#!/usr/bin/env python3
"""Generate a compact range review risk packet from exact truth hosts."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import review_artifact_lint
import review_header_metadata
from post_merge_packetization_gate import PACKETIZATION_GATE_RECEIPT_NAME, PACKETIZATION_GATE_SCHEMA_VERSION
from range_review_risk_packet_schema_contract import RANGE_REVIEW_RISK_PACKET_SCHEMA_VERSION


SCHEMA_VERSION = RANGE_REVIEW_RISK_PACKET_SCHEMA_VERSION
REPORT_DIR = Path("docs") / "reviews"
RISK_PACKET_MARKER = "_risk_packet_range_"
PLAN_SPEC_RE = re.compile(r"^`?(?P<path>docs/plans/[A-Za-z0-9_./-]+\.md)`?$")
TARGET_RANGE_RE = re.compile(
    r"^RANGE=(?P<range>[^\s()]+) \(EXCLUDE_DOCS=(?P<exclude_docs>[01])\)$"
)
H2_RE = re.compile(r"^\s*##\s+(?P<title>.+?)\s*$", re.MULTILINE)
BLOCKER_ID_RE = re.compile(r"\bB\d+\b")
JSON_BLOCK_RE = re.compile(r"```json\s*(?P<body>\{.*?\})\s*```", re.DOTALL)
RUNTIME_PREFIXES = (
    "apps/",
    "config/",
    "core/",
    "templates/",
    "static/",
    "assets/",
    "manage.py",
    "requirements",
    "pyproject.toml",
)
HELPER_PROCESS_PREFIXES = (
    "docs/",
    "scripts/",
    ".github/",
    ".planveyor",
)
REQUIRED_HOSTS = (
    "review_artifact",
    "post_merge_audit",
    "operational_receipt",
    "ready_to_push_closeout",
    "packetization_report",
)
MANUAL_NO_ORIGIN_SPEC = "N/A (origin_plan_state=manual_range_review_no_origin_plan)"


@dataclass(frozen=True)
class PacketError:
    code: str
    detail: str
    next_action: str

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "detail": self.detail,
            "next_action": self.next_action,
        }


@dataclass(frozen=True)
class RiskPacketReadback:
    state: str
    packet_path: str
    payload: dict[str, Any] | None
    errors: tuple[PacketError, ...]
    required_truth_hosts: tuple[str, ...] = REQUIRED_HOSTS
    same_transaction_created: bool = False

    @property
    def ok(self) -> bool:
        return self.state == "ok" and not self.errors and self.payload is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "state": self.state,
            "packet_path": self.packet_path,
            "packet_status": (self.payload or {}).get("packet_status", "blocked"),
            "required_truth_hosts": list(self.required_truth_hosts),
            "same_transaction_created": self.same_transaction_created,
            "errors": [error.as_dict() for error in self.errors],
        }


def repo_rel(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def resolve_repo_path(repo_root: Path, path: str | None) -> Path | None:
    if path is None or not path.strip():
        return None
    raw_path = Path(path)
    return raw_path if raw_path.is_absolute() else repo_root / raw_path


def run_git(repo_root: Path, *args: str) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        text=True,
        capture_output=True,
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def read_saved_range(repo_root: Path) -> str:
    def read_one(rel_path: str) -> str:
        path = repo_root / rel_path
        if not path.is_file():
            raise ValueError(f"missing {rel_path}")
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                return stripped
        raise ValueError(f"empty {rel_path}")

    return f"{read_one('.planveyor.range.base')}..{read_one('.planveyor.range.head')}"


def split_range(range_ref: str) -> tuple[str, str]:
    if ".." not in range_ref:
        raise ValueError(f"range must use BASE..HEAD: {range_ref}")
    base, head = range_ref.split("..", 1)
    base = base.strip()
    head = head.strip()
    if not base or not head:
        raise ValueError(f"range must include non-empty BASE and HEAD: {range_ref}")
    return base, head


def changed_files_for_range(repo_root: Path, range_ref: str) -> list[str]:
    rc, stdout, stderr = run_git(repo_root, "diff", "--name-only", range_ref)
    if rc != 0:
        detail = stderr.strip() or stdout.strip() or f"git diff failed for {range_ref}"
        raise RuntimeError(detail)
    return sorted(line.strip() for line in stdout.splitlines() if line.strip())


def _status_value(text: str) -> str:
    value, _line_no = review_header_metadata.singleton_header_value(text.splitlines(), "status")
    return value or "unknown"


def _validate_review_status(review_text: str) -> list[PacketError]:
    lines = review_text.splitlines()
    values = review_header_metadata.header_values(lines, "status")
    if not values:
        return [
            PacketError(
                code="missing_review_status",
                detail="review artifact has no non-empty top-level **Status:** carrier",
                next_action="rewrite the review artifact with one canonical preamble Status field",
            )
        ]
    if len(values) > 1:
        return [
            PacketError(
                code="ambiguous_review_status",
                detail="review artifact has duplicate top-level **Status:** carriers",
                next_action="rewrite the review artifact with exactly one canonical preamble Status field",
            )
        ]
    canonical_value, _line_no = review_header_metadata.singleton_header_value(lines, "status")
    if canonical_value is None:
        return [
            PacketError(
                code="invalid_review_status",
                detail="review artifact Status label is not in canonical `**Status:**` form",
                next_action="rewrite the review artifact with one canonical preamble Status field",
            )
        ]
    if not values[0][1].strip():
        return [
            PacketError(
                code="missing_review_status",
                detail="review artifact has an empty top-level **Status:** carrier",
                next_action="rewrite the review artifact with one non-empty canonical preamble Status field",
            )
        ]
    return []


def _target_value(text: str) -> str:
    value, _line_no = review_header_metadata.singleton_header_value(text.splitlines(), "target")
    return value.strip() if value else ""


def _spec_value(text: str) -> str | None:
    value, _line_no = review_header_metadata.singleton_header_value(text.splitlines(), "spec")
    return value.strip("` ").strip() if value else None


def _spec_path_from_value(value: str) -> str | None:
    match = PLAN_SPEC_RE.match(value)
    if match is None:
        return None
    return match.group("path")


def _range_from_target(value: str) -> str | None:
    match = TARGET_RANGE_RE.fullmatch(value)
    if match is None:
        return None
    range_ref = match.group("range").strip()
    return range_ref or None


def _exact_range_target_matches(value: object, *, expected_range: str) -> bool:
    """Accept only the range packet's own canonical target grammar.

    Range packets intentionally do not reuse current-review target parsing.
    Their only authority is the requested ``BASE..HEAD`` range plus the
    explicit EXCLUDE_DOCS bit; a current-shaped or prose-shaped value must be
    rejected before lifecycle selection or durable output handling.
    """

    if not isinstance(value, str):
        return False
    match = TARGET_RANGE_RE.fullmatch(value)
    return match is not None and match.group("range") == expected_range


def markdown_section(text: str, heading: str) -> str:
    for match in H2_RE.finditer(text):
        if match.group("title").strip().lower() != heading.lower():
            continue
        next_match = H2_RE.search(text, match.end())
        end = next_match.start() if next_match else len(text)
        return text[match.end() : end]
    return ""


def _section_is_empty_or_na(section: str) -> bool:
    normalized = " ".join(section.lower().replace("`", "").split())
    return not normalized or normalized.startswith("n/a") or "not found" in normalized


def _blocker_entry(blocker_id: str, *, state: str, source: str) -> dict[str, str]:
    return {"id": blocker_id, "state": state, "truth_host": source}


def parse_live_blockers(review_text: str, review_rel: str) -> list[dict[str, str]]:
    status = _status_value(review_text).lower()
    if "❌" not in status and "blocker" not in status:
        return []
    section = markdown_section(review_text, "S1 Blocker")
    if _section_is_empty_or_na(section):
        return [_blocker_entry("B1", state="live_missing_details", source=f"{review_rel}#S1-Blocker")]
    ids = sorted(set(BLOCKER_ID_RE.findall(section)))
    if not ids:
        ids = ["B1"]
    return [_blocker_entry(blocker_id, state="live", source=f"{review_rel}#{blocker_id}") for blocker_id in ids]


def parse_historical_blockers(review_text: str, review_rel: str) -> list[dict[str, str]]:
    historical: list[dict[str, str]] = []
    for line in review_text.splitlines():
        normalized = line.lower()
        if not any(marker in normalized for marker in ("historical", "historical-fixed", "closed", "fixed")):
            continue
        for blocker_id in sorted(set(BLOCKER_ID_RE.findall(line))):
            historical.append(_blocker_entry(blocker_id, state="historical_closed", source=f"{review_rel}#{blocker_id}"))
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for item in historical:
        key = f"{item['id']}|{item['truth_host']}"
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def parse_residual_risks(review_text: str, review_rel: str) -> list[dict[str, str]]:
    section = markdown_section(review_text, "S2 Risk")
    if _section_is_empty_or_na(section):
        return []
    risks: list[dict[str, str]] = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped or stripped.lower().startswith("n/a"):
            continue
        risks.append({"summary": stripped.lstrip("- ").strip(), "truth_host": f"{review_rel}#S2-Risk"})
    return risks


def parse_visual_status(review_text: str, review_rel: str) -> dict[str, str]:
    visual_section = markdown_section(review_text, "Визуальные доказательства") or markdown_section(review_text, "Visual evidence")
    for line in review_text.splitlines():
        normalized = line.lower()
        if "visual review" in normalized or "visual gate" in normalized or "visual env" in normalized:
            if "n/a" in normalized:
                return {
                    "status": "N/A",
                    "reason": line.strip().lstrip("- ").strip(),
                    "truth_host": f"{review_rel}#visual",
                }
    if visual_section:
        if "n/a" in visual_section.lower():
            return {
                "status": "N/A",
                "reason": "visual section declares N/A",
                "truth_host": f"{review_rel}#visual",
            }
        return {
            "status": "present",
            "reason": "visual section present",
            "truth_host": f"{review_rel}#visual",
        }
    return {
        "status": "unknown",
        "reason": "visual status not found in review artifact",
        "truth_host": review_rel,
    }


def _extract_first_json_payload(text: str, schema_marker: str) -> dict[str, Any] | None:
    for match in JSON_BLOCK_RE.finditer(text):
        try:
            payload = json.loads(match.group("body"))
        except json.JSONDecodeError:
            continue
        if schema_marker in json.dumps(payload, ensure_ascii=False):
            return payload
    return None


def _host_summary(kind: str, path: Path, repo_root: Path) -> dict[str, Any]:
    rel_path = repo_rel(path, repo_root)
    text = path.read_text(encoding="utf-8", errors="replace")
    summary: dict[str, Any] = {
        "kind": kind,
        "path": rel_path,
        "status": _status_value(text),
    }
    if kind == "post_merge_audit":
        first_h1 = ""
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if line.startswith("# "):
                first_h1 = " ".join(line[2:].split())
                break
        is_post_merge_audit = (
            "post_merge_audit" in path.name.lower()
            or "post-merge audit" in first_h1.lower()
        )
        summary["event_type"] = "review.post_merge_audit" if is_post_merge_audit else "unknown"
    elif kind == "operational_receipt":
        summary["schema_version"] = "post_merge_operational_receipt.v1" if "post_merge_operational_receipt.v1" in text else "unknown"
    elif kind == "ready_to_push_closeout":
        summary["schema_version"] = "ready_to_push_closeout_receipt.v1" if "ready_to_push_closeout_receipt.v1" in text else "unknown"
    elif kind == "packetization_report":
        payload = _extract_first_json_payload(text, PACKETIZATION_GATE_RECEIPT_NAME)
        summary["schema_version"] = PACKETIZATION_GATE_RECEIPT_NAME
        if payload and isinstance(payload.get(PACKETIZATION_GATE_RECEIPT_NAME), dict):
            gate_payload = payload[PACKETIZATION_GATE_RECEIPT_NAME]
            summary["schema_version"] = gate_payload.get("schema_version") or PACKETIZATION_GATE_RECEIPT_NAME
            summary["blocking_count"] = gate_payload.get("blocking_count")
            summary["schema_version_expected"] = PACKETIZATION_GATE_SCHEMA_VERSION
    return summary


def classify_changed_paths(paths: Sequence[str]) -> tuple[list[str], list[str]]:
    runtime: list[str] = []
    helper: list[str] = []
    for path in sorted(set(paths)):
        normalized = path.replace("\\", "/")
        if normalized.startswith(HELPER_PROCESS_PREFIXES):
            helper.append(normalized)
        elif normalized.startswith(RUNTIME_PREFIXES):
            runtime.append(normalized)
        else:
            helper.append(normalized)
    return runtime, helper


def same_range_packet_paths(repo_root: Path, *, base_short: str, head_short: str, exclude: Path | None = None) -> list[Path]:
    pattern = f"*{RISK_PACKET_MARKER}{base_short}_{head_short}.md"
    excluded = exclude.resolve() if exclude else None
    paths: list[Path] = []
    for path in sorted((repo_root / REPORT_DIR).glob(pattern)):
        if not path.is_file():
            continue
        if excluded and path.resolve() == excluded:
            continue
        paths.append(path)
    return paths


def packet_is_superseded(path: Path) -> bool:
    text = path.read_text(encoding="utf-8", errors="replace")
    status = _status_value(text).lower()
    return status.startswith("superseded")


def default_packet_path(repo_root: Path, *, base_short: str, head_short: str, now: datetime) -> Path:
    return repo_root / REPORT_DIR / f"{now:%y%m%d_%H%M%S}_risk_packet_range_{base_short}_{head_short}.md"


def _risk_payload_from_value(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    for key in ("risk_packet", "range_review_risk_packet"):
        nested = value.get(key)
        if isinstance(nested, dict) and "schema_version" in nested:
            return nested
    if "schema_version" in value:
        return value
    return None


def _risk_payload_from_text(text: str) -> tuple[dict[str, Any] | None, str | None]:
    malformed_json_seen = False
    for match in JSON_BLOCK_RE.finditer(text):
        try:
            parsed = json.loads(match.group("body"))
        except json.JSONDecodeError:
            malformed_json_seen = True
            continue
        payload = _risk_payload_from_value(parsed)
        if payload is not None:
            return payload, None
    if malformed_json_seen:
        return None, "malformed_json"
    return None, "missing_schema_payload"


def _readback_state_from_errors(errors: Sequence[PacketError]) -> str:
    if not errors:
        return "ok"
    code = errors[0].code
    if code == "missing_risk_packet":
        return "missing"
    if code == "ambiguous_risk_packet":
        return "ambiguous"
    if code == "superseded_risk_packet":
        return "superseded"
    if code in {"unparseable_risk_packet", "risk_packet_schema_mismatch"}:
        return "unparseable"
    if code == "risk_packet_range_mismatch":
        return "range_mismatched"
    if code in {"missing_truth_host", "missing_truth_host_path"}:
        return "missing_truth_hosts"
    if code == "risk_packet_not_ok":
        return "blocked"
    return "invalid"


def _missing_packet_error(pattern: str) -> PacketError:
    return PacketError(
        code="missing_risk_packet",
        detail=f"no active non-superseded risk packet matched {pattern}",
        next_action="run planveyor_review_risk_packet for the same range",
    )


def _resolve_active_packet_path(
    repo_root: Path,
    *,
    base_short: str,
    head_short: str,
    risk_packet_path: Path | None = None,
) -> tuple[Path | None, list[PacketError], str]:
    if risk_packet_path is not None:
        path = risk_packet_path if risk_packet_path.is_absolute() else repo_root / risk_packet_path
        rel_path = repo_rel(path, repo_root)
        if not path.is_file():
            return None, [
                PacketError(
                    code="missing_risk_packet",
                    detail=f"risk packet path does not exist: {rel_path}",
                    next_action="materialize the risk packet or pass the correct --risk-packet",
                )
            ], rel_path
        if packet_is_superseded(path):
            return path, [
                PacketError(
                    code="superseded_risk_packet",
                    detail=f"risk packet is superseded: {rel_path}",
                    next_action="pass the active non-superseded risk packet",
                )
            ], rel_path
        return path, [], rel_path

    pattern = f"docs/reviews/*{RISK_PACKET_MARKER}{base_short}_{head_short}.md"
    candidates = same_range_packet_paths(repo_root, base_short=base_short, head_short=head_short)
    active = [path for path in candidates if not packet_is_superseded(path)]
    superseded = [path for path in candidates if packet_is_superseded(path)]
    if not active:
        if superseded:
            rel_paths = ", ".join(repo_rel(path, repo_root) for path in superseded)
            return None, [
                PacketError(
                    code="superseded_risk_packet",
                    detail=f"only superseded same-range risk packet(s) found: {rel_paths}",
                    next_action="regenerate the active non-superseded risk packet for the same range",
                )
            ], pattern
        return None, [_missing_packet_error(pattern)], pattern
    if len(active) > 1:
        rel_paths = ", ".join(repo_rel(path, repo_root) for path in active)
        return None, [
            PacketError(
                code="ambiguous_risk_packet",
                detail=f"multiple active non-superseded risk packets matched: {rel_paths}",
                next_action="supersede stale risk packets or pass --risk-packet PATH",
            )
        ], pattern
    return active[0], [], repo_rel(active[0], repo_root)


def _validate_payload_range(
    payload: dict[str, Any],
    *,
    expected_range: str,
    expected_base: str,
    expected_head: str,
    packet_rel: str,
) -> list[PacketError]:
    errors: list[PacketError] = []
    actual_schema = payload.get("schema_version")
    if actual_schema != SCHEMA_VERSION:
        errors.append(
            PacketError(
                code="risk_packet_schema_mismatch",
                detail=f"risk packet schema_version is {actual_schema!r}, expected {SCHEMA_VERSION}",
                next_action="rerun planveyor_review_risk_packet with the current helper",
            )
        )
    actual_base = str(payload.get("base") or "")
    actual_head = str(payload.get("head") or "")
    actual_range = str(payload.get("range") or "")
    if expected_base and actual_base and actual_base != expected_base:
        errors.append(
            PacketError(
                code="risk_packet_range_mismatch",
                detail=f"risk packet base {actual_base} does not match expected base {expected_base}",
                next_action="regenerate the risk packet for the active range",
            )
        )
    if expected_head and actual_head and actual_head != expected_head:
        errors.append(
            PacketError(
                code="risk_packet_range_mismatch",
                detail=f"risk packet head {actual_head} does not match expected head {expected_head}",
                next_action="regenerate the risk packet for the active range",
            )
        )
    if expected_range and actual_range and actual_range != expected_range:
        errors.append(
            PacketError(
                code="risk_packet_range_mismatch",
                detail=f"risk packet range {actual_range} does not match expected range {expected_range}",
                next_action="regenerate the risk packet for the active range",
            )
        )
    target_snapshot = payload.get("target_snapshot")
    if not _exact_range_target_matches(target_snapshot, expected_range=expected_range):
        errors.append(
            PacketError(
                code="risk_packet_target_mismatch",
                detail=(
                    "risk packet target_snapshot must exactly equal "
                    f"RANGE={expected_range} (EXCLUDE_DOCS=<0|1>); observed {target_snapshot!r}"
                ),
                next_action="regenerate the risk packet for the active range with a canonical range Target",
            )
        )
    if payload.get("packet_status") != "ok":
        errors.append(
            PacketError(
                code="risk_packet_not_ok",
                detail=f"risk packet packet_status is {payload.get('packet_status')!r}: {packet_rel}",
                next_action="resolve review blockers and regenerate the risk packet",
            )
        )
    return errors


def _validate_payload_truth_hosts(
    repo_root: Path,
    payload: dict[str, Any],
) -> list[PacketError]:
    hosts = payload.get("truth_hosts")
    if not isinstance(hosts, dict):
        hosts = {}
    errors: list[PacketError] = []
    for key in REQUIRED_HOSTS:
        host = hosts.get(key)
        if not isinstance(host, dict):
            errors.append(
                PacketError(
                    code="missing_truth_host",
                    detail=f"risk packet is missing required truth host {key}",
                    next_action="regenerate planveyor_review_risk_packet with exact truth-host paths",
                )
            )
            continue
        path_value = str(host.get("path") or "")
        if not path_value or path_value.startswith("N/A"):
            errors.append(
                PacketError(
                    code="missing_truth_host",
                    detail=f"risk packet is missing required truth host {key}",
                    next_action="regenerate planveyor_review_risk_packet with exact truth-host paths",
                )
            )
            continue
        resolved = resolve_repo_path(repo_root, path_value)
        if resolved is None or not resolved.is_file():
            errors.append(
                PacketError(
                    code="missing_truth_host_path",
                    detail=f"truth host path for {key} does not exist: {path_value}",
                    next_action="materialize the missing artifact or regenerate the risk packet",
                )
            )
    return errors


def read_risk_packet(
    repo_root: Path,
    *,
    range_ref: str,
    risk_packet_path: Path | None = None,
    same_transaction_created: bool = False,
) -> RiskPacketReadback:
    repo_root = repo_root.resolve()
    base, head = split_range(range_ref)
    packet_path, errors, packet_ref = _resolve_active_packet_path(
        repo_root,
        base_short=base[:7],
        head_short=head[:7],
        risk_packet_path=risk_packet_path,
    )
    if errors:
        return RiskPacketReadback(
            state=_readback_state_from_errors(errors),
            packet_path=packet_ref,
            payload=None,
            errors=tuple(errors),
            same_transaction_created=same_transaction_created,
        )

    assert packet_path is not None
    packet_rel = repo_rel(packet_path, repo_root)
    text = packet_path.read_text(encoding="utf-8", errors="replace")
    payload, parse_error = _risk_payload_from_text(text)
    if payload is None:
        errors = [
            PacketError(
                code="unparseable_risk_packet",
                detail=f"risk packet JSON block is not parseable: {parse_error}",
                next_action="rerun planveyor_review_risk_packet",
            )
        ]
        return RiskPacketReadback(
            state="unparseable",
            packet_path=packet_rel,
            payload=None,
            errors=tuple(errors),
            same_transaction_created=same_transaction_created,
        )

    errors = [
        *_validate_payload_range(
            payload,
            expected_range=range_ref,
            expected_base=base,
            expected_head=head,
            packet_rel=packet_rel,
        ),
        *_validate_payload_truth_hosts(repo_root, payload),
    ]
    return RiskPacketReadback(
        state=_readback_state_from_errors(errors),
        packet_path=packet_rel,
        payload=payload,
        errors=tuple(errors),
        same_transaction_created=same_transaction_created,
    )


def _validate_required_hosts(repo_root: Path, hosts: dict[str, Path | None]) -> list[PacketError]:
    errors: list[PacketError] = []
    for key in REQUIRED_HOSTS:
        path = hosts.get(key)
        if path is None:
            errors.append(
                PacketError(
                    code="missing_truth_host",
                    detail=f"{key} path is required",
                    next_action=f"pass --{key.replace('_', '-')} PATH and rerun planveyor_review_risk_packet",
                )
            )
            continue
        if not path.is_file():
            errors.append(
                PacketError(
                    code="missing_truth_host",
                    detail=f"{key} path does not exist: {repo_rel(path, repo_root)}",
                    next_action=f"materialize or pass the correct {key} truth host, then rerun planveyor_review_risk_packet",
                )
            )
    return errors


def _validate_plan_risk_lane(
    repo_root: Path,
    review_text: str,
    review_target: str,
    *,
    expected_range: str,
) -> list[PacketError]:
    if not review_target:
        return [
            PacketError(
                code="missing_review_target",
                detail="review artifact has no non-empty top-level **Target:** carrier",
                next_action="rewrite the review artifact with `**Target:** RANGE=<base>..<head> (EXCLUDE_DOCS=<0|1>)`",
            )
        ]

    spec_value = _spec_value(review_text)
    if spec_value is None or not spec_value:
        return [
            PacketError(
                code="missing_review_spec",
                detail="review artifact has no non-empty top-level **Spec:** carrier",
                next_action=(
                    "rewrite the review artifact with `**Spec:** docs/plans/...md` or exact "
                    f"`**Spec:** {MANUAL_NO_ORIGIN_SPEC}` for manual no-origin reviews"
                ),
            )
        ]
    if spec_value == MANUAL_NO_ORIGIN_SPEC:
        review_range = _range_from_target(review_target)
        if review_range != expected_range:
            return [
                PacketError(
                    code="manual_no_origin_target_mismatch",
                    detail=(
                        f"manual no-origin review target range {review_range!r} does not match requested "
                        f"range {expected_range!r}"
                    ),
                    next_action=(
                        "rewrite the manual no-origin review artifact with "
                        "`**Target:** RANGE=<base>..<head> (EXCLUDE_DOCS=<0|1>)` for the requested range"
                    ),
                )
            ]
        return []

    spec_rel = _spec_path_from_value(spec_value)
    if spec_rel is None:
        return [
            PacketError(
                code="invalid_review_spec",
                detail=(
                    f"review artifact has invalid **Spec:** carrier {spec_value!r}; expected docs/plans/...md "
                    f"or exact {MANUAL_NO_ORIGIN_SPEC!r}"
                ),
                next_action="rewrite the review artifact with a valid machine-readable Spec carrier",
            )
        ]
    if not _exact_range_target_matches(review_target, expected_range=expected_range):
        return [
            PacketError(
                code="risk_packet_target_mismatch",
                detail=(
                    "review Target must exactly equal "
                    f"RANGE={expected_range} (EXCLUDE_DOCS=<0|1>); observed {review_target!r}"
                ),
                next_action=(
                    "rewrite the review artifact with the requested canonical range Target before "
                    "creating a risk packet"
                ),
            )
        ]
    spec_path = repo_root / spec_rel
    if not spec_path.is_file():
        return [
            PacketError(
                code="missing_origin_plan",
                detail=f"origin plan does not exist: {spec_rel}",
                next_action="materialize the origin plan or pass the matching review artifact",
            )
        ]
    selection = review_artifact_lint.select_plan_risk_lane_snapshot(spec_path)
    if selection.error_code:
        return [
            PacketError(
                code=str(selection.error_code),
                detail=str(selection.message or "current risk lane selection failed"),
                next_action="mark exactly one reviewer_code_risk payload current=true or supersede stale payloads",
            )
        ]
    if selection.snapshot is None:
        return [
            PacketError(
                code="missing_plan_resident_risk_lane",
                detail="origin plan has no parseable reviewer_code_risk target_snapshot JSON block",
                next_action="materialize the current reviewer_code_risk lane JSON in the plan before packet generation",
            )
        ]
    if selection.snapshot != review_target:
        return [
            PacketError(
                code="risk_lane_target_mismatch",
                detail=f"origin risk snapshot {selection.snapshot!r} does not match review target {review_target!r}",
                next_action="rerun Reviewer/finalizer so plan-resident risk snapshot and review artifact target match",
            )
        ]
    return []


def build_packet_payload(
    *,
    repo_root: Path,
    range_ref: str,
    out_path: Path,
    host_paths: dict[str, Path],
    changed_files: Sequence[str],
) -> tuple[dict[str, Any] | None, list[PacketError]]:
    errors = _validate_required_hosts(repo_root, host_paths)
    if errors:
        return None, errors

    review_path = host_paths["review_artifact"]
    review_rel = repo_rel(review_path, repo_root)
    review_text = review_path.read_text(encoding="utf-8", errors="replace")
    status_errors = _validate_review_status(review_text)
    if status_errors:
        return None, status_errors
    review_status = _status_value(review_text)
    review_target = _target_value(review_text)
    risk_lane_errors = _validate_plan_risk_lane(repo_root, review_text, review_target, expected_range=range_ref)
    if risk_lane_errors:
        return None, risk_lane_errors

    base, head = split_range(range_ref)
    runtime_paths, helper_paths = classify_changed_paths(changed_files)
    live_blockers = parse_live_blockers(review_text, review_rel)
    historical_blockers = parse_historical_blockers(review_text, review_rel)
    residual_risks = parse_residual_risks(review_text, review_rel)
    visual_readback = review_artifact_lint.evaluate_runtime_ui_visual_evidence(
        project_root=repo_root,
        review_path=review_path,
        review_text=review_text,
    )
    if visual_readback.state in {"red", "ambiguous"}:
        return None, [
            PacketError(
                code=f"runtime_ui_visual_evidence_{visual_readback.state}",
                detail=(
                    "authoritative final-review visual evidence blocks risk packet `ok`: "
                    + ",".join(visual_readback.reason_codes)
                ),
                next_action="complete comparator, full-index perceptual review and current-review durable assets",
            )
        ]
    if visual_readback.state == "green":
        visual_status = {
            "status": "green",
            "reason": "authoritative current-review visual evidence readback",
            "truth_host": f"{review_rel}#visual",
        }
    else:
        visual_status = parse_visual_status(review_text, review_rel)
    host_summaries = {
        key: _host_summary(key, path, repo_root)
        for key, path in host_paths.items()
    }
    closure_artifacts = [
        {"kind": key, "path": repo_rel(path, repo_root)}
        for key, path in host_paths.items()
        if key != "review_artifact"
    ]
    if historical_blockers:
        closure_artifacts.append({"kind": "same_file_review_rerun", "path": review_rel})

    packet_status = "review_blocked" if live_blockers else "ok"
    return (
        {
            "schema_version": SCHEMA_VERSION,
            "packet_status": packet_status,
            "packet_path": repo_rel(out_path, repo_root),
            "range": range_ref,
            "range_id": f"{base[:7]}..{head[:7]}",
            "base": base,
            "head": head,
            "target_snapshot": review_target,
            "runtime_touched_paths": runtime_paths,
            "helper_process_touched_paths": helper_paths,
            "visual_status": visual_status,
            "live_blockers": live_blockers,
            "historical_blockers": historical_blockers,
            "closure_artifacts": closure_artifacts,
            "residual_risks": residual_risks,
            "truth_hosts": host_summaries,
        },
        [],
    )


def _table_rows(values: Sequence[str]) -> list[str]:
    if not values:
        return ["| N/A |", "| --- |"]
    return ["| path |", "| --- |", *[f"| `{value}` |" for value in values]]


def render_packet_markdown(payload: dict[str, Any]) -> str:
    runtime_rows = "\n".join(_table_rows(payload["runtime_touched_paths"]))
    helper_rows = "\n".join(_table_rows(payload["helper_process_touched_paths"]))
    truth_rows = ["| kind | path | status |", "| --- | --- | --- |"]
    for key, host in payload["truth_hosts"].items():
        truth_rows.append(f"| {key} | `{host['path']}` | {host.get('status', 'unknown')} |")

    blocker_rows = ["| blocker | state | truth_host |", "| --- | --- | --- |"]
    blockers = [*payload["live_blockers"], *payload["historical_blockers"]]
    if blockers:
        for blocker in blockers:
            blocker_rows.append(f"| {blocker['id']} | {blocker['state']} | `{blocker['truth_host']}` |")
    else:
        blocker_rows.append("| N/A | N/A | N/A |")

    return "\n".join(
        [
            "# Range review risk packet",
            "",
            f"**Schema version:** {SCHEMA_VERSION}",
            "**Status:** ✅ Done",
            f"**Range:** `{payload['range']}`",
            f"**Packet status:** `{payload['packet_status']}`",
            "",
            "## Summary",
            f"- range_id: `{payload['range_id']}`",
            f"- target_snapshot: `{payload['target_snapshot']}`",
            f"- visual_status: `{payload['visual_status']['status']}`",
            f"- live_blockers_count: {len(payload['live_blockers'])}",
            f"- historical_blockers_count: {len(payload['historical_blockers'])}",
            f"- residual_risks_count: {len(payload['residual_risks'])}",
            "",
            "## Runtime touched paths",
            runtime_rows,
            "",
            "## Helper/process touched paths",
            helper_rows,
            "",
            "## Blockers",
            "\n".join(blocker_rows),
            "",
            "## Closure artifacts",
            "| kind | path |",
            "| --- | --- |",
            *[f"| {item['kind']} | `{item['path']}` |" for item in payload["closure_artifacts"]],
            "",
            "## Truth hosts",
            "\n".join(truth_rows),
            "",
            "## Risk packet JSON",
            "```json",
            json.dumps({"risk_packet": payload}, ensure_ascii=False, indent=2, sort_keys=True),
            "```",
            "",
        ]
    )


def render_plain(payload: dict[str, Any] | None, errors: Sequence[PacketError]) -> str:
    if errors:
        lines = ["range_review_risk_packet: blocked", "errors:"]
        lines.extend(f"  - {error.code}: {error.detail}" for error in errors)
        return "\n".join(lines)
    assert payload is not None
    return "\n".join(
        [
            "range_review_risk_packet: ok",
            f"  packet_path: {payload['packet_path']}",
            f"  packet_status: {payload['packet_status']}",
            f"  range_id: {payload['range_id']}",
            f"  live_blockers_count: {len(payload['live_blockers'])}",
            f"  historical_blockers_count: {len(payload['historical_blockers'])}",
        ]
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="Repository root (default: current directory).")
    parser.add_argument("--range", dest="range_ref", help="Git range BASE..HEAD; defaults to saved .planveyor range.")
    parser.add_argument("--review-artifact", required=True, help="Live review artifact truth host.")
    parser.add_argument("--post-merge-audit", required=True, help="Post-merge audit truth host.")
    parser.add_argument("--operational-receipt", required=True, help="Operational receipt truth host.")
    parser.add_argument("--ready-to-push-closeout", required=True, help="Ready-to-push closeout truth host.")
    parser.add_argument("--packetization-report", required=True, help="Packetization report truth host.")
    parser.add_argument("--out", help="Output path; default docs/reviews/<stamp>_risk_packet_range_<base7>_<head7>.md.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable readback.")
    parser.add_argument("--now", default=None, help=argparse.SUPPRESS)
    return parser


def parse_now(value: str | None) -> datetime:
    if not value:
        return datetime.now()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%y%m%d_%H%M%S", "%y%m%d_%H%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    raise ValueError(f"unsupported --now value: {value}")


def _error_response(errors: Sequence[PacketError], *, packet_path: str | None = None) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "blocked",
        "packet_status": "blocked",
        "packet_path": packet_path or "N/A (why=packet not written)",
        "errors": [error.as_dict() for error in errors],
    }


def main(argv: Sequence[str] | None = None) -> int:
    ns = build_parser().parse_args(argv)
    repo_root = Path(ns.repo_root).resolve()
    try:
        now = parse_now(ns.now)
        range_ref = ns.range_ref or read_saved_range(repo_root)
        base, head = split_range(range_ref)
        base_short = base[:7]
        head_short = head[:7]
        out_path = resolve_repo_path(repo_root, ns.out) if ns.out else default_packet_path(
            repo_root,
            base_short=base_short,
            head_short=head_short,
            now=now,
        )
        assert out_path is not None
        if ns.out is None:
            active = [path for path in same_range_packet_paths(repo_root, base_short=base_short, head_short=head_short) if not packet_is_superseded(path)]
            if active:
                rel_paths = ", ".join(repo_rel(path, repo_root) for path in active)
                raise RuntimeError(f"ambiguous active same-range risk packets; pass --out or supersede older packet: {rel_paths}")
        changed_files = changed_files_for_range(repo_root, range_ref)
        host_paths = {
            "review_artifact": resolve_repo_path(repo_root, ns.review_artifact),
            "post_merge_audit": resolve_repo_path(repo_root, ns.post_merge_audit),
            "operational_receipt": resolve_repo_path(repo_root, ns.operational_receipt),
            "ready_to_push_closeout": resolve_repo_path(repo_root, ns.ready_to_push_closeout),
            "packetization_report": resolve_repo_path(repo_root, ns.packetization_report),
        }
        payload, errors = build_packet_payload(
            repo_root=repo_root,
            range_ref=range_ref,
            out_path=out_path,
            host_paths={key: value for key, value in host_paths.items() if value is not None},
            changed_files=changed_files,
        )
        if errors:
            response = _error_response(errors, packet_path=repo_rel(out_path, repo_root))
            if ns.json:
                sys.stdout.write(json.dumps({"range_review_risk_packet": response}, ensure_ascii=False, sort_keys=True) + "\n")
            else:
                sys.stdout.write(render_plain(None, errors) + "\n")
            return 2
        assert payload is not None
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(render_packet_markdown(payload), encoding="utf-8")
    except (OSError, RuntimeError, ValueError) as exc:
        errors = [
            PacketError(
                code="risk_packet_generation_failed",
                detail=str(exc),
                next_action="fix range/truth-host inputs or pass explicit --out, then rerun planveyor_review_risk_packet",
            )
        ]
        response = _error_response(errors)
        if ns.json:
            sys.stdout.write(json.dumps({"range_review_risk_packet": response}, ensure_ascii=False, sort_keys=True) + "\n")
        else:
            sys.stdout.write(render_plain(None, errors) + "\n")
        return 2

    if ns.json:
        sys.stdout.write(json.dumps({"range_review_risk_packet": payload}, ensure_ascii=False, sort_keys=True) + "\n")
    else:
        sys.stdout.write(render_plain(payload, []) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

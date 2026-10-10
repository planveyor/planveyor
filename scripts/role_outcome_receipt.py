#!/usr/bin/env python3
"""Finalize machine-owned role outcome receipts for the custom pipeline."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tempfile
from typing import Any, Callable, Iterator

sys.dont_write_bytecode = True
sys.pycache_prefix = os.devnull



def _authority_module() -> Any:
    """Import the sibling authority parser without consulting a target package."""

    expected = Path(__file__).resolve().with_name("contract_authority_context.py")
    loaded = [
        sys.modules[name]
        for name in ("contract_authority_context", "scripts.contract_authority_context")
        if name in sys.modules
    ]
    for module in loaded:
        origin = getattr(module, "__file__", None)
        if not isinstance(origin, str) or Path(origin).resolve(strict=True) != expected:
            raise ImportError("authority module has an unsafe origin")
    if len({id(module) for module in loaded}) > 1:
        raise ImportError("authority module aliases are split")
    if loaded:
        return loaded[0]
    script_dir = str(expected.parent)
    while script_dir in sys.path:
        sys.path.remove(script_dir)
    sys.path.insert(0, script_dir)
    return importlib.import_module("contract_authority_context")

READBACK_SCHEMA = "role_outcome_readback.v1"
PREFLIGHT_SCHEMA = "role_outcome_preflight.v1"
EXECUTION_SCHEMA = "role_execution_receipt.v1"
LINT_SCHEMA = "role_outcome_semantic_lint.v1"
DIAGNOSTIC_SCHEMA = "role_outcome_semantic_diagnostic.v1"
RECOVERY_SCHEMA = "role_outcome_recovery.v1"
RESERVATION_SCHEMA = "role_outcome_rerun_reservation.v1"
REJECTION_SCHEMA = "role_outcome_rejection_receipt.v1"
RERUN_STARTED_SCHEMA = "role_outcome_rerun_started.v1"
ACTIVE_MODE_ROW = "- Mode: manager-custom-pipeline"
EVIDENCE_HEADINGS = (
    "## Evidence (chronological, append-only)",
    "## Evidence",
)
DRAFT_MARKER = "- Role outcome semantic draft"
RECEIPT_MARKER = "- Role outcome receipt"
REJECTION_MARKER = "- Role outcome rejection receipt"
RERUN_STARTED_MARKER = "- Role outcome rerun started"
SEMANTIC_FIELDS = (
    "worked",
    "blocked_by",
    "helped_by",
    "residuals",
    "candidate_followups",
    "gates",
)
ENVELOPE_FIELDS = (
    "role",
    "lane",
    "run_id",
    "target_plan",
    "artifact_ref",
    "written_at",
)
ROLE_LANES = {
    "planner": "planner",
    "coder": "coder",
    "reviewer_code_risk": "reviewer_code_risk",
    "reviewer_code_contracts": "reviewer_code_contracts",
}
PERSISTED_STATES = {"finalized", "blocked"}
SUCCESS_REASONS = {"ok", "already_finalized"}
BLOCKED_REASONS = {
    "preexisting_semantic_draft",
    "carrier_resolution_failed",
    "unsafe_carrier_path",
    "execution_receipt_invalid",
    "execution_identity_mismatch",
    "execution_authority_context_invalid",
    "execution_authority_root_mismatch",
    "semantic_draft_missing",
    "semantic_draft_duplicate",
    "semantic_draft_invalid",
    "wrong_placement",
    "forbidden_carrier_present",
    "current_outcome_duplicate",
    "carrier_changed",
    "carrier_write_failed",
    "readback_write_failed",
    "recovery_chain_invalid",
}
DIAGNOSTIC_RULES = (
    "field_missing",
    "field_order_invalid",
    "unexpected_label",
    "bullet_count_out_of_range",
    "na_must_be_single",
    "na_syntax_invalid",
    "na_trailing_punctuation",
    "bullet_empty",
    "bullet_too_long",
    "forbidden_fence",
    "forbidden_json",
)
REJECTION_FIELDS = (
    "schema_version",
    "run_id",
    "role",
    "lane",
    "target_plan",
    "carrier_path",
    "semantic_draft_sha256",
    "reason_code",
    "recovery_state",
    "rerun_budget",
    "written_at",
)
RERUN_STARTED_FIELDS = (
    "schema_version",
    "run_id",
    "recovery_of_run_id",
    "rejection_receipt_sha256",
    "role",
    "lane",
    "target_plan",
    "carrier_path",
    "started_at",
)
PLAN_RE = re.compile(r"^docs/plans/[^/]+\.md$")
REVIEW_RE = re.compile(r"docs/(?:code_reviews|doc_reviews)/[^`\s]+\.md")
RFC3339_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


class OutcomeError(Exception):
    def __init__(
        self,
        reason_code: str,
        *,
        carrier_path: str | None = None,
        artifact_ref: str | None = None,
        semantic_draft_count: int = 0,
        finalized_receipt_count: int = 0,
        forbidden_carrier_hits: list[str] | None = None,
    ) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code
        self.carrier_path = carrier_path
        self.artifact_ref = artifact_ref
        self.semantic_draft_count = semantic_draft_count
        self.finalized_receipt_count = finalized_receipt_count
        self.forbidden_carrier_hits = forbidden_carrier_hits or []


class CarrierChanged(OutcomeError):
    def __init__(self) -> None:
        super().__init__("carrier_changed")


@dataclass(frozen=True)
class Paths:
    root: Path
    plan_rel: str
    plan: Path
    output_dir: Path
    readback: Path
    preflight: Path
    execution_receipt: Path | None


@dataclass(frozen=True)
class Placement:
    expected_rel: str
    expected: Path
    artifact_ref: str
    forbidden_rel: str | None
    forbidden: Path | None


@dataclass(frozen=True)
class SemanticBlock:
    start: int
    end: int
    values: dict[str, list[str]]


@dataclass(frozen=True)
class ReceiptBlock:
    start: int
    end: int
    envelope: dict[str, str]
    values: dict[str, list[str]]


@dataclass(frozen=True)
class OrderedBlock:
    start: int
    end: int
    values: dict[str, str]


@dataclass(frozen=True)
class RecoveryChain:
    draft_start: int
    rejection: OrderedBlock
    rejection_sha256: str
    rerun: OrderedBlock


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _repo_rel(value: str, pattern: re.Pattern[str], field: str) -> str:
    posix = PurePosixPath(value)
    if posix.is_absolute() or ".." in posix.parts or str(posix) != value or not pattern.fullmatch(value):
        raise OutcomeError("carrier_resolution_failed")
    if field == "plan" and not PLAN_RE.fullmatch(value):
        raise OutcomeError("carrier_resolution_failed")
    return value


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _inside(root: Path, path: Path) -> Path:
    root_abs = _absolute(root)
    candidate = _absolute(path)
    try:
        candidate.relative_to(root_abs)
    except ValueError as exc:
        raise OutcomeError("unsafe_carrier_path") from exc
    return candidate


def _validate_components(root: Path, path: Path, *, allow_missing_final: bool) -> Path:
    root = _absolute(root)
    path = _inside(root, path)
    try:
        root_info = root.lstat()
    except OSError as exc:
        raise OutcomeError("unsafe_carrier_path") from exc
    if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
        raise OutcomeError("unsafe_carrier_path")
    current = root
    parts = path.relative_to(root).parts
    for index, part in enumerate(parts):
        current /= part
        final = index == len(parts) - 1
        try:
            info = current.lstat()
        except FileNotFoundError:
            if not final or not allow_missing_final:
                raise OutcomeError("unsafe_carrier_path")
            continue
        if stat.S_ISLNK(info.st_mode):
            raise OutcomeError("unsafe_carrier_path")
        if final:
            if not stat.S_ISREG(info.st_mode) and not stat.S_ISDIR(info.st_mode):
                raise OutcomeError("unsafe_carrier_path")
        elif not stat.S_ISDIR(info.st_mode):
            raise OutcomeError("unsafe_carrier_path")
    return path


def build_paths(args: argparse.Namespace, *, require_execution: bool) -> Paths:
    root = _absolute(Path(args.project_root))
    _validate_components(root, root, allow_missing_final=False)
    plan_rel = _repo_rel(args.plan, PLAN_RE, "plan")
    plan = _validate_components(root, root / plan_rel, allow_missing_final=False)
    output_dir = _absolute(Path(args.output_dir))
    expected_output = root / ".tmp" / "planveyor_role_runs" / args.run_id
    if output_dir != _absolute(expected_output):
        raise OutcomeError("unsafe_carrier_path")
    _validate_components(root, output_dir, allow_missing_final=False)
    if not output_dir.is_dir():
        raise OutcomeError("unsafe_carrier_path")
    readback = _validate_components(
        root, output_dir / "role_outcome_readback.json", allow_missing_final=True
    )
    preflight = _validate_components(
        root, output_dir / "role_outcome_preflight.json", allow_missing_final=True
    )
    execution: Path | None = None
    if require_execution:
        if not args.execution_receipt:
            raise OutcomeError("execution_receipt_invalid")
        execution = _absolute(Path(args.execution_receipt))
        expected_execution = root / ".planveyor.role_runs" / f"{args.run_id}.json"
        if execution != _absolute(expected_execution):
            raise OutcomeError("execution_identity_mismatch")
        execution = _validate_components(root, execution, allow_missing_final=False)
    return Paths(root, plan_rel, plan, output_dir, readback, preflight, execution)


def build_lint_paths(args: argparse.Namespace) -> tuple[Path, str, Path]:
    root = _absolute(Path(args.project_root))
    _validate_components(root, root, allow_missing_final=False)
    plan_rel = _repo_rel(args.plan, PLAN_RE, "plan")
    plan = _validate_components(root, root / plan_rel, allow_missing_final=False)
    return root, plan_rel, plan


def lint_paths(args: argparse.Namespace) -> Paths:
    root, plan_rel, plan = build_lint_paths(args)
    return Paths(root, plan_rel, plan, root, root, root, None)


def _read_text(root: Path, path: Path, *, missing_ok: bool = False) -> str:
    try:
        _validate_components(root, path, allow_missing_final=missing_ok)
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        if missing_ok:
            return ""
        raise OutcomeError("carrier_resolution_failed")
    except (OSError, UnicodeError) as exc:
        raise OutcomeError("unsafe_carrier_path") from exc


def _section_bounds(text: str, heading: str) -> tuple[int, int] | None:
    lines = text.splitlines()
    try:
        start = lines.index(heading) + 1
    except ValueError:
        return None
    end = len(lines)
    for index in range(start, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return start, end


def _section(text: str, heading: str) -> list[str]:
    bounds = _section_bounds(text, heading)
    if bounds is None:
        return []
    start, end = bounds
    return text.splitlines()[start:end]


def _evidence_bounds(text: str) -> tuple[int, int]:
    lines = text.splitlines()
    matches = [
        index
        for index, line in enumerate(lines)
        if line in EVIDENCE_HEADINGS
    ]
    if len(matches) != 1:
        raise OutcomeError("carrier_resolution_failed")
    start = matches[0] + 1
    end = len(lines)
    for index in range(start, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return start, end


def is_active(plan_text: str) -> bool:
    return ACTIVE_MODE_ROW in _section(plan_text, "## Verification rerun / exec handoff")


def _live_review_rel(plan_text: str, *, required: bool) -> str | None:
    section_lines = _section(plan_text, "## Review artifacts")
    if not section_lines:
        raise OutcomeError("carrier_resolution_failed")
    section = "\n".join(section_lines)
    paths = sorted(set(REVIEW_RE.findall(section)))
    explicit_absence = any(
        re.search(r"(?:^|:\s*)`?N/A \(why=.+\)`?$", line.strip().removeprefix("- ").strip())
        for line in section_lines
    )
    if len(paths) > 1 or (paths and explicit_absence):
        raise OutcomeError("carrier_resolution_failed")
    if paths:
        return _repo_rel(paths[0], REVIEW_RE, "review")
    if required or not explicit_absence:
        raise OutcomeError("carrier_resolution_failed")
    return None


def resolve_placement(paths: Paths, role: str, plan_text: str) -> Placement:
    if role == "reviewer_code_contracts":
        review_rel = _live_review_rel(plan_text, required=True)
        assert review_rel is not None
        review = _validate_components(paths.root, paths.root / review_rel, allow_missing_final=True)
        return Placement(review_rel, review, review_rel, paths.plan_rel, paths.plan)
    review_rel = _live_review_rel(plan_text, required=False)
    review = (
        _validate_components(paths.root, paths.root / review_rel, allow_missing_final=True)
        if review_rel is not None
        else None
    )
    return Placement(
        paths.plan_rel,
        paths.plan,
        f"{paths.plan_rel}::## Evidence",
        review_rel,
        review,
    )


def _block_end(lines: list[str], start: int) -> int:
    end = start + 1
    while end < len(lines) and lines[end].startswith("  "):
        end += 1
    return end


def _semantic_diagnostics(
    lines: list[str],
    start: int,
) -> tuple[int, dict[str, list[str]], list[dict[str, Any]]]:
    end = _block_end(lines, start)
    cursor = start + 1
    values: dict[str, list[str]] = {}
    diagnostics_by_field: dict[str, list[dict[str, Any]]] = {
        field: [] for field in SEMANTIC_FIELDS
    }
    for field in SEMANTIC_FIELDS:
        field_diagnostics = diagnostics_by_field[field]
        observed_label: str | None = None
        row_match = (
            re.fullmatch(r"  - ([A-Za-z_][A-Za-z0-9_]*):", lines[cursor])
            if cursor < end
            else None
        )
        if row_match is None:
            field_diagnostics.append({"rule_code": "field_missing", "field": field})
            values[field] = []
            continue
        observed_label = row_match.group(1)
        if observed_label != field:
            rule_code = (
                "field_order_invalid"
                if observed_label in SEMANTIC_FIELDS
                else "unexpected_label"
            )
            field_diagnostics.append(
                {
                    "rule_code": rule_code,
                    "field": field,
                    "observed_label": observed_label,
                }
            )
        cursor += 1
        bullets: list[str] = []
        while cursor < end and lines[cursor].startswith("    - "):
            bullets.append(lines[cursor][6:])
            cursor += 1
        values[field] = bullets
        if not 1 <= len(bullets) <= 3:
            field_diagnostics.append(
                {"rule_code": "bullet_count_out_of_range", "field": field}
            )
        na_indices = [
            index for index, value in enumerate(bullets, start=1) if value.startswith("N/A")
        ]
        if na_indices and len(bullets) != 1:
            field_diagnostics.append(
                {
                    "rule_code": "na_must_be_single",
                    "field": field,
                    "bullet_index": na_indices[0],
                }
            )
        for bullet_index, value in enumerate(bullets, start=1):
            if value.startswith("N/A"):
                if re.fullmatch(r"N/A \(why=.+\)", value):
                    pass
                elif re.fullmatch(r"N/A \(why=.+\)[.,;:!?]+", value):
                    field_diagnostics.append(
                        {
                            "rule_code": "na_trailing_punctuation",
                            "field": field,
                            "bullet_index": bullet_index,
                        }
                    )
                else:
                    field_diagnostics.append(
                        {
                            "rule_code": "na_syntax_invalid",
                            "field": field,
                            "bullet_index": bullet_index,
                        }
                    )
            if not value.strip():
                field_diagnostics.append(
                    {
                        "rule_code": "bullet_empty",
                        "field": field,
                        "bullet_index": bullet_index,
                    }
                )
            if len(value) > 500:
                field_diagnostics.append(
                    {
                        "rule_code": "bullet_too_long",
                        "field": field,
                        "bullet_index": bullet_index,
                        "actual_chars": len(value),
                        "max_allowed": 500,
                    }
                )
            if "```" in value:
                field_diagnostics.append(
                    {
                        "rule_code": "forbidden_fence",
                        "field": field,
                        "bullet_index": bullet_index,
                    }
                )
            stripped = value.lstrip()
            if stripped.startswith("{") or stripped.startswith("["):
                field_diagnostics.append(
                    {
                        "rule_code": "forbidden_json",
                        "field": field,
                        "bullet_index": bullet_index,
                    }
                )
    extra_diagnostics: list[dict[str, Any]] = []
    while cursor < end:
        row_match = re.fullmatch(r"  - ([A-Za-z_][A-Za-z0-9_]*):", lines[cursor])
        observed = row_match.group(1) if row_match else "<unparseable>"
        extra_diagnostics.append(
            {"rule_code": "unexpected_label", "observed_label": observed}
        )
        cursor += 1
        while cursor < end and lines[cursor].startswith("    - "):
            cursor += 1

    rule_rank = {rule: index for index, rule in enumerate(DIAGNOSTIC_RULES)}
    diagnostics: list[dict[str, Any]] = []
    for field in SEMANTIC_FIELDS:
        diagnostics.extend(
            sorted(
                diagnostics_by_field[field],
                key=lambda item: (
                    0 if "bullet_index" not in item else 1,
                    item.get("bullet_index", 0),
                    rule_rank[item["rule_code"]],
                ),
            )
        )
    diagnostics.extend(extra_diagnostics)
    return end, values, diagnostics


def parse_semantic_block(lines: list[str], start: int) -> SemanticBlock:
    end, values, diagnostics = _semantic_diagnostics(lines, start)
    if diagnostics:
        raise OutcomeError("semantic_draft_invalid")
    return SemanticBlock(start, end, values)


def _validate_bullets(values: list[str]) -> None:
    if not 1 <= len(values) <= 3:
        raise OutcomeError("semantic_draft_invalid")
    if len(values) == 1 and values[0].startswith("N/A"):
        if not re.fullmatch(r"N/A \(why=.+\)", values[0]):
            raise OutcomeError("semantic_draft_invalid")
        return
    if any(value.startswith("N/A") for value in values):
        raise OutcomeError("semantic_draft_invalid")
    for value in values:
        if not value.strip() or len(value) > 500:
            raise OutcomeError("semantic_draft_invalid")
        stripped = value.lstrip()
        if "```" in value or stripped.startswith("{") or stripped.startswith("["):
            raise OutcomeError("semantic_draft_invalid")


def parse_receipt_block(lines: list[str], start: int) -> ReceiptBlock:
    end = _block_end(lines, start)
    cursor = start + 1
    envelope: dict[str, str] = {}
    for field in ENVELOPE_FIELDS:
        prefix = f"  - {field}: "
        if cursor >= end or not lines[cursor].startswith(prefix):
            raise OutcomeError("semantic_draft_invalid")
        value = lines[cursor][len(prefix) :]
        if not value:
            raise OutcomeError("semantic_draft_invalid")
        envelope[field] = value
        cursor += 1
    if not RFC3339_RE.fullmatch(envelope["written_at"]):
        raise OutcomeError("semantic_draft_invalid")
    values: dict[str, list[str]] = {}
    for field in SEMANTIC_FIELDS:
        if cursor >= end or lines[cursor] != f"  - {field}:":
            raise OutcomeError("semantic_draft_invalid")
        cursor += 1
        bullets: list[str] = []
        while cursor < end and lines[cursor].startswith("    - "):
            bullets.append(lines[cursor][6:])
            cursor += 1
        _validate_bullets(bullets)
        values[field] = bullets
    if cursor != end:
        raise OutcomeError("semantic_draft_invalid")
    return ReceiptBlock(start, end, envelope, values)


def _marker_indices(text: str, marker: str) -> list[int]:
    return [index for index, line in enumerate(text.splitlines()) if line == marker]


def _block_sha256(lines: list[str], start: int, end: int) -> str:
    raw = "\n".join(lines[start:end]).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _candidate_sha256(text: str, start: int) -> str:
    lines = text.splitlines()
    return _block_sha256(lines, start, _block_end(lines, start))


def parse_ordered_block(
    lines: list[str],
    start: int,
    marker: str,
    fields: tuple[str, ...],
) -> OrderedBlock:
    if start >= len(lines) or lines[start] != marker:
        raise OutcomeError("recovery_chain_invalid")
    end = _block_end(lines, start)
    cursor = start + 1
    values: dict[str, str] = {}
    for field in fields:
        prefix = f"  - {field}: "
        if cursor >= end or not lines[cursor].startswith(prefix):
            raise OutcomeError("recovery_chain_invalid")
        value = lines[cursor][len(prefix) :]
        if not value:
            raise OutcomeError("recovery_chain_invalid")
        values[field] = value
        cursor += 1
    if cursor != end:
        raise OutcomeError("recovery_chain_invalid")
    return OrderedBlock(start, end, values)


def _outcome_event_indices(text: str) -> list[tuple[int, str]]:
    markers = (DRAFT_MARKER, REJECTION_MARKER, RERUN_STARTED_MARKER, RECEIPT_MARKER)
    return sorted(
        (index, marker)
        for marker in markers
        for index in _marker_indices(text, marker)
    )


def _validated_rejection(
    text: str,
    lines: list[str],
    draft_index: int,
    rejection_index: int,
    target_plan: str,
    carrier_path: str,
) -> tuple[OrderedBlock, str, str, str]:
    rejection = parse_ordered_block(
        lines, rejection_index, REJECTION_MARKER, REJECTION_FIELDS
    )
    rejection_hash = _block_sha256(lines, rejection.start, rejection.end)
    draft_hash = _candidate_sha256(text, draft_index)
    _, _, draft_diagnostics = _semantic_diagnostics(lines, draft_index)
    declared_role = rejection.values["role"]
    declared_lane = ROLE_LANES.get(declared_role)
    role_owns_carrier = (
        carrier_path != target_plan
        if declared_role == "reviewer_code_contracts"
        else carrier_path == target_plan
    )
    if (
        rejection.values["schema_version"] != REJECTION_SCHEMA
        or declared_lane is None
        or rejection.values["lane"] != declared_lane
        or rejection.values["target_plan"] != target_plan
        or rejection.values["carrier_path"] != carrier_path
        or not role_owns_carrier
        or rejection.values["semantic_draft_sha256"] != draft_hash
        or not draft_diagnostics
        or rejection.values["reason_code"] != "semantic_draft_invalid"
        or rejection.values["recovery_state"] != "rerun_available"
        or rejection.values["rerun_budget"] != "1"
        or not RFC3339_RE.fullmatch(rejection.values["written_at"])
    ):
        raise OutcomeError("recovery_chain_invalid")
    return rejection, rejection_hash, declared_role, declared_lane


def _recovery_chains(
    text: str,
    target_plan: str,
    carrier_path: str,
) -> list[RecoveryChain]:
    lines = text.splitlines()
    events = _outcome_event_indices(text)
    chains: list[RecoveryChain] = []
    rerun_hashes: set[str] = set()
    for event_index, (index, marker) in enumerate(events):
        if marker != RERUN_STARTED_MARKER:
            continue
        if event_index < 2:
            raise OutcomeError("recovery_chain_invalid")
        rejection_index, rejection_marker = events[event_index - 1]
        draft_index, draft_marker = events[event_index - 2]
        if rejection_marker != REJECTION_MARKER or draft_marker != DRAFT_MARKER:
            raise OutcomeError("recovery_chain_invalid")
        rejection, rejection_hash, declared_role, declared_lane = (
            _validated_rejection(
                text,
                lines,
                draft_index,
                rejection_index,
                target_plan,
                carrier_path,
            )
        )
        rerun = parse_ordered_block(
            lines, index, RERUN_STARTED_MARKER, RERUN_STARTED_FIELDS
        )
        if (
            rerun.values["schema_version"] != RERUN_STARTED_SCHEMA
            or rerun.values["recovery_of_run_id"] != rejection.values["run_id"]
            or rerun.values["rejection_receipt_sha256"] != rejection_hash
            or rerun.values["role"] != declared_role
            or rerun.values["lane"] != declared_lane
            or rerun.values["target_plan"] != target_plan
            or rerun.values["carrier_path"] != carrier_path
            or not RFC3339_RE.fullmatch(rerun.values["started_at"])
            or rejection_hash in rerun_hashes
        ):
            raise OutcomeError("recovery_chain_invalid")
        rerun_hashes.add(rejection_hash)
        chains.append(
            RecoveryChain(
                draft_start=draft_index,
                rejection=rejection,
                rejection_sha256=rejection_hash,
                rerun=rerun,
            )
        )
    consumed_rejections = {chain.rejection.start for chain in chains}
    pending_rejections: list[OrderedBlock] = []
    for event_index, (index, marker) in enumerate(events):
        if marker != REJECTION_MARKER or index in consumed_rejections:
            continue
        if (
            event_index < 1
            or events[event_index - 1][1] != DRAFT_MARKER
            or event_index != len(events) - 1
        ):
            raise OutcomeError("recovery_chain_invalid")
        draft_index = events[event_index - 1][0]
        rejection, _, _, _ = _validated_rejection(
            text,
            lines,
            draft_index,
            index,
            target_plan,
            carrier_path,
        )
        pending_rejections.append(rejection)
    if len(pending_rejections) > 1:
        raise OutcomeError("recovery_chain_invalid")
    return chains


def _current_recovery_chain(
    text: str,
    role: str,
    target_plan: str,
    carrier_path: str,
    run_id: str,
) -> RecoveryChain | None:
    matches = [
        chain
        for chain in _recovery_chains(text, target_plan, carrier_path)
        if chain.rerun.values["role"] == role
        and chain.rerun.values["run_id"] == run_id
    ]
    if len(matches) > 1:
        raise OutcomeError("recovery_chain_invalid")
    return matches[0] if matches else None


def _current_receipts(text: str, run_id: str) -> list[ReceiptBlock]:
    lines = text.splitlines()
    current: list[ReceiptBlock] = []
    for index in _marker_indices(text, RECEIPT_MARKER):
        try:
            block = parse_receipt_block(lines, index)
        except OutcomeError:
            block_text = "\n".join(lines[index : _block_end(lines, index)])
            if f"  - run_id: {run_id}" in block_text:
                raise OutcomeError("current_outcome_duplicate")
            continue
        if block.envelope["run_id"] == run_id:
            current.append(block)
    return current


def _forbidden_hits(rel: str, text: str, run_id: str) -> list[str]:
    hits = [f"{rel}::{DRAFT_MARKER}" for _ in _marker_indices(text, DRAFT_MARKER)]
    hits.extend(f"{rel}::{RECEIPT_MARKER}" for _ in _current_receipts(text, run_id))
    return hits


def scan(
    paths: Paths,
    placement: Placement,
    run_id: str,
    role: str | None = None,
) -> dict[str, Any]:
    expected_text = _read_text(paths.root, placement.expected, missing_ok=True)
    forbidden_text = (
        _read_text(paths.root, placement.forbidden, missing_ok=True)
        if placement.forbidden is not None
        else ""
    )
    expected_drafts_all = _marker_indices(expected_text, DRAFT_MARKER)
    forbidden_drafts = _marker_indices(forbidden_text, DRAFT_MARKER)
    expected_receipts_all = _current_receipts(expected_text, run_id)
    forbidden_receipts = _current_receipts(forbidden_text, run_id)
    recovery_chain: RecoveryChain | None = None
    quarantined: set[int] = set()
    if role is not None:
        chains = _recovery_chains(expected_text, paths.plan_rel, placement.expected_rel)
        quarantined = {chain.draft_start for chain in chains}
        current_matches = [
            chain
            for chain in chains
            if chain.rerun.values["role"] == role
            and chain.rerun.values["run_id"] == run_id
        ]
        if len(current_matches) > 1:
            raise OutcomeError("recovery_chain_invalid")
        recovery_chain = current_matches[0] if current_matches else None
    live_expected_drafts_all = [
        index
        for index in expected_drafts_all
        if index not in quarantined
    ]
    if placement.artifact_ref.endswith("::## Evidence"):
        start, end = _evidence_bounds(expected_text)
        expected_drafts = [
            index for index in live_expected_drafts_all if start <= index < end
        ]
        expected_misplaced_drafts = [
            index for index in live_expected_drafts_all if not start <= index < end
        ]
        expected_receipts = [
            receipt for receipt in expected_receipts_all if start <= receipt.start < end
        ]
        expected_misplaced_receipts = [
            receipt for receipt in expected_receipts_all if not start <= receipt.start < end
        ]
    else:
        expected_drafts = live_expected_drafts_all
        expected_misplaced_drafts = []
        expected_receipts = expected_receipts_all
        expected_misplaced_receipts = []
    forbidden_hits = (
        _forbidden_hits(placement.forbidden_rel, forbidden_text, run_id)
        if placement.forbidden_rel is not None
        else []
    )
    forbidden_hits.extend(
        f"{placement.expected_rel}::outside ## Evidence::{DRAFT_MARKER}"
        for _ in expected_misplaced_drafts
    )
    forbidden_hits.extend(
        f"{placement.expected_rel}::outside ## Evidence::{RECEIPT_MARKER}"
        for _ in expected_misplaced_receipts
    )
    return {
        "expected_text": expected_text,
        "forbidden_text": forbidden_text,
        "expected_drafts": expected_drafts,
        "expected_misplaced_drafts": expected_misplaced_drafts,
        "forbidden_drafts": forbidden_drafts,
        "expected_receipts": expected_receipts,
        "expected_misplaced_receipts": expected_misplaced_receipts,
        "forbidden_receipts": forbidden_receipts,
        "semantic_draft_count": len(live_expected_drafts_all) + len(forbidden_drafts),
        "finalized_receipt_count": len(expected_receipts_all) + len(forbidden_receipts),
        "forbidden_carrier_hits": sorted(forbidden_hits),
        "recovery_chain": recovery_chain,
    }


def read_execution(paths: Paths, role: str, run_id: str, *, preflight_blocked: bool) -> dict[str, Any]:
    assert paths.execution_receipt is not None
    try:
        payload = json.loads(paths.execution_receipt.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OutcomeError("execution_receipt_invalid") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != EXECUTION_SCHEMA:
        raise OutcomeError("execution_receipt_invalid")
    required = {"run_id", "role", "target_plan", "state", "exit_code", "process_start_outcome"}
    if any(field not in payload for field in required):
        raise OutcomeError("execution_receipt_invalid")
    if (
        payload.get("run_id") != run_id
        or payload.get("role") != role
        or payload.get("target_plan") != paths.plan_rel
    ):
        raise OutcomeError("execution_identity_mismatch")
    receipt_value = payload.get("receipt_path")
    if receipt_value and _absolute(Path(str(receipt_value))) != paths.execution_receipt:
        raise OutcomeError("execution_identity_mismatch")
    if "authority_context" in payload:
        # This is historical entry evidence, not a request to re-attest today's
        # target checkout after the role has legitimately changed it.
        authority = _authority_module()
        parse_context_envelope = authority.parse_context_envelope
        ContractAuthorityError = authority.ContractAuthorityError

        try:
            raw_authority = payload["authority_context"]
            authority = parse_context_envelope(raw_authority if isinstance(raw_authority, str) else json.dumps(raw_authority))
        except (ContractAuthorityError, TypeError, ValueError) as exc:
            raise OutcomeError("execution_authority_context_invalid") from exc
        entry_observation = authority["entry_observation"]
        if not isinstance(entry_observation, dict) or entry_observation["root"] != str(paths.root.resolve()):
            raise OutcomeError("execution_authority_root_mismatch")
    if preflight_blocked and (
        payload.get("state") != "precondition_failed"
        or payload.get("process_start_outcome") != "not_started"
        or payload.get("exit_code") != 125
        or payload.get("non_green_reason") != "role_outcome_preflight_failed"
    ):
        raise OutcomeError("execution_identity_mismatch")
    return payload


def _readback_payload(
    paths: Paths,
    role: str,
    state: str,
    reason_code: str,
    *,
    execution_receipt_path: str,
    carrier_path: str | None,
    artifact_ref: str | None,
    semantic_draft_count: int,
    finalized_receipt_count: int,
    forbidden_carrier_hits: list[str],
    written_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": READBACK_SCHEMA,
        "state": state,
        "reason_code": reason_code,
        "run_id": paths.output_dir.name,
        "role": role,
        "lane": ROLE_LANES[role],
        "target_plan": paths.plan_rel,
        "execution_receipt_path": execution_receipt_path,
        "carrier_path": carrier_path,
        "artifact_ref": artifact_ref,
        "semantic_draft_count": semantic_draft_count,
        "finalized_receipt_count": finalized_receipt_count,
        "forbidden_carrier_hits": sorted(forbidden_carrier_hits),
        "written_at": written_at,
    }


def _direct(payload: dict[str, Any], *, persisted: bool) -> dict[str, Any]:
    result = dict(payload)
    result["role_outcome_readback_persisted"] = persisted
    return result


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def carrier_lock_path(paths: Paths, placement: Placement) -> Path:
    lock_root = paths.root / ".tmp" / "planveyor_role_outcome_locks"
    _validate_components(paths.root, lock_root.parent, allow_missing_final=False)
    try:
        lock_root.mkdir(mode=0o700)
    except FileExistsError:
        pass
    except OSError as exc:
        raise OutcomeError("unsafe_carrier_path") from exc
    _validate_components(paths.root, lock_root, allow_missing_final=False)
    digest = hashlib.sha256(placement.expected_rel.encode("utf-8")).hexdigest()
    return _validate_components(
        paths.root,
        lock_root / f"{digest}.lock",
        allow_missing_final=True,
    )


@contextmanager
def carrier_lock(paths: Paths, placement: Placement) -> Iterator[None]:
    lock_path = carrier_lock_path(paths, placement)
    flags = os.O_RDWR | os.O_CREAT
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    old_umask = os.umask(0o077)
    fd = -1
    try:
        try:
            fd = os.open(lock_path, flags, 0o600)
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise OutcomeError("unsafe_carrier_path")
            os.fchmod(fd, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX)
        except OutcomeError:
            raise
        except OSError as exc:
            raise OutcomeError("unsafe_carrier_path") from exc
        yield
    finally:
        if fd >= 0:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
        os.umask(old_umask)


def atomic_write(
    path: Path,
    data: bytes,
    *,
    expected_before: bytes | None = None,
    mode: int = 0o600,
) -> None:
    if expected_before is not None:
        try:
            current = path.read_bytes()
        except OSError as exc:
            raise CarrierChanged() from exc
        if current != expected_before:
            raise CarrierChanged()
    old_umask = os.umask(0o077)
    temp_name = ""
    try:
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=path.parent)
        with os.fdopen(fd, "wb") as handle:
            os.fchmod(handle.fileno(), mode)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if expected_before is not None and path.read_bytes() != expected_before:
            raise CarrierChanged()
        os.replace(temp_name, path)
        temp_name = ""
        _fsync_dir(path.parent)
    finally:
        os.umask(old_umask)
        if temp_name:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass


def atomic_create(path: Path, data: bytes, *, mode: int = 0o600) -> None:
    old_umask = os.umask(0o077)
    temp_name = ""
    try:
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=path.parent)
        with os.fdopen(fd, "wb") as handle:
            os.fchmod(handle.fileno(), mode)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temp_name, path, follow_symlinks=False)
        except FileExistsError as exc:
            raise OutcomeError("current_outcome_duplicate") from exc
        _fsync_dir(path.parent)
    finally:
        os.umask(old_umask)
        if temp_name:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass


def persist_readback(paths: Paths, payload: dict[str, Any]) -> None:
    data = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    atomic_create(paths.readback, data, mode=0o600)


def validate_readback(payload: Any, paths: Paths, role: str, plan_text: str) -> None:
    fields = {
        "schema_version",
        "state",
        "reason_code",
        "run_id",
        "role",
        "lane",
        "target_plan",
        "execution_receipt_path",
        "carrier_path",
        "artifact_ref",
        "semantic_draft_count",
        "finalized_receipt_count",
        "forbidden_carrier_hits",
        "written_at",
    }
    if not isinstance(payload, dict) or set(payload) != fields:
        raise OutcomeError("execution_receipt_invalid")
    if (
        payload["schema_version"] != READBACK_SCHEMA
        or payload["state"] not in PERSISTED_STATES
        or payload["run_id"] != paths.output_dir.name
        or payload["role"] != role
        or payload["lane"] != ROLE_LANES[role]
        or payload["target_plan"] != paths.plan_rel
        or payload["execution_receipt_path"] != f".planveyor.role_runs/{paths.output_dir.name}.json"
        or not RFC3339_RE.fullmatch(payload["written_at"])
    ):
        raise OutcomeError("execution_identity_mismatch")
    reason = payload["reason_code"]
    if reason not in SUCCESS_REASONS | (BLOCKED_REASONS - {"readback_write_failed"}):
        raise OutcomeError("execution_receipt_invalid")
    if payload["state"] == "finalized" and reason not in SUCCESS_REASONS:
        raise OutcomeError("execution_receipt_invalid")
    if payload["state"] == "blocked" and reason in SUCCESS_REASONS:
        raise OutcomeError("execution_receipt_invalid")
    if not isinstance(payload["semantic_draft_count"], int) or payload["semantic_draft_count"] < 0:
        raise OutcomeError("execution_receipt_invalid")
    if not isinstance(payload["finalized_receipt_count"], int) or payload["finalized_receipt_count"] < 0:
        raise OutcomeError("execution_receipt_invalid")
    hits = payload["forbidden_carrier_hits"]
    if not isinstance(hits, list) or hits != sorted(hits) or any(not isinstance(item, str) for item in hits):
        raise OutcomeError("execution_receipt_invalid")
    for field in ("carrier_path", "artifact_ref"):
        if payload[field] is not None and not isinstance(payload[field], str):
            raise OutcomeError("execution_receipt_invalid")
    placement = resolve_placement(paths, role, plan_text)
    if payload["carrier_path"] not in {None, placement.expected_rel}:
        raise OutcomeError("execution_identity_mismatch")
    if payload["artifact_ref"] not in {None, placement.artifact_ref}:
        raise OutcomeError("execution_identity_mismatch")
    if payload["state"] != "finalized":
        return
    if (
        payload["carrier_path"] != placement.expected_rel
        or payload["artifact_ref"] != placement.artifact_ref
        or payload["finalized_receipt_count"] != 1
        or payload["forbidden_carrier_hits"]
        or (
            payload["reason_code"] == "ok"
            and payload["semantic_draft_count"] != 1
        )
        or (
            payload["reason_code"] == "already_finalized"
            and payload["semantic_draft_count"] != 0
        )
    ):
        raise OutcomeError("execution_receipt_invalid")
    scanned = scan(paths, placement, paths.output_dir.name, role)
    if scanned["semantic_draft_count"]:
        raise OutcomeError("current_outcome_duplicate")
    if scanned["forbidden_receipts"] or scanned["expected_misplaced_receipts"]:
        raise OutcomeError("forbidden_carrier_present")
    if not scanned["expected_receipts"]:
        raise OutcomeError("carrier_resolution_failed")
    if len(scanned["expected_receipts"]) != 1:
        raise OutcomeError("current_outcome_duplicate")
    receipt = scanned["expected_receipts"][0]
    if (
        receipt.envelope["role"] != role
        or receipt.envelope["lane"] != ROLE_LANES[role]
        or receipt.envelope["run_id"] != paths.output_dir.name
        or receipt.envelope["target_plan"] != paths.plan_rel
        or receipt.envelope["artifact_ref"] != placement.artifact_ref
        or receipt.envelope["written_at"] != payload["written_at"]
    ):
        raise OutcomeError("execution_identity_mismatch")


def _ephemeral(paths: Paths, role: str, reason: str) -> dict[str, Any]:
    lane = ROLE_LANES.get(role)
    return {
        "schema_version": READBACK_SCHEMA,
        "state": "not_applicable",
        "reason_code": reason,
        "run_id": paths.output_dir.name,
        "role": role,
        "lane": lane,
        "target_plan": paths.plan_rel,
        "execution_receipt_path": None,
        "carrier_path": None,
        "artifact_ref": None,
        "semantic_draft_count": 0,
        "finalized_receipt_count": 0,
        "forbidden_carrier_hits": [],
        "written_at": utc_now(),
        "role_outcome_readback_persisted": False,
    }


def _lint_payload(
    paths: Paths,
    role: str,
    *,
    state: str,
    reason_code: str,
    carrier_path: str | None,
    artifact_ref: str | None,
    semantic_draft_count: int,
    semantic_draft_sha256: str | None,
    diagnostics: list[dict[str, Any]],
) -> dict[str, Any]:
    safe_action = {
        "valid": "continue_current_invocation",
        "invalid": "fix_current_draft",
        "blocked": "return_owner_architect",
    }[state]
    return {
        "schema_version": LINT_SCHEMA,
        "state": state,
        "reason_code": reason_code,
        "role": role,
        "lane": ROLE_LANES.get(role),
        "target_plan": paths.plan_rel,
        "carrier_path": carrier_path,
        "artifact_ref": artifact_ref,
        "semantic_draft_count": semantic_draft_count,
        "semantic_draft_sha256": semantic_draft_sha256,
        "diagnostics": diagnostics,
        "safe_action": safe_action,
    }


def lint_draft(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    paths = lint_paths(args)
    plan_text = _read_text(paths.root, paths.plan)
    if args.role not in ROLE_LANES:
        return _lint_payload(
            paths,
            args.role,
            state="blocked",
            reason_code="unsupported_role",
            carrier_path=None,
            artifact_ref=None,
            semantic_draft_count=0,
            semantic_draft_sha256=None,
            diagnostics=[],
        ), 126
    if not is_active(plan_text):
        return _lint_payload(
            paths,
            args.role,
            state="blocked",
            reason_code="mode_inactive",
            carrier_path=None,
            artifact_ref=None,
            semantic_draft_count=0,
            semantic_draft_sha256=None,
            diagnostics=[],
        ), 126
    try:
        placement = resolve_placement(paths, args.role, plan_text)
        scanned = scan(paths, placement, "", args.role)
        details = {
            "carrier_path": placement.expected_rel,
            "artifact_ref": placement.artifact_ref,
            "semantic_draft_count": scanned["semantic_draft_count"],
        }
        if (
            scanned["forbidden_drafts"] or scanned["expected_misplaced_drafts"]
        ) and not scanned["expected_drafts"]:
            reason = "wrong_placement"
        elif scanned["forbidden_drafts"] or scanned["expected_misplaced_drafts"]:
            reason = "forbidden_carrier_present"
        elif not scanned["expected_drafts"]:
            reason = "semantic_draft_missing"
        elif len(scanned["expected_drafts"]) != 1:
            reason = "semantic_draft_duplicate"
        else:
            lines = scanned["expected_text"].splitlines()
            start = scanned["expected_drafts"][0]
            end, _, diagnostics = _semantic_diagnostics(lines, start)
            digest = _block_sha256(lines, start, end)
            state = "invalid" if diagnostics else "valid"
            reason_code = "semantic_draft_invalid" if diagnostics else "ok"
            return _lint_payload(
                paths,
                args.role,
                state=state,
                reason_code=reason_code,
                semantic_draft_sha256=digest,
                diagnostics=diagnostics,
                **details,
            ), (125 if diagnostics else 0)
        return _lint_payload(
            paths,
            args.role,
            state="blocked",
            reason_code=reason,
            semantic_draft_sha256=None,
            diagnostics=[],
            **details,
        ), 126
    except OutcomeError as exc:
        return _lint_payload(
            paths,
            args.role,
            state="blocked",
            reason_code=exc.reason_code,
            carrier_path=exc.carrier_path,
            artifact_ref=exc.artifact_ref,
            semantic_draft_count=exc.semantic_draft_count,
            semantic_draft_sha256=None,
            diagnostics=[],
        ), 126


def _diagnostic_payload(
    paths: Paths,
    role: str,
    *,
    state: str,
    reason_code: str,
    carrier_path: str | None,
    semantic_draft_sha256: str | None,
    diagnostics: list[dict[str, Any]],
    recovery_available: bool,
) -> dict[str, Any]:
    return {
        "schema_version": DIAGNOSTIC_SCHEMA,
        "state": state,
        "reason_code": reason_code,
        "run_id": paths.output_dir.name,
        "role": role,
        "lane": ROLE_LANES[role],
        "target_plan": paths.plan_rel,
        "carrier_path": carrier_path,
        "semantic_draft_sha256": semantic_draft_sha256,
        "diagnostics": diagnostics,
        "recovery_state": "reject_required" if recovery_available else "unavailable",
        "safe_action": (
            "reject_then_explicit_same_role_rerun"
            if recovery_available
            else "return_owner_architect"
        ),
        "written_at": utc_now(),
    }


def persist_diagnostic(paths: Paths, payload: dict[str, Any]) -> None:
    path = _validate_components(
        paths.root,
        paths.output_dir / "role_outcome_semantic_diagnostic.json",
        allow_missing_final=True,
    )
    data = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    atomic_create(path, data, mode=0o600)


def preflight(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    paths = build_paths(args, require_execution=False)
    plan_text = _read_text(paths.root, paths.plan)
    if not is_active(plan_text):
        return _ephemeral(paths, args.role, "mode_inactive"), 0
    if args.role not in ROLE_LANES:
        return _ephemeral(paths, args.role, "unsupported_role"), 0
    try:
        placement = resolve_placement(paths, args.role, plan_text)
        scanned = scan(paths, placement, args.run_id, args.role)
        state = "ready"
        reason = "ok"
        if scanned["semantic_draft_count"]:
            state = "blocked"
            reason = "preexisting_semantic_draft"
        elif scanned["finalized_receipt_count"]:
            state = "blocked"
            reason = "current_outcome_duplicate"
        payload = {
            "schema_version": PREFLIGHT_SCHEMA,
            "state": state,
            "reason_code": reason,
            "run_id": args.run_id,
            "role": args.role,
            "lane": ROLE_LANES[args.role],
            "target_plan": paths.plan_rel,
            "carrier_path": placement.expected_rel,
            "artifact_ref": placement.artifact_ref,
            "forbidden_carrier_path": placement.forbidden_rel,
            "semantic_draft_count": scanned["semantic_draft_count"],
            "finalized_receipt_count": scanned["finalized_receipt_count"],
            "forbidden_carrier_hits": scanned["forbidden_carrier_hits"],
        }
    except OutcomeError as exc:
        payload = {
            "schema_version": PREFLIGHT_SCHEMA,
            "state": "blocked",
            "reason_code": exc.reason_code,
            "run_id": args.run_id,
            "role": args.role,
            "lane": ROLE_LANES[args.role],
            "target_plan": paths.plan_rel,
            "carrier_path": exc.carrier_path,
            "artifact_ref": exc.artifact_ref,
            "forbidden_carrier_path": None,
            "semantic_draft_count": exc.semantic_draft_count,
            "finalized_receipt_count": exc.finalized_receipt_count,
            "forbidden_carrier_hits": sorted(exc.forbidden_carrier_hits),
        }
    return payload, 0 if payload["state"] == "ready" else 125


def read_preflight(paths: Paths, args: argparse.Namespace) -> dict[str, Any]:
    expected = _absolute(Path(args.preflight_result))
    if expected != paths.preflight:
        raise OutcomeError("unsafe_carrier_path")
    _validate_components(paths.root, expected, allow_missing_final=False)
    try:
        payload = json.loads(expected.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OutcomeError("execution_receipt_invalid") from exc
    fields = {
        "schema_version",
        "state",
        "reason_code",
        "run_id",
        "role",
        "lane",
        "target_plan",
        "carrier_path",
        "artifact_ref",
        "forbidden_carrier_path",
        "semantic_draft_count",
        "finalized_receipt_count",
        "forbidden_carrier_hits",
    }
    if not isinstance(payload, dict) or set(payload) != fields:
        raise OutcomeError("execution_receipt_invalid")
    if (
        payload["schema_version"] != PREFLIGHT_SCHEMA
        or payload["state"] not in {"ready", "blocked"}
        or payload["run_id"] != args.run_id
        or payload["role"] != args.role
        or payload["lane"] != ROLE_LANES[args.role]
        or payload["target_plan"] != paths.plan_rel
    ):
        raise OutcomeError("execution_identity_mismatch")
    return payload


def _blocked_from_error(paths: Paths, role: str, exc: OutcomeError) -> dict[str, Any]:
    return _readback_payload(
        paths,
        role,
        "blocked",
        exc.reason_code,
        execution_receipt_path=f".planveyor.role_runs/{paths.output_dir.name}.json",
        carrier_path=exc.carrier_path,
        artifact_ref=exc.artifact_ref,
        semantic_draft_count=exc.semantic_draft_count,
        finalized_receipt_count=exc.finalized_receipt_count,
        forbidden_carrier_hits=exc.forbidden_carrier_hits,
        written_at=utc_now(),
    )


def _publish_or_direct_failure(paths: Paths, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    try:
        persist_readback(paths, payload)
    except OutcomeError as exc:
        failed = dict(payload)
        failed["state"] = "blocked"
        failed["reason_code"] = exc.reason_code
        return _direct(failed, persisted=False), 126
    except OSError:
        failed = dict(payload)
        failed["state"] = "blocked"
        failed["reason_code"] = "readback_write_failed"
        return _direct(failed, persisted=False), 126
    return _direct(payload, persisted=True), 0 if payload["state"] == "finalized" else 126


def _render_receipt(role: str, run_id: str, target_plan: str, artifact_ref: str, written_at: str, values: dict[str, list[str]]) -> list[str]:
    rows = [RECEIPT_MARKER]
    envelope = {
        "role": role,
        "lane": ROLE_LANES[role],
        "run_id": run_id,
        "target_plan": target_plan,
        "artifact_ref": artifact_ref,
        "written_at": written_at,
    }
    rows.extend(f"  - {field}: {envelope[field]}" for field in ENVELOPE_FIELDS)
    for field in SEMANTIC_FIELDS:
        rows.append(f"  - {field}:")
        rows.extend(f"    - {value}" for value in values[field])
    return rows


def _finalize_ready(
    paths: Paths,
    args: argparse.Namespace,
    preflight_payload: dict[str, Any],
    initial_plan_text: str,
) -> tuple[dict[str, Any], int]:
    initial_placement = resolve_placement(paths, args.role, initial_plan_text)
    with carrier_lock(paths, initial_placement):
        try:
            plan_text = _read_text(paths.root, paths.plan)
            placement = resolve_placement(paths, args.role, plan_text)
            if (
                placement.expected_rel != initial_placement.expected_rel
                or placement.expected_rel != preflight_payload["carrier_path"]
                or placement.artifact_ref != preflight_payload["artifact_ref"]
                or placement.forbidden_rel != preflight_payload["forbidden_carrier_path"]
            ):
                raise CarrierChanged()
            scanned = scan(paths, placement, args.run_id, args.role)
            details = {
                "carrier_path": placement.expected_rel,
                "artifact_ref": placement.artifact_ref,
                "semantic_draft_count": scanned["semantic_draft_count"],
                "finalized_receipt_count": scanned["finalized_receipt_count"],
                "forbidden_carrier_hits": scanned["forbidden_carrier_hits"],
            }
            if scanned["finalized_receipt_count"]:
                payload = _blocked_from_error(
                    paths,
                    args.role,
                    OutcomeError("current_outcome_duplicate", **details),
                )
                return _direct(payload, persisted=False), 126
            if (
                scanned["forbidden_drafts"] or scanned["expected_misplaced_drafts"]
            ) and not scanned["expected_drafts"]:
                raise OutcomeError("wrong_placement", **details)
            if scanned["forbidden_drafts"] or scanned["expected_misplaced_drafts"]:
                raise OutcomeError("forbidden_carrier_present", **details)
            if not scanned["expected_drafts"]:
                raise OutcomeError("semantic_draft_missing", **details)
            if len(scanned["expected_drafts"]) != 1:
                raise OutcomeError("semantic_draft_duplicate", **details)
            lines = scanned["expected_text"].splitlines()
            semantic_start = scanned["expected_drafts"][0]
            semantic_end, semantic_values, diagnostics = _semantic_diagnostics(
                lines, semantic_start
            )
            if diagnostics:
                diagnostic = _diagnostic_payload(
                    paths,
                    args.role,
                    state="invalid",
                    reason_code="semantic_draft_invalid",
                    carrier_path=placement.expected_rel,
                    semantic_draft_sha256=_block_sha256(
                        lines, semantic_start, semantic_end
                    ),
                    diagnostics=diagnostics,
                    recovery_available=scanned["recovery_chain"] is None,
                )
                persist_diagnostic(paths, diagnostic)
                raise OutcomeError("semantic_draft_invalid", **details)
            semantic = SemanticBlock(
                semantic_start,
                semantic_end,
                semantic_values,
            )
            written_at = utc_now()
            replacement = _render_receipt(
                args.role,
                args.run_id,
                paths.plan_rel,
                placement.artifact_ref,
                written_at,
                semantic.values,
            )
            new_lines = lines[: semantic.start] + replacement + lines[semantic.end :]
            suffix = "\n" if scanned["expected_text"].endswith("\n") else ""
            new_text = "\n".join(new_lines) + suffix
            try:
                mode = stat.S_IMODE(placement.expected.stat().st_mode)
                atomic_write(
                    placement.expected,
                    new_text.encode("utf-8"),
                    expected_before=scanned["expected_text"].encode("utf-8"),
                    mode=mode,
                )
            except CarrierChanged:
                raise OutcomeError("carrier_changed", **details)
            except OSError as exc:
                raise OutcomeError("carrier_write_failed", **details) from exc
            final_text = _read_text(paths.root, placement.expected)
            final_scanned = scan(paths, placement, args.run_id, args.role)
            final_receipts = final_scanned["expected_receipts"]
            if final_scanned["semantic_draft_count"] or len(final_receipts) != 1:
                raise OutcomeError("carrier_write_failed", **details)
            receipt = final_receipts[0]
            if (
                receipt.envelope["role"] != args.role
                or receipt.envelope["lane"] != ROLE_LANES[args.role]
                or receipt.envelope["target_plan"] != paths.plan_rel
                or receipt.envelope["artifact_ref"] != placement.artifact_ref
                or receipt.envelope["written_at"] != written_at
            ):
                raise OutcomeError("carrier_write_failed", **details)
            payload = _readback_payload(
                paths,
                args.role,
                "finalized",
                "ok",
                execution_receipt_path=f".planveyor.role_runs/{args.run_id}.json",
                carrier_path=placement.expected_rel,
                artifact_ref=placement.artifact_ref,
                semantic_draft_count=1,
                finalized_receipt_count=1,
                forbidden_carrier_hits=[],
                written_at=written_at,
            )
            return _publish_or_direct_failure(paths, payload)
        except OutcomeError as exc:
            diagnostic_path = paths.output_dir / "role_outcome_semantic_diagnostic.json"
            if (
                exc.reason_code
                in {
                    "semantic_draft_missing",
                    "semantic_draft_duplicate",
                    "wrong_placement",
                    "forbidden_carrier_present",
                    "recovery_chain_invalid",
                }
                and not diagnostic_path.exists()
            ):
                try:
                    persist_diagnostic(
                        paths,
                        _diagnostic_payload(
                            paths,
                            args.role,
                            state="blocked",
                            reason_code=exc.reason_code,
                            carrier_path=exc.carrier_path,
                            semantic_draft_sha256=None,
                            diagnostics=[],
                            recovery_available=False,
                        ),
                    )
                except (OutcomeError, OSError):
                    pass
            payload = _blocked_from_error(paths, args.role, exc)
            return _publish_or_direct_failure(paths, payload)


def finalize(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    paths = build_paths(args, require_execution=True)
    plan_text = _read_text(paths.root, paths.plan)
    if not is_active(plan_text):
        return _ephemeral(paths, args.role, "mode_inactive"), 0
    if args.role not in ROLE_LANES:
        return _ephemeral(paths, args.role, "unsupported_role"), 0
    try:
        preflight_payload = read_preflight(paths, args)
        blocked_preflight = preflight_payload["state"] == "blocked"
        read_execution(paths, args.role, args.run_id, preflight_blocked=blocked_preflight)
        if blocked_preflight:
            reason = preflight_payload["reason_code"]
            if reason not in BLOCKED_REASONS - {"readback_write_failed"}:
                raise OutcomeError("execution_receipt_invalid")
            payload = _readback_payload(
                paths,
                args.role,
                "blocked",
                reason,
                execution_receipt_path=f".planveyor.role_runs/{args.run_id}.json",
                carrier_path=preflight_payload["carrier_path"],
                artifact_ref=preflight_payload["artifact_ref"],
                semantic_draft_count=preflight_payload["semantic_draft_count"],
                finalized_receipt_count=preflight_payload["finalized_receipt_count"],
                forbidden_carrier_hits=preflight_payload["forbidden_carrier_hits"],
                written_at=utc_now(),
            )
            direct, _ = _publish_or_direct_failure(paths, payload)
            return direct, 125 if direct.get("role_outcome_readback_persisted") else 126
        return _finalize_ready(paths, args, preflight_payload, plan_text)
    except OutcomeError as exc:
        payload = _blocked_from_error(paths, args.role, exc)
        return _publish_or_direct_failure(paths, payload)


def readback(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    paths = build_paths(args, require_execution=True)
    plan_text = _read_text(paths.root, paths.plan)
    if not is_active(plan_text):
        return _ephemeral(paths, args.role, "mode_inactive"), 0
    if args.role not in ROLE_LANES:
        return _ephemeral(paths, args.role, "unsupported_role"), 0
    try:
        read_execution(paths, args.role, args.run_id, preflight_blocked=False)
        paths.readback.lstat()
        _validate_components(paths.root, paths.readback, allow_missing_final=False)
        payload = json.loads(paths.readback.read_text(encoding="utf-8"))
        validate_readback(payload, paths, args.role, plan_text)
    except FileNotFoundError:
        payload = _readback_payload(
            paths,
            args.role,
            "blocked",
            "readback_write_failed",
            execution_receipt_path=f".planveyor.role_runs/{args.run_id}.json",
            carrier_path=None,
            artifact_ref=None,
            semantic_draft_count=0,
            finalized_receipt_count=0,
            forbidden_carrier_hits=[],
            written_at=utc_now(),
        )
        return _direct(payload, persisted=False), 126
    except (OSError, UnicodeError, json.JSONDecodeError, OutcomeError) as exc:
        reason = exc.reason_code if isinstance(exc, OutcomeError) else "execution_receipt_invalid"
        payload = _readback_payload(
            paths,
            args.role,
            "blocked",
            reason,
            execution_receipt_path=f".planveyor.role_runs/{args.run_id}.json",
            carrier_path=None,
            artifact_ref=None,
            semantic_draft_count=0,
            finalized_receipt_count=0,
            forbidden_carrier_hits=[],
            written_at=utc_now(),
        )
        return _direct(payload, persisted=paths.readback.exists()), 126
    return _direct(payload, persisted=True), 0 if payload["state"] == "finalized" else 126


def recover_readback(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    paths = build_paths(args, require_execution=True)
    plan_text = _read_text(paths.root, paths.plan)
    if not is_active(plan_text):
        return _ephemeral(paths, args.role, "mode_inactive"), 0
    if args.role not in ROLE_LANES:
        return _ephemeral(paths, args.role, "unsupported_role"), 0
    if paths.readback.exists():
        return readback(args)
    try:
        read_execution(paths, args.role, args.run_id, preflight_blocked=False)
        placement = resolve_placement(paths, args.role, plan_text)
        scanned = scan(paths, placement, args.run_id, args.role)
        details = {
            "carrier_path": placement.expected_rel,
            "artifact_ref": placement.artifact_ref,
            "semantic_draft_count": scanned["semantic_draft_count"],
            "finalized_receipt_count": scanned["finalized_receipt_count"],
            "forbidden_carrier_hits": scanned["forbidden_carrier_hits"],
        }
        if scanned["semantic_draft_count"]:
            raise OutcomeError("current_outcome_duplicate", **details)
        if scanned["forbidden_receipts"] or scanned["expected_misplaced_receipts"]:
            raise OutcomeError("forbidden_carrier_present", **details)
        if len(scanned["expected_receipts"]) != 1:
            raise OutcomeError("current_outcome_duplicate", **details)
        receipt = scanned["expected_receipts"][0]
        if (
            receipt.envelope["role"] != args.role
            or receipt.envelope["lane"] != ROLE_LANES[args.role]
            or receipt.envelope["target_plan"] != paths.plan_rel
            or receipt.envelope["artifact_ref"] != placement.artifact_ref
        ):
            raise OutcomeError("execution_identity_mismatch", **details)
        payload = _readback_payload(
            paths,
            args.role,
            "finalized",
            "already_finalized",
            execution_receipt_path=f".planveyor.role_runs/{args.run_id}.json",
            carrier_path=placement.expected_rel,
            artifact_ref=placement.artifact_ref,
            semantic_draft_count=0,
            finalized_receipt_count=1,
            forbidden_carrier_hits=[],
            written_at=receipt.envelope["written_at"],
        )
        return _publish_or_direct_failure(paths, payload)
    except OutcomeError as exc:
        payload = _blocked_from_error(paths, args.role, exc)
        return _publish_or_direct_failure(paths, payload)


def _insert_after_block(text: str, end: int, rows: list[str]) -> str:
    pieces = text.splitlines(keepends=True)
    offset = sum(len(piece) for piece in pieces[:end])
    prefix = text[:offset]
    suffix = text[offset:]
    separator = "" if not prefix or prefix.endswith(("\n", "\r")) else "\n"
    insertion = separator + "\n".join(rows)
    if suffix:
        insertion += "" if insertion.endswith(("\n", "\r")) else "\n"
    elif text.endswith(("\n", "\r")):
        insertion += "\n"
    return prefix + insertion + suffix


def _read_json_object(path: Path, reason: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OutcomeError(reason) from exc
    if not isinstance(payload, dict):
        raise OutcomeError(reason)
    return payload


def _validated_diagnostic(
    paths: Paths,
    role: str,
    *,
    semantic_draft_sha256: str,
) -> dict[str, Any]:
    path = _validate_components(
        paths.root,
        paths.output_dir / "role_outcome_semantic_diagnostic.json",
        allow_missing_final=False,
    )
    payload = _read_json_object(path, "recovery_not_available")
    fields = {
        "schema_version",
        "state",
        "reason_code",
        "run_id",
        "role",
        "lane",
        "target_plan",
        "carrier_path",
        "semantic_draft_sha256",
        "diagnostics",
        "recovery_state",
        "safe_action",
        "written_at",
    }
    if (
        set(payload) != fields
        or payload["schema_version"] != DIAGNOSTIC_SCHEMA
        or payload["state"] != "invalid"
        or payload["reason_code"] != "semantic_draft_invalid"
        or payload["run_id"] != paths.output_dir.name
        or payload["role"] != role
        or payload["lane"] != ROLE_LANES[role]
        or payload["target_plan"] != paths.plan_rel
        or payload["semantic_draft_sha256"] != semantic_draft_sha256
        or not isinstance(payload["diagnostics"], list)
        or not payload["diagnostics"]
        or payload["recovery_state"] != "reject_required"
        or payload["safe_action"] != "reject_then_explicit_same_role_rerun"
        or not RFC3339_RE.fullmatch(payload["written_at"])
    ):
        raise OutcomeError("recovery_not_available")
    return payload


def _recovery_payload(
    paths: Paths,
    role: str,
    *,
    state: str,
    reason_code: str,
    carrier_path: str | None,
    semantic_draft_sha256: str | None,
    rejection_receipt_sha256: str | None,
    written_at: str,
    mutation_performed: bool,
) -> dict[str, Any]:
    ready = state == "ready"
    return {
        "schema_version": RECOVERY_SCHEMA,
        "state": state,
        "reason_code": reason_code,
        "run_id": paths.output_dir.name,
        "role": role,
        "lane": ROLE_LANES.get(role),
        "target_plan": paths.plan_rel,
        "carrier_path": carrier_path,
        "semantic_draft_sha256": semantic_draft_sha256,
        "rejection_receipt_sha256": rejection_receipt_sha256,
        "recovery_state": "rerun_available" if ready else "unavailable",
        "rerun_budget": 1 if ready else 0,
        "safe_action": (
            "dispatch_exact_same_role_rerun" if ready else "return_owner_architect"
        ),
        "written_at": written_at,
        "mutation_performed": mutation_performed,
    }


def reject_rerun(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    paths = build_paths(args, require_execution=True)
    written_at = utc_now()
    carrier_path: str | None = None
    semantic_hash: str | None = None
    try:
        plan_text = _read_text(paths.root, paths.plan)
        if not is_active(plan_text) or args.role not in ROLE_LANES:
            raise OutcomeError("recovery_not_available")
        read_execution(paths, args.role, args.run_id, preflight_blocked=False)
        persisted = _read_json_object(paths.readback, "recovery_not_available")
        validate_readback(persisted, paths, args.role, plan_text)
        if (
            persisted["state"] != "blocked"
            or persisted["reason_code"] != "semantic_draft_invalid"
        ):
            raise OutcomeError("recovery_not_available")
        placement = resolve_placement(paths, args.role, plan_text)
        carrier_path = placement.expected_rel
        with carrier_lock(paths, placement):
            current_plan_text = _read_text(paths.root, paths.plan)
            current_placement = resolve_placement(paths, args.role, current_plan_text)
            if current_placement != placement:
                raise OutcomeError("carrier_changed")
            scanned = scan(paths, placement, args.run_id, args.role)
            if (
                scanned["forbidden_drafts"]
                or scanned["expected_misplaced_drafts"]
                or len(scanned["expected_drafts"]) != 1
                or scanned["recovery_chain"] is not None
            ):
                raise OutcomeError("recovery_not_available")
            lines = scanned["expected_text"].splitlines()
            draft_start = scanned["expected_drafts"][0]
            draft_end, _, diagnostics = _semantic_diagnostics(lines, draft_start)
            if not diagnostics:
                raise OutcomeError("recovery_not_available")
            semantic_hash = _block_sha256(lines, draft_start, draft_end)
            diagnostic = _validated_diagnostic(
                paths,
                args.role,
                semantic_draft_sha256=semantic_hash,
            )
            if (
                diagnostic["carrier_path"] != placement.expected_rel
                or diagnostic["diagnostics"] != diagnostics
            ):
                raise OutcomeError("recovery_not_available")
            events = _outcome_event_indices(scanned["expected_text"])
            if not events or events[-1] != (draft_start, DRAFT_MARKER):
                raise OutcomeError("recovery_not_available")
            rows = [
                REJECTION_MARKER,
                f"  - schema_version: {REJECTION_SCHEMA}",
                f"  - run_id: {args.run_id}",
                f"  - role: {args.role}",
                f"  - lane: {ROLE_LANES[args.role]}",
                f"  - target_plan: {paths.plan_rel}",
                f"  - carrier_path: {placement.expected_rel}",
                f"  - semantic_draft_sha256: {semantic_hash}",
                "  - reason_code: semantic_draft_invalid",
                "  - recovery_state: rerun_available",
                "  - rerun_budget: 1",
                f"  - written_at: {written_at}",
            ]
            rejection_hash = _block_sha256(rows, 0, len(rows))
            existing_rejections = [
                parse_ordered_block(
                    lines,
                    index,
                    REJECTION_MARKER,
                    REJECTION_FIELDS,
                )
                for index in _marker_indices(
                    scanned["expected_text"], REJECTION_MARKER
                )
            ]
            if any(
                rejection.values["run_id"] == args.run_id
                for rejection in existing_rejections
            ):
                raise OutcomeError("recovery_not_available")
            existing_rejection_hashes = [
                _block_sha256(lines, rejection.start, rejection.end)
                for rejection in existing_rejections
            ]
            if rejection_hash in existing_rejection_hashes:
                raise OutcomeError("recovery_not_available")
            new_text = _insert_after_block(
                scanned["expected_text"], draft_end, rows
            )
            mode = stat.S_IMODE(placement.expected.stat().st_mode)
            atomic_write(
                placement.expected,
                new_text.encode("utf-8"),
                expected_before=scanned["expected_text"].encode("utf-8"),
                mode=mode,
            )
            final_text = _read_text(paths.root, placement.expected)
            final_lines = final_text.splitlines()
            matching_rejection_indices = [
                index
                for index in _marker_indices(final_text, REJECTION_MARKER)
                if _block_sha256(
                    final_lines,
                    index,
                    _block_end(final_lines, index),
                )
                == rejection_hash
            ]
            if len(matching_rejection_indices) != 1:
                raise OutcomeError("carrier_write_failed")
            rejection = parse_ordered_block(
                final_lines,
                matching_rejection_indices[0],
                REJECTION_MARKER,
                REJECTION_FIELDS,
            )
            if rejection.values["semantic_draft_sha256"] != semantic_hash:
                raise OutcomeError("carrier_write_failed")
        return _recovery_payload(
            paths,
            args.role,
            state="ready",
            reason_code="ok",
            carrier_path=carrier_path,
            semantic_draft_sha256=semantic_hash,
            rejection_receipt_sha256=rejection_hash,
            written_at=written_at,
            mutation_performed=True,
        ), 0
    except (OutcomeError, OSError) as exc:
        reason = exc.reason_code if isinstance(exc, OutcomeError) else "carrier_write_failed"
        return _recovery_payload(
            paths,
            args.role,
            state="blocked",
            reason_code=reason,
            carrier_path=carrier_path,
            semantic_draft_sha256=semantic_hash,
            rejection_receipt_sha256=None,
            written_at=written_at,
            mutation_performed=False,
        ), 126


def _reservation_payload(
    paths: Paths,
    args: argparse.Namespace,
    *,
    state: str,
    reason_code: str,
    carrier_path: str | None,
    written_at: str,
    mutation_performed: bool,
) -> dict[str, Any]:
    return {
        "schema_version": RESERVATION_SCHEMA,
        "state": state,
        "reason_code": reason_code,
        "run_id": args.run_id,
        "recovery_of_run_id": args.recovery_of_run_id,
        "rejection_receipt_sha256": args.rejection_receipt_sha256,
        "role": args.role,
        "lane": ROLE_LANES.get(args.role),
        "target_plan": paths.plan_rel,
        "carrier_path": carrier_path,
        "safe_action": (
            "continue_same_role_dispatch"
            if state == "started"
            else "return_owner_architect"
        ),
        "written_at": written_at,
        "mutation_performed": mutation_performed,
    }


def reserve_rerun(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    paths = build_paths(args, require_execution=False)
    written_at = utc_now()
    carrier_path: str | None = None
    try:
        plan_text = _read_text(paths.root, paths.plan)
        if (
            not is_active(plan_text)
            or args.role not in ROLE_LANES
            or args.run_id == args.recovery_of_run_id
            or not re.fullmatch(r"[0-9a-f]{64}", args.rejection_receipt_sha256)
        ):
            raise OutcomeError("recovery_not_available")
        placement = resolve_placement(paths, args.role, plan_text)
        carrier_path = placement.expected_rel
        with carrier_lock(paths, placement):
            current_plan_text = _read_text(paths.root, paths.plan)
            current_placement = resolve_placement(paths, args.role, current_plan_text)
            if current_placement != placement:
                raise OutcomeError("carrier_changed")
            text = _read_text(paths.root, placement.expected)
            lines = text.splitlines()
            events = _outcome_event_indices(text)
            _recovery_chains(
                text,
                paths.plan_rel,
                placement.expected_rel,
            )
            rejection_matches: list[OrderedBlock] = []
            for index in _marker_indices(text, REJECTION_MARKER):
                rejection = parse_ordered_block(
                    lines, index, REJECTION_MARKER, REJECTION_FIELDS
                )
                digest = _block_sha256(lines, rejection.start, rejection.end)
                if digest == args.rejection_receipt_sha256:
                    rejection_matches.append(rejection)
            if len(rejection_matches) != 1:
                raise OutcomeError("recovery_not_available")
            rejection = rejection_matches[0]
            event_position = events.index((rejection.start, REJECTION_MARKER))
            if (
                event_position < 1
                or events[event_position - 1][1] != DRAFT_MARKER
                or event_position != len(events) - 1
            ):
                raise OutcomeError("recovery_chain_invalid")
            draft_start = events[event_position - 1][0]
            (
                validated_rejection,
                validated_rejection_hash,
                declared_role,
                declared_lane,
            ) = _validated_rejection(
                text,
                lines,
                draft_start,
                rejection.start,
                paths.plan_rel,
                placement.expected_rel,
            )
            if (
                validated_rejection_hash != args.rejection_receipt_sha256
                or validated_rejection.values["run_id"]
                != args.recovery_of_run_id
                or declared_role != args.role
                or declared_lane != ROLE_LANES[args.role]
            ):
                raise OutcomeError("recovery_not_available")
            rows = [
                RERUN_STARTED_MARKER,
                f"  - schema_version: {RERUN_STARTED_SCHEMA}",
                f"  - run_id: {args.run_id}",
                f"  - recovery_of_run_id: {args.recovery_of_run_id}",
                f"  - rejection_receipt_sha256: {args.rejection_receipt_sha256}",
                f"  - role: {args.role}",
                f"  - lane: {ROLE_LANES[args.role]}",
                f"  - target_plan: {paths.plan_rel}",
                f"  - carrier_path: {placement.expected_rel}",
                f"  - started_at: {written_at}",
            ]
            new_text = _insert_after_block(text, rejection.end, rows)
            mode = stat.S_IMODE(placement.expected.stat().st_mode)
            atomic_write(
                placement.expected,
                new_text.encode("utf-8"),
                expected_before=text.encode("utf-8"),
                mode=mode,
            )
            final_text = _read_text(paths.root, placement.expected)
            chain = _current_recovery_chain(
                final_text,
                args.role,
                paths.plan_rel,
                placement.expected_rel,
                args.run_id,
            )
            if (
                chain is None
                or chain.rejection_sha256 != args.rejection_receipt_sha256
            ):
                raise OutcomeError("carrier_write_failed")
        return _reservation_payload(
            paths,
            args,
            state="started",
            reason_code="ok",
            carrier_path=carrier_path,
            written_at=written_at,
            mutation_performed=True,
        ), 0
    except (OutcomeError, OSError, ValueError) as exc:
        reason = exc.reason_code if isinstance(exc, OutcomeError) else "recovery_not_available"
        return _reservation_payload(
            paths,
            args,
            state="blocked",
            reason_code=reason,
            carrier_path=carrier_path,
            written_at=written_at,
            mutation_performed=False,
        ), 126


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="operation", required=True)
    lint = subparsers.add_parser("lint-draft")
    lint.add_argument("--project-root", required=True)
    lint.add_argument("--plan", required=True)
    lint.add_argument("--role", required=True)
    lint.add_argument("--format", choices=("json",), default="json")
    for operation in (
        "preflight",
        "finalize",
        "readback",
        "recover-readback",
        "reject-rerun",
        "reserve-rerun",
    ):
        child = subparsers.add_parser(operation)
        child.add_argument("--project-root", required=True)
        child.add_argument("--plan", required=True)
        child.add_argument("--role", required=True)
        child.add_argument("--run-id", required=True)
        child.add_argument("--output-dir", required=True)
        child.add_argument("--execution-receipt")
        child.add_argument("--preflight-result")
        if operation == "reserve-rerun":
            child.add_argument("--recovery-of-run-id", required=True)
            child.add_argument("--rejection-receipt-sha256", required=True)
        child.add_argument("--format", choices=("json",), default="json")
    return result


def _fallback(args: argparse.Namespace | None, reason: str) -> dict[str, Any]:
    role = getattr(args, "role", "") if args else ""
    run_id = getattr(args, "run_id", "") if args else ""
    plan = getattr(args, "plan", "") if args else ""
    operation = getattr(args, "operation", "") if args else ""
    if operation == "lint-draft":
        return {
            "schema_version": LINT_SCHEMA,
            "state": "blocked",
            "reason_code": reason,
            "role": role,
            "lane": ROLE_LANES.get(role),
            "target_plan": plan,
            "carrier_path": None,
            "artifact_ref": None,
            "semantic_draft_count": 0,
            "semantic_draft_sha256": None,
            "diagnostics": [],
            "safe_action": "return_owner_architect",
        }
    if operation == "reject-rerun":
        return {
            "schema_version": RECOVERY_SCHEMA,
            "state": "blocked",
            "reason_code": reason,
            "run_id": run_id,
            "role": role,
            "lane": ROLE_LANES.get(role),
            "target_plan": plan,
            "carrier_path": None,
            "semantic_draft_sha256": None,
            "rejection_receipt_sha256": None,
            "recovery_state": "unavailable",
            "rerun_budget": 0,
            "safe_action": "return_owner_architect",
            "written_at": utc_now(),
            "mutation_performed": False,
        }
    if operation == "reserve-rerun":
        return {
            "schema_version": RESERVATION_SCHEMA,
            "state": "blocked",
            "reason_code": reason,
            "run_id": run_id,
            "recovery_of_run_id": getattr(args, "recovery_of_run_id", ""),
            "rejection_receipt_sha256": getattr(
                args, "rejection_receipt_sha256", ""
            ),
            "role": role,
            "lane": ROLE_LANES.get(role),
            "target_plan": plan,
            "carrier_path": None,
            "safe_action": "return_owner_architect",
            "written_at": utc_now(),
            "mutation_performed": False,
        }
    return {
        "schema_version": READBACK_SCHEMA,
        "state": "blocked",
        "reason_code": reason,
        "run_id": run_id,
        "role": role,
        "lane": ROLE_LANES.get(role),
        "target_plan": plan,
        "execution_receipt_path": None,
        "carrier_path": None,
        "artifact_ref": None,
        "semantic_draft_count": 0,
        "finalized_receipt_count": 0,
        "forbidden_carrier_hits": [],
        "written_at": utc_now(),
        "role_outcome_readback_persisted": False,
    }


def main(argv: list[str] | None = None) -> int:
    args: argparse.Namespace | None = None
    try:
        args = parser().parse_args(argv)
        handlers: dict[str, Callable[[argparse.Namespace], tuple[dict[str, Any], int]]] = {
            "lint-draft": lint_draft,
            "preflight": preflight,
            "finalize": finalize,
            "readback": readback,
            "recover-readback": recover_readback,
            "reject-rerun": reject_rerun,
            "reserve-rerun": reserve_rerun,
        }
        payload, rc = handlers[args.operation](args)
    except OutcomeError as exc:
        payload = _fallback(args, exc.reason_code)
        if args and args.operation == "preflight" and exc.reason_code in BLOCKED_REASONS:
            rc = 125
        elif args and args.operation == "lint-draft":
            rc = 126
        else:
            rc = 126
    except Exception:
        payload = _fallback(args, "execution_receipt_invalid")
        rc = 126
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

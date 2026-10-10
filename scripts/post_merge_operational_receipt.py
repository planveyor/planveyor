#!/usr/bin/env python3
"""Write a structured post-merge operational receipt."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import re
import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from plan_harvest_lint import parse_plan_harvest_file_followups_receipt


_KNOWN_CONTENT_PROFILES = frozenset({"default", "planveyor", "target-local"})

class CommandPortabilityPolicyError(ValueError):
    """The requested public content profile is unsupported."""


@dataclass(frozen=True)
class CommandPortabilityRules:
    literal_rules: tuple[tuple[str, str], ...]
    miniforge_replacement: str


GENERIC_COMMAND_PORTABILITY_RULES = CommandPortabilityRules(
    literal_rules=(("/" + "opt/homebrew/bin/python3", "python3"),),
    miniforge_replacement="python3",
)


SCHEMA_VERSION = "post_merge_operational_receipt.v1"
ARCHIVE_SNAPSHOT_STATUSES = {"ok", "no_op", "blocked"}
ARCHIVE_SNAPSHOT_BACKENDS = {"git_text_export", "git_whole_sqlite", "s3_minio_sqlite"}
ARCHIVE_SNAPSHOT_FIELDS = (
    "status",
    "storage_backend",
    "manifest_path",
    "artifact_path",
    "object_uri",
    "checksum",
    "format_version",
    "access_status",
    "restore_status",
    "readback_status",
    "no_op_reason",
    "blocker_reason",
    "source",
    "export_command",
    "export_status",
    "snapshot_created_at_utc",
    "snapshot_source_db_sha256",
    "snapshot_source_docs_count",
)
S3_BACKENDS = {"s3_minio_sqlite"}
SECRETISH_KEYS = {
    "access_key",
    "access_key_id",
    "secret",
    "secret_access_key",
    "password",
    "token",
    "session_token",
}
DISALLOWED_NO_OP_REASONS = {
    "current_db_migration_failed",
    "helper_failed",
    "snapshot_failed",
    "restore_failed",
    "checksum_mismatch",
    "object_access_failed",
    "missing_manifest",
}
DOCS_INDEX_CONTEXT_NO_OP_REASONS = {
    "not_applicable_no_docs_or_followups_delta",
    "not_applicable_empty_docs_corpus",
    "not_applicable_bootstrap_index_unavailable",
}
DOCS_INDEX_CONTEXT_REQUIRED_INT_FIELDS = (
    "plans_total",
    "plans_covered",
    "plans_uncovered",
    "followups_total",
    "followups_covered",
    "followups_uncovered",
)
DOCS_INDEX_CONTEXT_CANON_STATES = {"advisory", "noisy", "covered", "empty", "not_checked", "skipped"}
RETRIEVAL_METRICS_REQUIRED_INT_FIELDS = (
    "query_total",
    "evaluated_total",
    "read_events_total",
)
RETRIEVAL_METRICS_REQUIRED_RATE_FIELDS = (
    "outcome_evaluated_rate",
    "read_open_rate",
)
RETRIEVAL_LOW_OUTCOME_RATE = 0.20
RETRIEVAL_LOW_READ_OPEN_RATE = 0.05
DOCS_HYGIENE_SUGGEST_TOP_CANDIDATES_LIMIT = 20
DOCS_HYGIENE_SUGGEST_GATE_COMMAND = "planveyor_post_merge_docs_hygiene_suggest_gate"
DOCS_HYGIENE_SUGGEST_CANONICAL_PREFIX = "planveyor_docs_hygiene_suggest --range "
FOLLOWUPS_TRIAGE_LAUNCH_MODES = {"file", "range"}
FOLLOWUPS_TRIAGE_FILE_REJECTED_NAMES = {
    "index.md",
    "_template_followups_backlog.md",
}
FOLLOWUPS_TRIAGE_LAUNCH_REQUIRED_INT_FIELDS = (
    "dry_run_append_new",
    "dry_run_merge_source",
    "dry_run_possible_duplicate",
    "dry_run_route_fallback",
    "apply_append_new",
    "apply_merge_source",
    "apply_possible_duplicate",
    "apply_route_fallback",
    "idempotency_append_new",
    "idempotency_merge_source",
    "idempotency_possible_duplicate",
    "idempotency_route_fallback",
)
FOLLOWUPS_TRIAGE_LAUNCH_RANGE_REQUIRED_INT_FIELDS = (
    "dry_run_unparsed_bullets",
    "apply_unparsed_bullets",
    "idempotency_unparsed_bullets",
)
FOLLOWUPS_TRIAGE_LAUNCH_CLOSURE_REF_FIELDS = (
    "manual_decision_ref",
    "already_tracked_ref",
)
FOLLOWUPS_LANE_RECONCILIATION_COUNT_FIELDS = (
    "range_append_new",
    "range_merge_source",
    "range_possible_duplicate",
    "range_route_fallback",
    "range_unparsed_bullets",
    "range_unresolved_append_new",
    "range_unresolved_possible_duplicate",
    "range_unresolved_route_fallback",
    "range_unresolved_unparsed_bullets",
)
FOLLOWUPS_TRIAGE_LAUNCH_REQUIRED_FIELDS = (
    "source_harvest_receipt_path",
    "triage_mode",
    "index_rebuild_status",
    "readback_status",
    "index_path",
    "process_improvements_lane",
)
PROCESS_IMPROVEMENTS_OPEN_SUMMARY_FIELD = "process_improvements_open_summary"
PROCESS_IMPROVEMENTS_OPEN_SUMMARY_SOURCE = "docs/process_improvements/promotion_surface.md"
PROCESS_IMPROVEMENTS_OPEN_SUMMARY_REQUIRED_KEYS = (
    "source",
    "lane",
    "ordinary_followups",
    "open",
    "triaged",
    "promoted",
    "null_execution",
    "owner_or_next_step",
)
PROCESS_IMPROVEMENTS_OPEN_SUMMARY_STATUSES = ("open", "triaged", "promoted")
PROCESS_IMPROVEMENT_DECISIONS_HEADING = "## Process-improvement promotion decisions"
PROCESS_IMPROVEMENT_FIELD_ASSIGNMENT_RE = re.compile(
    r"(?P<key>[A-Za-z][A-Za-z0-9_-]*)\s*(?:=|:)\s*(?:`(?P<backtick>[^`]*)`|(?P<bare>[^;|]+))",
    re.IGNORECASE,
)
REQUIRED_STEPS = (
    "docs_finalize",
    "doc_lint",
    "docs_hygiene_archive",
    "docs_hygiene_suggest",
    "docs_index_context",
    "retrieval_metrics",
    "followups_triage_launch",
    "canon_sweep",
    "planveyor_merge_bundle_report",
)
REQUIRED_STEP_FIELDS = (
    "step",
    "command",
    "artifact_path",
    "count_summary",
    "no_op_reason",
    "in_scope",
    "captured_at",
    "source",
)
STEP_RE = re.compile(r"^[a-z][a-z0-9_]*$")
SHA256_RE = re.compile(r"^(?:sha256:)?[a-f0-9]{64}$")
ENUM_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
DOCS_HYGIENE_RANGE_RE = re.compile(r"^\[planveyor\] Range:\s*(?P<range>.+?)\s*$", re.MULTILINE)
DOCS_HYGIENE_SECTION_COUNT_RE = re.compile(r"\((?P<count>[0-9]+)\):\s*$")
USER_PATH_PREFIX_RE = "/" + "Users" + r"/[^/\s'\"`]+"
USER_MINIFORGE_PYTHON_RE = re.compile(
    USER_PATH_PREFIX_RE + r"/miniforge3/envs/[^/\s'\"`]+/bin/python(?:3(?:\.\d+)?)?"
)


def load_command_portability_rules(
    *,
    content_profile_id: str = "default",
    policy_root: Path | None = None,
) -> CommandPortabilityRules:
    """Return generic public rules without reading ``policy_root``.

    The parameter remains an API compatibility seam. Explicit caller-owned
    command mappings use CommandPortabilityRules through rules=.
    """
    profile = content_profile_id.strip()
    if profile not in _KNOWN_CONTENT_PROFILES:
        raise CommandPortabilityPolicyError(f"unsupported content_profile_id: {content_profile_id!r}")
    return GENERIC_COMMAND_PORTABILITY_RULES


def _portabilize_command(
    value: str,
    *,
    rules: CommandPortabilityRules = GENERIC_COMMAND_PORTABILITY_RULES,
) -> str:
    command = value.strip()
    if not command or _is_na_value(command):
        return command
    command = USER_MINIFORGE_PYTHON_RE.sub(rules.miniforge_replacement, command)
    for old, new in rules.literal_rules:
        command = command.replace(old, new)
    return command


def _read_range_value(path: Path) -> str:
    if not path.is_file():
        raise ValueError(f"missing {path}")
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line
    raise ValueError(f"empty {path}")


def _sha7(value: str) -> str:
    return value[:7]


def _default_output_path(root: Path, base: str, head: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%y%m%d_%H%M")
    return (
        root
        / "docs"
        / "reviews"
        / f"{stamp}_post_merge_operational_receipt_range_{_sha7(base)}_{_sha7(head)}.md"
    )


def _load_record_json(raw: str) -> dict[str, Any]:
    try:
        record = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid --record-json: {exc}") from exc
    if not isinstance(record, dict):
        raise ValueError("--record-json must decode to an object")
    return record


def _manifest_has_secretish_keys(value: object) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in SECRETISH_KEYS:
                return True
            if _manifest_has_secretish_keys(child):
                return True
        return False
    if isinstance(value, list):
        return any(_manifest_has_secretish_keys(child) for child in value)
    return False


def _object_uri_has_inline_secret(uri: str) -> bool:
    lowered = uri.lower()
    if not uri:
        return False
    if "://" in uri:
        authority = uri.split("://", 1)[1].split("/", 1)[0]
        if "@" in authority:
            return True
    secret_query_tokens = (
        "x-amz-signature=",
        "x-amz-credential=",
        "x-amz-security-token=",
        "awsaccesskeyid=",
        "signature=",
        "token=",
    )
    return any(token in lowered for token in secret_query_tokens)


def _field_string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _is_meaningful_value(value: str) -> bool:
    if not value:
        return False
    lowered = value.strip().lower()
    if lowered in {"n/a", "na", "none", "-", "tbd", "unconfirmed"}:
        return False
    if lowered.startswith(("n/a ", "n/a(", "n/a (", "na ", "na(", "na (")):
        return False
    return True


def _is_durable_followups_triage_ref(value: str) -> bool:
    if not _is_meaningful_value(value):
        return False
    token = value.strip().strip("`").split()[0].strip("`.,;()[]<>")
    path_text = token.split("#", 1)[0]
    if ":" in path_text:
        maybe_path, maybe_line = path_text.rsplit(":", 1)
        if maybe_line.isdigit():
            path_text = maybe_path
    path = Path(path_text)
    return path_text.startswith("docs/") and path.suffix == ".md" and not path.is_absolute() and ".." not in path.parts


def _followups_triage_launch_closure_refs(summary: dict[str, str]) -> dict[str, str]:
    return {
        field: summary.get(field, "").strip()
        for field in FOLLOWUPS_TRIAGE_LAUNCH_CLOSURE_REF_FIELDS
        if _is_meaningful_value(summary.get(field, "").strip())
    }


def _validate_followups_triage_launch_closure_refs(summary: dict[str, str], *, step: str) -> dict[str, str]:
    refs = _followups_triage_launch_closure_refs(summary)
    for field, value in refs.items():
        if not _is_durable_followups_triage_ref(value):
            raise ValueError(f"{step}: count_summary.{field} must be a durable docs/*.md ref")
    return refs


def _is_na_value(value: str) -> bool:
    lowered = value.strip().lower()
    return lowered in {"n/a", "na"} or lowered.startswith(
        ("n/a ", "n/a(", "n/a (", "na ", "na(", "na (")
    )


def _parse_count_summary(value: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in re.split(r"[;,]", value):
        part = part.strip()
        if not part or "=" not in part:
            continue
        key, raw = part.split("=", 1)
        key = key.strip().lower()
        if not key:
            continue
        out[key] = raw.strip()
    return out


def _strip_summary_value(raw: str) -> str:
    return raw.strip().strip("`").strip()


def _is_valid_followups_triage_file_target(value: str) -> bool:
    raw = value.strip()
    path = Path(raw)
    if not raw or path.is_absolute() or ".." in path.parts:
        return False
    if path.suffix != ".md":
        return False
    if len(path.parts) < 3 or path.parts[0] != "docs" or path.parts[1] != "followups":
        return False
    if path.name in FOLLOWUPS_TRIAGE_FILE_REJECTED_NAMES:
        return False
    if path.name.endswith("_master.md"):
        return False
    return True


def _option_value(tokens: list[str], option: str) -> str | None:
    for index, token in enumerate(tokens):
        if token == option:
            if index + 1 >= len(tokens):
                return ""
            return tokens[index + 1]
        if token.startswith(f"{option}="):
            return token.split("=", 1)[1]
    return None


def _followups_triage_specs(command: str) -> list[dict[str, str]]:
    specs: list[dict[str, str]] = []
    for raw_segment in re.split(r"\s*(?:;|&&|\|\|)\s*", command):
        segment = raw_segment.strip()
        if "planveyor_followups_triage" not in segment:
            continue
        try:
            tokens = shlex.split(segment)
        except ValueError as exc:
            raise ValueError(f"command is not shell-parseable: {exc}") from exc
        if "planveyor_followups_triage" not in tokens:
            continue
        index = tokens.index("planveyor_followups_triage")
        args = tokens[index + 1 :]
        file_target = _option_value(args, "--file")
        range_target = _option_value(args, "--range")
        if file_target is not None and range_target is not None:
            raise ValueError("planveyor_followups_triage command must not mix --file and --range")
        if file_target is None and range_target is None:
            raise ValueError("planveyor_followups_triage command must include --file or --range")
        if file_target is not None:
            specs.append({"mode": "file", "target": file_target})
        else:
            specs.append({"mode": "range", "target": range_target or ""})
    return specs


def validate_followups_triage_command_surface(
    command: str,
    *,
    triage_mode: str,
    expected_range: str | None = None,
) -> None:
    """Validate recorded planveyor_followups_triage commands structurally."""
    mode = triage_mode.strip().lower()
    if mode not in FOLLOWUPS_TRIAGE_LAUNCH_MODES:
        allowed = "|".join(sorted(FOLLOWUPS_TRIAGE_LAUNCH_MODES))
        raise ValueError(f"triage_mode must be one of {allowed}")
    specs = _followups_triage_specs(command)
    if not specs:
        raise ValueError("command must include planveyor_followups_triage --file or --range")
    for spec in specs:
        spec_mode = spec["mode"]
        target = spec["target"].strip()
        if spec_mode != mode:
            raise ValueError(f"command mode {spec_mode} does not match triage_mode={mode}")
        if spec_mode == "file":
            if not _is_valid_followups_triage_file_target(target):
                raise ValueError(
                    "command --file target must be a repo-relative docs/followups/*.md inbox "
                    f"path, got {target or 'missing'}"
                )
        elif not target:
            raise ValueError("command --range target is required")
        elif expected_range is not None and target != expected_range:
            raise ValueError(f"command --range target {target} does not match receipt range {expected_range}")


def _parse_semicolon_summary(value: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in value.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        key, raw = part.split("=", 1)
        key = key.strip().lower()
        if key:
            out[key] = _strip_summary_value(raw)
    return out


def _summary_int(summary: dict[str, str], key: str, *, step: str) -> int:
    raw = summary.get(key, "")
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{step}: count_summary.{key} must be an integer") from exc
    if value < 0:
        raise ValueError(f"{step}: count_summary.{key} must be >= 0")
    return value


def _summary_rate(summary: dict[str, str], key: str, *, step: str) -> float:
    raw = summary.get(key, "")
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{step}: count_summary.{key} must be a decimal rate") from exc
    if value < 0.0 or value > 1.0:
        raise ValueError(f"{step}: count_summary.{key} must be between 0 and 1")
    return value


def _validate_docs_index_context_record(out: dict[str, Any]) -> None:
    step = str(out["step"])
    no_op_reason = str(out["no_op_reason"])
    if out["in_scope"] == "no":
        if no_op_reason not in DOCS_INDEX_CONTEXT_NO_OP_REASONS:
            allowed = "|".join(sorted(DOCS_INDEX_CONTEXT_NO_OP_REASONS))
            raise ValueError(f"{step}: no_op_reason must be one of {allowed}")
        return

    summary = _parse_count_summary(str(out["count_summary"]))
    missing = [field for field in DOCS_INDEX_CONTEXT_REQUIRED_INT_FIELDS if field not in summary]
    if "canon_state" not in summary:
        missing.append("canon_state")
    if missing:
        raise ValueError(f"{step}: count_summary missing field(s): {', '.join(missing)}")

    for corpus in ("plans", "followups"):
        total = _summary_int(summary, f"{corpus}_total", step=step)
        covered = _summary_int(summary, f"{corpus}_covered", step=step)
        uncovered = _summary_int(summary, f"{corpus}_uncovered", step=step)
        if total != covered + uncovered:
            raise ValueError(f"{step}: {corpus}_total must equal {corpus}_covered + {corpus}_uncovered")
        if uncovered != 0:
            raise ValueError(f"{step}: {corpus}_uncovered must be 0")
        state = summary.get(f"{corpus}_state", "").strip().lower()
        if total == 0:
            reason = summary.get(f"{corpus}_reason", "").strip()
            if state != "empty" or not _is_meaningful_value(reason):
                raise ValueError(f"{step}: empty {corpus} corpus requires {corpus}_state=empty and {corpus}_reason")
        elif state and state != "covered":
            raise ValueError(f"{step}: non-empty {corpus} corpus requires {corpus}_state=covered when present")

    canon_state = summary.get("canon_state", "").strip().lower()
    if canon_state not in DOCS_INDEX_CONTEXT_CANON_STATES:
        allowed = "|".join(sorted(DOCS_INDEX_CONTEXT_CANON_STATES))
        raise ValueError(f"{step}: count_summary.canon_state must be one of {allowed}")


def _validate_retrieval_metrics_record(out: dict[str, Any]) -> None:
    step = str(out["step"])
    no_op_reason = str(out["no_op_reason"])
    if out["in_scope"] == "no":
        if not ENUM_RE.fullmatch(no_op_reason):
            raise ValueError(f"{step}: skipped/out-of-scope row requires enum-like no_op_reason")
        return

    summary = _parse_count_summary(str(out["count_summary"]))
    missing = [field for field in RETRIEVAL_METRICS_REQUIRED_INT_FIELDS if field not in summary]
    missing.extend(field for field in RETRIEVAL_METRICS_REQUIRED_RATE_FIELDS if field not in summary)
    if "read_log_status" not in summary:
        missing.append("read_log_status")
    if "used_for_decision" not in summary:
        missing.append("used_for_decision")
    if missing:
        raise ValueError(f"{step}: count_summary missing field(s): {', '.join(missing)}")

    query_total = _summary_int(summary, "query_total", step=step)
    evaluated_total = _summary_int(summary, "evaluated_total", step=step)
    read_events_total = _summary_int(summary, "read_events_total", step=step)
    if evaluated_total > query_total:
        raise ValueError(f"{step}: evaluated_total cannot exceed query_total")
    outcome_rate = _summary_rate(summary, "outcome_evaluated_rate", step=step)
    read_open_rate = _summary_rate(summary, "read_open_rate", step=step)
    if not _is_meaningful_value(summary.get("read_log_status", "")):
        raise ValueError(f"{step}: count_summary.read_log_status is required")
    used_for_decision = summary["used_for_decision"].strip().lower()
    if used_for_decision not in {"true", "false"}:
        raise ValueError(f"{step}: count_summary.used_for_decision must be true or false")
    accepted_no_op_reason = summary.get("accepted_no_op_reason", "").strip()
    if used_for_decision == "false":
        if accepted_no_op_reason != "not_used_for_decision":
            raise ValueError(f"{step}: used_for_decision=false requires accepted_no_op_reason=not_used_for_decision")
        return
    if accepted_no_op_reason == "not_used_for_decision":
        raise ValueError(f"{step}: accepted_no_op_reason=not_used_for_decision is invalid when used_for_decision=true")

    low_coverage = query_total > 0 and (
        outcome_rate < RETRIEVAL_LOW_OUTCOME_RATE or read_open_rate < RETRIEVAL_LOW_READ_OPEN_RATE
    )
    if not low_coverage:
        return

    follow_up_ref = summary.get("follow_up_ref", "")
    if _is_meaningful_value(follow_up_ref):
        return
    if ENUM_RE.fullmatch(accepted_no_op_reason):
        return
    raise ValueError(f"{step}: low coverage requires follow_up_ref or accepted_no_op_reason")


def _validate_followups_triage_launch_record(out: dict[str, Any]) -> None:
    step = str(out["step"])
    if out["in_scope"] != "yes":
        raise ValueError(f"{step}: launch receipt row must be in_scope=yes")

    command = str(out["command"])
    if "followups_index_rebuild.py" not in command:
        raise ValueError(f"{step}: command must include scripts/followups_index_rebuild.py")

    summary = _parse_count_summary(str(out["count_summary"]))
    missing = [field for field in FOLLOWUPS_TRIAGE_LAUNCH_REQUIRED_FIELDS if field not in summary]
    missing.extend(field for field in FOLLOWUPS_TRIAGE_LAUNCH_REQUIRED_INT_FIELDS if field not in summary)
    if missing:
        raise ValueError(f"{step}: count_summary missing field(s): {', '.join(missing)}")

    triage_mode = summary["triage_mode"].strip().lower()
    if triage_mode not in FOLLOWUPS_TRIAGE_LAUNCH_MODES:
        allowed = "|".join(sorted(FOLLOWUPS_TRIAGE_LAUNCH_MODES))
        raise ValueError(f"{step}: count_summary.triage_mode must be one of {allowed}")
    if triage_mode == "range":
        missing = [field for field in FOLLOWUPS_TRIAGE_LAUNCH_RANGE_REQUIRED_INT_FIELDS if field not in summary]
        if missing:
            raise ValueError(f"{step}: count_summary missing field(s): {', '.join(missing)}")
    try:
        validate_followups_triage_command_surface(command, triage_mode=triage_mode)
    except ValueError as exc:
        raise ValueError(f"{step}: {exc}") from exc
    int_fields = FOLLOWUPS_TRIAGE_LAUNCH_REQUIRED_INT_FIELDS
    if triage_mode == "range":
        int_fields = int_fields + FOLLOWUPS_TRIAGE_LAUNCH_RANGE_REQUIRED_INT_FIELDS
    for field in int_fields:
        _summary_int(summary, field, step=step)
    if summary["index_rebuild_status"].strip().lower() != "ok":
        raise ValueError(f"{step}: count_summary.index_rebuild_status must be ok")
    if summary["readback_status"].strip().lower() != "ok":
        raise ValueError(f"{step}: count_summary.readback_status must be ok")
    if summary["process_improvements_lane"].strip().lower() != "separate":
        raise ValueError(f"{step}: count_summary.process_improvements_lane must be separate")
    closure_refs = _validate_followups_triage_launch_closure_refs(summary, step=step)
    final_zero_fields = ("idempotency_append_new", "idempotency_possible_duplicate", "idempotency_route_fallback")
    if triage_mode == "range":
        final_zero_fields = final_zero_fields + ("idempotency_unparsed_bullets",)
    for field in final_zero_fields:
        if _summary_int(summary, field, step=step) != 0 and not closure_refs:
            raise ValueError(
                f"{step}: count_summary.{field} must be 0 at final proof unless manual_decision_ref or "
                "already_tracked_ref is set"
            )
    source_path = summary["source_harvest_receipt_path"].strip()
    if not _is_meaningful_value(source_path):
        raise ValueError(f"{step}: count_summary.source_harvest_receipt_path is required")
    if out["artifact_path"] != source_path:
        raise ValueError(f"{step}: artifact_path must match count_summary.source_harvest_receipt_path")


def _require_repo_relative_file(root: Path, value: str, *, label: str, field: str) -> Path:
    raw = value.strip()
    if not _is_meaningful_value(raw):
        raise ValueError(f"{label}: {field} must be a repo-relative path")
    path = Path(raw)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{label}: {field} must be a repo-relative path")
    resolved = root / path
    if not resolved.is_file():
        raise ValueError(f"{label}: {field} missing on disk: {raw}")
    return resolved


def _followups_triage_phase(summary: dict[str, str], prefix: str) -> dict[str, int]:
    phase = {
        "append_new": int(summary[f"{prefix}_append_new"]),
        "merge_source": int(summary[f"{prefix}_merge_source"]),
        "possible_duplicate": int(summary[f"{prefix}_possible_duplicate"]),
        "route_fallback": int(summary[f"{prefix}_route_fallback"]),
    }
    unparsed_key = f"{prefix}_unparsed_bullets"
    if unparsed_key in summary:
        phase["unparsed_bullets"] = int(summary[unparsed_key])
    return phase


def _legacy_harvest_file_followups_result(source_text: str) -> tuple[str, int]:
    result_match = re.search(r"Result:\s*`(?P<value>[^`]+)`", source_text, flags=re.IGNORECASE)
    result = result_match.group("value").strip() if result_match else ""
    if not result and re.search(r"\bNO FOLLOWUPS\b", source_text, flags=re.IGNORECASE):
        result = "NO FOLLOWUPS"
    if not result:
        result = "UNCONFIRMED"

    return result, 0 if result.upper() == "NO FOLLOWUPS" else 1


def _harvest_file_followups_result(source_text: str, *, rel_path: str) -> tuple[str, int]:
    parsed = parse_plan_harvest_file_followups_receipt(source_text, rel_path=rel_path)
    if parsed.schema_class == "legacy":
        return _legacy_harvest_file_followups_result(source_text)
    if parsed.schema_class != "current" or parsed.findings:
        details = "; ".join(f"{finding.code}: {finding.message}" for finding in parsed.findings)
        if not details:
            details = f"unsupported schema class {parsed.schema_class!r}"
        raise ValueError(f"followups_lane_reconciliation: invalid current source harvest receipt: {details}")
    assert parsed.result is not None and parsed.count is not None
    return parsed.result, parsed.count


def _followups_reconciliation_count(value: dict[str, int], field: str) -> int:
    raw = value.get(field, 0)
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
        raise ValueError(f"followups_lane_reconciliation.{field} must be a non-negative integer")
    return raw


def _build_followups_lane_reconciliation(root: Path, receipt: dict[str, Any]) -> dict[str, Any]:
    source_path = str(receipt.get("source_harvest_receipt_path", "")).strip()
    source_file = _require_repo_relative_file(
        root,
        source_path,
        label="followups_lane_reconciliation",
        field="source_harvest_receipt_path",
    )
    source_text = source_file.read_text(encoding="utf-8", errors="replace")
    harvest_result, harvest_count = _harvest_file_followups_result(source_text, rel_path=source_path)
    triage_mode = str(receipt.get("triage_mode", "")).strip().lower()
    apply_counts = receipt.get("apply")
    idempotency_counts = receipt.get("idempotency_apply")
    if not isinstance(apply_counts, dict):
        raise ValueError("followups_lane_reconciliation: followups_triage_launch_receipt.apply must be an object")
    if not isinstance(idempotency_counts, dict):
        raise ValueError("followups_lane_reconciliation: followups_triage_launch_receipt.idempotency_apply must be an object")

    reconciliation = {
        "source_harvest_receipt_path": source_path,
        "harvest_file_followups_result": harvest_result,
        "harvest_file_followups_count": harvest_count,
        "range_triage_mode": triage_mode,
        "range_append_new": _followups_reconciliation_count(apply_counts, "append_new"),
        "range_merge_source": _followups_reconciliation_count(apply_counts, "merge_source"),
        "range_possible_duplicate": _followups_reconciliation_count(apply_counts, "possible_duplicate"),
        "range_route_fallback": _followups_reconciliation_count(apply_counts, "route_fallback"),
        "range_unparsed_bullets": _followups_reconciliation_count(apply_counts, "unparsed_bullets")
        if "unparsed_bullets" in apply_counts
        else 0,
        "range_unresolved_append_new": _followups_reconciliation_count(idempotency_counts, "append_new"),
        "range_unresolved_possible_duplicate": _followups_reconciliation_count(
            idempotency_counts, "possible_duplicate"
        ),
        "range_unresolved_route_fallback": _followups_reconciliation_count(idempotency_counts, "route_fallback"),
        "range_unresolved_unparsed_bullets": _followups_reconciliation_count(
            idempotency_counts, "unparsed_bullets"
        )
        if "unparsed_bullets" in idempotency_counts
        else 0,
        "manual_decision_ref": str(receipt.get("manual_decision_ref", "")).strip(),
        "already_tracked_ref": str(receipt.get("already_tracked_ref", "")).strip(),
        "source_range_command": str(receipt.get("command", "")).strip(),
    }
    unresolved_total = sum(
        int(reconciliation[field])
        for field in (
            "range_unresolved_append_new",
            "range_unresolved_possible_duplicate",
            "range_unresolved_route_fallback",
            "range_unresolved_unparsed_bullets",
        )
    )
    if unresolved_total and not (
        _is_meaningful_value(reconciliation["manual_decision_ref"])
        or _is_meaningful_value(reconciliation["already_tracked_ref"])
    ):
        raise ValueError(
            "followups_lane_reconciliation: unresolved range counts require manual_decision_ref or already_tracked_ref"
        )
    reconciliation["owner_summary"] = (
        f"file-lane={harvest_result} ({harvest_count}); "
        f"range-lane apply append_new={reconciliation['range_append_new']}, "
        f"possible_duplicate={reconciliation['range_possible_duplicate']}, "
        f"route_fallback={reconciliation['range_route_fallback']}, "
        f"unparsed_bullets={reconciliation['range_unparsed_bullets']}; "
        f"triage_mode={triage_mode}; "
        f"unresolved={unresolved_total}"
    )
    return reconciliation


def _build_followups_triage_launch_receipt(
    root: Path,
    records: list[dict[str, Any]],
    *,
    range_ref: str,
) -> dict[str, Any]:
    record = next((item for item in records if item.get("step") == "followups_triage_launch"), None)
    if record is None:
        raise ValueError("followups_triage_launch_receipt: missing followups_triage_launch step record")
    if record.get("in_scope") != "yes":
        raise ValueError("followups_triage_launch_receipt: followups_triage_launch step must be in_scope=yes")

    summary = _parse_count_summary(str(record.get("count_summary", "")))
    triage_mode = summary["triage_mode"].strip().lower()
    try:
        validate_followups_triage_command_surface(
            str(record.get("command", "")),
            triage_mode=triage_mode,
            expected_range=range_ref if triage_mode == "range" else None,
        )
    except ValueError as exc:
        raise ValueError(f"followups_triage_launch_receipt: {exc}") from exc
    source_path = summary.get("source_harvest_receipt_path", "").strip()
    source_file = _require_repo_relative_file(
        root,
        source_path,
        label="followups_triage_launch_receipt",
        field="source_harvest_receipt_path",
    )
    source_text = source_file.read_text(encoding="utf-8", errors="replace")
    if "## Follow-up harvest triage/import receipt" not in source_text:
        raise ValueError("followups_triage_launch_receipt: source harvest receipt missing follow-up launch heading")
    if "planveyor_followups_triage" not in source_text:
        raise ValueError("followups_triage_launch_receipt: source harvest receipt missing planveyor_followups_triage command")
    if "followups_index_rebuild.py" not in source_text:
        raise ValueError("followups_triage_launch_receipt: source harvest receipt missing followups_index_rebuild.py command")

    process_improvements_ref = summary.get(
        "process_improvements_ref",
        "N/A (why=process-improvements decision receipt is cited separately)",
    )
    receipt = {
        "source_harvest_receipt_path": source_path,
        "triage_mode": triage_mode,
        "command": str(record.get("command", "")).strip(),
        "dry_run": _followups_triage_phase(summary, "dry_run"),
        "apply": _followups_triage_phase(summary, "apply"),
        "idempotency_apply": _followups_triage_phase(summary, "idempotency"),
        "index_rebuild": {
            "command": "scripts/followups_index_rebuild.py --project-root .",
            "index_path": summary["index_path"].strip(),
            "status": summary["index_rebuild_status"].strip().lower(),
            "readback_status": summary["readback_status"].strip().lower(),
        },
        "process_improvements_lane": {
            "status": summary["process_improvements_lane"].strip().lower(),
            "decision_receipt_path": process_improvements_ref.strip(),
        },
    }
    receipt.update(_followups_triage_launch_closure_refs(summary))
    return receipt


def _extract_process_improvements_open_summary(source_text: str) -> dict[str, str] | None:
    pattern = re.compile(
        rf"{re.escape(PROCESS_IMPROVEMENTS_OPEN_SUMMARY_FIELD)}\s*:\s*(?P<body>.+)$",
        flags=re.IGNORECASE | re.MULTILINE,
    )
    matches = list(pattern.finditer(source_text))
    if not matches:
        return None
    if len(matches) > 1:
        raise ValueError("process_improvements_open_summary: source harvest receipt has multiple summary lines")
    return _parse_semicolon_summary(matches[0].group("body"))


def _markdown_table_cells(line: str) -> list[str]:
    if "|" not in line:
        return []
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return []
    return [cell.strip() for cell in stripped.strip("|").split("|")]


def _normalize_table_column(value: str) -> str:
    return re.sub(r"\s+", "_", value.strip().strip("`").lower())


def _strip_markdown_cell(value: str) -> str:
    return value.strip().strip("`").strip()


def _process_improvement_line_assignments(line: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for match in PROCESS_IMPROVEMENT_FIELD_ASSIGNMENT_RE.finditer(line):
        key = _normalize_table_column(match.group("key"))
        value = match.group("backtick") if match.group("backtick") is not None else match.group("bare")
        fields[key] = _strip_markdown_cell((value or "").strip().rstrip(".,)"))
    return fields


def _process_improvement_decision_section_lines(source_text: str) -> list[str]:
    lines = source_text.splitlines()
    out: list[str] = []
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped.lower() == PROCESS_IMPROVEMENT_DECISIONS_HEADING.lower():
            in_section = True
            continue
        if in_section and stripped.startswith("## "):
            break
        if in_section:
            out.append(line)
    return out


def _visible_process_improvement_summary_rows(source_text: str) -> list[str]:
    rows: list[str] = []
    header: list[str] | None = None
    for line in _process_improvement_decision_section_lines(source_text):
        if PROCESS_IMPROVEMENTS_OPEN_SUMMARY_FIELD in line:
            continue
        fields = _process_improvement_line_assignments(line)
        assigned_status = (fields.get("raw_status") or fields.get("status") or "").lower()
        if assigned_status in PROCESS_IMPROVEMENTS_OPEN_SUMMARY_STATUSES:
            rows.append(assigned_status)
            continue
        cells = _markdown_table_cells(line)
        if not cells:
            continue
        normalized = [_normalize_table_column(cell) for cell in cells]
        if "raw_status" in normalized or "status" in normalized:
            header = normalized
            continue
        if header is None:
            continue
        status_index = header.index("raw_status") if "raw_status" in header else header.index("status")
        if status_index >= len(cells):
            continue
        status = _strip_markdown_cell(cells[status_index]).lower()
        if status in PROCESS_IMPROVEMENTS_OPEN_SUMMARY_STATUSES:
            rows.append(status)
    return rows


def _empty_process_improvements_open_summary(source_path: str) -> dict[str, Any]:
    return {
        "source_harvest_receipt_path": source_path,
        "decision_receipt_path": f"{source_path}#process-improvement-promotion-decisions",
        "ordinary_followups_result": "NO FOLLOWUPS",
        "lane_status": "separate",
        "counts_by_raw_status": {
            "open": 0,
            "triaged": 0,
            "promoted": 0,
        },
        "null_execution_rows": 0,
        "owner_or_next_step": "none (no open/triaged/promoted process-improvement rows)",
    }


def _process_improvements_summary_int(summary: dict[str, str], key: str) -> int:
    raw = summary.get(key, "")
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"process_improvements_open_summary: {key} must be an integer") from exc
    if value < 0:
        raise ValueError(f"process_improvements_open_summary: {key} must be >= 0")
    return value


def _build_process_improvements_open_summary(
    root: Path,
    followups_triage_launch_receipt: dict[str, Any],
) -> dict[str, Any]:
    source_path = str(followups_triage_launch_receipt.get("source_harvest_receipt_path", "")).strip()
    source_file = _require_repo_relative_file(
        root,
        source_path,
        label="process_improvements_open_summary",
        field="source_harvest_receipt_path",
    )
    source_text = source_file.read_text(encoding="utf-8", errors="replace")
    if PROCESS_IMPROVEMENT_DECISIONS_HEADING not in source_text:
        raise ValueError("process_improvements_open_summary: source harvest receipt missing PI decision heading")
    visible_pi_rows = _visible_process_improvement_summary_rows(source_text)
    summary = _extract_process_improvements_open_summary(source_text)
    if summary is None:
        if not visible_pi_rows:
            return _empty_process_improvements_open_summary(source_path)
        raise ValueError("process_improvements_open_summary: source harvest receipt missing process_improvements_open_summary")

    missing = [key for key in PROCESS_IMPROVEMENTS_OPEN_SUMMARY_REQUIRED_KEYS if key not in summary]
    if missing:
        raise ValueError(f"process_improvements_open_summary: missing field(s): {', '.join(missing)}")
    if summary["source"] != PROCESS_IMPROVEMENTS_OPEN_SUMMARY_SOURCE:
        raise ValueError(
            "process_improvements_open_summary: source must be "
            f"{PROCESS_IMPROVEMENTS_OPEN_SUMMARY_SOURCE}"
        )
    if summary["lane"].strip().lower() != "separate":
        raise ValueError("process_improvements_open_summary: lane must be separate")
    if summary["ordinary_followups"].strip().upper() != "NO FOLLOWUPS":
        raise ValueError("process_improvements_open_summary: ordinary_followups must be NO FOLLOWUPS")
    owner_or_next_step = summary["owner_or_next_step"].strip()
    if not _is_meaningful_value(owner_or_next_step):
        raise ValueError("process_improvements_open_summary: owner_or_next_step is required")

    counts = {
        status: _process_improvements_summary_int(summary, status)
        for status in ("open", "triaged", "promoted")
    }
    null_execution_rows = _process_improvements_summary_int(summary, "null_execution")
    if null_execution_rows > sum(counts.values()):
        raise ValueError("process_improvements_open_summary: null_execution cannot exceed open+triaged+promoted")

    return {
        "source_harvest_receipt_path": source_path,
        "decision_receipt_path": f"{source_path}#process-improvement-promotion-decisions",
        "ordinary_followups_result": "NO FOLLOWUPS",
        "lane_status": "separate",
        "counts_by_raw_status": counts,
        "null_execution_rows": null_execution_rows,
        "owner_or_next_step": owner_or_next_step,
    }


def _safe_repo_relative_path(root: Path, value: str, *, field: str) -> Path:
    raw = value.strip()
    if not _is_meaningful_value(raw):
        raise ValueError(f"docs_hygiene_suggest_summary: {field} must be a repo-relative path")
    path = Path(raw)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"docs_hygiene_suggest_summary: {field} must be a repo-relative path")
    return root / path


def _docs_hygiene_stderr_path(stdout_path: str) -> str:
    if stdout_path.endswith(".stdout"):
        return f"{stdout_path[:-len('.stdout')]}.stderr"
    return "N/A (why=stderr artifact path unavailable from stdout path)"


def _docs_hygiene_count_from_heading(line: str) -> int | None:
    match = DOCS_HYGIENE_SECTION_COUNT_RE.search(line.strip())
    if not match:
        return None
    return int(match.group("count"))


def _count_docs_hygiene_canon_blocked(lines: list[str]) -> int:
    in_section = False
    count = 0
    for line in lines:
        if line.startswith("[planveyor] ") and "Blocked by canon references" in line:
            in_section = True
            continue
        if in_section and line.startswith("[planveyor] "):
            break
        if in_section and line.startswith("  - "):
            count += 1
    return count


def _extract_docs_hygiene_archive_command(lines: list[str]) -> str:
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("python3 scripts/docs_hygiene_archive.py --range ") and stripped.endswith(" --apply"):
            return stripped
    return "N/A (why=no archive-required command marker in docs_hygiene_suggest stdout)"


def _extract_docs_hygiene_suggested_items(lines: list[str]) -> list[str]:
    items: list[str] = []
    in_command = False
    for line in lines:
        if line.strip() == "[planveyor] Suggested (Owner) command:":
            in_command = True
            continue
        if not in_command:
            continue
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped == "git rm -r \\":
            continue
        if stripped.startswith("[planveyor] "):
            break
        if stripped.endswith("\\"):
            stripped = stripped[:-1].rstrip()
        if stripped and not stripped.startswith("#"):
            items.append(stripped)
    return items


def _docs_hygiene_suggest_canonical_command(range_ref: str) -> str:
    return f"{DOCS_HYGIENE_SUGGEST_CANONICAL_PREFIX}{range_ref}"


def _docs_hygiene_candidate_class(path: str) -> str:
    if path.startswith("docs/plans/"):
        return "terminal_plan"
    if path.startswith("docs/followups/"):
        return "done_followup"
    if path.startswith("docs/code_reviews/assets/"):
        return "asset_dir"
    if path.startswith(("docs/code_reviews/", "docs/doc_reviews/", "docs/code_drafts/")):
        return "safe_review_or_code_draft"
    return "suggested_path"


def _docs_hygiene_candidate_counts(lines: list[str], suggested_items: list[str]) -> dict[str, int]:
    counts = {
        "terminal_plans": 0,
        "safe_review_code_drafts": 0,
        "blocked_review_code_drafts": 0,
        "blocked_missing_review_code_drafts": 0,
        "done_followups": 0,
        "blocked_followups": 0,
        "canon_blocked_items": _count_docs_hygiene_canon_blocked(lines),
        "suggested_git_rm_paths": 0,
        "suggested_asset_dirs": 0,
        "suggested_owner_command_items": len(suggested_items),
    }
    for line in lines:
        if line.startswith("[planveyor] Terminal plans in range"):
            counts["terminal_plans"] = _docs_hygiene_count_from_heading(line) or 0
        elif line.startswith("[planveyor] Review/code drafts safe to delete"):
            counts["safe_review_code_drafts"] = _docs_hygiene_count_from_heading(line) or 0
        elif line.startswith("[planveyor] Review/code drafts NOT safe to delete"):
            counts["blocked_review_code_drafts"] = _docs_hygiene_count_from_heading(line) or 0
        elif line.startswith("[planveyor] Review/code drafts blocked BUT missing on disk"):
            counts["blocked_missing_review_code_drafts"] = _docs_hygiene_count_from_heading(line) or 0
        elif line.startswith("[planveyor] Followups (Done) candidates"):
            counts["done_followups"] = _docs_hygiene_count_from_heading(line) or 0
        elif line.startswith("[planveyor] Followups (Done) blocked"):
            counts["blocked_followups"] = _docs_hygiene_count_from_heading(line) or 0
    counts["suggested_asset_dirs"] = sum(1 for item in suggested_items if item.startswith("docs/code_reviews/assets/"))
    counts["suggested_git_rm_paths"] = len(suggested_items) - counts["suggested_asset_dirs"]
    return counts


def _build_docs_hygiene_suggest_summary(
    root: Path,
    records: list[dict[str, Any]],
    *,
    range_ref: str,
) -> dict[str, Any]:
    record = next((item for item in records if item.get("step") == "docs_hygiene_suggest"), None)
    if record is None:
        raise ValueError("docs_hygiene_suggest_summary: missing docs_hygiene_suggest step record")
    if record.get("in_scope") != "yes":
        raise ValueError("docs_hygiene_suggest_summary: docs_hygiene_suggest step must be in_scope=yes")
    stdout_rel = str(record.get("artifact_path", "")).strip()
    stdout_path = _safe_repo_relative_path(root, stdout_rel, field="source_stdout_path")
    if not stdout_path.is_file():
        raise ValueError(f"docs_hygiene_suggest_summary: source stdout missing on disk: {stdout_rel}")
    text = stdout_path.read_text(encoding="utf-8", errors="replace")
    if "Traceback" in text:
        raise ValueError("docs_hygiene_suggest_summary: source stdout contains Traceback")
    range_match = DOCS_HYGIENE_RANGE_RE.search(text)
    if not range_match:
        raise ValueError("docs_hygiene_suggest_summary: source stdout missing [planveyor] Range marker")
    stdout_range = range_match.group("range").strip()
    if stdout_range != range_ref:
        raise ValueError(
            f"docs_hygiene_suggest_summary: stdout range={stdout_range}; expected={range_ref}"
        )
    if "[planveyor] Suggested (Owner) command:" not in text:
        raise ValueError("docs_hygiene_suggest_summary: source stdout missing Suggested (Owner) command marker")

    lines = text.splitlines()
    command = str(record.get("command", "")).strip()
    canonical_command = _docs_hygiene_suggest_canonical_command(range_ref)
    if command not in {canonical_command, DOCS_HYGIENE_SUGGEST_GATE_COMMAND}:
        raise ValueError(
            "docs_hygiene_suggest_summary: command must be exact "
            f"{DOCS_HYGIENE_SUGGEST_GATE_COMMAND!r} or {canonical_command!r}"
        )
    suggested_items = _extract_docs_hygiene_suggested_items(lines)
    suggest_result = str(record.get("result", "")).strip()
    if not suggest_result and "exit_code" in record:
        suggest_result = f"exit_code={record['exit_code']}"
    top_candidates = [
        {
            "path": path,
            "class": _docs_hygiene_candidate_class(path),
            "reason": "included in Suggested (Owner) command",
        }
        for path in suggested_items[:DOCS_HYGIENE_SUGGEST_TOP_CANDIDATES_LIMIT]
    ]
    return {
        "range": range_ref,
        "command": canonical_command,
        "gate_command": command,
        "suggest_result": suggest_result,
        "source_stdout_path": stdout_rel,
        "source_stderr_path": _docs_hygiene_stderr_path(stdout_rel),
        "report_only": True,
        "deletion_executed": False,
        "ready_to_push_ticked_by_suggest_gate": False,
        "archive_required_command": _extract_docs_hygiene_archive_command(lines),
        "suggested_owner_rerun_command": canonical_command,
        "candidate_counts": _docs_hygiene_candidate_counts(lines, suggested_items),
        "top_candidates": top_candidates,
        "omitted_count": max(0, len(suggested_items) - DOCS_HYGIENE_SUGGEST_TOP_CANDIDATES_LIMIT),
    }


def _normalize_archive_snapshot(
    record: dict[str, Any],
    *,
    command_rules: CommandPortabilityRules = GENERIC_COMMAND_PORTABILITY_RULES,
) -> dict[str, Any]:
    if _manifest_has_secretish_keys(record):
        raise ValueError("archive_snapshot: secret-like credential keys are not allowed")

    out = {field: _field_string(record.get(field, "")) for field in ARCHIVE_SNAPSHOT_FIELDS}
    out["export_command"] = _portabilize_command(out["export_command"], rules=command_rules)
    missing_fields = [field for field in ARCHIVE_SNAPSHOT_FIELDS if not out[field]]
    if missing_fields:
        raise ValueError(f"archive_snapshot: missing required field(s): {', '.join(missing_fields)}")

    status = out["status"].lower()
    out["status"] = status
    if status not in ARCHIVE_SNAPSHOT_STATUSES:
        raise ValueError(f"archive_snapshot: status must be {'|'.join(sorted(ARCHIVE_SNAPSHOT_STATUSES))}")

    backend = out["storage_backend"]
    if _is_meaningful_value(backend) and backend not in ARCHIVE_SNAPSHOT_BACKENDS:
        raise ValueError(f"archive_snapshot: unsupported storage_backend={backend!r}")

    object_uri = out["object_uri"]
    if _object_uri_has_inline_secret(object_uri):
        raise ValueError("archive_snapshot: object_uri appears to contain inline credentials or secret query material")

    checksum = out["checksum"].lower()
    if _is_meaningful_value(checksum) and not SHA256_RE.fullmatch(checksum):
        raise ValueError("archive_snapshot: checksum must be lowercase sha256 hex or sha256:<hex>")
    source_db_sha = out["snapshot_source_db_sha256"].lower()
    if _is_meaningful_value(source_db_sha) and not SHA256_RE.fullmatch(source_db_sha):
        raise ValueError("archive_snapshot: snapshot_source_db_sha256 must be lowercase sha256 hex or sha256:<hex>")

    no_op_reason = out["no_op_reason"]
    blocker_reason = out["blocker_reason"]

    if status == "ok":
        if backend not in ARCHIVE_SNAPSHOT_BACKENDS:
            raise ValueError("archive_snapshot: ok status requires selected storage_backend")
        if not _is_meaningful_value(out["manifest_path"]):
            raise ValueError("archive_snapshot: ok status requires manifest_path")
        if not _is_meaningful_value(checksum):
            raise ValueError("archive_snapshot: ok status requires checksum")
        if not _is_meaningful_value(out["format_version"]):
            raise ValueError("archive_snapshot: ok status requires format_version")
        if "planveyor_docs_archive_snapshot_export" not in out["export_command"]:
            raise ValueError("archive_snapshot: ok status requires export_command")
        if out["export_status"] != "ok":
            raise ValueError("archive_snapshot: ok status requires export_status=ok")
        if not _is_meaningful_value(out["snapshot_created_at_utc"]):
            raise ValueError("archive_snapshot: ok status requires snapshot_created_at_utc")
        if not _is_meaningful_value(source_db_sha):
            raise ValueError("archive_snapshot: ok status requires snapshot_source_db_sha256")
        try:
            source_docs_count = int(out["snapshot_source_docs_count"])
        except ValueError as exc:
            raise ValueError("archive_snapshot: snapshot_source_docs_count must be a non-negative integer") from exc
        if source_docs_count < 0:
            raise ValueError("archive_snapshot: snapshot_source_docs_count must be a non-negative integer")
        if "planveyor_docs_archive_snapshot_export" not in out["source"]:
            raise ValueError("archive_snapshot: ok status requires source to include export")
        if backend in S3_BACKENDS:
            if not _is_meaningful_value(object_uri):
                raise ValueError("archive_snapshot: selected S3/MinIO backend requires object_uri")
            if out["access_status"] != "ok":
                raise ValueError("archive_snapshot: selected S3/MinIO backend requires access_status=ok")
        elif not _is_meaningful_value(out["artifact_path"]):
            raise ValueError("archive_snapshot: git-backed backend requires artifact_path")
        if out["restore_status"] != "ok":
            raise ValueError("archive_snapshot: ok status requires restore_status=ok")
        if out["readback_status"] != "ok":
            raise ValueError("archive_snapshot: ok status requires readback_status=ok")
        if not _is_na_value(no_op_reason):
            raise ValueError("archive_snapshot: ok status requires no_op_reason=N/A (...)")
        if not _is_na_value(blocker_reason):
            raise ValueError("archive_snapshot: ok status requires blocker_reason=N/A (...)")
    elif status == "no_op":
        if not ENUM_RE.fullmatch(no_op_reason) or no_op_reason in DISALLOWED_NO_OP_REASONS:
            raise ValueError("archive_snapshot: no_op status requires an allowed enum-like no_op_reason")
        if not _is_na_value(blocker_reason):
            raise ValueError("archive_snapshot: no_op status requires blocker_reason=N/A (...)")
        if out["restore_status"] not in {"no_op", "not_required"}:
            raise ValueError("archive_snapshot: no_op status requires restore_status=no_op|not_required")
        if out["readback_status"] not in {"no_op", "not_required"}:
            raise ValueError("archive_snapshot: no_op status requires readback_status=no_op|not_required")
    else:
        if not ENUM_RE.fullmatch(blocker_reason):
            raise ValueError("archive_snapshot: blocked status requires enum-like blocker_reason")
        if not _is_na_value(no_op_reason):
            raise ValueError("archive_snapshot: blocked status requires no_op_reason=N/A (...)")

    return out


def _normalize_record(
    record: dict[str, Any],
    *,
    command_rules: CommandPortabilityRules = GENERIC_COMMAND_PORTABILITY_RULES,
) -> dict[str, Any]:
    out = {field: _field_string(record.get(field, "")) for field in REQUIRED_STEP_FIELDS}
    out["command"] = _portabilize_command(out["command"], rules=command_rules)
    if not STEP_RE.fullmatch(out["step"]):
        raise ValueError(f"invalid step token: {out['step']!r}")
    if out["step"] not in REQUIRED_STEPS:
        raise ValueError(f"unsupported step token: {out['step']!r}")
    missing_fields = [field for field in REQUIRED_STEP_FIELDS if not out[field]]
    if missing_fields:
        raise ValueError(f"{out['step']}: missing required field(s): {', '.join(missing_fields)}")
    exit_code_value = _field_string(record.get("exit_code", ""))
    if "exit_code" in record and exit_code_value:
        try:
            out["exit_code"] = int(exit_code_value)
        except ValueError as exc:
            raise ValueError(f"{out['step']}: exit_code must be an integer") from exc
    result_value = _field_string(record.get("result", ""))
    if "result" in record and result_value:
        out["result"] = result_value
    if "exit_code" not in out and "result" not in out:
        raise ValueError(f"{out['step']}: either exit_code or result is required")
    if out["in_scope"] not in {"yes", "no"}:
        raise ValueError(f"{out['step']}: in_scope must be yes|no")
    if out["in_scope"] == "yes" and not _is_na_value(out["no_op_reason"]):
        raise ValueError(f"{out['step']}: ran steps must use no_op_reason=N/A (...)")
    if out["step"] == "docs_index_context":
        _validate_docs_index_context_record(out)
    if out["step"] == "retrieval_metrics":
        _validate_retrieval_metrics_record(out)
    if out["step"] == "followups_triage_launch":
        _validate_followups_triage_launch_record(out)
    return out


def _build_payload(
    root: Path,
    records: list[dict[str, Any]],
    out_path: Path,
    archive_snapshot: dict[str, Any],
) -> dict[str, Any]:
    base = _read_range_value(root / ".planveyor.range.base")
    head = _read_range_value(root / ".planveyor.range.head")
    range_ref = f"{base}..{head}"
    tracker_path = root / ".planveyor.merge_tracker.md"
    if not tracker_path.is_file():
        raise ValueError(f"missing {tracker_path}")
    followups_triage_launch_receipt = _build_followups_triage_launch_receipt(
        root,
        records,
        range_ref=range_ref,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "range": range_ref,
        "base": base,
        "head": head,
        "tracker_path": ".planveyor.merge_tracker.md",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "generated_by": "scripts/post_merge_operational_receipt.py",
        "receipt_path": out_path.relative_to(root).as_posix(),
        "archive_snapshot": archive_snapshot,
        "docs_hygiene_suggest_summary": _build_docs_hygiene_suggest_summary(
            root,
            records,
            range_ref=range_ref,
        ),
        "followups_triage_launch_receipt": followups_triage_launch_receipt,
        "followups_lane_reconciliation": _build_followups_lane_reconciliation(
            root,
            followups_triage_launch_receipt,
        ),
        "process_improvements_open_summary": _build_process_improvements_open_summary(
            root,
            followups_triage_launch_receipt,
        ),
        "steps": records,
    }


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Post-merge operational receipt",
        "",
        "**Status:** ✅ Done",
        "",
        "## Operational receipt summary",
        f"- schema_version: {payload['schema_version']}",
        f"- range: {payload['range']}",
        f"- base: {payload['base']}",
        f"- head: {payload['head']}",
        f"- tracker_path: {payload['tracker_path']}",
        f"- archive_snapshot_status: {payload['archive_snapshot']['status']}",
        f"- archive_snapshot_backend: {payload['archive_snapshot']['storage_backend']}",
        f"- archive_snapshot_manifest: {payload['archive_snapshot']['manifest_path']}",
        f"- archive_snapshot_artifact: {payload['archive_snapshot']['artifact_path']}",
        f"- archive_snapshot_object_uri: {payload['archive_snapshot']['object_uri']}",
        f"- archive_snapshot_checksum: {payload['archive_snapshot']['checksum']}",
        f"- archive_snapshot_export_command: {payload['archive_snapshot']['export_command']}",
        f"- archive_snapshot_export_status: {payload['archive_snapshot']['export_status']}",
        f"- archive_snapshot_created_at_utc: {payload['archive_snapshot']['snapshot_created_at_utc']}",
        f"- archive_snapshot_source_db_sha256: {payload['archive_snapshot']['snapshot_source_db_sha256']}",
        f"- archive_snapshot_source_docs_count: {payload['archive_snapshot']['snapshot_source_docs_count']}",
        f"- archive_snapshot_restore_status: {payload['archive_snapshot']['restore_status']}",
        f"- archive_snapshot_readback_status: {payload['archive_snapshot']['readback_status']}",
        f"- docs_hygiene_suggest_report_only: {payload['docs_hygiene_suggest_summary']['report_only']}",
        f"- docs_hygiene_suggest_deletion_executed: {payload['docs_hygiene_suggest_summary']['deletion_executed']}",
        f"- docs_hygiene_suggest_omitted_count: {payload['docs_hygiene_suggest_summary']['omitted_count']}",
        f"- followups_triage_launch_mode: {payload['followups_triage_launch_receipt']['triage_mode']}",
        f"- followups_triage_launch_source: {payload['followups_triage_launch_receipt']['source_harvest_receipt_path']}",
        f"- followups_triage_launch_index_readback: {payload['followups_triage_launch_receipt']['index_rebuild']['readback_status']}",
        f"- followups_lane_reconciliation_summary: {payload['followups_lane_reconciliation']['owner_summary']}",
        f"- followups_lane_reconciliation_range_append_new: {payload['followups_lane_reconciliation']['range_append_new']}",
        f"- followups_lane_reconciliation_range_unparsed_bullets: {payload['followups_lane_reconciliation']['range_unparsed_bullets']}",
        f"- process_improvements_open_summary_lane: {payload['process_improvements_open_summary']['lane_status']}",
        f"- process_improvements_open_summary_counts: {json.dumps(payload['process_improvements_open_summary']['counts_by_raw_status'], ensure_ascii=False, sort_keys=True)}",
        f"- process_improvements_open_summary_null_execution_rows: {payload['process_improvements_open_summary']['null_execution_rows']}",
        f"- generated_at: {payload['generated_at']}",
        "",
        "## Docs hygiene suggest summary",
        f"- range: {payload['docs_hygiene_suggest_summary']['range']}",
        f"- command: {payload['docs_hygiene_suggest_summary']['command']}",
        f"- suggest_result: {payload['docs_hygiene_suggest_summary']['suggest_result']}",
        f"- source_stdout_path: {payload['docs_hygiene_suggest_summary']['source_stdout_path']}",
        f"- source_stderr_path: {payload['docs_hygiene_suggest_summary']['source_stderr_path']}",
        f"- report_only: {payload['docs_hygiene_suggest_summary']['report_only']}",
        f"- deletion_executed: {payload['docs_hygiene_suggest_summary']['deletion_executed']}",
        f"- ready_to_push_ticked_by_suggest_gate: {payload['docs_hygiene_suggest_summary']['ready_to_push_ticked_by_suggest_gate']}",
        f"- archive_required_command: {payload['docs_hygiene_suggest_summary']['archive_required_command']}",
        f"- suggested_owner_rerun_command: {payload['docs_hygiene_suggest_summary']['suggested_owner_rerun_command']}",
        f"- candidate_counts: {json.dumps(payload['docs_hygiene_suggest_summary']['candidate_counts'], ensure_ascii=False, sort_keys=True)}",
        f"- omitted_count: {payload['docs_hygiene_suggest_summary']['omitted_count']}",
        "- top_candidates:",
        *[
            f"  - {item['path']} ({item['class']}; {item['reason']})"
            for item in payload["docs_hygiene_suggest_summary"]["top_candidates"]
        ],
        "",
        "## Followups triage launch receipt",
        f"- source_harvest_receipt_path: {payload['followups_triage_launch_receipt']['source_harvest_receipt_path']}",
        f"- triage_mode: {payload['followups_triage_launch_receipt']['triage_mode']}",
        f"- command: {payload['followups_triage_launch_receipt']['command']}",
        f"- dry_run: {json.dumps(payload['followups_triage_launch_receipt']['dry_run'], ensure_ascii=False, sort_keys=True)}",
        f"- apply: {json.dumps(payload['followups_triage_launch_receipt']['apply'], ensure_ascii=False, sort_keys=True)}",
        f"- idempotency_apply: {json.dumps(payload['followups_triage_launch_receipt']['idempotency_apply'], ensure_ascii=False, sort_keys=True)}",
        f"- index_rebuild: {json.dumps(payload['followups_triage_launch_receipt']['index_rebuild'], ensure_ascii=False, sort_keys=True)}",
        f"- process_improvements_lane: {json.dumps(payload['followups_triage_launch_receipt']['process_improvements_lane'], ensure_ascii=False, sort_keys=True)}",
        "",
        "## Followups lane reconciliation",
        f"- source_harvest_receipt_path: {payload['followups_lane_reconciliation']['source_harvest_receipt_path']}",
        f"- harvest_file_followups_result: {payload['followups_lane_reconciliation']['harvest_file_followups_result']}",
        f"- harvest_file_followups_count: {payload['followups_lane_reconciliation']['harvest_file_followups_count']}",
        f"- range_triage_mode: {payload['followups_lane_reconciliation']['range_triage_mode']}",
        f"- range_append_new: {payload['followups_lane_reconciliation']['range_append_new']}",
        f"- range_merge_source: {payload['followups_lane_reconciliation']['range_merge_source']}",
        f"- range_possible_duplicate: {payload['followups_lane_reconciliation']['range_possible_duplicate']}",
        f"- range_route_fallback: {payload['followups_lane_reconciliation']['range_route_fallback']}",
        f"- range_unparsed_bullets: {payload['followups_lane_reconciliation']['range_unparsed_bullets']}",
        f"- manual_decision_ref: {payload['followups_lane_reconciliation']['manual_decision_ref'] or 'N/A (why=no unresolved range outcomes)'}",
        f"- already_tracked_ref: {payload['followups_lane_reconciliation']['already_tracked_ref'] or 'N/A (why=no unresolved range outcomes)'}",
        f"- source_range_command: {payload['followups_lane_reconciliation']['source_range_command']}",
        f"- owner_summary: {payload['followups_lane_reconciliation']['owner_summary']}",
        "",
        "## Process improvements open summary",
        f"- source_harvest_receipt_path: {payload['process_improvements_open_summary']['source_harvest_receipt_path']}",
        f"- decision_receipt_path: {payload['process_improvements_open_summary']['decision_receipt_path']}",
        f"- ordinary_followups_result: {payload['process_improvements_open_summary']['ordinary_followups_result']}",
        f"- lane_status: {payload['process_improvements_open_summary']['lane_status']}",
        f"- counts_by_raw_status: {json.dumps(payload['process_improvements_open_summary']['counts_by_raw_status'], ensure_ascii=False, sort_keys=True)}",
        f"- null_execution_rows: {payload['process_improvements_open_summary']['null_execution_rows']}",
        f"- owner_or_next_step: {payload['process_improvements_open_summary']['owner_or_next_step']}",
        "",
        "## Operational receipt JSON",
        "```json",
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="Repository root (default: current directory)")
    parser.add_argument("--out", default="", help="Output markdown path (default: docs/reviews/<stamp>_...md)")
    parser.add_argument(
        "--record-json",
        action="append",
        default=[],
        help=(
            "Repeatable JSON step record. Required fields: step, command, artifact_path, "
            "count_summary, no_op_reason, in_scope, captured_at, source, plus exit_code or result."
        ),
    )
    parser.add_argument(
        "--archive-snapshot-json",
        required=True,
        help=(
            "Archive snapshot receipt JSON. Required fields: status, storage_backend, manifest_path, "
            "artifact_path, object_uri, checksum, format_version, access_status, restore_status, "
            "readback_status, no_op_reason, blocker_reason, source."
        ),
    )
    parser.add_argument("--print-path", action="store_true", help="Print written path")
    parser.add_argument(
        "--content-profile-id",
        default="default",
        choices=sorted(_KNOWN_CONTENT_PROFILES),
        help="Public content profile; normalization uses generic interpreter rules.",
    )
    ns = parser.parse_args(argv)

    root = Path(ns.repo_root).resolve()
    try:
        command_rules = load_command_portability_rules(content_profile_id=ns.content_profile_id)
        records = [
            _normalize_record(_load_record_json(raw), command_rules=command_rules)
            for raw in ns.record_json
        ]
        archive_snapshot = _normalize_archive_snapshot(
            _load_record_json(str(ns.archive_snapshot_json)),
            command_rules=command_rules,
        )
        step_counts = {step: 0 for step in REQUIRED_STEPS}
        for record in records:
            step_counts[record["step"]] += 1
        duplicate_steps = [step for step, count in step_counts.items() if count > 1]
        if duplicate_steps:
            raise ValueError(f"duplicate step records: {', '.join(duplicate_steps)}")
        missing_steps = [step for step, count in step_counts.items() if count == 0]
        if missing_steps:
            raise ValueError(f"missing required step records: {', '.join(missing_steps)}")
        order = {step: index for index, step in enumerate(REQUIRED_STEPS)}
        records = sorted(records, key=lambda record: order[str(record["step"])])
        base = _read_range_value(root / ".planveyor.range.base")
        head = _read_range_value(root / ".planveyor.range.head")
        if not ns.out:
            out_path = _default_output_path(root, base, head)
        else:
            out_path = Path(ns.out)
            if not out_path.is_absolute():
                out_path = root / out_path
        payload = _build_payload(root, records, out_path, archive_snapshot)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(_render_markdown(payload), encoding="utf-8")
    except ValueError as exc:
        sys.stderr.write(f"post_merge_operational_receipt: {exc}\n")
        return 2

    if ns.print_path:
        sys.stdout.write(f"{out_path.relative_to(root).as_posix()}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

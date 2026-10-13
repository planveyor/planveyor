#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

sys.dont_write_bytecode = True
sys.pycache_prefix = os.devnull



SCRIPT_DIR = Path(__file__).resolve().parent
_RUNTIME_SCRIPT_DIR_TEXT = str(SCRIPT_DIR)
while _RUNTIME_SCRIPT_DIR_TEXT in sys.path:
    sys.path.remove(_RUNTIME_SCRIPT_DIR_TEXT)
sys.path.insert(0, _RUNTIME_SCRIPT_DIR_TEXT)


def _module_origin_is(module: object, expected_path: Path) -> bool:
    module_file = getattr(module, "__file__", None)
    if not isinstance(module_file, str):
        return False
    try:
        return Path(module_file).resolve(strict=True) == expected_path
    except (OSError, RuntimeError, ValueError):
        return False


def _authority_module() -> Any:
    """Load authority code only when package/direct spellings name this runtime."""

    expected_path = SCRIPT_DIR / "contract_authority_context.py"
    aliases = ("scripts.contract_authority_context", "contract_authority_context")
    package = sys.modules.get("scripts")
    package_is_local = True
    if package is not None:
        locations = getattr(package, "__path__", None)
        if locations is None:
            package_is_local = False
        else:
            try:
                resolved_locations = tuple(Path(location).resolve(strict=True) for location in locations)
            except (OSError, RuntimeError, TypeError, ValueError):
                package_is_local = False
            else:
                package_file = getattr(package, "__file__", None)
                package_is_local = (
                    bool(resolved_locations)
                    and all(path == SCRIPT_DIR for path in resolved_locations)
                    and (
                        package_file is None
                        or _module_origin_is(package, SCRIPT_DIR / "__init__.py")
                    )
                )

    loaded = [sys.modules[name] for name in aliases if name in sys.modules]
    if any(not _module_origin_is(module, expected_path) for module in loaded):
        raise ImportError("preloaded contract_authority_context is not from the docs-closeout runtime")
    if len({id(module) for module in loaded}) > 1:
        raise ImportError("package and direct contract_authority_context aliases disagree")
    module = loaded[0] if loaded else importlib.import_module("contract_authority_context")
    if not _module_origin_is(module, expected_path):
        raise ImportError("contract_authority_context must be loaded from the docs-closeout runtime")
    packaged, direct = aliases
    existing_direct = sys.modules.get(direct)
    if existing_direct is not None and existing_direct is not module:
        raise ImportError("package and direct contract_authority_context aliases disagree")
    sys.modules[direct] = module
    if package_is_local:
        existing_packaged = sys.modules.get(packaged)
        if existing_packaged is not None and existing_packaged is not module:
            raise ImportError("package and direct contract_authority_context aliases disagree")
        sys.modules[packaged] = module
    return module


_authority = _authority_module()
if TYPE_CHECKING:
    from contract_authority_context import (
        ContractAuthorityError,
        ContractContext,
        context_for_reader,
        context_to_json,
        require_declared_read,
        resolve_top_level_context,
        validate_before_effect,
    )
else:
    ContractAuthorityError = _authority.ContractAuthorityError
    ContractContext = _authority.ContractContext
    context_for_reader = _authority.context_for_reader
    context_to_json = _authority.context_to_json
    require_declared_read = _authority.require_declared_read
    resolve_top_level_context = _authority.resolve_top_level_context
    validate_before_effect = _authority.validate_before_effect


import contract_authority_children
import plan_queue
import plan_lint
import plan_status_oracle
import fs_object_identity
import process_improvements_collect
import review_header_metadata
import followups_capture
import followups_lint


NONE_LIKE_RE = re.compile(r"^(?:n/?a\b|none\b|no(?:ne)?\b)", re.IGNORECASE)
UNKNOWN_LIKE_RE = re.compile(r"^unknown\b", re.IGNORECASE)
S1_NONE_SENTINELS = frozenset(
    {
        "Отсутствуют",
        "Нет",
        "Не выявлено",
        "Отсутствуют (green verdict; канонические `B<N>` не открывались)",
    }
)
LABEL_KEYS = (
    "Loop signal",
    "Root cause class",
    "Extraordinary action",
    "Next owner",
    "Blocker IDs considered",
    "Blocker IDs",
)
TERMINAL_STATUSES = {"done", "superseded"}
DOCS_CLOSEOUT_PAYLOAD_SCHEMA = "docs_closeout_payload.v1"
DOCS_CLOSEOUT_SCHEMA_INVALID_REASON = "docs_closeout_payload_schema_invalid"
DOCS_CLOSEOUT_STATES = {"completed", "no_op", "blocked"}
FINAL_DOCS_COMMIT_VALUES = {"required", "no_op", "landed"}
PROTECTED_RECLASSIFICATION_REASON = "canon_delta_requires_process_improvement"
DOCS_DELTA_UNKNOWN_REASON = "docs_delta_unknown"
NO_CYCLE_STAGING_PROOF_UNAVAILABLE_REASON = "no_cycle_staging_proof_unavailable"
PROTECTED_DOCS_RECLASSIFICATION_TASK = (
    "Review/reclassify protected docs-closeout canon delta through docs/process_improvements/* "
    "or a promoted explicit execution carrier before any final docs-only commit."
)
TERMINAL_DOCS_DELTA_UNKNOWN_TASK = (
    "Do not dispatch Architect or the next queue role: terminal Git docs-delta proof is unavailable."
)
TERMINAL_DOCS_DELTA_UNKNOWN_PROOF_EXPECTATION = (
    "Manager must stop and rerun `planveyor_docs_closeout <plan_ref> --json` only after fresh Git "
    "docs-delta proof is available."
)
PI_CAPTURE_ROLES = process_improvements_collect.GENERAL_CAPTURE_ROLES
PI_CAPTURE_CONTINUATION_STATES = {"clean_noop", "materialized", "already_tracked"}
PI_CAPTURE_STATES = {*PI_CAPTURE_CONTINUATION_STATES, "pending", "blocked"}
PI_ADVISORY_SCHEMA = "process_improvement_advisory.v1"
PI_ADVISORY_STATES = {"clean_noop", "advisory_backlog", "unknown"}
PI_ADVISORY_STATUSES = ("open", "triaged", "promoted", "deferred", "unconfirmed")
FOLLOWUPS_RECONCILIATION_SCHEMA = "followups_reconciliation.v1"
FOLLOWUPS_RECONCILIATION_STATES = {
    "clean_noop",
    "open",
    "unknown",
    "external_clean_noop",
    "external_clean",
    "external_invalid",
    "external_unknown",
}
FOLLOWUPS_BOOTSTRAP_ADMISSION_SCHEMA = "followups_bootstrap_admission.v1"
FOLLOWUPS_CONTINUATION_ADMISSION_SCHEMA = "followups_continuation_admission.v1"
FOLLOWUPS_CONTINUATION_ADMISSION_KEYS = {
    "schema", "state", "reason", "plan_ref", "capture_cycle_id", "phase", "next_dispatch", "proof",
}
FOLLOWUPS_CONTINUATION_PROOF_KEYS = {
    "identity_payload", "semantic_closeout_identity", "source_identity", "receipt_revision",
    "receipt_content_sha256", "receipt_sha256", "receipt_object_identity", "receipt_object",
    "cycle_directory_identity", "transaction_host_identity", "followup_files",
    "baseline_process_improvement_files", "baseline_dirty_process_improvement_paths",
    "collector_proof", "collector_states", "collector_inputs", "general_pi_checkpoint", "docs_delta", "terminal_admission",
}
FOLLOWUPS_BOOTSTRAP_ADMISSION_STATES = {"ready", "blocked"}
FOLLOWUPS_BOOTSTRAP_ADMISSION_REASONS = {
    "missing_v2_frozen_manifest",
    "bootstrap_plan_schema_invalid",
    "bootstrap_source_identity_invalid",
    "bootstrap_manifest_path_unsafe",
    "bootstrap_manifest_present",
    "bootstrap_reconciliation_not_missing",
    "bootstrap_capture_path_unsafe",
    "bootstrap_capture_invalid",
    "bootstrap_capture_active",
    "bootstrap_capture_ambiguous",
    "bootstrap_blocked_predecessor_present",
}
FOLLOWUPS_BOOTSTRAP_ADMISSION_KEYS = {
    "schema",
    "state",
    "reason",
    "plan_ref",
    "canonical_manifest_path",
    "source_terminal_commit_oid",
    "source_plan_blob_oid",
    "source_plan_sha256",
}
FOLLOWUPS_BLOCKED_PREDECESSOR_RECOVERY_ADMISSION_SCHEMA = (
    "followups_blocked_predecessor_recovery_admission.v1"
)
FOLLOWUPS_BLOCKED_PREDECESSOR_RECOVERY_ADMISSION_STATES = {"not_applicable", "ready", "blocked"}
FOLLOWUPS_BLOCKED_PREDECESSOR_RECOVERY_ADMISSION_REASONS = {
    "no_blocked_predecessor",
    "blocked_predecessor_recovery_ready",
    "recovery_source_identity_invalid",
    "recovery_capture_path_unsafe",
    "recovery_capture_invalid",
    "recovery_predecessor_ambiguous",
    "recovery_predecessor_foreign",
    "recovery_predecessor_identity_drift",
    "recovery_predecessor_topology_invalid",
    "recovery_predecessor_marker_present",
    "recovery_predecessor_manifest_present",
    "recovery_predecessor_checkpoint_invalid",
    "recovery_predecessor_pi_drift",
    "recovery_already_consumed",
}
FOLLOWUPS_BLOCKED_PREDECESSOR_RECOVERY_ADMISSION_KEYS = {
    "schema",
    "state",
    "reason",
    "plan_ref",
    "semantic_closeout_identity",
    "source_terminal_commit_oid",
    "source_plan_blob_oid",
    "source_plan_sha256",
    "transaction_host_identity",
    "predecessor_capture_cycle_id",
    "predecessor_receipt_object_identity",
    "predecessor_receipt_sha256",
    "general_pi_checkpoint_sha256",
    "process_improvement_after_map_sha256",
}
V2_EXTERNAL_FOLLOWUP_STAGING_PROOF_SCHEMA = "v2_external_followup_staging_proof.v1"
V2_EXTERNAL_FOLLOWUP_STAGING_PROOF_KEYS = {
    "schema_version",
    "frozen_manifest_path",
    "frozen_manifest_object",
    "baseline_followups_snapshot_sha256",
    "source_identity",
    "carrier_path",
    "canonical_render_sha256",
    "carrier_object",
    "carrier_absence",
    "expected_parent_oid",
    "expected_rows",
}
FOLLOWUPS_CAPTURE_STATES = {"clean_noop", "materialized", "blocked"}
FOLLOWUPS_OUT_REPAIR_SHAPES = (
    "promote to a concrete docs/plans/<...>.md path in plan_meta.followups_out[].plan",
    "or add row-local terminal status/disposition with evidence such as source_ref and reason",
    "or record explicit cancellation/supersession/no-successor decision with source_ref and reason",
)
BLOCKED_CLOSEOUT_KINDS = {
    "commit_ready": "semantic_closeout_commit_pending",
    "staged_empty": "semantic_closeout_has_unstaged_delta",
    "staged_mismatch": "semantic_closeout_has_unrelated_staged_paths",
    "needs_rerun": "semantic_closeout_needs_rerun",
}
ACCEPTED_RED_CLOSEOUT_KIND = "accepted_red_recovered"
ACCEPTED_RED_BUNDLE_FIELDS = (
    "terminal_disposition",
    "delivery_green",
    "staging_policy",
    "durable_capture_required",
    "durable_capture_state",
    "active_checkout_state",
    "recovery_state",
    "recovery_ref",
    "recovery_manifest_path",
    "recovery_cleanup_path",
    "recovery_plan",
    "recovery_code_draft",
    "recovery_targets",
    "successor_plan",
    "review_bundle_sha256",
    "capture_commit",
    "cleanup_commit",
    "captured_parent",
)
DISPATCH_FAMILY = (
    ("Architect", "general", "docs/tools/prompts/architect_docs_finalize_general.md", "planveyor_arch_docs_general"),
    ("Coder", "general", "docs/tools/prompts/coder_docs_finalize_general.md", "planveyor_coder_docs_general"),
    ("Planner", "general", "docs/tools/prompts/planner_docs_finalize_general.md", "planveyor_planner_docs_general"),
    ("Reviewer", "general", "docs/tools/prompts/reviewer_docs_finalize_general.md", "planveyor_reviewer_docs_general"),
    ("Architect", "followups", "docs/tools/prompts/architect_docs_finalize_followups.md", "planveyor_arch_followups"),
    ("Coder", "followups", "docs/tools/prompts/coder_docs_finalize_followups.md", "planveyor_coder_followups"),
    ("Planner", "followups", "docs/tools/prompts/planner_docs_finalize_followups.md", "planveyor_planner_followups"),
    ("Reviewer", "followups", "docs/tools/prompts/reviewer_docs_finalize_followups.md", "planveyor_reviewer_followups"),
)
CONTENT_PROFILE_IDS = frozenset(("default", "planveyor", "target-local"))


class ProfilePromptError(RuntimeError):
    pass


def _reader_context(root: Path, context: ContractContext | None) -> ContractContext:
    return context_for_reader(root, context)


def _dispatch_family_for_profile(
    content_profile_id: str,
    *,
    context: ContractContext | None = None,
) -> tuple[tuple[str, str, str, str], ...]:
    if content_profile_id not in CONTENT_PROFILE_IDS:
        raise ProfilePromptError(
            "unsupported docs-closeout content profile: "
            f"{content_profile_id!r} "
            "(expected default, planveyor, or target-local)"
        )
    if context is not None and context.state == "engaged":
        if content_profile_id != "target-local":
            raise ProfilePromptError(
                "engaged docs-closeout context requires target-local content profile"
            )
        family = []
        for role, lane, prompt_file, wrapper in DISPATCH_FAMILY:
            source = require_declared_read(
                context,
                prompt_file,
                "docs-closeout dispatch prompt",
            )
            family.append((role, lane, str(source), wrapper))
        return tuple(family)

    if content_profile_id == "target-local":
        raise ProfilePromptError(
            "target-local docs-closeout content profile requires an engaged contract"
        )
    return DISPATCH_FAMILY


REVIEW_STATUS_BLOCKING_RE = re.compile(r"(?:\bs1\s+blocker\b|\bblocker(?:\(ы\)|s)?\b)", re.IGNORECASE)
REVIEW_STATUS_NON_BLOCKING_RE = re.compile(r"(?:✅|\bok\b|\bno\s+blockers?\b)", re.IGNORECASE)
S1_BLOCKER_HEADING_RE = re.compile(r"^\s*##\s+S1 Blocker\b", re.IGNORECASE)
H2_HEADING_RE = re.compile(r"^\s*##\s+")
H3_BLOCKER_HEADING_RE = re.compile(r"^\s*###\s+(?P<id>B\d+)\b", re.IGNORECASE)
BLOCKER_ID_LINE_RE = re.compile(
    r"^\s*-\s*Blocker ID:\s*(?:(?P<quoted>`)(?P<quoted_id>B\d+)`|(?P<bare_id>B\d+))\s*$",
    re.IGNORECASE,
)
CURRENT_STATE_LINE_RE = re.compile(r"^\s*-\s*Current state:\s*(?P<value>.*?)\s*$", re.IGNORECASE)
S1_STRUCTURAL_FIELD_PREFIX_RE = re.compile(
    r"^\s*-\s*(?:Blocker ID|Current state)(?=$|[^\w])", re.IGNORECASE
)
CANONICAL_CURRENT_BLOCKER_STATE = "open"
CANONICAL_CLOSED_BLOCKER_STATES = frozenset({"historical-fixed", "superseded"})
TERMINAL_FAST_PATH_SCHEMA = "terminal_closeout_fast_path.v1"
TERMINAL_FAST_PATH_FAMILY_LANES = tuple(f"{role}:{lane}" for role, lane, _prompt, _wrapper in DISPATCH_FAMILY)
TERMINAL_FAST_PATH_FINAL_HANDOFF_LANE = "Architect:final_docs_handoff"
PROTECTED_DOCS_PREFIXES = (
    "docs/tools/prompts/",
    "docs/playbooks/",
)
PROTECTED_DOCS_EXACT_PATHS = {
    "docs/code_drafts/_template.md",
    "docs/code_reviews/README.md",
    "docs/doc_reviews/README.md",
    "docs/followups/README.md",
    "docs/plans/README.md",
    "docs/process_improvements/README.md",
    "docs/tools/owner_runbook_codex.md",
    # The Russian copy of a protected human document keeps the original's
    # protection.  Copies are listed by exact path: `.ru.md` is not a general
    # rule for docs/.  Copies under PROTECTED_DOCS_PREFIXES are already covered.
    "docs/tools/owner_runbook_codex.ru.md",
}
PI_DERIVED_SURFACE_PATHS = {
    process_improvements_collect.INDEX_PATH.as_posix(),
    process_improvements_collect.DEFERRED_PATH.as_posix(),
    process_improvements_collect.PROMOTION_PATH.as_posix(),
}


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _root_relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _clean_value(raw: str | None) -> str | None:
    if raw is None:
        return None
    cleaned = raw.strip()
    if cleaned.startswith("`") and cleaned.endswith("`") and len(cleaned) >= 2:
        cleaned = cleaned[1:-1].strip()
    return cleaned or None


def _normalize_optional_value(raw: str | None) -> tuple[str | None, str]:
    cleaned = _clean_value(raw)
    if cleaned is None:
        return None, "unknown"
    if UNKNOWN_LIKE_RE.match(cleaned):
        return None, "unknown"
    if NONE_LIKE_RE.match(cleaned):
        return None, "none"
    return cleaned, "listed"


def _bool_text(value: bool | None) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "unknown"


def _extract_review_artifacts(plan_text: str, root: Path) -> list[Path]:
    paths: list[Path] = []
    for _line_no, raw in plan_lint.extract_live_review_artifact_refs(plan_text.splitlines()):
        target = Path(raw.strip())
        resolved = (root / target).resolve()
        if resolved.exists() and resolved not in paths:
            paths.append(resolved)
    return paths


def _latest_label_value(artifact_texts: list[tuple[Path, str]], label: str) -> tuple[str | None, Path | None]:
    pattern = re.compile(rf"^\s*(?:[-*]\s*)?(?:`)?{re.escape(label)}(?:`)?\s*:\s*(.+?)\s*$", re.IGNORECASE)
    latest_value = None
    latest_source = None
    for source_path, text in artifact_texts:
        for line in text.splitlines():
            match = pattern.match(line)
            if match:
                latest_value = _clean_value(match.group(1))
                latest_source = source_path
    return latest_value, latest_source


def _parse_blocker_ids(raw: str | None) -> list[str]:
    cleaned = _clean_value(raw)
    if cleaned is None or NONE_LIKE_RE.match(cleaned) or UNKNOWN_LIKE_RE.match(cleaned):
        return []
    values: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(r"(?:[A-Za-z0-9_./-]+#B\d+|B\d+)", cleaned):
        value = match.group(0)
        if value in seen:
            continue
        seen.add(value)
        values.append(value)
    return values


def _review_status_is_blocking(raw_status: str | None) -> bool:
    cleaned = _clean_value(raw_status)
    if cleaned is None:
        return False
    if "❌" in cleaned:
        return True
    if REVIEW_STATUS_NON_BLOCKING_RE.search(cleaned):
        return False
    return bool(REVIEW_STATUS_BLOCKING_RE.search(cleaned))


def _s1_blocker_section_lines(text: str) -> tuple[list[str], bool]:
    in_section = False
    section_count = 0
    lines: list[str] = []
    for line in text.splitlines():
        if S1_BLOCKER_HEADING_RE.match(line):
            section_count += 1
            in_section = True
            continue
        if in_section and H2_HEADING_RE.match(line):
            in_section = False
            continue
        if in_section:
            lines.append(line)
    return lines, section_count > 1


def _canonical_blocker_id(raw: str) -> str:
    return f"B{raw[1:]}"


def _s1_none_sentinel(raw: str) -> bool:
    """Recognize bounded standalone S1 none prose without widening global fields."""

    trimmed = raw.strip()
    if not trimmed:
        return False
    english_compatible = _clean_value(trimmed)
    if english_compatible and NONE_LIKE_RE.match(english_compatible):
        return True
    if trimmed.endswith("."):
        trimmed = trimmed[:-1].rstrip()
    return trimmed in S1_NONE_SENTINELS


def _s1_blocker_section_disposition(section_lines: list[str]) -> dict[str, Any]:
    """Parse canonical S1 records without letting one record decide another."""

    records: list[dict[str, Any]] = []
    current_record: dict[str, Any] | None = None
    recognized_ids: list[str] = []
    seen_recognized_ids: set[str] = set()
    orphan_ids: set[str] = set()
    orphan_structural_line = False
    standalone_non_na_line = False

    def add_recognized_id(raw: str) -> str:
        value = _canonical_blocker_id(raw)
        if value not in seen_recognized_ids:
            seen_recognized_ids.add(value)
            recognized_ids.append(value)
        return value

    for line in section_lines:
        heading_match = H3_BLOCKER_HEADING_RE.match(line)
        if heading_match:
            if current_record is not None:
                records.append(current_record)
            heading_id = add_recognized_id(heading_match.group("id"))
            current_record = {
                "heading_id": heading_id,
                "blocker_ids": [],
                "states": [],
                "malformed_structural_line": False,
            }
            continue

        blocker_match = BLOCKER_ID_LINE_RE.match(line)
        if blocker_match:
            blocker_id = add_recognized_id(
                blocker_match.group("quoted_id") or blocker_match.group("bare_id")
            )
            if current_record is None:
                orphan_structural_line = True
                orphan_ids.add(blocker_id)
            else:
                current_record["blocker_ids"].append(blocker_id)
            continue

        state_match = CURRENT_STATE_LINE_RE.match(line)
        if state_match:
            state = _clean_value(state_match.group("value"))
            if current_record is None:
                orphan_structural_line = True
            else:
                current_record["states"].append(state)
            continue

        if S1_STRUCTURAL_FIELD_PREFIX_RE.match(line):
            if current_record is None:
                orphan_structural_line = True
            else:
                current_record["malformed_structural_line"] = True
            continue

        if current_record is None:
            stripped = line.strip()
            list_value = re.sub(r"^[-*]\s+", "", stripped).strip()
            if list_value and not _s1_none_sentinel(list_value):
                standalone_non_na_line = True

    if current_record is not None:
        records.append(current_record)

    record_identity_counts: dict[str, int] = {}
    for record in records:
        blocker_ids = record["blocker_ids"]
        if len(blocker_ids) == 1 and blocker_ids[0] == record["heading_id"]:
            identity = record["heading_id"]
            record_identity_counts[identity] = record_identity_counts.get(identity, 0) + 1

    blocking_ids: set[str] = set(orphan_ids)
    malformed = orphan_structural_line or standalone_non_na_line
    closed_record_count = 0
    for record in records:
        heading_id = record["heading_id"]
        blocker_ids = record["blocker_ids"]
        states = record["states"]
        record_ids = {heading_id, *blocker_ids}
        valid_identity = len(blocker_ids) == 1 and blocker_ids[0] == heading_id
        valid_state_count = len(states) == 1
        state = states[0] if valid_state_count else None
        duplicate_record_id = valid_identity and record_identity_counts[heading_id] > 1
        if (
            not valid_identity
            or not valid_state_count
            or duplicate_record_id
            or record["malformed_structural_line"]
        ):
            malformed = True
            blocking_ids.update(record_ids)
            continue
        if state == CANONICAL_CURRENT_BLOCKER_STATE:
            blocking_ids.add(heading_id)
            continue
        if state in CANONICAL_CLOSED_BLOCKER_STATES:
            closed_record_count += 1
            continue
        malformed = True
        blocking_ids.add(heading_id)

    return {
        "blocking": bool(malformed or blocking_ids),
        "blocking_ids": [value for value in recognized_ids if value in blocking_ids],
        "recognized_ids": recognized_ids,
        "closed_only": bool(records) and not malformed and closed_record_count == len(records),
    }


def _extract_s1_blocker_ids(section_lines: list[str]) -> list[str]:
    return list(_s1_blocker_section_disposition(section_lines)["recognized_ids"])


def _s1_blocker_section_is_blocking(section_lines: list[str]) -> bool:
    return bool(_s1_blocker_section_disposition(section_lines)["blocking"])


def _review_blocker_context(
    artifact_texts: list[tuple[Path, str]], root: Path
) -> tuple[dict[str, Any], set[Path]]:
    sources: list[str] = []
    blocker_ids: list[str] = []
    seen_ids: set[str] = set()
    green_closed_only_sources: set[Path] = set()

    for source_path, text in artifact_texts:
        source_rel = _root_relative(source_path, root)
        status_values = review_header_metadata.header_values(text.splitlines(), "status")
        canonical_status, _status_line = review_header_metadata.singleton_header_value(
            text.splitlines(),
            "status",
        )
        canonical_green_status = (
            len(status_values) == 1 and _clean_value(canonical_status) == "✅ OK"
        )
        status_blocks = not canonical_green_status
        section_lines, duplicate_s1_sections = _s1_blocker_section_lines(text)
        section = _s1_blocker_section_disposition(section_lines)
        section_blocks = duplicate_s1_sections or bool(section["blocking"])
        if not status_blocks and not section_blocks:
            if section["closed_only"]:
                green_closed_only_sources.add(source_path.resolve())
            continue
        if source_rel not in sources:
            sources.append(source_rel)
        for blocker_id in section["blocking_ids"]:
            canonical = f"{source_rel}#{blocker_id}"
            if canonical in seen_ids:
                continue
            seen_ids.add(canonical)
            blocker_ids.append(canonical)

    return (
        {
            "review_blocker_status": "blocking" if sources else "none",
            "review_blocker_sources": sources,
            "review_blocker_ids": blocker_ids,
        },
        green_closed_only_sources,
    )


def _absent_runtime_value(value: Any) -> bool:
    cleaned = _clean_value(str(value)) if value is not None else None
    if cleaned is None:
        return True
    return bool(NONE_LIKE_RE.match(cleaned) or UNKNOWN_LIKE_RE.match(cleaned))


def load_bundle_payload(bundle_json: str) -> dict[str, Any]:
    payload = json.loads(bundle_json)
    if not isinstance(payload, dict):
        raise ValueError("docs_closeout expects a JSON object from planveyor_plan_bundle --closeout-json")
    return payload


def _schema_error(errors: list[str], path: str, message: str) -> None:
    errors.append(f"{path}: {message}")


def _required_string(
    payload: dict[str, Any],
    key: str,
    errors: list[str],
    *,
    allowed: set[str] | None = None,
    path: str | None = None,
) -> str | None:
    path = path or key
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        _schema_error(errors, path, "missing required string")
        return None
    if allowed is not None and value not in allowed:
        _schema_error(errors, path, f"unsupported value {value!r}; expected one of {sorted(allowed)}")
    return value


def _required_bool(payload: dict[str, Any], key: str, errors: list[str], *, path: str | None = None) -> bool | None:
    path = path or key
    value = payload.get(key)
    if not isinstance(value, bool):
        _schema_error(errors, path, "missing required boolean")
        return None
    return value


def _required_dict(payload: dict[str, Any], key: str, errors: list[str], *, path: str | None = None) -> dict[str, Any] | None:
    path = path or key
    value = payload.get(key)
    if not isinstance(value, dict):
        _schema_error(errors, path, "missing required object")
        return None
    return value


def _required_string_list(
    payload: dict[str, Any],
    key: str,
    errors: list[str],
    *,
    path: str | None = None,
) -> list[str] | None:
    path = path or key
    value = payload.get(key)
    if not isinstance(value, list):
        _schema_error(errors, path, "missing required list")
        return None
    bad_items = [idx for idx, item in enumerate(value) if not isinstance(item, str)]
    if bad_items:
        _schema_error(errors, path, f"non-string item(s) at indexes {bad_items}")
        return None
    return value


def _required_list(payload: dict[str, Any], key: str, errors: list[str], *, path: str | None = None) -> list[Any] | None:
    path = path or key
    value = payload.get(key)
    if not isinstance(value, list):
        _schema_error(errors, path, "missing required list")
        return None
    return value


def _validate_process_improvement_advisory(payload: dict[str, Any], errors: list[str]) -> None:
    _required_string(
        payload,
        "process_improvement_advisory_state",
        errors,
        allowed=PI_ADVISORY_STATES,
    )
    _required_string(payload, "process_improvement_advisory_reason", errors)
    counts = _required_dict(payload, "process_improvement_advisory_counts", errors)
    if counts is not None:
        for key in _empty_process_improvement_advisory_counts():
            if not isinstance(counts.get(key), int):
                _schema_error(errors, f"process_improvement_advisory_counts.{key}", "missing required integer")
    _required_string(payload, "process_improvement_advisory_proof_host", errors)


def _validate_followups_reconciliation(payload: dict[str, Any], errors: list[str]) -> None:
    followups = _required_dict(payload, "followups_reconciliation", errors)
    if followups is None:
        return
    _required_string(
        followups,
        "schema",
        errors,
        allowed={FOLLOWUPS_RECONCILIATION_SCHEMA},
        path="followups_reconciliation.schema",
    )
    _required_string(
        followups,
        "state",
        errors,
        allowed=FOLLOWUPS_RECONCILIATION_STATES,
        path="followups_reconciliation.state",
    )
    _required_string(followups, "reason", errors, path="followups_reconciliation.reason")
    _required_string(followups, "proof_host", errors, path="followups_reconciliation.proof_host")
    _required_list(followups, "open_items", errors, path="followups_reconciliation.open_items")
    _required_list(
        followups,
        "closed_or_promoted_items",
        errors,
        path="followups_reconciliation.closed_or_promoted_items",
    )


def _validate_followups_bootstrap_admission(payload: dict[str, Any], errors: list[str]) -> None:
    admission = _required_dict(payload, "followups_bootstrap_admission", errors)
    if admission is None:
        return
    if set(admission) != FOLLOWUPS_BOOTSTRAP_ADMISSION_KEYS:
        _schema_error(errors, "followups_bootstrap_admission", "has unknown or missing fields")
        return
    _required_string(
        admission,
        "schema",
        errors,
        allowed={FOLLOWUPS_BOOTSTRAP_ADMISSION_SCHEMA},
        path="followups_bootstrap_admission.schema",
    )
    state = _required_string(
        admission,
        "state",
        errors,
        allowed=FOLLOWUPS_BOOTSTRAP_ADMISSION_STATES,
        path="followups_bootstrap_admission.state",
    )
    reason = _required_string(
        admission,
        "reason",
        errors,
        allowed=FOLLOWUPS_BOOTSTRAP_ADMISSION_REASONS,
        path="followups_bootstrap_admission.reason",
    )
    _required_string(admission, "plan_ref", errors, path="followups_bootstrap_admission.plan_ref")
    _required_string(
        admission,
        "canonical_manifest_path",
        errors,
        path="followups_bootstrap_admission.canonical_manifest_path",
    )
    identity_keys = (
        "source_terminal_commit_oid",
        "source_plan_blob_oid",
        "source_plan_sha256",
    )
    if state == "ready":
        if reason != "missing_v2_frozen_manifest":
            _schema_error(errors, "followups_bootstrap_admission.reason", "ready admission must preserve missing_v2_frozen_manifest")
        for key in identity_keys:
            _required_string(admission, key, errors, path=f"followups_bootstrap_admission.{key}")
    else:
        for key in identity_keys:
            value = admission.get(key)
            if value is not None and not isinstance(value, str):
                _schema_error(errors, f"followups_bootstrap_admission.{key}", "must be string or null when blocked")


def _validate_followups_continuation_admission(payload: dict[str, Any], errors: list[str]) -> None:
    admission = payload.get("followups_continuation_admission")
    selected = payload.get("followups_capture_cycle_id") not in (None, "none", "")
    if admission is None and not selected:
        return  # Compatibility for payloads without an explicit capture selector.
    path = "followups_continuation_admission"
    if not isinstance(admission, dict) or set(admission) != FOLLOWUPS_CONTINUATION_ADMISSION_KEYS:
        _schema_error(errors, path, "missing admission or unknown/missing fields")
        return
    if (admission["schema"] != FOLLOWUPS_CONTINUATION_ADMISSION_SCHEMA
            or admission["state"] not in ("not_applicable", "blocked", "ready")
            or admission["plan_ref"] != payload.get("plan_ref")
            or admission["phase"] != "pre_first_followups"
            or not isinstance(admission["reason"], str) or not admission["reason"]):
        _schema_error(errors, path, "invalid schema/state/subject/phase/reason")
    if selected and admission["capture_cycle_id"] != payload.get("followups_capture_cycle_id"):
        _schema_error(errors, path, "selector differs from the explicit capture selector")
    if admission["state"] != "ready":
        if admission["proof"] is not None or admission["next_dispatch"] is not None:
            _schema_error(errors, path, "non-ready admission cannot carry permission")
        return
    proof = admission["proof"]
    if (admission["reason"] != "pre_first_followups" or admission["next_dispatch"] != "Architect:followups"
            or not selected or not isinstance(admission["capture_cycle_id"], str)
            or not followups_capture.UUID4_RE.fullmatch(admission["capture_cycle_id"])
            or not isinstance(proof, dict) or set(proof) != FOLLOWUPS_CONTINUATION_PROOF_KEYS):
        _schema_error(errors, path, "ready admission lacks exact selector/proof/next dispatch")
        return
    identity = proof.get("identity_payload")
    if (not isinstance(identity, dict) or identity.get("plan_ref") != payload.get("plan_ref")
            or not isinstance(identity.get("plan_sha256"), str)
            or not followups_capture.HEX64_RE.fullmatch(identity["plan_sha256"])
            or any(identity.get(key) != payload.get(key) for key in
                   ("semantic_status", "semantic_status_norm", "semantic_closeout_kind"))
            or proof.get("semantic_closeout_identity") != followups_capture._semantic_identity(identity)):
        _schema_error(errors, path, "semantic identity is malformed or stale")
    source = proof.get("source_identity")
    if (not isinstance(source, dict) or set(source) != {
            "plan_ref", "source_terminal_commit_oid", "source_plan_blob_oid", "source_plan_sha256"}
            or source.get("plan_ref") != payload.get("plan_ref")
            or not all(isinstance(source.get(key), str) and followups_capture.OID_RE.fullmatch(source[key])
                       for key in ("source_terminal_commit_oid", "source_plan_blob_oid"))
            or not isinstance(identity, dict) or source.get("source_plan_sha256") != identity.get("plan_sha256")):
        _schema_error(errors, path, "fresh committed source identity is malformed")
    revision = proof.get("receipt_revision")
    if type(revision) is not int or revision < 1:
        _schema_error(errors, path, "receipt revision is invalid")
    for key in ("receipt_content_sha256", "receipt_sha256"):
        if not isinstance(proof.get(key), str) or not followups_capture.HEX64_RE.fullmatch(proof[key]):
            _schema_error(errors, path, f"{key} is invalid")
    for key in ("receipt_object_identity", "receipt_object", "cycle_directory_identity",
                "transaction_host_identity", "followup_files", "baseline_process_improvement_files",
                "collector_proof", "collector_states", "docs_delta", "terminal_admission"):
        if not isinstance(proof.get(key), dict):
            _schema_error(errors, path, f"{key} must be an object")
    if proof.get("baseline_dirty_process_improvement_paths") != []:
        _schema_error(errors, path, "dirty-before-begin PI paths cannot acquire ownership")
    collectors = proof.get("collector_proof")
    if not isinstance(collectors, dict) or not isinstance(collectors.get("input_receipts"), list):
        _schema_error(errors, path, "canonical collector inputs are absent")
    else:
        inputs = collectors["input_receipts"]
        if [item.get("role") if isinstance(item, dict) else None for item in inputs] != list(PI_CAPTURE_ROLES):
            _schema_error(errors, path, "canonical collector role order differs")
        for item in inputs:
            if (not isinstance(item, dict) or set(item) != {"role", "path", "object_identity", "content_sha256"}
                    or item.get("role") not in PI_CAPTURE_ROLES or not isinstance(item.get("object_identity"), dict)
                    or item.get("content_sha256") != item["object_identity"].get("sha256")
                    or item.get("path") != process_improvements_collect.capture_receipt_rel_path(
                        str(payload.get("plan_ref")), item["role"], admission["capture_cycle_id"]).as_posix()):
                _schema_error(errors, path, "canonical collector receipt identity is malformed")
        try:
            if set(collectors) != {"input_receipts", "before_process_improvement_files", "after_process_improvement_files", "process_improvement_path_results"}:
                raise ValueError("incomplete collector object proof")
            before = followups_capture._validate_pi_object_map(collectors["before_process_improvement_files"],
                admission["plan_ref"], field="continuation.before")
            after = followups_capture._validate_pi_object_map(collectors["after_process_improvement_files"],
                admission["plan_ref"], field="continuation.after")
            followups_capture._validate_pi_path_results(collectors["process_improvement_path_results"],
                plan_ref=admission["plan_ref"], before_objects=before, after_objects=after)
            if before != proof["baseline_process_improvement_files"]:
                raise ValueError("collector baseline ownership differs")
            delta = proof["docs_delta"]
            owned = followups_capture._changed_paths(before, after)
            if (not isinstance(delta, dict) or set(delta) != {"paths", "protected_paths", "owned_pi_paths"}
                    or delta["protected_paths"] != [] or delta["owned_pi_paths"] != owned
                    or not isinstance(delta["paths"], list)
                    or any(not isinstance(item, str) for item in delta["paths"])
                    or delta["paths"] != sorted(set(delta["paths"])) or set(delta["paths"]).difference(owned)):
                raise ValueError("docs delta lacks exact PI ownership")
            marker = proof["general_pi_checkpoint"]
            if marker is not None:
                followups_capture._validate_general_pi_checkpoint_marker(marker,
                    plan_ref=admission["plan_ref"], capture_cycle_id=admission["capture_cycle_id"], current_objects=after)
                if (revision != marker["prior_receipt_revision"] + 1 or marker["input_receipts"] != inputs
                        or marker["before_process_improvement_files"] != before):
                    raise ValueError("checkpoint replay proof differs")
            elif revision != 1:
                raise ValueError("pre-checkpoint revision differs")
        except (followups_capture.CaptureError, ValueError, KeyError, TypeError):
            _schema_error(errors, path, "object/delta/checkpoint proof is malformed or stale")
    states = proof.get("collector_states")
    if (not isinstance(states, dict) or set(states) != set(PI_CAPTURE_ROLES)
            or any(value not in tuple(PI_CAPTURE_CONTINUATION_STATES) for value in states.values())):
        _schema_error(errors, path, "collector states are invalid")
    inputs = proof.get("collector_inputs")
    if (not isinstance(inputs, dict) or set(inputs) != set(PI_CAPTURE_ROLES)
            or any(not isinstance(value, str) or not followups_capture.HEX64_RE.fullmatch(value)
                   for value in inputs.values())):
        _schema_error(errors, path, "canonical collector input digests are invalid")


def _validate_followups_blocked_predecessor_recovery_admission(
    payload: dict[str, Any],
    errors: list[str],
) -> None:
    admission = _required_dict(payload, "followups_blocked_predecessor_recovery_admission", errors)
    if admission is None:
        return
    if set(admission) != FOLLOWUPS_BLOCKED_PREDECESSOR_RECOVERY_ADMISSION_KEYS:
        _schema_error(errors, "followups_blocked_predecessor_recovery_admission", "has unknown or missing fields")
        return
    _required_string(
        admission,
        "schema",
        errors,
        allowed={FOLLOWUPS_BLOCKED_PREDECESSOR_RECOVERY_ADMISSION_SCHEMA},
        path="followups_blocked_predecessor_recovery_admission.schema",
    )
    state = _required_string(
        admission,
        "state",
        errors,
        allowed=FOLLOWUPS_BLOCKED_PREDECESSOR_RECOVERY_ADMISSION_STATES,
        path="followups_blocked_predecessor_recovery_admission.state",
    )
    _required_string(
        admission,
        "reason",
        errors,
        allowed=FOLLOWUPS_BLOCKED_PREDECESSOR_RECOVERY_ADMISSION_REASONS,
        path="followups_blocked_predecessor_recovery_admission.reason",
    )
    _required_string(admission, "plan_ref", errors, path="followups_blocked_predecessor_recovery_admission.plan_ref")
    identity_keys = (
        "semantic_closeout_identity",
        "source_terminal_commit_oid",
        "source_plan_blob_oid",
        "source_plan_sha256",
        "transaction_host_identity",
        "predecessor_capture_cycle_id",
        "predecessor_receipt_object_identity",
        "predecessor_receipt_sha256",
        "general_pi_checkpoint_sha256",
        "process_improvement_after_map_sha256",
    )
    if state == "ready":
        for key in (
            "semantic_closeout_identity",
            "source_terminal_commit_oid",
            "source_plan_blob_oid",
            "source_plan_sha256",
            "predecessor_capture_cycle_id",
            "predecessor_receipt_sha256",
            "general_pi_checkpoint_sha256",
            "process_improvement_after_map_sha256",
        ):
            _required_string(admission, key, errors, path=f"followups_blocked_predecessor_recovery_admission.{key}")
        for key in ("transaction_host_identity", "predecessor_receipt_object_identity"):
            if not isinstance(admission.get(key), dict):
                _schema_error(errors, f"followups_blocked_predecessor_recovery_admission.{key}", "must be an object when ready")
    else:
        for key in identity_keys:
            if admission.get(key) is not None:
                _schema_error(errors, f"followups_blocked_predecessor_recovery_admission.{key}", "must be null unless ready")


def _validate_terminal_fast_path(payload: dict[str, Any], errors: list[str]) -> None:
    fast_path = _required_dict(payload, "terminal_closeout_fast_path", errors)
    if fast_path is None:
        return
    _required_string(
        fast_path,
        "schema",
        errors,
        allowed={TERMINAL_FAST_PATH_SCHEMA},
        path="terminal_closeout_fast_path.schema",
    )
    eligible = _required_bool(fast_path, "eligible", errors, path="terminal_closeout_fast_path.eligible")
    _required_string(fast_path, "reason", errors, path="terminal_closeout_fast_path.reason")
    skipped = _required_string_list(
        fast_path,
        "skipped_lanes",
        errors,
        path="terminal_closeout_fast_path.skipped_lanes",
    )
    fallback = _required_string_list(
        fast_path,
        "fallback_lanes",
        errors,
        path="terminal_closeout_fast_path.fallback_lanes",
    )
    missing = _required_string_list(
        fast_path,
        "missing_or_dirty_preconditions",
        errors,
        path="terminal_closeout_fast_path.missing_or_dirty_preconditions",
    )
    if not isinstance(fast_path.get("proof_hosts"), dict):
        _schema_error(errors, "terminal_closeout_fast_path.proof_hosts", "missing required object")
    if not isinstance(fast_path.get("precondition_results"), dict):
        _schema_error(errors, "terminal_closeout_fast_path.precondition_results", "missing required object")
    _required_string_list(
        fast_path,
        "dirty_runtime_signals",
        errors,
        path="terminal_closeout_fast_path.dirty_runtime_signals",
    )
    if eligible is True:
        if missing:
            _schema_error(
                errors,
                "terminal_closeout_fast_path",
                "eligible=true with non-empty missing_or_dirty_preconditions",
            )
        if fallback:
            _schema_error(errors, "terminal_closeout_fast_path", "eligible=true with fallback_lanes")
        if not skipped:
            _schema_error(errors, "terminal_closeout_fast_path", "eligible=true without skipped_lanes")
        if payload.get("state") != "completed":
            _schema_error(errors, "terminal_closeout_fast_path", "eligible=true while state is not completed")
        if payload.get("final_docs_commit") not in {"no_op", "landed"}:
            _schema_error(
                errors,
                "terminal_closeout_fast_path",
                "eligible=true without final_docs_commit=no_op|landed",
            )


def _validate_v2_external_staging_object(value: Any, errors: list[str], *, path: str) -> None:
    if not isinstance(value, dict):
        _schema_error(errors, path, "expected regular-object mapping")
        return
    if set(value) != {"sha256", "file_type", "st_size"}:
        _schema_error(errors, path, "must contain exactly sha256, file_type and st_size")
    sha256 = value.get("sha256")
    if not isinstance(sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", sha256):
        _schema_error(errors, f"{path}.sha256", "must be a lower-case SHA-256")
    if value.get("file_type") != "regular":
        _schema_error(errors, f"{path}.file_type", "must equal regular")
    size = value.get("st_size")
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        _schema_error(errors, f"{path}.st_size", "must be a non-negative integer")


def _validate_v2_external_staging_proof(value: Any, errors: list[str], *, path: str) -> None:
    if not isinstance(value, dict):
        _schema_error(errors, path, "expected v2 external staging proof object")
        return
    if set(value) != V2_EXTERNAL_FOLLOWUP_STAGING_PROOF_KEYS:
        _schema_error(errors, path, "has unknown or missing proof fields")
    if value.get("schema_version") != V2_EXTERNAL_FOLLOWUP_STAGING_PROOF_SCHEMA:
        _schema_error(errors, f"{path}.schema_version", "unsupported v2 external staging proof schema")
    for key in ("frozen_manifest_path", "baseline_followups_snapshot_sha256", "carrier_path", "canonical_render_sha256"):
        raw = value.get(key)
        if not isinstance(raw, str) or not raw.strip():
            _schema_error(errors, f"{path}.{key}", "missing required string")
    for key in ("baseline_followups_snapshot_sha256", "canonical_render_sha256"):
        raw = value.get(key)
        if not isinstance(raw, str) or not re.fullmatch(r"[0-9a-f]{64}", raw):
            _schema_error(errors, f"{path}.{key}", "must be a lower-case SHA-256")
    _validate_v2_external_staging_object(value.get("frozen_manifest_object"), errors, path=f"{path}.frozen_manifest_object")
    _validate_v2_external_staging_object(value.get("carrier_object"), errors, path=f"{path}.carrier_object")
    source = value.get("source_identity")
    if not isinstance(source, dict):
        _schema_error(errors, f"{path}.source_identity", "expected exact source identity object")
    else:
        expected_source_keys = {
            "plan_ref",
            "source_terminal_commit_oid",
            "source_plan_blob_oid",
            "source_plan_sha256",
        }
        if set(source) != expected_source_keys:
            _schema_error(errors, f"{path}.source_identity", "has unknown or missing source identity fields")
        for key in expected_source_keys:
            raw = source.get(key)
            if not isinstance(raw, str) or not raw.strip():
                _schema_error(errors, f"{path}.source_identity.{key}", "missing required string")
        for key in ("source_terminal_commit_oid", "source_plan_blob_oid"):
            raw = source.get(key)
            if not isinstance(raw, str) or not re.fullmatch(r"[0-9a-f]{40,64}", raw):
                _schema_error(errors, f"{path}.source_identity.{key}", "must be a lower-case Git OID")
        raw = source.get("source_plan_sha256")
        if not isinstance(raw, str) or not re.fullmatch(r"[0-9a-f]{64}", raw):
            _schema_error(errors, f"{path}.source_identity.source_plan_sha256", "must be a lower-case SHA-256")
    absence = value.get("carrier_absence")
    expected_absence_keys = {"baseline", "source_terminal_commit", "expected_parent"}
    if not isinstance(absence, dict) or set(absence) != expected_absence_keys or any(absence.get(key) is not True for key in expected_absence_keys):
        _schema_error(errors, f"{path}.carrier_absence", "must be the exact all-true three-tree absence proof")
    parent = value.get("expected_parent_oid")
    if not isinstance(parent, str) or not re.fullmatch(r"[0-9a-f]{40,64}", parent):
        _schema_error(errors, f"{path}.expected_parent_oid", "must be a lower-case Git OID")
    rows = value.get("expected_rows")
    if not isinstance(rows, list) or not rows:
        _schema_error(errors, f"{path}.expected_rows", "must be a non-empty sorted row list")
        return
    normalized_rows: list[tuple[str, str]] = []
    for index, row in enumerate(rows):
        row_path = f"{path}.expected_rows[{index}]"
        if not isinstance(row, dict) or set(row) != {"source_ref", "item_id", "tuple_owner", "row_digest"}:
            _schema_error(errors, row_path, "must contain exactly source_ref, item_id, tuple_owner and row_digest")
            continue
        source_ref = row.get("source_ref")
        item_id = row.get("item_id")
        owner = row.get("tuple_owner")
        digest = row.get("row_digest")
        if not isinstance(source_ref, str) or not source_ref.strip():
            _schema_error(errors, f"{row_path}.source_ref", "missing required string")
        if not isinstance(item_id, str) or not item_id.strip():
            _schema_error(errors, f"{row_path}.item_id", "missing required string")
        if not isinstance(owner, str) or not owner.strip():
            _schema_error(errors, f"{row_path}.tuple_owner", "missing required string")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            _schema_error(errors, f"{row_path}.row_digest", "must be a lower-case SHA-256")
        if isinstance(source_ref, str) and isinstance(item_id, str):
            normalized_rows.append((source_ref, item_id))
    if normalized_rows != sorted(normalized_rows) or len(normalized_rows) != len(set(normalized_rows)):
        _schema_error(errors, f"{path}.expected_rows", "rows must be sorted and tuple-unique")


def _validate_architect_final_handoff(payload: dict[str, Any], errors: list[str]) -> None:
    handoff = _required_dict(payload, "architect_final_handoff", errors)
    if handoff is None:
        return
    _required_string(handoff, "role", errors, allowed={"Architect"}, path="architect_final_handoff.role")
    required = _required_bool(handoff, "required", errors, path="architect_final_handoff.required")
    _required_string(handoff, "plan_ref", errors, path="architect_final_handoff.plan_ref")
    _required_string(handoff, "task", errors, path="architect_final_handoff.task")
    _required_string(handoff, "proof_expectation", errors, path="architect_final_handoff.proof_expectation")
    _required_string_list(
        handoff,
        "final_docs_diff_paths",
        errors,
        path="architect_final_handoff.final_docs_diff_paths",
    )
    _required_string_list(
        handoff,
        "protected_docs_delta_paths",
        errors,
        path="architect_final_handoff.protected_docs_delta_paths",
    )
    _required_bool(handoff, "operational_only", errors, path="architect_final_handoff.operational_only")
    expectations = _required_list(
        handoff,
        "followups_staging_expectations",
        errors,
        path="architect_final_handoff.followups_staging_expectations",
    )
    if expectations is not None:
        paths: list[str] = []
        for index, item in enumerate(expectations):
            item_path = f"architect_final_handoff.followups_staging_expectations[{index}]"
            if not isinstance(item, dict):
                _schema_error(errors, item_path, "expected object")
                continue
            path_value = _required_string(item, "path", errors, path=f"{item_path}.path")
            ownership_class = _required_string(
                item,
                "ownership_class",
                errors,
                allowed={"ordinary_followup", "process_improvement"},
                path=f"{item_path}.ownership_class",
            )
            _required_string(item, "capture_cycle_id", errors, path=f"{item_path}.capture_cycle_id")
            _required_string(item, "receipt_content_sha256", errors, path=f"{item_path}.receipt_content_sha256")
            if not isinstance(item.get("receipt_revision"), int) or isinstance(item.get("receipt_revision"), bool):
                _schema_error(errors, f"{item_path}.receipt_revision", "missing required integer")
            _required_dict(item, "receipt_object_identity", errors, path=f"{item_path}.receipt_object_identity")
            _required_dict(item, "expected_object", errors, path=f"{item_path}.expected_object")
            _required_string(item, "expected_staged_mode", errors, allowed={"100644"}, path=f"{item_path}.expected_staged_mode")
            if ownership_class == "process_improvement":
                _required_dict(item, "ownership_proof", errors, path=f"{item_path}.ownership_proof")
            elif ownership_class == "ordinary_followup" and "ownership_proof" in item:
                _validate_v2_external_staging_proof(item.get("ownership_proof"), errors, path=f"{item_path}.ownership_proof")
            if path_value:
                paths.append(path_value)
        if paths != sorted(paths) or len(paths) != len(set(paths)):
            _schema_error(errors, "architect_final_handoff.followups_staging_expectations", "paths must be unique and sorted")
    final_docs_commit = payload.get("final_docs_commit")
    if final_docs_commit == "required" and required is not True:
        _schema_error(errors, "architect_final_handoff.required", "must be true when final_docs_commit=required")
    if final_docs_commit in {"no_op", "landed"} and required is True:
        _schema_error(
            errors,
            "architect_final_handoff.required",
            "must be false when final_docs_commit=no_op|landed",
        )
    if payload.get("state") == "blocked" and payload.get("final_docs_commit_reason") == "followup_capture_blocked":
        if payload.get("final_docs_commit") != "no_op":
            _schema_error(errors, "final_docs_commit", "blocked followups capture must project no_op")
        if required is not False:
            _schema_error(errors, "architect_final_handoff.required", "blocked followups capture cannot request Architect handoff")
        if handoff.get("skip_reason") != "blocked":
            _schema_error(errors, "architect_final_handoff.skip_reason", "blocked followups capture must use skip_reason=blocked")
        if expectations not in ([], None):
            _schema_error(
                errors,
                "architect_final_handoff.followups_staging_expectations",
                "blocked followups capture must expose an empty exact stage allowlist",
            )


def _is_nonempty_sorted_unique_string_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and item for item in value)
        and value == sorted(value)
        and len(value) == len(set(value))
    )


def _validate_protected_reclassification(payload: dict[str, Any], errors: list[str]) -> None:
    if payload.get("final_docs_commit_reason") != PROTECTED_RECLASSIFICATION_REASON:
        return

    final_paths = payload.get("final_docs_diff_paths")
    protected_paths = payload.get("protected_docs_delta_paths")
    if payload.get("state") != "completed":
        _schema_error(errors, "state", "protected reclassification must remain completed")
    if payload.get("final_docs_commit") != "required":
        _schema_error(errors, "final_docs_commit", "protected reclassification must require reclassification")
    if not _is_nonempty_sorted_unique_string_list(final_paths):
        _schema_error(errors, "final_docs_diff_paths", "must be a non-empty sorted unique protected path list")
    if not _is_nonempty_sorted_unique_string_list(protected_paths):
        _schema_error(errors, "protected_docs_delta_paths", "must be a non-empty sorted unique protected path list")
    if final_paths != protected_paths:
        _schema_error(
            errors,
            "protected_docs_delta_paths",
            "must exact-match final_docs_diff_paths for protected reclassification",
        )

    handoff = payload.get("architect_final_handoff")
    if not isinstance(handoff, dict):
        return
    handoff_final_paths = handoff.get("final_docs_diff_paths")
    handoff_protected_paths = handoff.get("protected_docs_delta_paths")
    if not _is_nonempty_sorted_unique_string_list(handoff_final_paths):
        _schema_error(
            errors,
            "architect_final_handoff.final_docs_diff_paths",
            "must be a non-empty sorted unique protected path list",
        )
    if not _is_nonempty_sorted_unique_string_list(handoff_protected_paths):
        _schema_error(
            errors,
            "architect_final_handoff.protected_docs_delta_paths",
            "must be a non-empty sorted unique protected path list",
        )
    if handoff_final_paths != final_paths:
        _schema_error(
            errors,
            "architect_final_handoff.final_docs_diff_paths",
            "must exact-match final_docs_diff_paths for protected reclassification",
        )
    if handoff_protected_paths != final_paths:
        _schema_error(
            errors,
            "architect_final_handoff.protected_docs_delta_paths",
            "must exact-match final_docs_diff_paths for protected reclassification",
        )
    if handoff.get("required") is not True:
        _schema_error(errors, "architect_final_handoff.required", "must be true for protected reclassification")
    if handoff.get("task") != PROTECTED_DOCS_RECLASSIFICATION_TASK:
        _schema_error(errors, "architect_final_handoff.task", "must be the protected reclassification task")
    if handoff.get("skip_reason") is not None:
        _schema_error(errors, "architect_final_handoff.skip_reason", "must be null for protected reclassification")
    if handoff.get("followups_staging_expectations") != []:
        _schema_error(
            errors,
            "architect_final_handoff.followups_staging_expectations",
            "must be empty for protected reclassification",
        )


def _validate_terminal_docs_delta_unknown(payload: dict[str, Any], errors: list[str]) -> None:
    if payload.get("reason_code") != DOCS_DELTA_UNKNOWN_REASON:
        return

    if payload.get("state") != "blocked":
        _schema_error(errors, "state", "unknown terminal docs delta must block closeout")
    if payload.get("final_docs_commit") != "no_op":
        _schema_error(errors, "final_docs_commit", "unknown terminal docs delta cannot grant commit authority")
    if payload.get("final_docs_commit_reason") != DOCS_DELTA_UNKNOWN_REASON:
        _schema_error(errors, "final_docs_commit_reason", "must preserve unknown terminal docs delta proof")
    if payload.get("final_docs_diff_paths") != []:
        _schema_error(errors, "final_docs_diff_paths", "must be empty when terminal docs delta proof is unknown")
    if payload.get("protected_docs_delta_paths") != []:
        _schema_error(errors, "protected_docs_delta_paths", "must be empty when terminal docs delta proof is unknown")

    handoff = payload.get("architect_final_handoff")
    if not isinstance(handoff, dict):
        return
    if handoff.get("required") is not False:
        _schema_error(errors, "architect_final_handoff.required", "unknown terminal docs delta cannot request handoff")
    if handoff.get("task") != TERMINAL_DOCS_DELTA_UNKNOWN_TASK:
        _schema_error(errors, "architect_final_handoff.task", "must stop for unknown terminal docs delta proof")
    if handoff.get("skip_reason") != DOCS_DELTA_UNKNOWN_REASON:
        _schema_error(errors, "architect_final_handoff.skip_reason", "must preserve unknown terminal docs delta proof")
    if handoff.get("followups_staging_expectations") != []:
        _schema_error(
            errors,
            "architect_final_handoff.followups_staging_expectations",
            "must be empty when terminal docs delta proof is unknown",
        )


def validate_docs_closeout_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Attach and enforce the manager-facing docs-closeout payload schema."""
    errors: list[str] = []
    _required_string(payload, "state", errors, allowed=DOCS_CLOSEOUT_STATES)
    _required_string(payload, "reason_code", errors)
    _required_string(payload, "plan_ref", errors)
    _required_string(payload, "semantic_status", errors)
    _required_string(payload, "semantic_status_norm", errors)
    _required_string(payload, "semantic_closeout_kind", errors)
    if not isinstance(payload.get("bundle_ok"), bool):
        _schema_error(errors, "bundle_ok", "missing required boolean")
    _required_list(payload, "bundle_errors", errors)
    _required_string(payload, "final_docs_commit", errors, allowed=FINAL_DOCS_COMMIT_VALUES)
    _required_string(payload, "final_docs_commit_reason", errors)
    _required_string_list(payload, "final_docs_diff_paths", errors)
    _required_string_list(payload, "protected_docs_delta_paths", errors)
    _required_string(
        payload,
        "followups_capture_state",
        errors,
        allowed=FOLLOWUPS_CAPTURE_STATES,
    )
    _required_string(payload, "followups_capture_reason", errors)
    _required_string(payload, "followups_capture_cycle_id", errors)
    _required_string(payload, "followups_capture_receipt_path", errors)
    _required_string_list(payload, "followups_capture_roles", errors)
    _required_string_list(payload, "current_plan_owned_docs_delta_paths", errors)
    _required_string_list(payload, "foreign_docs_delta_paths", errors)
    _required_string_list(payload, "blocked_docs_delta_paths", errors)
    _required_string(
        payload,
        "process_improvement_capture_state",
        errors,
        allowed=PI_CAPTURE_STATES,
    )
    _required_string(payload, "process_improvement_capture_reason", errors)
    _required_string_list(payload, "process_improvement_capture_roles", errors)
    _required_string_list(payload, "process_improvement_backlog_paths", errors)
    _required_string(payload, "process_improvement_receipt_path", errors)
    _required_string_list(payload, "process_improvement_missing_roles", errors)
    _validate_process_improvement_advisory(payload, errors)
    _validate_followups_reconciliation(payload, errors)
    _validate_followups_bootstrap_admission(payload, errors)
    _validate_followups_continuation_admission(payload, errors)
    _validate_followups_blocked_predecessor_recovery_admission(payload, errors)
    _validate_terminal_fast_path(payload, errors)
    if not isinstance(payload.get("runtime_context"), dict):
        _schema_error(errors, "runtime_context", "missing required object")
    if not isinstance(payload.get("dispatch_family"), list):
        _schema_error(errors, "dispatch_family", "missing required list")
    if not isinstance(payload.get("process_improvement_seed"), dict):
        _schema_error(errors, "process_improvement_seed", "missing required object")
    _validate_architect_final_handoff(payload, errors)
    _validate_protected_reclassification(payload, errors)
    _validate_terminal_docs_delta_unknown(payload, errors)
    if payload.get("semantic_closeout_kind") == ACCEPTED_RED_CLOSEOUT_KIND:
        _required_string(
            payload,
            "terminal_disposition",
            errors,
            allowed={"accepted_red_supersession"},
        )
        if payload.get("delivery_green") is not False:
            _schema_error(errors, "delivery_green", "must be false for accepted-red recovery")
        _required_string(payload, "staging_policy", errors, allowed={"forbidden"})
        if payload.get("durable_capture_required") is not True:
            _schema_error(errors, "durable_capture_required", "must be true for accepted-red recovery")
        _required_string(payload, "durable_capture_state", errors, allowed={"cleanup_recorded"})
        _required_string(
            payload,
            "active_checkout_state",
            errors,
            allowed={"clean", "recovery_owned_overlap"},
        )
        _required_string(payload, "recovery_state", errors, allowed={"completed"})
        for key in (
            "recovery_ref",
            "recovery_manifest_path",
            "recovery_cleanup_path",
            "recovery_plan",
            "recovery_code_draft",
            "successor_plan",
            "review_bundle_sha256",
            "capture_commit",
            "cleanup_commit",
            "captured_parent",
        ):
            _required_string(payload, key, errors)
        _required_string_list(payload, "recovery_targets", errors)
        _required_string_list(payload, "accepted_red_routing_docs", errors)
    final_docs_paths = payload.get("final_docs_diff_paths")
    owned_docs_paths = payload.get("current_plan_owned_docs_delta_paths")
    protected_reclassification = (
        payload.get("final_docs_commit_reason")
        == PROTECTED_RECLASSIFICATION_REASON
    )
    if payload.get("final_docs_commit") == "required":
        if not isinstance(final_docs_paths, list) or not final_docs_paths:
            _schema_error(errors, "final_docs_diff_paths", "must be non-empty when final_docs_commit=required")
        if (
            not protected_reclassification
            and isinstance(final_docs_paths, list)
            and isinstance(owned_docs_paths, list)
            and not set(final_docs_paths).issubset(set(owned_docs_paths))
        ):
            _schema_error(errors, "final_docs_diff_paths", "must be a subset of current-plan-owned docs paths")
        if not protected_reclassification:
            handoff = payload.get("architect_final_handoff")
            expectations = handoff.get("followups_staging_expectations") if isinstance(handoff, dict) else None
            expectation_paths = [item.get("path") for item in expectations or [] if isinstance(item, dict)]
            if isinstance(final_docs_paths, list) and expectation_paths != final_docs_paths:
                _schema_error(
                    errors,
                    "architect_final_handoff.followups_staging_expectations",
                    "paths must exact-match final_docs_diff_paths when final_docs_commit=required",
                )

    payload["schema"] = DOCS_CLOSEOUT_PAYLOAD_SCHEMA
    if errors:
        payload["state"] = "blocked"
        payload["reason_code"] = DOCS_CLOSEOUT_SCHEMA_INVALID_REASON
        payload["schema_state"] = "blocked"
        payload["schema_errors"] = errors
    else:
        payload["schema_state"] = "ok"
        payload["schema_errors"] = []
    return payload


def _format_schema_errors(payload: dict[str, Any]) -> str:
    errors = payload.get("schema_errors")
    if not errors:
        return "none"
    return "|".join(str(item) for item in errors)


def _refresh_dispatch_context_block(payload: dict[str, Any]) -> None:
    raw_block = payload.get("dispatch_context_block")
    if not isinstance(raw_block, str) or not raw_block:
        return
    replacements = {
        "- docs_closeout_state=": f"- docs_closeout_state={payload.get('state', 'blocked')}",
        "- docs_closeout_reason=": f"- docs_closeout_reason={payload.get('reason_code', DOCS_CLOSEOUT_SCHEMA_INVALID_REASON)}",
    }
    lines: list[str] = []
    inserted_schema = False
    for line in raw_block.splitlines():
        replacement = None
        for prefix, value in replacements.items():
            if line.startswith(prefix):
                replacement = value
                break
        lines.append(replacement if replacement is not None else line)
        if (replacement or line).startswith("- docs_closeout_reason="):
            lines.extend(
                [
                    f"- docs_closeout_payload_schema={payload.get('schema', DOCS_CLOSEOUT_PAYLOAD_SCHEMA)}",
                    f"- docs_closeout_payload_schema_state={payload.get('schema_state', 'blocked')}",
                    f"- docs_closeout_payload_schema_errors={_format_schema_errors(payload)}",
                ]
            )
            inserted_schema = True
    if not inserted_schema:
        lines.extend(
            [
                f"- docs_closeout_payload_schema={payload.get('schema', DOCS_CLOSEOUT_PAYLOAD_SCHEMA)}",
                f"- docs_closeout_payload_schema_state={payload.get('schema_state', 'blocked')}",
                f"- docs_closeout_payload_schema_errors={_format_schema_errors(payload)}",
            ]
        )
    payload["dispatch_context_block"] = "\n".join(lines)


def finalize_docs_closeout_payload(payload: dict[str, Any]) -> dict[str, Any]:
    validate_docs_closeout_payload(payload)
    _refresh_dispatch_context_block(payload)
    return payload


def _git_status_docs_paths(root: Path) -> tuple[list[str], bool]:
    """Return pending docs paths from porcelain status; bool=false means proof failed."""
    root = root.resolve()
    rev_parse = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
    )
    if rev_parse.returncode != 0:
        return [], False

    status = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "-z",
            "--",
            "docs",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if status.returncode != 0:
        return [], False

    paths: set[str] = set()
    entries = status.stdout.split("\0")
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if not entry:
            continue
        if len(entry) < 4:
            return [], False

        status_code = entry[:2]
        path = entry[3:]
        if path:
            paths.add(path)
        if "R" in status_code or "C" in status_code:
            if index < len(entries) and entries[index]:
                paths.add(entries[index])
                index += 1
    return sorted(paths), True


def _normalize_repo_path(raw: str) -> str:
    return raw.strip().strip("`").replace("\\", "/").lstrip("./")


def _bundle_scope_paths(bundle_payload: dict[str, Any]) -> set[str]:
    paths: set[str] = set()
    plan_ref = bundle_payload.get("plan")
    if isinstance(plan_ref, str) and plan_ref.strip():
        paths.add(_normalize_repo_path(plan_ref))

    direct_paths = bundle_payload.get("bundle_paths")
    if isinstance(direct_paths, list):
        for raw in direct_paths:
            if isinstance(raw, str) and raw.strip():
                paths.add(_normalize_repo_path(raw))

    for repo_payload in bundle_payload.get("repo_roots") or []:
        if not isinstance(repo_payload, dict):
            continue
        for raw in repo_payload.get("bundle_paths") or []:
            if isinstance(raw, str) and raw.strip():
                paths.add(_normalize_repo_path(raw))
    return paths


def _post_cas_caller_bundle_paths(
    *,
    root: Path,
    bundle_payload: dict[str, Any],
) -> tuple[str, ...] | None:
    """Accept only the producer-shaped, same-root path inventory.

    The exceptional post-CAS route has no compatibility fallback for a loose
    aggregate ``bundle_paths`` field: the normal producer publishes one
    same-root ``repo_roots`` entry, and reader admission compares that exact
    list with a fresh independently derived inventory.
    """

    if "bundle_paths" in bundle_payload:
        return None
    repo_roots = bundle_payload.get("repo_roots")
    if not isinstance(repo_roots, list) or len(repo_roots) != 1:
        return None
    repo_payload = repo_roots[0]
    if not isinstance(repo_payload, dict):
        return None
    raw_root = repo_payload.get("repo_root")
    if not isinstance(raw_root, str) or not raw_root.strip():
        return None
    try:
        if Path(raw_root).resolve() != root.resolve():
            return None
    except OSError:
        return None
    raw_paths = repo_payload.get("bundle_paths")
    if not isinstance(raw_paths, list) or not raw_paths:
        return None
    paths: list[str] = []
    for raw_path in raw_paths:
        if not isinstance(raw_path, str):
            return None
        normalized = _normalize_repo_path(raw_path)
        if not normalized or normalized != raw_path:
            return None
        try:
            normalized = followups_capture._post_cas_semantic_identity_normalize_bundle_path(root, normalized)
        except followups_capture.CaptureError:
            return None
        paths.append(normalized)
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        return None
    return tuple(paths)


def _post_cas_bundle_tree_entries(
    *,
    root: Path,
    plan_ref: str,
    bundle_payload: dict[str, Any],
) -> tuple[str, list[dict[str, str]]] | None:
    """Return only a freshly clean, current-tree exact bundle witness.

    ``already_materialized`` is a derived closeout label, not proof.  The one
    post-CAS caller path therefore reopens every scoped bundle file and checks
    it against both the index/worktree and the committed tree before asking
    the capture reader to consider a semantic transition.
    """

    if (
        bundle_payload.get("bundle_ok") is not True
        or bundle_payload.get("closeout_kind") != "already_materialized"
        or _normalize_repo_path(str(bundle_payload.get("plan") or "")) != plan_ref
    ):
        return None
    caller_paths = _post_cas_caller_bundle_paths(root=root, bundle_payload=bundle_payload)
    if caller_paths is None:
        return None
    try:
        canonical_paths = followups_capture._post_cas_semantic_identity_canonical_bundle_paths(
            root,
            plan_ref=plan_ref,
        )
    except followups_capture.CaptureError:
        return None
    if caller_paths != canonical_paths:
        return None
    try:
        head = followups_capture._git(root, "rev-parse", "--verify", "HEAD^{commit}").stdout.decode(
            "ascii", errors="replace"
        ).strip()
        if not followups_capture.OID_RE.fullmatch(head):
            return None
        entries: list[dict[str, str]] = []
        for path in canonical_paths:
            snapshot = fs_object_identity.snapshot_regular_or_absent(root, path)
            if snapshot.state != "regular" or snapshot.data is None or snapshot.git_mode not in {"100644", "100755"}:
                return None
            entry = followups_capture._ordinary_v2_read_tree_entry(
                root,
                tree_oid=head,
                carrier_path=path,
                reason_code="followup_capture_semantic_identity_mismatch",
            )
            if entry is None:
                return None
            mode, kind, oid = entry
            if mode != snapshot.git_mode or kind != "blob":
                return None
            actual_oid = followups_capture._git(
                root,
                "hash-object",
                "--stdin",
                input_bytes=snapshot.data,
            ).stdout.decode("ascii", errors="replace").strip()
            if actual_oid != oid:
                return None
            for args in (
                ("diff", "--quiet", "HEAD", "--", path),
                ("diff", "--cached", "--quiet", "HEAD", "--", path),
            ):
                if followups_capture._git(root, *args, check=False).returncode != 0:
                    return None
            if followups_capture._git(
                root,
                "ls-files",
                "--others",
                "--exclude-standard",
                "-z",
                "--",
                path,
            ).stdout:
                return None
            entries.append({"path": path, "mode": mode, "oid": oid})
        return head, entries
    except (followups_capture.CaptureError, fs_object_identity.ObjectIdentityError):
        return None


def _post_cas_semantic_identity_proof(
    *,
    root: Path,
    plan_ref: str,
    capture_cycle_id: str | None,
    semantic_fields: tuple[str, str, str],
    bundle_payload: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Derive the sole caller-selected staged-empty post-CAS witness.

    The first read is deliberately literal against the receipt-side identity.
    It independently reopens the receipt, host, frozen ordinary binding,
    durable rows and PI state before this derived caller can form an
    in-memory proof.  The reader receives the witness and repeats that work;
    this function never writes or treats empty deltas/reconciliation as proof.
    """

    if (
        not capture_cycle_id
        or bundle_payload is None
        or semantic_fields[0] not in {"Done", "Superseded"}
        or semantic_fields[1] != semantic_fields[0].lower()
        or semantic_fields[2] != "already_materialized"
    ):
        return None
    tree = _post_cas_bundle_tree_entries(
        root=root,
        plan_ref=plan_ref,
        bundle_payload=bundle_payload,
    )
    if tree is None:
        return None
    head, entries = tree
    receipt_fields = (semantic_fields[0], semantic_fields[1], "staged_empty")
    try:
        readback = followups_capture.read_capture(
            root,
            plan_ref,
            capture_cycle_id,
            semantic_fields=receipt_fields,
        )
        manifest_path = followups_capture.v2_frozen_manifest_path(root, plan_ref).resolve().relative_to(
            root.resolve()
        ).as_posix()
        _manifest_object, manifest_bytes = followups_capture.read_repo_regular_path(root, manifest_path)
        manifest = json.loads(manifest_bytes.decode("utf-8"))
        source_keys = {
            "source_terminal_commit_oid",
            "source_plan_blob_oid",
            "source_plan_sha256",
        }
        if (
            not isinstance(manifest, dict)
            or not source_keys.issubset(manifest)
            or any(not isinstance(manifest.get(key), str) for key in source_keys)
        ):
            return None
        values = {
            "route": followups_capture.POST_CAS_SEMANTIC_IDENTITY_TRANSITION_ROUTE,
            "plan_ref": plan_ref,
            "capture_cycle_id": capture_cycle_id,
            "receipt_content_sha256": readback["receipt_content_sha256"],
            "semantic_closeout_identity": readback["semantic_closeout_identity"],
            "plan_sha256": readback["plan_sha256"],
            "terminal_status_line": readback["terminal_status_line"],
            "receipt_semantic_fields": list(receipt_fields),
            "current_semantic_fields": list(semantic_fields),
            "source_terminal_commit_oid": manifest["source_terminal_commit_oid"],
            "source_plan_blob_oid": manifest["source_plan_blob_oid"],
            "source_plan_sha256": manifest["source_plan_sha256"],
            "frozen_manifest_path": manifest_path,
            "frozen_manifest_sha256": followups_capture._sha256(manifest_bytes),
            "pi_final_objects": readback["pi_final_objects"],
            "current_head": head,
            "bundle_tree_entries": entries,
        }
        if set(values) != followups_capture.POST_CAS_SEMANTIC_IDENTITY_PROOF_KEYS:
            return None
        return values
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, followups_capture.CaptureError):
        return None


def _is_protected_docs_path(path: str) -> bool:
    normalized = _normalize_repo_path(path)
    if not normalized.startswith("docs/"):
        return False
    if normalized in PROTECTED_DOCS_EXACT_PATHS:
        return True
    if normalized.startswith(PROTECTED_DOCS_PREFIXES):
        return True
    basename = Path(normalized).name
    return basename.startswith("_template") and basename.endswith(".md")


def _unowned_protected_docs_paths(docs_paths: list[str], bundle_payload: dict[str, Any]) -> list[str]:
    explicit_scope = _bundle_scope_paths(bundle_payload)
    return [
        path
        for path in docs_paths
        if _is_protected_docs_path(path) and _normalize_repo_path(path) not in explicit_scope
    ]


def _terminal_immutable_docs_paths(plan_ref: str) -> set[str]:
    normalized_plan_ref = _normalize_repo_path(plan_ref)
    stem = Path(normalized_plan_ref).stem
    return {
        normalized_plan_ref,
        f"docs/code_drafts/{stem}__code_draft.md",
        f"docs/code_reviews/{stem}.md",
        f"docs/doc_reviews/{stem}.md",
    }


def _terminal_protected_docs_delta_paths(
    *,
    root: Path,
    plan_ref: str,
    status_norm: str,
    docs_status_snapshot: tuple[list[str], bool] | None = None,
) -> tuple[list[str], bool]:
    """Return terminal protected delta plus whether the Git docs proof was readable."""
    if status_norm not in TERMINAL_STATUSES:
        return [], True
    docs_paths, ok = (
        docs_status_snapshot
        if docs_status_snapshot is not None
        else _git_status_docs_paths(root)
    )
    if not ok:
        return [], False
    terminal_artifacts = _terminal_immutable_docs_paths(plan_ref)
    return (
        [
            path
            for path in docs_paths
            if _is_protected_docs_path(path)
            or _normalize_repo_path(path) in terminal_artifacts
        ],
        True,
    )


def classify_final_docs_commit(
    *,
    root: Path,
    state: str,
    bundle_payload: dict[str, Any],
    current_plan_owned_docs_paths: list[str] | None = None,
    docs_status_snapshot: tuple[list[str], bool] | None = None,
) -> dict[str, Any]:
    if state != "completed":
        return {
            "final_docs_commit": "no_op",
            "final_docs_commit_reason": "docs_closeout_not_completed",
            "final_docs_diff_paths": [],
            "protected_docs_delta_paths": [],
        }

    explicit_raw = _clean_value(str(bundle_payload.get("final_docs_commit") or ""))
    if explicit_raw:
        explicit = explicit_raw.lower()
        if explicit in FINAL_DOCS_COMMIT_VALUES:
            return {
                "final_docs_commit": explicit,
                "final_docs_commit_reason": "explicit_bundle_payload",
                "final_docs_diff_paths": [],
                "protected_docs_delta_paths": [],
            }
        return {
            "final_docs_commit": "no_op",
            "final_docs_commit_reason": f"unsupported_final_docs_commit:{explicit_raw}",
            "final_docs_diff_paths": [],
            "protected_docs_delta_paths": [],
        }

    docs_paths, ok = (
        docs_status_snapshot
        if docs_status_snapshot is not None
        else _git_status_docs_paths(root)
    )
    if not ok:
        return {
            "final_docs_commit": "no_op",
            "final_docs_commit_reason": "docs_delta_unknown",
            "final_docs_diff_paths": [],
            "protected_docs_delta_paths": [],
        }
    if docs_paths:
        protected_paths = _unowned_protected_docs_paths(docs_paths, bundle_payload)
        proven_owned_paths = {
            _normalize_repo_path(path)
            for path in (current_plan_owned_docs_paths or [])
            if isinstance(path, str) and path.strip()
        }
        owned_paths = sorted(
            path
            for path in docs_paths
            if _normalize_repo_path(path) in _bundle_scope_paths(bundle_payload)
            or _normalize_repo_path(path) in proven_owned_paths
        )
        if not owned_paths and not protected_paths:
            return {
                "final_docs_commit": "no_op",
                "final_docs_commit_reason": "no_current_plan_owned_docs_delta",
                "final_docs_diff_paths": [],
                "protected_docs_delta_paths": [],
            }
        return {
            "final_docs_commit": "required",
            "final_docs_commit_reason": "canon_delta_requires_process_improvement"
            if protected_paths
            else "docs_delta_present",
            "final_docs_diff_paths": (
                sorted(set(owned_paths) | set(protected_paths)) if protected_paths else owned_paths
            ),
            "protected_docs_delta_paths": protected_paths,
        }
    return {
        "final_docs_commit": "no_op",
        "final_docs_commit_reason": "no_net_docs_diff",
        "final_docs_diff_paths": [],
        "protected_docs_delta_paths": [],
    }


def _load_process_improvement_receipt(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Process-improvement capture receipt is not a JSON object: {path}")
    return payload


def _repo_path_is_lexically_missing(root: Path, rel_path: str) -> bool:
    """Distinguish a missing expected receipt from an unsafe lexical component."""
    current = root.absolute()
    parts = Path(rel_path).parts
    for index, part in enumerate(parts):
        current = current / part
        try:
            entry = current.lstat()
        except FileNotFoundError:
            return True
        if stat.S_ISLNK(entry.st_mode) or (index < len(parts) - 1 and not stat.S_ISDIR(entry.st_mode)):
            return False
    return False


def classify_process_improvement_capture(
    root: Path,
    plan_ref: str,
    *,
    capture_cycle_id: str | None = None,
) -> dict[str, Any]:
    expected_dir = process_improvements_collect.capture_receipt_dir_rel_path(
        plan_ref,
        capture_cycle_id,
    ).as_posix()
    receipts: list[dict[str, Any]] = []
    receipt_paths: list[str] = []
    missing_roles: list[str] = []
    invalid_errors: list[str] = []
    backlog_paths: set[str] = set()

    for role in PI_CAPTURE_ROLES:
        rel_path = process_improvements_collect.capture_receipt_rel_path(
            plan_ref,
            role,
            capture_cycle_id,
        )
        path = root / rel_path
        try:
            if capture_cycle_id:
                _object_identity, data = followups_capture.read_repo_regular_path(root, rel_path.as_posix())
                receipt = json.loads(data.decode("utf-8"))
                if not isinstance(receipt, dict):
                    raise ValueError("Process-improvement capture receipt is not a JSON object")
            else:
                if not path.exists():
                    missing_roles.append(role)
                    continue
                receipt = _load_process_improvement_receipt(path)
        except Exception as exc:
            if capture_cycle_id and _repo_path_is_lexically_missing(root, rel_path.as_posix()):
                missing_roles.append(role)
                continue
            invalid_errors.append(f"{rel_path.as_posix()}: {exc}")
            continue

        if receipt.get("source_ref") != plan_ref:
            invalid_errors.append(f"{rel_path.as_posix()}: source_ref mismatch")
            continue
        if str(receipt.get("role") or "").lower() != role.lower():
            invalid_errors.append(f"{rel_path.as_posix()}: role mismatch")
            continue
        state = str(receipt.get("capture_state") or "")
        if state not in PI_CAPTURE_CONTINUATION_STATES and state != "blocked":
            invalid_errors.append(f"{rel_path.as_posix()}: unsupported capture_state={state!r}")
            continue
        if capture_cycle_id:
            if receipt.get("receipt_schema") != process_improvements_collect.CAPTURE_RECEIPT_V2_SCHEMA:
                invalid_errors.append(f"{rel_path.as_posix()}: receipt schema is not v2")
                continue
            if receipt.get("followups_capture_cycle_id") != capture_cycle_id:
                invalid_errors.append(f"{rel_path.as_posix()}: followups capture cycle mismatch")
                continue
            input_sha256 = receipt.get("input_sha256")
            if not isinstance(input_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", input_sha256):
                invalid_errors.append(f"{rel_path.as_posix()}: input_sha256 is invalid")
                continue
            required_chain_fields = {
                "before_process_improvement_files",
                "after_process_improvement_files",
                "process_improvement_path_results",
            }
            missing_chain_fields = sorted(required_chain_fields.difference(receipt))
            if missing_chain_fields:
                invalid_errors.append(
                    f"{rel_path.as_posix()}: missing object-chain fields={','.join(missing_chain_fields)}"
                )
                continue
        elif receipt.get("receipt_schema") != process_improvements_collect.CAPTURE_RECEIPT_V1_SCHEMA:
            invalid_errors.append(f"{rel_path.as_posix()}: receipt schema is not legacy v1")
            continue
        for raw_path in receipt.get("backlog_paths") or []:
            if isinstance(raw_path, str) and raw_path.strip():
                backlog_paths.add(raw_path.strip())
        receipts.append(receipt)
        receipt_paths.append(rel_path.as_posix())

    if (
        capture_cycle_id
        and not invalid_errors
        and receipts
        and not missing_roles
        and all(item.get("capture_state") != "blocked" for item in receipts)
    ):
        try:
            followups_capture.general_pi_capture_receipts_proof(root, plan_ref, capture_cycle_id)
        except followups_capture.CaptureError as exc:
            invalid_errors.append(f"current-cycle general PI receipt proof: {exc.reason_code}")

    if invalid_errors:
        return {
            "process_improvement_capture_state": "blocked",
            "process_improvement_capture_reason": "invalid_capture_receipt",
            "process_improvement_capture_roles": [str(item.get("role") or "unknown") for item in receipts],
            "process_improvement_backlog_paths": sorted(backlog_paths),
            "process_improvement_receipt_path": expected_dir,
            "process_improvement_receipt_paths": receipt_paths,
            "process_improvement_missing_roles": missing_roles,
            "process_improvement_capture_errors": invalid_errors,
        }

    blocked = [item for item in receipts if item.get("capture_state") == "blocked"]
    if blocked:
        first = blocked[0]
        return {
            "process_improvement_capture_state": "blocked",
            "process_improvement_capture_reason": str(first.get("reason_code") or "collector_blocked"),
            "process_improvement_capture_roles": [str(item.get("role") or "unknown") for item in receipts],
            "process_improvement_backlog_paths": sorted(backlog_paths),
            "process_improvement_receipt_path": expected_dir,
            "process_improvement_receipt_paths": receipt_paths,
            "process_improvement_missing_roles": missing_roles,
            "process_improvement_capture_errors": [str(first.get("error") or "collector blocked")],
        }

    if not receipts or missing_roles:
        return {
            "process_improvement_capture_state": "pending",
            "process_improvement_capture_reason": "awaiting_general_docs_finalize_capture",
            "process_improvement_capture_roles": [str(item.get("role") or "unknown") for item in receipts],
            "process_improvement_backlog_paths": sorted(backlog_paths),
            "process_improvement_receipt_path": expected_dir,
            "process_improvement_receipt_paths": receipt_paths,
            "process_improvement_missing_roles": missing_roles,
            "process_improvement_capture_errors": [],
        }

    states = {str(item.get("capture_state")) for item in receipts}
    if "materialized" in states:
        state = "materialized"
        reason = "process_improvements_materialized"
    elif "already_tracked" in states:
        state = "already_tracked"
        reason = "process_improvements_already_tracked"
    else:
        state = "clean_noop"
        reason = "all_roles_clean_noop"

    return {
        "process_improvement_capture_state": state,
        "process_improvement_capture_reason": reason,
        "process_improvement_capture_roles": [str(item.get("role") or "unknown") for item in receipts],
        "process_improvement_backlog_paths": sorted(backlog_paths),
        "process_improvement_receipt_path": expected_dir,
        "process_improvement_receipt_paths": receipt_paths,
        "process_improvement_missing_roles": [],
        "process_improvement_capture_errors": [],
    }


def _process_improvement_tail_paths(
    *,
    root: Path,
    plan_ref: str,
    pi_capture: dict[str, Any],
    docs_status_snapshot: tuple[list[str], bool] | None = None,
) -> dict[str, Any]:
    """Return same-plan PI tail paths only when lineage and generated surfaces are proven."""
    capture_state = pi_capture.get("process_improvement_capture_state")
    if capture_state not in {"materialized", "already_tracked"}:
        return {"ok": False, "reason": "pi_capture_not_materialized", "paths": []}

    docs_paths, status_ok = (
        docs_status_snapshot
        if docs_status_snapshot is not None
        else _git_status_docs_paths(root)
    )
    if not status_ok:
        return {"ok": False, "reason": "docs_delta_unknown", "paths": []}
    dirty_paths = {_normalize_repo_path(path) for path in docs_paths}
    if not dirty_paths:
        return {"ok": False, "reason": "no_docs_delta", "paths": []}

    expected_backlog = _normalize_repo_path(process_improvements_collect.backlog_rel_path_for_source_ref(plan_ref))
    receipt_backlogs = {
        _normalize_repo_path(path)
        for path in pi_capture.get("process_improvement_backlog_paths") or []
        if isinstance(path, str) and path.strip()
    }
    if receipt_backlogs != {expected_backlog}:
        return {"ok": False, "reason": "pi_backlog_path_mismatch", "paths": sorted(dirty_paths)}
    if expected_backlog not in dirty_paths:
        return {"ok": False, "reason": "current_plan_backlog_not_dirty", "paths": sorted(dirty_paths)}

    backlog_path = root / expected_backlog
    try:
        backlog = process_improvements_collect.parse_backlog_file(backlog_path, root)
    except Exception as exc:
        return {"ok": False, "reason": f"pi_backlog_unreadable:{exc}", "paths": sorted(dirty_paths)}
    if backlog.source_ref != plan_ref:
        return {"ok": False, "reason": "pi_backlog_source_ref_mismatch", "paths": sorted(dirty_paths)}

    allowed_paths = {expected_backlog, *PI_DERIVED_SURFACE_PATHS}
    unexpected_paths = dirty_paths - allowed_paths
    if unexpected_paths:
        return {"ok": False, "reason": "unexpected_docs_delta_paths", "paths": sorted(dirty_paths)}

    derived_check = process_improvements_collect.check_derived_surfaces(root)
    if not derived_check.get("ok"):
        return {"ok": False, "reason": "derived_surfaces_not_fresh", "paths": sorted(dirty_paths)}

    return {"ok": True, "reason": "same_plan_process_improvement_tail", "paths": sorted(dirty_paths)}


def _current_plan_pi_owned_paths(
    *,
    root: Path,
    plan_ref: str,
    pi_capture: dict[str, Any],
    dirty_paths: set[str],
    capture: dict[str, Any] | None,
) -> tuple[set[str], set[str]]:
    """Return proven same-plan PI paths and malformed same-plan candidates."""
    if pi_capture.get("process_improvement_capture_state") not in {"materialized", "already_tracked"}:
        return set(), set()
    expected = _normalize_repo_path(process_improvements_collect.backlog_rel_path_for_source_ref(plan_ref))
    candidate_dirty = dirty_paths & ({expected} | PI_DERIVED_SURFACE_PATHS)
    if capture is None:
        return set(), candidate_dirty
    if expected not in dirty_paths:
        return set(), set()
    foreign_backlogs = {
        path
        for path in dirty_paths
        if path.startswith("docs/process_improvements/")
        and path.endswith("__process_improvements_backlog.md")
        and path != expected
    }
    if foreign_backlogs:
        return set(), candidate_dirty
    try:
        backlog = process_improvements_collect.parse_backlog_file(root / expected, root)
    except Exception:
        return set(), candidate_dirty
    if backlog.source_ref != plan_ref:
        return set(), candidate_dirty
    try:
        proof = followups_capture.process_improvement_staging_proof(
            root,
            plan_ref,
            capture_binding=capture,
        )
    except followups_capture.CaptureError:
        return set(), candidate_dirty
    if proof.get("backlog_path") != expected:
        return set(), candidate_dirty
    final_objects = proof["cycle_proof"]["pi_final_objects"]
    if expected not in final_objects:
        return set(), candidate_dirty
    try:
        derived = process_improvements_collect.check_derived_surfaces(root)
    except Exception:
        return set(), candidate_dirty
    owned = {expected}
    derived_dirty = dirty_paths & PI_DERIVED_SURFACE_PATHS
    if not derived.get("ok") or not derived_dirty.issubset(set(final_objects)):
        return set(), candidate_dirty
    owned.update(derived_dirty)
    return owned, set()


def _ordinary_path_source_refs(root: Path, rel_path: str) -> tuple[set[str], str | None]:
    try:
        _object, data = followups_capture.read_followup_path(root, rel_path)
        text = data.decode("utf-8")
        import followups_lint

        followup = followups_lint.parse_followup_text(text, rel_path, root / rel_path)
        findings = followups_lint.lint_followup_files([followup], root)
        if findings:
            return set(), "followup_capture_lint_failed"
        active = [item for item in followup.items if item.status in {"open", "promoted", "unconfirmed"}]
        refs = {str(item.fields.get("source_ref") or "").strip() for item in active}
        if not active or "" in refs:
            return refs - {""}, "followup_capture_source_ref_missing"
        return refs, None
    except (UnicodeDecodeError, followups_capture.CaptureError):
        return set(), "followup_capture_path_unsafe"


def _is_v2_followup_candidate(root: Path, rel_path: str) -> bool:
    """Identify an already-materialized V2 carrier without granting it ownership."""

    try:
        _object, data = followups_capture.read_followup_path(root, rel_path)
        text = data.decode("utf-8")
        followup = followups_lint.parse_followup_text(text, rel_path, root / rel_path)
        schema_class, _findings = followups_lint.classify_followups_schema_version(followup)
        return schema_class == "v2"
    except (UnicodeDecodeError, followups_capture.CaptureError):
        return False


def classify_followups_capture(
    *,
    root: Path,
    plan_ref: str,
    capture_cycle_id: str | None,
    semantic_fields: tuple[str, str, str],
    pi_capture: dict[str, Any],
    bundle_payload: dict[str, Any] | None = None,
    docs_status_snapshot: tuple[list[str], bool] | None = None,
) -> dict[str, Any]:
    docs_paths, status_ok = (
        docs_status_snapshot
        if docs_status_snapshot is not None
        else _git_status_docs_paths(root)
    )
    dirty_paths = {_normalize_repo_path(path) for path in docs_paths}
    if not status_ok:
        return {
            "followups_capture_state": "blocked",
            "followups_capture_reason": "docs_delta_unknown",
            "followups_capture_cycle_id": capture_cycle_id or "none",
            "followups_capture_receipt_path": "none",
            "followups_capture_roles": [],
            "current_plan_owned_docs_delta_paths": [],
            "foreign_docs_delta_paths": [],
            "blocked_docs_delta_paths": [],
            "followups_staging_expectations": [],
            "capture_readback": None,
        }
    if not capture_cycle_id:
        bundle_scope = _bundle_scope_paths(bundle_payload or {})
        owned = {
            path
            for path in dirty_paths
            if path in bundle_scope
        }
        pi_tail = _process_improvement_tail_paths(
            root=root,
            plan_ref=plan_ref,
            pi_capture=pi_capture,
            docs_status_snapshot=docs_status_snapshot,
        )
        if pi_tail["ok"]:
            owned.update(pi_tail["paths"])
        return {
            "followups_capture_state": "clean_noop",
            "followups_capture_reason": "capture_cycle_not_requested",
            "followups_capture_cycle_id": "none",
            "followups_capture_receipt_path": "none",
            "followups_capture_roles": [],
            "current_plan_owned_docs_delta_paths": sorted(owned),
            "foreign_docs_delta_paths": sorted(dirty_paths - owned),
            "blocked_docs_delta_paths": [],
            "followups_staging_expectations": [],
            "capture_readback": None,
        }

    capture: dict[str, Any] | None = None
    pending_index_transition = False
    capture_reason = "capture_materialized"
    capture_blocked_paths: set[str] = set()
    try:
        post_cas_proof = _post_cas_semantic_identity_proof(
            root=root,
            plan_ref=plan_ref,
            capture_cycle_id=capture_cycle_id,
            semantic_fields=semantic_fields,
            bundle_payload=bundle_payload,
        )
        capture = followups_capture.read_capture(
            root,
            plan_ref,
            capture_cycle_id,
            semantic_fields=semantic_fields,
            _post_cas_semantic_identity_proof=post_cas_proof,
            _include_pending_transition=True,
        )
        pending_index_transition = capture.pop("_pending_index_transition", False)
    except followups_capture.CaptureError as exc:
        capture_reason = exc.reason_code
        for key in ("path", "paths", "changed_paths", "declared_paths"):
            value = exc.details.get(key)
            if isinstance(value, str):
                capture_blocked_paths.add(_normalize_repo_path(value))
            elif isinstance(value, list):
                capture_blocked_paths.update(_normalize_repo_path(str(item)) for item in value)

    if capture is not None and capture.get("general_pi_checkpoint") is None:
        capture = None
        capture_reason = "followup_capture_pi_general_checkpoint_legacy"
    if capture is not None and pi_capture.get("process_improvement_capture_state") == "blocked":
        capture = None
        capture_reason = str(pi_capture.get("process_improvement_capture_reason") or "invalid_capture_receipt")

    owned: set[str] = set()
    expectations: list[dict[str, Any]] = []
    roles: list[str] = []
    receipt_path = "none"
    if capture is not None:
        owned.update(path for path in capture["created_paths"] if path in dirty_paths)
        expectations = [
            item
            for item in capture["staging_expectations"]
            if item.get("path") in dirty_paths
        ]
        roles = list(capture["completed_roles"])
        receipt_path = str(capture["receipt_path"])

    pi_owned, pi_blocked = _current_plan_pi_owned_paths(
        root=root,
        plan_ref=plan_ref,
        pi_capture=pi_capture,
        dirty_paths=dirty_paths,
        capture=capture,
    )
    if capture is not None and pi_owned:
        try:
            expectations.extend(
                followups_capture.process_improvement_staging_expectations(
                    root,
                    plan_ref,
                    sorted(pi_owned),
                    capture_binding=capture,
                )
            )
            owned.update(pi_owned)
        except followups_capture.CaptureError:
            pi_blocked.update(pi_owned)

    v2_proof_blocked = False
    v2_proof_blocked_paths: set[str] = set()
    if capture is not None:
        remaining_followups = {
            path
            for path in dirty_paths - owned - pi_blocked - capture_blocked_paths
            if path.startswith("docs/followups/")
        }
        manifest_hint = os.path.lexists(followups_capture.v2_frozen_manifest_path(root, plan_ref))
        v2_candidates = {
            path
            for path in remaining_followups
            if _is_v2_followup_candidate(root, path)
        }
        # A malformed or unsafe expected carrier may no longer be parseable as
        # V2.  A canonical manifest hint still makes every remaining follow-up
        # path fail through the V2 proof rather than accidentally inheriting PI
        # ownership.
        if v2_candidates or (manifest_hint and remaining_followups):
            try:
                v2_expectations = followups_capture.v2_external_followup_staging_expectations(
                    root,
                    plan_ref,
                    capture_binding=capture,
                )
                derived_paths = {str(expectation["path"]) for expectation in v2_expectations}
                already_owned_followups = {
                    path for path in owned if path.startswith("docs/followups/")
                }
                transaction_paths = derived_paths
                available_transaction_paths = remaining_followups | already_owned_followups
                if v2_candidates - derived_paths:
                    v2_proof_blocked = True
                    v2_proof_blocked_paths.update(v2_candidates - derived_paths)
                elif not transaction_paths.issubset(available_transaction_paths):
                    # The raw carrier and its generated index form one exact
                    # terminal tree transaction.  A stale status snapshot or
                    # index-only delta must not stage just a projection.
                    v2_proof_blocked = True
                    v2_proof_blocked_paths.update(transaction_paths & remaining_followups)
                else:
                    for expectation in v2_expectations:
                        path = expectation["path"]
                        if path in remaining_followups:
                            expectations.append(expectation)
                            owned.add(path)
            except followups_capture.CaptureError:
                v2_proof_blocked = True
                v2_proof_blocked_paths.update(v2_candidates or remaining_followups)
    blocked = set(capture_blocked_paths) | set(pi_blocked) | v2_proof_blocked_paths
    foreign: set[str] = set()

    for path in sorted(dirty_paths - owned - blocked):
        if path == plan_ref:
            blocked.add(path)
            continue
        if path.startswith("docs/followups/"):
            try:
                followups_capture.validate_followup_relpath(path)
            except followups_capture.CaptureError:
                blocked.add(path)
                continue
            refs, error = _ordinary_path_source_refs(root, path)
            if error or len(refs) != 1:
                blocked.add(path)
            elif refs == {plan_ref}:
                blocked.add(path)  # same-plan row without exact current-cycle receipt
            else:
                foreign.add(path)
            continue
        if path.startswith("docs/process_improvements/") and path == _normalize_repo_path(
            process_improvements_collect.backlog_rel_path_for_source_ref(plan_ref)
        ):
            blocked.add(path)
            continue
        foreign.add(path)

    if capture is None:
        blocked.update(
            path
            for path in dirty_paths
            if path.startswith("docs/followups/") and path not in foreign
        )
    state = "blocked" if capture is None or blocked else ("materialized" if owned else "clean_noop")
    reason = (
        capture_reason
        if capture is None
        else (
            "missing_or_mismatched_v2_tuple_proof"
            if v2_proof_blocked
            else ("capture_owned_delta" if owned else "capture_finalized_noop")
        )
    )
    closing_expectations = [] if state == "blocked" else sorted(expectations, key=lambda item: item["path"])
    return {
        "followups_capture_state": state,
        "followups_capture_reason": reason,
        "followups_capture_cycle_id": capture_cycle_id,
        "followups_capture_receipt_path": receipt_path,
        "followups_capture_roles": roles,
        "current_plan_owned_docs_delta_paths": sorted(owned),
        "foreign_docs_delta_paths": sorted(foreign),
        "blocked_docs_delta_paths": sorted(blocked),
        "followups_staging_expectations": closing_expectations,
        "capture_readback": capture,
        "_pending_index_transition": pending_index_transition,
    }


def _empty_process_improvement_advisory_counts() -> dict[str, int]:
    return {
        "backlog_files": 0,
        "rows_total": 0,
        "advisory_rows": 0,
        "open": 0,
        "triaged": 0,
        "promoted": 0,
        "deferred": 0,
        "unconfirmed": 0,
        "null_execution_rows": 0,
        "delivery_ref_rows": 0,
    }


def classify_process_improvement_advisory(root: Path) -> dict[str, Any]:
    """Summarize raw PI backlog rows for readback without changing closeout gates."""
    backlog_paths = process_improvements_collect.iter_backlog_paths(root)
    counts = _empty_process_improvement_advisory_counts()
    counts["backlog_files"] = len(backlog_paths)
    source_paths = [_root_relative(path, root) for path in backlog_paths]
    errors: list[str] = []

    for path in backlog_paths:
        rel_path = _root_relative(path, root)
        try:
            backlog = process_improvements_collect.parse_backlog_file(path, root)
        except Exception as exc:
            errors.append(f"{rel_path}: {exc}")
            continue
        for entry in backlog.entries:
            counts["rows_total"] += 1
            status = entry.status
            if status in PI_ADVISORY_STATUSES:
                counts["advisory_rows"] += 1
                counts[status] += 1
            if entry.execution_kind == "null" or entry.execution_ref == "null":
                counts["null_execution_rows"] += 1
            if entry.delivery_refs != "null":
                counts["delivery_ref_rows"] += 1

    if errors:
        state = "unknown"
        reason = "backlog_parse_error"
    elif counts["advisory_rows"]:
        state = "advisory_backlog"
        reason = "open_process_improvement_rows"
    elif backlog_paths:
        state = "clean_noop"
        reason = "no_advisory_rows"
    else:
        state = "clean_noop"
        reason = "no_backlog_files"

    return {
        "schema": PI_ADVISORY_SCHEMA,
        "process_improvement_advisory_state": state,
        "process_improvement_advisory_reason": reason,
        "process_improvement_advisory_counts": counts,
        "process_improvement_advisory_proof_host": "docs/process_improvements/*__process_improvements_backlog.md",
        "process_improvement_advisory_backlog_paths": source_paths,
        "process_improvement_advisory_errors": errors,
    }


def _followups_blocked_predecessor_recovery_payload(
    *,
    plan_ref: str,
    state: str,
    reason: str,
    identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if state not in FOLLOWUPS_BLOCKED_PREDECESSOR_RECOVERY_ADMISSION_STATES:
        raise ValueError(f"unsupported blocked predecessor recovery state: {state}")
    if reason not in FOLLOWUPS_BLOCKED_PREDECESSOR_RECOVERY_ADMISSION_REASONS:
        raise ValueError(f"unsupported blocked predecessor recovery reason: {reason}")
    proof = identity or {}
    return {
        "schema": FOLLOWUPS_BLOCKED_PREDECESSOR_RECOVERY_ADMISSION_SCHEMA,
        "state": state,
        "reason": reason,
        "plan_ref": plan_ref,
        "semantic_closeout_identity": proof.get("semantic_closeout_identity"),
        "source_terminal_commit_oid": proof.get("source_terminal_commit_oid"),
        "source_plan_blob_oid": proof.get("source_plan_blob_oid"),
        "source_plan_sha256": proof.get("source_plan_sha256"),
        "transaction_host_identity": proof.get("transaction_host_identity"),
        "predecessor_capture_cycle_id": proof.get("predecessor_capture_cycle_id"),
        "predecessor_receipt_object_identity": proof.get("predecessor_receipt_object_identity"),
        "predecessor_receipt_sha256": proof.get("predecessor_receipt_sha256"),
        "general_pi_checkpoint_sha256": proof.get("general_pi_checkpoint_sha256"),
        "process_improvement_after_map_sha256": proof.get("process_improvement_after_map_sha256"),
    }


def _followups_blocked_predecessor_recovery_profile(plan_ref: str) -> dict[str, str] | None:
    """Return one test-injected recovery profile, or explicit no-applicability."""

    registry = followups_capture.BLOCKED_PREDECESSOR_RECOVERY_PROFILES
    required = {
        "plan_ref",
        "predecessor_capture_cycle_id",
        "source_terminal_commit_oid",
        "source_plan_blob_oid",
        "source_plan_sha256",
        "predecessor_receipt_sha256",
    }
    if not isinstance(registry, dict):
        raise ValueError("blocked predecessor recovery profile registry is malformed")
    if plan_ref not in registry:
        return None
    profile = registry[plan_ref]
    if (
        not isinstance(profile, dict)
        or set(profile) != required
        or any(not isinstance(profile.get(key), str) or not profile[key] for key in required)
        or profile.get("plan_ref") != plan_ref
    ):
        raise ValueError("blocked predecessor recovery profile is malformed")
    return {key: str(profile[key]) for key in required}


def _followups_blocked_predecessor_cycle_has_marker(cycle_fd: int) -> bool:
    for entry in (
        followups_capture.ORDINARY_V2_BOUND_DIRECTORY,
        followups_capture.ORDINARY_V2_SUBMISSION_DIRECTORY,
    ):
        try:
            os.stat(entry, dir_fd=cycle_fd, follow_symlinks=False)
        except FileNotFoundError:
            continue
        except OSError:
            return True
        return True
    return False


def _followups_blocked_predecessor_topology(
    root: Path,
    *,
    plan_ref: str,
    host: followups_capture.CaptureHost,
    cycle_id: str,
    receipt: dict[str, Any],
    raw: bytes,
    receipt_identity: dict[str, Any],
    cycle_identity: dict[str, Any],
    source: dict[str, str],
    profile: dict[str, str],
) -> tuple[dict[str, Any] | None, str | None]:
    """Prove the one fixed failed pre-bind shape without normalizing it."""

    if cycle_id != profile["predecessor_capture_cycle_id"]:
        return None, "recovery_predecessor_foreign"
    if followups_capture._sha256(raw) != profile["predecessor_receipt_sha256"]:
        return None, "recovery_predecessor_identity_drift"
    if (
        receipt.get("plan_ref") != plan_ref
        or receipt.get("plan_sha256") != source["source_plan_sha256"]
        or receipt.get("receipt_object_identity") != receipt_identity
        or receipt.get("cycle_directory_identity") != cycle_identity
        or receipt.get("transaction_host_identity") != host.transaction_host_identity()
    ):
        return None, "recovery_predecessor_identity_drift"
    identity_payload = receipt.get("identity_payload")
    if (
        not isinstance(identity_payload, dict)
        or receipt.get("semantic_closeout_identity") != followups_capture._semantic_identity(identity_payload)
        or identity_payload.get("plan_ref") != plan_ref
        or identity_payload.get("plan_sha256") != source["source_plan_sha256"]
        or identity_payload.get("terminal_status_line") != receipt.get("terminal_status_line")
        or identity_payload.get("required_roles") != list(followups_capture.REQUIRED_ROLES)
    ):
        return None, "recovery_predecessor_identity_drift"
    if (
        receipt.get("state") != "blocked"
        or receipt.get("reason_code") != "followup_capture_role_order_mismatch"
        or receipt.get("required_roles") != list(followups_capture.REQUIRED_ROLES)
        or receipt.get("completed_roles") != []
        or receipt.get("created_paths") != []
        or receipt.get("no_followups_roles") != []
        or receipt.get("blocked_roles") != ["Coder"]
        or receipt.get("retry_of_capture_cycle_id") is not None
        or receipt.get("pi_lineage_root_cycle_id") != cycle_id
        or receipt.get("pi_adopted_from_cycle_ids") != []
        or receipt.get("pi_ownership_state") != "blocked"
        or receipt.get("pi_final_objects") != {}
        or receipt.get("pi_failure_checkpoint") is not None
        or receipt.get(followups_capture.ORDINARY_V2_BINDING_KEY) is not None
        or receipt.get(followups_capture.BLOCKED_PREDECESSOR_RECOVERY_BINDING_KEY) is not None
        or receipt.get("baseline_dirty_process_improvement_paths") != []
        or receipt.get("current_followup_files") != receipt.get("baseline_followup_files")
    ):
        return None, "recovery_predecessor_topology_invalid"
    role_results = receipt.get("role_results")
    if not isinstance(role_results, dict) or set(role_results) != {"Architect", "Coder"}:
        return None, "recovery_predecessor_topology_invalid"
    architect = role_results.get("Architect")
    coder = role_results.get("Coder")
    if (
        not isinstance(architect, dict)
        or architect.get("role") != "Architect"
        or architect.get("state") != "prepared"
        or architect.get("reason_code") != "role_prepared"
        or not isinstance(coder, dict)
        or coder.get("role") != "Coder"
        or coder.get("state") != "blocked"
        or coder.get("reason_code") != "followup_capture_role_order_mismatch"
        or coder.get("role_output_kind") is not None
    ):
        return None, "recovery_predecessor_topology_invalid"
    try:
        lineage = followups_capture._receipt_pi_lineage(receipt)
        checkpoint = followups_capture._validate_general_pi_checkpoint_marker(
            receipt.get("general_pi_checkpoint"),
            plan_ref=plan_ref,
            capture_cycle_id=cycle_id,
            current_objects=lineage["current_objects"],
        )
    except followups_capture.CaptureError:
        return None, "recovery_predecessor_checkpoint_invalid"
    if checkpoint is None or (
        checkpoint["before_process_improvement_files"] != receipt.get("baseline_process_improvement_files")
        or architect.get("prepared_process_improvement_files") != checkpoint["after_process_improvement_files"]
        or lineage["current_objects"] != checkpoint["after_process_improvement_files"]
    ):
        return None, "recovery_predecessor_checkpoint_invalid"
    try:
        live_pi = followups_capture.snapshot_process_improvement_data_files(root, plan_ref)
    except followups_capture.CaptureError:
        return None, "recovery_predecessor_pi_drift"
    if live_pi != checkpoint["after_process_improvement_files"]:
        return None, "recovery_predecessor_pi_drift"
    return {
        "semantic_closeout_identity": receipt["semantic_closeout_identity"],
        "source_terminal_commit_oid": source["source_terminal_commit_oid"],
        "source_plan_blob_oid": source["source_plan_blob_oid"],
        "source_plan_sha256": source["source_plan_sha256"],
        "transaction_host_identity": host.transaction_host_identity(),
        "predecessor_capture_cycle_id": cycle_id,
        "predecessor_receipt_sha256": followups_capture._sha256(raw),
        "general_pi_checkpoint_sha256": followups_capture._sha256(followups_capture._canonical_json_bytes(checkpoint)),
        "process_improvement_after_map_sha256": followups_capture._sha256(
            followups_capture._canonical_json_bytes(checkpoint["after_process_improvement_files"])
        ),
    }, None


def classify_followups_blocked_predecessor_recovery(root: Path, plan_ref: str) -> dict[str, Any]:
    """Classify a test-injected failed predecessor before ordinary bootstrap."""

    root = root.absolute()
    try:
        normalized_plan_ref = followups_capture.normalize_plan_ref(plan_ref)
        profile = _followups_blocked_predecessor_recovery_profile(normalized_plan_ref)
    except (ValueError, followups_capture.CaptureError):
        return _followups_blocked_predecessor_recovery_payload(
            plan_ref=str(plan_ref), state="blocked", reason="recovery_source_identity_invalid"
        )
    if profile is None:
        return _followups_blocked_predecessor_recovery_payload(
            plan_ref=normalized_plan_ref, state="not_applicable", reason="no_blocked_predecessor"
        )
    source, source_reason = _followups_bootstrap_source_identity(root, normalized_plan_ref)
    expected_source = {
        "plan_ref": normalized_plan_ref,
        "source_terminal_commit_oid": profile["source_terminal_commit_oid"],
        "source_plan_blob_oid": profile["source_plan_blob_oid"],
        "source_plan_sha256": profile["source_plan_sha256"],
    }
    if source_reason is not None or source != expected_source:
        return _followups_blocked_predecessor_recovery_payload(
            plan_ref=normalized_plan_ref, state="blocked", reason="recovery_source_identity_invalid"
        )
    family_rel = f".tmp/followups_capture/{followups_capture.plan_stem(normalized_plan_ref)}"
    family_path = root / family_rel
    if not path_components_are_symlink_free(root, family_rel):
        return _followups_blocked_predecessor_recovery_payload(
            plan_ref=normalized_plan_ref, state="blocked", reason="recovery_capture_path_unsafe"
        )
    try:
        family_stat = family_path.lstat()
    except FileNotFoundError:
        return _followups_blocked_predecessor_recovery_payload(
            plan_ref=normalized_plan_ref, state="not_applicable", reason="no_blocked_predecessor"
        )
    except OSError:
        return _followups_blocked_predecessor_recovery_payload(
            plan_ref=normalized_plan_ref, state="blocked", reason="recovery_capture_path_unsafe"
        )
    if not stat.S_ISDIR(family_stat.st_mode):
        return _followups_blocked_predecessor_recovery_payload(
            plan_ref=normalized_plan_ref, state="blocked", reason="recovery_capture_path_unsafe"
        )
    try:
        with followups_capture.CaptureHost(root, normalized_plan_ref) as host:
            candidates: list[tuple[str, dict[str, Any], bytes, dict[str, Any], dict[str, Any]]] = []
            for entry in sorted(os.listdir(host.family_fd)):
                if not followups_capture.UUID4_RE.fullmatch(entry):
                    continue
                cycle_fd = None
                try:
                    cycle_fd, cycle_identity = followups_capture._open_cycle(host, entry)
                    receipt, raw, receipt_identity = followups_capture._read_receipt(cycle_fd, normalized_plan_ref, entry)
                    if receipt.get(followups_capture.BLOCKED_PREDECESSOR_RECOVERY_BINDING_KEY) is not None:
                        return _followups_blocked_predecessor_recovery_payload(
                            plan_ref=normalized_plan_ref, state="blocked", reason="recovery_already_consumed"
                        )
                    if receipt.get("state") != "finalized":
                        candidates.append((entry, receipt, raw, receipt_identity, cycle_identity))
                except followups_capture.CaptureError:
                    return _followups_blocked_predecessor_recovery_payload(
                        plan_ref=normalized_plan_ref, state="blocked", reason="recovery_capture_invalid"
                    )
                finally:
                    if cycle_fd is not None:
                        os.close(cycle_fd)
            if not candidates:
                return _followups_blocked_predecessor_recovery_payload(
                    plan_ref=normalized_plan_ref, state="not_applicable", reason="no_blocked_predecessor"
                )
            if len(candidates) != 1:
                return _followups_blocked_predecessor_recovery_payload(
                    plan_ref=normalized_plan_ref, state="blocked", reason="recovery_predecessor_ambiguous"
                )
            entry, receipt, raw, receipt_identity, cycle_identity = candidates[0]
            cycle_fd, cycle_identity_now = followups_capture._open_cycle(host, entry)
            try:
                current, current_raw, current_identity = followups_capture._read_receipt(cycle_fd, normalized_plan_ref, entry)
                if (
                    current != receipt
                    or current_raw != raw
                    or current_identity != receipt_identity
                    or cycle_identity_now != cycle_identity
                ):
                    return _followups_blocked_predecessor_recovery_payload(
                        plan_ref=normalized_plan_ref, state="blocked", reason="recovery_predecessor_identity_drift"
                    )
                if _followups_blocked_predecessor_cycle_has_marker(cycle_fd):
                    return _followups_blocked_predecessor_recovery_payload(
                        plan_ref=normalized_plan_ref, state="blocked", reason="recovery_predecessor_marker_present"
                    )
                manifest = followups_capture.v2_frozen_manifest_path(root, normalized_plan_ref)
                if os.path.lexists(manifest):
                    return _followups_blocked_predecessor_recovery_payload(
                        plan_ref=normalized_plan_ref, state="blocked", reason="recovery_predecessor_manifest_present"
                    )
                details, reason = _followups_blocked_predecessor_topology(
                    root,
                    plan_ref=normalized_plan_ref,
                    host=host,
                    cycle_id=entry,
                    receipt=current,
                    raw=current_raw,
                    receipt_identity=current_identity,
                    cycle_identity=cycle_identity_now,
                    source=source,
                    profile=profile,
                )
                if reason is not None:
                    return _followups_blocked_predecessor_recovery_payload(
                        plan_ref=normalized_plan_ref, state="blocked", reason=reason
                    )
                assert details is not None
                st = os.stat(followups_capture.RECEIPT_NAME, dir_fd=cycle_fd, follow_symlinks=False)
                details["predecessor_receipt_object_identity"] = {
                    "path": current_identity["path"],
                    **followups_capture._followup_object(st, current_raw),
                }
                return _followups_blocked_predecessor_recovery_payload(
                    plan_ref=normalized_plan_ref,
                    state="ready",
                    reason="blocked_predecessor_recovery_ready",
                    identity=details,
                )
            finally:
                os.close(cycle_fd)
    except followups_capture.CaptureError:
        return _followups_blocked_predecessor_recovery_payload(
            plan_ref=normalized_plan_ref, state="blocked", reason="recovery_capture_path_unsafe"
        )


def _followups_bootstrap_admission_payload(
    *,
    plan_ref: str,
    manifest_path: Path,
    state: str,
    reason: str,
    source_identity: dict[str, str] | None = None,
) -> dict[str, Any]:
    if state not in FOLLOWUPS_BOOTSTRAP_ADMISSION_STATES:
        raise ValueError(f"unsupported bootstrap admission state: {state}")
    if reason not in FOLLOWUPS_BOOTSTRAP_ADMISSION_REASONS:
        raise ValueError(f"unsupported bootstrap admission reason: {reason}")
    source = source_identity or {}
    return {
        "schema": FOLLOWUPS_BOOTSTRAP_ADMISSION_SCHEMA,
        "state": state,
        "reason": reason,
        "plan_ref": plan_ref,
        "canonical_manifest_path": manifest_path.as_posix(),
        "source_terminal_commit_oid": source.get("source_terminal_commit_oid"),
        "source_plan_blob_oid": source.get("source_plan_blob_oid"),
        "source_plan_sha256": source.get("source_plan_sha256"),
    }


def _followups_bootstrap_source_identity(
    root: Path,
    plan_ref: str,
) -> tuple[dict[str, str] | None, str | None]:
    """Read one current ordinary-V2 terminal source without selecting history."""

    try:
        normalized_plan_ref = followups_capture.normalize_plan_ref(plan_ref)
        _object, worktree_bytes = followups_capture.read_repo_regular_path(root, normalized_plan_ref)
        plan_text = worktree_bytes.decode("utf-8")
        schema_class, _findings = plan_lint.classify_plan_schema_version(
            root / normalized_plan_ref,
            plan_text.splitlines(),
        )
        if schema_class != "v2":
            return None, "bootstrap_plan_schema_invalid"
        head = (
            followups_capture._git(root, "rev-parse", "--verify", "HEAD^{commit}")
            .stdout.decode("ascii", errors="replace")
            .strip()
        )
        blob = followups_capture._git(root, "rev-parse", "--verify", f"HEAD:{normalized_plan_ref}", check=False)
        if blob.returncode != 0:
            return None, "bootstrap_source_identity_invalid"
        source = followups_capture._v2_source_identity(
            root,
            normalized_plan_ref,
            head,
            blob.stdout.decode("ascii", errors="replace").strip(),
        )
        committed = followups_capture._git(root, "show", f"{head}:{normalized_plan_ref}").stdout
        if worktree_bytes != committed:
            return None, "bootstrap_source_identity_invalid"
        return source, None
    except (UnicodeDecodeError, followups_capture.CaptureError, OSError):
        return None, "bootstrap_source_identity_invalid"


def _followups_bootstrap_capture_reason(root: Path, plan_ref: str) -> str | None:
    """Return an exact fail-closed reason for current capture-family ambiguity."""

    family_rel = f".tmp/followups_capture/{followups_capture.plan_stem(plan_ref)}"
    family_path = root / family_rel
    if not path_components_are_symlink_free(root, family_rel):
        return "bootstrap_capture_path_unsafe"
    try:
        family_stat = family_path.lstat()
    except FileNotFoundError:
        return None
    except OSError:
        return "bootstrap_capture_path_unsafe"
    if not stat.S_ISDIR(family_stat.st_mode):
        return "bootstrap_capture_path_unsafe"

    active_count = 0
    try:
        with followups_capture.CaptureHost(root, plan_ref) as host:
            for entry in os.listdir(host.family_fd):
                if not followups_capture.UUID4_RE.fullmatch(entry):
                    continue
                cycle_fd = None
                try:
                    cycle_fd, _identity = followups_capture._open_cycle(host, entry)
                    receipt, _raw, _receipt_identity = followups_capture._read_receipt(cycle_fd, plan_ref, entry)
                except followups_capture.CaptureError:
                    return "bootstrap_capture_invalid"
                finally:
                    if cycle_fd is not None:
                        os.close(cycle_fd)
                if receipt.get("state") == "started":
                    active_count += 1
    except followups_capture.CaptureError:
        return "bootstrap_capture_path_unsafe"
    if active_count > 1:
        return "bootstrap_capture_ambiguous"
    if active_count == 1:
        return "bootstrap_capture_active"
    return None


def classify_followups_continuation_admission(
    root: Path, plan_ref: str, capture_cycle_id: str | None, *,
    bundle_payload: dict[str, Any], context: ContractContext | None = None,
) -> dict[str, Any]:
    """Read-only permission for the exact bridge before any followups progress.

    Fresh source identity is a current witness. It is never backfilled into the
    historical cycle receipt, which only persisted its semantic identity.
    """
    root = root.absolute()
    result: dict[str, Any] = {
        "schema": FOLLOWUPS_CONTINUATION_ADMISSION_SCHEMA,
        "state": "blocked" if capture_cycle_id else "not_applicable",
        "reason": "continuation_selector_absent", "plan_ref": plan_ref,
        "capture_cycle_id": capture_cycle_id, "phase": "pre_first_followups",
        "next_dispatch": None, "proof": None,
    }
    if not capture_cycle_id:
        return result

    def refuse(reason: str) -> dict[str, Any]:
        result["reason"] = reason
        return result

    try:
        plan_ref = followups_capture.normalize_plan_ref(plan_ref)
        followups_capture._validate_uuid4(capture_cycle_id)
        context = _reader_context(root, context)
        oracle = plan_status_oracle.oracle_result(root / plan_ref, context=context)
        review = plan_lint.preflight_current_review_proof(root / plan_ref, project_root=root)
        mode = plan_status_oracle.manager_mode_admission(
            plan_status_oracle.parse_plan_meta_admission_carrier(oracle.captured_plan_text), "manager-collab")
        if (oracle.status_norm not in TERMINAL_STATUSES or oracle.route_guard_triggered
                or not oracle.queue_closeout_ready or oracle.owner_qna_readback_state != "clean"
                or review.state == "blocked" or mode["manager_mode_admitted"] is not True
                or bundle_payload.get("plan") != plan_ref or bundle_payload.get("bundle_ok") is not True
                or bundle_payload.get("errors") != []):
            return refuse("continuation_terminal_admission_blocked")
        semantic_fields = (oracle.status_value, oracle.status_norm, str(bundle_payload.get("closeout_kind") or "unknown"))
        if semantic_fields[2] != "already_materialized":
            return refuse("continuation_semantic_identity_drift")
        manifest = followups_capture.v2_frozen_manifest_path(root, plan_ref)
        manifest_rel = manifest.relative_to(root).as_posix()
        if not path_components_are_symlink_free(root, manifest_rel):
            return refuse("continuation_manifest_path_unsafe")
        try:
            manifest.lstat()
        except FileNotFoundError:
            pass
        else:
            return refuse("continuation_manifest_present")
        reconciliation = classify_followups_reconciliation(root, plan_ref)
        if (reconciliation.get("state"), reconciliation.get("reason")) != (
                "external_unknown", "missing_v2_frozen_manifest"):
            return refuse("continuation_reconciliation_not_missing")
        with followups_capture.CaptureHost(root, plan_ref, create=False) as host:
            active: list[str] = []
            for entry in os.listdir(host.family_fd):
                if not followups_capture.UUID4_RE.fullmatch(entry):
                    continue
                fd, cycle_identity = followups_capture._open_cycle(host, entry)
                try:
                    candidate, _, _ = followups_capture._read_receipt(fd, plan_ref, entry)
                    if (candidate["cycle_directory_identity"] != cycle_identity
                            or candidate["transaction_host_identity"] != host.transaction_host_identity()):
                        return refuse("continuation_host_object_drift")
                    if candidate.get("state") == "started":
                        active.append(entry)
                finally:
                    os.close(fd)
            if active != [capture_cycle_id]:
                return refuse("continuation_active_subject_ambiguous")
            fd, cycle_identity = followups_capture._open_cycle(host, capture_cycle_id)
            try:
                receipt, raw, receipt_identity = followups_capture._read_receipt(fd, plan_ref, capture_cycle_id)
                if (receipt.get("state") != "started" or receipt.get("finalized_at") is not None
                        or receipt.get("completed_roles") != [] or receipt.get("blocked_roles") != []
                        or receipt.get("role_results") != {}
                        or receipt.get(followups_capture.ORDINARY_V2_BINDING_KEY) is not None):
                    return refuse("continuation_phase_closed")
                for directory in (followups_capture.ORDINARY_V2_BOUND_DIRECTORY,
                                  followups_capture.ORDINARY_V2_SUBMISSION_DIRECTORY,
                                  followups_capture.ORDINARY_V2_INPUT_DIRECTORY):
                    try:
                        os.stat(directory, dir_fd=fd, follow_symlinks=False)
                    except FileNotFoundError:
                        pass
                    else:
                        return refuse("continuation_ordinary_progress_present")
                source = followups_capture._ordinary_v2_current_source_identity(root, plan_ref, receipt)
                identity = followups_capture._identity_payload(
                    plan_ref=plan_ref, plan_sha256=source["source_plan_sha256"],
                    terminal_status_line=receipt["terminal_status_line"], semantic_status=semantic_fields[0],
                    semantic_status_norm=semantic_fields[1], semantic_closeout_kind=semantic_fields[2],
                    required_roles=list(followups_capture.REQUIRED_ROLES))
                if identity != receipt["identity_payload"]:
                    return refuse("continuation_semantic_identity_drift")
                lineage = followups_capture._receipt_pi_lineage(receipt)
                if (lineage["ownership_state"] != "active" or lineage["final_objects"]
                        or lineage["failure_checkpoint"] is not None or "general_pi_checkpoint" not in receipt):
                    return refuse("continuation_pi_phase_invalid")
                live_followups, _ = followups_capture.snapshot_followups(root)
                if (live_followups != receipt.get("baseline_followup_files")
                        or live_followups != receipt.get("current_followup_files")):
                    return refuse("continuation_followups_drift")
                marker = receipt.get("general_pi_checkpoint")
                if marker is None:
                    if receipt["receipt_revision"] != 1:
                        return refuse("continuation_receipt_revision_invalid")
                    collectors = followups_capture._general_pi_capture_receipts_proof(
                        root, plan_ref, capture_cycle_id, expected_before=lineage["current_objects"])
                else:
                    checkpoint = followups_capture.general_pi_checkpoint_proof(root, plan_ref, receipt)
                    if receipt["receipt_revision"] != checkpoint["marker"]["prior_receipt_revision"] + 1:
                        return refuse("continuation_receipt_revision_invalid")
                    collectors = checkpoint["collector_proof"]
                before = collectors["before_process_improvement_files"]
                after = collectors["after_process_improvement_files"]
                if (receipt["baseline_dirty_process_improvement_paths"] != []
                        or before != receipt["baseline_process_improvement_files"]):
                    return refuse("continuation_pi_baseline_unowned")
                docs_snapshot = _git_status_docs_paths(root)
                protected, delta_ok = _terminal_protected_docs_delta_paths(
                    root=root, plan_ref=plan_ref, status_norm=oracle.status_norm, docs_status_snapshot=docs_snapshot)
                if not docs_snapshot[1] or not delta_ok:
                    return refuse("continuation_docs_delta_unknown")
                if protected:
                    return refuse("continuation_protected_docs_delta")
                owned_pi = followups_capture._changed_paths(before, after)
                if set(docs_snapshot[0]).difference(owned_pi):
                    return refuse("continuation_foreign_or_unproven_docs_delta")
                # Re-open the aggregate after all read-only witnesses. No admission
                # may combine inputs from different aggregate revisions/objects.
                _, now_raw, now_identity = followups_capture._read_receipt(fd, plan_ref, capture_cycle_id)
                if now_raw != raw or now_identity != receipt_identity:
                    return refuse("continuation_receipt_object_drift")
                receipt_stat = os.stat(followups_capture.RECEIPT_NAME, dir_fd=fd, follow_symlinks=False)
                result.update(state="ready", reason="pre_first_followups", next_dispatch="Architect:followups", proof={
                    "identity_payload": identity, "semantic_closeout_identity": receipt["semantic_closeout_identity"],
                    "source_identity": source, "receipt_revision": receipt["receipt_revision"],
                    "receipt_content_sha256": receipt["receipt_content_sha256"],
                    "receipt_sha256": followups_capture._sha256(raw), "receipt_object_identity": receipt_identity,
                    "receipt_object": followups_capture._followup_object(receipt_stat, raw),
                    "cycle_directory_identity": cycle_identity, "transaction_host_identity": host.transaction_host_identity(),
                    "followup_files": live_followups, "baseline_process_improvement_files": before,
                    "baseline_dirty_process_improvement_paths": receipt["baseline_dirty_process_improvement_paths"],
                    "collector_proof": {key: value for key, value in collectors.items() if key != "role_receipts"},
                    "collector_states": {item["role"]: item["capture_state"] for item in collectors["role_receipts"]},
                    "collector_inputs": {item["role"]: item["input_sha256"] for item in collectors["role_receipts"]},
                    "general_pi_checkpoint": marker,
                    "docs_delta": {"paths": docs_snapshot[0], "protected_paths": protected, "owned_pi_paths": owned_pi},
                    "terminal_admission": {"manager_mode": mode, "owner_qna_state": oracle.owner_qna_readback_state,
                        "review_state": review.state, "bundle_ok": True, "bundle_errors": [], "closeout_kind": semantic_fields[2]},
                })
                return result
            finally:
                os.close(fd)
    except (followups_capture.CaptureError, ContractAuthorityError, OSError, ValueError) as exc:
        return refuse(getattr(exc, "reason_code", "continuation_proof_unavailable"))


def classify_followups_bootstrap_admission(root: Path, plan_ref: str) -> dict[str, Any]:
    """Derive one read-only admission to start an ordinary V2 family.

    This is intentionally distinct from reconciliation: it can authorize one
    fresh capture only when the manifest has no lexical filesystem entry.  It
    never parses, repairs, or writes a present manifest.
    """

    root = root.absolute()
    try:
        normalized_plan_ref = followups_capture.normalize_plan_ref(plan_ref)
    except followups_capture.CaptureError:
        normalized_plan_ref = str(plan_ref)
        manifest_path = root / ".tmp" / "followups_capture" / "invalid-plan-ref" / "v2_frozen_manifest.json"
        return _followups_bootstrap_admission_payload(
            plan_ref=normalized_plan_ref,
            manifest_path=manifest_path.relative_to(root),
            state="blocked",
            reason="bootstrap_source_identity_invalid",
        )

    manifest_abs = followups_capture.v2_frozen_manifest_path(root, normalized_plan_ref)
    manifest_rel = manifest_abs.relative_to(root).as_posix()
    manifest_path = Path(manifest_rel)
    recovery = classify_followups_blocked_predecessor_recovery(root, normalized_plan_ref)
    if recovery.get("state") != "not_applicable":
        return _followups_bootstrap_admission_payload(
            plan_ref=normalized_plan_ref,
            manifest_path=manifest_path,
            state="blocked",
            reason="bootstrap_blocked_predecessor_present",
        )
    source, source_reason = _followups_bootstrap_source_identity(root, normalized_plan_ref)
    if source_reason is not None:
        return _followups_bootstrap_admission_payload(
            plan_ref=normalized_plan_ref,
            manifest_path=manifest_path,
            state="blocked",
            reason=source_reason,
            source_identity=source,
        )
    assert source is not None

    if not path_components_are_symlink_free(root, manifest_rel):
        return _followups_bootstrap_admission_payload(
            plan_ref=normalized_plan_ref,
            manifest_path=manifest_path,
            state="blocked",
            reason="bootstrap_manifest_path_unsafe",
            source_identity=source,
        )
    try:
        manifest_abs.lstat()
    except FileNotFoundError:
        pass
    except OSError:
        return _followups_bootstrap_admission_payload(
            plan_ref=normalized_plan_ref,
            manifest_path=manifest_path,
            state="blocked",
            reason="bootstrap_manifest_path_unsafe",
            source_identity=source,
        )
    else:
        return _followups_bootstrap_admission_payload(
            plan_ref=normalized_plan_ref,
            manifest_path=manifest_path,
            state="blocked",
            reason="bootstrap_manifest_present",
            source_identity=source,
        )

    reconciliation = classify_followups_reconciliation(root, normalized_plan_ref)
    if (
        reconciliation.get("state") != "external_unknown"
        or reconciliation.get("reason") != "missing_v2_frozen_manifest"
    ):
        return _followups_bootstrap_admission_payload(
            plan_ref=normalized_plan_ref,
            manifest_path=manifest_path,
            state="blocked",
            reason="bootstrap_reconciliation_not_missing",
            source_identity=source,
        )
    capture_reason = _followups_bootstrap_capture_reason(root, normalized_plan_ref)
    if capture_reason is not None:
        return _followups_bootstrap_admission_payload(
            plan_ref=normalized_plan_ref,
            manifest_path=manifest_path,
            state="blocked",
            reason=capture_reason,
            source_identity=source,
        )
    return _followups_bootstrap_admission_payload(
        plan_ref=normalized_plan_ref,
        manifest_path=manifest_path,
        state="ready",
        reason="missing_v2_frozen_manifest",
        source_identity=source,
    )


def classify_followups_reconciliation(root: Path, plan_ref: str) -> dict[str, Any]:
    root = root.absolute()
    plan_path = root / plan_ref
    plan_text = _read_text(plan_path)
    plan_meta = plan_status_oracle.parse_plan_meta(plan_text)
    schema_class, _schema_findings = plan_lint.classify_plan_schema_version(plan_path, plan_text.splitlines())
    if schema_class == "v2":
        manifest_path = followups_capture.v2_frozen_manifest_path(root, plan_ref)
        manifest_rel = manifest_path.relative_to(root).as_posix()
        if not path_components_are_symlink_free(root, manifest_rel):
            return {
                "schema": FOLLOWUPS_RECONCILIATION_SCHEMA,
                "state": "external_invalid",
                "reason": "v2_manifest_path_unsafe",
                "proof_host": manifest_rel,
                "open_items": [{"row_ref": manifest_rel, "summary": "manifest path is not symlink-free", "proof_host": manifest_rel}],
                "closed_or_promoted_items": [],
            }
        try:
            manifest_stat = manifest_path.lstat()
        except FileNotFoundError:
            return {
                "schema": FOLLOWUPS_RECONCILIATION_SCHEMA,
                "state": "external_unknown",
                "reason": "missing_v2_frozen_manifest",
                "proof_host": manifest_rel,
                "open_items": [],
                "closed_or_promoted_items": [],
            }
        except OSError as exc:
            return {
                "schema": FOLLOWUPS_RECONCILIATION_SCHEMA,
                "state": "external_invalid",
                "reason": "v2_manifest_path_unsafe",
                "proof_host": manifest_rel,
                "open_items": [{"row_ref": manifest_rel, "summary": str(exc), "proof_host": manifest_rel}],
                "closed_or_promoted_items": [],
            }
        if not stat.S_ISREG(manifest_stat.st_mode):
            return {
                "schema": FOLLOWUPS_RECONCILIATION_SCHEMA,
                "state": "external_invalid",
                "reason": "v2_manifest_not_regular",
                "proof_host": manifest_rel,
                "open_items": [{"row_ref": manifest_rel, "summary": "manifest is not a regular file", "proof_host": manifest_rel}],
                "closed_or_promoted_items": [],
            }
        try:
            _manifest_object, manifest_bytes = followups_capture.read_repo_regular_path(root, manifest_rel)
            manifest = json.loads(manifest_bytes.decode("utf-8"))
            if not isinstance(manifest, dict) or manifest.get("plan_ref") != plan_ref:
                raise ValueError("plan_ref mismatch")
            proof = followups_capture.v2_external_proof(root, manifest)
        except followups_capture.CaptureError as exc:
            return {
                "schema": FOLLOWUPS_RECONCILIATION_SCHEMA,
                "state": "external_invalid",
                "reason": exc.reason_code,
                "proof_host": manifest_rel,
                "open_items": [{"row_ref": manifest_rel, "summary": str(exc), "proof_host": manifest_rel}],
                "closed_or_promoted_items": [],
            }
        except Exception as exc:
            return {
                "schema": FOLLOWUPS_RECONCILIATION_SCHEMA,
                "state": "external_invalid",
                "reason": "invalid_v2_manifest_or_proof",
                "proof_host": manifest_rel,
                "open_items": [{"row_ref": manifest_rel, "summary": str(exc), "proof_host": manifest_rel}],
                "closed_or_promoted_items": [],
            }
        state = str(proof.get("state") or "external_invalid")
        proof_rows = proof.get("proof_rows") if isinstance(proof.get("proof_rows"), list) else []
        proof_hosts = [str(row.get("proof_host")) for row in proof_rows if isinstance(row, dict) and row.get("proof_host")]
        errors = proof.get("errors") if isinstance(proof.get("errors"), list) else []
        return {
            "schema": FOLLOWUPS_RECONCILIATION_SCHEMA,
            "state": state if state in FOLLOWUPS_RECONCILIATION_STATES else "external_invalid",
            "reason": str(proof.get("reason") or "invalid_v2_proof"),
            "proof_host": "|".join(proof_hosts) if proof_hosts else manifest_rel,
            "open_items": [
                {"row_ref": manifest_rel, "summary": str(error), "proof_host": manifest_rel}
                for error in errors
            ],
            "closed_or_promoted_items": proof_rows,
        }
    if schema_class != "legacy_v1":
        return {
            "schema": FOLLOWUPS_RECONCILIATION_SCHEMA,
            "state": "external_invalid",
            "reason": "unsupported_plan_schema_for_legacy_followups",
            "proof_host": f"{plan_ref}::plan_meta.followups_out",
            "open_items": [],
            "closed_or_promoted_items": [],
        }
    proof_host = f"{plan_ref}::plan_meta.followups_out"
    if "followups_out" not in plan_meta:
        return {
            "schema": "followups_reconciliation.v1",
            "state": "unknown",
            "reason": "missing_plan_meta_followups_out",
            "proof_host": proof_host,
            "open_items": [],
            "closed_or_promoted_items": [],
        }

    followups_out = plan_meta.get("followups_out")
    if not isinstance(followups_out, list):
        return {
            "schema": "followups_reconciliation.v1",
            "state": "unknown",
            "reason": "invalid_plan_meta_followups_out",
            "proof_host": proof_host,
            "open_items": [],
            "closed_or_promoted_items": [],
        }

    def open_item_readback(idx: int, item: dict[str, Any]) -> dict[str, Any]:
        plan_value = item.get("plan")
        current_plan_value = str(plan_value).strip() if isinstance(plan_value, str) else None
        return {
            "index": idx,
            "row_ref": f"plan_meta.followups_out[{idx}]",
            "proof_host": proof_host,
            "summary": str(item.get("summary") or "").strip(),
            "plan": current_plan_value or None,
            "current_plan_value": current_plan_value or "null",
            "status": str(item.get("status") or item.get("state") or "").strip() or None,
            "disposition": str(item.get("disposition") or item.get("resolution") or "").strip() or None,
            "source_ref": str(item.get("source_ref") or item.get("ref") or item.get("evidence") or "").strip()
            or None,
            "reason": str(item.get("reason") or "").strip() or None,
            "accepted_repair_shapes": list(FOLLOWUPS_OUT_REPAIR_SHAPES),
        }

    invalid_items = [idx for idx, item in enumerate(followups_out, start=1) if not isinstance(item, dict)]
    if invalid_items:
        return {
            "schema": "followups_reconciliation.v1",
            "state": "unknown",
            "reason": "invalid_followups_out_item",
            "proof_host": proof_host,
            "open_items": [
                {
                    "index": idx,
                    "row_ref": f"plan_meta.followups_out[{idx}]",
                    "proof_host": proof_host,
                    "summary": "",
                    "plan": None,
                    "current_plan_value": "invalid",
                    "accepted_repair_shapes": list(FOLLOWUPS_OUT_REPAIR_SHAPES),
                }
                for idx in invalid_items
            ],
            "closed_or_promoted_items": [],
        }

    open_items = [open_item_readback(idx, item) for idx, item in plan_lint.open_roadmap_followups(plan_meta)]
    if open_items:
        try:
            current_snapshot, current_bytes = followups_capture.snapshot_followups(root, include_bytes=True)
        except followups_capture.CaptureError as exc:
            return {
                "schema": FOLLOWUPS_RECONCILIATION_SCHEMA,
                "state": "external_invalid",
                "reason": "v2_integrity_blocker",
                "proof_host": "docs/followups/*",
                "open_items": [
                    {
                        "row_ref": proof_host,
                        "summary": f"{exc.reason_code}:{exc}",
                        "proof_host": "docs/followups/*",
                    }
                ],
                "closed_or_promoted_items": [],
            }
        inventory = followups_lint._inventory_followups_snapshot(root, current_snapshot, current_bytes)
        if inventory.blockers:
            return {
                "schema": FOLLOWUPS_RECONCILIATION_SCHEMA,
                "state": "external_invalid",
                "reason": "v2_integrity_blocker",
                "proof_host": "docs/followups/*",
                "open_items": [
                    {
                        "row_ref": finding.rel_path,
                        "summary": finding.render(),
                        "proof_host": finding.rel_path,
                    }
                    for finding in inventory.blockers
                ],
                "closed_or_promoted_items": [],
            }

        source_ref = followups_lint.normalize_source_ref(plan_ref)
        if source_ref is None:
            return {
                "schema": FOLLOWUPS_RECONCILIATION_SCHEMA,
                "state": "external_invalid",
                "reason": "legacy_bridge_source_ref_invalid",
                "proof_host": proof_host,
                "open_items": open_items,
                "closed_or_promoted_items": [],
            }
        bridge_items: dict[tuple[str, str], list[followups_lint.FollowupItem]] = {}
        for followup in inventory.valid_v2.values():
            for item in followup.items:
                identity = followups_lint.v2_legacy_bridge_identity(item)
                if identity is not None:
                    bridge_items.setdefault(identity, []).append(item)

        proof_rows: list[dict[str, Any]] = []
        missing_bridge = False
        ambiguous_bridge = False
        for open_item in open_items:
            row_ref = str(open_item["row_ref"])
            matching = bridge_items.get((source_ref, row_ref), [])
            if not matching:
                missing_bridge = True
                continue
            if len(matching) != 1:
                ambiguous_bridge = True
                continue
            bridge_item = matching[0]
            proof_rows.append(
                {
                    "proof_host": f"{bridge_item.rel_path}#{bridge_item.item_id}",
                    "source_ref": source_ref,
                    "legacy_row_ref": row_ref,
                    "legacy_plan_sha256": bridge_item.legacy_plan_sha256,
                    "legacy_row_sha256": bridge_item.legacy_row_sha256,
                    "v2_status": bridge_item.status,
                    "v2_disposition_kind": bridge_item.disposition_kind,
                    "v2_disposition_ref": bridge_item.disposition_ref,
                    "v2_disposition_commit_oid": bridge_item.disposition_commit_oid,
                    "applied_row_digest": followups_lint.v2_row_digest(bridge_item),
                }
            )
        if ambiguous_bridge:
            return {
                "schema": FOLLOWUPS_RECONCILIATION_SCHEMA,
                "state": "external_invalid",
                "reason": "ambiguous_legacy_v2_bridge_proof",
                "proof_host": proof_host,
                "open_items": open_items,
                "closed_or_promoted_items": [],
            }
        if missing_bridge:
            return {
                "schema": FOLLOWUPS_RECONCILIATION_SCHEMA,
                "state": "open",
                "reason": "open_plan_meta_followups_out",
                "proof_host": proof_host,
                "open_items": open_items,
                "closed_or_promoted_items": [],
            }
        return {
            "schema": FOLLOWUPS_RECONCILIATION_SCHEMA,
            "state": "external_clean",
            "reason": "exact_legacy_v2_bridge_proof",
            "proof_host": "|".join(str(row["proof_host"]) for row in proof_rows),
            "open_items": [],
            "closed_or_promoted_items": proof_rows,
        }

    closed_or_promoted_items = [
        {
            "index": idx,
            "summary": str(item.get("summary") or "").strip(),
            "plan": str(item.get("plan") or "").strip() or None,
        }
        for idx, item in enumerate(followups_out, start=1)
        if isinstance(item, dict)
    ]
    return {
        "schema": "followups_reconciliation.v1",
        "state": "clean_noop",
        "reason": "plan_meta_followups_out_clean",
        "proof_host": proof_host,
        "open_items": [],
        "closed_or_promoted_items": closed_or_promoted_items,
    }


def _format_followups_reconciliation_open_item(item: dict[str, Any]) -> str:
    repair_shapes = item.get("accepted_repair_shapes") or []
    repair_text = "|".join(str(shape) for shape in repair_shapes) if repair_shapes else "unknown"
    return (
        f"row_ref={item.get('row_ref') or 'unknown'};"
        f"summary={item.get('summary') or 'N/A'};"
        f"current_plan_value={item.get('current_plan_value') or 'unknown'};"
        f"repair_shapes={repair_text};"
        f"proof_host={item.get('proof_host') or 'unknown'}"
    )


def _dirty_terminal_runtime_signals(runtime_context: dict[str, Any]) -> list[str]:
    dirty: list[str] = []
    for key in ("loop_detected", "repeated_blocker_detected", "max_iterations_reached"):
        if str(runtime_context.get(key) or "").strip().lower() == "yes":
            dirty.append(f"{key}=yes")

    if str(runtime_context.get("latest_stop_reason_scope") or "").strip().lower() == "current_active":
        dirty.append("latest_stop_reason_scope=current_active")

    for key in ("latest_stop_reason", "latest_stop_plan", "latest_stop_item_ref"):
        if not _absent_runtime_value(runtime_context.get(key)):
            dirty.append(f"{key}={runtime_context.get(key)}")

    if runtime_context.get("latest_blocker_ids"):
        dirty.append(
            "latest_blocker_ids="
            + "|".join(str(item) for item in runtime_context.get("latest_blocker_ids") or [])
        )
    if runtime_context.get("review_blocker_status") == "blocking":
        dirty.append("review_blocker_status=blocking")

    for key in ("root_cause_class", "next_owner", "extraordinary_action"):
        if not _absent_runtime_value(runtime_context.get(key)):
            dirty.append(f"{key}={runtime_context.get(key)}")

    return dirty


def classify_terminal_closeout_fast_path(
    *,
    plan_ref: str,
    state: str,
    closeout_kind: str,
    bundle_ok: bool,
    bundle_errors: list[Any],
    final_docs_commit: str,
    protected_docs_delta_paths: list[str],
    process_improvement_capture_state: str,
    process_improvement_receipt_path: str,
    followups_reconciliation: dict[str, Any],
    runtime_context: dict[str, Any],
) -> dict[str, Any]:
    dirty_runtime_signals = _dirty_terminal_runtime_signals(runtime_context)
    checks = {
        "docs_closeout_completed": state == "completed",
        "semantic_materialized": closeout_kind == "already_materialized",
        "bundle_materialized": bundle_ok and not bundle_errors,
        "final_docs_commit_clean": final_docs_commit in {"no_op", "landed"},
        "pi_capture_clean": process_improvement_capture_state in PI_CAPTURE_CONTINUATION_STATES,
        "followups_clean": followups_reconciliation.get("state") in {"clean_noop", "external_clean_noop", "external_clean"},
        "protected_docs_clean": not protected_docs_delta_paths,
        "runtime_context_clean": not dirty_runtime_signals,
    }
    missing_or_dirty = [name for name, ok in checks.items() if not ok]
    eligible = not missing_or_dirty
    return {
        "schema": TERMINAL_FAST_PATH_SCHEMA,
        "eligible": eligible,
        "reason": "clean_terminal_materialized_noop" if eligible else "missing_or_dirty_preconditions",
        "skipped_lanes": list((*TERMINAL_FAST_PATH_FAMILY_LANES, TERMINAL_FAST_PATH_FINAL_HANDOFF_LANE))
        if eligible
        else [],
        "fallback_lanes": [] if eligible else list(TERMINAL_FAST_PATH_FAMILY_LANES),
        "proof_hosts": {
            "docs_closeout": {
                "command": f"planveyor_docs_closeout {plan_ref} --json",
                "fields": [
                    "state",
                    "semantic_closeout_kind",
                    "final_docs_commit",
                    "protected_docs_delta_paths",
                    "process_improvement_capture_state",
                    "runtime_context",
                ],
            },
            "bundle": {
                "command": f"planveyor_plan_bundle --closeout-json {plan_ref}",
                "fields": ["bundle_ok", "bundle_errors", "closeout_kind"],
            },
            "followups": {
                "proof_host": followups_reconciliation.get("proof_host") or "unknown",
                "state": followups_reconciliation.get("state") or "unknown",
                "reason": followups_reconciliation.get("reason") or "unknown",
            },
            "process_improvements": {
                "receipt_path": process_improvement_receipt_path,
                "state": process_improvement_capture_state,
            },
            "runtime_context": {
                "artifact_sources": runtime_context.get("artifact_sources") or [],
                "queue_context_source": runtime_context.get("queue_context_source") or {},
            },
        },
        "precondition_results": checks,
        "missing_or_dirty_preconditions": missing_or_dirty,
        "dirty_runtime_signals": dirty_runtime_signals,
    }


def collect_runtime_context(root: Path, plan_ref: str, oracle: plan_status_oracle.OracleResult) -> dict[str, Any]:
    root = root.resolve()
    plan_path = root / plan_ref
    plan_text = _read_text(plan_path)
    review_artifacts = _extract_review_artifacts(plan_text, root)
    artifact_paths = [plan_path, *sorted(review_artifacts, key=lambda item: item.stat().st_mtime)]
    artifact_texts = [(path, _read_text(path)) for path in artifact_paths]
    review_artifact_set = {path.resolve() for path in review_artifacts}
    review_artifact_texts = [
        (path, text) for path, text in artifact_texts if path.resolve() in review_artifact_set
    ]
    review_blocker_context, green_closed_only_review_paths = _review_blocker_context(
        review_artifact_texts,
        root,
    )
    review_label_artifact_texts = [
        (path, text)
        for path, text in artifact_texts
        if path.resolve() not in green_closed_only_review_paths
    ]

    loop_value, loop_source = _latest_label_value(artifact_texts, "Loop signal")
    root_cause_raw, root_cause_source = _latest_label_value(
        review_label_artifact_texts,
        "Root cause class",
    )
    extraordinary_raw, extraordinary_source = _latest_label_value(
        review_label_artifact_texts,
        "Extraordinary action",
    )
    next_owner_raw, next_owner_source = _latest_label_value(
        review_label_artifact_texts,
        "Next owner",
    )
    blocker_ids_raw, blocker_ids_source = _latest_label_value(
        review_label_artifact_texts,
        "Blocker IDs considered",
    )
    if blocker_ids_raw is None:
        blocker_ids_raw, blocker_ids_source = _latest_label_value(
            review_label_artifact_texts,
            "Blocker IDs",
        )

    root_cause_class, root_cause_state = _normalize_optional_value(root_cause_raw)
    extraordinary_action, extraordinary_state = _normalize_optional_value(extraordinary_raw)
    next_owner, next_owner_state = _normalize_optional_value(next_owner_raw)
    blocker_ids = _parse_blocker_ids(blocker_ids_raw)
    blocker_ids_state = "listed" if blocker_ids else "unknown"
    if blocker_ids_raw is not None and not blocker_ids:
        blocker_ids_state = "none" if NONE_LIKE_RE.match(blocker_ids_raw) else "unknown"
    for blocker_id in review_blocker_context["review_blocker_ids"]:
        if blocker_id not in blocker_ids:
            blocker_ids.append(blocker_id)
    if blocker_ids:
        blocker_ids_state = "listed"

    queue_paths = plan_queue.queue_paths(root)
    queue_context = plan_queue.queue_runtime_context_snapshot(queue_paths, plan=plan_ref)
    history_available = bool(queue_context.get("history_available"))
    latest_stop_reason = queue_context.get("latest_stop_reason") or ("unknown" if not history_available else "none")
    latest_stop_plan = queue_context.get("latest_stop_plan") or ("unknown" if not history_available else "none")
    latest_stop_reason_scope = queue_context.get("latest_stop_reason_scope") or "none"
    latest_stop_item_ref = queue_context.get("latest_stop_item_ref") or ("unknown" if not history_available else "none")
    historical_stop_reason = queue_context.get("historical_stop_reason") or ("unknown" if not history_available else "none")
    historical_stop_plan = queue_context.get("historical_stop_plan") or ("unknown" if not history_available else "none")
    historical_stop_item_ref = queue_context.get("historical_stop_item_ref") or ("unknown" if not history_available else "none")
    terminal_tail_stop_reason = queue_context.get("terminal_tail_stop_reason") or (
        "unknown" if not history_available else "none"
    )
    terminal_tail_stop_at = queue_context.get("terminal_tail_stop_at") or (
        "unknown" if not history_available else "none"
    )
    terminal_tail_stop_source_plan = queue_context.get("terminal_tail_stop_source_plan") or (
        "unknown" if not history_available else "none"
    )
    terminal_tail_stop_source_item_ref = queue_context.get("terminal_tail_stop_source_item_ref") or (
        "unknown" if not history_available else "none"
    )
    terminal_tail_stop_active_item_ref = queue_context.get("terminal_tail_stop_active_item_ref") or (
        "unknown" if not history_available else "none"
    )

    loop_detected = queue_context.get("loop_detected")
    if loop_value is not None:
        loop_value_norm = loop_value.strip().lower()
        if loop_value_norm.startswith("yes"):
            loop_detected = True
        elif loop_value_norm.startswith("no"):
            loop_detected = False
        else:
            loop_detected = queue_context.get("loop_detected")

    return {
        "plan_ref": plan_ref,
        "semantic_status": oracle.status_value,
        "semantic_status_norm": oracle.status_norm,
        "closeout_runtime_class": oracle.runtime_class,
        "queue_closeout_ready": oracle.queue_closeout_ready,
        "queue_closeout_kind": oracle.queue_closeout_kind,
        "queue_closeout_reason": oracle.queue_closeout_reason,
        "route_guard_triggered": oracle.route_guard_triggered,
        "route_guard_kind": oracle.route_guard_kind,
        "route_guard_reason": oracle.route_guard_reason,
        "machine_authority_decision_state": oracle.machine_authority_decision_state,
        "machine_authority_decision_reason": oracle.machine_authority_decision_reason,
        "machine_authority_decision_id": oracle.machine_authority_decision_id,
        "machine_authority_decision_route": oracle.machine_authority_decision_route,
        "machine_authority_decision_carrier_sha256": oracle.machine_authority_decision_carrier_sha256,
        "machine_authority_decision_confirmation_state": oracle.machine_authority_decision_confirmation_state,
        "loop_detected": _bool_text(loop_detected),
        "repeated_blocker_detected": _bool_text(queue_context.get("repeated_blocker_detected")),
        "max_iterations_reached": _bool_text(queue_context.get("max_iterations_reached")),
        "latest_stop_reason": latest_stop_reason,
        "latest_stop_plan": latest_stop_plan,
        "latest_stop_reason_scope": latest_stop_reason_scope,
        "latest_stop_item_ref": latest_stop_item_ref,
        "historical_stop_reason": historical_stop_reason,
        "historical_stop_plan": historical_stop_plan,
        "historical_stop_item_ref": historical_stop_item_ref,
        "terminal_tail_stop_reason": terminal_tail_stop_reason,
        "terminal_tail_stop_at": terminal_tail_stop_at,
        "terminal_tail_stop_source_plan": terminal_tail_stop_source_plan,
        "terminal_tail_stop_source_item_ref": terminal_tail_stop_source_item_ref,
        "terminal_tail_stop_active_item_ref": terminal_tail_stop_active_item_ref,
        "latest_blocker_ids": blocker_ids,
        "latest_blocker_ids_state": blocker_ids_state,
        **review_blocker_context,
        "root_cause_class": root_cause_class or root_cause_state,
        "root_cause_class_source": _root_relative(root_cause_source, root) if root_cause_source else "unknown",
        "extraordinary_action": extraordinary_action or extraordinary_state,
        "extraordinary_action_source": _root_relative(extraordinary_source, root) if extraordinary_source else "unknown",
        "next_owner": next_owner or next_owner_state,
        "next_owner_source": _root_relative(next_owner_source, root) if next_owner_source else "unknown",
        "queue_context_source": {
            "state_path": _root_relative(queue_paths.state_path, root),
            "log_path": _root_relative(queue_paths.log_path, root),
            "history_available": queue_context.get("history_available"),
            "last_transition_kind": queue_context.get("last_transition_kind") or "none",
        },
        "artifact_sources": [_root_relative(path, root) for path in artifact_paths],
        "loop_signal_source": _root_relative(loop_source, root) if loop_source else "unknown",
        "blocker_ids_source": _root_relative(blocker_ids_source, root) if blocker_ids_source else "unknown",
    }


def lexical_exists(path: Path) -> bool:
    return os.path.lexists(path)


def regular_file_exists(path: Path) -> bool:
    return path.is_file() and not path.is_symlink()


def path_components_are_symlink_free(
    root: Path,
    rel: str,
    *,
    include_leaf: bool = True,
) -> bool:
    lexical = Path(rel)
    if lexical.is_absolute() or not lexical.parts or any(part in {".", ".."} for part in lexical.parts):
        return False
    current = root
    parts = lexical.parts if include_leaf else lexical.parts[:-1]
    for part in parts:
        current /= part
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            return True
        except OSError:
            return False
        if stat.S_ISLNK(mode):
            return False
    return True


def _accepted_red_snapshot_reason(error: fs_object_identity.ObjectIdentityError) -> str:
    if error.reason_code == "symlink_forbidden":
        return "accepted_red_active_checkout_aliased"
    if error.reason_code == "leaf_not_regular":
        return "accepted_red_active_checkout_non_regular"
    return "accepted_red_active_checkout_drift"


def _head_regular_or_absent(
    root: Path,
    relative_path: str,
) -> tuple[str, bytes | None, str | None] | None:
    tree = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "ls-tree",
            "-z",
            "--full-name",
            "HEAD",
            "--",
            relative_path,
        ],
        capture_output=True,
        check=False,
        env=plan_status_oracle.accepted_red_git_env(),
    )
    if tree.returncode:
        return None
    if not tree.stdout:
        return ("absent", None, None)
    records = tree.stdout.removesuffix(b"\0").split(b"\0")
    if len(records) != 1:
        return None
    metadata, separator, encoded_path = records[0].partition(b"\t")
    fields = metadata.split()
    try:
        listed_path = encoded_path.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if (
        not separator
        or len(fields) != 3
        or fields[0] not in {b"100644", b"100755"}
        or fields[1] != b"blob"
        or listed_path != relative_path
    ):
        return None
    blob = subprocess.run(
        ["git", "-C", str(root), "cat-file", "blob", fields[2].decode("ascii")],
        capture_output=True,
        check=False,
        env=plan_status_oracle.accepted_red_git_env(),
    )
    if blob.returncode:
        return None
    return ("regular", blob.stdout, fields[0].decode("ascii"))


def verify_accepted_red_receipt(
    *,
    root: Path,
    plan_ref: str,
    bundle_payload: dict[str, Any],
    context: ContractContext | None = None,
) -> tuple[bool, str]:
    ref = bundle_payload.get("recovery_ref")
    manifest_path = bundle_payload.get("recovery_manifest_path")
    cleanup_path = bundle_payload.get("recovery_cleanup_path")
    capture_commit = bundle_payload.get("capture_commit")
    cleanup_commit = bundle_payload.get("cleanup_commit")
    captured_parent = bundle_payload.get("captured_parent")
    if not all(
        isinstance(value, str) and value
        for value in (ref, manifest_path, cleanup_path, capture_commit, cleanup_commit, captured_parent)
    ):
        return False, "accepted_red_receipt_identity_missing"
    try:
        source_review_rel = plan_status_oracle.resolve_accepted_red_review_path(
            root,
            plan_ref,
        )
    except plan_status_oracle.AcceptedRedDurableValidationError:
        return False, "accepted_red_recovery_review_invalid"

    def git_text(*args: str) -> tuple[int, str]:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            check=False,
            env=plan_status_oracle.accepted_red_git_env(),
        )
        return proc.returncode, proc.stdout.strip()

    rc, tip = git_text("rev-parse", "--verify", str(ref))
    if rc or tip != cleanup_commit:
        return False, "accepted_red_receipt_ref_mismatch"
    rc, cleanup_parent = git_text("rev-parse", f"{cleanup_commit}^")
    if rc or cleanup_parent != capture_commit:
        return False, "accepted_red_receipt_cleanup_parent_mismatch"
    rc, capture_parent = git_text("rev-parse", f"{capture_commit}^")
    if rc or capture_parent != captured_parent:
        return False, "accepted_red_receipt_capture_parent_mismatch"
    rc, manifest_raw = git_text("show", f"{capture_commit}:{manifest_path}")
    if rc:
        return False, "accepted_red_manifest_missing"
    rc, cleanup_raw = git_text("show", f"{cleanup_commit}:{cleanup_path}")
    if rc:
        return False, "accepted_red_cleanup_receipt_missing"
    try:
        manifest = json.loads(manifest_raw)
        cleanup = json.loads(cleanup_raw)
    except json.JSONDecodeError:
        return False, "accepted_red_receipt_json_invalid"
    expected_manifest = {
        "schema": "planveyor_rejected_baseline.v1",
        "source_plan": plan_ref,
        "recovery_plan": bundle_payload.get("recovery_plan"),
        "successor_plan": bundle_payload.get("successor_plan"),
        "historical_review": source_review_rel,
        "review_bundle_sha256": bundle_payload.get("review_bundle_sha256"),
        "recovery_ref": ref,
        "recovery_manifest_path": manifest_path,
        "recovery_cleanup_path": cleanup_path,
        "captured_parent": captured_parent,
    }
    frozen_recovery_contract = (
        "recovery_code_draft" in manifest or "recovery_targets" in manifest
    )
    recovery_contract_state = bundle_payload.get("recovery_contract_state")
    allowlisted_rebind = (
        recovery_contract_state == "allowlisted_terminal_rebind"
    )
    if frozen_recovery_contract:
        expected_manifest.update(
            recovery_code_draft=(
                manifest.get("recovery_code_draft")
                if allowlisted_rebind
                else bundle_payload.get("recovery_code_draft")
            ),
            recovery_targets=(
                manifest.get("recovery_targets")
                if allowlisted_rebind
                else bundle_payload.get("recovery_targets")
            ),
        )
    if not isinstance(manifest, dict) or any(manifest.get(key) != value for key, value in expected_manifest.items()):
        return False, "accepted_red_manifest_identity_mismatch"
    expected_cleanup = {
        "schema": "planveyor_rejected_baseline_cleanup.v1",
        "source_plan": plan_ref,
        "recovery_plan": bundle_payload.get("recovery_plan"),
        "recovery_ref": ref,
        "review_bundle_sha256": bundle_payload.get("review_bundle_sha256"),
        "capture_commit": capture_commit,
        "captured_parent": captured_parent,
        "cleanup_head": captured_parent,
    }
    if frozen_recovery_contract:
        expected_cleanup.update(
            recovery_code_draft=(
                manifest.get("recovery_code_draft")
                if allowlisted_rebind
                else bundle_payload.get("recovery_code_draft")
            ),
            recovery_targets=(
                manifest.get("recovery_targets")
                if allowlisted_rebind
                else bundle_payload.get("recovery_targets")
            ),
        )
    if not isinstance(cleanup, dict) or any(cleanup.get(key) != value for key, value in expected_cleanup.items()):
        return False, "accepted_red_cleanup_identity_mismatch"
    targets = manifest.get("targets")
    if not isinstance(targets, list) or not all(
        isinstance(item, dict) and isinstance(item.get("path"), str) for item in targets
    ):
        return False, "accepted_red_manifest_targets_invalid"
    target_paths = [str(item["path"]) for item in targets]
    if target_paths != sorted(set(target_paths)):
        return False, "accepted_red_manifest_targets_invalid"
    shared_recovery_contract: dict[str, object] | None = None
    if allowlisted_rebind:
        routing = manifest.get("routing_carriers")
        if not isinstance(routing, list) or not all(
            isinstance(item, dict) and isinstance(item.get("path"), str)
            for item in routing
        ):
            return False, "accepted_red_manifest_identity_mismatch"
        routing_paths = [str(item["path"]) for item in routing]
        if routing_paths != sorted(set(routing_paths)):
            return False, "accepted_red_manifest_identity_mismatch"
        durable = plan_status_oracle.validate_accepted_red_durable_ref(
            root,
            {
                "source_plan": plan_ref,
                "review": source_review_rel,
                "review_sha": bundle_payload.get("review_bundle_sha256"),
                "successor": bundle_payload.get("successor_plan"),
                "ref": ref,
                "manifest_path": manifest_path,
                "cleanup_path": cleanup_path,
                "targets": target_paths,
                "routing": routing_paths,
            },
            context=context,
        )
        if (
            durable.state != "valid_cleanup"
            or durable.capture_commit != capture_commit
            or durable.cleanup_commit != cleanup_commit
            or durable.recovery_contract_state != recovery_contract_state
            or durable.recovery_contract is None
        ):
            return False, "accepted_red_recovery_identity_invalid"
        shared_recovery_contract = dict(durable.recovery_contract)
    staged = subprocess.run(
        ["git", "-C", str(root), "diff", "--cached", "--quiet", "HEAD", "--", *target_paths],
        capture_output=True,
        check=False,
        env=plan_status_oracle.accepted_red_git_env(),
    )
    if staged.returncode:
        return False, "accepted_red_target_index_mismatch"

    recovery_plan = str(bundle_payload.get("recovery_plan") or "")
    if shared_recovery_contract is not None:
        recovery_contract = shared_recovery_contract
    else:
        try:
            recovery_contract = plan_status_oracle.parse_accepted_red_recovery_contract(
                root,
                recovery_plan,
                plan_ref,
                target_paths,
                allow_terminal_status=True,
            )
        except plan_status_oracle.AcceptedRedDurableValidationError as error:
            if "contains a symlinked path component" in str(error):
                return False, "accepted_red_active_checkout_aliased"
            return False, "accepted_red_recovery_identity_invalid"
    recovery_draft_rel = recovery_contract.get("recovery_code_draft")
    recovery_targets_raw = recovery_contract.get("recovery_targets")
    if (
        bundle_payload.get("recovery_code_draft") != recovery_draft_rel
        or bundle_payload.get("recovery_targets") != recovery_targets_raw
    ):
        return False, "accepted_red_recovery_contract_mismatch"
    if not isinstance(recovery_targets_raw, list) or not recovery_targets_raw:
        return False, "accepted_red_recovery_contract_missing"
    recovery_targets = set(str(item) for item in recovery_targets_raw)
    if not frozen_recovery_contract:
        if recovery_contract_state == "legacy_completed_terminal":
            if recovery_contract.get("recovery_status") not in {"done", "superseded"}:
                return False, "accepted_red_recovery_contract_state_mismatch"
        elif recovery_contract_state == "legacy_review_anchored":
            try:
                recovery_review_rel = (
                    plan_status_oracle.resolve_accepted_red_review_path(
                        root,
                        recovery_plan,
                    )
                )
                review_path = root / recovery_review_rel
                review_text = review_path.read_text(encoding="utf-8")
            except plan_status_oracle.AcceptedRedDurableValidationError:
                return False, "accepted_red_recovery_review_missing"
            except (OSError, UnicodeDecodeError):
                return False, "accepted_red_recovery_review_invalid"
            target_match = re.search(
                r"^\*\*Target:\*\*\s*BUNDLE=current bundle_sha256=([0-9a-f]{64})\s*$",
                review_text,
                re.MULTILINE,
            )
            if not target_match:
                return False, "accepted_red_recovery_review_invalid"
            snapshot_args = [
                recovery_plan,
                "--current-bundle",
                "--project-root",
                str(root),
            ]
            try:
                snapshot_command = (
                    contract_authority_children.python_entry_argv(
                        context,
                        SCRIPT_DIR / "review_target_snapshot.py",
                        snapshot_args,
                        python_executable=sys.executable,
                    )
                    if context is not None and context.state == "engaged"
                    else [
                        sys.executable,
                        "-B",
                        str(SCRIPT_DIR / "review_target_snapshot.py"),
                        *snapshot_args,
                    ]
                )
            except contract_authority_children.AuthorityChildLaunchError:
                return False, "accepted_red_recovery_review_invalid"
            snapshot_kwargs: dict[str, Any] = {
                "capture_output": True,
                "text": True,
                "check": False,
            }
            if context is not None and context.state == "engaged":
                snapshot_env = os.environ.copy()
                snapshot_env["_PLANVEYOR_AUTHORITY_CONTEXT_V1"] = context_to_json(context)
                snapshot_kwargs["env"] = snapshot_env
            snapshot = subprocess.run(snapshot_command, **snapshot_kwargs)
            if snapshot.returncode:
                return False, "accepted_red_recovery_review_invalid"
            try:
                snapshot_payload = json.loads(snapshot.stdout)
            except json.JSONDecodeError:
                return False, "accepted_red_recovery_review_invalid"
            if snapshot_payload.get("bundle_sha256") != target_match.group(1):
                return False, "accepted_red_recovery_review_stale"
        else:
            return False, "accepted_red_recovery_contract_state_mismatch"
    snapshots: dict[str, fs_object_identity.ObjectSnapshot] = {}
    try:
        for rel in sorted(set(target_paths) | recovery_targets):
            snapshots[rel] = fs_object_identity.snapshot_regular_or_absent(root, rel)
    except fs_object_identity.ObjectIdentityError as error:
        return False, _accepted_red_snapshot_reason(error)

    dirty_targets: list[str] = []
    for rel in target_paths:
        snapshot = snapshots[rel]
        head = _head_regular_or_absent(root, rel)
        if head is None:
            return False, "accepted_red_active_checkout_drift"
        if (snapshot.state, snapshot.data, snapshot.git_mode) != head:
            dirty_targets.append(rel)
    active_state = "clean"
    if dirty_targets:
        if any(
            rel in recovery_targets and snapshots[rel].state != "regular"
            for rel in dirty_targets
        ):
            return False, "accepted_red_active_checkout_non_regular"
        if all(rel in recovery_targets for rel in dirty_targets):
            active_state = "recovery_owned_overlap"
        else:
            return False, "accepted_red_active_checkout_drift"
    if bundle_payload.get("active_checkout_state") != active_state:
        return False, "accepted_red_active_checkout_state_mismatch"
    return True, "accepted_red_receipt_verified"


def classify_docs_closeout(
    *,
    plan_ref: str,
    bundle_payload: dict[str, Any],
    root: Path,
    followups_capture_cycle_id: str | None = None,
    content_profile_id: str = "default",
    context: ContractContext | None = None,
) -> dict[str, Any]:
    context = _reader_context(root, context)
    root = context.project_root
    dispatch_sources = _dispatch_family_for_profile(content_profile_id, context=context)
    if context.state == "engaged":
        validate_before_effect(context)
    plan_path = root / plan_ref
    oracle = plan_status_oracle.oracle_result(plan_path, context=context)
    current_review_proof = plan_lint.preflight_current_review_proof(plan_path, project_root=root)
    closeout_kind = str(bundle_payload.get("closeout_kind") or "unknown")
    bundle_ok = bool(bundle_payload.get("bundle_ok"))
    accepted_red_source = oracle.terminal_disposition == "accepted_red_supersession"
    accepted_red_receipt_ok, accepted_red_receipt_reason = (
        verify_accepted_red_receipt(
            root=root,
            plan_ref=plan_ref,
            bundle_payload=bundle_payload,
            context=context,
        )
        if accepted_red_source
        else (False, "not_accepted_red")
    )
    accepted_red_completed = (
        accepted_red_source
        and not oracle.route_guard_triggered
        and closeout_kind == ACCEPTED_RED_CLOSEOUT_KIND
        and bundle_ok
        and bundle_payload.get("terminal_disposition") == "accepted_red_supersession"
        and bundle_payload.get("delivery_green") is False
        and bundle_payload.get("staging_policy") == "forbidden"
        and bundle_payload.get("durable_capture_required") is True
        and bundle_payload.get("durable_capture_state") == "cleanup_recorded"
        and bundle_payload.get("recovery_state") == "completed"
        and bundle_payload.get("active_checkout_state") in {"clean", "recovery_owned_overlap"}
        and bundle_payload.get("successor_plan") == oracle.accepted_red_successor_plan
        and bundle_payload.get("review_bundle_sha256") == oracle.accepted_red_review_bundle_sha256
        and accepted_red_receipt_ok
    )

    terminal_oracle_blocked = oracle.status_norm in TERMINAL_STATUSES and (
        oracle.route_guard_triggered
        or (not accepted_red_source and not oracle.queue_closeout_ready)
    )
    if current_review_proof.state == "blocked":
        state = "blocked"
        reason = current_review_proof.reason_code or "current_review_proof_blocked"
    elif terminal_oracle_blocked:
        state = "blocked"
        reason = (
            f"oracle_terminal_admission_blocked:{oracle.route_guard_kind}"
            if oracle.route_guard_triggered
            else f"oracle_terminal_admission_blocked:{oracle.queue_closeout_kind}"
        )
    elif accepted_red_completed:
        state = "completed"
        reason = "accepted_red_recovery_completed"
    elif accepted_red_source:
        state = "blocked"
        reason = (
            accepted_red_receipt_reason
            if closeout_kind == ACCEPTED_RED_CLOSEOUT_KIND and bundle_ok and not accepted_red_receipt_ok
            else "accepted_red_recovery_incomplete"
        )
    elif oracle.status_norm not in TERMINAL_STATUSES and oracle.queue_closeout_ready:
        state = "no_op"
        reason = "non_terminal_non_executable_queue_context"
    elif oracle.status_norm not in TERMINAL_STATUSES:
        state = "no_op"
        reason = "semantic_status_not_terminal"
    elif not bundle_ok:
        state = "blocked"
        reason = "semantic_closeout_bundle_invalid"
    elif closeout_kind == "already_materialized":
        state = "completed"
        reason = "semantic_closeout_materialized"
    elif closeout_kind in BLOCKED_CLOSEOUT_KINDS:
        state = "blocked"
        reason = BLOCKED_CLOSEOUT_KINDS[closeout_kind]
    else:
        state = "blocked"
        reason = f"unsupported_closeout_kind:{closeout_kind}"

    runtime_context = collect_runtime_context(root, plan_ref, oracle)
    terminal_protected_paths: list[str] = []
    terminal_docs_delta_proof_ok = True
    terminal_docs_status_snapshot = (
        _git_status_docs_paths(root)
        if oracle.status_norm in TERMINAL_STATUSES
        else None
    )
    pi_capture = classify_process_improvement_capture(
        root,
        plan_ref,
        capture_cycle_id=followups_capture_cycle_id,
    )
    if state == "blocked" and reason == "semantic_closeout_has_unstaged_delta":
        pi_tail = _process_improvement_tail_paths(
            root=root,
            plan_ref=plan_ref,
            pi_capture=pi_capture,
            docs_status_snapshot=terminal_docs_status_snapshot,
        )
        if pi_tail["ok"]:
            state = "completed"
            reason = "post_done_process_improvement_tail"

    followups_projection = classify_followups_capture(
        root=root,
        plan_ref=plan_ref,
        capture_cycle_id=followups_capture_cycle_id,
        semantic_fields=(oracle.status_value, oracle.status_norm, closeout_kind),
        pi_capture=pi_capture,
        bundle_payload=bundle_payload,
        docs_status_snapshot=terminal_docs_status_snapshot,
    )
    pending_index_transition = followups_projection.pop("_pending_index_transition", False)
    if (
        state == "blocked" and reason == "semantic_closeout_has_unstaged_delta"
        and pending_index_transition
        and followups_projection["followups_capture_state"] == "materialized"
    ):
        state = "completed"
        reason = "post_done_capture_owned_delta"

    if state == "completed" and oracle.status_norm in TERMINAL_STATUSES:
        terminal_protected_paths, terminal_docs_delta_proof_ok = _terminal_protected_docs_delta_paths(
            root=root,
            plan_ref=plan_ref,
            status_norm=oracle.status_norm,
            docs_status_snapshot=terminal_docs_status_snapshot,
        )
        if not terminal_docs_delta_proof_ok:
            state = "blocked"
            reason = DOCS_DELTA_UNKNOWN_REASON

    no_cycle_staging_proof_unavailable = (
        not followups_capture_cycle_id
        and bool(followups_projection["current_plan_owned_docs_delta_paths"])
    )
    capture_blocked = (
        bool(followups_capture_cycle_id)
        and followups_projection["followups_capture_state"] == "blocked"
    ) or no_cycle_staging_proof_unavailable

    if capture_blocked and terminal_docs_delta_proof_ok and not terminal_protected_paths:
        state = "blocked"
        reason = (
            NO_CYCLE_STAGING_PROOF_UNAVAILABLE_REASON
            if no_cycle_staging_proof_unavailable
            else followups_projection["followups_capture_reason"]
        )

    if not terminal_docs_delta_proof_ok:
        final_docs = {
            "final_docs_commit": "no_op",
            "final_docs_commit_reason": DOCS_DELTA_UNKNOWN_REASON,
            "final_docs_diff_paths": [],
            "protected_docs_delta_paths": [],
        }
    elif terminal_protected_paths:
        final_docs = {
            "final_docs_commit": "required",
            "final_docs_commit_reason": PROTECTED_RECLASSIFICATION_REASON,
            "final_docs_diff_paths": terminal_protected_paths,
            "protected_docs_delta_paths": terminal_protected_paths,
        }
    elif capture_blocked:
        final_docs = {
            "final_docs_commit": "no_op",
            "final_docs_commit_reason": (
                NO_CYCLE_STAGING_PROOF_UNAVAILABLE_REASON
                if no_cycle_staging_proof_unavailable
                else "followup_capture_blocked"
            ),
            "final_docs_diff_paths": [],
            "protected_docs_delta_paths": [],
        }
    elif followups_capture_cycle_id:
        owned_paths = followups_projection["current_plan_owned_docs_delta_paths"]
        blocked_paths = followups_projection["blocked_docs_delta_paths"]
        if followups_projection["followups_capture_state"] == "blocked":
            final_docs = {
                "final_docs_commit": "no_op",
                "final_docs_commit_reason": "followup_capture_blocked",
                "final_docs_diff_paths": [],
                "protected_docs_delta_paths": [],
            }
        elif blocked_paths:
            final_docs = {
                "final_docs_commit": "no_op",
                "final_docs_commit_reason": "followup_capture_blocked",
                "final_docs_diff_paths": [],
                "protected_docs_delta_paths": [],
            }
        elif owned_paths:
            final_docs = {
                "final_docs_commit": "required",
                "final_docs_commit_reason": "current_plan_owned_docs_delta_present",
                "final_docs_diff_paths": list(owned_paths),
                "protected_docs_delta_paths": [],
            }
        elif accepted_red_completed:
            explicit = _clean_value(str(bundle_payload.get("final_docs_commit") or ""))
            final_docs = {
                "final_docs_commit": "landed" if explicit and explicit.lower() == "landed" else "no_op",
                "final_docs_commit_reason": (
                    "accepted_red_routing_docs_landed"
                    if explicit and explicit.lower() == "landed"
                    else "accepted_red_evidence_ref_materialized"
                ),
                "final_docs_diff_paths": [],
                "protected_docs_delta_paths": [],
            }
        else:
            explicit = _clean_value(str(bundle_payload.get("final_docs_commit") or ""))
            final_docs = {
                "final_docs_commit": "landed" if explicit and explicit.lower() == "landed" else "no_op",
                "final_docs_commit_reason": "explicit_bundle_payload" if explicit and explicit.lower() == "landed" else "no_current_plan_owned_docs_delta",
                "final_docs_diff_paths": [],
                "protected_docs_delta_paths": [],
            }
    elif accepted_red_completed:
        explicit = _clean_value(str(bundle_payload.get("final_docs_commit") or ""))
        final_docs = {
            "final_docs_commit": "landed" if explicit and explicit.lower() == "landed" else "no_op",
            "final_docs_commit_reason": (
                "accepted_red_routing_docs_landed"
                if explicit and explicit.lower() == "landed"
                else "accepted_red_evidence_ref_materialized"
            ),
            "final_docs_diff_paths": [],
            "protected_docs_delta_paths": [],
        }
    else:
        final_docs = classify_final_docs_commit(
            root=root,
            state=state,
            bundle_payload=bundle_payload,
            current_plan_owned_docs_paths=followups_projection["current_plan_owned_docs_delta_paths"],
            docs_status_snapshot=terminal_docs_status_snapshot,
        )
    final_docs_commit = final_docs["final_docs_commit"]
    final_docs_commit_reason = final_docs["final_docs_commit_reason"]
    final_docs_diff_paths = final_docs["final_docs_diff_paths"]
    protected_docs_delta_paths = final_docs["protected_docs_delta_paths"]
    pi_capture_state = pi_capture["process_improvement_capture_state"]
    pi_capture_reason = pi_capture["process_improvement_capture_reason"]
    pi_backlog_paths = pi_capture["process_improvement_backlog_paths"]
    pi_advisory = classify_process_improvement_advisory(root)
    pi_advisory_counts = pi_advisory["process_improvement_advisory_counts"]
    followups_reconciliation = classify_followups_reconciliation(root, plan_ref)
    followups_blocked_predecessor_recovery_admission = classify_followups_blocked_predecessor_recovery(root, plan_ref)
    followups_bootstrap_admission = classify_followups_bootstrap_admission(root, plan_ref)
    followups_continuation_admission = classify_followups_continuation_admission(
        root, plan_ref, followups_capture_cycle_id, bundle_payload=bundle_payload, context=context)
    terminal_fast_path = classify_terminal_closeout_fast_path(
        plan_ref=plan_ref,
        state=state,
        closeout_kind=closeout_kind,
        bundle_ok=bundle_ok,
        bundle_errors=list(bundle_payload.get("errors") or []),
        final_docs_commit=final_docs_commit,
        protected_docs_delta_paths=protected_docs_delta_paths,
        process_improvement_capture_state=pi_capture_state,
        process_improvement_receipt_path=pi_capture["process_improvement_receipt_path"],
        followups_reconciliation=followups_reconciliation,
        runtime_context=runtime_context,
    )
    dispatch_context_lines = [
        "Docs closeout context (repo-backed):",
        f"- plan_ref={runtime_context['plan_ref']}",
        f"- semantic_status={runtime_context['semantic_status']}",
        f"- closeout_runtime_class={runtime_context['closeout_runtime_class']}",
        f"- queue_closeout_kind={runtime_context['queue_closeout_kind']}",
        f"- docs_closeout_state={state}",
        f"- docs_closeout_reason={reason}",
        f"- semantic_closeout_kind={closeout_kind}",
        f"- final_docs_commit={final_docs_commit}",
        f"- final_docs_commit_reason={final_docs_commit_reason}",
        f"- final_docs_diff_paths={'|'.join(final_docs_diff_paths) if final_docs_diff_paths else 'none'}",
        f"- protected_docs_delta_paths={'|'.join(protected_docs_delta_paths) if protected_docs_delta_paths else 'none'}",
        f"- followups_capture_state={followups_projection['followups_capture_state']}",
        f"- followups_capture_reason={followups_projection['followups_capture_reason']}",
        f"- followups_capture_cycle_id={followups_projection['followups_capture_cycle_id']}",
        f"- followups_capture_receipt_path={followups_projection['followups_capture_receipt_path']}",
        f"- followups_capture_roles={'|'.join(followups_projection['followups_capture_roles']) if followups_projection['followups_capture_roles'] else 'none'}",
        f"- current_plan_owned_docs_delta_paths={'|'.join(followups_projection['current_plan_owned_docs_delta_paths']) if followups_projection['current_plan_owned_docs_delta_paths'] else 'none'}",
        f"- foreign_docs_delta_paths={'|'.join(followups_projection['foreign_docs_delta_paths']) if followups_projection['foreign_docs_delta_paths'] else 'none'}",
        f"- blocked_docs_delta_paths={'|'.join(followups_projection['blocked_docs_delta_paths']) if followups_projection['blocked_docs_delta_paths'] else 'none'}",
        f"- process_improvement_capture_state={pi_capture_state}",
        f"- process_improvement_capture_reason={pi_capture_reason}",
        f"- process_improvement_capture_roles={'|'.join(pi_capture['process_improvement_capture_roles']) if pi_capture['process_improvement_capture_roles'] else 'none'}",
        f"- process_improvement_backlog_paths={'|'.join(pi_backlog_paths) if pi_backlog_paths else 'none'}",
        f"- process_improvement_receipt_path={pi_capture['process_improvement_receipt_path']}",
        f"- process_improvement_missing_roles={'|'.join(pi_capture['process_improvement_missing_roles']) if pi_capture['process_improvement_missing_roles'] else 'none'}",
        f"- process_improvement_advisory_state={pi_advisory['process_improvement_advisory_state']}",
        f"- process_improvement_advisory_reason={pi_advisory['process_improvement_advisory_reason']}",
        (
            "- process_improvement_advisory_counts="
            f"open={pi_advisory_counts['open']};"
            f"triaged={pi_advisory_counts['triaged']};"
            f"promoted={pi_advisory_counts['promoted']};"
            f"deferred={pi_advisory_counts['deferred']};"
            f"unconfirmed={pi_advisory_counts['unconfirmed']};"
            f"null_execution={pi_advisory_counts['null_execution_rows']};"
            f"delivery_refs={pi_advisory_counts['delivery_ref_rows']}"
        ),
        f"- process_improvement_advisory_proof_host={pi_advisory['process_improvement_advisory_proof_host']}",
        f"- followups_reconciliation_state={followups_reconciliation['state']}",
        f"- followups_reconciliation_reason={followups_reconciliation['reason']}",
        f"- followups_reconciliation_open_items={len(followups_reconciliation['open_items'])}",
        f"- followups_reconciliation_proof_host={followups_reconciliation['proof_host']}",
        f"- followups_bootstrap_admission_schema={followups_bootstrap_admission['schema']}",
        f"- followups_bootstrap_admission_state={followups_bootstrap_admission['state']}",
        f"- followups_bootstrap_admission_reason={followups_bootstrap_admission['reason']}",
        f"- followups_bootstrap_admission_manifest_path={followups_bootstrap_admission['canonical_manifest_path']}",
        f"- followups_bootstrap_admission_source_terminal_commit_oid={followups_bootstrap_admission['source_terminal_commit_oid'] or 'none'}",
        f"- followups_bootstrap_admission_source_plan_blob_oid={followups_bootstrap_admission['source_plan_blob_oid'] or 'none'}",
        f"- followups_bootstrap_admission_source_plan_sha256={followups_bootstrap_admission['source_plan_sha256'] or 'none'}",
        f"- followups_blocked_predecessor_recovery_admission_schema={followups_blocked_predecessor_recovery_admission['schema']}",
        f"- followups_blocked_predecessor_recovery_admission_state={followups_blocked_predecessor_recovery_admission['state']}",
        f"- followups_blocked_predecessor_recovery_admission_reason={followups_blocked_predecessor_recovery_admission['reason']}",
        f"- followups_blocked_predecessor_recovery_predecessor_capture_cycle_id={followups_blocked_predecessor_recovery_admission['predecessor_capture_cycle_id'] or 'none'}",
        *[
            f"- followups_reconciliation_open_item[{idx}]="
            f"{_format_followups_reconciliation_open_item(item)}"
            for idx, item in enumerate(followups_reconciliation["open_items"], start=1)
        ],
        f"- terminal_closeout_fast_path_schema={terminal_fast_path['schema']}",
        f"- terminal_closeout_fast_path_eligible={'true' if terminal_fast_path['eligible'] else 'false'}",
        f"- terminal_closeout_fast_path_reason={terminal_fast_path['reason']}",
        f"- terminal_closeout_fast_path_skipped_lanes={'|'.join(terminal_fast_path['skipped_lanes']) if terminal_fast_path['skipped_lanes'] else 'none'}",
        f"- terminal_closeout_fast_path_fallback_lanes={'|'.join(terminal_fast_path['fallback_lanes']) if terminal_fast_path['fallback_lanes'] else 'none'}",
        f"- terminal_closeout_fast_path_missing_or_dirty={'|'.join(terminal_fast_path['missing_or_dirty_preconditions']) if terminal_fast_path['missing_or_dirty_preconditions'] else 'none'}",
        f"- loop_detected={runtime_context['loop_detected']}",
        f"- repeated_blocker_detected={runtime_context['repeated_blocker_detected']}",
        f"- max_iterations_reached={runtime_context['max_iterations_reached']}",
        f"- latest_stop_reason={runtime_context['latest_stop_reason']}",
        f"- latest_stop_plan={runtime_context['latest_stop_plan']}",
        f"- latest_stop_reason_scope={runtime_context['latest_stop_reason_scope']}",
        f"- latest_stop_item_ref={runtime_context['latest_stop_item_ref']}",
        f"- historical_stop_reason={runtime_context['historical_stop_reason']}",
        f"- historical_stop_plan={runtime_context['historical_stop_plan']}",
        f"- historical_stop_item_ref={runtime_context['historical_stop_item_ref']}",
        f"- terminal_tail_stop_reason={runtime_context['terminal_tail_stop_reason']}",
        f"- terminal_tail_stop_at={runtime_context['terminal_tail_stop_at']}",
        f"- terminal_tail_stop_source_plan={runtime_context['terminal_tail_stop_source_plan']}",
        f"- terminal_tail_stop_source_item_ref={runtime_context['terminal_tail_stop_source_item_ref']}",
        f"- terminal_tail_stop_active_item_ref={runtime_context['terminal_tail_stop_active_item_ref']}",
        f"- latest_blocker_ids={'|'.join(runtime_context['latest_blocker_ids']) if runtime_context['latest_blocker_ids'] else runtime_context['latest_blocker_ids_state']}",
        f"- review_blocker_status={runtime_context['review_blocker_status']}",
        f"- review_blocker_sources={'|'.join(runtime_context['review_blocker_sources']) if runtime_context['review_blocker_sources'] else 'none'}",
        f"- root_cause_class={runtime_context['root_cause_class']}",
        f"- next_owner={runtime_context['next_owner']}",
        f"- extraordinary_action={runtime_context['extraordinary_action']}",
    ]

    dispatch_family = [
        {
            "role": role,
            "lane": lane,
            "prompt_file": prompt_file,
            "wrapper": wrapper,
            "plan_ref": plan_ref,
        }
        for role, lane, prompt_file, wrapper in dispatch_sources
    ]

    payload = {
        "state": state,
        "reason_code": reason,
        "plan_ref": plan_ref,
        "semantic_status": oracle.status_value,
        "semantic_status_norm": oracle.status_norm,
        "semantic_closeout_kind": closeout_kind,
        "bundle_ok": bundle_ok,
        "bundle_errors": list(bundle_payload.get("errors") or []),
        **{
            key: bundle_payload.get(key)
            for key in ACCEPTED_RED_BUNDLE_FIELDS
            if key in bundle_payload
        },
        "accepted_red_routing_docs": (
            [
                plan_ref,
                f"docs/code_drafts/{plan_path.stem}__code_draft.md",
                oracle.accepted_red_historical_review,
                oracle.accepted_red_successor_plan,
            ]
            if accepted_red_source
            else []
        ),
        "final_docs_commit": final_docs_commit,
        "final_docs_commit_reason": final_docs_commit_reason,
        "final_docs_diff_paths": final_docs_diff_paths,
        "protected_docs_delta_paths": protected_docs_delta_paths,
        **{
            key: value
            for key, value in followups_projection.items()
            if key not in {"followups_staging_expectations", "capture_readback"}
        },
        "followups_capture": followups_projection["capture_readback"],
        **pi_capture,
        "process_improvement_advisory": pi_advisory,
        "process_improvement_advisory_state": pi_advisory["process_improvement_advisory_state"],
        "process_improvement_advisory_reason": pi_advisory["process_improvement_advisory_reason"],
        "process_improvement_advisory_counts": pi_advisory_counts,
        "process_improvement_advisory_proof_host": pi_advisory["process_improvement_advisory_proof_host"],
        "process_improvement_advisory_backlog_paths": pi_advisory["process_improvement_advisory_backlog_paths"],
        "process_improvement_advisory_errors": pi_advisory["process_improvement_advisory_errors"],
        "followups_reconciliation": followups_reconciliation,
        "followups_blocked_predecessor_recovery_admission": followups_blocked_predecessor_recovery_admission,
        "followups_bootstrap_admission": followups_bootstrap_admission,
        "followups_continuation_admission": followups_continuation_admission,
        "terminal_closeout_fast_path": terminal_fast_path,
        "runtime_context": runtime_context,
        "dispatch_context_block": "\n".join(dispatch_context_lines),
        "dispatch_family": dispatch_family,
        "process_improvement_seed": {
            "source_ref": plan_ref,
            "docs_closeout_state": state,
            "docs_closeout_reason": reason,
            "semantic_status": oracle.status_value,
            "semantic_closeout_kind": closeout_kind,
            "final_docs_commit": final_docs_commit,
            "final_docs_commit_reason": final_docs_commit_reason,
            "final_docs_diff_paths": final_docs_diff_paths,
            "protected_docs_delta_paths": protected_docs_delta_paths,
            "process_improvement_capture_state": pi_capture_state,
            "process_improvement_capture_reason": pi_capture_reason,
            "process_improvement_capture_roles": pi_capture["process_improvement_capture_roles"],
            "process_improvement_backlog_paths": pi_backlog_paths,
            "process_improvement_receipt_path": pi_capture["process_improvement_receipt_path"],
            "process_improvement_advisory_state": pi_advisory["process_improvement_advisory_state"],
            "process_improvement_advisory_reason": pi_advisory["process_improvement_advisory_reason"],
            "process_improvement_advisory_counts": pi_advisory_counts,
            "process_improvement_advisory_proof_host": pi_advisory["process_improvement_advisory_proof_host"],
            "followups_reconciliation_state": followups_reconciliation["state"],
            "followups_reconciliation_reason": followups_reconciliation["reason"],
            "followups_blocked_predecessor_recovery_admission_state": followups_blocked_predecessor_recovery_admission["state"],
            "followups_blocked_predecessor_recovery_admission_reason": followups_blocked_predecessor_recovery_admission["reason"],
            "followups_bootstrap_admission_state": followups_bootstrap_admission["state"],
            "followups_bootstrap_admission_reason": followups_bootstrap_admission["reason"],
            "terminal_closeout_fast_path_eligible": terminal_fast_path["eligible"],
            "terminal_closeout_fast_path_reason": terminal_fast_path["reason"],
            "terminal_closeout_fast_path_missing_or_dirty": terminal_fast_path["missing_or_dirty_preconditions"],
            "closeout_runtime_class": runtime_context["closeout_runtime_class"],
            "queue_closeout_kind": runtime_context["queue_closeout_kind"],
            "loop_detected": runtime_context["loop_detected"],
            "repeated_blocker_detected": runtime_context["repeated_blocker_detected"],
            "max_iterations_reached": runtime_context["max_iterations_reached"],
            "latest_stop_reason": runtime_context["latest_stop_reason"],
            "latest_stop_plan": runtime_context["latest_stop_plan"],
            "latest_stop_reason_scope": runtime_context["latest_stop_reason_scope"],
            "latest_stop_item_ref": runtime_context["latest_stop_item_ref"],
            "historical_stop_reason": runtime_context["historical_stop_reason"],
            "historical_stop_plan": runtime_context["historical_stop_plan"],
            "historical_stop_item_ref": runtime_context["historical_stop_item_ref"],
            "terminal_tail_stop_reason": runtime_context["terminal_tail_stop_reason"],
            "terminal_tail_stop_at": runtime_context["terminal_tail_stop_at"],
            "terminal_tail_stop_source_plan": runtime_context["terminal_tail_stop_source_plan"],
            "terminal_tail_stop_source_item_ref": runtime_context["terminal_tail_stop_source_item_ref"],
            "terminal_tail_stop_active_item_ref": runtime_context["terminal_tail_stop_active_item_ref"],
            "latest_blocker_ids": runtime_context["latest_blocker_ids"],
            "review_blocker_status": runtime_context["review_blocker_status"],
            "review_blocker_sources": runtime_context["review_blocker_sources"],
            "root_cause_class": runtime_context["root_cause_class"],
            "next_owner": runtime_context["next_owner"],
        },
        "architect_final_handoff": {
            "role": "Architect",
            "required": final_docs_commit == "required"
            and (
                final_docs_commit_reason == PROTECTED_RECLASSIFICATION_REASON
                or not capture_blocked
            ),
            "plan_ref": plan_ref,
            "task": PROTECTED_DOCS_RECLASSIFICATION_TASK
            if final_docs_commit_reason == PROTECTED_RECLASSIFICATION_REASON
            else (
                TERMINAL_DOCS_DELTA_UNKNOWN_TASK
                if not terminal_docs_delta_proof_ok
                else (
                    "After all docs-closeout role passes land, Architect reviews `final_docs_diff_paths` and makes one exact docs-only commit."
                    if final_docs_commit == "required"
                    else (
                        "Do not dispatch Architect or the next queue role: no finalized followups capture proves "
                        "the current owned docs delta."
                        if capture_blocked
                        else "Skip final Architect docs-only handoff; helper proved no pending final docs commit."
                    )
                )
            ),
            "proof_expectation": (
                "After Architect returns, Manager reruns `planveyor_docs_closeout <plan_ref> "
                + (
                    f"--followups-capture-cycle-id {followups_projection['followups_capture_cycle_id']} "
                    if followups_projection["followups_capture_cycle_id"] != "none"
                    else ""
                )
                + "--json` "
                "and may continue only when fresh helper proof is `final_docs_commit=no_op|landed`."
            )
            if final_docs_commit == "required"
            else (
                TERMINAL_DOCS_DELTA_UNKNOWN_PROOF_EXPECTATION
                if not terminal_docs_delta_proof_ok
                else (
                    "Blocked capture is not a green no-op: Manager must stop and rerun only after fresh non-blocked "
                    "`followups_capture_receipt.v1` proof yields `final_docs_commit=no_op|landed`."
                    if capture_blocked
                    else "No Architect handoff required; helper already proved `final_docs_commit=no_op|landed`."
                )
            ),
            "final_docs_diff_paths": final_docs_diff_paths,
            "protected_docs_delta_paths": protected_docs_delta_paths,
            "skip_reason": (
                None
                if final_docs_commit == "required"
                else (
                    DOCS_DELTA_UNKNOWN_REASON
                    if not terminal_docs_delta_proof_ok
                    else ("blocked" if capture_blocked else final_docs_commit)
                )
            ),
            "operational_only": True,
            "followups_staging_expectations": (
                []
                if final_docs_commit_reason
                in {PROTECTED_RECLASSIFICATION_REASON, DOCS_DELTA_UNKNOWN_REASON}
                else followups_projection["followups_staging_expectations"]
            ),
        },
    }
    return finalize_docs_closeout_payload(payload)


def render_text(payload: dict[str, Any]) -> str:
    if payload.get("schema_state") == "blocked":
        return "\n".join(
            [
                "docs-closeout:",
                " state=blocked",
                f" reason={payload.get('reason_code', DOCS_CLOSEOUT_SCHEMA_INVALID_REASON)}",
                f" plan_ref={payload.get('plan_ref', 'unknown')}",
                f" schema={payload.get('schema', DOCS_CLOSEOUT_PAYLOAD_SCHEMA)}",
                " schema_state=blocked",
                f" schema_errors={_format_schema_errors(payload)}",
            ]
        )

    runtime_context = payload["runtime_context"]
    blocker_ids = runtime_context["latest_blocker_ids"]
    followups_reconciliation = payload["followups_reconciliation"]
    followups_blocked_predecessor_recovery_admission = payload["followups_blocked_predecessor_recovery_admission"]
    followups_bootstrap_admission = payload["followups_bootstrap_admission"]
    terminal_fast_path = payload["terminal_closeout_fast_path"]
    pi_advisory_counts = payload["process_improvement_advisory_counts"]
    dispatch_pairs = ",".join(
        f"{entry['role']}:{entry['lane']}" for entry in payload["dispatch_family"]
    )
    return "\n".join(
        [
            "docs-closeout:",
            f" state={payload['state']}",
            f" reason={payload['reason_code']}",
            f" plan_ref={payload['plan_ref']}",
            f" schema={payload['schema']}",
            f" schema_state={payload['schema_state']}",
            f" schema_errors={_format_schema_errors(payload)}",
            f" semantic_status={payload['semantic_status']}",
            f" closeout_runtime_class={runtime_context['closeout_runtime_class']}",
            f" queue_closeout_kind={runtime_context['queue_closeout_kind']}",
            f" semantic_closeout_kind={payload['semantic_closeout_kind']}",
            f" final_docs_commit={payload['final_docs_commit']}",
            f" final_docs_commit_reason={payload['final_docs_commit_reason']}",
            f" final_docs_diff_paths={','.join(payload['final_docs_diff_paths']) if payload['final_docs_diff_paths'] else 'none'}",
            f" protected_docs_delta_paths={','.join(payload['protected_docs_delta_paths']) if payload['protected_docs_delta_paths'] else 'none'}",
            f" followups_capture_state={payload['followups_capture_state']}",
            f" followups_capture_reason={payload['followups_capture_reason']}",
            f" followups_capture_cycle_id={payload['followups_capture_cycle_id']}",
            f" current_plan_owned_docs_delta_paths={','.join(payload['current_plan_owned_docs_delta_paths']) if payload['current_plan_owned_docs_delta_paths'] else 'none'}",
            f" foreign_docs_delta_paths={','.join(payload['foreign_docs_delta_paths']) if payload['foreign_docs_delta_paths'] else 'none'}",
            f" blocked_docs_delta_paths={','.join(payload['blocked_docs_delta_paths']) if payload['blocked_docs_delta_paths'] else 'none'}",
            f" process_improvement_capture_state={payload['process_improvement_capture_state']}",
            f" process_improvement_capture_reason={payload['process_improvement_capture_reason']}",
            f" process_improvement_capture_roles={','.join(payload['process_improvement_capture_roles']) if payload['process_improvement_capture_roles'] else 'none'}",
            f" process_improvement_backlog_paths={','.join(payload['process_improvement_backlog_paths']) if payload['process_improvement_backlog_paths'] else 'none'}",
            f" process_improvement_receipt_path={payload['process_improvement_receipt_path']}",
            f" process_improvement_advisory_state={payload['process_improvement_advisory_state']}",
            f" process_improvement_advisory_reason={payload['process_improvement_advisory_reason']}",
            (
                " process_improvement_advisory_counts="
                f"open={pi_advisory_counts['open']};"
                f"triaged={pi_advisory_counts['triaged']};"
                f"promoted={pi_advisory_counts['promoted']};"
                f"deferred={pi_advisory_counts['deferred']};"
                f"unconfirmed={pi_advisory_counts['unconfirmed']};"
                f"null_execution={pi_advisory_counts['null_execution_rows']};"
                f"delivery_refs={pi_advisory_counts['delivery_ref_rows']}"
            ),
            f" process_improvement_advisory_proof_host={payload['process_improvement_advisory_proof_host']}",
            f" followups_reconciliation_state={followups_reconciliation['state']}",
            f" followups_reconciliation_reason={followups_reconciliation['reason']}",
            f" followups_reconciliation_open_items={len(followups_reconciliation['open_items'])}",
            f" followups_reconciliation_proof_host={followups_reconciliation['proof_host']}",
            f" followups_bootstrap_admission_schema={followups_bootstrap_admission['schema']}",
            f" followups_bootstrap_admission_state={followups_bootstrap_admission['state']}",
            f" followups_bootstrap_admission_reason={followups_bootstrap_admission['reason']}",
            f" followups_bootstrap_admission_manifest_path={followups_bootstrap_admission['canonical_manifest_path']}",
            f" followups_bootstrap_admission_source_terminal_commit_oid={followups_bootstrap_admission['source_terminal_commit_oid'] or 'none'}",
            f" followups_bootstrap_admission_source_plan_blob_oid={followups_bootstrap_admission['source_plan_blob_oid'] or 'none'}",
            f" followups_bootstrap_admission_source_plan_sha256={followups_bootstrap_admission['source_plan_sha256'] or 'none'}",
            f" followups_blocked_predecessor_recovery_admission_schema={followups_blocked_predecessor_recovery_admission['schema']}",
            f" followups_blocked_predecessor_recovery_admission_state={followups_blocked_predecessor_recovery_admission['state']}",
            f" followups_blocked_predecessor_recovery_admission_reason={followups_blocked_predecessor_recovery_admission['reason']}",
            f" followups_blocked_predecessor_recovery_predecessor_capture_cycle_id={followups_blocked_predecessor_recovery_admission['predecessor_capture_cycle_id'] or 'none'}",
            *[
                f" followups_reconciliation_open_item[{idx}]="
                f"{_format_followups_reconciliation_open_item(item)}"
                for idx, item in enumerate(followups_reconciliation["open_items"], start=1)
            ],
            f" terminal_closeout_fast_path_schema={terminal_fast_path['schema']}",
            f" terminal_closeout_fast_path_eligible={'true' if terminal_fast_path['eligible'] else 'false'}",
            f" terminal_closeout_fast_path_reason={terminal_fast_path['reason']}",
            f" terminal_closeout_fast_path_skipped_lanes={','.join(terminal_fast_path['skipped_lanes']) if terminal_fast_path['skipped_lanes'] else 'none'}",
            f" terminal_closeout_fast_path_fallback_lanes={','.join(terminal_fast_path['fallback_lanes']) if terminal_fast_path['fallback_lanes'] else 'none'}",
            f" terminal_closeout_fast_path_missing_or_dirty={','.join(terminal_fast_path['missing_or_dirty_preconditions']) if terminal_fast_path['missing_or_dirty_preconditions'] else 'none'}",
            f" loop_detected={runtime_context['loop_detected']}",
            f" repeated_blocker_detected={runtime_context['repeated_blocker_detected']}",
            f" max_iterations_reached={runtime_context['max_iterations_reached']}",
            f" latest_stop_reason={runtime_context['latest_stop_reason']}",
            f" latest_stop_reason_scope={runtime_context['latest_stop_reason_scope']}",
            f" historical_stop_reason={runtime_context['historical_stop_reason']}",
            f" terminal_tail_stop_reason={runtime_context['terminal_tail_stop_reason']}",
            f" terminal_tail_stop_source_plan={runtime_context['terminal_tail_stop_source_plan']}",
            f" terminal_tail_stop_source_item_ref={runtime_context['terminal_tail_stop_source_item_ref']}",
            f" terminal_tail_stop_active_item_ref={runtime_context['terminal_tail_stop_active_item_ref']}",
            f" latest_blocker_ids={','.join(blocker_ids) if blocker_ids else runtime_context['latest_blocker_ids_state']}",
            f" review_blocker_status={runtime_context['review_blocker_status']}",
            f" review_blocker_sources={','.join(runtime_context['review_blocker_sources']) if runtime_context['review_blocker_sources'] else 'none'}",
            f" root_cause_class={runtime_context['root_cause_class']}",
            f" next_owner={runtime_context['next_owner']}",
            f" dispatch_family={dispatch_pairs}",
        ]
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="docs_closeout",
        description="Classify manager docs-closeout state from repo-backed closeout and queue carriers.",
    )
    parser.add_argument("--project-root", default=".", help="Repository root.")
    # Preserve the shell-facing physical identity argument while keeping it out
    # of source selection.  The effective scalar below is the only selector.
    parser.add_argument("--repo-profile-id", default=None, help=argparse.SUPPRESS)
    parser.add_argument(
        "--content-profile-id",
        default="default",
        choices=tuple(sorted(CONTENT_PROFILE_IDS)),
        help="Effective content profile for docs-closeout dispatch sources.",
    )
    parser.add_argument("--plan", required=True, help="Plan path relative to the repository root.")
    parser.add_argument(
        "--bundle-json",
        default="-",
        help="Path to JSON emitted by planveyor_plan_bundle --closeout-json, or '-' to read stdin.",
    )
    parser.add_argument(
        "--followups-capture-cycle-id",
        default=None,
        help="Exact Manager-fed followups capture UUIDv4 for post-family ownership proof.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON payload instead of text.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    root = Path(args.project_root).resolve()
    try:
        authority_context = resolve_top_level_context(root)
        validate_before_effect(authority_context)
    except ContractAuthorityError as exc:
        payload = {
            "schema": DOCS_CLOSEOUT_PAYLOAD_SCHEMA,
            "schema_state": "blocked",
            "schema_errors": [f"contract_authority: {exc}"],
            "state": "blocked",
            "reason_code": "contract_authority_unavailable",
            "plan_ref": args.plan,
        }
        if args.json:
            sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        else:
            sys.stderr.write(f"docs_closeout: {exc}\n")
        return 1
    plan_ref = plan_queue.project_relative_path(root, args.plan, require_exists=True)
    if args.bundle_json == "-":
        bundle_json = sys.stdin.read()
    else:
        bundle_json = Path(args.bundle_json).read_text(encoding="utf-8")

    try:
        payload = classify_docs_closeout(
            plan_ref=plan_ref,
            bundle_payload=load_bundle_payload(bundle_json),
            root=root,
            followups_capture_cycle_id=args.followups_capture_cycle_id,
            content_profile_id=args.content_profile_id,
            context=authority_context,
        )
    except ContractAuthorityError as exc:
        payload = {
            "schema": DOCS_CLOSEOUT_PAYLOAD_SCHEMA,
            "schema_state": "blocked",
            "schema_errors": [f"contract_authority: {exc}"],
            "state": "blocked",
            "reason_code": "contract_authority_unavailable",
            "plan_ref": plan_ref,
        }
        if args.json:
            sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        else:
            sys.stderr.write(f"docs_closeout: {exc}\n")
        return 1
    except ProfilePromptError as exc:
        payload = {
            "schema": DOCS_CLOSEOUT_PAYLOAD_SCHEMA,
            "schema_state": "blocked",
            "schema_errors": [str(exc)],
            "state": "blocked",
            "reason_code": "profile_prompt_unavailable",
            "plan_ref": plan_ref,
        }
        if args.json:
            sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        else:
            sys.stderr.write(f"docs_closeout: {exc}\n")
        return 1
    except plan_queue.QueueError as exc:
        queue_error = dict(exc.payload or {})
        payload = {
            "schema": DOCS_CLOSEOUT_PAYLOAD_SCHEMA,
            "schema_state": "blocked",
            "schema_errors": [f"queue_runtime_context: {exc}"],
            "state": "blocked",
            "reason_code": "queue_runtime_context_unavailable",
            "plan_ref": plan_ref,
            "queue_error": queue_error,
        }
        if args.json:
            sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        else:
            sys.stdout.write(
                "docs_closeout: state=blocked reason=queue_runtime_context_unavailable "
                f"plan_ref={plan_ref} queue_error={queue_error.get('error') or 'unknown'}\n"
            )
        return 1
    if args.json:
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    else:
        sys.stdout.write(render_text(payload) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

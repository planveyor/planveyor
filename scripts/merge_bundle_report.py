#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from post_merge_packetization_gate import (
    BLOCKING_COVERAGES,
    resolve_recovery_lineage,
    resolve_target_applicability,
    same_range_report_paths,
)
from shared_docs_mirror_drift import (
    GENERIC_MIRROR_POLICY,
    MirrorPolicy,
    MirrorPolicyError,
    load_shared_docs_mirror_policy,
)
from post_merge_packetization_gate import (
    PACKETIZATION_GATE_RECEIPT_KIND,
    PACKETIZATION_GATE_RECEIPT_NAME,
    PACKETIZATION_GATE_SCHEMA_VERSION,
    PACKETIZATION_GATE_STEP,
)
from rollout_packet import _resolve_current_delivery_packet_path, _validate_current_delivery_packet
from post_merge_operational_receipt import (
    SCHEMA_VERSION as OPERATIONAL_RECEIPT_SCHEMA_VERSION,
    validate_followups_triage_command_surface,
)
from plan_harvest_lint import parse_plan_harvest_file_followups_receipt
import range_review_risk_packet
import post_merge_audit_lint
import retrieval_telemetry_receipt
import merge_gate_policy


STEP_LINE_RE = re.compile(
    r"^(?P<prefix>\s*[-*]\s*\[)(?P<mark>[ xX])(?P<suffix>\]\s+)(?P<key>step:[^\s#]+)(?P<rest>.*)$"
)
STATUS_RE = re.compile(r"^\*\*Status:\*\*\s*(?P<value>.+?)\s*$")
HEADER_RE = re.compile(r"^(?P<key>[A-Z_]+)=(?P<value>.*)$")
FOLLOWUPS_HEADER_FIELD_RE = re.compile(
    r"^\s*(?:[-*]\s*)?\*\*(?P<key>[^:*]+):\*\*\s*(?P<value>.+?)\s*$",
    re.IGNORECASE,
)
FOLLOWUPS_PLAN_HARVEST_FILENAME_RE = re.compile(
    r"^\d{6}_\d{4}_followups_range_[0-9a-f]{7}_[0-9a-f]{7}\.md$",
    re.IGNORECASE,
)
FOLLOWUPS_POST_MERGE_AUDIT_FILENAME_RE = re.compile(
    r"^\d{6}_\d{4}_post_merge_audit_followups_range_[0-9a-f]{7}_[0-9a-f]{7}\.md$",
    re.IGNORECASE,
)
ARTIFACT_FILENAME_TIMESTAMP_RE = re.compile(r"(?P<stamp>\d{6}_\d{4})")
DOCS_FINALIZE_RECEIPT_PATH_RE = re.compile(
    r"^docs/reviews/(?P<stamp>\d{6}_\d{4})_docs_finalize_receipt_range_"
    r"(?P<base>[0-9a-f]{7})_(?P<head>[0-9a-f]{7})\.md$"
)
DOCS_FINALIZE_RANGE_COMPONENT_RE = re.compile(r"^[0-9a-f]{7,64}$")
DOCS_FINALIZE_RECEIPT_KIND = "docs_finalize_receipt"


@dataclass(frozen=True)
class ArtifactSpec:
    step: str
    kind: str
    pattern_template: str
    required_for_completed: bool = True
    require_final_status: bool = True

    def pattern(self, base_short: str, head_short: str) -> str:
        return self.pattern_template.format(base_short=base_short, head_short=head_short)


@dataclass(frozen=True)
class ReceiptSpec:
    step: str
    kind: str
    name: str
    tokens: tuple[str, ...]
    expected_surface: str
    only_when_packetization_required: bool = False


@dataclass(frozen=True)
class FollowupsBacklogClassification:
    path: str
    role: str
    source: str
    imported_into: str
    error: str = ""


@dataclass(frozen=True)
class PacketizationReportPayload:
    payload: dict[str, Any]
    structural_present: bool = False
    error: dict[str, str] | None = None


CANON_SWEEP_RECEIPT_KIND = "canon_sweep_receipt"
CANON_SWEEP_RECEIPT_ALLOWED_PROOF_KINDS = {"snapshot", "report", "no_op"}
CANON_SWEEP_RECEIPT_ALLOWED_TARGET_IMPACTS = {
    "source_only",
    "shared_consumer",
    "shared_multi",
    "none",
}
CANON_SWEEP_RECEIPT_CLOSURE_FIELDS = ("snapshot_path", "report_path", "no_op_reason")

ARTIFACT_SPECS: tuple[ArtifactSpec, ...] = (
    ArtifactSpec(
        step="step:review_range",
        kind="review_plan",
        pattern_template="docs/plans/*_reviewer_range_{base_short}_{head_short}.md",
    ),
    ArtifactSpec(
        step="step:review_range",
        kind="review_code_draft",
        pattern_template="docs/code_drafts/*_reviewer_range_{base_short}_{head_short}__code_draft.md",
        require_final_status=False,
    ),
    ArtifactSpec(
        step="step:review_range",
        kind="review_artifact",
        pattern_template="docs/code_reviews/*_reviewer_range_{base_short}_{head_short}.md",
    ),
    ArtifactSpec(
        step="step:merge_notes",
        kind="merge_notes",
        pattern_template="docs/reviews/*_merge_notes_range_{base_short}_{head_short}.md",
    ),
    ArtifactSpec(
        step="step:plan_harvest",
        kind="plan_harvest",
        pattern_template="docs/reviews/*_plan_harvest_range_{base_short}_{head_short}.md",
    ),
    ArtifactSpec(
        step="step:plan_harvest",
        kind="followups_backlog",
        pattern_template="docs/followups/*_followups_range_{base_short}_{head_short}.md",
    ),
    ArtifactSpec(
        step="step:canon_sweep",
        kind="canon_snapshot",
        pattern_template="docs/snapshots/*range_{base_short}_{head_short}*",
        required_for_completed=False,
        require_final_status=False,
    ),
    ArtifactSpec(
        step="step:canon_sweep",
        kind=CANON_SWEEP_RECEIPT_KIND,
        pattern_template="docs/reviews/*_canon_sweep_receipt_range_{base_short}_{head_short}.md",
        required_for_completed=False,
    ),
    ArtifactSpec(
        step=PACKETIZATION_GATE_STEP,
        kind=PACKETIZATION_GATE_RECEIPT_KIND,
        pattern_template="docs/reviews/*_packetization_gate_range_{base_short}_{head_short}.md",
    ),
    ArtifactSpec(
        step="step:post_merge_audit",
        kind="post_merge_audit",
        pattern_template="docs/reviews/*_post_merge_audit_range_{base_short}_{head_short}.md",
    ),
    ArtifactSpec(
        step="step:docs_finalize",
        kind=DOCS_FINALIZE_RECEIPT_KIND,
        pattern_template="docs/reviews/*_docs_finalize_receipt_range_{base_short}_{head_short}.md",
    ),
    ArtifactSpec(
        step="step:ready_to_push",
        kind="post_merge_operational_receipt",
        pattern_template="docs/reviews/*_post_merge_operational_receipt_range_{base_short}_{head_short}.md",
    ),
    ArtifactSpec(
        step="step:ready_to_push",
        kind="ready_to_push_closeout_receipt",
        pattern_template="docs/reviews/*_ready_to_push_closeout_range_{base_short}_{head_short}.md",
        required_for_completed=False,
    ),
)

RECEIPT_SPECS: tuple[ReceiptSpec, ...] = (
    ReceiptSpec(
        step="step:plan_harvest",
        kind="plan_harvest",
        name="followup_harvest_triage_import",
        tokens=("Follow-up harvest triage/import receipt",),
        expected_surface="`## Follow-up harvest triage/import receipt` in the plan-harvest report",
    ),
    ReceiptSpec(
        step="step:plan_harvest",
        kind="plan_harvest",
        name="process_improvement_decision_state",
        tokens=("Process-improvement promotion decisions",),
        expected_surface="`## Process-improvement promotion decisions` with helper-backed row state",
    ),
    ReceiptSpec(
        step="step:plan_harvest",
        kind="plan_harvest",
        name="docs_retrieval_metrics",
        tokens=("Docs retrieval metrics receipt", "query_total", "evaluated_total", "read_log_status", "read_events_total"),
        expected_surface="`## Docs retrieval metrics receipt` with parseable query/read summary values",
    ),
    ReceiptSpec(
        step="step:plan_harvest",
        kind="plan_harvest",
        name="golden_path_lane",
        tokens=("Golden Path lane receipt",),
        expected_surface="`## Golden Path lane receipt` citing `docs/guides/golden_paths.md` anchors",
    ),
    ReceiptSpec(
        step="step:plan_harvest",
        kind="plan_harvest",
        name="adr_key_decisions",
        tokens=("ADR candidates / durable decisions",),
        expected_surface="`## ADR candidates / durable decisions` or explicit no-op reason",
    ),
    ReceiptSpec(
        step="step:plan_harvest",
        kind="plan_harvest",
        name="canon_followup_summary",
        tokens=("Follow-ups (extracted", "Canon/follow-up summary"),
        expected_surface="follow-up/canon outcome summary in the plan-harvest report",
    ),
    ReceiptSpec(
        step="step:plan_harvest",
        kind="plan_harvest",
        name=PACKETIZATION_GATE_RECEIPT_NAME,
        tokens=(PACKETIZATION_GATE_STEP,),
        expected_surface=f"packetization handoff/readback line containing `{PACKETIZATION_GATE_STEP}`",
        only_when_packetization_required=True,
    ),
    ReceiptSpec(
        step="step:post_merge_audit",
        kind="post_merge_audit",
        name="audit_matrix",
        tokens=("Audit matrix",),
        expected_surface="audit matrix section in the post-merge audit report",
    ),
    ReceiptSpec(
        step="step:post_merge_audit",
        kind="post_merge_audit",
        name="role_quality_matrix",
        tokens=("Role-quality", "Role assessment"),
        expected_surface="role-quality/role-assessment receipt in the post-merge audit report",
    ),
    ReceiptSpec(
        step="step:post_merge_audit",
        kind="post_merge_audit",
        name="followup_harvest_triage_import",
        tokens=("Follow-up harvest triage/import receipt",),
        expected_surface="post-merge audit citation of the harvest triage/import receipt",
    ),
    ReceiptSpec(
        step="step:post_merge_audit",
        kind="post_merge_audit",
        name="process_improvement_decision_state",
        tokens=("Process-improvement promotion decisions",),
        expected_surface="post-merge audit citation of process-improvement decision-state receipt",
    ),
    ReceiptSpec(
        step="step:post_merge_audit",
        kind="post_merge_audit",
        name="docs_retrieval_metrics",
        tokens=("Docs retrieval metrics receipt",),
        expected_surface="post-merge audit citation or local section for docs retrieval metrics",
    ),
    ReceiptSpec(
        step="step:post_merge_audit",
        kind="post_merge_audit",
        name=PACKETIZATION_GATE_RECEIPT_NAME,
        tokens=(PACKETIZATION_GATE_STEP,),
        expected_surface=f"post-merge audit packetization receipt citation containing `{PACKETIZATION_GATE_STEP}`",
        only_when_packetization_required=True,
    ),
)

RECEIPT_PREFLIGHT_SCHEMA_VERSION = "post_merge_receipt_preflight.v1"
RECEIPT_PREFLIGHT_STEPS = (
    "plan_harvest",
    "canon_sweep",
    "post_merge_audit",
    "packetization_gate",
    "docs_finalize",
)

NO_COMMITTED_ARTIFACT_STEPS = {
    "step:doc_lint",
    "step:docs_hygiene_archive",
    "step:docs_hygiene_suggest",
}

OPERATIONAL_RECEIPT_KIND = "post_merge_operational_receipt"
READY_TO_PUSH_CLOSEOUT_RECEIPT_KIND = "ready_to_push_closeout_receipt"
READY_TO_PUSH_CLOSEOUT_SCHEMA_VERSION = "ready_to_push_closeout_receipt.v1"
READY_TO_PUSH_TERMINAL_STATE = "terminal_ready_to_push_proof"
READY_TO_PUSH_PRE_TERMINAL_STATE = "pre_terminal_missing_allowed"
READY_TO_PUSH_CLOSEOUT_REQUIRED_AFTER = "2026-06-07T11:20:00+00:00"
READY_TO_PUSH_CLOSEOUT_REQUIRED_AFTER_DT = datetime.fromisoformat(
    READY_TO_PUSH_CLOSEOUT_REQUIRED_AFTER
).astimezone(timezone.utc)
READY_TO_PUSH_CLOSEOUT_JSON_HEADING = "Ready-to-push closeout receipt JSON"
READY_TO_PUSH_CLOSEOUT_EXPECTED_SURFACE = (
    "ready_to_push_closeout_receipt.v1 JSON with range/base/head, final_bundle_status=ok, "
    "terminal_state=terminal_ready_to_push_proof, accepted paths, clean git state buckets, "
    "tracker tick intent/result and pending_owner_gate=git push"
)
READY_TO_PUSH_CLOSEOUT_PATH_LIST_FIELDS = (
    "required_paths",
    "contextual_paths",
    "staged_accepted_paths",
    "unexpected_staged_paths",
    "suspicious_paths",
    "unstaged_tracked_paths",
    "untracked_accepted_paths",
)
READY_TO_PUSH_CLOSEOUT_TRACKER_TICK_RESULTS = {"ticked", "already_ticked"}
OPERATIONAL_RECEIPT_STEPS = {
    "docs_finalize",
    "doc_lint",
    "docs_hygiene_archive",
    "docs_hygiene_suggest",
    "docs_index_context",
    "retrieval_metrics",
    "followups_triage_launch",
    "canon_sweep",
    "planveyor_merge_bundle_report",
}
OPERATIONAL_RECEIPT_STEP_FIELDS = {
    "step",
    "command",
    "artifact_path",
    "count_summary",
    "no_op_reason",
    "in_scope",
    "captured_at",
    "source",
}
OPERATIONAL_RECEIPT_TRIGGER_STEPS = {
    "step:docs_finalize",
    "step:doc_lint",
    "step:docs_hygiene_archive",
    "step:docs_hygiene_suggest",
}
OPERATIONAL_RECEIPT_EXPECTED_SURFACE = (
    "schema_version/range/base/head/tracker_path, archive snapshot backend/manifest/artifact/object/checksum/"
    "format/access/export/source-db/restore/readback/no-op/blocker fields, and per-step command/result/artifact/count/"
    "no-op/in-scope/timestamp/source rows; docs_hygiene_suggest_summary with report_only/deletion flags, "
    "candidate counts, top candidates and omitted count; docs_index_context plans/followups coverage or closed no-op; "
    "process_improvements_open_summary with ordinary followups result, separate lane status, raw PI counts, "
    "null execution count and source decision receipt path; "
    "followups_lane_reconciliation with file-lane result, range-lane counts, durable decision refs and owner summary; "
    "retrieval_metrics rates with used_for_decision plus follow-up/accepted no-op for low decision-used coverage "
    "or accepted_no_op_reason=not_used_for_decision for telemetry-only metrics; followups_triage_launch_receipt command/count/"
    "index readback; clean committed pre-enforcement legacy "
    "receipts without archive_snapshot/docs quality rows or with old-schema archive_snapshot rows are compatibility-only history"
)
ARCHIVE_SNAPSHOT_STATUSES = {"ok", "no_op", "blocked"}
ARCHIVE_SNAPSHOT_BACKENDS = {"git_text_export", "git_whole_sqlite", "s3_minio_sqlite"}
ARCHIVE_SNAPSHOT_FIELDS = {
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
}
ARCHIVE_SNAPSHOT_FRESH_EXPORT_FIELDS = {
    "export_command",
    "export_status",
    "snapshot_created_at_utc",
    "snapshot_source_db_sha256",
    "snapshot_source_docs_count",
}
# Receipts generated before the archive_snapshot receipt field landed remain valid
# historical closeout artifacts. New/current receipts must carry archive_snapshot.
ARCHIVE_SNAPSHOT_RECEIPT_REQUIRED_AFTER = "2026-05-18T19:30:00+00:00"
ARCHIVE_SNAPSHOT_RECEIPT_REQUIRED_AFTER_DT = datetime.fromisoformat(
    ARCHIVE_SNAPSHOT_RECEIPT_REQUIRED_AFTER
).astimezone(timezone.utc)
ARCHIVE_SNAPSHOT_FRESH_EXPORT_REQUIRED_AFTER = "2026-06-07T09:30:00+00:00"
ARCHIVE_SNAPSHOT_FRESH_EXPORT_REQUIRED_AFTER_DT = datetime.fromisoformat(
    ARCHIVE_SNAPSHOT_FRESH_EXPORT_REQUIRED_AFTER
).astimezone(timezone.utc)
DOCS_INDEX_CONTEXT_RECEIPT_REQUIRED_AFTER = "2026-05-19T07:00:00+00:00"
DOCS_INDEX_CONTEXT_RECEIPT_REQUIRED_AFTER_DT = datetime.fromisoformat(
    DOCS_INDEX_CONTEXT_RECEIPT_REQUIRED_AFTER
).astimezone(timezone.utc)
DOCS_HYGIENE_SUGGEST_SUMMARY_REQUIRED_AFTER = "2026-05-19T11:30:00+00:00"
DOCS_HYGIENE_SUGGEST_SUMMARY_REQUIRED_AFTER_DT = datetime.fromisoformat(
    DOCS_HYGIENE_SUGGEST_SUMMARY_REQUIRED_AFTER
).astimezone(timezone.utc)
FOLLOWUPS_TRIAGE_LAUNCH_RECEIPT_REQUIRED_AFTER = "2026-05-19T12:40:00+00:00"
FOLLOWUPS_TRIAGE_LAUNCH_RECEIPT_REQUIRED_AFTER_DT = datetime.fromisoformat(
    FOLLOWUPS_TRIAGE_LAUNCH_RECEIPT_REQUIRED_AFTER
).astimezone(timezone.utc)
PROCESS_IMPROVEMENTS_OPEN_SUMMARY_REQUIRED_AFTER = "2026-06-06T20:42:00+00:00"
PROCESS_IMPROVEMENTS_OPEN_SUMMARY_REQUIRED_AFTER_DT = datetime.fromisoformat(
    PROCESS_IMPROVEMENTS_OPEN_SUMMARY_REQUIRED_AFTER
).astimezone(timezone.utc)
FOLLOWUPS_LANE_RECONCILIATION_REQUIRED_AFTER = "2026-06-18T07:55:00+00:00"
FOLLOWUPS_LANE_RECONCILIATION_REQUIRED_AFTER_DT = datetime.fromisoformat(
    FOLLOWUPS_LANE_RECONCILIATION_REQUIRED_AFTER
).astimezone(timezone.utc)
PROCESS_IMPROVEMENTS_OPEN_SUMMARY_FIELD = "process_improvements_open_summary"
PROCESS_IMPROVEMENTS_OPEN_SUMMARY_STATUSES = ("open", "triaged", "promoted")
PROCESS_IMPROVEMENT_DECISIONS_HEADING = "## Process-improvement promotion decisions"
FOLLOWUPS_HARVEST_TRIAGE_HEADING = "## Follow-up harvest triage/import receipt"
FOLLOWUPS_HARVEST_TRIAGE_ANCHOR = "follow-up-harvest-triageimport-receipt"
PROCESS_IMPROVEMENT_DECISIONS_ANCHOR = "process-improvement-promotion-decisions"
PROCESS_IMPROVEMENT_FIELD_ASSIGNMENT_RE = re.compile(
    r"(?P<key>[A-Za-z][A-Za-z0-9_-]*)\s*(?:=|:)\s*(?:`(?P<backtick>[^`]*)`|(?P<bare>[^;|]+))",
    re.IGNORECASE,
)
DOCS_HYGIENE_SUGGEST_CANDIDATE_COUNT_FIELDS = {
    "terminal_plans",
    "safe_review_code_drafts",
    "blocked_review_code_drafts",
    "blocked_missing_review_code_drafts",
    "done_followups",
    "blocked_followups",
    "canon_blocked_items",
    "suggested_git_rm_paths",
    "suggested_asset_dirs",
    "suggested_owner_command_items",
}
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
FOLLOWUPS_TRIAGE_LAUNCH_REQUIRED_FIELDS = (
    "source_harvest_receipt_path",
    "triage_mode",
    "index_rebuild_status",
    "readback_status",
    "index_path",
    "process_improvements_lane",
)
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
DISALLOWED_ARCHIVE_NO_OP_REASONS = {
    "current_db_migration_failed",
    "helper_failed",
    "snapshot_failed",
    "restore_failed",
    "checksum_mismatch",
    "object_access_failed",
    "missing_manifest",
}
ARCHIVE_SHA256_RE = re.compile(r"^(?:sha256:)?[a-f0-9]{64}$")
ARCHIVE_ENUM_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
CHECKLIST_ERROR_DETAIL_RE = re.compile(r"^(?P<step>step:[^/\s]+)/(?P<receipt>[^:]+):")
GIT_DIAGNOSTIC_TIMEOUT_SECONDS = 30
GIT_TIMEOUT_RETURN_CODE = 124


def _operator_source_command(step: str, receipt: str) -> str:
    if step == "step:plan_harvest":
        return "update the plan-harvest report artifact"
    if step == "step:post_merge_audit":
        return "update the post-merge audit report artifact"
    if step == "step:canon_sweep":
        return "planveyor_arch_canon_sweep_start"
    if step == "step:ready_to_push" and receipt == "post_merge_operational_closeout":
        return "planveyor_post_merge_operational_receipt --help"
    if step == "step:ready_to_push" and receipt == "ready_to_push_terminal_proof":
        return "planveyor_post_merge_ready_to_push_closeout"
    return "inspect planveyor_merge_bundle_report error detail"


def _operator_next_action(status: str, step: str, receipt: str) -> str:
    if status == "ok":
        return "N/A (already present)"
    if status == "advisory":
        return "inspect planveyor_merge_bundle_report error detail"
    if step == "step:plan_harvest":
        return (
            "add/fix the named receipt section in "
            "docs/reviews/*_plan_harvest_range_<base7>_<head7>.md, then rerun "
            "planveyor_merge_bundle_report"
        )
    if step == "step:post_merge_audit":
        return (
            "add/fix the named receipt citation/section in "
            "docs/reviews/*_post_merge_audit_range_<base7>_<head7>.md, then rerun "
            "planveyor_merge_bundle_report"
        )
    if step == "step:canon_sweep":
        return (
            "materialize/fix docs/snapshots/*range_<base7>_<head7>* or "
            "docs/reviews/*_canon_sweep_receipt_range_<base7>_<head7>.md with final status, "
            "then rerun planveyor_merge_bundle_report"
        )
    if step == "step:ready_to_push" and receipt == "post_merge_operational_closeout":
        return (
            "create/fix committed docs/reviews/*_post_merge_operational_receipt_range_<base7>_<head7>.md, "
            "then rerun planveyor_merge_bundle_report"
        )
    if step == "step:ready_to_push" and receipt == "ready_to_push_terminal_proof":
        return (
            "materialize/fix docs/reviews/*_ready_to_push_closeout_range_<base7>_<head7>.md only "
            "when terminal closeout is required, then rerun planveyor_merge_bundle_report"
        )
    return "inspect planveyor_merge_bundle_report error detail"


def _receipt_error_key(error: dict[str, str]) -> tuple[str, str] | None:
    detail = str(error.get("detail") or "")
    match = CHECKLIST_ERROR_DETAIL_RE.match(detail)
    if not match:
        return None
    return match.group("step"), match.group("receipt")


def _operator_status_for_error(code: str) -> str:
    if code == "missing_required_receipt":
        return "missing"
    if code == "inconsistent_receipt":
        return "inconsistent"
    return "advisory"


def build_operator_receipt_checklist(
    substep_receipts: list[dict[str, Any]],
    errors: list[dict[str, str]],
) -> list[dict[str, Any]]:
    errors_by_key: dict[tuple[str, str], list[dict[str, str]]] = {}
    unmatched_errors: list[dict[str, str]] = []
    for error in errors:
        key = _receipt_error_key(error)
        if key is None:
            unmatched_errors.append(error)
            continue
        errors_by_key.setdefault(key, []).append(error)

    rows: list[dict[str, Any]] = []
    matched_keys: set[tuple[str, str]] = set()
    for receipt in substep_receipts:
        step = str(receipt.get("step") or "")
        receipt_name = str(receipt.get("receipt") or "")
        key = (step, receipt_name)
        matching_errors = errors_by_key.get(key, [])
        if matching_errors:
            matched_keys.add(key)
            primary_error = matching_errors[0]
            blocker_code = str(primary_error.get("code") or "unknown")
            status = _operator_status_for_error(blocker_code)
            error_detail = str(primary_error.get("detail") or "")
        elif receipt.get("present"):
            blocker_code = "N/A"
            status = "ok"
            error_detail = ""
        else:
            blocker_code = "missing_required_receipt"
            status = "missing"
            error_detail = "receipt marked missing without a matching error"

        rows.append(
            {
                "step": step,
                "kind": receipt.get("kind") or "",
                "receipt": receipt_name,
                "status": status,
                "blocker_code": blocker_code,
                "source_artifact": receipt.get("path") or "(none)",
                "source_command": _operator_source_command(step, receipt_name),
                "next_action": _operator_next_action(status, step, receipt_name),
                "expected_surface": receipt.get("expected_surface") or "",
                "error_detail": error_detail,
                "matched_error_count": len(matching_errors),
            }
        )

    for error in unmatched_errors:
        key = _receipt_error_key(error)
        step, receipt_name = key if key is not None else ("unknown", "unmatched_error")
        rows.append(
            {
                "step": step,
                "kind": "unmatched_error",
                "receipt": receipt_name,
                "status": "advisory",
                "blocker_code": str(error.get("code") or "unknown"),
                "source_artifact": "(see error detail)",
                "source_command": "inspect planveyor_merge_bundle_report error detail",
                "next_action": "inspect planveyor_merge_bundle_report error detail",
                "expected_surface": "",
                "error_detail": str(error.get("detail") or ""),
                "matched_error_count": 1,
            }
        )

    for key, key_errors in errors_by_key.items():
        if key in matched_keys:
            continue
        step, receipt_name = key
        primary_error = key_errors[0]
        rows.append(
            {
                "step": step,
                "kind": "unmatched_error",
                "receipt": receipt_name,
                "status": "advisory",
                "blocker_code": str(primary_error.get("code") or "unknown"),
                "source_artifact": "(see error detail)",
                "source_command": _operator_source_command(step, receipt_name),
                "next_action": "inspect planveyor_merge_bundle_report error detail",
                "expected_surface": "",
                "error_detail": str(primary_error.get("detail") or ""),
                "matched_error_count": len(key_errors),
            }
        )

    return rows


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _git_timeout_detail(args: tuple[str, ...], timeout: float | int) -> str:
    return f"git {' '.join(args)} timed out after {timeout:g}s"


def _run_git(root: Path, *args: str) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            text=True,
            capture_output=True,
            check=False,
            timeout=GIT_DIAGNOSTIC_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        return (
            GIT_TIMEOUT_RETURN_CODE,
            stdout,
            _git_timeout_detail(args, GIT_DIAGNOSTIC_TIMEOUT_SECONDS),
        )
    return proc.returncode, proc.stdout, proc.stderr


def _read_range_value(path: Path) -> str | None:
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        return line
    return None


def _parse_tracker(path: Path) -> tuple[dict[str, str], list[dict[str, Any]]]:
    header: dict[str, str] = {}
    steps: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        header_match = HEADER_RE.match(line.strip())
        if header_match:
            header[header_match.group("key")] = header_match.group("value").strip()
            continue
        step_match = STEP_LINE_RE.match(line)
        if step_match:
            steps.append(
                {
                    "key": step_match.group("key").strip(),
                    "checked": step_match.group("mark").lower() == "x",
                }
            )
    return header, steps


def _expected_tracker_header(root: Path, *, base: str, head: str) -> dict[str, str]:
    expected: dict[str, str] = {}
    if base:
        expected["BASE"] = base
    if head:
        expected["HEAD"] = head
    merge = _read_range_value(root / ".planveyor.range.merge")
    if merge:
        expected["MERGE_SHA"] = merge
    if base and head:
        expected["RANGE"] = f"{base}..{head}"
        expected["RANGE_ID"] = f"range_{base[:7]}_{head[:7]}"
    return expected


def _tracker_header_consistency_errors(
    *,
    root: Path,
    tracker_header: dict[str, str],
    base: str,
    head: str,
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for field, expected in _expected_tracker_header(root, base=base, head=head).items():
        actual = tracker_header.get(field)
        if actual is None:
            errors.append(
                {
                    "code": "tracker_header_missing",
                    "detail": f"{field}: expected={expected}",
                }
            )
        elif actual != expected:
            errors.append(
                {
                    "code": "tracker_header_mismatch",
                    "detail": f"{field}: tracker={actual}; saved={expected}",
                }
            )
    return errors


def _first_unchecked(steps: list[dict[str, Any]]) -> str:
    for step in steps:
        if not step["checked"]:
            return str(step["key"])
    return ""


def _extract_status(path: Path) -> str | None:
    try:
        lines = _read_text(path).splitlines()
    except FileNotFoundError:
        return None
    for line in lines[:40]:
        match = STATUS_RE.match(line.strip())
        if match:
            return match.group("value").strip()
    return None


def _is_final_status(value: str | None) -> bool:
    if value is None:
        return False
    norm = value.lower().replace("✅", "").strip()
    return norm.startswith("ok") or norm.startswith("done") or norm.startswith("superseded")


def _is_superseded_packetization_status(value: str | None) -> bool:
    return value == "Superseded"


def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _find_matches(root: Path, pattern: str) -> list[str]:
    return sorted(_rel(path, root) for path in root.glob(pattern) if path.is_file())


def _extract_followups_header_field(text: str, field_names: set[str]) -> str:
    normalized_names = {field.casefold() for field in field_names}
    for line in text.splitlines()[:40]:
        match = FOLLOWUPS_HEADER_FIELD_RE.match(line)
        if not match:
            continue
        key = match.group("key").strip().casefold()
        if key in normalized_names:
            return match.group("value").strip().strip("`").strip()
    return ""


def _normalize_followups_source(value: str) -> str:
    value = value.strip().strip("`").lower()
    return re.sub(r"[\s_-]+", " ", value).strip()


def _is_real_followups_import(value: str) -> bool:
    if not _is_meaningful_receipt_value(value) or _is_na_value(value):
        return False
    return "docs/followups/" in value


def _classify_followups_backlog(root: Path, path: str) -> FollowupsBacklogClassification:
    try:
        text = _read_text(root / path)
    except FileNotFoundError:
        return FollowupsBacklogClassification(
            path=path,
            role="unknown_same_range_followups",
            source="",
            imported_into="",
            error=f"{path} disappeared while classifying same-range followups",
        )

    source = _extract_followups_header_field(text, {"Source", "Источник"})
    imported_into = _extract_followups_header_field(text, {"Imported into"})
    source_norm = _normalize_followups_source(source)
    name = Path(path).name
    is_plan_harvest_name = bool(FOLLOWUPS_PLAN_HARVEST_FILENAME_RE.match(name))
    is_post_merge_audit_name = bool(FOLLOWUPS_POST_MERGE_AUDIT_FILENAME_RE.match(name))

    if source_norm == "plan harvest":
        if not is_plan_harvest_name:
            return FollowupsBacklogClassification(
                path=path,
                role="unknown_same_range_followups",
                source=source,
                imported_into=imported_into,
                error=(
                    f"{path} has Source=plan harvest but filename is not the primary "
                    "plan-harvest followups_range family"
                ),
            )
        return FollowupsBacklogClassification(
            path=path,
            role="primary_plan_harvest",
            source=source,
            imported_into=imported_into,
        )

    if source_norm == "post merge audit":
        if not is_post_merge_audit_name:
            return FollowupsBacklogClassification(
                path=path,
                role="unknown_same_range_followups",
                source=source,
                imported_into=imported_into,
                error=(
                    f"{path} has Source=post-merge audit but filename is not the "
                    "post_merge_audit_followups_range family"
                ),
            )
        if not _is_real_followups_import(imported_into):
            return FollowupsBacklogClassification(
                path=path,
                role="unknown_same_range_followups",
                source=source,
                imported_into=imported_into,
                error=(
                    f"{path} is supplemental post-merge audit followups but has malformed "
                    f"Imported into={imported_into or 'missing'}"
                ),
            )
        return FollowupsBacklogClassification(
            path=path,
            role="supplemental_post_merge_audit",
            source=source,
            imported_into=imported_into,
        )

    return FollowupsBacklogClassification(
        path=path,
        role="unknown_same_range_followups",
        source=source,
        imported_into=imported_into,
        error=(
            f"{path} has unsupported or missing Source={source or 'missing'}; "
            "expected Source=plan harvest for primary backlog or Source=post-merge audit "
            "for supplemental audit backlog"
        ),
    )


def _artifact_row(
    *,
    root: Path,
    spec: ArtifactSpec,
    path: str,
    required: bool,
    status_map: dict[str, dict[str, Any]],
    kind: str | None = None,
    active_candidate: bool = True,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    status = _extract_status(root / path) if spec.require_final_status else None
    row: dict[str, Any] = {
        "step": spec.step,
        "kind": kind or spec.kind,
        "path": path,
        "required": required,
        "git_state": _git_state_for(path, status_map),
        "status": status,
        "status_final": _is_final_status(status) if spec.require_final_status else None,
        "active_candidate": active_candidate,
    }
    if extra:
        row.update(extra)
    return row


def _is_superseded_packetization_report(root: Path, path: str) -> bool:
    return _is_superseded_packetization_status(_extract_status(root / path))


def _parse_git_status(stdout: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for line in stdout.splitlines():
        if not line:
            continue
        xy = line[:2]
        path = line[3:].strip() if len(line) > 3 else ""
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()
        if not path:
            continue
        out[path] = {
            "xy": xy,
            "staged": xy[0] not in (" ", "?"),
            "unstaged": xy[1] not in (" ", "?"),
            "untracked": xy == "??",
        }
    return out


def _git_state_for(path: str, status_map: dict[str, dict[str, Any]]) -> str:
    state = status_map.get(path)
    if not state:
        return "clean"
    if state["untracked"]:
        return "untracked"
    parts: list[str] = []
    if state["staged"]:
        parts.append("staged")
    if state["unstaged"]:
        parts.append("unstaged")
    return "+".join(parts) if parts else state["xy"].strip()


def _status_bucket(path: str, required_paths: set[str]) -> str:
    if path in required_paths:
        return "required"
    if path.startswith(".planveyor."):
        return "candidate/contextual"
    if path.startswith("docs/"):
        return "candidate/contextual"
    return "suspicious"


def _artifact_timestamp_from_filename(path: str) -> tuple[str, datetime | None]:
    match = ARTIFACT_FILENAME_TIMESTAMP_RE.search(Path(path).name)
    if not match:
        return "", None
    raw = match.group("stamp")
    try:
        parsed = datetime.strptime(raw, "%y%m%d_%H%M")
    except ValueError:
        return raw, None
    return raw, parsed


def _latest_commit_for_path(root: Path, path: str) -> tuple[dict[str, Any], int | None]:
    rc, stdout, stderr = _run_git(root, "log", "-1", "--format=%H%x00%cI%x00%ct", "--", path)
    if rc == GIT_TIMEOUT_RETURN_CODE:
        return {
            "commit_lookup_status": "timeout",
            "commit_lookup_detail": stderr.strip() or stdout.strip(),
            "commit_sha": "",
            "commit_sha_short": "",
            "committed_at": "",
        }, None
    if rc != 0:
        return {
            "commit_lookup_status": "failed",
            "commit_lookup_detail": stderr.strip() or stdout.strip(),
            "commit_sha": "",
            "commit_sha_short": "",
            "committed_at": "",
        }, None
    raw = stdout.strip()
    if not raw:
        return {
            "commit_lookup_status": "missing",
            "commit_lookup_detail": "path has no committed history",
            "commit_sha": "",
            "commit_sha_short": "",
            "committed_at": "",
        }, None
    parts = raw.split("\x00")
    commit_sha = parts[0] if parts else ""
    committed_at = parts[1] if len(parts) > 1 else ""
    try:
        commit_epoch = int(parts[2]) if len(parts) > 2 else None
    except ValueError:
        commit_epoch = None
    return {
        "commit_lookup_status": "ok",
        "commit_lookup_detail": "",
        "commit_sha": commit_sha,
        "commit_sha_short": commit_sha[:7],
        "committed_at": committed_at,
    }, commit_epoch


def _lineage_role_for_artifact(artifact: dict[str, Any]) -> str:
    kind = str(artifact.get("kind") or "")
    if kind in {"review_plan", "review_code_draft", "review_artifact"}:
        return "source_review_scaffold"
    if kind in {"followups_backlog", "supplemental_followups_backlog"}:
        return "followup_fix"
    if kind in {
        "merge_notes",
        "plan_harvest",
        "post_merge_audit",
        "packetization_gate",
        "post_merge_operational_receipt",
        "ready_to_push_closeout_receipt",
        CANON_SWEEP_RECEIPT_KIND,
    }:
        return "docs_closeout"
    if kind == "canon_snapshot":
        return "derived_index"
    return "other"


def _attach_artifact_timestamp_lineage(root: Path, artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    sortable_rows: list[tuple[dict[str, Any], datetime, int]] = []
    rows: list[dict[str, Any]] = []
    for artifact in artifacts:
        path = str(artifact.get("path") or "")
        raw_timestamp, filename_dt = _artifact_timestamp_from_filename(path)
        commit_info, commit_epoch = _latest_commit_for_path(root, path) if path else ({}, None)
        lineage = {
            "schema_version": "artifact_timestamp_lineage.v1",
            "artifact_path": path,
            "lineage_role": _lineage_role_for_artifact(artifact),
            "readback_kind": "derived/read-only",
            "chronology_authority": "git_commit_order",
            "artifact_materialized_at": (
                filename_dt.isoformat(timespec="minutes") if filename_dt else ""
            ),
            "artifact_materialized_at_source": "filename_timestamp" if filename_dt else "unknown",
            "artifact_filename_timestamp": raw_timestamp,
            "derived_from_filename": bool(filename_dt),
            "status_write_at": "",
            "status_write_at_source": "unknown",
            "commit_sha": commit_info.get("commit_sha", ""),
            "commit_sha_short": commit_info.get("commit_sha_short", ""),
            "committed_at": commit_info.get("committed_at", ""),
            "commit_lookup_status": commit_info.get("commit_lookup_status", "missing"),
            "commit_lookup_detail": commit_info.get("commit_lookup_detail", ""),
            "artifact_timestamp_order_index": None,
            "commit_order_index": None,
            "diverges_from_commit_order": False,
        }
        artifact["artifact_lineage"] = lineage
        rows.append(lineage)
        if filename_dt is not None and commit_epoch is not None:
            sortable_rows.append((artifact, filename_dt, commit_epoch))

    for index, (artifact, _, _) in enumerate(
        sorted(sortable_rows, key=lambda item: (item[1], str(item[0].get("path") or ""))),
        start=1,
    ):
        artifact["artifact_lineage"]["artifact_timestamp_order_index"] = index
    for index, (artifact, _, _) in enumerate(
        sorted(sortable_rows, key=lambda item: (item[2], str(item[0].get("path") or ""))),
        start=1,
    ):
        artifact["artifact_lineage"]["commit_order_index"] = index

    divergent_artifact_paths: set[str] = set()
    for left_index, (left_artifact, left_timestamp, left_commit) in enumerate(sortable_rows):
        for right_artifact, right_timestamp, right_commit in sortable_rows[left_index + 1:]:
            timestamp_direction = (left_timestamp > right_timestamp) - (left_timestamp < right_timestamp)
            commit_direction = (left_commit > right_commit) - (left_commit < right_commit)
            if timestamp_direction and commit_direction and timestamp_direction != commit_direction:
                divergent_artifact_paths.add(str(left_artifact.get("path") or ""))
                divergent_artifact_paths.add(str(right_artifact.get("path") or ""))

    for artifact in artifacts:
        path = str(artifact.get("path") or "")
        if path in divergent_artifact_paths:
            artifact["artifact_lineage"]["diverges_from_commit_order"] = True

    return {
        "schema_version": "artifact_timestamp_lineage_summary.v1",
        "status": "diverged" if divergent_artifact_paths else "aligned",
        "chronology_authority": "git_commit_order",
        "readback_kind": "derived/read-only",
        "rows_count": len(rows),
        "divergent_rows_count": len(divergent_artifact_paths),
        "divergent_artifact_paths": sorted(divergent_artifact_paths),
        "rows": rows,
    }


def _range_diff_candidates(root: Path, range_ref: str) -> tuple[list[str], dict[str, str] | None]:
    rc, stdout, stderr = _run_git(root, "diff", "--name-only", range_ref)
    if rc == GIT_TIMEOUT_RETURN_CODE:
        return [], {"code": "range_diff_timeout", "detail": stderr.strip() or stdout.strip()}
    if rc != 0:
        return [], {
            "code": "range_diff_unavailable",
            "detail": stderr.strip() or stdout.strip() or f"git diff failed for {range_ref}",
        }
    return [line.strip() for line in stdout.splitlines() if line.strip()], None


def _is_followups_triage_file_target(path: str) -> bool:
    path_obj = Path(path)
    if path_obj.is_absolute() or ".." in path_obj.parts:
        return False
    if path_obj.suffix != ".md":
        return False
    if len(path_obj.parts) < 3 or path_obj.parts[0] != "docs" or path_obj.parts[1] != "followups":
        return False
    if path_obj.name in FOLLOWUPS_TRIAGE_FILE_REJECTED_NAMES:
        return False
    if path_obj.name.endswith("_master.md"):
        return False
    return True


def _followups_triage_file_targets_from_command(command: str) -> set[str]:
    targets: set[str] = set()
    for match in re.finditer(r"--file(?:=|\s+)(?P<path>[^\s;]+)", command):
        targets.add(match.group("path").strip().strip("'\"`"))
    return targets


def _range_followups_obligation_paths(
    range_candidates: list[str],
    *,
    file_mode_targets: set[str],
) -> list[str]:
    obligations: list[str] = []
    for path in range_candidates:
        if not _is_followups_triage_file_target(path):
            continue
        name = Path(path).name
        if "followups_memory" in name or (path not in file_mode_targets and "_followups_range_" in name):
            obligations.append(path)
    return sorted(set(obligations))


def _report_has_blocking_packetization_rows(root: Path, report_path: str) -> bool:
    result = _packetization_report_payload_result(root, report_path)
    if result.error:
        return True
    if not result.structural_present:
        try:
            text = _read_text(root / report_path)
        except FileNotFoundError:
            return True
        coverage_column: int | None = None
        for line in text.splitlines():
            stripped = line.strip()
            if not (stripped.startswith("|") and stripped.endswith("|")):
                continue
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if coverage_column is None:
                normalized = [cell.casefold() for cell in cells]
                if "coverage" in normalized:
                    coverage_column = normalized.index("coverage")
                continue
            if all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
                continue
            if coverage_column < len(cells) and cells[coverage_column] in BLOCKING_COVERAGES:
                return True
        return False

    payload = result.payload
    raw_rows = payload.get("rows")
    if not isinstance(raw_rows, list):
        return True
    rows = _packetization_rows(raw_rows)
    if len(rows) != len(raw_rows):
        return True

    actual_counts: dict[str, int] = {}
    blocking_rows = 0
    for row in rows:
        coverage = row.get("coverage")
        if not isinstance(coverage, str) or not coverage.strip():
            return True
        normalized_coverage = coverage.strip()
        actual_counts[normalized_coverage] = actual_counts.get(normalized_coverage, 0) + 1
        row_blocking = _packetization_row_is_blocking(row)
        if row_blocking is None:
            return True
        blocking_rows += int(row_blocking)

    declared_blocking_rows = payload.get("blocking_rows_count", payload.get("blocking_count"))
    if declared_blocking_rows is not None:
        if isinstance(declared_blocking_rows, bool) or not isinstance(declared_blocking_rows, int):
            return True
        if declared_blocking_rows != blocking_rows:
            return True

    if "blocking_coverage_counts" not in payload:
        return blocking_rows > 0
    raw_counts = payload.get("blocking_coverage_counts")
    if not isinstance(raw_counts, dict):
        return True

    declared_counts: dict[str, int] = {}
    for coverage, count in raw_counts.items():
        if (
            not isinstance(coverage, str)
            or not coverage.strip()
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count < 0
        ):
            return True
        declared_counts[coverage.strip()] = count

    expected_counts = dict(actual_counts)
    for coverage in declared_counts:
        expected_counts.setdefault(coverage, 0)
    if declared_counts != expected_counts:
        return True
    return blocking_rows > 0


PACKETIZATION_REUSE_NA = "N/A (why=not derivable from current report schema)"
PACKETIZATION_UNCLAIMED_DIAGNOSTIC_SAMPLE_LIMIT = 3
MACHINE_READABLE_JSON_RE = re.compile(r"^##\s+Machine-readable JSON\s*$", flags=re.IGNORECASE | re.MULTILINE)
JSON_FENCE_RE = re.compile(r"```json\s*(?P<body>.*?)```", flags=re.IGNORECASE | re.DOTALL)


def _packetization_json_error(report_path: str, detail: str) -> dict[str, str]:
    return {
        "code": "malformed_packetization_json",
        "detail": f"{report_path} has malformed structural packetization JSON: {detail}",
    }


def _packetization_report_payload_result(root: Path, report_path: str) -> PacketizationReportPayload:
    try:
        text = _read_text(root / report_path)
    except FileNotFoundError:
        return PacketizationReportPayload(payload={})

    json_fences = list(JSON_FENCE_RE.finditer(text))
    if not json_fences:
        if MACHINE_READABLE_JSON_RE.search(text):
            return PacketizationReportPayload(
                payload={},
                structural_present=True,
                error=_packetization_json_error(report_path, "missing ```json``` fence"),
            )
        return PacketizationReportPayload(payload={})

    for match in json_fences:
        try:
            parsed = json.loads(match.group("body"))
        except json.JSONDecodeError as exc:
            return PacketizationReportPayload(
                payload={},
                structural_present=True,
                error=_packetization_json_error(report_path, exc.msg),
            )
        if not isinstance(parsed, dict):
            return PacketizationReportPayload(
                payload={},
                structural_present=True,
                error=_packetization_json_error(report_path, "top-level payload is not an object"),
            )
        if "packetization_gate" in parsed:
            gate_payload = parsed.get("packetization_gate")
            if not isinstance(gate_payload, dict):
                return PacketizationReportPayload(
                    payload={},
                    structural_present=True,
                    error=_packetization_json_error(report_path, "packetization_gate payload is not an object"),
                )
            return PacketizationReportPayload(payload=gate_payload, structural_present=True)
        return PacketizationReportPayload(payload=parsed, structural_present=True)

    return PacketizationReportPayload(payload={})


def _packetization_report_payload(root: Path, report_path: str) -> dict[str, Any]:
    return _packetization_report_payload_result(root, report_path).payload


def _packetization_report_schema_errors(root: Path, report_path: str) -> list[dict[str, str]]:
    result = _packetization_report_payload_result(root, report_path)
    if result.error:
        return [result.error]
    if not result.structural_present:
        return []
    payload = result.payload
    schema_version = str(payload.get("schema_version") or "").strip()
    if not schema_version:
        return [
            {
                "code": "missing_packetization_schema_version",
                "detail": f"{report_path} has structural packetization JSON without schema_version",
            }
        ]
    if schema_version != PACKETIZATION_GATE_SCHEMA_VERSION:
        return [
            {
                "code": "unsupported_packetization_schema_version",
                "detail": (
                    f"{report_path} schema_version={schema_version}; "
                    f"expected={PACKETIZATION_GATE_SCHEMA_VERSION}"
                ),
            }
        ]
    return []


def _path_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = str(item).strip()
        if not text or text.lower().startswith("n/a"):
            continue
        out.append(text)
    return sorted(dict.fromkeys(out))


def _packetization_rows(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def _packetization_row_is_blocking(row: dict[str, Any]) -> bool | None:
    """Return the structural blocking bit, with a legacy coverage fallback.

    New packetization reports make the policy decision explicit per row.  Older
    reports have no such field and retain their established coverage semantics.
    A malformed explicit bit is deliberately fail-closed for consumers.
    """

    if "blocking" in row:
        value = row.get("blocking")
        return value if isinstance(value, bool) else None
    return _receipt_field_string(row.get("coverage", "")) in BLOCKING_COVERAGES


def _present_blocking_coverage_counts(readback: dict[str, Any]) -> list[str]:
    """Render only current, nonzero blocking classes from structured readback."""

    raw_coverages = readback.get("blocking_coverages")
    raw_counts = readback.get("blocking_coverage_counts")
    if not isinstance(raw_coverages, list) or not isinstance(raw_counts, dict):
        return []
    blocking_coverages = {
        _receipt_field_string(coverage)
        for coverage in raw_coverages
        if _receipt_field_string(coverage)
    }
    return [
        f"{coverage}={count}"
        for coverage, count in sorted(raw_counts.items())
        if coverage in blocking_coverages
        and isinstance(count, int)
        and not isinstance(count, bool)
        and count > 0
    ]


def _packetization_readback(
    *,
    root: Path,
    active_reports: list[str],
    artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    superseded_reports = sorted(
        str(artifact["path"])
        for artifact in artifacts
        if artifact.get("kind") == PACKETIZATION_GATE_RECEIPT_KIND and not artifact.get("active_candidate", True)
    )
    readback: dict[str, Any] = {
        "active_packetization_report": "N/A (why=no active packetization report)",
        "superseded_packetization_reports": superseded_reports,
        "blocking_rows_count": 0,
        "blocking_coverages": [],
        "blocking_coverage_counts": {},
        "draft_packets_created_count": 0,
        "draft_packets_created_paths": [],
        "draft_packets_reused_paths": PACKETIZATION_REUSE_NA,
        "report_accepted_packet_paths": "N/A (why=not claimed by active report)",
        "schema_version": "N/A (why=no active packetization report)",
    }
    if len(active_reports) > 1:
        readback["active_packetization_report"] = "N/A (why=ambiguous active packetization reports)"
        return readback
    if not active_reports:
        return readback

    active_report = active_reports[0]
    readback["active_packetization_report"] = active_report
    payload_result = _packetization_report_payload_result(root, active_report)
    payload = payload_result.payload
    if payload_result.error:
        readback["schema_version"] = "N/A (why=malformed structural packetization JSON)"
    elif payload_result.structural_present:
        readback["schema_version"] = str(
            payload.get("schema_version") or "N/A (why=missing schema_version in structural JSON)"
        )
    else:
        readback["schema_version"] = "N/A (why=legacy packetization report)"
    rows = _packetization_rows(payload.get("rows"))

    if "report_accepted_packet_paths" in payload:
        raw_accepted = payload.get("report_accepted_packet_paths")
        if isinstance(raw_accepted, list):
            readback["report_accepted_packet_paths"] = [str(item) for item in raw_accepted]
        else:
            readback["report_accepted_packet_paths"] = "N/A (why=malformed claimed accepted paths)"

    created_paths = _path_list(payload.get("draft_packets_created_paths")) or _path_list(
        payload.get("created_packets")
    )
    readback["draft_packets_created_paths"] = created_paths
    readback["draft_packets_created_count"] = len(created_paths)

    coverage_counts: dict[str, int] = {}
    if rows:
        for row in rows:
            coverage = _receipt_field_string(row.get("coverage", ""))
            if coverage:
                coverage_counts[coverage] = coverage_counts.get(coverage, 0) + 1
        blocking_coverages = sorted(
            {
                str(row.get("coverage") or "")
                for row in rows
                if _packetization_row_is_blocking(row) is True
            }
        )
    else:
        raw_counts = payload.get("blocking_coverage_counts")
        if isinstance(raw_counts, dict):
            for raw_coverage, raw_count in raw_counts.items():
                count = _summary_int_value(raw_count)
                if count is not None and count >= 0:
                    coverage_counts[str(raw_coverage)] = count
        blocking_coverages = _path_list(payload.get("blocking_coverages"))
        if blocking_coverages:
            blocking_coverages = sorted(
                coverage
                for coverage in blocking_coverages
                if isinstance(coverage_counts.get(coverage), int)
                and not isinstance(coverage_counts.get(coverage), bool)
                and coverage_counts[coverage] > 0
            )
        else:
            blocking_coverages = sorted(
                coverage
                for coverage, count in coverage_counts.items()
                if coverage in BLOCKING_COVERAGES and count > 0
            )
    readback["blocking_coverages"] = blocking_coverages
    readback["blocking_coverage_counts"] = dict(sorted(coverage_counts.items()))

    blocking_count = payload.get("blocking_rows_count", payload.get("blocking_count"))
    if isinstance(blocking_count, int):
        readback["blocking_rows_count"] = blocking_count
    elif rows:
        readback["blocking_rows_count"] = sum(
            1 for row in rows if _packetization_row_is_blocking(row) is True
        )
    elif blocking_coverages:
        readback["blocking_rows_count"] = len(blocking_coverages)

    explicit_reused = payload.get("draft_packets_reused_paths")
    if isinstance(explicit_reused, str) and explicit_reused.strip().lower().startswith("n/a"):
        readback["draft_packets_reused_paths"] = explicit_reused.strip()
    else:
        reused_paths = _path_list(explicit_reused)
        if not reused_paths and rows:
            reused_paths = _path_list(
                [
                    row.get("packet_path")
                    for row in rows
                    if str(row.get("coverage") or "") == "covered"
                ]
            )
        if reused_paths:
            readback["draft_packets_reused_paths"] = reused_paths
    return readback


def _receipt_preflight_report_paths(
    *,
    root: Path,
    packetization_reports: list[str],
) -> tuple[list[str], list[dict[str, str]]]:
    paths: list[str] = []
    errors: list[dict[str, str]] = []
    for raw_path in packetization_reports:
        path_text = str(raw_path).strip()
        if not path_text:
            continue
        candidate = Path(path_text).expanduser()
        resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
        try:
            paths.append(resolved.relative_to(root).as_posix())
        except ValueError:
            errors.append(
                {
                    "code": "inconsistent_receipt",
                    "detail": (
                        "step:post_merge_audit/packetization_gate: explicit packetization report "
                        f"{path_text} is outside repo root"
                    ),
                }
            )
    return sorted(dict.fromkeys(paths)), errors


def validate_packetization_reports_for_receipt_preflight(
    *,
    root: Path,
    range_ref: str | None,
    packetization_reports: list[str],
    mirror_policy: MirrorPolicy = GENERIC_MIRROR_POLICY,
) -> tuple[list[str], list[dict[str, str]]]:
    """Apply strict same-range packetization policy for late receipt preflight only."""

    requested_range = str(range_ref or "").strip()
    base, separator, head = requested_range.partition("..")
    if not separator or not base or not head or ".." in head:
        return [], [
            {
                "code": "inconsistent_receipt",
                "detail": (
                    "step:post_merge_audit/packetization_gate: shared packetization validation "
                    "requires an exact resolved BASE..HEAD range"
                ),
            }
        ]
    try:
        normalized_range = resolve_recovery_lineage(
            root,
            range_ref=requested_range,
            mirror_policy=mirror_policy,
        ).range_ref
    except (OSError, RuntimeError, ValueError) as exc:
        return [], [
            {
                "code": "inconsistent_receipt",
                "detail": (
                    "step:post_merge_audit/packetization_gate: shared packetization validation "
                    f"cannot resolve exact range {requested_range}: {exc}"
                ),
            }
        ]

    supplied_reports, errors = _receipt_preflight_report_paths(
        root=root,
        packetization_reports=packetization_reports,
    )
    if errors:
        return [], errors

    same_range_reports = [
        _rel(path, root)
        for path in same_range_report_paths(root, range_ref=normalized_range)
    ]
    same_range_set = set(same_range_reports)
    wrong_range_reports = [path for path in supplied_reports if path not in same_range_set]
    if wrong_range_reports:
        return same_range_reports, [
            {
                "code": "inconsistent_receipt",
                "detail": (
                    "step:post_merge_audit/packetization_gate: explicit packetization report "
                    f"does not match resolved range {normalized_range}: {', '.join(wrong_range_reports)}"
                ),
            }
        ]

    if not same_range_reports:
        return [], [
            {
                "code": "inconsistent_receipt",
                "detail": (
                    "step:post_merge_audit/packetization_gate: missing active packetization report "
                    f"for resolved range {normalized_range}"
                ),
            }
        ]

    active_reports = [
        path for path in same_range_reports if not _is_superseded_packetization_report(root, path)
    ]
    if not active_reports:
        return same_range_reports, [
            {
                "code": "superseded_packetization_report",
                "detail": (
                    "step:post_merge_audit/packetization_gate: all same-range packetization reports "
                    f"are Superseded for {normalized_range}: {', '.join(same_range_reports)}"
                ),
            }
        ]
    if len(active_reports) > 1:
        return same_range_reports, [
            {
                "code": "ambiguous_artifact",
                "detail": (
                    "step:post_merge_audit/packetization_gate: multiple active same-range "
                    f"packetization reports for {normalized_range}: {', '.join(active_reports)}"
                ),
            }
        ]

    active_report = active_reports[0]
    status = _extract_status(root / active_report)
    if not _is_final_status(status):
        return same_range_reports, [
            {
                "code": "non_final_artifact_status",
                "detail": (
                    "step:post_merge_audit/packetization_gate: "
                    f"{active_report} status={status or 'missing'}"
                ),
            }
        ]

    payload_result = _packetization_report_payload_result(root, active_report)
    if payload_result.error:
        return same_range_reports, [payload_result.error]
    if not payload_result.structural_present:
        return same_range_reports, [
            {
                "code": "missing_packetization_schema_version",
                "detail": (
                    "step:post_merge_audit/packetization_gate: "
                    f"{active_report} has no structural packetization JSON"
                ),
            }
        ]

    schema_errors = _packetization_report_schema_errors(root, active_report)
    if schema_errors:
        return same_range_reports, schema_errors

    payload_range = _receipt_field_string(payload_result.payload.get("range", ""))
    if payload_range != normalized_range:
        return same_range_reports, [
            {
                "code": "inconsistent_receipt",
                "detail": (
                    "step:post_merge_audit/packetization_gate: "
                    f"{active_report} range={payload_range or 'missing'}; expected={normalized_range}"
                ),
            }
        ]

    if _report_has_blocking_packetization_rows(root, active_report):
        report_readback = _packetization_readback(
            root=root,
            active_reports=[active_report],
            artifacts=[],
        )
        blocking_coverages = _present_blocking_coverage_counts(report_readback)
        return same_range_reports, [
            {
                "code": "blocking_packetization_rows",
                "detail": (
                    "step:post_merge_audit/packetization_gate: "
                    f"{active_report} contains {', '.join(blocking_coverages) or 'malformed structural rows/counts'}"
                ),
            }
        ]

    return same_range_reports, []


def _has_all_tokens(text: str, tokens: tuple[str, ...]) -> bool:
    lower = text.lower()
    return all(token.lower() in lower for token in tokens)


def _extract_receipt_field(text: str, field: str) -> str:
    pattern = re.compile(
        rf"^\s*(?:[-*]\s*)?(?:`|\*\*)?{re.escape(field)}(?:`|\*\*)?\s*:\s*(?P<value>.+?)\s*$",
        flags=re.IGNORECASE | re.MULTILINE,
    )
    match = pattern.search(text)
    if not match:
        return ""
    return match.group("value").strip().strip("`").strip()


def _is_meaningful_receipt_value(value: str) -> bool:
    if not value:
        return False
    lowered = value.strip().lower()
    if lowered in {"n/a", "na", "none", "-", "tbd", "unconfirmed"}:
        return False
    if lowered.startswith(("n/a ", "n/a(", "n/a (", "na ", "na(", "na (")):
        return False
    return True


def _is_durable_followups_triage_ref(value: str) -> bool:
    if not _is_meaningful_receipt_value(value):
        return False
    token = value.strip().strip("`").split()[0].strip("`.,;()[]<>")
    path_text = token.split("#", 1)[0]
    if ":" in path_text:
        maybe_path, maybe_line = path_text.rsplit(":", 1)
        if maybe_line.isdigit():
            path_text = maybe_path
    path = Path(path_text)
    return path_text.startswith("docs/") and path.suffix == ".md" and not path.is_absolute() and ".." not in path.parts


def _followups_triage_launch_summary_closure_refs(summary: dict[str, str]) -> dict[str, str]:
    return {
        field: summary.get(field, "").strip()
        for field in FOLLOWUPS_TRIAGE_LAUNCH_CLOSURE_REF_FIELDS
        if _is_meaningful_receipt_value(summary.get(field, "").strip())
    }


def _followups_triage_launch_receipt_closure_refs(value: dict[str, Any]) -> dict[str, str]:
    refs = {
        field: _receipt_field_string(value.get(field, ""))
        for field in FOLLOWUPS_TRIAGE_LAUNCH_CLOSURE_REF_FIELDS
        if _is_meaningful_receipt_value(_receipt_field_string(value.get(field, "")))
    }
    nested = value.get("closure_refs")
    if isinstance(nested, dict):
        for field in FOLLOWUPS_TRIAGE_LAUNCH_CLOSURE_REF_FIELDS:
            raw = _receipt_field_string(nested.get(field, ""))
            if _is_meaningful_receipt_value(raw):
                refs.setdefault(field, raw)
    return refs


def _is_enum_like_reason(value: str) -> bool:
    if not _is_meaningful_receipt_value(value):
        return False
    return bool(re.fullmatch(r"[a-z][a-z0-9_-]*", value.strip()))


def _is_na_value(value: str) -> bool:
    lowered = value.strip().lower()
    return lowered in {"n/a", "na"} or lowered.startswith(
        ("n/a ", "n/a(", "n/a (", "na ", "na(", "na (")
    )


def _has_secretish_keys(value: object) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in SECRETISH_KEYS:
                return True
            if _has_secretish_keys(child):
                return True
        return False
    if isinstance(value, list):
        return any(_has_secretish_keys(child) for child in value)
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


def _canon_sweep_receipt_error(detail: str) -> dict[str, str]:
    return {"code": "inconsistent_receipt", "detail": f"step:canon_sweep/canon_sweep_execution: {detail}"}


def _validate_canon_sweep_receipt_text(
    *,
    text: str,
    artifact_path: str,
    packetization_reports: list[str],
    require_packetization_report: bool = True,
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    required_tokens = (
        "Canon sweep receipt",
        "changed_shared_canon_files_count",
        "changed_shared_canon_files",
        "proof_kind",
        "target_repo_impact",
    )
    missing_tokens = [token for token in required_tokens if token.lower() not in text.lower()]
    if missing_tokens:
        errors.append(
            _canon_sweep_receipt_error(
                f"{artifact_path} missing required token(s): {', '.join(missing_tokens)}"
            )
        )
        return errors

    changed_count_raw = _extract_receipt_field(text, "changed_shared_canon_files_count")
    try:
        changed_count = int(changed_count_raw)
    except ValueError:
        errors.append(
            _canon_sweep_receipt_error(
                f"{artifact_path} has non-integer changed_shared_canon_files_count={changed_count_raw or 'missing'}"
            )
        )
        changed_count = -1
    if changed_count < 0:
        errors.append(
            _canon_sweep_receipt_error(
                f"{artifact_path} has negative changed_shared_canon_files_count={changed_count}"
            )
        )

    changed_files = _extract_receipt_field(text, "changed_shared_canon_files")
    if changed_count == 0 and changed_files.strip().lower() != "none":
        errors.append(
            _canon_sweep_receipt_error(
                f"{artifact_path} must use changed_shared_canon_files: none when count is 0"
            )
        )
    if changed_count > 0 and not _is_meaningful_receipt_value(changed_files):
        errors.append(_canon_sweep_receipt_error(f"{artifact_path} missing changed_shared_canon_files value"))

    proof_kind = _extract_receipt_field(text, "proof_kind").lower()
    if proof_kind not in CANON_SWEEP_RECEIPT_ALLOWED_PROOF_KINDS:
        allowed = ", ".join(sorted(CANON_SWEEP_RECEIPT_ALLOWED_PROOF_KINDS))
        errors.append(
            _canon_sweep_receipt_error(
                f"{artifact_path} has unsupported proof_kind={proof_kind or 'missing'}; "
                f"allowed values: {allowed}"
            )
        )

    target_impact = _extract_receipt_field(text, "target_repo_impact").lower()
    if target_impact not in CANON_SWEEP_RECEIPT_ALLOWED_TARGET_IMPACTS:
        errors.append(
            _canon_sweep_receipt_error(
                f"{artifact_path} has unsupported target_repo_impact={target_impact or 'missing'}"
            )
        )

    closure_values = {
        field: _extract_receipt_field(text, field) for field in CANON_SWEEP_RECEIPT_CLOSURE_FIELDS
    }
    meaningful_closures = [
        field for field, value in closure_values.items() if _is_meaningful_receipt_value(value)
    ]
    if len(meaningful_closures) != 1:
        errors.append(
            _canon_sweep_receipt_error(
                f"{artifact_path} must have exactly one meaningful closure lane from "
                f"{', '.join(CANON_SWEEP_RECEIPT_CLOSURE_FIELDS)}; found={meaningful_closures or 'none'}"
            )
        )
    elif proof_kind == "no_op" and meaningful_closures[0] != "no_op_reason":
        errors.append(_canon_sweep_receipt_error(f"{artifact_path} proof_kind=no_op requires no_op_reason"))
    elif proof_kind == "snapshot" and meaningful_closures[0] != "snapshot_path":
        errors.append(_canon_sweep_receipt_error(f"{artifact_path} proof_kind=snapshot requires snapshot_path"))
    elif proof_kind == "report" and meaningful_closures[0] != "report_path":
        errors.append(_canon_sweep_receipt_error(f"{artifact_path} proof_kind=report requires report_path"))

    no_op_reason = closure_values["no_op_reason"]
    if proof_kind == "no_op" and not _is_enum_like_reason(no_op_reason):
        errors.append(
            _canon_sweep_receipt_error(
                f"{artifact_path} no_op_reason must be a closed enum-like token, got={no_op_reason or 'missing'}"
            )
        )

    packetization_handoff = _extract_receipt_field(text, "packetization_handoff")
    if target_impact.startswith("shared_"):
        if PACKETIZATION_GATE_STEP not in packetization_handoff:
            errors.append(
                _canon_sweep_receipt_error(
                    f"{artifact_path} shared target_repo_impact requires packetization_handoff with {PACKETIZATION_GATE_STEP}"
                )
            )
        if require_packetization_report and not packetization_reports:
            errors.append(
                _canon_sweep_receipt_error(
                    f"{artifact_path} cites shared target_repo_impact but no packetization gate report artifact was found"
                )
            )

    return errors


def _validate_canon_sweep_proof(
    *,
    root: Path,
    artifacts: list[dict[str, Any]],
    completed_steps: set[str],
    packetization_reports: list[str],
    require_packetization_report: bool = True,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    if "step:canon_sweep" not in completed_steps:
        return [], []

    snapshot_artifacts = [
        artifact
        for artifact in artifacts
        if artifact["step"] == "step:canon_sweep" and artifact["kind"] == "canon_snapshot" and artifact.get("path")
    ]
    receipt_artifacts = [
        artifact
        for artifact in artifacts
        if artifact["step"] == "step:canon_sweep"
        and artifact["kind"] == CANON_SWEEP_RECEIPT_KIND
        and artifact.get("path")
    ]
    if snapshot_artifacts:
        return [
            {
                "step": "step:canon_sweep",
                "kind": "canon_snapshot",
                "receipt": "canon_sweep_execution",
                "path": str(snapshot_artifacts[0]["path"]),
                "required": True,
                "present": True,
                "expected_surface": "snapshot path or explicit no-op/report receipt with impact classification",
            }
        ], []

    if not receipt_artifacts:
        return [
            {
                "step": "step:canon_sweep",
                "kind": CANON_SWEEP_RECEIPT_KIND,
                "receipt": "canon_sweep_execution",
                "path": "(none)",
                "required": True,
                "present": False,
                "expected_surface": "snapshot path or explicit no-op/report receipt with impact classification",
            }
        ], [
            {
                "code": "missing_required_receipt",
                "detail": (
                    "step:canon_sweep/canon_sweep_execution: missing "
                    "docs/snapshots/*range_<base7>_<head7>* or "
                    "docs/reviews/*_canon_sweep_receipt_range_<base7>_<head7>.md"
                ),
            }
        ]

    receipt_artifact = receipt_artifacts[0]
    artifact_path = str(receipt_artifact["path"])
    text = _read_text(root / artifact_path)
    validation_errors = _validate_canon_sweep_receipt_text(
        text=text,
        artifact_path=artifact_path,
        packetization_reports=packetization_reports,
        require_packetization_report=require_packetization_report,
    )
    if not receipt_artifact.get("status_final"):
        validation_errors.append(
            _canon_sweep_receipt_error(
                f"{artifact_path} status={receipt_artifact.get('status') or 'missing'} is not final"
            )
        )
    return [
        {
            "step": "step:canon_sweep",
            "kind": CANON_SWEEP_RECEIPT_KIND,
            "receipt": "canon_sweep_execution",
            "path": artifact_path,
            "required": True,
            "present": not validation_errors,
            "expected_surface": "snapshot path or explicit no-op/report receipt with impact classification",
        }
    ], validation_errors


def _validate_substep_receipts(
    *,
    root: Path,
    artifacts: list[dict[str, Any]],
    completed_steps: set[str],
    packetization_required: bool,
    packetization_reports: list[str],
    require_packetization_report: bool = True,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    receipts: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    text_cache: dict[str, str] = {}

    for spec in RECEIPT_SPECS:
        if spec.step not in completed_steps:
            continue
        if spec.only_when_packetization_required and not packetization_required:
            continue

        matching_artifacts = [
            artifact
            for artifact in artifacts
            if artifact["step"] == spec.step and artifact["kind"] == spec.kind and artifact.get("path")
        ]
        if len(matching_artifacts) != 1:
            continue

        artifact_path = str(matching_artifacts[0]["path"])
        text = text_cache.get(artifact_path)
        if text is None:
            text = _read_text(root / artifact_path)
            text_cache[artifact_path] = text

        present = _has_all_tokens(text, spec.tokens)
        receipt = {
            "step": spec.step,
            "kind": spec.kind,
            "receipt": spec.name,
            "path": artifact_path,
            "required": True,
            "present": present,
            "expected_surface": spec.expected_surface,
        }
        receipts.append(receipt)
        if not present:
            errors.append(
                {
                    "code": "missing_required_receipt",
                    "detail": f"{spec.step}/{spec.name}: missing in {artifact_path}; expected {spec.expected_surface}",
                }
            )
            continue
        if (
            spec.name == PACKETIZATION_GATE_RECEIPT_NAME
            and spec.only_when_packetization_required
            and require_packetization_report
            and not packetization_reports
        ):
            errors.append(
                {
                    "code": "inconsistent_receipt",
                    "detail": (
                        f"{spec.step}/{spec.name}: {artifact_path} cites `{PACKETIZATION_GATE_STEP}`, "
                        "but no packetization gate report artifact was found"
                    ),
                }
            )

    if "step:plan_harvest" in completed_steps:
        matching_artifacts = [
            artifact
            for artifact in artifacts
            if artifact["step"] == "step:plan_harvest"
            and artifact["kind"] == "plan_harvest"
            and artifact.get("path")
        ]
        if len(matching_artifacts) == 1:
            artifact_path = str(matching_artifacts[0]["path"])
            text = text_cache.get(artifact_path)
            if text is None:
                text = _read_text(root / artifact_path)
                text_cache[artifact_path] = text
            parsed = parse_plan_harvest_file_followups_receipt(text, rel_path=artifact_path)
            if parsed.schema_class != "legacy":
                receipts.append(
                    {
                        "step": "step:plan_harvest",
                        "kind": "plan_harvest",
                        "receipt": "file_followups_literal_contract",
                        "path": artifact_path,
                        "required": True,
                        "present": not parsed.findings,
                        "expected_surface": (
                            "current review.v1 plan-harvest receipt with literal "
                            "harvest_file_followups_result/count"
                        ),
                    }
                )
                for finding in parsed.findings:
                    errors.append(
                        {
                            "code": "invalid_current_plan_harvest_file_followups",
                            "detail": (
                                "step:plan_harvest/file_followups_literal_contract: "
                                f"{finding.render()}"
                            ),
                        }
                    )
                if parsed.schema_class == "unsupported" and not parsed.findings:
                    errors.append(
                        {
                            "code": "invalid_current_plan_harvest_file_followups",
                            "detail": (
                                "step:plan_harvest/file_followups_literal_contract: "
                                f"{artifact_path} uses an unsupported explicit schema"
                            ),
                        }
                    )

    telemetry_steps = {
        ("step:plan_harvest", "plan_harvest"),
        ("step:post_merge_audit", "post_merge_audit"),
    }
    for step, kind in telemetry_steps:
        if step not in completed_steps:
            continue
        matching_artifacts = [
            artifact
            for artifact in artifacts
            if artifact["step"] == step and artifact["kind"] == kind and artifact.get("path")
        ]
        if len(matching_artifacts) != 1:
            continue
        artifact_path = str(matching_artifacts[0]["path"])
        text = text_cache.get(artifact_path)
        if text is None:
            text = _read_text(root / artifact_path)
            text_cache[artifact_path] = text
        receipt_findings = retrieval_telemetry_receipt.lint_retrieval_telemetry_receipt(
            text.splitlines(),
            decision_evidence_only=True,
        )
        if not receipt_findings:
            if retrieval_telemetry_receipt.needs_retrieval_telemetry_receipt(
                text.splitlines(),
                decision_evidence_only=True,
            ):
                receipts.append(
                    {
                        "step": step,
                        "kind": kind,
                        "receipt": "retrieval_telemetry",
                        "path": artifact_path,
                        "required": True,
                        "present": True,
                        "expected_surface": "`## Retrieval telemetry receipt` with parseable query/read/outcome fields",
                    }
                )
            continue
        receipts.append(
            {
                "step": step,
                "kind": kind,
                "receipt": "retrieval_telemetry",
                "path": artifact_path,
                "required": True,
                "present": False,
                "expected_surface": "`## Retrieval telemetry receipt` with parseable query/read/outcome fields",
            }
        )
        errors.append(
            {
                "code": "missing_required_receipt",
                "detail": f"{step}/retrieval_telemetry: {receipt_findings[0].message} in {artifact_path}",
            }
        )

    return receipts, errors


def _receipt_preflight_next_action(error: dict[str, str]) -> str:
    key = _receipt_error_key(error)
    if key is not None:
        status = _operator_status_for_error(str(error.get("code") or ""))
        return _operator_next_action(status, key[0], key[1]).replace(
            "planveyor_merge_bundle_report",
            "planveyor_post_merge_receipt_preflight",
        )

    detail = str(error.get("detail") or "")
    if detail.startswith("step:packetization_gate/"):
        return (
            "fix the packetization gate report so it has final non-superseded status "
            "and no blocking coverage rows, then rerun planveyor_post_merge_receipt_preflight"
        )
    if detail.startswith("step:docs_finalize/"):
        return (
            "return docs-finalize output with a parseable `Process improvements` section "
            "for the general lane or `NO FOLLOWUPS` for the followups lane, then rerun "
            "planveyor_post_merge_receipt_preflight"
        )
    if error.get("code") == "malformed_packetization_json":
        return (
            "fix the packetization gate report `## Machine-readable JSON` block so it parses "
            "as a packetization object, then rerun planveyor_post_merge_receipt_preflight"
        )
    if error.get("code") == "missing_path":
        return "pass an explicit existing receipt path with --path"
    if error.get("code") == "path_outside_repo":
        return "pass a repo-relative receipt path under the selected --repo-root"
    return "inspect preflight error detail and rerun planveyor_post_merge_receipt_preflight"


def _receipt_preflight_with_next_actions(errors: list[dict[str, str]]) -> list[dict[str, str]]:
    enriched: list[dict[str, str]] = []
    for error in errors:
        item = dict(error)
        item["next_action"] = _receipt_preflight_next_action(error)
        enriched.append(item)
    return enriched


def _receipt_preflight_rel_path(
    root: Path,
    raw_path: str | Path,
) -> tuple[Path | None, str, list[dict[str, str]]]:
    path_text = str(raw_path).strip()
    if not path_text:
        return None, "", [{"code": "missing_path", "detail": "--path is required"}]

    root_resolved = root.resolve()
    candidate = Path(path_text).expanduser()
    resolved = candidate.resolve() if candidate.is_absolute() else (root_resolved / candidate).resolve()
    try:
        rel_path = resolved.relative_to(root_resolved).as_posix()
    except ValueError:
        return resolved, path_text, [
            {
                "code": "path_outside_repo",
                "detail": f"{path_text} is outside repo root {root_resolved}",
            }
        ]
    if not resolved.is_file():
        return resolved, rel_path, [{"code": "missing_path", "detail": f"{rel_path} does not exist"}]
    return resolved, rel_path, []


def _receipt_preflight_substep(
    *,
    root: Path,
    step: str,
    kind: str,
    rel_path: str,
    packetization_required: bool,
    packetization_reports: list[str],
    require_packetization_report: bool = True,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    status = _extract_status(root / rel_path)
    artifacts = [
        {
            "step": step,
            "kind": kind,
            "path": rel_path,
            "required": True,
            "status": status,
            "status_final": _is_final_status(status),
            "active_candidate": True,
        }
    ]
    receipts, errors = _validate_substep_receipts(
        root=root,
        artifacts=artifacts,
        completed_steps={step},
        packetization_required=packetization_required,
        packetization_reports=packetization_reports,
        require_packetization_report=require_packetization_report,
    )
    if not _is_final_status(status):
        errors.insert(
            0,
            {
                "code": "non_final_artifact_status",
                "detail": f"{step}/{kind}: {rel_path} status={status or 'missing'}",
            },
        )
    return receipts, errors


def _receipt_preflight_canon_sweep(
    *,
    root: Path,
    rel_path: str,
    packetization_required: bool,
    packetization_reports: list[str],
    require_packetization_report: bool = True,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    if rel_path.startswith("docs/snapshots/"):
        return [
            {
                "step": "step:canon_sweep",
                "kind": "canon_snapshot",
                "receipt": "canon_sweep_execution",
                "path": rel_path,
                "required": True,
                "present": True,
                "expected_surface": "snapshot path or explicit no-op/report receipt with impact classification",
            }
        ], []

    status = _extract_status(root / rel_path)
    artifacts = [
        {
            "step": "step:canon_sweep",
            "kind": CANON_SWEEP_RECEIPT_KIND,
            "path": rel_path,
            "required": True,
            "status": status,
            "status_final": _is_final_status(status),
            "active_candidate": True,
        }
    ]
    receipts, errors = _validate_canon_sweep_proof(
        root=root,
        artifacts=artifacts,
        completed_steps={"step:canon_sweep"},
        packetization_reports=packetization_reports,
        require_packetization_report=require_packetization_report,
    )
    if packetization_required:
        text = _read_text(root / rel_path)
        packetization_handoff = _extract_receipt_field(text, "packetization_handoff")
        if PACKETIZATION_GATE_STEP not in packetization_handoff:
            errors.append(
                _canon_sweep_receipt_error(
                    f"{rel_path} shared range requires packetization_handoff with {PACKETIZATION_GATE_STEP}"
                )
            )
        if require_packetization_report and not packetization_reports:
            errors.append(
                _canon_sweep_receipt_error(
                    f"{rel_path} shared range requires a packetization gate report artifact"
                )
            )
    return receipts, errors


def _receipt_preflight_packetization_gate(
    *,
    root: Path,
    rel_path: str,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    expected_surface = "non-superseded final packetization gate report with no blocking coverage rows"
    errors: list[dict[str, str]] = []
    status = _extract_status(root / rel_path)
    if _is_superseded_packetization_status(status):
        errors.append(
            {
                "code": "superseded_packetization_report",
                "detail": f"step:packetization_gate/packetization_gate: {rel_path} status=Superseded is not active",
            }
        )
    elif not _is_final_status(status):
        errors.append(
            {
                "code": "non_final_artifact_status",
                "detail": f"step:packetization_gate/packetization_gate: {rel_path} status={status or 'missing'}",
            }
        )
    if _report_has_blocking_packetization_rows(root, rel_path):
        report_readback = _packetization_readback(
            root=root,
            active_reports=[rel_path],
            artifacts=[],
        )
        present = _present_blocking_coverage_counts(report_readback)
        errors.append(
            {
                "code": "blocking_packetization_rows",
                "detail": (
                    "step:packetization_gate/packetization_gate: "
                    f"{rel_path} contains {', '.join(present) or 'structural blocking rows/counts'}"
                ),
            }
        )
    errors.extend(_packetization_report_schema_errors(root, rel_path))
    return [
        {
            "step": PACKETIZATION_GATE_STEP,
            "kind": PACKETIZATION_GATE_RECEIPT_KIND,
            "receipt": PACKETIZATION_GATE_RECEIPT_NAME,
            "path": rel_path,
            "required": True,
            "present": not errors,
            "expected_surface": expected_surface,
        }
    ], errors


def _receipt_preflight_has_no_followups(text: str) -> bool:
    return any(line.strip().upper() == "NO FOLLOWUPS" for line in text.splitlines())


def _receipt_preflight_markdown_field(text: str, field: str) -> str:
    candidate_pattern = re.compile(
        rf"^\s*\*\*{re.escape(field)}:\*\*.*$",
        re.IGNORECASE,
    )
    canonical_pattern = re.compile(
        rf"^\*\*{re.escape(field)}:\*\* (?P<value>\S(?:.*\S)?)$"
    )
    candidates = [
        line for line in text.splitlines() if candidate_pattern.fullmatch(line)
    ]
    if len(candidates) != 1:
        return ""
    match = canonical_pattern.fullmatch(candidates[0])
    return match.group("value") if match else ""


def _docs_finalize_range_parts(range_ref: str) -> tuple[str, str] | None:
    parts = range_ref.strip().split("..")
    if len(parts) != 2:
        return None
    base, head = (part.strip() for part in parts)
    if not DOCS_FINALIZE_RANGE_COMPONENT_RE.fullmatch(base):
        return None
    if not DOCS_FINALIZE_RANGE_COMPONENT_RE.fullmatch(head):
        return None
    return base, head


def _receipt_preflight_docs_finalize_legacy(
    *,
    root: Path,
    rel_path: str,
    role: str,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Keep the ordinary general/followups closeout grammar compatible."""

    expected_surface = (
        "docs-finalize general output with parseable `Process improvements` section, "
        "or followups lane output containing literal `NO FOLLOWUPS`"
    )
    text = _read_text(root / rel_path)
    receipt = {
        "step": "step:docs_finalize",
        "kind": "docs_finalize",
        "receipt": "process_improvements_or_followups",
        "path": rel_path,
        "required": True,
        "present": True,
        "expected_surface": expected_surface,
    }
    if re.search(r"^\s*##+\s+(?:\d+[.)]\s*)?Process improvements\b", text, re.IGNORECASE | re.MULTILINE):
        from process_improvements_collect import parse_process_improvements_section

        try:
            parse_process_improvements_section(text, role=role, default_source_ref=rel_path)
        except ValueError as exc:
            receipt["present"] = False
            return [receipt], [
                {
                    "code": "malformed_process_improvements",
                    "detail": f"step:docs_finalize/process_improvements: {exc} in {rel_path}",
                }
            ]
        return [receipt], []

    if _receipt_preflight_has_no_followups(text):
        return [receipt], []

    receipt["present"] = False
    return [receipt], [
        {
            "code": "missing_required_receipt",
            "detail": (
                f"step:docs_finalize/process_improvements: missing parseable Process improvements section "
                f"or NO FOLLOWUPS in {rel_path}; expected {expected_surface}"
            ),
        }
    ]


def _receipt_preflight_docs_finalize(
    *,
    root: Path,
    rel_path: str,
    role: str,
    range_ref: str | None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    if range_ref is None:
        return _receipt_preflight_docs_finalize_legacy(root=root, rel_path=rel_path, role=role)

    expected_surface = (
        "Architect `review.v1` docs-finalize receipt at the exact supplied range path with "
        "a byte-identical docs_finalize_receipt_path readback and parseable `Process improvements`"
    )
    text = _read_text(root / rel_path)
    receipt = {
        "step": "step:docs_finalize",
        "kind": "docs_finalize",
        "receipt": "architect_docs_finalize_receipt",
        "path": rel_path,
        "required": True,
        "present": True,
        "expected_surface": expected_surface,
    }
    errors: list[dict[str, str]] = []
    range_parts = _docs_finalize_range_parts(range_ref)
    if range_parts is None:
        errors.append(
            {
                "code": "invalid_docs_finalize_range",
                "detail": f"step:docs_finalize/range: expected full-or-short SHA range BASE..HEAD; got {range_ref!r}",
            }
        )
    else:
        base, head = range_parts
        path_match = DOCS_FINALIZE_RECEIPT_PATH_RE.fullmatch(rel_path)
        if path_match is None:
            errors.append(
                {
                    "code": "invalid_docs_finalize_receipt_path",
                    "detail": (
                        "step:docs_finalize/path: expected "
                        "docs/reviews/<stamp>_docs_finalize_receipt_range_<base7>_<head7>.md; "
                        f"got {rel_path}"
                    ),
                }
            )
        elif (path_match.group("base"), path_match.group("head")) != (base[:7], head[:7]):
            errors.append(
                {
                    "code": "docs_finalize_receipt_range_mismatch",
                    "detail": (
                        f"step:docs_finalize/path: {rel_path} does not match supplied range "
                        f"{base}..{head}"
                    ),
                }
            )

        for field, expected in (("BASE", base), ("HEAD", head)):
            actual = _receipt_preflight_markdown_field(text, field)
            if actual != expected:
                errors.append(
                    {
                        "code": "docs_finalize_receipt_identity_mismatch",
                        "detail": (
                            f"step:docs_finalize/{field.lower()}: expected={expected}; "
                            f"actual={actual or 'missing'} in {rel_path}"
                        ),
                    }
                )

    if role != "Architect":
        errors.append(
            {
                "code": "docs_finalize_role_mismatch",
                "detail": f"step:docs_finalize/role: expected=Architect; actual={role or 'missing'}",
            }
        )
    receipt_role = _receipt_preflight_markdown_field(text, "Role")
    if receipt_role != "Architect":
        errors.append(
            {
                "code": "docs_finalize_receipt_role_mismatch",
                "detail": (
                    f"step:docs_finalize/receipt-role: expected=Architect; "
                    f"actual={receipt_role or 'missing'} in {rel_path}"
                ),
            }
        )
    if _receipt_preflight_markdown_field(text, "Schema version") != "review.v1":
        errors.append(
            {
                "code": "docs_finalize_receipt_schema_mismatch",
                "detail": f"step:docs_finalize/schema: expected=review.v1 in {rel_path}",
            }
        )
    status = _receipt_preflight_markdown_field(text, "Status")
    if not _is_final_status(status):
        errors.append(
            {
                "code": "non_final_artifact_status",
                "detail": f"step:docs_finalize/docs_finalize_receipt: {rel_path} status={status or 'missing'}",
            }
        )

    readbacks = [line for line in text.splitlines() if "docs_finalize_receipt_path=" in line]
    expected_readback = f"docs_finalize_receipt_path={rel_path}"
    if readbacks != [expected_readback]:
        errors.append(
            {
                "code": "docs_finalize_receipt_readback_mismatch",
                "detail": (
                    f"step:docs_finalize/readback: expected exactly {expected_readback!r}; "
                    f"actual={readbacks or ['missing']}"
                ),
            }
        )

    if _receipt_preflight_has_no_followups(text) or any(
        line.strip().upper() == "NO PROGRESS UPDATES" for line in text.splitlines()
    ):
        errors.append(
            {
                "code": "disallowed_docs_finalize_carrier",
                "detail": f"step:docs_finalize/process_improvements: non-primary carrier in {rel_path}",
            }
        )

    process_improvements_heading_re = re.compile(
        r"^\s*#{2,}\s+(?:\d+[.)]\s*)?Process improvements\b.*$",
        re.IGNORECASE,
    )
    process_improvements_headings = [
        line
        for line in text.splitlines()
        if process_improvements_heading_re.fullmatch(line)
    ]
    if process_improvements_headings != ["## Process improvements"]:
        errors.append(
            {
                "code": "docs_finalize_process_improvements_heading_mismatch",
                "detail": (
                    "step:docs_finalize/process_improvements: expected exactly "
                    f"'## Process improvements'; actual={process_improvements_headings or ['missing']} "
                    f"in {rel_path}"
                ),
            }
        )
    else:
        from process_improvements_collect import parse_process_improvements_section

        try:
            parse_process_improvements_section(text, role="Architect", default_source_ref=rel_path)
        except ValueError as exc:
            errors.append(
                {
                    "code": "malformed_process_improvements",
                    "detail": f"step:docs_finalize/process_improvements: {exc} in {rel_path}",
                }
            )

    if errors:
        receipt["present"] = False
    return [receipt], errors


def validate_post_merge_receipt_preflight(
    *,
    root: Path,
    step: str,
    path: str | Path,
    packetization_required: bool = False,
    target_packet_required: bool = False,
    packetization_reports: list[str] | None = None,
    packetization_range: str | None = None,
    role: str = "Coder",
    docs_finalize_range: str | None = None,
    mirror_policy: MirrorPolicy = GENERIC_MIRROR_POLICY,
) -> dict[str, Any]:
    """Validate one freshly materialized post-merge receipt using final-report schema truth."""

    root_resolved = root.resolve()
    reports = packetization_reports or []
    step_norm = step.strip()
    raw_path = str(path).strip()
    _, rel_path, path_errors = _receipt_preflight_rel_path(root_resolved, path)
    if step_norm == "docs_finalize" and docs_finalize_range is not None and Path(raw_path).is_absolute():
        path_errors.append(
            {
                "code": "absolute_docs_finalize_receipt_path",
                "detail": f"step:docs_finalize/path: expected repo-relative path; got {raw_path}",
            }
        )
    receipts: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    proof_scope = "step_local_receipt"
    terminal_readiness = "not_evaluated"
    packetization_state = "not_required"
    if packetization_required and step_norm in {
        "plan_harvest",
        "canon_sweep",
        "post_merge_audit",
        "packetization_gate",
    }:
        packetization_state = "required_validation_blocked"
    if path_errors:
        errors.extend(path_errors)
    elif step_norm == "plan_harvest":
        receipts, errors = _receipt_preflight_substep(
            root=root_resolved,
            step="step:plan_harvest",
            kind="plan_harvest",
            rel_path=rel_path,
            packetization_required=packetization_required,
            packetization_reports=reports,
            require_packetization_report=False,
        )
        if packetization_required and not errors:
            packetization_state = "handoff_recorded_future_step_pending"
    elif step_norm == "canon_sweep":
        receipts, errors = _receipt_preflight_canon_sweep(
            root=root_resolved,
            rel_path=rel_path,
            packetization_required=packetization_required,
            packetization_reports=reports,
            require_packetization_report=False,
        )
        if packetization_required and not errors:
            packetization_state = "handoff_recorded_future_step_pending"
    elif step_norm == "post_merge_audit":
        receipts, errors = _receipt_preflight_substep(
            root=root_resolved,
            step="step:post_merge_audit",
            kind="post_merge_audit",
            rel_path=rel_path,
            packetization_required=packetization_required,
            packetization_reports=reports,
            require_packetization_report=False,
        )
        if packetization_required:
            _, packetization_errors = validate_packetization_reports_for_receipt_preflight(
                root=root_resolved,
                range_ref=packetization_range,
                packetization_reports=reports,
                mirror_policy=mirror_policy,
            )
            errors.extend(packetization_errors)
        if not path_errors:
            audit_artifacts = post_merge_audit_lint.load_audit_artifacts(root_resolved, [rel_path])
            authority_findings = [
                finding
                for artifact in audit_artifacts
                for finding in post_merge_audit_lint._lint_current_audit_status_authority(artifact)
            ]
            errors.extend(
                {
                    "code": "post_merge_audit_authority_blocked",
                    "detail": finding.render(),
                }
                for finding in authority_findings
            )
        if packetization_required and not errors:
            packetization_state = "active_report_validated"
    elif step_norm == "packetization_gate":
        receipts, errors = _receipt_preflight_packetization_gate(root=root_resolved, rel_path=rel_path)
        if packetization_required and not errors:
            packetization_state = "packetization_gate_validated"
    elif step_norm == "docs_finalize":
        receipts, errors = _receipt_preflight_docs_finalize(
            root=root_resolved,
            rel_path=rel_path,
            role=role,
            range_ref=docs_finalize_range,
        )
    else:
        errors = [
            {
                "code": "unsupported_step",
                "detail": f"{step_norm or '(missing)'} is not one of {', '.join(RECEIPT_PREFLIGHT_STEPS)}",
            }
        ]

    enriched_errors = _receipt_preflight_with_next_actions(errors)
    return {
        "schema_version": RECEIPT_PREFLIGHT_SCHEMA_VERSION,
        "status": "blocked" if enriched_errors else "ok",
        "step": step_norm,
        "path": rel_path,
        "packetization_required": packetization_required,
        "packetization_report_required": packetization_required,
        "target_packet_required": target_packet_required,
        "packetization_reports": reports,
        "proof_scope": proof_scope,
        "terminal_readiness": terminal_readiness,
        "packetization_state": packetization_state,
        "receipts": receipts,
        "errors": enriched_errors,
    }


def _validate_operational_receipt(
    *,
    root: Path,
    artifacts: list[dict[str, Any]],
    required: bool,
    base: str,
    head: str,
    range_candidates: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    if not required:
        return [], []

    matching_artifacts = [
        artifact
        for artifact in artifacts
        if artifact["kind"] == OPERATIONAL_RECEIPT_KIND and artifact.get("path")
    ]
    if len(matching_artifacts) != 1:
        return [], []

    artifact_path = str(matching_artifacts[0]["path"])
    git_state = str(matching_artifacts[0].get("git_state") or "")
    validation_errors = _validate_operational_receipt_text(
        _read_text(root / artifact_path),
        artifact_path=artifact_path,
        base=base,
        head=head,
        root=root,
        artifact_git_state=git_state,
        range_candidates=range_candidates,
    )
    if not matching_artifacts[0].get("status_final"):
        validation_errors.append(
            {
                "code": "inconsistent_receipt",
                "detail": (
                    f"step:ready_to_push/post_merge_operational_closeout: {artifact_path} "
                    f"status={matching_artifacts[0].get('status') or 'missing'} is not final"
                ),
            }
        )
    present = not validation_errors
    receipts = [
        {
            "step": "step:ready_to_push",
            "kind": OPERATIONAL_RECEIPT_KIND,
            "receipt": "post_merge_operational_closeout",
            "path": artifact_path,
            "required": True,
            "present": present,
            "expected_surface": OPERATIONAL_RECEIPT_EXPECTED_SURFACE,
        }
    ]
    if present:
        return receipts, []
    return receipts, validation_errors


def _operational_receipt_artifact(
    *,
    artifacts: list[dict[str, Any]],
) -> dict[str, Any] | None:
    matching_artifacts = [
        artifact
        for artifact in artifacts
        if artifact["kind"] == OPERATIONAL_RECEIPT_KIND and artifact.get("path")
    ]
    if len(matching_artifacts) != 1:
        return None
    return matching_artifacts[0]


def _operational_receipt_payload(
    *,
    root: Path,
    artifacts: list[dict[str, Any]],
) -> dict[str, Any] | None:
    artifact = _operational_receipt_artifact(artifacts=artifacts)
    if not artifact:
        return None
    payload = _extract_json_block(_read_text(root / str(artifact["path"])))
    return payload if isinstance(payload, dict) else None


def _is_pre_enforcement_ready_to_push_terminal_receipt(payload: dict[str, Any] | None) -> bool:
    if not payload:
        return False
    generated_at = _parse_receipt_datetime(payload.get("generated_at", ""))
    if generated_at is None:
        return False
    return generated_at < READY_TO_PUSH_CLOSEOUT_REQUIRED_AFTER_DT


def _ready_to_push_closeout_receipt_error(artifact_path: str, detail: str) -> dict[str, str]:
    return {
        "code": "inconsistent_receipt",
        "detail": f"step:ready_to_push/ready_to_push_terminal_proof: {artifact_path}: {detail}",
    }


def _is_repo_relative_path_value(value: str) -> bool:
    if not _is_meaningful_receipt_value(value):
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts


def _validate_ready_to_push_closeout_receipt_text(
    *,
    text: str,
    artifact_path: str,
    base: str,
    head: str,
) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    payload = _extract_named_json_block(text, READY_TO_PUSH_CLOSEOUT_JSON_HEADING)
    if not payload:
        return None, [
            _ready_to_push_closeout_receipt_error(
                artifact_path,
                f"malformed/token-only `## {READY_TO_PUSH_CLOSEOUT_JSON_HEADING}`; expected {READY_TO_PUSH_CLOSEOUT_EXPECTED_SURFACE}",
            )
        ]

    errors: list[dict[str, str]] = []
    expected = {
        "schema_version": READY_TO_PUSH_CLOSEOUT_SCHEMA_VERSION,
        "range": f"{base}..{head}",
        "base": base,
        "head": head,
        "range_id": f"{base[:7]}..{head[:7]}",
        "terminal_state": READY_TO_PUSH_TERMINAL_STATE,
        "final_bundle_status": "ok",
        "pending_owner_gate": "git push",
        "generated_by": "scripts/post_merge_ready_to_push_closeout.py",
    }
    for field, expected_value in expected.items():
        actual = _receipt_field_string(payload.get(field, ""))
        if actual != expected_value:
            errors.append(
                _ready_to_push_closeout_receipt_error(
                    artifact_path,
                    f"{field}={actual or 'missing'}; expected={expected_value}",
                )
            )

    if _receipt_field_string(payload.get("final_bundle_status", "")) == "expected_pending_receipt":
        errors.append(
            _ready_to_push_closeout_receipt_error(
                artifact_path,
                "expected_pending_receipt is pre-receipt readback and cannot be terminal proof",
            )
        )

    generated_at = _parse_receipt_datetime(payload.get("generated_at_utc", ""))
    if generated_at is None:
        errors.append(
            _ready_to_push_closeout_receipt_error(
                artifact_path,
                "generated_at_utc must be an ISO timestamp",
            )
        )
    source_command = _receipt_field_string(payload.get("source_command", ""))
    if "planveyor_post_merge_ready_to_push_closeout" not in source_command:
        errors.append(
            _ready_to_push_closeout_receipt_error(
                artifact_path,
                "source_command must include planveyor_post_merge_ready_to_push_closeout",
            )
        )
    action = _receipt_field_string(payload.get("action", ""))
    if not _is_meaningful_receipt_value(action):
        errors.append(_ready_to_push_closeout_receipt_error(artifact_path, "action is required"))

    tracker_path = _receipt_field_string(payload.get("tracker_path", ""))
    if not _is_repo_relative_path_value(tracker_path):
        errors.append(
            _ready_to_push_closeout_receipt_error(
                artifact_path,
                "tracker_path must be repo-relative",
            )
        )

    tracker_tick = payload.get("tracker_tick")
    if not isinstance(tracker_tick, dict):
        errors.append(_ready_to_push_closeout_receipt_error(artifact_path, "tracker_tick must be an object"))
    else:
        for field in ("intent", "result"):
            if not _is_meaningful_receipt_value(_receipt_field_string(tracker_tick.get(field, ""))):
                errors.append(
                    _ready_to_push_closeout_receipt_error(
                        artifact_path,
                        f"tracker_tick.{field} is required",
                    )
                )
        tick_result = _receipt_field_string(tracker_tick.get("result", ""))
        if tick_result and tick_result not in READY_TO_PUSH_CLOSEOUT_TRACKER_TICK_RESULTS:
            allowed = "|".join(sorted(READY_TO_PUSH_CLOSEOUT_TRACKER_TICK_RESULTS))
            errors.append(
                _ready_to_push_closeout_receipt_error(
                    artifact_path,
                    f"tracker_tick.result={tick_result} unsupported; expected={allowed}",
                )
            )

    for field in READY_TO_PUSH_CLOSEOUT_PATH_LIST_FIELDS:
        value = payload.get(field)
        if not isinstance(value, list):
            errors.append(_ready_to_push_closeout_receipt_error(artifact_path, f"{field} must be a list"))
            continue
        for index, item in enumerate(value):
            item_string = _receipt_field_string(item)
            if not _is_repo_relative_path_value(item_string):
                errors.append(
                    _ready_to_push_closeout_receipt_error(
                        artifact_path,
                        f"{field}[{index}] must be a repo-relative path",
                    )
                )

    for field in (
        "unexpected_staged_paths",
        "suspicious_paths",
        "unstaged_tracked_paths",
        "untracked_accepted_paths",
    ):
        value = payload.get(field)
        if isinstance(value, list) and value:
            errors.append(
                _ready_to_push_closeout_receipt_error(
                    artifact_path,
                    f"{field} must be empty for terminal proof",
                )
            )

    return payload, errors


def _validate_ready_to_push_closeout_receipt(
    *,
    root: Path,
    artifacts: list[dict[str, Any]],
    completed_steps: set[str],
    current_step: str,
    base: str,
    head: str,
) -> tuple[list[dict[str, Any]], list[dict[str, str]], dict[str, Any]]:
    operational_artifact = _operational_receipt_artifact(artifacts=artifacts)
    operational_payload = _operational_receipt_payload(root=root, artifacts=artifacts)
    operational_git_state = str(operational_artifact.get("git_state") or "") if operational_artifact else ""
    terminal_required = "step:ready_to_push" in completed_steps
    if (
        terminal_required
        and operational_git_state == "clean"
        and _is_pre_enforcement_ready_to_push_terminal_receipt(operational_payload)
    ):
        terminal_required = False

    matching_artifacts = [
        artifact
        for artifact in artifacts
        if artifact["kind"] == READY_TO_PUSH_CLOSEOUT_RECEIPT_KIND and artifact.get("path")
    ]
    proof_state = {
        "state": "not_applicable",
        "pre_receipt_state": "",
        "required": terminal_required,
        "path": "",
        "schema_version": READY_TO_PUSH_CLOSEOUT_SCHEMA_VERSION,
    }
    if not matching_artifacts:
        if terminal_required:
            missing_path = f"docs/reviews/*_ready_to_push_closeout_range_{base[:7]}_{head[:7]}.md"
            return [
                {
                    "step": "step:ready_to_push",
                    "kind": READY_TO_PUSH_CLOSEOUT_RECEIPT_KIND,
                    "receipt": "ready_to_push_terminal_proof",
                    "path": "(none)",
                    "required": True,
                    "present": False,
                    "expected_surface": READY_TO_PUSH_CLOSEOUT_EXPECTED_SURFACE,
                }
            ], [
                {
                    "code": "missing_required_receipt",
                    "detail": f"step:ready_to_push/ready_to_push_terminal_proof: {missing_path}",
                }
            ], {**proof_state, "state": "missing_required"}
        if current_step == "step:ready_to_push":
            proof_state["state"] = READY_TO_PUSH_PRE_TERMINAL_STATE
            proof_state["pre_receipt_state"] = "pre_receipt_pending"
        elif "step:ready_to_push" in completed_steps:
            proof_state["state"] = "legacy_pre_enforcement_compatible"
        return [], [], proof_state

    artifact = matching_artifacts[0]
    artifact_path = str(artifact["path"])
    payload, validation_errors = _validate_ready_to_push_closeout_receipt_text(
        text=_read_text(root / artifact_path),
        artifact_path=artifact_path,
        base=base,
        head=head,
    )
    if not artifact.get("status_final"):
        validation_errors.append(
            _ready_to_push_closeout_receipt_error(
                artifact_path,
                f"status={artifact.get('status') or 'missing'} is not final",
            )
        )
    if terminal_required and str(artifact.get("git_state") or "") != "clean":
        validation_errors.append(
            _ready_to_push_closeout_receipt_error(
                artifact_path,
                f"git_state={artifact.get('git_state') or 'missing'}; expected=clean committed proof",
            )
        )
    present = not validation_errors
    receipt = {
        "step": "step:ready_to_push",
        "kind": READY_TO_PUSH_CLOSEOUT_RECEIPT_KIND,
        "receipt": "ready_to_push_terminal_proof",
        "path": artifact_path,
        "required": terminal_required,
        "present": present,
        "expected_surface": READY_TO_PUSH_CLOSEOUT_EXPECTED_SURFACE,
    }
    proof_payload = payload or {}
    proof_state = {
        **proof_state,
        "state": READY_TO_PUSH_TERMINAL_STATE if present else "invalid",
        "pre_receipt_state": "closed_by_terminal_proof" if present else "invalid",
        "path": artifact_path,
        "final_bundle_status": _receipt_field_string(proof_payload.get("final_bundle_status", "")),
        "pending_owner_gate": _receipt_field_string(proof_payload.get("pending_owner_gate", "")),
    }
    return [receipt], validation_errors, proof_state


def _validate_range_review_risk_packet(
    *,
    root: Path,
    completed_steps: set[str],
    current_step: str,
    ready_to_push_terminal_proof: dict[str, Any],
    base: str,
    head: str,
) -> tuple[dict[str, Any], list[dict[str, str]], str | None]:
    terminal_required = bool(ready_to_push_terminal_proof.get("required")) or (
        ready_to_push_terminal_proof.get("state") == READY_TO_PUSH_TERMINAL_STATE
    )
    if not terminal_required:
        state = (
            READY_TO_PUSH_PRE_TERMINAL_STATE
            if current_step == "step:ready_to_push"
            else "not_applicable"
        )
        return {
            "state": state,
            "required": False,
            "path": "",
            "schema_version": range_review_risk_packet.SCHEMA_VERSION,
            "source": "range_review_risk_packet",
        }, [], None

    if not base or not head:
        return {
            "state": "missing_range",
            "required": True,
            "path": "",
            "schema_version": range_review_risk_packet.SCHEMA_VERSION,
            "source": "range_review_risk_packet",
        }, [
            {
                "code": "missing_range",
                "detail": "range_review_risk_packet: missing base/head for risk packet validation",
            }
        ], None

    readback = range_review_risk_packet.read_risk_packet(root, range_ref=f"{base}..{head}")
    errors = [
        {
            "code": error.code,
            "detail": f"range_review_risk_packet: {error.detail}",
        }
        for error in readback.errors
    ]
    path = readback.packet_path if readback.ok else ""
    return {
        **readback.as_dict(),
        "required": True,
        "source": "range_review_risk_packet",
    }, errors, path or None


def _extract_operational_archive_snapshot(
    *,
    root: Path,
    artifacts: list[dict[str, Any]],
) -> dict[str, Any] | None:
    matching_artifacts = [
        artifact
        for artifact in artifacts
        if artifact["kind"] == OPERATIONAL_RECEIPT_KIND and artifact.get("path")
    ]
    if len(matching_artifacts) != 1:
        return None
    payload = _extract_json_block(_read_text(root / str(matching_artifacts[0]["path"])))
    if not payload:
        return None
    archive_snapshot = payload.get("archive_snapshot")
    if isinstance(archive_snapshot, dict):
        return archive_snapshot
    return None


def _extract_operational_docs_hygiene_suggest_summary(
    *,
    root: Path,
    artifacts: list[dict[str, Any]],
) -> dict[str, Any] | None:
    matching_artifacts = [
        artifact
        for artifact in artifacts
        if artifact["kind"] == OPERATIONAL_RECEIPT_KIND and artifact.get("path")
    ]
    if len(matching_artifacts) != 1:
        return None
    payload = _extract_json_block(_read_text(root / str(matching_artifacts[0]["path"])))
    if not payload:
        return None
    summary = payload.get("docs_hygiene_suggest_summary")
    if isinstance(summary, dict):
        return summary
    return None


def _extract_operational_followups_triage_launch_receipt(
    *,
    root: Path,
    artifacts: list[dict[str, Any]],
) -> dict[str, Any] | None:
    matching_artifacts = [
        artifact
        for artifact in artifacts
        if artifact["kind"] == OPERATIONAL_RECEIPT_KIND and artifact.get("path")
    ]
    if len(matching_artifacts) != 1:
        return None
    payload = _extract_json_block(_read_text(root / str(matching_artifacts[0]["path"])))
    if not payload:
        return None
    receipt = payload.get("followups_triage_launch_receipt")
    if isinstance(receipt, dict):
        return receipt
    return None


def _extract_operational_followups_lane_reconciliation(
    *,
    root: Path,
    artifacts: list[dict[str, Any]],
) -> dict[str, Any] | None:
    matching_artifacts = [
        artifact
        for artifact in artifacts
        if artifact["kind"] == OPERATIONAL_RECEIPT_KIND and artifact.get("path")
    ]
    if len(matching_artifacts) != 1:
        return None
    payload = _extract_json_block(_read_text(root / str(matching_artifacts[0]["path"])))
    if not payload:
        return None
    reconciliation = payload.get("followups_lane_reconciliation")
    if isinstance(reconciliation, dict):
        return reconciliation
    return None


def _extract_operational_process_improvements_open_summary(
    *,
    root: Path,
    artifacts: list[dict[str, Any]],
) -> dict[str, Any] | None:
    matching_artifacts = [
        artifact
        for artifact in artifacts
        if artifact["kind"] == OPERATIONAL_RECEIPT_KIND and artifact.get("path")
    ]
    if len(matching_artifacts) != 1:
        return None
    payload = _extract_json_block(_read_text(root / str(matching_artifacts[0]["path"])))
    if not payload:
        return None
    summary = payload.get("process_improvements_open_summary")
    if isinstance(summary, dict):
        return summary
    return None


def _extract_named_json_block(text: str, heading: str) -> dict[str, Any] | None:
    heading_match = re.search(rf"^\s*## {re.escape(heading)}\s*$", text, flags=re.MULTILINE)
    if not heading_match:
        return None
    block_match = re.search(r"```json\s*(?P<body>\{.*?\})\s*```", text[heading_match.end():], flags=re.DOTALL)
    if not block_match:
        return None
    try:
        payload = json.loads(block_match.group("body"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _extract_json_block(text: str) -> dict[str, Any] | None:
    return _extract_named_json_block(text, "Operational receipt JSON")


def _operational_receipt_error(artifact_path: str, detail: str) -> dict[str, str]:
    return {
        "code": "inconsistent_receipt",
        "detail": f"step:ready_to_push/post_merge_operational_closeout: {artifact_path}: {detail}",
    }


def _receipt_field_string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _docs_hygiene_suggest_canonical_command(range_ref: str) -> str:
    return f"{DOCS_HYGIENE_SUGGEST_CANONICAL_PREFIX}{range_ref}"


def _parse_receipt_datetime(value: Any) -> datetime | None:
    raw = _receipt_field_string(value)
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _is_pre_enforcement_archive_snapshot_receipt(payload: dict[str, Any]) -> bool:
    generated_at = _parse_receipt_datetime(payload.get("generated_at", ""))
    if generated_at is None:
        return False
    return generated_at < ARCHIVE_SNAPSHOT_RECEIPT_REQUIRED_AFTER_DT


def _is_pre_enforcement_archive_snapshot_fresh_export_receipt(payload: dict[str, Any]) -> bool:
    generated_at = _parse_receipt_datetime(payload.get("generated_at", ""))
    if generated_at is None:
        return False
    return generated_at < ARCHIVE_SNAPSHOT_FRESH_EXPORT_REQUIRED_AFTER_DT


def _is_pre_enforcement_docs_quality_receipt(payload: dict[str, Any]) -> bool:
    generated_at = _parse_receipt_datetime(payload.get("generated_at", ""))
    if generated_at is None:
        return False
    return generated_at < DOCS_INDEX_CONTEXT_RECEIPT_REQUIRED_AFTER_DT


def _is_pre_enforcement_docs_hygiene_suggest_summary_receipt(payload: dict[str, Any]) -> bool:
    generated_at = _parse_receipt_datetime(payload.get("generated_at", ""))
    if generated_at is None:
        return False
    return generated_at < DOCS_HYGIENE_SUGGEST_SUMMARY_REQUIRED_AFTER_DT


def _is_pre_enforcement_followups_triage_launch_receipt(payload: dict[str, Any]) -> bool:
    generated_at = _parse_receipt_datetime(payload.get("generated_at", ""))
    if generated_at is None:
        return False
    return generated_at < FOLLOWUPS_TRIAGE_LAUNCH_RECEIPT_REQUIRED_AFTER_DT


def _is_pre_enforcement_process_improvements_open_summary(payload: dict[str, Any]) -> bool:
    generated_at = _parse_receipt_datetime(payload.get("generated_at", ""))
    if generated_at is None:
        return False
    return generated_at < PROCESS_IMPROVEMENTS_OPEN_SUMMARY_REQUIRED_AFTER_DT


def _is_pre_enforcement_followups_lane_reconciliation(payload: dict[str, Any]) -> bool:
    generated_at = _parse_receipt_datetime(payload.get("generated_at", ""))
    if generated_at is None:
        return False
    return generated_at < FOLLOWUPS_LANE_RECONCILIATION_REQUIRED_AFTER_DT


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


def _summary_int(
    summary: dict[str, str],
    key: str,
    *,
    artifact_path: str,
    step: str,
) -> tuple[int | None, dict[str, str] | None]:
    raw = summary.get(key, "")
    try:
        value = int(raw)
    except ValueError:
        return None, _operational_receipt_error(artifact_path, f"{step}: count_summary.{key} must be an integer")
    if value < 0:
        return None, _operational_receipt_error(artifact_path, f"{step}: count_summary.{key} must be >= 0")
    return value, None


def _summary_rate(
    summary: dict[str, str],
    key: str,
    *,
    artifact_path: str,
    step: str,
) -> tuple[float | None, dict[str, str] | None]:
    raw = summary.get(key, "")
    try:
        value = float(raw)
    except ValueError:
        return None, _operational_receipt_error(artifact_path, f"{step}: count_summary.{key} must be a decimal rate")
    if value < 0.0 or value > 1.0:
        return None, _operational_receipt_error(artifact_path, f"{step}: count_summary.{key} must be between 0 and 1")
    return value, None


def _validate_docs_index_context_row(row: dict[str, Any], *, artifact_path: str) -> list[dict[str, str]]:
    step = "docs_index_context"
    errors: list[dict[str, str]] = []
    in_scope = _receipt_field_string(row.get("in_scope", ""))
    no_op_reason = _receipt_field_string(row.get("no_op_reason", ""))
    if in_scope == "no":
        if no_op_reason not in DOCS_INDEX_CONTEXT_NO_OP_REASONS:
            allowed = "|".join(sorted(DOCS_INDEX_CONTEXT_NO_OP_REASONS))
            errors.append(_operational_receipt_error(artifact_path, f"{step}: no_op_reason must be one of {allowed}"))
        return errors
    if in_scope != "yes":
        return errors

    summary = _parse_count_summary(_receipt_field_string(row.get("count_summary", "")))
    missing = [field for field in DOCS_INDEX_CONTEXT_REQUIRED_INT_FIELDS if field not in summary]
    if "canon_state" not in summary:
        missing.append("canon_state")
    if missing:
        errors.append(_operational_receipt_error(artifact_path, f"{step}: count_summary missing field(s): {', '.join(missing)}"))
        return errors

    for corpus in ("plans", "followups"):
        total, error = _summary_int(summary, f"{corpus}_total", artifact_path=artifact_path, step=step)
        if error:
            errors.append(error)
            continue
        covered, error = _summary_int(summary, f"{corpus}_covered", artifact_path=artifact_path, step=step)
        if error:
            errors.append(error)
            continue
        uncovered, error = _summary_int(summary, f"{corpus}_uncovered", artifact_path=artifact_path, step=step)
        if error:
            errors.append(error)
            continue
        assert total is not None and covered is not None and uncovered is not None
        if total != covered + uncovered:
            errors.append(_operational_receipt_error(artifact_path, f"{step}: {corpus}_total must equal {corpus}_covered + {corpus}_uncovered"))
        if uncovered != 0:
            errors.append(_operational_receipt_error(artifact_path, f"{step}: {corpus}_uncovered must be 0"))
        state = summary.get(f"{corpus}_state", "").strip().lower()
        if total == 0:
            reason = summary.get(f"{corpus}_reason", "").strip()
            if state != "empty" or not _is_meaningful_receipt_value(reason):
                errors.append(_operational_receipt_error(artifact_path, f"{step}: empty {corpus} corpus requires {corpus}_state=empty and {corpus}_reason"))
        elif state and state != "covered":
            errors.append(_operational_receipt_error(artifact_path, f"{step}: non-empty {corpus} corpus requires {corpus}_state=covered when present"))

    canon_state = summary.get("canon_state", "").strip().lower()
    if canon_state not in DOCS_INDEX_CONTEXT_CANON_STATES:
        allowed = "|".join(sorted(DOCS_INDEX_CONTEXT_CANON_STATES))
        errors.append(_operational_receipt_error(artifact_path, f"{step}: count_summary.canon_state must be one of {allowed}"))
    return errors


def _validate_retrieval_metrics_row(row: dict[str, Any], *, artifact_path: str) -> list[dict[str, str]]:
    step = "retrieval_metrics"
    errors: list[dict[str, str]] = []
    in_scope = _receipt_field_string(row.get("in_scope", ""))
    no_op_reason = _receipt_field_string(row.get("no_op_reason", ""))
    if in_scope == "no":
        if not _is_enum_like_reason(no_op_reason):
            errors.append(_operational_receipt_error(artifact_path, f"{step}: skipped/out-of-scope row requires enum-like no_op_reason"))
        return errors
    if in_scope != "yes":
        return errors

    summary = _parse_count_summary(_receipt_field_string(row.get("count_summary", "")))
    missing = [field for field in RETRIEVAL_METRICS_REQUIRED_INT_FIELDS if field not in summary]
    missing.extend(field for field in RETRIEVAL_METRICS_REQUIRED_RATE_FIELDS if field not in summary)
    if "read_log_status" not in summary:
        missing.append("read_log_status")
    if "used_for_decision" not in summary:
        missing.append("used_for_decision")
    if missing:
        errors.append(_operational_receipt_error(artifact_path, f"{step}: count_summary missing field(s): {', '.join(missing)}"))
        return errors

    query_total, error = _summary_int(summary, "query_total", artifact_path=artifact_path, step=step)
    if error:
        errors.append(error)
    evaluated_total, error = _summary_int(summary, "evaluated_total", artifact_path=artifact_path, step=step)
    if error:
        errors.append(error)
    _, error = _summary_int(summary, "read_events_total", artifact_path=artifact_path, step=step)
    if error:
        errors.append(error)
    outcome_rate, error = _summary_rate(summary, "outcome_evaluated_rate", artifact_path=artifact_path, step=step)
    if error:
        errors.append(error)
    read_open_rate, error = _summary_rate(summary, "read_open_rate", artifact_path=artifact_path, step=step)
    if error:
        errors.append(error)
    if errors:
        return errors

    assert query_total is not None and evaluated_total is not None
    assert outcome_rate is not None and read_open_rate is not None
    if evaluated_total > query_total:
        errors.append(_operational_receipt_error(artifact_path, f"{step}: evaluated_total cannot exceed query_total"))
    if not _is_meaningful_receipt_value(summary.get("read_log_status", "")):
        errors.append(_operational_receipt_error(artifact_path, f"{step}: count_summary.read_log_status is required"))
    used_for_decision = _receipt_field_string(summary.get("used_for_decision", "")).lower()
    if used_for_decision not in {"true", "false"}:
        errors.append(_operational_receipt_error(artifact_path, f"{step}: count_summary.used_for_decision must be true or false"))
    accepted_no_op_reason = _receipt_field_string(summary.get("accepted_no_op_reason", ""))
    if used_for_decision == "false":
        if accepted_no_op_reason != "not_used_for_decision":
            errors.append(_operational_receipt_error(artifact_path, f"{step}: used_for_decision=false requires accepted_no_op_reason=not_used_for_decision"))
        return errors
    if accepted_no_op_reason == "not_used_for_decision":
        errors.append(_operational_receipt_error(artifact_path, f"{step}: accepted_no_op_reason=not_used_for_decision is invalid when used_for_decision=true"))

    low_coverage = query_total > 0 and (
        outcome_rate < RETRIEVAL_LOW_OUTCOME_RATE or read_open_rate < RETRIEVAL_LOW_READ_OPEN_RATE
    )
    if low_coverage:
        follow_up_ref = summary.get("follow_up_ref", "")
        if not _is_meaningful_receipt_value(follow_up_ref) and not _is_enum_like_reason(accepted_no_op_reason):
            errors.append(_operational_receipt_error(artifact_path, f"{step}: low coverage requires follow_up_ref or accepted_no_op_reason"))

    return errors


def _validate_docs_hygiene_suggest_summary(
    value: object,
    *,
    artifact_path: str,
    payload: dict[str, Any],
    artifact_git_state: str,
) -> list[dict[str, str]]:
    if not isinstance(value, dict):
        if (
            value is None
            and artifact_git_state == "clean"
            and _is_pre_enforcement_docs_hygiene_suggest_summary_receipt(payload)
        ):
            return []
        return [_operational_receipt_error(artifact_path, "docs_hygiene_suggest_summary must be an object")]

    errors: list[dict[str, str]] = []
    range_ref = _receipt_field_string(payload.get("range", ""))
    if _receipt_field_string(value.get("range", "")) != range_ref:
        errors.append(_operational_receipt_error(artifact_path, "docs_hygiene_suggest_summary.range must match receipt range"))

    steps = payload.get("steps")
    docs_hygiene_row = None
    if isinstance(steps, list):
        docs_hygiene_row = next(
            (row for row in steps if isinstance(row, dict) and row.get("step") == "docs_hygiene_suggest"),
            None,
        )
    row_command = _receipt_field_string(docs_hygiene_row.get("command", "")) if isinstance(docs_hygiene_row, dict) else ""
    row_stdout = _receipt_field_string(docs_hygiene_row.get("artifact_path", "")) if isinstance(docs_hygiene_row, dict) else ""

    canonical_command = _docs_hygiene_suggest_canonical_command(range_ref)
    command = _receipt_field_string(value.get("command", ""))
    gate_command = _receipt_field_string(value.get("gate_command", ""))
    if command != canonical_command:
        errors.append(_operational_receipt_error(artifact_path, "docs_hygiene_suggest_summary.command must equal canonical same-range planveyor_docs_hygiene_suggest --range"))
    if row_command == DOCS_HYGIENE_SUGGEST_GATE_COMMAND:
        if gate_command != DOCS_HYGIENE_SUGGEST_GATE_COMMAND:
            errors.append(_operational_receipt_error(artifact_path, "docs_hygiene_suggest_summary.gate_command must preserve wrapper row command"))
    elif row_command == canonical_command:
        if gate_command and gate_command != canonical_command:
            errors.append(_operational_receipt_error(artifact_path, "docs_hygiene_suggest_summary.gate_command must match canonical row command when present"))
    elif row_command:
        errors.append(_operational_receipt_error(artifact_path, "docs_hygiene_suggest: command must be exact wrapper gate or canonical same-range command"))
    if not _is_meaningful_receipt_value(_receipt_field_string(value.get("suggest_result", ""))):
        errors.append(_operational_receipt_error(artifact_path, "docs_hygiene_suggest_summary.suggest_result is required"))

    source_stdout_path = _receipt_field_string(value.get("source_stdout_path", ""))
    if not _is_meaningful_receipt_value(source_stdout_path):
        errors.append(_operational_receipt_error(artifact_path, "docs_hygiene_suggest_summary.source_stdout_path is required"))
    if row_stdout and source_stdout_path != row_stdout:
        errors.append(_operational_receipt_error(artifact_path, "docs_hygiene_suggest_summary.source_stdout_path must match docs_hygiene_suggest row artifact_path"))
    if not _receipt_field_string(value.get("source_stderr_path", "")):
        errors.append(_operational_receipt_error(artifact_path, "docs_hygiene_suggest_summary.source_stderr_path is required"))

    expected_false = {
        "deletion_executed": value.get("deletion_executed"),
        "ready_to_push_ticked_by_suggest_gate": value.get("ready_to_push_ticked_by_suggest_gate"),
    }
    if value.get("report_only") is not True:
        errors.append(_operational_receipt_error(artifact_path, "docs_hygiene_suggest_summary.report_only must be true"))
    for field, actual in expected_false.items():
        if actual is not False:
            errors.append(_operational_receipt_error(artifact_path, f"docs_hygiene_suggest_summary.{field} must be false"))

    if not _receipt_field_string(value.get("archive_required_command", "")):
        errors.append(_operational_receipt_error(artifact_path, "docs_hygiene_suggest_summary.archive_required_command is required"))
    rerun = _receipt_field_string(value.get("suggested_owner_rerun_command", ""))
    if rerun != canonical_command:
        errors.append(_operational_receipt_error(artifact_path, "docs_hygiene_suggest_summary.suggested_owner_rerun_command must equal canonical same-range planveyor_docs_hygiene_suggest --range"))

    counts = value.get("candidate_counts")
    if not isinstance(counts, dict):
        errors.append(_operational_receipt_error(artifact_path, "docs_hygiene_suggest_summary.candidate_counts must be an object"))
    else:
        missing = sorted(DOCS_HYGIENE_SUGGEST_CANDIDATE_COUNT_FIELDS - set(counts))
        if missing:
            errors.append(_operational_receipt_error(artifact_path, f"docs_hygiene_suggest_summary.candidate_counts missing field(s): {', '.join(missing)}"))
        for field in sorted(DOCS_HYGIENE_SUGGEST_CANDIDATE_COUNT_FIELDS & set(counts)):
            raw = counts.get(field)
            if not isinstance(raw, int) or isinstance(raw, bool) or raw < 0:
                errors.append(_operational_receipt_error(artifact_path, f"docs_hygiene_suggest_summary.candidate_counts.{field} must be a non-negative integer"))

    top_candidates = value.get("top_candidates")
    if not isinstance(top_candidates, list):
        errors.append(_operational_receipt_error(artifact_path, "docs_hygiene_suggest_summary.top_candidates must be a list"))
    elif len(top_candidates) > DOCS_HYGIENE_SUGGEST_TOP_CANDIDATES_LIMIT:
        errors.append(_operational_receipt_error(artifact_path, "docs_hygiene_suggest_summary.top_candidates exceeds cap"))
    else:
        for index, candidate in enumerate(top_candidates):
            if not isinstance(candidate, dict):
                errors.append(_operational_receipt_error(artifact_path, f"docs_hygiene_suggest_summary.top_candidates[{index}] must be an object"))
                continue
            path = _receipt_field_string(candidate.get("path", ""))
            candidate_class = _receipt_field_string(candidate.get("class", ""))
            reason = _receipt_field_string(candidate.get("reason", ""))
            path_obj = Path(path)
            if not _is_meaningful_receipt_value(path) or path_obj.is_absolute() or ".." in path_obj.parts:
                errors.append(_operational_receipt_error(artifact_path, f"docs_hygiene_suggest_summary.top_candidates[{index}].path must be repo-relative"))
            if not _is_meaningful_receipt_value(candidate_class):
                errors.append(_operational_receipt_error(artifact_path, f"docs_hygiene_suggest_summary.top_candidates[{index}].class is required"))
            if not _is_meaningful_receipt_value(reason):
                errors.append(_operational_receipt_error(artifact_path, f"docs_hygiene_suggest_summary.top_candidates[{index}].reason is required"))

    omitted_count = value.get("omitted_count")
    if not isinstance(omitted_count, int) or isinstance(omitted_count, bool) or omitted_count < 0:
        errors.append(_operational_receipt_error(artifact_path, "docs_hygiene_suggest_summary.omitted_count must be a non-negative integer"))

    return errors


def _validate_followups_triage_launch_row(row: dict[str, Any], *, artifact_path: str) -> list[dict[str, str]]:
    step = "followups_triage_launch"
    errors: list[dict[str, str]] = []
    in_scope = _receipt_field_string(row.get("in_scope", ""))
    command = _receipt_field_string(row.get("command", ""))
    if in_scope != "yes":
        errors.append(_operational_receipt_error(artifact_path, f"{step}: launch receipt row must be in_scope=yes"))
    if "followups_index_rebuild.py" not in command:
        errors.append(_operational_receipt_error(artifact_path, f"{step}: command must include scripts/followups_index_rebuild.py"))

    summary = _parse_count_summary(_receipt_field_string(row.get("count_summary", "")))
    missing = [field for field in FOLLOWUPS_TRIAGE_LAUNCH_REQUIRED_FIELDS if field not in summary]
    missing.extend(field for field in FOLLOWUPS_TRIAGE_LAUNCH_REQUIRED_INT_FIELDS if field not in summary)
    if missing:
        errors.append(_operational_receipt_error(artifact_path, f"{step}: count_summary missing field(s): {', '.join(missing)}"))
        return errors

    triage_mode = summary["triage_mode"].strip().lower()
    if triage_mode not in FOLLOWUPS_TRIAGE_LAUNCH_MODES:
        allowed = "|".join(sorted(FOLLOWUPS_TRIAGE_LAUNCH_MODES))
        errors.append(_operational_receipt_error(artifact_path, f"{step}: count_summary.triage_mode must be one of {allowed}"))
    else:
        if triage_mode == "range":
            missing = [field for field in FOLLOWUPS_TRIAGE_LAUNCH_RANGE_REQUIRED_INT_FIELDS if field not in summary]
            if missing:
                errors.append(_operational_receipt_error(artifact_path, f"{step}: count_summary missing field(s): {', '.join(missing)}"))
                return errors
        try:
            validate_followups_triage_command_surface(command, triage_mode=triage_mode)
        except ValueError as exc:
            errors.append(_operational_receipt_error(artifact_path, f"{step}: {exc}"))
    int_fields = FOLLOWUPS_TRIAGE_LAUNCH_REQUIRED_INT_FIELDS
    if triage_mode == "range":
        int_fields = int_fields + FOLLOWUPS_TRIAGE_LAUNCH_RANGE_REQUIRED_INT_FIELDS
    for field in int_fields:
        _, error = _summary_int(summary, field, artifact_path=artifact_path, step=step)
        if error:
            errors.append(error)
    if summary["index_rebuild_status"].strip().lower() != "ok":
        errors.append(_operational_receipt_error(artifact_path, f"{step}: count_summary.index_rebuild_status must be ok"))
    if summary["readback_status"].strip().lower() != "ok":
        errors.append(_operational_receipt_error(artifact_path, f"{step}: count_summary.readback_status must be ok"))
    if summary["process_improvements_lane"].strip().lower() != "separate":
        errors.append(_operational_receipt_error(artifact_path, f"{step}: count_summary.process_improvements_lane must be separate"))
    closure_refs = _followups_triage_launch_summary_closure_refs(summary)
    for field, value in closure_refs.items():
        if not _is_durable_followups_triage_ref(value):
            errors.append(_operational_receipt_error(artifact_path, f"{step}: count_summary.{field} must be a durable docs/*.md ref"))
    final_zero_fields = ("idempotency_append_new", "idempotency_possible_duplicate", "idempotency_route_fallback")
    if triage_mode == "range":
        final_zero_fields = final_zero_fields + ("idempotency_unparsed_bullets",)
    for field in final_zero_fields:
        raw, error = _summary_int(summary, field, artifact_path=artifact_path, step=step)
        if error:
            errors.append(error)
        elif raw is not None and raw > 0 and not closure_refs:
            errors.append(
                _operational_receipt_error(
                    artifact_path,
                    f"{step}: count_summary.{field} must be 0 at final proof unless manual_decision_ref or already_tracked_ref is set",
                )
            )
    if row.get("artifact_path") != summary["source_harvest_receipt_path"].strip():
        errors.append(_operational_receipt_error(artifact_path, f"{step}: artifact_path must match count_summary.source_harvest_receipt_path"))
    return errors


def _validate_followups_triage_launch_receipt(
    value: object,
    *,
    artifact_path: str,
    root: Path,
    payload: dict[str, Any],
    artifact_git_state: str,
    range_candidates: list[str],
) -> list[dict[str, str]]:
    if not isinstance(value, dict):
        if (
            value is None
            and artifact_git_state == "clean"
            and _is_pre_enforcement_followups_triage_launch_receipt(payload)
        ):
            return []
        return [_operational_receipt_error(artifact_path, "followups_triage_launch_receipt must be an object")]

    errors: list[dict[str, str]] = []
    source_path = _receipt_field_string(value.get("source_harvest_receipt_path", ""))
    if not _is_meaningful_receipt_value(source_path):
        errors.append(_operational_receipt_error(artifact_path, "followups_triage_launch_receipt.source_harvest_receipt_path is required"))
    else:
        path = Path(source_path)
        if path.is_absolute() or ".." in path.parts:
            errors.append(_operational_receipt_error(artifact_path, "followups_triage_launch_receipt.source_harvest_receipt_path must be repo-relative"))
        elif not (root / path).is_file():
            errors.append(_operational_receipt_error(artifact_path, f"followups_triage_launch_receipt source missing on disk: {source_path}"))
        else:
            source_text = _read_text(root / path)
            for token in (
                "## Follow-up harvest triage/import receipt",
                "planveyor_followups_triage",
                "followups_index_rebuild.py",
            ):
                if token not in source_text:
                    errors.append(_operational_receipt_error(artifact_path, f"followups_triage_launch_receipt source missing token: {token}"))

    triage_mode = _receipt_field_string(value.get("triage_mode", "")).lower()
    if triage_mode not in FOLLOWUPS_TRIAGE_LAUNCH_MODES:
        allowed = "|".join(sorted(FOLLOWUPS_TRIAGE_LAUNCH_MODES))
        errors.append(_operational_receipt_error(artifact_path, f"followups_triage_launch_receipt.triage_mode must be one of {allowed}"))
    command = _receipt_field_string(value.get("command", ""))
    expected_range = _receipt_field_string(payload.get("range", "")) if triage_mode == "range" else None
    if triage_mode in FOLLOWUPS_TRIAGE_LAUNCH_MODES:
        try:
            validate_followups_triage_command_surface(
                command,
                triage_mode=triage_mode,
                expected_range=expected_range,
            )
        except ValueError as exc:
            errors.append(_operational_receipt_error(artifact_path, f"followups_triage_launch_receipt: {exc}"))
    if "followups_index_rebuild.py" not in command:
        errors.append(_operational_receipt_error(artifact_path, "followups_triage_launch_receipt.command must include scripts/followups_index_rebuild.py"))
    if triage_mode == "file":
        obligations = _range_followups_obligation_paths(
            range_candidates,
            file_mode_targets=_followups_triage_file_targets_from_command(command),
        )
        if obligations:
            sample = ", ".join(obligations[:5])
            errors.append(
                _operational_receipt_error(
                    artifact_path,
                    "followups_triage_launch_receipt.triage_mode=file is insufficient while "
                    f"range followup inbox obligations exist: {sample}",
                )
            )

    for phase_name in ("dry_run", "apply", "idempotency_apply"):
        phase = value.get(phase_name)
        if not isinstance(phase, dict):
            errors.append(_operational_receipt_error(artifact_path, f"followups_triage_launch_receipt.{phase_name} must be an object"))
            continue
        phase_fields = ("append_new", "merge_source", "possible_duplicate", "route_fallback")
        if triage_mode == "range":
            phase_fields = phase_fields + ("unparsed_bullets",)
        for field in phase_fields:
            raw = phase.get(field)
            if not isinstance(raw, int) or isinstance(raw, bool) or raw < 0:
                errors.append(_operational_receipt_error(artifact_path, f"followups_triage_launch_receipt.{phase_name}.{field} must be a non-negative integer"))
    idempotency = value.get("idempotency_apply")
    if isinstance(idempotency, dict):
        closure_refs = _followups_triage_launch_receipt_closure_refs(value)
        for field, ref in closure_refs.items():
            if not _is_durable_followups_triage_ref(ref):
                errors.append(
                    _operational_receipt_error(
                        artifact_path,
                        f"followups_triage_launch_receipt.{field} must be a durable docs/*.md ref",
                    )
                )
        final_fields = ("append_new", "possible_duplicate", "route_fallback")
        if triage_mode == "range":
            final_fields = final_fields + ("unparsed_bullets",)
        for field in final_fields:
            raw = idempotency.get(field)
            if isinstance(raw, int) and not isinstance(raw, bool) and raw > 0 and not closure_refs:
                errors.append(
                    _operational_receipt_error(
                        artifact_path,
                        "followups_triage_launch_receipt.idempotency_apply."
                        f"{field} must be 0 at final proof unless manual_decision_ref or already_tracked_ref is set",
                    )
                )

    index_rebuild = value.get("index_rebuild")
    if not isinstance(index_rebuild, dict):
        errors.append(_operational_receipt_error(artifact_path, "followups_triage_launch_receipt.index_rebuild must be an object"))
    else:
        if _receipt_field_string(index_rebuild.get("status", "")).lower() != "ok":
            errors.append(_operational_receipt_error(artifact_path, "followups_triage_launch_receipt.index_rebuild.status must be ok"))
        if _receipt_field_string(index_rebuild.get("readback_status", "")).lower() != "ok":
            errors.append(_operational_receipt_error(artifact_path, "followups_triage_launch_receipt.index_rebuild.readback_status must be ok"))
        index_path = _receipt_field_string(index_rebuild.get("index_path", ""))
        if index_path != "docs/followups/index.md":
            errors.append(_operational_receipt_error(artifact_path, "followups_triage_launch_receipt.index_rebuild.index_path must be docs/followups/index.md"))

    lane = value.get("process_improvements_lane")
    if not isinstance(lane, dict):
        errors.append(_operational_receipt_error(artifact_path, "followups_triage_launch_receipt.process_improvements_lane must be an object"))
    elif _receipt_field_string(lane.get("status", "")).lower() != "separate":
        errors.append(_operational_receipt_error(artifact_path, "followups_triage_launch_receipt.process_improvements_lane.status must be separate"))
    return errors


def _reconciliation_int(
    value: dict[str, Any],
    field: str,
    *,
    artifact_path: str,
) -> tuple[int | None, list[dict[str, str]]]:
    raw = value.get(field)
    if not isinstance(raw, int) or isinstance(raw, bool) or raw < 0:
        return None, [
            _operational_receipt_error(
                artifact_path,
                f"followups_lane_reconciliation.{field} must be a non-negative integer",
            )
        ]
    return raw, []


def _validate_followups_lane_reconciliation(
    value: object,
    *,
    artifact_path: str,
    payload: dict[str, Any],
    artifact_git_state: str,
) -> list[dict[str, str]]:
    if not isinstance(value, dict):
        if (
            value is None
            and artifact_git_state == "clean"
            and _is_pre_enforcement_followups_lane_reconciliation(payload)
        ):
            return []
        return [_operational_receipt_error(artifact_path, "followups_lane_reconciliation must be an object")]

    errors: list[dict[str, str]] = []
    launch = payload.get("followups_triage_launch_receipt")
    if not isinstance(launch, dict):
        errors.append(
            _operational_receipt_error(
                artifact_path,
                "followups_lane_reconciliation requires followups_triage_launch_receipt",
            )
        )
        launch = {}

    required_strings = (
        "source_harvest_receipt_path",
        "harvest_file_followups_result",
        "range_triage_mode",
        "source_range_command",
        "owner_summary",
    )
    for field in required_strings:
        if not _is_meaningful_receipt_value(_receipt_field_string(value.get(field, ""))):
            errors.append(_operational_receipt_error(artifact_path, f"followups_lane_reconciliation.{field} is required"))

    source_path = _receipt_field_string(value.get("source_harvest_receipt_path", ""))
    launch_source = _receipt_field_string(launch.get("source_harvest_receipt_path", ""))
    if launch_source and source_path != launch_source:
        errors.append(
            _operational_receipt_error(
                artifact_path,
                "followups_lane_reconciliation.source_harvest_receipt_path must match followups_triage_launch_receipt",
            )
        )

    triage_mode = _receipt_field_string(value.get("range_triage_mode", "")).lower()
    launch_mode = _receipt_field_string(launch.get("triage_mode", "")).lower()
    if triage_mode not in FOLLOWUPS_TRIAGE_LAUNCH_MODES:
        allowed = "|".join(sorted(FOLLOWUPS_TRIAGE_LAUNCH_MODES))
        errors.append(_operational_receipt_error(artifact_path, f"followups_lane_reconciliation.range_triage_mode must be one of {allowed}"))
    elif launch_mode and triage_mode != launch_mode:
        errors.append(
            _operational_receipt_error(
                artifact_path,
                "followups_lane_reconciliation.range_triage_mode must match followups_triage_launch_receipt.triage_mode",
            )
        )

    command = _receipt_field_string(value.get("source_range_command", ""))
    launch_command = _receipt_field_string(launch.get("command", ""))
    if launch_command and command != launch_command:
        errors.append(
            _operational_receipt_error(
                artifact_path,
                "followups_lane_reconciliation.source_range_command must match followups_triage_launch_receipt.command",
            )
        )

    count_fields = (
        "harvest_file_followups_count",
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
    parsed_counts: dict[str, int] = {}
    for field in count_fields:
        parsed, field_errors = _reconciliation_int(value, field, artifact_path=artifact_path)
        errors.extend(field_errors)
        if parsed is not None:
            parsed_counts[field] = parsed

    apply_counts = launch.get("apply")
    if isinstance(apply_counts, dict):
        expected_pairs = {
            "range_append_new": "append_new",
            "range_merge_source": "merge_source",
            "range_possible_duplicate": "possible_duplicate",
            "range_route_fallback": "route_fallback",
        }
        if triage_mode == "range":
            expected_pairs["range_unparsed_bullets"] = "unparsed_bullets"
        for field, launch_field in expected_pairs.items():
            if field in parsed_counts and parsed_counts[field] != apply_counts.get(launch_field):
                errors.append(
                    _operational_receipt_error(
                        artifact_path,
                        f"followups_lane_reconciliation.{field} must match followups_triage_launch_receipt.apply.{launch_field}",
                    )
                )

    idempotency_counts = launch.get("idempotency_apply")
    if isinstance(idempotency_counts, dict):
        expected_pairs = {
            "range_unresolved_append_new": "append_new",
            "range_unresolved_possible_duplicate": "possible_duplicate",
            "range_unresolved_route_fallback": "route_fallback",
        }
        if triage_mode == "range":
            expected_pairs["range_unresolved_unparsed_bullets"] = "unparsed_bullets"
        for field, launch_field in expected_pairs.items():
            if field in parsed_counts and parsed_counts[field] != idempotency_counts.get(launch_field):
                errors.append(
                    _operational_receipt_error(
                        artifact_path,
                        f"followups_lane_reconciliation.{field} must match followups_triage_launch_receipt.idempotency_apply.{launch_field}",
                    )
                )

    closure_refs = {
        field: _receipt_field_string(value.get(field, ""))
        for field in FOLLOWUPS_TRIAGE_LAUNCH_CLOSURE_REF_FIELDS
        if _is_meaningful_receipt_value(_receipt_field_string(value.get(field, "")))
    }
    launch_closure_refs = _followups_triage_launch_receipt_closure_refs(launch) if isinstance(launch, dict) else {}
    for field in FOLLOWUPS_TRIAGE_LAUNCH_CLOSURE_REF_FIELDS:
        reconciliation_ref = closure_refs.get(field, "")
        launch_ref = launch_closure_refs.get(field, "")
        if reconciliation_ref and launch_ref and reconciliation_ref != launch_ref:
            errors.append(
                _operational_receipt_error(
                    artifact_path,
                    f"followups_lane_reconciliation.{field} must match followups_triage_launch_receipt.{field}",
                )
            )
        elif launch_ref and not reconciliation_ref:
            errors.append(
                _operational_receipt_error(
                    artifact_path,
                    f"followups_lane_reconciliation.{field} must preserve followups_triage_launch_receipt.{field}",
                )
            )
    for field, ref in closure_refs.items():
        if not _is_durable_followups_triage_ref(ref):
            errors.append(
                _operational_receipt_error(
                    artifact_path,
                    f"followups_lane_reconciliation.{field} must be a durable docs/*.md ref",
                )
            )
    unresolved_total = sum(
        parsed_counts.get(field, 0)
        for field in (
            "range_unresolved_append_new",
            "range_unresolved_possible_duplicate",
            "range_unresolved_route_fallback",
            "range_unresolved_unparsed_bullets",
        )
    )
    if unresolved_total > 0 and not closure_refs:
        errors.append(
            _operational_receipt_error(
                artifact_path,
                "followups_lane_reconciliation unresolved range counts require manual_decision_ref or already_tracked_ref",
            )
        )
    owner_summary = _receipt_field_string(value.get("owner_summary", ""))
    owner_summary_lower = owner_summary.lower()
    if "file-lane" not in owner_summary_lower:
        errors.append(
            _operational_receipt_error(
                artifact_path,
                "followups_lane_reconciliation.owner_summary must label the harvest result as file-lane",
            )
        )
    range_total = sum(
        parsed_counts.get(field, 0)
        for field in (
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
    )
    if range_total > 0 and "range-lane" not in owner_summary_lower:
        errors.append(
            _operational_receipt_error(
                artifact_path,
                "followups_lane_reconciliation.owner_summary must label non-zero range counts as range-lane",
            )
        )
    return errors


def _process_improvements_summary_count(
    counts: dict[str, Any],
    field: str,
    *,
    artifact_path: str,
) -> tuple[int | None, list[dict[str, str]]]:
    raw = counts.get(field)
    if not isinstance(raw, int) or isinstance(raw, bool) or raw < 0:
        return None, [
            _operational_receipt_error(
                artifact_path,
                f"process_improvements_open_summary.counts_by_raw_status.{field} must be a non-negative integer",
            )
        ]
    return raw, []


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


def _section_lines(source_text: str, heading: str) -> list[str]:
    lines = source_text.splitlines()
    out: list[str] = []
    in_section = False
    heading_norm = heading.casefold()
    for line in lines:
        stripped = line.strip()
        if stripped.casefold() == heading_norm:
            in_section = True
            continue
        if in_section and stripped.startswith("## "):
            break
        if in_section:
            out.append(line)
    return out


def _summary_int_value(value: Any) -> int | None:
    raw = _receipt_field_string(value).strip("`").rstrip(".,")
    if not raw:
        return None
    try:
        parsed = int(raw)
    except ValueError:
        return None
    if parsed < 0:
        return None
    return parsed


def _legacy_plan_harvest_followups_result(source_text: str) -> str:
    result_match = re.search(
        r"^\s*(?:[-*]\s*)?Result:\s*`?(?P<result>[^`\n]+?)`?(?:\s+-|\s*$)",
        source_text,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    if not result_match:
        return ""
    return result_match.group("result").strip()


def _followups_receipt_phase_from_text(value: str) -> str:
    lowered = value.casefold()
    if "idempotency" in lowered:
        return "idempotency"
    if "dry-run" in lowered or "dry run" in lowered:
        return "dry_run"
    if "apply" in lowered or "imported" in lowered:
        return "apply"
    if "rebuild" in lowered:
        return "rebuild"
    return ""


def _triage_mode_matches_receipt_line(value: str, expected_mode: str) -> bool:
    if expected_mode not in FOLLOWUPS_TRIAGE_LAUNCH_MODES:
        return True
    if expected_mode == "file" and "--range" in value:
        return False
    if expected_mode == "range" and "--file" in value:
        return False
    return True


def _plan_harvest_followups_receipt_counts(
    source_text: str,
    *,
    expected_triage_mode: str = "",
) -> dict[str, int]:
    counts: dict[str, int] = {}
    header: list[str] | None = None
    for line in _section_lines(source_text, FOLLOWUPS_HARVEST_TRIAGE_HEADING):
        cells = _markdown_table_cells(line)
        if cells:
            normalized = [_normalize_table_column(cell).replace("-", "_") for cell in cells]
            if {"append_new", "merge_source", "possible_duplicate", "route_fallback"} & set(normalized):
                header = normalized
                continue
            if header is None:
                continue
            row = {
                header[index]: _strip_markdown_cell(cell)
                for index, cell in enumerate(cells)
                if index < len(header)
            }
            row_text = " ".join(row.get(field, "") for field in ("mode", "command", "result"))
            if not _triage_mode_matches_receipt_line(row_text, expected_triage_mode):
                continue
            phase = _followups_receipt_phase_from_text(
                row_text
            )
            if not phase:
                continue
            for field in ("append_new", "merge_source", "possible_duplicate", "route_fallback", "unparsed_bullets"):
                parsed = _summary_int_value(row.get(field))
                if parsed is not None:
                    counts[f"{phase}_{field}"] = parsed
            continue

        if "planveyor_followups_triage" not in line:
            continue
        if not _triage_mode_matches_receipt_line(line, expected_triage_mode):
            continue
        phase = _followups_receipt_phase_from_text(line)
        if not phase:
            continue
        summary = _parse_count_summary(line)
        for field in ("append_new", "merge_source", "possible_duplicate", "route_fallback", "unparsed_bullets"):
            parsed = _summary_int_value(summary.get(field))
            if parsed is not None:
                counts[f"{phase}_{field}"] = parsed
    return counts


def _plan_harvest_process_improvements_summary(source_text: str) -> dict[str, str] | None:
    matches = [
        match
        for line in _process_improvement_decision_section_lines(source_text)
        if (match := re.search(
            rf"{re.escape(PROCESS_IMPROVEMENTS_OPEN_SUMMARY_FIELD)}\s*:\s*(?P<body>.+)$",
            line,
            flags=re.IGNORECASE,
        ))
    ]
    if len(matches) != 1:
        return None
    return _parse_semicolon_summary(matches[0].group("body"))


def _freshness_error(
    *,
    source_path: str,
    target_path: str,
    field: str,
    detail: str,
    code: str = "stale_receipt_copy",
) -> dict[str, str]:
    return {
        "code": code,
        "detail": f"field={field}; source={source_path}; target={target_path}; {detail}",
    }


def _active_artifacts_by_kind(artifacts: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [
        artifact
        for artifact in artifacts
        if artifact.get("kind") == kind
        and artifact.get("path")
        and artifact.get("active_candidate", True)
    ]


def _validate_operational_harvest_freshness(
    *,
    root: Path,
    artifacts: list[dict[str, Any]],
    operational_payload: dict[str, Any] | None,
) -> list[dict[str, str]]:
    if not operational_payload:
        return []
    operational_artifact = _operational_receipt_artifact(artifacts=artifacts)
    if not operational_artifact:
        return []
    target_path = _receipt_field_string(operational_artifact.get("path", ""))
    reconciliation = operational_payload.get("followups_lane_reconciliation")
    pi_summary = operational_payload.get("process_improvements_open_summary")
    if not isinstance(reconciliation, dict) and not isinstance(pi_summary, dict):
        return []

    current_harvests = _active_artifacts_by_kind(artifacts, "plan_harvest")
    compared_fields = []
    if isinstance(reconciliation, dict):
        compared_fields.append("followups_lane_reconciliation.source_harvest_receipt_path")
    if isinstance(pi_summary, dict):
        compared_fields.append("process_improvements_open_summary.source_harvest_receipt_path")
    if len(current_harvests) != 1:
        code = "missing_current_truth_host" if not current_harvests else "ambiguous_current_truth_host"
        source_path = "(none)" if not current_harvests else ", ".join(str(item.get("path")) for item in current_harvests)
        return [
            _freshness_error(
                source_path=source_path,
                target_path=target_path,
                field=field,
                detail="expected exactly one current same-range plan_harvest truth host",
                code=code,
            )
            for field in compared_fields
        ]

    source_path = _receipt_field_string(current_harvests[0].get("path", ""))
    source_text = _read_text(root / source_path)
    parsed_harvest = parse_plan_harvest_file_followups_receipt(source_text, rel_path=source_path)
    errors: list[dict[str, str]] = []

    if isinstance(reconciliation, dict):
        reconciliation_source = _receipt_field_string(reconciliation.get("source_harvest_receipt_path", ""))
        if reconciliation_source != source_path:
            errors.append(
                _freshness_error(
                    source_path=source_path,
                    target_path=target_path,
                    field="followups_lane_reconciliation.source_harvest_receipt_path",
                    detail=f"expected={source_path}; actual={reconciliation_source or 'missing'}",
                )
            )

        if parsed_harvest.schema_class == "current" and parsed_harvest.findings:
            for finding in parsed_harvest.findings:
                errors.append(
                    _freshness_error(
                        source_path=f"{source_path}#{FOLLOWUPS_HARVEST_TRIAGE_ANCHOR}",
                        target_path=target_path,
                        field="followups_lane_reconciliation.harvest_file_followups_result",
                        detail=f"current truth host is invalid: {finding.code}: {finding.message}",
                        code="invalid_current_truth_host",
                    )
                )
        elif parsed_harvest.schema_class == "unsupported":
            detail = "; ".join(f"{finding.code}: {finding.message}" for finding in parsed_harvest.findings)
            errors.append(
                _freshness_error(
                    source_path=f"{source_path}#{FOLLOWUPS_HARVEST_TRIAGE_ANCHOR}",
                    target_path=target_path,
                    field="followups_lane_reconciliation.harvest_file_followups_result",
                    detail=f"unsupported current truth host: {detail or parsed_harvest.schema_class}",
                    code="invalid_current_truth_host",
                )
            )
        else:
            source_result = (
                parsed_harvest.result
                if parsed_harvest.schema_class == "current"
                else _legacy_plan_harvest_followups_result(source_text)
            )
            if source_result:
                actual_result = _receipt_field_string(reconciliation.get("harvest_file_followups_result", ""))
                if actual_result != source_result:
                    errors.append(
                        _freshness_error(
                            source_path=f"{source_path}#{FOLLOWUPS_HARVEST_TRIAGE_ANCHOR}",
                            target_path=target_path,
                            field="followups_lane_reconciliation.harvest_file_followups_result",
                            detail=f"expected={source_result}; actual={actual_result or 'missing'}",
                        )
                    )
                if parsed_harvest.schema_class == "current":
                    expected_count = parsed_harvest.count
                else:
                    expected_count = 0 if source_result.upper() == "NO FOLLOWUPS" else None
                actual_count = _summary_int_value(reconciliation.get("harvest_file_followups_count"))
                if expected_count is not None and actual_count != expected_count:
                    errors.append(
                        _freshness_error(
                            source_path=f"{source_path}#{FOLLOWUPS_HARVEST_TRIAGE_ANCHOR}",
                            target_path=target_path,
                            field="followups_lane_reconciliation.harvest_file_followups_count",
                            detail=(
                                f"expected={expected_count}; "
                                f"actual={actual_count if actual_count is not None else 'missing'}"
                            ),
                        )
                    )

        source_counts = _plan_harvest_followups_receipt_counts(
            source_text,
            expected_triage_mode=_receipt_field_string(reconciliation.get("range_triage_mode", "")).lower(),
        )
        count_pairs = {
            "range_append_new": "apply_append_new",
            "range_merge_source": "apply_merge_source",
            "range_possible_duplicate": "apply_possible_duplicate",
            "range_route_fallback": "apply_route_fallback",
            "range_unparsed_bullets": "apply_unparsed_bullets",
            "range_unresolved_append_new": "idempotency_append_new",
            "range_unresolved_possible_duplicate": "idempotency_possible_duplicate",
            "range_unresolved_route_fallback": "idempotency_route_fallback",
            "range_unresolved_unparsed_bullets": "idempotency_unparsed_bullets",
        }
        for target_field, source_field in count_pairs.items():
            if source_field not in source_counts:
                continue
            actual = _summary_int_value(reconciliation.get(target_field))
            expected = source_counts[source_field]
            if actual != expected:
                errors.append(
                    _freshness_error(
                        source_path=f"{source_path}#{FOLLOWUPS_HARVEST_TRIAGE_ANCHOR}",
                        target_path=target_path,
                        field=f"followups_lane_reconciliation.{target_field}",
                        detail=f"expected={expected}; actual={actual if actual is not None else 'missing'}",
                    )
                )

    if isinstance(pi_summary, dict):
        pi_source = _receipt_field_string(pi_summary.get("source_harvest_receipt_path", ""))
        if pi_source != source_path:
            errors.append(
                _freshness_error(
                    source_path=source_path,
                    target_path=target_path,
                    field="process_improvements_open_summary.source_harvest_receipt_path",
                    detail=f"expected={source_path}; actual={pi_source or 'missing'}",
                )
            )
        decision_path = _receipt_field_string(pi_summary.get("decision_receipt_path", ""))
        expected_decision_path = f"{source_path}#{PROCESS_IMPROVEMENT_DECISIONS_ANCHOR}"
        if decision_path != expected_decision_path:
            errors.append(
                _freshness_error(
                    source_path=f"{source_path}#{PROCESS_IMPROVEMENT_DECISIONS_ANCHOR}",
                    target_path=target_path,
                    field="process_improvements_open_summary.decision_receipt_path",
                    detail=f"expected={expected_decision_path}; actual={decision_path or 'missing'}",
                )
            )

        source_summary = _plan_harvest_process_improvements_summary(source_text)
        if source_summary is None:
            counts = pi_summary.get("counts_by_raw_status")
            counts = counts if isinstance(counts, dict) else {}
            zero_summary = (
                not _visible_process_improvement_summary_rows(source_text)
                and all(_summary_int_value(counts.get(field)) == 0 for field in PROCESS_IMPROVEMENTS_OPEN_SUMMARY_STATUSES)
                and _summary_int_value(pi_summary.get("null_execution_rows")) == 0
            )
            if not zero_summary:
                errors.append(
                    _freshness_error(
                        source_path=f"{source_path}#{PROCESS_IMPROVEMENT_DECISIONS_ANCHOR}",
                        target_path=target_path,
                        field="process_improvements_open_summary",
                        detail="expected exactly one process_improvements_open_summary source line",
                        code="missing_current_truth_host",
                    )
                )
        else:
            string_pairs = {
                "ordinary_followups_result": "ordinary_followups",
                "lane_status": "lane",
                "owner_or_next_step": "owner_or_next_step",
            }
            for target_field, source_field in string_pairs.items():
                expected = _receipt_field_string(source_summary.get(source_field, ""))
                actual = _receipt_field_string(pi_summary.get(target_field, ""))
                if expected and actual != expected:
                    errors.append(
                        _freshness_error(
                            source_path=f"{source_path}#{PROCESS_IMPROVEMENT_DECISIONS_ANCHOR}",
                            target_path=target_path,
                            field=f"process_improvements_open_summary.{target_field}",
                            detail=f"expected={expected}; actual={actual or 'missing'}",
                        )
                    )
            counts = pi_summary.get("counts_by_raw_status")
            counts = counts if isinstance(counts, dict) else {}
            for field in PROCESS_IMPROVEMENTS_OPEN_SUMMARY_STATUSES:
                expected = _summary_int_value(source_summary.get(field))
                actual = _summary_int_value(counts.get(field))
                if expected is not None and actual != expected:
                    errors.append(
                        _freshness_error(
                            source_path=f"{source_path}#{PROCESS_IMPROVEMENT_DECISIONS_ANCHOR}",
                            target_path=target_path,
                            field=f"process_improvements_open_summary.counts_by_raw_status.{field}",
                            detail=f"expected={expected}; actual={actual if actual is not None else 'missing'}",
                        )
                    )
            expected_null = _summary_int_value(source_summary.get("null_execution"))
            actual_null = _summary_int_value(pi_summary.get("null_execution_rows"))
            if expected_null is not None and actual_null != expected_null:
                errors.append(
                    _freshness_error(
                        source_path=f"{source_path}#{PROCESS_IMPROVEMENT_DECISIONS_ANCHOR}",
                        target_path=target_path,
                        field="process_improvements_open_summary.null_execution_rows",
                        detail=f"expected={expected_null}; actual={actual_null if actual_null is not None else 'missing'}",
                    )
                )
    return errors


def _validate_packetization_report_freshness(
    *,
    root: Path,
    active_report: str,
    range_ref: str,
    mirror_policy: MirrorPolicy = GENERIC_MIRROR_POLICY,
) -> list[dict[str, str]]:
    payload = _packetization_report_payload(root, active_report)
    if not payload:
        return []
    source_path = active_report
    target_path = "merge_bundle_report.packetization_gate"
    errors: list[dict[str, str]] = []

    report_path = _receipt_field_string(payload.get("report_path", ""))
    if report_path and report_path != active_report:
        errors.append(
            _freshness_error(
                source_path=source_path,
                target_path=target_path,
                field="packetization_gate.active_packetization_report",
                detail=f"expected={active_report}; actual={report_path}",
            )
        )

    try:
        resolved_range = (
            resolve_recovery_lineage(
                root,
                range_ref=range_ref,
                mirror_policy=mirror_policy,
            ).range_ref
            if range_ref
            else ""
        )
    except (OSError, RuntimeError, ValueError) as exc:
        return [
            _freshness_error(
                source_path=source_path,
                target_path=target_path,
                field="packetization_gate.range",
                detail=f"could not resolve expected exact range: {exc}",
            )
        ]
    payload_range = _receipt_field_string(payload.get("range", ""))
    if payload_range and resolved_range and payload_range != resolved_range:
        errors.append(
            _freshness_error(
                source_path=source_path,
                target_path=target_path,
                field="packetization_gate.range",
                detail=f"expected={resolved_range}; actual={payload_range}",
            )
        )

    raw_rows = payload.get("rows")
    rows = _packetization_rows(raw_rows)
    if not isinstance(raw_rows, list) or len(rows) != len(raw_rows):
        errors.append(
            _freshness_error(
                source_path=source_path,
                target_path=target_path,
                field="packetization_gate.rows",
                detail="expected a list of row objects",
            )
        )
    else:
        row_bits = [_packetization_row_is_blocking(row) for row in rows]
        if any(bit is None for bit in row_bits):
            errors.append(
                _freshness_error(
                    source_path=source_path,
                    target_path=target_path,
                    field="packetization_gate.rows.blocking",
                    detail="explicit blocking fields must be booleans",
                )
            )
        expected_blocking = sum(1 for bit in row_bits if bit is True)
        for field in ("blocking_rows_count", "blocking_count"):
            actual = _summary_int_value(payload.get(field))
            if actual is not None and actual != expected_blocking:
                errors.append(
                    _freshness_error(
                        source_path=source_path,
                        target_path=target_path,
                        field=f"packetization_gate.{field}",
                        detail=f"expected={expected_blocking}; actual={actual}",
                    )
                )
        expected_coverage_counts: dict[str, int] = {}
        for row in rows:
            coverage = _receipt_field_string(row.get("coverage", ""))
            if coverage:
                expected_coverage_counts[coverage] = expected_coverage_counts.get(coverage, 0) + 1
        if "blocking_coverage_counts" in payload:
            declared_counts = payload.get("blocking_coverage_counts")
            normalized_declared: dict[str, int] = {}
            invalid_counts: list[str] = []
            if not isinstance(declared_counts, dict):
                invalid_counts.append("map is not an object")
            else:
                for coverage, raw_count in declared_counts.items():
                    if (
                        not isinstance(coverage, str)
                        or not coverage.strip()
                        or isinstance(raw_count, bool)
                        or not isinstance(raw_count, int)
                        or raw_count < 0
                    ):
                        invalid_counts.append(f"{coverage!r}={raw_count!r}")
                        continue
                    normalized_declared[coverage.strip()] = raw_count
            if invalid_counts:
                errors.append(
                    _freshness_error(
                        source_path=source_path,
                        target_path=target_path,
                        field="packetization_gate.blocking_coverage_counts",
                        detail=f"invalid structural counts: {', '.join(invalid_counts)}",
                    )
                )
            else:
                for coverage in normalized_declared:
                    expected_coverage_counts.setdefault(coverage, 0)
                if normalized_declared != expected_coverage_counts:
                    errors.append(
                        _freshness_error(
                            source_path=source_path,
                            target_path=target_path,
                            field="packetization_gate.blocking_coverage_counts",
                            detail=f"expected={expected_coverage_counts}; actual={normalized_declared}",
                        )
                    )

    created_paths = _path_list(payload.get("draft_packets_created_paths")) or _path_list(
        payload.get("created_packets")
    )
    created_count = _summary_int_value(payload.get("draft_packets_created_count"))
    if created_count is not None and created_count != len(created_paths):
        errors.append(
            _freshness_error(
                source_path=source_path,
                target_path=target_path,
                field="packetization_gate.draft_packets_created_count",
                detail=f"expected={len(created_paths)}; actual={created_count}",
            )
        )
    return errors


def _packetization_current_delivery_error(active_report: str, detail: str) -> dict[str, str]:
    return {
        "code": "inconsistent_packetization_packet",
        "detail": f"{active_report} report_accepted_packet_paths: {detail}",
    }


def _packetization_string_list(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return ()
    return tuple(value)


def _packetization_literal_string(value: object) -> str:
    return value if isinstance(value, str) else ""


def _packetization_row_key(row: dict[str, Any]) -> tuple[str, str, str, tuple[str, ...], str]:
    return (
        _packetization_literal_string(row.get("changed_file")),
        _packetization_literal_string(row.get("target_repo")),
        _packetization_literal_string(row.get("target_kind")),
        _packetization_string_list(row.get("target_writable_carriers")),
        _packetization_literal_string(row.get("authority")),
    )


def _packetization_target_row_label(
    row: tuple[str, str, str, tuple[str, ...], str],
) -> str:
    changed_file, target_repo, target_kind, carriers, authority = row
    return f"{changed_file}@{target_repo}/{target_kind}[{','.join(carriers) or '-'}]#{authority}"


def _compact_packetization_carrier_summary(carriers: tuple[str, ...]) -> str:
    """Return a bounded carrier description for unclaimed aggregate diagnostics."""

    ordered_carriers = tuple(sorted(carriers))
    sample = ordered_carriers[:PACKETIZATION_UNCLAIMED_DIAGNOSTIC_SAMPLE_LIMIT]
    summary = f"carrier_count={len(ordered_carriers)} carrier_sample={','.join(sample) or '-'}"
    omitted = len(ordered_carriers) - len(sample)
    if omitted:
        summary += f" carrier_omitted={omitted}"
    return summary


def _compact_packetization_target_row_label(
    row: tuple[str, str, str, tuple[str, ...], str],
) -> str:
    changed_file, target_repo, target_kind, carriers, authority = row
    return (
        f"{changed_file}@{target_repo}/{target_kind}"
        f"[{_compact_packetization_carrier_summary(carriers)}]#{authority}"
    )


def _render_packetization_target_rows(
    rows: set[tuple[str, str, str, tuple[str, ...], str]],
) -> str:
    return ", ".join(_packetization_target_row_label(row) for row in sorted(rows))


def _packetization_row_is_unclaimed_empty_acceptance(row: dict[str, Any]) -> bool:
    coverage = _receipt_field_string(row.get("coverage", ""))
    blocking = _packetization_row_is_blocking(row)
    return (
        _receipt_field_string(row.get("packet_path", "")) == "N/A"
        and (
            (coverage == "missing-packet" and blocking is True)
            or (coverage == "source_only" and blocking is False)
        )
    )


def _compact_unclaimed_packetization_detail(category: str, labels: list[str]) -> str:
    ordered_labels = sorted(labels)
    sample = ordered_labels[:PACKETIZATION_UNCLAIMED_DIAGNOSTIC_SAMPLE_LIMIT]
    detail = (
        "unclaimed_empty_accepted "
        f"category={category} count={len(ordered_labels)} sample={'; '.join(sample) or '-'}"
    )
    omitted = len(ordered_labels) - len(sample)
    if omitted:
        detail += f" omitted={omitted}"
    return detail


def _validate_packetization_current_delivery(
    *,
    root: Path,
    active_report: str,
    range_ref: str,
    mirror_policy: MirrorPolicy = GENERIC_MIRROR_POLICY,
) -> list[dict[str, str]]:
    """Reopen claimed current packets instead of trusting the report's derived green summary."""

    payload = _packetization_report_payload(root, active_report)
    if "report_accepted_packet_paths" not in payload:
        # Older active reports remain readable; only reports that claim the new receipt field opt into this proof.
        return []

    errors: list[dict[str, str]] = []
    raw_paths = payload.get("report_accepted_packet_paths")
    if not isinstance(raw_paths, list) or not all(isinstance(path, str) for path in raw_paths):
        return [_packetization_current_delivery_error(active_report, "must be a sorted list of packet paths")]
    paths = [str(path) for path in raw_paths]
    if paths != sorted(paths):
        errors.append(_packetization_current_delivery_error(active_report, "must be sorted"))
    if len(paths) != len(set(paths)):
        errors.append(_packetization_current_delivery_error(active_report, "must not contain duplicates"))

    try:
        lineage = resolve_recovery_lineage(
            root,
            range_ref=range_ref,
            mirror_policy=mirror_policy,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        errors.append(_packetization_current_delivery_error(active_report, f"source lineage is not current: {exc}"))
        return errors

    payload_range = _receipt_field_string(payload.get("range", ""))
    if payload_range != lineage.range_ref:
        errors.append(
            _packetization_current_delivery_error(
                active_report,
                f"range={payload_range or 'missing'}; expected={lineage.range_ref}",
            )
        )
    if _receipt_field_string(payload.get("source_range", "")) != lineage.range_ref:
        errors.append(
            _packetization_current_delivery_error(
                active_report,
                f"source_range must equal {lineage.range_ref}",
            )
        )
    if _receipt_field_string(payload.get("source_revision", "")) != lineage.head:
        errors.append(
            _packetization_current_delivery_error(
                active_report,
                f"source_revision must equal {lineage.head}",
            )
        )
    applicability = lineage.applicability
    source_artifacts = payload.get("source_artifacts")
    if source_artifacts != list(applicability.report_context_paths):
        errors.append(
            _packetization_current_delivery_error(
                active_report,
                "source_artifacts must equal the resolved report-context source artifact set",
            )
        )

    if payload.get("packetization_report_required") is not applicability.packetization_report_required:
        errors.append(
            _packetization_current_delivery_error(
                active_report,
                "packetization_report_required must equal the resolved applicability result",
            )
        )
    if payload.get("target_packet_required") is not applicability.target_packet_required:
        errors.append(
            _packetization_current_delivery_error(
                active_report,
                "target_packet_required must equal the resolved applicability result",
            )
        )
    if payload.get("target_partitions") != [partition.to_json() for partition in applicability.partitions]:
        errors.append(
            _packetization_current_delivery_error(
                active_report,
                "target_partitions must exactly equal the resolved partition set",
            )
        )

    raw_rows = payload.get("rows")
    rows = _packetization_rows(raw_rows)
    compact_unclaimed_rows = (
        not paths
        and isinstance(raw_rows, list)
        and len(rows) == len(raw_rows)
        and bool(rows)
        and all(_packetization_row_is_unclaimed_empty_acceptance(row) for row in rows)
    )
    compact_diagnostics: dict[str, list[str]] = {}

    def add_structural_delivery_error(
        category: str,
        detail: str,
        labels: list[str],
    ) -> None:
        if compact_unclaimed_rows:
            compact_diagnostics.setdefault(category, []).extend(labels)
            return
        errors.append(_packetization_current_delivery_error(active_report, detail))

    def structural_target_row_label(
        row: tuple[str, str, str, tuple[str, ...], str],
    ) -> str:
        if compact_unclaimed_rows:
            return _compact_packetization_target_row_label(row)
        return _packetization_target_row_label(row)

    def structural_target_rows_detail(
        prefix: str,
        target_rows: set[tuple[str, str, str, tuple[str, ...], str]],
    ) -> str:
        if compact_unclaimed_rows:
            return prefix
        return prefix + _render_packetization_target_rows(target_rows)

    expected_target_rows: set[tuple[str, str, str, tuple[str, ...], str]] = set()
    for record in applicability.records:
        if record.ignored_reason:
            continue
        carriers = tuple(sorted(record.target_writable_carriers))
        if (
            record.target_repo
            and record.target_kind
            and not record.source_only_reason
            and not record.blocking_reason
        ):
            partition = applicability.partition_for(
                target_repo=record.target_repo,
                target_kind=record.target_kind,
            )
            if partition is not None:
                carriers = tuple(partition.target_writable_carriers)
        expected_target_rows.add(
            (
                record.changed_file,
                record.target_repo or "",
                record.target_kind or "",
                carriers,
                record.authority,
            )
        )
    actual_target_rows = [_packetization_row_key(row) for row in rows]
    actual_target_row_set = set(actual_target_rows)
    duplicate_target_rows = {
        row for row in actual_target_row_set if actual_target_rows.count(row) > 1
    }
    missing_target_rows = expected_target_rows - actual_target_row_set
    extra_target_rows = actual_target_row_set - expected_target_rows
    if missing_target_rows:
        add_structural_delivery_error(
            "missing_expected_target_rows",
            structural_target_rows_detail("missing expected target rows: ", missing_target_rows),
            [structural_target_row_label(row) for row in sorted(missing_target_rows)],
        )
    if extra_target_rows:
        add_structural_delivery_error(
            "unexpected_target_rows",
            structural_target_rows_detail("unexpected target rows: ", extra_target_rows),
            [structural_target_row_label(row) for row in sorted(extra_target_rows)],
        )
    if duplicate_target_rows:
        add_structural_delivery_error(
            "duplicate_target_rows",
            structural_target_rows_detail("duplicate target rows: ", duplicate_target_rows),
            [structural_target_row_label(row) for row in sorted(duplicate_target_rows)],
        )

    rows_by_target: dict[tuple[str, str, str, tuple[str, ...], str], list[dict[str, Any]]] = {}
    for row, target_row in zip(rows, actual_target_rows):
        rows_by_target.setdefault(target_row, []).append(row)
    partition_rows: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for partition in applicability.partitions:
        partition_key = partition.key
        partition_records = [
            record
            for record in applicability.records
            if (
                record.target_repo,
                record.target_kind,
            )
            == partition_key
            and not record.source_only_reason
            and not record.blocking_reason
        ]
        for record in partition_records:
            row_key = (
                record.changed_file,
                partition.target_repo,
                partition.target_kind,
                tuple(partition.target_writable_carriers),
                record.authority,
            )
            partition_rows.setdefault(partition_key, []).extend(rows_by_target.get(row_key, []))

    packet_bindings: dict[str, set[tuple[str, str]]] = {}
    for partition in applicability.partitions:
        partition_key = partition.key
        bound_rows = partition_rows.get(partition_key, [])
        if compact_unclaimed_rows:
            label = (
                f"{partition.target_repo}/{partition.target_kind}"
                f"[{_compact_packetization_carrier_summary(partition.target_writable_carriers)}]"
            )
        else:
            label = f"{partition.target_repo}/{partition.target_kind}[{','.join(partition.target_writable_carriers)}]"
        expected_sources = list(partition.target_source_artifacts)
        packet_refs: set[str] = set()
        for row in bound_rows:
            row_label = structural_target_row_label(_packetization_row_key(row))
            if row.get("target_source_artifacts") != expected_sources:
                add_structural_delivery_error(
                    "target_source_artifacts_mismatch",
                    f"target partition {label} row target_source_artifacts must exactly equal its partition set",
                    [row_label],
                )
            if row.get("target_writable_carriers") != list(partition.target_writable_carriers):
                add_structural_delivery_error(
                    "target_writable_carriers_mismatch",
                    f"target partition {label} row target_writable_carriers must exactly equal its partition set",
                    [row_label],
                )
            if _receipt_field_string(row.get("authority", "")) not in partition.record_authorities:
                add_structural_delivery_error(
                    "row_authority_mismatch",
                    f"target partition {label} row authority must name one resolved record authority",
                    [row_label],
                )
            coverage = _receipt_field_string(row.get("coverage", ""))
            if coverage != "covered" or _packetization_row_is_blocking(row) is not False:
                add_structural_delivery_error(
                    "uncovered_or_blocking_target_rows",
                    f"target partition {label} must be covered and non-blocking",
                    [row_label],
                )
            packet_ref = _receipt_field_string(row.get("packet_path", ""))
            if not packet_ref or packet_ref == "N/A":
                add_structural_delivery_error(
                    "target_rows_without_accepted_packet",
                    f"target partition {label} must name one accepted packet",
                    [row_label],
                )
                continue
            packet_refs.add(packet_ref)
        if len(packet_refs) != 1:
            add_structural_delivery_error(
                "target_partitions_without_single_packet",
                f"target partition {label} must bind exactly one packet; found {', '.join(sorted(packet_refs)) or 'none'}",
                [label],
            )
            continue
        packet_ref = next(iter(packet_refs))
        if packet_ref not in paths:
            errors.append(
                _packetization_current_delivery_error(
                    active_report,
                    f"target partition {label} packet {packet_ref} is not report-accepted",
                )
            )
            continue
        packet_bindings.setdefault(packet_ref, set()).add(partition_key)
        try:
            packet_path = _resolve_current_delivery_packet_path(root, packet_ref)
            _, findings = _validate_current_delivery_packet(
                packet_path,
                root,
                source_range=lineage.range_ref,
                source_revision=lineage.head,
                source_artifacts=expected_sources,
                expected_target_repo=partition.target_repo,
                expected_target_kind=partition.target_kind,
                expected_target_writable_carriers=list(partition.target_writable_carriers),
                require_tracked=True,
            )
        except (OSError, ValueError) as exc:
            errors.append(_packetization_current_delivery_error(active_report, f"{packet_ref}: {exc}"))
            continue
        finding_messages = [
            str(finding.get("message") or "invalid packet")
            for finding in findings
            if finding.get("severity") == "error"
        ]
        if finding_messages:
            errors.append(
                _packetization_current_delivery_error(
                    active_report,
                    f"{packet_ref}: {'; '.join(finding_messages)}",
                )
            )

    if compact_diagnostics:
        for category, labels in sorted(compact_diagnostics.items()):
            errors.append(
                _packetization_current_delivery_error(
                    active_report,
                    _compact_unclaimed_packetization_detail(category, labels),
                )
            )
        recovery_command = _receipt_field_string(payload.get("recovery_command", ""))
        errors.append(
            _packetization_current_delivery_error(
                active_report,
                "unclaimed_empty_accepted recovery_action="
                + (recovery_command or "rerun packetization recovery for the current exact range"),
            )
        )

    for packet_ref, bound_partitions in sorted(packet_bindings.items()):
        if len(bound_partitions) > 1:
            errors.append(
                _packetization_current_delivery_error(
                    active_report,
                    f"accepted packet {packet_ref} is reused across target partitions",
                )
            )
    unused_accepted_paths = sorted(set(paths) - set(packet_bindings))
    if unused_accepted_paths:
        errors.append(
            _packetization_current_delivery_error(
                active_report,
                "report-accepted packets are not bound to a resolved target partition: "
                + ", ".join(unused_accepted_paths),
            )
        )

    covered_paths = sorted(
        {
            _receipt_field_string(row.get("packet_path", ""))
            for row in rows
            if _receipt_field_string(row.get("coverage", "")) == "covered"
            and _receipt_field_string(row.get("packet_path", ""))
        }
    )
    missing_from_acceptance = sorted(set(covered_paths) - set(paths))
    if missing_from_acceptance:
        errors.append(
            _packetization_current_delivery_error(
                active_report,
                "covered packet paths missing from report_accepted_packet_paths: " + ", ".join(missing_from_acceptance),
            )
        )
    return errors


def _validate_process_improvements_open_summary(
    value: object,
    *,
    artifact_path: str,
    root: Path,
    payload: dict[str, Any],
    artifact_git_state: str,
) -> list[dict[str, str]]:
    if not isinstance(value, dict):
        if (
            value is None
            and artifact_git_state == "clean"
            and _is_pre_enforcement_process_improvements_open_summary(payload)
        ):
            return []
        return [_operational_receipt_error(artifact_path, "process_improvements_open_summary must be an object")]

    errors: list[dict[str, str]] = []
    followups_receipt = payload.get("followups_triage_launch_receipt")
    expected_source = ""
    if isinstance(followups_receipt, dict):
        expected_source = _receipt_field_string(followups_receipt.get("source_harvest_receipt_path", ""))

    source_path = _receipt_field_string(value.get("source_harvest_receipt_path", ""))
    source_text: str | None = None
    if not _is_meaningful_receipt_value(source_path):
        errors.append(_operational_receipt_error(artifact_path, "process_improvements_open_summary.source_harvest_receipt_path is required"))
    else:
        path = Path(source_path)
        if path.is_absolute() or ".." in path.parts:
            errors.append(_operational_receipt_error(artifact_path, "process_improvements_open_summary.source_harvest_receipt_path must be repo-relative"))
        elif not (root / path).is_file():
            errors.append(_operational_receipt_error(artifact_path, f"process_improvements_open_summary source missing on disk: {source_path}"))
        else:
            source_text = _read_text(root / path)
    if expected_source and source_path != expected_source:
        errors.append(_operational_receipt_error(artifact_path, "process_improvements_open_summary.source_harvest_receipt_path must match followups_triage_launch_receipt source"))

    expected_decision_path = f"{source_path}#process-improvement-promotion-decisions" if source_path else ""
    decision_path = _receipt_field_string(value.get("decision_receipt_path", ""))
    if decision_path != expected_decision_path:
        errors.append(_operational_receipt_error(artifact_path, "process_improvements_open_summary.decision_receipt_path must point to source harvest PI decision anchor"))
    if _receipt_field_string(value.get("ordinary_followups_result", "")).upper() != "NO FOLLOWUPS":
        errors.append(_operational_receipt_error(artifact_path, "process_improvements_open_summary.ordinary_followups_result must be NO FOLLOWUPS"))
    if _receipt_field_string(value.get("lane_status", "")).lower() != "separate":
        errors.append(_operational_receipt_error(artifact_path, "process_improvements_open_summary.lane_status must be separate"))

    counts = value.get("counts_by_raw_status")
    parsed_counts: dict[str, int] = {}
    if not isinstance(counts, dict):
        errors.append(_operational_receipt_error(artifact_path, "process_improvements_open_summary.counts_by_raw_status must be an object"))
    else:
        missing = [field for field in ("open", "triaged", "promoted") if field not in counts]
        if missing:
            errors.append(_operational_receipt_error(artifact_path, f"process_improvements_open_summary.counts_by_raw_status missing field(s): {', '.join(missing)}"))
        for field in ("open", "triaged", "promoted"):
            if field not in counts:
                continue
            value_int, count_errors = _process_improvements_summary_count(
                counts,
                field,
                artifact_path=artifact_path,
            )
            errors.extend(count_errors)
            if value_int is not None:
                parsed_counts[field] = value_int

    null_execution = value.get("null_execution_rows")
    parsed_null_execution: int | None = None
    if not isinstance(null_execution, int) or isinstance(null_execution, bool) or null_execution < 0:
        errors.append(_operational_receipt_error(artifact_path, "process_improvements_open_summary.null_execution_rows must be a non-negative integer"))
    else:
        parsed_null_execution = null_execution
        if len(parsed_counts) == 3 and null_execution > sum(parsed_counts.values()):
            errors.append(_operational_receipt_error(artifact_path, "process_improvements_open_summary.null_execution_rows cannot exceed open+triaged+promoted"))

    if source_text is not None and PROCESS_IMPROVEMENTS_OPEN_SUMMARY_FIELD not in source_text:
        no_open_summary = (
            len(parsed_counts) == 3
            and sum(parsed_counts.values()) == 0
            and parsed_null_execution == 0
            and PROCESS_IMPROVEMENT_DECISIONS_HEADING in source_text
            and not _visible_process_improvement_summary_rows(source_text)
        )
        if not no_open_summary:
            errors.append(_operational_receipt_error(artifact_path, "process_improvements_open_summary source missing summary line"))

    if not _is_meaningful_receipt_value(_receipt_field_string(value.get("owner_or_next_step", ""))):
        errors.append(_operational_receipt_error(artifact_path, "process_improvements_open_summary.owner_or_next_step is required"))
    return errors


def _operational_step_record(payload: dict[str, Any], step: str) -> dict[str, Any] | None:
    steps = payload.get("steps")
    if not isinstance(steps, list):
        return None
    for item in steps:
        if isinstance(item, dict) and _receipt_field_string(item.get("step", "")) == step:
            return item
    return None


def _normalized_archive_sha(value: str) -> str:
    lowered = value.lower()
    if lowered.startswith("sha256:"):
        return lowered.split(":", 1)[1]
    return lowered


def _validate_git_text_archive_snapshot_manifest(
    *,
    root: Path,
    artifact_path: str,
    manifest_path: str,
    artifact_path_field: str,
    checksum: str,
    storage_backend: str,
    format_version: str,
    snapshot_created_at_utc: str,
    snapshot_source_db_sha256: str,
    snapshot_source_docs_count: int | None,
) -> list[dict[str, str]]:
    manifest_file = root / manifest_path
    try:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [
            _operational_receipt_error(
                artifact_path,
                f"archive_snapshot manifest must be parseable JSON: {manifest_path}: {exc}",
            )
        ]
    if not isinstance(manifest, dict):
        return [_operational_receipt_error(artifact_path, "archive_snapshot manifest must be a JSON object")]

    errors: list[dict[str, str]] = []
    manifest_backend = _receipt_field_string(manifest.get("storage_backend", ""))
    if manifest_backend != storage_backend:
        errors.append(
            _operational_receipt_error(
                artifact_path,
                f"archive_snapshot.storage_backend={storage_backend}; manifest storage_backend={manifest_backend or 'missing'}",
            )
        )
    manifest_format = _receipt_field_string(manifest.get("snapshot_manifest_version", ""))
    if manifest_format != format_version:
        errors.append(
            _operational_receipt_error(
                artifact_path,
                f"archive_snapshot.format_version={format_version}; manifest snapshot_manifest_version={manifest_format or 'missing'}",
            )
        )
    manifest_created = _receipt_field_string(manifest.get("created_at_utc", ""))
    if manifest_created != snapshot_created_at_utc:
        errors.append(
            _operational_receipt_error(
                artifact_path,
                "archive_snapshot.snapshot_created_at_utc must match manifest.created_at_utc",
            )
        )

    artifact_obj = manifest.get("artifact")
    if not isinstance(artifact_obj, dict):
        errors.append(_operational_receipt_error(artifact_path, "archive_snapshot manifest artifact must be an object"))
    else:
        manifest_artifact_path = _receipt_field_string(artifact_obj.get("path", ""))
        expected_artifact_rel = (Path(manifest_path).parent / manifest_artifact_path).as_posix() if manifest_artifact_path else ""
        if expected_artifact_rel and expected_artifact_rel != artifact_path_field:
            errors.append(
                _operational_receipt_error(
                    artifact_path,
                    f"archive_snapshot.artifact_path={artifact_path_field}; manifest artifact path resolves to {expected_artifact_rel}",
                )
            )
        manifest_checksum = _receipt_field_string(artifact_obj.get("sha256", ""))
        if _normalized_archive_sha(manifest_checksum) != _normalized_archive_sha(checksum):
            errors.append(
                _operational_receipt_error(
                    artifact_path,
                    "archive_snapshot.checksum must match manifest artifact.sha256",
                )
            )

    source_db = manifest.get("source_db")
    if not isinstance(source_db, dict):
        errors.append(_operational_receipt_error(artifact_path, "archive_snapshot manifest source_db must be an object"))
    else:
        manifest_db_sha = _receipt_field_string(source_db.get("db_sha256", "")).lower()
        if _normalized_archive_sha(manifest_db_sha) != _normalized_archive_sha(snapshot_source_db_sha256):
            errors.append(
                _operational_receipt_error(
                    artifact_path,
                    "archive_snapshot.snapshot_source_db_sha256 must match manifest source_db.db_sha256",
                )
            )
        manifest_docs_count = source_db.get("docs_count")
        if manifest_docs_count != snapshot_source_docs_count:
            errors.append(
                _operational_receipt_error(
                    artifact_path,
                    "archive_snapshot.snapshot_source_docs_count must match manifest source_db.docs_count",
                )
            )
    return errors


def _validate_archive_snapshot_receipt(
    value: object,
    *,
    artifact_path: str,
    root: Path,
    payload: dict[str, Any],
    artifact_git_state: str,
) -> list[dict[str, str]]:
    if not isinstance(value, dict):
        if (
            value is None
            and artifact_git_state == "clean"
            and _is_pre_enforcement_archive_snapshot_receipt(payload)
        ):
            return []
        return [_operational_receipt_error(artifact_path, "archive_snapshot must be an object")]

    errors: list[dict[str, str]] = []
    if _has_secretish_keys(value):
        errors.append(_operational_receipt_error(artifact_path, "archive_snapshot contains secret-like credential keys"))

    legacy_fresh_export_schema = (
        artifact_git_state == "clean"
        and _is_pre_enforcement_archive_snapshot_fresh_export_receipt(payload)
    )
    missing_fields = sorted(field for field in ARCHIVE_SNAPSHOT_FIELDS if not _receipt_field_string(value.get(field, "")))
    legacy_missing_fresh_export_fields = (
        legacy_fresh_export_schema
        and bool(missing_fields)
        and set(missing_fields) <= ARCHIVE_SNAPSHOT_FRESH_EXPORT_FIELDS
    )
    if missing_fields:
        if not legacy_missing_fresh_export_fields:
            errors.append(
                _operational_receipt_error(
                    artifact_path,
                    f"archive_snapshot missing field(s): {', '.join(missing_fields)}",
                )
            )
            return errors

    status = _receipt_field_string(value.get("status", "")).lower()
    backend = _receipt_field_string(value.get("storage_backend", ""))
    manifest_path = _receipt_field_string(value.get("manifest_path", ""))
    artifact = _receipt_field_string(value.get("artifact_path", ""))
    object_uri = _receipt_field_string(value.get("object_uri", ""))
    checksum = _receipt_field_string(value.get("checksum", "")).lower()
    format_version = _receipt_field_string(value.get("format_version", ""))
    access_status = _receipt_field_string(value.get("access_status", ""))
    restore_status = _receipt_field_string(value.get("restore_status", ""))
    readback_status = _receipt_field_string(value.get("readback_status", ""))
    no_op_reason = _receipt_field_string(value.get("no_op_reason", ""))
    blocker_reason = _receipt_field_string(value.get("blocker_reason", ""))
    source = _receipt_field_string(value.get("source", ""))
    export_command = _receipt_field_string(value.get("export_command", ""))
    export_status = _receipt_field_string(value.get("export_status", ""))
    snapshot_created_at_utc = _receipt_field_string(value.get("snapshot_created_at_utc", ""))
    snapshot_source_db_sha256 = _receipt_field_string(value.get("snapshot_source_db_sha256", "")).lower()
    snapshot_source_docs_count_raw = _receipt_field_string(value.get("snapshot_source_docs_count", ""))
    require_fresh_export_fields = not legacy_missing_fresh_export_fields
    snapshot_source_docs_count: int | None = None

    if status not in ARCHIVE_SNAPSHOT_STATUSES:
        errors.append(_operational_receipt_error(artifact_path, f"archive_snapshot.status={status or 'missing'} unsupported"))
    if _is_meaningful_receipt_value(backend) and backend not in ARCHIVE_SNAPSHOT_BACKENDS:
        errors.append(_operational_receipt_error(artifact_path, f"archive_snapshot.storage_backend={backend} unsupported"))
    if _object_uri_has_inline_secret(object_uri):
        errors.append(_operational_receipt_error(artifact_path, "archive_snapshot.object_uri contains inline credentials or secret query"))
    if _is_meaningful_receipt_value(checksum) and not ARCHIVE_SHA256_RE.fullmatch(checksum):
        errors.append(_operational_receipt_error(artifact_path, "archive_snapshot.checksum must be lowercase sha256 hex or sha256:<hex>"))
    if _is_meaningful_receipt_value(snapshot_source_db_sha256) and not ARCHIVE_SHA256_RE.fullmatch(snapshot_source_db_sha256):
        errors.append(_operational_receipt_error(artifact_path, "archive_snapshot.snapshot_source_db_sha256 must be lowercase sha256 hex or sha256:<hex>"))

    if status == "ok":
        if backend not in ARCHIVE_SNAPSHOT_BACKENDS:
            errors.append(_operational_receipt_error(artifact_path, "archive_snapshot ok status requires storage_backend"))
        if not _is_meaningful_receipt_value(manifest_path):
            errors.append(_operational_receipt_error(artifact_path, "archive_snapshot ok status requires manifest_path"))
        if not _is_meaningful_receipt_value(checksum):
            errors.append(_operational_receipt_error(artifact_path, "archive_snapshot ok status requires checksum"))
        if not _is_meaningful_receipt_value(format_version):
            errors.append(_operational_receipt_error(artifact_path, "archive_snapshot ok status requires format_version"))
        if require_fresh_export_fields:
            if "planveyor_docs_archive_snapshot_export" not in export_command:
                errors.append(_operational_receipt_error(artifact_path, "archive_snapshot ok status requires export_command"))
            if export_status != "ok":
                errors.append(_operational_receipt_error(artifact_path, "archive_snapshot ok status requires export_status=ok"))
            if not _is_meaningful_receipt_value(snapshot_created_at_utc):
                errors.append(_operational_receipt_error(artifact_path, "archive_snapshot ok status requires snapshot_created_at_utc"))
            if not _is_meaningful_receipt_value(snapshot_source_db_sha256):
                errors.append(_operational_receipt_error(artifact_path, "archive_snapshot ok status requires snapshot_source_db_sha256"))
            try:
                snapshot_source_docs_count = int(snapshot_source_docs_count_raw)
            except ValueError:
                errors.append(_operational_receipt_error(artifact_path, "archive_snapshot.snapshot_source_docs_count must be a non-negative integer"))
            else:
                if snapshot_source_docs_count < 0:
                    errors.append(_operational_receipt_error(artifact_path, "archive_snapshot.snapshot_source_docs_count must be a non-negative integer"))
            if "planveyor_docs_archive_snapshot_export" not in source:
                errors.append(_operational_receipt_error(artifact_path, "archive_snapshot ok status requires source to include export"))
        if backend in S3_BACKENDS:
            if not _is_meaningful_receipt_value(object_uri):
                errors.append(_operational_receipt_error(artifact_path, "archive_snapshot selected S3/MinIO backend requires object_uri"))
            if access_status != "ok":
                errors.append(_operational_receipt_error(artifact_path, "archive_snapshot selected S3/MinIO backend requires access_status=ok"))
        elif not _is_meaningful_receipt_value(artifact):
            errors.append(_operational_receipt_error(artifact_path, "archive_snapshot git-backed backend requires artifact_path"))
        else:
            for field, rel_path in (("manifest_path", manifest_path), ("artifact_path", artifact)):
                candidate = Path(rel_path)
                if candidate.is_absolute() or ".." in candidate.parts:
                    errors.append(_operational_receipt_error(artifact_path, f"archive_snapshot {field} must be a repo-relative path"))
                    continue
                if not (root / candidate).is_file():
                    errors.append(_operational_receipt_error(artifact_path, f"archive_snapshot {field} missing on disk: {rel_path}"))
            if backend == "git_text_export" and require_fresh_export_fields and _is_meaningful_receipt_value(manifest_path):
                errors.extend(
                    _validate_git_text_archive_snapshot_manifest(
                        root=root,
                        artifact_path=artifact_path,
                        manifest_path=manifest_path,
                        artifact_path_field=artifact,
                        checksum=checksum,
                        storage_backend=backend,
                        format_version=format_version,
                        snapshot_created_at_utc=snapshot_created_at_utc,
                        snapshot_source_db_sha256=snapshot_source_db_sha256,
                        snapshot_source_docs_count=snapshot_source_docs_count,
                    )
                )
        if restore_status != "ok":
            errors.append(_operational_receipt_error(artifact_path, "archive_snapshot ok status requires restore_status=ok"))
        if readback_status != "ok":
            errors.append(_operational_receipt_error(artifact_path, "archive_snapshot ok status requires readback_status=ok"))
        if not _is_na_value(no_op_reason):
            errors.append(_operational_receipt_error(artifact_path, "archive_snapshot ok status requires no_op_reason=N/A (...)"))
        if not _is_na_value(blocker_reason):
            errors.append(_operational_receipt_error(artifact_path, "archive_snapshot ok status requires blocker_reason=N/A (...)"))
    elif status == "no_op":
        if not ARCHIVE_ENUM_RE.fullmatch(no_op_reason) or no_op_reason in DISALLOWED_ARCHIVE_NO_OP_REASONS:
            errors.append(_operational_receipt_error(artifact_path, "archive_snapshot no_op status requires allowed enum-like no_op_reason"))
        if not _is_na_value(blocker_reason):
            errors.append(_operational_receipt_error(artifact_path, "archive_snapshot no_op status requires blocker_reason=N/A (...)"))
        if restore_status not in {"no_op", "not_required"}:
            errors.append(_operational_receipt_error(artifact_path, "archive_snapshot no_op status requires restore_status=no_op|not_required"))
        if readback_status not in {"no_op", "not_required"}:
            errors.append(_operational_receipt_error(artifact_path, "archive_snapshot no_op status requires readback_status=no_op|not_required"))
    elif status == "blocked":
        if not ARCHIVE_ENUM_RE.fullmatch(blocker_reason):
            errors.append(_operational_receipt_error(artifact_path, "archive_snapshot blocked status requires enum-like blocker_reason"))
        if not _is_na_value(no_op_reason):
            errors.append(_operational_receipt_error(artifact_path, "archive_snapshot blocked status requires no_op_reason=N/A (...)"))
        errors.append(_operational_receipt_error(artifact_path, f"archive_snapshot blocked: {blocker_reason or 'missing'}"))

    if status == "ok" and require_fresh_export_fields:
        snapshot_dt = _parse_receipt_datetime(snapshot_created_at_utc)
        if snapshot_dt is None:
            errors.append(_operational_receipt_error(artifact_path, "archive_snapshot.snapshot_created_at_utc must be an ISO timestamp"))
        archive_record = _operational_step_record(payload, "docs_hygiene_archive")
        archive_dt = _parse_receipt_datetime(archive_record.get("captured_at", "")) if archive_record else None
        if archive_record is not None and archive_dt is None:
            errors.append(_operational_receipt_error(artifact_path, "docs_hygiene_archive.captured_at must be an ISO timestamp"))
        if snapshot_dt is not None and archive_dt is not None and snapshot_dt < archive_dt:
            errors.append(_operational_receipt_error(artifact_path, "archive_snapshot stale: snapshot_created_at_utc is older than docs_hygiene_archive.captured_at"))

    return errors


def _validate_operational_receipt_text(
    text: str,
    *,
    artifact_path: str,
    base: str,
    head: str,
    root: Path,
    artifact_git_state: str,
    range_candidates: list[str],
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    payload = _extract_json_block(text)
    if payload is None:
        return [
            {
                "code": "inconsistent_receipt",
                "detail": (
                    f"step:ready_to_push/post_merge_operational_closeout: malformed/token-only "
                    f"`## Operational receipt JSON` in {artifact_path}; expected {OPERATIONAL_RECEIPT_EXPECTED_SURFACE}"
                ),
            }
        ]

    expected_range = f"{base}..{head}" if base and head else ""
    expected_top = {
        "schema_version": OPERATIONAL_RECEIPT_SCHEMA_VERSION,
        "range": expected_range,
        "base": base,
        "head": head,
    }
    for field, expected in expected_top.items():
        actual = _receipt_field_string(payload.get(field, ""))
        if actual != expected:
            errors.append(_operational_receipt_error(artifact_path, f"{field}={actual or 'missing'}; expected={expected}"))
    tracker_path = _receipt_field_string(payload.get("tracker_path", ""))
    if tracker_path != ".planveyor.merge_tracker.md":
        errors.append(
            _operational_receipt_error(
                artifact_path,
                f"tracker_path={tracker_path or 'missing'}; expected=.planveyor.merge_tracker.md",
            )
        )

    steps = payload.get("steps")
    if not isinstance(steps, list):
        return errors + [_operational_receipt_error(artifact_path, "steps must be a list")]

    errors.extend(
        _validate_archive_snapshot_receipt(
            payload.get("archive_snapshot"),
            artifact_path=artifact_path,
            root=root,
            payload=payload,
            artifact_git_state=artifact_git_state,
        )
    )
    errors.extend(
        _validate_docs_hygiene_suggest_summary(
            payload.get("docs_hygiene_suggest_summary"),
            artifact_path=artifact_path,
            payload=payload,
            artifact_git_state=artifact_git_state,
        )
    )
    enforce_followups_launch = not (
        artifact_git_state == "clean" and _is_pre_enforcement_followups_triage_launch_receipt(payload)
    )
    errors.extend(
        _validate_followups_triage_launch_receipt(
            payload.get("followups_triage_launch_receipt"),
            artifact_path=artifact_path,
            root=root,
            payload=payload,
            artifact_git_state=artifact_git_state,
            range_candidates=range_candidates,
        )
    )
    errors.extend(
        _validate_followups_lane_reconciliation(
            payload.get("followups_lane_reconciliation"),
            artifact_path=artifact_path,
            payload=payload,
            artifact_git_state=artifact_git_state,
        )
    )
    errors.extend(
        _validate_process_improvements_open_summary(
            payload.get("process_improvements_open_summary"),
            artifact_path=artifact_path,
            root=root,
            payload=payload,
            artifact_git_state=artifact_git_state,
        )
    )
    enforce_docs_quality = not (
        artifact_git_state == "clean" and _is_pre_enforcement_docs_quality_receipt(payload)
    )

    seen_steps: set[str] = set()
    for index, row in enumerate(steps):
        if not isinstance(row, dict):
            errors.append(_operational_receipt_error(artifact_path, f"steps[{index}] must be an object"))
            continue
        step = _receipt_field_string(row.get("step", ""))
        if step not in OPERATIONAL_RECEIPT_STEPS:
            errors.append(_operational_receipt_error(artifact_path, f"steps[{index}].step={step or 'missing'} unsupported"))
            continue
        if step in seen_steps:
            errors.append(_operational_receipt_error(artifact_path, f"duplicate step row: {step}"))
        seen_steps.add(step)
        missing_fields = [field for field in OPERATIONAL_RECEIPT_STEP_FIELDS if not _receipt_field_string(row.get(field, ""))]
        if missing_fields:
            errors.append(_operational_receipt_error(artifact_path, f"{step}: missing field(s): {', '.join(sorted(missing_fields))}"))
            continue
        has_exit_code = _receipt_field_string(row.get("exit_code", "")) != ""
        has_result = _is_meaningful_receipt_value(_receipt_field_string(row.get("result", "")))
        if not has_exit_code and not has_result:
            errors.append(_operational_receipt_error(artifact_path, f"{step}: exit_code or result is required"))
        if has_exit_code:
            try:
                exit_code = int(_receipt_field_string(row.get("exit_code", "")))
            except ValueError:
                errors.append(_operational_receipt_error(artifact_path, f"{step}: exit_code must be integer"))
            else:
                if _receipt_field_string(row.get("in_scope", "")) == "yes" and exit_code != 0:
                    errors.append(_operational_receipt_error(artifact_path, f"{step}: in-scope exit_code must be 0"))
        in_scope = _receipt_field_string(row.get("in_scope", ""))
        no_op_reason = _receipt_field_string(row.get("no_op_reason", ""))
        command = _receipt_field_string(row.get("command", ""))
        if in_scope not in {"yes", "no"}:
            errors.append(_operational_receipt_error(artifact_path, f"{step}: in_scope must be yes|no"))
        if in_scope == "yes" and not _is_meaningful_receipt_value(command):
            errors.append(_operational_receipt_error(artifact_path, f"{step}: in-scope command is missing"))
        if in_scope == "yes" and not no_op_reason.lower().startswith("n/a"):
            errors.append(_operational_receipt_error(artifact_path, f"{step}: ran steps must use no_op_reason=N/A (why=ran)"))
        if in_scope == "no" and not _is_meaningful_receipt_value(no_op_reason):
            errors.append(_operational_receipt_error(artifact_path, f"{step}: skipped/out-of-scope row requires no_op_reason"))
        if step == "docs_hygiene_suggest":
            if in_scope != "yes":
                errors.append(_operational_receipt_error(artifact_path, f"{step}: report-only gate row must be in_scope=yes"))
            expected = _docs_hygiene_suggest_canonical_command(expected_range)
            if command not in {expected, DOCS_HYGIENE_SUGGEST_GATE_COMMAND}:
                errors.append(_operational_receipt_error(artifact_path, f"{step}: command must be exact wrapper gate or canonical same-range command"))
        if step == "planveyor_merge_bundle_report" and in_scope != "yes":
            errors.append(_operational_receipt_error(artifact_path, f"{step}: final gate row must be in_scope=yes"))
        if enforce_followups_launch and step == "followups_triage_launch":
            errors.extend(_validate_followups_triage_launch_row(row, artifact_path=artifact_path))
        if enforce_docs_quality and step == "docs_index_context":
            errors.extend(_validate_docs_index_context_row(row, artifact_path=artifact_path))
        if enforce_docs_quality and step == "retrieval_metrics":
            errors.extend(_validate_retrieval_metrics_row(row, artifact_path=artifact_path))

    required_steps = set(OPERATIONAL_RECEIPT_STEPS)
    if not enforce_followups_launch:
        required_steps.discard("followups_triage_launch")
    missing_steps = sorted(required_steps - seen_steps)
    if missing_steps:
        errors.append(_operational_receipt_error(artifact_path, f"missing step row(s): {', '.join(missing_steps)}"))

    return errors


def _packetization_source_only_paths(applicability: object) -> list[str]:
    records = getattr(applicability, "records", ())
    return sorted(
        {
            str(record.changed_file)
            for record in records
            if getattr(record, "source_only_reason", None)
        }
    )


def build_report(
    root: Path,
    tracker_path: Path | None = None,
    *,
    merge_binding: merge_gate_policy.TrackerBinding | None = None,
    mirror_policy: MirrorPolicy = GENERIC_MIRROR_POLICY,
) -> dict[str, Any]:
    # This is the direct report/digest/closeout entry.  Bind the engaged root,
    # declared policy, and lexical tracker before this historical report code
    # resolves the leaf or emits any tracker-derived report body.
    merge_gate_policy.validate_tracker_for_root(root, tracker_path, expected_binding=merge_binding)
    root = root.resolve()
    if tracker_path is None:
        tracker = (root / ".planveyor.merge_tracker.md").resolve()
    elif tracker_path.is_absolute():
        tracker = tracker_path.resolve()
    else:
        tracker = (root / tracker_path).resolve()

    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    base = _read_range_value(root / ".planveyor.range.base")
    head = _read_range_value(root / ".planveyor.range.head")
    if not base or not head:
        errors.append({"code": "missing_range", "detail": "missing .planveyor.range.base or .planveyor.range.head"})
        base = base or ""
        head = head or ""

    if not tracker.exists():
        errors.append({"code": "missing_tracker", "detail": str(tracker)})
        tracker_header: dict[str, str] = {}
        tracker_steps: list[dict[str, Any]] = []
    else:
        tracker_header, tracker_steps = _parse_tracker(tracker)
        if not tracker_steps:
            errors.append({"code": "no_tracker_steps", "detail": str(tracker)})

    range_ref = f"{base}..{head}" if base and head else ""
    tracker_range = tracker_header.get("RANGE", "")
    if range_ref and tracker_range and tracker_range != range_ref:
        errors.append(
            {
                "code": "range_mismatch",
                "detail": f"tracker={tracker_range}; saved={range_ref}",
            }
        )
    errors.extend(
        _tracker_header_consistency_errors(
            root=root,
            tracker_header=tracker_header,
            base=base,
            head=head,
        )
    )

    base_short = base[:7]
    head_short = head[:7]
    completed_steps = {str(step["key"]) for step in tracker_steps if step["checked"]}
    current_step = _first_unchecked(tracker_steps)
    operational_receipt_required = "step:ready_to_push" in completed_steps or (
        current_step == "step:ready_to_push"
        and bool(completed_steps & OPERATIONAL_RECEIPT_TRIGGER_STEPS)
    )

    rc, status_stdout, status_stderr = _run_git(root, "status", "--short", "--untracked-files=all")
    if rc == GIT_TIMEOUT_RETURN_CODE:
        errors.append({"code": "git_status_timeout", "detail": status_stderr.strip() or status_stdout.strip()})
        status_map: dict[str, dict[str, Any]] = {}
    elif rc != 0:
        errors.append({"code": "git_status_failed", "detail": status_stderr.strip() or status_stdout.strip()})
        status_map: dict[str, dict[str, Any]] = {}
    else:
        status_map = _parse_git_status(status_stdout)

    artifacts: list[dict[str, Any]] = []
    required_paths: set[str] = set()
    for spec in ARTIFACT_SPECS:
        if not base_short or not head_short:
            continue
        matches = _find_matches(root, spec.pattern(base_short, head_short))
        inactive_matches: list[str] = []
        if spec.kind == PACKETIZATION_GATE_RECEIPT_KIND:
            inactive_matches = [
                path for path in matches if _is_superseded_packetization_report(root, path)
            ]
            matches = [path for path in matches if path not in inactive_matches]
        required = spec.required_for_completed and spec.step in completed_steps
        if spec.kind == OPERATIONAL_RECEIPT_KIND:
            required = operational_receipt_required
        if spec.step == "step:plan_harvest" and spec.kind == "followups_backlog":
            classifications = [_classify_followups_backlog(root, path) for path in matches]
            primary_matches = [
                item for item in classifications if item.role == "primary_plan_harvest"
            ]
            supplemental_matches = [
                item for item in classifications if item.role == "supplemental_post_merge_audit"
            ]
            unknown_matches = [
                item for item in classifications if item.role == "unknown_same_range_followups"
            ]

            for item in unknown_matches:
                errors.append(
                    {
                        "code": "inconsistent_artifact_classification",
                        "detail": f"{spec.step}/{spec.kind}: {item.error}",
                    }
                )
                artifacts.append(
                    _artifact_row(
                        root=root,
                        spec=spec,
                        path=item.path,
                        required=False,
                        status_map=status_map,
                        kind="unknown_followups_backlog",
                        extra={
                            "followups_role": item.role,
                            "source": item.source or "missing",
                            "imported_into": item.imported_into or "missing",
                        },
                    )
                )
            for item in supplemental_matches:
                artifacts.append(
                    _artifact_row(
                        root=root,
                        spec=spec,
                        path=item.path,
                        required=False,
                        status_map=status_map,
                        kind="supplemental_followups_backlog",
                        extra={
                            "followups_role": item.role,
                            "source": item.source,
                            "imported_into": item.imported_into,
                        },
                    )
                )
            if len(primary_matches) > 1:
                primary_paths = [item.path for item in primary_matches]
                errors.append(
                    {
                        "code": "ambiguous_artifact",
                        "detail": f"{spec.step}/{spec.kind}: {', '.join(primary_paths)}",
                    }
                )
                for item in primary_matches:
                    artifacts.append(
                        _artifact_row(
                            root=root,
                            spec=spec,
                            path=item.path,
                            required=required,
                            status_map=status_map,
                            extra={
                                "followups_role": item.role,
                                "source": item.source,
                                "imported_into": item.imported_into or "missing",
                            },
                        )
                    )
                continue
            if not primary_matches:
                if required:
                    detail = f"{spec.step}/{spec.kind}: {spec.pattern(base_short, head_short)}"
                    if supplemental_matches:
                        detail += (
                            "; missing primary plan-harvest followups backlog; supplemental="
                            + ", ".join(item.path for item in supplemental_matches)
                        )
                    errors.append({"code": "missing_required_artifact", "detail": detail})
                continue

            primary = primary_matches[0]
            path = primary.path
            status = _extract_status(root / path) if spec.require_final_status else None
            status_final = _is_final_status(status) if spec.require_final_status else None
            if required:
                required_paths.add(path)
            if required and spec.require_final_status and not status_final:
                errors.append(
                    {
                        "code": "non_final_artifact_status",
                        "detail": f"{spec.step}/{spec.kind}: {path} status={status or 'missing'}",
                    }
                )
            artifacts.append(
                {
                    "step": spec.step,
                    "kind": spec.kind,
                    "path": path,
                    "required": required,
                    "git_state": _git_state_for(path, status_map),
                    "status": status,
                    "status_final": status_final,
                    "active_candidate": True,
                    "followups_role": primary.role,
                    "source": primary.source,
                    "imported_into": primary.imported_into or "missing",
                }
            )
            continue
        for path in inactive_matches:
            status = _extract_status(root / path) if spec.require_final_status else None
            artifacts.append(
                {
                    "step": spec.step,
                    "kind": spec.kind,
                    "path": path,
                    "required": False,
                    "git_state": _git_state_for(path, status_map),
                    "status": status,
                    "status_final": _is_final_status(status) if spec.require_final_status else None,
                    "active_candidate": False,
                }
            )
        if len(matches) > 1:
            errors.append(
                {
                    "code": "ambiguous_artifact",
                    "detail": f"{spec.step}/{spec.kind}: {', '.join(matches)}",
                }
            )
            for path in matches:
                artifacts.append(
                    {
                        "step": spec.step,
                        "kind": spec.kind,
                        "path": path,
                        "required": required,
                        "git_state": _git_state_for(path, status_map),
                        "status": None,
                        "status_final": None,
                        "active_candidate": True,
                    }
                )
            continue
        if not matches:
            if required:
                code = (
                    "missing_required_receipt"
                    if spec.kind == OPERATIONAL_RECEIPT_KIND
                    else "missing_required_artifact"
                )
                errors.append(
                    {
                        "code": code,
                        "detail": f"{spec.step}/{spec.kind}: {spec.pattern(base_short, head_short)}",
                    }
                )
            continue
        path = matches[0]
        status = _extract_status(root / path) if spec.require_final_status else None
        status_final = _is_final_status(status) if spec.require_final_status else None
        if required:
            required_paths.add(path)
        if required and spec.require_final_status and not status_final:
            errors.append(
                {
                    "code": "non_final_artifact_status",
                    "detail": f"{spec.step}/{spec.kind}: {path} status={status or 'missing'}",
                }
            )
        artifacts.append(
            {
                "step": spec.step,
                "kind": spec.kind,
                "path": path,
                "required": required,
                "git_state": _git_state_for(path, status_map),
                "status": status,
                "status_final": status_final,
                "active_candidate": True,
            }
        )

    no_committed_artifact_steps = [
        step for step in sorted(completed_steps) if step in NO_COMMITTED_ARTIFACT_STEPS
    ]
    post_merge_audit_authority: dict[str, Any] = {
        "state": "not_required",
        "paths": [],
        "findings": [],
    }
    post_merge_audit_paths = [
        str(artifact["path"])
        for artifact in artifacts
        if artifact.get("kind") == "post_merge_audit" and artifact.get("active_candidate", True)
    ]
    if post_merge_audit_paths:
        post_merge_audit_authority["state"] = "green"
        post_merge_audit_authority["paths"] = post_merge_audit_paths
        audit_artifacts = post_merge_audit_lint.load_audit_artifacts(root, post_merge_audit_paths)
        audit_findings = [
            finding
            for artifact in audit_artifacts
            for finding in post_merge_audit_lint._lint_current_audit_status_authority(artifact)
        ]
        if audit_findings:
            post_merge_audit_authority["state"] = "blocked"
            post_merge_audit_authority["findings"] = [finding.render() for finding in audit_findings]
            errors.extend(
                {
                    "code": "post_merge_audit_authority_blocked",
                    "detail": finding.render(),
                }
                for finding in audit_findings
            )
    artifact_lineage = _attach_artifact_timestamp_lineage(root, artifacts)

    range_candidates: list[str] = []
    if range_ref:
        range_candidates, diagnostic = _range_diff_candidates(root, range_ref)
        if diagnostic:
            if diagnostic["code"] == "range_diff_timeout":
                errors.append(diagnostic)
            else:
                warnings.append(diagnostic)

    try:
        packetization_applicability = resolve_target_applicability(
            root,
            changed_files=range_candidates,
            base=base or None,
            head=head or None,
            mirror_policy=mirror_policy,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        errors.append(
            {
                "code": "packetization_applicability_unavailable",
                "detail": str(exc),
            }
        )
        packetization_applicability = resolve_target_applicability(
            root,
            changed_files=range_candidates,
            mirror_policy=mirror_policy,
        )
    packetization_shared_paths = list(packetization_applicability.report_context_paths)
    packetization_source_only = _packetization_source_only_paths(packetization_applicability)
    packetization_reports = [
        artifact["path"]
        for artifact in artifacts
        if artifact["kind"] == PACKETIZATION_GATE_RECEIPT_KIND and artifact.get("active_candidate", True)
    ]
    packetization_readback = _packetization_readback(
        root=root,
        active_reports=[str(path) for path in packetization_reports],
        artifacts=artifacts,
    )
    packetization_required = packetization_applicability.packetization_report_required
    if packetization_required and not packetization_reports:
        errors.append(
            {
                "code": "missing_packetization_report",
                "detail": (
                    "applicable report-context files changed without "
                    f"docs/reviews/*_packetization_gate_range_{base_short}_{head_short}.md; "
                    f"sample={', '.join(packetization_shared_paths[:5])}"
                ),
            }
        )
    for report_path in packetization_reports:
        if _report_has_blocking_packetization_rows(root, str(report_path)):
            report_readback = _packetization_readback(
                root=root,
                active_reports=[str(report_path)],
                artifacts=artifacts,
            )
            present = _present_blocking_coverage_counts(report_readback)
            errors.append(
                {
                    "code": "blocking_packetization_rows",
                    "detail": f"{report_path} contains {', '.join(present) or 'structural blocking rows'}",
                }
            )
        errors.extend(_packetization_report_schema_errors(root, str(report_path)))
    if len(packetization_reports) == 1:
        errors.extend(
            _validate_packetization_report_freshness(
                root=root,
                active_report=str(packetization_reports[0]),
                range_ref=range_ref,
                mirror_policy=mirror_policy,
            )
        )
        current_delivery_errors = _validate_packetization_current_delivery(
            root=root,
            active_report=str(packetization_reports[0]),
            range_ref=range_ref,
            mirror_policy=mirror_policy,
        )
        errors.extend(current_delivery_errors)
        accepted_packet_paths = packetization_readback.get("report_accepted_packet_paths")
        if not current_delivery_errors and isinstance(accepted_packet_paths, list):
            required_paths.update(_path_list(accepted_packet_paths))

    canon_sweep_receipts, canon_sweep_errors = _validate_canon_sweep_proof(
        root=root,
        artifacts=artifacts,
        completed_steps=completed_steps,
        packetization_reports=packetization_reports,
    )
    substep_receipts = list(canon_sweep_receipts)
    errors.extend(canon_sweep_errors)
    docs_finalize_artifacts = [
        artifact
        for artifact in artifacts
        if artifact.get("kind") == DOCS_FINALIZE_RECEIPT_KIND
        and artifact.get("active_candidate", True)
    ]
    if "step:docs_finalize" in completed_steps and len(docs_finalize_artifacts) == 1:
        docs_finalize_preflight = validate_post_merge_receipt_preflight(
            root=root,
            step="docs_finalize",
            path=str(docs_finalize_artifacts[0]["path"]),
            role="Architect",
            docs_finalize_range=range_ref,
        )
        substep_receipts.extend(docs_finalize_preflight["receipts"])
        errors.extend(docs_finalize_preflight["errors"])
    for receipt in canon_sweep_receipts:
        receipt_path = str(receipt.get("path") or "")
        if receipt_path and receipt_path != "(none)":
            required_paths.add(receipt_path)

    required_substep_receipts, receipt_errors = _validate_substep_receipts(
        root=root,
        artifacts=artifacts,
        completed_steps=completed_steps,
        packetization_required=packetization_required,
        packetization_reports=packetization_reports,
    )
    substep_receipts.extend(required_substep_receipts)
    errors.extend(receipt_errors)
    operational_receipts, operational_receipt_errors = _validate_operational_receipt(
        root=root,
        artifacts=artifacts,
        required=operational_receipt_required,
        base=base,
        head=head,
        range_candidates=range_candidates,
    )
    substep_receipts.extend(operational_receipts)
    errors.extend(operational_receipt_errors)
    closeout_receipts, closeout_receipt_errors, ready_to_push_terminal_proof = (
        _validate_ready_to_push_closeout_receipt(
            root=root,
            artifacts=artifacts,
            completed_steps=completed_steps,
            current_step=current_step,
            base=base,
            head=head,
        )
    )
    substep_receipts.extend(closeout_receipts)
    errors.extend(closeout_receipt_errors)
    for receipt in closeout_receipts:
        if receipt.get("present") and receipt.get("path") and receipt.get("path") != "(none)":
            required_paths.add(str(receipt["path"]))
    risk_packet_state, risk_packet_errors, risk_packet_required_path = _validate_range_review_risk_packet(
        root=root,
        completed_steps=completed_steps,
        current_step=current_step,
        ready_to_push_terminal_proof=ready_to_push_terminal_proof,
        base=base,
        head=head,
    )
    errors.extend(risk_packet_errors)
    if risk_packet_required_path:
        required_paths.add(risk_packet_required_path)
    archive_snapshot = _extract_operational_archive_snapshot(root=root, artifacts=artifacts)
    docs_hygiene_suggest_summary = _extract_operational_docs_hygiene_suggest_summary(
        root=root,
        artifacts=artifacts,
    )
    followups_triage_launch_receipt = _extract_operational_followups_triage_launch_receipt(
        root=root,
        artifacts=artifacts,
    )
    followups_lane_reconciliation = _extract_operational_followups_lane_reconciliation(
        root=root,
        artifacts=artifacts,
    )
    process_improvements_open_summary = _extract_operational_process_improvements_open_summary(
        root=root,
        artifacts=artifacts,
    )
    errors.extend(
        _validate_operational_harvest_freshness(
            root=root,
            artifacts=artifacts,
            operational_payload=_operational_receipt_payload(root=root, artifacts=artifacts),
        )
    )
    operator_receipt_checklist = build_operator_receipt_checklist(substep_receipts, errors)

    grouped_status: dict[str, list[dict[str, Any]]] = {
        "required": [],
        "candidate_contextual": [],
        "suspicious": [],
    }
    all_status_paths = set(status_map)
    for path in sorted(all_status_paths):
        bucket = _status_bucket(path, required_paths)
        item = {
            "path": path,
            "git_state": _git_state_for(path, status_map),
            "source": "git_status" if path in status_map else "range_diff",
        }
        if bucket == "required":
            grouped_status["required"].append(item)
        elif bucket == "candidate/contextual":
            grouped_status["candidate_contextual"].append(item)
        else:
            grouped_status["suspicious"].append(item)

    return {
        "status": "blocked" if errors else "ok",
        "errors": errors,
        "warnings": warnings,
        "range": {
            "base": base,
            "head": head,
            "range": range_ref,
            "base_short": base_short,
            "head_short": head_short,
        },
        "tracker": {
            "path": str(tracker),
            "header": tracker_header,
            "header_range": tracker_range,
            "current_step": current_step,
            "steps": tracker_steps,
            "completed_steps": sorted(completed_steps),
        },
        "artifacts": artifacts,
        "artifact_lineage": artifact_lineage,
        "no_committed_artifact_steps": no_committed_artifact_steps,
        "packetization_gate": {
            "required": packetization_required,
            "packetization_report_required": packetization_applicability.packetization_report_required,
            "target_packet_required": packetization_applicability.target_packet_required,
            "target_partitions": [partition.to_json() for partition in packetization_applicability.partitions],
            "shared_canon_files_count": len(packetization_shared_paths),
            "sample_shared_canon_files": packetization_shared_paths[:20],
            "source_only_files_count": len(packetization_source_only),
            "sample_source_only_files": packetization_source_only[:20],
            "report_paths": packetization_reports,
            **packetization_readback,
        },
        "archive_snapshot": archive_snapshot or {},
        "docs_hygiene_suggest_summary": docs_hygiene_suggest_summary or {},
        "followups_triage_launch_receipt": followups_triage_launch_receipt or {},
        "followups_lane_reconciliation": followups_lane_reconciliation or {},
        "process_improvements_open_summary": process_improvements_open_summary or {},
        "ready_to_push_terminal_proof": ready_to_push_terminal_proof,
        "risk_packet_state": risk_packet_state,
        "post_merge_audit_authority": post_merge_audit_authority,
        "substep_receipts": substep_receipts,
        "operator_receipt_checklist": operator_receipt_checklist,
        "range_diff_candidates": {
            "count": len(range_candidates),
            "sample_paths": range_candidates[:20],
            "omitted_count": max(0, len(range_candidates) - 20),
        },
        "git_status": grouped_status,
    }


def render_plain(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("merge_bundle_report:")
    lines.append(f"  status: {payload['status']}")
    lines.append(f"  range: {payload['range']['range'] or '(missing)'}")
    lines.append(f"  tracker: {payload['tracker']['path']}")
    lines.append(f"  current_step: {payload['tracker']['current_step'] or '(done)'}")
    if payload["errors"]:
        lines.append("  errors:")
        for error in payload["errors"]:
            lines.append(f"    - {error['code']}: {error['detail']}")
    if payload["warnings"]:
        lines.append("  warnings:")
        for warning in payload["warnings"]:
            lines.append(f"    - {warning['code']}: {warning['detail']}")

    lines.append("")
    lines.append("required/current artifacts:")
    if payload["artifacts"]:
        for artifact in payload["artifacts"]:
            req = "required" if artifact["required"] else "candidate/contextual"
            status = artifact["status"] if artifact["status"] is not None else "N/A"
            detail_parts = []
            if artifact.get("followups_role"):
                detail_parts.append(f"role={artifact['followups_role']}")
            if artifact.get("source"):
                detail_parts.append(f"source={artifact['source']}")
            if artifact.get("imported_into"):
                detail_parts.append(f"imported_into={artifact['imported_into']}")
            details = f" ({'; '.join(detail_parts)})" if detail_parts else ""
            lines.append(
                f"  - {artifact['step']} {artifact['kind']} "
                f"[{req}; git={artifact['git_state']}; status={status}]: "
                f"{artifact['path']}{details}"
            )
    else:
        lines.append("  - (none)")
    for step in payload["no_committed_artifact_steps"]:
        lines.append(
            f"  - {step} [completed; no committed per-step artifact required; final closeout uses operational receipt]"
        )
    artifact_lineage = payload.get("artifact_lineage") or {}
    divergent_paths = set(artifact_lineage.get("divergent_artifact_paths") or [])
    if divergent_paths:
        lines.append("")
        lines.append("artifact timestamp lineage (derived/read-only; chronology authority=git_commit_order):")
        lines.append("  note: artifact filename timestamps are not commit chronology or status authority")
        for artifact in payload["artifacts"]:
            if artifact.get("path") not in divergent_paths:
                continue
            lineage = artifact.get("artifact_lineage") or {}
            lines.append(
                "  - "
                f"{lineage.get('artifact_path')}: "
                f"artifact_materialized_at={lineage.get('artifact_materialized_at') or '(unknown)'} "
                f"(derived_from_filename={str(lineage.get('derived_from_filename')).lower()}); "
                f"commit_sha={lineage.get('commit_sha_short') or '(uncommitted)'}; "
                f"committed_at={lineage.get('committed_at') or '(unknown)'}; "
                f"artifact_order={lineage.get('artifact_timestamp_order_index')}; "
                f"commit_order={lineage.get('commit_order_index')}; "
                f"lineage_role={lineage.get('lineage_role')}"
            )

    range_candidates = payload["range_diff_candidates"]
    packetization_gate = payload["packetization_gate"]
    lines.append("")
    lines.append("packetization gate:")
    lines.append(
        f"  required: {packetization_gate['required']} "
        f"(shared={packetization_gate['shared_canon_files_count']}; "
        f"source_only={packetization_gate['source_only_files_count']})"
    )
    if packetization_gate["report_paths"]:
        for path in packetization_gate["report_paths"]:
            lines.append(f"  - report: {path}")
    else:
        lines.append("  - report: (none)")
    lines.append(f"  active_packetization_report: {packetization_gate['active_packetization_report']}")
    lines.append(f"  schema_version: {packetization_gate['schema_version']}")
    superseded_reports = packetization_gate["superseded_packetization_reports"]
    if superseded_reports:
        lines.append(f"  superseded_packetization_reports: {', '.join(superseded_reports)}")
    else:
        lines.append("  superseded_packetization_reports: (none)")
    lines.append(f"  blocking_rows_count: {packetization_gate['blocking_rows_count']}")
    if packetization_gate["blocking_coverages"]:
        lines.append(f"  blocking_coverages: {', '.join(packetization_gate['blocking_coverages'])}")
    else:
        lines.append("  blocking_coverages: (none)")
    present_coverage_counts = _present_blocking_coverage_counts(packetization_gate)
    if present_coverage_counts:
        lines.append(
            "  blocking_coverage_counts: "
            + ", ".join(present_coverage_counts)
        )
    else:
        lines.append("  blocking_coverage_counts: (none)")
    lines.append(f"  draft_packets_created_count: {packetization_gate['draft_packets_created_count']}")
    if packetization_gate["draft_packets_created_paths"]:
        lines.append(f"  draft_packets_created_paths: {', '.join(packetization_gate['draft_packets_created_paths'])}")
    else:
        lines.append("  draft_packets_created_paths: (none)")
    reused_paths = packetization_gate["draft_packets_reused_paths"]
    if isinstance(reused_paths, list):
        lines.append(f"  draft_packets_reused_paths: {', '.join(reused_paths) if reused_paths else '(none)'}")
    else:
        lines.append(f"  draft_packets_reused_paths: {reused_paths}")
    accepted_paths = packetization_gate["report_accepted_packet_paths"]
    if isinstance(accepted_paths, list):
        lines.append(f"  report_accepted_packet_paths: {', '.join(accepted_paths) if accepted_paths else '(none)'}")
    else:
        lines.append(f"  report_accepted_packet_paths: {accepted_paths}")

    archive_snapshot = payload.get("archive_snapshot") or {}
    lines.append("")
    lines.append("archive snapshot receipt:")
    if archive_snapshot:
        fields = (
            "status",
            "storage_backend",
            "manifest_path",
            "artifact_path",
            "object_uri",
            "checksum",
            "format_version",
            "access_status",
            "export_command",
            "export_status",
            "snapshot_created_at_utc",
            "snapshot_source_db_sha256",
            "snapshot_source_docs_count",
            "restore_status",
            "readback_status",
            "no_op_reason",
            "blocker_reason",
        )
        for field in fields:
            lines.append(f"  - {field}: {archive_snapshot.get(field) or '(missing)'}")
    else:
        lines.append("  - (none)")

    hygiene_summary = payload.get("docs_hygiene_suggest_summary") or {}
    lines.append("")
    lines.append("docs hygiene suggest summary:")
    if hygiene_summary:
        lines.append(f"  - report_only: {hygiene_summary.get('report_only')}")
        lines.append(f"  - deletion_executed: {hygiene_summary.get('deletion_executed')}")
        lines.append(f"  - ready_to_push_ticked_by_suggest_gate: {hygiene_summary.get('ready_to_push_ticked_by_suggest_gate')}")
        lines.append(f"  - omitted_count: {hygiene_summary.get('omitted_count')}")
    else:
        lines.append("  - (none)")

    followups_launch = payload.get("followups_triage_launch_receipt") or {}
    lines.append("")
    lines.append("followups triage launch receipt:")
    if followups_launch:
        lines.append(f"  - source_harvest_receipt_path: {followups_launch.get('source_harvest_receipt_path')}")
        lines.append(f"  - triage_mode: {followups_launch.get('triage_mode')}")
        index_rebuild = followups_launch.get("index_rebuild") or {}
        if isinstance(index_rebuild, dict):
            lines.append(f"  - index_rebuild_status: {index_rebuild.get('status')}")
            lines.append(f"  - readback_status: {index_rebuild.get('readback_status')}")
    else:
        lines.append("  - (none)")

    reconciliation = payload.get("followups_lane_reconciliation") or {}
    lines.append("")
    lines.append("followups lane reconciliation:")
    if reconciliation:
        lines.append(f"  - source_harvest_receipt_path: {reconciliation.get('source_harvest_receipt_path')}")
        lines.append(f"  - harvest_file_followups_result: {reconciliation.get('harvest_file_followups_result')}")
        lines.append(f"  - harvest_file_followups_count: {reconciliation.get('harvest_file_followups_count')}")
        lines.append(f"  - range_triage_mode: {reconciliation.get('range_triage_mode')}")
        lines.append(f"  - range_append_new: {reconciliation.get('range_append_new')}")
        lines.append(f"  - range_possible_duplicate: {reconciliation.get('range_possible_duplicate')}")
        lines.append(f"  - range_route_fallback: {reconciliation.get('range_route_fallback')}")
        lines.append(f"  - range_unparsed_bullets: {reconciliation.get('range_unparsed_bullets')}")
        lines.append(f"  - owner_summary: {reconciliation.get('owner_summary')}")
    else:
        lines.append("  - (none)")

    pi_summary = payload.get("process_improvements_open_summary") or {}
    lines.append("")
    lines.append("process improvements open summary:")
    if pi_summary:
        lines.append(f"  - source_harvest_receipt_path: {pi_summary.get('source_harvest_receipt_path')}")
        lines.append(f"  - decision_receipt_path: {pi_summary.get('decision_receipt_path')}")
        lines.append(f"  - ordinary_followups_result: {pi_summary.get('ordinary_followups_result')}")
        lines.append(f"  - lane_status: {pi_summary.get('lane_status')}")
        lines.append(f"  - counts_by_raw_status: {pi_summary.get('counts_by_raw_status')}")
        lines.append(f"  - null_execution_rows: {pi_summary.get('null_execution_rows')}")
    else:
        lines.append("  - (none)")

    terminal_proof = payload.get("ready_to_push_terminal_proof") or {}
    lines.append("")
    lines.append("ready_to_push terminal proof:")
    if terminal_proof:
        lines.append(f"  - state: {terminal_proof.get('state')}")
        if terminal_proof.get("pre_receipt_state"):
            lines.append(f"  - pre_receipt_state: {terminal_proof.get('pre_receipt_state')}")
        lines.append(f"  - required: {terminal_proof.get('required')}")
        lines.append(f"  - path: {terminal_proof.get('path') or '(none)'}")
        if terminal_proof.get("final_bundle_status"):
            lines.append(f"  - final_bundle_status: {terminal_proof.get('final_bundle_status')}")
        if terminal_proof.get("pending_owner_gate"):
            lines.append(f"  - pending_owner_gate: {terminal_proof.get('pending_owner_gate')}")
    else:
        lines.append("  - (none)")

    risk_packet = payload.get("risk_packet_state") or {}
    lines.append("")
    lines.append("range review risk packet:")
    if risk_packet:
        lines.append(f"  - state: {risk_packet.get('state')}")
        lines.append(f"  - required: {risk_packet.get('required')}")
        lines.append(f"  - path: {risk_packet.get('packet_path') or risk_packet.get('path') or '(none)'}")
        lines.append(f"  - packet_status: {risk_packet.get('packet_status') or '(none)'}")
    else:
        lines.append("  - (none)")

    lines.append("")
    lines.append("sub-step receipts:")
    if payload["substep_receipts"]:
        for receipt in payload["substep_receipts"]:
            state = "present" if receipt["present"] else "missing"
            lines.append(
                f"  - {receipt['step']} {receipt['receipt']} [{state}]: {receipt['path']}"
            )
    else:
        lines.append("  - (none)")

    lines.append("")
    lines.append("operator receipt checklist:")
    if payload["operator_receipt_checklist"]:
        for row in payload["operator_receipt_checklist"]:
            lines.append(
                f"  - {row['step']} {row['receipt']} "
                f"[{row['status']}; blocker={row['blocker_code']}]: {row['source_artifact']}"
            )
            lines.append(f"    command: {row['source_command']}")
            lines.append(f"    next: {row['next_action']}")
            if row.get("error_detail"):
                lines.append(f"    detail: {row['error_detail']}")
    else:
        lines.append("  - (none)")

    lines.append("")
    lines.append("")
    lines.append("range diff candidates:")
    lines.append(
        f"  count: {range_candidates['count']} (showing {len(range_candidates['sample_paths'])}; omitted {range_candidates['omitted_count']})"
    )
    for path in range_candidates["sample_paths"]:
        lines.append(f"  - {path}")

    lines.append("")
    lines.append("git status grouping:")
    for title, key in (
        ("required", "required"),
        ("candidate/contextual", "candidate_contextual"),
        ("suspicious", "suspicious"),
    ):
        lines.append(f"  {title}:")
        items = payload["git_status"][key]
        if not items:
            lines.append("    - (none)")
            continue
        for item in items:
            lines.append(f"    - [{item['git_state']}; {item['source']}] {item['path']}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Read-only final merge bundle report helper")
    parser.add_argument("--root", default=".", help="Repository root (default: current directory)")
    parser.add_argument(
        "--tracker",
        default=None,
        help="Path to .planveyor.merge_tracker.md (default: <root>/.planveyor.merge_tracker.md)",
    )
    parser.add_argument(
        "--format",
        choices=("plain", "json"),
        default="plain",
        help="Output format (default: plain)",
    )
    parser.add_argument(
        "--content-profile-id",
        default="default",
        choices=("default", "planveyor", "target-local"),
        help="Resolved public content profile for the generic mirror policy.",
    )
    ns = parser.parse_args(argv)

    try:
        mirror_policy = load_shared_docs_mirror_policy(content_profile_id=ns.content_profile_id)
        payload = build_report(
            Path(ns.root),
            Path(ns.tracker) if ns.tracker else None,
            mirror_policy=mirror_policy,
        )
    except (
        merge_gate_policy.MergeGatePolicyError,
        merge_gate_policy.authority.ContractAuthorityError,
        MirrorPolicyError,
    ) as exc:
        print(f"merge_bundle_report: {getattr(exc, 'reason_code', 'merge_policy_invalid')}: {exc}", file=sys.stderr)
        return 2
    if ns.format == "json":
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    else:
        sys.stdout.write(render_plain(payload) + "\n")
    return 2 if payload["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

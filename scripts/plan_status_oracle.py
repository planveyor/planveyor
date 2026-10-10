#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import re
import subprocess
import sys
import unicodedata
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, cast

sys.dont_write_bytecode = True
sys.pycache_prefix = os.devnull


SCRIPT_DIR = Path(__file__).resolve().parent
_script_dir_text = os.fspath(SCRIPT_DIR)
if _script_dir_text in sys.path:
    sys.path.remove(_script_dir_text)
sys.path.insert(0, _script_dir_text)


def _module_has_expected_origin(module: object, expected: Path) -> bool:
    origin = getattr(module, "__file__", None)
    if not isinstance(origin, str):
        return False
    try:
        return Path(origin).resolve(strict=True) == expected
    except (OSError, RuntimeError, ValueError):
        return False


def _scripts_package_is_local() -> bool:
    """Whether a preloaded ``scripts`` package belongs to this runtime."""

    package = sys.modules.get("scripts")
    if package is None:
        return True
    package_paths = getattr(package, "__path__", None)
    if package_paths is None:
        return False
    try:
        paths = tuple(Path(entry).resolve(strict=True) for entry in package_paths)
    except (OSError, RuntimeError, TypeError, ValueError):
        return False
    if not paths or any(path != SCRIPT_DIR for path in paths):
        return False
    package_file = getattr(package, "__file__", None)
    if package_file is not None and not _module_has_expected_origin(package, SCRIPT_DIR / "__init__.py"):
        return False
    return True


def _assert_alias_origin(module: object | None, expected: Path) -> None:
    if module is not None and not _module_has_expected_origin(module, expected):
        raise ImportError("authority module has an unsafe origin")


def _authority_module() -> Any:
    """Load only the sibling authority module under both trusted spellings."""

    package_is_local = _scripts_package_is_local()
    expected = SCRIPT_DIR / "contract_authority_context.py"
    direct = sys.modules.get("contract_authority_context")
    packaged = sys.modules.get("scripts.contract_authority_context")
    _assert_alias_origin(direct, expected)
    _assert_alias_origin(packaged, expected)
    if direct is not None and packaged is not None and direct is not packaged:
        raise ImportError("authority module aliases are split")
    module = direct or packaged
    if module is None:
        module = importlib.import_module("contract_authority_context")
        _assert_alias_origin(module, expected)
    sys.modules["contract_authority_context"] = module
    if package_is_local:
        sys.modules["scripts.contract_authority_context"] = module
    return module


_authority = _authority_module()
if TYPE_CHECKING:
    from contract_authority_context import (
        ContractAuthorityError,
        ContractContext,
        context_for_reader,
        context_to_json,
        read_declared_text,
        resolve_top_level_context,
    )
else:
    ContractAuthorityError = _authority.ContractAuthorityError
    ContractContext = _authority.ContractContext
    context_for_reader = _authority.context_for_reader
    context_to_json = _authority.context_to_json
    read_declared_text = _authority.read_declared_text
    resolve_top_level_context = _authority.resolve_top_level_context

import contract_authority_children
import review_artifact_lint
import review_header_metadata
import review_target_snapshot
from fs_object_identity import ObjectIdentityError, snapshot_regular_or_absent


RUNTIME_CLASS_EXECUTABLE = "executable"
RUNTIME_CLASS_PARKED_UMBRELLA = "parked_umbrella"
RUNTIME_CLASS_ROUTING_ONLY_BASELINE = "routing_only_baseline"
RUNTIME_CLASS_VERIFIED_REFERENCE_CHILD = "verified_reference_child"
NON_EXECUTABLE_RUNTIME_CLASSES = {
    RUNTIME_CLASS_PARKED_UMBRELLA,
    RUNTIME_CLASS_ROUTING_ONLY_BASELINE,
    RUNTIME_CLASS_VERIFIED_REFERENCE_CHILD,
}
NON_EXECUTABLE_HANDOFF_KEYS = (
    "ready for coder",
    "ready for review",
    "ready for arch review",
)
REVIEW_ONLY_IMPLEMENTATION_STATUS_NORMS = {
    "ready for planner",
    "planner intake",
    "planner finalize",
    "ready for coder",
    "coder intake",
    "in progress",
}
SCOPE_EXPANSION_DOWNSTREAM_STATUS_NORMS = {
    "ready for planner",
    "planner intake",
    "planner finalize",
    "ready for coder",
    "coder intake",
    "in progress",
    "ready for review",
    "reviewer intake",
    "reviewer code review",
    "reviewer visual review",
}
SCOPE_EXPANSION_ARCHITECT_ACCEPTED_BLOCKED_STATUS_NORMS = (
    SCOPE_EXPANSION_DOWNSTREAM_STATUS_NORMS | {"done"}
)
SCOPE_EXPANSION_REQUIRED_FIELDS = ("state", "target_contour", "source_ref", "reason")
REVIEW_ONLY_ROUTE_OVERRIDE_KEY = "review_only_route_override"
PROMOTED_ROUTE_ARTIFACT_HEADING_RE = re.compile(r"^\s*##\s+Promoted route artifact\b", re.IGNORECASE)
ANALYSIS_PACK_HEADING_RE = re.compile(r"^\s*##\s+Analysis pack\b", re.IGNORECASE)
ANALYSIS_PACK_AUTHORITY_INVALID = "analysis_pack_authority_invalid"
ANALYSIS_PACK_TEMPLATE_SENTINEL = "`docs/analysis_packs/<PLAN_STEM>.md#Analysis-pack`"
# An `analysis_wave` plan may keep its pack as the plan-resident `## Analysis pack`
# table only while no code draft is required: Architect and Planner intake, plus
# `Superseded` history retired before the transfer. From `Planner finalize` on the
# pack is the standalone `docs/analysis_packs/<PLAN_STEM>.md` review target, because
# the origin plan can never be a reviewed target itself.
ANALYSIS_PACK_PLAN_RESIDENT_STATUS_NORMS = frozenset(
    {
        "architect initial draft",
        "architect draft",
        "ready for planner",
        "planner intake",
        "ready for architect response",
        "architect response",
        "superseded",
    }
)
ANALYSIS_PACK_OPERATIONAL_FIELDS = frozenset(
    {
        "recommendation",
        "route_recommendation",
        "execution_budget",
        "stale_trigger",
    }
)
ANALYSIS_PACK_REF_RE = re.compile(
    r"^\s*`(?P<ref>docs/analysis_packs/[A-Za-z0-9][A-Za-z0-9_./-]*\.md#Analysis-pack)`(?P<annotation>.*)$"
)
REVIEW_ARTIFACTS_HEADING_RE = re.compile(r"^\s*##\s+Review artifacts\b", re.IGNORECASE)
REVIEW_ARTIFACT_RE = re.compile(r"docs/(?:code_reviews|doc_reviews)/[A-Za-z0-9][A-Za-z0-9_./-]*\.md")
LIVE_REVIEW_ARTIFACT_LINE_RE = re.compile(
    r"^\s*-\s*(?:Code review \(primary\)|Doc review \(docs-only\))\s*:\s*(?P<body>.*)$",
    re.IGNORECASE,
)
REVIEW_DATE_LINE_RE = re.compile(r"^\s*\*\*Date:\*\*\s*(?P<value>.+?)\s*$", re.IGNORECASE)
REVIEW_BLOCKER_STATUS_RE = re.compile(r"s1 blocker", re.IGNORECASE)
REVIEW_OK_STATUS_RE = re.compile(r"(?:✅\s*)?ok\b", re.IGNORECASE)
STALE_NOTE_LINE_RE = re.compile(r"^\s*-\s*stale note\s*\((?P<meta>[^)]*)\)\s*:\s*(?P<body>.*)$", re.IGNORECASE)
RERUN_NOTE_LINE_RE = re.compile(r"^\s*-\s*rerun note\s*\((?P<meta>[^)]*)\)\s*:\s*(?P<body>.*)$", re.IGNORECASE)
SAME_REVIEW_FILE_RE = re.compile(r"(?:same review (?:file|artifact)|этот же review[- ]file)", re.IGNORECASE)
INLINE_TIMESTAMP_RE = re.compile(r"(?P<value>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}|\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2})")
REPO_RELATIVE_PLAN_PATH_RE = re.compile(r"^docs/plans/[A-Za-z0-9][A-Za-z0-9_./-]*\.md$")
EXECUTION_QUEUE_HEADING_RE = re.compile(r"^\s*##\s+Execution queue\b", re.IGNORECASE)
CHILD_PLAN_MAP_HEADING_RE = re.compile(r"^\s*##\s+Child plan map\b", re.IGNORECASE)
SMALL_MODEL_READY_CHILD_HEADING_RE = re.compile(r"^\s*##\s+Small-model-ready child contract\b", re.IGNORECASE)
PLACEHOLDER_CHILD_VALUE_RE = re.compile(r"^(?:tbd|n/?a|none|null|-+)(?:\b|$)", re.IGNORECASE)
FILENAME_TS_RE = re.compile(r"^(?P<ts>\d{6}_\d{4})_")
MACHINE_AUTHORITY_DECISION_SCHEMA = "machine_authority_decision.v1"
MACHINE_AUTHORITY_DECISION_REQUIRED_STATUSES = frozenset(
    {
        "ready for planner",
        "planner intake",
        "planner finalize",
        "ready for coder",
        "coder intake",
        "in progress",
        "ready for review",
        "reviewer intake",
        "reviewer code review",
        "reviewer visual review",
        "ready for arch review",
        "architect arch review",
        "done",
        "superseded",
    }
)
MACHINE_AUTHORITY_DECISION_ARCHITECT_STATUSES = frozenset(
    {
        "architect initial draft",
        "architect draft",
        "ready for architect response",
        "architect response",
    }
)
MACHINE_AUTHORITY_DECISION_REF_REQUIRED_STATUSES = frozenset(
    {
        "planner finalize",
        "ready for coder",
        "coder intake",
        "in progress",
        "ready for review",
        "reviewer intake",
        "reviewer code review",
        "reviewer visual review",
        "ready for arch review",
        "architect arch review",
        "done",
        "superseded",
    }
)
MACHINE_AUTHORITY_DECISION_NA_REASONS = frozenset(
    {
        "no_machine_authority_change",
        "unchanged_structured_consumer",
        "docs_or_tests_only",
    }
)
MACHINE_AUTHORITY_DECISION_IMPACTS = frozenset(
    {"authorization", "routing", "mutation", "terminal"}
)
MACHINE_AUTHORITY_DECISION_FAILURE_KEYS = frozenset(
    {"missing", "malformed", "duplicate", "stale", "legacy"}
)
MACHINE_AUTHORITY_DECISION_LEGACY_CUTOVER_POLICY = {
    "kind": "implementation_snapshot_basename_floor",
    "legacy_behavior": "read_only_no_backfill",
    "authority_change_behavior": "post_cutover_successor",
    "snapshot_rule": (
        "implementation bundle materializes one fixed canonical plan-id floor strictly later than every "
        "docs/plans filename in its delivery-baseline tree"
    ),
}
MACHINE_AUTHORITY_DECISION_HANDOFF_POLICY = {"kind": "status_and_purpose_handoff"}
MACHINE_AUTHORITY_DECISION_ID_RE = re.compile(
    r"^mad-\d{6}-\d{4}(?:-[a-z0-9][a-z0-9-]*)?$"
)
MACHINE_AUTHORITY_DECISION_JSON_POINTER_RE = re.compile(
    r"^json_pointer:/(?:[^/~]|~[01])+(?:/(?:[^/~]|~[01])+)*$"
)
MACHINE_AUTHORITY_DECISION_SCHEMA_LOCATOR_RE = re.compile(
    r"^(?:sentinel|evidence_schema):[a-z][a-z0-9_.-]*\.v[0-9]+$"
)
SMALL_MODEL_HARD_FIELDS = (
    "Task outcome",
    "Local context bundle",
    "Mutable surfaces",
    "Read-only surfaces",
    "Forbidden scope",
    "Inputs from parent/predecessor",
    "Output to consumer",
    "Acceptance/proof lane",
    "Stop condition",
    "Expected reviewer lane",
)
SMALL_MODEL_WARNING_FIELDS = (
    "Runner suitability",
    "Task size/complexity",
    "Readiness notes",
)
SMALL_MODEL_FIELD_BY_NORM = {
    " ".join(field.lower().split()): field
    for field in (*SMALL_MODEL_HARD_FIELDS, *SMALL_MODEL_WARNING_FIELDS)
}
SMALL_MODEL_HARD_NA_ALLOWED_FIELDS = frozenset(
    {
        "Read-only surfaces",
        "Forbidden scope",
        "Inputs from parent/predecessor",
        "Expected reviewer lane",
    }
)
SMALL_MODEL_PLACEHOLDER_VALUE_RE = re.compile(
    r"^(?:`?\s*)?(?:tbd|todo|unconfirmed|unknown|none|null|-+)(?:\s*`?)?(?:\b|$)",
    re.IGNORECASE,
)
SMALL_MODEL_ANGLE_PLACEHOLDER_VALUE_RE = re.compile(r"^\s*`?\s*<[^>\n]+>\s*`?\s*$")
SMALL_MODEL_NA_VALUE_RE = re.compile(r"^\s*`?\s*n\s*/?\s*a\b", re.IGNORECASE)
SMALL_MODEL_NA_WITH_REASON_RE = re.compile(r"\bn\s*/?\s*a\b.*\bwhy\s*=", re.IGNORECASE)
SMALL_MODEL_VAGUE_VALUE_RE = re.compile(
    r"\b(?:as discussed|see parent|same as parent|chat memory|oral context|manager explains|later)\b|"
    r"\b(?:см\.?\s*parent|как обсудили|в чате|потом)\b",
    re.IGNORECASE,
)
PROMOTED_FROM_AUTHORITY_NOTE = "derived_read_only; source artifact is writable truth"
PROMOTED_FROM_REQUIRED_FIELDS = (
    "authority_note",
    "source_plan",
    "source_route_ref",
    "accepted_route",
    "promoted_artifact_kind",
    "promoted_artifact_ref",
    "queue_admission_at_acceptance",
    "runner_admission_at_acceptance",
)
QUEUE_ACTIVATION_REQUIRED_FIELDS = ("state", "source_ref", "reason")
SOURCE_ROUTE_REQUIRED_FIELDS = (
    "accepted_route",
    "promoted_artifact_kind",
    "promoted_artifact_ref",
    "queue_admission",
    "runner_admission",
)
SOURCE_ROUTE_ANALYSIS_FIELDS = (
    "source_analysis_plan",
    "source_analysis_pack_ref",
)
ANALYSIS_ROUTE_LIFECYCLE_BUDGET_KEYS = (
    "source_ref_floor",
    "route_iteration_limit",
    "needs_analysis_depth_cap",
    "current_needs_analysis_depth",
    "stop_owner",
    "exhaustion_action",
)
ANALYSIS_ROUTE_LIFECYCLE_DEFAULT_DEPTH_CAP = 2
ANALYSIS_ROUTE_LIFECYCLE_KV_RE = re.compile(
    r"\b(?P<key>[A-Za-z][A-Za-z0-9_-]*)\s*(?:=|:)\s*(?P<value>.*?)"
    r"(?=\s*(?:;|,\s*(?=[A-Za-z][A-Za-z0-9_-]*\s*(?:=|:))|\n|\||$))"
)
SOURCE_ROUTE_ENUM_FIELDS = {
    "accepted_route": "accepted_routes",
    "promoted_artifact_kind": "promoted_artifact_kinds",
    "queue_admission": "queue_admission",
    "runner_admission": "runner_admission",
}
PROMOTED_FROM_ENUM_FIELDS = {
    "accepted_route": "accepted_routes",
    "promoted_artifact_kind": "promoted_artifact_kinds",
    "queue_admission_at_acceptance": "queue_admission",
    "runner_admission_at_acceptance": "runner_admission",
}
FIXTURE_BACKED_SOURCE_ROUTES = frozenset({"developer_wave", "decomposition_wave"})
NON_EXECUTABLE_SOURCE_ROUTES = frozenset({"human_gate", "defer", "reject"})
NON_EXECUTABLE_ROUTE_EXPECTED_FIELDS = {
    "human_gate": {
        "promoted_artifact_kind": "owner_gate",
        "queue_admission": "needs_owner",
    },
    "defer": {
        "promoted_artifact_kind": "followup",
        "queue_admission": "not_queueable",
    },
    "reject": {
        "promoted_artifact_kind": "rejection_receipt",
        "queue_admission": "not_queueable",
    },
}
NON_EXECUTABLE_ROUTE_REVISIT_REQUIRED = frozenset({"human_gate", "defer"})
SUBJECT_IDENTITY_FIELD = "subject_identity"
DUPLICATE_OF_FIELD = "duplicate_of"
NON_EXECUTABLE_FUZZY_SUBJECT_RE = re.compile(
    r"\b(?:fuzzy(?:[-_ ]?match)?|near[-_ ]?match|approx(?:imate)?|similar|maybe|probably|"
    r"примерн|похож|неч[её]тк|около)\b",
    re.IGNORECASE,
)
NON_EXECUTABLE_DUPLICATE_HINT_RE = re.compile(r"\b(?:duplicate|duplicated|дубликат|дублиру)\b", re.IGNORECASE)
PROMOTED_ROUTE_ARTIFACT_ANCHOR = "promoted-route-artifact"
CURRENT_STATE_SCHEMA = "plan_current_state.v1"
CONTEXTUAL_UNAVAILABLE = "contextual_unavailable"
REQUIRED_MANAGER_MODES = frozenset({"manager-collab", "manager-custom-pipeline", "either"})
ACTUAL_MANAGER_MODES = ("manager-collab", "manager-custom-pipeline")


@dataclass(frozen=True)
class DecompositionChildIssue:
    line_no: int | None
    kind: str
    value: str
    message: str


@dataclass(frozen=True)
class DecompositionChildState:
    state: str
    reason: str
    concrete_child_paths: tuple[str, ...]
    expansion_source: str
    issues: tuple[DecompositionChildIssue, ...]
    # This tuple is intentionally not projected into OracleResult JSON.  It
    # carries the complete planning identity for strict-parent validation and
    # exact-bundle membership, while ``concrete_child_paths`` remains the
    # public bounded routing projection.
    canonical_planning_child_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class SmallModelReadinessFinding:
    child_path: str
    line_no: int | None
    field: str
    severity: str
    finding_kind: str
    value: str
    message: str
    blocks_queue: bool


@dataclass(frozen=True)
class SourceRouteCarrierIssue:
    severity: str
    field: str
    kind: str
    message: str


@dataclass(frozen=True)
class OwnerQuestionEvent:
    line_no: int
    qid: str
    state: str
    text: str
    canonical_text: str
    owner_scoped: bool


@dataclass(frozen=True)
class OwnerQuestionIssue:
    line_no: int
    kind: str
    text: str
    message: str


@dataclass(frozen=True)
class AnalysisRouteLifecycleState:
    state: str
    reason: str
    next_owner: str
    budget_status: str
    needs_analysis_depth_cap: str
    current_needs_analysis_depth: str
    stale_trigger_state: str


@dataclass(frozen=True)
class AnalysisPackAuthorityResolution:
    mode: str
    authority_text: str
    authority_path: Path | None
    truth_host: str
    error_token: str
    detail_category: str

    @property
    def is_valid(self) -> bool:
        return not self.error_token


@dataclass(frozen=True)
class ScopeExpansionState:
    carrier_state: str
    state: str
    target_contour: str
    source_ref: str
    reason: str
    classification_reason: str


@dataclass(frozen=True)
class AcceptedRedDisposition:
    terminal_disposition: str
    delivery_green: bool
    staging_policy: str
    durable_capture_required: bool
    successor_plan: str
    historical_review: str
    review_bundle_sha256: str
    reason: str


@dataclass(frozen=True)
class AcceptedRedDurableRefResult:
    state: str
    reason: str
    capture_commit: str = ""
    cleanup_commit: str = ""
    manifest: Mapping[str, object] | None = None
    cleanup: Mapping[str, object] | None = None
    targets: tuple[Mapping[str, object], ...] = ()
    routing: tuple[Mapping[str, object], ...] = ()
    recovery_contract: Mapping[str, object] | None = None
    recovery_contract_state: str = ""


@dataclass(frozen=True)
class AcceptedRedRecoveryContractRebind:
    recovery_revision: str
    recovery_review: str
    recovery_bundle_sha256: str
    recovery_targets: tuple[str, ...]
    binding_sha256: str


@dataclass(frozen=True)
class AcceptedRedSuccessorTopologyRebind:
    schema: str
    rebind_id: str
    source_plan: str
    source_draft_rule: str
    source_review: str
    source_review_bundle_sha256: str
    source_open_blockers: tuple[str, ...]
    source_scope_ref: str
    successor_plan: str
    successor_commit: str
    successor_plan_blob_oid: str
    successor_review: str
    successor_review_blob_oid: str
    successor_expected_parent: None
    successor_requires_source_in_depends_on: bool
    carrier_set_ref: str
    carrier_set_commit: str
    carrier_set_tree: str
    carrier_set_parent: str
    carrier_paths: tuple[str, ...]
    target_snapshot_ref: str
    target_snapshot_commit: str
    targets: tuple[Mapping[str, object], ...]
    entry_sha256: str


@dataclass(frozen=True)
class OracleResult:
    status_line: str
    status_value: str
    status_norm: str
    plan_type: str
    plan_type_norm: str
    planning_contour_marker: str
    planning_contour_role: str
    planning_contour_readback_state: str
    planning_contour_readback_reason: str
    scope_expansion_carrier_state: str
    scope_expansion_state: str
    scope_expansion_target_contour: str
    scope_expansion_source_ref: str
    scope_expansion_reason: str
    machine_authority_decision_state: str
    machine_authority_decision_reason: str
    machine_authority_decision_id: str
    machine_authority_decision_route: str
    machine_authority_decision_carrier_sha256: str
    machine_authority_decision_confirmation_state: str
    machine_authority_decision_ref_state: str
    machine_authority_decision_ref_reason: str
    terminal_disposition: str
    delivery_green: bool
    staging_policy: str
    durable_capture_required: bool
    accepted_red_successor_plan: str
    accepted_red_historical_review: str
    accepted_red_review_bundle_sha256: str
    terminal_disposition_reason: str
    source_route_state: str
    source_route_accepted_route: str
    source_route_promoted_artifact_kind: str
    source_route_promoted_artifact_ref: str
    source_route_queue_admission: str
    source_route_runner_admission: str
    source_route_non_executable_carrier_state: str
    source_route_non_executable_carrier_reason: str
    analysis_route_lifecycle_state: str
    analysis_route_lifecycle_reason: str
    analysis_route_lifecycle_next_owner: str
    analysis_route_lifecycle_budget_status: str
    analysis_route_lifecycle_needs_analysis_depth_cap: str
    analysis_route_lifecycle_current_needs_analysis_depth: str
    analysis_route_lifecycle_stale_trigger_state: str
    promoted_from_state: str
    promoted_from_authority_note: str
    promoted_from_accepted_route: str
    promoted_from_promoted_artifact_kind: str
    promoted_from_promoted_artifact_ref: str
    promoted_from_queue_admission: str
    promoted_from_runner_admission: str
    queue_activation_carrier_state: str
    queue_activation_state: str
    pending_activation: bool
    pending_activation_reason: str
    review_readback_state: str
    review_readback_reason: str
    route_guard_triggered: bool
    route_guard_kind: str
    route_guard_reason: str
    route_guard_next_owner: str
    owner_qna_readback_state: str
    owner_qna_readback_reason: str
    open_owner_questions: tuple[OwnerQuestionEvent, ...]
    owner_qna_issues: tuple[OwnerQuestionIssue, ...]
    runtime_class: str
    runtime_class_reason: str
    queue_closeout_ready: bool
    queue_closeout_kind: str
    queue_closeout_reason: str
    decomposition_child_state: str
    decomposition_child_reason: str
    decomposition_child_paths: tuple[str, ...]
    decomposition_child_issues: tuple[DecompositionChildIssue, ...]
    small_model_ready_child: str
    small_model_readiness_state: str
    small_model_readiness_findings: tuple[SmallModelReadinessFinding, ...]
    captured_plan_text: str
    plan_mtime: str
    plan_size: int
    plan_hash: str
    oracle_run_id: str


def _iso_utc(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _status_norm_from_line(line: str) -> str:
    check = line.lstrip()
    if check.startswith(">"):
        check = check[1:].lstrip()
    if not check.startswith("**Status:**"):
        return ""
    value = check[len("**Status:**") :].strip()
    return " ".join(value.lower().split())


OWNER_QNA_ID_RE = re.compile(r"\bid=(Q\d+)\b", re.IGNORECASE)
OWNER_QNA_STATE_RE = re.compile(r"\bstatus=(open|closed|superseded)\b", re.IGNORECASE)
OWNER_QNA_OWNER_RE = re.compile(r"\bto\s*=\s*Owner\b", re.IGNORECASE)
OWNER_QNA_ARROW_OWNER_RE = re.compile(r"\([^)]*(?:->|→)\s*Owner\b", re.IGNORECASE)
OWNER_QNA_LEGACY_ID_RE = re.compile(r"^\s*[-*]\s*\[[^\]]+\]\s*\((?P<id>[A-Z]\d+)\s*,", re.IGNORECASE)
OWNER_QNA_NEEDS_OWNER_NO_RE = re.compile(r"\bneeds_owner\s*=\s*no\b", re.IGNORECASE)
OWNER_QNA_CARRIER_RE = re.compile(r"^\s*[-*]\s*\[\d{4}-\d{2}-\d{2}[^\]]+\]")
INLINE_CODE_SPAN_RE = re.compile(r"`[^`]*`")
OWNER_QNA_SECTION_HEADING_RE = re.compile(
    r"^##\s+Q&A log(?:\s*\([^)]*\))?\s*$",
    re.IGNORECASE,
)


def _owner_qna_id(scan_line: str) -> str:
    if id_match := OWNER_QNA_ID_RE.search(scan_line):
        return id_match.group(1).upper()
    if legacy_match := OWNER_QNA_LEGACY_ID_RE.search(scan_line):
        return legacy_match.group("id").upper()
    return ""


def _closed_owner_no_question(scan_line: str, state: str) -> bool:
    return (
        state == "closed"
        and OWNER_QNA_NEEDS_OWNER_NO_RE.search(scan_line) is not None
        and "NO QUESTIONS" in scan_line.upper()
    )


def _owner_qna_section_lines(
    plan_text: str,
) -> tuple[list[tuple[int, str]], list[OwnerQuestionIssue]]:
    """Return canonical Q&A rows while treating fenced examples as opaque."""

    lines = plan_text.splitlines()
    heading_indices = _machine_authority_top_level_heading_indices(lines)
    section_starts = [
        index
        for index in heading_indices
        if OWNER_QNA_SECTION_HEADING_RE.fullmatch(lines[index])
    ]
    if not section_starts:
        return [], []
    if len(section_starts) != 1:
        line_no = section_starts[1] + 1
        return [], [
            OwnerQuestionIssue(
                line_no=line_no,
                kind="ambiguous_owner_qna_section",
                text=lines[section_starts[1]].strip(),
                message="expected exactly one canonical ## Q&A log section",
            )
        ]
    start = section_starts[0] + 1
    end = next((index for index in heading_indices if index >= start), len(lines))
    return list(enumerate(lines[start:end], start=start + 1)), []


def owner_qna_events_and_issues(plan_text: str) -> tuple[list[OwnerQuestionEvent], list[OwnerQuestionIssue]]:
    events: list[OwnerQuestionEvent] = []
    qna_lines, issues = _owner_qna_section_lines(plan_text)
    for line_no, line in qna_lines:
        scan_line = INLINE_CODE_SPAN_RE.sub("", line)
        qid = _owner_qna_id(scan_line)
        state_match = OWNER_QNA_STATE_RE.search(scan_line)
        timestamped_carrier = OWNER_QNA_CARRIER_RE.search(scan_line) is not None
        owner_scoped = (
            OWNER_QNA_OWNER_RE.search(scan_line) is not None
            or OWNER_QNA_ARROW_OWNER_RE.search(scan_line) is not None
        )
        owner_carrier = timestamped_carrier and owner_scoped
        state = state_match.group(1).lower() if state_match else ""
        if timestamped_carrier and qid and state_match:
            events.append(
                OwnerQuestionEvent(
                    line_no=line_no,
                    qid=qid,
                    state=state,
                    text=line.strip(),
                    canonical_text=scan_line.strip(),
                    owner_scoped=owner_scoped,
                )
            )
            continue
        if owner_carrier and (qid or state_match):
            if state and not qid and _closed_owner_no_question(scan_line, state):
                continue
            missing = []
            if not qid:
                missing.append("id=Qn")
            if not state_match:
                missing.append("status=open|closed|superseded")
            issues.append(
                OwnerQuestionIssue(
                    line_no=line_no,
                    kind="malformed_owner_qna",
                    text=line.strip(),
                    message="Owner Q&A line is missing " + " and ".join(missing),
                )
            )
    return events, issues


def latest_owner_qna_events(events: Iterable[OwnerQuestionEvent]) -> dict[str, OwnerQuestionEvent]:
    events_by_line = list(events)
    owner_question_ids = {event.qid for event in events_by_line if event.owner_scoped}
    latest: dict[str, OwnerQuestionEvent] = {}
    for event in events_by_line:
        if event.qid not in owner_question_ids:
            continue
        latest[event.qid] = event
    return latest


def open_owner_qna_events(events: Iterable[OwnerQuestionEvent]) -> list[OwnerQuestionEvent]:
    open_events = [
        event
        for event in latest_owner_qna_events(events).values()
        if event.state == "open"
    ]
    return sorted(open_events, key=lambda event: event.line_no)


def owner_qna_readback(plan_text: str) -> tuple[str, str, tuple[OwnerQuestionEvent, ...], tuple[OwnerQuestionIssue, ...]]:
    events, issues = owner_qna_events_and_issues(plan_text)
    if issues:
        return (
            "blocked",
            "malformed_owner_qna_entries",
            tuple(open_owner_qna_events(events)),
            tuple(issues),
        )
    open_questions = tuple(open_owner_qna_events(events))
    if open_questions:
        return ("open", "open_owner_questions", open_questions, ())
    return ("clean", "no_open_owner_questions", (), ())


def _scan_status_line(plan_text: str) -> tuple[int, str]:
    matches: list[tuple[int, str]] = []
    for idx, line in enumerate(plan_text.splitlines(), start=1):
        check = line.lstrip()
        if check.startswith(">"):
            # Allow blockquoted headings to terminate the header scan, but do not
            # treat blockquoted **Status:** as the canonical header status.
            unquoted = check[1:].lstrip()
            if unquoted.startswith("##"):
                break
            continue
        if check.startswith("##"):
            break
        if check.startswith("**Status:**"):
            matches.append((idx, line))

    if len(matches) != 1:
        details = "\n".join([f"{n}:{l}" for n, l in matches])
        raise ValueError(
            f"Plan hygiene: expected exactly 1 header **Status:** line, got {len(matches)}"
            + (f"\n{details}" if details else "")
        )

    line_no, raw_line = matches[0]
    if "|" in raw_line:
        raise ValueError("Plan hygiene: template placeholder **Status:** detected (contains '|')")
    return line_no, raw_line


def _scan_plan_type_line(plan_text: str) -> tuple[int | None, str | None]:
    matches: list[tuple[int, str]] = []
    for idx, line in enumerate(plan_text.splitlines(), start=1):
        check = line.lstrip()
        if check.startswith(">"):
            unquoted = check[1:].lstrip()
            if unquoted.startswith("##"):
                break
            continue
        if check.startswith("##"):
            break
        if check.startswith("**Plan type:**"):
            matches.append((idx, line))

    if len(matches) > 1:
        details = "\n".join([f"{n}:{l}" for n, l in matches])
        raise ValueError(
            f"Plan hygiene: expected at most 1 header **Plan type:** line, got {len(matches)}\n{details}"
        )
    if not matches:
        return None, None
    return matches[0]


def _normalize_value(value: str) -> str:
    return " ".join(value.lower().split())


def _header_lines(plan_text: str) -> list[str]:
    lines: list[str] = []
    for line in plan_text.splitlines():
        check = line.lstrip()
        if check.startswith(">"):
            unquoted = check[1:].lstrip()
            if unquoted.startswith("##"):
                break
            continue
        if check.startswith("##"):
            break
        lines.append(line)
    return lines


def parse_plan_meta(plan_text: str) -> dict[str, object]:
    in_json = False
    buf: list[str] = []
    for line in plan_text.splitlines():
        if not in_json and re.match(r"^\s*```json\s*$", line, re.IGNORECASE):
            in_json = True
            buf = []
            continue
        if in_json and re.match(r"^\s*```\s*$", line):
            block = "\n".join(buf).strip()
            in_json = False
            buf = []
            if "plan_meta" not in block:
                continue
            try:
                parsed = json.loads(block)
            except json.JSONDecodeError:
                continue
            meta = parsed.get("plan_meta")
            if isinstance(meta, dict):
                return meta
        if in_json:
            buf.append(line)
    return {}


class MachineAuthorityDecisionError(ValueError):
    """The post-cutover machine-authority admission carrier is invalid."""

    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


@dataclass(frozen=True)
class StrictPlanMetaJsonResult:
    state: str
    reason_code: str
    reason: str
    line_no: int | None
    plan_meta: Mapping[str, object] | None
    has_machine_authority_marker: bool


@dataclass(frozen=True)
class MachineAuthorityDecisionReadback:
    state: str
    reason_code: str
    reason: str
    decision_id: str
    route: str
    carrier_sha256: str
    confirmation_state: str
    applicability: str
    ref_state: str
    ref_reason: str
    route_guard_required: bool


_TOP_LEVEL_META_HEADING_RE = re.compile(
    r"^ {0,3}##[ \t]+Meta(?:[ \t]*\([^)]*\))?(?:[ \t]+#+)?[ \t]*$",
    re.IGNORECASE,
)
_TOP_LEVEL_HEADING_RE = re.compile(r"^ {0,3}##(?:[ \t]|$)")
_JSON_FENCE_START_RE = re.compile(r"^ {0,3}```json[ \t]*$", re.IGNORECASE)
_JSON_FENCE_END_RE = re.compile(r"^ {0,3}```[ \t]*$")
_MARKDOWN_FENCE_RE = re.compile(r"^ {0,3}(?P<marker>`{3,}|~{3,})")
_MACHINE_AUTHORITY_QNA_DIRECTION_RE = re.compile(
    r"^\s*[-*]\s*\[\d{4}-\d{2}-\d{2}[^\]]+\]\s*"
    r"\((?P<from>Architect|Owner)\s*(?:->|→)\s*(?P<to>Owner|Architect)\s*,(?P<body>[^)]*)\)(?P<tail>.*)$",
    re.IGNORECASE,
)
_MACHINE_AUTHORITY_QNA_DIRECTION_TUPLE_RE = re.compile(
    r"\((?:Architect|Owner)\s*(?:->|→)\s*(?:Owner|Architect)\s*,[^)]*\)",
    re.IGNORECASE,
)


def _machine_authority_reject_duplicate_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise MachineAuthorityDecisionError(
                "duplicate_json_key",
                f"duplicate JSON key `{key}` in strict machine-authority carrier",
            )
        result[key] = value
    return result


def _machine_authority_reject_nonfinite(value: str) -> object:
    raise MachineAuthorityDecisionError(
        "nonfinite_json_value",
        f"non-finite JSON value `{value}` is forbidden in strict machine-authority carrier",
    )


def _machine_authority_load_json(text: str) -> object:
    try:
        return json.loads(
            text,
            object_pairs_hook=_machine_authority_reject_duplicate_keys,
            parse_constant=_machine_authority_reject_nonfinite,
        )
    except MachineAuthorityDecisionError:
        raise
    except json.JSONDecodeError as exc:
        raise MachineAuthorityDecisionError(
            "malformed_json",
            f"malformed strict machine-authority JSON: {exc.msg}",
        ) from exc


def _machine_authority_top_level_heading_indices(lines: Sequence[str]) -> list[int]:
    """Return H2 headings while treating fenced examples as opaque prose."""

    headings: list[int] = []
    active_marker = ""
    for index, line in enumerate(lines):
        fence = _MARKDOWN_FENCE_RE.match(line)
        if active_marker:
            if (
                fence is not None
                and fence.group("marker")[0] == active_marker[0]
                and len(fence.group("marker")) >= len(active_marker)
                and not line[fence.end() :].strip()
            ):
                active_marker = ""
            continue
        if fence is not None:
            marker = fence.group("marker")
            if marker[0] != "`" or "`" not in line[fence.end() :]:
                active_marker = marker
                continue
        if _TOP_LEVEL_HEADING_RE.match(line):
            headings.append(index)
    return headings


def _machine_authority_raw_candidate_marker_seen(raw: str) -> bool:
    """Recognize a token-level root ``plan_meta`` decision key in invalid JSON.

    Strict decoding remains authoritative for valid JSON.  This narrow prefix
    scan is only used after a decoding failure, so a malformed value following
    an actual ``plan_meta.machine_authority_decision`` key remains fail-closed
    without turning unrelated malformed JSON into a carrier.
    """

    decoder = json.JSONDecoder()
    length = len(raw)

    def skip_whitespace(index: int) -> int:
        while index < length and raw[index] in " \t\r\n":
            index += 1
        return index

    def decode_string(index: int) -> tuple[str, int] | None:
        if index >= length or raw[index] != '"':
            return None
        cursor = index + 1
        while cursor < length:
            character = raw[cursor]
            if character == "\\":
                cursor += 2
                continue
            if character == '"':
                try:
                    decoded = json.loads(raw[index : cursor + 1])
                except (TypeError, ValueError):
                    return None
                return decoded, cursor + 1
            cursor += 1
        return None

    def recover_to_member_boundary(index: int) -> int | None:
        """Skip one malformed value without losing later sibling-key evidence.

        Recovery is deliberately limited to a comma or object end at the same
        object depth.  Nested objects and strings are skipped as values, so a
        nested/decoy ``machine_authority_decision`` never becomes a direct
        ``plan_meta`` member merely because an earlier sibling is malformed.
        """

        nested_depth = 0
        while index < length:
            character = raw[index]
            if character == '"':
                decoded = decode_string(index)
                if decoded is None:
                    return None
                _, index = decoded
                continue
            if character in "{[":
                nested_depth += 1
            elif character in "}]":
                if nested_depth == 0:
                    return index
                nested_depth -= 1
            elif character == "," and nested_depth == 0:
                return index
            index += 1
        return None

    def scan_object(index: int, *, is_plan_meta: bool) -> tuple[bool, int | None]:
        if index >= length or raw[index] != "{":
            return False, None
        index = skip_whitespace(index + 1)
        while index < length:
            if raw[index] == "}":
                return False, index + 1
            decoded_key = decode_string(index)
            if decoded_key is None:
                return False, None
            key, index = decoded_key
            index = skip_whitespace(index)
            if index >= length or raw[index] != ":":
                return False, None
            index = skip_whitespace(index + 1)
            if is_plan_meta and key == "machine_authority_decision":
                return True, index
            if not is_plan_meta and key == "plan_meta" and index < length and raw[index] == "{":
                found, next_index = scan_object(index, is_plan_meta=True)
                if found:
                    return True, next_index
                if next_index is None:
                    return False, None
                index = next_index
            else:
                try:
                    _, index = decoder.raw_decode(raw, index)
                except (TypeError, ValueError):
                    recovered = recover_to_member_boundary(index)
                    if recovered is None:
                        return False, None
                    index = recovered
            index = skip_whitespace(index)
            if index < length and raw[index] == ",":
                index = skip_whitespace(index + 1)
                continue
            if index < length and raw[index] == "}":
                return False, index + 1
            return False, None
        return False, None

    start = skip_whitespace(0)
    if start >= length or raw[start] != "{":
        return False
    found, _ = scan_object(start, is_plan_meta=False)
    return found


def _machine_authority_meta_candidate_marker_seen(
    lines: Sequence[str],
    heading_indices: Sequence[int],
    section_starts: Sequence[int],
) -> bool:
    """Return whether actual Meta sections contain fail-closed decision evidence."""

    for section_start in section_starts:
        start = section_start + 1
        end = next((index for index in heading_indices if index >= start), len(lines))
        in_json = False
        buf: list[str] = []
        for line in lines[start:end]:
            if not in_json and _JSON_FENCE_START_RE.fullmatch(line):
                in_json = True
                buf = []
                continue
            if in_json and _JSON_FENCE_END_RE.fullmatch(line):
                raw = "\n".join(buf).strip()
                in_json = False
                buf = []
                try:
                    parsed = _machine_authority_load_json(raw)
                except MachineAuthorityDecisionError:
                    if _machine_authority_raw_candidate_marker_seen(raw):
                        return True
                    continue
                if not isinstance(parsed, Mapping):
                    continue
                plan_meta = parsed.get("plan_meta")
                if isinstance(plan_meta, Mapping) and "machine_authority_decision" in plan_meta:
                    return True
                continue
            if in_json:
                buf.append(line)
        if in_json:
            if _machine_authority_raw_candidate_marker_seen("\n".join(buf)):
                return True
    return False


def strict_plan_meta_json(plan_text: str) -> StrictPlanMetaJsonResult:
    """Read the sole top-level Meta carrier without touching prose/example JSON.

    This intentionally differs from ``parse_plan_meta``.  The latter remains a
    legacy compatibility reader for existing generic consumers; this function
    is the one shared source for machine-authority admission only.
    """

    lines = plan_text.splitlines()
    heading_indices = _machine_authority_top_level_heading_indices(lines)
    section_starts = [index for index in heading_indices if _TOP_LEVEL_META_HEADING_RE.fullmatch(lines[index])]
    if len(section_starts) != 1:
        return StrictPlanMetaJsonResult(
            "invalid",
            "meta_section_ambiguous",
            f"expected exactly one top-level ## Meta section, got {len(section_starts)}",
            None,
            None,
            _machine_authority_meta_candidate_marker_seen(lines, heading_indices, section_starts),
        )

    start = section_starts[0] + 1
    end = next((index for index in heading_indices if index >= start), len(lines))
    in_json = False
    fence_line = 0
    buf: list[str] = []
    candidates: list[tuple[int, Mapping[str, object]]] = []
    marker_seen = False
    for line_no, line in enumerate(lines[start:end], start=start + 1):
        if not in_json and _JSON_FENCE_START_RE.fullmatch(line):
            in_json = True
            fence_line = line_no
            buf = []
            continue
        if in_json and _JSON_FENCE_END_RE.fullmatch(line):
            raw = "\n".join(buf).strip()
            in_json = False
            buf = []
            try:
                parsed = _machine_authority_load_json(raw)
            except MachineAuthorityDecisionError as exc:
                return StrictPlanMetaJsonResult(
                    "invalid",
                    exc.reason_code,
                    f"line {fence_line}: {exc}",
                    fence_line,
                    None,
                    True,
                )
            if not isinstance(parsed, Mapping) or "plan_meta" not in parsed:
                continue
            plan_meta = parsed.get("plan_meta")
            if not isinstance(plan_meta, Mapping):
                return StrictPlanMetaJsonResult(
                    "invalid",
                    "plan_meta_not_object",
                    f"line {fence_line}: root plan_meta must be a JSON object",
                    fence_line,
                    None,
                    True,
                )
            marker_seen = marker_seen or "machine_authority_decision" in plan_meta
            candidates.append((fence_line, plan_meta))
            continue
        if in_json:
            buf.append(line)

    if in_json:
        return StrictPlanMetaJsonResult(
            "invalid",
            "unterminated_meta_json",
            f"line {fence_line}: unterminated JSON fence in top-level ## Meta",
            fence_line,
            None,
            True,
        )
    if len(candidates) != 1:
        return StrictPlanMetaJsonResult(
            "invalid",
            "plan_meta_carrier_ambiguous",
            f"expected exactly one root plan_meta JSON fence in top-level ## Meta, got {len(candidates)}",
            candidates[0][0] if candidates else None,
            None,
            marker_seen,
        )
    line_no, plan_meta = candidates[0]
    return StrictPlanMetaJsonResult(
        "valid",
        "ok",
        "sole strict top-level Meta carrier is valid",
        line_no,
        plan_meta,
        "machine_authority_decision" in plan_meta,
    )


def _machine_authority_normalize_json(value: object) -> object:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, list):
        return [_machine_authority_normalize_json(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _machine_authority_normalize_json(item) for key, item in value.items()}
    return value


def machine_authority_decision_sha256(decision: Mapping[str, object]) -> str:
    """Return the canonical digest used by active and N-A derived refs."""

    core = {key: value for key, value in decision.items() if key != "owner_confirmation"}
    canonical = json.dumps(
        _machine_authority_normalize_json(core),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _machine_authority_require_exact_keys(
    value: Mapping[str, object],
    expected: set[str],
    *,
    label: str,
) -> None:
    actual = set(value)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing or unknown:
        detail: list[str] = []
        if missing:
            detail.append("missing=" + ",".join(missing))
        if unknown:
            detail.append("unknown=" + ",".join(unknown))
        raise MachineAuthorityDecisionError(
            "unknown_or_missing_keys",
            f"{label} exact key set failed ({'; '.join(detail)})",
        )


def _machine_authority_require_nonempty_string(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MachineAuthorityDecisionError(
            "invalid_string",
            f"{label} must be a non-empty string",
        )
    if value != value.strip():
        raise MachineAuthorityDecisionError(
            "invalid_string",
            f"{label} must not include surrounding whitespace",
        )
    return value


def _machine_authority_require_unique_strings(value: object, *, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise MachineAuthorityDecisionError("invalid_string_array", f"{label} must be a non-empty array")
    values = [_machine_authority_require_nonempty_string(item, label=f"{label}[]") for item in value]
    normalized_values = [unicodedata.normalize("NFC", item) for item in values]
    if len(normalized_values) != len(set(normalized_values)):
        raise MachineAuthorityDecisionError("duplicate_array_value", f"{label} must be unique")
    if normalized_values != sorted(normalized_values):
        raise MachineAuthorityDecisionError("unsorted_array_value", f"{label} must be sorted")
    return normalized_values


def _machine_authority_repo_relative_path(value: object, *, label: str) -> str:
    path = _machine_authority_require_nonempty_string(value, label=label)
    pure = PurePosixPath(path)
    if pure.is_absolute() or ".." in pure.parts or "\\" in path or not path.startswith("docs/"):
        raise MachineAuthorityDecisionError(
            "invalid_repo_path",
            f"{label} must be a normalized repo-relative docs/ path",
        )
    if pure.as_posix() != path:
        raise MachineAuthorityDecisionError(
            "invalid_repo_path",
            f"{label} must be normalized without dot segments",
        )
    return path


def _machine_authority_plan_path(plan_path: Path) -> tuple[Path, str]:
    root = _repo_root_for_plan_path(plan_path)
    try:
        rel = plan_path.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        rel = plan_path.as_posix()
    return root, rel


def _machine_authority_absent_carrier_readback(
    plan_path: Path, status_norm: str,
) -> MachineAuthorityDecisionReadback:
    """Decide carrier omission from lifecycle purpose, never filename age."""

    if plan_path.name == "_template.md":
        reason_code = "template_no_carrier"
    elif status_norm == "architect initial draft":
        reason_code = "initial_architect_draft_no_carrier"
    elif status_norm in MACHINE_AUTHORITY_DECISION_ARCHITECT_STATUSES:
        reason_code = "architect_owned_no_carrier"
    elif status_norm in MACHINE_AUTHORITY_DECISION_REQUIRED_STATUSES:
        return MachineAuthorityDecisionReadback(
            "missing", "missing_required_carrier",
            "downstream handoff requires machine_authority_decision",
            "", "", "", "", "", "missing",
            "no current-plan tagged ref can exist without a carrier", True,
        )
    else:
        reason_code = "carrier_not_required_before_downstream_handoff"
    return MachineAuthorityDecisionReadback(
        "not_required", reason_code,
        "machine-authority carrier is not required before downstream handoff",
        "", "", "", "", "", "not_required",
        "no tagged ref is required without a carrier before downstream handoff", False,
    )


def _machine_authority_validate_authority_host(
    value: object,
    *,
    plan_rel: str,
) -> None:
    if not isinstance(value, Mapping):
        raise MachineAuthorityDecisionError("authority_host_invalid", "authority_host must be an object")
    _machine_authority_require_exact_keys(
        value,
        {"repo", "path", "locator"},
        label="recommended_route.authority_host",
    )
    if value.get("repo") != "current":
        raise MachineAuthorityDecisionError("authority_host_invalid", "authority_host.repo must equal current")
    if _machine_authority_repo_relative_path(value.get("path"), label="authority_host.path") != plan_rel:
        raise MachineAuthorityDecisionError(
            "authority_host_invalid",
            "authority_host.path must be the current plan path",
        )
    locator = _machine_authority_require_nonempty_string(value.get("locator"), label="authority_host.locator")
    if not (
        MACHINE_AUTHORITY_DECISION_JSON_POINTER_RE.fullmatch(locator)
        or MACHINE_AUTHORITY_DECISION_SCHEMA_LOCATOR_RE.fullmatch(locator)
    ):
        raise MachineAuthorityDecisionError(
            "authority_locator_invalid",
            "authority_host.locator must be an exact JSON pointer or schema locator",
        )
def _machine_authority_validate_grammar_contour(
    value: object,
    *,
    authority_host: Mapping[str, object],
    plan_path: Path,
    plan_rel: str,
    decision_id: str,
    origin_chain: frozenset[str],
) -> None:
    if not isinstance(value, Mapping):
        raise MachineAuthorityDecisionError("grammar_contour_invalid", "grammar_contour must be an object")
    _machine_authority_require_exact_keys(
        value,
        {
            "contour_origin_plan",
            "contour_origin_decision_id",
            "grammar_contour_id",
            "parser_owner",
            "parser_or_library",
            "axes",
            "proof_matrix_ref",
            "budget_policy",
            "exit_rule",
        },
        label="recommended_route.grammar_contour",
    )
    try:
        origin_plan = _machine_authority_repo_relative_path(
            value.get("contour_origin_plan"), label="grammar_contour.contour_origin_plan"
        )
    except MachineAuthorityDecisionError as exc:
        raise MachineAuthorityDecisionError("grammar_contour_invalid", "grammar contour origin plan is invalid") from exc
    origin_id = _machine_authority_require_nonempty_string(
        value.get("contour_origin_decision_id"), label="grammar_contour.contour_origin_decision_id"
    )
    if not REPO_RELATIVE_PLAN_PATH_RE.fullmatch(origin_plan) or not MACHINE_AUTHORITY_DECISION_ID_RE.fullmatch(origin_id):
        raise MachineAuthorityDecisionError("grammar_contour_invalid", "grammar contour origin decision id is invalid")
    root, _ = _machine_authority_plan_path(plan_path)
    if origin_plan == plan_rel:
        if origin_id != decision_id:
            raise MachineAuthorityDecisionError(
                "grammar_contour_invalid",
                "grammar contour self-origin does not match the current admission decision",
            )
    else:
        origin_path = root / origin_plan
        if not origin_path.is_file():
            raise MachineAuthorityDecisionError("grammar_contour_invalid", "grammar contour origin plan is not materialized")
        try:
            origin_text = origin_path.read_text(encoding="utf-8")
            origin_readback = machine_authority_decision_readback(
                origin_path,
                plan_text=origin_text,
                _grammar_origin_chain=origin_chain | {plan_rel},
            )
            origin_meta = strict_plan_meta_json(origin_text)
        except (OSError, UnicodeDecodeError) as exc:
            raise MachineAuthorityDecisionError(
                "grammar_contour_invalid",
                f"grammar contour origin plan cannot be validated: {exc}",
            ) from exc
        if (
            origin_readback.state != "frozen_confirmed"
            or origin_readback.reason_code != "ok"
            or origin_readback.decision_id != origin_id
            or origin_meta.state != "valid"
            or origin_meta.plan_meta is None
        ):
            raise MachineAuthorityDecisionError(
                "grammar_contour_invalid",
                "grammar contour origin does not bind a validated first-admission decision",
            )
        origin_decision = origin_meta.plan_meta.get("machine_authority_decision")
        origin_route = origin_decision.get("recommended_route") if isinstance(origin_decision, Mapping) else None
        origin_contour = origin_route.get("grammar_contour") if isinstance(origin_route, Mapping) else None
        if (
            not isinstance(origin_route, Mapping)
            or origin_route.get("kind") != "bounded_grammar"
            or not isinstance(origin_contour, Mapping)
            or origin_contour.get("contour_origin_plan") != origin_plan
            or origin_contour.get("contour_origin_decision_id") != origin_id
        ):
            raise MachineAuthorityDecisionError(
                "grammar_contour_invalid",
                "grammar contour origin is not a self-bound first-admission contour",
            )
    parser_owner = _machine_authority_require_nonempty_string(
        value.get("parser_owner"), label="grammar_contour.parser_owner"
    )
    parser_or_library = _machine_authority_require_nonempty_string(
        value.get("parser_or_library"), label="grammar_contour.parser_or_library"
    )
    if parser_owner.lower() in {"ad_hoc", "tbd", "infer_from_prose"} or parser_or_library.lower() in {
        "ad_hoc",
        "tbd",
        "infer_from_prose",
    }:
        raise MachineAuthorityDecisionError("grammar_contour_invalid", "grammar parser owner/library is a placeholder")
    raw_axes = value.get("axes")
    if not isinstance(raw_axes, list) or not raw_axes:
        raise MachineAuthorityDecisionError("grammar_contour_invalid", "grammar_contour.axes must be non-empty")
    axes: list[dict[str, str]] = []
    axis_ids: list[str] = []
    for index, axis in enumerate(raw_axes):
        if not isinstance(axis, Mapping):
            raise MachineAuthorityDecisionError("grammar_contour_invalid", f"grammar_contour.axes[{index}] must be an object")
        _machine_authority_require_exact_keys(axis, {"axis_id", "description"}, label=f"grammar_contour.axes[{index}]")
        axis_id = _machine_authority_require_nonempty_string(axis.get("axis_id"), label=f"grammar_contour.axes[{index}].axis_id")
        description = _machine_authority_require_nonempty_string(axis.get("description"), label=f"grammar_contour.axes[{index}].description")
        axis_ids.append(axis_id)
        axes.append({"axis_id": axis_id, "description": description})
    normalized_axis_ids = [unicodedata.normalize("NFC", axis_id) for axis_id in axis_ids]
    if len(normalized_axis_ids) != len(set(normalized_axis_ids)) or normalized_axis_ids != sorted(normalized_axis_ids):
        raise MachineAuthorityDecisionError("grammar_contour_invalid", "grammar_contour.axes must be sorted and unique")
    proof_matrix_ref = _machine_authority_require_nonempty_string(
        value.get("proof_matrix_ref"), label="grammar_contour.proof_matrix_ref"
    )
    if not re.fullmatch(r"docs/(?:plans|code_drafts)/[A-Za-z0-9_./-]+\.md#[A-Za-z][A-Za-z0-9 _./-]*", proof_matrix_ref):
        raise MachineAuthorityDecisionError("grammar_contour_invalid", "grammar_contour.proof_matrix_ref must be an exact plan/draft section ref")
    proof_rel, proof_section = proof_matrix_ref.split("#", 1)
    try:
        proof_rel = _machine_authority_repo_relative_path(
            proof_rel,
            label="grammar_contour.proof_matrix_ref",
        )
    except MachineAuthorityDecisionError as exc:
        raise MachineAuthorityDecisionError("grammar_contour_invalid", "grammar contour proof matrix path is invalid") from exc
    proof_path = root / proof_rel
    if not proof_path.is_file():
        raise MachineAuthorityDecisionError("grammar_contour_invalid", "grammar contour proof matrix file is not materialized")
    try:
        proof_lines = proof_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise MachineAuthorityDecisionError(
            "grammar_contour_invalid",
            f"grammar contour proof matrix cannot be read: {exc}",
        ) from exc
    if not any(proof_lines[index][2:].strip() == proof_section for index in _machine_authority_top_level_heading_indices(proof_lines)):
        raise MachineAuthorityDecisionError("grammar_contour_invalid", "grammar contour proof matrix section is not materialized")
    if value.get("budget_policy") != "same_contract_once_total":
        raise MachineAuthorityDecisionError("grammar_contour_invalid", "grammar_contour.budget_policy is invalid")
    if value.get("exit_rule") != "structured_successor_or_literal_de_scope":
        raise MachineAuthorityDecisionError("grammar_contour_invalid", "grammar_contour.exit_rule is invalid")
    identity = {
        "schema_version": "grammar_contour_identity.v1",
        "contour_origin_plan": origin_plan,
        "contour_origin_decision_id": origin_id,
        "authority_host": dict(authority_host),
        "parser_owner": parser_owner,
        "parser_or_library": parser_or_library,
        "axes": axes,
        "proof_matrix_ref": proof_matrix_ref,
        "budget_policy": "same_contract_once_total",
        "exit_rule": "structured_successor_or_literal_de_scope",
    }
    expected_id = "gc_" + hashlib.sha256(
        json.dumps(
            _machine_authority_normalize_json(identity),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    if value.get("grammar_contour_id") != expected_id:
        raise MachineAuthorityDecisionError("grammar_contour_invalid", "grammar_contour_id does not match canonical identity")


def _machine_authority_qna_lifecycle(plan_text: str, question_ref: str) -> None:
    events, issues = owner_qna_events_and_issues(plan_text)
    if issues:
        raise MachineAuthorityDecisionError(
            "owner_qna_lifecycle_invalid",
            "machine-authority confirmation requires one unambiguous canonical Q&A section",
        )
    if open_owner_qna_events(events):
        raise MachineAuthorityDecisionError(
            "owner_qna_lifecycle_invalid",
            "machine-authority confirmation requires a clean generic Owner Q&A readback",
        )
    questions: list[int] = []
    answers: list[int] = []
    for event in events:
        if event.qid != question_ref:
            continue
        match = _MACHINE_AUTHORITY_QNA_DIRECTION_RE.match(event.canonical_text)
        if match is None:
            raise MachineAuthorityDecisionError(
                "owner_qna_lifecycle_invalid",
                "machine-authority Q&A direction is invalid",
            )
        body = match.group("body")
        id_matches = list(OWNER_QNA_ID_RE.finditer(body))
        state_matches = list(OWNER_QNA_STATE_RE.finditer(body))
        if (
            len(id_matches) != 1
            or len(state_matches) != 1
            or id_matches[0].group(1).upper() != question_ref
            or _MACHINE_AUTHORITY_QNA_DIRECTION_TUPLE_RE.search(match.group("tail")) is not None
        ):
            raise MachineAuthorityDecisionError(
                "owner_qna_lifecycle_invalid",
                "machine-authority Q&A carrier is ambiguous or does not match the confirmation ref",
            )
        source = match.group("from").lower()
        target = match.group("to").lower()
        state = state_matches[0].group(1).lower()
        if source == "architect" and target == "owner":
            if state != "open":
                raise MachineAuthorityDecisionError("owner_qna_lifecycle_invalid", "Architect question must be status=open")
            questions.append(event.line_no)
        elif source == "owner" and target == "architect":
            if state != "closed":
                raise MachineAuthorityDecisionError("owner_qna_lifecycle_invalid", "Owner answer must be status=closed")
            answers.append(event.line_no)
        else:
            raise MachineAuthorityDecisionError("owner_qna_lifecycle_invalid", "machine-authority Q&A direction is invalid")
    if len(questions) != 1 or len(answers) != 1 or answers[0] <= questions[0]:
        raise MachineAuthorityDecisionError(
            "owner_qna_lifecycle_invalid",
            "machine-authority confirmation requires one Architect->Owner open question and one later Owner->Architect closed answer",
        )


def _machine_authority_validate_required_decision(
    decision: Mapping[str, object],
    *,
    plan_path: Path,
    plan_rel: str,
    plan_text: str,
    status_norm: str,
    origin_chain: frozenset[str],
) -> tuple[str, str, str, str]:
    allowed = {
        "schema_version",
        "decision_id",
        "applicability",
        "state",
        "impacts",
        "cutover_policy",
        "recommended_route",
        "alternatives",
        "owner_confirmation",
    }
    _machine_authority_require_exact_keys(
        decision,
        allowed,
        label="plan_meta.machine_authority_decision",
    )
    if decision.get("schema_version") != MACHINE_AUTHORITY_DECISION_SCHEMA:
        raise MachineAuthorityDecisionError("schema_invalid", "machine-authority schema_version is invalid")
    decision_id = _machine_authority_require_nonempty_string(decision.get("decision_id"), label="decision_id")
    if not MACHINE_AUTHORITY_DECISION_ID_RE.fullmatch(decision_id):
        raise MachineAuthorityDecisionError("decision_id_invalid", "decision_id must match mad-YYMMDD-HHMM[-slug]")
    if decision.get("applicability") != "required":
        raise MachineAuthorityDecisionError("applicability_invalid", "required decision must set applicability=required")
    state = decision.get("state")
    if state not in {"draft", "frozen"}:
        raise MachineAuthorityDecisionError("state_invalid", "required decision state must be draft or frozen")
    impacts = _machine_authority_require_unique_strings(decision.get("impacts"), label="impacts")
    if any(item not in MACHINE_AUTHORITY_DECISION_IMPACTS for item in impacts):
        raise MachineAuthorityDecisionError("impacts_invalid", "impacts contains an unsupported value")
    policy = decision.get("cutover_policy")
    if not isinstance(policy, dict) or (
        policy != MACHINE_AUTHORITY_DECISION_LEGACY_CUTOVER_POLICY
        and policy != MACHINE_AUTHORITY_DECISION_HANDOFF_POLICY
    ):
        raise MachineAuthorityDecisionError(
            "cutover_policy_invalid",
            "cutover_policy must exactly match the legacy or status-and-purpose handoff policy",
        )
    route = decision.get("recommended_route")
    if not isinstance(route, Mapping):
        raise MachineAuthorityDecisionError("recommended_route_invalid", "recommended_route must be an object")
    route_kind = route.get("kind")
    route_keys = {
        "id",
        "kind",
        "authority_host",
        "canonical_writer",
        "canonical_reader",
        "derived_consumers",
        "schema",
        "identity_fields",
        "cardinality",
        "failure_behavior",
    }
    if route_kind == "bounded_grammar":
        route_keys.add("grammar_contour")
    _machine_authority_require_exact_keys(route, route_keys, label="recommended_route")
    route_id = _machine_authority_require_nonempty_string(route.get("id"), label="recommended_route.id")
    if route_kind not in {"structured_carrier", "bounded_grammar"}:
        raise MachineAuthorityDecisionError("recommended_route_invalid", "recommended_route.kind is invalid")
    _machine_authority_validate_authority_host(route.get("authority_host"), plan_rel=plan_rel)
    _machine_authority_require_nonempty_string(route.get("canonical_writer"), label="recommended_route.canonical_writer")
    canonical_reader = _machine_authority_require_nonempty_string(
        route.get("canonical_reader"),
        label="recommended_route.canonical_reader",
    )
    _machine_authority_require_unique_strings(route.get("derived_consumers"), label="recommended_route.derived_consumers")
    _machine_authority_require_unique_strings(route.get("identity_fields"), label="recommended_route.identity_fields")
    route_schema = _machine_authority_require_nonempty_string(
        route.get("schema"),
        label="recommended_route.schema",
    )
    cardinality = _machine_authority_require_nonempty_string(
        route.get("cardinality"),
        label="recommended_route.cardinality",
    )
    failure_behavior = route.get("failure_behavior")
    if not isinstance(failure_behavior, Mapping):
        raise MachineAuthorityDecisionError("failure_behavior_invalid", "failure_behavior must be an object")
    _machine_authority_require_exact_keys(
        failure_behavior,
        set(MACHINE_AUTHORITY_DECISION_FAILURE_KEYS),
        label="recommended_route.failure_behavior",
    )
    if any(failure_behavior.get(key) != "fail_closed" for key in MACHINE_AUTHORITY_DECISION_FAILURE_KEYS):
        raise MachineAuthorityDecisionError("failure_behavior_invalid", "all failure_behavior values must be fail_closed")
    if route_kind == "bounded_grammar":
        authority_host = route.get("authority_host")
        assert isinstance(authority_host, Mapping)
        _machine_authority_validate_grammar_contour(
            route.get("grammar_contour"),
            authority_host=authority_host,
            plan_path=plan_path,
            plan_rel=plan_rel,
            decision_id=decision_id,
            origin_chain=origin_chain,
        )
    alternatives = decision.get("alternatives")
    if not isinstance(alternatives, list) or not alternatives:
        raise MachineAuthorityDecisionError("alternatives_invalid", "alternatives must be a non-empty array")
    alternative_ids: list[str] = []
    for index, alternative in enumerate(alternatives):
        if not isinstance(alternative, Mapping):
            raise MachineAuthorityDecisionError("alternatives_invalid", f"alternatives[{index}] must be an object")
        _machine_authority_require_exact_keys(
            alternative,
            {"id", "kind", "disposition", "tradeoff"},
            label=f"alternatives[{index}]",
        )
        alternative_id = _machine_authority_require_nonempty_string(alternative.get("id"), label=f"alternatives[{index}].id")
        _machine_authority_require_nonempty_string(alternative.get("kind"), label=f"alternatives[{index}].kind")
        _machine_authority_require_nonempty_string(alternative.get("tradeoff"), label=f"alternatives[{index}].tradeoff")
        if alternative.get("disposition") not in {"rejected", "deferred"}:
            raise MachineAuthorityDecisionError("alternatives_invalid", "alternative disposition is invalid")
        alternative_ids.append(alternative_id)
    normalized_alternative_ids = [unicodedata.normalize("NFC", alternative_id) for alternative_id in alternative_ids]
    if (
        len(normalized_alternative_ids) != len(set(normalized_alternative_ids))
        or unicodedata.normalize("NFC", route_id) in normalized_alternative_ids
    ):
        raise MachineAuthorityDecisionError("alternatives_invalid", "alternative ids must be unique and exclude recommended route")
    if normalized_alternative_ids != sorted(normalized_alternative_ids):
        raise MachineAuthorityDecisionError("alternatives_invalid", "alternative ids must be sorted")
    confirmation = decision.get("owner_confirmation")
    if not isinstance(confirmation, Mapping):
        raise MachineAuthorityDecisionError("owner_confirmation_invalid", "owner_confirmation must be an object")
    confirmation_state = confirmation.get("state")
    confirmation_keys = {"state", "question_ref", "decision_id", "route_id", "carrier_sha256"}
    if confirmation_state == "rejected":
        confirmation_keys.add("successor_plan_ref")
    _machine_authority_require_exact_keys(confirmation, confirmation_keys, label="owner_confirmation")
    if confirmation_state not in {"pending", "confirmed", "rejected"}:
        raise MachineAuthorityDecisionError("owner_confirmation_invalid", "owner_confirmation.state is invalid")
    question_ref = _machine_authority_require_nonempty_string(confirmation.get("question_ref"), label="owner_confirmation.question_ref")
    if not re.fullmatch(r"Q[1-9][0-9]*", question_ref):
        raise MachineAuthorityDecisionError("owner_confirmation_invalid", "owner_confirmation.question_ref must be Q[1-9][0-9]*")
    digest = machine_authority_decision_sha256(decision)
    if confirmation.get("decision_id") != decision_id or confirmation.get("route_id") != route_id:
        raise MachineAuthorityDecisionError("owner_confirmation_mismatch", "owner confirmation id/route must match frozen core")
    if confirmation.get("carrier_sha256") != digest:
        raise MachineAuthorityDecisionError("owner_confirmation_mismatch", "owner confirmation digest must match canonical core")
    if state == "draft":
        if confirmation_state != "pending" or status_norm not in MACHINE_AUTHORITY_DECISION_ARCHITECT_STATUSES:
            raise MachineAuthorityDecisionError("draft_not_architect_owned", "draft decision may remain only in Architect-owned status with pending confirmation")
        return "draft", decision_id, route_id, digest
    if confirmation_state in {"confirmed", "rejected"}:
        _machine_authority_qna_lifecycle(plan_text, question_ref)
    if confirmation_state == "confirmed":
        return "frozen_confirmed", decision_id, route_id, digest
    if confirmation_state == "pending":
        if status_norm not in MACHINE_AUTHORITY_DECISION_ARCHITECT_STATUSES:
            raise MachineAuthorityDecisionError("owner_confirmation_pending", "pending confirmation blocks downstream handoff")
        return "frozen_pending", decision_id, route_id, digest
    successor = _machine_authority_repo_relative_path(
        confirmation.get("successor_plan_ref"), label="owner_confirmation.successor_plan_ref"
    )
    if successor == plan_rel:
        raise MachineAuthorityDecisionError("rejected_successor_invalid", "rejected successor must differ from source plan")
    if status_norm == "superseded":
        _machine_authority_validate_rejected_successor(
            plan_path=plan_path,
            plan_rel=plan_rel,
            plan_meta=decision,
            successor_rel=successor,
        )
        return "frozen_rejected_successor", decision_id, route_id, digest
    if status_norm not in MACHINE_AUTHORITY_DECISION_ARCHITECT_STATUSES:
        raise MachineAuthorityDecisionError("owner_confirmation_rejected", "rejected confirmation blocks downstream source status")
    return "frozen_rejected", decision_id, route_id, digest


def _machine_authority_validate_rejected_successor(
    *,
    plan_path: Path,
    plan_rel: str,
    plan_meta: Mapping[str, object],
    successor_rel: str,
) -> None:
    root, _ = _machine_authority_plan_path(plan_path)
    if not REPO_RELATIVE_PLAN_PATH_RE.fullmatch(successor_rel):
        raise MachineAuthorityDecisionError(
            "rejected_successor_invalid",
            "rejected successor must use a canonical docs/plans path",
        )
    successor_path = root / successor_rel
    if not successor_path.is_file():
        raise MachineAuthorityDecisionError("rejected_successor_invalid", "rejected successor plan is not materialized")
    successor_text = successor_path.read_text(encoding="utf-8")
    _, successor_status_line = _scan_status_line(successor_text)
    successor_status = _status_norm_from_line(successor_status_line) if successor_status_line else ""
    if successor_status in {"done", "superseded"}:
        raise MachineAuthorityDecisionError("rejected_successor_invalid", "rejected successor must remain non-terminal")
    successor_meta_result = strict_plan_meta_json(successor_text)
    if successor_meta_result.state != "valid" or successor_meta_result.plan_meta is None:
        raise MachineAuthorityDecisionError("rejected_successor_invalid", "rejected successor strict Meta is invalid")
    successor_meta = successor_meta_result.plan_meta
    depends_on = successor_meta.get("depends_on")
    if not isinstance(depends_on, list) or depends_on.count(plan_rel) != 1:
        raise MachineAuthorityDecisionError("rejected_successor_invalid", "successor depends_on must contain exactly the source plan")
    successor_decision = successor_meta.get("machine_authority_decision")
    if not isinstance(successor_decision, Mapping):
        raise MachineAuthorityDecisionError("rejected_successor_invalid", "successor decision is missing")
    successor_confirmation = successor_decision.get("owner_confirmation")
    if (
        successor_decision.get("state") != "frozen"
        or not isinstance(successor_confirmation, Mapping)
        or successor_confirmation.get("state") not in {"pending", "confirmed"}
    ):
        raise MachineAuthorityDecisionError("rejected_successor_invalid", "successor must carry frozen pending/confirmed decision")
    source_meta_result = strict_plan_meta_json(plan_path.read_text(encoding="utf-8"))
    if source_meta_result.state != "valid" or source_meta_result.plan_meta is None:
        raise MachineAuthorityDecisionError("rejected_successor_invalid", "source strict Meta is invalid")
    next_plans = source_meta_result.plan_meta.get("next_plans")
    if not isinstance(next_plans, list) or next_plans != [successor_rel]:
        raise MachineAuthorityDecisionError("rejected_successor_invalid", "source next_plans must contain exactly the successor")
    successor_readback = machine_authority_decision_readback(successor_path, plan_text=successor_text)
    if (
        successor_readback.state not in {"frozen_pending", "frozen_confirmed"}
        or successor_readback.reason_code != "ok"
    ):
        raise MachineAuthorityDecisionError(
            "rejected_successor_invalid",
            "rejected successor must pass the full frozen machine-authority lifecycle",
        )


def _machine_authority_strict_code_draft_meta(draft_text: str) -> Mapping[str, object]:
    candidates: list[Mapping[str, object]] = []
    in_json = False
    fence_line = 0
    buf: list[str] = []
    for line_no, line in enumerate(draft_text.splitlines(), start=1):
        if not in_json and _JSON_FENCE_START_RE.fullmatch(line):
            in_json = True
            fence_line = line_no
            buf = []
            continue
        if in_json and _JSON_FENCE_END_RE.fullmatch(line):
            raw = "\n".join(buf).strip()
            in_json = False
            buf = []
            parsed = _machine_authority_load_json(raw)
            if not isinstance(parsed, Mapping) or "code_draft_meta" not in parsed:
                continue
            if not isinstance(parsed.get("code_draft_meta"), Mapping):
                raise MachineAuthorityDecisionError("code_draft_meta_invalid", "code_draft_meta must be a root object")
            candidates.append(parsed["code_draft_meta"])
            continue
        if in_json:
            buf.append(line)
    if in_json:
        raise MachineAuthorityDecisionError("code_draft_meta_invalid", f"line {fence_line}: unterminated code draft JSON")
    if len(candidates) != 1:
        raise MachineAuthorityDecisionError("code_draft_meta_invalid", "expected exactly one code_draft_meta JSON carrier")
    return candidates[0]


def _machine_authority_validate_draft_ref(
    *,
    root: Path,
    plan_path: Path,
    plan_rel: str,
    decision: Mapping[str, object],
    applicability: str,
    decision_id: str,
    digest: str,
) -> tuple[str, str]:
    draft_rel = f"docs/code_drafts/{plan_path.stem}__code_draft.md"
    draft_path = root / draft_rel
    if not draft_path.is_file():
        return "missing", f"missing current-plan code draft `{draft_rel}`"
    try:
        draft_meta = _machine_authority_strict_code_draft_meta(draft_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, MachineAuthorityDecisionError) as exc:
        return "invalid", f"invalid current-plan code draft: {exc}"
    if draft_meta.get("plan") != plan_rel:
        return "invalid", "code_draft_meta.plan does not match current plan"
    ref = draft_meta.get("machine_authority_decision_ref")
    if not isinstance(ref, Mapping):
        return "missing", "code_draft_meta.machine_authority_decision_ref is missing"
    if applicability == "required":
        expected = {"applicability", "decision_id", "carrier_sha256"}
        if set(ref) != expected or ref.get("applicability") != "required":
            return "invalid", "active machine_authority_decision_ref has wrong variant or keys"
        if ref.get("decision_id") != decision_id or ref.get("carrier_sha256") != digest:
            return "invalid", "active machine_authority_decision_ref drifts from validated carrier"
    else:
        expected = {"applicability", "reason_code", "carrier_sha256"}
        if set(ref) != expected or ref.get("applicability") != "not_applicable":
            return "invalid", "N-A machine_authority_decision_ref has wrong variant or keys"
        if ref.get("reason_code") != decision.get("reason_code") or ref.get("carrier_sha256") != digest:
            return "invalid", "N-A machine_authority_decision_ref drifts from validated carrier"
    return "valid", "validated tagged code-draft reference matches current carrier"


def _machine_authority_context_entries(plan_text: str, label: str) -> tuple[str, ...]:
    """Return every literal Context links entry for one label.

    The strict no-parent-draft admission must not trust the first matching
    ``Code draft(s):`` row: a later live same-stem ref is a conflicting
    current carrier, not an innocuous duplicate.
    """

    entries: list[str] = []
    for line in _header_section_lines(plan_text, "**Context links"):
        match = re.match(rf"^\s*-\s*{re.escape(label)}\s*(.+?)\s*$", line)
        if match:
            entries.append(match.group(1).strip())
    return tuple(entries)


def _machine_authority_is_literal_reasoned_na(value: str) -> bool:
    """Accept only the exact reasoned N/A Context-links value."""

    cleaned = value.strip().rstrip(".,;").strip()
    if cleaned.startswith("`") and cleaned.endswith("`") and len(cleaned) >= 2:
        cleaned = cleaned[1:-1].strip()
    return bool(
        re.fullmatch(
            r"n\s*/\s*a\s*\(\s*why\s*=\s*[^)\s][^)]*\s*\)",
            cleaned,
            re.IGNORECASE,
        )
    )


def _machine_authority_strict_na_parent_admission(
    *,
    root: Path,
    plan_path: Path,
    plan_text: str,
    plan_meta: Mapping[str, object],
) -> tuple[bool, str | None]:
    """Validate the strict decomposition N-A draft boundary.

    This is intentionally a narrow reader-side exception. It relies on the
    existing header/meta extractors and does not create a second plan grammar.
    The caller has already validated an exact ``not_applicable`` decision.
    ``None`` means the generic N-A branch remains applicable; a non-empty
    reason is a strict-decomposition conflict that must fail closed.
    """

    if _normalize_value(str(plan_meta.get("phase_overlay") or "")) != "decomposition_wave":
        return False, None
    if _normalize_value(str(plan_meta.get("phase_state") or "")) not in {"active", "parked"}:
        return False, None

    draft_rel = f"docs/code_drafts/{plan_path.stem}__code_draft.md"
    draft_entries = _machine_authority_context_entries(plan_text, "Code draft(s):")
    if len(draft_entries) != 1:
        return False, "strict N-A decomposition parent requires exactly one literal Code draft(s) entry"
    if not _machine_authority_is_literal_reasoned_na(draft_entries[0]):
        return False, "strict N-A decomposition parent requires literal Code draft(s): N/A (why=...)"
    context_values = []
    for line in _header_section_lines(plan_text, "**Context links"):
        match = re.match(r"^\s*-\s*[^:]+:\s*(.+?)\s*$", line)
        if match:
            context_values.append(match.group(1).strip())
    if any(draft_rel in value for value in context_values):
        return False, "strict N-A decomposition parent has a live current-plan code-draft ref"

    # ``Path.exists`` misses a dangling link. Any directory, regular file, or
    # link at the canonical same-stem location is a physical conflict.
    if os.path.lexists(root / draft_rel):
        return False, f"strict N-A decomposition parent has a physical current-plan code draft `{draft_rel}`"
    return True, None


def machine_authority_decision_readback(
    plan_path: Path,
    plan_text: str | None = None,
    *,
    _grammar_origin_chain: frozenset[str] | None = None,
) -> MachineAuthorityDecisionReadback:
    """Validate one admission carrier and its downstream tagged ref once."""

    if plan_text is None:
        plan_text = plan_path.read_text(encoding="utf-8")
    root, plan_rel = _machine_authority_plan_path(plan_path)
    strict_meta = strict_plan_meta_json(plan_text)
    if plan_path.name == "_template.md" and not strict_meta.has_machine_authority_marker:
        return _machine_authority_absent_carrier_readback(plan_path, "")
    try:
        _, raw_status_line = _scan_status_line(plan_text)
    except ValueError as exc:
        if strict_meta.has_machine_authority_marker:
            return MachineAuthorityDecisionReadback(
                "invalid",
                "status_header_invalid",
                str(exc),
                "",
                "",
                "",
                "",
                "",
                "invalid",
                str(exc),
                True,
            )
        raw_status_line = ""
    status_norm = _status_norm_from_line(raw_status_line) if raw_status_line else ""
    absent_carrier = _machine_authority_absent_carrier_readback(plan_path, status_norm)
    grammar_origin_chain = _grammar_origin_chain or frozenset()
    if plan_rel in grammar_origin_chain:
        return MachineAuthorityDecisionReadback(
            "invalid",
            "grammar_contour_invalid",
            "grammar contour origin cycle is invalid",
            "",
            "",
            "",
            "",
            "",
            "invalid",
            "grammar contour origin cycle is invalid",
            True,
        )
    if strict_meta.state != "valid" or strict_meta.plan_meta is None:
        if absent_carrier.route_guard_required or strict_meta.has_machine_authority_marker:
            return MachineAuthorityDecisionReadback(
                "invalid",
                strict_meta.reason_code,
                strict_meta.reason,
                "",
                "",
                "",
                "",
                "",
                "invalid",
                strict_meta.reason,
                True,
            )
        return absent_carrier
    if "machine_authority_decision" not in strict_meta.plan_meta:
        return absent_carrier
    decision = strict_meta.plan_meta["machine_authority_decision"]
    if not isinstance(decision, Mapping):
        return MachineAuthorityDecisionReadback(
            "invalid",
            "carrier_not_object",
            "plan_meta.machine_authority_decision must be an object",
            "",
            "",
            "",
            "",
            "",
            "invalid",
            "carrier is not object-shaped",
            True,
        )
    try:
        applicability = decision.get("applicability")
        if applicability == "not_applicable":
            _machine_authority_require_exact_keys(
                decision,
                {"schema_version", "applicability", "reason_code"},
                label="plan_meta.machine_authority_decision",
            )
            if decision.get("schema_version") != MACHINE_AUTHORITY_DECISION_SCHEMA:
                raise MachineAuthorityDecisionError("schema_invalid", "N-A schema_version is invalid")
            na_reason_code = decision.get("reason_code")
            if na_reason_code not in MACHINE_AUTHORITY_DECISION_NA_REASONS:
                raise MachineAuthorityDecisionError("not_applicable_reason_invalid", "N-A reason_code is invalid")
            digest = machine_authority_decision_sha256(decision)
            strict_na_parent, strict_na_conflict = _machine_authority_strict_na_parent_admission(
                root=root,
                plan_path=plan_path,
                plan_text=plan_text,
                plan_meta=strict_meta.plan_meta,
            )
            if strict_na_conflict:
                raise MachineAuthorityDecisionError("code_draft_ref_invalid", strict_na_conflict)
            if strict_na_parent:
                ref_state = "not_required"
                ref_reason = "strict N-A decomposition parent has no current-plan code draft"
            else:
                ref_state, ref_reason = _machine_authority_validate_draft_ref(
                    root=root,
                    plan_path=plan_path,
                    plan_rel=plan_rel,
                    decision=decision,
                    applicability="not_applicable",
                    decision_id="",
                    digest=digest,
                )
            # A strict decomposition parent is deliberately the one N-A form
            # without a current-plan draft.  Its derived ``not_required``
            # state remains stable across the later planning/review/terminal
            # statuses; ordinary N-A plans still take the historical
            # same-stem-ref gate below.
            if (
                status_norm in MACHINE_AUTHORITY_DECISION_REF_REQUIRED_STATUSES
                and ref_state != "valid"
                and not strict_na_parent
            ):
                raise MachineAuthorityDecisionError("code_draft_ref_invalid", ref_reason)
            return MachineAuthorityDecisionReadback(
                "not_applicable",
                "ok",
                "exact not_applicable carrier is valid",
                "",
                "",
                digest,
                "not_applicable",
                "not_applicable",
                ref_state,
                ref_reason,
                False,
            )
        if applicability != "required":
            raise MachineAuthorityDecisionError("applicability_invalid", "applicability must be required or not_applicable")
        state, decision_id, route, digest = _machine_authority_validate_required_decision(
            decision,
            plan_path=plan_path,
            plan_rel=plan_rel,
            plan_text=plan_text,
            status_norm=status_norm,
            origin_chain=grammar_origin_chain,
        )
        confirmation = decision.get("owner_confirmation")
        assert isinstance(confirmation, Mapping)
        confirmation_state = str(confirmation.get("state") or "")
        ref_state, ref_reason = _machine_authority_validate_draft_ref(
            root=root,
            plan_path=plan_path,
            plan_rel=plan_rel,
            decision=decision,
            applicability="required",
            decision_id=decision_id,
            digest=digest,
        )
        if state == "frozen_confirmed" and status_norm in MACHINE_AUTHORITY_DECISION_REF_REQUIRED_STATUSES and ref_state != "valid":
            raise MachineAuthorityDecisionError("code_draft_ref_invalid", ref_reason)
        if state == "frozen_rejected_successor":
            return MachineAuthorityDecisionReadback(
                state,
                "ok",
                "rejected source has an exact non-terminal successor",
                decision_id,
                route,
                digest,
                confirmation_state,
                "required",
                ref_state,
                ref_reason,
                False,
            )
        return MachineAuthorityDecisionReadback(
            state,
            "ok",
            "machine-authority carrier is valid for its current Architect-owned lifecycle state",
            decision_id,
            route,
            digest,
            confirmation_state,
            "required",
            ref_state,
            ref_reason,
            state not in {"frozen_confirmed"} and status_norm in MACHINE_AUTHORITY_DECISION_REQUIRED_STATUSES,
        )
    except MachineAuthorityDecisionError as exc:
        return MachineAuthorityDecisionReadback(
            "invalid",
            exc.reason_code,
            str(exc),
            "",
            "",
            "",
            "",
            "",
            "invalid",
            str(exc),
            True,
        )


class CurrentOpenBlockerError(ValueError):
    """The canonical current-open blocker carrier is missing or inconsistent."""


def current_open_blocker_ids(review_text: str) -> tuple[str, ...]:
    """Return the numeric-order current-open IDs from the sole S1 section."""

    lines = review_text.splitlines()
    section_starts = [
        index
        for index, line in enumerate(lines)
        if re.fullmatch(r"## S1 Blocker\s*", line)
    ]
    if len(section_starts) != 1:
        raise CurrentOpenBlockerError("review must contain exactly one canonical ## S1 Blocker section")
    start = section_starts[0] + 1
    end = next(
        (
            index
            for index in range(start, len(lines))
            if re.match(r"^##(?:\s|$)", lines[index])
        ),
        len(lines),
    )
    section = lines[start:end]
    subsection_starts = [
        index for index, line in enumerate(section) if re.match(r"^###(?:\s|$)", line)
    ]
    if not subsection_starts:
        raise CurrentOpenBlockerError("canonical ## S1 Blocker section has no blocker subsections")

    ids: list[str] = []
    heading_re = re.compile(
        r"^### (B([1-9][0-9]*))(?:\) (\S(?:.*\S)?))?\s*$"
    )
    blocker_field_re = re.compile(
        r"^\s*-\s+Blocker ID:\s+(?:`(?P<quoted>B[1-9][0-9]*)`|(?P<plain>B[1-9][0-9]*))\s*$"
    )
    state_field_re = re.compile(
        r"^\s*-\s+Current state:\s+(?:`(?P<quoted>open)`|(?P<plain>open))\s*$"
    )
    for position, subsection_start in enumerate(subsection_starts):
        heading = section[subsection_start]
        heading_match = heading_re.fullmatch(heading)
        if heading_match is None:
            raise CurrentOpenBlockerError(f"malformed blocker heading: {heading!r}")
        subsection_end = (
            subsection_starts[position + 1]
            if position + 1 < len(subsection_starts)
            else len(section)
        )
        body = section[subsection_start + 1 : subsection_end]
        blocker_fields = [
            line for line in body if re.match(r"^\s*-\s+Blocker ID:", line)
        ]
        state_fields = [
            line for line in body if re.match(r"^\s*-\s+Current state:", line)
        ]
        if len(blocker_fields) != 1:
            raise CurrentOpenBlockerError(
                f"{heading_match.group(1)} must contain exactly one Blocker ID field"
            )
        if len(state_fields) != 1:
            raise CurrentOpenBlockerError(
                f"{heading_match.group(1)} must contain exactly one Current state field"
            )
        blocker_match = blocker_field_re.fullmatch(blocker_fields[0])
        state_match = state_field_re.fullmatch(state_fields[0])
        if blocker_match is None:
            raise CurrentOpenBlockerError(
                f"{heading_match.group(1)} has a malformed Blocker ID field"
            )
        if state_match is None:
            raise CurrentOpenBlockerError(
                f"{heading_match.group(1)} has an unsupported Current state"
            )
        field_id = blocker_match.group("quoted") or blocker_match.group("plain")
        heading_id = heading_match.group(1)
        if field_id != heading_id:
            raise CurrentOpenBlockerError(
                f"blocker heading/field mismatch: {heading_id} != {field_id}"
            )
        if heading_id in ids:
            raise CurrentOpenBlockerError(f"duplicate blocker ID: {heading_id}")
        ids.append(heading_id)

    return tuple(sorted(ids, key=lambda value: int(value[1:])))


def accepted_red_topology_open_blocker_ids(review_text: str) -> tuple[str, ...]:
    """Read the one live blocker from a frozen accepted-red historical review."""

    lines = review_text.splitlines()
    section_starts = [
        index
        for index, line in enumerate(lines)
        if re.fullmatch(r"## S1 Blocker\s*", line)
    ]
    if len(section_starts) != 1:
        raise CurrentOpenBlockerError(
            "topology review must contain exactly one canonical ## S1 Blocker section"
        )
    start = section_starts[0] + 1
    end = next(
        (
            index
            for index in range(start, len(lines))
            if re.match(r"^##(?:\s|$)", lines[index])
        ),
        len(lines),
    )
    section = lines[start:end]
    subsection_starts = [
        index for index, line in enumerate(section) if re.match(r"^###(?:\s|$)", line)
    ]
    if not subsection_starts:
        raise CurrentOpenBlockerError(
            "topology review has no blocker subsections"
        )
    heading_re = re.compile(r"^### (B([1-9][0-9]*))(?:\) (\S(?:.*\S)?))?\s*$")
    blocker_field_re = re.compile(
        r"^\s*-\s+Blocker ID:\s+(?:`(?P<quoted>B[1-9][0-9]*)`|(?P<plain>B[1-9][0-9]*))\s*$"
    )
    state_field_re = re.compile(
        r"^\s*-\s+Current state:\s+(?:`(?P<quoted>open|historical-fixed)`|(?P<plain>open|historical-fixed))\s*$"
    )
    open_ids: list[str] = []
    seen_ids: set[str] = set()
    for position, subsection_start in enumerate(subsection_starts):
        heading = section[subsection_start]
        heading_match = heading_re.fullmatch(heading)
        if heading_match is None:
            raise CurrentOpenBlockerError(
                f"malformed topology blocker heading: {heading!r}"
            )
        subsection_end = (
            subsection_starts[position + 1]
            if position + 1 < len(subsection_starts)
            else len(section)
        )
        body = section[subsection_start + 1 : subsection_end]
        blocker_fields = [
            line for line in body if re.match(r"^\s*-\s+Blocker ID:", line)
        ]
        state_fields = [
            line for line in body if re.match(r"^\s*-\s+Current state:", line)
        ]
        if len(blocker_fields) != 1 or len(state_fields) != 1:
            raise CurrentOpenBlockerError(
                f"{heading_match.group(1)} has malformed topology blocker fields"
            )
        blocker_match = blocker_field_re.fullmatch(blocker_fields[0])
        state_match = state_field_re.fullmatch(state_fields[0])
        if blocker_match is None or state_match is None:
            raise CurrentOpenBlockerError(
                f"{heading_match.group(1)} has unsupported topology blocker fields"
            )
        blocker_id = blocker_match.group("quoted") or blocker_match.group("plain")
        if blocker_id != heading_match.group(1) or blocker_id in seen_ids:
            raise CurrentOpenBlockerError(
                "topology blocker identity is malformed or duplicate"
            )
        seen_ids.add(blocker_id)
        state = state_match.group("quoted") or state_match.group("plain")
        if state == "open":
            open_ids.append(blocker_id)
    return tuple(sorted(open_ids, key=lambda value: int(value[1:])))


def successor_inherited_blocker_ids(
    successor_text: str,
    review_rel: str,
) -> tuple[str, ...]:
    """Return exact blocker refs inherited in the successor header carrier."""

    header = re.split(r"^##(?:\s|$)", successor_text, maxsplit=1, flags=re.MULTILINE)[0]
    raw_ids = re.findall(
        rf"{re.escape(review_rel)}#(B[0-9]+)\b",
        header,
    )
    if not raw_ids:
        raise CurrentOpenBlockerError("successor has no inherited refs to the source review")
    if any(re.fullmatch(r"B[1-9][0-9]*", blocker_id) is None for blocker_id in raw_ids):
        raise CurrentOpenBlockerError("successor contains a malformed inherited blocker ref")
    if len(set(raw_ids)) != len(raw_ids):
        raise CurrentOpenBlockerError("successor contains duplicate inherited blocker refs")
    return tuple(sorted(raw_ids, key=lambda value: int(value[1:])))


class AcceptedRedDurableValidationError(ValueError):
    """A present accepted-red durable ref failed its full evidence contract."""


# Incident-specific accepted-red evidence is intentionally not carried by the
# neutral Planveyor runtime. A target that needs one must supply and validate its
# own immutable evidence; tests inject synthetic entries explicitly.
ACCEPTED_RED_SNAPSHOT_BRIDGE_ALLOWLIST: dict[tuple[str, str, str], str] = {}
ACCEPTED_RED_RECOVERY_CONTRACT_REBIND_ALLOWLIST: dict[
    tuple[str, str, str, str, str, str],
    AcceptedRedRecoveryContractRebind,
] = {}
ACCEPTED_RED_SUCCESSOR_TOPOLOGY_REBIND_ALLOWLIST: tuple[
    AcceptedRedSuccessorTopologyRebind, ...
] = ()


ACCEPTED_RED_GIT_AUTHORITY_ENVIRONMENT_NAMES = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_COMMON_DIR",
    "GIT_INDEX_FILE",
)


def assert_accepted_red_clean_git_authority_environment() -> None:
    """Reject ambient Git authority overrides before accepted-red topology reads."""

    overridden = [
        name
        for name in ACCEPTED_RED_GIT_AUTHORITY_ENVIRONMENT_NAMES
        if name in os.environ
    ]
    if overridden:
        raise AcceptedRedDurableValidationError(
            "accepted-red operational-red: ambient Git authority override(s): "
            + ", ".join(overridden)
        )


def accepted_red_git_env() -> dict[str, str]:
    env = os.environ.copy()
    for name in ACCEPTED_RED_GIT_AUTHORITY_ENVIRONMENT_NAMES:
        env.pop(name, None)
    env["GIT_NO_REPLACE_OBJECTS"] = "1"
    return env


def _accepted_red_git(
    root: Path,
    *args: str,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        input=input_bytes,
        capture_output=True,
        check=False,
        env=accepted_red_git_env(),
    )


def _accepted_red_git_text(root: Path, *args: str) -> str:
    proc = _accepted_red_git(root, *args)
    if proc.returncode:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        raise AcceptedRedDurableValidationError(
            f"git {' '.join(args)} failed: {detail or 'unknown git error'}"
        )
    try:
        return proc.stdout.decode("utf-8", "strict").strip()
    except UnicodeDecodeError as exc:
        raise AcceptedRedDurableValidationError(
            f"git {' '.join(args)} returned non-UTF-8 output"
        ) from exc


def _accepted_red_assert_no_object_rewrite_topology(root: Path) -> None:
    if os.environ.get("GIT_REPLACE_REF_BASE"):
        raise AcceptedRedDurableValidationError(
            "custom Git replace-ref namespace is forbidden for accepted-red evidence"
        )
    replacements = _accepted_red_git(
        root,
        "for-each-ref",
        "--format=%(refname)",
        "refs/replace/",
    )
    if replacements.returncode:
        raise AcceptedRedDurableValidationError(
            "cannot inspect Git replace refs for accepted-red evidence"
        )
    if replacements.stdout.strip():
        raise AcceptedRedDurableValidationError(
            "Git replace refs are forbidden for accepted-red evidence"
        )
    graft_raw = _accepted_red_git_text(
        root,
        "rev-parse",
        "--git-path",
        "info/grafts",
    )
    graft_path = Path(graft_raw)
    if not graft_path.is_absolute():
        graft_path = root / graft_path
    if graft_path.exists() or graft_path.is_symlink():
        raise AcceptedRedDurableValidationError(
            "Git graft topology is forbidden for accepted-red evidence"
        )


def _accepted_red_has_rejected_ref(root: Path, source_stem: str) -> bool:
    ref_prefix = f"refs/planveyor/rejected-baselines/{source_stem}/"
    proc = _accepted_red_git(
        root,
        "for-each-ref",
        "--format=%(refname)",
        ref_prefix,
    )
    if proc.returncode:
        return False
    if isinstance(proc.stdout, bytes):
        try:
            ref_text = proc.stdout.decode("utf-8", "strict")
        except UnicodeDecodeError:
            return False
    elif isinstance(proc.stdout, str):
        ref_text = proc.stdout
    else:
        return False
    refs = ref_text.splitlines()
    return any(ref.startswith(ref_prefix) for ref in refs)


def _accepted_red_exact_keys(
    value: Mapping[str, object],
    allowed_sets: tuple[frozenset[str], ...],
    *,
    label: str,
) -> None:
    keys = frozenset(value)
    if keys not in allowed_sets:
        raise AcceptedRedDurableValidationError(f"{label} has unknown or incomplete fields")


def _accepted_red_repo_rel(raw_path: object, *, label: str) -> str:
    if not isinstance(raw_path, str) or not raw_path or "\\" in raw_path:
        raise AcceptedRedDurableValidationError(f"{label} must be a non-empty POSIX path")
    path = PurePosixPath(raw_path)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise AcceptedRedDurableValidationError(
            f"{label} must be repo-relative without traversal"
        )
    return raw_path


def _accepted_red_regular_path(root: Path, rel: str, *, label: str) -> Path:
    _accepted_red_repo_rel(rel, label=label)
    path = root / rel
    current = root
    for part in PurePosixPath(rel).parts:
        current /= part
        if current.is_symlink():
            raise AcceptedRedDurableValidationError(
                f"{label} contains a symlinked path component"
            )
        if not current.exists():
            break
    if not path.is_file() or path.is_symlink():
        raise AcceptedRedDurableValidationError(f"{label} must be an existing regular file")
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise AcceptedRedDurableValidationError(f"{label} escapes repository") from exc
    return path


def _accepted_red_carrier_text(
    root: Path,
    rel: str,
    *,
    label: str,
    carrier_commit: str | None = None,
) -> str:
    if carrier_commit is None:
        path = _accepted_red_regular_path(root, rel, label=label)
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise AcceptedRedDurableValidationError(f"cannot read {label}") from exc
    rel = _accepted_red_repo_rel(rel, label=label)
    entry = _accepted_red_tree_entry(root, carrier_commit, rel)
    if entry is None:
        raise AcceptedRedDurableValidationError(f"{label} is absent from carrier commit")
    mode, _oid, data = entry
    if mode != "100644":
        raise AcceptedRedDurableValidationError(f"{label} mode mismatch")
    try:
        return data.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise AcceptedRedDurableValidationError(f"cannot decode {label}") from exc


def resolve_accepted_red_review_path(
    root: Path,
    plan_ref: str,
    *,
    plan_text: str | None = None,
    carrier_commit: str | None = None,
) -> str:
    """Resolve one declared same-stem review for accepted-red consumers."""

    plan_rel = _accepted_red_repo_rel(plan_ref, label="accepted-red source plan")
    if plan_text is None:
        plan_text = _accepted_red_carrier_text(
            root,
            plan_rel,
            label="accepted-red source plan",
            carrier_commit=carrier_commit,
        )
    sections = re.findall(
        r"^##\s+Review artifacts\s*$\n(?P<body>[\s\S]*?)(?=^##(?:\s|$)|\Z)",
        plan_text,
        re.MULTILINE | re.IGNORECASE,
    )
    if len(sections) != 1:
        raise AcceptedRedDurableValidationError(
            "accepted-red source plan must have exactly one Review artifacts section"
        )

    stem = Path(plan_rel).stem
    allowed = {
        f"docs/code_reviews/{stem}.md",
        f"docs/doc_reviews/{stem}.md",
    }
    declared = sorted(
        {
            review_ref
            for review_ref in REVIEW_ARTIFACT_RE.findall(sections[0])
            if review_ref in allowed
        }
    )
    if len(declared) != 1:
        raise AcceptedRedDurableValidationError(
            "accepted-red source plan must declare exactly one allowed same-stem review"
        )
    review_rel = declared[0]
    _accepted_red_carrier_text(
        root,
        review_rel,
        label="accepted-red declared review",
        carrier_commit=carrier_commit,
    )

    counterpart_rel = next(iter(allowed - {review_rel}))
    if carrier_commit is None:
        counterpart = root / counterpart_rel
        counterpart_present = counterpart.exists() or counterpart.is_symlink()
    else:
        counterpart_present = (
            _accepted_red_tree_entry(root, carrier_commit, counterpart_rel) is not None
        )
    if counterpart_present:
        raise AcceptedRedDurableValidationError(
            "accepted-red source has both same-stem review carriers"
        )
    return review_rel


def _accepted_red_fenced_json(text: str, key: str) -> dict[str, object]:
    matches: list[dict[str, object]] = []
    for raw in re.findall(r"```json\s*([\s\S]*?)```", text):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        candidate = parsed.get(key) if isinstance(parsed, dict) else None
        if isinstance(candidate, dict):
            matches.append(candidate)
    if len(matches) != 1:
        raise AcceptedRedDurableValidationError(
            f"expected exactly one valid {key} JSON carrier"
        )
    return matches[0]


def _accepted_red_optional_fenced_json(
    text: str,
    key: str,
) -> dict[str, object] | None:
    matches: list[dict[str, object]] = []
    for raw in re.findall(r"```json\s*([\s\S]*?)```", text):
        if f'"{key}"' not in raw:
            continue

        def exact_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
            value: dict[str, object] = {}
            for pair_key, pair_value in pairs:
                if pair_key in value:
                    raise AcceptedRedDurableValidationError(
                        f"{key} JSON carrier contains duplicate key: {pair_key}"
                    )
                value[pair_key] = pair_value
            return value

        try:
            parsed = json.loads(raw, object_pairs_hook=exact_object)
        except json.JSONDecodeError as exc:
            raise AcceptedRedDurableValidationError(
                f"{key} JSON carrier is malformed"
            ) from exc
        candidate = parsed.get(key) if isinstance(parsed, dict) else None
        if isinstance(candidate, dict):
            matches.append(candidate)
    if len(matches) > 1:
        raise AcceptedRedDurableValidationError(
            f"expected at most one valid {key} JSON carrier"
        )
    return matches[0] if matches else None


def _accepted_red_snapshot_bridge(
    root: Path,
    recovery_text: str,
    source_plan: str,
    source_targets: tuple[str, ...],
    *,
    carrier_commit: str | None = None,
) -> dict[str, object] | None:
    bridge = _accepted_red_optional_fenced_json(
        recovery_text,
        "accepted_red_snapshot_bridge",
    )
    if bridge is None:
        return None
    _accepted_red_exact_keys(
        bridge,
        (
            frozenset(
                {
                    "schema",
                    "bridge_id",
                    "bridge_sha256",
                    "source_plan",
                    "review_bundle_sha256",
                    "legacy_hash_basis_schema",
                    "legacy_hash_basis",
                    "producer_commit",
                    "producer_path",
                    "producer_blob_oid",
                    "current_hash_basis_schema",
                    "current_hash_basis",
                    "current_bundle_sha256",
                    "targets",
                }
            ),
        ),
        label="accepted-red snapshot bridge",
    )
    expected_scalars = {
        "schema": "planveyor_accepted_red_snapshot_bridge.v1",
        "source_plan": source_plan,
        "legacy_hash_basis": "sha256-canonical-json-v1-path-sha256-size",
        "legacy_hash_basis_schema": "review_target_snapshot.hash_basis.v1",
        "producer_path": "scripts/review_target_snapshot.py",
        "current_hash_basis": "sha256-canonical-json-v2-path-sha256-size-git_mode",
        "current_hash_basis_schema": review_target_snapshot.HASH_BASIS_SCHEMA_VERSION,
    }
    for key, expected in expected_scalars.items():
        if bridge.get(key) != expected:
            raise AcceptedRedDurableValidationError(
                f"accepted-red snapshot bridge identity mismatch: {key}"
            )
    bridge_id = bridge.get("bridge_id")
    if not isinstance(bridge_id, str) or re.fullmatch(r"[a-z0-9][a-z0-9-]+", bridge_id) is None:
        raise AcceptedRedDurableValidationError(
            "accepted-red snapshot bridge has invalid bridge_id"
        )
    for key in (
        "bridge_sha256",
        "review_bundle_sha256",
        "current_bundle_sha256",
    ):
        value = bridge.get(key)
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise AcceptedRedDurableValidationError(
                f"accepted-red snapshot bridge has invalid {key}"
            )
    source_review_rel = resolve_accepted_red_review_path(
        root,
        source_plan,
        carrier_commit=carrier_commit,
    )
    source_review_text = _accepted_red_carrier_text(
        root,
        source_review_rel,
        label="accepted-red snapshot bridge source review",
        carrier_commit=carrier_commit,
    )
    review_target_match = re.search(
        r"^\*\*Target:\*\*\s*BUNDLE=current bundle_sha256=([0-9a-f]{64})\s*$",
        source_review_text,
        re.MULTILINE,
    )
    if (
        review_target_match is None
        or bridge["review_bundle_sha256"] != review_target_match.group(1)
    ):
        raise AcceptedRedDurableValidationError(
            "accepted-red snapshot bridge review identity mismatch"
        )
    for key in ("producer_commit", "producer_blob_oid"):
        value = bridge.get(key)
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{40}", value) is None:
            raise AcceptedRedDurableValidationError(
                f"accepted-red snapshot bridge has invalid {key}"
            )
    producer_commit = str(bridge["producer_commit"])
    producer_path = str(bridge["producer_path"])
    producer_blob_oid = str(bridge["producer_blob_oid"])
    commit_probe = _accepted_red_git(
        root,
        "cat-file",
        "-e",
        f"{producer_commit}^{{commit}}",
    )
    if commit_probe.returncode:
        raise AcceptedRedDurableValidationError(
            "accepted-red snapshot bridge producer commit is unavailable"
        )
    ancestor_probe = _accepted_red_git(
        root,
        "merge-base",
        "--is-ancestor",
        producer_commit,
        carrier_commit or "HEAD",
    )
    if ancestor_probe.returncode:
        raise AcceptedRedDurableValidationError(
            "accepted-red snapshot bridge producer commit is outside HEAD lineage"
        )
    if (
        _accepted_red_git_text(root, "rev-parse", f"{producer_commit}:{producer_path}")
        != producer_blob_oid
    ):
        raise AcceptedRedDurableValidationError(
            "accepted-red snapshot bridge producer blob mismatch"
        )
    producer_blob = _accepted_red_git(root, "cat-file", "blob", producer_blob_oid)
    if producer_blob.returncode:
        raise AcceptedRedDurableValidationError(
            "accepted-red snapshot bridge producer blob is unavailable"
        )
    try:
        producer_text = producer_blob.stdout.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise AcceptedRedDurableValidationError(
            "accepted-red snapshot bridge producer blob is not UTF-8"
        ) from exc
    if (
        'SNAPSHOT_SCHEMA_VERSION = "review_target_snapshot.v1"' not in producer_text
        or 'HASH_BASIS_SCHEMA_VERSION = "review_target_snapshot.hash_basis.v1"'
        not in producer_text
    ):
        raise AcceptedRedDurableValidationError(
            "accepted-red snapshot bridge producer is not the declared v1 producer"
        )

    raw_targets = bridge.get("targets")
    if not isinstance(raw_targets, list):
        raise AcceptedRedDurableValidationError(
            "accepted-red snapshot bridge targets must be a list"
        )
    targets: list[dict[str, object]] = []
    for index, raw in enumerate(raw_targets, start=1):
        if not isinstance(raw, dict):
            raise AcceptedRedDurableValidationError(
                f"accepted-red snapshot bridge target {index} must be an object"
            )
        _accepted_red_exact_keys(
            raw,
            (
                frozenset(
                    {
                        "path",
                        "sha256",
                        "size_bytes",
                        "git_mode",
                        "git_blob_oid",
                    }
                ),
            ),
            label=f"accepted-red snapshot bridge target {index}",
        )
        rel = _accepted_red_repo_rel(
            raw.get("path"),
            label=f"accepted-red snapshot bridge target {index} path",
        )
        digest = raw.get("sha256")
        size_bytes = raw.get("size_bytes")
        git_mode = raw.get("git_mode")
        git_blob_oid = raw.get("git_blob_oid")
        if (
            not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            or isinstance(size_bytes, bool)
            or not isinstance(size_bytes, int)
            or size_bytes < 0
            or git_mode not in {"100644", "100755"}
            or not isinstance(git_blob_oid, str)
            or re.fullmatch(r"[0-9a-f]{40}", git_blob_oid) is None
        ):
            raise AcceptedRedDurableValidationError(
                f"accepted-red snapshot bridge target {index} has invalid fields"
            )
        targets.append(
            {
                "path": rel,
                "sha256": digest,
                "size_bytes": size_bytes,
                "git_mode": git_mode,
                "git_blob_oid": git_blob_oid,
            }
        )
    if [str(item["path"]) for item in targets] != sorted(source_targets):
        raise AcceptedRedDurableValidationError(
            "accepted-red snapshot bridge target inventory mismatch"
        )
    normalized_bridge = {**bridge, "targets": targets}
    digest_payload = dict(normalized_bridge)
    claimed_digest = str(digest_payload.pop("bridge_sha256"))
    computed_digest = hashlib.sha256(
        json.dumps(
            digest_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    if claimed_digest != computed_digest:
        raise AcceptedRedDurableValidationError(
            "accepted-red snapshot bridge digest mismatch"
        )
    allowlist_key = (
        source_plan,
        str(normalized_bridge["review_bundle_sha256"]),
        str(normalized_bridge["bridge_id"]),
    )
    if ACCEPTED_RED_SNAPSHOT_BRIDGE_ALLOWLIST.get(allowlist_key) != claimed_digest:
        raise AcceptedRedDurableValidationError(
            "accepted-red snapshot bridge is not allowlisted"
        )
    return normalized_bridge


def parse_accepted_red_recovery_contract(
    root: Path,
    recovery_rel: str,
    source_plan: str,
    source_targets: Iterable[str],
    *,
    allow_terminal_status: bool = False,
    carrier_commit: str | None = None,
) -> dict[str, object]:
    """Read the recovery plan/draft identity used by capture and durable validation."""

    source_target_list = tuple(source_targets)
    if not recovery_rel or recovery_rel == source_plan:
        raise AcceptedRedDurableValidationError(
            "recovery plan must be distinct from the rejected source plan"
        )
    recovery_rel = _accepted_red_repo_rel(recovery_rel, label="recovery plan")
    recovery_text = _accepted_red_carrier_text(
        root,
        recovery_rel,
        label="recovery plan",
        carrier_commit=carrier_commit,
    )
    if not re.search(
        rf"^\s*-\s*Superseded incident plan:\s*`{re.escape(source_plan)}`\.?\s*$",
        recovery_text,
        re.MULTILINE,
    ):
        raise AcceptedRedDurableValidationError(
            "recovery plan does not bind the exact rejected source plan"
        )
    status_match = re.search(
        r"^\*\*Status:\*\*\s*(.+?)\s*$",
        recovery_text,
        re.MULTILINE,
    )
    if status_match is None:
        raise AcceptedRedDurableValidationError("recovery plan has no workflow status")
    recovery_status = status_match.group(1).strip().lower()
    if not allow_terminal_status and recovery_status in {"done", "superseded"}:
        raise AcceptedRedDurableValidationError(
            "recovery plan must have a non-terminal workflow status"
        )
    snapshot_bridge = _accepted_red_snapshot_bridge(
        root,
        recovery_text,
        source_plan,
        source_target_list,
        carrier_commit=carrier_commit,
    )

    draft_refs = sorted(
        set(
            re.findall(
                r"docs/code_drafts/[A-Za-z0-9_./-]+__code_draft\.md",
                recovery_text,
            )
        )
    )
    matching_drafts: list[tuple[str, dict[str, object]]] = []
    for draft_rel in draft_refs:
        try:
            draft_text = _accepted_red_carrier_text(
                root,
                draft_rel,
                label="recovery code draft",
                carrier_commit=carrier_commit,
            )
            draft_meta = _accepted_red_fenced_json(draft_text, "code_draft_meta")
        except AcceptedRedDurableValidationError:
            continue
        if draft_meta.get("plan") == recovery_rel:
            matching_drafts.append((draft_rel, draft_meta))
    if len(matching_drafts) != 1:
        raise AcceptedRedDurableValidationError(
            "recovery plan must link exactly one identity-matched code draft"
        )
    recovery_draft, recovery_meta = matching_drafts[0]
    expected_draft = f"docs/code_drafts/{Path(recovery_rel).stem}__code_draft.md"
    if recovery_draft != expected_draft:
        raise AcceptedRedDurableValidationError(
            "recovery code-draft identity/path mismatch"
        )

    values = recovery_meta.get("targets")
    if not isinstance(values, list) or not values:
        raise AcceptedRedDurableValidationError(
            "recovery code draft must declare a non-empty target set"
        )
    targets: list[str] = []
    for index, item in enumerate(values, start=1):
        if not isinstance(item, dict):
            raise AcceptedRedDurableValidationError(
                f"recovery target {index} must be an object"
            )
        rel = _accepted_red_repo_rel(
            item.get("path"),
            label=f"recovery target {index}",
        )
        if carrier_commit is None:
            current = root
            for part in PurePosixPath(rel).parts[:-1]:
                current /= part
                if current.is_symlink():
                    raise AcceptedRedDurableValidationError(
                        f"recovery target {index} contains a symlinked path component"
                    )
                if not current.exists():
                    break
            try:
                (root / rel).resolve().relative_to(root.resolve())
            except ValueError as exc:
                raise AcceptedRedDurableValidationError(
                    f"recovery target {index} escapes repository"
                ) from exc
        targets.append(rel)
    if len(set(targets)) != len(targets):
        raise AcceptedRedDurableValidationError(
            "recovery code draft contains duplicate targets"
        )
    targets = sorted(targets)
    if not set(targets).intersection(source_target_list):
        raise AcceptedRedDurableValidationError(
            "recovery target set does not own any rejected-target overlap"
        )
    return {
        "recovery_plan": recovery_rel,
        "recovery_code_draft": recovery_draft,
        "recovery_targets": targets,
        "recovery_status": recovery_status,
        "snapshot_bridge": snapshot_bridge,
    }


def _accepted_red_revision_blob_record(
    root: Path,
    revision: str,
    rel: str,
    *,
    label: str,
) -> dict[str, object]:
    entry = _accepted_red_tree_entry(root, revision, rel)
    if entry is None:
        raise AcceptedRedDurableValidationError(
            f"{label} is absent from pinned recovery revision: {rel}"
        )
    mode, oid, data = entry
    if mode not in {"100644", "100755"}:
        raise AcceptedRedDurableValidationError(
            f"{label} has unsupported mode in pinned recovery revision: {rel}"
        )
    return {
        "path": rel,
        "mode": mode,
        "blob_oid": oid,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }


def _accepted_red_revision_bundle(
    root: Path,
    revision: str,
    targets: Iterable[str],
) -> tuple[str, tuple[Mapping[str, object], ...]]:
    records = tuple(
        _accepted_red_revision_blob_record(
            root,
            revision,
            rel,
            label="recovery target",
        )
        for rel in sorted(targets)
    )
    files = [
        {
            "git_mode": record["mode"],
            "path": record["path"],
            "sha256": record["sha256"],
            "size_bytes": record["size_bytes"],
        }
        for record in records
    ]
    hash_basis = {
        "algorithm": "sha256",
        "files": files,
        "schema_version": "review_target_snapshot.hash_basis.v2",
    }
    bundle_sha256 = hashlib.sha256(
        json.dumps(
            hash_basis,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return bundle_sha256, records


def _accepted_red_recovery_contract_rebind_entry(
    contract: Mapping[str, object],
    manifest: Mapping[str, object],
    legacy_tip: str,
) -> AcceptedRedRecoveryContractRebind | None:
    key = (
        str(contract.get("source_plan") or ""),
        str(contract.get("review_sha") or ""),
        legacy_tip,
        str(manifest.get("captured_parent") or ""),
        str(manifest.get("recovery_plan") or ""),
        str(manifest.get("recovery_code_draft") or ""),
    )
    return ACCEPTED_RED_RECOVERY_CONTRACT_REBIND_ALLOWLIST.get(key)


def _accepted_red_validate_recovery_contract_rebind(
    root: Path,
    contract: Mapping[str, object],
    manifest: Mapping[str, object],
    legacy_tip: str,
    entry: AcceptedRedRecoveryContractRebind,
) -> dict[str, object]:
    revision = entry.recovery_revision
    if re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise AcceptedRedDurableValidationError(
            "accepted-red recovery rebind revision is invalid"
        )
    commit_probe = _accepted_red_git(
        root,
        "cat-file",
        "-e",
        f"{revision}^{{commit}}",
    )
    if commit_probe.returncode:
        raise AcceptedRedDurableValidationError(
            "accepted-red recovery rebind revision is unavailable"
        )
    captured_parent = str(manifest.get("captured_parent") or "")
    ancestor = _accepted_red_git(
        root,
        "merge-base",
        "--is-ancestor",
        captured_parent,
        revision,
    )
    if ancestor.returncode:
        raise AcceptedRedDurableValidationError(
            "accepted-red recovery rebind revision is outside captured-parent lineage"
        )

    source_targets = tuple(
        str(item)
        for item in cast(Iterable[object], contract["targets"])
    )
    recovery_plan = str(manifest["recovery_plan"])
    effective = parse_accepted_red_recovery_contract(
        root,
        recovery_plan,
        str(contract["source_plan"]),
        source_targets,
        allow_terminal_status=True,
        carrier_commit=revision,
    )
    if effective["recovery_status"] != "done":
        raise AcceptedRedDurableValidationError(
            "accepted-red recovery rebind plan is not Done at pinned revision"
        )
    frozen_draft = _accepted_red_repo_rel(
        manifest.get("recovery_code_draft"),
        label="frozen recovery code draft",
    )
    frozen_targets_raw = manifest.get("recovery_targets")
    if not isinstance(frozen_targets_raw, list) or not frozen_targets_raw:
        raise AcceptedRedDurableValidationError(
            "accepted-red recovery rebind requires frozen recovery targets"
        )
    frozen_targets = tuple(
        _accepted_red_repo_rel(value, label="frozen recovery target")
        for value in frozen_targets_raw
    )
    if frozen_targets != tuple(sorted(set(frozen_targets))):
        raise AcceptedRedDurableValidationError(
            "accepted-red frozen recovery targets are not exact sorted identities"
        )
    effective_targets = tuple(
        str(value)
        for value in cast(Iterable[object], effective["recovery_targets"])
    )
    if (
        effective["recovery_plan"] != recovery_plan
        or effective["recovery_code_draft"] != frozen_draft
        or effective_targets != entry.recovery_targets
    ):
        raise AcceptedRedDurableValidationError(
            "accepted-red recovery rebind effective contract mismatch"
        )
    if not set(frozen_targets) < set(effective_targets):
        raise AcceptedRedDurableValidationError(
            "accepted-red recovery rebind is not the exact strict target widening"
        )

    recovery_review = resolve_accepted_red_review_path(
        root,
        recovery_plan,
        carrier_commit=revision,
    )
    if recovery_review != entry.recovery_review:
        raise AcceptedRedDurableValidationError(
            "accepted-red recovery rebind review identity mismatch"
        )
    review_text = _accepted_red_carrier_text(
        root,
        recovery_review,
        label="pinned recovery review",
        carrier_commit=revision,
    )
    review_header = re.split(
        r"^##(?:\s|$)",
        review_text,
        maxsplit=1,
        flags=re.MULTILINE,
    )[0]
    review_statuses = re.findall(
        r"^\*\*Status:\*\*\s*(.+?)\s*$",
        review_header,
        re.MULTILINE,
    )
    review_targets = re.findall(
        r"^\*\*Target:\*\*\s*BUNDLE=current bundle_sha256=([0-9a-f]{64})\s*$",
        review_header,
        re.MULTILINE,
    )
    if (
        len(review_statuses) != 1
        or REVIEW_OK_STATUS_RE.fullmatch(review_statuses[0]) is None
        or len(review_targets) != 1
    ):
        raise AcceptedRedDurableValidationError(
            "accepted-red recovery rebind review is not exact green"
        )

    recovery_bundle, target_records = _accepted_red_revision_bundle(
        root,
        revision,
        effective_targets,
    )
    if (
        recovery_bundle != entry.recovery_bundle_sha256
        or review_targets[0] != recovery_bundle
    ):
        raise AcceptedRedDurableValidationError(
            "accepted-red recovery rebind review bundle mismatch"
        )

    manifest_path = str(contract["manifest_path"])
    cleanup_path = str(contract["cleanup_path"])
    manifest_record = _accepted_red_revision_blob_record(
        root,
        legacy_tip,
        manifest_path,
        label="legacy manifest",
    )
    cleanup_record = _accepted_red_revision_blob_record(
        root,
        legacy_tip,
        cleanup_path,
        label="legacy cleanup",
    )
    plan_record = _accepted_red_revision_blob_record(
        root,
        revision,
        recovery_plan,
        label="recovery plan",
    )
    draft_record = _accepted_red_revision_blob_record(
        root,
        revision,
        frozen_draft,
        label="recovery code draft",
    )
    review_record = _accepted_red_revision_blob_record(
        root,
        revision,
        recovery_review,
        label="recovery review",
    )
    identity = {
        "schema": "accepted_red_recovery_contract_rebind.v1",
        "source_plan": contract["source_plan"],
        "historical_review": contract["review"],
        "review_bundle_sha256": contract["review_sha"],
        "successor_plan": contract["successor"],
        "legacy_ref": contract["ref"],
        "legacy_tip": legacy_tip,
        "captured_parent": captured_parent,
        "legacy_manifest_path": manifest_path,
        "legacy_manifest_blob_oid": manifest_record["blob_oid"],
        "legacy_cleanup_path": cleanup_path,
        "legacy_cleanup_blob_oid": cleanup_record["blob_oid"],
        "frozen_recovery_plan": recovery_plan,
        "frozen_recovery_code_draft": frozen_draft,
        "frozen_recovery_targets": list(frozen_targets),
        "recovery_revision": revision,
        "recovery_plan": recovery_plan,
        "recovery_plan_blob_oid": plan_record["blob_oid"],
        "recovery_code_draft": frozen_draft,
        "recovery_code_draft_blob_oid": draft_record["blob_oid"],
        "recovery_review": recovery_review,
        "recovery_review_blob_oid": review_record["blob_oid"],
        "recovery_bundle_sha256": recovery_bundle,
        "recovery_targets": [dict(record) for record in target_records],
    }
    binding_sha256 = hashlib.sha256(
        json.dumps(
            identity,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    if binding_sha256 != entry.binding_sha256:
        raise AcceptedRedDurableValidationError(
            "accepted-red recovery rebind digest mismatch"
        )
    return effective


def _accepted_red_commit_parent(root: Path, commit: str, *, label: str) -> str:
    line = _accepted_red_git_text(root, "rev-list", "--parents", "-n", "1", commit)
    parts = line.split()
    if len(parts) != 2 or parts[0] != commit:
        raise AcceptedRedDurableValidationError(
            f"{label} must have exactly one parent"
        )
    return parts[1]


def _accepted_red_changed_paths(
    root: Path,
    parent: str,
    commit: str,
) -> list[str]:
    proc = _accepted_red_git(
        root,
        "diff-tree",
        "--no-commit-id",
        "--name-only",
        "-r",
        "-z",
        parent,
        commit,
    )
    if proc.returncode:
        raise AcceptedRedDurableValidationError("cannot read durable commit path delta")
    try:
        return [
            raw.decode("utf-8", "strict")
            for raw in proc.stdout.split(b"\0")
            if raw
        ]
    except UnicodeDecodeError as exc:
        raise AcceptedRedDurableValidationError(
            "durable commit path delta contains non-UTF-8 paths"
        ) from exc


def _accepted_red_tree_entry(
    root: Path,
    commit: str,
    rel: str,
) -> tuple[str, str, bytes] | None:
    proc = _accepted_red_git(root, "ls-tree", "-z", commit, "--", rel)
    if proc.returncode:
        raise AcceptedRedDurableValidationError(f"cannot read tree entry: {rel}")
    entries = [entry for entry in proc.stdout.split(b"\0") if entry]
    if not entries:
        return None
    if len(entries) != 1:
        raise AcceptedRedDurableValidationError(f"ambiguous tree entry: {rel}")
    try:
        header, raw_path = entries[0].split(b"\t", 1)
        mode, object_type, oid = header.decode("ascii").split()
        path = raw_path.decode("utf-8", "strict")
    except (ValueError, UnicodeDecodeError) as exc:
        raise AcceptedRedDurableValidationError(
            f"malformed tree entry: {rel}"
        ) from exc
    if path != rel or object_type != "blob":
        raise AcceptedRedDurableValidationError(f"tree entry is not an exact blob: {rel}")
    blob = _accepted_red_git(root, "cat-file", "blob", oid)
    if blob.returncode:
        raise AcceptedRedDurableValidationError(f"cannot read blob: {rel}")
    return mode, oid, blob.stdout


def _accepted_red_json_blob(
    root: Path,
    commit: str,
    rel: str,
    *,
    required: bool,
) -> dict[str, object] | None:
    entry = _accepted_red_tree_entry(root, commit, rel)
    if entry is None:
        if required:
            raise AcceptedRedDurableValidationError(f"missing evidence blob: {rel}")
        return None
    mode, _oid, data = entry
    if mode != "100644":
        raise AcceptedRedDurableValidationError(f"evidence JSON mode mismatch: {rel}")
    try:
        payload = json.loads(data.decode("utf-8", "strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcceptedRedDurableValidationError(f"invalid evidence JSON: {rel}") from exc
    if not isinstance(payload, dict):
        raise AcceptedRedDurableValidationError(f"invalid evidence object: {rel}")
    return payload


def _accepted_red_validate_blob_records(
    root: Path,
    commit: str,
    records: object,
    *,
    expected_paths: list[str],
    label: str,
) -> tuple[Mapping[str, object], ...]:
    if not isinstance(records, list):
        raise AcceptedRedDurableValidationError(f"{label} records must be a list")
    result: list[Mapping[str, object]] = []
    for index, raw_record in enumerate(records, start=1):
        if not isinstance(raw_record, dict):
            raise AcceptedRedDurableValidationError(
                f"{label} record {index} must be an object"
            )
        _accepted_red_exact_keys(
            raw_record,
            (
                frozenset({"path", "sha256", "size_bytes", "mode", "blob_oid"}),
            ),
            label=f"{label} record {index}",
        )
        rel = _accepted_red_repo_rel(
            raw_record.get("path"),
            label=f"{label} record {index} path",
        )
        sha = raw_record.get("sha256")
        size = raw_record.get("size_bytes")
        mode = raw_record.get("mode")
        oid = raw_record.get("blob_oid")
        if (
            not isinstance(sha, str)
            or re.fullmatch(r"[0-9a-f]{64}", sha) is None
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size < 0
            or mode not in {"100644", "100755"}
            or not isinstance(oid, str)
            or not oid
        ):
            raise AcceptedRedDurableValidationError(
                f"{label} record has invalid field types: {rel}"
            )
        entry = _accepted_red_tree_entry(root, commit, rel)
        if entry is None:
            raise AcceptedRedDurableValidationError(
                f"{label} record tree path is missing: {rel}"
            )
        tree_mode, tree_oid, data = entry
        if tree_mode != mode or tree_oid != oid:
            raise AcceptedRedDurableValidationError(
                f"{label} record tree/blob identity mismatch: {rel}"
            )
        if hashlib.sha256(data).hexdigest() != sha or len(data) != size:
            raise AcceptedRedDurableValidationError(
                f"{label} record blob digest mismatch: {rel}"
            )
        retained = dict(raw_record)
        retained["_bytes"] = data
        result.append(retained)
    if [record["path"] for record in result] != expected_paths:
        raise AcceptedRedDurableValidationError(f"{label} path inventory mismatch")
    return tuple(result)


def _accepted_red_topology_rebind_identity(
    entry: AcceptedRedSuccessorTopologyRebind,
) -> dict[str, object]:
    """Return the canonical digest input for one topology-only exception."""

    return {
        "schema": entry.schema,
        "rebind_id": entry.rebind_id,
        "source_plan": entry.source_plan,
        "source_draft_rule": entry.source_draft_rule,
        "source_review": entry.source_review,
        "source_review_bundle_sha256": entry.source_review_bundle_sha256,
        "source_open_blockers": list(entry.source_open_blockers),
        "source_scope_ref": entry.source_scope_ref,
        "successor_plan": entry.successor_plan,
        "successor_commit": entry.successor_commit,
        "successor_plan_blob_oid": entry.successor_plan_blob_oid,
        "successor_review": entry.successor_review,
        "successor_review_blob_oid": entry.successor_review_blob_oid,
        "successor_expected_parent": entry.successor_expected_parent,
        "successor_requires_source_in_depends_on": (
            entry.successor_requires_source_in_depends_on
        ),
        "carrier_set_ref": entry.carrier_set_ref,
        "carrier_set_commit": entry.carrier_set_commit,
        "carrier_set_tree": entry.carrier_set_tree,
        "carrier_set_parent": entry.carrier_set_parent,
        "carrier_paths": list(entry.carrier_paths),
        "target_snapshot_ref": entry.target_snapshot_ref,
        "target_snapshot_commit": entry.target_snapshot_commit,
        "targets": [dict(record) for record in entry.targets],
    }


def _accepted_red_same_stem_code_draft(plan_rel: str) -> str:
    return f"docs/code_drafts/{Path(plan_rel).stem}__code_draft.md"


def _accepted_red_resolve_topology_carrier_paths(
    entry: AcceptedRedSuccessorTopologyRebind,
) -> tuple[str, ...]:
    if entry.source_draft_rule != "same_stem_code_draft":
        raise AcceptedRedDurableValidationError(
            "accepted-red topology rebind has unsupported source draft rule"
        )
    tokens = {
        "@source_same_stem_code_draft": _accepted_red_same_stem_code_draft(
            entry.source_plan
        ),
        "@successor_same_stem_code_draft": _accepted_red_same_stem_code_draft(
            entry.successor_plan
        ),
    }
    if tuple(entry.carrier_paths[:2]) != tuple(tokens):
        raise AcceptedRedDurableValidationError(
            "accepted-red topology carrier tokens are not exact"
        )
    resolved: list[str] = []
    for raw_path in entry.carrier_paths:
        if raw_path.startswith("@"):
            if raw_path not in tokens:
                raise AcceptedRedDurableValidationError(
                    "accepted-red topology carrier token is unknown"
                )
            rel = tokens[raw_path]
        else:
            rel = _accepted_red_repo_rel(raw_path, label="topology carrier path")
        resolved.append(rel)
    if not resolved or len(set(resolved)) != len(resolved) or resolved != sorted(resolved):
        raise AcceptedRedDurableValidationError(
            "accepted-red topology carrier inventory is not exact sorted"
        )
    return tuple(resolved)


def _accepted_red_validate_topology_rebind_entry(
    entry: AcceptedRedSuccessorTopologyRebind,
) -> tuple[str, ...]:
    if not isinstance(entry, AcceptedRedSuccessorTopologyRebind):
        raise AcceptedRedDurableValidationError(
            "accepted-red topology rebind entry has an invalid type"
        )
    if entry.schema != "planveyor_accepted_red_successor_topology_rebind.v1":
        raise AcceptedRedDurableValidationError(
            "accepted-red topology rebind schema is invalid"
        )
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", entry.rebind_id):
        raise AcceptedRedDurableValidationError(
            "accepted-red topology rebind id is invalid"
        )
    for label, value in (
        ("topology source plan", entry.source_plan),
        ("topology source review", entry.source_review),
        ("topology successor plan", entry.successor_plan),
        ("topology successor review", entry.successor_review),
    ):
        _accepted_red_repo_rel(value, label=label)
    for label, value in (
        ("topology successor commit", entry.successor_commit),
        ("topology successor plan blob", entry.successor_plan_blob_oid),
        ("topology successor review blob", entry.successor_review_blob_oid),
        ("topology carrier commit", entry.carrier_set_commit),
        ("topology carrier tree", entry.carrier_set_tree),
        ("topology carrier parent", entry.carrier_set_parent),
        ("topology target snapshot commit", entry.target_snapshot_commit),
    ):
        if re.fullmatch(r"[0-9a-f]{40}", value) is None:
            raise AcceptedRedDurableValidationError(f"{label} is invalid")
    for label, value in (
        ("topology source review bundle", entry.source_review_bundle_sha256),
        ("topology entry digest", entry.entry_sha256),
    ):
        if re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise AcceptedRedDurableValidationError(f"{label} is invalid")
    if (
        entry.successor_expected_parent is not None
        or entry.successor_requires_source_in_depends_on is not True
    ):
        raise AcceptedRedDurableValidationError(
            "accepted-red topology rebind parent substitution is invalid"
        )
    if (
        not entry.carrier_set_ref.startswith("refs/planveyor/recovery-inputs/")
        or not entry.target_snapshot_ref.startswith("refs/planveyor/recovery-inputs/")
    ):
        raise AcceptedRedDurableValidationError(
            "accepted-red topology rebind preservation ref is invalid"
        )
    if (
        not entry.source_open_blockers
        or tuple(
            sorted(set(entry.source_open_blockers), key=lambda value: int(value[1:]))
        )
        != entry.source_open_blockers
        or any(re.fullmatch(r"B[1-9][0-9]*", value) is None for value in entry.source_open_blockers)
    ):
        raise AcceptedRedDurableValidationError(
            "accepted-red topology rebind blocker inventory is invalid"
        )
    if entry.source_scope_ref != f"{entry.source_review}#{entry.source_open_blockers[-1]}":
        raise AcceptedRedDurableValidationError(
            "accepted-red topology rebind scope ref is invalid"
        )
    resolved_paths = _accepted_red_resolve_topology_carrier_paths(entry)
    if any(not isinstance(record, Mapping) for record in entry.targets):
        raise AcceptedRedDurableValidationError(
            "accepted-red topology target record is not an object"
        )
    targets = [dict(record) for record in entry.targets]
    target_paths = [
        _accepted_red_repo_rel(record.get("path"), label="topology target path")
        if isinstance(record, Mapping)
        else ""
        for record in targets
    ]
    if (
        not targets
        or target_paths != sorted(target_paths)
        or len(set(target_paths)) != len(target_paths)
    ):
        raise AcceptedRedDurableValidationError(
            "accepted-red topology target inventory is not exact sorted"
        )
    for index, record in enumerate(targets, start=1):
        _accepted_red_exact_keys(
            record,
            (frozenset({"path", "mode", "blob_oid", "size_bytes", "sha256"}),),
            label=f"topology target record {index}",
        )
        size_bytes = record.get("size_bytes")
        if (
            record.get("mode") not in {"100644", "100755"}
            or not isinstance(record.get("blob_oid"), str)
            or re.fullmatch(r"[0-9a-f]{40}", str(record.get("blob_oid"))) is None
            or isinstance(size_bytes, bool)
            or not isinstance(size_bytes, int)
            or size_bytes < 0
            or not isinstance(record.get("sha256"), str)
            or re.fullmatch(r"[0-9a-f]{64}", str(record.get("sha256"))) is None
        ):
            raise AcceptedRedDurableValidationError(
                f"topology target record {index} has invalid fields"
            )
    digest = hashlib.sha256(
        json.dumps(
            _accepted_red_topology_rebind_identity(entry),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    if digest != entry.entry_sha256:
        raise AcceptedRedDurableValidationError(
            "accepted-red topology rebind digest mismatch"
        )
    return resolved_paths


def _accepted_red_worktree_matches_tree(
    root: Path,
    rel: str,
    commit: str,
    *,
    label: str,
) -> tuple[str, str, bytes]:
    path = _accepted_red_regular_path(root, rel, label=label)
    entry = _accepted_red_tree_entry(root, commit, rel)
    if entry is None:
        raise AcceptedRedDurableValidationError(
            f"{label} is absent from frozen carrier set"
        )
    mode, oid, data = entry
    try:
        active = path.read_bytes()
        active_mode = "100755" if path.stat().st_mode & 0o111 else "100644"
    except OSError as exc:
        raise AcceptedRedDurableValidationError(f"cannot read {label}") from exc
    if active != data or active_mode != mode:
        raise AcceptedRedDurableValidationError(
            f"{label} differs from frozen carrier set"
        )
    return mode, oid, data


def validate_accepted_red_successor_topology_rebind(
    root: Path,
    source_rel: str,
    source_text: str,
    successor_rel: str,
    successor_text: str,
) -> None:
    """Authorize exactly one frozen null-parent accepted-red successor tuple."""

    assert_accepted_red_clean_git_authority_environment()
    _accepted_red_assert_no_object_rewrite_topology(root)
    matching_entries = [
        entry
        for entry in ACCEPTED_RED_SUCCESSOR_TOPOLOGY_REBIND_ALLOWLIST
        if isinstance(entry, AcceptedRedSuccessorTopologyRebind)
        and entry.source_plan == source_rel
        and entry.successor_plan == successor_rel
    ]
    if (
        len(ACCEPTED_RED_SUCCESSOR_TOPOLOGY_REBIND_ALLOWLIST) != 1
        or len(matching_entries) != 1
    ):
        raise AcceptedRedDurableValidationError(
            "accepted-red topology rebind is not a unique incident authority"
        )
    entry = matching_entries[0]
    resolved_carriers = _accepted_red_validate_topology_rebind_entry(entry)

    target_tip = _accepted_red_git_text(
        root,
        "rev-parse",
        "--verify",
        f"{entry.target_snapshot_ref}^{{commit}}",
    )
    carrier_tip = _accepted_red_git_text(
        root,
        "rev-parse",
        "--verify",
        f"{entry.carrier_set_ref}^{{commit}}",
    )
    if target_tip != entry.target_snapshot_commit or carrier_tip != entry.carrier_set_commit:
        raise AcceptedRedDurableValidationError(
            "accepted-red topology preservation ref tip mismatch"
        )
    if _accepted_red_git_text(root, "rev-parse", f"{carrier_tip}^{{tree}}") != entry.carrier_set_tree:
        raise AcceptedRedDurableValidationError(
            "accepted-red topology carrier tree mismatch"
        )
    if _accepted_red_commit_parent(root, carrier_tip, label="topology carrier set") != entry.carrier_set_parent:
        raise AcceptedRedDurableValidationError(
            "accepted-red topology carrier parent mismatch"
        )
    if entry.carrier_set_parent != entry.target_snapshot_commit:
        raise AcceptedRedDurableValidationError(
            "accepted-red topology carrier parent is not the target snapshot"
        )
    successor_probe = _accepted_red_git(
        root,
        "cat-file",
        "-e",
        f"{entry.successor_commit}^{{commit}}",
    )
    if successor_probe.returncode:
        raise AcceptedRedDurableValidationError(
            "accepted-red topology successor commit is unavailable"
        )

    source_draft = _accepted_red_same_stem_code_draft(source_rel)
    successor_draft = _accepted_red_same_stem_code_draft(successor_rel)
    required_carriers = {
        source_rel,
        source_draft,
        entry.source_review,
        successor_rel,
        successor_draft,
        entry.successor_review,
    }
    if not required_carriers.issubset(resolved_carriers):
        raise AcceptedRedDurableValidationError(
            "accepted-red topology carrier inventory lacks required identities"
        )
    active_carriers: dict[str, tuple[str, str, bytes]] = {}
    for rel in resolved_carriers:
        active_carriers[rel] = _accepted_red_worktree_matches_tree(
            root,
            rel,
            carrier_tip,
            label="topology carrier",
        )
    source_entry = active_carriers.get(source_rel)
    successor_entry = active_carriers.get(successor_rel)
    if source_entry is None or successor_entry is None:
        raise AcceptedRedDurableValidationError(
            "accepted-red topology carrier inventory lacks source or successor"
        )
    if source_text.encode("utf-8") != source_entry[2] or successor_text.encode("utf-8") != successor_entry[2]:
        raise AcceptedRedDurableValidationError(
            "accepted-red topology active carrier text mismatch"
        )

    for rel, expected_oid in (
        (entry.successor_plan, entry.successor_plan_blob_oid),
        (entry.successor_review, entry.successor_review_blob_oid),
    ):
        successor_record = _accepted_red_tree_entry(root, entry.successor_commit, rel)
        carrier_record = active_carriers.get(rel)
        if (
            successor_record is None
            or carrier_record is None
            or successor_record[1] != expected_oid
            or successor_record != carrier_record
        ):
            raise AcceptedRedDurableValidationError(
                "accepted-red topology terminal successor blob mismatch"
            )

    if source_draft not in active_carriers or successor_draft not in active_carriers:
        raise AcceptedRedDurableValidationError(
            "accepted-red topology same-stem draft carrier is missing"
        )
    try:
        source_meta = parse_plan_meta(source_entry[2].decode("utf-8", "strict"))
        source_scope = source_meta.get("scope_expansion")
        source_draft_meta = _accepted_red_fenced_json(
            active_carriers[source_draft][2].decode("utf-8", "strict"),
            "code_draft_meta",
        )
        source_review_text = active_carriers[entry.source_review][2].decode(
            "utf-8",
            "strict",
        )
        successor_meta = parse_plan_meta(successor_entry[2].decode("utf-8", "strict"))
        successor_review_text = active_carriers[entry.successor_review][2].decode(
            "utf-8",
            "strict",
        )
    except (UnicodeDecodeError, ValueError, AcceptedRedDurableValidationError) as exc:
        raise AcceptedRedDurableValidationError(
            "accepted-red topology carrier content is invalid"
        ) from exc
    source_statuses = re.findall(
        r"^\*\*Status:\*\*\s*(.+?)\s*$",
        source_entry[2].decode("utf-8", "strict"),
        re.MULTILINE,
    )
    successor_plan_statuses = re.findall(
        r"^\*\*Status:\*\*\s*(.+?)\s*$",
        successor_entry[2].decode("utf-8", "strict"),
        re.MULTILINE,
    )
    if (
        len(source_statuses) != 1
        or source_statuses[0].strip() != "Superseded"
        or not isinstance(source_scope, Mapping)
        or source_scope.get("state") != "architect_accepted"
        or source_scope.get("source_ref") != entry.source_scope_ref
        or source_meta.get("next_plans") != [successor_rel]
    ):
        raise AcceptedRedDurableValidationError(
            "accepted-red topology source scope identity mismatch"
        )
    if source_draft_meta.get("plan") != source_rel:
        raise AcceptedRedDurableValidationError(
            "accepted-red topology source draft identity mismatch"
        )
    source_targets_raw = source_draft_meta.get("targets")
    if not isinstance(source_targets_raw, list):
        raise AcceptedRedDurableValidationError(
            "accepted-red topology source draft target inventory is invalid"
        )
    source_targets = []
    for target in source_targets_raw:
        if not isinstance(target, Mapping):
            raise AcceptedRedDurableValidationError(
                "accepted-red topology source draft target is invalid"
            )
        source_targets.append(
            _accepted_red_repo_rel(
                target.get("path"),
                label="topology source draft target",
            )
        )
    expected_targets = [str(record["path"]) for record in entry.targets]
    if sorted(source_targets) != expected_targets or len(set(source_targets)) != len(source_targets):
        raise AcceptedRedDurableValidationError(
            "accepted-red topology source draft target inventory mismatch"
        )
    review_target = re.search(
        r"^\*\*Target:\*\*\s*BUNDLE=current bundle_sha256=([0-9a-f]{64})\s*$",
        source_review_text,
        re.MULTILINE,
    )
    review_status = re.search(
        r"^\*\*Status:\*\*\s*(.+?)\s*$",
        source_review_text,
        re.MULTILINE,
    )
    try:
        source_blockers = accepted_red_topology_open_blocker_ids(source_review_text)
    except CurrentOpenBlockerError as exc:
        raise AcceptedRedDurableValidationError(
            "accepted-red topology source blocker carrier is invalid"
        ) from exc
    if (
        review_target is None
        or review_target.group(1) != entry.source_review_bundle_sha256
        or review_status is None
        or "❌" not in review_status.group(1)
        or source_blockers != entry.source_open_blockers
    ):
        raise AcceptedRedDurableValidationError(
            "accepted-red topology source review identity mismatch"
        )
    successor_parent = successor_meta.get("parent")
    depends_on = successor_meta.get("depends_on")
    if (
        "parent" not in successor_meta
        or successor_parent is not entry.successor_expected_parent
        or not isinstance(depends_on, list)
        or depends_on.count(source_rel) != 1
        or len(successor_plan_statuses) != 1
        or successor_plan_statuses[0].strip() != "Done"
    ):
        raise AcceptedRedDurableValidationError(
            "accepted-red topology successor backlink identity mismatch"
        )
    successor_statuses = re.findall(
        r"^\*\*Status:\*\*\s*(.+?)\s*$",
        re.split(r"^##(?:\s|$)", successor_review_text, maxsplit=1, flags=re.MULTILINE)[0],
        re.MULTILINE,
    )
    if len(successor_statuses) != 1 or REVIEW_OK_STATUS_RE.fullmatch(successor_statuses[0]) is None:
        raise AcceptedRedDurableValidationError(
            "accepted-red topology successor review is not exact green"
        )

    target_records = _accepted_red_validate_blob_records(
        root,
        entry.target_snapshot_commit,
        list(entry.targets),
        expected_paths=expected_targets,
        label="topology target",
    )
    target_bundle, recomputed_records = _accepted_red_revision_bundle(
        root,
        entry.target_snapshot_commit,
        expected_targets,
    )
    if (
        target_bundle != entry.source_review_bundle_sha256
        or tuple(
            {key: value for key, value in record.items() if key != "_bytes"}
            for record in target_records
        )
        != tuple(dict(record) for record in recomputed_records)
    ):
        raise AcceptedRedDurableValidationError(
            "accepted-red topology target snapshot mismatch"
        )


def _accepted_red_snapshot_command(
    context: ContractContext | None,
    helper: Path,
    arguments: Sequence[str],
) -> list[str]:
    if context is not None and context.state == "engaged":
        return contract_authority_children.python_entry_argv(
            context,
            helper,
            arguments,
            python_executable=sys.executable,
        )
    return [sys.executable, "-B", str(helper), *arguments]


def _accepted_red_validate_legacy_review(
    root: Path,
    recovery_rel: str,
    *,
    context: ContractContext | None = None,
) -> None:
    review_rel = resolve_accepted_red_review_path(root, recovery_rel)
    review_path = _accepted_red_regular_path(
        root,
        review_rel,
        label="legacy recovery review",
    )
    try:
        review_text = review_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise AcceptedRedDurableValidationError(
            "cannot read legacy recovery review"
        ) from exc
    target_match = re.search(
        r"^\*\*Target:\*\*\s*BUNDLE=current bundle_sha256=([0-9a-f]{64})\s*$",
        review_text,
        re.MULTILINE,
    )
    if target_match is None:
        raise AcceptedRedDurableValidationError(
            "legacy recovery review has no exact current-bundle target"
        )
    helper = SCRIPT_DIR / "review_target_snapshot.py"
    snapshot_args = [
        recovery_rel,
        "--current-bundle",
        "--project-root",
        str(root),
    ]
    try:
        snapshot_command = _accepted_red_snapshot_command(context, helper, snapshot_args)
    except contract_authority_children.AuthorityChildLaunchError as exc:
        raise AcceptedRedDurableValidationError(
            "legacy recovery snapshot authority launch failed"
        ) from exc
    snapshot_env = accepted_red_git_env()
    if context is not None and context.state == "engaged":
        snapshot_env["_PLANVEYOR_AUTHORITY_CONTEXT_V1"] = context_to_json(context)
    proc = subprocess.run(
        snapshot_command,
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        env=snapshot_env,
    )
    if proc.returncode:
        raise AcceptedRedDurableValidationError(
            proc.stderr.strip() or "legacy recovery snapshot failed"
        )
    try:
        snapshot = review_target_snapshot.validate_snapshot_payload(
            json.loads(proc.stdout)
        )
    except (json.JSONDecodeError, review_target_snapshot.SnapshotError) as exc:
        raise AcceptedRedDurableValidationError(
            "legacy recovery snapshot payload is invalid"
        ) from exc
    if snapshot["bundle_sha256"] != target_match.group(1):
        raise AcceptedRedDurableValidationError(
            "legacy recovery review target differs from the fresh recovery bundle"
        )


def _accepted_red_validate_manifest(
    root: Path,
    capture_commit: str,
    contract: Mapping[str, object],
    *,
    legacy_tip: str | None = None,
) -> tuple[
    dict[str, object],
    tuple[Mapping[str, object], ...],
    tuple[Mapping[str, object], ...],
    dict[str, object],
    str,
]:
    manifest_path = str(contract["manifest_path"])
    cleanup_path = str(contract["cleanup_path"])
    if _accepted_red_tree_entry(root, capture_commit, cleanup_path) is not None:
        raise AcceptedRedDurableValidationError(
            "capture commit unexpectedly contains cleanup carrier"
        )
    manifest = _accepted_red_json_blob(
        root,
        capture_commit,
        manifest_path,
        required=True,
    )
    assert manifest is not None
    base_keys = frozenset(
        {
            "schema",
            "source_plan",
            "recovery_plan",
            "historical_review",
            "review_target",
            "review_bundle_sha256",
            "successor_plan",
            "captured_parent",
            "recovery_ref",
            "recovery_manifest_path",
            "recovery_cleanup_path",
            "targets",
            "routing_carriers",
        }
    )
    frozen_keys = base_keys | {"recovery_code_draft", "recovery_targets"}
    bridged_keys = frozen_keys | {
        "snapshot_bridge",
        "recovery_plan_blob_oid",
        "recovery_code_draft_blob_oid",
    }
    _accepted_red_exact_keys(
        manifest,
        (base_keys, frozen_keys, bridged_keys),
        label="manifest",
    )
    expected_identity = {
        "schema": "planveyor_rejected_baseline.v1",
        "source_plan": contract["source_plan"],
        "historical_review": contract["review"],
        "review_target": f"BUNDLE=current bundle_sha256={contract['review_sha']}",
        "review_bundle_sha256": contract["review_sha"],
        "successor_plan": contract["successor"],
        "recovery_ref": contract["ref"],
        "recovery_manifest_path": manifest_path,
        "recovery_cleanup_path": cleanup_path,
    }
    for key, expected in expected_identity.items():
        if manifest.get(key) != expected:
            raise AcceptedRedDurableValidationError(
                f"manifest identity mismatch: {key}"
            )
    capture_parent = _accepted_red_commit_parent(
        root,
        capture_commit,
        label="capture commit",
    )
    if manifest.get("captured_parent") != capture_parent:
        raise AcceptedRedDurableValidationError("capture parent mismatch")
    changed_paths = _accepted_red_changed_paths(
        root,
        capture_parent,
        capture_commit,
    )
    contract_targets = list(cast(Iterable[str], contract["targets"]))
    contract_routing = list(cast(Iterable[str], contract["routing"]))
    allowed_changed_paths = {
        *contract_targets,
        *contract_routing,
        manifest_path,
    }
    if manifest_path not in changed_paths or not set(changed_paths).issubset(
        allowed_changed_paths
    ):
        raise AcceptedRedDurableValidationError(
            "capture commit path delta is outside the exact evidence inventory"
        )

    targets = _accepted_red_validate_blob_records(
        root,
        capture_commit,
        manifest.get("targets"),
        expected_paths=contract_targets,
        label="target",
    )
    routing = _accepted_red_validate_blob_records(
        root,
        capture_commit,
        manifest.get("routing_carriers"),
        expected_paths=contract_routing,
        label="routing",
    )
    recovery_rel = manifest.get("recovery_plan")
    if not isinstance(recovery_rel, str):
        raise AcceptedRedDurableValidationError(
            "manifest recovery_plan must be a string"
        )
    manifest_keys = frozenset(manifest)
    rebind_entry = (
        _accepted_red_recovery_contract_rebind_entry(
            contract,
            manifest,
            legacy_tip,
        )
        if legacy_tip is not None and manifest_keys == frozen_keys
        else None
    )
    if rebind_entry is not None:
        assert legacy_tip is not None
        recovery_contract = _accepted_red_validate_recovery_contract_rebind(
            root,
            contract,
            manifest,
            legacy_tip,
            rebind_entry,
        )
    else:
        recovery_contract = parse_accepted_red_recovery_contract(
            root,
            recovery_rel,
            str(contract["source_plan"]),
            contract_targets,
            allow_terminal_status=True,
            carrier_commit=(
                capture_parent
                if manifest_keys == bridged_keys
                else None
            ),
        )
    if manifest_keys in {frozen_keys, bridged_keys}:
        if rebind_entry is None:
            for key in ("recovery_code_draft", "recovery_targets"):
                if manifest.get(key) != recovery_contract[key]:
                    raise AcceptedRedDurableValidationError(
                        f"manifest recovery contract mismatch: {key}"
                    )
            if manifest.get("snapshot_bridge") != recovery_contract["snapshot_bridge"]:
                raise AcceptedRedDurableValidationError(
                    "manifest recovery contract mismatch: snapshot_bridge"
                )
        if manifest_keys == bridged_keys:
            for record in routing:
                rel = str(record["path"])
                entry = _accepted_red_tree_entry(root, capture_parent, rel)
                if entry is None:
                    raise AcceptedRedDurableValidationError(
                        f"manifest routing carrier is absent from capture parent: {rel}"
                    )
                mode, oid, data = entry
                if (
                    mode != record["mode"]
                    or oid != record["blob_oid"]
                    or hashlib.sha256(data).hexdigest() != record["sha256"]
                    or len(data) != record["size_bytes"]
                ):
                    raise AcceptedRedDurableValidationError(
                        f"manifest routing carrier differs from capture parent: {rel}"
                    )
            for manifest_key, recovery_key in (
                ("recovery_plan_blob_oid", "recovery_plan"),
                ("recovery_code_draft_blob_oid", "recovery_code_draft"),
            ):
                entry = _accepted_red_tree_entry(
                    root,
                    capture_parent,
                    str(recovery_contract[recovery_key]),
                )
                if entry is None or entry[1] != manifest.get(manifest_key):
                    raise AcceptedRedDurableValidationError(
                        f"manifest recovery contract mismatch: {manifest_key}"
                    )
        recovery_contract_state = (
            "allowlisted_terminal_rebind"
            if rebind_entry is not None
            else "manifest_frozen"
        )
    else:
        recovery_contract_state = "legacy_pending_review"
    return (
        manifest,
        targets,
        routing,
        recovery_contract,
        recovery_contract_state,
    )


def validate_accepted_red_capture_commit(
    root: Path,
    capture_commit: str,
    contract: Mapping[str, object],
) -> None:
    """Validate a candidate capture commit before publishing its evidence ref."""

    _accepted_red_assert_no_object_rewrite_topology(root)
    _accepted_red_validate_manifest(root, capture_commit, contract)


def validate_accepted_red_cleanup_candidate(
    root: Path,
    cleanup_commit: str,
    capture_commit: str,
    contract: Mapping[str, object],
    manifest: Mapping[str, object],
    recovery_contract: Mapping[str, object],
    recovery_contract_state: str,
) -> dict[str, object]:
    if (
        _accepted_red_commit_parent(root, cleanup_commit, label="cleanup commit")
        != capture_commit
    ):
        raise AcceptedRedDurableValidationError("cleanup parent mismatch")
    if _accepted_red_changed_paths(root, capture_commit, cleanup_commit) != [
        str(contract["cleanup_path"])
    ]:
        raise AcceptedRedDurableValidationError(
            "cleanup commit must change only the cleanup carrier"
        )
    cleanup = _accepted_red_json_blob(
        root,
        cleanup_commit,
        str(contract["cleanup_path"]),
        required=True,
    )
    assert cleanup is not None
    base_keys = frozenset(
        {
            "schema",
            "source_plan",
            "recovery_plan",
            "recovery_ref",
            "review_bundle_sha256",
            "capture_commit",
            "captured_parent",
            "cleanup_head",
            "targets",
            "routing_carriers",
        }
    )
    frozen_keys = base_keys | {"recovery_code_draft", "recovery_targets"}
    frozen_contract_states = {
        "manifest_frozen",
        "allowlisted_terminal_rebind",
    }
    expected_key_set = (
        frozen_keys
        if recovery_contract_state in frozen_contract_states
        else base_keys
    )
    _accepted_red_exact_keys(
        cleanup,
        (expected_key_set,),
        label="cleanup",
    )
    expected_identity: dict[str, object] = {
        "schema": "planveyor_rejected_baseline_cleanup.v1",
        "source_plan": contract["source_plan"],
        "recovery_plan": manifest["recovery_plan"],
        "recovery_ref": contract["ref"],
        "review_bundle_sha256": contract["review_sha"],
        "capture_commit": capture_commit,
        "captured_parent": manifest["captured_parent"],
        "cleanup_head": manifest["captured_parent"],
    }
    if recovery_contract_state in frozen_contract_states:
        expected_identity.update(
            recovery_code_draft=manifest["recovery_code_draft"],
            recovery_targets=manifest["recovery_targets"],
        )
    for key, expected in expected_identity.items():
        if cleanup.get(key) != expected:
            raise AcceptedRedDurableValidationError(
                f"cleanup identity mismatch: {key}"
            )

    raw_targets = cleanup.get("targets")
    if not isinstance(raw_targets, list):
        raise AcceptedRedDurableValidationError("cleanup targets must be a list")
    expected_paths = list(cast(Iterable[str], contract["targets"]))
    if [
        item.get("path") if isinstance(item, dict) else None
        for item in raw_targets
    ] != expected_paths:
        raise AcceptedRedDurableValidationError(
            "cleanup target inventory mismatch"
        )
    cleanup_head = str(cleanup["cleanup_head"])
    for index, item in enumerate(raw_targets, start=1):
        assert isinstance(item, dict)
        rel = _accepted_red_repo_rel(
            item.get("path"),
            label=f"cleanup target {index} path",
        )
        entry = _accepted_red_tree_entry(root, cleanup_head, rel)
        if item.get("state") == "absent":
            _accepted_red_exact_keys(
                item,
                (frozenset({"path", "state"}),),
                label=f"cleanup target {index}",
            )
            if entry is not None:
                raise AcceptedRedDurableValidationError(
                    f"cleanup absent record mismatch: {rel}"
                )
            continue
        if item.get("state") != "head":
            raise AcceptedRedDurableValidationError(
                f"cleanup target state mismatch: {rel}"
            )
        _accepted_red_exact_keys(
            item,
            (
                frozenset(
                    {
                        "path",
                        "state",
                        "sha256",
                        "size_bytes",
                        "mode",
                        "blob_oid",
                    }
                ),
            ),
            label=f"cleanup target {index}",
        )
        if (
            not isinstance(item.get("sha256"), str)
            or re.fullmatch(r"[0-9a-f]{64}", str(item["sha256"])) is None
            or isinstance(item.get("size_bytes"), bool)
            or not isinstance(item.get("size_bytes"), int)
            or int(item["size_bytes"]) < 0
            or item.get("mode") not in {"100644", "100755"}
            or not isinstance(item.get("blob_oid"), str)
            or not item["blob_oid"]
        ):
            raise AcceptedRedDurableValidationError(
                f"cleanup HEAD record has invalid field types: {rel}"
            )
        if entry is None:
            raise AcceptedRedDurableValidationError(
                f"cleanup HEAD record is missing: {rel}"
            )
        mode, oid, data = entry
        if (
            item.get("mode") != mode
            or item.get("blob_oid") != oid
            or item.get("sha256") != hashlib.sha256(data).hexdigest()
            or item.get("size_bytes") != len(data)
        ):
            raise AcceptedRedDurableValidationError(
                f"cleanup HEAD record mismatch: {rel}"
            )
    if cleanup.get("routing_carriers") != manifest.get("routing_carriers"):
        raise AcceptedRedDurableValidationError(
            "cleanup routing-carrier readback mismatch"
        )
    return cleanup


def validate_accepted_red_durable_ref(
    root: Path,
    contract: Mapping[str, object],
    *,
    context: ContractContext | None = None,
) -> AcceptedRedDurableRefResult:
    """Validate the complete accepted-red evidence ref without mutating Git state."""

    ref = contract.get("ref")
    if not isinstance(ref, str) or not ref.startswith("refs/planveyor/rejected-baselines/"):
        return AcceptedRedDurableRefResult("invalid", "invalid recovery ref identity")
    try:
        _accepted_red_assert_no_object_rewrite_topology(root)
    except AcceptedRedDurableValidationError as exc:
        return AcceptedRedDurableRefResult("invalid", str(exc))
    exists = _accepted_red_git(root, "show-ref", "--verify", "--quiet", ref)
    if exists.returncode == 1:
        return AcceptedRedDurableRefResult("missing", "durable recovery ref is absent")
    if exists.returncode:
        detail = exists.stderr.decode("utf-8", "replace").strip()
        return AcceptedRedDurableRefResult(
            "invalid",
            detail or "cannot inspect durable recovery ref",
        )
    try:
        tip = _accepted_red_git_text(root, "rev-parse", "--verify", f"{ref}^{{commit}}")
        cleanup_path = _accepted_red_repo_rel(
            contract.get("cleanup_path"),
            label="cleanup path",
        )
        manifest_path = _accepted_red_repo_rel(
            contract.get("manifest_path"),
            label="manifest path",
        )
        if not manifest_path.endswith("/manifest.json") or not cleanup_path.endswith(
            "/cleanup.json"
        ):
            raise AcceptedRedDurableValidationError(
                "manifest/cleanup path identity is invalid"
            )
        cleanup_at_tip = _accepted_red_tree_entry(root, tip, cleanup_path)
        if cleanup_at_tip is not None:
            capture_commit = _accepted_red_commit_parent(
                root,
                tip,
                label="cleanup commit",
            )
            cleanup_commit = tip
        else:
            try:
                (
                    manifest,
                    targets,
                    routing,
                    recovery_contract,
                    recovery_contract_state,
                ) = _accepted_red_validate_manifest(
                    root,
                    tip,
                    contract,
                    legacy_tip=tip,
                )
            except AcceptedRedDurableValidationError as direct_error:
                parent = _accepted_red_commit_parent(root, tip, label="ref tip")
                try:
                    _accepted_red_validate_manifest(
                        root,
                        parent,
                        contract,
                        legacy_tip=tip,
                    )
                except AcceptedRedDurableValidationError:
                    raise direct_error
                raise AcceptedRedDurableValidationError(
                    "cleanup topology is claimed but cleanup carrier is missing"
                ) from direct_error
            if recovery_contract_state == "legacy_pending_review":
                _accepted_red_validate_legacy_review(
                    root,
                    str(manifest["recovery_plan"]),
                    context=context,
                )
                recovery_contract_state = "legacy_review_anchored"
            return AcceptedRedDurableRefResult(
                state="valid_capture",
                reason="durable capture is valid",
                capture_commit=tip,
                manifest=manifest,
                targets=targets,
                routing=routing,
                recovery_contract=recovery_contract,
                recovery_contract_state=recovery_contract_state,
            )

        (
            manifest,
            targets,
            routing,
            recovery_contract,
            recovery_contract_state,
        ) = _accepted_red_validate_manifest(
            root,
            capture_commit,
            contract,
            legacy_tip=tip,
        )
        cleanup = validate_accepted_red_cleanup_candidate(
            root,
            cleanup_commit,
            capture_commit,
            contract,
            manifest,
            recovery_contract,
            recovery_contract_state,
        )
        if recovery_contract_state == "legacy_pending_review":
            if recovery_contract["recovery_status"] in {"done", "superseded"}:
                recovery_contract_state = "legacy_completed_terminal"
            else:
                _accepted_red_validate_legacy_review(
                    root,
                    str(manifest["recovery_plan"]),
                    context=context,
                )
                recovery_contract_state = "legacy_review_anchored"
        return AcceptedRedDurableRefResult(
            state="valid_cleanup",
            reason="durable capture and cleanup are valid",
            capture_commit=capture_commit,
            cleanup_commit=cleanup_commit,
            manifest=manifest,
            cleanup=cleanup,
            targets=targets,
            routing=routing,
            recovery_contract=recovery_contract,
            recovery_contract_state=recovery_contract_state,
        )
    except (AcceptedRedDurableValidationError, KeyError, TypeError, ValueError) as exc:
        return AcceptedRedDurableRefResult("invalid", str(exc))


def classify_accepted_red_disposition(
    *,
    plan_path: Path,
    plan_text: str,
    status_norm: str,
    meta: Mapping[str, object],
    context: ContractContext | None = None,
) -> AcceptedRedDisposition:
    ordinary = AcceptedRedDisposition(
        terminal_disposition="ordinary",
        delivery_green=status_norm == "done",
        staging_policy="allowed",
        durable_capture_required=False,
        successor_plan="",
        historical_review="",
        review_bundle_sha256="",
        reason="accepted-red conjunction is not applicable",
    )
    scope = meta.get("scope_expansion")
    next_plans = meta.get("next_plans")
    structurally_admitted = (
        status_norm == "superseded"
        and isinstance(scope, Mapping)
        and scope.get("state") == "architect_accepted"
        and isinstance(next_plans, list)
        and len(next_plans) == 1
        and isinstance(next_plans[0], str)
    )
    root = _repo_root_for_plan_path(plan_path)
    if root is None:
        return ordinary
    try:
        source_rel = plan_path.resolve().relative_to(root).as_posix()
    except ValueError:
        return ordinary
    stem = plan_path.stem
    durable_ref_admitted = (
        not structurally_admitted
        and _accepted_red_has_rejected_ref(root, stem)
    )
    if not structurally_admitted and not durable_ref_admitted:
        return ordinary

    successor_rel = ""
    review_rel = ""

    def invalid_carrier_disposition() -> AcceptedRedDisposition:
        return AcceptedRedDisposition(
            terminal_disposition="accepted_red_supersession",
            delivery_green=False,
            staging_policy="forbidden",
            durable_capture_required=True,
            successor_plan=successor_rel,
            historical_review=review_rel,
            review_bundle_sha256="",
            reason="accepted_red_carrier_invalid",
        )

    if not structurally_admitted:
        return invalid_carrier_disposition()

    assert isinstance(next_plans, list)
    assert isinstance(next_plans[0], str)
    assert isinstance(scope, Mapping)
    successor_rel = _clean_plan_ref(next_plans[0])
    successor_path = root / successor_rel
    draft_rel = f"docs/code_drafts/{stem}__code_draft.md"
    try:
        review_rel = resolve_accepted_red_review_path(
            root,
            source_rel,
            plan_text=plan_text,
        )
    except AcceptedRedDurableValidationError:
        return AcceptedRedDisposition(
            terminal_disposition="accepted_red_supersession",
            delivery_green=False,
            staging_policy="forbidden",
            durable_capture_required=True,
            successor_plan=successor_rel,
            historical_review="",
            review_bundle_sha256="",
            reason="accepted_red_review_route_invalid",
        )

    draft_path = root / draft_rel
    review_path = root / review_rel
    if not successor_path.is_file() or not draft_path.is_file() or not review_path.is_file():
        return invalid_carrier_disposition()
    try:
        successor_text = successor_path.read_text(encoding="utf-8")
        successor_meta = parse_plan_meta(successor_text)
        draft_text = draft_path.read_text(encoding="utf-8")
        review_text = review_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return invalid_carrier_disposition()
    topology_rebind = False
    if successor_meta.get("parent") != source_rel:
        try:
            validate_accepted_red_successor_topology_rebind(
                root,
                source_rel,
                plan_text,
                successor_rel,
                successor_text,
            )
        except AcceptedRedDurableValidationError:
            return invalid_carrier_disposition()
        topology_rebind = True
    draft_meta: Mapping[str, object] | None = None
    for raw in re.findall(r"```json\s*([\s\S]*?)```", draft_text):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        candidate = parsed.get("code_draft_meta") if isinstance(parsed, Mapping) else None
        if isinstance(candidate, Mapping):
            draft_meta = candidate
            break
    if draft_meta is None or draft_meta.get("plan") != source_rel:
        return invalid_carrier_disposition()
    target_match = re.search(
        r"^\*\*Target:\*\*\s*BUNDLE=current bundle_sha256=([0-9a-f]{64})\s*$",
        review_text,
        re.MULTILINE,
    )
    status_match = re.search(r"^\*\*Status:\*\*\s*(.+?)\s*$", review_text, re.MULTILINE)
    review_sha = target_match.group(1) if target_match is not None else ""

    def invalid_review_disposition() -> AcceptedRedDisposition:
        return AcceptedRedDisposition(
            terminal_disposition="accepted_red_supersession",
            delivery_green=False,
            staging_policy="forbidden",
            durable_capture_required=True,
            successor_plan=successor_rel,
            historical_review=review_rel,
            review_bundle_sha256=review_sha,
            reason="accepted_red_review_invalid",
        )

    if target_match is None or status_match is None or "❌" not in status_match.group(1):
        return invalid_review_disposition()
    try:
        current_blockers = (
            accepted_red_topology_open_blocker_ids(review_text)
            if topology_rebind
            else current_open_blocker_ids(review_text)
        )
        inherited_blockers = successor_inherited_blocker_ids(
            successor_text,
            review_rel,
        )
    except CurrentOpenBlockerError:
        return invalid_review_disposition()
    if inherited_blockers != current_blockers:
        return invalid_review_disposition()
    source_ref = scope.get("source_ref")
    if source_ref not in {f"{review_rel}#{blocker}" for blocker in current_blockers}:
        return invalid_review_disposition()
    targets_raw = draft_meta.get("targets")
    if not isinstance(targets_raw, list) or not targets_raw:
        return invalid_carrier_disposition()
    targets: list[str] = []
    for item in targets_raw:
        if not isinstance(item, Mapping):
            return invalid_carrier_disposition()
        try:
            targets.append(
                _accepted_red_repo_rel(
                    item.get("path"),
                    label="source target",
                )
            )
        except AcceptedRedDurableValidationError:
            return invalid_carrier_disposition()
    targets = sorted(targets)
    if len(set(targets)) != len(targets):
        return invalid_carrier_disposition()
    review_sha = target_match.group(1)
    snapshot_helper = SCRIPT_DIR / "review_target_snapshot.py"
    snapshot_args = [
        source_rel,
        "--current-bundle",
        "--project-root",
        str(root),
    ]
    try:
        snapshot_command = _accepted_red_snapshot_command(context, snapshot_helper, snapshot_args)
    except contract_authority_children.AuthorityChildLaunchError:
        return invalid_carrier_disposition()
    snapshot_kwargs: dict[str, Any] = {
        "cwd": root,
        "capture_output": True,
        "text": True,
        "check": False,
    }
    if context is not None and context.state == "engaged":
        snapshot_env = os.environ.copy()
        snapshot_env["_PLANVEYOR_AUTHORITY_CONTEXT_V1"] = context_to_json(context)
        snapshot_kwargs["env"] = snapshot_env
    snapshot = subprocess.run(snapshot_command, **snapshot_kwargs)
    snapshot_matches = False
    if snapshot.returncode == 0:
        try:
            snapshot_payload = review_target_snapshot.validate_snapshot_payload(
                json.loads(snapshot.stdout)
            )
        except (json.JSONDecodeError, review_target_snapshot.SnapshotError):
            pass
        else:
            snapshot_matches = snapshot_payload["bundle_sha256"] == review_sha

    evidence_ref = f"refs/planveyor/rejected-baselines/{stem}/{review_sha}"
    prefix = f".planveyor/rejected-baselines/{stem}/{review_sha}"
    contract: dict[str, object] = {
        "source_plan": source_rel,
        "source_stem": stem,
        "draft": draft_rel,
        "review": review_rel,
        "successor": successor_rel,
        "targets": targets,
        "routing": sorted([source_rel, draft_rel, review_rel, successor_rel]),
        "review_sha": review_sha,
        "ref": evidence_ref,
        "manifest_path": f"{prefix}/manifest.json",
        "cleanup_path": f"{prefix}/cleanup.json",
    }
    durable = validate_accepted_red_durable_ref(root, contract, context=context)
    if durable.state in {"valid_capture", "valid_cleanup"}:
        disposition_reason = "accepted_red_durable_capture"
    elif durable.state == "invalid":
        disposition_reason = "accepted_red_snapshot_mismatch_without_valid_durable_ref"
    else:
        if snapshot_matches:
            disposition_reason = "accepted_red_current_snapshot"
        else:
            disposition_reason = "accepted_red_snapshot_mismatch_without_durable_ref"
    return AcceptedRedDisposition(
        terminal_disposition="accepted_red_supersession",
        delivery_green=False,
        staging_policy="forbidden",
        durable_capture_required=True,
        successor_plan=successor_rel,
        historical_review=review_rel,
        review_bundle_sha256=review_sha,
        reason=disposition_reason,
    )


def parse_plan_meta_admission_carrier(plan_text: str) -> dict[str, object]:
    """Parse exactly one valid plan_meta carrier for mode admission."""

    matches: list[dict[str, object]] = []
    in_json = False
    start_line = 0
    buf: list[str] = []
    for line_no, line in enumerate(plan_text.splitlines(), start=1):
        if not in_json and re.match(r"^\s*```json\s*$", line, re.IGNORECASE):
            in_json = True
            start_line = line_no
            buf = []
            continue
        if in_json and re.match(r"^\s*```\s*$", line):
            block = "\n".join(buf).strip()
            in_json = False
            buf = []
            try:
                parsed = json.loads(block)
            except json.JSONDecodeError as exc:
                if "plan_meta" not in block:
                    continue
                raise ValueError(
                    f"Plan hygiene: malformed plan_meta JSON carrier at line {start_line}: {exc.msg}"
                ) from exc
            if not isinstance(parsed, dict) or "plan_meta" not in parsed:
                continue
            meta = parsed.get("plan_meta")
            if not isinstance(meta, dict):
                raise ValueError(
                    f"Plan hygiene: plan_meta carrier at line {start_line} must contain a JSON object"
                )
            matches.append(meta)
            continue
        if in_json:
            buf.append(line)
    if in_json and "plan_meta" in "\n".join(buf):
        raise ValueError(f"Plan hygiene: unterminated plan_meta JSON carrier at line {start_line}")
    if len(matches) != 1:
        raise ValueError(
            f"Plan hygiene: expected exactly 1 valid plan_meta JSON carrier, got {len(matches)}"
        )
    return matches[0]


def manager_mode_admission(plan_meta: Mapping[str, object], actual_mode: str) -> dict[str, object]:
    present = "required_manager_mode" in plan_meta
    raw_required = plan_meta.get("required_manager_mode")
    valid_required = (
        raw_required
        if isinstance(raw_required, str) and raw_required in REQUIRED_MANAGER_MODES
        else None
    )
    if not present:
        state = "unclassified_missing"
        reason = "required_mode_missing"
        source = "missing"
        admitted = False
    elif valid_required is None:
        state = "invalid_required_mode"
        reason = "required_mode_invalid"
        source = "plan_meta.required_manager_mode"
        admitted = False
    elif valid_required == "either":
        state = "admitted"
        reason = "plan_allows_either"
        source = "plan_meta.required_manager_mode"
        admitted = True
    elif valid_required == actual_mode:
        state = "admitted"
        reason = "mode_match"
        source = "plan_meta.required_manager_mode"
        admitted = True
    else:
        state = "mismatch"
        reason = "required_mode_mismatch"
        source = "plan_meta.required_manager_mode"
        admitted = False
    return {
        "required_manager_mode": valid_required,
        "actual_manager_mode": actual_mode,
        "manager_mode_source": source,
        "manager_mode_state": state,
        "manager_mode_admitted": admitted,
        "manager_mode_reason": reason,
    }


def _section_lines_with_numbers(plan_text: str, heading_re: re.Pattern[str]) -> list[tuple[int, str]]:
    in_section = False
    collected: list[tuple[int, str]] = []
    for idx, line in enumerate(plan_text.splitlines(), start=1):
        if not in_section and heading_re.match(line):
            in_section = True
            continue
        if in_section and re.match(r"^\s*##\s+", line):
            break
        if in_section:
            collected.append((idx, line))
    return collected


def _clean_plan_ref(raw_value: object) -> str:
    value = str(raw_value).strip()
    if value.startswith("`") and value.endswith("`") and len(value) >= 2:
        value = value[1:-1].strip()
    return value.strip().strip("`").rstrip(".,;")


def _is_placeholder_child_ref(value: str) -> bool:
    cleaned = _clean_plan_ref(value).strip()
    return not cleaned or bool(PLACEHOLDER_CHILD_VALUE_RE.match(cleaned))


def _is_repo_relative_plan_path(value: str) -> bool:
    cleaned = _clean_plan_ref(value)
    return bool(REPO_RELATIVE_PLAN_PATH_RE.fullmatch(cleaned)) and ".." not in PurePosixPath(cleaned).parts


def _split_route_ref(value: object) -> tuple[str, str]:
    cleaned = _clean_plan_ref(str(value))
    if "#" not in cleaned:
        return cleaned, ""
    path_part, anchor = cleaned.split("#", 1)
    return path_part.strip(), anchor.strip().lower().replace("_", "-")


def _explicit_na_with_reason(value: object) -> bool:
    return bool(SMALL_MODEL_NA_WITH_REASON_RE.search(str(value)))


def execution_queue_plan_entries(plan_text: str) -> list[tuple[int, str]]:
    entries: list[tuple[int, str]] = []
    for line_no, line in _section_lines_with_numbers(plan_text, EXECUTION_QUEUE_HEADING_RE):
        match = re.match(r"^\s*-\s*Plan:\s*(.+?)\s*$", line.strip(), re.IGNORECASE)
        if match:
            entries.append((line_no, _clean_plan_ref(match.group(1))))
    return entries


def concrete_execution_queue_plan_entries(plan_text: str) -> list[tuple[int, str]]:
    return [(line_no, value) for line_no, value in execution_queue_plan_entries(plan_text) if _is_repo_relative_plan_path(value)]


def child_plan_map_entries(plan_text: str) -> list[tuple[int, str]]:
    entries: list[tuple[int, str]] = []
    for line_no, line in _section_lines_with_numbers(plan_text, CHILD_PLAN_MAP_HEADING_RE):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 2:
            continue
        first_cell = cells[0].strip("`").strip().lower()
        second_cell = cells[1].strip()
        if first_cell in {"queue order", "---"} or set(first_cell) <= {"-", " "}:
            continue
        entries.append((line_no, _clean_plan_ref(second_cell)))
    return entries


def _plan_ref_issue(line_no: int | None, value: str) -> DecompositionChildIssue | None:
    if _is_placeholder_child_ref(value):
        return DecompositionChildIssue(
            line_no,
            "decomposition_child_placeholder",
            value,
            "active decomposition child path is placeholder/missing",
        )
    if not _is_repo_relative_plan_path(value):
        return DecompositionChildIssue(
            line_no,
            "decomposition_child_invalid_path",
            value,
            "active decomposition child path must be repo-relative docs/plans/*.md",
        )
    return None


def _concrete_path_values(entries: list[tuple[int | None, str]]) -> list[str]:
    result: list[str] = []
    for _, value in entries:
        cleaned = _clean_plan_ref(value)
        if _plan_ref_issue(None, cleaned) is None:
            result.append(cleaned)
    return result


def _child_file_issue(root: Path | None, value: str) -> DecompositionChildIssue | None:
    if root is None:
        return None
    child_path = root / value
    if not child_path.is_file():
        return DecompositionChildIssue(
            None,
            "decomposition_child_missing_file",
            value,
            "active decomposition child file is missing",
        )
    try:
        _scan_status_line(child_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return DecompositionChildIssue(
            None,
            "decomposition_child_not_lintable",
            value,
            f"active decomposition child is not queue-lintable: {exc}",
        )
    return None


def _repo_root_for_plan_path(
    plan_path: Path,
    *,
    context: ContractContext | None = None,
) -> Path:
    resolved = plan_path.resolve()
    if context is not None and context.state == "engaged":
        root = context.project_root.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError(
                f"Plan path is outside the engaged contract project root: {resolved}"
            ) from exc
        return root
    start = resolved.parent if resolved.is_file() else resolved
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    if resolved.parent.name == "plans" and resolved.parent.parent.name == "docs":
        return resolved.parent.parent.parent
    return start


def _planning_contour_vocab(
    root: Path,
    *,
    context: ContractContext | None = None,
) -> dict[str, frozenset[str]]:
    path = root / "docs/_meta/plan_vocab.json"
    resolved_context = context_for_reader(root, context=context)
    if resolved_context.state == "engaged":
        # Vocabulary is an authority input, unlike the mutable plan and review
        # artifacts the oracle reports on.  An engaged caller must therefore
        # never silently receive the legacy empty-vocabulary fallback.
        parsed = json.loads(
            read_declared_text(
                resolved_context,
                "docs/_meta/plan_vocab.json",
                purpose="plan-status vocabulary",
            )
        )
        if not isinstance(parsed, dict):
            raise ValueError("Engaged plan vocabulary must be a JSON object.")
    else:
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {}
    planning_contour = parsed.get("planning_contour")
    if not isinstance(planning_contour, dict):
        if resolved_context.state == "engaged":
            raise ValueError("Engaged plan vocabulary requires a planning_contour object.")
        return {}

    vocab: dict[str, frozenset[str]] = {}
    for key in (
        "accepted_routes",
        "promoted_artifact_kinds",
        "queue_admission",
        "runner_admission",
        "queue_activation_states",
        "scope_expansion_states",
    ):
        values = planning_contour.get(key)
        if not isinstance(values, list):
            if resolved_context.state == "engaged":
                raise ValueError(f"Engaged plan vocabulary requires list field: planning_contour.{key}.")
            continue
        vocab[key] = frozenset(_normalize_value(str(value)) for value in values if str(value).strip())
    return vocab


def decomposition_child_state(
    plan_text: str,
    *,
    root: Path | None = None,
    context: ContractContext | None = None,
) -> DecompositionChildState:
    # A post-cutover decomposition parent must take its graph from the same
    # canonical top-level Meta carrier as machine-authority admission.  The
    # permissive legacy reader is retained only for older/non-strict callers;
    # otherwise a preamble JSON example could fabricate ``next_plans`` after
    # the strict parent has already been admitted.
    strict_meta = strict_plan_meta_json(plan_text)
    meta: Mapping[str, object]
    if strict_meta.state == "valid" and strict_meta.plan_meta is not None:
        meta = strict_meta.plan_meta
    else:
        meta = parse_plan_meta(plan_text)
    phase_overlay = _normalize_value(str(meta.get("phase_overlay") or ""))
    phase_state = _normalize_value(str(meta.get("phase_state") or ""))
    if phase_overlay != "decomposition_wave":
        return DecompositionChildState("not_decomposition", "plan has no decomposition_wave overlay", (), "none", ())
    if phase_state not in {"active", "parked"}:
        return DecompositionChildState("not_active", "decomposition parent is not active", (), "none", ())

    issues: list[DecompositionChildIssue] = []
    execution_entries = execution_queue_plan_entries(plan_text)
    child_map_entries_raw = child_plan_map_entries(plan_text)
    meta_next_entries: list[tuple[int | None, str]] = []
    next_plans = meta.get("next_plans")
    if isinstance(next_plans, list):
        meta_next_entries = [(None, _clean_plan_ref(item)) for item in next_plans]

    all_entries: list[tuple[str, int | None, str]] = []
    all_entries.extend(("execution_queue", line_no, value) for line_no, value in execution_entries)
    all_entries.extend(("child_plan_map", line_no, value) for line_no, value in child_map_entries_raw)
    all_entries.extend(("next_plans", line_no, value) for line_no, value in meta_next_entries)
    if not all_entries:
        issues.append(
            DecompositionChildIssue(
                None,
                "decomposition_children_missing",
                "",
                f"{phase_state} decomposition has no materialized child graph",
            )
        )

    seen_by_source: dict[str, set[str]] = {}
    for source, line_no, value in all_entries:
        cleaned = _clean_plan_ref(value)
        issue = _plan_ref_issue(line_no, cleaned)
        if issue is not None:
            issues.append(issue)
            continue
        seen = seen_by_source.setdefault(source, set())
        if cleaned in seen:
            issues.append(
                DecompositionChildIssue(
                    line_no,
                    "decomposition_child_duplicate",
                    cleaned,
                    "active decomposition child path is duplicated",
                )
            )
            continue
        seen.add(cleaned)

    execution_paths = _concrete_path_values([(line_no, value) for line_no, value in execution_entries])
    child_map_paths = _concrete_path_values([(line_no, value) for line_no, value in child_map_entries_raw])
    meta_next_paths = _concrete_path_values(meta_next_entries)
    # A canonical planning carrier is never inferred from the bounded routing
    # projection.  Prefer the complete child map when present; a concrete
    # execution queue is an equivalent fallback only when the map is absent.
    canonical_planning_paths = child_map_paths or execution_paths
    canonical_source = "child_plan_map" if child_map_paths else ("execution_queue" if execution_paths else "none")
    if execution_paths and child_map_paths and execution_paths != child_map_paths:
        issues.append(
            DecompositionChildIssue(
                None,
                "decomposition_child_graph_mismatch",
                "execution_queue vs child_plan_map",
                "`## Execution queue` plan list must match `## Child plan map` for decomposition",
            )
        )
    if meta_next_paths and canonical_planning_paths:
        bounded_next_prefix = canonical_planning_paths[: len(meta_next_paths)]
        if meta_next_paths != canonical_planning_paths and meta_next_paths != bounded_next_prefix:
            issues.append(
                DecompositionChildIssue(
                    None,
                    "decomposition_child_graph_mismatch",
                    f"{canonical_source} vs next_plans",
                    "next_plans must equal or be an ordered prefix of the canonical child graph",
                )
            )
    elif meta_next_paths:
        issues.append(
            DecompositionChildIssue(
                None,
                "decomposition_children_missing",
                "next_plans",
                "next_plans requires a complete canonical child map or execution queue",
            )
        )

    selected_paths = execution_paths or meta_next_paths
    selected_source = "execution_queue" if execution_paths else ("next_plans" if meta_next_paths else "none")
    for child in canonical_planning_paths:
        issue = _child_file_issue(root, child)
        if issue is not None:
            issues.append(issue)

    if issues:
        first = issues[0]
        reason = f"{first.kind}: {first.message}" + (f" ({first.value})" if first.value else "")
        return DecompositionChildState(
            "missing",
            reason,
            tuple(selected_paths),
            selected_source,
            tuple(issues),
            tuple(canonical_planning_paths),
        )
    if selected_paths:
        return DecompositionChildState(
            "queue_ready",
            f"{phase_state} decomposition child graph is concrete and queue importable",
            tuple(selected_paths),
            selected_source,
            (),
            tuple(canonical_planning_paths),
        )
    if child_map_paths:
        if phase_state == "parked":
            issue = DecompositionChildIssue(
                None,
                "decomposition_children_missing",
                "child_plan_map",
                "parked decomposition requires a queue-ready child graph",
            )
            return DecompositionChildState(
                "missing",
                f"{issue.kind}: {issue.message} ({issue.value})",
                tuple(child_map_paths),
                "child_plan_map",
                (issue,),
                tuple(canonical_planning_paths),
            )
        return DecompositionChildState(
            "drafted",
            f"{phase_state} decomposition has concrete child map but no queue carrier",
            tuple(child_map_paths),
            "child_plan_map",
            (),
            tuple(canonical_planning_paths),
        )
    return DecompositionChildState(
        "missing",
        f"{phase_state} decomposition has no queue-ready child graph",
        (),
        "none",
        (),
    )


def _filename_ts_value(path: Path) -> int | None:
    match = FILENAME_TS_RE.match(path.name)
    if not match:
        return None
    try:
        return int(match.group("ts").replace("_", ""))
    except ValueError:
        return None


def _small_model_contract_lines(plan_text: str) -> list[tuple[int, str]]:
    return _section_lines_with_numbers(plan_text, SMALL_MODEL_READY_CHILD_HEADING_RE)


def _clean_small_model_cell(value: str) -> str:
    return value.strip().strip("`").strip()


def _normalize_small_model_field(value: str) -> str:
    cleaned = _clean_small_model_cell(value).rstrip(":")
    return SMALL_MODEL_FIELD_BY_NORM.get(_normalize_value(cleaned), "")


def _small_model_contract_fields(plan_text: str) -> dict[str, tuple[int, str]]:
    fields: dict[str, tuple[int, str]] = {}
    for line_no, line in _small_model_contract_lines(plan_text):
        stripped = line.strip()
        if stripped.startswith("|"):
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if len(cells) < 2:
                continue
            field = _normalize_small_model_field(cells[0])
            if not field or field == "Field" or set(_clean_small_model_cell(cells[0])) <= {"-"}:
                continue
            if _normalize_value(cells[0]) in {"field", "---"}:
                continue
            fields[field] = (line_no, "|".join(cells[1:]).strip())
            continue

        bullet_match = re.match(r"^\s*-\s*`?(?P<field>[^:`]+?)`?\s*:\s*(?P<value>.+?)\s*$", line)
        if bullet_match:
            field = _normalize_small_model_field(bullet_match.group("field"))
            if field:
                fields[field] = (line_no, bullet_match.group("value").strip())
    return fields


def _small_model_value_problem(field: str, value: str) -> str | None:
    cleaned = _clean_small_model_cell(value)
    if not cleaned:
        return "missing"
    if SMALL_MODEL_PLACEHOLDER_VALUE_RE.search(cleaned):
        return "placeholder"
    if SMALL_MODEL_ANGLE_PLACEHOLDER_VALUE_RE.fullmatch(cleaned):
        return "placeholder"
    if SMALL_MODEL_VAGUE_VALUE_RE.search(cleaned):
        return "vague"
    if SMALL_MODEL_NA_VALUE_RE.search(cleaned):
        has_reason = bool(SMALL_MODEL_NA_WITH_REASON_RE.search(cleaned))
        if not has_reason:
            return "placeholder"
        if field in SMALL_MODEL_HARD_NA_ALLOWED_FIELDS or field in SMALL_MODEL_WARNING_FIELDS:
            return None
        return "placeholder"
    return None


def small_model_ready_child_findings(
    plan_path: Path,
    *,
    child_path: str | None = None,
    promoted: bool = False,
) -> tuple[SmallModelReadinessFinding, ...]:
    try:
        plan_text = plan_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return (
            SmallModelReadinessFinding(
                child_path or plan_path.as_posix(),
                None,
                "__file__",
                "hard",
                "invalid",
                "",
                f"promoted child plan cannot be read for small-model readiness: {exc}",
                True,
            ),
        )

    if not promoted and not _small_model_contract_lines(plan_text):
        return ()

    rendered_child_path = child_path or plan_path.as_posix()
    fields = _small_model_contract_fields(plan_text)
    findings: list[SmallModelReadinessFinding] = []
    for field in SMALL_MODEL_HARD_FIELDS:
        field_info = fields.get(field)
        if field_info is None:
            findings.append(
                SmallModelReadinessFinding(
                    rendered_child_path,
                    None,
                    field,
                    "hard",
                    "missing",
                    "",
                    f"small-model-ready promoted child is missing `{field}`",
                    True,
                )
            )
            continue
        line_no, value = field_info
        problem = _small_model_value_problem(field, value)
        if problem is None:
            continue
        findings.append(
            SmallModelReadinessFinding(
                rendered_child_path,
                line_no,
                field,
                "hard",
                problem,
                value,
                f"small-model-ready promoted child has {problem} `{field}`",
                True,
            )
        )

    for field in SMALL_MODEL_WARNING_FIELDS:
        field_info = fields.get(field)
        if field_info is None:
            findings.append(
                SmallModelReadinessFinding(
                    rendered_child_path,
                    None,
                    field,
                    "warning",
                    "missing",
                    "",
                    f"small-model-ready warning-first field is missing `{field}`",
                    False,
                )
            )
            continue
        line_no, value = field_info
        problem = _small_model_value_problem(field, value)
        if problem is None:
            continue
        findings.append(
            SmallModelReadinessFinding(
                rendered_child_path,
                line_no,
                field,
                "warning",
                problem,
                value,
                f"small-model-ready warning-first field has {problem} `{field}`",
                False,
            )
        )

    return tuple(findings)


def decomposition_child_readiness_findings(
    plan_text: str,
    *,
    root: Path | None = None,
    child_state: DecompositionChildState | None = None,
) -> tuple[SmallModelReadinessFinding, ...]:
    state = child_state or decomposition_child_state(plan_text, root=root)
    if root is None or state.state != "queue_ready":
        return ()
    findings: list[SmallModelReadinessFinding] = []
    for child in state.concrete_child_paths:
        findings.extend(
            small_model_ready_child_findings(
                root / child,
                child_path=child,
                promoted=True,
            )
        )
    return tuple(findings)


def small_model_readiness_summary(
    findings: tuple[SmallModelReadinessFinding, ...],
    *,
    assessed_children: tuple[str, ...] = (),
) -> tuple[str, str]:
    if not assessed_children:
        return "unknown", "not_applicable"
    if any(finding.blocks_queue for finding in findings):
        return "false", "blocked"
    if findings:
        return "true", "warning"
    return "true", "ready"


def _header_section_lines(plan_text: str, heading_prefix: str) -> list[str]:
    in_section = False
    collected: list[str] = []
    for line in _header_lines(plan_text):
        stripped = line.strip()
        if not in_section and stripped.startswith(heading_prefix):
            in_section = True
            continue
        if not in_section:
            continue
        if stripped.startswith("**") and not stripped.startswith(heading_prefix):
            break
        collected.append(line)
    return collected


def parse_handoff_statuses(plan_text: str) -> dict[str, str]:
    handoffs: dict[str, str] = {}
    for line in _header_section_lines(plan_text, "**Handoff statuses"):
        match = re.match(r"^\s*-\s*`?([^`]+?)`?\s+(?:—|-)\s+(.+?)\s*$", line)
        if not match:
            continue
        handoffs[_normalize_value(match.group(1))] = match.group(2).strip()
    return handoffs


def parse_context_entry(plan_text: str, label: str) -> str | None:
    for line in _header_section_lines(plan_text, "**Context links"):
        match = re.match(rf"^\s*-\s*{re.escape(label)}\s*(.+?)\s*$", line)
        if match:
            return match.group(1).strip()
    return None


def _clean_markdown_table_cell(value: str) -> str:
    cleaned = value.strip()
    if cleaned.startswith("`") and cleaned.endswith("`") and len(cleaned) >= 2:
        cleaned = cleaned[1:-1].strip()
    return cleaned


def _markdown_table_fields(plan_text: str, heading_re: re.Pattern[str]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for _, line in _section_lines_with_numbers(plan_text, heading_re):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 2:
            continue
        key = _clean_markdown_table_cell(cells[0])
        if not key or _normalize_value(key) in {"field", "---"} or set(key) <= {"-"}:
            continue
        fields[key] = _clean_markdown_table_cell("|".join(cells[1:]))
    return fields


def _section_contains_na_value(plan_text: str, heading_re: re.Pattern[str]) -> bool:
    for _, line in _section_lines_with_numbers(plan_text, heading_re):
        stripped = line.strip().strip("`").strip()
        if stripped:
            return stripped.lower().startswith("n/a")
    return False


def _source_route_fields(plan_text: str) -> dict[str, str]:
    return _markdown_table_fields(plan_text, PROMOTED_ROUTE_ARTIFACT_HEADING_RE)


def _analysis_pack_fields(plan_text: str) -> dict[str, str]:
    return _markdown_table_fields(plan_text, ANALYSIS_PACK_HEADING_RE)


def _analysis_pack_ref_rows(plan_text: str) -> list[str]:
    rows: list[str] = []
    for _, line in _section_lines_with_numbers(plan_text, ANALYSIS_PACK_HEADING_RE):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 2:
            continue
        if _normalize_value(_clean_markdown_table_cell(cells[0])) != "analysis_pack_ref":
            continue
        rows.append("|".join(cells[1:]).strip())
    return rows


def _code_draft_meta(draft_text: str) -> dict[str, object] | None:
    in_json = False
    buf: list[str] = []
    metas: list[dict[str, object]] = []
    for line in draft_text.splitlines():
        if not in_json and re.match(r"^\s*```json\s*$", line, re.IGNORECASE):
            in_json = True
            buf = []
            continue
        if in_json and re.match(r"^\s*```\s*$", line):
            block = "\n".join(buf).strip()
            in_json = False
            buf = []
            if "code_draft_meta" not in block:
                continue
            try:
                parsed = json.loads(block)
            except json.JSONDecodeError:
                return None
            meta = parsed.get("code_draft_meta")
            if not isinstance(meta, dict):
                return None
            metas.append(meta)
        if in_json:
            buf.append(line)
    return metas[0] if len(metas) == 1 else None


def _invalid_analysis_pack_authority(
    detail_category: str,
    *,
    authority_text: str = "",
    authority_path: Path | None = None,
    truth_host: str = "",
) -> AnalysisPackAuthorityResolution:
    return AnalysisPackAuthorityResolution(
        mode="external",
        authority_text=authority_text,
        authority_path=authority_path,
        truth_host=truth_host,
        error_token=ANALYSIS_PACK_AUTHORITY_INVALID,
        detail_category=detail_category,
    )


def _analysis_pack_status_norm(effective_status: str | None) -> str:
    return " ".join(str(effective_status or "").replace("`", "").lower().split())


def resolve_analysis_pack_authority(
    *,
    origin_plan_path: Path,
    plan_text: str,
    effective_status: str | None,
) -> AnalysisPackAuthorityResolution:
    """Resolve the sole operational analysis-pack carrier for an origin plan.

    ``effective_status`` is the plan status the caller evaluates: the header
    status, or the simulated status of ``plan_lint --as-status``. ``None`` means
    the status is unreadable. An explicit ``analysis_pack_ref`` row always selects
    the standalone pack; the template sentinel row counts as no ref. Without a ref
    an ``analysis_wave`` plan keeps its plan-resident pack only on
    ``ANALYSIS_PACK_PLAN_RESIDENT_STATUS_NORMS``; every other status, including an
    unreadable one, requires the standalone pack.
    """

    meta = parse_plan_meta(plan_text)
    ref_rows = _analysis_pack_ref_rows(plan_text)
    wave_family = _normalize_value(str(meta.get("wave_family") or ""))
    has_ref = bool(ref_rows) and ref_rows != [ANALYSIS_PACK_TEMPLATE_SENTINEL]
    required_external = (
        wave_family == "analysis_wave"
        and _analysis_pack_status_norm(effective_status) not in ANALYSIS_PACK_PLAN_RESIDENT_STATUS_NORMS
    )
    if not has_ref and not required_external:
        return AnalysisPackAuthorityResolution(
            mode="legacy",
            authority_text=plan_text,
            authority_path=origin_plan_path,
            truth_host=f"{origin_plan_path.as_posix()}#Analysis-pack",
            error_token="",
            detail_category="",
        )
    if not has_ref:
        return _invalid_analysis_pack_authority("ref_missing")
    if len(ref_rows) != 1:
        return _invalid_analysis_pack_authority("ref_malformed")

    ref_match = ANALYSIS_PACK_REF_RE.fullmatch(ref_rows[0])
    if ref_match is None:
        return _invalid_analysis_pack_authority("ref_malformed")
    ref = ref_match.group("ref")
    annotation = ref_match.group("annotation")
    if (
        re.search(r"docs/[A-Za-z0-9_./-]+", annotation, re.IGNORECASE)
        or re.search(r"#Analysis-pack\b", annotation, re.IGNORECASE)
        or any(
            re.search(rf"\b{re.escape(field)}\b", annotation, re.IGNORECASE)
            for field in ANALYSIS_PACK_OPERATIONAL_FIELDS
        )
    ):
        return _invalid_analysis_pack_authority("ref_noncanonical", truth_host=ref)

    repo_root = _repo_root_for_plan_path(origin_plan_path)
    try:
        origin_rel = origin_plan_path.resolve().relative_to(repo_root.resolve()).as_posix()
    except (OSError, ValueError):
        return _invalid_analysis_pack_authority("repo_root_unresolved", truth_host=ref)
    if not origin_rel.startswith("docs/plans/"):
        return _invalid_analysis_pack_authority("repo_root_unresolved", truth_host=ref)

    canonical_ref = f"docs/analysis_packs/{origin_plan_path.stem}.md#Analysis-pack"
    if ref != canonical_ref:
        return _invalid_analysis_pack_authority("ref_noncanonical", truth_host=ref)
    ref_path_text = ref.split("#", 1)[0]
    ref_path = PurePosixPath(ref_path_text)
    if ref_path.is_absolute() or ".." in ref_path.parts or "\\" in ref_path_text:
        return _invalid_analysis_pack_authority("ref_noncanonical", truth_host=ref)

    draft_rel = f"docs/code_drafts/{origin_plan_path.stem}__code_draft.md"
    try:
        draft_snapshot = snapshot_regular_or_absent(repo_root, draft_rel)
    except ObjectIdentityError as exc:
        if exc.reason_code == "ancestor_missing":
            return _invalid_analysis_pack_authority("draft_missing", truth_host=ref)
        return _invalid_analysis_pack_authority("draft_malformed", truth_host=ref)
    if draft_snapshot.state == "absent":
        return _invalid_analysis_pack_authority("draft_missing", truth_host=ref)
    if draft_snapshot.data is None:
        return _invalid_analysis_pack_authority("draft_malformed", truth_host=ref)
    try:
        draft_text = draft_snapshot.data.decode("utf-8")
    except UnicodeDecodeError:
        return _invalid_analysis_pack_authority("draft_malformed", truth_host=ref)
    draft_meta = _code_draft_meta(draft_text)
    if draft_meta is None:
        return _invalid_analysis_pack_authority("draft_malformed", truth_host=ref)
    if draft_meta.get("plan") != origin_rel:
        return _invalid_analysis_pack_authority("draft_malformed", truth_host=ref)
    targets = draft_meta.get("targets")
    if not isinstance(targets, list):
        return _invalid_analysis_pack_authority("draft_malformed", truth_host=ref)
    target_count = sum(
        1
        for target in targets
        if isinstance(target, dict) and target.get("path") == ref_path_text
    )
    if target_count == 0:
        return _invalid_analysis_pack_authority("target_missing", truth_host=ref)
    if target_count != 1:
        return _invalid_analysis_pack_authority("target_ambiguous", truth_host=ref)

    pack_path = repo_root / ref_path_text
    try:
        pack_snapshot = snapshot_regular_or_absent(repo_root, ref_path_text)
    except ObjectIdentityError as exc:
        if exc.reason_code == "ancestor_missing":
            return _invalid_analysis_pack_authority("pack_missing", authority_path=pack_path, truth_host=ref)
        return _invalid_analysis_pack_authority("pack_unreadable", authority_path=pack_path, truth_host=ref)
    if pack_snapshot.state == "absent":
        return _invalid_analysis_pack_authority("pack_missing", authority_path=pack_path, truth_host=ref)
    if pack_snapshot.data is None:
        return _invalid_analysis_pack_authority("pack_unreadable", authority_path=pack_path, truth_host=ref)
    try:
        pack_text = pack_snapshot.data.decode("utf-8")
    except UnicodeDecodeError:
        return _invalid_analysis_pack_authority("pack_unreadable", authority_path=pack_path, truth_host=ref)

    origin_fields = {
        _normalize_value(key.replace("-", "_"))
        for key in _analysis_pack_fields(plan_text)
    }
    if origin_fields & ANALYSIS_PACK_OPERATIONAL_FIELDS:
        return _invalid_analysis_pack_authority(
            "operational_duplicate",
            authority_text=pack_text,
            authority_path=pack_path,
            truth_host=ref,
        )
    return AnalysisPackAuthorityResolution(
        mode="external",
        authority_text=pack_text,
        authority_path=pack_path,
        truth_host=ref,
        error_token="",
        detail_category="",
    )


def _clean_lifecycle_value(value: object) -> str:
    return str(value).strip().strip("`").strip().strip('"').strip("'").strip()


def _lifecycle_key_value_pairs(value: object) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for match in ANALYSIS_ROUTE_LIFECYCLE_KV_RE.finditer(str(value)):
        key = _normalize_value(match.group("key").replace("-", "_"))
        pairs[key] = _clean_lifecycle_value(match.group("value"))
    return pairs


def _analysis_route_lifecycle_fields(plan_text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for carrier in (_analysis_pack_fields(plan_text), _source_route_fields(plan_text)):
        for raw_key, raw_value in carrier.items():
            key = _normalize_value(raw_key.replace("-", "_"))
            value = _clean_lifecycle_value(raw_value)
            if key in {"execution_budget", "stale_trigger", "requirement_slices"}:
                fields.update(_lifecycle_key_value_pairs(value))
            if key in {
                "budget_status",
                "source_ref_floor",
                "route_iteration_limit",
                "needs_analysis_depth_cap",
                "current_needs_analysis_depth",
                "stop_owner",
                "exhaustion_action",
                "override_ref",
                "source_subject_baseline",
                "current_source_subject",
                "source_refs_baseline",
                "current_source_refs",
                "change_ref",
                "action",
            }:
                fields[key] = value
    return fields


def _lifecycle_int(value: str) -> int | None:
    match = re.search(r"-?\d+", value)
    if not match:
        return None
    try:
        return int(match.group(0))
    except ValueError:
        return None


def _lifecycle_has_override(value: str) -> bool:
    cleaned = _clean_lifecycle_value(value)
    if not cleaned:
        return False
    if PLACEHOLDER_CHILD_VALUE_RE.match(cleaned):
        return False
    if cleaned.lower().startswith("n/a"):
        return False
    return True


def _lifecycle_values_differ(left: str, right: str) -> bool:
    return _normalize_value(_clean_lifecycle_value(left)) != _normalize_value(_clean_lifecycle_value(right))


def classify_analysis_route_lifecycle(plan_text: str) -> AnalysisRouteLifecycleState:
    meta = parse_plan_meta(plan_text)
    analysis_pack = _analysis_pack_fields(plan_text)
    source_route = _source_route_fields(plan_text)
    applicable = _normalize_value(str(meta.get("wave_family") or "")) == "analysis_wave" or bool(analysis_pack or source_route)
    fields = _analysis_route_lifecycle_fields(plan_text)
    if not applicable:
        return AnalysisRouteLifecycleState("not_applicable", "plan has no analysis route lifecycle carrier", "", "", "", "", "not_applicable")
    if not fields:
        return AnalysisRouteLifecycleState("warning", "`execution_budget` lifecycle carrier is missing", "", "", "", "", "unknown")

    budget_status = _normalize_value(fields.get("budget_status", ""))
    cap_text = fields.get("needs_analysis_depth_cap", "")
    current_text = fields.get("current_needs_analysis_depth", "")
    cap = _lifecycle_int(cap_text)
    current = _lifecycle_int(current_text)
    effective_cap = cap if cap is not None else ANALYSIS_ROUTE_LIFECYCLE_DEFAULT_DEPTH_CAP
    if budget_status == "exhausted":
        return AnalysisRouteLifecycleState(
            "architect_stop",
            "explicit budget_status=exhausted routes to Architect",
            "Architect",
            budget_status,
            cap_text,
            current_text,
            "not_evaluated",
        )

    if current is not None and current > effective_cap and not _lifecycle_has_override(fields.get("override_ref", "")):
        cap_reason = cap if cap is not None else f"default {ANALYSIS_ROUTE_LIFECYCLE_DEFAULT_DEPTH_CAP}"
        return AnalysisRouteLifecycleState(
            "architect_stop",
            f"current_needs_analysis_depth={current} exceeds needs_analysis_depth_cap={cap_reason}",
            "Architect",
            budget_status,
            cap_text or str(ANALYSIS_ROUTE_LIFECYCLE_DEFAULT_DEPTH_CAP),
            current_text,
            "not_evaluated",
        )

    missing_budget_keys = [key for key in ANALYSIS_ROUTE_LIFECYCLE_BUDGET_KEYS if not _clean_lifecycle_value(fields.get(key, ""))]
    if missing_budget_keys:
        return AnalysisRouteLifecycleState(
            "warning",
            "missing lifecycle budget key(s): " + ", ".join(missing_budget_keys),
            "",
            budget_status,
            cap_text,
            current_text,
            "unknown",
        )
    if cap is None or current is None:
        return AnalysisRouteLifecycleState(
            "warning",
            "`needs_analysis` depth values must be numeric",
            "",
            budget_status,
            cap_text,
            current_text,
            "unknown",
        )

    stale_action = _normalize_value(fields.get("action", ""))
    change_ref = _clean_lifecycle_value(fields.get("change_ref", ""))
    if change_ref and stale_action == "architect_recheck":
        return AnalysisRouteLifecycleState(
            "stale_needs_architect_review",
            "source lifecycle change_ref requires architect_recheck",
            "Architect",
            budget_status,
            cap_text,
            current_text,
            "changed",
        )

    subject_baseline = fields.get("source_subject_baseline", "")
    current_subject = fields.get("current_source_subject", "")
    refs_baseline = fields.get("source_refs_baseline", "")
    current_refs = fields.get("current_source_refs", "")
    has_subject_pair = bool(subject_baseline and current_subject)
    has_refs_pair = bool(refs_baseline and current_refs)
    if has_subject_pair and _lifecycle_values_differ(subject_baseline, current_subject):
        return AnalysisRouteLifecycleState(
            "stale_needs_architect_review",
            "source subject changed from accepted baseline",
            "Architect",
            budget_status,
            cap_text,
            current_text,
            "changed",
        )
    if has_refs_pair and _lifecycle_values_differ(refs_baseline, current_refs):
        return AnalysisRouteLifecycleState(
            "stale_needs_architect_review",
            "source refs changed from accepted baseline",
            "Architect",
            budget_status,
            cap_text,
            current_text,
            "changed",
        )
    if not has_subject_pair and not has_refs_pair:
        return AnalysisRouteLifecycleState(
            "warning",
            "source subject/ref baseline is missing or ambiguous",
            "",
            budget_status,
            cap_text,
            current_text,
            "unknown",
        )

    stale_state = "unchanged"
    return AnalysisRouteLifecycleState("ok", "analysis route lifecycle budget and stale trigger are valid", "", budget_status, cap_text, current_text, stale_state)


def _enum_token(value: object) -> str:
    raw = str(value).strip().strip("`").strip()
    match = re.match(r"^[A-Za-z0-9_/-]+", raw)
    if not match:
        return ""
    return _normalize_value(match.group(0))


def _invalid_enum_fields(
    carrier: Mapping[str, object],
    field_to_vocab_key: dict[str, str],
    vocab: dict[str, frozenset[str]],
) -> list[str]:
    invalid: list[str] = []
    for field, vocab_key in field_to_vocab_key.items():
        allowed = vocab.get(vocab_key)
        if not allowed:
            invalid.append(field)
            continue
        token = _enum_token(carrier.get(field, ""))
        if token not in allowed:
            invalid.append(field)
    return invalid


def _source_route_required_fields(fields: Mapping[str, str]) -> tuple[str, ...]:
    accepted_route = _enum_token(fields.get("accepted_route", ""))
    if accepted_route in FIXTURE_BACKED_SOURCE_ROUTES:
        return SOURCE_ROUTE_ANALYSIS_FIELDS + SOURCE_ROUTE_REQUIRED_FIELDS
    return SOURCE_ROUTE_REQUIRED_FIELDS


def _carrier_field_is_blank(fields: Mapping[str, str], field: str) -> bool:
    return not str(fields.get(field, "")).strip()


def non_executable_source_route_carrier_issues(
    fields: Mapping[str, str],
    *,
    source_route_state: str = "valid",
) -> tuple[SourceRouteCarrierIssue, ...]:
    if source_route_state != "valid":
        return ()

    accepted_route = _enum_token(fields.get("accepted_route", ""))
    if accepted_route not in NON_EXECUTABLE_SOURCE_ROUTES:
        return ()

    issues: list[SourceRouteCarrierIssue] = []
    for field, expected in NON_EXECUTABLE_ROUTE_EXPECTED_FIELDS.get(accepted_route, {}).items():
        actual = _enum_token(fields.get(field, ""))
        if actual != expected:
            issues.append(
                SourceRouteCarrierIssue(
                    "ERROR",
                    field,
                    "route_mapping_mismatch",
                    f"`accepted_route={accepted_route}` requires `{field}={expected}`.",
                )
            )

    if accepted_route in NON_EXECUTABLE_ROUTE_REVISIT_REQUIRED and _carrier_field_is_blank(fields, "revisit_when"):
        issues.append(
            SourceRouteCarrierIssue(
                "ERROR",
                "revisit_when",
                "missing_revisit_when",
                f"`accepted_route={accepted_route}` must carry a concrete `revisit_when` re-entry trigger.",
            )
        )

    subject_identity = str(fields.get(SUBJECT_IDENTITY_FIELD, "")).strip()
    if accepted_route in {"defer", "human_gate"} and not subject_identity:
        issues.append(
            SourceRouteCarrierIssue(
                "WARN",
                SUBJECT_IDENTITY_FIELD,
                "missing_subject_identity",
                f"`accepted_route={accepted_route}` has no `subject_identity`; duplicate/fuzzy subject checks are only advisory.",
            )
        )
    elif subject_identity and NON_EXECUTABLE_FUZZY_SUBJECT_RE.search(subject_identity):
        issues.append(
            SourceRouteCarrierIssue(
                "WARN",
                SUBJECT_IDENTITY_FIELD,
                "fuzzy_subject_identity",
                "`subject_identity` must be exact enough for duplicate/re-entry checks; fuzzy subject matching is warning-only.",
            )
        )

    duplicate_of = str(fields.get(DUPLICATE_OF_FIELD, "")).strip()
    if duplicate_of and NON_EXECUTABLE_FUZZY_SUBJECT_RE.search(duplicate_of):
        issues.append(
            SourceRouteCarrierIssue(
                "WARN",
                DUPLICATE_OF_FIELD,
                "fuzzy_duplicate_ref",
                "`duplicate_of` must point to an exact prior route/follow-up subject; fuzzy duplicate refs stay warning-only.",
            )
        )

    if accepted_route == "reject":
        duplicate_hint_text = " ".join(
            str(fields.get(field, ""))
            for field in ("accepted_route_reason", "next_action", "promoted_artifact_ref", SUBJECT_IDENTITY_FIELD)
        )
        if NON_EXECUTABLE_DUPLICATE_HINT_RE.search(duplicate_hint_text) and not duplicate_of:
            issues.append(
                SourceRouteCarrierIssue(
                    "WARN",
                    DUPLICATE_OF_FIELD,
                    "duplicate_reject_missing_ref",
                    "Duplicate rejection must carry `duplicate_of` with an exact route/follow-up/source ref.",
                )
            )

    return tuple(issues)


def classify_non_executable_source_route_carrier(
    fields: Mapping[str, str],
    *,
    source_route_state: str,
) -> tuple[str, str]:
    accepted_route = _enum_token(fields.get("accepted_route", ""))
    if source_route_state != "valid":
        return "not_applicable", f"source_route_state={source_route_state}; carrier grammar not assessed"
    if accepted_route not in NON_EXECUTABLE_SOURCE_ROUTES:
        return "not_applicable", f"accepted_route={accepted_route or '<missing>'} is executable/decomposition or unknown"

    issues = non_executable_source_route_carrier_issues(fields, source_route_state=source_route_state)
    if not issues:
        return "valid", f"accepted_route={accepted_route} non-executable carrier is concrete"

    rendered = "; ".join(f"{issue.kind}:{issue.field}" for issue in issues)
    if any(issue.severity == "ERROR" for issue in issues):
        return "missing_required", rendered
    return "warning", rendered


def classify_source_route(
    plan_text: str,
    meta: dict[str, object],
    *,
    planning_contour_vocab: dict[str, frozenset[str]],
) -> tuple[str, dict[str, str], str]:
    if _normalize_value(str(meta.get("wave_family") or "")) != "analysis_wave":
        return "not_applicable", {}, "plan is not an analysis_wave source"

    fields = _source_route_fields(plan_text)
    if not fields or _section_contains_na_value(plan_text, PROMOTED_ROUTE_ARTIFACT_HEADING_RE):
        return "absent", fields, "analysis_wave source has no materialized ## Promoted route artifact"

    missing = [field for field in _source_route_required_fields(fields) if not fields.get(field)]
    if missing:
        return "missing_required", fields, "source route artifact is missing required fields: " + ", ".join(missing)
    invalid = _invalid_enum_fields(fields, SOURCE_ROUTE_ENUM_FIELDS, planning_contour_vocab)
    if invalid:
        return "missing_required", fields, "source route artifact has invalid enum fields: " + ", ".join(invalid)
    return "valid", fields, "source route artifact has required readback fields"


def _object_field_is_blank(value: object) -> bool:
    return value is None or not str(value).strip()


def _classify_object_carrier(
    meta: dict[str, object],
    key: str,
    *,
    applicable: bool,
    required_fields: tuple[str, ...],
    allowed_state_values: frozenset[str] | None = None,
    enum_fields: dict[str, str] | None = None,
    planning_contour_vocab: dict[str, frozenset[str]] | None = None,
) -> tuple[str, dict[str, object]]:
    if not applicable:
        return "not_applicable", {}
    if key not in meta:
        return "absent", {}
    value = meta.get(key)
    if value is None:
        return "null", {}
    if not isinstance(value, dict):
        return "non_object", {}

    missing = [field for field in required_fields if _object_field_is_blank(value.get(field))]
    if key == "promoted_from" and value.get("authority_note") != PROMOTED_FROM_AUTHORITY_NOTE:
        missing.append("authority_note")
    if allowed_state_values is not None:
        state = _normalize_value(str(value.get("state") or ""))
        if state not in allowed_state_values:
            missing.append("state")
    if enum_fields is not None:
        missing.extend(_invalid_enum_fields(value, enum_fields, planning_contour_vocab or {}))
    if missing:
        return "missing_required", value
    return "valid", value


def _source_route_parity_state(
    plan_path: Path,
    root: Path,
    promoted_from_obj: dict[str, object],
    *,
    planning_contour_vocab: dict[str, frozenset[str]],
) -> str:
    if _enum_token(promoted_from_obj.get("accepted_route", "")) != "decomposition_wave":
        return "valid"

    source_plan = _clean_plan_ref(promoted_from_obj.get("source_plan", ""))
    if not _is_repo_relative_plan_path(source_plan):
        if _explicit_na_with_reason(source_plan):
            return "valid"
        return "missing_required"

    source_route_path, source_route_anchor = _split_route_ref(promoted_from_obj.get("source_route_ref", ""))
    if source_route_path != source_plan or source_route_anchor != PROMOTED_ROUTE_ARTIFACT_ANCHOR:
        return "missing_required"

    source_path = root / source_plan
    if not source_path.is_file():
        return "missing_required"
    try:
        source_text = source_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return "missing_required"

    source_meta = parse_plan_meta(source_text)
    if _normalize_value(str(source_meta.get("wave_family") or "")) != "analysis_wave":
        return "missing_required"

    source_fields = _source_route_fields(source_text)
    if not source_fields or _section_contains_na_value(source_text, PROMOTED_ROUTE_ARTIFACT_HEADING_RE):
        return "missing_required"

    missing = [field for field in _source_route_required_fields(source_fields) if not source_fields.get(field)]
    if missing:
        return "missing_required"
    invalid = _invalid_enum_fields(source_fields, SOURCE_ROUTE_ENUM_FIELDS, planning_contour_vocab)
    if invalid:
        return "missing_required"

    current_rel_path = str(plan_path.resolve().relative_to(root.resolve()))
    if _clean_plan_ref(source_fields.get("source_analysis_plan", "")) != source_plan:
        return "missing_required"
    if _clean_plan_ref(promoted_from_obj.get("promoted_artifact_ref", "")) != current_rel_path:
        return "missing_required"
    if _clean_plan_ref(source_fields.get("promoted_artifact_ref", "")) != current_rel_path:
        return "missing_required"

    comparison_pairs = (
        ("accepted_route", "accepted_route"),
        ("promoted_artifact_kind", "promoted_artifact_kind"),
        ("queue_admission", "queue_admission_at_acceptance"),
        ("runner_admission", "runner_admission_at_acceptance"),
    )
    for source_field, target_field in comparison_pairs:
        if _enum_token(source_fields.get(source_field, "")) != _enum_token(promoted_from_obj.get(target_field, "")):
            return "missing_required"

    return "valid"


def classify_planning_contour_marker(meta: dict[str, object]) -> str:
    if _normalize_value(str(meta.get("wave_family") or "")) == "analysis_wave":
        return "analysis_wave"
    if _normalize_value(str(meta.get("phase_overlay") or "")) == "decomposition_wave":
        return "decomposition_wave"
    return "none"


def classify_planning_contour_role(meta: dict[str, object], marker: str) -> str:
    if marker == "analysis_wave":
        return "source_analysis"
    if marker == "decomposition_wave":
        phase_state = _normalize_value(str(meta.get("phase_state") or ""))
        if phase_state == "active":
            return "active_decomposition"
        if phase_state == "parked":
            return "parked_decomposition"
        return "promoted_target"
    if "promoted_from" in meta:
        return "promoted_target"
    return "ordinary"


def _live_review_artifact_refs(plan_text: str) -> list[tuple[int, str]]:
    entries: list[tuple[int, str]] = []
    seen: dict[str, int] = {}
    for line_no, line in _section_lines_with_numbers(plan_text, REVIEW_ARTIFACTS_HEADING_RE):
        match = LIVE_REVIEW_ARTIFACT_LINE_RE.match(line)
        if not match:
            continue
        for ref in REVIEW_ARTIFACT_RE.findall(match.group("body")):
            seen.setdefault(ref, line_no)
    entries.extend((line_no, ref) for ref, line_no in seen.items())
    return sorted(entries, key=lambda item: item[0])


def _review_header_values(review_text: str) -> tuple[str | None, str | None]:
    date_value: str | None = None
    status_values: list[str] = []
    lines = tuple(review_text.splitlines())
    for _line_no, line in review_artifact_lint._extract_review_header_lines(lines):
        if date_value is None:
            date_match = REVIEW_DATE_LINE_RE.match(line)
            if date_match:
                date_value = date_match.group("value").strip()
    status_value, _status_line = review_header_metadata.singleton_header_value(lines, "status")
    if status_value is not None:
        status_values.append(status_value)
    status_value = status_values[0] if len(status_values) == 1 else None
    return date_value, status_value


def _parse_inline_timestamp(raw_value: str) -> datetime | None:
    match = INLINE_TIMESTAMP_RE.search(raw_value)
    if not match:
        return None
    stamp = match.group("value")
    for fmt in ("%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M"):
        try:
            return datetime.strptime(stamp, fmt)
        except ValueError:
            continue
    return None


def _note_mentions_current_review_artifact(note_body: str, live_rel_path: str) -> bool:
    return live_rel_path in note_body or bool(SAME_REVIEW_FILE_RE.search(note_body))


def _review_artifacts_section_has_stale_rerun_note(
    plan_text: str,
    *,
    live_rel_path: str,
    review_date_value: str | None,
) -> bool:
    body = [line for _, line in _section_lines_with_numbers(plan_text, REVIEW_ARTIFACTS_HEADING_RE)]
    review_dt = _parse_inline_timestamp(review_date_value or "")

    def has_current_cycle_note(note_re: re.Pattern[str]) -> bool:
        for line in body:
            match = note_re.match(line)
            if not match:
                continue
            if not _note_mentions_current_review_artifact(match.group("body"), live_rel_path):
                continue
            note_dt = _parse_inline_timestamp(match.group("meta"))
            if review_dt is None:
                return True
            if note_dt is not None and note_dt >= review_dt:
                return True
        return False

    return has_current_cycle_note(STALE_NOTE_LINE_RE) and has_current_cycle_note(RERUN_NOTE_LINE_RE)


def classify_review_readback(plan_text: str, *, root: Path | None = None, plan_path: Path | None = None) -> tuple[str, str]:
    live_refs = _live_review_artifact_refs(plan_text)
    if not live_refs:
        return "none", "no live review artifact declared"
    if len(live_refs) > 1:
        paths = ", ".join(ref for _, ref in live_refs)
        return "unknown", f"multiple live review artifacts declared: {paths}"

    _, live_rel_path = live_refs[0]
    if root is None:
        return "unknown", "repo root is unavailable for live review artifact readback"
    review_path = root / live_rel_path
    if not review_path.exists():
        return "none", f"live review artifact is not materialized yet: {live_rel_path}"
    try:
        review_bytes = review_path.read_bytes()
        review_text = review_bytes.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return "unknown", f"live review artifact cannot be read: {exc}"

    if plan_path is not None:
        # Keep the oracle a projection consumer: the strict current-proof
        # classifier/support/recompute path lives in plan_lint and must run
        # before a malformed current-shaped review can be reported as green.
        import plan_lint

        proof = plan_lint.preflight_current_review_proof(plan_path, project_root=root)
        if proof.state == "blocked":
            return (
                "live_blocker",
                f"{proof.reason_code or 'current_review_proof_blocked'}: {proof.message}",
            )

    review_date_value, review_status_value = _review_header_values(review_text)
    if not review_status_value:
        return "unknown", f"live review artifact has no header status: {live_rel_path}"
    review_status_norm = review_artifact_lint.normalize_review_status(review_status_value)
    if review_status_norm == review_artifact_lint.FINAL_BLOCKER_STATUS:
        if _review_artifacts_section_has_stale_rerun_note(
            plan_text,
            live_rel_path=live_rel_path,
            review_date_value=review_date_value,
        ):
            if plan_path is not None:
                closeout = review_artifact_lint.classify_same_file_rerun_closeout(
                    plan_path,
                    review_path,
                    project_root=root,
                )
                if closeout.state == "stale_red_after_fix":
                    return "stale_red_after_fix", closeout.reason
                return "live_blocker", closeout.reason
            return (
                "stale_review_only",
                f"red review artifact has stale/rerun notes, but fixed-evidence selector was not evaluated: {live_rel_path}",
            )
        return "live_blocker", f"red review artifact is still live: {live_rel_path}"
    if review_status_norm == review_artifact_lint.FINAL_OK_STATUS:
        if plan_path is None:
            return "unknown", "green review artifact freshness requires a known plan path"
        try:
            artifacts = [
                review_artifact_lint.review_artifact_from_text(
                    root,
                    review_path,
                    review_text,
                )
            ]
            findings = review_artifact_lint.lint_review_artifacts(
                artifacts,
                project_root=root,
                origin_plan=plan_path,
                require_dual_lane_origin=True,
            )
        except Exception as exc:
            return "unknown", f"green review artifact freshness cannot be checked: {exc}"
        try:
            post_lint_review_bytes = review_path.read_bytes()
        except OSError as exc:
            return "unknown", f"green review artifact changed or became unreadable during validation: {exc}"
        if post_lint_review_bytes != review_bytes:
            return "unknown", "green review artifact changed during validation; rerun readback on a stable file"
        stale_codes = {
            "current_bundle_target_snapshot_mismatch",
            "dual_lane_target_snapshot_mismatch",
        }
        finding_codes = sorted({finding.code for finding in findings})
        non_stale_codes = set(finding_codes) - stale_codes
        if findings and non_stale_codes:
            codes = ",".join(finding_codes)
            return (
                "unknown",
                f"green review artifact lint is not green: {live_rel_path}; findings={codes}",
            )
        if stale_codes.intersection(finding_codes):
            codes = ",".join(code for code in finding_codes if code in stale_codes)
            return (
                "stale_green_review",
                f"green review artifact target snapshot is stale: {live_rel_path}; findings={codes}",
            )
        return "ok", f"live review artifact is green: {live_rel_path}"
    return "unknown", f"live review artifact status is not recognized: {review_status_value}"


def review_operational_route(review_readback_state: str) -> tuple[str, str]:
    if review_readback_state == "stale_red_after_fix":
        return "reviewer_same_file_rewrite_required", "Reviewer"
    if review_readback_state == "stale_green_review":
        return "reviewer_same_file_rewrite_required", "Reviewer"
    if review_readback_state == "live_blocker":
        return "review_blocker_requires_resolution", "Coder"
    if review_readback_state == "stale_review_only":
        return "review_blocker_requires_resolution", "Reviewer"
    if review_readback_state == "ok":
        return "review_green", ""
    if review_readback_state == "none":
        return "review_not_materialized", "Reviewer"
    return "review_readback_unknown", "Architect"


def classify_planning_contour_readback(
    *,
    role: str,
    source_route_state: str,
    source_route_non_executable_carrier_state: str,
    promoted_from_state: str,
    queue_activation_carrier_state: str,
    review_readback_state: str,
) -> tuple[str, str]:
    issues: list[str] = []
    if role == "source_analysis" and source_route_state != "valid":
        issues.append(f"source_route_state={source_route_state}")
    if role == "source_analysis" and source_route_non_executable_carrier_state in {"missing_required", "warning"}:
        issues.append(f"source_route_non_executable_carrier_state={source_route_non_executable_carrier_state}")
    if role in {"promoted_target", "active_decomposition", "parked_decomposition"}:
        if promoted_from_state != "valid":
            issues.append(f"promoted_from_state={promoted_from_state}")
        if queue_activation_carrier_state != "valid":
            issues.append(f"queue_activation_carrier_state={queue_activation_carrier_state}")
    if review_readback_state in {"live_blocker", "stale_green_review"}:
        issues.append(f"review_readback_state={review_readback_state}")
    if review_readback_state == "unknown":
        issues.append("review_readback_state=unknown")

    if issues:
        return "warning", "; ".join(issues)
    if role == "ordinary":
        return "not_applicable", "ordinary plan has no planning-contour route readback role"
    return "valid", "planning-contour readback carriers are present"


def classify_pending_activation(
    queue_activation_carrier_state: str,
    queue_activation_obj: dict[str, object],
    meta: dict[str, object],
    plan_text: str,
) -> tuple[bool, str]:
    if queue_activation_carrier_state in {"null", "non_object", "missing_required"}:
        return (
            True,
            f"queue_activation_carrier_state={queue_activation_carrier_state}; activation carrier is not queueable",
        )

    state = _normalize_value(str(queue_activation_obj.get("state") or ""))
    if state == "not_requested":
        return True, "queue_activation.state=not_requested; activation/child selection is still pending"
    if state in {"owner_approved", "architect_approved"}:
        next_plans_value = meta.get("next_plans")
        next_plans = [str(item).strip() for item in next_plans_value] if isinstance(next_plans_value, list) else []
        if concrete_execution_queue_plan_entries(plan_text) and not any(next_plans):
            return (
                True,
                "queue_activation.state is approved but ## Execution queue has child plan(s) and plan_meta.next_plans[] is empty",
            )
    return False, ""


def _is_na_value(value: str | None) -> bool:
    if value is None:
        return False
    cleaned = value.strip().strip("`")
    return cleaned.lower().startswith("n/a")


def _has_review_only_route_override(plan_text: str) -> bool:
    meta = parse_plan_meta(plan_text)
    override = meta.get(REVIEW_ONLY_ROUTE_OVERRIDE_KEY)
    if not isinstance(override, dict):
        return False
    owner = _normalize_value(str(override.get("owner") or ""))
    reason = str(override.get("reason") or "").strip()
    return bool(override.get("allow_planner_coder_lane") is True and owner == "architect" and reason)


def classify_scope_expansion(
    meta: dict[str, object],
    *,
    planning_contour_vocab: dict[str, frozenset[str]],
) -> ScopeExpansionState:
    if "scope_expansion" not in meta:
        return ScopeExpansionState(
            "absent",
            "absent",
            "",
            "",
            "",
            "plan_meta.scope_expansion is absent",
        )

    value = meta.get("scope_expansion")
    if value is None:
        malformed_reason = "plan_meta.scope_expansion is null"
    elif not isinstance(value, dict):
        malformed_reason = "plan_meta.scope_expansion must be an object"
    else:
        wrong_type = [
            field
            for field in SCOPE_EXPANSION_REQUIRED_FIELDS
            if field in value and not isinstance(value[field], str)
        ]
        missing = [
            field
            for field in SCOPE_EXPANSION_REQUIRED_FIELDS
            if field not in value or (isinstance(value[field], str) and not value[field].strip())
        ]
        state = _normalize_value(value["state"]) if isinstance(value.get("state"), str) else ""
        allowed_states = planning_contour_vocab.get("scope_expansion_states", frozenset())
        if missing:
            malformed_reason = "plan_meta.scope_expansion is missing required field(s): " + ", ".join(missing)
        elif wrong_type:
            malformed_reason = "plan_meta.scope_expansion required field(s) must be strings: " + ", ".join(wrong_type)
        elif state not in allowed_states:
            malformed_reason = f"plan_meta.scope_expansion.state={state or '<empty>'} is not manifest-valid"
        else:
            return ScopeExpansionState(
                "valid",
                state,
                value["target_contour"].strip(),
                value["source_ref"].strip(),
                value["reason"].strip(),
                "plan_meta.scope_expansion is valid",
            )

    return ScopeExpansionState(
        "malformed",
        "unknown",
        "",
        "",
        "",
        malformed_reason,
    )


def semantic_cycle_checkpoint_report(
    plan_path: Path,
    *,
    context: ContractContext | None = None,
) -> Mapping[str, object]:
    """Late-import the single plan-lint checkpoint authority without a module cycle."""

    # plan_lint imports this oracle for its longstanding status/readback helpers.
    # Importing only while serving an oracle request keeps the authority one-way:
    # all checkpoint semantics remain in plan_lint, while this module projects
    # only generic route_guard_* fields for every Manager mode.
    import plan_lint

    return plan_lint.build_semantic_cycle_checkpoint_report(plan_path, context=context)


def classify_route_guard(
    plan_text: str,
    plan_type_norm: str,
    status_value: str,
    status_norm: str,
    *,
    planning_contour_role: str,
    scope_expansion: ScopeExpansionState,
    machine_authority: MachineAuthorityDecisionReadback | None = None,
    checkpoint_report: Mapping[str, object] | None = None,
) -> tuple[bool, str, str, str]:
    if scope_expansion.carrier_state == "malformed":
        return (
            True,
            "scope_expansion_malformed",
            f"{scope_expansion.classification_reason}; route to Architect normalization",
            "Architect",
        )

    if scope_expansion.state == "reroute_required":
        return (
            True,
            "scope_expansion_reroute_required",
            (
                "Explicit role-owned plan_meta.scope_expansion.state=reroute_required "
                f"for planning_contour_role={planning_contour_role}; route to Architect before raw status"
            ),
            "Architect",
        )

    if (
        scope_expansion.state == "architect_accepted"
        and status_norm in SCOPE_EXPANSION_ARCHITECT_ACCEPTED_BLOCKED_STATUS_NORMS
    ):
        return (
            True,
            "scope_expansion_architect_accepted_wrong_status",
            (
                "plan_meta.scope_expansion.state=architect_accepted is transition-only and cannot enter "
                f"downstream status {status_value}; Architect must materialize the accepted route or reset the carrier"
            ),
            "Architect",
        )

    if machine_authority is not None and machine_authority.route_guard_required:
        kind = "machine_authority_decision_" + re.sub(
            r"[^a-z0-9_]+", "_", machine_authority.reason_code.lower()
        ).strip("_")
        return (
            True,
            kind,
            "Machine-authority admission "
            f"state={machine_authority.state} reason_code={machine_authority.reason_code} "
            f"blocks raw downstream status {status_value}; route to Architect normalization",
            "Architect",
        )

    checkpoint_state = checkpoint_report.get("state") if isinstance(checkpoint_report, Mapping) else None
    checkpoint_reason = checkpoint_report.get("reason_code") if isinstance(checkpoint_report, Mapping) else None
    if checkpoint_state in {"required", "blocked"} and status_norm not in {
        "ready for architect response",
        "architect response",
    }:
        kind = "semantic_cycle_checkpoint_required" if checkpoint_state == "required" else "semantic_cycle_checkpoint_invalid"
        return (
            True,
            kind,
            "Semantic cycle checkpoint "
            f"state={checkpoint_state} reason_code={checkpoint_reason or 'invalid'} blocks raw downstream status "
            f"{status_value}; route to Architect normalization",
            "Architect",
        )

    if plan_type_norm != "review-only" or status_norm not in REVIEW_ONLY_IMPLEMENTATION_STATUS_NORMS:
        return False, "none", "no route guard triggered", ""

    if _has_review_only_route_override(plan_text):
        return (
            False,
            "none",
            f"review-only implementation lane allowed by plan_meta.{REVIEW_ONLY_ROUTE_OVERRIDE_KEY}",
            "",
        )

    return (
        True,
        "review_only_wrong_status",
        (
            f"Plan type review-only with status {status_value} is in Planner/Coder implementation lane "
            f"without explicit plan_meta.{REVIEW_ONLY_ROUTE_OVERRIDE_KEY}; route to Architect normalization"
        ),
        "Architect",
    )


def classify_runtime_state(plan_text: str, status_value: str, status_norm: str) -> tuple[str, str, bool, str, str]:
    meta = parse_plan_meta(plan_text)
    handoffs = parse_handoff_statuses(plan_text)
    code_drafts_value = parse_context_entry(plan_text, "Code draft(s):")
    phase_overlay = _normalize_value(str(meta.get("phase_overlay") or ""))
    phase_state = _normalize_value(str(meta.get("phase_state") or ""))
    parent_value = meta.get("parent")
    has_parent = isinstance(parent_value, str) and bool(parent_value.strip())
    non_executable_handoffs = all(_is_na_value(handoffs.get(key)) for key in NON_EXECUTABLE_HANDOFF_KEYS)
    code_drafts_na = _is_na_value(code_drafts_value)
    has_non_executable_markers = non_executable_handoffs and code_drafts_na

    runtime_class = RUNTIME_CLASS_EXECUTABLE
    runtime_class_reason = "default executable item; queue requires terminal Done/Superseded unless repo-backed non-executable markers say otherwise"
    if has_non_executable_markers and phase_state == "parked":
        runtime_class = RUNTIME_CLASS_PARKED_UMBRELLA
        runtime_class_reason = "phase_state=parked plus downstream executable handoffs N/A and Code draft(s): N/A"
    elif phase_state == "parked":
        runtime_class_reason = (
            "phase_state=parked without complete repo-backed non-executable markers; "
            "downstream executable handoffs and Code draft(s): N/A are required"
        )
    elif has_non_executable_markers and has_parent:
        runtime_class = RUNTIME_CLASS_VERIFIED_REFERENCE_CHILD
        runtime_class_reason = "parent-linked reference child with downstream executable handoffs N/A and Code draft(s): N/A"
    elif has_non_executable_markers:
        runtime_class = RUNTIME_CLASS_ROUTING_ONLY_BASELINE
        runtime_class_reason = "standalone routing-only baseline with downstream executable handoffs N/A and Code draft(s): N/A"
    elif phase_overlay == "decomposition_wave" and phase_state == "active":
        runtime_class_reason = "active decomposition wave remains planning/execution-carrying; non-executable markers do not apply"

    if status_norm in {"done", "superseded"}:
        queue_closeout_ready = True
        queue_closeout_kind = "terminal_status"
        queue_closeout_reason = f"terminal status {status_value} remains queue-closeable for any runtime class"
    elif runtime_class in NON_EXECUTABLE_RUNTIME_CLASSES and status_norm == "ready for planner":
        queue_closeout_ready = True
        queue_closeout_kind = "non_executable_ready"
        queue_closeout_reason = f"{runtime_class} is repo-backed and currently parked at Ready for Planner"
    else:
        queue_closeout_ready = False
        queue_closeout_kind = "not_ready"
        if runtime_class in NON_EXECUTABLE_RUNTIME_CLASSES:
            queue_closeout_reason = (
                f"{runtime_class} markers are present, but auto-advance is allowed only from Ready for Planner; "
                f"current status is {status_value}"
            )
        else:
            queue_closeout_reason = "current item is still executable or ambiguous, so queue must wait for Done/Superseded"

    return (
        runtime_class,
        runtime_class_reason,
        queue_closeout_ready,
        queue_closeout_kind,
        queue_closeout_reason,
    )


def oracle_result(
    plan_path: Path,
    *,
    context: ContractContext | None = None,
) -> OracleResult:
    repo_root = _repo_root_for_plan_path(plan_path, context=context)
    resolved_context = context_for_reader(repo_root, context=context)
    raw = plan_path.read_bytes()
    text = raw.decode("utf-8")
    line_no, raw_line = _scan_status_line(text)
    status_value = raw_line.lstrip()[len("**Status:**") :].strip()
    status_norm = _status_norm_from_line(raw_line)
    _, plan_type_line = _scan_plan_type_line(text)
    plan_type = ""
    if plan_type_line is not None:
        plan_type = plan_type_line.lstrip()[len("**Plan type:**") :].strip()
    plan_type_norm = _normalize_value(plan_type)
    meta = parse_plan_meta(text)
    planning_contour_vocab = _planning_contour_vocab(repo_root, context=resolved_context)
    planning_contour_marker = classify_planning_contour_marker(meta)
    planning_contour_role = classify_planning_contour_role(meta, planning_contour_marker)
    scope_expansion = classify_scope_expansion(
        meta,
        planning_contour_vocab=planning_contour_vocab,
    )
    machine_authority = machine_authority_decision_readback(plan_path, text)
    accepted_red = classify_accepted_red_disposition(
        plan_path=plan_path,
        plan_text=text,
        status_norm=status_norm,
        meta=meta,
        context=resolved_context,
    )
    source_route_state, source_route_fields, _source_route_reason = classify_source_route(
        text,
        meta,
        planning_contour_vocab=planning_contour_vocab,
    )
    source_route_non_executable_carrier_state, source_route_non_executable_carrier_reason = (
        classify_non_executable_source_route_carrier(
            source_route_fields,
            source_route_state=source_route_state,
        )
    )
    analysis_authority = resolve_analysis_pack_authority(
        origin_plan_path=plan_path,
        plan_text=text,
        effective_status=status_value,
    )
    if analysis_authority.is_valid:
        analysis_lifecycle = classify_analysis_route_lifecycle(analysis_authority.authority_text)
    elif analysis_authority.detail_category == "operational_duplicate":
        pack_lifecycle = classify_analysis_route_lifecycle(analysis_authority.authority_text)
        analysis_lifecycle = AnalysisRouteLifecycleState(
            "warning",
            f"{ANALYSIS_PACK_AUTHORITY_INVALID}:{analysis_authority.detail_category}",
            pack_lifecycle.next_owner,
            pack_lifecycle.budget_status,
            pack_lifecycle.needs_analysis_depth_cap,
            pack_lifecycle.current_needs_analysis_depth,
            pack_lifecycle.stale_trigger_state,
        )
    else:
        analysis_lifecycle = AnalysisRouteLifecycleState(
            "warning",
            f"{ANALYSIS_PACK_AUTHORITY_INVALID}:{analysis_authority.detail_category}",
            "",
            "",
            "",
            "",
            "unknown",
        )
    promoted_from_applicable = planning_contour_role in {
        "promoted_target",
        "active_decomposition",
        "parked_decomposition",
    } or "promoted_from" in meta
    promoted_from_state, promoted_from_obj = _classify_object_carrier(
        meta,
        "promoted_from",
        applicable=promoted_from_applicable,
        required_fields=PROMOTED_FROM_REQUIRED_FIELDS,
        enum_fields=PROMOTED_FROM_ENUM_FIELDS,
        planning_contour_vocab=planning_contour_vocab,
    )
    if promoted_from_state == "valid":
        promoted_from_state = _source_route_parity_state(
            plan_path,
            repo_root,
            promoted_from_obj,
            planning_contour_vocab=planning_contour_vocab,
        )
    queue_activation_applicable = (
        "queue_activation" in meta
        or planning_contour_role in {"promoted_target", "active_decomposition", "parked_decomposition"}
        or status_norm == "architect initial draft"
    )
    queue_activation_carrier_state, queue_activation_obj = _classify_object_carrier(
        meta,
        "queue_activation",
        applicable=queue_activation_applicable,
        required_fields=QUEUE_ACTIVATION_REQUIRED_FIELDS,
        allowed_state_values=planning_contour_vocab.get("queue_activation_states", frozenset()),
    )
    checkpoint_report = semantic_cycle_checkpoint_report(plan_path, context=resolved_context)
    route_guard_triggered, route_guard_kind, route_guard_reason, route_guard_next_owner = classify_route_guard(
        text,
        plan_type_norm,
        status_value,
        status_norm,
        planning_contour_role=planning_contour_role,
        scope_expansion=scope_expansion,
        machine_authority=machine_authority,
        checkpoint_report=checkpoint_report,
    )
    (
        owner_qna_readback_state,
        owner_qna_readback_reason,
        open_owner_questions,
        owner_qna_issues,
    ) = owner_qna_readback(text)
    runtime_class, runtime_class_reason, queue_closeout_ready, queue_closeout_kind, queue_closeout_reason = classify_runtime_state(
        text,
        status_value,
        status_norm,
    )
    if route_guard_triggered and queue_closeout_ready:
        queue_closeout_ready = False
        queue_closeout_kind = "route_guard_blocked"
        queue_closeout_reason = (
            f"route_guard_kind={route_guard_kind} blocks raw queue closeout for status {status_value}"
        )
    review_readback_state, review_readback_reason = classify_review_readback(text, root=repo_root, plan_path=plan_path)
    planning_contour_readback_state, planning_contour_readback_reason = classify_planning_contour_readback(
        role=planning_contour_role,
        source_route_state=source_route_state,
        source_route_non_executable_carrier_state=source_route_non_executable_carrier_state,
        promoted_from_state=promoted_from_state,
        queue_activation_carrier_state=queue_activation_carrier_state,
        review_readback_state=review_readback_state,
    )
    pending_activation, pending_activation_reason = classify_pending_activation(
        queue_activation_carrier_state,
        queue_activation_obj,
        meta,
        text,
    )
    child_state = decomposition_child_state(text, root=repo_root, context=resolved_context)
    readiness_findings = decomposition_child_readiness_findings(text, root=repo_root, child_state=child_state)
    readiness_assessed_paths = child_state.concrete_child_paths if child_state.state == "queue_ready" else ()
    small_model_ready_child, small_model_readiness_state = small_model_readiness_summary(
        readiness_findings,
        assessed_children=readiness_assessed_paths,
    )
    if child_state.state in {"missing", "drafted"}:
        queue_closeout_ready = False
        queue_closeout_kind = "decomposition_children_missing"
        queue_closeout_reason = child_state.reason
    readiness_blockers = [finding for finding in readiness_findings if finding.blocks_queue]
    if readiness_blockers:
        first_blocker = readiness_blockers[0]
        queue_closeout_ready = False
        queue_closeout_kind = "small_model_ready_child_blocked"
        queue_closeout_reason = (
            f"{first_blocker.child_path}: {first_blocker.field}: "
            f"{first_blocker.finding_kind}: {first_blocker.message}"
        )

    st = plan_path.stat()
    return OracleResult(
        status_line=f"{line_no}:{raw_line}",
        status_value=status_value,
        status_norm=status_norm,
        plan_type=plan_type,
        plan_type_norm=plan_type_norm,
        planning_contour_marker=planning_contour_marker,
        planning_contour_role=planning_contour_role,
        planning_contour_readback_state=planning_contour_readback_state,
        planning_contour_readback_reason=planning_contour_readback_reason,
        scope_expansion_carrier_state=scope_expansion.carrier_state,
        scope_expansion_state=scope_expansion.state,
        scope_expansion_target_contour=scope_expansion.target_contour,
        scope_expansion_source_ref=scope_expansion.source_ref,
        scope_expansion_reason=scope_expansion.reason,
        machine_authority_decision_state=machine_authority.state,
        machine_authority_decision_reason=machine_authority.reason_code,
        machine_authority_decision_id=machine_authority.decision_id,
        machine_authority_decision_route=machine_authority.route,
        machine_authority_decision_carrier_sha256=machine_authority.carrier_sha256,
        machine_authority_decision_confirmation_state=machine_authority.confirmation_state,
        machine_authority_decision_ref_state=machine_authority.ref_state,
        machine_authority_decision_ref_reason=machine_authority.ref_reason,
        terminal_disposition=accepted_red.terminal_disposition,
        delivery_green=accepted_red.delivery_green,
        staging_policy=accepted_red.staging_policy,
        durable_capture_required=accepted_red.durable_capture_required,
        accepted_red_successor_plan=accepted_red.successor_plan,
        accepted_red_historical_review=accepted_red.historical_review,
        accepted_red_review_bundle_sha256=accepted_red.review_bundle_sha256,
        terminal_disposition_reason=accepted_red.reason,
        source_route_state=source_route_state,
        source_route_accepted_route=source_route_fields.get("accepted_route", ""),
        source_route_promoted_artifact_kind=source_route_fields.get("promoted_artifact_kind", ""),
        source_route_promoted_artifact_ref=source_route_fields.get("promoted_artifact_ref", ""),
        source_route_queue_admission=source_route_fields.get("queue_admission", ""),
        source_route_runner_admission=source_route_fields.get("runner_admission", ""),
        source_route_non_executable_carrier_state=source_route_non_executable_carrier_state,
        source_route_non_executable_carrier_reason=source_route_non_executable_carrier_reason,
        analysis_route_lifecycle_state=analysis_lifecycle.state,
        analysis_route_lifecycle_reason=analysis_lifecycle.reason,
        analysis_route_lifecycle_next_owner=analysis_lifecycle.next_owner,
        analysis_route_lifecycle_budget_status=analysis_lifecycle.budget_status,
        analysis_route_lifecycle_needs_analysis_depth_cap=analysis_lifecycle.needs_analysis_depth_cap,
        analysis_route_lifecycle_current_needs_analysis_depth=analysis_lifecycle.current_needs_analysis_depth,
        analysis_route_lifecycle_stale_trigger_state=analysis_lifecycle.stale_trigger_state,
        promoted_from_state=promoted_from_state,
        promoted_from_authority_note=str(promoted_from_obj.get("authority_note") or ""),
        promoted_from_accepted_route=str(promoted_from_obj.get("accepted_route") or ""),
        promoted_from_promoted_artifact_kind=str(promoted_from_obj.get("promoted_artifact_kind") or ""),
        promoted_from_promoted_artifact_ref=str(promoted_from_obj.get("promoted_artifact_ref") or ""),
        promoted_from_queue_admission=str(promoted_from_obj.get("queue_admission_at_acceptance") or ""),
        promoted_from_runner_admission=str(promoted_from_obj.get("runner_admission_at_acceptance") or ""),
        queue_activation_carrier_state=queue_activation_carrier_state,
        queue_activation_state=str(queue_activation_obj.get("state") or ""),
        pending_activation=pending_activation,
        pending_activation_reason=pending_activation_reason,
        review_readback_state=review_readback_state,
        review_readback_reason=review_readback_reason,
        route_guard_triggered=route_guard_triggered,
        route_guard_kind=route_guard_kind,
        route_guard_reason=route_guard_reason,
        route_guard_next_owner=route_guard_next_owner,
        owner_qna_readback_state=owner_qna_readback_state,
        owner_qna_readback_reason=owner_qna_readback_reason,
        open_owner_questions=open_owner_questions,
        owner_qna_issues=owner_qna_issues,
        runtime_class=runtime_class,
        runtime_class_reason=runtime_class_reason,
        queue_closeout_ready=queue_closeout_ready,
        queue_closeout_kind=queue_closeout_kind,
        queue_closeout_reason=queue_closeout_reason,
        decomposition_child_state=child_state.state,
        decomposition_child_reason=child_state.reason,
        decomposition_child_paths=child_state.concrete_child_paths,
        decomposition_child_issues=child_state.issues,
        small_model_ready_child=small_model_ready_child,
        small_model_readiness_state=small_model_readiness_state,
        small_model_readiness_findings=readiness_findings,
        captured_plan_text=text,
        plan_mtime=_iso_utc(st.st_mtime),
        plan_size=len(raw),
        plan_hash=hashlib.sha256(raw).hexdigest(),
        oracle_run_id=str(uuid.uuid4()),
    )


def _current_state_blocker(res: OracleResult) -> tuple[str, str]:
    hard_blockers: list[str] = []
    unknowns: list[str] = []

    if res.route_guard_triggered:
        hard_blockers.append(f"route_guard_kind={res.route_guard_kind}")
    if res.review_readback_state == "live_blocker":
        hard_blockers.append("review_readback_state=live_blocker")
    elif res.review_readback_state == "stale_green_review":
        hard_blockers.append("review_readback_state=stale_green_review")
    elif res.review_readback_state == "stale_red_after_fix":
        hard_blockers.append("review_readback_state=stale_red_after_fix")
    elif res.review_readback_state == "stale_review_only":
        hard_blockers.append("review_readback_state=stale_review_only")
    elif res.review_readback_state in {"none", "unknown"}:
        unknowns.append(f"review_readback_state={res.review_readback_state}")

    if res.planning_contour_readback_state == "warning":
        hard_blockers.append(f"planning_contour_readback_state=warning ({res.planning_contour_readback_reason})")

    if res.queue_closeout_kind in {"decomposition_children_missing", "small_model_ready_child_blocked"}:
        hard_blockers.append(f"queue_closeout_kind={res.queue_closeout_kind}")

    if res.pending_activation:
        hard_blockers.append(f"pending_activation=true ({res.pending_activation_reason})")

    if hard_blockers:
        return "blocked", "; ".join(hard_blockers)
    if unknowns:
        return "unknown", "; ".join(unknowns)
    return "none", "no known blocker from supported oracle carriers"


def _current_state_terminal_ready(res: OracleResult, blocker_state: str) -> tuple[str, str]:
    if blocker_state == "blocked":
        return "blocked", "supported oracle carriers report a blocking condition"
    if not res.queue_closeout_ready:
        return "not_ready", res.queue_closeout_reason
    if blocker_state == "unknown":
        return "unknown", "supported oracle carriers leave blocker state unknown"
    return (
        "unknown",
        (
            "queue/runtime carrier is terminal-ready, but docs-closeout, final-docs, "
            "followups and process-improvement facts are Manager context unavailable to this oracle"
        ),
    )


def build_current_state(res: OracleResult, plan_path: Path) -> dict[str, object]:
    blocker_state, blocker_reason = _current_state_blocker(res)
    terminal_ready_state, terminal_ready_reason = _current_state_terminal_ready(res, blocker_state)
    review_route, review_next_owner = review_operational_route(res.review_readback_state)
    unavailable_reason = (
        "not read by plan_status_oracle.py; supplied by planveyor_docs_closeout/Manager closeout context"
    )

    authorities: dict[str, object] = {
        "status_header": {
            "state": "available",
            "source": "PLAN_PATH header **Status:**",
            "value": res.status_value,
            "status_line": res.status_line,
        },
        "oracle_base": {
            "state": "available",
            "source": "scripts/plan_status_oracle.py base fields",
            "runtime_class": res.runtime_class,
            "queue_closeout_kind": res.queue_closeout_kind,
        },
        "scope_expansion": {
            "state": res.scope_expansion_carrier_state,
            "source": "plan_meta.scope_expansion",
            "value": res.scope_expansion_state,
            "target_contour": res.scope_expansion_target_contour,
            "source_ref": res.scope_expansion_source_ref,
            "reason": res.scope_expansion_reason,
        },
        "machine_authority_decision": {
            "state": res.machine_authority_decision_state,
            "source": "plan_meta.machine_authority_decision via sole strict top-level ## Meta",
            "reason": res.machine_authority_decision_reason,
            "decision_id": res.machine_authority_decision_id,
            "route": res.machine_authority_decision_route,
            "carrier_sha256": res.machine_authority_decision_carrier_sha256,
            "confirmation_state": res.machine_authority_decision_confirmation_state,
            "ref_state": res.machine_authority_decision_ref_state,
            "ref_reason": res.machine_authority_decision_ref_reason,
        },
        "terminal_disposition": {
            "state": res.terminal_disposition,
            "source": "terminal source plan, code draft, review, successor and current-bundle snapshot",
            "delivery_green": res.delivery_green,
            "staging_policy": res.staging_policy,
            "durable_capture_required": res.durable_capture_required,
            "successor_plan": res.accepted_red_successor_plan,
            "historical_review": res.accepted_red_historical_review,
            "review_bundle_sha256": res.accepted_red_review_bundle_sha256,
            "reason": res.terminal_disposition_reason,
        },
        "source_promoted_route": {
            "state": res.source_route_state,
            "source": "source plan ## Promoted route artifact when applicable",
            "accepted_route": res.source_route_accepted_route,
            "promoted_artifact_kind": res.source_route_promoted_artifact_kind,
            "promoted_artifact_ref": res.source_route_promoted_artifact_ref,
            "queue_admission": res.source_route_queue_admission,
            "runner_admission": res.source_route_runner_admission,
            "non_executable_carrier_state": res.source_route_non_executable_carrier_state,
            "non_executable_carrier_reason": res.source_route_non_executable_carrier_reason,
        },
        "analysis_route_lifecycle": {
            "state": res.analysis_route_lifecycle_state,
            "source": "analysis/source route lifecycle budget fields",
            "reason": res.analysis_route_lifecycle_reason,
            "next_owner": res.analysis_route_lifecycle_next_owner,
            "budget_status": res.analysis_route_lifecycle_budget_status,
            "needs_analysis_depth_cap": res.analysis_route_lifecycle_needs_analysis_depth_cap,
            "current_needs_analysis_depth": res.analysis_route_lifecycle_current_needs_analysis_depth,
            "stale_trigger_state": res.analysis_route_lifecycle_stale_trigger_state,
        },
        "promoted_from": {
            "state": res.promoted_from_state,
            "source": "plan_meta.promoted_from derived/read-only linkage",
            "authority_note": res.promoted_from_authority_note,
            "accepted_route": res.promoted_from_accepted_route,
            "promoted_artifact_kind": res.promoted_from_promoted_artifact_kind,
            "promoted_artifact_ref": res.promoted_from_promoted_artifact_ref,
            "queue_admission_at_acceptance": res.promoted_from_queue_admission,
            "runner_admission_at_acceptance": res.promoted_from_runner_admission,
        },
        "review": {
            "state": res.review_readback_state,
            "source": "## Review artifacts live review artifact readback",
            "reason": res.review_readback_reason,
            "route": review_route,
            "next_owner": review_next_owner,
        },
        "queue_runtime": {
            "state": res.queue_closeout_kind,
            "source": "header status plus runtime/queue closeout classifiers",
            "queue_closeout_ready": res.queue_closeout_ready,
            "reason": res.queue_closeout_reason,
        },
        "queue_activation": {
            "state": res.queue_activation_carrier_state,
            "source": "plan_meta.queue_activation",
            "value": res.queue_activation_state,
            "pending_activation": res.pending_activation,
            "pending_activation_reason": res.pending_activation_reason,
        },
        "docs_closeout": {
            "state": CONTEXTUAL_UNAVAILABLE,
            "source": "planveyor_docs_closeout context",
            "reason": unavailable_reason,
        },
        "followups_reconciliation": {
            "state": CONTEXTUAL_UNAVAILABLE,
            "source": "Manager docs-closeout followups_reconciliation context",
            "reason": unavailable_reason,
        },
        "process_improvement_capture": {
            "state": CONTEXTUAL_UNAVAILABLE,
            "source": "Manager docs-closeout process_improvement_capture context",
            "reason": unavailable_reason,
        },
    }

    return {
        "schema": CURRENT_STATE_SCHEMA,
        "plan_path": str(plan_path),
        "status_value": res.status_value,
        "status_norm": res.status_norm,
        "status_source": "PLAN_PATH header **Status:**",
        "status_line": res.status_line,
        "runtime_class": res.runtime_class,
        "runtime_class_reason": res.runtime_class_reason,
        "queue_closeout_ready": res.queue_closeout_ready,
        "queue_closeout_kind": res.queue_closeout_kind,
        "queue_closeout_reason": res.queue_closeout_reason,
        "review_readback_state": res.review_readback_state,
        "review_readback_reason": res.review_readback_reason,
        "review_route": review_route,
        "review_next_owner": review_next_owner,
        "scope_expansion_carrier_state": res.scope_expansion_carrier_state,
        "scope_expansion_state": res.scope_expansion_state,
        "scope_expansion_target_contour": res.scope_expansion_target_contour,
        "scope_expansion_source_ref": res.scope_expansion_source_ref,
        "scope_expansion_reason": res.scope_expansion_reason,
        "machine_authority_decision_state": res.machine_authority_decision_state,
        "machine_authority_decision_reason": res.machine_authority_decision_reason,
        "machine_authority_decision_id": res.machine_authority_decision_id,
        "machine_authority_decision_route": res.machine_authority_decision_route,
        "machine_authority_decision_carrier_sha256": res.machine_authority_decision_carrier_sha256,
        "machine_authority_decision_confirmation_state": res.machine_authority_decision_confirmation_state,
        "machine_authority_decision_ref_state": res.machine_authority_decision_ref_state,
        "machine_authority_decision_ref_reason": res.machine_authority_decision_ref_reason,
        "terminal_disposition": res.terminal_disposition,
        "delivery_green": res.delivery_green,
        "staging_policy": res.staging_policy,
        "durable_capture_required": res.durable_capture_required,
        "accepted_red_successor_plan": res.accepted_red_successor_plan,
        "accepted_red_historical_review": res.accepted_red_historical_review,
        "accepted_red_review_bundle_sha256": res.accepted_red_review_bundle_sha256,
        "terminal_disposition_reason": res.terminal_disposition_reason,
        "source_route_state": res.source_route_state,
        "source_route_accepted_route": res.source_route_accepted_route,
        "source_route_queue_admission": res.source_route_queue_admission,
        "source_route_runner_admission": res.source_route_runner_admission,
        "source_route_non_executable_carrier_state": res.source_route_non_executable_carrier_state,
        "source_route_non_executable_carrier_reason": res.source_route_non_executable_carrier_reason,
        "analysis_route_lifecycle_state": res.analysis_route_lifecycle_state,
        "analysis_route_lifecycle_reason": res.analysis_route_lifecycle_reason,
        "analysis_route_lifecycle_next_owner": res.analysis_route_lifecycle_next_owner,
        "analysis_route_lifecycle_budget_status": res.analysis_route_lifecycle_budget_status,
        "analysis_route_lifecycle_needs_analysis_depth_cap": res.analysis_route_lifecycle_needs_analysis_depth_cap,
        "analysis_route_lifecycle_current_needs_analysis_depth": res.analysis_route_lifecycle_current_needs_analysis_depth,
        "analysis_route_lifecycle_stale_trigger_state": res.analysis_route_lifecycle_stale_trigger_state,
        "promoted_from_state": res.promoted_from_state,
        "promoted_from_accepted_route": res.promoted_from_accepted_route,
        "promoted_from_queue_admission": res.promoted_from_queue_admission,
        "promoted_from_runner_admission": res.promoted_from_runner_admission,
        "queue_activation_state": res.queue_activation_state,
        "queue_activation_carrier_state": res.queue_activation_carrier_state,
        "route_guard_kind": res.route_guard_kind,
        "route_guard_reason": res.route_guard_reason,
        "docs_closeout_state": CONTEXTUAL_UNAVAILABLE,
        "docs_closeout_reason": unavailable_reason,
        "final_docs_commit": CONTEXTUAL_UNAVAILABLE,
        "final_docs_commit_reason": unavailable_reason,
        "followups_reconciliation_state": CONTEXTUAL_UNAVAILABLE,
        "followups_reconciliation_reason": unavailable_reason,
        "process_improvement_capture_state": CONTEXTUAL_UNAVAILABLE,
        "process_improvement_capture_reason": unavailable_reason,
        "terminal_ready_state": terminal_ready_state,
        "terminal_ready_reason": terminal_ready_reason,
        "blocker_state": blocker_state,
        "blocker_reason": blocker_reason,
        "authorities": authorities,
    }


def json_payload(res: OracleResult, plan_path: Path) -> dict[str, object]:
    review_route, review_next_owner = review_operational_route(res.review_readback_state)
    return {
        "status_line": res.status_line,
        "status_value": res.status_value,
        "status_norm": res.status_norm,
        "plan_type": res.plan_type,
        "plan_type_norm": res.plan_type_norm,
        "planning_contour_marker": res.planning_contour_marker,
        "planning_contour_role": res.planning_contour_role,
        "planning_contour_readback_state": res.planning_contour_readback_state,
        "planning_contour_readback_reason": res.planning_contour_readback_reason,
        "scope_expansion_carrier_state": res.scope_expansion_carrier_state,
        "scope_expansion_state": res.scope_expansion_state,
        "scope_expansion_target_contour": res.scope_expansion_target_contour,
        "scope_expansion_source_ref": res.scope_expansion_source_ref,
        "scope_expansion_reason": res.scope_expansion_reason,
        "machine_authority_decision_state": res.machine_authority_decision_state,
        "machine_authority_decision_reason": res.machine_authority_decision_reason,
        "machine_authority_decision_id": res.machine_authority_decision_id,
        "machine_authority_decision_route": res.machine_authority_decision_route,
        "machine_authority_decision_carrier_sha256": res.machine_authority_decision_carrier_sha256,
        "machine_authority_decision_confirmation_state": res.machine_authority_decision_confirmation_state,
        "machine_authority_decision_ref_state": res.machine_authority_decision_ref_state,
        "machine_authority_decision_ref_reason": res.machine_authority_decision_ref_reason,
        "terminal_disposition": res.terminal_disposition,
        "delivery_green": res.delivery_green,
        "staging_policy": res.staging_policy,
        "durable_capture_required": res.durable_capture_required,
        "accepted_red_successor_plan": res.accepted_red_successor_plan,
        "accepted_red_historical_review": res.accepted_red_historical_review,
        "accepted_red_review_bundle_sha256": res.accepted_red_review_bundle_sha256,
        "terminal_disposition_reason": res.terminal_disposition_reason,
        "source_route_state": res.source_route_state,
        "source_route_accepted_route": res.source_route_accepted_route,
        "source_route_promoted_artifact_kind": res.source_route_promoted_artifact_kind,
        "source_route_promoted_artifact_ref": res.source_route_promoted_artifact_ref,
        "source_route_queue_admission": res.source_route_queue_admission,
        "source_route_runner_admission": res.source_route_runner_admission,
        "source_route_non_executable_carrier_state": res.source_route_non_executable_carrier_state,
        "source_route_non_executable_carrier_reason": res.source_route_non_executable_carrier_reason,
        "analysis_route_lifecycle_state": res.analysis_route_lifecycle_state,
        "analysis_route_lifecycle_reason": res.analysis_route_lifecycle_reason,
        "analysis_route_lifecycle_next_owner": res.analysis_route_lifecycle_next_owner,
        "analysis_route_lifecycle_budget_status": res.analysis_route_lifecycle_budget_status,
        "analysis_route_lifecycle_needs_analysis_depth_cap": res.analysis_route_lifecycle_needs_analysis_depth_cap,
        "analysis_route_lifecycle_current_needs_analysis_depth": res.analysis_route_lifecycle_current_needs_analysis_depth,
        "analysis_route_lifecycle_stale_trigger_state": res.analysis_route_lifecycle_stale_trigger_state,
        "promoted_from_state": res.promoted_from_state,
        "promoted_from_authority_note": res.promoted_from_authority_note,
        "promoted_from_accepted_route": res.promoted_from_accepted_route,
        "promoted_from_promoted_artifact_kind": res.promoted_from_promoted_artifact_kind,
        "promoted_from_promoted_artifact_ref": res.promoted_from_promoted_artifact_ref,
        "promoted_from_queue_admission": res.promoted_from_queue_admission,
        "promoted_from_runner_admission": res.promoted_from_runner_admission,
        "queue_activation_carrier_state": res.queue_activation_carrier_state,
        "queue_activation_state": res.queue_activation_state,
        "pending_activation": res.pending_activation,
        "pending_activation_reason": res.pending_activation_reason,
        "review_readback_state": res.review_readback_state,
        "review_readback_reason": res.review_readback_reason,
        "review_route": review_route,
        "review_next_owner": review_next_owner,
        "route_guard_triggered": res.route_guard_triggered,
        "route_guard_kind": res.route_guard_kind,
        "route_guard_reason": res.route_guard_reason,
        "route_guard_next_owner": res.route_guard_next_owner,
        "owner_qna_readback_state": res.owner_qna_readback_state,
        "owner_qna_readback_reason": res.owner_qna_readback_reason,
        "open_owner_questions": [
            {
                "id": question.qid,
                "line_no": question.line_no,
                "state": question.state,
                "text": question.text,
            }
            for question in res.open_owner_questions
        ],
        "owner_qna_issues": [
            {
                "line_no": issue.line_no,
                "kind": issue.kind,
                "text": issue.text,
                "message": issue.message,
            }
            for issue in res.owner_qna_issues
        ],
        "runtime_class": res.runtime_class,
        "runtime_class_reason": res.runtime_class_reason,
        "queue_closeout_ready": res.queue_closeout_ready,
        "queue_closeout_kind": res.queue_closeout_kind,
        "queue_closeout_reason": res.queue_closeout_reason,
        "decomposition_child_state": res.decomposition_child_state,
        "decomposition_child_reason": res.decomposition_child_reason,
        "decomposition_child_paths": list(res.decomposition_child_paths),
        "decomposition_child_issues": [
            {
                "line_no": issue.line_no,
                "kind": issue.kind,
                "value": issue.value,
                "message": issue.message,
            }
            for issue in res.decomposition_child_issues
        ],
        "small_model_ready_child": res.small_model_ready_child,
        "small_model_readiness_state": res.small_model_readiness_state,
        "small_model_readiness_findings": [
            {
                "child_path": finding.child_path,
                "line_no": finding.line_no,
                "field": finding.field,
                "severity": finding.severity,
                "finding_kind": finding.finding_kind,
                "value": finding.value,
                "message": finding.message,
                "blocks_queue": finding.blocks_queue,
            }
            for finding in res.small_model_readiness_findings
        ],
        "plan_mtime": res.plan_mtime,
        "plan_size": res.plan_size,
        "plan_hash": res.plan_hash,
        "oracle_run_id": res.oracle_run_id,
        "plan_path": str(plan_path),
        "current_state": build_current_state(res, plan_path),
    }


def format_current_state_plain(current_state: Mapping[str, object]) -> str:
    scalar_fields = (
        "schema",
        "plan_path",
        "status_value",
        "status_norm",
        "status_source",
        "runtime_class",
        "queue_closeout_ready",
        "queue_closeout_kind",
        "review_readback_state",
        "review_readback_reason",
        "scope_expansion_carrier_state",
        "scope_expansion_state",
        "scope_expansion_target_contour",
        "scope_expansion_source_ref",
        "scope_expansion_reason",
        "machine_authority_decision_state",
        "machine_authority_decision_reason",
        "machine_authority_decision_id",
        "machine_authority_decision_route",
        "machine_authority_decision_carrier_sha256",
        "machine_authority_decision_confirmation_state",
        "machine_authority_decision_ref_state",
        "machine_authority_decision_ref_reason",
        "source_route_state",
        "source_route_accepted_route",
        "source_route_queue_admission",
        "source_route_runner_admission",
        "source_route_non_executable_carrier_state",
        "source_route_non_executable_carrier_reason",
        "analysis_route_lifecycle_state",
        "analysis_route_lifecycle_reason",
        "analysis_route_lifecycle_next_owner",
        "analysis_route_lifecycle_budget_status",
        "analysis_route_lifecycle_needs_analysis_depth_cap",
        "analysis_route_lifecycle_current_needs_analysis_depth",
        "analysis_route_lifecycle_stale_trigger_state",
        "promoted_from_state",
        "promoted_from_accepted_route",
        "promoted_from_queue_admission",
        "promoted_from_runner_admission",
        "queue_activation_state",
        "route_guard_kind",
        "docs_closeout_state",
        "final_docs_commit",
        "followups_reconciliation_state",
        "process_improvement_capture_state",
        "terminal_ready_state",
        "blocker_state",
    )
    lines: list[str] = []
    for field in scalar_fields:
        lines.append(f"{field}={current_state.get(field, '')}")
    lines.append(
        "authorities="
        + json.dumps(current_state.get("authorities", {}), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="plan_status_oracle",
        description="Deterministically extract header **Status:** from a plan file.",
    )
    parser.add_argument("plan_path", help="Path to docs/plans/<...>.md")
    parser.add_argument("--json", action="store_true", help="Print JSON output (debug/manager use).")
    parser.add_argument(
        "--manager-mode",
        choices=ACTUAL_MANAGER_MODES,
        help="Evaluate Manager-mode admission for the supplied concrete runtime.",
    )
    parser.add_argument(
        "--current-state",
        action="store_true",
        help="Print compact derived current-state readback (debug/manager use).",
    )
    args = parser.parse_args(argv)

    if args.manager_mode and not args.json:
        print("--manager-mode requires --json.", file=sys.stderr)
        return 2

    plan_path = Path(args.plan_path)
    try:
        context = resolve_top_level_context(_repo_root_for_plan_path(plan_path))
    except ContractAuthorityError as exc:
        print(f"contract_authority_preflight_failed:{exc.reason_code}", file=sys.stderr)
        return 3
    if not plan_path.exists():
        print(f"Missing plan: {plan_path}", file=sys.stderr)
        return 2
    if not plan_path.is_file():
        print(f"Not a file: {plan_path}", file=sys.stderr)
        return 2

    try:
        res = oracle_result(plan_path, context=context)
    except UnicodeDecodeError as e:
        print(f"Plan read error (utf-8 decode): {e}", file=sys.stderr)
        return 3
    except OSError as e:
        print(f"Plan read error: {e}", file=sys.stderr)
        return 3
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 3
    except ContractAuthorityError as e:
        print(f"contract_authority_preflight_failed:{e.reason_code}", file=sys.stderr)
        return 3

    if args.json:
        payload = json_payload(res, plan_path)
        if args.manager_mode:
            try:
                plan_meta = parse_plan_meta_admission_carrier(res.captured_plan_text)
            except ValueError as e:
                print(str(e), file=sys.stderr)
                return 3
            admission = manager_mode_admission(plan_meta, args.manager_mode)
            payload.update(admission)
            sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
            return 0 if admission["manager_mode_admitted"] else 4
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        return 0

    if args.current_state:
        sys.stdout.write(format_current_state_plain(build_current_state(res, plan_path)))
        return 0

    sys.stdout.write(res.status_line + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

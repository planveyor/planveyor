#!/usr/bin/env python3
"""Lint docs/plans/*.md for basic Q&A + header hygiene.

Checks:
- Exactly one `**Status:**` header exists (no missing/duplicates, no template placeholder).
- Plan-family schema version is explicit on the canonical template; versionless non-template plans stay legacy-compatible.
- For current plan.v2 plans: a valid `plan_meta` JSON block exists and includes `cluster`.
- For navigation-contract plans: optional `plan_meta.parent` / `plan_meta.next_plans` keep deterministic repo-relative shape.
- If `plan_meta.phase_overlay` is present, it must use canonical values and a compatible `phase_state`.
- For navigation-contract plans: `## Close-out routing` and `## Verification rerun / exec handoff` are required-or-`N/A (why)`.
- For current plan.v2 plans: large fenced code blocks are rejected (move implementation sketches to `docs/code_drafts/`).
- For plans in execution/review flow: a code draft link (`docs/code_drafts/*.md`) is required and must exist.
- For plans in execution/review flow: if Planner logged `NO SUGGESTIONS`, the linked code draft must contain a review stamp line (append-only).
- For rerun-shaped coder states: a blocker review artifact cannot stay silently current without an explicit stale/superseded + rerun note in `## Review artifacts`.
- For new reviewer-facing plans/review bundles: ad-hoc reviewer automation (`.tmp/*_flow.js`, inline `run-code`) is forbidden
  in `## Visual Acceptance` contract and linked review artifacts.
- For documentation-impact-era plans: `## Documentation impact / provenance` is checked warning-first for
  missing/placeholder carrier values. For new execution/review handoffs, exact drift between
  `Synchronous doc/registry targets` and linked `code_draft_meta.targets` is a hard error.
- For scope-route-era active dev plans: ambiguous scope/follow-up/broad-cleanup wording must name an explicit
  route class (`same-contract reroute`, `real scope expansion`, or `de-scoped follow-up`).
- For new analysis-wave plans: `analysis_pack.promoted_route_refs` must stay refs-only and must not duplicate
  literal accepted-route fields owned by `## Promoted route artifact`.
- For new analysis-wave plans: `analysis_pack` route completeness and inspected-source floor are checked warning-first.
- For new planning-contour plans: fixture-backed route/linkage carriers must be object-shaped and manifest-valid
  where the V1/E3/E4 contract is proven; V2/V3-dependent route discrimination stays warning-first.
- For new Architect intake plans: `## Как я понял задачу` is required as a separate human-readable carrier
  before the plan leaves `Architect initial draft`.
- For current plan.v2 plans: core human-facing statement sections should be Russian-first; English is reserved for
  identifiers, paths, commands, enum/API/field names, and literal source terms.
- If plan is marked Done: no open Q&A items or open `## Post-merge gate` checklist items remain.
- Every Q&A item opened via `status=open` must be later closed or superseded.

This is intentionally lightweight and deterministic (no markdown parser).
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from contextlib import contextmanager
import contextvars
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import TYPE_CHECKING, Any, Iterable, Iterator, Sequence

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
        read_declared_text,
        resolve_top_level_context,
    )
else:
    ContractAuthorityError = _authority.ContractAuthorityError
    ContractContext = _authority.ContractContext
    context_for_reader = _authority.context_for_reader
    read_declared_text = _authority.read_declared_text
    resolve_top_level_context = _authority.resolve_top_level_context

import plan_status_oracle
import retrieval_telemetry_receipt
import review_header_metadata
import review_visual_lane_contract
from review_target_snapshot import (
    CURRENT_BUNDLE_TARGET,
    SnapshotError,
    build_current_bundle_snapshot,
    validate_snapshot_payload,
)
from review_schema_contract import (
    CODE_DOC_REVIEW_BLOCKER_STATUS_NORM,
    CODE_DOC_REVIEW_FINAL_STATUS_NORMS,
    CODE_DOC_REVIEW_OK_STATUS_NORM,
    normalize_review_status,
    review_blocker_status_regex,
)


# IMPORTANT:
# This tool is executed from other repos via shell wrappers (`source scripts/planveyor.zsh`),
# so paths must be resolved relative to the current working directory (repo/worktree root),
# not relative to the tooling repo where this script lives.
REPO_ROOT = Path.cwd().resolve()
PLANS_ROOT = REPO_ROOT / "docs" / "plans"
DOCS_META_ROOT = REPO_ROOT / "docs" / "_meta"
PLAN_VOCAB_PATH = DOCS_META_ROOT / "plan_vocab.json"

ALLOWED_CLUSTERS: frozenset[str] = frozenset()
DEPRECATED_CLUSTER_ALIASES: dict[str, str] = {}
CANONICAL_PLAN_STATUSES: tuple[str, ...] = ()
CODE_DRAFT_REQUIRED_STATUS_NORMS: frozenset[str] = frozenset()
SHARED_HELPER_INVENTORY_TERMINAL_CURRENT_PROOF_STATUS_NORMS: frozenset[str] = frozenset({"superseded"})
ALLOWED_PHASE_OVERLAYS: frozenset[str] = frozenset()
PHASE_OVERLAY_STATES: dict[str, frozenset[str]] = {}
ALLOWED_REQUIRED_MANAGER_MODES: frozenset[str] = frozenset()
DEFAULT_BLOCKING_DEPENDENCY_CARRIER = {
    "field": "blocking_depends_on",
    "shape": "sorted_unique_repo_relative_plan_path_array",
    "subset_of": "depends_on",
    "clearance": "delivery_green",
}
BLOCKING_DEPENDENCY_CARRIER_FIELD = DEFAULT_BLOCKING_DEPENDENCY_CARRIER["field"]
BLOCKING_DEPENDENCY_CARRIER_SHAPE = DEFAULT_BLOCKING_DEPENDENCY_CARRIER["shape"]
BLOCKING_DEPENDENCY_CARRIER_SUBSET_FIELD = DEFAULT_BLOCKING_DEPENDENCY_CARRIER["subset_of"]
BLOCKING_DEPENDENCY_CARRIER_CLEARANCE_FIELD = DEFAULT_BLOCKING_DEPENDENCY_CARRIER["clearance"]
BLOCKING_DEPENDENCY_EARLY_STATUS_NORMS = frozenset(
    {"architect initial draft", "architect draft", "architect response"}
)
BLOCKING_DEPENDENCY_TERMINAL_STATUS_NORMS = frozenset({"done", "superseded"})
EXACT_BUNDLE_ADVISORY_STATUS_NORMS = {
    "architect initial draft",
    "architect draft",
    "ready for planner",
    "planner intake",
    "ready for architect response",
    "architect response",
}
ORIGIN_PLAN_IN_REVIEW_TARGETS_REASON = "origin_plan_in_review_targets"
ORIGIN_PLAN_EARLY_DEV_STATUS_NORMS = frozenset(EXACT_BUNDLE_ADVISORY_STATUS_NORMS)
ORIGIN_PLAN_TERMINAL_STATUS_NORMS = frozenset({"done", "superseded"})
ORIGIN_PLAN_REVIEW_TARGET_CLASSIFICATIONS = (
    "range_exempt",
    "terminal_history",
    "parked_reference",
    "restamp_before_handoff",
)
DECOMPOSITION_EARLY_INTAKE_STATUS_NORMS = frozenset(
    {
        "architect initial draft",
        "architect draft",
        "ready for planner",
        "planner intake",
    }
)
DECOMPOSITION_MATERIALIZATION_STATUS_NORMS = frozenset(
    {
        "planner finalize",
        "ready for coder",
        "coder intake",
        "in progress",
        "ready for architect response",
        "architect response",
    }
)

# Allow old plan headers that used Markdown blockquotes (`> **Status:** ...`).
# NOTE: do not use `**Status:**` anywhere else in a plan (it's reserved for workflow routing).
STATUS_LINE_RE = re.compile(r"^\s*(?:>\s*)?\*\*Status:\*\*\s*(?P<status>.+?)\s*$")
SCHEMA_VERSION_LINE_RE = re.compile(r"^\s*(?:>\s*)?\*\*Schema version:\*\*\s*(?P<value>.+?)\s*$", re.IGNORECASE)
DONE_RE = re.compile(r"\bdone\b", re.IGNORECASE)
CURRENT_PLAN_SCHEMA_VERSION = "plan.v2"
LEGACY_PLAN_SCHEMA_VERSION = "plan.v1"

DEFAULT_EXCLUDES = {
    PLANS_ROOT / "README.md",
    PLANS_ROOT / "_template.md",
}

# Require code_draft references once a plan is in execution/review flow.
PLAN_TYPE_RE = re.compile(r"^\s*(?:>\s*)?\*\*Plan type:\*\*\s*(?P<plan_type>.+?)\s*$")
CODE_DRAFT_RE = re.compile(r"docs/code_drafts/[A-Za-z0-9][A-Za-z0-9_./-]*\.md")
REVIEW_ARTIFACT_ROOTS = ("docs/code_reviews/", "docs/doc_reviews/")
LEGACY_REVIEW_ARTIFACT_ROOTS = REVIEW_ARTIFACT_ROOTS + ("docs/reviews/",)
REVIEW_ARTIFACT_PATH_TOKEN_RE = re.compile(
    r"(?:^|(?<=[\s`'\"\(\[\{>;,:\|]))"
    r"[^\s`'\"\(\[\{\)\]\}>;,:#|]*"
    r"docs/(?:code_reviews|doc_reviews|reviews)/[A-Za-z0-9][^\s`'\"\)\]\}>;,:#|]*"
)
# Outside inline code spans, Markdown punctuation terminates a review-path
# token. Inside a code span, punctuation is literal data and must be retained
# until eligibility evaluates the full carrier.
REVIEW_ARTIFACT_CODE_SPAN_TOKEN_RE = re.compile(
    r"\S*docs/(?:code_reviews|doc_reviews|reviews)/[A-Za-z0-9]\S*"
)
REVIEW_ARTIFACT_ANCHOR_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
REVIEW_ARTIFACT_OUTSIDE_ANCHOR_TRAILING_DELIMITERS = ")]}>;,:|"
REVIEW_ARTIFACTS_HEADING_RE = re.compile(r"^\s*##\s+Review artifacts\b", re.IGNORECASE)
LIVE_REVIEW_ARTIFACT_LINE_RE = re.compile(
    r"^\s*-\s*(?:Code review \(primary\)|Doc review \(docs-only\))\s*:\s*(?P<body>.*)$",
    re.IGNORECASE,
)
REVIEW_DATE_LINE_RE = re.compile(r"^\s*\*\*Date:\*\*\s*(?P<value>.+?)\s*$", re.IGNORECASE)
REVIEW_TARGET_LINE_RE = re.compile(r"^\s*\*\*(?:Review target|Target|Range):\*\*\s*(?P<value>.+?)\s*$", re.IGNORECASE)
PLAN_REVIEW_TARGET_LINE_RE = re.compile(
    r"^\s*-\s*Review target:\s*`(?P<value>[^`]+)`\s*$",
    re.IGNORECASE,
)
IMMUTABLE_RANGE_REVIEW_TARGET_RE = re.compile(
    r"^RANGE=[0-9a-f]{7,40}\.\.[0-9a-f]{7,40} \(EXCLUDE_DOCS=[01]\)$",
    re.IGNORECASE,
)
IMMUTABLE_COMMIT_REVIEW_TARGET_RE = re.compile(
    r"^COMMIT=[0-9a-f]{7,40}$",
    re.IGNORECASE,
)
REVIEW_BLOCKER_STATUS_RE = re.compile(review_blocker_status_regex(), re.IGNORECASE)
STALE_OR_SUPERSEDED_RE = re.compile(r"\b(?:stale|superseded)\b", re.IGNORECASE)
RERUN_RE = re.compile(r"\brerun\b", re.IGNORECASE)
STALE_NOTE_LINE_RE = re.compile(r"^\s*-\s*stale note\s*\((?P<meta>[^)]*)\)\s*:\s*(?P<body>.*)$", re.IGNORECASE)
RERUN_NOTE_LINE_RE = re.compile(r"^\s*-\s*rerun note\s*\((?P<meta>[^)]*)\)\s*:\s*(?P<body>.*)$", re.IGNORECASE)
SAME_REVIEW_FILE_RE = re.compile(r"(?:same review (?:file|artifact)|этот же review[- ]file)", re.IGNORECASE)
INLINE_TIMESTAMP_RE = re.compile(r"(?P<value>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}|\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2})")
# Planner should explicitly confirm code draft review when they had no suggestions.
PLANNER_SUGGESTIONS_HEADING_RE = re.compile(r"^\s*###\s+planner suggestions\b", re.IGNORECASE)
SECTION_HEADING_RE = re.compile(r"^\s*#{2,3}\s+")
NO_SUGGESTIONS_RE = re.compile(r"\bno suggestions\b", re.IGNORECASE)
PLANNER_NO_SUGGESTIONS_STAMP_RE = re.compile(
    r"\bplanner\b.*\bno suggestions\b|\bno suggestions\b.*\bplanner\b",
    re.IGNORECASE,
)

VISUAL_ACCEPTANCE_RE = re.compile(r"^\s*##\s+visual acceptance\b", re.IGNORECASE)
HOW_TO_RUN_REVIEWER_HEADING_RE = re.compile(r"^\s*###\s+how to run\s+\(reviewer\)\s*$", re.IGNORECASE)
VISUAL_CHECKS_HEADING_RE = re.compile(r"^\s*###\s+visual checks\b", re.IGNORECASE)

JSON_FENCE_START_RE = re.compile(r"^\s*```json\s*$", re.IGNORECASE)
FENCE_START_RE = re.compile(r"^\s*```(?P<lang>[A-Za-z0-9_+-]*)\s*$")
FENCE_END_RE = re.compile(r"^\s*```\s*$")
# Kept deliberately byte-for-byte compatible with the former selector in
# review_artifact_lint.py.  The selector is public compatibility surface and
# must continue to discover compact lane receipts regardless of where the
# JSON fence sits in a plan.
JSON_BLOCK_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)
SPACE_RE = re.compile(r"\s+")
ARCHITECT_UNDERSTANDING_HEADING_RE = re.compile(r"^\s*#{2,4}\s+Как я понял задачу\b", re.IGNORECASE)
ANY_MD_HEADING_RE = re.compile(r"^\s*#{1,6}\s+")
CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
RUSSIAN_PLAN_STATEMENT_SECTION_RE = re.compile(
    r"^\s*##\s+(?P<title>"
    r"Как я понял задачу|Problem|Solution(?:\s*\([^)]*\))?|Decisions(?:\s*\([^)]*\))?|"
    r"Scope|Out of scope|Acceptance criteria\s*/\s*DoD"
    r")\b",
    re.IGNORECASE,
)

# Limit huge code blocks in plans (encourage moving sketches to docs/code_drafts).
# Calibrated from a representative historical plan (largest code block there was ~81 lines).
MAX_PLAN_CODE_BLOCK_LINES = 120
MAX_PLAN_CODE_BLOCK_UTF8_BYTES = 16_384

# Disallow implementation snippets in plans (use docs/code_drafts instead).
DISALLOWED_PLAN_FENCE_LANGS = {
    "py",
    "python",
}

DECISIONS_HEADING_RE = re.compile(r"^\s*##\s+Decisions\s*\(final\)\s*$", re.IGNORECASE)
CHANGES_HEADING_RE = re.compile(r"^\s*##\s+Changes\s*\(by area\)\s*$", re.IGNORECASE)
H2_HEADING_RE = re.compile(r"^\s*##\s+")
STATE_TRANSITION_DECLARATION_H2_HEADING_RE = re.compile(r"^ {0,3}##[ \t]+")
REVIEWABILITY_PREFLIGHT_RECEIPT_HEADING_RE = re.compile(
    r"^ {0,3}##[ \t]+Reviewability preflight receipt\s*$", re.IGNORECASE
)
STATE_TRANSITION_DECLARATIONS_HEADING_RE = re.compile(
    r"^ {0,3}###[ \t]+State-transition declarations\s*$"
)
STATE_TRANSITION_DECLARATIONS_HEADING_CANDIDATE_RE = re.compile(
    r"^ {0,3}###[ \t]+state[- ]transition declarations\s*$", re.IGNORECASE
)
STATE_TRANSITION_DECLARATION_FENCE_START_RE = re.compile(
    r"^ {0,3}(?P<marker>`{3,}|~{3,})(?:[^\r\n]*)$"
)
STATE_TRANSITION_DECLARATION_RAW_HTML_BLOCK_START_RE = re.compile(
    r"^ {0,3}<(?P<tag>script|pre|style|textarea)(?:[ \t>/]|$)", re.IGNORECASE
)
STATE_TRANSITION_DECLARATION_CDATA_BLOCK_START_RE = re.compile(r"^ {0,3}<!\[CDATA\[", re.IGNORECASE)
STATE_TRANSITION_DECLARATION_PROCESSING_INSTRUCTION_BLOCK_START_RE = re.compile(r"^ {0,3}<\?")
STATE_TRANSITION_DECLARATION_DECLARATION_BLOCK_START_RE = re.compile(r"^ {0,3}<![A-Z]")
STATE_TRANSITION_DECLARATION_LINE_RE = re.compile(
    r"^ {0,3}-[ \t]+`(?P<label>[^`]+)`[ \t]*:[ \t]*(?P<value>.*?)[ \t]*$"
)
STATE_TRANSITION_DECLARATION_LABELS = (
    "before-state",
    "allowed mutation inventory",
    "after-state",
    "protected-target post-review continuity",
)
STATE_TRANSITION_DECLARATION_SUBFIELDS = {
    "before-state": ("carrier", "identity", "expected"),
    "allowed mutation inventory": ("writer", "entrypoint", "targets"),
    "after-state": ("carrier", "identity", "expected"),
    "protected-target post-review continuity": ("targets", "on_change"),
}
STATE_TRANSITION_DECLARATION_PLACEHOLDERS = frozenset(
    {"", "...", "tbd", "tbc", "todo", "fixme", "unconfirmed", "unknown", "n/a", "na"}
)
STATE_TRANSITION_DECLARATION_PLACEHOLDER_PREFIX_RE = re.compile(
    r"^(?:tbd|tbc|todo|fixme|unconfirmed|unknown|n/a|na)(?=$|[\s:;,.(\[{\-])",
    re.IGNORECASE,
)
STATE_TRANSITION_DECLARATION_LABEL_FAMILY_RE = re.compile(
    r"(?:^|[- _])(?:state|mutation|inventory|target|continuity)(?:$|[- _])",
    re.IGNORECASE,
)
CLOSE_OUT_ROUTING_HEADING_RE = re.compile(r"^\s*##\s+Close-out routing\b", re.IGNORECASE)
POST_MERGE_GATE_HEADING_RE = re.compile(r"^\s*##\s+Post-merge gate\b", re.IGNORECASE)
ROLLOUT_PACKET_HANDOFF_HEADING_RE = re.compile(r"^\s*##\s+Rollout packet handoff\b", re.IGNORECASE)
VERIFICATION_HANDOFF_HEADING_RE = re.compile(r"^\s*##\s+Verification rerun / exec handoff\b", re.IGNORECASE)
OPEN_MARKDOWN_CHECKBOX_RE = re.compile(r"^\s*-\s*\[\s\]\s*(?P<body>.*)$")
REPO_RELATIVE_PLAN_PATH_RE = re.compile(r"^docs/plans/[A-Za-z0-9][A-Za-z0-9_./-]*\.md$")
ROLL_OUT_PACKET_PATH_RE = re.compile(r"^docs/rollout_packets/[A-Za-z0-9][A-Za-z0-9_./-]*\.md$")
ROLL_OUT_PACKET_TARGET_REPO_SET_RE = re.compile(
    r"^[a-z0-9][a-z0-9-]*(?:\s*(?:\+|\|)\s*[a-z0-9][a-z0-9-]*)*$"
)
ROLL_OUT_PACKET_PLAN_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
CLOSE_OUT_ROUTING_REQUIRED_LINES = (
    "- Roadmap/queue sync:",
    "- Follow-up sync:",
    "- Next bounded slice:",
    "- Terminal outcome:",
)
ROLLOUT_PACKET_HANDOFF_REQUIRED_LINES = (
    "- Role:",
    "- Packet path:",
    "- Target repo:",
    "- Suggested target plan slug:",
    "- Queue after import:",
)
VERIFICATION_HANDOFF_REQUIRED_LINES = (
    "- Mode:",
    "- Context source:",
    "- Prompt:",
    "- Command:",
    "- Expected artifact:",
)
VERIFICATION_HANDOFF_ALLOWED_MODES = frozenset({"reuse-thread", "fresh-exec", "manager-custom-pipeline"})
DOCUMENTATION_IMPACT_HEADING_RE = re.compile(
    r"^\s*##\s+Documentation impact / provenance\b",
    re.IGNORECASE,
)
DOCUMENTATION_IMPACT_REQUIRED_LINES = (
    "- Source docs used:",
    "- Synchronous doc/registry targets:",
    "- Post-merge canon updates:",
    "- Deferred documentation follow-ups:",
    "- Provenance refs:",
)
DOCUMENTATION_IMPACT_SYNC_TARGET_LINE = "- Synchronous doc/registry targets:"
EXPLICIT_NA_WITH_REASON_RE = re.compile(r"\bn\s*/\s*a\b.*\bwhy\s*=", re.IGNORECASE)
REPO_RELATIVE_TARGET_RE = re.compile(
    r"`(?P<quoted>(?:docs|scripts)/[^`\s,;]+)`|(?P<bare>(?:docs|scripts)/[A-Za-z0-9_./-]+)"
)

MECHANISM_COVERAGE_HEADING_RE = re.compile(r"^\s*##\s+Mechanism coverage\b", re.IGNORECASE)
DECOMPOSITION_QUALITY_GATE_HEADING_RE = re.compile(r"^\s*##\s+Decomposition quality gate\b", re.IGNORECASE)
CHILD_PLAN_MAP_HEADING_RE = re.compile(r"^\s*##\s+Child plan map\b", re.IGNORECASE)
EXECUTION_QUEUE_HEADING_RE = re.compile(r"^\s*##\s+Execution queue\b", re.IGNORECASE)
ANALYSIS_PACK_HEADING_RE = re.compile(r"^\s*##\s+Analysis pack\b", re.IGNORECASE)
PROMOTED_ROUTE_ARTIFACT_HEADING_RE = re.compile(r"^\s*##\s+Promoted route artifact\b", re.IGNORECASE)
ACCEPTED_ROUTE_LITERAL_FIELDS = frozenset(
    {
        "accepted_route",
        "promoted_artifact_ref",
        "queue_admission",
        "runner_admission",
    }
)
ACCEPTED_ROUTE_DERIVED_PROMOTED_FROM_KEY = "promoted_from"
ACCEPTED_ROUTE_DERIVED_AUTHORITY_NOTE_KEY = "authority_note"
ACCEPTED_ROUTE_DERIVED_AUTHORITY_NOTE = "derived_read_only; source artifact is writable truth"
ACCEPTED_ROUTE_DERIVED_ACCEPTANCE_FIELDS = frozenset(
    {
        "queue_admission_at_acceptance",
        "runner_admission_at_acceptance",
    }
)
ACCEPTED_ROUTE_LITERAL_FIELD_RE = re.compile(
    r"`?\b(accepted_route|promoted_artifact_ref|queue_admission|runner_admission)\b`?",
    re.IGNORECASE,
)
NO_RELEVANT_HITS_RE = re.compile(r"\bNO\s+RELEVANT\s+HITS\b", re.IGNORECASE)
ANALYSIS_PACK_COMPLETION_WARNING_PREFIX = "Analysis pack completeness warning: "
ANALYSIS_ROUTE_LIFECYCLE_WARNING_PREFIX = "Analysis route lifecycle warning: "
ANALYSIS_ROUTE_LIFECYCLE_ERROR_PREFIX = "Analysis route lifecycle stop: "
ANALYSIS_PACK_ROUTE_REQUIRED_FIELDS = {
    "developer_wave": (
        "scope_refs",
        "documentation_impact_seed",
        "dependent_inventory_mutable_surfaces",
        "requirement_slices",
        "reviewability_seed",
        "runner_handoff_seed",
        "route_recommendation",
    ),
    "decomposition_wave": (
        "scope_refs",
        "documentation_impact_seed",
        "dependent_inventory_mutable_surfaces",
        "requirement_slices",
        "decomposition_sizing_rationale",
        "route_recommendation",
    ),
    "human_gate": (
        "scope_refs",
        "options_considered",
        "recommendation",
        "risks_escalation_triggers",
        "route_recommendation",
    ),
    "defer": (
        "scope_refs",
        "options_considered",
        "recommendation",
        "route_recommendation",
    ),
    "reject": (
        "recommendation",
        "route_recommendation",
    ),
}
PLANNING_CONTOUR_REQUIRED_KEYS = frozenset(
    {
        "wave_markers",
        "accepted_routes",
        "requirement_slice_kinds",
        "promoted_artifact_kinds",
        "queue_admission",
        "runner_admission",
        "queue_activation_states",
        "scope_expansion_states",
        "status_transition_matrix",
    }
)
PLANNING_CONTOUR_ACCEPTED_ROUTES = (
    "developer_wave",
    "decomposition_wave",
    "human_gate",
    "defer",
    "reject",
)
PLANNING_CONTOUR_REQUIREMENT_SLICE_KIND_VALUES = (
    "dev_candidate",
    "decomposition_candidate",
    "needs_analysis",
)
PLANNING_CONTOUR_REQUIREMENT_SLICE_KINDS: frozenset[str] = frozenset(
    PLANNING_CONTOUR_REQUIREMENT_SLICE_KIND_VALUES
)
PLANNING_CONTOUR_PROMOTED_ARTIFACT_KINDS = (
    "seed_dev_plan",
    "decomposition_umbrella",
    "owner_gate",
    "followup",
    "rejection_receipt",
)
PLANNING_CONTOUR_QUEUE_ADMISSION = (
    "queueable_now",
    "needs_planner",
    "needs_owner",
    "not_queueable",
)
PLANNING_CONTOUR_RUNNER_ADMISSION = (
    "frontier_only",
    "small_runner_ok",
    "small_runner_blocked",
)
PLANNING_CONTOUR_QUEUE_ACTIVATION_STATES = (
    "not_requested",
    "owner_approved",
    "architect_approved",
    "n/a",
)
PLANNING_CONTOUR_SCOPE_EXPANSION_STATES = (
    "n/a",
    "suspected",
    "reroute_required",
    "architect_accepted",
)
PLANNING_CONTOUR_ENUM_VALUES = {
    "accepted_routes": frozenset(PLANNING_CONTOUR_ACCEPTED_ROUTES),
    "requirement_slice_kinds": frozenset(PLANNING_CONTOUR_REQUIREMENT_SLICE_KIND_VALUES),
    "promoted_artifact_kinds": frozenset(PLANNING_CONTOUR_PROMOTED_ARTIFACT_KINDS),
    "queue_admission": frozenset(PLANNING_CONTOUR_QUEUE_ADMISSION),
    "runner_admission": frozenset(PLANNING_CONTOUR_RUNNER_ADMISSION),
    "queue_activation_states": frozenset(PLANNING_CONTOUR_QUEUE_ACTIVATION_STATES),
    "scope_expansion_states": frozenset(PLANNING_CONTOUR_SCOPE_EXPANSION_STATES),
}
PLANNING_CONTOUR_PROMOTED_FROM_REQUIRED_FIELDS = (
    "authority_note",
    "source_plan",
    "source_route_ref",
    "accepted_route",
    "promoted_artifact_kind",
    "promoted_artifact_ref",
    "queue_admission_at_acceptance",
    "runner_admission_at_acceptance",
)
PLANNING_CONTOUR_QUEUE_ACTIVATION_REQUIRED_FIELDS = ("state", "source_ref", "reason")
PLANNING_CONTOUR_SCOPE_EXPANSION_REQUIRED_FIELDS = ("state", "target_contour", "source_ref", "reason")
PLANNING_CONTOUR_SOURCE_ROUTE_REQUIRED_FIELDS = (
    "accepted_route",
    "promoted_artifact_kind",
    "promoted_artifact_ref",
    "queue_admission",
    "runner_admission",
)
PLANNING_CONTOUR_SOURCE_ROUTE_ANALYSIS_FIELDS = (
    "source_analysis_plan",
    "source_analysis_pack_ref",
)
PLANNING_CONTOUR_SOURCE_ROUTE_ENUM_FIELDS = {
    "accepted_route": "accepted_routes",
    "promoted_artifact_kind": "promoted_artifact_kinds",
    "queue_admission": "queue_admission",
    "runner_admission": "runner_admission",
}
PLANNING_CONTOUR_PROMOTED_FROM_ENUM_FIELDS = {
    "accepted_route": "accepted_routes",
    "promoted_artifact_kind": "promoted_artifact_kinds",
    "queue_admission_at_acceptance": "queue_admission",
    "runner_admission_at_acceptance": "runner_admission",
}
PLANNING_CONTOUR_SCHEMA_ERROR_PREFIX = "Planning-contour schema hard gate: "
PLANNING_CONTOUR_SCHEMA_WARNING_PREFIX = "Planning-contour schema warning: "
PLANNING_CONTOUR_FIXTURE_BACKED_SOURCE_ROUTES = frozenset({"developer_wave", "decomposition_wave"})
PLANNING_CONTOUR_PROMOTED_ROUTE_ARTIFACT_ANCHOR = "promoted-route-artifact"
REQUIREMENT_SLICE_KIND_RE = re.compile(r"\bslice_kind\s*=\s*(?P<value>[A-Za-z0-9_]+)\b", re.IGNORECASE)
NEEDS_ANALYSIS_KEY_UNKNOWNS_RE = re.compile(r"\bkey[_ -]?unknowns\b", re.IGNORECASE)
NEEDS_ANALYSIS_TRIGGER_RE = re.compile(
    r"\btrigger[_ -]?for[_ -]?promotion\b|\bpromotion[_ -]?trigger\b|\bfuture promotion trigger\b",
    re.IGNORECASE,
)
NEEDS_ANALYSIS_DEV_QUEUE_RE = re.compile(
    r"\bqueue_admission\s*=\s*queueable_now\b|"
    r"\brunner_admission\s*=\s*small_runner_ok\b|"
    r"\brunner_suitability\s*=\s*small_runner_ok\b|"
    r"\bsmall_model_ready_state\s*=\s*ready\b",
    re.IGNORECASE,
)
DEV_CONTOUR_DRIFT_SCOPE_EXPANSION_STATES = frozenset(
    {
        "suspected",
        "reroute_required",
        "architect_accepted",
    }
)
DEV_CONTOUR_CHILD_GRAPH_DRIFT_WARNING_PREFIX = "Dev-contour child graph drift warning: "
DEV_CONTOUR_PRE_CODER_STATUS_NORMS = frozenset({"planner finalize", "ready for coder"})
DECOMPOSITION_MECHANISM_SCHEMA_WARNING_PREFIX = "Decomposition mechanism schema warning: "
DECOMPOSITION_GRAPH_SHAPE_WARNING_PREFIX = "Decomposition graph-shape warning: "
SMALL_RUNNER_ADMISSION_WARNING_PREFIX = "Small-runner admission warning: "
LEGACY_CHILD_GRAPH_DRIFT_RE = re.compile(
    r"\bsplit_required\s*=\s*true\b|\bhidden child graph\b",
    re.IGNORECASE,
)
DEV_CONTOUR_FAILURE_MODE_FIELD_RE = re.compile(
    r"^\s*(?:[-*]\s*)?`?(?:decomposition_)?(?:failure_mode|failure_modes|smell|smell_detector)`?\s*[:=]\s*`?"
    r"(?P<mode>silent_scope_widening|hidden_dependency_drift)\b",
    re.IGNORECASE,
)
DEV_CONTOUR_CHILD_REF_MARKER_RE = re.compile(
    r"\b(?:child(?:[-_ ]?(?:plan|ref|refs|graph))?|promoted[-_ ]child|next[-_ ]plans?|execution[-_ ]queue)\b",
    re.IGNORECASE,
)
DEV_CONTOUR_LIVE_CHILD_REF_FIELD_RE = re.compile(
    r"^\s*(?:[-*]\s*)?`?(?:child(?:[-_ ]?(?:plan|ref|refs|graph))?|promoted[-_ ]child|next[-_ ]plans?)`?\s*:",
    re.IGNORECASE,
)
DELIVERED_BASELINE_CONTEXT_ROW_RE = re.compile(r"^\s*-\s*Delivered baseline:\s*", re.IGNORECASE)
DEV_CONTOUR_APPEND_ONLY_HISTORICAL_HEADINGS = frozenset(
    {
        "evidence (chronological, append-only)",
        "q&a log (chronological, append-only)",
        "suggestions log (chronological, append-only)",
        "objections / risks log (chronological, append-only)",
    }
)
DEV_CONTOUR_PROOF_LANES_RE = re.compile(
    r"^\s*(?:[-*]\s*)?`?(?:independent_)?proof_lanes?`?\s*[:=]\s*(?P<value>.+)$",
    re.IGNORECASE,
)
DEV_CONTOUR_INTEGRATION_OWNER_FIELD_RE = re.compile(
    r"^\s*(?:[-*]\s*)?`?(?:integration_owner|recomposition_owner|serialization_policy)`?\s*[:=]\s*`?(?P<value>.+?)`?\s*$",
    re.IGNORECASE,
)
DEV_CONTOUR_INTEGRATION_POLICY_TEXT_RE = re.compile(r"\b(?:serialized|sequential|blocking dependency)\b", re.IGNORECASE)
DEV_CONTOUR_INTEGRATION_ABSENCE_RE = re.compile(
    r"\b(?:absent|missing|not\s+(?:assigned|set|yet|serialized|sequential|blocking)|"
    r"unknown|unassigned|without|no\s+(?:integration|recomposition|serialization|owner|policy))\b",
    re.IGNORECASE,
)
UMBRELLA_ROADMAP_LIFECYCLE_WARNING_PREFIX = "Umbrella roadmap lifecycle warning: "
UMBRELLA_MARKER_RE = re.compile(r"\b(?:umbrella|master-plan)\b", re.IGNORECASE)
ROADMAP_MARKER_RE = re.compile(r"\b(?:roadmap|scaleout|scale-out)\b", re.IGNORECASE)
SELECTED_ROADMAP_CHILD_MARKER_RE = re.compile(
    r"\b(?:planning-contour|phase-?\s*2|roadmap|route-discrimination|sibling rollout|hard-gate|schema companion)\b",
    re.IGNORECASE,
)
ROADMAP_NEXT_WORK_SIGNAL_RE = re.compile(
    r"\b(?:A1|H1|V3|next bounded slice|route discrimination|sibling adoption|hard gates?)\b",
    re.IGNORECASE,
)
PARENT_RETURN_SIGNAL_RE = re.compile(
    r"\b(?:return|returns|returned|resume|resumes|sync|choose|decide)\b(?:\W+\w+){0,8}?\W+\bparent\b|"
    r"\bparent\b(?:\W+\w+){0,8}?\W+\b(?:return|returns|resume|resumes|sync|choose|decide|receives?)\b",
    re.IGNORECASE,
)
NEXT_BOUNDED_SLICE_LINE_RE = re.compile(r"^\s*-\s*Next bounded slice:\s*(?P<body>.+?)\s*$", re.IGNORECASE)
UMBRELLA_ROADMAP_DISPOSITION_RE = re.compile(
    r"\b(?:successor activation (?:plan )?(?:materialized|linked)|"
    r"next activation carrier|parked/reference (?:state|keep)|"
    r"superseded by|no successor\s*\(why=|all tracks (?:terminal|cancelled|canceled|handled|exhausted)|"
    r"fully exhausted|cancelled/handled)\b",
    re.IGNORECASE,
)
UMBRELLA_ROADMAP_ROW_CARRIER_RE = re.compile(
    r"\b(?:successor activation (?:plan )?(?:materialized|linked)|next activation carrier|superseded by)\b",
    re.IGNORECASE,
)
UMBRELLA_ROADMAP_GLOBAL_DISPOSITION_RE = re.compile(
    r"\b(?:parked/reference (?:state|keep)|no successor\s*\(why=|"
    r"all tracks (?:terminal|cancelled|canceled|handled|exhausted)|fully exhausted|cancelled/handled)\b",
    re.IGNORECASE,
)
FOLLOWUP_ADDRESS_STOPWORDS = {
    "after",
    "before",
    "current",
    "queue",
    "slice",
    "plan",
    "track",
    "tracks",
    "roadmap",
    "remaining",
    "promote",
    "materialize",
    "materialized",
    "linked",
}
FOLLOWUP_HANDLED_RE = re.compile(
    r"\b(?:cancelled|canceled|handled|already tracked|already-tracked|terminal|done|superseded|"
    r"rejected|closed|canon sync closed|no successor)\b",
    re.IGNORECASE,
)
FOLLOWUP_NEGATED_HANDLED_RE = re.compile(
    r"\b(?:not|never|without|cannot|can't|cant|isn't|isnt|aren't|arent)\s+(?:\w+\s+){0,3}?"
    r"(?:cancelled|canceled|handled|tracked|terminal|done|superseded|rejected|closed)\b|"
    r"\b(?:unhandled|uncancelled|uncanceled|unclosed)\b",
    re.IGNORECASE,
)
FOLLOWUP_PENDING_HANDLED_RE = re.compile(
    r"\b(?:needs?|needed|should|must|will|shall)\s+(?:\w+\s+){0,6}?"
    r"(?:cancelled|canceled|handled|tracked|terminal|done|superseded|rejected|closed)\b|"
    r"\bto\s+be\s+(?:cancelled|canceled|handled|tracked|terminal|done|superseded|rejected|closed)\b",
    re.IGNORECASE,
)
FOLLOWUP_DISPOSITION_KEYS = {
    "disposition",
    "status",
    "state",
    "resolution",
    "outcome",
    "decision",
}
FOLLOWUP_DISPOSITION_EVIDENCE_KEYS = {
    "reason",
    "source_ref",
    "ref",
    "refs",
    "owner_ref",
    "decision_ref",
    "evidence",
}
FOLLOWUP_DISPOSITION_EVIDENCE_RE = re.compile(
    r"\b(?:why=|because|after|by|owner|canon|review|source|ref|docs/|no successor)\b",
    re.IGNORECASE,
)
CONCRETE_PLAN_PATH_RE = re.compile(r"\bdocs/plans/[A-Za-z0-9][A-Za-z0-9_./-]*\.md\b")
TEMP_REVIEWER_FLOW_PATH_RE = re.compile(r"\.tmp/[A-Za-z0-9_./-]*_flow\.js")
SCOPE_ROUTE_CLASSIFICATION_TOKENS = (
    "same-contract reroute",
    "real scope expansion",
    "de-scoped follow-up",
)
SCOPE_ROUTE_CLASSIFICATION_WINDOW = 4
SCOPE_ROUTE_AMBIGUOUS_RE = re.compile(
    r"\b(scope split|scope expansion|broad cleanup|follow-up later|followup later|separate issue|"
    r"out-of-bundle|outside exact bundle|widen(?:ing)? (?:the )?exact bundle|"
    r"разду(?:ть|вает|вать).{0,40}bundle|внебандлов(?:ый|ого|ые))\b",
    re.IGNORECASE,
)
SHARED_HELPER_DEPENDENT_INVENTORY: dict[str, tuple[str, ...]] = {
    "scripts/planveyor/role_runtime.zsh": (
        "scripts/test_planveyor_init_capture.py",
        "scripts/test_planveyor_trace_extractor.py",
        "scripts/test_planveyor_bare_entrypoints.py",
        "scripts/test_planveyor_router_merge_boundary.py",
    ),
}
SHARED_HELPER_DEPENDENT_INVENTORY_PLACEHOLDER_RE = re.compile(
    r"\b(?:audit|check|verify|review|inspect|confirm)\s+(?:dependents?|consumers?|fanout|fan-out)\s+later\b|"
    r"\b(?:dependents?|consumers?|fanout|fan-out)\s+(?:tbd|todo|later|unknown|n/?a)\b|"
    r"\b(?:audit later|check later)\b",
    re.IGNORECASE,
)
SHARED_HELPER_DEPENDENT_INVENTORY_LABEL = "dependent tests / dependent docs / known consumer paths"
SHARED_HELPER_REVIEWABILITY_FIELD_RE = re.compile(r"^\s*-\s+`[^`]+`:")
BLOCKER_ATTRIBUTION_REQUIRED_SNIPPETS: dict[str, tuple[str, ...]] = {
    "docs/plans/README.md": (
        "<review_artifact_path>#B<N>",
        "same-contract reroute",
        "real scope expansion",
        "de-scoped follow-up",
    ),
    "docs/code_reviews/_template_merge_range.md": (
        "Blocker ID:",
        "Current state:",
        "Classification:",
        "Primary owner gap:",
        "Evidence refs:",
    ),
    "docs/code_reviews/_template_single_commit.md": (
        "Blocker ID:",
        "Current state:",
        "Classification:",
        "Primary owner gap:",
        "Evidence refs:",
    ),
    "docs/doc_reviews/_template_merge_range.md": (
        "Blocker ID:",
        "Current state:",
        "Classification:",
        "Primary owner gap:",
        "Evidence refs:",
    ),
    "docs/doc_reviews/_template_single_commit.md": (
        "Blocker ID:",
        "Current state:",
        "Classification:",
        "Primary owner gap:",
        "Evidence refs:",
    ),
    "docs/tools/prompts/reviewer_status_driven.md": (
        "<review_artifact_path>#B<N>",
        "Blocker ID",
        "Current state",
        "Classification",
        "Primary owner gap",
        "Evidence refs",
    ),
    "docs/playbooks/post_merge_plan_harvest.md": (
        "<review_artifact_path>#B<N>",
        "Current state",
        "Classification",
        "Primary owner gap",
        "Evidence refs",
    ),
    "docs/playbooks/post_merge_audit.md": (
        "<review_artifact_path>#B<N>",
        "Blocker refs",
    ),
    "docs/tools/prompts/architect_post_merge_audit.md": (
        "<review_artifact_path>#B<N>",
        "blocker refs",
    ),
    "docs/reviews/_template_post_merge_audit.md": (
        "Blocker refs:",
        "<review_artifact_path>#B1",
    ),
}


@dataclass(frozen=True)
class Finding:
    file: Path
    line: int
    severity: str  # "ERROR" | "WARN"
    message: str


@dataclass(frozen=True)
class StateTransitionDeclarations:
    heading_line: int
    label_lines: dict[str, int]
    normalized_fields: tuple[tuple[str, tuple[tuple[str, str | tuple[str, ...]], ...]], ...]


@dataclass(frozen=True)
class StateTransitionDeclarationsParseResult:
    heading_lines: tuple[int, ...]
    declaration: StateTransitionDeclarations | None
    findings: tuple[Finding, ...]


@dataclass(frozen=True)
class PlanRiskLaneCandidate:
    """One parseable plan-resident ``reviewer_code_risk`` compact receipt.

    This type used to live in :mod:`review_artifact_lint`.  It is defined here
    so the selector and the semantic-observation producer share one authority
    without creating an import cycle.
    """

    snapshot: str
    line_no: int
    payload: dict[str, Any]
    run_id: str | None
    written_at_key: str | None
    run_id_key: str | None
    explicit_current: bool
    explicit_non_current: bool


@dataclass(frozen=True)
class PlanRiskLaneSelection:
    """Compatibility result for current plan-resident risk-lane selection."""

    snapshot: str | None
    line_no: int
    payload: dict[str, Any] | None
    error_code: str | None
    message: str | None
    run_id: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class RiskLaneSupportDiagnostic:
    """One generic selected-support preflight diagnostic.

    This deliberately does not depend on the review-artifact linter's local
    ``Finding`` type so both the selector CLI and final lint can project the
    same validation result without an import cycle.
    """

    code: str
    message: str


@dataclass(frozen=True)
class PlanRiskLaneSupportManifest:
    """Read-only all-history risk-support membership for one origin plan.

    ``records`` deliberately carries only the declared path/hash pair.  It is
    consumed by the exact-bundle helper as byte-durability membership, while
    selected-current semantic/parity validation remains in
    :func:`preflight_selected_risk_lane_support`.
    """

    records: tuple[tuple[str, str], ...]
    diagnostics: tuple[RiskLaneSupportDiagnostic, ...]


@dataclass(frozen=True)
class CurrentReviewProofPreflight:
    """One read-only verdict for a live ``BUNDLE=current`` review proof.

    This is deliberately a process-local result rather than another durable
    receipt schema.  Consumers use it to decide whether a *current* review
    proof is authoritative; historical and non-current review carriers remain
    readable through their existing compatibility paths.
    """

    state: str  # "planned" | "not_current" | "current_green" | "blocked"
    reason_code: str | None
    message: str
    plan_path: str
    review_path: str | None
    target: str | None
    diagnostics: tuple[RiskLaneSupportDiagnostic, ...] = ()

    @property
    def current_green(self) -> bool:
        return self.state == "current_green"

    def as_dict(self) -> dict[str, object]:
        return {
            "state": self.state,
            "reason_code": self.reason_code,
            "message": self.message,
            "plan_path": self.plan_path,
            "review_path": self.review_path,
            "target": self.target,
            "diagnostics": [
                {"code": diagnostic.code, "message": diagnostic.message}
                for diagnostic in self.diagnostics
            ],
        }


@dataclass(frozen=True)
class SemanticObservationDiagnostic:
    """One deterministic semantic-observation validation diagnostic."""

    stage: str
    code: str
    path: str | None
    line: int | None
    message: str

    def report_value(self) -> dict[str, object]:
        return {
            "code": self.code,
            "path": self.path,
            "line": self.line,
            "message": self.message,
        }


@dataclass(frozen=True)
class SemanticJsonCarrier:
    """A JSON fence in ``## Evidence`` participating in the V1 protocol."""

    line_no: int
    end_line_no: int
    payload: dict[str, Any] | None
    raw: str
    kind: str | None


@dataclass(frozen=True)
class SemanticCheckpointDiagnostic:
    """One deterministic semantic-cycle checkpoint validation diagnostic."""

    code: str
    path: str | None
    line: int | None
    message: str

    def report_value(self) -> dict[str, object]:
        return {
            "code": self.code,
            "path": self.path,
            "line": self.line,
            "message": self.message,
        }


@dataclass(frozen=True)
class SemanticCheckpointJsonCarrier:
    """One checkpoint resolution JSON fence in ``PLAN_PATH::## Evidence``."""

    line_no: int
    end_line_no: int
    payload: dict[str, Any] | None
    raw: str
    kind: str


class ManifestError(RuntimeError):
    """Raised when a required control-plane manifest is missing or malformed."""


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def require_manifest_string_list(raw: object, *, label: str, lower_case: bool = False) -> list[str]:
    if not isinstance(raw, list) or any(not isinstance(item, str) or not item.strip() for item in raw):
        raise ManifestError(f"{label} must be a JSON array of non-empty strings.")

    values = [item.strip().lower() if lower_case else item.strip() for item in raw]
    if len(set(values)) != len(values):
        raise ManifestError(f"{label} must not contain duplicates.")
    return values


def require_manifest_string_map(raw: object, *, label: str) -> dict[str, str]:
    if not isinstance(raw, dict):
        raise ManifestError(f"{label} must be a JSON object of strings.")

    result: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not key.strip() or not isinstance(value, str) or not value.strip():
            raise ManifestError(f"{label} must contain only non-empty string keys and values.")
        key_norm = key.strip().lower()
        value_norm = value.strip().lower()
        if key_norm in result and result[key_norm] != value_norm:
            raise ManifestError(f"{label} contains conflicting alias mapping for {key_norm!r}.")
        result[key_norm] = value_norm
    return result


def require_manifest_object(raw: object, *, label: str) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise ManifestError(f"{label} must be a JSON object.")
    return raw


def validate_manifest_exact_string_set(
    raw: object,
    *,
    label: str,
    expected: Sequence[str],
) -> tuple[str, ...]:
    values = require_manifest_string_list(raw, label=label, lower_case=True)
    expected_set = set(expected)
    missing = sorted(expected_set - set(values))
    extra = sorted(set(values) - expected_set)
    if missing or extra:
        details = []
        if missing:
            details.append(f"missing: {', '.join(missing)}")
        if extra:
            details.append(f"unknown: {', '.join(extra)}")
        raise ManifestError(f"{label} must match the E2 planning-contour enum ({'; '.join(details)}).")
    return tuple(values)


def validate_blocking_dependency_carrier_manifest(raw: object, *, label: str) -> dict[str, str]:
    carrier = require_manifest_object(raw, label=label)
    expected = DEFAULT_BLOCKING_DEPENDENCY_CARRIER
    missing = sorted(set(expected) - set(carrier))
    extra = sorted(set(carrier) - set(expected))
    if missing or extra:
        details: list[str] = []
        if missing:
            details.append(f"missing: {', '.join(missing)}")
        if extra:
            details.append(f"unknown: {', '.join(extra)}")
        raise ManifestError(f"{label} must contain exactly the V1 keys ({'; '.join(details)}).")

    result: dict[str, str] = {}
    for key, expected_value in expected.items():
        value = carrier.get(key)
        if value != expected_value:
            raise ManifestError(
                f"{label}.{key} must equal {expected_value!r} for the V1 blocking dependency carrier."
            )
        result[key] = expected_value
    return result


def validate_planning_contour_manifest(raw: object, *, label: str) -> dict[str, object]:
    planning_contour = require_manifest_object(raw, label=label)
    missing_keys = sorted(PLANNING_CONTOUR_REQUIRED_KEYS - set(planning_contour))
    if missing_keys:
        raise ManifestError(f"{label} is missing required key(s): {', '.join(missing_keys)}.")

    wave_markers = require_manifest_object(planning_contour.get("wave_markers"), label=f"{label}.wave_markers")
    for route_name in ("analysis_wave", "decomposition_wave"):
        marker = require_manifest_object(
            wave_markers.get(route_name),
            label=f"{label}.wave_markers.{route_name}",
        )
        field = marker.get("field")
        if not isinstance(field, str) or not field.strip():
            raise ManifestError(f"{label}.wave_markers.{route_name}.field must be a non-empty string.")
        required_value = marker.get("required_value")
        if not isinstance(required_value, str) or not required_value.strip():
            raise ManifestError(f"{label}.wave_markers.{route_name}.required_value must be a non-empty string.")

    validate_manifest_exact_string_set(
        planning_contour.get("accepted_routes"),
        label=f"{label}.accepted_routes",
        expected=PLANNING_CONTOUR_ACCEPTED_ROUTES,
    )
    validate_manifest_exact_string_set(
        planning_contour.get("requirement_slice_kinds"),
        label=f"{label}.requirement_slice_kinds",
        expected=PLANNING_CONTOUR_REQUIREMENT_SLICE_KIND_VALUES,
    )
    validate_manifest_exact_string_set(
        planning_contour.get("promoted_artifact_kinds"),
        label=f"{label}.promoted_artifact_kinds",
        expected=PLANNING_CONTOUR_PROMOTED_ARTIFACT_KINDS,
    )
    validate_manifest_exact_string_set(
        planning_contour.get("queue_admission"),
        label=f"{label}.queue_admission",
        expected=PLANNING_CONTOUR_QUEUE_ADMISSION,
    )
    validate_manifest_exact_string_set(
        planning_contour.get("runner_admission"),
        label=f"{label}.runner_admission",
        expected=PLANNING_CONTOUR_RUNNER_ADMISSION,
    )
    validate_manifest_exact_string_set(
        planning_contour.get("queue_activation_states"),
        label=f"{label}.queue_activation_states",
        expected=PLANNING_CONTOUR_QUEUE_ACTIVATION_STATES,
    )
    validate_manifest_exact_string_set(
        planning_contour.get("scope_expansion_states"),
        label=f"{label}.scope_expansion_states",
        expected=PLANNING_CONTOUR_SCOPE_EXPANSION_STATES,
    )

    transition_matrix = planning_contour.get("status_transition_matrix")
    if not isinstance(transition_matrix, list) or not transition_matrix:
        raise ManifestError(f"{label}.status_transition_matrix must be a non-empty JSON array.")
    required_transition_keys = {
        "from_marker",
        "accepted_route",
        "target_marker",
        "initial_status",
        "required_carriers",
        "queue_activation_required",
        "hard_gate_state",
    }
    for idx, entry in enumerate(transition_matrix):
        entry_label = f"{label}.status_transition_matrix[{idx}]"
        entry_obj = require_manifest_object(entry, label=entry_label)
        missing = sorted(required_transition_keys - set(entry_obj))
        if missing:
            raise ManifestError(f"{entry_label} is missing required key(s): {', '.join(missing)}.")
        accepted_route = entry_obj.get("accepted_route")
        if accepted_route not in PLANNING_CONTOUR_ACCEPTED_ROUTES:
            raise ManifestError(f"{entry_label}.accepted_route must use the planning-contour accepted route enum.")
        carriers = entry_obj.get("required_carriers")
        if not isinstance(carriers, list) or any(not isinstance(item, str) or not item.strip() for item in carriers):
            raise ManifestError(f"{entry_label}.required_carriers must be a JSON array of non-empty strings.")
        if not isinstance(entry_obj.get("queue_activation_required"), bool):
            raise ManifestError(f"{entry_label}.queue_activation_required must be a boolean.")
        hard_gate_state = entry_obj.get("hard_gate_state")
        if hard_gate_state not in {"warning", "error", "none"}:
            raise ManifestError(f"{entry_label}.hard_gate_state must be one of: warning, error, none.")

    return planning_contour


def load_plan_vocab(path: Path, *, raw_text: str | None = None) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8") if raw_text is None else raw_text)
    except FileNotFoundError as exc:
        raise ManifestError(f"Missing required plan vocabulary manifest: {rel(path)}.") from exc
    except json.JSONDecodeError as exc:
        raise ManifestError(f"Invalid JSON in {rel(path)}:{exc.lineno}:{exc.colno}: {exc.msg}.") from exc

    if not isinstance(raw, dict):
        raise ManifestError(f"{rel(path)} must contain a top-level JSON object.")

    plan_statuses = raw.get("plan_statuses")
    if not isinstance(plan_statuses, dict):
        raise ManifestError(f"{rel(path)}: `plan_statuses` must be a JSON object.")

    status_groups = plan_statuses.get("groups")
    if not isinstance(status_groups, dict):
        raise ManifestError(f"{rel(path)}: `plan_statuses.groups` must be a JSON object.")

    clusters = raw.get("clusters")
    if not isinstance(clusters, dict):
        raise ManifestError(f"{rel(path)}: `clusters` must be a JSON object.")

    phase_overlays = raw.get("phase_overlays")
    if phase_overlays is None:
        phase_overlays = {}
    if not isinstance(phase_overlays, dict):
        raise ManifestError(f"{rel(path)}: `phase_overlays` must be a JSON object.")

    manager_modes = raw.get("manager_modes")
    if not isinstance(manager_modes, dict):
        raise ManifestError(f"{rel(path)}: `manager_modes` must be a JSON object.")
    required_manager_modes = require_manifest_string_list(
        manager_modes.get("canonical_required"),
        label=f"{rel(path)} -> manager_modes.canonical_required",
        lower_case=True,
    )
    if set(required_manager_modes) != {"manager-collab", "manager-custom-pipeline", "either"}:
        raise ManifestError(
            f"{rel(path)} -> manager_modes.canonical_required must contain exactly "
            "manager-collab, manager-custom-pipeline, either."
        )
    actual_manager_modes = require_manifest_string_list(
        manager_modes.get("canonical_actual"),
        label=f"{rel(path)} -> manager_modes.canonical_actual",
        lower_case=True,
    )
    if set(actual_manager_modes) != {"manager-collab", "manager-custom-pipeline"}:
        raise ManifestError(
            f"{rel(path)} -> manager_modes.canonical_actual must contain exactly "
            "manager-collab, manager-custom-pipeline."
        )
    blocking_dependency_carrier = validate_blocking_dependency_carrier_manifest(
        raw.get("blocking_dependency_carrier"),
        label=f"{rel(path)} -> blocking_dependency_carrier",
    )

    planning_contour_raw = raw.get("planning_contour")
    planning_contour = (
        validate_planning_contour_manifest(
            planning_contour_raw,
            label=f"{rel(path)} -> planning_contour",
        )
        if planning_contour_raw is not None
        else None
    )

    canonical_statuses = require_manifest_string_list(
        plan_statuses.get("canonical"),
        label=f"{rel(path)} -> plan_statuses.canonical",
    )
    canonical_status_norms = {value.lower() for value in canonical_statuses}

    code_draft_required = require_manifest_string_list(
        status_groups.get("code_draft_required"),
        label=f"{rel(path)} -> plan_statuses.groups.code_draft_required",
        lower_case=True,
    )
    for label, values in (
        ("code_draft_required", code_draft_required),
    ):
        unknown = sorted(set(values) - canonical_status_norms)
        if unknown:
            rendered = ", ".join(unknown)
            raise ManifestError(
                f"{rel(path)} -> plan_statuses.groups.{label} references unknown canonical statuses: {rendered}."
            )

    canonical_clusters = require_manifest_string_list(
        clusters.get("canonical"),
        label=f"{rel(path)} -> clusters.canonical",
        lower_case=True,
    )
    deprecated_cluster_aliases = require_manifest_string_map(
        clusters.get("deprecated_aliases"),
        label=f"{rel(path)} -> clusters.deprecated_aliases",
    )
    canonical_phase_overlays = require_manifest_string_list(
        phase_overlays.get("canonical", []),
        label=f"{rel(path)} -> phase_overlays.canonical",
        lower_case=True,
    )
    raw_phase_overlay_states = phase_overlays.get("states", {})
    if not isinstance(raw_phase_overlay_states, dict):
        raise ManifestError(f"{rel(path)} -> phase_overlays.states must be a JSON object.")
    phase_overlay_states: dict[str, frozenset[str]] = {}
    for overlay_name, states_raw in raw_phase_overlay_states.items():
        if not isinstance(overlay_name, str) or not overlay_name.strip():
            raise ManifestError(f"{rel(path)} -> phase_overlays.states keys must be non-empty strings.")
        overlay_key = overlay_name.strip().lower()
        states = require_manifest_string_list(
            states_raw,
            label=f"{rel(path)} -> phase_overlays.states.{overlay_key}",
            lower_case=True,
        )
        phase_overlay_states[overlay_key] = frozenset(states)

    unknown_phase_overlay_states = sorted(set(phase_overlay_states) - set(canonical_phase_overlays))
    if unknown_phase_overlay_states:
        rendered = ", ".join(unknown_phase_overlay_states)
        raise ManifestError(
            f"{rel(path)} -> phase_overlays.states references unknown canonical overlay(s): {rendered}."
        )

    unknown_cluster_targets = sorted(set(deprecated_cluster_aliases.values()) - set(canonical_clusters))
    if unknown_cluster_targets:
        rendered = ", ".join(unknown_cluster_targets)
        raise ManifestError(
            f"{rel(path)} -> clusters.deprecated_aliases points to unknown canonical cluster(s): {rendered}."
        )

    return {
        "canonical_statuses": tuple(canonical_statuses),
        "code_draft_required": frozenset(code_draft_required),
        "canonical_clusters": frozenset(canonical_clusters),
        "deprecated_cluster_aliases": deprecated_cluster_aliases,
        "canonical_phase_overlays": frozenset(canonical_phase_overlays),
        "phase_overlay_states": phase_overlay_states,
        "required_manager_modes": frozenset(required_manager_modes),
        "blocking_dependency_carrier": blocking_dependency_carrier,
        "planning_contour": planning_contour,
        "planning_contour_requirement_slice_kinds": frozenset(
            require_manifest_string_list(
                planning_contour.get("requirement_slice_kinds"),
                label=f"{rel(path)} -> planning_contour.requirement_slice_kinds",
                lower_case=True,
            )
        )
        if planning_contour
        else frozenset(PLANNING_CONTOUR_REQUIREMENT_SLICE_KIND_VALUES),
    }


def apply_plan_vocab(config: dict[str, object]) -> None:
    global ALLOWED_CLUSTERS
    global DEPRECATED_CLUSTER_ALIASES
    global CANONICAL_PLAN_STATUSES
    global CODE_DRAFT_REQUIRED_STATUS_NORMS
    global ALLOWED_PHASE_OVERLAYS
    global PHASE_OVERLAY_STATES
    global PLANNING_CONTOUR_REQUIREMENT_SLICE_KINDS
    global ALLOWED_REQUIRED_MANAGER_MODES
    global BLOCKING_DEPENDENCY_CARRIER_FIELD
    global BLOCKING_DEPENDENCY_CARRIER_SHAPE
    global BLOCKING_DEPENDENCY_CARRIER_SUBSET_FIELD
    global BLOCKING_DEPENDENCY_CARRIER_CLEARANCE_FIELD

    ALLOWED_CLUSTERS = config["canonical_clusters"]  # type: ignore[assignment]
    DEPRECATED_CLUSTER_ALIASES = config["deprecated_cluster_aliases"]  # type: ignore[assignment]
    CANONICAL_PLAN_STATUSES = config["canonical_statuses"]  # type: ignore[assignment]
    CODE_DRAFT_REQUIRED_STATUS_NORMS = config["code_draft_required"]  # type: ignore[assignment]
    ALLOWED_PHASE_OVERLAYS = config["canonical_phase_overlays"]  # type: ignore[assignment]
    PHASE_OVERLAY_STATES = config["phase_overlay_states"]  # type: ignore[assignment]
    ALLOWED_REQUIRED_MANAGER_MODES = config["required_manager_modes"]  # type: ignore[assignment]
    blocking_dependency_carrier = config["blocking_dependency_carrier"]
    assert isinstance(blocking_dependency_carrier, Mapping)
    BLOCKING_DEPENDENCY_CARRIER_FIELD = str(blocking_dependency_carrier["field"])
    BLOCKING_DEPENDENCY_CARRIER_SHAPE = str(blocking_dependency_carrier["shape"])
    BLOCKING_DEPENDENCY_CARRIER_SUBSET_FIELD = str(blocking_dependency_carrier["subset_of"])
    BLOCKING_DEPENDENCY_CARRIER_CLEARANCE_FIELD = str(blocking_dependency_carrier["clearance"])
    PLANNING_CONTOUR_REQUIREMENT_SLICE_KINDS = config["planning_contour_requirement_slice_kinds"]  # type: ignore[assignment]


def load_and_apply_plan_vocab(path: Path) -> None:
    apply_plan_vocab(load_plan_vocab(path))


def _actual_repo_root_for_plan_path(plan_path: Path) -> Path:
    """Resolve the plan's physical project root without caller environment overrides."""

    abs_path = plan_path.resolve()
    start_dir = abs_path.parent if abs_path.is_file() else abs_path
    for parent in [start_dir] + list(start_dir.parents):
        if (parent / ".git").exists():
            return parent
    return start_dir


def repo_root_for_plan_path(plan_path: Path, *, context: ContractContext | None = None) -> Path:
    """Best-effort repo root resolution for a plan file path.

    Motivation: this script lives in `planveyor`, but it lints plans and code drafts that live in
    different git worktrees/repos. For checks like `docs/code_drafts/...` we must resolve paths
    relative to the repo that contains the plan (not relative to tooling root).
    """

    if context is None:
        context = _ACTIVE_PLAN_LINT_CONTEXT.get()

    abs_path = plan_path.resolve()
    start_dir = abs_path.parent if abs_path.is_file() else abs_path

    if context is not None:
        root = context.project_root.resolve()
        try:
            abs_path.relative_to(root)
        except ValueError as exc:
            raise ValueError(
                f"Plan path is outside the {context.state} contract project root: {abs_path}"
            ) from exc
        if context is not _ACTIVE_PLAN_LINT_CONTEXT.get():
            # The identical active context was already validated at scope entry.
            context_for_reader(root, context=context)
        for parent in (start_dir, *start_dir.parents):
            if parent == root:
                break
            if os.path.lexists(parent / ".git"):
                # An outer context cannot admit a plan from a nested Git root.
                context_for_reader(parent, context=context)
        # A captured context fixes the reader root in both modes. In particular,
        # a non-Git legacy plan must not move from its captured project root to
        # docs/plans in a nested reader. The environment is only a convenience
        # for callers which have not yet captured a context.
        return root

    env_root = os.environ.get("PLANVEYOR_PROJECT_ROOT")
    if env_root:
        try:
            env_root_path = Path(env_root).resolve()
            abs_path.relative_to(env_root_path)
            return env_root_path
        except Exception:
            pass

    for parent in [start_dir] + list(start_dir.parents):
        if (parent / ".git").exists():
            return parent

    return start_dir


_PLAN_LINT_SCOPED_GLOBAL_NAMES = (
    "REPO_ROOT",
    "PLANS_ROOT",
    "DOCS_META_ROOT",
    "PLAN_VOCAB_PATH",
    "DEFAULT_EXCLUDES",
    "ALLOWED_CLUSTERS",
    "DEPRECATED_CLUSTER_ALIASES",
    "CANONICAL_PLAN_STATUSES",
    "CODE_DRAFT_REQUIRED_STATUS_NORMS",
    "ALLOWED_PHASE_OVERLAYS",
    "PHASE_OVERLAY_STATES",
    "PLANNING_CONTOUR_REQUIREMENT_SLICE_KINDS",
    "ALLOWED_REQUIRED_MANAGER_MODES",
    "BLOCKING_DEPENDENCY_CARRIER_FIELD",
    "BLOCKING_DEPENDENCY_CARRIER_SHAPE",
    "BLOCKING_DEPENDENCY_CARRIER_SUBSET_FIELD",
    "BLOCKING_DEPENDENCY_CARRIER_CLEARANCE_FIELD",
)

# The legacy validator graph has many pure helpers which predate an explicit
# context parameter.  This is a dynamic call-scope guard, not a root cache: a
# public entry still resolves and passes one context, and nested helpers only
# consult it to avoid re-resolving or honoring PLANVEYOR_PROJECT_ROOT mid-call.
_ACTIVE_PLAN_LINT_CONTEXT: contextvars.ContextVar[ContractContext | None] = contextvars.ContextVar(
    "plan_lint_active_contract_context",
    default=None,
)


@contextmanager
def _scoped_plan_lint_context(
    project_root: Path,
    *,
    context: ContractContext | None = None,
    require_vocab: bool,
) -> Iterator[ContractContext]:
    """Apply one target's mutable vocabulary only for the current call.

    ``plan_lint`` predates the authority boundary and exposes many pure helpers
    that read module globals.  Scoping and restoring those values keeps a
    process which lints project A then project B from retaining A's vocabulary.
    Older fixture callers with no local vocabulary retain their established
    vocabulary values, while path-derived globals still follow the explicit
    plan root for the duration of the call.
    """

    resolved_context = context_for_reader(project_root, context=context)
    root = resolved_context.project_root.resolve()
    caller_vocab_path = PLAN_VOCAB_PATH
    # Preserve the established test/tool API that can supply an explicit
    # vocabulary path for a one-shot CLI invocation.  It is never honored in
    # engaged mode, where the exact declared target row is the only source.
    vocab_path = (
        # ``main`` historically loaded the current module vocabulary before
        # traversing its plan arguments.  Keep that exact legacy override,
        # including a caller's patched path, while engaged callers are bound
        # exclusively to their declared target row.
        caller_vocab_path
        if require_vocab and resolved_context.state != "engaged"
        else (
            resolved_context.contract_root / "docs" / "_meta" / "plan_vocab.json"
            if resolved_context.state == "engaged"
            else root / "docs" / "_meta" / "plan_vocab.json"
        )
    )
    needs_vocab = resolved_context.state == "engaged" or require_vocab or vocab_path.is_file()
    context_token = _ACTIVE_PLAN_LINT_CONTEXT.set(resolved_context)
    originals = {name: globals()[name] for name in _PLAN_LINT_SCOPED_GLOBAL_NAMES}
    try:
        globals().update(
            {
                "REPO_ROOT": root,
                "PLANS_ROOT": root / "docs" / "plans",
                "DOCS_META_ROOT": root / "docs" / "_meta",
                "PLAN_VOCAB_PATH": vocab_path,
                "DEFAULT_EXCLUDES": {
                    root / "docs" / "plans" / "README.md",
                    root / "docs" / "plans" / "_template.md",
                },
            }
        )
        if resolved_context.state == "engaged":
            config = load_plan_vocab(
                vocab_path,
                raw_text=read_declared_text(
                    resolved_context,
                    "docs/_meta/plan_vocab.json",
                    purpose="plan vocabulary",
                ),
            )
        elif needs_vocab:
            config = load_plan_vocab(vocab_path)
        else:
            config = None
        if config is not None:
            apply_plan_vocab(config)
        yield resolved_context
    finally:
        for name, value in originals.items():
            globals()[name] = value
        _ACTIVE_PLAN_LINT_CONTEXT.reset(context_token)


def repo_relative_display(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path.resolve())


def repo_root_for_fs_path(path: Path) -> Path | None:
    abs_path = path.resolve()
    anchor = abs_path if abs_path.exists() else abs_path.parent
    while not anchor.exists() and anchor != anchor.parent:
        anchor = anchor.parent
    cwd = anchor if anchor.is_dir() else anchor.parent
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    value = result.stdout.strip()
    return Path(value).resolve() if value else None


def git_head_contains_path(repo_root: Path, rel_path: str) -> bool:
    return git_ref_contains_path(repo_root, "HEAD", rel_path)


def git_ref_contains_path(repo_root: Path, ref: str, rel_path: str) -> bool:
    ref_value = str(ref or "").strip()
    if not ref_value:
        return False
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "cat-file", "-e", f"{ref_value}:{rel_path}"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return False
    return result.returncode == 0


def iter_plan_files(paths: Sequence[Path]) -> list[Path]:
    resolved: set[Path] = set()
    for path in paths:
        candidate = path.resolve()
        if candidate.is_dir():
            for plan in candidate.rglob("*.md"):
                if plan.resolve() in DEFAULT_EXCLUDES:
                    continue
                resolved.add(plan.resolve())
        else:
            if candidate in DEFAULT_EXCLUDES:
                continue
            resolved.add(candidate)
    return sorted(resolved)


def read_text(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def extract_status_lines(lines: list[str]) -> list[tuple[int, str]]:
    status_lines: list[tuple[int, str]] = []
    for idx, line in enumerate(lines, start=1):
        match = STATUS_LINE_RE.match(line)
        if not match:
            continue
        status_lines.append((idx, match.group("status").strip()))
    return status_lines


def extract_schema_version_lines(lines: list[str]) -> list[tuple[int, str]]:
    schema_lines: list[tuple[int, str]] = []
    for idx, line in enumerate(lines, start=1):
        match = SCHEMA_VERSION_LINE_RE.match(line)
        if not match:
            continue
        schema_lines.append((idx, match.group("value").strip()))
    return schema_lines


def normalize_schema_version(value: str) -> str:
    return " ".join(value.replace("`", "").split()).lower()


def extract_plan_type(lines: list[str]) -> str | None:
    for line in lines:
        match = PLAN_TYPE_RE.match(line)
        if not match:
            continue
        value = match.group("plan_type").strip()
        if not value:
            return None
        # Normalize "dev (dev | review-only)" style (template).
        value = value.split("(")[0].strip()
        return value.lower()
    return None


def has_raw_literal_dev_plan_type(lines: list[str]) -> bool:
    """Return whether the first raw plan-type header is exactly ``dev``."""

    for line in lines:
        match = PLAN_TYPE_RE.match(line)
        if match:
            return match.group("plan_type").strip() == "dev"
    return False


def extract_code_draft_refs(lines: list[str], *, include_annotated: bool = False) -> list[tuple[int, str]]:
    """Return list of (line_no, rel_path_str) for code draft links mentioned in the plan.

    By default paths are skipped when they are already correctly annotated as
    out-of-scope, so they do not produce spurious missing-file findings:
    - a ``docs/code_drafts/...`` path nested inside an explicit ``N/A (...)`` marker
      (superseded / sibling-repo / non-applicable) is not a local draft reference;
    - a ``docs/code_drafts/...`` path named inside a historical changelog/evidence
      line (carrying an inline timestamp) is immutable provenance, not a live ref.

    When ``include_annotated`` is True the N/A / historical filters are
    not applied, so callers that only need to know whether the plan is aware of the
    code-draft concept (e.g. the "plan must mention at least one code draft" gate) do
    not false-fire on plans whose only mention is a correctly annotated out-of-scope
    reference.
    """
    seen: dict[str, int] = {}
    for idx, line in enumerate(lines, start=1):
        if not include_annotated:
            if re.search(r"\bN/A\s*\(", line):
                # The line annotates the reference as non-applicable; do not treat the
                # embedded docs/code_drafts/... substring as a local draft reference.
                continue
            if INLINE_TIMESTAMP_RE.search(line):
                # Historical changelog/evidence lines (with an inline timestamp) are
                # immutable provenance; a docs/code_drafts/... path named inside such
                # a log is not a live local draft reference.
                continue
        for match in CODE_DRAFT_RE.findall(line):
            if match not in seen:
                seen[match] = idx
    return sorted(((line_no, path) for path, line_no in seen.items()), key=lambda x: x[0])


def _iter_inline_code_spans(text: str) -> list[tuple[int, int, str]]:
    """Return bounded inline code spans as ``(start, end, body)`` triples."""
    spans: list[tuple[int, int, str]] = []
    cursor = 0
    while cursor < len(text):
        start = text.find("`", cursor)
        if start < 0:
            break
        marker_end = start + 1
        while marker_end < len(text) and text[marker_end] == "`":
            marker_end += 1
        marker = text[start:marker_end]
        closing = text.find(marker, marker_end)
        if closing < 0:
            cursor = marker_end
            continue
        end = closing + len(marker)
        spans.append((start, end, text[marker_end:closing]))
        cursor = end
    return spans


def _extract_outside_code_span_review_path_tokens(text: str) -> list[str]:
    """Return outside-span review tokens, preserving adjacent anchor fragments."""
    tokens: list[str] = []
    for match in REVIEW_ARTIFACT_PATH_TOKEN_RE.finditer(text):
        raw_path = match.group()
        anchor_start = match.end()
        if anchor_start < len(text) and text[anchor_start] == "#":
            anchor_end = anchor_start + 1
            while (
                anchor_end < len(text)
                and not text[anchor_end].isspace()
                and text[anchor_end] not in {"`", "'", '"'}
            ):
                anchor_end += 1
            anchor_fragment = text[anchor_start:anchor_end]
            trimmed_anchor = anchor_fragment[1:].rstrip(REVIEW_ARTIFACT_OUTSIDE_ANCHOR_TRAILING_DELIMITERS)
            if (
                trimmed_anchor != anchor_fragment[1:]
                and REVIEW_ARTIFACT_ANCHOR_RE.fullmatch(trimmed_anchor)
            ):
                anchor_fragment = f"#{trimmed_anchor}"
            raw_path += anchor_fragment
        tokens.append(raw_path)
    return tokens


def extract_review_artifact_path_tokens(text: str) -> list[str]:
    """Return full review literal tokens before eligibility.

    Outside inline code spans, Markdown punctuation may delimit a path token,
    but an adjacent anchor fragment remains part of that token until its full
    literal reaches eligibility. Within a code span, capture the entire
    non-whitespace literal so malformed suffixes such as ``live.md:evil``
    cannot be truncated before eligibility.
    Canonical carriers use this raw presence to fail closed before the later
    eligible Markdown-ref cardinality check.
    """
    tokens: list[str] = []
    cursor = 0
    for start, end, body in _iter_inline_code_spans(text):
        tokens.extend(_extract_outside_code_span_review_path_tokens(text[cursor:start]))
        tokens.extend(REVIEW_ARTIFACT_CODE_SPAN_TOKEN_RE.findall(body))
        cursor = end
    tokens.extend(_extract_outside_code_span_review_path_tokens(text[cursor:]))
    return tokens


def is_review_artifact_path_eligible(raw_path: str, *, allow_legacy_root: bool = False) -> bool:
    """Return whether a literal path is an exact eligible review Markdown path."""
    path, separator, anchor = raw_path.strip().partition("#")
    if separator and not REVIEW_ARTIFACT_ANCHOR_RE.fullmatch(anchor):
        return False
    roots = LEGACY_REVIEW_ARTIFACT_ROOTS if allow_legacy_root else REVIEW_ARTIFACT_ROOTS
    if (
        not path
        or path.startswith(("/", "\\"))
        or "\\" in path
        or not path.endswith(".md")
        or not path.startswith(roots)
    ):
        return False
    parts = path.split("/")
    return not any(part in {"", ".", "..", "assets"} for part in parts)


def extract_review_artifact_refs(lines: list[str]) -> list[tuple[int, str]]:
    """Return list of (line_no, rel_path_str) for review artifact links mentioned in the plan."""
    seen: dict[str, int] = {}
    for idx, line in enumerate(lines, start=1):
        for raw_path in extract_review_artifact_path_tokens(line):
            path = raw_path.strip().partition("#")[0]
            if is_review_artifact_path_eligible(raw_path) and path not in seen:
                seen[path] = idx
    return sorted(((line_no, path) for path, line_no in seen.items()), key=lambda x: x[0])


def extract_live_review_artifact_refs(lines: list[str]) -> list[tuple[int, str]]:
    """Return literal live review-artifact refs from `## Review artifacts`.

    Only the canonical live carriers count here:
    `- Code review (primary): ...`
    `- Doc review (docs-only): ...`
    Historical/stale notes elsewhere in the plan must not become a second live route.
    """

    section = slice_h2_section(lines, REVIEW_ARTIFACTS_HEADING_RE)
    if not section:
        return []

    heading_line_no, body = section
    seen: dict[str, int] = {}
    for idx, line in enumerate(body):
        match = LIVE_REVIEW_ARTIFACT_LINE_RE.match(line)
        if not match:
            continue

        line_no = heading_line_no + idx + 1
        for raw_path in extract_review_artifact_path_tokens(match.group("body")):
            path = raw_path.strip().partition("#")[0]
            if is_review_artifact_path_eligible(raw_path) and path not in seen:
                seen[path] = line_no

    return sorted(((line_no, rel_path_str) for rel_path_str, line_no in seen.items()), key=lambda x: x[0])


def extract_live_review_artifact_raw_rows(lines: list[str]) -> list[tuple[int, tuple[str, ...]]]:
    """Return canonical live carrier rows with their raw review-path tokens."""
    section = slice_h2_section(lines, REVIEW_ARTIFACTS_HEADING_RE)
    if not section:
        return []

    heading_line_no, body = section
    rows: list[tuple[int, tuple[str, ...]]] = []
    for idx, line in enumerate(body):
        match = LIVE_REVIEW_ARTIFACT_LINE_RE.match(line)
        if not match:
            continue

        line_no = heading_line_no + idx + 1
        rows.append((line_no, tuple(extract_review_artifact_path_tokens(match.group("body")))))

    return rows


def extract_live_review_artifact_raw_refs(lines: list[str]) -> list[tuple[int, str]]:
    """Return literal raw review-path tokens from canonical live carrier rows.

    Unlike :func:`extract_live_review_artifact_refs`, this preserves malformed
    path tokens. Callers use it only to decide whether canonical presence blocks
    legacy fallback; it is not a usable-ref selector.
    """
    seen: dict[str, int] = {}
    for line_no, refs in extract_live_review_artifact_raw_rows(lines):
        for ref in refs:
            if ref not in seen:
                seen[ref] = line_no

    return sorted(((line_no, rel_path_str) for rel_path_str, line_no in seen.items()), key=lambda x: x[0])


def parse_inline_timestamp(raw_value: str) -> datetime | None:
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


def note_mentions_current_review_artifact(note_body: str, live_rel_path: str) -> bool:
    return live_rel_path in note_body or bool(SAME_REVIEW_FILE_RE.search(note_body))


def review_artifacts_section_has_stale_rerun_note(
    lines: list[str],
    *,
    live_rel_path: str,
    review_date_value: str | None,
) -> bool:
    section = slice_h2_section(lines, REVIEW_ARTIFACTS_HEADING_RE)
    if not section:
        return False

    _, body = section
    review_dt = parse_inline_timestamp(review_date_value or "")

    def has_current_cycle_note(note_re: re.Pattern[str]) -> bool:
        for line in body:
            match = note_re.match(line)
            if not match:
                continue
            if not note_mentions_current_review_artifact(match.group("body"), live_rel_path):
                continue

            note_dt = parse_inline_timestamp(match.group("meta"))
            if review_dt is None:
                return True
            if note_dt is not None and note_dt >= review_dt:
                return True
        return False

    return has_current_cycle_note(STALE_NOTE_LINE_RE) and has_current_cycle_note(RERUN_NOTE_LINE_RE)


def requires_code_draft(status_value: str | None) -> bool:
    if not status_value:
        return False
    s = status_value.strip().lower()
    return s in CODE_DRAFT_REQUIRED_STATUS_NORMS


def requires_shared_helper_dependent_inventory(status_value: str | None) -> bool:
    if requires_code_draft(status_value):
        return True
    if not status_value:
        return False
    s = status_value.strip().lower()
    return s in SHARED_HELPER_INVENTORY_TERMINAL_CURRENT_PROOF_STATUS_NORMS


def normalized_phase_overlay(plan_meta_obj: dict | None) -> str | None:
    if not isinstance(plan_meta_obj, dict):
        return None
    raw = plan_meta_obj.get("phase_overlay")
    if not isinstance(raw, str):
        return None
    value = raw.strip().lower()
    return value or None


def normalized_phase_state(plan_meta_obj: dict | None) -> str | None:
    if not isinstance(plan_meta_obj, dict):
        return None
    raw = plan_meta_obj.get("phase_state")
    if not isinstance(raw, str):
        return None
    value = raw.strip().lower()
    return value or None


def is_decomposition_wave(plan_meta_obj: dict | None) -> bool:
    return normalized_phase_overlay(plan_meta_obj) == "decomposition_wave"


def is_analysis_wave(plan_meta_obj: dict | None) -> bool:
    if not isinstance(plan_meta_obj, dict):
        return False
    return str(plan_meta_obj.get("wave_family") or "").strip().lower() == "analysis_wave"


def is_current_plan(path: Path) -> bool:
    """Plan checks apply independent of a filename's date or lack of one."""
    return path.name != "_template.md"


def is_architect_understanding_block_enforced(path: Path) -> bool:
    return is_current_plan(path)


def is_russian_plan_statement_warning_enforced(path: Path) -> bool:
    return is_current_plan(path)


def architect_understanding_block_severity(status_value: str | None) -> str:
    status_norm = " ".join((status_value or "").strip().lower().split())
    return "WARN" if status_norm == "architect initial draft" else "ERROR"


def is_meta_required(path: Path) -> bool:
    return is_current_plan(path)


def is_reviewer_ad_hoc_automation_ban_enforced(path: Path) -> bool:
    return is_current_plan(path)


def is_navigation_contract_enforced(path: Path) -> bool:
    return is_current_plan(path)


def is_post_merge_gate_enforced(path: Path) -> bool:
    return is_current_plan(path)


def is_done_executable_review_artifact_guard_enforced(path: Path) -> bool:
    return is_current_plan(path)


def is_review_artifact_rerun_freshness_enforced(path: Path) -> bool:
    return is_current_plan(path)


def is_review_route_determinism_enforced(path: Path) -> bool:
    return is_current_plan(path)


def is_blocker_attribution_contract_enforced(path: Path) -> bool:
    return is_current_plan(path)


def is_documentation_impact_enforced(path: Path) -> bool:
    return is_current_plan(path)


def documentation_impact_target_drift_severity(path: Path, status_value: str | None) -> str:
    if is_current_plan(path) and requires_code_draft(status_value):
        return "ERROR"
    return "WARN"


def documentation_impact_target_drift_prefix(severity: str) -> str:
    if severity == "ERROR":
        return "Documentation impact / provenance hard gate: "
    return "Documentation impact / provenance warning: "


def is_scope_route_classification_enforced(path: Path) -> bool:
    return is_current_plan(path)


def is_analysis_route_single_authority_enforced(path: Path) -> bool:
    return is_current_plan(path)


def is_coder_rerun_window(status_value: str | None) -> bool:
    if not status_value:
        return False
    return status_value.strip().lower() in {"in progress", "ready for review"}


def is_active_dev_plan(plan_type: str | None, status_value: str | None) -> bool:
    if not plan_type or plan_type.strip().lower() != "dev":
        return False
    if not status_value:
        return True
    status_norm = status_value.strip().lower()
    return not (status_norm.startswith("done") or status_norm.startswith("superseded"))


def is_repo_relative_plan_path(value: str) -> bool:
    candidate = value.strip()
    if not candidate or not REPO_RELATIVE_PLAN_PATH_RE.fullmatch(candidate):
        return False
    parts = PurePosixPath(candidate).parts
    return ".." not in parts


def parse_blocking_dependency_carrier(
    plan_meta_obj: Mapping[str, object] | None,
) -> tuple[tuple[str, ...] | None, list[str]]:
    """Parse the opt-in hard external-dependency carrier without inferring it.

    ``None`` means the carrier is absent and preserves ordinary ``depends_on``
    compatibility.  A present malformed carrier returns diagnostics so the
    queue can fail closed before it considers any state transition.
    """

    field = BLOCKING_DEPENDENCY_CARRIER_FIELD
    if not isinstance(plan_meta_obj, Mapping) or field not in plan_meta_obj:
        return None, []

    raw_entries = plan_meta_obj.get(field)
    if not isinstance(raw_entries, list):
        return (), [
            f"plan_meta.{field} must be a JSON array of unique, lexicographically sorted "
            "repo-relative `docs/plans/*.md` strings."
        ]

    entries: list[str] = []
    errors: list[str] = []
    for index, raw_entry in enumerate(raw_entries):
        if not isinstance(raw_entry, str):
            errors.append(
                f"plan_meta.{field}[{index}] must be a repo-relative `docs/plans/*.md` string."
            )
            continue
        if raw_entry != raw_entry.strip() or not is_repo_relative_plan_path(raw_entry):
            errors.append(
                f"plan_meta.{field}[{index}] must be a canonical repo-relative `docs/plans/*.md` path."
            )
            continue
        entries.append(raw_entry)

    if len(set(entries)) != len(entries):
        errors.append(f"plan_meta.{field} must contain unique paths.")
    if entries != sorted(entries):
        errors.append(f"plan_meta.{field} must be lexicographically sorted.")

    depends_on = plan_meta_obj.get(BLOCKING_DEPENDENCY_CARRIER_SUBSET_FIELD)
    if not isinstance(depends_on, list) or any(not isinstance(item, str) for item in depends_on):
        errors.append(
            f"plan_meta.{field} requires plan_meta.{BLOCKING_DEPENDENCY_CARRIER_SUBSET_FIELD} "
            "to be a JSON array of strings."
        )
    else:
        missing = [entry for entry in entries if entry not in depends_on]
        if missing:
            errors.append(
                f"plan_meta.{field} entries must also appear in "
                f"plan_meta.{BLOCKING_DEPENDENCY_CARRIER_SUBSET_FIELD}: {', '.join(missing)}."
            )

    return tuple(entries), errors


def blocking_dependency_readback_severity(
    plan_meta_obj: Mapping[str, object],
    *,
    status_value: str | None,
) -> str:
    status_norm = planning_contour_token(status_value or "")
    queue_activation = plan_meta_obj.get("queue_activation")
    activation_state = (
        planning_contour_token(queue_activation.get("state"))
        if isinstance(queue_activation, Mapping)
        else ""
    )
    if status_norm in BLOCKING_DEPENDENCY_TERMINAL_STATUS_NORMS:
        return "WARN"
    if activation_state in {"owner_approved", "architect_approved"}:
        return "ERROR"
    if (
        status_norm in BLOCKING_DEPENDENCY_EARLY_STATUS_NORMS
        and activation_state in {"n/a", "not_requested"}
    ):
        return "WARN"
    return "ERROR"


def validate_blocking_dependency_carrier(
    path: Path,
    plan_meta_obj: Mapping[str, object] | None,
    plan_meta_line: int | None,
    *,
    status_value: str | None,
    context: ContractContext | None = None,
) -> list[Finding]:
    entries, errors = parse_blocking_dependency_carrier(plan_meta_obj)
    if entries is None:
        return []

    line = plan_meta_line or 1
    if errors:
        return [Finding(path, line, "ERROR", error) for error in errors]

    assert isinstance(plan_meta_obj, Mapping)
    severity = blocking_dependency_readback_severity(plan_meta_obj, status_value=status_value)
    resolved_context = context or _ACTIVE_PLAN_LINT_CONTEXT.get()
    repo_root = repo_root_for_plan_path(path, context=resolved_context)
    findings: list[Finding] = []
    for dependency in entries:
        try:
            oracle = plan_status_oracle.oracle_result(
                repo_root / dependency,
                context=resolved_context,
            )
        except Exception as exc:
            findings.append(
                Finding(
                    path,
                    line,
                    severity,
                    "Blocking dependency readback: "
                    f"{dependency} could not be evaluated through "
                    "plan_status_oracle.oracle_result(...).delivery_green "
                    f"({type(exc).__name__}: {exc}).",
                )
            )
            continue
        if oracle.delivery_green is not True:
            findings.append(
                Finding(
                    path,
                    line,
                    severity,
                    "Blocking dependency readback: "
                    f"{dependency} requires "
                    "plan_status_oracle.oracle_result(...).delivery_green=true; "
                    "observed delivery_green=false.",
                )
            )
    return findings


def extract_json_code_blocks(lines: list[str]) -> list[tuple[int, str]]:
    blocks: list[tuple[int, str]] = []
    in_json = False
    start_line = 0
    buf: list[str] = []

    for idx, line in enumerate(lines, start=1):
        if not in_json and JSON_FENCE_START_RE.match(line):
            in_json = True
            start_line = idx
            buf = []
            continue

        if in_json and FENCE_END_RE.match(line):
            blocks.append((start_line, "\n".join(buf).strip()))
            in_json = False
            start_line = 0
            buf = []
            continue

        if in_json:
            buf.append(line)

    return blocks


def _normalize_text(value: str) -> str:
    return SPACE_RE.sub(" ", value.lower()).strip()


def _normalize_literal(value: str) -> str:
    return SPACE_RE.sub(" ", value.replace("`", "").strip()).strip()


def _snapshot_string_from_structured_payload(snapshot: dict[str, Any]) -> str | None:
    for key in ("normalized", "literal", "value", "target", "target_ref"):
        raw_value = snapshot.get(key)
        if isinstance(raw_value, str) and raw_value.strip():
            base = _normalize_literal(raw_value)
            bundle_sha = snapshot.get("bundle_sha256")
            if isinstance(bundle_sha, str) and bundle_sha.strip() and "bundle_sha256=" not in base:
                return _normalize_literal(f"{base} bundle_sha256={bundle_sha.strip()}")
            return base

    fields: list[str] = []
    for key in ("bundle", "range", "plan", "base_ref", "head_ref", "bundle_sha256"):
        raw_value = snapshot.get(key)
        if isinstance(raw_value, str) and raw_value.strip():
            fields.append(f"{key}={raw_value.strip()}")
    if not fields:
        return None
    return _normalize_literal(" ".join(fields))


def _extract_target_snapshot_from_payload(payload: dict[str, Any]) -> str | None:
    """Return the selector-compatible literal target snapshot from a lane receipt."""

    target_snapshot = payload.get("target_snapshot")
    if isinstance(target_snapshot, str) and target_snapshot.strip():
        base = _normalize_literal(target_snapshot)
        bundle_sha = payload.get("bundle_sha256")
        if isinstance(bundle_sha, str) and bundle_sha.strip() and "bundle_sha256=" not in base:
            return _normalize_literal(f"{base} bundle_sha256={bundle_sha.strip()}")
        snapshot_hashes = payload.get("snapshot_hashes")
        if isinstance(snapshot_hashes, dict):
            nested_bundle_sha = snapshot_hashes.get("bundle_sha256")
            if isinstance(nested_bundle_sha, str) and nested_bundle_sha.strip() and "bundle_sha256=" not in base:
                return _normalize_literal(f"{base} bundle_sha256={nested_bundle_sha.strip()}")
        return base
    if isinstance(target_snapshot, dict):
        return _snapshot_string_from_structured_payload(target_snapshot)
    return None


def _lifecycle_marker_is_true(value: Any) -> bool:
    if value is True:
        return True
    if isinstance(value, str):
        return _normalize_text(value.replace("`", "")) in {"true", "yes", "current", "latest", "active"}
    return False


def _lifecycle_marker_is_false(value: Any) -> bool:
    if value is False:
        return True
    if isinstance(value, str):
        return _normalize_text(value.replace("`", "")) in {
            "false",
            "no",
            "stale",
            "historical",
            "superseded",
            "not current",
            "not_current",
        }
    return False


def _has_superseded_marker(payload: dict[str, Any]) -> bool:
    superseded_by = payload.get("superseded_by")
    if superseded_by is None:
        return False
    if isinstance(superseded_by, str):
        normalized = _normalize_text(superseded_by.replace("`", ""))
        return bool(normalized and not normalized.startswith("n/a"))
    return True


def _risk_lane_lifecycle_flags(payload: dict[str, Any]) -> tuple[bool, bool]:
    explicit_current = _lifecycle_marker_is_true(payload.get("current"))
    explicit_non_current = _lifecycle_marker_is_false(payload.get("current")) or _has_superseded_marker(payload)
    for key in ("lifecycle", "lifecycle_status", "artifact_status", "artifact_state", "risk_artifact_state"):
        value = payload.get(key)
        if _lifecycle_marker_is_true(value):
            explicit_current = True
        if _lifecycle_marker_is_false(value):
            explicit_non_current = True
    return explicit_current, explicit_non_current


def _timestamp_match_has_only_wrapper_prefix(raw: str, match: re.Match[str]) -> bool:
    return not raw[: match.start()].strip(" \t\r\n([{<`'\"")


def _timestamp_match_timezone(raw: str, match: re.Match[str]) -> tuple[timezone | None, bool]:
    suffix = raw[match.end() :]
    suffix_match = re.fullmatch(
        r"(?P<fraction>\.\d+)?"
        r"(?P<timezone_spacing>\s*)"
        r"(?P<timezone>Z|MSK|[+-]\d{2}:?\d{2})?"
        r"(?P<trailing>[ \t\r\n,.;:)\]}>`'\"]*)",
        suffix,
        re.IGNORECASE,
    )
    if suffix_match is None:
        return None, True
    if suffix_match.group("fraction") and match.group("second") is None:
        return None, True
    timezone_token = suffix_match.group("timezone")
    if timezone_token is None:
        return None, False
    timezone_value = timezone_token.upper()
    if timezone_value == "Z":
        return timezone.utc, True
    if timezone_value == "MSK":
        # Legacy label of stamps written before the engine switched to local numeric offsets.
        return timezone(timedelta(hours=3)), True
    sign = 1 if timezone_value[0] == "+" else -1
    digits = timezone_value[1:].replace(":", "")
    hours = int(digits[:2])
    minutes = int(digits[2:])
    if hours > 23 or minutes > 59:
        return None, True
    return timezone(sign * timedelta(hours=hours, minutes=minutes)), True


def _timestamp_match_sort_key(
    raw: str,
    match: re.Match[str],
    *,
    year: str,
    month: str,
    day: str,
    normalize_timezone: bool,
) -> str | None:
    second = match.group("second") or "00"
    try:
        timestamp = datetime(
            int(year),
            int(month),
            int(day),
            int(match.group("hour")),
            int(match.group("minute")),
            int(second),
        )
    except ValueError:
        return None
    timestamp_timezone, has_timezone_token = _timestamp_match_timezone(raw, match)
    if has_timezone_token and timestamp_timezone is None:
        return None
    if normalize_timezone and timestamp_timezone is not None:
        timestamp = timestamp.replace(tzinfo=timestamp_timezone).astimezone(timezone.utc).replace(tzinfo=None)
    return timestamp.strftime("%Y%m%d%H%M%S")


def _sortable_timestamp_value(
    value: Any,
    *,
    normalize_timezone: bool = True,
    allow_embedded_prefix: bool = False,
) -> str | None:
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    iso_match = re.search(
        r"(?P<year>\d{4})[-_]?((?P<month>\d{2})[-_]?(?P<day>\d{2}))"
        r"[ T_-]*(?P<hour>\d{2}):?(?P<minute>\d{2})(?::?(?P<second>\d{2}))?",
        raw,
    )
    if iso_match:
        if not allow_embedded_prefix and not _timestamp_match_has_only_wrapper_prefix(raw, iso_match):
            return None
        return _timestamp_match_sort_key(
            raw,
            iso_match,
            year=iso_match.group("year"),
            month=iso_match.group("month"),
            day=iso_match.group("day"),
            normalize_timezone=normalize_timezone,
        )
    dmy_match = re.search(
        r"(?P<day>\d{2})\.(?P<month>\d{2})\.(?P<year>\d{4})"
        r"[ T_-]*(?P<hour>\d{2}):(?P<minute>\d{2})(?::(?P<second>\d{2}))?",
        raw,
    )
    if dmy_match:
        if not allow_embedded_prefix and not _timestamp_match_has_only_wrapper_prefix(raw, dmy_match):
            return None
        return _timestamp_match_sort_key(
            raw,
            dmy_match,
            year=dmy_match.group("year"),
            month=dmy_match.group("month"),
            day=dmy_match.group("day"),
            normalize_timezone=normalize_timezone,
        )
    run_id_match = re.search(
        r"(?P<date>\d{8})[T_-]?(?P<hour>\d{2})(?P<minute>\d{2})(?P<second>\d{2})?",
        raw,
    )
    if run_id_match:
        if not allow_embedded_prefix and not _timestamp_match_has_only_wrapper_prefix(raw, run_id_match):
            return None
        second = run_id_match.group("second") or "00"
        return f"{run_id_match.group('date')}{run_id_match.group('hour')}{run_id_match.group('minute')}{second}"
    return None


def _plan_risk_lane_candidates(plan_path: Path) -> tuple[PlanRiskLaneCandidate, ...]:
    """Read candidates with the pre-V1 public selector's exact behavior."""

    try:
        plan_text = plan_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ()
    candidates: list[PlanRiskLaneCandidate] = []
    for match in JSON_BLOCK_RE.finditer(plan_text):
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict) or payload.get("lane_id") != "reviewer_code_risk":
            continue
        target_snapshot = _extract_target_snapshot_from_payload(payload)
        if not target_snapshot:
            continue
        run_id = payload.get("run_id")
        run_id = run_id.strip() if isinstance(run_id, str) and run_id.strip() else None
        written_at = payload.get("written_at")
        has_written_at = isinstance(written_at, str) and bool(written_at.strip())
        explicit_current, explicit_non_current = _risk_lane_lifecycle_flags(payload)
        candidates.append(
            PlanRiskLaneCandidate(
                snapshot=target_snapshot,
                line_no=plan_text.count("\n", 0, match.start()) + 1,
                payload=payload,
                run_id=run_id,
                written_at_key=_sortable_timestamp_value(written_at),
                run_id_key=(
                    None if has_written_at else _sortable_timestamp_value(run_id, allow_embedded_prefix=True)
                ),
                explicit_current=explicit_current,
                explicit_non_current=explicit_non_current,
            )
        )
    return tuple(candidates)


def _candidate_label(candidate: PlanRiskLaneCandidate) -> str:
    run_id = candidate.run_id or "run_id=<missing>"
    return f"line {candidate.line_no} {run_id}"


def _risk_lane_lifecycle_error(
    candidate: PlanRiskLaneCandidate,
    *,
    code: str,
    message: str,
) -> PlanRiskLaneSelection:
    return PlanRiskLaneSelection(
        snapshot=None,
        line_no=candidate.line_no,
        payload=None,
        error_code=code,
        message=message,
    )


def _meaningful_superseded_by(value: str | None) -> str | None:
    """Return a meaningful ``superseded_by`` target, excluding blank/N/A."""

    if value is None:
        return None
    normalized = value.strip()
    if not normalized or _normalize_text(normalized.replace("`", "")).startswith("n/a"):
        return None
    return normalized


def _validate_plan_risk_lane_lifecycle(
    candidates: Sequence[PlanRiskLaneCandidate],
) -> PlanRiskLaneSelection | None:
    """Fail closed on contradictory compact risk-lane lifecycle metadata."""

    for candidate in candidates:
        if candidate.explicit_current and candidate.explicit_non_current:
            return _risk_lane_lifecycle_error(
                candidate,
                code="risk_lane_lifecycle_contradiction",
                message=(
                    "Plan-resident `reviewer_code_risk` candidate has simultaneous current and "
                    f"historical/superseded lifecycle markers: {_candidate_label(candidate)}."
                ),
            )

        raw_superseded_by = candidate.payload.get("superseded_by")
        if raw_superseded_by is not None and not isinstance(raw_superseded_by, str):
            return _risk_lane_lifecycle_error(
                candidate,
                code="risk_lane_superseded_by_invalid",
                message=(
                    "Plan-resident `reviewer_code_risk.superseded_by` must be a non-empty string "
                    f"owned by a candidate with a non-empty `run_id`: {_candidate_label(candidate)}."
                ),
            )
        superseded_by = _meaningful_superseded_by(raw_superseded_by)
        if superseded_by is None:
            continue
        if candidate.run_id is None:
            return _risk_lane_lifecycle_error(
                candidate,
                code="risk_lane_superseded_by_invalid",
                message=(
                    "Plan-resident `reviewer_code_risk.superseded_by` must be a non-empty string "
                    f"owned by a candidate with a non-empty `run_id`: {_candidate_label(candidate)}."
                ),
            )
        if superseded_by == candidate.run_id:
            return _risk_lane_lifecycle_error(
                candidate,
                code="risk_lane_superseded_by_self",
                message=(
                    "Plan-resident `reviewer_code_risk.superseded_by` must not self-reference "
                    f"`run_id`: {_candidate_label(candidate)}."
                ),
            )

        sibling_matches = [
            sibling
            for sibling in candidates
            if sibling is not candidate and sibling.run_id == superseded_by
        ]
        if not sibling_matches:
            return _risk_lane_lifecycle_error(
                candidate,
                code="risk_lane_superseded_by_orphan",
                message=(
                    "Plan-resident `reviewer_code_risk.superseded_by` must reference one parseable "
                    f"sibling `run_id`; target={superseded_by!r} from {_candidate_label(candidate)}."
                ),
            )
        if len(sibling_matches) > 1:
            return _risk_lane_lifecycle_error(
                candidate,
                code="risk_lane_superseded_by_ambiguous",
                message=(
                    "Plan-resident `reviewer_code_risk.superseded_by` references multiple parseable "
                    f"sibling runs; target={superseded_by!r} from {_candidate_label(candidate)}."
                ),
            )
    return None


def _ambiguous_risk_lane_selection(
    candidates: Sequence[PlanRiskLaneCandidate], reason: str
) -> PlanRiskLaneSelection:
    labels = ", ".join(_candidate_label(candidate) for candidate in candidates)
    return PlanRiskLaneSelection(
        snapshot=None,
        line_no=candidates[0].line_no if candidates else 1,
        payload=None,
        error_code="ambiguous_plan_resident_risk_lane",
        message=(
            "Origin plan has multiple parseable `reviewer_code_risk` lane-run JSON blocks without a unique "
            f"current/latest selector ({reason}): {labels}. Add exactly one explicit `current=true` marker "
            "or mark historical blocks with `current=false` / `superseded_by` and sortable `written_at` / `run_id`."
        ),
    )


def select_plan_risk_lane_snapshot(plan_path: str | Path) -> PlanRiskLaneSelection:
    """Return the deterministic current ``reviewer_code_risk`` snapshot for a plan.

    This intentionally preserves the former ``review_artifact_lint`` selection
    behavior and field values.  Its new location makes it safe for both the
    review-artifact compatibility projection and the semantic producer to use
    one implementation.
    """

    candidates = _plan_risk_lane_candidates(Path(plan_path))
    if not candidates:
        return PlanRiskLaneSelection(snapshot=None, line_no=1, payload=None, error_code=None, message=None)
    lifecycle_error = _validate_plan_risk_lane_lifecycle(candidates)
    if lifecycle_error is not None:
        return lifecycle_error
    if len(candidates) == 1:
        selected = candidates[0]
        if selected.explicit_non_current:
            return _ambiguous_risk_lane_selection(candidates, "all candidates are marked historical/superseded")
        return PlanRiskLaneSelection(
            snapshot=selected.snapshot,
            line_no=selected.line_no,
            payload=selected.payload,
            error_code=None,
            message=None,
            run_id=selected.run_id,
            reason="single parseable reviewer_code_risk lane",
        )

    explicit_current = [candidate for candidate in candidates if candidate.explicit_current]
    if len(explicit_current) == 1:
        selected = explicit_current[0]
        return PlanRiskLaneSelection(
            snapshot=selected.snapshot,
            line_no=selected.line_no,
            payload=selected.payload,
            error_code=None,
            message=None,
            run_id=selected.run_id,
            reason="explicit current marker selected",
        )
    if len(explicit_current) > 1:
        return _ambiguous_risk_lane_selection(explicit_current, "multiple explicit current markers")

    active_candidates = [candidate for candidate in candidates if not candidate.explicit_non_current]
    if len(active_candidates) == 1:
        selected = active_candidates[0]
        return PlanRiskLaneSelection(
            snapshot=selected.snapshot,
            line_no=selected.line_no,
            payload=selected.payload,
            error_code=None,
            message=None,
            run_id=selected.run_id,
            reason="single non-historical reviewer_code_risk lane selected",
        )
    if not active_candidates:
        return _ambiguous_risk_lane_selection(candidates, "all candidates are marked historical/superseded")

    if any(candidate.written_at_key is None and candidate.run_id_key is None for candidate in active_candidates):
        return _ambiguous_risk_lane_selection(active_candidates, "missing sortable `written_at` / `run_id`")

    keyed_candidates = [
        ((candidate.written_at_key or candidate.run_id_key or ""), candidate)
        for candidate in active_candidates
    ]
    keyed_candidates.sort(key=lambda item: item[0], reverse=True)
    if len(keyed_candidates) > 1 and keyed_candidates[0][0] == keyed_candidates[1][0]:
        return _ambiguous_risk_lane_selection(active_candidates, "latest `written_at` / `run_id` tie")
    selected = keyed_candidates[0][1]
    return PlanRiskLaneSelection(
        snapshot=selected.snapshot,
        line_no=selected.line_no,
        payload=selected.payload,
        error_code=None,
        message=None,
        run_id=selected.run_id,
        reason="latest sortable written_at/run_id selected",
    )


# Compatibility for existing callers while review_artifact_lint moves
# to the public export above.  New code must call select_plan_risk_lane_snapshot.
def _select_plan_risk_lane_snapshot(plan_path: Path) -> PlanRiskLaneSelection:
    return select_plan_risk_lane_snapshot(plan_path)


HOMEBREW_PYTHON_LITERAL = "/" + "opt/homebrew/bin/python3"
HOMEBREW_COMMAND_EVIDENCE_CODE = "expanded_homebrew_python_command_evidence"
COMMAND_EVIDENCE_KEY_MARKERS = (
    "command",
    "commands",
    "commands_run",
    "cmd",
    "gate",
    "gates",
    "verification",
)
RAW_DIAGNOSTIC_KEY_MARKERS = (
    "stdout",
    "stderr",
    "raw_output",
    "raw output",
    "log",
    "traceback",
)
RISK_LANE_COMPACT_FINDING_FIELDS = ("id", "severity", "domain", "title", "source_refs")


def _payload_string(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _is_current_bundle_snapshot(value: str | None) -> bool:
    if value is None:
        return False
    normalized = _normalize_literal(value)
    return normalized.startswith(CURRENT_BUNDLE_TARGET) and "bundle_sha256=" in normalized


def _selected_current_bundle_claim(value: object) -> bool:
    """Return whether the selected compact machine carrier claims current authority.

    This deliberately reuses the canonical current-claim shape probe only for
    the selected ``target_snapshot`` field.  It must not become a prose scan:
    a nonterminal bare or partial ``BUNDLE=current`` compact claim is an
    attempted authority carrier and therefore enters strict admission, while
    terminal immutable history retains its lifecycle-only compatibility path.
    """

    return _current_review_claim_shaped(value)


def _looks_like_command(value: str) -> bool:
    stripped = value.strip().strip("`").strip()
    if not stripped:
        return False
    if stripped.startswith(("$PYBIN ", "python3 ", "zsh ", "make ", "./", "/", "PYBIN=")):
        return True
    return " -B " in stripped or " --" in stripped


def _is_raw_diagnostic_path(key_path: Sequence[str]) -> bool:
    key_text = ".".join(key_path).casefold()
    return any(marker in key_text for marker in RAW_DIAGNOSTIC_KEY_MARKERS)


def _is_command_evidence_path(key_path: Sequence[str], value: str) -> bool:
    if _is_raw_diagnostic_path(key_path):
        return False
    key_text = ".".join(key_path).casefold()
    return any(marker in key_text for marker in COMMAND_EVIDENCE_KEY_MARKERS) or _looks_like_command(value)


def _iter_homebrew_command_payload_paths(value: Any, key_path: Sequence[str] = ()) -> Iterable[str]:
    if isinstance(value, dict):
        for key, nested in value.items():
            yield from _iter_homebrew_command_payload_paths(nested, (*key_path, str(key)))
        return
    if isinstance(value, list):
        for index, nested in enumerate(value):
            yield from _iter_homebrew_command_payload_paths(nested, (*key_path, str(index)))
        return
    if not isinstance(value, str) or HOMEBREW_PYTHON_LITERAL not in value:
        return
    if _is_command_evidence_path(key_path, value):
        yield ".".join(key_path) or "<root>"


def _canonical_risk_lane_findings_projection(payload: dict[str, Any]) -> str | None:
    findings = payload.get("findings")
    if not isinstance(findings, list):
        return None
    projection: list[dict[str, object]] = []
    for finding in findings:
        if not isinstance(finding, dict):
            return None
        item: dict[str, object] = {}
        for field in RISK_LANE_COMPACT_FINDING_FIELDS:
            value = finding.get(field)
            if field == "source_refs":
                if not isinstance(value, list) or any(
                    not isinstance(source_ref, str) or not source_ref.strip() for source_ref in value
                ):
                    return None
                item[field] = [source_ref.strip() for source_ref in value]
            elif not isinstance(value, str) or not value.strip():
                return None
            else:
                item[field] = value.strip()
        projection.append(item)
    return json.dumps(projection, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _resolve_repo_relative_support_ref(project_root: Path, ref: str) -> Path | None:
    ref_path = Path(ref.strip())
    if ref_path.is_absolute() or ref_path.parts[:1] == ("~",) or any(part == ".." for part in ref_path.parts):
        return None
    resolved_root = project_root.resolve()
    lexical_path = resolved_root / ref_path
    candidate = resolved_root
    for part in ref_path.parts:
        candidate /= part
        if candidate.is_symlink():
            return None
    return lexical_path


def collect_plan_risk_lane_support_refs(
    plan_path: str | Path,
    *,
    project_root: str | Path | None = None,
) -> PlanRiskLaneSupportManifest:
    """Collect all declared risk-support assets without selecting a current run.

    This is the exact-bundle membership boundary.  It intentionally scans every
    parseable plan JSON block independently from ``_plan_risk_lane_candidates``:
    historical receipts can lack ``target_snapshot`` and must still be retained
    or rejected truthfully.  Historical payload contents are never JSON/schema
    or parity validated here; only their declared path and bytes/hash durable
    identity is checked.
    """

    resolved_plan_path = Path(plan_path).resolve()
    resolved_root = (
        Path(project_root).resolve() if project_root is not None else repo_root_for_plan_path(resolved_plan_path)
    )
    try:
        resolved_plan_path.relative_to(resolved_root)
    except ValueError:
        return PlanRiskLaneSupportManifest(
            records=(),
            diagnostics=(
                RiskLaneSupportDiagnostic(
                    code="invalid_risk_lane_support_payload_ref",
                    message=(
                        "Origin plan must resolve inside the caller-resolved project root: "
                        f"plan={resolved_plan_path}; project_root={resolved_root}."
                    ),
                ),
            ),
        )

    try:
        plan_text = resolved_plan_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return PlanRiskLaneSupportManifest(
            records=(),
            diagnostics=(
                RiskLaneSupportDiagnostic(
                    code="missing_risk_lane_support_payload_file",
                    message=f"Origin plan is unreadable for risk-support membership: {exc}",
                ),
            ),
        )

    records: list[tuple[str, str]] = []
    diagnostics: list[RiskLaneSupportDiagnostic] = []
    seen_pairs: set[tuple[str, str]] = set()
    declared_hashes_by_path: dict[str, str] = {}

    for match in JSON_BLOCK_RE.finditer(plan_text):
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict) or payload.get("lane_id") != "reviewer_code_risk":
            continue

        has_ref = "full_payload_ref" in payload
        has_hash = "full_payload_sha256" in payload
        if not has_ref and not has_hash:
            continue

        support_ref = _payload_string(payload, "full_payload_ref")
        support_sha = _payload_string(payload, "full_payload_sha256")
        if support_ref is None:
            diagnostics.append(
                RiskLaneSupportDiagnostic(
                    code="missing_risk_lane_support_payload_ref",
                    message="Plan-resident `reviewer_code_risk` support declaration lacks a non-empty `full_payload_ref`.",
                )
            )
        if support_sha is None:
            diagnostics.append(
                RiskLaneSupportDiagnostic(
                    code="missing_risk_lane_support_payload_hash",
                    message="Plan-resident `reviewer_code_risk` support declaration lacks a non-empty `full_payload_sha256`.",
                )
            )
        if support_ref is None or support_sha is None:
            continue

        support_path = _resolve_repo_relative_support_ref(resolved_root, support_ref)
        if support_path is None:
            diagnostics.append(
                RiskLaneSupportDiagnostic(
                    code="invalid_risk_lane_support_payload_ref",
                    message=(
                        "Plan-resident `reviewer_code_risk.full_payload_ref` must be a repo-relative "
                        f"symlink-free path inside the project root: {support_ref}"
                    ),
                )
            )
            continue

        canonical_path = str(support_path)
        previous_sha = declared_hashes_by_path.get(canonical_path)
        if previous_sha is not None and previous_sha != support_sha:
            diagnostics.append(
                RiskLaneSupportDiagnostic(
                    code="risk_lane_support_payload_hash_conflict",
                    message=(
                        "Plan-resident `reviewer_code_risk` support declarations assign conflicting hashes "
                        f"to {support_ref}: first={previous_sha}; later={support_sha}."
                    ),
                )
            )
            continue
        declared_hashes_by_path.setdefault(canonical_path, support_sha)

        pair = (support_ref, support_sha)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)

        if not support_path.exists() or not support_path.is_file():
            diagnostics.append(
                RiskLaneSupportDiagnostic(
                    code="missing_risk_lane_support_payload_file",
                    message=f"Plan-resident risk-support payload file is missing: {support_ref}",
                )
            )
            continue
        try:
            support_bytes = support_path.read_bytes()
        except OSError:
            diagnostics.append(
                RiskLaneSupportDiagnostic(
                    code="missing_risk_lane_support_payload_file",
                    message=f"Plan-resident risk-support payload file is unreadable: {support_ref}",
                )
            )
            continue

        actual_sha = hashlib.sha256(support_bytes).hexdigest()
        if actual_sha != support_sha:
            diagnostics.append(
                RiskLaneSupportDiagnostic(
                    code="risk_lane_support_payload_hash_mismatch",
                    message=(
                        "Plan-resident risk-support payload hash does not match declared bytes: "
                        f"ref={support_ref}; expected={support_sha}; actual={actual_sha}."
                    ),
                )
            )
            continue
        records.append(pair)

    return PlanRiskLaneSupportManifest(records=tuple(records), diagnostics=tuple(diagnostics))


def preflight_selected_risk_lane_support(
    plan_path: str | Path,
    selection: PlanRiskLaneSelection,
    *,
    project_root: str | Path | None = None,
) -> tuple[RiskLaneSupportDiagnostic, ...]:
    """Validate immutable support for one lifecycle-valid tentative selection.

    The raw selector intentionally remains lifecycle-only.  This read-only
    boundary is called by the selector CLI, final review-artifact lint and
    exact-bundle scope inspection. Scope callers use this raw diagnostic tuple
    independently of current-proof completion diagnostics; historical manifest
    collection remains path/bytes/hash-only.
    """

    if selection.error_code or selection.snapshot is None or selection.payload is None:
        return ()

    resolved_plan_path = Path(plan_path).resolve()
    resolved_root = (
        Path(project_root).resolve() if project_root is not None else repo_root_for_plan_path(resolved_plan_path)
    )
    try:
        resolved_plan_path.relative_to(resolved_root)
    except ValueError:
        return (
            RiskLaneSupportDiagnostic(
                code="origin_plan_outside_project_root",
                message=(
                    "`origin_plan` must resolve inside the caller-resolved project root: "
                    f"plan={resolved_plan_path}; project_root={resolved_root}."
                ),
            ),
        )

    support_ref = _payload_string(selection.payload, "full_payload_ref")
    support_sha = _payload_string(selection.payload, "full_payload_sha256")
    current_bundle = _is_current_bundle_snapshot(selection.snapshot)
    current_claim = _selected_current_bundle_claim(selection.payload.get("target_snapshot"))
    terminal_history = False
    if current_claim:
        try:
            status_lines = extract_status_lines(resolved_plan_path.read_text(encoding="utf-8", errors="replace").splitlines())
        except OSError:
            # The fresh producer call below owns this as a typed unavailable
            # failure if the compact carrier is otherwise current-shaped.
            status_lines = []
        if len(status_lines) == 1:
            status_norm = " ".join(status_lines[0][1].replace("`", "").split()).lower()
            terminal_history = status_norm in {"done", "superseded"}
    fresh_current_claim = current_claim and not terminal_history
    strict_current_bundle = current_bundle or fresh_current_claim
    diagnostics: list[RiskLaneSupportDiagnostic] = []

    if support_ref is None and (support_sha is not None or strict_current_bundle):
        diagnostics.append(
            RiskLaneSupportDiagnostic(
                code="missing_risk_lane_support_payload_ref",
                message="`full_payload_sha256` is present or BUNDLE=current requires `full_payload_ref`.",
            )
        )
    if support_sha is None and (support_ref is not None or strict_current_bundle):
        diagnostics.append(
            RiskLaneSupportDiagnostic(
                code="missing_risk_lane_support_payload_hash",
                message="`full_payload_ref` is present or BUNDLE=current requires `full_payload_sha256`.",
            )
        )
    if support_ref is None:
        return tuple(diagnostics)

    support_path = _resolve_repo_relative_support_ref(resolved_root, support_ref)
    if support_path is None:
        diagnostics.append(
            RiskLaneSupportDiagnostic(
                code="invalid_risk_lane_support_payload_ref",
                message=(
                    "`full_payload_ref` must be a repo-relative, symlink-free path inside the project root: "
                    f"{support_ref}"
                ),
            )
        )
        return tuple(diagnostics)
    if not support_path.exists() or not support_path.is_file():
        diagnostics.append(
            RiskLaneSupportDiagnostic(
                code="missing_risk_lane_support_payload_file",
                message=f"`full_payload_ref` file is missing: {support_ref}",
            )
        )
        return tuple(diagnostics)

    try:
        support_bytes = support_path.read_bytes()
    except OSError:
        diagnostics.append(
            RiskLaneSupportDiagnostic(
                code="missing_risk_lane_support_payload_file",
                message=f"`full_payload_ref` file is unreadable: {support_ref}",
            )
        )
        return tuple(diagnostics)

    if support_sha is not None:
        actual_sha = hashlib.sha256(support_bytes).hexdigest()
        if actual_sha != support_sha:
            diagnostics.append(
                RiskLaneSupportDiagnostic(
                    code="risk_lane_support_payload_hash_mismatch",
                    message=(
                        "`full_payload_sha256` does not match referenced support payload: "
                        f"expected={support_sha}; actual={actual_sha}."
                    ),
                )
            )

    try:
        support_payload = json.loads(support_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        diagnostics.append(
            RiskLaneSupportDiagnostic(
                code="invalid_risk_lane_support_payload_json",
                message=f"`full_payload_ref` must contain a JSON object: {exc}",
            )
        )
        return tuple(diagnostics)
    if not isinstance(support_payload, dict):
        diagnostics.append(
            RiskLaneSupportDiagnostic(
                code="invalid_risk_lane_support_payload_json",
                message="`full_payload_ref` must contain a JSON object.",
            )
        )
        return tuple(diagnostics)

    command_paths = tuple(_iter_homebrew_command_payload_paths(support_payload))
    if command_paths:
        diagnostics.append(
            RiskLaneSupportDiagnostic(
                code=HOMEBREW_COMMAND_EVIDENCE_CODE,
                message=(
                    "`full_payload_ref` contains expanded owner-local Homebrew interpreter command evidence at "
                    f"{', '.join(command_paths)}; record `$PYBIN ...` or `python3 ...` instead."
                ),
            )
        )

    parity_errors: list[str] = []
    support_snapshot = _extract_target_snapshot_from_payload(support_payload)
    compact_snapshot: dict[str, str] | None = None
    validated_support_snapshot: dict[str, Any] | None = None
    if strict_current_bundle:
        if fresh_current_claim:
            compact_snapshot, compact_error = _exact_current_compact_snapshot(
                selection.payload.get("target_snapshot")
            )
            if compact_error is not None:
                diagnostics.append(
                    RiskLaneSupportDiagnostic(
                        code="current_review_proof_compact_snapshot_invalid",
                        message=compact_error,
                    )
                )
        try:
            validated_support_snapshot = validate_snapshot_payload(support_payload.get("target_snapshot"))
        except SnapshotError as exc:
            diagnostics.append(
                RiskLaneSupportDiagnostic(
                    code="invalid_risk_lane_support_payload_snapshot",
                    message=(
                        "Current BUNDLE=current support payload must carry an exact nested "
                        f"validated review_target_snapshot current-bundle payload: {exc}."
                    ),
                )
            )
        else:
            validated_target = validated_support_snapshot.get("target")
            support_snapshot = _normalize_literal(validated_target) if isinstance(validated_target, str) else None
    if support_snapshot != selection.snapshot:
        parity_errors.append("target_snapshot")

    compact_run_id = _payload_string(selection.payload, "run_id")
    support_run_id = _payload_string(support_payload, "run_id")
    if compact_run_id is None or support_run_id is None or compact_run_id != support_run_id:
        parity_errors.append("run_id")

    if _payload_string(support_payload, "lane_id") != "reviewer_code_risk":
        parity_errors.append("lane_id")

    compact_lane_status = _payload_string(selection.payload, "lane_status")
    support_lane_status = _payload_string(support_payload, "lane_status")
    if compact_lane_status is None or support_lane_status is None:
        parity_errors.append("lane_status")
    elif _normalize_text(compact_lane_status) != _normalize_text(support_lane_status):
        parity_errors.append("lane_status")

    _, support_explicit_non_current = _risk_lane_lifecycle_flags(support_payload)
    if support_explicit_non_current:
        parity_errors.append("current")

    compact_findings_projection = _canonical_risk_lane_findings_projection(selection.payload)
    support_findings_projection = _canonical_risk_lane_findings_projection(support_payload)
    if compact_findings_projection is None or support_findings_projection is None:
        parity_errors.append("findings")
    elif compact_findings_projection != support_findings_projection:
        parity_errors.append("findings")

    if parity_errors:
        diagnostics.append(
            RiskLaneSupportDiagnostic(
                code="risk_lane_support_payload_parity_mismatch",
                message=(
                    "Support payload disagrees with selected plan-resident `reviewer_code_risk` compact truth: "
                    f"{', '.join(sorted(set(parity_errors)))}."
                ),
            )
        )
    if diagnostics or not fresh_current_claim:
        return tuple(diagnostics)

    # A compact hashed-current claim is an authority candidate, not merely a
    # lifecycle marker.  The selector must compare it with a freshly derived
    # producer snapshot before it can report `selected`; otherwise a changed
    # or removed target could retain an authenticated but stale support file.
    assert compact_snapshot is not None
    assert validated_support_snapshot is not None
    expected_target = f"{CURRENT_BUNDLE_TARGET} bundle_sha256={compact_snapshot['bundle_sha256']}"
    if selection.snapshot != expected_target:
        diagnostics.append(
            RiskLaneSupportDiagnostic(
                code="current_review_proof_projection_mismatch",
                message=(
                    "Selected compact target_snapshot must exactly project its "
                    "canonical BUNDLE=current bundle_sha256 carrier."
                ),
            )
        )
        return tuple(diagnostics)
    try:
        producer_snapshot = build_current_bundle_snapshot(resolved_plan_path, project_root=resolved_root)
    except (OSError, SnapshotError) as exc:
        diagnostics.append(
            RiskLaneSupportDiagnostic(
                code="current_review_proof_producer_or_support_unavailable",
                message=f"Current review proof cannot read fresh canonical producer bytes: {exc}",
            )
        )
        return tuple(diagnostics)
    if validated_support_snapshot != producer_snapshot:
        diagnostics.append(
            RiskLaneSupportDiagnostic(
                code="current_review_proof_producer_mismatch",
                message="Immutable support target_snapshot must exactly equal fresh canonical producer output.",
            )
        )
        return tuple(diagnostics)
    if (
        producer_snapshot.get("target") != expected_target
        or producer_snapshot.get("target_snapshot") != compact_snapshot
    ):
        diagnostics.append(
            RiskLaneSupportDiagnostic(
                code="current_review_proof_projection_mismatch",
                message=(
                    "Fresh producer Target and compact target_snapshot disagree with the selected "
                    "current review proof."
                ),
            )
        )
    return tuple(diagnostics)


_CURRENT_REVIEW_TARGET_RE = re.compile(
    rf"^{re.escape(CURRENT_BUNDLE_TARGET)} bundle_sha256=(?P<sha256>[0-9a-f]{{64}})$"
)
_CURRENT_REVIEW_PROOF_TERMINAL_HISTORY_STATUSES = frozenset({"done", "superseded"})


def _current_review_claim_shaped(value: object) -> bool:
    """Return whether an authoritative snapshot field claims a current bundle.

    This intentionally looks only at fields already selected as machine
    carriers (a review Target or a compact/support ``target_snapshot``).  It
    must not become a prose scanner: ordinary narrative references to current
    work are outside this classifier.
    """

    if isinstance(value, str):
        normalized = value.casefold()
        return "bundle" in normalized and "current" in normalized
    if not isinstance(value, dict):
        return False
    target = value.get("target")
    if isinstance(target, str):
        return _current_review_claim_shaped(target)
    # A compact current projection without its literal target is malformed but
    # still an attempted authority claim, so it must not fall back to history.
    return "bundle_sha256" in value and any(
        isinstance(key, str) and "target" in key.casefold() for key in value
    )


def _exact_current_review_target(value: object) -> tuple[str | None, str | None]:
    if not isinstance(value, str):
        return None, "current review Target must be a string"
    match = _CURRENT_REVIEW_TARGET_RE.fullmatch(value)
    if match is None:
        return None, (
            "current review Target must exactly equal "
            "`BUNDLE=current bundle_sha256=<64 lowercase hex>`"
        )
    return match.group("sha256"), None


def _exact_current_compact_snapshot(value: object) -> tuple[dict[str, str] | None, str | None]:
    if not isinstance(value, dict):
        return None, "current compact target_snapshot must be an object"
    if set(value) != {"bundle_sha256", "target"}:
        return None, "current compact target_snapshot must contain exactly bundle_sha256 and target"
    bundle_sha = value.get("bundle_sha256")
    target = value.get("target")
    if not isinstance(bundle_sha, str) or _CURRENT_REVIEW_TARGET_RE.fullmatch(
        f"{CURRENT_BUNDLE_TARGET} bundle_sha256={bundle_sha}"
    ) is None:
        return None, "current compact target_snapshot.bundle_sha256 must be 64 lowercase hex"
    if target != CURRENT_BUNDLE_TARGET:
        return None, f"current compact target_snapshot.target must equal {CURRENT_BUNDLE_TARGET!r}"
    return {"bundle_sha256": bundle_sha, "target": target}, None


def _selected_support_has_current_claim(
    *,
    project_root: Path,
    selection: PlanRiskLaneSelection,
) -> bool:
    """Probe only the selected immutable wrapper for a structured current claim.

    A malformed/unreadable wrapper cannot be treated as proof, but a readable
    full snapshot that claims ``BUNDLE=current`` must not be downgraded to a
    non-current review merely because the header or compact receipt disagrees.
    Full support validation remains below in the same canonical reader.
    """

    if selection.payload is None:
        return False
    support_ref = _payload_string(selection.payload, "full_payload_ref")
    support_path = _resolve_repo_relative_support_ref(project_root, support_ref or "")
    if support_path is None or not support_path.is_file():
        return False
    try:
        support_payload = json.loads(support_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return isinstance(support_payload, dict) and _current_review_claim_shaped(
        support_payload.get("target_snapshot")
    )


def _current_review_proof_result(
    *,
    state: str,
    reason_code: str | None,
    message: str,
    plan_path: Path,
    review_path: Path | None,
    target: str | None,
    diagnostics: Sequence[RiskLaneSupportDiagnostic] = (),
) -> CurrentReviewProofPreflight:
    return CurrentReviewProofPreflight(
        state=state,
        reason_code=reason_code,
        message=message,
        plan_path=str(plan_path),
        review_path=str(review_path) if review_path is not None else None,
        target=target,
        diagnostics=tuple(diagnostics),
    )


def preflight_current_review_proof(
    plan_path: str | Path,
    *,
    project_root: str | Path | None = None,
) -> CurrentReviewProofPreflight:
    """Read one live current-review proof through the canonical authority path.

    ``select_plan_risk_lane_snapshot`` remains a lifecycle selector and is
    deliberately not tightened for old/range reviews.  This function owns the
    extra current-only grammar, immutable support, and fresh producer equality
    checks.  Consumers must project this result instead of reconstructing a
    permissive current-bundle rule from headers or hashes.
    """

    resolved_plan_path = Path(plan_path).resolve()
    resolved_root = (
        Path(project_root).resolve() if project_root is not None else repo_root_for_plan_path(resolved_plan_path)
    )
    try:
        resolved_plan_path.relative_to(resolved_root)
    except ValueError:
        return _current_review_proof_result(
            state="blocked",
            reason_code="current_review_proof_origin_outside_project_root",
            message="Current review proof origin plan must resolve inside the caller project root.",
            plan_path=resolved_plan_path,
            review_path=None,
            target=None,
        )
    try:
        plan_lines = resolved_plan_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return _current_review_proof_result(
            state="blocked",
            reason_code="current_review_proof_plan_unreadable",
            message=f"Current review proof origin plan is unreadable: {exc}",
            plan_path=resolved_plan_path,
            review_path=None,
            target=None,
        )

    status_lines = extract_status_lines(plan_lines)
    if len(status_lines) == 1:
        status_norm = " ".join(status_lines[0][1].replace("`", "").split()).lower()
        if status_norm in _CURRENT_REVIEW_PROOF_TERMINAL_HISTORY_STATUSES:
            return _current_review_proof_result(
                state="not_current",
                reason_code=None,
                message=(
                    "Terminal immutable plan history remains compatibility-readable and does not "
                    "supply a fresh current-review proof."
                ),
                plan_path=resolved_plan_path,
                review_path=None,
                target=None,
            )

    live_refs = extract_live_review_artifact_refs(plan_lines)
    if not live_refs:
        return _current_review_proof_result(
            state="planned",
            reason_code=None,
            message="No live review artifact is materialized for this plan yet.",
            plan_path=resolved_plan_path,
            review_path=None,
            target=None,
        )
    if len(live_refs) != 1:
        return _current_review_proof_result(
            state="blocked",
            reason_code="current_review_proof_review_route_ambiguous",
            message="Current review proof requires exactly one live review artifact route.",
            plan_path=resolved_plan_path,
            review_path=None,
            target=None,
        )

    _review_line, review_ref = live_refs[0]
    review_path = (resolved_root / review_ref).resolve()
    try:
        review_path.relative_to(resolved_root)
    except ValueError:
        return _current_review_proof_result(
            state="blocked",
            reason_code="current_review_proof_review_outside_project_root",
            message="Current review proof artifact must resolve inside the caller project root.",
            plan_path=resolved_plan_path,
            review_path=review_path,
            target=None,
        )
    if not review_path.is_file():
        return _current_review_proof_result(
            state="planned",
            reason_code=None,
            message="Live review artifact is declared but not materialized yet.",
            plan_path=resolved_plan_path,
            review_path=review_path,
            target=None,
        )
    try:
        review_bytes = review_path.read_bytes()
        review_lines = review_bytes.decode("utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        return _current_review_proof_result(
            state="blocked",
            reason_code="current_review_proof_review_unreadable",
            message=f"Current review proof artifact is unreadable: {exc}",
            plan_path=resolved_plan_path,
            review_path=review_path,
            target=None,
        )

    target_values = review_header_metadata.header_values(review_lines, "target")
    target_value = target_values[0][1] if len(target_values) == 1 else None
    selection = select_plan_risk_lane_snapshot(resolved_plan_path)
    compact_snapshot = selection.payload.get("target_snapshot") if selection.payload is not None else None
    current_claim = (
        any(_current_review_claim_shaped(value) for _line, value in target_values)
        or _current_review_claim_shaped(compact_snapshot)
        or _selected_support_has_current_claim(project_root=resolved_root, selection=selection)
    )
    if not current_claim:
        return _current_review_proof_result(
            state="not_current",
            reason_code=None,
            message="Live review does not carry an authoritative current-bundle claim.",
            plan_path=resolved_plan_path,
            review_path=review_path,
            target=target_value,
        )

    if len(target_values) != 1:
        return _current_review_proof_result(
            state="blocked",
            reason_code="current_review_proof_target_ambiguous",
            message="A current review proof requires exactly one top-level `**Target:**` carrier.",
            plan_path=resolved_plan_path,
            review_path=review_path,
            target=None,
        )
    bundle_sha, target_error = _exact_current_review_target(target_value)
    if target_error is not None:
        return _current_review_proof_result(
            state="blocked",
            reason_code="current_review_proof_target_invalid",
            message=target_error,
            plan_path=resolved_plan_path,
            review_path=review_path,
            target=target_value,
        )
    assert bundle_sha is not None

    if selection.error_code or selection.payload is None or selection.snapshot is None:
        return _current_review_proof_result(
            state="blocked",
            reason_code=selection.error_code or "missing_plan_resident_risk_lane",
            message=selection.message or "Current review proof requires one selected plan-resident risk-lane receipt.",
            plan_path=resolved_plan_path,
            review_path=review_path,
            target=target_value,
        )
    compact, compact_error = _exact_current_compact_snapshot(selection.payload.get("target_snapshot"))
    if compact_error is not None:
        return _current_review_proof_result(
            state="blocked",
            reason_code="current_review_proof_compact_snapshot_invalid",
            message=compact_error,
            plan_path=resolved_plan_path,
            review_path=review_path,
            target=target_value,
        )
    expected_target = f"{CURRENT_BUNDLE_TARGET} bundle_sha256={bundle_sha}"
    if compact is None or compact["bundle_sha256"] != bundle_sha or selection.snapshot != expected_target:
        return _current_review_proof_result(
            state="blocked",
            reason_code="current_review_proof_projection_mismatch",
            message="Current review Target and compact risk-lane target_snapshot must be exact equal projections.",
            plan_path=resolved_plan_path,
            review_path=review_path,
            target=target_value,
        )

    support_diagnostics = preflight_selected_risk_lane_support(
        resolved_plan_path,
        selection,
        project_root=resolved_root,
    )
    if support_diagnostics:
        current_proof_diagnostic = next(
            (
                diagnostic
                for diagnostic in support_diagnostics
                if diagnostic.code.startswith("current_review_proof_")
            ),
            None,
        )
        return _current_review_proof_result(
            state="blocked",
            reason_code=(
                current_proof_diagnostic.code
                if current_proof_diagnostic is not None
                else "current_review_proof_support_invalid"
            ),
            message=(
                current_proof_diagnostic.message
                if current_proof_diagnostic is not None
                else "Immutable selected risk-lane support did not pass canonical preflight."
            ),
            plan_path=resolved_plan_path,
            review_path=review_path,
            target=target_value,
            diagnostics=tuple(
                diagnostic
                for diagnostic in support_diagnostics
                if current_proof_diagnostic is None or diagnostic.code != current_proof_diagnostic.code
            ),
        )

    support_ref = _payload_string(selection.payload, "full_payload_ref")
    support_path = _resolve_repo_relative_support_ref(resolved_root, support_ref or "")
    if support_ref is None or support_path is None:
        # The support preflight above normally owns this condition.  Retain a
        # defensive fail-closed guard so this authority never dereferences an
        # unvalidated value if its lower-level contract changes.
        return _current_review_proof_result(
            state="blocked",
            reason_code="current_review_proof_support_invalid",
            message="Immutable selected risk-lane support path is unavailable after preflight.",
            plan_path=resolved_plan_path,
            review_path=review_path,
            target=target_value,
        )
    try:
        support_payload = json.loads(support_path.read_text(encoding="utf-8"))
        support_snapshot = validate_snapshot_payload(
            support_payload.get("target_snapshot") if isinstance(support_payload, dict) else None
        )
        producer_snapshot = build_current_bundle_snapshot(resolved_plan_path, project_root=resolved_root)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, SnapshotError) as exc:
        return _current_review_proof_result(
            state="blocked",
            reason_code="current_review_proof_producer_or_support_unavailable",
            message=f"Current review proof cannot read validated support/producer bytes: {exc}",
            plan_path=resolved_plan_path,
            review_path=review_path,
            target=target_value,
        )

    if support_snapshot != producer_snapshot:
        return _current_review_proof_result(
            state="blocked",
            reason_code="current_review_proof_producer_mismatch",
            message="Immutable support target_snapshot must exactly equal fresh canonical producer output.",
            plan_path=resolved_plan_path,
            review_path=review_path,
            target=target_value,
        )
    if producer_snapshot.get("target") != expected_target or producer_snapshot.get("target_snapshot") != compact:
        return _current_review_proof_result(
            state="blocked",
            reason_code="current_review_proof_projection_mismatch",
            message="Fresh producer Target and compact target_snapshot disagree with the live current review proof.",
            plan_path=resolved_plan_path,
            review_path=review_path,
            target=target_value,
        )
    try:
        if review_path.read_bytes() != review_bytes:
            return _current_review_proof_result(
                state="blocked",
                reason_code="current_review_proof_input_changed",
                message="Live review artifact changed during current-proof preflight; rerun on stable bytes.",
                plan_path=resolved_plan_path,
                review_path=review_path,
                target=target_value,
            )
    except OSError as exc:
        return _current_review_proof_result(
            state="blocked",
            reason_code="current_review_proof_input_changed",
            message=f"Live review artifact became unreadable during current-proof preflight: {exc}",
            plan_path=resolved_plan_path,
            review_path=review_path,
            target=target_value,
        )
    return _current_review_proof_result(
        state="current_green",
        reason_code=None,
        message="Live current review proof exactly matches compact support and fresh producer bytes.",
        plan_path=resolved_plan_path,
        review_path=review_path,
        target=target_value,
    )


def validate_required_manager_mode(
    path: Path,
    plan_meta_obj: dict,
    plan_meta_line: int | None,
) -> list[Finding]:
    findings: list[Finding] = []
    required_manager_mode = plan_meta_obj.get("required_manager_mode")
    if "required_manager_mode" not in plan_meta_obj:
        severity = "ERROR" if is_current_plan(path) else "WARN"
        findings.append(
            Finding(
                path,
                plan_meta_line or 1,
                severity,
                "plan_meta.required_manager_mode is missing; use one of: "
                + ", ".join(sorted(ALLOWED_REQUIRED_MANAGER_MODES))
                + ".",
            )
        )
    elif (
        not isinstance(required_manager_mode, str)
        or required_manager_mode not in ALLOWED_REQUIRED_MANAGER_MODES
    ):
        findings.append(
            Finding(
                path,
                plan_meta_line or 1,
                "ERROR",
                "plan_meta.required_manager_mode must be one of: "
                + ", ".join(sorted(ALLOWED_REQUIRED_MANAGER_MODES))
                + ".",
            )
        )
    return findings


def validate_plan_meta(path: Path, lines: list[str]) -> tuple[list[Finding], int | None, dict | None]:
    cardinality_error = _top_level_plan_meta_cardinality_error(lines)
    if cardinality_error is not None:
        reason_code, line = cardinality_error
        return [
            Finding(
                path,
                line,
                "ERROR",
                (
                    "plan_meta_carrier_ambiguous: expected at most one individually valid "
                    "duplicate-key-safe root plan_meta JSON carrier in each actual top-level "
                    "## Meta host."
                    if reason_code == "plan_meta_carrier_ambiguous"
                    else "meta_section_ambiguous: expected at most one individually valid root "
                    "plan_meta JSON carrier across actual top-level ## Meta hosts."
                ),
            )
        ], None, None

    findings: list[Finding] = []
    blocks = extract_json_code_blocks(lines)
    if not is_meta_required(path):
        for start_line, text in blocks:
            if "plan_meta" not in text:
                continue
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                continue
            historical_meta = parsed.get("plan_meta") if isinstance(parsed, dict) else None
            if isinstance(historical_meta, dict):
                findings.extend(validate_required_manager_mode(path, historical_meta, start_line))
                return findings, start_line, historical_meta
        return findings, None, None

    plan_meta_obj: dict | None = None
    plan_meta_line: int | None = None

    for start_line, text in blocks:
        if "plan_meta" not in text:
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as e:
            findings.append(
                Finding(
                    path,
                    start_line,
                    "ERROR",
                    f"Invalid JSON in plan_meta block: {e.msg} (pos {e.pos}).",
                )
            )
            return findings, None, None

        if isinstance(parsed, dict) and isinstance(parsed.get("plan_meta"), dict):
            plan_meta_obj = parsed["plan_meta"]
            plan_meta_line = start_line
            break

    if plan_meta_obj is None:
        findings.append(
            Finding(
                path,
                1,
                "ERROR",
                "Missing required plan_meta JSON block (```json ... plan_meta ... ```).",
            )
        )
        return findings, None, None

    cluster = plan_meta_obj.get("cluster")
    if not isinstance(cluster, str) or not cluster.strip() or cluster.strip().upper() == "UNCONFIRMED":
        findings.append(
            Finding(
                path,
                plan_meta_line or 1,
                "ERROR",
                "plan_meta.cluster must be a non-empty value (not UNCONFIRMED).",
            )
        )
        return findings, plan_meta_line, plan_meta_obj

    cluster_value = cluster.strip()
    if cluster_value != cluster_value.lower():
        findings.append(
            Finding(
                path,
                plan_meta_line or 1,
                "ERROR",
                f"plan_meta.cluster must be lower-case (got {cluster_value!r}).",
            )
        )

    if cluster_value in DEPRECATED_CLUSTER_ALIASES:
        canonical = DEPRECATED_CLUSTER_ALIASES[cluster_value]
        findings.append(
            Finding(
                path,
                plan_meta_line or 1,
                "ERROR",
                f"plan_meta.cluster {cluster_value!r} is deprecated; use {canonical!r}.",
            )
        )
    elif cluster_value not in ALLOWED_CLUSTERS:
        findings.append(
            Finding(
                path,
                plan_meta_line or 1,
                "ERROR",
                f"plan_meta.cluster must be one of: {', '.join(sorted(ALLOWED_CLUSTERS))}.",
            )
        )

    if "clusters" in plan_meta_obj:
        findings.append(
            Finding(
                path,
                plan_meta_line or 1,
                "ERROR",
                "plan_meta.clusters is deprecated; use plan_meta.tags instead.",
            )
        )

    tags = plan_meta_obj.get("tags")
    if tags is None:
        tags = []
    if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
        findings.append(
            Finding(
                path,
                plan_meta_line or 1,
                "ERROR",
                "plan_meta.tags must be a JSON array of strings (e.g. [\"ui\"]).",
            )
        )

    findings.extend(validate_required_manager_mode(path, plan_meta_obj, plan_meta_line))

    phase_overlay = plan_meta_obj.get("phase_overlay")
    phase_state = plan_meta_obj.get("phase_state")
    phase_overlay_value: str | None = None
    if phase_overlay is not None:
        if not isinstance(phase_overlay, str) or not phase_overlay.strip():
            findings.append(
                Finding(
                    path,
                    plan_meta_line or 1,
                    "ERROR",
                    "plan_meta.phase_overlay must be a non-empty string or null.",
                )
            )
        else:
            phase_overlay_value = phase_overlay.strip().lower()
            if phase_overlay_value != phase_overlay.strip():
                findings.append(
                    Finding(
                        path,
                        plan_meta_line or 1,
                        "ERROR",
                        f"plan_meta.phase_overlay must be lower-case (got {phase_overlay!r}).",
                    )
                )
            elif phase_overlay_value not in ALLOWED_PHASE_OVERLAYS:
                findings.append(
                    Finding(
                        path,
                        plan_meta_line or 1,
                        "ERROR",
                        f"plan_meta.phase_overlay must be one of: {', '.join(sorted(ALLOWED_PHASE_OVERLAYS))}.",
                    )
                )

    if phase_state is not None:
        if not isinstance(phase_state, str) or not phase_state.strip():
            findings.append(
                Finding(
                    path,
                    plan_meta_line or 1,
                    "ERROR",
                    "plan_meta.phase_state must be a non-empty string or null.",
                )
            )
        elif phase_overlay_value is None:
            findings.append(
                Finding(
                    path,
                    plan_meta_line or 1,
                    "ERROR",
                    "plan_meta.phase_state is only allowed together with plan_meta.phase_overlay.",
                )
            )
        else:
            phase_state_value = phase_state.strip().lower()
            if phase_state_value != phase_state.strip():
                findings.append(
                    Finding(
                        path,
                        plan_meta_line or 1,
                        "ERROR",
                        f"plan_meta.phase_state must be lower-case (got {phase_state!r}).",
                    )
                )
            else:
                allowed_states = PHASE_OVERLAY_STATES.get(phase_overlay_value, frozenset())
                if phase_state_value not in allowed_states:
                    findings.append(
                        Finding(
                            path,
                            plan_meta_line or 1,
                            "ERROR",
                            f"plan_meta.phase_state for {phase_overlay_value!r} must be one of: {', '.join(sorted(allowed_states))}.",
                        )
                    )
    elif phase_overlay_value is not None:
        findings.append(
            Finding(
                path,
                plan_meta_line or 1,
                "ERROR",
                "plan_meta.phase_overlay requires plan_meta.phase_state.",
            )
        )

    depends_on = plan_meta_obj.get("depends_on")
    if depends_on is None:
        depends_on = []
    if not isinstance(depends_on, list) or any(not isinstance(dep, str) for dep in depends_on):
        findings.append(
            Finding(
                path,
                plan_meta_line or 1,
                "ERROR",
                "plan_meta.depends_on must be a JSON array of strings (plan paths).",
            )
        )

    parent = plan_meta_obj.get("parent")
    if parent is not None:
        if not isinstance(parent, str) or not is_repo_relative_plan_path(parent):
            findings.append(
                Finding(
                    path,
                    plan_meta_line or 1,
                    "ERROR",
                    "plan_meta.parent must be a repo-relative plan path like `docs/plans/...md` or null.",
                )
            )

    next_plans = plan_meta_obj.get("next_plans")
    if next_plans is not None:
        if not isinstance(next_plans, list):
            findings.append(
                Finding(
                    path,
                    plan_meta_line or 1,
                    "ERROR",
                    "plan_meta.next_plans must be a JSON array of repo-relative plan paths.",
                )
            )
        else:
            if len(next_plans) > 3:
                findings.append(
                    Finding(
                        path,
                        plan_meta_line or 1,
                        "ERROR",
                        "plan_meta.next_plans is bounded to 0..3 direct next slices.",
                    )
                )
            normalized_next_plans: list[str] = []
            for idx, item in enumerate(next_plans, start=1):
                if not isinstance(item, str) or not is_repo_relative_plan_path(item):
                    findings.append(
                        Finding(
                            path,
                            plan_meta_line or 1,
                            "ERROR",
                            f"plan_meta.next_plans[{idx}] must be a repo-relative plan path like `docs/plans/...md`.",
                        )
                    )
                    continue
                normalized_next_plans.append(item.strip())
            if len(set(normalized_next_plans)) != len(normalized_next_plans):
                findings.append(
                    Finding(
                        path,
                        plan_meta_line or 1,
                        "ERROR",
                        "plan_meta.next_plans must not contain duplicate plan paths.",
                    )
                )

    schema_class, _ = classify_plan_schema_version(path, lines)
    followups_out = plan_meta_obj.get("followups_out")
    if schema_class == "v2":
        if "followups_out" in plan_meta_obj:
            findings.append(
                Finding(
                    path,
                    plan_meta_line or 1,
                    "ERROR",
                    "plan.v2 forbids plan_meta.followups_out; deferred authority lives only in docs/followups/*.md.",
                )
            )
    elif followups_out is not None and not isinstance(followups_out, list):
        findings.append(
            Finding(
                path,
                plan_meta_line or 1,
                "ERROR",
                "plan_meta.followups_out must be a JSON array.",
            )
        )
    elif isinstance(followups_out, list):
        for idx, item in enumerate(followups_out, start=1):
            if not isinstance(item, dict):
                findings.append(
                    Finding(
                        path,
                        plan_meta_line or 1,
                        "ERROR",
                        f"plan_meta.followups_out[{idx}] must be an object.",
                    )
                )
                continue

            item_cluster = item.get("cluster")
            if not isinstance(item_cluster, str) or not item_cluster.strip():
                findings.append(
                    Finding(
                        path,
                        plan_meta_line or 1,
                        "ERROR",
                        f"plan_meta.followups_out[{idx}].cluster must be a non-empty string.",
                    )
                )
                continue

            item_cluster_value = item_cluster.strip()
            if item_cluster_value != item_cluster_value.lower():
                findings.append(
                    Finding(
                        path,
                        plan_meta_line or 1,
                        "ERROR",
                        f"plan_meta.followups_out[{idx}].cluster must be lower-case (got {item_cluster_value!r}).",
                    )
                )

            if item_cluster_value in DEPRECATED_CLUSTER_ALIASES:
                canonical = DEPRECATED_CLUSTER_ALIASES[item_cluster_value]
                findings.append(
                    Finding(
                        path,
                        plan_meta_line or 1,
                        "ERROR",
                        f"plan_meta.followups_out[{idx}].cluster {item_cluster_value!r} is deprecated; use {canonical!r}.",
                    )
                )
            elif item_cluster_value not in ALLOWED_CLUSTERS:
                findings.append(
                    Finding(
                        path,
                        plan_meta_line or 1,
                        "ERROR",
                        f"plan_meta.followups_out[{idx}].cluster must be one of: {', '.join(sorted(ALLOWED_CLUSTERS))}.",
                    )
                )

            summary = item.get("summary")
            if summary is not None and not isinstance(summary, str):
                findings.append(
                    Finding(
                        path,
                        plan_meta_line or 1,
                        "ERROR",
                        f"plan_meta.followups_out[{idx}].summary must be a string (or null).",
                    )
                )

    canon_updates = plan_meta_obj.get("canon_updates")
    if canon_updates is None:
        canon_updates = []
    if not isinstance(canon_updates, list):
        findings.append(
            Finding(
                path,
                plan_meta_line or 1,
                "ERROR",
                "plan_meta.canon_updates must be a JSON array.",
            )
        )

    return findings, plan_meta_line, plan_meta_obj


def strict_plan_meta_json(lines: Sequence[str]) -> plan_status_oracle.StrictPlanMetaJsonResult:
    """Expose the authority-only strict Meta reader at the lint contract anchor.

    Generic plan_meta readers remain intentionally legacy-compatible.  This wrapper
    is only for the post-cutover machine-authority admission carrier.
    """

    return plan_status_oracle.strict_plan_meta_json("\n".join(lines))


def _top_level_plan_meta_cardinality_error(lines: Sequence[str]) -> tuple[str, int] | None:
    """Return the B20 valid-carrier cardinality failure, if any.

    The generic lint path deliberately reuses the shared duplicate-key-safe
    heading/fence reader.  It adds only the Q10 valid-carrier cardinality gate;
    it does not alter authority-reader or malformed-carrier semantics.
    """

    heading_indices = plan_status_oracle._machine_authority_top_level_heading_indices(lines)
    valid_host_lines: list[int] = []
    for start in heading_indices:
        if not plan_status_oracle._TOP_LEVEL_META_HEADING_RE.fullmatch(lines[start]):
            continue
        end = next((index for index in heading_indices if index > start), len(lines))
        strict = strict_plan_meta_json(lines[start:end])
        if strict.state == "valid":
            valid_host_lines.append(start + (strict.line_no or 1))
        elif strict.reason_code == "plan_meta_carrier_ambiguous" and strict.line_no is not None:
            # A non-null line means the strict reader found at least one valid
            # root carrier; its ambiguous state therefore proves two or more.
            return "plan_meta_carrier_ambiguous", start + strict.line_no
    if len(valid_host_lines) > 1:
        return "meta_section_ambiguous", valid_host_lines[1]
    return None


def validate_machine_authority_decision(path: Path, lines: Sequence[str]) -> list[Finding]:
    """Fail closed only for the new machine-authority admission contract."""

    strict_meta = strict_plan_meta_json(lines)
    readback = plan_status_oracle.machine_authority_decision_readback(
        path,
        plan_text="\n".join(lines),
    )
    # Initial Architect drafts may still be deciding applicability.  The
    # carrier becomes mandatory at the first executable downstream handoff.
    if readback.state == "missing" and not readback.route_guard_required:
        return []
    if readback.state not in {"invalid", "missing"}:
        return []
    line = strict_meta.line_no or 1
    return [
        Finding(
            path,
            line,
            "ERROR",
            "Machine-authority admission failed closed: "
            f"{readback.reason_code}: {readback.reason}.",
        )
    ]


def validate_manager_mode_handoff_command(
    path: Path,
    lines: list[str],
    plan_meta_obj: dict | None,
) -> list[Finding]:
    """Keep only the canonical Manager execution handoff aligned with metadata."""

    if not isinstance(plan_meta_obj, dict):
        return []
    required_mode = plan_meta_obj.get("required_manager_mode")
    if required_mode not in {"manager-collab", "manager-custom-pipeline"}:
        return []

    section = slice_h2_section(lines, VERIFICATION_HANDOFF_HEADING_RE)
    if not section:
        return []
    section_line, body = section
    findings: list[Finding] = []
    for offset, line in enumerate(body, start=1):
        if not re.match(r"^\s*-\s*Command\s*:", line, re.IGNORECASE):
            continue
        command = line.split(":", 1)[1]
        command_modes: set[str] = set()
        if re.search(r"\bplanveyor_manager_custom_pipeline(?:_tui|_cmd)?\b", command):
            command_modes.add("manager-custom-pipeline")
        # Check custom first because its binary starts with `planveyor_manager`.
        scrubbed = re.sub(r"\bplanveyor_manager_custom_pipeline(?:_tui|_cmd)?\b", "", command)
        if re.search(r"\bplanveyor_manager(?:_collab(?:_tui|_cmd)?)?\b", scrubbed):
            command_modes.add("manager-collab")
        if re.search(
            r"\bMANAGER_CMD=\S+\s+planveyor_manager(?:_custom_pipeline|_collab)?(?:_tui|_cmd)?\b",
            command,
        ):
            findings.append(
                Finding(
                    path,
                    section_line + offset,
                    "ERROR",
                    "Malformed Manager handoff command: do not concatenate "
                    "`MANAGER_CMD=...` with a Manager wrapper binary.",
                )
            )
        for command_mode in sorted(command_modes):
            if command_mode != required_mode:
                findings.append(
                    Finding(
                        path,
                        section_line + offset,
                        "ERROR",
                        "Canonical Manager handoff command contradicts "
                        f"plan_meta.required_manager_mode={required_mode!r}: "
                        f"command selects {command_mode!r}.",
                    )
                )
    return findings


def slice_h2_section(lines: list[str], heading_re: re.Pattern[str]) -> tuple[int, list[str]] | None:
    """Return (heading_line_no, section_body_lines) for a `## ...` section (body excludes the heading line)."""
    start_idx: int | None = None
    in_fence = False
    for idx, line in enumerate(lines):
        if in_fence:
            if FENCE_END_RE.match(line):
                in_fence = False
            continue
        if FENCE_START_RE.match(line):
            in_fence = True
            continue
        if heading_re.match(line):
            start_idx = idx
            break
    if start_idx is None:
        return None

    end_idx = len(lines)
    in_fence = False
    for idx in range(start_idx + 1, len(lines)):
        line = lines[idx]
        if in_fence:
            if FENCE_END_RE.match(line):
                in_fence = False
            continue
        if FENCE_START_RE.match(line):
            in_fence = True
            continue
        if H2_HEADING_RE.match(line):
            end_idx = idx
            break
    return (start_idx + 1, lines[start_idx + 1 : end_idx])


def split_markdown_table_row(line: str) -> list[str] | None:
    stripped = line.strip()
    if not stripped.startswith("|") or "|" not in stripped[1:]:
        return None
    return [cell.strip() for cell in stripped.strip("|").split("|")]


def normalize_table_cell(value: str) -> str:
    return " ".join(value.replace("`", "").split()).lower()


def clean_markdown_table_cell(value: str) -> str:
    cleaned = value.strip()
    if cleaned.startswith("`") and cleaned.endswith("`") and len(cleaned) >= 2:
        return cleaned[1:-1].strip()
    return cleaned


def planning_contour_token(value: object) -> str:
    raw = str(value).strip()
    if raw.startswith("`") and raw.endswith("`") and len(raw) >= 2:
        raw = raw[1:-1].strip()
    return raw.lower()


def planning_contour_leading_token(value: object) -> str:
    raw = str(value).strip().strip("`").strip()
    match = re.match(r"^[A-Za-z0-9_/-]+", raw)
    if not match:
        return ""
    return match.group(0).strip().lower()


def object_field_is_blank(value: object) -> bool:
    return value is None or not str(value).strip()


def planning_contour_invalid_enum_fields(
    carrier: Mapping[str, object],
    field_to_vocab_key: dict[str, str],
) -> list[str]:
    invalid: list[str] = []
    for field, vocab_key in field_to_vocab_key.items():
        allowed = PLANNING_CONTOUR_ENUM_VALUES.get(vocab_key)
        token = planning_contour_token(carrier.get(field, ""))
        if not allowed or token not in allowed:
            invalid.append(field)
    return invalid


def clean_planning_contour_ref(value: object) -> str:
    cleaned = str(value).strip()
    if cleaned.startswith("`") and cleaned.endswith("`") and len(cleaned) >= 2:
        cleaned = cleaned[1:-1].strip()
    return cleaned.strip("`").rstrip(".,;")


def split_planning_contour_route_ref(value: object) -> tuple[str, str]:
    cleaned = clean_planning_contour_ref(value)
    if "#" not in cleaned:
        return cleaned, ""
    path_part, anchor = cleaned.split("#", 1)
    return path_part.strip(), anchor.strip().lower().replace("_", "-")


def planning_contour_explicit_na_with_reason(value: object) -> bool:
    return bool(EXPLICIT_NA_WITH_REASON_RE.search(str(value)))


def planning_contour_source_route_required_fields(fields: Mapping[str, str]) -> tuple[str, ...]:
    accepted_route = planning_contour_token(fields.get("accepted_route", ""))
    accepted_route_prefix = planning_contour_leading_token(fields.get("accepted_route", ""))
    if (
        accepted_route in PLANNING_CONTOUR_FIXTURE_BACKED_SOURCE_ROUTES
        or accepted_route_prefix in PLANNING_CONTOUR_FIXTURE_BACKED_SOURCE_ROUTES
    ):
        return PLANNING_CONTOUR_SOURCE_ROUTE_ANALYSIS_FIELDS + PLANNING_CONTOUR_SOURCE_ROUTE_REQUIRED_FIELDS
    return PLANNING_CONTOUR_SOURCE_ROUTE_REQUIRED_FIELDS


def planning_contour_schema_finding(
    path: Path,
    line: int | None,
    severity: str,
    message: str,
) -> Finding:
    prefix = PLANNING_CONTOUR_SCHEMA_ERROR_PREFIX if severity == "ERROR" else PLANNING_CONTOUR_SCHEMA_WARNING_PREFIX
    return Finding(path, line or 1, severity, prefix + message)


def accepted_route_literal_fields_in_text(value: str) -> set[str]:
    return {match.group(1).lower() for match in ACCEPTED_ROUTE_LITERAL_FIELD_RE.finditer(value)}


def accepted_route_literal_paths_in_plan_meta(
    value: object,
    *,
    path_parts: tuple[str, ...] = (),
) -> list[tuple[str, ...]]:
    if isinstance(value, dict):
        results: list[tuple[str, ...]] = []
        for raw_key, child_value in value.items():
            if not isinstance(raw_key, str):
                continue
            key = raw_key.strip().lower()
            child_path = (*path_parts, key)
            if key in ACCEPTED_ROUTE_LITERAL_FIELDS and (
                not path_parts or path_parts[0] != ACCEPTED_ROUTE_DERIVED_PROMOTED_FROM_KEY
            ):
                results.append(child_path)
                continue
            if path_parts and path_parts[0] == ACCEPTED_ROUTE_DERIVED_PROMOTED_FROM_KEY:
                continue
            results.extend(accepted_route_literal_paths_in_plan_meta(child_value, path_parts=child_path))
        return results
    if isinstance(value, list):
        results = []
        for idx, item in enumerate(value):
            results.extend(accepted_route_literal_paths_in_plan_meta(item, path_parts=(*path_parts, f"[{idx}]")))
        return results
    return []


def accepted_route_literal_paths_in_promoted_from(
    value: object,
    *,
    path_parts: tuple[str, ...] = (),
) -> list[tuple[str, ...]]:
    if isinstance(value, dict):
        results: list[tuple[str, ...]] = []
        for raw_key, child_value in value.items():
            if not isinstance(raw_key, str):
                continue
            key = raw_key.strip().lower()
            child_path = (*path_parts, key)
            if key in ACCEPTED_ROUTE_LITERAL_FIELDS or key in ACCEPTED_ROUTE_DERIVED_ACCEPTANCE_FIELDS:
                results.append(child_path)
            results.extend(accepted_route_literal_paths_in_promoted_from(child_value, path_parts=child_path))
        return results
    if isinstance(value, list):
        results = []
        for idx, item in enumerate(value):
            results.extend(accepted_route_literal_paths_in_promoted_from(item, path_parts=(*path_parts, f"[{idx}]")))
        return results
    return []


def promoted_from_authority_note(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    raw = value.get(ACCEPTED_ROUTE_DERIVED_AUTHORITY_NOTE_KEY)
    if not isinstance(raw, str):
        return None
    return raw.strip()


def requirement_slice_entries(value: str) -> list[tuple[str, str]]:
    matches = list(REQUIREMENT_SLICE_KIND_RE.finditer(value))
    entries: list[tuple[str, str]] = []
    for idx, match in enumerate(matches):
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(value)
        entries.append((match.group("value").strip().lower(), value[match.start() : end]))
    return entries


def validate_analysis_pack_requirement_slices(
    path: Path,
    lines: list[str],
) -> list[Finding]:
    findings: list[Finding] = []
    if path.name == "_template.md":
        return findings

    section = slice_h2_section(lines, ANALYSIS_PACK_HEADING_RE)
    if not section:
        return findings

    heading_line_no, body = section
    allowed = ", ".join(f"`{value}`" for value in sorted(PLANNING_CONTOUR_REQUIREMENT_SLICE_KINDS))
    for idx, line in enumerate(body):
        cells = split_markdown_table_row(line)
        if not cells or len(cells) < 2:
            continue

        field_name = normalize_table_cell(cells[0])
        if field_name != "requirement_slices":
            continue

        line_no = heading_line_no + idx + 1
        value = " | ".join(cells[1:])
        for slice_kind, entry in requirement_slice_entries(value):
            if slice_kind not in PLANNING_CONTOUR_REQUIREMENT_SLICE_KINDS:
                findings.append(
                    Finding(
                        path,
                        line_no,
                        "ERROR",
                        "`Analysis pack.requirement_slices.slice_kind` must use canonical value "
                        f"from `docs/_meta/plan_vocab.json` ({allowed}); found `{slice_kind}`.",
                    )
                )
                continue

            if slice_kind != "needs_analysis":
                continue

            missing: list[str] = []
            if not NEEDS_ANALYSIS_KEY_UNKNOWNS_RE.search(entry):
                missing.append("key_unknowns")
            if not NEEDS_ANALYSIS_TRIGGER_RE.search(entry):
                missing.append("trigger_for_promotion")
            if missing:
                findings.append(
                    Finding(
                        path,
                        line_no,
                        "ERROR",
                        "`needs_analysis` requirement slice must carry analysis package seed field(s): "
                        + ", ".join(f"`{field}`" for field in missing)
                        + ".",
                    )
                )
                continue

            queue_match = NEEDS_ANALYSIS_DEV_QUEUE_RE.search(entry)
            if queue_match:
                findings.append(
                    Finding(
                        path,
                        line_no,
                        "ERROR",
                        "`needs_analysis` requirement slice cannot be admitted as a dev/small-runner child "
                        f"from `requirement_slices` (`{queue_match.group(0)}`); promote it through a reviewed "
                        "analysis route first.",
                    )
                )

    return findings


def validate_analysis_pack_authority(
    path: Path,
    resolution: plan_status_oracle.AnalysisPackAuthorityResolution,
) -> list[Finding]:
    if path.name == "_template.md" or resolution.is_valid:
        return []
    truth_host = resolution.truth_host or f"{path.as_posix()}#Analysis-pack"
    message = (
        f"{plan_status_oracle.ANALYSIS_PACK_AUTHORITY_INVALID}:"
        f"{resolution.detail_category}; truth_host={truth_host}."
    )
    if resolution.detail_category == "ref_missing":
        pack_rel = f"docs/analysis_packs/{path.stem}.md"
        message += (
            " From `Planner finalize` on, an `analysis_wave` pack lives outside the plan: "
            f"move the `## Analysis pack` table into `{pack_rel}` under the same heading, "
            f"keep one plan row `analysis_pack_ref` = `{pack_rel}#Analysis-pack` and add "
            f"`{pack_rel}` to `code_draft_meta.targets` of "
            f"`docs/code_drafts/{path.stem}__code_draft.md` "
            "(see `docs/playbooks/analysis_wave.md`)."
        )
    return [Finding(path, 1, "ERROR", message)]


def validate_analysis_route_single_authority(
    path: Path,
    lines: list[str],
    plan_meta_obj: dict | None,
    plan_meta_line: int | None = None,
) -> list[Finding]:
    findings: list[Finding] = []
    if path.name == "_template.md":
        return findings
    if not is_analysis_route_single_authority_enforced(path):
        return findings

    if isinstance(plan_meta_obj, dict):
        promoted_from = plan_meta_obj.get(ACCEPTED_ROUTE_DERIVED_PROMOTED_FROM_KEY)
        promoted_from_paths = accepted_route_literal_paths_in_promoted_from(promoted_from)
        if promoted_from_paths and promoted_from_authority_note(promoted_from) != ACCEPTED_ROUTE_DERIVED_AUTHORITY_NOTE:
            dotted_paths = ", ".join(
                f"`{'.'.join(('plan_meta', ACCEPTED_ROUTE_DERIVED_PROMOTED_FROM_KEY, *literal_path)).replace('.[', '[')}`"
                for literal_path in promoted_from_paths
            )
            findings.append(
                Finding(
                    path,
                    plan_meta_line or 1,
                    "WARN",
                    "Analysis route single-authority warning: `plan_meta.promoted_from` contains "
                    f"derived route/admission field(s) {dotted_paths} but missing exact "
                    f"`plan_meta.promoted_from.authority_note={ACCEPTED_ROUTE_DERIVED_AUTHORITY_NOTE}`.",
                )
            )

    if not is_analysis_wave(plan_meta_obj):
        return findings

    for literal_path in accepted_route_literal_paths_in_plan_meta(plan_meta_obj):
        dotted_path = ".".join(("plan_meta", *literal_path)).replace(".[", "[")
        findings.append(
            Finding(
                path,
                plan_meta_line or 1,
                "ERROR",
                "Analysis route single-authority violation: "
                f"`{dotted_path}` duplicates writable accepted-route truth. Keep accepted route truth in "
                "`## Promoted route artifact`; use `plan_meta.promoted_from` only for derived target snapshots.",
            )
        )

    section = slice_h2_section(lines, ANALYSIS_PACK_HEADING_RE)
    if not section:
        return findings

    heading_line_no, body = section
    for idx, line in enumerate(body):
        cells = split_markdown_table_row(line)
        if not cells or len(cells) < 2:
            continue

        field_name = normalize_table_cell(cells[0])
        if field_name in {"field", "---"}:
            continue

        line_no = heading_line_no + idx + 1
        if field_name in ACCEPTED_ROUTE_LITERAL_FIELDS:
            findings.append(
                Finding(
                    path,
                    line_no,
                    "ERROR",
                    "`## Analysis pack` must not define literal accepted-route fields "
                    f"`{field_name}`. Keep accepted route truth in `## Promoted route artifact`.",
                )
            )
            continue

        if field_name != "promoted_route_refs":
            continue

        literal_fields = accepted_route_literal_fields_in_text(" | ".join(cells[1:]))
        if literal_fields:
            fields = ", ".join(f"`{field}`" for field in sorted(literal_fields))
            findings.append(
                Finding(
                    path,
                    line_no,
                    "ERROR",
                    "`analysis_pack.promoted_route_refs` must stay refs-only; found duplicated "
                    f"accepted-route literal field(s): {fields}. Put those fields only in "
                    "`## Promoted route artifact`.",
                )
            )

    return findings


def is_analysis_pack_completion_warning_enforced(path: Path) -> bool:
    return is_current_plan(path)


def analysis_pack_fields(
    lines: list[str],
) -> tuple[int, dict[str, str], dict[str, int]] | None:
    section = slice_h2_section(lines, ANALYSIS_PACK_HEADING_RE)
    if section is None:
        return None

    heading_line_no, body = section
    fields: dict[str, str] = {}
    line_by_field: dict[str, int] = {}
    for offset, line in enumerate(body, start=1):
        cells = split_markdown_table_row(line)
        if not cells or len(cells) < 2:
            continue
        field_name = normalize_table_cell(cells[0])
        if field_name in {"field", "---"} or set(field_name) <= {"-"}:
            continue
        fields[field_name] = clean_markdown_table_cell("|".join(cells[1:]))
        line_by_field[field_name] = heading_line_no + offset
    return heading_line_no, fields, line_by_field


def analysis_pack_value_is_placeholder(value: str) -> bool:
    stripped = clean_markdown_table_cell(value).strip()
    if not stripped:
        return True
    if is_placeholder_value(stripped):
        return True
    if is_explicit_na_value(stripped):
        return True
    if re.fullmatch(r"(?:none|no|nil|null|-+)", stripped.strip("`").strip(), re.IGNORECASE):
        return True
    return False


def bounded_no_relevant_hits(value: str) -> bool:
    if not NO_RELEVANT_HITS_RE.search(value):
        return False
    has_query = bool(re.search(r"\bquery\s*(?:=|:)", value, re.IGNORECASE))
    has_lane = bool(re.search(r"\blane\s*(?:=|:)", value, re.IGNORECASE))
    has_reason = bool(re.search(r"\b(?:reason|why)\s*(?:=|:)", value, re.IGNORECASE))
    return has_query and has_lane and has_reason


INSPECTED_SOURCE_LABEL_RE = re.compile(
    r"\b(?:opened\s*/\s*read|opened|read)"
    r"(?:\s+(?:(?:source|sources)(?:\s+(?:ref|refs|file|files))?|(?:ref|refs|file|files)))?\s*:",
    re.IGNORECASE,
)


def scope_refs_has_inspected_source(value: str) -> bool:
    for segment in re.split(r"[\n;]+", value):
        label = INSPECTED_SOURCE_LABEL_RE.search(segment)
        if label and REPO_RELATIVE_TARGET_RE.search(segment[label.end() :]):
            return True
    return False


def validate_analysis_pack_completion_source_floor(
    path: Path,
    lines: list[str],
    plan_meta_obj: dict | None,
) -> list[Finding]:
    if path.name == "_template.md":
        return []
    if not is_analysis_wave(plan_meta_obj):
        return []
    if not is_analysis_pack_completion_warning_enforced(path):
        return []

    parsed = analysis_pack_fields(lines)
    if parsed is None:
        return [
            Finding(
                path,
                1,
                "WARN",
                ANALYSIS_PACK_COMPLETION_WARNING_PREFIX
                + "`## Analysis pack` is missing; route completeness and source floor cannot be checked.",
            )
        ]

    heading_line_no, fields, line_by_field = parsed
    findings: list[Finding] = []
    route_value = fields.get("route_recommendation", "")
    route = planning_contour_leading_token(route_value)
    if route not in ANALYSIS_PACK_ROUTE_REQUIRED_FIELDS:
        findings.append(
            Finding(
                path,
                line_by_field.get("route_recommendation", heading_line_no),
                "WARN",
                ANALYSIS_PACK_COMPLETION_WARNING_PREFIX
                + "`route_recommendation` must name one primary route enum "
                f"({', '.join(ANALYSIS_PACK_ROUTE_REQUIRED_FIELDS)}).",
            )
        )
        return findings

    missing_or_placeholder = [
        field for field in ANALYSIS_PACK_ROUTE_REQUIRED_FIELDS[route] if analysis_pack_value_is_placeholder(fields.get(field, ""))
    ]
    if missing_or_placeholder:
        details = ", ".join(f"`{field}`" for field in missing_or_placeholder)
        findings.append(
            Finding(
                path,
                line_by_field.get(missing_or_placeholder[0], line_by_field.get("route_recommendation", heading_line_no)),
                "WARN",
                ANALYSIS_PACK_COMPLETION_WARNING_PREFIX
                + f"`{route}` pack is missing route-required non-placeholder field(s): {details}.",
            )
        )

    values_text = "\n".join(fields.values())
    no_hits_present = bool(NO_RELEVANT_HITS_RE.search(values_text))
    no_hits_bounded = any(bounded_no_relevant_hits(value) for value in fields.values())
    if no_hits_present and not no_hits_bounded:
        findings.append(
            Finding(
                path,
                heading_line_no,
                "WARN",
                ANALYSIS_PACK_COMPLETION_WARNING_PREFIX
                + "`NO RELEVANT HITS` must be bounded with query, lane and reason/why.",
            )
        )

    scope_refs = fields.get("scope_refs", "")
    has_source = scope_refs_has_inspected_source(scope_refs)
    if route != "reject":
        if not has_source and not no_hits_bounded:
            findings.append(
                Finding(
                    path,
                    line_by_field.get("scope_refs", heading_line_no),
                    "WARN",
                    ANALYSIS_PACK_COMPLETION_WARNING_PREFIX
                    + f"`{route}` pack must record concrete opened/read `scope_refs` or bounded `NO RELEVANT HITS`; "
                    "retrieval hits alone do not satisfy the source floor.",
                )
            )
    elif not has_source and not no_hits_bounded:
        findings.append(
            Finding(
                path,
                line_by_field.get("scope_refs", heading_line_no),
                "WARN",
                ANALYSIS_PACK_COMPLETION_WARNING_PREFIX
                + "`reject` pack should still record inspected source refs or bounded source-discovery `NO RELEVANT HITS`.",
            )
        )

    return findings


def is_analysis_route_lifecycle_enforced(path: Path) -> bool:
    return is_current_plan(path)


def validate_analysis_route_lifecycle_guard(
    path: Path,
    lines: list[str],
    plan_meta_obj: dict | None,
) -> list[Finding]:
    if path.name == "_template.md":
        return []
    if not is_analysis_wave(plan_meta_obj):
        return []
    if not is_analysis_route_lifecycle_enforced(path):
        return []

    lifecycle = plan_status_oracle.classify_analysis_route_lifecycle("\n".join(lines))
    if lifecycle.state in {"not_applicable", "ok"}:
        return []

    parsed_pack = analysis_pack_fields(lines)
    line_no = parsed_pack[0] if parsed_pack is not None else 1
    if lifecycle.state in {"architect_stop", "stale_needs_architect_review"}:
        return [
            Finding(
                path,
                line_no,
                "ERROR",
                ANALYSIS_ROUTE_LIFECYCLE_ERROR_PREFIX
                + f"{lifecycle.reason}; next_owner={lifecycle.next_owner or 'Architect'}.",
            )
        ]

    return [
        Finding(
            path,
            line_no,
            "WARN",
            ANALYSIS_ROUTE_LIFECYCLE_WARNING_PREFIX + lifecycle.reason + ".",
        )
    ]


def is_planning_contour_schema_hardening_enforced(path: Path) -> bool:
    return is_current_plan(path)


def promoted_route_artifact_fields(
    lines: list[str],
) -> tuple[int, dict[str, str], dict[str, int], bool] | None:
    section = slice_h2_section(lines, PROMOTED_ROUTE_ARTIFACT_HEADING_RE)
    if not section:
        return None

    heading_line_no, body = section
    fields: dict[str, str] = {}
    line_by_field: dict[str, int] = {}
    contains_na = False
    for offset, line in enumerate(body, start=1):
        stripped = line.strip().strip("`").strip()
        if stripped and stripped.lower().startswith("n/a"):
            contains_na = True

        cells = split_markdown_table_row(line)
        if not cells or len(cells) < 2:
            continue
        field_name = normalize_table_cell(cells[0])
        if field_name in {"field", "---"} or set(field_name) <= {"-"}:
            continue
        fields[field_name] = clean_markdown_table_cell("|".join(cells[1:]))
        line_by_field[field_name] = heading_line_no + offset

    return heading_line_no, fields, line_by_field, contains_na


def validate_planning_contour_source_route_artifact(
    path: Path,
    lines: list[str],
    plan_meta_obj: dict | None,
) -> list[Finding]:
    if not is_analysis_wave(plan_meta_obj):
        return []

    artifact = promoted_route_artifact_fields(lines)
    if artifact is None:
        return [
            planning_contour_schema_finding(
                path,
                1,
                "WARN",
                "`## Promoted route artifact` is missing on an analysis_wave plan; keep this warning-first until "
                "the accepted route is materialized.",
            )
        ]

    heading_line_no, fields, line_by_field, contains_na = artifact
    if contains_na and not fields:
        return [
            planning_contour_schema_finding(
                path,
                heading_line_no,
                "WARN",
                "`## Promoted route artifact` is `N/A`; source route readback cannot be schema-valid.",
            )
        ]
    if not fields:
        return [
            planning_contour_schema_finding(
                path,
                heading_line_no,
                "WARN",
                "`## Promoted route artifact` has no parseable table rows.",
            )
        ]

    required_fields = planning_contour_source_route_required_fields(fields)
    missing = [field for field in required_fields if not fields.get(field)]
    invalid = planning_contour_invalid_enum_fields(fields, PLANNING_CONTOUR_SOURCE_ROUTE_ENUM_FIELDS)
    accepted_route = planning_contour_token(fields.get("accepted_route", ""))
    accepted_route_prefix = planning_contour_leading_token(fields.get("accepted_route", ""))
    if missing or invalid:
        severity = (
            "ERROR"
            if accepted_route in PLANNING_CONTOUR_FIXTURE_BACKED_SOURCE_ROUTES
            or accepted_route_prefix in PLANNING_CONTOUR_FIXTURE_BACKED_SOURCE_ROUTES
            else "WARN"
        )
        line_no = line_by_field.get("accepted_route", heading_line_no)
        details: list[str] = []
        if missing:
            details.append("missing required field(s): " + ", ".join(missing))
        if invalid:
            details.append("invalid enum field(s): " + ", ".join(invalid))
        route_note = ""
        if severity == "WARN":
            route_note = " Non-decomposition/V3-dependent route discrimination remains warning-first."
        return [
            planning_contour_schema_finding(
                path,
                line_no,
                severity,
                "`## Promoted route artifact` is not schema-valid: " + "; ".join(details) + "." + route_note,
            )
        ]

    findings: list[Finding] = []
    non_executable_issues = plan_status_oracle.non_executable_source_route_carrier_issues(
        fields,
        source_route_state="valid",
    )
    for issue in non_executable_issues:
        findings.append(
            planning_contour_schema_finding(
                path,
                line_by_field.get(issue.field, heading_line_no),
                issue.severity,
                "`## Promoted route artifact` non-executable carrier is not concrete: "
                + issue.message,
            )
        )

    if accepted_route not in PLANNING_CONTOUR_FIXTURE_BACKED_SOURCE_ROUTES:
        return findings

    repo_root = repo_root_for_plan_path(path)
    promoted_artifact_ref = clean_planning_contour_ref(fields.get("promoted_artifact_ref", ""))
    line_no = line_by_field.get("promoted_artifact_ref", heading_line_no)
    if not is_repo_relative_plan_path(promoted_artifact_ref):
        findings.append(
            planning_contour_schema_finding(
                path,
                line_no,
                "ERROR",
                "`## Promoted route artifact.promoted_artifact_ref` must be a repo-relative "
                "`docs/plans/*.md` file path for fixture-backed routes.",
            )
        )
        return findings

    promoted_artifact_path = repo_root / promoted_artifact_ref
    if not promoted_artifact_path.is_file():
        findings.append(
            planning_contour_schema_finding(
                path,
                line_no,
                "ERROR",
                "`## Promoted route artifact.promoted_artifact_ref` target does not exist: "
                f"`{promoted_artifact_ref}`.",
            )
        )

    return findings


def validate_promoted_from_source_route_parity(
    path: Path,
    promoted_from: dict[str, object] | None,
    plan_meta_line: int | None,
) -> list[Finding]:
    if not isinstance(promoted_from, dict):
        return []
    if planning_contour_token(promoted_from.get("accepted_route", "")) != "decomposition_wave":
        return []

    repo_root = repo_root_for_plan_path(path)
    current_rel_path = repo_relative_display(path, repo_root)
    source_plan = clean_planning_contour_ref(promoted_from.get("source_plan", ""))
    source_route_path, source_route_anchor = split_planning_contour_route_ref(promoted_from.get("source_route_ref", ""))

    def finding(message: str) -> Finding:
        return planning_contour_schema_finding(
            path,
            plan_meta_line,
            "ERROR",
            "`plan_meta.promoted_from` source route provenance is not valid: " + message,
        )

    findings: list[Finding] = []
    if not is_repo_relative_plan_path(source_plan):
        if planning_contour_explicit_na_with_reason(source_plan):
            return findings
        findings.append(finding("`source_plan` must be a repo-relative `docs/plans/*.md` path."))
        return findings

    if source_route_path != source_plan or source_route_anchor != PLANNING_CONTOUR_PROMOTED_ROUTE_ARTIFACT_ANCHOR:
        findings.append(
            finding(
                "`source_route_ref` must point to the same source plan `## Promoted route artifact` "
                f"(expected `{source_plan}#{PLANNING_CONTOUR_PROMOTED_ROUTE_ARTIFACT_ANCHOR}`)."
            )
        )

    source_path = repo_root / source_plan
    if not source_path.is_file():
        findings.append(finding(f"`source_plan` does not exist: `{source_plan}`."))
        return findings

    try:
        source_lines = read_text(source_path)
    except (OSError, UnicodeDecodeError) as exc:
        findings.append(finding(f"`source_plan` cannot be read: `{source_plan}` ({exc})."))
        return findings

    source_meta = plan_status_oracle.parse_plan_meta("\n".join(source_lines))
    if not is_analysis_wave(source_meta):
        findings.append(finding(f"`source_plan` must be an `analysis_wave` plan: `{source_plan}`."))

    source_artifact = promoted_route_artifact_fields(source_lines)
    if source_artifact is None:
        findings.append(finding(f"`source_plan` has no `## Promoted route artifact`: `{source_plan}`."))
        return findings

    _heading_line_no, source_fields, _line_by_field, contains_na = source_artifact
    if contains_na and not source_fields:
        findings.append(finding(f"`source_plan` has `N/A` instead of a materialized `## Promoted route artifact`: `{source_plan}`."))
        return findings
    if not source_fields:
        findings.append(finding(f"`source_plan` has no parseable `## Promoted route artifact` fields: `{source_plan}`."))
        return findings

    missing = [field for field in planning_contour_source_route_required_fields(source_fields) if not source_fields.get(field)]
    invalid = planning_contour_invalid_enum_fields(source_fields, PLANNING_CONTOUR_SOURCE_ROUTE_ENUM_FIELDS)
    if missing:
        findings.append(
            finding(
                "`source_plan` `## Promoted route artifact` is missing required field(s): "
                + ", ".join(missing)
                + "."
            )
        )
    if invalid:
        findings.append(
            finding(
                "`source_plan` `## Promoted route artifact` has invalid enum field(s): "
                + ", ".join(invalid)
                + "."
            )
        )

    source_analysis_plan = clean_planning_contour_ref(source_fields.get("source_analysis_plan", ""))
    if source_analysis_plan and source_analysis_plan != source_plan:
        findings.append(
            finding(
                "`source_plan` `source_analysis_plan` must point back to the same source plan "
                f"(got `{source_analysis_plan}`, expected `{source_plan}`)."
            )
        )

    target_promoted_artifact_ref = clean_planning_contour_ref(promoted_from.get("promoted_artifact_ref", ""))
    source_promoted_artifact_ref = clean_planning_contour_ref(source_fields.get("promoted_artifact_ref", ""))
    if target_promoted_artifact_ref != current_rel_path:
        findings.append(
            finding(
                "`promoted_artifact_ref` must equal the current target plan path "
                f"(got `{target_promoted_artifact_ref}`, expected `{current_rel_path}`)."
            )
        )
    if source_promoted_artifact_ref != current_rel_path:
        findings.append(
            finding(
                "source `promoted_artifact_ref` must equal the current target plan path "
                f"(got `{source_promoted_artifact_ref}`, expected `{current_rel_path}`)."
            )
        )

    comparison_pairs = (
        ("accepted_route", "accepted_route"),
        ("promoted_artifact_kind", "promoted_artifact_kind"),
        ("queue_admission", "queue_admission_at_acceptance"),
        ("runner_admission", "runner_admission_at_acceptance"),
    )
    for source_field, target_field in comparison_pairs:
        if planning_contour_token(source_fields.get(source_field, "")) != planning_contour_token(
            promoted_from.get(target_field, "")
        ):
            findings.append(
                finding(
                    f"source `{source_field}` must match target `{target_field}` "
                    f"(source `{source_fields.get(source_field, '')}`, target `{promoted_from.get(target_field, '')}`)."
                )
            )

    return findings


def validate_planning_contour_object_carrier(
    path: Path,
    plan_meta_obj: dict,
    plan_meta_line: int | None,
    *,
    key: str,
    required_fields: tuple[str, ...],
    enum_fields: dict[str, str] | None = None,
    allowed_state_values: frozenset[str] | None = None,
    applicable: bool,
    missing_is_error: bool,
) -> tuple[list[Finding], dict[str, object] | None]:
    if not applicable:
        return [], None

    field_path = f"plan_meta.{key}"
    if key not in plan_meta_obj:
        if not missing_is_error:
            return [], None
        return [
            planning_contour_schema_finding(
                path,
                plan_meta_line,
                "ERROR",
                f"`{field_path}` is required for this planning-contour carrier.",
            )
        ], None

    value = plan_meta_obj.get(key)
    if value is None:
        return [
            planning_contour_schema_finding(
                path,
                plan_meta_line,
                "ERROR",
                f"`{field_path}` must be an object, not null.",
            )
        ], None
    if not isinstance(value, dict):
        return [
            planning_contour_schema_finding(
                path,
                plan_meta_line,
                "ERROR",
                f"`{field_path}` must be an object.",
            )
        ], None

    missing = [field for field in required_fields if object_field_is_blank(value.get(field))]
    if key == ACCEPTED_ROUTE_DERIVED_PROMOTED_FROM_KEY and value.get(ACCEPTED_ROUTE_DERIVED_AUTHORITY_NOTE_KEY) != ACCEPTED_ROUTE_DERIVED_AUTHORITY_NOTE:
        if ACCEPTED_ROUTE_DERIVED_AUTHORITY_NOTE_KEY not in missing:
            missing.append(ACCEPTED_ROUTE_DERIVED_AUTHORITY_NOTE_KEY)

    invalid: list[str] = []
    if allowed_state_values is not None:
        state = planning_contour_token(value.get("state", ""))
        if state not in allowed_state_values:
            invalid.append("state")
    if enum_fields is not None:
        invalid.extend(planning_contour_invalid_enum_fields(value, enum_fields))

    if not missing and not invalid:
        return [], value

    details: list[str] = []
    if missing:
        details.append("missing required field(s): " + ", ".join(missing))
    if invalid:
        details.append("invalid enum field(s): " + ", ".join(invalid))
    return [
        planning_contour_schema_finding(
            path,
            plan_meta_line,
            "ERROR",
            f"`{field_path}` is not schema-valid: " + "; ".join(details) + ".",
        )
    ], value


def planning_contour_role_requires_promoted_from(plan_meta_obj: dict | None) -> bool:
    if not isinstance(plan_meta_obj, dict):
        return False
    return is_decomposition_wave(plan_meta_obj) or ACCEPTED_ROUTE_DERIVED_PROMOTED_FROM_KEY in plan_meta_obj


def validate_planning_contour_carrier_schema(
    path: Path,
    lines: list[str],
    plan_meta_obj: dict | None,
    plan_meta_line: int | None,
    *,
    status_value: str | None,
) -> list[Finding]:
    if path.name == "_template.md" or not is_planning_contour_schema_hardening_enforced(path):
        return []
    if not isinstance(plan_meta_obj, dict):
        return []

    findings: list[Finding] = []
    findings.extend(validate_planning_contour_source_route_artifact(path, lines, plan_meta_obj))

    promoted_from_findings, promoted_from_obj = validate_planning_contour_object_carrier(
        path,
        plan_meta_obj,
        plan_meta_line,
        key=ACCEPTED_ROUTE_DERIVED_PROMOTED_FROM_KEY,
        required_fields=PLANNING_CONTOUR_PROMOTED_FROM_REQUIRED_FIELDS,
        enum_fields=PLANNING_CONTOUR_PROMOTED_FROM_ENUM_FIELDS,
        applicable=planning_contour_role_requires_promoted_from(plan_meta_obj),
        missing_is_error=is_decomposition_wave(plan_meta_obj),
    )
    findings.extend(promoted_from_findings)
    if not promoted_from_findings:
        findings.extend(validate_promoted_from_source_route_parity(path, promoted_from_obj, plan_meta_line))

    status_norm = status_value.strip().lower() if status_value else ""
    queue_activation_applicable = "queue_activation" in plan_meta_obj or status_norm == "architect initial draft"
    queue_activation_findings, queue_activation_obj = validate_planning_contour_object_carrier(
        path,
        plan_meta_obj,
        plan_meta_line,
        key="queue_activation",
        required_fields=PLANNING_CONTOUR_QUEUE_ACTIVATION_REQUIRED_FIELDS,
        allowed_state_values=PLANNING_CONTOUR_ENUM_VALUES["queue_activation_states"],
        applicable=queue_activation_applicable,
        missing_is_error=status_norm == "architect initial draft",
    )
    findings.extend(queue_activation_findings)
    if status_norm == "architect initial draft" and isinstance(queue_activation_obj, dict):
        activation_state = planning_contour_token(queue_activation_obj.get("state", ""))
        if (
            activation_state in PLANNING_CONTOUR_ENUM_VALUES["queue_activation_states"]
            and activation_state not in {"owner_approved", "architect_approved", "n/a"}
        ):
            findings.append(
                planning_contour_schema_finding(
                    path,
                    plan_meta_line,
                    "ERROR",
                    "`plan_meta.queue_activation.state` must be `owner_approved`, `architect_approved`, "
                    "or intentional collection-ineligible `n/a` before an `Architect initial draft` "
                    "enters the queue.",
                )
            )
    if status_norm and status_norm != "architect initial draft" and isinstance(queue_activation_obj, dict):
        activation_state = planning_contour_token(queue_activation_obj.get("state", ""))
        if activation_state == "not_requested":
            findings.append(
                planning_contour_schema_finding(
                    path,
                    plan_meta_line,
                    "ERROR",
                    "`plan_meta.queue_activation.state=not_requested` cannot survive past "
                    "`Architect initial draft`; open Owner Q&A, materialize activation, or mark it `n/a`.",
                )
            )
        if activation_state in {"owner_approved", "architect_approved"}:
            next_plans = plan_meta_obj.get("next_plans")
            next_plan_paths = [str(item).strip() for item in next_plans] if isinstance(next_plans, list) else []
            execution_queue_entries = plan_status_oracle.concrete_execution_queue_plan_entries("\n".join(lines))
            if execution_queue_entries and not any(next_plan_paths):
                findings.append(
                    planning_contour_schema_finding(
                        path,
                        plan_meta_line,
                        "ERROR",
                        "`plan_meta.queue_activation.state` is approved and `## Execution queue` has child plan(s), "
                        "so `plan_meta.next_plans[]` must carry the same activation path before handoff/queue import.",
                    )
                )

    scope_expansion_findings, _ = validate_planning_contour_object_carrier(
        path,
        plan_meta_obj,
        plan_meta_line,
        key="scope_expansion",
        required_fields=PLANNING_CONTOUR_SCOPE_EXPANSION_REQUIRED_FIELDS,
        allowed_state_values=PLANNING_CONTOUR_ENUM_VALUES["scope_expansion_states"],
        applicable="scope_expansion" in plan_meta_obj,
        missing_is_error=False,
    )
    findings.extend(scope_expansion_findings)

    return findings


def normalized_scope_expansion_state(plan_meta_obj: dict | None) -> str | None:
    if not isinstance(plan_meta_obj, dict):
        return None
    scope_expansion = plan_meta_obj.get("scope_expansion")
    if not isinstance(scope_expansion, dict):
        return None
    raw_state = scope_expansion.get("state")
    if not isinstance(raw_state, str):
        return None
    state = raw_state.strip().lower()
    return state or None


def has_scope_expansion_carrier(plan_meta_obj: dict | None) -> bool:
    if not isinstance(plan_meta_obj, dict):
        return False
    return isinstance(plan_meta_obj.get("scope_expansion"), dict)


def is_ordinary_dev_contour(plan_meta_obj: dict | None) -> bool:
    return not is_analysis_wave(plan_meta_obj) and not is_decomposition_wave(plan_meta_obj)


def dev_contour_integration_value_is_material(value: str) -> bool:
    cleaned = value.strip().strip("`").strip()
    if not cleaned:
        return False
    if is_placeholder_value(cleaned):
        return False
    if is_explicit_na_value(cleaned):
        return False
    if re.fullmatch(r"`?\s*(?:none|no|null|unknown|unassigned|-+)\s*`?", cleaned, re.IGNORECASE):
        return False
    return not DEV_CONTOUR_INTEGRATION_ABSENCE_RE.search(cleaned)


def has_material_dev_contour_integration_owner(lines: list[str]) -> bool:
    for line in lines:
        field = DEV_CONTOUR_INTEGRATION_OWNER_FIELD_RE.search(line)
        if field and dev_contour_integration_value_is_material(field.group("value")):
            return True
        if DEV_CONTOUR_INTEGRATION_POLICY_TEXT_RE.search(line) and dev_contour_integration_value_is_material(line):
            return True
    return False


def is_dev_contour_append_only_historical_row(line: str, h2_heading: str) -> bool:
    timestamped_row = re.match(r"^\s*-\s*\[(?P<timestamp>[^\]]+)\]\s*", line)
    return bool(
        h2_heading in DEV_CONTOUR_APPEND_ONLY_HISTORICAL_HEADINGS
        and timestamped_row
        and INLINE_TIMESTAMP_RE.search(timestamped_row.group("timestamp"))
    )


def legacy_child_graph_drift_line(lines: list[str]) -> tuple[int, str] | None:
    has_material_integration_owner = has_material_dev_contour_integration_owner(lines)
    current_h2_heading = ""
    current_h2_is_live_child_carrier = False
    in_fence = False
    for idx, line in enumerate(lines, start=1):
        if in_fence:
            if FENCE_END_RE.match(line):
                in_fence = False
        elif FENCE_START_RE.match(line):
            in_fence = True
        elif H2_HEADING_RE.match(line):
            current_h2_heading = " ".join(line.lstrip("#").strip().lower().split())
            current_h2_is_live_child_carrier = bool(
                CHILD_PLAN_MAP_HEADING_RE.match(line) or EXECUTION_QUEUE_HEADING_RE.match(line)
            )
        if LEGACY_CHILD_GRAPH_DRIFT_RE.search(line):
            return idx, "legacy child-graph/split-required wording"
        failure_mode = DEV_CONTOUR_FAILURE_MODE_FIELD_RE.search(line)
        if failure_mode:
            return idx, f"decomposition failure-mode `{failure_mode.group('mode').lower()}`"
        if CONCRETE_PLAN_PATH_RE.search(line):
            if (
                current_h2_is_live_child_carrier
                or DEV_CONTOUR_LIVE_CHILD_REF_FIELD_RE.search(line)
            ):
                return idx, "concrete child plan path in child-map/queue context"
            if DEV_CONTOUR_CHILD_REF_MARKER_RE.search(line) and not (
                DELIVERED_BASELINE_CONTEXT_ROW_RE.match(line)
                or is_dev_contour_append_only_historical_row(line, current_h2_heading)
            ):
                return idx, "concrete child plan path in child-map/queue context"
        proof_lanes = DEV_CONTOUR_PROOF_LANES_RE.search(line)
        if proof_lanes:
            value = proof_lanes.group("value")
            lane_count = len([part for part in re.split(r"[,;/|]+", value) if part.strip()])
            if lane_count >= 2 and not has_material_integration_owner:
                return idx, "multiple proof lanes without integration/recomposition owner or serialization policy"
    return None


def is_dev_contour_pre_coder_admission_applicable(
    path: Path,
    lines: list[str],
    plan_meta_obj: dict | None,
    *,
    status_value: str | None,
) -> bool:
    status_norm = " ".join((status_value or "").strip().lower().split())
    return bool(
        extract_plan_type(lines) == "dev"
        and has_raw_literal_dev_plan_type(lines)
        and is_current_plan(path)
        and is_ordinary_dev_contour(plan_meta_obj)
        and status_norm in DEV_CONTOUR_PRE_CODER_STATUS_NORMS
    )


def dev_contour_pre_coder_blocking_finding(path: Path, line_no: int, detail: str) -> Finding:
    return Finding(
        path,
        line_no,
        "ERROR",
        DEV_CONTOUR_CHILD_GRAPH_DRIFT_WARNING_PREFIX + detail,
    )


def validate_dev_contour_child_graph_drift(
    path: Path,
    lines: list[str],
    plan_meta_obj: dict | None,
    plan_meta_line: int | None,
    *,
    status_value: str | None = None,
) -> list[Finding]:
    if not is_ordinary_dev_contour(plan_meta_obj):
        return []

    state = normalized_scope_expansion_state(plan_meta_obj)
    if is_dev_contour_pre_coder_admission_applicable(
        path,
        lines,
        plan_meta_obj,
        status_value=status_value,
    ):
        if state in DEV_CONTOUR_DRIFT_SCOPE_EXPANSION_STATES:
            return [
                dev_contour_pre_coder_blocking_finding(
                    path,
                    plan_meta_line or 1,
                    f"`plan_meta.scope_expansion.state={state}` is unresolved at the pre-Coder handoff; "
                    "use the existing Architect reroute before Coder starts.",
                )
            ]

        legacy_drift = legacy_child_graph_drift_line(lines)
        if legacy_drift:
            line_no, reason = legacy_drift
            return [
                dev_contour_pre_coder_blocking_finding(
                    path,
                    line_no,
                    f"{reason} remains unresolved at the pre-Coder handoff; "
                    "remove the existing detector signal or use the existing Architect reroute before Coder starts.",
                )
            ]

        return []

    if state in DEV_CONTOUR_DRIFT_SCOPE_EXPANSION_STATES:
        message = DEV_CONTOUR_CHILD_GRAPH_DRIFT_WARNING_PREFIX + (
            f"`plan_meta.scope_expansion.state={state}` indicates this ordinary dev plan "
            "should stop and close the routing decision, reroute to planning contour, or record a concrete override reason; "
            "warning-only, not queue/admission blocking."
        )
        return [
            Finding(
                path,
                plan_meta_line or 1,
                "WARN",
                message,
            )
        ]

    if has_scope_expansion_carrier(plan_meta_obj):
        return []

    legacy_drift = legacy_child_graph_drift_line(lines)
    if not legacy_drift:
        return []

    line_no, reason = legacy_drift
    message = DEV_CONTOUR_CHILD_GRAPH_DRIFT_WARNING_PREFIX + (
        f"{reason} found without `plan_meta.scope_expansion`; use the E2 scope-expansion carrier "
        "for parseable reroute state, add an integration/serialization owner, or record a concrete override reason. "
        "Warning-only, not queue/admission blocking."
    )
    return [
        Finding(
            path,
            line_no,
            "WARN",
            message,
        )
    ]


def is_done_status(status_value: str | None) -> bool:
    return bool(status_value and status_value.strip().lower() == "done")


def validate_done_post_merge_gate_checklist(
    path: Path,
    lines: list[str],
    *,
    status_value: str | None,
) -> list[Finding]:
    if not is_done_status(status_value):
        return []

    # Legacy plan.v1 remains readable; current plan.v2 follows the same rule at every filename.
    if not is_post_merge_gate_enforced(path):
        return []

    section = slice_h2_section(lines, POST_MERGE_GATE_HEADING_RE)
    if not section:
        return []

    section_line_no, body = section
    findings: list[Finding] = []
    for idx, line in enumerate(body):
        if not OPEN_MARKDOWN_CHECKBOX_RE.match(line):
            continue
        findings.append(
            Finding(
                path,
                section_line_no + idx + 1,
                "ERROR",
                "Done plan has an open `## Post-merge gate` checklist item. "
                "Close it as `- [x]` with evidence, move the plan out of `Done`, "
                "or make the whole section explicit `N/A (why=...)`; open `- [ ]` "
                "post-merge gates cannot coexist with `Status: Done`.",
            )
        )

    return findings


def text_has_umbrella_roadmap_signal(lines: list[str], plan_meta_obj: dict | None) -> bool:
    title_text = lines[0] if lines else ""
    tags = (plan_meta_obj or {}).get("tags")
    tags_text = " ".join(str(item) for item in tags) if isinstance(tags, list) else ""
    title_and_tags = f"{title_text}\n{tags_text}"
    if not UMBRELLA_MARKER_RE.search(title_and_tags):
        return False
    head_text = "\n".join(lines[:80])
    return bool(ROADMAP_MARKER_RE.search(f"{head_text}\n{tags_text}"))


def text_has_affirmative_followup_disposition(text: str) -> bool:
    return bool(
        FOLLOWUP_HANDLED_RE.search(text)
        and not FOLLOWUP_NEGATED_HANDLED_RE.search(text)
        and not FOLLOWUP_PENDING_HANDLED_RE.search(text)
    )


def text_has_followup_disposition_evidence(text: str) -> bool:
    return bool(FOLLOWUP_DISPOSITION_EVIDENCE_RE.search(text))


def followup_out_item_has_structured_disposition_evidence(item: dict) -> bool:
    for key, value in item.items():
        if not isinstance(key, str):
            continue
        normalized_key = key.strip().lower()
        if normalized_key in FOLLOWUP_DISPOSITION_EVIDENCE_KEYS and str(value or "").strip():
            return True
        if (
            normalized_key != "summary"
            and isinstance(value, str)
            and text_has_followup_disposition_evidence(value)
        ):
            return True
    return False


def followup_out_item_has_handled_disposition(item: dict) -> bool:
    has_structured_evidence = followup_out_item_has_structured_disposition_evidence(item)
    for key, value in item.items():
        if not isinstance(key, str) or key.strip().lower() not in FOLLOWUP_DISPOSITION_KEYS:
            continue
        if isinstance(value, str) and text_has_affirmative_followup_disposition(value) and has_structured_evidence:
            return True

    summary = item.get("summary")
    if (
        isinstance(summary, str)
        and text_has_affirmative_followup_disposition(summary)
        and text_has_followup_disposition_evidence(summary)
    ):
        return True

    return False


def followup_out_item_is_open_roadmap_track(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    plan_value = item.get("plan")
    if isinstance(plan_value, str) and plan_value.strip():
        return False

    if followup_out_item_has_handled_disposition(item):
        return False
    return bool(str(item.get("summary") or "").strip())


def open_roadmap_followups(plan_meta_obj: dict | None) -> list[tuple[int, dict]]:
    if not isinstance(plan_meta_obj, dict):
        return []
    followups_out = plan_meta_obj.get("followups_out")
    if not isinstance(followups_out, list):
        return []
    open_items: list[tuple[int, dict]] = []
    for idx, item in enumerate(followups_out, start=1):
        if followup_out_item_is_open_roadmap_track(item):
            open_items.append((idx, item))
    return open_items


def followup_summary_address_tokens(item: dict) -> set[str]:
    summary = str(item.get("summary") or "").lower()
    tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", summary)
        if len(token) >= 4 and token not in FOLLOWUP_ADDRESS_STOPWORDS
    }
    return tokens


def closeout_text_addresses_followup(section_text: str, idx: int, item: dict) -> bool:
    if re.search(rf"(?<!\w)followups_out\[{idx}\](?!\w)", section_text, re.IGNORECASE):
        return True

    tokens = followup_summary_address_tokens(item)
    if not tokens:
        return False
    section_tokens = set(re.findall(r"[a-z0-9]+", section_text.lower()))
    required_matches = min(2, len(tokens))
    return len(tokens & section_tokens) >= required_matches


def has_umbrella_roadmap_closeout_disposition(lines: list[str], open_items: list[tuple[int, dict]]) -> bool:
    section = slice_h2_section(lines, CLOSE_OUT_ROUTING_HEADING_RE)
    if not section:
        return False
    _, section_lines = section
    section_text = "\n".join(section_lines)
    if UMBRELLA_ROADMAP_GLOBAL_DISPOSITION_RE.search(section_text):
        return True
    if not UMBRELLA_ROADMAP_ROW_CARRIER_RE.search(section_text):
        return False
    if not CONCRETE_PLAN_PATH_RE.search(section_text):
        return False
    return all(closeout_text_addresses_followup(section_text, idx, item) for idx, item in open_items)


def validate_umbrella_roadmap_lifecycle_guard(
    path: Path,
    lines: list[str],
    plan_meta_obj: dict | None,
    plan_meta_line: int | None,
    *,
    status_value: str | None,
) -> list[Finding]:
    if not is_done_status(status_value):
        return []
    if not text_has_umbrella_roadmap_signal(lines, plan_meta_obj):
        return []

    open_items = open_roadmap_followups(plan_meta_obj)
    if not open_items:
        return []

    if has_umbrella_roadmap_closeout_disposition(lines, open_items):
        return []

    first_idx, first_item = open_items[0]
    summary = str(first_item.get("summary") or "").strip()
    suffix = f" First open item: followups_out[{first_idx}]"
    if summary:
        suffix += f" summary={summary!r}."
    severity = "ERROR" if umbrella_roadmap_lifecycle_hard_errors(path, lines) else "WARN"
    return [
        Finding(
            path,
            plan_meta_line or 1,
            severity,
            UMBRELLA_ROADMAP_LIFECYCLE_WARNING_PREFIX
            + "Done roadmap/umbrella has non-cancelled `plan_meta.followups_out[].plan=null` track(s) "
            "without row-local plan/disposition, parked/reference keep, superseded-by path, or cancelled/handled disposition. "
            "Queue completion closes only the current queue slice; it does not by itself close roadmap delivery."
            + suffix,
        )
    ]


def umbrella_roadmap_lifecycle_hard_errors(path: Path, lines: list[str]) -> bool:
    if not is_current_plan(path):
        return False
    schema_class, _ = classify_plan_schema_version(path, lines)
    return schema_class in {"v2", "legacy_v1"}


def text_has_selected_roadmap_child_signal(lines: list[str], plan_meta_obj: dict | None) -> bool:
    if not isinstance(plan_meta_obj, dict):
        return False
    parent = plan_meta_obj.get("parent")
    if not isinstance(parent, str) or not parent.strip():
        return False
    tags = plan_meta_obj.get("tags")
    tags_text = " ".join(str(item) for item in tags) if isinstance(tags, list) else ""
    head_text = "\n".join(lines[:120])
    return bool(SELECTED_ROADMAP_CHILD_MARKER_RE.search(f"{head_text}\n{tags_text}"))


def closeout_has_materialized_successor_or_terminal_disposition(
    lines: list[str],
    plan_meta_obj: dict | None,
) -> bool:
    if isinstance(plan_meta_obj, dict):
        next_plans = plan_meta_obj.get("next_plans")
        if isinstance(next_plans, list) and any(isinstance(item, str) and item.strip() for item in next_plans):
            return True

    section = slice_h2_section(lines, CLOSE_OUT_ROUTING_HEADING_RE)
    if not section:
        return False
    _, section_lines = section
    section_text = "\n".join(section_lines)
    if UMBRELLA_ROADMAP_DISPOSITION_RE.search(section_text):
        return True
    for line in section_lines:
        match = NEXT_BOUNDED_SLICE_LINE_RE.match(line)
        if match and CONCRETE_PLAN_PATH_RE.search(match.group("body")):
            return True
    return False


def selected_child_next_handoff_gap(lines: list[str]) -> tuple[int, str] | None:
    section = slice_h2_section(lines, CLOSE_OUT_ROUTING_HEADING_RE)
    if not section:
        return None
    heading_line_no, section_lines = section
    section_text = "\n".join(section_lines)
    for idx, line in enumerate(section_lines, start=heading_line_no + 1):
        match = NEXT_BOUNDED_SLICE_LINE_RE.match(line)
        if not match:
            continue
        body = match.group("body").strip()
        if body and not CONCRETE_PLAN_PATH_RE.search(body) and not UMBRELLA_ROADMAP_DISPOSITION_RE.search(body):
            return idx, body
    if PARENT_RETURN_SIGNAL_RE.search(section_text) and ROADMAP_NEXT_WORK_SIGNAL_RE.search(section_text):
        return heading_line_no, "closeout returns roadmap selection to parent without successor disposition"
    return None


def validate_selected_child_roadmap_handoff_guard(
    path: Path,
    lines: list[str],
    plan_meta_obj: dict | None,
    plan_meta_line: int | None,
    *,
    status_value: str | None,
) -> list[Finding]:
    if not is_done_status(status_value):
        return []
    if not text_has_selected_roadmap_child_signal(lines, plan_meta_obj):
        return []
    if closeout_has_materialized_successor_or_terminal_disposition(lines, plan_meta_obj):
        return []

    gap = selected_child_next_handoff_gap(lines)
    if not gap:
        return []
    line_no, body = gap
    return [
        Finding(
            path,
            line_no or plan_meta_line or 1,
            "WARN",
            UMBRELLA_ROADMAP_LIFECYCLE_WARNING_PREFIX
            + "Done selected roadmap child punts next work back to parent without materialized successor, "
            "transferred follow-up carrier, explicit no-successor reason, or cancelled/handled disposition. "
            f"Selected child closeout: {body!r}.",
        )
    ]


def is_placeholder_value(value: str) -> bool:
    value = value.strip()
    if not value:
        return True
    upper = value.upper()
    if "UNCONFIRMED" in upper or "TBD" in upper:
        return True
    if re.fullmatch(r"(?:N\s*/\s*A|NA)", upper):
        return True
    return value.strip(".") == ""


def validate_materialized_review_visual_lane_contract(path: Path, lines: list[str]) -> list[Finding]:
    """Validate one helper-owned inline-v1 or safe external-v2/ref-v1 carrier."""
    text = "\n".join(lines)
    if not any(line.strip() == "## Review visual lane contract" for line in lines):
        return []
    expected_plan_ref: str | None = None
    try:
        expected_plan_ref = path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        pass
    expected_range_identity = review_visual_lane_contract.review_target_identity(text)
    payload, contract_errors = review_visual_lane_contract.parse_materialized_contract(
        text,
        project_root=REPO_ROOT,
        expected_plan_ref=expected_plan_ref,
        expected_range_identity=expected_range_identity,
        require_review_target_identity=True,
    )
    heading_line = next(
        (line_no for line_no, line in enumerate(lines, start=1) if line.strip() == "## Review visual lane contract"),
        1,
    )
    if contract_errors or payload is None:
        return [
            Finding(
                path,
                heading_line,
                "ERROR",
                "Generated review visual lane contract is invalid: " + ", ".join(contract_errors),
            )
        ]

    # A generated range plan and its same-stem draft are two derived consumers,
    # never two authorities.  The helper verifies each ref projection; this
    # additional readback catches a plan-only update before Reviewer intake.
    if expected_plan_ref and path.is_file() and expected_plan_ref.startswith("docs/plans/"):
        draft_ref = f"docs/code_drafts/{path.stem}__code_draft.md"
        draft_path = REPO_ROOT / draft_ref
        if draft_path.is_file():
            draft_text = draft_path.read_text(encoding="utf-8", errors="replace")
            draft_payload, draft_errors = review_visual_lane_contract.parse_materialized_contract(
                draft_text,
                project_root=REPO_ROOT,
                expected_plan_ref=expected_plan_ref,
                expected_range_identity=expected_range_identity,
            )
            if draft_errors or draft_payload is None or draft_payload != payload:
                return [
                    Finding(
                        path,
                        heading_line,
                        "ERROR",
                        "Generated plan/draft review visual lane projection mismatch: "
                        + ", ".join(draft_errors or ("projection_mismatch",)),
                    )
                ]

    visual_section = slice_h2_section(lines, VISUAL_ACCEPTANCE_RE)
    visual_body = "" if visual_section is None else "\n".join(visual_section[1])
    visual_normalized = " ".join(visual_body.lower().replace("`", "").split())
    state = str(payload["availability_state"])
    runtime_ui_kind = str(payload["runtime_ui_kind"])
    if state in {"missing", "malformed", "ambiguous"} and runtime_ui_kind == "web":
        return [
            Finding(
                path,
                heading_line,
                "ERROR",
                "Generated runtime-UI visual lane is a technical proof gap "
                f"(availability_state={state}, reason={payload['reason']}); route to Architect before Reviewer-ready use.",
            )
        ]

    if state == "not_applicable":
        reason = str(payload["reason"])
        if reason.startswith("profile_local_runtime_lane:"):
            return []
        if "n/a" not in visual_normalized or "why" not in visual_normalized:
            return [
                Finding(
                    path,
                    visual_section[0] if visual_section else heading_line,
                    "ERROR",
                    "Generated non-UI/docs-only visual lane must retain explicit `N/A (why=...)`.",
                )
            ]
        return []

    if state != "available":
        return []
    naked_na = re.match(r"^n\s*/\s*a\b", visual_normalized, re.IGNORECASE) is not None
    if not visual_body or naked_na:
        return [
            Finding(
                path,
                visual_section[0] if visual_section else heading_line,
                "ERROR",
                "Available generated runtime-UI visual lane cannot use naked `Visual Acceptance: N/A`.",
            )
        ]

    required_literals = [
        str(payload["comparator_command"]),
        str(payload["durable_review_asset_root"]),
        "comparator_claim=mechanical",
        "complete-index",
        "design_verdict",
    ]
    required_literals.extend(str(command) for command in payload["human_commands_by_mode"].values())
    missing = [literal for literal in required_literals if literal not in visual_body]
    if missing:
        return [
            Finding(
                path,
                visual_section[0] if visual_section else heading_line,
                "ERROR",
                "Available generated runtime-UI visual lane is missing comparator/human/current-root claim literal(s): "
                + ", ".join(missing),
            )
        ]
    return []


_REVIEW_RANGE_PROVENANCE_HEADING = "Review-range semantic provenance"
_REVIEW_RANGE_PROVENANCE_V1 = "review_range_semantic_provenance.v1"
_REVIEW_RANGE_PROVENANCE_V2 = "review_range_semantic_provenance.v2"
_REVIEW_RANGE_PROVENANCE_ENGINE_BY_SCHEMA = {
    _REVIEW_RANGE_PROVENANCE_V1: "review-range-source-route.v1",
    _REVIEW_RANGE_PROVENANCE_V2: "review-range-source-route.v2",
}
_REVIEW_RANGE_SEMANTIC_SURFACE_SHA256 = (
    "f41cf5cbc089f4614d4106e48366eabe4bcbb388e02d6fbcf981c59aa57bc5de"
)
_REVIEW_RANGE_PROVENANCE_FIELDS = frozenset(
    {
        "schema_version",
        "source_engine_version",
        "source_runtime_pin",
        "context_state",
        "behavior_identity",
        "marker_repository_id_or_not_applicable",
        "context_generation",
        "semantic_surface_sha256",
        "selected_rule_ids",
        "inputs",
        "outputs",
        "visual_contract_ref_or_inline_digest",
    }
)
_REVIEW_RANGE_LEGACY_RULE_IDS = (
    "fixed_dependent_test_map",
    "legacy_profile_aware_generated_prose",
    "provenance_rerun_and_lifecycle",
    "range_and_artifact_core",
    "review_only_mechanical_commands",
    "visual_contract_parser_and_renderer",
)
_REVIEW_RANGE_ENGAGED_RULE_IDS = ("planveyor.v1", "planveyor.review_only.v1")
_REVIEW_RANGE_ENGAGED_INPUT_SPECS = (
    ("policy_json", "docs/_meta/review_range_policy.v1.json", "strict_duplicate_key_safe_json"),
    ("plan_template", "docs/plans/_template.md", "declared_text"),
    ("code_draft_template", "docs/code_drafts/_template.md", "declared_text"),
    ("reviewer_role_reference", "docs/roles/reviewer.md", "declared_identity"),
    ("review_scoping_playbook", "docs/playbooks/review_scoping_plan.md", "declared_text"),
    ("review_merge_playbook", "docs/playbooks/review_merge_range.md", "declared_text"),
    ("plan_vocabulary_reference", "docs/_meta/plan_vocab.json", "captured_row_only"),
    ("smoke_visual", "docs/smoke_visual.md", "visual_helper_declared_text"),
    ("testing_runbook", "docs/testing_runbook.md", "visual_helper_declared_text"),
)
_REVIEW_RANGE_INPUT_ROW_FIELDS_V1 = frozenset(
    {"id", "reader", "contract_relative_path", "captured_manifest_path", "mode", "blob_oid", "sha256"}
)
_REVIEW_RANGE_INPUT_ROW_FIELDS_V2 = frozenset(
    {"id", "reader", "contract_relative_path", "content_source"}
)
_REVIEW_RANGE_OUTPUT_ROW_FIELDS = frozenset({"artifact", "section_or_path", "rule_ids"})
_REVIEW_RANGE_HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
_REVIEW_RANGE_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_REVIEW_RANGE_REPOSITORY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_REVIEW_RANGE_MAX_TEXT_BYTES = 1024


def _review_range_text(value: object, *, maximum: int = _REVIEW_RANGE_MAX_TEXT_BYTES) -> bool:
    if not (
        type(value) is str
        and bool(value)
        and value == value.strip()
        and "\n" not in value
        and "\r" not in value
    ):
        return False
    try:
        return len(value.encode("utf-8")) <= maximum
    except UnicodeEncodeError:
        return False


def _review_range_engaged_repository_ids_are_valid(
    behavior_identity: object,
    marker_repository_id: object,
) -> bool:
    """Validate the durable engaged-consumer identity pair without routing."""

    if not (
        _review_range_text(behavior_identity)
        and _review_range_text(marker_repository_id)
        and behavior_identity != "default"
        and behavior_identity == marker_repository_id
    ):
        return False
    assert type(behavior_identity) is str
    return _REVIEW_RANGE_REPOSITORY_ID_RE.fullmatch(behavior_identity) is not None


def _review_range_relative_path(value: object) -> bool:
    if not _review_range_text(value):
        return False
    assert type(value) is str
    if "\\" in value:
        return False
    candidate = PurePosixPath(value)
    return (
        not candidate.is_absolute()
        and "." not in candidate.parts
        and ".." not in candidate.parts
        and candidate.as_posix() == value
    )


def parse_review_range_semantic_provenance(lines: Sequence[str]) -> tuple[dict[str, object] | None, str | None]:
    """Parse the source-owned receipt without making it a routing authority."""

    text = "\n".join(lines)
    heading = f"## {_REVIEW_RANGE_PROVENANCE_HEADING}\n"
    if heading not in text:
        return None, None
    section = text.split(heading, 1)[1].split("\n## ", 1)[0]
    blocks = re.findall(r"```json\n(.*?)\n```", section, flags=re.DOTALL)
    if len(blocks) != 1:
        return None, "receipt_json_block_invalid"

    def reject_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        parsed: dict[str, object] = {}
        for key, value in pairs:
            if key in parsed:
                raise ValueError("duplicate receipt key")
            parsed[key] = value
        return parsed

    def reject_constant(_value: str) -> None:
        raise ValueError("non-finite JSON constant")

    try:
        payload = json.loads(
            blocks[0],
            object_pairs_hook=reject_duplicate_pairs,
            parse_constant=reject_constant,
        )
    except (json.JSONDecodeError, RecursionError):
        return None, "receipt_json_invalid"
    except ValueError:
        return None, "receipt_json_non_finite_or_duplicate_key"
    if type(payload) is not dict:
        return None, "receipt_not_object"
    return payload, None


def _review_range_semantic_provenance_shape_error(payload: dict[str, object]) -> str | None:
    """Return a stable shape error for the finite source-engine receipt."""

    if set(payload) != _REVIEW_RANGE_PROVENANCE_FIELDS:
        return "schema_or_field_set"
    schema = payload.get("schema_version")
    if type(schema) is not str:
        return "schema_or_field_set"
    expected_engine = _REVIEW_RANGE_PROVENANCE_ENGINE_BY_SCHEMA.get(schema)
    if expected_engine is None or payload.get("source_engine_version") != expected_engine:
        return "schema_or_field_set"
    if payload.get("semantic_surface_sha256") != _REVIEW_RANGE_SEMANTIC_SURFACE_SHA256:
        return "semantic_table"

    state = payload.get("context_state")
    generation = payload.get("context_generation")
    behavior_identity = payload.get("behavior_identity")
    marker_repository_id = payload.get("marker_repository_id_or_not_applicable")
    if (
        type(state) is not str
        or state not in {"legacy", "engaged"}
        or not _review_range_text(generation, maximum=64)
        or _REVIEW_RANGE_HEX64_RE.fullmatch(str(generation)) is None
        or not _review_range_text(behavior_identity)
        or not _review_range_text(marker_repository_id)
    ):
        return "context_facts"

    runtime_pin = payload.get("source_runtime_pin")
    if state == "legacy":
        if runtime_pin != {"state": "legacy_unpinned"} or marker_repository_id != "not_applicable":
            return "runtime_pin"
    else:
        if not _review_range_engaged_repository_ids_are_valid(
            behavior_identity,
            marker_repository_id,
        ) or type(runtime_pin) is not dict:
            return "runtime_pin"
        if set(runtime_pin) != {"runtime_api_version", "runtime_root", "sha256"}:
            return "runtime_pin"
        runtime_api = runtime_pin.get("runtime_api_version")
        runtime_root = runtime_pin.get("runtime_root")
        runtime_sha256 = runtime_pin.get("sha256")
        if (
            type(runtime_api) is not int
            or not 1 <= runtime_api <= 999
            or not _review_range_text(runtime_root)
            or not str(runtime_root).startswith("/")
            or not _review_range_text(runtime_sha256, maximum=64)
            or _REVIEW_RANGE_HEX64_RE.fullmatch(str(runtime_sha256)) is None
        ):
            return "runtime_pin"

    selected = payload.get("selected_rule_ids")
    if type(selected) is not list or not selected:
        return "rule_input_output_rows"
    # Check every element before set-based duplicate detection: malformed JSON
    # must yield a lint finding, never an unhashable-value exception.
    if any(not _review_range_text(item, maximum=128) for item in selected):
        return "rule_input_output_rows"
    if len(selected) != len(set(selected)):
        return "rule_input_output_rows"
    expected_rule_ids = (
        frozenset(_REVIEW_RANGE_ENGAGED_RULE_IDS)
        if state == "engaged"
        else frozenset(_REVIEW_RANGE_LEGACY_RULE_IDS)
    )
    if len(selected) != len(expected_rule_ids) or set(selected) != expected_rule_ids:
        return "rule_input_output_rows"

    inputs = payload.get("inputs")
    if type(inputs) is not list:
        return "rule_input_output_rows"
    if state == "legacy":
        if inputs:
            return "rule_input_output_rows"
    else:
        if len(inputs) != len(_REVIEW_RANGE_ENGAGED_INPUT_SPECS):
            return "engaged_input_set"
        for row, (input_id, relative_path, reader) in zip(inputs, _REVIEW_RANGE_ENGAGED_INPUT_SPECS):
            if type(row) is not dict:
                return "engaged_input_set"
            if (
                row.get("id") != input_id
                or row.get("reader") != reader
                or row.get("contract_relative_path") != relative_path
            ):
                return "engaged_input_set"
            if schema == _REVIEW_RANGE_PROVENANCE_V1:
                if set(row) != _REVIEW_RANGE_INPUT_ROW_FIELDS_V1:
                    return "engaged_input_set"
                captured_path = row.get("captured_manifest_path")
                if (
                    not _review_range_relative_path(captured_path)
                    or not (captured_path == relative_path or str(captured_path).endswith("/" + relative_path))
                    or not _review_range_text(row.get("mode"), maximum=6)
                    or re.fullmatch(r"100[0-7]{3}", str(row.get("mode"))) is None
                    or not _review_range_text(row.get("blob_oid"), maximum=40)
                    or _REVIEW_RANGE_HEX40_RE.fullmatch(str(row.get("blob_oid"))) is None
                    or not _review_range_text(row.get("sha256"), maximum=64)
                    or _REVIEW_RANGE_HEX64_RE.fullmatch(str(row.get("sha256"))) is None
                ):
                    return "engaged_input_set"
            else:
                if set(row) != _REVIEW_RANGE_INPUT_ROW_FIELDS_V2 or row.get("content_source") != "current_local_worktree":
                    return "engaged_input_set"

    outputs = payload.get("outputs")
    if type(outputs) is not list or len(outputs) != 2:
        return "rule_input_output_rows"
    expected_artifacts = ("plan", "draft")
    for row, artifact in zip(outputs, expected_artifacts):
        if type(row) is not dict or set(row) != _REVIEW_RANGE_OUTPUT_ROW_FIELDS:
            return "rule_input_output_rows"
        if row.get("artifact") != artifact or type(row.get("rule_ids")) is not list or row.get("rule_ids") != selected:
            return "rule_input_output_rows"
        if not _review_range_relative_path(row.get("section_or_path")):
            return "rule_input_output_rows"
    plan_ref = outputs[0]["section_or_path"]
    draft_ref = outputs[1]["section_or_path"]
    assert type(plan_ref) is str and type(draft_ref) is str
    if (
        not is_repo_relative_plan_path(plan_ref)
        or "_reviewer_range_" not in plan_ref
        or draft_ref != f"docs/code_drafts/{PurePosixPath(plan_ref).stem}__code_draft.md"
    ):
        return "rule_input_output_rows"

    visual = payload.get("visual_contract_ref_or_inline_digest")
    if type(visual) is not dict:
        return "visual_receipt"
    kind = visual.get("kind")
    if kind == "inline_digest":
        if set(visual) != {"kind", "sha256"}:
            return "visual_receipt"
    elif kind == "external_ref":
        if set(visual) != {"kind", "ref", "sha256"} or not _review_range_relative_path(visual.get("ref")):
            return "visual_receipt"
    else:
        return "visual_receipt"
    visual_sha256 = visual.get("sha256")
    if not _review_range_text(visual_sha256, maximum=64) or _REVIEW_RANGE_HEX64_RE.fullmatch(str(visual_sha256)) is None:
        return "visual_receipt"
    return None


def validate_review_range_semantic_provenance(path: Path, lines: list[str]) -> list[Finding]:
    """Validate the optional source-engine receipt and its visual projection."""

    payload, parse_error = parse_review_range_semantic_provenance(lines)
    if payload is None and parse_error is None:
        return []
    heading_line = next(
        (line_no for line_no, line in enumerate(lines, start=1) if line.strip() == f"## {_REVIEW_RANGE_PROVENANCE_HEADING}"),
        1,
    )
    if parse_error:
        return [Finding(path, heading_line, "ERROR", f"Review-range semantic provenance is invalid: {parse_error}")]
    assert payload is not None
    shape_error = _review_range_semantic_provenance_shape_error(payload)
    if shape_error:
        messages = {
            "schema_or_field_set": "Review-range semantic provenance has an invalid schema or field set.",
            "semantic_table": "Review-range semantic provenance has an unknown semantic table.",
            "context_facts": "Review-range semantic provenance has invalid context facts.",
            "runtime_pin": "Review-range semantic provenance has an invalid source runtime pin.",
            "rule_input_output_rows": "Review-range semantic provenance has invalid rule/input/output rows.",
            "engaged_input_set": "Review-range engaged provenance does not bind the finite Planveyor input set.",
            "visual_receipt": "Review-range semantic provenance lacks a finite visual receipt.",
        }
        return [Finding(path, heading_line, "ERROR", messages[shape_error])]

    visual = payload["visual_contract_ref_or_inline_digest"]
    assert type(visual) is dict
    plan_text = "\n".join(lines)
    if visual["kind"] == "external_ref":
        refs, ref_errors = review_visual_lane_contract.referenced_full_payload_refs(plan_text)
        if (
            ref_errors
            or len(refs) != 1
            or visual["ref"] != refs[0]
        ):
            return [Finding(path, heading_line, "ERROR", "Review-range provenance/visual-contract reference mismatch.")]
    else:
        contract, errors = review_visual_lane_contract.parse_materialized_contract(
            plan_text,
            project_root=repo_root_for_plan_path(path),
            expected_plan_ref=(path.relative_to(repo_root_for_plan_path(path)).as_posix() if path.is_file() else None),
        )
        if contract is None or errors:
            return [Finding(path, heading_line, "ERROR", "Review-range provenance has no parseable inline visual contract.")]
        digest = hashlib.sha256(
            review_visual_lane_contract.render_materialized_contract(contract).encode("utf-8")
        ).hexdigest()
        if visual["sha256"] != digest:
            return [Finding(path, heading_line, "ERROR", "Review-range provenance/inline visual digest mismatch.")]
    return []

def reviewer_plan_line_violation(line: str) -> str | None:
    if TEMP_REVIEWER_FLOW_PATH_RE.search(line):
        return (
            "temporary reviewer helper path `.tmp/*_flow.js` is forbidden in reviewer-facing plan contract. "
            "If standard primitives are insufficient, simplify the proof path or expand scope under a checked-in repo-local review helper."
        )

    lowered = line.lower()
    if "run-code" in lowered and (":::" in lowered or "code=" in lowered):
        return (
            "inline reviewer `run-code` step is forbidden in reviewer-facing plan contract. "
            "Planner must materialize a checked-in repo-local review helper instead of delegating ad-hoc automation to Reviewer."
        )

    return None


def reviewer_artifact_line_violation(line: str) -> str | None:
    if TEMP_REVIEWER_FLOW_PATH_RE.search(line):
        return (
            "Ad-hoc reviewer automation detected: `.tmp/*_flow.js` cannot be a proof source of truth. "
            "Stop the loop and return the plan to Architect/Planner for checked-in helper scope expansion."
        )

    lowered = line.lower()
    if "run-code" in lowered and (":::" in lowered or "code=" in lowered):
        return (
            "Ad-hoc reviewer automation detected: inline `run-code` proof path is forbidden. "
            "Use a checked-in repo-local review helper or simplify the proof path instead of closing review on temp automation."
        )

    return None


def validate_reviewer_proof_contract(path: Path, lines: list[str]) -> list[Finding]:
    if not is_reviewer_ad_hoc_automation_ban_enforced(path):
        return []

    findings: list[Finding] = []

    visual_section = slice_h2_section(lines, VISUAL_ACCEPTANCE_RE)
    if visual_section:
        visual_line_no, visual_body = visual_section
        active_subsection: str | None = None

        for idx, line in enumerate(visual_body):
            line_no = visual_line_no + idx + 1
            if HOW_TO_RUN_REVIEWER_HEADING_RE.match(line):
                active_subsection = "### How to run (Reviewer)"
                continue
            if VISUAL_CHECKS_HEADING_RE.match(line):
                active_subsection = "### Visual checks (screenshots required for UI tasks)"
                continue
            if SECTION_HEADING_RE.match(line):
                active_subsection = None
                continue
            if not active_subsection:
                continue

            violation = reviewer_plan_line_violation(line)
            if not violation:
                continue
            findings.append(Finding(path, line_no, "ERROR", f"{active_subsection}: {violation}"))

    plan_repo_root = repo_root_for_plan_path(path)
    for _, rel_path_str in extract_review_artifact_refs(lines):
        artifact_path = (plan_repo_root / rel_path_str).resolve()
        if not artifact_path.is_file():
            continue

        for line_no, line in enumerate(read_text(artifact_path), start=1):
            violation = reviewer_artifact_line_violation(line)
            if not violation:
                continue
            findings.append(Finding(artifact_path, line_no, "ERROR", violation))

    return findings


def extract_code_draft_target_paths(code_draft_path: Path) -> list[str] | None:
    blocks = extract_json_code_blocks(read_text(code_draft_path))
    code_draft_meta: dict | None = None

    for _, text in blocks:
        if "code_draft_meta" not in text:
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return None

        if isinstance(parsed, dict) and isinstance(parsed.get("code_draft_meta"), dict):
            code_draft_meta = parsed["code_draft_meta"]
            break

    if code_draft_meta is None:
        return None

    raw_targets = code_draft_meta.get("targets")
    if not isinstance(raw_targets, list) or not raw_targets:
        return None

    target_paths: list[str] = []
    for item in raw_targets:
        if not isinstance(item, dict):
            return None
        raw_path = item.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            return None
        target_paths.append(raw_path.strip())

    return target_paths


def extract_code_draft_meta(code_draft_path: Path) -> tuple[dict | None, str | None]:
    blocks = extract_json_code_blocks(read_text(code_draft_path))
    saw_code_draft_meta_marker = False

    for _, text in blocks:
        if "code_draft_meta" not in text:
            continue
        saw_code_draft_meta_marker = True
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            return None, f"invalid JSON around code_draft_meta ({exc.msg})"

        if not isinstance(parsed, dict) or "code_draft_meta" not in parsed:
            continue
        meta = parsed.get("code_draft_meta")
        if not isinstance(meta, dict):
            return None, "code_draft_meta must be a top-level JSON object"
        return meta, None

    if saw_code_draft_meta_marker:
        return None, "missing top-level code_draft_meta object"
    return None, "missing code_draft_meta JSON block"


def select_primary_code_draft_path(
    plan_path: Path,
    code_draft_refs: list[tuple[int, str]],
    *,
    plan_repo_root: Path,
) -> Path | None:
    if not code_draft_refs:
        return None

    expected_rel = f"docs/code_drafts/{plan_path.stem}__code_draft.md"
    ordered_refs = [rel_path_str for _, rel_path_str in code_draft_refs]
    if expected_rel in ordered_refs:
        ordered_refs = [expected_rel] + [rel_path_str for rel_path_str in ordered_refs if rel_path_str != expected_rel]

    for rel_path_str in ordered_refs:
        candidate = (plan_repo_root / rel_path_str).resolve()
        if candidate.exists():
            return candidate
    return None


def same_file_object(origin_plan: Path, target: Path) -> bool:
    """Compare two caller-validated existing paths by filesystem object identity."""

    return origin_plan.samefile(target)


def _valid_immutable_range_review(lines: list[str], plan_type: str | None) -> bool:
    if plan_type != "review-only":
        return False
    review_targets = [
        match.group("value")
        for line in lines
        if (match := PLAN_REVIEW_TARGET_LINE_RE.match(line))
    ]
    return (
        len(review_targets) == 1
        and IMMUTABLE_RANGE_REVIEW_TARGET_RE.fullmatch(review_targets[0]) is not None
    )


def _valid_immutable_commit_review(
    lines: list[str],
    *,
    plan_repo_root: Path,
) -> bool:
    review_targets = [
        match.group("value")
        for line in lines
        if (match := PLAN_REVIEW_TARGET_LINE_RE.match(line))
    ]
    if len(review_targets) != 1:
        return False
    match = IMMUTABLE_COMMIT_REVIEW_TARGET_RE.fullmatch(review_targets[0])
    if match is None:
        return False

    commit_ref = review_targets[0].split("=", 1)[1]
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(plan_repo_root),
                "rev-parse",
                "--verify",
                "--quiet",
                "--end-of-options",
                f"{commit_ref}^{{commit}}",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    resolved = result.stdout.strip()
    return (
        result.returncode == 0
        and len(resolved.splitlines()) == 1
        and re.fullmatch(r"[0-9a-f]{40,64}", resolved, re.IGNORECASE) is not None
    )


def _parked_reference_plan(lines: list[str], plan_meta_obj: dict | None) -> bool:
    if not isinstance(plan_meta_obj, dict) or plan_meta_obj.get("phase_state") != "parked":
        return False

    code_draft_na_re = re.compile(
        r"^\s*-\s*Code draft(?:\(s\)|s)?:\s*`?N/A \(why=[^)]+\)`?\s*$",
        re.IGNORECASE,
    )
    if not any(code_draft_na_re.match(line) for line in lines):
        return False

    verification_start = next(
        (
            index
            for index, line in enumerate(lines)
            if line.strip().lower() == "## verification rerun / exec handoff"
        ),
        None,
    )
    if verification_start is None:
        return False
    verification_lines: list[str] = []
    for line in lines[verification_start + 1 :]:
        if line.startswith("## "):
            break
        verification_lines.append(line)
    required_na_fields = ("mode", "command", "expected artifact")
    return all(
        any(
            re.match(
                rf"^\s*-\s*{re.escape(field)}:\s*`?N/A \(why=[^)]+\)`?\s*$",
                line,
                re.IGNORECASE,
            )
            for line in verification_lines
        )
        for field in required_na_fields
    )


def _origin_plan_review_target_classification(
    *,
    lines: list[str],
    plan_type: str | None,
    raw_status_value: str | None,
    plan_meta_obj: dict | None,
    plan_repo_root: Path,
) -> str | None:
    if _valid_immutable_commit_review(lines, plan_repo_root=plan_repo_root):
        return None
    if _valid_immutable_range_review(lines, plan_type):
        return "range_exempt"
    raw_status_norm = " ".join((raw_status_value or "").strip().lower().split())
    if raw_status_norm in ORIGIN_PLAN_TERMINAL_STATUS_NORMS:
        return "terminal_history"
    if _parked_reference_plan(lines, plan_meta_obj):
        return "parked_reference"
    return "restamp_before_handoff"


def validate_origin_plan_review_targets(
    path: Path,
    lines: list[str],
    *,
    raw_status_value: str | None,
    effective_status_value: str | None,
    plan_type: str | None,
    plan_meta_obj: dict | None,
    code_draft_refs: list[tuple[int, str]],
    plan_repo_root: Path,
) -> list[Finding]:
    """Reject current-bundle targets that are the same file object as the origin plan."""

    code_draft_path = select_primary_code_draft_path(
        path,
        code_draft_refs,
        plan_repo_root=plan_repo_root,
    )
    if code_draft_path is None:
        return []

    meta, error = extract_code_draft_meta(code_draft_path)
    if error or meta is None:
        return []
    raw_targets = meta.get("targets")
    if not isinstance(raw_targets, list) or not raw_targets:
        return []

    origin_abs = path.resolve()
    has_origin_target = False
    for item in raw_targets:
        if not isinstance(item, dict):
            continue
        raw_path = item.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            continue
        target_path = Path(raw_path)
        try:
            target_abs = (
                target_path.resolve()
                if target_path.is_absolute()
                else (plan_repo_root / target_path).resolve()
            )
            if not target_abs.exists() or not target_abs.is_file():
                continue
            if same_file_object(origin_abs, target_abs):
                has_origin_target = True
                break
        except (OSError, ValueError):
            # Caller-owned path diagnostics retain precedence over this identity-only guard.
            continue

    if not has_origin_target:
        return []
    classification = _origin_plan_review_target_classification(
        lines=lines,
        plan_type=plan_type,
        raw_status_value=raw_status_value,
        plan_meta_obj=plan_meta_obj,
        plan_repo_root=plan_repo_root,
    )
    if classification is None:
        return []
    raw_status_norm = " ".join((raw_status_value or "").strip().lower().split())
    effective_status_norm = " ".join((effective_status_value or "").strip().lower().split())
    is_prospective_done = (
        effective_status_norm == "done"
        and raw_status_norm not in ORIGIN_PLAN_TERMINAL_STATUS_NORMS
    )
    is_early_dev = (
        plan_type == "dev"
        and raw_status_norm in ORIGIN_PLAN_EARLY_DEV_STATUS_NORMS
        and not is_prospective_done
    )
    severity = (
        "WARN"
        if classification != "restamp_before_handoff" or is_early_dev
        else "ERROR"
    )
    ref_line_no = next(
        (
            line_no
            for line_no, rel_path in code_draft_refs
            if (plan_repo_root / rel_path).resolve() == code_draft_path
        ),
        1,
    )
    return [
        Finding(
            path,
            ref_line_no,
            severity,
            f"{ORIGIN_PLAN_IN_REVIEW_TARGETS_REASON}: "
            "`code_draft_meta.targets` contains the origin plan file object; "
            f"classification={classification}. Keep `PLAN_PATH` in the final exact bundle "
            "but outside reviewed target bytes.",
        )
    ]


def is_exact_bundle_preflight_enforced(status_value: str | None) -> bool:
    if not status_value:
        return False
    return status_value.strip().lower() in {"planner finalize", "ready for coder"}


def is_exact_bundle_preflight_advisory(status_value: str | None) -> bool:
    if not status_value:
        return False
    return status_value.strip().lower() in EXACT_BUNDLE_ADVISORY_STATUS_NORMS


def validate_exact_bundle_preflight(
    path: Path,
    *,
    status_value: str | None,
    code_draft_refs: list[tuple[int, str]],
    plan_repo_root: Path,
) -> list[Finding]:
    findings: list[Finding] = []
    enforced = is_exact_bundle_preflight_enforced(status_value)
    advisory = is_exact_bundle_preflight_advisory(status_value) and bool(code_draft_refs)
    if not enforced and not advisory:
        return findings

    code_draft_path = select_primary_code_draft_path(path, code_draft_refs, plan_repo_root=plan_repo_root)
    if code_draft_path is None:
        return findings

    severity = "ERROR" if enforced else "WARN"
    prefix = "Planner exact-bundle preflight failed" if enforced else "Planner exact-bundle seed warning"
    suffix = (
        "For the first executable handoff run `planveyor_plan_bundle --preflight <PLAN_PATH>` through the external facade. "
        "Genuine refinement with a materialized live review uses `planveyor_plan_bundle --scope-check <PLAN_PATH>` "
        "for inventory only; contract/lint/machine-authority/handoff gates, semantic lint/derived handoff digest "
        "and same-contract skip-Planner remain unchanged. Scope does not grant green/route/commit; final --check stays strict."
        if enforced
        else "This is advisory seed hygiene before `Planner finalize`; Planner hard gate remains fail-closed before `Ready for Coder`."
    )
    ref_line_no = next(
        (line_no for line_no, rel_path in code_draft_refs if (plan_repo_root / rel_path).resolve() == code_draft_path),
        1,
    )
    meta, error = extract_code_draft_meta(code_draft_path)
    if error or meta is None:
        findings.append(
            Finding(
                path,
                ref_line_no,
                severity,
                f"{prefix}: "
                f"{error or 'invalid code_draft_meta'} in `{repo_relative_display(code_draft_path, plan_repo_root)}`. "
                f"{suffix}",
            )
        )
        return findings

    expected_plan = repo_relative_display(path, plan_repo_root)
    if meta.get("plan") != expected_plan:
        findings.append(
            Finding(
                path,
                ref_line_no,
                severity,
                f"{prefix}: "
                f"`code_draft_meta.plan` must be `{expected_plan}` before `Ready for Coder` "
                f"(got {meta.get('plan')!r}).",
            )
        )

    raw_targets = meta.get("targets")
    if not isinstance(raw_targets, list) or not raw_targets:
        findings.append(
            Finding(
                path,
                ref_line_no,
                severity,
                f"{prefix}: `code_draft_meta.targets` must be a non-empty list before `Ready for Coder`.",
            )
        )
        return findings

    for item in raw_targets:
        if not isinstance(item, dict):
            findings.append(
                Finding(
                    path,
                    ref_line_no,
                    severity,
                    f"{prefix}: invalid target entry {item!r}.",
                )
            )
            continue
        raw_path = item.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            findings.append(
                Finding(
                    path,
                    ref_line_no,
                    severity,
                    f"{prefix}: invalid target path in {item!r}.",
                )
            )
            continue
        target_path = Path(raw_path)
        target_abs = target_path.resolve() if target_path.is_absolute() else (plan_repo_root / target_path).resolve()
        if not target_abs.exists():
            findings.append(
                Finding(
                    path,
                    ref_line_no,
                    severity,
                    f"{prefix}: "
                    f"`code_draft_meta.targets` contains missing/stale path `{raw_path}`.",
                )
            )

    raw_deleted_paths = meta.get("deleted_paths", [])
    if raw_deleted_paths is None:
        raw_deleted_paths = []
    if not isinstance(raw_deleted_paths, list):
        findings.append(
            Finding(
                path,
                ref_line_no,
                severity,
                f"{prefix}: `code_draft_meta.deleted_paths` must be a list when present.",
            )
        )
        return findings

    for item in raw_deleted_paths:
        if not isinstance(item, dict):
            findings.append(
                Finding(
                    path,
                    ref_line_no,
                    severity,
                    f"{prefix}: invalid deleted_path entry {item!r}.",
                )
            )
            continue
        raw_path = item.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            findings.append(
                Finding(
                    path,
                    ref_line_no,
                    severity,
                    f"{prefix}: invalid deleted_path path in {item!r}.",
                )
            )
            continue
        is_review_only = item.get("review_only") is True or str(item.get("kind") or "").strip().lower() == "review_only"
        base_ref = str(item.get("base_ref") or "").strip()
        deletion_ref = str(item.get("deletion_ref") or item.get("deleted_ref") or "").strip()
        if is_review_only and (not base_ref or not deletion_ref):
            findings.append(
                Finding(
                    path,
                    ref_line_no,
                    severity,
                    f"{prefix}: review-only `code_draft_meta.deleted_paths` entry `{raw_path}` "
                    "must declare non-empty `base_ref` and `deletion_ref`.",
                )
            )
        deleted_path = Path(raw_path)
        deleted_abs = deleted_path.resolve() if deleted_path.is_absolute() else (plan_repo_root / deleted_path).resolve()
        deleted_repo_root = repo_root_for_fs_path(deleted_abs)
        if deleted_repo_root is None:
            findings.append(
                Finding(
                    path,
                    ref_line_no,
                    severity,
                    f"{prefix}: "
                    f"`code_draft_meta.deleted_paths` contains non-repo path `{raw_path}`.",
                )
            )
            continue
        try:
            deleted_rel = str(deleted_abs.relative_to(deleted_repo_root))
        except ValueError:
            findings.append(
                Finding(
                    path,
                    ref_line_no,
                    severity,
                    f"{prefix}: "
                    f"`code_draft_meta.deleted_paths` path `{raw_path}` is outside its git root.",
                )
            )
            continue
        deletion_source_exists = (
            git_ref_contains_path(deleted_repo_root, base_ref, deleted_rel)
            if is_review_only and base_ref
            else git_head_contains_path(deleted_repo_root, deleted_rel)
        )
        if not deletion_source_exists:
            findings.append(
                Finding(
                    path,
                    ref_line_no,
                    severity,
                    f"{prefix}: "
                    f"`code_draft_meta.deleted_paths` contains untracked/missing deletion path `{raw_path}`.",
                )
            )
        if is_review_only and deletion_ref and git_ref_contains_path(deleted_repo_root, deletion_ref, deleted_rel):
            findings.append(
                Finding(
                    path,
                    ref_line_no,
                    severity,
                    f"{prefix}: review-only `code_draft_meta.deleted_paths` entry `{raw_path}` "
                    f"uses deletion_ref `{deletion_ref}` that still contains the path.",
                )
            )

    return findings


def state_transition_declaration_value_is_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    return (
        normalized in STATE_TRANSITION_DECLARATION_PLACEHOLDERS
        or bool(STATE_TRANSITION_DECLARATION_PLACEHOLDER_PREFIX_RE.match(normalized))
        or ("<" in normalized and ">" in normalized)
    )


def normalize_state_transition_protected_path(value: object) -> tuple[str | None, str | None]:
    if not isinstance(value, str) or not value or value != value.strip():
        return None, "must be a non-empty trimmed repo-relative POSIX path"
    if value.startswith("/") or "\\" in value:
        return None, "must be repo-relative POSIX, not absolute or backslash-separated"

    raw_parts = value.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        return None, "must not contain empty, `.` or `..` path segments"

    normalized = str(PurePosixPath(value))
    if normalized != value:
        return None, "must already be a normalized repo-relative POSIX path"
    return normalized, None


def state_transition_declaration_inline_code_marker_end(
    line: str,
    start: int,
    marker_length: int,
) -> int | None:
    """Return the end of the next equal-length backtick run, if present."""

    index = start
    while index < len(line):
        if line[index] != "`":
            index += 1
            continue
        marker_end = index
        while marker_end < len(line) and line[marker_end] == "`":
            marker_end += 1
        if marker_end - index == marker_length:
            return marker_end
        index = marker_end
    return None


def state_transition_declaration_markdown_columns(text: str) -> int:
    """Return the rendered column width with four-column tabs."""

    columns = 0
    for character in text:
        if character == "\t":
            columns += 4 - columns % 4
        else:
            columns += 1
    return columns


def state_transition_declaration_leading_indent_columns(line: str) -> int:
    """Return the leading Markdown indentation width with four-column tabs."""

    index = 0
    while index < len(line) and line[index] in {" ", "\t"}:
        index += 1
    return state_transition_declaration_markdown_columns(line[:index])


def state_transition_declaration_line_is_indented_code(line: str) -> bool:
    """Return whether a line starts an indented Markdown code block."""

    return state_transition_declaration_leading_indent_columns(line) >= 4


def state_transition_declaration_list_continuation_indent(line: str) -> int | None:
    """Return the content indentation of a top-level Markdown list item."""

    match = re.match(r"^ {0,3}(?:[-+*]|\d+[.)])(?:(?P<whitespace>[ \t]+)|$)", line)
    if match is None:
        return None
    whitespace = match.group("whitespace") or ""
    marker_end = match.start("whitespace") if whitespace else match.end()
    marker_width = state_transition_declaration_markdown_columns(line[:marker_end])
    if not whitespace or match.end() == len(line):
        return marker_width + 1
    whitespace_width = state_transition_declaration_markdown_columns(line[: match.end()]) - marker_width
    return marker_width + (whitespace_width if whitespace_width <= 4 else 1)


def state_transition_declaration_line_starts_top_level_block(line: str) -> bool:
    """Return whether a line cannot be a lazy continuation of a container paragraph."""

    return bool(
        re.match(r"^ {0,3}#{1,6}[ \t]+", line)
        or STATE_TRANSITION_DECLARATION_FENCE_START_RE.match(line)
    )


def state_transition_declaration_inline_code_line_is_block_boundary(line: str) -> bool:
    """Return whether a line ends the paragraph containing an inline code span."""

    return state_transition_declaration_line_is_indented_code(line) or not line.strip() or bool(
        re.match(r"^ {0,3}#{1,6}[ \t]+", line)
        or STATE_TRANSITION_DECLARATION_FENCE_START_RE.match(line)
    )


def state_transition_declaration_has_inline_code_closer(
    lines: Sequence[str],
    marker_length: int,
) -> bool:
    """Return whether an unclosed marker can form a cross-line code span."""

    for line in lines:
        if state_transition_declaration_inline_code_line_is_block_boundary(line):
            return False
        if state_transition_declaration_inline_code_marker_end(line, 0, marker_length) is not None:
            return True
    return False


def state_transition_declaration_mask_html_tag_attributes(
    text: str,
    *,
    html_tag_open: bool,
    html_attribute_quote: str | None,
) -> tuple[str, bool, str | None]:
    """Mask quoted raw-HTML attribute values before locating comment openers."""

    masked = list(text)
    index = 0
    while index < len(text):
        character = text[index]
        if html_attribute_quote is not None:
            masked[index] = " "
            if character == html_attribute_quote:
                html_attribute_quote = None
            index += 1
            continue
        if html_tag_open:
            if character in {"\"", "'"}:
                masked[index] = " "
                html_attribute_quote = character
            elif character == ">":
                html_tag_open = False
            index += 1
            continue
        if character == "<":
            name_index = index + 1
            if name_index < len(text) and text[name_index] == "/":
                name_index += 1
            if name_index < len(text) and text[name_index].isalpha():
                html_tag_open = True
        index += 1
    return "".join(masked), html_tag_open, html_attribute_quote


def state_transition_declaration_mask_inline_link_destinations(text: str) -> str:
    """Mask complete Markdown inline-link destinations and titles."""

    masked = list(text)
    index = 0
    while (link_end := text.find("](", index)) != -1:
        destination_start = link_end + 1
        cursor = destination_start
        parentheses = 0
        quote: str | None = None
        while cursor < len(text):
            character = text[cursor]
            if character == "\\":
                cursor += 2
                continue
            if quote is not None:
                if character == quote:
                    quote = None
            elif character in {"\"", "'"}:
                quote = character
            elif character == "(":
                parentheses += 1
            elif character == ")":
                parentheses -= 1
                if parentheses == 0:
                    label_start = text.rfind("[", 0, link_end)
                    mask_start = label_start if label_start != -1 else destination_start
                    for masked_index in range(mask_start, cursor + 1):
                        masked[masked_index] = " "
                    index = cursor + 1
                    break
            cursor += 1
        else:
            index = destination_start
    return "".join(masked)


def state_transition_declaration_mask_full_reference_links(text: str) -> str:
    """Mask complete Markdown full-reference link labels."""

    masked = list(text)
    for match in re.finditer(r"(?<!\\)\[[^\]\r\n]*\]\[[^\]\r\n]*\]", text):
        for masked_index in range(match.start(), match.end()):
            masked[masked_index] = " "
    return "".join(masked)


def state_transition_declaration_reference_label_normalized(label: str) -> str:
    """Return the CommonMark comparison form of a reference label."""

    return re.sub(r"[ \t]+", " ", label).strip().casefold()


def state_transition_declaration_reference_definition_labels(lines: Sequence[str]) -> set[str]:
    """Return normalized labels defined by Markdown reference definitions."""

    labels: set[str] = set()
    for line in lines:
        if (match := re.match(r"^ {0,3}\[(?P<label>[^\]\r\n]+)\]:", line)) is not None:
            labels.add(state_transition_declaration_reference_label_normalized(match.group("label")))
    return labels


def state_transition_declaration_mask_reference_definition_label(text: str) -> str:
    """Mask a complete Markdown reference-definition label."""

    match = re.match(r"^ {0,3}\[(?P<label>[^\]\r\n]+)\]:", text)
    if match is None:
        return text
    masked = list(text)
    for masked_index in range(match.start(), match.end()):
        masked[masked_index] = " "
    return "".join(masked)


def state_transition_declaration_mask_shortcut_reference_links(text: str, reference_labels: set[str]) -> str:
    """Mask complete shortcut-reference link labels known to have a definition."""

    masked = list(text)
    for match in re.finditer(r"(?<!\\)\[(?P<label>[^\]\r\n]+)\](?![\[(:])", text):
        if state_transition_declaration_reference_label_normalized(match.group("label")) in reference_labels:
            for masked_index in range(match.start(), match.end()):
                masked[masked_index] = " "
    return "".join(masked)


def state_transition_declaration_reference_definition_destination_end(text: str) -> int | None:
    """Return the offset after a Markdown reference-definition destination."""

    match = re.match(r"^ {0,3}\[[^\]\r\n]+\]:[ \t]+", text)
    if match is None:
        return None
    cursor = match.end()
    if cursor < len(text) and text[cursor] == "<":
        destination_end = text.find(">", cursor + 1)
        if destination_end == -1:
            return None
        return destination_end + 1
    destination_start = cursor
    while cursor < len(text) and text[cursor] not in {" ", "\t"}:
        cursor += 1
    return cursor if cursor > destination_start else None


def state_transition_declaration_mask_quoted_markdown_title(
    text: str,
    *,
    title_start: int,
    require_line_end: bool,
) -> str:
    """Mask a complete Markdown title at the given delimiter."""

    if text[title_start] not in {"\"", "'", "("}:
        return text
    closer = ")" if text[title_start] == "(" else text[title_start]
    cursor = title_start + 1
    while cursor < len(text):
        if text[cursor] == "\\":
            cursor += 2
            continue
        if text[cursor] == closer:
            if require_line_end and text[cursor + 1 :].strip():
                return text
            masked = list(text)
            for masked_index in range(title_start, cursor + 1):
                masked[masked_index] = " "
            return "".join(masked)
        cursor += 1
    return text


def state_transition_declaration_mask_reference_definition_title(text: str) -> str:
    """Mask a complete same-line quoted title in a Markdown reference definition."""

    cursor = state_transition_declaration_reference_definition_destination_end(text)
    if cursor is None:
        return text
    while cursor < len(text) and text[cursor] in {" ", "\t"}:
        cursor += 1
    if cursor >= len(text):
        return text
    return state_transition_declaration_mask_quoted_markdown_title(
        text,
        title_start=cursor,
        require_line_end=False,
    )


def state_transition_declaration_mask_reference_definition_continuation_title(text: str) -> str:
    """Mask a complete next-line quoted title in a Markdown reference definition."""

    match = re.match(r"^ {0,3}(?P<delimiter>[\"'(])", text)
    if match is None:
        return text
    return state_transition_declaration_mask_quoted_markdown_title(
        text,
        title_start=match.start("delimiter"),
        require_line_end=True,
    )


def state_transition_declaration_reference_definition_title_continuation_lines(
    lines: Sequence[str],
) -> set[int]:
    """Return one-based line numbers that are valid next-line reference titles."""

    continuation_lines: set[int] = set()
    for index, line in enumerate(lines[:-1]):
        destination_end = state_transition_declaration_reference_definition_destination_end(line)
        if destination_end is None or line[destination_end:].strip():
            continue
        if state_transition_declaration_mask_reference_definition_continuation_title(lines[index + 1]) != lines[index + 1]:
            continuation_lines.add(index + 2)
    return continuation_lines


def state_transition_declaration_raw_html_block_start_tag(text: str) -> str | None:
    """Return the CommonMark type-1 raw HTML block tag starting this line."""

    match = STATE_TRANSITION_DECLARATION_RAW_HTML_BLOCK_START_RE.match(text)
    return match.group("tag").lower() if match is not None else None


def state_transition_declaration_raw_html_block_closes(line: str, tag: str) -> bool:
    """Return whether a raw HTML block closes on this line."""

    return bool(re.search(rf"</{re.escape(tag)}[ \t]*>", line, re.IGNORECASE))


def state_transition_declaration_raw_html_literal_block_end_marker(text: str) -> str | None:
    """Return the terminator for a non-comment CommonMark raw HTML block."""

    if STATE_TRANSITION_DECLARATION_CDATA_BLOCK_START_RE.match(text):
        return "]]>"
    if STATE_TRANSITION_DECLARATION_PROCESSING_INSTRUCTION_BLOCK_START_RE.match(text):
        return "?>"
    if STATE_TRANSITION_DECLARATION_DECLARATION_BLOCK_START_RE.match(text):
        return ">"
    return None


def state_transition_declaration_comment_text(
    line: str,
    inline_code_marker_length: int | None,
    following_lines: Sequence[str],
    html_tag_open: bool,
    html_attribute_quote: str | None,
    reference_labels: set[str],
    reference_definition_title_continuation: bool,
) -> tuple[str, int | None, bool, str | None]:
    """Mask inline-code spans before looking for HTML comments.

    Markdown code spans may continue across lines, so the active delimiter length
    is returned for the next line when a span remains open.
    """

    masked = list(line)
    index = 0
    while index < len(line):
        if inline_code_marker_length is not None:
            marker_start = index
            marker_end = state_transition_declaration_inline_code_marker_end(
                line,
                index,
                inline_code_marker_length,
            )
            if marker_end is None:
                for masked_index in range(marker_start, len(line)):
                    masked[masked_index] = " "
                break
            for masked_index in range(marker_start, marker_end):
                masked[masked_index] = " "
            index = marker_end
            inline_code_marker_length = None
            continue

        if line[index] != "`":
            index += 1
            continue

        marker_start = index
        while index < len(line) and line[index] == "`":
            index += 1
        marker_length = index - marker_start
        marker_end = state_transition_declaration_inline_code_marker_end(line, index, marker_length)
        if marker_end is not None:
            for masked_index in range(marker_start, marker_end):
                masked[masked_index] = " "
            index = marker_end
            continue
        if state_transition_declaration_has_inline_code_closer(following_lines, marker_length):
            for masked_index in range(marker_start, len(line)):
                masked[masked_index] = " "
            inline_code_marker_length = marker_length
            break
        index = marker_start + marker_length

    comment_text, html_tag_open, html_attribute_quote = state_transition_declaration_mask_html_tag_attributes(
        "".join(masked),
        html_tag_open=html_tag_open,
        html_attribute_quote=html_attribute_quote,
    )
    comment_text = state_transition_declaration_mask_inline_link_destinations(comment_text)
    comment_text = state_transition_declaration_mask_full_reference_links(comment_text)
    comment_text = state_transition_declaration_mask_reference_definition_title(comment_text)
    if reference_definition_title_continuation:
        comment_text = state_transition_declaration_mask_reference_definition_continuation_title(comment_text)
    comment_text = state_transition_declaration_mask_reference_definition_label(comment_text)
    comment_text = state_transition_declaration_mask_shortcut_reference_links(comment_text, reference_labels)
    return comment_text, inline_code_marker_length, html_tag_open, html_attribute_quote


def state_transition_declaration_html_comment_opener_index(text: str) -> int | None:
    """Return the first HTML-comment opener not escaped in Markdown text.

    An odd run of backslashes directly before the opener escapes its ``<``.
    """

    index = text.find("<!--")
    while index != -1:
        backslash_count = 0
        preceding_index = index - 1
        while preceding_index >= 0 and text[preceding_index] == "\\":
            backslash_count += 1
            preceding_index -= 1
        if backslash_count % 2 == 0:
            return index
        index = text.find("<!--", index + len("<!--"))
    return None


def state_transition_declaration_html_comment_opener_can_carry_state(
    *,
    line: str,
    in_markdown_container: bool,
) -> bool:
    """Return whether an opener may carry HTML-comment state to a later block.

    CommonMark type-2 HTML blocks begin only at the start of a line after at
    most three spaces. A mid-line raw HTML comment remains inline and cannot
    hide a following declaration heading. Use the original line here: masking
    an inline-code prefix can otherwise make an inline opener look block-level.
    """

    return not in_markdown_container and bool(re.match(r"^ {0,3}<!--", line))


def state_transition_declaration_blocks(
    lines: list[str],
) -> list[tuple[int, bool, list[tuple[int, str]]]]:
    """Collect opt-in H3 blocks within active reviewability-receipt H2 sections.

    HTML comments are deliberately ignored so the non-active template examples do
    not opt every generated artifact into structural validation.
    """

    blocks: list[tuple[int, bool, list[tuple[int, str]]]] = []
    receipt_active = False
    current_heading_line: int | None = None
    current_heading_is_canonical = False
    current_body: list[tuple[int, str]] = []
    fence_marker: str | None = None
    in_html_comment = False
    raw_html_block_tag: str | None = None
    raw_html_literal_block_end_marker: str | None = None
    inline_code_marker_length: int | None = None
    html_tag_open = False
    html_attribute_quote: str | None = None
    reference_labels = state_transition_declaration_reference_definition_labels(lines)
    reference_definition_title_continuation_lines = (
        state_transition_declaration_reference_definition_title_continuation_lines(lines)
    )
    list_continuation_indents: list[int] = []
    list_allows_lazy_continuation = False
    blockquote_allows_lazy_continuation = False

    def close_current() -> None:
        nonlocal current_heading_line, current_heading_is_canonical, current_body
        if current_heading_line is not None:
            blocks.append((current_heading_line, current_heading_is_canonical, current_body))
        current_heading_line = None
        current_heading_is_canonical = False
        current_body = []

    for line_no, line in enumerate(lines, start=1):
        if fence_marker is not None:
            if re.match(rf"^ {{0,3}}{re.escape(fence_marker[0])}{{{len(fence_marker)},}}[ \t]*$", line):
                fence_marker = None
            continue
        if raw_html_block_tag is not None:
            if state_transition_declaration_raw_html_block_closes(line, raw_html_block_tag):
                raw_html_block_tag = None
            continue
        if raw_html_literal_block_end_marker is not None:
            if raw_html_literal_block_end_marker in line:
                raw_html_literal_block_end_marker = None
            continue
        if in_html_comment:
            if "-->" in line:
                in_html_comment = False
            continue
        if state_transition_declaration_line_is_indented_code(line):
            continue
        list_marker_indent = state_transition_declaration_list_continuation_indent(line)
        leading_indent = state_transition_declaration_leading_indent_columns(line)
        line_is_blank = not line.strip()
        line_starts_top_level_block = state_transition_declaration_line_starts_top_level_block(line)
        line_starts_html_comment = bool(re.match(r"^ {0,3}<!--", line))
        line_starts_blockquote = bool(re.match(r"^ {0,3}>[ \t]?", line))
        if line_is_blank:
            list_allows_lazy_continuation = False
            blockquote_allows_lazy_continuation = False
        elif list_marker_indent is not None:
            while list_continuation_indents and list_continuation_indents[-1] >= list_marker_indent:
                list_continuation_indents.pop()
            list_continuation_indents.append(list_marker_indent)
            list_allows_lazy_continuation = True
        elif list_continuation_indents:
            narrowed_indents = list(list_continuation_indents)
            while narrowed_indents and leading_indent < narrowed_indents[-1]:
                narrowed_indents.pop()
            if narrowed_indents:
                list_continuation_indents = narrowed_indents
                list_allows_lazy_continuation = True
            elif line_starts_top_level_block or line_starts_html_comment or not list_allows_lazy_continuation:
                list_continuation_indents.clear()
        if line_starts_blockquote:
            blockquote_allows_lazy_continuation = True
        elif line_starts_top_level_block or line_starts_html_comment:
            blockquote_allows_lazy_continuation = False
        in_markdown_container = bool(list_continuation_indents) or blockquote_allows_lazy_continuation
        if (
            inline_code_marker_length is not None
            and state_transition_declaration_inline_code_line_is_block_boundary(line)
        ):
            inline_code_marker_length = None
        was_in_inline_code = inline_code_marker_length is not None
        if not was_in_inline_code and (fence_match := STATE_TRANSITION_DECLARATION_FENCE_START_RE.match(line)):
            fence_marker = fence_match.group("marker")
            continue
        comment_text, inline_code_marker_length, html_tag_open, html_attribute_quote = state_transition_declaration_comment_text(
            line,
            inline_code_marker_length,
            lines[line_no:],
            html_tag_open,
            html_attribute_quote,
            reference_labels,
            line_no in reference_definition_title_continuation_lines,
        )
        if (raw_html_tag := state_transition_declaration_raw_html_block_start_tag(comment_text)) is not None:
            if not state_transition_declaration_raw_html_block_closes(line, raw_html_tag):
                raw_html_block_tag = raw_html_tag
            inline_code_marker_length = None
            html_tag_open = False
            html_attribute_quote = None
            continue
        if (literal_block_end_marker := state_transition_declaration_raw_html_literal_block_end_marker(comment_text)) is not None:
            if literal_block_end_marker not in line:
                raw_html_literal_block_end_marker = literal_block_end_marker
            inline_code_marker_length = None
            html_tag_open = False
            html_attribute_quote = None
            continue
        if (comment_opener_index := state_transition_declaration_html_comment_opener_index(comment_text)) is not None:
            if (
                "-->" not in line[comment_opener_index + len("<!--") :]
                and state_transition_declaration_html_comment_opener_can_carry_state(
                    line=line,
                    in_markdown_container=in_markdown_container,
                )
            ):
                in_html_comment = True
            continue
        if was_in_inline_code:
            continue

        if STATE_TRANSITION_DECLARATION_H2_HEADING_RE.match(line):
            close_current()
            receipt_active = bool(REVIEWABILITY_PREFLIGHT_RECEIPT_HEADING_RE.match(line))
            continue

        if not receipt_active:
            continue

        if re.match(r"^ {0,3}###[ \t]+", line):
            close_current()
            if STATE_TRANSITION_DECLARATIONS_HEADING_CANDIDATE_RE.match(line):
                current_heading_line = line_no
                current_heading_is_canonical = bool(STATE_TRANSITION_DECLARATIONS_HEADING_RE.match(line))
            continue

        if current_heading_line is not None:
            current_body.append((line_no, line))

    close_current()
    return blocks


def parse_state_transition_declaration_value(
    *,
    path: Path,
    line_no: int,
    label: str,
    value: str,
) -> tuple[tuple[tuple[str, str | tuple[str, ...]], ...] | None, list[Finding]]:
    findings: list[Finding] = []
    expected_subfields = STATE_TRANSITION_DECLARATION_SUBFIELDS[label]
    if not value or "`" in value:
        findings.append(
            Finding(
                path,
                line_no,
                "ERROR",
                f"State-transition declarations `{label}` must use an unquoted single-line value.",
            )
        )
        return None, findings

    parsed_fields: dict[str, str] = {}
    ordered_keys: list[str] = []
    for raw_part in value.split(";"):
        part = raw_part.strip()
        if not part or "=" not in part:
            findings.append(
                Finding(
                    path,
                    line_no,
                    "ERROR",
                    f"State-transition declarations `{label}` has malformed subfield grammar.",
                )
            )
            return None, findings

        raw_key, raw_subvalue = part.split("=", 1)
        key = raw_key.strip()
        raw_subvalue = raw_subvalue.strip()
        if not key or not raw_subvalue:
            findings.append(
                Finding(
                    path,
                    line_no,
                    "ERROR",
                    f"State-transition declarations `{label}` permits whitespace only around subfield separators.",
                )
            )
            return None, findings
        if key in parsed_fields:
            findings.append(
                Finding(
                    path,
                    line_no,
                    "ERROR",
                    f"State-transition declarations `{label}` repeats subfield `{key}`.",
                )
            )
            return None, findings
        parsed_fields[key] = raw_subvalue
        ordered_keys.append(key)

    if tuple(ordered_keys) != expected_subfields or set(parsed_fields) != set(expected_subfields):
        findings.append(
            Finding(
                path,
                line_no,
                "ERROR",
                f"State-transition declarations `{label}` must use exactly ordered subfields "
                f"{', '.join(f'`{field}`' for field in expected_subfields)}.",
            )
        )
        return None, findings

    normalized_fields: list[tuple[str, str | tuple[str, ...]]] = []
    for key in expected_subfields:
        raw_subvalue = parsed_fields[key]
        if key != "targets":
            if state_transition_declaration_value_is_placeholder(raw_subvalue):
                findings.append(
                    Finding(
                        path,
                        line_no,
                        "ERROR",
                        f"State-transition declarations `{label}` contains placeholder `{key}`.",
                    )
                )
                continue
            normalized_fields.append((key, raw_subvalue))
            continue

        try:
            raw_targets = json.loads(raw_subvalue)
        except json.JSONDecodeError:
            findings.append(
                Finding(
                    path,
                    line_no,
                    "ERROR",
                    f"State-transition declarations `{label}` field `targets` must be a JSON array.",
                )
            )
            continue
        if not isinstance(raw_targets, list) or not raw_targets:
            findings.append(
                Finding(
                    path,
                    line_no,
                    "ERROR",
                    f"State-transition declarations `{label}` field `targets` must be a non-empty JSON array.",
                )
            )
            continue
        if any(
            not isinstance(target, str)
            or not target.strip()
            or target != target.strip()
            or state_transition_declaration_value_is_placeholder(target)
            for target in raw_targets
        ):
            findings.append(
                Finding(
                    path,
                    line_no,
                    "ERROR",
                    f"State-transition declarations `{label}` field `targets` must contain non-placeholder strings.",
                )
            )
            continue

        if label == "protected-target post-review continuity":
            normalized_targets: list[str] = []
            target_problem: str | None = None
            for target in raw_targets:
                normalized_target, target_problem = normalize_state_transition_protected_path(target)
                if target_problem:
                    break
                assert normalized_target is not None
                normalized_targets.append(normalized_target)
            if target_problem:
                findings.append(
                    Finding(
                        path,
                        line_no,
                        "ERROR",
                        "State-transition declarations `protected-target post-review continuity` "
                        f"field `targets` {target_problem}.",
                    )
                )
                continue
            if normalized_targets != sorted(normalized_targets) or len(set(normalized_targets)) != len(normalized_targets):
                findings.append(
                    Finding(
                        path,
                        line_no,
                        "ERROR",
                        "State-transition declarations `protected-target post-review continuity` "
                        "field `targets` must be sorted and unique.",
                    )
                )
                continue
            normalized_fields.append((key, tuple(normalized_targets)))
        else:
            normalized_fields.append((key, tuple(raw_targets)))

    if findings:
        return None, findings

    if label == "protected-target post-review continuity":
        on_change = parsed_fields["on_change"]
        if on_change != "same-file-review-rerun":
            return (
                None,
                [
                    Finding(
                        path,
                        line_no,
                        "ERROR",
                        "State-transition declarations `protected-target post-review continuity` "
                        "must use literal `on_change=same-file-review-rerun`.",
                    )
                ],
            )

    return tuple(normalized_fields), findings


def parse_state_transition_declarations(
    path: Path,
    lines: list[str],
) -> StateTransitionDeclarationsParseResult:
    blocks = state_transition_declaration_blocks(lines)
    if not blocks:
        return StateTransitionDeclarationsParseResult((), None, ())

    findings: list[Finding] = []
    if len(blocks) > 1:
        findings.append(
            Finding(
                path,
                blocks[1][0],
                "ERROR",
                "State-transition declarations must appear in exactly one opt-in subsection.",
            )
        )

    parsed_declarations: list[StateTransitionDeclarations] = []
    for heading_line, is_canonical_heading, body in blocks:
        block_findings: list[Finding] = []
        if not is_canonical_heading:
            block_findings.append(
                Finding(
                    path,
                    heading_line,
                    "ERROR",
                    "State-transition declarations heading must be literal `### State-transition declarations`.",
                )
            )

        label_lines: dict[str, int] = {}
        label_values: dict[str, tuple[tuple[str, str | tuple[str, ...]], ...]] = {}
        label_order: list[str] = []
        declaration_rows_open = True
        for line_no, line in body:
            stripped = line.strip()
            if not stripped:
                continue
            match = STATE_TRANSITION_DECLARATION_LINE_RE.match(line)
            if declaration_rows_open:
                if line[:1].isspace() and match is None:
                    block_findings.append(
                        Finding(
                            path,
                            line_no,
                            "ERROR",
                            "State-transition declarations values must remain single-line list items.",
                        )
                    )
                    continue
                if not stripped.startswith("-"):
                    declaration_rows_open = False
                    continue
                if match is None:
                    block_findings.append(
                        Finding(
                            path,
                            line_no,
                            "ERROR",
                            "State-transition declarations must use `- `literal label`: unquoted value` Markdown form.",
                        )
                    )
                    continue
            elif match is None:
                continue
            elif (
                match.group("label") not in STATE_TRANSITION_DECLARATION_LABELS
                and not STATE_TRANSITION_DECLARATION_LABEL_FAMILY_RE.search(match.group("label"))
            ):
                # A receipt may continue with ordinary metadata list items after
                # narrative prose. Keep those outside this compact declaration
                # grammar, while still rejecting state-declaration-shaped aliases.
                continue

            label = match.group("label")
            if label not in STATE_TRANSITION_DECLARATION_LABELS:
                block_findings.append(
                    Finding(
                        path,
                        line_no,
                        "ERROR",
                        f"State-transition declarations has unknown label `{label}`.",
                    )
                )
                continue
            if label in label_lines:
                block_findings.append(
                    Finding(
                        path,
                        line_no,
                        "ERROR",
                        f"State-transition declarations repeats label `{label}`.",
                    )
                )
                continue

            normalized_value, value_findings = parse_state_transition_declaration_value(
                path=path,
                line_no=line_no,
                label=label,
                value=match.group("value"),
            )
            block_findings.extend(value_findings)
            label_lines[label] = line_no
            label_order.append(label)
            if normalized_value is not None:
                label_values[label] = normalized_value

        missing_labels = [label for label in STATE_TRANSITION_DECLARATION_LABELS if label not in label_lines]
        if missing_labels:
            block_findings.append(
                Finding(
                    path,
                    heading_line,
                    "ERROR",
                    "State-transition declarations is missing label(s): "
                    + ", ".join(f"`{label}`" for label in missing_labels)
                    + ".",
                )
            )
        elif tuple(label_order) != STATE_TRANSITION_DECLARATION_LABELS:
            block_findings.append(
                Finding(
                    path,
                    heading_line,
                    "ERROR",
                    "State-transition declarations labels must use the canonical order: "
                    + ", ".join(f"`{label}`" for label in STATE_TRANSITION_DECLARATION_LABELS)
                    + ".",
                )
            )

        if all(label in label_values for label in ("before-state", "after-state")):
            before_fields = dict(label_values["before-state"])
            after_fields = dict(label_values["after-state"])
            for field in ("carrier", "identity"):
                if before_fields[field] != after_fields[field]:
                    block_findings.append(
                        Finding(
                            path,
                            label_lines["after-state"],
                            "ERROR",
                            f"State-transition declarations before/after `{field}` must match exactly.",
                        )
                    )

        findings.extend(block_findings)
        if not block_findings and is_canonical_heading:
            parsed_declarations.append(
                StateTransitionDeclarations(
                    heading_line=heading_line,
                    label_lines=label_lines,
                    normalized_fields=tuple(
                        (label, label_values[label]) for label in STATE_TRANSITION_DECLARATION_LABELS
                    ),
                )
            )

    declaration = parsed_declarations[0] if len(blocks) == 1 and len(parsed_declarations) == 1 else None
    return StateTransitionDeclarationsParseResult(
        heading_lines=tuple(heading_line for heading_line, _, _ in blocks),
        declaration=declaration,
        findings=tuple(findings),
    )


def normalized_state_transition_code_draft_targets(
    code_draft_path: Path,
) -> tuple[tuple[str, ...] | None, str | None]:
    meta, error = extract_code_draft_meta(code_draft_path)
    if error or meta is None:
        return None, error or "invalid code_draft_meta"
    raw_targets = meta.get("targets")
    if not isinstance(raw_targets, list) or not raw_targets:
        return None, "code_draft_meta.targets must be a non-empty list"

    normalized_targets: list[str] = []
    for item in raw_targets:
        if not isinstance(item, dict):
            return None, f"invalid code_draft_meta.targets entry {item!r}"
        normalized_target, problem = normalize_state_transition_protected_path(item.get("path"))
        if problem:
            return None, f"code_draft_meta.targets path {item.get('path')!r} {problem}"
        assert normalized_target is not None
        normalized_targets.append(normalized_target)
    if len(set(normalized_targets)) != len(normalized_targets):
        return None, "code_draft_meta.targets must not duplicate protected paths"
    return tuple(sorted(normalized_targets)), None


def state_transition_declaration_fields(
    declaration: StateTransitionDeclarations,
) -> dict[str, dict[str, str | tuple[str, ...]]]:
    return {label: dict(fields) for label, fields in declaration.normalized_fields}


def validate_state_transition_declarations(
    path: Path,
    lines: list[str],
    *,
    status_value: str | None,
    code_draft_refs: list[tuple[int, str]],
    plan_repo_root: Path,
) -> list[Finding]:
    plan_result = parse_state_transition_declarations(path, lines)
    findings = list(plan_result.findings)
    code_draft_path = select_primary_code_draft_path(path, code_draft_refs, plan_repo_root=plan_repo_root)
    draft_result: StateTransitionDeclarationsParseResult | None = None
    code_draft_targets: tuple[str, ...] | None = None
    if code_draft_path is not None:
        draft_result = parse_state_transition_declarations(code_draft_path, read_text(code_draft_path))
        findings.extend(draft_result.findings)
        if draft_result.declaration is not None:
            code_draft_targets, target_error = normalized_state_transition_code_draft_targets(code_draft_path)
            if target_error:
                findings.append(
                    Finding(
                        code_draft_path,
                        draft_result.declaration.heading_line,
                        "ERROR",
                        f"State-transition declarations cannot compare protected targets: {target_error}.",
                    )
                )
            else:
                draft_protected_fields = state_transition_declaration_fields(draft_result.declaration)[
                    "protected-target post-review continuity"
                ]
                draft_protected_targets = draft_protected_fields["targets"]
                assert isinstance(draft_protected_targets, tuple)
                if draft_protected_targets != code_draft_targets:
                    findings.append(
                        Finding(
                            code_draft_path,
                            draft_result.declaration.label_lines["protected-target post-review continuity"],
                            "ERROR",
                            "State-transition declarations protected-target paths must exactly equal normalized "
                            "`code_draft_meta.targets`.",
                        )
                    )

    if not requires_code_draft(status_value):
        return findings

    if code_draft_path is None or draft_result is None:
        if plan_result.heading_lines:
            findings.append(
                Finding(
                    path,
                    plan_result.heading_lines[0],
                    "ERROR",
                    "State-transition declarations require a linked code draft on code-draft-required statuses.",
                )
            )
        return findings

    if bool(plan_result.heading_lines) != bool(draft_result.heading_lines):
        mismatch_path = path if plan_result.heading_lines else code_draft_path
        mismatch_line = plan_result.heading_lines[0] if plan_result.heading_lines else draft_result.heading_lines[0]
        findings.append(
            Finding(
                mismatch_path,
                mismatch_line,
                "ERROR",
                "State-transition declarations must be present in both plan and code draft on code-draft-required statuses.",
            )
        )
        return findings

    if plan_result.declaration is None or draft_result.declaration is None:
        return findings

    if plan_result.declaration.normalized_fields != draft_result.declaration.normalized_fields:
        findings.append(
            Finding(
                path,
                plan_result.declaration.heading_line,
                "ERROR",
                "State-transition declarations plan/code-draft parity mismatch after normalized comparison.",
            )
        )

    if code_draft_targets is None:
        return findings

    protected_fields = state_transition_declaration_fields(plan_result.declaration)[
        "protected-target post-review continuity"
    ]
    protected_targets = protected_fields["targets"]
    assert isinstance(protected_targets, tuple)
    if protected_targets != code_draft_targets:
        findings.append(
            Finding(
                path,
                plan_result.declaration.label_lines["protected-target post-review continuity"],
                "ERROR",
                "State-transition declarations protected-target paths must exactly equal normalized "
                "`code_draft_meta.targets`.",
            )
        )

    return findings


def extract_shared_helper_dependent_inventory_carrier(lines: list[str]) -> str:
    blocks: list[str] = []
    for line_index, line in enumerate(lines):
        if SHARED_HELPER_DEPENDENT_INVENTORY_LABEL not in line.lower():
            continue

        block: list[str] = []
        for current_index in range(line_index, len(lines)):
            current_line = lines[current_index]
            if current_index > line_index:
                stripped = current_line.strip()
                if current_line.startswith("## "):
                    break
                if SHARED_HELPER_REVIEWABILITY_FIELD_RE.match(current_line):
                    break
                if stripped and not current_line.startswith((" ", "\t", "-")):
                    lowered = stripped.lower()
                    if "inventory" not in lowered and "run-to-confirm" not in lowered:
                        break
            block.append(current_line)
        blocks.append("\n".join(block))

    return "\n".join(blocks)


def validate_shared_helper_dependent_inventory(
    path: Path,
    lines: list[str],
    *,
    status_value: str | None,
    code_draft_refs: list[tuple[int, str]],
    plan_repo_root: Path,
) -> list[Finding]:
    if not requires_shared_helper_dependent_inventory(status_value):
        return []

    code_draft_path = select_primary_code_draft_path(path, code_draft_refs, plan_repo_root=plan_repo_root)
    if code_draft_path is None:
        return []

    meta, error = extract_code_draft_meta(code_draft_path)
    if error or meta is None:
        return []

    raw_targets = meta.get("targets")
    if not isinstance(raw_targets, list):
        return []

    target_paths: list[str] = []
    for item in raw_targets:
        if not isinstance(item, dict):
            continue
        raw_path = item.get("path")
        if isinstance(raw_path, str) and raw_path.strip():
            target_paths.append(raw_path.strip())

    mapped_targets = sorted(set(target_paths).intersection(SHARED_HELPER_DEPENDENT_INVENTORY))
    if not mapped_targets:
        return []

    ref_line_no = next(
        (line_no for line_no, rel_path in code_draft_refs if (plan_repo_root / rel_path).resolve() == code_draft_path),
        1,
    )
    try:
        code_draft_lines = read_text(code_draft_path)
    except OSError:
        code_draft_lines = []
    carrier_lines = lines + [""] + code_draft_lines
    inventory_carrier_text = extract_shared_helper_dependent_inventory_carrier(carrier_lines)
    placeholder_match = SHARED_HELPER_DEPENDENT_INVENTORY_PLACEHOLDER_RE.search(inventory_carrier_text)

    findings: list[Finding] = []
    for target_path in mapped_targets:
        required_paths = SHARED_HELPER_DEPENDENT_INVENTORY[target_path]
        missing_paths = [dependent_path for dependent_path in required_paths if dependent_path not in inventory_carrier_text]
        if not missing_paths and placeholder_match is None:
            continue

        reason = (
            "placeholder/non-inventory carrier"
            if placeholder_match is not None
            else "missing/incomplete dependent inventory"
        )
        reason_code = (
            "shared_helper_dependent_inventory.placeholder"
            if placeholder_match is not None
            else "shared_helper_dependent_inventory.missing"
        )
        missing_rendered = ", ".join(f"`{dependent_path}`" for dependent_path in missing_paths)
        required_rendered = ", ".join(f"`{dependent_path}`" for dependent_path in required_paths)
        findings.append(
            Finding(
                path,
                ref_line_no,
                "ERROR",
                "Shared helper dependent inventory hard gate: "
                f"code `{reason_code}`; `{target_path}` is in `code_draft_meta.targets`, but its {reason} omits mapped "
                f"dependent path(s): {missing_rendered}. Required run-to-confirm inventory: {required_rendered}.",
            )
        )

    return findings


def validate_review_route_determinism(
    path: Path,
    lines: list[str],
    *,
    status_value: str | None,
    code_draft_refs: list[tuple[int, str]],
    plan_repo_root: Path,
) -> list[Finding]:
    findings: list[Finding] = []
    if not is_review_route_determinism_enforced(path):
        return findings
    if not requires_code_draft(status_value):
        return findings

    live_refs = extract_live_review_artifact_refs(lines)
    if len(live_refs) > 1:
        line_nos = ", ".join(str(line_no) for line_no, _ in live_refs)
        routes = ", ".join(rel_path_str for _, rel_path_str in live_refs)
        findings.append(
            Finding(
                path,
                live_refs[0][0],
                "ERROR",
                "Ambiguous live review route in `## Review artifacts`: keep exactly one literal live path "
                f"(found {routes}; lines {line_nos}). Historical/stale notes may stay outside the live carrier.",
            )
        )
        return findings

    if not live_refs:
        return findings

    live_line_no, live_rel_path = live_refs[0]
    if not live_rel_path.startswith("docs/code_reviews/"):
        return findings

    code_draft_path = select_primary_code_draft_path(path, code_draft_refs, plan_repo_root=plan_repo_root)
    if code_draft_path is None:
        return findings

    target_paths = extract_code_draft_target_paths(code_draft_path)
    if not target_paths:
        return findings

    if all(target_path.startswith("docs/") for target_path in target_paths):
        findings.append(
            Finding(
                path,
                live_line_no,
                "ERROR",
                "Docs-only bundle mismatch: live review route points to `docs/code_reviews/...`, "
                "but `code_draft_meta.targets` are docs-only. Use `docs/doc_reviews/...` for the live carrier.",
            )
        )

    return findings


def is_non_executable_umbrella_parent(lines: list[str], plan_meta_obj: dict | None) -> bool:
    return text_has_umbrella_roadmap_signal(lines, plan_meta_obj) or is_decomposition_wave(plan_meta_obj)


def validate_done_executable_review_artifact_guard(
    path: Path,
    lines: list[str],
    plan_meta_obj: dict | None,
    *,
    status_value: str | None,
    plan_type: str | None,
    plan_repo_root: Path,
) -> list[Finding]:
    # ADR 009 migration boundary: the strict live-carrier guard was introduced at
    # Current plan.v2 applies this guard. Historical
    # legacy Done-dev plans used older carrier formats ((target=`staged`), (Reviewer),
    # Primary host, Docs review, etc.) that don't match the canonical live-carrier
    # regex; they are exempt so this rule does not retroactively block 115 historical
    # plans. Post-boundary plans must carry exactly one canonical live carrier.
    if not is_done_executable_review_artifact_guard_enforced(path):
        return []
    if not is_done_status(status_value):
        return []
    if (plan_type or "").strip().lower() != "dev":
        return []
    if is_non_executable_umbrella_parent(lines, plan_meta_obj):
        return []

    live_refs = extract_live_review_artifact_refs(lines)
    if not live_refs:
        return [
            Finding(
                path,
                1,
                "ERROR",
                "Terminal `Done` executable dev plan must carry one live review artifact in `## Review artifacts` "
                "(`Code review (primary)` or `Doc review (docs-only)`) and the artifact file must exist.",
            )
        ]
    if len(live_refs) > 1:
        line_nos = ", ".join(str(line_no) for line_no, _ in live_refs)
        routes = ", ".join(rel_path_str for _, rel_path_str in live_refs)
        return [
            Finding(
                path,
                live_refs[0][0],
                "ERROR",
                "Terminal `Done` executable dev plan has ambiguous live review artifacts; keep exactly one "
                f"(found {routes}; lines {line_nos}).",
            )
        ]

    live_line_no, live_rel_path = live_refs[0]
    review_path = (plan_repo_root / live_rel_path).resolve()
    if review_path.is_file():
        return []
    return [
        Finding(
            path,
            live_line_no,
            "ERROR",
            f"Terminal `Done` executable dev plan points to missing review artifact `{live_rel_path}`. "
            "Materialize the review artifact before `Done`, or mark the plan as explicit non-executable umbrella/reference.",
        )
    ]


def extract_review_header_values(
    review_lines: list[str],
) -> tuple[tuple[int, str] | None, tuple[int, str] | None, tuple[int, str] | None]:
    def read(label: str) -> tuple[int, str] | None:
        value, line_no = review_header_metadata.singleton_header_value(review_lines, label)
        return (line_no, value) if value is not None else None

    date_line = read("date")
    target_line = read("target")
    status_line = read("status")
    return date_line, target_line, status_line


def validate_review_artifact_rerun_freshness(
    path: Path,
    lines: list[str],
    *,
    status_value: str | None,
    plan_repo_root: Path,
) -> list[Finding]:
    findings: list[Finding] = []
    if not is_review_artifact_rerun_freshness_enforced(path):
        return findings
    if not is_coder_rerun_window(status_value):
        return findings

    live_refs = extract_live_review_artifact_refs(lines)
    if len(live_refs) != 1:
        return findings

    live_line_no, live_rel_path = live_refs[0]
    review_path = (plan_repo_root / live_rel_path).resolve()
    if not review_path.exists():
        return findings

    review_lines = read_text(review_path)
    duplicate_fields = review_header_metadata.duplicate_singleton_fields(
        review_lines,
        ("date", "target", "status"),
    )
    if duplicate_fields:
        duplicate_line, duplicate_label = duplicate_fields[0]
        return [
            Finding(
                review_path,
                duplicate_line,
                "ERROR",
                f"Review artifact freshness guard: duplicate `{duplicate_label}` metadata is ambiguous; keep one preamble field.",
            )
        ]
    for label in ("date", "target", "status"):
        values = review_header_metadata.header_values(review_lines, label)
        canonical_value, canonical_line = review_header_metadata.singleton_header_value(
            review_lines,
            label,
        )
        if len(values) == 1 and canonical_value is None:
            return [
                Finding(
                    review_path,
                    canonical_line,
                    "ERROR",
                    f"Review artifact freshness guard: `{label}` metadata is noncanonical; use exact `**Label:**` spelling.",
                )
            ]
    review_date_line, target_line, review_status_line = extract_review_header_values(review_lines)
    if not review_status_line:
        return findings
    if not REVIEW_BLOCKER_STATUS_RE.search(review_status_line[1]):
        return findings
    if review_artifacts_section_has_stale_rerun_note(
        lines,
        live_rel_path=live_rel_path,
        review_date_value=review_date_line[1] if review_date_line else None,
    ):
        return findings

    target_value = target_line[1] if target_line else "<missing **Target:**>"
    findings.append(
        Finding(
            path,
            live_line_no,
            "ERROR",
            "Review artifact freshness guard: live review file "
            f"`{live_rel_path}` still carries blocker-era header (`**Target:** {target_value}`, "
            f"`**Status:** {review_status_line[1]}`) while plan status is `{status_value}`. "
            "Add an explicit stale/superseded + rerun note in `## Review artifacts` until Reviewer rewrites "
            "the same review file in place.",
        )
    )
    return findings


def validate_blocker_attribution_contract(
    path: Path,
    *,
    code_draft_refs: list[tuple[int, str]],
    plan_repo_root: Path,
) -> list[Finding]:
    findings: list[Finding] = []
    if not is_blocker_attribution_contract_enforced(path):
        return findings

    code_draft_path = select_primary_code_draft_path(path, code_draft_refs, plan_repo_root=plan_repo_root)
    if code_draft_path is None:
        return findings

    target_paths = set(extract_code_draft_target_paths(code_draft_path) or [])
    if not target_paths:
        return findings

    for rel_path_str, snippets in BLOCKER_ATTRIBUTION_REQUIRED_SNIPPETS.items():
        if rel_path_str not in target_paths:
            continue

        target_path = (plan_repo_root / rel_path_str).resolve()
        if not target_path.exists():
            continue

        text = target_path.read_text(encoding="utf-8")
        missing = [snippet for snippet in snippets if snippet not in text]
        if not missing:
            continue

        findings.append(
            Finding(
                path,
                1,
                "ERROR",
                "Blocker attribution contract mismatch: "
                f"`{rel_path_str}` is missing required literal snippet(s): {', '.join(missing)}.",
            )
        )

    return findings


def extract_fenced_code_blocks(lines: list[str]) -> list[tuple[int, str, int, int]]:
    """Return fence body metrics, with UTF-8 bytes over joined inner content only."""
    blocks: list[tuple[int, str, int, int]] = []
    in_fence = False
    start_line = 0
    lang = ""
    inner_count = 0
    inner_bytes = 0

    for idx, line in enumerate(lines, start=1):
        if not in_fence:
            match = FENCE_START_RE.match(line)
            if not match:
                continue
            in_fence = True
            start_line = idx
            lang = (match.group("lang") or "").lower()
            inner_count = 0
            continue

        # inside fence
        if FENCE_END_RE.match(line):
            blocks.append((start_line, lang, inner_count, inner_bytes))
            in_fence = False
            start_line = 0
            lang = ""
            inner_count = 0
            inner_bytes = 0
            continue

        if inner_count:
            inner_bytes += len(b"\n")
        inner_bytes += len(line.encode("utf-8"))
        inner_count += 1

    return blocks


def _is_review_range_semantic_provenance_fence(
    lines: list[str],
    *,
    start_line: int,
    lang: str,
) -> bool:
    """Whether a JSON fence belongs to the separately validated provenance receipt."""

    if lang != "json":
        return False
    heading_line = next(
        (
            line_no
            for line_no, line in enumerate(lines[: start_line - 1], start=1)
            if line.strip() == "## Review-range semantic provenance"
        ),
        None,
    )
    if heading_line is None or any(line.startswith("## ") for line in lines[heading_line : start_line - 1]):
        return False
    payload, parse_error = parse_review_range_semantic_provenance(lines)
    return (
        parse_error is None
        and payload is not None
        and _review_range_semantic_provenance_shape_error(payload) is None
    )


def validate_code_block_sizes(path: Path, lines: list[str], plan_meta_line: int | None) -> list[Finding]:
    findings: list[Finding] = []
    if not is_meta_required(path):
        return findings

    for start_line, lang, inner_count, inner_bytes in extract_fenced_code_blocks(lines):
        if plan_meta_line and start_line == plan_meta_line:
            continue
        # This finite source-engine receipt is verified by
        # ``validate_review_range_semantic_provenance`` below.  It is audit
        # data rather than an implementation sketch, and may legitimately
        # carry one identity row per declared input.
        if _is_review_range_semantic_provenance_fence(lines, start_line=start_line, lang=lang):
            continue
        if lang in DISALLOWED_PLAN_FENCE_LANGS:
            findings.append(
                Finding(
                    path,
                    start_line,
                    "ERROR",
                    f"Запрещён `{lang}` code block в plan. Перенеси implementation sketch в docs/code_drafts/ и залинкуй в Context links.",
                )
            )
            continue
        if inner_count > MAX_PLAN_CODE_BLOCK_LINES:
            findings.append(
                Finding(
                    path,
                    start_line,
                    "ERROR",
                    f"Large code block detected ({inner_count} lines). Move implementation sketch to docs/code_drafts/ and link it in plan Context links.",
                )
            )
        elif inner_bytes > MAX_PLAN_CODE_BLOCK_UTF8_BYTES:
            findings.append(
                Finding(
                    path,
                    start_line,
                    "ERROR",
                    f"Large code block detected ({inner_bytes} UTF-8 bytes). Move implementation sketch to docs/code_drafts/ and link it in plan Context links.",
                )
            )

    return findings


def validate_phase_overlay_contract(path: Path, lines: list[str], plan_meta_obj: dict | None) -> list[Finding]:
    if not is_decomposition_wave(plan_meta_obj):
        return []

    findings: list[Finding] = []
    section = slice_h2_section(lines, MECHANISM_COVERAGE_HEADING_RE)
    error_message = (
        "decomposition_wave plan must contain materialized `## Mechanism coverage` "
        "(used mechanisms / `N/A (why)` / promoted-child impact)."
    )
    if not section:
        return [Finding(path, 1, "ERROR", error_message)]

    line_no, body = section
    normalized = "\n".join(line.strip().lower() for line in body if line.strip())
    if not normalized or "unconfirmed" in normalized or "tbd" in normalized:
        return [Finding(path, line_no, "ERROR", error_message)]
    return findings


def is_decomposition_early_intake_status(status_value: str | None) -> bool:
    if not status_value:
        return False
    return " ".join(status_value.strip().lower().split()) in DECOMPOSITION_EARLY_INTAKE_STATUS_NORMS


def is_deferred_early_intake_child_graph_gap(
    state: plan_status_oracle.DecompositionChildState,
    status_value: str | None,
    plan_text: str,
) -> bool:
    if not is_decomposition_early_intake_status(status_value):
        return False
    if state.expansion_source != "none" or state.concrete_child_paths:
        return False
    execution_queue_entries = plan_status_oracle.execution_queue_plan_entries(plan_text)
    if any(not is_explicit_na_with_reason(value) for _line_no, value in execution_queue_entries):
        return False
    meta = plan_status_oracle.parse_plan_meta(plan_text)
    next_plans = meta.get("next_plans")
    if isinstance(next_plans, list) and any(str(item).strip() for item in next_plans):
        return False
    deferred_issue_kinds = {"decomposition_children_missing", "decomposition_child_placeholder"}
    return bool(state.issues) and all(issue.kind in deferred_issue_kinds for issue in state.issues)


def is_section_level_explanatory_child_map_absence(lines: list[str]) -> bool:
    section = slice_h2_section(lines, CHILD_PLAN_MAP_HEADING_RE)
    if not section:
        return False
    _heading_line, body = section
    nonempty_rows = [line.strip() for line in body if line.strip()]
    return len(nonempty_rows) == 1 and bool(
        re.fullmatch(
            r"(?:[-*]\s*)?`?N\s*/\s*A\s*\(\s*why\s*=\s*[^)]+\)`?\s*",
            nonempty_rows[0],
            re.IGNORECASE,
        )
    )


def is_explanatory_execution_queue_absence(lines: list[str], plan_text: str) -> bool:
    section = slice_h2_section(lines, EXECUTION_QUEUE_HEADING_RE)
    if not section:
        return False
    _heading_line, body = section
    plan_entries = plan_status_oracle.execution_queue_plan_entries(plan_text)
    if len(plan_entries) != 1 or not is_explicit_na_with_reason(plan_entries[0][1]):
        return False

    for line in body:
        stripped = line.strip()
        if not stripped:
            continue
        if re.fullmatch(
            r"-\s*Plan:\s*`?N\s*/\s*A\s*\(\s*why\s*=\s*[^)]+\)`?\s*",
            stripped,
            re.IGNORECASE,
        ):
            continue
        if re.match(r"-\s*Resume parent:\s*.+", stripped, re.IGNORECASE) and not CONCRETE_PLAN_PATH_RE.search(stripped):
            continue
        return False
    return True


def is_deferred_decomposition_materialization_child_graph_gap(
    state: plan_status_oracle.DecompositionChildState,
    status_value: str | None,
    plan_text: str,
    lines: list[str],
) -> bool:
    status_norm = " ".join((status_value or "").strip().lower().split())
    if status_norm not in DECOMPOSITION_MATERIALIZATION_STATUS_NORMS:
        return False
    if state.expansion_source != "none" or state.concrete_child_paths:
        return False
    meta = plan_status_oracle.parse_plan_meta(plan_text)
    if meta.get("next_plans") != []:
        return False
    return bool(
        is_section_level_explanatory_child_map_absence(lines)
        and is_explanatory_execution_queue_absence(lines, plan_text)
    )


def validate_decomposition_child_materialization(
    path: Path,
    lines: list[str],
    plan_meta_obj: dict | None,
    *,
    status_value: str | None,
    context: ContractContext | None = None,
) -> list[Finding]:
    if not is_decomposition_wave(plan_meta_obj):
        return []

    plan_text = "\n".join(lines)
    resolved_context = context or _ACTIVE_PLAN_LINT_CONTEXT.get()
    state = plan_status_oracle.decomposition_child_state(
        plan_text,
        root=repo_root_for_plan_path(path, context=resolved_context),
        context=resolved_context,
    )
    if state.state != "missing":
        return []
    if is_deferred_early_intake_child_graph_gap(state, status_value, plan_text):
        return []
    if is_deferred_decomposition_materialization_child_graph_gap(state, status_value, plan_text, lines):
        return []

    issues = state.issues or (
        plan_status_oracle.DecompositionChildIssue(
            None,
            "decomposition_children_missing",
            "",
            state.reason,
        ),
    )
    findings: list[Finding] = []
    for issue in issues:
        line_no = issue.line_no or 1
        value_suffix = f": {issue.value}" if issue.value else ""
        findings.append(
            Finding(
                path,
                line_no,
                "ERROR",
                f"decomposition_children_missing: {issue.kind}{value_suffix}: {issue.message}",
            )
        )
    return findings


def validate_decomposition_child_readiness(
    path: Path,
    lines: list[str],
    plan_meta_obj: dict | None,
    *,
    context: ContractContext | None = None,
) -> list[Finding]:
    if not is_decomposition_wave(plan_meta_obj):
        return []

    resolved_context = context or _ACTIVE_PLAN_LINT_CONTEXT.get()
    repo_root = repo_root_for_plan_path(path, context=resolved_context)
    plan_text = "\n".join(lines)
    state = plan_status_oracle.decomposition_child_state(
        plan_text,
        root=repo_root,
        context=resolved_context,
    )
    readiness_findings = plan_status_oracle.decomposition_child_readiness_findings(
        plan_text,
        root=repo_root,
        child_state=state,
    )
    findings: list[Finding] = []
    for readiness in readiness_findings:
        child_file = repo_root / readiness.child_path
        severity = "ERROR" if readiness.blocks_queue else "WARN"
        value_suffix = f": {readiness.value}" if readiness.value else ""
        findings.append(
            Finding(
                child_file,
                readiness.line_no or 1,
                severity,
                "small_model_ready_child: "
                f"{readiness.field}: {readiness.finding_kind}{value_suffix}: {readiness.message}",
            )
        )
    return findings


SMALL_RUNNER_PROOF_FIELD_ALIASES = {
    "runner_admission": "runner_admission",
    "runner_admission_at_acceptance": "runner_admission",
    "small_model_ready_state": "small_model_ready_state",
    "small_runner_ready_state": "small_model_ready_state",
    "runner_suitability": "runner_suitability",
    "task_size_complexity": "task_size_complexity",
    "task_size": "task_size_complexity",
    "runner_id": "runner_id",
    "runner": "runner_id",
    "coder_runner_id": "runner_id",
    "runner_result": "runner_result",
    "runner_outcome": "runner_result",
    "small_runner_result": "runner_result",
    "small_runner_success": "small_runner_success",
    "frontier_intervention": "frontier_intervention",
    "reviewer_lane": "reviewer_lane",
    "independent_reviewer_lane": "reviewer_lane",
    "review_lane": "reviewer_lane",
    "runner_quality": "runner_quality",
}
SMALL_RUNNER_SUCCESS_TRUE_VALUES = frozenset({"true", "yes", "success", "successful", "ok", "passed", "complete", "completed"})
SMALL_RUNNER_FALSE_VALUES = frozenset({"false", "no", "failed", "failure", "blocked", "unavailable", "inconclusive"})
SMALL_RUNNER_RED_EVIDENCE_RE = re.compile(
    r"\b("
    r"small_runner_success\s*[:=]\s*false|"
    r"inconclusive_runner_unavailable|"
    r"runner[_ -]?unavailable|"
    r"unavailable[_ -]?runner|"
    r"partial[_ -]?output|"
    r"frontier[_ -]?intervention\s*[:=]\s*(?:true|yes|required)|"
    r"frontier intervention"
    r")\b",
    re.IGNORECASE,
)


def is_small_runner_admission_enforced(path: Path) -> bool:
    return is_current_plan(path)


def small_runner_key(value: object) -> str:
    key = normalize_table_cell(str(value)).replace("/", " ")
    key = re.sub(r"[^a-z0-9]+", "_", key).strip("_")
    return SMALL_RUNNER_PROOF_FIELD_ALIASES.get(key, key)


def collect_small_runner_fields(
    lines: list[str],
    plan_meta_obj: dict | None,
) -> dict[str, list[tuple[int, str]]]:
    fields: dict[str, list[tuple[int, str]]] = {}

    def add_field(key_obj: object, value_obj: object, line_no: int) -> None:
        key = small_runner_key(key_obj)
        if key not in SMALL_RUNNER_PROOF_FIELD_ALIASES.values():
            return
        value = clean_markdown_table_cell(str(value_obj).strip())
        fields.setdefault(key, []).append((line_no, value))

    def walk_meta(obj: object) -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                add_field(key, value, 1)
                walk_meta(value)
        elif isinstance(obj, list):
            for item in obj:
                walk_meta(item)

    walk_meta(plan_meta_obj or {})

    field_re = re.compile(r"^\s*[-*]\s*`?(?P<field>[A-Za-z][A-Za-z0-9 _/-]*)`?\s*:\s*(?P<value>.*)$")
    for line_no, line in enumerate(lines, start=1):
        match = field_re.match(line)
        if match:
            add_field(match.group("field"), match.group("value"), line_no)
            continue
        cells = split_markdown_table_row(line)
        if cells and len(cells) >= 2:
            add_field(cells[0], "|".join(cells[1:]), line_no)

    return fields


def first_small_runner_field_line(fields: dict[str, list[tuple[int, str]]], *keys: str) -> int:
    for key in keys:
        values = fields.get(key)
        if values:
            return values[0][0]
    return 1


def small_runner_values(fields: dict[str, list[tuple[int, str]]], key: str) -> tuple[str, ...]:
    return tuple(value for _line_no, value in fields.get(key, ()))


def small_runner_value_token(value: str) -> str:
    return normalize_table_cell(value).replace(" ", "_")


def small_runner_claims_positive_ready(fields: dict[str, list[tuple[int, str]]]) -> bool:
    if any(small_runner_value_token(value) == "small_runner_ok" for value in small_runner_values(fields, "runner_admission")):
        return True
    if any(small_runner_value_token(value) == "ready" for value in small_runner_values(fields, "small_model_ready_state")):
        return True
    return any("small_runner_ok" in small_runner_value_token(value) for value in small_runner_values(fields, "runner_suitability"))


def small_runner_value_is_material(value: str) -> bool:
    cleaned = value.strip()
    if not cleaned:
        return False
    if is_placeholder_value(cleaned):
        return False
    if is_explicit_na_value(cleaned):
        return False
    if re.fullmatch(r"`?\s*(?:none|null|-+)\s*`?", cleaned, re.IGNORECASE):
        return False
    return True


def small_runner_has_truthy_success(fields: dict[str, list[tuple[int, str]]]) -> bool:
    for value in small_runner_values(fields, "small_runner_success"):
        token = small_runner_value_token(value)
        if token in SMALL_RUNNER_SUCCESS_TRUE_VALUES:
            return True
    return False


def small_runner_has_clean_frontier_boundary(fields: dict[str, list[tuple[int, str]]]) -> bool:
    values = small_runner_values(fields, "frontier_intervention")
    if not values:
        return False
    for value in values:
        token = small_runner_value_token(value)
        if token in {"false", "no", "none", "n_a", "not_required", "not_used"}:
            return True
    return False


def small_runner_result_is_material_success(fields: dict[str, list[tuple[int, str]]]) -> bool:
    for value in small_runner_values(fields, "runner_result"):
        token = small_runner_value_token(value)
        if token in SMALL_RUNNER_FALSE_VALUES:
            continue
        if small_runner_value_is_material(value):
            return True
    return False


def small_runner_has_material_proof(fields: dict[str, list[tuple[int, str]]]) -> bool:
    return all(
        (
            any(small_runner_value_is_material(value) for value in small_runner_values(fields, "runner_id")),
            small_runner_result_is_material_success(fields),
            small_runner_has_truthy_success(fields),
            small_runner_has_clean_frontier_boundary(fields),
            any(small_runner_value_is_material(value) for value in small_runner_values(fields, "reviewer_lane")),
        )
    )


def small_runner_has_red_evidence(lines: list[str], fields: dict[str, list[tuple[int, str]]]) -> tuple[bool, int]:
    for key in ("small_runner_success", "runner_result", "frontier_intervention"):
        for line_no, value in fields.get(key, ()):
            token = small_runner_value_token(value)
            if key == "small_runner_success" and token in SMALL_RUNNER_FALSE_VALUES:
                return True, line_no
            if key == "runner_result" and (
                token in SMALL_RUNNER_FALSE_VALUES or any(marker in token for marker in ("unavailable", "partial", "inconclusive"))
            ):
                return True, line_no
            if key == "frontier_intervention" and token in {"true", "yes", "required", "used"}:
                return True, line_no
    return False, 1


def small_runner_admission_warning(path: Path, line_no: int, message: str) -> Finding:
    return Finding(path, line_no, "WARN", SMALL_RUNNER_ADMISSION_WARNING_PREFIX + message)


def validate_small_runner_admission(
    path: Path,
    lines: list[str],
    plan_meta_obj: dict | None,
) -> list[Finding]:
    if path.name == "_template.md":
        return []
    if not is_small_runner_admission_enforced(path):
        return []

    fields = collect_small_runner_fields(lines, plan_meta_obj)
    if not small_runner_claims_positive_ready(fields):
        return []

    line_no = first_small_runner_field_line(fields, "runner_admission", "small_model_ready_state", "runner_suitability")
    findings: list[Finding] = []
    has_red_evidence, red_line = small_runner_has_red_evidence(lines, fields)
    if has_red_evidence:
        findings.append(
            small_runner_admission_warning(
                path,
                red_line,
                "`small_runner_ok` / `small_model_ready_state=ready` cannot count as positive proof while runner evidence is unavailable, partial, failed, or frontier-controlled.",
            )
        )
    if not small_runner_has_material_proof(fields):
        findings.append(
            small_runner_admission_warning(
                path,
                line_no,
                "`small_runner_ok` / `small_model_ready_state=ready` needs proof receipt fields: `runner_id`, material `runner_result`, `small_runner_success=true`, `frontier_intervention=false|none`, and independent `reviewer_lane`.",
            )
        )
    return findings


DECOMPOSITION_MECHANISM_FIELDS = (
    "mechanism",
    "usage",
    "source_refs",
    "proof_anchor",
    "state",
    "promoted_child_impact",
)
DECOMPOSITION_QUALITY_GATE_FIELDS = (
    "solvability",
    "completeness",
    "non_redundancy",
    "mutable_surface_runtime_isolation",
    "recomposition_owner",
)
DECOMPOSITION_FAILURE_MODES = (
    "over_decomposition",
    "under_decomposition",
    "silent_scope_widening",
    "orphan_child",
    "hidden_dependency_drift",
    "approval_or_risk_leakage",
    "parallel_conflict",
)
DECOMPOSITION_WEAK_QUALITY_VALUES = frozenset({"ok", "okay", "pass", "passes", "green", "done", "yes", "no"})


@dataclass(frozen=True)
class DecompositionSchemaRow:
    line_no: int
    fields: dict[str, str]
    line_by_field: dict[str, int]


def is_decomposition_mechanism_schema_enforced(path: Path) -> bool:
    return is_current_plan(path)


def decomposition_schema_key(value: str) -> str:
    key = normalize_table_cell(value).replace("/", " ")
    key = re.sub(r"[^a-z0-9]+", "_", key).strip("_")
    aliases = {
        "source_ref": "source_refs",
        "source_refs": "source_refs",
        "proof": "proof_anchor",
        "proof_ref": "proof_anchor",
        "proof_refs": "proof_anchor",
        "proof_anchor": "proof_anchor",
        "promoted_child": "promoted_child_impact",
        "child_impact": "promoted_child_impact",
        "promoted_child_impact": "promoted_child_impact",
        "non_redundancy": "non_redundancy",
        "non_redundant": "non_redundancy",
        "mutable_surface_runtime_isolation": "mutable_surface_runtime_isolation",
        "mutable_runtime_isolation": "mutable_surface_runtime_isolation",
        "runtime_isolation": "mutable_surface_runtime_isolation",
        "recomposition_integration_owner": "recomposition_owner",
        "recomposition_owner": "recomposition_owner",
        "integration_owner": "recomposition_owner",
    }
    return aliases.get(key, key)


def parse_decomposition_schema_rows(
    body: list[str],
    heading_line_no: int,
    allowed_fields: Sequence[str],
) -> list[DecompositionSchemaRow]:
    allowed = set(allowed_fields)
    rows: list[DecompositionSchemaRow] = []

    table_rows: list[tuple[int, list[str]]] = []
    for offset, line in enumerate(body, start=1):
        cells = split_markdown_table_row(line)
        if not cells:
            continue
        normalized_cells = [decomposition_schema_key(cell) for cell in cells]
        if set(normalized_cells) <= {"", "-"} or all(set(cell) <= {"-"} for cell in normalized_cells if cell):
            continue
        table_rows.append((heading_line_no + offset, cells))

    if table_rows:
        header_line_no, header_cells = table_rows[0]
        header_keys = [decomposition_schema_key(cell) for cell in header_cells]
        if any(key in allowed for key in header_keys) and len(header_keys) > 2:
            for line_no, cells in table_rows[1:]:
                fields: dict[str, str] = {}
                line_by_field: dict[str, int] = {}
                for key, cell in zip(header_keys, cells):
                    if key in allowed:
                        fields[key] = clean_markdown_table_cell(cell)
                        line_by_field[key] = line_no
                if fields:
                    rows.append(DecompositionSchemaRow(line_no, fields, line_by_field))
            if rows:
                return rows

        table_current: dict[str, str] = {}
        table_current_lines: dict[str, int] = {}
        table_current_line_no: int | None = None
        for line_no, cells in table_rows:
            if len(cells) < 2:
                continue
            key = decomposition_schema_key(cells[0])
            if key not in allowed:
                continue
            if key in table_current and table_current:
                assert table_current_line_no is not None
                rows.append(DecompositionSchemaRow(table_current_line_no, table_current, table_current_lines))
                table_current = {}
                table_current_lines = {}
                table_current_line_no = line_no
            table_current[key] = clean_markdown_table_cell("|".join(cells[1:]))
            table_current_lines[key] = line_no
            table_current_line_no = (
                line_no if table_current_line_no is None else min(table_current_line_no, line_no)
            )
        if table_current:
            rows.append(
                DecompositionSchemaRow(
                    table_current_line_no or header_line_no,
                    table_current,
                    table_current_lines,
                )
            )

    current: dict[str, str] = {}
    current_lines: dict[str, int] = {}
    current_line_no = heading_line_no
    field_re = re.compile(r"^\s*[-*]\s*`?(?P<field>[A-Za-z][A-Za-z0-9 _/-]*)`?\s*:\s*(?P<value>.*)$")
    for offset, line in enumerate(body, start=1):
        match = field_re.match(line)
        if not match:
            continue
        key = decomposition_schema_key(match.group("field"))
        if key not in allowed:
            continue
        line_no = heading_line_no + offset
        if key == "mechanism" and current:
            rows.append(DecompositionSchemaRow(current_line_no, current, current_lines))
            current = {}
            current_lines = {}
            current_line_no = line_no
        current[key] = match.group("value").strip()
        current_lines[key] = line_no
        if not current_line_no or current_line_no == heading_line_no:
            current_line_no = line_no
    if current:
        rows.append(DecompositionSchemaRow(current_line_no, current, current_lines))

    return rows


def decomposition_schema_value_problem(value: str) -> str | None:
    cleaned = value.strip()
    if not cleaned:
        return "empty"
    if is_placeholder_value(cleaned):
        return "placeholder"
    if is_explicit_na_value(cleaned) and not is_explicit_na_with_reason(cleaned):
        return "N/A without why"
    return None


def decomposition_schema_warning(path: Path, line_no: int, message: str) -> Finding:
    return Finding(path, line_no, "WARN", DECOMPOSITION_MECHANISM_SCHEMA_WARNING_PREFIX + message)


def validate_decomposition_mechanism_schema(
    path: Path,
    lines: list[str],
    plan_meta_obj: dict | None,
) -> list[Finding]:
    if path.name == "_template.md":
        return []
    if not is_decomposition_wave(plan_meta_obj):
        return []
    if not is_decomposition_mechanism_schema_enforced(path):
        return []

    findings: list[Finding] = []

    mechanism_section = slice_h2_section(lines, MECHANISM_COVERAGE_HEADING_RE)
    if mechanism_section:
        heading_line_no, body = mechanism_section
        rows = parse_decomposition_schema_rows(body, heading_line_no, DECOMPOSITION_MECHANISM_FIELDS)
        if not rows:
            findings.append(
                decomposition_schema_warning(
                    path,
                    heading_line_no,
                    "`## Mechanism coverage` has no parseable row-based mechanism fields.",
                )
            )
        for row in rows:
            for field in DECOMPOSITION_MECHANISM_FIELDS:
                value = row.fields.get(field, "")
                problem = decomposition_schema_value_problem(value)
                if not value or problem:
                    detail = problem or "missing"
                    findings.append(
                        decomposition_schema_warning(
                            path,
                            row.line_by_field.get(field, row.line_no),
                            f"`## Mechanism coverage` row is missing or weak field `{field}` ({detail}).",
                        )
                    )
            mechanism = row.fields.get("mechanism", "")
            proof_anchor = row.fields.get("proof_anchor", "")
            if mechanism and not is_explicit_na_with_reason(mechanism):
                proof_problem = decomposition_schema_value_problem(proof_anchor)
                if not proof_anchor or proof_problem:
                    findings.append(
                        decomposition_schema_warning(
                            path,
                            row.line_by_field.get("proof_anchor", row.line_no),
                            "named mechanism row must carry `proof_anchor` or explicit `N/A (why=...)`.",
                        )
                    )

    quality_section = slice_h2_section(lines, DECOMPOSITION_QUALITY_GATE_HEADING_RE)
    if not quality_section:
        findings.append(
            decomposition_schema_warning(
                path,
                1,
                "`## Decomposition quality gate` is missing for active decomposition schema enforcement.",
            )
        )
        return findings

    quality_line_no, quality_body = quality_section
    quality_rows = parse_decomposition_schema_rows(quality_body, quality_line_no, DECOMPOSITION_QUALITY_GATE_FIELDS)
    quality_fields: dict[str, str] = {}
    quality_line_by_field: dict[str, int] = {}
    for row in quality_rows:
        quality_fields.update(row.fields)
        quality_line_by_field.update(row.line_by_field)
    if not quality_fields:
        findings.append(
            decomposition_schema_warning(
                path,
                quality_line_no,
                "`## Decomposition quality gate` has no parseable quality fields.",
            )
        )
    for field in DECOMPOSITION_QUALITY_GATE_FIELDS:
        value = quality_fields.get(field, "")
        problem = decomposition_schema_value_problem(value)
        normalized_value = normalize_table_cell(value)
        if normalized_value in DECOMPOSITION_WEAK_QUALITY_VALUES:
            problem = "generic verdict without proof"
        if not value or problem:
            detail = problem or "missing"
            findings.append(
                decomposition_schema_warning(
                    path,
                    quality_line_by_field.get(field, quality_line_no),
                    f"`## Decomposition quality gate` is missing or weak field `{field}` ({detail}).",
                )
            )
        for failure_mode in DECOMPOSITION_FAILURE_MODES:
            if failure_mode in normalized_value:
                findings.append(
                    decomposition_schema_warning(
                        path,
                        quality_line_by_field.get(field, quality_line_no),
                        f"`## Decomposition quality gate` names failure mode `{failure_mode}`; record mitigation, reroute, or deferred follow-up before promotion.",
                    )
                )

    return findings


DECOMPOSITION_GRAPH_LARGE_CHILD_COUNT = 10
DECOMPOSITION_GRAPH_DEPTH_WARNING = 4
DECOMPOSITION_GRAPH_CUMULATIVE_COMPLEXITY_WARNING = 20
DECOMPOSITION_GRAPH_REASON_KEYS = frozenset(
    {
        "decomposition_sizing_rationale",
        "parent_reference_reason",
        "large_child_count_reason",
        "depth_override_reason",
        "cumulative_complexity_reason",
    }
)


@dataclass(frozen=True)
class DecompositionGraphStats:
    max_depth: int
    edge_count: int


def is_decomposition_graph_shape_enforced(path: Path) -> bool:
    return is_current_plan(path)


def is_active_decomposition_wave(plan_meta_obj: dict | None) -> bool:
    return is_decomposition_wave(plan_meta_obj) and normalized_phase_state(plan_meta_obj) == "active"


def clean_decomposition_plan_ref(value: object) -> str:
    cleaned = str(value).strip()
    if cleaned.startswith("`") and cleaned.endswith("`") and len(cleaned) >= 2:
        cleaned = cleaned[1:-1].strip()
    return cleaned.strip().strip("`").rstrip(".,;")


def is_repo_relative_decomposition_plan_path(value: object) -> bool:
    cleaned = clean_decomposition_plan_ref(value)
    return bool(re.fullmatch(r"docs/plans/[A-Za-z0-9][A-Za-z0-9_./-]*\.md", cleaned)) and ".." not in PurePosixPath(cleaned).parts


def decomposition_graph_key(value: object) -> str:
    key = normalize_table_cell(str(value)).replace("/", " ")
    key = re.sub(r"[^a-z0-9]+", "_", key).strip("_")
    aliases = {
        "decomposition_sizing_reason": "decomposition_sizing_rationale",
        "decomposition_sizing_rationale": "decomposition_sizing_rationale",
        "parent_reference_reason": "parent_reference_reason",
        "parent_reason": "parent_reference_reason",
        "reference_reason": "parent_reference_reason",
        "recomposition_reason": "parent_reference_reason",
        "single_child_reason": "parent_reference_reason",
        "one_child_reason": "parent_reference_reason",
        "large_child_count_reason": "large_child_count_reason",
        "large_count_reason": "large_child_count_reason",
        "fanout_reason": "large_child_count_reason",
        "fan_out_reason": "large_child_count_reason",
        "depth_override_reason": "depth_override_reason",
        "recursion_depth_reason": "depth_override_reason",
        "depth_reason": "depth_override_reason",
        "cumulative_complexity_reason": "cumulative_complexity_reason",
        "complexity_reason": "cumulative_complexity_reason",
    }
    return aliases.get(key, key)


def is_material_decomposition_graph_reason(value: str) -> bool:
    cleaned = value.strip()
    if not cleaned:
        return False
    if is_placeholder_value(cleaned):
        return False
    if is_explicit_na_value(cleaned):
        return False
    if re.fullmatch(r"`?\s*(?:none|no|null|-+)\s*`?", cleaned, re.IGNORECASE):
        return False
    return True


def collect_decomposition_graph_reasons(lines: list[str], plan_meta_obj: dict | None) -> dict[str, tuple[int, str]]:
    reasons: dict[str, tuple[int, str]] = {}

    def add_reason(key_obj: object, value_obj: object, line_no: int) -> None:
        key = decomposition_graph_key(key_obj)
        if key not in DECOMPOSITION_GRAPH_REASON_KEYS:
            return
        value = clean_markdown_table_cell(str(value_obj).strip())
        if is_material_decomposition_graph_reason(value):
            reasons.setdefault(key, (line_no, value))

    def walk_meta(obj: object) -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                add_reason(key, value, 1)
                walk_meta(value)
        elif isinstance(obj, list):
            for item in obj:
                walk_meta(item)

    walk_meta(plan_meta_obj or {})

    field_re = re.compile(r"^\s*[-*]\s*`?(?P<field>[A-Za-z][A-Za-z0-9 _/-]*(?:reason|rationale))`?\s*:\s*(?P<value>.*)$")
    for line_no, line in enumerate(lines, start=1):
        match = field_re.match(line)
        if match:
            add_reason(match.group("field"), match.group("value"), line_no)
            continue
        cells = split_markdown_table_row(line)
        if cells and len(cells) >= 2:
            add_reason(cells[0], "|".join(cells[1:]), line_no)

    return reasons


def has_decomposition_graph_reason(reasons: dict[str, tuple[int, str]], *keys: str) -> bool:
    return any(key in reasons for key in keys)


def concrete_decomposition_child_entries(
    plan_text: str,
    plan_meta_obj: dict | None,
) -> list[tuple[str, int | None, str]]:
    entries: list[tuple[str, int | None, str]] = []
    for line_no, value in plan_status_oracle.execution_queue_plan_entries(plan_text):
        if is_repo_relative_decomposition_plan_path(value):
            entries.append(("execution_queue", line_no, clean_decomposition_plan_ref(value)))
    for line_no, value in plan_status_oracle.child_plan_map_entries(plan_text):
        if is_repo_relative_decomposition_plan_path(value):
            entries.append(("child_plan_map", line_no, clean_decomposition_plan_ref(value)))
    next_plans = (plan_meta_obj or {}).get("next_plans")
    if isinstance(next_plans, list):
        for value in next_plans:
            if is_repo_relative_decomposition_plan_path(value):
                entries.append(("next_plans", None, clean_decomposition_plan_ref(value)))
    return entries


def unique_decomposition_child_paths(entries: Sequence[tuple[str, int | None, str]]) -> tuple[str, ...]:
    seen: set[str] = set()
    paths: list[str] = []
    for _source, _line_no, child_path in entries:
        if child_path in seen:
            continue
        seen.add(child_path)
        paths.append(child_path)
    return tuple(paths)


def decomposition_graph_warning_line(
    lines: list[str],
    entries: Sequence[tuple[str, int | None, str]],
) -> int:
    for _source, line_no, _child_path in entries:
        if line_no:
            return line_no
    for heading_re in (EXECUTION_QUEUE_HEADING_RE, CHILD_PLAN_MAP_HEADING_RE):
        section = slice_h2_section(lines, heading_re)
        if section:
            return section[0]
    return 1


def read_child_plan_meta(path: Path) -> tuple[dict | None, str | None]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None, None
    return plan_status_oracle.parse_plan_meta(text), text


def collect_decomposition_graph_stats(
    root: Path,
    child_paths: Sequence[str],
    *,
    depth: int = 1,
    seen: frozenset[str] = frozenset(),
) -> DecompositionGraphStats:
    max_depth = depth
    edge_count = len(child_paths)
    for child_path in child_paths:
        child_depth = depth + 1
        max_depth = max(max_depth, child_depth)
        if child_path in seen:
            continue
        child_meta, child_text = read_child_plan_meta(root / child_path)
        if child_meta is None or child_text is None or not is_active_decomposition_wave(child_meta):
            continue
        child_entries = concrete_decomposition_child_entries(child_text, child_meta)
        nested_paths = unique_decomposition_child_paths(child_entries)
        nested_stats = collect_decomposition_graph_stats(
            root,
            nested_paths,
            depth=child_depth,
            seen=seen | frozenset({child_path}),
        )
        max_depth = max(max_depth, nested_stats.max_depth)
        edge_count += nested_stats.edge_count
    return DecompositionGraphStats(max_depth=max_depth, edge_count=edge_count)


def decomposition_graph_shape_warning(path: Path, line_no: int, message: str) -> Finding:
    return Finding(path, line_no, "WARN", DECOMPOSITION_GRAPH_SHAPE_WARNING_PREFIX + message)


def validate_decomposition_graph_shape(
    path: Path,
    lines: list[str],
    plan_meta_obj: dict | None,
) -> list[Finding]:
    if path.name == "_template.md":
        return []
    if not is_decomposition_graph_shape_enforced(path):
        return []
    if not is_active_decomposition_wave(plan_meta_obj):
        return []

    plan_text = "\n".join(lines)
    entries = concrete_decomposition_child_entries(plan_text, plan_meta_obj)
    child_paths = unique_decomposition_child_paths(entries)
    child_count = len(child_paths)
    line_no = decomposition_graph_warning_line(lines, entries)
    reasons = collect_decomposition_graph_reasons(lines, plan_meta_obj)
    has_general_reason = has_decomposition_graph_reason(reasons, "decomposition_sizing_rationale")
    findings: list[Finding] = []

    if child_count == 0 and not has_general_reason:
        findings.append(
            decomposition_graph_shape_warning(
                path,
                line_no,
                "active decomposition umbrella has 0 materialized child plans; add child graph, `decomposition_sizing_rationale`, or keep the parent parked/reference.",
            )
        )

    if child_count == 1 and not (
        has_general_reason or has_decomposition_graph_reason(reasons, "parent_reference_reason")
    ):
        findings.append(
            decomposition_graph_shape_warning(
                path,
                line_no,
                "1-child decomposition umbrella needs `parent_reference_reason` / recomposition rationale, otherwise collapse to a direct dev plan.",
            )
        )

    if child_count >= DECOMPOSITION_GRAPH_LARGE_CHILD_COUNT and not (
        has_general_reason or has_decomposition_graph_reason(reasons, "large_child_count_reason")
    ):
        findings.append(
            decomposition_graph_shape_warning(
                path,
                line_no,
                f"large decomposition child count ({child_count}) meets threshold >= {DECOMPOSITION_GRAPH_LARGE_CHILD_COUNT}; add `large_child_count_reason` or split/stage the graph.",
            )
        )

    if child_paths:
        stats = collect_decomposition_graph_stats(repo_root_for_plan_path(path), child_paths)
        if stats.max_depth > DECOMPOSITION_GRAPH_DEPTH_WARNING and not (
            has_general_reason or has_decomposition_graph_reason(reasons, "depth_override_reason")
        ):
            findings.append(
                decomposition_graph_shape_warning(
                    path,
                    line_no,
                    f"decomposition recursion depth {stats.max_depth} exceeds soft limit > {DECOMPOSITION_GRAPH_DEPTH_WARNING}; add `depth_override_reason` or flatten/split the graph.",
                )
            )
        if stats.edge_count >= DECOMPOSITION_GRAPH_CUMULATIVE_COMPLEXITY_WARNING and not (
            has_general_reason or has_decomposition_graph_reason(reasons, "cumulative_complexity_reason")
        ):
            findings.append(
                decomposition_graph_shape_warning(
                    path,
                    line_no,
                    f"cumulative decomposition complexity ({stats.edge_count} child edges) meets threshold >= {DECOMPOSITION_GRAPH_CUMULATIVE_COMPLEXITY_WARNING}; add `cumulative_complexity_reason` or split traversal follow-up.",
                )
            )

    return findings


def collect_required_section_fields(section_body: list[str], prefixes: Sequence[str]) -> dict[str, tuple[int, str]]:
    fields: dict[str, tuple[int, str]] = {}
    for offset, raw_line in enumerate(section_body, start=1):
        stripped = raw_line.strip()
        for prefix in prefixes:
            if stripped.startswith(prefix):
                fields[prefix] = (offset, stripped[len(prefix) :].strip())
    return fields


def is_explicit_na_value(value: str) -> bool:
    return bool(re.search(r"\bn\s*/\s*a\b", value, re.IGNORECASE))


def is_explicit_na_with_reason(value: str) -> bool:
    return bool(EXPLICIT_NA_WITH_REASON_RE.search(value))


def documentation_impact_value_problem(value: str) -> str | None:
    stripped = value.strip()
    if not stripped:
        return "is empty"
    if is_explicit_na_value(stripped) and not is_explicit_na_with_reason(stripped):
        return "uses `N/A` without `why=...`"
    if is_placeholder_value(stripped):
        return "is a placeholder"
    if re.fullmatch(r"(?:none|no|nil|null|-+)", stripped.strip("`").strip(), re.IGNORECASE):
        return "is a generic placeholder"
    return None


def extract_repo_relative_target_paths(value: str) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for match in REPO_RELATIVE_TARGET_RE.finditer(value):
        raw_path = match.group("quoted") or match.group("bare") or ""
        path = raw_path.strip().strip("`").rstrip(".,;:)")
        if not path or ".." in PurePosixPath(path).parts:
            continue
        if path in seen:
            continue
        seen.add(path)
        result.append(path)
    return result


def is_documentation_target_path(path: str) -> bool:
    return path.startswith("docs/") and not path.startswith(
        ("docs/code_drafts/", "docs/code_reviews/", "docs/doc_reviews/")
    )


def validate_documentation_impact_section(
    path: Path,
    lines: list[str],
    *,
    code_draft_refs: list[tuple[int, str]],
    plan_repo_root: Path,
    status_value: str | None,
) -> list[Finding]:
    if not is_documentation_impact_enforced(path):
        return []

    section = slice_h2_section(lines, DOCUMENTATION_IMPACT_HEADING_RE)
    if not section:
        return [
            Finding(
                path,
                1,
                "WARN",
                "Documentation impact / provenance warning: missing `## Documentation impact / provenance`. "
                "Add the carrier fields or use explicit `N/A (why=...)` for fields that do not apply.",
            )
        ]

    section_line_no, body = section
    findings: list[Finding] = []
    fields = collect_required_section_fields(body, DOCUMENTATION_IMPACT_REQUIRED_LINES)
    missing = [prefix for prefix in DOCUMENTATION_IMPACT_REQUIRED_LINES if prefix not in fields]
    for prefix in missing:
        findings.append(
            Finding(
                path,
                section_line_no,
                "WARN",
                "Documentation impact / provenance warning: "
                f"missing `{prefix}`. Fill it or use explicit `N/A (why=...)`.",
            )
        )

    for prefix in DOCUMENTATION_IMPACT_REQUIRED_LINES:
        if prefix not in fields:
            continue
        field_line_offset, value = fields[prefix]
        problem = documentation_impact_value_problem(value)
        if not problem:
            continue
        findings.append(
            Finding(
                path,
                section_line_no + field_line_offset,
                "WARN",
                "Documentation impact / provenance warning: "
                f"`{prefix}` {problem}. Fill it or use explicit `N/A (why=...)`.",
            )
        )

    if DOCUMENTATION_IMPACT_SYNC_TARGET_LINE not in fields:
        return findings

    sync_line_offset, sync_value = fields[DOCUMENTATION_IMPACT_SYNC_TARGET_LINE]
    sync_line_no = section_line_no + sync_line_offset
    code_draft_path = select_primary_code_draft_path(path, code_draft_refs, plan_repo_root=plan_repo_root)
    if code_draft_path is None:
        return findings

    code_draft_targets = extract_code_draft_target_paths(code_draft_path)
    if not code_draft_targets:
        return findings

    code_draft_target_set = set(code_draft_targets)
    sync_targets = extract_repo_relative_target_paths(sync_value)
    sync_target_set = set(sync_targets)
    sync_is_explicit_na = is_explicit_na_with_reason(sync_value)
    target_drift_severity = documentation_impact_target_drift_severity(path, status_value)
    target_drift_prefix = documentation_impact_target_drift_prefix(target_drift_severity)

    for sync_target in sorted(sync_target_set):
        if sync_target not in code_draft_target_set:
            findings.append(
                Finding(
                    path,
                    sync_line_no,
                    target_drift_severity,
                    target_drift_prefix +
                    f"`Synchronous doc/registry targets` lists `{sync_target}`, but linked "
                    "`code_draft_meta.targets` does not include it. Restamp the code draft target inventory "
                    "or move optional/non-live paths to `Possible sync targets`.",
                )
            )

    code_draft_doc_targets = sorted(
        target for target in code_draft_target_set if is_documentation_target_path(target)
    )
    if sync_is_explicit_na and code_draft_doc_targets:
        rendered = ", ".join(f"`{target}`" for target in code_draft_doc_targets)
        findings.append(
            Finding(
                path,
                sync_line_no,
                target_drift_severity,
                target_drift_prefix +
                f"`Synchronous doc/registry targets` is explicit `N/A`, but code draft doc target(s) exist: {rendered}.",
            )
        )
        return findings

    for doc_target in code_draft_doc_targets:
        if doc_target in sync_target_set:
            continue
        findings.append(
            Finding(
                path,
                sync_line_no,
                target_drift_severity,
                target_drift_prefix +
                f"`code_draft_meta.targets` includes doc target `{doc_target}`, but "
                "`Synchronous doc/registry targets` does not name it. Update the carrier or restamp the code draft.",
            )
        )

    return findings


def validate_scope_route_classification(
    path: Path,
    lines: list[str],
    *,
    plan_type: str | None,
    status_value: str | None,
) -> list[Finding]:
    if not is_scope_route_classification_enforced(path):
        return []
    if not is_active_dev_plan(plan_type, status_value):
        return []

    in_fence = False
    for line_no, line in enumerate(lines, start=1):
        if in_fence:
            if FENCE_END_RE.match(line):
                in_fence = False
            continue
        if FENCE_START_RE.match(line):
            in_fence = True
            continue
        if not is_scope_route_lintable_line(line):
            continue
        if SCOPE_ROUTE_AMBIGUOUS_RE.search(line):
            if has_local_scope_route_classification(lines, line_no):
                continue
            return [
                Finding(
                    path,
                    line_no,
                    "ERROR",
                    "Ambiguous scope/follow-up routing in active dev plan: wording about scope split, broad cleanup, "
                    "out-of-bundle work, or follow-up-later must name one explicit route class: "
                    "`same-contract reroute`, `real scope expansion`, or `de-scoped follow-up`.",
                )
            ]

    return []


def validate_architect_understanding_block(
    path: Path,
    lines: list[str],
    *,
    status_value: str | None,
) -> list[Finding]:
    if not is_architect_understanding_block_enforced(path):
        return []

    severity = architect_understanding_block_severity(status_value)
    error_message = (
        "Architect understanding block missing/placeholder: add a separate `## Как я понял задачу` "
        "section with a short human-readable summary before the plan leaves Architect intake."
    )

    in_fence = False
    for idx, line in enumerate(lines):
        if in_fence:
            if FENCE_END_RE.match(line):
                in_fence = False
            continue
        if FENCE_START_RE.match(line):
            in_fence = True
            continue

        match = ARCHITECT_UNDERSTANDING_HEADING_RE.match(line)
        if not match:
            continue

        heading_line_no = idx + 1
        body: list[str] = []
        in_body_fence = False
        for body_line in lines[idx + 1 :]:
            if in_body_fence:
                if FENCE_END_RE.match(body_line):
                    in_body_fence = False
                continue
            if FENCE_START_RE.match(body_line):
                in_body_fence = True
                continue
            if ANY_MD_HEADING_RE.match(body_line):
                break
            stripped = body_line.strip()
            if stripped:
                body.append(stripped)

        body_text = architect_understanding_body_text(body)
        if (
            not body_text
            or is_placeholder_value(body_text)
            or is_explicit_na_value(body_text)
            or re.fullmatch(r"(?i)no questions\.?", body_text)
            or len(body_text) < 20
        ):
            return [Finding(path, heading_line_no, severity, error_message)]
        return []

    return [Finding(path, 1, severity, error_message)]


def is_architect_understanding_instruction_line(stripped: str) -> bool:
    if not stripped:
        return True
    if stripped.startswith(">"):
        return True
    if re.fullmatch(r"\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?", stripped):
        return True
    cleaned = re.sub(r"^[>\-\*\d.)\s\[\]xX]+", "", stripped).strip()
    if not (cleaned.startswith("(") and cleaned.endswith(")")):
        return False
    normalized = re.sub(r"\s+", " ", cleaned[1:-1].replace("`", "").lower()).strip()
    return (
        "required for architect intake" in normalized
        or "этот блок не заменяет" in normalized
        or (
            "коротко" in normalized
            and "по-человечески" in normalized
            and "по-русски" in normalized
            and "что меняем" in normalized
        )
    )


def architect_understanding_body_text(body: list[str]) -> str:
    content: list[str] = []
    for item in body:
        stripped = item.strip()
        if is_architect_understanding_instruction_line(stripped):
            continue
        cleaned = re.sub(r"^[>\-\*\d.)\s\[\]xX]+", "", stripped).strip()
        if cleaned:
            content.append(cleaned)
    return " ".join(content).strip()


def is_plan_statement_instruction_line(stripped: str) -> bool:
    if not stripped:
        return True
    if stripped.startswith(">"):
        return True
    if stripped.startswith("(") and stripped.endswith(")"):
        return True
    if re.fullmatch(r"\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?", stripped):
        return True
    return False


def plan_statement_body_text(lines: list[str], start_idx: int) -> str:
    body: list[str] = []
    in_fence = False
    for line in lines[start_idx:]:
        if in_fence:
            if FENCE_END_RE.match(line):
                in_fence = False
            continue
        if FENCE_START_RE.match(line):
            in_fence = True
            continue
        if H2_HEADING_RE.match(line):
            break

        stripped = line.strip()
        if is_plan_statement_instruction_line(stripped):
            continue
        cleaned = re.sub(r"^[>\-\*\d.)\s\[\]xX]+", "", stripped).strip()
        if cleaned:
            body.append(cleaned)
    return " ".join(body).strip()


def validate_russian_plan_statement_sections(path: Path, lines: list[str]) -> list[Finding]:
    if not is_russian_plan_statement_warning_enforced(path):
        return []

    findings: list[Finding] = []
    in_fence = False
    for idx, line in enumerate(lines):
        if in_fence:
            if FENCE_END_RE.match(line):
                in_fence = False
            continue
        if FENCE_START_RE.match(line):
            in_fence = True
            continue

        match = RUSSIAN_PLAN_STATEMENT_SECTION_RE.match(line)
        if not match:
            continue

        body_text = plan_statement_body_text(lines, idx + 1)
        if not body_text or is_placeholder_value(body_text) or is_explicit_na_value(body_text):
            continue
        if CYRILLIC_RE.search(body_text):
            continue
        findings.append(
            Finding(
                path,
                idx + 1,
                "WARN",
                "Russian-first plan statement warning: human-facing постановка section "
                f"`## {match.group('title')}` has no Cyrillic narrative. Write the plan statement in Russian; "
                "keep English only for identifiers, paths, commands, enum/API/field names, and literal source terms.",
            )
        )
    return findings


def is_scope_route_lintable_line(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped and not stripped.startswith("#") and not stripped.startswith(">"))


def has_local_scope_route_classification(lines: list[str], line_no: int) -> bool:
    start = max(1, line_no - SCOPE_ROUTE_CLASSIFICATION_WINDOW)
    end = min(len(lines), line_no + SCOPE_ROUTE_CLASSIFICATION_WINDOW)
    for candidate_line_no in range(start, end + 1):
        candidate = lines[candidate_line_no - 1].strip()
        if candidate.startswith("#") or candidate.startswith(">"):
            continue
        if any(token in candidate for token in SCOPE_ROUTE_CLASSIFICATION_TOKENS):
            return True
    return False


def validate_close_out_routing_section(path: Path, lines: list[str]) -> list[Finding]:
    if not is_navigation_contract_enforced(path):
        return []

    error_message = (
        "navigation contract: missing/placeholder `## Close-out routing` "
        "(`Roadmap/queue sync`, `Follow-up sync`, `Next bounded slice`, `Terminal outcome`)."
    )
    section = slice_h2_section(lines, CLOSE_OUT_ROUTING_HEADING_RE)
    if not section:
        return [Finding(path, 1, "ERROR", error_message)]

    line_no, body = section
    fields = collect_required_section_fields(body, CLOSE_OUT_ROUTING_REQUIRED_LINES)
    missing = [prefix for prefix in CLOSE_OUT_ROUTING_REQUIRED_LINES if prefix not in fields]
    if missing:
        return [Finding(path, line_no, "ERROR", error_message)]

    findings: list[Finding] = []
    for prefix in CLOSE_OUT_ROUTING_REQUIRED_LINES:
        field_line_offset, value = fields[prefix]
        field_line_no = line_no + field_line_offset
        if not value or is_placeholder_value(value):
            findings.append(Finding(path, field_line_no, "ERROR", error_message))
            continue
        if prefix == "- Terminal outcome:":
            lowered = value.strip().lower()
            if not (lowered.startswith("yes") or lowered.startswith("no") or is_explicit_na_value(value)):
                findings.append(
                    Finding(
                        path,
                        field_line_no,
                        "ERROR",
                        "`Terminal outcome` must start with `yes`, `no`, or explicit `N/A (why)`.",
                    )
                )

    return findings


def validate_rollout_packet_handoff_section(path: Path, lines: list[str]) -> list[Finding]:
    if not is_navigation_contract_enforced(path):
        return []

    error_message = (
        "navigation contract: missing/placeholder `## Rollout packet handoff` "
        "(`Role`, `Packet path`, `Target repo`, `Suggested target plan slug`, `Queue after import`)."
    )
    section = slice_h2_section(lines, ROLLOUT_PACKET_HANDOFF_HEADING_RE)
    if not section:
        return [Finding(path, 1, "ERROR", error_message)]

    line_no, body = section
    fields = collect_required_section_fields(body, ROLLOUT_PACKET_HANDOFF_REQUIRED_LINES)
    missing = [prefix for prefix in ROLLOUT_PACKET_HANDOFF_REQUIRED_LINES if prefix not in fields]
    if missing:
        return [Finding(path, line_no, "ERROR", error_message)]

    findings: list[Finding] = []
    for prefix in ROLLOUT_PACKET_HANDOFF_REQUIRED_LINES:
        field_line_offset, value = fields[prefix]
        field_line_no = line_no + field_line_offset
        if not value or is_placeholder_value(value):
            findings.append(Finding(path, field_line_no, "ERROR", error_message))

    role_value = fields["- Role:"][1]
    packet_path_value = fields["- Packet path:"][1]
    target_repo_value = fields["- Target repo:"][1]
    suggested_slug_value = fields["- Suggested target plan slug:"][1]
    queue_after_import_value = fields["- Queue after import:"][1]
    target_repo_line_no = line_no + fields["- Target repo:"][0]
    suggested_slug_line_no = line_no + fields["- Suggested target plan slug:"][0]

    role_clean = role_value.strip().strip("`").lower()
    if is_explicit_na_value(role_value):
        for prefix, value in (
            ("Packet path", packet_path_value),
            ("Target repo", target_repo_value),
            ("Suggested target plan slug", suggested_slug_value),
            ("Queue after import", queue_after_import_value),
        ):
            if is_explicit_na_value(value):
                continue
            findings.append(
                Finding(
                    path,
                    line_no,
                    "ERROR",
                    f"When `Role` is `N/A`, `{prefix}` must also be explicit `N/A (why)`.",
                )
            )
        return findings

    if role_clean not in {"source-packet", "target-import"}:
        findings.append(
            Finding(
                path,
                line_no,
                "ERROR",
                "`Role` in `## Rollout packet handoff` must be `source-packet`, `target-import`, or explicit `N/A (why)`.",
            )
        )

    packet_clean = packet_path_value.strip().strip("`")
    if not is_explicit_na_value(packet_path_value) and not ROLL_OUT_PACKET_PATH_RE.fullmatch(packet_clean):
        findings.append(
            Finding(
                path,
                line_no,
                "ERROR",
                "`Packet path` must be `docs/rollout_packets/...` or explicit `N/A (why)`.",
            )
        )

    target_repo_clean = target_repo_value.strip().strip("`")
    if not is_explicit_na_value(target_repo_value) and not ROLL_OUT_PACKET_TARGET_REPO_SET_RE.fullmatch(target_repo_clean):
        findings.append(
            Finding(
                path,
                target_repo_line_no,
                "ERROR",
                "`Target repo` must be a bounded repo id set like `consumer-fixture`, `partner-fixture`, "
                "`consumer-fixture + partner-fixture`, or explicit `N/A (why)`.",
            )
        )

    suggested_slug_clean = suggested_slug_value.strip().strip("`")
    if not is_explicit_na_value(suggested_slug_value) and not ROLL_OUT_PACKET_PLAN_SLUG_RE.fullmatch(
        suggested_slug_clean
    ):
        findings.append(
            Finding(
                path,
                suggested_slug_line_no,
                "ERROR",
                "`Suggested target plan slug` must be a bounded slug like `topic_slug` or explicit `N/A (why)`.",
            )
        )

    queue_clean = queue_after_import_value.strip().strip("`").lower()
    if not (
        queue_clean.startswith("yes")
        or queue_clean.startswith("no")
        or is_explicit_na_value(queue_after_import_value)
    ):
        findings.append(
            Finding(
                path,
                line_no,
                "ERROR",
                "`Queue after import` must start with `yes`, `no`, or explicit `N/A (why)`.",
            )
        )

    return findings


def validate_verification_handoff_section(path: Path, lines: list[str]) -> list[Finding]:
    if not is_navigation_contract_enforced(path):
        return []

    error_message = (
        "navigation contract: missing/placeholder `## Verification rerun / exec handoff` "
        "(`Mode`, `Context source`, `Prompt`, `Command`, `Expected artifact`)."
    )
    section = slice_h2_section(lines, VERIFICATION_HANDOFF_HEADING_RE)
    if not section:
        return [Finding(path, 1, "ERROR", error_message)]

    line_no, body = section
    fields = collect_required_section_fields(body, VERIFICATION_HANDOFF_REQUIRED_LINES)
    missing = [prefix for prefix in VERIFICATION_HANDOFF_REQUIRED_LINES if prefix not in fields]
    if missing:
        return [Finding(path, line_no, "ERROR", error_message)]

    findings: list[Finding] = []
    for prefix in VERIFICATION_HANDOFF_REQUIRED_LINES:
        field_line_offset, value = fields[prefix]
        field_line_no = line_no + field_line_offset
        if not value or is_placeholder_value(value):
            findings.append(Finding(path, field_line_no, "ERROR", error_message))
            continue
        if prefix == "- Mode:":
            lowered = value.strip().lower()
            if lowered not in VERIFICATION_HANDOFF_ALLOWED_MODES and not is_explicit_na_value(value):
                findings.append(
                    Finding(
                        path,
                        field_line_no,
                        "ERROR",
                        "`Mode` must be one of `reuse-thread`, `fresh-exec`, `manager-custom-pipeline`, or explicit `N/A (why)`.",
                    )
                )

    return findings


def classify_plan_schema_version(path: Path, lines: list[str]) -> tuple[str, list[Finding]]:
    findings: list[Finding] = []
    schema_lines = extract_schema_version_lines(lines)
    if len(schema_lines) > 1:
        line_nos = ", ".join(str(line_no) for line_no, _ in schema_lines)
        findings.append(
            Finding(
                path,
                schema_lines[0][0],
                "ERROR",
                f"Multiple **Schema version:** header lines found ({line_nos}). Keep one canonical top-level carrier.",
            )
        )
        return "unsupported", findings

    if not schema_lines:
        if path.name == "_template.md":
            findings.append(
                Finding(
                    path,
                    1,
                    "ERROR",
                    "Missing `**Schema version:** plan.v2` on the canonical plan template. "
                    "Versionless non-template plans are tolerated only as legacy compatibility carriers.",
                )
            )
            return "unsupported", findings
        return "legacy_v1", findings

    line_no, raw_value = schema_lines[0]
    normalized = normalize_schema_version(raw_value)
    if normalized == CURRENT_PLAN_SCHEMA_VERSION:
        return "v2", findings
    if normalized == LEGACY_PLAN_SCHEMA_VERSION:
        return "legacy_v1", findings
    if normalized != CURRENT_PLAN_SCHEMA_VERSION:
        findings.append(
            Finding(
                path,
                line_no,
                "ERROR",
                f"Unsupported plan schema version {raw_value!r}; current={CURRENT_PLAN_SCHEMA_VERSION!r}, "
                f"legacy={LEGACY_PLAN_SCHEMA_VERSION!r} and versionless historical plans remain readable.",
            )
        )
        return "unsupported", findings

    raise AssertionError("unreachable schema classifier")


# Semantic review observation V1 -------------------------------------------------
#
# This implementation intentionally lives in plan_lint rather than in the CLI
# projection.  PLAN_PATH is the only truth host; review_artifact_lint and
# semantic_review_observation.py are consumers of these parse/validation APIs.

SEMANTIC_OBSERVATION_MARKER_HEADING = "### Semantic review observation"
SEMANTIC_OBSERVATION_MARKER_ROWS = (
    "- `schema=semantic_review_observation.v1`",
    "- `mode=required`",
    "- `writer=reviewer_code_contracts`",
)
SEMANTIC_CHECKPOINT_MARKER_HEADING = "### Semantic cycle checkpoint"
SEMANTIC_CHECKPOINT_MARKER_ROWS = (
    "- `schema=semantic_cycle_checkpoint.v1`",
    "- `mode=required`",
    "- `writer=architect`",
)
SEMANTIC_OBSERVATION_PROPOSAL_SCHEMA = "semantic_review_observation_proposal.v1"
SEMANTIC_OBSERVATION_SCHEMA = "semantic_review_observation.v1"
SEMANTIC_OBSERVATION_REPORT_SCHEMA = "semantic_review_observation_report.v1"
SEMANTIC_CHECKPOINT_RESOLUTION_SCHEMA = "semantic_cycle_checkpoint_resolution.v1"
SEMANTIC_CHECKPOINT_RESOLUTION_V2_SCHEMA = "semantic_cycle_checkpoint_resolution.v2"
SEMANTIC_CHECKPOINT_REPORT_SCHEMA = "semantic_cycle_checkpoint_report.v1"
SEMANTIC_CONTRACT_FINGERPRINT_SCHEMA = "contract_fingerprint.v1"
SEMANTIC_REVIEW_GENERATION_SCHEMA = "semantic_review_generation.v1"
SEMANTIC_BLOCKER_FAMILY_SCHEMA = "blocker_family.v1"
SEMANTIC_REPORT_FIELDS = (
    "schema_version",
    "state",
    "reason_code",
    "candidate_machine_fields",
    "materialization",
    "validated_chain",
    "errors",
)
SEMANTIC_CANDIDATE_FIELDS = (
    "risk_run_id",
    "target_snapshot",
    "review_artifact",
    "review_generation_id",
    "observation_id",
    "contract_fingerprint",
    "predecessor_observation_id",
    "proposal_sha256",
    "blocker_machine_fields",
    "resolved_blocker_family_ids",
)
SEMANTIC_PROPOSAL_FIELDS = (
    "schema_version",
    "progress_verdict",
    "progress_evidence_refs",
    "blockers",
    "resolved_predecessor_blocker_refs",
)
SEMANTIC_OBSERVATION_FIELDS = (
    "schema_version",
    "observation_id",
    "review_generation_id",
    "risk_run_id",
    "target_snapshot",
    "review_artifact",
    "contract_fingerprint",
    "predecessor_observation_id",
    "proposal_sha256",
    "progress_verdict",
    "progress_evidence_refs",
    "blockers",
    "resolved_blocker_family_ids",
)
SEMANTIC_CHECKPOINT_RESOLUTION_FIELDS = (
    "schema_version",
    "trigger_observation_id",
    "trigger_kind",
    "contract_fingerprint",
    "required_family_resolutions",
    "decision_evidence_refs",
    "allowed_next_status",
)
SEMANTIC_CHECKPOINT_OPTIONAL_RESOLUTION_FIELDS = frozenset({"successor_plan_ref", "owner_question_ref"})
SEMANTIC_CHECKPOINT_FAMILY_RESOLUTION_FIELDS = ("blocker_family_id", "decision")
SEMANTIC_CHECKPOINT_V2_RESOLUTION_FIELDS = (
    "schema_version",
    "resolution_state",
    "authority_decision_id",
    "authority_carrier_sha256",
    "grammar_contour_id",
    "trigger_observation_id",
    "trigger_kind",
    "contract_fingerprint",
    "required_family_resolutions",
    "decision_evidence_refs",
    "allowed_next_status",
)
SEMANTIC_CHECKPOINT_V2_OPTIONAL_RESOLUTION_FIELDS = frozenset({"successor_plan_ref"})
SEMANTIC_CHECKPOINT_V2_FAMILY_RESOLUTION_FIELDS = (
    "blocker_family_id",
    "blocker_ref",
    "grammar_axis_ids",
    "decision",
)
SEMANTIC_CHECKPOINT_V2_SUCCESSOR_INTAKE_SCHEMA = "semantic_cycle_successor_intake.v1"
SEMANTIC_CHECKPOINT_V2_SUCCESSOR_INTAKE_FIELDS = (
    "schema_version",
    "source_plan",
    "source_trigger_observation_id",
    "source_grammar_contour_id",
    "inherited_family_refs",
)
SEMANTIC_CHECKPOINT_V2_SUCCESSOR_FAMILY_FIELDS = (
    "blocker_family_id",
    "blocker_ref",
    "grammar_axis_ids",
)
SEMANTIC_CHECKPOINT_V2_DECISIONS = frozenset({"same_contract_once", "de_scope", "successor"})
SEMANTIC_CHECKPOINT_V2_DECISION_NEXT_STATUS = {
    "same_contract_once": "Coder intake",
    "de_scope": "Reviewer intake",
    "successor": "Superseded",
}
SEMANTIC_CHECKPOINT_V2_EVIDENCE_REF_RE = re.compile(
    r"docs/(?:code_reviews|plans|code_drafts)/[A-Za-z0-9_./-]+\.md#[A-Za-z][A-Za-z0-9 _./-]*"
)
SEMANTIC_CHECKPOINT_TRIGGER_KINDS = frozenset(
    {"family_survival", "scope_churn", "independent_boundary"}
)
SEMANTIC_CHECKPOINT_DECISIONS = frozenset({"same_contract_once", "de_scope", "successor", "stop"})
SEMANTIC_CHECKPOINT_DECISION_NEXT_STATUS = {
    "same_contract_once": "Coder intake",
    "de_scope": "Reviewer intake",
    "successor": "Superseded",
    "stop": "Architect response",
}
SEMANTIC_CHECKPOINT_ARCHITECT_STATUS_NORMS = frozenset(
    {"ready for architect response", "architect response"}
)
SEMANTIC_CHECKPOINT_CONTINUATION_STATUS_NORMS = {
    "Coder intake": frozenset(
        {
            "coder intake",
            "in progress",
            "ready for review",
            "reviewer intake",
            "reviewer code review",
            "reviewer visual review",
            "ready for arch review",
        }
    ),
    "Reviewer intake": frozenset(
        {"reviewer intake", "reviewer code review", "reviewer visual review", "ready for arch review"}
    ),
    "Superseded": frozenset({"superseded"}),
    "Architect response": frozenset({"architect response"}),
}
SEMANTIC_BLOCKER_PROPOSAL_FIELDS = (
    "blocker_ref",
    "lineage_relation",
    "predecessor_blocker_ref",
)
SEMANTIC_BLOCKER_OBSERVATION_FIELDS = SEMANTIC_BLOCKER_PROPOSAL_FIELDS + ("blocker_family_id",)
SEMANTIC_PROGRESS_VERDICTS = frozenset(
    {
        "first_observation",
        "same_contract_progress",
        "same_contract_stalled",
        "scope_churn",
        "independent_boundary",
    }
)
SEMANTIC_LINEAGE_RELATIONS = frozenset({"first_observation", "same_family", "independent_boundary"})
SEMANTIC_SUCCESSFUL_RISK_LANE_STATUSES = frozenset({"complete", "no_findings"})
SEMANTIC_FINGERPRINT_SECTION_HEADINGS = (
    "Decisions (final)",
    "Scope",
    "Out of scope",
    "Changes (by area)",
    "Acceptance criteria / DoD",
    "Tests",
    "Commands",
)
SEMANTIC_STAGE_REASON_CODES = {
    "activation": "activation_invalid",
    "risk": "risk_lane_selection_blocked",
    "live_review": "live_review_artifact_invalid",
    "code_draft": "code_draft_invalid",
    "fingerprint": "fingerprint_unavailable",
    "proposal": "role_proposal_invalid",
    "observation_schema": "observation_schema_invalid",
    "chain": "observation_chain_invalid",
    "current_head": "current_head_mismatch",
    "role": "role_field_invalid",
}
SEMANTIC_STAGE_ORDER = tuple(SEMANTIC_STAGE_REASON_CODES)
SEMANTIC_STAGE_RANK = {stage: index for index, stage in enumerate(SEMANTIC_STAGE_ORDER)}
SEMANTIC_EVIDENCE_HEADING_RE = re.compile(
    r"^ {0,3}##[ \t]+Evidence(?:[ \t]*\([^)]*\))?[ \t]*$",
    re.IGNORECASE,
)
SEMANTIC_RECEIPT_HEADING_RE = re.compile(
    r"^ {0,3}##[ \t]+Reviewability preflight receipt[ \t]*$",
    re.IGNORECASE,
)
SEMANTIC_H3_HEADING_RE = re.compile(r"^ {0,3}###[ \t]+(?P<title>.*?)[ \t]*$")
SEMANTIC_BLOCKER_REF_SUFFIX_RE = re.compile(r"#B(?P<number>[1-9][0-9]*)$")
SEMANTIC_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SEMANTIC_AGGREGATE_HEADING_RE = re.compile(
    r"^ {0,3}##[ \t]+Lane synthesis / aggregate verdict[ \t]*$", re.IGNORECASE
)
SEMANTIC_CONTRACTS_LANE_HEADING_RE = re.compile(
    r"^ {0,3}##[ \t]+reviewer_code_contracts(?:\b|[ \t].*)$", re.IGNORECASE
)
SEMANTIC_AGGREGATE_STATUS_RE = re.compile(r"^\s*-\s*Aggregate status\s*:\s*(?P<value>.+?)\s*$", re.IGNORECASE)
SEMANTIC_BLOCKER_ID_RE = re.compile(r"^\s*-\s*Blocker ID\s*:\s*B(?P<number>[1-9][0-9]*)\s*$", re.IGNORECASE)
SEMANTIC_S1_BLOCKER_HEADING_RE = re.compile(r"^ {0,3}##[ \t]+S1 Blocker[ \t]*$", re.IGNORECASE)
SEMANTIC_BLOCKER_RECORD_HEADING_RE = re.compile(
    r"^ {0,3}###[ \t]+B(?P<number>[1-9][0-9]*)\)(?:[ \t]+.*)?$", re.IGNORECASE
)
SEMANTIC_BLOCKER_RECORD_PREFIX_RE = re.compile(r"^ {0,3}###[ \t]+B[0-9]+", re.IGNORECASE)
SEMANTIC_BLOCKER_ID_FIELD_RE = re.compile(r"^\s*-\s*Blocker ID\s*:\s*(?P<value>.+?)\s*$", re.IGNORECASE)
SEMANTIC_BLOCKER_STATE_RE = re.compile(r"^\s*-\s*Current state\s*:\s*(?P<value>.+?)\s*$", re.IGNORECASE)
SEMANTIC_CURRENT_BLOCKER_STATES = frozenset({"open", "historical-fixed", "superseded"})


def semantic_canonical_json_bytes(value: object) -> bytes:
    """Serialize a V1 hash payload under the versioned canonical JSON rules."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _semantic_sha256(value: object) -> str:
    return hashlib.sha256(semantic_canonical_json_bytes(value)).hexdigest()


def _semantic_empty_candidate_machine_fields() -> dict[str, object | None]:
    return {field: None for field in SEMANTIC_CANDIDATE_FIELDS}


def _semantic_path_display(path: Path, repo_root: Path) -> str:
    return repo_relative_display(path, repo_root).replace("\\", "/")


def _semantic_diagnostic(
    diagnostics: list[SemanticObservationDiagnostic],
    *,
    stage: str,
    code: str,
    path: str | None,
    line: int | None,
    message: str,
) -> None:
    diagnostics.append(
        SemanticObservationDiagnostic(
            stage=stage,
            code=code,
            path=path,
            line=line,
            message=message,
        )
    )


def _semantic_sorted_diagnostics(
    diagnostics: Iterable[SemanticObservationDiagnostic],
) -> list[SemanticObservationDiagnostic]:
    unique: dict[tuple[str, str, str | None, int | None, str], SemanticObservationDiagnostic] = {}
    for diagnostic in diagnostics:
        unique[(diagnostic.stage, diagnostic.code, diagnostic.path, diagnostic.line, diagnostic.message)] = diagnostic
    return sorted(
        unique.values(),
        key=lambda item: (
            SEMANTIC_STAGE_RANK.get(item.stage, len(SEMANTIC_STAGE_RANK)),
            item.code,
            item.path or "",
            -1 if item.line is None else item.line,
            item.message,
        ),
    )


def _semantic_masked_markdown_lines(lines: Sequence[str]) -> list[bool]:
    """Return whether each line is inside a fence or HTML comment.

    Marker examples are deliberately documented in HTML comments.  Treating an
    example as activation would impose a writer duty on every ordinary plan.
    """

    masked: list[bool] = []
    in_fence = False
    in_comment = False
    for line in lines:
        is_masked = in_fence or in_comment
        if not in_fence and not in_comment and FENCE_START_RE.match(line):
            is_masked = True
            in_fence = True
        elif in_fence and FENCE_END_RE.match(line):
            is_masked = True
            in_fence = False

        if not in_fence:
            if in_comment:
                is_masked = True
                if "-->" in line:
                    in_comment = False
            elif "<!--" in line:
                is_masked = True
                if "-->" not in line[line.index("<!--") + 4 :]:
                    in_comment = True
        masked.append(is_masked)
    return masked


def _semantic_h2_sections(lines: Sequence[str], masked: Sequence[bool]) -> list[tuple[int, str, int]]:
    sections: list[tuple[int, str, int]] = []
    for index, line in enumerate(lines):
        if masked[index] or not H2_HEADING_RE.match(line):
            continue
        sections.append((index, line.strip(), len(lines)))
    return [
        (start, title, sections[offset + 1][0] if offset + 1 < len(sections) else len(lines))
        for offset, (start, title, _unused) in enumerate(sections)
    ]


def _semantic_activation(
    plan_path: Path,
    lines: Sequence[str],
    *,
    repo_root: Path,
) -> tuple[bool, list[SemanticObservationDiagnostic]]:
    """Parse the literal opt-in marker and distinguish absence from bad input."""

    diagnostics: list[SemanticObservationDiagnostic] = []
    path_value = _semantic_path_display(plan_path, repo_root)
    masked = _semantic_masked_markdown_lines(lines)
    receipt_sections = [
        (start, end)
        for start, title, end in _semantic_h2_sections(lines, masked)
        if SEMANTIC_RECEIPT_HEADING_RE.match(title)
    ]
    semantic_heading_lines: list[int] = []
    malformed_heading_lines: list[int] = []
    for index, line in enumerate(lines):
        if masked[index]:
            continue
        match = SEMANTIC_H3_HEADING_RE.match(line)
        if match is None:
            continue
        title = match.group("title")
        if title == "Semantic review observation":
            semantic_heading_lines.append(index)
        elif title.casefold() == "semantic review observation":
            malformed_heading_lines.append(index)

    has_attempt = bool(semantic_heading_lines or malformed_heading_lines)
    if not has_attempt:
        return False, diagnostics

    if len(receipt_sections) != 1:
        _semantic_diagnostic(
            diagnostics,
            stage="activation",
            code="semantic_marker_receipt_location_invalid",
            path=path_value,
            line=(semantic_heading_lines or malformed_heading_lines or [0])[0] + 1,
            message="Semantic review observation marker requires exactly one `## Reviewability preflight receipt` section.",
        )
        return True, diagnostics

    receipt_start, receipt_end = receipt_sections[0]
    matching_in_receipt = [line for line in semantic_heading_lines if receipt_start < line < receipt_end]
    malformed_in_receipt = [line for line in malformed_heading_lines if receipt_start < line < receipt_end]
    if malformed_in_receipt:
        _semantic_diagnostic(
            diagnostics,
            stage="activation",
            code="semantic_marker_heading_nonliteral",
            path=path_value,
            line=malformed_in_receipt[0] + 1,
            message="Semantic review observation heading must be literal `### Semantic review observation`.",
        )
    if len(matching_in_receipt) != 1 or len(semantic_heading_lines) != len(matching_in_receipt):
        _semantic_diagnostic(
            diagnostics,
            stage="activation",
            code="semantic_marker_location_or_count_invalid",
            path=path_value,
            line=(matching_in_receipt or semantic_heading_lines or [receipt_start])[0] + 1,
            message="Semantic review observation marker must appear exactly once inside `## Reviewability preflight receipt`.",
        )
        return True, diagnostics

    marker_index = matching_in_receipt[0]
    end_index = receipt_end
    for index in range(marker_index + 1, receipt_end):
        if not masked[index] and SEMANTIC_H3_HEADING_RE.match(lines[index]):
            end_index = index
            break
    body = [line.rstrip(" \t") for line in lines[marker_index + 1 : end_index] if line.strip()]
    if tuple(body) != SEMANTIC_OBSERVATION_MARKER_ROWS:
        _semantic_diagnostic(
            diagnostics,
            stage="activation",
            code="semantic_marker_rows_invalid",
            path=path_value,
            line=marker_index + 1,
            message="Semantic review observation marker must contain exactly the canonical schema/mode/writer rows.",
        )
    return True, diagnostics


def _semantic_evidence_carriers(
    plan_path: Path,
    lines: Sequence[str],
    *,
    repo_root: Path,
) -> tuple[list[SemanticJsonCarrier], list[SemanticObservationDiagnostic]]:
    """Return JSON carriers in the sole Evidence section in physical order."""

    diagnostics: list[SemanticObservationDiagnostic] = []
    path_value = _semantic_path_display(plan_path, repo_root)
    masked = _semantic_masked_markdown_lines(lines)
    evidence_sections = [
        (start, end)
        for start, title, end in _semantic_h2_sections(lines, masked)
        if SEMANTIC_EVIDENCE_HEADING_RE.match(title)
    ]
    if len(evidence_sections) != 1:
        _semantic_diagnostic(
            diagnostics,
            stage="risk",
            code="semantic_evidence_section_invalid",
            path=path_value,
            line=(evidence_sections[1][0] + 1 if len(evidence_sections) > 1 else 1),
            message="Active semantic observation requires exactly one `## Evidence` section.",
        )
        return [], diagnostics

    start, end = evidence_sections[0]
    carriers: list[SemanticJsonCarrier] = []
    in_json = False
    json_start = 0
    buffer: list[str] = []
    for index in range(start + 1, end):
        line = lines[index]
        if not in_json:
            if JSON_FENCE_START_RE.match(line):
                in_json = True
                json_start = index
                buffer = []
            continue
        if FENCE_END_RE.match(line):
            raw = "\n".join(buffer).strip()
            payload: dict[str, Any] | None = None
            kind: str | None = None
            try:
                decoded = json.loads(raw)
            except json.JSONDecodeError:
                if "reviewer_code_risk" in raw:
                    kind = "risk_malformed"
                elif "semantic_review_observation" in raw:
                    kind = "semantic_malformed"
            else:
                if isinstance(decoded, dict):
                    payload = decoded
                    schema_version = decoded.get("schema_version")
                    if decoded.get("lane_id") == "reviewer_code_risk":
                        kind = "risk"
                    elif schema_version == SEMANTIC_OBSERVATION_PROPOSAL_SCHEMA:
                        kind = "proposal"
                    elif schema_version == SEMANTIC_OBSERVATION_SCHEMA:
                        kind = "observation"
                    elif isinstance(schema_version, str) and schema_version.startswith("semantic_review_observation"):
                        kind = "semantic_unknown"
            if kind is not None:
                carriers.append(
                    SemanticJsonCarrier(
                        line_no=json_start + 1,
                        end_line_no=index + 1,
                        payload=payload,
                        raw=raw,
                        kind=kind,
                    )
                )
            in_json = False
            json_start = 0
            buffer = []
            continue
        buffer.append(line)

    if in_json:
        raw = "\n".join(buffer)
        if "reviewer_code_risk" in raw or "semantic_review_observation" in raw:
            _semantic_diagnostic(
                diagnostics,
                stage="risk" if "reviewer_code_risk" in raw else "observation_schema",
                code="semantic_json_fence_unclosed",
                path=path_value,
                line=json_start + 1,
                message="Semantic observation JSON carrier fence is not closed inside `## Evidence`.",
            )
    return carriers, diagnostics


def _semantic_normalize_section_text(lines: Sequence[str]) -> str:
    normalized: list[str] = []
    in_fence = False
    for raw_line in lines:
        line = re.sub(r"[ \t]+$", "", raw_line).replace("\r", "")
        if in_fence:
            normalized.append(line)
            if FENCE_END_RE.match(line):
                in_fence = False
            continue
        if FENCE_START_RE.match(line):
            normalized.append(line)
            in_fence = True
            continue
        # Completion is lifecycle noise only for an actual Markdown task-list
        # marker outside a fenced literal.  Keep arbitrary `[x]` prose, inline
        # code, regexes and examples byte-significant in the fingerprint.
        normalized.append(re.sub(r"^(\s*(?:[-+*]|\d+[.)])\s+\[)[xX](\])", r"\1 \2", line))
    while normalized and not normalized[0].strip():
        normalized.pop(0)
    while normalized and not normalized[-1].strip():
        normalized.pop()
    return "\n".join(normalized)


def _semantic_exact_h2_section(
    lines: Sequence[str],
    masked: Sequence[bool],
    heading: str,
) -> tuple[int, list[str]] | None:
    matches: list[tuple[int, int]] = []
    for start, title, end in _semantic_h2_sections(lines, masked):
        if title == f"## {heading}":
            matches.append((start, end))
    if len(matches) != 1:
        return None
    start, end = matches[0]
    return start + 1, list(lines[start:end])


def _semantic_normalized_paths(
    raw_items: object,
    *,
    item_label: str,
) -> tuple[list[str] | None, str | None]:
    if not isinstance(raw_items, list):
        return None, f"`code_draft_meta.{item_label}` must be a list"
    paths: list[str] = []
    for item in raw_items:
        if not isinstance(item, dict):
            return None, f"`code_draft_meta.{item_label}` entry must be an object"
        normalized, problem = normalize_state_transition_protected_path(item.get("path"))
        if problem or normalized is None:
            return None, f"`code_draft_meta.{item_label}` path {item.get('path')!r} {problem or 'is invalid'}"
        paths.append(normalized)
    if len(set(paths)) != len(paths):
        return None, f"`code_draft_meta.{item_label}` must not duplicate paths"
    return sorted(paths), None


def _semantic_state_transition_payload(declaration: StateTransitionDeclarations) -> list[dict[str, object]]:
    payload: list[dict[str, object]] = []
    for label, fields in declaration.normalized_fields:
        payload.append(
            {
                "label": label,
                "fields": {key: value for key, value in fields},
            }
        )
    return payload


def _semantic_contract_fingerprint(
    plan_path: Path,
    lines: Sequence[str],
    *,
    repo_root: Path,
) -> tuple[dict[str, object] | None, str | None, int | None, list[SemanticObservationDiagnostic]]:
    """Build ``contract_fingerprint.v1`` from the frozen hash basis."""

    diagnostics: list[SemanticObservationDiagnostic] = []
    path_value = _semantic_path_display(plan_path, repo_root)
    live_refs = extract_live_review_artifact_refs(list(lines))
    review_artifact: str | None = None
    review_line: int | None = None
    if len(live_refs) != 1:
        _semantic_diagnostic(
            diagnostics,
            stage="fingerprint",
            code="semantic_live_review_route_invalid",
            path=path_value,
            line=live_refs[1][0] if len(live_refs) > 1 else 1,
            message="Semantic fingerprint requires exactly one literal live review artifact path.",
        )
    else:
        review_line, review_artifact = live_refs[0]
        normalized_path, problem = normalize_state_transition_protected_path(review_artifact)
        if problem or normalized_path is None:
            _semantic_diagnostic(
                diagnostics,
                stage="fingerprint",
                code="semantic_live_review_path_invalid",
                path=path_value,
                line=review_line,
                message="Semantic fingerprint live review artifact must be a normalized repo-relative POSIX path.",
            )
        else:
            review_artifact = normalized_path

    draft_refs = extract_code_draft_refs(list(lines))
    code_draft_path = select_primary_code_draft_path(plan_path, draft_refs, plan_repo_root=repo_root)
    if code_draft_path is None:
        _semantic_diagnostic(
            diagnostics,
            stage="code_draft",
            code="semantic_code_draft_missing",
            path=path_value,
            line=1,
            message="Active semantic observation requires a linked code draft with `code_draft_meta`.",
        )
        return None, review_artifact, review_line, diagnostics

    meta, meta_error = extract_code_draft_meta(code_draft_path)
    if meta_error or meta is None:
        _semantic_diagnostic(
            diagnostics,
            stage="code_draft",
            code="semantic_code_draft_meta_invalid",
            path=_semantic_path_display(code_draft_path, repo_root),
            line=1,
            message=f"Semantic fingerprint cannot read code_draft_meta: {meta_error or 'invalid metadata'}.",
        )
        return None, review_artifact, review_line, diagnostics
    expected_plan = _semantic_path_display(plan_path, repo_root)
    if meta.get("plan") != expected_plan:
        _semantic_diagnostic(
            diagnostics,
            stage="code_draft",
            code="semantic_code_draft_plan_mismatch",
            path=_semantic_path_display(code_draft_path, repo_root),
            line=1,
            message=f"`code_draft_meta.plan` must equal `{expected_plan}` for semantic fingerprinting.",
        )
    target_paths, target_error = _semantic_normalized_paths(meta.get("targets"), item_label="targets")
    deleted_paths, deleted_error = _semantic_normalized_paths(
        meta.get("deleted_paths", []), item_label="deleted_paths"
    )
    if target_error:
        _semantic_diagnostic(
            diagnostics,
            stage="code_draft",
            code="semantic_code_draft_targets_invalid",
            path=_semantic_path_display(code_draft_path, repo_root),
            line=1,
            message=target_error + ".",
        )
    if deleted_error:
        _semantic_diagnostic(
            diagnostics,
            stage="code_draft",
            code="semantic_code_draft_deleted_paths_invalid",
            path=_semantic_path_display(code_draft_path, repo_root),
            line=1,
            message=deleted_error + ".",
        )

    masked = _semantic_masked_markdown_lines(lines)
    sections: dict[str, str] = {}
    for heading in SEMANTIC_FINGERPRINT_SECTION_HEADINGS:
        section = _semantic_exact_h2_section(lines, masked, heading)
        if section is None:
            _semantic_diagnostic(
                diagnostics,
                stage="fingerprint",
                code="semantic_fingerprint_section_invalid",
                path=path_value,
                line=1,
                message=f"Semantic fingerprint requires exactly one literal `## {heading}` section.",
            )
            continue
        _line_no, section_lines = section
        sections[heading] = _semantic_normalize_section_text(section_lines)

    plan_declarations = parse_state_transition_declarations(plan_path, list(lines))
    if plan_declarations.findings or plan_declarations.declaration is None:
        _semantic_diagnostic(
            diagnostics,
            stage="fingerprint",
            code="semantic_state_transition_declarations_invalid",
            path=path_value,
            line=(plan_declarations.heading_lines[0] if plan_declarations.heading_lines else 1),
            message="Semantic fingerprint requires one valid canonical state-transition declaration block.",
        )
    else:
        draft_declarations = parse_state_transition_declarations(code_draft_path, read_text(code_draft_path))
        if (
            draft_declarations.findings
            or draft_declarations.declaration is None
            or draft_declarations.declaration.normalized_fields != plan_declarations.declaration.normalized_fields
        ):
            _semantic_diagnostic(
                diagnostics,
                stage="code_draft",
                code="semantic_state_transition_declaration_parity_invalid",
                path=_semantic_path_display(code_draft_path, repo_root),
                line=(draft_declarations.heading_lines[0] if draft_declarations.heading_lines else 1),
                message="Code-draft state-transition declarations must be valid and normalized-equal to PLAN_PATH.",
            )

    if diagnostics or target_paths is None or deleted_paths is None or review_artifact is None:
        return None, review_artifact, review_line, diagnostics

    assert plan_declarations.declaration is not None
    payload = {
        "schema_version": SEMANTIC_CONTRACT_FINGERPRINT_SCHEMA,
        "target_paths": target_paths,
        "deleted_paths": deleted_paths,
        "review_artifact": review_artifact,
        "sections": sections,
        "state_transition_declarations": _semantic_state_transition_payload(plan_declarations.declaration),
    }
    return (
        {
            "schema_version": SEMANTIC_CONTRACT_FINGERPRINT_SCHEMA,
            "sha256": _semantic_sha256(payload),
            "target_paths": target_paths,
            "deleted_paths": deleted_paths,
        },
        review_artifact,
        review_line,
        diagnostics,
    )


def build_semantic_review_contract_fingerprint(plan_path: str | Path) -> dict[str, object] | None:
    """Public read-only fingerprint projection, or ``None`` when inputs are invalid."""

    path = Path(plan_path)
    try:
        lines = read_text(path)
    except OSError:
        return None
    fingerprint, _review_artifact, _review_line, diagnostics = _semantic_contract_fingerprint(
        path,
        lines,
        repo_root=repo_root_for_plan_path(path),
    )
    return fingerprint if not diagnostics else None


def _semantic_current_live_blocker_ids(
    review_lines: Sequence[str],
    *,
    review_artifact: str,
) -> tuple[list[SemanticObservationDiagnostic], frozenset[int] | None]:
    """Parse canonical current ``## S1 Blocker`` records from one live review.

    Historical prose and arbitrary ``Blocker ID`` mentions are deliberately not
    semantic input.  Only immediate canonical ``### B<N>)`` records under the
    exact S1 section can contribute an ``open`` blocker to the current
    generation.
    """

    diagnostics: list[SemanticObservationDiagnostic] = []
    masked = _semantic_masked_markdown_lines(review_lines)
    section_indexes = [
        index
        for index, line in enumerate(review_lines)
        if not masked[index] and SEMANTIC_S1_BLOCKER_HEADING_RE.match(line)
    ]
    if len(section_indexes) > 1:
        _semantic_diagnostic(
            diagnostics,
            stage="live_review",
            code="semantic_live_review_blocker_section_ambiguous",
            path=review_artifact,
            line=section_indexes[1] + 1,
            message="Live review may contain at most one canonical `## S1 Blocker` section.",
        )
        return diagnostics, None
    if not section_indexes:
        return diagnostics, frozenset()

    section_start = section_indexes[0]
    section_end = next(
        (
            index
            for index in range(section_start + 1, len(review_lines))
            if not masked[index] and H2_HEADING_RE.match(review_lines[index])
        ),
        len(review_lines),
    )
    records: list[tuple[int, int]] = []
    for index in range(section_start + 1, section_end):
        if masked[index]:
            continue
        if SEMANTIC_BLOCKER_RECORD_HEADING_RE.match(review_lines[index]):
            records.append((index, section_end))
        elif SEMANTIC_BLOCKER_RECORD_PREFIX_RE.match(review_lines[index]):
            _semantic_diagnostic(
                diagnostics,
                stage="live_review",
                code="semantic_live_review_blocker_heading_invalid",
                path=review_artifact,
                line=index + 1,
                message="Canonical current blocker heading must use exact `### B<N>)` grammar.",
            )
    records = [
        (start, records[offset + 1][0] if offset + 1 < len(records) else section_end)
        for offset, (start, _unused_end) in enumerate(records)
    ]

    seen_ids: set[int] = set()
    open_ids: set[int] = set()
    for record_start, record_end in records:
        heading_match = SEMANTIC_BLOCKER_RECORD_HEADING_RE.match(review_lines[record_start])
        assert heading_match is not None
        heading_id = int(heading_match.group("number"))
        id_fields = [
            (index, match.group("value").strip())
            for index in range(record_start + 1, record_end)
            if not masked[index]
            and (match := SEMANTIC_BLOCKER_ID_FIELD_RE.match(review_lines[index])) is not None
        ]
        state_fields = [
            (index, match.group("value").strip())
            for index in range(record_start + 1, record_end)
            if not masked[index]
            and (match := SEMANTIC_BLOCKER_STATE_RE.match(review_lines[index])) is not None
        ]
        expected_id = f"B{heading_id}"
        if len(id_fields) != 1 or id_fields[0][1] != expected_id:
            _semantic_diagnostic(
                diagnostics,
                stage="live_review",
                code="semantic_live_review_blocker_id_invalid",
                path=review_artifact,
                line=record_start + 1,
                message=(
                    "Canonical blocker record must contain exactly one matching "
                    f"`Blocker ID: {expected_id}` row."
                ),
            )
            continue
        if heading_id in seen_ids:
            _semantic_diagnostic(
                diagnostics,
                stage="live_review",
                code="semantic_live_review_blocker_id_duplicate",
                path=review_artifact,
                line=id_fields[0][0] + 1,
                message="Canonical live blocker IDs must be unique.",
            )
            continue
        seen_ids.add(heading_id)
        if len(state_fields) != 1:
            _semantic_diagnostic(
                diagnostics,
                stage="live_review",
                code="semantic_live_review_blocker_state_missing_or_ambiguous",
                path=review_artifact,
                line=record_start + 1,
                message="Canonical blocker record must contain exactly one `Current state` row.",
            )
            continue
        state = _normalize_text(state_fields[0][1].replace("`", ""))
        if state not in SEMANTIC_CURRENT_BLOCKER_STATES:
            _semantic_diagnostic(
                diagnostics,
                stage="live_review",
                code="semantic_live_review_blocker_state_invalid",
                path=review_artifact,
                line=state_fields[0][0] + 1,
                message="Canonical blocker Current state must be open, historical-fixed or superseded.",
            )
            continue
        if state == "open":
            open_ids.add(heading_id)

    if diagnostics:
        return diagnostics, None
    return diagnostics, frozenset(open_ids)


def _semantic_validate_live_review_artifact(
    *,
    repo_root: Path,
    plan_path: Path,
    review_artifact: str | None,
    review_line: int | None,
    target_snapshot: str | None,
) -> tuple[list[SemanticObservationDiagnostic], frozenset[int] | None]:
    """Validate the authoritative current review and return its canonical B ids.

    This deliberately avoids importing ``review_artifact_lint``: that module
    depends on this one.  The small read-only checks below are the semantic
    producer's freshness boundary, not a second review-artifact selector.
    """

    diagnostics: list[SemanticObservationDiagnostic] = []
    if review_artifact is None:
        return diagnostics, None
    review_path = (repo_root / review_artifact).resolve()
    if not review_path.is_file():
        _semantic_diagnostic(
            diagnostics,
            stage="live_review",
            code="semantic_live_review_artifact_missing",
            path=review_artifact,
            line=review_line,
            message="Selected risk generation requires the declared live review artifact to exist.",
        )
        return diagnostics, None
    review_lines = read_text(review_path)
    header_target, target_line = review_header_metadata.singleton_header_value(review_lines, "target")
    if header_target is None:
        _semantic_diagnostic(
            diagnostics,
            stage="live_review",
            code="semantic_live_review_target_invalid",
            path=review_artifact,
            line=target_line,
            message="Selected risk generation requires one canonical `**Target:**` header in the live review artifact.",
        )
    elif target_snapshot is not None and _normalize_literal(header_target) != target_snapshot:
        _semantic_diagnostic(
            diagnostics,
            stage="live_review",
            code="semantic_live_review_target_snapshot_mismatch",
            path=review_artifact,
            line=target_line,
            message="Live review `**Target:**` does not match the helper-selected risk-lane target snapshot.",
        )
    header_status, status_line = review_header_metadata.singleton_header_value(review_lines, "status")
    normalized_header_status = normalize_review_status(header_status)
    if normalized_header_status not in CODE_DOC_REVIEW_FINAL_STATUS_NORMS:
        _semantic_diagnostic(
            diagnostics,
            stage="live_review",
            code="semantic_live_review_status_not_final",
            path=review_artifact,
            line=status_line,
            message="Selected semantic generation requires one canonical final `**Status:**` outcome in the live review artifact.",
        )
    if isinstance(target_snapshot, str) and target_snapshot.startswith(CURRENT_BUNDLE_TARGET + " "):
        try:
            current_snapshot = build_current_bundle_snapshot(plan_path, project_root=repo_root)
        except SnapshotError as exc:
            _semantic_diagnostic(
                diagnostics,
                stage="live_review",
                code="semantic_current_target_snapshot_unavailable",
                path=review_artifact,
                line=target_line,
                message=f"Current bundle snapshot cannot be recomputed: {exc}.",
            )
        else:
            current_target = current_snapshot.get("target")
            if current_target != target_snapshot:
                _semantic_diagnostic(
                    diagnostics,
                    stage="current_head",
                    code="semantic_current_target_snapshot_stale",
                    path=review_artifact,
                    line=target_line,
                    message="The selected BUNDLE=current target_snapshot no longer matches current target bytes.",
                )

    normalized_aggregate_status: str | None = None
    aggregate_indexes = [
        index for index, line in enumerate(review_lines) if SEMANTIC_AGGREGATE_HEADING_RE.match(line)
    ]
    contracts_indexes = [
        index for index, line in enumerate(review_lines) if SEMANTIC_CONTRACTS_LANE_HEADING_RE.match(line)
    ]
    if len(contracts_indexes) != 1:
        _semantic_diagnostic(
            diagnostics,
            stage="live_review",
            code="semantic_contracts_lane_missing_or_ambiguous",
            path=review_artifact,
            line=1,
            message="Selected semantic generation requires exactly one reviewer_code_contracts review section.",
        )
    if len(aggregate_indexes) != 1:
        _semantic_diagnostic(
            diagnostics,
            stage="live_review",
            code="semantic_aggregate_verdict_missing_or_ambiguous",
            path=review_artifact,
            line=1,
            message="Selected semantic generation requires exactly one `## Lane synthesis / aggregate verdict` section.",
        )
    else:
        aggregate_start = aggregate_indexes[0]
        aggregate_end = next(
            (
                index
                for index in range(aggregate_start + 1, len(review_lines))
                if H2_HEADING_RE.match(review_lines[index])
            ),
            len(review_lines),
        )
        aggregate_statuses = [
            (index, match.group("value").strip())
            for index in range(aggregate_start + 1, aggregate_end)
            if (match := SEMANTIC_AGGREGATE_STATUS_RE.match(review_lines[index])) is not None
        ]
        if len(aggregate_statuses) != 1 or not aggregate_statuses[0][1]:
            _semantic_diagnostic(
                diagnostics,
                stage="live_review",
                code="semantic_aggregate_status_missing_or_ambiguous",
                path=review_artifact,
                line=aggregate_start + 1,
                message="Lane synthesis / aggregate verdict must contain exactly one non-empty Aggregate status.",
            )
        else:
            aggregate_line, aggregate_status = aggregate_statuses[0]
            normalized_aggregate_status = normalize_review_status(aggregate_status)
            if normalized_aggregate_status not in CODE_DOC_REVIEW_FINAL_STATUS_NORMS:
                _semantic_diagnostic(
                    diagnostics,
                    stage="live_review",
                    code="semantic_aggregate_status_not_final",
                    path=review_artifact,
                    line=aggregate_line + 1,
                    message="Lane synthesis / aggregate verdict must use one canonical final Aggregate status.",
                )
            elif (
                normalized_header_status in CODE_DOC_REVIEW_FINAL_STATUS_NORMS
                and normalized_aggregate_status != normalized_header_status
            ):
                _semantic_diagnostic(
                    diagnostics,
                    stage="live_review",
                    code="semantic_live_review_status_mismatch",
                    path=review_artifact,
                    line=aggregate_line + 1,
                    message="Live review `**Status:**` and Aggregate status must carry the same canonical final outcome.",
                )

    blocker_diagnostics, blocker_ids = _semantic_current_live_blocker_ids(
        review_lines,
        review_artifact=review_artifact,
    )
    diagnostics.extend(blocker_diagnostics)
    if (
        blocker_ids is not None
        and normalized_header_status in CODE_DOC_REVIEW_FINAL_STATUS_NORMS
        and normalized_aggregate_status == normalized_header_status
    ):
        if normalized_header_status == CODE_DOC_REVIEW_OK_STATUS_NORM and blocker_ids:
            _semantic_diagnostic(
                diagnostics,
                stage="live_review",
                code="semantic_live_review_green_open_blockers",
                path=review_artifact,
                line=status_line,
                message="Green live review and aggregate verdict require zero canonical open blocker records.",
            )
        elif normalized_header_status == CODE_DOC_REVIEW_BLOCKER_STATUS_NORM and not blocker_ids:
            _semantic_diagnostic(
                diagnostics,
                stage="live_review",
                code="semantic_live_review_red_without_open_blockers",
                path=review_artifact,
                line=status_line,
                message="Red live review and aggregate verdict require at least one canonical open blocker record.",
            )
    return diagnostics, blocker_ids


def _semantic_blocker_ref_number(value: object, *, review_artifact: str) -> int | None:
    if not isinstance(value, str):
        return None
    prefix = f"{review_artifact}#B"
    if not value.startswith(prefix):
        return None
    suffix = value[len(prefix) :]
    if not suffix.isdigit() or suffix.startswith("0"):
        return None
    return int(suffix)


def _semantic_missing_live_blocker_refs(
    blockers: object,
    *,
    review_artifact: str,
    live_blocker_ids: frozenset[int],
) -> list[str]:
    """Return canonical blocker refs no longer present in the live review."""

    if not isinstance(blockers, list):
        return []
    missing: list[str] = []
    for blocker in blockers:
        if not isinstance(blocker, dict):
            continue
        blocker_ref = blocker.get("blocker_ref")
        number = _semantic_blocker_ref_number(blocker_ref, review_artifact=review_artifact)
        if isinstance(blocker_ref, str) and number is not None and number not in live_blocker_ids:
            missing.append(blocker_ref)
    return missing


def _semantic_blocker_refs(
    blockers: object,
    *,
    review_artifact: str,
) -> frozenset[str]:
    """Return canonical blocker refs carried by a validated proposal/final."""

    if not isinstance(blockers, list):
        return frozenset()
    refs: set[str] = set()
    for blocker in blockers:
        if not isinstance(blocker, dict):
            continue
        blocker_ref = blocker.get("blocker_ref")
        if (
            isinstance(blocker_ref, str)
            and _semantic_blocker_ref_number(blocker_ref, review_artifact=review_artifact) is not None
        ):
            refs.add(blocker_ref)
    return frozenset(refs)


def _semantic_expected_live_blocker_refs(
    live_blocker_ids: frozenset[int],
    *,
    review_artifact: str,
) -> frozenset[str]:
    return frozenset(f"{review_artifact}#B{number}" for number in live_blocker_ids)


def _semantic_blocker_ref_sort_key(value: str) -> tuple[str, int]:
    match = SEMANTIC_BLOCKER_REF_SUFFIX_RE.search(value)
    return (value[: match.start()] if match else value, int(match.group("number")) if match else -1)


def _semantic_fingerprint_shape_valid(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != {"schema_version", "sha256", "target_paths", "deleted_paths"}:
        return False
    if value.get("schema_version") != SEMANTIC_CONTRACT_FINGERPRINT_SCHEMA:
        return False
    if not isinstance(value.get("sha256"), str) or SEMANTIC_SHA256_RE.fullmatch(value["sha256"]) is None:
        return False
    for key in ("target_paths", "deleted_paths"):
        raw_paths = value.get(key)
        if not isinstance(raw_paths, list) or raw_paths != sorted(set(raw_paths)):
            return False
        for path in raw_paths:
            normalized, problem = normalize_state_transition_protected_path(path)
            if problem or normalized != path:
                return False
    return True


def _semantic_validate_proposal(
    proposal: object,
    *,
    review_artifact: str,
    predecessor: dict[str, Any] | None,
    contract_fingerprint: dict[str, object] | None,
    target_snapshot: str | None,
    plan_path_value: str,
    line_no: int,
) -> tuple[dict[str, Any] | None, list[SemanticObservationDiagnostic]]:
    diagnostics: list[SemanticObservationDiagnostic] = []
    if not isinstance(proposal, dict) or set(proposal) != set(SEMANTIC_PROPOSAL_FIELDS):
        _semantic_diagnostic(
            diagnostics,
            stage="proposal",
            code="semantic_proposal_root_schema_invalid",
            path=plan_path_value,
            line=line_no,
            message="Semantic role proposal must contain exactly the V1 five root fields.",
        )
        return None, diagnostics
    if proposal.get("schema_version") != SEMANTIC_OBSERVATION_PROPOSAL_SCHEMA:
        _semantic_diagnostic(
            diagnostics,
            stage="proposal",
            code="semantic_proposal_version_invalid",
            path=plan_path_value,
            line=line_no,
            message="Semantic role proposal has an unsupported schema_version.",
        )
    progress = proposal.get("progress_verdict")
    if not isinstance(progress, str) or progress not in SEMANTIC_PROGRESS_VERDICTS:
        _semantic_diagnostic(
            diagnostics,
            stage="role",
            code="semantic_progress_verdict_invalid",
            path=plan_path_value,
            line=line_no,
            message="Semantic proposal progress_verdict must be one accepted V1 enum.",
        )
    evidence_refs = proposal.get("progress_evidence_refs")
    if not isinstance(evidence_refs, list) or any(not isinstance(value, str) or not value.strip() for value in evidence_refs):
        _semantic_diagnostic(
            diagnostics,
            stage="role",
            code="semantic_progress_evidence_refs_invalid",
            path=plan_path_value,
            line=line_no,
            message="Semantic proposal progress_evidence_refs must be a list of non-empty strings.",
        )

    raw_blockers = proposal.get("blockers")
    blockers: list[dict[str, Any]] = []
    if not isinstance(raw_blockers, list):
        _semantic_diagnostic(
            diagnostics,
            stage="proposal",
            code="semantic_proposal_blockers_invalid",
            path=plan_path_value,
            line=line_no,
            message="Semantic proposal blockers must be a list.",
        )
    else:
        last_number = 0
        seen_refs: set[str] = set()
        for blocker in raw_blockers:
            if not isinstance(blocker, dict) or set(blocker) != set(SEMANTIC_BLOCKER_PROPOSAL_FIELDS):
                _semantic_diagnostic(
                    diagnostics,
                    stage="proposal",
                    code="semantic_proposal_blocker_schema_invalid",
                    path=plan_path_value,
                    line=line_no,
                    message="Each semantic proposal blocker must contain exactly blocker_ref, lineage_relation and predecessor_blocker_ref.",
                )
                continue
            raw_ref = blocker.get("blocker_ref")
            ref: str | None = raw_ref if isinstance(raw_ref, str) else None
            # The parser rejects non-string refs through the existing
            # diagnostic path.  Narrow here so the canonical-ref set only
            # ever receives the validated string form.
            number = (
                _semantic_blocker_ref_number(ref, review_artifact=review_artifact)
                if isinstance(ref, str)
                else None
            )
            relation = blocker.get("lineage_relation")
            predecessor_ref = blocker.get("predecessor_blocker_ref")
            if number is None:
                _semantic_diagnostic(
                    diagnostics,
                    stage="proposal",
                    code="semantic_proposal_blocker_ref_invalid",
                    path=plan_path_value,
                    line=line_no,
                    message=f"Semantic blocker_ref must use `{review_artifact}#B<N>` canonical grammar.",
                )
            elif number <= last_number or ref in seen_refs:
                _semantic_diagnostic(
                    diagnostics,
                    stage="proposal",
                    code="semantic_proposal_blockers_unsorted_or_duplicate",
                    path=plan_path_value,
                    line=line_no,
                    message="Semantic proposal blockers must be sorted by canonical B<N> and unique.",
                )
            else:
                assert ref is not None
                last_number = number
                seen_refs.add(ref)
            if not isinstance(relation, str) or relation not in SEMANTIC_LINEAGE_RELATIONS:
                _semantic_diagnostic(
                    diagnostics,
                    stage="proposal",
                    code="semantic_proposal_lineage_relation_invalid",
                    path=plan_path_value,
                    line=line_no,
                    message="Semantic proposal blocker lineage_relation is invalid.",
                )
            if relation in {"first_observation", "independent_boundary"} and predecessor_ref is not None:
                _semantic_diagnostic(
                    diagnostics,
                    stage="proposal",
                    code="semantic_proposal_predecessor_forbidden",
                    path=plan_path_value,
                    line=line_no,
                    message="first_observation and independent_boundary blockers require predecessor_blocker_ref=null.",
                )
            if relation == "same_family" and not isinstance(predecessor_ref, str):
                _semantic_diagnostic(
                    diagnostics,
                    stage="proposal",
                    code="semantic_proposal_predecessor_required",
                    path=plan_path_value,
                    line=line_no,
                    message="same_family blockers require a literal predecessor_blocker_ref.",
                )
            blockers.append(blocker)

    raw_resolved = proposal.get("resolved_predecessor_blocker_refs")
    resolved_refs: list[str] = []
    if not isinstance(raw_resolved, list) or any(not isinstance(value, str) for value in raw_resolved):
        _semantic_diagnostic(
            diagnostics,
            stage="proposal",
            code="semantic_proposal_resolved_refs_invalid",
            path=plan_path_value,
            line=line_no,
            message="resolved_predecessor_blocker_refs must be a list of canonical string refs.",
        )
    else:
        resolved_refs = list(raw_resolved)
        if len(set(resolved_refs)) != len(resolved_refs) or resolved_refs != sorted(
            resolved_refs, key=_semantic_blocker_ref_sort_key
        ):
            _semantic_diagnostic(
                diagnostics,
                stage="proposal",
                code="semantic_proposal_resolved_refs_unsorted_or_duplicate",
                path=plan_path_value,
                line=line_no,
                message="resolved_predecessor_blocker_refs must be sorted and unique.",
            )

    predecessor_blockers: dict[str, dict[str, Any]] = {}
    if predecessor is not None:
        for blocker in predecessor.get("blockers", []):
            if isinstance(blocker, dict) and isinstance(blocker.get("blocker_ref"), str):
                predecessor_blockers[blocker["blocker_ref"]] = blocker

    same_refs: list[str] = []
    for blocker in blockers:
        relation = blocker.get("lineage_relation")
        predecessor_ref = blocker.get("predecessor_blocker_ref")
        if predecessor is None:
            if relation == "same_family":
                _semantic_diagnostic(
                    diagnostics,
                    stage="proposal",
                    code="semantic_proposal_same_family_without_head",
                    path=plan_path_value,
                    line=line_no,
                    message="same_family is forbidden before the first accepted semantic observation.",
                )
            if relation == "independent_boundary":
                _semantic_diagnostic(
                    diagnostics,
                    stage="proposal",
                    code="semantic_proposal_independent_before_head",
                    path=plan_path_value,
                    line=line_no,
                    message="independent_boundary requires an immediately preceding accepted observation head.",
                )
        else:
            if relation == "first_observation":
                _semantic_diagnostic(
                    diagnostics,
                    stage="proposal",
                    code="semantic_proposal_first_with_head",
                    path=plan_path_value,
                    line=line_no,
                    message="first_observation is forbidden after an accepted semantic observation head exists.",
                )
            if relation == "same_family":
                if predecessor_ref not in predecessor_blockers:
                    _semantic_diagnostic(
                        diagnostics,
                        stage="proposal",
                        code="semantic_proposal_predecessor_not_in_head",
                        path=plan_path_value,
                        line=line_no,
                        message="same_family predecessor_blocker_ref must resolve in the immediately preceding head.",
                    )
                elif predecessor_ref in same_refs:
                    _semantic_diagnostic(
                        diagnostics,
                        stage="proposal",
                        code="semantic_proposal_predecessor_reused",
                        path=plan_path_value,
                        line=line_no,
                        message="One predecessor blocker family may survive through same_family only once.",
                    )
                else:
                    same_refs.append(predecessor_ref)

    if predecessor is None:
        if resolved_refs:
            _semantic_diagnostic(
                diagnostics,
                stage="proposal",
                code="semantic_proposal_resolves_without_head",
                path=plan_path_value,
                line=line_no,
                message="First semantic observation cannot resolve predecessor blocker families.",
            )
    else:
        for ref in resolved_refs:
            if ref not in predecessor_blockers:
                _semantic_diagnostic(
                    diagnostics,
                    stage="proposal",
                    code="semantic_proposal_resolved_ref_not_in_head",
                    path=plan_path_value,
                    line=line_no,
                    message="resolved_predecessor_blocker_refs must resolve in the immediately preceding head.",
                )
        surviving_or_resolved = set(same_refs) | set(resolved_refs)
        if set(same_refs) & set(resolved_refs) or surviving_or_resolved != set(predecessor_blockers):
            _semantic_diagnostic(
                diagnostics,
                stage="proposal",
                code="semantic_proposal_family_accounting_invalid",
                path=plan_path_value,
                line=line_no,
                message="Every immediate-predecessor blocker family must survive exactly once or resolve exactly once.",
            )

    progress_value = proposal.get("progress_verdict")
    if predecessor is None:
        expected_progress = "first_observation"
    else:
        has_same_family = bool(same_refs)
        has_independent_boundary = any(
            blocker.get("lineage_relation") == "independent_boundary" for blocker in blockers
        )
        has_resolved_family = bool(resolved_refs)
        previous_fingerprint = predecessor.get("contract_fingerprint")
        previous_sha = previous_fingerprint.get("sha256") if isinstance(previous_fingerprint, dict) else None
        current_sha = contract_fingerprint.get("sha256") if isinstance(contract_fingerprint, dict) else None
        target_drift = isinstance(target_snapshot, str) and predecessor.get("target_snapshot") != target_snapshot
        contract_drift = isinstance(current_sha, str) and previous_sha != current_sha

        # The role owns the semantic judgment, but this V1 carrier has a
        # declared deterministic summary precedence.  Validate that the
        # submitted enum agrees with its own lineage facts; do not select or
        # rewrite a verdict on the role's behalf.
        if target_drift or contract_drift:
            expected_progress = "scope_churn"
        elif has_independent_boundary:
            expected_progress = "independent_boundary"
        elif has_same_family:
            expected_progress = "same_contract_stalled"
        elif has_resolved_family:
            expected_progress = "same_contract_progress"
        else:
            expected_progress = None

    if expected_progress is None:
        _semantic_diagnostic(
            diagnostics,
            stage="role",
            code="semantic_progress_relation_missing",
            path=plan_path_value,
            line=line_no,
            message="A later semantic observation must declare a predecessor relation, closure, independent boundary or contract/target drift.",
        )
    elif progress_value != expected_progress:
        _semantic_diagnostic(
            diagnostics,
            stage="role",
            code="semantic_progress_precedence_invalid",
            path=plan_path_value,
            line=line_no,
            message=(
                "progress_verdict must match the declared V1 lineage precedence; "
                f"expected={expected_progress}, received={progress_value!r}."
            ),
        )

    if diagnostics:
        return None, diagnostics
    return proposal, diagnostics


def _semantic_generation_id(*, risk_run_id: str, review_artifact: str, target_snapshot: str) -> str:
    return "rgo_" + _semantic_sha256(
        {
            "schema_version": SEMANTIC_REVIEW_GENERATION_SCHEMA,
            "risk_run_id": risk_run_id,
            "review_artifact": review_artifact,
            "target_snapshot": target_snapshot,
        }
    )


def _semantic_observation_id(review_generation_id: str) -> str:
    return "sro_" + _semantic_sha256(
        {
            "schema_version": SEMANTIC_OBSERVATION_SCHEMA,
            "review_generation_id": review_generation_id,
        }
    )


def _semantic_blocker_family_id(*, observation_id: str, blocker_ref: str) -> str:
    return "bf_" + _semantic_sha256(
        {
            "schema_version": SEMANTIC_BLOCKER_FAMILY_SCHEMA,
            "observation_id": observation_id,
            "blocker_ref": blocker_ref,
        }
    )


def _semantic_materialize_observation(
    proposal: dict[str, Any],
    *,
    risk_run_id: str,
    target_snapshot: str,
    review_artifact: str,
    contract_fingerprint: dict[str, object],
    predecessor: dict[str, Any] | None,
) -> tuple[dict[str, object], dict[str, object]]:
    """Inject all machine-owned V1 fields into one validated role proposal."""

    review_generation_id = _semantic_generation_id(
        risk_run_id=risk_run_id,
        review_artifact=review_artifact,
        target_snapshot=target_snapshot,
    )
    observation_id = _semantic_observation_id(review_generation_id)
    predecessor_observation_id = predecessor.get("observation_id") if predecessor is not None else None
    predecessor_families: dict[str, str] = {}
    if predecessor is not None:
        for item in predecessor.get("blockers", []):
            if isinstance(item, dict):
                ref = item.get("blocker_ref")
                family = item.get("blocker_family_id")
                if isinstance(ref, str) and isinstance(family, str):
                    predecessor_families[ref] = family

    machine_blockers: list[dict[str, object]] = []
    blocker_machine_fields: list[dict[str, str]] = []
    for role_blocker in proposal["blockers"]:
        assert isinstance(role_blocker, dict)
        blocker_ref = role_blocker["blocker_ref"]
        relation = role_blocker["lineage_relation"]
        predecessor_ref = role_blocker["predecessor_blocker_ref"]
        assert isinstance(blocker_ref, str)
        if relation == "same_family":
            assert isinstance(predecessor_ref, str)
            family_id = predecessor_families[predecessor_ref]
        else:
            family_id = _semantic_blocker_family_id(observation_id=observation_id, blocker_ref=blocker_ref)
        machine_blockers.append(
            {
                "blocker_ref": blocker_ref,
                "lineage_relation": relation,
                "predecessor_blocker_ref": predecessor_ref,
                "blocker_family_id": family_id,
            }
        )
        blocker_machine_fields.append({"blocker_ref": blocker_ref, "blocker_family_id": family_id})

    resolved_ids = sorted(
        {
            predecessor_families[ref]
            for ref in proposal["resolved_predecessor_blocker_refs"]
            if isinstance(ref, str)
        }
    )
    proposal_sha256 = _semantic_sha256(proposal)
    fields: dict[str, object] = {
        "risk_run_id": risk_run_id,
        "target_snapshot": target_snapshot,
        "review_artifact": review_artifact,
        "review_generation_id": review_generation_id,
        "observation_id": observation_id,
        "contract_fingerprint": contract_fingerprint,
        "predecessor_observation_id": predecessor_observation_id,
        "proposal_sha256": proposal_sha256,
        "blocker_machine_fields": blocker_machine_fields,
        "resolved_blocker_family_ids": resolved_ids,
    }
    observation: dict[str, object] = {
        "schema_version": SEMANTIC_OBSERVATION_SCHEMA,
        "observation_id": observation_id,
        "review_generation_id": review_generation_id,
        "risk_run_id": risk_run_id,
        "target_snapshot": target_snapshot,
        "review_artifact": review_artifact,
        "contract_fingerprint": contract_fingerprint,
        "predecessor_observation_id": predecessor_observation_id,
        "proposal_sha256": proposal_sha256,
        "progress_verdict": proposal["progress_verdict"],
        "progress_evidence_refs": proposal["progress_evidence_refs"],
        "blockers": machine_blockers,
        "resolved_blocker_family_ids": resolved_ids,
    }
    return fields, observation


def _semantic_observation_root_shape_valid(observation: object) -> bool:
    return isinstance(observation, dict) and set(observation) == set(SEMANTIC_OBSERVATION_FIELDS)


def _semantic_observation_machine_shape_valid(observation: dict[str, Any]) -> bool:
    if observation.get("schema_version") != SEMANTIC_OBSERVATION_SCHEMA:
        return False
    for field, prefix in (("observation_id", "sro_"), ("review_generation_id", "rgo_")):
        value = observation.get(field)
        if not isinstance(value, str) or not value.startswith(prefix) or SEMANTIC_SHA256_RE.fullmatch(value[len(prefix) :]) is None:
            return False
    if not isinstance(observation.get("risk_run_id"), str) or not observation["risk_run_id"].strip():
        return False
    if not isinstance(observation.get("target_snapshot"), str) or not observation["target_snapshot"].strip():
        return False
    review_artifact = observation.get("review_artifact")
    normalized_path, problem = normalize_state_transition_protected_path(review_artifact)
    if problem or normalized_path != review_artifact:
        return False
    predecessor_id = observation.get("predecessor_observation_id")
    if predecessor_id is not None and (
        not isinstance(predecessor_id, str)
        or not predecessor_id.startswith("sro_")
        or SEMANTIC_SHA256_RE.fullmatch(predecessor_id[4:]) is None
    ):
        return False
    proposal_sha = observation.get("proposal_sha256")
    if not isinstance(proposal_sha, str) or SEMANTIC_SHA256_RE.fullmatch(proposal_sha) is None:
        return False
    if not _semantic_fingerprint_shape_valid(observation.get("contract_fingerprint")):
        return False
    resolved = observation.get("resolved_blocker_family_ids")
    if not isinstance(resolved, list) or resolved != sorted(set(resolved)):
        return False
    if any(not isinstance(value, str) or not value.startswith("bf_") or SEMANTIC_SHA256_RE.fullmatch(value[3:]) is None for value in resolved):
        return False
    blockers = observation.get("blockers")
    if not isinstance(blockers, list):
        return False
    for blocker in blockers:
        if not isinstance(blocker, dict) or set(blocker) != set(SEMANTIC_BLOCKER_OBSERVATION_FIELDS):
            return False
        family_id = blocker.get("blocker_family_id")
        if not isinstance(family_id, str) or not family_id.startswith("bf_") or SEMANTIC_SHA256_RE.fullmatch(family_id[3:]) is None:
            return False
    return True


def _semantic_validate_observation_against_expected(
    observation: object,
    *,
    expected: dict[str, object],
    plan_path_value: str,
    line_no: int,
    current: bool,
) -> list[SemanticObservationDiagnostic]:
    diagnostics: list[SemanticObservationDiagnostic] = []
    if not _semantic_observation_root_shape_valid(observation):
        _semantic_diagnostic(
            diagnostics,
            stage="observation_schema",
            code="semantic_observation_root_schema_invalid",
            path=plan_path_value,
            line=line_no,
            message="Semantic final observation must contain exactly the V1 root fields.",
        )
        return diagnostics
    assert isinstance(observation, dict)
    if not _semantic_observation_machine_shape_valid(observation):
        _semantic_diagnostic(
            diagnostics,
            stage="observation_schema",
            code="semantic_observation_machine_schema_invalid",
            path=plan_path_value,
            line=line_no,
            message="Semantic final observation has malformed machine-owned field shape.",
        )
        return diagnostics

    machine_fields = (
        "schema_version",
        "observation_id",
        "review_generation_id",
        "risk_run_id",
        "target_snapshot",
        "review_artifact",
        "contract_fingerprint",
        "predecessor_observation_id",
        "proposal_sha256",
        "blockers",
        "resolved_blocker_family_ids",
    )
    mismatched_machine = [field for field in machine_fields if observation.get(field) != expected.get(field)]
    if mismatched_machine:
        _semantic_diagnostic(
            diagnostics,
            stage="current_head" if current else "observation_schema",
            code="semantic_observation_machine_fields_mismatch",
            path=plan_path_value,
            line=line_no,
            message=(
                "Semantic final observation machine-owned fields do not equal deterministic materialization: "
                + ", ".join(mismatched_machine)
                + "."
            ),
        )
    role_fields = ("progress_verdict", "progress_evidence_refs")
    mismatched_role = [field for field in role_fields if observation.get(field) != expected.get(field)]
    if mismatched_role:
        _semantic_diagnostic(
            diagnostics,
            stage="role",
            code="semantic_observation_role_fields_mismatch",
            path=plan_path_value,
            line=line_no,
            message="Semantic final observation role fields must exactly copy the paired role proposal.",
        )
    return diagnostics


def _semantic_source_from_carrier(carrier: SemanticJsonCarrier) -> tuple[str | None, str | None]:
    if carrier.payload is None:
        return None, None
    run_id = carrier.payload.get("run_id")
    normalized_run_id = run_id.strip() if isinstance(run_id, str) and run_id.strip() else None
    return normalized_run_id, _extract_target_snapshot_from_payload(carrier.payload)


def _semantic_next_carrier_index(carriers: Sequence[SemanticJsonCarrier], index: int) -> int | None:
    for next_index in range(index + 1, len(carriers)):
        if carriers[next_index].kind is not None:
            return next_index
    return None


def _semantic_historical_materialization_inputs(
    observation: object,
) -> tuple[str | None, dict[str, object] | None]:
    if not isinstance(observation, dict):
        return None, None
    review_artifact = observation.get("review_artifact")
    fingerprint = observation.get("contract_fingerprint")
    if not isinstance(review_artifact, str) or not _semantic_fingerprint_shape_valid(fingerprint):
        return None, None
    return review_artifact, fingerprint


def _semantic_candidate_from_materialization(fields: dict[str, object]) -> dict[str, object | None]:
    return {field: fields.get(field) for field in SEMANTIC_CANDIDATE_FIELDS}


def _semantic_machine_fields_from_observation(observation: dict[str, Any]) -> dict[str, object]:
    """Project a validated accepted node into the report's machine-field shape."""

    blocker_machine_fields = [
        {
            "blocker_ref": blocker["blocker_ref"],
            "blocker_family_id": blocker["blocker_family_id"],
        }
        for blocker in observation.get("blockers", [])
        if isinstance(blocker, dict)
        and isinstance(blocker.get("blocker_ref"), str)
        and isinstance(blocker.get("blocker_family_id"), str)
    ]
    blocker_machine_fields.sort(key=lambda item: _semantic_blocker_ref_sort_key(item["blocker_ref"]))
    return {
        "risk_run_id": observation.get("risk_run_id"),
        "target_snapshot": observation.get("target_snapshot"),
        "review_artifact": observation.get("review_artifact"),
        "review_generation_id": observation.get("review_generation_id"),
        "observation_id": observation.get("observation_id"),
        "contract_fingerprint": observation.get("contract_fingerprint"),
        "predecessor_observation_id": observation.get("predecessor_observation_id"),
        "proposal_sha256": observation.get("proposal_sha256"),
        "blocker_machine_fields": blocker_machine_fields,
        "resolved_blocker_family_ids": observation.get("resolved_blocker_family_ids"),
    }


def _semantic_report(
    *,
    state: str,
    reason_code: str,
    candidate_machine_fields: dict[str, object | None],
    materialization: dict[str, object] | None,
    validated_chain: Sequence[str],
    diagnostics: Iterable[SemanticObservationDiagnostic],
) -> dict[str, object]:
    return {
        "schema_version": SEMANTIC_OBSERVATION_REPORT_SCHEMA,
        "state": state,
        "reason_code": reason_code,
        "candidate_machine_fields": candidate_machine_fields,
        "materialization": materialization,
        "validated_chain": list(validated_chain),
        "errors": [diagnostic.report_value() for diagnostic in _semantic_sorted_diagnostics(diagnostics)],
    }


def build_semantic_review_observation_report(
    plan_path: str | Path,
    *,
    context: ContractContext | None = None,
) -> dict[str, object]:
    """Read, materialize and validate semantic observation V1 without writing."""

    path = Path(plan_path)
    repo_root = repo_root_for_plan_path(path, context=context)
    path_value = _semantic_path_display(path, repo_root)
    try:
        lines = read_text(path)
    except OSError as exc:
        diagnostic = SemanticObservationDiagnostic(
            stage="activation",
            code="semantic_plan_unreadable",
            path=path_value,
            line=1,
            message=f"Cannot read PLAN_PATH: {exc}.",
        )
        return _semantic_report(
            state="blocked",
            reason_code="activation_invalid",
            candidate_machine_fields=_semantic_empty_candidate_machine_fields(),
            materialization=None,
            validated_chain=(),
            diagnostics=(diagnostic,),
        )

    active, diagnostics = _semantic_activation(path, lines, repo_root=repo_root)
    if not active:
        return _semantic_report(
            state="not_available",
            reason_code="feature_not_activated",
            candidate_machine_fields=_semantic_empty_candidate_machine_fields(),
            materialization=None,
            validated_chain=(),
            diagnostics=(),
        )

    carriers, carrier_diagnostics = _semantic_evidence_carriers(path, lines, repo_root=repo_root)
    diagnostics.extend(carrier_diagnostics)
    evidence_semantic_lines = {
        carrier.line_no
        for carrier in carriers
        if carrier.kind in {"proposal", "observation", "semantic_unknown", "semantic_malformed"}
    }
    # The role-to-helper transport is plan-resident *Evidence*, not an
    # arbitrary JSON fence elsewhere in PLAN_PATH.  Catch an attempted side
    # channel before lifecycle handling can mistake it for a missing proposal.
    plan_text = "\n".join(lines)
    for match in JSON_BLOCK_RE.finditer(plan_text):
        line_no = plan_text.count("\n", 0, match.start()) + 1
        if line_no in evidence_semantic_lines:
            continue
        raw_json = match.group(1)
        try:
            decoded = json.loads(raw_json)
        except json.JSONDecodeError:
            if "semantic_review_observation" not in raw_json:
                continue
        else:
            if not (
                isinstance(decoded, dict)
                and isinstance(decoded.get("schema_version"), str)
                and decoded["schema_version"].startswith("semantic_review_observation")
            ):
                continue
        _semantic_diagnostic(
            diagnostics,
            stage="risk",
            code="semantic_carrier_outside_evidence",
            path=path_value,
            line=line_no,
            message="Semantic proposal/final JSON carriers are valid only inside the sole `## Evidence` section.",
        )
    fingerprint, review_artifact, review_line, fingerprint_diagnostics = _semantic_contract_fingerprint(
        path,
        lines,
        repo_root=repo_root,
    )
    diagnostics.extend(fingerprint_diagnostics)

    selection = select_plan_risk_lane_snapshot(path)
    raw_risk_carriers = [carrier for carrier in carriers if carrier.kind in {"risk", "risk_malformed"}]
    semantic_carriers = [
        carrier
        for carrier in carriers
        if carrier.kind in {"proposal", "observation", "semantic_unknown", "semantic_malformed"}
    ]
    if any(carrier.kind == "risk_malformed" for carrier in carriers):
        first = next(carrier for carrier in carriers if carrier.kind == "risk_malformed")
        _semantic_diagnostic(
            diagnostics,
            stage="risk",
            code="semantic_risk_lane_json_malformed",
            path=path_value,
            line=first.line_no,
            message="A reviewer_code_risk JSON carrier in `## Evidence` is malformed.",
        )
    current_live_blocker_ids: frozenset[int] | None = None
    if selection.error_code:
        _semantic_diagnostic(
            diagnostics,
            stage="risk",
            code=selection.error_code,
            path=path_value,
            line=selection.line_no,
            message=selection.message or "Risk-lane selection is ambiguous or invalid.",
        )
    elif selection.snapshot is None:
        if raw_risk_carriers or semantic_carriers:
            first = (raw_risk_carriers or semantic_carriers)[0]
            _semantic_diagnostic(
                diagnostics,
                stage="risk",
                code="semantic_risk_lane_unbound_carrier",
                path=path_value,
                line=first.line_no,
                message="Raw risk/proposal/final carriers exist without one selectable plan-resident risk generation.",
            )
    else:
        selected_carriers = [
            carrier for carrier in raw_risk_carriers if carrier.kind == "risk" and carrier.line_no == selection.line_no
        ]
        if len(selected_carriers) != 1:
            _semantic_diagnostic(
                diagnostics,
                stage="risk",
                code="semantic_selected_risk_not_in_evidence",
                path=path_value,
                line=selection.line_no,
                message="The selected reviewer_code_risk receipt must be one parseable JSON carrier in `## Evidence`.",
            )
        if selection.run_id is None:
            _semantic_diagnostic(
                diagnostics,
                stage="risk",
                code="semantic_selected_risk_run_id_missing",
                path=path_value,
                line=selection.line_no,
                message="The selected reviewer_code_risk receipt must provide a non-empty run_id.",
            )
        lane_status = selection.payload.get("lane_status") if isinstance(selection.payload, dict) else None
        lane_status_normalized = _normalize_text(lane_status.replace("`", "")) if isinstance(lane_status, str) else ""
        if lane_status_normalized not in SEMANTIC_SUCCESSFUL_RISK_LANE_STATUSES:
            _semantic_diagnostic(
                diagnostics,
                stage="risk",
                code="semantic_selected_risk_lane_not_successful",
                path=path_value,
                line=selection.line_no,
                message="The selected reviewer_code_risk receipt must declare lane_status=complete or no_findings.",
            )
        live_review_diagnostics, current_live_blocker_ids = _semantic_validate_live_review_artifact(
            repo_root=repo_root,
            plan_path=path,
            review_artifact=review_artifact,
            review_line=review_line,
            target_snapshot=selection.snapshot,
        )
        diagnostics.extend(live_review_diagnostics)

    for carrier in carriers:
        if carrier.kind in {"semantic_unknown", "semantic_malformed"}:
            _semantic_diagnostic(
                diagnostics,
                stage="observation_schema",
                code="semantic_carrier_schema_invalid",
                path=path_value,
                line=carrier.line_no,
                message="Semantic Evidence contains an unsupported or malformed observation carrier schema.",
            )

    selected_line = selection.line_no if selection.snapshot is not None and not selection.error_code else None
    selected_run_id = selection.run_id if selected_line is not None else None
    selected_snapshot = selection.snapshot if selected_line is not None else None
    current_precondition_error = any(
        diagnostic.stage in {"activation", "risk", "live_review", "code_draft", "fingerprint"}
        for diagnostic in diagnostics
    )

    accepted: list[dict[str, Any]] = []
    accepted_ids: set[str] = set()
    accepted_generation_ids: set[str] = set()
    paired_final_indexes: set[int] = set()
    selected_proposal_count = 0
    selected_valid_materialization: tuple[dict[str, object], dict[str, object]] | None = None
    selected_accepted = False
    last_risk_index: int | None = None

    for index, carrier in enumerate(carriers):
        if carrier.kind == "risk":
            last_risk_index = index
            continue
        if carrier.kind == "risk_malformed":
            last_risk_index = None
            continue
        if carrier.kind != "proposal":
            continue

        source = carriers[last_risk_index] if last_risk_index is not None else None
        source_run_id, source_snapshot = _semantic_source_from_carrier(source) if source is not None else (None, None)
        source_is_selected = source is not None and selected_line is not None and source.line_no == selected_line
        next_index = _semantic_next_carrier_index(carriers, index)
        next_carrier = carriers[next_index] if next_index is not None else None
        paired_final = next_carrier if next_carrier is not None and next_carrier.kind == "observation" else None
        if paired_final is not None and next_index is not None:
            paired_final_indexes.add(next_index)

        if source is None or source_run_id is None or source_snapshot is None:
            _semantic_diagnostic(
                diagnostics,
                stage="risk",
                code="semantic_proposal_source_risk_invalid",
                path=path_value,
                line=carrier.line_no,
                message="Semantic proposal must follow a parseable reviewer_code_risk receipt with run_id and target_snapshot.",
            )
            continue

        # A proposal before a later selected risk receipt is normally just
        # historical/non-current.  The exception is a proposal appended *after*
        # an accepted observation for that exact source generation: accepted
        # P/F evidence is immutable and cannot be reopened by a later retry.
        if paired_final is None and any(
            item.get("risk_run_id") == source_run_id and item.get("target_snapshot") == source_snapshot
            for item in accepted
        ):
            _semantic_diagnostic(
                diagnostics,
                stage="proposal",
                code="semantic_accepted_generation_duplicate_proposal",
                path=path_value,
                line=carrier.line_no,
                message="An accepted semantic generation cannot receive a later unconsumed replacement proposal.",
            )
            continue

        if source_is_selected:
            selected_proposal_count += 1
            if selected_proposal_count > 1:
                _semantic_diagnostic(
                    diagnostics,
                    stage="proposal",
                    code="semantic_selected_generation_duplicate_proposal",
                    path=path_value,
                    line=carrier.line_no,
                    message="The selected risk generation may have at most one semantic role proposal.",
                )

        current = source_is_selected
        expected_review_artifact: str | None = None
        expected_fingerprint: dict[str, object] | None = None
        observation_payload = paired_final.payload if paired_final is not None else None
        if current:
            expected_review_artifact = review_artifact
            expected_fingerprint = fingerprint
        elif paired_final is not None:
            expected_review_artifact, expected_fingerprint = _semantic_historical_materialization_inputs(observation_payload)
            if expected_review_artifact is None or expected_fingerprint is None:
                _semantic_diagnostic(
                    diagnostics,
                    stage="observation_schema",
                    code="semantic_historical_observation_machine_fields_invalid",
                    path=path_value,
                    line=paired_final.line_no,
                    message="Historical semantic observation must preserve valid review_artifact and contract_fingerprint machine fields.",
                )

        # A pre-selected unconsumed proposal is historical/non-current.  It does
        # not create a writer duty for the newly selected risk generation.
        if expected_review_artifact is None or expected_fingerprint is None:
            if current and paired_final is not None:
                _semantic_diagnostic(
                    diagnostics,
                    stage="observation_schema",
                    code="semantic_current_observation_inputs_unavailable",
                    path=path_value,
                    line=paired_final.line_no,
                    message="Current final observation cannot be validated without current fingerprint and live review inputs.",
                )
            continue

        normalized_review_artifact, review_problem = normalize_state_transition_protected_path(expected_review_artifact)
        if review_problem or normalized_review_artifact != expected_review_artifact:
            _semantic_diagnostic(
                diagnostics,
                stage="observation_schema",
                code="semantic_observation_review_artifact_invalid",
                path=path_value,
                line=paired_final.line_no if paired_final is not None else carrier.line_no,
                message="Semantic observation review_artifact must be a normalized repo-relative POSIX path.",
            )
            continue

        validated_proposal, proposal_diagnostics = _semantic_validate_proposal(
            carrier.payload,
            review_artifact=expected_review_artifact,
            predecessor=accepted[-1] if accepted else None,
            contract_fingerprint=expected_fingerprint,
            target_snapshot=source_snapshot,
            plan_path_value=path_value,
            line_no=carrier.line_no,
        )
        diagnostics.extend(proposal_diagnostics)
        if validated_proposal is None:
            continue
        if current and current_live_blocker_ids is not None:
            missing_live_blockers = _semantic_missing_live_blocker_refs(
                validated_proposal["blockers"],
                review_artifact=expected_review_artifact,
                live_blocker_ids=current_live_blocker_ids,
            )
            if missing_live_blockers:
                _semantic_diagnostic(
                    diagnostics,
                    stage="live_review",
                    code="semantic_live_review_blocker_ref_missing",
                    path=expected_review_artifact,
                    line=carrier.line_no,
                    message="Current semantic proposal references blocker id(s) absent from the live review artifact: "
                    + ", ".join(missing_live_blockers)
                    + ".",
                )
                continue
            proposal_refs = _semantic_blocker_refs(
                validated_proposal["blockers"],
                review_artifact=expected_review_artifact,
            )
            expected_live_refs = _semantic_expected_live_blocker_refs(
                current_live_blocker_ids,
                review_artifact=expected_review_artifact,
            )
            if proposal_refs != expected_live_refs:
                _semantic_diagnostic(
                    diagnostics,
                    stage="live_review",
                    code="semantic_live_review_blocker_ref_set_mismatch",
                    path=expected_review_artifact,
                    line=carrier.line_no,
                    message=(
                        "Current semantic proposal blocker refs must exactly match the canonical open "
                        "blocker set in the live review artifact."
                    ),
                )
                continue
        fields, expected_observation = _semantic_materialize_observation(
            validated_proposal,
            risk_run_id=source_run_id,
            target_snapshot=source_snapshot,
            review_artifact=expected_review_artifact,
            contract_fingerprint=expected_fingerprint,
            predecessor=accepted[-1] if accepted else None,
        )
        if current and not current_precondition_error:
            selected_valid_materialization = (fields, expected_observation)

        if paired_final is None:
            if current and next_carrier is not None and next_carrier.kind in {
                "risk",
                "risk_malformed",
                "proposal",
                "semantic_unknown",
                "semantic_malformed",
            }:
                _semantic_diagnostic(
                    diagnostics,
                    stage="risk",
                    code="semantic_proposal_positional_pairing_invalid",
                    path=path_value,
                    line=carrier.line_no,
                    message="A semantic proposal is consumed only by the immediately next semantic final carrier.",
                )
            continue

        observation_diagnostics = _semantic_validate_observation_against_expected(
            observation_payload,
            expected=expected_observation,
            plan_path_value=path_value,
            line_no=paired_final.line_no,
            current=current,
        )
        diagnostics.extend(observation_diagnostics)
        if observation_diagnostics or not isinstance(observation_payload, dict):
            continue

        observation_id = observation_payload["observation_id"]
        generation_id = observation_payload["review_generation_id"]
        if observation_id in accepted_ids or generation_id in accepted_generation_ids:
            _semantic_diagnostic(
                diagnostics,
                stage="chain",
                code="semantic_observation_identity_duplicate",
                path=path_value,
                line=paired_final.line_no,
                message="Semantic observation_id and review_generation_id must be unique in the accepted chain.",
            )
            continue
        accepted.append(observation_payload)
        accepted_ids.add(observation_id)
        accepted_generation_ids.add(generation_id)
        if current:
            selected_accepted = True

    for index, carrier in enumerate(carriers):
        if carrier.kind != "observation" or index in paired_final_indexes:
            continue
        _semantic_diagnostic(
            diagnostics,
            stage="risk",
            code="semantic_observation_unbound",
            path=path_value,
            line=carrier.line_no,
            message="Semantic final observation is not positionally paired with a source risk receipt and role proposal.",
        )

    if selected_run_id and selected_snapshot and review_artifact:
        selected_generation = _semantic_generation_id(
            risk_run_id=selected_run_id,
            review_artifact=review_artifact,
            target_snapshot=selected_snapshot,
        )
        selected_existing = [
            item for item in accepted if item.get("review_generation_id") == selected_generation
        ]
        if len(selected_existing) > 1:
            _semantic_diagnostic(
                diagnostics,
                stage="chain",
                code="semantic_selected_generation_identity_duplicate",
                path=path_value,
                line=selection.line_no,
                message="The selected deterministic review_generation_id appears more than once in accepted history.",
            )
        elif selected_existing:
            selected_node = selected_existing[0]
            if not accepted or accepted[-1] is not selected_node:
                _semantic_diagnostic(
                    diagnostics,
                    stage="chain",
                    code="semantic_current_generation_not_head",
                    path=path_value,
                    line=selection.line_no,
                    message="The selected risk generation must materialize the unique current observation head.",
                )
            elif (
                selected_node.get("risk_run_id") != selected_run_id
                or selected_node.get("target_snapshot") != selected_snapshot
                or selected_node.get("review_artifact") != review_artifact
                or selected_node.get("contract_fingerprint") != fingerprint
            ):
                _semantic_diagnostic(
                    diagnostics,
                    stage="current_head",
                    code="semantic_existing_generation_freshness_mismatch",
                    path=path_value,
                    line=selection.line_no,
                message="The existing selected generation no longer matches current risk, target, review or fingerprint bytes.",
            )
            elif current_live_blocker_ids is not None:
                missing_live_blockers = _semantic_missing_live_blocker_refs(
                    selected_node.get("blockers"),
                    review_artifact=review_artifact,
                    live_blocker_ids=current_live_blocker_ids,
                )
                selected_refs = _semantic_blocker_refs(
                    selected_node.get("blockers"),
                    review_artifact=review_artifact,
                )
                expected_live_refs = _semantic_expected_live_blocker_refs(
                    current_live_blocker_ids,
                    review_artifact=review_artifact,
                )
                if missing_live_blockers:
                    _semantic_diagnostic(
                        diagnostics,
                        stage="live_review",
                        code="semantic_live_review_blocker_ref_missing",
                        path=review_artifact,
                        line=selection.line_no,
                        message="Current semantic observation references blocker id(s) absent from the live review artifact: "
                        + ", ".join(missing_live_blockers)
                        + ".",
                    )
                elif selected_refs != expected_live_refs:
                    _semantic_diagnostic(
                        diagnostics,
                        stage="live_review",
                        code="semantic_live_review_blocker_ref_set_mismatch",
                        path=review_artifact,
                        line=selection.line_no,
                        message=(
                            "Current semantic observation blocker refs must exactly match the canonical open "
                            "blocker set in the live review artifact."
                        ),
                    )
                else:
                    # A retry can select a physically newer receipt for the same
                    # deterministic generation.  It is an idempotent readback,
                    # never a request for another proposal/final pair.
                    selected_accepted = True
                    if selected_valid_materialization is None:
                        selected_valid_materialization = (
                            _semantic_machine_fields_from_observation(selected_node),
                            selected_node,
                        )
            else:
                # A retry can select a physically newer receipt for the same
                # deterministic generation.  It is an idempotent readback,
                # never a request for another proposal/final pair.
                selected_accepted = True
                if selected_valid_materialization is None:
                    selected_valid_materialization = (
                        _semantic_machine_fields_from_observation(selected_node),
                        selected_node,
                    )

    validated_chain = [str(item["observation_id"]) for item in accepted]
    sorted_diagnostics = _semantic_sorted_diagnostics(diagnostics)
    if sorted_diagnostics:
        candidate = _semantic_empty_candidate_machine_fields()
        if selected_valid_materialization is not None:
            candidate = _semantic_candidate_from_materialization(selected_valid_materialization[0])
        elif selected_run_id and selected_snapshot and review_artifact and fingerprint:
            predecessor_id = accepted[-1].get("observation_id") if accepted else None
            generation = _semantic_generation_id(
                risk_run_id=selected_run_id,
                review_artifact=review_artifact,
                target_snapshot=selected_snapshot,
            )
            candidate.update(
                {
                    "risk_run_id": selected_run_id,
                    "target_snapshot": selected_snapshot,
                    "review_artifact": review_artifact,
                    "review_generation_id": generation,
                    "observation_id": _semantic_observation_id(generation),
                    "contract_fingerprint": fingerprint,
                    "predecessor_observation_id": predecessor_id,
                }
            )
        return _semantic_report(
            state="blocked",
            reason_code=SEMANTIC_STAGE_REASON_CODES[sorted_diagnostics[0].stage],
            candidate_machine_fields=candidate,
            materialization=None,
            validated_chain=validated_chain,
            diagnostics=sorted_diagnostics,
        )

    if not raw_risk_carriers and not semantic_carriers:
        return _semantic_report(
            state="not_available",
            reason_code="risk_generation_not_available",
            candidate_machine_fields=_semantic_empty_candidate_machine_fields(),
            materialization=None,
            validated_chain=validated_chain,
            diagnostics=(),
        )

    if selected_valid_materialization is None:
        candidate = _semantic_empty_candidate_machine_fields()
        if selected_run_id and selected_snapshot and review_artifact and fingerprint:
            generation = _semantic_generation_id(
                risk_run_id=selected_run_id,
                review_artifact=review_artifact,
                target_snapshot=selected_snapshot,
            )
            candidate.update(
                {
                    "risk_run_id": selected_run_id,
                    "target_snapshot": selected_snapshot,
                    "review_artifact": review_artifact,
                    "review_generation_id": generation,
                    "observation_id": _semantic_observation_id(generation),
                    "contract_fingerprint": fingerprint,
                    "predecessor_observation_id": accepted[-1].get("observation_id") if accepted else None,
                }
            )
        return _semantic_report(
            state="ready_to_materialize",
            reason_code="role_proposal_required",
            candidate_machine_fields=candidate,
            materialization=None,
            validated_chain=validated_chain,
            diagnostics=(),
        )

    candidate_fields, expected_observation = selected_valid_materialization
    candidate = _semantic_candidate_from_materialization(candidate_fields)
    if selected_accepted:
        return _semantic_report(
            state="valid",
            reason_code="current_observation_valid",
            candidate_machine_fields=candidate,
            materialization=None,
            validated_chain=validated_chain,
            diagnostics=(),
        )
    return _semantic_report(
        state="ready_to_materialize",
        reason_code="observation_not_materialized",
        candidate_machine_fields=candidate,
        materialization={
            "proposal_sha256": candidate_fields["proposal_sha256"],
            "observation": expected_observation,
        },
        validated_chain=validated_chain,
        diagnostics=(),
    )


semantic_review_observation_report = build_semantic_review_observation_report
build_semantic_observation_report = build_semantic_review_observation_report


# Semantic cycle checkpoint V1 ---------------------------------------------------
#
# The checkpoint is deliberately a consumer of the accepted producer sequence
# above.  It never reconstructs family identity from review prose and it never
# writes a counter or a side ledger: Evidence is the sole resolution host.

def _semantic_checkpoint_diagnostic(
    diagnostics: list[SemanticCheckpointDiagnostic],
    *,
    code: str,
    path: str | None,
    line: int | None,
    message: str,
) -> None:
    diagnostics.append(SemanticCheckpointDiagnostic(code=code, path=path, line=line, message=message))


def _semantic_checkpoint_sorted_diagnostics(
    diagnostics: Iterable[SemanticCheckpointDiagnostic],
) -> list[SemanticCheckpointDiagnostic]:
    unique: dict[tuple[str, str | None, int | None, str], SemanticCheckpointDiagnostic] = {}
    for diagnostic in diagnostics:
        unique[(diagnostic.code, diagnostic.path, diagnostic.line, diagnostic.message)] = diagnostic
    return sorted(
        unique.values(),
        key=lambda item: (item.code, item.path or "", -1 if item.line is None else item.line, item.message),
    )


def _semantic_checkpoint_report(
    *,
    state: str,
    reason_code: str,
    producer: dict[str, object] | None,
    trigger: dict[str, object] | None,
    resolution: dict[str, object] | None,
    diagnostics: Iterable[SemanticCheckpointDiagnostic],
) -> dict[str, object]:
    return {
        "schema_version": SEMANTIC_CHECKPOINT_REPORT_SCHEMA,
        "state": state,
        "reason_code": reason_code,
        "producer": producer,
        "trigger": trigger,
        "resolution": resolution,
        "errors": [item.report_value() for item in _semantic_checkpoint_sorted_diagnostics(diagnostics)],
    }


def _semantic_checkpoint_status_norm(value: str | None) -> str:
    return " ".join((value or "").split()).casefold()


def _semantic_checkpoint_marker_activation(
    plan_path: Path,
    lines: Sequence[str],
    *,
    repo_root: Path,
) -> tuple[bool, list[SemanticCheckpointDiagnostic]]:
    """Parse the literal checkpoint opt-in without activating template prose."""

    diagnostics: list[SemanticCheckpointDiagnostic] = []
    path_value = _semantic_path_display(plan_path, repo_root)
    masked = _semantic_masked_markdown_lines(lines)
    receipt_sections = [
        (start, end)
        for start, title, end in _semantic_h2_sections(lines, masked)
        if SEMANTIC_RECEIPT_HEADING_RE.match(title)
    ]
    literal_lines: list[int] = []
    malformed_lines: list[int] = []
    for index, line in enumerate(lines):
        if masked[index]:
            continue
        match = SEMANTIC_H3_HEADING_RE.match(line)
        if match is None:
            continue
        title = match.group("title")
        if title == "Semantic cycle checkpoint":
            literal_lines.append(index)
        elif title.casefold() == "semantic cycle checkpoint":
            malformed_lines.append(index)

    if not literal_lines and not malformed_lines:
        return False, diagnostics

    if len(receipt_sections) != 1:
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_marker_receipt_location_invalid",
            path=path_value,
            line=(literal_lines or malformed_lines or [0])[0] + 1,
            message="Semantic cycle checkpoint marker requires exactly one `## Reviewability preflight receipt` section.",
        )
        return True, diagnostics

    receipt_start, receipt_end = receipt_sections[0]
    matching = [line for line in literal_lines if receipt_start < line < receipt_end]
    malformed_in_receipt = [line for line in malformed_lines if receipt_start < line < receipt_end]
    if malformed_in_receipt:
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_marker_heading_nonliteral",
            path=path_value,
            line=malformed_in_receipt[0] + 1,
            message="Semantic cycle checkpoint heading must be literal `### Semantic cycle checkpoint`.",
        )
    if len(matching) != 1 or len(literal_lines) != len(matching):
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_marker_location_or_count_invalid",
            path=path_value,
            line=(matching or literal_lines or [receipt_start])[0] + 1,
            message="Semantic cycle checkpoint marker must appear exactly once inside `## Reviewability preflight receipt`.",
        )
        return True, diagnostics

    marker_index = matching[0]
    end_index = next(
        (
            index
            for index in range(marker_index + 1, receipt_end)
            if not masked[index] and SEMANTIC_H3_HEADING_RE.match(lines[index])
        ),
        receipt_end,
    )
    body = [line.rstrip(" \t") for line in lines[marker_index + 1 : end_index] if line.strip()]
    if tuple(body) != SEMANTIC_CHECKPOINT_MARKER_ROWS:
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_marker_rows_invalid",
            path=path_value,
            line=marker_index + 1,
            message="Semantic cycle checkpoint marker must contain exactly the canonical schema/mode/writer rows.",
        )
    return True, diagnostics


def _semantic_checkpoint_json_load(raw: str) -> dict[str, Any] | None:
    """Decode one object while making duplicate JSON keys fail closed."""

    def no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        decoded: dict[str, Any] = {}
        for key, value in pairs:
            if key in decoded:
                raise ValueError(f"duplicate JSON key {key!r}")
            decoded[key] = value
        return decoded

    decoded = json.loads(raw, object_pairs_hook=no_duplicate_keys)
    return decoded if isinstance(decoded, dict) else None


def _semantic_checkpoint_resolution_carriers(
    plan_path: Path,
    lines: Sequence[str],
    *,
    repo_root: Path,
) -> tuple[list[SemanticCheckpointJsonCarrier], list[SemanticCheckpointDiagnostic]]:
    """Read only checkpoint resolution carriers from the sole Evidence section."""

    diagnostics: list[SemanticCheckpointDiagnostic] = []
    path_value = _semantic_path_display(plan_path, repo_root)
    masked = _semantic_masked_markdown_lines(lines)
    evidence_sections = [
        (start, end)
        for start, title, end in _semantic_h2_sections(lines, masked)
        if SEMANTIC_EVIDENCE_HEADING_RE.match(title)
    ]
    if len(evidence_sections) != 1:
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_evidence_section_invalid",
            path=path_value,
            line=evidence_sections[1][0] + 1 if len(evidence_sections) > 1 else 1,
            message="Semantic cycle checkpoint requires exactly one `## Evidence` section.",
        )
        return [], diagnostics

    start, end = evidence_sections[0]
    carriers: list[SemanticCheckpointJsonCarrier] = []
    in_json = False
    json_start = 0
    buffer: list[str] = []
    for index in range(start + 1, end):
        line = lines[index]
        if not in_json:
            if JSON_FENCE_START_RE.match(line):
                in_json = True
                json_start = index
                buffer = []
            continue
        if FENCE_END_RE.match(line):
            raw = "\n".join(buffer).strip()
            payload: dict[str, Any] | None = None
            kind = "other"
            try:
                payload = _semantic_checkpoint_json_load(raw)
            except (json.JSONDecodeError, ValueError):
                if "semantic_cycle_checkpoint" in raw:
                    kind = "malformed"
            else:
                schema_version = payload.get("schema_version") if payload is not None else None
                if schema_version == SEMANTIC_CHECKPOINT_RESOLUTION_SCHEMA:
                    kind = "resolution_v1"
                elif schema_version == SEMANTIC_CHECKPOINT_RESOLUTION_V2_SCHEMA:
                    kind = "resolution_v2"
                elif isinstance(schema_version, str) and schema_version.startswith("semantic_cycle_checkpoint"):
                    kind = "unknown"
            if kind != "other":
                carriers.append(
                    SemanticCheckpointJsonCarrier(
                        line_no=json_start + 1,
                        end_line_no=index + 1,
                        payload=payload,
                        raw=raw,
                        kind=kind,
                    )
                )
            in_json = False
            json_start = 0
            buffer = []
            continue
        buffer.append(line)

    if in_json and "semantic_cycle_checkpoint" in "\n".join(buffer):
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_json_fence_unclosed",
            path=path_value,
            line=json_start + 1,
            message="Semantic cycle checkpoint JSON carrier fence is not closed inside `## Evidence`.",
        )

    plan_text = "\n".join(lines)
    for match in JSON_BLOCK_RE.finditer(plan_text):
        line_no = plan_text.count("\n", 0, match.start()) + 1
        if start + 1 < line_no <= end:
            continue
        raw = match.group(1)
        try:
            decoded = _semantic_checkpoint_json_load(raw)
        except (json.JSONDecodeError, ValueError):
            is_checkpoint = bool(
                re.search(
                    r'"schema_version"\s*:\s*"semantic_cycle_checkpoint[^"\\]*"',
                    raw,
                )
            )
        else:
            is_checkpoint = bool(
                isinstance(decoded, dict)
                and isinstance(decoded.get("schema_version"), str)
                and decoded["schema_version"].startswith("semantic_cycle_checkpoint")
            )
        if not is_checkpoint:
            continue
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_carrier_outside_evidence",
            path=path_value,
            line=line_no,
            message="Semantic cycle checkpoint resolution JSON is valid only inside the sole `## Evidence` section.",
        )
    return carriers, diagnostics


def _semantic_checkpoint_accepted_observations(
    plan_path: Path,
    lines: Sequence[str],
    producer_report: Mapping[str, object],
    *,
    repo_root: Path,
) -> tuple[list[dict[str, Any]] | None, list[SemanticCheckpointDiagnostic]]:
    """Project producer's immutable accepted IDs back to their exact Evidence nodes."""

    diagnostics: list[SemanticCheckpointDiagnostic] = []
    path_value = _semantic_path_display(plan_path, repo_root)
    accepted_ids = producer_report.get("validated_chain")
    if not isinstance(accepted_ids, list) or any(not isinstance(item, str) or not item for item in accepted_ids):
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_accepted_chain_invalid",
            path=path_value,
            line=1,
            message="Producer valid report must expose a non-empty string-only accepted observation chain.",
        )
        return None, diagnostics

    carriers, producer_diagnostics = _semantic_evidence_carriers(plan_path, lines, repo_root=repo_root)
    for item in producer_diagnostics:
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_observation_evidence_invalid",
            path=item.path,
            line=item.line,
            message=item.message,
        )
    observations_by_id: dict[str, list[dict[str, Any]]] = {}
    for carrier in carriers:
        if carrier.kind != "observation" or not isinstance(carrier.payload, dict):
            continue
        observation_id = carrier.payload.get("observation_id")
        if isinstance(observation_id, str):
            observations_by_id.setdefault(observation_id, []).append(carrier.payload)

    observations: list[dict[str, Any]] = []
    for observation_id in accepted_ids:
        candidates = observations_by_id.get(observation_id, [])
        if len(candidates) != 1:
            _semantic_checkpoint_diagnostic(
                diagnostics,
                code="checkpoint_accepted_observation_carrier_invalid",
                path=path_value,
                line=1,
                message=(
                    "Every producer accepted observation_id must map to exactly one Evidence final carrier; "
                    f"`{observation_id}` mapped to {len(candidates)} carrier(s)."
                ),
            )
            continue
        observations.append(candidates[0])
    return (None if diagnostics else observations), diagnostics


def _semantic_checkpoint_trigger_for_observation(
    observations: Sequence[dict[str, Any]],
    index: int,
    *,
    plan_path_value: str,
    diagnostics: list[SemanticCheckpointDiagnostic],
    scope_churn_precedes: bool = False,
) -> dict[str, object] | None:
    """Derive the one deterministic checkpoint trigger for one accepted head."""

    current = observations[index]
    observation_id = current.get("observation_id")
    blockers = current.get("blockers")
    fingerprint = current.get("contract_fingerprint")
    if not isinstance(observation_id, str) or not isinstance(blockers, list) or not isinstance(fingerprint, dict):
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_accepted_observation_fields_invalid",
            path=plan_path_value,
            line=1,
            message="Accepted producer observation is missing required machine fields for checkpoint projection.",
        )
        return None
    if not blockers:
        return None

    families: list[str] = []
    family_rows: list[dict[str, str]] = []
    for blocker in blockers:
        if (
            not isinstance(blocker, dict)
            or not isinstance(blocker.get("blocker_family_id"), str)
            or not isinstance(blocker.get("blocker_ref"), str)
        ):
            _semantic_checkpoint_diagnostic(
                diagnostics,
                code="checkpoint_accepted_blocker_fields_invalid",
                path=plan_path_value,
                line=1,
                message="Accepted producer blocker rows must retain machine-owned blocker_family_id values.",
            )
            return None
        family_id = blocker["blocker_family_id"]
        blocker_ref = blocker["blocker_ref"]
        families.append(family_id)
        family_rows.append({"blocker_family_id": family_id, "blocker_ref": blocker_ref})
    required_families = sorted(set(families))
    if len(required_families) != len(families):
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_current_blocker_family_duplicate",
            path=plan_path_value,
            line=1,
            message="One accepted current observation may not contain duplicate blocker_family_id rows.",
        )
        return None

    family_survival = False
    if index:
        predecessor = observations[index - 1]
        predecessor_id = predecessor.get("observation_id")
        predecessor_snapshot = predecessor.get("target_snapshot")
        current_snapshot = current.get("target_snapshot")
        predecessor_blockers = predecessor.get("blockers")
        if (
            current.get("predecessor_observation_id") != predecessor_id
            or not isinstance(predecessor_blockers, list)
            or not isinstance(predecessor_snapshot, str)
            or not isinstance(current_snapshot, str)
        ):
            _semantic_checkpoint_diagnostic(
                diagnostics,
                code="checkpoint_accepted_chain_adjacency_invalid",
                path=plan_path_value,
                line=1,
                message="Checkpoint family survival requires adjacent accepted observation heads with intact machine lineage.",
            )
            return None
        predecessor_refs = {
            (item.get("blocker_ref"), item.get("blocker_family_id"))
            for item in predecessor_blockers
            if isinstance(item, dict)
        }
        family_survival = current_snapshot != predecessor_snapshot and any(
            blocker.get("lineage_relation") == "same_family"
            and (blocker.get("predecessor_blocker_ref"), blocker.get("blocker_family_id")) in predecessor_refs
            for blocker in blockers
            if isinstance(blocker, dict)
        )

    independent_boundary = any(
        isinstance(blocker, dict) and blocker.get("lineage_relation") == "independent_boundary" for blocker in blockers
    )
    scope_churn = current.get("progress_verdict") == "scope_churn"
    if scope_churn and scope_churn_precedes:
        # Resolution V2 consumes the immutable producer verdict directly: a
        # simultaneous surviving family cannot downgrade scope churn into a
        # permit-eligible family_survival trigger.  V1 retains its established
        # family-local precedence for compatibility.
        trigger_kind = "scope_churn"
    elif family_survival:
        trigger_kind = "family_survival"
    elif independent_boundary:
        trigger_kind = "independent_boundary"
    elif scope_churn:
        trigger_kind = "scope_churn"
    else:
        return None
    return {
        "observation_id": observation_id,
        "trigger_kind": trigger_kind,
        "contract_fingerprint": fingerprint,
        "required_blocker_family_ids": required_families,
        "required_family_rows": sorted(family_rows, key=lambda item: item["blocker_family_id"]),
    }


def _semantic_checkpoint_trigger_map(
    observations: Sequence[dict[str, Any]],
    *,
    plan_path_value: str,
    diagnostics: list[SemanticCheckpointDiagnostic],
    scope_churn_precedes: bool = False,
) -> dict[str, dict[str, object]]:
    triggers: dict[str, dict[str, object]] = {}
    for index, observation in enumerate(observations):
        trigger = _semantic_checkpoint_trigger_for_observation(
            observations,
            index,
            plan_path_value=plan_path_value,
            diagnostics=diagnostics,
            scope_churn_precedes=scope_churn_precedes,
        )
        if trigger is not None:
            triggers[str(trigger["observation_id"])] = trigger
    return triggers


def _semantic_checkpoint_resolution_shape_valid(
    carrier: SemanticCheckpointJsonCarrier,
    *,
    plan_path_value: str,
    diagnostics: list[SemanticCheckpointDiagnostic],
) -> bool:
    """Validate fields that are independent of a particular observation head."""

    if carrier.kind == "malformed":
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_resolution_json_malformed",
            path=plan_path_value,
            line=carrier.line_no,
            message="Semantic cycle checkpoint resolution JSON is malformed or repeats a JSON key.",
        )
        return False
    if carrier.kind in {"unknown", "resolution_v2"}:
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_resolution_schema_unknown",
            path=plan_path_value,
            line=carrier.line_no,
            message="Semantic cycle checkpoint carrier must use the exact V1 resolution schema.",
        )
        return False
    payload = carrier.payload
    if carrier.kind != "resolution_v1" or not isinstance(payload, dict):
        return False

    valid = True
    expected_fields = set(SEMANTIC_CHECKPOINT_RESOLUTION_FIELDS)
    allowed_fields = expected_fields | SEMANTIC_CHECKPOINT_OPTIONAL_RESOLUTION_FIELDS
    unknown = sorted(set(payload) - allowed_fields)
    missing = sorted(expected_fields - set(payload))
    if unknown or missing:
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_resolution_fields_invalid",
            path=plan_path_value,
            line=carrier.line_no,
            message=(
                "Checkpoint resolution must use the exact V1 field set"
                + (f"; missing={', '.join(missing)}" if missing else "")
                + (f"; unknown={', '.join(unknown)}" if unknown else "")
                + "."
            ),
        )
        valid = False
    if payload.get("schema_version") != SEMANTIC_CHECKPOINT_RESOLUTION_SCHEMA:
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_resolution_schema_invalid",
            path=plan_path_value,
            line=carrier.line_no,
            message="Checkpoint resolution must use `semantic_cycle_checkpoint_resolution.v1`.",
        )
        valid = False
    if not isinstance(payload.get("trigger_observation_id"), str) or not payload.get("trigger_observation_id", "").strip():
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_resolution_trigger_invalid",
            path=plan_path_value,
            line=carrier.line_no,
            message="Checkpoint resolution trigger_observation_id must be a non-empty string.",
        )
        valid = False
    if payload.get("trigger_kind") not in SEMANTIC_CHECKPOINT_TRIGGER_KINDS:
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_resolution_trigger_kind_invalid",
            path=plan_path_value,
            line=carrier.line_no,
            message="Checkpoint resolution trigger_kind is not a V1 checkpoint trigger.",
        )
        valid = False
    if not isinstance(payload.get("contract_fingerprint"), dict):
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_resolution_fingerprint_invalid",
            path=plan_path_value,
            line=carrier.line_no,
            message="Checkpoint resolution contract_fingerprint must be the producer machine object.",
        )
        valid = False
    if not isinstance(payload.get("allowed_next_status"), str) or not payload.get("allowed_next_status", "").strip():
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_resolution_next_status_invalid",
            path=plan_path_value,
            line=carrier.line_no,
            message="Checkpoint resolution allowed_next_status must be a non-empty string.",
        )
        valid = False

    evidence_refs = payload.get("decision_evidence_refs")
    if (
        not isinstance(evidence_refs, list)
        or not evidence_refs
        or any(not isinstance(item, str) or not item.strip() for item in evidence_refs)
        or len({item.strip() for item in evidence_refs if isinstance(item, str)}) != len(evidence_refs)
    ):
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_resolution_evidence_refs_invalid",
            path=plan_path_value,
            line=carrier.line_no,
            message="Checkpoint resolution decision_evidence_refs must be a non-empty unique string list.",
        )
        valid = False

    family_rows = payload.get("required_family_resolutions")
    if not isinstance(family_rows, list) or not family_rows:
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_resolution_families_invalid",
            path=plan_path_value,
            line=carrier.line_no,
            message="Checkpoint resolution required_family_resolutions must be a non-empty V1 family list.",
        )
        return False
    family_ids: list[str] = []
    decisions: list[str] = []
    for item in family_rows:
        if not isinstance(item, dict) or set(item) != set(SEMANTIC_CHECKPOINT_FAMILY_RESOLUTION_FIELDS):
            _semantic_checkpoint_diagnostic(
                diagnostics,
                code="checkpoint_resolution_family_fields_invalid",
                path=plan_path_value,
                line=carrier.line_no,
                message="Each checkpoint family resolution must contain exactly blocker_family_id and decision.",
            )
            valid = False
            continue
        family_id = item.get("blocker_family_id")
        decision = item.get("decision")
        if not isinstance(family_id, str) or not family_id.strip():
            _semantic_checkpoint_diagnostic(
                diagnostics,
                code="checkpoint_resolution_family_id_invalid",
                path=plan_path_value,
                line=carrier.line_no,
                message="Checkpoint family resolution blocker_family_id must be a non-empty string.",
            )
            valid = False
        else:
            family_ids.append(family_id)
        if decision not in SEMANTIC_CHECKPOINT_DECISIONS:
            _semantic_checkpoint_diagnostic(
                diagnostics,
                code="checkpoint_resolution_decision_invalid",
                path=plan_path_value,
                line=carrier.line_no,
                message="Checkpoint family resolution decision is not a V1 Architect decision.",
            )
            valid = False
        else:
            decisions.append(decision)
    if len(set(family_ids)) != len(family_ids):
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_resolution_family_duplicate",
            path=plan_path_value,
            line=carrier.line_no,
            message="Checkpoint resolution may not duplicate blocker_family_id entries.",
        )
        valid = False
    if family_ids != sorted(family_ids):
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_resolution_family_order_invalid",
            path=plan_path_value,
            line=carrier.line_no,
            message="Checkpoint resolution family entries must be sorted by blocker_family_id.",
        )
        valid = False
    if len(set(decisions)) > 1:
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_resolution_decision_mixed",
            path=plan_path_value,
            line=carrier.line_no,
            message="One checkpoint resolution must use one compatible decision for every required family.",
        )
        valid = False
    decision = decisions[0] if len(decisions) == len(family_rows) and decisions else None
    if decision is not None:
        expected_status = SEMANTIC_CHECKPOINT_DECISION_NEXT_STATUS[decision]
        if payload.get("allowed_next_status") != expected_status:
            _semantic_checkpoint_diagnostic(
                diagnostics,
                code="checkpoint_resolution_decision_status_mismatch",
                path=plan_path_value,
                line=carrier.line_no,
                message=f"Decision {decision} requires allowed_next_status={expected_status!r}.",
            )
            valid = False
        if decision == "successor":
            if not isinstance(payload.get("successor_plan_ref"), str) or not payload.get("successor_plan_ref", "").strip():
                _semantic_checkpoint_diagnostic(
                    diagnostics,
                    code="checkpoint_resolution_successor_missing",
                    path=plan_path_value,
                    line=carrier.line_no,
                    message="Successor resolution requires a materialized successor_plan_ref.",
                )
                valid = False
            if "owner_question_ref" in payload:
                _semantic_checkpoint_diagnostic(
                    diagnostics,
                    code="checkpoint_resolution_owner_question_unexpected",
                    path=plan_path_value,
                    line=carrier.line_no,
                    message="owner_question_ref is valid only for the stop decision.",
                )
                valid = False
        elif "successor_plan_ref" in payload:
            _semantic_checkpoint_diagnostic(
                diagnostics,
                code="checkpoint_resolution_successor_unexpected",
                path=plan_path_value,
                line=carrier.line_no,
                message="successor_plan_ref is valid only for the successor decision.",
            )
            valid = False
        if decision != "stop" and "owner_question_ref" in payload:
            _semantic_checkpoint_diagnostic(
                diagnostics,
                code="checkpoint_resolution_owner_question_unexpected",
                path=plan_path_value,
                line=carrier.line_no,
                message="owner_question_ref is valid only for the stop decision.",
            )
            valid = False
        if decision == "stop" and "owner_question_ref" in payload and (
            not isinstance(payload.get("owner_question_ref"), str) or not payload.get("owner_question_ref", "").strip()
        ):
            _semantic_checkpoint_diagnostic(
                diagnostics,
                code="checkpoint_resolution_owner_question_invalid",
                path=plan_path_value,
                line=carrier.line_no,
                message="stop owner_question_ref must be a non-empty Owner question ID.",
            )
            valid = False
    return valid


def _semantic_checkpoint_v2_context(
    plan_path: Path,
    lines: Sequence[str],
    *,
    repo_root: Path,
    context: ContractContext | None = None,
) -> tuple[str, dict[str, object] | None]:
    """Return the bounded-grammar selector state without creating a second parser.

    The generic machine-authority reader remains the sole admission parser.  This
    overlay consumes its validated readback plus the already-decoded strict Meta
    object only after a plan has explicitly declared ``bounded_grammar``.
    """

    plan_rel = _semantic_path_display(plan_path, repo_root)
    plan_text = "\n".join(lines)
    strict = plan_status_oracle.strict_plan_meta_json(plan_text)
    if strict.state != "valid" or strict.plan_meta is None:
        return "not_subject", None
    decision = strict.plan_meta.get("machine_authority_decision")
    route = decision.get("recommended_route") if isinstance(decision, Mapping) else None
    if not isinstance(route, Mapping) or route.get("kind") != "bounded_grammar":
        return "not_subject", None

    readback = plan_status_oracle.machine_authority_decision_readback(plan_path, plan_text=plan_text)
    if readback.state != "frozen_confirmed" or readback.reason_code != "ok":
        return "admission_unavailable", None
    contour = route.get("grammar_contour")
    if not isinstance(contour, Mapping):
        return "admission_unavailable", None
    contour_id = contour.get("grammar_contour_id")
    axes = contour.get("axes")
    if (
        not isinstance(contour_id, str)
        or SEMANTIC_SHA256_RE.fullmatch(contour_id[3:]) is None
        or not contour_id.startswith("gc_")
        or not isinstance(axes, list)
        or not axes
    ):
        return "admission_unavailable", None
    axis_ids = [item.get("axis_id") for item in axes if isinstance(item, Mapping)]
    if len(axis_ids) != len(axes) or any(not isinstance(item, str) or not item for item in axis_ids):
        return "admission_unavailable", None

    scope = plan_status_oracle.classify_scope_expansion(
        dict(strict.plan_meta),
        planning_contour_vocab=plan_status_oracle._planning_contour_vocab(
            repo_root,
            context=context or _ACTIVE_PLAN_LINT_CONTEXT.get(),
        ),
    )
    return (
        "selected",
        {
            "plan_rel": plan_rel,
            "authority_decision_id": readback.decision_id,
            "authority_carrier_sha256": readback.carrier_sha256,
            "grammar_contour_id": contour_id,
            "grammar_axis_ids": axis_ids,
            "scope_expansion_precedes": (
                scope.carrier_state == "malformed" or scope.state == "reroute_required"
            ),
        },
    )


def _semantic_checkpoint_v2_string_list(value: object) -> list[str] | None:
    if not isinstance(value, list) or not value:
        return None
    if any(not isinstance(item, str) or not item or item != item.strip() for item in value):
        return None
    if value != sorted(value) or len(set(value)) != len(value):
        return None
    return list(value)


def _semantic_checkpoint_v2_resolution_shape_valid(
    carrier: SemanticCheckpointJsonCarrier,
    *,
    context: Mapping[str, object],
    plan_path_value: str,
    diagnostics: list[SemanticCheckpointDiagnostic],
) -> bool:
    """Validate the standalone V2 shape before binding it to a trigger."""

    if carrier.kind == "malformed":
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_v2_resolution_json_malformed",
            path=plan_path_value,
            line=carrier.line_no,
            message="Bounded-grammar checkpoint V2 JSON is malformed or repeats a JSON key.",
        )
        return False
    if carrier.kind == "resolution_v1":
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_v2_resolution_version_mixed",
            path=plan_path_value,
            line=carrier.line_no,
            message="An admitted bounded-grammar checkpoint accepts V2 resolution carriers only; V1/V2 mixing is invalid.",
        )
        return False
    if carrier.kind == "unknown":
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_v2_resolution_schema_unknown",
            path=plan_path_value,
            line=carrier.line_no,
            message="A semantic cycle checkpoint carrier in a bounded-grammar subject must use the exact V2 schema.",
        )
        return False
    payload = carrier.payload
    if carrier.kind != "resolution_v2" or not isinstance(payload, dict):
        return False

    valid = True
    expected = set(SEMANTIC_CHECKPOINT_V2_RESOLUTION_FIELDS)
    allowed = expected | SEMANTIC_CHECKPOINT_V2_OPTIONAL_RESOLUTION_FIELDS
    unknown = sorted(set(payload) - allowed)
    missing = sorted(expected - set(payload))
    if unknown or missing:
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_v2_resolution_fields_invalid",
            path=plan_path_value,
            line=carrier.line_no,
            message=(
                "Bounded-grammar V2 resolution must use the exact root field set"
                + (f"; missing={', '.join(missing)}" if missing else "")
                + (f"; unknown={', '.join(unknown)}" if unknown else "")
                + "."
            ),
        )
        valid = False
    if payload.get("schema_version") != SEMANTIC_CHECKPOINT_RESOLUTION_V2_SCHEMA:
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_v2_resolution_schema_invalid",
            path=plan_path_value,
            line=carrier.line_no,
            message="Bounded-grammar resolution must use `semantic_cycle_checkpoint_resolution.v2`.",
        )
        valid = False
    if payload.get("resolution_state") != "accepted":
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_v2_resolution_state_invalid",
            path=plan_path_value,
            line=carrier.line_no,
            message="Only literal V2 `resolution_state=accepted` carriers participate in checkpoint history.",
        )
        valid = False
    for field in ("authority_decision_id", "authority_carrier_sha256", "grammar_contour_id"):
        if payload.get(field) != context.get(field):
            _semantic_checkpoint_diagnostic(
                diagnostics,
                code="checkpoint_v2_authority_binding_drift",
                path=plan_path_value,
                line=carrier.line_no,
                message=f"V2 {field} must exactly match the validated bounded-grammar admission.",
            )
            valid = False
    if not isinstance(payload.get("trigger_observation_id"), str) or not payload["trigger_observation_id"].strip():
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_v2_resolution_trigger_invalid",
            path=plan_path_value,
            line=carrier.line_no,
            message="V2 trigger_observation_id must be a non-empty string.",
        )
        valid = False
    if payload.get("trigger_kind") not in SEMANTIC_CHECKPOINT_TRIGGER_KINDS:
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_v2_resolution_trigger_kind_invalid",
            path=plan_path_value,
            line=carrier.line_no,
            message="V2 trigger_kind is invalid.",
        )
        valid = False
    if not isinstance(payload.get("contract_fingerprint"), dict):
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_v2_resolution_fingerprint_invalid",
            path=plan_path_value,
            line=carrier.line_no,
            message="V2 contract_fingerprint must be the accepted producer machine object.",
        )
        valid = False
    evidence_refs = payload.get("decision_evidence_refs")
    if (
        not isinstance(evidence_refs, list)
        or not evidence_refs
        or any(
            not isinstance(item, str)
            or item != item.strip()
            or SEMANTIC_CHECKPOINT_V2_EVIDENCE_REF_RE.fullmatch(item) is None
            for item in evidence_refs
        )
        or evidence_refs != sorted(evidence_refs)
        or len(set(evidence_refs)) != len(evidence_refs)
    ):
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_v2_resolution_evidence_refs_invalid",
            path=plan_path_value,
            line=carrier.line_no,
            message=(
                "V2 decision_evidence_refs must be a non-empty sorted unique list of "
                "normalized repo-backed docs references."
            ),
        )
        valid = False

    rows = payload.get("required_family_resolutions")
    if not isinstance(rows, list) or not rows:
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_v2_resolution_families_invalid",
            path=plan_path_value,
            line=carrier.line_no,
            message="V2 required_family_resolutions must be a non-empty exact family list.",
        )
        return False
    family_ids: list[str] = []
    decisions: list[str] = []
    allowed_axes = context.get("grammar_axis_ids")
    allowed_axis_set = set(allowed_axes) if isinstance(allowed_axes, list) else set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != set(SEMANTIC_CHECKPOINT_V2_FAMILY_RESOLUTION_FIELDS):
            _semantic_checkpoint_diagnostic(
                diagnostics,
                code="checkpoint_v2_resolution_family_fields_invalid",
                path=plan_path_value,
                line=carrier.line_no,
                message="Each V2 family row must contain exactly blocker_family_id, blocker_ref, grammar_axis_ids and decision.",
            )
            valid = False
            continue
        family_id = row.get("blocker_family_id")
        blocker_ref = row.get("blocker_ref")
        axes = _semantic_checkpoint_v2_string_list(row.get("grammar_axis_ids"))
        decision = row.get("decision")
        if not isinstance(family_id, str) or not family_id.strip() or family_id != family_id.strip():
            _semantic_checkpoint_diagnostic(
                diagnostics,
                code="checkpoint_v2_resolution_family_id_invalid",
                path=plan_path_value,
                line=carrier.line_no,
                message="V2 blocker_family_id must be a non-empty trimmed string.",
            )
            valid = False
        else:
            family_ids.append(family_id)
        if not isinstance(blocker_ref, str) or not blocker_ref.strip() or blocker_ref != blocker_ref.strip():
            _semantic_checkpoint_diagnostic(
                diagnostics,
                code="checkpoint_v2_resolution_blocker_ref_invalid",
                path=plan_path_value,
                line=carrier.line_no,
                message="V2 blocker_ref must be a non-empty trimmed string.",
            )
            valid = False
        if axes is None or any(axis not in allowed_axis_set for axis in axes):
            _semantic_checkpoint_diagnostic(
                diagnostics,
                code="checkpoint_v2_resolution_axes_invalid",
                path=plan_path_value,
                line=carrier.line_no,
                message="V2 grammar_axis_ids must be a non-empty sorted unique subset of the frozen contour registry.",
            )
            valid = False
        if decision not in SEMANTIC_CHECKPOINT_V2_DECISIONS:
            _semantic_checkpoint_diagnostic(
                diagnostics,
                code="checkpoint_v2_resolution_decision_invalid",
                path=plan_path_value,
                line=carrier.line_no,
                message="V2 decisions are limited to same_contract_once, de_scope or successor; stop is forbidden.",
            )
            valid = False
        else:
            decisions.append(decision)
    if family_ids != sorted(family_ids) or len(set(family_ids)) != len(family_ids):
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_v2_resolution_family_order_invalid",
            path=plan_path_value,
            line=carrier.line_no,
            message="V2 family rows must be sorted and unique by blocker_family_id.",
        )
        valid = False
    if len(set(decisions)) > 1:
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_v2_resolution_decision_mixed",
            path=plan_path_value,
            line=carrier.line_no,
            message="Every V2 family row must use the same decision.",
        )
        valid = False
    decision = decisions[0] if len(decisions) == len(rows) and decisions else None
    if decision is not None:
        expected_status = SEMANTIC_CHECKPOINT_V2_DECISION_NEXT_STATUS[decision]
        if payload.get("allowed_next_status") != expected_status:
            _semantic_checkpoint_diagnostic(
                diagnostics,
                code="checkpoint_v2_resolution_decision_status_mismatch",
                path=plan_path_value,
                line=carrier.line_no,
                message=f"V2 decision {decision} requires allowed_next_status={expected_status!r}.",
            )
            valid = False
        successor_ref = payload.get("successor_plan_ref")
        if decision == "successor":
            if not isinstance(successor_ref, str) or not successor_ref or successor_ref != successor_ref.strip():
                _semantic_checkpoint_diagnostic(
                    diagnostics,
                    code="checkpoint_v2_resolution_successor_missing",
                    path=plan_path_value,
                    line=carrier.line_no,
                    message="V2 successor requires one non-empty successor_plan_ref.",
                )
                valid = False
        elif "successor_plan_ref" in payload:
            _semantic_checkpoint_diagnostic(
                diagnostics,
                code="checkpoint_v2_resolution_successor_unexpected",
                path=plan_path_value,
                line=carrier.line_no,
                message="V2 successor_plan_ref is valid only for decision=successor.",
            )
            valid = False
    return valid


def _semantic_checkpoint_de_scope_supported(
    lines: Sequence[str],
    family_id: str,
) -> bool:
    """Require a pre-existing literal family exclusion, never a hidden scope rewrite."""

    masked = _semantic_masked_markdown_lines(lines)
    scope = _semantic_exact_h2_section(lines, masked, "Scope")
    acceptance = _semantic_exact_h2_section(lines, masked, "Acceptance criteria / DoD")
    out_of_scope = _semantic_exact_h2_section(lines, masked, "Out of scope")
    if scope is None or acceptance is None or out_of_scope is None:
        return False
    _scope_line, scope_lines = scope
    _acceptance_line, acceptance_lines = acceptance
    _out_line, out_lines = out_of_scope
    scope_text = "\n".join(scope_lines)
    acceptance_text = "\n".join(acceptance_lines)
    out_text = "\n".join(out_lines)
    return family_id in out_text and family_id not in scope_text and family_id not in acceptance_text


def _semantic_checkpoint_successor_materialized(
    plan_path: Path,
    successor_ref: str,
    *,
    repo_root: Path,
) -> bool:
    normalized, problem = normalize_state_transition_protected_path(successor_ref)
    if problem or normalized is None or not normalized.startswith("docs/plans/"):
        return False
    current = _semantic_path_display(plan_path, repo_root)
    if normalized == current:
        return False
    return (repo_root / normalized).is_file()


def _semantic_checkpoint_v2_successor_valid(
    *,
    plan_path: Path,
    plan_path_value: str,
    successor_ref: object,
    trigger: Mapping[str, object],
    rows: Sequence[object],
    context: Mapping[str, object],
    repo_root: Path,
    carrier_line_no: int,
    diagnostics: list[SemanticCheckpointDiagnostic],
    require_nonterminal: bool = True,
) -> bool:
    """Validate the one structured successor transfer allowed after V2 exhaustion."""

    if not isinstance(successor_ref, str):
        return False
    normalized, problem = normalize_state_transition_protected_path(successor_ref)
    if (
        problem
        or normalized is None
        or not normalized.startswith("docs/plans/")
        or normalized == plan_path_value
    ):
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_v2_successor_path_invalid",
            path=plan_path_value,
            line=carrier_line_no,
            message="V2 successor_plan_ref must be a distinct normalized docs/plans path.",
        )
        return False
    successor_path = repo_root / normalized
    if successor_path.is_symlink() or not successor_path.is_file():
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_v2_successor_unmaterialized",
            path=plan_path_value,
            line=carrier_line_no,
            message="V2 successor_plan_ref must name a materialized non-symlink plan file.",
        )
        return False
    try:
        successor_lines = read_text(successor_path)
        successor_text = "\n".join(successor_lines)
    except OSError as exc:
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_v2_successor_unreadable",
            path=plan_path_value,
            line=carrier_line_no,
            message=f"V2 successor plan cannot be read: {exc}.",
        )
        return False
    status_value, status_norm = _semantic_checkpoint_current_status(successor_lines)
    if not status_value or (require_nonterminal and status_norm in {"done", "superseded"}):
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_v2_successor_terminal",
            path=plan_path_value,
            line=carrier_line_no,
            message="V2 successor must remain materialized and non-terminal.",
        )
        return False
    strict = plan_status_oracle.strict_plan_meta_json(successor_text)
    if strict.state != "valid" or strict.plan_meta is None:
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_v2_successor_meta_invalid",
            path=plan_path_value,
            line=carrier_line_no,
            message="V2 successor requires one valid strict Meta carrier.",
        )
        return False
    readback = plan_status_oracle.machine_authority_decision_readback(successor_path, plan_text=successor_text)
    successor_decision = strict.plan_meta.get("machine_authority_decision")
    successor_route = (
        successor_decision.get("recommended_route") if isinstance(successor_decision, Mapping) else None
    )
    if (
        readback.state != "frozen_confirmed"
        or readback.reason_code != "ok"
        or not isinstance(successor_route, Mapping)
        or successor_route.get("kind") != "structured_carrier"
    ):
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_v2_successor_admission_invalid",
            path=plan_path_value,
            line=carrier_line_no,
            message="V2 successor must have a frozen+confirmed structured-carrier admission, never bounded_grammar.",
        )
        return False
    meta = strict.plan_meta
    depends_on = meta.get("depends_on")
    if not isinstance(depends_on, list) or depends_on.count(plan_path_value) != 1:
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_v2_successor_backlink_invalid",
            path=plan_path_value,
            line=carrier_line_no,
            message="V2 successor plan_meta.depends_on must contain the literal source subject exactly once.",
        )
        return False
    intake = meta.get("semantic_cycle_successor_intake")
    if not isinstance(intake, Mapping) or set(intake) != set(SEMANTIC_CHECKPOINT_V2_SUCCESSOR_INTAKE_FIELDS):
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_v2_successor_intake_invalid",
            path=plan_path_value,
            line=carrier_line_no,
            message="V2 successor must carry one exact semantic_cycle_successor_intake.v1 object.",
        )
        return False
    if (
        intake.get("schema_version") != SEMANTIC_CHECKPOINT_V2_SUCCESSOR_INTAKE_SCHEMA
        or intake.get("source_plan") != plan_path_value
        or intake.get("source_trigger_observation_id") != trigger.get("observation_id")
        or intake.get("source_grammar_contour_id") != context.get("grammar_contour_id")
    ):
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_v2_successor_intake_binding_invalid",
            path=plan_path_value,
            line=carrier_line_no,
            message="V2 successor intake must exactly bind the source plan, trigger and grammar contour.",
        )
        return False
    inherited = intake.get("inherited_family_refs")
    if not isinstance(inherited, list):
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_v2_successor_intake_families_invalid",
            path=plan_path_value,
            line=carrier_line_no,
            message="V2 successor intake inherited_family_refs must be an exact sorted family transfer.",
        )
        return False
    source_rows: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            return False
        source_rows.append(
            {
                "blocker_family_id": row.get("blocker_family_id"),
                "blocker_ref": row.get("blocker_ref"),
                "grammar_axis_ids": row.get("grammar_axis_ids"),
            }
        )
    if any(not isinstance(row, Mapping) or set(row) != set(SEMANTIC_CHECKPOINT_V2_SUCCESSOR_FAMILY_FIELDS) for row in inherited):
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_v2_successor_intake_family_fields_invalid",
            path=plan_path_value,
            line=carrier_line_no,
            message="Each successor inherited family row must omit decision and use the exact three transfer fields.",
        )
        return False
    inherited_rows = [dict(row) for row in inherited]
    if inherited_rows != source_rows:
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_v2_successor_intake_family_coverage_invalid",
            path=plan_path_value,
            line=carrier_line_no,
            message="V2 successor intake must exact-cover the accepted source family rows in sorted order.",
        )
        return False
    return True


def _semantic_checkpoint_v2_validate_resolution_against_trigger(
    carrier: SemanticCheckpointJsonCarrier,
    trigger: Mapping[str, object],
    *,
    current_trigger_id: str,
    plan_path: Path,
    plan_path_value: str,
    lines: Sequence[str],
    repo_root: Path,
    context: Mapping[str, object],
    diagnostics: list[SemanticCheckpointDiagnostic],
) -> bool:
    """Bind a V2 accepted carrier to its own immutable trigger and admission."""

    payload = carrier.payload
    assert isinstance(payload, dict)
    valid = True
    if payload.get("trigger_kind") != trigger.get("trigger_kind"):
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_v2_resolution_trigger_kind_mismatch",
            path=plan_path_value,
            line=carrier.line_no,
            message="V2 trigger_kind must exactly match its accepted trigger observation.",
        )
        valid = False
    if payload.get("contract_fingerprint") != trigger.get("contract_fingerprint"):
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_v2_resolution_fingerprint_stale",
            path=plan_path_value,
            line=carrier.line_no,
            message="V2 contract_fingerprint must exactly match its own accepted trigger observation.",
        )
        valid = False
    rows = payload.get("required_family_resolutions")
    expected_rows = trigger.get("required_family_rows")
    if isinstance(rows, list) and isinstance(expected_rows, list):
        actual_rows = [
            {"blocker_family_id": row.get("blocker_family_id"), "blocker_ref": row.get("blocker_ref")}
            for row in rows
            if isinstance(row, Mapping)
        ]
        if actual_rows != expected_rows:
            _semantic_checkpoint_diagnostic(
                diagnostics,
                code="checkpoint_v2_resolution_family_coverage_invalid",
                path=plan_path_value,
                line=carrier.line_no,
                message="V2 resolution must exact-cover every current trigger blocker family and blocker_ref.",
            )
            valid = False
    else:
        valid = False
    decision = None
    if isinstance(rows, list) and rows and isinstance(rows[0], Mapping):
        candidate = rows[0].get("decision")
        decision = candidate if isinstance(candidate, str) else None
    if trigger.get("trigger_kind") == "scope_churn" and decision != "successor":
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_v2_scope_churn_requires_successor",
            path=plan_path_value,
            line=carrier.line_no,
            message="V2 scope_churn permits only a concrete successor decision.",
        )
        valid = False
    if decision == "de_scope" and payload.get("trigger_observation_id") == current_trigger_id:
        if not isinstance(rows, list) or any(
            not isinstance(row, Mapping)
            or not isinstance(row.get("blocker_family_id"), str)
            or not _semantic_checkpoint_de_scope_supported(lines, row["blocker_family_id"])
            for row in rows
        ):
            _semantic_checkpoint_diagnostic(
                diagnostics,
                code="checkpoint_v2_de_scope_not_preexisting",
                path=plan_path_value,
                line=carrier.line_no,
                message="V2 de_scope requires each current family to be literally pre-existing Out of scope and absent from Scope/Acceptance.",
            )
            valid = False
    if decision == "successor":
        _source_status_value, source_status_norm = _semantic_checkpoint_current_status(lines)
        require_nonterminal = (
            payload.get("trigger_observation_id") == current_trigger_id
            and source_status_norm not in {"done", "superseded"}
        )
        valid = _semantic_checkpoint_v2_successor_valid(
            plan_path=plan_path,
            plan_path_value=plan_path_value,
            successor_ref=payload.get("successor_plan_ref"),
            trigger=trigger,
            rows=rows if isinstance(rows, list) else (),
            context=context,
            repo_root=repo_root,
            carrier_line_no=carrier.line_no,
            diagnostics=diagnostics,
            require_nonterminal=require_nonterminal,
        ) and valid
    return valid


def _semantic_checkpoint_validate_resolution_against_trigger(
    carrier: SemanticCheckpointJsonCarrier,
    trigger: Mapping[str, object],
    *,
    current_trigger_id: str,
    plan_path: Path,
    plan_path_value: str,
    lines: Sequence[str],
    repo_root: Path,
    diagnostics: list[SemanticCheckpointDiagnostic],
) -> bool:
    """Bind a structurally valid Architect resolution to one immutable trigger."""

    payload = carrier.payload
    assert isinstance(payload, dict)
    valid = True
    if payload.get("trigger_kind") != trigger.get("trigger_kind"):
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_resolution_trigger_kind_mismatch",
            path=plan_path_value,
            line=carrier.line_no,
            message="Checkpoint resolution trigger_kind must exactly match the accepted trigger observation.",
        )
        valid = False
    if payload.get("contract_fingerprint") != trigger.get("contract_fingerprint"):
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_resolution_fingerprint_stale",
            path=plan_path_value,
            line=carrier.line_no,
            message="Checkpoint resolution contract_fingerprint must exactly match its accepted trigger observation.",
        )
        valid = False
    rows = payload.get("required_family_resolutions")
    expected_families = trigger.get("required_blocker_family_ids")
    if isinstance(rows, list) and isinstance(expected_families, list):
        actual_families = [item.get("blocker_family_id") for item in rows if isinstance(item, dict)]
        if actual_families != expected_families:
            _semantic_checkpoint_diagnostic(
                diagnostics,
                code="checkpoint_resolution_family_coverage_invalid",
                path=plan_path_value,
                line=carrier.line_no,
                message="Checkpoint resolution must exact-cover every sorted current open blocker family.",
            )
            valid = False
    else:
        valid = False

    decision = None
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        candidate = rows[0].get("decision")
        decision = candidate if isinstance(candidate, str) else None
    if decision == "successor":
        successor_ref = payload.get("successor_plan_ref")
        if not isinstance(successor_ref, str) or not _semantic_checkpoint_successor_materialized(
            plan_path, successor_ref, repo_root=repo_root
        ):
            _semantic_checkpoint_diagnostic(
                diagnostics,
                code="checkpoint_resolution_successor_unmaterialized",
                path=plan_path_value,
                line=carrier.line_no,
                message="successor_plan_ref must be a distinct materialized docs/plans plan.",
            )
            valid = False
    if decision == "stop" and payload.get("owner_question_ref") is not None:
        owner_ref = payload.get("owner_question_ref")
        if payload.get("trigger_observation_id") == current_trigger_id:
            _state, _reason, open_questions, _issues = plan_status_oracle.owner_qna_readback("\n".join(lines))
            open_ids = {question.qid for question in open_questions}
            if owner_ref not in open_ids:
                _semantic_checkpoint_diagnostic(
                    diagnostics,
                    code="checkpoint_resolution_owner_question_not_open",
                    path=plan_path_value,
                    line=carrier.line_no,
                    message="stop owner_question_ref must name an open Architect/Owner question in this plan.",
                )
                valid = False
    if decision == "de_scope" and payload.get("trigger_observation_id") == current_trigger_id:
        if not isinstance(rows, list) or any(
            not isinstance(item, dict)
            or not isinstance(item.get("blocker_family_id"), str)
            or not _semantic_checkpoint_de_scope_supported(lines, item["blocker_family_id"])
            for item in rows
        ):
            _semantic_checkpoint_diagnostic(
                diagnostics,
                code="checkpoint_resolution_de_scope_not_preexisting",
                path=plan_path_value,
                line=carrier.line_no,
                message=(
                    "de_scope requires every current family to be literally excluded by the existing `## Out of scope` "
                    "section and absent from Scope/Acceptance; a contract rewrite must use successor, real scope expansion or stop."
                ),
            )
            valid = False
    return valid


def _semantic_checkpoint_current_status(lines: Sequence[str]) -> tuple[str, str]:
    status_lines = extract_status_lines(list(lines))
    if len(status_lines) != 1:
        return "", ""
    status = status_lines[0][1]
    return status, _semantic_checkpoint_status_norm(status)


def _build_semantic_cycle_checkpoint_report(
    plan_path: str | Path,
    *,
    protocol: str,
    v2_context: Mapping[str, object] | None = None,
    context: ContractContext | None = None,
) -> dict[str, object]:
    """Read-only checkpoint projection from accepted producer history.

    ``scripts/semantic_cycle_checkpoint.py`` and the status oracle consume this
    report directly.  The report intentionally has no mutation path and no
    Manager-owned counter, classifier, or decision field.
    """

    path = Path(plan_path)
    repo_root = repo_root_for_plan_path(path, context=context)
    path_value = _semantic_path_display(path, repo_root)
    try:
        lines = read_text(path)
    except OSError as exc:
        diagnostic = SemanticCheckpointDiagnostic(
            code="checkpoint_plan_unreadable",
            path=path_value,
            line=1,
            message=f"Cannot read PLAN_PATH: {exc}.",
        )
        return _semantic_checkpoint_report(
            state="blocked",
            reason_code="activation_invalid",
            producer=None,
            trigger=None,
            resolution=None,
            diagnostics=(diagnostic,),
        )

    marker_active, diagnostics = _semantic_checkpoint_marker_activation(path, lines, repo_root=repo_root)
    if not marker_active:
        return _semantic_checkpoint_report(
            state="not_available",
            reason_code="feature_not_activated",
            producer=None,
            trigger=None,
            resolution=None,
            diagnostics=(),
        )

    if protocol == "v2":
        assert v2_context is not None
        if v2_context.get("scope_expansion_precedes") is True:
            # The generic oracle owns this higher-precedence route.  Do not
            # inspect or spend a V2 carrier under a scope-expansion reroute.
            return _semantic_checkpoint_report(
                state="waiting",
                reason_code="scope_expansion_reroute_precedes_checkpoint",
                producer=None,
                trigger=None,
                resolution=None,
                diagnostics=(),
            )

    producer_active, producer_activation_diagnostics = _semantic_activation(path, lines, repo_root=repo_root)
    if not producer_active:
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_dual_marker_missing_producer",
            path=path_value,
            line=1,
            message=(
                "Active semantic cycle checkpoint requires the exact active Semantic review observation "
                "marker in the same Reviewability preflight receipt."
            ),
        )
    for item in producer_activation_diagnostics:
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_dual_marker_producer_invalid",
            path=item.path,
            line=item.line,
            message=item.message,
        )

    resolution_carriers, carrier_diagnostics = _semantic_checkpoint_resolution_carriers(path, lines, repo_root=repo_root)
    diagnostics.extend(carrier_diagnostics)
    if diagnostics:
        return _semantic_checkpoint_report(
            state="blocked",
            reason_code="activation_invalid",
            producer=None,
            trigger=None,
            resolution=None,
            diagnostics=diagnostics,
        )

    producer_report = build_semantic_review_observation_report(path, context=context)
    producer_state = producer_report.get("state")
    producer_reason = producer_report.get("reason_code")
    producer_summary: dict[str, object] = {
        "state": producer_state if isinstance(producer_state, str) else "invalid",
        "reason_code": producer_reason if isinstance(producer_reason, str) else "invalid",
    }
    if producer_state == "blocked":
        # Producer remains the owner of this failure.  The checkpoint must not
        # recast a Reviewer/risk contract error as an Architect decision.
        return _semantic_checkpoint_report(
            state="producer_blocked",
            reason_code=str(producer_reason or "producer_blocked"),
            producer=producer_summary,
            trigger=None,
            resolution=None,
            diagnostics=(),
        )
    if producer_state == "not_available":
        if resolution_carriers:
            _semantic_checkpoint_diagnostic(
                diagnostics,
                code="checkpoint_resolution_before_current_observation",
                path=path_value,
                line=resolution_carriers[0].line_no,
                message="Checkpoint resolution is invalid until the producer exposes a valid/current observation trigger.",
            )
            return _semantic_checkpoint_report(
                state="blocked",
                reason_code="resolution_invalid",
                producer=producer_summary,
                trigger=None,
                resolution=None,
                diagnostics=diagnostics,
            )
        return _semantic_checkpoint_report(
            state="waiting",
            reason_code=str(producer_reason or "producer_waiting"),
            producer=producer_summary,
            trigger=None,
            resolution=None,
            diagnostics=(),
        )
    producer_waiting = producer_state == "ready_to_materialize"
    if producer_state not in {"valid", "ready_to_materialize"} or (
        producer_state == "valid" and producer_reason != "current_observation_valid"
    ):
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_producer_state_unknown",
            path=path_value,
            line=1,
            message="Checkpoint consumer accepts only producer valid/current_observation_valid or documented waiting states.",
        )
        return _semantic_checkpoint_report(
            state="blocked",
            reason_code="producer_state_invalid",
            producer=producer_summary,
            trigger=None,
            resolution=None,
            diagnostics=diagnostics,
        )

    # A fresh Reviewer risk/proposal can leave the producer waiting while its
    # validated_chain still carries older accepted observations.  Those older
    # checkpoint triggers and their Architect resolutions remain history; only
    # a resolution that cannot bind to that accepted history is invalid here.
    accepted_chain = producer_report.get("validated_chain")
    if producer_waiting and isinstance(accepted_chain, list) and not accepted_chain:
        if resolution_carriers:
            _semantic_checkpoint_diagnostic(
                diagnostics,
                code="checkpoint_resolution_before_current_observation",
                path=path_value,
                line=resolution_carriers[0].line_no,
                message="Checkpoint resolution is invalid until the producer exposes a valid/current observation trigger.",
            )
            return _semantic_checkpoint_report(
                state="blocked",
                reason_code="resolution_invalid",
                producer=producer_summary,
                trigger=None,
                resolution=None,
                diagnostics=diagnostics,
            )
        return _semantic_checkpoint_report(
            state="waiting",
            reason_code=str(producer_reason or "producer_waiting"),
            producer=producer_summary,
            trigger=None,
            resolution=None,
            diagnostics=(),
        )

    observations, observation_diagnostics = _semantic_checkpoint_accepted_observations(
        path,
        lines,
        producer_report,
        repo_root=repo_root,
    )
    diagnostics.extend(observation_diagnostics)
    if observations is None:
        return _semantic_checkpoint_report(
            state="blocked",
            reason_code="accepted_history_invalid",
            producer=producer_summary,
            trigger=None,
            resolution=None,
            diagnostics=diagnostics,
        )
    triggers = _semantic_checkpoint_trigger_map(
        observations,
        plan_path_value=path_value,
        diagnostics=diagnostics,
        scope_churn_precedes=protocol == "v2",
    )
    if diagnostics:
        return _semantic_checkpoint_report(
            state="blocked",
            reason_code="accepted_history_invalid",
            producer=producer_summary,
            trigger=None,
            resolution=None,
            diagnostics=diagnostics,
        )

    current_observation_id = observations[-1].get("observation_id")
    if not isinstance(current_observation_id, str):
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_current_observation_id_invalid",
            path=path_value,
            line=1,
            message="Producer current accepted observation must retain observation_id.",
        )
        return _semantic_checkpoint_report(
            state="blocked",
            reason_code="accepted_history_invalid",
            producer=producer_summary,
            trigger=None,
            resolution=None,
            diagnostics=diagnostics,
        )

    records_by_trigger: dict[str, list[tuple[SemanticCheckpointJsonCarrier, bool]]] = {}
    valid_records: list[SemanticCheckpointJsonCarrier] = []
    for carrier in resolution_carriers:
        if protocol == "v2":
            assert v2_context is not None
            shape_valid = _semantic_checkpoint_v2_resolution_shape_valid(
                carrier,
                context=v2_context,
                plan_path_value=path_value,
                diagnostics=diagnostics,
            )
        else:
            shape_valid = _semantic_checkpoint_resolution_shape_valid(
                carrier,
                plan_path_value=path_value,
                diagnostics=diagnostics,
            )
        payload = carrier.payload
        trigger_id = payload.get("trigger_observation_id") if isinstance(payload, dict) else None
        if isinstance(trigger_id, str):
            records_by_trigger.setdefault(trigger_id, []).append((carrier, shape_valid))
        if not shape_valid or not isinstance(payload, dict):
            continue
        trigger = triggers.get(str(payload["trigger_observation_id"]))
        if trigger is None:
            _semantic_checkpoint_diagnostic(
                diagnostics,
                code="checkpoint_resolution_trigger_unknown",
                path=path_value,
                line=carrier.line_no,
                message="Checkpoint resolution trigger_observation_id must name an accepted checkpoint-triggering observation.",
            )
            continue
        if protocol == "v2":
            assert v2_context is not None
            bound_valid = _semantic_checkpoint_v2_validate_resolution_against_trigger(
                carrier,
                trigger,
                current_trigger_id="" if producer_waiting else current_observation_id,
                plan_path=path,
                plan_path_value=path_value,
                lines=lines,
                repo_root=repo_root,
                context=v2_context,
                diagnostics=diagnostics,
            )
        else:
            bound_valid = _semantic_checkpoint_validate_resolution_against_trigger(
                carrier,
                trigger,
                current_trigger_id="" if producer_waiting else current_observation_id,
                plan_path=path,
                plan_path_value=path_value,
                lines=lines,
                repo_root=repo_root,
                diagnostics=diagnostics,
            )
        if bound_valid:
            valid_records.append(carrier)

    for trigger_id, records in records_by_trigger.items():
        if len(records) > 1:
            _semantic_checkpoint_diagnostic(
                diagnostics,
                code="checkpoint_resolution_duplicate_for_trigger",
                path=path_value,
                line=records[1][0].line_no,
                message="Each accepted checkpoint trigger may have at most one Architect resolution carrier.",
            )

    valid_by_trigger: dict[str, list[SemanticCheckpointJsonCarrier]] = {}
    for carrier in valid_records:
        assert isinstance(carrier.payload, dict)
        valid_by_trigger.setdefault(str(carrier.payload["trigger_observation_id"]), []).append(carrier)

    for trigger_id in triggers:
        if (producer_waiting or trigger_id != current_observation_id) and len(valid_by_trigger.get(trigger_id, [])) != 1:
            _semantic_checkpoint_diagnostic(
                diagnostics,
                code="checkpoint_historical_resolution_missing",
                path=path_value,
                line=1,
                message="A historical checkpoint trigger is missing one valid Architect resolution and cannot be bypassed.",
            )

    seen_permits: dict[str, SemanticCheckpointJsonCarrier] = {}
    for carrier in valid_records:
        assert isinstance(carrier.payload, dict)
        rows = carrier.payload.get("required_family_resolutions")
        if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
            continue
        if rows[0].get("decision") != "same_contract_once":
            continue
        if protocol == "v2":
            assert v2_context is not None
            contour_id = v2_context.get("grammar_contour_id")
            if not isinstance(contour_id, str):
                continue
            previous = seen_permits.get(contour_id)
            if previous is not None:
                _semantic_checkpoint_diagnostic(
                    diagnostics,
                    code="grammar_contour_same_contract_once_reused",
                    path=path_value,
                    line=carrier.line_no,
                    message=(
                        "same_contract_once is single-use for the entire stable grammar_contour_id; "
                        "a new blocker family, target snapshot or fingerprint cannot reset the permit."
                    ),
                )
            else:
                seen_permits[contour_id] = carrier
        else:
            for item in rows:
                assert isinstance(item, dict)
                family_id = item.get("blocker_family_id")
                if not isinstance(family_id, str):
                    continue
                previous = seen_permits.get(family_id)
                if previous is not None:
                    _semantic_checkpoint_diagnostic(
                        diagnostics,
                        code="checkpoint_same_contract_permit_reused",
                        path=path_value,
                        line=carrier.line_no,
                        message=(
                            "same_contract_once is single-use for each blocker_family_id across fingerprint drift; "
                            "the fingerprint remains the exact resolution freshness binding, not a new Coder-intake key."
                        ),
                    )
                else:
                    seen_permits[family_id] = carrier

    current_trigger = triggers.get(current_observation_id)
    current_records = records_by_trigger.get(current_observation_id, [])
    current_valid_records = valid_by_trigger.get(current_observation_id, [])
    if current_trigger is None and current_records:
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_resolution_without_current_trigger",
            path=path_value,
            line=current_records[0][0].line_no,
            message="Current checkpoint resolution is invalid because the current accepted observation has no checkpoint trigger.",
        )

    required_diagnostics: list[SemanticCheckpointDiagnostic] = []
    if current_trigger is not None and not current_records:
        _semantic_checkpoint_diagnostic(
            required_diagnostics,
            code="checkpoint_resolution_required",
            path=path_value,
            line=1,
            message="Current accepted checkpoint trigger requires one Architect resolution before downstream routing.",
        )
    if current_trigger is not None and current_records and len(current_valid_records) != 1 and not diagnostics:
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_current_resolution_invalid",
            path=path_value,
            line=current_records[0][0].line_no if current_records else 1,
            message="Current checkpoint trigger must have exactly one valid Architect resolution.",
        )

    if diagnostics:
        return _semantic_checkpoint_report(
            state="blocked",
            reason_code="resolution_invalid",
            producer=producer_summary,
            trigger=current_trigger,
            resolution=None,
            diagnostics=diagnostics,
        )
    if producer_waiting:
        return _semantic_checkpoint_report(
            state="waiting",
            reason_code=str(producer_reason or "producer_waiting"),
            producer=producer_summary,
            trigger=None,
            resolution=None,
            diagnostics=(),
        )
    if required_diagnostics:
        return _semantic_checkpoint_report(
            state="required",
            reason_code="resolution_required",
            producer=producer_summary,
            trigger=current_trigger,
            resolution=None,
            diagnostics=required_diagnostics,
        )
    if current_trigger is None:
        return _semantic_checkpoint_report(
            state="not_required",
            reason_code="current_observation_no_checkpoint_trigger",
            producer=producer_summary,
            trigger=None,
            resolution=None,
            diagnostics=(),
        )

    resolution_carrier = current_valid_records[0]
    assert isinstance(resolution_carrier.payload, dict)
    resolution = resolution_carrier.payload
    allowed_next_status = str(resolution["allowed_next_status"])
    status_value, status_norm = _semantic_checkpoint_current_status(lines)
    if status_norm in SEMANTIC_CHECKPOINT_ARCHITECT_STATUS_NORMS:
        return _semantic_checkpoint_report(
            state="resolved",
            reason_code="architect_resolution_pending_release",
            producer=producer_summary,
            trigger=current_trigger,
            resolution=resolution,
            diagnostics=(),
        )
    permitted_statuses = SEMANTIC_CHECKPOINT_CONTINUATION_STATUS_NORMS[allowed_next_status]
    if status_norm not in permitted_statuses:
        _semantic_checkpoint_diagnostic(
            diagnostics,
            code="checkpoint_resolution_next_status_mismatch",
            path=path_value,
            line=resolution_carrier.line_no,
            message=(
                f"Checkpoint resolution permits {allowed_next_status!r}; current status {status_value!r} is not the "
                "exact release or its normal owning-role continuation."
            ),
        )
        return _semantic_checkpoint_report(
            state="blocked",
            reason_code="resolution_next_status_mismatch",
            producer=producer_summary,
            trigger=current_trigger,
            resolution=resolution,
            diagnostics=diagnostics,
        )
    return _semantic_checkpoint_report(
        state="permitted",
        reason_code="resolution_release_valid",
        producer=producer_summary,
        trigger=current_trigger,
        resolution=resolution,
        diagnostics=(),
    )


def build_semantic_cycle_checkpoint_report(
    plan_path: str | Path,
    *,
    context: ContractContext | None = None,
) -> dict[str, object]:
    """Select legacy V1 or the separately admitted bounded-grammar V2 overlay."""

    path = Path(plan_path)
    resolved_context = context or _ACTIVE_PLAN_LINT_CONTEXT.get()
    repo_root = repo_root_for_plan_path(path, context=resolved_context)
    try:
        lines = read_text(path)
    except OSError:
        # Keep the existing unreadable-plan diagnostic and its public shape in
        # one implementation path.
        return _build_semantic_cycle_checkpoint_report(path, protocol="v1", context=resolved_context)
    selector_state, selector_context = _semantic_checkpoint_v2_context(
        path,
        lines,
        repo_root=repo_root,
        context=resolved_context,
    )
    if selector_state == "selected":
        assert selector_context is not None
        report = _build_semantic_cycle_checkpoint_report(
            path, protocol="v2", v2_context=selector_context, context=resolved_context,
        )
        report.update(
            {
                "authority_decision_id": selector_context["authority_decision_id"],
                "authority_carrier_sha256": selector_context["authority_carrier_sha256"],
                "grammar_contour_id": selector_context["grammar_contour_id"],
            }
        )
        return report
    if selector_state == "admission_unavailable":
        # A declared bounded-grammar route cannot fall back to the legacy
        # family-local protocol.  Admission itself remains generic-oracle
        # authority, so report a passive checkpoint state without inspecting
        # Evidence or minting a missing-carrier duty.
        return _semantic_checkpoint_report(
            state="waiting",
            reason_code="bounded_grammar_admission_unavailable",
            producer=None,
            trigger=None,
            resolution=None,
            diagnostics=(),
        )
    return _build_semantic_cycle_checkpoint_report(path, protocol="v1", context=resolved_context)


semantic_cycle_checkpoint_report = build_semantic_cycle_checkpoint_report


def validate_semantic_cycle_checkpoint_contract(
    path: Path,
    lines: Sequence[str],
    *,
    status_value: str | None,
    context: ContractContext | None = None,
) -> list[Finding]:
    """Surface active checkpoint failures without stealing producer ownership."""

    active, _activation_diagnostics = _semantic_checkpoint_marker_activation(
        path,
        lines,
        repo_root=repo_root_for_plan_path(path, context=context or _ACTIVE_PLAN_LINT_CONTEXT.get()),
    )
    if not active:
        return []
    report = build_semantic_cycle_checkpoint_report(path, context=context)
    state = report.get("state")
    if state == "producer_blocked":
        return []
    if state not in {"blocked", "required"}:
        return []
    errors = report.get("errors")
    first = errors[0] if isinstance(errors, list) and errors and isinstance(errors[0], dict) else {}
    line = first.get("line") if isinstance(first, dict) else None
    message = first.get("message") if isinstance(first, dict) else "checkpoint resolution is required"
    return [
        Finding(
            path,
            int(line) if isinstance(line, int) else 1,
            "ERROR",
            f"Semantic cycle checkpoint is {state} ({report.get('reason_code', 'invalid')}): {message}.",
        )
    ]


def _semantic_coder_stale_current_warning_eligible(
    path: Path,
    lines: Sequence[str],
    *,
    status_value: str | None,
    report: dict[str, object],
) -> bool:
    """Allow only the declared pre-Reviewer stale-current presentation WARN."""

    if not is_coder_rerun_window(status_value):
        return False
    if report.get("state") != "blocked" or report.get("reason_code") != "current_head_mismatch":
        return False
    errors = report.get("errors")
    if not isinstance(errors, list):
        return False
    stale_snapshot_errors = [
        error
        for error in errors
        if isinstance(error, dict) and error.get("code") == "semantic_current_target_snapshot_stale"
    ]
    fingerprint_mismatch_errors = [
        error
        for error in errors
        if isinstance(error, dict)
        and error.get("code") == "semantic_observation_machine_fields_mismatch"
        and error.get("message")
        == "Semantic final observation machine-owned fields do not equal deterministic materialization: "
        "contract_fingerprint."
    ]
    if len(stale_snapshot_errors) != 1:
        return False
    if len(errors) == 1:
        pass
    elif len(errors) == 2 and len(fingerprint_mismatch_errors) == 1:
        pass
    else:
        return False

    repo_root = repo_root_for_plan_path(path)
    _fingerprint, review_artifact, _review_line, fingerprint_diagnostics = _semantic_contract_fingerprint(
        path,
        lines,
        repo_root=repo_root,
    )
    if fingerprint_diagnostics or not review_artifact:
        return False
    review_path = (repo_root / review_artifact).resolve()
    if not review_path.is_file():
        return False
    review_lines = read_text(review_path)
    review_status, _review_status_line = review_header_metadata.singleton_header_value(review_lines, "status")
    review_date, _review_date_line = review_header_metadata.singleton_header_value(review_lines, "date")
    if normalize_review_status(review_status) != CODE_DOC_REVIEW_BLOCKER_STATUS_NORM:
        return False
    aggregate_indexes = [
        index for index, line in enumerate(review_lines) if SEMANTIC_AGGREGATE_HEADING_RE.match(line)
    ]
    if len(aggregate_indexes) != 1:
        return False
    aggregate_start = aggregate_indexes[0]
    aggregate_end = next(
        (index for index in range(aggregate_start + 1, len(review_lines)) if H2_HEADING_RE.match(review_lines[index])),
        len(review_lines),
    )
    aggregate_statuses = [
        match.group("value").strip()
        for index in range(aggregate_start + 1, aggregate_end)
        if (match := SEMANTIC_AGGREGATE_STATUS_RE.match(review_lines[index])) is not None
    ]
    if len(aggregate_statuses) != 1 or normalize_review_status(aggregate_statuses[0]) != CODE_DOC_REVIEW_BLOCKER_STATUS_NORM:
        return False
    return review_artifacts_section_has_stale_rerun_note(
        list(lines),
        live_rel_path=review_artifact,
        review_date_value=review_date,
    )


def validate_semantic_review_observation_contract(
    path: Path,
    lines: Sequence[str],
    *,
    status_value: str | None,
) -> list[Finding]:
    """Surface active-contract failures through ordinary plan linting."""

    active, _activation_diagnostics = _semantic_activation(path, lines, repo_root=repo_root_for_plan_path(path))
    if not active:
        return []
    report = build_semantic_review_observation_report(path)
    if report["state"] == "blocked":
        errors = report["errors"]
        assert isinstance(errors, list) and errors
        first = errors[0]
        assert isinstance(first, dict)
        line = first.get("line")
        if _semantic_coder_stale_current_warning_eligible(
            path,
            lines,
            status_value=status_value,
            report=report,
        ):
            return [
                Finding(
                    path,
                    int(line) if isinstance(line, int) else 1,
                    "WARN",
                    "Semantic review observation contract remains intentionally blocked "
                    "(current_head_mismatch) during the bounded Coder same-file rerun window; "
                    "fresh Reviewer risk/proposal/final evidence is still required.",
                )
            ]
        return [
            Finding(
                path,
                int(line) if isinstance(line, int) else 1,
                "ERROR",
                "Semantic review observation contract is blocked "
                f"({report['reason_code']}): {first.get('message', 'invalid carrier')}.",
            )
        ]
    if (status_value or "").strip().casefold() == "ready for arch review" and report["state"] != "valid":
        return [
            Finding(
                path,
                1,
                "ERROR",
                "Active semantic review observation contract requires valid/current_observation_valid before `Ready for Arch review`.",
            )
        ]
    return []


def _lint_plan_in_context(
    path: Path,
    *,
    effective_status: str | None = None,
    context: ContractContext | None = None,
) -> list[Finding]:
    if effective_status not in {None, "Done"}:
        raise ValueError(f"Unsupported effective plan status: {effective_status!r}")

    findings: list[Finding] = []
    lines = read_text(path)
    plan_repo_root = repo_root_for_plan_path(path, context=context)
    status_lines = extract_status_lines(lines)
    raw_status_value = status_lines[0][1] if status_lines else None
    effective_status_value = effective_status if effective_status is not None else raw_status_value

    meta_findings, plan_meta_line, plan_meta_obj = validate_plan_meta(path, lines)
    analysis_authority = plan_status_oracle.resolve_analysis_pack_authority(
        origin_plan_path=path,
        plan_text="\n".join(lines),
        effective_status=effective_status_value,
    )
    analysis_lines = (
        lines
        if analysis_authority.mode == "legacy"
        else analysis_authority.authority_text.splitlines()
    )
    findings.extend(meta_findings)
    findings.extend(validate_machine_authority_decision(path, lines))
    findings.extend(
        validate_blocking_dependency_carrier(
            path,
            plan_meta_obj,
            plan_meta_line,
            status_value=effective_status_value,
            context=context,
        )
    )
    findings.extend(validate_code_block_sizes(path, lines, plan_meta_line))
    findings.extend(validate_phase_overlay_contract(path, lines, plan_meta_obj))
    findings.extend(
        validate_decomposition_child_materialization(
            path,
            lines,
            plan_meta_obj,
            status_value=effective_status_value,
            context=context,
        )
    )
    findings.extend(
        validate_decomposition_child_readiness(
            path,
            lines,
            plan_meta_obj,
            context=context,
        )
    )
    findings.extend(validate_small_runner_admission(path, lines, plan_meta_obj))
    findings.extend(validate_decomposition_mechanism_schema(path, lines, plan_meta_obj))
    findings.extend(validate_decomposition_graph_shape(path, lines, plan_meta_obj))
    findings.extend(validate_close_out_routing_section(path, lines))
    findings.extend(validate_rollout_packet_handoff_section(path, lines))
    findings.extend(validate_verification_handoff_section(path, lines))
    findings.extend(validate_manager_mode_handoff_command(path, lines, plan_meta_obj))
    findings.extend(validate_analysis_pack_authority(path, analysis_authority))
    if analysis_authority.authority_text:
        findings.extend(validate_analysis_pack_requirement_slices(path, analysis_lines))
        findings.extend(validate_analysis_route_single_authority(path, analysis_lines, plan_meta_obj, plan_meta_line))
        findings.extend(validate_analysis_pack_completion_source_floor(path, analysis_lines, plan_meta_obj))
        findings.extend(validate_analysis_route_lifecycle_guard(path, analysis_lines, plan_meta_obj))
    findings.extend(
        validate_planning_contour_carrier_schema(
            path,
            lines,
            plan_meta_obj,
            plan_meta_line,
            status_value=effective_status_value,
        )
    )
    findings.extend(
        validate_dev_contour_child_graph_drift(
            path,
            lines,
            plan_meta_obj,
            plan_meta_line,
            status_value=effective_status_value,
        )
    )
    findings.extend(
        validate_umbrella_roadmap_lifecycle_guard(
            path,
            lines,
            plan_meta_obj,
            plan_meta_line,
            status_value=effective_status_value,
        )
    )
    findings.extend(
        validate_selected_child_roadmap_handoff_guard(
            path,
            lines,
            plan_meta_obj,
            plan_meta_line,
            status_value=effective_status_value,
        )
    )
    findings.extend(validate_reviewer_proof_contract(path, lines))
    _, schema_findings = classify_plan_schema_version(path, lines)
    findings.extend(schema_findings)

    plan_type = extract_plan_type(lines)
    refs = extract_code_draft_refs(lines)
    findings.extend(
        validate_scope_route_classification(
            path,
            lines,
            plan_type=plan_type,
            status_value=effective_status_value,
        )
    )
    findings.extend(validate_architect_understanding_block(path, lines, status_value=effective_status_value))
    findings.extend(validate_done_post_merge_gate_checklist(path, lines, status_value=effective_status_value))
    findings.extend(validate_russian_plan_statement_sections(path, lines))
    findings.extend(validate_materialized_review_visual_lane_contract(path, lines))
    findings.extend(validate_review_range_semantic_provenance(path, lines))
    findings.extend(
        validate_review_artifact_rerun_freshness(
            path,
            lines,
            status_value=effective_status_value,
            plan_repo_root=plan_repo_root,
        )
    )
    findings.extend(
        validate_review_route_determinism(
            path,
            lines,
            status_value=effective_status_value,
            code_draft_refs=refs,
            plan_repo_root=plan_repo_root,
        )
    )
    findings.extend(
        validate_done_executable_review_artifact_guard(
            path,
            lines,
            plan_meta_obj,
            status_value=effective_status_value,
            plan_type=plan_type,
            plan_repo_root=plan_repo_root,
        )
    )
    findings.extend(
        validate_exact_bundle_preflight(
            path,
            status_value=effective_status_value,
            code_draft_refs=refs,
            plan_repo_root=plan_repo_root,
        )
    )
    findings.extend(
        validate_state_transition_declarations(
            path,
            lines,
            status_value=effective_status_value,
            code_draft_refs=refs,
            plan_repo_root=plan_repo_root,
        )
    )
    findings.extend(
        validate_semantic_review_observation_contract(
            path,
            lines,
            status_value=effective_status_value,
        )
    )
    findings.extend(
        validate_semantic_cycle_checkpoint_contract(
            path,
            lines,
            status_value=effective_status_value,
            context=context,
        )
    )
    findings.extend(
        validate_origin_plan_review_targets(
            path,
            lines,
            raw_status_value=raw_status_value,
            effective_status_value=effective_status_value,
            plan_type=plan_type,
            plan_meta_obj=plan_meta_obj,
            code_draft_refs=refs,
            plan_repo_root=plan_repo_root,
        )
    )
    findings.extend(
        validate_shared_helper_dependent_inventory(
            path,
            lines,
            status_value=effective_status_value,
            code_draft_refs=refs,
            plan_repo_root=plan_repo_root,
        )
    )
    findings.extend(
        validate_documentation_impact_section(
            path,
            lines,
            code_draft_refs=refs,
            plan_repo_root=plan_repo_root,
            status_value=effective_status_value,
        )
    )
    findings.extend(
        Finding(path, receipt.line_no, "ERROR", receipt.message)
        for receipt in retrieval_telemetry_receipt.lint_retrieval_telemetry_receipt(lines)
    )
    findings.extend(
        validate_blocker_attribution_contract(
            path,
            code_draft_refs=refs,
            plan_repo_root=plan_repo_root,
        )
    )
    is_done = bool(effective_status_value and DONE_RE.search(effective_status_value))
    if not status_lines:
        findings.append(Finding(path, 1, "ERROR", "Missing **Status:** header (must be exactly one line)."))
    elif len(status_lines) > 1:
        line_nos = ", ".join(str(line_no) for line_no, _ in status_lines)
        findings.append(
            Finding(
                path,
                status_lines[0][0],
                "ERROR",
                f"Multiple **Status:** header lines found ({line_nos}). Must be exactly one.",
            )
        )
    else:
        status_line_no, status_value_single = status_lines[0]
        if "|" in status_value_single:
            findings.append(
                Finding(
                    path,
                    status_line_no,
                    "ERROR",
                "Template placeholder **Status:** detected (contains '|'). Replace with a single status value.",
            )
        )

    # Code draft requirement:
    # - Once a plan is in execution/review flow, it must mention at least one docs/code_drafts/*.md link.
    # - If a plan mentions code_drafts links but files are missing, that's an error in execution flow and a warn otherwise.
    require_draft = requires_code_draft(effective_status_value)
    if is_decomposition_wave(plan_meta_obj):
        require_draft = False
    # The "must mention a code draft" gate checks awareness of the code-draft concept:
    # either an explicit path (even an out-of-scope N/A / sibling-repo / historical
    # one) or an explicit `Code draft(s): N/A (...)` carrier both satisfy it. The
    # missing-file check below uses the filtered refs.
    code_draft_carrier_re = re.compile(r"^\s*-\s*Code draft(?:\(s\)|s)?:\s*", re.IGNORECASE)
    has_draft_awareness = bool(
        extract_code_draft_refs(lines, include_annotated=True)
        or any(code_draft_carrier_re.match(line) for line in lines)
    )
    if require_draft and not has_draft_awareness:
        details = f" (plan_type={plan_type})" if plan_type else ""
        findings.append(
            Finding(
                path,
                1,
                "ERROR",
                "Missing code draft link: add `docs/code_drafts/...__code_draft.md` to Context links and create the file." + details,
            )
        )

    for line_no, rel_path_str in refs:
        draft_path = (plan_repo_root / rel_path_str).resolve()
        if not draft_path.exists():
            findings.append(
                Finding(
                    path,
                    line_no,
                    "ERROR" if require_draft else "WARN",
                    f"Code draft link points to missing file: {rel_path_str}.",
                )
            )

    # Planner: if there are no suggestions, we still need an explicit stamp in the code draft that it was reviewed.
    # (Otherwise it's too easy to "skip" the artifact by just leaving a link in Context links.)
    if require_draft and refs:
        in_planner_suggestions = False
        saw_no_suggestions = False
        no_suggestions_line_no: int | None = None

        for idx, line in enumerate(lines, start=1):
            if PLANNER_SUGGESTIONS_HEADING_RE.match(line):
                in_planner_suggestions = True
                continue

            if in_planner_suggestions and SECTION_HEADING_RE.match(line):
                break

            if not in_planner_suggestions:
                continue

            if NO_SUGGESTIONS_RE.search(line):
                saw_no_suggestions = True
                no_suggestions_line_no = no_suggestions_line_no or idx

        if saw_no_suggestions:
            expected_rel = f"docs/code_drafts/{path.stem}__code_draft.md"
            ref_paths = [rel_path_str for _, rel_path_str in refs]
            to_check = [expected_rel] if expected_rel in ref_paths else ref_paths

            stamp_ok = False
            for rel_path_str in to_check:
                draft_path = (plan_repo_root / rel_path_str).resolve()
                if not draft_path.exists():
                    continue
                for draft_line in draft_path.read_text(encoding="utf-8").splitlines():
                    if PLANNER_NO_SUGGESTIONS_STAMP_RE.search(draft_line):
                        stamp_ok = True
                        break
                if stamp_ok:
                    break

            if not stamp_ok:
                findings.append(
                    Finding(
                        path,
                        no_suggestions_line_no or 1,
                        "ERROR",
                        "Planner: если в `### Planner suggestions` написано `NO SUGGESTIONS`, нужно добавить штамп в code draft "
                        "(строка вида `- […] (Planner) NO SUGGESTIONS …` в `docs/code_drafts/...__code_draft.md`).",
                    )
                )

    qna_events, qna_issues = plan_status_oracle.owner_qna_events_and_issues("\n".join(lines))
    latest_qna_events = plan_status_oracle.latest_owner_qna_events(qna_events)
    still_open = sorted(qid for qid, event in latest_qna_events.items() if event.state == "open")
    for issue in qna_issues:
        findings.append(
            Finding(
                path,
                issue.line_no,
                "ERROR",
                f"{issue.message}. Use append-only `id=Qn status=open|closed|superseded` Owner Q&A carriers.",
            )
        )
    for qid in still_open:
        line_no = latest_qna_events[qid].line_no
        findings.append(
            Finding(
                path,
                line_no,
                "ERROR",
                f"Q&A item {qid} is still open. Add a CLOSED entry (status=closed) or supersede it.",
            )
        )

    if is_done and still_open:
        findings.append(
            Finding(
                path,
                1,
                "ERROR",
                "Plan status is Done but there are open Q&A items.",
            )
        )

    return findings


def lint_plan(
    path: Path,
    *,
    effective_status: str | None = None,
    context: ContractContext | None = None,
) -> list[Finding]:
    """Lint one plan with target-local vocabulary and no sticky global state."""

    resolved_context = context or _ACTIVE_PLAN_LINT_CONTEXT.get()
    root = (
        repo_root_for_plan_path(path, context=resolved_context)
        if resolved_context is not None
        else _actual_repo_root_for_plan_path(path)
    )
    with _scoped_plan_lint_context(root, context=resolved_context, require_vocab=False) as active_context:
        return _lint_plan_in_context(path, effective_status=effective_status, context=active_context)


def print_findings(findings: Iterable[Finding]) -> None:
    for finding in findings:
        print(f"{finding.severity}: {rel(finding.file)}:{finding.line}: {finding.message}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lint docs plans for Q&A hygiene.")
    parser.add_argument(
        "paths",
        nargs="*",
        help="Plan file(s) or directories (default: docs/plans).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Lint all plans under docs/plans.",
    )
    parser.add_argument(
        "--as-status",
        metavar="STATUS",
        help="Evaluate status-dependent validators as STATUS without changing the plan (only Done is supported).",
    )
    args = parser.parse_args(argv)

    if args.as_status is not None:
        if args.as_status != "Done":
            print("ERROR: --as-status supports only the exact value Done.")
            return 2
        if args.all:
            print("ERROR: --as-status cannot be combined with --all.")
            return 2
        if len(args.paths) != 1:
            print("ERROR: --as-status requires exactly one explicit plan file.")
            return 2
        override_path = Path(args.paths[0])
        if not override_path.is_file():
            print("ERROR: --as-status requires one existing regular plan file.")
            return 2

    try:
        # An explicit plan path selects the one actual project root before
        # authority capture.  Argument parsing and path derivation do not
        # consume contract content; every vocabulary/default traversal follows
        # the single captured context below.
        root_hints = {
            _actual_repo_root_for_plan_path(Path(raw_path)).resolve()
            for raw_path in (() if args.all else args.paths)
        }
        if len(root_hints) > 1:
            print("ERROR: explicit plan paths must belong to one project root.")
            return 2
        context = resolve_top_level_context(next(iter(root_hints), None))
    except ContractAuthorityError as exc:
        print(f"ERROR: {exc}")
        return 1

    try:
        # Capture once before the direct CLI reads its vocabulary or traverses
        # default paths.  The context is then passed through every nested plan.
        with _scoped_plan_lint_context(
            context.project_root,
            context=context,
            require_vocab=True,
        ) as resolved_context:
            if args.all or not args.paths:
                targets = [PLANS_ROOT]
            else:
                targets = [Path(arg) for arg in args.paths]

            plan_files = iter_plan_files(targets)
            if not plan_files:
                print("WARN: no plan files found.")
                return 0

            all_findings: list[Finding] = []
            for plan in plan_files:
                all_findings.extend(lint_plan(plan, effective_status=args.as_status))
    except (ManifestError, ContractAuthorityError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1

    print_findings(all_findings)
    has_errors = any(f.severity == "ERROR" for f in all_findings)
    return 1 if has_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

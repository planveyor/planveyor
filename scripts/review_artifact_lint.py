#!/usr/bin/env python3
"""Lint bounded review-artifact grammar families."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import importlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import sys
from typing import TYPE_CHECKING, Any, Iterable, Mapping, Sequence

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
        require_declared_read,
        resolve_top_level_context,
    )
else:
    ContractAuthorityError = _authority.ContractAuthorityError
    ContractContext = _authority.ContractContext
    context_for_reader = _authority.context_for_reader
    read_declared_text = _authority.read_declared_text
    require_declared_read = _authority.require_declared_read
    resolve_top_level_context = _authority.resolve_top_level_context

REPO_ROOT = Path(__file__).resolve().parents[1]

import plan_lint
import review_header_metadata
import retrieval_telemetry_receipt
import review_visual_lane_contract
from review_target_snapshot import (
    CURRENT_BUNDLE_TARGET,
    SnapshotError,
    build_current_bundle_snapshot,
)
from review_schema_contract import (
    CODE_DOC_REVIEW_BLOCKER_STATUS,
    CODE_DOC_REVIEW_BLOCKER_STATUS_NORM,
    CODE_DOC_REVIEW_FINAL_STATUS_NORMS,
    CODE_DOC_REVIEW_OK_STATUS,
    CODE_DOC_REVIEW_OK_STATUS_NORM,
    CODE_DOC_REVIEW_STATUS_NORMS,
    CURRENT_REVIEW_SCHEMA_VERSION,
    MERGE_NOTES_STATUS_NORMS,
    normalize_review_status,
)


def __getattr__(name: str):
    """Lazily re-export selector API without a plan-lint import cycle."""

    if name in {
        "PlanRiskLaneCandidate",
        "PlanRiskLaneSelection",
        "select_plan_risk_lane_snapshot",
    }:
        return getattr(plan_lint, name)
    raise AttributeError(name)

DEFAULT_TEMPLATE_SCOPE: tuple[Path, ...] = (
    REPO_ROOT / "docs" / "code_reviews" / "_template_merge_range.md",
    REPO_ROOT / "docs" / "code_reviews" / "_template_single_commit.md",
    REPO_ROOT / "docs" / "doc_reviews" / "_template_merge_range.md",
    REPO_ROOT / "docs" / "doc_reviews" / "_template_single_commit.md",
    REPO_ROOT / "docs" / "reviews" / "_template_merge_notes.md",
)
_DEFAULT_TEMPLATE_RELATIVE_PATHS: tuple[str, ...] = tuple(
    path.relative_to(REPO_ROOT).as_posix() for path in DEFAULT_TEMPLATE_SCOPE
)

H1_RE = re.compile(r"^\s*#\s+(?P<title>.+?)\s*$")
H2_RE = re.compile(r"^\s*##\s+(?P<title>.+?)\s*$")
H3_RE = re.compile(r"^\s*###\s+(?P<title>.+?)\s*$")
STATUS_HEADER_RE = re.compile(r"^\*\*Status:\*\*\s*(?P<value>.*?)\s*$", re.IGNORECASE)
REVIEW_HEADER_FIELD_RE = review_header_metadata.HEADER_FIELD_RE
SCHEMA_VERSION_HEADER_RE = re.compile(r"^\s*\*\*Schema version:\*\*\s*(?P<value>.+?)\s*$", re.IGNORECASE)
DATE_HEADER_RE = re.compile(r"^\s*\*\*Date:\*\*\s*(?P<value>.+?)\s*$", re.IGNORECASE)
TARGET_HEADER_RE = re.compile(r"^\s*\*\*Target:\*\*\s*(?P<value>.+?)\s*$", re.IGNORECASE)
SPEC_HEADER_RE = re.compile(r"^\s*\*\*Spec:\*\*\s*(?P<value>.+?)\s*$", re.IGNORECASE)
RANGE_HEADER_RE = re.compile(r"^\s*\*\*Range:\*\*\s*(?P<value>.+?)\s*$", re.IGNORECASE)
ORIGIN_PLAN_RE = re.compile(r"\bPLAN\s*=\s*`?(?P<path>docs/plans/[A-Za-z0-9_./-]+\.md)`?")
PLAN_SPEC_RE = re.compile(r"^`?(?P<path>docs/plans/[A-Za-z0-9_./-]+\.md)`?$")
BLOCKER_TITLE_RE = re.compile(r"^b(?P<num>\d+)(?:\)|\b)")
SPACE_RE = re.compile(r"\s+")
ASSET_PATH_RE = re.compile(r"(?P<path>(?:docs/(?:code_reviews|doc_reviews)/assets|assets)/[^\s`]+?\.(?:png|jpg|jpeg|webp))")
IMAGE_TOKEN_RE = re.compile(r"(?P<path>/?[^\s`]+?\.(?:png|jpg|jpeg|webp))")
LANE_FINDING_RE = re.compile(r"\b(?:risk:R\d+|contracts:C\d+|visual:V\d+)\b", re.IGNORECASE)
CANONICAL_BLOCKER_RE = re.compile(r"\bB\d+\b")
FINAL_OK_STATUS = CODE_DOC_REVIEW_OK_STATUS_NORM
FINAL_BLOCKER_STATUS = CODE_DOC_REVIEW_BLOCKER_STATUS_NORM
FINAL_REVIEW_STATUSES = CODE_DOC_REVIEW_FINAL_STATUS_NORMS
RUSSIAN_FIRST_SUMMARY_PREFIXES = ("ОК:", "Замечания:", "Вердикт:")
MANUAL_NO_ORIGIN_SPEC = "N/A (origin_plan_state=manual_range_review_no_origin_plan)"
SINGLETON_REVIEW_HEADER_LABELS = {
    "date",
    "target",
    "range",
    "spec",
    "schema version",
    "status",
}

RERUN_FIELD_LABELS = ("rerun mode", "baseline artifact")
VISUAL_FIELD_LABELS = ("visual env", "source scenarios", "post-merge visual sanity")
BLOCKER_FIELD_LABELS = ("blocker id", "current state", "classification", "primary owner gap", "evidence refs")
RERUN_SECTION_TITLES = {"контекст rerun", "rerun context"}
VISUAL_SECTION_TITLES = {"визуальные доказательства", "visual evidence"}
RISK_LANE_TITLE_PREFIX = "reviewer_code_risk"
CONTRACTS_LANE_TITLE_PREFIX = "reviewer_code_contracts"
SYNTHESIS_TITLE_PREFIX = "lane synthesis / aggregate verdict"
REQUIRED_CODE_LANE_PREFIXES = (
    (RISK_LANE_TITLE_PREFIX, "reviewer_code_risk"),
    (CONTRACTS_LANE_TITLE_PREFIX, "reviewer_code_contracts"),
)
FINAL_LANE_FIELD_LABELS = ("lane status", "target snapshot", "coverage domains")
FINAL_SYNTHESIS_FIELD_LABELS = ("source lanes", "aggregate status")
SUCCESSFUL_RISK_LANE_STATUSES = {"complete", "no_findings"}
FINAL_SYNTHESIS_PROVENANCE_FIELD_LABELS = (
    "source_lane",
    "lane_finding_id",
    "synthesis_disposition",
    "canonical_ref",
    "audit_status",
    "followup_plan",
)
EXACT_BUNDLE_HYGIENE_SECTION_TITLES = {
    "exact bundle hygiene",
    "exact-bundle hygiene",
    "гигиена exact bundle",
    "гигиена exact-bundle",
}
EXACT_BUNDLE_HYGIENE_FIELD_LABELS = {
    "exact bundle hygiene",
    "exact-bundle hygiene",
    "bundle hygiene",
    "untracked files check",
    "new/untracked files check",
    "untracked hygiene",
}
SMALL_RUNNER_REVIEW_FIELD_ALIASES = {
    "runner_id": "runner_id",
    "coder_runner_id": "runner_id",
    "author_runner_id": "runner_id",
    "runner": "runner_id",
    "reviewer_runner_id": "reviewer_runner_id",
    "review_runner_id": "reviewer_runner_id",
    "reviewer_lane": "reviewer_lane",
    "review_lane": "reviewer_lane",
    "independent_reviewer_lane": "reviewer_lane",
    "runner_result": "runner_result",
    "runner_outcome": "runner_result",
    "small_runner_result": "runner_result",
    "small_runner_success": "small_runner_success",
    "frontier_intervention": "frontier_intervention",
    "runner_admission": "runner_admission",
    "small_model_ready_state": "small_model_ready_state",
}
SMALL_RUNNER_REVIEW_SUCCESS_VALUES = {"true", "yes", "success", "successful", "ok", "passed", "complete", "completed"}
SMALL_RUNNER_REVIEW_FALSE_VALUES = {"false", "no", "failed", "failure", "blocked", "unavailable", "inconclusive"}
SMALL_RUNNER_REVIEW_RED_RE = re.compile(
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
HISTORICAL_RECONCILIATION_MARKERS = (
    "historical anchor",
    "historical-fixed",
    "same review artifact rewritten in place",
    "same review file rewritten in place",
    "previous blocker is closed",
    "previous verdict is closed",
    "superseded",
    "closed by this rerun",
    "rewritten in place",
)
RERUN_RESULT_LINE_RE = re.compile(r"^\s*-\s*rerun result\s*\((?P<meta>[^)]*)\)\s*:\s*(?P<body>.*)$", re.IGNORECASE)
HISTORICAL_DIFF_DISPOSITION_H2 = "Historical diff-check disposition (optional)"
HISTORICAL_DIFF_CANDIDATE_H3 = "Candidate rows"
HISTORICAL_DIFF_TOP_LEVEL_FIELDS = (
    "Raw command",
    "Raw exit",
    "Candidate count",
    "Candidate set SHA-256",
)
HISTORICAL_DIFF_ROW_FIELDS = (
    "range",
    "raw_command",
    "raw_exit",
    "path",
    "line",
    "blob_oid",
    "finding_kind",
    "provenance_ref",
    "provenance_sha256",
    "lifecycle",
    "reason_code",
    "owner",
    "action",
)
HISTORICAL_DIFF_RANGE_TARGET_RE = re.compile(
    r"^RANGE=(?P<range>[0-9a-f]{40}\.\.[0-9a-f]{40})(?:\s+\(EXCLUDE_DOCS=[01]\))?$"
)
HISTORICAL_DIFF_RAW_FINDING_RE = re.compile(
    r"^(?P<path>.+):(?P<line>[1-9][0-9]*): (?P<message>trailing whitespace\.|new blank line at EOF\.)$"
)
HISTORICAL_DIFF_APPROVAL_RE = re.compile(
    r"^Historical disposition approval: state=accepted range=(?P<range>[0-9a-f]{40}\.\.[0-9a-f]{40}) "
    r"raw_exit=(?P<raw_exit>[0-9]+) candidate_set_sha256=(?P<digest>[0-9a-f]{64})$"
)
HISTORICAL_DIFF_APPROVAL_SECTION = "архитектурное ревью"
HISTORICAL_DIFF_ALLOWED_FINDING_KINDS = {"trailing_whitespace", "blank_line_at_eof"}
HISTORICAL_DIFF_ALLOWED_REASON_CODES = {
    "intentional_markdown_hard_break",
    "immutable_support_payload_selected_current",
    "immutable_support_payload_historical_or_superseded",
}
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
COMMAND_EVIDENCE_LINE_MARKERS = (
    "command",
    "commands_run",
    "команд",
    "gate",
    "verification",
    "evidence",
    "-> exit",
)


@dataclass(frozen=True)
class Finding:
    rel_path: str
    line_no: int
    code: str
    message: str

    def render(self) -> str:
        return f"{self.rel_path}:{self.line_no}: {self.code}: {self.message}"


@dataclass(frozen=True)
class RuntimeUiVisualEvidenceReadback:
    state: str
    reason_codes: tuple[str, ...]
    current_asset_refs: tuple[str, ...]
    mandatory_modes: tuple[str, ...]
    comparator_result: str
    design_verdict: str
    review_path: str
    origin_plan: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "reason_codes": list(self.reason_codes),
            "current_asset_refs": list(self.current_asset_refs),
            "mandatory_modes": list(self.mandatory_modes),
            "comparator_result": self.comparator_result,
            "design_verdict": self.design_verdict,
            "review_path": self.review_path,
            "origin_plan": self.origin_plan,
        }


@dataclass(frozen=True)
class ReviewArtifact:
    path: Path
    rel_path: str
    lines: tuple[str, ...]
    first_heading: str | None
    is_code_review: bool
    is_merge_notes: bool


@dataclass(frozen=True)
class BlockerBlock:
    blocker_id: str
    line_no: int
    lines: tuple[tuple[int, str], ...]


@dataclass(frozen=True)
class SectionBlock:
    title: str
    line_no: int
    lines: tuple[tuple[int, str], ...]


@dataclass(frozen=True)
class SameFileRerunCloseout:
    state: str
    line_no: int
    reason: str


@dataclass(frozen=True)
class HistoricalDiffCheckReadback:
    state: str
    as_status: str
    range_value: str | None
    raw_command: str | None
    raw_exit: int | None
    finding_count: int
    candidate_count: int | None
    candidate_set_sha256: str | None
    approval_state: str
    issues: tuple[Finding, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "as_status": self.as_status,
            "range": self.range_value,
            "raw_command": self.raw_command,
            "raw_exit": self.raw_exit,
            "finding_count": self.finding_count,
            "candidate_count": self.candidate_count,
            "candidate_set_sha256": self.candidate_set_sha256,
            "approval_state": self.approval_state,
            "issues": [
                {"code": finding.code, "path": finding.rel_path, "line": finding.line_no}
                for finding in self.issues
            ],
        }


def _normalize_text(value: str) -> str:
    return SPACE_RE.sub(" ", value.lower()).strip()


def _normalize_literal(value: str) -> str:
    return SPACE_RE.sub(" ", value.replace("`", "").strip()).strip()


def _relative_path(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _first_heading(lines: Sequence[str]) -> str | None:
    for line in lines:
        match = H1_RE.match(line)
        if match:
            return _normalize_text(match.group("title"))
    return None


def _is_guarded_review_artifact(artifact: ReviewArtifact) -> bool:
    # Guards follow the carrier (code/doc review, not a template), never the filename date.
    if artifact.path.name.startswith("_template_"):
        return False
    return "code_reviews" in artifact.path.parts or "doc_reviews" in artifact.path.parts


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
    if any(marker in key_text for marker in COMMAND_EVIDENCE_KEY_MARKERS):
        return True
    return _looks_like_command(value)


def _iter_homebrew_command_payload_paths(value: Any, key_path: Sequence[str] = ()) -> Iterable[str]:
    if isinstance(value, dict):
        for key, nested in value.items():
            key_str = str(key)
            yield from _iter_homebrew_command_payload_paths(nested, (*key_path, key_str))
        return
    if isinstance(value, list):
        for index, nested in enumerate(value):
            yield from _iter_homebrew_command_payload_paths(nested, (*key_path, str(index)))
        return
    if not isinstance(value, str):
        return
    if HOMEBREW_PYTHON_LITERAL not in value:
        return
    if not _is_command_evidence_path(key_path, value):
        return
    yield ".".join(key_path) or "<root>"


def _line_is_homebrew_command_evidence(line: str) -> bool:
    if HOMEBREW_PYTHON_LITERAL not in line:
        return False
    lower = line.casefold()
    if any(marker in lower for marker in RAW_DIAGNOSTIC_KEY_MARKERS):
        return False
    if any(marker in lower for marker in COMMAND_EVIDENCE_LINE_MARKERS):
        return True
    stripped = line.strip()
    while stripped.startswith("- "):
        stripped = stripped[2:].strip()
    return _looks_like_command(stripped)


def _lint_homebrew_command_evidence_lines(artifact: ReviewArtifact) -> list[Finding]:
    if artifact.path.name.startswith("_template_"):
        return []
    if not artifact.is_code_review and not artifact.is_merge_notes and "doc_reviews" not in artifact.path.parts:
        return []
    review_status, _ = _review_status(artifact)
    if review_status not in FINAL_REVIEW_STATUSES and review_status not in MERGE_NOTES_STATUS_NORMS:
        return []
    findings: list[Finding] = []
    for line_no, line in enumerate(artifact.lines, start=1):
        if not _line_is_homebrew_command_evidence(line):
            continue
        findings.append(
            Finding(
                rel_path=artifact.rel_path,
                line_no=line_no,
                code=HOMEBREW_COMMAND_EVIDENCE_CODE,
                message=(
                    "Committed review/plan evidence must spell interpreter commands portably "
                    "(`$PYBIN ...` or `python3 ...`), not with an expanded owner-local Homebrew path."
                ),
            )
        )
    return findings


def _detect_code_review(path: Path, first_heading: str | None) -> bool:
    if "code_reviews" in path.parts:
        return True
    if first_heading is None:
        return False
    return first_heading.startswith("code review")


def _detect_merge_notes(path: Path, first_heading: str | None) -> bool:
    if path.name == "_template_merge_notes.md":
        return True
    if "_merge_notes_" in path.name:
        return True
    if first_heading is None:
        return False
    return "merge notes" in first_heading


def _normalize_field_label(line: str) -> str | None:
    normalized = line.replace("`", "").strip()
    while normalized.startswith("- "):
        normalized = normalized[2:].strip()
    if ":" not in normalized:
        return None
    label = normalized.split(":", 1)[0].strip()
    if not label:
        return None
    return _normalize_text(label)


def _field_locations(lines: Iterable[tuple[int, str]]) -> dict[str, int]:
    locations: dict[str, int] = {}
    for line_no, line in lines:
        label = _normalize_field_label(line)
        if label is None:
            continue
        locations.setdefault(label, line_no)
    return locations


def _field_values(lines: Iterable[tuple[int, str]]) -> dict[str, str]:
    values: dict[str, str] = {}
    for _, line in lines:
        label = _normalize_field_label(line)
        if label is None or ":" not in line:
            continue
        value = line.split(":", 1)[1].strip()
        values.setdefault(label, value.strip("`").strip())
    return values


def _first_summary_line(artifact: ReviewArtifact) -> tuple[int, str | None]:
    for line_no, line in enumerate(artifact.lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if H1_RE.match(line):
            continue
        if H2_RE.match(line) or H3_RE.match(line):
            return line_no, None
        if stripped.startswith(">"):
            continue
        if stripped.startswith("**") and ":**" in stripped:
            continue
        return line_no, stripped
    return 1, None


def _has_exact_bundle_hygiene_receipt(section_blocks: Sequence[SectionBlock]) -> bool:
    for section in section_blocks:
        if section.title in EXACT_BUNDLE_HYGIENE_SECTION_TITLES:
            return True
        section_fields = _field_locations(section.lines)
        if any(label in section_fields for label in EXACT_BUNDLE_HYGIENE_FIELD_LABELS):
            return True
    return False


def _extract_review_header_lines(lines: Sequence[str]) -> list[tuple[int, str]]:
    return [
        (line_no, raw_line)
        for line_no, _label, _value, raw_line in review_header_metadata.extract_header_fields(lines)
    ]


def _header_value(lines: Sequence[str], matcher: re.Pattern[str]) -> tuple[str | None, int]:
    matches: list[tuple[int, str]] = []
    for line_no, line in _extract_review_header_lines(lines):
        match = matcher.match(line)
        if match:
            matches.append((line_no, match.group("value").strip()))
    if len(matches) == 1:
        line_no, value = matches[0]
        return value, line_no
    if len(matches) > 1:
        return None, matches[1][0]
    return None, 1


def _duplicate_review_header_field_findings(artifact: ReviewArtifact) -> list[Finding]:
    return [
        Finding(
            rel_path=artifact.rel_path,
            line_no=line_no,
            code="duplicate_review_header_field",
            message=f"Review metadata field `{label}` must appear exactly once in the header preamble.",
        )
        for line_no, label in review_header_metadata.duplicate_singleton_fields(
            artifact.lines,
            tuple(sorted(SINGLETON_REVIEW_HEADER_LABELS)),
        )
    ]


def _noncanonical_review_header_field_findings(artifact: ReviewArtifact) -> list[Finding]:
    findings: list[Finding] = []
    for label in sorted(SINGLETON_REVIEW_HEADER_LABELS):
        values = review_header_metadata.header_values(artifact.lines, label)
        if len(values) != 1:
            continue
        value, line_no = review_header_metadata.singleton_header_value(artifact.lines, label)
        if value is not None:
            continue
        findings.append(
            Finding(
                rel_path=artifact.rel_path,
                line_no=line_no,
                code="noncanonical_review_header_field",
                message=f"Review metadata field `{label}` must use canonical `**Label:**` spelling without label whitespace drift.",
            )
        )
    return findings


def _extract_schema_version_lines(lines: Sequence[str]) -> list[tuple[int, str]]:
    matches: list[tuple[int, str]] = []
    for line_no, line in _extract_review_header_lines(lines):
        match = SCHEMA_VERSION_HEADER_RE.match(line)
        if not match:
            continue
        matches.append((line_no, match.group("value").strip()))
    return matches


def _extract_status_lines(lines: Sequence[str]) -> list[tuple[int, str]]:
    matches: list[tuple[int, str]] = []
    for line_no, line in _extract_review_header_lines(lines):
        match = STATUS_HEADER_RE.match(line)
        if match:
            matches.append((line_no, match.group("value").strip()))
    return matches


def _normalize_schema_version(value: str) -> str:
    return SPACE_RE.sub(" ", value.replace("`", "").lower()).strip()


def _heading_locations(lines: Sequence[str], matcher: re.Pattern[str]) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for line_no, line in enumerate(lines, start=1):
        match = matcher.match(line)
        if match:
            found.append((line_no, _normalize_text(match.group("title"))))
    return found


def _iter_h2_blocks(artifact: ReviewArtifact) -> list[SectionBlock]:
    blocks: list[SectionBlock] = []
    current_title: str | None = None
    current_line_no: int | None = None
    current_lines: list[tuple[int, str]] = []

    def flush() -> None:
        nonlocal current_title, current_line_no, current_lines
        if current_title is None or current_line_no is None:
            current_lines = []
            return
        blocks.append(SectionBlock(title=current_title, line_no=current_line_no, lines=tuple(current_lines)))
        current_title = None
        current_line_no = None
        current_lines = []

    for line_no, line in enumerate(artifact.lines, start=1):
        h2_match = H2_RE.match(line)
        if h2_match:
            flush()
            current_title = _normalize_text(h2_match.group("title"))
            current_line_no = line_no
            continue
        if current_title is not None:
            current_lines.append((line_no, line))

    flush()
    return blocks


def _section_lines(lines: Sequence[str], section_titles: set[str]) -> list[tuple[int, str]]:
    collected: list[tuple[int, str]] = []
    current_h2: str | None = None
    for line_no, line in enumerate(lines, start=1):
        h2_match = H2_RE.match(line)
        if h2_match:
            current_h2 = _normalize_text(h2_match.group("title"))
            continue
        if current_h2 in section_titles:
            collected.append((line_no, line))
    return collected


def _artifact_repo_root(path: Path) -> Path:
    for parent in path.parents:
        if parent.name == "docs":
            return parent.parent
    return path.parent


def _is_visual_asset_guidance_line(line: str) -> bool:
    lower = line.lower()
    return (
        "store in:" in lower
        or "list here" in lower
        or "prefer relative paths like" in lower
        or "use one exact literal path per screenshot" in lower
        or "add at least 1 screenshot per mode" in lower
    )


def _visual_asset_paths(line: str) -> tuple[str, ...]:
    return tuple(match.group("path") for match in ASSET_PATH_RE.finditer(line))


def _image_like_tokens(line: str) -> tuple[str, ...]:
    return tuple(match.group("path") for match in IMAGE_TOKEN_RE.finditer(line))


def _resolve_visual_asset_path(artifact: ReviewArtifact, raw_path: str) -> Path:
    if raw_path.startswith("assets/"):
        return (artifact.path.parent / raw_path).resolve()
    return (_artifact_repo_root(artifact.path) / raw_path).resolve()


def _is_placeholder_asset_path(raw_path: str) -> bool:
    return "<" in raw_path or ">" in raw_path


def _iter_visual_asset_refs(artifact: ReviewArtifact) -> list[tuple[int, str]]:
    refs: list[tuple[int, str]] = []
    for line_no, line in _section_lines(artifact.lines, VISUAL_SECTION_TITLES):
        if _is_visual_asset_guidance_line(line):
            continue
        raw_paths = _visual_asset_paths(line)
        image_like_tokens = _image_like_tokens(line)
        if not raw_paths:
            if image_like_tokens or ("<path>" in line.lower() and "proves:" in line.lower()):
                refs.append((line_no, ""))
            continue
        if len(raw_paths) != 1 or "<path>" in line.lower():
            refs.append((line_no, ""))
            continue
        if len(image_like_tokens) != 1 or image_like_tokens[0] != raw_paths[0]:
            refs.append((line_no, ""))
            continue
        refs.append((line_no, raw_paths[0]))
    return refs


def _visual_evidence_field_rows(artifact: ReviewArtifact) -> list[tuple[int, str, str]]:
    rows: list[tuple[int, str, str]] = []
    for line_no, line in _section_lines(artifact.lines, VISUAL_SECTION_TITLES):
        stripped = line.strip()
        while stripped.startswith(("- ", "* ")):
            stripped = stripped[2:].strip()
        if ":" not in stripped:
            continue
        raw_label, raw_value = stripped.split(":", 1)
        label = _normalize_text(raw_label.replace("`", "").replace("*", ""))
        value = raw_value.strip().strip("`").strip()
        rows.append((line_no, label, value))
    return rows


def _visual_evidence_values(artifact: ReviewArtifact) -> tuple[dict[str, str], list[tuple[int, str, str]]]:
    rows = _visual_evidence_field_rows(artifact)
    values: dict[str, str] = {}
    for _line_no, label, value in rows:
        values.setdefault(label, value)
    return values, rows


def _origin_plan_from_review(
    *, project_root: Path, artifact: ReviewArtifact, origin_plan: str | Path | None
) -> Path | None:
    if origin_plan is not None:
        candidate = Path(origin_plan)
        return candidate if candidate.is_absolute() else project_root / candidate
    raw_spec, _line_no = _header_value(artifact.lines, SPEC_HEADER_RE)
    if raw_spec is None:
        return None
    match = PLAN_SPEC_RE.match(raw_spec.strip())
    if match is None:
        return None
    return project_root / match.group("path")


def _canonical_visual_asset_ref(raw_path: str) -> str:
    value = raw_path.strip().strip("`").strip()
    if value.startswith("assets/"):
        return f"docs/code_reviews/{value}"
    return value


def _path_has_symlink(root: Path, path: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def evaluate_runtime_ui_visual_evidence(
    *,
    project_root: str | Path,
    review_path: str | Path,
    origin_plan: str | Path | None = None,
    review_text: str | None = None,
) -> RuntimeUiVisualEvidenceReadback:
    """Return the single reusable runtime-UI visual closure classification."""
    root = Path(project_root).resolve()
    path = Path(review_path)
    if not path.is_absolute():
        path = root / path
    rel_review = _relative_path(root, path.resolve())
    if review_text is None:
        if not path.is_file():
            return RuntimeUiVisualEvidenceReadback(
                state="ambiguous",
                reason_codes=("missing_review_artifact",),
                current_asset_refs=(),
                mandatory_modes=(),
                comparator_result="missing",
                design_verdict="missing",
                review_path=rel_review,
                origin_plan=None,
            )
        review_text = path.read_text(encoding="utf-8", errors="replace")
    artifact = review_artifact_from_text(root, path, review_text)
    plan_path = _origin_plan_from_review(project_root=root, artifact=artifact, origin_plan=origin_plan)
    if plan_path is None:
        return RuntimeUiVisualEvidenceReadback(
            state="not_applicable",
            reason_codes=("no_materialized_visual_lane_contract",),
            current_asset_refs=(),
            mandatory_modes=(),
            comparator_result="not_applicable",
            design_verdict="not_applicable",
            review_path=rel_review,
            origin_plan=None,
        )
    if not plan_path.is_file():
        return RuntimeUiVisualEvidenceReadback(
            state="ambiguous",
            reason_codes=("missing_origin_plan",),
            current_asset_refs=(),
            mandatory_modes=(),
            comparator_result="missing",
            design_verdict="missing",
            review_path=rel_review,
            origin_plan=_relative_path(root, plan_path.resolve()),
        )
    plan_text = plan_path.read_text(encoding="utf-8", errors="replace")
    if not any(line.strip() == "## Review visual lane contract" for line in plan_text.splitlines()):
        return RuntimeUiVisualEvidenceReadback(
            state="not_applicable",
            reason_codes=("no_materialized_visual_lane_contract",),
            current_asset_refs=(),
            mandatory_modes=(),
            comparator_result="not_applicable",
            design_verdict="not_applicable",
            review_path=rel_review,
            origin_plan=_relative_path(root, plan_path.resolve()),
        )
    contract, contract_errors = review_visual_lane_contract.parse_materialized_contract(
        plan_text,
        project_root=root,
        expected_plan_ref=_relative_path(root, plan_path.resolve()),
        expected_range_identity=review_visual_lane_contract.review_target_identity(plan_text),
        require_review_target_identity=True,
    )
    if contract is None or contract_errors:
        return RuntimeUiVisualEvidenceReadback(
            state="ambiguous",
            reason_codes=tuple(contract_errors or ("invalid_materialized_visual_lane_contract",)),
            current_asset_refs=(),
            mandatory_modes=(),
            comparator_result="missing",
            design_verdict="missing",
            review_path=rel_review,
            origin_plan=_relative_path(root, plan_path.resolve()),
        )
    state = str(contract["availability_state"])
    if state == "not_applicable":
        return RuntimeUiVisualEvidenceReadback(
            state="not_applicable",
            reason_codes=(str(contract["reason"]),),
            current_asset_refs=(),
            mandatory_modes=(),
            comparator_result="not_applicable",
            design_verdict="not_applicable",
            review_path=rel_review,
            origin_plan=_relative_path(root, plan_path.resolve()),
        )
    if state != "available":
        return RuntimeUiVisualEvidenceReadback(
            state="red" if state in {"missing", "malformed"} else "ambiguous",
            reason_codes=(f"visual_lane_{state}", str(contract["reason"])),
            current_asset_refs=(),
            mandatory_modes=tuple(str(mode) for mode in contract["mandatory_modes"]),
            comparator_result="missing",
            design_verdict="missing",
            review_path=rel_review,
            origin_plan=_relative_path(root, plan_path.resolve()),
        )

    values, rows = _visual_evidence_values(artifact)
    reasons: list[str] = []
    ambiguous: list[str] = []
    single_value_labels = {
        "comparator command",
        "comparator claim",
        "comparator result",
        "capture status",
        "complete index inspected",
        "design verdict",
        "finding dispositions",
        "mandatory modes",
        *(f"human index ({mode})" for mode in contract["mandatory_modes"]),
    }
    for label in single_value_labels:
        if sum(1 for _line_no, row_label, _value in rows if row_label == label) > 1:
            ambiguous.append(f"duplicate_visual_field:{label}")
    comparator_result = _normalize_literal(values.get("comparator result", "")).lower()
    design_verdict = _normalize_literal(values.get("design verdict", "")).lower()
    if _normalize_literal(values.get("comparator command", "")) != str(contract["comparator_command"]):
        reasons.append("comparator_command_mismatch")
    if _normalize_literal(values.get("comparator claim", "")).lower() != "mechanical":
        reasons.append("missing_mechanical_comparator_claim")
    if comparator_result != "pass":
        reasons.append("comparator_not_pass")
    if _normalize_literal(values.get("capture status", "")).lower() != "complete":
        reasons.append("capture_status_not_complete")
    if _normalize_literal(values.get("complete index inspected", "")).lower() not in {"yes", "true", "complete"}:
        reasons.append("complete_index_not_inspected")
    if design_verdict not in {"no_findings", "findings"}:
        reasons.append("missing_design_verdict")
    if design_verdict == "findings":
        dispositions = values.get("finding dispositions", "")
        if not re.search(r"status=(?:closed|deferred)\b", dispositions) or not re.search(
            r"reference=[^\s,;]+", dispositions
        ):
            reasons.append("nonterminal_visual_findings")

    mandatory_modes = tuple(str(mode) for mode in contract["mandatory_modes"])
    declared_modes = {
        token.strip()
        for token in re.split(r"[,;+]", _normalize_literal(values.get("mandatory modes", "")))
        if token.strip()
    }
    if declared_modes != set(mandatory_modes):
        reasons.append("mandatory_modes_mismatch")
    for mode in mandatory_modes:
        expected_index = str(contract["human_index_paths_by_mode"][mode])
        if _normalize_literal(values.get(f"human index ({mode})", "")) != expected_index:
            reasons.append(f"human_index_mismatch:{mode}")

    expected_root_rel = f"docs/code_reviews/assets/{path.stem}/"
    if str(contract["durable_review_asset_root"]) != expected_root_rel:
        ambiguous.append("current_review_asset_root_mismatch")
    expected_root = (root / expected_root_rel).resolve()
    asset_refs: list[str] = []
    for mode in mandatory_modes:
        candidates = [value for _line_no, label, value in rows if label == f"durable asset ({mode})"]
        if not candidates:
            reasons.append(f"missing_durable_asset:{mode}")
            continue
        valid_for_mode = False
        for raw_path in candidates:
            canonical = _canonical_visual_asset_ref(raw_path)
            raw_obj = Path(canonical)
            if raw_obj.is_absolute() or ".." in raw_obj.parts or canonical.startswith(".tmp/"):
                ambiguous.append(f"unsafe_durable_asset_ref:{mode}")
                continue
            candidate = root / raw_obj
            try:
                candidate.resolve().relative_to(expected_root)
            except (OSError, ValueError):
                ambiguous.append(f"other_review_asset_ref:{mode}")
                continue
            if _path_has_symlink(expected_root, candidate):
                ambiguous.append(f"symlink_durable_asset:{mode}")
                continue
            if not candidate.is_file():
                reasons.append(f"missing_durable_asset_file:{mode}")
                continue
            if candidate.stat().st_size <= 0:
                reasons.append(f"empty_durable_asset_file:{mode}")
                continue
            valid_for_mode = True
            asset_refs.append(canonical)
        if not valid_for_mode and not any(reason.endswith(f":{mode}") for reason in reasons + ambiguous):
            reasons.append(f"missing_durable_asset:{mode}")

    final_state = "ambiguous" if ambiguous else ("red" if reasons else "green")
    return RuntimeUiVisualEvidenceReadback(
        state=final_state,
        reason_codes=tuple(dict.fromkeys((*ambiguous, *reasons))),
        current_asset_refs=tuple(dict.fromkeys(asset_refs)),
        mandatory_modes=mandatory_modes,
        comparator_result=comparator_result or "missing",
        design_verdict=design_verdict or "missing",
        review_path=rel_review,
        origin_plan=_relative_path(root, plan_path.resolve()),
    )


def evaluate_review_range_semantic_provenance(
    *,
    project_root: str | Path,
    review_path: str | Path,
    origin_plan: str | Path | None = None,
    review_text: str | None = None,
) -> tuple[str, ...]:
    """Cross-read the optional source receipt through existing public parsers.

    The receipt is audit data.  This checker neither selects a route nor
    parses policy: it only rejects disagreement between its canonical
    plan/range/visual facts and the existing visual-contract parser.
    """

    root = Path(project_root).resolve()
    path = Path(review_path)
    if not path.is_absolute():
        path = root / path
    if review_text is None:
        try:
            review_text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ()
    artifact = review_artifact_from_text(root, path, review_text)
    plan_path = _origin_plan_from_review(project_root=root, artifact=artifact, origin_plan=origin_plan)
    if plan_path is None or not plan_path.is_file():
        return ()
    try:
        plan_text = plan_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ()
    receipt, receipt_error = plan_lint.parse_review_range_semantic_provenance(plan_text.splitlines())
    if receipt is None and receipt_error is None:
        return ()
    if receipt_error or receipt is None:
        return ("review_range_provenance_invalid",)
    shape_error = plan_lint._review_range_semantic_provenance_shape_error(receipt)
    if shape_error is not None:
        return ("review_range_provenance_invalid",)
    if receipt.get("schema_version") not in {
        plan_lint._REVIEW_RANGE_PROVENANCE_V1,
        plan_lint._REVIEW_RANGE_PROVENANCE_V2,
    }:
        return ("review_range_provenance_invalid",)
    plan_ref = _relative_path(root, plan_path.resolve())
    outputs = receipt.get("outputs")
    if not isinstance(outputs, list) or not any(
        isinstance(row, Mapping) and row.get("artifact") == "plan" and row.get("section_or_path") == plan_ref
        for row in outputs
    ):
        return ("review_range_provenance_plan_ref_mismatch",)
    identity = review_visual_lane_contract.review_target_identity(plan_text)
    if identity is None:
        return ("review_range_provenance_range_missing",)
    spec_match = SPEC_HEADER_RE.search(review_text)
    if spec_match is not None:
        spec = PLAN_SPEC_RE.match(spec_match.group("value").strip())
        if spec is None or spec.group("path") != plan_ref:
            return ("review_range_provenance_spec_mismatch",)
    target_match = re.search(
        r"(?m)^\*\*Target:\*\*\s*`?RANGE=([0-9a-f]{40})\.\.([0-9a-f]{40}) \(EXCLUDE_DOCS=([01])\)`?\s*$",
        review_text,
    )
    if target_match is not None and identity != (
        target_match.group(1), target_match.group(2), int(target_match.group(3))
    ):
        return ("review_range_provenance_range_mismatch",)
    visual = receipt.get("visual_contract_ref_or_inline_digest")
    if not isinstance(visual, Mapping):
        return ("review_range_provenance_visual_missing",)
    contract, errors = review_visual_lane_contract.parse_materialized_contract(
        plan_text,
        project_root=root,
        expected_plan_ref=plan_ref,
        expected_range_identity=identity,
        require_review_target_identity=True,
    )
    if contract is None or errors:
        return ("review_range_provenance_visual_mismatch",)
    if visual.get("kind") == "external_ref":
        refs, ref_errors = review_visual_lane_contract.referenced_full_payload_refs(plan_text)
        if ref_errors or len(refs) != 1 or visual.get("ref") != refs[0]:
            return ("review_range_provenance_visual_mismatch",)
        support = root / refs[0]
        try:
            digest = hashlib.sha256(support.read_bytes()).hexdigest()
        except OSError:
            return ("review_range_provenance_visual_mismatch",)
        if visual.get("sha256") != digest:
            return ("review_range_provenance_visual_mismatch",)
    elif visual.get("kind") == "inline_digest":
        digest = hashlib.sha256(
            review_visual_lane_contract.render_materialized_contract(contract).encode("utf-8")
        ).hexdigest()
        if visual.get("sha256") != digest:
            return ("review_range_provenance_visual_mismatch",)
    else:
        return ("review_range_provenance_visual_missing",)
    return ()


def _default_template_scope(
    root: Path,
    context: ContractContext,
) -> tuple[Path, ...]:
    if context.state != "engaged":
        # Keep the historical tooling-owned default for legacy callers.
        return DEFAULT_TEMPLATE_SCOPE
    return tuple(
        require_declared_read(context, relative_path, purpose="review artifact template")
        for relative_path in _DEFAULT_TEMPLATE_RELATIVE_PATHS
    )


def _expand_paths(
    root: Path,
    raw_paths: Sequence[str],
    *,
    context: ContractContext,
) -> list[Path]:
    candidates = list(_default_template_scope(root, context) if not raw_paths else ())
    seen: set[Path] = set()

    def add_path(path: Path) -> None:
        resolved = path.resolve()
        if resolved in seen:
            return
        seen.add(resolved)
        candidates.append(resolved)

    for raw in raw_paths:
        path = Path(raw)
        if not path.is_absolute():
            path = root / path
        if not path.exists():
            raise FileNotFoundError(f"Missing review artifact path: {path}")
        if path.is_dir():
            for child in sorted(path.rglob("*.md")):
                add_path(child)
            continue
        add_path(path)

    return candidates


def review_artifact_from_text(project_root: Path, path: Path, text: str) -> ReviewArtifact:
    """Build one review artifact from an already captured filesystem snapshot."""
    root = project_root.resolve()
    resolved_path = path.resolve()
    lines = tuple(text.splitlines())
    first_heading = _first_heading(lines)
    return ReviewArtifact(
        path=resolved_path,
        rel_path=_relative_path(root, resolved_path),
        lines=lines,
        first_heading=first_heading,
        is_code_review=_detect_code_review(resolved_path, first_heading),
        is_merge_notes=_detect_merge_notes(resolved_path, first_heading),
    )


def load_review_artifacts(
    project_root: Path,
    raw_paths: Sequence[str] | None = None,
    *,
    context: ContractContext | None = None,
) -> list[ReviewArtifact]:
    root = project_root.resolve()
    resolved_context = context_for_reader(root, context=context)
    raw_paths = [] if raw_paths is None else list(raw_paths)
    artifacts: list[ReviewArtifact] = []
    use_declared_templates = resolved_context.state == "engaged" and not raw_paths
    for path in _expand_paths(root, raw_paths, context=resolved_context):
        if use_declared_templates:
            try:
                relative_path = path.resolve().relative_to(resolved_context.contract_root).as_posix()
            except ValueError as exc:  # pragma: no cover - require_declared_read already enforces this.
                raise ValueError(f"Declared review template escapes contract root: {path}") from exc
            text = read_declared_text(
                resolved_context,
                relative_path,
                purpose="review artifact template",
            )
        else:
            # Explicit review artifacts are project evidence, not manifest-only
            # authority content.
            text = path.read_text(encoding="utf-8", errors="replace")
        artifacts.append(review_artifact_from_text(root, path, text))
    return artifacts


def classify_review_schema_version(artifact: ReviewArtifact) -> tuple[str, list[Finding]]:
    findings: list[Finding] = []
    if not artifact.is_merge_notes:
        return "n/a", findings

    matches = _extract_schema_version_lines(artifact.lines)
    if len(matches) > 1:
        line_nos = ", ".join(str(line_no) for line_no, _ in matches)
        findings.append(
            Finding(
                rel_path=artifact.rel_path,
                line_no=matches[0][0],
                code="multiple_schema_version_headers",
                message=f"Multiple `**Schema version:**` header lines found ({line_nos}). Keep one canonical top-level carrier.",
            )
        )
        return "unsupported", findings

    if not matches:
        if artifact.path.name == "_template_merge_notes.md":
            findings.append(
                Finding(
                    rel_path=artifact.rel_path,
                    line_no=1,
                    code="missing_schema_version",
                    message="Missing `**Schema version:** review.v1` on the canonical merge-notes template. "
                    "Versionless non-template merge notes are tolerated only as legacy compatibility carriers.",
                )
            )
            return "unsupported", findings
        return "legacy", findings

    line_no, raw_value = matches[0]
    normalized = _normalize_schema_version(raw_value)
    if normalized != CURRENT_REVIEW_SCHEMA_VERSION:
        findings.append(
            Finding(
                rel_path=artifact.rel_path,
                line_no=line_no,
                code="unsupported_schema_version",
                message=(
                    f"Unsupported review schema version {raw_value!r}; current={CURRENT_REVIEW_SCHEMA_VERSION!r}, "
                    "versionless historical merge notes are the only legacy lane in v1."
                ),
            )
        )
        return "unsupported", findings

    return "current", findings


def _claims_rerun_context(artifact: ReviewArtifact, file_fields: dict[str, int], h2_sections: dict[str, int]) -> tuple[bool, int]:
    explicit_rerun = any(label in file_fields for label in RERUN_FIELD_LABELS) or any(
        title in h2_sections for title in RERUN_SECTION_TITLES
    )
    if explicit_rerun:
        for title in RERUN_SECTION_TITLES:
            if title in h2_sections:
                return True, h2_sections[title]
        for label in RERUN_FIELD_LABELS:
            if label in file_fields:
                return True, file_fields[label]
    if not artifact.is_code_review:
        return False, 1

    if artifact.first_heading and "merge-range" in artifact.first_heading:
        return True, 1
    if "_reviewer_range_" in artifact.path.name:
        return True, 1
    for line_no, line in enumerate(artifact.lines, start=1):
        lower = line.lower()
        if "**target:**" in lower and "range=" in lower:
            return True, line_no
        if "**range:**" in lower:
            return True, line_no
        if "**review target:**" in lower and "range=" in lower:
            return True, line_no
    return False, 1


def _merge_range_anchor(artifact: ReviewArtifact) -> int | None:
    if not artifact.is_code_review:
        return None
    if artifact.first_heading and "merge-range" in artifact.first_heading:
        return 1
    if "_reviewer_range_" in artifact.path.name:
        return 1
    for line_no, line in enumerate(artifact.lines, start=1):
        lower = line.lower()
        if "**target:**" in lower and "range=" in lower:
            return line_no
        if "**range:**" in lower:
            return line_no
        if "**review target:**" in lower and "range=" in lower:
            return line_no
    return None


def _visual_receipt_requirements(
    artifact: ReviewArtifact,
    file_fields: dict[str, int],
    h2_sections: dict[str, int],
    claims_rerun: bool,
) -> tuple[tuple[str, ...], int]:
    del claims_rerun
    visual_anchor = next((h2_sections[title] for title in VISUAL_SECTION_TITLES if title in h2_sections), None)
    merge_range_anchor = _merge_range_anchor(artifact)
    visual_fields_present = tuple(label for label in VISUAL_FIELD_LABELS if label in file_fields)
    if not artifact.is_code_review:
        return (), 1
    if visual_anchor is None and not visual_fields_present:
        return (), 1
    anchor = visual_anchor
    if anchor is None:
        for label in visual_fields_present:
            anchor = file_fields[label]
            break
    if merge_range_anchor is None:
        return ("visual env",), anchor or 1
    return VISUAL_FIELD_LABELS, anchor or merge_range_anchor


def _iter_blocker_blocks(artifact: ReviewArtifact) -> list[BlockerBlock]:
    blocks: list[BlockerBlock] = []
    current_h2: str | None = None
    current_title: str | None = None
    current_line_no: int | None = None
    current_lines: list[tuple[int, str]] = []

    def flush() -> None:
        nonlocal current_title, current_line_no, current_lines
        if current_title is None or current_line_no is None:
            current_lines = []
            return
        blocks.append(BlockerBlock(blocker_id=current_title, line_no=current_line_no, lines=tuple(current_lines)))
        current_title = None
        current_line_no = None
        current_lines = []

    for line_no, line in enumerate(artifact.lines, start=1):
        h2_match = H2_RE.match(line)
        if h2_match:
            flush()
            current_h2 = _normalize_text(h2_match.group("title"))
            continue

        h3_match = H3_RE.match(line)
        if h3_match:
            flush()
            if current_h2 != "s1 blocker":
                continue
            normalized_title = _normalize_text(h3_match.group("title"))
            blocker_match = BLOCKER_TITLE_RE.match(normalized_title)
            if blocker_match is None:
                continue
            current_title = f"B{blocker_match.group('num')}"
            current_line_no = line_no
            continue

        if current_title is not None:
            current_lines.append((line_no, line))

    flush()
    return blocks


def _review_status(artifact: ReviewArtifact) -> tuple[str | None, int]:
    matches = _extract_status_lines(artifact.lines)
    if not matches:
        return None, 1
    if len(matches) != 1:
        return None, matches[1][0]
    line_no, raw_value = matches[0]
    return normalize_review_status(raw_value), line_no


def _status_is_placeholder(value: str | None) -> bool:
    return value is not None and "|" in value


def _validate_status_family(artifact: ReviewArtifact, status: str | None, line_no: int) -> Finding | None:
    if status is None:
        return None
    if _status_is_placeholder(status):
        if artifact.path.name.startswith("_template_"):
            return None
        return Finding(
            rel_path=artifact.rel_path,
            line_no=line_no,
            code="invalid_review_status_family",
            message=(
                "Review artifact status placeholders are only valid in `_template_*` files; "
                "non-template artifacts must choose one status literal for their carrier."
            ),
        )
    if artifact.is_merge_notes:
        if status not in MERGE_NOTES_STATUS_NORMS:
            return Finding(
                rel_path=artifact.rel_path,
                line_no=line_no,
                code="invalid_review_status_family",
                message="Merge notes status must be one of `Draft` or `✅ Done`; code/doc review verdict statuses do not belong here.",
            )
        return None
    if not _is_guarded_review_artifact(artifact):
        return None
    if status not in CODE_DOC_REVIEW_STATUS_NORMS:
        return Finding(
            rel_path=artifact.rel_path,
            line_no=line_no,
            code="invalid_review_status_family",
            message=(
                "Code/doc review status must be one of `Черновик`, "
                f"`{CODE_DOC_REVIEW_OK_STATUS}`, or `{CODE_DOC_REVIEW_BLOCKER_STATUS}`; "
                "merge-notes statuses such as `✅ Done` do not belong here."
            ),
        )
    return None


def _status_is_green(value: str | None) -> bool:
    if value is None:
        return False
    normalized = _normalize_text(value.replace("`", ""))
    return "✅" in value or normalized.startswith("ok") or normalized.startswith("done") or "green" in normalized


def _status_is_red(value: str | None) -> bool:
    if value is None:
        return False
    normalized = _normalize_text(value.replace("`", ""))
    return "❌" in value or "blocker" in normalized or "finding" in normalized


def _blocker_states(artifact: ReviewArtifact) -> tuple[str, ...]:
    states: list[str] = []
    for block in _iter_blocker_blocks(artifact):
        fields = _field_values(block.lines)
        current_state = _normalize_text(fields.get("current state", "").replace("`", ""))
        if current_state:
            states.append(current_state)
    return tuple(states)


def _has_explicit_historical_reconciliation(artifact: ReviewArtifact) -> bool:
    text = "\n".join(artifact.lines).lower()
    if any(marker in text for marker in HISTORICAL_RECONCILIATION_MARKERS):
        return True
    for state in _blocker_states(artifact):
        if state in {"historical-fixed", "superseded"}:
            return True
    return False


def _same_file_rerun_result_present(
    plan_lines: Sequence[str],
    *,
    live_rel_path: str,
    review_date_value: str | None,
) -> bool:
    section = plan_lint.slice_h2_section(list(plan_lines), plan_lint.REVIEW_ARTIFACTS_HEADING_RE)
    if not section:
        return False

    _, body = section
    review_dt = plan_lint.parse_inline_timestamp(review_date_value or "")
    for line in body:
        match = RERUN_RESULT_LINE_RE.match(line)
        if not match:
            continue
        if not plan_lint.note_mentions_current_review_artifact(match.group("body"), live_rel_path):
            continue
        note_dt = plan_lint.parse_inline_timestamp(match.group("meta"))
        if review_dt is None:
            return True
        if note_dt is not None and note_dt >= review_dt:
            return True
    return False


def _review_synthesis_status(artifact: ReviewArtifact) -> tuple[str | None, int]:
    section = _find_section_block(_iter_h2_blocks(artifact), SYNTHESIS_TITLE_PREFIX)
    if section is None:
        return None, 1
    values = _field_values(section.lines)
    status = values.get("aggregate status")
    if status is None:
        return None, section.line_no
    return _normalize_text(status.replace("`", "")), section.line_no


def _current_fixed_risk_lane_selection(plan_path: Path, review: ReviewArtifact) -> tuple[plan_lint.PlanRiskLaneSelection | None, str]:
    selection = plan_lint.select_plan_risk_lane_snapshot(plan_path)
    if selection.error_code or selection.payload is None:
        reason = selection.error_code or "missing_plan_resident_risk_lane"
        return None, f"current risk-lane selector did not produce fixed evidence: {reason}"

    lane_status = _payload_string(selection.payload, "lane_status")
    if lane_status is None:
        return None, "current risk-lane lane_status is missing"
    lane_status_norm = _normalize_text(lane_status.replace("`", ""))
    if lane_status_norm not in SUCCESSFUL_RISK_LANE_STATUSES:
        return None, f"current risk-lane lane_status is not successful: {lane_status}"

    review_snapshot, _ = _strict_target_snapshot(review)
    if not review_snapshot:
        return None, "live review artifact has no strict Target snapshot"
    if selection.snapshot != review_snapshot:
        return (
            None,
            "current risk-lane target snapshot does not match live review artifact "
            f"({selection.snapshot!r} != {review_snapshot!r})",
        )

    findings_count = _payload_findings_count(selection.payload)
    if findings_count != 0:
        rendered = "unknown" if findings_count is None else str(findings_count)
        return None, f"current risk-lane findings_count is not zero: {rendered}"

    return selection, f"current risk-lane fixed evidence selected at line {selection.line_no}"


def _has_current_fixed_risk_lane_evidence(plan_path: Path, review: ReviewArtifact) -> tuple[bool, str]:
    selection, reason = _current_fixed_risk_lane_selection(plan_path, review)
    return selection is not None, reason


def _risk_lane_selection_order(selection: plan_lint.PlanRiskLaneSelection) -> tuple[str | None, bool, bool, Any, bool]:
    if selection.payload is None:
        return None, False, False, None, False
    written_at = selection.payload.get("written_at")
    if isinstance(written_at, str) and written_at.strip():
        written_at_key = _sortable_timestamp_value(written_at)
        return (
            written_at_key,
            _sortable_timestamp_has_explicit_seconds(written_at),
            _sortable_timestamp_has_explicit_timezone(written_at),
            written_at,
            False,
        )
    run_id_key = _sortable_timestamp_value(selection.run_id, allow_embedded_prefix=True)
    return (
        run_id_key,
        _sortable_timestamp_has_explicit_seconds(selection.run_id, allow_embedded_prefix=True),
        _sortable_timestamp_has_explicit_timezone(selection.run_id, allow_embedded_prefix=True),
        selection.run_id,
        True,
    )


def _ordering_is_same_minute_ambiguous(
    *,
    review_order_key: str,
    fixed_order_key: str,
    review_has_seconds: bool,
    fixed_has_seconds: bool,
) -> bool:
    if review_order_key == fixed_order_key:
        return True
    return not review_has_seconds and fixed_has_seconds and review_order_key[:12] == fixed_order_key[:12]


def classify_same_file_rerun_closeout(
    plan_path: Path,
    review_path: Path,
    *,
    project_root: Path | None = None,
) -> SameFileRerunCloseout:
    root = project_root or _artifact_repo_root(review_path)
    plan_lines = plan_path.read_text(encoding="utf-8", errors="replace").splitlines()
    review = load_review_artifacts(root, [str(review_path.relative_to(root))])[0]
    has_structured_historical_disposition = bool(_historical_disposition_sections(review))
    current_proof = plan_lint.preflight_current_review_proof(plan_path, project_root=root)
    if (
        current_proof.state == "blocked"
        and current_proof.review_path is not None
        and Path(current_proof.review_path).resolve() == review_path.resolve()
    ):
        return SameFileRerunCloseout(
            state="needs_reviewer_rerun",
            line_no=1,
            reason=(
                f"{current_proof.reason_code or 'current_review_proof_blocked'}: "
                f"{current_proof.message}"
            ),
        )
    duplicate_header_findings = _duplicate_review_header_field_findings(review)
    invalid_header_findings = [
        *duplicate_header_findings,
        *_noncanonical_review_header_field_findings(review),
    ]
    if invalid_header_findings:
        finding = invalid_header_findings[0]
        return SameFileRerunCloseout(
            state="needs_reviewer_rerun",
            line_no=finding.line_no,
            reason=f"{finding.code}: {finding.message}",
        )
    review_status, review_status_line = _review_status(review)
    review_date_value, _ = _header_value(review.lines, DATE_HEADER_RE)
    synthesis_status, synthesis_line = _review_synthesis_status(review)
    blocker_states = _blocker_states(review)
    status_family_finding = _validate_status_family(review, review_status, review_status_line)
    if status_family_finding is not None:
        return SameFileRerunCloseout(
            state="needs_reviewer_rerun",
            line_no=status_family_finding.line_no,
            reason=f"{status_family_finding.code}: {status_family_finding.message}",
        )
    structured_historical_reconciled = False
    if has_structured_historical_disposition:
        historical_readback = evaluate_historical_diff_check_disposition(
            project_root=root,
            review_path=review_path,
            origin_plan=plan_path,
            as_status="Done",
            review_text="\n".join(review.lines) + "\n",
        )
        structured_historical_reconciled = historical_readback.state == "accepted"
    current_green = review_status == CODE_DOC_REVIEW_OK_STATUS_NORM
    active_quarantine = plan_lint.review_artifacts_section_has_stale_rerun_note(
        plan_lines,
        live_rel_path=_relative_path(root, review_path),
        review_date_value=review_date_value,
    )
    rerun_result_present = _same_file_rerun_result_present(
        plan_lines,
        live_rel_path=_relative_path(root, review_path),
        review_date_value=review_date_value,
    )
    historical_reconciled = (
        not has_structured_historical_disposition
        and (_has_explicit_historical_reconciliation(review) or rerun_result_present)
    )

    has_open_blocker = any(state == "open" for state in blocker_states)
    if (_status_is_red(review_status) or _status_is_red(synthesis_status) or has_open_blocker) and not (
        structured_historical_reconciled and not has_open_blocker
    ):
        line_no = review_status_line if review_status_line else synthesis_line
        reason = "Current review header or synthesis still carries a blocker-era signal."
        if active_quarantine:
            fixed_selection, fixed_reason = _current_fixed_risk_lane_selection(plan_path, review)
            if fixed_selection is not None:
                fixed_order_key, fixed_has_seconds, fixed_has_timezone, fixed_order_value, fixed_allows_prefix = (
                    _risk_lane_selection_order(fixed_selection)
                )
                review_order_key = _sortable_timestamp_value(review_date_value)
                review_has_seconds = _sortable_timestamp_has_explicit_seconds(review_date_value)
                review_has_timezone = _sortable_timestamp_has_explicit_timezone(review_date_value)
                if review_has_timezone != fixed_has_timezone:
                    review_order_key = _sortable_timestamp_value(review_date_value, normalize_timezone=False)
                    fixed_order_key = _sortable_timestamp_value(
                        fixed_order_value,
                        normalize_timezone=False,
                        allow_embedded_prefix=fixed_allows_prefix,
                    )
                if has_open_blocker:
                    if fixed_order_key is None or review_order_key is None:
                        return SameFileRerunCloseout(
                            state="current_red",
                            line_no=line_no,
                            reason=(
                                "Live review artifact still contains an open same-file blocker, and freshness "
                                "ordering against fixed risk-lane evidence is unavailable; route remains "
                                f"current-red/Coder. {fixed_reason}."
                            ),
                        )
                    if _ordering_is_same_minute_ambiguous(
                        review_order_key=review_order_key,
                        fixed_order_key=fixed_order_key,
                        review_has_seconds=review_has_seconds,
                        fixed_has_seconds=fixed_has_seconds,
                    ):
                        return SameFileRerunCloseout(
                            state="current_red",
                            line_no=line_no,
                            reason=(
                                "Live review artifact still contains an open same-file blocker, and same-minute "
                                "freshness ordering against selected fixed risk-lane evidence is ambiguous; "
                                f"route remains current-red/Coder. {fixed_reason}."
                            ),
                        )
                    if review_order_key > fixed_order_key:
                        return SameFileRerunCloseout(
                            state="current_red",
                            line_no=line_no,
                            reason=(
                                "Live review artifact contains an open same-file blocker newer than the selected "
                                "fixed risk-lane evidence; route remains current-red/Coder instead of "
                                f"stale_red_after_fix. {fixed_reason}."
                            ),
                        )
                return SameFileRerunCloseout(
                    state="stale_red_after_fix",
                    line_no=line_no,
                    reason=(
                        "Live review artifact is a stale red baseline after repo-backed Coder fix; "
                        "same-file Reviewer rewrite is required. "
                        f"{fixed_reason}."
                    ),
                )
            reason = (
                "Live review artifact has a stale/rerun note but remains a live current-red blocker "
                f"because fixed evidence is not proven: {fixed_reason}."
            )
        return SameFileRerunCloseout(
            state="current_red",
            line_no=line_no,
            reason=reason,
        )

    if structured_historical_reconciled:
        return SameFileRerunCloseout(
            state="historical_reconciled",
            line_no=review_status_line if review_status_line else 1,
            reason=(
                "Live review artifact has an accepted structured historical diff-check disposition "
                "after current-proof, canonical-header, and open-blocker gates."
            ),
        )

    if review_status is None and synthesis_status is None and not blocker_states:
        return SameFileRerunCloseout(
            state="needs_reviewer_rerun",
            line_no=1,
            reason="Live review artifact is missing canonical `**Status:**` closeout verdict.",
        )

    if active_quarantine and not historical_reconciled:
        return SameFileRerunCloseout(
            state="needs_reviewer_rerun",
            line_no=review_status_line if review_status_line else 1,
            reason=(
                "Active stale/rerun quarantine still points at the live review artifact without "
                "an explicit same-file rerun result or historical reconciliation."
            ),
        )

    if active_quarantine and not rerun_result_present:
        return SameFileRerunCloseout(
            state="needs_reviewer_rerun",
            line_no=review_status_line if review_status_line else 1,
            reason=(
                "Active stale/rerun quarantine still points at the live review artifact without "
                "a later same-file Rerun result row."
            ),
        )

    if not current_green:
        return SameFileRerunCloseout(
            state="needs_reviewer_rerun",
            line_no=review_status_line if review_status_line else 1,
            reason="Current review header is not a green closeout verdict.",
        )

    if historical_reconciled:
        return SameFileRerunCloseout(
            state="historical_reconciled",
            line_no=review_status_line if review_status_line else 1,
            reason="Live review artifact was explicitly rewritten in place or marked historical/superseded.",
        )

    return SameFileRerunCloseout(
        state="current_green",
        line_no=review_status_line if review_status_line else 1,
        reason="Current live review header is green and no active quarantine remains.",
    )


def _review_snapshot(artifact: ReviewArtifact) -> tuple[str | None, int, str]:
    target_value, target_line = _header_value(artifact.lines, TARGET_HEADER_RE)
    if target_value is not None:
        return _normalize_literal(target_value), target_line, "Target"
    range_value, range_line = _header_value(artifact.lines, RANGE_HEADER_RE)
    if range_value is not None:
        return _normalize_literal(range_value), range_line, "Range"
    return None, 1, "Target/Range"


def _is_merge_range_review_artifact(artifact: ReviewArtifact) -> bool:
    if artifact.first_heading and "merge-range" in artifact.first_heading:
        return True
    if "_reviewer_range_" in artifact.path.name:
        return True
    target_value, _ = _header_value(artifact.lines, TARGET_HEADER_RE)
    if target_value is not None and _normalize_literal(target_value).upper().startswith("RANGE="):
        return True
    range_value, _ = _header_value(artifact.lines, RANGE_HEADER_RE)
    return range_value is not None


def _historical_disposition_sections(artifact: ReviewArtifact) -> list[tuple[int, tuple[tuple[int, str], ...]]]:
    """Return literal optional-disposition H2 blocks, ignoring fenced examples."""

    sections: list[tuple[int, tuple[tuple[int, str], ...]]] = []
    active_line: int | None = None
    active_lines: list[tuple[int, str]] = []
    fenced = False
    for line_no, line in enumerate(artifact.lines, start=1):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            if active_line is not None:
                active_lines.append((line_no, line))
            continue
        if fenced:
            if active_line is not None:
                active_lines.append((line_no, line))
            continue
        h2_match = H2_RE.match(line)
        if h2_match:
            if active_line is not None:
                sections.append((active_line, tuple(active_lines)))
                active_line = None
                active_lines = []
            if h2_match.group("title") == HISTORICAL_DIFF_DISPOSITION_H2:
                active_line = line_no
            continue
        if active_line is not None:
            active_lines.append((line_no, line))
    if active_line is not None:
        sections.append((active_line, tuple(active_lines)))
    return sections


def _historical_literal_value(raw_value: str) -> str:
    value = raw_value.strip()
    if len(value) >= 2 and value.startswith("`") and value.endswith("`"):
        return value[1:-1]
    return value


def _historical_disposition_issue(
    artifact: ReviewArtifact,
    *,
    code: str,
    line_no: int,
    path: str | None = None,
) -> Finding:
    return Finding(
        rel_path=path or artifact.rel_path,
        line_no=line_no,
        code=code,
        message="Historical diff-check disposition is not a complete literal candidate carrier.",
    )


def _parse_historical_diff_disposition(
    artifact: ReviewArtifact,
) -> tuple[bool, dict[str, str], list[tuple[int, dict[str, str]]], list[Finding]]:
    """Parse the opt-in section without the lossy generic field reader."""

    sections = _historical_disposition_sections(artifact)
    if not sections:
        return False, {}, [], []

    issues: list[Finding] = []
    if len(sections) != 1:
        for line_no, _lines in sections[1:]:
            issues.append(
                _historical_disposition_issue(
                    artifact, code="duplicate_historical_diff_disposition_section", line_no=line_no
                )
            )
    section_line, section_lines = sections[0]
    top_values: dict[str, str] = {}
    candidates: list[tuple[int, dict[str, str]]] = []
    candidate_line: int | None = None
    candidate_values: dict[str, str] = {}
    saw_candidate_h3 = False

    def flush_candidate() -> None:
        nonlocal candidate_line, candidate_values
        if candidate_line is None:
            return
        missing = [label for label in HISTORICAL_DIFF_ROW_FIELDS if label not in candidate_values]
        if missing:
            issues.append(
                _historical_disposition_issue(
                    artifact,
                    code="missing_historical_diff_candidate_field",
                    line_no=candidate_line,
                    path=candidate_values.get("path") or artifact.rel_path,
                )
            )
        candidates.append((candidate_line, dict(candidate_values)))
        candidate_line = None
        candidate_values = {}

    for line_no, line in section_lines:
        if not line.strip():
            continue
        h3_match = H3_RE.match(line)
        if h3_match:
            if line != f"### {HISTORICAL_DIFF_CANDIDATE_H3}" or saw_candidate_h3:
                issues.append(
                    _historical_disposition_issue(
                        artifact, code="invalid_historical_diff_candidate_rows_heading", line_no=line_no
                    )
                )
            else:
                saw_candidate_h3 = True
            continue
        if not saw_candidate_h3:
            top_match = re.fullmatch(r"- (?P<label>[^:]+):(?P<value>.*)", line)
            if top_match is None:
                issues.append(
                    _historical_disposition_issue(
                        artifact, code="invalid_historical_diff_top_level_row", line_no=line_no
                    )
                )
                continue
            label = top_match.group("label")
            if label not in HISTORICAL_DIFF_TOP_LEVEL_FIELDS:
                issues.append(
                    _historical_disposition_issue(
                        artifact, code="unknown_historical_diff_top_level_field", line_no=line_no
                    )
                )
                continue
            if label in top_values:
                issues.append(
                    _historical_disposition_issue(
                        artifact, code="duplicate_historical_diff_top_level_field", line_no=line_no
                    )
                )
                continue
            top_values[label] = _historical_literal_value(top_match.group("value"))
            continue

        if re.fullmatch(r"- Candidate:\s*", line):
            flush_candidate()
            candidate_line = line_no
            candidate_values = {}
            continue
        nested_match = re.fullmatch(r"  - (?P<label>[a-z0-9_]+):(?P<value>.*)", line)
        if nested_match is None:
            issues.append(
                _historical_disposition_issue(
                    artifact, code="invalid_historical_diff_candidate_row", line_no=line_no
                )
            )
            continue
        if candidate_line is None:
            issues.append(
                _historical_disposition_issue(
                    artifact, code="orphan_historical_diff_candidate_field", line_no=line_no
                )
            )
            continue
        label = nested_match.group("label")
        if label not in HISTORICAL_DIFF_ROW_FIELDS:
            issues.append(
                _historical_disposition_issue(
                    artifact, code="unknown_historical_diff_candidate_field", line_no=line_no
                )
            )
            continue
        if label in candidate_values:
            issues.append(
                _historical_disposition_issue(
                    artifact,
                    code="duplicate_historical_diff_candidate_field",
                    line_no=line_no,
                    path=candidate_values.get("path") or artifact.rel_path,
                )
            )
            continue
        candidate_values[label] = _historical_literal_value(nested_match.group("value"))

    flush_candidate()
    if not saw_candidate_h3:
        issues.append(
            _historical_disposition_issue(
                artifact, code="missing_historical_diff_candidate_rows_heading", line_no=section_line
            )
        )
    if tuple(top_values) != HISTORICAL_DIFF_TOP_LEVEL_FIELDS:
        issues.append(
            _historical_disposition_issue(
                artifact, code="invalid_historical_diff_top_level_field_order", line_no=section_line
            )
        )
    return True, top_values, candidates, issues


def _historical_target_range(artifact: ReviewArtifact) -> tuple[str | None, int]:
    target_value, line_no = _header_value(artifact.lines, TARGET_HEADER_RE)
    if target_value is None:
        return None, line_no
    match = HISTORICAL_DIFF_RANGE_TARGET_RE.fullmatch(_historical_literal_value(target_value))
    if match is None:
        return None, line_no
    return match.group("range").lower(), line_no


def _historical_parse_nonnegative_int(value: str) -> int | None:
    if not re.fullmatch(r"0|[1-9][0-9]*", value):
        return None
    return int(value)


def _historical_parse_raw_findings(raw_output: str) -> tuple[list[dict[str, Any]], bool]:
    findings: list[dict[str, Any]] = []
    previous_kind: str | None = None
    parse_failed = False
    for raw_line in raw_output.splitlines():
        if not raw_line:
            continue
        match = HISTORICAL_DIFF_RAW_FINDING_RE.fullmatch(raw_line)
        if match is not None:
            message = match.group("message")
            kind = "trailing_whitespace" if message == "trailing whitespace." else "blank_line_at_eof"
            findings.append({"path": match.group("path"), "line": int(match.group("line")), "finding_kind": kind})
            previous_kind = kind
            continue
        if raw_line.startswith("+") and previous_kind == "trailing_whitespace":
            continue
        parse_failed = True
    return findings, parse_failed


def _historical_resolve_repo_path(project_root: Path, raw_path: str) -> Path | None:
    path = Path(raw_path)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return None
    lexical_path = project_root / path
    current = project_root
    for part in path.parts:
        current /= part
        if current.is_symlink():
            return None
    try:
        lexical_path.resolve().relative_to(project_root.resolve())
    except ValueError:
        return None
    return lexical_path


def _historical_candidate_digest(rows: Sequence[dict[str, Any]]) -> str:
    canonical = json.dumps(
        list(rows), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _historical_candidate_sort_key(row: dict[str, Any]) -> tuple[bytes, int, str, str, str]:
    return (
        str(row.get("path", "")).encode("utf-8"),
        int(row.get("line", 0)) if isinstance(row.get("line"), int) else -1,
        str(row.get("finding_kind", "")),
        str(row.get("blob_oid", "")),
        str(row.get("provenance_ref", "")),
    )


def _historical_approval_state(
    artifact: ReviewArtifact,
    *,
    range_value: str,
    raw_exit: int,
    candidate_digest: str,
) -> str:
    matching_sections = [
        section for section in _iter_h2_blocks(artifact) if section.title == HISTORICAL_DIFF_APPROVAL_SECTION
    ]
    approval_lines: list[str] = []
    for section in matching_sections:
        for _line_no, line in section.lines:
            if line.startswith("Historical disposition approval:"):
                approval_lines.append(line)
    if not approval_lines:
        return "missing"
    if len(approval_lines) != 1:
        return "drifted"
    match = HISTORICAL_DIFF_APPROVAL_RE.fullmatch(approval_lines[0])
    if match is None:
        return "drifted"
    if (
        match.group("range").lower() != range_value
        or int(match.group("raw_exit")) != raw_exit
        or match.group("digest").lower() != candidate_digest
    ):
        return "drifted"
    return "accepted"


def _historical_support_reason_code(
    *,
    project_root: Path,
    support_ref: str,
    support_sha256: str,
    support_bytes: bytes,
) -> tuple[str | None, tuple[str, ...]]:
    """Authenticate a support asset against the source plan named by target_ref."""

    try:
        support_payload = json.loads(support_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, ("invalid_historical_support_payload_json",)
    if not isinstance(support_payload, dict):
        return None, ("invalid_historical_support_payload_json",)
    target_ref = support_payload.get("target_ref")
    if not isinstance(target_ref, str):
        return None, ("missing_historical_support_target_ref",)
    source_refs = [match.group("path") for match in ORIGIN_PLAN_RE.finditer(target_ref)]
    if len(source_refs) != 1:
        return None, ("ambiguous_historical_support_target_ref",)
    source_plan = _historical_resolve_repo_path(project_root, source_refs[0])
    if source_plan is None or not source_plan.exists() or not source_plan.is_file():
        return None, ("missing_historical_support_origin_plan",)

    manifest = plan_lint.collect_plan_risk_lane_support_refs(source_plan, project_root=project_root)
    if manifest.diagnostics:
        return None, tuple(diagnostic.code for diagnostic in manifest.diagnostics)
    pair = (support_ref, support_sha256)
    if pair not in manifest.records:
        return None, ("foreign_historical_support_provenance",)

    selection = plan_lint.select_plan_risk_lane_snapshot(source_plan)
    if selection.error_code or selection.payload is None:
        return None, (selection.error_code or "missing_historical_support_selection",)
    support_diagnostics = plan_lint.preflight_selected_risk_lane_support(
        source_plan, selection, project_root=project_root
    )
    if support_diagnostics:
        return None, tuple(diagnostic.code for diagnostic in support_diagnostics)
    selected_ref = _payload_string(selection.payload, "full_payload_ref")
    selected_sha = _payload_string(selection.payload, "full_payload_sha256")
    if selected_ref is None or selected_sha is None:
        return None, ("missing_historical_support_selection",)
    if pair == (selected_ref, selected_sha):
        return "immutable_support_payload_selected_current", ()
    return "immutable_support_payload_historical_or_superseded", ()


def evaluate_historical_diff_check_disposition(
    *,
    project_root: Path,
    review_path: str | Path,
    origin_plan: str | Path,
    as_status: str,
    review_text: str | None = None,
) -> HistoricalDiffCheckReadback:
    """Read one opt-in historical range disposition without rewriting raw Git truth."""

    root = project_root.resolve()
    raw_review_path = Path(review_path)
    resolved_review_path = (raw_review_path if raw_review_path.is_absolute() else root / raw_review_path).resolve()
    if not _path_is_within_project_root(resolved_review_path, root) or not resolved_review_path.is_file():
        issue = Finding(
            rel_path=_relative_path(root, resolved_review_path),
            line_no=1,
            code="missing_historical_diff_review_path",
            message="Historical diff-check readback requires one readable review artifact inside the project root.",
        )
        return HistoricalDiffCheckReadback(
            state="blocked",
            as_status=as_status,
            range_value=None,
            raw_command=None,
            raw_exit=None,
            finding_count=0,
            candidate_count=None,
            candidate_set_sha256=None,
            approval_state="missing",
            issues=(issue,),
        )
    review = review_artifact_from_text(
        root,
        resolved_review_path,
        review_text if review_text is not None else resolved_review_path.read_text(encoding="utf-8", errors="replace"),
    )
    issues: list[Finding] = []
    origin_path, origin_within_root = _selector_origin_plan_path(root, str(origin_plan))
    if not origin_within_root or not origin_path.is_file():
        issues.append(
            _historical_disposition_issue(
                review, code="missing_historical_diff_origin_plan", line_no=1
            )
        )
    else:
        _spec_value, spec_line, spec_state, spec_plan_ref = _spec_carrier(review)
        if spec_state != "plan" or spec_plan_ref is None or (root / spec_plan_ref).resolve() != origin_path:
            issues.append(
                _historical_disposition_issue(
                    review, code="historical_diff_origin_plan_spec_mismatch", line_no=spec_line
                )
            )

    range_value, target_line = _historical_target_range(review)
    if range_value is None:
        issues.append(
            _historical_disposition_issue(review, code="invalid_historical_diff_target_range", line_no=target_line)
        )
        return HistoricalDiffCheckReadback(
            state="blocked",
            as_status=as_status,
            range_value=None,
            raw_command=None,
            raw_exit=None,
            finding_count=0,
            candidate_count=None,
            candidate_set_sha256=None,
            approval_state="missing",
            issues=tuple(sorted(issues, key=lambda item: (item.rel_path, item.line_no, item.code))),
        )

    raw_command = f"git diff --check {range_value}"
    try:
        raw_process = subprocess.run(
            ["git", "diff", "--check", range_value],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            shell=False,
        )
    except OSError:
        issues.append(_historical_disposition_issue(review, code="historical_diff_raw_probe_failed", line_no=target_line))
        return HistoricalDiffCheckReadback(
            state="blocked",
            as_status=as_status,
            range_value=range_value,
            raw_command=raw_command,
            raw_exit=None,
            finding_count=0,
            candidate_count=None,
            candidate_set_sha256=None,
            approval_state="missing",
            issues=tuple(sorted(issues, key=lambda item: (item.rel_path, item.line_no, item.code))),
        )
    raw_findings, raw_parse_failed = _historical_parse_raw_findings(raw_process.stdout + raw_process.stderr)
    if raw_parse_failed or (raw_process.returncode != 0 and not raw_findings):
        issues.append(_historical_disposition_issue(review, code="unparseable_historical_diff_raw_output", line_no=target_line))

    opted_in, top_values, parsed_candidates, parse_issues = _parse_historical_diff_disposition(review)
    issues.extend(parse_issues)
    if raw_process.returncode == 0 and not raw_findings and not opted_in and not issues:
        return HistoricalDiffCheckReadback(
            state="raw_green",
            as_status=as_status,
            range_value=range_value,
            raw_command=raw_command,
            raw_exit=raw_process.returncode,
            finding_count=0,
            candidate_count=0,
            candidate_set_sha256=None,
            approval_state="not_applicable",
            issues=(),
        )
    if not opted_in:
        issues.append(_historical_disposition_issue(review, code="missing_historical_diff_disposition", line_no=target_line))

    candidate_count: int | None = None
    candidate_digest: str | None = None
    parsed_rows: list[dict[str, Any]] = []
    if opted_in:
        top_command = top_values.get("Raw command")
        if top_command != raw_command:
            issues.append(_historical_disposition_issue(review, code="historical_diff_raw_command_mismatch", line_no=target_line))
        top_raw_exit = _historical_parse_nonnegative_int(top_values.get("Raw exit", ""))
        if top_raw_exit is None:
            issues.append(_historical_disposition_issue(review, code="invalid_historical_diff_raw_exit", line_no=target_line))
        elif top_raw_exit != raw_process.returncode:
            issues.append(_historical_disposition_issue(review, code="historical_diff_raw_exit_mismatch", line_no=target_line))
        candidate_count = _historical_parse_nonnegative_int(top_values.get("Candidate count", ""))
        if candidate_count is None:
            issues.append(_historical_disposition_issue(review, code="invalid_historical_diff_candidate_count", line_no=target_line))
        candidate_digest = top_values.get("Candidate set SHA-256") or None
        if candidate_digest is None or re.fullmatch(r"[0-9a-f]{64}", candidate_digest, re.IGNORECASE) is None:
            issues.append(_historical_disposition_issue(review, code="invalid_historical_diff_candidate_digest", line_no=target_line))

        raw_identity = {(finding["path"], finding["line"], finding["finding_kind"]) for finding in raw_findings}
        candidate_identity: set[tuple[str, int, str]] = set()
        head = range_value.split("..", 1)[1]
        for row_line, raw_row in parsed_candidates:
            row: dict[str, Any] = {}
            for field in HISTORICAL_DIFF_ROW_FIELDS:
                raw_value = raw_row.get(field)
                if raw_value is None:
                    continue
                row[field] = raw_value
            raw_exit = _historical_parse_nonnegative_int(str(row.get("raw_exit", "")))
            row_line_number = _historical_parse_nonnegative_int(str(row.get("line", "")))
            if raw_exit is None or row_line_number is None:
                issues.append(_historical_disposition_issue(review, code="invalid_historical_diff_candidate_integer", line_no=row_line))
                continue
            row["raw_exit"] = raw_exit
            row["line"] = row_line_number
            parsed_rows.append(row)
            path = str(row.get("path", ""))
            finding_kind = str(row.get("finding_kind", ""))
            identity = (path, row_line_number, finding_kind)
            if identity in candidate_identity:
                issues.append(
                    _historical_disposition_issue(
                        review, code="duplicate_historical_diff_candidate", line_no=row_line, path=path or review.rel_path
                    )
                )
            candidate_identity.add(identity)
            if row.get("range") != range_value:
                issues.append(_historical_disposition_issue(review, code="historical_diff_candidate_range_mismatch", line_no=row_line, path=path or None))
            if row.get("raw_command") != raw_command:
                issues.append(_historical_disposition_issue(review, code="historical_diff_candidate_raw_command_mismatch", line_no=row_line, path=path or None))
            if raw_exit != raw_process.returncode:
                issues.append(_historical_disposition_issue(review, code="historical_diff_candidate_raw_exit_mismatch", line_no=row_line, path=path or None))
            if finding_kind not in HISTORICAL_DIFF_ALLOWED_FINDING_KINDS:
                issues.append(_historical_disposition_issue(review, code="invalid_historical_diff_finding_kind", line_no=row_line, path=path or None))
            if row.get("lifecycle") != "candidate" or row.get("owner") != "Reviewer" or row.get("action") != "record_candidate":
                issues.append(_historical_disposition_issue(review, code="invalid_historical_diff_candidate_lifecycle", line_no=row_line, path=path or None))
            if identity not in raw_identity:
                issues.append(_historical_disposition_issue(review, code="foreign_historical_diff_candidate", line_no=row_line, path=path or None))

            candidate_path = _historical_resolve_repo_path(root, path)
            if candidate_path is None or not candidate_path.is_file():
                issues.append(_historical_disposition_issue(review, code="invalid_historical_diff_candidate_path", line_no=row_line, path=path or None))
                continue
            try:
                tree_process = subprocess.run(
                    ["git", "ls-tree", head, "--", path],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    check=False,
                    shell=False,
                )
            except OSError:
                issues.append(_historical_disposition_issue(review, code="historical_diff_blob_lookup_failed", line_no=row_line, path=path))
                continue
            tree_match = re.fullmatch(r"[0-7]{6} blob (?P<blob>[0-9a-f]{40})\t.+\n?", tree_process.stdout, re.IGNORECASE)
            if tree_process.returncode != 0 or tree_match is None:
                issues.append(_historical_disposition_issue(review, code="historical_diff_blob_lookup_failed", line_no=row_line, path=path))
                continue
            blob_oid = tree_match.group("blob").lower()
            if str(row.get("blob_oid", "")).lower() != blob_oid:
                issues.append(_historical_disposition_issue(review, code="historical_diff_blob_oid_mismatch", line_no=row_line, path=path))
            try:
                blob_process = subprocess.run(
                    ["git", "cat-file", "blob", blob_oid],
                    cwd=root,
                    capture_output=True,
                    check=False,
                    shell=False,
                )
            except OSError:
                issues.append(_historical_disposition_issue(review, code="historical_diff_blob_read_failed", line_no=row_line, path=path))
                continue
            if blob_process.returncode != 0:
                issues.append(_historical_disposition_issue(review, code="historical_diff_blob_read_failed", line_no=row_line, path=path))
                continue
            try:
                current_bytes = candidate_path.read_bytes()
            except OSError:
                issues.append(_historical_disposition_issue(review, code="historical_diff_candidate_read_failed", line_no=row_line, path=path))
                continue
            actual_sha = hashlib.sha256(blob_process.stdout).hexdigest()
            if current_bytes != blob_process.stdout:
                issues.append(_historical_disposition_issue(review, code="historical_diff_current_bytes_stale", line_no=row_line, path=path))
            if str(row.get("provenance_sha256", "")).lower() != actual_sha:
                issues.append(_historical_disposition_issue(review, code="historical_diff_provenance_sha256_mismatch", line_no=row_line, path=path))

            reason_code = str(row.get("reason_code", ""))
            if reason_code not in HISTORICAL_DIFF_ALLOWED_REASON_CODES:
                issues.append(_historical_disposition_issue(review, code="invalid_historical_diff_reason_code", line_no=row_line, path=path))
                continue
            if finding_kind == "trailing_whitespace":
                if (
                    row.get("provenance_ref") != path
                    or reason_code != "intentional_markdown_hard_break"
                ):
                    issues.append(_historical_disposition_issue(review, code="invalid_historical_diff_hard_break_provenance", line_no=row_line, path=path))
            elif finding_kind == "blank_line_at_eof":
                if row.get("provenance_ref") != path:
                    issues.append(_historical_disposition_issue(review, code="invalid_historical_diff_support_provenance", line_no=row_line, path=path))
                    continue
                expected_reason, support_codes = _historical_support_reason_code(
                    project_root=root,
                    support_ref=path,
                    support_sha256=actual_sha,
                    support_bytes=current_bytes,
                )
                for code in support_codes:
                    issues.append(_historical_disposition_issue(review, code=code, line_no=row_line, path=path))
                if expected_reason is not None and reason_code != expected_reason:
                    issues.append(_historical_disposition_issue(review, code="historical_diff_support_lifecycle_mismatch", line_no=row_line, path=path))

        if candidate_count is not None and candidate_count != len(parsed_rows):
            issues.append(_historical_disposition_issue(review, code="historical_diff_candidate_count_mismatch", line_no=target_line))
        if candidate_count is not None and candidate_count != len(raw_findings):
            issues.append(_historical_disposition_issue(review, code="historical_diff_raw_finding_count_mismatch", line_no=target_line))
        if candidate_identity != raw_identity:
            issues.append(_historical_disposition_issue(review, code="historical_diff_candidate_inventory_mismatch", line_no=target_line))
        if parsed_rows != sorted(parsed_rows, key=_historical_candidate_sort_key):
            issues.append(_historical_disposition_issue(review, code="historical_diff_candidate_order_mismatch", line_no=target_line))
        if all(set(row) == set(HISTORICAL_DIFF_ROW_FIELDS) for row in parsed_rows):
            actual_digest = _historical_candidate_digest(parsed_rows)
            if candidate_digest is not None and candidate_digest.lower() != actual_digest:
                issues.append(_historical_disposition_issue(review, code="historical_diff_candidate_digest_mismatch", line_no=target_line))

    approval_state = "not_applicable"
    if raw_process.returncode != 0 and candidate_digest is not None:
        approval_state = _historical_approval_state(
            review,
            range_value=range_value,
            raw_exit=raw_process.returncode,
            candidate_digest=candidate_digest.lower(),
        )
        if approval_state == "drifted":
            issues.append(_historical_disposition_issue(review, code="historical_diff_approval_drifted", line_no=target_line))
    sorted_issues = tuple(sorted(issues, key=lambda item: (item.rel_path, item.line_no, item.code)))
    if not sorted_issues and raw_process.returncode == 0 and not raw_findings:
        state = "raw_green"
    elif not sorted_issues and raw_process.returncode != 0 and as_status == "Ready for Arch review":
        state = "verified_pending_architect"
    elif not sorted_issues and raw_process.returncode != 0 and as_status == "Done" and approval_state == "accepted":
        state = "accepted"
    else:
        if raw_process.returncode != 0 and as_status == "Done" and approval_state == "missing":
            sorted_issues = tuple(
                sorted(
                    (*sorted_issues, _historical_disposition_issue(review, code="historical_diff_approval_missing", line_no=target_line)),
                    key=lambda item: (item.rel_path, item.line_no, item.code),
                )
            )
        state = "blocked"
    return HistoricalDiffCheckReadback(
        state=state,
        as_status=as_status,
        range_value=range_value,
        raw_command=raw_command,
        raw_exit=raw_process.returncode,
        finding_count=len(raw_findings),
        candidate_count=candidate_count,
        candidate_set_sha256=candidate_digest.lower() if candidate_digest is not None else None,
        approval_state=approval_state,
        issues=sorted_issues,
    )


def _strict_target_snapshot(artifact: ReviewArtifact) -> tuple[str | None, int]:
    target_value, target_line = _header_value(artifact.lines, TARGET_HEADER_RE)
    if target_value is None:
        return None, target_line
    normalized = _normalize_literal(target_value)
    if not normalized:
        return None, target_line
    return normalized, target_line


def _spec_carrier(artifact: ReviewArtifact) -> tuple[str | None, int, str | None, str | None]:
    raw_value, line_no = _header_value(artifact.lines, SPEC_HEADER_RE)
    if raw_value is None:
        return None, line_no, "missing", None
    value = _normalize_literal(raw_value)
    if not value:
        return value, line_no, "missing", None
    if value == MANUAL_NO_ORIGIN_SPEC:
        return value, line_no, "manual_no_origin", None
    plan_match = PLAN_SPEC_RE.match(value)
    if plan_match:
        return value, line_no, "plan", plan_match.group("path")
    return value, line_no, "invalid", None


def _origin_plan_refs_from_target(artifact: ReviewArtifact) -> tuple[list[str], int]:
    target_value, target_line = _header_value(artifact.lines, TARGET_HEADER_RE)
    if target_value is None:
        return [], 1
    refs: list[str] = []
    seen: set[str] = set()
    for match in ORIGIN_PLAN_RE.finditer(target_value):
        ref = match.group("path")
        if ref in seen:
            continue
        seen.add(ref)
        refs.append(ref)
    return refs, target_line


def _path_is_within_project_root(path: Path, project_root: Path) -> bool:
    try:
        path.resolve().relative_to(project_root.resolve())
    except ValueError:
        return False
    return True


def _resolve_origin_plan(
    artifact: ReviewArtifact,
    *,
    project_root: Path | None,
    origin_plan: str | Path | None,
) -> tuple[Path | None, int, str | None]:
    root = project_root or _artifact_repo_root(artifact.path)
    if origin_plan is not None:
        raw_origin = str(origin_plan).strip()
        if raw_origin:
            path = Path(raw_origin)
            resolved = (path if path.is_absolute() else root / path).resolve()
            return resolved, 1, None if _path_is_within_project_root(resolved, root) else "outside"

    refs, target_line = _origin_plan_refs_from_target(artifact)
    if len(refs) == 1:
        resolved = (root / refs[0]).resolve()
        return resolved, target_line, None if _path_is_within_project_root(resolved, root) else "outside"
    if len(refs) > 1:
        return None, target_line, "multiple"
    return None, target_line, "missing"


def _is_dual_lane_review(section_blocks: Sequence[SectionBlock]) -> bool:
    risk_section = _find_section_block(section_blocks, RISK_LANE_TITLE_PREFIX)
    contracts_section = _find_section_block(section_blocks, CONTRACTS_LANE_TITLE_PREFIX)
    if risk_section is not None and contracts_section is not None:
        return True

    synthesis_block = _find_section_block(section_blocks, SYNTHESIS_TITLE_PREFIX)
    if synthesis_block is None:
        return False
    values = _field_values(synthesis_block.lines)
    source_lanes = _normalize_text(values.get("source lanes", "").replace("`", ""))
    return "reviewer_code_risk" in source_lanes and "reviewer_code_contracts" in source_lanes


def _is_current_bundle_snapshot(value: str | None) -> bool:
    if value is None:
        return False
    normalized = _normalize_literal(value)
    return normalized.startswith(CURRENT_BUNDLE_TARGET) and "bundle_sha256=" in normalized


def _current_bundle_snapshot_from_disk(
    origin_plan_path: Path,
    *,
    project_root: Path | None,
) -> tuple[str | None, str | None]:
    try:
        snapshot = build_current_bundle_snapshot(origin_plan_path, project_root=project_root)
    except (OSError, SnapshotError) as exc:
        return None, str(exc)
    target = snapshot.get("target")
    if not isinstance(target, str) or not target.strip():
        return None, "current-bundle producer returned no literal target"
    return _normalize_literal(target), None


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


def _sortable_timestamp_has_explicit_timezone(value: Any, *, allow_embedded_prefix: bool = False) -> bool:
    if not isinstance(value, str):
        return False
    raw = value.strip()
    if not raw:
        return False
    for pattern in (
        r"(?P<year>\d{4})[-_]?((?P<month>\d{2})[-_]?(?P<day>\d{2}))"
        r"[ T_-]*(?P<hour>\d{2}):?(?P<minute>\d{2})(?::?(?P<second>\d{2}))?",
        r"(?P<day>\d{2})\.(?P<month>\d{2})\.(?P<year>\d{4})"
        r"[ T_-]*(?P<hour>\d{2}):(?P<minute>\d{2})(?::(?P<second>\d{2}))?",
    ):
        match = re.search(pattern, raw)
        if match:
            if not allow_embedded_prefix and not _timestamp_match_has_only_wrapper_prefix(raw, match):
                return False
            timestamp_timezone, _has_timezone_token = _timestamp_match_timezone(raw, match)
            return timestamp_timezone is not None
    return False


def _sortable_timestamp_has_explicit_seconds(value: Any, *, allow_embedded_prefix: bool = False) -> bool:
    if not isinstance(value, str):
        return False
    raw = value.strip()
    if not raw:
        return False
    iso_match = re.search(
        r"(?P<year>\d{4})[-_]?((?P<month>\d{2})[-_]?(?P<day>\d{2}))"
        r"[ T_-]*(?P<hour>\d{2}):?(?P<minute>\d{2})(?::?(?P<second>\d{2}))?",
        raw,
    )
    if iso_match:
        if not allow_embedded_prefix and not _timestamp_match_has_only_wrapper_prefix(raw, iso_match):
            return False
        return iso_match.group("second") is not None
    dmy_match = re.search(
        r"(?P<day>\d{2})\.(?P<month>\d{2})\.(?P<year>\d{4})"
        r"[ T_-]*(?P<hour>\d{2}):(?P<minute>\d{2})(?::(?P<second>\d{2}))?",
        raw,
    )
    if dmy_match:
        if not allow_embedded_prefix and not _timestamp_match_has_only_wrapper_prefix(raw, dmy_match):
            return False
        return dmy_match.group("second") is not None
    run_id_match = re.search(
        r"(?P<date>\d{8})[T_-]?(?P<hour>\d{2})(?P<minute>\d{2})(?P<second>\d{2})?",
        raw,
    )
    if run_id_match and not allow_embedded_prefix and not _timestamp_match_has_only_wrapper_prefix(raw, run_id_match):
        return False
    return bool(run_id_match and run_id_match.group("second") is not None)


def _payload_string(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _payload_findings_count(payload: dict[str, Any]) -> int | None:
    findings = payload.get("findings")
    if isinstance(findings, list):
        return len(findings)
    if isinstance(findings, dict):
        return len(findings)
    if isinstance(findings, str):
        normalized = _normalize_text(findings.replace("`", ""))
        if normalized in {"", "[]", "none", "n/a", "n/a (no findings)", "n/a (no risk findings)"}:
            return 0
        if "no findings" in normalized or "findings отсутствуют" in normalized:
            return 0
        return 1

    no_findings_reason = _payload_string(payload, "no_findings_reason")
    if no_findings_reason:
        return 0

    raw_count = payload.get("findings_count")
    if isinstance(raw_count, int) and raw_count >= 0:
        return raw_count
    if isinstance(raw_count, str) and raw_count.strip().isdigit():
        return int(raw_count.strip())
    return None


def _selector_origin_plan_path(project_root: Path, origin_plan: str) -> tuple[Path, bool]:
    plan_path = Path(origin_plan)
    resolved = (plan_path if plan_path.is_absolute() else project_root / plan_path).resolve()
    return resolved, _path_is_within_project_root(resolved, project_root)


def _risk_lane_selection_payload(
    *,
    selection: plan_lint.PlanRiskLaneSelection,
    origin_plan_path: Path,
    project_root: Path,
    support_diagnostics: Sequence[plan_lint.RiskLaneSupportDiagnostic] = (),
) -> dict[str, Any]:
    origin_plan = _relative_path(project_root, origin_plan_path)
    if selection.error_code:
        state = "blocked"
        reason = selection.message or "Origin plan risk lane selection is blocked."
        error_code = selection.error_code
    elif selection.snapshot is None:
        state = "missing"
        error_code = "missing_plan_resident_risk_lane"
        if origin_plan_path.exists():
            reason = (
                "Origin plan has no parseable plan-resident `reviewer_code_risk` lane-run JSON block "
                "with parseable `target_snapshot`; projection blocks are not accepted."
            )
        else:
            reason = f"Origin plan does not exist: {origin_plan}"
    elif selection.payload is not None and tuple(_iter_homebrew_command_payload_paths(selection.payload)):
        state = "blocked"
        paths = ", ".join(_iter_homebrew_command_payload_paths(selection.payload))
        reason = (
            "Selected plan-resident `reviewer_code_risk` payload contains expanded owner-local Homebrew "
            f"interpreter command evidence at {paths}; record `$PYBIN ...` or `python3 ...` instead."
        )
        error_code = HOMEBREW_COMMAND_EVIDENCE_CODE
    elif support_diagnostics:
        first_diagnostic = support_diagnostics[0]
        state = "blocked"
        reason = first_diagnostic.message
        error_code = first_diagnostic.code
    else:
        state = "selected"
        reason = selection.reason or "reviewer_code_risk lane selected"
        error_code = None

    return {
        "schema_version": "reviewer_risk_lane_selection.v1",
        "state": state,
        "origin_plan": origin_plan,
        "selected_line": selection.line_no if state == "selected" else None,
        "run_id": selection.run_id if state == "selected" else None,
        "target_snapshot": selection.snapshot if state == "selected" else None,
        "reason": reason,
        "error_code": error_code,
    }


def review_artifact_status(path: str | Path) -> str | None:
    """Read the literal review artifact status header."""
    artifact_path = Path(path)
    try:
        lines = tuple(artifact_path.read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError:
        return None
    artifact = ReviewArtifact(
        path=artifact_path,
        rel_path=str(artifact_path),
        lines=lines,
        first_heading=_first_heading(lines),
        is_code_review=_detect_code_review(artifact_path, _first_heading(lines)),
        is_merge_notes=_detect_merge_notes(artifact_path, _first_heading(lines)),
    )
    status, _ = _review_status(artifact)
    return status


def _find_section_block(sections: Sequence[SectionBlock], title_prefix: str) -> SectionBlock | None:
    for section in sections:
        if section.title.startswith(title_prefix):
            return section
    return None


def _section_finding_ids(section: SectionBlock | None) -> tuple[str, ...]:
    if section is None:
        return ()
    ids: list[str] = []
    for _, line in section.lines:
        ids.extend(match.group(0) for match in LANE_FINDING_RE.finditer(line))
    return tuple(ids)


def _section_has_canonical_blocker_ref(section: SectionBlock | None) -> bool:
    if section is None:
        return False
    for _, line in section.lines:
        if CANONICAL_BLOCKER_RE.search(line):
            return True
    return False


def _validate_no_findings_provenance_values(values: dict[str, str]) -> list[str]:
    invalid: list[str] = []

    source_lane = _normalize_text(values.get("source_lane", "").replace("`", ""))
    if "reviewer_code_risk" not in source_lane or "reviewer_code_contracts" not in source_lane:
        invalid.append("source_lane")

    lane_finding_id = _normalize_text(values.get("lane_finding_id", "").replace("`", ""))
    if lane_finding_id != "n/a (no lane findings)":
        invalid.append("lane_finding_id")

    synthesis_disposition = _normalize_text(values.get("synthesis_disposition", "").replace("`", ""))
    if synthesis_disposition != "no_findings":
        invalid.append("synthesis_disposition")

    canonical_ref = _normalize_text(values.get("canonical_ref", "").replace("`", ""))
    if "lane-synthesis--aggregate-verdict" not in canonical_ref or canonical_ref.startswith("n/a"):
        invalid.append("canonical_ref")

    audit_status = _normalize_text(values.get("audit_status", "").replace("`", ""))
    if audit_status not in {"pending_post_merge_audit", "done", "n/a"}:
        invalid.append("audit_status")

    followup_plan = _normalize_text(values.get("followup_plan", "").replace("`", ""))
    if followup_plan != "n/a":
        invalid.append("followup_plan")

    return invalid


def _small_runner_review_key(value: str) -> str:
    key = _normalize_text(value.replace("/", " ")).replace(" ", "_")
    key = re.sub(r"[^a-z0-9_]+", "_", key).strip("_")
    return SMALL_RUNNER_REVIEW_FIELD_ALIASES.get(key, key)


def _small_runner_review_token(value: str) -> str:
    return _normalize_text(value.replace("`", "")).replace(" ", "_")


def _collect_small_runner_review_fields(artifact: ReviewArtifact) -> dict[str, list[tuple[int, str]]]:
    fields: dict[str, list[tuple[int, str]]] = {}

    def add_field(raw_key: str, raw_value: str, line_no: int) -> None:
        key = _small_runner_review_key(raw_key)
        if key not in SMALL_RUNNER_REVIEW_FIELD_ALIASES.values():
            return
        fields.setdefault(key, []).append((line_no, raw_value.strip().strip("`").strip()))

    for line_no, line in enumerate(artifact.lines, start=1):
        normalized = line.replace("`", "").strip()
        while normalized.startswith("- "):
            normalized = normalized[2:].strip()
        if ":" in normalized:
            raw_key, raw_value = normalized.split(":", 1)
            add_field(raw_key, raw_value, line_no)
        for inline_match in re.finditer(
            r"\b(?P<field>runner_id|reviewer_runner_id|runner_result|small_runner_success|frontier_intervention|runner_admission|small_model_ready_state)\s*[=:]\s*(?P<value>[A-Za-z0-9_./-]+)",
            line,
            re.IGNORECASE,
        ):
            add_field(inline_match.group("field"), inline_match.group("value"), line_no)

    return fields


def _small_runner_review_values(fields: dict[str, list[tuple[int, str]]], key: str) -> tuple[str, ...]:
    return tuple(value for _line_no, value in fields.get(key, ()))


def _small_runner_review_first_line(fields: dict[str, list[tuple[int, str]]], *keys: str) -> int:
    for key in keys:
        values = fields.get(key)
        if values:
            return values[0][0]
    return 1


def _small_runner_review_claims_success(fields: dict[str, list[tuple[int, str]]]) -> bool:
    if any(_small_runner_review_token(value) == "small_runner_ok" for value in _small_runner_review_values(fields, "runner_admission")):
        return True
    if any(_small_runner_review_token(value) == "ready" for value in _small_runner_review_values(fields, "small_model_ready_state")):
        return True
    return any(
        _small_runner_review_token(value) in SMALL_RUNNER_REVIEW_SUCCESS_VALUES
        for value in _small_runner_review_values(fields, "small_runner_success")
    )


def _small_runner_review_material(value: str) -> bool:
    raw = value.strip()
    if not raw:
        return False
    if plan_lint.is_placeholder_value(raw) or plan_lint.is_explicit_na_value(raw):
        return False
    token = _small_runner_review_token(raw)
    if not token:
        return False
    if token in {"n/a", "na", "none", "null", "tbd", "todo", "-", "unknown", "unconfirmed"}:
        return False
    if token.startswith(("n/a", "na_", "none_", "null_", "tbd_", "todo_", "unknown_", "unconfirmed_", "not_exposed", "not_available")):
        return False
    return True


def _small_runner_review_has_material_success_proof(fields: dict[str, list[tuple[int, str]]]) -> bool:
    runner_id = any(_small_runner_review_material(value) for value in _small_runner_review_values(fields, "runner_id"))
    runner_result = any(_small_runner_review_material(value) for value in _small_runner_review_values(fields, "runner_result"))
    success = any(
        _small_runner_review_token(value) in SMALL_RUNNER_REVIEW_SUCCESS_VALUES
        for value in _small_runner_review_values(fields, "small_runner_success")
    )
    frontier_clean = any(
        _small_runner_review_token(value) in {"false", "no", "none", "not_required", "not_used", "n/a", "na"}
        for value in _small_runner_review_values(fields, "frontier_intervention")
    )
    reviewer_lane = any(_small_runner_review_material(value) for value in _small_runner_review_values(fields, "reviewer_lane")) or any(
        _small_runner_review_material(value) for value in _small_runner_review_values(fields, "reviewer_runner_id")
    )
    return runner_id and runner_result and success and frontier_clean and reviewer_lane


def _small_runner_review_has_red_evidence(
    artifact: ReviewArtifact,
    fields: dict[str, list[tuple[int, str]]],
) -> tuple[bool, int]:
    for key in ("small_runner_success", "runner_result", "frontier_intervention"):
        for line_no, value in fields.get(key, ()):
            token = _small_runner_review_token(value)
            if key == "small_runner_success" and token in SMALL_RUNNER_REVIEW_FALSE_VALUES:
                return True, line_no
            if key == "runner_result" and (
                token in SMALL_RUNNER_REVIEW_FALSE_VALUES or any(marker in token for marker in ("unavailable", "partial", "inconclusive"))
            ):
                return True, line_no
            if key == "frontier_intervention" and token in {"true", "yes", "required", "used"}:
                return True, line_no
    for line_no, line in enumerate(artifact.lines, start=1):
        if SMALL_RUNNER_REVIEW_RED_RE.search(line):
            return True, line_no
    return False, 1


def _small_runner_review_has_self_approval_mismatch(fields: dict[str, list[tuple[int, str]]]) -> tuple[bool, int]:
    runner_ids = {_small_runner_review_token(value) for value in _small_runner_review_values(fields, "runner_id") if _small_runner_review_material(value)}
    reviewer_runner_ids = {
        _small_runner_review_token(value)
        for value in _small_runner_review_values(fields, "reviewer_runner_id")
        if _small_runner_review_material(value)
    }
    if runner_ids & reviewer_runner_ids:
        return True, _small_runner_review_first_line(fields, "reviewer_runner_id", "reviewer_lane")
    for lane_line, lane_value in fields.get("reviewer_lane", ()):
        lane_token = _small_runner_review_token(lane_value)
        if any(runner_id and runner_id in lane_token for runner_id in runner_ids):
            if "independent" not in lane_token and "frontier" not in lane_token and "contracts" not in lane_token:
                return True, lane_line
    return False, 1


def validate_small_runner_review_consistency(artifact: ReviewArtifact) -> list[Finding]:
    fields = _collect_small_runner_review_fields(artifact)
    if not _small_runner_review_claims_success(fields):
        return []

    findings: list[Finding] = []
    line_no = _small_runner_review_first_line(fields, "small_runner_success", "runner_admission", "small_model_ready_state")
    red, red_line = _small_runner_review_has_red_evidence(artifact, fields)
    if red:
        findings.append(
            Finding(
                rel_path=artifact.rel_path,
                line_no=red_line,
                code="small_runner_success_conflicts_with_red_evidence",
                message="Review artifact claims small-runner success/readiness while runner evidence is unavailable, partial, failed, or frontier-controlled.",
            )
        )
    if not _small_runner_review_has_material_success_proof(fields):
        findings.append(
            Finding(
                rel_path=artifact.rel_path,
                line_no=line_no,
                code="small_runner_success_missing_proof",
                message=(
                    "Small-runner success/readiness claims need material proof fields: `runner_id`, `runner_result`, "
                    "`small_runner_success=true`, `frontier_intervention=false|none`, and reviewer lane/readback."
                ),
            )
        )
    mismatch, mismatch_line = _small_runner_review_has_self_approval_mismatch(fields)
    if mismatch:
        findings.append(
            Finding(
                rel_path=artifact.rel_path,
                line_no=mismatch_line,
                code="small_runner_reviewer_lane_mismatch",
                message="Same small runner appears to be the only substantive reviewer for its own successful output; add independent/frontier review readback.",
            )
        )
    return findings


def lint_review_artifacts(
    artifacts: Sequence[ReviewArtifact],
    *,
    project_root: Path | None = None,
    origin_plan: str | Path | None = None,
    require_dual_lane_origin: bool = False,
) -> list[Finding]:
    findings: list[Finding] = []

    for artifact in artifacts:
        _, schema_findings = classify_review_schema_version(artifact)
        findings.extend(schema_findings)
        findings.extend(
            Finding(
                rel_path=artifact.rel_path,
                line_no=receipt.line_no,
                code=receipt.code,
                message=receipt.message,
            )
            for receipt in retrieval_telemetry_receipt.lint_retrieval_telemetry_receipt(artifact.lines)
        )
        findings.extend(validate_small_runner_review_consistency(artifact))
        findings.extend(_lint_homebrew_command_evidence_lines(artifact))
        findings.extend(_duplicate_review_header_field_findings(artifact))
        findings.extend(_noncanonical_review_header_field_findings(artifact))

        line_pairs = tuple(enumerate(artifact.lines, start=1))
        file_fields = _field_locations(line_pairs)
        h2_sections = {title: line_no for line_no, title in _heading_locations(artifact.lines, H2_RE)}
        section_blocks = _iter_h2_blocks(artifact)
        status_matches = _extract_status_lines(artifact.lines)
        review_status, review_status_line = _review_status(artifact)
        if len(status_matches) > 1:
            findings.append(
                Finding(
                    rel_path=artifact.rel_path,
                    line_no=status_matches[1][0],
                    code="duplicate_review_status",
                    message="Review artifact must contain exactly one `**Status:**` header.",
                )
            )
        status_family_finding = _validate_status_family(artifact, review_status, review_status_line)
        if status_family_finding is not None:
            findings.append(status_family_finding)

        if _is_guarded_review_artifact(artifact) and review_status in FINAL_REVIEW_STATUSES:
            summary_line_no, summary_line = _first_summary_line(artifact)
            if summary_line is None or not summary_line.startswith(RUSSIAN_FIRST_SUMMARY_PREFIXES):
                findings.append(
                    Finding(
                        rel_path=artifact.rel_path,
                        line_no=summary_line_no,
                        code="invalid_russian_first_summary",
                        message=(
                            "Final code/doc review artifacts need a Russian-first summary line starting with "
                            "`ОК:`, `Замечания:`, or `Вердикт:` before lane sections."
                        ),
                    )
                )

            if review_status == FINAL_OK_STATUS and not _has_exact_bundle_hygiene_receipt(section_blocks):
                findings.append(
                    Finding(
                        rel_path=artifact.rel_path,
                        line_no=review_status_line,
                        code="missing_exact_bundle_hygiene_receipt",
                        message=(
                            "Final `✅ OK` review artifacts need an explicit exact-bundle/untracked-file "
                            "hygiene receipt before green closeout."
                        ),
                    )
                )

        claims_rerun, rerun_anchor = _claims_rerun_context(artifact, file_fields, h2_sections)
        if claims_rerun:
            missing_rerun = [label for label in RERUN_FIELD_LABELS if label not in file_fields]
            if missing_rerun:
                findings.append(
                    Finding(
                        rel_path=artifact.rel_path,
                        line_no=rerun_anchor,
                        code="missing_rerun_fields",
                        message=f"Missing rerun fields: {', '.join(missing_rerun)}",
                    )
                )

        required_visual_fields, visual_anchor = _visual_receipt_requirements(
            artifact, file_fields, h2_sections, claims_rerun
        )
        if required_visual_fields:
            missing_visual = [label for label in required_visual_fields if label not in file_fields]
            if missing_visual:
                findings.append(
                    Finding(
                        rel_path=artifact.rel_path,
                        line_no=visual_anchor,
                        code="missing_visual_receipt_fields",
                        message=f"Missing visual receipt fields: {', '.join(missing_visual)}",
                    )
                )

        for line_no, raw_path in _iter_visual_asset_refs(artifact):
            if not raw_path:
                findings.append(
                    Finding(
                        rel_path=artifact.rel_path,
                        line_no=line_no,
                        code="invalid_visual_asset_ref",
                        message="Visual asset ref must be one exact literal repo path",
                    )
                )
                continue
            if _is_placeholder_asset_path(raw_path):
                continue
            asset_path = _resolve_visual_asset_path(artifact, raw_path)
            if not asset_path.exists() or not asset_path.is_file():
                findings.append(
                    Finding(
                        rel_path=artifact.rel_path,
                        line_no=line_no,
                        code="missing_visual_asset_file",
                        message=f"Visual asset file is missing: {raw_path}",
                    )
                )
                continue
            if asset_path.stat().st_size <= 0:
                findings.append(
                    Finding(
                        rel_path=artifact.rel_path,
                        line_no=line_no,
                        code="empty_visual_asset_file",
                        message=f"Visual asset file is empty: {raw_path}",
                    )
                )

        if artifact.is_code_review and review_status in FINAL_REVIEW_STATUSES:
            visual_readback = evaluate_runtime_ui_visual_evidence(
                project_root=project_root or _artifact_repo_root(artifact.path),
                review_path=artifact.path,
                origin_plan=origin_plan,
                review_text="\n".join(artifact.lines) + "\n",
            )
            if visual_readback.state in {"red", "ambiguous"}:
                findings.append(
                    Finding(
                        rel_path=artifact.rel_path,
                        line_no=visual_anchor,
                        code=f"runtime_ui_visual_evidence_{visual_readback.state}",
                        message=(
                            "Terminal runtime-UI review requires independent comparator and complete-index "
                            "human proof with current-review-owned per-mode durable assets; reason_codes="
                            + ",".join(visual_readback.reason_codes)
                        ),
                    )
                )

        for provenance_error in evaluate_review_range_semantic_provenance(
            project_root=project_root or _artifact_repo_root(artifact.path),
            review_path=artifact.path,
            origin_plan=origin_plan,
            review_text="\n".join(artifact.lines) + "\n",
        ):
            findings.append(
                Finding(
                    rel_path=artifact.rel_path,
                    line_no=review_status_line,
                    code=provenance_error,
                    message="Review-range semantic provenance disagrees with the materialized plan/review visual contract.",
                )
            )

        for block in _iter_blocker_blocks(artifact):
            block_fields = _field_locations(block.lines)
            missing_blocker = [label for label in BLOCKER_FIELD_LABELS if label not in block_fields]
            if missing_blocker:
                findings.append(
                    Finding(
                        rel_path=artifact.rel_path,
                        line_no=block.line_no,
                        code="missing_blocker_fields",
                        message=f"{block.blocker_id} missing blocker fields: {', '.join(missing_blocker)}",
                    )
                )

        if artifact.is_merge_notes or review_status not in FINAL_REVIEW_STATUSES:
            continue

        missing_sections: list[str] = []
        lane_blocks: dict[str, SectionBlock] = {}
        for title_prefix, lane_label in REQUIRED_CODE_LANE_PREFIXES:
            section = _find_section_block(section_blocks, title_prefix)
            if section is None:
                missing_sections.append(lane_label)
                continue
            lane_blocks[lane_label] = section
        synthesis_block = _find_section_block(section_blocks, SYNTHESIS_TITLE_PREFIX)
        if synthesis_block is None:
            missing_sections.append("lane synthesis / aggregate verdict")
        if missing_sections:
            findings.append(
                Finding(
                    rel_path=artifact.rel_path,
                    line_no=review_status_line,
                    code="missing_final_lane_sections",
                    message=f"Final review status requires sections: {', '.join(missing_sections)}",
                )
            )
            continue
        assert synthesis_block is not None

        for lane_label, section in lane_blocks.items():
            lane_fields = _field_locations(section.lines)
            missing_lane_fields = [label for label in FINAL_LANE_FIELD_LABELS if label not in lane_fields]
            if missing_lane_fields:
                findings.append(
                    Finding(
                        rel_path=artifact.rel_path,
                        line_no=section.line_no,
                        code="missing_final_lane_fields",
                        message=f"{lane_label} missing final lane fields: {', '.join(missing_lane_fields)}",
                    )
                )

        synthesis_fields = _field_locations(synthesis_block.lines)
        synthesis_values = _field_values(synthesis_block.lines)
        missing_synthesis_fields = [label for label in FINAL_SYNTHESIS_FIELD_LABELS if label not in synthesis_fields]
        if missing_synthesis_fields:
            findings.append(
                Finding(
                    rel_path=artifact.rel_path,
                    line_no=synthesis_block.line_no,
                    code="missing_final_synthesis_fields",
                    message=f"Lane synthesis missing fields: {', '.join(missing_synthesis_fields)}",
                )
            )

        raw_lane_findings = _section_finding_ids(lane_blocks["reviewer_code_risk"]) + _section_finding_ids(
            lane_blocks["reviewer_code_contracts"]
        )
        is_no_findings_final = review_status == FINAL_OK_STATUS and not raw_lane_findings
        has_provenance_record = any(label in synthesis_fields for label in FINAL_SYNTHESIS_PROVENANCE_FIELD_LABELS)
        if raw_lane_findings or has_provenance_record or is_no_findings_final:
            missing_provenance_fields = [
                label for label in FINAL_SYNTHESIS_PROVENANCE_FIELD_LABELS if label not in synthesis_fields
            ]
            if missing_provenance_fields:
                findings.append(
                    Finding(
                        rel_path=artifact.rel_path,
                        line_no=synthesis_block.line_no,
                        code="missing_final_synthesis_provenance_fields",
                        message=f"Lane synthesis missing provenance fields: {', '.join(missing_provenance_fields)}",
                    )
                )
            elif is_no_findings_final:
                invalid_provenance_values = _validate_no_findings_provenance_values(synthesis_values)
                if invalid_provenance_values:
                    findings.append(
                        Finding(
                            rel_path=artifact.rel_path,
                            line_no=synthesis_block.line_no,
                            code="invalid_final_no_findings_provenance",
                            message=(
                                "Lane synthesis no-findings provenance has invalid values: "
                                f"{', '.join(invalid_provenance_values)}"
                            ),
                        )
                    )

        if require_dual_lane_origin and _is_dual_lane_review(section_blocks):
            origin_plan_path: Path | None
            origin_line: int
            origin_state: str | None
            if _is_merge_range_review_artifact(artifact):
                review_snapshot, review_snapshot_line = _strict_target_snapshot(artifact)
                if review_snapshot is None:
                    findings.append(
                        Finding(
                            rel_path=artifact.rel_path,
                            line_no=review_snapshot_line,
                            code="missing_review_target_snapshot",
                            message=(
                                "Final merge-range dual-lane review requires a non-empty top-level "
                                "`**Target:**` carrier. `**Range:**` is legacy-only fallback and is not accepted here."
                            ),
                        )
                    )

                spec_value, spec_line, spec_state, spec_plan_rel = _spec_carrier(artifact)
                if spec_state == "missing":
                    findings.append(
                        Finding(
                            rel_path=artifact.rel_path,
                            line_no=spec_line,
                            code="missing_review_spec",
                            message=(
                                "Final merge-range dual-lane review requires top-level `**Spec:** docs/plans/...` "
                                f"or exact `{MANUAL_NO_ORIGIN_SPEC}` for manual no-origin reviews."
                            ),
                        )
                    )
                    continue
                if spec_state == "invalid":
                    findings.append(
                        Finding(
                            rel_path=artifact.rel_path,
                            line_no=spec_line,
                            code="invalid_review_spec",
                            message=(
                                f"Invalid `**Spec:**` carrier {spec_value!r}; expected `docs/plans/...md` "
                                f"or exact `{MANUAL_NO_ORIGIN_SPEC}`."
                            ),
                        )
                    )
                    continue
                if spec_state == "manual_no_origin":
                    if origin_plan is not None and str(origin_plan).strip():
                        findings.append(
                            Finding(
                                rel_path=artifact.rel_path,
                                line_no=spec_line,
                                code="manual_no_origin_with_origin_plan",
                                message=(
                                    f"`**Spec:** {MANUAL_NO_ORIGIN_SPEC}` is only valid for manual no-origin "
                                    "range reviews. Do not use it when `--origin-plan` is supplied."
                                ),
                            )
                        )
                    continue

                assert spec_plan_rel is not None
                origin_line = spec_line
                root = project_root or _artifact_repo_root(artifact.path)
                origin_plan_path = (root / spec_plan_rel).resolve()
                if not _path_is_within_project_root(origin_plan_path, root):
                    findings.append(
                        Finding(
                            rel_path=artifact.rel_path,
                            line_no=spec_line,
                            code="origin_plan_outside_project_root",
                            message=(
                                "Review `**Spec:**` must resolve inside the caller-resolved project root: "
                                f"plan={origin_plan_path}; project_root={root.resolve()}."
                            ),
                        )
                    )
                    continue
                if origin_plan is not None:
                    raw_origin = str(origin_plan).strip()
                    if raw_origin:
                        cli_origin = Path(raw_origin)
                        cli_origin_path = (cli_origin if cli_origin.is_absolute() else root / cli_origin).resolve()
                        if not _path_is_within_project_root(cli_origin_path, root):
                            findings.append(
                                Finding(
                                    rel_path=artifact.rel_path,
                                    line_no=spec_line,
                                    code="origin_plan_outside_project_root",
                                    message=(
                                        "`--origin-plan` must resolve inside the caller-resolved project root: "
                                        f"plan={cli_origin_path}; project_root={root.resolve()}."
                                    ),
                                )
                            )
                            continue
                        if cli_origin_path != origin_plan_path:
                            findings.append(
                                Finding(
                                    rel_path=artifact.rel_path,
                                    line_no=spec_line,
                                    code="origin_plan_spec_mismatch",
                                    message=(
                                        "`--origin-plan` does not match the review `**Spec:**` carrier: "
                                        f"origin={_relative_path(root, cli_origin_path)}; spec={spec_plan_rel}."
                                    ),
                                )
                            )
                            continue
                review_snapshot_source = "Target"
            else:
                origin_plan_path, origin_line, origin_state = _resolve_origin_plan(
                    artifact,
                    project_root=project_root,
                    origin_plan=origin_plan,
                )
                review_snapshot, review_snapshot_line, review_snapshot_source = _review_snapshot(artifact)
                if origin_state in {"missing", "multiple"}:
                    findings.append(
                        Finding(
                            rel_path=artifact.rel_path,
                            line_no=origin_line,
                            code="missing_dual_lane_origin_plan",
                            message=(
                                "Final dual-lane review requires explicit origin plan via "
                                "`--origin-plan PLAN_PATH` or exactly one `PLAN=docs/plans/...` in `**Target:**`."
                            ),
                        )
                    )
                    continue
                if origin_state == "outside":
                    root = project_root or _artifact_repo_root(artifact.path)
                    findings.append(
                        Finding(
                            rel_path=artifact.rel_path,
                            line_no=origin_line,
                            code="origin_plan_outside_project_root",
                            message=(
                                "`origin_plan` must resolve inside the caller-resolved project root: "
                                f"plan={origin_plan_path}; project_root={root.resolve()}."
                            ),
                        )
                    )
                    continue

            if origin_plan_path is not None and not origin_plan_path.exists():
                findings.append(
                    Finding(
                        rel_path=artifact.rel_path,
                        line_no=origin_line,
                        code="missing_dual_lane_origin_plan_file",
                        message=f"Origin plan does not exist: {_relative_path(project_root or _artifact_repo_root(artifact.path), origin_plan_path)}",
                    )
                )
            elif origin_plan_path is not None:
                root = project_root or _artifact_repo_root(artifact.path)
                current_proof = plan_lint.preflight_current_review_proof(
                    origin_plan_path,
                    project_root=root,
                )
                is_live_current_artifact = (
                    current_proof.review_path is not None
                    and Path(current_proof.review_path).resolve() == artifact.path.resolve()
                    and current_proof.state in {"current_green", "blocked"}
                )
                if is_live_current_artifact:
                    if current_proof.state == "blocked":
                        findings.append(
                            Finding(
                                rel_path=artifact.rel_path,
                                line_no=review_snapshot_line,
                                code=current_proof.reason_code or "current_review_proof_blocked",
                                message=current_proof.message,
                            )
                        )
                        findings.extend(
                            Finding(
                                rel_path=artifact.rel_path,
                                line_no=origin_line,
                                code=diagnostic.code,
                                message=diagnostic.message,
                            )
                            for diagnostic in current_proof.diagnostics
                        )
                    # A green current proof already owns strict Target,
                    # compact/support, and producer parity.  Do not recreate
                    # those checks in this facade.
                else:
                    # Historical and range artifacts retain the compatibility
                    # selector/support path.  They are not current-proof
                    # authority and therefore do not enter the strict reader.
                    risk_selection = plan_lint.select_plan_risk_lane_snapshot(origin_plan_path)
                    if risk_selection.error_code:
                        findings.append(
                            Finding(
                                rel_path=artifact.rel_path,
                                line_no=origin_line,
                                code=risk_selection.error_code,
                                message=risk_selection.message or "Origin plan risk lane selection is ambiguous.",
                            )
                        )
                    elif risk_selection.snapshot is None:
                        findings.append(
                            Finding(
                                rel_path=artifact.rel_path,
                                line_no=origin_line,
                                code="missing_plan_resident_risk_lane",
                                message=(
                                    "Origin plan is missing a plan-resident `reviewer_code_risk` lane-run JSON block "
                                    "with parseable `target_snapshot`; projection blocks are not accepted."
                                ),
                            )
                        )
                    elif review_snapshot is None:
                        findings.append(
                            Finding(
                                rel_path=artifact.rel_path,
                                line_no=review_snapshot_line,
                                code="missing_review_target_snapshot",
                                message="Final dual-lane review requires `**Target:**` or fallback `**Range:**` for snapshot parity.",
                            )
                        )
                    elif risk_selection.snapshot != review_snapshot:
                        findings.append(
                            Finding(
                                rel_path=artifact.rel_path,
                                line_no=review_snapshot_line,
                                code="dual_lane_target_snapshot_mismatch",
                                message=(
                                    "Plan-resident `reviewer_code_risk.target_snapshot` does not match review "
                                    f"`**{review_snapshot_source}:**`: plan={risk_selection.snapshot!r}; review={review_snapshot!r}."
                                ),
                            )
                        )
                    else:
                        command_paths = tuple(_iter_homebrew_command_payload_paths(risk_selection.payload or {}))
                        if command_paths:
                            findings.append(
                                Finding(
                                    rel_path=artifact.rel_path,
                                    line_no=origin_line,
                                    code=HOMEBREW_COMMAND_EVIDENCE_CODE,
                                    message=(
                                        "Selected plan-resident `reviewer_code_risk` payload contains expanded "
                                        "owner-local Homebrew interpreter command evidence at "
                                        f"{', '.join(command_paths)}; record `$PYBIN ...` or `python3 ...` instead."
                                    ),
                                )
                            )
                        findings.extend(
                            Finding(
                                rel_path=artifact.rel_path,
                                line_no=origin_line,
                                code=diagnostic.code,
                                message=diagnostic.message,
                            )
                            for diagnostic in plan_lint.preflight_selected_risk_lane_support(
                                origin_plan_path,
                                risk_selection,
                                project_root=root,
                            )
                        )

        if review_status != FINAL_BLOCKER_STATUS:
            continue

        if raw_lane_findings and not _section_has_canonical_blocker_ref(synthesis_block):
            findings.append(
                Finding(
                    rel_path=artifact.rel_path,
                    line_no=synthesis_block.line_no,
                    code="missing_canonical_blocker_refs",
                    message="Final `❌ S1 blocker(ы)` with lane findings requires canonical `B<N>` refs in `Lane synthesis / aggregate verdict`",
                )
            )

    return sorted(findings, key=lambda item: (item.rel_path, item.line_no, item.code))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lint bounded review-artifact grammar families.")
    parser.add_argument(
        "--project-root",
        default=None,
        help="Repo root for resolving relative paths (legacy defaults to this repository).",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Files or directories to lint. Defaults to shared review templates only.",
    )
    parser.add_argument(
        "--origin-plan",
        default=None,
        help="Explicit origin PLAN_PATH for final dual-lane review snapshot parity checks.",
    )
    parser.add_argument(
        "--select-risk-lane",
        action="store_true",
        help="Print helper-backed current reviewer_code_risk lane selection readback for --origin-plan.",
    )
    parser.add_argument(
        "--historical-diff-check-readback",
        action="store_true",
        help="Read one opt-in historical merge-range disposition without rewriting the raw Git verdict.",
    )
    parser.add_argument(
        "--as-status",
        default=None,
        help="Required projection status for --historical-diff-check-readback: Ready for Arch review or Done.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON for readback modes.",
    )
    args = parser.parse_args(argv)
    if args.select_risk_lane and args.historical_diff_check_readback:
        parser.error("--select-risk-lane and --historical-diff-check-readback are mutually exclusive")
    if args.historical_diff_check_readback:
        if not args.origin_plan:
            parser.error("--historical-diff-check-readback requires --origin-plan PLAN")
        if not args.json:
            parser.error("--historical-diff-check-readback requires --json")
        if len(args.paths) != 1:
            parser.error("--historical-diff-check-readback requires exactly one review artifact path")
        if args.as_status not in {"Ready for Arch review", "Done"}:
            parser.error('--historical-diff-check-readback requires --as-status "Ready for Arch review" or "Done"')
    elif args.as_status is not None:
        parser.error("--as-status is only valid with --historical-diff-check-readback")
    if args.select_risk_lane:
        if not args.origin_plan:
            parser.error("--select-risk-lane requires --origin-plan PLAN")
        if not args.json:
            parser.error("--select-risk-lane requires --json")
        if args.paths:
            parser.error("--select-risk-lane does not accept review artifact paths")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        context = (
            resolve_top_level_context(Path(args.project_root))
            if args.project_root
            else resolve_top_level_context()
        )
    except ContractAuthorityError as exc:
        print(f"contract_authority_preflight_failed:{exc.reason_code}")
        return 2
    # Keep the captured context with every direct CLI branch.  Legacy default
    # templates remain tooling-owned in ``_default_template_scope``; using the
    # discovered root here only avoids a second, unrelated context resolution.
    project_root = context.project_root.resolve()
    if args.historical_diff_check_readback:
        readback = evaluate_historical_diff_check_disposition(
            project_root=project_root,
            review_path=args.paths[0],
            origin_plan=args.origin_plan,
            as_status=args.as_status,
        )
        print(json.dumps(readback.as_dict(), ensure_ascii=False, sort_keys=True))
        return 0 if readback.state in {"raw_green", "verified_pending_architect", "accepted"} else 1
    if args.select_risk_lane:
        origin_plan_path, origin_in_project_root = _selector_origin_plan_path(project_root, args.origin_plan)
        support_diagnostics: tuple[plan_lint.RiskLaneSupportDiagnostic, ...] = ()
        if not origin_in_project_root:
            selection = plan_lint.PlanRiskLaneSelection(
                snapshot=None,
                line_no=1,
                payload=None,
                error_code="origin_plan_outside_project_root",
                message=(
                    "`origin_plan` must resolve inside the caller-resolved project root: "
                    f"plan={origin_plan_path}; project_root={project_root}."
                ),
            )
        else:
            selection = plan_lint.select_plan_risk_lane_snapshot(origin_plan_path)
            support_diagnostics = plan_lint.preflight_selected_risk_lane_support(
                origin_plan_path,
                selection,
                project_root=project_root,
            )
        payload = _risk_lane_selection_payload(
            selection=selection,
            origin_plan_path=origin_plan_path,
            project_root=project_root,
            support_diagnostics=support_diagnostics,
        )
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0 if payload["state"] == "selected" else 1

    try:
        artifacts = load_review_artifacts(
            project_root,
            args.paths,
            context=context,
        )
    except (FileNotFoundError, ContractAuthorityError, ValueError) as exc:
        print(str(exc))
        return 2

    findings = lint_review_artifacts(
        artifacts,
        project_root=project_root,
        origin_plan=args.origin_plan,
        require_dual_lane_origin=True,
    )
    if findings:
        for finding in findings:
            print(finding.render())
        return 1

    print("review-artifact-lint: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Lint bounded post-merge audit carriers."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import importlib
import os
from pathlib import Path
import re
import sys
from typing import TYPE_CHECKING, Any, Sequence

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

import retrieval_telemetry_receipt
import censor_receipts_harvest
import review_artifact_lint
from review_schema_contract import CURRENT_REVIEW_SCHEMA_VERSION

DEFAULT_TEMPLATE_SCOPE: tuple[Path, ...] = (
    REPO_ROOT / "docs" / "reviews" / "_template_post_merge_audit.md",
)
_DEFAULT_TEMPLATE_RELATIVE_PATHS: tuple[str, ...] = (
    "docs/reviews/_template_post_merge_audit.md",
)

H1_RE = re.compile(r"^\s*#\s+(?P<title>.+?)\s*$")
H2_RE = re.compile(r"^\s*##\s+(?P<title>.+?)\s*$")
H3_RE = re.compile(r"^\s*###\s+(?P<title>.+?)\s*$")
SCHEMA_VERSION_HEADER_RE = re.compile(r"^\s*\*\*Schema version:\*\*\s*(?P<value>.+?)\s*$", re.IGNORECASE)
STATUS_HEADER_RE = re.compile(r"^\s*\*\*Status:\*\*\s*(?P<value>.+?)\s*$", re.IGNORECASE)
SPACE_RE = re.compile(r"\s+")

FOLLOWUP_CARRIER_PHRASE = "lost follow-up during harvest/promotion"
AUDIT_MATRIX_TITLE = "audit matrix (summary)"
LANE_SYNTHESIS_TITLE = "lane synthesis / aggregate verdict"
ROLE_ASSESSMENT_TITLES = (
    "role assessment (censor receipts, if applicable)",
    "role assessment (censor receipts)",
)
ROLE_ASSESSMENT_HELPER_SUMMARY_RE = re.compile(r"^\s*-\s*Helper summary:\s*(?P<body>.+?)\s*$", re.IGNORECASE)
ROLE_ASSESSMENT_HELPER_ROLE_QUALITY_RE = re.compile(r"^\s*-\s*Helper role-quality:\s*(?P<body>.+?)\s*$", re.IGNORECASE)
ROLE_ASSESSMENT_ASSESSMENT_RE = re.compile(r"^\s*-\s*Assessment:\s*(?P<body>.+?)\s*$", re.IGNORECASE)
ROLE_ASSESSMENT_RECEIPT_SOURCE_RE = re.compile(r"^\s*-\s*Receipt source:\s*(?P<body>.+?)\s*$", re.IGNORECASE)
COUNTER_RE = re.compile(r"(?P<key>[A-Za-z /-]+?)\s*=\s*(?P<value>\d+)")
HELPER_SUMMARY_COUNTER_KEYS = (
    "receipts",
    "complete",
    "partial",
    "missing",
    "unconfirmed",
)
HELPER_ROLE_QUALITY_COUNTER_KEYS = tuple(SPACE_RE.sub(" ", key.lower()).strip() for key in censor_receipts_harvest.ROLE_QUALITY_CATEGORIES)
DERIVED_INDEX_BUILD_TOKEN = "planveyor_docs_index_build all"
DERIVED_INDEX_CHECK_TOKEN = "docs_context_check"
LANE_SYNTHESIS_SOURCE_TOKEN = "lane synthesis source"
PROVENANCE_FIELD_TOKENS = (
    "source_lane",
    "lane_finding_id",
    "synthesis_disposition",
    "canonical_ref",
    "audit_status",
    "followup_plan",
)
DERIVED_INDEX_SUMMARY_RE = {
    "plans": re.compile(r"(plans\s*:\s*covered=\d+.*uncovered=\d+|docs_context_check.*corpus=plans.*covered=\d+.*uncovered=\d+)", re.IGNORECASE),
    "followups": re.compile(
        r"(followups\s*:\s*covered=\d+.*uncovered=\d+|docs_context_check.*corpus=followups.*covered=\d+.*uncovered=\d+)",
        re.IGNORECASE,
    ),
}
POST_MERGE_RECEIPT_CITATIONS_TITLE = "post-merge audit receipt citations"
FOLLOWUPS_TRACKED_POINTER_TOKEN = "already tracked elsewhere"
FOLLOWUPS_TRACKED_POINTER_TARGETS = (
    "docs/followups/",
    "docs/plans/",
)
FOLLOWUPS_CLOSEOUT_FIELD_RE = re.compile(
    r"\b(?:manual_decision_ref|already_tracked_ref)\b\s*[:=]\s*`?"
    r"(?P<ref>[^\s`<>)\],;]+)",
    re.IGNORECASE,
)
FOLLOWUPS_REF_TOKEN_RE = re.compile(r"`?(?P<ref>docs/(?:followups|plans)/[^\s`<>)\],;]+)", re.IGNORECASE)
FOLLOWUPS_DURABLE_REF_RE = re.compile(
    r"docs/(?:followups|plans)/[^\s`<>)\],;]+?\.md(?:#[A-Za-z0-9_.\-/]+|:\d+)?",
    re.IGNORECASE,
)
FOLLOWUPS_CLEANUP_CLAIM_RE = re.compile(
    r"(cleanup[-\s]?readiness|cleanup[-\s]?ready|handled follow-?ups|handled followups|follow-?ups handled)",
    re.IGNORECASE,
)
AUDIT_RECEIPT_CITATION_TOKENS = (
    ("audit_matrix", ("Audit matrix",)),
    ("role_quality", ("Role-quality", "Role assessment")),
    ("followup_harvest_triage_import", ("Follow-up harvest triage/import receipt",)),
    ("process_improvement_decision_state", ("Process-improvement promotion decisions",)),
    ("docs_retrieval_metrics", ("Docs retrieval metrics receipt",)),
    ("docs_index_context", ("docs_index_context", "docs_context_check")),
    ("packetization_gate", ("step:packetization_gate",)),
)
COMPACT_NO_FINDINGS_TITLE = "compact no-findings mode"
COMPACT_MODE_ENABLED_RE = re.compile(r"\bcompact_mode\b\s*[:=]\s*`?enabled`?\b", re.IGNORECASE)
COMPACT_FIELD_RE = re.compile(
    r"^\s*(?:[-*]\s*)?`?(?P<key>[a-z][a-z0-9_-]*)`?\s*[:=]\s*`?(?P<value>.+?)`?\s*$",
    re.IGNORECASE,
)
COMPACT_REQUIRED_FIELDS = (
    "compact_mode",
    "review_status",
    "findings",
    "live_blocker_lineage",
    "role_quality_candidate",
    "process_improvements",
    "followups",
    "packetization",
    "ready_to_push",
    "docs_index_context",
    "receipt_citations",
    "producer_authority",
)
COMPACT_RESIDUAL_FIELDS = (
    "process_improvements",
    "followups",
    "packetization",
    "ready_to_push",
    "docs_index_context",
    "receipt_citations",
)
COMPACT_BAD_VALUE_RE = re.compile(
    r"\b(missing|ambiguous|red|pending|blocked|unconfirmed|tbd|unknown|unclear|stale|inconsistent)\b|\bnot\s+clear\b|❌",
    re.IGNORECASE,
)
COMPACT_FINDING_RE = re.compile(r"\bS[1-3]\b|live\s+finding|finding[s]?\s*[:=]\s*(present|open|red)", re.IGNORECASE)
COMPACT_BLOCKER_REF_RE = re.compile(r"#B\d+\b", re.IGNORECASE)
FIELD_LINE_RE = re.compile(
    r"^\s*(?:[-*]\s*)?`?(?P<key>[A-Za-z][A-Za-z0-9_ /-]*)`?\s*:\s*(?P<value>.+?)\s*$",
    re.IGNORECASE,
)
LIVE_BLOCKER_REF_RE = re.compile(r"(?:#|:|\b)B\d+\b|❌", re.IGNORECASE)
BLOCKER_NONLIVE_PROOF_RE = re.compile(
    r"^(?:historical|closed|superseded|closed_by_same_file_rewrite)(?:\s+blocker)?(?:\s+proof)?\s*[:=]\s*(?P<proof>.+?)\s*$",
    re.IGNORECASE,
)
BLOCKER_NONLIVE_PROOF_REF_RE = re.compile(
    r"docs/(?:plans|followups|reviews|code_reviews)/[^\s`<>)\],;]+?\.md(?:#[A-Za-z0-9_.\-/]+|:\d+)?"
    r"|(?:manual_decision_ref|already_tracked_ref|proof_ref|canonical_ref|evidence_ref)\s*[:=]\s*[^\s`<>)\],;]+",
    re.IGNORECASE,
)
FOLLOWUP_TERMINAL_PROOF_RE = re.compile(
    r"^(?:terminal|handled|closed|done|closed_by_same_file_rewrite)(?:\s+proof)?\s*[:=]\s*(?P<proof>.+?)\s*$",
    re.IGNORECASE,
)
FOLLOWUP_TERMINAL_PROOF_REF_RE = re.compile(
    r"docs/(?:plans|followups|reviews|code_reviews)/[^\s`<>)\],;]+?\.md(?:#[A-Za-z0-9_.\-/]+|:\d+)?"
    r"|(?:manual_decision_ref|already_tracked_ref|proof_ref|canonical_ref|evidence_ref)\s*[:=]\s*[^\s`<>)\],;]+",
    re.IGNORECASE,
)
TERMINAL_SYNTHESIS_DISPOSITIONS = frozenset(
    (
        "accepted",
        "no_findings",
        "superseded",
        "closed_by_same_file_rewrite",
    )
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
class AuditArtifact:
    path: Path
    rel_path: str
    lines: tuple[str, ...]
    first_heading: str | None


@dataclass(frozen=True)
class AuditStatusRow:
    line_no: int
    fields: dict[str, tuple[int, str]]


def _normalize_text(value: str) -> str:
    return SPACE_RE.sub(" ", value.lower()).strip()


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


def _is_post_merge_audit(path: Path, first_heading: str | None) -> bool:
    if path.name == "_template_post_merge_audit.md":
        return True
    if "_post_merge_audit_" in path.name:
        return True
    if first_heading is None:
        return False
    return "post-merge audit" in first_heading


def _default_template_scope(context: ContractContext) -> tuple[Path, ...]:
    if context.state != "engaged":
        return DEFAULT_TEMPLATE_SCOPE
    return tuple(
        require_declared_read(context, relative_path, purpose="post-merge audit template")
        for relative_path in _DEFAULT_TEMPLATE_RELATIVE_PATHS
    )


def _expand_paths(
    root: Path,
    raw_paths: Sequence[str],
    *,
    context: ContractContext,
) -> list[Path]:
    candidates = list(_default_template_scope(context) if not raw_paths else ())
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
            raise FileNotFoundError(f"Missing audit artifact path: {path}")
        if path.is_dir():
            for child in sorted(path.rglob("*.md")):
                add_path(child)
            continue
        add_path(path)

    return candidates


def load_audit_artifacts(
    project_root: Path,
    raw_paths: Sequence[str] | None = None,
    *,
    context: ContractContext | None = None,
) -> list[AuditArtifact]:
    root = project_root.resolve()
    resolved_context = context_for_reader(root, context=context)
    raw_paths = [] if raw_paths is None else list(raw_paths)
    artifacts: list[AuditArtifact] = []
    use_declared_templates = resolved_context.state == "engaged" and not raw_paths
    for path in _expand_paths(root, raw_paths, context=resolved_context):
        if use_declared_templates:
            try:
                relative_path = path.resolve().relative_to(resolved_context.contract_root).as_posix()
            except ValueError as exc:  # pragma: no cover - require_declared_read already enforces this.
                raise ValueError(f"Declared audit template escapes contract root: {path}") from exc
            text = read_declared_text(
                resolved_context,
                relative_path,
                purpose="post-merge audit template",
            )
        else:
            text = path.read_text(encoding="utf-8", errors="replace")
        lines = tuple(text.splitlines())
        first_heading = _first_heading(lines)
        if not _is_post_merge_audit(path, first_heading):
            continue
        artifacts.append(
            AuditArtifact(
                path=path,
                rel_path=_relative_path(root, path),
                lines=lines,
                first_heading=first_heading,
            )
        )
    return artifacts


def _find_line(lines: Sequence[str], pattern: str) -> int | None:
    needle = pattern.lower()
    for line_no, line in enumerate(lines, start=1):
        if needle in line.lower():
            return line_no
    return None


def _heading_locations(lines: Sequence[str]) -> dict[str, int]:
    locations: dict[str, int] = {}
    for line_no, line in enumerate(lines, start=1):
        match = H2_RE.match(line)
        if not match:
            continue
        title = _normalize_text(match.group("title"))
        locations.setdefault(title, line_no)
    return locations


def _section_lines(lines: Sequence[str], section_title: str) -> list[tuple[int, str]]:
    collected: list[tuple[int, str]] = []
    current_h2: str | None = None
    for line_no, line in enumerate(lines, start=1):
        match = H2_RE.match(line)
        if match:
            current_h2 = _normalize_text(match.group("title"))
            continue
        if current_h2 == section_title:
            collected.append((line_no, line))
    return collected


def _field_key(raw_key: str) -> str:
    normalized = _normalize_text(raw_key.replace("`", "").replace("-", "_").replace("/", " "))
    return normalized.replace(" ", "_")


def _clean_field_value(raw_value: str) -> str:
    value = raw_value.strip()
    while value and value[-1] in ".;":
        value = value[:-1].strip()
    if len(value) >= 2 and value[0] == "`" and value[-1] == "`":
        value = value[1:-1].strip()
    return value


def _parse_field_line(line: str) -> tuple[str, str] | None:
    match = FIELD_LINE_RE.match(line)
    if not match:
        return None
    return _field_key(match.group("key")), _clean_field_value(match.group("value"))


def _is_noop_value(value: str) -> bool:
    normalized = _normalize_text(value.replace("`", ""))
    return normalized in {"n/a", "none"} or normalized.startswith("n/a ") or normalized.startswith("n/a (")


def _artifact_project_root(artifact: AuditArtifact) -> Path:
    rel_path = Path(artifact.rel_path)
    if rel_path.is_absolute():
        return REPO_ROOT
    root = artifact.path.resolve()
    for _ in rel_path.parts:
        root = root.parent
    return root


def _audit_matrix_rows(artifact: AuditArtifact) -> list[AuditStatusRow]:
    rows: list[AuditStatusRow] = []
    current_line: int | None = None
    current_fields: dict[str, tuple[int, str]] = {}
    for line_no, line in _section_lines(artifact.lines, AUDIT_MATRIX_TITLE):
        if H3_RE.match(line):
            if current_fields:
                rows.append(AuditStatusRow(line_no=current_line or line_no, fields=current_fields))
            current_line = line_no
            current_fields = {}
            continue

        parsed = _parse_field_line(line)
        if parsed is None:
            continue
        key, value = parsed
        if key not in {
            "lane_synthesis_source",
            "source_lane",
            "lane_finding_id",
            "synthesis_disposition",
            "canonical_ref",
            "audit_status",
            "followup_plan",
            "blocker_refs",
        }:
            continue
        if current_line is None:
            current_line = line_no
        current_fields[key] = (line_no, value)

    if current_fields:
        rows.append(AuditStatusRow(line_no=current_line or 1, fields=current_fields))
    return rows


def _extract_ref_path(value: str) -> str | None:
    cleaned = _clean_field_value(value)
    if _is_noop_value(cleaned) or _normalize_text(cleaned) == "unconfirmed":
        return None
    path_text = cleaned.split("#", 1)[0].strip().strip("`")
    if not path_text.endswith(".md"):
        return None
    return path_text


def _source_path_for_row(artifact: AuditArtifact, source_value: str) -> Path | None:
    path_text = _extract_ref_path(source_value)
    if path_text is None:
        return None
    path = Path(path_text)
    if path.is_absolute():
        return path
    return (_artifact_project_root(artifact) / path).resolve()


def _lane_synthesis_records(lines: Sequence[str]) -> list[AuditStatusRow] | None:
    section = _section_lines(lines, LANE_SYNTHESIS_TITLE)
    if not section:
        return None

    records: list[AuditStatusRow] = []
    current_line: int | None = None
    current_fields: dict[str, tuple[int, str]] = {}
    for line_no, line in section:
        parsed = _parse_field_line(line)
        if parsed is None:
            if "finding:" in line.lower() and current_fields:
                records.append(AuditStatusRow(line_no=current_line or line_no, fields=current_fields))
                current_line = line_no
                current_fields = {}
            continue
        key, value = parsed
        if key not in PROVENANCE_FIELD_TOKENS:
            continue
        if key in current_fields and current_fields:
            records.append(AuditStatusRow(line_no=current_line or line_no, fields=current_fields))
            current_line = line_no
            current_fields = {}
        if current_line is None:
            current_line = line_no
        current_fields[key] = (line_no, value)

    if current_fields:
        records.append(AuditStatusRow(line_no=current_line or 1, fields=current_fields))
    return records


def _normalized_row_value(row: AuditStatusRow, key: str) -> str:
    value = row.fields.get(key)
    if value is None:
        return ""
    return _normalize_text(value[1].replace("`", ""))


def _row_value(row: AuditStatusRow, key: str) -> str:
    value = row.fields.get(key)
    return "" if value is None else value[1]


def _source_records_matching_row(row: AuditStatusRow, records: Sequence[AuditStatusRow]) -> list[AuditStatusRow]:
    lane_finding_id = _normalized_row_value(row, "lane_finding_id")
    if not lane_finding_id:
        return []
    return [record for record in records if _normalized_row_value(record, "lane_finding_id") == lane_finding_id]


def _has_live_blocker_ref(value: str) -> bool:
    normalized = _normalize_text(value.replace("`", ""))
    if not normalized or _is_noop_value(normalized):
        return False
    if "no live blocker" in normalized:
        return False
    proof_match = BLOCKER_NONLIVE_PROOF_RE.match(value.replace("`", "").strip())
    if proof_match is not None:
        proof = proof_match.group("proof").strip()
        if proof and not _is_noop_value(proof) and BLOCKER_NONLIVE_PROOF_REF_RE.search(proof):
            return False
    if LIVE_BLOCKER_REF_RE.search(value) is not None:
        return True
    if any(token in normalized for token in ("historical", "closed", "superseded")):
        return False
    return "live blocker" in normalized


def _has_nonterminal_followup(value: str) -> bool:
    normalized = _normalize_text(value.replace("`", ""))
    if not normalized or _is_noop_value(normalized):
        return False
    match = FOLLOWUP_TERMINAL_PROOF_RE.match(value.replace("`", "").strip())
    if match is None:
        return True
    proof = match.group("proof").strip()
    if not proof or _is_noop_value(proof):
        return True
    return FOLLOWUP_TERMINAL_PROOF_REF_RE.search(proof) is None


def _lint_current_audit_status_authority(artifact: AuditArtifact) -> list[Finding]:
    if artifact.path.name == "_template_post_merge_audit.md":
        return []

    findings: list[Finding] = []
    for row in _audit_matrix_rows(artifact):
        source = row.fields.get("lane_synthesis_source")
        audit_status = _normalized_row_value(row, "audit_status")
        synthesis_disposition = _normalized_row_value(row, "synthesis_disposition")
        blocker_refs = _row_value(row, "blocker_refs")
        followup_plan = _row_value(row, "followup_plan")

        if source is None:
            continue

        source_path = _source_path_for_row(artifact, source[1])
        if source_path is None or not source_path.exists():
            if audit_status == "done":
                findings.append(
                    Finding(
                        rel_path=artifact.rel_path,
                        line_no=source[0],
                        code="audit_status_source_missing",
                        message=(
                            "Current post-merge audit rows must cite a readable local review artifact before "
                            "`audit_status=done` can be treated as derived truth."
                        ),
                    )
                )
            continue

        source_lines = tuple(source_path.read_text(encoding="utf-8", errors="replace").splitlines())
        if audit_status == "done":
            visual_readback = review_artifact_lint.evaluate_runtime_ui_visual_evidence(
                project_root=_artifact_project_root(artifact),
                review_path=source_path,
                review_text="\n".join(source_lines) + "\n",
            )
            if visual_readback.state in {"red", "ambiguous"}:
                findings.append(
                    Finding(
                        rel_path=artifact.rel_path,
                        line_no=source[0],
                        code="audit_status_done_conflicts_with_visual_evidence",
                        message=(
                            "`audit_status=done` cannot override authoritative runtime-UI visual evidence "
                            f"state={visual_readback.state}; reason_codes="
                            + ",".join(visual_readback.reason_codes)
                        ),
                    )
                )
        source_records = _lane_synthesis_records(source_lines)
        if source_records is None:
            if audit_status == "done":
                findings.append(
                    Finding(
                        rel_path=artifact.rel_path,
                        line_no=source[0],
                        code="audit_status_source_missing_lane_synthesis",
                        message=(
                            "Cited review artifact is missing `## Lane synthesis / aggregate verdict`; "
                            "`audit_status=done` fails closed."
                        ),
                    )
                )
            continue

        matches = _source_records_matching_row(row, source_records)
        if len(matches) != 1:
            if audit_status == "done":
                code = "audit_status_source_ambiguous" if len(matches) > 1 else "audit_status_source_missing_record"
                findings.append(
                    Finding(
                        rel_path=artifact.rel_path,
                        line_no=row.line_no,
                        code=code,
                        message=(
                            "`audit_status=done` row must match exactly one cited lane-synthesis record "
                            f"by `lane_finding_id`; matched={len(matches)}."
                        ),
                    )
                )
            continue

        source_disposition = _normalized_row_value(matches[0], "synthesis_disposition")
        if source_disposition and synthesis_disposition and source_disposition != synthesis_disposition:
            findings.append(
                Finding(
                    rel_path=artifact.rel_path,
                    line_no=row.fields.get("synthesis_disposition", (row.line_no, ""))[0],
                    code="audit_status_source_mismatch",
                    message=(
                        "`synthesis_disposition` in the audit row does not match the cited live review "
                        f"artifact ({synthesis_disposition!r} != {source_disposition!r})."
                    ),
                )
            )

        if audit_status != "done":
            continue

        if synthesis_disposition not in TERMINAL_SYNTHESIS_DISPOSITIONS:
            findings.append(
                Finding(
                    rel_path=artifact.rel_path,
                    line_no=row.fields.get("audit_status", (row.line_no, ""))[0],
                    code="audit_status_done_conflicts_with_source",
                    message=(
                        "`audit_status=done` requires terminal green source synthesis; "
                        f"got `synthesis_disposition={synthesis_disposition or 'missing'}`."
                    ),
                )
            )
        if _has_live_blocker_ref(blocker_refs):
            findings.append(
                Finding(
                    rel_path=artifact.rel_path,
                    line_no=row.fields.get("blocker_refs", (row.line_no, ""))[0],
                    code="audit_status_done_with_live_blocker",
                    message="`audit_status=done` is invalid while live blocker refs remain in the audit row.",
                )
            )
        if _has_nonterminal_followup(followup_plan):
            findings.append(
                Finding(
                    rel_path=artifact.rel_path,
                    line_no=row.fields.get("followup_plan", (row.line_no, ""))[0],
                    code="audit_status_done_with_nonterminal_followup",
                    message="`audit_status=done` requires `followup_plan: N/A` or explicit terminal/handled proof.",
                )
            )

    return findings


def _compact_section_fields(
    lines: Sequence[str],
) -> tuple[int | None, dict[str, tuple[int, str]], dict[str, list[tuple[int, str]]]]:
    headings = _heading_locations(lines)
    section_start = headings.get(COMPACT_NO_FINDINGS_TITLE)
    if section_start is None:
        return None, {}, {}
    fields: dict[str, tuple[int, str]] = {}
    occurrences: dict[str, list[tuple[int, str]]] = {}
    for line_no, line in _section_lines(lines, COMPACT_NO_FINDINGS_TITLE):
        match = COMPACT_FIELD_RE.match(line)
        if not match:
            continue
        key = match.group("key").strip().lower().replace("-", "_")
        value = match.group("value").strip().strip("`")
        occurrences.setdefault(key, []).append((line_no, value))
        fields.setdefault(key, (line_no, value))
    duplicate_fields = {key: values for key, values in occurrences.items() if len(values) > 1}
    return section_start, fields, duplicate_fields


def _is_compact_mode_enabled(
    fields: dict[str, tuple[int, str]], duplicate_fields: dict[str, list[tuple[int, str]]] | None = None
) -> bool:
    values = []
    first_value = fields.get("compact_mode")
    if first_value is not None:
        values.append(first_value)
    if duplicate_fields is not None:
        values.extend(duplicate_fields.get("compact_mode", [])[1:])
    return any(_normalize_text(value.replace("_", " ")) == "enabled" for _, value in values)


def _compact_normalized_value(value: str) -> str:
    return _normalize_text(value.replace("`", ""))


def _compact_has_bad_value(value: str) -> bool:
    return COMPACT_BAD_VALUE_RE.search(_compact_normalized_value(value)) is not None


def _compact_n_a_why_reason(value: str) -> str | None:
    normalized = _compact_normalized_value(value)
    if normalized.startswith("n/a (why=") and normalized.endswith(")"):
        return normalized.removeprefix("n/a (why=").removesuffix(")").strip()
    return None


def _compact_value_is_clear(value: str) -> bool:
    normalized = _normalize_text(value.replace("`", ""))
    if _compact_has_bad_value(value):
        return False
    if normalized == "clear":
        return True
    reason = _compact_n_a_why_reason(value)
    if reason is not None:
        return bool(reason) and COMPACT_BAD_VALUE_RE.search(reason) is None
    return False


def _compact_producer_authority_is_explicit(value: str) -> bool:
    normalized = _compact_normalized_value(value)
    if _compact_has_bad_value(value):
        return False
    reason = _compact_n_a_why_reason(value)
    if reason is not None:
        return bool(reason) and reason not in {"none", "n/a", "not applicable"}
    if normalized in {"", "none", "n/a", "not applicable"}:
        return False
    return True


def _lint_compact_no_findings_mode(artifact: AuditArtifact, headings: dict[str, int]) -> list[Finding]:
    findings: list[Finding] = []
    section_start, fields, duplicate_fields = _compact_section_fields(artifact.lines)
    if not _is_compact_mode_enabled(fields, duplicate_fields):
        if section_start is None and any(COMPACT_MODE_ENABLED_RE.search(line) for line in artifact.lines):
            findings.append(
                Finding(
                    rel_path=artifact.rel_path,
                    line_no=1,
                    code="compact_no_findings_missing_section",
                    message="`compact_mode: enabled` must live inside `## Compact no-findings mode`.",
                )
            )
        return findings

    line_no = section_start or 1
    for field, occurrences in duplicate_fields.items():
        findings.append(
            Finding(
                rel_path=artifact.rel_path,
                line_no=occurrences[1][0],
                code="compact_no_findings_duplicate_field",
                message=f"Compact no-findings mode forbids duplicate `{field}` fields; duplicate truth hosts are ambiguous.",
            )
        )

    artifact_text = "\n".join(artifact.lines)
    normalized_artifact_text = _normalize_text(artifact_text.replace("_", " ").replace("`", ""))
    if "lane finding id: n/a (no lane findings)" not in normalized_artifact_text:
        findings.append(
            Finding(
                rel_path=artifact.rel_path,
                line_no=line_no,
                code="compact_no_findings_missing_no_findings_provenance",
                message="Compact no-findings mode requires `lane_finding_id: N/A (no lane findings)` provenance.",
            )
        )
    if "synthesis disposition: no findings" not in normalized_artifact_text:
        findings.append(
            Finding(
                rel_path=artifact.rel_path,
                line_no=line_no,
                code="compact_no_findings_missing_no_findings_provenance",
                message="Compact no-findings mode requires `synthesis_disposition: no_findings` provenance.",
            )
        )
    if COMPACT_BLOCKER_REF_RE.search(artifact_text):
        findings.append(
            Finding(
                rel_path=artifact.rel_path,
                line_no=line_no,
                code="compact_no_findings_live_blocker_lineage",
                message="Compact no-findings mode is forbidden while `#B<N>` blocker refs are present.",
            )
        )

    for field in COMPACT_REQUIRED_FIELDS:
        if field in fields:
            continue
        findings.append(
            Finding(
                rel_path=artifact.rel_path,
                line_no=line_no,
                code="compact_no_findings_missing_field",
                message=f"Compact no-findings mode requires `{field}`.",
            )
        )

    review_status = fields.get("review_status")
    if review_status and (
        _compact_has_bad_value(review_status[1]) or _compact_normalized_value(review_status[1]) not in {"✅ ok", "ok"}
    ):
        findings.append(
            Finding(
                rel_path=artifact.rel_path,
                line_no=review_status[0],
                code="compact_no_findings_review_not_green",
                message="Compact no-findings mode requires live review status `✅ OK`.",
            )
        )

    finding_status = fields.get("findings")
    if finding_status:
        normalized = _compact_normalized_value(finding_status[1].replace("_", " "))
        no_findings = normalized in {"no findings", "none", "n/a", "n/a (why=no findings)"}
        if not no_findings or _compact_has_bad_value(finding_status[1]) or COMPACT_FINDING_RE.search(finding_status[1]):
            findings.append(
                Finding(
                    rel_path=artifact.rel_path,
                    line_no=finding_status[0],
                    code="compact_no_findings_findings_present",
                    message="Compact no-findings mode requires no S1/S2/S3 findings.",
                )
            )

    blocker_lineage = fields.get("live_blocker_lineage")
    if blocker_lineage:
        normalized = _compact_normalized_value(blocker_lineage[1])
        no_live_blocker = normalized in {"no live blocker lineage", "n/a (no live blocker lineage)", "none", "n/a"}
        if not no_live_blocker or _compact_has_bad_value(blocker_lineage[1]) or "#b" in normalized:
            findings.append(
                Finding(
                    rel_path=artifact.rel_path,
                    line_no=blocker_lineage[0],
                    code="compact_no_findings_live_blocker_lineage",
                    message="Compact no-findings mode is forbidden while live blocker lineage is present or ambiguous.",
                )
            )

    role_quality = fields.get("role_quality_candidate")
    if role_quality:
        normalized = _compact_normalized_value(role_quality[1])
        no_flagged_candidate = normalized in {
            "no flagged role-quality candidate",
            "n/a (why=no flagged role-quality candidate)",
            "none",
            "n/a",
        }
        if not no_flagged_candidate or _compact_has_bad_value(role_quality[1]) or (
            "flagged" in normalized and "no flagged" not in normalized
        ):
            findings.append(
                Finding(
                    rel_path=artifact.rel_path,
                    line_no=role_quality[0],
                    code="compact_no_findings_role_quality_candidate",
                    message="Compact no-findings mode is forbidden while a role-quality candidate is flagged.",
                )
            )

    for field in COMPACT_RESIDUAL_FIELDS:
        current = fields.get(field)
        if current is None:
            continue
        if _compact_value_is_clear(current[1]):
            continue
        findings.append(
            Finding(
                rel_path=artifact.rel_path,
                line_no=current[0],
                code="compact_no_findings_residual_host_not_clear",
                message=(
                    f"Compact no-findings mode requires `{field}` to be explicit `clear` "
                    "or `N/A (why=...)`; missing/red/pending/ambiguous hosts must use full audit mode."
                ),
            )
        )

    producer_authority = fields.get("producer_authority")
    if producer_authority and not _compact_producer_authority_is_explicit(producer_authority[1]):
        findings.append(
            Finding(
                rel_path=artifact.rel_path,
                line_no=producer_authority[0],
                code="compact_no_findings_producer_authority_ambiguous",
                message="Compact no-findings mode requires explicit producer authority or `N/A (why=...)`.",
            )
        )

    return findings


def _extract_schema_version_lines(lines: Sequence[str]) -> list[tuple[int, str]]:
    matches: list[tuple[int, str]] = []
    for line_no, line in enumerate(lines, start=1):
        match = SCHEMA_VERSION_HEADER_RE.match(line)
        if not match:
            continue
        matches.append((line_no, match.group("value").strip()))
    return matches


def _extract_status_lines(lines: Sequence[str]) -> list[tuple[int, str]]:
    matches: list[tuple[int, str]] = []
    for line_no, line in enumerate(lines, start=1):
        match = STATUS_HEADER_RE.match(line)
        if not match:
            continue
        matches.append((line_no, match.group("value").strip()))
    return matches


def _normalize_schema_version(value: str) -> str:
    return SPACE_RE.sub(" ", value.replace("`", "").lower()).strip()


def _normalize_status_value(value: str) -> str:
    return SPACE_RE.sub(" ", value.replace("`", "").lower()).strip()


def _classify_review_schema_version(artifact: AuditArtifact) -> tuple[str, list[Finding]]:
    findings: list[Finding] = []
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
        if artifact.path.name == "_template_post_merge_audit.md":
            findings.append(
                Finding(
                    rel_path=artifact.rel_path,
                    line_no=1,
                    code="missing_schema_version",
                    message="Missing `**Schema version:** review.v1` on the canonical post-merge audit template. "
                    "Versionless non-template audit files are tolerated only as legacy compatibility carriers.",
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
                    "versionless historical audit files are the only legacy lane in v1."
                ),
            )
        )
        return "unsupported", findings

    return "current", findings


def _needs_lane_synthesis_contract(artifact: AuditArtifact) -> bool:
    if artifact.path.name == "_template_post_merge_audit.md":
        return True
    for _, raw_value in _extract_status_lines(artifact.lines):
        normalized = _normalize_status_value(raw_value)
        if normalized in {"done", "✅ done"}:
            return True
    return False


def _needs_derived_index_receipt(lines: Sequence[str]) -> bool:
    text = "\n".join(lines).lower()
    return (
        DERIVED_INDEX_BUILD_TOKEN in text
        or DERIVED_INDEX_CHECK_TOKEN in text
        or "derived docs index receipt" in text
    )


def _has_all_tokens(text: str, tokens: tuple[str, ...]) -> bool:
    return all(token.lower() in text for token in tokens)


def _has_followups_tracked_pointer(text: str) -> bool:
    return any(FOLLOWUPS_TRACKED_POINTER_TOKEN in line.lower() and _has_durable_followups_ref_token(line) for line in text.splitlines())


def _is_durable_followups_ref(value: str) -> bool:
    raw_ref = value.strip().strip("`").strip(".,;()[]<>")
    if not FOLLOWUPS_DURABLE_REF_RE.fullmatch(raw_ref):
        return False
    path_text = raw_ref.split("#", 1)[0]
    if ":" in path_text:
        maybe_path, maybe_line = path_text.rsplit(":", 1)
        if not maybe_line.isdigit():
            return False
        path_text = maybe_path
    path = Path(path_text)
    return path_text.startswith(FOLLOWUPS_TRACKED_POINTER_TARGETS) and path.suffix == ".md" and ".." not in path.parts


def _has_durable_followups_ref_token(text: str) -> bool:
    for match in FOLLOWUPS_REF_TOKEN_RE.finditer(text):
        if _is_durable_followups_ref(match.group("ref")):
            return True
    return False


def _has_durable_followups_closeout_ref(text: str) -> bool:
    for match in FOLLOWUPS_CLOSEOUT_FIELD_RE.finditer(text):
        if _is_durable_followups_ref(match.group("ref")):
            return True
    return False


def _has_followups_range_or_tracked_pointer(citation_text: str) -> bool:
    if _has_followups_tracked_pointer(citation_text):
        return True
    if not _has_all_tokens(citation_text, ("Follow-up harvest triage/import receipt",)):
        return False
    if _has_durable_followups_closeout_ref(citation_text):
        return True
    return any(
        token in citation_text
        for token in (
            "--range",
            "range-mode",
            "range mode",
            "followups_triage_launch_receipt",
        )
    )


def _lint_current_audit_receipt_citations(artifact: AuditArtifact, headings: dict[str, int]) -> list[Finding]:
    findings: list[Finding] = []
    if POST_MERGE_RECEIPT_CITATIONS_TITLE not in headings:
        findings.append(
            Finding(
                rel_path=artifact.rel_path,
                line_no=1,
                code="missing_post_merge_receipt_citations",
                message="Current post-merge audit reports must include `## Post-merge audit receipt citations`.",
            )
        )
        citation_text = ""
    else:
        citation_text = "\n".join(line for _, line in _section_lines(artifact.lines, POST_MERGE_RECEIPT_CITATIONS_TITLE)).lower()

    for name, tokens in AUDIT_RECEIPT_CITATION_TOKENS:
        if name == "followup_harvest_triage_import" and _has_followups_tracked_pointer(citation_text):
            continue
        if _has_all_tokens(citation_text, tokens):
            continue
        findings.append(
            Finding(
                rel_path=artifact.rel_path,
                line_no=headings.get(POST_MERGE_RECEIPT_CITATIONS_TITLE, 1),
                code="missing_post_merge_receipt_citation",
                message=f"Post-merge audit receipt citations must cite `{name}` using token(s): {', '.join(tokens)}.",
            )
        )

    text = "\n".join(artifact.lines).lower()
    if FOLLOWUPS_CLEANUP_CLAIM_RE.search(text) and not _has_followups_range_or_tracked_pointer(citation_text):
        findings.append(
            Finding(
                rel_path=artifact.rel_path,
                line_no=headings.get(POST_MERGE_RECEIPT_CITATIONS_TITLE, 1),
                code="missing_followups_launch_receipt_pointer",
                message=(
                    "Audit claims about handled followups or cleanup readiness must cite range-mode "
                    "`Follow-up harvest triage/import receipt` proof or an explicit "
                    "durable `manual_decision_ref`/`already_tracked_ref` docs/followups or docs/plans pointer."
                ),
            )
        )

    if "satd" in text and "satd/candidate" not in citation_text:
        findings.append(
            Finding(
                rel_path=artifact.rel_path,
                line_no=headings.get(POST_MERGE_RECEIPT_CITATIONS_TITLE, 1),
                code="missing_post_merge_receipt_citation",
                message="SATD audit text must cite `SATD/candidate` rows or an explicit no-op.",
            )
        )

    return findings


def _parse_counter_line(raw_value: str) -> dict[str, int]:
    counters: dict[str, int] = {}
    for match in COUNTER_RE.finditer(raw_value):
        key = _normalize_text(match.group("key"))
        counters[key] = int(match.group("value"))
    return counters


def _missing_counter_keys(counters: dict[str, int], expected_keys: Sequence[str]) -> list[str]:
    return [key for key in expected_keys if key not in counters]


def _role_assessment_field(section_lines: Sequence[tuple[int, str]], pattern: re.Pattern[str]) -> tuple[int, str] | None:
    for line_no, line in section_lines:
        match = pattern.match(line)
        if match:
            return line_no, match.group("body").strip()
    return None


def _is_template_placeholder_section(artifact: AuditArtifact, section_text: str) -> bool:
    return artifact.path.name == "_template_post_merge_audit.md" and "<N>" in section_text


def _lint_role_assessment_receipt_quality(artifact: AuditArtifact, role_assessment_line: int) -> list[Finding]:
    schema_class, _ = _classify_review_schema_version(artifact)
    if schema_class != "current":
        return []

    section_title = next(
        (title for title in ROLE_ASSESSMENT_TITLES if title in _heading_locations(artifact.lines)),
        ROLE_ASSESSMENT_TITLES[0],
    )
    section_lines = _section_lines(artifact.lines, section_title)
    section_text = "\n".join(line for _, line in section_lines)
    if _is_template_placeholder_section(artifact, section_text):
        return []

    assessment = _role_assessment_field(section_lines, ROLE_ASSESSMENT_ASSESSMENT_RE)
    receipt_source = _role_assessment_field(section_lines, ROLE_ASSESSMENT_RECEIPT_SOURCE_RE)
    summary = _role_assessment_field(section_lines, ROLE_ASSESSMENT_HELPER_SUMMARY_RE)
    role_quality = _role_assessment_field(section_lines, ROLE_ASSESSMENT_HELPER_ROLE_QUALITY_RE)

    assessment_value = _normalize_text(assessment[1]) if assessment else ""
    receipt_source_value = _normalize_text(receipt_source[1]) if receipt_source else ""
    explicit_missing_noop = "receipt missing" in assessment_value and "receipt missing" in receipt_source_value
    if explicit_missing_noop:
        return []

    if not summary or not role_quality:
        return [
            Finding(
                rel_path=artifact.rel_path,
                line_no=role_assessment_line,
                code="missing_censor_receipt_helper_summary",
                message=(
                    "Role assessment must either declare explicit `receipt missing` no-op "
                    "or copy helper-backed `Helper summary` and `Helper role-quality` counters."
                ),
            )
        ]

    summary_counters = _parse_counter_line(summary[1])
    role_quality_counters = _parse_counter_line(role_quality[1])
    missing_summary_keys = _missing_counter_keys(summary_counters, HELPER_SUMMARY_COUNTER_KEYS)
    missing_role_quality_keys = _missing_counter_keys(role_quality_counters, HELPER_ROLE_QUALITY_COUNTER_KEYS)
    if missing_summary_keys or missing_role_quality_keys:
        missing_parts = []
        if missing_summary_keys:
            missing_parts.append("Helper summary: " + ", ".join(missing_summary_keys))
        if missing_role_quality_keys:
            missing_parts.append("Helper role-quality: " + ", ".join(missing_role_quality_keys))
        return [
            Finding(
                rel_path=artifact.rel_path,
                line_no=summary[0] if missing_summary_keys else role_quality[0],
                code="invalid_censor_receipt_helper_counters",
                message=(
                    "Role assessment helper counters must include the complete expected key set before they can "
                    f"be treated as green ({'; '.join(missing_parts)})."
                ),
            )
        ]

    bad_summary = {
        key: summary_counters.get(key, 0)
        for key in ("partial", "missing", "unconfirmed")
        if summary_counters.get(key, 0) > 0
    }
    bad_role_quality = {
        key: role_quality_counters.get(key, 0)
        for key in (
            "missed live blocker",
            "receipt missing",
            censor_receipts_harvest.ROLE_QUALITY_CATEGORIES[-1].lower(),
        )
        if role_quality_counters.get(key, 0) > 0
    }
    if not bad_summary and not bad_role_quality:
        return []

    bad_parts = [f"{key}={value}" for key, value in sorted({**bad_summary, **bad_role_quality}.items())]
    code = "contradictory_censor_receipt_assessment" if "helped" in assessment_value else "invalid_censor_receipt_assessment"
    return [
        Finding(
            rel_path=artifact.rel_path,
            line_no=assessment[0] if assessment else role_assessment_line,
            code=code,
            message=(
                "Role assessment cannot be green/helper-backed when helper counters contain "
                f"non-green evidence ({', '.join(bad_parts)}). Use explicit `receipt missing` no-op "
                "only when the receipt is genuinely absent."
            ),
        )
    ]


def lint_audit_artifacts(artifacts: Sequence[AuditArtifact]) -> list[Finding]:
    findings: list[Finding] = []
    for artifact in artifacts:
        schema_class, schema_findings = _classify_review_schema_version(artifact)
        findings.extend(schema_findings)
        headings = _heading_locations(artifact.lines)

        if schema_class == "current":
            findings.extend(_lint_current_audit_receipt_citations(artifact, headings))
            findings.extend(_lint_compact_no_findings_mode(artifact, headings))
            findings.extend(_lint_current_audit_status_authority(artifact))
        findings.extend(
            Finding(
                rel_path=artifact.rel_path,
                line_no=receipt.line_no,
                code=receipt.code,
                message=receipt.message,
            )
            for receipt in retrieval_telemetry_receipt.lint_retrieval_telemetry_receipt(
                artifact.lines,
                decision_evidence_only=True,
            )
        )

        if _needs_lane_synthesis_contract(artifact):
            lane_source_line = _find_line(artifact.lines, LANE_SYNTHESIS_SOURCE_TOKEN)
            if lane_source_line is None:
                findings.append(
                    Finding(
                        rel_path=artifact.rel_path,
                        line_no=1,
                        code="missing_lane_synthesis_source",
                        message="Missing required lane-synthesis carrier 'Lane synthesis source' for template/Done audit artifact",
                    )
                )

            for token in PROVENANCE_FIELD_TOKENS:
                field_line = _find_line(artifact.lines, token)
                if field_line is not None:
                    continue
                findings.append(
                    Finding(
                        rel_path=artifact.rel_path,
                        line_no=1,
                        code="missing_lane_provenance_field",
                        message=f"Missing required lane provenance field '{token}' for template/Done audit artifact",
                    )
                )

        phrase_line = _find_line(artifact.lines, FOLLOWUP_CARRIER_PHRASE)
        if phrase_line is None:
            findings.append(
                Finding(
                    rel_path=artifact.rel_path,
                    line_no=1,
                    code="missing_followup_carrier_phrase",
                    message=f"Missing required audit carrier phrase '{FOLLOWUP_CARRIER_PHRASE}'",
                )
            )

        role_assessment_line = next((headings[title] for title in ROLE_ASSESSMENT_TITLES if title in headings), None)
        if role_assessment_line is None:
            findings.append(
                Finding(
                    rel_path=artifact.rel_path,
                    line_no=1,
                    code="missing_role_assessment_section",
                    message="Missing required section '## Role assessment (censor receipts...)'",
                )
            )
        else:
            findings.extend(_lint_role_assessment_receipt_quality(artifact, role_assessment_line))

        if not _needs_derived_index_receipt(artifact.lines):
            continue

        build_line = _find_line(artifact.lines, DERIVED_INDEX_BUILD_TOKEN)
        if build_line is None:
            findings.append(
                Finding(
                    rel_path=artifact.rel_path,
                    line_no=1,
                    code="missing_derived_index_receipt",
                    message=f"Missing derived-index build token '{DERIVED_INDEX_BUILD_TOKEN}'",
                )
            )

        check_line = _find_line(artifact.lines, DERIVED_INDEX_CHECK_TOKEN)
        if check_line is None:
            findings.append(
                Finding(
                    rel_path=artifact.rel_path,
                    line_no=1,
                    code="missing_derived_index_receipt",
                    message=f"Missing derived-index check token '{DERIVED_INDEX_CHECK_TOKEN}'",
                )
            )

        full_text = "\n".join(artifact.lines)
        for corpus, summary_re in DERIVED_INDEX_SUMMARY_RE.items():
            if summary_re.search(full_text):
                continue
            findings.append(
                Finding(
                    rel_path=artifact.rel_path,
                    line_no=1,
                    code="missing_derived_index_receipt",
                    message=f"Missing derived-index coverage summary for '{corpus}'",
                )
            )

    return findings


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lint post-merge audit carriers.")
    parser.add_argument("paths", nargs="*", help="Optional audit file/directory paths.")
    args = parser.parse_args(argv)

    try:
        initial_context = resolve_top_level_context()
        # The default template remains tooling-owned for legacy callers in
        # ``_default_template_scope``.  Retaining this captured context avoids
        # rediscovering the root before the reader starts.
        project_root = initial_context.project_root.resolve()
        context: ContractContext | None = initial_context
        artifacts = load_audit_artifacts(project_root, args.paths, context=context)
    except (FileNotFoundError, ContractAuthorityError, ValueError) as exc:
        print(f"post-merge-audit-lint: FAIL\n{exc}")
        return 1

    findings = lint_audit_artifacts(artifacts)
    if findings:
        print("post-merge-audit-lint: FAIL")
        for finding in findings:
            print(finding.render())
        return 1

    print("post-merge-audit-lint: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

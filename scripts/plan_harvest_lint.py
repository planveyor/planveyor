#!/usr/bin/env python3
"""Lint bounded plan-harvest carriers and backlog linkage."""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import os
from dataclasses import dataclass
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

import retrieval_telemetry_receipt
from review_schema_contract import CURRENT_REVIEW_SCHEMA_VERSION


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE_SCOPE: tuple[Path, ...] = (
    REPO_ROOT / "docs" / "reviews" / "_template_plan_harvest.md",
)
_DEFAULT_TEMPLATE_RELATIVE_PATHS: tuple[str, ...] = (
    "docs/reviews/_template_plan_harvest.md",
)

H1_RE = re.compile(r"^\s*#\s+(?P<title>.+?)\s*$")
H2_RE = re.compile(r"^\s*##\s+(?P<title>.+?)\s*$")
SCHEMA_VERSION_HEADER_RE = re.compile(r"^\s*\*\*Schema version:\*\*\s*(?P<value>.*?)\s*$", re.IGNORECASE)
SPACE_RE = re.compile(r"\s+")
BACKLOG_REF_RE = re.compile(r"(?P<path>docs/followups/[^\s`]+?\.md)")
REVIEW_REF_RE = re.compile(r"(?P<path>docs/reviews/[^\s`|)#]+?\.md)(?P<anchor>#[A-Za-z0-9_.-]+)?")
FOLLOWUPS_RANGE_CLOSURE_CLAIM_RE = re.compile(
    r"(cleanup[-\s]?readiness|cleanup[-\s]?ready|handled follow-?ups|handled followups|follow-?ups handled)",
    re.IGNORECASE,
)
DURABLE_FOLLOWUPS_CLOSEOUT_FIELD_RE = re.compile(
    r"(?<![A-Za-z0-9_])`?(?:manual_decision_ref|already_tracked_ref)`?\s*[:=]\s*`?"
    r"(?P<ref>[^\s`<>)\],;]+)",
    re.IGNORECASE,
)
DURABLE_FOLLOWUPS_REF_TOKEN_RE = re.compile(r"`?(?P<ref>docs/(?:followups|plans)/[^\s`<>)\],;]+)", re.IGNORECASE)
DURABLE_FOLLOWUPS_REF_RE = re.compile(
    r"docs/(?:followups|plans)/[^\s`<>)\],;]+?\.md(?:#[A-Za-z0-9_.\-/]+|:\d+)?",
    re.IGNORECASE,
)

NO_FOLLOWUPS_TOKEN = "no followups"
HARVEST_FILE_FOLLOWUPS_RESULT_FIELD = "harvest_file_followups_result"
HARVEST_FILE_FOLLOWUPS_COUNT_FIELD = "harvest_file_followups_count"
HARVEST_FILE_FOLLOWUPS_ALLOWED_RESULTS = {
    "created/imported": "created/imported",
    "no followups": "NO FOLLOWUPS",
}
HARVEST_FILE_FOLLOWUPS_UNRESOLVED_FIELDS = (
    "append_new",
    "possible_duplicate",
    "route_fallback",
    "unparsed_bullets",
)
FOLLOWUPS_BACKLOG_TITLE = "follow-ups backlog (created)"
FOLLOWUPS_EXTRACTED_TITLE = "follow-ups (extracted; без дублей)"
RANGE_RESULT_TITLE = "range result"
FOLLOWUPS_BACKLOG_TITLE_ALT = "follow-ups (backlog)"
DERIVED_INDEX_BUILD_TOKEN = "planveyor_docs_index_build all"
DERIVED_INDEX_CHECK_TOKEN = "docs_context_check"
ALLOWED_NO_FOLLOWUPS_REASONS = (
    "handled in follow-up",
    "already tracked elsewhere",
    "canon sync closed it",
    "no remaining actionable debt after full-wave harvest",
)
DERIVED_INDEX_SUMMARY_RE = {
    "plans": re.compile(r"(plans\s*:\s*covered=\d+.*uncovered=\d+|docs_context_check.*corpus=plans.*covered=\d+.*uncovered=\d+)", re.IGNORECASE),
    "followups": re.compile(
        r"(followups\s*:\s*covered=\d+.*uncovered=\d+|docs_context_check.*corpus=followups.*covered=\d+.*uncovered=\d+)",
        re.IGNORECASE,
    ),
}
RETRIEVAL_METRICS_RECEIPT_TITLE = "docs retrieval metrics receipt"
RETRIEVAL_METRICS_TRIGGER_TOKENS = (
    "docs_retrieve",
    "planveyor_docs_retrieve",
    "docs_get",
    "docs_multi_get",
    "read_open",
    "read_events_total",
    "retrieval metrics",
    "docs retrieval metrics",
    "docs-retrieve observability",
    "docs retrieve observability",
    "process_docs_retrieve_observability_metrics",
)
RETRIEVAL_METRICS_REQUIRED_COLUMNS = (
    "repo",
    "repo_role",
    "query_log_status",
    "query_total",
    "with_hits",
    "zero_hits",
    "hit_rate",
    "warnings_total",
    "errors_total",
    "with_event_id",
    "evaluated_total",
    "outcome_evaluated_rate",
    "outcome_used",
    "outcome_partial",
    "outcome_miss",
    "outcome_noise",
    "not_evaluated_total",
    "read_log_status",
    "read_events_total",
    "read_open_rate",
    "unique_paths",
    "used_for_decision",
    "low_coverage_triage",
    "follow_up_ref",
    "accepted_no_op_reason",
    "source_command",
)
RETRIEVAL_METRICS_INT_COLUMNS = (
    "query_total",
    "with_hits",
    "zero_hits",
    "warnings_total",
    "errors_total",
    "with_event_id",
    "evaluated_total",
    "outcome_used",
    "outcome_partial",
    "outcome_miss",
    "outcome_noise",
    "not_evaluated_total",
    "read_events_total",
    "unique_paths",
)
RETRIEVAL_METRICS_ALLOWED_ROLES = {"source", "read_only_target"}
RETRIEVAL_METRICS_AUDIT_POINTER_SUMMARY_TOKENS = (
    "query_total",
    "evaluated_total",
    "outcome_evaluated_rate",
    "read_log_status",
    "read_events_total",
    "read_open_rate",
    "used_for_decision",
    "accepted_no_op_reason",
)
RETRIEVAL_METRICS_AUDIT_POINTER_INT_FIELDS = (
    "query_total",
    "evaluated_total",
    "read_events_total",
)
RETRIEVAL_METRICS_AUDIT_POINTER_STATUS_FIELDS = {
    "read_log_status": {"present", "missing"},
}
RETRIEVAL_LOW_OUTCOME_RATE = 0.20
RETRIEVAL_LOW_READ_OPEN_RATE = 0.05
RETRIEVAL_DECISION_EVIDENCE_MARKERS = (
    "decision evidence",
    "source selection",
    "source-selection",
    "file selection",
    "selected files",
    "lookup evidence",
    "cited evidence",
)
PROCESS_IMPROVEMENT_DECISIONS_TITLE = "process-improvement promotion decisions"
PROCESS_IMPROVEMENTS_OPEN_SUMMARY_FIELD = "process_improvements_open_summary"
PROCESS_IMPROVEMENTS_OPEN_SUMMARY_SOURCE = "docs/process_improvements/promotion_surface.md"
PROCESS_IMPROVEMENTS_OPEN_SUMMARY_STATUSES = ("open", "triaged", "promoted")
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
FOLLOWUP_TRIAGE_RECEIPT_TITLE = "follow-up harvest triage/import receipt"
GOLDEN_PATH_LANE_RECEIPT_TITLE = "golden path lane receipt"
ADR_DECISIONS_RECEIPT_TITLE = "adr candidates / durable decisions"
CANON_FOLLOWUP_SUMMARY_TITLE = "canon/follow-up summary"
PACKETIZATION_GATE_TOKEN = "step:packetization_gate"
GOLDEN_PATH_ANCHORS = (
    "docs/guides/golden_paths.md#post-merge-plan-harvest",
    "docs/guides/golden_paths.md#post-merge-audit",
    "docs/guides/golden_paths.md#process-improvement-promotion",
    "docs/guides/golden_paths.md#source-rollout-packet-lifecycle",
)
PACKETIZATION_TRIGGER_TOKENS = (
    "shared canon",
    "shared process canon",
    "canon sweep",
    "packetization handoff",
)
PI_ENTRY_ID_RE = re.compile(r"\bPI-\d{3}\b")
PI_SOURCE_REF_RE = re.compile(
    r"\bsource[_ -]?ref\s*[:=]\s*`?(?P<value>[^`|;,]+?)(?:`|\s*(?:[|;,]|$))",
    re.IGNORECASE,
)
PI_FIELD_ASSIGNMENT_RE = re.compile(
    r"(?P<key>[A-Za-z][A-Za-z0-9_-]*)\s*(?:=|:)\s*(?:`(?P<backtick>[^`]*)`|(?P<bare>[^;|]+))",
    re.IGNORECASE,
)
PI_DECISION_ALIASES = {
    "promoted": "promoted",
    "promote": "promoted",
    "deferred": "deferred",
    "defer": "deferred",
    "rejected": "rejected",
    "reject": "rejected",
    "handled": "handled",
    "done": "handled",
    "closed": "handled",
}
PI_NA_VALUES = {"", "n/a", "na", "null", "none", "unknown"}
TIMESTAMPED_SLUG_RE = re.compile(r"^\d{6}_\d{4}_(?P<slug>.+)$")


def _load_followups_module():
    module_path = Path(__file__).with_name("followups_lint.py")
    spec = importlib.util.spec_from_file_location("_plan_harvest_followups_lint", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


FOLLOWUPS_LINT = _load_followups_module()


def _load_process_improvements_module():
    module_path = Path(__file__).with_name("process_improvements_collect.py")
    spec = importlib.util.spec_from_file_location("_plan_harvest_process_improvements_collect", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PROCESS_IMPROVEMENTS = _load_process_improvements_module()


@dataclass(frozen=True)
class Finding:
    rel_path: str
    line_no: int
    code: str
    message: str

    def render(self) -> str:
        return f"{self.rel_path}:{self.line_no}: {self.code}: {self.message}"


@dataclass(frozen=True)
class PlanHarvestFileFollowupsReceipt:
    """Pure text-level current/legacy receipt classification for plan-harvest callers."""

    schema_class: str
    result: str | None
    count: int | None
    findings: tuple[Finding, ...]


@dataclass(frozen=True)
class HarvestArtifact:
    path: Path
    rel_path: str
    lines: tuple[str, ...]
    first_heading: str | None
    kind: str
    repo_root: Path


@dataclass(frozen=True)
class ProcessImprovementRecord:
    file_rel: str
    source_ref: str
    entry: object


@dataclass(frozen=True)
class ProcessImprovementDecision:
    line_no: int
    entry_id: str
    source_hint: str | None
    source_ref: str | None
    decision: str
    reason: str | None
    execution_kind: str | None
    execution_ref: str | None
    owner_or_next_step: str | None


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


def _artifact_repo_root(path: Path) -> Path:
    for parent in path.parents:
        if parent.name == "docs":
            return parent.parent
    return REPO_ROOT


def _detect_kind(path: Path, first_heading: str | None) -> str | None:
    if path.name == "_template_plan_harvest.md":
        return "report"
    if "_plan_harvest_" in path.name:
        return "report"
    if "_post_merge_audit_" in path.name:
        return "audit"
    if "_followups_range_" in path.name:
        return "backlog"
    if first_heading is None:
        return None
    if "plan harvest" in first_heading:
        return "report"
    if "post-merge audit" in first_heading:
        return "audit"
    if first_heading.startswith("follow-ups backlog"):
        return "backlog"
    return None


def _default_template_scope(context: ContractContext) -> tuple[Path, ...]:
    if context.state != "engaged":
        return DEFAULT_TEMPLATE_SCOPE
    return tuple(
        require_declared_read(context, relative_path, purpose="plan-harvest template")
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
            raise FileNotFoundError(f"Missing plan-harvest artifact path: {path}")
        if path.is_dir():
            for child in sorted(path.rglob("*.md")):
                add_path(child)
            continue
        add_path(path)

    return candidates


def load_harvest_artifacts(
    project_root: Path,
    raw_paths: Sequence[str] | None = None,
    *,
    context: ContractContext | None = None,
) -> list[HarvestArtifact]:
    root = project_root.resolve()
    resolved_context = context_for_reader(root, context=context)
    raw_paths = [] if raw_paths is None else list(raw_paths)
    artifacts: list[HarvestArtifact] = []
    use_declared_templates = resolved_context.state == "engaged" and not raw_paths
    for path in _expand_paths(root, raw_paths, context=resolved_context):
        if use_declared_templates:
            try:
                relative_path = path.resolve().relative_to(resolved_context.contract_root).as_posix()
            except ValueError as exc:  # pragma: no cover - require_declared_read already enforces this.
                raise ValueError(f"Declared harvest template escapes contract root: {path}") from exc
            text = read_declared_text(
                resolved_context,
                relative_path,
                purpose="plan-harvest template",
            )
        else:
            text = path.read_text(encoding="utf-8", errors="replace")
        lines = tuple(text.splitlines())
        first_heading = _first_heading(lines)
        kind = _detect_kind(path, first_heading)
        if kind is None:
            continue
        repo_root = _artifact_repo_root(path)
        artifacts.append(
            HarvestArtifact(
                path=path,
                rel_path=_relative_path(root, path),
                lines=lines,
                first_heading=first_heading,
                kind=kind,
                repo_root=repo_root,
            )
        )
    return artifacts


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


def _section_has_content(section_lines: Sequence[tuple[int, str]]) -> bool:
    for _, line in section_lines:
        stripped = line.strip()
        if stripped and not set(stripped.replace(" ", "")) <= {"-", "|", ":"}:
            return True
    return False


def _extract_schema_version_lines(lines: Sequence[str]) -> list[tuple[int, str]]:
    matches: list[tuple[int, str]] = []
    for line_no, line in enumerate(lines, start=1):
        match = SCHEMA_VERSION_HEADER_RE.match(line)
        if not match:
            continue
        matches.append((line_no, match.group("value").strip()))
    return matches


def _normalize_schema_version(value: str) -> str:
    return SPACE_RE.sub(" ", value.replace("`", "").lower()).strip()


def _classify_plan_harvest_schema_text(source_text: str, *, rel_path: str) -> tuple[str, list[Finding]]:
    findings: list[Finding] = []
    matches = _extract_schema_version_lines(source_text.splitlines())
    if len(matches) > 1:
        line_nos = ", ".join(str(line_no) for line_no, _ in matches)
        findings.append(
            Finding(
                rel_path=rel_path,
                line_no=matches[0][0],
                code="multiple_schema_version_headers",
                message=f"Multiple `**Schema version:**` header lines found ({line_nos}). Keep one canonical top-level carrier.",
            )
        )
        return "unsupported", findings

    if not matches:
        if Path(rel_path).name.startswith("_template"):
            findings.append(
                Finding(
                    rel_path=rel_path,
                    line_no=1,
                    code="missing_schema_version",
                    message="Missing `**Schema version:** review.v1` on the canonical plan-harvest template. "
                    "Versionless non-template harvest reports are tolerated only as legacy compatibility carriers.",
                )
            )
            return "unsupported", findings
        return "legacy", findings

    line_no, raw_value = matches[0]
    normalized = _normalize_schema_version(raw_value)
    if normalized != CURRENT_REVIEW_SCHEMA_VERSION:
        findings.append(
            Finding(
                rel_path=rel_path,
                line_no=line_no,
                code="unsupported_schema_version",
                message=(
                    f"Unsupported review schema version {raw_value!r}; current={CURRENT_REVIEW_SCHEMA_VERSION!r}, "
                    "versionless historical harvest reports are the only legacy lane in v1."
                ),
            )
        )
        return "unsupported", findings

    return "current", findings


def _classify_review_schema_version(artifact: HarvestArtifact) -> tuple[str, list[Finding]]:
    """Lint-local adapter over the public text-level plan-harvest classifier."""

    if artifact.kind not in {"report", "audit"}:
        return "n/a", []
    return _classify_plan_harvest_schema_text("\n".join(artifact.lines), rel_path=artifact.rel_path)


def _current_receipt_field_rows(
    section_lines: Sequence[tuple[int, str]],
    *,
    field: str,
) -> list[tuple[int, str]]:
    field_re = re.compile(
        rf"(?<![A-Za-z0-9_])`?{re.escape(field)}`?\s*(?:=|:)\s*(?P<value>.+?)\s*$",
        re.IGNORECASE,
    )
    rows: list[tuple[int, str]] = []
    for line_no, line in section_lines:
        match = field_re.search(line)
        if match:
            rows.append((line_no, match.group("value").strip()))
    return rows


def _current_receipt_table_cells(line: str) -> list[str] | None:
    if "|" not in line:
        return None
    raw_cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    if not raw_cells or all(not cell for cell in raw_cells):
        return None
    if all(re.fullmatch(r":?-{3,}:?", cell) for cell in raw_cells):
        return None
    return raw_cells


def _current_receipt_idempotency_counter_rows(
    section_lines: Sequence[tuple[int, str]],
) -> dict[str, list[tuple[int, str]]]:
    counter_rows = {field: [] for field in HARVEST_FILE_FOLLOWUPS_UNRESOLVED_FIELDS}
    assignment_re = re.compile(
        rf"(?<![A-Za-z0-9_])(?P<field>{'|'.join(HARVEST_FILE_FOLLOWUPS_UNRESOLVED_FIELDS)})"
        r"(?![A-Za-z0-9_])\s*(?:=|:)\s*(?P<value>`[^`]*`|[^,\s;|]+)",
        re.IGNORECASE,
    )
    table_header: dict[str, list[int]] | None = None
    for line_no, line in section_lines:
        cells = _current_receipt_table_cells(line)
        if cells:
            normalized = [cell.strip().strip("`").lower().replace("-", "_") for cell in cells]
            if any(field in normalized for field in HARVEST_FILE_FOLLOWUPS_UNRESOLVED_FIELDS):
                table_header = {field: [] for field in HARVEST_FILE_FOLLOWUPS_UNRESOLVED_FIELDS}
                for index, name in enumerate(normalized):
                    if name in table_header:
                        table_header[name].append(index)
                continue
            if table_header is not None:
                row_text = " ".join(cells).lower()
                if "idempotency" not in row_text:
                    continue
                for field, indexes in table_header.items():
                    for index in indexes:
                        raw_value = cells[index].strip() if index < len(cells) else ""
                        counter_rows[field].append((line_no, raw_value))
                continue

        if "idempotency" not in line.lower():
            continue
        for match in assignment_re.finditer(line):
            counter_rows[match.group("field").lower()].append((line_no, match.group("value")))
    return counter_rows


def _parse_current_idempotency_counter(raw_value: str) -> int | None:
    normalized = raw_value.strip()
    if normalized.endswith("."):
        normalized = normalized[:-1].rstrip()
    normalized = normalized.strip("`").strip()
    if not re.fullmatch(r"\d+", normalized):
        return None
    return int(normalized)


def parse_plan_harvest_file_followups_receipt(
    source_text: str,
    *,
    rel_path: str,
) -> PlanHarvestFileFollowupsReceipt:
    """Classify and validate a plan-harvest file-followups receipt without filesystem access."""

    schema_class, findings = _classify_plan_harvest_schema_text(source_text, rel_path=rel_path)
    if schema_class != "current":
        return PlanHarvestFileFollowupsReceipt(schema_class, None, None, tuple(findings))

    lines = tuple(source_text.splitlines())
    section = _section_lines(lines, FOLLOWUP_TRIAGE_RECEIPT_TITLE)
    if not section:
        findings.append(
            Finding(
                rel_path=rel_path,
                line_no=1,
                code="missing_harvest_file_followups_receipt",
                message=(
                    "Current plan-harvest artifacts require `## Follow-up harvest triage/import receipt` "
                    "with literal file-followups result/count fields."
                ),
            )
        )
        return PlanHarvestFileFollowupsReceipt(schema_class, None, None, tuple(findings))

    result_rows = _current_receipt_field_rows(section, field=HARVEST_FILE_FOLLOWUPS_RESULT_FIELD)
    count_rows = _current_receipt_field_rows(section, field=HARVEST_FILE_FOLLOWUPS_COUNT_FIELD)
    result: str | None = None
    count: int | None = None

    if not result_rows:
        findings.append(
            Finding(
                rel_path=rel_path,
                line_no=section[0][0],
                code="missing_harvest_file_followups_result",
                message=f"Current receipt requires exactly one `{HARVEST_FILE_FOLLOWUPS_RESULT_FIELD}` literal.",
            )
        )
    elif len(result_rows) > 1:
        findings.append(
            Finding(
                rel_path=rel_path,
                line_no=result_rows[0][0],
                code="duplicate_harvest_file_followups_result",
                message=f"Current receipt has multiple `{HARVEST_FILE_FOLLOWUPS_RESULT_FIELD}` literals.",
            )
        )
    else:
        result_line_no, raw_result = result_rows[0]
        result_match = re.fullmatch(
            r"`?(?P<value>created/imported|no followups)`?(?P<suffix>\s*(?:[—–-]\s*.*)?)",
            raw_result,
            flags=re.IGNORECASE,
        )
        if result_match is None:
            findings.append(
                Finding(
                    rel_path=rel_path,
                    line_no=result_line_no,
                    code="invalid_harvest_file_followups_result",
                    message=(
                        f"`{HARVEST_FILE_FOLLOWUPS_RESULT_FIELD}` must be exactly `created/imported` "
                        "or `NO FOLLOWUPS`."
                    ),
                )
            )
        else:
            result = HARVEST_FILE_FOLLOWUPS_ALLOWED_RESULTS[result_match.group("value").casefold()]
            no_op_reasons = [
                reason for reason in ALLOWED_NO_FOLLOWUPS_REASONS if reason in raw_result.casefold()
            ]
            if result == "NO FOLLOWUPS" and len(no_op_reasons) != 1:
                findings.append(
                    Finding(
                        rel_path=rel_path,
                        line_no=result_line_no,
                        code="invalid_harvest_file_followups_no_op_reason",
                        message="`NO FOLLOWUPS` must keep one allowed reason in the same result receipt line.",
                    )
                )
            if result == "created/imported" and result_match.group("suffix").strip():
                findings.append(
                    Finding(
                        rel_path=rel_path,
                        line_no=result_line_no,
                        code="invalid_harvest_file_followups_result",
                        message="`created/imported` must not carry a no-op explanation.",
                    )
                )

    if not count_rows:
        findings.append(
            Finding(
                rel_path=rel_path,
                line_no=section[0][0],
                code="missing_harvest_file_followups_count",
                message=f"Current receipt requires exactly one `{HARVEST_FILE_FOLLOWUPS_COUNT_FIELD}` literal.",
            )
        )
    elif len(count_rows) > 1:
        findings.append(
            Finding(
                rel_path=rel_path,
                line_no=count_rows[0][0],
                code="duplicate_harvest_file_followups_count",
                message=f"Current receipt has multiple `{HARVEST_FILE_FOLLOWUPS_COUNT_FIELD}` literals.",
            )
        )
    else:
        count_line_no, raw_count = count_rows[0]
        count_match = re.fullmatch(r"`?(?P<value>\d+)`?", raw_count.rstrip("."))
        if count_match is None:
            findings.append(
                Finding(
                    rel_path=rel_path,
                    line_no=count_line_no,
                    code="invalid_harvest_file_followups_count",
                    message=f"`{HARVEST_FILE_FOLLOWUPS_COUNT_FIELD}` must be a non-negative integer.",
                )
            )
        else:
            count = int(count_match.group("value"))

    if result == "created/imported" and count is not None and count <= 0:
        findings.append(
            Finding(
                rel_path=rel_path,
                line_no=count_rows[0][0],
                code="invalid_harvest_file_followups_result_count",
                message="`created/imported` requires a positive exact file-followups count.",
            )
        )
    if result == "NO FOLLOWUPS" and count is not None and count != 0:
        findings.append(
            Finding(
                rel_path=rel_path,
                line_no=count_rows[0][0],
                code="invalid_harvest_file_followups_result_count",
                message="`NO FOLLOWUPS` requires file-followups count `0`.",
            )
        )

    section_text = "\n".join(line for _, line in section)
    closure_rows = [
        (line_no, match.group("ref"))
        for line_no, line in section
        for match in DURABLE_FOLLOWUPS_CLOSEOUT_FIELD_RE.finditer(line)
    ]
    for line_no, raw_ref in closure_rows:
        if not _is_durable_followups_ref(raw_ref):
            findings.append(
                Finding(
                    rel_path=rel_path,
                    line_no=line_no,
                    code="invalid_harvest_file_followups_closure_ref",
                    message="manual_decision_ref/already_tracked_ref must be a durable docs/followups or docs/plans ref.",
                )
            )

    idempotency_counter_rows = _current_receipt_idempotency_counter_rows(section)
    unresolved_rows: list[tuple[int, str, int]] = []
    for field in HARVEST_FILE_FOLLOWUPS_UNRESOLVED_FIELDS:
        rows = idempotency_counter_rows[field]
        if not rows:
            findings.append(
                Finding(
                    rel_path=rel_path,
                    line_no=section[0][0],
                    code="missing_harvest_file_followups_idempotency_counter",
                    message=f"Current receipt requires exactly one parseable `{field}` idempotency counter.",
                )
            )
            continue
        if len(rows) > 1:
            findings.append(
                Finding(
                    rel_path=rel_path,
                    line_no=rows[0][0],
                    code="duplicate_harvest_file_followups_idempotency_counter",
                    message=f"Current receipt has multiple `{field}` idempotency counters.",
                )
            )
            continue
        line_no, raw_value = rows[0]
        value = _parse_current_idempotency_counter(raw_value)
        if value is None:
            findings.append(
                Finding(
                    rel_path=rel_path,
                    line_no=line_no,
                    code="invalid_harvest_file_followups_idempotency_counter",
                    message=f"Current receipt requires `{field}` idempotency counter to be a non-negative integer.",
                )
            )
            continue
        if value != 0:
            unresolved_rows.append((line_no, field, value))
    if unresolved_rows and not _has_durable_followups_closeout_ref(section_text):
        line_no, field, value = unresolved_rows[0]
        findings.append(
            Finding(
                rel_path=rel_path,
                line_no=line_no,
                code="unresolved_harvest_file_followups",
                message=(
                    f"Current receipt has unresolved `{field}={value}`; add a durable "
                    "manual_decision_ref or already_tracked_ref."
                ),
            )
        )

    return PlanHarvestFileFollowupsReceipt(schema_class, result, count, tuple(findings))


def _find_line(lines: Sequence[str], token: str) -> int | None:
    needle = token.lower()
    for line_no, line in enumerate(lines, start=1):
        if needle in line.lower():
            return line_no
    return None


def _has_allowed_no_followups_reason(line: str) -> bool:
    lower = line.lower()
    return any(reason in lower for reason in ALLOWED_NO_FOLLOWUPS_REASONS)


def _needs_derived_index_receipt(lines: Sequence[str]) -> bool:
    text = "\n".join(lines).lower()
    return (
        DERIVED_INDEX_BUILD_TOKEN in text
        or DERIVED_INDEX_CHECK_TOKEN in text
        or "derived index receipt" in text
    )


def _needs_retrieval_metrics_receipt(lines: Sequence[str]) -> bool:
    text = "\n".join(lines).lower()
    return any(token in text for token in RETRIEVAL_METRICS_TRIGGER_TOKENS)


def _has_retrieval_decision_evidence(lines: Sequence[str]) -> bool:
    for line in lines:
        lower = line.lower()
        if "planveyor_docs_lookup" in lower:
            return True
        if (
            any(token in lower for token in ("docs_retrieve", "planveyor_docs_retrieve", "docs_get", "docs_multi_get"))
            and any(marker in lower for marker in RETRIEVAL_DECISION_EVIDENCE_MARKERS)
        ):
            return True
    return False


def _first_retrieval_metrics_trigger_line(lines: Sequence[str]) -> int:
    for line_no, line in enumerate(lines, start=1):
        lower = line.lower()
        if any(token in lower for token in RETRIEVAL_METRICS_TRIGGER_TOKENS):
            return line_no
    return 1


def _is_placeholder_path(raw_path: str) -> bool:
    return any(token in raw_path for token in ("<", ">", "YYMMDD", "HEAD", "base7", "head7"))


def _extract_backlog_refs(section_lines: Sequence[tuple[int, str]]) -> list[tuple[int, str]]:
    refs: list[tuple[int, str]] = []
    for line_no, line in section_lines:
        for match in BACKLOG_REF_RE.finditer(line):
            refs.append((line_no, match.group("path")))
    return refs


def _strip_cell(raw: str) -> str:
    cell = raw.strip()
    if cell.startswith("-"):
        cell = cell[1:].strip()
    cell = cell.strip().strip("|").strip()
    if cell.startswith("`") and cell.endswith("`") and len(cell) >= 2:
        cell = cell[1:-1].strip()
    return cell


def _literal_or_none(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = _strip_cell(raw)
    if value.lower() in PI_NA_VALUES:
        return None
    return value or None


def _normalize_pi_decision(raw: str) -> str | None:
    value = _strip_cell(raw).lower().replace("✅", "").strip()
    value = value.split()[0] if value else value
    return PI_DECISION_ALIASES.get(value)


def _split_decision_cells(line: str) -> list[str]:
    stripped = line.strip()
    if "|" not in stripped:
        return []
    cells = [_strip_cell(cell) for cell in stripped.strip("|").split("|")]
    if not cells:
        return []
    if all(set(cell.replace(" ", "")) <= {"-", ":"} for cell in cells if cell):
        return []
    return cells


def _normalize_table_column(raw: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", _strip_cell(raw).lower()).strip("_")


def _field_assignments(line: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for match in PI_FIELD_ASSIGNMENT_RE.finditer(line):
        key = _normalize_table_column(match.group("key"))
        value = match.group("backtick") if match.group("backtick") is not None else match.group("bare")
        fields[key] = _strip_cell((value or "").strip().rstrip(".,)"))
    return fields


def _cell_to_int(raw: str) -> int | None:
    value = _strip_cell(raw).replace(",", "")
    if not value or value.lower() in PI_NA_VALUES:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _cell_to_rate(raw: str) -> float | None:
    value = _strip_cell(raw).replace(",", "")
    if not value or value.lower() in PI_NA_VALUES:
        return None
    try:
        if value.endswith("%"):
            parsed = float(value[:-1].strip()) / 100.0
        else:
            parsed = float(value)
    except ValueError:
        return None
    if parsed < 0.0 or parsed > 1.0:
        return None
    return parsed


def _retrieval_metrics_table(
    section_lines: Sequence[tuple[int, str]],
) -> tuple[int, list[str], list[tuple[int, dict[str, str]]]] | None:
    header_line_no: int | None = None
    headers: list[str] = []
    header_index = -1
    for index, (line_no, line) in enumerate(section_lines):
        cells = _split_decision_cells(line)
        if not cells:
            continue
        normalized = [_normalize_table_column(cell) for cell in cells]
        if "repo" not in normalized or "query_total" not in normalized:
            continue
        header_line_no = line_no
        headers = normalized
        header_index = index
        break

    if header_line_no is None:
        return None

    rows: list[tuple[int, dict[str, str]]] = []
    for line_no, line in section_lines[header_index + 1 :]:
        cells = _split_decision_cells(line)
        if not cells:
            continue
        row = {
            header: cells[index] if index < len(cells) else ""
            for index, header in enumerate(headers)
        }
        if any(value for value in row.values()):
            rows.append((line_no, row))
    return header_line_no, headers, rows


def _retrieval_metrics_harvest_refs(lines: Sequence[str]) -> list[tuple[int, str, str]]:
    refs: list[tuple[int, str, str]] = []
    for line_no, line in enumerate(lines, start=1):
        for match in REVIEW_REF_RE.finditer(line):
            raw_path = match.group("path")
            if "_plan_harvest_" not in Path(raw_path).name:
                continue
            refs.append((line_no, raw_path, match.group("anchor") or ""))
    return refs


def _has_retrieval_metrics_pointer_summary(lines: Sequence[str]) -> bool:
    return _has_retrieval_metrics_pointer_summary_assignments(lines) or _has_retrieval_metrics_pointer_summary_table(lines)


def _field_assignment_value(text: str, field: str) -> str | None:
    pattern = re.compile(
        rf"(?<![A-Za-z0-9_]){re.escape(field)}\s*(?:=|:)\s*`?(?P<value>[A-Za-z0-9_,.%+-]+)",
        re.IGNORECASE,
    )
    match = pattern.search(text)
    if match is None:
        return None
    return match.group("value").strip("`.,;)")


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


def _valid_pointer_summary_row(row: dict[str, str]) -> bool:
    for field in RETRIEVAL_METRICS_AUDIT_POINTER_INT_FIELDS:
        if _cell_to_int(row.get(field, "")) is None:
            return False
    for field, allowed_values in RETRIEVAL_METRICS_AUDIT_POINTER_STATUS_FIELDS.items():
        if _strip_cell(row.get(field, "")).lower() not in allowed_values:
            return False
    for field in ("outcome_evaluated_rate", "read_open_rate"):
        if _cell_to_rate(row.get(field, "")) is None:
            return False
    used_for_decision = _strip_cell(row.get("used_for_decision", "")).lower()
    if used_for_decision not in {"true", "false"}:
        return False
    if used_for_decision == "false" and _strip_cell(row.get("accepted_no_op_reason", "")) != "not_used_for_decision":
        return False
    return True


def _has_retrieval_metrics_pointer_summary_assignments(lines: Sequence[str]) -> bool:
    text = "\n".join(lines)
    row: dict[str, str] = {}
    for field in RETRIEVAL_METRICS_AUDIT_POINTER_SUMMARY_TOKENS:
        value = _field_assignment_value(text, field)
        if value is None:
            return False
        row[field] = value
    return _valid_pointer_summary_row(row)


def _has_retrieval_metrics_pointer_summary_table(lines: Sequence[str]) -> bool:
    required = set(RETRIEVAL_METRICS_AUDIT_POINTER_SUMMARY_TOKENS)
    for header_index, line in enumerate(lines):
        cells = _split_decision_cells(line)
        if not cells:
            continue
        headers = [_normalize_table_column(cell) for cell in cells]
        if not required.issubset(headers):
            continue
        for row_line in lines[header_index + 1 :]:
            row_cells = _split_decision_cells(row_line)
            if not row_cells:
                continue
            row = {
                header: row_cells[index] if index < len(row_cells) else ""
                for index, header in enumerate(headers)
            }
            if _valid_pointer_summary_row(row):
                return True
    return False


def _resolve_review_ref_path(artifact: HarvestArtifact, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path.resolve()
    return (artifact.repo_root / raw_path).resolve()


def _load_report_artifact_for_ref(audit: HarvestArtifact, raw_path: str) -> HarvestArtifact | None:
    resolved = _resolve_review_ref_path(audit, raw_path)
    if not resolved.exists():
        return None
    text = resolved.read_text(encoding="utf-8", errors="replace")
    lines = tuple(text.splitlines())
    return HarvestArtifact(
        path=resolved,
        rel_path=_relative_path(REPO_ROOT, resolved),
        lines=lines,
        first_heading=_first_heading(lines),
        kind="report",
        repo_root=_artifact_repo_root(resolved),
    )


def _audit_pointer_finding(audit: HarvestArtifact, line_no: int, message: str) -> Finding:
    return Finding(
        rel_path=audit.rel_path,
        line_no=line_no,
        code="invalid_retrieval_metrics_receipt_pointer",
        message=message,
    )


def _has_valid_retrieval_metrics_harvest_pointer(audit: HarvestArtifact) -> tuple[bool, Finding | None]:
    if audit.kind != "audit":
        return False, None

    refs = _retrieval_metrics_harvest_refs(audit.lines)
    if not refs:
        return False, None
    if not _has_retrieval_metrics_pointer_summary(audit.lines):
        line_no, _, _ = refs[0]
        return False, _audit_pointer_finding(
            audit,
            line_no,
            "Docs retrieval metrics receipt pointer must copy summary fields: query_total, evaluated_total, outcome_evaluated_rate, read_log_status, read_events_total, read_open_rate, used_for_decision, accepted_no_op_reason.",
        )

    first_failure: Finding | None = None
    for line_no, raw_path, anchor in refs:
        if anchor != "#docs-retrieval-metrics-receipt":
            first_failure = first_failure or _audit_pointer_finding(
                audit,
                line_no,
                f"Docs retrieval metrics receipt pointer must link `{raw_path}#docs-retrieval-metrics-receipt`.",
            )
            continue
        harvest = _load_report_artifact_for_ref(audit, raw_path)
        if harvest is None:
            first_failure = first_failure or _audit_pointer_finding(
                audit,
                line_no,
                f"Docs retrieval metrics receipt pointer references missing harvest report: {raw_path}",
            )
            continue
        headings = _heading_locations(harvest.lines)
        if RETRIEVAL_METRICS_RECEIPT_TITLE not in headings:
            first_failure = first_failure or _audit_pointer_finding(
                audit,
                line_no,
                f"Referenced harvest report lacks `## Docs retrieval metrics receipt`: {raw_path}",
            )
            continue
        receipt_findings = _lint_retrieval_metrics_receipt(harvest)
        if not receipt_findings:
            return True, None
        first_failure = first_failure or _audit_pointer_finding(
            audit,
            line_no,
            f"Referenced harvest metrics receipt is invalid: {receipt_findings[0].message}",
        )

    return False, first_failure


def _lint_retrieval_metrics_receipt(artifact: HarvestArtifact) -> list[Finding]:
    if not _needs_retrieval_metrics_receipt(artifact.lines):
        return []

    headings = _heading_locations(artifact.lines)
    receipt_line = headings.get(RETRIEVAL_METRICS_RECEIPT_TITLE)
    if receipt_line is None:
        pointer_ok, pointer_finding = _has_valid_retrieval_metrics_harvest_pointer(artifact)
        if pointer_ok:
            return []
        if pointer_finding is not None:
            return [pointer_finding]
        return [
            Finding(
                rel_path=artifact.rel_path,
                line_no=_first_retrieval_metrics_trigger_line(artifact.lines),
                code="missing_retrieval_metrics_receipt",
                message="Docs-retrieve/index usage is in scope but `## Docs retrieval metrics receipt` is missing.",
            )
        ]

    section = _section_lines(artifact.lines, RETRIEVAL_METRICS_RECEIPT_TITLE)
    table = _retrieval_metrics_table(section)
    if table is None:
        return [
            Finding(
                rel_path=artifact.rel_path,
                line_no=receipt_line,
                code="invalid_retrieval_metrics_receipt",
                message="Docs retrieval metrics receipt must include the canonical aggregate metrics table.",
            )
        ]

    header_line_no, headers, rows = table
    findings: list[Finding] = []
    missing_columns = [column for column in RETRIEVAL_METRICS_REQUIRED_COLUMNS if column not in headers]
    if missing_columns:
        findings.append(
            Finding(
                rel_path=artifact.rel_path,
                line_no=header_line_no,
                code="invalid_retrieval_metrics_receipt",
                message="Docs retrieval metrics receipt table is missing columns: " + ", ".join(missing_columns),
            )
        )
        return findings

    if not rows:
        findings.append(
            Finding(
                rel_path=artifact.rel_path,
                line_no=header_line_no,
                code="invalid_retrieval_metrics_receipt",
                message="Docs retrieval metrics receipt table must include at least one aggregate row.",
            )
        )
        return findings

    for line_no, row in rows:
        repo_role = _strip_cell(row.get("repo_role", "")).lower()
        if repo_role not in RETRIEVAL_METRICS_ALLOWED_ROLES:
            findings.append(
                Finding(
                    rel_path=artifact.rel_path,
                    line_no=line_no,
                    code="invalid_retrieval_metrics_receipt",
                    message="Docs retrieval metrics receipt rows must label repo_role as `source` or `read_only_target`.",
                )
            )

        for column in RETRIEVAL_METRICS_INT_COLUMNS:
            if _cell_to_int(row.get(column, "")) is not None:
                continue
            findings.append(
                Finding(
                    rel_path=artifact.rel_path,
                    line_no=line_no,
                    code="invalid_retrieval_metrics_receipt",
                    message=f"Docs retrieval metrics receipt column `{column}` must be an integer count.",
                )
            )

        outcome_rate = _cell_to_rate(row.get("outcome_evaluated_rate", ""))
        if outcome_rate is None:
            findings.append(
                Finding(
                    rel_path=artifact.rel_path,
                    line_no=line_no,
                    code="invalid_retrieval_metrics_receipt",
                    message="Docs retrieval metrics receipt column `outcome_evaluated_rate` must be a decimal or percent rate.",
                )
            )
        read_open_rate = _cell_to_rate(row.get("read_open_rate", ""))
        if read_open_rate is None:
            findings.append(
                Finding(
                    rel_path=artifact.rel_path,
                    line_no=line_no,
                    code="invalid_retrieval_metrics_receipt",
                    message="Docs retrieval metrics receipt column `read_open_rate` must be a decimal or percent rate.",
                )
            )

        query_log_status = _strip_cell(row.get("query_log_status", "")).lower()
        if query_log_status == "missing":
            for column in (
                "query_total",
                "with_hits",
                "zero_hits",
                "warnings_total",
                "errors_total",
                "with_event_id",
                "evaluated_total",
                "outcome_used",
                "outcome_partial",
                "outcome_miss",
                "outcome_noise",
                "not_evaluated_total",
            ):
                value = _cell_to_int(row.get(column, ""))
                if value == 0:
                    continue
                findings.append(
                    Finding(
                        rel_path=artifact.rel_path,
                        line_no=line_no,
                        code="invalid_retrieval_metrics_receipt",
                        message=f"`query_log_status=missing` requires `{column}=0`.",
                    )
                )

        read_log_status = _strip_cell(row.get("read_log_status", "")).lower()
        if read_log_status == "missing":
            for column in ("read_events_total", "unique_paths"):
                value = _cell_to_int(row.get(column, ""))
                if value == 0:
                    continue
                findings.append(
                    Finding(
                        rel_path=artifact.rel_path,
                        line_no=line_no,
                        code="invalid_retrieval_metrics_receipt",
                        message=f"`read_log_status=missing` requires `{column}=0`.",
                    )
                )

        if not _strip_cell(row.get("source_command", "")):
            findings.append(
                Finding(
                    rel_path=artifact.rel_path,
                    line_no=line_no,
                    code="invalid_retrieval_metrics_receipt",
                    message="Docs retrieval metrics receipt rows must name the source command.",
                )
            )

        used_for_decision = _strip_cell(row.get("used_for_decision", "")).lower()
        if used_for_decision not in {"true", "false"}:
            findings.append(
                Finding(
                    rel_path=artifact.rel_path,
                    line_no=line_no,
                    code="invalid_retrieval_metrics_receipt",
                    message="Docs retrieval metrics receipt column `used_for_decision` must be `true` or `false`.",
                )
            )
            continue

        accepted_no_op_reason = _strip_cell(row.get("accepted_no_op_reason", ""))
        if used_for_decision == "false":
            if accepted_no_op_reason != "not_used_for_decision":
                findings.append(
                    Finding(
                        rel_path=artifact.rel_path,
                        line_no=line_no,
                        code="invalid_retrieval_metrics_receipt",
                        message="`used_for_decision=false` requires `accepted_no_op_reason=not_used_for_decision`.",
                    )
                )
            if _has_retrieval_decision_evidence(artifact.lines):
                findings.append(
                    Finding(
                        rel_path=artifact.rel_path,
                        line_no=line_no,
                        code="invalid_retrieval_metrics_receipt",
                        message="Retrieval metrics cited as decision evidence cannot use `used_for_decision=false`.",
                    )
                )
        elif accepted_no_op_reason == "not_used_for_decision":
            findings.append(
                Finding(
                    rel_path=artifact.rel_path,
                    line_no=line_no,
                    code="invalid_retrieval_metrics_receipt",
                    message="`not_used_for_decision` no-op reason is invalid when `used_for_decision=true`.",
                )
            )

        query_total = _cell_to_int(row.get("query_total", ""))
        if (
            query_total is not None
            and query_total > 0
            and used_for_decision == "true"
            and outcome_rate is not None
            and read_open_rate is not None
            and (outcome_rate < RETRIEVAL_LOW_OUTCOME_RATE or read_open_rate < RETRIEVAL_LOW_READ_OPEN_RATE)
        ):
            follow_up_ref = _strip_cell(row.get("follow_up_ref", ""))
            follow_up_ok = bool(follow_up_ref and follow_up_ref.lower() not in PI_NA_VALUES and not follow_up_ref.lower().startswith("n/a"))
            if not follow_up_ok and not re.fullmatch(r"[a-z][a-z0-9_-]*", accepted_no_op_reason):
                findings.append(
                    Finding(
                        rel_path=artifact.rel_path,
                        line_no=line_no,
                        code="invalid_retrieval_metrics_receipt",
                        message="Low docs retrieval coverage requires `follow_up_ref` or enum-like `accepted_no_op_reason`.",
                    )
                )

    return findings


def _extract_source_ref(line: str) -> str | None:
    match = PI_SOURCE_REF_RE.search(line)
    if not match:
        return None
    return _literal_or_none(match.group("value"))


def _source_ref_from_cells(cells: Sequence[str], entry_index: int) -> str | None:
    if entry_index <= 0:
        return None
    return _literal_or_none(cells[entry_index - 1])


def _parse_process_improvement_decision(line_no: int, line: str) -> ProcessImprovementDecision | None:
    if line.lstrip().startswith("###"):
        return None
    cells = _split_decision_cells(line)
    if not cells:
        return None

    entry_index = next((idx for idx, cell in enumerate(cells) if PI_ENTRY_ID_RE.search(cell)), None)
    if entry_index is None:
        return None

    decision_index = next(
        (idx for idx, cell in enumerate(cells) if idx != entry_index and _normalize_pi_decision(cell) is not None),
        None,
    )
    if decision_index is None:
        return None

    identity = cells[entry_index]
    entry_match = PI_ENTRY_ID_RE.search(identity)
    assert entry_match is not None
    entry_id = entry_match.group(0)
    source_hint = None
    if "@" in identity:
        source_hint = _literal_or_none(identity.split("@", 1)[1])

    decision = _normalize_pi_decision(cells[decision_index])
    assert decision is not None
    reason = _literal_or_none(cells[decision_index + 1]) if len(cells) > decision_index + 1 else None
    execution_kind = _literal_or_none(cells[decision_index + 2]) if len(cells) > decision_index + 2 else None
    execution_ref = _literal_or_none(cells[decision_index + 3]) if len(cells) > decision_index + 3 else None
    owner_or_next_step = _literal_or_none(cells[decision_index + 4]) if len(cells) > decision_index + 4 else None

    return ProcessImprovementDecision(
        line_no=line_no,
        entry_id=entry_id,
        source_hint=source_hint,
        source_ref=_extract_source_ref(line) or _source_ref_from_cells(cells, entry_index),
        decision=decision,
        reason=reason,
        execution_kind=execution_kind,
        execution_ref=execution_ref,
        owner_or_next_step=owner_or_next_step,
    )


def _process_improvement_decisions(section_lines: Sequence[tuple[int, str]]) -> list[ProcessImprovementDecision]:
    rows: list[ProcessImprovementDecision] = []
    for line_no, line in section_lines:
        if line.lstrip().startswith("###"):
            break
        decision = _parse_process_improvement_decision(line_no, line)
        if decision is not None:
            rows.append(decision)
    return rows


def _process_improvements_open_summary_lines(
    section_lines: Sequence[tuple[int, str]],
) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for line_no, line in section_lines:
        if PROCESS_IMPROVEMENTS_OPEN_SUMMARY_FIELD in line:
            out.append((line_no, line))
    return out


def _parse_process_improvements_open_summary_line(line: str) -> dict[str, str] | None:
    match = re.search(
        rf"{re.escape(PROCESS_IMPROVEMENTS_OPEN_SUMMARY_FIELD)}\s*:\s*(?P<body>.+)$",
        line,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return _parse_semicolon_summary(match.group("body"))


def _raw_process_improvement_summary_rows(
    section_lines: Sequence[tuple[int, str]],
) -> list[tuple[int, str, bool]]:
    rows: list[tuple[int, str, bool]] = []
    header: list[str] | None = None
    for line_no, line in section_lines:
        if PROCESS_IMPROVEMENTS_OPEN_SUMMARY_FIELD in line:
            continue
        fields = _field_assignments(line)
        assigned_status = _literal_or_none(fields.get("raw_status") or fields.get("status"))
        if assigned_status is not None and assigned_status.lower() in PROCESS_IMPROVEMENTS_OPEN_SUMMARY_STATUSES:
            has_null_execution = (
                _literal_or_none(fields.get("execution_kind")) is None
                or _literal_or_none(fields.get("execution_ref")) is None
            )
            rows.append((line_no, assigned_status.lower(), has_null_execution))
            continue
        cells = _split_decision_cells(line)
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
        status = _strip_cell(cells[status_index]).lower()
        if status in PROCESS_IMPROVEMENTS_OPEN_SUMMARY_STATUSES:
            execution_kind = ""
            execution_ref = ""
            if "execution_kind" in header:
                execution_kind_index = header.index("execution_kind")
                if execution_kind_index < len(cells):
                    execution_kind = cells[execution_kind_index]
            if "execution_ref" in header:
                execution_ref_index = header.index("execution_ref")
                if execution_ref_index < len(cells):
                    execution_ref = cells[execution_ref_index]
            has_null_execution = _literal_or_none(execution_kind) is None or _literal_or_none(execution_ref) is None
            rows.append((line_no, status, has_null_execution))
    return rows


def _process_improvements_open_summary_count(
    summary: dict[str, str],
    field: str,
) -> int | None:
    raw = summary.get(field, "")
    try:
        value = int(raw)
    except ValueError:
        return None
    if value < 0:
        return None
    return value


def _lint_process_improvements_open_summary(
    report: HarvestArtifact,
    section_lines: Sequence[tuple[int, str]],
    *,
    has_no_followups: bool,
) -> list[Finding]:
    raw_summary_rows = _raw_process_improvement_summary_rows(section_lines)
    summary_lines = _process_improvements_open_summary_lines(section_lines)
    if not summary_lines:
        if has_no_followups and raw_summary_rows:
            line_no = raw_summary_rows[0][0]
            return [
                Finding(
                    rel_path=report.rel_path,
                    line_no=line_no,
                    code="missing_process_improvements_open_summary",
                    message=(
                        "`NO FOLLOWUPS` covers ordinary followups only; open/triaged/promoted "
                        "process-improvement rows require a compact `process_improvements_open_summary`."
                    ),
                )
            ]
        return []

    if len(summary_lines) > 1:
        return [
            Finding(
                rel_path=report.rel_path,
                line_no=summary_lines[1][0],
                code="invalid_process_improvements_open_summary",
                message="Keep exactly one `process_improvements_open_summary` line in the PI decisions section.",
            )
        ]

    line_no, line = summary_lines[0]
    summary = _parse_process_improvements_open_summary_line(line)
    if summary is None:
        return [
            Finding(
                rel_path=report.rel_path,
                line_no=line_no,
                code="invalid_process_improvements_open_summary",
                message="Malformed `process_improvements_open_summary` line.",
            )
        ]

    missing = [key for key in PROCESS_IMPROVEMENTS_OPEN_SUMMARY_REQUIRED_KEYS if key not in summary]
    if missing:
        return [
            Finding(
                rel_path=report.rel_path,
                line_no=line_no,
                code="invalid_process_improvements_open_summary",
                message="`process_improvements_open_summary` missing key(s): " + ", ".join(missing),
            )
        ]

    findings: list[Finding] = []
    if summary["source"] != PROCESS_IMPROVEMENTS_OPEN_SUMMARY_SOURCE:
        findings.append(
            Finding(
                rel_path=report.rel_path,
                line_no=line_no,
                code="invalid_process_improvements_open_summary",
                message=(
                    "`process_improvements_open_summary.source` must be "
                    f"`{PROCESS_IMPROVEMENTS_OPEN_SUMMARY_SOURCE}`."
                ),
            )
        )
    if summary["lane"].lower() != "separate":
        findings.append(
            Finding(
                rel_path=report.rel_path,
                line_no=line_no,
                code="invalid_process_improvements_open_summary",
                message="`process_improvements_open_summary.lane` must be `separate`.",
            )
        )
    if summary["ordinary_followups"].upper() != "NO FOLLOWUPS":
        findings.append(
            Finding(
                rel_path=report.rel_path,
                line_no=line_no,
                code="invalid_process_improvements_open_summary",
                message="`process_improvements_open_summary.ordinary_followups` must be `NO FOLLOWUPS`.",
            )
        )

    counts: dict[str, int] = {}
    for field in ("open", "triaged", "promoted", "null_execution"):
        value = _process_improvements_open_summary_count(summary, field)
        if value is None:
            findings.append(
                Finding(
                    rel_path=report.rel_path,
                    line_no=line_no,
                    code="invalid_process_improvements_open_summary",
                    message=f"`process_improvements_open_summary.{field}` must be a non-negative integer.",
                )
            )
            continue
        counts[field] = value
    if not findings:
        expected_counts = {
            status: sum(1 for _, raw_status, _ in raw_summary_rows if raw_status == status)
            for status in PROCESS_IMPROVEMENTS_OPEN_SUMMARY_STATUSES
        }
        expected_null_execution = sum(1 for _, _, has_null_execution in raw_summary_rows if has_null_execution)
        for field, expected in expected_counts.items():
            if counts[field] != expected:
                findings.append(
                    Finding(
                        rel_path=report.rel_path,
                        line_no=line_no,
                        code="invalid_process_improvements_open_summary",
                        message=(
                            f"`process_improvements_open_summary.{field}` must match visible "
                            f"`{field}` PI rows: expected {expected}, got {counts[field]}."
                        ),
                    )
                )
        if counts["null_execution"] != expected_null_execution:
            findings.append(
                Finding(
                    rel_path=report.rel_path,
                    line_no=line_no,
                    code="invalid_process_improvements_open_summary",
                    message=(
                        "`process_improvements_open_summary.null_execution` must match visible "
                        f"PI rows with null execution fields: expected {expected_null_execution}, "
                        f"got {counts['null_execution']}."
                    ),
                )
            )
        status_total = counts["open"] + counts["triaged"] + counts["promoted"]
        if raw_summary_rows and status_total == 0:
            findings.append(
                Finding(
                    rel_path=report.rel_path,
                    line_no=line_no,
                    code="invalid_process_improvements_open_summary",
                    message="`process_improvements_open_summary` must count visible open/triaged/promoted PI rows.",
                )
            )
        if counts["null_execution"] > status_total:
            findings.append(
                Finding(
                    rel_path=report.rel_path,
                    line_no=line_no,
                    code="invalid_process_improvements_open_summary",
                    message="`process_improvements_open_summary.null_execution` cannot exceed open+triaged+promoted.",
                )
            )
    if not _literal_or_none(summary["owner_or_next_step"]):
        findings.append(
            Finding(
                rel_path=report.rel_path,
                line_no=line_no,
                code="invalid_process_improvements_open_summary",
                message="`process_improvements_open_summary.owner_or_next_step` is required.",
            )
        )
    return findings


def _load_process_improvement_records(project_root: Path) -> tuple[list[ProcessImprovementRecord], str | None]:
    records: list[ProcessImprovementRecord] = []
    try:
        backlog_paths = PROCESS_IMPROVEMENTS.iter_backlog_paths(project_root)
        for backlog_path in backlog_paths:
            backlog = PROCESS_IMPROVEMENTS.parse_backlog_file(backlog_path, project_root)
            file_rel = backlog_path.relative_to(project_root).as_posix()
            for entry in backlog.entries:
                records.append(
                    ProcessImprovementRecord(
                        file_rel=file_rel,
                        source_ref=backlog.source_ref,
                        entry=entry,
                    )
                )
    except (OSError, ValueError) as exc:
        return records, str(exc)
    return records, None


def _entry_source_keys(record: ProcessImprovementRecord) -> set[str]:
    entry_source_ref = getattr(record.entry, "source_ref")
    keys = {
        record.file_rel,
        record.source_ref,
        entry_source_ref,
    }
    for raw in (record.file_rel, record.source_ref, entry_source_ref):
        path = Path(str(raw))
        stem = path.stem
        keys.add(stem)
        keys.add(path.as_posix())
        timestamped_match = TIMESTAMPED_SLUG_RE.match(stem)
        if timestamped_match:
            slug = timestamped_match.group("slug")
            keys.add(slug)
            if slug.startswith("process_"):
                keys.add(slug.removeprefix("process_"))
    return {key for key in keys if key}


def _resolve_process_improvement_record(
    decision: ProcessImprovementDecision,
    records: Sequence[ProcessImprovementRecord],
) -> tuple[ProcessImprovementRecord | None, str | None]:
    candidates = list(records)
    if decision.source_ref is not None:
        candidates = [record for record in candidates if decision.source_ref in _entry_source_keys(record)]

    candidates = [record for record in candidates if getattr(record.entry, "entry_id") == decision.entry_id]

    if decision.source_ref is None and decision.source_hint is not None:
        candidates = [record for record in candidates if decision.source_hint in _entry_source_keys(record)]

    if len(candidates) == 1:
        return candidates[0], None
    if not candidates:
        return None, "missing"
    return None, "ambiguous"


def _has_deferred_carrier(decision: ProcessImprovementDecision, record: ProcessImprovementRecord) -> bool:
    entry = record.entry
    if _literal_or_none(getattr(entry, "execution_kind")) is not None and _literal_or_none(getattr(entry, "execution_ref")) is not None:
        return True
    return _literal_or_none(getattr(entry, "delivery_refs")) is not None


def _delivery_ref_values(raw: str) -> set[str]:
    value = _literal_or_none(raw)
    if value is None:
        return set()
    return {part.strip() for part in value.split("; ") if part.strip()}


def _is_followup_bridge(decision: ProcessImprovementDecision) -> bool:
    return decision.execution_kind == "external_ref" and decision.execution_ref is not None and decision.execution_ref.startswith("docs/followups/")


def _deferred_decision_field_findings(
    report: HarvestArtifact,
    decision: ProcessImprovementDecision,
    record: ProcessImprovementRecord,
) -> list[Finding]:
    findings: list[Finding] = []
    if decision.reason is None:
        findings.append(
            Finding(
                rel_path=report.rel_path,
                line_no=decision.line_no,
                code="process_improvement_decision_state_mismatch",
                message=(
                    f"Deferred process-improvement decision for `{record.file_rel}:{decision.entry_id}` "
                    "requires a reason."
                ),
            )
        )
    if decision.owner_or_next_step is None:
        findings.append(
            Finding(
                rel_path=report.rel_path,
                line_no=decision.line_no,
                code="process_improvement_decision_state_mismatch",
                message=(
                    f"Deferred process-improvement decision for `{record.file_rel}:{decision.entry_id}` "
                    "requires owner_or_next_step or revisit condition."
                ),
            )
        )
    if _is_followup_bridge(decision) and decision.execution_ref not in _delivery_ref_values(getattr(record.entry, "delivery_refs")):
        findings.append(
            Finding(
                rel_path=report.rel_path,
                line_no=decision.line_no,
                code="process_improvement_decision_state_mismatch",
                message=(
                    f"Deferred process-improvement decision for `{record.file_rel}:{decision.entry_id}` "
                    "uses an ordinary follow-up bridge that is not backlinked from raw delivery_refs."
                ),
            )
        )
    if (
        decision.execution_ref is not None
        and not _is_followup_bridge(decision)
        and decision.execution_ref != _literal_or_none(getattr(record.entry, "execution_ref"))
        and decision.execution_ref not in _delivery_ref_values(getattr(record.entry, "delivery_refs"))
    ):
        findings.append(
            Finding(
                rel_path=report.rel_path,
                line_no=decision.line_no,
                code="process_improvement_decision_state_mismatch",
                message=(
                    f"Deferred process-improvement decision for `{record.file_rel}:{decision.entry_id}` "
                    "uses an execution_ref that is not materialized in raw execution_ref or delivery_refs."
                ),
            )
        )
    return findings


def _validate_process_improvement_decision(
    report: HarvestArtifact,
    decision: ProcessImprovementDecision,
    record: ProcessImprovementRecord,
) -> list[Finding]:
    entry = record.entry
    actual_status = getattr(entry, "status")
    findings: list[Finding] = []

    expected_status = decision.decision
    if expected_status == "deferred":
        if actual_status == "deferred" or (
            actual_status in {"open", "unconfirmed", "triaged"} and _has_deferred_carrier(decision, record)
        ):
            findings.extend(_deferred_decision_field_findings(report, decision, record))
            return findings
        findings.append(
            Finding(
                rel_path=report.rel_path,
                line_no=decision.line_no,
                code="process_improvement_decision_state_mismatch",
                message=(
                    f"Process-improvement decision `{decision.decision}` for `{record.file_rel}:{decision.entry_id}` "
                    f"does not match raw row status `{actual_status}` or a materialized deferral carrier."
                ),
            )
        )
        return findings
    elif actual_status == expected_status:
        pass
    else:
        findings.append(
            Finding(
                rel_path=report.rel_path,
                line_no=decision.line_no,
                code="process_improvement_decision_state_mismatch",
                message=(
                    f"Process-improvement decision `{decision.decision}` for `{record.file_rel}:{decision.entry_id}` "
                    f"does not match raw row status `{actual_status}`."
                ),
            )
        )
        return findings

    if expected_status == "promoted":
        if getattr(entry, "execution_kind") == "null" or getattr(entry, "execution_ref") == "null":
            findings.append(
                Finding(
                    rel_path=report.rel_path,
                    line_no=decision.line_no,
                    code="process_improvement_decision_state_mismatch",
                    message=(
                        f"Promoted process-improvement decision for `{record.file_rel}:{decision.entry_id}` "
                        "requires raw row execution_kind and execution_ref."
                    ),
                )
            )
        if decision.execution_kind is not None and decision.execution_kind != getattr(entry, "execution_kind"):
            findings.append(
                Finding(
                    rel_path=report.rel_path,
                    line_no=decision.line_no,
                    code="process_improvement_decision_execution_mismatch",
                    message=(
                        f"Process-improvement decision execution_kind `{decision.execution_kind}` does not match "
                        f"raw row `{getattr(entry, 'execution_kind')}` for `{record.file_rel}:{decision.entry_id}`."
                    ),
                )
            )
        if decision.execution_ref is not None and decision.execution_ref != getattr(entry, "execution_ref"):
            findings.append(
                Finding(
                    rel_path=report.rel_path,
                    line_no=decision.line_no,
                    code="process_improvement_decision_execution_mismatch",
                    message=(
                        f"Process-improvement decision execution_ref `{decision.execution_ref}` does not match "
                        f"raw row `{getattr(entry, 'execution_ref')}` for `{record.file_rel}:{decision.entry_id}`."
                    ),
                )
            )

    return findings


def _lint_process_improvement_decisions(report: HarvestArtifact) -> list[Finding]:
    section = _section_lines(report.lines, PROCESS_IMPROVEMENT_DECISIONS_TITLE)
    if not section:
        return []

    decisions = _process_improvement_decisions(section)
    if not decisions:
        return []

    records, load_error = _load_process_improvement_records(report.repo_root)
    if load_error is not None:
        return [
            Finding(
                rel_path=report.rel_path,
                line_no=decisions[0].line_no,
                code="unresolved_process_improvement_row",
                message=f"Could not load process-improvement rows: {load_error}",
            )
        ]

    findings: list[Finding] = []
    for decision in decisions:
        record, state = _resolve_process_improvement_record(decision, records)
        if record is None:
            findings.append(
                Finding(
                    rel_path=report.rel_path,
                    line_no=decision.line_no,
                    code="unresolved_process_improvement_row",
                    message=(
                        f"Could not resolve process-improvement row `{decision.entry_id}`"
                        + (f" with source hint `{decision.source_hint}`" if decision.source_hint else "")
                        + f" ({state}). Use explicit source_ref, entry_id, or an exact unique plan slug."
                    ),
                )
            )
            continue
        findings.extend(_validate_process_improvement_decision(report, decision, record))
    return findings


def _needs_packetization_gate_receipt(lines: Sequence[str]) -> bool:
    text = "\n".join(lines).lower()
    if PACKETIZATION_GATE_TOKEN in text:
        return False
    return any(token in text for token in PACKETIZATION_TRIGGER_TOKENS)


def _backlog_has_open_items(report: HarvestArtifact, backlog_refs: Sequence[tuple[int, str]]) -> bool:
    for _, raw_path in backlog_refs:
        if _is_placeholder_path(raw_path):
            continue
        resolved = _resolve_backlog_path(report, raw_path)
        if not resolved.exists():
            continue
        text = resolved.read_text(encoding="utf-8", errors="replace").lower()
        if any(token in text for token in ("status=open", "status=unconfirmed", "status: `open`", "status: `unconfirmed`")):
            return True
    return False


def _is_durable_followups_ref(value: str) -> bool:
    raw_ref = value.strip().strip("`").strip(".,;()[]<>")
    if not DURABLE_FOLLOWUPS_REF_RE.fullmatch(raw_ref):
        return False
    path_text = raw_ref.split("#", 1)[0]
    if ":" in path_text:
        maybe_path, maybe_line = path_text.rsplit(":", 1)
        if not maybe_line.isdigit():
            return False
        path_text = maybe_path
    path = Path(path_text)
    return path_text.startswith(("docs/followups/", "docs/plans/")) and path.suffix == ".md" and ".." not in path.parts


def _has_durable_followups_ref_token(text: str) -> bool:
    for match in DURABLE_FOLLOWUPS_REF_TOKEN_RE.finditer(text):
        if _is_durable_followups_ref(match.group("ref")):
            return True
    return False


def _has_durable_followups_closeout_ref(text: str) -> bool:
    for match in DURABLE_FOLLOWUPS_CLOSEOUT_FIELD_RE.finditer(text):
        if _is_durable_followups_ref(match.group("ref")):
            return True
    return False


def _has_already_tracked_elsewhere_durable_ref(text: str) -> bool:
    return any("already tracked elsewhere" in line and _has_durable_followups_ref_token(line) for line in text.splitlines())


def _lint_current_report_receipts(
    report: HarvestArtifact,
    headings: dict[str, int],
    backlog_refs: Sequence[tuple[int, str]],
) -> list[Finding]:
    findings: list[Finding] = []
    required_sections = (
        (
            FOLLOWUP_TRIAGE_RECEIPT_TITLE,
            "missing_followup_harvest_triage_receipt",
            "`## Follow-up harvest triage/import receipt` is required for current plan-harvest reports.",
        ),
        (
            PROCESS_IMPROVEMENT_DECISIONS_TITLE,
            "missing_process_improvement_decisions_receipt",
            "`## Process-improvement promotion decisions` is required for current plan-harvest reports.",
        ),
        (
            RETRIEVAL_METRICS_RECEIPT_TITLE,
            "missing_retrieval_metrics_receipt",
            "`## Docs retrieval metrics receipt` is required for current plan-harvest reports.",
        ),
        (
            GOLDEN_PATH_LANE_RECEIPT_TITLE,
            "missing_golden_path_lane_receipt",
            "`## Golden Path lane receipt` is required for current plan-harvest reports.",
        ),
        (
            ADR_DECISIONS_RECEIPT_TITLE,
            "missing_adr_decisions_receipt",
            "`## ADR candidates / durable decisions` is required for current plan-harvest reports.",
        ),
        (
            CANON_FOLLOWUP_SUMMARY_TITLE,
            "missing_canon_followup_summary_receipt",
            "`## Canon/follow-up summary` is required for current plan-harvest reports.",
        ),
    )

    for title, code, message in required_sections:
        line_no = headings.get(title)
        if line_no is None:
            findings.append(Finding(report.rel_path, 1, code, message))
            continue
        if not _section_has_content(_section_lines(report.lines, title)):
            findings.append(
                Finding(
                    report.rel_path,
                    line_no,
                    code.replace("missing_", "invalid_", 1),
                    f"`## {title}` must contain a literal receipt row or explicit no-op reason.",
                )
            )

    followup_section = _section_lines(report.lines, FOLLOWUP_TRIAGE_RECEIPT_TITLE)
    if _section_has_content(followup_section):
        section_text = "\n".join(line for _, line in followup_section).lower()
        if "planveyor_followups_triage" in section_text and "n/a" in section_text and _backlog_has_open_items(report, backlog_refs):
            line_no = next((line_no for line_no, line in followup_section if "n/a" in line.lower()), headings[FOLLOWUP_TRIAGE_RECEIPT_TITLE])
            findings.append(
                Finding(
                    report.rel_path,
                    line_no,
                    code="invalid_followup_harvest_triage_receipt",
                    message="`planveyor_followups_triage: N/A` is invalid while referenced backlog rows remain open/UNCONFIRMED.",
                )
            )
        required_tokens = (
            "planveyor_followups_triage",
            "--dry-run",
            "--apply",
            "idempotency",
            "followups_index_rebuild.py",
        )
        missing_tokens = [token for token in required_tokens if token not in section_text]
        if missing_tokens and "n/a" not in section_text:
            findings.append(
                Finding(
                    report.rel_path,
                    headings[FOLLOWUP_TRIAGE_RECEIPT_TITLE],
                    code="invalid_followup_harvest_triage_receipt",
                    message=(
                        "`## Follow-up harvest triage/import receipt` must cite triage dry-run/apply/"
                        f"idempotency plus index rebuild/readback; missing: {', '.join(missing_tokens)}."
                    ),
                )
            )
        if (
            FOLLOWUPS_RANGE_CLOSURE_CLAIM_RE.search(section_text)
            and "--range" not in section_text
            and not _has_durable_followups_closeout_ref(section_text)
            and not _has_already_tracked_elsewhere_durable_ref(section_text)
        ):
            findings.append(
                Finding(
                    report.rel_path,
                    headings[FOLLOWUP_TRIAGE_RECEIPT_TITLE],
                    code="invalid_followup_harvest_triage_receipt",
                    message=(
                        "Followups handled/cleanup-ready claims require range-mode proof or "
                        "an explicit durable manual_decision_ref/already_tracked_ref docs/followups or docs/plans pointer."
                    ),
                )
            )

    golden_section = _section_lines(report.lines, GOLDEN_PATH_LANE_RECEIPT_TITLE)
    if _section_has_content(golden_section):
        section_text = "\n".join(line for _, line in golden_section).lower()
        if not any(anchor in section_text for anchor in GOLDEN_PATH_ANCHORS):
            findings.append(
                Finding(
                    report.rel_path,
                    headings[GOLDEN_PATH_LANE_RECEIPT_TITLE],
                    code="invalid_golden_path_lane_receipt",
                    message="Golden Path lane receipt must cite a known `docs/guides/golden_paths.md` anchor.",
                )
            )

    process_section = _section_lines(report.lines, PROCESS_IMPROVEMENT_DECISIONS_TITLE)
    if _section_has_content(process_section):
        findings.extend(
            _lint_process_improvements_open_summary(
                report,
                process_section,
                has_no_followups=any(NO_FOLLOWUPS_TOKEN in line.lower() for line in report.lines),
            )
        )

    if _needs_packetization_gate_receipt(report.lines):
        line_no = _first_retrieval_metrics_trigger_line(report.lines)
        findings.append(
            Finding(
                report.rel_path,
                line_no,
                code="missing_packetization_gate_receipt",
                message="Shared canon/canon-sweep text requires packetization handoff/readback token `step:packetization_gate`.",
            )
        )

    return findings


def _resolve_backlog_path(report: HarvestArtifact, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path.resolve()
    return (report.repo_root / raw_path).resolve()


def _wrap_followups_findings(repo_root: Path, findings) -> list[Finding]:
    wrapped: list[Finding] = []
    for finding in findings:
        rel_path = finding.rel_path
        if Path(rel_path).is_absolute():
            rel_path = _relative_path(repo_root, Path(rel_path))
        wrapped.append(
            Finding(
                rel_path=rel_path,
                line_no=finding.line_no or 1,
                code=f"followups_lint_{finding.code}",
                message=finding.message,
            )
        )
    return wrapped


def _lint_backlog_artifact(backlog: HarvestArtifact) -> list[Finding]:
    findings: list[Finding] = []
    headings = _heading_locations(backlog.lines)
    if RANGE_RESULT_TITLE not in headings and FOLLOWUPS_BACKLOG_TITLE_ALT not in headings:
        findings.append(
            Finding(
                rel_path=backlog.rel_path,
                line_no=1,
                code="missing_backlog_outcome_section",
                message="Missing required backlog section '## Range result' or '## Follow-ups (backlog)'",
            )
        )

    no_followups_lines = [
        (line_no, line)
        for line_no, line in enumerate(backlog.lines, start=1)
        if NO_FOLLOWUPS_TOKEN in line.lower()
    ]
    for line_no, line in no_followups_lines:
        if _has_allowed_no_followups_reason(line):
            continue
        findings.append(
            Finding(
                rel_path=backlog.rel_path,
                line_no=line_no,
                code="invalid_no_followups_reason",
                message="NO FOLLOWUPS must keep one allowed reason in the same receipt line",
            )
        )

    raw_path: str
    try:
        raw_path = str(backlog.path.relative_to(backlog.repo_root))
    except ValueError:
        raw_path = str(backlog.path)
    followup_files = FOLLOWUPS_LINT.load_followup_files(backlog.repo_root, [raw_path])
    followup_findings = FOLLOWUPS_LINT.lint_followup_files(followup_files, backlog.repo_root)
    if followup_findings:
        findings.extend(_wrap_followups_findings(backlog.repo_root, followup_findings))
        return findings

    if no_followups_lines:
        return findings

    if followup_files and any(file.items for file in followup_files):
        return findings

    findings.append(
        Finding(
            rel_path=backlog.rel_path,
            line_no=1,
            code="missing_backlog_outcome",
            message="Backlog must materialize follow-up items or an explicit NO FOLLOWUPS outcome",
        )
    )
    return findings


def _lint_report_artifact(
    report: HarvestArtifact,
    explicit_backlogs: dict[Path, HarvestArtifact],
    seen_backlogs: set[Path],
) -> list[Finding]:
    findings: list[Finding] = []
    schema_class, schema_findings = _classify_review_schema_version(report)
    findings.extend(schema_findings)
    headings = _heading_locations(report.lines)
    if FOLLOWUPS_BACKLOG_TITLE not in headings:
        findings.append(
            Finding(
                rel_path=report.rel_path,
                line_no=1,
                code="missing_backlog_section",
                message="Missing required section '## Follow-ups backlog (created)'",
            )
        )
    if FOLLOWUPS_EXTRACTED_TITLE not in headings:
        findings.append(
            Finding(
                rel_path=report.rel_path,
                line_no=1,
                code="missing_followups_section",
                message="Missing required section '## Follow-ups (extracted; без дублей)'",
            )
        )

    backlog_section = _section_lines(report.lines, FOLLOWUPS_BACKLOG_TITLE)
    backlog_refs = _extract_backlog_refs(backlog_section)
    has_no_followups = any(NO_FOLLOWUPS_TOKEN in line.lower() for line in report.lines)
    if has_no_followups and not backlog_refs:
        findings.append(
            Finding(
                rel_path=report.rel_path,
                line_no=1,
                code="missing_backlog_ref",
                message="Harvest report with NO FOLLOWUPS must point to a standalone docs/followups backlog artifact",
            )
        )

    seen_paths: set[Path] = set()
    for line_no, raw_path in backlog_refs:
        if not raw_path.startswith("docs/followups/"):
            findings.append(
                Finding(
                    rel_path=report.rel_path,
                    line_no=line_no,
                    code="invalid_backlog_ref",
                    message=f"Backlog ref must stay under docs/followups/: {raw_path}",
                )
            )
            continue
        if _is_placeholder_path(raw_path):
            continue

        resolved = _resolve_backlog_path(report, raw_path)
        if resolved in seen_paths:
            continue
        seen_paths.add(resolved)
        seen_backlogs.add(resolved)
        if not resolved.exists():
            findings.append(
                Finding(
                    rel_path=report.rel_path,
                    line_no=line_no,
                    code="missing_backlog_file",
                    message=f"Missing referenced backlog artifact: {raw_path}",
                )
            )
            continue

        backlog = explicit_backlogs.get(resolved)
        if backlog is None:
            text = resolved.read_text(encoding="utf-8", errors="replace")
            text_lines = tuple(text.splitlines())
            backlog = HarvestArtifact(
                path=resolved,
                rel_path=_relative_path(REPO_ROOT, resolved),
                lines=text_lines,
                first_heading=_first_heading(text_lines),
                kind="backlog",
                repo_root=report.repo_root,
            )
        findings.extend(_lint_backlog_artifact(backlog))

    if schema_class == "current":
        findings.extend(_lint_current_report_receipts(report, headings, backlog_refs))
        findings.extend(
            parse_plan_harvest_file_followups_receipt(
                "\n".join(report.lines),
                rel_path=report.rel_path,
            ).findings
        )

    if _needs_derived_index_receipt(report.lines):
        build_line = _find_line(report.lines, DERIVED_INDEX_BUILD_TOKEN)
        if build_line is None:
            findings.append(
                Finding(
                    rel_path=report.rel_path,
                    line_no=1,
                    code="missing_derived_index_receipt",
                    message=f"Missing derived-index build token '{DERIVED_INDEX_BUILD_TOKEN}'",
                )
            )

        check_line = _find_line(report.lines, DERIVED_INDEX_CHECK_TOKEN)
        if check_line is None:
            findings.append(
                Finding(
                    rel_path=report.rel_path,
                    line_no=1,
                    code="missing_derived_index_receipt",
                    message=f"Missing derived-index check token '{DERIVED_INDEX_CHECK_TOKEN}'",
                )
            )

        full_text = "\n".join(report.lines)
        for corpus, summary_re in DERIVED_INDEX_SUMMARY_RE.items():
            if summary_re.search(full_text):
                continue
            findings.append(
                Finding(
                    rel_path=report.rel_path,
                    line_no=1,
                    code="missing_derived_index_receipt",
                    message=f"Missing derived-index coverage summary for '{corpus}'",
                )
            )

    findings.extend(_lint_retrieval_metrics_receipt(report))
    findings.extend(
        Finding(
            rel_path=report.rel_path,
            line_no=receipt.line_no,
            code=receipt.code,
            message=receipt.message,
        )
        for receipt in retrieval_telemetry_receipt.lint_retrieval_telemetry_receipt(
            report.lines,
            decision_evidence_only=True,
        )
    )

    for line_no, line in enumerate(report.lines, start=1):
        if NO_FOLLOWUPS_TOKEN not in line.lower():
            continue
        if PROCESS_IMPROVEMENTS_OPEN_SUMMARY_FIELD in line:
            continue
        if _has_allowed_no_followups_reason(line):
            continue
        findings.append(
            Finding(
                rel_path=report.rel_path,
                line_no=line_no,
                code="invalid_no_followups_reason",
                message="NO FOLLOWUPS must keep one allowed reason in the same receipt line",
            )
        )

    findings.extend(_lint_process_improvement_decisions(report))

    return findings


def _lint_audit_artifact(audit: HarvestArtifact) -> list[Finding]:
    findings: list[Finding] = []
    _, schema_findings = _classify_review_schema_version(audit)
    findings.extend(schema_findings)
    findings.extend(_lint_retrieval_metrics_receipt(audit))
    findings.extend(
        Finding(
            rel_path=audit.rel_path,
            line_no=receipt.line_no,
            code=receipt.code,
            message=receipt.message,
        )
        for receipt in retrieval_telemetry_receipt.lint_retrieval_telemetry_receipt(
            audit.lines,
            decision_evidence_only=True,
        )
    )
    return findings


def lint_harvest_artifacts(artifacts: Sequence[HarvestArtifact]) -> list[Finding]:
    findings: list[Finding] = []
    seen_backlogs: set[Path] = set()
    explicit_backlogs = {artifact.path: artifact for artifact in artifacts if artifact.kind == "backlog"}

    for artifact in artifacts:
        if artifact.kind == "report":
            findings.extend(_lint_report_artifact(artifact, explicit_backlogs, seen_backlogs))
            continue
        if artifact.kind == "audit":
            findings.extend(_lint_audit_artifact(artifact))
            continue
        if artifact.path in seen_backlogs:
            continue
        seen_backlogs.add(artifact.path)
        findings.extend(_lint_backlog_artifact(artifact))

    return findings


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lint plan-harvest carriers and backlog linkage.")
    parser.add_argument("paths", nargs="*", help="Optional harvest report/backlog file or directory paths.")
    args = parser.parse_args(argv)

    try:
        initial_context = resolve_top_level_context()
        # Default legacy templates stay tooling-owned in
        # ``_default_template_scope``.  Use the single direct-CLI capture for
        # the reader call instead of resolving authority a second time.
        project_root = initial_context.project_root.resolve()
        context: ContractContext | None = initial_context
        artifacts = load_harvest_artifacts(project_root, args.paths, context=context)
    except (FileNotFoundError, ContractAuthorityError, ValueError) as exc:
        print(f"plan-harvest-lint: FAIL\n{exc}")
        return 1

    findings = lint_harvest_artifacts(artifacts)
    if findings:
        print("plan-harvest-lint: FAIL")
        for finding in findings:
            print(finding.render())
        return 1

    print("plan-harvest-lint: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

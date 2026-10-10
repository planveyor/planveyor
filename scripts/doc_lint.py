#!/usr/bin/env python3
"""Lightweight docs lint for planveyor canonical documentation.

Checks:
1) Broken local markdown links.
2) Optional inline code span repo refs (``...``).
3) Shared reviewability preflight receipt drift across the exact ten-file bundle.
4) Shared reviewer/manager deadlock contract drift across the exact seven-file bundle.
5) Harvest/followups durable-carrier drift for range receipts/backlogs.
6) Optional explicit-root basic hygiene for finalized docs artifacts.

Default scope is the durable/canonical docs surface for this repo, not plans,
snapshots, or review artifacts.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Iterable, Sequence
from urllib.parse import unquote


REPO_ROOT = Path(__file__).resolve().parents[1]
# This remains an explicit environment input only. There is no sibling-repo
# fallback: a cross-repository check names its root with --product-root or
# PLANVEYOR_PRODUCT_ROOT.
_explicit_product_root = os.environ.get("PLANVEYOR_PRODUCT_ROOT", "").strip()
PRODUCT_REPO_ROOT = Path(_explicit_product_root).resolve() if _explicit_product_root else None
_KNOWN_CONTENT_PROFILES = frozenset({"default", "planveyor", "target-local"})


class ProductRootPolicyError(ValueError):
    """The selected fixed doc-lint product-root policy is unavailable."""


@dataclass(frozen=True)
class ProductRootPolicy:
    allowed_ref_prefixes: tuple[str, ...]
    root_filenames: tuple[str, ...]


GENERIC_PRODUCT_ROOT_POLICY = ProductRootPolicy(
    allowed_ref_prefixes=("docs/", "scripts/"),
    root_filenames=("Makefile", "AGENTS.md", "README.md"),
)


def _strict_product_policy(data: bytes) -> ProductRootPolicy:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ProductRootPolicyError(f"doc-lint product-root policy: duplicate key {key!r}")
            result[key] = value
        return result

    try:
        raw = json.loads(data.decode("utf-8"), object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError, ProductRootPolicyError) as exc:
        raise ProductRootPolicyError("doc-lint product-root policy: invalid JSON") from exc
    if not isinstance(raw, dict) or set(raw) != {"schema_version", "allowed_ref_prefixes", "root_filenames"}:
        raise ProductRootPolicyError("doc-lint product-root policy: unsupported schema")
    if raw.get("schema_version") != "doc-lint-product-root-policy.v1":
        raise ProductRootPolicyError("doc-lint product-root policy: unsupported schema version")
    prefixes = raw.get("allowed_ref_prefixes")
    names = raw.get("root_filenames")
    if not isinstance(prefixes, list) or not isinstance(names, list):
        raise ProductRootPolicyError("doc-lint product-root policy: invalid list field")
    if not prefixes or not names or any(not isinstance(value, str) or not value for value in [*prefixes, *names]):
        raise ProductRootPolicyError("doc-lint product-root policy: invalid path value")
    if len(set(prefixes)) != len(prefixes) or len(set(names)) != len(names):
        raise ProductRootPolicyError("doc-lint product-root policy: duplicate path value")
    if any(not value.endswith("/") or value.startswith("/") or ".." in value for value in prefixes):
        raise ProductRootPolicyError("doc-lint product-root policy: invalid reference prefix")
    if any("/" in value or value in {".", ".."} for value in names):
        raise ProductRootPolicyError("doc-lint product-root policy: invalid root filename")
    return ProductRootPolicy(tuple(prefixes), tuple(names))


def load_product_root_policy(
    *,
    content_profile_id: str = "default",
    policy_root: Path | None = None,
) -> ProductRootPolicy:
    """Return generic public policy without reading ``policy_root``.

    The parameter remains for API compatibility. Explicit caller policies use
    ProductRootPolicy through the existing checker arguments; selecting a
    public profile creates no consumer JSON prerequisite.
    """
    profile = content_profile_id.strip()
    if profile not in _KNOWN_CONTENT_PROFILES:
        raise ProductRootPolicyError(f"unsupported content_profile_id: {content_profile_id!r}")
    return GENERIC_PRODUCT_ROOT_POLICY


def _selected_product_root(value: str | None) -> Path | None:
    if value is None or not value.strip():
        if PRODUCT_REPO_ROOT is not None and not PRODUCT_REPO_ROOT.is_dir():
            raise ProductRootPolicyError(f"PLANVEYOR_PRODUCT_ROOT is not a directory: {PRODUCT_REPO_ROOT}")
        return PRODUCT_REPO_ROOT
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        raise ProductRootPolicyError("selected product root must be absolute")
    if not candidate.is_dir():
        raise ProductRootPolicyError(f"selected product root is not a directory: {candidate}")
    resolved = candidate.resolve()
    if PRODUCT_REPO_ROOT is not None and PRODUCT_REPO_ROOT != resolved:
        raise ProductRootPolicyError("--product-root conflicts with PLANVEYOR_PRODUCT_ROOT")
    return resolved

DEFAULT_ROOTS = (
    REPO_ROOT / "AGENTS.md",
    REPO_ROOT / "README.md",
    REPO_ROOT / "planveyor_owner_book.md",
    REPO_ROOT / "docs" / "code_drafts" / "_template.md",
    REPO_ROOT / "docs" / "roles",
    REPO_ROOT / "docs" / "playbooks",
    REPO_ROOT / "docs" / "tools",
)
DEFAULT_EXCLUDES = (
    REPO_ROOT / "docs" / "snapshots",
    REPO_ROOT / "docs" / "plans",
    REPO_ROOT / "docs" / "code_reviews",
    REPO_ROOT / "docs" / "doc_reviews",
)
DEFAULT_EXCLUDE_FILES: tuple[Path, ...] = ()

EXTERNAL_SCHEMES = ("http://", "https://", "mailto:", "tel:", "tg:", "ftp://")
ANCHOR_LINE_RE = re.compile(r"^L\d+(?:C\d+)?$")

CODE_REF_PREFIXES = ("docs/", "scripts/")
CODE_REF_PREFIXES_REPO = ("docs/", "scripts/", "var/")
ROOT_FILENAMES = ("Makefile", "AGENTS.md", "README.md", "planveyor_owner_book.md")
ALLOWED_CODE_REF_SUFFIXES = {
    ".csv",
    ".gif",
    ".jpeg",
    ".jpg",
    ".json",
    ".lock",
    ".md",
    ".png",
    ".py",
    ".sh",
    ".sqlite",
    ".svg",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
PLACEHOLDER_CODE_REF_SUBSTRINGS = (
    "NNN-topic.md",
    "YYMMDD",
    "YYYYMMDD",
    "YYYY-MM-DD",
)
PLACEHOLDER_CODE_REF_PATHS = frozenset({"docs/plans/...md"})

REF_DEF_RE = re.compile(r"^\s*\[[^\]]+\]:\s*(?P<dest>\S+)\s*$")
HEADING_RE = re.compile(r"^(?P<level>#{1,6})\s+(?P<text>.*)$")
TRAILING_WHITESPACE_RE = re.compile(r"[ \t]+$")
RAW_MERGE_MARKER_RE = re.compile(r"^(<<<<<<<|=======|>>>>>>>)")


@dataclass(frozen=True)
class Finding:
    file: Path
    line: int
    severity: str
    message: str


@dataclass(frozen=True)
class DeScopedDebtItem:
    source_plan: Path
    line: int
    text: str
    markers: tuple[str, ...]
    keywords: tuple[str, ...]


REVIEWABILITY_RECEIPT_ANCHOR = "reviewability preflight receipt"
PROOF_PATH_CLASS_ANCHOR = "proof-path class"
ANTI_FALSE_GREEN_ANCHOR = "helper family named + primary lane green + promised contextual lane still implicit/red"

REVIEWABILITY_RECEIPT_BUNDLE: tuple[str, ...] = (
    "docs/tools/prompts/architect_draft_discussion.md",
    "docs/tools/prompts/architect_status_driven.md",
    "docs/tools/prompts/architect_censor.md",
    "docs/tools/prompts/planner_status_driven.md",
    "docs/tools/prompts/planner_censor.md",
    "docs/tools/prompts/coder_status_driven.md",
    "docs/tools/prompts/coder_censor.md",
    "docs/roles/architect.md",
    "docs/roles/planner.md",
    "docs/roles/coder.md",
)
REVIEWABILITY_RECEIPT_REQUIRED_FILES = frozenset(REVIEWABILITY_RECEIPT_BUNDLE)
PROOF_PATH_CLASS_REQUIRED_FILES = frozenset(
    path for path in REVIEWABILITY_RECEIPT_BUNDLE if path != "docs/tools/prompts/coder_censor.md"
)
ANTI_FALSE_GREEN_REQUIRED_FILES = frozenset(
    (
        "docs/tools/prompts/architect_status_driven.md",
        "docs/tools/prompts/architect_censor.md",
        "docs/tools/prompts/planner_status_driven.md",
        "docs/tools/prompts/planner_censor.md",
        "docs/tools/prompts/coder_status_driven.md",
        "docs/tools/prompts/coder_censor.md",
        "docs/roles/planner.md",
        "docs/roles/coder.md",
    )
)
REVIEWABILITY_RECEIPT_ANCHOR_REQUIREMENTS: tuple[tuple[str, frozenset[str]], ...] = (
    (REVIEWABILITY_RECEIPT_ANCHOR, REVIEWABILITY_RECEIPT_REQUIRED_FILES),
    (PROOF_PATH_CLASS_ANCHOR, PROOF_PATH_CLASS_REQUIRED_FILES),
    (ANTI_FALSE_GREEN_ANCHOR, ANTI_FALSE_GREEN_REQUIRED_FILES),
)

RECEIPT_SCHEMA_EMITTER_INVENTORY_BUNDLE: tuple[str, ...] = (
    "docs/tools/prompts/planner_status_driven.md",
    "docs/tools/prompts/coder_censor.md",
    "docs/code_drafts/_template.md",
)
RECEIPT_SCHEMA_EMITTER_INVENTORY_ANCHORS: tuple[str, ...] = (
    "receipt schema emitter inventory",
    "generated skeleton/bootstrap/readback emitters",
    "target decision",
)

REVIEWER_MANAGER_DEADLOCK_BUNDLE: tuple[str, ...] = (
    "docs/roles/reviewer.md",
    "docs/tools/prompts/reviewer_status_driven.md",
    "docs/roles/manager.md",
    "docs/tools/prompts/manager_router.md",
    "docs/tools/prompts/manager_collab_pipeline.md",
    "docs/tools/prompts/manager_custom_pipeline.md",
    "docs/tools/prompts/manager_collab_merge_pipeline.md",
)
REVIEWER_MANAGER_DEADLOCK_FILE_ANCHORS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "docs/roles/reviewer.md",
        ("Loop signal", "Root cause class", "Next owner", "same-contract reroute vs scope gap"),
    ),
    (
        "docs/tools/prompts/reviewer_status_driven.md",
        (
            "Loop signal",
            "Root cause class",
            "Next owner",
            "same-contract reroute vs scope gap",
            "Extraordinary action",
        ),
    ),
    (
        "docs/roles/manager.md",
        ("router-only", "repeated same-status / same-blocker loop", "blind endless rerun"),
    ),
    (
        "docs/tools/prompts/manager_router.md",
        ("router-only", "Loop signal:", "Root cause class:", "Extraordinary action:", "Next owner:", "blind endless rerun"),
    ),
    (
        "docs/tools/prompts/manager_collab_pipeline.md",
        ("router-only", "Loop signal:", "Root cause class:", "Extraordinary action:", "Next owner:", "blind endless rerun"),
    ),
    (
        "docs/tools/prompts/manager_custom_pipeline.md",
        ("router-only", "Loop signal:", "Root cause class:", "Extraordinary action:", "Next owner:", "blind endless rerun"),
    ),
    (
        "docs/tools/prompts/manager_collab_merge_pipeline.md",
        ("router-only", "Loop signal:", "Root cause class:", "Extraordinary action:", "Next owner:", "blind endless rerun"),
    ),
)

HARVEST_REPORT_DIR = "docs/reviews/"
HARVEST_BACKLOG_DIR = "docs/followups/"
HARVEST_REPORT_NAME_TOKEN = "_plan_harvest"
HARVEST_AUDIT_NAME_TOKEN = "_post_merge_audit"
HARVEST_BACKLOG_NAME_TOKEN = "_followups_range_"
HARVEST_MEMORY_DUMP_TITLE = "memory dump"
HARVEST_NO_FOLLOWUPS_PHRASE = "no followups"
HARVEST_HANDLED_PHRASES = (
    "already tracked elsewhere",
    "already tracked in",
    "handled elsewhere",
    "status=handled",
)
HARVEST_CANON_CLOSURE_PHRASES = (
    "canon sync",
    "canon-sync",
    "canon closure",
    "closed by canon",
)
HARVEST_OWNER_REJECTION_PHRASES = (
    "explicit owner rejection",
    "owner rejection",
    "rejected by owner",
)
DE_SCOPED_DEBT_TRIGGER_PHRASES = (
    "removed from active scope",
    "intentionally removed",
    "если по-прежнему нужно",
    "отдельный follow-up",
)
DE_SCOPED_LOST_FOLLOWUP_PHRASES = (
    "lost follow-up during harvest",
    "lost follow-up during harvest/promotion",
)
DE_SCOPED_SHARED_GUARD_REQUIREMENTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "docs/plans/_template.md",
        ("already tracked elsewhere", "canon sync closed it"),
    ),
    (
        "docs/plans/README.md",
        ("removed from active scope", "already tracked elsewhere", "no followups"),
    ),
    (
        "docs/followups/_template_followups_backlog.md",
        ("removed from active scope", "already tracked elsewhere"),
    ),
    (
        "docs/playbooks/post_merge_plan_harvest.md",
        ("removed from active scope", "no followups", "already tracked elsewhere"),
    ),
    (
        "docs/playbooks/post_merge_audit.md",
        ("removed from active scope", "lost follow-up during harvest/promotion"),
    ),
    (
        "docs/tools/prompts/architect_plan_harvest.md",
        ("removed from active scope", "already tracked elsewhere", "no followups"),
    ),
    (
        "docs/tools/prompts/architect_post_merge_audit.md",
        ("removed from active scope", "lost follow-up during harvest/promotion"),
    ),
    (
        "docs/reviews/_template_plan_harvest.md",
        ("removed from active scope", "already tracked elsewhere", "no followups"),
    ),
    (
        "docs/reviews/_template_post_merge_audit.md",
        ("lost follow-up during harvest/promotion",),
    ),
)
DE_SCOPED_SHARED_GUARD_BUNDLE = tuple(rel_path for rel_path, _ in DE_SCOPED_SHARED_GUARD_REQUIREMENTS)
DE_SCOPED_PLAN_SECTION_TITLES = frozenset(("out of scope", "follow-ups (deferred)"))
DE_SCOPED_STOPWORDS = frozenset(
    {
        "active",
        "already",
        "architect",
        "because",
        "canon",
        "closed",
        "elsewhere",
        "follow",
        "followup",
        "followups",
        "from",
        "into",
        "item",
        "items",
        "later",
        "need",
        "needed",
        "owner",
        "plan",
        "planner",
        "presumably",
        "promotion",
        "removed",
        "scope",
        "tracked",
        "true",
        "when",
        "если",
        "который",
        "нужно",
        "отдельный",
        "план",
        "позже",
        "прежнему",
        "сейчас",
        "такой",
        "этот",
    }
)
INLINE_CODE_SPAN_RE = re.compile(r"`([^`]+)`")
WORD_TOKEN_RE = re.compile(r"[a-zA-Zа-яА-Я0-9][a-zA-Zа-яА-Я0-9_-]*")
MARKDOWN_DOC_REF_RE = re.compile(r"(?P<ref>(?:docs/)?[A-Za-z0-9_./-]+\.md)\b")

ADR_DIR = "docs/adr"
ADR_BUNDLE_FILES: tuple[str, ...] = (
    "docs/adr/README.md",
    "docs/adr/_template.md",
)
ADR_RUNTIME_EXCLUDES = frozenset({"README.md", "_template.md"})
ADR_ALLOWED_STATUSES = frozenset({"proposed", "accepted", "superseded"})
ADR_REQUIRED_FRONTMATTER_KEYS: tuple[str, ...] = (
    "status",
    "date",
    "decision-makers",
    "source-range",
    "source-plan",
    "code-anchor",
)
ADR_SUPERSESSION_SECTION = "superseded by / supersedes"
ADR_SUPERSEDES_LABEL = "supersedes"
ADR_SUPERSEDED_BY_LABEL = "superseded by"
ADR_BARE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
ADR_RUNTIME_NAME_RE = re.compile(r"^\d{3}-[a-z0-9][a-z0-9.-]*\.md$")
ADR_REQUIRED_SECTION_TITLES: tuple[str, ...] = (
    "context and problem statement",
    "decision drivers",
    "considered options",
    "decision outcome",
    "consequences",
    "canonical refs",
    "confirmation",
    "revisit signals",
    "superseded by / supersedes",
)


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _first_line_with_substring(text: str, needle: str) -> int:
    needle_lower = needle.lower()
    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        if needle_lower in raw_line.lower():
            return line_no
    return 1


def _parse_simple_frontmatter(markdown_file: Path) -> tuple[dict[str, str], dict[str, int]]:
    lines = markdown_file.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, {}

    frontmatter: dict[str, str] = {}
    line_numbers: dict[str, int] = {}
    for line_no, raw_line in enumerate(lines[1:], start=2):
        if raw_line.strip() == "---":
            return frontmatter, line_numbers
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        normalized_key = key.strip()
        normalized_value = value.strip().strip('"').strip("'")
        if not normalized_key:
            continue
        frontmatter[normalized_key] = normalized_value
        line_numbers[normalized_key] = line_no
    return {}, {}


def _extract_section_lines(markdown_file: Path, section_title: str) -> dict[str, tuple[str, int]]:
    lines = markdown_file.read_text(encoding="utf-8").splitlines()
    in_section = False
    collected: dict[str, tuple[str, int]] = {}

    for line_no, raw_line in enumerate(lines, start=1):
        heading_match = HEADING_RE.match(raw_line)
        if heading_match and len(heading_match.group("level")) == 2:
            in_section = _normalize_heading_text(heading_match.group("text")) == section_title
            continue
        if not in_section:
            continue
        if HEADING_RE.match(raw_line):
            break
        stripped = raw_line.strip()
        if not stripped.startswith("- ") or ":" not in stripped:
            continue
        label, value = stripped[2:].split(":", 1)
        collected[_normalize_heading_text(label)] = (value.strip(), line_no)

    return collected


def _find_h2_section_line(markdown_file: Path, section_title: str) -> int | None:
    lines = markdown_file.read_text(encoding="utf-8").splitlines()
    for line_no, raw_line in enumerate(lines, start=1):
        heading_match = HEADING_RE.match(raw_line)
        if not heading_match or len(heading_match.group("level")) != 2:
            continue
        if _normalize_heading_text(heading_match.group("text")) == section_title:
            return line_no
    return None


def _is_na_like(value: str) -> bool:
    cleaned = value.strip().strip("`").strip('"').strip("'").strip()
    if not cleaned:
        return True
    return cleaned.lower().startswith("n/a")


def _normalize_adr_ref_candidate(value: str) -> str | None:
    candidate = value.strip().strip("`").strip('"').strip("'").strip()
    if not candidate:
        return None
    if candidate.endswith(".md"):
        return candidate
    if "/" not in candidate and ADR_BARE_ID_RE.fullmatch(candidate):
        return candidate
    return None


def _extract_adr_ref(value: str) -> str | None:
    refs = extract_markdown_doc_refs(value)
    if refs:
        return refs[0]
    for code_span in extract_code_spans(value):
        normalized = _normalize_adr_ref_candidate(code_span)
        if normalized is not None:
            return normalized
    return _normalize_adr_ref_candidate(value)


def _resolve_adr_ref(source_file: Path, ref: str, repo_root: Path) -> Path:
    repo_root = repo_root.resolve()
    if ref.endswith(".md"):
        if ref.startswith(f"{ADR_DIR}/"):
            candidate = (repo_root / ref).resolve()
        elif "/" in ref:
            candidate = (source_file.parent / ref).resolve()
        else:
            candidate = (source_file.parent / ref).resolve()
        return candidate

    candidate = (source_file.parent / f"{ref}.md").resolve()
    return candidate


def _rel_adr(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _validate_adr_reference(
    source_file: Path,
    line_no: int,
    label: str,
    raw_value: str,
    repo_root: Path,
) -> tuple[Path | None, list[Finding]]:
    repo_root = repo_root.resolve()
    adr_root = (repo_root / ADR_DIR).resolve()
    ref = _extract_adr_ref(raw_value)
    if ref is None:
        return None, [
            Finding(
                file=source_file,
                line=line_no,
                severity="ERROR",
                message=f"ADR '{label}' must point to an ADR markdown path/id or be `N/A`",
            )
        ]

    target = _resolve_adr_ref(source_file, ref, repo_root)
    findings: list[Finding] = []
    if not is_within_root(target, adr_root):
        findings.append(
            Finding(
                file=source_file,
                line=line_no,
                severity="ERROR",
                message=f"ADR '{label}' must stay inside {ADR_DIR}: {ref}",
            )
        )
        return None, findings

    if target.name in ADR_RUNTIME_EXCLUDES:
        findings.append(
            Finding(
                file=source_file,
                line=line_no,
                severity="ERROR",
                message=f"ADR '{label}' cannot point to template/canon helper file: {ref}",
            )
        )
        return None, findings

    if not target.exists():
        findings.append(
            Finding(
                file=source_file,
                line=line_no,
                severity="ERROR",
                message=f"ADR '{label}' points to missing ADR file: {ref}",
            )
        )
        return None, findings

    return target, findings


def lint_reviewability_preflight_receipt_bundle(repo_root: Path | None = None) -> list[Finding]:
    repo_root = REPO_ROOT if repo_root is None else repo_root.resolve()
    findings: list[Finding] = []
    file_texts: dict[str, str] = {}

    for rel_path in REVIEWABILITY_RECEIPT_BUNDLE:
        abs_path = (repo_root / rel_path).resolve()
        if not abs_path.exists():
            findings.append(
                Finding(
                    file=abs_path,
                    line=1,
                    severity="ERROR",
                    message=f"Missing required reviewability bundle file: {rel_path}",
                )
            )
            continue
        file_texts[rel_path] = abs_path.read_text(encoding="utf-8")

    for anchor, required_files in REVIEWABILITY_RECEIPT_ANCHOR_REQUIREMENTS:
        for rel_path in sorted(required_files):
            if rel_path not in file_texts:
                continue
            if anchor in file_texts[rel_path]:
                continue
            findings.append(
                Finding(
                    file=(repo_root / rel_path).resolve(),
                    line=1,
                    severity="ERROR",
                    message=f"Missing required reviewability anchor '{anchor}'",
                )
            )

    return findings


def lint_receipt_schema_emitter_inventory_bundle(repo_root: Path | None = None) -> list[Finding]:
    repo_root = REPO_ROOT if repo_root is None else repo_root.resolve()
    findings: list[Finding] = []

    for rel_path in RECEIPT_SCHEMA_EMITTER_INVENTORY_BUNDLE:
        abs_path = (repo_root / rel_path).resolve()
        if not abs_path.exists():
            findings.append(
                Finding(
                    file=abs_path,
                    line=1,
                    severity="ERROR",
                    message=f"Missing required receipt schema emitter inventory bundle file: {rel_path}",
                )
            )
            continue

        text = abs_path.read_text(encoding="utf-8")
        for anchor in RECEIPT_SCHEMA_EMITTER_INVENTORY_ANCHORS:
            if anchor in text:
                continue
            findings.append(
                Finding(
                    file=abs_path,
                    line=1,
                    severity="ERROR",
                    message=f"Missing required receipt schema emitter inventory anchor '{anchor}'",
                )
            )

    return findings


def lint_reviewer_manager_deadlock_bundle(repo_root: Path | None = None) -> list[Finding]:
    repo_root = REPO_ROOT if repo_root is None else repo_root.resolve()
    findings: list[Finding] = []
    file_texts: dict[str, str] = {}

    for rel_path in REVIEWER_MANAGER_DEADLOCK_BUNDLE:
        abs_path = (repo_root / rel_path).resolve()
        if not abs_path.exists():
            findings.append(
                Finding(
                    file=abs_path,
                    line=1,
                    severity="ERROR",
                    message=f"Missing required reviewer/manager deadlock bundle file: {rel_path}",
                )
            )
            continue
        file_texts[rel_path] = abs_path.read_text(encoding="utf-8")

    for rel_path, anchors in REVIEWER_MANAGER_DEADLOCK_FILE_ANCHORS:
        if rel_path not in file_texts:
            continue
        text = file_texts[rel_path]
        for anchor in anchors:
            if anchor in text:
                continue
            findings.append(
                Finding(
                    file=(repo_root / rel_path).resolve(),
                    line=1,
                    severity="ERROR",
                    message=f"Missing required reviewer/manager deadlock anchor '{anchor}'",
                )
            )

    return findings


def lint_descoped_debt_guard_bundle(repo_root: Path | None = None) -> list[Finding]:
    repo_root = REPO_ROOT if repo_root is None else repo_root.resolve()
    findings: list[Finding] = []

    for rel_path, anchors in DE_SCOPED_SHARED_GUARD_REQUIREMENTS:
        abs_path = (repo_root / rel_path).resolve()
        if not abs_path.exists():
            findings.append(
                Finding(
                    file=abs_path,
                    line=1,
                    severity="ERROR",
                    message=f"Missing required de-scoped debt guard bundle file: {rel_path}",
                )
            )
            continue

        text = abs_path.read_text(encoding="utf-8").lower()
        for anchor in anchors:
            if anchor in text:
                continue
            findings.append(
                Finding(
                    file=abs_path,
                    line=1,
                    severity="ERROR",
                    message=f"Missing required de-scoped debt guard anchor '{anchor}'",
                )
            )

    return findings


def lint_adr_bundle(repo_root: Path | None = None) -> list[Finding]:
    repo_root = REPO_ROOT if repo_root is None else repo_root.resolve()
    adr_root = (repo_root / ADR_DIR).resolve()
    findings: list[Finding] = []

    readme_path = (repo_root / ADR_BUNDLE_FILES[0]).resolve()
    template_path = (repo_root / ADR_BUNDLE_FILES[1]).resolve()

    for required_path in (readme_path, template_path):
        if required_path.exists():
            continue
        findings.append(
            Finding(
                file=required_path,
                line=1,
                severity="ERROR",
                message=f"Missing required ADR bundle file: {_rel_adr(required_path, repo_root)}",
            )
        )
    if findings:
        return findings

    readme_text = readme_path.read_text(encoding="utf-8")
    readme_lower = readme_text.lower()
    for status in sorted(ADR_ALLOWED_STATUSES):
        token = f"`{status}`"
        if token in readme_text:
            continue
        findings.append(
            Finding(
                file=readme_path,
                line=1,
                severity="ERROR",
                message=f"ADR README must document live status `{status}`",
            )
        )
    if "`deprecated`" in readme_text:
        findings.append(
            Finding(
                file=readme_path,
                line=_first_line_with_substring(readme_text, "`deprecated`"),
                severity="ERROR",
                message="ADR README must not advertise legacy status `deprecated` as a live forward token",
            )
        )
    if "superseded by <adr>" in readme_lower:
        findings.append(
            Finding(
                file=readme_path,
                line=_first_line_with_substring(readme_text, "superseded by <ADR>"),
                severity="ERROR",
                message="ADR README must not advertise `superseded by <ADR>` as a live status token",
            )
        )
    if "`code_anchor`" in readme_text:
        findings.append(
            Finding(
                file=readme_path,
                line=_first_line_with_substring(readme_text, "`code_anchor`"),
                severity="ERROR",
                message="ADR README must use canonical frontmatter key `code-anchor`, not `code_anchor`",
            )
        )
    if "`code-anchor`" not in readme_text:
        findings.append(
            Finding(
                file=readme_path,
                line=1,
                severity="ERROR",
                message="ADR README must document canonical frontmatter key `code-anchor`",
            )
        )
    if "`NNN-topic.md`" not in readme_text:
        findings.append(
            Finding(
                file=readme_path,
                line=1,
                severity="ERROR",
                message="ADR README must document the shared/package naming rule `NNN-topic.md`",
            )
        )
    if "`YYYYMMDD-short-title.md`" in readme_text:
        findings.append(
            Finding(
                file=readme_path,
                line=_first_line_with_substring(readme_text, "`YYYYMMDD-short-title.md`"),
                severity="ERROR",
                message="ADR README must not advertise legacy dated naming as the live shared/package rule",
            )
        )
    if ADR_SUPERSESSION_SECTION not in readme_lower:
        findings.append(
            Finding(
                file=readme_path,
                line=1,
                severity="ERROR",
                message="ADR README must document section `Superseded by / Supersedes`",
            )
        )
    for heading in ("`Canonical refs`", "`Revisit signals`"):
        if heading in readme_text:
            continue
        findings.append(
            Finding(
                file=readme_path,
                line=1,
                severity="ERROR",
                message=f"ADR README must document section {heading}",
            )
        )

    template_frontmatter, template_lines = _parse_simple_frontmatter(template_path)
    if not template_frontmatter:
        findings.append(
            Finding(
                file=template_path,
                line=1,
                severity="ERROR",
                message="ADR template must start with frontmatter",
            )
        )
    else:
        if "code_anchor" in template_frontmatter:
            findings.append(
                Finding(
                    file=template_path,
                    line=template_lines.get("code_anchor", 1),
                    severity="ERROR",
                    message="ADR template must use canonical frontmatter key `code-anchor`, not `code_anchor`",
                )
            )
        if template_frontmatter.get("status") != "proposed":
            findings.append(
                Finding(
                    file=template_path,
                    line=template_lines.get("status", 1),
                    severity="ERROR",
                    message='ADR template must keep `status: "proposed"`',
                )
            )
        if "code-anchor" not in template_frontmatter:
            findings.append(
                Finding(
                    file=template_path,
                    line=1,
                    severity="ERROR",
                    message="ADR template must expose frontmatter key `code-anchor`",
                )
            )

    template_section = _extract_section_lines(template_path, ADR_SUPERSESSION_SECTION)
    for label in (ADR_SUPERSEDES_LABEL, ADR_SUPERSEDED_BY_LABEL):
        if label in template_section:
            continue
        findings.append(
            Finding(
                file=template_path,
                line=1,
                severity="ERROR",
                message=f"ADR template must define section bullet `{label}`",
            )
        )
    for section_title in ADR_REQUIRED_SECTION_TITLES:
        if _find_h2_section_line(template_path, section_title) is not None:
            continue
        findings.append(
            Finding(
                file=template_path,
                line=1,
                severity="ERROR",
                message=f"ADR template must define section `## {section_title.title()}`",
            )
        )

    adr_files = sorted(
        candidate
        for candidate in adr_root.glob("*.md")
        if candidate.name not in ADR_RUNTIME_EXCLUDES
    )
    frontmatter_cache: dict[Path, tuple[dict[str, str], dict[str, int]]] = {}
    section_cache: dict[Path, dict[str, tuple[str, int]]] = {}

    for adr_file in adr_files:
        if not ADR_RUNTIME_NAME_RE.fullmatch(adr_file.name):
            findings.append(
                Finding(
                    file=adr_file,
                    line=1,
                    severity="ERROR",
                    message="ADR filename must follow shared/package naming `NNN-topic.md`",
                )
            )
        frontmatter, line_numbers = _parse_simple_frontmatter(adr_file)
        if not frontmatter:
            findings.append(
                Finding(
                    file=adr_file,
                    line=1,
                    severity="ERROR",
                    message="ADR file must start with frontmatter",
                )
            )
            continue
        frontmatter_cache[adr_file] = (frontmatter, line_numbers)

        for key in ADR_REQUIRED_FRONTMATTER_KEYS:
            value = frontmatter.get(key, "")
            if key in frontmatter and value.strip():
                continue
            findings.append(
                Finding(
                    file=adr_file,
                    line=line_numbers.get(key, 1),
                    severity="ERROR",
                    message=f"ADR file is missing required frontmatter key `{key}`",
                )
            )

        if "code_anchor" in frontmatter:
            findings.append(
                Finding(
                    file=adr_file,
                    line=line_numbers.get("code_anchor", 1),
                    severity="ERROR",
                    message="ADR file must use canonical frontmatter key `code-anchor`, not `code_anchor`",
                )
            )

        status = frontmatter.get("status", "").strip().lower()
        if status not in ADR_ALLOWED_STATUSES:
            findings.append(
                Finding(
                    file=adr_file,
                    line=line_numbers.get("status", 1),
                    severity="ERROR",
                    message=(
                        "ADR status must be one of "
                        "`proposed|accepted|superseded`; "
                        f"got `{frontmatter.get('status', '').strip() or 'missing'}`"
                    ),
                )
            )

        code_anchor = frontmatter.get("code-anchor", "")
        if status == "accepted" and _is_na_like(code_anchor):
            findings.append(
                Finding(
                    file=adr_file,
                    line=line_numbers.get("code-anchor", 1),
                    severity="ERROR",
                    message="`accepted` ADR must carry a non-empty `code-anchor`",
                )
            )

        section_values = _extract_section_lines(adr_file, ADR_SUPERSESSION_SECTION)
        section_cache[adr_file] = section_values
        for label in (ADR_SUPERSEDES_LABEL, ADR_SUPERSEDED_BY_LABEL):
            if label in section_values:
                continue
            findings.append(
                Finding(
                    file=adr_file,
                    line=1,
                    severity="ERROR",
                    message=f"ADR file must define section bullet `{label}` inside `## Superseded by / Supersedes`",
                )
            )
        for section_title in ADR_REQUIRED_SECTION_TITLES:
            if _find_h2_section_line(adr_file, section_title) is not None:
                continue
            findings.append(
                Finding(
                    file=adr_file,
                    line=1,
                    severity="ERROR",
                    message=f"ADR file must define section `## {section_title.title()}`",
                )
            )

        superseded_by_value, superseded_by_line = section_values.get(ADR_SUPERSEDED_BY_LABEL, ("", 1))
        if status == "superseded" and _is_na_like(superseded_by_value):
            findings.append(
                Finding(
                    file=adr_file,
                    line=superseded_by_line,
                    severity="ERROR",
                    message="`status: superseded` requires a non-`N/A` `Superseded by` ADR pointer",
                )
            )

    for adr_file, section_values in section_cache.items():
        for label, reciprocal_label in (
            (ADR_SUPERSEDES_LABEL, ADR_SUPERSEDED_BY_LABEL),
            (ADR_SUPERSEDED_BY_LABEL, ADR_SUPERSEDES_LABEL),
        ):
            raw_value, line_no = section_values.get(label, ("", 1))
            if _is_na_like(raw_value):
                continue
            target, ref_findings = _validate_adr_reference(adr_file, line_no, label, raw_value, repo_root)
            findings.extend(ref_findings)
            if target is None:
                continue
            reciprocal_values = section_cache.get(target)
            if reciprocal_values is None:
                reciprocal_values = _extract_section_lines(target, ADR_SUPERSESSION_SECTION)
                section_cache[target] = reciprocal_values
            reciprocal_raw_value, reciprocal_line = reciprocal_values.get(reciprocal_label, ("", 1))
            if _is_na_like(reciprocal_raw_value):
                findings.append(
                    Finding(
                        file=target,
                        line=reciprocal_line,
                        severity="ERROR",
                        message=(
                            f"ADR reciprocity drift: `{_rel_adr(target, repo_root)}` must point back to "
                            f"`{_rel_adr(adr_file, repo_root)}` via `{reciprocal_label}`"
                        ),
                    )
                )
                continue
            reciprocal_target, reciprocal_findings = _validate_adr_reference(
                target,
                reciprocal_line,
                reciprocal_label,
                reciprocal_raw_value,
                repo_root,
            )
            findings.extend(reciprocal_findings)
            if reciprocal_target is None:
                continue
            if reciprocal_target.resolve() == adr_file.resolve():
                continue
            findings.append(
                Finding(
                    file=target,
                    line=reciprocal_line,
                    severity="ERROR",
                    message=(
                        f"ADR reciprocity drift: `{_rel_adr(target, repo_root)}` points to "
                        f"`{_rel_adr(reciprocal_target, repo_root)}` instead of `{_rel_adr(adr_file, repo_root)}`"
                    ),
                )
            )

    return findings


def rel_to(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def is_within_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def repo_root_candidates(*, product_root: Path | None = None) -> tuple[Path, ...]:
    ordered: list[Path] = []
    for candidate in (product_root if product_root is not None else PRODUCT_REPO_ROOT, REPO_ROOT):
        if candidate is None:
            continue
        candidate = candidate.resolve()
        if candidate not in ordered:
            ordered.append(candidate)
    return tuple(ordered)


def infer_repo_root_for_path(
    path: Path,
    default_root: Path | None = None,
    *,
    product_root: Path | None = None,
) -> Path:
    path = path.resolve()
    matches = [root for root in repo_root_candidates(product_root=product_root) if is_within_root(path, root)]
    if matches:
        return max(matches, key=lambda root: len(root.parts))
    if default_root is not None:
        return default_root.resolve()
    return REPO_ROOT


def infer_selected_repo_root(
    roots: Sequence[Path],
    default_root: Path | None = None,
    *,
    product_root: Path | None = None,
) -> Path:
    best_match: tuple[int, int, Path] | None = None
    for candidate in repo_root_candidates(product_root=product_root):
        score = sum(1 for root in roots if is_within_root(root.resolve(), candidate))
        if score <= 0:
            continue
        ranked = (score, len(candidate.parts), candidate)
        if best_match is None or ranked > best_match:
            best_match = ranked
    if best_match is not None:
        return best_match[2]
    if default_root is not None:
        return default_root.resolve()
    return REPO_ROOT


def is_harvest_followup_semantic_file(
    markdown_file: Path,
    repo_root: Path | None = None,
    *,
    product_root: Path | None = None,
) -> bool:
    repo_root = infer_repo_root_for_path(markdown_file, repo_root, product_root=product_root)
    rel_path = rel_to(markdown_file, repo_root)
    name = markdown_file.name
    return (
        rel_path.startswith(HARVEST_REPORT_DIR)
        and (HARVEST_REPORT_NAME_TOKEN in name or HARVEST_AUDIT_NAME_TOKEN in name)
    ) or (
        rel_path.startswith(HARVEST_BACKLOG_DIR)
        and HARVEST_BACKLOG_NAME_TOKEN in name
    )


def extract_markdown_doc_refs(text: str) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for match in MARKDOWN_DOC_REF_RE.finditer(text):
        ref = match.group("ref").strip("`'\"()[]{}<>.,;:")
        if not ref or ref in seen:
            continue
        seen.add(ref)
        refs.append(ref)
    return refs


def resolve_markdown_doc_ref(ref: str, repo_root: Path) -> Path | None:
    repo_root = repo_root.resolve()
    candidates: list[Path] = []
    if "/" in ref:
        candidates.append((repo_root / ref).resolve())
    else:
        candidates.extend(
            [
                (repo_root / "docs" / "followups" / ref).resolve(),
                (repo_root / "docs" / "plans" / ref).resolve(),
                (repo_root / "docs" / "reviews" / ref).resolve(),
                (repo_root / "docs" / "code_reviews" / ref).resolve(),
                (repo_root / "docs" / "doc_reviews" / ref).resolve(),
                (repo_root / "docs" / ref).resolve(),
                (repo_root / ref).resolve(),
            ]
        )

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _read_title_line(markdown_file: Path) -> str:
    for line in markdown_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _normalize_heading_text(text: str) -> str:
    cleaned = text.strip().strip("`").strip()
    return " ".join(cleaned.lower().split())


def _extract_descoped_markers(text: str) -> tuple[str, ...]:
    markers: list[str] = []
    for match in INLINE_CODE_SPAN_RE.finditer(text):
        token = " ".join(match.group(1).strip().lower().split())
        if len(token) >= 4 and token not in markers:
            markers.append(token)
    return tuple(markers)


def _extract_descoped_keywords(text: str) -> tuple[str, ...]:
    keywords: list[str] = []
    for raw_token in WORD_TOKEN_RE.findall(text.lower()):
        token = raw_token.strip("-_")
        if len(token) < 4 or token in DE_SCOPED_STOPWORDS:
            continue
        if token not in keywords:
            keywords.append(token)
        if len(keywords) >= 6:
            break
    return tuple(keywords)


def extract_descoped_debt_items(plan_file: Path) -> list[DeScopedDebtItem]:
    items: list[DeScopedDebtItem] = []
    in_target_section = False

    for line_no, line in enumerate(plan_file.read_text(encoding="utf-8").splitlines(), start=1):
        heading_match = HEADING_RE.match(line)
        if heading_match and len(heading_match.group("level")) == 2:
            in_target_section = _normalize_heading_text(heading_match.group("text")) in DE_SCOPED_PLAN_SECTION_TITLES
            continue
        if not in_target_section:
            continue

        line_lower = line.lower()
        if not any(phrase in line_lower for phrase in DE_SCOPED_DEBT_TRIGGER_PHRASES):
            continue

        text = line.strip()
        items.append(
            DeScopedDebtItem(
                source_plan=plan_file.resolve(),
                line=line_no,
                text=text,
                markers=_extract_descoped_markers(text),
                keywords=_extract_descoped_keywords(text),
            )
        )

    return items


def _line_mentions_descoped_item(line_lower: str, item: DeScopedDebtItem) -> bool:
    if any(marker in line_lower for marker in item.markers):
        return True
    if not item.keywords:
        return False
    matches = sum(1 for keyword in item.keywords if keyword in line_lower)
    threshold = 1 if len(item.keywords) == 1 else 2
    return matches >= threshold


def _collect_related_semantic_files(markdown_file: Path, repo_root: Path) -> list[Path]:
    queue = [markdown_file.resolve()]
    seen = {markdown_file.resolve()}
    related: list[Path] = []

    while queue:
        current = queue.pop(0)
        related.append(current)
        text = current.read_text(encoding="utf-8")
        for ref in extract_markdown_doc_refs(text):
            resolved = resolve_markdown_doc_ref(ref, repo_root)
            if resolved is None or resolved in seen:
                continue
            if not is_harvest_followup_semantic_file(resolved, repo_root):
                continue
            seen.add(resolved)
            queue.append(resolved)

    return related


def _is_review_artifact(path: Path, repo_root: Path) -> bool:
    rel_path = rel_to(path, repo_root)
    return rel_path.startswith("docs/reviews/") or rel_path.startswith("docs/code_reviews/") or rel_path.startswith("docs/doc_reviews/")


def _is_sources_heading(text: str) -> bool:
    return _normalize_heading_text(text).startswith("источники")


def _is_plans_list_header(line: str) -> bool:
    stripped = line.strip().lower()
    return stripped.startswith("- plans")


def _collect_source_plan_refs(bundle_files: Sequence[Path], repo_root: Path) -> list[Path]:
    plan_refs: dict[Path, None] = {}
    for markdown_file in bundle_files:
        if not _is_review_artifact(markdown_file, repo_root):
            continue

        in_sources_section = False
        plans_list_active = False
        text = markdown_file.read_text(encoding="utf-8")
        for line in text.splitlines():
            heading_match = HEADING_RE.match(line)
            if heading_match and len(heading_match.group("level")) == 2:
                in_sources_section = _is_sources_heading(heading_match.group("text"))
                plans_list_active = False
                continue
            if not in_sources_section:
                continue

            if line.startswith("#"):
                plans_list_active = False
                continue

            if _is_plans_list_header(line):
                plans_list_active = True
                continue

            if not line.startswith("  - ") or not plans_list_active:
                continue

            for ref in extract_markdown_doc_refs(line):
                resolved = resolve_markdown_doc_ref(ref, repo_root)
                if resolved is None:
                    continue
                rel_path = rel_to(resolved, repo_root)
                if rel_path.startswith("docs/plans/"):
                    plan_refs[resolved.resolve()] = None
    return sorted(plan_refs)


def _descoped_item_has_materialized_outcome(
    item: DeScopedDebtItem,
    bundle_files: Sequence[Path],
    repo_root: Path,
    title_cache: dict[Path, str],
) -> bool:
    for markdown_file in bundle_files:
        for raw_line in markdown_file.read_text(encoding="utf-8").splitlines():
            line_lower = raw_line.lower()
            if not _line_mentions_descoped_item(line_lower, item):
                continue

            refs = extract_markdown_doc_refs(raw_line)
            ref_kinds = [classify_harvest_doc_ref(ref, repo_root, title_cache) for ref in refs]
            has_durable_ref = any(kind in {"durable_backlog", "promoted_plan"} for kind in ref_kinds)
            has_canon_closure = any(phrase in line_lower for phrase in HARVEST_CANON_CLOSURE_PHRASES) and any(
                kind == "canon_doc" for kind in ref_kinds
            )
            has_owner_rejection = any(phrase in line_lower for phrase in HARVEST_OWNER_REJECTION_PHRASES)
            has_explicit_loss = any(phrase in line_lower for phrase in DE_SCOPED_LOST_FOLLOWUP_PHRASES)
            if has_durable_ref or has_canon_closure or has_owner_rejection or has_explicit_loss:
                return True

    return False


def classify_harvest_doc_ref(ref: str, repo_root: Path, title_cache: dict[Path, str]) -> str:
    resolved = resolve_markdown_doc_ref(ref, repo_root)
    if resolved is None:
        return "missing"

    rel_path = rel_to(resolved, repo_root)
    if rel_path.startswith("docs/followups/"):
        title = title_cache.get(resolved)
        if title is None:
            title = _read_title_line(resolved).lower()
            title_cache[resolved] = title
        if HARVEST_MEMORY_DUMP_TITLE in title:
            return "memory_dump"
        return "durable_backlog"
    if rel_path.startswith("docs/plans/"):
        return "promoted_plan"
    if rel_path.startswith("docs/reviews/") or rel_path.startswith("docs/code_reviews/") or rel_path.startswith("docs/doc_reviews/"):
        return "review_artifact"
    if rel_path.startswith("docs/"):
        return "canon_doc"
    return "other"


def lint_harvest_durable_followup_carriers(
    markdown_files: Sequence[Path],
    repo_root: Path | None = None,
    *,
    product_root: Path | None = None,
) -> list[Finding]:
    repo_root = None if repo_root is None else repo_root.resolve()
    findings: list[Finding] = []
    title_cache: dict[Path, str] = {}

    for markdown_file in markdown_files:
        file_repo_root = infer_repo_root_for_path(markdown_file, repo_root, product_root=product_root)
        if not is_harvest_followup_semantic_file(
            markdown_file,
            file_repo_root,
            product_root=product_root,
        ):
            continue

        related_bundle = _collect_related_semantic_files(markdown_file, file_repo_root)
        source_plans = _collect_source_plan_refs(related_bundle, file_repo_root)
        for source_plan in source_plans:
            for item in extract_descoped_debt_items(source_plan):
                if _descoped_item_has_materialized_outcome(item, related_bundle, file_repo_root, title_cache):
                    continue
                bundle_summary = ", ".join(rel_to(path, file_repo_root) for path in related_bundle)
                findings.append(
                    Finding(
                        file=markdown_file,
                        line=1,
                        severity="ERROR",
                        message=(
                            "De-scoped actionable debt is not materialized in harvest/audit/followups bundle: "
                            f"{rel_to(source_plan, file_repo_root)}:{item.line} -> {item.text} "
                            f"(bundle: {bundle_summary})"
                        ),
                    )
                )

        lines = markdown_file.read_text(encoding="utf-8").splitlines()
        for line_no, raw_line in enumerate(lines, start=1):
            line_lower = raw_line.lower()
            is_no_followups_line = HARVEST_NO_FOLLOWUPS_PHRASE in line_lower
            is_handled_line = any(phrase in line_lower for phrase in HARVEST_HANDLED_PHRASES)
            if not is_no_followups_line and not is_handled_line:
                continue

            refs = extract_markdown_doc_refs(raw_line)
            ref_kinds = [classify_harvest_doc_ref(ref, file_repo_root, title_cache) for ref in refs]
            has_memory_dump_ref = any(kind == "memory_dump" for kind in ref_kinds) or HARVEST_MEMORY_DUMP_TITLE in line_lower
            if not has_memory_dump_ref:
                continue

            has_durable_ref = any(kind in {"durable_backlog", "promoted_plan"} for kind in ref_kinds)
            has_canon_closure = any(phrase in line_lower for phrase in HARVEST_CANON_CLOSURE_PHRASES) and any(
                kind == "canon_doc" for kind in ref_kinds
            )
            has_owner_rejection = any(phrase in line_lower for phrase in HARVEST_OWNER_REJECTION_PHRASES)
            if has_durable_ref or has_canon_closure or has_owner_rejection:
                continue

            refs_summary = ", ".join(refs) if refs else "memory dump"
            message = (
                "NO FOLLOWUPS cannot rely only on memory-dump carriers"
                if is_no_followups_line
                else "Handled-state cannot rely only on memory-dump carriers"
            )
            findings.append(
                Finding(
                    file=markdown_file,
                    line=line_no,
                    severity="ERROR",
                    message=f"{message}: {refs_summary}",
                )
            )

    return findings


def _target_is_selected_by_scope(
    target: Path,
    roots: Sequence[Path],
    exclude_dirs: Sequence[Path],
    exclude_files: Sequence[Path],
    *,
    allow_default_excluded_explicit_files: Sequence[Path] = (),
) -> bool:
    exclude_dir_set = {path.resolve() for path in exclude_dirs}
    exclude_file_set = {path.resolve() for path in exclude_files}
    allow_default_excluded_explicit_file_set = {
        path.resolve() for path in allow_default_excluded_explicit_files
    }
    target = target.resolve()

    if target in exclude_file_set:
        return False
    if (
        target not in allow_default_excluded_explicit_file_set
        and any(exclude == target or exclude in target.parents for exclude in exclude_dir_set)
    ):
        return False

    for root in roots:
        root = root.resolve()
        if root.is_dir():
            if root == target or root in target.parents:
                return True
            continue
        if root == target:
            return True
    return False


def scope_covers_reviewability_preflight_receipt_bundle(
    roots: Sequence[Path],
    exclude_dirs: Sequence[Path],
    exclude_files: Sequence[Path],
    repo_root: Path | None = None,
    *,
    allow_default_excluded_explicit_files: Sequence[Path] = (),
) -> bool:
    repo_root = REPO_ROOT if repo_root is None else repo_root.resolve()
    return all(
        _target_is_selected_by_scope(
            (repo_root / rel_path).resolve(),
            roots,
            exclude_dirs,
            exclude_files,
            allow_default_excluded_explicit_files=allow_default_excluded_explicit_files,
        )
        for rel_path in REVIEWABILITY_RECEIPT_BUNDLE
    )


def scope_covers_receipt_schema_emitter_inventory_bundle(
    roots: Sequence[Path],
    exclude_dirs: Sequence[Path],
    exclude_files: Sequence[Path],
    repo_root: Path | None = None,
    *,
    allow_default_excluded_explicit_files: Sequence[Path] = (),
) -> bool:
    repo_root = REPO_ROOT if repo_root is None else repo_root.resolve()
    return all(
        _target_is_selected_by_scope(
            (repo_root / rel_path).resolve(),
            roots,
            exclude_dirs,
            exclude_files,
            allow_default_excluded_explicit_files=allow_default_excluded_explicit_files,
        )
        for rel_path in RECEIPT_SCHEMA_EMITTER_INVENTORY_BUNDLE
    )


def scope_covers_reviewer_manager_deadlock_bundle(
    roots: Sequence[Path],
    exclude_dirs: Sequence[Path],
    exclude_files: Sequence[Path],
    repo_root: Path | None = None,
    *,
    allow_default_excluded_explicit_files: Sequence[Path] = (),
) -> bool:
    repo_root = REPO_ROOT if repo_root is None else repo_root.resolve()
    return all(
        _target_is_selected_by_scope(
            (repo_root / rel_path).resolve(),
            roots,
            exclude_dirs,
            exclude_files,
            allow_default_excluded_explicit_files=allow_default_excluded_explicit_files,
        )
        for rel_path in REVIEWER_MANAGER_DEADLOCK_BUNDLE
    )


def scope_covers_descoped_debt_guard_bundle(
    roots: Sequence[Path],
    exclude_dirs: Sequence[Path],
    exclude_files: Sequence[Path],
    repo_root: Path | None = None,
    *,
    allow_default_excluded_explicit_files: Sequence[Path] = (),
) -> bool:
    repo_root = REPO_ROOT if repo_root is None else repo_root.resolve()
    return all(
        _target_is_selected_by_scope(
            (repo_root / rel_path).resolve(),
            roots,
            exclude_dirs,
            exclude_files,
            allow_default_excluded_explicit_files=allow_default_excluded_explicit_files,
        )
        for rel_path in DE_SCOPED_SHARED_GUARD_BUNDLE
    )


def scope_covers_adr_bundle(
    roots: Sequence[Path],
    exclude_dirs: Sequence[Path],
    exclude_files: Sequence[Path],
    repo_root: Path | None = None,
    *,
    allow_default_excluded_explicit_files: Sequence[Path] = (),
) -> bool:
    repo_root = REPO_ROOT if repo_root is None else repo_root.resolve()
    adr_root = (repo_root / ADR_DIR).resolve()
    return _target_is_selected_by_scope(
        adr_root,
        roots,
        exclude_dirs,
        exclude_files,
        allow_default_excluded_explicit_files=allow_default_excluded_explicit_files,
    ) and all(
        _target_is_selected_by_scope(
            (repo_root / rel_path).resolve(),
            roots,
            exclude_dirs,
            exclude_files,
            allow_default_excluded_explicit_files=allow_default_excluded_explicit_files,
        )
        for rel_path in ADR_BUNDLE_FILES
    )


def iter_markdown_files(
    roots: Sequence[Path],
    exclude_dirs: Sequence[Path],
    exclude_files: Sequence[Path],
    *,
    allow_default_excluded_explicit_files: Sequence[Path] = (),
) -> list[Path]:
    exclude_dir_set = {path.resolve() for path in exclude_dirs}
    exclude_file_set = {path.resolve() for path in exclude_files}
    allow_default_excluded_explicit_file_set = {
        path.resolve() for path in allow_default_excluded_explicit_files
    }

    files: set[Path] = set()
    for root in roots:
        root = root.resolve()
        candidates: Iterable[Path]
        if root.is_file():
            candidates = (root,)
        else:
            candidates = root.rglob("*.md")

        for candidate in candidates:
            candidate = candidate.resolve()
            if candidate in exclude_file_set:
                continue
            if (
                candidate not in allow_default_excluded_explicit_file_set
                and any(exclude in candidate.parents or candidate == exclude for exclude in exclude_dir_set)
            ):
                continue
            files.add(candidate)
    return sorted(files)


def collect_basic_hygiene_files(
    roots: Sequence[Path],
    exclude_dirs: Sequence[Path],
    exclude_files: Sequence[Path],
) -> tuple[list[Path], list[Finding]]:
    findings: list[Finding] = []
    for root in roots:
        if root.exists():
            continue
        findings.append(
            Finding(
                file=root,
                line=1,
                severity="ERROR",
                message="Missing basic hygiene root",
            )
        )
    return iter_markdown_files(roots, exclude_dirs, exclude_files), findings


def lint_basic_hygiene(markdown_files: Sequence[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for markdown_file in markdown_files:
        try:
            lines = markdown_file.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError as exc:
            findings.append(
                Finding(
                    file=markdown_file,
                    line=1,
                    severity="ERROR",
                    message=f"Cannot read markdown as UTF-8: {exc}",
                )
            )
            continue
        for line_no, raw_line in enumerate(lines, start=1):
            if TRAILING_WHITESPACE_RE.search(raw_line):
                findings.append(
                    Finding(
                        file=markdown_file,
                        line=line_no,
                        severity="ERROR",
                        message="Trailing whitespace",
                    )
                )
            if RAW_MERGE_MARKER_RE.match(raw_line):
                findings.append(
                    Finding(
                        file=markdown_file,
                        line=line_no,
                        severity="ERROR",
                        message="Raw merge marker",
                    )
                )
    return findings


def _run_generated_check(
    repo_root: Path,
    script_name: str,
    extra_args: Sequence[str],
) -> tuple[int, dict[str, Any] | None, str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    command = [
        sys.executable,
        "-B",
        str(repo_root / "scripts" / script_name),
        "--project-root",
        str(repo_root),
        *extra_args,
        "--json",
    ]
    completed = subprocess.run(
        command,
        cwd=repo_root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    stdout = completed.stdout.strip()
    if not stdout:
        return completed.returncode, None, completed.stderr.strip()
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return completed.returncode, None, f"Invalid JSON output: {exc}; stderr={completed.stderr.strip()}"
    if not isinstance(payload, dict):
        return completed.returncode, None, f"Unexpected JSON output type: {type(payload).__name__}"
    return completed.returncode, payload, completed.stderr.strip()


def _issue_summary(raw_issues: Any) -> str:
    if isinstance(raw_issues, list):
        return ",".join(str(issue) for issue in raw_issues) or "unknown"
    if raw_issues is None:
        return "unknown"
    return str(raw_issues) or "unknown"


def lint_generated_surface_freshness(repo_root: Path | None = None) -> list[Finding]:
    root = repo_root or REPO_ROOT
    findings: list[Finding] = []

    followups_code, followups_payload, followups_stderr = _run_generated_check(
        root,
        "followups_index_rebuild.py",
        ["--check"],
    )
    if followups_payload is None:
        findings.append(
            Finding(
                file=root / "docs" / "followups" / "index.md",
                line=1,
                severity="ERROR",
                message=(
                    "Generated followups summary check failed: helper returned "
                    f"no parseable JSON (exit={followups_code}; stderr={followups_stderr or 'none'})."
                ),
            )
        )
    else:
        if followups_code != 0 or not bool(followups_payload.get("ok")):
            issues = _issue_summary(followups_payload.get("issues"))
            rel_path = str(followups_payload.get("index_path") or "docs/followups/index.md")
            findings.append(
                Finding(
                    file=root / rel_path,
                    line=1,
                    severity="ERROR",
                    message=(
                        "Generated followups summary is stale or malformed "
                        f"(issues={issues}); regenerate via "
                        "PYTHONDONTWRITEBYTECODE=1 python3 -B "
                        "scripts/followups_index_rebuild.py --project-root ."
                    ),
                )
            )

    process_code, process_payload, process_stderr = _run_generated_check(
        root,
        "process_improvements_collect.py",
        ["--check"],
    )
    if process_payload is None:
        findings.append(
            Finding(
                file=root / "docs" / "process_improvements" / "index.md",
                line=1,
                severity="ERROR",
                message=(
                    "Generated process-improvements surface check failed: helper returned "
                    f"no parseable JSON (exit={process_code}; stderr={process_stderr or 'none'})."
                ),
            )
        )
    else:
        surfaces = process_payload.get("surfaces")
        if not isinstance(surfaces, list):
            findings.append(
                Finding(
                    file=root / "docs" / "process_improvements" / "index.md",
                    line=1,
                    severity="ERROR",
                    message="Generated process-improvements surface check failed: missing `surfaces` list.",
                )
            )
        else:
            for raw_surface in surfaces:
                if not isinstance(raw_surface, dict):
                    findings.append(
                        Finding(
                            file=root / "docs" / "process_improvements" / "index.md",
                            line=1,
                            severity="ERROR",
                            message="Generated process-improvements surface check failed: malformed surface item.",
                        )
                    )
                    continue
                if process_code == 0 and bool(raw_surface.get("ok")):
                    continue
                issues = _issue_summary(raw_surface.get("issues"))
                rel_path = str(raw_surface.get("path") or "docs/process_improvements/index.md")
                findings.append(
                    Finding(
                        file=root / rel_path,
                        line=1,
                        severity="ERROR",
                        message=(
                            "Generated process-improvements surface is stale or malformed "
                            f"(issues={issues}); regenerate via "
                            "PYTHONDONTWRITEBYTECODE=1 python3 -B "
                            "scripts/process_improvements_collect.py --project-root . --rebuild-derived"
                        ),
                    )
                )

    return findings


def is_external(target: str) -> bool:
    lower = target.lower()
    return any(lower.startswith(prefix) for prefix in EXTERNAL_SCHEMES)


def is_route(target: str) -> bool:
    return target.startswith("/")


def update_fence_state(line: str, fence: str | None) -> str | None:
    stripped = line.lstrip()
    if fence is None:
        if stripped.startswith("```"):
            return "```"
        if stripped.startswith("~~~"):
            return "~~~"
        return None
    if stripped.startswith(fence):
        return None
    return fence


def parse_link_destination(line: str, open_paren: int) -> tuple[str, int] | None:
    if open_paren >= len(line) or line[open_paren] != "(":
        return None
    i = open_paren + 1
    while i < len(line) and line[i].isspace():
        i += 1
    start = i

    depth = 0
    while i < len(line):
        char = line[i]
        if char == "(":
            depth += 1
        elif char == ")":
            if depth == 0:
                return (line[start:i], i + 1)
            depth -= 1
        i += 1
    return None


def strip_link_title(destination: str) -> str:
    destination = destination.strip()
    if destination.startswith("<") and destination.endswith(">"):
        destination = destination[1:-1].strip()
    if not destination:
        return destination
    return destination.split()[0]


def extract_inline_link_targets(line: str) -> list[str]:
    targets: list[str] = []
    i = 0
    while i < len(line):
        idx = line.find("](", i)
        if idx == -1:
            break

        open_paren = idx + 1
        parsed = parse_link_destination(line, open_paren)
        if not parsed:
            i = open_paren + 1
            continue

        raw, next_i = parsed
        dest = strip_link_title(raw)
        if dest:
            targets.append(dest)
        i = next_i
    return targets


def extract_reference_definition_target(line: str) -> str | None:
    match = REF_DEF_RE.match(line)
    if not match:
        return None
    return strip_link_title(match.group("dest"))


def extract_code_spans(line: str) -> list[str]:
    spans: list[str] = []
    i = 0
    while i < len(line):
        start = line.find("`", i)
        if start == -1:
            break
        end = line.find("`", start + 1)
        if end == -1:
            break
        spans.append(line[start + 1 : end])
        i = end + 1
    return spans


def extract_code_file_refs_with_prefixes(code_span: str, prefixes: Sequence[str]) -> list[str]:
    candidates: set[str] = set()

    for prefix in prefixes:
        pattern = rf"(?<![\w./-]){re.escape(prefix)}[^\s`]+"
        for match in re.finditer(pattern, code_span):
            candidates.add(match.group(0))

    for filename in ROOT_FILENAMES:
        pattern = rf"(?<![\w./-]){re.escape(filename)}(?![\w./-])"
        for match in re.finditer(pattern, code_span):
            candidates.add(match.group(0))

    cleaned: list[str] = []
    for candidate in sorted(candidates):
        candidate = candidate.strip("),;:\"'")
        if not candidate:
            continue
        if any(char in candidate for char in ("*", "{", "}", "<", ">", "|", "…")):
            continue
        if is_external(candidate) or is_route(candidate):
            continue
        cleaned.append(candidate)
    return cleaned


def split_path_and_anchor(target: str) -> tuple[str, str, str | None]:
    if "#" not in target:
        return (target, "", None)
    path, anchor = target.split("#", 1)
    return (path, "#", anchor or None)


def strip_location_suffix(path: str) -> str:
    if ":" not in path:
        return path
    return path.split(":", 1)[0]


def github_slug(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[*_`]", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = text.replace(" ", "-")
    text = re.sub(r"-+", "-", text).strip("-")
    return text


def extract_heading_anchors(markdown_path: Path) -> set[str]:
    anchors: list[str] = []
    fence: str | None = None
    for raw_line in markdown_path.read_text(encoding="utf-8").splitlines():
        fence = update_fence_state(raw_line, fence)
        if fence is not None:
            continue
        match = HEADING_RE.match(raw_line)
        if not match:
            continue
        heading = match.group("text").strip().strip("#").strip()
        if not heading:
            continue
        anchors.append(heading)

    seen: dict[str, int] = {}
    slugs: set[str] = set()
    for heading in anchors:
        base = github_slug(heading)
        if not base:
            continue
        count = seen.get(base, 0)
        seen[base] = count + 1
        slug = base if count == 0 else f"{base}-{count}"
        slugs.add(slug)
    return slugs


def should_check_anchor(anchor: str) -> bool:
    if not anchor:
        return False
    return not ANCHOR_LINE_RE.fullmatch(anchor)


def resolve_markdown_link_path(source_file: Path, link_path: str) -> Path:
    return (source_file.parent / link_path).resolve()


def resolve_code_ref_path(code_path: str) -> Path:
    return (REPO_ROOT / code_path).resolve()


def maybe_resolve_product_repo_path(
    path: Path,
    *,
    product_policy: ProductRootPolicy = GENERIC_PRODUCT_ROOT_POLICY,
    product_root: Path | None = None,
) -> Path:
    if product_root is None:
        return path
    try:
        rel_path = path.relative_to(REPO_ROOT)
    except ValueError:
        return path

    rel_str = rel_path.as_posix()
    if not (
        rel_str.startswith(product_policy.allowed_ref_prefixes)
        or rel_str in product_policy.root_filenames
    ):
        return path
    return (product_root / rel_path).resolve()


def is_placeholder_code_ref(path_part: str) -> bool:
    return path_part in PLACEHOLDER_CODE_REF_PATHS or any(
        token in path_part for token in PLACEHOLDER_CODE_REF_SUBSTRINGS
    )


def lint_file(
    markdown_file: Path,
    code_refs_scope: str | None,
    check_anchors: bool,
    anchor_cache: dict[Path, set[str]],
    *,
    product_policy: ProductRootPolicy = GENERIC_PRODUCT_ROOT_POLICY,
    product_root: Path | None = None,
) -> list[Finding]:
    findings: list[Finding] = []

    fence: str | None = None
    lines = markdown_file.read_text(encoding="utf-8").splitlines()
    for line_no, raw_line in enumerate(lines, start=1):
        fence = update_fence_state(raw_line, fence)
        if fence is not None:
            continue

        link_targets = extract_inline_link_targets(raw_line)
        ref_target = extract_reference_definition_target(raw_line)
        if ref_target:
            link_targets.append(ref_target)

        for target in link_targets:
            target = unquote(target).strip()
            if not target or is_external(target) or is_route(target):
                continue

            path_part, _hash, anchor = split_path_and_anchor(target)
            if not path_part:
                if check_anchors and anchor and should_check_anchor(anchor):
                    anchors = anchor_cache.get(markdown_file)
                    if anchors is None:
                        anchors = extract_heading_anchors(markdown_file)
                        anchor_cache[markdown_file] = anchors
                    if anchor not in anchors:
                        findings.append(
                            Finding(
                                file=markdown_file,
                                line=line_no,
                                severity="ERROR",
                                message=f"Broken anchor '#{anchor}'",
                            )
                        )
                continue

            resolved = resolve_markdown_link_path(markdown_file, path_part)
            if not resolved.exists():
                resolved = maybe_resolve_product_repo_path(
                    resolved,
                    product_policy=product_policy,
                    product_root=product_root,
                )
            if not resolved.exists():
                findings.append(
                    Finding(
                        file=markdown_file,
                        line=line_no,
                        severity="ERROR",
                        message=f"Broken link target: {path_part} (resolved: {rel(resolved)})",
                    )
                )
                continue

            if (
                check_anchors
                and anchor
                and should_check_anchor(anchor)
                and resolved.suffix.lower() == ".md"
            ):
                anchors = anchor_cache.get(resolved)
                if anchors is None:
                    anchors = extract_heading_anchors(resolved)
                    anchor_cache[resolved] = anchors
                if anchor not in anchors:
                    findings.append(
                        Finding(
                            file=markdown_file,
                            line=line_no,
                            severity="ERROR",
                            message=f"Broken link anchor: {path_part}#{anchor}",
                        )
                    )

        if code_refs_scope:
            prefixes = CODE_REF_PREFIXES_REPO if code_refs_scope == "repo" else CODE_REF_PREFIXES
            for code_span in extract_code_spans(raw_line):
                for candidate in extract_code_file_refs_with_prefixes(code_span, prefixes):
                    candidate = unquote(candidate).strip()
                    if not candidate:
                        continue

                    path_part, _hash, _anchor = split_path_and_anchor(candidate)
                    path_part = strip_location_suffix(path_part)
                    if not path_part:
                        continue

                    suffix = Path(path_part).suffix
                    if path_part not in ROOT_FILENAMES and not suffix:
                        continue
                    if suffix and suffix not in ALLOWED_CODE_REF_SUFFIXES:
                        continue
                    if is_placeholder_code_ref(path_part):
                        continue

                    resolved = resolve_code_ref_path(path_part)
                    if not resolved.exists():
                        resolved = maybe_resolve_product_repo_path(
                            resolved,
                            product_policy=product_policy,
                            product_root=product_root,
                        )
                    if not resolved.exists():
                        findings.append(
                            Finding(
                                file=markdown_file,
                                line=line_no,
                                severity="ERROR",
                                message=f"Missing referenced file: {path_part}",
                            )
                        )

    return findings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lint planveyor docs for broken internal references.")
    parser.add_argument(
        "--root",
        action="append",
        default=[],
        help="Root file/dir to scan. Can be repeated.",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Directory to exclude from scan. Can be repeated.",
    )
    parser.add_argument(
        "--exclude-file",
        action="append",
        default=[],
        help="File to exclude from scan. Can be repeated.",
    )
    parser.add_argument(
        "--check-code-refs",
        action="store_true",
        help="Also check inline code span file references (`...`).",
    )
    parser.add_argument(
        "--code-refs-scope",
        choices=("docs", "repo"),
        default="docs",
        help="Scope of inline code span checks: 'docs' or 'repo'.",
    )
    parser.add_argument(
        "--check-anchors",
        action="store_true",
        help="Also validate anchors for markdown links (best-effort).",
    )
    parser.add_argument(
        "--check-basic-hygiene",
        action="store_true",
        help="Only scan selected markdown roots for trailing whitespace and raw merge markers.",
    )
    parser.add_argument(
        "--product-root",
        default=None,
        help="Explicit absolute target repository root for cross-repository references.",
    )
    parser.add_argument(
        "--content-profile-id",
        default="default",
        choices=sorted(_KNOWN_CONTENT_PROFILES),
        help="Public profiles use generic references; callers may pass an explicit ProductRootPolicy.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        product_root = _selected_product_root(args.product_root)
        product_policy = load_product_root_policy(content_profile_id=args.content_profile_id, policy_root=product_root)
    except ProductRootPolicyError as exc:
        print(f"doc-lint: product-root policy invalid: {exc}", file=sys.stderr)
        return 2

    roots = [Path(p) for p in args.root] if args.root else list(DEFAULT_ROOTS)
    if args.root and product_root is None and any(not is_within_root(root, REPO_ROOT) for root in roots):
        print(
            "doc-lint: cross-repository roots require --product-root or PLANVEYOR_PRODUCT_ROOT",
            file=sys.stderr,
        )
        return 2
    exclude_dirs = [Path(p) for p in args.exclude] if args.exclude else list(DEFAULT_EXCLUDES)
    exclude_files = [Path(p) for p in args.exclude_file] if args.exclude_file else list(DEFAULT_EXCLUDE_FILES)
    selected_repo_root = infer_selected_repo_root(roots, product_root=product_root)

    if args.check_basic_hygiene:
        # In this mode --root values are proof inputs, not canonical-doc discovery
        # roots.  Default excludes would otherwise skip plan/review artifacts.
        hygiene_exclude_dirs = [Path(p) for p in args.exclude] if args.exclude else []
        hygiene_exclude_files = [Path(p) for p in args.exclude_file] if args.exclude_file else []
        hygiene_markdown_files, hygiene_findings = collect_basic_hygiene_files(
            roots,
            hygiene_exclude_dirs,
            hygiene_exclude_files,
        )
        hygiene_findings.extend(lint_basic_hygiene(hygiene_markdown_files))
        if not hygiene_findings:
            print("doc-lint: OK")
            return 0

        hygiene_findings.sort(key=lambda finding: (rel(finding.file), finding.line, finding.message))
        for finding in hygiene_findings:
            print(f"{rel(finding.file)}:{finding.line}: {finding.severity}: {finding.message}")

        errors = sum(1 for finding in hygiene_findings if finding.severity == "ERROR")
        warnings = sum(1 for finding in hygiene_findings if finding.severity == "WARN")
        if errors:
            print(f"doc-lint: FAIL ({errors} errors, {warnings} warnings)")
            return 1
        print(f"doc-lint: OK ({warnings} warnings)")
        return 0

    allow_default_excluded_explicit_files = tuple(
        root.resolve()
        for root in roots
        if args.root and not args.exclude and root.is_file()
    )
    markdown_files = iter_markdown_files(
        roots,
        exclude_dirs,
        exclude_files,
        allow_default_excluded_explicit_files=allow_default_excluded_explicit_files,
    )
    anchor_cache: dict[Path, set[str]] = {}

    all_findings: list[Finding] = []
    if scope_covers_reviewability_preflight_receipt_bundle(
        roots,
        exclude_dirs,
        exclude_files,
        allow_default_excluded_explicit_files=allow_default_excluded_explicit_files,
    ):
        all_findings.extend(lint_reviewability_preflight_receipt_bundle())
    if not args.root or scope_covers_receipt_schema_emitter_inventory_bundle(
        roots,
        exclude_dirs,
        exclude_files,
        allow_default_excluded_explicit_files=allow_default_excluded_explicit_files,
    ):
        all_findings.extend(lint_receipt_schema_emitter_inventory_bundle(selected_repo_root))
    if scope_covers_reviewer_manager_deadlock_bundle(
        roots,
        exclude_dirs,
        exclude_files,
        allow_default_excluded_explicit_files=allow_default_excluded_explicit_files,
    ):
        all_findings.extend(lint_reviewer_manager_deadlock_bundle())
    if not args.root or scope_covers_adr_bundle(
        roots,
        exclude_dirs,
        exclude_files,
        selected_repo_root,
        allow_default_excluded_explicit_files=allow_default_excluded_explicit_files,
    ):
        all_findings.extend(lint_adr_bundle(selected_repo_root))
    if not args.root or scope_covers_descoped_debt_guard_bundle(
        roots,
        exclude_dirs,
        exclude_files,
        allow_default_excluded_explicit_files=allow_default_excluded_explicit_files,
    ):
        all_findings.extend(lint_descoped_debt_guard_bundle(selected_repo_root))
    if not args.root:
        all_findings.extend(lint_generated_surface_freshness(selected_repo_root))
    all_findings.extend(
        lint_harvest_durable_followup_carriers(
            markdown_files,
            repo_root=selected_repo_root,
            product_root=product_root,
        )
    )
    for markdown_file in markdown_files:
        all_findings.extend(
            lint_file(
                markdown_file,
                code_refs_scope=args.code_refs_scope if args.check_code_refs else None,
                check_anchors=args.check_anchors,
                anchor_cache=anchor_cache,
                product_policy=product_policy,
                product_root=product_root,
            )
        )

    if not all_findings:
        print("doc-lint: OK")
        return 0

    all_findings.sort(key=lambda finding: (rel(finding.file), finding.line, finding.message))
    for finding in all_findings:
        print(f"{rel(finding.file)}:{finding.line}: {finding.severity}: {finding.message}")

    errors = sum(1 for finding in all_findings if finding.severity == "ERROR")
    warnings = sum(1 for finding in all_findings if finding.severity == "WARN")
    if errors:
        print(f"doc-lint: FAIL ({errors} errors, {warnings} warnings)")
        return 1

    print(f"doc-lint: OK ({warnings} warnings)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

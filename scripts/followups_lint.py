#!/usr/bin/env python3
"""Validate follow-ups backlog files and expose shared lifecycle helpers."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping


FOLLOWUPS_IGNORE = {"README.md", "index.md", "_template_followups_backlog.md"}
ALLOWED_ITEM_STATUSES = {"open", "promoted", "handled", "unconfirmed", "cancelled"}
V2_ITEM_STATUSES = {"open", "promoted", "handled", "cancelled"}
V2_DISPOSITION_KINDS = {"promoted_plan", "terminal_delivery", "cancelled_decision"}
V2_REQUIRED_FIELDS = (
    "cluster",
    "to",
    "status",
    "plan",
    "why",
    "item_id",
    "source_ref",
    "disposition_kind",
    "disposition_ref",
    "disposition_commit_oid",
    "reason",
)
V2_LEGACY_BRIDGE_FIELDS = (
    "legacy_row_ref",
    "legacy_plan_sha256",
    "legacy_row_sha256",
)
V2_PRESENTATION_FIELDS = (
    "source_intent",
    "canon_summary",
    "sources",
)
PROCESS_IMPROVEMENT_ONLY_ITEM_STATUSES = {"triaged", "deferred", "rejected"}
ALLOWED_ASSIGNEES = {"planner", "architect", "coder", "owner", "reviewer", "manager"}
ACCEPTED_PROMOTE_TARGET_PREFIXES = (
    "docs/plans/",
    "docs/reviews/",
    "docs/code_reviews/",
    "docs/doc_reviews/",
    "docs/code_drafts/",
)
TERMINAL_PLAN_STATUSES = {"done"}
STALE_PLAN_STATUSES = {"superseded"}
CLEANUP_RECEIPT_DECISIONS = {"delete-ready", "retain", "needs-richer-summary"}
CLEANUP_REVERSE_REFERENCE_ROOTS = (
    "docs/followups",
    "docs/plans",
    "docs/reviews",
    "docs/code_reviews",
    "docs/doc_reviews",
    "docs/playbooks",
    "docs/tools",
)

ITEM_RE = re.compile(r"^\s*-\s*(?P<prio>P[0-9?])\s+\[(?P<mark>[ xX])\]\s+(?P<body>.+?)\s*$")
HEADER_STATUS_RE = re.compile(r"^\s*(?:-\s*)?\*\*Status:\*\*\s*(?P<value>.+?)\s*$")
HEADER_SCHEMA_VERSION_RE = re.compile(r"^\s*(?:-\s*)?\*\*Schema version:\*\*\s*(?P<value>.+?)\s*$", re.IGNORECASE)
IMPORTED_INTO_RE = re.compile(r"^\s*(?:-\s*)?\*\*Imported into:\*\*\s*(?P<value>.+?)\s*$")
IMPORTED_REF_RE = re.compile(r"`(docs/followups/[^`]+\.md)`")
SECTION_H2_RE = re.compile(r"^\s*##\s+")
FOLLOWUPS_H2_RE = re.compile(r"^\s*##\s+Follow-ups\b", re.IGNORECASE)
PLAN_PLACEHOLDER_RE = re.compile(
    r"^docs/plans/[^`\s]*?(?:YYMMDD|YYYYMMDD|UNCONFIRMED|<[^>]+>)[^`\s]*\.md$",
    re.IGNORECASE,
)
CURRENT_FOLLOWUPS_SCHEMA_VERSION = "followups.v2"
LEGACY_FOLLOWUPS_SCHEMA_VERSION = "followups.v1"
V2_ITEM_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,79}$")
GIT_OID_RE = re.compile(r"^[0-9a-f]{40,64}$")
LEGACY_ROW_REF_RE = re.compile(r"^plan_meta\.followups_out\[(?P<index>[1-9][0-9]*)\]$")
PLAN_SCHEMA_VERSION_RE = re.compile(r"^\s*\*\*Schema version:\*\*\s*(?P<value>.+?)\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class Finding:
    rel_path: str
    line_no: int | None
    code: str
    message: str

    def render(self) -> str:
        if self.line_no is None:
            return f"{self.rel_path}: {self.code}: {self.message}"
        return f"{self.rel_path}:{self.line_no}: {self.code}: {self.message}"


@dataclass(frozen=True)
class TargetState:
    raw: str | None
    normalized: str | None
    resolved_path: Path | None
    exists: bool
    kind: str
    status_norm: str | None
    bucket: str
    closure_proof_class: str | None = None


@dataclass(frozen=True)
class FollowupItem:
    rel_path: str
    line_no: int
    priority: str
    mark: str
    body: str
    summary: str
    fields: dict[str, str]
    cluster: str | None
    assignee: str | None
    status: str | None
    plan: str | None
    why: str | None
    tags: tuple[str, ...]

    @property
    def item_id(self) -> str | None:
        return _normalize_scalar(self.fields.get("item_id"))

    @property
    def source_ref(self) -> str | None:
        return _normalize_scalar(self.fields.get("source_ref"))

    @property
    def disposition_kind(self) -> str | None:
        return _normalize_nullable(self.fields.get("disposition_kind"))

    @property
    def disposition_ref(self) -> str | None:
        return _normalize_nullable(self.fields.get("disposition_ref"))

    @property
    def disposition_commit_oid(self) -> str | None:
        return _normalize_nullable(self.fields.get("disposition_commit_oid"))

    @property
    def reason(self) -> str | None:
        return _normalize_nullable(self.fields.get("reason"))

    @property
    def legacy_row_ref(self) -> str | None:
        return _normalize_nullable(self.fields.get("legacy_row_ref"))

    @property
    def legacy_plan_sha256(self) -> str | None:
        return _normalize_nullable(self.fields.get("legacy_plan_sha256"))

    @property
    def legacy_row_sha256(self) -> str | None:
        return _normalize_nullable(self.fields.get("legacy_row_sha256"))

    def render_line(self, *, body: str | None = None, mark: str | None = None) -> str:
        next_body = self.body if body is None else body
        next_mark = self.mark if mark is None else mark
        return f"- {self.priority} [{next_mark}] {next_body}"


@dataclass(frozen=True)
class MalformedFollowupRow:
    rel_path: str
    line_no: int
    line: str


@dataclass
class FollowupFile:
    path: Path
    rel_path: str
    lines: list[str]
    header_status: str | None
    imported_into: str | None
    items: list[FollowupItem]
    malformed_rows: list[MalformedFollowupRow]

    @property
    def is_master(self) -> bool:
        return self.path.name.endswith("_followups_master.md")

    @property
    def is_done(self) -> bool:
        return self.header_status == "done"

    @property
    def imported_refs(self) -> tuple[str, ...]:
        return tuple(parse_imported_refs(self.imported_into))

    def updated_text(self, replacements: dict[int, str]) -> str:
        out: list[str] = []
        for idx, line in enumerate(self.lines, start=1):
            out.append(replacements.get(idx, line))
        return "\n".join(out) + "\n"


@dataclass(frozen=True)
class _FollowupsSnapshotInventory:
    """Private three-way classification of one immutable follow-ups snapshot.

    Callers must provide the object map and bytes returned by the same
    ``snapshot_followups(..., include_bytes=True)`` read.  This keeps
    compatibility-only V1 carriers out of the V2 authority set without
    silently discarding an explicit or malformed V2 carrier.
    """

    legacy_v1: dict[str, FollowupFile]
    valid_v2: dict[str, FollowupFile]
    blockers: tuple[Finding, ...]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _normalize_scalar(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().strip("`").strip().strip("'").strip('"').strip()
    normalized = normalized.replace("\u00a0", " ")
    return normalized or None


def _normalize_nullable(value: str | None) -> str | None:
    normalized = _normalize_scalar(value)
    if normalized is None or normalized.lower() == "null":
        return None
    return normalized


def _normalize_item_status(value: str | None) -> str | None:
    normalized = _normalize_scalar(value)
    return None if normalized is None else normalized.lower()


def _normalize_header_status(value: str | None) -> str | None:
    normalized = _normalize_scalar(value)
    if normalized is None:
        return None
    normalized = normalized.lower().replace("✅", "").strip()
    return " ".join(normalized.split())


def _normalize_schema_version(value: str) -> str:
    return " ".join(value.replace("`", "").split()).lower()


def parse_imported_refs(value: str | None) -> list[str]:
    if value is None:
        return []
    raw = value.strip()
    normalized = _normalize_scalar(value)
    if normalized is None:
        return []
    if normalized.upper().startswith("N/A"):
        return []

    refs = [ref.strip() for ref in IMPORTED_REF_RE.findall(raw) if ref.strip()]
    if refs:
        return refs

    out: list[str] = []
    for part in normalized.split(","):
        candidate = _normalize_scalar(part)
        if candidate is None or candidate.upper().startswith("N/A"):
            continue
        if candidate.startswith("docs/followups/") and candidate.endswith(".md"):
            out.append(candidate)
    return out


def _split_tokens(body: str) -> tuple[str, list[str]]:
    if " — " in body:
        parts = [part.strip() for part in body.split(" — ")]
    elif " - " in body:
        parts = [part.strip() for part in body.split(" - ")]
    else:
        parts = [body.strip()]
    summary = parts[0] if parts else body.strip()
    tokens = parts[1:] if len(parts) > 1 else []
    return summary, tokens


def _join_tokens(summary: str, tokens: Iterable[str]) -> str:
    rendered = [summary.strip(), *[token.strip() for token in tokens if token.strip()]]
    return " — ".join(rendered)


def token_key(token: str) -> str | None:
    raw = token.strip()
    if not raw:
        return None
    if raw.lower().startswith("why:"):
        return "why"
    if "=" in raw:
        key = raw.split("=", 1)[0].strip().lower()
        if re.fullmatch(r"[a-z_][a-z0-9_]*", key):
            return key
    return None


def extract_field(body: str, key: str) -> str | None:
    _, tokens = _split_tokens(body)
    wanted = key.lower()
    for token in tokens:
        current_key = token_key(token)
        if current_key != wanted:
            continue
        if wanted == "why":
            return token.split(":", 1)[1].strip() if ":" in token else ""
        if "=" in token:
            return token.split("=", 1)[1].strip()
    return None


def upsert_field(body: str, key: str, value: str) -> str:
    summary, tokens = _split_tokens(body)
    wanted = key.lower()
    replacement = f"{wanted}={value}" if wanted != "why" else f"why: {value}"
    for idx, token in enumerate(tokens):
        if token_key(token) == wanted:
            tokens[idx] = replacement
            return _join_tokens(summary, tokens)
    tokens.append(replacement)
    return _join_tokens(summary, tokens)


def parse_tags(raw: str | None) -> tuple[str, ...]:
    normalized = _normalize_scalar(raw)
    if normalized is None:
        return ()
    source = normalized
    if source.startswith("[") and source.endswith("]"):
        source = source[1:-1]
    values: list[str] = []
    for part in source.split(","):
        token = _normalize_scalar(part)
        if token:
            values.append(token)
    return tuple(values)


def normalize_plan_value(raw: str | None) -> str | None:
    normalized = _normalize_scalar(raw)
    if normalized is None:
        return None
    if normalized.lower() == "null":
        return "null"
    return normalized


def is_placeholder_plan(plan_value: str | None) -> bool:
    if plan_value is None or plan_value == "null":
        return False
    return bool(PLAN_PLACEHOLDER_RE.match(plan_value))


def path_kind(rel_path: str) -> str:
    if rel_path.startswith("docs/plans/"):
        return "plan"
    if rel_path.startswith("docs/reviews/"):
        return "review"
    if rel_path.startswith("docs/code_reviews/"):
        return "code_review"
    if rel_path.startswith("docs/doc_reviews/"):
        return "doc_review"
    if rel_path.startswith("docs/code_drafts/"):
        return "code_draft"
    return "other"


def resolve_project_root(project_root: str | None) -> Path:
    root = Path(project_root).expanduser() if project_root else Path.cwd()
    return root.resolve()


def followups_dir(project_root: Path) -> Path:
    return project_root / "docs" / "followups"


def iter_followup_paths(project_root: Path) -> list[Path]:
    from followups_capture import snapshot_followups

    objects, _contents = snapshot_followups(project_root)
    return [
        project_root / rel_path
        for rel_path in sorted(objects)
        if Path(rel_path).name not in FOLLOWUPS_IGNORE
    ]


def resolve_followup_path(project_root: Path, raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path.absolute()
    return (project_root / path).absolute()


def expand_followup_target(project_root: Path, raw_path: str) -> list[Path]:
    resolved = resolve_followup_path(project_root, raw_path)
    if resolved == project_root.absolute():
        return iter_followup_paths(project_root)
    followups_root = followups_dir(project_root).absolute()
    if resolved == followups_root:
        return iter_followup_paths(project_root)
    try:
        rel_path = resolved.relative_to(project_root.absolute()).as_posix()
    except ValueError:
        return [resolved]
    from followups_capture import validate_followup_relpath

    validate_followup_relpath(rel_path)
    return [resolved]


def parse_followup_item(rel_path: str, line_no: int, line: str) -> FollowupItem | None:
    match = ITEM_RE.match(line)
    if not match:
        return None
    priority = match.group("prio")
    mark = match.group("mark")
    body = match.group("body").strip()
    summary, tokens = _split_tokens(body)

    fields: dict[str, str] = {}
    for token in tokens:
        key = token_key(token)
        if key is None:
            continue
        if key == "why":
            value = token.split(":", 1)[1].strip() if ":" in token else ""
        else:
            value = token.split("=", 1)[1].strip()
        fields[key] = value

    cluster = _normalize_scalar(fields.get("cluster"))
    cluster = cluster.lower() if cluster else None
    assignee = _normalize_scalar(fields.get("to"))
    assignee = assignee.lower() if assignee else None
    status = _normalize_item_status(fields.get("status"))
    plan = normalize_plan_value(fields.get("plan"))
    why = _normalize_scalar(fields.get("why"))
    tags = parse_tags(fields.get("tags"))

    return FollowupItem(
        rel_path=rel_path,
        line_no=line_no,
        priority=priority,
        mark=mark,
        body=body,
        summary=summary,
        fields=fields,
        cluster=cluster,
        assignee=assignee,
        status=status,
        plan=plan,
        why=why,
        tags=tags,
    )


def is_allowed_non_item_followup_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if stripped.startswith("### "):
        return True
    if stripped.startswith("```"):
        return True
    if stripped == "Формат:" or stripped == "Формат (рекомендованный):":
        return True
    if stripped.startswith("`") and stripped.endswith("`"):
        return True
    return False


def looks_like_followup_item_candidate(line: str) -> bool:
    stripped = line.strip()
    if not stripped or is_allowed_non_item_followup_line(line):
        return False
    if re.match(r"^-?\s*P[0-9?]\b", stripped):
        return True
    return any(anchor in stripped for anchor in ("cluster=", "to=", "status=", "plan=", "why:"))


def parse_followup_text(text: str, rel_path: str, path: Path) -> FollowupFile:
    lines = text.splitlines()
    header_status: str | None = None
    imported_into: str | None = None
    items: list[FollowupItem] = []
    malformed_rows: list[MalformedFollowupRow] = []
    in_followups = False

    for idx, line in enumerate(lines, start=1):
        if header_status is None:
            status_match = HEADER_STATUS_RE.match(line)
            if status_match:
                header_status = _normalize_header_status(status_match.group("value"))
        if imported_into is None:
            imported_match = IMPORTED_INTO_RE.match(line)
            if imported_match:
                imported_into = _normalize_scalar(imported_match.group("value"))

        if FOLLOWUPS_H2_RE.match(line):
            in_followups = True
            continue
        if in_followups and SECTION_H2_RE.match(line):
            break
        if not in_followups:
            continue
        item = parse_followup_item(rel_path, idx, line)
        if item is not None:
            items.append(item)
            continue
        if looks_like_followup_item_candidate(line):
            malformed_rows.append(MalformedFollowupRow(rel_path=rel_path, line_no=idx, line=line.strip()))

    return FollowupFile(
        path=path.absolute(),
        rel_path=rel_path,
        lines=lines,
        header_status=header_status,
        imported_into=imported_into,
        items=items,
        malformed_rows=malformed_rows,
    )


def parse_followup_file(path: Path, project_root: Path) -> FollowupFile:
    from followups_capture import read_followup_path, validate_followup_relpath

    try:
        rel_path = path.absolute().relative_to(project_root.absolute()).as_posix()
    except ValueError as exc:
        raise ValueError(f"followups target is outside project root: {path}") from exc
    rel_path = validate_followup_relpath(rel_path)
    _object, data = read_followup_path(project_root, rel_path)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"followups target is not UTF-8: {rel_path}: {exc}") from exc
    return parse_followup_text(text, rel_path, project_root / rel_path)


def normalize_source_ref(raw: str | None) -> str | None:
    """Return one safe repo-relative source reference, optionally with an anchor.

    V2 uses the source reference as part of durable identity.  It deliberately
    does not resolve a source path: the durable row may refer to a historical
    terminal blob, while path existence is verified by the capture/promote
    boundary that owns that operation.
    """

    value = _normalize_nullable(raw)
    if value is None:
        return None
    path_part, marker, anchor = value.partition("#")
    path_part = path_part.strip()
    if not path_part or path_part.startswith(("/", "~")) or "\\" in path_part:
        return None
    pieces = path_part.split("/")
    if any(piece in {"", ".", ".."} for piece in pieces):
        return None
    if marker and not anchor.strip():
        return None
    if marker and "#" in anchor:
        return None
    return f"{path_part}#{anchor.strip()}" if marker else path_part


def v2_row_payload(item: FollowupItem) -> dict[str, object]:
    """Normalize the immutable semantic payload used by V2 tuple/digest proof."""

    payload: dict[str, object] = {
        "priority": item.priority,
        "summary": item.summary,
        "cluster": item.cluster,
        "to": item.assignee,
        "status": item.status,
        # ``FollowupItem.plan`` deliberately preserves the historical V1
        # spelling ``"null"`` for legacy callers.  V2 proof/digests use one
        # semantic null instead, otherwise a rendered ``plan=null`` row would
        # fail its own strict open-state matrix after a parse/readback cycle.
        "plan": _normalize_nullable(item.fields.get("plan")),
        "why": item.why,
        "tags": list(item.tags),
        "item_id": item.item_id,
        "source_ref": normalize_source_ref(item.source_ref),
        "disposition_kind": item.disposition_kind,
        "disposition_ref": item.disposition_ref,
        "disposition_commit_oid": item.disposition_commit_oid,
        "reason": item.reason,
        "legacy_row_ref": item.legacy_row_ref,
        "legacy_plan_sha256": item.legacy_plan_sha256,
        "legacy_row_sha256": item.legacy_row_sha256,
    }
    for field in V2_PRESENTATION_FIELDS:
        if item.fields.get(field) is not None:
            payload[field] = item.fields[field]
    return payload


def canonical_v2_row_bytes(payload: Mapping[str, object]) -> bytes:
    return json.dumps(
        dict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def v2_row_digest(item_or_payload: FollowupItem | Mapping[str, object]) -> str:
    payload = v2_row_payload(item_or_payload) if isinstance(item_or_payload, FollowupItem) else dict(item_or_payload)
    for field in V2_LEGACY_BRIDGE_FIELDS:
        payload.setdefault(field, None)
    return _sha256(canonical_v2_row_bytes(payload))


def render_v2_row(payload: Mapping[str, object]) -> str:
    """Render the one stable markdown grammar accepted by the V2 writer."""

    required = (
        "priority",
        "summary",
        "cluster",
        "to",
        "status",
        "plan",
        "why",
        "item_id",
        "source_ref",
        "disposition_kind",
        "disposition_ref",
        "disposition_commit_oid",
        "reason",
    )
    missing = [key for key in required if key not in payload]
    if missing:
        raise ValueError(f"V2 row payload is missing fields: {', '.join(missing)}")
    priority = str(payload["priority"])
    summary = str(payload["summary"]).strip()
    if priority not in {"P0", "P1", "P2", "P?"} or not summary:
        raise ValueError("V2 row requires a supported priority and non-empty summary")

    def text_or_null(key: str) -> str:
        value = payload.get(key)
        return "null" if value is None else str(value).strip() or "null"

    tags = payload.get("tags")
    tag_token = ""
    if isinstance(tags, (list, tuple)) and tags:
        tag_token = f" — tags={','.join(str(value).strip() for value in tags if str(value).strip())}"
    bridge_tokens = "".join(
        f" — {key}={text_or_null(key)}"
        for key in V2_LEGACY_BRIDGE_FIELDS
        if payload.get(key) is not None
    )
    presentation_prefix = "".join(
        f" — {key}={text_or_null(key)}"
        for key in ("source_intent", "canon_summary")
        if payload.get(key) is not None
    )
    presentation_suffix = "".join(
        f" — {key}={text_or_null(key)}"
        for key in ("sources",)
        if payload.get(key) is not None
    )
    return (
        f"- {priority} [ ] {summary}"
        f"{presentation_prefix}"
        f" — cluster={text_or_null('cluster')}"
        f"{tag_token}"
        f" — to={text_or_null('to')}"
        f" — status={text_or_null('status')}"
        f" — plan={text_or_null('plan')}"
        f" — item_id={text_or_null('item_id')}"
        f" — source_ref={text_or_null('source_ref')}"
        f" — disposition_kind={text_or_null('disposition_kind')}"
        f" — disposition_ref={text_or_null('disposition_ref')}"
        f" — disposition_commit_oid={text_or_null('disposition_commit_oid')}"
        f" — reason={text_or_null('reason')}"
        f"{bridge_tokens}"
        f" — why: {text_or_null('why')}"
        f"{presentation_suffix}"
    )


def load_followup_files(project_root: Path, paths: Iterable[str] | None = None) -> list[FollowupFile]:
    selected_paths = (
        [path for raw in paths for path in expand_followup_target(project_root, raw)]
        if paths
        else iter_followup_paths(project_root)
    )
    return [
        parse_followup_file(path, project_root)
        for path in selected_paths
        if os.path.lexists(path)
    ]


def read_markdown_status_header(path: Path) -> str | None:
    lines = _read_text(path).splitlines()
    matches: list[str] = []
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith(">"):
            continue
        if stripped.startswith("##"):
            break
        match = HEADER_STATUS_RE.match(line)
        if match:
            matches.append(match.group("value"))
    if len(matches) != 1:
        return None
    return _normalize_item_status(matches[0])


def _plan_closure_proof_class(path: Path) -> str | None:
    text = _read_text(path)
    if (
        re.search(r"Architect arch review\s*(?:->|→)\s*Done|Ready for Arch review\s*(?:->|→).*Done", text, re.IGNORECASE)
        and ("review_artifact_lint" in text or "planveyor_plan_bundle --check" in text)
    ):
        return "arch_review_ok"
    if re.search(r"\*\*Status:\*\*\s*✅\s*OK|`✅ OK`|review artifact.*✅ OK", text, re.IGNORECASE):
        return "review_artifact_ok"
    if "planveyor_plan_bundle --commit-ready" in text:
        return "commit_ready"
    if (
        "## Acceptance criteria / DoD" in text
        and re.search(r"^- \[x\] ", text, re.MULTILINE)
        and re.search(r"Status (?:moved |-> ).*Done|Status -> `Done`", text)
    ):
        return "accepted_dod_evidence"
    return None


def _extract_schema_version_lines(lines: list[str]) -> list[tuple[int, str]]:
    matches: list[tuple[int, str]] = []
    for line_no, line in enumerate(lines, start=1):
        match = HEADER_SCHEMA_VERSION_RE.match(line)
        if not match:
            continue
        matches.append((line_no, match.group("value").strip()))
    return matches


def classify_followups_schema_version(followup: FollowupFile) -> tuple[str, list[Finding]]:
    findings: list[Finding] = []
    matches = _extract_schema_version_lines(followup.lines)
    if len(matches) > 1:
        line_nos = ", ".join(str(line_no) for line_no, _ in matches)
        findings.append(
            Finding(
                rel_path=followup.rel_path,
                line_no=matches[0][0],
                code="multiple_schema_version_headers",
                message=f"Multiple `**Schema version:**` header lines found ({line_nos}). Keep one canonical top-level carrier.",
            )
        )
        return "unsupported", findings

    if not matches:
        if followup.path.name == "_template_followups_backlog.md":
            findings.append(
                Finding(
                    rel_path=followup.rel_path,
                    line_no=1,
                    code="missing_schema_version",
                    message="Missing `**Schema version:** followups.v2` on the canonical followups template. "
                    "Versionless non-template backlog files are tolerated only as legacy compatibility carriers.",
                )
            )
            return "unsupported", findings
        return "legacy_v1", findings

    line_no, raw_value = matches[0]
    normalized = _normalize_schema_version(raw_value)
    if normalized == CURRENT_FOLLOWUPS_SCHEMA_VERSION:
        return "v2", findings
    if normalized == LEGACY_FOLLOWUPS_SCHEMA_VERSION:
        return "legacy_v1", findings
    if normalized != CURRENT_FOLLOWUPS_SCHEMA_VERSION:
        findings.append(
            Finding(
                rel_path=followup.rel_path,
                line_no=line_no,
                code="unsupported_schema_version",
                message=(
                    f"Unsupported followups schema version {raw_value!r}; current={CURRENT_FOLLOWUPS_SCHEMA_VERSION!r}, "
                    f"legacy={LEGACY_FOLLOWUPS_SCHEMA_VERSION!r} and versionless historical backlog files remain readable."
                ),
            )
        )
        return "unsupported", findings

    raise AssertionError("unreachable schema classifier")


def _inventory_followups_snapshot(
    project_root: Path,
    snapshot: Mapping[str, Mapping[str, Any]],
    file_bytes: Mapping[str, bytes],
) -> _FollowupsSnapshotInventory:
    """Classify one complete immutable snapshot for V2 authority admission.

    This intentionally reuses the existing snapshot reader, text parser,
    schema classifier and V2 linter.  It does not invent another Markdown
    grammar: section cardinality is counted with the existing canonical H2
    matcher.  A malformed explicit V2 file is therefore a blocker, whereas a
    proven legacy V1 carrier remains compatibility-only.
    """

    try:
        from followups_capture import CaptureError, validate_followup_relpath
    except ModuleNotFoundError:  # package import in focused unittest invocation
        from scripts.followups_capture import CaptureError, validate_followup_relpath

    legacy_v1: dict[str, FollowupFile] = {}
    valid_v2: dict[str, FollowupFile] = {}
    blockers: list[Finding] = []
    ignored_paths = {
        rel_path
        for rel_path in set(snapshot) | set(file_bytes)
        if Path(rel_path).name in FOLLOWUPS_IGNORE
    }

    for rel_path in sorted((set(snapshot) | set(file_bytes)) - ignored_paths):
        if rel_path not in snapshot or rel_path not in file_bytes:
            blockers.append(
                Finding(
                    rel_path=rel_path,
                    line_no=None,
                    code="followups_snapshot_incomplete",
                    message="Follow-ups snapshot object map and byte map must contain the same carrier paths.",
                )
            )
            continue
        try:
            normalized_path = validate_followup_relpath(rel_path)
        except CaptureError as exc:
            blockers.append(
                Finding(
                    rel_path=rel_path,
                    line_no=None,
                    code="followups_snapshot_path_invalid",
                    message=str(exc),
                )
            )
            continue
        if normalized_path != rel_path:
            blockers.append(
                Finding(
                    rel_path=rel_path,
                    line_no=None,
                    code="followups_snapshot_path_invalid",
                    message="Follow-ups snapshot path is not canonical.",
                )
            )
            continue

        object_value = snapshot[rel_path]
        data = file_bytes[rel_path]
        digest = hashlib.sha256(data).hexdigest()
        if (
            not isinstance(object_value, Mapping)
            or set(object_value) != {"sha256", "file_type", "st_size"}
            or object_value.get("sha256") != digest
            or object_value.get("file_type") != "regular"
            or object_value.get("st_size") != len(data)
        ):
            blockers.append(
                Finding(
                    rel_path=rel_path,
                    line_no=None,
                    code="followups_snapshot_object_invalid",
                    message="Follow-ups carrier is not one strict regular-file snapshot object bound to its supplied bytes.",
                )
            )
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            blockers.append(
                Finding(
                    rel_path=rel_path,
                    line_no=None,
                    code="followups_snapshot_not_utf8",
                    message="Follow-ups carrier is not strict UTF-8.",
                )
            )
            continue

        followup = parse_followup_text(text, rel_path, project_root / rel_path)
        schema_class, schema_findings = classify_followups_schema_version(followup)
        if schema_class == "legacy_v1" and not schema_findings:
            legacy_v1[rel_path] = followup
            continue
        if schema_class != "v2" or schema_findings:
            if schema_findings:
                blockers.extend(schema_findings)
            else:
                blockers.append(
                    Finding(
                        rel_path=rel_path,
                        line_no=None,
                        code="followups_schema_not_v2",
                        message="Explicit follow-ups carrier is not one canonical followups.v2 file.",
                    )
                )
            continue

        section_lines = [
            line_no
            for line_no, line in enumerate(followup.lines, start=1)
            if FOLLOWUPS_H2_RE.match(line)
        ]
        if len(section_lines) != 1:
            blockers.append(
                Finding(
                    rel_path=rel_path,
                    line_no=section_lines[0] if section_lines else None,
                    code="v2_followups_section_count_invalid",
                    message="A followups.v2 carrier requires exactly one canonical `## Follow-ups` section.",
                )
            )
            continue

        row_findings = lint_followup_files([followup], project_root)
        if row_findings:
            blockers.extend(row_findings)
            continue
        valid_v2[rel_path] = followup

    # Individual admission above intentionally keeps a cross-carrier duplicate
    # visible here.  The same complete-set lint is used by the writer before a
    # replacement and makes external readback fail closed as well.
    global_findings = lint_followup_files(
        [valid_v2[rel_path] for rel_path in sorted(valid_v2)],
        project_root,
    )
    seen = {(finding.rel_path, finding.line_no, finding.code, finding.message) for finding in blockers}
    for finding in global_findings:
        key = (finding.rel_path, finding.line_no, finding.code, finding.message)
        if key not in seen:
            blockers.append(finding)
            seen.add(key)

    return _FollowupsSnapshotInventory(
        legacy_v1=legacy_v1,
        valid_v2=valid_v2,
        blockers=tuple(blockers),
    )


def _v2_field_value(item: FollowupItem, key: str) -> str | None:
    if key == "plan":
        return item.plan
    if key == "why":
        return item.why
    if key == "item_id":
        return item.item_id
    if key == "source_ref":
        return item.source_ref
    if key == "disposition_kind":
        return item.disposition_kind
    if key == "disposition_ref":
        return item.disposition_ref
    if key == "disposition_commit_oid":
        return item.disposition_commit_oid
    if key == "reason":
        return item.reason
    return item.fields.get(key)


def _v2_finding(item: FollowupItem, code: str, message: str) -> Finding:
    return Finding(rel_path=item.rel_path, line_no=item.line_no, code=code, message=message)


def _v2_legacy_bridge_values(item: FollowupItem) -> dict[str, str | None]:
    return {
        "legacy_row_ref": item.legacy_row_ref,
        "legacy_plan_sha256": item.legacy_plan_sha256,
        "legacy_row_sha256": item.legacy_row_sha256,
    }


def v2_legacy_bridge_identity(item: FollowupItem) -> tuple[str, str] | None:
    """Return the one legacy row identity claimed by a complete V2 bridge."""

    values = _v2_legacy_bridge_values(item)
    row_ref = values["legacy_row_ref"]
    source_ref = normalize_source_ref(item.source_ref)
    if (
        source_ref is None
        or "#" in source_ref
        or row_ref is None
        or LEGACY_ROW_REF_RE.fullmatch(row_ref) is None
        or any(values[field] is None for field in V2_LEGACY_BRIDGE_FIELDS)
    ):
        return None
    return source_ref, row_ref


def _parse_plan_meta_object(plan_text: str) -> dict[str, object] | None:
    in_json = False
    block_lines: list[str] = []
    for line in plan_text.splitlines():
        if not in_json and re.fullmatch(r"\s*```json\s*", line, re.IGNORECASE):
            in_json = True
            block_lines = []
            continue
        if in_json and re.fullmatch(r"\s*```\s*", line):
            raw_block = "\n".join(block_lines).strip()
            in_json = False
            block_lines = []
            if "plan_meta" not in raw_block:
                continue
            try:
                parsed = json.loads(raw_block)
            except json.JSONDecodeError:
                continue
            meta = parsed.get("plan_meta") if isinstance(parsed, dict) else None
            if isinstance(meta, dict):
                return meta
            continue
        if in_json:
            block_lines.append(line)
    return None


def _lint_v2_legacy_bridge(item: FollowupItem, project_root: Path) -> list[Finding]:
    """Verify an optional V1 bridge by literal path/index/hash, never prose."""

    values = _v2_legacy_bridge_values(item)
    if not any(value is not None for value in values.values()):
        return []
    findings: list[Finding] = []
    missing = [field for field, value in values.items() if value is None]
    if missing:
        return [
            _v2_finding(
                item,
                "v2_legacy_bridge_incomplete",
                "V2 legacy bridge requires all of legacy_row_ref, legacy_plan_sha256 and legacy_row_sha256; missing "
                + ", ".join(missing)
                + ".",
            )
        ]
    assert all(isinstance(value, str) for value in values.values())
    row_ref = values["legacy_row_ref"]
    plan_sha = values["legacy_plan_sha256"]
    row_sha = values["legacy_row_sha256"]
    assert isinstance(row_ref, str) and isinstance(plan_sha, str) and isinstance(row_sha, str)
    row_ref_match = LEGACY_ROW_REF_RE.fullmatch(row_ref)
    if row_ref_match is None:
        findings.append(
            _v2_finding(
                item,
                "v2_legacy_bridge_row_ref_invalid",
                "legacy_row_ref must be an exact `plan_meta.followups_out[N]` reference with a 1-based index.",
            )
        )
    if not re.fullmatch(r"[0-9a-f]{64}", plan_sha) or not re.fullmatch(r"[0-9a-f]{64}", row_sha):
        findings.append(
            _v2_finding(
                item,
                "v2_legacy_bridge_hash_invalid",
                "legacy_plan_sha256 and legacy_row_sha256 must be 64-character lower-case SHA-256 values.",
            )
        )
    source_ref = normalize_source_ref(item.source_ref)
    if source_ref is None or "#" in source_ref:
        findings.append(
            _v2_finding(
                item,
                "v2_legacy_bridge_source_invalid",
                "a legacy bridge requires source_ref to be the exact unanchored legacy plan path.",
            )
        )
        return findings
    root = project_root.resolve()
    source_path = (root / source_ref).resolve()
    try:
        source_path.relative_to(root)
    except ValueError:
        findings.append(
            _v2_finding(item, "v2_legacy_bridge_source_invalid", "legacy bridge source plan escapes project root."))
        return findings
    if not source_path.is_file():
        findings.append(
            _v2_finding(item, "v2_legacy_bridge_source_missing", "legacy bridge source plan is not a regular file."))
        return findings
    try:
        plan_bytes = source_path.read_bytes()
        plan_text = plan_bytes.decode("utf-8")
    except (OSError, UnicodeDecodeError):
        findings.append(
            _v2_finding(item, "v2_legacy_bridge_source_invalid", "legacy bridge source plan is unreadable UTF-8."))
        return findings
    schema_values = [
        _normalize_schema_version(schema_match.group("value"))
        for line in plan_text.splitlines()
        if (schema_match := PLAN_SCHEMA_VERSION_RE.match(line))
    ]
    if schema_values != ["plan.v1"]:
        findings.append(
            _v2_finding(item, "v2_legacy_bridge_plan_schema_invalid", "legacy bridge source must be one explicit plan.v1 carrier."))
    if _sha256(plan_bytes) != plan_sha:
        findings.append(
            _v2_finding(item, "v2_legacy_bridge_plan_hash_mismatch", "legacy_plan_sha256 does not match source plan bytes."))
    plan_meta = _parse_plan_meta_object(plan_text)
    raw_rows = plan_meta.get("followups_out") if isinstance(plan_meta, dict) else None
    row_index = int(row_ref_match.group("index")) if row_ref_match is not None else 0
    if not isinstance(raw_rows, list) or row_index < 1 or row_index > len(raw_rows) or not isinstance(raw_rows[row_index - 1], dict):
        findings.append(
            _v2_finding(item, "v2_legacy_bridge_row_missing", "legacy_row_ref does not resolve to one object row in source plan_meta.followups_out."))
        return findings
    actual_row_sha = _sha256(
        json.dumps(raw_rows[row_index - 1], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    if actual_row_sha != row_sha:
        findings.append(
            _v2_finding(item, "v2_legacy_bridge_row_hash_mismatch", "legacy_row_sha256 does not match the exact source followups_out row."))
    return findings


def _lint_v2_commit_bound_disposition(
    item: FollowupItem,
    project_root: Path,
    *,
    status: str,
    disposition_ref: str,
    disposition_oid: str,
    plan: str | None,
) -> list[Finding]:
    """Verify a non-open V2 disposition against exact committed bytes."""

    root = project_root.resolve()
    commit_probe = subprocess.run(
        ["git", "rev-parse", f"{disposition_oid}^{{commit}}"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if commit_probe.returncode != 0:
        return [
            _v2_finding(
                item,
                "v2_disposition_commit_missing",
                "disposition_commit_oid does not resolve to a reachable commit in project_root.",
            )
        ]
    commit_oid = commit_probe.stdout.strip()
    reachable_probe = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit_oid, "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if reachable_probe.returncode != 0:
        return [
            _v2_finding(
                item,
                "v2_disposition_commit_unreachable",
                "disposition_commit_oid must be reachable from the current project_root HEAD.",
            )
        ]
    ref_path = disposition_ref.split("#", 1)[0]
    object_probe = subprocess.run(
        ["git", "show", f"{commit_oid}:{ref_path}"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if object_probe.returncode != 0:
        return [
            _v2_finding(
                item,
                "v2_disposition_ref_missing",
                "disposition_ref is absent from disposition_commit_oid.",
            )
        ]
    findings: list[Finding] = []
    if status == "promoted" and plan is not None and ref_path != plan:
        findings.append(
            _v2_finding(
                item,
                "v2_promoted_commit_ref_mismatch",
                "promoted disposition commit must materialize the exact plan= path.",
            )
        )
    if status == "handled" and ref_path.startswith("docs/plans/"):
        try:
            plan_text = object_probe.stdout.decode("utf-8")
        except UnicodeDecodeError:
            findings.append(
                _v2_finding(
                    item,
                    "v2_handled_plan_invalid",
                    "handled disposition plan bytes are not UTF-8.",
                )
            )
        else:
            statuses = [
                _normalize_header_status(match.group("value"))
                for line in plan_text.splitlines()
                if (match := HEADER_STATUS_RE.match(line))
            ]
            if statuses != ["done"] and statuses != ["superseded"]:
                findings.append(
                    _v2_finding(
                        item,
                        "v2_handled_plan_not_terminal",
                        "handled disposition_ref under docs/plans/ must be Done or Superseded in disposition_commit_oid.",
                    )
                )
    return findings


def lint_v2_item(
    item: FollowupItem,
    project_root: Path,
    *,
    validate_legacy_bridge_source: bool = True,
    validate_disposition_source: bool = True,
) -> list[Finding]:
    """Validate the V2 typed row matrix without inferring disposition from prose."""

    findings: list[Finding] = []
    missing = [key for key in V2_REQUIRED_FIELDS if item.fields.get(key) is None]
    if missing:
        findings.append(
            _v2_finding(item, "v2_missing_fields", f"V2 row is missing required fields: {', '.join(missing)}.")
        )
        return findings

    if item.assignee is None or item.assignee not in ALLOWED_ASSIGNEES:
        findings.append(_v2_finding(item, "v2_invalid_assignee", f"Unsupported `to=` value: {item.assignee!r}."))
    if item.cluster is None:
        findings.append(_v2_finding(item, "v2_invalid_cluster", "V2 row requires a non-empty `cluster=` value."))
    if item.why is None:
        findings.append(_v2_finding(item, "v2_missing_why", "V2 row requires a non-empty `why:` value."))
    if item.item_id is None or not V2_ITEM_ID_RE.fullmatch(item.item_id):
        findings.append(
            _v2_finding(
                item,
                "v2_invalid_item_id",
                "`item_id=` must match `^[a-z0-9][a-z0-9._-]{2,79}$` and remains stable across edits.",
            )
        )
    normalized_source = normalize_source_ref(item.source_ref)
    if normalized_source is None or normalized_source != item.source_ref:
        findings.append(
            _v2_finding(
                item,
                "v2_invalid_source_ref",
                "`source_ref=` must be one safe repo-relative path, optionally followed by one non-empty `#anchor`.",
            )
        )

    if validate_legacy_bridge_source:
        findings.extend(_lint_v2_legacy_bridge(item, project_root))

    status = item.status
    if status not in V2_ITEM_STATUSES:
        findings.append(
            _v2_finding(item, "v2_invalid_status", "V2 `status=` must be one of: open, promoted, handled, cancelled.")
        )
        return findings

    # V1 helpers retain literal ``"null"`` for compatibility; V2 is typed
    # and treats the canonical on-disk spelling ``null`` as JSON-like null.
    plan = _normalize_nullable(item.fields.get("plan"))
    disposition_kind = item.disposition_kind
    disposition_ref = item.disposition_ref
    disposition_oid = item.disposition_commit_oid
    reason = item.reason
    if status == "open":
        invalid = {
            "plan": plan,
            "disposition_kind": disposition_kind,
            "disposition_ref": disposition_ref,
            "disposition_commit_oid": disposition_oid,
        }
        non_null = [key for key, value in invalid.items() if value is not None]
        if non_null:
            findings.append(
                _v2_finding(
                    item,
                    "v2_open_disposition_not_null",
                    "`status=open` requires plan/disposition_kind/disposition_ref/disposition_commit_oid to be literal `null`: "
                    + ", ".join(non_null),
                )
            )
        return findings

    if reason is None:
        findings.append(
            _v2_finding(item, "v2_missing_disposition_reason", f"`status={status}` requires a non-null `reason=`."))
    if disposition_oid is None or not GIT_OID_RE.fullmatch(disposition_oid):
        findings.append(
            _v2_finding(
                item,
                "v2_invalid_disposition_commit_oid",
                "Non-open V2 rows require a 40..64 lower-case hexadecimal `disposition_commit_oid=`.",
            )
        )

    expected_kind = {
        "promoted": "promoted_plan",
        "handled": "terminal_delivery",
        "cancelled": "cancelled_decision",
    }[status]
    if disposition_kind != expected_kind:
        findings.append(
            _v2_finding(
                item,
                "v2_disposition_kind_mismatch",
                f"`status={status}` requires `disposition_kind={expected_kind}`.",
            )
        )
    if disposition_ref is None or normalize_source_ref(disposition_ref) != disposition_ref:
        findings.append(
            _v2_finding(
                item,
                "v2_invalid_disposition_ref",
                "Non-open V2 rows require one safe repo-relative `disposition_ref=`.",
            )
        )

    if status == "promoted":
        if plan is None or not plan.startswith("docs/plans/") or not plan.endswith(".md"):
            findings.append(
                _v2_finding(
                    item,
                    "v2_invalid_promoted_plan",
                    "`status=promoted` requires a repo-relative `plan=docs/plans/*.md`.",
                )
            )
        if plan is not None and disposition_ref != plan:
            findings.append(
                _v2_finding(
                    item,
                    "v2_promoted_ref_mismatch",
                    "`status=promoted` requires `disposition_ref` to equal `plan` exactly.",
                )
            )
    elif plan is not None:
        findings.append(
            _v2_finding(
                item,
                "v2_non_promoted_plan_not_null",
                f"`status={status}` requires `plan=null`; plan paths are only V2 promoted disposition targets.",
            )
        )
    if (
        validate_disposition_source
        and reason is not None
        and disposition_oid is not None
        and GIT_OID_RE.fullmatch(disposition_oid)
        and disposition_ref is not None
        and normalize_source_ref(disposition_ref) == disposition_ref
    ):
        findings.extend(
            _lint_v2_commit_bound_disposition(
                item,
                project_root,
                status=status,
                disposition_ref=disposition_ref,
                disposition_oid=disposition_oid,
                plan=plan,
            )
        )
    return findings


def resolve_target_state(
    project_root: Path,
    plan_value: str | None,
    cache: dict[str, TargetState] | None = None,
) -> TargetState:
    normalized = normalize_plan_value(plan_value)
    if normalized is None or normalized == "null":
        return TargetState(plan_value, normalized, None, False, "none", None, "none")

    if cache is not None and normalized in cache:
        return cache[normalized]

    if is_placeholder_plan(normalized):
        state = TargetState(plan_value, normalized, None, False, "plan", None, "placeholder")
        if cache is not None:
            cache[normalized] = state
        return state

    resolved: Path | None = None
    if normalized.startswith("/"):
        resolved = Path(normalized).expanduser().resolve()
    elif normalized.startswith("docs/"):
        resolved = (project_root / normalized).resolve()

    if resolved is None:
        state = TargetState(plan_value, normalized, None, False, "other", None, "unsupported")
        if cache is not None:
            cache[normalized] = state
        return state

    exists = resolved.exists()
    rel_path = normalized
    kind = path_kind(rel_path)
    if not exists:
        state = TargetState(plan_value, normalized, resolved, False, kind, None, "missing")
        if cache is not None:
            cache[normalized] = state
        return state

    if kind == "plan":
        status_norm = read_markdown_status_header(resolved)
        if status_norm in TERMINAL_PLAN_STATUSES:
            bucket = "done_plan"
            closure_proof_class = _plan_closure_proof_class(resolved)
        elif status_norm in STALE_PLAN_STATUSES:
            bucket = "stale_plan"
            closure_proof_class = "stale_plan"
        else:
            bucket = "active_plan"
            closure_proof_class = None
        state = TargetState(plan_value, normalized, resolved, True, kind, status_norm, bucket, closure_proof_class)
    else:
        state = TargetState(plan_value, normalized, resolved, True, kind, None, "archived_artifact", "archived_artifact")

    if cache is not None:
        cache[normalized] = state
    return state


def lint_followup_files(files: Iterable[FollowupFile], project_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    target_cache: dict[str, TargetState] = {}
    v2_identities: dict[tuple[str, str], FollowupItem] = {}
    v2_legacy_bridges: dict[tuple[str, str], FollowupItem] = {}
    for followup in files:
        schema_class, schema_findings = classify_followups_schema_version(followup)
        findings.extend(schema_findings)

        if schema_class == "v2":
            for malformed in followup.malformed_rows:
                findings.append(
                    Finding(
                        rel_path=malformed.rel_path,
                        line_no=malformed.line_no,
                        code="malformed_followup_row",
                        message=(
                            "Malformed V2 follow-up row under `## Follow-ups`: line looks like a backlog item "
                            "but does not match the required `- P? [ ] ...` grammar."
                        ),
                    )
                )
            for item in followup.items:
                findings.extend(lint_v2_item(item, project_root))
                bridge_identity = v2_legacy_bridge_identity(item)
                if bridge_identity is not None:
                    existing_bridge = v2_legacy_bridges.get(bridge_identity)
                    if existing_bridge is None:
                        v2_legacy_bridges[bridge_identity] = item
                    else:
                        findings.append(
                            _v2_finding(
                                item,
                                "v2_legacy_bridge_duplicate",
                                "Duplicate V2 legacy bridge identity; first row is "
                                f"{existing_bridge.rel_path}:{existing_bridge.line_no}.",
                            )
                        )
                source_ref = normalize_source_ref(item.source_ref)
                item_id = item.item_id
                if source_ref is None or item_id is None or not V2_ITEM_ID_RE.fullmatch(item_id):
                    continue
                identity = (source_ref, item_id)
                existing = v2_identities.get(identity)
                if existing is None:
                    v2_identities[identity] = item
                    continue
                findings.append(
                    _v2_finding(
                        item,
                        "v2_duplicate_tuple",
                        "Duplicate V2 `(source_ref,item_id)` tuple; first row is "
                        f"{existing.rel_path}:{existing.line_no}.",
                    )
                )
            continue

        if followup.is_done and not followup.imported_into:
            findings.append(
                Finding(
                    rel_path=followup.rel_path,
                    line_no=None,
                    code="missing_imported_into",
                    message="`**Status:** ✅ Done` требует `**Imported into:** ...` для cleanup-ready carrier.",
                )
            )
        if (
            followup.is_done
            and followup.imported_into
            and not followup.imported_refs
            and any((item.status or "").lower() in {"open", "promoted", "unconfirmed"} for item in followup.items)
        ):
            findings.append(
                Finding(
                    rel_path=followup.rel_path,
                    line_no=None,
                    code="imported_into_without_real_target_for_open_rows",
                    message=(
                        "`**Imported into:** N/A` не является real import target для open/promoted/UNCONFIRMED rows; "
                        "импортируй в master backlog или оставь файл Draft/pending."
                    ),
                )
            )

        for malformed in followup.malformed_rows:
            findings.append(
                Finding(
                    rel_path=malformed.rel_path,
                    line_no=malformed.line_no,
                    code="malformed_followup_row",
                    message=(
                        "Malformed follow-up row under `## Follow-ups`: line looks like a backlog item "
                        "but does not match the required `- P? [ ] ...` grammar."
                    ),
                )
            )

        for item in followup.items:
            missing_fields = [
                field
                for field in ("cluster", "to", "status", "plan", "why")
                if item.fields.get(field) is None
            ]
            if missing_fields:
                findings.append(
                    Finding(
                        rel_path=item.rel_path,
                        line_no=item.line_no,
                        code="missing_fields",
                        message=f"Missing required follow-up fields: {', '.join(missing_fields)}.",
                    )
                )

            if item.assignee is not None and item.assignee not in ALLOWED_ASSIGNEES:
                findings.append(
                    Finding(
                        rel_path=item.rel_path,
                        line_no=item.line_no,
                        code="invalid_assignee",
                        message=f"Unsupported `to=` value: {item.assignee!r}.",
                    )
                )

            if item.status is not None and item.status not in ALLOWED_ITEM_STATUSES:
                if item.status in PROCESS_IMPROVEMENT_ONLY_ITEM_STATUSES:
                    message = (
                        f"`status={item.status}` belongs to `docs/process_improvements/*` lifecycle rows, "
                        "not ordinary `docs/followups/*` rows. Allowed follow-up statuses: "
                        "`handled`, `open`, `promoted`, `unconfirmed`; use a process-improvement backlog row "
                        "or an explicit delivery follow-up with a backlink/delivery_refs bridge."
                    )
                else:
                    message = f"Unsupported `status=` value: {item.status!r}."
                findings.append(
                    Finding(
                        rel_path=item.rel_path,
                        line_no=item.line_no,
                        code="invalid_status",
                        message=message,
                    )
                )

            if is_placeholder_plan(item.plan):
                findings.append(
                    Finding(
                        rel_path=item.rel_path,
                        line_no=item.line_no,
                        code="placeholder_plan",
                        message="Placeholder future `plan=` path is forbidden; keep `plan=null` until real promote.",
                    )
                )

            if item.status != "promoted":
                continue

            if item.plan in (None, "null"):
                findings.append(
                    Finding(
                        rel_path=item.rel_path,
                        line_no=item.line_no,
                        code="missing_promoted_target",
                        message="`status=promoted` requires a real target in `plan=`.",
                    )
                )
                continue

            state = resolve_target_state(project_root, item.plan, target_cache)
            if not state.normalized.startswith(ACCEPTED_PROMOTE_TARGET_PREFIXES):
                findings.append(
                    Finding(
                        rel_path=item.rel_path,
                        line_no=item.line_no,
                        code="unsupported_promoted_target",
                        message=(
                            "`status=promoted` must point to `docs/plans/*`, `docs/reviews/*`, "
                            "`docs/code_reviews/*`, `docs/doc_reviews/*`, or `docs/code_drafts/*`."
                        ),
                    )
                )
                continue

            if state.bucket in {"missing", "unsupported", "placeholder"}:
                findings.append(
                    Finding(
                        rel_path=item.rel_path,
                        line_no=item.line_no,
                        code="broken_promoted_target",
                        message=f"`status=promoted` points to a missing or invalid target: {item.plan!r}.",
                    )
                )

    return findings


def record_for_item(item: FollowupItem, *, reason: str | None = None, target_state: TargetState | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "file": item.rel_path,
        "line": item.line_no,
        "priority": item.priority,
        "summary": item.summary,
        "cluster": item.cluster,
        "to": item.assignee,
        "status": item.status,
        "plan": item.plan,
        "why": item.why,
        "tags": list(item.tags),
        "item_id": item.item_id,
        "source_ref": normalize_source_ref(item.source_ref),
        "disposition_kind": item.disposition_kind,
        "disposition_ref": item.disposition_ref,
        "disposition_commit_oid": item.disposition_commit_oid,
        "reason_field": item.reason,
    }
    if reason is not None:
        payload["reason"] = reason
    if target_state is not None:
        payload["target_bucket"] = target_state.bucket
        payload["target_kind"] = target_state.kind
        payload["target_status"] = target_state.status_norm
        payload["target_path"] = target_state.normalized
        payload["target_closure_proof_class"] = target_state.closure_proof_class
    return payload


def is_v2_followup(followup: FollowupFile) -> bool:
    schema_class, _findings = classify_followups_schema_version(followup)
    return schema_class == "v2"


def ready_candidates(files: Iterable[FollowupFile]) -> list[FollowupItem]:
    return [
        item
        for followup in active_tracking_files(files)
        for item in followup.items
        if item.status == "open" and item.plan in (None, "null") and item.assignee != "owner"
    ]


def needs_owner_triage(files: Iterable[FollowupFile]) -> list[FollowupItem]:
    return [
        item
        for followup in active_tracking_files(files)
        for item in followup.items
        if item.assignee == "owner" or item.status == "unconfirmed"
    ]


def broken_plan_links(
    files: Iterable[FollowupFile],
    project_root: Path,
) -> list[dict[str, object]]:
    cache: dict[str, TargetState] = {}
    rows: list[dict[str, object]] = []
    for followup in active_tracking_files(files):
        for item in followup.items:
            if item.plan in (None, "null"):
                if item.status == "promoted":
                    rows.append(record_for_item(item, reason="missing_plan_target"))
                continue
            if is_placeholder_plan(item.plan):
                rows.append(record_for_item(item, reason="placeholder_plan"))
                continue
            state = resolve_target_state(project_root, item.plan, cache)
            if state.bucket in {"missing", "unsupported"}:
                rows.append(record_for_item(item, reason="broken_plan_link", target_state=state))
    return rows


def candidate_handled(
    files: Iterable[FollowupFile],
    project_root: Path,
) -> list[tuple[FollowupItem, TargetState]]:
    cache: dict[str, TargetState] = {}
    rows: list[tuple[FollowupItem, TargetState]] = []
    for followup in active_tracking_files(files):
        if is_v2_followup(followup):
            continue
        for item in followup.items:
            if item.status != "promoted" or item.plan in (None, "null"):
                continue
            state = resolve_target_state(project_root, item.plan, cache)
            if state.bucket == "done_plan" and state.closure_proof_class is not None:
                rows.append((item, state))
    return rows


def candidate_needs_closure_proof(
    files: Iterable[FollowupFile],
    project_root: Path,
) -> list[tuple[FollowupItem, TargetState]]:
    cache: dict[str, TargetState] = {}
    rows: list[tuple[FollowupItem, TargetState]] = []
    for followup in active_tracking_files(files):
        if is_v2_followup(followup):
            continue
        for item in followup.items:
            if item.status != "promoted" or item.plan in (None, "null"):
                continue
            state = resolve_target_state(project_root, item.plan, cache)
            if state.bucket == "done_plan" and state.closure_proof_class is None:
                rows.append((item, state))
    return rows


def stale_promoted(
    files: Iterable[FollowupFile],
    project_root: Path,
) -> list[tuple[FollowupItem, TargetState]]:
    cache: dict[str, TargetState] = {}
    rows: list[tuple[FollowupItem, TargetState]] = []
    for followup in active_tracking_files(files):
        if is_v2_followup(followup):
            continue
        for item in followup.items:
            if item.status != "promoted" or item.plan in (None, "null"):
                continue
            state = resolve_target_state(project_root, item.plan, cache)
            if state.bucket in {"stale_plan", "archived_artifact"}:
                rows.append((item, state))
    return rows


def cleanup_ready(files: Iterable[FollowupFile]) -> list[FollowupFile]:
    return [followup for followup in files if followup.is_done and followup.imported_refs]


def _read_existing_rel_path(project_root: Path, rel_path: str) -> str:
    path = (project_root / rel_path).resolve()
    if not path.exists() or not path.is_file():
        return ""
    return _read_text(path)


def _semantic_summaries_preserved(followup: FollowupFile, project_root: Path) -> tuple[bool, list[str]]:
    if not followup.items:
        return True, []
    imported_text = "\n".join(_read_existing_rel_path(project_root, rel_path) for rel_path in followup.imported_refs)
    missing = [item.summary for item in followup.items if item.summary and item.summary not in imported_text]
    return not missing, missing


def _scan_cleanup_reverse_references(
    followup: FollowupFile,
    project_root: Path,
) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    needle = followup.rel_path
    for root_rel in CLEANUP_REVERSE_REFERENCE_ROOTS:
        root = (project_root / root_rel).resolve()
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.md")):
            resolved = path.resolve()
            if resolved == followup.path:
                continue
            try:
                rel_path = resolved.relative_to(project_root).as_posix()
            except ValueError:
                continue
            for line_no, line in enumerate(_read_text(resolved).splitlines(), start=1):
                if needle not in line:
                    continue
                refs.append(
                    {
                        "file": rel_path,
                        "line": line_no,
                        "match": needle,
                    }
                )
    return refs


def _cleanup_item_refs(followup: FollowupFile, project_root: Path) -> list[dict[str, object]]:
    cache: dict[str, TargetState] = {}
    rows: list[dict[str, object]] = []
    for item in followup.items:
        row: dict[str, object] = {
            "line": item.line_no,
            "priority": item.priority,
            "summary": item.summary,
            "status": item.status,
            "source_status": item.status,
            "source_classification": item.cluster,
            "plan": item.plan,
            "why": item.why,
        }
        if item.plan not in (None, "null"):
            state = resolve_target_state(project_root, item.plan, cache)
            row["target_bucket"] = state.bucket
            row["target_kind"] = state.kind
            row["target_status"] = state.status_norm
            row["target_path"] = state.normalized
            row["proof_class"] = state.closure_proof_class
        rows.append(row)
    return rows


def _cleanup_terminal_refs(item_refs: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    terminal_buckets = {"done_plan", "stale_plan", "archived_artifact"}
    return [
        ref
        for ref in item_refs
        if ref.get("plan") not in (None, "null") and ref.get("target_bucket") in terminal_buckets
    ]


def _cleanup_preserved_summary(followup: FollowupFile) -> str:
    if not followup.items:
        return "No follow-up rows in source file."
    summaries = [item.summary for item in followup.items if item.summary]
    rendered = "; ".join(summaries)
    if len(rendered) <= 500:
        return rendered
    return rendered[:497].rstrip() + "..."


def cleanup_receipt_rows(files: Iterable[FollowupFile], project_root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for followup in cleanup_ready(files):
        item_refs = _cleanup_item_refs(followup, project_root)
        terminal_refs = _cleanup_terminal_refs(item_refs)
        semantic_preserved, missing_summaries = _semantic_summaries_preserved(followup, project_root)
        reverse_references = _scan_cleanup_reverse_references(followup, project_root)
        missing_proof_refs = [
            ref
            for ref in terminal_refs
            if ref.get("target_bucket") == "done_plan" and not ref.get("proof_class")
        ]
        reasons: list[str] = []

        if reverse_references:
            decision = "retain"
            reasons.append("reverse references remain")
        elif missing_proof_refs:
            decision = "needs-richer-summary"
            reasons.append("terminal plan refs need explicit closure proof class")
        elif not semantic_preserved:
            decision = "needs-richer-summary"
            reasons.append("semantic compression not proven in imported carriers")
        else:
            decision = "delete-ready"
            reasons.append("semantic summaries are preserved and no reverse references were found")

        if missing_summaries:
            reasons.append(f"missing summaries: {len(missing_summaries)}")

        rows.append(
            {
                "file": followup.rel_path,
                "source_path": followup.rel_path,
                "decision": decision,
                "status": followup.header_status,
                "items": len(followup.items),
                "item_refs": item_refs,
                "imported_into": list(followup.imported_refs),
                "imported_refs": list(followup.imported_refs),
                "promoted_or_handled_refs": [
                    ref for ref in item_refs if ref.get("plan") not in (None, "null")
                ],
                "terminal_proof": terminal_refs,
                "missing_proof_refs": missing_proof_refs,
                "source_statuses": sorted({str(ref.get("source_status")) for ref in item_refs if ref.get("source_status")}),
                "source_classifications": sorted(
                    {str(ref.get("source_classification")) for ref in item_refs if ref.get("source_classification")}
                ),
                "proof_classes": sorted({str(ref.get("proof_class")) for ref in item_refs if ref.get("proof_class")}),
                "reverse_references": reverse_references,
                "reverse_reference_count": len(reverse_references),
                "semantic_compression_preserved": semantic_preserved,
                "missing_summaries": missing_summaries,
                "preserved_summary": _cleanup_preserved_summary(followup),
                "reason": "; ".join(reasons),
                "reasons": reasons,
            }
        )
    return rows


def cleanup_receipt_decision_counts(rows: Iterable[dict[str, object]]) -> dict[str, int]:
    counts = {decision: 0 for decision in sorted(CLEANUP_RECEIPT_DECISIONS)}
    other = 0
    for row in rows:
        decision = str(row.get("decision") or "unknown")
        if decision in counts:
            counts[decision] += 1
            continue
        counts[decision] = counts.get(decision, 0) + 1
        other += 1
    counts["other"] = other
    return counts


def active_tracking_files(files: Iterable[FollowupFile]) -> list[FollowupFile]:
    return [followup for followup in files if followup.is_master or not followup.imported_refs]


def render_findings_text(findings: Iterable[Finding]) -> str:
    rendered = [finding.render() for finding in findings]
    if not rendered:
        return "followups-lint: OK"
    return "\n".join([*rendered, f"followups-lint: FAIL ({len(rendered)} findings)"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="followups_lint",
        description="Validate `docs/followups/*` backlog files and promoted-pointer semantics.",
    )
    parser.add_argument("paths", nargs="*", help="Optional followups files to lint (relative to `--project-root`).")
    parser.add_argument("--project-root", default="", help="Repo root that owns `docs/followups/*` (default: cwd).")
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    args = parser.parse_args(argv)

    project_root = resolve_project_root(args.project_root or None)
    try:
        files = load_followup_files(project_root, args.paths or None)
    except (OSError, ValueError) as exc:
        sys.stdout.write(f"followups-lint: FAIL (unsafe followups object: {exc})\n")
        return 1
    except Exception as exc:
        if exc.__class__.__module__ != "followups_capture":
            raise
        sys.stdout.write(f"followups-lint: FAIL (unsafe followups object: {exc})\n")
        return 1
    findings = lint_followup_files(files, project_root)

    if args.format == "json":
        payload = {
            "project_root": str(project_root),
            "files": [followup.rel_path for followup in files],
            "findings": [
                {
                    "file": finding.rel_path,
                    "line": finding.line_no,
                    "code": finding.code,
                    "message": finding.message,
                }
                for finding in findings
            ],
        }
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    else:
        sys.stdout.write(render_findings_text(findings) + "\n")

    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())

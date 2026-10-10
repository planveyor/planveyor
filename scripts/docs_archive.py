#!/usr/bin/env python3
"""
Local docs archive (SQLite FTS5) for temp artifacts that may be deleted from git.

Motivation:
- We delete `docs/plans/*` (and often related review artifacts) after merge.
- Git history is searchable, but it's slower/more awkward than local FTS for quick recall.
- Archive lives in `.tmp/` (gitignored) by default.

This is NOT the same as the derived docs index (`scripts/docs_index_build.py`):
- derived index is rebuildable from current files,
- archive DB is append-only and keeps deleted docs for later search.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import quote

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from portability_substitution import (
    GENERIC_PORTABILITY_RULES,
    PortabilityPolicyError,
    PortabilityRules,
    load_portability_rules,
    portabilize_text,
)


TOOL_VERSION = "1"
SCHEMA_VERSION = "1"

# IMPORTANT:
# This tool is executed from other repos via shell wrappers (`source scripts/planveyor.zsh`),
# so paths must be resolved relative to the current working directory (repo/worktree root),
# not relative to the tooling repo where this script lives.
REPO_ROOT = Path.cwd().resolve()

DEFAULT_DB = ".tmp/planveyor_docs_archive.sqlite"
DEFAULT_CHUNK_TARGET_TOKENS = 900
QUERY_PROFILE_SIGNAL_KINDS = ("plan", "code_review", "doc_review")
SNAPSHOT_FORMAT_VERSION = "1"
DEFAULT_SNAPSHOT_DIR = "docs/_meta/archive_snapshots/current"
SNAPSHOT_MANIFEST_NAME = "manifest.json"
SNAPSHOT_DOCS_JSONL_NAME = "archived_docs.jsonl"
SNAPSHOT_SQLITE_NAME = "archive.sqlite"
SNAPSHOT_BACKENDS = ("git_text_export", "git_whole_sqlite", "s3_minio_sqlite")
S3_BACKENDS = {"s3_minio_sqlite"}
SECRETISH_MANIFEST_KEYS = {
    "access_key",
    "access_key_id",
    "secret",
    "secret_access_key",
    "password",
    "token",
    "session_token",
}

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
FENCE_RE = re.compile(r"^\s*```")


def _utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _json_dumps_stable(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_dumps_pretty(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sqlite_fts5_self_check(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS __fts5_check USING fts5(x)")
        conn.execute("DROP TABLE __fts5_check")
    except sqlite3.OperationalError as e:
        sqlite_ver = getattr(sqlite3, "sqlite_version", "?")
        msg = str(e)
        raise RuntimeError(
            "SQLite FTS5 is not available in this Python/SQLite build.\n"
            f"- sqlite3.sqlite_version: {sqlite_ver}\n"
            f"- error: {msg}\n"
            "Tip: use a Python build linked with SQLite that has FTS5 enabled."
        ) from e


def _sqlite_uri_readonly(path: Path) -> str:
    abs_path = path.expanduser().resolve().as_posix()
    # Keep "/" safe for readability; escape spaces and other URI-unsafe chars.
    return f"file:{quote(abs_path, safe='/')}?mode=ro"


def _ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _meta_get(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return None if row is None else str(row[0])


def _meta_set(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS meta (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS archived_docs (
          doc_id INTEGER PRIMARY KEY,
          kind TEXT NOT NULL,
          original_path TEXT NOT NULL,
          sha256 TEXT NOT NULL,
          archived_at_utc TEXT NOT NULL,
          title TEXT NOT NULL,
          extra_json TEXT NOT NULL,
          content TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS archived_docs_uq_path_sha "
        "ON archived_docs(original_path, sha256)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS archived_docs_ix_path ON archived_docs(original_path)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS archived_docs_ix_kind ON archived_docs(kind)"
    )

    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS archived_chunks_fts USING fts5(
          doc_id UNINDEXED,
          kind UNINDEXED,
          original_path UNINDEXED,
          start_line UNINDEXED,
          heading,
          body,
          tokenize = 'porter'
        )
        """
    )

    existing_schema = _meta_get(conn, "schema_version")
    if existing_schema and existing_schema != SCHEMA_VERSION:
        raise RuntimeError(
            f"Unsupported archive DB schema_version={existing_schema} (expected {SCHEMA_VERSION}). "
            "Use a different --db or delete/recreate the archive DB."
        )

    _meta_set(conn, "schema_version", SCHEMA_VERSION)
    _meta_set(conn, "tool_version", TOOL_VERSION)


def estimate_tokens_chars4(text: str) -> int:
    # Very rough: ~4 chars/token heuristic.
    return max(1, len(text) // 4)


def _iter_markdown_sections(lines: list[str]) -> Iterable[tuple[str, list[tuple[int, str]]]]:
    """Yield (heading, section_lines_with_numbers)."""
    current_heading = "(preamble)"
    current: list[tuple[int, str]] = []
    in_code = False

    for i, line in enumerate(lines, start=1):
        if FENCE_RE.match(line):
            in_code = not in_code

        m = HEADING_RE.match(line) if not in_code else None
        if m:
            if current:
                yield (current_heading, current)
            current_heading = m.group(2).strip()
            current = [(i, line)]
        else:
            current.append((i, line))

    if current:
        yield (current_heading, current)


def _split_by_paragraphs(section: list[tuple[int, str]]) -> list[list[tuple[int, str]]]:
    # Deterministic paragraph split by blank lines.
    out: list[list[tuple[int, str]]] = []
    buf: list[tuple[int, str]] = []
    for ln, line in section:
        if not line.strip():
            if buf:
                out.append(buf)
                buf = []
            continue
        buf.append((ln, line))
    if buf:
        out.append(buf)
    return out


@dataclass(frozen=True)
class Chunk:
    start_line: int
    heading: str
    body: str


def chunks_for_markdown(text: str, *, chunk_target_tokens: int) -> list[Chunk]:
    lines = text.splitlines()
    out: list[Chunk] = []

    for heading, section in _iter_markdown_sections(lines):
        paragraphs = _split_by_paragraphs(section)
        if not paragraphs:
            continue

        cur: list[tuple[int, str]] = []
        for para in paragraphs:
            candidate = cur + para
            candidate_text = "\n".join(line for _, line in candidate).strip()
            if cur and estimate_tokens_chars4(candidate_text) > chunk_target_tokens:
                body = "\n".join(line for _, line in cur).strip()
                if body:
                    out.append(Chunk(start_line=int(cur[0][0]), heading=heading, body=body))
                cur = para
            else:
                cur = candidate

        if cur:
            body = "\n".join(line for _, line in cur).strip()
            if body:
                out.append(Chunk(start_line=int(cur[0][0]), heading=heading, body=body))

    return out


def _normalize_path(p: str) -> str:
    path = Path(p).expanduser()
    if not path.is_absolute():
        path = (REPO_ROOT / path).resolve()
    try:
        rel = path.relative_to(REPO_ROOT)
    except ValueError:
        return path.as_posix()
    return rel.as_posix()


def kind_for_path(original_path: str) -> str:
    p = original_path
    if p.startswith("docs/plans/"):
        return "plan"
    if p.startswith("docs/code_reviews/"):
        return "code_review"
    if p.startswith("docs/doc_reviews/"):
        return "doc_review"
    if p.startswith("docs/code_drafts/"):
        return "code_draft"
    if p.startswith("docs/followups/"):
        return "followup"
    if p.startswith("docs/snapshots/"):
        return "snapshot"
    if p.startswith("docs/reviews/"):
        return "review"
    return "misc"


def _title_from_text(text: str, fallback: str) -> str:
    for line in text.splitlines():
        m = HEADING_RE.match(line)
        if m and m.group(1) == "#":
            title = m.group(2).strip()
            if title:
                return title
            break
    return fallback


@dataclass(frozen=True)
class ArchiveStats:
    inserted: int
    skipped_existing: int
    missing: int


def archive_markdown_paths(
    conn: sqlite3.Connection,
    paths: list[str],
    *,
    db_label: str,
    chunk_target_tokens: int,
    extra_meta: dict | None,
    dry_run: bool,
    portability_rules: PortabilityRules = GENERIC_PORTABILITY_RULES,
) -> ArchiveStats:
    inserted = 0
    skipped_existing = 0
    missing = 0

    for raw in paths:
        original_path = _normalize_path(raw)
        disk_path = REPO_ROOT / original_path if not Path(original_path).is_absolute() else Path(original_path)
        if not disk_path.exists():
            missing += 1
            continue

        text = disk_path.read_text(encoding="utf-8", errors="replace")
        # Portabilize content at ingest so archived records carry portable paths,
        # not owner-local ones. Applied before the sha is derived so content and
        # sha (and the FTS chunks built from `text` below) stay consistent. This
        # closes the latent contamination vector noted in plan 260621_1204:301
        # (archive append had no portability awareness).
        text = portabilize_text(text, rules=portability_rules)
        sha = _sha256_hex(text)
        kind = kind_for_path(original_path)
        title = _title_from_text(text, fallback=Path(original_path).name)
        archived_at = _utc_now_iso()
        meta_obj = {
            "tool": "docs_archive",
            "tool_version": TOOL_VERSION,
            "schema_version": SCHEMA_VERSION,
            "db": db_label,
            "extra": extra_meta or {},
        }
        extra_json = _json_dumps_stable(meta_obj)

        row = conn.execute(
            "SELECT doc_id FROM archived_docs WHERE original_path = ? AND sha256 = ?",
            (original_path, sha),
        ).fetchone()
        if row is not None:
            skipped_existing += 1
            continue

        if dry_run:
            inserted += 1
            continue

        cur = conn.execute(
            """
            INSERT INTO archived_docs(kind, original_path, sha256, archived_at_utc, title, extra_json, content)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (kind, original_path, sha, archived_at, title, extra_json, text),
        )
        doc_id = int(cur.lastrowid)

        chunks = chunks_for_markdown(text, chunk_target_tokens=chunk_target_tokens)
        rows: list[tuple[str, str, str, str, str, str]] = []
        for ch in chunks:
            rows.append(
                (
                    str(doc_id),
                    kind,
                    original_path,
                    str(ch.start_line),
                    ch.heading,
                    ch.body,
                )
            )

        if rows:
            conn.executemany(
                "INSERT INTO archived_chunks_fts(doc_id, kind, original_path, start_line, heading, body) "
                "VALUES(?, ?, ?, ?, ?, ?)",
                rows,
            )

        inserted += 1

    return ArchiveStats(inserted=inserted, skipped_existing=skipped_existing, missing=missing)


def _ensure_db_ready(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("SELECT 1 FROM meta LIMIT 1")
        conn.execute("SELECT 1 FROM archived_docs LIMIT 1")
        conn.execute("SELECT 1 FROM archived_chunks_fts LIMIT 1")
    except sqlite3.OperationalError as e:
        msg = str(e).lower()
        if "no such module: fts5" in msg:
            sqlite_ver = getattr(sqlite3, "sqlite_version", "?")
            raise RuntimeError(
                "SQLite FTS5 is not available in this Python/SQLite build.\n"
                f"- sqlite3.sqlite_version: {sqlite_ver}\n"
                f"- error: {e}\n"
                "Tip: use a Python build linked with SQLite that has FTS5 enabled."
            ) from e
        raise RuntimeError(
            "Archive DB is missing required tables (meta/archived_docs/archived_chunks_fts). "
            "Initialize it via: scripts/docs_archive.py ingest ..."
        ) from e
    except sqlite3.Error as e:
        raise RuntimeError(
            "Archive DB is missing required tables (meta/archived_docs/archived_chunks_fts). "
            "Initialize it via: scripts/docs_archive.py ingest ..."
        ) from e


def _kind_counts(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        "SELECT kind, count(*) FROM archived_docs GROUP BY kind ORDER BY kind"
    ).fetchall()
    return {str(kind): int(count) for kind, count in rows}


def archive_db_summary(
    conn: sqlite3.Connection,
    *,
    db_path: Path,
    portability_rules: PortabilityRules = GENERIC_PORTABILITY_RULES,
) -> dict[str, object]:
    _ensure_db_ready(conn)
    counts_row = conn.execute(
        """
        SELECT
          count(*) AS docs_count,
          count(DISTINCT original_path) AS distinct_paths,
          -- UTF-8 BYTE length of content, not character count: SQLite length()
          -- on TEXT returns codepoints, but the field is named content_bytes.
          -- CAST(content AS BLOB) makes length() count bytes so name and value agree.
          coalesce(sum(length(CAST(content AS BLOB))), 0) AS content_bytes,
          min(archived_at_utc) AS archived_at_min_utc,
          max(archived_at_utc) AS archived_at_max_utc
        FROM archived_docs
        """
    ).fetchone()
    chunks_row = conn.execute("SELECT count(*) FROM archived_chunks_fts").fetchone()
    docs_count, distinct_paths, content_bytes, min_at, max_at = counts_row
    db_size = db_path.stat().st_size if db_path.exists() else 0
    return {
        # Portabilize the manifest-facing db_path so the snapshot manifest
        # does not embed an owner-local absolute path (the db_path here flows
        # into manifest.source_db.db_path). db_path (the Path object) is still
        # used above/below for the on-disk size/sha, which are machine-local
        # facts and intentionally not portabilized.
        "db_path": portabilize_text(db_path.as_posix(), rules=portability_rules),
        "db_size_bytes": int(db_size),
        "db_sha256": _sha256_file(db_path) if db_path.exists() else "",
        "schema_version": _meta_get(conn, "schema_version") or "unknown",
        "tool_version": _meta_get(conn, "tool_version") or "unknown",
        "docs_count": int(docs_count or 0),
        "chunks_count": int(chunks_row[0] or 0),
        "distinct_paths": int(distinct_paths or 0),
        "content_bytes": int(content_bytes or 0),
        "archived_at_min_utc": str(min_at or ""),
        "archived_at_max_utc": str(max_at or ""),
        "kind_counts": _kind_counts(conn),
    }


def _manifest_has_secretish_keys(value: object) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in SECRETISH_MANIFEST_KEYS:
                return True
            if _manifest_has_secretish_keys(child):
                return True
        return False
    if isinstance(value, list):
        return any(_manifest_has_secretish_keys(child) for child in value)
    return False


def _object_uri_has_inline_secret(uri: str) -> bool:
    # Object URIs with inline userinfo or presigned query params are not durable repo truth.
    uri_l = uri.lower()
    if re.search(r"://[^/?#\s]+:[^/?#\s]+@", uri):
        return True
    return any(token in uri_l for token in ("x-amz-", "signature=", "access_key", "secret"))


def _snapshot_relative_path(path: Path, *, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _snapshot_base_manifest(
    *,
    backend: str,
    source_summary: dict[str, object],
    created_at_utc: str | None = None,
) -> dict[str, object]:
    if backend not in SNAPSHOT_BACKENDS:
        raise ValueError(f"unsupported snapshot backend: {backend}")
    return {
        "snapshot_manifest_version": SNAPSHOT_FORMAT_VERSION,
        "storage_backend": backend,
        "created_at_utc": created_at_utc or _utc_now_iso(),
        "tool": "docs_archive",
        "tool_version": TOOL_VERSION,
        "schema_version": SCHEMA_VERSION,
        "stable_identity_fields": ["original_path", "kind", "sha256"],
        "source_db": source_summary,
        "restore": {
            "requires_original_tmp_db": False,
            "restores_to": "sqlite_fts5",
            "preconditions": ["python sqlite3 with FTS5"],
        },
    }


def _storage_matrix_for_manifest(
    *,
    source_summary: dict[str, object],
    text_artifact: Path | None,
    sqlite_artifact: Path | None,
    selected_backend: str,
) -> list[dict[str, object]]:
    source_size = int(source_summary.get("db_size_bytes") or 0)
    rows: list[dict[str, object]] = []
    if text_artifact is not None and text_artifact.exists():
        rows.append(
            {
                "backend": "git_text_export",
                "git_artifact": text_artifact.as_posix(),
                "size_bytes": text_artifact.stat().st_size,
                "fresh_clone_requirement": "git clone only",
                "selected": selected_backend == "git_text_export",
            }
        )
    else:
        rows.append(
            {
                "backend": "git_text_export",
                "size_bytes": None,
                "fresh_clone_requirement": "git clone only",
                "selected": selected_backend == "git_text_export",
            }
        )
    rows.append(
        {
            "backend": "git_whole_sqlite",
            "size_bytes": sqlite_artifact.stat().st_size if sqlite_artifact and sqlite_artifact.exists() else source_size,
            "fresh_clone_requirement": "git clone only",
            "selected": selected_backend == "git_whole_sqlite",
        }
    )
    rows.append(
        {
            "backend": "s3_minio_sqlite",
            "size_bytes": source_size,
            "fresh_clone_requirement": "git clone plus configured S3/MinIO object access",
            "selected": selected_backend == "s3_minio_sqlite",
            "access_behavior": "fail_closed_without_explicit_object_file_or_configured_downloader",
        }
    )
    return rows


def _iter_archived_doc_records(
    conn: sqlite3.Connection,
    *,
    portability_rules: PortabilityRules = GENERIC_PORTABILITY_RULES,
) -> Iterable[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT kind, original_path, sha256, archived_at_utc, title, extra_json, content
        FROM archived_docs
        ORDER BY kind, original_path, sha256
        """
    )
    for kind, original_path, sha, archived_at, title, extra_json, content in rows:
        yield _normalize_record_for_export(
            kind=kind,
            original_path=original_path,
            sha=sha,
            archived_at=archived_at,
            title=title,
            extra_json=extra_json,
            content=content,
            portability_rules=portability_rules,
        )


def _normalize_record_for_export(
    *,
    kind: object,
    original_path: object,
    sha: object,
    archived_at: object,
    title: object,
    extra_json: object,
    content: object,
    portability_rules: PortabilityRules = GENERIC_PORTABILITY_RULES,
) -> dict[str, object]:
    """Portabilize a record at the git_text_export chokepoint.

    Normalizes records for the JSONL emitted by ``export_git_text_snapshot``
    (via ``_iter_archived_doc_records``). Two fields are normalized so a dirty
    source DB cannot produce a dirty JSONL export:

    * ``content`` -> ``portabilize_text(content)``. ``sha256`` is ALWAYS
      recomputed from the portabilized content (unconditionally, not only when
      content changed) so a stale/garbage stored sha cannot survive into the
      export — the producer contract "content and sha must agree" is enforced
      at the chokepoint. For an already-portable record whose stored sha is
      already correct this is a no-op (idempotent).
    * ``extra_json.db`` -> portabilized via :func:`_normalize_extra_json_for_export`.

    SCOPE: this normalizes ONLY the git_text_export (JSONL) path. The
    git_whole_sqlite and s3_minio backends copy the source DB verbatim
    (``conn.backup``) and do NOT normalize — those backends are not currently
    selected, and a switch to them would need its own normalization gate.
    ``original_path``/``title`` are passed through unchanged (ingest's
    ``_normalize_path`` already makes original_path repo-relative).

    ``content``/``extra_json`` must be non-None strings (the archived_docs
    schema is NOT NULL); None is a contract violation surfaced as a TypeError
    rather than coerced to the literal "None".
    """
    if content is None or extra_json is None:
        raise TypeError(
            f"_normalize_record_for_export: content/extra_json must not be None "
            f"(original_path={original_path!r}); archived_docs schema is NOT NULL"
        )
    portabilized = portabilize_text(str(content), rules=portability_rules)
    # Unconditional recompute: the emitted sha is always the sha of the emitted
    # content, so a legacy/hand-edited stored sha can never leak into a record.
    final_sha = _sha256_hex(portabilized)
    return {
        "kind": str(kind),
        "original_path": str(original_path),
        "sha256": final_sha,
        "archived_at_utc": str(archived_at),
        "title": str(title),
        "extra_json": _normalize_extra_json_for_export(
            str(extra_json),
            portability_rules=portability_rules,
        ),
        "content": portabilized,
    }


def _normalize_extra_json_for_export(
    extra_json: str,
    *,
    portability_rules: PortabilityRules = GENERIC_PORTABILITY_RULES,
) -> str:
    """Portabilize extra_json.db at export time; leave non-JSON/missing intact.

    If extra_json parses as a JSON object with a ``db`` key, that key's value
    is run through :func:`portabilize_text` and the object re-serialized with
    the same stable settings as ingest (``_json_dumps_stable``). Any parse
    failure is returned verbatim so downstream JSONL validity checks surface
    it rather than silently rewriting unknown shapes.
    """
    if not extra_json:
        return extra_json
    try:
        meta = json.loads(extra_json)
    except (json.JSONDecodeError, TypeError):
        return extra_json
    if not isinstance(meta, dict) or "db" not in meta:
        return extra_json
    normalized = portabilize_text(str(meta["db"]), rules=portability_rules)
    if normalized == meta["db"]:
        return extra_json
    meta["db"] = normalized
    return _json_dumps_stable(meta)


@dataclass(frozen=True)
class SnapshotExportResult:
    backend: str
    manifest_path: Path
    artifact_path: Path | None
    docs_count: int
    artifact_size_bytes: int
    artifact_sha256: str


@dataclass(frozen=True)
class SnapshotRestoreResult:
    backend: str
    restored_docs: int
    skipped_existing: int
    query_hits: int | None = None


def _write_manifest(manifest_path: Path, manifest: dict[str, object], *, force: bool) -> None:
    if manifest_path.exists() and not force:
        raise RuntimeError(f"snapshot manifest already exists: {manifest_path} (pass --force)")
    _ensure_parent_dir(manifest_path)
    manifest_path.write_text(_json_dumps_pretty(manifest), encoding="utf-8")


def export_git_text_snapshot(
    conn: sqlite3.Connection,
    *,
    db_path: Path,
    output_dir: Path,
    force: bool,
    created_at_utc: str | None = None,
    portability_rules: PortabilityRules = GENERIC_PORTABILITY_RULES,
) -> SnapshotExportResult:
    _ensure_db_ready(conn)
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_path = output_dir / SNAPSHOT_DOCS_JSONL_NAME
    manifest_path = output_dir / SNAPSHOT_MANIFEST_NAME
    if docs_path.exists() and not force:
        raise RuntimeError(f"snapshot docs artifact already exists: {docs_path} (pass --force)")

    docs_count = 0
    with docs_path.open("w", encoding="utf-8") as f:
        for record in _iter_archived_doc_records(conn, portability_rules=portability_rules):
            f.write(_json_dumps_stable(record))
            f.write("\n")
            docs_count += 1

    source_summary = archive_db_summary(
        conn,
        db_path=db_path,
        portability_rules=portability_rules,
    )
    artifact_sha = _sha256_file(docs_path)
    manifest = _snapshot_base_manifest(
        backend="git_text_export",
        source_summary=source_summary,
        created_at_utc=created_at_utc,
    )
    manifest["artifact"] = {
        "path": docs_path.name,
        "size_bytes": docs_path.stat().st_size,
        "sha256": artifact_sha,
        "record_count": docs_count,
        "content_type": "application/x-jsonlines; charset=utf-8",
    }
    manifest["storage_matrix"] = _storage_matrix_for_manifest(
        source_summary=source_summary,
        text_artifact=docs_path,
        sqlite_artifact=None,
        selected_backend="git_text_export",
    )
    manifest["selection_reason"] = (
        "git_text_export selected: reviewable git-backed carrier; restore rebuilds SQLite/FTS "
        "without the original .tmp DB. Whole SQLite remains measured as source size; "
        "S3/MinIO remains optional and fail-closed without access."
    )
    _write_manifest(manifest_path, manifest, force=force)
    return SnapshotExportResult(
        backend="git_text_export",
        manifest_path=manifest_path,
        artifact_path=docs_path,
        docs_count=docs_count,
        artifact_size_bytes=docs_path.stat().st_size,
        artifact_sha256=artifact_sha,
    )


def export_git_whole_sqlite_snapshot(
    conn: sqlite3.Connection,
    *,
    db_path: Path,
    output_dir: Path,
    force: bool,
    created_at_utc: str | None = None,
    portability_rules: PortabilityRules = GENERIC_PORTABILITY_RULES,
) -> SnapshotExportResult:
    _ensure_db_ready(conn)
    output_dir.mkdir(parents=True, exist_ok=True)
    sqlite_path = output_dir / SNAPSHOT_SQLITE_NAME
    manifest_path = output_dir / SNAPSHOT_MANIFEST_NAME
    if sqlite_path.exists() and not force:
        raise RuntimeError(f"snapshot SQLite artifact already exists: {sqlite_path} (pass --force)")

    if sqlite_path.exists():
        sqlite_path.unlink()
    dest = sqlite3.connect(sqlite_path.as_posix())
    try:
        conn.backup(dest)
        dest.commit()
    finally:
        dest.close()

    source_summary = archive_db_summary(
        conn,
        db_path=db_path,
        portability_rules=portability_rules,
    )
    artifact_sha = _sha256_file(sqlite_path)
    manifest = _snapshot_base_manifest(
        backend="git_whole_sqlite",
        source_summary=source_summary,
        created_at_utc=created_at_utc,
    )
    manifest["artifact"] = {
        "path": sqlite_path.name,
        "size_bytes": sqlite_path.stat().st_size,
        "sha256": artifact_sha,
        "record_count": int(source_summary.get("docs_count") or 0),
        "content_type": "application/vnd.sqlite3",
    }
    manifest["storage_matrix"] = _storage_matrix_for_manifest(
        source_summary=source_summary,
        text_artifact=None,
        sqlite_artifact=sqlite_path,
        selected_backend="git_whole_sqlite",
    )
    manifest["selection_reason"] = (
        "git_whole_sqlite selected: simplest git-backed carrier; restore verifies schema/version, "
        "checksum and query readback. Binary churn must remain an explicit policy tradeoff."
    )
    _write_manifest(manifest_path, manifest, force=force)
    return SnapshotExportResult(
        backend="git_whole_sqlite",
        manifest_path=manifest_path,
        artifact_path=sqlite_path,
        docs_count=int(source_summary.get("docs_count") or 0),
        artifact_size_bytes=sqlite_path.stat().st_size,
        artifact_sha256=artifact_sha,
    )


def export_s3_minio_manifest(
    conn: sqlite3.Connection,
    *,
    db_path: Path,
    output_dir: Path,
    object_uri: str,
    object_sha256: str,
    object_size_bytes: int,
    force: bool,
    created_at_utc: str | None = None,
    portability_rules: PortabilityRules = GENERIC_PORTABILITY_RULES,
) -> SnapshotExportResult:
    _ensure_db_ready(conn)
    if not object_uri.strip():
        raise RuntimeError("--object-uri is required for s3_minio_sqlite")
    if _object_uri_has_inline_secret(object_uri):
        raise RuntimeError("object_uri appears to contain inline credentials or presigned secret material")
    if not re.fullmatch(r"[0-9a-f]{64}", object_sha256):
        raise RuntimeError("--object-sha256 must be a lowercase sha256 hex digest")
    if int(object_size_bytes) <= 0:
        raise RuntimeError("--object-size-bytes must be > 0")

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / SNAPSHOT_MANIFEST_NAME
    source_summary = archive_db_summary(
        conn,
        db_path=db_path,
        portability_rules=portability_rules,
    )
    manifest = _snapshot_base_manifest(
        backend="s3_minio_sqlite",
        source_summary=source_summary,
        created_at_utc=created_at_utc,
    )
    manifest["artifact"] = {
        "object_uri": object_uri,
        "size_bytes": int(object_size_bytes),
        "sha256": object_sha256,
        "record_count": int(source_summary.get("docs_count") or 0),
        "content_type": "application/vnd.sqlite3",
        "access_preflight": "restore requires explicit configured object access; no credentials in git",
    }
    manifest["storage_matrix"] = _storage_matrix_for_manifest(
        source_summary=source_summary,
        text_artifact=None,
        sqlite_artifact=None,
        selected_backend="s3_minio_sqlite",
    )
    manifest["selection_reason"] = (
        "s3_minio_sqlite selected: repo carries manifest/checksum only; fresh clone requires "
        "configured object-store access and restore fails closed without it."
    )
    _write_manifest(manifest_path, manifest, force=force)
    return SnapshotExportResult(
        backend="s3_minio_sqlite",
        manifest_path=manifest_path,
        artifact_path=None,
        docs_count=int(source_summary.get("docs_count") or 0),
        artifact_size_bytes=int(object_size_bytes),
        artifact_sha256=object_sha256,
    )


def load_snapshot_manifest(manifest_path: Path) -> dict[str, object]:
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise RuntimeError(f"snapshot manifest is not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise RuntimeError("snapshot manifest must be a JSON object")
    validate_snapshot_manifest(data, manifest_path=manifest_path, verify_artifact=False)
    return data


def validate_snapshot_manifest(
    manifest: dict[str, object],
    *,
    manifest_path: Path | None = None,
    verify_artifact: bool,
    object_file: Path | None = None,
) -> None:
    version = str(manifest.get("snapshot_manifest_version") or "")
    if version != SNAPSHOT_FORMAT_VERSION:
        raise RuntimeError(
            f"unsupported snapshot_manifest_version={version!r} (expected {SNAPSHOT_FORMAT_VERSION})"
        )
    backend = str(manifest.get("storage_backend") or "")
    if backend not in SNAPSHOT_BACKENDS:
        raise RuntimeError(f"unsupported storage_backend={backend!r}")
    if _manifest_has_secretish_keys(manifest):
        raise RuntimeError("snapshot manifest contains secret-like credential keys")
    artifact = manifest.get("artifact")
    if not isinstance(artifact, dict):
        raise RuntimeError("snapshot manifest missing artifact object")

    if backend in {"git_text_export", "git_whole_sqlite"}:
        rel_path = str(artifact.get("path") or "")
        if not rel_path:
            raise RuntimeError("git-backed snapshot manifest missing artifact.path")
        if Path(rel_path).is_absolute():
            raise RuntimeError("git-backed snapshot artifact.path must be relative to manifest")
        if verify_artifact:
            if manifest_path is None:
                raise RuntimeError("manifest_path is required for artifact verification")
            artifact_path = manifest_path.parent / rel_path
            if not artifact_path.exists():
                raise RuntimeError(f"snapshot artifact not found: {artifact_path}")
            expected_size = int(artifact.get("size_bytes") or -1)
            expected_sha = str(artifact.get("sha256") or "")
            if expected_size != artifact_path.stat().st_size:
                raise RuntimeError(
                    f"snapshot artifact size mismatch: expected {expected_size}, got {artifact_path.stat().st_size}"
                )
            if expected_sha != _sha256_file(artifact_path):
                raise RuntimeError("snapshot artifact checksum mismatch")
    elif backend in S3_BACKENDS:
        object_uri = str(artifact.get("object_uri") or "")
        expected_sha = str(artifact.get("sha256") or "")
        expected_size = int(artifact.get("size_bytes") or -1)
        if not object_uri:
            raise RuntimeError("s3_minio_sqlite manifest missing artifact.object_uri")
        if _object_uri_has_inline_secret(object_uri):
            raise RuntimeError("s3_minio_sqlite object_uri contains inline credentials or secret query")
        if not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
            raise RuntimeError("s3_minio_sqlite manifest artifact.sha256 must be lowercase sha256 hex")
        if expected_size <= 0:
            raise RuntimeError("s3_minio_sqlite manifest artifact.size_bytes must be > 0")
        if verify_artifact:
            if object_file is None:
                raise RuntimeError(
                    "s3_minio_sqlite restore requires --object-file or configured downloader; "
                    "failing closed without object-store access"
                )
            if not object_file.exists():
                raise RuntimeError(f"s3_minio_sqlite object file not found: {object_file}")
            if expected_size != object_file.stat().st_size:
                raise RuntimeError(
                    f"s3_minio_sqlite object size mismatch: expected {expected_size}, got {object_file.stat().st_size}"
                )
            if expected_sha != _sha256_file(object_file):
                raise RuntimeError("s3_minio_sqlite object checksum mismatch")


def _insert_archived_doc_record(
    conn: sqlite3.Connection,
    record: dict[str, object],
    *,
    chunk_target_tokens: int,
) -> bool:
    kind = str(record.get("kind") or "")
    original_path = str(record.get("original_path") or "")
    sha = str(record.get("sha256") or "")
    archived_at = str(record.get("archived_at_utc") or _utc_now_iso())
    title = str(record.get("title") or Path(original_path).name)
    extra_json = str(record.get("extra_json") or "{}")
    content = str(record.get("content") or "")
    if not kind or not original_path or not sha or not content:
        raise RuntimeError("snapshot record missing kind/original_path/sha256/content")
    if _sha256_hex(content) != sha:
        raise RuntimeError(f"snapshot record checksum mismatch for {original_path}")

    row = conn.execute(
        "SELECT doc_id FROM archived_docs WHERE original_path = ? AND sha256 = ?",
        (original_path, sha),
    ).fetchone()
    if row is not None:
        return False

    cur = conn.execute(
        """
        INSERT INTO archived_docs(kind, original_path, sha256, archived_at_utc, title, extra_json, content)
        VALUES(?, ?, ?, ?, ?, ?, ?)
        """,
        (kind, original_path, sha, archived_at, title, extra_json, content),
    )
    doc_id = int(cur.lastrowid)
    rows: list[tuple[str, str, str, str, str, str]] = []
    for ch in chunks_for_markdown(content, chunk_target_tokens=chunk_target_tokens):
        rows.append((str(doc_id), kind, original_path, str(ch.start_line), ch.heading, ch.body))
    if rows:
        conn.executemany(
            "INSERT INTO archived_chunks_fts(doc_id, kind, original_path, start_line, heading, body) "
            "VALUES(?, ?, ?, ?, ?, ?)",
            rows,
        )
    return True


def _restore_git_text_snapshot(
    *,
    manifest: dict[str, object],
    manifest_path: Path,
    dest_db: Path,
    replace: bool,
) -> SnapshotRestoreResult:
    validate_snapshot_manifest(manifest, manifest_path=manifest_path, verify_artifact=True)
    artifact = manifest["artifact"]
    assert isinstance(artifact, dict)
    docs_path = manifest_path.parent / str(artifact["path"])
    _ensure_parent_dir(dest_db)
    if replace and dest_db.exists():
        dest_db.unlink()
    conn = sqlite3.connect(dest_db.as_posix())
    inserted = 0
    skipped = 0
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        sqlite_fts5_self_check(conn)
        ensure_schema(conn)
        with docs_path.open("r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as e:
                    raise RuntimeError(f"invalid JSONL record at {docs_path}:{line_no}: {e}") from e
                if not isinstance(record, dict):
                    raise RuntimeError(f"invalid JSONL record at {docs_path}:{line_no}: expected object")
                if _insert_archived_doc_record(
                    conn,
                    record,
                    chunk_target_tokens=DEFAULT_CHUNK_TARGET_TOKENS,
                ):
                    inserted += 1
                else:
                    skipped += 1
        conn.commit()
    finally:
        conn.close()
    return SnapshotRestoreResult(
        backend="git_text_export",
        restored_docs=inserted,
        skipped_existing=skipped,
    )


def _restore_sqlite_snapshot_file(
    *,
    source_sqlite: Path,
    dest_db: Path,
    backend: str,
) -> SnapshotRestoreResult:
    _ensure_parent_dir(dest_db)
    if dest_db.exists():
        dest_db.unlink()
    src = sqlite3.connect(_sqlite_uri_readonly(source_sqlite), uri=True)
    try:
        _ensure_db_ready(src)
        docs_count = int(src.execute("SELECT count(*) FROM archived_docs").fetchone()[0])
        dest = sqlite3.connect(dest_db.as_posix())
        try:
            src.backup(dest)
            dest.commit()
        finally:
            dest.close()
    finally:
        src.close()
    return SnapshotRestoreResult(backend=backend, restored_docs=docs_count, skipped_existing=0)


def restore_snapshot_from_manifest(
    *,
    manifest_path: Path,
    dest_db: Path,
    object_file: Path | None = None,
    query: str | None = None,
    replace: bool = False,
) -> SnapshotRestoreResult:
    manifest = load_snapshot_manifest(manifest_path)
    backend = str(manifest["storage_backend"])
    if backend == "git_text_export":
        result = _restore_git_text_snapshot(
            manifest=manifest,
            manifest_path=manifest_path,
            dest_db=dest_db,
            replace=replace,
        )
    elif backend == "git_whole_sqlite":
        validate_snapshot_manifest(manifest, manifest_path=manifest_path, verify_artifact=True)
        artifact = manifest["artifact"]
        assert isinstance(artifact, dict)
        source_sqlite = manifest_path.parent / str(artifact["path"])
        result = _restore_sqlite_snapshot_file(
            source_sqlite=source_sqlite,
            dest_db=dest_db,
            backend=backend,
        )
    elif backend in S3_BACKENDS:
        validate_snapshot_manifest(
            manifest,
            manifest_path=manifest_path,
            verify_artifact=True,
            object_file=object_file,
        )
        assert object_file is not None
        result = _restore_sqlite_snapshot_file(
            source_sqlite=object_file,
            dest_db=dest_db,
            backend=backend,
        )
    else:
        raise RuntimeError(f"unsupported storage_backend={backend!r}")

    if query:
        conn = sqlite3.connect(_sqlite_uri_readonly(dest_db), uri=True)
        try:
            conn.execute("PRAGMA query_only = ON")
            hits = query_hits(conn, query=query, kinds=None, k=5)
        finally:
            conn.close()
        result = SnapshotRestoreResult(
            backend=result.backend,
            restored_docs=result.restored_docs,
            skipped_existing=result.skipped_existing,
            query_hits=len(hits),
        )
    return result


@dataclass(frozen=True)
class Hit:
    doc_id: int
    original_path: str
    start_line: int
    heading: str
    score: float
    excerpt: str


def _run_match_query(
    conn: sqlite3.Connection,
    *,
    query: str,
    kinds: tuple[str, ...] | None,
    k: int,
) -> list[tuple]:
    if kinds and len(kinds) == 1:
        return conn.execute(
            """
            SELECT
              doc_id,
              original_path,
              start_line,
              heading,
              bm25(archived_chunks_fts) AS score,
              snippet(archived_chunks_fts, 5, '[', ']', ' … ', 12) AS excerpt
            FROM archived_chunks_fts
            WHERE kind = ? AND archived_chunks_fts MATCH ?
            ORDER BY score
            LIMIT ?
            """,
            (kinds[0], query, int(k)),
        ).fetchall()
    if kinds:
        placeholders = ", ".join("?" for _ in kinds)
        sql = f"""
        SELECT
          doc_id,
          original_path,
          start_line,
          heading,
          bm25(archived_chunks_fts) AS score,
          snippet(archived_chunks_fts, 5, '[', ']', ' … ', 12) AS excerpt
        FROM archived_chunks_fts
        WHERE kind IN ({placeholders}) AND archived_chunks_fts MATCH ?
        ORDER BY score
        LIMIT ?
        """
        params: tuple[object, ...] = (*kinds, query, int(k))
        return conn.execute(sql, params).fetchall()
    return conn.execute(
        """
        SELECT
          doc_id,
          original_path,
          start_line,
          heading,
          bm25(archived_chunks_fts) AS score,
          snippet(archived_chunks_fts, 5, '[', ']', ' … ', 12) AS excerpt
        FROM archived_chunks_fts
        WHERE archived_chunks_fts MATCH ?
        ORDER BY score
        LIMIT ?
        """,
        (query, int(k)),
    ).fetchall()


def _fts_parse_error(err: sqlite3.OperationalError) -> bool:
    msg = str(err).lower()
    if "no such column" in msg:
        return True
    if "fts5" in msg and "syntax error" in msg:
        return True
    if "malformed match expression" in msg:
        return True
    if "unterminated string" in msg:
        return True
    return False


def _plain_text_to_fts_and_query(text: str) -> str:
    tokens = re.findall(r"\w+", text, flags=re.UNICODE)
    if not tokens:
        return ""
    quoted = ['"' + token.replace('"', '""') + '"' for token in tokens]
    return " AND ".join(quoted)


def query_hits(
    conn: sqlite3.Connection,
    *,
    query: str,
    kinds: tuple[str, ...] | None,
    k: int,
) -> list[Hit]:
    query_text = str(query).strip()
    if not query_text:
        return []

    try:
        rows = _run_match_query(conn, query=query_text, kinds=kinds, k=k)
    except sqlite3.OperationalError as e:
        if not _fts_parse_error(e):
            raise
        fallback_query = _plain_text_to_fts_and_query(query_text)
        if not fallback_query:
            return []
        rows = _run_match_query(conn, query=fallback_query, kinds=kinds, k=k)

    out: list[Hit] = []
    for doc_id, original_path, start_line, heading, score, excerpt in rows:
        try:
            start_i = int(str(start_line))
        except ValueError:
            start_i = 1
        out.append(
            Hit(
                doc_id=int(str(doc_id)),
                original_path=str(original_path),
                start_line=start_i,
                heading=str(heading or ""),
                score=float(score),
                excerpt=str(excerpt or "").replace("\n", " ").strip(),
            )
        )
    return out


def format_hits_human(hits: list[Hit]) -> str:
    lines: list[str] = []
    for i, h in enumerate(hits, start=1):
        jump = f"{h.original_path}:{h.start_line}"
        heading = h.heading.strip() or "(no heading)"
        lines.append(f"{i:>2}) {jump}  score={h.score:.3f}  doc_id={h.doc_id}  {heading}")
        if h.excerpt:
            lines.append(f"    {h.excerpt}")
    return "\n".join(lines)


def format_hits_md(hits: list[Hit]) -> str:
    lines: list[str] = []
    for h in hits:
        jump = f"{h.original_path}:{h.start_line}"
        heading = h.heading.strip() or "(no heading)"
        lines.append(f"- `{jump}` — {heading} (score={h.score:.3f}, doc_id={h.doc_id})")
        if h.excerpt:
            lines.append(f"  - {h.excerpt}")
    return "\n".join(lines)


def profile_kinds(profile: str | None) -> tuple[str, ...] | None:
    if not profile or profile == "all":
        return None
    if profile == "signal":
        return QUERY_PROFILE_SIGNAL_KINDS
    raise ValueError(f"unsupported profile: {profile}")


def _show_doc(conn: sqlite3.Connection, *, doc_id: int | None, path: str | None) -> int:
    if doc_id is None and not path:
        print("ERROR: provide --id or --path", file=sys.stderr)
        return 2

    if doc_id is not None:
        row = conn.execute(
            "SELECT doc_id, kind, original_path, sha256, archived_at_utc, title, extra_json, content "
            "FROM archived_docs WHERE doc_id = ?",
            (int(doc_id),),
        ).fetchone()
    else:
        norm = _normalize_path(str(path))
        row = conn.execute(
            "SELECT doc_id, kind, original_path, sha256, archived_at_utc, title, extra_json, content "
            "FROM archived_docs WHERE original_path = ? ORDER BY archived_at_utc DESC LIMIT 1",
            (norm,),
        ).fetchone()

    if row is None:
        print("ERROR: archived doc not found", file=sys.stderr)
        return 2

    doc_id2, kind, original_path, sha, archived_at, title, extra_json, content = row
    print(f"[planveyor] docs_archive show")
    print(f"- doc_id: {doc_id2}")
    print(f"- kind: {kind}")
    print(f"- original_path: {original_path}")
    print(f"- sha256: {sha}")
    print(f"- archived_at_utc: {archived_at}")
    print(f"- title: {title}")
    print(f"- extra_json: {extra_json}")
    print("")
    print(content)
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Local archive for deleted temp docs (SQLite FTS5).")
    parser.add_argument("--db", default=DEFAULT_DB, help=f"SQLite DB path (default: {DEFAULT_DB})")
    parser.add_argument(
        "--content-profile-id",
        default="default",
        choices=("default", "planveyor", "target-local"),
        help="Public content profile; normalization uses generic interpreter rules.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ingest = sub.add_parser("ingest", help="Archive markdown files into the DB (append-only).")
    p_ingest.add_argument(
        "--chunk-target-tokens",
        type=int,
        default=DEFAULT_CHUNK_TARGET_TOKENS,
        help=f"Approx token target per chunk (default: {DEFAULT_CHUNK_TARGET_TOKENS})",
    )
    p_ingest.add_argument("--dry-run", action="store_true", help="Compute stats but do not write to DB.")
    p_ingest.add_argument(
        "--extra-json",
        default="{}",
        help="Extra metadata JSON to store per archived doc (default: {}).",
    )
    p_ingest.add_argument("paths", nargs="+", help="File paths to archive (relative to repo root or absolute).")

    p_query = sub.add_parser("query", help="Search archived docs (FTS query).")
    p_query_filters = p_query.add_mutually_exclusive_group()
    p_query_filters.add_argument(
        "--kind",
        help="Filter by a single kind (plan/code_review/doc_review/code_draft/followup/snapshot/review/misc).",
    )
    p_query_filters.add_argument(
        "--profile",
        choices=["signal", "all"],
        help=(
            "Mixed-query profile: `signal` = plan+code_review+doc_review; "
            "`all` = current back-compat all-kinds mode."
        ),
    )
    p_query.add_argument("--k", type=int, default=12, help="Top-K results (default: 12)")
    p_query.add_argument("--md", action="store_true", help="Markdown-friendly output")
    p_query.add_argument("query", help="FTS query (falls back to plain text token AND query on parse errors).")

    p_show = sub.add_parser("show", help="Print full archived doc by id or path.")
    p_show.add_argument("--id", type=int, help="archived doc_id")
    p_show.add_argument("--path", help="original path (most recent archived version will be shown)")

    p_snapshot_info = sub.add_parser("snapshot-info", help="Print archive DB snapshot/readback facts.")
    p_snapshot_info.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    p_snapshot_export = sub.add_parser("snapshot-export", help="Export a portable archive snapshot.")
    p_snapshot_export.add_argument(
        "--backend",
        choices=SNAPSHOT_BACKENDS,
        default="git_text_export",
        help="Snapshot backend (default: git_text_export).",
    )
    p_snapshot_export.add_argument(
        "--output-dir",
        default=DEFAULT_SNAPSHOT_DIR,
        help=f"Snapshot output dir (default: {DEFAULT_SNAPSHOT_DIR}).",
    )
    p_snapshot_export.add_argument("--force", action="store_true", help="Overwrite existing snapshot files.")
    p_snapshot_export.add_argument(
        "--created-at-utc",
        help="Override manifest timestamp for deterministic tests (YYYY-MM-DDTHH:MM:SSZ).",
    )
    p_snapshot_export.add_argument("--object-uri", help="S3/MinIO object URI for s3_minio_sqlite manifest.")
    p_snapshot_export.add_argument("--object-sha256", help="S3/MinIO object sha256 for s3_minio_sqlite manifest.")
    p_snapshot_export.add_argument(
        "--object-size-bytes",
        type=int,
        help="S3/MinIO object size for s3_minio_sqlite manifest.",
    )

    p_snapshot_validate = sub.add_parser("snapshot-validate", help="Validate a snapshot manifest/artifact.")
    p_snapshot_validate.add_argument("--manifest", required=True, help="Snapshot manifest JSON path.")
    p_snapshot_validate.add_argument(
        "--object-file",
        help="Local object file for selected s3_minio_sqlite artifact validation.",
    )
    p_snapshot_validate.add_argument(
        "--verify-artifact",
        action="store_true",
        help="Verify artifact size/checksum, not only manifest shape.",
    )

    p_snapshot_restore = sub.add_parser("snapshot-restore", help="Restore archive snapshot into a temp/local DB.")
    p_snapshot_restore.add_argument("--manifest", required=True, help="Snapshot manifest JSON path.")
    p_snapshot_restore.add_argument("--dest-db", required=True, help="Destination SQLite archive DB path.")
    p_snapshot_restore.add_argument(
        "--object-file",
        help="Local object file for selected s3_minio_sqlite restore.",
    )
    p_snapshot_restore.add_argument("--query", help="Optional query/readback after restore.")
    p_snapshot_restore.add_argument(
        "--expect-min-hits",
        type=int,
        default=0,
        help="Fail if --query returns fewer hits than this value.",
    )
    p_snapshot_restore.add_argument(
        "--replace",
        action="store_true",
        help="Replace destination DB before restore.",
    )

    args = parser.parse_args(argv)
    try:
        portability_rules = load_portability_rules(content_profile_id=args.content_profile_id)
    except PortabilityPolicyError as e:
        print(f"ERROR: portability policy invalid: {e}", file=sys.stderr)
        return 2
    db_path = Path(args.db)

    cmd_requires_existing_db = args.cmd in {"query", "show", "snapshot-info", "snapshot-export"}
    if cmd_requires_existing_db and not db_path.exists():
        print(f"ERROR: archive DB not found: {db_path}", file=sys.stderr)
        return 2

    if args.cmd == "ingest":
        _ensure_parent_dir(db_path)
        conn = sqlite3.connect(db_path.as_posix())
    elif cmd_requires_existing_db:
        conn = sqlite3.connect(_sqlite_uri_readonly(db_path), uri=True)
    else:
        conn = None
    try:
        if conn is not None:
            conn.execute("PRAGMA foreign_keys = ON")
        if args.cmd == "ingest":
            assert conn is not None
            conn.execute("PRAGMA journal_mode = WAL")
            sqlite_fts5_self_check(conn)
            ensure_schema(conn)
        elif conn is not None:
            conn.execute("PRAGMA query_only = ON")

        if args.cmd == "ingest":
            assert conn is not None
            chunk_target_tokens = int(args.chunk_target_tokens)
            if chunk_target_tokens <= 0:
                print("ERROR: --chunk-target-tokens must be > 0", file=sys.stderr)
                return 2
            try:
                extra_meta = json.loads(str(args.extra_json))
            except json.JSONDecodeError as e:
                print(f"ERROR: --extra-json is not valid JSON: {e}", file=sys.stderr)
                return 2
            if extra_meta is None:
                extra_meta = {}

            paths = [str(p) for p in args.paths]
            # Portabilize the db_label so records carry a portable path in
            # extra_json.db from the moment they are stored. Defense in depth:
            # archive_db_summary portabilizes manifest.source_db.db_path, and
            # _iter_archived_doc_records re-portabilizes extra_json.db at export
            # time, so the snapshot cannot reintroduce a leak even if the source
            # DB holds pre-fix records. Mirrors the content portabilization at
            # line 345.
            stats = archive_markdown_paths(
                conn,
                paths,
                db_label=portabilize_text(db_path.as_posix(), rules=portability_rules),
                chunk_target_tokens=chunk_target_tokens,
                extra_meta=extra_meta if isinstance(extra_meta, dict) else {"extra_json_raw": str(args.extra_json)},
                dry_run=bool(args.dry_run),
                portability_rules=portability_rules,
            )
            if not args.dry_run:
                conn.commit()

            print("[planveyor] docs_archive ingest")
            print(f"- db: {db_path}")
            print(f"- inserted: {stats.inserted}")
            print(f"- skipped_existing: {stats.skipped_existing}")
            print(f"- missing_on_disk: {stats.missing}")
            return 0

        if args.cmd == "query":
            assert conn is not None
            try:
                _ensure_db_ready(conn)
            except RuntimeError as e:
                print(f"ERROR: {e}", file=sys.stderr)
                return 2
            profile = str(args.profile) if getattr(args, "profile", None) else None
            kind = str(args.kind) if args.kind else None
            kinds = (kind,) if kind else profile_kinds(profile)
            hits = query_hits(conn, query=str(args.query), kinds=kinds, k=int(args.k))
            if kind:
                filter_desc = f"kind={kind}"
            elif profile:
                if kinds:
                    filter_desc = f"profile={profile} ({','.join(kinds)})"
                else:
                    filter_desc = f"profile={profile}"
            else:
                filter_desc = "profile=all (back-compat default)"
            header = f"docs_archive query (db={db_path}, {filter_desc}, k={int(args.k)}, hits={len(hits)})"
            print(header)
            if not hits:
                return 0
            print("")
            if bool(args.md):
                print(format_hits_md(hits))
            else:
                print(format_hits_human(hits))
            print("")
            print("Tip: show full doc:")
            print(f"  python3 scripts/docs_archive.py --db {db_path} show --id <doc_id>")
            return 0

        if args.cmd == "show":
            assert conn is not None
            try:
                _ensure_db_ready(conn)
            except RuntimeError as e:
                print(f"ERROR: {e}", file=sys.stderr)
                return 2
            return _show_doc(conn, doc_id=args.id, path=args.path)

        if args.cmd == "snapshot-info":
            assert conn is not None
            try:
                summary = archive_db_summary(
                    conn,
                    db_path=db_path,
                    portability_rules=portability_rules,
                )
            except RuntimeError as e:
                print(f"ERROR: {e}", file=sys.stderr)
                return 2
            if bool(args.json):
                print(_json_dumps_pretty(summary), end="")
            else:
                print("[planveyor] docs_archive snapshot-info")
                print(f"- db: {db_path}")
                print(f"- schema_version: {summary['schema_version']}")
                print(f"- db_size_bytes: {summary['db_size_bytes']}")
                print(f"- db_sha256: {summary['db_sha256']}")
                print(f"- docs_count: {summary['docs_count']}")
                print(f"- chunks_count: {summary['chunks_count']}")
                print(f"- distinct_paths: {summary['distinct_paths']}")
                print(f"- content_bytes: {summary['content_bytes']}")
                print(f"- archived_range_utc: {summary['archived_at_min_utc']}..{summary['archived_at_max_utc']}")
                print(f"- kind_counts: {_json_dumps_stable(summary['kind_counts'])}")
            return 0

        if args.cmd == "snapshot-export":
            assert conn is not None
            try:
                backend = str(args.backend)
                if backend == "git_text_export":
                    result = export_git_text_snapshot(
                        conn,
                        db_path=db_path,
                        output_dir=Path(str(args.output_dir)),
                        force=bool(args.force),
                        created_at_utc=args.created_at_utc,
                        portability_rules=portability_rules,
                    )
                elif backend == "git_whole_sqlite":
                    result = export_git_whole_sqlite_snapshot(
                        conn,
                        db_path=db_path,
                        output_dir=Path(str(args.output_dir)),
                        force=bool(args.force),
                        created_at_utc=args.created_at_utc,
                        portability_rules=portability_rules,
                    )
                elif backend == "s3_minio_sqlite":
                    result = export_s3_minio_manifest(
                        conn,
                        db_path=db_path,
                        output_dir=Path(str(args.output_dir)),
                        object_uri=str(args.object_uri or ""),
                        object_sha256=str(args.object_sha256 or ""),
                        object_size_bytes=int(args.object_size_bytes or 0),
                        force=bool(args.force),
                        created_at_utc=args.created_at_utc,
                        portability_rules=portability_rules,
                    )
                else:
                    print(f"ERROR: unsupported snapshot backend: {backend}", file=sys.stderr)
                    return 2
            except RuntimeError as e:
                print(f"ERROR: {e}", file=sys.stderr)
                return 2
            print("[planveyor] docs_archive snapshot-export")
            print(f"- backend: {result.backend}")
            print(f"- manifest: {result.manifest_path}")
            if result.artifact_path is not None:
                print(f"- artifact: {result.artifact_path}")
            print(f"- docs_count: {result.docs_count}")
            print(f"- artifact_size_bytes: {result.artifact_size_bytes}")
            print(f"- artifact_sha256: {result.artifact_sha256}")
            return 0

        if args.cmd == "snapshot-validate":
            manifest_path = Path(str(args.manifest))
            object_file = Path(str(args.object_file)) if args.object_file else None
            try:
                manifest = load_snapshot_manifest(manifest_path)
                validate_snapshot_manifest(
                    manifest,
                    manifest_path=manifest_path,
                    verify_artifact=bool(args.verify_artifact),
                    object_file=object_file,
                )
            except RuntimeError as e:
                print(f"ERROR: {e}", file=sys.stderr)
                return 2
            print("[planveyor] docs_archive snapshot-validate")
            print(f"- manifest: {manifest_path}")
            print(f"- storage_backend: {manifest['storage_backend']}")
            print(f"- verify_artifact: {str(bool(args.verify_artifact)).lower()}")
            print("- result: OK")
            return 0

        if args.cmd == "snapshot-restore":
            object_file = Path(str(args.object_file)) if args.object_file else None
            try:
                result = restore_snapshot_from_manifest(
                    manifest_path=Path(str(args.manifest)),
                    dest_db=Path(str(args.dest_db)),
                    object_file=object_file,
                    query=str(args.query) if args.query else None,
                    replace=bool(args.replace),
                )
            except RuntimeError as e:
                print(f"ERROR: {e}", file=sys.stderr)
                return 2
            if args.query and int(args.expect_min_hits) > 0:
                restored_query_hits = int(result.query_hits or 0)
                if restored_query_hits < int(args.expect_min_hits):
                    print(
                        f"ERROR: snapshot restore query returned {restored_query_hits} hits "
                        f"(expected at least {int(args.expect_min_hits)})",
                        file=sys.stderr,
                    )
                    return 2
            print("[planveyor] docs_archive snapshot-restore")
            print(f"- backend: {result.backend}")
            print(f"- dest_db: {args.dest_db}")
            print(f"- restored_docs: {result.restored_docs}")
            print(f"- skipped_existing: {result.skipped_existing}")
            if args.query:
                print(f"- query_hits: {result.query_hits}")
            print("- result: OK")
            return 0

        print("ERROR: unsupported command", file=sys.stderr)
        return 2
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

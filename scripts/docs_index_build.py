#!/usr/bin/env python3
"""
Build a local, derived docs retrieval index using SQLite FTS5.

Goals:
- Offline, deterministic, rebuildable.
- Three corpuses:
  - canon: docs/** excluding noisy dirs + docs/plans/** + docs/followups/**
  - followups: docs/followups/** excluding template
  - plans: docs/plans/** excluding template/readme
- In repositories with i18n/pairs.json, Russian copies `*.ru.md` are not indexed
  in any corpus (read them by explicit path).
- Default DB is per-worktree (in .tmp/). Shared DB only via explicit --db.
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
from typing import Iterable, Iterator


TOOL_VERSION = "1"
SCHEMA_VERSION = "1"

DEFAULT_DB = ".tmp/planveyor_docs_index.sqlite"
DEFAULT_ROOT = "docs"
DEFAULT_CHUNK_TARGET_TOKENS = 900


CANON_EXCLUDE_PREFIXES = (
    "docs/plans/",
    "docs/followups/",
    "docs/reviews/",
    "docs/code_reviews/",
    "docs/doc_reviews/",
    "docs/snapshots/",
)

FOLLOWUPS_INCLUDE_PREFIX = "docs/followups/"
FOLLOWUPS_EXCLUDE_FILES = {"docs/followups/_template_followups_backlog.md"}
PLANS_INCLUDE_PREFIX = "docs/plans/"
PLANS_EXCLUDE_FILES = {"docs/plans/_template.md", "docs/plans/README.md"}
# A human document `name.md` may have a Russian copy `name.ru.md` next to it.
# In a target that opts in through i18n/pairs.json, search must not hand roles
# both versions; an explicit read by path still opens copies.
TRANSLATION_COPY_SUFFIXES = (".ru.md",)


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
FENCE_RE = re.compile(r"^\s*```")
TASK_RE = re.compile(r"^(\s*)-\s+(.*\S)\s*$")
CHECKBOX_PREFIX_RE = re.compile(r"^\[\s*[xX ]\s*\]\s+")


def estimate_tokens_chars4(text: str) -> int:
    # Very rough: ~4 chars/token heuristic.
    return max(1, len(text) // 4)


def _ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _json_dumps_stable(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def translation_copy_suffixes(project_root: Path | None = None) -> tuple[str, ...]:
    # Match doc_lint's target-local registry opt-in. Invalid JSON or a broken
    # symlink must not silently turn the copy filter off; doc_lint diagnoses it.
    registry = (project_root or Path.cwd()).resolve() / "i18n/pairs.json"
    return TRANSLATION_COPY_SUFFIXES if registry.exists() or registry.is_symlink() else ()


def corpus_rules(corpus: str, root: str, chunk_target_tokens: int, *, project_root: Path | None = None) -> dict:
    # Backward-compat helper (kept small): returns an index-level config
    # (same for all corpuses). The per-corpus build chooses the file list + chunking,
    # but the fingerprint must remain stable across canon/followups/plans builds.
    if corpus not in {"canon", "followups", "plans"}:
        raise ValueError(f"Unsupported corpus: {corpus}")
    rules = {
        "tool_version": TOOL_VERSION,
        "schema_version": SCHEMA_VERSION,
        "root": root,
        "chunk_target_tokens": int(chunk_target_tokens),
        "canon": {
            "exclude_prefixes": list(CANON_EXCLUDE_PREFIXES),
        },
        "followups": {
            "include_prefix": FOLLOWUPS_INCLUDE_PREFIX,
            "exclude_files": sorted(FOLLOWUPS_EXCLUDE_FILES),
        },
        "plans": {
            "include_prefix": PLANS_INCLUDE_PREFIX,
            "exclude_files": sorted(PLANS_EXCLUDE_FILES),
        },
    }
    suffixes = translation_copy_suffixes(project_root)
    if suffixes:
        rules["exclude_suffixes"] = list(suffixes)
    return rules


def compute_fingerprint(rules: dict) -> str:
    # Fingerprint only depends on stable params that affect the index.
    return _sha256_hex(_json_dumps_stable(rules))


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
        CREATE VIRTUAL TABLE IF NOT EXISTS doc_chunks_fts USING fts5(
          corpus UNINDEXED,
          path UNINDEXED,
          start_line UNINDEXED,
          heading,
          body,
          tokenize = 'porter'
        )
        """
    )


def _meta_get(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return None if row is None else str(row[0])


def _meta_set(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


def read_index_config(conn: sqlite3.Connection) -> dict:
    schema = _meta_get(conn, "schema_version")
    if schema != SCHEMA_VERSION:
        raise RuntimeError(f"Unsupported or missing index schema_version={schema!r}; rebuild the index.")
    config_json = _meta_get(conn, "index_config_json")
    legacy_json = _meta_get(conn, "corpus_rules_json")
    try:
        config = json.loads(config_json or legacy_json or "null")
    except (ValueError, TypeError) as e:
        raise RuntimeError("Index config is invalid; rebuild the index.") from e
    if not isinstance(config, dict):
        raise RuntimeError("Index config is missing or invalid; rebuild the index.")
    fingerprint = _meta_get(conn, "fingerprint")
    if not fingerprint or fingerprint != compute_fingerprint(config):
        raise RuntimeError("Index fingerprint mismatch with stored config; rebuild the index.")
    if not isinstance(config.get("root"), str) or not config["root"]:
        raise RuntimeError("Index config has an invalid root; rebuild the index.")
    tokens = config.get("chunk_target_tokens")
    if type(tokens) is not int or tokens <= 0:
        raise RuntimeError("Index config has invalid chunk_target_tokens; rebuild the index.")
    if not config_json:
        config.pop("corpus", None)
    return config


def validate_index_config(conn: sqlite3.Connection, *, rules: dict) -> bool:
    """Validate current/known older rules; return whether copy pruning is needed."""
    existing = read_index_config(conn)
    normalized = dict(existing)
    # Existing backwards-compatible, additive plans-corpus migration.
    if "plans" not in normalized:
        normalized["plans"] = rules["plans"]
    prune_copies = "exclude_suffixes" not in normalized and "exclude_suffixes" in rules
    if prune_copies:
        normalized["exclude_suffixes"] = rules["exclude_suffixes"]
    if compute_fingerprint(normalized) != compute_fingerprint(rules):
        raise RuntimeError(
            "Index fingerprint mismatch.\n"
            f"- db fingerprint: {_meta_get(conn, 'fingerprint')}\n"
            f"- expected: {compute_fingerprint(rules)}\n"
            "Rebuild with --force-rebuild or use a different --db."
        )
    return prune_copies


def init_or_validate_meta(conn: sqlite3.Connection, *, rules: dict, fingerprint: str, force_rebuild: bool) -> bool:
    populated = conn.execute("SELECT 1 FROM meta LIMIT 1").fetchone() or conn.execute(
        "SELECT 1 FROM doc_chunks_fts LIMIT 1"
    ).fetchone()
    prune_copies = False
    if populated and not force_rebuild:
        prune_copies = validate_index_config(conn, rules=rules)
        if prune_copies:
            # This exact rule only removes derived rows. Apply it to every
            # corpus before updating the shared fingerprint, even when the
            # caller requested just one corpus. Other rows remain untouched.
            corpuses = {str(row[0]) for row in conn.execute("SELECT DISTINCT corpus FROM doc_chunks_fts")}
            for suffix in rules["exclude_suffixes"]:
                conn.execute("DELETE FROM doc_chunks_fts WHERE path GLOB ?", ("*" + suffix,))
            for corpus in ("canon", "followups", "plans"):
                if corpus in corpuses or _meta_get(conn, f"built_at_utc.{corpus}") is not None:
                    files, chunks = conn.execute(
                        "SELECT count(DISTINCT path), count(*) FROM doc_chunks_fts WHERE corpus = ?", (corpus,)
                    ).fetchone()
                    _meta_set(conn, f"files_total.{corpus}", str(files))
                    _meta_set(conn, f"chunks_total.{corpus}", str(chunks))

    _meta_set(conn, "schema_version", SCHEMA_VERSION)
    _meta_set(conn, "tool_version", TOOL_VERSION)
    _meta_set(conn, "fingerprint", fingerprint)
    _meta_set(conn, "index_config_json", _json_dumps_stable(rules))
    return prune_copies


@dataclass(frozen=True)
class Chunk:
    corpus: str
    path: str
    start_line: int
    heading: str
    body: str


def iter_files_for_corpus(*, corpus: str, root: Path) -> Iterator[Path]:
    suffixes = translation_copy_suffixes()
    for path in sorted(root.rglob("*.md")):
        rel = path.as_posix()
        if path.name.endswith(suffixes):
            continue
        if corpus == "canon":
            if any(rel.startswith(prefix) for prefix in CANON_EXCLUDE_PREFIXES):
                continue
            yield path
        elif corpus == "followups":
            if not rel.startswith(FOLLOWUPS_INCLUDE_PREFIX):
                continue
            if rel in FOLLOWUPS_EXCLUDE_FILES:
                continue
            yield path
        elif corpus == "plans":
            if not rel.startswith(PLANS_INCLUDE_PREFIX):
                continue
            if rel in PLANS_EXCLUDE_FILES:
                continue
            yield path
        else:
            raise ValueError(f"Unsupported corpus: {corpus}")


def _iter_markdown_sections(lines: list[str]) -> Iterator[tuple[str, list[tuple[int, str]]]]:
    # Returns (heading, section_lines_with_numbers), deterministic.
    sections: list[tuple[str, list[tuple[int, str]]]] = []
    current_heading = "(preamble)"
    current: list[tuple[int, str]] = []
    in_code = False

    for i, line in enumerate(lines, start=1):
        if FENCE_RE.match(line):
            in_code = not in_code

        m = HEADING_RE.match(line) if not in_code else None
        if m:
            if current:
                sections.append((current_heading, current))
            current_heading = m.group(2).strip()
            current = [(i, line)]
        else:
            current.append((i, line))

    if current:
        sections.append((current_heading, current))

    yield from sections


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


def chunks_for_canon(path: Path, *, chunk_target_tokens: int) -> list[Chunk]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []

    rel = path.as_posix()
    lines = text.splitlines()

    chunks: list[Chunk] = []
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
                    chunks.append(
                        Chunk(
                            corpus="canon",
                            path=rel,
                            start_line=int(cur[0][0]),
                            heading=heading,
                            body=body,
                        )
                    )
                cur = para
            else:
                cur = candidate

        if cur:
            body = "\n".join(line for _, line in cur).strip()
            if body:
                chunks.append(
                    Chunk(
                        corpus="canon",
                        path=rel,
                        start_line=int(cur[0][0]),
                        heading=heading,
                        body=body,
                    )
                )

    return chunks


def _task_summary(raw: str, max_len: int = 90) -> str:
    s = raw.strip()
    s = CHECKBOX_PREFIX_RE.sub("", s).strip()
    s = re.sub(r"\s+", " ", s)
    if len(s) <= max_len:
        return s
    return s[: max_len - 1].rstrip() + "…"


def chunks_for_followups(path: Path) -> list[Chunk]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []

    rel = path.as_posix()
    lines = text.splitlines()
    numbered = list(enumerate(lines, start=1))

    chunks: list[Chunk] = []
    current_heading = "(no heading)"
    in_code = False

    task_indent: int | None = None
    task_start_line: int | None = None
    task_lines: list[str] = []
    task_raw_first: str | None = None

    def flush_task() -> None:
        nonlocal task_indent, task_start_line, task_lines, task_raw_first
        if task_start_line is None:
            return
        body = "\n".join(task_lines).strip()
        if not body:
            task_indent = None
            task_start_line = None
            task_lines = []
            task_raw_first = None
            return

        task_title = _task_summary(task_raw_first or body.splitlines()[0])
        heading = f"{current_heading}: {task_title}" if current_heading else task_title
        chunks.append(
            Chunk(
                corpus="followups",
                path=rel,
                start_line=int(task_start_line),
                heading=heading,
                body=body,
            )
        )

        task_indent = None
        task_start_line = None
        task_lines = []
        task_raw_first = None

    for ln, line in numbered:
        if FENCE_RE.match(line):
            in_code = not in_code

        if not in_code:
            m_h = HEADING_RE.match(line)
            if m_h:
                flush_task()
                current_heading = m_h.group(2).strip()
                continue

            m_t = TASK_RE.match(line)
            if m_t:
                indent = len(m_t.group(1) or "")
                raw = m_t.group(2)
                # New task starts on same or lower indent.
                if task_indent is None or indent <= task_indent:
                    flush_task()
                    task_indent = indent
                    task_start_line = ln
                    task_lines = [line]
                    task_raw_first = raw
                    continue

        # Continuations (only if indented deeper than the bullet indent; blanks are allowed).
        if task_indent is not None and task_start_line is not None:
            if not line.strip():
                task_lines.append(line)
                continue
            indent2 = len(line) - len(line.lstrip(" "))
            if indent2 > task_indent:
                task_lines.append(line)

    flush_task()
    return chunks


def iter_chunks_for_corpus(*, corpus: str, root: Path, chunk_target_tokens: int) -> Iterator[Chunk]:
    for path in iter_files_for_corpus(corpus=corpus, root=root):
        if corpus == "canon":
            for chunk in chunks_for_canon(path, chunk_target_tokens=chunk_target_tokens):
                yield chunk
        elif corpus == "followups":
            for chunk in chunks_for_followups(path):
                yield chunk
        elif corpus == "plans":
            for chunk in chunks_for_canon(path, chunk_target_tokens=chunk_target_tokens):
                yield Chunk(
                    corpus="plans",
                    path=chunk.path,
                    start_line=chunk.start_line,
                    heading=chunk.heading,
                    body=chunk.body,
                )
        else:
            raise ValueError(f"Unsupported corpus: {corpus}")


def rebuild_corpus(conn: sqlite3.Connection, *, corpus: str, root: Path, chunk_target_tokens: int) -> tuple[int, int]:
    conn.execute("DELETE FROM doc_chunks_fts WHERE corpus = ?", (corpus,))
    rows: list[tuple[str, str, str, str, str]] = []
    chunks_total = 0
    files_seen: set[str] = set()

    for chunk in iter_chunks_for_corpus(corpus=corpus, root=root, chunk_target_tokens=chunk_target_tokens):
        chunks_total += 1
        files_seen.add(chunk.path)
        rows.append(
            (
                chunk.corpus,
                chunk.path,
                str(chunk.start_line),
                chunk.heading,
                chunk.body,
            )
        )
        if len(rows) >= 500:
            conn.executemany(
                "INSERT INTO doc_chunks_fts(corpus, path, start_line, heading, body) VALUES(?, ?, ?, ?, ?)",
                rows,
            )
            rows = []

    if rows:
        conn.executemany(
            "INSERT INTO doc_chunks_fts(corpus, path, start_line, heading, body) VALUES(?, ?, ?, ?, ?)",
            rows,
        )

    return len(files_seen), chunks_total


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Build SQLite FTS index for planveyor docs (canon + followups + plans).")
    parser.add_argument("--db", default=DEFAULT_DB, help=f"SQLite DB path (default: {DEFAULT_DB})")
    parser.add_argument("--corpus", choices=["canon", "followups", "plans"], required=True, help="Corpus to (re)build")
    parser.add_argument("--root", default=DEFAULT_ROOT, help="Docs root directory (default: docs)")
    parser.add_argument(
        "--chunk-target-tokens",
        type=int,
        default=DEFAULT_CHUNK_TARGET_TOKENS,
        help=f"Approx token target per chunk (canon/plans). Default: {DEFAULT_CHUNK_TARGET_TOKENS}",
    )
    parser.add_argument("--force-rebuild", action="store_true", help="Drop existing tables and rebuild.")

    args = parser.parse_args(argv)

    db_path = Path(args.db)
    _ensure_parent_dir(db_path)

    root = Path(args.root)
    if not root.exists() or not root.is_dir():
        print(f"ERROR: docs root not found or not a directory: {root}", file=sys.stderr)
        return 2

    chunk_target_tokens = int(args.chunk_target_tokens)
    if chunk_target_tokens <= 0:
        print("ERROR: --chunk-target-tokens must be > 0", file=sys.stderr)
        return 2

    rules = corpus_rules(args.corpus, root.as_posix(), chunk_target_tokens)
    fp = compute_fingerprint(rules)

    conn = sqlite3.connect(db_path.as_posix())
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        sqlite_fts5_self_check(conn)

        if args.force_rebuild:
            conn.execute("DROP TABLE IF EXISTS doc_chunks_fts")
            conn.execute("DROP TABLE IF EXISTS meta")

        ensure_schema(conn)
        migrated_copies = init_or_validate_meta(conn, rules=rules, fingerprint=fp, force_rebuild=bool(args.force_rebuild))

        files_total, chunks_total = rebuild_corpus(conn, corpus=args.corpus, root=root, chunk_target_tokens=chunk_target_tokens)
        _meta_set(conn, f"built_at_utc.{args.corpus}", str(int(time.time())))
        _meta_set(conn, f"files_total.{args.corpus}", str(files_total))
        _meta_set(conn, f"chunks_total.{args.corpus}", str(chunks_total))

        conn.commit()
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    except sqlite3.Error as e:
        print(f"ERROR: sqlite error: {e}", file=sys.stderr)
        return 2
    finally:
        conn.close()

    print("docs_index_build")
    print(f"- db: {db_path}")
    print(f"- corpus: {args.corpus}")
    print(f"- root: {root}")
    print(f"- chunk_target_tokens: {chunk_target_tokens}")
    print(f"- files_indexed: {files_total}")
    print(f"- chunks_indexed: {chunks_total}")
    print(f"- fingerprint: {fp[:12]}…")
    if migrated_copies:
        print("- index_migration: translation_copy_exclusion (all corpuses)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

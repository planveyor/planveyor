#!/usr/bin/env python3
"""
Query local docs retrieval index (SQLite FTS5) built by `scripts/docs_index_build.py`.

Output modes:
- `--format text` (default): human-readable list with jump hint `path:line`
- `--format md` / `--md`: markdown-friendly bullets
- `--format json`: strict JSON payload in stdout
- `--files`: only unique file paths (one per line)
- `--no-context`: disable path-prefix context hints (Context: (none))
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import traceback
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from docs_context_registry import contexts_for_path, format_contexts_inline


DEFAULT_DB = ".tmp/planveyor_docs_index.sqlite"
ALL_K_CAP = 300
DEFAULT_LOG = ".tmp/planveyor_docs_retrieve_queries.jsonl"
LOG_ENV_VAR = "PLANVEYOR_DOCS_RETRIEVE_LOG"
LOG_DISABLE_VALUES = {"0", "off", "false", "no", "disable", "disabled"}
STATUS_FILTER_TOKENS = {
    "open",
    "opened",
    "done",
    "status",
    "draft",
    "ready",
    "closed",
    "active",
    "progress",
    "открыт",
    "открытые",
    "открытая",
    "открыто",
    "статус",
    "готов",
    "готово",
    "готовые",
    "закрыт",
    "закрытые",
    "выполнен",
    "выполнено",
}

USAGE_ERROR = 2
RUNTIME_ERROR = 1


class UsageError(RuntimeError):
    """CLI usage/arguments error."""


class RuntimeDataError(RuntimeError):
    """Runtime/data/index error."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # pragma: no cover - argparse integration
        raise UsageError(message)


@dataclass(frozen=True)
class Hit:
    path: str
    line: int
    heading: str
    bm25_raw: float
    score: float
    snippet: str


def _meta_get(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return None if row is None else str(row[0])


def _ensure_db_ready(conn: sqlite3.Connection) -> dict[str, str]:
    # Basic schema check (friendly error).
    try:
        conn.execute("SELECT 1 FROM meta LIMIT 1")
        conn.execute("SELECT 1 FROM doc_chunks_fts LIMIT 1")
    except sqlite3.Error as e:
        raise RuntimeDataError(
            "Index DB is missing required tables (meta/doc_chunks_fts). "
            "Build it first with: scripts/docs_index_build.py"
        ) from e

    schema_version = _meta_get(conn, "schema_version")
    if not schema_version:
        raise RuntimeDataError("Index DB has no schema_version in meta. Rebuild the index.")

    tool_version = _meta_get(conn, "tool_version") or ""
    return {
        "schema_version": schema_version,
        "tool_version": tool_version,
    }


def _run_match_query(conn: sqlite3.Connection, *, corpus: str, query: str, k: int) -> list[tuple]:
    return conn.execute(
        """
        SELECT
          path,
          start_line,
          heading,
          bm25(doc_chunks_fts) AS bm25_raw,
          snippet(doc_chunks_fts, 4, '[', ']', ' … ', 12) AS snippet
        FROM doc_chunks_fts
        WHERE corpus = ? AND doc_chunks_fts MATCH ?
        ORDER BY bm25_raw
        LIMIT ?
        """,
        (corpus, query, int(k)),
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


def _query_tokens(text: str) -> list[str]:
    return re.findall(r"\w+", text, flags=re.UNICODE)


def _contains_cyrillic(text: str) -> bool:
    return bool(re.search(r"[А-Яа-яЁё]", text))


def _query_warnings(query: str, *, corpus: str, query_mode: str) -> list[str]:
    tokens = _query_tokens(query)
    token_count = len(tokens)
    token_set = {token.lower() for token in tokens}
    warnings: list[str] = []

    if query_mode == "fallback":
        warnings.append(
            "Punctuation query fell back to token-AND search; exact phrase semantics are lost. "
            "Prefer 2-5 exact anchor tokens."
        )
    if token_count >= 5:
        warnings.append(
            "Long free-text query: SQLite FTS here is token-based. Prefer 2-5 exact anchor tokens "
            "(cluster, filename fragment, code term), then inspect files with docs_get/docs_multi_get."
        )
    if _contains_cyrillic(query) and token_count >= 4:
        warnings.append(
            "Russian free-text search is exact-token only: paraphrases, wordforms and е/ё variants may miss. "
            "Reformulate with exact cluster/tag/file terms from docs."
        )
    if corpus == "plans" and token_set.intersection(STATUS_FILTER_TOKENS):
        warnings.append(
            "Do not infer plan status from FTS terms like open/status/done. Retrieve related files first, "
            "then read header **Status:** via docs_get/docs_multi_get or plan_status_oracle.py."
        )
    return warnings


def _post_query_warnings(query: str, *, hits: list[Hit]) -> list[str]:
    if hits:
        return []
    if len(_query_tokens(query)) < 3:
        return []
    return [
        "0 hits. Retry with a narrower corpus and shorter anchor query (2-5 exact tokens), not a full sentence."
    ]


def _dedupe_preserve(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _emit_warnings_stderr(warnings: list[str]) -> None:
    for warning in warnings:
        print(f"WARN: {warning}", file=sys.stderr)


def _resolve_log_path(args: argparse.Namespace) -> Path | None:
    if bool(getattr(args, "no_log", False)):
        return None

    arg_value = str(getattr(args, "log_file", "") or "").strip()
    if arg_value:
        return Path(arg_value)

    env_value = os.environ.get(LOG_ENV_VAR)
    if env_value is not None:
        env_value = env_value.strip()
        if env_value.lower() in LOG_DISABLE_VALUES:
            return None
        if env_value:
            return Path(env_value)

    return Path(DEFAULT_LOG)


def _materialize_log_path(path: Path | None) -> Path | None:
    if path is None:
        return None
    if path.is_absolute():
        return path
    return Path.cwd() / path


def _append_log(log_path: Path | None, payload: dict[str, object]) -> None:
    if log_path is None:
        return
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
            fh.write("\n")
    except OSError:
        return


def _new_event_id(*, corpus: str, query: str) -> str:
    digest = hashlib.sha1(f"{Path.cwd()}\0{corpus}\0{query}".encode("utf-8")).hexdigest()[:10]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{digest}-{uuid.uuid4().hex[:8]}"


def _log_event(
    log_path: Path | None,
    *,
    event_id: str,
    db_path: Path,
    corpus: str,
    query: str,
    k: int,
    output_mode: str,
    query_mode: str,
    min_score: float | None,
    hits: list[Hit],
    files: list[str],
    warnings: list[str],
    error: str | None = None,
) -> None:
    payload: dict[str, object] = {
        "event_id": event_id,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "cwd": Path.cwd().as_posix(),
        "db": db_path.as_posix(),
        "corpus": corpus,
        "query": query,
        "k": k,
        "output_mode": output_mode,
        "query_mode": query_mode,
        "min_score": min_score,
        "warnings": warnings,
        "hits": len(hits),
        "files": len(files),
        "top_files": files[:10],
    }
    if error is not None:
        payload["error"] = error
    _append_log(log_path, payload)


def _normalize_score(bm25_raw: float) -> float:
    magnitude = abs(float(bm25_raw))
    return magnitude / (1.0 + magnitude)


def query_hits(conn: sqlite3.Connection, *, corpus: str, query: str, k: int) -> tuple[list[Hit], str]:
    query_text = str(query).strip()
    if not query_text:
        return [], "empty"

    query_mode = "raw"
    try:
        rows = _run_match_query(conn, corpus=corpus, query=query_text, k=k)
    except sqlite3.OperationalError as e:
        if not _fts_parse_error(e):
            raise
        fallback_query = _plain_text_to_fts_and_query(query_text)
        if not fallback_query:
            return [], "empty"
        rows = _run_match_query(conn, corpus=corpus, query=fallback_query, k=k)
        query_mode = "fallback"

    out: list[Hit] = []
    for path, start_line, heading, bm25_raw, snippet in rows:
        try:
            line_i = int(str(start_line))
        except ValueError:
            line_i = 1
        raw = float(bm25_raw)
        out.append(
            Hit(
                path=str(path),
                line=line_i,
                heading=str(heading or ""),
                bm25_raw=raw,
                score=_normalize_score(raw),
                snippet=str(snippet or "").replace("\n", " ").strip(),
            )
        )

    # Deterministic order with explicit tie-breakers.
    out.sort(key=lambda h: (h.bm25_raw, h.path, h.line))
    return out, query_mode


def _unique_files_from_hits(hits: list[Hit]) -> list[str]:
    seen: set[str] = set()
    files: list[str] = []
    for hit in hits:
        if hit.path in seen:
            continue
        seen.add(hit.path)
        files.append(hit.path)
    return files


def _build_context_map(hits: list[Hit], *, enabled: bool) -> dict[str, list[dict[str, str]]]:
    by_path: dict[str, list[dict[str, str]]] = {}
    for hit in hits:
        if hit.path in by_path:
            continue
        by_path[hit.path] = contexts_for_path(hit.path) if enabled else []
    return by_path


def format_hits_human(hits: list[Hit], *, context_map: dict[str, list[dict[str, str]]]) -> str:
    lines: list[str] = []
    for i, h in enumerate(hits, start=1):
        jump = f"{h.path}:{h.line}"
        heading = h.heading.strip() or "(no heading)"
        lines.append(f"{i:>2}) {jump}  score={h.score:.3f}  bm25_raw={h.bm25_raw:.3f}  {heading}")
        lines.append(f"    Context: {format_contexts_inline(context_map.get(h.path, []))}")
        if h.snippet:
            lines.append(f"    {h.snippet}")
    return "\n".join(lines)


def format_hits_md(hits: list[Hit], *, context_map: dict[str, list[dict[str, str]]]) -> str:
    lines: list[str] = []
    for h in hits:
        jump = f"{h.path}:{h.line}"
        heading = h.heading.strip() or "(no heading)"
        lines.append(f"- `{jump}` — {heading} (score={h.score:.3f}, bm25_raw={h.bm25_raw:.3f})")
        lines.append(f"  - Context: {format_contexts_inline(context_map.get(h.path, []))}")
        if h.snippet:
            lines.append(f"  - {h.snippet}")
    return "\n".join(lines)


def _json_dump(payload: dict) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.write("\n")


def _scan_wants_json(argv: list[str]) -> bool:
    for i, arg in enumerate(argv):
        if arg == "--format" and i + 1 < len(argv) and argv[i + 1].strip().lower() == "json":
            return True
        if arg.startswith("--format=") and arg.split("=", 1)[1].strip().lower() == "json":
            return True
    return False


def _scan_has_flag(argv: list[str], name: str) -> bool:
    for arg in argv:
        if arg == name or arg.startswith(name + "="):
            return True
    return False


def _emit_json_error(
    *,
    code: str,
    message: str,
    query: str | None = None,
    corpus: str | None = None,
    k: int | None = None,
    db: str | None = None,
    meta_extra: dict | None = None,
) -> None:
    meta: dict[str, object] = {}
    if db:
        meta["db"] = db
    if meta_extra:
        meta.update(meta_extra)
    payload = {
        "ok": False,
        "query": query,
        "corpus": corpus,
        "k": k,
        "hits": [],
        "files": [],
        "meta": meta,
        "error": {"code": code, "message": message},
    }
    _json_dump(payload)


def _build_parser() -> _Parser:
    parser = _Parser(description="Query planveyor docs retrieval index (SQLite FTS5).")
    parser.add_argument("--db", default=DEFAULT_DB, help=f"SQLite DB path (default: {DEFAULT_DB})")
    parser.add_argument("--corpus", choices=["canon", "followups", "plans"], required=True, help="Corpus to query")
    parser.add_argument("--k", type=int, default=0, help="Top-K results (default depends on corpus)")
    parser.add_argument("--all", action="store_true", help=f"Use extended cap (k={ALL_K_CAP})")
    parser.add_argument(
        "--format",
        choices=["text", "md", "json"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument("--md", action="store_true", help="Alias for --format md (backward-compatible)")
    parser.add_argument("--files", action="store_true", help="Output only unique file paths (newline-separated)")
    parser.add_argument("--no-context", action="store_true", help="Disable context hints in text/md/json outputs")
    parser.add_argument(
        "--min-score",
        type=float,
        default=None,
        help="Minimum normalized score in [0..1] (applied after retrieval)",
    )
    parser.add_argument(
        "--log-file",
        default="",
        help=(
            f"Query log path (JSONL). Default: {DEFAULT_LOG}; override via {LOG_ENV_VAR}=PATH; "
            f"disable with --no-log or {LOG_ENV_VAR}=0"
        ),
    )
    parser.add_argument("--no-log", action="store_true", help="Disable query logging for this invocation")
    parser.add_argument(
        "query",
        help=(
            "FTS query string. If raw FTS parse fails (e.g. punctuation like now-line), "
            "tool retries as plain text (token AND query)."
        ),
    )
    return parser


def _default_k_for_corpus(corpus: str) -> int:
    if corpus == "followups":
        return 15
    if corpus == "plans":
        return 12
    return 8


def _resolve_output_mode(args: argparse.Namespace, *, has_format_flag: bool) -> str:
    if args.files and (has_format_flag or args.md):
        raise UsageError("Use either --files OR --format/--md, not both.")
    if args.md and has_format_flag:
        raise UsageError("Use either --md OR --format, not both.")
    if args.files:
        return "files"
    if args.md:
        return "md"
    return str(args.format)


def _validate_args(args: argparse.Namespace, *, has_format_flag: bool) -> tuple[str, int]:
    output_mode = _resolve_output_mode(args, has_format_flag=has_format_flag)

    if int(args.k) < 0:
        raise UsageError("--k must be >= 0")
    if args.min_score is not None and not (0.0 <= float(args.min_score) <= 1.0):
        raise UsageError("--min-score must be in range [0..1]")

    if args.all:
        k = ALL_K_CAP
    elif int(args.k) > 0:
        k = int(args.k)
    else:
        k = _default_k_for_corpus(str(args.corpus))

    return output_mode, k


def _run(argv: list[str], *, parser: _Parser) -> int:
    wants_json = _scan_wants_json(argv)
    has_format_flag = _scan_has_flag(argv, "--format")

    try:
        args = parser.parse_args(argv)
        output_mode, k = _validate_args(args, has_format_flag=has_format_flag)
        wants_json = wants_json or (output_mode == "json")
    except UsageError as e:
        if wants_json:
            _emit_json_error(code="usage_error", message=str(e))
        else:
            print(f"ERROR: {e}", file=sys.stderr)
            print(parser.format_usage().strip(), file=sys.stderr)
        return USAGE_ERROR

    db_path = Path(str(args.db))
    log_path = _materialize_log_path(_resolve_log_path(args))
    event_id = _new_event_id(corpus=str(args.corpus), query=str(args.query))
    if not db_path.exists():
        msg = (
            f"index DB not found: {db_path}\n"
            "Build it first, e.g.:\n"
            f"  $PYBIN scripts/docs_index_build.py --db {db_path} --corpus {args.corpus}\n"
            f"  conda run -n planveyor python scripts/docs_index_build.py --db {db_path} --corpus {args.corpus}"
        )
        _log_event(
            log_path,
            event_id=event_id,
            db_path=db_path,
            corpus=str(args.corpus),
            query=str(args.query),
            k=k,
            output_mode=output_mode,
            query_mode="raw",
            min_score=float(args.min_score) if args.min_score is not None else None,
            hits=[],
            files=[],
            warnings=[],
            error=f"index DB not found: {db_path}",
        )
        if wants_json:
            _emit_json_error(
                code="runtime_error",
                message=f"index DB not found: {db_path}",
                query=str(args.query),
                corpus=str(args.corpus),
                k=k,
                db=db_path.as_posix(),
                meta_extra={"event_id": event_id},
            )
            print(msg, file=sys.stderr)
        else:
            print(f"ERROR: {msg}", file=sys.stderr)
        return RUNTIME_ERROR

    query_mode = "raw"
    db_meta: dict[str, str] = {"schema_version": "", "tool_version": ""}
    try:
        conn = sqlite3.connect(db_path.as_posix())
        try:
            db_meta = _ensure_db_ready(conn)
            hits, query_mode = query_hits(conn, corpus=str(args.corpus), query=str(args.query), k=k)
        finally:
            conn.close()
    except RuntimeDataError as e:
        _log_event(
            log_path,
            event_id=event_id,
            db_path=db_path,
            corpus=str(args.corpus),
            query=str(args.query),
            k=k,
            output_mode=output_mode,
            query_mode=query_mode,
            min_score=float(args.min_score) if args.min_score is not None else None,
            hits=[],
            files=[],
            warnings=[],
            error=str(e),
        )
        if wants_json:
            _emit_json_error(
                code="runtime_error",
                message=str(e),
                query=str(args.query),
                corpus=str(args.corpus),
                k=k,
                db=db_path.as_posix(),
                meta_extra={"event_id": event_id},
            )
        else:
            print(f"ERROR: {e}", file=sys.stderr)
        return RUNTIME_ERROR
    except sqlite3.Error as e:
        _log_event(
            log_path,
            event_id=event_id,
            db_path=db_path,
            corpus=str(args.corpus),
            query=str(args.query),
            k=k,
            output_mode=output_mode,
            query_mode=query_mode,
            min_score=float(args.min_score) if args.min_score is not None else None,
            hits=[],
            files=[],
            warnings=[],
            error=f"sqlite error: {e}",
        )
        if wants_json:
            _emit_json_error(
                code="runtime_error",
                message=f"sqlite error: {e}",
                query=str(args.query),
                corpus=str(args.corpus),
                k=k,
                db=db_path.as_posix(),
                meta_extra={"event_id": event_id},
            )
        else:
            print(f"ERROR: sqlite error: {e}", file=sys.stderr)
        return RUNTIME_ERROR

    min_score = float(args.min_score) if args.min_score is not None else None
    if min_score is not None:
        hits = [h for h in hits if h.score >= min_score]

    files = _unique_files_from_hits(hits)
    warnings = _dedupe_preserve(
        _query_warnings(str(args.query), corpus=str(args.corpus), query_mode=query_mode)
        + _post_query_warnings(str(args.query), hits=hits)
    )
    if warnings:
        _emit_warnings_stderr(warnings)
    _log_event(
        log_path,
        event_id=event_id,
        db_path=db_path,
        corpus=str(args.corpus),
        query=str(args.query),
        k=k,
        output_mode=output_mode,
        query_mode=query_mode,
        min_score=min_score,
        hits=hits,
        files=files,
        warnings=warnings,
    )

    if output_mode == "files":
        for path in files:
            print(path)
        return 0

    context_map = _build_context_map(hits, enabled=(not bool(args.no_context)))

    if output_mode == "json":
        payload = {
            "ok": True,
            "query": str(args.query),
            "corpus": str(args.corpus),
            "k": k,
            "hits": [
                {
                    "path": h.path,
                    "line": h.line,
                    "heading": h.heading,
                    "bm25_raw": h.bm25_raw,
                    "score": h.score,
                    "snippet": h.snippet,
                    "contexts": context_map.get(h.path, []),
                }
                for h in hits
            ],
            "files": files,
            "meta": {
                "event_id": event_id,
                "db": db_path.as_posix(),
                "schema_version": db_meta.get("schema_version", ""),
                "tool_version": db_meta.get("tool_version", ""),
                "query_mode": query_mode,
                "min_score": min_score,
                "all": bool(args.all),
                "warnings": warnings,
                "log_file": "" if log_path is None else log_path.as_posix(),
            },
        }
        _json_dump(payload)
        return 0

    header = f"docs_retrieve (corpus={args.corpus}, k={k}, hits={len(hits)}, event_id={event_id})"
    print(header)
    if not hits:
        return 0

    print()
    if output_mode == "md":
        print(format_hits_md(hits, context_map=context_map))
    else:
        print(format_hits_human(hits, context_map=context_map))
    return 0


def main(argv: list[str]) -> int:
    parser = _build_parser()
    try:
        return _run(argv, parser=parser)
    except BrokenPipeError:  # pragma: no cover - shell pipeline behavior
        return 0
    except Exception as e:  # pragma: no cover - defensive top-level hardening
        wants_json = _scan_wants_json(argv)
        msg = f"unexpected error: {type(e).__name__}: {e}"
        if wants_json:
            try:
                _emit_json_error(code="runtime_error", message=msg)
            except Exception:
                print(f"ERROR: {msg}", file=sys.stderr)
        else:
            print(f"ERROR: {msg}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return RUNTIME_ERROR


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

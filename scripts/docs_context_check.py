#!/usr/bin/env python3
"""
Coverage checker for docs path-prefix context registry.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import traceback
from collections import Counter
from pathlib import Path

from docs_context_registry import contexts_for_path, registered_prefixes


DEFAULT_DB = ".tmp/planveyor_docs_index.sqlite"
DEFAULT_MAX_UNCOVERED = 50
DEFAULT_MAX_HINTS = 20
DEFAULT_HINT_DEPTH = 2

USAGE_ERROR = 2
RUNTIME_ERROR = 1


class UsageError(RuntimeError):
    """CLI usage/arguments error."""


class RuntimeDataError(RuntimeError):
    """Runtime/data/index error."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # pragma: no cover - argparse integration
        raise UsageError(message)


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


def _emit_json_error(
    *,
    code: str,
    message: str,
    corpus: str | None = None,
    db: str | None = None,
) -> None:
    _json_dump(
        {
            "ok": False,
            "corpus": corpus,
            "uncovered_paths": [],
            "hints": [],
            "meta": {"db": db or ""},
            "error": {"code": code, "message": message},
        }
    )


def _build_parser() -> _Parser:
    parser = _Parser(description="Check docs context coverage by corpus.")
    parser.add_argument("--db", default=DEFAULT_DB, help=f"SQLite DB path (default: {DEFAULT_DB})")
    parser.add_argument("--corpus", choices=["canon", "followups", "plans"], required=True, help="Corpus to check")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    parser.add_argument(
        "--max-uncovered",
        type=int,
        default=DEFAULT_MAX_UNCOVERED,
        help=f"Max uncovered paths to print/return (default: {DEFAULT_MAX_UNCOVERED})",
    )
    parser.add_argument(
        "--max-hints",
        type=int,
        default=DEFAULT_MAX_HINTS,
        help=f"Max prefix hints to print/return (default: {DEFAULT_MAX_HINTS})",
    )
    parser.add_argument(
        "--hint-depth",
        type=int,
        default=DEFAULT_HINT_DEPTH,
        help=f"Candidate prefix depth under root (default: {DEFAULT_HINT_DEPTH})",
    )
    return parser


def _ensure_db_ready(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("SELECT 1 FROM meta LIMIT 1")
        conn.execute("SELECT 1 FROM doc_chunks_fts LIMIT 1")
    except sqlite3.Error as e:
        raise RuntimeDataError(
            "Index DB is missing required tables (meta/doc_chunks_fts). "
            "Build it first with: scripts/docs_index_build.py"
        ) from e


def _load_paths(conn: sqlite3.Connection, *, corpus: str) -> list[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT path
        FROM doc_chunks_fts
        WHERE corpus = ?
        ORDER BY path
        """,
        (corpus,),
    ).fetchall()
    return [str(row[0]) for row in rows]


def _normalize_path(path: str) -> str:
    out = str(path or "").strip().replace("\\", "/")
    while "//" in out:
        out = out.replace("//", "/")
    while out.startswith("./"):
        out = out[2:]
    return out


def _candidate_prefixes(path: str, *, hint_depth: int) -> list[str]:
    normalized = _normalize_path(path)
    if not normalized:
        return []

    parts = [part for part in normalized.split("/") if part]
    if not parts:
        return []

    dir_parts = parts[:-1]
    out: list[str] = []
    max_take = min(len(dir_parts), 1 + int(hint_depth))
    for take in range(2, max_take + 1):
        out.append("/".join(dir_parts[:take]) + "/")

    if out:
        return out
    return [normalized]


def _run(argv: list[str], *, parser: _Parser) -> int:
    wants_json = _scan_wants_json(argv)
    try:
        args = parser.parse_args(argv)
        wants_json = wants_json or (str(args.format) == "json")
    except UsageError as e:
        if wants_json:
            _emit_json_error(code="usage_error", message=str(e))
        else:
            print(f"ERROR: {e}", file=sys.stderr)
            print(parser.format_usage().strip(), file=sys.stderr)
        return USAGE_ERROR

    if int(args.max_uncovered) < 1 or int(args.max_hints) < 1 or int(args.hint_depth) < 1:
        msg = "--max-uncovered, --max-hints, --hint-depth must be >= 1"
        if wants_json:
            _emit_json_error(code="usage_error", message=msg, corpus=str(args.corpus), db=str(args.db))
        else:
            print(f"ERROR: {msg}", file=sys.stderr)
        return USAGE_ERROR

    db_path = Path(str(args.db))
    if not db_path.exists():
        msg = f"index DB not found: {db_path}"
        if wants_json:
            _emit_json_error(code="runtime_error", message=msg, corpus=str(args.corpus), db=db_path.as_posix())
        else:
            print(f"ERROR: {msg}", file=sys.stderr)
        return RUNTIME_ERROR

    try:
        conn = sqlite3.connect(db_path.as_posix())
        try:
            _ensure_db_ready(conn)
            paths = _load_paths(conn, corpus=str(args.corpus))
        finally:
            conn.close()
    except RuntimeDataError as e:
        if wants_json:
            _emit_json_error(code="runtime_error", message=str(e), corpus=str(args.corpus), db=db_path.as_posix())
        else:
            print(f"ERROR: {e}", file=sys.stderr)
        return RUNTIME_ERROR
    except sqlite3.Error as e:
        msg = f"sqlite error: {e}"
        if wants_json:
            _emit_json_error(code="runtime_error", message=msg, corpus=str(args.corpus), db=db_path.as_posix())
        else:
            print(f"ERROR: {msg}", file=sys.stderr)
        return RUNTIME_ERROR

    known = set(registered_prefixes())
    uncovered_all: list[str] = []
    hint_counts: Counter[str] = Counter()
    covered_count = 0

    for path in paths:
        if contexts_for_path(path):
            covered_count += 1
            continue
        uncovered_all.append(path)
        for prefix in _candidate_prefixes(path, hint_depth=int(args.hint_depth)):
            if prefix in known:
                continue
            hint_counts[prefix] += 1

    total_paths = len(paths)
    uncovered_count = len(uncovered_all)
    coverage_ratio = (float(covered_count) / float(total_paths)) if total_paths > 0 else 1.0

    uncovered_limited = uncovered_all[: int(args.max_uncovered)]
    hints_sorted = sorted(hint_counts.items(), key=lambda item: (-item[1], item[0]))
    hints_limited = [{"prefix": prefix, "count": count} for prefix, count in hints_sorted[: int(args.max_hints)]]

    payload = {
        "ok": True,
        "corpus": str(args.corpus),
        "uncovered_paths": uncovered_limited,
        "hints": hints_limited,
        "meta": {
            "db": db_path.as_posix(),
            "total_paths": total_paths,
            "covered_paths": covered_count,
            "uncovered_paths": uncovered_count,
            "coverage_ratio": coverage_ratio,
            "max_uncovered": int(args.max_uncovered),
            "max_hints": int(args.max_hints),
            "hint_depth": int(args.hint_depth),
            "omitted_uncovered_paths": max(0, uncovered_count - len(uncovered_limited)),
        },
    }

    if str(args.format) == "json":
        _json_dump(payload)
        return 0

    print(
        "docs_context_check "
        f"(corpus={args.corpus}, files={total_paths}, covered={covered_count}, "
        f"uncovered={uncovered_count}, coverage={coverage_ratio:.1%})"
    )

    print()
    if uncovered_limited:
        print(f"Uncovered paths (first {len(uncovered_limited)}):")
        for path in uncovered_limited:
            print(f"- {path}")
        if uncovered_count > len(uncovered_limited):
            print(f"- ... ({uncovered_count - len(uncovered_limited)} more)")
    else:
        print("Uncovered paths: (none)")

    print()
    if hints_limited:
        print(f"Suggested prefixes (top {len(hints_limited)}):")
        for hint in hints_limited:
            print(f"- {hint['prefix']} (count={hint['count']})")
    else:
        print("Suggested prefixes: (none)")

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

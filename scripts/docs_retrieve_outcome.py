#!/usr/bin/env python3
"""
Append an explicit outcome row for a docs_retrieve query event.

The query log remains append-only. This helper writes a separate JSONL outcome
row keyed by docs_retrieve `event_id` / `query_event_id`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


DEFAULT_QUERY_LOG = ".tmp/planveyor_docs_retrieve_queries.jsonl"
DEFAULT_OUTCOME_LOG = ".tmp/planveyor_docs_retrieve_outcomes.jsonl"
QUERY_LOG_ENV_VAR = "PLANVEYOR_DOCS_RETRIEVE_LOG"
OUTCOME_LOG_ENV_VAR = "PLANVEYOR_DOCS_RETRIEVE_OUTCOME_LOG"
LOG_DISABLE_VALUES = {"0", "off", "false", "no", "disable", "disabled"}
OUTCOMES = ("used", "partial", "miss", "noise", "not_evaluated")
MAX_NOTE_CHARS = 240
MAX_PATH_CHARS = 500

USAGE_ERROR = 2
RUNTIME_ERROR = 1


class UsageError(RuntimeError):
    """CLI usage/arguments error."""


def _utc_ts() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _resolve_path(*, arg_value: str, env_var: str, default: str) -> Path | None:
    arg_value = str(arg_value or "").strip()
    if arg_value:
        return Path(arg_value)

    env_value = os.environ.get(env_var)
    if env_value is not None:
        env_value = env_value.strip()
        if env_value.lower() in LOG_DISABLE_VALUES:
            return None
        if env_value:
            return Path(env_value)

    return Path(default)


def _materialize_path(path: Path | None) -> Path | None:
    if path is None:
        return None
    if path.is_absolute():
        return path
    return Path.cwd() / path


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    rows.append(payload)
    except FileNotFoundError as e:
        raise UsageError(f"query log not found: {path}") from e
    except OSError as e:
        raise RuntimeError(f"cannot read query log {path}: {e}") from e
    return rows


def _latest_query_event(rows: list[dict[str, object]]) -> dict[str, object] | None:
    cwd = Path.cwd().as_posix()
    for row in reversed(rows):
        event_id = str(row.get("event_id") or "").strip()
        if not event_id:
            continue
        if str(row.get("cwd") or "") == cwd:
            return row
    return None


def _query_event_by_id(rows: list[dict[str, object]], event_id: str) -> dict[str, object] | None:
    for row in reversed(rows):
        if str(row.get("event_id") or "").strip() == event_id:
            return row
    return None


def _validate_scalar(value: str, *, label: str, max_chars: int) -> str:
    value = str(value or "").strip()
    if not value:
        return ""
    if len(value) > max_chars:
        raise UsageError(f"{label} is too long (max {max_chars} chars)")
    if any((ord(ch) < 32 and ch not in ("\t",)) for ch in value):
        raise UsageError(f"{label} must not contain newlines or control characters")
    if "\n" in value or "\r" in value:
        raise UsageError(f"{label} must not contain newlines or control characters")
    return value


def _dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        item = _validate_scalar(item, label="file path", max_chars=MAX_PATH_CHARS)
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _as_int(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _append_jsonl(path: Path, payload: dict[str, object]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
            fh.write("\n")
    except OSError as e:
        raise RuntimeError(f"cannot write outcome log {path}: {e}") from e


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mark a docs_retrieve query event with a bounded outcome.")
    parser.add_argument(
        "--query-log",
        default="",
        help=(
            f"docs_retrieve query log path. Default: {DEFAULT_QUERY_LOG}; "
            f"override via {QUERY_LOG_ENV_VAR}=PATH"
        ),
    )
    parser.add_argument(
        "--outcome-log",
        default="",
        help=(
            f"Outcome log path. Default: {DEFAULT_OUTCOME_LOG}; "
            f"override via {OUTCOME_LOG_ENV_VAR}=PATH"
        ),
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--event-id", default="", help="Exact docs_retrieve event_id to mark")
    target.add_argument("--latest", action="store_true", help="Mark the latest query event from the current cwd")
    parser.add_argument("--outcome", required=True, choices=OUTCOMES, help="Explicit retrieval outcome")
    parser.add_argument("--opened-file", action="append", default=[], help="File opened because of this retrieval")
    parser.add_argument("--cited-file", action="append", default=[], help="File cited/used as durable evidence")
    parser.add_argument("--note", default="", help=f"Short note, max {MAX_NOTE_CHARS} chars; no snippets/transcripts/secrets")
    parser.add_argument("--tool", default="planveyor_docs_retrieve", help="Tool label for the outcome row")
    parser.add_argument("--repo", default="", help="Repo label (default: current directory basename)")
    parser.add_argument("--json", action="store_true", help="Print JSON receipt")
    return parser


def _run(argv: list[str]) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    query_log = _materialize_path(
        _resolve_path(arg_value=args.query_log, env_var=QUERY_LOG_ENV_VAR, default=DEFAULT_QUERY_LOG)
    )
    outcome_log = _materialize_path(
        _resolve_path(arg_value=args.outcome_log, env_var=OUTCOME_LOG_ENV_VAR, default=DEFAULT_OUTCOME_LOG)
    )
    if query_log is None:
        raise UsageError(f"query log is disabled via {QUERY_LOG_ENV_VAR}; pass --query-log explicitly")
    if outcome_log is None:
        raise UsageError(f"outcome log is disabled via {OUTCOME_LOG_ENV_VAR}; pass --outcome-log explicitly")

    rows = _load_jsonl(query_log)
    event_id = _validate_scalar(str(args.event_id or ""), label="event_id", max_chars=120)
    if args.latest:
        event = _latest_query_event(rows)
        if event is None:
            raise UsageError(f"no current-cwd query event with event_id found in {query_log}")
        event_id = str(event["event_id"])
    else:
        event = _query_event_by_id(rows, event_id)
        if event is None:
            raise UsageError(f"event_id not found in query log: {event_id}")

    note = _validate_scalar(str(args.note or ""), label="note", max_chars=MAX_NOTE_CHARS)
    opened_files = _dedupe(args.opened_file)
    cited_files = _dedupe(args.cited_file)
    repo = _validate_scalar(str(args.repo or Path.cwd().name), label="repo", max_chars=120)
    tool = _validate_scalar(str(args.tool or "planveyor_docs_retrieve"), label="tool", max_chars=120)

    payload: dict[str, object] = {
        "ts": _utc_ts(),
        "query_event_id": event_id,
        "cwd": Path.cwd().as_posix(),
        "repo": repo,
        "tool": tool,
        "outcome": str(args.outcome),
        "opened_files": opened_files,
        "cited_files": cited_files,
        "notes": note,
        "query": str(event.get("query") or ""),
        "query_corpus": str(event.get("corpus") or ""),
        "query_hits": _as_int(event.get("hits")),
        "query_files": _as_int(event.get("files")),
        "query_log_file": query_log.as_posix(),
    }
    _append_jsonl(outcome_log, payload)

    receipt = {
        "ok": True,
        "query_event_id": event_id,
        "outcome": str(args.outcome),
        "outcome_log_file": outcome_log.as_posix(),
    }
    if args.json:
        json.dump(receipt, sys.stdout, ensure_ascii=False, separators=(",", ":"))
        sys.stdout.write("\n")
    else:
        print(f"docs_retrieve_outcome query_event_id={event_id} outcome={args.outcome} log={outcome_log.as_posix()}")
    return 0


def main(argv: list[str]) -> int:
    try:
        return _run(argv)
    except UsageError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return USAGE_ERROR
    except BrokenPipeError:  # pragma: no cover - shell pipeline behavior
        return 0
    except Exception as e:  # pragma: no cover - defensive top-level hardening
        print(f"ERROR: {e}", file=sys.stderr)
        return RUNTIME_ERROR


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

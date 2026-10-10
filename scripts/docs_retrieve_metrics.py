#!/usr/bin/env python3
"""
Summarize docs_retrieve query logs and explicit outcome logs.

Missing outcomes are reported as `not_evaluated`, not as `miss`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path


DEFAULT_QUERY_LOG = ".tmp/planveyor_docs_retrieve_queries.jsonl"
DEFAULT_OUTCOME_LOG = ".tmp/planveyor_docs_retrieve_outcomes.jsonl"
DEFAULT_READ_LOG = ".tmp/planveyor_docs_retrieve_reads.jsonl"
QUERY_LOG_ENV_VAR = "PLANVEYOR_DOCS_RETRIEVE_LOG"
OUTCOME_LOG_ENV_VAR = "PLANVEYOR_DOCS_RETRIEVE_OUTCOME_LOG"
READ_LOG_ENV_VAR = "PLANVEYOR_DOCS_RETRIEVE_READ_LOG"
LOG_DISABLE_VALUES = {"0", "off", "false", "no", "disable", "disabled"}
OUTCOMES = ("used", "partial", "miss", "noise", "not_evaluated")

USAGE_ERROR = 2
RUNTIME_ERROR = 1


class UsageError(RuntimeError):
    """CLI usage/arguments error."""


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


def _load_jsonl(path: Path | None, *, required: bool) -> list[dict[str, object]]:
    if path is None:
        return []
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
        if required:
            raise UsageError(f"log not found: {path}") from e
        return []
    except OSError as e:
        raise RuntimeError(f"cannot read log {path}: {e}") from e
    return rows


def _log_status(path: Path | None) -> str:
    if path is None:
        return "disabled"
    if path.exists():
        return "present"
    return "missing"


def _as_int(value: object) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _latest_outcomes_by_event(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    latest: dict[str, dict[str, object]] = {}
    for row in rows:
        event_id = str(row.get("query_event_id") or "").strip()
        outcome = str(row.get("outcome") or "").strip()
        if not event_id or outcome not in OUTCOMES:
            continue
        latest[event_id] = row
    return latest


def summarize_read_open(read_rows: list[dict[str, object]]) -> dict[str, object]:
    read_events_total = len(read_rows)
    ok_events_total = 0
    error_events_total = 0
    files_total = 0
    returned_bytes_total = 0
    returned_lines_total = 0
    truncated_files_total = 0
    tools: Counter[str] = Counter()
    path_counts: Counter[str] = Counter()
    path_bytes: Counter[str] = Counter()

    def add_path(path: str, *, returned_bytes: int, returned_lines: int, truncated: bool) -> None:
        nonlocal files_total, returned_bytes_total, returned_lines_total, truncated_files_total
        path = str(path or "").strip()
        if not path:
            return
        files_total += 1
        returned_bytes_total += returned_bytes
        returned_lines_total += returned_lines
        if truncated:
            truncated_files_total += 1
        path_counts[path] += 1
        path_bytes[path] += returned_bytes

    for row in read_rows:
        status = str(row.get("status") or "").strip().lower()
        if status == "ok":
            ok_events_total += 1
        else:
            error_events_total += 1
        tool = str(row.get("tool") or "").strip() or "unknown"
        tools[tool] += 1

        files = row.get("files")
        if isinstance(files, list):
            for item in files:
                if not isinstance(item, dict):
                    continue
                add_path(
                    str(item.get("path") or ""),
                    returned_bytes=_as_int(item.get("returned_bytes")),
                    returned_lines=_as_int(item.get("returned_lines")),
                    truncated=_as_bool(item.get("truncated")),
                )
            continue

        add_path(
            str(row.get("path") or ""),
            returned_bytes=_as_int(row.get("returned_bytes")),
            returned_lines=_as_int(row.get("returned_lines")),
            truncated=_as_bool(row.get("truncated")),
        )

    top_paths = [
        {
            "path": path,
            "reads": count,
            "returned_bytes": path_bytes[path],
        }
        for path, count in sorted(path_counts.items(), key=lambda item: (-item[1], item[0]))[:20]
    ]

    return {
        "read_events_total": read_events_total,
        "ok_events_total": ok_events_total,
        "error_events_total": error_events_total,
        "files_total": files_total,
        "unique_paths": len(path_counts),
        "returned_bytes_total": returned_bytes_total,
        "returned_lines_total": returned_lines_total,
        "truncated_files_total": truncated_files_total,
        "tools": dict(sorted(tools.items())),
        "top_paths": top_paths,
    }


def summarize(
    query_rows: list[dict[str, object]],
    outcome_rows: list[dict[str, object]],
    read_rows: list[dict[str, object]] | None = None,
    *,
    used_for_decision: bool = False,
    accepted_no_op_reason: str = "not_used_for_decision",
) -> dict[str, object]:
    latest_outcomes = _latest_outcomes_by_event(outcome_rows)
    read_rows = read_rows or []

    query_total = len(query_rows)
    with_hits = sum(1 for row in query_rows if _as_int(row.get("hits")) > 0)
    zero_hits = sum(1 for row in query_rows if _as_int(row.get("hits")) == 0)
    warnings_total = sum(1 for row in query_rows if row.get("warnings"))
    errors_total = sum(1 for row in query_rows if row.get("error"))
    event_ids = [str(row.get("event_id") or "").strip() for row in query_rows]
    event_ids = [event_id for event_id in event_ids if event_id]
    unique_event_ids = set(event_ids)

    outcome_counts: Counter[str] = Counter({name: 0 for name in OUTCOMES})
    evaluated_event_ids: set[str] = set()
    evaluated_hit_total = 0
    evaluated_zero_hit_total = 0
    for row in query_rows:
        event_id = str(row.get("event_id") or "").strip()
        if not event_id or event_id not in latest_outcomes:
            continue
        outcome = str(latest_outcomes[event_id].get("outcome") or "")
        if outcome not in OUTCOMES:
            continue
        outcome_counts[outcome] += 1
        evaluated_event_ids.add(event_id)
        if _as_int(row.get("hits")) > 0:
            evaluated_hit_total += 1
        else:
            evaluated_zero_hit_total += 1

    evaluated_total = len(evaluated_event_ids)
    not_evaluated_total = max(0, query_total - evaluated_total)
    outcome_counts["not_evaluated"] += not_evaluated_total

    hit_rate = (with_hits / query_total) if query_total else 0.0
    evaluated_hit_rate = (evaluated_hit_total / evaluated_total) if evaluated_total else 0.0
    read_open_summary = summarize_read_open(read_rows)
    outcome_evaluated_rate = (evaluated_total / query_total) if query_total else 1.0
    read_open_rate = (
        min(1.0, int(read_open_summary["read_events_total"]) / query_total) if query_total else 1.0
    )
    process_findings: list[dict[str, object]] = []
    if query_total > 0 and evaluated_total == 0:
        process_findings.append(
            {
                "code": "zero_outcome_coverage",
                "severity": "process_gap",
                "message": "docs_retrieve query log has rows but no evaluated outcome rows.",
            }
        )
    elif query_total > 0 and outcome_evaluated_rate < 0.20:
        process_findings.append(
            {
                "code": "low_outcome_coverage",
                "severity": "process_gap",
                "message": "docs_retrieve outcome coverage is below 20%.",
            }
        )
    if query_total > 0 and int(read_open_summary["read_events_total"]) == 0:
        process_findings.append(
            {
                "code": "zero_read_open_coverage",
                "severity": "process_gap",
                "message": "docs_retrieve query log has rows but no docs_get/docs_multi_get read/open rows.",
            }
        )
    elif query_total > 0 and read_open_rate < 0.05:
        process_findings.append(
            {
                "code": "low_read_open_coverage",
                "severity": "process_gap",
                "message": "docs_get/docs_multi_get read/open coverage is below 5%.",
            }
        )

    return {
        "query_only": {
            "query_total": query_total,
            "with_hits": with_hits,
            "zero_hits": zero_hits,
            "hit_rate": hit_rate,
            "warnings_total": warnings_total,
            "errors_total": errors_total,
            "with_event_id": len(event_ids),
            "unique_event_ids": len(unique_event_ids),
            "missing_event_id_total": query_total - len(event_ids),
        },
        "query_plus_outcome": {
            "evaluated_total": evaluated_total,
            "not_evaluated_total": not_evaluated_total,
            "evaluated_with_hits": evaluated_hit_total,
            "evaluated_zero_hits": evaluated_zero_hit_total,
            "evaluated_hit_rate": evaluated_hit_rate,
            "outcome_evaluated_rate": outcome_evaluated_rate,
            "outcomes": dict(outcome_counts),
            "outcome_rows_total": len(outcome_rows),
        },
        "read_open": {**read_open_summary, "read_open_rate": read_open_rate},
        "decision_usage": {
            "used_for_decision": used_for_decision,
            "accepted_no_op_reason": accepted_no_op_reason,
        },
        "process_findings": process_findings,
        "notes": [
            "Missing outcomes are reported as not_evaluated, not miss.",
            "If multiple outcome rows exist for one query_event_id, the latest row wins.",
            "Read/open telemetry is path-only usage evidence, not a usefulness verdict.",
        ],
    }


def _format_pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def format_text(
    summary: dict[str, object],
    *,
    query_log: Path | None,
    outcome_log: Path | None,
    read_log: Path | None,
    query_log_status: str,
    outcome_log_status: str,
    read_log_status: str,
) -> str:
    query_only = summary["query_only"]  # type: ignore[index]
    query_plus = summary["query_plus_outcome"]  # type: ignore[index]
    read_open = summary["read_open"]  # type: ignore[index]
    decision_usage = summary["decision_usage"]  # type: ignore[index]
    process_findings = summary["process_findings"]  # type: ignore[index]
    outcomes = query_plus["outcomes"]  # type: ignore[index]
    lines = [
        "docs_retrieve_metrics",
        f"query_log: {query_log.as_posix() if query_log else 'disabled'}",
        f"query_log_status: {query_log_status}",
        f"outcome_log: {outcome_log.as_posix() if outcome_log else 'disabled'}",
        f"outcome_log_status: {outcome_log_status}",
        f"read_log: {read_log.as_posix() if read_log else 'disabled'}",
        f"read_log_status: {read_log_status}",
        f"used_for_decision: {str(decision_usage['used_for_decision']).lower()}",
        f"accepted_no_op_reason: {decision_usage['accepted_no_op_reason']}",
        "",
        "query-only baseline:",
        f"  query_total: {query_only['query_total']}",
        f"  with_hits: {query_only['with_hits']}",
        f"  zero_hits: {query_only['zero_hits']}",
        f"  hit_rate: {_format_pct(float(query_only['hit_rate']))}",
        f"  warnings_total: {query_only['warnings_total']}",
        f"  errors_total: {query_only['errors_total']}",
        f"  with_event_id: {query_only['with_event_id']}",
        f"  missing_event_id_total: {query_only['missing_event_id_total']}",
        "",
        "query+outcome view:",
        f"  evaluated_total: {query_plus['evaluated_total']}",
        f"  not_evaluated_total: {query_plus['not_evaluated_total']}",
        f"  evaluated_with_hits: {query_plus['evaluated_with_hits']}",
        f"  evaluated_zero_hits: {query_plus['evaluated_zero_hits']}",
        f"  evaluated_hit_rate: {_format_pct(float(query_plus['evaluated_hit_rate']))}",
        f"  outcome_evaluated_rate: {_format_pct(float(query_plus['outcome_evaluated_rate']))}",
        "  outcomes:",
    ]
    for outcome in OUTCOMES:
        lines.append(f"    {outcome}: {outcomes[outcome]}")
    lines.extend(
        [
            "",
            "read/open view:",
            f"  read_events_total: {read_open['read_events_total']}",
            f"  read_open_rate: {_format_pct(float(read_open['read_open_rate']))}",
            f"  ok_events_total: {read_open['ok_events_total']}",
            f"  error_events_total: {read_open['error_events_total']}",
            f"  files_total: {read_open['files_total']}",
            f"  unique_paths: {read_open['unique_paths']}",
            f"  returned_bytes_total: {read_open['returned_bytes_total']}",
            f"  returned_lines_total: {read_open['returned_lines_total']}",
            f"  truncated_files_total: {read_open['truncated_files_total']}",
            f"  tools: {json.dumps(read_open['tools'], ensure_ascii=False, sort_keys=True)}",
        ]
    )
    lines.extend(
        [
            "",
            "process findings:",
        ]
    )
    if process_findings:
        for finding in process_findings:  # type: ignore[assignment]
            lines.append(f"  - {finding['code']}: {finding['message']}")
    else:
        lines.append("  - none")
    lines.extend(
        [
            "",
            "note: Missing outcomes are reported as not_evaluated, not miss.",
            "note: If multiple outcome rows exist for one query_event_id, the latest row wins.",
            "note: Read/open telemetry is path-only usage evidence, not a usefulness verdict.",
        ]
    )
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Summarize docs_retrieve query/outcome logs.")
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
    parser.add_argument(
        "--read-log",
        default="",
        help=(
            f"docs_get/docs_multi_get read/open log path. Default: {DEFAULT_READ_LOG}; "
            f"override via {READ_LOG_ENV_VAR}=PATH"
        ),
    )
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    parser.add_argument(
        "--used-for-decision",
        choices=["true", "false"],
        default="false",
        help="Whether aggregate retrieval metrics were used as decision evidence.",
    )
    parser.add_argument(
        "--accepted-no-op-reason",
        default="",
        help="Enum-like reason for telemetry-only or accepted low-coverage metrics.",
    )
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
    read_log = _materialize_path(
        _resolve_path(arg_value=args.read_log, env_var=READ_LOG_ENV_VAR, default=DEFAULT_READ_LOG)
    )
    query_log_status = _log_status(query_log)
    outcome_log_status = _log_status(outcome_log)
    read_log_status = _log_status(read_log)
    query_rows = _load_jsonl(query_log, required=False)
    outcome_rows = _load_jsonl(outcome_log, required=False)
    read_rows = _load_jsonl(read_log, required=False)
    used_for_decision = args.used_for_decision == "true"
    accepted_no_op_reason = str(args.accepted_no_op_reason or "").strip()
    if not used_for_decision and not accepted_no_op_reason:
        accepted_no_op_reason = "not_used_for_decision"
    if used_for_decision and accepted_no_op_reason == "not_used_for_decision":
        raise UsageError("accepted_no_op_reason=not_used_for_decision is invalid with --used-for-decision true")
    summary = summarize(
        query_rows,
        outcome_rows,
        read_rows,
        used_for_decision=used_for_decision,
        accepted_no_op_reason=accepted_no_op_reason,
    )

    if args.format == "json":
        payload = {
            "ok": True,
            "query_log": "" if query_log is None else query_log.as_posix(),
            "query_log_status": query_log_status,
            "outcome_log": "" if outcome_log is None else outcome_log.as_posix(),
            "outcome_log_status": outcome_log_status,
            "read_log": "" if read_log is None else read_log.as_posix(),
            "read_log_status": read_log_status,
            "summary": summary,
        }
        json.dump(payload, sys.stdout, ensure_ascii=False, separators=(",", ":"))
        sys.stdout.write("\n")
    else:
        print(
            format_text(
                summary,
                query_log=query_log,
                outcome_log=outcome_log,
                read_log=read_log,
                query_log_status=query_log_status,
                outcome_log_status=outcome_log_status,
                read_log_status=read_log_status,
            )
        )
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

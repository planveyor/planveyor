#!/usr/bin/env python3
"""Read-only per-wave telemetry and retrieval-corpus report."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import plan_status_oracle


SCHEMA_VERSION = "wave_telemetry_report.v1"
DEFAULT_JSON_OUT = ".tmp/wave_telemetry_report.json"
DEFAULT_QUERY_LOG = ".tmp/planveyor_docs_retrieve_queries.jsonl"
DEFAULT_OUTCOME_LOG = ".tmp/planveyor_docs_retrieve_outcomes.jsonl"
DEFAULT_READ_LOG = ".tmp/planveyor_docs_retrieve_reads.jsonl"
PLAN_REF_RE = re.compile(r"docs/plans/[A-Za-z0-9_./-]+\.md")
WAVE_LABELS = ("analysis_wave", "decomposition_wave", "developer_wave", "unknown")


@dataclass(frozen=True)
class PlanDoc:
    path: Path
    rel_path: str
    title: str
    status: str | None
    meta_read: plan_status_oracle.StrictPlanMetaJsonResult
    text: str

    @property
    def plan_meta(self) -> dict[str, Any]:
        if self.meta_read.state == "valid" and isinstance(self.meta_read.plan_meta, dict):
            return dict(self.meta_read.plan_meta)
        return {}

    @property
    def status_norm(self) -> str:
        return _normalize(self.status)


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _rel(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _resolve(root: Path, raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else root / path


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _status_from_text(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("##"):
            break
        if stripped.startswith("**Status:**"):
            value = stripped[len("**Status:**") :].strip()
            return value or None
    return None


def _title_from_text(text: str, rel_path: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return rel_path


def _section_text(markdown: str, heading: str) -> str:
    wanted = _normalize(heading)
    in_section = False
    lines: list[str] = []
    for line in markdown.splitlines():
        match = re.match(r"^\s*##\s+(.+?)\s*$", line)
        if match:
            current = _normalize(match.group(1).strip())
            if in_section:
                break
            suffix = current[len(wanted) :] if current.startswith(wanted) else ""
            in_section = current == wanted or suffix.startswith((" ", "(", ":", "-"))
            continue
        if in_section:
            lines.append(line)
    return "\n".join(lines).strip()


def _table_value(section: str, key: str) -> str | None:
    key_norm = _normalize(key)
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip().strip("`") for cell in stripped.strip("|").split("|")]
        if len(cells) < 2:
            continue
        if set(cells[0]) <= {"-", ":", " "}:
            continue
        if _normalize(cells[0]) == key_norm:
            return cells[1].strip() or None
    return None


def _route_label(value: Any) -> str:
    raw = str(value or "").strip().strip("`<> ")
    normalized = _normalize(raw)
    for route in ("developer_wave", "decomposition_wave", "analysis_wave", "human_gate", "defer", "reject"):
        if route in normalized:
            return route
    return raw or "unknown"


def _load_jsonl(path: Path) -> tuple[list[dict[str, Any]], str]:
    if not path.exists():
        return [], "missing"
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
    return rows, "present"


def load_plans(root: Path) -> list[PlanDoc]:
    plans_root = root / "docs/plans"
    if not plans_root.exists():
        return []
    docs: list[PlanDoc] = []
    for path in sorted(plans_root.glob("*.md")):
        if path.name.startswith("_"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        rel_path = _rel(root, path)
        docs.append(
            PlanDoc(
                path=path,
                rel_path=rel_path,
                title=_title_from_text(text, rel_path),
                status=_status_from_text(text),
                meta_read=plan_status_oracle.strict_plan_meta_json(text),
                text=text,
            )
        )
    return docs


def _promoted_from(plan: PlanDoc) -> dict[str, Any] | None:
    value = plan.plan_meta.get("promoted_from")
    if not isinstance(value, dict):
        return None
    route = _route_label(value.get("accepted_route"))
    if not route or route == "unknown":
        return None
    return {
        "accepted_route": route,
        "promoted_artifact_ref": str(value.get("promoted_artifact_ref") or "").strip() or "unknown",
        "truth_host": f"{plan.rel_path}#plan_meta.promoted_from",
    }


def _promoted_section(plan: PlanDoc) -> dict[str, Any] | None:
    section = _section_text(plan.text, "Promoted route artifact")
    if not section or section.strip().startswith("N/A"):
        return None
    route = _table_value(section, "accepted_route") or _table_value(section, "Accepted route")
    if not route:
        return None
    return {
        "accepted_route": _route_label(route),
        "promoted_artifact_ref": _table_value(section, "promoted_artifact_ref") or "unknown",
        "truth_host": f"{plan.rel_path}#Promoted route artifact",
    }


def _add_diag(
    diagnostics: list[dict[str, Any]],
    *,
    severity: str,
    code: str,
    truth_host: str,
    detail: str,
    plan: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    item: dict[str, Any] = {
        "severity": severity,
        "code": code,
        "truth_host": truth_host,
        "detail": detail,
    }
    if plan:
        item["plan"] = plan
    if extra:
        item.update(extra)
    diagnostics.append(item)


def _classify_plan(plan: PlanDoc, diagnostics: list[dict[str, Any]]) -> str:
    if plan.meta_read.state != "valid":
        _add_diag(
            diagnostics,
            severity="warning",
            code="plan_meta_strict_read_failed",
            plan=plan.rel_path,
            truth_host=f"{plan.rel_path}#plan_meta",
            detail=(
                f"reader_state={plan.meta_read.state}; reason_code={plan.meta_read.reason_code}; "
                f"{plan.meta_read.reason}; wave/promoted_from carriers are unknown."
            ),
            extra={"reason_code": plan.meta_read.reason_code},
        )
    meta = plan.plan_meta
    wave_family = str(meta.get("wave_family") or "").strip()
    phase_overlay = str(meta.get("phase_overlay") or "").strip()
    promoted_meta = _promoted_from(plan)
    promoted_section = _promoted_section(plan)

    if promoted_meta and promoted_section and promoted_meta["accepted_route"] != promoted_section["accepted_route"]:
        _add_diag(
            diagnostics,
            severity="error",
            code="promoted_route_conflict",
            plan=plan.rel_path,
            truth_host=f"{promoted_meta['truth_host']}|{promoted_section['truth_host']}",
            detail="plan_meta.promoted_from accepted_route conflicts with Promoted route artifact.",
            extra={"meta_route": promoted_meta["accepted_route"], "section_route": promoted_section["accepted_route"]},
        )

    if wave_family == "analysis_wave":
        return "analysis_wave"
    if phase_overlay == "decomposition_wave":
        return "decomposition_wave"
    if promoted_meta and promoted_meta["accepted_route"] == "developer_wave":
        return "developer_wave"
    if promoted_section and promoted_section["accepted_route"] == "developer_wave":
        return "developer_wave"

    prose = _normalize(_section_text(plan.text, "Analysis pack") + "\n" + plan.text[:2000])
    prose_markers = [label for label in ("analysis_wave", "decomposition_wave", "developer_wave") if label in prose]
    if prose_markers:
        _add_diag(
            diagnostics,
            severity="warning",
            code="ambiguous_prose_wave_marker",
            plan=plan.rel_path,
            truth_host=f"{plan.rel_path}#prose",
            detail="Wave-like prose marker exists without repo-backed wave carrier; reporter leaves wave as unknown.",
            extra={"markers": prose_markers},
        )
    return "unknown"


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _event_id(row: dict[str, Any]) -> str:
    return str(row.get("event_id") or row.get("query_event_id") or "").strip()


def _summarize_retrieval(
    *,
    root: Path,
    query_rows: list[dict[str, Any]],
    outcome_rows: list[dict[str, Any]],
    read_rows: list[dict[str, Any]],
    query_log_status: str,
    outcome_log_status: str,
    read_log_status: str,
    diagnostics: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    query_ids = {_event_id(row) for row in query_rows if _event_id(row)}
    outcome_ids = {str(row.get("query_event_id") or "").strip() for row in outcome_rows if row.get("query_event_id")}
    unmatched_outcomes = sorted(outcome_ids - query_ids)
    if unmatched_outcomes:
        _add_diag(
            diagnostics,
            severity="error",
            code="outcome_without_query",
            truth_host="docs_retrieve outcome log",
            detail="Outcome rows reference query_event_id values that are absent from the query log.",
            extra={"query_event_ids": unmatched_outcomes[:20]},
        )

    latest_outcomes: dict[str, dict[str, Any]] = {}
    for row in outcome_rows:
        event_id = str(row.get("query_event_id") or "").strip()
        if event_id:
            latest_outcomes[event_id] = row

    outcome_counts: Counter[str] = Counter()
    for row in query_rows:
        event_id = _event_id(row)
        outcome = str(latest_outcomes.get(event_id, {}).get("outcome") or "not_evaluated")
        outcome_counts[outcome] += 1

    read_tools: Counter[str] = Counter()
    path_counts: Counter[str] = Counter()
    missing_paths: list[str] = []
    read_files_total = 0

    def add_read_path(path_value: Any) -> None:
        nonlocal read_files_total
        path = str(path_value or "").strip()
        if not path:
            return
        read_files_total += 1
        path_counts[path] += 1
        resolved = root / path if not Path(path).is_absolute() else Path(path)
        if not resolved.exists() and path not in missing_paths:
            missing_paths.append(path)

    for row in read_rows:
        read_tools[str(row.get("tool") or "unknown")] += 1
        files = row.get("files")
        if isinstance(files, list):
            for item in files:
                if isinstance(item, dict):
                    add_read_path(item.get("path"))
            continue
        add_read_path(row.get("path"))

    if missing_paths:
        _add_diag(
            diagnostics,
            severity="error",
            code="read_open_missing_path",
            truth_host="docs_retrieve read/open log",
            detail="Read/open log references paths that do not exist in this repo root.",
            extra={"paths": missing_paths[:20]},
        )

    for status, label in (
        (query_log_status, "retrieval_query_log_missing"),
        (outcome_log_status, "retrieval_outcome_log_missing"),
        (read_log_status, "retrieval_read_log_missing"),
    ):
        if status == "missing":
            _add_diag(
                diagnostics,
                severity="warning",
                code=label,
                truth_host=".tmp/planveyor_docs_retrieve_*.jsonl",
                detail="Optional local retrieval telemetry log is absent; related report fields are not_available.",
            )

    retrieval_metrics = {
        "query_total": len(query_rows),
        "queries_with_hits": sum(1 for row in query_rows if _as_int(row.get("hits")) > 0),
        "outcome_rows_total": len(outcome_rows),
        "matched_outcome_rows": len(outcome_ids & query_ids),
        "unmatched_outcome_event_ids": unmatched_outcomes[:50],
        "outcomes": dict(sorted(outcome_counts.items())),
        "state": "available" if query_log_status == "present" else "not_available",
    }
    read_open_metrics = {
        "read_events_total": len(read_rows),
        "read_files_total": read_files_total,
        "unique_paths": len(path_counts),
        "missing_paths": missing_paths[:50],
        "tools": dict(sorted(read_tools.items())),
        "state": "available" if read_log_status == "present" else "not_available",
    }
    retrieval_corpus = {
        "opened_paths": sorted(path_counts),
        "top_paths": [
            {"path": path, "reads": count}
            for path, count in sorted(path_counts.items(), key=lambda item: (-item[1], item[0]))[:20]
        ],
        "source": "local .tmp docs_retrieve logs",
        "raw_log_imported": False,
    }
    return retrieval_metrics, read_open_metrics, retrieval_corpus


def _review_counts(root: Path, plans: list[PlanDoc]) -> dict[str, Any]:
    status_counts: Counter[str] = Counter()
    review_root = root / "docs/code_reviews"
    if review_root.exists():
        for path in review_root.glob("*.md"):
            text = path.read_text(encoding="utf-8", errors="replace")
            status = _status_from_text(text) or "unknown"
            status_counts[status] += 1
    censor_mentions = 0
    for plan in plans:
        censor_mentions += len(re.findall(r"\([A-Za-z ]*CENSOR\)", plan.text))
    return {
        "censor_evidence_mentions": censor_mentions,
        "review_artifacts_total": sum(status_counts.values()),
        "review_artifacts_by_status": dict(sorted(status_counts.items())),
    }


def build_report(
    *,
    root: Path,
    json_out: Path,
    generated_at: str,
    query_log: Path,
    outcome_log: Path,
    read_log: Path,
) -> dict[str, Any]:
    diagnostics: list[dict[str, Any]] = []
    plans = load_plans(root)
    plans_by_wave: dict[str, list[dict[str, Any]]] = {label: [] for label in WAVE_LABELS}
    status_counts: Counter[str] = Counter()
    for plan in plans:
        wave = _classify_plan(plan, diagnostics)
        status = plan.status or "unknown"
        status_counts[status] += 1
        plans_by_wave[wave].append({"plan": plan.rel_path, "status": status, "title": plan.title})

    query_rows, query_log_status = _load_jsonl(query_log)
    outcome_rows, outcome_log_status = _load_jsonl(outcome_log)
    read_rows, read_log_status = _load_jsonl(read_log)
    retrieval_metrics, read_open_metrics, retrieval_corpus = _summarize_retrieval(
        root=root,
        query_rows=query_rows,
        outcome_rows=outcome_rows,
        read_rows=read_rows,
        query_log_status=query_log_status,
        outcome_log_status=outcome_log_status,
        read_log_status=read_log_status,
        diagnostics=diagnostics,
    )

    if any(item["severity"] == "error" for item in diagnostics):
        confidence = {"status": "low", "reason": "red_truth_host_diagnostics_present"}
    elif diagnostics:
        confidence = {"status": "medium", "reason": "missing_or_ambiguous_source_diagnostics_present"}
    else:
        confidence = {"status": "high", "reason": "all_available_sources_consistent"}

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "inputs": {
            "root": root.as_posix(),
            "plans_glob": "docs/plans/*.md",
            "plan_count": len(plans),
            "query_log": _rel(root, query_log),
            "outcome_log": _rel(root, outcome_log),
            "read_log": _rel(root, read_log),
            "json_out": _rel(root, json_out),
        },
        "source_availability": {
            "plans": "available" if plans else "not_available",
            "retrieval_query_log": query_log_status,
            "retrieval_outcome_log": outcome_log_status,
            "retrieval_read_log": read_log_status,
            "session_stats": "not_available",
            "cost_fields": "not_available",
            "raw_target_repo_logs_imported": False,
        },
        "plans_by_wave": plans_by_wave,
        "wave_counts": {label: len(rows) for label, rows in plans_by_wave.items()},
        "plans_by_status": dict(sorted(status_counts.items())),
        "retrieval_metrics": retrieval_metrics,
        "read_open_metrics": read_open_metrics,
        "retrieval_corpus": retrieval_corpus,
        "censor_review_counts": _review_counts(root, plans),
        "runner_class": {
            "state": "unknown",
            "reason": "No explicit session/runner telemetry carrier was provided to this V1 reporter.",
        },
        "session_metrics": {
            "state": "unknown",
            "turns": "unknown",
            "sessions": "unknown",
            "reason": "No explicit sanitized session metrics source was provided.",
        },
        "cost_fields": {
            "state": "unknown",
            "tokens": "unknown",
            "cost": "unknown",
            "reason": "No explicit billing/session-cost carrier was provided; reporter does not infer values.",
        },
        "truth_source_boundary": {
            "wave_truth_sources": ["plan_meta.wave_family", "plan_meta.phase_overlay", "plan_meta.promoted_from"],
            "retrieval_truth_sources": ["local docs_retrieve query/outcome/read-open JSONL logs"],
            "filename_or_prose_wave_truth": False,
            "raw_log_import": False,
            "helper_is_read_only": True,
        },
        "confidence": {**confidence, "diagnostics": diagnostics},
    }


def render_text(payload: dict[str, Any], *, markdown: bool = False) -> str:
    prefix = "- " if markdown else "  "
    title = "## wave-telemetry-report" if markdown else "wave-telemetry-report:"
    confidence = payload["confidence"]
    lines = [
        title,
        f"{prefix}schema_version: {payload['schema_version']}",
        f"{prefix}confidence: {confidence['status']} ({confidence['reason']})",
        f"{prefix}plan_count: {payload['inputs']['plan_count']}",
        f"{prefix}wave_counts: {json.dumps(payload['wave_counts'], ensure_ascii=False, sort_keys=True)}",
        f"{prefix}retrieval_state: query={payload['source_availability']['retrieval_query_log']} outcome={payload['source_availability']['retrieval_outcome_log']} read={payload['source_availability']['retrieval_read_log']}",
        f"{prefix}retrieval_queries: {payload['retrieval_metrics']['query_total']}",
        f"{prefix}read_open_unique_paths: {payload['read_open_metrics']['unique_paths']}",
        f"{prefix}session_metrics: {payload['session_metrics']['state']}",
        f"{prefix}cost_fields: {payload['cost_fields']['state']}",
        f"{prefix}diagnostics: {len(confidence['diagnostics'])}",
    ]
    if payload["retrieval_corpus"]["top_paths"]:
        lines.append(f"{prefix}top_read_paths:")
        for item in payload["retrieval_corpus"]["top_paths"][:5]:
            lines.append(f"{prefix}  - {item['path']} reads={item['reads']}")
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repo root")
    parser.add_argument("--json-out", default=DEFAULT_JSON_OUT, help="Write report JSON to this path")
    parser.add_argument("--query-log", default=DEFAULT_QUERY_LOG, help="docs_retrieve query JSONL log")
    parser.add_argument("--outcome-log", default=DEFAULT_OUTCOME_LOG, help="docs_retrieve outcome JSONL log")
    parser.add_argument("--read-log", default=DEFAULT_READ_LOG, help="docs_get/docs_multi_get read/open JSONL log")
    parser.add_argument("--generated-at", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--json", action="store_true", help="Print JSON payload to stdout")
    parser.add_argument("--format", choices=("text", "markdown"), default="text", help="Plain-output format")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    json_out = _resolve(root, args.json_out)
    payload = build_report(
        root=root,
        json_out=json_out,
        generated_at=args.generated_at or _now_utc(),
        query_log=_resolve(root, args.query_log),
        outcome_log=_resolve(root, args.outcome_log),
        read_log=_resolve(root, args.read_log),
    )
    _write_json(json_out, payload)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_text(payload, markdown=args.format == "markdown"))
        print(f"wrote {_rel(root, json_out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

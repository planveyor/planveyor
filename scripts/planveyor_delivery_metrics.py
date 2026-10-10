#!/usr/bin/env python3
"""Derive bounded delivery metrics and a generated scorecard from repo traces."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_TRACE_JSONL_REL = ".tmp/planveyor_trace_events.jsonl"
DEFAULT_ATTRIBUTION_JSONL_REL = ".tmp/planveyor_failure_attribution.jsonl"
DEFAULT_METRICS_JSON_REL = ".tmp/planveyor_delivery_metrics.json"
DEFAULT_SCORECARD_MD_REL = "docs/reviews/planveyor_delivery_scorecard.md"
REVIEW_EVENT_TYPES = ("review.code.single_commit", "review.doc.single_commit")
POSITIVE_REVIEW_EVENT_TYPES = {
    "review.code.single_commit",
    "review.doc.single_commit",
    "review.code.merge_range",
    "review.doc.merge_range",
}


def _collapse_space(value: str) -> str:
    return " ".join(value.split())


def _normalize_status(value: str) -> str:
    return _collapse_space(value).strip().lower()


def _classify_review_status(value: str) -> str:
    normalized = _normalize_status(value)
    if not normalized:
        return "other"
    if "no blockers" in normalized:
        return "success"
    if "❌" in normalized or "blocker" in normalized:
        return "blocked"
    if normalized.startswith("✅") or "no blockers" in normalized or normalized in {"ok", "done"}:
        return "success"
    return "other"


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _parse_ts(value: str) -> datetime | None:
    raw = value.strip()
    if not raw:
        return None
    candidate = raw
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    elif candidate.endswith(" MSK"):
        # Legacy label of stamps written before the engine switched to local numeric offsets.
        candidate = candidate[:-4] + "+03:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_ts(value: datetime | None) -> str:
    if value is None:
        return "N/A"
    return value.isoformat().replace("+00:00", "Z")


def _round(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 2)


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _percent(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.1f}%"


def _format_number(value: float | int | None) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, int):
        return str(value)
    return f"{value:.2f}"


def _has_literal_trace_id(value: str) -> bool:
    normalized = value.strip()
    return bool(normalized and not normalized.startswith("N/A"))


def _is_literal_finding_ref(value: str) -> bool:
    normalized = value.strip()
    return bool(normalized and not normalized.startswith("N/A"))


def _display_path(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())


def _event_plan_path(event: dict[str, Any]) -> str | None:
    payload = event.get("payload") or {}
    plan_paths = [str(item).strip() for item in payload.get("plan_paths") or [] if str(item).strip()]
    if len(plan_paths) == 1:
        return plan_paths[0]
    return None


def _filter_failure_rows(
    rows: list[dict[str, Any]],
    event_lookup: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    counted: list[dict[str, Any]] = []
    excluded_positive_review = 0
    for row in rows:
        payload = row.get("payload") or {}
        source_event_id = str(payload.get("source_event_id") or "")
        source_event = event_lookup.get(source_event_id)
        if source_event is not None and str(payload.get("source_event_type") or "") in POSITIVE_REVIEW_EVENT_TYPES:
            status = str((source_event.get("payload") or {}).get("status") or "")
            if _classify_review_status(status) == "success":
                excluded_positive_review += 1
                continue
        counted.append(row)
    return counted, excluded_positive_review


def build_metrics(
    events: list[dict[str, Any]],
    failure_rows: list[dict[str, Any]],
    *,
    generated_at: str,
    trace_jsonl_path: str,
    attribution_jsonl_path: str,
    metrics_json_path: str,
    scorecard_path: str,
) -> dict[str, Any]:
    event_lookup = {str(event.get("event_id") or ""): event for event in events}
    counted_failure_rows, excluded_positive_review = _filter_failure_rows(failure_rows, event_lookup)

    event_timestamps = [_parse_ts(str(event.get("ts") or "")) for event in events]
    row_timestamps = [_parse_ts(str(row.get("ts") or "")) for row in counted_failure_rows]
    coverage_points = [value for value in (*event_timestamps, *row_timestamps) if value is not None]
    coverage_from = min(coverage_points) if coverage_points else None
    coverage_to = max(coverage_points) if coverage_points else None
    coverage_span_hours = (
        _round((coverage_to - coverage_from).total_seconds() / 3600.0)
        if coverage_from is not None and coverage_to is not None
        else None
    )

    review_events_total = 0
    review_events_decisive = 0
    review_events_excluded_ambiguous_plan_paths = 0
    review_events_excluded_non_decisive_status = 0
    eligible_review_events: list[dict[str, Any]] = []
    lane_map: defaultdict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    event_id_to_lane: dict[str, tuple[str, str]] = {}

    for index, event in enumerate(events):
        event_type = str(event.get("event_type") or "")
        if event_type not in REVIEW_EVENT_TYPES:
            continue
        review_events_total += 1
        payload = event.get("payload") or {}
        status = str(payload.get("status") or "")
        status_class = _classify_review_status(status)
        if status_class == "other":
            review_events_excluded_non_decisive_status += 1
            continue
        review_events_decisive += 1
        plan_path = _event_plan_path(event)
        if plan_path is None:
            review_events_excluded_ambiguous_plan_paths += 1
            continue
        parsed_ts = _parse_ts(str(event.get("ts") or ""))
        lane_key = (plan_path, event_type)
        record = {
            "event_id": str(event.get("event_id") or ""),
            "event_type": event_type,
            "plan_path": plan_path,
            "status": status,
            "status_class": status_class,
            "source_path": str(event.get("source_path") or ""),
            "ts": str(event.get("ts") or ""),
            "ts_parsed": parsed_ts,
            "sort_key": (
                parsed_ts.isoformat() if parsed_ts is not None else "",
                index,
            ),
        }
        eligible_review_events.append(record)
        lane_map[lane_key].append(record)
        event_id_to_lane[record["event_id"]] = lane_key

    total_cycles = len(eligible_review_events)
    lane_stats: list[dict[str, Any]] = []
    blocked_or_escalated_lanes: set[tuple[str, str]] = set()
    governance_escalation_lanes: set[tuple[str, str]] = set()

    for lane_key, records in lane_map.items():
        ordered = sorted(records, key=lambda item: item["sort_key"])
        cycle_count = len(ordered)
        first_record = ordered[0]
        blocked = any(item["status_class"] == "blocked" for item in ordered)
        if blocked:
            blocked_or_escalated_lanes.add(lane_key)
        timestamps = [item["ts_parsed"] for item in ordered if item["ts_parsed"] is not None]
        span_hours = None
        if cycle_count > 1 and len(timestamps) >= 2:
            span_hours = _round((max(timestamps) - min(timestamps)).total_seconds() / 3600.0)
        lane_stats.append(
            {
                "lane_key": lane_key,
                "cycle_count": cycle_count,
                "first_status_class": first_record["status_class"],
                "blocked": blocked,
                "span_hours": span_hours,
            }
        )

    for row in counted_failure_rows:
        payload = row.get("payload") or {}
        if str(payload.get("failure_code") or "") != "GOVERNANCE_BLOCK":
            continue
        lane_key = event_id_to_lane.get(str(payload.get("source_event_id") or ""))
        if lane_key is None:
            continue
        governance_escalation_lanes.add(lane_key)
        blocked_or_escalated_lanes.add(lane_key)

    lanes_considered = len(lane_stats)
    cycle_counts = [item["cycle_count"] for item in lane_stats]
    first_pass_success_count = sum(1 for item in lane_stats if item["first_status_class"] == "success")
    rework_lanes = sum(1 for item in lane_stats if item["cycle_count"] > 1)
    blocked_or_escalated_lane_count = len(blocked_or_escalated_lanes)
    blocked_review_events = sum(1 for item in eligible_review_events if item["status_class"] == "blocked")

    failure_distribution = Counter(str((row.get("payload") or {}).get("failure_code") or "UNKNOWN") for row in counted_failure_rows)
    literal_finding_refs = sum(
        1 for row in counted_failure_rows if _is_literal_finding_ref(str((row.get("payload") or {}).get("finding_ref") or ""))
    )
    inferred_finding_refs = len(counted_failure_rows) - literal_finding_refs
    distinct_failure_source_events = len(
        {
            str((row.get("payload") or {}).get("source_event_id") or "")
            for row in counted_failure_rows
            if str((row.get("payload") or {}).get("source_event_id") or "").strip()
        }
    )

    latency_spans = [item["span_hours"] for item in lane_stats if item["span_hours"] is not None]
    literal_trace_id_events = sum(1 for event in events if _has_literal_trace_id(str(event.get("trace_id") or "")))

    metrics = {
        "schema_version": "delivery_metrics.v1",
        "generated_at": generated_at,
        "inputs": {
            "trace_jsonl": trace_jsonl_path,
            "failure_attribution_jsonl": attribution_jsonl_path,
            "metrics_json": metrics_json_path,
            "scorecard_markdown": scorecard_path,
            "trace_event_count": len(events),
            "failure_row_count_total": len(failure_rows),
            "failure_row_count_counted": len(counted_failure_rows),
        },
        "coverage_window": {
            "from": _format_ts(coverage_from),
            "to": _format_ts(coverage_to),
            "span_hours": coverage_span_hours,
            "source": "combined trace-event and counted failure-attribution timestamps",
        },
        "trace_coverage": {
            "literal_trace_id_events": literal_trace_id_events,
            "literal_trace_id_rate": _ratio(literal_trace_id_events, len(events)),
            "review_events_total": review_events_total,
            "review_events_decisive": review_events_decisive,
            "review_events_unit_eligible": total_cycles,
            "review_events_excluded_ambiguous_plan_paths": review_events_excluded_ambiguous_plan_paths,
            "review_events_excluded_non_decisive_status": review_events_excluded_non_decisive_status,
            "failure_rows_excluded_positive_review_false_positive": excluded_positive_review,
        },
        "metrics": {
            "inner_loop_cycles": {
                "identity_rule": "single-plan-path review.code.single_commit / review.doc.single_commit lanes only",
                "review_lanes_considered": lanes_considered,
                "review_events_considered": total_cycles,
                "average_cycles_per_lane": _round(statistics.mean(cycle_counts)) if cycle_counts else None,
                "median_cycles_per_lane": _round(statistics.median(cycle_counts)) if cycle_counts else None,
                "rework_lanes": rework_lanes,
                "rework_rate": _ratio(rework_lanes, lanes_considered),
                "max_cycles_per_lane": max(cycle_counts) if cycle_counts else 0,
            },
            "first_pass_success": {
                "success_lanes": first_pass_success_count,
                "review_lanes_considered": lanes_considered,
                "rate": _ratio(first_pass_success_count, lanes_considered),
            },
            "blocked_or_escalated": {
                "blocked_or_escalated_lanes": blocked_or_escalated_lane_count,
                "review_lanes_considered": lanes_considered,
                "rate": _ratio(blocked_or_escalated_lane_count, lanes_considered),
                "blocked_review_events": blocked_review_events,
                "blocked_review_event_rate": _ratio(blocked_review_events, total_cycles),
                "governance_escalation_lanes": len(governance_escalation_lanes),
            },
            "failure_distribution": {
                "rows_counted": len(counted_failure_rows),
                "by_failure_code": dict(sorted(failure_distribution.items())),
            },
            "review_findings": {
                "counted_findings": len(counted_failure_rows),
                "literal_finding_refs": literal_finding_refs,
                "inferred_finding_refs": inferred_finding_refs,
                "distinct_source_events": distinct_failure_source_events,
            },
            "latency": {
                "metric": "review-loop span only",
                "supported_lanes": len(latency_spans),
                "median_review_loop_span_hours": _round(statistics.median(latency_spans)) if latency_spans else None,
                "average_review_loop_span_hours": _round(statistics.mean(latency_spans)) if latency_spans else None,
                "max_review_loop_span_hours": max(latency_spans) if latency_spans else None,
            },
        },
        "confidence": {
            "unit_metrics": {
                "level": "bounded",
                "summary": "Only decisive single-plan review.code.single_commit / review.doc.single_commit lanes count toward first-pass, blocked ratio, and inner-loop cycles.",
            },
            "failure_attribution": {
                "level": "partial",
                "summary": "Failure distribution is counted from compact attribution rows after excluding rows attached to positive review verdicts.",
            },
            "latency": {
                "level": "partial",
                "summary": "Only first-to-last review-loop span is supported; end-to-end implementation latency is not derivable from the current substrate.",
            },
            "trace_lineage": {
                "level": "low" if literal_trace_id_events == 0 else "partial",
                "summary": "Literal trace_id coverage remains sparse, so v1 identity uses plan-path + review-family lanes instead of full run lineage.",
            },
        },
        "omitted_metrics": [
            {
                "name": "complexity_adjusted_throughput",
                "reason": "Current repo-local traces do not expose a trustworthy complexity denominator.",
            },
            {
                "name": "ai_velocity_multiplier",
                "reason": "No truthful baseline/comparator exists in the extracted repo-native substrate.",
            },
            {
                "name": "end_to_end_task_latency",
                "reason": "The current traces do not expose one reliable implementation-start boundary for each review lane.",
            },
            {
                "name": "queue_wait_time",
                "reason": "Queue entry/exit boundaries are not materialized consistently enough for a first-wave scorecard.",
            },
        ],
    }
    return metrics


def render_scorecard(metrics: dict[str, Any]) -> str:
    inner = metrics["metrics"]["inner_loop_cycles"]
    first_pass = metrics["metrics"]["first_pass_success"]
    blocked = metrics["metrics"]["blocked_or_escalated"]
    failure_distribution = metrics["metrics"]["failure_distribution"]
    findings = metrics["metrics"]["review_findings"]
    latency = metrics["metrics"]["latency"]
    coverage = metrics["coverage_window"]
    trace_coverage = metrics["trace_coverage"]
    confidence = metrics["confidence"]

    failure_mix = ", ".join(
        f"`{code}`={count}" for code, count in sorted(failure_distribution["by_failure_code"].items())
    ) or "N/A"

    lines = [
        "# Delivery scorecard — trace-derived",
        "",
        "- Источник истины: только `.tmp/planveyor_trace_events.jsonl` и `.tmp/planveyor_failure_attribution.jsonl`; этот markdown остаётся generated summary, а не вторым SoT.",
        f"- Сгенерировано: `{metrics['generated_at']}`",
        f"- Coverage window: `{coverage['from']}` -> `{coverage['to']}` (`span_hours={_format_number(coverage['span_hours'])}`)",
        f"- Inputs: trace events = `{metrics['inputs']['trace_event_count']}`, failure rows = `{metrics['inputs']['failure_row_count_total']}`, counted failure rows = `{metrics['inputs']['failure_row_count_counted']}`",
        "",
        "## First-wave metrics",
        f"- Inner loop cycles: `{inner['review_events_considered']}` decisive review events across `{inner['review_lanes_considered']}` single-plan review lanes; avg = `{_format_number(inner['average_cycles_per_lane'])}`, median = `{_format_number(inner['median_cycles_per_lane'])}`, rework lanes = `{inner['rework_lanes']}` ({_percent(inner['rework_rate'])}).",
        f"- First-pass success: `{first_pass['success_lanes']}/{first_pass['review_lanes_considered']}` lanes ({_percent(first_pass['rate'])}).",
        f"- Blocked/escalated ratio: `{blocked['blocked_or_escalated_lanes']}/{blocked['review_lanes_considered']}` lanes ({_percent(blocked['rate'])}); blocked events = `{blocked['blocked_review_events']}/{inner['review_events_considered']}` ({_percent(blocked['blocked_review_event_rate'])}), governance escalations = `{blocked['governance_escalation_lanes']}`.",
        f"- Failure-class distribution: {failure_mix}.",
        f"- Review findings: counted = `{findings['counted_findings']}`, literal refs = `{findings['literal_finding_refs']}`, inferred refs = `{findings['inferred_finding_refs']}`, distinct source events = `{findings['distinct_source_events']}`.",
        f"- Bounded latency fact: review-loop span supported on `{latency['supported_lanes']}` reworked lanes; median = `{_format_number(latency['median_review_loop_span_hours'])}` h, avg = `{_format_number(latency['average_review_loop_span_hours'])}` h, max = `{_format_number(latency['max_review_loop_span_hours'])}` h.",
        "",
        "## Coverage / confidence",
        f"- Unit metrics (`{confidence['unit_metrics']['level']}`): {confidence['unit_metrics']['summary']}",
        f"- Failure attribution (`{confidence['failure_attribution']['level']}`): {confidence['failure_attribution']['summary']} Excluded positive-review false positives = `{trace_coverage['failure_rows_excluded_positive_review_false_positive']}`.",
        f"- Trace lineage (`{confidence['trace_lineage']['level']}`): {confidence['trace_lineage']['summary']} Literal trace_id coverage = `{trace_coverage['literal_trace_id_events']}/{metrics['inputs']['trace_event_count']}` ({_percent(trace_coverage['literal_trace_id_rate'])}).",
        f"- Eligibility filter: total review events = `{trace_coverage['review_events_total']}`, decisive = `{trace_coverage['review_events_decisive']}`, eligible single-plan lanes = `{trace_coverage['review_events_unit_eligible']}`, excluded ambiguous plan-path reviews = `{trace_coverage['review_events_excluded_ambiguous_plan_paths']}`, excluded non-decisive statuses = `{trace_coverage['review_events_excluded_non_decisive_status']}`.",
        f"- Latency (`{confidence['latency']['level']}`): {confidence['latency']['summary']}",
        "",
        "## Omitted metrics",
    ]
    for item in metrics["omitted_metrics"]:
        lines.append(f"- `{item['name']}`: {item['reason']}")
    lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Derive bounded delivery metrics and a generated scorecard from canonical trace artifacts."
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Repository root used to resolve default inputs/outputs (default: current directory).",
    )
    parser.add_argument(
        "--trace-jsonl",
        help=f"Override trace JSONL path (default: <root>/{DEFAULT_TRACE_JSONL_REL}).",
    )
    parser.add_argument(
        "--attribution-jsonl",
        help=f"Override failure-attribution JSONL path (default: <root>/{DEFAULT_ATTRIBUTION_JSONL_REL}).",
    )
    parser.add_argument(
        "--json-out",
        help=f"Override metrics JSON output path (default: <root>/{DEFAULT_METRICS_JSON_REL}).",
    )
    parser.add_argument(
        "--markdown-out",
        help=f"Override scorecard markdown output path (default: <root>/{DEFAULT_SCORECARD_MD_REL}).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    trace_jsonl_path = Path(args.trace_jsonl).expanduser().resolve() if args.trace_jsonl else root / DEFAULT_TRACE_JSONL_REL
    attribution_jsonl_path = (
        Path(args.attribution_jsonl).expanduser().resolve()
        if args.attribution_jsonl
        else root / DEFAULT_ATTRIBUTION_JSONL_REL
    )
    metrics_json_path = Path(args.json_out).expanduser().resolve() if args.json_out else root / DEFAULT_METRICS_JSON_REL
    scorecard_path = Path(args.markdown_out).expanduser().resolve() if args.markdown_out else root / DEFAULT_SCORECARD_MD_REL

    if not trace_jsonl_path.exists():
        print(
            f"error: missing canonical trace input {trace_jsonl_path}. Rerun scripts/planveyor_trace_extractor.py first.",
            file=sys.stderr,
        )
        return 1
    if not attribution_jsonl_path.exists():
        print(
            f"error: missing canonical failure-attribution input {attribution_jsonl_path}. Rerun scripts/planveyor_failure_attribution.py first.",
            file=sys.stderr,
        )
        return 1

    events = _load_jsonl(trace_jsonl_path)
    failure_rows = _load_jsonl(attribution_jsonl_path)
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    metrics = build_metrics(
        events,
        failure_rows,
        generated_at=generated_at,
        trace_jsonl_path=_display_path(trace_jsonl_path, root),
        attribution_jsonl_path=_display_path(attribution_jsonl_path, root),
        metrics_json_path=_display_path(metrics_json_path, root),
        scorecard_path=_display_path(scorecard_path, root),
    )
    _write_json(metrics_json_path, metrics)
    _write_text(scorecard_path, render_scorecard(metrics))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

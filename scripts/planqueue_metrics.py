#!/usr/bin/env python3
"""Derive read-only planning-contour queue health metrics."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "planqueue_health_metrics.v1"
DEFAULT_LOG_REL = ".planveyor.planqueue.log"
DEFAULT_STATE_REL = ".planveyor.planqueue.json"
DEFAULT_JSON_OUT_REL = ".tmp/planveyor_planqueue_health_metrics.json"
DEFAULT_MARKDOWN_OUT_REL = ".tmp/planveyor_planqueue_health_scorecard.md"
LOOP_STOP_REASONS = {"loop_escalation_recorded", "unchanged_status", "real_loop"}
ANNOTATION_KEYS = ("outcome", "outcome_label", "activation_outcome", "admission_outcome")
TRUE_POSITIVE_VALUES = {"true_positive", "tp"}
FALSE_POSITIVE_VALUES = {"false_positive", "fp"}
JUDGMENT_VALUES = TRUE_POSITIVE_VALUES | FALSE_POSITIVE_VALUES
MECHANICAL_OUTCOME_VALUES = {"fixed", "stale_historical", "owner_action"}
KNOWN_UNKNOWN_OUTCOME_VALUES = {"unknown", "human_gate"}
STAMPER_ROLE_KEYS = ("stamper_role", "outcome_stamper_role", "stamped_by_role")
EVIDENCE_REF_KEYS = ("evidence_ref", "outcome_evidence_ref")
SOURCE_REF_KEYS = (
    "source_event_ref",
    "source_item_ref",
    "queue_event_ref",
    "queue_item_ref",
    "event_ref",
    "item_ref",
    "stop_event_ref",
    "stop_item_ref",
)
EVIDENCE_STATE_KEYS = ("evidence_state", "outcome_evidence_state", "evidence_status")
SUPPORTED_EVIDENCE_REF_PREFIXES = (
    "docs/code_reviews/",
    "docs/doc_reviews/",
    "docs/plans/",
    "docs/process_improvements/",
    ".tmp/process_improvements_capture/",
    ".planveyor.owner_answers",
    "owner:",
    "adoption:",
)
GREEN_EVIDENCE_STATES = {"fixed", "closed", "resolved", "stale_historical", "owner_action", "no_live_blocker", "ok", "green"}
RED_EVIDENCE_STATES = {"red", "live_blocker", "open_blocker", "contradictory", "inconsistent", "blocked"}
AMBIGUOUS_LINEAGE_VALUES = {"ambiguous", "true", "yes", "1"}
NON_EXECUTABLE_RUNTIME_CLASSES = {
    "parked_umbrella",
    "routing_only_baseline",
    "verified_reference_child",
}


@dataclass(frozen=True)
class ParsedLog:
    entries: list[dict[str, str]]
    malformed_rows: list[dict[str, Any]]
    malformed_field_chunks: list[dict[str, Any]]


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _display_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _safe_int(value: Any) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def _percent(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.1f}%"


def parse_queue_log(log_path: Path) -> ParsedLog:
    if not log_path.exists():
        return ParsedLog(entries=[], malformed_rows=[], malformed_field_chunks=[])

    entries: list[dict[str, str]] = []
    malformed_rows: list[dict[str, Any]] = []
    malformed_field_chunks: list[dict[str, Any]] = []

    for index, raw_line in enumerate(log_path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        if not raw_line.strip():
            continue
        parts = raw_line.split("\t")
        if len(parts) < 2 or not parts[0].strip() or not parts[1].strip():
            malformed_rows.append(
                {
                    "line": index,
                    "reason": "missing_timestamp_or_event",
                    "raw": raw_line[:200],
                }
            )
            continue
        entry: dict[str, str] = {"at": parts[0].strip(), "event": parts[1].strip(), "_line": str(index)}
        for chunk in parts[2:]:
            if "=" not in chunk:
                malformed_field_chunks.append(
                    {
                        "line": index,
                        "event": entry["event"],
                        "reason": "field_without_equals",
                        "raw": chunk[:200],
                    }
                )
                continue
            key, value = chunk.split("=", 1)
            key = key.strip()
            if not key:
                malformed_field_chunks.append(
                    {
                        "line": index,
                        "event": entry["event"],
                        "reason": "empty_field_key",
                        "raw": chunk[:200],
                    }
                )
                continue
            entry[key] = value
        entries.append(entry)

    return ParsedLog(
        entries=entries,
        malformed_rows=malformed_rows,
        malformed_field_chunks=malformed_field_chunks,
    )


def load_state_read_only(state_path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not state_path.exists():
        return None, None
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, f"state_json_decode_error: {exc}"
    if not isinstance(payload, dict):
        return None, "state_json_not_object"
    return payload, None


def _annotation_value(entry: dict[str, str]) -> str | None:
    for key in ANNOTATION_KEYS:
        raw = entry.get(key)
        if raw is None:
            continue
        normalized = " ".join(raw.strip().lower().replace("-", "_").split())
        if normalized:
            return normalized
    return None


def _first_present(entry: dict[str, str], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        raw = entry.get(key)
        if raw is None:
            continue
        value = raw.strip()
        if value:
            return value
    return None


def _normalized_first_present(entry: dict[str, str], keys: tuple[str, ...]) -> str | None:
    value = _first_present(entry, keys)
    if value is None:
        return None
    return " ".join(value.lower().replace("-", "_").split())


def _supported_evidence_ref(value: str | None) -> bool:
    if value is None:
        return False
    return value.startswith(SUPPORTED_EVIDENCE_REF_PREFIXES)


def _lineage_is_ambiguous(entry: dict[str, str]) -> bool:
    value = _normalized_first_present(entry, ("lineage_status", "ambiguous_lineage"))
    return value in AMBIGUOUS_LINEAGE_VALUES


def _validate_annotation(entry: dict[str, str], value: str) -> dict[str, Any]:
    stamper_role = _first_present(entry, STAMPER_ROLE_KEYS)
    evidence_ref = _first_present(entry, EVIDENCE_REF_KEYS)
    source_ref = _first_present(entry, SOURCE_REF_KEYS)
    evidence_state = _normalized_first_present(entry, EVIDENCE_STATE_KEYS)
    missing_fields = [
        name
        for name, present in (
            ("stamper_role", stamper_role),
            ("evidence_ref", evidence_ref),
            ("source_ref", source_ref),
        )
        if not present
    ]
    base: dict[str, Any] = {
        "line": _safe_int(entry.get("_line")),
        "event": entry.get("event") or "unknown",
        "outcome": value,
        "stamper_role": stamper_role,
        "evidence_ref": evidence_ref,
        "source_ref": source_ref,
        "evidence_state": evidence_state,
        "missing_fields": missing_fields,
    }
    if value in JUDGMENT_VALUES:
        base["category"] = "judgment"
    elif value in MECHANICAL_OUTCOME_VALUES:
        base["category"] = "mechanical"
    elif value in KNOWN_UNKNOWN_OUTCOME_VALUES:
        base["category"] = "known_unknown"
    else:
        base["category"] = "unsupported"

    if _lineage_is_ambiguous(entry):
        return {
            **base,
            "status": "invalid",
            "verdict": "human_gate",
            "reason": "ambiguous_lineage",
        }
    if base["category"] == "unsupported":
        return {
            **base,
            "status": "invalid",
            "verdict": "unknown",
            "reason": "unsupported_outcome_value",
        }
    if missing_fields:
        return {
            **base,
            "status": "invalid",
            "verdict": "unknown",
            "reason": "missing_authority_fields",
        }
    if not _supported_evidence_ref(evidence_ref):
        return {
            **base,
            "status": "invalid",
            "verdict": "unknown",
            "reason": "unsupported_evidence_ref_host",
        }
    if evidence_state in RED_EVIDENCE_STATES:
        return {
            **base,
            "status": "invalid",
            "verdict": "unknown",
            "reason": "authoritative_evidence_red_or_inconsistent",
        }
    if base["category"] in {"judgment", "mechanical"} and evidence_state not in GREEN_EVIDENCE_STATES:
        return {
            **base,
            "status": "invalid",
            "verdict": "unknown",
            "reason": "unsupported_or_missing_green_evidence_state",
        }
    return {
        **base,
        "status": "valid",
        "verdict": "known_unknown" if base["category"] == "known_unknown" else "counted",
        "reason": "authority_refs_valid",
    }


def _state_counts(state: dict[str, Any] | None) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for item in (state or {}).get("items", []):
        if isinstance(item, dict):
            counter[str(item.get("state") or "unknown")] += 1
    return dict(sorted(counter.items()))


def _current_warning_candidates(state: dict[str, Any] | None) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for item in (state or {}).get("items", []):
        if not isinstance(item, dict):
            continue
        warning = item.get("queue_activation_warning")
        runtime_class = item.get("runtime_class")
        state_value = str(item.get("state") or "")
        if warning:
            candidates.append(
                {
                    "kind": "queue_activation_warning",
                    "plan": item.get("plan"),
                    "order": item.get("order"),
                    "state": state_value,
                    "reason": warning,
                }
            )
        if state_value in {"pending", "active"} and runtime_class in NON_EXECUTABLE_RUNTIME_CLASSES:
            candidates.append(
                {
                    "kind": "parked_umbrella_drift_candidate",
                    "plan": item.get("plan"),
                    "order": item.get("order"),
                    "state": state_value,
                    "reason": f"runtime_class={runtime_class}",
                }
            )
    return candidates


def build_metrics(
    *,
    root: Path,
    log_path: Path,
    state_path: Path,
    json_out_path: Path,
    markdown_out_path: Path,
    generated_at: str,
) -> dict[str, Any]:
    root = root.resolve()
    parsed_log = parse_queue_log(log_path)
    state, state_error = load_state_read_only(state_path)
    entries = parsed_log.entries
    event_counter = Counter(entry.get("event") or "unknown" for entry in entries)
    valid_rows = len(entries)
    total_rows = valid_rows + len(parsed_log.malformed_rows)

    state_repair_count = event_counter.get("state_repair", 0)
    stop_entries = [entry for entry in entries if entry.get("event") == "stop"]
    stop_reasons = Counter(entry.get("reason") or "unknown" for entry in stop_entries)
    loop_stop_count = sum(count for reason, count in stop_reasons.items() if reason in LOOP_STOP_REASONS)
    queue_complete_from_state = bool(((state or {}).get("last_transition") or {}).get("queue_complete"))
    last_transition = (state or {}).get("last_transition") if isinstance((state or {}).get("last_transition"), dict) else {}
    active_items = [
        item
        for item in (state or {}).get("items", [])
        if isinstance(item, dict) and str(item.get("state") or "") == "active"
    ]
    pending_items = [
        item
        for item in (state or {}).get("items", [])
        if isinstance(item, dict) and str(item.get("state") or "") == "pending"
    ]

    append_rejected_items = sum(_safe_int(entry.get("rejected")) for entry in entries if entry.get("event") == "append")
    admission_stop_count = sum(
        1
        for entry in stop_entries
        if any(token in (entry.get("reason") or "") for token in ("admission", "blocked", "queue_activation"))
    )
    warning_candidates = _current_warning_candidates(state)

    annotated_entries: list[dict[str, str]] = []
    annotation_validations: list[dict[str, Any]] = []
    annotation_counter: Counter[str] = Counter()
    valid_annotation_counter: Counter[str] = Counter()
    invalid_annotation_reasons: Counter[str] = Counter()
    annotation_missing_count = 0
    for entry in entries:
        if entry.get("event") not in {"activate", "append", "set"}:
            continue
        value = _annotation_value(entry)
        if value is None:
            annotation_missing_count += 1
            continue
        annotation_counter[value] += 1
        annotated_entries.append(entry)
        validation = _validate_annotation(entry, value)
        annotation_validations.append(validation)
        if validation["status"] == "valid":
            valid_annotation_counter[value] += 1
        else:
            invalid_annotation_reasons[str(validation["reason"])] += 1
    true_positive_count = sum(valid_annotation_counter[value] for value in TRUE_POSITIVE_VALUES)
    false_positive_count = sum(valid_annotation_counter[value] for value in FALSE_POSITIVE_VALUES)
    rate_denominator = true_positive_count + false_positive_count
    if rate_denominator:
        true_positive_rate = {
            "status": "computed",
            "value": _ratio(true_positive_count, rate_denominator),
            "reason": "valid_authority_backed_judgment_annotations_present",
        }
    elif annotated_entries:
        true_positive_rate = {
            "status": "unknown",
            "value": None,
            "reason": "no_valid_judgment_annotations",
        }
    else:
        true_positive_rate = {
            "status": "unknown",
            "value": None,
            "reason": "outcome_annotation_missing",
        }

    diagnostics: list[dict[str, Any]] = []
    if not log_path.exists():
        diagnostics.append({"severity": "warning", "code": "log_missing", "message": "Queue log file is absent"})
    if not state_path.exists():
        diagnostics.append({"severity": "warning", "code": "state_missing", "message": "Queue state file is absent"})
    if state_error:
        diagnostics.append({"severity": "error", "code": "state_parse_error", "message": state_error})
    for row in parsed_log.malformed_rows[:10]:
        diagnostics.append({"severity": "warning", "code": "malformed_log_row", **row})
    for row in parsed_log.malformed_field_chunks[:10]:
        diagnostics.append({"severity": "warning", "code": "malformed_log_field", **row})
    if queue_complete_from_state and (active_items or pending_items):
        diagnostics.append(
            {
                "severity": "error",
                "code": "queue_complete_with_open_items",
                "message": "State last_transition says queue_complete while active/pending items remain",
                "active_count": len(active_items),
                "pending_count": len(pending_items),
            }
        )
    for candidate in warning_candidates[:10]:
        diagnostics.append({"severity": "warning", "code": candidate["kind"], **candidate})
    for validation in annotation_validations[:20]:
        if validation["status"] != "valid":
            diagnostics.append(
                {
                    "severity": "warning",
                    "code": "invalid_outcome_annotation",
                    **validation,
                }
            )

    if any(item.get("severity") == "error" for item in diagnostics):
        confidence_status = "low"
        confidence_reason = "error_diagnostics_present"
    elif diagnostics:
        confidence_status = "medium"
        confidence_reason = "warning_diagnostics_present"
    else:
        confidence_status = "high"
        confidence_reason = "log_and_state_read_without_diagnostics"

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "inputs": {
            "root": root.as_posix(),
            "log_path": _display_path(log_path, root),
            "state_path": _display_path(state_path, root),
            "json_out_path": _display_path(json_out_path, root),
            "markdown_out_path": _display_path(markdown_out_path, root),
            "log_exists": log_path.exists(),
            "state_exists": state_path.exists(),
            "log_rows_total": total_rows,
            "log_rows_valid": valid_rows,
            "log_rows_malformed": len(parsed_log.malformed_rows),
            "log_field_chunks_malformed": len(parsed_log.malformed_field_chunks),
        },
        "event_totals": {
            "total_rows": total_rows,
            "valid_rows": valid_rows,
            "malformed_rows": len(parsed_log.malformed_rows),
            "malformed_field_chunks": len(parsed_log.malformed_field_chunks),
            "by_event": dict(sorted(event_counter.items())),
        },
        "health": {
            "state_repair": {
                "count": state_repair_count,
                "rate_per_valid_log_row": _ratio(state_repair_count, valid_rows),
            },
            "transitions": {
                "set": event_counter.get("set", 0),
                "append": event_counter.get("append", 0),
                "activate": event_counter.get("activate", 0),
                "complete": event_counter.get("complete", 0),
                "supersede": event_counter.get("supersede", 0),
                "closeout_non_executable": event_counter.get("closeout_non_executable", 0),
                "advance": event_counter.get("advance", 0),
                "planpath_override": event_counter.get("planpath_override", 0),
                "queue_complete_from_state": queue_complete_from_state,
                "last_transition_kind": last_transition.get("kind"),
            },
            "stops": {
                "count": len(stop_entries),
                "loop_stop_count": loop_stop_count,
                "by_reason": dict(sorted(stop_reasons.items())),
            },
            "observed_admission": {
                "append_rejected_items": append_rejected_items,
                "admission_or_blocker_stop_rows": admission_stop_count,
                "current_warning_candidates": len(warning_candidates),
                "rate_status": "observed_only",
                "reason": "current queue instrumentation may reject before append_log",
            },
            "current_state": {
                "exists": state is not None,
                "mode": (state or {}).get("mode"),
                "cursor": (state or {}).get("cursor"),
                "active_plan": active_items[0].get("plan") if active_items else None,
                "active_count": len(active_items),
                "pending_count": len(pending_items),
                "state_counts": _state_counts(state),
                "warning_candidates": warning_candidates,
            },
        },
        "outcome_quality": {
            "annotation_keys": list(ANNOTATION_KEYS),
            "annotated_rows": len(annotated_entries),
            "valid_annotation_rows": sum(1 for item in annotation_validations if item["status"] == "valid"),
            "invalid_annotation_rows": sum(1 for item in annotation_validations if item["status"] != "valid"),
            "missing_annotation_rows": annotation_missing_count,
            "by_annotation": dict(sorted(annotation_counter.items())),
            "by_valid_annotation": dict(sorted(valid_annotation_counter.items())),
            "invalid_annotation_reasons": dict(sorted(invalid_annotation_reasons.items())),
            "known_unknown_rows": sum(
                1 for item in annotation_validations if item["status"] == "valid" and item["category"] == "known_unknown"
            ),
            "human_gate_rows": sum(1 for item in annotation_validations if item.get("verdict") == "human_gate"),
            "annotation_validation": annotation_validations,
            "true_positive_rate": true_positive_rate,
        },
        "confidence": {
            "status": confidence_status,
            "reason": confidence_reason,
            "diagnostics": diagnostics,
        },
        "omitted_metrics": [
            {
                "metric": "absolute_admission_reject_rate",
                "status": "omitted",
                "reason": "some admission/dependency blockers can raise before append_log",
            },
            {
                "metric": "unannotated_activation_true_positive_rate",
                "status": "unknown" if not rate_denominator else "computed_from_annotations_only",
                "reason": true_positive_rate["reason"],
            },
        ],
    }


def _format_table(rows: list[tuple[str, Any]]) -> list[str]:
    lines = ["| Field | Value |", "| --- | --- |"]
    for key, value in rows:
        if isinstance(value, bool):
            rendered = "yes" if value else "no"
        elif value is None:
            rendered = "N/A"
        else:
            rendered = str(value)
        lines.append(f"| `{key}` | `{rendered}` |")
    return lines


def render_scorecard(metrics: dict[str, Any]) -> str:
    inputs = metrics["inputs"]
    health = metrics["health"]
    outcome = metrics["outcome_quality"]
    confidence = metrics["confidence"]
    by_event = metrics["event_totals"]["by_event"]
    tp_rate = outcome["true_positive_rate"]

    lines: list[str] = [
        "# Planqueue health scorecard",
        "",
        "Generated readback only. Live queue routing truth remains `.planveyor.planqueue.json`, `planveyor_q_show` and Manager/oracle readback.",
        "",
        "## Summary",
        "",
        *_format_table(
            [
                ("schema_version", metrics["schema_version"]),
                ("generated_at", metrics["generated_at"]),
                ("confidence", confidence["status"]),
                ("confidence_reason", confidence["reason"]),
                ("valid_log_rows", inputs["log_rows_valid"]),
                ("malformed_log_rows", inputs["log_rows_malformed"]),
                ("state_repair_count", health["state_repair"]["count"]),
                ("state_repair_rate", _percent(health["state_repair"]["rate_per_valid_log_row"])),
                ("true_positive_rate_status", tp_rate["status"]),
                ("true_positive_rate", _percent(tp_rate["value"])),
                ("observed_admission_rate_status", health["observed_admission"]["rate_status"]),
            ]
        ),
        "",
        "## Sources",
        "",
        *_format_table(
            [
                ("log_path", inputs["log_path"]),
                ("log_exists", inputs["log_exists"]),
                ("state_path", inputs["state_path"]),
                ("state_exists", inputs["state_exists"]),
                ("json_out_path", inputs["json_out_path"]),
                ("markdown_out_path", inputs["markdown_out_path"]),
            ]
        ),
        "",
        "## Event totals",
        "",
        "| Event | Count |",
        "| --- | ---: |",
    ]
    if by_event:
        for event, count in sorted(by_event.items()):
            lines.append(f"| `{event}` | {count} |")
    else:
        lines.append("| `N/A` | 0 |")

    stop_reasons = health["stops"]["by_reason"]
    lines.extend(["", "## Queue health", ""])
    lines.extend(
        _format_table(
            [
                ("activate", health["transitions"]["activate"]),
                ("complete", health["transitions"]["complete"]),
                ("advance", health["transitions"]["advance"]),
                ("queue_complete_from_state", health["transitions"]["queue_complete_from_state"]),
                ("stop_count", health["stops"]["count"]),
                ("loop_stop_count", health["stops"]["loop_stop_count"]),
                ("active_plan", health["current_state"]["active_plan"]),
                ("active_count", health["current_state"]["active_count"]),
                ("pending_count", health["current_state"]["pending_count"]),
                ("current_warning_candidates", health["observed_admission"]["current_warning_candidates"]),
                ("append_rejected_items", health["observed_admission"]["append_rejected_items"]),
                ("admission_or_blocker_stop_rows", health["observed_admission"]["admission_or_blocker_stop_rows"]),
            ]
        )
    )

    lines.extend(["", "## Stop reasons", "", "| Reason | Count |", "| --- | ---: |"])
    if stop_reasons:
        for reason, count in sorted(stop_reasons.items()):
            lines.append(f"| `{reason}` | {count} |")
    else:
        lines.append("| `N/A` | 0 |")

    lines.extend(
        [
            "",
            "## Outcome quality",
            "",
            *_format_table(
                [
                    ("annotated_rows", outcome["annotated_rows"]),
                    ("valid_annotation_rows", outcome["valid_annotation_rows"]),
                    ("invalid_annotation_rows", outcome["invalid_annotation_rows"]),
                    ("missing_annotation_rows", outcome["missing_annotation_rows"]),
                    ("known_unknown_rows", outcome["known_unknown_rows"]),
                    ("human_gate_rows", outcome["human_gate_rows"]),
                    ("true_positive_rate_status", tp_rate["status"]),
                    ("true_positive_rate_reason", tp_rate["reason"]),
                ]
            ),
            "",
            "Outcome annotations are counted only when `stamper_role`, `evidence_ref`, a stable source event/item ref and a supported structural evidence state are present. Unsupported or unverifiable annotations stay `unknown` / `human_gate`.",
            "",
            "## Diagnostics",
            "",
        ]
    )
    diagnostics = confidence["diagnostics"]
    if diagnostics:
        lines.extend(["| Severity | Code | Detail |", "| --- | --- | --- |"])
        for item in diagnostics:
            detail = item.get("message") or item.get("reason") or item.get("raw") or item.get("plan") or "N/A"
            lines.append(f"| `{item.get('severity')}` | `{item.get('code')}` | `{detail}` |")
    else:
        lines.append("No diagnostics.")

    lines.extend(
        [
            "",
            "## Omitted metrics",
            "",
            "| Metric | Status | Reason |",
            "| --- | --- | --- |",
        ]
    )
    for item in metrics["omitted_metrics"]:
        lines.append(f"| `{item['metric']}` | `{item['status']}` | `{item['reason']}` |")
    lines.append("")
    return "\n".join(lines)


def _resolve_path(root: Path, raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    return root / path


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repo root for default queue paths")
    parser.add_argument("--log", default=DEFAULT_LOG_REL, help="Queue log path, absolute or root-relative")
    parser.add_argument("--state", default=DEFAULT_STATE_REL, help="Queue state path, absolute or root-relative")
    parser.add_argument("--json-out", default=DEFAULT_JSON_OUT_REL, help="Metrics JSON output path")
    parser.add_argument("--markdown-out", default=DEFAULT_MARKDOWN_OUT_REL, help="Markdown scorecard output path")
    parser.add_argument("--generated-at", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--json", action="store_true", help="Print metrics JSON to stdout")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    log_path = _resolve_path(root, args.log)
    state_path = _resolve_path(root, args.state)
    json_out_path = _resolve_path(root, args.json_out)
    markdown_out_path = _resolve_path(root, args.markdown_out)
    metrics = build_metrics(
        root=root,
        log_path=log_path,
        state_path=state_path,
        json_out_path=json_out_path,
        markdown_out_path=markdown_out_path,
        generated_at=args.generated_at or _now_utc(),
    )
    _write_json(json_out_path, metrics)
    _write_text(markdown_out_path, render_scorecard(metrics))
    if args.json:
        print(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"planqueue-metrics: wrote {_display_path(json_out_path, root)}")
        print(f"planqueue-metrics: wrote {_display_path(markdown_out_path, root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Derive compact failure-attribution rows from canonical trace events."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable


DEFAULT_TRACE_JSONL_REL = ".tmp/planveyor_trace_events.jsonl"
DEFAULT_ATTRIBUTION_JSONL_REL = ".tmp/planveyor_failure_attribution.jsonl"
SPACE_RE = re.compile(r"\s+")
NON_ID_RE = re.compile(r"[^a-z0-9._-]+")
HEADER_FIELD_RE = re.compile(r"^\*\*(?P<label>[^*]+?):\*\*\s*(?P<value>.+?)\s*$")
H2_RE = re.compile(r"^\s*##\s+(?P<title>.+?)\s*$")
H3_RE = re.compile(r"^\s*###\s+(?P<title>.+?)\s*$")
FIELD_LINE_RE = re.compile(r"^\s*-\s+`?(?P<label>[^:`]+?)`?:\s*(?P<value>.+?)\s*$")
BLOCKER_TITLE_RE = re.compile(r"^\s*(?P<blocker>B\d+)\)")
AUDIT_ITEM_TITLE_RE = re.compile(r"^\s*(?P<item>A\d+)\)")
DOC_REF_RE = re.compile(r"docs/[A-Za-z0-9_./#-]+")
FAILURE_SIGNAL_RE = re.compile(r"(blocker|fail|error|missing|diverged|partial|unknown|denied)", re.IGNORECASE)

FAILURE_CODES = (
    "CONTRACT_VIOLATION",
    "ROUTING_FAILURE",
    "REVIEWABILITY_GAP",
    "RUNTIME_ENV",
    "TOOL_ERROR",
    "GOVERNANCE_BLOCK",
    "UNKNOWN",
    "MIXED",
)
EXPLICIT_CLASSIFICATION_MAP = {
    "same-contract reroute": "ROUTING_FAILURE",
    "stale evidence / historical artifact mismatch": "REVIEWABILITY_GAP",
    "closed baseline + live blocker split": "MIXED",
    "real scope expansion": "GOVERNANCE_BLOCK",
}
KEYWORD_GROUPS = {
    "CONTRACT_VIOLATION": (
        "contract violation",
        "contract drift",
        "schema mismatch",
        "literal bundle contract",
        "invariant",
        "unexpected response",
        "wrong status code",
        "bundle mismatch",
        "scope drift",
    ),
    "ROUTING_FAILURE": (
        "same-contract reroute",
        "routing failure",
        "route drift",
        "review route",
        "review host",
        "bundle host",
        "queue closeout",
        "queue runtime",
        "planner finalize",
        "architect response",
        "reroute",
    ),
    "REVIEWABILITY_GAP": (
        "reviewability",
        "stale evidence",
        "historical artifact mismatch",
        "missing evidence",
        "missing visual",
        "missing path",
        "proof lane",
        "visual sanity",
        "lint gate",
        "review artifact",
    ),
    "RUNTIME_ENV": (
        "operationalerror",
        "connection refused",
        "permission denied",
        "sandbox",
        "database",
        "credentials",
        "profile",
        "failed to launch the browser process",
        "abort trap",
        "sigabrt",
        "environment",
    ),
    "TOOL_ERROR": (
        "traceback",
        "exception",
        "tool error",
        "cli failed",
        "failed to parse",
        "jsondecode",
        "broken pipe",
        "crash",
        "stack trace",
    ),
    "GOVERNANCE_BLOCK": (
        "owner",
        "needs_owner",
        "approval",
        "governance",
        "policy",
        "scope expansion",
        "manual decision",
        "out of scope",
    ),
}
DONE_STATUSES = ("✅ done", "done", "ok", "✅ ok")


def _n_a(reason: str) -> str:
    return f"N/A (why={reason})"


def _collapse_space(value: str) -> str:
    return SPACE_RE.sub(" ", value.strip())


def _slug(value: str) -> str:
    normalized = NON_ID_RE.sub("_", value.strip().lower())
    normalized = normalized.strip("._")
    return normalized or "unknown"


def _normalize_title(value: str) -> str:
    return _collapse_space(value).lower()


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _resolve_roots(raw_roots: list[str], events: list[dict[str, Any]], trace_jsonl_path: Path) -> list[Path]:
    resolved: list[Path] = []
    seen: set[Path] = set()

    def add(path: Path) -> None:
        candidate = path.expanduser().resolve()
        if candidate in seen:
            return
        seen.add(candidate)
        resolved.append(candidate)

    if raw_roots:
        for raw in raw_roots:
            add(Path(raw))
    else:
        add(Path.cwd())

    add(trace_jsonl_path.parent.parent)
    for event in events:
        raw_root = str(event.get("source_root") or "").strip()
        if raw_root:
            add(Path(raw_root))
    return resolved


def _resolve_source_file(event: dict[str, Any], roots: list[Path]) -> Path | None:
    raw_source_path = str(event.get("source_path") or "").strip()
    if not raw_source_path:
        return None

    path = Path(raw_source_path)
    if path.is_absolute() and path.exists():
        return path.resolve()

    raw_source_root = str(event.get("source_root") or "").strip()
    candidates: list[Path] = []
    if raw_source_root:
        candidates.append(Path(raw_source_root).expanduser() / raw_source_path)
    for root in roots:
        candidates.append(root / raw_source_path)

    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return None


def _header_fields(lines: list[str]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in lines:
        match = HEADER_FIELD_RE.match(line.strip())
        if not match:
            continue
        fields[_normalize_title(match.group("label"))] = _collapse_space(match.group("value"))
    return fields


def _section_field_map(lines: Iterable[str]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in lines:
        match = FIELD_LINE_RE.match(line)
        if not match:
            continue
        label = _normalize_title(match.group("label"))
        fields[label] = _collapse_space(match.group("value"))
    return fields


def _extract_doc_refs(value: str) -> list[str]:
    refs = sorted(set(DOC_REF_RE.findall(value)))
    if refs:
        return refs
    cleaned = _collapse_space(value)
    return [cleaned] if cleaned else []


def _match_codes(text: str) -> set[str]:
    normalized = _normalize_title(text)
    matches: set[str] = set()
    for code, needles in KEYWORD_GROUPS.items():
        if any(needle in normalized for needle in needles):
            matches.add(code)
    return matches


def _reduce_codes(matches: set[str]) -> str:
    if not matches:
        return "UNKNOWN"
    if len(matches) == 1:
        return next(iter(matches))
    return "MIXED"


def _code_from_text(text: str) -> str:
    return _reduce_codes(_match_codes(text))


def _looks_failing_status(value: str) -> bool:
    normalized = _normalize_title(value)
    if not normalized:
        return False
    if normalized in DONE_STATUSES or normalized.startswith("✅"):
        return False
    return bool(FAILURE_SIGNAL_RE.search(normalized))


def _is_done_status(value: str) -> bool:
    normalized = _normalize_title(value)
    return normalized in DONE_STATUSES or normalized.startswith("✅")


def _join_non_field_lines(lines: Iterable[str]) -> str:
    snippets: list[str] = []
    for line in lines:
        if HEADER_FIELD_RE.match(line.strip()) or FIELD_LINE_RE.match(line):
            continue
        if line.strip().startswith("### "):
            continue
        cleaned = _collapse_space(line)
        if cleaned:
            snippets.append(cleaned)
    return " ".join(snippets)


def _parse_review_blockers(rel_source_path: str, lines: list[str]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    current_h2: str | None = None
    current_blocker_id: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_blocker_id, current_lines
        if current_blocker_id is None:
            current_lines = []
            return
        fields = _section_field_map(current_lines)
        reason = _join_non_field_lines(current_lines)
        classification = fields.get("classification", "")
        explicit = EXPLICIT_CLASSIFICATION_MAP.get(_normalize_title(classification), "")
        code = explicit or _code_from_text(" ".join((classification, reason, fields.get("evidence refs", ""))))
        evidence_refs = _extract_doc_refs(fields.get("evidence refs", ""))
        findings.append(
            {
                "failure_code": code,
                "finding_ref": f"{rel_source_path}#{current_blocker_id}",
                "current_state": fields.get("current state", "open"),
                "classification_hint": classification or _n_a("review blocker did not expose a compact classification hint"),
                "primary_owner_gap": fields.get("primary owner gap", _n_a("review blocker did not expose primary owner gap")),
                "evidence_refs": evidence_refs or [rel_source_path],
                "reason": reason or _n_a("review blocker did not expose additional prose context"),
                "lineage_source": "live_review_blocker",
            }
        )
        current_blocker_id = None
        current_lines = []

    for line in lines:
        h2_match = H2_RE.match(line)
        if h2_match:
            flush()
            current_h2 = _normalize_title(h2_match.group("title"))
            continue
        h3_match = H3_RE.match(line)
        if h3_match:
            flush()
            if current_h2 != "s1 blocker":
                continue
            blocker_match = BLOCKER_TITLE_RE.match(_collapse_space(h3_match.group("title")))
            if blocker_match is None:
                continue
            current_blocker_id = blocker_match.group("blocker")
            continue
        if current_blocker_id is not None:
            current_lines.append(line)

    flush()
    return findings


def _parse_unstructured_review_failure(rel_source_path: str, lines: list[str], status: str) -> list[dict[str, Any]]:
    current_h2: str | None = None
    section_lines: list[str] = []
    for line in lines:
        h2_match = H2_RE.match(line)
        if h2_match:
            title = _normalize_title(h2_match.group("title"))
            if current_h2 == "s1 blocker" and section_lines:
                break
            current_h2 = title
            section_lines = []
            continue
        if current_h2 == "s1 blocker":
            section_lines.append(line)

    if current_h2 != "s1 blocker":
        return []

    reason = _join_non_field_lines(section_lines)
    if not reason and not _looks_failing_status(status):
        return []
    code = _code_from_text(" ".join((status, reason)))
    return [
        {
            "failure_code": code,
            "finding_ref": _n_a("review artifact exposed failing verdict without literal blocker lineage"),
            "current_state": "open",
            "classification_hint": _n_a("review artifact did not expose canonical blocker fields"),
            "primary_owner_gap": _n_a("review artifact did not expose primary owner gap"),
            "evidence_refs": [rel_source_path],
            "reason": reason or _collapse_space(status) or _n_a("review artifact did not expose additional prose context"),
            "lineage_source": "live_review_unstructured",
        }
    ]


def _parse_audit_matrix(rel_source_path: str, lines: list[str]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    current_h2: str | None = None
    current_item_id: str | None = None
    current_item_title: str = ""
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_item_id, current_item_title, current_lines
        if current_item_id is None:
            current_lines = []
            return
        fields = _section_field_map(current_lines)
        status = fields.get("status", "")
        if _is_done_status(status):
            current_item_id = None
            current_item_title = ""
            current_lines = []
            return
        notes = _join_non_field_lines(current_lines)
        evidence_refs = _extract_doc_refs(fields.get("blocker refs", ""))
        code = _code_from_text(" ".join((current_item_title, status, notes, fields.get("blocker refs", ""))))
        findings.append(
            {
                "failure_code": code,
                "finding_ref": f"{rel_source_path}#{current_item_id}",
                "current_state": status or "unknown",
                "classification_hint": "audit matrix status",
                "primary_owner_gap": _n_a("post-merge audit matrix does not expose primary owner gap"),
                "evidence_refs": evidence_refs or [rel_source_path],
                "reason": notes or current_item_title or _n_a("audit matrix item did not expose additional prose context"),
                "lineage_source": "live_audit_matrix",
            }
        )
        current_item_id = None
        current_item_title = ""
        current_lines = []

    for line in lines:
        h2_match = H2_RE.match(line)
        if h2_match:
            flush()
            current_h2 = _normalize_title(h2_match.group("title"))
            continue
        h3_match = H3_RE.match(line)
        if h3_match:
            flush()
            if current_h2 not in {"audit matrix", "audit matrix (summary)"}:
                continue
            title = _collapse_space(h3_match.group("title"))
            item_match = AUDIT_ITEM_TITLE_RE.match(title)
            if item_match is None:
                continue
            current_item_id = item_match.group("item")
            current_item_title = title.split(")", 1)[1].strip() if ")" in title else title
            continue
        if current_item_id is not None:
            current_lines.append(line)

    flush()
    return findings


def _parse_live_artifact(rel_source_path: str, path: Path) -> list[dict[str, Any]]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    fields = _header_fields(lines)
    status = fields.get("status", "")

    if "code_reviews" in path.parts or "doc_reviews" in path.parts:
        blockers = _parse_review_blockers(rel_source_path, lines)
        if blockers:
            return blockers
        return _parse_unstructured_review_failure(rel_source_path, lines, status)

    if "reviews" in path.parts:
        audit_items = _parse_audit_matrix(rel_source_path, lines)
        if audit_items:
            return audit_items
        if _looks_failing_status(status):
            reason = _join_non_field_lines(lines)
            return [
                {
                    "failure_code": _code_from_text(" ".join((status, reason))),
                    "finding_ref": _n_a("review artifact exposed failing verdict without live blocker lineage"),
                    "current_state": status,
                    "classification_hint": _n_a("review artifact did not expose audit-matrix or blocker fields"),
                    "primary_owner_gap": _n_a("review artifact did not expose primary owner gap"),
                    "evidence_refs": [rel_source_path],
                    "reason": reason or _collapse_space(status),
                    "lineage_source": "live_review_status",
                }
            ]

    return []


def _build_row(event: dict[str, Any], finding: dict[str, Any]) -> dict[str, Any]:
    trace_id = str(event.get("trace_id") or _n_a("source event did not expose trace_id"))
    source_path = str(event.get("source_path") or "")
    token = _slug(" ".join((str(event.get("event_id") or ""), finding["finding_ref"], finding["failure_code"])))
    return {
        "schema_version": "failure_attribution.v1",
        "event_type": f"failure_attribution.{_slug(str(event.get('source_family') or 'unknown'))}",
        "ts": str(event.get("ts") or ""),
        "event_id": f"evt.failure_attribution.{token}",
        "trace_id": trace_id,
        "span_id": f"span.failure_attribution.{token}",
        "parent_span_id": str(event.get("span_id") or _n_a("source event did not expose span_id")),
        "source_family": "failure_attribution",
        "source_path": source_path,
        "source_root": str(event.get("source_root") or ""),
        "payload": {
            "failure_code": finding["failure_code"],
            "finding_ref": finding["finding_ref"],
            "current_state": finding["current_state"],
            "classification_hint": finding["classification_hint"],
            "primary_owner_gap": finding["primary_owner_gap"],
            "evidence_refs": finding["evidence_refs"],
            "reason": finding["reason"],
            "lineage_source": finding["lineage_source"],
            "source_event_id": str(event.get("event_id") or ""),
            "source_event_type": str(event.get("event_type") or ""),
            "source_event_family": str(event.get("source_family") or ""),
        },
    }


def _review_findings_for_event(
    event: dict[str, Any],
    roots: list[Path],
    artifact_cache: dict[Path, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    rel_source_path = str(event.get("source_path") or "")
    source_file = _resolve_source_file(event, roots)
    if source_file is not None:
        if source_file not in artifact_cache:
            artifact_cache[source_file] = _parse_live_artifact(rel_source_path, source_file)
        findings = artifact_cache[source_file]
        if findings:
            return findings

    payload = event.get("payload") or {}
    status = str(payload.get("status") or "")
    blocker_ids = [str(item) for item in payload.get("blocker_ids") or [] if str(item).strip()]
    combined = " ".join(
        (
            str(event.get("event_type") or ""),
            status,
            str(payload.get("title") or ""),
            str(payload.get("target") or ""),
            str(payload.get("spec") or ""),
        )
    )
    if not blocker_ids and not _looks_failing_status(combined):
        return []

    code = _code_from_text(combined)
    findings: list[dict[str, Any]] = []
    if blocker_ids:
        for blocker_id in blocker_ids:
            findings.append(
                {
                    "failure_code": code,
                    "finding_ref": f"{rel_source_path}#{blocker_id}",
                    "current_state": status or "open",
                    "classification_hint": _n_a("trace event did not expose live blocker classification"),
                    "primary_owner_gap": _n_a("trace event did not expose primary owner gap"),
                    "evidence_refs": [rel_source_path],
                    "reason": _collapse_space(combined) or _n_a("trace event did not expose additional failure context"),
                    "lineage_source": "trace_payload_only",
                }
            )
        return findings

    return [
        {
            "failure_code": code,
            "finding_ref": _n_a("trace event exposed failing review status without literal blocker lineage"),
            "current_state": status or "unknown",
            "classification_hint": _n_a("trace event did not expose canonical blocker classification"),
            "primary_owner_gap": _n_a("trace event did not expose primary owner gap"),
            "evidence_refs": [rel_source_path] if rel_source_path else [],
            "reason": _collapse_space(combined) or _n_a("trace event did not expose additional failure context"),
            "lineage_source": "trace_payload_only",
        }
    ]


def _runtime_findings_for_event(event: dict[str, Any]) -> list[dict[str, Any]]:
    payload = event.get("payload") or {}
    relevant_keys = (
        "stop_reason",
        "status",
        "error",
        "last_error",
        "stderr",
        "stdout",
        "pipeline_mode",
        "pre_status_line",
        "result_artifact",
    )
    signal = " ".join(str(payload.get(key) or "") for key in relevant_keys)
    signal = _collapse_space(" ".join((str(event.get("event_type") or ""), signal)))
    if not signal or not FAILURE_SIGNAL_RE.search(signal):
        return []
    return [
        {
            "failure_code": _code_from_text(signal),
            "finding_ref": _n_a("runtime receipt does not expose live blocker lineage"),
            "current_state": str(payload.get("status") or "open"),
            "classification_hint": "runtime receipt inference",
            "primary_owner_gap": _n_a("runtime receipt does not expose primary owner gap"),
            "evidence_refs": [str(event.get("source_path") or "")],
            "reason": signal,
            "lineage_source": "runtime_receipt_payload",
        }
    ]


def _collab_findings_for_event(event: dict[str, Any]) -> list[dict[str, Any]]:
    payload = event.get("payload") or {}
    signal = _collapse_space(
        " ".join(
            (
                str(payload.get("event") or ""),
                str(payload.get("note") or ""),
                str(payload.get("raw_ts") or ""),
            )
        )
    )
    if not signal or not FAILURE_SIGNAL_RE.search(signal):
        return []
    return [
        {
            "failure_code": _code_from_text(signal),
            "finding_ref": _n_a("collab log does not expose live blocker lineage"),
            "current_state": "observed",
            "classification_hint": "collab log inference",
            "primary_owner_gap": _n_a("collab log does not expose primary owner gap"),
            "evidence_refs": [str(event.get("source_path") or "")],
            "reason": signal,
            "lineage_source": "collab_log_payload",
        }
    ]


def derive_attribution_rows(events: list[dict[str, Any]], roots: list[Path]) -> list[dict[str, Any]]:
    artifact_cache: dict[Path, list[dict[str, Any]]] = {}
    rows: list[dict[str, Any]] = []

    for event in events:
        source_family = str(event.get("source_family") or "")
        findings: list[dict[str, Any]] = []
        if source_family == "review_receipt":
            findings = _review_findings_for_event(event, roots, artifact_cache)
        elif source_family == "run_receipt":
            findings = _runtime_findings_for_event(event)
        elif source_family == "collab_agent_log":
            findings = _collab_findings_for_event(event)

        for finding in findings:
            rows.append(_build_row(event, finding))

    rows.sort(
        key=lambda row: (
            str(row.get("ts") or ""),
            str(row.get("source_path") or ""),
            str((row.get("payload") or {}).get("finding_ref") or ""),
            str((row.get("payload") or {}).get("failure_code") or ""),
        )
    )
    return rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Derive compact failure-attribution JSONL from canonical trace events and "
            "optional live review/audit lineage."
        )
    )
    parser.add_argument(
        "--root",
        action="append",
        default=[],
        help="Repository root used to resolve live review/audit artifacts. Repeatable; defaults to the current working directory.",
    )
    parser.add_argument(
        "--jsonl-in",
        default="",
        help=f"Input trace JSONL path (default: first root/{DEFAULT_TRACE_JSONL_REL}).",
    )
    parser.add_argument(
        "--jsonl-out",
        default="",
        help=f"Output attribution JSONL path (default: first root/{DEFAULT_ATTRIBUTION_JSONL_REL}).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    initial_roots = [Path(raw).expanduser().resolve() for raw in args.root] or [Path.cwd().resolve()]
    trace_jsonl = (
        Path(args.jsonl_in).expanduser().resolve()
        if args.jsonl_in
        else (initial_roots[0] / DEFAULT_TRACE_JSONL_REL).resolve()
    )
    output_jsonl = (
        Path(args.jsonl_out).expanduser().resolve()
        if args.jsonl_out
        else (initial_roots[0] / DEFAULT_ATTRIBUTION_JSONL_REL).resolve()
    )

    if not trace_jsonl.exists():
        parser.error(f"Missing input trace JSONL: {trace_jsonl}")

    events = _load_jsonl(trace_jsonl)
    roots = _resolve_roots(args.root, events, trace_jsonl)
    rows = derive_attribution_rows(events, roots)
    _write_jsonl(output_jsonl, rows)
    print(
        json.dumps(
            {
                "input_events": len(events),
                "attribution_rows": len(rows),
                "jsonl_in": str(trace_jsonl),
                "jsonl_out": str(output_jsonl),
                "roots": [str(root) for root in roots],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

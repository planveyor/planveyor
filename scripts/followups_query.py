#!/usr/bin/env python3
"""Structured operational views over `docs/followups/*`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import followups_lint as common


_CLEANUP_RECEIPT_DECISION_ORDER = {
    "delete-ready": 0,
    "needs-richer-summary": 1,
    "retain": 2,
}


def _short_text(value: object, *, limit: int = 180) -> str:
    rendered = str(value or "").replace("\n", " ").strip()
    rendered = " ".join(rendered.split())
    if not rendered:
        return "none"
    if len(rendered) <= limit:
        return rendered
    return rendered[: limit - 3].rstrip() + "..."


def _list_marker(value: object) -> str:
    if not isinstance(value, list) or not value:
        return "none"
    return ",".join(_short_text(item, limit=80) for item in value)


def _missing_proof_marker(value: object) -> str:
    if not isinstance(value, list) or not value:
        return "0"
    refs: list[str] = []
    for ref in value:
        if isinstance(ref, dict):
            refs.append(_short_text(ref.get("plan") or ref.get("target_path") or ref.get("summary") or ref, limit=80))
        else:
            refs.append(_short_text(ref, limit=80))
    return f"{len(value)}[{','.join(refs)}]"


def _cleanup_receipt_sort_key(row: dict[str, object]) -> tuple[int, str, str]:
    decision = str(row.get("decision") or "")
    return (
        _CLEANUP_RECEIPT_DECISION_ORDER.get(decision, 99),
        decision,
        str(row.get("source_path") or row.get("file") or ""),
    )


def _cleanup_receipt_row_line(row: dict[str, object]) -> str:
    source_path = _short_text(row.get("source_path") or row.get("file"), limit=120)
    decision = _short_text(row.get("decision"), limit=40)
    return " | ".join(
        [
            f"source_path={source_path}",
            f"decision={decision}",
            f"reason={_short_text(row.get('reason'), limit=120)}",
            f"items={row.get('items', 0)}",
            f"reverse_reference_count={row.get('reverse_reference_count', 0)}",
            f"missing_proof_refs={_missing_proof_marker(row.get('missing_proof_refs'))}",
            f"source_statuses={_list_marker(row.get('source_statuses'))}",
            f"source_classifications={_list_marker(row.get('source_classifications'))}",
            f"proof_classes={_list_marker(row.get('proof_classes'))}",
            f"semantic_compression_preserved={str(bool(row.get('semantic_compression_preserved'))).lower()}",
            f"preserved_summary={_short_text(row.get('preserved_summary'))}",
        ]
    )


def _cleanup_receipt_text(rows: list[dict[str, object]]) -> str:
    decision_counts = common.cleanup_receipt_decision_counts(rows)
    count_parts = [
        f"{decision}={decision_counts.get(decision, 0)}"
        for decision in ("delete-ready", "retain", "needs-richer-summary")
    ]
    unknown_decisions = sorted(
        decision
        for decision in decision_counts
        if decision not in {"delete-ready", "retain", "needs-richer-summary", "other"}
    )
    count_parts.extend(f"{decision}={decision_counts[decision]}" for decision in unknown_decisions)
    count_parts.append(f"other={decision_counts.get('other', 0)}")

    delete_ready_rows = [row for row in rows if row.get("decision") == "delete-ready"]
    lines = [
        "view: cleanup-receipt",
        f"count: {len(rows)}",
        f"candidate_count: {len(rows)}",
        "decision_counts: " + "; ".join(count_parts),
        f"delete-ready: {len(delete_ready_rows)}",
        "read_only: true; decision=delete-ready is not deletion permission; Owner cleanup requires fresh archive/suggest and a separate cleanup action.",
        "delete-ready checklist:",
    ]
    if delete_ready_rows:
        for row in sorted(delete_ready_rows, key=_cleanup_receipt_sort_key):
            source_path = _short_text(row.get("source_path") or row.get("file"), limit=120)
            lines.append(
                f"- [ ] {source_path} | items={row.get('items', 0)} | summary={_short_text(row.get('preserved_summary'))}"
            )
    else:
        lines.append("- none")

    lines.append("source drill-down:")
    if not rows:
        lines.append("- none")
    else:
        for row in sorted(rows, key=_cleanup_receipt_sort_key):
            lines.append(f"- {_cleanup_receipt_row_line(row)}")
    return "\n".join(lines)


def _text_rows(view: str, rows: list[dict[str, object]]) -> str:
    if view == "cleanup-receipt":
        return _cleanup_receipt_text(rows)

    lines = [f"view: {view}", f"count: {len(rows)}"]
    for row in rows:
        summary = str(row.get("summary") or row.get("preserved_summary") or row.get("file"))
        file_part = f"{row.get('file')}:{row.get('line')}" if row.get("line") else str(row.get("file"))
        extra: list[str] = []
        if row.get("priority"):
            extra.append(str(row["priority"]))
        if row.get("to"):
            extra.append(f"to={row['to']}")
        if row.get("status"):
            extra.append(f"status={row['status']}")
        if row.get("source_ref"):
            extra.append(f"source_ref={row['source_ref']}")
        if row.get("item_id"):
            extra.append(f"item_id={row['item_id']}")
        if row.get("plan"):
            extra.append(f"plan={row['plan']}")
        if row.get("reason"):
            extra.append(f"reason={row['reason']}")
        if row.get("imported_into"):
            extra.append(f"imported_into={row['imported_into']}")
        if row.get("target_status"):
            extra.append(f"target_status={row['target_status']}")
        if row.get("decision"):
            extra.append(f"decision={row['decision']}")
        if row.get("reverse_reference_count") is not None:
            extra.append(f"reverse_references={row['reverse_reference_count']}")
        lines.append(f"- {file_part} | {summary} | {'; '.join(extra)}".rstrip(" |"))
    return "\n".join(lines)


def _load_rows(view: str, project_root: Path) -> list[dict[str, object]]:
    files = common.load_followup_files(project_root)
    if view == "ready-candidates":
        return [common.record_for_item(item) for item in common.ready_candidates(files)]
    if view == "needs-owner-triage":
        return [common.record_for_item(item) for item in common.needs_owner_triage(files)]
    if view == "broken-plan-links":
        return common.broken_plan_links(files, project_root)
    if view == "stale-promoted":
        return [
            common.record_for_item(item, reason=state.bucket, target_state=state)
            for item, state in common.stale_promoted(files, project_root)
        ]
    if view == "cleanup-ready":
        return [
            {
                "file": followup.rel_path,
                "status": followup.header_status,
                "imported_into": followup.imported_into,
                "items": len(followup.items),
            }
            for followup in common.cleanup_ready(files)
        ]
    if view == "cleanup-receipt":
        return common.cleanup_receipt_rows(files, project_root)
    raise ValueError(f"Unsupported view: {view}")


def _filter_identity_rows(
    rows: list[dict[str, object]],
    *,
    source_ref: str | None,
    item_id: str | None,
) -> list[dict[str, object]]:
    """Filter only on explicit V2 identity fields, never summary/path similarity."""

    normalized_source = common.normalize_source_ref(source_ref) if source_ref else None
    if source_ref and normalized_source is None:
        raise ValueError("--source-ref must be one safe repo-relative V2 source reference")
    out: list[dict[str, object]] = []
    for row in rows:
        if normalized_source is not None and row.get("source_ref") != normalized_source:
            continue
        if item_id and row.get("item_id") != item_id:
            continue
        out.append(row)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="followups_query",
        description="Structured operational views for followups backlog files.",
    )
    parser.add_argument(
        "view",
        choices=(
            "ready-candidates",
            "needs-owner-triage",
            "broken-plan-links",
            "stale-promoted",
            "cleanup-ready",
            "cleanup-receipt",
        ),
        help="Named operational view.",
    )
    parser.add_argument("--project-root", default="", help="Repo root that owns `docs/followups/*` (default: cwd).")
    parser.add_argument("--source-ref", default="", help="Exact V2 source_ref filter (no heuristic matching).")
    parser.add_argument("--item-id", default="", help="Exact V2 item_id filter (no mutable line alias).")
    parser.add_argument("--format", choices=("text", "json"), default="text", help="Output format.")
    args = parser.parse_args(argv)

    project_root = common.resolve_project_root(args.project_root or None)
    try:
        rows = _filter_identity_rows(
            _load_rows(args.view, project_root),
            source_ref=args.source_ref or None,
            item_id=args.item_id or None,
        )
    except ValueError as exc:
        parser.error(str(exc))

    if args.format == "json":
        payload = {
            "project_root": str(project_root),
            "view": args.view,
            "count": len(rows),
            "rows": rows,
        }
        if args.view == "cleanup-receipt":
            payload["candidate_count"] = len(rows)
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    else:
        sys.stdout.write(_text_rows(args.view, rows) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

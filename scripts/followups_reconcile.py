#!/usr/bin/env python3
"""Reconcile promoted follow-ups against live plan/doc targets."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import followups_lint as common


def _report_payload(project_root: Path) -> dict[str, object]:
    files = common.load_followup_files(project_root)
    v2_observed = [
        common.record_for_item(item)
        for followup in files
        if common.is_v2_followup(followup)
        for item in followup.items
    ]
    broken = common.broken_plan_links(files, project_root)
    missing = [row for row in broken if row.get("reason") == "missing_plan_target"]
    broken_only = [row for row in broken if row.get("reason") != "missing_plan_target"]
    stale = [
        common.record_for_item(item, reason=state.bucket, target_state=state)
        for item, state in common.stale_promoted(files, project_root)
    ]
    candidates = [
        common.record_for_item(item, reason="candidate_handled", target_state=state)
        for item, state in common.candidate_handled(files, project_root)
    ]
    needs_closure_proof = [
        common.record_for_item(item, reason="candidate_needs_closure_proof", target_state=state)
        for item, state in common.candidate_needs_closure_proof(files, project_root)
    ]
    cleanup = [
        {
            "file": followup.rel_path,
            "status": followup.header_status,
            "imported_into": followup.imported_into,
            "items": len(followup.items),
        }
        for followup in common.cleanup_ready(files)
    ]
    return {
        "project_root": str(project_root),
        "broken_plan_link": broken_only,
        "missing_plan_target": missing,
        "stale_promoted": stale,
        "candidate_handled": candidates,
        "candidate_needs_closure_proof": needs_closure_proof,
        "external_v2_observed": v2_observed,
        "cleanup_ready": cleanup,
    }


def _proven_legacy_mutation_files(project_root: Path) -> list[common.FollowupFile]:
    """Return only compatibility carriers after one full V2 integrity check."""

    try:
        from followups_capture import CaptureError, snapshot_followups
    except ModuleNotFoundError:
        from scripts.followups_capture import CaptureError, snapshot_followups
    try:
        snapshot, file_bytes = snapshot_followups(project_root, include_bytes=True)
    except CaptureError as exc:
        raise RuntimeError(f"follow-ups snapshot is unsafe: {exc}") from exc
    inventory = common._inventory_followups_snapshot(project_root, snapshot, file_bytes)
    if inventory.blockers:
        codes = ", ".join(sorted({finding.code for finding in inventory.blockers}))
        raise RuntimeError(f"follow-ups V2 integrity blocker: {codes}")
    return [inventory.legacy_v1[rel_path] for rel_path in sorted(inventory.legacy_v1)]


def _text_report(payload: dict[str, object]) -> str:
    lines = [f"project_root: {payload['project_root']}"]
    for key in (
        "broken_plan_link",
        "missing_plan_target",
        "stale_promoted",
        "candidate_handled",
        "candidate_needs_closure_proof",
        "external_v2_observed",
        "cleanup_ready",
    ):
        rows = payload[key]
        assert isinstance(rows, list)
        lines.append(f"{key}: {len(rows)}")
        for row in rows:
            summary = row.get("summary") or row.get("file")
            location = f"{row.get('file')}:{row.get('line')}" if row.get("line") else str(row.get("file"))
            extras: list[str] = []
            if row.get("plan"):
                extras.append(f"plan={row['plan']}")
            if row.get("reason"):
                extras.append(f"reason={row['reason']}")
            if row.get("target_status"):
                extras.append(f"target_status={row['target_status']}")
            if row.get("target_closure_proof_class"):
                extras.append(f"proof_class={row['target_closure_proof_class']}")
            if row.get("imported_into"):
                extras.append(f"imported_into={row['imported_into']}")
            lines.append(f"- {location} | {summary} | {'; '.join(extras)}".rstrip(" |"))
    return "\n".join(lines)


def _apply_candidate_handled(project_root: Path, write_to: Path | None) -> dict[str, object]:
    files = _proven_legacy_mutation_files(project_root)
    replacements_by_file: dict[str, dict[int, str]] = {}
    candidate_rows: list[dict[str, object]] = []
    for item, state in common.candidate_handled(files, project_root):
        next_body = common.upsert_field(item.body, "status", "handled")
        replacements_by_file.setdefault(item.rel_path, {})[item.line_no] = item.render_line(body=next_body, mark="x")
        candidate_rows.append(common.record_for_item(item, reason="candidate_handled", target_state=state))

    written_files: list[dict[str, object]] = []
    for followup in files:
        replacements = replacements_by_file.get(followup.rel_path)
        if not replacements:
            continue
        text = followup.updated_text(replacements)
        if write_to is None:
            dest = followup.path
        else:
            dest = (write_to / followup.rel_path).resolve()
            dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        written_files.append(
            {
                "source": followup.rel_path,
                "destination": str(dest),
                "changes": len(replacements),
            }
        )

    payload = _report_payload(project_root)
    payload["applied"] = {
        "candidate_handled": candidate_rows,
        "written_files": written_files,
        "write_to": str(write_to) if write_to is not None else None,
    }
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="followups_reconcile",
        description="Report or apply safe promoted->handled reconciliation for followups backlog files.",
    )
    parser.add_argument("--project-root", default="", help="Repo root that owns `docs/followups/*` (default: cwd).")
    parser.add_argument("--format", choices=("text", "json"), default="text", help="Output format.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--report", action="store_true", help="Emit report only (default).")
    mode.add_argument("--apply", action="store_true", help="Apply safe promoted->handled transitions.")
    parser.add_argument(
        "--write-to",
        default="",
        help="Optional sandbox output dir. When set with `--apply`, writes changed followups files under this directory instead of the project repo.",
    )
    args = parser.parse_args(argv)

    project_root = common.resolve_project_root(args.project_root or None)
    write_to = Path(args.write_to).expanduser().resolve() if args.write_to else None
    try:
        payload = _apply_candidate_handled(project_root, write_to) if args.apply else _report_payload(project_root)
    except RuntimeError as exc:
        sys.stderr.write(f"followups_reconcile: BLOCKED: {exc}\n")
        return 2

    if args.format == "json":
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    else:
        text = _text_report(payload)
        if args.apply:
            applied = payload.get("applied", {})
            assert isinstance(applied, dict)
            written = applied.get("written_files", [])
            assert isinstance(written, list)
            text += f"\napplied_files: {len(written)}"
        sys.stdout.write(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

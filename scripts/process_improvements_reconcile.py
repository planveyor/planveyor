#!/usr/bin/env python3
"""Reconcile promoted process-improvement rows against repo-backed terminal carriers."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import process_improvements_collect as common


REPO_LOCAL_EXECUTION_KINDS = {
    "plan",
    "helper",
    "canon_doc",
    "rollout_packet",
    "umbrella_wave",
}
STATUS_RE = re.compile(r"^\s*(?:-\s*)?\*\*Status:\*\*\s*(?P<value>.+?)\s*$", re.IGNORECASE)
NON_PLAN_PROOF_RE = re.compile(r"(?m)^\s*(?:-\s*)?process_improvement_id:\s*(?P<entry_id>PI-\d+)\s*$")


def _normalize_status(raw: str | None) -> str | None:
    value = common._normalize_scalar(raw)
    if value is None:
        return None
    value = value.replace("✅", "").strip().lower()
    return " ".join(value.split())


def _read_header_status(path: Path) -> str | None:
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[:60]:
        match = STATUS_RE.match(line)
        if match:
            return _normalize_status(match.group("value"))
    return None


def _carrier_process_improvement_ids(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return [match.group("entry_id") for match in NON_PLAN_PROOF_RE.finditer(text)]


def _literal_ref(raw: str) -> str | None:
    value = common._normalize_scalar(raw)
    if value is None or value.lower() in {"null", "none", "unknown"}:
        return None
    if any(ch.isspace() for ch in value):
        return None
    return value


def _repo_relative_ref(project_root: Path, raw_ref: str) -> tuple[str, Path] | None:
    project_root = project_root.resolve()
    path = Path(raw_ref).expanduser()
    resolved = path.resolve() if path.is_absolute() else (project_root / path).resolve()
    try:
        rel = resolved.relative_to(project_root)
    except ValueError:
        return None
    return rel.as_posix(), resolved


def _record(
    *,
    category: str,
    file_rel: str,
    entry: common.BacklogEntry,
    reason: str,
    target_path: str | None = None,
    target_status: str | None = None,
    handled_ref: str | None = None,
    missing_carrier_fields: list[str] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "category": category,
        "file": file_rel,
        "entry_id": entry.entry_id,
        "status": entry.status,
        "owner": entry.owner,
        "promotion_class": entry.promotion_class,
        "target_canon_path": entry.target_canon_path,
        "execution_kind": entry.execution_kind,
        "execution_ref": entry.execution_ref,
        "reason": reason,
    }
    if target_path is not None:
        payload["target_path"] = target_path
    if target_status is not None:
        payload["target_status"] = target_status
    if handled_ref is not None:
        payload["handled_ref"] = handled_ref
    if missing_carrier_fields is not None:
        payload["missing_carrier_fields"] = missing_carrier_fields
    if category == "candidate_handled":
        payload["needs_reconcile"] = True
    return payload


def classify_entry(project_root: Path, *, file_rel: str, entry: common.BacklogEntry) -> dict[str, object]:
    carrier_issues = common.triage_carrier_issues(entry)
    if carrier_issues:
        return _record(
            category="missing_carrier",
            file_rel=file_rel,
            entry=entry,
            reason="missing_triage_carrier",
            missing_carrier_fields=[issue.field for issue in carrier_issues],
        )

    ref = _literal_ref(entry.execution_ref)
    if ref is None:
        return _record(category="missing_execution_ref", file_rel=file_rel, entry=entry, reason="missing_execution_ref")

    if entry.execution_kind == "external_ref":
        return _record(
            category="stale_promoted",
            file_rel=file_rel,
            entry=entry,
            reason="external_ref_not_file_backed",
            target_path=ref,
        )

    if entry.execution_kind not in REPO_LOCAL_EXECUTION_KINDS:
        return _record(
            category="stale_promoted",
            file_rel=file_rel,
            entry=entry,
            reason="unsupported_execution_kind",
            target_path=ref,
        )

    resolved = _repo_relative_ref(project_root, ref)
    if resolved is None:
        return _record(
            category="missing_execution_ref",
            file_rel=file_rel,
            entry=entry,
            reason="execution_ref_outside_project_root",
            target_path=ref,
        )
    target_rel, target_path = resolved
    if not target_path.exists():
        return _record(
            category="missing_execution_ref",
            file_rel=file_rel,
            entry=entry,
            reason="missing_repo_local_execution_ref",
            target_path=target_rel,
        )

    if entry.execution_kind == "plan":
        status = _read_header_status(target_path)
        if status == "done":
            return _record(
                category="candidate_handled",
                file_rel=file_rel,
                entry=entry,
                reason="done_plan",
                target_path=target_rel,
                target_status=status,
                handled_ref=target_rel,
            )
        return _record(
            category="stale_promoted",
            file_rel=file_rel,
            entry=entry,
            reason="stale_plan" if status == "superseded" else "non_terminal_plan",
            target_path=target_rel,
            target_status=status,
        )

    proof_ids = _carrier_process_improvement_ids(target_path)
    if not proof_ids:
        return _record(
            category="stale_promoted",
            file_rel=file_rel,
            entry=entry,
            reason="missing_process_improvement_id",
            target_path=target_rel,
        )
    if len(proof_ids) > 1:
        return _record(
            category="stale_promoted",
            file_rel=file_rel,
            entry=entry,
            reason="ambiguous_process_improvement_id",
            target_path=target_rel,
        )
    if proof_ids[0] != entry.entry_id:
        return _record(
            category="stale_promoted",
            file_rel=file_rel,
            entry=entry,
            reason="process_improvement_id_mismatch",
            target_path=target_rel,
        )

    return _record(
        category="candidate_handled",
        file_rel=file_rel,
        entry=entry,
        reason="verified_process_improvement_id",
        target_path=target_rel,
        handled_ref=target_rel,
    )


def _selected_backlogs(project_root: Path, raw_backlogs: list[str] | None) -> list[Path]:
    if raw_backlogs:
        return [common.resolve_backlog_path(project_root, backlog) for backlog in raw_backlogs]
    return common.iter_backlog_paths(project_root)


def report_payload(
    *,
    project_root: Path,
    backlogs: list[str] | None = None,
    entries: set[str] | None = None,
) -> dict[str, object]:
    project_root = project_root.resolve()
    rows = {
        "candidate_handled": [],
        "stale_promoted": [],
        "missing_execution_ref": [],
        "missing_carrier": [],
    }
    for backlog_path in _selected_backlogs(project_root, backlogs):
        backlog = common.parse_backlog_file(backlog_path, project_root)
        file_rel = backlog_path.relative_to(project_root).as_posix()
        for entry in backlog.entries:
            if entry.status != "promoted" and not (entry.status == "triaged" and entry.execution_kind == "plan"):
                continue
            if entries is not None and entry.entry_id not in entries:
                continue
            record = classify_entry(project_root, file_rel=file_rel, entry=entry)
            category = record["category"]
            if entry.status == "triaged" and category not in {"candidate_handled", "missing_carrier"}:
                continue
            assert category in rows
            rows[category].append(record)
    return {
        "project_root": str(project_root),
        **rows,
    }


def apply_candidate_handled(
    *,
    project_root: Path,
    backlogs: list[str] | None,
    entries: set[str] | None,
    handled_at: str,
    handled_ref: str | None,
) -> dict[str, object]:
    project_root = project_root.resolve()
    normalized_handled_at = common._normalize_optional_timestamp(handled_at, field_name="handled_at")
    if normalized_handled_at == "null":
        raise ValueError("Missing required field: handled_at")

    before = report_payload(project_root=project_root, backlogs=backlogs, entries=entries)
    candidates = list(before["candidate_handled"])
    applied: list[dict[str, object]] = []
    derived_surfaces: dict[str, str] = {}
    for candidate in candidates:
        file_rel = str(candidate["file"])
        entry_id = str(candidate["entry_id"])
        next_handled_ref = handled_ref or str(candidate["handled_ref"])
        result = common.update_backlog_entry(
            project_root=project_root,
            backlog_path=project_root / file_rel,
            entry_id=entry_id,
            status="handled",
            handled_ref=next_handled_ref,
            handled_at=normalized_handled_at,
            triage_note=f"handled via process_improvements_reconcile.py ({candidate['reason']})",
        )
        applied.append(
            {
                "file": file_rel,
                "entry_id": entry_id,
                "handled_ref": next_handled_ref,
                "handled_at": normalized_handled_at,
                "reason": candidate["reason"],
            }
        )
        result_surfaces = result.get("derived_surfaces", {})
        if isinstance(result_surfaces, dict):
            derived_surfaces.update({str(key): str(value) for key, value in result_surfaces.items()})

    after = report_payload(project_root=project_root, backlogs=backlogs, entries=entries)
    return {
        **after,
        "applied": {
            "candidate_handled": applied,
            "derived_surfaces": derived_surfaces,
        },
    }


def _text_payload(payload: dict[str, object]) -> str:
    lines = [f"project_root: {payload['project_root']}"]
    for key in ("candidate_handled", "stale_promoted", "missing_execution_ref", "missing_carrier"):
        rows = payload[key]
        assert isinstance(rows, list)
        lines.append(f"{key}: {len(rows)}")
        for row in rows:
            extras = [
                f"execution_kind={row.get('execution_kind')}",
                f"execution_ref={row.get('execution_ref')}",
                f"reason={row.get('reason')}",
            ]
            missing_fields = row.get("missing_carrier_fields")
            if isinstance(missing_fields, list):
                extras.append(f"missing_carrier_fields={','.join(str(field) for field in missing_fields)}")
            if row.get("target_status") is not None:
                extras.append(f"target_status={row.get('target_status')}")
            lines.append(f"- {row.get('file')}:{row.get('entry_id')} | {'; '.join(extras)}")
    applied = payload.get("applied")
    if isinstance(applied, dict):
        rows = applied.get("candidate_handled", [])
        assert isinstance(rows, list)
        lines.append(f"applied_candidate_handled: {len(rows)}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="process_improvements_reconcile",
        description="Report or apply safe promoted->handled sync for process-improvement rows.",
    )
    parser.add_argument("--project-root", default="", help="Repo root (default: cwd).")
    parser.add_argument("--backlog", action="append", help="Optional backlog file under docs/process_improvements/.")
    parser.add_argument("--entry", action="append", help="Optional entry id filter like PI-001.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--report", action="store_true", help="Emit report only (default).")
    mode.add_argument("--apply", action="store_true", help="Mark safe candidate_handled rows as handled.")
    parser.add_argument("--handled-at", help="Handled timestamp receipt; required with --apply.")
    parser.add_argument("--handled-ref", help="Optional handled_ref override for apply.")
    parser.add_argument("--format", choices=("text", "json"), default="text", help="Output format.")
    parser.add_argument("--json", action="store_true", help="Alias for `--format json`.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    project_root = common.resolve_project_root(args.project_root or None)
    entries = set(args.entry) if args.entry else None
    try:
        if args.apply:
            if not args.handled_at:
                parser.error("--handled-at is required with --apply")
            payload = apply_candidate_handled(
                project_root=project_root,
                backlogs=args.backlog,
                entries=entries,
                handled_at=args.handled_at,
                handled_ref=args.handled_ref,
            )
        else:
            payload = report_payload(project_root=project_root, backlogs=args.backlog, entries=entries)
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    output_format = "json" if args.json else args.format
    if output_format == "json":
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    else:
        sys.stdout.write(_text_payload(payload) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

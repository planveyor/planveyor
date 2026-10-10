#!/usr/bin/env python3
"""Promote one process-improvement row with explicit execution pointers."""

from __future__ import annotations

import argparse
import json
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


def _normalize_literal(raw: str | None, *, field_name: str) -> str:
    value = common._normalize_scalar(raw)
    if value is None or value.lower() in {"null", "none", "unknown"}:
        raise ValueError(f"Missing required field: {field_name}")
    if any(ch.isspace() for ch in value):
        raise ValueError(f"{field_name} must be a literal ref without whitespace: {value!r}")
    return value


def _normalize_execution_kind(raw: str | None) -> str:
    value = _normalize_literal(raw, field_name="execution_kind").lower()
    if value not in common.EXECUTION_KINDS:
        raise ValueError(f"Unsupported execution_kind: {value!r}")
    return value


def _repo_relative_ref(project_root: Path, raw_ref: str) -> tuple[str, Path]:
    project_root = project_root.resolve()
    path = Path(raw_ref).expanduser()
    resolved = path.resolve() if path.is_absolute() else (project_root / path).resolve()
    try:
        rel = resolved.relative_to(project_root)
    except ValueError as exc:
        raise ValueError(f"execution_ref must stay inside project root for repo-local kinds: {raw_ref}") from exc
    return rel.as_posix(), resolved


def normalize_execution_ref(project_root: Path, *, execution_kind: str, execution_ref: str) -> str:
    ref = _normalize_literal(execution_ref, field_name="execution_ref")
    if execution_kind == "external_ref":
        return ref
    if execution_kind not in REPO_LOCAL_EXECUTION_KINDS:
        raise ValueError(f"Unsupported repo-local execution_kind: {execution_kind!r}")
    rel_ref, resolved = _repo_relative_ref(project_root, ref)
    if not resolved.exists():
        raise FileNotFoundError(f"Missing execution_ref for repo-local kind {execution_kind!r}: {rel_ref}")
    return rel_ref


def _find_entry(project_root: Path, backlog_path: Path, entry_id: str) -> common.BacklogEntry:
    backlog = common.parse_backlog_file(backlog_path, project_root)
    for entry in backlog.entries:
        if entry.entry_id == entry_id:
            return entry
    rel = backlog_path.relative_to(project_root).as_posix()
    raise ValueError(f"Missing entry `{entry_id}` in {rel}")


def _validate_promotable(entry: common.BacklogEntry) -> None:
    if entry.status in {"promoted", "handled", "rejected"}:
        raise ValueError(f"Cannot promote row already in status={entry.status!r}: {entry.entry_id}")
    missing = [
        field_name
        for field_name in ("target_canon_path", "target_repo_scope", "delivery_mode", "priority")
        if getattr(entry, field_name) == "null" or getattr(entry, field_name) == "P?"
    ]
    if missing:
        raise ValueError(f"Cannot promote row without mature target fields: {', '.join(missing)}")


def build_payload(
    *,
    project_root: Path,
    backlog_path: Path,
    entry_id: str,
    execution_kind: str,
    execution_ref: str,
    promoted_at: str,
    delivery_refs: str | None,
    triage_note: str | None,
    apply: bool,
) -> dict[str, object]:
    project_root = project_root.resolve()
    backlog_path = backlog_path.resolve()
    entry = _find_entry(project_root, backlog_path, entry_id)
    _validate_promotable(entry)

    normalized_kind = _normalize_execution_kind(execution_kind)
    normalized_ref = normalize_execution_ref(
        project_root,
        execution_kind=normalized_kind,
        execution_ref=execution_ref,
    )
    normalized_promoted_at = common._normalize_optional_timestamp(promoted_at, field_name="promoted_at")
    if normalized_promoted_at == "null":
        raise ValueError("Missing required field: promoted_at")
    normalized_delivery_refs = common._normalize_delivery_refs(
        delivery_refs if delivery_refs is not None else entry.delivery_refs
    )

    backlog_rel = backlog_path.relative_to(project_root).as_posix()
    mutation = {
        "status": "promoted",
        "execution_kind": normalized_kind,
        "execution_ref": normalized_ref,
        "delivery_refs": normalized_delivery_refs,
        "promoted_at": normalized_promoted_at,
    }
    if triage_note is not None:
        mutation["triage_note"] = common._normalize_ref(triage_note, field_name="triage_note")

    payload: dict[str, object] = {
        "project_root": str(project_root),
        "mode": "apply" if apply else "report",
        "file": backlog_rel,
        "entry_id": entry.entry_id,
        "before": {
            "status": entry.status,
            "execution_kind": entry.execution_kind,
            "execution_ref": entry.execution_ref,
            "delivery_refs": entry.delivery_refs,
            "promoted_at": entry.promoted_at,
        },
        "mutation": mutation,
        "writes": [
            backlog_rel,
            common.INDEX_PATH.as_posix(),
            common.DEFERRED_PATH.as_posix(),
            common.PROMOTION_PATH.as_posix(),
        ],
    }

    if apply:
        updated = common.update_backlog_entry(
            project_root=project_root,
            backlog_path=backlog_path,
            entry_id=entry.entry_id,
            status="promoted",
            execution_kind=normalized_kind,
            execution_ref=normalized_ref,
            delivery_refs=normalized_delivery_refs,
            promoted_at=normalized_promoted_at,
            triage_note=triage_note,
        )
        payload["applied"] = updated
    return payload


def _text_payload(payload: dict[str, object]) -> str:
    mutation = payload["mutation"]
    assert isinstance(mutation, dict)
    writes = payload["writes"]
    assert isinstance(writes, list)
    return "\n".join(
        [
            "process-improvements-promote:",
            f" mode={payload['mode']}",
            f" file={payload['file']}",
            f" entry_id={payload['entry_id']}",
            f" status={mutation['status']}",
            f" execution_kind={mutation['execution_kind']}",
            f" execution_ref={mutation['execution_ref']}",
            f" delivery_refs={mutation['delivery_refs']}",
            f" promoted_at={mutation['promoted_at']}",
            f" writes={','.join(str(path) for path in writes)}",
        ]
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="process_improvements_promote",
        description="Report or apply a bounded process-improvement promoted pointer update.",
    )
    parser.add_argument("--project-root", default="", help="Repo root (default: cwd).")
    parser.add_argument("--backlog", required=True, help="Backlog file under docs/process_improvements/.")
    parser.add_argument("--entry", required=True, help="Entry id like PI-001.")
    parser.add_argument("--execution-kind", required=True, help="Execution carrier kind.")
    parser.add_argument("--execution-ref", required=True, help="Existing repo-local carrier path or external literal ref.")
    parser.add_argument("--promoted-at", required=True, help="Promotion timestamp receipt.")
    parser.add_argument("--delivery-refs", help="`null` or a `; `-separated literal delivery ref list.")
    parser.add_argument("--triage-note", help="Optional replacement triage note.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--report", action="store_true", help="Preview without writing files (default).")
    mode.add_argument("--apply", action="store_true", help="Write the raw backlog row and regenerated surfaces.")
    parser.add_argument("--format", choices=("text", "json"), default="text", help="Output format.")
    parser.add_argument("--json", action="store_true", help="Alias for `--format json`.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    project_root = common.resolve_project_root(args.project_root or None)
    backlog_path = common.resolve_backlog_path(project_root, args.backlog)
    try:
        payload = build_payload(
            project_root=project_root,
            backlog_path=backlog_path,
            entry_id=args.entry,
            execution_kind=args.execution_kind,
            execution_ref=args.execution_ref,
            promoted_at=args.promoted_at,
            delivery_refs=args.delivery_refs,
            triage_note=args.triage_note,
            apply=args.apply,
        )
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

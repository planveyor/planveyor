#!/usr/bin/env python3
"""Deterministic triage updates for process-improvement backlog rows."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import process_improvements_collect as common


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="process_improvements_triage",
        description="Update one row in docs/process_improvements/* and rebuild derived surfaces.",
    )
    parser.add_argument("--project-root", default="", help="Repo root (default: cwd).")
    parser.add_argument("--backlog", required=True, help="Backlog file under docs/process_improvements/.")
    parser.add_argument("--entry", required=True, help="Entry id like PI-001.")
    parser.add_argument("--status", help="New triage status.")
    parser.add_argument("--priority", help="New priority (`P0`, `P1`, `P2`, `P?`).")
    parser.add_argument("--owner", help="New owner role.")
    parser.add_argument("--promotion-class", help="New promotion class.")
    parser.add_argument("--target-canon-path", help="Literal target canon/helper path or `null`.")
    parser.add_argument(
        "--target-repo-scope",
        help="Literal target repo scope (`current-consumer`, `<target-repo>`, `multi_repo`) or `null`.",
    )
    parser.add_argument(
        "--delivery-mode",
        help="Literal delivery mode (`source_only`, `source_plus_rollout`, `packet_only`, `umbrella_mixed`) or `null`.",
    )
    parser.add_argument(
        "--execution-kind",
        help="Execution carrier kind (`plan`, `helper`, `canon_doc`, `rollout_packet`, `umbrella_wave`, `external_ref`) or `null`.",
    )
    parser.add_argument("--execution-ref", help="Primary literal execution carrier or `null`.")
    parser.add_argument("--delivery-refs", help="`null` or a `; `-separated literal delivery ref list.")
    parser.add_argument("--handled-ref", help="Terminal proof carrier for handled rows or `null`.")
    parser.add_argument("--promoted-at", help="Promotion timestamp receipt or `null`.")
    parser.add_argument("--handled-at", help="Handled timestamp receipt or `null`.")
    parser.add_argument("--triage-note", help="Human-readable triage note.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not any(
        value is not None
        for value in (
            args.status,
            args.priority,
            args.owner,
            args.promotion_class,
            args.target_canon_path,
            args.target_repo_scope,
            args.delivery_mode,
            args.execution_kind,
            args.execution_ref,
            args.delivery_refs,
            args.handled_ref,
            args.promoted_at,
            args.handled_at,
            args.triage_note,
        )
    ):
        parser.error("At least one triage field must be provided")

    project_root = common.resolve_project_root(args.project_root or None)
    backlog_path = common.resolve_backlog_path(project_root, args.backlog)
    try:
        payload = common.update_backlog_entry(
            project_root=project_root,
            backlog_path=backlog_path,
            entry_id=args.entry,
            status=args.status,
            priority=args.priority,
            owner=args.owner,
            promotion_class=args.promotion_class,
            target_canon_path=args.target_canon_path,
            target_repo_scope=args.target_repo_scope,
            delivery_mode=args.delivery_mode,
            execution_kind=args.execution_kind,
            execution_ref=args.execution_ref,
            delivery_refs=args.delivery_refs,
            handled_ref=args.handled_ref,
            promoted_at=args.promoted_at,
            handled_at=args.handled_at,
            triage_note=args.triage_note,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    if args.json:
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    else:
        sys.stdout.write(common._text_payload(payload) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

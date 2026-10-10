#!/usr/bin/env python3
"""Step-local post-merge receipt schema preflight."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from contract_authority_context import ContractAuthorityError
from merge_bundle_report import RECEIPT_PREFLIGHT_STEPS, validate_post_merge_receipt_preflight
from post_merge_packetization_gate import (
    changed_files_for_range,
    read_range,
    resolve_target_applicability,
    same_range_report_paths,
)
from shared_docs_mirror_drift import (
    GENERIC_MIRROR_POLICY,
    MirrorPolicy,
    MirrorPolicyError,
    load_shared_docs_mirror_policy,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=RECEIPT_PREFLIGHT_STEPS)
    parser.add_argument("--path", help="Explicit repo-relative receipt path to preflight.")
    parser.add_argument(
        "--range",
        dest="range_ref",
        help=(
            "Optional BASE..HEAD packetization context; defaults to saved .planveyor range when present. "
            "For docs_finalize, an explicit value selects the strict merge receipt contract."
        ),
    )
    parser.add_argument("--repo-root", default=".", help="Repository root for resolving --path (default: current directory).")
    parser.add_argument("--packetization-required", action="store_true", help="Force packetization handoff token checks even without shared-canon range context.")
    parser.add_argument(
        "--packetization-report",
        action="append",
        default=[],
        help="Packetization report path used to close shared-canon handoff checks; may be repeated.",
    )
    parser.add_argument("--role", default="Coder", help="Role name used when validating docs-finalize process improvements.")
    parser.add_argument("--format", choices=("plain", "json"), default="plain")
    parser.add_argument(
        "--content-profile-id",
        default="default",
        choices=("default", "planveyor", "target-local"),
        help="Resolved public content profile for the generic mirror policy.",
    )
    return parser


def render_plain(payload: dict[str, object]) -> str:
    step = str(payload.get("step") or "")
    path = str(payload.get("path") or "")
    status = str(payload.get("status") or "")
    lines = [f"post_merge_receipt_preflight: {status} step={step} path={path or '(missing)'}"]
    for field in ("proof_scope", "terminal_readiness", "packetization_state"):
        value = payload.get(field)
        if value is not None:
            lines.append(f"{field}={value}")

    receipts = payload.get("receipts")
    if isinstance(receipts, list) and receipts:
        lines.append("receipts:")
        for receipt in receipts:
            if not isinstance(receipt, dict):
                continue
            state = "present" if receipt.get("present") else "missing"
            lines.append(
                f"  - {receipt.get('step')} {receipt.get('receipt')} "
                f"[{state}]: {receipt.get('path')}"
            )
            if (
                receipt.get("receipt") == "packetization_gate"
                and payload.get("packetization_state") == "handoff_recorded_future_step_pending"
            ):
                lines.append("    next_packetization_gate=step:packetization_gate")

    errors = payload.get("errors")
    if isinstance(errors, list) and errors:
        lines.append("errors:")
        for error in errors:
            if not isinstance(error, dict):
                continue
            lines.append(f"  - {error.get('code')}: {error.get('detail')}")
            lines.append(f"    next: {error.get('next_action')}")
    return "\n".join(lines)


def _repo_rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _implicit_saved_range_present(repo_root: Path) -> bool:
    return any(
        (repo_root / filename).exists() or (repo_root / filename).is_symlink()
        for filename in (".planveyor.range.base", ".planveyor.range.head")
    )


def _range_packetization_context(
    *,
    repo_root: Path,
    range_ref: str | None,
    explicit_range: bool,
    mirror_policy: MirrorPolicy = GENERIC_MIRROR_POLICY,
) -> tuple[bool, bool, list[str], str | None, dict[str, object] | None]:
    try:
        resolved_range = range_ref or read_range(repo_root)
        if ".." not in resolved_range:
            raise ValueError(f"range must be BASE..HEAD: {resolved_range}")
        changed_files = changed_files_for_range(repo_root, resolved_range)
    except Exception as exc:
        if explicit_range or _implicit_saved_range_present(repo_root):
            return False, False, [], None, {
                "code": "range_packetization_context_unavailable",
                "detail": str(exc),
            }
        return False, False, [], None, None

    try:
        base, _, head = resolved_range.partition("..")
        applicability = resolve_target_applicability(
            repo_root,
            changed_files=changed_files,
            base=base or None,
            head=head or None,
            mirror_policy=mirror_policy,
        )
    except Exception as exc:
        return False, False, [], None, {
            "code": "range_packetization_context_unavailable",
            "detail": str(exc),
        }
    report_paths = [
        _repo_rel(path, repo_root)
        for path in same_range_report_paths(repo_root, range_ref=resolved_range)
    ]
    return (
        applicability.packetization_report_required,
        applicability.target_packet_required,
        report_paths,
        resolved_range,
        None,
    )


def _error_payload(*, step: str, code: str, detail: str) -> dict[str, object]:
    return {
        "schema_version": "post_merge_receipt_preflight.v1",
        "status": "blocked",
        "step": step,
        "path": "",
        "packetization_required": False,
        "packetization_report_required": False,
        "target_packet_required": False,
        "packetization_reports": [],
        "proof_scope": "step_local_receipt",
        "terminal_readiness": "not_evaluated",
        "packetization_state": "not_evaluated",
        "receipts": [],
        "errors": [
            {
                "code": code,
                "detail": detail,
                "next_action": "fix range context or pass an explicit valid --range, then rerun planveyor_post_merge_receipt_preflight",
            }
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    ns = build_parser().parse_args(argv)
    repo_root = Path(ns.repo_root).resolve()
    try:
        mirror_policy = load_shared_docs_mirror_policy(content_profile_id=ns.content_profile_id)
    except MirrorPolicyError as exc:
        payload = _error_payload(step=ns.step, code="shared_docs_mirror_policy_invalid", detail=str(exc))
        if ns.format == "json":
            sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        else:
            sys.stdout.write(render_plain(payload) + "\n")
        return 1
    if ns.step == "docs_finalize" and ns.range_ref is not None:
        # The merge-only docs-finalize receipt is a pure range identity check; it
        # must be testable before a repository has a diff/packetization context.
        derived_packetization_required, derived_target_packet_required, derived_reports, resolved_range, context_error = (
            False,
            False,
            [],
            ns.range_ref,
            None,
        )
    else:
        (
            derived_packetization_required,
            derived_target_packet_required,
            derived_reports,
            resolved_range,
            context_error,
        ) = _range_packetization_context(
            repo_root=repo_root,
            range_ref=ns.range_ref,
            explicit_range=ns.range_ref is not None,
            mirror_policy=mirror_policy,
        )
    if context_error:
        payload = _error_payload(
            step=ns.step,
            code=str(context_error["code"]),
            detail=str(context_error["detail"]),
        )
        if ns.format == "json":
            sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        else:
            sys.stdout.write(render_plain(payload) + "\n")
        return 1

    packetization_reports = list(ns.packetization_report or []) or derived_reports
    try:
        payload = validate_post_merge_receipt_preflight(
            root=repo_root,
            step=ns.step,
            path=ns.path or "",
            packetization_required=ns.packetization_required or derived_packetization_required,
            target_packet_required=derived_target_packet_required,
            packetization_reports=packetization_reports,
            packetization_range=resolved_range,
            role=ns.role,
            docs_finalize_range=ns.range_ref if ns.step == "docs_finalize" else None,
            mirror_policy=mirror_policy,
        )
    except ContractAuthorityError as exc:
        payload = _error_payload(
            step=ns.step,
            code='contract_authority_preflight_failed',
            detail=exc.reason_code,
        )
        payload['errors'][0]['next_action'] = 'Передайте проверенный Git top-level проекта; не обходите authority guard.'
    if ns.format == "json":
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    else:
        sys.stdout.write(render_plain(payload) + "\n")
    return 0 if payload["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

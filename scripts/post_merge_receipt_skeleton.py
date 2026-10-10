#!/usr/bin/env python3
"""Emit parser-valid post-merge receipt skeleton frames."""

from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path
import sys
from textwrap import dedent
from typing import TYPE_CHECKING, Any, Callable, Sequence

sys.dont_write_bytecode = True
sys.pycache_prefix = os.devnull



_AUTHORITY_SCRIPTS_DIR = Path(__file__).resolve().parent


def _module_has_expected_origin(module: object, expected: Path) -> bool:
    origin = getattr(module, "__file__", None)
    if not isinstance(origin, str):
        return False
    try:
        return Path(origin).resolve(strict=True) == expected
    except (OSError, RuntimeError, ValueError):
        return False


def _scripts_package_is_local() -> bool:
    package = sys.modules.get("scripts")
    if package is None:
        return True
    package_paths = getattr(package, "__path__", None)
    if package_paths is None:
        return False
    try:
        paths = tuple(Path(entry).resolve(strict=True) for entry in package_paths)
    except (OSError, RuntimeError, TypeError, ValueError):
        return False
    if not paths or any(path != _AUTHORITY_SCRIPTS_DIR for path in paths):
        return False
    package_file = getattr(package, "__file__", None)
    return package_file is None or _module_has_expected_origin(
        package, _AUTHORITY_SCRIPTS_DIR / "__init__.py"
    )


def _assert_authority_alias_origin(module: object | None, expected: Path) -> None:
    if module is not None and not _module_has_expected_origin(module, expected):
        raise ImportError("authority module has an unsafe origin")


def _load_authority_context() -> Any:
    """Load only the exact sibling context module under either import spelling."""

    package_name = "scripts.contract_authority_context"
    direct_name = "contract_authority_context"
    package_is_local = _scripts_package_is_local()
    expected = _AUTHORITY_SCRIPTS_DIR / f"{direct_name}.py"
    direct = sys.modules.get(direct_name)
    packaged = sys.modules.get(package_name)
    _assert_authority_alias_origin(direct, expected)
    _assert_authority_alias_origin(packaged, expected)
    if direct is not None and packaged is not None and direct is not packaged:
        raise ImportError("authority module aliases are split")
    module = direct or packaged
    if module is None:
        script_dir = os.fspath(_AUTHORITY_SCRIPTS_DIR)
        if script_dir in sys.path:
            sys.path.remove(script_dir)
        sys.path.insert(0, script_dir)
        module = importlib.import_module(direct_name)
        _assert_authority_alias_origin(module, expected)
    sys.modules[direct_name] = module
    if package_is_local:
        sys.modules[package_name] = module
    return module


authority_context = _load_authority_context()

if TYPE_CHECKING:
    from contract_authority_context import ContractContext
else:
    ContractContext = Any

from post_merge_operational_receipt import SCHEMA_VERSION as OPERATIONAL_SCHEMA_VERSION
from review_schema_contract import CURRENT_REVIEW_SCHEMA_VERSION

PLAN_REF = "docs/plans/260617_2138_process_post_merge_receipt_skeleton_helpers.md"
SUPPORTED_FAMILIES = (
    "canon_sweep_receipt",
    "docs_finalize_receipt",
    "plan_harvest",
    "post_merge_audit",
    "post_merge_operational_receipt",
)


def _with_final_newline(text: str) -> str:
    return text.rstrip() + "\n"


def _render_canon_sweep_receipt() -> str:
    return _with_final_newline(
        dedent(
            """\
            # Canon sweep receipt skeleton

            **Status:** Draft
            **Schema version:** receipt.v1

            ## Canon sweep summary
            - receipt_family: `canon_sweep_receipt`
            - changed_shared_canon_files_count: `N/A (why=skeleton; fill integer before closeout)`
            - changed_shared_canon_files: `N/A (why=skeleton; fill none or comma-separated repo paths before closeout)`
            - proof_kind: `report`
            - snapshot_path: `N/A (why=proof_kind is report; fill only for proof_kind=snapshot)`
            - report_path: `N/A (why=skeleton; fill durable report path before closeout)`
            - no_op_reason: `N/A (why=proof_kind is report; fill only for proof_kind=no_op)`
            - target_repo_impact: `N/A (why=skeleton; fill source_only|shared_consumer|shared_multi|none before closeout)`
            - packetization_handoff: `step:packetization_gate` -> `N/A (why=skeleton; fill packetization report path or bounded no-op before closeout)`
            - range: `<BASE>..<HEAD>`
            - generated_from: `scripts/post_merge_receipt_skeleton.py`

            ## Canon carriers checked
            | carrier | impact | proof |
            | --- | --- | --- |
            | `<docs/path.md>` | `<updated|no_change|deferred>` | `<command/ref or N/A>` |

            ## Packetization handoff
            - packetization_handoff: `step:packetization_gate`
            - packetization_report: `docs/reviews/<stamp>_packetization_gate_range_<base7>_<head7>.md` | `N/A (why=no shared canon delta)`
            - target_repo_impact: `source_only|shared_consumer|shared_multi|none`
            """
        )
    )


def _render_docs_finalize_receipt() -> str:
    """Render the merge-only frame; Architect must replace every placeholder."""

    return _with_final_newline(
        dedent(
            f"""\
            # Docs finalize receipt — range <BASE>..<HEAD>

            **Date:** 01.01.1970 00:00 +0000
            **Role:** Architect
            **BASE:** <BASE>
            **HEAD:** <HEAD>
            **Status:** Draft
            **Schema version:** {CURRENT_REVIEW_SCHEMA_VERSION}

            docs_finalize_receipt_path=docs/reviews/<stamp>_docs_finalize_receipt_range_<base7>_<head7>.md

            ## Process improvements

            NO PROCESS IMPROVEMENTS — why: clean_run
            """
        )
    )


def _render_plan_harvest() -> str:
    return _with_final_newline(
        dedent(
            f"""\
            # Review: Plan harvest — range deadbee..feed123

            **Date:** 29.03.2026 18:20 +0000
            **BASE:** deadbee
            **HEAD:** feed123
            **Status:** Draft
            **Schema version:** {CURRENT_REVIEW_SCHEMA_VERSION}

            ## Follow-ups backlog (created)
            - `docs/followups/260419_1109_followups_range_deadbee_feed123.md`

            ## Follow-ups (extracted; без дублей)
            - Result: `NO FOLLOWUPS` — no remaining actionable debt after full-wave harvest.

            ## Follow-up harvest triage/import receipt
            - harvest_file_followups_result: `NO FOLLOWUPS` — no remaining actionable debt after full-wave harvest.
            - harvest_file_followups_count: 0
            - `planveyor_followups_triage --file docs/followups/260419_1109_followups_range_deadbee_feed123.md --dry-run`: append_new=0, merge_source=0, possible_duplicate=0, route_fallback=0, unparsed_bullets=0.
            - `planveyor_followups_triage --file docs/followups/260419_1109_followups_range_deadbee_feed123.md --apply`: append_new=0, merge_source=0, possible_duplicate=0, route_fallback=0, unparsed_bullets=0.
            - `planveyor_followups_triage --file docs/followups/260419_1109_followups_range_deadbee_feed123.md --apply` (idempotency): append_new=0, merge_source=0, possible_duplicate=0, route_fallback=0, unparsed_bullets=0.
            - `scripts/followups_index_rebuild.py --project-root .`: status=ok; readback_status=ok; index_path=docs/followups/index.md.

            ## Process-improvement promotion decisions
            - `N/A (why=no mature process-improvement rows in fixture)`.

            ## Golden Path lane receipt
            - `lane=tooling_process`; `active carrier=docs/guides/golden_paths.md#post-merge-plan-harvest`; `outcome=no changes needed (why=fixture)`.

            ## ADR candidates / durable decisions
            - `N/A (why=no durable decision candidate in fixture)`.

            ## Canon/follow-up summary
            - canon_updates=0; followups=0.

            ## Docs retrieval metrics receipt

            | repo | repo_role | query_log_status | query_total | with_hits | zero_hits | hit_rate | warnings_total | errors_total | with_event_id | evaluated_total | outcome_evaluated_rate | outcome_used | outcome_partial | outcome_miss | outcome_noise | not_evaluated_total | read_log_status | read_events_total | read_open_rate | unique_paths | used_for_decision | low_coverage_triage | follow_up_ref | accepted_no_op_reason | source_command |
            | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | --- | --- | --- | --- | --- |
            | planveyor | source | present | 3 | 2 | 1 | 66.7% | 1 | 0 | 3 | 2 | 66.7% | 1 | 0 | 1 | 0 | 1 | missing | 0 | 0.0% | 0 | true | accepted_no_op | N/A | not_applicable_bootstrap_logs_unavailable | scripts/docs_retrieve_metrics.py --format json |
            | planveyor | read_only_target | missing | 0 | 0 | 0 | 0.0% | 0 | 0 | 0 | 0 | 100.0% | 0 | 0 | 0 | 0 | 0 | missing | 0 | 100.0% | 0 | false | not_required | N/A | not_used_for_decision | scripts/docs_retrieve_metrics.py --format json |
            """
        )
    )


def _render_post_merge_audit() -> str:
    return _with_final_newline(
        dedent(
            f"""\
            # Review: Post-merge audit — example topic

            **Date:** 29.03.2026 18:10 +0000
            **Topic:** example
            **Status:** Draft
            **Schema version:** {CURRENT_REVIEW_SCHEMA_VERSION}

            ## Audit matrix (summary)
            ### A1) Example item
            - Lane synthesis source: `UNCONFIRMED`
            - source_lane: `UNCONFIRMED`
            - lane_finding_id: `UNCONFIRMED`
            - synthesis_disposition: `N/A`
            - canonical_ref: `N/A`
            - audit_status: `UNCONFIRMED`
            - followup_plan: `N/A`
            - Blocker refs: `UNCONFIRMED`
            - Code anchors: `scripts/post_merge_audit_lint.py:1`
            - Tests/smokes: `python -B scripts/test_post_merge_audit_lint.py`
            - Docs: `docs/reviews/_template_post_merge_audit.md`
            - Status: `unknown`

            ## Post-merge audit receipt citations
            - Audit matrix: `docs/reviews/260329_1810_post_merge_audit_example.md#audit-matrix-summary`.
            - Role-quality: `Role assessment (censor receipts, if applicable)`.
            - Follow-up harvest triage/import receipt: `docs/reviews/260329_1809_plan_harvest_range_deadbee_feed123.md#follow-up-harvest-triageimport-receipt`.
            - Process-improvement promotion decisions: `docs/reviews/260329_1809_plan_harvest_range_deadbee_feed123.md#process-improvement-promotion-decisions`.
            - Docs retrieval metrics receipt: `docs/reviews/260329_1809_plan_harvest_range_deadbee_feed123.md#docs-retrieval-metrics-receipt`.
            - Docs index/context: `docs_index_context`; `planveyor_docs_index_build all`; `docs_context_check corpus=plans covered=2 uncovered=0`; `docs_context_check corpus=followups covered=1 uncovered=0`.
            - Packetization: `step:packetization_gate` -> `N/A (why=no shared canon delta in fixture)`.
            - SATD/candidate rows: `N/A (why=no SATD candidate in fixture)`.

            ## Follow-ups
            - Если source plan literal-но вынес item из active scope, audit фиксирует `lost follow-up during harvest/promotion`, а не молчит.

            ## Role assessment (censor receipts, if applicable)
            - Receipt source: `N/A (receipt missing)`
            - Assessment: `receipt missing`
            """
        )
    )


def _operational_payload() -> dict[str, object]:
    return {
        "schema_version": OPERATIONAL_SCHEMA_VERSION,
        "range": "<BASE>..<HEAD>",
        "base": "<BASE>",
        "head": "<HEAD>",
        "tracker_path": ".planveyor.merge_tracker.md",
        "generated_at": "1970-01-01T00:00:00+00:00",
        "generated_by": "scripts/post_merge_receipt_skeleton.py",
        "receipt_path": "docs/reviews/<stamp>_post_merge_operational_receipt_range_<base7>_<head7>.md",
        "archive_snapshot": {
            "status": "pending_skeleton_fill",
            "storage_backend": "N/A",
            "manifest_path": "N/A",
            "artifact_path": "N/A",
            "object_uri": "N/A",
            "checksum": "N/A",
            "export_command": "N/A",
            "export_status": "pending_skeleton_fill",
            "snapshot_created_at_utc": "N/A",
            "snapshot_source_db_sha256": "N/A",
            "snapshot_source_docs_count": 0,
            "restore_status": "pending_skeleton_fill",
            "readback_status": "pending_skeleton_fill",
        },
        "docs_hygiene_suggest_summary": {
            "range": "<BASE>..<HEAD>",
            "command": "planveyor_post_merge_docs_hygiene_suggest_gate",
            "suggest_result": "pending_skeleton_fill",
            "source_stdout_path": "N/A",
            "source_stderr_path": "N/A",
            "report_only": True,
            "deletion_executed": False,
            "ready_to_push_ticked_by_suggest_gate": False,
            "archive_required_command": "N/A",
            "suggested_owner_rerun_command": "N/A",
            "candidate_counts": {},
            "omitted_count": 0,
            "top_candidates": [],
        },
        "followups_triage_launch_receipt": {
            "source_harvest_receipt_path": "docs/reviews/<stamp>_plan_harvest_range_<base7>_<head7>.md",
            "triage_mode": "range",
            "command": "planveyor_followups_triage --range <BASE>..<HEAD> --apply",
            "dry_run": {"append_new": 0, "merge_source": 0, "possible_duplicate": 0, "route_fallback": 0, "unparsed_bullets": 0},
            "apply": {"append_new": 0, "merge_source": 0, "possible_duplicate": 0, "route_fallback": 0, "unparsed_bullets": 0},
            "idempotency_apply": {
                "append_new": 0,
                "merge_source": 0,
                "possible_duplicate": 0,
                "route_fallback": 0,
                "unparsed_bullets": 0,
            },
            "index_rebuild": {"status": "pending_skeleton_fill", "readback_status": "pending_skeleton_fill"},
            "process_improvements_lane": {"lane_status": "separate", "open": 0, "triaged": 0, "promoted": 0},
        },
        "process_improvements_open_summary": {
            "source_harvest_receipt_path": "docs/reviews/<stamp>_plan_harvest_range_<base7>_<head7>.md",
            "decision_receipt_path": "docs/reviews/<stamp>_plan_harvest_range_<base7>_<head7>.md#process-improvement-promotion-decisions",
            "ordinary_followups_result": "NO FOLLOWUPS",
            "lane_status": "separate",
            "counts_by_raw_status": {"open": 0, "triaged": 0, "promoted": 0},
            "null_execution_rows": 0,
            "owner_or_next_step": "N/A (why=skeleton)",
        },
        "steps": [
            {
                "step": "docs_hygiene_suggest",
                "command": "planveyor_post_merge_docs_hygiene_suggest_gate",
                "status": "pending_skeleton_fill",
                "receipt_ref": "N/A",
            },
            {
                "step": "followups_triage_launch",
                "command": "planveyor_followups_triage --range <BASE>..<HEAD> --apply",
                "status": "pending_skeleton_fill",
                "receipt_ref": "N/A",
            },
            {
                "step": "archive_snapshot",
                "command": "archive snapshot export/readback command",
                "status": "pending_skeleton_fill",
                "receipt_ref": "N/A",
            },
        ],
    }


def _render_post_merge_operational_receipt() -> str:
    payload = _operational_payload()
    archive_snapshot = payload["archive_snapshot"]
    docs_hygiene = payload["docs_hygiene_suggest_summary"]
    followups = payload["followups_triage_launch_receipt"]
    pi_summary = payload["process_improvements_open_summary"]
    assert isinstance(archive_snapshot, dict)
    assert isinstance(docs_hygiene, dict)
    assert isinstance(followups, dict)
    assert isinstance(pi_summary, dict)

    return _with_final_newline(
        "\n".join(
            [
                "# Post-merge operational receipt skeleton",
                "",
                "**Status:** Draft",
                "",
                "## Operational receipt summary",
                f"- schema_version: {payload['schema_version']}",
                f"- range: {payload['range']}",
                f"- base: {payload['base']}",
                f"- head: {payload['head']}",
                f"- tracker_path: {payload['tracker_path']}",
                f"- archive_snapshot_status: {archive_snapshot['status']}",
                f"- archive_snapshot_backend: {archive_snapshot['storage_backend']}",
                f"- archive_snapshot_manifest: {archive_snapshot['manifest_path']}",
                f"- archive_snapshot_artifact: {archive_snapshot['artifact_path']}",
                f"- archive_snapshot_checksum: {archive_snapshot['checksum']}",
                f"- archive_snapshot_restore_status: {archive_snapshot['restore_status']}",
                f"- archive_snapshot_readback_status: {archive_snapshot['readback_status']}",
                f"- docs_hygiene_suggest_report_only: {docs_hygiene['report_only']}",
                f"- docs_hygiene_suggest_deletion_executed: {docs_hygiene['deletion_executed']}",
                f"- docs_hygiene_suggest_omitted_count: {docs_hygiene['omitted_count']}",
                f"- followups_triage_launch_mode: {followups['triage_mode']}",
                f"- followups_triage_launch_source: {followups['source_harvest_receipt_path']}",
                f"- followups_triage_launch_index_readback: {followups['index_rebuild']['readback_status']}",
                f"- process_improvements_open_summary_lane: {pi_summary['lane_status']}",
                f"- process_improvements_open_summary_counts: {json.dumps(pi_summary['counts_by_raw_status'], sort_keys=True)}",
                f"- process_improvements_open_summary_null_execution_rows: {pi_summary['null_execution_rows']}",
                f"- generated_at: {payload['generated_at']}",
                "",
                "## Docs hygiene suggest summary",
                f"- range: {docs_hygiene['range']}",
                f"- command: {docs_hygiene['command']}",
                f"- suggest_result: {docs_hygiene['suggest_result']}",
                f"- source_stdout_path: {docs_hygiene['source_stdout_path']}",
                f"- source_stderr_path: {docs_hygiene['source_stderr_path']}",
                f"- report_only: {docs_hygiene['report_only']}",
                f"- deletion_executed: {docs_hygiene['deletion_executed']}",
                f"- candidate_counts: {json.dumps(docs_hygiene['candidate_counts'], sort_keys=True)}",
                f"- omitted_count: {docs_hygiene['omitted_count']}",
                "",
                "## Followups triage launch receipt",
                f"- source_harvest_receipt_path: {followups['source_harvest_receipt_path']}",
                f"- triage_mode: {followups['triage_mode']}",
                f"- command: {followups['command']}",
                f"- dry_run: {json.dumps(followups['dry_run'], sort_keys=True)}",
                f"- apply: {json.dumps(followups['apply'], sort_keys=True)}",
                f"- idempotency_apply: {json.dumps(followups['idempotency_apply'], sort_keys=True)}",
                f"- index_rebuild: {json.dumps(followups['index_rebuild'], sort_keys=True)}",
                f"- process_improvements_lane: {json.dumps(followups['process_improvements_lane'], sort_keys=True)}",
                "",
                "## Process improvements open summary",
                f"- source_harvest_receipt_path: {pi_summary['source_harvest_receipt_path']}",
                f"- decision_receipt_path: {pi_summary['decision_receipt_path']}",
                f"- ordinary_followups_result: {pi_summary['ordinary_followups_result']}",
                f"- lane_status: {pi_summary['lane_status']}",
                f"- counts_by_raw_status: {json.dumps(pi_summary['counts_by_raw_status'], sort_keys=True)}",
                f"- null_execution_rows: {pi_summary['null_execution_rows']}",
                f"- owner_or_next_step: {pi_summary['owner_or_next_step']}",
                "",
                "## Operational receipt JSON",
                "```json",
                json.dumps(payload, indent=2, sort_keys=True),
                "```",
            ]
        )
    )


RENDERERS: dict[str, Callable[[], str]] = {
    "canon_sweep_receipt": _render_canon_sweep_receipt,
    "docs_finalize_receipt": _render_docs_finalize_receipt,
    "plan_harvest": _render_plan_harvest,
    "post_merge_audit": _render_post_merge_audit,
    "post_merge_operational_receipt": _render_post_merge_operational_receipt,
}


def render_skeleton(family: str) -> str:
    try:
        renderer = RENDERERS[family]
    except KeyError as exc:
        raise ValueError(f"unsupported receipt skeleton family: {family}") from exc
    return renderer()


def _receipt_context(
    context: ContractContext | None = None,
) -> ContractContext:
    """Capture the one context used by a receipt-emission invocation."""

    if context is None:
        return authority_context.resolve_top_level_context()
    return authority_context.context_for_reader(context.project_root, context)


def _reject_engaged_private_delivery(
    family: str,
    context: ContractContext,
) -> None:
    if context.state == "engaged" and family != "docs_finalize_receipt":
        raise authority_context.ContractAuthorityError(
            "engaged_private_delivery_unsupported",
            f"receipt skeleton family is unavailable in engaged authority: {family}",
        )


def _output_path_for_context(
    raw_path: str,
    context: ContractContext,
) -> Path:
    """Return a canonical engaged output path bound beneath its project root."""

    output_path = Path(raw_path)
    if context.state != "engaged":
        return output_path
    resolved_output = output_path.expanduser().resolve(strict=False)
    project_root = context.project_root.resolve(strict=False)
    try:
        resolved_output.relative_to(project_root)
    except ValueError as exc:
        raise authority_context.ContractAuthorityError(
            "context_output_root_mismatch",
            "engaged receipt output must be below the context project root",
        ) from exc
    return resolved_output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=f"Plan ref: {PLAN_REF}",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("family", choices=SUPPORTED_FAMILIES, help="Skeleton family to render.")
    parser.add_argument("--out", help="Optional output path for the generated skeleton.")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    context: ContractContext | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    writer_context = _receipt_context(context)
    _reject_engaged_private_delivery(args.family, writer_context)
    text = render_skeleton(args.family)

    if args.out:
        out_path = _output_path_for_context(args.out, writer_context)
        # ``_receipt_context`` has just captured or revalidated this context;
        # no contract read or effect occurs before this initial mkdir.
        out_path.parent.mkdir(parents=True, exist_ok=True)
        authority_context.validate_before_effect(writer_context)
        out_path.write_text(text, encoding="utf-8")

    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

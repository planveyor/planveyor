#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path
from textwrap import dedent
from unittest import mock


MODULE_PATH = Path(__file__).with_name("plan_harvest_lint.py")
SPEC = importlib.util.spec_from_file_location("plan_harvest_lint", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

import review_schema_contract
from test_support.process_contract_fixtures import temporary_git_root


class PlanHarvestLintTests(unittest.TestCase):
    def _write_markdown(self, root: Path, rel_path: str, body: str) -> Path:
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        return target

    def _load_paths(self, root: Path, *rel_paths: str):
        return MODULE.load_harvest_artifacts(root, list(rel_paths))

    def test_review_schema_version_uses_shared_contract(self) -> None:
        self.assertEqual(MODULE.CURRENT_REVIEW_SCHEMA_VERSION, review_schema_contract.CURRENT_REVIEW_SCHEMA_VERSION)
        self.assertEqual(MODULE.CURRENT_REVIEW_SCHEMA_VERSION, "review.v1")

    def _green_backlog(self) -> str:
        return dedent(
            """\
            # Follow-ups backlog — Architect range harvest

            **Date:** 2026-03-29 18:20 MSK
            **Source:** Architect plan harvest
            **Status:** closed

            ## Range result
            - `NO FOLLOWUPS` — reason: no remaining actionable debt after full-wave harvest.
            """
        )

    def _green_report(self, backlog_path: str) -> str:
        return dedent(
            f"""\
            # Review: Plan harvest — range deadbee..feed123

            **Date:** 29.03.2026 18:20 MSK
            **BASE:** deadbee
            **HEAD:** feed123
            **Status:** ✅ Done

            ## Follow-ups backlog (created)
            - `{backlog_path}`

            ## Follow-ups (extracted; без дублей)
            - Result: `NO FOLLOWUPS` — no remaining actionable debt after full-wave harvest.
            """
        )

    def _green_retrieval_metrics_receipt(self) -> str:
        return dedent(
            """\

            ## Docs retrieval metrics receipt

            | repo | repo_role | query_log_status | query_total | with_hits | zero_hits | hit_rate | warnings_total | errors_total | with_event_id | evaluated_total | outcome_evaluated_rate | outcome_used | outcome_partial | outcome_miss | outcome_noise | not_evaluated_total | read_log_status | read_events_total | read_open_rate | unique_paths | used_for_decision | low_coverage_triage | follow_up_ref | accepted_no_op_reason | source_command |
            | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | --- | --- | --- | --- | --- |
            | planveyor | source | present | 3 | 2 | 1 | 66.7% | 1 | 0 | 3 | 2 | 66.7% | 1 | 0 | 1 | 0 | 1 | missing | 0 | 0.0% | 0 | true | accepted_no_op | N/A | not_applicable_bootstrap_logs_unavailable | scripts/docs_retrieve_metrics.py --format json |
            | planveyor | read_only_target | missing | 0 | 0 | 0 | 0.0% | 0 | 0 | 0 | 0 | 100.0% | 0 | 0 | 0 | 0 | 0 | missing | 0 | 100.0% | 0 | false | not_required | N/A | not_used_for_decision | scripts/docs_retrieve_metrics.py --format json |
            """
        )

    def _current_receipt_sections(self) -> str:
        return (
            dedent(
                """\

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
                """
            )
            + self._green_retrieval_metrics_receipt()
        )

    def _current_file_followups_source(
        self,
        *,
        result: str = "NO FOLLOWUPS",
        count: str = "0",
        result_suffix: str = " — no remaining actionable debt after full-wave harvest.",
        idempotency_line: str = "- triage (idempotency): append_new=0, possible_duplicate=0, route_fallback=0, unparsed_bullets=0.",
        closure_line: str = "",
    ) -> str:
        return dedent(
            f"""\
            # Plan harvest

            **Date:** 01.01.2020 00:00 MSK
            **Schema version:** review.v1

            ## Follow-up harvest triage/import receipt
            - harvest_file_followups_result: `{result}`{result_suffix}
            - harvest_file_followups_count: {count}
            {idempotency_line}
            {closure_line}
            """
        )

    def _current_receipt_sections_with_pi_open_summary(self, *, include_summary: bool = True) -> str:
        summary_line = (
            "- process_improvements_open_summary: source=docs/process_improvements/promotion_surface.md; "
            "lane=separate; ordinary_followups=NO FOLLOWUPS; open=2; triaged=0; promoted=0; "
            "null_execution=2; owner_or_next_step=Planner triage in process-improvement promotion lane\n"
            if include_summary
            else ""
        )
        return self._current_receipt_sections().replace(
            "## Process-improvement promotion decisions\n"
            "- `N/A (why=no mature process-improvement rows in fixture)`.",
            "## Process-improvement promotion decisions\n"
            f"{summary_line}"
            "| source_ref | entry_id | raw_status | execution_kind | execution_ref | owner_or_next_step |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            "| `docs/process_improvements/promotion_surface.md` | `PI-001` | `open` | `null` | `null` | `Planner triage in process-improvement promotion lane` |\n"
            "| `docs/process_improvements/promotion_surface.md` | `PI-002` | `open` | `null` | `null` | `Planner triage in process-improvement promotion lane` |",
        )

    def _current_receipt_sections_with_bullet_pi_rows(
        self,
        *,
        include_summary: bool = True,
        open_count: int = 2,
        null_execution_count: int = 2,
    ) -> str:
        summary_line = (
            "- process_improvements_open_summary: source=docs/process_improvements/promotion_surface.md; "
            f"lane=separate; ordinary_followups=NO FOLLOWUPS; open={open_count}; triaged=0; promoted=0; "
            f"null_execution={null_execution_count}; owner_or_next_step=Planner triage in process-improvement promotion lane\n"
            if include_summary
            else ""
        )
        return self._current_receipt_sections().replace(
            "## Process-improvement promotion decisions\n"
            "- `N/A (why=no mature process-improvement rows in fixture)`.",
            "## Process-improvement promotion decisions\n"
            f"{summary_line}"
            "- Detected open raw rows, but this harvest keeps them in the PI lane:\n"
            "  - source_ref=`docs/plans/260517_1310_process_pending_followups_decision_wave.md`; "
            "entry_id=`PI-001`; raw_status=`open`; execution_kind=`null`; execution_ref=`null`; "
            "owner_or_next_step=`Planner triage in process-improvement promotion lane`.\n"
            "  - source_ref=`docs/plans/260521_2102_process_memory_finalize_umbrella_child_graph_repair.md`; "
            "entry_id=`PI-001`; raw_status=`open`; reason=`execution_kind and execution_ref are null`; "
            "owner_or_next_step=`Planner triage in process-improvement promotion lane`.",
        )

    def _current_report_with_receipts(self, backlog_path: str, receipt_sections: str) -> str:
        return (
            self._green_report(backlog_path).replace(
                "**Status:** ✅ Done\n",
                "**Status:** ✅ Done\n**Schema version:** review.v1\n",
            )
            + receipt_sections
        )

    def test_public_file_followups_parser_classifies_current_legacy_and_unsupported(self) -> None:
        current = MODULE.parse_plan_harvest_file_followups_receipt(
            self._current_file_followups_source(result="created/imported", count="2", result_suffix=""),
            rel_path="docs/reviews/200101_0000_plan_harvest_range_deadbee_feed123.md",
        )
        legacy = MODULE.parse_plan_harvest_file_followups_receipt(
            "# Historical plan harvest\n\n## Follow-up harvest triage/import receipt\n- Result: `NO FOLLOWUPS`\n",
            rel_path="docs/reviews/200101_0000_plan_harvest_range_deadbee_feed123.md",
        )
        unsupported = MODULE.parse_plan_harvest_file_followups_receipt(
            self._current_file_followups_source().replace("review.v1", "review.v0"),
            rel_path="docs/reviews/260829_1500_plan_harvest_range_deadbee_feed123.md",
        )
        template = MODULE.parse_plan_harvest_file_followups_receipt(
            "# Template\n\n## Follow-up harvest triage/import receipt\n",
            rel_path="docs/reviews/_template_plan_harvest.md",
        )

        self.assertEqual((current.schema_class, current.result, current.count, current.findings), ("current", "created/imported", 2, ()))
        self.assertEqual((legacy.schema_class, legacy.result, legacy.count, legacy.findings), ("legacy", None, None, ()))
        self.assertEqual(unsupported.schema_class, "unsupported")
        self.assertIn("unsupported_schema_version", {finding.code for finding in unsupported.findings})
        self.assertEqual(template.schema_class, "unsupported")
        self.assertIn("missing_schema_version", {finding.code for finding in template.findings})

    def test_public_file_followups_parser_rejects_invalid_current_literals(self) -> None:
        cases = (
            (
                self._current_file_followups_source().replace(
                    "- harvest_file_followups_result: `NO FOLLOWUPS` — no remaining actionable debt after full-wave harvest.\n",
                    "",
                ),
                "missing_harvest_file_followups_result",
            ),
            (self._current_file_followups_source(result="TBD", result_suffix=""), "invalid_harvest_file_followups_result"),
            (self._current_file_followups_source(count="<count>"), "invalid_harvest_file_followups_count"),
            (self._current_file_followups_source(count="-1"), "invalid_harvest_file_followups_count"),
            (
                self._current_file_followups_source().replace(
                    "- harvest_file_followups_count: 0\n",
                    "- harvest_file_followups_count: 0\n- harvest_file_followups_count: 0\n",
                ),
                "duplicate_harvest_file_followups_count",
            ),
            (self._current_file_followups_source(count="1"), "invalid_harvest_file_followups_result_count"),
            (
                self._current_file_followups_source(result="created/imported", count="0", result_suffix=""),
                "invalid_harvest_file_followups_result_count",
            ),
            (
                self._current_file_followups_source(result_suffix=""),
                "invalid_harvest_file_followups_no_op_reason",
            ),
            (
                self._current_file_followups_source(
                    result_suffix=" — handled in follow-up; already tracked elsewhere.",
                ),
                "invalid_harvest_file_followups_no_op_reason",
            ),
        )

        for source, expected_code in cases:
            with self.subTest(expected_code=expected_code):
                parsed = MODULE.parse_plan_harvest_file_followups_receipt(
                    source,
                    rel_path="docs/reviews/260829_1501_plan_harvest_range_deadbee_feed123.md",
                )
                self.assertIn(expected_code, {finding.code for finding in parsed.findings})

    def test_public_file_followups_parser_requires_complete_idempotency_counter_set(self) -> None:
        fields = MODULE.HARVEST_FILE_FOLLOWUPS_UNRESOLVED_FIELDS
        for field in fields:
            remaining = [name for name in fields if name != field]
            omitted = ", ".join(f"{name}=0" for name in remaining) + "."
            duplicate = ", ".join(f"{name}=0" for name in fields) + f", {field}=0."
            malformed = ", ".join(
                f"{name}={'1.5' if name == field else '0'}" for name in fields
            ) + "."
            cases = (
                (omitted, "missing_harvest_file_followups_idempotency_counter"),
                (duplicate, "duplicate_harvest_file_followups_idempotency_counter"),
                (malformed, "invalid_harvest_file_followups_idempotency_counter"),
            )
            for counters, expected_code in cases:
                with self.subTest(field=field, expected_code=expected_code):
                    parsed = MODULE.parse_plan_harvest_file_followups_receipt(
                        self._current_file_followups_source(
                            idempotency_line=f"- triage (idempotency): {counters}",
                            closure_line="- manual_decision_ref=docs/plans/260829_1503_process_followups.md#closure",
                        ),
                        rel_path="docs/reviews/260829_1503_plan_harvest_range_deadbee_feed123.md",
                    )
                    matching = [finding for finding in parsed.findings if finding.code == expected_code]
                    self.assertTrue(matching, parsed.findings)
                    self.assertTrue(any(f"`{field}`" in finding.message for finding in matching), matching)

    def test_public_file_followups_parser_rejects_duplicate_table_counter_header(self) -> None:
        parsed = MODULE.parse_plan_harvest_file_followups_receipt(
            self._current_file_followups_source(
                idempotency_line=dedent(
                    """\
                    | command | mode | append_new | possible_duplicate | route_fallback | unparsed_bullets | unparsed_bullets |
                    | --- | --- | ---: | ---: | ---: | ---: | ---: |
                    | triage | idempotency | 0 | 0 | 0 | 0 | 0 |
                    """
                ),
            ),
            rel_path="docs/reviews/260829_1504_plan_harvest_range_deadbee_feed123.md",
        )

        matching = [
            finding
            for finding in parsed.findings
            if finding.code == "duplicate_harvest_file_followups_idempotency_counter"
        ]
        self.assertTrue(matching, parsed.findings)
        self.assertTrue(any("`unparsed_bullets`" in finding.message for finding in matching), matching)

    def test_public_file_followups_parser_requires_durable_closure_for_unresolved_idempotency(self) -> None:
        unresolved = self._current_file_followups_source(
            idempotency_line="- triage (idempotency): append_new=0, possible_duplicate=1, route_fallback=0, unparsed_bullets=1."
        )
        closed = self._current_file_followups_source(
            idempotency_line="- triage (idempotency): append_new=0, possible_duplicate=1, route_fallback=0, unparsed_bullets=1.",
            closure_line="- manual_decision_ref=docs/plans/260829_1502_process_followups.md#closure",
        )
        malformed = self._current_file_followups_source(
            closure_line="- already_tracked_ref=handled",
        )

        unresolved_parsed = MODULE.parse_plan_harvest_file_followups_receipt(
            unresolved,
            rel_path="docs/reviews/260829_1502_plan_harvest_range_deadbee_feed123.md",
        )
        closed_parsed = MODULE.parse_plan_harvest_file_followups_receipt(
            closed,
            rel_path="docs/reviews/260829_1502_plan_harvest_range_deadbee_feed123.md",
        )
        malformed_parsed = MODULE.parse_plan_harvest_file_followups_receipt(
            malformed,
            rel_path="docs/reviews/260829_1502_plan_harvest_range_deadbee_feed123.md",
        )

        self.assertIn("unresolved_harvest_file_followups", {finding.code for finding in unresolved_parsed.findings})
        self.assertEqual(closed_parsed.findings, ())
        self.assertIn("invalid_harvest_file_followups_closure_ref", {finding.code for finding in malformed_parsed.findings})

    def test_canonical_plan_harvest_template_is_current_parser_valid(self) -> None:
        root = Path(__file__).resolve().parents[1]
        rel_path = "docs/reviews/_template_plan_harvest.md"
        findings = MODULE.lint_harvest_artifacts(MODULE.load_harvest_artifacts(root, [rel_path]))

        self.assertEqual(findings, [])

    def _post_merge_audit(self, body: str) -> str:
        return dedent(
            f"""\
            # Review: Post-merge audit - range deadbee..feed123

            **Date:** 2026-05-10 15:24 MSK
            **Status:** ✅ Done
            **Schema version:** review.v1

            {body}
            """
        )

    def _process_improvement_backlog(
        self,
        *,
        source_ref: str = "docs/plans/260510_1200_process_pi_source.md",
        status: str = "triaged",
        execution_kind: str = "plan",
        execution_ref: str = "docs/plans/execution.md",
        delivery_refs: str = "null",
        triage_note: str = "fixture",
    ) -> str:
        promoted_at = "2026-05-10 22:29 MSK" if status in {"promoted", "handled"} else "null"
        handled_ref = execution_ref if status == "handled" else "null"
        handled_at = "2026-05-10 22:30 MSK" if status == "handled" else "null"
        target_canon_path = "docs/tools/owner_runbook_codex.md" if status in {"triaged", "promoted", "handled"} else "null"
        target_repo_scope = "planveyor" if status in {"triaged", "promoted", "handled"} else "null"
        delivery_mode = "source_only" if status in {"triaged", "promoted", "handled"} else "null"
        return dedent(
            f"""\
            # Process improvements backlog - fixture

            **Source ref:** `{source_ref}`
            **Status:** Draft

            ## Suggestions (truth)
            ### PI-001
            - status: `{status}`
            - priority: `P1`
            - role: `Architect`
            - owner: `Architect`
            - promotion_class: `helper_change`
            - target_canon_path: `{target_canon_path}`
            - target_repo_scope: `{target_repo_scope}`
            - delivery_mode: `{delivery_mode}`
            - execution_kind: `{execution_kind}`
            - execution_ref: `{execution_ref}`
            - delivery_refs: `{delivery_refs}`
            - handled_ref: `{handled_ref}`
            - promoted_at: `{promoted_at}`
            - handled_at: `{handled_at}`
            - trigger_ref: `docs/code_reviews/example.md#B1`
            - source_ref: `{source_ref}`
            - symptom: `harvest prose drift`
            - process_gap: `terminal decision not checked against raw state`
            - suggested_fix: `lint process improvement decision state`
            - created_at: `2026-05-10 20:06 MSK`
            - triage_note: `{triage_note}`
            """
        )

    def _report_with_process_decision(
        self,
        *,
        backlog_path: str,
        source_slug: str = "pi_source",
        decision: str = "promoted",
        execution_kind: str = "plan",
        execution_ref: str = "docs/plans/execution.md",
        owner_or_next_step: str = "N/A",
    ) -> str:
        return (
            self._green_report(backlog_path)
            + dedent(
                f"""\

                ## Process-improvement promotion decisions

                - `PI-001 @ {source_slug}` | `{decision}` | fixture reason | `{execution_kind}` | `{execution_ref}` | `{owner_or_next_step}`
                """
            )
        )

    def _report_with_process_decision_source_ref_cell(
        self,
        *,
        backlog_path: str,
        source_ref: str = "docs/plans/260510_1200_process_pi_source.md",
        decision: str = "handled",
        execution_kind: str = "plan",
        execution_ref: str = "docs/plans/execution.md",
    ) -> str:
        return (
            self._green_report(backlog_path)
            + dedent(
                f"""\

                ## Process-improvement promotion decisions

                | source_ref | entry_id | decision | reason | execution_kind | execution_ref | owner_or_next_step |
                | --- | --- | --- | --- | --- | --- | --- |
                | `{source_ref}` | `PI-001` | `{decision}` | fixture reason | `{execution_kind}` | `{execution_ref}` | `N/A` |
                """
            )
        )

    def test_green_report_and_backlog_pass(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            backlog_path = "docs/followups/260329_1820_followups_range_deadbee_feed123.md"
            report_path = "docs/reviews/260329_1820_plan_harvest_range_deadbee_feed123.md"
            self._write_markdown(root, backlog_path, self._green_backlog())
            self._write_markdown(root, report_path, self._green_report(backlog_path))

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, report_path, backlog_path))

        self.assertEqual(findings, [])

    def test_missing_backlog_ref_is_reported_for_no_followups_report(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            report_path = "docs/reviews/260329_1821_plan_harvest_missing_backlog.md"
            self._write_markdown(
                root,
                report_path,
                dedent(
                    """\
                    # Review: Plan harvest — range deadbee..feed123

                    **Date:** 29.03.2026 18:21 MSK
                    **BASE:** deadbee
                    **HEAD:** feed123
                    **Status:** ✅ Done

                    ## Follow-ups backlog (created)
                    - `N/A`

                    ## Follow-ups (extracted; без дублей)
                    - Result: `NO FOLLOWUPS` — no remaining actionable debt after full-wave harvest.
                    """
                ),
            )

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, report_path))

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "missing_backlog_ref")

    def test_invalid_backlog_no_followups_reason_is_reported(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            backlog_path = "docs/followups/260329_1822_followups_range_deadbee_feed123.md"
            report_path = "docs/reviews/260329_1822_plan_harvest_range_deadbee_feed123.md"
            self._write_markdown(
                root,
                backlog_path,
                self._green_backlog().replace(
                    "no remaining actionable debt after full-wave harvest",
                    "we looked at one thing",
                ),
            )
            self._write_markdown(root, report_path, self._green_report(backlog_path))

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, report_path, backlog_path))

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "invalid_no_followups_reason")
        self.assertEqual(findings[0].rel_path, backlog_path)

    def test_followups_lint_failure_is_surface_for_backlog_rows(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            backlog_path = "docs/followups/260329_1823_followups_range_deadbee_feed123.md"
            report_path = "docs/reviews/260329_1823_plan_harvest_range_deadbee_feed123.md"
            self._write_markdown(
                root,
                backlog_path,
                dedent(
                    """\
                    # Follow-ups backlog — Architect range harvest

                    **Date:** 2026-03-29 18:23 MSK
                    **Source:** Architect plan harvest
                    **Status:** draft

                    ## Follow-ups (backlog)
                    - P2 Broken row without checkbox marker — cluster=process — tags=fixtures — to=Coder — status=open — plan=null — why: malformed proof
                    """
                ),
            )
            self._write_markdown(root, report_path, self._green_report(backlog_path))

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, report_path, backlog_path))

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "followups_lint_malformed_followup_row")
        self.assertIn("Malformed follow-up row", findings[0].message)

    def test_derived_index_receipt_requires_derived_index_summary(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            backlog_path = "docs/followups/260329_1824_followups_range_deadbee_feed123.md"
            report_path = "docs/reviews/260329_1824_plan_harvest_range_deadbee_feed123.md"
            self._write_markdown(root, backlog_path, self._green_backlog())
            self._write_markdown(
                root,
                report_path,
                self._green_report(backlog_path)
                + dedent(
                    """\

                    ## Notes
                    - Derived-index note: blocker-free closeout refreshed `planveyor_docs_index_build all`.
                    """
                ),
            )

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, report_path, backlog_path))

        self.assertEqual(len(findings), 3)
        self.assertTrue(all(finding.code == "missing_derived_index_receipt" for finding in findings))
        self.assertTrue(any("docs_context_check" in finding.message for finding in findings))
        self.assertTrue(any("plans" in finding.message for finding in findings))
        self.assertTrue(any("followups" in finding.message for finding in findings))

    def test_current_260510_docs_retrieve_gap_requires_retrieval_metrics_receipt(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            backlog_path = "docs/followups/260510_followups_range.md"
            report_path = "docs/reviews/260510_plan_harvest_range.md"
            self._write_markdown(root, backlog_path, self._green_backlog())
            self._write_markdown(
                root,
                report_path,
                self._green_report(backlog_path)
                + dedent(
                    """\

                    ## Sources
                    - `260504_2225_process_docs_retrieve_observability_metrics_wave2.md`
                    """
                ),
            )

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, report_path, backlog_path))

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "missing_retrieval_metrics_receipt")
        self.assertIn("Docs retrieval metrics receipt", findings[0].message)

    def test_retrieval_metrics_receipt_accepts_missing_read_log_zero_count(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            backlog_path = "docs/followups/260510_followups_range.md"
            report_path = "docs/reviews/260510_plan_harvest_range.md"
            self._write_markdown(root, backlog_path, self._green_backlog())
            self._write_markdown(
                root,
                report_path,
                self._green_report(backlog_path)
                + dedent(
                    """\

                    ## Sources
                    - `scripts/docs_retrieve_metrics.py`
                    """
                )
                + self._green_retrieval_metrics_receipt(),
            )

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, report_path, backlog_path))

        self.assertEqual(findings, [])

    def test_lookup_backed_harvest_requires_retrieval_telemetry_receipt(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            backlog_path = "docs/followups/260510_lookup_followups_range.md"
            report_path = "docs/reviews/260510_lookup_plan_harvest_range.md"
            self._write_markdown(root, backlog_path, self._green_backlog())
            self._write_markdown(
                root,
                report_path,
                self._green_report(backlog_path)
                + "\n## Lookup evidence\n- Used `planveyor_docs_lookup plans \"retrieval receipt\"` for source selection.\n",
            )

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, report_path, backlog_path))

        self.assertIn("missing_retrieval_telemetry_receipt", {finding.code for finding in findings})

    def test_retrieve_backed_source_selection_requires_retrieval_telemetry_receipt(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            backlog_path = "docs/followups/260510_retrieve_followups_range.md"
            report_path = "docs/reviews/260510_retrieve_plan_harvest_range.md"
            self._write_markdown(root, backlog_path, self._green_backlog())
            self._write_markdown(
                root,
                report_path,
                self._green_report(backlog_path)
                + "\n## Lookup evidence\n- Used `planveyor_docs_retrieve plans \"retrieval receipt\"` for source selection.\n",
            )

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, report_path, backlog_path))

        self.assertIn("missing_retrieval_telemetry_receipt", {finding.code for finding in findings})

    def test_lookup_backed_harvest_accepts_retrieval_telemetry_receipt(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            backlog_path = "docs/followups/260510_lookup_followups_range.md"
            report_path = "docs/reviews/260510_lookup_plan_harvest_range.md"
            self._write_markdown(root, backlog_path, self._green_backlog())
            self._write_markdown(
                root,
                report_path,
                self._green_report(backlog_path)
                + dedent(
                    """\

                    ## Lookup evidence
                    - Used `planveyor_docs_lookup plans "retrieval receipt"` for source selection.

                    ## Retrieval telemetry receipt
                    - query_event_id: `20260511T120000Z-abcd123456-12345678`
                    - used_for_decision: `true`
                    - read_open: `ok`
                    - read_log_status: `present`
                    - read_event_id: `read-20260511T120001Z-12345678`
                    - outcome: `used`
                    - outcome_reason: used for harvest source selection.
                    - cited/opened files: `docs/tools/snippet.md`
                    """
                ),
            )

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, report_path, backlog_path))

        self.assertNotIn("missing_retrieval_telemetry_receipt", {finding.code for finding in findings})
        self.assertNotIn("invalid_retrieval_telemetry_receipt", {finding.code for finding in findings})

    def test_retrieval_metrics_receipt_requires_missing_read_log_zero_count(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            backlog_path = "docs/followups/260510_followups_range.md"
            report_path = "docs/reviews/260510_plan_harvest_range.md"
            bad_receipt = self._green_retrieval_metrics_receipt().replace(
                "| missing | 0 | 0.0% | 0 | true | accepted_no_op |",
                "| missing | 1 | 0.0% | 0 | true | accepted_no_op |",
                1,
            )
            self._write_markdown(root, backlog_path, self._green_backlog())
            self._write_markdown(
                root,
                report_path,
                self._green_report(backlog_path)
                + dedent(
                    """\

                    ## Sources
                    - `read_events_total`
                    """
                )
                + bad_receipt,
            )

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, report_path, backlog_path))

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "invalid_retrieval_metrics_receipt")
        self.assertIn("read_events_total=0", findings[0].message)

    def test_retrieval_metrics_receipt_requires_used_for_decision_column(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            backlog_path = "docs/followups/260510_followups_range.md"
            report_path = "docs/reviews/260510_plan_harvest_range.md"
            bad_receipt = self._green_retrieval_metrics_receipt().replace(" | used_for_decision", "", 1)
            self._write_markdown(root, backlog_path, self._green_backlog())
            self._write_markdown(
                root,
                report_path,
                self._green_report(backlog_path)
                + dedent(
                    """\

                    ## Sources
                    - `scripts/docs_retrieve_metrics.py`
                    """
                )
                + bad_receipt,
            )

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, report_path, backlog_path))

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "invalid_retrieval_metrics_receipt")
        self.assertIn("missing columns: used_for_decision", findings[0].message)

    def test_retrieval_metrics_receipt_false_requires_not_used_no_op_reason(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            backlog_path = "docs/followups/260510_followups_range.md"
            report_path = "docs/reviews/260510_plan_harvest_range.md"
            bad_receipt = self._green_retrieval_metrics_receipt().replace(
                "| false | not_required | N/A | not_used_for_decision |",
                "| false | not_required | N/A | N/A |",
                1,
            )
            self._write_markdown(root, backlog_path, self._green_backlog())
            self._write_markdown(
                root,
                report_path,
                self._green_report(backlog_path)
                + dedent(
                    """\

                    ## Sources
                    - `scripts/docs_retrieve_metrics.py`
                    """
                )
                + bad_receipt,
            )

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, report_path, backlog_path))

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "invalid_retrieval_metrics_receipt")
        self.assertIn("used_for_decision=false", findings[0].message)

    def test_retrieval_metrics_receipt_rejects_false_when_artifact_uses_retrieval_decision_evidence(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            backlog_path = "docs/followups/260510_followups_range.md"
            report_path = "docs/reviews/260510_plan_harvest_range.md"
            self._write_markdown(root, backlog_path, self._green_backlog())
            self._write_markdown(
                root,
                report_path,
                self._green_report(backlog_path)
                + dedent(
                    """\

                    ## Lookup evidence
                    - Used `planveyor_docs_retrieve plans "retrieval receipt"` for source selection.

                    ## Retrieval telemetry receipt
                    - query_event_id: `20260511T120000Z-abcd123456-12345678`
                    - used_for_decision: `true`
                    - read_open: `ok`
                    - read_log_status: `present`
                    - read_event_id: `read-20260511T120001Z-12345678`
                    - outcome: `used`
                    - outcome_reason: used for harvest source selection.
                    - cited/opened files: `docs/tools/snippet.md`
                    """
                )
                + self._green_retrieval_metrics_receipt(),
            )

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, report_path, backlog_path))

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "invalid_retrieval_metrics_receipt")
        self.assertIn("decision evidence", findings[0].message)

    def test_post_merge_audit_docs_retrieve_requires_canonical_receipt_heading(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            report_path = "docs/reviews/260510_post_merge_audit_range.md"
            self._write_markdown(
                root,
                report_path,
                self._post_merge_audit(
                    dedent(
                        """\
                        ## Retro addendum: docs retrieval metrics receipt

                        - `260504_2225_process_docs_retrieve_observability_metrics_wave2.md`
                        """
                    )
                ),
            )

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, report_path))

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "missing_retrieval_metrics_receipt")

    def test_post_merge_audit_accepts_pointer_to_harvest_retrieval_metrics_receipt(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            backlog_path = "docs/followups/260510_followups_range.md"
            harvest_path = "docs/reviews/260510_plan_harvest_range_deadbee_feed123.md"
            audit_path = "docs/reviews/260510_post_merge_audit_range_deadbee_feed123.md"
            self._write_markdown(root, backlog_path, self._green_backlog())
            self._write_markdown(
                root,
                harvest_path,
                self._green_report(backlog_path)
                + dedent(
                    """\

                    ## Sources
                    - `planveyor_docs_retrieve`
                    """
                )
                + self._green_retrieval_metrics_receipt(),
            )
            self._write_markdown(
                root,
                audit_path,
                self._post_merge_audit(
                    dedent(
                        f"""\
                        ## Docs retrieval metrics receipt pointer

                        - Harvest receipt: `{harvest_path}#docs-retrieval-metrics-receipt`
                        - Summary copied from harvest: `query_total=3`, `evaluated_total=2`, `outcome_evaluated_rate=0.667`, `read_log_status=missing`, `read_events_total=0`, `read_open_rate=0.0`, `used_for_decision=true`, `accepted_no_op_reason=not_applicable_bootstrap_logs_unavailable`.
                        - Trigger: `planveyor_docs_retrieve`
                        """
                    )
                ),
            )

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, audit_path))

        self.assertEqual(findings, [])

    def test_post_merge_audit_rejects_pointer_to_harvest_without_receipt(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            backlog_path = "docs/followups/260510_followups_range.md"
            harvest_path = "docs/reviews/260510_plan_harvest_range_deadbee_feed123.md"
            audit_path = "docs/reviews/260510_post_merge_audit_range_deadbee_feed123.md"
            self._write_markdown(root, backlog_path, self._green_backlog())
            self._write_markdown(
                root,
                harvest_path,
                self._green_report(backlog_path)
                + dedent(
                    """\

                    ## Sources
                    - `planveyor_docs_retrieve`
                    """
                ),
            )
            self._write_markdown(
                root,
                audit_path,
                self._post_merge_audit(
                    dedent(
                        f"""\
                        ## Docs retrieval metrics receipt pointer

                        - Harvest receipt: `{harvest_path}#docs-retrieval-metrics-receipt`
                        - Summary copied from harvest: `query_total=3`, `evaluated_total=2`, `outcome_evaluated_rate=0.667`, `read_log_status=missing`, `read_events_total=0`, `read_open_rate=0.0`, `used_for_decision=true`, `accepted_no_op_reason=not_applicable_bootstrap_logs_unavailable`.
                        - Trigger: `planveyor_docs_retrieve`
                        """
                    )
                ),
            )

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, audit_path))

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "invalid_retrieval_metrics_receipt_pointer")
        self.assertIn("lacks `## Docs retrieval metrics receipt`", findings[0].message)

    def test_post_merge_audit_rejects_pointer_without_copied_summary(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            backlog_path = "docs/followups/260510_followups_range.md"
            harvest_path = "docs/reviews/260510_plan_harvest_range_deadbee_feed123.md"
            audit_path = "docs/reviews/260510_post_merge_audit_range_deadbee_feed123.md"
            self._write_markdown(root, backlog_path, self._green_backlog())
            self._write_markdown(
                root,
                harvest_path,
                self._green_report(backlog_path)
                + dedent(
                    """\

                    ## Sources
                    - `planveyor_docs_retrieve`
                    """
                )
                + self._green_retrieval_metrics_receipt(),
            )
            self._write_markdown(
                root,
                audit_path,
                self._post_merge_audit(
                    dedent(
                        f"""\
                        ## Docs retrieval metrics receipt pointer

                        - Harvest receipt: `{harvest_path}#docs-retrieval-metrics-receipt`
                        - Trigger: `planveyor_docs_retrieve`
                        """
                    )
                ),
            )

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, audit_path))

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "invalid_retrieval_metrics_receipt_pointer")
        self.assertIn("must copy summary fields", findings[0].message)

    def test_post_merge_audit_rejects_pointer_with_field_names_only_summary(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            backlog_path = "docs/followups/260510_followups_range.md"
            harvest_path = "docs/reviews/260510_plan_harvest_range_deadbee_feed123.md"
            audit_path = "docs/reviews/260510_post_merge_audit_range_deadbee_feed123.md"
            self._write_markdown(root, backlog_path, self._green_backlog())
            self._write_markdown(
                root,
                harvest_path,
                self._green_report(backlog_path)
                + dedent(
                    """\

                    ## Sources
                    - `planveyor_docs_retrieve`
                    """
                )
                + self._green_retrieval_metrics_receipt(),
            )
            self._write_markdown(
                root,
                audit_path,
                self._post_merge_audit(
                    dedent(
                        f"""\
                        ## Docs retrieval metrics receipt pointer

                        - Harvest receipt: `{harvest_path}#docs-retrieval-metrics-receipt`
                        - Summary fields copied from harvest: `query_total`, `evaluated_total`, `outcome_evaluated_rate`, `read_log_status`, `read_events_total`, `read_open_rate`, `used_for_decision`, `accepted_no_op_reason`.
                        - Trigger: `planveyor_docs_retrieve`
                        """
                    )
                ),
            )

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, audit_path))

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "invalid_retrieval_metrics_receipt_pointer")
        self.assertIn("must copy summary fields", findings[0].message)

    def test_post_merge_audit_accepts_pointer_with_summary_table(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            backlog_path = "docs/followups/260510_followups_range.md"
            harvest_path = "docs/reviews/260510_plan_harvest_range_deadbee_feed123.md"
            audit_path = "docs/reviews/260510_post_merge_audit_range_deadbee_feed123.md"
            self._write_markdown(root, backlog_path, self._green_backlog())
            self._write_markdown(
                root,
                harvest_path,
                self._green_report(backlog_path)
                + dedent(
                    """\

                    ## Sources
                    - `planveyor_docs_retrieve`
                    """
                )
                + self._green_retrieval_metrics_receipt(),
            )
            self._write_markdown(
                root,
                audit_path,
                self._post_merge_audit(
                    dedent(
                        f"""\
                        ## Docs retrieval metrics receipt pointer

                        - Harvest receipt: `{harvest_path}#docs-retrieval-metrics-receipt`
                        - Trigger: `planveyor_docs_retrieve`

                        | query_total | evaluated_total | outcome_evaluated_rate | read_log_status | read_events_total | read_open_rate | used_for_decision | accepted_no_op_reason |
                        | ---: | ---: | ---: | --- | ---: | ---: | --- | --- |
                        | 3 | 2 | 66.7% | missing | 0 | 0.0% | true | not_applicable_bootstrap_logs_unavailable |
                        """
                    )
                ),
            )

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, audit_path))

        self.assertEqual(findings, [])

    def test_post_merge_audit_rejects_pointer_without_exact_receipt_anchor(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            backlog_path = "docs/followups/260510_followups_range.md"
            harvest_path = "docs/reviews/260510_plan_harvest_range_deadbee_feed123.md"
            audit_path = "docs/reviews/260510_post_merge_audit_range_deadbee_feed123.md"
            self._write_markdown(root, backlog_path, self._green_backlog())
            self._write_markdown(
                root,
                harvest_path,
                self._green_report(backlog_path)
                + dedent(
                    """\

                    ## Sources
                    - `planveyor_docs_retrieve`
                    """
                )
                + self._green_retrieval_metrics_receipt(),
            )
            self._write_markdown(
                root,
                audit_path,
                self._post_merge_audit(
                    dedent(
                        f"""\
                        ## Docs retrieval metrics receipt pointer

                        - Harvest receipt: `{harvest_path}`
                        - Summary copied from harvest: `query_total=3`, `evaluated_total=2`, `outcome_evaluated_rate=0.667`, `read_log_status=missing`, `read_events_total=0`, `read_open_rate=0.0`, `used_for_decision=true`, `accepted_no_op_reason=not_applicable_bootstrap_logs_unavailable`.
                        - Trigger: `planveyor_docs_retrieve`
                        """
                    )
                ),
            )

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, audit_path))

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "invalid_retrieval_metrics_receipt_pointer")
        self.assertIn("#docs-retrieval-metrics-receipt", findings[0].message)

    def test_post_merge_audit_accepts_retrieval_metrics_receipt(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            report_path = "docs/reviews/260510_post_merge_audit_range.md"
            self._write_markdown(
                root,
                report_path,
                self._post_merge_audit(
                    dedent(
                        """\
                        ## Sources
                        - `planveyor_docs_retrieve`
                        """
                    )
                    + self._green_retrieval_metrics_receipt()
                ),
            )

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, report_path))

        self.assertEqual(findings, [])

    def test_main_returns_zero_for_green_pair(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            backlog_path = root / "docs" / "followups" / "260329_1825_followups_range_deadbee_feed123.md"
            report_path = root / "docs" / "reviews" / "260329_1825_plan_harvest_range_deadbee_feed123.md"
            self._write_markdown(root, str(backlog_path.relative_to(root)), self._green_backlog())
            self._write_markdown(root, str(report_path.relative_to(root)), self._green_report(str(backlog_path.relative_to(root))))
            stdout = io.StringIO()

            with mock.patch("sys.stdout", stdout):
                result = MODULE.main([str(report_path), str(backlog_path)])

        self.assertEqual(result, 0)
        self.assertEqual(stdout.getvalue().strip(), "plan-harvest-lint: OK")

    def test_current_plan_harvest_schema_version_is_accepted(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            backlog_path = "docs/followups/260419_1109_followups_range_deadbee_feed123.md"
            report_path = "docs/reviews/260419_1109_plan_harvest_range_deadbee_feed123.md"
            self._write_markdown(root, backlog_path, self._green_backlog())
            self._write_markdown(
                root,
                report_path,
                self._green_report(backlog_path).replace("**Status:** ✅ Done\n", "**Status:** ✅ Done\n**Schema version:** review.v1\n")
                + self._current_receipt_sections(),
            )

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, report_path, backlog_path))

        self.assertEqual(findings, [])

    def test_current_plan_harvest_requires_receipt_sections(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            backlog_path = "docs/followups/260419_1108_followups_range_deadbee_feed123.md"
            report_path = "docs/reviews/260419_1108_plan_harvest_range_deadbee_feed123.md"
            self._write_markdown(root, backlog_path, self._green_backlog())
            self._write_markdown(
                root,
                report_path,
                self._green_report(backlog_path).replace("**Status:** ✅ Done\n", "**Status:** ✅ Done\n**Schema version:** review.v1\n"),
            )

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, report_path, backlog_path))

        codes = {finding.code for finding in findings}
        self.assertIn("missing_followup_harvest_triage_receipt", codes)
        self.assertIn("missing_process_improvement_decisions_receipt", codes)
        self.assertIn("missing_retrieval_metrics_receipt", codes)
        self.assertIn("missing_golden_path_lane_receipt", codes)

    def test_followup_triage_na_is_rejected_when_backlog_has_open_rows(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            backlog_path = "docs/followups/260419_1107_followups_range_deadbee_feed123.md"
            report_path = "docs/reviews/260419_1107_plan_harvest_range_deadbee_feed123.md"
            self._write_markdown(
                root,
                backlog_path,
                dedent(
                    """\
                    # Follow-ups backlog - fixture

                    **Status:** Draft

                    ## Range result
                    - `NO FOLLOWUPS` — reason: no remaining actionable debt after full-wave harvest.
                    - P1 [ ] Open fixture row - cluster=process - tags=test - to=Planner - status=open - plan=null - why: prove triage receipt cannot be N/A
                    """
                ),
            )
            self._write_markdown(
                root,
                report_path,
                self._green_report(backlog_path).replace("**Status:** ✅ Done\n", "**Status:** ✅ Done\n**Schema version:** review.v1\n")
                + self._current_receipt_sections().replace(
                    "`planveyor_followups_triage --file docs/followups/260419_1109_followups_range_deadbee_feed123.md --dry-run`: append_new=0, merge_source=0, possible_duplicate=0, route_fallback=0, unparsed_bullets=0.",
                    "`planveyor_followups_triage: N/A (why=no index)`",
                ),
            )

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, report_path, backlog_path))

        self.assertEqual([finding.code for finding in findings], ["invalid_followup_harvest_triage_receipt"])

    def test_followup_cleanup_ready_claim_requires_range_proof(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            backlog_path = "docs/followups/260419_1120_followups_range_deadbee_feed123.md"
            report_path = "docs/reviews/260419_1120_plan_harvest_range_deadbee_feed123.md"
            self._write_markdown(root, backlog_path, self._green_backlog())
            receipt_sections = self._current_receipt_sections().replace(
                "## Process-improvement promotion decisions\n",
                "- Cleanup readiness: handled followups are cleanup-ready.\n\n"
                "## Process-improvement promotion decisions\n",
            )
            body = self._current_report_with_receipts(
                backlog_path,
                receipt_sections,
            )
            self._write_markdown(root, report_path, body)

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, report_path))

        self.assertTrue(
            any(
                finding.code == "invalid_followup_harvest_triage_receipt"
                and "range-mode proof" in finding.message
                for finding in findings
            )
        )

    def test_followup_cleanup_ready_claim_accepts_durable_closeout_refs(self) -> None:
        durable_refs = (
            "already_tracked_ref=docs/followups/process_followups_master.md#example-item",
            "manual_decision_ref=docs/plans/260419_1121_process_followups_decision.md#manual-followups-decision",
        )
        for index, durable_ref in enumerate(durable_refs, start=1):
            with self.subTest(durable_ref=durable_ref), temporary_git_root() as tmpdir:
                root = Path(tmpdir).resolve()
                backlog_path = f"docs/followups/260419_112{index}_followups_range_deadbee_feed123.md"
                report_path = f"docs/reviews/260419_112{index}_plan_harvest_range_deadbee_feed123.md"
                self._write_markdown(root, backlog_path, self._green_backlog())
                receipt_sections = self._current_receipt_sections().replace(
                    "## Process-improvement promotion decisions\n",
                    "- Cleanup readiness: handled followups are cleanup-ready.\n"
                    f"- {durable_ref}\n\n"
                    "## Process-improvement promotion decisions\n",
                )
                body = self._current_report_with_receipts(
                    backlog_path,
                    receipt_sections,
                )
                self._write_markdown(root, report_path, body)

                findings = MODULE.lint_harvest_artifacts(self._load_paths(root, report_path))

                self.assertFalse(
                    any(finding.code == "invalid_followup_harvest_triage_receipt" for finding in findings),
                    [finding.render() for finding in findings],
                )

    def test_followup_cleanup_ready_claim_rejects_weak_closeout_refs(self) -> None:
        weak_refs = (
            "already_tracked_ref=handled",
            "manual_decision_ref=TBD",
        )
        for index, weak_ref in enumerate(weak_refs, start=1):
            with self.subTest(weak_ref=weak_ref), temporary_git_root() as tmpdir:
                root = Path(tmpdir).resolve()
                backlog_path = f"docs/followups/260419_112{index}_followups_range_deadbee_feed123.md"
                report_path = f"docs/reviews/260419_112{index}_plan_harvest_range_deadbee_feed123.md"
                self._write_markdown(root, backlog_path, self._green_backlog())
                receipt_sections = self._current_receipt_sections().replace(
                    "## Process-improvement promotion decisions\n",
                    "- Cleanup readiness: handled followups are cleanup-ready.\n"
                    f"- {weak_ref}\n\n"
                    "## Process-improvement promotion decisions\n",
                )
                body = self._current_report_with_receipts(
                    backlog_path,
                    receipt_sections,
                )
                self._write_markdown(root, report_path, body)

                findings = MODULE.lint_harvest_artifacts(self._load_paths(root, report_path))

                self.assertTrue(
                    any(
                        finding.code == "invalid_followup_harvest_triage_receipt"
                        and "range-mode proof" in finding.message
                        for finding in findings
                    ),
                    [finding.render() for finding in findings],
                )

    def test_followup_cleanup_ready_claim_rejects_malformed_closeout_refs(self) -> None:
        malformed_refs = (
            "manual_decision_ref=docs/plans/not_markdown.md.tmp",
            "already_tracked_ref=docs/followups/item.md:abc",
        )
        for index, malformed_ref in enumerate(malformed_refs, start=1):
            with self.subTest(malformed_ref=malformed_ref), temporary_git_root() as tmpdir:
                root = Path(tmpdir).resolve()
                backlog_path = f"docs/followups/260419_113{index}_followups_range_deadbee_feed123.md"
                report_path = f"docs/reviews/260419_113{index}_plan_harvest_range_deadbee_feed123.md"
                self._write_markdown(root, backlog_path, self._green_backlog())
                receipt_sections = self._current_receipt_sections().replace(
                    "## Process-improvement promotion decisions\n",
                    "- Cleanup readiness: handled followups are cleanup-ready.\n"
                    f"- {malformed_ref}\n\n"
                    "## Process-improvement promotion decisions\n",
                )
                body = self._current_report_with_receipts(
                    backlog_path,
                    receipt_sections,
                )
                self._write_markdown(root, report_path, body)

                findings = MODULE.lint_harvest_artifacts(self._load_paths(root, report_path))

                self.assertTrue(
                    any(finding.code == "invalid_followup_harvest_triage_receipt" for finding in findings),
                    [finding.render() for finding in findings],
                )

    def test_followup_cleanup_ready_claim_constrains_already_tracked_elsewhere_phrase(self) -> None:
        cases = (
            ("already tracked elsewhere", True),
            ("already tracked elsewhere in docs/followups/process_followups_master.md#example-item", False),
        )
        for index, (phrase, should_fail) in enumerate(cases, start=1):
            with self.subTest(phrase=phrase), temporary_git_root() as tmpdir:
                root = Path(tmpdir).resolve()
                backlog_path = f"docs/followups/260419_114{index}_followups_range_deadbee_feed123.md"
                report_path = f"docs/reviews/260419_114{index}_plan_harvest_range_deadbee_feed123.md"
                self._write_markdown(root, backlog_path, self._green_backlog())
                receipt_sections = self._current_receipt_sections().replace(
                    "## Process-improvement promotion decisions\n",
                    "- Cleanup readiness: handled followups are cleanup-ready.\n"
                    f"- Followups are {phrase}.\n\n"
                    "## Process-improvement promotion decisions\n",
                )
                body = self._current_report_with_receipts(
                    backlog_path,
                    receipt_sections,
                )
                self._write_markdown(root, report_path, body)

                findings = MODULE.lint_harvest_artifacts(self._load_paths(root, report_path))

                has_finding = any(finding.code == "invalid_followup_harvest_triage_receipt" for finding in findings)
                self.assertEqual(has_finding, should_fail, [finding.render() for finding in findings])

    def test_current_plan_harvest_accepts_no_followups_with_separate_pi_open_summary(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            backlog_path = "docs/followups/260419_1112_followups_range_deadbee_feed123.md"
            report_path = "docs/reviews/260419_1112_plan_harvest_range_deadbee_feed123.md"
            self._write_markdown(root, backlog_path, self._green_backlog())
            self._write_markdown(
                root,
                report_path,
                self._current_report_with_receipts(
                    backlog_path,
                    self._current_receipt_sections_with_pi_open_summary(),
                ),
            )

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, report_path, backlog_path))

        self.assertEqual(findings, [])

    def test_current_plan_harvest_requires_pi_open_summary_for_open_raw_rows(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            backlog_path = "docs/followups/260419_1113_followups_range_deadbee_feed123.md"
            report_path = "docs/reviews/260419_1113_plan_harvest_range_deadbee_feed123.md"
            self._write_markdown(root, backlog_path, self._green_backlog())
            self._write_markdown(
                root,
                report_path,
                self._current_report_with_receipts(
                    backlog_path,
                    self._current_receipt_sections_with_pi_open_summary(include_summary=False),
                ),
            )

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, report_path, backlog_path))

        self.assertEqual([finding.code for finding in findings], ["missing_process_improvements_open_summary"])

    def test_current_plan_harvest_requires_pi_open_summary_for_bullet_open_raw_rows(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            backlog_path = "docs/followups/260419_1118_followups_range_deadbee_feed123.md"
            report_path = "docs/reviews/260419_1118_plan_harvest_range_deadbee_feed123.md"
            self._write_markdown(root, backlog_path, self._green_backlog())
            self._write_markdown(
                root,
                report_path,
                self._current_report_with_receipts(
                    backlog_path,
                    self._current_receipt_sections_with_bullet_pi_rows(include_summary=False),
                ),
            )

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, report_path, backlog_path))

        self.assertEqual([finding.code for finding in findings], ["missing_process_improvements_open_summary"])

    def test_current_plan_harvest_rejects_bullet_pi_open_summary_undercount(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            backlog_path = "docs/followups/260419_1119_followups_range_deadbee_feed123.md"
            report_path = "docs/reviews/260419_1119_plan_harvest_range_deadbee_feed123.md"
            self._write_markdown(root, backlog_path, self._green_backlog())
            self._write_markdown(
                root,
                report_path,
                self._current_report_with_receipts(
                    backlog_path,
                    self._current_receipt_sections_with_bullet_pi_rows(
                        open_count=1,
                        null_execution_count=1,
                    ),
                ),
            )

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, report_path, backlog_path))

        self.assertEqual([finding.code for finding in findings], ["invalid_process_improvements_open_summary"] * 2)
        messages = "\n".join(finding.message for finding in findings)
        self.assertIn("expected 2, got 1", messages)
        self.assertIn("null execution fields: expected 2, got 1", messages)

    def test_current_plan_harvest_rejects_malformed_pi_open_summary(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            backlog_path = "docs/followups/260419_1114_followups_range_deadbee_feed123.md"
            report_path = "docs/reviews/260419_1114_plan_harvest_range_deadbee_feed123.md"
            self._write_markdown(root, backlog_path, self._green_backlog())
            receipt_sections = self._current_receipt_sections_with_pi_open_summary().replace(
                "null_execution=2; ",
                "",
            )
            self._write_markdown(
                root,
                report_path,
                self._current_report_with_receipts(backlog_path, receipt_sections),
            )

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, report_path, backlog_path))

        self.assertEqual([finding.code for finding in findings], ["invalid_process_improvements_open_summary"])

    def test_current_plan_harvest_rejects_pi_open_summary_undercount(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            backlog_path = "docs/followups/260419_1115_followups_range_deadbee_feed123.md"
            report_path = "docs/reviews/260419_1115_plan_harvest_range_deadbee_feed123.md"
            self._write_markdown(root, backlog_path, self._green_backlog())
            receipt_sections = self._current_receipt_sections_with_pi_open_summary().replace(
                "open=2; triaged=0; promoted=0; null_execution=2;",
                "open=1; triaged=0; promoted=0; null_execution=1;",
            )
            self._write_markdown(
                root,
                report_path,
                self._current_report_with_receipts(backlog_path, receipt_sections),
            )

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, report_path, backlog_path))

        self.assertEqual([finding.code for finding in findings], ["invalid_process_improvements_open_summary"] * 2)
        messages = "\n".join(finding.message for finding in findings)
        self.assertIn("expected 2, got 1", messages)
        self.assertIn("null execution fields: expected 2, got 1", messages)

    def test_current_plan_harvest_rejects_pi_open_summary_wrong_status_bucket(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            backlog_path = "docs/followups/260419_1116_followups_range_deadbee_feed123.md"
            report_path = "docs/reviews/260419_1116_plan_harvest_range_deadbee_feed123.md"
            self._write_markdown(root, backlog_path, self._green_backlog())
            receipt_sections = self._current_receipt_sections_with_pi_open_summary().replace(
                "| `docs/process_improvements/promotion_surface.md` | `PI-002` | `open` | `null` | `null` |",
                "| `docs/process_improvements/promotion_surface.md` | `PI-002` | `triaged` | `null` | `null` |",
            )
            self._write_markdown(
                root,
                report_path,
                self._current_report_with_receipts(backlog_path, receipt_sections),
            )

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, report_path, backlog_path))

        self.assertEqual([finding.code for finding in findings], ["invalid_process_improvements_open_summary"] * 2)
        messages = "\n".join(finding.message for finding in findings)
        self.assertIn("`process_improvements_open_summary.open` must match", messages)
        self.assertIn("`process_improvements_open_summary.triaged` must match", messages)

    def test_current_plan_harvest_rejects_pi_open_summary_wrong_null_execution_count(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            backlog_path = "docs/followups/260419_1117_followups_range_deadbee_feed123.md"
            report_path = "docs/reviews/260419_1117_plan_harvest_range_deadbee_feed123.md"
            self._write_markdown(root, backlog_path, self._green_backlog())
            receipt_sections = self._current_receipt_sections_with_pi_open_summary().replace(
                "null_execution=2; ",
                "null_execution=1; ",
            )
            self._write_markdown(
                root,
                report_path,
                self._current_report_with_receipts(backlog_path, receipt_sections),
            )

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, report_path, backlog_path))

        self.assertEqual([finding.code for finding in findings], ["invalid_process_improvements_open_summary"])
        self.assertIn("null execution fields: expected 2, got 1", findings[0].message)

    def test_shared_canon_text_requires_packetization_gate_receipt(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            backlog_path = "docs/followups/260419_1106_followups_range_deadbee_feed123.md"
            report_path = "docs/reviews/260419_1106_plan_harvest_range_deadbee_feed123.md"
            self._write_markdown(root, backlog_path, self._green_backlog())
            self._write_markdown(
                root,
                report_path,
                self._green_report(backlog_path).replace("**Status:** ✅ Done\n", "**Status:** ✅ Done\n**Schema version:** review.v1\n")
                + self._current_receipt_sections()
                + "\n## Notes\n- shared canon changed in this range.\n",
            )

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, report_path, backlog_path))

        self.assertEqual([finding.code for finding in findings], ["missing_packetization_gate_receipt"])

    def test_versionless_plan_harvest_report_is_legacy(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            backlog_path = "docs/followups/260419_1110_followups_range_deadbee_feed123.md"
            report_path = "docs/reviews/260419_1110_plan_harvest_range_deadbee_feed123.md"
            self._write_markdown(root, backlog_path, self._green_backlog())
            self._write_markdown(root, report_path, self._green_report(backlog_path))

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, report_path, backlog_path))

        self.assertEqual(findings, [])

    def test_wrong_plan_harvest_schema_version_is_reported(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            backlog_path = "docs/followups/260419_1111_followups_range_deadbee_feed123.md"
            report_path = "docs/reviews/260419_1111_plan_harvest_range_deadbee_feed123.md"
            self._write_markdown(root, backlog_path, self._green_backlog())
            self._write_markdown(
                root,
                report_path,
                self._green_report(backlog_path).replace("**Status:** ✅ Done\n", "**Status:** ✅ Done\n**Schema version:** plan.v1\n"),
            )

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, report_path, backlog_path))

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "unsupported_schema_version")
        self.assertIn("Unsupported review schema version", findings[0].message)

    def test_process_improvement_promoted_decision_fails_for_triaged_row(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            backlog_path = "docs/followups/260510_followups_range.md"
            report_path = "docs/reviews/260510_plan_harvest_range.md"
            pi_path = "docs/process_improvements/pi_source__process_improvements_backlog.md"
            self._write_markdown(root, backlog_path, self._green_backlog())
            self._write_markdown(root, pi_path, self._process_improvement_backlog(status="triaged"))
            self._write_markdown(root, report_path, self._report_with_process_decision(backlog_path=backlog_path, decision="promoted"))

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, report_path, backlog_path))

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "process_improvement_decision_state_mismatch")
        self.assertIn("does not match raw row status `triaged`", findings[0].message)

    def test_process_improvement_deferred_decision_fails_for_open_row_without_carrier(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            backlog_path = "docs/followups/260510_followups_range.md"
            report_path = "docs/reviews/260510_plan_harvest_range.md"
            pi_path = "docs/process_improvements/pi_source__process_improvements_backlog.md"
            self._write_markdown(root, backlog_path, self._green_backlog())
            self._write_markdown(
                root,
                pi_path,
                self._process_improvement_backlog(status="open", execution_kind="null", execution_ref="null"),
            )
            self._write_markdown(
                root,
                report_path,
                self._report_with_process_decision(
                    backlog_path=backlog_path,
                    decision="deferred",
                    execution_kind="N/A",
                    execution_ref="N/A",
                ),
            )

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, report_path, backlog_path))

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "process_improvement_decision_state_mismatch")
        self.assertIn("does not match raw row status `open`", findings[0].message)

    def test_process_improvement_deferred_decision_rejects_report_only_execution_ref(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            backlog_path = "docs/followups/260510_followups_range.md"
            report_path = "docs/reviews/260510_plan_harvest_range.md"
            pi_path = "docs/process_improvements/pi_source__process_improvements_backlog.md"
            self._write_markdown(root, backlog_path, self._green_backlog())
            self._write_markdown(
                root,
                pi_path,
                self._process_improvement_backlog(status="open", execution_kind="null", execution_ref="null"),
            )
            self._write_markdown(
                root,
                report_path,
                self._report_with_process_decision(
                    backlog_path=backlog_path,
                    decision="deferred",
                    execution_kind="plan",
                    execution_ref="docs/plans/execution.md",
                    owner_or_next_step="Architect: revisit after execution plan",
                ),
            )

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, report_path, backlog_path))

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "process_improvement_decision_state_mismatch")
        self.assertIn("does not match raw row status `open`", findings[0].message)

    def test_process_improvement_deferred_decision_accepts_triaged_row_with_followup_backlink(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            backlog_path = "docs/followups/260510_followups_range.md"
            report_path = "docs/reviews/260510_plan_harvest_range.md"
            pi_path = "docs/process_improvements/pi_source__process_improvements_backlog.md"
            bridge_ref = "docs/followups/260510_followups_range.md"
            self._write_markdown(root, backlog_path, self._green_backlog())
            self._write_markdown(
                root,
                pi_path,
                self._process_improvement_backlog(
                    status="triaged",
                    execution_kind="plan",
                    execution_ref="docs/plans/execution.md",
                    delivery_refs=bridge_ref,
                ),
            )
            self._write_markdown(
                root,
                report_path,
                self._report_with_process_decision(
                    backlog_path=backlog_path,
                    decision="deferred",
                    execution_kind="external_ref",
                    execution_ref=bridge_ref,
                    owner_or_next_step="Architect: revisit after routing plan terminal",
                ),
            )

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, report_path, backlog_path))

        self.assertEqual(findings, [])

    def test_process_improvement_deferred_decision_rejects_followup_without_backlink(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            backlog_path = "docs/followups/260510_followups_range.md"
            report_path = "docs/reviews/260510_plan_harvest_range.md"
            pi_path = "docs/process_improvements/pi_source__process_improvements_backlog.md"
            self._write_markdown(root, backlog_path, self._green_backlog())
            self._write_markdown(
                root,
                pi_path,
                self._process_improvement_backlog(
                    status="triaged",
                    execution_kind="plan",
                    execution_ref="docs/plans/execution.md",
                ),
            )
            self._write_markdown(
                root,
                report_path,
                self._report_with_process_decision(
                    backlog_path=backlog_path,
                    decision="deferred",
                    execution_kind="external_ref",
                    execution_ref="docs/followups/260510_followups_range.md",
                    owner_or_next_step="Architect: revisit after routing plan terminal",
                ),
            )

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, report_path, backlog_path))

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "process_improvement_decision_state_mismatch")
        self.assertIn("not backlinked from raw delivery_refs", findings[0].message)

    def test_process_improvement_handled_row_must_use_handled_decision(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            backlog_path = "docs/followups/260510_followups_range.md"
            report_path = "docs/reviews/260510_plan_harvest_range.md"
            pi_path = "docs/process_improvements/pi_source__process_improvements_backlog.md"
            self._write_markdown(root, backlog_path, self._green_backlog())
            self._write_markdown(root, pi_path, self._process_improvement_backlog(status="handled"))
            self._write_markdown(root, report_path, self._report_with_process_decision(backlog_path=backlog_path, decision="promoted"))

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, report_path, backlog_path))

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "process_improvement_decision_state_mismatch")
        self.assertIn("does not match raw row status `handled`", findings[0].message)

    def test_process_improvement_handled_decision_accepts_handled_row(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            backlog_path = "docs/followups/260510_followups_range.md"
            report_path = "docs/reviews/260510_plan_harvest_range.md"
            pi_path = "docs/process_improvements/pi_source__process_improvements_backlog.md"
            self._write_markdown(root, backlog_path, self._green_backlog())
            self._write_markdown(root, pi_path, self._process_improvement_backlog(status="handled"))
            self._write_markdown(root, report_path, self._report_with_process_decision(backlog_path=backlog_path, decision="handled"))

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, report_path, backlog_path))

        self.assertEqual(findings, [])

    def test_process_improvement_source_ref_cell_disambiguates_duplicate_entry_ids(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            backlog_path = "docs/followups/260510_followups_range.md"
            report_path = "docs/reviews/260510_plan_harvest_range.md"
            source_ref = "docs/plans/260510_1200_process_pi_source.md"
            self._write_markdown(root, backlog_path, self._green_backlog())
            self._write_markdown(
                root,
                "docs/process_improvements/pi_source__process_improvements_backlog.md",
                self._process_improvement_backlog(source_ref=source_ref, status="handled"),
            )
            self._write_markdown(
                root,
                "docs/process_improvements/other_source__process_improvements_backlog.md",
                self._process_improvement_backlog(
                    source_ref="docs/plans/260510_1201_process_other_source.md",
                    status="triaged",
                ),
            )
            self._write_markdown(
                root,
                report_path,
                self._report_with_process_decision_source_ref_cell(backlog_path=backlog_path, source_ref=source_ref),
            )

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, report_path, backlog_path))

        self.assertEqual(findings, [])

    def test_process_improvement_unresolved_row_is_reported(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            backlog_path = "docs/followups/260510_followups_range.md"
            report_path = "docs/reviews/260510_plan_harvest_range.md"
            self._write_markdown(root, backlog_path, self._green_backlog())
            self._write_markdown(root, report_path, self._report_with_process_decision(backlog_path=backlog_path))

            findings = MODULE.lint_harvest_artifacts(self._load_paths(root, report_path, backlog_path))

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "unresolved_process_improvement_row")


if __name__ == "__main__":
    unittest.main()

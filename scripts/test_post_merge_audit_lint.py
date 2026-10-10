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


MODULE_PATH = Path(__file__).with_name("post_merge_audit_lint.py")
SPEC = importlib.util.spec_from_file_location("post_merge_audit_lint", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

import review_schema_contract
from test_support.process_contract_fixtures import temporary_git_root


class PostMergeAuditLintTests(unittest.TestCase):
    def _write_markdown(self, root: Path, rel_path: str, body: str) -> Path:
        if (
            rel_path != "docs/code_reviews/260329_1800_example.md"
            and "docs/code_reviews/260329_1800_example.md#Lane synthesis" in body
        ):
            source = root / "docs/code_reviews/260329_1800_example.md"
            if not source.exists():
                self._write_markdown(root, "docs/code_reviews/260329_1800_example.md", self._review_source_fixture())
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        return target

    def _load_single(self, root: Path, rel_path: str):
        return MODULE.load_audit_artifacts(root, [rel_path])

    def test_review_schema_version_uses_shared_contract(self) -> None:
        self.assertEqual(MODULE.CURRENT_REVIEW_SCHEMA_VERSION, review_schema_contract.CURRENT_REVIEW_SCHEMA_VERSION)
        self.assertEqual(MODULE.CURRENT_REVIEW_SCHEMA_VERSION, "review.v1")

    def _review_source_fixture(self) -> str:
        return dedent(
            """\
            # Review: example topic

            **Date:** 29.03.2026 18:00 MSK
            **Status:** ✅ OK

            ## Lane synthesis / aggregate verdict
            - Source lanes: `reviewer_code_risk`, `reviewer_code_contracts`
            - Aggregate status: `✅ OK`
            - Finding: `contracts:B1`
              - source_lane: `reviewer_code_contracts`
              - lane_finding_id: `contracts:B1`
              - synthesis_disposition: `accepted`
              - canonical_ref: `docs/code_reviews/260329_1800_example.md#B1`
              - audit_status: `pending_post_merge_audit`
              - followup_plan: `N/A`
            - Finding: `N/A (findings отсутствуют)`
              - source_lane: `reviewer_code_risk+reviewer_code_contracts`
              - lane_finding_id: `N/A (no lane findings)`
              - synthesis_disposition: `no_findings`
              - canonical_ref: `docs/code_reviews/260329_1800_example.md#Lane-synthesis--aggregate-verdict`
              - audit_status: `pending_post_merge_audit`
              - followup_plan: `N/A`
            """
        )

    def _green_audit_fixture(self) -> str:
        return dedent(
            """\
            # Review: Post-merge audit — example topic

            **Date:** 29.03.2026 18:10 MSK
            **Topic:** example
            **Status:** ✅ Done

            ## Audit matrix (summary)
            ### A1) Example item
            - Lane synthesis source: `docs/code_reviews/260329_1800_example.md#Lane synthesis / aggregate verdict`
            - source_lane: `reviewer_code_contracts`
            - lane_finding_id: `contracts:B1`
            - synthesis_disposition: `accepted`
            - canonical_ref: `docs/reviews/260329_1810_post_merge_audit_example.md#A1`
            - audit_status: `done`
            - followup_plan: `N/A`
            - Blocker refs: `N/A (no live blocker lineage)`
            - Code anchors: `scripts/post_merge_audit_lint.py:1`
            - Tests/smokes: `python -B scripts/test_post_merge_audit_lint.py`
            - Docs: `docs/reviews/_template_post_merge_audit.md`
            - Status: `✅ Done`

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

    def _current_green_audit_fixture(self) -> str:
        return self._green_audit_fixture().replace("**Status:** ✅ Done\n", "**Status:** ✅ Done\n**Schema version:** review.v1\n")

    def _compact_section(self) -> str:
        return dedent(
            """\
            ## Compact no-findings mode
            - compact_mode: enabled
            - review_status: ✅ OK
            - findings: no_findings
            - live_blocker_lineage: N/A (no live blocker lineage)
            - role_quality_candidate: N/A (why=no flagged role-quality candidate)
            - process_improvements: clear
            - followups: clear
            - packetization: N/A (why=no shared canon delta)
            - ready_to_push: clear
            - docs_index_context: clear
            - receipt_citations: clear
            - producer_authority: N/A (why=manual post-merge audit author)
            """
        )

    def _compact_audit_fixture(self) -> str:
        body = self._current_green_audit_fixture()
        body = body.replace("- lane_finding_id: `contracts:B1`\n", "- lane_finding_id: `N/A (no lane findings)`\n")
        body = body.replace("- synthesis_disposition: `accepted`\n", "- synthesis_disposition: `no_findings`\n")
        body = body.replace("- Blocker refs: `docs/code_reviews/260329_1800_example.md#B1`\n", "- Blocker refs: `N/A (no live blocker lineage)`\n")
        return body.replace("## Role assessment (censor receipts, if applicable)\n", self._compact_section() + "\n## Role assessment (censor receipts, if applicable)\n")

    def _audit_with_role_assessment(self, body: str) -> str:
        fixture = self._green_audit_fixture().replace("**Status:** ✅ Done\n", "**Status:** ✅ Done\n**Schema version:** review.v1\n")
        before, _ = fixture.split("## Role assessment (censor receipts, if applicable)\n", 1)
        return before + "## Role assessment (censor receipts, if applicable)\n" + dedent(body)

    def test_green_fixture_passes(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(root, "docs/reviews/260329_1810_post_merge_audit_example.md", self._green_audit_fixture())

            findings = MODULE.lint_audit_artifacts(self._load_single(root, "docs/reviews/260329_1810_post_merge_audit_example.md"))

        self.assertEqual(findings, [])

    def test_current_compact_no_findings_mode_passes_when_truth_hosts_are_clear(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/reviews/260419_1200_post_merge_audit_compact_ok.md",
                self._compact_audit_fixture(),
            )

            findings = MODULE.lint_audit_artifacts(
                self._load_single(root, "docs/reviews/260419_1200_post_merge_audit_compact_ok.md")
            )

        self.assertEqual(findings, [])

    def test_helper_backed_role_assessment_passes(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/reviews/260329_1810_post_merge_audit_role_quality.md",
                self._audit_with_role_assessment(
                    """\
                    - Helper command: `python3 scripts/censor_receipts_harvest.py --plan docs/plans/example.md --format json`
                    - Helper summary: `receipts=1; complete=1; partial=0; missing=0; unconfirmed=0`
                    - Helper role-quality: `helped=1; missed live blocker=0; receipt missing=0; noise/no-op=0; UNCONFIRMED=0`
                    - Receipt source: `docs/plans/example.md:10`
                    - Assessment: `helped`
                    """
                ),
            )

            findings = MODULE.lint_audit_artifacts(
                self._load_single(root, "docs/reviews/260329_1810_post_merge_audit_role_quality.md")
            )

        self.assertEqual(findings, [])

    def test_current_compact_no_findings_mode_still_requires_no_findings_provenance(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            broken = self._compact_audit_fixture().replace(
                "- synthesis_disposition: `no_findings`\n",
                "- synthesis_disposition: `accepted`\n",
            )
            self._write_markdown(
                root,
                "docs/reviews/260419_1201_post_merge_audit_compact_missing_no_findings.md",
                broken,
            )

            findings = MODULE.lint_audit_artifacts(
                self._load_single(root, "docs/reviews/260419_1201_post_merge_audit_compact_missing_no_findings.md")
            )

        self.assertIn("compact_no_findings_missing_no_findings_provenance", {finding.code for finding in findings})

    def test_current_compact_no_findings_mode_rejects_live_blocker_lineage(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            broken = self._compact_audit_fixture().replace(
                "- live_blocker_lineage: N/A (no live blocker lineage)\n",
                "- live_blocker_lineage: `docs/code_reviews/260419_1202.md#B1`\n",
            )
            self._write_markdown(
                root,
                "docs/reviews/260419_1202_post_merge_audit_compact_live_blocker.md",
                broken,
            )

            findings = MODULE.lint_audit_artifacts(
                self._load_single(root, "docs/reviews/260419_1202_post_merge_audit_compact_live_blocker.md")
            )

        self.assertIn("compact_no_findings_live_blocker_lineage", {finding.code for finding in findings})

    def test_current_compact_no_findings_mode_rejects_flagged_role_quality_candidate(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            broken = self._compact_audit_fixture().replace(
                "- role_quality_candidate: N/A (why=no flagged role-quality candidate)\n",
                "- role_quality_candidate: flagged plan `docs/plans/example.md`\n",
            )
            self._write_markdown(
                root,
                "docs/reviews/260419_1203_post_merge_audit_compact_role_quality.md",
                broken,
            )

            findings = MODULE.lint_audit_artifacts(
                self._load_single(root, "docs/reviews/260419_1203_post_merge_audit_compact_role_quality.md")
            )

        self.assertIn("compact_no_findings_role_quality_candidate", {finding.code for finding in findings})

    def test_current_compact_no_findings_mode_rejects_unclear_residual_hosts(self) -> None:
        replacements = [
            ("process_improvements", "red"),
            ("process_improvements", "unclear"),
            ("process_improvements", "not clear"),
            ("process_improvements", "stale"),
            ("process_improvements", "inconsistent"),
            ("process_improvements", "clear but inconsistent"),
            ("process_improvements", "not applicable"),
            ("followups", "pending"),
            ("followups", "not applicable"),
            ("packetization", "ambiguous"),
            ("packetization", "not applicable"),
            ("ready_to_push", "missing"),
            ("docs_index_context", "UNCONFIRMED"),
            ("receipt_citations", "blocked"),
        ]
        for field, value in replacements:
            with self.subTest(field=field, value=value), temporary_git_root() as tmpdir:
                root = Path(tmpdir).resolve()
                broken = self._compact_audit_fixture().replace(f"- {field}: clear\n", f"- {field}: {value}\n")
                if field == "packetization":
                    broken = self._compact_audit_fixture().replace(
                        "- packetization: N/A (why=no shared canon delta)\n",
                        f"- packetization: {value}\n",
                    )
                self._write_markdown(
                    root,
                    f"docs/reviews/260419_1204_post_merge_audit_compact_{field}.md",
                    broken,
                )

                findings = MODULE.lint_audit_artifacts(
                    self._load_single(root, f"docs/reviews/260419_1204_post_merge_audit_compact_{field}.md")
                )

                self.assertIn("compact_no_findings_residual_host_not_clear", {finding.code for finding in findings})

    def test_current_compact_no_findings_mode_rejects_stale_core_preconditions(self) -> None:
        replacements = [
            ("review_status", "✅ OK (stale)", "compact_no_findings_review_not_green"),
            ("findings", "no_findings but stale", "compact_no_findings_findings_present"),
            (
                "live_blocker_lineage",
                "N/A (no live blocker lineage, stale readback)",
                "compact_no_findings_live_blocker_lineage",
            ),
            (
                "role_quality_candidate",
                "N/A (why=no flagged role-quality candidate; stale readback)",
                "compact_no_findings_role_quality_candidate",
            ),
            ("producer_authority", "none", "compact_no_findings_producer_authority_ambiguous"),
        ]
        for field, value, expected_code in replacements:
            with self.subTest(field=field, value=value), temporary_git_root() as tmpdir:
                root = Path(tmpdir).resolve()
                current_line = next(
                    line for line in self._compact_section().splitlines() if line.startswith(f"- {field}: ")
                )
                broken = self._compact_audit_fixture().replace(f"{current_line}\n", f"- {field}: {value}\n")
                self._write_markdown(
                    root,
                    f"docs/reviews/260419_1205_post_merge_audit_compact_{field}.md",
                    broken,
                )

                findings = MODULE.lint_audit_artifacts(
                    self._load_single(root, f"docs/reviews/260419_1205_post_merge_audit_compact_{field}.md")
                )

                self.assertIn(expected_code, {finding.code for finding in findings})

    def test_current_compact_no_findings_mode_rejects_duplicate_truth_hosts(self) -> None:
        replacements = [
            ("process_improvements", "pending"),
            ("review_status", "✅ OK (stale)"),
            ("producer_authority", "none"),
        ]
        for field, duplicate_value in replacements:
            with self.subTest(field=field), temporary_git_root() as tmpdir:
                root = Path(tmpdir).resolve()
                current_line = next(
                    line for line in self._compact_section().splitlines() if line.startswith(f"- {field}: ")
                )
                broken = self._compact_audit_fixture().replace(
                    f"{current_line}\n",
                    f"{current_line}\n- {field}: {duplicate_value}\n",
                )
                self._write_markdown(
                    root,
                    f"docs/reviews/260419_1206_post_merge_audit_compact_duplicate_{field}.md",
                    broken,
                )

                findings = MODULE.lint_audit_artifacts(
                    self._load_single(root, f"docs/reviews/260419_1206_post_merge_audit_compact_duplicate_{field}.md")
                )

                self.assertIn("compact_no_findings_duplicate_field", {finding.code for finding in findings})

    def test_role_assessment_without_helper_summary_fails_closed(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/reviews/260329_1810_post_merge_audit_missing_helper_summary.md",
                self._audit_with_role_assessment(
                    """\
                    - Receipt source: `docs/plans/example.md:10`
                    - Assessment: `helped`
                    """
                ),
            )

            findings = MODULE.lint_audit_artifacts(
                self._load_single(root, "docs/reviews/260329_1810_post_merge_audit_missing_helper_summary.md")
            )

        self.assertEqual([finding.code for finding in findings], ["missing_censor_receipt_helper_summary"])

    def test_partial_helper_summary_fails_closed(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/reviews/260329_1810_post_merge_audit_partial_helper_summary.md",
                self._audit_with_role_assessment(
                    """\
                    - Helper command: `python3 scripts/censor_receipts_harvest.py --plan docs/plans/example.md --format json`
                    - Helper summary: `receipts=2; complete=1; partial=1; missing=0; unconfirmed=0`
                    - Helper role-quality: `helped=1; missed live blocker=0; receipt missing=1; noise/no-op=0; UNCONFIRMED=0`
                    - Receipt source: `docs/plans/example.md:10`
                    - Assessment: `UNCONFIRMED`
                    """
                ),
            )

            findings = MODULE.lint_audit_artifacts(
                self._load_single(root, "docs/reviews/260329_1810_post_merge_audit_partial_helper_summary.md")
            )

        self.assertEqual([finding.code for finding in findings], ["invalid_censor_receipt_assessment"])

    def test_helped_assessment_with_bad_helper_counters_fails_closed(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/reviews/260329_1810_post_merge_audit_contradictory_helper_summary.md",
                self._audit_with_role_assessment(
                    """\
                    - Helper command: `python3 scripts/censor_receipts_harvest.py --plan docs/plans/example.md --format json`
                    - Helper summary: `receipts=1; complete=1; partial=0; missing=0; unconfirmed=0`
                    - Helper role-quality: `helped=1; missed live blocker=1; receipt missing=0; noise/no-op=0; UNCONFIRMED=0`
                    - Receipt source: `docs/plans/example.md:10`
                    - Assessment: `helped`
                    """
                ),
            )

            findings = MODULE.lint_audit_artifacts(
                self._load_single(root, "docs/reviews/260329_1810_post_merge_audit_contradictory_helper_summary.md")
            )

        self.assertEqual([finding.code for finding in findings], ["contradictory_censor_receipt_assessment"])

    def test_helper_summary_missing_unconfirmed_counter_fails_closed(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/reviews/260329_1810_post_merge_audit_missing_summary_counter.md",
                self._audit_with_role_assessment(
                    """\
                    - Helper command: `python3 scripts/censor_receipts_harvest.py --plan docs/plans/example.md --format json`
                    - Helper summary: `receipts=1; complete=1; partial=0; missing=0`
                    - Helper role-quality: `helped=1; missed live blocker=0; receipt missing=0; noise/no-op=0; UNCONFIRMED=0`
                    - Receipt source: `docs/plans/example.md:10`
                    - Assessment: `helped`
                    """
                ),
            )

            findings = MODULE.lint_audit_artifacts(
                self._load_single(root, "docs/reviews/260329_1810_post_merge_audit_missing_summary_counter.md")
            )

        self.assertEqual([finding.code for finding in findings], ["invalid_censor_receipt_helper_counters"])
        self.assertIn("Helper summary: unconfirmed", findings[0].message)

    def test_helper_role_quality_missing_receipt_missing_counter_fails_closed(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/reviews/260329_1810_post_merge_audit_missing_receipt_missing_counter.md",
                self._audit_with_role_assessment(
                    """\
                    - Helper command: `python3 scripts/censor_receipts_harvest.py --plan docs/plans/example.md --format json`
                    - Helper summary: `receipts=1; complete=1; partial=0; missing=0; unconfirmed=0`
                    - Helper role-quality: `helped=1; missed live blocker=0; noise/no-op=0; UNCONFIRMED=0`
                    - Receipt source: `docs/plans/example.md:10`
                    - Assessment: `helped`
                    """
                ),
            )

            findings = MODULE.lint_audit_artifacts(
                self._load_single(root, "docs/reviews/260329_1810_post_merge_audit_missing_receipt_missing_counter.md")
            )

        self.assertEqual([finding.code for finding in findings], ["invalid_censor_receipt_helper_counters"])
        self.assertIn("Helper role-quality: receipt missing", findings[0].message)

    def test_helper_role_quality_missing_unconfirmed_counter_fails_closed(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/reviews/260329_1810_post_merge_audit_missing_role_quality_unconfirmed.md",
                self._audit_with_role_assessment(
                    """\
                    - Helper command: `python3 scripts/censor_receipts_harvest.py --plan docs/plans/example.md --format json`
                    - Helper summary: `receipts=1; complete=1; partial=0; missing=0; unconfirmed=0`
                    - Helper role-quality: `helped=1; missed live blocker=0; receipt missing=0; noise/no-op=0`
                    - Receipt source: `docs/plans/example.md:10`
                    - Assessment: `helped`
                    """
                ),
            )

            findings = MODULE.lint_audit_artifacts(
                self._load_single(root, "docs/reviews/260329_1810_post_merge_audit_missing_role_quality_unconfirmed.md")
            )

        self.assertEqual([finding.code for finding in findings], ["invalid_censor_receipt_helper_counters"])
        self.assertIn("Helper role-quality: unconfirmed", findings[0].message)
    def test_lookup_backed_audit_requires_retrieval_telemetry_receipt(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/reviews/260329_1810_post_merge_audit_lookup.md",
                self._green_audit_fixture()
                + "\n## Lookup evidence\n- Used `planveyor_docs_lookup plans \"retrieval receipt\"` for audit source selection.\n",
            )

            findings = MODULE.lint_audit_artifacts(
                self._load_single(root, "docs/reviews/260329_1810_post_merge_audit_lookup.md")
            )

        self.assertIn("missing_retrieval_telemetry_receipt", {finding.code for finding in findings})

    def test_retrieve_backed_audit_source_selection_requires_retrieval_telemetry_receipt(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/reviews/260329_1810_post_merge_audit_retrieve.md",
                self._green_audit_fixture()
                + "\n## Lookup evidence\n- Used `planveyor_docs_retrieve plans \"retrieval receipt\"` for audit source selection.\n",
            )

            findings = MODULE.lint_audit_artifacts(
                self._load_single(root, "docs/reviews/260329_1810_post_merge_audit_retrieve.md")
            )

        self.assertIn("missing_retrieval_telemetry_receipt", {finding.code for finding in findings})

    def test_lookup_backed_audit_accepts_retrieval_telemetry_receipt(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/reviews/260329_1810_post_merge_audit_lookup_ok.md",
                self._green_audit_fixture()
                + dedent(
                    """\

                    ## Lookup evidence
                    - Used `planveyor_docs_lookup plans "retrieval receipt"` for audit source selection.

                    ## Retrieval telemetry receipt
                    - query_event_id: `20260511T120000Z-abcd123456-12345678`
                    - used_for_decision: `true`
                    - read_open: `ok`
                    - read_log_status: `present`
                    - read_event_id: `read-20260511T120001Z-12345678`
                    - outcome: `used`
                    - outcome_reason: used for audit source selection.
                    - cited/opened files: `docs/tools/snippet.md`
                    """
                ),
            )

            findings = MODULE.lint_audit_artifacts(
                self._load_single(root, "docs/reviews/260329_1810_post_merge_audit_lookup_ok.md")
            )

        self.assertNotIn("missing_retrieval_telemetry_receipt", {finding.code for finding in findings})
        self.assertNotIn("invalid_retrieval_telemetry_receipt", {finding.code for finding in findings})

    def test_missing_followup_carrier_phrase_is_reported(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            broken = self._green_audit_fixture().replace("`lost follow-up during harvest/promotion`", "`missing carrier`")
            self._write_markdown(root, "docs/reviews/260329_1811_post_merge_audit_missing_phrase.md", broken)

            findings = MODULE.lint_audit_artifacts(
                self._load_single(root, "docs/reviews/260329_1811_post_merge_audit_missing_phrase.md")
            )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "missing_followup_carrier_phrase")
        self.assertIn("lost follow-up during harvest/promotion", findings[0].message)

    def test_missing_role_assessment_section_is_reported(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            broken = self._green_audit_fixture().split("## Role assessment (censor receipts, if applicable)\n", 1)[0]
            self._write_markdown(root, "docs/reviews/260329_1812_post_merge_audit_missing_role_section.md", broken)

            findings = MODULE.lint_audit_artifacts(
                self._load_single(root, "docs/reviews/260329_1812_post_merge_audit_missing_role_section.md")
            )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "missing_role_assessment_section")
        self.assertIn("Role assessment", findings[0].message)

    def test_done_without_lane_synthesis_source_is_reported(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            broken = self._green_audit_fixture().replace(
                "- Lane synthesis source: `docs/code_reviews/260329_1800_example.md#Lane synthesis / aggregate verdict`\n",
                "",
            )
            self._write_markdown(root, "docs/reviews/260329_1815_post_merge_audit_missing_lane_source.md", broken)

            findings = MODULE.lint_audit_artifacts(
                self._load_single(root, "docs/reviews/260329_1815_post_merge_audit_missing_lane_source.md")
            )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "missing_lane_synthesis_source")
        self.assertIn("Lane synthesis source", findings[0].message)

    def test_done_without_provenance_field_is_reported(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            broken = self._green_audit_fixture().replace("- canonical_ref: `docs/reviews/260329_1810_post_merge_audit_example.md#A1`\n", "")
            self._write_markdown(root, "docs/reviews/260329_1816_post_merge_audit_missing_provenance.md", broken)

            findings = MODULE.lint_audit_artifacts(
                self._load_single(root, "docs/reviews/260329_1816_post_merge_audit_missing_provenance.md")
            )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "missing_lane_provenance_field")
        self.assertIn("canonical_ref", findings[0].message)

    def test_derived_index_receipt_requires_derived_index_summary(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/reviews/260329_1813_post_merge_audit_router.md",
                dedent(
                    """\
                    # Review: Post-merge audit — router profile

                    **Date:** 29.03.2026 18:13 MSK
                    **Topic:** derived-index fixture
                    **Status:** ✅ Done

                    ## Audit matrix (summary)
                    ### A1) Router item
                    - Lane synthesis source: `docs/code_reviews/260329_1805_router.md#Lane synthesis / aggregate verdict`
                    - source_lane: `synthesized`
                    - lane_finding_id: `contracts:B3`
                    - synthesis_disposition: `accepted`
                    - canonical_ref: `docs/reviews/260329_1813_post_merge_audit_router.md#A1`
                    - audit_status: `done`
                    - followup_plan: `N/A`

                    ## Follow-ups
                    - Audit still knows about `lost follow-up during harvest/promotion`.

                    ## Role assessment (censor receipts, if applicable)
                    - Receipt source: `N/A`

                    ## Notes
                    - Derived-index note: blocker-free closeout refreshed `planveyor_docs_index_build all`.
                    """
                ),
            )

            findings = MODULE.lint_audit_artifacts(self._load_single(root, "docs/reviews/260329_1813_post_merge_audit_router.md"))

        self.assertEqual(len(findings), 3)
        self.assertTrue(all(finding.code == "missing_derived_index_receipt" for finding in findings))
        self.assertTrue(any("docs_context_check" in finding.message for finding in findings))
        self.assertTrue(any("plans" in finding.message for finding in findings))
        self.assertTrue(any("followups" in finding.message for finding in findings))

    def test_main_returns_non_zero_for_broken_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            broken = self._green_audit_fixture().replace("## Role assessment (censor receipts, if applicable)\n", "## Different section\n")
            self._write_markdown(root, "docs/reviews/260329_1814_post_merge_audit_cli.md", broken)
            stdout = io.StringIO()

            with mock.patch("sys.stdout", stdout):
                result = MODULE.main([str(root / "docs" / "reviews" / "260329_1814_post_merge_audit_cli.md")])

        self.assertEqual(result, 1)
        output = stdout.getvalue()
        self.assertIn("post-merge-audit-lint: FAIL", output)
        self.assertIn("missing_role_assessment_section", output)

    def test_current_post_merge_audit_schema_version_is_accepted(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/reviews/260419_1112_post_merge_audit_schema_current.md",
                self._green_audit_fixture().replace("**Status:** ✅ Done\n", "**Status:** ✅ Done\n**Schema version:** review.v1\n"),
            )

            findings = MODULE.lint_audit_artifacts(
                self._load_single(root, "docs/reviews/260419_1112_post_merge_audit_schema_current.md")
            )

        self.assertEqual(findings, [])

    def test_current_post_merge_audit_rejects_missing_review_artifact_for_done(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            body = self._current_green_audit_fixture().replace(
                "docs/code_reviews/260329_1800_example.md#Lane synthesis / aggregate verdict",
                "docs/code_reviews/260329_1801_missing.md#Lane synthesis / aggregate verdict",
            )
            self._write_markdown(root, "docs/reviews/260419_1110_post_merge_audit_missing_source.md", body)

            findings = MODULE.lint_audit_artifacts(
                self._load_single(root, "docs/reviews/260419_1110_post_merge_audit_missing_source.md")
            )

        self.assertIn("audit_status_source_missing", {finding.code for finding in findings})

    def test_current_post_merge_audit_rejects_missing_lane_synthesis_section_for_done(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/code_reviews/260329_1800_example.md",
                "# Review: example\n\n**Status:** ✅ OK\n\n## Notes\n- No synthesis section.\n",
            )
            self._write_markdown(
                root,
                "docs/reviews/260419_1110_post_merge_audit_missing_lane_synthesis.md",
                self._current_green_audit_fixture(),
            )

            findings = MODULE.lint_audit_artifacts(
                self._load_single(root, "docs/reviews/260419_1110_post_merge_audit_missing_lane_synthesis.md")
            )

        self.assertIn("audit_status_source_missing_lane_synthesis", {finding.code for finding in findings})

    def test_current_post_merge_audit_rejects_ambiguous_lane_finding_ref_for_done(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            ambiguous_source = self._review_source_fixture().replace(
                "- Finding: `N/A (findings отсутствуют)`\n",
                (
                    "- Finding: `contracts:B1 duplicate`\n"
                    "  - source_lane: `reviewer_code_risk`\n"
                    "  - lane_finding_id: `contracts:B1`\n"
                    "  - synthesis_disposition: `accepted`\n"
                    "  - canonical_ref: `docs/code_reviews/260329_1800_example.md#B1-duplicate`\n"
                    "  - audit_status: `pending_post_merge_audit`\n"
                    "  - followup_plan: `N/A`\n"
                    "- Finding: `N/A (findings отсутствуют)`\n"
                ),
            )
            self._write_markdown(root, "docs/code_reviews/260329_1800_example.md", ambiguous_source)
            self._write_markdown(
                root,
                "docs/reviews/260419_1110_post_merge_audit_ambiguous_source.md",
                self._current_green_audit_fixture(),
            )

            findings = MODULE.lint_audit_artifacts(
                self._load_single(root, "docs/reviews/260419_1110_post_merge_audit_ambiguous_source.md")
            )

        self.assertIn("audit_status_source_ambiguous", {finding.code for finding in findings})

    def test_current_post_merge_audit_rejects_source_synthesis_mismatch_for_done(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/code_reviews/260329_1800_example.md",
                self._review_source_fixture().replace("synthesis_disposition: `accepted`", "synthesis_disposition: `deferred`", 1),
            )
            self._write_markdown(
                root,
                "docs/reviews/260419_1110_post_merge_audit_source_mismatch.md",
                self._current_green_audit_fixture(),
            )

            findings = MODULE.lint_audit_artifacts(
                self._load_single(root, "docs/reviews/260419_1110_post_merge_audit_source_mismatch.md")
            )

        self.assertIn("audit_status_source_mismatch", {finding.code for finding in findings})

    def test_current_post_merge_audit_rejects_deferred_synthesis_done(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            deferred_source = self._review_source_fixture().replace(
                "synthesis_disposition: `accepted`",
                "synthesis_disposition: `deferred`",
                1,
            )
            body = self._current_green_audit_fixture().replace(
                "- synthesis_disposition: `accepted`\n",
                "- synthesis_disposition: `deferred`\n",
            )
            self._write_markdown(root, "docs/code_reviews/260329_1800_example.md", deferred_source)
            self._write_markdown(root, "docs/reviews/260419_1110_post_merge_audit_deferred_done.md", body)

            findings = MODULE.lint_audit_artifacts(
                self._load_single(root, "docs/reviews/260419_1110_post_merge_audit_deferred_done.md")
            )

        self.assertIn("audit_status_done_conflicts_with_source", {finding.code for finding in findings})

    def test_current_post_merge_audit_rejects_live_blocker_done(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            body = self._current_green_audit_fixture().replace(
                "- Blocker refs: `N/A (no live blocker lineage)`\n",
                "- Blocker refs: `docs/code_reviews/260329_1800_example.md#B1`\n",
            )
            self._write_markdown(root, "docs/reviews/260419_1110_post_merge_audit_live_blocker_done.md", body)

            findings = MODULE.lint_audit_artifacts(
                self._load_single(root, "docs/reviews/260419_1110_post_merge_audit_live_blocker_done.md")
            )

        self.assertIn("audit_status_done_with_live_blocker", {finding.code for finding in findings})

    def test_current_post_merge_audit_rejects_live_blocker_substrings_without_nonlive_proof(self) -> None:
        cases = {
            "closed_path": "docs/code_reviews/260329_closed_example.md#B1",
            "historical_path": "docs/code_reviews/260329_historical_example.md#B1",
            "superseded_path": "docs/code_reviews/260329_superseded_example.md#B1",
            "negated_closed": "not closed: docs/code_reviews/260329_1800_example.md#B1",
            "prose_only": "closed in prose but still docs/code_reviews/260329_1800_example.md#B1",
        }
        for case_name, blocker_refs in cases.items():
            with self.subTest(case_name=case_name):
                with temporary_git_root() as tmpdir:
                    root = Path(tmpdir).resolve()
                    body = self._current_green_audit_fixture().replace(
                        "- Blocker refs: `N/A (no live blocker lineage)`\n",
                        f"- Blocker refs: `{blocker_refs}`\n",
                    )
                    self._write_markdown(root, f"docs/reviews/260419_1110_post_merge_audit_{case_name}.md", body)

                    findings = MODULE.lint_audit_artifacts(
                        self._load_single(root, f"docs/reviews/260419_1110_post_merge_audit_{case_name}.md")
                    )

                self.assertIn("audit_status_done_with_live_blocker", {finding.code for finding in findings})

    def test_current_post_merge_audit_accepts_explicit_nonlive_blocker_proof(self) -> None:
        cases = {
            "closed": "closed: docs/code_reviews/260329_1800_example.md#B1",
            "historical": "historical: docs/code_reviews/260329_1800_example.md#B1",
            "superseded": "superseded: docs/code_reviews/260329_1800_example.md#B1",
            "closed_proof": "closed proof: manual_decision_ref=docs/plans/260329_1812_followup.md#decision",
        }
        for case_name, blocker_refs in cases.items():
            with self.subTest(case_name=case_name):
                with temporary_git_root() as tmpdir:
                    root = Path(tmpdir).resolve()
                    body = self._current_green_audit_fixture().replace(
                        "- Blocker refs: `N/A (no live blocker lineage)`\n",
                        f"- Blocker refs: `{blocker_refs}`\n",
                    )
                    self._write_markdown(root, f"docs/reviews/260419_1110_post_merge_audit_nonlive_blocker_{case_name}.md", body)

                    findings = MODULE.lint_audit_artifacts(
                        self._load_single(root, f"docs/reviews/260419_1110_post_merge_audit_nonlive_blocker_{case_name}.md")
                    )

                self.assertEqual(findings, [])

    def test_current_post_merge_audit_rejects_nonterminal_followup_done(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            body = self._current_green_audit_fixture().replace(
                "- followup_plan: `N/A`\n",
                "- followup_plan: `docs/plans/260329_1812_followup.md`\n",
            )
            self._write_markdown(root, "docs/reviews/260419_1110_post_merge_audit_followup_done.md", body)

            findings = MODULE.lint_audit_artifacts(
                self._load_single(root, "docs/reviews/260419_1110_post_merge_audit_followup_done.md")
            )

        self.assertIn("audit_status_done_with_nonterminal_followup", {finding.code for finding in findings})

    def test_current_post_merge_audit_rejects_accepted_named_followup_path_without_terminal_proof(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            body = self._current_green_audit_fixture().replace(
                "- followup_plan: `N/A`\n",
                "- followup_plan: `docs/plans/260329_1812_accepted_followup.md`\n",
            )
            self._write_markdown(root, "docs/reviews/260419_1110_post_merge_audit_accepted_path_followup.md", body)

            findings = MODULE.lint_audit_artifacts(
                self._load_single(root, "docs/reviews/260419_1110_post_merge_audit_accepted_path_followup.md")
            )

        self.assertIn("audit_status_done_with_nonterminal_followup", {finding.code for finding in findings})

    def test_current_post_merge_audit_rejects_terminal_word_substrings_without_proof(self) -> None:
        cases = {
            "done_path": "docs/plans/260329_done_followup.md",
            "closed_path": "docs/plans/260329_closed_followup.md",
            "handled_path": "docs/followups/260329_handled_followup.md",
            "terminal_path": "docs/plans/260329_terminal_followup.md",
            "negated_done": "not done: docs/plans/260329_followup.md#resolution",
            "prose_only": "handled in prose without proof_ref",
        }
        for case_name, followup_plan in cases.items():
            with self.subTest(case_name=case_name):
                with temporary_git_root() as tmpdir:
                    root = Path(tmpdir).resolve()
                    body = self._current_green_audit_fixture().replace(
                        "- followup_plan: `N/A`\n",
                        f"- followup_plan: `{followup_plan}`\n",
                    )
                    self._write_markdown(root, f"docs/reviews/260419_1110_post_merge_audit_{case_name}.md", body)

                    findings = MODULE.lint_audit_artifacts(
                        self._load_single(root, f"docs/reviews/260419_1110_post_merge_audit_{case_name}.md")
                    )

                self.assertIn("audit_status_done_with_nonterminal_followup", {finding.code for finding in findings})

    def test_current_post_merge_audit_accepts_explicit_terminal_followup_proof(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            body = self._current_green_audit_fixture().replace(
                "- followup_plan: `N/A`\n",
                "- followup_plan: `done: docs/plans/260329_1812_followup.md#closed`\n",
            )
            self._write_markdown(root, "docs/reviews/260419_1110_post_merge_audit_terminal_followup_done.md", body)

            findings = MODULE.lint_audit_artifacts(
                self._load_single(root, "docs/reviews/260419_1110_post_merge_audit_terminal_followup_done.md")
            )

        self.assertEqual(findings, [])

    def test_current_post_merge_audit_draft_missing_source_can_remain_unconfirmed(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            body = self._current_green_audit_fixture()
            body = body.replace("- Lane synthesis source: `docs/code_reviews/260329_1800_example.md#Lane synthesis / aggregate verdict`\n", "- Lane synthesis source: `UNCONFIRMED`\n")
            body = body.replace("- source_lane: `reviewer_code_contracts`\n", "- source_lane: `UNCONFIRMED`\n")
            body = body.replace("- lane_finding_id: `contracts:B1`\n", "- lane_finding_id: `UNCONFIRMED`\n")
            body = body.replace("- synthesis_disposition: `accepted`\n", "- synthesis_disposition: `N/A`\n")
            body = body.replace("- canonical_ref: `docs/reviews/260329_1810_post_merge_audit_example.md#A1`\n", "- canonical_ref: `N/A`\n")
            body = body.replace("- audit_status: `done`\n", "- audit_status: `UNCONFIRMED`\n")
            body = body.replace("- Status: `✅ Done`\n", "- Status: `unknown`\n")
            self._write_markdown(root, "docs/reviews/260419_1110_post_merge_audit_unconfirmed_source.md", body)

            findings = MODULE.lint_audit_artifacts(
                self._load_single(root, "docs/reviews/260419_1110_post_merge_audit_unconfirmed_source.md")
            )

        self.assertEqual(findings, [])

    def test_current_post_merge_audit_requires_receipt_citations(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            broken = self._green_audit_fixture().replace("**Status:** ✅ Done\n", "**Status:** ✅ Done\n**Schema version:** review.v1\n")
            before, rest = broken.split("## Post-merge audit receipt citations\n", 1)
            _, after = rest.split("## Follow-ups\n", 1)
            broken = before + "## Follow-ups\n" + after
            self._write_markdown(
                root,
                "docs/reviews/260419_1111_post_merge_audit_missing_receipts.md",
                broken,
            )

            findings = MODULE.lint_audit_artifacts(
                self._load_single(root, "docs/reviews/260419_1111_post_merge_audit_missing_receipts.md")
            )

        codes = [finding.code for finding in findings]
        self.assertIn("missing_post_merge_receipt_citations", codes)
        self.assertIn("missing_post_merge_receipt_citation", codes)

    def test_current_post_merge_audit_requires_citation_tokens_inside_citation_section(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            broken = self._green_audit_fixture().replace("**Status:** ✅ Done\n", "**Status:** ✅ Done\n**Schema version:** review.v1\n")
            broken = broken.replace(
                "- Follow-up harvest triage/import receipt: `docs/reviews/260329_1809_plan_harvest_range_deadbee_feed123.md#follow-up-harvest-triageimport-receipt`.\n",
                "",
            )
            self._write_markdown(
                root,
                "docs/reviews/260419_1115_post_merge_audit_missing_one_receipt.md",
                broken,
            )

            findings = MODULE.lint_audit_artifacts(
                self._load_single(root, "docs/reviews/260419_1115_post_merge_audit_missing_one_receipt.md")
            )

        self.assertEqual([finding.code for finding in findings], ["missing_post_merge_receipt_citation"])
        self.assertIn("followup_harvest_triage_import", findings[0].message)

    def test_current_post_merge_audit_accepts_already_tracked_followup_pointer(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            body = self._green_audit_fixture().replace("**Status:** ✅ Done\n", "**Status:** ✅ Done\n**Schema version:** review.v1\n")
            body = body.replace(
                "- Follow-up harvest triage/import receipt: `docs/reviews/260329_1809_plan_harvest_range_deadbee_feed123.md#follow-up-harvest-triageimport-receipt`.\n",
                "- Follow-ups: already tracked elsewhere -> `docs/followups/process_followups_master.md#example-item`.\n",
            )
            self._write_markdown(
                root,
                "docs/reviews/260419_1116_post_merge_audit_followups_tracked_elsewhere.md",
                body,
            )

            findings = MODULE.lint_audit_artifacts(
                self._load_single(root, "docs/reviews/260419_1116_post_merge_audit_followups_tracked_elsewhere.md")
            )

        self.assertEqual(findings, [])

    def test_current_post_merge_audit_accepts_durable_closeout_refs_for_cleanup_claim(self) -> None:
        durable_refs = (
            "already_tracked_ref=docs/followups/process_followups_master.md#example-item",
            "manual_decision_ref=docs/plans/260419_1119_process_followups_decision.md#manual-followups-decision",
        )
        for index, durable_ref in enumerate(durable_refs, start=1):
            with self.subTest(durable_ref=durable_ref), temporary_git_root() as tmpdir:
                root = Path(tmpdir).resolve()
                body = self._green_audit_fixture().replace(
                    "**Status:** ✅ Done\n",
                    "**Status:** ✅ Done\n**Schema version:** review.v1\n",
                )
                body = body.replace(
                    "- Follow-up harvest triage/import receipt: `docs/reviews/260329_1809_plan_harvest_range_deadbee_feed123.md#follow-up-harvest-triageimport-receipt`.\n",
                    (
                        "- Follow-up harvest triage/import receipt: "
                        "`docs/reviews/260329_1809_plan_harvest_range_deadbee_feed123.md#follow-up-harvest-triageimport-receipt`; "
                        f"{durable_ref}.\n"
                    ),
                )
                body = body.replace(
                    "## Role assessment (censor receipts, if applicable)\n",
                    "- Cleanup readiness: handled followups are cleanup-ready.\n\n## Role assessment (censor receipts, if applicable)\n",
                )
                rel_path = f"docs/reviews/260419_1119_post_merge_audit_followups_durable_ref_{index}.md"
                self._write_markdown(root, rel_path, body)

                findings = MODULE.lint_audit_artifacts(self._load_single(root, rel_path))

                self.assertFalse(
                    any(finding.code == "missing_followups_launch_receipt_pointer" for finding in findings),
                    [finding.render() for finding in findings],
                )

    def test_current_post_merge_audit_rejects_weak_closeout_refs_for_cleanup_claim(self) -> None:
        weak_refs = (
            "already_tracked_ref=handled",
            "manual_decision_ref=TBD",
        )
        for index, weak_ref in enumerate(weak_refs, start=1):
            with self.subTest(weak_ref=weak_ref), temporary_git_root() as tmpdir:
                root = Path(tmpdir).resolve()
                body = self._green_audit_fixture().replace(
                    "**Status:** ✅ Done\n",
                    "**Status:** ✅ Done\n**Schema version:** review.v1\n",
                )
                body = body.replace(
                    "- Follow-up harvest triage/import receipt: `docs/reviews/260329_1809_plan_harvest_range_deadbee_feed123.md#follow-up-harvest-triageimport-receipt`.\n",
                    (
                        "- Follow-up harvest triage/import receipt: "
                        "`docs/reviews/260329_1809_plan_harvest_range_deadbee_feed123.md#follow-up-harvest-triageimport-receipt`; "
                        f"{weak_ref}.\n"
                    ),
                )
                body = body.replace(
                    "## Role assessment (censor receipts, if applicable)\n",
                    "- Cleanup readiness: handled followups are cleanup-ready.\n\n## Role assessment (censor receipts, if applicable)\n",
                )
                rel_path = f"docs/reviews/260419_112{index}_post_merge_audit_followups_weak_ref.md"
                self._write_markdown(root, rel_path, body)

                findings = MODULE.lint_audit_artifacts(self._load_single(root, rel_path))

                self.assertTrue(
                    any(finding.code == "missing_followups_launch_receipt_pointer" for finding in findings),
                    [finding.render() for finding in findings],
                )

    def test_current_post_merge_audit_rejects_malformed_closeout_refs_for_cleanup_claim(self) -> None:
        malformed_refs = (
            "manual_decision_ref=docs/plans/not_markdown.md.tmp",
            "already_tracked_ref=docs/followups/item.md:abc",
        )
        for index, malformed_ref in enumerate(malformed_refs, start=1):
            with self.subTest(malformed_ref=malformed_ref), temporary_git_root() as tmpdir:
                root = Path(tmpdir).resolve()
                body = self._green_audit_fixture().replace(
                    "**Status:** ✅ Done\n",
                    "**Status:** ✅ Done\n**Schema version:** review.v1\n",
                )
                body = body.replace(
                    "- Follow-up harvest triage/import receipt: `docs/reviews/260329_1809_plan_harvest_range_deadbee_feed123.md#follow-up-harvest-triageimport-receipt`.\n",
                    (
                        "- Follow-up harvest triage/import receipt: "
                        "`docs/reviews/260329_1809_plan_harvest_range_deadbee_feed123.md#follow-up-harvest-triageimport-receipt`; "
                        f"{malformed_ref}.\n"
                    ),
                )
                body = body.replace(
                    "## Role assessment (censor receipts, if applicable)\n",
                    "- Cleanup readiness: handled followups are cleanup-ready.\n\n## Role assessment (censor receipts, if applicable)\n",
                )
                rel_path = f"docs/reviews/260419_113{index}_post_merge_audit_followups_malformed_ref.md"
                self._write_markdown(root, rel_path, body)

                findings = MODULE.lint_audit_artifacts(self._load_single(root, rel_path))

                self.assertTrue(
                    any(finding.code == "missing_followups_launch_receipt_pointer" for finding in findings),
                    [finding.render() for finding in findings],
                )

    def test_current_post_merge_audit_constrains_already_tracked_elsewhere_phrase(self) -> None:
        cases = (
            ("already tracked elsewhere", True),
            ("already tracked elsewhere in docs/followups/process_followups_master.md#example-item", False),
        )
        for index, (phrase, should_fail) in enumerate(cases, start=1):
            with self.subTest(phrase=phrase), temporary_git_root() as tmpdir:
                root = Path(tmpdir).resolve()
                body = self._green_audit_fixture().replace(
                    "**Status:** ✅ Done\n",
                    "**Status:** ✅ Done\n**Schema version:** review.v1\n",
                )
                body = body.replace(
                    "- Follow-up harvest triage/import receipt: `docs/reviews/260329_1809_plan_harvest_range_deadbee_feed123.md#follow-up-harvest-triageimport-receipt`.\n",
                    (
                        "- Follow-up harvest triage/import receipt: "
                        "`docs/reviews/260329_1809_plan_harvest_range_deadbee_feed123.md#follow-up-harvest-triageimport-receipt`; "
                        f"{phrase}.\n"
                    ),
                )
                body = body.replace(
                    "## Role assessment (censor receipts, if applicable)\n",
                    "- Cleanup readiness: handled followups are cleanup-ready.\n\n## Role assessment (censor receipts, if applicable)\n",
                )
                rel_path = f"docs/reviews/260419_114{index}_post_merge_audit_followups_phrase_ref.md"
                self._write_markdown(root, rel_path, body)

                findings = MODULE.lint_audit_artifacts(self._load_single(root, rel_path))

                has_finding = any(finding.code == "missing_followups_launch_receipt_pointer" for finding in findings)
                self.assertEqual(has_finding, should_fail, [finding.render() for finding in findings])

    def test_current_post_merge_audit_cleanup_claim_requires_followup_launch_pointer(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            body = self._green_audit_fixture().replace("**Status:** ✅ Done\n", "**Status:** ✅ Done\n**Schema version:** review.v1\n")
            body = body.replace(
                "- Follow-up harvest triage/import receipt: `docs/reviews/260329_1809_plan_harvest_range_deadbee_feed123.md#follow-up-harvest-triageimport-receipt`.\n",
                "",
            )
            body = body.replace(
                "## Role assessment (censor receipts, if applicable)\n",
                "- Cleanup readiness: handled followups are cleanup-ready.\n\n## Role assessment (censor receipts, if applicable)\n",
            )
            self._write_markdown(
                root,
                "docs/reviews/260419_1117_post_merge_audit_cleanup_claim_without_followups_launch.md",
                body,
            )

            findings = MODULE.lint_audit_artifacts(
                self._load_single(root, "docs/reviews/260419_1117_post_merge_audit_cleanup_claim_without_followups_launch.md")
            )

        codes = [finding.code for finding in findings]
        self.assertIn("missing_post_merge_receipt_citation", codes)
        self.assertIn("missing_followups_launch_receipt_pointer", codes)

    def test_current_post_merge_audit_cleanup_claim_requires_range_or_manual_followup_proof(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            body = self._green_audit_fixture().replace("**Status:** ✅ Done\n", "**Status:** ✅ Done\n**Schema version:** review.v1\n")
            body = body.replace(
                "## Role assessment (censor receipts, if applicable)\n",
                "- Cleanup readiness: handled followups are cleanup-ready.\n\n## Role assessment (censor receipts, if applicable)\n",
            )
            self._write_markdown(
                root,
                "docs/reviews/260419_1118_post_merge_audit_cleanup_claim_without_range_proof.md",
                body,
            )

            findings = MODULE.lint_audit_artifacts(
                self._load_single(root, "docs/reviews/260419_1118_post_merge_audit_cleanup_claim_without_range_proof.md")
            )

        codes = [finding.code for finding in findings]
        self.assertIn("missing_followups_launch_receipt_pointer", codes)

    def test_versionless_post_merge_audit_is_legacy(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(root, "docs/reviews/260419_1113_post_merge_audit_schema_legacy.md", self._green_audit_fixture())

            findings = MODULE.lint_audit_artifacts(
                self._load_single(root, "docs/reviews/260419_1113_post_merge_audit_schema_legacy.md")
            )

        self.assertEqual(findings, [])

    def test_wrong_post_merge_audit_schema_version_is_reported(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/reviews/260419_1114_post_merge_audit_schema_unsupported.md",
                self._green_audit_fixture().replace("**Status:** ✅ Done\n", "**Status:** ✅ Done\n**Schema version:** followups.v1\n"),
            )

            findings = MODULE.lint_audit_artifacts(
                self._load_single(root, "docs/reviews/260419_1114_post_merge_audit_schema_unsupported.md")
            )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "unsupported_schema_version")
        self.assertIn("Unsupported review schema version", findings[0].message)

    def _write_runtime_visual_source(self, root: Path, *, green: bool) -> None:
        plan_rel = "docs/plans/260329_1759_runtime_visual.md"
        review_rel = "docs/code_reviews/260329_1800_example.md"
        payload = {
            "schema_version": "review_visual_lane_contract.v1",
            "availability_state": "available",
            "runtime_ui_kind": "web",
            "profile_id": "default",
            "source_refs": ["docs/smoke_visual.md", "docs/testing_runbook.md"],
            "changed_path_evidence": [],
            "mandatory_modes": ["primary", "secondary"],
            "comparator_command": "./scripts/run_visual_check.sh --repeat 2",
            "comparator_claim": "mechanical",
            "baseline_update_allowed": False,
            "human_commands_by_mode": {"primary": "./scripts/human.sh --mode primary", "secondary": "./scripts/human.sh --mode secondary"},
            "human_index_paths_by_mode": {"primary": ".tmp/primary/index.md", "secondary": ".tmp/secondary/index.md"},
            "human_output_roots_by_mode": {"primary": ".tmp/primary", "secondary": ".tmp/secondary"},
            "complete_index_required": True,
            "durable_review_asset_root": "docs/code_reviews/assets/260329_1800_example/",
            "reason": "repo_backed_visual_lane",
        }
        self._write_markdown(
            root,
            plan_rel,
            "# Plan\n\n## Review visual lane contract\n\n"
            + MODULE.review_artifact_lint.review_visual_lane_contract.render_materialized_contract(payload)
            + "\n",
        )
        visual = "- Durable screenshots: N/A\n"
        if green:
            asset_root = root / "docs" / "code_reviews" / "assets" / "260329_1800_example"
            asset_root.mkdir(parents=True, exist_ok=True)
            (asset_root / "primary.png").write_bytes(b"png")
            (asset_root / "secondary.png").write_bytes(b"png")
            visual = dedent(
                """\
                - Comparator command: `./scripts/run_visual_check.sh --repeat 2`
                - Comparator claim: `mechanical`
                - Comparator result: `pass`
                - Capture status: `complete`
                - Complete index inspected: `yes`
                - Design verdict: `no_findings`
                - Mandatory modes: `primary, secondary`
                - Human index (primary): `.tmp/primary/index.md`
                - Human index (secondary): `.tmp/secondary/index.md`
                - Durable asset (primary): `docs/code_reviews/assets/260329_1800_example/primary.png`
                - Durable asset (secondary): `docs/code_reviews/assets/260329_1800_example/secondary.png`
                """
            )
        source = self._review_source_fixture().replace(
            "**Status:** ✅ OK\n", f"**Spec:** {plan_rel}\n**Status:** ✅ OK\n"
        )
        source += "\n## Визуальные доказательства\n" + visual
        self._write_markdown(root, review_rel, source)

    def test_audit_done_cannot_override_red_runtime_visual_source(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            audit_rel = "docs/reviews/260329_1810_post_merge_audit_example.md"
            self._write_markdown(root, audit_rel, self._current_green_audit_fixture())
            self._write_runtime_visual_source(root, green=False)
            findings = MODULE.lint_audit_artifacts(self._load_single(root, audit_rel))
        self.assertIn("audit_status_done_conflicts_with_visual_evidence", {finding.code for finding in findings})

    def test_audit_done_accepts_green_runtime_visual_source(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            audit_rel = "docs/reviews/260329_1810_post_merge_audit_example.md"
            self._write_markdown(root, audit_rel, self._current_green_audit_fixture())
            self._write_runtime_visual_source(root, green=True)
            findings = MODULE.lint_audit_artifacts(self._load_single(root, audit_rel))
        self.assertNotIn("audit_status_done_conflicts_with_visual_evidence", {finding.code for finding in findings})


if __name__ == "__main__":
    unittest.main()

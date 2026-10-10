from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from textwrap import dedent


MODULE_PATH = Path(__file__).with_name("censor_receipts_harvest.py")
SPEC = importlib.util.spec_from_file_location("censor_receipts_harvest", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(text), encoding="utf-8")


def _run_cli(args: list[str]) -> tuple[int, str]:
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        exit_code = MODULE.main(args)
    return exit_code, stdout.getvalue()


def _payload(
    plan: Path,
    *review_artifacts: Path,
    censor_role: str | None = None,
    handoff_status: str | None = None,
    censor_dispatch_id: str | None = None,
) -> tuple[int, dict[str, object]]:
    args = ["--plan", str(plan)]
    for artifact in review_artifacts:
        args.extend(["--review-artifact", str(artifact)])
    if censor_role:
        args.extend(["--censor-role", censor_role])
    if handoff_status:
        args.extend(["--handoff-status", handoff_status])
    if censor_dispatch_id:
        args.extend(["--censor-dispatch-id", censor_dispatch_id])
    args.extend(["--format", "json"])
    exit_code, stdout = _run_cli(args)
    return exit_code, json.loads(stdout)


def _complete_censor_row(
    role: str,
    handoff_status: str,
    timestamp: str = "02:01",
    censor_dispatch_id: str | None = None,
) -> str:
    dispatch_field = (
        f"Censor dispatch id: {censor_dispatch_id}. " if censor_dispatch_id else ""
    )
    return (
        f"- [2026-07-11 {timestamp} MSK] ({role} CENSOR) OK: {handoff_status} validated; "
        f"current=true. {dispatch_field}Observations: Second opinion: NO FINDINGS. Addendum (new angle): "
        "checked the role-event boundary. Context reconciliation: current handoff matches plan. "
        "Counterfactuals considered: later role events could leave this receipt stale; exact matching "
        "must decide that. Fixes: none. Artifacts opened: `PLAN_PATH`. Review verdict seen: no live "
        "review artifact. Blocker IDs considered: `N/A`. Role-owned finding: none. Reconciliation: "
        "no live blocker. Final censor verdict: OK."
    )


class CensorReceiptsHarvestTests(unittest.TestCase):
    def test_complete_no_live_receipt_is_noise_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/no_findings.md"
            _write(
                plan,
                """\
                # Plan

                ## Evidence
                - [2026-05-08 02:00 MSK] (Coder CENSOR) OK. Artifacts opened: `PLAN_PATH`; `scripts/censor_receipts_harvest.py`. Review verdict seen: no live review artifact. Blocker IDs considered: `N/A (why=no live review artifact)`. Role-owned finding: none. Reconciliation: no live blocker. Final censor verdict: OK.
                """,
            )

            exit_code, payload = _payload(plan)

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            set(payload),
            {
                "inputs",
                "censor_evidence_lint",
                "summary",
                "receipts",
                "findings",
                "warnings",
                "unconfirmed_reasons",
            },
        )
        summary = payload["summary"]
        self.assertEqual(summary["complete_receipt_count"], 1)
        self.assertEqual(summary["role_quality"]["noise/no-op"], 1)
        self.assertEqual(payload["receipts"][0]["fields"]["Final censor verdict"], "OK")
        self.assertEqual(payload["findings"][0]["review_verdict"], "no live review artifact")
        self.assertEqual(payload["findings"][0]["final_censor_verdict"], "OK")
        self.assertEqual(payload["findings"][0]["category"], "noise/no-op")

    def test_supported_censor_role_tags_preserve_existing_classification(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/supported_roles.md"
            rows = "\n".join(
                f"- [2026-07-11 01:00 MSK] ({role} CENSOR) OK. "
                "Artifacts opened: `PLAN_PATH`. Review verdict seen: no live review artifact. "
                "Blocker IDs considered: `N/A`. Role-owned finding: none. "
                "Reconciliation: no live blocker. Final censor verdict: OK."
                for role in MODULE.SUPPORTED_CENSOR_ROLES
            )
            _write(plan, f"# Plan\n\n## Evidence\n{rows}\n")

            exit_code, payload = _payload(plan)

        self.assertEqual(exit_code, 0)
        self.assertEqual([receipt["role"] for receipt in payload["receipts"]], list(MODULE.SUPPORTED_CENSOR_ROLES))
        self.assertTrue(all(receipt["invalid_reasons"] == [] for receipt in payload["receipts"]))
        self.assertEqual(payload["summary"]["role_quality"]["UNCONFIRMED"], 0)

    def test_unsupported_censor_role_tag_is_unconfirmed_and_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/unsupported_role.md"
            _write(
                plan,
                """\
                # Plan

                ## Evidence
                - [2026-07-11 01:01 MSK] (Wizard CENSOR) OK: Ready for Review validated; current=true. Observations: Second opinion: FOUND DEFECTS. Addendum (new angle): invalid role checked. Context reconciliation: handoff is current. Fixes: none. Artifacts opened: `PLAN_PATH`. Review verdict seen: no live review artifact. Blocker IDs considered: `N/A`. Role-owned finding: none. Reconciliation: no live blocker. Final censor verdict: OK.
                """,
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Wizard",
                handoff_status="Ready for Review",
            )

        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["summary"]["role_quality"]["UNCONFIRMED"], 1)
        self.assertEqual(payload["findings"][0]["category"], "UNCONFIRMED")
        self.assertIn("unsupported_censor_role_tag:Wizard", payload["receipts"][0]["invalid_reasons"])
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "incomplete")
        self.assertEqual(lint["reason_code"], "missing_or_invalid_fields")
        self.assertIn("unsupported_censor_role_tag:Wizard", lint["invalid_reasons"])

    def test_malformed_supported_censor_role_tag_is_selected_and_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/malformed_role.md"
            _write(
                plan,
                """\
                # Plan

                ## Evidence
                - [2026-07-11 01:02 MSK] (Coder CENSOR extra) OK: Ready for Review validated; current=true. Observations: Second opinion: FOUND DEFECTS. Addendum (new angle): malformed role checked. Context reconciliation: handoff is current. Fixes: none. Artifacts opened: `PLAN_PATH`. Review verdict seen: no live review artifact. Blocker IDs considered: `N/A`. Role-owned finding: none. Reconciliation: no live blocker. Final censor verdict: OK.
                """,
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Coder",
                handoff_status="Ready for Review",
            )
        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["receipts"][0]["role"], "Coder")
        self.assertEqual(payload["receipts"][0]["invalid_reasons"], ["malformed_censor_role_tag"])
        self.assertEqual(payload["summary"]["role_quality"]["UNCONFIRMED"], 1)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "incomplete")
        self.assertEqual(lint["reason_code"], "missing_or_invalid_fields")
        self.assertIn("malformed_censor_role_tag", lint["invalid_reasons"])

    def test_live_blocker_with_role_finding_is_helped(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/helped.md"
            review = root / "docs/code_reviews/helped.md"
            _write(
                plan,
                """\
                # Plan

                ## Evidence
                - [2026-05-08 02:10 MSK] (Planner CENSOR) OK. Artifacts opened: `PLAN_PATH`; `docs/code_reviews/helped.md`. Review verdict seen: current blocker verdict S1 blocker. Blocker IDs considered: `docs/code_reviews/helped.md#B1`. Role-owned finding: parser handoff gap fixed. Reconciliation: live blocker belongs here. Final censor verdict: FOUND GAP.
                """,
            )
            _write(review, "# Review\n\n## S1 Blocker\n### B1) Parser handoff gap\n")

            exit_code, payload = _payload(plan, review)

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["summary"]["role_quality"]["helped"], 1)
        self.assertEqual(payload["findings"][0]["category"], "helped")

    def test_live_blocker_without_role_finding_is_missed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/missed.md"
            _write(
                plan,
                """\
                # Plan

                ## Evidence
                - [2026-05-08 02:20 MSK] (Coder CENSOR) OK. Artifacts opened: `PLAN_PATH`; `docs/code_reviews/missed.md`. Review verdict seen: current blocker verdict S1 blocker. Blocker IDs considered: `docs/code_reviews/missed.md#B2`. Role-owned finding: none. Reconciliation: live blocker belongs here. Final censor verdict: OK.
                """,
            )

            exit_code, payload = _payload(plan)

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["summary"]["role_quality"]["missed live blocker"], 1)
        self.assertEqual(payload["findings"][0]["category"], "missed live blocker")
        self.assertEqual(
            payload["findings"][0]["reason"],
            "exact current negative signal with no role-owned finding",
        )

    def test_current_blocker_without_literal_negative_signal_is_unconfirmed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/ambiguous_current.md"
            _write(
                plan,
                """\
                # Plan

                ## Evidence
                - [2026-05-08 02:25 MSK] (Coder CENSOR) OK. Artifacts opened: `PLAN_PATH`; `docs/code_reviews/current.md`. Review verdict seen: current blocker verdict S1 blocker. Blocker IDs considered: `docs/code_reviews/current.md#B2`. Role-owned finding: none. Reconciliation: blocker context mentioned but ownership is unclear. Final censor verdict: OK.
                """,
            )

            exit_code, payload = _payload(plan)

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["summary"]["role_quality"]["missed live blocker"], 0)
        self.assertEqual(payload["summary"]["role_quality"]["UNCONFIRMED"], 1)
        self.assertEqual(payload["findings"][0]["category"], "UNCONFIRMED")
        self.assertEqual(
            payload["findings"][0]["reason"],
            "live blocker wording without exact current negative signal",
        )
        self.assertEqual(payload["summary"]["unconfirmed_count"], 1)
        self.assertIn(
            "ambiguous live blocker wording",
            payload["unconfirmed_reasons"][0],
        )

    def test_contextual_blocker_prose_with_no_live_marker_is_noise(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/contextual_no_live.md"
            _write(
                plan,
                """\
                # Plan

                ## Evidence
                - [2026-05-08 02:26 MSK] (Coder CENSOR) OK. Artifacts opened: `PLAN_PATH`; `docs/code_reviews/old.md`. Review verdict seen: no live review artifact, historical note mentions S1 blocker. Blocker IDs considered: `docs/code_reviews/old.md#B1` (historical anchor only). Role-owned finding: none. Reconciliation: no live blocker; historical anchor only. Final censor verdict: OK.
                """,
            )

            exit_code, payload = _payload(plan)

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["summary"]["role_quality"]["noise/no-op"], 1)
        self.assertEqual(payload["summary"]["role_quality"]["missed live blocker"], 0)
        self.assertEqual(payload["summary"]["role_quality"]["UNCONFIRMED"], 0)

    def test_historical_artifact_does_not_become_live_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/historical.md"
            _write(
                plan,
                """\
                # Plan

                ## Evidence
                - [2026-05-08 02:30 MSK] (Architect CENSOR) OK. Artifacts opened: `PLAN_PATH`; `docs/code_reviews/old.md`. Review verdict seen: OK historical anchor only. Blocker IDs considered: `docs/code_reviews/old.md#B1`. Role-owned finding: none. Reconciliation: historical anchor only. Final censor verdict: OK.
                """,
            )

            exit_code, payload = _payload(plan)

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["summary"]["role_quality"]["noise/no-op"], 1)
        self.assertEqual(payload["summary"]["role_quality"]["missed live blocker"], 0)

    def test_partial_receipt_is_receipt_missing_and_unconfirmed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/partial.md"
            _write(
                plan,
                """\
                # Plan

                ## Evidence
                - [2026-05-08 02:40 MSK] (Coder CENSOR) OK. Artifacts opened: `PLAN_PATH`. Review verdict seen: no live review artifact.
                """,
            )

            exit_code, payload = _payload(plan)

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["summary"]["partial_receipt_count"], 1)
        self.assertEqual(payload["summary"]["role_quality"]["receipt missing"], 1)
        self.assertEqual(payload["findings"][0]["category"], "receipt missing")
        self.assertTrue(payload["unconfirmed_reasons"])

    def test_malformed_current_range_receipt_exits_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/current_partial.md"
            _write(
                plan,
                """\
                # Plan

                ## Evidence
                - [2026-05-08 02:50 MSK] (Planner CENSOR) current-range receipt. Review verdict seen: current blocker verdict S1 blocker. Blocker IDs considered: `docs/code_reviews/live.md#B1`.
                """,
            )

            exit_code, payload = _payload(plan)

        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["summary"]["malformed_current_range_count"], 1)
        self.assertEqual(payload["summary"]["role_quality"]["receipt missing"], 1)

    def test_review_artifact_role_assessment_block_is_extracted(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/empty.md"
            review = root / "docs/reviews/audit.md"
            _write(plan, "# Plan\n")
            _write(
                review,
                """\
                # Review

                ## Role assessment (censor receipts, if applicable)
                ### R1) sample / Coder
                - Receipt source: `docs/plans/sample.md:25`
                - Artifacts opened: `PLAN_PATH`; `docs/code_reviews/live.md`
                - Review verdict seen: current blocker verdict S1 blocker
                - Blocker IDs considered: `docs/code_reviews/live.md#B1`
                - Role-owned finding: review blocker triaged
                - Reconciliation: live blocker belongs here
                - Final censor verdict: FOUND GAP
                - Assessment: helped
                """,
            )

            exit_code, payload = _payload(plan, review)

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["receipts"][0]["source"], "review_artifact")
        self.assertEqual(payload["receipts"][0]["role"], "Coder")
        self.assertEqual(payload["summary"]["role_quality"]["helped"], 1)

    def test_deadlock_addendum_fields_are_extracted(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/deadlock.md"
            _write(
                plan,
                """\
                # Plan

                ## Evidence
                - [2026-05-08 03:05 MSK] (Coder CENSOR) OK. Artifacts opened: `PLAN_PATH`; `docs/code_reviews/live.md`. Review verdict seen: current blocker verdict S1 blocker. Blocker IDs considered: `docs/code_reviews/live.md#B1`. Role-owned finding: repeated rerun loop classified. Reconciliation: live blocker belongs here. Final censor verdict: FOUND GAP. Loop signal: repeated same-status / same-blocker loop. Root cause class: same-contract reroute. Why previous rerun did not break the loop: rerun reused stale proof. Extraordinary action: rollback to Architect response.
                """,
            )

            exit_code, payload = _payload(plan)

        self.assertEqual(exit_code, 0)
        deadlock = payload["receipts"][0]["deadlock_fields"]
        self.assertEqual(deadlock["Loop signal"], "repeated same-status / same-blocker loop")
        self.assertEqual(deadlock["Root cause class"], "same-contract reroute")
        self.assertEqual(deadlock["Why previous rerun did not break the loop"], "rerun reused stale proof")
        self.assertEqual(deadlock["Extraordinary action"], "rollback to Architect response")

    def test_text_output_names_all_role_quality_categories(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/text.md"
            _write(
                plan,
                """\
                # Plan

                ## Evidence
                - [2026-05-08 03:00 MSK] (Coder CENSOR) OK. Artifacts opened: `PLAN_PATH`. Review verdict seen: no live review artifact. Blocker IDs considered: `N/A`. Role-owned finding: none. Reconciliation: no live blocker. Final censor verdict: OK.
                """,
            )

            exit_code, stdout = _run_cli(["--plan", str(plan), "--format", "text"])

        self.assertEqual(exit_code, 0)
        for category in MODULE.ROLE_QUALITY_CATEGORIES:
            self.assertIn(category, stdout)
        self.assertIn("review_verdict=no live review artifact", stdout)
        self.assertIn("final_censor_verdict=OK", stdout)
        self.assertIn("category=noise/no-op", stdout)

    def test_censor_evidence_lint_complete_current_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/complete_censor_lint.md"
            _write(
                plan,
                """\
                # Plan

                ## Evidence
                - [2026-06-23 02:00 MSK] (Coder CENSOR) OK: Ready for Review validated. Observations: Second opinion: FOUND DEFECTS. Addendum (new angle): checked helper and prompt lanes. Context reconciliation: current handoff matches plan. Fixes: added missing tests. Artifacts opened: `PLAN_PATH`. Review verdict seen: no live review artifact. Blocker IDs considered: `N/A`. Role-owned finding: tests missing. Reconciliation: no live blocker. Final censor verdict: OK.
                """,
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Coder",
                handoff_status="Ready for Review",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "complete")
        self.assertEqual(lint["reason_code"], "complete_current_receipt")
        self.assertEqual(lint["missing_fields"], [])
        self.assertEqual(payload["receipts"][0]["parse_status"], "complete")

    def test_censor_evidence_lint_no_findings_requires_counterfactuals(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/no_counterfactuals.md"
            _write(
                plan,
                """\
                # Plan

                ## Evidence
                - [2026-06-23 02:01 MSK] (Planner CENSOR) OK: Ready for Coder validated. Observations: Second opinion: NO FINDINGS. Addendum (new angle): checked alternate lane. Context reconciliation: current handoff matches plan. Fixes: none. Artifacts opened: `PLAN_PATH`. Review verdict seen: no live review artifact. Blocker IDs considered: `N/A`. Role-owned finding: none. Reconciliation: no live blocker. Final censor verdict: OK.
                """,
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Planner",
                handoff_status="Ready for Coder",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "incomplete")
        self.assertIn("Counterfactuals considered", lint["missing_fields"])
        self.assertIn("no_findings_missing_counterfactuals", lint["invalid_reasons"])

    def test_censor_evidence_lint_no_findings_requires_fixes_label(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/no_fixes.md"
            _write(
                plan,
                """\
                # Plan

                ## Evidence
                - [2026-06-23 02:01 MSK] (Planner CENSOR) OK: Ready for Coder validated. Observations: Second opinion: NO FINDINGS. Addendum (new angle): checked alternate lane. Context reconciliation: current handoff matches plan. Counterfactuals considered: missing fixes label could make a NO FINDINGS row non-machine-readable; helper must reject that. Artifacts opened: `PLAN_PATH`. Review verdict seen: no live review artifact. Blocker IDs considered: `N/A`. Role-owned finding: none. Reconciliation: no live blocker. Final censor verdict: OK.
                """,
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Planner",
                handoff_status="Ready for Coder",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "incomplete")
        self.assertEqual(lint["reason_code"], "missing_or_invalid_fields")
        self.assertEqual(lint["missing_fields"], ["Fixes"])

    def test_censor_evidence_lint_requires_structured_receipt_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/missing_structured_labels.md"
            _write(
                plan,
                """\
                # Plan

                ## Evidence
                - [2026-06-23 02:01 MSK] (Coder CENSOR) OK: Ready for Review validated. Observations: Second opinion: FOUND DEFECTS. Addendum (new angle): checked helper and prompt lanes. Context reconciliation: current handoff matches plan. Fixes: added missing tests.
                """,
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Coder",
                handoff_status="Ready for Review",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "incomplete")
        self.assertEqual(lint["reason_code"], "missing_or_invalid_fields")
        self.assertIn("Artifacts opened", lint["missing_fields"])
        self.assertIn("Review verdict seen", lint["missing_fields"])
        self.assertIn("Final censor verdict", lint["missing_fields"])

    def test_censor_evidence_lint_current_receipt_stale_after_later_matching_delta(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/stale_current_receipt.md"
            _write(
                plan,
                """\
                # Plan

                ## Evidence
                - [2026-06-23 02:01 MSK] (Coder CENSOR) OK: Ready for Review validated; current=true. Observations: Second opinion: NO FINDINGS. Addendum (new angle): checked helper and prompt lanes. Context reconciliation: current handoff matches plan. Counterfactuals considered: stale current receipt could hide later delta, not confirmed. Fixes: none. Artifacts opened: `PLAN_PATH`. Review verdict seen: no live review artifact. Blocker IDs considered: `N/A`. Role-owned finding: none. Reconciliation: no live blocker. Final censor verdict: OK.
                - [2026-06-23 02:02 MSK] (Coder) Fixed review blocker for Ready for Review. Status moved to `Ready for Review`.
                """,
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Coder",
                handoff_status="Ready for Review",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "incomplete")
        self.assertEqual(lint["reason_code"], "missing_current_receipt")
        self.assertIn("stale_current_receipt_after_later_matching_event", lint["invalid_reasons"])

    def test_suffixed_planner_event_invalidates_current_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/planner_suffix_watermark.md"
            _write(
                plan,
                "\n".join(
                    [
                        "# Plan",
                        "",
                        "## Evidence",
                        _complete_censor_row("Planner", "Ready for Coder"),
                        "- [2026-07-11 02:02 MSK] (Planner re-finalize, Planner finalize -> Ready for Coder) Material contract changed.",
                    ]
                ),
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Planner",
                handoff_status="Ready for Coder",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "incomplete")
        self.assertEqual(lint["reason_code"], "missing_current_receipt")
        self.assertIn("stale_current_receipt_after_later_matching_event", lint["invalid_reasons"])
        self.assertIn("Planner re-finalize", lint["selected_excerpt"])

    def test_suffixed_coder_event_invalidates_current_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/coder_suffix_watermark.md"
            _write(
                plan,
                "\n".join(
                    [
                        "# Plan",
                        "",
                        "## Evidence",
                        _complete_censor_row("Coder", "Ready for Review"),
                        "- [2026-07-11 02:02 MSK] (Coder B1 target verification, Ready for Coder -> Ready for Review) Target changed.",
                    ]
                ),
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Coder",
                handoff_status="Ready for Review",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "incomplete")
        self.assertEqual(lint["reason_code"], "missing_current_receipt")
        self.assertIn("stale_current_receipt_after_later_matching_event", lint["invalid_reasons"])
        self.assertIn("Coder B1 target verification", lint["selected_excerpt"])

    def test_near_match_lowercase_unknown_and_prose_role_tags_do_not_invalidate(self) -> None:
        cases = (
            ("Planner", "Ready for Coder", "(Plannerish re-finalize) Ready for Coder"),
            ("Planner", "Ready for Coder", "(planner re-finalize) Ready for Coder"),
            ("Planner", "Ready for Coder", "(Wizard re-finalize) Ready for Coder"),
            ("Coder", "Ready for Review", "(CoderB1 target verification) Ready for Review"),
            ("Planner", "Ready for Coder", "Note mentions (Planner re-finalize) Ready for Coder"),
        )
        for role, handoff_status, event in cases:
            with self.subTest(event=event), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                plan = root / "docs/plans/non_role_event.md"
                _write(
                    plan,
                    "\n".join(
                        [
                            "# Plan",
                            "",
                            "## Evidence",
                            _complete_censor_row(role, handoff_status),
                            f"- [2026-07-11 02:02 MSK] {event}. Material prose only.",
                        ]
                    ),
                )

                exit_code, payload = _payload(
                    plan,
                    censor_role=role,
                    handoff_status=handoff_status,
                )

            self.assertEqual(exit_code, 0)
            lint = payload["censor_evidence_lint"]
            self.assertEqual(lint["state"], "complete")
            self.assertEqual(lint["reason_code"], "complete_current_receipt")

    def test_unrelated_role_or_status_does_not_invalidate_current_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/unrelated_role_status.md"
            _write(
                plan,
                "\n".join(
                    [
                        "# Plan",
                        "",
                        "## Evidence",
                        _complete_censor_row("Planner", "Ready for Coder"),
                        "- [2026-07-11 02:02 MSK] (Coder B1 target verification) Ready for Coder material change.",
                        "- [2026-07-11 02:03 MSK] (Planner re-finalize) Ready for Review material change.",
                    ]
                ),
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Planner",
                handoff_status="Ready for Coder",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "complete")
        self.assertEqual(lint["reason_code"], "complete_current_receipt")

    def test_malformed_censor_tag_never_falls_back_to_generic_role_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/malformed_censor_no_fallback.md"
            _write(
                plan,
                "\n".join(
                    [
                        "# Plan",
                        "",
                        "## Evidence",
                        _complete_censor_row("Coder", "Ready for Review"),
                        "- [2026-07-11 02:02 MSK] (Coder CENSOR extra) Ready for Review malformed receipt.",
                    ]
                ),
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Coder",
                handoff_status="Ready for Review",
            )

        self.assertEqual(exit_code, 2)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "incomplete")
        self.assertEqual(lint["reason_code"], "missing_or_invalid_fields")
        self.assertIn("malformed_censor_role_tag", lint["invalid_reasons"])
        self.assertTrue(
            any(
                receipt["invalid_reasons"] == ["malformed_censor_role_tag"]
                for receipt in payload["receipts"]
            )
        )

    def test_inline_censor_reference_in_role_event_is_context_not_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/inline_censor_reference.md"
            _write(
                plan,
                "\n".join(
                    [
                        "# Plan",
                        "",
                        "## Evidence",
                        _complete_censor_row("Planner", "Ready for Coder"),
                        "- [2026-07-11 02:02 MSK] (Planner finalize, Planner intake -> Planner finalize) A fresh supervised (Planner CENSOR) receipt is still required before Ready for Coder.",
                    ]
                ),
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Planner",
                handoff_status="Ready for Coder",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "incomplete")
        self.assertEqual(lint["reason_code"], "missing_current_receipt")
        self.assertIn("stale_current_receipt_after_later_matching_event", lint["invalid_reasons"])
        self.assertIn("Planner finalize", lint["selected_excerpt"])
        self.assertEqual(payload["summary"]["receipt_count"], 1)

    def test_censor_evidence_lint_selects_latest_current_true_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/latest_current_receipt.md"
            _write(
                plan,
                """\
                # Plan

                ## Evidence
                - [2026-06-23 02:01 MSK] (Coder CENSOR) OK: Ready for Review validated; current=true. Observations: Second opinion: NO FINDINGS. Addendum (new angle): checked old helper lane. Context reconciliation: old handoff matched plan. Counterfactuals considered: old current marker could be stale, not confirmed then. Fixes: none. Artifacts opened: `PLAN_PATH`. Review verdict seen: no live review artifact. Blocker IDs considered: `N/A`. Role-owned finding: none. Reconciliation: no live blocker. Final censor verdict: OK.
                - [2026-06-23 02:02 MSK] (Coder CENSOR) OK: Ready for Review validated; current=true. Observations: Second opinion: NO FINDINGS. Addendum (new angle): checked fresh helper lane. Context reconciliation: fresh handoff matches plan. Counterfactuals considered: older current marker could make selector ambiguous, not confirmed. Fixes: none. Artifacts opened: `PLAN_PATH`. Review verdict seen: no live review artifact. Blocker IDs considered: `N/A`. Role-owned finding: none. Reconciliation: no live blocker. Final censor verdict: OK.
                """,
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Coder",
                handoff_status="Ready for Review",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "complete")
        self.assertEqual(lint["reason_code"], "complete_current_receipt")
        self.assertIn("02:02 MSK", lint["selected_excerpt"])

    def test_no_selector_preserves_legacy_current_marker_outside_preamble(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = Path(tmpdir) / "docs/plans/legacy_current_marker.md"
            old_receipt = _complete_censor_row(
                "Coder",
                "Ready for Review",
                timestamp="02:01",
            ).replace("current=true. ", "", 1)
            current_receipt = _complete_censor_row(
                "Coder",
                "Ready for Review",
                timestamp="02:02",
            ).replace("current=true. Observations:", "Observations: current=true.", 1)
            _write(
                plan,
                "# Plan\n\n## Evidence\n" + old_receipt + "\n" + current_receipt + "\n",
            )

            _, payload = _payload(
                plan,
                censor_role="Coder",
                handoff_status="Ready for Review",
            )

        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "complete")
        self.assertEqual(lint["reason_code"], "complete_current_receipt")
        self.assertIn("02:02 MSK", lint["selected_excerpt"])

    def test_censor_evidence_lint_selects_newer_unmarked_receipt_after_current_true(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/current_then_newer_unmarked.md"
            _write(
                plan,
                """\
                # Plan

                ## Evidence
                - [2026-06-23 02:01 MSK] (Coder CENSOR) OK: Ready for Review validated; current=true. Observations: Second opinion: NO FINDINGS. Addendum (new angle): checked old helper lane. Context reconciliation: old handoff matched plan. Counterfactuals considered: newer receipt could supersede this one, not confirmed then. Fixes: none. Artifacts opened: `PLAN_PATH`. Review verdict seen: no live review artifact. Blocker IDs considered: `N/A`. Role-owned finding: none. Reconciliation: no live blocker. Final censor verdict: OK.
                - [2026-06-23 02:02 MSK] (Coder CENSOR) OK: Ready for Review validated. Observations: Second opinion: FOUND DEFECTS. Addendum (new angle): checked fresh helper lane. Context reconciliation: fresh handoff supersedes old current marker. Fixes: selected newer receipt. Artifacts opened: `PLAN_PATH`. Review verdict seen: no live review artifact. Blocker IDs considered: `N/A`. Role-owned finding: newer unmarked receipt selected. Reconciliation: no live blocker. Final censor verdict: OK.
                """,
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Coder",
                handoff_status="Ready for Review",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "complete")
        self.assertEqual(lint["reason_code"], "complete_current_receipt")
        self.assertIn("02:02 MSK", lint["selected_excerpt"])
        self.assertIn("FOUND DEFECTS", lint["selected_excerpt"])

    def test_censor_dispatch_id_missing_is_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = Path(tmpdir) / "docs/plans/missing_dispatch.md"
            _write(plan, "# Plan\n\n## Evidence\n" + _complete_censor_row("Coder", "Ready for Review"))

            exit_code, payload = _payload(
                plan,
                censor_role="Coder",
                handoff_status="Ready for Review",
                censor_dispatch_id="dispatch-new",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "incomplete")
        self.assertEqual(lint["reason_code"], "missing_or_mismatched_censor_dispatch_id")
        self.assertEqual(lint["invalid_reasons"], ["missing_censor_dispatch_id"])

    def test_censor_dispatch_id_mismatch_is_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = Path(tmpdir) / "docs/plans/mismatched_dispatch.md"
            _write(
                plan,
                "# Plan\n\n## Evidence\n"
                + _complete_censor_row(
                    "Coder",
                    "Ready for Review",
                    censor_dispatch_id="dispatch-old",
                ),
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Coder",
                handoff_status="Ready for Review",
                censor_dispatch_id="dispatch-new",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "incomplete")
        self.assertEqual(lint["reason_code"], "missing_or_mismatched_censor_dispatch_id")
        self.assertEqual(lint["actual_censor_dispatch_id"], "dispatch-old")
        self.assertEqual(lint["invalid_reasons"], ["mismatched_censor_dispatch_id"])

    def test_censor_dispatch_id_requires_structural_handoff_header(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = Path(tmpdir) / "docs/plans/dispatch_status_header.md"
            receipt = _complete_censor_row(
                "Coder",
                "Ready for Review",
                censor_dispatch_id="dispatch-new",
            ).replace(
                "Ready for Review validated",
                "In progress validated",
                1,
            ).replace(
                "Second opinion: NO FINDINGS.",
                "Second opinion: NO FINDINGS. Expected Ready for Review appears only in observations.",
                1,
            )
            _write(plan, f"# Plan\n\n## Evidence\n{receipt}\n")

            _, payload = _payload(
                plan,
                censor_role="Coder",
                handoff_status="Ready for Review",
                censor_dispatch_id="dispatch-new",
            )

        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "incomplete")
        self.assertEqual(lint["reason_code"], "missing_or_mismatched_censor_dispatch_id")
        self.assertEqual(
            lint["invalid_reasons"],
            ["dispatch_receipt_role_or_handoff_status_mismatch"],
        )

    def test_censor_dispatch_id_handoff_header_must_follow_censor_tag(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = Path(tmpdir) / "docs/plans/dispatch_header_anchor.md"
            receipt = _complete_censor_row(
                "Coder",
                "Ready for Review",
                censor_dispatch_id="dispatch-new",
            ).replace(
                "(Coder CENSOR) OK:",
                "(Coder CENSOR) NOTE: not a handoff header. OK:",
                1,
            )
            _write(plan, f"# Plan\n\n## Evidence\n{receipt}\n")

            _, payload = _payload(
                plan,
                censor_role="Coder",
                handoff_status="Ready for Review",
                censor_dispatch_id="dispatch-new",
            )

        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "incomplete")
        self.assertEqual(
            lint["invalid_reasons"],
            ["dispatch_receipt_role_or_handoff_status_mismatch"],
        )

    def test_censor_dispatch_id_exact_match_is_complete(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = Path(tmpdir) / "docs/plans/matching_dispatch.md"
            _write(
                plan,
                "# Plan\n\n## Evidence\n"
                + _complete_censor_row(
                    "Coder",
                    "Ready for Review",
                    censor_dispatch_id="dispatch-new",
                ),
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Coder",
                handoff_status="Ready for Review",
                censor_dispatch_id="dispatch-new",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "complete")
        self.assertEqual(lint["reason_code"], "complete_current_receipt")
        self.assertEqual(lint["censor_dispatch_id"], "dispatch-new")

    def test_censor_dispatch_id_selects_later_match_over_historical_current(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = Path(tmpdir) / "docs/plans/new_dispatch_after_current.md"
            historical = _complete_censor_row("Coder", "Ready for Review", timestamp="02:01")
            matching = _complete_censor_row(
                "Coder",
                "Ready for Review",
                timestamp="02:02",
                censor_dispatch_id="dispatch-new",
            )
            _write(plan, f"# Plan\n\n## Evidence\n{historical}\n{matching}\n")

            exit_code, payload = _payload(
                plan,
                censor_role="Coder",
                handoff_status="Ready for Review",
                censor_dispatch_id="dispatch-new",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "complete")
        self.assertIn("02:02 MSK", lint["selected_excerpt"])
        self.assertIn("Censor dispatch id: dispatch-new", lint["selected_excerpt"])

    def test_censor_dispatch_id_receipt_must_be_current(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = Path(tmpdir) / "docs/plans/dispatch_without_current.md"
            receipt = _complete_censor_row(
                "Coder",
                "Ready for Review",
                censor_dispatch_id="dispatch-new",
            ).replace("current=true. ", "", 1)
            _write(plan, f"# Plan\n\n## Evidence\n{receipt}\n")

            exit_code, payload = _payload(
                plan,
                censor_role="Coder",
                handoff_status="Ready for Review",
                censor_dispatch_id="dispatch-new",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "incomplete")
        self.assertEqual(lint["reason_code"], "missing_or_mismatched_censor_dispatch_id")
        self.assertEqual(lint["invalid_reasons"], ["dispatch_receipt_missing_current_marker"])

    def test_censor_dispatch_id_rejects_current_marker_mentioned_only_in_prose(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = Path(tmpdir) / "docs/plans/prose_current_marker.md"
            receipt = _complete_censor_row(
                "Coder",
                "Ready for Review",
                censor_dispatch_id="dispatch-new",
            ).replace("current=true. ", "", 1).replace(
                "Second opinion: NO FINDINGS.",
                "Second opinion: NO FINDINGS; prose says current=true is absent.",
                1,
            )
            _write(plan, f"# Plan\n\n## Evidence\n{receipt}\n")

            _, payload = _payload(
                plan,
                censor_role="Coder",
                handoff_status="Ready for Review",
                censor_dispatch_id="dispatch-new",
            )

        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "incomplete")
        self.assertEqual(lint["invalid_reasons"], ["dispatch_receipt_missing_current_marker"])

    def test_censor_dispatch_id_rejects_dispatch_field_mentioned_only_in_prose(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = Path(tmpdir) / "docs/plans/prose_dispatch_field.md"
            receipt = _complete_censor_row("Coder", "Ready for Review").replace(
                "Second opinion: NO FINDINGS.",
                "Second opinion: NO FINDINGS. Censor dispatch id: dispatch-new.",
                1,
            )
            _write(plan, f"# Plan\n\n## Evidence\n{receipt}\n")

            _, payload = _payload(
                plan,
                censor_role="Coder",
                handoff_status="Ready for Review",
                censor_dispatch_id="dispatch-new",
            )

        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "incomplete")
        self.assertEqual(lint["invalid_reasons"], ["missing_censor_dispatch_id"])

    def test_censor_dispatch_id_rejects_duplicate_fields_in_one_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = Path(tmpdir) / "docs/plans/duplicate_dispatch_fields.md"
            receipt = _complete_censor_row(
                "Coder",
                "Ready for Review",
                censor_dispatch_id="dispatch-new",
            ).replace(
                "Observations:",
                "Censor dispatch id: dispatch-new. Observations:",
                1,
            )
            _write(plan, f"# Plan\n\n## Evidence\n{receipt}\n")

            _, payload = _payload(
                plan,
                censor_role="Coder",
                handoff_status="Ready for Review",
                censor_dispatch_id="dispatch-new",
            )

        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "incomplete")
        self.assertEqual(lint["reason_code"], "ambiguous_censor_dispatch_id")
        self.assertEqual(
            lint["invalid_reasons"],
            ["duplicate_or_conflicting_censor_dispatch_id_fields"],
        )

    def test_censor_dispatch_id_rejects_malformed_duplicate_field(self) -> None:
        for malformed_value in ("dispatch/other", ""):
            with self.subTest(malformed_value=malformed_value), tempfile.TemporaryDirectory() as tmpdir:
                plan = Path(tmpdir) / "docs/plans/malformed_duplicate_dispatch_field.md"
                receipt = _complete_censor_row(
                    "Coder",
                    "Ready for Review",
                    censor_dispatch_id="dispatch-new",
                ).replace(
                    "Observations:",
                    f"Censor dispatch id: {malformed_value}. Observations:",
                    1,
                )
                _write(plan, f"# Plan\n\n## Evidence\n{receipt}\n")

                _, payload = _payload(
                    plan,
                    censor_role="Coder",
                    handoff_status="Ready for Review",
                    censor_dispatch_id="dispatch-new",
                )

            lint = payload["censor_evidence_lint"]
            self.assertEqual(lint["state"], "incomplete")
            self.assertEqual(lint["reason_code"], "ambiguous_censor_dispatch_id")
            self.assertEqual(
                lint["invalid_reasons"],
                ["duplicate_or_conflicting_censor_dispatch_id_fields"],
            )

    def test_censor_dispatch_id_rejects_malformed_duplicate_label(self) -> None:
        for malformed_label in ("Censor dispatch id :", "Censor dispatch-id:"):
            with self.subTest(label=malformed_label), tempfile.TemporaryDirectory() as tmpdir:
                plan = Path(tmpdir) / "docs/plans/malformed_duplicate_dispatch_label.md"
                receipt = _complete_censor_row(
                    "Coder",
                    "Ready for Review",
                    censor_dispatch_id="dispatch-new",
                ).replace(
                    "Observations:",
                    f"{malformed_label} dispatch-other. Observations:",
                    1,
                )
                _write(plan, f"# Plan\n\n## Evidence\n{receipt}\n")

                _, payload = _payload(
                    plan,
                    censor_role="Coder",
                    handoff_status="Ready for Review",
                    censor_dispatch_id="dispatch-new",
                )

            lint = payload["censor_evidence_lint"]
            self.assertEqual(lint["state"], "incomplete")
            self.assertEqual(lint["reason_code"], "ambiguous_censor_dispatch_id")
            self.assertEqual(
                lint["invalid_reasons"],
                ["duplicate_or_conflicting_censor_dispatch_id_fields"],
            )

    def test_censor_dispatch_id_rejects_duplicate_or_conflicting_current_fields(self) -> None:
        replacements = {
            "duplicate_true": "current=true; current=true.",
            "conflicting": "current=false; current=true.",
            "case_conflicting": "CURRENT=false; current=true.",
            "false_only": "current=false.",
            "spaced_true": "current = true.",
        }
        for case, current_fields in replacements.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmpdir:
                plan = Path(tmpdir) / f"docs/plans/{case}_current_fields.md"
                receipt = _complete_censor_row(
                    "Coder",
                    "Ready for Review",
                    censor_dispatch_id="dispatch-new",
                ).replace("current=true.", current_fields, 1)
                _write(plan, f"# Plan\n\n## Evidence\n{receipt}\n")

                _, payload = _payload(
                    plan,
                    censor_role="Coder",
                    handoff_status="Ready for Review",
                    censor_dispatch_id="dispatch-new",
                )

            lint = payload["censor_evidence_lint"]
            self.assertEqual(lint["state"], "incomplete")
            expected = (
                "invalid_current_field"
                if case in {"false_only", "spaced_true"}
                else "duplicate_or_conflicting_current_fields"
            )
            self.assertEqual(lint["invalid_reasons"], [expected])

    def test_censor_dispatch_id_rejects_duplicate_machine_readback_labels(self) -> None:
        replacements = {
            "second_opinion": (
                "Second opinion: NO FINDINGS.",
                "Second opinion: FOUND DEFECTS. Second opinion: NO FINDINGS.",
                "duplicate_machine_readback_label:Second opinion",
            ),
            "final_verdict": (
                "Final censor verdict: OK.",
                "Final censor verdict: FAIL. Final censor verdict: OK.",
                "duplicate_machine_readback_label:Final censor verdict",
            ),
            "case_drift": (
                "Second opinion: NO FINDINGS.",
                "second opinion: FOUND DEFECTS. Second opinion: NO FINDINGS.",
                "duplicate_machine_readback_label:Second opinion",
            ),
        }
        for case, (old, new, expected_reason) in replacements.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmpdir:
                plan = Path(tmpdir) / f"docs/plans/{case}_duplicate_label.md"
                receipt = _complete_censor_row(
                    "Coder",
                    "Ready for Review",
                    censor_dispatch_id="dispatch-new",
                ).replace(old, new, 1)
                _write(plan, f"# Plan\n\n## Evidence\n{receipt}\n")

                _, payload = _payload(
                    plan,
                    censor_role="Coder",
                    handoff_status="Ready for Review",
                    censor_dispatch_id="dispatch-new",
                )

            lint = payload["censor_evidence_lint"]
            self.assertEqual(lint["state"], "incomplete")
            self.assertEqual(lint["reason_code"], "missing_or_invalid_fields")
            self.assertIn(expected_reason, lint["invalid_reasons"])

    def test_censor_dispatch_id_scans_provenance_across_malformed_punctuation(self) -> None:
        mutations = {
            "dispatch": lambda row: row.replace(
                "Observations:",
                ", Censor dispatch id: dispatch-other. Observations:",
                1,
            ),
            "current": lambda row: row.replace(
                "current=true.",
                "current=true. note, current=false.",
                1,
            ),
            "handoff": lambda row: row.replace(
                "current=true.",
                "note, FAIL: In progress validated; current=true.",
                1,
            ),
        }
        for case, mutate in mutations.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmpdir:
                plan = Path(tmpdir) / f"docs/plans/{case}_punctuation.md"
                receipt = mutate(
                    _complete_censor_row(
                        "Coder",
                        "Ready for Review",
                        censor_dispatch_id="dispatch-new",
                    )
                )
                _write(plan, f"# Plan\n\n## Evidence\n{receipt}\n")

                _, payload = _payload(
                    plan,
                    censor_role="Coder",
                    handoff_status="Ready for Review",
                    censor_dispatch_id="dispatch-new",
                )

            self.assertEqual(payload["censor_evidence_lint"]["state"], "incomplete")

    def test_censor_dispatch_id_requires_one_literal_uppercase_handoff_header(self) -> None:
        replacements = {
            "lowercase": "ok: Ready for Review validated;",
            "duplicate_conflict": (
                "OK: Ready for Review validated; FAIL: In progress validated;"
            ),
        }
        for case, header in replacements.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmpdir:
                plan = Path(tmpdir) / f"docs/plans/{case}_handoff_header.md"
                receipt = _complete_censor_row(
                    "Coder",
                    "Ready for Review",
                    censor_dispatch_id="dispatch-new",
                ).replace("OK: Ready for Review validated;", header, 1)
                _write(plan, f"# Plan\n\n## Evidence\n{receipt}\n")

                _, payload = _payload(
                    plan,
                    censor_role="Coder",
                    handoff_status="Ready for Review",
                    censor_dispatch_id="dispatch-new",
                )

            lint = payload["censor_evidence_lint"]
            self.assertEqual(lint["state"], "incomplete")
            self.assertEqual(
                lint["invalid_reasons"],
                ["dispatch_receipt_role_or_handoff_status_mismatch"],
            )

    def test_censor_dispatch_id_rejects_malformed_observations_boundary(self) -> None:
        for malformed_boundary in ("Observations :", "observations:"):
            with self.subTest(boundary=malformed_boundary), tempfile.TemporaryDirectory() as tmpdir:
                plan = Path(tmpdir) / "docs/plans/malformed_observations_boundary.md"
                receipt = _complete_censor_row(
                    "Coder",
                    "Ready for Review",
                    censor_dispatch_id="dispatch-new",
                ).replace("Observations:", malformed_boundary, 1)
                _write(plan, f"# Plan\n\n## Evidence\n{receipt}\n")

                _, payload = _payload(
                    plan,
                    censor_role="Coder",
                    handoff_status="Ready for Review",
                    censor_dispatch_id="dispatch-new",
                )

            lint = payload["censor_evidence_lint"]
            self.assertEqual(lint["state"], "incomplete")
            self.assertEqual(lint["reason_code"], "missing_or_invalid_fields")
            self.assertEqual(lint["invalid_reasons"], ["malformed_observations_boundary"])

    def test_censor_dispatch_id_rejects_body_only_identity_after_malformed_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = Path(tmpdir) / "docs/plans/body_only_dispatch_identity.md"
            receipt = _complete_censor_row(
                "Coder",
                "Ready for Review",
                censor_dispatch_id="dispatch-new",
            ).replace(
                "current=true. Censor dispatch id: dispatch-new. Observations:",
                "Observations : body prose. current=true. Censor dispatch id: dispatch-new.",
                1,
            )
            _write(plan, f"# Plan\n\n## Evidence\n{receipt}\n")

            _, payload = _payload(
                plan,
                censor_role="Coder",
                handoff_status="Ready for Review",
                censor_dispatch_id="dispatch-new",
            )

        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "incomplete")
        self.assertNotEqual(lint["reason_code"], "complete_current_receipt")

    def test_censor_dispatch_id_rejects_duplicate_observations_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = Path(tmpdir) / "docs/plans/duplicate_observations_boundary.md"
            receipt = _complete_censor_row(
                "Coder",
                "Ready for Review",
                censor_dispatch_id="dispatch-new",
            ).replace("Observations:", "Observations: body. Observations:", 1)
            _write(plan, f"# Plan\n\n## Evidence\n{receipt}\n")

            _, payload = _payload(
                plan,
                censor_role="Coder",
                handoff_status="Ready for Review",
                censor_dispatch_id="dispatch-new",
            )

        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "incomplete")
        self.assertEqual(lint["reason_code"], "missing_or_invalid_fields")
        self.assertEqual(lint["invalid_reasons"], ["duplicate_observations_boundaries"])

    def test_censor_dispatch_id_rejects_duplicate_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = Path(tmpdir) / "docs/plans/duplicate_dispatch_receipts.md"
            first = _complete_censor_row(
                "Coder", "Ready for Review", "02:01", "dispatch-new"
            )
            second = _complete_censor_row(
                "Coder", "Ready for Review", "02:02", "dispatch-new"
            )
            _write(plan, f"# Plan\n\n## Evidence\n{first}\n{second}\n")

            _, payload = _payload(
                plan,
                censor_role="Coder",
                handoff_status="Ready for Review",
                censor_dispatch_id="dispatch-new",
            )

        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "incomplete")
        self.assertEqual(lint["reason_code"], "ambiguous_censor_dispatch_id")
        self.assertEqual(lint["invalid_reasons"], ["duplicate_censor_dispatch_id_receipts"])

    def test_censor_dispatch_id_rejects_duplicate_receipt_outside_expected_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = Path(tmpdir) / "docs/plans/duplicate_dispatch_other_status.md"
            current = _complete_censor_row(
                "Coder", "Ready for Review", "02:01", "dispatch-new"
            )
            other_status = _complete_censor_row(
                "Coder", "In progress", "02:02", "dispatch-new"
            )
            _write(plan, f"# Plan\n\n## Evidence\n{current}\n{other_status}\n")

            _, payload = _payload(
                plan,
                censor_role="Coder",
                handoff_status="Ready for Review",
                censor_dispatch_id="dispatch-new",
            )

        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "incomplete")
        self.assertEqual(lint["reason_code"], "ambiguous_censor_dispatch_id")
        self.assertEqual(lint["invalid_reasons"], ["duplicate_censor_dispatch_id_receipts"])

    def test_censor_dispatch_id_rejects_malformed_global_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = Path(tmpdir) / "docs/plans/malformed_global_duplicate.md"
            current = _complete_censor_row(
                "Coder", "Ready for Review", "02:01", "dispatch-new"
            )
            malformed_other = _complete_censor_row(
                "Planner", "In progress", "02:02"
            ).replace(
                "Observations:",
                "Censor dispatch id : dispatch-new. Observations:",
                1,
            )
            _write(plan, f"# Plan\n\n## Evidence\n{current}\n{malformed_other}\n")

            _, payload = _payload(
                plan,
                censor_role="Coder",
                handoff_status="Ready for Review",
                censor_dispatch_id="dispatch-new",
            )

        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "incomplete")
        self.assertEqual(lint["reason_code"], "ambiguous_censor_dispatch_id")
        self.assertEqual(
            lint["invalid_reasons"],
            ["duplicate_or_conflicting_censor_dispatch_id_fields"],
        )

    def test_censor_dispatch_id_rejects_old_dispatch_after_newer_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = Path(tmpdir) / "docs/plans/stale_dispatch.md"
            old = _complete_censor_row(
                "Coder", "Ready for Review", "02:01", "dispatch-old"
            )
            new = _complete_censor_row(
                "Coder", "Ready for Review", "02:02", "dispatch-new"
            )
            _write(plan, f"# Plan\n\n## Evidence\n{old}\n{new}\n")

            _, payload = _payload(
                plan,
                censor_role="Coder",
                handoff_status="Ready for Review",
                censor_dispatch_id="dispatch-old",
            )

        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "incomplete")
        self.assertEqual(lint["reason_code"], "stale_censor_dispatch_id")
        self.assertEqual(
            lint["invalid_reasons"],
            ["later_same_role_status_receipt_supersedes_dispatch"],
        )

    def test_censor_evidence_lint_valid_skip_hint(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/valid_skip.md"
            _write(
                plan,
                """\
                # Plan

                ## Evidence
                - [2026-06-23 02:02 MSK] (Coder) Handoff to Ready for Review. Censor hint: skip (why=evidence-only delta; previous coder-owned contract unchanged).
                """,
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Coder",
                handoff_status="Ready for Review",
            )
            dispatch_exit_code, dispatch_payload = _payload(
                plan,
                censor_role="Coder",
                handoff_status="Ready for Review",
                censor_dispatch_id="dispatch-skipped",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "skipped_by_valid_hint")
        self.assertEqual(lint["reason_code"], "valid_skip_hint")
        self.assertEqual(dispatch_exit_code, 0)
        dispatch_lint = dispatch_payload["censor_evidence_lint"]
        self.assertEqual(dispatch_lint["state"], "incomplete")
        self.assertEqual(
            dispatch_lint["reason_code"],
            "missing_or_mismatched_censor_dispatch_id",
        )
        self.assertEqual(
            dispatch_lint["invalid_reasons"],
            ["dispatch_selector_disallows_skip_hint"],
        )

    def test_censor_evidence_lint_handoff_only_alias_accepts_incident_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/handoff_only_alias.md"
            _write(
                plan,
                """\
                # Plan

                ## Evidence
                - [2026-06-28 17:03 MSK] (Architect) Handoff to Ready for Planner after checking scope / acceptance / tests / commands readback only. Censor hint: skip (why=handoff-only delta; previous architect-owned contract unchanged).
                """,
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Architect",
                handoff_status="Ready for Planner",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "skipped_by_valid_hint")
        self.assertEqual(lint["reason_code"], "valid_skip_hint")
        self.assertEqual(lint["invalid_reasons"], [])

    def test_censor_evidence_lint_handoff_only_alias_requires_unchanged_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/handoff_only_without_contract.md"
            _write(
                plan,
                """\
                # Plan

                ## Evidence
                - [2026-06-28 17:03 MSK] (Architect) Handoff to Ready for Planner after checking scope / acceptance / tests / commands readback only. Censor hint: skip (why=handoff-only delta).
                """,
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Architect",
                handoff_status="Ready for Planner",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "incomplete")
        self.assertEqual(lint["reason_code"], "invalid_skip_hint")
        self.assertIn("skip_hint_semantic_delta", lint["invalid_reasons"])

    def test_censor_evidence_lint_handoff_only_alias_rejects_wrong_role_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/handoff_only_wrong_role_contract.md"
            _write(
                plan,
                """\
                # Plan

                ## Evidence
                - [2026-06-28 17:03 MSK] (Coder) Handoff to Ready for Review after checking scope / acceptance / tests / commands readback only. Censor hint: skip (why=handoff-only delta; previous architect-owned contract unchanged).
                """,
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Coder",
                handoff_status="Ready for Review",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "incomplete")
        self.assertEqual(lint["reason_code"], "invalid_skip_hint")
        self.assertIn("skip_hint_semantic_delta", lint["invalid_reasons"])

    def test_censor_evidence_lint_evidence_status_alias_accepts_live_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/evidence_status_alias_live.md"
            _write(
                plan,
                """\
                # Plan

                ## Evidence
                - [2026-07-01 22:03 MSK] (Architect) Handoff to Ready for Planner after status move, contract readback, tests/gates check and queue evidence update. Censor hint: skip (why=evidence/status handoff only; previous architect-owned contract unchanged).
                """,
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Architect",
                handoff_status="Ready for Planner",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "skipped_by_valid_hint")
        self.assertEqual(lint["reason_code"], "valid_skip_hint")
        self.assertEqual(lint["invalid_reasons"], [])

    def test_censor_evidence_lint_evidence_status_only_alias_accepts_bounded_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/evidence_status_only_alias.md"
            _write(
                plan,
                """\
                # Plan

                ## Evidence
                - [2026-07-01 22:04 MSK] (Planner) Handoff to Ready for Coder after status/evidence restamp and tests readback. Censor hint: skip (why=evidence/status-only delta; previous planner-owned contract unchanged).
                """,
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Planner",
                handoff_status="Ready for Coder",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "skipped_by_valid_hint")
        self.assertEqual(lint["reason_code"], "valid_skip_hint")
        self.assertEqual(lint["invalid_reasons"], [])

    def test_censor_evidence_lint_status_evidence_only_alias_accepts_bounded_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/status_evidence_only_alias.md"
            _write(
                plan,
                """\
                # Plan

                ## Evidence
                - [2026-07-01 22:04 MSK] (Architect) Handoff to Ready for Planner after status/evidence restamp and tests readback. Censor hint: skip (why=status/evidence-only delta; previous architect-owned contract unchanged).
                """,
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Architect",
                handoff_status="Ready for Planner",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "skipped_by_valid_hint")
        self.assertEqual(lint["reason_code"], "valid_skip_hint")
        self.assertEqual(lint["invalid_reasons"], [])

    def test_censor_evidence_lint_evidence_status_alias_requires_unchanged_contract(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/evidence_status_without_contract.md"
            _write(
                plan,
                """\
                # Plan

                ## Evidence
                - [2026-07-01 22:05 MSK] (Architect) Handoff to Ready for Planner after status move, contract readback and tests/gates check. Censor hint: skip (why=evidence/status handoff only).
                """,
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Architect",
                handoff_status="Ready for Planner",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "incomplete")
        self.assertEqual(lint["reason_code"], "invalid_skip_hint")
        self.assertIn("skip_hint_semantic_delta", lint["invalid_reasons"])

    def test_censor_evidence_lint_evidence_status_alias_rejects_missing_why(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/evidence_status_missing_why.md"
            _write(
                plan,
                """\
                # Plan

                ## Evidence
                - [2026-07-01 22:05 MSK] (Architect) Handoff to Ready for Planner after status/evidence restamp, contract readback and tests/gates check. Censor hint: skip.
                """,
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Architect",
                handoff_status="Ready for Planner",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "incomplete")
        self.assertEqual(lint["reason_code"], "invalid_skip_hint")
        self.assertIn("skip_hint_missing_why", lint["invalid_reasons"])

    def test_censor_evidence_lint_evidence_status_alias_rejects_wrong_role_contract(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/evidence_status_wrong_role.md"
            _write(
                plan,
                """\
                # Plan

                ## Evidence
                - [2026-07-01 22:06 MSK] (Coder) Handoff to Ready for Review after status/evidence restamp and tests readback. Censor hint: skip (why=evidence/status-only delta; previous architect-owned contract unchanged).
                """,
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Coder",
                handoff_status="Ready for Review",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "incomplete")
        self.assertEqual(lint["reason_code"], "invalid_skip_hint")
        self.assertIn("skip_hint_semantic_delta", lint["invalid_reasons"])

    def test_censor_evidence_lint_evidence_status_alias_rejects_changed_targets_reason(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/evidence_status_changed_targets.md"
            _write(
                plan,
                """\
                # Plan

                ## Evidence
                - [2026-07-01 22:07 MSK] (Coder) Handoff to Ready for Review. Censor hint: skip (why=evidence/status-only delta; implementation changed targets and tests; previous coder-owned contract unchanged).
                """,
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Coder",
                handoff_status="Ready for Review",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "incomplete")
        self.assertEqual(lint["reason_code"], "invalid_skip_hint")
        self.assertIn("skip_hint_semantic_delta", lint["invalid_reasons"])

    def test_censor_evidence_lint_missing_current_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/missing_current.md"
            _write(
                plan,
                """\
                # Plan

                ## Evidence
                - [2026-06-23 02:02 MSK] (Coder) Implemented current handoff without censor yet.
                """,
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Coder",
                handoff_status="Ready for Review",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "incomplete")
        self.assertEqual(lint["reason_code"], "missing_current_receipt")

    def test_censor_evidence_lint_skip_hint_rejects_semantic_delta(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/semantic_skip.md"
            _write(
                plan,
                """\
                # Plan

                ## Evidence
                - [2026-06-23 02:03 MSK] (Coder) Handoff to Ready for Review. Censor hint: skip (why=implementation changed targets and tests).
                """,
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Coder",
                handoff_status="Ready for Review",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "incomplete")
        self.assertEqual(lint["reason_code"], "invalid_skip_hint")
        self.assertIn("skip_hint_semantic_delta", lint["invalid_reasons"])

    def test_censor_evidence_lint_handoff_only_alias_rejects_changed_targets_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/handoff_only_changed_targets.md"
            _write(
                plan,
                """\
                # Plan

                ## Evidence
                - [2026-06-23 02:03 MSK] (Coder) Handoff to Ready for Review. Censor hint: skip (why=handoff-only delta; implementation changed targets and tests; previous coder-owned contract unchanged).
                """,
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Coder",
                handoff_status="Ready for Review",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "incomplete")
        self.assertEqual(lint["reason_code"], "invalid_skip_hint")
        self.assertIn("skip_hint_semantic_delta", lint["invalid_reasons"])

    def test_censor_evidence_lint_skip_hint_ignores_other_role_blocker_wording(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/stale_skip.md"
            _write(
                plan,
                """\
                # Plan

                ## Evidence
                - [2026-06-23 02:03 MSK] (Coder) Handoff to Ready for Review. Censor hint: skip (why=evidence-only delta).
                - [2026-06-23 02:04 MSK] (Reviewer) S1 blocker materialized after the skip hint.
                """,
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Coder",
                handoff_status="Ready for Review",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "skipped_by_valid_hint")
        self.assertEqual(lint["reason_code"], "valid_skip_hint")
        self.assertEqual(lint["invalid_reasons"], [])

    def test_censor_evidence_lint_skip_hint_rejects_literal_0136_shape_structurally(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/literal_0136_shape.md"
            last_matching = (
                "- [2026-07-13 19:36 MSK] (Architect) Ready for Planner handoff "
                "records real scope expansion after the review cycle."
            )
            _write(
                plan,
                f"""\
                # Plan

                ## Evidence
                - [2026-07-13 19:33 MSK] (Architect) Handoff to Ready for Planner. Censor hint: skip (why=evidence-only delta).
                - [2026-07-13 19:34 MSK] (Reviewer) S1 blocker materialized after the skip hint.
                {last_matching}
                """,
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Architect",
                handoff_status="Ready for Planner",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "incomplete")
        self.assertEqual(lint["reason_code"], "invalid_skip_hint")
        self.assertEqual(
            lint["invalid_reasons"],
            ["stale_current_receipt_after_later_matching_event"],
        )
        self.assertEqual(lint["selected_excerpt"], last_matching)

    def test_censor_evidence_lint_skip_hint_rejects_neutral_matching_event(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/neutral_structural_stale.md"
            last_matching = (
                "- [2026-07-13 20:04 MSK] (Architect) Ready for Planner handoff "
                "now reflects the revised source inventory."
            )
            _write(
                plan,
                f"""\
                # Plan

                ## Evidence
                - [2026-07-13 20:01 MSK] (Architect) Handoff to Ready for Planner. Censor hint: skip (why=evidence-only delta).
                - [2026-07-13 20:02 MSK] (Architect) Ready for Planner handoff records the first neutral context update.
                - [2026-07-13 20:03 MSK] (Reviewer) Contract assessment recorded a material observation.
                {last_matching}
                """,
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Architect",
                handoff_status="Ready for Planner",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "incomplete")
        self.assertEqual(lint["reason_code"], "invalid_skip_hint")
        self.assertEqual(
            lint["invalid_reasons"],
            ["stale_current_receipt_after_later_matching_event"],
        )
        self.assertEqual(lint["selected_excerpt"], last_matching)

    def test_censor_evidence_lint_skip_hint_ignores_other_status_and_unknown_tags(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/non_matching_context.md"
            _write(
                plan,
                """\
                # Plan

                ## Evidence
                - [2026-07-13 20:01 MSK] (Architect) Handoff to Ready for Planner. Censor hint: skip (why=evidence-only delta).
                - [2026-07-13 20:02 MSK] (Architect) Ready for Coder handoff records a material change.
                - [2026-07-13 20:03 MSK] (Architect-ish) Ready for Planner handoff records a material change.
                - [2026-07-13 20:04 MSK] Prose mentions Architect and Ready for Planner without a canonical role tag.
                """,
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Architect",
                handoff_status="Ready for Planner",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "skipped_by_valid_hint")
        self.assertEqual(lint["reason_code"], "valid_skip_hint")
        self.assertEqual(lint["invalid_reasons"], [])

    def test_censor_evidence_lint_skip_hint_ignores_matching_event_before_skip(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/pre_skip_context.md"
            _write(
                plan,
                """\
                # Plan

                ## Evidence
                - [2026-07-13 20:01 MSK] (Architect) Ready for Planner handoff reflects an earlier material event.
                - [2026-07-13 20:02 MSK] (Architect) Handoff to Ready for Planner. Censor hint: skip (why=evidence-only delta).
                """,
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Architect",
                handoff_status="Ready for Planner",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "skipped_by_valid_hint")
        self.assertEqual(lint["reason_code"], "valid_skip_hint")
        self.assertEqual(lint["invalid_reasons"], [])

    def test_censor_evidence_lint_fresh_receipt_recovers_after_stale_skip(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/fresh_receipt_recovery.md"
            fresh_receipt = _complete_censor_row(
                "Architect",
                "Ready for Planner",
                "20:03",
            )
            _write(
                plan,
                f"""\
                # Plan

                ## Evidence
                - [2026-07-11 20:01 MSK] (Architect) Handoff to Ready for Planner. Censor hint: skip (why=evidence-only delta).
                - [2026-07-11 20:02 MSK] (Architect) Ready for Planner handoff now reflects the revised source inventory.
                {fresh_receipt}
                """,
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Architect",
                handoff_status="Ready for Planner",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "complete")
        self.assertEqual(lint["reason_code"], "complete_current_receipt")
        self.assertEqual(lint["invalid_reasons"], [])

    def test_censor_evidence_lint_repeated_skip_preserves_stale_context(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/repeated_skip_stale.md"
            stale_context = (
                "- [2026-07-13 20:02 MSK] (Architect) Ready for Planner handoff "
                "now reflects the revised source inventory."
            )
            _write(
                plan,
                f"""\
                # Plan

                ## Evidence
                - [2026-07-13 20:01 MSK] (Architect) Handoff to Ready for Planner. Censor hint: skip (why=evidence-only delta).
                {stale_context}
                - [2026-07-13 20:03 MSK] (Architect) Handoff to Ready for Planner. Censor hint: skip (why=evidence-only delta).
                """,
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Architect",
                handoff_status="Ready for Planner",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "incomplete")
        self.assertEqual(lint["reason_code"], "invalid_skip_hint")
        self.assertEqual(
            lint["invalid_reasons"],
            ["stale_current_receipt_after_later_matching_event"],
        )
        self.assertEqual(lint["receipt_line"], 6)
        self.assertEqual(lint["selected_excerpt"], stale_context)

    def test_censor_evidence_lint_malformed_receipt_does_not_reset_stale_context(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/malformed_receipt_stale.md"
            stale_context = (
                "- [2026-07-13 20:02 MSK] (Architect) Ready for Planner handoff "
                "now reflects the revised source inventory."
            )
            _write(
                plan,
                f"""\
                # Plan

                ## Evidence
                - [2026-07-13 20:01 MSK] (Architect) Handoff to Ready for Planner. Censor hint: skip (why=evidence-only delta).
                {stale_context}
                - [2026-07-13 20:03 MSK] (Architect CENSOR) OK: Ready for Planner validated. Observations: Second opinion: FOUND DEFECTS. Fixes: none.
                - [2026-07-13 20:04 MSK] (Architect) Handoff to Ready for Planner. Censor hint: skip (why=evidence-only delta).
                """,
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Architect",
                handoff_status="Ready for Planner",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "incomplete")
        self.assertEqual(lint["reason_code"], "invalid_skip_hint")
        self.assertEqual(
            lint["invalid_reasons"],
            ["stale_current_receipt_after_later_matching_event"],
        )
        self.assertEqual(lint["selected_excerpt"], stale_context)

    def test_censor_evidence_lint_complete_receipt_resets_stale_before_later_skip(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/complete_receipt_resets_stale.md"
            fresh_receipt = _complete_censor_row(
                "Architect",
                "Ready for Planner",
                "20:03",
            )
            _write(
                plan,
                f"""\
                # Plan

                ## Evidence
                - [2026-07-11 20:01 MSK] (Architect) Handoff to Ready for Planner. Censor hint: skip (why=evidence-only delta).
                - [2026-07-11 20:02 MSK] (Architect) Ready for Planner handoff now reflects the revised source inventory.
                {fresh_receipt}
                - [2026-07-11 20:04 MSK] (Architect) Handoff to Ready for Planner. Censor hint: skip (why=evidence-only delta).
                """,
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Architect",
                handoff_status="Ready for Planner",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "skipped_by_valid_hint")
        self.assertEqual(lint["reason_code"], "valid_skip_hint")
        self.assertEqual(lint["invalid_reasons"], [])

    def test_censor_evidence_lint_skip_hint_anti_spam_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/skip_spam.md"
            _write(
                plan,
                """\
                # Plan

                ## Evidence
                - [2026-06-23 02:04 MSK] (Architect) Handoff to Ready for Planner. Censor hint: skip (why=evidence-only delta).
                - [2026-06-23 02:05 MSK] (Architect) Handoff to Ready for Planner. Censor hint: skip (why=evidence-only delta).
                - [2026-06-23 02:06 MSK] (Architect) Handoff to Ready for Planner. Censor hint: skip (why=evidence-only delta).
                """,
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Architect",
                handoff_status="Ready for Planner",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "incomplete")
        self.assertIn("skip_hint_anti_spam_limit_exceeded", lint["invalid_reasons"])

    def test_censor_evidence_lint_skip_hint_anti_spam_resets_after_full_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/skip_spam_reset.md"
            _write(
                plan,
                """\
                # Plan

                ## Evidence
                - [2026-06-23 02:04 MSK] (Architect) Handoff to Ready for Planner. Censor hint: skip (why=evidence-only delta).
                - [2026-06-23 02:05 MSK] (Architect CENSOR) OK: Ready for Planner validated. Observations: Second opinion: NO FINDINGS. Addendum (new angle): checked helper gate. Context reconciliation: current handoff matches plan. Counterfactuals considered: old skip could be stale, not confirmed. Fixes: none. Artifacts opened: `PLAN_PATH`. Review verdict seen: no live review artifact. Blocker IDs considered: `N/A`. Role-owned finding: none. Reconciliation: no live blocker. Final censor verdict: OK.
                - [2026-06-23 02:06 MSK] (Architect) Handoff to Ready for Planner. Censor hint: skip (why=evidence-only delta).
                - [2026-06-23 02:07 MSK] (Architect CENSOR) OK: Ready for Planner validated. Observations: Second opinion: NO FINDINGS. Addendum (new angle): checked helper gate. Context reconciliation: current handoff matches plan. Counterfactuals considered: old skip could be stale, not confirmed. Fixes: none. Artifacts opened: `PLAN_PATH`. Review verdict seen: no live review artifact. Blocker IDs considered: `N/A`. Role-owned finding: none. Reconciliation: no live blocker. Final censor verdict: OK.
                - [2026-06-23 02:08 MSK] (Architect) Handoff to Ready for Planner. Censor hint: skip (why=evidence-only delta).
                """,
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Architect",
                handoff_status="Ready for Planner",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "skipped_by_valid_hint")
        self.assertEqual(lint["reason_code"], "valid_skip_hint")
        self.assertEqual(lint["invalid_reasons"], [])

    def test_censor_evidence_lint_ambiguous_same_role_status_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/ambiguous.md"
            _write(
                plan,
                """\
                # Plan

                ## Evidence
                - [2026-06-23 02:07 MSK] (Coder CENSOR) OK: Ready for Review validated. Observations: Second opinion: FOUND DEFECTS. Addendum: angle one. Context reconciliation: current handoff. Fixes: none.
                - [2026-06-23 02:08 MSK] (Coder CENSOR) OK: Ready for Review validated. Observations: Second opinion: FOUND DEFECTS. Addendum: angle two. Context reconciliation: current handoff. Fixes: none.
                """,
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Coder",
                handoff_status="Ready for Review",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "incomplete")
        self.assertEqual(lint["reason_code"], "ambiguous_current_receipt")

    def test_censor_evidence_lint_ambiguous_complete_unmarked_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/ambiguous_complete.md"
            _write(
                plan,
                """\
                # Plan

                ## Evidence
                - [2026-06-30 02:07 MSK] (Planner CENSOR) OK: Ready for Coder validated. Observations: Second opinion: NO FINDINGS. Addendum (new angle): checked first receipt. Context reconciliation: current handoff matches plan. Counterfactuals considered: duplicate receipt could appear later, not confirmed yet. Fixes: none. Artifacts opened: `PLAN_PATH`. Review verdict seen: no live review artifact. Blocker IDs considered: `N/A`. Role-owned finding: none. Reconciliation: no live blocker. Final censor verdict: OK.
                - [2026-06-30 02:08 MSK] (Planner CENSOR) OK: Ready for Coder validated. Observations: Second opinion: NO FINDINGS. Addendum (new angle): checked duplicate receipt. Context reconciliation: current handoff still matches plan. Counterfactuals considered: duplicate unmarked receipt must not be selected by line order. Fixes: none. Artifacts opened: `PLAN_PATH`. Review verdict seen: no live review artifact. Blocker IDs considered: `N/A`. Role-owned finding: none. Reconciliation: no live blocker. Final censor verdict: OK.
                """,
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Planner",
                handoff_status="Ready for Coder",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "incomplete")
        self.assertEqual(lint["reason_code"], "ambiguous_current_receipt")
        self.assertIn(
            "multiple_same_role_status_receipts_without_current_selector",
            lint["invalid_reasons"],
        )

    def test_censor_evidence_lint_current_recovery_after_malformed_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/current_recovery.md"
            _write(
                plan,
                """\
                # Plan

                ## Evidence
                - [2026-06-30 02:07 MSK] (Coder CENSOR) OK: Ready for Review validated after wrapper failure. Observations: Second opinion: FOUND DEFECTS. Addendum (new angle): wrapper resume failed before full receipt. Context reconciliation: current handoff not recoverable from this prose-only row. Fixes: none yet.
                - [2026-06-30 02:08 MSK] (Coder CENSOR) OK: Ready for Review validated; current=true. Observations: Second opinion: NO FINDINGS. Addendum (new angle): checked structured recovery receipt. Context reconciliation: this complete current receipt supersedes the malformed historical row. Counterfactuals considered: malformed row could be selected, not confirmed because this row is current=true; missing labels could be inferred from prose, not confirmed because fields are literal here. Fixes: none. Artifacts opened: `PLAN_PATH`. Review verdict seen: no live review artifact. Blocker IDs considered: `N/A`. Role-owned finding: none. Reconciliation: no live blocker. Final censor verdict: OK.
                """,
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Coder",
                handoff_status="Ready for Review",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "complete")
        self.assertEqual(lint["reason_code"], "complete_current_receipt")
        self.assertEqual(payload["summary"]["missing_receipt_count"], 1)
        self.assertTrue(
            any("missing:" in warning for warning in payload["warnings"]),
            payload["warnings"],
        )

    def test_censor_evidence_lint_requires_context_reconciliation_not_reconciliation_alias(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/missing_context_and_fixes.md"
            _write(
                plan,
                """\
                # Plan

                ## Evidence
                - [2026-06-30 02:08 MSK] (Coder CENSOR) OK: Ready for Review validated. Observations: Second opinion: NO FINDINGS. Addendum (new angle): checked alias boundary. Counterfactuals considered: Reconciliation might be incorrectly treated as Context reconciliation; helper must reject that. Artifacts opened: `PLAN_PATH`. Review verdict seen: no live review artifact. Blocker IDs considered: `N/A`. Role-owned finding: none. Reconciliation: no live blocker. Final censor verdict: OK.
                """,
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Coder",
                handoff_status="Ready for Review",
            )

        self.assertEqual(exit_code, 0)
        lint = payload["censor_evidence_lint"]
        self.assertEqual(lint["state"], "incomplete")
        self.assertEqual(lint["reason_code"], "missing_or_invalid_fields")
        self.assertIn("Context reconciliation", lint["missing_fields"])
        self.assertIn("Fixes", lint["missing_fields"])

    def test_plan_prose_outside_evidence_is_not_receipt_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = root / "docs/plans/prose_example.md"
            _write(
                plan,
                """\
                # Plan

                ## Notes
                Example text mentioning (Coder CENSOR) OK: Ready for Review validated. Observations: Second opinion: NO FINDINGS. Addendum (new angle): prose only. Context reconciliation: prose only. Counterfactuals considered: prose should not count. Fixes: none. Artifacts opened: `PLAN_PATH`. Review verdict seen: no live review artifact. Blocker IDs considered: `N/A`. Role-owned finding: none. Reconciliation: no live blocker. Final censor verdict: OK.

                ## Evidence
                - [2026-06-30 02:08 MSK] (Coder CENSOR) OK: Ready for Review validated; current=true. Observations: Second opinion: NO FINDINGS. Addendum (new angle): checked actual evidence row. Context reconciliation: current handoff matches plan. Counterfactuals considered: prose example could be selected, not confirmed because helper scans plan Evidence only. Fixes: none. Artifacts opened: `PLAN_PATH`. Review verdict seen: no live review artifact. Blocker IDs considered: `N/A`. Role-owned finding: none. Reconciliation: no live blocker. Final censor verdict: OK.
                """,
            )

            exit_code, payload = _payload(
                plan,
                censor_role="Coder",
                handoff_status="Ready for Review",
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["summary"]["receipt_count"], 1)
        self.assertEqual(payload["summary"]["complete_receipt_count"], 1)
        self.assertEqual(payload["censor_evidence_lint"]["state"], "complete")


if __name__ == "__main__":
    unittest.main()

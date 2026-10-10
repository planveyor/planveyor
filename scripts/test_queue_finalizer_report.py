from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import queue_finalizer_report
from scripts import plan_queue
from scripts.test_support.process_contract_fixtures import temporary_git_root


class QueueFinalizerReportTests(unittest.TestCase):
    def _write(self, root: Path, rel_path: str, text: str) -> Path:
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text).strip() + "\n", encoding="utf-8")
        return path

    def _write_bytes(self, root: Path, rel_path: str, payload: bytes) -> Path:
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return path

    def _write_state(self, root: Path, items: list[dict[str, object]]) -> None:
        for item in items:
            if item.get("state") == "skipped_manager_mode":
                item.setdefault(
                    "manager_mode_skip_id",
                    f"{int(item.get('order') or 0):032x}",
                )
        active_or_pending = next(
            (item for item in items if item.get("state") in {"active", "pending"}),
            None,
        )
        state = {
            "version": 1,
            "mode": "execution_queue",
            "resume_parent": "none",
            "source_plan": "docs/plans/parent.md",
            "parent_plan": "docs/plans/parent.md",
            "cursor": (
                int(active_or_pending["order"]) - 1
                if active_or_pending is not None
                else len(items)
            ),
            "items": items,
        }
        (root / ".planveyor.planqueue.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        log_lines = ["2026-06-19T00:00:00Z\tset\tplan=docs/plans/parent.md"]
        for item in items:
            if item.get("state") != "skipped_manager_mode":
                continue
            log_lines.append(
                f"{item.get('completed_at') or '2026-06-19T00:00:01Z'}\tskip_manager_mode"
                f"\tplan={item.get('plan')}"
                f"\torder={item.get('order')}"
                f"\tskip_phase={item.get('skip_phase')}"
                f"\tmanager_mode_skip_id={item.get('manager_mode_skip_id')}"
                f"\trequired_manager_mode={item.get('required_manager_mode')}"
                f"\tactual_manager_mode={item.get('actual_manager_mode')}"
                f"\tmanager_mode_state={item.get('manager_mode_state')}"
                f"\tmanager_mode_reason={item.get('manager_mode_reason')}"
            )
        (root / ".planveyor.planqueue.log").write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    def _plan(
        self,
        *,
        title: str = "child",
        status: str = "Done",
        review_refs: list[str] | None = None,
        review_rows: list[str] | None = None,
        promoted_seed: str | None = None,
        wave_family: str | None = None,
    ) -> str:
        review_lines = review_rows
        if review_lines is None:
            review_lines = [f"- Code review: `{ref}`" for ref in (review_refs or [])]
        review_section = "\n".join(review_lines) or "`N/A (why=fixture)`"
        route_section = "`N/A (why=fixture)`"
        if promoted_seed:
            route_section = f"""
            | Field | Value |
            | --- | --- |
            | accepted_route | developer_wave |
            | promoted_artifact_ref | `{promoted_seed}` |
            """
        wave_value = "null" if wave_family is None else json.dumps(wave_family)
        return f"""
            # Plan: {title}

            **Date:** 2026-06-19 00:00 MSK
            **Stage:** Stage 1
            **Priority:** P1
            **Plan type:** dev
            **Status:** {status}
            **Schema version:** plan.v1

            ## Meta (machine-readable JSON; required for new plans)
            ```json
            {{
              "plan_meta": {{
                "cluster": "process",
                "tags": ["fixture"],
                "wave_family": {wave_value},
                "phase_overlay": null,
                "phase_state": null,
                "parent": null,
                "next_plans": [],
                "depends_on": [],
                "followups_out": [],
                "canon_updates": []
              }}
            }}
            ```

            ## Promoted route artifact
            {route_section}

            ## Review artifacts
            {review_section}

            ## Evidence (chronological, append-only)
            - Fixture evidence.
            """

    def _run_cli_json(self, root: Path) -> tuple[int, dict[str, object], str]:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            rc = queue_finalizer_report.main(["--repo-root", str(root), "--format", "json"])
        raw_stdout = stdout.getvalue()
        return rc, json.loads(raw_stdout), raw_stdout

    def _review(self, status: str) -> str:
        return f"""
            # Code review fixture

            **Schema version:** review.v1
            **Status:** {status}

            ## S1 Blocker
            N/A
            """

    def test_complete_queue_emits_final_report_with_required_buckets(self) -> None:
        with temporary_git_root(prefix="queue_finalizer_green_") as tmpdir:
            root = Path(tmpdir)
            self._write(root, "docs/code_reviews/child.md", self._review("✅ OK"))
            self._write(
                root,
                "docs/plans/260619_0105_process_compact_censor_reviewer_receipt_protocol.md",
                self._plan(title="seed", status="Architect initial draft"),
            )
            self._write(
                root,
                "docs/plans/child.md",
                self._plan(
                    review_refs=["docs/code_reviews/child.md"],
                    promoted_seed="docs/plans/260619_0105_process_compact_censor_reviewer_receipt_protocol.md",
                ),
            )
            self._write(
                root,
                "docs/plans/260618_1758_process_plan_current_state_terminal_receipt.md",
                self._plan(
                    title="analysis",
                    status="Done",
                    wave_family="analysis_wave",
                    review_refs=["docs/code_reviews/analysis.md"],
                ),
            )
            self._write(root, "docs/code_reviews/analysis.md", self._review("✅ OK"))
            self._write(root, "docs/process_improvements/index.md", "# Index\n\n- PI-001 P1\n")
            self._write(root, "docs/plans/260617_2145_process_merge_range_verdict_digest.md", "# Digest\n")
            self._write_state(
                root,
                [
                    {"order": 1, "plan": "docs/plans/child.md", "state": "done", "final_status": "Done"},
                    {
                        "order": 2,
                        "plan": "docs/plans/260618_1758_process_plan_current_state_terminal_receipt.md",
                        "state": "done",
                        "final_status": "Done",
                    },
                ],
            )

            report = queue_finalizer_report.build_report(root)

        self.assertEqual(report["schema_version"], "queue_finalizer_report.v1")
        self.assertEqual(report["report_status"], "ok")
        self.assertTrue(report["queue"]["queue_complete"])
        self.assertEqual(report["queue"]["item_count"], 2)
        self.assertTrue(any(action["action"] == "git push" for action in report["owner_actions"]))
        self.assertIn("docs/code_reviews/child.md#Status", report["truth_hosts"])
        self.assertIn("planning_contour", report["cost_profile"]["counts"])
        self.assertTrue(
            any(bucket["state"] == "unavailable_or_deferred" for bucket in report["policy_buckets"]),
            report["policy_buckets"],
        )
        self.assertTrue(
            any(route["state"] == "accepted_seed_pending_implementation" for route in report["accepted_routes"]),
            report["accepted_routes"],
        )
        self.assertEqual(report["process_improvements"]["rows_by_urgency"], {"P1": 1})

    def test_mixed_done_and_manager_mode_skip_is_operationally_complete(self) -> None:
        with temporary_git_root(prefix="queue_finalizer_mixed_skip_") as tmpdir:
            root = Path(tmpdir)
            self._write(root, "docs/code_reviews/done.md", self._review("✅ OK"))
            self._write(
                root,
                "docs/plans/done.md",
                self._plan(status="Done", review_refs=["docs/code_reviews/done.md"]),
            )
            self._write(root, "docs/plans/skipped.md", self._plan(status="Ready for Coder"))
            skipped = {
                "order": 2,
                "plan": "docs/plans/skipped.md",
                "state": "skipped_manager_mode",
                "completed_at": "2026-06-19T00:00:01Z",
                "final_status": None,
                "runtime_class": None,
                "closeout_kind": "manager_mode_mismatch",
                "closeout_reason": "required_mode_mismatch",
                "skip_phase": "activation",
                "required_manager_mode": "manager-custom-pipeline",
                "actual_manager_mode": "manager-collab",
                "manager_mode_state": "mismatch",
                "manager_mode_reason": "required_mode_mismatch",
            }
            self._write_state(
                root,
                [
                    {"order": 1, "plan": "docs/plans/done.md", "state": "done", "final_status": "Done"},
                    skipped,
                ],
            )

            report = queue_finalizer_report.build_report(root)
            plain = queue_finalizer_report.render_plain(report)

        self.assertEqual(report["report_status"], "ok")
        self.assertTrue(report["queue"]["queue_complete"])
        self.assertEqual(report["queue"]["skipped_manager_mode_count"], 1)
        self.assertEqual(report["items"][1]["plan_status"], "Ready for Coder")
        self.assertEqual(report["items"][1]["completed_at"], "2026-06-19T00:00:01Z")
        self.assertEqual(report["items"][1]["manager_mode_skip_id"], f"{2:032x}")
        self.assertIn("required=manager-custom-pipeline", plain)

    def test_manager_mode_skip_with_stale_only_history_blocks(self) -> None:
        with tempfile.TemporaryDirectory(prefix="queue_finalizer_stale_skip_") as tmpdir:
            root = Path(tmpdir)
            self._write(root, "docs/plans/skipped.md", self._plan(status="Ready for Coder"))
            skipped = {
                "order": 1,
                "plan": "docs/plans/skipped.md",
                "state": "skipped_manager_mode",
                "completed_at": "2026-06-20T00:00:01Z",
                "final_status": None,
                "runtime_class": None,
                "closeout_kind": "manager_mode_mismatch",
                "closeout_reason": "required_mode_mismatch",
                "skip_phase": "activation",
                "required_manager_mode": "manager-custom-pipeline",
                "actual_manager_mode": "manager-collab",
                "manager_mode_state": "mismatch",
                "manager_mode_reason": "required_mode_mismatch",
            }
            self._write_state(root, [skipped])
            log_path = root / ".planveyor.planqueue.log"
            log_path.write_text(
                log_path.read_text(encoding="utf-8").replace(
                    "2026-06-20T00:00:01Z\tskip_manager_mode",
                    "2026-06-19T00:00:01Z\tskip_manager_mode",
                ),
                encoding="utf-8",
            )

            report = queue_finalizer_report.build_report(root)

        self.assertEqual(report["report_status"], "blocked")
        self.assertIn(
            "inconsistent_manager_mode_skip",
            {error["code"] for error in report["errors"]},
            report["errors"],
        )

    def test_manager_mode_skip_ignores_historical_rows_when_current_lifecycle_matches(self) -> None:
        with temporary_git_root(prefix="queue_finalizer_repeated_skip_") as tmpdir:
            root = Path(tmpdir)
            self._write(root, "docs/plans/skipped.md", self._plan(status="Ready for Coder"))
            skipped = {
                "order": 1,
                "plan": "docs/plans/skipped.md",
                "state": "skipped_manager_mode",
                "completed_at": "2026-06-20T00:00:01Z",
                "final_status": None,
                "runtime_class": None,
                "closeout_kind": "manager_mode_mismatch",
                "closeout_reason": "required_mode_mismatch",
                "skip_phase": "activation",
                "required_manager_mode": "manager-custom-pipeline",
                "actual_manager_mode": "manager-collab",
                "manager_mode_state": "mismatch",
                "manager_mode_reason": "required_mode_mismatch",
            }
            self._write_state(root, [skipped])
            log_path = root / ".planveyor.planqueue.log"
            current_history = log_path.read_text(encoding="utf-8")
            historical_row = next(
                line
                for line in current_history.splitlines()
                if "\tskip_manager_mode\t" in line
            ).replace(
                f"manager_mode_skip_id={1:032x}",
                f"manager_mode_skip_id={2:032x}",
            )
            log_path.write_text(
                current_history + historical_row + "\n",
                encoding="utf-8",
            )

            report = queue_finalizer_report.build_report(root)

        self.assertEqual(report["report_status"], "ok")
        self.assertNotIn(
            "inconsistent_manager_mode_skip",
            {error["code"] for error in report["errors"]},
            report["errors"],
        )

    def test_manager_mode_skip_rejects_conflicting_current_lifecycle_timestamp(self) -> None:
        with tempfile.TemporaryDirectory(prefix="queue_finalizer_conflicting_skip_") as tmpdir:
            root = Path(tmpdir)
            self._write(root, "docs/plans/skipped.md", self._plan(status="Ready for Coder"))
            skipped = {
                "order": 1,
                "plan": "docs/plans/skipped.md",
                "state": "skipped_manager_mode",
                "completed_at": "2026-06-20T00:00:01Z",
                "final_status": None,
                "runtime_class": None,
                "closeout_kind": "manager_mode_mismatch",
                "closeout_reason": "required_mode_mismatch",
                "skip_phase": "activation",
                "required_manager_mode": "manager-custom-pipeline",
                "actual_manager_mode": "manager-collab",
                "manager_mode_state": "mismatch",
                "manager_mode_reason": "required_mode_mismatch",
            }
            self._write_state(root, [skipped])
            log_path = root / ".planveyor.planqueue.log"
            current_history = log_path.read_text(encoding="utf-8")
            conflicting_row = next(
                line
                for line in current_history.splitlines()
                if "\tskip_manager_mode\t" in line
            ).replace(
                "2026-06-20T00:00:01Z\tskip_manager_mode",
                "2026-06-19T00:00:01Z\tskip_manager_mode",
            )
            log_path.write_text(
                current_history + conflicting_row + "\n",
                encoding="utf-8",
            )

            report = queue_finalizer_report.build_report(root)

        self.assertEqual(report["report_status"], "blocked")
        self.assertIn(
            "inconsistent_manager_mode_skip",
            {error["code"] for error in report["errors"]},
            report["errors"],
        )

    def test_incomplete_or_mismatched_manager_mode_skip_blocks(self) -> None:
        for case in (
            "missing_field",
            "missing_completed_at",
            "missing_lifecycle_id",
            "log_mismatch",
        ):
            with self.subTest(case=case), tempfile.TemporaryDirectory(prefix="queue_finalizer_bad_skip_") as tmpdir:
                root = Path(tmpdir)
                self._write(root, "docs/plans/skipped.md", self._plan(status="Ready for Coder"))
                skipped = {
                    "order": 1,
                    "plan": "docs/plans/skipped.md",
                    "state": "skipped_manager_mode",
                    "completed_at": "2026-06-19T00:00:01Z",
                    "final_status": None,
                    "runtime_class": None,
                    "closeout_kind": "manager_mode_mismatch",
                    "closeout_reason": "required_mode_mismatch",
                    "skip_phase": "activation",
                    "required_manager_mode": "manager-custom-pipeline",
                    "actual_manager_mode": "manager-collab",
                    "manager_mode_state": "mismatch",
                    "manager_mode_reason": "required_mode_mismatch",
                }
                if case == "missing_field":
                    skipped["manager_mode_reason"] = "wrong"
                elif case == "missing_completed_at":
                    skipped["completed_at"] = None
                elif case == "missing_lifecycle_id":
                    skipped["manager_mode_skip_id"] = "invalid"
                self._write_state(root, [skipped])
                if case == "log_mismatch":
                    log_path = root / ".planveyor.planqueue.log"
                    log_path.write_text(
                        log_path.read_text(encoding="utf-8").replace(
                            "actual_manager_mode=manager-collab",
                            "actual_manager_mode=manager-custom-pipeline",
                        ),
                        encoding="utf-8",
                    )

                report = queue_finalizer_report.build_report(root)

            self.assertEqual(report["report_status"], "blocked")
            self.assertIn(
                "inconsistent_manager_mode_skip",
                {error["code"] for error in report["errors"]},
                report["errors"],
            )

    def test_non_terminal_queue_is_blocked(self) -> None:
        with temporary_git_root(prefix="queue_finalizer_active_") as tmpdir:
            root = Path(tmpdir)
            self._write(root, "docs/plans/child.md", self._plan(status="Ready for Review"))
            self._write_state(root, [{"order": 1, "plan": "docs/plans/child.md", "state": "active"}])

            report = queue_finalizer_report.build_report(root)

        self.assertEqual(report["report_status"], "blocked")
        self.assertFalse(report["queue"]["queue_complete"])
        self.assertIn("non_terminal_queue_item", {error["code"] for error in report["errors"]})

    def test_missing_state_log_or_plan_truth_hosts_block(self) -> None:
        for missing in ("state", "log", "plan"):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory(prefix="queue_finalizer_missing_host_") as tmpdir:
                root = Path(tmpdir)
                self._write(root, "docs/code_reviews/child.md", self._review("✅ OK"))
                self._write(
                    root,
                    "docs/plans/child.md",
                    self._plan(review_refs=["docs/code_reviews/child.md"]),
                )
                self._write_state(
                    root,
                    [{"order": 1, "plan": "docs/plans/child.md", "state": "done", "final_status": "Done"}],
                )
                missing_path = {
                    "state": root / ".planveyor.planqueue.json",
                    "log": root / ".planveyor.planqueue.log",
                    "plan": root / "docs/plans/child.md",
                }[missing]
                missing_path.unlink()

                report = queue_finalizer_report.build_report(root)

            self.assertEqual(report["report_status"], "blocked")
            self.assertTrue(
                {error["code"] for error in report["errors"]}
                & {"missing_truth_host", "queue_recovery_required"}
            )

    def test_semantic_terminal_queue_state_with_non_terminal_plan_status_blocks(self) -> None:
        with temporary_git_root(prefix="queue_finalizer_semantic_mismatch_") as tmpdir:
            root = Path(tmpdir)
            self._write(root, "docs/code_reviews/child.md", self._review("✅ OK"))
            self._write(
                root,
                "docs/plans/child.md",
                self._plan(
                    status="Ready for Review",
                    review_refs=["docs/code_reviews/child.md"],
                ),
            )
            self._write_state(
                root,
                [{"order": 1, "plan": "docs/plans/child.md", "state": "done", "final_status": "Done"}],
            )

            report = queue_finalizer_report.build_report(root)

        self.assertEqual(report["report_status"], "blocked")
        self.assertIn("inconsistent_truth_host", {error["code"] for error in report["errors"]})

    def test_invalid_transaction_marker_blocks_final_report(self) -> None:
        with tempfile.TemporaryDirectory(prefix="queue_finalizer_invalid_marker_") as tmpdir:
            root = Path(tmpdir)
            self._write(root, "docs/plans/child.md", self._plan())
            self._write_state(
                root,
                [{"order": 1, "plan": "docs/plans/child.md", "state": "done", "final_status": "Done"}],
            )
            (root / ".planveyor.planqueue.txn.json").write_text("{}\n", encoding="utf-8")

            report = queue_finalizer_report.build_report(root)

        self.assertEqual(report["report_status"], "blocked")
        self.assertFalse(report["queue"]["queue_complete"])
        self.assertEqual(report["queue"]["recovery_state"], "blocked")
        self.assertIn("queue_recovery_required", {error["code"] for error in report["errors"]})

    def test_pending_transaction_marker_blocks_final_report(self) -> None:
        with temporary_git_root(prefix="queue_finalizer_pending_marker_") as tmpdir:
            root = Path(tmpdir)
            self._write(root, "docs/plans/child.md", self._plan())
            self._write_state(
                root,
                [{"order": 1, "plan": "docs/plans/child.md", "state": "done", "final_status": "Done"}],
            )
            paths = plan_queue.QueuePaths(
                root=root,
                state_path=root / ".planveyor.planqueue.json",
                log_path=root / ".planveyor.planqueue.log",
            )
            after_state = json.loads(paths.state_path.read_text(encoding="utf-8"))
            after_state["mode"] = "post_transaction"

            def interrupt(phase: str, _paths: plan_queue.QueuePaths, _marker: dict[str, object]) -> None:
                if phase == "marker":
                    raise RuntimeError("interrupt-after-marker")

            plan_queue._TRANSACTION_PHASE_HOOK = interrupt
            try:
                with self.assertRaisesRegex(RuntimeError, "interrupt-after-marker"):
                    with plan_queue.queue_lock(paths, "exclusive", command="fixture", timeout=0.1):
                        plan_queue._commit_transaction(
                            paths,
                            operation="fixture",
                            after_state=after_state,
                            audit_rows=[plan_queue._audit_row("fixture")],
                        )
            finally:
                plan_queue._TRANSACTION_PHASE_HOOK = None

            report = queue_finalizer_report.build_report(root)

        self.assertEqual(report["report_status"], "blocked")
        self.assertFalse(report["queue"]["queue_complete"])
        self.assertEqual(report["queue"]["recovery_state"], "blocked")
        self.assertIn("queue_recovery_required", {error["code"] for error in report["errors"]})

    def test_missing_review_truth_host_blocks(self) -> None:
        with temporary_git_root(prefix="queue_finalizer_missing_") as tmpdir:
            root = Path(tmpdir)
            self._write(root, "docs/plans/child.md", self._plan(review_refs=["docs/code_reviews/missing.md"]))
            self._write_state(root, [{"order": 1, "plan": "docs/plans/child.md", "state": "done", "final_status": "Done"}])

            report = queue_finalizer_report.build_report(root)

        self.assertEqual(report["report_status"], "blocked")
        self.assertIn("missing_truth_host", {error["code"] for error in report["errors"]})
        self.assertTrue(any(error["truth_host"] == "docs/code_reviews/missing.md" for error in report["errors"]))

    def test_missing_doc_review_truth_host_blocks(self) -> None:
        with temporary_git_root(prefix="queue_finalizer_missing_doc_review_") as tmpdir:
            root = Path(tmpdir)
            self._write(root, "docs/plans/child.md", self._plan(review_refs=["docs/doc_reviews/missing.md"]))
            self._write_state(root, [{"order": 1, "plan": "docs/plans/child.md", "state": "done", "final_status": "Done"}])

            report = queue_finalizer_report.build_report(root)

        self.assertEqual(report["report_status"], "blocked")
        self.assertIn("missing_truth_host", {error["code"] for error in report["errors"]})
        self.assertTrue(any(error["truth_host"] == "docs/doc_reviews/missing.md" for error in report["errors"]))

    def test_ambiguous_review_truth_host_blocks(self) -> None:
        with temporary_git_root(prefix="queue_finalizer_ambiguous_") as tmpdir:
            root = Path(tmpdir)
            self._write(root, "docs/code_reviews/one.md", self._review("✅ OK"))
            self._write(root, "docs/code_reviews/two.md", self._review("✅ OK"))
            self._write(
                root,
                "docs/plans/child.md",
                self._plan(review_refs=["docs/code_reviews/one.md", "docs/code_reviews/two.md"]),
            )
            self._write_state(root, [{"order": 1, "plan": "docs/plans/child.md", "state": "done", "final_status": "Done"}])

            report = queue_finalizer_report.build_report(root)

        self.assertEqual(report["report_status"], "blocked")
        self.assertIn("ambiguous_truth_host", {error["code"] for error in report["errors"]})

    def test_red_review_truth_host_blocks_even_when_queue_done(self) -> None:
        with temporary_git_root(prefix="queue_finalizer_red_") as tmpdir:
            root = Path(tmpdir)
            self._write(root, "docs/code_reviews/child.md", self._review("❌ S1 Blocker(s)"))
            self._write(root, "docs/plans/child.md", self._plan(review_refs=["docs/code_reviews/child.md"]))
            self._write_state(root, [{"order": 1, "plan": "docs/plans/child.md", "state": "done", "final_status": "Done"}])

            report = queue_finalizer_report.build_report(root)

        self.assertEqual(report["report_status"], "blocked")
        self.assertIn("red_truth_host", {error["code"] for error in report["errors"]})
        self.assertTrue(any(error["truth_host"] == "docs/code_reviews/child.md#Status" for error in report["errors"]))

    def test_red_doc_review_truth_host_blocks_even_when_queue_done(self) -> None:
        with temporary_git_root(prefix="queue_finalizer_red_doc_review_") as tmpdir:
            root = Path(tmpdir)
            self._write(root, "docs/doc_reviews/child.md", self._review("❌ S1 Blocker(s)"))
            self._write(root, "docs/plans/child.md", self._plan(review_refs=["docs/doc_reviews/child.md"]))
            self._write_state(root, [{"order": 1, "plan": "docs/plans/child.md", "state": "done", "final_status": "Done"}])

            report = queue_finalizer_report.build_report(root)

        self.assertEqual(report["report_status"], "blocked")
        self.assertIn("red_truth_host", {error["code"] for error in report["errors"]})
        self.assertTrue(any(error["truth_host"] == "docs/doc_reviews/child.md#Status" for error in report["errors"]))

    def test_no_blockers_review_status_stays_green(self) -> None:
        with temporary_git_root(prefix="queue_finalizer_no_blockers_") as tmpdir:
            root = Path(tmpdir)
            self._write(root, "docs/code_reviews/child.md", self._review("✅ No blockers"))
            self._write(root, "docs/plans/child.md", self._plan(review_refs=["docs/code_reviews/child.md"]))
            self._write_state(root, [{"order": 1, "plan": "docs/plans/child.md", "state": "done", "final_status": "Done"}])

            report = queue_finalizer_report.build_report(root)

        self.assertEqual(report["report_status"], "ok")
        self.assertEqual(report["items"][0]["review_artifacts"][0]["verdict"], "ok")

    def test_doc_review_no_blockers_status_is_discovered_and_green(self) -> None:
        with temporary_git_root(prefix="queue_finalizer_doc_review_green_") as tmpdir:
            root = Path(tmpdir)
            self._write(root, "docs/doc_reviews/child.md", self._review("✅ No blockers"))
            self._write(root, "docs/plans/child.md", self._plan(review_refs=["docs/doc_reviews/child.md"]))
            self._write_state(root, [{"order": 1, "plan": "docs/plans/child.md", "state": "done", "final_status": "Done"}])

            report = queue_finalizer_report.build_report(root)

        self.assertEqual(report["report_status"], "ok")
        self.assertEqual(report["items"][0]["review_artifacts"][0]["path"], "docs/doc_reviews/child.md")
        self.assertIn("docs/doc_reviews/child.md#Status", report["truth_hosts"])

    def test_closed_non_executable_ready_for_planner_is_not_inconsistent(self) -> None:
        with temporary_git_root(prefix="queue_finalizer_nonexec_") as tmpdir:
            root = Path(tmpdir)
            self._write(root, "docs/plans/reference.md", self._plan(status="Ready for Planner"))
            self._write_state(
                root,
                [
                    {
                        "order": 1,
                        "plan": "docs/plans/reference.md",
                        "state": "closed_non_executable",
                        "final_status": "Ready for Planner",
                        "runtime_class": "verified_reference_child",
                    }
                ],
            )

            report = queue_finalizer_report.build_report(root)

        self.assertEqual(report["report_status"], "ok")
        self.assertEqual(report["items"][0]["cost_profile"], "non_executable_reference")

    def test_cli_json_returns_nonzero_for_blocked_report(self) -> None:
        with tempfile.TemporaryDirectory(prefix="queue_finalizer_cli_") as tmpdir:
            root = Path(tmpdir)
            self._write(root, "docs/plans/child.md", self._plan(status="Ready for Review"))
            self._write_state(root, [{"order": 1, "plan": "docs/plans/child.md", "state": "active"}])

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                rc = queue_finalizer_report.main(["--repo-root", str(root), "--format", "json"])

        self.assertEqual(rc, 2)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["report_status"], "blocked")


    def test_canonical_primary_ignores_supporting_history_and_binary_assets_via_cli(self) -> None:
        with temporary_git_root(prefix="queue_finalizer_canonical_assets_") as tmpdir:
            root = Path(tmpdir)
            self._write(root, "docs/code_reviews/primary.md", self._review("✅ OK"))
            self._write(root, "docs/code_reviews/history.md", self._review("❌ S1 Blocker(s)"))
            self._write(root, "docs/code_reviews/source.md", self._review("❌ S1 Blocker(s)"))
            self._write_bytes(root, "docs/code_reviews/assets/proof.png", b"\x89PNG\r\n\x1a\nfixture")
            self._write(
                root,
                "docs/plans/child.md",
                self._plan(
                    review_rows=[
                        "- Code review (primary): `docs/code_reviews/primary.md`",
                        "- Historical review: `docs/code_reviews/history.md`",
                        "- Source review: `docs/code_reviews/source.md`",
                        "- Supporting visual: `docs/code_reviews/assets/proof.png`",
                    ]
                ),
            )
            self._write_state(root, [{"order": 1, "plan": "docs/plans/child.md", "state": "done", "final_status": "Done"}])

            rc, report, raw_stdout = self._run_cli_json(root)

        self.assertEqual(rc, 0)
        self.assertNotIn("Traceback", raw_stdout)
        self.assertEqual(report["schema_version"], "queue_finalizer_report.v1")
        self.assertEqual(report["report_status"], "ok")
        self.assertEqual(
            [artifact["path"] for artifact in report["items"][0]["review_artifacts"]],
            ["docs/code_reviews/primary.md"],
        )
        self.assertNotIn("docs/code_reviews/history.md#Status", report["truth_hosts"])
        self.assertNotIn("docs/code_reviews/assets/proof.png#Status", report["truth_hosts"])

    def test_two_canonical_review_rows_remain_ambiguous(self) -> None:
        with temporary_git_root(prefix="queue_finalizer_canonical_ambiguous_") as tmpdir:
            root = Path(tmpdir)
            for name in ("one", "two"):
                self._write(root, f"docs/code_reviews/{name}.md", self._review("✅ OK"))
            self._write(
                root,
                "docs/plans/child.md",
                self._plan(
                    review_rows=[
                        "- Code review (primary): `docs/code_reviews/one.md`",
                        "- Code review (primary): `docs/code_reviews/two.md`",
                        "- Historical review: `docs/code_reviews/history.md`",
                    ]
                ),
            )
            self._write_state(root, [{"order": 1, "plan": "docs/plans/child.md", "state": "done", "final_status": "Done"}])

            report = queue_finalizer_report.build_report(root)

        self.assertEqual(report["report_status"], "blocked")
        ambiguity = next(error for error in report["errors"] if error["code"] == "ambiguous_truth_host")
        self.assertEqual(ambiguity["candidates"], ["docs/code_reviews/one.md", "docs/code_reviews/two.md"])

    def test_legacy_exact_boundary_rejects_png_prefix_and_keeps_valid_control(self) -> None:
        with temporary_git_root(prefix="queue_finalizer_legacy_boundary_") as tmpdir:
            root = Path(tmpdir)
            self._write(root, "docs/code_reviews/live.md", self._review("✅ OK"))
            self._write(root, "docs/reviews/legacy.md", self._review("✅ OK"))
            self._write(
                root,
                "docs/plans/invalid.md",
                self._plan(review_rows=["- Code review: `docs/code_reviews/live.md.png`"]),
            )
            self._write(
                root,
                "docs/plans/valid.md",
                self._plan(review_rows=["- Code review: `docs/reviews/legacy.md`"]),
            )
            self._write_state(
                root,
                [
                    {"order": 1, "plan": "docs/plans/invalid.md", "state": "done", "final_status": "Done"},
                    {"order": 2, "plan": "docs/plans/valid.md", "state": "done", "final_status": "Done"},
                ],
            )

            report = queue_finalizer_report.build_report(root)

        self.assertEqual(report["report_status"], "blocked")
        invalid_item, valid_item = report["items"]
        self.assertEqual(invalid_item["review_artifacts"], [])
        self.assertEqual(valid_item["review_artifacts"][0]["path"], "docs/reviews/legacy.md")
        self.assertNotIn("docs/code_reviews/live.md#Status", report["truth_hosts"])
        self.assertIn("missing_truth_host", {error["code"] for error in report["errors"]})

    def test_literal_boundaries_reject_canonical_and_legacy_green_decoys(self) -> None:
        malformed_refs = (
            "docs/code_reviews/live.md@evil",
            "docs/code_reviews/live.md?download=1",
            "docs/code_reviews/live.md:evil",
            "docs/code_reviews/live.md;evil",
            "docs/code_reviews/live.md,evil",
            "docs/code_reviews/live.md|evil",
            "docs/code_reviews/live.md)evil",
            "/tmp/docs/code_reviews/live.md",
            "xdocs/code_reviews/live.md",
        )
        for carrier, label in (
            ("canonical", "Code review (primary)"),
            ("legacy", "Code review"),
        ):
            for malformed_ref in malformed_refs:
                with self.subTest(carrier=carrier, malformed_ref=malformed_ref), temporary_git_root(
                    prefix="queue_finalizer_literal_boundary_"
                ) as tmpdir:
                    root = Path(tmpdir)
                    self._write(root, "docs/code_reviews/live.md", self._review("✅ OK"))
                    self._write(
                        root,
                        "docs/plans/child.md",
                        self._plan(review_rows=[f"- {label}: `{malformed_ref}`"]),
                    )
                    self._write_state(
                        root,
                        [{"order": 1, "plan": "docs/plans/child.md", "state": "done", "final_status": "Done"}],
                    )

                    rc, report, raw_stdout = self._run_cli_json(root)

                self.assertEqual(rc, 2)
                self.assertNotIn("Traceback", raw_stdout)
                self.assertEqual(report["report_status"], "blocked")
                self.assertEqual(report["items"][0]["review_artifacts"], [])
                self.assertNotIn("docs/code_reviews/live.md#Status", report["truth_hosts"])
                self.assertIn("missing_truth_host", {error["code"] for error in report["errors"]})

    def test_unbackticked_malformed_anchors_reject_canonical_and_legacy_green_decoys(self) -> None:
        malformed_refs = (
            "docs/code_reviews/live.md#B1:evil",
            "docs/code_reviews/live.md#",
            "docs/code_reviews/live.md##B1",
            "docs/code_reviews/live.md#B1)evil",
            "docs/code_reviews/live.md#B1]evil",
            "docs/code_reviews/live.md#B1}evil",
            "docs/code_reviews/live.md#B1>evil",
            "docs/code_reviews/live.md#B1;evil",
            "docs/code_reviews/live.md#B1,evil",
            "docs/code_reviews/live.md#B1|evil",
        )
        for carrier, label in (
            ("canonical", "Code review (primary)"),
            ("legacy", "Code review"),
        ):
            for malformed_ref in malformed_refs:
                with self.subTest(carrier=carrier, malformed_ref=malformed_ref), temporary_git_root(
                    prefix="queue_finalizer_unbackticked_anchor_"
                ) as tmpdir:
                    root = Path(tmpdir)
                    self._write(root, "docs/code_reviews/live.md", self._review("✅ OK"))
                    self._write(
                        root,
                        "docs/plans/child.md",
                        self._plan(review_rows=[f"- {label}: {malformed_ref}"]),
                    )
                    self._write_state(
                        root,
                        [{"order": 1, "plan": "docs/plans/child.md", "state": "done", "final_status": "Done"}],
                    )

                    rc, report, raw_stdout = self._run_cli_json(root)

                self.assertEqual(rc, 2)
                self.assertNotIn("Traceback", raw_stdout)
                self.assertEqual(report["report_status"], "blocked")
                self.assertEqual(report["items"][0]["review_artifacts"], [])
                self.assertNotIn("docs/code_reviews/live.md#Status", report["truth_hosts"])
                self.assertIn("missing_truth_host", {error["code"] for error in report["errors"]})

    def test_literal_boundaries_accept_anchor_and_delimiter_controls(self) -> None:
        cases = (
            (
                "canonical",
                "docs/code_reviews/live.md",
                "- Code review (primary): (docs/code_reviews/live.md#B1)",
            ),
            (
                "legacy",
                "docs/reviews/live.md",
                "- Code review: (docs/reviews/live.md#B1)",
            ),
            (
                "canonical-code-span-anchor",
                "docs/code_reviews/live.md",
                "- Code review (primary): ``docs/code_reviews/live.md#B1``",
            ),
            (
                "canonical-anchor-colon",
                "docs/code_reviews/live.md",
                "- Code review (primary): docs/code_reviews/live.md#B1: evidence",
            ),
            (
                "canonical-colon",
                "docs/code_reviews/live.md",
                "- Code review (primary): docs/code_reviews/live.md: evidence",
            ),
            (
                "canonical-semicolon",
                "docs/code_reviews/live.md",
                "- Code review (primary): docs/code_reviews/live.md; evidence",
            ),
            (
                "canonical-comma",
                "docs/code_reviews/live.md",
                "- Code review (primary): docs/code_reviews/live.md, evidence",
            ),
            (
                "canonical-pipe",
                "docs/code_reviews/live.md",
                "- Code review (primary): docs/code_reviews/live.md | evidence",
            ),
            (
                "canonical-parenthesis",
                "docs/code_reviews/live.md",
                "- Code review (primary): (docs/code_reviews/live.md)",
            ),
        )
        for carrier, review_rel, review_row in cases:
            with self.subTest(carrier=carrier), temporary_git_root(
                prefix="queue_finalizer_literal_control_"
            ) as tmpdir:
                root = Path(tmpdir)
                self._write(root, review_rel, self._review("✅ OK"))
                self._write(root, "docs/plans/child.md", self._plan(review_rows=[review_row]))
                self._write_state(
                    root,
                    [{"order": 1, "plan": "docs/plans/child.md", "state": "done", "final_status": "Done"}],
                )

                rc, report, raw_stdout = self._run_cli_json(root)

            self.assertEqual(rc, 0)
            self.assertNotIn("Traceback", raw_stdout)
            self.assertEqual(report["report_status"], "ok")
            self.assertEqual(report["items"][0]["review_artifacts"][0]["path"], review_rel)

    def test_invalid_canonical_png_never_falls_back_to_green_legacy_or_decoy(self) -> None:
        with temporary_git_root(prefix="queue_finalizer_canonical_boundary_") as tmpdir:
            root = Path(tmpdir)
            self._write(root, "docs/code_reviews/live.md", self._review("✅ OK"))
            self._write(root, "docs/code_reviews/legacy.md", self._review("✅ OK"))
            self._write(
                root,
                "docs/plans/child.md",
                self._plan(
                    review_rows=[
                        "- Code review (primary): `docs/code_reviews/live.md.png`",
                        "- Code review: `docs/code_reviews/legacy.md`",
                        "- Supporting review: `docs/code_reviews/live.md`",
                    ]
                ),
            )
            self._write_state(root, [{"order": 1, "plan": "docs/plans/child.md", "state": "done", "final_status": "Done"}])

            rc, report, raw_stdout = self._run_cli_json(root)

        self.assertEqual(rc, 2)
        self.assertNotIn("Traceback", raw_stdout)
        self.assertEqual(report["report_status"], "blocked")
        self.assertEqual(report["items"][0]["review_artifacts"], [])
        self.assertNotIn("docs/code_reviews/live.md#Status", report["truth_hosts"])
        self.assertNotIn("docs/code_reviews/legacy.md#Status", report["truth_hosts"])
        self.assertIn("missing_truth_host", {error["code"] for error in report["errors"]})

    def test_empty_canonical_carrier_never_falls_back_to_green_legacy(self) -> None:
        with temporary_git_root(prefix="queue_finalizer_empty_canonical_") as tmpdir:
            root = Path(tmpdir)
            self._write(root, "docs/code_reviews/legacy.md", self._review("✅ OK"))
            self._write(
                root,
                "docs/plans/child.md",
                self._plan(
                    review_rows=[
                        "- Code review (primary): `N/A (why=fixture)`",
                        "- Code review: `docs/code_reviews/legacy.md`",
                    ]
                ),
            )
            self._write_state(root, [{"order": 1, "plan": "docs/plans/child.md", "state": "done", "final_status": "Done"}])

            report = queue_finalizer_report.build_report(root)

        self.assertEqual(report["report_status"], "blocked")
        self.assertEqual(report["items"][0]["review_artifacts"], [])
        self.assertNotIn("docs/code_reviews/legacy.md#Status", report["truth_hosts"])
        self.assertIn("missing_truth_host", {error["code"] for error in report["errors"]})

    def test_invalid_canonical_asset_and_unknown_status_remain_fail_closed(self) -> None:
        with temporary_git_root(prefix="queue_finalizer_canonical_fail_closed_") as tmpdir:
            root = Path(tmpdir)
            self._write_bytes(root, "docs/code_reviews/assets/claimed.md", b"\xffnot-markdown")
            self._write(root, "docs/code_reviews/pending.md", self._review("Pending"))
            self._write(
                root,
                "docs/plans/asset.md",
                self._plan(review_rows=["- Code review (primary): `docs/code_reviews/assets/claimed.md`"]),
            )
            self._write(
                root,
                "docs/plans/pending.md",
                self._plan(review_rows=["- Code review (primary): `docs/code_reviews/pending.md`"]),
            )
            self._write_state(
                root,
                [
                    {"order": 1, "plan": "docs/plans/asset.md", "state": "done", "final_status": "Done"},
                    {"order": 2, "plan": "docs/plans/pending.md", "state": "done", "final_status": "Done"},
                ],
            )

            report = queue_finalizer_report.build_report(root)

        codes = {error["code"] for error in report["errors"]}
        self.assertEqual(report["report_status"], "blocked")
        self.assertIn("missing_truth_host", codes)
        self.assertIn("inconsistent_truth_host", codes)
        self.assertNotIn("unreadable_truth_host", codes)

    def test_unreadable_mandatory_truth_hosts_return_structured_cli_json(self) -> None:
        for unreadable_host in ("review", "plan", "seed"):
            with self.subTest(unreadable_host=unreadable_host), temporary_git_root(
                prefix="queue_finalizer_unreadable_"
            ) as tmpdir:
                root = Path(tmpdir)
                self._write(root, "docs/code_reviews/review.md", self._review("✅ OK"))
                self._write(root, "docs/plans/seed.md", self._plan(title="seed", status="Architect initial draft"))
                self._write(
                    root,
                    "docs/plans/child.md",
                    self._plan(
                        review_rows=["- Code review (primary): `docs/code_reviews/review.md`"],
                        promoted_seed="docs/plans/seed.md",
                    ),
                )
                unreadable_path = {
                    "review": "docs/code_reviews/review.md",
                    "plan": "docs/plans/child.md",
                    "seed": "docs/plans/seed.md",
                }[unreadable_host]
                self._write_bytes(root, unreadable_path, b"\xffnot-utf8")
                self._write_state(root, [{"order": 1, "plan": "docs/plans/child.md", "state": "done", "final_status": "Done"}])

                rc, report, raw_stdout = self._run_cli_json(root)

            self.assertEqual(rc, 2)
            self.assertNotIn("Traceback", raw_stdout)
            self.assertEqual(report["report_status"], "blocked")
            self.assertTrue(
                any(
                    error["code"] == "unreadable_truth_host" and error["truth_host"] == unreadable_path
                    for error in report["errors"]
                ),
                report["errors"],
            )

    def test_unreadable_process_improvements_is_advisory(self) -> None:
        with temporary_git_root(prefix="queue_finalizer_unreadable_pi_") as tmpdir:
            root = Path(tmpdir)
            self._write(root, "docs/code_reviews/review.md", self._review("✅ OK"))
            self._write(
                root,
                "docs/plans/child.md",
                self._plan(review_rows=["- Code review (primary): `docs/code_reviews/review.md`"]),
            )
            self._write_bytes(root, "docs/process_improvements/index.md", b"\xffnot-utf8")
            self._write(root, "docs/process_improvements/deferred.md", "# Deferred\n\n- PI-001 P1")
            self._write_state(root, [{"order": 1, "plan": "docs/plans/child.md", "state": "done", "final_status": "Done"}])

            report = queue_finalizer_report.build_report(root)

        self.assertEqual(report["report_status"], "ok")
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["process_improvements"]["state"], "unavailable_or_deferred")
        self.assertCountEqual(
            report["process_improvements"]["truth_hosts"],
            ["docs/process_improvements/index.md", "docs/process_improvements/deferred.md"],
        )
        self.assertEqual(report["process_improvements"]["rows_by_urgency"], {})


if __name__ == "__main__":
    unittest.main()

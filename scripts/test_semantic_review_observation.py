#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from textwrap import dedent


SCRIPT_PATH = Path(__file__).with_name("semantic_review_observation.py")


class SemanticReviewObservationCliTests(unittest.TestCase):
    PLAN_REL = "docs/plans/260801_1622_cli_fixture.md"
    DRAFT_REL = "docs/code_drafts/260801_1622_cli_fixture__code_draft.md"
    REVIEW_REL = "docs/code_reviews/260801_1622_cli_fixture.md"

    def _declarations(self) -> str:
        return dedent(
            """\
            ### State-transition declarations
            - `before-state`: carrier=docs/plans/README.md#semantic; identity=semantic-review-observation.v1; expected=absent
            - `allowed mutation inventory`: writer=coder; entrypoint=semantic-cli-fixture; targets=["scripts/example.py"]
            - `after-state`: carrier=docs/plans/README.md#semantic; identity=semantic-review-observation.v1; expected=present
            - `protected-target post-review continuity`: targets=["scripts/example.py"]; on_change=same-file-review-rerun
            """
        ).rstrip()

    def _review_text(
        self,
        target: str,
        *,
        blocker_ids: tuple[int, ...] = (),
        status: str | None = None,
    ) -> str:
        status = status or ("❌ S1 blocker(ы)" if blocker_ids else "✅ OK")
        review = dedent(
            f"""\
            # Code review: CLI fixture

            **Target:** {target}
            **Status:** {status}

            ## reviewer_code_contracts

            - Lane status: complete

            ## Lane synthesis / aggregate verdict

            - Aggregate status: {status}
            """
        )
        if blocker_ids:
            review += "\n## S1 Blocker\n\n" + "\n\n".join(
                dedent(
                    f"""\
                    ### B{blocker_id}) CLI fixture blocker

                    - Blocker ID: B{blocker_id}
                    - Current state: open
                    """
                ).rstrip()
                for blocker_id in blocker_ids
            ) + "\n"
        return review

    def _plan_text(self, *, marker_rows: str | None = None, evidence: str = "") -> str:
        marker_rows = marker_rows or "\n".join(
            (
                "- `schema=semantic_review_observation.v1`",
                "- `mode=required`",
                "- `writer=reviewer_code_contracts`",
            )
        )
        return dedent(
            f"""\
            # Plan: semantic CLI fixture

            **Status:** Ready for Review

            - Code draft(s): `{self.DRAFT_REL}`

            ## Decisions (final)
            - CLI fixture.

            ## Scope
            - [ ] CLI fixture.

            ## Out of scope
            - None.

            ## Changes (by area)
            - Helper: CLI fixture.

            ## Acceptance criteria / DoD
            - [ ] CLI fixture.

            ## Tests
            - CLI fixture.

            ## Commands
            - python3 -B scripts/semantic_review_observation.py

            ## Reviewability preflight receipt

            ### Semantic review observation
            __MARKER_ROWS__

            __DECLARATIONS__

            ## Review artifacts

            - Code review (primary): `{self.REVIEW_REL}`

            ## Evidence
            __EVIDENCE__
            """
        ).replace("__MARKER_ROWS__", marker_rows).replace("__DECLARATIONS__", self._declarations()).replace(
            "__EVIDENCE__", evidence
        )

    def _write_fixture(self, root: Path, *, marker_rows: str | None = None, evidence: str = "") -> Path:
        (root / ".git").mkdir()
        plan = root / self.PLAN_REL
        draft = root / self.DRAFT_REL
        review = root / self.REVIEW_REL
        target = root / "scripts/example.py"
        for item in (plan, draft, review, target):
            item.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# fixture\n", encoding="utf-8")
        review.write_text("# Code review\n\n**Target:** BUNDLE=current bundle_sha256=cli\n", encoding="utf-8")
        draft.write_text(
            dedent(
                f"""\
                # Code draft: CLI fixture

                ```json
                {{"code_draft_meta":{{"plan":"{self.PLAN_REL}","targets":[{{"path":"scripts/example.py"}}],"deleted_paths":[]}}}}
                ```

                ## Reviewability preflight receipt

                __DECLARATIONS__
                """
            ).replace("__DECLARATIONS__", self._declarations()),
            encoding="utf-8",
        )
        plan.write_text(self._plan_text(marker_rows=marker_rows, evidence=evidence), encoding="utf-8")
        return plan

    def _run(self, plan: Path, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT_PATH), "--plan", str(plan), *extra],
            check=False,
            text=True,
            capture_output=True,
        )

    def test_json_and_text_clean_waiting_are_stdout_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = self._write_fixture(Path(tmpdir))
            before = plan.read_bytes()
            json_run = self._run(plan, "--format", "json")
            self.assertEqual(json_run.returncode, 0, json_run.stderr)
            report = json.loads(json_run.stdout)
            self.assertEqual(report["schema_version"], "semantic_review_observation_report.v1")
            self.assertEqual((report["state"], report["reason_code"]), ("not_available", "risk_generation_not_available"))
            self.assertEqual(plan.read_bytes(), before)

            text_run = self._run(plan, "--format", "text")
            self.assertEqual(text_run.returncode, 0, text_run.stderr)
            self.assertIn("semantic_review_observation: not_available", text_run.stdout)
            self.assertIn("reason_code: risk_generation_not_available", text_run.stdout)

    def test_blocked_contract_is_nonzero_and_mutation_flags_are_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = self._write_fixture(
                Path(tmpdir),
                marker_rows="\n".join(
                    (
                        "- `schema=semantic_review_observation.v1`",
                        "- `mode=required`",
                        "- `writer=not_reviewer_code_contracts`",
                    )
                ),
            )
            blocked = self._run(plan, "--format", "json")
            self.assertEqual(blocked.returncode, 1)
            report = json.loads(blocked.stdout)
            self.assertEqual((report["state"], report["reason_code"]), ("blocked", "activation_invalid"))

            forbidden = self._run(plan, "--format", "json", "--write")
            self.assertNotEqual(forbidden.returncode, 0)
            self.assertIn("unrecognized arguments", forbidden.stderr)

    def test_unbound_semantic_final_is_validation_first_blocked_without_write(self) -> None:
        unbound_final = "```json\n" + json.dumps(
            {"schema_version": "semantic_review_observation.v1", "observation_id": "sro_" + "0" * 64}
        ) + "\n```"
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = self._write_fixture(Path(tmpdir), evidence=unbound_final)
            before = plan.read_bytes()
            result = self._run(plan, "--format", "json")
            self.assertEqual(result.returncode, 1, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual((report["state"], report["reason_code"]), ("blocked", "risk_lane_selection_blocked"))
            self.assertTrue(any(error["code"] == "semantic_observation_unbound" for error in report["errors"]))
            self.assertEqual(plan.read_bytes(), before)

    def test_cli_projects_proposal_materialization_and_valid_readback_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = self._write_fixture(root)
            target = "semantic-cli-fixture-target"
            (root / self.REVIEW_REL).write_text(self._review_text(target), encoding="utf-8")
            risk = {
                "run_id": "reviewer_code_risk:cli:20260802T180000Z",
                "lane_id": "reviewer_code_risk",
                "target_snapshot": target,
                "lane_status": "complete",
                "current": True,
            }
            risk_fence = "```json\n" + json.dumps(risk, indent=2) + "\n```"
            plan.write_text(self._plan_text(evidence=risk_fence), encoding="utf-8")
            before = plan.read_bytes()
            proposal_required = self._run(plan, "--format", "json")
            self.assertEqual(proposal_required.returncode, 0, proposal_required.stderr)
            self.assertEqual(
                (json.loads(proposal_required.stdout)["state"], json.loads(proposal_required.stdout)["reason_code"]),
                ("ready_to_materialize", "role_proposal_required"),
            )
            self.assertEqual(plan.read_bytes(), before)

            proposal = {
                "schema_version": "semantic_review_observation_proposal.v1",
                "progress_verdict": "first_observation",
                "progress_evidence_refs": [f"{self.REVIEW_REL}#aggregate"],
                "blockers": [],
                "resolved_predecessor_blocker_refs": [],
            }
            evidence = risk_fence + "\n\n```json\n" + json.dumps(proposal, indent=2) + "\n```"
            plan.write_text(self._plan_text(evidence=evidence), encoding="utf-8")
            before = plan.read_bytes()
            materialized = self._run(plan, "--format", "json")
            self.assertEqual(materialized.returncode, 0, materialized.stderr)
            report = json.loads(materialized.stdout)
            self.assertEqual((report["state"], report["reason_code"]), ("ready_to_materialize", "observation_not_materialized"))
            self.assertEqual(plan.read_bytes(), before)
            materialization = report["materialization"]
            self.assertIsInstance(materialization, dict)
            assert isinstance(materialization, dict)
            observation = materialization["observation"]
            self.assertIsInstance(observation, dict)
            assert isinstance(observation, dict)

            final_evidence = evidence + "\n\n```json\n" + json.dumps(observation, indent=2) + "\n```"
            plan.write_text(self._plan_text(evidence=final_evidence), encoding="utf-8")
            before = plan.read_bytes()
            valid = self._run(plan, "--format", "json")
            self.assertEqual(valid.returncode, 0, valid.stderr)
            valid_report = json.loads(valid.stdout)
            self.assertEqual((valid_report["state"], valid_report["reason_code"]), ("valid", "current_observation_valid"))
            self.assertIsNone(valid_report["materialization"])
            self.assertEqual(plan.read_bytes(), before)

    def test_cli_0258_family_continuity_requires_scope_churn_on_target_change(self) -> None:
        """Model 0258 Q1/Q2: B1 survives, but changed target is not progress."""

        def fence(payload: dict[str, object]) -> str:
            return "```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```"

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = self._write_fixture(root)
            first_target = "0258-q1-corrected-packet"
            second_target = "0258-q2-de-scoped-packet"
            review_path = root / self.REVIEW_REL
            review_path.write_text(self._review_text(first_target, blocker_ids=(1,)), encoding="utf-8")
            first_risk = {
                "run_id": "reviewer_code_risk:0258:q1:20260802T180000Z",
                "lane_id": "reviewer_code_risk",
                "target_snapshot": first_target,
                "lane_status": "complete",
                "current": True,
            }
            first_proposal = {
                "schema_version": "semantic_review_observation_proposal.v1",
                "progress_verdict": "first_observation",
                "progress_evidence_refs": [f"{self.REVIEW_REL}#B1"],
                "blockers": [
                    {
                        "blocker_ref": f"{self.REVIEW_REL}#B1",
                        "lineage_relation": "first_observation",
                        "predecessor_blocker_ref": None,
                    }
                ],
                "resolved_predecessor_blocker_refs": [],
            }
            first_evidence = fence(first_risk) + "\n\n" + fence(first_proposal)
            plan.write_text(self._plan_text(evidence=first_evidence), encoding="utf-8")
            first_materialization = json.loads(self._run(plan, "--format", "json").stdout)["materialization"]
            self.assertIsInstance(first_materialization, dict)
            assert isinstance(first_materialization, dict)
            first_observation = first_materialization["observation"]
            self.assertIsInstance(first_observation, dict)
            assert isinstance(first_observation, dict)

            historical_risk = {**first_risk, "current": False}
            historical_evidence = (
                fence(historical_risk) + "\n\n" + fence(first_proposal) + "\n\n" + fence(first_observation)
            )
            review_path.write_text(self._review_text(second_target, blocker_ids=(1,)), encoding="utf-8")
            second_risk = {
                "run_id": "reviewer_code_risk:0258:q2:20260802T190000Z",
                "lane_id": "reviewer_code_risk",
                "target_snapshot": second_target,
                "lane_status": "complete",
                "current": True,
            }
            second_proposal = {
                "schema_version": "semantic_review_observation_proposal.v1",
                "progress_verdict": "same_contract_stalled",
                "progress_evidence_refs": [f"{self.REVIEW_REL}#B1"],
                "blockers": [
                    {
                        "blocker_ref": f"{self.REVIEW_REL}#B1",
                        "lineage_relation": "same_family",
                        "predecessor_blocker_ref": f"{self.REVIEW_REL}#B1",
                    }
                ],
                "resolved_predecessor_blocker_refs": [],
            }
            current_prefix = historical_evidence + "\n\n" + fence(second_risk) + "\n\n"
            plan.write_text(self._plan_text(evidence=current_prefix + fence(second_proposal)), encoding="utf-8")
            wrong_verdict = self._run(plan, "--format", "json")
            self.assertEqual(wrong_verdict.returncode, 1, wrong_verdict.stderr)
            wrong_report = json.loads(wrong_verdict.stdout)
            self.assertEqual((wrong_report["state"], wrong_report["reason_code"]), ("blocked", "role_field_invalid"))
            self.assertTrue(any(error["code"] == "semantic_progress_precedence_invalid" for error in wrong_report["errors"]))

            second_proposal["progress_verdict"] = "scope_churn"
            plan.write_text(self._plan_text(evidence=current_prefix + fence(second_proposal)), encoding="utf-8")
            second_materialized = self._run(plan, "--format", "json")
            self.assertEqual(second_materialized.returncode, 0, second_materialized.stderr)
            second_report = json.loads(second_materialized.stdout)
            self.assertEqual(
                (second_report["state"], second_report["reason_code"]),
                ("ready_to_materialize", "observation_not_materialized"),
            )
            materialization = second_report["materialization"]
            self.assertIsInstance(materialization, dict)
            assert isinstance(materialization, dict)
            second_observation = materialization["observation"]
            self.assertIsInstance(second_observation, dict)
            assert isinstance(second_observation, dict)
            self.assertEqual(second_observation["progress_verdict"], "scope_churn")
            self.assertEqual(second_observation["predecessor_observation_id"], first_observation["observation_id"])
            self.assertEqual(
                second_observation["blockers"][0]["blocker_family_id"],
                first_observation["blockers"][0]["blocker_family_id"],
            )

            final_evidence = current_prefix + fence(second_proposal) + "\n\n" + fence(second_observation)
            plan.write_text(self._plan_text(evidence=final_evidence), encoding="utf-8")
            valid = self._run(plan, "--format", "json")
            self.assertEqual(valid.returncode, 0, valid.stderr)
            valid_report = json.loads(valid.stdout)
            self.assertEqual((valid_report["state"], valid_report["reason_code"]), ("valid", "current_observation_valid"))
            self.assertEqual(
                valid_report["validated_chain"],
                [first_observation["observation_id"], second_observation["observation_id"]],
            )


if __name__ == "__main__":
    unittest.main()

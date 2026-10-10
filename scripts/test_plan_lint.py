#!/usr/bin/env python3
from __future__ import annotations

import copy
from contextlib import nullcontext
import hashlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from textwrap import dedent
from unittest import mock

try:
    from test_support.process_contract_fixtures import (
        NON_GIT_ROOT_SKIP_REASON,
        inside_git_work_tree,
        standalone_git_root,
        temporary_git_root,
        write_text_fixture,
    )
except ModuleNotFoundError:
    from scripts.test_support.process_contract_fixtures import (
        NON_GIT_ROOT_SKIP_REASON,
        inside_git_work_tree,
        standalone_git_root,
        temporary_git_root,
        write_text_fixture,
    )


MODULE_PATH = Path(__file__).with_name("plan_lint.py")
SPEC = importlib.util.spec_from_file_location("plan_lint", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

import review_schema_contract
from review_target_snapshot import build_current_bundle_snapshot


def setUpModule() -> None:
    MODULE.load_and_apply_plan_vocab(MODULE.PLAN_VOCAB_PATH)


def ensure_fixture_git(root: Path) -> None:
    """Materialize a valid disposable legacy Git repository for a fixture."""

    # Read only this fixture's metadata: Git discovery would answer for an
    # enclosing work tree around TMPDIR.
    head = subprocess.run(
        ["git", f"--git-dir={root / '.git'}", "rev-parse", "--verify", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if head.returncode == 0:
        return
    subprocess.run(["git", "init", "--quiet", str(root)], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", 'plan-lint' + '@' + 'example' + '.' + 'invalid'], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Plan lint fixture"], check=True)
    subprocess.run(["git", "-C", str(root), "add", "--all"], check=True)
    subprocess.run(
        ["git", "-C", str(root), "commit", "--quiet", "--allow-empty", "-m", "fixture"],
        check=True,
    )


def _fixture_required_machine_authority_decision(
    *,
    plan_rel: str,
    decision_id: str,
    route_id: str,
    cutover_policy: object | None = None,
) -> dict[str, object]:
    """Return a minimal valid required-carrier fixture without corpus input."""

    oracle = MODULE.plan_status_oracle
    route = {
        "id": route_id,
        "kind": "structured_carrier",
        "authority_host": {
            "repo": "current",
            "path": plan_rel,
            "locator": "json_pointer:/plan_meta/machine_authority_decision",
        },
        "canonical_writer": "fixture-writer",
        "canonical_reader": "fixture-reader",
        "derived_consumers": ["fixture_censor", "fixture_oracle"],
        "schema": "fixture.v1",
        "identity_fields": ["decision_id", "plan_path"],
        "cardinality": "one",
        "failure_behavior": {key: "fail_closed" for key in oracle.MACHINE_AUTHORITY_DECISION_FAILURE_KEYS},
    }
    decision: dict[str, object] = {
        "schema_version": oracle.MACHINE_AUTHORITY_DECISION_SCHEMA,
        "decision_id": decision_id,
        "applicability": "required",
        "state": "frozen",
        "impacts": ["authorization", "routing"],
        "cutover_policy": copy.deepcopy(
            oracle.MACHINE_AUTHORITY_DECISION_HANDOFF_POLICY
            if cutover_policy is None
            else cutover_policy
        ),
        "recommended_route": route,
        "alternatives": [
            {
                "id": "fixture_free_form",
                "kind": "fixture",
                "disposition": "rejected",
                "tradeoff": "fixture",
            },
            {
                "id": "fixture_prose",
                "kind": "fixture",
                "disposition": "rejected",
                "tradeoff": "fixture",
            },
        ],
        "owner_confirmation": {
            "state": "confirmed",
            "question_ref": "Q5",
            "decision_id": decision_id,
            "route_id": route_id,
            "carrier_sha256": "",
        },
    }
    confirmation = decision["owner_confirmation"]
    assert isinstance(confirmation, dict)
    confirmation["carrier_sha256"] = oracle.machine_authority_decision_sha256(decision)
    return decision


def _write_fixture_required_machine_authority_plan(
    root: Path,
    *,
    plan_rel: str,
    decision: dict[str, object],
    status: str = "Ready for Coder",
    write_draft: bool = True,
) -> Path:
    """Materialize a plan/ref pair that exercises the admission reader alone."""

    plan = root / plan_rel
    plan.parent.mkdir(parents=True, exist_ok=True)
    if not (root / ".git").exists():
        standalone_git_root(root)
    confirmation = decision["owner_confirmation"]
    assert isinstance(confirmation, dict)
    question_ref = confirmation["question_ref"]
    assert isinstance(question_ref, str)
    plan.write_text(
        "# Plan: machine-authority fixture\n\n"
        "**Plan type:** dev\n"
        f"**Status:** {status}\n\n"
        "## Meta\n```json\n"
        + json.dumps({"plan_meta": {"cluster": "process", "machine_authority_decision": decision}}, indent=2)
        + "\n```\n\n"
        "## Plan provenance / session context\n\n"
        "- Fixture provenance only.\n\n"
        "## Acceptance criteria / DoD\n\n"
        "- [ ] Fixture contract.\n\n"
        "## Q&A log\n\n"
        f"- [2026-08-14 18:20 MSK] (Architect -> Owner, id={question_ref}, blocker=yes, needs_owner=yes, status=open) Q: fixture\n"
        f"- [2026-08-14 18:21 MSK] (Owner -> Architect, id={question_ref}, blocker=no, needs_owner=no, status=closed) A: fixture\n\n"
        "## Suggestions log\n\n"
        "- Fixture only.\n",
        encoding="utf-8",
    )
    if write_draft:
        draft = root / f"docs/code_drafts/{plan.stem}__code_draft.md"
        draft.parent.mkdir(parents=True, exist_ok=True)
        draft.write_text(
            "# Code draft: machine-authority fixture\n\n```json\n"
            + json.dumps(
                {
                    "code_draft_meta": {
                        "plan": plan_rel,
                        "cluster": "process",
                        "machine_authority_decision_ref": {
                            "applicability": "required",
                            "decision_id": decision["decision_id"],
                            "carrier_sha256": MODULE.plan_status_oracle.machine_authority_decision_sha256(decision),
                        },
                    }
                },
                indent=2,
            )
            + "\n```\n",
            encoding="utf-8",
        )
    return plan


class PlanLintCapturedRootTests(unittest.TestCase):
    PLAN_REL = "docs/plans/260909_0300_captured_root.md"

    def _plan(self, root: Path) -> Path:
        plan = root / self.PLAN_REL
        plan.parent.mkdir(parents=True)
        plan.write_text("# Plan: captured root\n", encoding="utf-8")
        return plan

    def test_captured_legacy_root_overrides_environment_without_changing_unbound_fallback(self) -> None:
        for git_repo in (False, True):
            with self.subTest(git_repo=git_repo), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                if not git_repo and inside_git_work_tree(root):
                    self.skipTest(NON_GIT_ROOT_SKIP_REASON)
                plan = self._plan(root)
                if git_repo:
                    ensure_fixture_git(root)
                context = MODULE.resolve_top_level_context(root, loaded_pin="unattested_legacy")
                self.assertEqual(context.state, "legacy")
                with mock.patch.dict(os.environ, {"PLANVEYOR_PROJECT_ROOT": str(root / "docs")}):
                    self.assertEqual(MODULE.repo_root_for_plan_path(plan, context=context), root)
                    self.assertEqual(MODULE.repo_root_for_plan_path(plan), root / "docs")

    def test_captured_legacy_root_rejects_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir).resolve()
            if inside_git_work_tree(base):
                self.skipTest(NON_GIT_ROOT_SKIP_REASON)
            root = base / "project"
            root.mkdir()
            outside = self._plan(base / "outside")
            context = MODULE.resolve_top_level_context(root, loaded_pin="unattested_legacy")
            with self.assertRaisesRegex(ValueError, "outside the legacy contract project root"):
                MODULE.repo_root_for_plan_path(outside, context=context)

    def test_captured_legacy_root_rejects_nested_git(self) -> None:
        for git_repo in (False, True):
            for scoped in (False, True):
                with self.subTest(git_repo=git_repo, scoped=scoped), tempfile.TemporaryDirectory() as tmpdir:
                    root = Path(tmpdir).resolve()
                    if not git_repo and inside_git_work_tree(root):
                        self.skipTest(NON_GIT_ROOT_SKIP_REASON)
                    if git_repo:
                        ensure_fixture_git(root)
                    context = MODULE.resolve_top_level_context(root, loaded_pin="unattested_legacy")
                    nested = root / "nested"
                    plan = self._plan(nested)
                    subprocess.run(["git", "init", "--quiet", str(nested)], check=True, capture_output=True)
                    ensure_fixture_git(nested)
                    scope = (
                        MODULE._scoped_plan_lint_context(root, context=context, require_vocab=False)
                        if scoped else nullcontext()
                    )
                    with scope, self.assertRaises(MODULE.ContractAuthorityError) as error:
                        MODULE.repo_root_for_plan_path(plan, context=context)
                    self.assertEqual(error.exception.reason_code, "context_project_root_mismatch")

    def test_lint_entry_accepts_captured_non_git_root_and_still_reports_invalid_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            if inside_git_work_tree(root):
                self.skipTest(NON_GIT_ROOT_SKIP_REASON)
            plan = self._plan(root)
            context = MODULE.resolve_top_level_context(root, loaded_pin="unattested_legacy")
            findings = MODULE.lint_plan(plan, context=context)
            self.assertTrue(any(finding.message == "Missing **Status:** header (must be exactly one line)." for finding in findings))

    def test_checkpoint_and_producer_share_captured_non_git_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir).resolve()
            if inside_git_work_tree(base):
                self.skipTest(NON_GIT_ROOT_SKIP_REASON)
            root = base / "project"
            root.mkdir()
            fixture = SemanticCycleCheckpointContractTests(methodName="runTest")
            _, plan, _ = fixture._survival_fixture(root)
            expected = MODULE.build_semantic_cycle_checkpoint_report(plan)
            self.assertEqual(expected["state"], "required")
            (root / ".git").rename(base / "detached-fixture-git")
            context = MODULE.resolve_top_level_context(root, loaded_pin="unattested_legacy")
            with mock.patch.dict(os.environ, {"PLANVEYOR_PROJECT_ROOT": str(root / "docs")}):
                actual = MODULE.plan_status_oracle.semantic_cycle_checkpoint_report(plan, context=context)
            self.assertEqual(actual, expected)

    def test_unreadable_checkpoint_diagnostic_uses_captured_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            if inside_git_work_tree(root):
                self.skipTest(NON_GIT_ROOT_SKIP_REASON)
            context = MODULE.resolve_top_level_context(root, loaded_pin="unattested_legacy")
            report = MODULE.build_semantic_cycle_checkpoint_report(root / self.PLAN_REL, context=context)
            self.assertEqual(report["reason_code"], "activation_invalid")
            self.assertEqual(report["errors"][0]["path"], self.PLAN_REL)


class PlanLintOwnerQnAParityTests(unittest.TestCase):
    def _lint_body(self, body: str, *, status: str = "Architect initial draft") -> list[object]:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = Path(tmpdir) / "docs" / "plans" / "260329_1700_owner_qna_fixture.md"
            plan.parent.mkdir(parents=True, exist_ok=True)
            plan.write_text(
                dedent(
                    f"""\
                    # Plan: owner qna fixture

                    **Date:** 2026-03-29 17:00 MSK
                    **Stage:** Stage 1
                    **Priority:** P1
                    **Plan type:** dev
                    **Status:** {status}

                    """
                ),
                encoding="utf-8",
            )
            plan.write_text(
                plan.read_text(encoding="utf-8") + dedent(body),
                encoding="utf-8",
            )
            return MODULE.lint_plan(plan)

    def test_latest_closed_owner_question_is_not_open(self) -> None:
        findings = self._lint_body(
            """\
            ## Q&A log
            - [2026-03-29 17:01 MSK] id=Q1 status=open to=Owner: Which path?
            - [2026-03-29 17:02 MSK] id=Q1 status=closed to=Owner: Answered by Owner.
            """
        )

        self.assertFalse(any("Q&A item Q1 is still open" in finding.message for finding in findings))

    def test_arrow_owner_question_close_is_not_open(self) -> None:
        findings = self._lint_body(
            """\
            ## Q&A log
            - [2026-03-29 17:01 MSK] (Architect → Owner, id=Q1, blocker=yes, needs_owner=yes, status=open) Q: Which path?
            - [2026-03-29 17:02 MSK] (Architect, id=Q1, status=closed) CLOSED: Owner answered.
            """
        )

        self.assertFalse(any("Q&A item Q1 is still open" in finding.message for finding in findings))

    def test_latest_open_owner_question_is_reported(self) -> None:
        findings = self._lint_body(
            """\
            ## Q&A log
            - [2026-03-29 17:01 MSK] id=Q1 status=open to=Owner: Which path?
            - [2026-03-29 17:02 MSK] id=Q1 status=closed to=Owner: Answered by Owner.
            - [2026-03-29 17:03 MSK] id=Q1 status=open to=Owner: Reopened after new route.
            """
        )

        self.assertTrue(any("Q&A item Q1 is still open" in finding.message for finding in findings))

    def test_arrow_owner_question_is_reported(self) -> None:
        findings = self._lint_body(
            """\
            ## Q&A log
            - [2026-03-29 17:01 MSK] (Architect -> Owner, id=Q1, blocker=yes, needs_owner=yes, status=open) Q: Which path?
            """
        )

        self.assertTrue(any("Q&A item Q1 is still open" in finding.message for finding in findings))

    def test_malformed_owner_question_is_error(self) -> None:
        findings = self._lint_body(
            """\
            ## Q&A log
            - [2026-03-29 17:01 MSK] status=open to=Owner: Missing stable id.
            """
        )

        messages = [finding.message for finding in findings]
        self.assertTrue(any("Owner Q&A line is missing id=Qn" in message for message in messages))

    def test_legacy_closed_no_questions_is_not_error(self) -> None:
        findings = self._lint_body(
            """\
            ## Q&A log
            - [2026-03-29 17:01 MSK] (Architect, to=Owner, needs_owner=no, status=closed) NO QUESTIONS.
            """
        )

        messages = [finding.message for finding in findings]
        self.assertFalse(any("Owner Q&A line is missing id=Qn" in message for message in messages))

    def test_legacy_owner_id_open_then_closed_is_not_error_or_open(self) -> None:
        findings = self._lint_body(
            """\
            ## Q&A log
            - [2026-03-29 17:01 MSK] (A1, Architect, to=Owner, needs_owner=yes, status=open) Choose a path.
            - [2026-03-29 17:02 MSK] (A1, Architect, to=Owner, needs_owner=no, status=closed) Owner answered.
            """
        )

        messages = [finding.message for finding in findings]
        self.assertFalse(any("Owner Q&A line is missing id=Qn" in message for message in messages))
        self.assertFalse(any("Q&A item A1 is still open" in message for message in messages))


class PlanLintArchitectUnderstandingBlockTests(unittest.TestCase):
    def _findings(self, body: str, *, status: str = "Architect draft", stem: str = "260619_1705_process_understanding") -> list[object]:
        lines = dedent(
            f"""\
            # Plan: understanding fixture

            **Status:** {status}

            {body}
            """
        ).splitlines()
        return MODULE.validate_architect_understanding_block(
            Path(f"docs/plans/{stem}.md"),
            lines,
            status_value=status,
        )

    def test_separate_understanding_block_is_accepted(self) -> None:
        findings = self._findings(
            """\
            ## Как я понял задачу
            Нужно закрепить человекочитаемое понимание задачи как отдельный intake-carrier перед передачей плана дальше.
            """
        )

        self.assertEqual(findings, [])

    def test_missing_understanding_block_is_error_after_initial_draft(self) -> None:
        findings = self._findings(
            """\
            ## Problem
            Есть только постановка без отдельного summary.
            """,
            status="Architect draft",
        )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "ERROR")
        self.assertIn("Architect understanding block", findings[0].message)

    def test_missing_understanding_block_is_warning_during_initial_draft(self) -> None:
        findings = self._findings(
            """\
            ## Problem
            Fresh scaffold can still be in intake before Architect writes the summary.
            """,
            status="Architect initial draft",
        )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "WARN")

    def test_inline_understanding_sentence_does_not_replace_block(self) -> None:
        findings = self._findings(
            """\
            ## Solution (high level)
            Как я понял задачу: это не отдельный блок и не должно засчитываться.
            """,
            status="Architect draft",
        )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "ERROR")

    def test_template_instruction_only_understanding_block_is_error(self) -> None:
        findings = self._findings(
            """\
            ## Как я понял задачу
            (Required for Architect intake. Коротко, по-человечески и по-русски: что меняем/решаем, границы, route/следующий contour, что не делаем, какие Owner-решения закрыты или не нужны. Этот блок не заменяет `## Q&A log` и не должен жить только в Evidence/CENSOR.)
            """,
            status="Architect draft",
        )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "ERROR")

    def test_generated_review_only_scaffold_instruction_is_error(self) -> None:
        findings = self._findings(
            """\
            ## Problem
            Выполнить review-only merge-range review и зафиксировать verdict.

            ## Как я понял задачу
            (Required for Architect intake. Коротко, по-человечески и по-русски: что меняем/решаем, границы, route/следующий contour, что не делаем, какие Owner-решения закрыты или не нужны. Этот блок не заменяет `## Q&A log` и не должен жить только в Evidence/CENSOR.)

            ## Solution (high level)
            Пройти merge-range review как bounded review-only flow.
            """,
            status="Superseded",
            stem="260627_1204_reviewer_range_aaaa111_bbbb222",
        )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "ERROR")

    def test_parenthetical_real_understanding_summary_is_accepted(self) -> None:
        findings = self._findings(
            """\
            ## Как я понял задачу
            (Нужно закрыть ложный зелёный lint для Architect summary без изменения runtime-поведения и без расширения severity.)
            """,
            status="Architect draft",
        )

        self.assertEqual(findings, [])


class PlanLintPostMergeGateDoneTests(unittest.TestCase):
    def _findings(self, body: str, *, status: str = "Done", stem: str = "260624_0100_process_post_merge_gate_fixture") -> list[object]:
        lines = dedent(
            f"""\
            # Plan: post-merge gate fixture

            **Status:** {status}

            {body}
            """
        ).splitlines()
        return MODULE.validate_done_post_merge_gate_checklist(
            Path(f"docs/plans/{stem}.md"),
            lines,
            status_value=status,
        )

    def test_done_plan_with_open_post_merge_gate_checkbox_fails(self) -> None:
        findings = self._findings(
            """\
            ## Post-merge gate (before deleting plan)
            - [ ] Canon update has been moved to durable docs.
            - [x] Follow-up row is closed.
            """
        )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "ERROR")
        self.assertIn("Post-merge gate", findings[0].message)
        self.assertIn("- [ ]", findings[0].message)

    def test_done_plan_with_closed_post_merge_gate_checkboxes_passes(self) -> None:
        findings = self._findings(
            """\
            ## Post-merge gate (before deleting plan)
            - [x] Canon update has been moved to durable docs.
            - [X] Follow-up row is closed.
            """
        )

        self.assertEqual(findings, [])

    def test_done_plan_with_post_merge_gate_section_level_na_passes(self) -> None:
        findings = self._findings(
            """\
            ## Post-merge gate (before deleting plan)
            `N/A (why=this fixture is not a post-merge cleanup carrier)`
            """
        )

        self.assertEqual(findings, [])

    def test_non_done_plan_with_open_post_merge_gate_checkbox_is_not_blocked(self) -> None:
        findings = self._findings(
            """\
            ## Post-merge gate (before deleting plan)
            - [ ] Canon update has been moved to durable docs.
            """,
            status="Ready for Review",
        )

        self.assertEqual(findings, [])

    def test_done_plan_with_open_post_merge_gate_old_date_is_enforced(self) -> None:
        findings = self._findings(
            """\
            ## Post-merge gate (before deleting plan)
            - [ ] Canon update has been moved to durable docs.
            """,
            stem="260623_1400_process_legacy_pre_boundary_plan",
        )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "ERROR")

    def test_done_plan_with_open_post_merge_gate_at_boundary_is_enforced(self) -> None:
        # Boundary semantics mirror is_navigation_contract_enforced: a plan whose
        # filename timestamp is >= POST_MERGE_GATE_REQUIRED_FROM falls under
        # enforcement (>= is inclusive), so an open gate item still fails.
        findings = self._findings(
            """\
            ## Post-merge gate (before deleting plan)
            - [ ] Canon update has been moved to durable docs.
            """,
            stem="260623_1411_process_boundary_plan",
        )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "ERROR")


class PlanLintSimulatedDoneTests(unittest.TestCase):
    def _write_plan(
        self,
        root: Path,
        *,
        body: str,
        status: str = "Architect initial draft",
        stem: str = "260624_0100_process_simulated_done_fixture",
    ) -> Path:
        plan = root / "docs" / "plans" / f"{stem}.md"
        plan.parent.mkdir(parents=True, exist_ok=True)
        plan.write_text(
            dedent(
                f"""\
                # Plan: simulated Done fixture

                **Date:** 2026-06-24 01:00 MSK
                **Stage:** Stage 1
                **Priority:** P1
                **Plan type:** dev
                **Status:** {status}
                **Schema version:** plan.v1

                {body}
                """
            ),
            encoding="utf-8",
        )
        return plan

    @staticmethod
    def _post_merge_errors(findings: list[object]) -> list[object]:
        return [finding for finding in findings if "open `## Post-merge gate`" in finding.message]

    def test_effective_done_runs_existing_status_validators_without_mutating_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = self._write_plan(
                Path(tmpdir),
                body="""\
                ## Post-merge gate (before deleting plan)
                - [ ] Durable closeout is still open.
                """,
            )
            before_bytes = plan.read_bytes()
            before_mtime_ns = plan.stat().st_mtime_ns

            ordinary = MODULE.lint_plan(plan)
            simulated = MODULE.lint_plan(plan, effective_status="Done")

            self.assertEqual(self._post_merge_errors(ordinary), [])
            self.assertEqual(len(self._post_merge_errors(simulated)), 1)
            self.assertFalse(any("Missing code draft link" in finding.message for finding in ordinary))
            self.assertTrue(any("Missing code draft link" in finding.message for finding in simulated))
            self.assertEqual(plan.read_bytes(), before_bytes)
            self.assertEqual(plan.stat().st_mtime_ns, before_mtime_ns)
            self.assertEqual(MODULE.extract_status_lines(MODULE.read_text(plan)), [(7, "Architect initial draft")])

    def test_effective_done_accepts_closed_and_section_level_na_gates(self) -> None:
        cases = {
            "closed": """\
                ## Post-merge gate (before deleting plan)
                - [x] Durable closeout is complete.
            """,
            "section_na": """\
                ## Post-merge gate (before deleting plan)
                `N/A (why=no post-merge cleanup carrier)`
            """,
        }
        for name, body in cases.items():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as tmpdir:
                plan = self._write_plan(Path(tmpdir), body=body)
                findings = MODULE.lint_plan(plan, effective_status="Done")
                self.assertEqual(self._post_merge_errors(findings), [])

    def test_effective_done_enforces_old_and_current_plan_names(self) -> None:
        body = """\
            ## Post-merge gate (before deleting plan)
            - [ ] Durable closeout is still open.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            historical = self._write_plan(
                root,
                body=body,
                stem="260623_1400_process_simulated_done_legacy_fixture",
            )
            actual_done = self._write_plan(
                root,
                body=body,
                status="Done",
                stem="260624_0101_process_actual_done_fixture",
            )

            self.assertEqual(len(self._post_merge_errors(MODULE.lint_plan(historical, effective_status="Done"))), 1)
            self.assertEqual(len(self._post_merge_errors(MODULE.lint_plan(actual_done))), 1)

    def test_effective_done_keeps_raw_header_multiplicity_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = self._write_plan(
                Path(tmpdir),
                body="""\
                **Status:** Ready for Review

                ## Post-merge gate (before deleting plan)
                - [x] Durable closeout is complete.
                """,
            )

            findings = MODULE.lint_plan(plan, effective_status="Done")

            self.assertTrue(any("Multiple **Status:** header lines" in finding.message for finding in findings))

    def test_main_accepts_exact_single_file_simulated_done_and_preserves_ordinary_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = self._write_plan(
                Path(tmpdir),
                body="""\
                ## Post-merge gate (before deleting plan)
                - [x] Durable closeout is complete.
                """,
            )
            for argv, expected_effective_status in (
                (["plan_lint.py", "--as-status", "Done", str(plan)], "Done"),
                (["plan_lint.py", str(plan)], None),
            ):
                with self.subTest(argv=argv):
                    stdout = io.StringIO()
                    with mock.patch.object(sys, "argv", argv):
                        with mock.patch("sys.stdout", stdout):
                            with mock.patch.object(MODULE, "lint_plan", return_value=[]) as lint_plan:
                                result = MODULE.main()

                    self.assertEqual(result, 0)
                    lint_plan.assert_called_once_with(
                        plan.resolve(),
                        effective_status=expected_effective_status,
                    )

    def test_main_rejects_simulated_done_cli_misuse_before_lint_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            first = self._write_plan(root, body="## Post-merge gate\n`N/A (why=fixture)`")
            second = self._write_plan(
                root,
                body="## Post-merge gate\n`N/A (why=fixture)`",
                stem="260624_0102_process_second_fixture",
            )
            cases = (
                (
                    ["plan_lint.py", "--as-status", "Done"],
                    "ERROR: --as-status requires exactly one explicit plan file.",
                ),
                (
                    ["plan_lint.py", "--as-status", "Done", str(first), str(second)],
                    "ERROR: --as-status requires exactly one explicit plan file.",
                ),
                (
                    ["plan_lint.py", "--as-status", "Done", str(first.parent)],
                    "ERROR: --as-status requires one existing regular plan file.",
                ),
                (
                    ["plan_lint.py", "--as-status", "Done", "--all"],
                    "ERROR: --as-status cannot be combined with --all.",
                ),
                (
                    ["plan_lint.py", "--as-status", "Ready for Review", str(first)],
                    "ERROR: --as-status supports only the exact value Done.",
                ),
            )
            for argv, expected_error in cases:
                with self.subTest(argv=argv):
                    stdout = io.StringIO()
                    with mock.patch.object(sys, "argv", argv):
                        with mock.patch("sys.stdout", stdout):
                            with mock.patch.object(MODULE, "iter_plan_files") as iter_plan_files:
                                result = MODULE.main()

                    self.assertEqual(result, 2)
                    self.assertIn(expected_error, stdout.getvalue())
                    iter_plan_files.assert_not_called()


class PlanLintDoneExecutableReviewArtifactGuardTests(unittest.TestCase):
    """Boundary tests for validate_done_executable_review_artifact_guard.

    The guard requires a `Status: Done` + `Plan type: dev` plan to carry exactly
    one live review-artifact carrier (`Code review (primary)` / `Doc review
    (docs-only)`) whose file exists. It was introduced at 260619_2212 (commit
    cccc3333). Per the ADR 009 migration-boundary convention (shared with the
    post-merge-gate family), pre-boundary legacy Done plans are exempt: their
    older carrier formats ((target=`staged`), (Reviewer), Primary host, Docs
    review, etc.) must not be retroactively blocked.
    """

    def _findings(
        self,
        body: str,
        *,
        status: str = "Done",
        plan_type: str = "dev",
        stem: str = "260620_0100_process_review_artifact_fixture",
        plan_repo_root: Path | None = None,
    ) -> list[object]:
        lines = dedent(
            f"""\
            # Plan: review artifact fixture

            **Status:** {status}

            **Plan type:** {plan_type}

            {body}
            """
        ).splitlines()
        return MODULE.validate_done_executable_review_artifact_guard(
            Path(f"docs/plans/{stem}.md"),
            lines,
            None,
            status_value=status,
            plan_type=plan_type,
            plan_repo_root=plan_repo_root or Path(__file__).resolve().parent.parent,
        )

    def test_post_boundary_done_dev_plan_without_live_carrier_fails(self) -> None:
        findings = self._findings(
            "## Review artifacts\n\n- Code review (target=`staged`): `docs/code_reviews/missing.md`\n"
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "ERROR")
        self.assertIn("must carry one live review artifact", findings[0].message)

    def test_post_boundary_done_dev_plan_with_live_carrier_and_existing_file_passes(
        self,
    ) -> None:
        review_rel = "docs/doc_reviews/260101_0000_live_review_fixture.md"
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_text_fixture(root, review_rel, "# Review fixture\n")
            findings = self._findings(
                f"## Review artifacts\n\n- Doc review (docs-only): `{review_rel}`\n",
                plan_repo_root=root,
            )
        self.assertEqual(findings, [])

    def test_old_date_done_dev_plan_with_missing_review_is_enforced(self) -> None:
        findings = self._findings(
            "## Review artifacts\n\n- Code review (target=`staged`): `docs/code_reviews/missing_legacy.md`\n",
            stem="260619_2211_process_legacy_pre_boundary_plan",
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "ERROR")

    def test_at_boundary_done_dev_plan_without_live_carrier_is_enforced(self) -> None:
        # Boundary semantics mirror is_*_enforced helpers: filename timestamp >=
        # the boundary timestamp falls under enforcement (>= is inclusive).
        findings = self._findings(
            "## Review artifacts\n\n- Code review (target=`staged`): `docs/code_reviews/missing.md`\n",
            stem="260619_2212_process_boundary_plan",
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "ERROR")

    def test_non_dev_plan_is_not_blocked(self) -> None:
        findings = self._findings(
            "## Review artifacts\n\n- Review: none\n",
            plan_type="process",
        )
        self.assertEqual(findings, [])

    def test_non_done_plan_is_not_blocked(self) -> None:
        findings = self._findings(
            "## Review artifacts\n\n- Review: none\n",
            status="Ready for Review",
        )
        self.assertEqual(findings, [])


class PlanLintRussianStatementSectionsTests(unittest.TestCase):
    def _findings(self, body: str, *, stem: str = "260619_1744_process_russian_statement") -> list[object]:
        lines = dedent(
            f"""\
            # Plan: Russian statement fixture

            **Status:** Architect draft

            {body}
            """
        ).splitlines()
        return MODULE.validate_russian_plan_statement_sections(
            Path(f"docs/plans/{stem}.md"),
            lines,
        )

    def test_english_problem_section_warns_for_new_plan(self) -> None:
        findings = self._findings(
            """\
            ## Problem
            Need to define the operational rollout plan for the analysis wave.
            """
        )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "WARN")
        self.assertIn("Russian-first plan statement warning", findings[0].message)

    def test_russian_problem_section_is_accepted(self) -> None:
        findings = self._findings(
            """\
            ## Problem
            Нужно закрепить правило, что постановка плана пишется по-русски.
            """
        )

        self.assertEqual(findings, [])

    def test_english_section_with_old_date_warns(self) -> None:
        findings = self._findings(
            """\
            ## Problem
            Need to define the operational rollout plan for the analysis wave.
            """,
            stem="260619_1743_process_russian_statement",
        )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "WARN")

    def test_explicit_na_section_is_ignored(self) -> None:
        findings = self._findings(
            """\
            ## Out of scope
            N/A (why=no explicit exclusions for this narrow draft)
            """
        )

        self.assertEqual(findings, [])


class PlanLintReviewRouteDeterminismTests(unittest.TestCase):
    def _write_fixture(
        self,
        root: Path,
        *,
        plan_stem: str,
        plan_status: str = "Ready for Review",
        target_paths: list[str],
        review_artifact_lines: list[str],
        review_artifact_payloads: dict[str, str] | None = None,
        extra_sections: str = "",
        changes_block: str | None = None,
        complete: bool = False,
    ) -> Path:
        (root / ".git").mkdir()
        ensure_fixture_git(root)
        (root / "docs" / "plans").mkdir(parents=True)
        (root / "docs" / "code_drafts").mkdir(parents=True)
        (root / "docs" / "code_reviews").mkdir(parents=True)
        (root / "docs" / "doc_reviews").mkdir(parents=True)

        plan_rel = f"docs/plans/{plan_stem}.md"
        draft_rel = f"docs/code_drafts/{plan_stem}__code_draft.md"
        plan_path = root / plan_rel
        draft_path = root / draft_rel

        draft_meta = {
            "code_draft_meta": {
                "plan": plan_rel,
                "cluster": "process",
                "targets": [{"path": target_path, "kind": "doc" if target_path.startswith("docs/") else "py"} for target_path in target_paths],
            }
        }
        plan_meta: dict[str, object] = {
            "cluster": "process",
            "tags": [],
            "required_manager_mode": "either",
            "phase_overlay": None,
            "phase_state": None,
            "parent": None,
            "next_plans": [],
            "depends_on": [],
            "followups_out": [],
            "canon_updates": [],
        }
        if complete:
            decision = {
                "schema_version": MODULE.plan_status_oracle.MACHINE_AUTHORITY_DECISION_SCHEMA,
                "applicability": "not_applicable",
                "reason_code": "no_machine_authority_change",
            }
            digest = MODULE.plan_status_oracle.machine_authority_decision_sha256(decision)
            plan_meta["machine_authority_decision"] = decision
            draft_meta["code_draft_meta"]["machine_authority_decision_ref"] = {
                "applicability": "not_applicable",
                "reason_code": "no_machine_authority_change",
                "carrier_sha256": digest,
            }
        sync_doc_targets = [path for path in target_paths if path.startswith("docs/")]
        draft_text = dedent(
            f"""\
                # Code draft: fixture

                **Date:** 2026-03-25 20:20 MSK
                **Cluster:** process
                **Related plan:** `{plan_rel}`
                **Author role:** Planner
                **Status:** Planner finalized

                ## Meta (machine-readable JSON)
                ```json
                {json.dumps(draft_meta, ensure_ascii=False, indent=2)}
                ```
                """
        )
        if complete:
            draft_text = "\n".join(
                line[16:] if line.startswith("                ") else line
                for line in draft_text.splitlines()
            ) + "\n"
        draft_path.write_text(draft_text, encoding="utf-8")

        review_artifacts_block = "\n".join(review_artifact_lines)
        changes_block = changes_block or dedent(
            """\
            - Scripts/tools:
              - `scripts/plan_lint.py`
            """
        ).rstrip()
        understanding_block = ""
        documentation_impact_block = ""
        if complete:
            rendered_sync_targets = ", ".join(f"`{path}`" for path in sync_doc_targets)
            if not rendered_sync_targets:
                rendered_sync_targets = "`N/A (why=fixture)`"
            understanding_block = dedent(
                """\
                ## Как я понял задачу

                Фикстура проверяет один локальный lint-контракт без неявных lifecycle-исключений.

                """
            ).strip()
            understanding_block = understanding_block.replace("\n", "\n                ") + "\n"
            documentation_impact_block = dedent(
                f"""\
                ## Documentation impact / provenance

                - Source docs used: `N/A (why=fixture)`.
                - Synchronous doc/registry targets: {rendered_sync_targets}.
                - Post-merge canon updates: `N/A (why=fixture)`.
                - Deferred documentation follow-ups: `N/A (why=fixture)`.
                - Provenance refs: fixture.

                """
            ).strip()
            documentation_impact_block = documentation_impact_block.replace("\n", "\n                ") + "\n"
        problem_body = "1. Фикстура проверяет `scripts/plan_lint.py`." if complete else "1. Fixture for `scripts/plan_lint.py`."
        solution_body = "1. Сохранить минимальную и детерминированную fixture." if complete else "1. Keep the fixture minimal and deterministic."
        decision_body = "- ✅ Final: использовать literal fixture для review-artifact carrier." if complete else "- ✅ Final: use literal review-artifact carrier fixtures."
        scope_body = "- Проверить `scripts/plan_lint.py`." if complete else "- Test `scripts/plan_lint.py`."
        out_of_scope_body = "- Runtime UI не входит в fixture." if complete else "- Runtime UI."
        acceptance_body = "- [ ] Фикстура остаётся сосредоточенной на детерминизме review-route." if complete else "- [ ] Fixture stays focused on review-route determinism."
        plan_text = dedent(
            f"""\
                # Plan: Fixture

                **Date:** 2026-03-25 20:20 MSK
                **Stage:** Stage 1
                **Priority:** P1
                **Plan type:** dev
                **Status:** {plan_status}

                **Context links (source of truth):**
                - Code draft(s): `{draft_rel}`

                ## Meta (machine-readable JSON; required for new plans)
                ```json
                {json.dumps({"plan_meta": plan_meta}, ensure_ascii=False, indent=2)}
                ```

                {understanding_block}
                ## Problem

                {problem_body}

                ## Solution (high level)

                {solution_body}

                ## Decisions (final)

                {decision_body}

                ## Scope

                {scope_body}

                ## Out of scope

                {out_of_scope_body}

                ## Follow-ups (deferred)

                - none

                ## Rollout packet handoff
                - Role: `N/A (why=fixture)`
                - Packet path: `N/A`
                - Target repo: `N/A`
                - Suggested target plan slug: `N/A`
                - Queue after import: `N/A`

                ## Close-out routing
                - Roadmap/queue sync: `N/A (fixture)`
                - Follow-up sync: `none`
                - Next bounded slice: `none (fixture)`
                - Terminal outcome: yes (fixture)

                ## Mechanism coverage

                - `N/A (why=fixture)`

                ## Risks / Open questions (summary)

                - none

                ## Changes (by area)

                {changes_block}

                ## Acceptance criteria / DoD

                {acceptance_body}

                ## Tests

                ### Critical runtime invariants (required for risky UI/layout/visibility/default-state/access tasks)

                - `N/A (why=fixture)`

                ### Что написать / поправить

                - `scripts/test_plan_lint.py`

                ### Что прогнать

                - `python3 scripts/test_plan_lint.py`

                ## Commands

                - `python3 scripts/test_plan_lint.py`

                ## Verification rerun / exec handoff
                - Mode: `N/A (why=fixture)`
                - Context source: `N/A`
                - Prompt: `N/A`
                - Command: `N/A`
                - Expected artifact: `N/A`

                ## Evidence (chronological, append-only)

                - [2026-03-25 20:20 MSK] (Planner) Fixture materialized.

                ## Review artifacts

                {review_artifacts_block}

                {documentation_impact_block}
                {extra_sections}
                """
        )
        if complete:
            plan_text = "\n".join(
                line[16:] if line.startswith("                ") else line
                for line in plan_text.splitlines()
            ) + "\n"
        plan_path.write_text(plan_text, encoding="utf-8")

        if review_artifact_payloads:
            for rel_path_str, payload in review_artifact_payloads.items():
                artifact_path = root / rel_path_str
                artifact_path.parent.mkdir(parents=True, exist_ok=True)
                artifact_path.write_text(payload, encoding="utf-8")

        return plan_path

    def test_dual_live_review_routes_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260324_1200_process_dual_live_review_route",
                target_paths=["scripts/plan_lint.py"],
                review_artifact_lines=[
                    "- Code review (primary): `docs/code_reviews/260324_1200_process_dual_live_review_route.md`",
                    "- Doc review (docs-only): `docs/doc_reviews/260324_1200_process_dual_live_review_route.md`",
                ],
            )

            findings = MODULE.lint_plan(plan_path)

        messages = [finding.message for finding in findings if "Ambiguous live review route" in finding.message]
        self.assertEqual(len(messages), 1)

    def test_docs_only_live_code_review_route_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260324_1201_process_docs_only_review_route",
                target_paths=["docs/plans/README.md", "docs/playbooks/example.md"],
                review_artifact_lines=[
                    "- Code review (primary): `docs/code_reviews/260324_1201_process_docs_only_review_route.md`",
                ],
            )

            findings = MODULE.lint_plan(plan_path)

        messages = [finding.message for finding in findings if "Docs-only bundle mismatch" in finding.message]
        self.assertEqual(len(messages), 1)



    def test_non_doc_live_code_review_route_with_non_doc_targets_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260324_1203_process_non_doc_review_route",
                target_paths=["scripts/plan_lint.py", "docs/plans/README.md"],
                review_artifact_lines=[
                    "- Code review (primary): `docs/code_reviews/260324_1203_process_non_doc_review_route.md`",
                ],
                complete=True,
            )

            findings = MODULE.lint_plan(plan_path)

        self.assertEqual(findings, [])

    def test_done_executable_missing_review_artifact_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260620_0103_process_done_missing_review_artifact",
                plan_status="Done",
                target_paths=["scripts/plan_lint.py"],
                review_artifact_lines=[
                    "- Code review (primary): `docs/code_reviews/260620_0103_process_done_missing_review_artifact.md`",
                ],
            )

            findings = MODULE.lint_plan(plan_path)

        messages = [finding.message for finding in findings]
        self.assertTrue(any("missing review artifact" in message for message in messages), messages)

    def test_done_executable_review_artifact_directory_fails(self) -> None:
        review_path = "docs/code_reviews/260620_0103_process_done_review_artifact_directory.md"
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260620_0103_process_done_review_artifact_directory",
                plan_status="Done",
                target_paths=["scripts/plan_lint.py"],
                review_artifact_lines=[
                    f"- Code review (primary): `{review_path}`",
                ],
            )
            (root / review_path).mkdir(parents=True)

            findings = MODULE.lint_plan(plan_path)

        messages = [finding.message for finding in findings]
        self.assertTrue(any("missing review artifact" in message for message in messages), messages)

    def test_done_executable_materialized_review_artifact_passes_terminal_guard(self) -> None:
        review_path = "docs/code_reviews/260619_0103_process_done_review_artifact_present.md"
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260619_0103_process_done_review_artifact_present",
                plan_status="Done",
                target_paths=["scripts/plan_lint.py"],
                review_artifact_lines=[
                    f"- Code review (primary): `{review_path}`",
                ],
                review_artifact_payloads={
                    review_path: "# Code review\n\n**Status:** ✅ OK\n",
                },
            )

            findings = MODULE.lint_plan(plan_path)

        self.assertFalse(any("Terminal `Done` executable dev plan" in finding.message for finding in findings), findings)

    def test_done_current_schema_roadmap_open_followup_errors_after_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = PlanLintUmbrellaRoadmapLifecycleGuardTests()._write_fixture(
                Path(tmpdir),
                plan_stem="260619_0103_process_roadmap_false_close",
            )

            findings = MODULE.lint_plan(plan_path)

        roadmap_findings = [
            finding
            for finding in findings
            if finding.message.startswith(MODULE.UMBRELLA_ROADMAP_LIFECYCLE_WARNING_PREFIX)
        ]
        self.assertEqual(len(roadmap_findings), 1)
        self.assertEqual(roadmap_findings[0].severity, "ERROR")


class PlanLintOriginPlanReviewTargetsTests(unittest.TestCase):
    def _write_fixture(
        self,
        root: Path,
        *,
        plan_stem: str,
        plan_status: str,
        target_paths: list[str] | None = None,
        plan_type: str = "dev",
        extra_sections: str = "",
    ) -> Path:
        plan_rel = f"docs/plans/{plan_stem}.md"
        plan_path = PlanLintReviewRouteDeterminismTests()._write_fixture(
            root,
            plan_stem=plan_stem,
            plan_status=plan_status,
            target_paths=target_paths or [plan_rel],
            review_artifact_lines=[],
            extra_sections=extra_sections,
        )
        if plan_type != "dev":
            payload = plan_path.read_text(encoding="utf-8")
            plan_path.write_text(
                payload.replace("**Plan type:** dev", f"**Plan type:** {plan_type}", 1),
                encoding="utf-8",
            )
        return plan_path

    def _materialize_commit(self, root: Path) -> str:
        subprocess.run(
            ["git", "-C", str(root), "init", "-q"],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "-C", str(root), "add", "--", "docs"],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "-c",
                "user.name=Plan Lint Test",
                "-c",
                'user.email=' + 'plan-lint' + '@' + 'example' + '.' + 'invalid',
                "-c",
                "commit.gpgsign=false",
                "commit",
                "-q",
                "-m",
                "Materialize plan lint fixture",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", "HEAD^{commit}"],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    def _origin_findings(
        self,
        plan_path: Path,
        *,
        effective_status: str | None = None,
    ) -> list[object]:
        return [
            finding
            for finding in MODULE.lint_plan(plan_path, effective_status=effective_status)
            if MODULE.ORIGIN_PLAN_IN_REVIEW_TARGETS_REASON in finding.message
        ]

    def test_early_dev_self_target_is_warning_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            stem = "260729_1400_process_origin_plan_early"
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem=stem,
                plan_status="Ready for Planner",
            )
            findings = self._origin_findings(plan_path)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "WARN")
        self.assertIn("classification=restamp_before_handoff", findings[0].message)

    def test_executable_dev_statuses_fail_closed(self) -> None:
        statuses = (
            "Planner finalize",
            "Ready for Coder",
            "Coder intake",
            "In progress",
            "Ready for Review",
            "Reviewer intake",
            "Reviewer code review",
            "Reviewer visual review",
            "Ready for Arch review",
            "Architect arch review",
        )
        for index, status in enumerate(statuses):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmpdir:
                plan_path = self._write_fixture(
                    Path(tmpdir),
                    plan_stem=f"260729_14{index:02d}_process_origin_plan_executable",
                    plan_status=status,
                )
                findings = self._origin_findings(plan_path)

            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].severity, "ERROR")
            self.assertIn("classification=restamp_before_handoff", findings[0].message)

    def test_review_only_current_bundle_fails_but_valid_range_is_exempt(self) -> None:
        cases = (
            ("", "ERROR", "restamp_before_handoff"),
            (
                "- Review target: `RANGE="
                + "a" * 7
                + ".."
                + "b" * 7
                + " (EXCLUDE_DOCS=0)`",
                "WARN",
                "range_exempt",
            ),
            (
                "- Review target: `RANGE=abc..def (EXCLUDE_DOCS=0)`",
                "ERROR",
                "restamp_before_handoff",
            ),
        )
        for index, (review_target, severity, classification) in enumerate(cases):
            with self.subTest(review_target=review_target), tempfile.TemporaryDirectory() as tmpdir:
                plan_path = self._write_fixture(
                    Path(tmpdir),
                    plan_stem=f"260729_15{index:02d}_process_origin_plan_review_only",
                    plan_status="Reviewer intake",
                    plan_type="review-only",
                    extra_sections=review_target,
                )
                findings = self._origin_findings(plan_path)

            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].severity, severity)
            self.assertIn(f"classification={classification}", findings[0].message)

    def test_immutable_commit_is_exempt_but_mutable_review_modes_fail_closed(self) -> None:
        for index, plan_type in enumerate(("dev", "review-only")):
            with self.subTest(plan_type=plan_type), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                plan_path = self._write_fixture(
                    root,
                    plan_stem=f"260729_155{index}_process_origin_plan_immutable_commit",
                    plan_status="Ready for Review",
                    plan_type=plan_type,
                )
                commit_oid = self._materialize_commit(root)
                plan_path.write_text(
                    plan_path.read_text(encoding="utf-8")
                    + f"\n- Review target: `COMMIT={commit_oid}`\n",
                    encoding="utf-8",
                )
                findings = self._origin_findings(plan_path)

            self.assertEqual(findings, [])

        fabricated_oid = "a" * 40
        for index, plan_type in enumerate(("dev", "review-only")):
            with (
                self.subTest(plan_type=plan_type, commit="unresolvable"),
                tempfile.TemporaryDirectory() as tmpdir,
            ):
                root = Path(tmpdir)
                plan_path = self._write_fixture(
                    root,
                    plan_stem=f"260729_155{index + 2}_process_origin_plan_unresolvable_commit",
                    plan_status="Ready for Review",
                    plan_type=plan_type,
                )
                self._materialize_commit(root)
                plan_path.write_text(
                    plan_path.read_text(encoding="utf-8")
                    + f"\n- Review target: `COMMIT={fabricated_oid}`\n",
                    encoding="utf-8",
                )
                findings = self._origin_findings(plan_path)

            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].severity, "ERROR")
            self.assertIn("classification=restamp_before_handoff", findings[0].message)

        mutable_targets = (
            "COMMIT=staged",
            "COMMIT=current",
            "BUNDLE=staged",
            "BUNDLE=current",
        )
        for type_index, plan_type in enumerate(("dev", "review-only")):
            for target_index, review_target in enumerate(mutable_targets):
                with (
                    self.subTest(plan_type=plan_type, review_target=review_target),
                    tempfile.TemporaryDirectory() as tmpdir,
                ):
                    plan_path = self._write_fixture(
                        Path(tmpdir),
                        plan_stem=(
                            f"260729_156{type_index}{target_index}_"
                            "process_origin_plan_mutable_mode"
                        ),
                        plan_status="Ready for Review",
                        plan_type=plan_type,
                        extra_sections=f"- Review target: `{review_target}`",
                    )
                    findings = self._origin_findings(plan_path)

                self.assertEqual(len(findings), 1)
                self.assertEqual(findings[0].severity, "ERROR")
                self.assertIn(
                    "classification=restamp_before_handoff",
                    findings[0].message,
                )

        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260729_1570_process_origin_plan_malformed_commit",
                plan_status="Ready for Review",
                extra_sections="- Review target: `COMMIT=abc`",
            )
            findings = self._origin_findings(plan_path)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "ERROR")
        self.assertIn("classification=restamp_before_handoff", findings[0].message)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260729_1571_process_origin_plan_mixed_commit_targets",
                plan_status="Ready for Review",
            )
            commit_oid = self._materialize_commit(root)
            plan_path.write_text(
                plan_path.read_text(encoding="utf-8")
                + f"\n- Review target: `COMMIT={commit_oid}`\n"
                + "- Review target: `BUNDLE=current`\n",
                encoding="utf-8",
            )
            findings = self._origin_findings(plan_path)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "ERROR")
        self.assertIn("classification=restamp_before_handoff", findings[0].message)

    def test_prospective_done_is_error_but_existing_terminal_history_is_diagnostic(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260729_1600_process_origin_plan_prospective_done",
                plan_status="Ready for Planner",
            )
            findings = self._origin_findings(plan_path, effective_status="Done")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "ERROR")
        self.assertIn("classification=restamp_before_handoff", findings[0].message)

        for index, status in enumerate(("Done", "Superseded")):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmpdir:
                plan_path = self._write_fixture(
                    Path(tmpdir),
                    plan_stem=f"260729_161{index}_process_origin_plan_terminal",
                    plan_status=status,
                )
                findings = self._origin_findings(plan_path)
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].severity, "WARN")
            self.assertIn("classification=terminal_history", findings[0].message)

    def test_multi_target_and_file_object_aliases_emit_one_finding(self) -> None:
        for alias_kind in ("lexical", "symlink", "hardlink"):
            with self.subTest(alias_kind=alias_kind), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                stem = f"260729_1700_process_origin_plan_{alias_kind}"
                plan_rel = f"docs/plans/{stem}.md"
                alias_rel = f"docs/aliases/{stem}.md"
                declared = (
                    f"docs//plans/{stem}.md"
                    if alias_kind == "lexical"
                    else alias_rel
                )
                plan_path = self._write_fixture(
                    root,
                    plan_stem=stem,
                    plan_status="In progress",
                    target_paths=["scripts/ordinary.py", declared, "docs/ordinary.md"],
                )
                write_text_fixture(root, "scripts/ordinary.py", "# ordinary\n")
                write_text_fixture(root, "docs/ordinary.md", "# ordinary\n")
                if alias_kind != "lexical":
                    alias_path = root / alias_rel
                    alias_path.parent.mkdir(parents=True, exist_ok=True)
                    if alias_kind == "symlink":
                        alias_path.symlink_to(plan_path)
                    else:
                        alias_path.hardlink_to(plan_path)

                findings = self._origin_findings(plan_path)

            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].severity, "ERROR")
            self.assertEqual(findings[0].message.count("classification="), 1)

    def test_independent_same_stem_target_does_not_trigger(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            stem = "260729_1800_process_origin_plan_same_stem"
            target_rel = f"docs/analysis_packs/{stem}.md"
            plan_path = self._write_fixture(
                root,
                plan_stem=stem,
                plan_status="In progress",
                target_paths=[target_rel],
            )
            write_text_fixture(root, target_rel, "# Independent analysis pack\n")

            findings = self._origin_findings(plan_path)

        self.assertEqual(findings, [])

    def test_inventory_classification_precedence_is_literal(self) -> None:
        parked_lines = [
            "- Code draft(s): `N/A (why=parked reference)`",
            "## Verification rerun / exec handoff",
            "- Mode: `N/A (why=parked reference)`",
            "- Command: `N/A (why=parked reference)`",
            "- Expected artifact: `N/A (why=parked reference)`",
        ]
        valid_range_lines = [
            "- Review target: `RANGE="
            + "a" * 40
            + ".."
            + "b" * 40
            + " (EXCLUDE_DOCS=1)`",
            *parked_lines,
        ]
        cases = (
            (valid_range_lines, "review-only", "Done", {"phase_state": "parked"}, "range_exempt"),
            (parked_lines, "dev", "Done", {"phase_state": "parked"}, "terminal_history"),
            (parked_lines, "dev", "In progress", {"phase_state": "parked"}, "parked_reference"),
            ([], "dev", "In progress", {}, "restamp_before_handoff"),
        )
        for lines, plan_type, status, meta, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(
                    MODULE._origin_plan_review_target_classification(
                        lines=lines,
                        plan_type=plan_type,
                        raw_status_value=status,
                        plan_meta_obj=meta,
                        plan_repo_root=MODULE_PATH.parent.parent,
                    ),
                    expected,
                )

    def test_canon_keeps_origin_plan_outside_reviewed_target_bytes(self) -> None:
        repo_root = MODULE_PATH.parent.parent
        readme = (repo_root / "docs/plans/README.md").read_text(encoding="utf-8")
        template = (repo_root / "docs/code_drafts/_template.md").read_text(encoding="utf-8")
        analysis_wave = (repo_root / "docs/playbooks/analysis_wave.md").read_text(encoding="utf-8")

        for text in (readme, template):
            self.assertIn("`BUNDLE=current`", text)
            self.assertIn("`code_draft_meta.targets`", text)
            self.assertIn("`PLAN_PATH`", text)
            self.assertIn("exact bundle", text)
        self.assertIn(MODULE.ORIGIN_PLAN_IN_REVIEW_TARGETS_REASON, readme)
        self.assertIn("`docs/analysis_packs/<plan_stem>.md`", analysis_wave)
        self.assertIn("единственной operational authority", analysis_wave)


class PlanLintUmbrellaRoadmapLifecycleGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        MODULE.load_and_apply_plan_vocab(MODULE.PLAN_VOCAB_PATH)

    def _write_fixture(
        self,
        root: Path,
        *,
        plan_stem: str,
        title: str = "roadmap umbrella fixture",
        tags: list[str] | None = None,
        followups_out: list[dict[str, object]] | None = None,
        next_plans: list[str] | None = None,
        decisions_extra: str = "",
        closeout_extra: str = "",
    ) -> Path:
        (root / ".git").mkdir()
        ensure_fixture_git(root)
        plan_rel = f"docs/plans/{plan_stem}.md"
        draft_rel = f"docs/code_drafts/{plan_stem}__code_draft.md"
        plan_path = root / plan_rel
        draft_path = root / draft_rel
        write_text_fixture(
            root,
            "docs/plans/README.md",
            "\n".join(
                [
                    "# Fixture README",
                    "<review_artifact_path>#B<N>",
                    "same-contract reroute",
                    "real scope expansion",
                    "de-scoped follow-up",
                    "",
                ]
            ),
        )
        write_text_fixture(root, "scripts/plan_lint.py", "# fixture target\n")
        (root / "docs" / "plans").mkdir(parents=True, exist_ok=True)
        (root / "docs" / "code_drafts").mkdir(parents=True, exist_ok=True)
        (root / "docs" / "code_reviews").mkdir(parents=True, exist_ok=True)

        draft_meta = {
            "code_draft_meta": {
                "plan": plan_rel,
                "cluster": "process",
                "targets": [
                    {"path": "docs/plans/README.md", "kind": "doc"},
                    {"path": "scripts/plan_lint.py", "kind": "py"},
                ],
                "deleted_paths": [],
            }
        }
        draft_path.write_text(
            dedent(
                f"""\
                # Code draft: umbrella roadmap lifecycle fixture

                ## Meta (machine-readable JSON)
                ```json
                {json.dumps(draft_meta, ensure_ascii=False, indent=2)}
                ```
                """
            ),
            encoding="utf-8",
        )

        plan_meta = {
            "cluster": "process",
            "tags": tags if tags is not None else ["umbrella", "roadmap"],
            "wave_family": None,
            "phase_overlay": None,
            "phase_state": None,
            "parent": None,
            "next_plans": next_plans or [],
            "depends_on": [],
            "followups_out": followups_out if followups_out is not None else [
                {
                    "cluster": "process",
                    "summary": "Promote remaining roadmap track after current queue slice closes.",
                    "plan": None,
                }
            ],
            "canon_updates": [],
        }
        plan_path.write_text(
            dedent(
                f"""\
                # Plan: {title}

                **Date:** 2026-06-16 23:03 MSK
                **Stage:** Stage 2
                **Priority:** P2
                **Plan type:** dev
                **Status:** Done
                **Schema version:** plan.v1

                **Context links (source of truth):**
                - Code draft(s): `{draft_rel}`

                ## Meta (machine-readable JSON; required for new plans)
                ```json
                {json.dumps({"plan_meta": plan_meta}, ensure_ascii=False, indent=2)}
                ```

                ## Documentation impact / provenance
                - Source docs used: fixture.
                - Synchronous doc/registry targets: `docs/plans/README.md`.
                - Post-merge canon updates: `N/A (why=fixture)`.
                - Deferred documentation follow-ups: `N/A (why=fixture)`.
                - Provenance refs: fixture.

                ## Decisions (final)
                - Fixture for roadmap umbrella lifecycle closeout.
                {decisions_extra}

                ### UI/HTMX playbooks (micro-block; required for UI/HTMX tasks)
                - Archetype: `N/A (why=process fixture; no UI/HTMX surface)`
                - Modules: `N/A (why=process fixture; no UI/HTMX surface)`
                - Primary CTA: `N/A (why=process fixture; no UI/HTMX surface)`
                - header_filters: `N/A (why=process fixture; no UI/HTMX surface)`
                - Results count strategy: `N/A (why=process fixture; no UI/HTMX surface)`

                ## Scope
                - Fixture.

                ## Out of scope
                - Product/runtime behavior.

                ## Follow-ups (deferred)
                - Remaining roadmap track stays deferred unless closeout says otherwise.

                ## Rollout packet handoff
                - Role: `N/A (why=fixture)`
                - Packet path: `N/A (why=fixture)`
                - Target repo: `N/A (why=fixture)`
                - Suggested target plan slug: `N/A (why=fixture)`
                - Queue after import: `N/A (why=fixture)`

                ## Close-out routing
                - Roadmap/queue sync: fixture roadmap umbrella closeout.
                - Follow-up sync: fixture follow-up state.
                - Next bounded slice: none.
                - Terminal outcome: yes (fixture)
                {closeout_extra}

                ## Changes (by area)
                - Tooling/helpers: `scripts/plan_lint.py`
                - Docs/registry: `docs/plans/README.md`

                ## Acceptance criteria / DoD
                - [x] Fixture.

                ## Tests
                - `python3 scripts/test_plan_lint.py`

                ## Commands
                - `python3 scripts/test_plan_lint.py`

                ## Verification rerun / exec handoff
                - Mode: fresh-exec
                - Context source: fixture.
                - Prompt: fixture.
                - Command: `python3 scripts/test_plan_lint.py`
                - Expected artifact: deterministic warning.

                ## Review artifacts
                - Code review (primary): `docs/code_reviews/{plan_stem}.md`
                """
            ),
            encoding="utf-8",
        )
        return plan_path

    def _roadmap_findings(self, findings: list[object]) -> list[object]:
        return [
            finding
            for finding in findings
            if finding.message.startswith(MODULE.UMBRELLA_ROADMAP_LIFECYCLE_WARNING_PREFIX)
        ]

    def _write_selected_child_fixture(
        self,
        root: Path,
        *,
        plan_stem: str,
        closeout_next: str,
        roadmap_sync: str = "return T1 outcome to parent activation carrier.",
        next_plans: list[str] | None = None,
    ) -> Path:
        (root / ".git").mkdir()
        ensure_fixture_git(root)
        plan_rel = f"docs/plans/{plan_stem}.md"
        draft_rel = f"docs/code_drafts/{plan_stem}__code_draft.md"
        plan_path = root / plan_rel
        draft_path = root / draft_rel
        write_text_fixture(root, "docs/plans/README.md", "# Fixture README\n")
        write_text_fixture(
            root,
            "docs/_meta/plan_vocab.json",
            (MODULE_PATH.parent.parent / "docs" / "_meta" / "plan_vocab.json").read_text(encoding="utf-8"),
        )
        (root / "docs" / "plans").mkdir(parents=True, exist_ok=True)
        (root / "docs" / "code_drafts").mkdir(parents=True, exist_ok=True)
        (root / "docs" / "doc_reviews").mkdir(parents=True, exist_ok=True)

        draft_meta = {
            "code_draft_meta": {
                "plan": plan_rel,
                "cluster": "process",
                "targets": [
                    {"path": "docs/plans/README.md", "kind": "doc"},
                    {"path": "docs/_meta/plan_vocab.json", "kind": "doc"},
                ],
                "deleted_paths": [],
            }
        }
        draft_path.write_text(
            dedent(
                f"""\
                # Code draft: selected child roadmap fixture

                ## Meta (machine-readable JSON)
                ```json
                {json.dumps(draft_meta, ensure_ascii=False, indent=2)}
                ```
                """
            ),
            encoding="utf-8",
        )

        plan_meta = {
            "cluster": "process",
            "tags": ["planning-contour", "phase-2", "t1", "taxonomy"],
            "wave_family": None,
            "phase_overlay": None,
            "phase_state": None,
            "parent": "docs/plans/260616_2301_process_planning_contour_phase2_next_child_activation.md",
            "next_plans": next_plans or [],
            "depends_on": [
                "docs/plans/260616_2301_process_planning_contour_phase2_next_child_activation.md"
            ],
            "queue_activation": {
                "state": "owner_approved",
                "source_ref": "docs/plans/260616_2301_process_planning_contour_phase2_next_child_activation.md#Architect-Q&A",
                "reason": "fixture selected child",
            },
            "scope_expansion": {
                "state": "n/a",
                "target_contour": "N/A",
                "source_ref": "N/A (why=fixture)",
                "reason": "fixture",
            },
            "followups_out": [],
            "canon_updates": ["docs/plans/README.md", "docs/_meta/plan_vocab.json"],
        }
        plan_path.write_text(
            dedent(
                f"""\
                # Plan: planning-contour Phase 2 T1 taxonomy fixture

                **Date:** 2026-06-17 16:50 MSK
                **Stage:** Stage 2
                **Priority:** P1
                **Plan type:** dev
                **Status:** Done
                **Schema version:** plan.v1

                **Context links (source of truth):**
                - Code draft(s): `{draft_rel}`

                ## Meta (machine-readable JSON; required for new plans)
                ```json
                {json.dumps({"plan_meta": plan_meta}, ensure_ascii=False, indent=2)}
                ```

                ## Documentation impact / provenance
                - Source docs used: fixture parent.
                - Synchronous doc/registry targets: `docs/plans/README.md`, `docs/_meta/plan_vocab.json`.
                - Post-merge canon updates: `N/A (why=fixture)`.
                - Deferred documentation follow-ups: `A1`, `H1` and `V3` remain parent-level follow-ups unless T1 changes their prerequisites.
                - Provenance refs: fixture.

                ## Decisions (final)
                - Fixture selected child for transitive roadmap handoff.

                ### UI/HTMX playbooks (micro-block; required for UI/HTMX tasks)
                - Archetype: `N/A (why=process fixture; no UI/HTMX surface)`
                - Modules: `N/A (why=process fixture; no UI/HTMX surface)`
                - Primary CTA: `N/A (why=process fixture; no UI/HTMX surface)`
                - header_filters: `N/A (why=process fixture; no UI/HTMX surface)`
                - Results count strategy: `N/A (why=process fixture; no UI/HTMX surface)`

                ## Scope
                - Fixture selected child.

                ## Out of scope
                - Product/runtime behavior.

                ## Follow-ups (deferred)
                - `A1`, `H1` and `V3` remain parent-level follow-ups unless promoted.

                ## Rollout packet handoff
                - Role: `N/A (why=fixture)`
                - Packet path: `N/A (why=fixture)`
                - Target repo: `N/A (why=fixture)`
                - Suggested target plan slug: `N/A (why=fixture)`
                - Queue after import: `N/A (why=fixture)`

                ## Close-out routing
                - Roadmap/queue sync: {roadmap_sync}
                - Follow-up sync: update parent dispositions for `A1`, `H1` and `V3` if T1 changes their prerequisites.
                - Next bounded slice: {closeout_next}
                - Terminal outcome: yes - fixture selected child closes.

                ## Changes (by area)
                - Docs/registry: `docs/plans/README.md`, `docs/_meta/plan_vocab.json`

                ## Acceptance criteria / DoD
                - [x] Fixture.

                ## Tests
                - `python3 scripts/test_plan_lint.py`

                ## Commands
                - `python3 scripts/test_plan_lint.py`

                ## Verification rerun / exec handoff
                - Mode: fresh-exec
                - Context source: fixture.
                - Prompt: fixture.
                - Command: `python3 scripts/test_plan_lint.py`
                - Expected artifact: deterministic warning.

                ## Review artifacts
                - Doc review (docs-only): `docs/doc_reviews/{plan_stem}.md`
                """
            ),
            encoding="utf-8",
        )
        return plan_path

    def test_done_roadmap_umbrella_with_open_plan_null_followup_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(Path(tmpdir), plan_stem="260616_2303_process_roadmap_false_close")

            findings = MODULE.lint_plan(plan_path)

        roadmap_findings = self._roadmap_findings(findings)
        self.assertEqual(len(roadmap_findings), 1)
        self.assertEqual(roadmap_findings[0].severity, "ERROR")
        self.assertIn("followups_out[].plan=null", roadmap_findings[0].message)

    def test_done_roadmap_umbrella_next_plans_does_not_close_unrelated_followups(self) -> None:
        next_plan = "docs/plans/260616_2301_process_selected_next_slice.md"
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260616_2303_process_roadmap_next_plans_unrelated_followup",
                next_plans=[next_plan],
                followups_out=[
                    {
                        "cluster": "process",
                        "summary": "Promote separate V3 route-discrimination track after current child closes.",
                        "plan": None,
                    }
                ],
            )
            write_text_fixture(root, next_plan, "# Plan: selected next slice\n")

            findings = MODULE.lint_plan(plan_path)

        roadmap_findings = self._roadmap_findings(findings)
        self.assertEqual(len(roadmap_findings), 1)
        self.assertEqual(roadmap_findings[0].severity, "ERROR")
        self.assertIn("followups_out[1]", roadmap_findings[0].message)
        self.assertIn("Promote separate V3 route-discrimination track", roadmap_findings[0].message)

    def test_done_roadmap_umbrella_with_negated_handled_summary_still_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260616_2304_process_roadmap_not_handled",
                followups_out=[
                    {
                        "cluster": "process",
                        "summary": "Remaining roadmap track is not handled and still needs Owner decision.",
                        "plan": None,
                    }
                ],
            )

            findings = MODULE.lint_plan(plan_path)

        roadmap_findings = self._roadmap_findings(findings)
        self.assertEqual(len(roadmap_findings), 1)

    def test_done_roadmap_umbrella_with_pending_handled_summary_still_warns(self) -> None:
        summaries = [
            "Remaining roadmap track needs to be handled by Owner decision.",
            "Remaining roadmap track needs Owner to mark as handled.",
            "Remaining roadmap track should be handled later by Owner.",
            "Remaining roadmap track should later be marked as handled.",
            "Remaining roadmap track to be handled after current queue closes.",
        ]
        for idx, summary in enumerate(summaries, start=1):
            with self.subTest(summary=summary), tempfile.TemporaryDirectory() as tmpdir:
                plan_path = self._write_fixture(
                    Path(tmpdir),
                    plan_stem=f"260616_2304_process_roadmap_pending_handled_{idx}",
                    followups_out=[
                        {
                            "cluster": "process",
                            "summary": summary,
                            "plan": None,
                        }
                    ],
                )

                findings = MODULE.lint_plan(plan_path)

            roadmap_findings = self._roadmap_findings(findings)
            self.assertEqual(len(roadmap_findings), 1)

    def test_done_roadmap_umbrella_with_bare_terminal_status_still_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260616_2304_process_roadmap_bare_cancelled_status",
                followups_out=[
                    {
                        "cluster": "process",
                        "summary": "Remaining roadmap track.",
                        "plan": None,
                        "status": "cancelled",
                    }
                ],
            )

            findings = MODULE.lint_plan(plan_path)

        roadmap_findings = self._roadmap_findings(findings)
        self.assertEqual(len(roadmap_findings), 1)

    def test_done_roadmap_umbrella_with_pending_summary_and_terminal_status_still_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260616_2304_process_roadmap_pending_summary_handled_status",
                followups_out=[
                    {
                        "cluster": "process",
                        "summary": "Remaining roadmap track needs Owner to mark as handled.",
                        "plan": None,
                        "status": "handled",
                    }
                ],
            )

            findings = MODULE.lint_plan(plan_path)

        roadmap_findings = self._roadmap_findings(findings)
        self.assertEqual(len(roadmap_findings), 1)

    def test_generic_disposition_guidance_outside_closeout_still_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260616_2305_process_roadmap_guidance_not_disposition",
                decisions_extra=(
                    "- Guidance says successor activation plan materialized and linked is required before closeout.\n"
                ),
            )

            findings = MODULE.lint_plan(plan_path)

        roadmap_findings = self._roadmap_findings(findings)
        self.assertEqual(len(roadmap_findings), 1)

    def test_generic_successor_activation_in_closeout_still_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260616_2305_process_roadmap_generic_successor_activation",
                closeout_extra=(
                    "- Successor activation plan materialized and linked: "
                    "`docs/plans/260616_2301_process_next_child_activation.md`.\n"
                ),
            )

            findings = MODULE.lint_plan(plan_path)

        roadmap_findings = self._roadmap_findings(findings)
        self.assertEqual(len(roadmap_findings), 1)

    def test_done_roadmap_umbrella_with_successor_activation_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260616_2306_process_roadmap_successor_activation",
                closeout_extra=(
                    "- Successor activation plan materialized and linked for followups_out[1]: "
                    "`docs/plans/260616_2301_process_next_child_activation.md`.\n"
                ),
            )

            findings = MODULE.lint_plan(plan_path)

        self.assertEqual(self._roadmap_findings(findings), [])

    def test_done_roadmap_umbrella_with_parked_reference_keep_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260616_2307_process_roadmap_parked_reference",
                closeout_extra=(
                    "- Parked/reference keep: remaining roadmap track is non-executable "
                    "discovery material until a new activation carrier exists.\n"
                ),
            )

            findings = MODULE.lint_plan(plan_path)

        self.assertEqual(self._roadmap_findings(findings), [])

    def test_done_roadmap_umbrella_with_handled_followup_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260616_2308_process_roadmap_handled_followup",
                followups_out=[
                    {
                        "cluster": "process",
                        "summary": "Remaining track handled by Owner cancellation.",
                        "plan": None,
                    }
                ],
            )

            findings = MODULE.lint_plan(plan_path)

        self.assertEqual(self._roadmap_findings(findings), [])

    def test_done_roadmap_umbrella_with_concrete_followup_plan_passes(self) -> None:
        followup_plan = "docs/plans/260616_2310_process_roadmap_promoted_followup.md"
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260616_2310_process_roadmap_concrete_followup_plan",
                followups_out=[
                    {
                        "cluster": "process",
                        "summary": "Promote remaining roadmap track.",
                        "plan": followup_plan,
                    }
                ],
            )
            write_text_fixture(root, followup_plan, "# Plan: promoted follow-up\n")

            findings = MODULE.lint_plan(plan_path)

        self.assertEqual(self._roadmap_findings(findings), [])

    def test_done_roadmap_umbrella_with_terminal_disposition_and_reason_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260616_2311_process_roadmap_terminal_disposition_reason",
                followups_out=[
                    {
                        "cluster": "process",
                        "summary": "Remaining roadmap track.",
                        "plan": None,
                        "status": "cancelled",
                        "disposition": "cancelled after Owner chose no successor.",
                    }
                ],
            )

            findings = MODULE.lint_plan(plan_path)

        self.assertEqual(self._roadmap_findings(findings), [])

    def test_done_ordinary_plan_with_open_followup_is_not_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260616_2309_process_single_slice_done",
                title="single process slice fixture",
                tags=["process"],
            )

            findings = MODULE.lint_plan(plan_path)

        self.assertEqual(self._roadmap_findings(findings), [])

    def test_done_selected_roadmap_child_punting_next_to_parent_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_selected_child_fixture(
                Path(tmpdir),
                plan_stem="260617_1650_process_selected_child_punts_next",
                closeout_next=(
                    "likely `V3` if route discrimination needs proof, `A1` if sibling adoption is next, "
                    "or `H1` if accepted fields need gates."
                ),
            )

            findings = MODULE.lint_plan(plan_path)

        roadmap_findings = self._roadmap_findings(findings)
        self.assertEqual(len(roadmap_findings), 1)
        self.assertEqual(roadmap_findings[0].severity, "WARN")
        self.assertIn("selected roadmap child", roadmap_findings[0].message)

    def test_done_selected_roadmap_child_parent_path_only_still_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_selected_child_fixture(
                Path(tmpdir),
                plan_stem="260617_1653_process_selected_child_parent_path_only",
                roadmap_sync=(
                    "return T1 outcome to parent activation carrier "
                    "`docs/plans/260616_2301_process_planning_contour_phase2_next_child_activation.md`."
                ),
                closeout_next=(
                    "parent can choose `V3` if route discrimination needs proof, `A1` if sibling adoption "
                    "is next, or `H1` if accepted fields need gates."
                ),
            )

            findings = MODULE.lint_plan(plan_path)

        roadmap_findings = self._roadmap_findings(findings)
        self.assertEqual(len(roadmap_findings), 1)
        self.assertEqual(roadmap_findings[0].severity, "WARN")
        self.assertIn("selected roadmap child", roadmap_findings[0].message)

    def test_done_selected_roadmap_child_with_materialized_next_plan_passes(self) -> None:
        next_plan = "docs/plans/260617_1630_process_planning_contour_phase2_v3_route_discrimination_pilot.md"
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_selected_child_fixture(
                root,
                plan_stem="260617_1651_process_selected_child_materialized_next",
                closeout_next=f"`{next_plan}`",
                next_plans=[next_plan],
            )
            write_text_fixture(root, next_plan, "# Plan: child\n")

            findings = MODULE.lint_plan(plan_path)

        self.assertEqual(self._roadmap_findings(findings), [])

    def test_done_selected_roadmap_child_with_no_successor_reason_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_selected_child_fixture(
                Path(tmpdir),
                plan_stem="260617_1652_process_selected_child_no_successor",
                closeout_next="N/A (why=no successor; all remaining roadmap tracks are cancelled/handled by Owner).",
            )

            findings = MODULE.lint_plan(plan_path)

        self.assertEqual(self._roadmap_findings(findings), [])


class PlanLintExactBundlePreflightTests(unittest.TestCase):
    def _write_fixture(self, *args, **kwargs) -> Path:
        helper = PlanLintReviewRouteDeterminismTests()
        return helper._write_fixture(*args, **kwargs)

    def _touch(self, root: Path, rel_path: str, text: str = "fixture\n") -> None:
        write_text_fixture(root, rel_path, text)

    def test_ready_for_coder_missing_code_draft_meta_fails_before_reviewer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_stem = "260423_0133_process_preflight_missing_meta"
            plan_path = self._write_fixture(
                root,
                plan_stem=plan_stem,
                plan_status="Ready for Coder",
                target_paths=["scripts/live_target.py"],
                review_artifact_lines=[
                    f"- Code review (primary): `docs/code_reviews/{plan_stem}.md`",
                ],
            )
            self._touch(root, "scripts/live_target.py")
            draft_path = root / "docs" / "code_drafts" / f"{plan_stem}__code_draft.md"
            draft_path.write_text("# Code draft without metadata\n", encoding="utf-8")

            findings = MODULE.lint_plan(plan_path)

        messages = [finding.message for finding in findings if "Planner exact-bundle preflight failed" in finding.message]
        self.assertEqual(len(messages), 1)
        self.assertIn("missing code_draft_meta", messages[0])

    def test_ready_for_coder_stale_target_inventory_fails_before_reviewer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_stem = "260423_0134_process_preflight_stale_target"
            plan_path = self._write_fixture(
                root,
                plan_stem=plan_stem,
                plan_status="Ready for Coder",
                target_paths=["scripts/missing_target.py"],
                review_artifact_lines=[
                    f"- Code review (primary): `docs/code_reviews/{plan_stem}.md`",
                ],
            )

            findings = MODULE.lint_plan(plan_path)

        messages = [finding.message for finding in findings if "Planner exact-bundle preflight failed" in finding.message]
        self.assertEqual(len(messages), 1)
        self.assertIn("missing/stale path `scripts/missing_target.py`", messages[0])

    def test_ready_for_coder_valid_preflight_metadata_passes_with_planned_review_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_stem = "260423_0135_process_preflight_valid"
            target_rel = "scripts/live_target.py"
            plan_path = self._write_fixture(
                root,
                plan_stem=plan_stem,
                plan_status="Ready for Coder",
                target_paths=[target_rel],
                review_artifact_lines=[
                    f"- Code review (primary): `docs/code_reviews/{plan_stem}.md`",
                ],
            )
            self._touch(root, target_rel)

            findings = MODULE.lint_plan(plan_path)

        messages = [finding.message for finding in findings if "Planner exact-bundle preflight failed" in finding.message]
        self.assertEqual(messages, [])

    def test_ready_for_planner_bad_code_draft_meta_warns_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_stem = "260423_0136_process_preflight_seed_warning"
            plan_path = self._write_fixture(
                root,
                plan_stem=plan_stem,
                plan_status="Ready for Planner",
                target_paths=["scripts/live_target.py"],
                review_artifact_lines=[
                    f"- Code review (primary): `docs/code_reviews/{plan_stem}.md`",
                ],
                complete=True,
            )
            draft_path = root / "docs" / "code_drafts" / f"{plan_stem}__code_draft.md"
            draft_path.write_text("# Code draft without metadata\n", encoding="utf-8")

            findings = MODULE.lint_plan(plan_path)

        messages = [finding for finding in findings if "Planner exact-bundle seed warning" in finding.message]
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].severity, "WARN")
        self.assertIn("missing code_draft_meta", messages[0].message)
        self.assertNotIn("ERROR", [finding.severity for finding in findings])

    def test_ready_for_planner_stale_target_inventory_warns_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_stem = "260423_0137_process_preflight_stale_seed_warning"
            plan_path = self._write_fixture(
                root,
                plan_stem=plan_stem,
                plan_status="Ready for Planner",
                target_paths=["scripts/missing_target.py"],
                review_artifact_lines=[
                    f"- Code review (primary): `docs/code_reviews/{plan_stem}.md`",
                ],
                complete=True,
            )

            findings = MODULE.lint_plan(plan_path)

        messages = [finding for finding in findings if "Planner exact-bundle seed warning" in finding.message]
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].severity, "WARN")
        self.assertIn("missing/stale path `scripts/missing_target.py`", messages[0].message)
        self.assertNotIn("ERROR", [finding.severity for finding in findings])

    def test_ready_for_coder_trailing_space_target_path_resolves_literally(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_stem = "260423_0138_process_preflight_trailing_space"
            target_rel = "scripts/trailing_target.py "  # literal trailing space
            plan_path = self._write_fixture(
                root,
                plan_stem=plan_stem,
                plan_status="Ready for Coder",
                target_paths=[target_rel],
                review_artifact_lines=[
                    f"- Code review (primary): `docs/code_reviews/{plan_stem}.md`",
                ],
            )
            self._touch(root, target_rel)  # create the literal trailing-space file

            findings = MODULE.lint_plan(plan_path)

        messages = [
            finding.message for finding in findings if "Planner exact-bundle preflight failed" in finding.message
        ]
        self.assertEqual(messages, [])

    def test_ready_for_coder_trimmed_alias_does_not_green_missing_trailing_space_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_stem = "260423_0139_process_preflight_trimmed_alias"
            declared = "scripts/alias_target.py "  # literal trailing space
            plan_path = self._write_fixture(
                root,
                plan_stem=plan_stem,
                plan_status="Ready for Coder",
                target_paths=[declared],
                review_artifact_lines=[
                    f"- Code review (primary): `docs/code_reviews/{plan_stem}.md`",
                ],
            )
            # Only the trimmed (no-space) file exists; the literal trailing-space target must stay missing.
            self._touch(root, "scripts/alias_target.py")

            findings = MODULE.lint_plan(plan_path)

        messages = [
            finding.message for finding in findings if "Planner exact-bundle preflight failed" in finding.message
        ]
        self.assertEqual(len(messages), 1)
        self.assertIn("missing/stale path `scripts/alias_target.py `", messages[0])

    def test_ready_for_coder_empty_target_path_fails_as_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_stem = "260423_0140_process_preflight_empty_path"
            plan_path = self._write_fixture(
                root,
                plan_stem=plan_stem,
                plan_status="Ready for Coder",
                target_paths=[""],
                review_artifact_lines=[
                    f"- Code review (primary): `docs/code_reviews/{plan_stem}.md`",
                ],
            )

            findings = MODULE.lint_plan(plan_path)

        messages = [
            finding.message for finding in findings if "Planner exact-bundle preflight failed" in finding.message
        ]
        self.assertEqual(len(messages), 1)
        self.assertIn("invalid target path", messages[0])

    def test_ready_for_coder_whitespace_only_target_path_is_literal_non_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_stem = "260423_0141_process_preflight_whitespace_path"
            plan_path = self._write_fixture(
                root,
                plan_stem=plan_stem,
                plan_status="Ready for Coder",
                target_paths=["   "],  # whitespace-only: literal non-empty, not normalized to empty
                review_artifact_lines=[
                    f"- Code review (primary): `docs/code_reviews/{plan_stem}.md`",
                ],
            )

            findings = MODULE.lint_plan(plan_path)

        messages = [
            finding.message for finding in findings if "Planner exact-bundle preflight failed" in finding.message
        ]
        # Whitespace-only path is NOT rejected as "invalid" (that would require trimming to empty);
        # it resolves to a missing literal file and fails as missing/stale with the literal value preserved.
        self.assertEqual(len(messages), 1)
        self.assertIn("missing/stale path `   `", messages[0])


class PlanLintSharedHelperDependentInventoryTests(unittest.TestCase):
    REQUIRED_ROLE_RUNTIME_DEPENDENTS = (
        "scripts/test_planveyor_init_capture.py",
        "scripts/test_planveyor_trace_extractor.py",
        "scripts/test_planveyor_bare_entrypoints.py",
        "scripts/test_planveyor_router_merge_boundary.py",
    )

    def _write_fixture(
        self,
        root: Path,
        *,
        target_paths: list[str],
        extra_sections: str = "",
        plan_status: str = "Ready for Coder",
        plan_stem: str = "260624_1439_process_shared_helper_inventory_fixture",
    ) -> Path:
        helper = PlanLintReviewRouteDeterminismTests()
        return helper._write_fixture(
            root,
            plan_stem=plan_stem,
            plan_status=plan_status,
            target_paths=target_paths,
            review_artifact_lines=[
                f"- Code review (primary): `docs/code_reviews/{plan_stem}.md`",
            ],
            extra_sections=extra_sections,
        )

    def _touch(self, root: Path, rel_path: str, text: str = "fixture\n") -> None:
        write_text_fixture(root, rel_path, text)

    def _shared_helper_findings(self, findings: list[object]) -> list[object]:
        return [finding for finding in findings if "Shared helper dependent inventory hard gate" in finding.message]

    def _explicit_inventory_section(self) -> str:
        inventory = "\n".join(f"- `{dependent}`" for dependent in self.REQUIRED_ROLE_RUNTIME_DEPENDENTS)
        return dedent(
            f"""\
            ## Reviewability preflight receipt

            - `dependent tests / dependent docs / known consumer paths`: `scripts/planveyor/role_runtime.zsh`
              run-to-confirm inventory:
            {inventory}
            """
        )

    def test_shared_helper_target_without_dependent_inventory_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                target_paths=["scripts/planveyor/role_runtime.zsh"],
            )
            self._touch(root, "scripts/planveyor/role_runtime.zsh")

            findings = MODULE.lint_plan(plan_path)

        messages = self._shared_helper_findings(findings)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].severity, "ERROR")
        self.assertIn("scripts/planveyor/role_runtime.zsh", messages[0].message)
        self.assertIn("shared_helper_dependent_inventory.missing", messages[0].message)
        self.assertIn("missing/incomplete dependent inventory", messages[0].message)
        self.assertIn("scripts/test_planveyor_trace_extractor.py", messages[0].message)

    def test_shared_helper_explicit_dependent_inventory_passes_without_mutable_dependent_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                target_paths=["scripts/planveyor/role_runtime.zsh"],
                extra_sections=self._explicit_inventory_section(),
            )
            self._touch(root, "scripts/planveyor/role_runtime.zsh")

            findings = MODULE.lint_plan(plan_path)

        self.assertEqual(self._shared_helper_findings(findings), [])

    def test_superseded_shared_helper_target_without_dependent_inventory_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_status="Superseded",
                target_paths=["scripts/planveyor/role_runtime.zsh"],
            )
            self._touch(root, "scripts/planveyor/role_runtime.zsh")

            findings = MODULE.lint_plan(plan_path)

        messages = self._shared_helper_findings(findings)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].severity, "ERROR")
        self.assertIn("shared_helper_dependent_inventory.missing", messages[0].message)
        self.assertIn("scripts/planveyor/role_runtime.zsh", messages[0].message)

    def test_superseded_shared_helper_explicit_dependent_inventory_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_status="Superseded",
                target_paths=["scripts/planveyor/role_runtime.zsh"],
                extra_sections=self._explicit_inventory_section(),
            )
            self._touch(root, "scripts/planveyor/role_runtime.zsh")

            findings = MODULE.lint_plan(plan_path)

        self.assertEqual(self._shared_helper_findings(findings), [])

    def test_shared_helper_audit_later_inventory_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                target_paths=["scripts/planveyor/role_runtime.zsh"],
                extra_sections=dedent(
                    """\
                    ## Reviewability preflight receipt

                    - `dependent tests / dependent docs / known consumer paths`: audit later.
                    """
                ),
            )
            self._touch(root, "scripts/planveyor/role_runtime.zsh")

            findings = MODULE.lint_plan(plan_path)

        messages = self._shared_helper_findings(findings)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].severity, "ERROR")
        self.assertIn("shared_helper_dependent_inventory.placeholder", messages[0].message)
        self.assertIn("placeholder/non-inventory carrier", messages[0].message)

    def test_shared_helper_audit_later_inventory_errors_when_dependencies_are_incidental(self) -> None:
        incidental_mentions = "\n".join(f"- Historical context mentions `{dependent}`." for dependent in self.REQUIRED_ROLE_RUNTIME_DEPENDENTS)
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                target_paths=["scripts/planveyor/role_runtime.zsh"],
                extra_sections=dedent(
                    f"""\
                    ## Incidental dependent context

                    {incidental_mentions}

                    ## Reviewability preflight receipt

                    - `dependent tests / dependent docs / known consumer paths`: audit later.
                    """
                ),
            )
            self._touch(root, "scripts/planveyor/role_runtime.zsh")

            findings = MODULE.lint_plan(plan_path)

        messages = self._shared_helper_findings(findings)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].severity, "ERROR")
        self.assertIn("shared_helper_dependent_inventory.placeholder", messages[0].message)
        self.assertIn("placeholder/non-inventory carrier", messages[0].message)

    def test_non_shared_target_does_not_require_dependent_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                target_paths=["scripts/plan_lint.py"],
            )
            self._touch(root, "scripts/plan_lint.py")

            findings = MODULE.lint_plan(plan_path)

        self.assertEqual(self._shared_helper_findings(findings), [])

    def test_superseded_non_shared_target_does_not_require_dependent_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_status="Superseded",
                target_paths=["scripts/plan_lint.py"],
            )
            self._touch(root, "scripts/plan_lint.py")

            findings = MODULE.lint_plan(plan_path)

        self.assertEqual(self._shared_helper_findings(findings), [])

    def test_shared_helper_partial_or_inconsistent_inventory_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                target_paths=["scripts/planveyor/role_runtime.zsh"],
                extra_sections=dedent(
                    """\
                    ## Reviewability preflight receipt

                    - `dependent tests / dependent docs / known consumer paths`: `scripts/test_plan_lint.py`.
                    """
                ),
            )
            self._touch(root, "scripts/planveyor/role_runtime.zsh")

            findings = MODULE.lint_plan(plan_path)

        messages = self._shared_helper_findings(findings)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].severity, "ERROR")
        self.assertIn("shared_helper_dependent_inventory.missing", messages[0].message)
        self.assertIn("scripts/test_planveyor_init_capture.py", messages[0].message)


class PlanLintScopeRouteClassificationTests(unittest.TestCase):
    def _write_fixture(self, *args, **kwargs) -> Path:
        helper = PlanLintReviewRouteDeterminismTests()
        return helper._write_fixture(*args, **kwargs)

    def _review_line(self, plan_stem: str) -> str:
        return f"- Code review (primary): `docs/code_reviews/{plan_stem}.md`"

    def _route_findings(self, findings: list[object]) -> list[object]:
        return [finding for finding in findings if "Ambiguous scope/follow-up routing" in finding.message]

    def _route_note(self, route_class: str | None = None) -> str:
        classifier = f"\n- Route classification: `{route_class}`." if route_class else ""
        return dedent(
            f"""\
            ## Scope split note

            - Active blocker mentions broad cleanup and follow-up later for an out-of-bundle scaffold issue.{classifier}
            """
        )

    def _template_route_boilerplate(self) -> str:
        return dedent(
            """\
            ## Template boilerplate

            > Shared generic set = `reopened-blocker classification / same-contract reroute`.
            > Reopened-blocker classification: `real scope expansion`.


            """
        )

    def test_ambiguous_active_scope_followup_text_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_stem = "260512_1135_process_scope_route_ambiguous"
            plan_path = self._write_fixture(
                root,
                plan_stem=plan_stem,
                target_paths=["scripts/plan_lint.py"],
                review_artifact_lines=[self._review_line(plan_stem)],
                extra_sections=self._route_note(),
            )

            findings = MODULE.lint_plan(plan_path)

        messages = [finding.message for finding in self._route_findings(findings)]
        self.assertEqual(len(messages), 1)
        self.assertIn("same-contract reroute", messages[0])
        self.assertIn("real scope expansion", messages[0])
        self.assertIn("de-scoped follow-up", messages[0])

    def test_template_route_boilerplate_does_not_satisfy_ambiguous_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_stem = "260512_1135_process_scope_route_template_boilerplate"
            plan_path = self._write_fixture(
                root,
                plan_stem=plan_stem,
                target_paths=["scripts/plan_lint.py"],
                review_artifact_lines=[self._review_line(plan_stem)],
                extra_sections=self._template_route_boilerplate() + self._route_note(),
            )

            findings = MODULE.lint_plan(plan_path)

        messages = self._route_findings(findings)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].severity, "ERROR")

    def test_same_contract_reroute_route_class_passes_scope_guard(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_stem = "260512_1136_process_scope_route_same_contract"
            plan_path = self._write_fixture(
                root,
                plan_stem=plan_stem,
                target_paths=["scripts/plan_lint.py"],
                review_artifact_lines=[self._review_line(plan_stem)],
                extra_sections=self._route_note("same-contract reroute"),
            )

            findings = MODULE.lint_plan(plan_path)

        self.assertEqual(self._route_findings(findings), [])

    def test_real_scope_expansion_route_class_passes_scope_guard(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_stem = "260512_1137_process_scope_route_expansion"
            plan_path = self._write_fixture(
                root,
                plan_stem=plan_stem,
                target_paths=["scripts/plan_lint.py"],
                review_artifact_lines=[self._review_line(plan_stem)],
                extra_sections=self._route_note("real scope expansion"),
            )

            findings = MODULE.lint_plan(plan_path)

        self.assertEqual(self._route_findings(findings), [])

    def test_de_scoped_followup_route_class_passes_scope_guard(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_stem = "260512_1138_process_scope_route_de_scoped"
            plan_path = self._write_fixture(
                root,
                plan_stem=plan_stem,
                target_paths=["scripts/plan_lint.py"],
                review_artifact_lines=[self._review_line(plan_stem)],
                extra_sections=self._route_note("de-scoped follow-up"),
            )

            findings = MODULE.lint_plan(plan_path)

        self.assertEqual(self._route_findings(findings), [])

    def test_done_plan_with_ambiguous_scope_text_is_legacy_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_stem = "260512_1139_process_scope_route_done_context"
            plan_path = self._write_fixture(
                root,
                plan_stem=plan_stem,
                plan_status="Done",
                target_paths=["scripts/plan_lint.py"],
                review_artifact_lines=[self._review_line(plan_stem)],
                extra_sections=self._route_note(),
            )

            findings = MODULE.lint_plan(plan_path)

        self.assertEqual(self._route_findings(findings), [])


class PlanLintDocumentationImpactTests(unittest.TestCase):
    def _write_fixture(self, *args, **kwargs) -> Path:
        helper = PlanLintReviewRouteDeterminismTests()
        return helper._write_fixture(*args, **kwargs)

    def _review_line(self, plan_stem: str) -> str:
        return f"- Code review (primary): `docs/code_reviews/{plan_stem}.md`"

    def _section(
        self,
        *,
        source: str = "`scripts/plan_lint.py`",
        sync: str = "N/A (why=fixture has no synchronous docs target)",
        post_merge: str = "N/A (why=fixture)",
        deferred: str = "N/A (why=fixture)",
        provenance: str = "fixture",
    ) -> str:
        return dedent(
            f"""\
            ## Documentation impact / provenance
            - Source docs used: {source}
            - Synchronous doc/registry targets: {sync}
            - Post-merge canon updates: {post_merge}
            - Deferred documentation follow-ups: {deferred}
            - Provenance refs: {provenance}
            """
        ).rstrip()

    def _documentation_impact_findings(self, findings: list[object]) -> list[object]:
        return [finding for finding in findings if "Documentation impact / provenance" in finding.message]

    def test_valid_documentation_impact_carrier_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_stem = "260510_1900_process_doc_impact_valid"
            plan_path = self._write_fixture(
                root,
                plan_stem=plan_stem,
                target_paths=["scripts/plan_lint.py", "docs/tools/owner_runbook_codex.md"],
                review_artifact_lines=[self._review_line(plan_stem)],
                extra_sections=self._section(sync="`docs/tools/owner_runbook_codex.md`"),
            )

            findings = MODULE.lint_plan(plan_path)

        self.assertEqual(self._documentation_impact_findings(findings), [])

    def test_missing_documentation_impact_section_warns_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_stem = "260510_1901_process_doc_impact_missing"
            plan_path = self._write_fixture(
                root,
                plan_stem=plan_stem,
                target_paths=["scripts/plan_lint.py"],
                review_artifact_lines=[self._review_line(plan_stem)],
            )

            findings = MODULE.lint_plan(plan_path)

        doc_findings = self._documentation_impact_findings(findings)
        self.assertEqual(len(doc_findings), 1)
        self.assertEqual(doc_findings[0].severity, "WARN")
        self.assertIn("missing `## Documentation impact / provenance`", doc_findings[0].message)
        self.assertNotIn("ERROR", [finding.severity for finding in doc_findings])

    def test_old_date_plan_without_documentation_impact_section_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_stem = "260423_0138_process_doc_impact_legacy_missing"
            plan_path = self._write_fixture(
                root,
                plan_stem=plan_stem,
                target_paths=["scripts/plan_lint.py"],
                review_artifact_lines=[self._review_line(plan_stem)],
            )

            findings = MODULE.lint_plan(plan_path)

        self.assertEqual(len(self._documentation_impact_findings(findings)), 1)
        self.assertEqual(self._documentation_impact_findings(findings)[0].severity, "WARN")

    def test_placeholder_documentation_impact_field_warns_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_stem = "260510_1902_process_doc_impact_placeholder"
            plan_path = self._write_fixture(
                root,
                plan_stem=plan_stem,
                target_paths=["scripts/plan_lint.py"],
                review_artifact_lines=[self._review_line(plan_stem)],
                extra_sections=self._section(source="TBD"),
            )

            findings = MODULE.lint_plan(plan_path)

        doc_findings = self._documentation_impact_findings(findings)
        self.assertEqual(len(doc_findings), 1)
        self.assertEqual(doc_findings[0].severity, "WARN")
        self.assertIn("`- Source docs used:` is a placeholder", doc_findings[0].message)

    def test_explicit_na_with_reason_documentation_impact_values_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_stem = "260510_1903_process_doc_impact_na_with_reason"
            plan_path = self._write_fixture(
                root,
                plan_stem=plan_stem,
                target_paths=["scripts/plan_lint.py"],
                review_artifact_lines=[self._review_line(plan_stem)],
                extra_sections=self._section(
                    source="N/A (why=fixture covers no source docs)",
                    sync="N/A (why=fixture has no sync docs targets)",
                    post_merge="N/A (why=fixture)",
                    deferred="N/A (why=fixture)",
                    provenance="N/A (why=fixture)",
                ),
            )

            findings = MODULE.lint_plan(plan_path)

        self.assertEqual(self._documentation_impact_findings(findings), [])

    def test_naked_na_documentation_impact_value_warns_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_stem = "260510_1904_process_doc_impact_naked_na"
            plan_path = self._write_fixture(
                root,
                plan_stem=plan_stem,
                target_paths=["scripts/plan_lint.py"],
                review_artifact_lines=[self._review_line(plan_stem)],
                extra_sections=self._section(source="N/A"),
            )

            findings = MODULE.lint_plan(plan_path)

        doc_findings = self._documentation_impact_findings(findings)
        self.assertEqual(len(doc_findings), 1)
        self.assertEqual(doc_findings[0].severity, "WARN")
        self.assertIn("uses `N/A` without `why=...`", doc_findings[0].message)

    def test_sync_doc_target_missing_from_code_draft_targets_warns_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_stem = "260510_1905_process_doc_impact_sync_target_drift"
            plan_path = self._write_fixture(
                root,
                plan_stem=plan_stem,
                target_paths=["scripts/plan_lint.py"],
                review_artifact_lines=[self._review_line(plan_stem)],
                extra_sections=self._section(sync="`docs/tools/owner_runbook_codex.md`"),
            )

            findings = MODULE.lint_plan(plan_path)

        messages = [finding.message for finding in self._documentation_impact_findings(findings)]
        self.assertEqual(len(messages), 1)
        self.assertIn("lists `docs/tools/owner_runbook_codex.md`", messages[0])
        self.assertIn("code_draft_meta.targets", messages[0])

    def test_sync_doc_target_missing_from_code_draft_targets_errors_for_new_handoffs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_stem = "260517_1224_process_doc_impact_sync_target_drift_error"
            plan_path = self._write_fixture(
                root,
                plan_stem=plan_stem,
                target_paths=["scripts/plan_lint.py"],
                review_artifact_lines=[self._review_line(plan_stem)],
                extra_sections=self._section(sync="`docs/tools/owner_runbook_codex.md`"),
            )

            findings = MODULE.lint_plan(plan_path)

        doc_findings = self._documentation_impact_findings(findings)
        self.assertEqual(len(doc_findings), 1)
        self.assertEqual(doc_findings[0].severity, "ERROR")
        self.assertIn("lists `docs/tools/owner_runbook_codex.md`", doc_findings[0].message)

    def test_code_draft_doc_target_missing_from_sync_carrier_warns_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_stem = "260510_1906_process_doc_impact_code_draft_doc_drift"
            plan_path = self._write_fixture(
                root,
                plan_stem=plan_stem,
                target_paths=["scripts/plan_lint.py", "docs/tools/owner_runbook_codex.md"],
                review_artifact_lines=[self._review_line(plan_stem)],
                extra_sections=self._section(sync="N/A (why=fixture claims no synchronous docs target)"),
            )

            findings = MODULE.lint_plan(plan_path)

        messages = [finding.message for finding in self._documentation_impact_findings(findings)]
        self.assertTrue(
            any("code draft doc target(s) exist: `docs/tools/owner_runbook_codex.md`" in message for message in messages)
        )
        self.assertTrue(all(finding.severity == "ERROR" for finding in self._documentation_impact_findings(findings)))

    def test_code_draft_doc_target_missing_from_sync_carrier_errors_for_new_handoffs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_stem = "260517_1225_process_doc_impact_code_draft_doc_drift_error"
            plan_path = self._write_fixture(
                root,
                plan_stem=plan_stem,
                target_paths=["scripts/plan_lint.py", "docs/tools/owner_runbook_codex.md"],
                review_artifact_lines=[self._review_line(plan_stem)],
                extra_sections=self._section(sync="N/A (why=fixture claims no synchronous docs target)"),
            )

            findings = MODULE.lint_plan(plan_path)

        doc_findings = self._documentation_impact_findings(findings)
        self.assertTrue(
            any("code draft doc target(s) exist: `docs/tools/owner_runbook_codex.md`" in finding.message for finding in doc_findings)
        )
        self.assertTrue(all(finding.severity == "ERROR" for finding in doc_findings))

    def test_new_pre_handoff_doc_target_drift_stays_warning_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_stem = "260517_1226_process_doc_impact_pre_handoff_drift"
            plan_path = self._write_fixture(
                root,
                plan_stem=plan_stem,
                plan_status="Ready for Planner",
                target_paths=["scripts/plan_lint.py"],
                review_artifact_lines=[self._review_line(plan_stem)],
                extra_sections=self._section(sync="`docs/tools/owner_runbook_codex.md`"),
            )

            findings = MODULE.lint_plan(plan_path)

        doc_findings = self._documentation_impact_findings(findings)
        self.assertEqual(len(doc_findings), 1)
        self.assertEqual(doc_findings[0].severity, "WARN")

    def test_new_missing_documentation_impact_section_stays_warning_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_stem = "260517_1227_process_doc_impact_missing_still_warning"
            plan_path = self._write_fixture(
                root,
                plan_stem=plan_stem,
                target_paths=["scripts/plan_lint.py"],
                review_artifact_lines=[self._review_line(plan_stem)],
            )

            findings = MODULE.lint_plan(plan_path)

        doc_findings = self._documentation_impact_findings(findings)
        self.assertEqual(len(doc_findings), 1)
        self.assertEqual(doc_findings[0].severity, "WARN")


class PlanLintAnalysisRouteSingleAuthorityTests(unittest.TestCase):
    def _write_fixture(
        self,
        root: Path,
        *,
        plan_stem: str,
        analysis_pack_rows: str,
        extra_sections: str = "",
        plan_meta_extra: str = "",
        analysis_wave: bool = True,
    ) -> Path:
        helper = PlanLintReviewRouteDeterminismTests()
        plan_path = helper._write_fixture(
            root,
            plan_stem=plan_stem,
            target_paths=["scripts/plan_lint.py"],
            review_artifact_lines=[f"- Code review (primary): `docs/code_reviews/{plan_stem}.md`"],
            extra_sections=dedent(
                f"""\
                ## Documentation impact / provenance
                - Source docs used: `docs/playbooks/analysis_wave.md`
                - Synchronous doc/registry targets: `docs/playbooks/analysis_wave.md`
                - Post-merge canon updates: `docs/playbooks/analysis_wave.md`
                - Deferred documentation follow-ups: N/A (why=fixture)
                - Provenance refs: fixture

                ## Analysis pack
                | Field | Value |
                | --- | --- |
                {analysis_pack_rows}

                ## Promoted route artifact
                | Field | Value |
                | --- | --- |
                | `accepted_route` | `developer_wave` |
                | `promoted_artifact_ref` | `docs/plans/260613_1800_process_seed.md` |
                | `queue_admission` | `not_queueable` |
                | `runner_admission` | `frontier_only` |

                {extra_sections}
                """
            ).rstrip(),
        )
        text = dedent(plan_path.read_text(encoding="utf-8"))
        if analysis_wave:
            text = text.replace(
                '"plan_meta": {',
                '"plan_meta": {\n    "wave_family": "analysis_wave",',
                1,
            )
        if plan_meta_extra:
            text = text.replace(
                '"plan_meta": {',
                f'"plan_meta": {{\n{plan_meta_extra}',
                1,
            )
        pack_rel = f"docs/analysis_packs/{plan_stem}.md"
        if analysis_wave:
            analysis_start = text.index("## Analysis pack")
            promoted_start = text.index("## Promoted route artifact", analysis_start)
            text = (
                text[:analysis_start]
                + "## Analysis pack\n| Field | Value |\n| --- | --- |\n"
                + f"| `analysis_pack_ref` | `{pack_rel}#Analysis-pack` |\n"
                + "| `authority_boundary` | `standalone_pack_only` |\n\n"
                + text[promoted_start:]
            )

        strict = MODULE.strict_plan_meta_json(text.splitlines())
        decision: dict[str, object] = {
            "schema_version": MODULE.plan_status_oracle.MACHINE_AUTHORITY_DECISION_SCHEMA,
            "applicability": "not_applicable",
            "reason_code": "docs_or_tests_only",
        }
        if strict.state == "valid" and strict.plan_meta is not None:
            plan_meta = copy.deepcopy(dict(strict.plan_meta))
            plan_meta["machine_authority_decision"] = decision
            meta_start = text.index("```json\n", text.index("## Meta")) + len("```json\n")
            meta_end = text.index("\n```", meta_start)
            text = text[:meta_start] + json.dumps({"plan_meta": plan_meta}, ensure_ascii=False, indent=2) + text[meta_end:]
        else:
            text += "\n## Meta\n```json\n" + json.dumps(
                {"plan_meta": {"machine_authority_decision": decision}},
                ensure_ascii=False,
                indent=2,
            ) + "\n```\n"
        plan_path.write_text(text, encoding="utf-8")

        draft_path = root / f"docs/code_drafts/{plan_stem}__code_draft.md"
        targets: list[dict[str, str]] = [{"path": "scripts/plan_lint.py", "kind": "py"}]
        if analysis_wave:
            targets.append({"path": pack_rel, "kind": "doc"})
        draft_payload = {
            "code_draft_meta": {
                "plan": f"docs/plans/{plan_stem}.md",
                "cluster": "process",
                "targets": targets,
                "deleted_paths": [],
                "machine_authority_decision_ref": {
                    "applicability": "not_applicable",
                    "reason_code": "docs_or_tests_only",
                    "carrier_sha256": MODULE.plan_status_oracle.machine_authority_decision_sha256(decision),
                },
            }
        }
        draft_path.write_text(
            "# Code draft: external analysis authority fixture\n\n```json\n"
            + json.dumps(draft_payload, ensure_ascii=False, indent=2)
            + "\n```\n",
            encoding="utf-8",
        )
        if analysis_wave:
            pack = root / pack_rel
            pack.parent.mkdir(parents=True, exist_ok=True)
            pack.write_text(
                "# Analysis pack\n\n## Analysis pack\n| Field | Value |\n| --- | --- |\n"
                + analysis_pack_rows
                + "\n",
                encoding="utf-8",
            )
        return plan_path

    def _single_authority_findings(self, findings: list[object]) -> list[object]:
        return [
            finding
            for finding in findings
            if "accepted-route literal" in finding.message
            or "`## Analysis pack` must not define literal accepted-route fields" in finding.message
            or "Analysis route single-authority violation" in finding.message
            or "Analysis route single-authority warning" in finding.message
        ]

    def _requirement_slice_findings(self, findings: list[object]) -> list[object]:
        return [
            finding
            for finding in findings
            if "requirement_slices.slice_kind" in finding.message
            or "needs_analysis requirement slice" in finding.message
            or "`needs_analysis` requirement slice" in finding.message
        ]

    def _analysis_completion_findings(self, findings: list[object]) -> list[object]:
        return [
            finding
            for finding in findings
            if "Analysis pack completeness warning:" in finding.message
        ]

    def _analysis_lifecycle_findings(self, findings: list[object]) -> list[object]:
        return [
            finding
            for finding in findings
            if finding.message.startswith("Analysis route lifecycle ")
        ]

    def _developer_lifecycle_rows(self, execution_budget: str, stale_trigger: str) -> str:
        return (
            "| `scope_refs` | opened/read: `docs/playbooks/analysis_wave.md` |\n"
            "| `documentation_impact_seed` | docs impact inherited from fixture |\n"
            "| `dependent_inventory_mutable_surfaces` | mutable `scripts/plan_lint.py`; tests `scripts/test_plan_lint.py` |\n"
            "| `requirement_slices` | `slice_kind=dev_candidate`; bounded helper/docs slice |\n"
            "| `reviewability_seed` | proof: `scripts.test_plan_lint` plus plan lint |\n"
            "| `runner_handoff_seed` | frontier only |\n"
            "| `route_recommendation` | `developer_wave` because fixture has enough source-backed scope |\n"
            f"| `execution_budget` | {execution_budget} |\n"
            f"| `stale_trigger` | {stale_trigger} |"
        )

    def test_promoted_route_refs_with_refs_only_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260613_1800_process_analysis_route_refs_only",
                analysis_pack_rows=(
                    "| `route_recommendation` | `developer_wave` + bounded docs/lint refs |\n"
                    "| `promoted_route_refs` | refs: `docs/plans/260613_1800_process_seed.md#promoted-route-artifact` |"
                ),
            )

            findings = MODULE.lint_plan(plan_path)

        self.assertEqual(self._single_authority_findings(findings), [])

    def test_historical_snapshot_text_with_old_route_fields_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260613_1801_process_analysis_route_snapshot_allowed",
                analysis_pack_rows="| `promoted_route_refs` | refs: source artifact only |",
                extra_sections=dedent(
                    """\
                    ## Historical snapshot
                    - Old quote: accepted_route=developer_wave; promoted_artifact_ref=docs/plans/old.md; queue_admission=not_queueable; runner_admission=frontier_only.
                    """
                ).rstrip(),
            )

            findings = MODULE.lint_plan(plan_path)

        self.assertEqual(self._single_authority_findings(findings), [])

    def test_live_promoted_route_refs_with_duplicate_literals_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260613_1802_process_analysis_route_duplicate_literals",
                analysis_pack_rows=(
                    "| `promoted_route_refs` | accepted_route=developer_wave; "
                    "promoted_artifact_ref=docs/plans/260613_1802_process_seed.md; "
                    "queue_admission=not_queueable; runner_admission=frontier_only |"
                ),
            )

            findings = MODULE.lint_plan(plan_path)

        single_authority_findings = self._single_authority_findings(findings)
        self.assertEqual(len(single_authority_findings), 1)
        self.assertIn("analysis_pack.promoted_route_refs", single_authority_findings[0].message)

    def test_writable_plan_meta_route_fields_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260613_1803_process_analysis_route_plan_meta_duplicate",
                analysis_pack_rows="| `promoted_route_refs` | refs: source artifact only |",
                plan_meta_extra='    "accepted_route": "developer_wave",\n    "queue_admission": "queueable_now",\n',
            )

            findings = MODULE.lint_plan(plan_path)

        single_authority_findings = self._single_authority_findings(findings)
        self.assertEqual(len(single_authority_findings), 2)
        messages = "\n".join(finding.message for finding in single_authority_findings)
        self.assertIn("plan_meta.accepted_route", messages)
        self.assertIn("plan_meta.queue_admission", messages)

    def test_derived_promoted_from_plan_meta_snapshot_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260613_1804_process_analysis_route_promoted_from_allowed",
                analysis_pack_rows="| `promoted_route_refs` | refs: source artifact only |",
                plan_meta_extra=dedent(
                    """\
                        "promoted_from": {
                          "accepted_route": "developer_wave",
                          "promoted_artifact_ref": "docs/plans/260613_1804_process_seed.md",
                          "queue_admission_at_acceptance": "queueable_now",
                          "runner_admission_at_acceptance": "frontier_only",
                          "authority_note": "derived_read_only; source artifact is writable truth"
                        },
                    """
                ),
            )

            findings = MODULE.lint_plan(plan_path)

        self.assertEqual(self._single_authority_findings(findings), [])

    def test_derived_promoted_from_without_authority_note_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260613_1806_process_analysis_route_promoted_from_missing_note",
                analysis_pack_rows="| `promoted_route_refs` | refs: source artifact only |",
                plan_meta_extra=dedent(
                    """\
                        "promoted_from": {
                          "accepted_route": "developer_wave",
                          "promoted_artifact_ref": "docs/plans/260613_1806_process_seed.md",
                          "queue_admission_at_acceptance": "queueable_now",
                          "runner_admission_at_acceptance": "frontier_only"
                        },
                    """
                ),
            )

            findings = MODULE.lint_plan(plan_path)

        single_authority_findings = self._single_authority_findings(findings)
        self.assertEqual(len(single_authority_findings), 1)
        self.assertEqual(single_authority_findings[0].severity, "WARN")
        self.assertIn("plan_meta.promoted_from.authority_note", single_authority_findings[0].message)
        self.assertIn("derived_read_only; source artifact is writable truth", single_authority_findings[0].message)

    def test_non_analysis_plan_meta_route_fields_are_unaffected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260613_1805_process_non_analysis_route_plan_meta_unaffected",
                analysis_pack_rows="| `promoted_route_refs` | accepted_route=developer_wave |",
                plan_meta_extra='    "accepted_route": "developer_wave",\n',
                analysis_wave=False,
            )

            findings = MODULE.lint_plan(plan_path)

        self.assertEqual(self._single_authority_findings(findings), [])

    def test_non_analysis_promoted_from_without_authority_note_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260613_1807_process_target_promoted_from_missing_note",
                analysis_pack_rows="| `promoted_route_refs` | refs: source artifact only |",
                plan_meta_extra=dedent(
                    """\
                        "promoted_from": {
                          "accepted_route": "developer_wave",
                          "promoted_artifact_ref": "docs/plans/260613_1807_process_seed.md"
                        },
                    """
                ),
                analysis_wave=False,
            )

            findings = MODULE.lint_plan(plan_path)

        single_authority_findings = self._single_authority_findings(findings)
        self.assertEqual(len(single_authority_findings), 1)
        self.assertEqual(single_authority_findings[0].severity, "WARN")
        self.assertIn("plan_meta.promoted_from.authority_note", single_authority_findings[0].message)

    def test_template_scaffold_examples_are_not_live_route_truth(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "docs" / "plans" / "_template.md"
            path.parent.mkdir(parents=True)
            path.write_text(
                dedent(
                    """\
                    # Plan template

                    ## Analysis pack
                    | Field | Value |
                    | --- | --- |
                    | `promoted_route_refs` | accepted_route=developer_wave; queue_admission=not_queueable |
                    """
                ),
                encoding="utf-8",
            )

            findings = MODULE.validate_analysis_route_single_authority(
                path,
                MODULE.read_text(path),
                {"wave_family": "analysis_wave"},
            )

        self.assertEqual(findings, [])

    def test_requirement_slices_reject_route_enum_as_slice_kind(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260619_1808_process_invalid_slice_kind_enum",
                analysis_pack_rows=(
                    "| `requirement_slices` | "
                    "`slice=plan_bundle_modes; slice_kind=developer_wave; proof=focused helper tests` |"
                ),
            )

            findings = MODULE.lint_plan(plan_path)

        slice_findings = self._requirement_slice_findings(findings)
        self.assertEqual(len(slice_findings), 1)
        self.assertEqual(slice_findings[0].severity, "ERROR")
        self.assertIn("developer_wave", slice_findings[0].message)
        self.assertIn("dev_candidate", slice_findings[0].message)

    def test_requirement_slices_allow_route_words_outside_slice_kind(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260619_1809_process_route_words_outside_slice_kind",
                analysis_pack_rows=(
                    "| `route_recommendation` | `developer_wave` advisory only |\n"
                    "| `requirement_slices` | "
                    "`slice=plan_bundle_modes; slice_kind=dev_candidate; outcome=developer_wave seed after review; "
                    "human_gate and reject remain rejected alternatives` |"
                ),
            )

            findings = MODULE.lint_plan(plan_path)

        self.assertEqual(self._requirement_slice_findings(findings), [])

    def test_needs_analysis_slice_requires_key_unknowns_and_trigger(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260619_1810_process_needs_analysis_incomplete_slice",
                analysis_pack_rows=(
                    "| `requirement_slices` | "
                    "`slice_kind=needs_analysis; analysis_subject=target outcome policy; "
                    "desired_outcome=decide exact target outcome ownership` |"
                ),
            )

            findings = MODULE.lint_plan(plan_path)

        slice_findings = self._requirement_slice_findings(findings)
        self.assertEqual(len(slice_findings), 1)
        self.assertEqual(slice_findings[0].severity, "ERROR")
        self.assertIn("key_unknowns", slice_findings[0].message)
        self.assertIn("trigger_for_promotion", slice_findings[0].message)

    def test_needs_analysis_slice_with_package_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260619_1811_process_needs_analysis_complete_slice",
                analysis_pack_rows=(
                    "| `requirement_slices` | "
                    "`slice_kind=needs_analysis; analysis_subject=target outcome policy; "
                    "desired_outcome=decide exact target outcome ownership; "
                    "key_unknowns=where target-local outcome proof lives; "
                    "trigger_for_promotion=target owner accepts exact carrier; "
                    "parent_consumer_decision=not queueable until accepted route returns; "
                    "expected_analysis_review_lane=docs/process review` |"
                ),
            )

            findings = MODULE.lint_plan(plan_path)

        self.assertEqual(self._requirement_slice_findings(findings), [])

    def test_needs_analysis_slice_rejects_queueable_dev_child_admission(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260619_1812_process_needs_analysis_queueable_slice",
                analysis_pack_rows=(
                    "| `requirement_slices` | "
                    "`slice_kind=needs_analysis; analysis_subject=target outcome policy; "
                    "key_unknowns=where target-local outcome proof lives; "
                    "trigger_for_promotion=target owner accepts exact carrier; "
                    "queue_admission=queueable_now` |"
                ),
            )

            findings = MODULE.lint_plan(plan_path)

        slice_findings = self._requirement_slice_findings(findings)
        self.assertEqual(len(slice_findings), 1)
        self.assertEqual(slice_findings[0].severity, "ERROR")
        self.assertIn("queueable_now", slice_findings[0].message)

    def test_analysis_pack_developer_wave_missing_required_fields_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260619_0027_process_analysis_pack_missing_developer_fields",
                analysis_pack_rows=(
                    "| `scope_refs` | opened/read: `docs/playbooks/analysis_wave.md` |\n"
                    "| `route_recommendation` | `developer_wave` because fixture has enough scope |"
                ),
            )

            findings = MODULE.lint_plan(plan_path)

        completion_findings = self._analysis_completion_findings(findings)
        self.assertTrue(
            any("missing route-required" in finding.message and "`reviewability_seed`" in finding.message for finding in completion_findings),
            [finding.message for finding in completion_findings],
        )
        self.assertTrue(all(finding.severity == "WARN" for finding in completion_findings), completion_findings)

    def test_analysis_pack_placeholder_required_field_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260619_0028_process_analysis_pack_placeholder_field",
                analysis_pack_rows=(
                    "| `scope_refs` | opened/read: `docs/playbooks/analysis_wave.md` |\n"
                    "| `documentation_impact_seed` | docs impact inherited from fixture |\n"
                    "| `dependent_inventory_mutable_surfaces` | `scripts/plan_lint.py` |\n"
                    "| `requirement_slices` | TBD |\n"
                    "| `reviewability_seed` | proof: `scripts.test_plan_lint` |\n"
                    "| `runner_handoff_seed` | frontier only |\n"
                    "| `route_recommendation` | `developer_wave` because fixture has enough scope |"
                ),
            )

            findings = MODULE.lint_plan(plan_path)

        completion_findings = self._analysis_completion_findings(findings)
        self.assertTrue(
            any("`requirement_slices`" in finding.message for finding in completion_findings),
            [finding.message for finding in completion_findings],
        )

    def test_analysis_pack_retrieval_only_scope_refs_do_not_satisfy_source_floor(self) -> None:
        self.assertFalse(MODULE.scope_refs_has_inspected_source("retrieval hits: `docs/README.md`"))

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260619_0029_process_analysis_pack_retrieval_only_sources",
                analysis_pack_rows=(
                    "| `scope_refs` | retrieval hits: `docs/README.md` |\n"
                    "| `documentation_impact_seed` | docs impact inherited from fixture |\n"
                    "| `dependent_inventory_mutable_surfaces` | `scripts/plan_lint.py` |\n"
                    "| `requirement_slices` | `slice_kind=dev_candidate` |\n"
                    "| `reviewability_seed` | proof: `scripts.test_plan_lint` |\n"
                    "| `runner_handoff_seed` | frontier only |\n"
                    "| `route_recommendation` | `developer_wave` because fixture has enough scope |"
                ),
            )

            findings = MODULE.lint_plan(plan_path)

        completion_findings = self._analysis_completion_findings(findings)
        self.assertTrue(
            any("retrieval hits alone do not satisfy the source floor" in finding.message for finding in completion_findings),
            [finding.message for finding in completion_findings],
        )

    def test_analysis_pack_bounded_no_relevant_hits_satisfies_source_floor(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260619_0030_process_analysis_pack_bounded_no_hits",
                analysis_pack_rows=(
                    "| `scope_refs` | NO RELEVANT HITS query=fixture lane=canon reason=no matching docs |\n"
                    "| `options_considered` | defer now; reject duplicate |\n"
                    "| `recommendation` | defer with explicit trigger |\n"
                    "| `route_recommendation` | `defer` because fixture has no inspected source matches |"
                ),
            )

            findings = MODULE.lint_plan(plan_path)

        completion_findings = self._analysis_completion_findings(findings)
        self.assertEqual(completion_findings, [])

    def test_analysis_pack_unbounded_no_relevant_hits_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260619_0032_process_analysis_pack_unbounded_no_hits",
                analysis_pack_rows=(
                    "| `scope_refs` | NO RELEVANT HITS query=fixture |\n"
                    "| `options_considered` | defer now; reject duplicate |\n"
                    "| `recommendation` | defer with explicit trigger |\n"
                    "| `route_recommendation` | `defer` because fixture has no inspected source matches |"
                ),
            )

            findings = MODULE.lint_plan(plan_path)

        completion_findings = self._analysis_completion_findings(findings)
        self.assertTrue(
            any("`NO RELEVANT HITS` must be bounded" in finding.message for finding in completion_findings),
            [finding.message for finding in completion_findings],
        )

    def test_analysis_pack_green_developer_wave_has_no_completion_warnings(self) -> None:
        self.assertTrue(MODULE.scope_refs_has_inspected_source("opened source refs: `docs/playbooks/analysis_wave.md`"))

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260619_0031_process_analysis_pack_green_developer",
                analysis_pack_rows=(
                    "| `scope_refs` | opened/read: `docs/playbooks/analysis_wave.md`, `scripts/plan_lint.py` |\n"
                    "| `documentation_impact_seed` | docs impact inherited from fixture |\n"
                    "| `dependent_inventory_mutable_surfaces` | mutable `scripts/plan_lint.py`; tests `scripts/test_plan_lint.py` |\n"
                    "| `requirement_slices` | `slice_kind=dev_candidate`; bounded helper/docs slice |\n"
                    "| `reviewability_seed` | proof: `scripts.test_plan_lint` plus plan lint |\n"
                    "| `runner_handoff_seed` | frontier only |\n"
                    "| `route_recommendation` | `developer_wave` because fixture has enough source-backed scope |"
                ),
            )

            findings = MODULE.lint_plan(plan_path)

        completion_findings = self._analysis_completion_findings(findings)
        self.assertEqual(completion_findings, [])

    def test_analysis_route_lifecycle_missing_budget_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260619_0033_process_analysis_lifecycle_missing_budget",
                analysis_pack_rows=self._developer_lifecycle_rows(
                    execution_budget="N/A (why=fixture missing budget)",
                    stale_trigger="source_subject_baseline=budget guard; current_source_subject=budget guard",
                ),
            )

            findings = MODULE.lint_plan(plan_path)

        lifecycle_findings = self._analysis_lifecycle_findings(findings)
        self.assertTrue(any(finding.severity == "WARN" and "missing lifecycle budget key" in finding.message for finding in lifecycle_findings))

    def test_analysis_route_lifecycle_malformed_budget_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260619_0034_process_analysis_lifecycle_malformed_budget",
                analysis_pack_rows=self._developer_lifecycle_rows(
                    execution_budget=(
                        "budget_status=active; source_ref_floor=1; route_iteration_limit=1; "
                        "needs_analysis_depth_cap=two; current_needs_analysis_depth=one; "
                        "stop_owner=Architect; exhaustion_action=architect_recheck"
                    ),
                    stale_trigger="source_subject_baseline=budget guard; current_source_subject=budget guard",
                ),
            )

            findings = MODULE.lint_plan(plan_path)

        lifecycle_findings = self._analysis_lifecycle_findings(findings)
        self.assertTrue(any(finding.severity == "WARN" and "depth values must be numeric" in finding.message for finding in lifecycle_findings))

    def test_analysis_route_lifecycle_ambiguous_source_baseline_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260619_0034_process_analysis_lifecycle_ambiguous_source",
                analysis_pack_rows=self._developer_lifecycle_rows(
                    execution_budget=(
                        "budget_status=active; source_ref_floor=1; route_iteration_limit=1; "
                        "needs_analysis_depth_cap=2; current_needs_analysis_depth=1; "
                        "stop_owner=Architect; exhaustion_action=architect_recheck"
                    ),
                    stale_trigger="source_subject_baseline=budget guard",
                ),
            )

            findings = MODULE.lint_plan(plan_path)

        lifecycle_findings = self._analysis_lifecycle_findings(findings)
        self.assertTrue(any(finding.severity == "WARN" and "source subject/ref baseline" in finding.message for finding in lifecycle_findings))

    def test_analysis_route_lifecycle_exhausted_budget_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260619_0034_process_analysis_lifecycle_exhausted",
                analysis_pack_rows=self._developer_lifecycle_rows(
                    execution_budget=(
                        "budget_status=exhausted; source_ref_floor=1; route_iteration_limit=1; "
                        "needs_analysis_depth_cap=2; current_needs_analysis_depth=1; "
                        "stop_owner=Architect; exhaustion_action=architect_recheck"
                    ),
                    stale_trigger="source_subject_baseline=budget guard; current_source_subject=budget guard",
                ),
            )

            findings = MODULE.lint_plan(plan_path)

        lifecycle_findings = self._analysis_lifecycle_findings(findings)
        self.assertTrue(any(finding.severity == "ERROR" and "budget_status=exhausted" in finding.message for finding in lifecycle_findings))

    def test_analysis_route_lifecycle_depth_overflow_requires_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260619_0035_process_analysis_lifecycle_depth_overflow",
                analysis_pack_rows=self._developer_lifecycle_rows(
                    execution_budget=(
                        "budget_status=active; source_ref_floor=1; route_iteration_limit=1; "
                        "needs_analysis_depth_cap=2; current_needs_analysis_depth=3; "
                        "stop_owner=Architect; exhaustion_action=architect_recheck"
                    ),
                    stale_trigger="source_subject_baseline=budget guard; current_source_subject=budget guard",
                ),
            )

            findings = MODULE.lint_plan(plan_path)

        lifecycle_findings = self._analysis_lifecycle_findings(findings)
        self.assertTrue(any(finding.severity == "ERROR" and "exceeds needs_analysis_depth_cap" in finding.message for finding in lifecycle_findings))

    def test_analysis_route_lifecycle_override_allows_depth_overflow(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260619_0036_process_analysis_lifecycle_override",
                analysis_pack_rows=self._developer_lifecycle_rows(
                    execution_budget=(
                        "budget_status=active; source_ref_floor=1; route_iteration_limit=1; "
                        "needs_analysis_depth_cap=2; current_needs_analysis_depth=3; "
                        "stop_owner=Architect; exhaustion_action=architect_recheck; "
                        "override_ref=docs/plans/260619_0036_override.md#Architect-QA"
                    ),
                    stale_trigger="source_subject_baseline=budget guard; current_source_subject=budget guard",
                ),
            )

            findings = MODULE.lint_plan(plan_path)

        self.assertEqual(self._analysis_lifecycle_findings(findings), [])

    def test_analysis_route_lifecycle_stale_source_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260619_0037_process_analysis_lifecycle_stale",
                analysis_pack_rows=self._developer_lifecycle_rows(
                    execution_budget=(
                        "budget_status=active; source_ref_floor=1; route_iteration_limit=1; "
                        "needs_analysis_depth_cap=2; current_needs_analysis_depth=1; "
                        "stop_owner=Architect; exhaustion_action=architect_recheck"
                    ),
                    stale_trigger=(
                        "source_subject_baseline=budget guard; current_source_subject=budget guard v2; "
                        "change_ref=docs/plans/260619_0037_changed.md; action=architect_recheck"
                    ),
                ),
            )

            findings = MODULE.lint_plan(plan_path)

        lifecycle_findings = self._analysis_lifecycle_findings(findings)
        self.assertTrue(any(finding.severity == "ERROR" and "Architect" in finding.message for finding in lifecycle_findings))

    def test_analysis_route_lifecycle_comma_source_refs_change_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260619_0038_process_analysis_lifecycle_comma_refs_stale",
                analysis_pack_rows=self._developer_lifecycle_rows(
                    execution_budget=(
                        "budget_status=active; source_ref_floor=1; route_iteration_limit=1; "
                        "needs_analysis_depth_cap=2; current_needs_analysis_depth=1; "
                        "stop_owner=Architect; exhaustion_action=architect_recheck"
                    ),
                    stale_trigger=(
                        "source_refs_baseline=docs/a.md, docs/b.md; "
                        "current_source_refs=docs/a.md, docs/c.md"
                    ),
                ),
            )

            findings = MODULE.lint_plan(plan_path)

        lifecycle_findings = self._analysis_lifecycle_findings(findings)
        self.assertTrue(any(finding.severity == "ERROR" and "source refs changed" in finding.message for finding in lifecycle_findings))

    def test_analysis_route_lifecycle_green_has_no_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260619_0038_process_analysis_lifecycle_green",
                analysis_pack_rows=self._developer_lifecycle_rows(
                    execution_budget=(
                        "budget_status=active; source_ref_floor=1; route_iteration_limit=1; "
                        "needs_analysis_depth_cap=2; current_needs_analysis_depth=1; "
                        "stop_owner=Architect; exhaustion_action=architect_recheck"
                    ),
                    stale_trigger=(
                        "source_subject_baseline=budget guard; current_source_subject=budget guard; "
                        "source_refs_baseline=docs/playbooks/analysis_wave.md; current_source_refs=docs/playbooks/analysis_wave.md"
                    ),
                ),
            )

            findings = MODULE.lint_plan(plan_path)

        self.assertEqual(self._analysis_lifecycle_findings(findings), [])


class PlanLintPlanningContourSchemaHardeningTests(unittest.TestCase):
    def setUp(self) -> None:
        MODULE.load_and_apply_plan_vocab(MODULE.PLAN_VOCAB_PATH)

    def _base_meta(self, **overrides: object) -> dict[str, object]:
        meta: dict[str, object] = {
            "cluster": "process",
            "tags": [],
            "wave_family": None,
            "phase_overlay": None,
            "phase_state": None,
            "parent": None,
            "next_plans": [],
            "depends_on": [],
            "followups_out": [],
            "canon_updates": [],
        }
        meta.update(overrides)
        return meta

    def _valid_promoted_from(self, **overrides: object) -> dict[str, object]:
        promoted_from: dict[str, object] = {
            "authority_note": MODULE.ACCEPTED_ROUTE_DERIVED_AUTHORITY_NOTE,
            "source_plan": "docs/plans/260614_1435_process_schema_source_valid.md",
            "source_route_ref": "docs/plans/260614_1435_process_schema_source_valid.md#promoted-route-artifact",
            "accepted_route": "decomposition_wave",
            "promoted_artifact_kind": "decomposition_umbrella",
            "promoted_artifact_ref": "docs/plans/260614_1436_process_schema_target_valid.md",
            "queue_admission_at_acceptance": "queueable_now",
            "runner_admission_at_acceptance": "frontier_only",
        }
        promoted_from.update(overrides)
        return promoted_from

    def _valid_queue_activation(self, **overrides: object) -> dict[str, object]:
        queue_activation: dict[str, object] = {
            "state": "architect_approved",
            "source_ref": "docs/plans/260614_1435_process_parent.md#execution-queue",
            "reason": "fixture-approved planning-contour admission",
        }
        queue_activation.update(overrides)
        return queue_activation

    def _valid_scope_expansion(self, **overrides: object) -> dict[str, object]:
        scope_expansion: dict[str, object] = {
            "state": "reroute_required",
            "target_contour": "decomposition_wave",
            "source_ref": "docs/plans/260614_1435_process_schema_fixture.md#evidence",
            "reason": "fixture child graph drift",
        }
        scope_expansion.update(overrides)
        return scope_expansion

    def _write_fixture(
        self,
        root: Path,
        *,
        plan_stem: str,
        plan_meta: dict[str, object],
        status: str = "Architect draft",
        extra_sections: str = "",
        review_artifact_payloads: dict[str, str] | None = None,
    ) -> Path:
        (root / ".git").mkdir(exist_ok=True)
        ensure_fixture_git(root)
        plan_path = root / "docs" / "plans" / f"{plan_stem}.md"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        (root / "docs" / "code_reviews").mkdir(parents=True, exist_ok=True)
        plan_path.write_text(
            dedent(
                f"""\
                # Plan: planning contour schema fixture

                **Date:** 2026-06-14 14:35 MSK
                **Stage:** Stage 1
                **Priority:** P1
                **Plan type:** dev
                **Status:** {status}
                **Schema version:** plan.v1

                **Context links (source of truth):**
                - Fixture: `scripts/test_plan_lint.py`

                ## Meta (machine-readable JSON; required for new plans)
                ```json
                {json.dumps({"plan_meta": plan_meta}, ensure_ascii=False, indent=2)}
                ```

                ## Documentation impact / provenance
                - Source docs used: fixture.
                - Synchronous doc/registry targets: `docs/plans/README.md`.
                - Post-merge canon updates: `N/A (why=fixture)`.
                - Deferred documentation follow-ups: `N/A (why=fixture)`.
                - Provenance refs: fixture.

                ## Decisions (final)
                - Fixture.

                ## Scope
                - Fixture.

                ## Out of scope
                - Product/runtime behavior.

                ## Rollout packet handoff
                - Role: `N/A (why=fixture)`
                - Packet path: `N/A`
                - Target repo: `N/A`
                - Suggested target plan slug: `N/A`
                - Queue after import: `N/A`

                ## Close-out routing
                - Roadmap/queue sync: `N/A (fixture)`
                - Follow-up sync: `none`
                - Next bounded slice: `none`
                - Terminal outcome: yes

                ## Mechanism coverage
                - Fixture route/linkage carrier validation.

                {extra_sections}

                ## Changes (by area)
                - Tooling/scripts: `scripts/plan_lint.py`

                ## Tests
                - `python3 scripts/test_plan_lint.py`

                ## Commands
                - `python3 scripts/test_plan_lint.py`

                ## Verification rerun / exec handoff
                - Mode: fresh-exec
                - Context source: fixture.
                - Prompt: fixture.
                - Command: `python3 scripts/test_plan_lint.py`
                - Expected artifact: deterministic lint finding.
                """
            ),
            encoding="utf-8",
        )

        for rel_path, payload in (review_artifact_payloads or {}).items():
            artifact_path = root / rel_path
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            artifact_path.write_text(payload, encoding="utf-8")

        return plan_path

    def _schema_findings(self, findings: list[object]) -> list[object]:
        return [
            finding
            for finding in findings
            if finding.message.startswith(MODULE.PLANNING_CONTOUR_SCHEMA_ERROR_PREFIX)
            or finding.message.startswith(MODULE.PLANNING_CONTOUR_SCHEMA_WARNING_PREFIX)
        ]

    def _source_route_artifact(self, *, accepted_route: str = "decomposition_wave", rows: str = "") -> str:
        default_rows = dedent(
            f"""\
            | `source_analysis_plan` | `docs/plans/260614_1435_process_schema_source_valid.md` |
            | `source_analysis_pack_ref` | `docs/plans/260614_1435_process_schema_source_valid.md#Analysis-pack` |
            | `accepted_route` | `{accepted_route}` |
            | `promoted_artifact_kind` | `decomposition_umbrella` |
            | `promoted_artifact_ref` | `docs/plans/260614_1436_process_schema_target_valid.md` |
            | `queue_admission` | `queueable_now` |
            | `runner_admission` | `frontier_only` |
            """
        ).rstrip()
        return dedent(
            f"""\
            ## Analysis pack
            | Field | Value |
            | --- | --- |
            | `route_recommendation` | `{accepted_route}` |
            | `promoted_route_refs` | refs only |

            ## Promoted route artifact
            | Field | Value |
            | --- | --- |
            {rows or default_rows}
            """
        ).rstrip()

    def test_valid_source_and_target_carriers_have_no_schema_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_path = self._write_fixture(
                root,
                plan_stem="260614_1435_process_schema_source_valid",
                plan_meta=self._base_meta(wave_family="analysis_wave"),
                extra_sections=self._source_route_artifact(),
            )
            target_path = self._write_fixture(
                root,
                plan_stem="260614_1436_process_schema_target_valid",
                status="Architect initial draft",
                plan_meta=self._base_meta(
                    phase_overlay="decomposition_wave",
                    phase_state="parked",
                    promoted_from=self._valid_promoted_from(),
                    queue_activation=self._valid_queue_activation(),
                ),
            )

            source_findings = self._schema_findings(MODULE.lint_plan(source_path))
            target_findings = self._schema_findings(MODULE.lint_plan(target_path))

        self.assertEqual(source_findings, [])
        self.assertEqual(target_findings, [])

    def test_fixture_backed_developer_source_route_requires_promoted_artifact_file(self) -> None:
        rows = dedent(
            """\
            | `source_analysis_plan` | `docs/plans/260614_1435_process_schema_source_valid.md` |
            | `source_analysis_pack_ref` | `docs/plans/260614_1435_process_schema_source_valid.md#Analysis-pack` |
            | `accepted_route` | `developer_wave` |
            | `promoted_artifact_kind` | `seed_dev_plan` |
            | `promoted_artifact_ref` | `docs/plans/260614_1436_process_missing_seed_dev_plan.md` |
            | `queue_admission` | `queueable_now` |
            | `runner_admission` | `frontier_only` |
            """
        ).rstrip()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_path = self._write_fixture(
                root,
                plan_stem="260614_1435_process_schema_source_valid",
                plan_meta=self._base_meta(wave_family="analysis_wave"),
                extra_sections=self._source_route_artifact(accepted_route="developer_wave", rows=rows),
            )

            findings = self._schema_findings(MODULE.lint_plan(source_path))

        self.assertTrue(any(finding.severity == "ERROR" for finding in findings), findings)
        messages = "\n".join(finding.message for finding in findings)
        self.assertIn("promoted_artifact_ref", messages)
        self.assertIn("does not exist", messages)

    def test_direct_owner_decomposition_target_skips_source_route_parity(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target_path = self._write_fixture(
                root,
                plan_stem="260614_1436_process_direct_owner_decomposition_target",
                status="Architect initial draft",
                plan_meta=self._base_meta(
                    phase_overlay="decomposition_wave",
                    phase_state="parked",
                    promoted_from=self._valid_promoted_from(
                        source_plan="N/A (why=direct Owner/external reviewer intake)",
                        source_route_ref="Owner message on 2026-06-19",
                        promoted_artifact_ref="docs/plans/260614_1436_process_direct_owner_decomposition_target.md",
                    ),
                    queue_activation=self._valid_queue_activation(),
                ),
            )

            target_findings = self._schema_findings(MODULE.lint_plan(target_path))

        self.assertEqual(target_findings, [])

    def test_promoted_from_absent_null_non_object_missing_required_and_invalid_enum_fail(self) -> None:
        cases: list[tuple[str, dict[str, object]]] = [
            ("absent", {}),
            ("null", {"promoted_from": None}),
            ("non_object", {"promoted_from": "docs/plans/source.md"}),
            ("missing_required", {"promoted_from": {"authority_note": MODULE.ACCEPTED_ROUTE_DERIVED_AUTHORITY_NOTE}}),
            ("invalid_enum", {"promoted_from": self._valid_promoted_from(accepted_route="qa_wave")}),
        ]
        for label, extra_meta in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                plan_path = self._write_fixture(
                    root,
                    plan_stem=f"260614_1437_process_schema_promoted_from_{label}",
                    plan_meta=self._base_meta(
                        phase_overlay="decomposition_wave",
                        phase_state="parked",
                        queue_activation=self._valid_queue_activation(),
                        **extra_meta,
                    ),
                )

                findings = self._schema_findings(MODULE.lint_plan(plan_path))

            self.assertTrue(any(finding.severity == "ERROR" for finding in findings), findings)
            self.assertTrue(any("plan_meta.promoted_from" in finding.message for finding in findings), findings)

    def test_missing_source_route_warns_and_fixture_backed_malformed_route_fails(self) -> None:
        rows = dedent(
            """\
            | `accepted_route` | `decomposition_wave` |
            | `promoted_artifact_kind` | `decomposition_umbrella` |
            | `promoted_artifact_ref` | `docs/plans/260614_1435_process_target_decomposition.md` |
            | `queue_admission` | `queueable_now` |
            """
        ).rstrip()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            missing_path = self._write_fixture(
                root,
                plan_stem="260614_1437_process_schema_source_route_missing",
                plan_meta=self._base_meta(wave_family="analysis_wave"),
            )
            malformed_path = self._write_fixture(
                root,
                plan_stem="260614_1437_process_schema_source_route_malformed",
                plan_meta=self._base_meta(wave_family="analysis_wave"),
                extra_sections=self._source_route_artifact(rows=rows),
            )

            missing_findings = self._schema_findings(MODULE.lint_plan(missing_path))
            malformed_findings = self._schema_findings(MODULE.lint_plan(malformed_path))

        self.assertEqual({finding.severity for finding in missing_findings}, {"WARN"})
        self.assertTrue(any("Promoted route artifact" in finding.message for finding in missing_findings), missing_findings)
        self.assertTrue(any(finding.severity == "ERROR" for finding in malformed_findings), malformed_findings)
        self.assertTrue(any("runner_admission" in finding.message for finding in malformed_findings), malformed_findings)

    def test_fixture_backed_source_route_requires_analysis_source_refs(self) -> None:
        rows = dedent(
            """\
            | `accepted_route` | `decomposition_wave` |
            | `promoted_artifact_kind` | `decomposition_umbrella` |
            | `promoted_artifact_ref` | `docs/plans/260614_1436_process_schema_target_valid.md` |
            | `queue_admission` | `queueable_now` |
            | `runner_admission` | `frontier_only` |
            """
        ).rstrip()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260614_1443_process_schema_source_route_missing_analysis_refs",
                plan_meta=self._base_meta(wave_family="analysis_wave"),
                extra_sections=self._source_route_artifact(rows=rows),
            )

            findings = self._schema_findings(MODULE.lint_plan(plan_path))

        self.assertTrue(any(finding.severity == "ERROR" for finding in findings), findings)
        messages = "\n".join(finding.message for finding in findings)
        self.assertIn("source_analysis_plan", messages)
        self.assertIn("source_analysis_pack_ref", messages)

    def test_promoted_from_source_route_provenance_failures(self) -> None:
        cases: list[tuple[str, str | None, dict[str, object], str]] = [
            (
                "missing_source_file",
                None,
                self._valid_promoted_from(source_plan="docs/plans/missing_source.md", source_route_ref="docs/plans/missing_source.md#promoted-route-artifact"),
                "does not exist",
            ),
            (
                "non_analysis_source",
                self._source_route_artifact(),
                self._valid_promoted_from(),
                "must be an `analysis_wave` plan",
            ),
            (
                "missing_route_artifact",
                "",
                self._valid_promoted_from(),
                "has no `## Promoted route artifact`",
            ),
            (
                "mismatched_target_ref",
                self._source_route_artifact(
                    rows=dedent(
                        """\
                        | `source_analysis_plan` | `docs/plans/260614_1435_process_schema_source_valid.md` |
                        | `source_analysis_pack_ref` | `docs/plans/260614_1435_process_schema_source_valid.md#Analysis-pack` |
                        | `accepted_route` | `decomposition_wave` |
                        | `promoted_artifact_kind` | `decomposition_umbrella` |
                        | `promoted_artifact_ref` | `docs/plans/260614_9999_other_target.md` |
                        | `queue_admission` | `queueable_now` |
                        | `runner_admission` | `frontier_only` |
                        """
                    ).rstrip()
                ),
                self._valid_promoted_from(),
                "source `promoted_artifact_ref` must equal the current target plan path",
            ),
            (
                "mismatched_admission",
                self._source_route_artifact(
                    rows=dedent(
                        """\
                        | `source_analysis_plan` | `docs/plans/260614_1435_process_schema_source_valid.md` |
                        | `source_analysis_pack_ref` | `docs/plans/260614_1435_process_schema_source_valid.md#Analysis-pack` |
                        | `accepted_route` | `decomposition_wave` |
                        | `promoted_artifact_kind` | `decomposition_umbrella` |
                        | `promoted_artifact_ref` | `docs/plans/260614_1436_process_schema_target_valid.md` |
                        | `queue_admission` | `needs_owner` |
                        | `runner_admission` | `frontier_only` |
                        """
                    ).rstrip()
                ),
                self._valid_promoted_from(),
                "source `queue_admission` must match target `queue_admission_at_acceptance`",
            ),
        ]
        for label, source_extra_sections, promoted_from, expected_message in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                if source_extra_sections is not None:
                    self._write_fixture(
                        root,
                        plan_stem="260614_1435_process_schema_source_valid",
                        plan_meta=self._base_meta(wave_family=None if label == "non_analysis_source" else "analysis_wave"),
                        extra_sections=source_extra_sections,
                    )
                target_path = self._write_fixture(
                    root,
                    plan_stem="260614_1436_process_schema_target_valid",
                    status="Architect initial draft",
                    plan_meta=self._base_meta(
                        phase_overlay="decomposition_wave",
                        phase_state="parked",
                        promoted_from=promoted_from,
                        queue_activation=self._valid_queue_activation(),
                    ),
                )

                findings = self._schema_findings(MODULE.lint_plan(target_path))

            self.assertTrue(any(finding.severity == "ERROR" for finding in findings), findings)
            self.assertTrue(any(expected_message in finding.message for finding in findings), findings)

    def test_queue_activation_architect_initial_draft_rejects_missing_or_malformed_object(self) -> None:
        cases: list[tuple[str, dict[str, object]]] = [
            ("absent", {}),
            ("null", {"queue_activation": None}),
            ("non_object", {"queue_activation": "owner_approved"}),
            ("missing_required", {"queue_activation": {"state": "owner_approved"}}),
            ("invalid_enum", {"queue_activation": self._valid_queue_activation(state="qa_approved")}),
        ]
        for label, extra_meta in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                plan_path = self._write_fixture(
                    root,
                    plan_stem=f"260614_1438_process_schema_queue_activation_{label}",
                    status="Architect initial draft",
                    plan_meta=self._base_meta(**extra_meta),
                )

                findings = self._schema_findings(MODULE.lint_plan(plan_path))

            self.assertTrue(any(finding.severity == "ERROR" for finding in findings), findings)
            self.assertTrue(any("plan_meta.queue_activation" in finding.message for finding in findings), findings)

    def test_queue_activation_architect_initial_draft_accepts_approved_or_intentional_na_object(self) -> None:
        for state in ("owner_approved", "architect_approved", "n/a"):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                plan_path = self._write_fixture(
                    root,
                    plan_stem=f"260614_1439_process_schema_queue_activation_{state}",
                    status="Architect initial draft",
                    plan_meta=self._base_meta(queue_activation=self._valid_queue_activation(state=state)),
                )

                findings = self._schema_findings(MODULE.lint_plan(plan_path))

            self.assertFalse(
                any(
                    finding.severity == "ERROR" and "plan_meta.queue_activation" in finding.message
                    for finding in findings
                ),
                findings,
            )

    def test_queue_activation_after_initial_draft_rejects_pending_or_malformed_carrier(self) -> None:
        cases: list[tuple[str, dict[str, object]]] = [
            ("not_requested", {"queue_activation": self._valid_queue_activation(state="not_requested")}),
            ("null", {"queue_activation": None}),
            ("non_object", {"queue_activation": "owner_approved"}),
            ("missing_required", {"queue_activation": {"state": "owner_approved"}}),
            ("invalid_enum", {"queue_activation": self._valid_queue_activation(state="qa_approved")}),
        ]
        for label, extra_meta in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                plan_path = self._write_fixture(
                    root,
                    plan_stem=f"260614_1440_process_schema_queue_activation_draft_{label}",
                    status="Architect draft",
                    plan_meta=self._base_meta(**extra_meta),
                )

                findings = self._schema_findings(MODULE.lint_plan(plan_path))

            self.assertTrue(any(finding.severity == "ERROR" for finding in findings), findings)
            self.assertTrue(any("plan_meta.queue_activation" in finding.message for finding in findings), findings)

    def test_queue_activation_approved_child_queue_requires_next_plans_carrier(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260614_1441_process_schema_queue_activation_missing_next_plans",
                status="Ready for Planner",
                plan_meta=self._base_meta(queue_activation=self._valid_queue_activation()),
                extra_sections=dedent(
                    """\
                    ## Execution queue
                    - Resume parent: `owner-restamp-required`
                    - Plan: `docs/plans/260614_1441_process_child.md`
                    """
                ).rstrip(),
            )

            findings = self._schema_findings(MODULE.lint_plan(plan_path))

        self.assertTrue(any(finding.severity == "ERROR" for finding in findings), findings)
        self.assertTrue(any("plan_meta.next_plans" in finding.message for finding in findings), findings)

    def test_queue_activation_approved_na_execution_queue_does_not_require_next_plans_carrier(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260614_1441_process_schema_queue_activation_na_execution_queue",
                status="Ready for Planner",
                plan_meta=self._base_meta(queue_activation=self._valid_queue_activation()),
                extra_sections=dedent(
                    """\
                    ## Execution queue
                    - Resume parent: `none`
                    - Plan: `N/A (why=no promoted child queue)`
                    """
                ).rstrip(),
            )

            findings = self._schema_findings(MODULE.lint_plan(plan_path))

        self.assertFalse(any("plan_meta.next_plans" in finding.message for finding in findings), findings)

    def test_scope_expansion_null_non_object_missing_required_and_invalid_state_fail(self) -> None:
        cases: list[tuple[str, object]] = [
            ("null", None),
            ("non_object", "reroute_required"),
            ("missing_required", {"state": "reroute_required"}),
            ("invalid_state", self._valid_scope_expansion(state="expanded")),
        ]
        for label, scope_expansion in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                plan_path = self._write_fixture(
                    root,
                    plan_stem=f"260614_1439_process_schema_scope_expansion_{label}",
                    plan_meta=self._base_meta(scope_expansion=scope_expansion),
                )

                findings = self._schema_findings(MODULE.lint_plan(plan_path))

            self.assertTrue(any(finding.severity == "ERROR" for finding in findings), findings)
            self.assertTrue(any("plan_meta.scope_expansion" in finding.message for finding in findings), findings)

    def test_enum_values_with_valid_prefix_and_suffix_fail_exact_validation(self) -> None:
        rows = dedent(
            """\
            | `accepted_route` | `decomposition_wave extra prose` |
            | `promoted_artifact_kind` | `decomposition_umbrella` |
            | `promoted_artifact_ref` | `docs/plans/260614_1435_process_target_decomposition.md` |
            | `queue_admission` | `queueable_now` |
            | `runner_admission` | `frontier_only` |
            """
        ).rstrip()
        cases: list[tuple[str, dict[str, object], str, str, str]] = [
            (
                "promoted_from",
                self._base_meta(
                    phase_overlay="decomposition_wave",
                    phase_state="parked",
                    promoted_from=self._valid_promoted_from(accepted_route="decomposition_wave extra prose"),
                    queue_activation=self._valid_queue_activation(),
                ),
                "Architect draft",
                "",
                "plan_meta.promoted_from",
            ),
            (
                "queue_activation",
                self._base_meta(queue_activation=self._valid_queue_activation(state="owner_approved because owner said so")),
                "Architect initial draft",
                "",
                "plan_meta.queue_activation",
            ),
            (
                "scope_expansion",
                self._base_meta(scope_expansion=self._valid_scope_expansion(state="reroute_required after review")),
                "Architect draft",
                "",
                "plan_meta.scope_expansion",
            ),
            (
                "source_route",
                self._base_meta(wave_family="analysis_wave"),
                "Architect draft",
                self._source_route_artifact(rows=rows),
                "Promoted route artifact",
            ),
        ]
        for label, plan_meta, status, extra_sections, expected_message in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                plan_path = self._write_fixture(
                    root,
                    plan_stem=f"260614_1442_process_schema_exact_enum_{label}",
                    plan_meta=plan_meta,
                    status=status,
                    extra_sections=extra_sections,
                )

                findings = self._schema_findings(MODULE.lint_plan(plan_path))

            self.assertTrue(any(finding.severity == "ERROR" for finding in findings), findings)
            self.assertTrue(any(expected_message in finding.message for finding in findings), findings)

    def test_non_decomposition_source_route_discrimination_stays_warning_only(self) -> None:
        rows = dedent(
            """\
            | `accepted_route` | `defer` |
            | `promoted_artifact_kind` | `followup` |
            | `promoted_artifact_ref` | `docs/followups/260614_1435_process_followup.md` |
            | `queue_admission` | `not_queueable` |
            | `revisit_when` | `owner accepts future QA carrier/public command surface` |
            | `subject_identity` | `exact(qa_wave public command carrier)` |
            """
        ).rstrip()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260614_1440_process_schema_non_decomposition_warning",
                plan_meta=self._base_meta(wave_family="analysis_wave"),
                extra_sections=self._source_route_artifact(accepted_route="defer", rows=rows),
            )

            findings = self._schema_findings(MODULE.lint_plan(plan_path))

        self.assertEqual({finding.severity for finding in findings}, {"WARN"})
        self.assertTrue(any("Non-decomposition/V3-dependent route discrimination" in finding.message for finding in findings))

    def test_defer_source_route_requires_revisit_when(self) -> None:
        rows = dedent(
            """\
            | `accepted_route` | `defer` |
            | `promoted_artifact_kind` | `followup` |
            | `promoted_artifact_ref` | `docs/followups/260614_1435_process_followup.md` |
            | `queue_admission` | `not_queueable` |
            | `runner_admission` | `frontier_only` |
            | `subject_identity` | `exact(qa_wave public command carrier)` |
            """
        ).rstrip()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260614_1440_process_schema_defer_missing_revisit_when",
                plan_meta=self._base_meta(wave_family="analysis_wave"),
                extra_sections=self._source_route_artifact(accepted_route="defer", rows=rows),
            )

            findings = self._schema_findings(MODULE.lint_plan(plan_path))

        self.assertTrue(any(finding.severity == "ERROR" for finding in findings), findings)
        self.assertTrue(any("revisit_when" in finding.message for finding in findings), findings)

    def test_defer_source_route_warns_on_fuzzy_subject_identity(self) -> None:
        rows = dedent(
            """\
            | `accepted_route` | `defer` |
            | `promoted_artifact_kind` | `followup` |
            | `promoted_artifact_ref` | `docs/followups/260614_1435_process_followup.md` |
            | `queue_admission` | `not_queueable` |
            | `runner_admission` | `frontier_only` |
            | `revisit_when` | `owner accepts future QA carrier/public command surface` |
            | `subject_identity` | `fuzzy_match(qa-ish future command)` |
            """
        ).rstrip()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260614_1440_process_schema_defer_fuzzy_subject",
                plan_meta=self._base_meta(wave_family="analysis_wave"),
                extra_sections=self._source_route_artifact(accepted_route="defer", rows=rows),
            )

            findings = self._schema_findings(MODULE.lint_plan(plan_path))

        self.assertFalse(any(finding.severity == "ERROR" for finding in findings), findings)
        self.assertTrue(any(finding.severity == "WARN" and "subject_identity" in finding.message for finding in findings), findings)

    def test_human_gate_source_route_requires_revisit_when(self) -> None:
        rows = dedent(
            """\
            | `accepted_route` | `human_gate` |
            | `promoted_artifact_kind` | `owner_gate` |
            | `promoted_artifact_ref` | `docs/plans/260614_1435_process_owner_gate.md#q-and-a-log` |
            | `queue_admission` | `needs_owner` |
            | `runner_admission` | `frontier_only` |
            | `subject_identity` | `exact(owner approval for target branch protection claim)` |
            """
        ).rstrip()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260614_1440_process_schema_human_gate_missing_revisit_when",
                plan_meta=self._base_meta(wave_family="analysis_wave"),
                extra_sections=self._source_route_artifact(accepted_route="human_gate", rows=rows),
            )

            findings = self._schema_findings(MODULE.lint_plan(plan_path))

        self.assertTrue(any(finding.severity == "ERROR" for finding in findings), findings)
        self.assertTrue(any("revisit_when" in finding.message for finding in findings), findings)

    def test_reject_duplicate_route_warns_without_duplicate_of(self) -> None:
        rows = dedent(
            """\
            | `accepted_route` | `reject` |
            | `accepted_route_reason` | `Rejected as duplicate of existing owner-runbook parser route.` |
            | `promoted_artifact_kind` | `rejection_receipt` |
            | `promoted_artifact_ref` | `docs/plans/260614_1440_process_schema_reject_duplicate.md#promoted-route-artifact` |
            | `queue_admission` | `not_queueable` |
            | `runner_admission` | `frontier_only` |
            | `subject_identity` | `exact(owner-runbook parser route)` |
            """
        ).rstrip()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260614_1440_process_schema_reject_duplicate_without_ref",
                plan_meta=self._base_meta(wave_family="analysis_wave"),
                extra_sections=self._source_route_artifact(accepted_route="reject", rows=rows),
            )

            findings = self._schema_findings(MODULE.lint_plan(plan_path))

        self.assertFalse(any(finding.severity == "ERROR" for finding in findings), findings)
        self.assertTrue(any(finding.severity == "WARN" and "duplicate_of" in finding.message for finding in findings), findings)

    def test_review_readback_words_are_not_schema_inputs(self) -> None:
        review_ref = "docs/code_reviews/260614_1441_process_schema_stale_review_words.md"
        review_payload = dedent(
            """\
            # Code Review: fixture

            **Date:** 2026-06-14 14:41 MSK
            **Reviewer:** Reviewer
            **Status:** S1 blocker

            ## Findings
            - `CURRENT-REVIEW-RED`; historical-fixed.
            """
        )
        extra_sections = dedent(
            f"""\
            ## Evidence (chronological, append-only)
            - [2026-06-14 14:41 MSK] Fixture mentions `CURRENT-REVIEW-RED`, `stale_review_only`, `historical-fixed`.

            ## Review artifacts
            - Code review (primary): `{review_ref}`
            - stale note (2026-06-14 14:42 MSK): same review artifact is stale for this fixture.
            - rerun note (2026-06-14 14:43 MSK): same review artifact was rerun; no schema input.
            """
        ).rstrip()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260614_1441_process_schema_stale_review_words",
                plan_meta=self._base_meta(),
                extra_sections=extra_sections,
                review_artifact_payloads={review_ref: review_payload},
            )

            findings = self._schema_findings(MODULE.lint_plan(plan_path))

        self.assertEqual(findings, [])


class PlanLintRetrievalTelemetryReceiptTests(unittest.TestCase):
    def _write_fixture(self, root: Path, *, extra_sections: str = "") -> Path:
        helper = PlanLintReviewRouteDeterminismTests()
        return helper._write_fixture(
            root,
            plan_stem="260324_1201_process_retrieval_receipt_fixture",
            target_paths=["scripts/plan_lint.py"],
            review_artifact_lines=[
                "- Code review (primary): `docs/code_reviews/260324_1201_process_retrieval_receipt_fixture.md`"
            ],
            changes_block=dedent(
                """\
                - Scripts/tools:
                  - `scripts/docs_retrieve.py`
                """
            ).rstrip(),
            extra_sections=extra_sections,
        )

    def _retrieval_findings(self, findings: list[object]) -> list[object]:
        return [
            finding
            for finding in findings
            if "Retrieval telemetry receipt" in finding.message
            or "retrieval telemetry receipt" in finding.message
            or "allowed enum" in finding.message
            or "used_for_decision" in finding.message
            or "Retrieval decision evidence" in finding.message
        ]

    def test_retrieval_backed_plan_requires_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(Path(tmpdir))

            findings = MODULE.lint_plan(plan_path)

        self.assertTrue(
            any("`## Retrieval telemetry receipt`" in finding.message for finding in self._retrieval_findings(findings))
        )

    def test_valid_retrieval_receipt_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                extra_sections=dedent(
                    """\
                    ## Retrieval telemetry receipt
                    - query_event_id: `20260511T120000Z-abcd123456-12345678`
                    - used_for_decision: `true`
                    - read_open: `ok`
                    - read_log_status: `present`
                    - read_event_id: `read-20260511T120001Z-12345678`
                    - outcome: `used`
                    - outcome_reason: used for fixture scope.
                    - cited/opened files: `docs/tools/snippet.md`
                    """
                ),
            )

            findings = MODULE.lint_plan(plan_path)

        self.assertEqual(self._retrieval_findings(findings), [])

    def test_retrieval_decision_evidence_rejects_false_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                extra_sections=dedent(
                    """\
                    ## Lookup evidence
                    - Used `planveyor_docs_lookup plans "retrieval receipt"` for source selection.

                    ## Retrieval telemetry receipt
                    - query_event_id: `20260511T120000Z-abcd123456-12345678`
                    - used_for_decision: `false`
                    - read_open: `ok`
                    - read_log_status: `present`
                    - read_event_id: `read-20260511T120001Z-12345678`
                    - outcome: `used`
                    - outcome_reason: used for fixture scope.
                    - cited/opened files: `docs/tools/snippet.md`
                    - accepted_no_op_reason: `not_used_for_decision`
                    """
                ),
            )

            findings = MODULE.lint_plan(plan_path)

        messages = [finding.message for finding in self._retrieval_findings(findings)]
        self.assertTrue(any("Retrieval decision evidence" in message for message in messages))

    def test_valid_no_op_retrieval_receipt_passes_without_full_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                extra_sections=dedent(
                    """\
                    ## Retrieval telemetry receipt
                    - used_for_decision: `false`
                    - no_op_reason: `retrieval_only_file_discovery`
                    """
                ),
            )

            findings = MODULE.lint_plan(plan_path)

        self.assertEqual(self._retrieval_findings(findings), [])

    def test_no_op_reason_must_use_closed_enum(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                extra_sections=dedent(
                    """\
                    ## Retrieval telemetry receipt
                    - query_event_id: `latest`
                    - used_for_decision: `false`
                    - read_open: `N/A (why=just_because)`
                    - read_log_status: `N/A (why=just_because)`
                    - read_event_id: `N/A`
                    - outcome: `not_evaluated`
                    - outcome_reason: retrieval did not influence the fixture.
                    - cited/opened files: `N/A`
                    - no_op_reason: `just_because`
                    """
                ),
            )

            findings = MODULE.lint_plan(plan_path)

        messages = [finding.message for finding in self._retrieval_findings(findings)]
        self.assertTrue(any("allowed enum" in message for message in messages))


class PlanLintSchemaVersionTests(unittest.TestCase):
    def _write_fixture(self, *args, **kwargs) -> Path:
        helper = PlanLintReviewRouteDeterminismTests()
        return helper._write_fixture(*args, **kwargs)

    def _schema_state(self, rel_path: str, body: str) -> tuple[str, list[object]]:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            path = root / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(dedent(body), encoding="utf-8")
            return MODULE.classify_plan_schema_version(path, path.read_text(encoding="utf-8").splitlines())

    def test_current_plan_schema_version_is_accepted(self) -> None:
        state, findings = self._schema_state(
            "docs/plans/260419_1100_plan_schema_current.md",
            """\
            # Plan: schema current

            **Status:** Ready for Review
            **Schema version:** plan.v2
            """,
        )

        self.assertEqual(state, "v2")
        self.assertEqual(findings, [])

    def test_versionless_non_template_plan_is_legacy(self) -> None:
        state, findings = self._schema_state(
            "docs/plans/260419_1101_plan_schema_legacy.md",
            """\
            # Plan: schema legacy

            **Status:** Ready for Review
            """,
        )

        self.assertEqual(state, "legacy_v1")
        self.assertEqual(findings, [])

    def test_missing_schema_version_on_template_is_reported(self) -> None:
        state, findings = self._schema_state(
            "docs/plans/_template.md",
            """\
            # Plan: template

            **Status:** Architect initial draft
            """,
        )

        self.assertEqual(state, "unsupported")
        self.assertEqual(len(findings), 1)
        self.assertIn("Missing `**Schema version:** plan.v2`", findings[0].message)

    def test_v2_plan_rejects_legacy_local_followups_out_authority(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            path = root / "docs/plans/260811_0001_v2_external.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "# Plan: V2\n\n**Status:** Architect initial draft\n**Schema version:** plan.v2\n\n"
                "## Meta (machine-readable JSON)\n```json\n"
                '{"plan_meta":{"cluster":"process","tags":[],"required_manager_mode":"either",'
                '"phase_overlay":null,"phase_state":null,"parent":null,"next_plans":[],"depends_on":[],'
                '"followups_out":[],"canon_updates":[]}}\n```\n',
                encoding="utf-8",
            )
            findings = MODULE.lint_plan(path)
            self.assertTrue(any("plan.v2 forbids plan_meta.followups_out" in finding.message for finding in findings))

    def test_wrong_plan_schema_version_is_reported(self) -> None:
        state, findings = self._schema_state(
            "docs/plans/260419_1102_plan_schema_unsupported.md",
            """\
            # Plan: schema unsupported

            **Status:** Ready for Review
            **Schema version:** followups.v1
            """,
        )

        self.assertEqual(state, "unsupported")
        self.assertEqual(len(findings), 1)
        self.assertIn("Unsupported plan schema version", findings[0].message)

    def test_stale_historical_review_note_outside_live_carrier_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260324_1202_process_stale_note_route",
                target_paths=["docs/plans/README.md"],
                review_artifact_lines=[
                    "- Doc review (docs-only): `docs/doc_reviews/260324_1202_process_stale_note_route.md`",
                ],
                extra_sections=dedent(
                    """\
                    ## Suggestions log (chronological, append-only)

                    ### Reviewer suggestions
                    - [2026-03-25 20:21 MSK] (Reviewer) Historical note only: stale blocker used to live in `docs/code_reviews/260323_2359_old_route.md`, but current rerun must follow the docs-only live carrier above.
                    """
                ),
                complete=True,
            )

            findings = MODULE.lint_plan(plan_path)

        self.assertEqual(findings, [])


class PlanLintReviewArtifactFreshnessTests(unittest.TestCase):
    def _write_fixture(self, *args, **kwargs) -> Path:
        helper = PlanLintReviewRouteDeterminismTests()
        return helper._write_fixture(*args, **kwargs)

    def test_ready_for_review_with_blocker_review_file_needs_stale_rerun_note(self) -> None:
        review_rel = "docs/code_reviews/260324_1203_process_review_freshness_fail.md"
        review_text = dedent(
            """\
            # Code review — single commit

            **Date:** 25.03.2026 20:25 MSK
            **Target:** staged
            **Status:** ❌ S1 blocker(ы)

            Findings: stale blocker still visible.
            """
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260324_1203_process_review_freshness_fail",
                target_paths=["scripts/plan_lint.py"],
                review_artifact_lines=[f"- Code review (primary): `{review_rel}`"],
                review_artifact_payloads={review_rel: review_text},
            )

            findings = MODULE.lint_plan(plan_path)

        messages = [finding.message for finding in findings if "Review artifact freshness guard" in finding.message]
        self.assertEqual(len(messages), 1)

    def test_in_progress_with_blocker_review_file_and_explicit_rerun_note_passes(self) -> None:
        review_rel = "docs/doc_reviews/260324_1204_process_review_freshness_pass.md"
        review_text = dedent(
            """\
            # Doc review — single commit (docs/registry)

            **Date:** 25.03.2026 20:26 MSK
            **Target:** current
            **Scope:** docs-only
            **Status:** ❌ S1 blocker(ы)

            Findings: blocker exists before rerun.
            """
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260324_1204_process_review_freshness_pass",
                plan_status="In progress",
                target_paths=["docs/plans/README.md"],
                review_artifact_lines=[
                    f"- Doc review (docs-only): `{review_rel}`",
                    f"- Stale note (2026-03-25 20:27 MSK, Coder): previous blocker verdict in `{review_rel}` is historical until reviewer rerun completes.",
                    "- Rerun note (2026-03-25 20:27 MSK, Coder): reviewer must inspect current tree and rewrite the same review file in place.",
                ],
                review_artifact_payloads={review_rel: review_text},
            )

            findings = MODULE.lint_plan(plan_path)

        freshness_messages = [finding.message for finding in findings if "Review artifact freshness guard" in finding.message]
        self.assertEqual(freshness_messages, [])

    def test_old_stale_rerun_notes_do_not_cover_later_blocker_cycle(self) -> None:
        review_rel = "docs/code_reviews/260324_1206_process_review_freshness_old_cycle.md"
        review_text = dedent(
            """\
            # Code review — single commit

            **Date:** 2026-03-25 20:30 MSK
            **Target:** current
            **Status:** ❌ S1 blocker(ы)

            Findings: later blocker reopened the same review file.
            """
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260324_1206_process_review_freshness_old_cycle",
                target_paths=["scripts/plan_lint.py"],
                review_artifact_lines=[
                    f"- Code review (primary): `{review_rel}`",
                    f"- Stale note (2026-03-25 20:27 MSK, Coder): previous blocker verdict in `{review_rel}` is historical until reviewer rerun completes.",
                    "- Rerun note (2026-03-25 20:27 MSK, Coder): reviewer must inspect current tree and rewrite the same review file in place.",
                    "- Rerun result (2026-03-25 20:29 MSK, Reviewer): same review artifact rewritten in place for `current`; previous blocker cycle is closed.",
                ],
                review_artifact_payloads={review_rel: review_text},
            )

            findings = MODULE.lint_plan(plan_path)

        messages = [finding.message for finding in findings if "Review artifact freshness guard" in finding.message]
        self.assertEqual(len(messages), 1)

    def test_rewritten_review_file_with_fresh_header_passes_without_stale_note(self) -> None:
        review_rel = "docs/code_reviews/260324_1205_process_review_freshness_rewritten.md"
        review_text = dedent(
            """\
            # Code review — single commit

            **Date:** 25.03.2026 20:28 MSK
            **Target:** current
            **Status:** ✅ OK

            OK: same review file rewritten in place after rerun.
            """
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260324_1205_process_review_freshness_rewritten",
                target_paths=["scripts/plan_lint.py"],
                review_artifact_lines=[f"- Code review (primary): `{review_rel}`"],
                review_artifact_payloads={review_rel: review_text},
            )

            findings = MODULE.lint_plan(plan_path)

        freshness_messages = [finding.message for finding in findings if "Review artifact freshness guard" in finding.message]
        self.assertEqual(freshness_messages, [])


class PlanLintNoUiCorpusRequirementTests(unittest.TestCase):
    def test_ui_tags_do_not_require_removed_playbook_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            helper = PlanLintReviewRouteDeterminismTests()
            path = helper._write_fixture(
                Path(tmpdir),
                plan_stem="260317_2210_ui_without_shared_playbook",
                target_paths=["scripts/plan_lint.py"],
                review_artifact_lines=[
                    "- Code review (primary): `docs/code_reviews/260317_2210_ui_without_shared_playbook.md`"
                ],
                changes_block="- Templates/partials: target-owned component",
            )
            findings = MODULE.lint_plan(path)
        self.assertFalse(any("UI/HTMX micro-block" in row.message or "UI playbook" in row.message for row in findings))


class PlanLintBlockerAttributionContractTests(unittest.TestCase):
    def _write_fixture(self, *args, **kwargs) -> Path:
        helper = PlanLintReviewRouteDeterminismTests()
        return helper._write_fixture(*args, **kwargs)

    def test_missing_classification_on_reviewer_prompt_fails(self) -> None:
        review_rel = "docs/doc_reviews/260326_2310_process_blocker_attribution_prompt_red.md"
        review_text = dedent(
            """\
            # Doc review — fixture

            **Date:** 27.03.2026 09:55 MSK
            **Target:** current
            **Status:** ✅ OK

            OK: fixture review artifact.
            """
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260326_2310_process_blocker_attribution_prompt_red",
                target_paths=["docs/tools/prompts/reviewer_status_driven.md"],
                review_artifact_lines=[f"- Doc review (docs-only): `{review_rel}`"],
                review_artifact_payloads={review_rel: review_text},
                changes_block=dedent(
                    """\
                    - Docs/registry:
                      - `docs/tools/prompts/reviewer_status_driven.md`
                    """
                ).rstrip(),
            )
            prompt_path = root / "docs" / "tools" / "prompts" / "reviewer_status_driven.md"
            prompt_path.parent.mkdir(parents=True, exist_ok=True)
            prompt_path.write_text(
                dedent(
                    """\
                    - Blocker lineage:
                      - canonical ref = `<review_artifact_path>#B<N>`
                      - fields: `Blocker ID`, `Current state`, `Primary owner gap`, `Evidence refs`
                    """
                ),
                encoding="utf-8",
            )

            findings = MODULE.lint_plan(plan_path)

        messages = [finding.message for finding in findings if "docs/tools/prompts/reviewer_status_driven.md" in finding.message]
        self.assertEqual(len(messages), 1)
        self.assertIn("Classification", messages[0])

    def test_missing_classification_on_harvest_playbook_fails(self) -> None:
        review_rel = "docs/doc_reviews/260326_2311_process_blocker_attribution_harvest_red.md"
        review_text = dedent(
            """\
            # Doc review — fixture

            **Date:** 27.03.2026 09:56 MSK
            **Target:** current
            **Status:** ✅ OK

            OK: fixture review artifact.
            """
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write_fixture(
                root,
                plan_stem="260326_2311_process_blocker_attribution_harvest_red",
                target_paths=["docs/playbooks/post_merge_plan_harvest.md"],
                review_artifact_lines=[f"- Doc review (docs-only): `{review_rel}`"],
                review_artifact_payloads={review_rel: review_text},
                changes_block=dedent(
                    """\
                    - Docs/registry:
                      - `docs/playbooks/post_merge_plan_harvest.md`
                    """
                ).rstrip(),
            )
            harvest_path = root / "docs" / "playbooks" / "post_merge_plan_harvest.md"
            harvest_path.parent.mkdir(parents=True, exist_ok=True)
            harvest_path.write_text(
                dedent(
                    """\
                    - Keep canonical ref `<review_artifact_path>#B<N>`
                    - Reuse `Current state`, `Primary owner gap`, `Evidence refs`
                    """
                ),
                encoding="utf-8",
            )

            findings = MODULE.lint_plan(plan_path)

        messages = [finding.message for finding in findings if "docs/playbooks/post_merge_plan_harvest.md" in finding.message]
        self.assertEqual(len(messages), 1)
        self.assertIn("Classification", messages[0])


class PlanLintDevContourChildGraphDriftTests(unittest.TestCase):
    def setUp(self) -> None:
        MODULE.load_and_apply_plan_vocab(MODULE.PLAN_VOCAB_PATH)

    def _write_fixture(
        self,
        root: Path,
        *,
        plan_stem: str,
        plan_type_header: str | None = "dev",
        status: str = "Architect draft",
        scope_expansion: dict[str, object] | None = None,
        include_scope_expansion_key: bool = False,
        wave_family: str | None = None,
        phase_overlay: str | None = None,
        phase_state: str | None = None,
        extra_body: str = "",
    ) -> Path:
        (root / ".git").mkdir()
        ensure_fixture_git(root)
        plan_path = root / "docs" / "plans" / f"{plan_stem}.md"
        plan_path.parent.mkdir(parents=True, exist_ok=True)

        plan_meta = {
            "cluster": "process",
            "tags": [],
            "wave_family": wave_family,
            "phase_overlay": phase_overlay,
            "phase_state": phase_state,
            "parent": None,
            "next_plans": [],
            "depends_on": [],
            "followups_out": [],
            "canon_updates": [],
        }
        if scope_expansion is not None or include_scope_expansion_key:
            plan_meta["scope_expansion"] = scope_expansion

        plan_type_line = f"**Plan type:** {plan_type_header}" if plan_type_header is not None else ""

        plan_path.write_text(
            dedent(
                f"""\
                # Plan: child graph drift fixture

                **Date:** 2026-06-14 15:20 MSK
                **Stage:** Stage 1
                **Priority:** P1
                {plan_type_line}
                **Status:** {status}
                **Schema version:** plan.v1

                **Context links (source of truth):**
                - Fixture: `scripts/plan_lint.py`

                ## Meta (machine-readable JSON; required for new plans)
                ```json
                {{
                  "plan_meta": {json.dumps(plan_meta, ensure_ascii=False, indent=4)}
                }}
                ```

                ## Documentation impact / provenance
                - Source docs used: fixture.
                - Synchronous doc/registry targets: `docs/plans/README.md`.
                - Post-merge canon updates: `N/A (why=fixture)`.
                - Deferred documentation follow-ups: `N/A (why=fixture)`.
                - Provenance refs: fixture.

                ## Decisions (final)
                - Fixture.

                ## Scope
                - Fixture.

                ## Out of scope
                - Queue admission.

                ## Rollout packet handoff
                - Role: `N/A (why=fixture)`
                - Packet path: `N/A`
                - Target repo: `N/A`
                - Suggested target plan slug: `N/A`
                - Queue after import: `N/A`

                ## Close-out routing
                - Roadmap/queue sync: `N/A (fixture)`
                - Follow-up sync: `none`
                - Next bounded slice: `none`
                - Terminal outcome: yes

                ## Mechanism coverage
                - `N/A (why=fixture)`

                {extra_body}

                ## Changes (by area)
                - Docs/registry: `docs/plans/README.md`

                ## Tests
                - `python3 scripts/test_plan_lint.py`

                ## Commands
                - `python3 scripts/test_plan_lint.py`

                ## Verification rerun / exec handoff
                - Mode: `N/A (why=fixture)`
                - Context source: `N/A`
                - Prompt: `N/A`
                - Command: `N/A`
                - Expected artifact: `N/A`
                """
            ),
            encoding="utf-8",
        )
        return plan_path

    def _drift_warnings(self, findings: list[object]) -> list[object]:
        return [
            finding
            for finding in findings
            if MODULE.DEV_CONTOUR_CHILD_GRAPH_DRIFT_WARNING_PREFIX in finding.message
        ]

    def test_scope_expansion_reroute_state_warns_warning_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260614_1520_process_scope_expansion_reroute_warning",
                scope_expansion={
                    "state": "reroute_required",
                    "target_contour": "decomposition_wave",
                    "source_ref": "fixture",
                    "reason": "fixture child graph drift",
                },
            )

            warnings = self._drift_warnings(MODULE.lint_plan(plan_path))

        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].severity, "WARN")
        self.assertIn("plan_meta.scope_expansion.state=reroute_required", warnings[0].message)

    def test_scope_expansion_na_state_does_not_warn(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260614_1521_process_scope_expansion_na_no_warning",
                scope_expansion={
                    "state": "n/a",
                    "target_contour": "N/A",
                    "source_ref": "N/A (why=fixture)",
                    "reason": "N/A (why=fixture)",
                },
            )

            warnings = self._drift_warnings(MODULE.lint_plan(plan_path))

        self.assertEqual(warnings, [])

    def test_legacy_split_required_without_scope_expansion_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260614_1522_process_legacy_split_required_warning",
                extra_body="- Legacy note: split_required=true but no parseable carrier.\n",
            )

            warnings = self._drift_warnings(MODULE.lint_plan(plan_path))

        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].severity, "WARN")
        self.assertIn("without `plan_meta.scope_expansion`", warnings[0].message)

    def test_legacy_child_plan_path_without_scope_expansion_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260614_1523_process_legacy_child_plan_path_warning",
                extra_body=dedent(
                    """\
                    ## Child plan map
                    - Child: `docs/plans/260614_1525_process_child_fixture.md`
                    """
                ),
            )

            warnings = self._drift_warnings(MODULE.lint_plan(plan_path))

        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].severity, "WARN")
        self.assertIn("concrete child plan path in child-map/queue context", warnings[0].message)

    def test_silent_scope_widening_failure_mode_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260614_1524_process_silent_scope_widening_warning",
                extra_body="- failure_mode: silent_scope_widening\n",
            )

            warnings = self._drift_warnings(MODULE.lint_plan(plan_path))

        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].severity, "WARN")
        self.assertIn("silent_scope_widening", warnings[0].message)
        self.assertIn("record a concrete override reason", warnings[0].message)

    def test_hidden_dependency_drift_failure_mode_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260614_1525_process_hidden_dependency_drift_warning",
                extra_body="- smell_detector: hidden_dependency_drift\n",
            )

            warnings = self._drift_warnings(MODULE.lint_plan(plan_path))

        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].severity, "WARN")
        self.assertIn("hidden_dependency_drift", warnings[0].message)
        self.assertIn("parseable reroute state", warnings[0].message)

    def test_multiple_proof_lanes_without_integration_owner_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260614_1526_process_multi_proof_lane_warning",
                extra_body="- `proof_lanes`: `plan_lint`, `doc_lint`\n",
            )

            warnings = self._drift_warnings(MODULE.lint_plan(plan_path))

        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].severity, "WARN")
        self.assertIn("multiple proof lanes without integration/recomposition owner", warnings[0].message)
        self.assertIn("add an integration/serialization owner", warnings[0].message)

    def test_placeholder_proof_lane_owner_values_do_not_suppress_warning(self) -> None:
        placeholder_values = [
            ("integration_owner", "N/A (why=no recomposition owner assigned yet)", "integration_owner_na"),
            ("recomposition_owner", "unknown (why=owner not selected)", "recomposition_owner_unknown"),
            ("serialization_policy", "N/A (why=no serialization policy assigned yet)", "serialization_policy_na"),
            ("serialization_policy", "not serialized yet", "serialization_policy_negated"),
        ]
        for field, value, slug in placeholder_values:
            with self.subTest(field=field, value=value):
                with tempfile.TemporaryDirectory() as tmpdir:
                    plan_path = self._write_fixture(
                        Path(tmpdir),
                        plan_stem=f"260614_1529_process_{slug}_warning",
                        extra_body=dedent(
                            f"""\
                            - `proof_lanes`: `plan_lint`, `doc_lint`
                            - `{field}`: `{value}`
                            """
                        ),
                    )

                    warnings = self._drift_warnings(MODULE.lint_plan(plan_path))

                self.assertEqual(len(warnings), 1)
                self.assertEqual(warnings[0].severity, "WARN")
                self.assertIn("multiple proof lanes without integration/recomposition owner", warnings[0].message)

    def test_multiple_proof_lanes_with_integration_owner_does_not_warn(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260614_1527_process_multi_proof_lane_with_owner_no_warning",
                extra_body=dedent(
                    """\
                    - `proof_lanes`: `plan_lint`, `doc_lint`
                    - `integration_owner`: `Coder records the recomposed proof before review`
                    """
                ),
            )

            warnings = self._drift_warnings(MODULE.lint_plan(plan_path))

        self.assertEqual(warnings, [])

    def test_multiple_proof_lanes_with_material_serialization_policy_does_not_warn(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260614_1532_process_multi_proof_lane_with_policy_no_warning",
                extra_body=dedent(
                    """\
                    - `proof_lanes`: `plan_lint`, `doc_lint`
                    - `serialization_policy`: serialized by Coder before review
                    """
                ),
            )

            warnings = self._drift_warnings(MODULE.lint_plan(plan_path))

        self.assertEqual(warnings, [])

    def test_context_plan_ref_without_child_marker_does_not_warn(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260614_1528_process_context_ref_no_warning",
                extra_body="- Related plan: `docs/plans/260614_1529_process_context_fixture.md`\n",
            )

            warnings = self._drift_warnings(MODULE.lint_plan(plan_path))

        self.assertEqual(warnings, [])

    def test_null_scope_expansion_child_plan_path_warns_as_missing_carrier(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260614_1530_process_null_scope_expansion_child_path_warning",
                include_scope_expansion_key=True,
                extra_body=dedent(
                    """\
                    ## Child plan map
                    - Child: `docs/plans/260614_1527_process_child_fixture.md`
                    """
                ),
            )

            warnings = self._drift_warnings(MODULE.lint_plan(plan_path))

        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].severity, "WARN")
        self.assertIn("concrete child plan path in child-map/queue context", warnings[0].message)
        self.assertIn("without `plan_meta.scope_expansion`", warnings[0].message)

    def test_decomposition_wave_child_graph_text_does_not_warn(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260614_1531_process_decomposition_child_graph_no_warning",
                phase_overlay="decomposition_wave",
                phase_state="active",
                extra_body=dedent(
                    """\
                    ## Child plan map
                    - Child: `docs/plans/260614_1528_process_child_fixture.md`
                    - Legacy note: `split_required=true` is not drift inside decomposition.
                    - `failure_mode`: `hidden_dependency_drift`
                    """
                ),
            )

            warnings = self._drift_warnings(MODULE.lint_plan(plan_path))

        self.assertEqual(warnings, [])

    def test_pre_coder_full_predicate_promotes_existing_signal_to_error(self) -> None:
        for status in ("Planner finalize", "Ready for Coder"):
            with self.subTest(status=status):
                with tempfile.TemporaryDirectory() as tmpdir:
                    plan_path = self._write_fixture(
                        Path(tmpdir),
                        plan_stem="260801_1634_process_pre_coder_existing_signal_error",
                        status=status,
                        extra_body="- Legacy note: split_required=true.\n",
                    )

                    findings = self._drift_warnings(MODULE.lint_plan(plan_path))

                self.assertEqual(len(findings), 1)
                self.assertEqual(findings[0].severity, "ERROR")
                self.assertIn("remains unresolved at the pre-Coder handoff", findings[0].message)
                self.assertNotIn("warning-only, not queue/admission blocking", findings[0].message)

    def test_pre_coder_unresolved_structured_states_are_errors(self) -> None:
        for status in ("Planner finalize", "Ready for Coder"):
            for state in ("suspected", "architect_accepted", "reroute_required"):
                with self.subTest(status=status, state=state):
                    with tempfile.TemporaryDirectory() as tmpdir:
                        plan_path = self._write_fixture(
                            Path(tmpdir),
                            plan_stem="260801_1635_process_pre_coder_structured_state_error",
                            status=status,
                            scope_expansion={
                                "state": state,
                                "target_contour": "decomposition_wave",
                                "source_ref": "fixture",
                                "reason": "fixture",
                            },
                        )

                        findings = self._drift_warnings(MODULE.lint_plan(plan_path))

                    self.assertEqual(len(findings), 1)
                    self.assertEqual(findings[0].severity, "ERROR")
                    self.assertIn(f"state={state}", findings[0].message)

    def test_pre_coder_state_na_uses_only_existing_detector_signal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            clean_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260801_1636_process_pre_coder_na_clean",
                status="Ready for Coder",
                scope_expansion={
                    "state": "n/a",
                    "target_contour": "developer_wave",
                    "source_ref": "N/A (why=fixture)",
                    "reason": "N/A (why=fixture)",
                },
            )

            clean_findings = self._drift_warnings(MODULE.lint_plan(clean_path))

        self.assertEqual(clean_findings, [])

        with tempfile.TemporaryDirectory() as tmpdir:
            signal_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260801_1637_process_pre_coder_na_signal",
                status="Ready for Coder",
                scope_expansion={
                    "state": "n/a",
                    "target_contour": "developer_wave",
                    "source_ref": "N/A (why=fixture)",
                    "reason": "Any free-form explanation is not a new override contract.",
                },
                extra_body="- Legacy note: split_required=true.\n",
            )

            signal_findings = self._drift_warnings(MODULE.lint_plan(signal_path))

        self.assertEqual(len(signal_findings), 1)
        self.assertEqual(signal_findings[0].severity, "ERROR")

    def test_pre_coder_state_na_preserves_existing_multi_proof_suppression(self) -> None:
        cases = (
            ("serialized proof evidence before Coder", None),
            ("context only", "ERROR"),
        )
        for reason, expected_severity in cases:
            with self.subTest(reason=reason):
                with tempfile.TemporaryDirectory() as tmpdir:
                    plan_path = self._write_fixture(
                        Path(tmpdir),
                        plan_stem="260801_1638_process_pre_coder_na_multi_proof",
                        status="Ready for Coder",
                        scope_expansion={
                            "state": "n/a",
                            "target_contour": "developer_wave",
                            "source_ref": "fixture",
                            "reason": reason,
                        },
                        extra_body="- `proof_lanes`: `plan_lint`, `doc_lint`\n",
                    )

                    findings = self._drift_warnings(MODULE.lint_plan(plan_path))

                if expected_severity is None:
                    self.assertEqual(findings, [])
                else:
                    self.assertEqual(len(findings), 1)
                    self.assertEqual(findings[0].severity, expected_severity)

    def test_off_predicate_state_na_keeps_existing_carrier_short_circuit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260801_1639_process_early_na_signal",
                status="Architect draft",
                scope_expansion={
                    "state": "n/a",
                    "target_contour": "developer_wave",
                    "source_ref": "fixture",
                    "reason": "fixture",
                },
                extra_body="- Legacy note: split_required=true.\n",
            )

            findings = self._drift_warnings(MODULE.lint_plan(plan_path))

        self.assertEqual(findings, [])

    def test_pre_coder_promotion_boundaries_preserve_legacy_behavior(self) -> None:
        cases = (
            ("260731_2359_process_pre_cutoff", "dev", "Ready for Coder", None, None, None, "ERROR"),
            ("260801_1638_process_composite", "dev (dev | review-only)", "Ready for Coder", None, None, None, "WARN"),
            ("260801_1639_process_missing_type", None, "Ready for Coder", None, None, None, "WARN"),
            ("260801_1640_process_non_dev", "analysis", "Ready for Coder", None, None, None, "WARN"),
            ("260801_1641_process_early_status", "dev", "Architect draft", None, None, None, "WARN"),
            (
                "260801_1642_process_decomposition",
                "dev",
                "Ready for Coder",
                None,
                "decomposition_wave",
                "active",
                None,
            ),
            (
                "260801_1643_process_analysis",
                "dev",
                "Ready for Coder",
                "analysis_wave",
                None,
                "active",
                None,
            ),
        )
        for plan_stem, plan_type, status, wave_family, phase_overlay, phase_state, expected_severity in cases:
            with self.subTest(plan_stem=plan_stem):
                with tempfile.TemporaryDirectory() as tmpdir:
                    plan_path = self._write_fixture(
                        Path(tmpdir),
                        plan_stem=plan_stem,
                        plan_type_header=plan_type,
                        status=status,
                        wave_family=wave_family,
                        phase_overlay=phase_overlay,
                        phase_state=phase_state,
                        extra_body="- Legacy note: split_required=true.\n",
                    )

                    findings = self._drift_warnings(MODULE.lint_plan(plan_path))

                if expected_severity is None:
                    self.assertEqual(findings, [])
                else:
                    self.assertEqual(len(findings), 1)
                    self.assertEqual(findings[0].severity, expected_severity)

    def test_ready_for_architect_response_keeps_existing_reroute_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260801_1644_process_existing_architect_reroute",
                status="Ready for Architect response",
                scope_expansion={
                    "state": "reroute_required",
                    "target_contour": "decomposition_wave",
                    "source_ref": "fixture",
                    "reason": "fixture",
                },
            )

            findings = self._drift_warnings(MODULE.lint_plan(plan_path))

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "WARN")
        self.assertIn("warning-only, not queue/admission blocking", findings[0].message)

    def test_pre_coder_historical_child_refs_do_not_create_live_graph_drift(self) -> None:
        historical_rows = dedent(
            """\
            - Delivered baseline: `docs/plans/260822_1728_missing-child_baseline.md` (missing-child provenance).

            ## Evidence (chronological, append-only)
            - [2026-08-22 22:00 MSK] (Planner) Historical child graph receipt references `docs/plans/260822_1729_child_evidence.md`.

            ## Q&A log (chronological, append-only)
            - [2026-08-22 22:01 MSK] (Planner) Historical child graph question referenced `docs/plans/260822_1730_child_qna.md`.

            ## Suggestions log (chronological, append-only)
            - [2026-08-22 22:02 MSK] (Planner) Historical child graph suggestion referenced `docs/plans/260822_1731_child_suggestion.md`.

            ## Objections / risks log (chronological, append-only)
            - [2026-08-22 22:03 MSK] (Planner) Historical child graph objection referenced `docs/plans/260822_1732_child_objection.md`.
            """
        )
        for status in ("Planner finalize", "Ready for Coder"):
            with self.subTest(status=status):
                with tempfile.TemporaryDirectory() as tmpdir:
                    plan_path = self._write_fixture(
                        Path(tmpdir),
                        plan_stem="260822_1727_process_historical_child_ref_clean",
                        status=status,
                        extra_body=historical_rows,
                    )
                    findings = self._drift_warnings(MODULE.lint_plan(plan_path))

                self.assertEqual(findings, [])

    def test_pre_coder_live_child_carriers_and_noncanonical_evidence_stay_errors(self) -> None:
        concrete_path = "docs/plans/260822_1730_billing.md"
        cases = {
            "unstructured_context": f"- Related child reference: `{concrete_path}`.\n",
            "anchored_child": f"- Child plan: `{concrete_path}` (historical qualifier is not authority).\n",
            "anchored_promoted": f"- Promoted child: `{concrete_path}` (historical qualifier is not authority).\n",
            "anchored_next": f"- Next plans: `{concrete_path}` (historical qualifier is not authority).\n",
            "child_map": (
                "## Child plan map\n"
                "| Queue order | Plan | Summary |\n"
                "| --- | --- | --- |\n"
                f"| 1 | `{concrete_path}` | fixture |\n"
            ),
            "execution_queue": f"## Execution queue\n- Plan: `{concrete_path}`\n",
            "noncanonical_evidence": (
                "## Evidence (chronological, append-only)\n"
                f"2026-08-22 22:00 MSK historical child graph reference `{concrete_path}`\n"
            ),
            "misplaced_evidence_timestamp": (
                "## Evidence (chronological, append-only)\n"
                f"- [historical] 2026-08-22 22:00 MSK child graph reference `{concrete_path}`\n"
            ),
        }
        for status in ("Planner finalize", "Ready for Coder"):
            for name, extra_body in cases.items():
                with self.subTest(status=status, case=name):
                    with tempfile.TemporaryDirectory() as tmpdir:
                        plan_path = self._write_fixture(
                            Path(tmpdir),
                            plan_stem="260822_1727_process_live_child_ref_error",
                            status=status,
                            extra_body=extra_body,
                        )
                        findings = self._drift_warnings(MODULE.lint_plan(plan_path))

                self.assertEqual(len(findings), 1)
                self.assertEqual(findings[0].severity, "ERROR")

        for status in ("Planner finalize", "Ready for Coder"):
            with self.subTest(status=status, case="plan_meta_next_plans"):
                with tempfile.TemporaryDirectory() as tmpdir:
                    plan_path = self._write_fixture(
                        Path(tmpdir),
                        plan_stem="260822_1727_process_next_plans_error",
                        status=status,
                    )
                    text = plan_path.read_text(encoding="utf-8")
                    plan_path.write_text(
                        text.replace(
                            '"next_plans": [],',
                            f'"next_plans": ["{concrete_path}"],',
                        ),
                        encoding="utf-8",
                    )
                    findings = self._drift_warnings(MODULE.lint_plan(plan_path))

                self.assertEqual(len(findings), 1)
                self.assertEqual(findings[0].severity, "ERROR")

    def test_pre_coder_long_live_map_and_queue_sections_with_neutral_paths_are_errors(self) -> None:
        concrete_path = "docs/plans/260822_1730_billing.md"
        cases = {
            "child_plan_map": dedent(
                f"""\
                ## Child plan map
                - Explanatory row before the live carrier.
                | Queue order | Plan | Summary |
                | --- | --- | --- |
                | 0 | N/A (why=fixture padding) | padding |
                | 1 | `{concrete_path}` | fixture |
                """
            ),
            "execution_queue": dedent(
                f"""\
                ## Execution queue
                - Explanatory row before the live carrier.
                - Additional fixture padding row.
                - Another fixture padding row.
                - Plan: `{concrete_path}`
                """
            ),
        }
        for status in ("Planner finalize", "Ready for Coder"):
            for name, extra_body in cases.items():
                with self.subTest(status=status, case=name):
                    with tempfile.TemporaryDirectory() as tmpdir:
                        plan_path = self._write_fixture(
                            Path(tmpdir),
                            plan_stem="260822_1727_process_long_live_section_error",
                            status=status,
                            extra_body=extra_body,
                        )
                        findings = self._drift_warnings(MODULE.lint_plan(plan_path))

                    self.assertEqual(len(findings), 1)
                    self.assertEqual(findings[0].severity, "ERROR")
                    self.assertIn("child-map/queue context", findings[0].message)

    def test_pre_coder_fenced_pseudo_h2_does_not_reset_live_child_section(self) -> None:
        concrete_path = "docs/plans/260822_1730_billing.md"
        cases = {
            "child_plan_map": dedent(
                f"""\
                ## Child plan map
                ```text
                ## Not a real heading
                ```
                - Reference: `{concrete_path}`
                """
            ),
            "execution_queue": dedent(
                f"""\
                ## Execution queue
                ```text
                ## Not a real heading
                ```
                - Reference: `{concrete_path}`
                """
            ),
        }
        for status in ("Planner finalize", "Ready for Coder"):
            for name, extra_body in cases.items():
                with self.subTest(status=status, case=name):
                    with tempfile.TemporaryDirectory() as tmpdir:
                        plan_path = self._write_fixture(
                            Path(tmpdir),
                            plan_stem="260822_1727_process_fenced_pseudo_h2_error",
                            status=status,
                            extra_body=extra_body,
                        )
                        findings = self._drift_warnings(MODULE.lint_plan(plan_path))

                    self.assertEqual(len(findings), 1)
                    self.assertEqual(findings[0].severity, "ERROR")
                    self.assertIn("child-map/queue context", findings[0].message)

    def test_pre_coder_real_h2_resets_live_child_section_after_fenced_pseudo_h2(self) -> None:
        concrete_path = "docs/plans/260822_1730_billing.md"
        cases = {
            "child_plan_map": "## Child plan map",
            "execution_queue": "## Execution queue",
        }
        for status in ("Planner finalize", "Ready for Coder"):
            for name, live_heading in cases.items():
                with self.subTest(status=status, case=name):
                    with tempfile.TemporaryDirectory() as tmpdir:
                        plan_path = self._write_fixture(
                            Path(tmpdir),
                            plan_stem="260822_1727_process_real_h2_reset_clean",
                            status=status,
                            extra_body=dedent(
                                f"""\
                                {live_heading}
                                ```text
                                ## Not a real heading
                                ```
                                ## Context
                                - Reference: `{concrete_path}`
                                """
                            ),
                        )
                        findings = self._drift_warnings(MODULE.lint_plan(plan_path))

                    self.assertEqual(findings, [])
    def test_history_path_with_marker_same_line_not_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260814_1503_process_history_path_marker_same_line",
                status="Planner finalize",
                extra_body=dedent(
                    """

                    ## Evidence (chronological, append-only)
                    - [2026-08-14 10:00 MSK] Q1 closed: successor `docs/plans/260614_1525_process_child_fixture.md` stuck in child-map context (history quote).
                    """
                ),
            )

            warnings = self._drift_warnings(MODULE.lint_plan(plan_path))

        self.assertEqual(warnings, [])

    def test_live_path_with_quoted_heading_window_not_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260814_1511_process_live_path_quoted_heading_window",
                status="Planner finalize",
                extra_body=dedent(
                    """

                    ## Review notes
                    - Gate error quote: `## Child plan map` window re-armed the detector.
                    - Line under test: `docs/plans/260614_1525_process_child_fixture.md`.
                    """
                ),
            )

            warnings = self._drift_warnings(MODULE.lint_plan(plan_path))

        self.assertEqual(warnings, [])


    def test_exact_drift_headings_still_arm_window(self) -> None:
        exact_headings = (
            "## Child plan map",
            "## Execution queue",
            "## Execution queue   ",
        )
        for heading in exact_headings:
            with self.subTest(heading=heading.rstrip()):
                with tempfile.TemporaryDirectory() as tmpdir:
                    plan_path = self._write_fixture(
                        Path(tmpdir),
                        plan_stem="260814_1513_process_exact_drift_heading_arms",
                        status="Planner finalize",
                        extra_body=dedent(
                            f"""

                            {heading}
                            - Review target: `docs/plans/260614_1525_process_child_fixture.md`.
                            """
                        ),
                    )

                    warnings = self._drift_warnings(MODULE.lint_plan(plan_path))

                self.assertEqual(len(warnings), 1)
                self.assertEqual(warnings[0].severity, "ERROR")
                self.assertIn("concrete child plan path in child-map/queue context", warnings[0].message)

    def test_fenced_and_inline_code_heading_mentions_not_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260814_1505_process_fenced_inline_code_heading_mentions",
                status="Planner finalize",
                extra_body=dedent(
                    """

                    ## Scope
                    - Live context path: `docs/plans/260614_1525_process_child_fixture.md`.

                    ```
                    ## Child plan map
                    ```

                    - Prose mention of `## Execution queue` wording is inline code, not a heading.
                    """
                ),
            )

            warnings = self._drift_warnings(MODULE.lint_plan(plan_path))

        self.assertEqual(warnings, [])



    def test_live_backticked_child_ref_still_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260814_1508_process_live_backticked_child_ref",
                extra_body="- Related: `docs/plans/260614_1525_process_child_fixture.md` is the next plan in this contour.\n",
            )

            warnings = self._drift_warnings(MODULE.lint_plan(plan_path))

        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].severity, "WARN")
        self.assertIn("concrete child plan path in child-map/queue context", warnings[0].message)

    def test_live_unbackticked_legacy_wording_still_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260814_1509_process_live_unbackticked_legacy_wording",
                extra_body="- Legacy note: hidden child graph declared without a carrier.\n",
            )

            warnings = self._drift_warnings(MODULE.lint_plan(plan_path))

        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].severity, "WARN")
        self.assertIn("without `plan_meta.scope_expansion`", warnings[0].message)

    def test_unbackticked_failure_mode_field_still_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260814_1510_process_unbackticked_failure_mode_field",
                extra_body="- failure_mode: hidden_dependency_drift\n",
            )

            warnings = self._drift_warnings(MODULE.lint_plan(plan_path))

        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].severity, "WARN")
        self.assertIn("hidden_dependency_drift", warnings[0].message)

    def test_unequal_backtick_runs_do_not_mask_live_legacy_wording(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260815_2201_process_unequal_backtick_runs_live_wording",
                extra_body="- Receipt cites `hidden child graph``` wording from history.\n",
            )

            warnings = self._drift_warnings(MODULE.lint_plan(plan_path))

        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].severity, "WARN")
        self.assertIn("without `plan_meta.scope_expansion`", warnings[0].message)


    def test_near_match_history_headings_are_live_sections(self) -> None:
        near_match_headings = (
            "## Evidence-based notes",
            "## Q&A log: receipt notes",
        )
        for heading in near_match_headings:
            with self.subTest(heading=heading):
                with tempfile.TemporaryDirectory() as tmpdir:
                    plan_path = self._write_fixture(
                        Path(tmpdir),
                        plan_stem="260815_2203_process_near_match_history_headings_live",
                        status="Planner finalize",
                        extra_body=dedent(
                            f"""

                            {heading}
                            - Parked successor child plan `docs/plans/260614_1525_process_child_fixture.md` waits on this slice.
                            """
                        ),
                    )

                    warnings = self._drift_warnings(MODULE.lint_plan(plan_path))

                self.assertEqual(len(warnings), 1)
                self.assertEqual(warnings[0].severity, "ERROR")
                self.assertIn("concrete child plan path in child-map/queue context", warnings[0].message)

    def test_real_suffix_history_headings_still_excluded(self) -> None:
        suffixed_headings = (
            "## Evidence (chronological, append-only)",
            "## Q&A log (chronological, append-only)",
        )
        for heading in suffixed_headings:
            with self.subTest(heading=heading):
                with tempfile.TemporaryDirectory() as tmpdir:
                    plan_path = self._write_fixture(
                        Path(tmpdir),
                        plan_stem="260815_2204_process_real_suffix_history_headings",
                        status="Planner finalize",
                        extra_body=dedent(
                            f"""

                            {heading}
                            - [2026-08-15 22:00 MSK] Receipt: successor child plan `docs/plans/260614_1525_process_child_fixture.md` quoted from history.
                            """
                        ),
                    )

                    warnings = self._drift_warnings(MODULE.lint_plan(plan_path))

                self.assertEqual(warnings, [])


    def test_longer_or_equal_fence_closer_still_closes(self) -> None:
        closers = ("```", "````")
        for closer in closers:
            with self.subTest(closer_len=len(closer)):
                with tempfile.TemporaryDirectory() as tmpdir:
                    plan_path = self._write_fixture(
                        Path(tmpdir),
                        plan_stem="260815_2206_process_fence_closer_scans_after",
                        extra_body=dedent(
                            f"""
                            ```text
                            sample content stays inside the fence
                            {closer}
                            - Live note: hidden child graph declared after the closer.
                            """
                        ),
                    )

                    warnings = self._drift_warnings(MODULE.lint_plan(plan_path))

                self.assertEqual(len(warnings), 1)
                self.assertEqual(warnings[0].severity, "WARN")
                self.assertIn("without `plan_meta.scope_expansion`", warnings[0].message)



    def test_unmatched_runs_raw_fallback_control(self) -> None:
        # D1.12 control: runs without an equal-length subsequent partner keep
        # conservative raw matching, and an unmatched run does not block
        # pairing for later runs (layout 2,1,1: the len-2 run stays raw, the
        # len-1 pair is masked). The signal between unmatched runs is caught
        # raw — green before and after the fix by design.
        unmatched_bodies = (
            "- Sample: ``hidden child graph` note` from history.",
            "- Sample: ``hidden child graph` from history.",
        )
        for body in unmatched_bodies:
            with self.subTest(body=body):
                with tempfile.TemporaryDirectory() as tmpdir:
                    plan_path = self._write_fixture(
                        Path(tmpdir),
                        plan_stem="260816_2209_process_unmatched_runs_raw_control",
                        extra_body=body + "\n",
                    )

                    warnings = self._drift_warnings(MODULE.lint_plan(plan_path))

                self.assertEqual(len(warnings), 1)
                self.assertEqual(warnings[0].severity, "WARN")
                self.assertIn("without `plan_meta.scope_expansion`", warnings[0].message)






class PlanLintDecompositionMechanismSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        MODULE.load_and_apply_plan_vocab(MODULE.PLAN_VOCAB_PATH)

    def _write_fixture(
        self,
        root: Path,
        *,
        plan_stem: str,
        mechanism_coverage: str,
        quality_gate: str,
    ) -> Path:
        (root / ".git").mkdir()
        ensure_fixture_git(root)
        plan_path = root / "docs" / "plans" / f"{plan_stem}.md"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(
            dedent(
                f"""\
                # Plan: decomposition mechanism schema fixture

                **Date:** 2026-06-19 00:30 MSK
                **Stage:** Stage 2
                **Priority:** P1
                **Plan type:** dev
                **Status:** Architect draft
                **Schema version:** plan.v1

                **Context links (source of truth):**
                - Fixture: `scripts/plan_lint.py`

                ## Meta (machine-readable JSON; required for new plans)
                ```json
                {{
                  "plan_meta": {{
                    "cluster": "process",
                    "tags": [],
                    "wave_family": null,
                    "phase_overlay": "decomposition_wave",
                    "phase_state": "active",
                    "parent": null,
                    "next_plans": [],
                    "depends_on": [],
                    "followups_out": [],
                    "canon_updates": []
                  }}
                }}
                ```

                ## Documentation impact / provenance
                - Source docs used: fixture.
                - Synchronous doc/registry targets: `docs/playbooks/decomposition_wave.md`.
                - Post-merge canon updates: `N/A (why=fixture)`.
                - Deferred documentation follow-ups: `N/A (why=fixture)`.
                - Provenance refs: fixture.

                ## Problem
                Фикстура проверяет schema warnings для decomposition carriers.

                ## Как я понял задачу
                Фикстура активного decomposition overlay не создаёт реальных children.

                ## Decisions (final)
                - Fixture.

                ### UI/HTMX playbooks (micro-block; required for UI/HTMX tasks)
                - Archetype: `N/A (why=process helper fixture)`
                - Modules: `N/A (why=process helper fixture)`
                - Primary CTA: `N/A (why=process helper fixture)`
                - header_filters: `N/A (why=process helper fixture)`
                - Results count strategy: `N/A (why=process helper fixture)`

                ## Scope
                - Fixture.

                ## Out of scope
                - Product code.

                ## Rollout packet handoff
                - Role: `N/A (why=fixture)`
                - Packet path: `N/A (why=fixture)`
                - Target repo: `N/A (why=fixture)`
                - Suggested target plan slug: `N/A (why=fixture)`
                - Queue after import: `N/A (why=fixture)`

                ## Close-out routing
                - Roadmap/queue sync: fixture.
                - Follow-up sync: `N/A (why=fixture)`
                - Next bounded slice: `N/A (why=fixture)`
                - Terminal outcome: no (fixture).

                ## Decomposition quality gate
                {quality_gate}

                ## Mechanism coverage
                {mechanism_coverage}

                ## Child plan map
                | Queue order | Plan | Summary |
                | --- | --- | --- |
                | 1 | `TBD (why=fixture child graph not ready)` | pending child |

                ## Execution queue
                - Resume parent: `owner-restamp-required`
                - Plan: `N/A (why=fixture child graph not ready)`

                ## Changes (by area)
                - Services/selectors: `scripts/plan_lint.py`.

                ## Tests
                - `python3 scripts/test_plan_lint.py`

                ## Commands
                - `python3 scripts/test_plan_lint.py`

                ## Verification rerun / exec handoff
                - Mode: fresh-exec
                - Context source: fixture.
                - Prompt: fixture.
                - Command: `python3 scripts/test_plan_lint.py`
                - Expected artifact: decomposition mechanism schema finding.
                """
            ),
            encoding="utf-8",
        )
        return plan_path

    def _valid_mechanism_coverage(self) -> str:
        return dedent(
            """\
            | Mechanism | Usage | Source refs | Proof anchor | State | Promoted child impact |
            | --- | --- | --- | --- | --- | --- |
            | golden-path | selected planning contour | `docs/guides/golden_paths.md#planning-contour-continuity` | `docs/guides/golden_paths.md#planning-contour-continuity` | used | child plans inherit source refs |
            """
        ).rstrip()

    def _valid_quality_gate(self) -> str:
        return dedent(
            """\
            - Solvability: `N/A (why=fixture child graph not ready)`
            - Completeness: `N/A (why=fixture child graph not ready)`
            - Non-redundancy: `N/A (why=fixture child graph not ready)`
            - Mutable surface / runtime isolation: `N/A (why=fixture child graph not ready)`
            - Recomposition / integration owner: `N/A (why=fixture child graph not ready)`
            """
        ).rstrip()

    def _schema_warnings(self, findings: list[object]) -> list[object]:
        return [
            finding
            for finding in findings
            if MODULE.DECOMPOSITION_MECHANISM_SCHEMA_WARNING_PREFIX in finding.message
        ]

    def test_decomposition_schema_valid_rows_have_no_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260619_0030_process_decomposition_schema_valid",
                mechanism_coverage=self._valid_mechanism_coverage(),
                quality_gate=self._valid_quality_gate(),
            )

            findings = MODULE.lint_plan(plan_path)

        self.assertEqual(self._schema_warnings(findings), [])

    def test_decomposition_mechanism_empty_prose_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260619_0030_process_decomposition_schema_empty_prose",
                mechanism_coverage="- Used golden path and backlog.",
                quality_gate=self._valid_quality_gate(),
            )

            warnings = self._schema_warnings(MODULE.lint_plan(plan_path))

        self.assertTrue(any("no parseable row-based mechanism fields" in finding.message for finding in warnings), warnings)

    def test_decomposition_mechanism_missing_proof_anchor_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260619_0030_process_decomposition_schema_missing_proof",
                mechanism_coverage=dedent(
                    """\
                    | Mechanism | Usage | Source refs | Proof anchor | State | Promoted child impact |
                    | --- | --- | --- | --- | --- | --- |
                    | golden-path | selected planning contour | `docs/guides/golden_paths.md` |  | used | child plans inherit source refs |
                    """
                ).rstrip(),
                quality_gate=self._valid_quality_gate(),
            )

            warnings = self._schema_warnings(MODULE.lint_plan(plan_path))

        self.assertTrue(any("proof_anchor" in finding.message for finding in warnings), warnings)

    def test_decomposition_mechanism_explicit_na_proof_anchor_allows_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260619_0030_process_decomposition_schema_na_proof",
                mechanism_coverage=dedent(
                    """\
                    | Mechanism | Usage | Source refs | Proof anchor | State | Promoted child impact |
                    | --- | --- | --- | --- | --- | --- |
                    | `N/A (why=fixture mechanism not used)` | `N/A (why=fixture mechanism not used)` | `N/A (why=fixture mechanism not used)` | `N/A (why=fixture mechanism not used)` | `N/A (why=fixture mechanism not used)` | `N/A (why=fixture mechanism not used)` |
                    """
                ).rstrip(),
                quality_gate=self._valid_quality_gate(),
            )

            findings = MODULE.lint_plan(plan_path)

        self.assertEqual(self._schema_warnings(findings), [])

    def test_decomposition_quality_gate_missing_field_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            quality_gate = dedent(
                """\
                - Solvability: child has owner/input/proof route
                - Completeness: parent plus deferred follow-ups cover scope
                - Mutable surface / runtime isolation: `N/A (why=serialized fixture)`
                - Recomposition / integration owner: Planner owns recomposition
                """
            ).rstrip()
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260619_0030_process_decomposition_schema_missing_quality",
                mechanism_coverage=self._valid_mechanism_coverage(),
                quality_gate=quality_gate,
            )

            warnings = self._schema_warnings(MODULE.lint_plan(plan_path))

        self.assertTrue(any("non_redundancy" in finding.message for finding in warnings), warnings)

    def test_decomposition_quality_gate_weak_value_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            quality_gate = self._valid_quality_gate().replace(
                "- Solvability: `N/A (why=fixture child graph not ready)`",
                "- Solvability: ok",
            )
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260619_0030_process_decomposition_schema_weak_quality",
                mechanism_coverage=self._valid_mechanism_coverage(),
                quality_gate=quality_gate,
            )

            warnings = self._schema_warnings(MODULE.lint_plan(plan_path))

        self.assertTrue(any("generic verdict without proof" in finding.message for finding in warnings), warnings)

    def test_decomposition_quality_gate_failure_modes_warn(self) -> None:
        for mode in MODULE.DECOMPOSITION_FAILURE_MODES:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmpdir:
                quality_gate = self._valid_quality_gate().replace(
                    "- Completeness: `N/A (why=fixture child graph not ready)`",
                    f"- Completeness: `{mode}` still needs mitigation",
                )
                plan_path = self._write_fixture(
                    Path(tmpdir),
                    plan_stem=f"260619_0030_process_decomposition_schema_{mode}",
                    mechanism_coverage=self._valid_mechanism_coverage(),
                    quality_gate=quality_gate,
                )

                warnings = self._schema_warnings(MODULE.lint_plan(plan_path))

            self.assertTrue(any(mode in finding.message for finding in warnings), warnings)


class PlanLintDecompositionGraphShapeTests(unittest.TestCase):
    def setUp(self) -> None:
        MODULE.load_and_apply_plan_vocab(MODULE.PLAN_VOCAB_PATH)

    def _write_child(
        self,
        root: Path,
        child_path: str,
        *,
        child_paths: list[str] | None = None,
        active: bool = False,
    ) -> None:
        path = root / child_path
        path.parent.mkdir(parents=True, exist_ok=True)
        phase_overlay = '"decomposition_wave"' if active else "null"
        phase_state = '"active"' if active else "null"
        next_plans = child_paths or []
        execution_queue = ""
        if next_plans:
            execution_queue = "\n## Execution queue\n" + "\n".join(f"- Plan: `{child}`" for child in next_plans)
        path.write_text(
            dedent(
                f"""\
                # Plan: child fixture

                **Date:** 2026-05-01 00:00 MSK
                **Stage:** Stage 1
                **Priority:** P2
                **Plan type:** dev
                **Status:** Architect draft
                **Schema version:** plan.v1

                ## Meta (machine-readable JSON; required for new plans)
                ```json
                {{
                  "plan_meta": {{
                    "cluster": "process",
                    "tags": [],
                    "wave_family": null,
                    "phase_overlay": {phase_overlay},
                    "phase_state": {phase_state},
                    "parent": null,
                    "next_plans": {json.dumps(next_plans)},
                    "depends_on": [],
                    "followups_out": [],
                    "canon_updates": []
                  }}
                }}
                ```
                {execution_queue}
                """
            ),
            encoding="utf-8",
        )

    def _write_fixture(
        self,
        root: Path,
        *,
        plan_stem: str,
        child_paths: list[str],
        reason_lines: str = "",
        phase_state: str = "active",
        include_placeholder_child: bool = False,
    ) -> Path:
        (root / ".git").mkdir(exist_ok=True)
        ensure_fixture_git(root)
        plan_path = root / "docs" / "plans" / f"{plan_stem}.md"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        for child_path in child_paths:
            if not (root / child_path).exists():
                self._write_child(root, child_path)

        child_rows = "\n".join(
            f"| {idx} | `{child}` | child fixture |"
            for idx, child in enumerate(child_paths, start=1)
        )
        queue_rows = "\n".join(f"- Plan: `{child}`" for child in child_paths)
        next_plans_json = json.dumps(child_paths)
        if include_placeholder_child:
            child_rows = "| 1 | `N/A (why=fixture child graph not ready)` | pending child |"
            queue_rows = "- Plan: `N/A (why=fixture child graph not ready)`"
            next_plans_json = "[]"

        plan_path.write_text(
            dedent(
                f"""\
                # Plan: decomposition graph shape fixture

                **Date:** 2026-06-19 00:31 MSK
                **Stage:** Stage 2
                **Priority:** P1
                **Plan type:** dev
                **Status:** Architect draft
                **Schema version:** plan.v1

                ## Meta (machine-readable JSON; required for new plans)
                ```json
                {{
                  "plan_meta": {{
                    "cluster": "process",
                    "tags": [],
                    "wave_family": null,
                    "phase_overlay": "decomposition_wave",
                    "phase_state": "{phase_state}",
                    "parent": null,
                    "next_plans": {next_plans_json},
                    "depends_on": [],
                    "followups_out": [],
                    "canon_updates": []
                  }}
                }}
                ```

                ## Documentation impact / provenance
                - Source docs used: fixture.
                - Synchronous doc/registry targets: `docs/playbooks/decomposition_wave.md`.
                - Post-merge canon updates: `N/A (why=fixture)`.
                - Deferred documentation follow-ups: `N/A (why=fixture)`.
                - Provenance refs: fixture.

                ## Decisions (final)
                - Fixture.

                {reason_lines}

                ### UI/HTMX playbooks (micro-block; required for UI/HTMX tasks)
                - Archetype: `N/A (why=process helper fixture)`
                - Modules: `N/A (why=process helper fixture)`
                - Primary CTA: `N/A (why=process helper fixture)`
                - header_filters: `N/A (why=process helper fixture)`
                - Results count strategy: `N/A (why=process helper fixture)`

                ## Rollout packet handoff
                - Role: `N/A (why=fixture)`
                - Packet path: `N/A (why=fixture)`
                - Target repo: `N/A (why=fixture)`
                - Suggested target plan slug: `N/A (why=fixture)`
                - Queue after import: `N/A (why=fixture)`

                ## Close-out routing
                - Roadmap/queue sync: fixture.
                - Follow-up sync: `N/A (why=fixture)`
                - Next bounded slice: `N/A (why=fixture)`
                - Terminal outcome: no (fixture).

                ## Decomposition quality gate
                - Solvability: `N/A (why=fixture)`
                - Completeness: `N/A (why=fixture)`
                - Non-redundancy: `N/A (why=fixture)`
                - Mutable surface / runtime isolation: `N/A (why=fixture)`
                - Recomposition / integration owner: `N/A (why=fixture)`

                ## Mechanism coverage
                | Mechanism | Usage | Source refs | Proof anchor | State | Promoted child impact |
                | --- | --- | --- | --- | --- | --- |
                | golden-path | selected planning contour | `docs/guides/golden_paths.md#planning-contour-continuity` | `docs/guides/golden_paths.md#planning-contour-continuity` | used | child plans inherit source refs |

                ## Child plan map
                | Queue order | Plan | Summary |
                | --- | --- | --- |
                {child_rows}

                ## Execution queue
                {queue_rows}

                ## Changes (by area)
                - Services/selectors: `scripts/plan_lint.py`.

                ## Tests
                - `python3 scripts/test_plan_lint.py`

                ## Commands
                - `python3 scripts/test_plan_lint.py`
                """
            ),
            encoding="utf-8",
        )
        return plan_path

    def _graph_warnings(self, findings: list[object]) -> list[object]:
        return [
            finding
            for finding in findings
            if MODULE.DECOMPOSITION_GRAPH_SHAPE_WARNING_PREFIX in finding.message
        ]

    def test_zero_child_active_decomposition_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260619_0031_process_graph_zero_child",
                child_paths=[],
                include_placeholder_child=True,
            )

            warnings = self._graph_warnings(MODULE.lint_plan(plan_path))

        self.assertTrue(any("0 materialized child" in finding.message for finding in warnings), warnings)

    def test_zero_child_with_sizing_rationale_does_not_warn(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260619_0031_process_graph_zero_child_reason",
                child_paths=[],
                include_placeholder_child=True,
                reason_lines="- Decomposition sizing rationale: staged child materialization remains parked for owner review.",
            )

            warnings = self._graph_warnings(MODULE.lint_plan(plan_path))

        self.assertFalse(any("0 materialized child" in finding.message for finding in warnings), warnings)

    def test_one_child_without_parent_reference_reason_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            child = "docs/plans/260501_0001_graph_child_one.md"
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260619_0031_process_graph_one_child",
                child_paths=[child],
            )

            warnings = self._graph_warnings(MODULE.lint_plan(plan_path))

        self.assertTrue(any("1-child decomposition umbrella" in finding.message for finding in warnings), warnings)

    def test_one_child_with_parent_reference_reason_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            child = "docs/plans/260501_0002_graph_child_one_reason.md"
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260619_0031_process_graph_one_child_reason",
                child_paths=[child],
                reason_lines="- Parent reference reason: parent keeps recomposition proof and shared review owner.",
            )

            warnings = self._graph_warnings(MODULE.lint_plan(plan_path))

        self.assertFalse(any("1-child decomposition umbrella" in finding.message for finding in warnings), warnings)

    def test_large_child_count_warns_and_reason_allows_override(self) -> None:
        child_paths = [f"docs/plans/260501_{idx:04d}_graph_large_child.md" for idx in range(10)]
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            warned_plan = self._write_fixture(
                root,
                plan_stem="260619_0031_process_graph_large_child_count",
                child_paths=child_paths,
            )
            warning_messages = [finding.message for finding in self._graph_warnings(MODULE.lint_plan(warned_plan))]
            reason_plan = self._write_fixture(
                root,
                plan_stem="260619_0031_process_graph_large_child_count_reason",
                child_paths=child_paths,
                reason_lines="- Large child count reason: deliberate full decomposition keeps independent review lanes.",
            )
            reason_messages = [finding.message for finding in self._graph_warnings(MODULE.lint_plan(reason_plan))]

        self.assertTrue(any("large decomposition child count" in message for message in warning_messages), warning_messages)
        self.assertFalse(any("large decomposition child count" in message for message in reason_messages), reason_messages)

    def test_depth_greater_than_four_warns_and_reason_allows_override(self) -> None:
        chain = [f"docs/plans/260501_01{idx:02d}_graph_depth_child.md" for idx in range(1, 5)]
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            for idx, child in enumerate(chain):
                next_children = [chain[idx + 1]] if idx + 1 < len(chain) else []
                self._write_child(root, child, child_paths=next_children, active=bool(next_children))
            warned_plan = self._write_fixture(
                root,
                plan_stem="260619_0031_process_graph_depth",
                child_paths=[chain[0]],
            )
            warning_messages = [finding.message for finding in self._graph_warnings(MODULE.lint_plan(warned_plan))]
            reason_plan = self._write_fixture(
                root,
                plan_stem="260619_0031_process_graph_depth_reason",
                child_paths=[chain[0]],
                reason_lines="- Depth override reason: depth is serialized across child reviews and intentionally parked.",
            )
            reason_messages = [finding.message for finding in self._graph_warnings(MODULE.lint_plan(reason_plan))]

        self.assertTrue(any("recursion depth" in message for message in warning_messages), warning_messages)
        self.assertFalse(any("recursion depth" in message for message in reason_messages), reason_messages)

    def test_cumulative_complexity_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            children = [f"docs/plans/260501_02{idx:02d}_graph_cumulative_child.md" for idx in range(5)]
            for idx, child in enumerate(children):
                grandchildren = [
                    f"docs/plans/260501_03{idx}{subidx}_graph_cumulative_grandchild.md"
                    for subidx in range(3)
                ]
                for grandchild in grandchildren:
                    self._write_child(root, grandchild)
                self._write_child(root, child, child_paths=grandchildren, active=True)
            plan_path = self._write_fixture(
                root,
                plan_stem="260619_0031_process_graph_cumulative",
                child_paths=children,
            )

            warnings = self._graph_warnings(MODULE.lint_plan(plan_path))

        self.assertTrue(any("cumulative decomposition complexity" in finding.message for finding in warnings), warnings)

    def test_parked_decomposition_skips_graph_shape_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                plan_stem="260619_0031_process_graph_parked",
                child_paths=[],
                phase_state="parked",
                include_placeholder_child=True,
            )

            warnings = self._graph_warnings(MODULE.lint_plan(plan_path))

        self.assertEqual(warnings, [])


class PlanLintDecompositionChildMaterializationTests(unittest.TestCase):
    def setUp(self) -> None:
        MODULE.load_and_apply_plan_vocab(MODULE.PLAN_VOCAB_PATH)

    def _write_active_decomposition_fixture(self, root: Path) -> Path:
        (root / ".git").mkdir()
        ensure_fixture_git(root)
        plan_path = root / "docs" / "plans" / "260517_1623_active_decomposition_missing_child.md"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(
            dedent(
                """\
                # Plan: active decomposition missing child

                **Date:** 2026-05-17 16:23 MSK
                **Stage:** Stage 1
                **Priority:** P1
                **Plan type:** dev
                **Status:** Architect draft
                **Schema version:** plan.v1

                ## Meta (machine-readable JSON; required for new plans)
                ```json
                {
                  "plan_meta": {
                    "cluster": "process",
                    "tags": [],
                    "phase_overlay": "decomposition_wave",
                    "phase_state": "active",
                    "parent": null,
                    "next_plans": [],
                    "depends_on": [],
                    "followups_out": [],
                    "canon_updates": []
                  }
                }
                ```

                ## Documentation impact / provenance
                - Source docs used: fixture.
                - Synchronous doc/registry targets: `docs/plans/README.md`.
                - Post-merge canon updates: `N/A (why=fixture)`.
                - Deferred documentation follow-ups: `N/A (why=fixture)`.
                - Provenance refs: fixture.

                ## Decisions (final)

                - Fixture keeps promoted child materialization explicit.

                ## Rollout packet handoff
                - Role: `N/A (why=fixture)`
                - Packet path: `N/A (why=fixture)`
                - Target repo: `N/A (why=fixture)`
                - Suggested target plan slug: `N/A (why=fixture)`
                - Queue after import: `N/A (why=fixture)`

                ## Close-out routing
                - Roadmap/queue sync: fixture.
                - Follow-up sync: `N/A (why=fixture)`
                - Next bounded slice: `N/A (why=fixture)`
                - Terminal outcome: no (fixture).

                ## Mechanism coverage
                - `Mechanism:` decomposition child-state helper gate
                - `Usage:` fixture.
                - `State:` planned
                - `Promoted child impact:` explicit child paths are required.

                ## Child plan map
                | Queue order | Plan | Summary |
                | --- | --- | --- |
                | 1 | `TBD` | missing child |

                ## Execution queue
                - Resume parent: `owner-restamp-required`
                - Plan: `TBD`

                ## Verification rerun / exec handoff
                - Mode: fresh-exec
                - Context source: fixture.
                - Prompt: fixture.
                - Command: `python3 scripts/test_plan_lint.py`
                - Expected artifact: deterministic lint finding.
                """
            ),
            encoding="utf-8",
        )
        return plan_path

    def test_active_decomposition_tbd_child_path_gets_deterministic_finding(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_active_decomposition_fixture(Path(tmpdir))

            findings = MODULE.lint_plan(plan_path)

        messages = [finding.message for finding in findings]
        self.assertTrue(
            any(
                "decomposition_children_missing" in message
                and "decomposition_child_placeholder" in message
                and "TBD" in message
                for message in messages
            ),
            messages,
        )

    def test_early_intake_active_decomposition_without_queue_carrier_is_non_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            ensure_fixture_git(root)
            plan_path = root / "docs" / "plans" / "260517_1624_active_decomposition_early_intake.md"
            plan_path.parent.mkdir(parents=True, exist_ok=True)
            plan_path.write_text(
                dedent(
                    """\
                    # Plan: active decomposition early intake

                    **Date:** 2026-05-17 16:24 MSK
                    **Stage:** Stage 1
                    **Priority:** P1
                    **Plan type:** dev
                    **Status:** Architect draft
                    **Schema version:** plan.v1

                    ## Meta (machine-readable JSON; required for new plans)
                    ```json
                    {
                      "plan_meta": {
                        "cluster": "process",
                        "tags": [],
                        "phase_overlay": "decomposition_wave",
                        "phase_state": "active",
                        "parent": null,
                        "next_plans": [],
                        "depends_on": [],
                        "followups_out": [],
                        "canon_updates": []
                      }
                    }
                    ```

                    ## Documentation impact / provenance
                    - Source docs used: fixture.
                    - Synchronous doc/registry targets: `docs/plans/README.md`.
                    - Post-merge canon updates: `N/A (why=fixture)`.
                    - Deferred documentation follow-ups: `N/A (why=fixture)`.
                    - Provenance refs: fixture.

                    ## Decisions (final)

                    - Fixture keeps early decomposition intake non-blocking.

                    ## Rollout packet handoff
                    - Role: `N/A (why=fixture)`
                    - Packet path: `N/A (why=fixture)`
                    - Target repo: `N/A (why=fixture)`
                    - Suggested target plan slug: `N/A (why=fixture)`
                    - Queue after import: `N/A (why=fixture)`

                    ## Close-out routing
                    - Roadmap/queue sync: fixture.
                    - Follow-up sync: `N/A (why=fixture)`
                    - Next bounded slice: `N/A (why=fixture)`
                    - Terminal outcome: no (fixture).

                    ## Mechanism coverage
                    - `Mechanism:` decomposition child-state helper gate
                    - `Usage:` fixture.
                    - `State:` planned
                    - `Promoted child impact:` explicit child paths are required before queue import.

                    ## Child plan map
                    | Queue order | Plan | Summary |
                    | --- | --- | --- |
                    | 1 | `TBD (why=Owner questions are still open)` | pending child |

                    ## Execution queue
                    - Resume parent: `owner-restamp-required`
                    - `N/A (why=child graph not ready during early intake)`

                    ## Verification rerun / exec handoff
                    - Mode: fresh-exec
                    - Context source: fixture.
                    - Prompt: fixture.
                    - Command: `python3 scripts/test_plan_lint.py`
                    - Expected artifact: no decomposition child materialization lint error.
                    """
                ),
                encoding="utf-8",
            )

            findings = MODULE.lint_plan(plan_path)

        messages = [finding.message for finding in findings]
        self.assertFalse(any("decomposition_children_missing" in message for message in messages), messages)

    def test_early_intake_active_decomposition_na_queue_entry_is_non_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            ensure_fixture_git(root)
            plan_path = root / "docs" / "plans" / "260517_1624_active_decomposition_early_intake_na_queue.md"
            plan_path.parent.mkdir(parents=True, exist_ok=True)
            plan_path.write_text(
                dedent(
                    """\
                    # Plan: active decomposition early intake with explanatory queue row

                    **Date:** 2026-05-17 16:24 MSK
                    **Stage:** Stage 1
                    **Priority:** P1
                    **Plan type:** dev
                    **Status:** Architect draft
                    **Schema version:** plan.v1

                    ## Meta (machine-readable JSON; required for new plans)
                    ```json
                    {
                      "plan_meta": {
                        "cluster": "process",
                        "tags": [],
                        "phase_overlay": "decomposition_wave",
                        "phase_state": "active",
                        "parent": null,
                        "next_plans": [],
                        "depends_on": [],
                        "followups_out": [],
                        "canon_updates": []
                      }
                    }
                    ```

                    ## Documentation impact / provenance
                    - Source docs used: fixture.
                    - Synchronous doc/registry targets: `docs/plans/README.md`.
                    - Post-merge canon updates: `N/A (why=fixture)`.
                    - Deferred documentation follow-ups: `N/A (why=fixture)`.
                    - Provenance refs: fixture.

                    ## Decisions (final)

                    - Fixture keeps early decomposition intake non-blocking when queue row is explanatory.

                    ## Rollout packet handoff
                    - Role: `N/A (why=fixture)`
                    - Packet path: `N/A (why=fixture)`
                    - Target repo: `N/A (why=fixture)`
                    - Suggested target plan slug: `N/A (why=fixture)`
                    - Queue after import: `N/A (why=fixture)`

                    ## Close-out routing
                    - Roadmap/queue sync: fixture.
                    - Follow-up sync: `N/A (why=fixture)`
                    - Next bounded slice: `N/A (why=fixture)`
                    - Terminal outcome: no (fixture).

                    ## Mechanism coverage
                    - `Mechanism:` decomposition child-state helper gate
                    - `Usage:` fixture.
                    - `State:` planned
                    - `Promoted child impact:` explicit child paths are required before queue import.

                    ## Child plan map
                    | Queue order | Plan | Summary |
                    | --- | --- | --- |
                    | 1 | `TBD (why=Owner questions are still open)` | pending child |

                    ## Execution queue
                    - Resume parent: `owner-restamp-required`
                    - Plan: `N/A (why=child graph not ready during early intake)`

                    ## Verification rerun / exec handoff
                    - Mode: fresh-exec
                    - Context source: fixture.
                    - Prompt: fixture.
                    - Command: `python3 scripts/test_plan_lint.py`
                    - Expected artifact: no decomposition child materialization lint error.
                    """
                ),
                encoding="utf-8",
            )

            findings = MODULE.lint_plan(plan_path)

        messages = [finding.message for finding in findings]
        self.assertFalse(any("decomposition_children_missing" in message for message in messages), messages)

    def test_active_decomposition_allows_full_queue_with_bounded_next_plans(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            ensure_fixture_git(root)
            plan_path = root / "docs" / "plans" / "260517_1625_active_decomposition_bounded_next.md"
            child_paths = [
                "docs/plans/260517_1640_child_a.md",
                "docs/plans/260517_1641_child_b.md",
                "docs/plans/260517_1642_child_c.md",
                "docs/plans/260517_1643_child_d.md",
                "docs/plans/260517_1644_child_e.md",
            ]
            for rel_path in child_paths:
                child_path = root / rel_path
                child_path.parent.mkdir(parents=True, exist_ok=True)
                child_path.write_text(
                    dedent(
                        """\
                        # Plan: child fixture

                        **Date:** 2026-05-17 16:40 MSK
                        **Stage:** Stage 1
                        **Priority:** P1
                        **Plan type:** dev
                        **Status:** Ready for Coder
                        **Schema version:** plan.v1
                        """
                    ),
                    encoding="utf-8",
                )
            next_plans_json = json.dumps(child_paths[:2], indent=8)
            child_map_rows = "\n".join(
                f"| {idx} | `{rel_path}` | child {idx} |"
                for idx, rel_path in enumerate(child_paths, start=1)
            )
            execution_rows = "\n".join(f"- Plan: `{rel_path}`" for rel_path in child_paths)
            plan_path.parent.mkdir(parents=True, exist_ok=True)
            plan_path.write_text(
                dedent(
                    f"""\
                    # Plan: active decomposition bounded next

                    **Date:** 2026-05-17 16:25 MSK
                    **Stage:** Stage 1
                    **Priority:** P1
                    **Plan type:** dev
                    **Status:** Architect draft
                    **Schema version:** plan.v1

                    ## Meta (machine-readable JSON; required for new plans)
                    ```json
                    {{
                      "plan_meta": {{
                        "cluster": "process",
                        "tags": [],
                        "phase_overlay": "decomposition_wave",
                        "phase_state": "active",
                        "parent": null,
                        "next_plans": {next_plans_json},
                        "depends_on": [],
                        "followups_out": [],
                        "canon_updates": []
                      }}
                    }}
                    ```

                    ## Documentation impact / provenance
                    - Source docs used: fixture.
                    - Synchronous doc/registry targets: `docs/plans/README.md`.
                    - Post-merge canon updates: `N/A (why=fixture)`.
                    - Deferred documentation follow-ups: `N/A (why=fixture)`.
                    - Provenance refs: fixture.

                    ## Decisions (final)

                    - Full execution queue can be longer than bounded direct next pointers.

                    ## Rollout packet handoff
                    - Role: `N/A (why=fixture)`
                    - Packet path: `N/A (why=fixture)`
                    - Target repo: `N/A (why=fixture)`
                    - Suggested target plan slug: `N/A (why=fixture)`
                    - Queue after import: `N/A (why=fixture)`

                    ## Close-out routing
                    - Roadmap/queue sync: fixture.
                    - Follow-up sync: `N/A (why=fixture)`
                    - Next bounded slice: `N/A (why=fixture)`
                    - Terminal outcome: yes (fixture).

                    ## Mechanism coverage
                    - `Mechanism:` decomposition child-state helper gate
                    - `Usage:` fixture.
                    - `State:` planned
                    - `Promoted child impact:` full queue is separate from bounded direct next pointers.

                    ## Child plan map
                    | Queue order | Plan | Summary |
                    | --- | --- | --- |
{child_map_rows}

                    ## Execution queue
                    - Resume parent: `run-parent-once`
{execution_rows}

                    ## Verification rerun / exec handoff
                    - Mode: fresh-exec
                    - Context source: fixture.
                    - Prompt: fixture.
                    - Command: `python3 scripts/test_plan_lint.py`
                    - Expected artifact: no decomposition mismatch finding.
                    """
                ),
                encoding="utf-8",
            )

            findings = MODULE.lint_plan(plan_path)

        messages = [finding.message for finding in findings]
        self.assertFalse(any("decomposition_child_graph_mismatch" in message for message in messages), messages)
        self.assertFalse(any("execution_queue vs next_plans" in message for message in messages), messages)
        self.assertFalse(any("decomposition_children_missing" in message for message in messages), messages)

    def _small_model_contract(self, *, omit: set[str] | None = None, overrides: dict[str, str] | None = None) -> str:
        omit = omit or set()
        overrides = overrides or {}
        fields = [
            ("Task outcome", "fixture child produces one observable helper result"),
            ("Local context bundle", "`docs/plans/parent.md`, `docs/playbooks/decomposition_wave.md`"),
            ("Mutable surfaces", "`scripts/fixture.py`, `scripts/test_fixture.py`"),
            ("Read-only surfaces", "`docs/playbooks/decomposition_wave.md`"),
            ("Forbidden scope", "model defaults and external runner wrappers"),
            ("Inputs from parent/predecessor", "`docs/plans/parent.md` queue row and predecessor artifact"),
            ("Output to consumer", "`docs/plans/child.md` status/evidence for Reviewer"),
            ("Acceptance/proof lane", "`python -m unittest scripts.test_plan_lint`"),
            ("Stop condition", "return to Planner if new helper CLI semantics are needed"),
            ("Expected reviewer lane", "code"),
            ("Runner suitability", "small runner OK; fallback to Coder if target bundle expands"),
            ("Task size/complexity", "small; one helper family and focused tests"),
            ("Readiness notes", "no known clarity gaps"),
        ]
        rows = [
            "## Small-model-ready child contract",
            "| Field | Value |",
            "| --- | --- |",
        ]
        for field, value in fields:
            if field in omit:
                continue
            rows.append(f"| {field} | {overrides.get(field, value)} |")
        return "\n".join(rows)

    def _write_active_decomposition_with_small_model_child(
        self,
        root: Path,
        *,
        contract: str,
        child_name: str = "260611_2101_child_ready.md",
    ) -> Path:
        (root / ".git").mkdir()
        ensure_fixture_git(root)
        child_rel = f"docs/plans/{child_name}"
        child_path = root / child_rel
        child_path.parent.mkdir(parents=True, exist_ok=True)
        child_path.write_text(
            dedent(
                f"""\
                # Plan: small model child fixture

                **Date:** 2026-06-11 21:01 MSK
                **Stage:** Stage 1
                **Priority:** P1
                **Plan type:** dev
                **Status:** Ready for Coder
                **Schema version:** plan.v1

                {contract}
                """
            ),
            encoding="utf-8",
        )
        parent = root / "docs" / "plans" / "260611_2100_active_decomposition_small_model_ready.md"
        parent.write_text(
            dedent(
                f"""\
                # Plan: active decomposition small model ready

                **Date:** 2026-06-11 21:00 MSK
                **Stage:** Stage 1
                **Priority:** P1
                **Plan type:** dev
                **Status:** Architect draft
                **Schema version:** plan.v1

                ## Meta (machine-readable JSON; required for new plans)
                ```json
                {{
                  "plan_meta": {{
                    "cluster": "process",
                    "tags": [],
                    "phase_overlay": "decomposition_wave",
                    "phase_state": "active",
                    "parent": null,
                    "next_plans": ["{child_rel}"],
                    "depends_on": [],
                    "followups_out": [],
                    "canon_updates": []
                  }}
                }}
                ```

                ## Documentation impact / provenance
                - Source docs used: fixture.
                - Synchronous doc/registry targets: `docs/plans/README.md`.
                - Post-merge canon updates: `N/A (why=fixture)`.
                - Deferred documentation follow-ups: `N/A (why=fixture)`.
                - Provenance refs: fixture.

                ## Rollout packet handoff
                - Role: `N/A (why=fixture)`
                - Packet path: `N/A (why=fixture)`
                - Target repo: `N/A (why=fixture)`
                - Suggested target plan slug: `N/A (why=fixture)`
                - Queue after import: `N/A (why=fixture)`

                ## Close-out routing
                - Roadmap/queue sync: fixture.
                - Follow-up sync: `N/A (why=fixture)`
                - Next bounded slice: `N/A (why=fixture)`
                - Terminal outcome: yes (fixture).

                ## Mechanism coverage
                - `Mechanism:` decomposition child-state helper gate
                - `Usage:` fixture.
                - `State:` planned
                - `Promoted child impact:` child readiness fields are required.

                ## Child plan map
                | Queue order | Plan | Summary |
                | --- | --- | --- |
                | 1 | `{child_rel}` | ready child |

                ## Execution queue
                - Resume parent: `run-parent-once`
                - Plan: `{child_rel}`

                ## Verification rerun / exec handoff
                - Mode: fresh-exec
                - Context source: fixture.
                - Prompt: fixture.
                - Command: `python3 scripts/test_plan_lint.py`
                - Expected artifact: small-model readiness finding.
                """
            ),
            encoding="utf-8",
        )
        return parent

    def test_active_decomposition_complete_small_model_child_has_no_readiness_finding(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_active_decomposition_with_small_model_child(
                Path(tmpdir),
                contract=self._small_model_contract(),
            )

            findings = MODULE.lint_plan(plan_path)

        messages = [finding.message for finding in findings]
        self.assertFalse(any("small_model_ready_child" in message for message in messages), messages)

    def test_active_decomposition_missing_objective_child_field_hard_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_active_decomposition_with_small_model_child(
                Path(tmpdir),
                contract=self._small_model_contract(omit={"Local context bundle"}),
            )

            findings = MODULE.lint_plan(plan_path)

        blockers = [
            finding
            for finding in findings
            if finding.severity == "ERROR" and "small_model_ready_child" in finding.message
        ]
        self.assertTrue(any("Local context bundle" in finding.message for finding in blockers), blockers)

    def test_active_decomposition_placeholder_and_vague_child_fields_hard_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_active_decomposition_with_small_model_child(
                Path(tmpdir),
                contract=self._small_model_contract(
                    overrides={
                        "Mutable surfaces": "TBD",
                        "Stop condition": "см. parent",
                    }
                ),
            )

            findings = MODULE.lint_plan(plan_path)

        blockers = [
            finding.message
            for finding in findings
            if finding.severity == "ERROR" and "small_model_ready_child" in finding.message
        ]
        self.assertTrue(any("Mutable surfaces: placeholder" in message for message in blockers), blockers)
        self.assertTrue(any("Stop condition: vague" in message for message in blockers), blockers)

    def test_active_decomposition_template_angle_placeholder_child_fields_hard_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_active_decomposition_with_small_model_child(
                Path(tmpdir),
                contract=self._small_model_contract(
                    overrides={
                        "Task outcome": "<one observable result>",
                        "Mutable surfaces": "<exact paths/path families allowed to change>",
                        "Acceptance/proof lane": "<exact commands/checks/receipts/review lane>",
                    }
                ),
            )

            findings = MODULE.lint_plan(plan_path)

        blockers = [
            finding.message
            for finding in findings
            if finding.severity == "ERROR" and "small_model_ready_child" in finding.message
        ]
        self.assertTrue(any("Task outcome: placeholder" in message for message in blockers), blockers)
        self.assertTrue(any("Mutable surfaces: placeholder" in message for message in blockers), blockers)
        self.assertTrue(any("Acceptance/proof lane: placeholder" in message for message in blockers), blockers)

    def test_active_decomposition_warning_first_fields_do_not_block_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_active_decomposition_with_small_model_child(
                Path(tmpdir),
                contract=self._small_model_contract(omit={"Runner suitability"}),
            )

            findings = MODULE.lint_plan(plan_path)

        readiness_findings = [finding for finding in findings if "small_model_ready_child" in finding.message]
        self.assertTrue(any(finding.severity == "WARN" for finding in readiness_findings), readiness_findings)
        self.assertFalse(any(finding.severity == "ERROR" for finding in readiness_findings), readiness_findings)

    def _write_materialization_corridor_fixture(
        self,
        root: Path,
        *,
        status: str,
        child_map_rows: str = "- `N/A (why=Coder assigns paths after child files exist)`",
        execution_queue_rows: str = "- Resume parent: `N/A (why=fixture)`\n- Plan: `N/A (why=child graph is not materialized)`",
        next_plans: list[str] | None = None,
        qna_rows: str = "- NO QUESTIONS (fixture).",
        child_files: dict[str, str] | None = None,
        strict_na_parent: bool = False,
        phase_state: str = "active",
    ) -> Path:
        (root / ".git").mkdir(exist_ok=True)
        ensure_fixture_git(root)
        for rel_path, child_text in (child_files or {}).items():
            child_path = root / rel_path
            child_path.parent.mkdir(parents=True, exist_ok=True)
            child_path.write_text(child_text, encoding="utf-8")

        plan_path = root / "docs" / "plans" / "260822_1727_materialization_corridor_fixture.md"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        meta = {
            "cluster": "process",
            "tags": [],
            "phase_overlay": "decomposition_wave",
            "phase_state": phase_state,
            "parent": None,
            "next_plans": next_plans if next_plans is not None else [],
            "depends_on": [],
            "followups_out": [],
            "canon_updates": [],
        }
        context_lines = ["**Context links (source of truth):", "- Fixture: `scripts/plan_lint.py`"]
        if strict_na_parent:
            meta["machine_authority_decision"] = {
                "schema_version": "machine_authority_decision.v1",
                "applicability": "not_applicable",
                "reason_code": "no_machine_authority_change",
            }
            context_lines = [
                "**Context links (source of truth):",
                "- Code draft(s): `N/A (why=strict decomposition parent fixture)`.",
            ]
        lines = [
            "# Plan: materialization corridor fixture",
            "",
            "**Date:** 2026-08-22 17:27 MSK",
            "**Stage:** Stage 1",
            "**Priority:** P1",
            "**Plan type:** dev",
            f"**Status:** {status}",
            "**Schema version:** plan.v1",
            "",
            *context_lines,
            "",
            "## Meta (machine-readable JSON; required for new plans)",
            "```json",
            json.dumps({"plan_meta": meta}, ensure_ascii=False, indent=2),
            "```",
            "",
            "## Documentation impact / provenance",
            "- Source docs used: fixture.",
            "- Synchronous doc/registry targets: `docs/plans/README.md`.",
            "- Post-merge canon updates: `N/A (why=fixture)`.",
            "- Deferred documentation follow-ups: `N/A (why=fixture)`.",
            "- Provenance refs: fixture.",
            "",
            "## Decisions (final)",
            "- Fixture keeps the candidate contour distinct from a child graph.",
            "",
            "## Close-out routing",
            "- Roadmap/queue sync: `N/A (why=fixture)`.",
            "- Follow-up sync: `N/A (why=fixture)`.",
            "- Next bounded slice: `N/A (why=fixture)`.",
            "- Terminal outcome: no (fixture).",
            "",
            "## Mechanism coverage",
            "- `Mechanism:` decomposition child-state helper gate.",
            "- `Usage:` fixture.",
            "- `State:` planned.",
            "- `Promoted child impact:` fixture remains planning-only.",
            "",
            "## Decomposition quality gate",
            "- `Solvability:` fixture.",
            "",
            "## Child plan map",
            *child_map_rows.splitlines(),
            "",
            "## Candidate child contours",
            "| Slug | Purpose |",
            "| --- | --- |",
            "| candidate-a | semantic input only |",
            "",
            "## Execution queue",
            *execution_queue_rows.splitlines(),
            "",
            "## Q&A log",
            "### Architect Q&A",
            *qna_rows.splitlines(),
            "",
            "## Verification rerun / exec handoff",
            "- Mode: fresh-exec",
            "- Context source: fixture.",
            "- Prompt: fixture.",
            "- Command: `python3 scripts/test_plan_lint.py`.",
            "- Expected artifact: deterministic materialization finding.",
        ]
        plan_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return plan_path

    @staticmethod
    def _materialization_messages(findings: list[object]) -> list[str]:
        return [
            finding.message
            for finding in findings
            if "decomposition_children_missing" in finding.message
        ]

    def test_strict_materialization_corridor_is_status_and_shape_bound(self) -> None:
        admitted_statuses = (
            "Planner finalize",
            "Ready for Coder",
            "Coder intake",
            "In progress",
            "Ready for Architect response",
            "Architect response",
        )
        for status in admitted_statuses:
            with self.subTest(status=status):
                with tempfile.TemporaryDirectory() as tmpdir:
                    findings = MODULE.lint_plan(
                        self._write_materialization_corridor_fixture(Path(tmpdir), status=status)
                    )
                self.assertEqual(self._materialization_messages(findings), [], findings)

        for status in ("Ready for Review", "Reviewer intake", "Ready for Arch review", "Done"):
            with self.subTest(status=status):
                with tempfile.TemporaryDirectory() as tmpdir:
                    findings = MODULE.lint_plan(
                        self._write_materialization_corridor_fixture(Path(tmpdir), status=status)
                    )
                self.assertTrue(self._materialization_messages(findings), findings)

    def test_strict_materialization_corridor_keeps_qna_hygiene_independent(self) -> None:
        cases = {
            "open": (
                "- [2026-08-22 22:00 MSK] (Architect -> Owner, id=Q1, blocker=yes, needs_owner=yes, status=open) "
                "Q: Confirm fixture?",
                "Q&A item Q1 is still open",
            ),
            "malformed": (
                "- [2026-08-22 22:00 MSK] (Architect -> Owner, id=Q2, blocker=yes, needs_owner=yes) "
                "Q: Confirm fixture?",
                "Owner Q&A line is missing status=open|closed|superseded",
            ),
        }
        for name, (qna_rows, expected_message) in cases.items():
            with self.subTest(case=name):
                with tempfile.TemporaryDirectory() as tmpdir:
                    findings = MODULE.lint_plan(
                        self._write_materialization_corridor_fixture(
                            Path(tmpdir),
                            status="Ready for Architect response",
                            qna_rows=qna_rows,
                        )
                    )
                self.assertEqual(self._materialization_messages(findings), [], findings)
                self.assertTrue(any(expected_message in finding.message for finding in findings), findings)

    def test_strict_materialization_corridor_rejects_named_or_partial_graphs(self) -> None:
        concrete_path = "docs/plans/260822_1728_child_fixture.md"
        cases = {
            "tbd": {
                "child_map_rows": "| Queue order | Plan | Summary |\n| --- | --- | --- |\n| 1 | `TBD` | pending |",
            },
            "named_na": {
                "child_map_rows": (
                    "| Queue order | Plan | Summary |\n| --- | --- | --- |\n"
                    "| 1 | `N/A (why=child not assigned)` | pending |"
                ),
            },
            "partial_linkage": {
                "child_map_rows": (
                    "| Queue order | Plan | Summary |\n| --- | --- | --- |\n"
                    f"| 1 | `{concrete_path}` | partial |"
                ),
            },
            "missing_child": {
                "child_map_rows": (
                    "| Queue order | Plan | Summary |\n| --- | --- | --- |\n"
                    f"| 1 | `{concrete_path}` | missing |"
                ),
                "execution_queue_rows": f"- Plan: `{concrete_path}`",
            },
            "nonlintable_child": {
                "child_map_rows": (
                    "| Queue order | Plan | Summary |\n| --- | --- | --- |\n"
                    f"| 1 | `{concrete_path}` | malformed child |"
                ),
                "execution_queue_rows": f"- Plan: `{concrete_path}`",
                "child_files": {
                    concrete_path: "# Not a lintable child plan\n\nThis fixture lacks the required status header.\n"
                },
            },
            "carrier_mismatch": {
                "child_map_rows": (
                    "| Queue order | Plan | Summary |\n| --- | --- | --- |\n"
                    f"| 1 | `{concrete_path}` | map child |"
                ),
                "execution_queue_rows": "- Plan: `docs/plans/260822_1729_other_child_fixture.md`",
            },
            "queue_entry": {
                "execution_queue_rows": f"- Plan: `{concrete_path}`",
            },
            "next_plans": {
                "next_plans": [concrete_path],
            },
        }
        for name, kwargs in cases.items():
            with self.subTest(case=name):
                with tempfile.TemporaryDirectory() as tmpdir:
                    findings = MODULE.lint_plan(
                        self._write_materialization_corridor_fixture(
                            Path(tmpdir),
                            status="Coder intake",
                            **kwargs,
                        )
                    )
                self.assertTrue(self._materialization_messages(findings), findings)

    def test_materialized_child_graph_uses_existing_normal_path(self) -> None:
        child_path = "docs/plans/260822_1728_child_fixture.md"
        with tempfile.TemporaryDirectory() as tmpdir:
            findings = MODULE.lint_plan(
                self._write_materialization_corridor_fixture(
                    Path(tmpdir),
                    status="Ready for Review",
                    child_map_rows=(
                        "| Queue order | Plan | Summary |\n| --- | --- | --- |\n"
                        f"| 1 | `{child_path}` | materialized |"
                    ),
                    execution_queue_rows=f"- Plan: `{child_path}`",
                    child_files={
                        child_path: (
                            "# Plan: child fixture\n\n"
                            "**Status:** Ready for Planner\n"
                        )
                    },
                )
            )
        self.assertEqual(self._materialization_messages(findings), [], findings)

    def test_strict_na_parent_projects_oracle_admission_without_a_private_lint_exemption(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            candidate_findings = MODULE.lint_plan(
                self._write_materialization_corridor_fixture(
                    Path(tmpdir),
                    status="Coder intake",
                    strict_na_parent=True,
                )
            )
        self.assertEqual(self._materialization_messages(candidate_findings), [], candidate_findings)
        self.assertFalse(
            any("machine_authority_decision" in finding.message for finding in candidate_findings),
            candidate_findings,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            review_findings = MODULE.lint_plan(
                self._write_materialization_corridor_fixture(
                    Path(tmpdir),
                    status="Ready for Review",
                    strict_na_parent=True,
                )
            )
        self.assertTrue(self._materialization_messages(review_findings), review_findings)

        child_path = "docs/plans/260823_1512_partial_strict_na_child.md"
        with tempfile.TemporaryDirectory() as tmpdir:
            partial_findings = MODULE.lint_plan(
                self._write_materialization_corridor_fixture(
                    Path(tmpdir),
                    status="Coder intake",
                    strict_na_parent=True,
                    child_map_rows=(
                        "| Queue order | Plan | Summary |\n| --- | --- | --- |\n"
                        f"| 1 | `{child_path}` | partial strict child |"
                    ),
                    next_plans=[],
                )
            )
        self.assertTrue(self._materialization_messages(partial_findings), partial_findings)


class PlanLintSmallRunnerAdmissionTests(unittest.TestCase):
    def setUp(self) -> None:
        MODULE.load_and_apply_plan_vocab(MODULE.PLAN_VOCAB_PATH)

    def _write_fixture(self, root: Path, stem: str, runner_rows: str) -> Path:
        (root / ".git").mkdir(exist_ok=True)
        ensure_fixture_git(root)
        plan_path = root / "docs" / "plans" / f"{stem}.md"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(
            dedent(
                f"""\
                # Plan: small runner admission fixture

                **Date:** 2026-06-19 00:32 MSK
                **Stage:** Stage 2
                **Priority:** P1
                **Plan type:** dev
                **Status:** Architect draft
                **Schema version:** plan.v1

                ## Meta (machine-readable JSON; required for new plans)
                ```json
                {{
                  "plan_meta": {{
                    "cluster": "process",
                    "tags": ["small-runner"],
                    "wave_family": null,
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

                ## Documentation impact / provenance
                - Source docs used: fixture.
                - Synchronous doc/registry targets: `docs/playbooks/decomposition_wave.md`.
                - Post-merge canon updates: `N/A (why=fixture)`.
                - Deferred documentation follow-ups: `N/A (why=fixture)`.
                - Provenance refs: fixture.

                ## Decisions (final)
                - Fixture.

                ### UI/HTMX playbooks (micro-block; required for UI/HTMX tasks)
                - Archetype: `N/A (why=process fixture)`
                - Modules: `N/A (why=process fixture)`
                - Primary CTA: `N/A (why=process fixture)`
                - header_filters: `N/A (why=process fixture)`
                - Results count strategy: `N/A (why=process fixture)`

                ## Small-runner proof receipt
                | Field | Value |
                | --- | --- |
                {runner_rows}

                ## Rollout packet handoff
                - Role: `N/A (why=fixture)`
                - Packet path: `N/A (why=fixture)`
                - Target repo: `N/A (why=fixture)`
                - Suggested target plan slug: `N/A (why=fixture)`
                - Queue after import: `N/A (why=fixture)`

                ## Close-out routing
                - Roadmap/queue sync: fixture.
                - Follow-up sync: `N/A (why=fixture)`
                - Next bounded slice: `N/A (why=fixture)`
                - Terminal outcome: no (fixture).

                ## Verification rerun / exec handoff
                - Mode: fresh-exec
                - Context source: fixture.
                - Prompt: fixture.
                - Command: `python3 scripts/test_plan_lint.py`
                - Expected artifact: small-runner admission warning.
                """
            ),
            encoding="utf-8",
        )
        return plan_path

    def _small_runner_warnings(self, findings: list[object]) -> list[object]:
        return [
            finding
            for finding in findings
            if MODULE.SMALL_RUNNER_ADMISSION_WARNING_PREFIX in finding.message
        ]

    def test_small_runner_ok_without_proof_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                "260619_0032_small_runner_missing_proof",
                "| `runner_admission` | `small_runner_ok` |",
            )

            warnings = self._small_runner_warnings(MODULE.lint_plan(plan_path))

        self.assertTrue(any("needs proof receipt" in finding.message for finding in warnings), warnings)

    def test_small_model_ready_with_material_runner_proof_passes(self) -> None:
        rows = "\n".join(
            (
                "| `small_model_ready_state` | `ready` |",
                "| `runner_id` | `claude` |",
                "| `runner_result` | `completed focused helper slice` |",
                "| `small_runner_success` | `true` |",
                "| `frontier_intervention` | `false` |",
                "| `reviewer_lane` | `independent frontier contracts review` |",
            )
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                "260619_0032_small_runner_ready_with_proof",
                rows,
            )

            warnings = self._small_runner_warnings(MODULE.lint_plan(plan_path))

        self.assertEqual(warnings, [])

    def test_small_runner_unavailable_evidence_cannot_count_as_success(self) -> None:
        rows = "\n".join(
            (
                "| `runner_admission` | `small_runner_ok` |",
                "| `runner_id` | `claude` |",
                "| `runner_result` | `inconclusive_runner_unavailable` |",
                "| `small_runner_success` | `false` |",
                "| `frontier_intervention` | `true` |",
                "| `reviewer_lane` | `frontier control review` |",
            )
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            plan_path = self._write_fixture(
                Path(tmpdir),
                "260619_0032_small_runner_unavailable_red",
                rows,
            )

            warnings = self._small_runner_warnings(MODULE.lint_plan(plan_path))

        self.assertTrue(any("cannot count as positive proof" in finding.message for finding in warnings), warnings)


class PlanLintManifestVocabularyTests(unittest.TestCase):
    def setUp(self) -> None:
        MODULE.load_and_apply_plan_vocab(MODULE.PLAN_VOCAB_PATH)

    def tearDown(self) -> None:
        MODULE.load_and_apply_plan_vocab(MODULE.PLAN_VOCAB_PATH)

    def _read_live_manifest(self) -> dict[str, object]:
        return json.loads(MODULE.PLAN_VOCAB_PATH.read_text(encoding="utf-8"))

    def _write_manifest(self, root: Path, payload: object, *, name: str = "plan_vocab.json") -> Path:
        manifest_dir = root / "docs" / "_meta"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = manifest_dir / name
        manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return manifest_path

    def test_green_temp_manifest_loads_and_applies_without_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manifest_path = self._write_manifest(root, self._read_live_manifest())

            live_config = MODULE.load_plan_vocab(MODULE.PLAN_VOCAB_PATH)
            temp_config = MODULE.load_plan_vocab(manifest_path)
            MODULE.load_and_apply_plan_vocab(manifest_path)

        self.assertEqual(temp_config, live_config)
        self.assertEqual(MODULE.CANONICAL_PLAN_STATUSES, live_config["canonical_statuses"])
        self.assertEqual(MODULE.CODE_DRAFT_REQUIRED_STATUS_NORMS, live_config["code_draft_required"])
        self.assertEqual(MODULE.ALLOWED_CLUSTERS, live_config["canonical_clusters"])

    def test_live_manifest_contains_planning_contour_contract(self) -> None:
        config = MODULE.load_plan_vocab(MODULE.PLAN_VOCAB_PATH)
        planning_contour = config["planning_contour"]

        self.assertEqual(
            config["blocking_dependency_carrier"],
            {
                "field": "blocking_depends_on",
                "shape": "sorted_unique_repo_relative_plan_path_array",
                "subset_of": "depends_on",
                "clearance": "delivery_green",
            },
        )

        self.assertEqual(
            planning_contour["accepted_routes"],
            [
                "developer_wave",
                "decomposition_wave",
                "human_gate",
                "defer",
                "reject",
            ],
        )
        self.assertIn("queue_activation_states", planning_contour)
        self.assertIn("scope_expansion_states", planning_contour)
        self.assertEqual(
            planning_contour["requirement_slice_kinds"],
            [
                "dev_candidate",
                "decomposition_candidate",
                "needs_analysis",
            ],
        )
        self.assertTrue(planning_contour["status_transition_matrix"])
        architect_draft_rows = [
            row
            for row in planning_contour["status_transition_matrix"]
            if row.get("initial_status") == "Architect initial draft"
        ]
        self.assertTrue(architect_draft_rows)
        self.assertTrue(all(row.get("queue_activation_required") is True for row in architect_draft_rows))

    def test_missing_manifest_fails_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            missing_path = Path(tmpdir) / "docs" / "_meta" / "missing_plan_vocab.json"

            with self.assertRaises(MODULE.ManifestError) as ctx:
                MODULE.load_plan_vocab(missing_path)

        self.assertIn("Missing required plan vocabulary manifest:", str(ctx.exception))
        self.assertIn("missing_plan_vocab.json", str(ctx.exception))

    def test_malformed_manifest_fails_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manifest_dir = root / "docs" / "_meta"
            manifest_dir.mkdir(parents=True, exist_ok=True)
            manifest_path = manifest_dir / "broken_plan_vocab.json"
            manifest_path.write_text("{ broken json\n", encoding="utf-8")

            with self.assertRaises(MODULE.ManifestError) as ctx:
                MODULE.load_plan_vocab(manifest_path)

        self.assertIn("Invalid JSON in", str(ctx.exception))
        self.assertIn("broken_plan_vocab.json", str(ctx.exception))

    def test_semantically_invalid_manifest_fails_on_unknown_canonical_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            payload = copy.deepcopy(self._read_live_manifest())
            payload["plan_statuses"]["groups"]["code_draft_required"].append("not-a-real-status")
            manifest_path = self._write_manifest(root, payload, name="invalid_plan_vocab.json")

            with self.assertRaises(MODULE.ManifestError) as ctx:
                MODULE.load_plan_vocab(manifest_path)

        self.assertIn("plan_statuses.groups.code_draft_required references unknown canonical statuses", str(ctx.exception))
        self.assertIn("not-a-real-status", str(ctx.exception))

    def test_semantically_invalid_manifest_fails_on_blocking_dependency_predicate_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            payload = copy.deepcopy(self._read_live_manifest())
            payload["blocking_dependency_carrier"]["clearance"] = "raw_done_status"
            manifest_path = self._write_manifest(root, payload, name="invalid_blocking_dependency_vocab.json")

            with self.assertRaises(MODULE.ManifestError) as ctx:
                MODULE.load_plan_vocab(manifest_path)

        self.assertIn("blocking_dependency_carrier.clearance", str(ctx.exception))
        self.assertIn("delivery_green", str(ctx.exception))

    def test_main_with_missing_manifest_path_returns_1_and_error_without_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            missing_path = Path(tmpdir) / "docs" / "_meta" / "missing_plan_vocab.json"
            stdout = io.StringIO()
            argv = [
                "plan_lint.py",
                "docs/plans/260316_2329_process_plan_vocab_manifest_lint_regression_tests.md",
            ]

            with mock.patch.object(MODULE, "PLAN_VOCAB_PATH", missing_path):
                with mock.patch.object(sys, "argv", argv):
                    with mock.patch("sys.stdout", stdout):
                        result = MODULE.main()

        self.assertEqual(result, 1)
        output = stdout.getvalue()
        self.assertIn("ERROR: Missing required plan vocabulary manifest:", output)
        self.assertIn("missing_plan_vocab.json", output)


class PlanLintBlockingDependencyCarrierTests(unittest.TestCase):
    def setUp(self) -> None:
        MODULE.load_and_apply_plan_vocab(MODULE.PLAN_VOCAB_PATH)

    def _meta(
        self,
        *,
        depends_on: object,
        blocking_depends_on: object,
        queue_activation_state: str = "owner_approved",
    ) -> dict[str, object]:
        return {
            "cluster": "process",
            "tags": [],
            "required_manager_mode": "either",
            "phase_overlay": None,
            "phase_state": None,
            "parent": None,
            "next_plans": [],
            "depends_on": depends_on,
            "blocking_depends_on": blocking_depends_on,
            "queue_activation": {
                "state": queue_activation_state,
                "source_ref": "docs/plans/fixture.md#Q1",
                "reason": "fixture",
            },
            "followups_out": [],
            "canon_updates": [],
        }

    def _validate(
        self,
        meta: dict[str, object],
        *,
        status: str = "Ready for Coder",
        path: Path | None = None,
    ) -> list[object]:
        return MODULE.validate_blocking_dependency_carrier(
            path or Path("/tmp/docs/plans/260805_1200_blocking_dependency_fixture.md"),
            meta,
            1,
            status_value=status,
        )

    def _write_target(self, root: Path, rel_path: str, *, status: str) -> Path:
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            "# Plan: blocking dependency target\n\n"
            "**Date:** 2026-08-05 12:00 MSK\n"
            "**Plan type:** dev\n"
            f"**Status:** {status}\n",
            encoding="utf-8",
        )
        return target

    def test_shape_and_subset_failures_are_always_errors(self) -> None:
        first = "docs/plans/260805_1201_dependency_a.md"
        second = "docs/plans/260805_1202_dependency_b.md"
        cases = {
            "wrong_type": self._meta(depends_on=[], blocking_depends_on={"path": first}),
            "invalid_path": self._meta(depends_on=[first], blocking_depends_on=["docs/reviews/not_a_plan.md"]),
            "duplicate": self._meta(depends_on=[first], blocking_depends_on=[first, first]),
            "unsorted": self._meta(depends_on=[first, second], blocking_depends_on=[second, first]),
            "missing_subset": self._meta(depends_on=[], blocking_depends_on=[first]),
        }

        for label, meta in cases.items():
            with self.subTest(label=label):
                findings = self._validate(meta)
                self.assertTrue(findings)
                self.assertTrue(all(finding.severity == "ERROR" for finding in findings), findings)
                self.assertTrue(
                    any("plan_meta.blocking_depends_on" in finding.message for finding in findings),
                    findings,
                )

    def test_valid_green_carrier_has_no_readback_finding(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            ensure_fixture_git(root)
            target_rel = "docs/plans/260805_1203_exact_green_outcome.md"
            self._write_target(root, target_rel, status="Done")
            meta = self._meta(depends_on=[target_rel], blocking_depends_on=[target_rel])
            findings = self._validate(
                meta,
                path=root / "docs/plans/260805_1204_valid_blocking_consumer.md",
            )

        self.assertEqual(findings, [])

    def test_lint_plan_routes_non_green_carrier_to_readback_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            ensure_fixture_git(root)
            target_rel = "docs/plans/260805_1205_red_outcome.md"
            plan_rel = "docs/plans/260805_1206_readback_consumer.md"
            self._write_target(root, target_rel, status="Ready for Coder")
            plan_path = root / plan_rel
            plan_path.parent.mkdir(parents=True, exist_ok=True)
            meta = self._meta(depends_on=[target_rel], blocking_depends_on=[target_rel])
            plan_path.write_text(
                "# Plan: blocking dependency consumer\n\n"
                "**Date:** 2026-08-05 12:06 MSK\n"
                "**Stage:** Stage 1\n"
                "**Priority:** P1\n"
                "**Plan type:** dev\n"
                "**Status:** Ready for Coder\n"
                "**Schema version:** plan.v1\n\n"
                "## Meta (machine-readable JSON; required for new plans)\n"
                "```json\n"
                + json.dumps({"plan_meta": meta}, ensure_ascii=False, indent=2)
                + "\n```\n",
                encoding="utf-8",
            )

            findings = MODULE.lint_plan(plan_path)

        readback = [finding for finding in findings if finding.message.startswith("Blocking dependency readback:")]
        self.assertEqual(len(readback), 1)
        self.assertEqual(readback[0].severity, "ERROR")
        self.assertIn(target_rel, readback[0].message)

    def test_readback_severity_is_warning_only_for_early_or_terminal_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            ensure_fixture_git(root)
            target_rel = "docs/plans/260805_1207_red_dependency.md"
            consumer_path = root / "docs/plans/260805_1208_readback_severity_consumer.md"
            self._write_target(root, target_rel, status="Ready for Coder")

            early = self._validate(
                self._meta(
                    depends_on=[target_rel],
                    blocking_depends_on=[target_rel],
                    queue_activation_state="n/a",
                ),
                status="Architect response",
                path=consumer_path,
            )
            approved = self._validate(
                self._meta(
                    depends_on=[target_rel],
                    blocking_depends_on=[target_rel],
                    queue_activation_state="owner_approved",
                ),
                status="Ready for Coder",
                path=consumer_path,
            )
            terminal = self._validate(
                self._meta(
                    depends_on=[target_rel],
                    blocking_depends_on=[target_rel],
                    queue_activation_state="owner_approved",
                ),
                status="Superseded",
                path=consumer_path,
            )

        self.assertEqual([finding.severity for finding in early], ["WARN"])
        self.assertEqual([finding.severity for finding in approved], ["ERROR"])
        self.assertEqual([finding.severity for finding in terminal], ["WARN"])


class CodeDraftRefsExtractionTests(unittest.TestCase):
    """extract_code_draft_refs must skip paths that are already correctly
    annotated as N/A (sibling-repo / superseded) so they do not produce
    spurious missing-file findings."""

    def test_plain_code_draft_ref_is_extracted(self) -> None:
        lines = [
            "- Code draft(s): `docs/code_drafts/260601_0101_process_fixture__code_draft.md`"
        ]
        refs = MODULE.extract_code_draft_refs(lines)
        self.assertEqual(len(refs), 1)
        self.assertTrue(refs[0][1].endswith("__code_draft.md"))

    def test_na_annotated_sibling_repo_ref_is_skipped(self) -> None:
        lines = [
            "- Code draft(s): `N/A (superseded seed artifact; canonical seed draft lives in `${EXTERNAL_REPO_ROOT:-$HOME/consumer-fixture}/docs/code_drafts/260601_0101_process_fixture__code_draft.md`)"
        ]
        refs = MODULE.extract_code_draft_refs(lines)
        self.assertEqual(refs, [])

    def test_historical_evidence_log_ref_is_skipped(self) -> None:
        # Historical changelog lines (with an inline timestamp) are immutable
        # provenance; a docs/code_drafts/... path named inside such a log must
        # not be treated as a live local draft reference.
        lines = [
            "- [2026-02-02 02:54] (Planner) Suggestion: привести `docs/code_drafts/260201_2241_process_fixture__code_draft.md` в соответствие решениям плана."
        ]
        refs = MODULE.extract_code_draft_refs(lines)
        self.assertEqual(refs, [])

    def test_review_freshness_headers_use_only_metadata_preamble(self) -> None:
        lines = [
            "# Review",
            "",
            "**Date:** 2026-07-13 03:00 MSK",
            "**Target:** BUNDLE=current",
            "**Status:** ✅ OK",
            "",
            "Summary body.",
            "**Date:** 2026-07-14 03:00 MSK",
            "**Target:** BUNDLE=body",
            "**Status:** ❌ S1 blocker(ы)",
        ]

        date_line, target_line, status_line = MODULE.extract_review_header_values(lines)

        self.assertEqual(date_line, (3, "2026-07-13 03:00 MSK"))
        self.assertEqual(target_line, (4, "BUNDLE=current"))
        self.assertEqual(status_line, (5, "✅ OK"))

    def test_review_freshness_duplicate_header_is_ambiguous(self) -> None:
        lines = [
            "# Review",
            "**Date:** 2026-07-13 03:00 MSK",
            "**Target:** BUNDLE=first",
            "**Target:** BUNDLE=second",
            "**Status:** ❌ S1 blocker(ы)",
        ]

        _date_line, target_line, _status_line = MODULE.extract_review_header_values(lines)

        self.assertIsNone(target_line)

    def test_review_freshness_noncanonical_status_is_not_proof(self) -> None:
        lines = ["# Review", "**Status :** ❌ S1 blocker(ы)"]

        _date_line, _target_line, status_line = MODULE.extract_review_header_values(lines)

        self.assertIsNone(status_line)

    def test_rerun_freshness_noncanonical_status_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260713_0301_fixture.md"
            review_rel = "docs/code_reviews/260713_0301_fixture.md"
            review_path = root / review_rel
            review_path.parent.mkdir(parents=True, exist_ok=True)
            review_path.write_text(
                "# Review\n\n**Date:** 2026-07-13 03:01 MSK\n"
                "**Target:** BUNDLE=current\n"
                "**Status :** ❌ S1 blocker(ы)\n",
                encoding="utf-8",
            )
            plan_path = root / plan_rel
            plan_path.parent.mkdir(parents=True, exist_ok=True)
            plan_lines = [
                "# Plan",
                "",
                "**Status:** Ready for Review",
                "",
                "## Review artifacts",
                f"- Code review (primary): `{review_rel}`",
            ]

            findings = MODULE.validate_review_artifact_rerun_freshness(
                plan_path,
                plan_lines,
                status_value="Ready for Review",
                plan_repo_root=root,
            )

        self.assertEqual(len(findings), 1)
        self.assertIn("`status` metadata is noncanonical", findings[0].message)

    def test_rerun_freshness_duplicate_review_status_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260713_0300_fixture.md"
            review_rel = "docs/code_reviews/260713_0300_fixture.md"
            review_path = root / review_rel
            review_path.parent.mkdir(parents=True, exist_ok=True)
            review_path.write_text(
                "# Review\n\n**Date:** 2026-07-13 03:00 MSK\n"
                "**Target:** BUNDLE=current\n"
                "**Status:** ❌ S1 blocker(ы)\n"
                "**Status :** ✅ OK\n",
                encoding="utf-8",
            )
            plan_path = root / plan_rel
            plan_path.parent.mkdir(parents=True, exist_ok=True)
            plan_lines = [
                "# Plan",
                "",
                "**Status:** Ready for Review",
                "",
                "## Review artifacts",
                f"- Code review (primary): `{review_rel}`",
            ]

            findings = MODULE.validate_review_artifact_rerun_freshness(
                plan_path,
                plan_lines,
                status_value="Ready for Review",
                plan_repo_root=root,
            )

        self.assertEqual(len(findings), 1)
        self.assertIn("duplicate `status` metadata", findings[0].message)


class PlanLintRequiredManagerModeTests(unittest.TestCase):
    def _meta_findings(self, basename: str, value: object = ...):
        meta: dict[str, object] = {"cluster": "process", "tags": []}
        if value is not ...:
            meta["required_manager_mode"] = value
        lines = ["```json", json.dumps({"plan_meta": meta}), "```"]
        return MODULE.validate_plan_meta(Path("/tmp/docs/plans") / basename, lines)[0]

    def test_required_mode_enum_is_enforced_for_old_and_new_names(self) -> None:
        for value in ("manager-collab", "manager-custom-pipeline", "either"):
            with self.subTest(value=value):
                findings = self._meta_findings("260712_1255_fixture.md", value)
                self.assertFalse(
                    [f for f in findings if "required_manager_mode" in f.message],
                    findings,
                )

        historical = self._meta_findings("260712_1254_fixture.md")
        current = self._meta_findings("260712_1255_fixture.md")
        self.assertEqual(
            [(f.severity, f.message) for f in historical if "required_manager_mode" in f.message][0][0],
            "ERROR",
        )
        self.assertEqual(
            [(f.severity, f.message) for f in current if "required_manager_mode" in f.message][0][0],
            "ERROR",
        )
        for invalid in ("native", 1, ["manager-collab"], None):
            with self.subTest(invalid=invalid):
                findings = self._meta_findings("260712_1254_fixture.md", invalid)
                mode_findings = [f for f in findings if "required_manager_mode" in f.message]
                self.assertEqual(mode_findings[0].severity, "ERROR")

        pre_meta_boundary_invalid = self._meta_findings("260101_0000_fixture.md", "native")
        pre_meta_boundary_missing = self._meta_findings("260101_0000_fixture.md")
        self.assertEqual(
            [f.severity for f in pre_meta_boundary_invalid if "required_manager_mode" in f.message],
            ["ERROR"],
        )
        self.assertEqual(
            [f.severity for f in pre_meta_boundary_missing if "required_manager_mode" in f.message],
            ["ERROR"],
        )
        undated_missing = self._meta_findings("fixture_without_date.md")
        self.assertEqual(
            [f.severity for f in undated_missing if "required_manager_mode" in f.message],
            ["ERROR"],
        )

    def test_manager_handoff_parity_and_non_manager_negative(self) -> None:
        path = Path("/tmp/docs/plans/260712_1255_fixture.md")
        native = {"required_manager_mode": "manager-collab"}
        custom = {"required_manager_mode": "manager-custom-pipeline"}

        def findings(command: str, meta: dict[str, str]):
            return MODULE.validate_manager_mode_handoff_command(
                path,
                [
                    "## Verification rerun / exec handoff",
                    f"- Command: `{command}`",
                    "## Evidence",
                ],
                meta,
            )

        self.assertEqual(findings("planveyor_manager_collab_cmd run", native), [])
        self.assertEqual(findings("planveyor_manager_custom_pipeline_cmd run", custom), [])
        self.assertTrue(findings("planveyor_manager_custom_pipeline_cmd run", native))
        self.assertTrue(findings("planveyor_manager_collab_cmd run", custom))
        malformed = findings("MANAGER_CMD=run planveyor_manager_custom_pipeline_cmd", custom)
        self.assertTrue(any("Malformed Manager handoff command" in f.message for f in malformed))
        self.assertEqual(findings("python3 -B scripts/plan_lint.py PLAN.md", native), [])


class PlanLintMaterializedReviewVisualLaneContractTests(unittest.TestCase):
    def _review_range_semantic_receipt_v2(self) -> dict[str, object]:
        payload = copy.deepcopy(self._review_range_semantic_receipt())
        payload["schema_version"] = MODULE._REVIEW_RANGE_PROVENANCE_V2
        payload["source_engine_version"] = MODULE._REVIEW_RANGE_PROVENANCE_ENGINE_BY_SCHEMA[
            MODULE._REVIEW_RANGE_PROVENANCE_V2
        ]
        payload["inputs"] = [
            {
                "id": row["id"],
                "reader": row["reader"],
                "contract_relative_path": row["contract_relative_path"],
                "content_source": "current_local_worktree",
            }
            for row in payload["inputs"]
        ]
        return payload


    def test_review_range_semantic_provenance_accepts_matching_planveyor_and_generic_v1_v2(self) -> None:
        long_generic_identity = "consumer_" + "a" * 129
        for make_receipt in (self._review_range_semantic_receipt, self._review_range_semantic_receipt_v2):
            for identity in ("planveyor", "consumer_42.alpha", long_generic_identity):
                with self.subTest(schema=make_receipt()["schema_version"], identity=identity):
                    payload = make_receipt()
                    payload["behavior_identity"] = identity
                    payload["marker_repository_id_or_not_applicable"] = identity
                    self.assertIsNone(MODULE._review_range_semantic_provenance_shape_error(payload))

    def test_review_range_semantic_provenance_rejects_invalid_consumer_ids_without_fence_exemption(self) -> None:
        path = Path("docs/plans/260909_0101_reviewer_range_fixture.md")
        cases = (
            ("malformed", ["consumer_42"], ["consumer_42"], "context_facts"),
            ("default", "default", "default", "runtime_pin"),
            ("mismatch", "consumer_42", "other_42", "runtime_pin"),
            ("grammar", "consumer@42", "consumer@42", "runtime_pin"),
        )
        for make_receipt in (self._review_range_semantic_receipt, self._review_range_semantic_receipt_v2):
            for label, behavior_identity, marker_identity, expected in cases:
                with self.subTest(schema=make_receipt()["schema_version"], case=label):
                    payload = make_receipt()
                    payload["behavior_identity"] = behavior_identity
                    payload["marker_repository_id_or_not_applicable"] = marker_identity
                    # JSON permits insignificant blank lines.  Keep the exact
                    # payload while making the fence large enough to prove
                    # that an invalid receipt does not receive the exemption.
                    body = json.dumps(payload, ensure_ascii=False, indent=2).replace("\n", "\n\n")
                    receipt = [
                        "## Review-range semantic provenance",
                        "",
                        "```json",
                        *body.splitlines(),
                        "```",
                    ]
                    self.assertEqual(MODULE._review_range_semantic_provenance_shape_error(payload), expected)
                    findings = MODULE.validate_review_range_semantic_provenance(path, receipt)
                    self.assertEqual(len(findings), 1)
                    self.assertTrue(
                        any(
                            "lines" in finding.message
                            for finding in MODULE.validate_code_block_sizes(path, receipt, 0)
                        )
                    )

    def test_review_range_semantic_provenance_rejects_non_scalar_unicode(self) -> None:
        for make_receipt in (self._review_range_semantic_receipt, self._review_range_semantic_receipt_v2):
            payload = make_receipt()
            payload["behavior_identity"] = "\ud800"
            with self.subTest(schema=payload["schema_version"]):
                self.assertEqual(MODULE._review_range_semantic_provenance_shape_error(payload), "context_facts")

    def test_review_range_semantic_provenance_rejects_excessive_json_nesting(self) -> None:
        depth = 50_000
        body = '{"nested":' + '[' * depth + '0' + ']' * depth + '}'
        lines = ["## Review-range semantic provenance", "", "```json", body, "```"]
        payload, error = MODULE.parse_review_range_semantic_provenance(lines)
        self.assertEqual(error, "receipt_json_invalid")
        self.assertIsNone(payload)


    def test_review_range_semantic_provenance_rejects_invalid_v2_rows_and_unhashable_schema(self) -> None:
        invalid_v2 = self._review_range_semantic_receipt_v2()
        invalid_v2["inputs"][0]["content_source"] = "captured_manifest"
        self.assertEqual(MODULE._review_range_semantic_provenance_shape_error(invalid_v2), "engaged_input_set")
        for bad_schema in ([], {}):
            malformed = self._review_range_semantic_receipt_v2()
            malformed["schema_version"] = bad_schema
            self.assertEqual(MODULE._review_range_semantic_provenance_shape_error(malformed), "schema_or_field_set")

    def _payload(self, state: str = "available") -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": "review_visual_lane_contract.v1",
            "availability_state": state,
            "runtime_ui_kind": "web" if state != "not_applicable" else "none",
            "profile_id": "default",
            "source_refs": ["docs/smoke_visual.md", "docs/testing_runbook.md"],
            "changed_path_evidence": [
                {
                    "status": "M",
                    "path": "templates/page.html",
                    "old_path": "",
                    "runtime_ui": True,
                    "runtime_ui_paths": ["templates/page.html"],
                }
            ],
            "mandatory_modes": ["primary", "secondary"] if state == "available" else [],
            "comparator_command": "./scripts/run_visual_check.sh --repeat 2" if state == "available" else "",
            "comparator_claim": "mechanical",
            "baseline_update_allowed": False,
            "human_commands_by_mode": (
                {
                    "primary": "./scripts/review_visual_design_audit.sh --mode primary",
                    "secondary": "./scripts/review_visual_design_audit.sh --mode secondary",
                }
                if state == "available"
                else {}
            ),
            "human_index_paths_by_mode": (
                {"primary": ".tmp/primary/index.md", "secondary": ".tmp/secondary/index.md"} if state == "available" else {}
            ),
            "human_output_roots_by_mode": (
                {"primary": ".tmp/primary", "secondary": ".tmp/secondary"} if state == "available" else {}
            ),
            "complete_index_required": True,
            "durable_review_asset_root": "docs/code_reviews/assets/260722_2206_review/",
            "reason": "repo_backed_visual_lane" if state == "available" else f"{state}_fixture",
        }
        return payload

    def _lines(self, payload: dict[str, object], visual_body: str) -> list[str]:
        return (
            "## Review visual lane contract\n\n"
            + MODULE.review_visual_lane_contract.render_materialized_contract(payload)
            + "\n\n## Visual Acceptance (browser, UI tasks)\n\n"
            + visual_body
            + "\n"
        ).splitlines()

    def test_available_two_claim_contract_passes(self) -> None:
        payload = self._payload()
        visual = "\n".join(
            [
                str(payload["comparator_command"]),
                *payload["human_commands_by_mode"].values(),
                str(payload["durable_review_asset_root"]),
                "comparator_claim=mechanical complete-index design_verdict",
            ]
        )
        findings = MODULE.validate_materialized_review_visual_lane_contract(
            Path("docs/plans/260722_2206_reviewer_range_fixture.md"), self._lines(payload, visual)
        )
        self.assertEqual(findings, [])

    def test_malformed_changed_path_evidence_is_a_finding(self) -> None:
        payload = self._payload()
        payload["changed_path_evidence"] = [None]

        findings = MODULE.validate_materialized_review_visual_lane_contract(
            Path("docs/plans/260722_2206_reviewer_range_fixture.md"),
            self._lines(payload, "N/A (why=malformed fixture)"),
        )

        self.assertEqual(len(findings), 1)
        self.assertIn("changed_path_evidence_malformed", findings[0].message)

    def test_available_naked_na_or_missing_human_claim_fails(self) -> None:
        payload = self._payload()
        naked = MODULE.validate_materialized_review_visual_lane_contract(
            Path("docs/plans/260722_2206_reviewer_range_fixture.md"),
            self._lines(payload, "N/A (why=no visual proof)"),
        )
        self.assertTrue(any("naked" in finding.message for finding in naked))
        incomplete = MODULE.validate_materialized_review_visual_lane_contract(
            Path("docs/plans/260722_2206_reviewer_range_fixture.md"),
            self._lines(
                payload,
                f"{payload['comparator_command']}\n{payload['durable_review_asset_root']}\n"
                "comparator_claim=mechanical complete-index design_verdict",
            ),
        )
        self.assertTrue(any("missing comparator/human" in finding.message for finding in incomplete))

    def test_non_available_runtime_ui_is_architect_gap(self) -> None:
        for state in ("missing", "malformed", "ambiguous"):
            with self.subTest(state=state):
                findings = MODULE.validate_materialized_review_visual_lane_contract(
                    Path("docs/plans/260722_2206_reviewer_range_fixture.md"),
                    self._lines(self._payload(state), f"technical gap availability_state={state}"),
                )
                self.assertTrue(any("route to Architect" in finding.message for finding in findings))

    def test_truthful_non_ui_not_applicable_passes(self) -> None:
        payload = self._payload("not_applicable")
        findings = MODULE.validate_materialized_review_visual_lane_contract(
            Path("docs/plans/260722_2206_reviewer_range_fixture.md"),
            self._lines(payload, "N/A (why=no runtime UI paths)"),
        )
        self.assertEqual(findings, [])

    def test_code_block_line_and_utf8_byte_limits_are_independent(self) -> None:
        path = Path("docs/plans/260830_0241_visual_fixture.md")
        line_bounded = ["```text", *(["x"] * MODULE.MAX_PLAN_CODE_BLOCK_LINES), "```"]
        line_over = ["```text", *(["x"] * (MODULE.MAX_PLAN_CODE_BLOCK_LINES + 1)), "```"]
        byte_bounded = ["```text", "x" * MODULE.MAX_PLAN_CODE_BLOCK_UTF8_BYTES, "```"]
        byte_over = ["```text", "x" * (MODULE.MAX_PLAN_CODE_BLOCK_UTF8_BYTES + 1), "```"]

        self.assertEqual(MODULE.validate_code_block_sizes(path, line_bounded, 0), [])
        self.assertTrue(
            any(
                "121 lines" in finding.message
                for finding in MODULE.validate_code_block_sizes(path, line_over, 0)
            )
        )
        self.assertEqual(MODULE.validate_code_block_sizes(path, byte_bounded, 0), [])
        self.assertTrue(
            any(
                "16385 UTF-8 bytes" in finding.message
                for finding in MODULE.validate_code_block_sizes(path, byte_over, 0)
            )
        )

    def _review_range_semantic_receipt(self) -> dict[str, object]:
        selected = list(MODULE._REVIEW_RANGE_ENGAGED_RULE_IDS)
        return {
            "schema_version": MODULE._REVIEW_RANGE_PROVENANCE_V1,
            "source_engine_version": MODULE._REVIEW_RANGE_PROVENANCE_ENGINE_BY_SCHEMA[MODULE._REVIEW_RANGE_PROVENANCE_V1],
            "source_runtime_pin": {
                "runtime_api_version": 5,
                "runtime_root": "/fixture/runtime",
                "sha256": "a" * 64,
            },
            "context_state": "engaged",
            "behavior_identity": "planveyor",
            "marker_repository_id_or_not_applicable": "planveyor",
            "context_generation": "b" * 64,
            "semantic_surface_sha256": MODULE._REVIEW_RANGE_SEMANTIC_SURFACE_SHA256,
            "selected_rule_ids": selected,
            "inputs": [
                {
                    "id": input_id,
                    "reader": reader,
                    "contract_relative_path": relative_path,
                    "captured_manifest_path": relative_path,
                    "mode": "100644",
                    "blob_oid": "c" * 40,
                    "sha256": "d" * 64,
                }
                for input_id, relative_path, reader in MODULE._REVIEW_RANGE_ENGAGED_INPUT_SPECS
            ],
            "outputs": [
                {
                    "artifact": "plan",
                    "section_or_path": "docs/plans/260909_0101_reviewer_range_fixture.md",
                    "rule_ids": selected,
                },
                {
                    "artifact": "draft",
                    "section_or_path": "docs/code_drafts/260909_0101_reviewer_range_fixture__code_draft.md",
                    "rule_ids": selected,
                },
            ],
            "visual_contract_ref_or_inline_digest": {"kind": "inline_digest", "sha256": "e" * 64},
        }

    def _review_range_receipt_lines(self, payload: dict[str, object]) -> list[str]:
        return [
            "## Review-range semantic provenance",
            "",
            "```json",
            *json.dumps(payload, ensure_ascii=False, indent=2).splitlines(),
            "```",
        ]

    def test_review_range_semantic_provenance_json_is_exempt_only_for_admitted_receipt_shape(self) -> None:
        path = Path("docs/plans/260909_0101_reviewer_range_fixture.md")
        receipt = self._review_range_receipt_lines(self._review_range_semantic_receipt())
        self.assertGreater(len(receipt) - 4, MODULE.MAX_PLAN_CODE_BLOCK_LINES)
        self.assertEqual(MODULE.validate_code_block_sizes(path, receipt, 0), [])

    def test_review_range_semantic_provenance_malformed_rule_id_is_a_finding_not_type_error(self) -> None:
        path = Path("docs/plans/260909_0101_reviewer_range_fixture.md")
        malformed = self._review_range_semantic_receipt()
        malformed["selected_rule_ids"] = [{}]
        receipt = self._review_range_receipt_lines(malformed)

        findings = MODULE.validate_review_range_semantic_provenance(path, receipt)

        self.assertEqual(len(findings), 1)
        self.assertIn("invalid rule/input/output rows", findings[0].message)
        self.assertTrue(
            any(
                "lines" in finding.message
                for finding in MODULE.validate_code_block_sizes(path, receipt, 0)
            )
        )

    def test_review_range_semantic_provenance_malformed_context_state_is_a_finding_and_not_fence_exempt(self) -> None:
        path = Path("docs/plans/260909_0101_reviewer_range_fixture.md")
        for invalid_state in ([], {}):
            with self.subTest(context_state_type=type(invalid_state).__name__):
                malformed = self._review_range_semantic_receipt()
                malformed["context_state"] = invalid_state
                receipt = self._review_range_receipt_lines(malformed)

                findings = MODULE.validate_review_range_semantic_provenance(path, receipt)

                self.assertEqual(len(findings), 1)
                self.assertIn("invalid context facts", findings[0].message)
                self.assertTrue(
                    any(
                        "lines" in finding.message
                        for finding in MODULE.validate_code_block_sizes(path, receipt, 0)
                    )
                )

    def test_visual_contract_content_byte_boundaries_match_generic_plan_guard(self) -> None:
        path = Path("docs/plans/260830_0241_visual_fixture.md")
        helper = MODULE.review_visual_lane_contract
        for content_bytes in (
            MODULE.MAX_PLAN_CODE_BLOCK_UTF8_BYTES - 1,
            MODULE.MAX_PLAN_CODE_BLOCK_UTF8_BYTES,
            MODULE.MAX_PLAN_CODE_BLOCK_UTF8_BYTES + 1,
        ):
            with self.subTest(content_bytes=content_bytes):
                payload = self._payload()
                payload["reason"] = ""
                base_markdown = helper.render_materialized_contract(payload)
                base_match = helper.JSON_BLOCK_RE.fullmatch(base_markdown.strip())
                assert base_match is not None
                base_body = base_match.group("body")
                payload["reason"] = "x" * (content_bytes - len(base_body.encode("utf-8")))
                inline_markdown = helper.render_materialized_contract(payload)
                inline_match = helper.JSON_BLOCK_RE.fullmatch(inline_markdown.strip())
                assert inline_match is not None
                body = inline_match.group("body")
                self.assertEqual(len(body.encode("utf-8")), content_bytes)
                self.assertEqual(helper._inline_metrics(inline_markdown), (len(body.splitlines()), content_bytes))

                materialization = helper.prepare_materialized_contract(
                    payload,
                    base="a" * 40,
                    head="b" * 40,
                    exclude_docs=0,
                    plan_ref="docs/plans/260830_0241_visual_fixture.md",
                    review_artifact_ref="docs/code_reviews/260830_0241_visual_fixture.md",
                )
                fence = ["```json", *body.splitlines(), "```"]
                extracted = MODULE.extract_fenced_code_blocks(fence)
                self.assertEqual(extracted, [(1, "json", len(body.splitlines()), content_bytes)])
                findings = MODULE.validate_code_block_sizes(path, fence, 0)

                if content_bytes <= MODULE.MAX_PLAN_CODE_BLOCK_UTF8_BYTES:
                    self.assertEqual(materialization["mode"], "inline")
                    parsed, errors = helper.parse_materialized_contract(inline_markdown)
                    self.assertEqual(errors, [])
                    self.assertEqual(parsed, payload)
                    self.assertEqual(findings, [])
                else:
                    self.assertEqual(materialization["mode"], "external")
                    parsed, errors = helper.parse_materialized_contract(inline_markdown)
                    self.assertIsNone(parsed)
                    self.assertEqual(errors, ["inline_content_byte_limit_exceeded"])
                    self.assertTrue(any("16385 UTF-8 bytes" in finding.message for finding in findings))

    def test_external_ref_resolves_and_same_stem_draft_drift_fails(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            plan_ref = "docs/plans/260830_0241_visual_fixture.md"
            draft_ref = "docs/code_drafts/260830_0241_visual_fixture__code_draft.md"
            review_ref = "docs/code_reviews/260830_0241_visual_fixture.md"
            payload = self._payload()
            payload["changed_path_evidence"] = [
                {
                    "status": "M",
                    "path": f"templates/generated_{index:04d}.html",
                    "old_path": "",
                    "runtime_ui": True,
                    "runtime_ui_paths": [f"templates/generated_{index:04d}.html"],
                }
                for index in range(940)
            ]
            materialization = MODULE.review_visual_lane_contract.prepare_materialized_contract(
                payload,
                base="a" * 40,
                head="b" * 40,
                exclude_docs=0,
                plan_ref=plan_ref,
                review_artifact_ref=review_ref,
            )
            self.assertEqual(materialization["mode"], "external")
            visual = "\n".join(
                [
                    str(payload["comparator_command"]),
                    *payload["human_commands_by_mode"].values(),
                    str(payload["durable_review_asset_root"]),
                    "comparator_claim=mechanical complete-index design_verdict",
                ]
            )
            plan_text = "\n".join(
                [
                    "# Plan",
                    "",
                    f"- Review target: `RANGE={'a' * 40}..{'b' * 40} (EXCLUDE_DOCS=0)`",
                    "",
                    "## Review visual lane contract",
                    "",
                    str(materialization["markdown"]),
                    "",
                    "## Visual Acceptance (browser, UI tasks)",
                    "",
                    visual,
                    "",
                ]
            )
            draft_text = "# Draft\n\n## Review visual lane contract\n\n" + str(materialization["markdown"]) + "\n"
            MODULE.review_visual_lane_contract.publish_generated_scaffold(
                project_root=root,
                plan_ref=plan_ref,
                plan_text=plan_text,
                draft_ref=draft_ref,
                draft_text=draft_text,
                materialization=materialization,
            )
            plan_path = root / plan_ref
            with mock.patch.object(MODULE, "REPO_ROOT", root):
                findings = MODULE.validate_materialized_review_visual_lane_contract(
                    plan_path,
                    plan_text.splitlines(),
                )
            self.assertEqual(findings, [])

            drifted = draft_text.replace('"full_payload_sha256":', '"full_payload_sha256": "0" * 0 #', 1)
            (root / draft_ref).write_text(drifted, encoding="utf-8")
            with mock.patch.object(MODULE, "REPO_ROOT", root):
                findings = MODULE.validate_materialized_review_visual_lane_contract(
                    plan_path,
                    plan_text.splitlines(),
                )
            self.assertTrue(any("projection mismatch" in finding.message for finding in findings))

    def test_external_ref_rejects_coherent_wrong_review_target(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            plan_ref = "docs/plans/260830_0241_wrong_range_visual_fixture.md"
            draft_ref = "docs/code_drafts/260830_0241_wrong_range_visual_fixture__code_draft.md"
            review_ref = "docs/code_reviews/260830_0241_wrong_range_visual_fixture.md"
            payload = self._payload()
            payload["changed_path_evidence"] = [
                {
                    "status": "M",
                    "path": f"templates/generated_{index:04d}.html",
                    "old_path": "",
                    "runtime_ui": True,
                    "runtime_ui_paths": [f"templates/generated_{index:04d}.html"],
                }
                for index in range(940)
            ]
            materialization = MODULE.review_visual_lane_contract.prepare_materialized_contract(
                payload,
                base="c" * 40,
                head="d" * 40,
                exclude_docs=1,
                plan_ref=plan_ref,
                review_artifact_ref=review_ref,
            )
            plan_text = (
                "# Plan\n\n"
                f"- Review target: `RANGE={'a' * 40}..{'b' * 40} (EXCLUDE_DOCS=0)`\n\n"
                "## Review visual lane contract\n\n"
                + str(materialization["markdown"])
                + "\n"
            )
            draft_text = "# Draft\n\n## Review visual lane contract\n\n" + str(materialization["markdown"]) + "\n"
            MODULE.review_visual_lane_contract.publish_generated_scaffold(
                project_root=root,
                plan_ref=plan_ref,
                plan_text=plan_text,
                draft_ref=draft_ref,
                draft_text=draft_text,
                materialization=materialization,
            )

            with mock.patch.object(MODULE, "REPO_ROOT", root):
                findings = MODULE.validate_materialized_review_visual_lane_contract(
                    root / plan_ref,
                    plan_text.splitlines(),
                )

            self.assertEqual(len(findings), 1)
            self.assertIn("identity_mismatch", findings[0].message)

    def test_external_ref_rejects_missing_or_noncanonical_review_target(self) -> None:
        cases = {
            "missing": "",
            "short": f"- Review target: `RANGE={'a' * 7}..{'b' * 7} (EXCLUDE_DOCS=0)`\n\n",
            "uppercase": f"- Review target: `RANGE={'A' * 40}..{'B' * 40} (EXCLUDE_DOCS=0)`\n\n",
            "duplicate": (
                f"- Review target: `RANGE={'a' * 40}..{'b' * 40} (EXCLUDE_DOCS=0)`\n"
                f"- Review target: `RANGE={'a' * 40}..{'b' * 40} (EXCLUDE_DOCS=0)`\n\n"
            ),
            "mixed": (
                f"- Review target: `RANGE={'a' * 40}..{'b' * 40} (EXCLUDE_DOCS=0)`\n"
                f"- Review target: `RANGE={'a' * 7}..{'b' * 7} (EXCLUDE_DOCS=0)`\n\n"
            ),
        }
        for name, target_lines in cases.items():
            with self.subTest(target=name), temporary_git_root() as tmpdir:
                root = Path(tmpdir)
                plan_ref = f"docs/plans/260830_0241_{name}_target_visual_fixture.md"
                draft_ref = f"docs/code_drafts/260830_0241_{name}_target_visual_fixture__code_draft.md"
                review_ref = f"docs/code_reviews/260830_0241_{name}_target_visual_fixture.md"
                payload = self._payload()
                payload["changed_path_evidence"] = [
                    {
                        "status": "M",
                        "path": f"templates/generated_{index:04d}.html",
                        "old_path": "",
                        "runtime_ui": True,
                        "runtime_ui_paths": [f"templates/generated_{index:04d}.html"],
                    }
                    for index in range(940)
                ]
                materialization = MODULE.review_visual_lane_contract.prepare_materialized_contract(
                    payload,
                    base="a" * 40,
                    head="b" * 40,
                    exclude_docs=0,
                    plan_ref=plan_ref,
                    review_artifact_ref=review_ref,
                )
                plan_text = (
                    "# Plan\n\n"
                    + target_lines
                    + "## Review visual lane contract\n\n"
                    + str(materialization["markdown"])
                    + "\n"
                )
                draft_text = "# Draft\n\n## Review visual lane contract\n\n" + str(materialization["markdown"]) + "\n"
                MODULE.review_visual_lane_contract.publish_generated_scaffold(
                    project_root=root,
                    plan_ref=plan_ref,
                    plan_text=plan_text,
                    draft_ref=draft_ref,
                    draft_text=draft_text,
                    materialization=materialization,
                )

                with mock.patch.object(MODULE, "REPO_ROOT", root):
                    findings = MODULE.validate_materialized_review_visual_lane_contract(
                        root / plan_ref,
                        plan_text.splitlines(),
                    )

                self.assertEqual(len(findings), 1)
                self.assertIn("review_target_identity_invalid", findings[0].message)


class PlanLintExternalAnalysisPackAuthorityTests(unittest.TestCase):
    STEM = "260729_0959_process_lint_external_authority"

    def _write_fixture(
        self,
        root: Path,
        *,
        stem: str | None = None,
        origin_rows: str = "",
        pack_rows: str | None = None,
        ref_row: str | None = None,
        write_pack: bool = True,
        status: str = "Architect initial draft",
    ) -> Path:
        stem = stem or self.STEM
        plan_rel = f"docs/plans/{stem}.md"
        pack_rel = f"docs/analysis_packs/{stem}.md"
        draft_rel = f"docs/code_drafts/{stem}__code_draft.md"
        canonical_ref = f"{pack_rel}#Analysis-pack"
        if ref_row is None:
            ref_row = f"| `analysis_pack_ref` | `{canonical_ref}` (refs-only annotation) |"
        plan = root / plan_rel
        plan.parent.mkdir(parents=True, exist_ok=True)
        plan.write_text(
            dedent(
                f"""\
                # Plan: lint external authority

                **Date:** 2026-07-29 09:59 MSK
                **Stage:** Stage 2
                **Priority:** P1
                **Plan type:** dev
                **Status:** {status}

                ## Meta (machine-readable JSON; required for new plans)
                ```json
                {json.dumps({"plan_meta": {"cluster": "process", "wave_family": "analysis_wave"}}, indent=2)}
                ```

                ## Analysis pack
                | Field | Value |
                | --- | --- |
                {ref_row}
                | `authority_boundary` | `standalone_pack_only` |
                {origin_rows}

                ## Promoted route artifact
                N/A (why=no accepted route)
                """
            ),
            encoding="utf-8",
        )
        draft = root / draft_rel
        draft.parent.mkdir(parents=True, exist_ok=True)
        draft.write_text(
            "# Draft\n\n```json\n"
            + json.dumps(
                {
                    "code_draft_meta": {
                        "plan": plan_rel,
                        "cluster": "process",
                        "targets": [{"path": pack_rel, "kind": "doc"}],
                        "deleted_paths": [],
                    }
                },
                indent=2,
            )
            + "\n```\n",
            encoding="utf-8",
        )
        if write_pack:
            pack = root / pack_rel
            pack.parent.mkdir(parents=True, exist_ok=True)
            default_rows = (
                "| `scope_refs` | opened/read: `docs/playbooks/analysis_wave.md` |\n"
                "| `documentation_impact_seed` | docs impact |\n"
                "| `dependent_inventory_mutable_surfaces` | mutable scripts/plan_lint.py |\n"
                "| `requirement_slices` | slice_kind=dev_candidate; bounded fixture |\n"
                "| `reviewability_seed` | focused test |\n"
                "| `runner_handoff_seed` | frontier only |\n"
                "| `route_recommendation` | `developer_wave` |\n"
                "| `execution_budget` | budget_status=active; source_ref_floor=1; route_iteration_limit=1; needs_analysis_depth_cap=2; current_needs_analysis_depth=1; stop_owner=Architect; exhaustion_action=architect_recheck |\n"
                "| `stale_trigger` | source_subject_baseline=authority; current_source_subject=authority |"
            )
            pack.write_text(
                "# Analysis pack\n\n## Analysis pack\n| Field | Value |\n| --- | --- |\n"
                + (default_rows if pack_rows is None else pack_rows)
                + "\n",
                encoding="utf-8",
            )
        return plan

    def _replacement_snapshot(
        self,
        root: Path,
        selected_rel: str,
        replacement_data: bytes,
    ) -> tuple[object, list[str]]:
        target = root / selected_rel
        replacement = target.with_name(f".{target.name}.replacement")
        replacement.write_bytes(replacement_data)
        real_snapshot = MODULE.plan_status_oracle.snapshot_regular_or_absent
        calls: list[str] = []
        replaced = False

        def wrapped(trusted_root: Path, relative_path: str) -> object:
            nonlocal replaced
            calls.append(relative_path)
            if relative_path != selected_rel:
                return real_snapshot(trusted_root, relative_path)

            def observer(stage: str) -> None:
                nonlocal replaced
                if stage == "after_leaf_read" and not replaced:
                    replacement.replace(target)
                    replaced = True

            return real_snapshot(trusted_root, relative_path, _observer=observer)

        return wrapped, calls

    def test_external_semantic_validators_read_standalone_pack(self) -> None:
        pack_rows = (
            "| `scope_refs` | opened/read: `docs/playbooks/analysis_wave.md` |\n"
            "| `documentation_impact_seed` | docs impact |\n"
            "| `dependent_inventory_mutable_surfaces` | mutable scripts/plan_lint.py |\n"
            "| `requirement_slices` | slice_kind=developer_wave; invalid fixture |\n"
            "| `reviewability_seed` | focused test |\n"
            "| `runner_handoff_seed` | frontier only |\n"
            "| `route_recommendation` | `developer_wave` |\n"
            "| `accepted_route` | `reject` |\n"
            "| `execution_budget` | budget_status=exhausted; source_ref_floor=1; route_iteration_limit=1; needs_analysis_depth_cap=2; current_needs_analysis_depth=1; stop_owner=Architect; exhaustion_action=architect_recheck |\n"
            "| `stale_trigger` | source_subject_baseline=authority; current_source_subject=authority |"
        )
        with temporary_git_root() as tmpdir:
            plan = self._write_fixture(Path(tmpdir), pack_rows=pack_rows)
            findings = MODULE.lint_plan(plan)

        messages = "\n".join(finding.message for finding in findings)
        self.assertIn("requirement_slices.slice_kind", messages)
        self.assertIn("must not define literal accepted-route fields", messages)
        self.assertIn("Analysis route lifecycle stop", messages)
        self.assertIn("budget_status=exhausted", messages)

    def test_preboundary_angle_duplicate_is_hard_red_without_mirror_lifecycle(self) -> None:
        with temporary_git_root() as tmpdir:
            stem = "260729_0958_process_lint_angle_external_authority"
            canonical_ref = f"docs/analysis_packs/{stem}.md#Analysis-pack"
            plan = self._write_fixture(
                Path(tmpdir),
                stem=stem,
                ref_row=f"| `analysis_pack_ref` | `{canonical_ref}` <human-note> |",
                origin_rows="| `execution_budget` | budget_status=exhausted; current_needs_analysis_depth=99 |",
            )
            findings = MODULE.lint_plan(plan)

        authority = [finding for finding in findings if "analysis_pack_authority_invalid" in finding.message]
        lifecycle = [finding for finding in findings if finding.message.startswith("Analysis route lifecycle")]
        self.assertEqual(len(authority), 1)
        self.assertEqual(authority[0].severity, "ERROR")
        self.assertIn("operational_duplicate", authority[0].message)
        self.assertEqual(lifecycle, [])

    def test_identity_failure_has_no_plan_mirror_fallback(self) -> None:
        with temporary_git_root() as tmpdir:
            plan = self._write_fixture(
                Path(tmpdir),
                origin_rows="| `execution_budget` | budget_status=exhausted; current_needs_analysis_depth=99 |",
                write_pack=False,
            )
            findings = MODULE.lint_plan(plan)

        messages = "\n".join(finding.message for finding in findings)
        self.assertIn("analysis_pack_authority_invalid:pack_missing", messages)
        self.assertNotIn("budget_status=exhausted routes to Architect", messages)

    def test_synchronized_carrier_replacement_is_one_hard_authority_error(self) -> None:
        for carrier, expected in (
            ("draft", "draft_malformed"),
            ("pack", "pack_unreadable"),
        ):
            with self.subTest(carrier=carrier), temporary_git_root() as tmpdir:
                root = Path(tmpdir)
                plan = self._write_fixture(
                    root,
                    origin_rows="| `execution_budget` | budget_status=exhausted; current_needs_analysis_depth=99 |",
                )
                draft_rel = f"docs/code_drafts/{self.STEM}__code_draft.md"
                pack_rel = f"docs/analysis_packs/{self.STEM}.md"
                selected_rel = draft_rel if carrier == "draft" else pack_rel
                expected_calls = [draft_rel] if carrier == "draft" else [draft_rel, pack_rel]
                source = root / selected_rel
                replacement_data = source.read_bytes().replace(
                    b"budget_status=active",
                    b"budget_status=exhausted",
                )
                wrapped, calls = self._replacement_snapshot(root, selected_rel, replacement_data)

                with mock.patch.object(
                    MODULE.plan_status_oracle,
                    "snapshot_regular_or_absent",
                    side_effect=wrapped,
                ):
                    findings = MODULE.lint_plan(plan)

                authority = [
                    finding
                    for finding in findings
                    if "analysis_pack_authority_invalid" in finding.message
                ]
                self.assertEqual(calls, expected_calls)
                self.assertEqual(len(authority), 1)
                self.assertEqual(authority[0].severity, "ERROR")
                self.assertIn(expected, authority[0].message)
                self.assertIn(
                    f"docs/analysis_packs/{self.STEM}.md#Analysis-pack",
                    authority[0].message,
                )
                self.assertFalse(
                    any(
                        finding.message.startswith("Analysis route lifecycle")
                        for finding in findings
                    )
                )
                self.assertNotIn(
                    "budget_status=exhausted routes to Architect",
                    "\n".join(finding.message for finding in findings),
                )

    def test_symlinked_pack_and_draft_are_hard_authority_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            for carrier, expected in (
                ("pack", "pack_unreadable"),
                ("draft", "draft_malformed"),
            ):
                with self.subTest(carrier=carrier):
                    root = base / f"repo-{carrier}"
                    root.mkdir()
                    standalone_git_root(root)
                    plan = self._write_fixture(root)
                    pack = root / f"docs/analysis_packs/{self.STEM}.md"
                    draft = root / f"docs/code_drafts/{self.STEM}__code_draft.md"
                    source = pack if carrier == "pack" else draft
                    outside = base / "outside" / f"{carrier}.md"
                    outside.parent.mkdir(parents=True, exist_ok=True)
                    outside.write_bytes(source.read_bytes())
                    source.unlink()
                    source.symlink_to(outside)

                    findings = MODULE.lint_plan(plan)

                    authority = [
                        finding
                        for finding in findings
                        if "analysis_pack_authority_invalid" in finding.message
                    ]
                    self.assertEqual(len(authority), 1)
                    self.assertEqual(authority[0].severity, "ERROR")
                    self.assertIn(expected, authority[0].message)
                    self.assertFalse(
                        any(
                            finding.message.startswith("Analysis route lifecycle")
                            for finding in findings
                        )
                    )

    INTAKE_STATUSES = (
        "Architect initial draft",
        "Architect draft",
        "Ready for Planner",
        "Planner intake",
        "Ready for Architect response",
        "Architect response",
    )
    EXTERNAL_REQUIRED_STATUSES = (
        "Planner finalize",
        "Ready for Coder",
        "Coder intake",
        "In progress",
        "Ready for Review",
        "Reviewer intake",
        "Reviewer code review",
        "Reviewer visual review",
        "Ready for Arch review",
        "Architect arch review",
        "Done",
    )
    PLAN_RESIDENT_ROWS = (
        "| `analysis_subject` | plan-resident fixture subject |\n"
        "| `route_recommendation` | `developer_wave` |"
    )

    def _write_plan_resident(
        self,
        root: Path,
        *,
        status: str,
        stem: str | None = None,
        rows: str | None = None,
    ) -> Path:
        plan = root / f"docs/plans/{stem or self.STEM}.md"
        plan.parent.mkdir(parents=True, exist_ok=True)
        plan.write_text(
            f"# Plan-resident pack\n\n**Plan type:** dev\n**Status:** {status}\n\n"
            '```json\n{"plan_meta":{"cluster":"process","wave_family":"analysis_wave"}}\n```\n\n'
            "## Analysis pack\n| Field | Value |\n| --- | --- |\n"
            + (self.PLAN_RESIDENT_ROWS if rows is None else rows)
            + "\n",
            encoding="utf-8",
        )
        return plan

    @staticmethod
    def _authority_findings(findings: list[object]) -> list[object]:
        return [
            finding
            for finding in findings
            if "analysis_pack_authority_invalid" in finding.message
        ]

    def test_analysis_wave_requires_ref_from_planner_finalize_regardless_of_filename(self) -> None:
        stems = {
            "current": self.STEM,
            "legacy": "260729_0958_process_legacy_analysis",
        }
        findings: dict[tuple[str, str], list[object]] = {}
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            for label, stem in stems.items():
                for status in ("Architect initial draft", "Planner finalize"):
                    plan = self._write_plan_resident(
                        root / label / status.replace(" ", "_"),
                        status=status,
                        stem=stem,
                    )
                    findings[(label, status)] = MODULE.lint_plan(plan)

        for label in stems:
            with self.subTest(filename=label):
                self.assertEqual(
                    self._authority_findings(findings[(label, "Architect initial draft")]),
                    [],
                )
                missing = self._authority_findings(findings[(label, "Planner finalize")])
                self.assertEqual(len(missing), 1)
                self.assertEqual(missing[0].severity, "ERROR")
                self.assertIn("analysis_pack_authority_invalid:ref_missing", missing[0].message)

    def test_plan_resident_pack_is_clean_on_every_intake_status(self) -> None:
        for status in self.INTAKE_STATUSES:
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmpdir:
                plan = self._write_plan_resident(Path(tmpdir), status=status)
                findings = MODULE.lint_plan(plan)

                self.assertEqual(self._authority_findings(findings), [])

    def test_plan_resident_pack_stays_the_semantic_authority_on_intake(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = self._write_plan_resident(
                Path(tmpdir),
                status="Ready for Planner",
                rows=self.PLAN_RESIDENT_ROWS + "\n| `accepted_route` | `reject` |",
            )
            findings = MODULE.lint_plan(plan)

        messages = "\n".join(finding.message for finding in findings)
        self.assertEqual(self._authority_findings(findings), [])
        self.assertIn("must not define literal accepted-route fields", messages)

    def test_missing_ref_after_intake_is_an_actionable_error(self) -> None:
        pack_rel = f"docs/analysis_packs/{self.STEM}.md"
        for status in self.EXTERNAL_REQUIRED_STATUSES:
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmpdir:
                plan = self._write_plan_resident(Path(tmpdir), status=status)
                authority = self._authority_findings(MODULE.lint_plan(plan))

                self.assertEqual(len(authority), 1)
                self.assertEqual(authority[0].severity, "ERROR")
                message = authority[0].message
                self.assertIn("analysis_pack_authority_invalid:ref_missing", message)
                self.assertIn("From `Planner finalize` on", message)
                self.assertIn(f"into `{pack_rel}` under the same heading", message)
                self.assertIn(f"`analysis_pack_ref` = `{pack_rel}#Analysis-pack`", message)
                self.assertIn(f"`docs/code_drafts/{self.STEM}__code_draft.md`", message)

    def test_external_pack_is_clean_on_every_status(self) -> None:
        for status in (*self.INTAKE_STATUSES, *self.EXTERNAL_REQUIRED_STATUSES, "Superseded"):
            with self.subTest(status=status), temporary_git_root() as tmpdir:
                plan = self._write_fixture(Path(tmpdir), status=status)
                findings = MODULE.lint_plan(plan)

                self.assertEqual(self._authority_findings(findings), [])

    def test_simulated_done_requires_external_pack_for_intake_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            for project in ("resident", "external"):
                (root / project).mkdir()
                standalone_git_root(root / project)
            resident = self._write_plan_resident(root / "resident", status="Architect draft")
            external = self._write_fixture(root / "external", status="Architect draft")
            header_findings = MODULE.lint_plan(resident)
            simulated_findings = MODULE.lint_plan(resident, effective_status="Done")
            external_simulated = MODULE.lint_plan(external, effective_status="Done")
            stdout = io.StringIO()
            argv = ["plan_lint.py", "--as-status", "Done", str(resident)]
            with mock.patch.object(sys, "argv", argv), mock.patch("sys.stdout", stdout):
                exit_code = MODULE.main()

        self.assertEqual(self._authority_findings(header_findings), [])
        simulated = self._authority_findings(simulated_findings)
        self.assertEqual(len(simulated), 1)
        self.assertEqual(simulated[0].severity, "ERROR")
        self.assertIn("analysis_pack_authority_invalid:ref_missing", simulated[0].message)
        self.assertEqual(self._authority_findings(external_simulated), [])
        self.assertNotEqual(exit_code, 0)
        self.assertIn("analysis_pack_authority_invalid:ref_missing", stdout.getvalue())

    def test_superseded_plan_resident_pack_without_transfer_is_not_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = self._write_plan_resident(Path(tmpdir), status="Superseded")
            findings = MODULE.lint_plan(plan)

        self.assertEqual(self._authority_findings(findings), [])

    def test_operational_duplicate_with_ref_holds_on_every_status_family(self) -> None:
        for status in ("Architect initial draft", "Ready for Planner", "Ready for Review", "Superseded"):
            with self.subTest(status=status), temporary_git_root() as tmpdir:
                plan = self._write_fixture(
                    Path(tmpdir),
                    status=status,
                    origin_rows="| `route_recommendation` | `reject` |",
                )
                authority = self._authority_findings(MODULE.lint_plan(plan))

                self.assertEqual(len(authority), 1)
                self.assertEqual(authority[0].severity, "ERROR")
                self.assertIn(
                    "analysis_pack_authority_invalid:operational_duplicate",
                    authority[0].message,
                )

    def test_template_sentinel_counts_as_missing_ref(self) -> None:
        rows = (
            "| `analysis_pack_ref` | `docs/analysis_packs/<PLAN_STEM>.md#Analysis-pack` |\n"
            + self.PLAN_RESIDENT_ROWS
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            intake = self._write_plan_resident(root / "intake", status="Ready for Planner", rows=rows)
            finalize = self._write_plan_resident(root / "finalize", status="Planner finalize", rows=rows)
            intake_findings = MODULE.lint_plan(intake)
            finalize_findings = MODULE.lint_plan(finalize)

        self.assertEqual(self._authority_findings(intake_findings), [])
        finalize_authority = self._authority_findings(finalize_findings)
        self.assertEqual(len(finalize_authority), 1)
        self.assertIn("analysis_pack_authority_invalid:ref_missing", finalize_authority[0].message)

    def test_new_non_analysis_template_placeholder_does_not_select_external_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = Path(tmpdir) / "docs/plans/260730_0246_process_ordinary_scaffold.md"
            plan.parent.mkdir(parents=True, exist_ok=True)
            plan.write_text(
                "# Ordinary\n\n**Plan type:** dev\n**Status:** Architect initial draft\n\n"
                '```json\n{"plan_meta":{"cluster":"process","wave_family":null}}\n```\n\n'
                "## Analysis pack\n| Field | Value |\n| --- | --- |\n"
                "| `analysis_pack_ref` | `docs/analysis_packs/<PLAN_STEM>.md#Analysis-pack` |\n",
                encoding="utf-8",
            )
            findings = MODULE.lint_plan(plan)

        self.assertFalse(
            any("analysis_pack_authority_invalid" in finding.message for finding in findings)
        )

class PlanLintStateTransitionDeclarationsTests(unittest.TestCase):
    STEM = "260801_1306_process_state_transition_fixture"
    PLAN_REL = f"docs/plans/{STEM}.md"
    DRAFT_REL = f"docs/code_drafts/{STEM}__code_draft.md"
    TARGETS = ("docs/a.md", "scripts/a.py")

    def _declarations(
        self,
        *,
        before_carrier: str = "docs/plans/README.md#Reviewability-preflight-receipt",
        before_identity: str = "state-transition-declarations.v1",
        after_carrier: str | None = None,
        after_identity: str | None = None,
        allowed_targets: str = '["state-transition-declarations.v1"]',
        protected_targets: str | None = None,
        on_change: str = "same-file-review-rerun",
    ) -> str:
        after_carrier = after_carrier if after_carrier is not None else before_carrier
        after_identity = after_identity if after_identity is not None else before_identity
        protected_targets = protected_targets if protected_targets is not None else json.dumps(list(self.TARGETS))
        return dedent(
            f"""\
            ### State-transition declarations
            - `before-state`: carrier={before_carrier}; identity={before_identity}; expected=absent
            - `allowed mutation inventory`: writer=coder; entrypoint=fixture; targets={allowed_targets}
            - `after-state`: carrier={after_carrier}; identity={after_identity}; expected=present
            - `protected-target post-review continuity`: targets={protected_targets}; on_change={on_change}
            """
        ).rstrip()

    def _write_pair(
        self,
        root: Path,
        *,
        plan_declarations: str | None,
        draft_declarations: str | None,
        target_paths: tuple[str, ...] | None = None,
    ) -> tuple[Path, list[str], list[tuple[int, str]]]:
        target_paths = target_paths or self.TARGETS
        plan_path = root / self.PLAN_REL
        draft_path = root / self.DRAFT_REL
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        draft_path.parent.mkdir(parents=True, exist_ok=True)
        target_meta = json.dumps(
            [{"path": target, "kind": "doc"} for target in target_paths],
            ensure_ascii=False,
        )
        plan_path.write_text(
            "# Plan: fixture\n\n"
            "**Status:** Coder intake\n\n"
            "## Reviewability preflight receipt\n"
            f"{plan_declarations or 'No opt-in declaration.'}\n",
            encoding="utf-8",
        )
        draft_path.write_text(
            "# Code draft: fixture\n\n"
            "```json\n"
            f'{{"code_draft_meta": {{"plan": "{self.PLAN_REL}", "targets": {target_meta}}}}}\n'
            "```\n\n"
            "## Reviewability preflight receipt\n"
            f"{draft_declarations or 'No opt-in declaration.'}\n",
            encoding="utf-8",
        )
        return plan_path, plan_path.read_text(encoding="utf-8").splitlines(), [(1, self.DRAFT_REL)]

    def _findings(
        self,
        *,
        plan_declarations: str | None,
        draft_declarations: str | None,
        status: str = "Coder intake",
        target_paths: tuple[str, ...] | None = None,
    ) -> list[object]:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path, plan_lines, refs = self._write_pair(
                root,
                plan_declarations=plan_declarations,
                draft_declarations=draft_declarations,
                target_paths=target_paths,
            )
            return MODULE.validate_state_transition_declarations(
                plan_path,
                plan_lines,
                status_value=status,
                code_draft_refs=refs,
                plan_repo_root=root,
            )

    def test_valid_opt_in_pair_has_no_findings(self) -> None:
        declarations = self._declarations()
        self.assertEqual(
            self._findings(plan_declarations=declarations, draft_declarations=declarations),
            [],
        )

    def test_non_opt_in_pair_has_no_findings(self) -> None:
        self.assertEqual(self._findings(plan_declarations=None, draft_declarations=None), [])

    def test_active_block_is_local_only_before_code_draft_required_status(self) -> None:
        findings = self._findings(
            plan_declarations=self._declarations(),
            draft_declarations=None,
            status="Architect draft",
        )
        self.assertEqual(findings, [])

    def test_active_code_draft_block_is_locally_validated_before_code_draft_required_status(self) -> None:
        malformed = self._declarations().replace("writer=coder", "writer=<writer>", 1)
        findings = self._findings(
            plan_declarations=None,
            draft_declarations=malformed,
            status="Architect draft",
        )
        self.assertTrue(findings)
        self.assertTrue(findings[0].file.as_posix().endswith(self.DRAFT_REL))

        protected_mismatch = self._declarations(protected_targets='["docs/a.md"]')
        findings = self._findings(
            plan_declarations=None,
            draft_declarations=protected_mismatch,
            status="Architect draft",
        )
        self.assertIn("must exactly equal normalized", "\n".join(finding.message for finding in findings))

    def test_required_status_requires_presence_in_both_artifacts(self) -> None:
        findings = self._findings(
            plan_declarations=self._declarations(),
            draft_declarations=None,
        )
        self.assertIn(
            "must be present in both plan and code draft",
            "\n".join(finding.message for finding in findings),
        )

    def test_parser_ignores_fenced_commented_and_outside_receipt_examples(self) -> None:
        declarations = self._declarations()
        for text in (
            f"## Reviewability preflight receipt\n<!--\n{declarations}\n-->",
            f"## Reviewability preflight receipt\n```text\n{declarations}\n```",
            f"## Reviewability preflight receipt\n~~~~ markdown\n{declarations}\n~~~~",
            f"## Reviewability preflight receipt\n````text\n{declarations}\n````",
            "## Reviewability preflight receipt\n"
            + "\n".join(f"    {line}" for line in declarations.splitlines()),
            f"{declarations}\n\n## Reviewability preflight receipt\nNo opt-in declaration.",
        ):
            with self.subTest(text=text[:30]):
                result = MODULE.parse_state_transition_declarations(
                    Path("docs/plans/260801_1306_fixture.md"),
                    text.splitlines(),
                )
                self.assertEqual(result.heading_lines, ())
                self.assertEqual(result.findings, ())

    def test_inline_code_comment_delimiter_does_not_hide_active_declaration_block(self) -> None:
        malformed = self._declarations().replace("expected=absent", "expected=<state>", 1)
        findings = self._findings(
            plan_declarations="Inline-code marker `<!--` is documentation, not a comment.\n" + malformed,
            draft_declarations=self._declarations(),
        )
        self.assertIn("contains placeholder `expected`", "\n".join(finding.message for finding in findings))

    def test_multiline_inline_code_comment_delimiter_does_not_hide_active_declaration_block(self) -> None:
        malformed = self._declarations().replace("expected=absent", "expected=<state>", 1)
        findings = self._findings(
            plan_declarations="Inline-code marker starts `\n<!--\nand closes here`\n" + malformed,
            draft_declarations=self._declarations(),
        )
        self.assertIn("contains placeholder `expected`", "\n".join(finding.message for finding in findings))

    def test_unclosed_inline_code_delimiter_does_not_hide_active_declaration_block(self) -> None:
        malformed = self._declarations().replace("expected=absent", "expected=<state>", 1)
        findings = self._findings(
            plan_declarations="Unclosed inline-code delimiter `\n" + malformed,
            draft_declarations=self._declarations(),
        )
        self.assertIn("contains placeholder `expected`", "\n".join(finding.message for finding in findings))

    def test_escaped_html_comment_opener_does_not_hide_active_declaration_block(self) -> None:
        malformed = self._declarations().replace("expected=absent", "expected=<state>", 1)
        for escaped_opener in (r"\<!--", r"\\\<!--"):
            with self.subTest(escaped_opener=escaped_opener):
                findings = self._findings(
                    plan_declarations=f"Escaped marker {escaped_opener} is literal text.\n" + malformed,
                    draft_declarations=self._declarations(),
                )
                self.assertIn(
                    "contains placeholder `expected`",
                    "\n".join(finding.message for finding in findings),
                )

    def test_midline_html_comment_openers_do_not_hide_active_declaration_block(self) -> None:
        malformed = self._declarations().replace("expected=absent", "expected=<state>", 1)
        for opener in (
            "Narrative starts <!--",
            r"Two backslashes \\<!-- begin an inline comment.",
            r"Escaped marker \<!-- stays literal; actual <!-- starts an inline comment.",
            "`x`<!--",
        ):
            with self.subTest(opener=opener):
                findings = self._findings(
                    plan_declarations=f"{opener}\n" + malformed,
                    draft_declarations=self._declarations(),
                )
                self.assertIn(
                    "contains placeholder `expected`",
                    "\n".join(finding.message for finding in findings),
                )

    def test_block_level_html_comment_openers_remain_active(self) -> None:
        declarations = self._declarations()
        for indentation in ("", " ", "   "):
            with self.subTest(indentation=repr(indentation)):
                text = (
                    "## Reviewability preflight receipt\n"
                    f"{indentation}<!-- block HTML comment\n"
                    f"{declarations}\n"
                    "-->"
                )
                result = MODULE.parse_state_transition_declarations(
                    Path("docs/plans/260801_1306_fixture.md"),
                    text.splitlines(),
                )
                self.assertEqual(result.heading_lines, ())
                self.assertEqual(result.findings, ())

    def test_html_comment_closer_inside_inline_code_does_not_hide_active_declaration_block(self) -> None:
        malformed = self._declarations().replace("expected=absent", "expected=<state>", 1)
        for opener in ("<!-- -->", "<!-- `-->"):
            with self.subTest(opener=opener):
                findings = self._findings(
                    plan_declarations=f"{opener}\n" + malformed,
                    draft_declarations=self._declarations(),
                )
                self.assertIn("contains placeholder `expected`", "\n".join(finding.message for finding in findings))

    def test_raw_html_attribute_comment_marker_does_not_hide_active_declaration_block(self) -> None:
        malformed = self._declarations().replace("expected=absent", "expected=<state>", 1)
        for prefix in (
            'Raw HTML <span data-marker="<!--"> literal.',
            'Raw HTML <span data-marker="\n<!--"> literal.',
        ):
            with self.subTest(prefix=prefix):
                findings = self._findings(
                    plan_declarations=f"{prefix}\n" + malformed,
                    draft_declarations=self._declarations(),
                )
                self.assertIn(
                    "contains placeholder `expected`",
                    "\n".join(finding.message for finding in findings),
                )

    def test_raw_html_block_comment_marker_does_not_hide_active_declaration_block(self) -> None:
        malformed = self._declarations().replace("expected=absent", "expected=<state>", 1)
        for tag in ("script", "pre", "style", "textarea"):
            with self.subTest(tag=tag):
                findings = self._findings(
                    plan_declarations=f"<{tag}>\nliteral marker = \"<!--\"\n</{tag}>\n" + malformed,
                    draft_declarations=self._declarations(),
                )
                self.assertIn(
                    "contains placeholder `expected`",
                    "\n".join(finding.message for finding in findings),
                )

    def test_raw_html_literal_block_comment_marker_does_not_hide_active_declaration_block(self) -> None:
        malformed = self._declarations().replace("expected=absent", "expected=<state>", 1)
        for opening_line, closing_line in (
            ("<![CDATA[", "]]>"),
            ("<?php", "?>"),
            ("<!DOCTYPE fixture [", ">"),
        ):
            with self.subTest(opening_line=opening_line):
                findings = self._findings(
                    plan_declarations=f"{opening_line}\nliteral marker = \"<!--\"\n{closing_line}\n" + malformed,
                    draft_declarations=self._declarations(),
                )
                self.assertIn(
                    "contains placeholder `expected`",
                    "\n".join(finding.message for finding in findings),
                )

    def test_markdown_inline_link_title_comment_marker_does_not_hide_active_declaration_block(self) -> None:
        malformed = self._declarations().replace("expected=absent", "expected=<state>", 1)
        for link in (
            '[link](https://example.test "<!--")',
            '[literal <!-- marker](https://example.test)',
        ):
            with self.subTest(link=link):
                findings = self._findings(
                    plan_declarations=f"Markdown {link} title.\n" + malformed,
                    draft_declarations=self._declarations(),
                )
                self.assertIn("contains placeholder `expected`", "\n".join(finding.message for finding in findings))

    def test_markdown_reference_definition_title_comment_marker_does_not_hide_active_declaration_block(self) -> None:
        malformed = self._declarations().replace("expected=absent", "expected=<state>", 1)
        for definition in (
            '[ref]: https://example.test "<!--"\n',
            '[ref]: https://example.test\n  "<!--"\n',
        ):
            with self.subTest(definition=definition):
                findings = self._findings(
                    plan_declarations=definition + malformed,
                    draft_declarations=self._declarations(),
                )
                self.assertIn("contains placeholder `expected`", "\n".join(finding.message for finding in findings))

    def test_markdown_full_reference_link_label_comment_marker_does_not_hide_active_declaration_block(self) -> None:
        malformed = self._declarations().replace("expected=absent", "expected=<state>", 1)
        findings = self._findings(
            plan_declarations='[ref]: https://example.test\nMarkdown [literal <!-- marker][ref].\n' + malformed,
            draft_declarations=self._declarations(),
        )
        self.assertIn("contains placeholder `expected`", "\n".join(finding.message for finding in findings))

    def test_markdown_shortcut_reference_link_label_comment_marker_does_not_hide_active_declaration_block(self) -> None:
        malformed = self._declarations().replace("expected=absent", "expected=<state>", 1)
        findings = self._findings(
            plan_declarations='[literal <!-- marker]: https://example.test\nMarkdown [literal <!-- marker].\n' + malformed,
            draft_declarations=self._declarations(),
        )
        self.assertIn("contains placeholder `expected`", "\n".join(finding.message for finding in findings))

    def test_indented_and_container_html_comment_openers_do_not_hide_active_declaration_block(self) -> None:
        malformed = self._declarations().replace("expected=absent", "expected=<state>", 1)
        for opener in (
            "    <!-- indented code",
            " \t<!-- tab-expanded indented code",
            "  \t<!-- tab-expanded indented code",
            "   \t<!-- tab-expanded indented code",
            "> <!-- quoted container",
            "- <!-- list container",
        ):
            with self.subTest(opener=opener):
                findings = self._findings(
                    plan_declarations=f"{opener}\n" + malformed,
                    draft_declarations=self._declarations(),
                )
                self.assertIn(
                    "contains placeholder `expected`",
                    "\n".join(finding.message for finding in findings),
                )

    def test_list_continuation_html_comment_opener_does_not_hide_active_declaration_block(self) -> None:
        malformed = self._declarations().replace("expected=absent", "expected=<state>", 1)
        for opener in (
            "- item\n  <!-- list continuation",
            "1. item\n   <!-- ordered-list continuation",
            "-     item\n  <!-- wide-whitespace list continuation",
            "-      item\n  <!-- wider-whitespace list continuation",
            "-   \titem\n  <!-- tab-expanded list continuation",
            "1.     item\n   <!-- wide-whitespace ordered-list continuation",
            "-\n  <!-- empty-list continuation",
            "-   \n  <!-- empty-list trailing-whitespace continuation",
            "1.\n   <!-- empty-ordered-list continuation",
            "1. \t\n   <!-- empty-ordered-list trailing-whitespace continuation",
            "- outer\n  - nested\n  <!-- outer-list continuation after nested item",
            "- outer\n  - nested\n\n  <!-- outer-list continuation after nested blank separator",
            "1. outer\n   1. nested\n   <!-- outer-ordered-list continuation after nested item",
        ):
            with self.subTest(opener=opener):
                findings = self._findings(
                    plan_declarations=f"{opener}\n" + malformed,
                    draft_declarations=self._declarations(),
                )
                self.assertIn(
                    "contains placeholder `expected`",
                    "\n".join(finding.message for finding in findings),
                )

    def test_lazy_container_html_comment_opener_does_not_hide_active_declaration_block(self) -> None:
        malformed = self._declarations().replace("expected=absent", "expected=<state>", 1)
        for opener in (
            "- paragraph\nlazy continuation <!-- list-local comment",
            "- paragraph\nfirst lazy continuation\nsecond lazy continuation <!-- list-local comment",
            "> paragraph\nlazy continuation <!-- blockquote-local comment",
            "> paragraph\nfirst lazy continuation\nsecond lazy continuation <!-- blockquote-local comment",
            "- outer\n  - nested\nouter lazy continuation <!-- outer-list-local comment",
        ):
            with self.subTest(opener=opener):
                findings = self._findings(
                    plan_declarations=f"{opener}\n" + malformed,
                    draft_declarations=self._declarations(),
                )
                self.assertIn(
                    "contains placeholder `expected`",
                    "\n".join(finding.message for finding in findings),
                )

    def test_bare_html_comment_ends_lazy_container_and_stays_ignored(self) -> None:
        declarations = self._declarations()
        for container in ("- list item", "> blockquote item"):
            for separator in ("", "\n"):
                with self.subTest(container=container, separator=separator):
                    text = (
                        "## Reviewability preflight receipt\n"
                        f"{container}\n"
                        f"{separator}<!-- true top-level comment\n"
                        f"{declarations}\n"
                        "-->"
                    )
                    result = MODULE.parse_state_transition_declarations(
                        Path("docs/plans/260801_1306_fixture.md"),
                        text.splitlines(),
                    )
                    self.assertEqual(result.heading_lines, ())
                    self.assertEqual(result.findings, ())

    def test_template_examples_stay_non_active(self) -> None:
        for template in (Path("docs/plans/_template.md"), Path("docs/code_drafts/_template.md")):
            result = MODULE.parse_state_transition_declarations(template, template.read_text(encoding="utf-8").splitlines())
            self.assertEqual(result.heading_lines, (), template)

    def test_readme_canonical_grammar_keeps_values_unquoted(self) -> None:
        readme = Path("docs/plans/README.md").read_text(encoding="utf-8")
        expected_rows = (
            "- `before-state`: carrier=<literal>; identity=<literal>; expected=<literal>",
            '- `allowed mutation inventory`: writer=<literal>; entrypoint=<literal>; targets=["<canonical mutation identifier>", ...]',
            "- `after-state`: carrier=<literal>; identity=<literal>; expected=<literal>",
            '- `protected-target post-review continuity`: targets=["<repo-relative POSIX path>", ...]; on_change=same-file-review-rerun',
        )
        for row in expected_rows:
            self.assertIn(row, readme)
        self.assertNotIn("- `before-state`: `carrier=", readme)

    def test_outer_separator_whitespace_normalizes_but_scalar_case_does_not(self) -> None:
        declarations = self._declarations().replace(
            "- `before-state`: carrier=",
            "- `before-state` : carrier=",
        ).replace(
            "; identity=",
            " ; identity=",
        )
        self.assertEqual(
            self._findings(plan_declarations=declarations, draft_declarations=self._declarations()),
            [],
        )

        case_drift = self._declarations().replace("expected=absent", "expected=ABSENT", 1)
        findings = self._findings(plan_declarations=case_drift, draft_declarations=self._declarations())
        self.assertIn("parity mismatch", "\n".join(finding.message for finding in findings))

    def test_missing_duplicate_unknown_and_malformed_labels_fail(self) -> None:
        declarations = self._declarations()
        variants = {
            "missing": declarations.replace(
                "- `after-state`: carrier=docs/plans/README.md#Reviewability-preflight-receipt; identity=state-transition-declarations.v1; expected=present\n",
                "",
            ),
            "duplicate": declarations.replace(
                "- `after-state`:",
                "- `before-state`: carrier=docs/plans/README.md#Reviewability-preflight-receipt; identity=state-transition-declarations.v1; expected=absent\n- `after-state`:",
            ),
            "unknown": declarations + "\n- `unknown-state`: value=fixture",
            "malformed": declarations.replace("- `before-state`:", "- before-state:"),
        }
        for name, variant in variants.items():
            with self.subTest(name=name):
                findings = self._findings(plan_declarations=variant, draft_declarations=self._declarations())
                self.assertTrue(findings, name)
                self.assertTrue(
                    any("State-transition declarations" in finding.message for finding in findings),
                    [finding.message for finding in findings],
                )

    def test_declaration_rows_after_prose_still_fail(self) -> None:
        declarations = self._declarations()
        duplicate_after_prose = declarations + "\n\nNarrative detail.\n" + declarations.splitlines()[1]
        findings = self._findings(
            plan_declarations=duplicate_after_prose,
            draft_declarations=declarations,
        )
        self.assertIn("repeats label `before-state`", "\n".join(finding.message for finding in findings))

        unknown_after_prose = declarations + "\n\nNarrative detail.\n- `unknown-state`: value=fixture"
        findings = self._findings(
            plan_declarations=unknown_after_prose,
            draft_declarations=declarations,
        )
        self.assertIn("unknown label `unknown-state`", "\n".join(finding.message for finding in findings))

        metadata_after_prose = declarations + "\n\nNarrative detail.\n- `truth-host metadata`: retained."
        self.assertEqual(
            self._findings(
                plan_declarations=metadata_after_prose,
                draft_declarations=metadata_after_prose,
            ),
            [],
        )

    def test_subfield_grammar_placeholder_and_before_after_drift_fail(self) -> None:
        declarations = self._declarations()
        variants = {
            "order": declarations.replace(
                "carrier=docs/plans/README.md#Reviewability-preflight-receipt; identity=state-transition-declarations.v1; expected=absent",
                "identity=state-transition-declarations.v1; carrier=docs/plans/README.md#Reviewability-preflight-receipt; expected=absent",
                1,
            ),
            "placeholder": declarations.replace("expected=absent", "expected=<state>", 1),
            "todo-placeholder": declarations.replace("expected=absent", "expected=TODO", 1),
            "unknown-placeholder": declarations.replace("writer=coder", "writer=UNKNOWN", 1),
            "carrier-drift": self._declarations(after_carrier="docs/plans/other.md#Receipt"),
            "identity-drift": self._declarations(after_identity="other.v1"),
            "backticked-value": declarations.replace("writer=coder", "writer=`coder`", 1),
        }
        for name, variant in variants.items():
            with self.subTest(name=name):
                findings = self._findings(plan_declarations=variant, draft_declarations=variant)
                self.assertTrue(findings, name)

        for placeholder in ("TODO later", "FIXME: choose", "UNKNOWN reason", "TBC soon", "N/A because"):
            with self.subTest(placeholder=placeholder):
                variant = declarations.replace("expected=absent", f"expected={placeholder}", 1)
                findings = self._findings(plan_declarations=variant, draft_declarations=variant)
                self.assertIn("contains placeholder `expected`", "\n".join(finding.message for finding in findings))

    def test_protected_paths_are_strict_and_exactly_match_code_draft_targets(self) -> None:
        variants = {
            "invalid-json": "not-json",
            "placeholder": '["docs/<repo-relative POSIX path>.md", "scripts/a.py"]',
            "unsorted": '["scripts/a.py", "docs/a.md"]',
            "duplicate": '["docs/a.md", "docs/a.md"]',
            "absolute": '["/docs/a.md", "scripts/a.py"]',
            "backslash": '["docs\\\\a.md", "scripts/a.py"]',
            "dot": '["./docs/a.md", "scripts/a.py"]',
            "traversal": '["docs/../a.md", "scripts/a.py"]',
        }
        for name, protected_targets in variants.items():
            with self.subTest(name=name):
                declarations = self._declarations(protected_targets=protected_targets)
                findings = self._findings(plan_declarations=declarations, draft_declarations=declarations)
                self.assertTrue(findings, name)

        declarations = self._declarations()
        findings = self._findings(
            plan_declarations=declarations,
            draft_declarations=declarations,
            target_paths=("docs/a.md", "scripts/a.py", "scripts/extra.py"),
        )
        self.assertIn("must exactly equal normalized", "\n".join(finding.message for finding in findings))

    def test_allowed_mutation_inventory_is_not_reinterpreted_as_protected_paths(self) -> None:
        declarations = self._declarations(allowed_targets='["writer:state-transition"]')
        self.assertEqual(
            self._findings(plan_declarations=declarations, draft_declarations=declarations),
            [],
        )

    def test_subfield_separator_whitespace_is_normalized(self) -> None:
        declarations = self._declarations().replace(
            "carrier=docs/plans/README.md#Reviewability-preflight-receipt",
            "carrier = docs/plans/README.md#Reviewability-preflight-receipt",
            1,
        )
        self.assertEqual(
            self._findings(plan_declarations=declarations, draft_declarations=self._declarations()),
            [],
        )

    def test_literal_rerun_route_and_heading_are_required(self) -> None:
        invalid_route = self._declarations(on_change="automatic-rerun")
        findings = self._findings(plan_declarations=invalid_route, draft_declarations=invalid_route)
        self.assertIn("same-file-review-rerun", "\n".join(finding.message for finding in findings))

        invalid_heading = self._declarations().replace(
            "### State-transition declarations",
            "### State Transition declarations",
        )
        findings = self._findings(plan_declarations=invalid_heading, draft_declarations=invalid_heading)
        self.assertIn("heading must be literal", "\n".join(finding.message for finding in findings))

class SemanticReviewObservationContractTests(unittest.TestCase):
    PLAN_REL = "docs/plans/260801_1622_semantic_fixture.md"
    DRAFT_REL = "docs/code_drafts/260801_1622_semantic_fixture__code_draft.md"
    REVIEW_REL = "docs/code_reviews/260801_1622_semantic_fixture.md"
    SNAPSHOT = "semantic-fixture-target"

    def _not_applicable_machine_authority_decision(self) -> dict[str, str]:
        return {
            "schema_version": MODULE.plan_status_oracle.MACHINE_AUTHORITY_DECISION_SCHEMA,
            "applicability": "not_applicable",
            "reason_code": "docs_or_tests_only",
        }

    def _not_applicable_machine_authority_ref(self) -> dict[str, str]:
        decision = self._not_applicable_machine_authority_decision()
        return {
            "applicability": "not_applicable",
            "reason_code": decision["reason_code"],
            "carrier_sha256": MODULE.plan_status_oracle.machine_authority_decision_sha256(decision),
        }

    def _declarations(self) -> str:
        targets = '["scripts/example.py"]'
        return dedent(
            f"""\
            ### State-transition declarations
            - `before-state`: carrier=docs/plans/README.md#semantic; identity=semantic-review-observation.v1; expected=absent
            - `allowed mutation inventory`: writer=coder; entrypoint=semantic-fixture; targets={targets}
            - `after-state`: carrier=docs/plans/README.md#semantic; identity=semantic-review-observation.v1; expected=present
            - `protected-target post-review continuity`: targets={targets}; on_change=same-file-review-rerun
            """
        ).rstrip()

    def _review_text(
        self,
        snapshot: str,
        *,
        status: str = "✅ OK",
        blockers: tuple[tuple[int, str], ...] = (),
    ) -> str:
        blocker_section = ""
        if blockers:
            records = "\n\n".join(
                dedent(
                    f"""\
                    ### B{number}) semantic fixture blocker

                    - Blocker ID: B{number}
                    - Current state: {state}
                    """
                ).rstrip()
                for number, state in blockers
            )
            blocker_section = f"\n\n## S1 Blocker\n\n{records}"
        return (
            dedent(
                f"""\
                # Code review: semantic fixture

                **Date:** 2026-08-02 20:07 MSK
                **Target:** {snapshot}
                **Status:** {status}

                ## reviewer_code_contracts

                - Lane status: complete

                ## Lane synthesis / aggregate verdict

                - Aggregate status: {status}
                """
            ).rstrip()
            + blocker_section
            + "\n"
        )

    def _write_fixture(self, root: Path, evidence: str = "") -> Path:
        (root / ".git").mkdir()
        ensure_fixture_git(root)
        plan = root / self.PLAN_REL
        draft = root / self.DRAFT_REL
        review = root / self.REVIEW_REL
        target = root / "scripts/example.py"
        for item in (plan, draft, review, target):
            item.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# fixture\n", encoding="utf-8")
        review.write_text(self._review_text(self.SNAPSHOT), encoding="utf-8")
        draft_payload = {
            "code_draft_meta": {
                "plan": self.PLAN_REL,
                "targets": [{"path": "scripts/example.py", "kind": "py"}],
                "deleted_paths": [],
                "machine_authority_decision_ref": self._not_applicable_machine_authority_ref(),
            }
        }
        draft_text = dedent(
            """\
                # Code draft: semantic fixture

                ```json
                __DRAFT_PAYLOAD__
                ```

                ## Reviewability preflight receipt

                __DECLARATIONS__
                """
        ).replace("__DRAFT_PAYLOAD__", json.dumps(draft_payload, indent=2)).replace(
            "__DECLARATIONS__", self._declarations()
        )
        draft.write_text(draft_text, encoding="utf-8")
        plan.write_text(self._plan_text(evidence), encoding="utf-8")
        return plan

    def _plan_text(
        self,
        evidence: str,
        *,
        status: str = "Ready for Review",
        review_notes: str = "",
    ) -> str:
        plan_meta = {
            "plan_meta": {
                "machine_authority_decision": self._not_applicable_machine_authority_decision(),
            }
        }
        return dedent(
            f"""\
            # Plan: semantic fixture

            **Date:** 2026-08-02 18:00 MSK
            **Plan type:** dev
            **Status:** {status}

            ## Meta
            ```json
            __PLAN_META__
            ```

            - Code draft(s): `{self.DRAFT_REL}`

            ## Decisions (final)
            - Stable contract decision.

            ## Scope
            - [ ] semantic fixture scope.

            ## Out of scope
            - Nothing else.

            ## Changes (by area)
            - Helper: fixture only.

            ## Acceptance criteria / DoD
            - [ ] stable fixture.

            ## Tests
            - focused fixture test.

            ## Commands
            - python3 -B scripts/test_plan_lint.py

            ## Reviewability preflight receipt

            ### Semantic review observation
            - `schema=semantic_review_observation.v1`
            - `mode=required`
            - `writer=reviewer_code_contracts`

            __DECLARATIONS__

            ## Review artifacts

            - Code review (primary): `{self.REVIEW_REL}`
            __REVIEW_NOTES__

            ## Evidence
            __EVIDENCE__
            """
        ).replace("__PLAN_META__", json.dumps(plan_meta, indent=2)).replace(
            "__DECLARATIONS__", self._declarations()
        ).replace("__REVIEW_NOTES__", review_notes).replace("__EVIDENCE__", evidence)

    def _risk_fence(
        self,
        *,
        run_id: str = "reviewer_code_risk:fixture:20260802T180000Z",
        snapshot: str | None = None,
        current: bool = True,
    ) -> str:
        snapshot = snapshot or self.SNAPSHOT
        return dedent(
            f"""\
            ```json
            {{
              "run_id": "{run_id}",
              "lane_id": "reviewer_code_risk",
              "target_snapshot": "{snapshot}",
              "lane_status": "complete",
              "current": {str(current).lower()}
            }}
            ```
            """
        ).rstrip()

    def _proposal_fence(self, proposal: dict[str, object] | None = None) -> str:
        proposal = proposal or {
            "schema_version": "semantic_review_observation_proposal.v1",
            "progress_verdict": "first_observation",
            "progress_evidence_refs": [f"{self.REVIEW_REL}#aggregate"],
            "blockers": [],
            "resolved_predecessor_blocker_refs": [],
        }
        return "```json\n" + json.dumps(proposal, ensure_ascii=False, indent=2) + "\n```"

    def _final_fence(self, observation: dict[str, object]) -> str:
        return "```json\n" + json.dumps(observation, ensure_ascii=False, indent=2) + "\n```"

    def _first_blocker_proposal(self) -> dict[str, object]:
        return {
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

    def _accepted_first_blocker(
        self, root: Path
    ) -> tuple[Path, dict[str, object], dict[str, object], str]:
        plan = self._write_fixture(root)
        (root / self.REVIEW_REL).write_text(
            self._review_text(self.SNAPSHOT, status="❌ S1 blocker(ы)", blockers=((1, "open"),)),
            encoding="utf-8",
        )
        proposal = self._first_blocker_proposal()
        source_evidence = self._risk_fence() + "\n\n" + self._proposal_fence(proposal)
        plan.write_text(self._plan_text(source_evidence), encoding="utf-8")
        materialization = MODULE.build_semantic_review_observation_report(plan)["materialization"]
        assert isinstance(materialization, dict)
        observation = materialization["observation"]
        assert isinstance(observation, dict)
        accepted_evidence = source_evidence + "\n\n" + self._final_fence(observation)
        plan.write_text(self._plan_text(accepted_evidence), encoding="utf-8")
        accepted_report = MODULE.build_semantic_review_observation_report(plan)
        self.assertEqual((accepted_report["state"], accepted_report["reason_code"]), ("valid", "current_observation_valid"))
        return plan, proposal, observation, accepted_evidence

    def test_active_clean_waiting_and_role_proposal_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = self._write_fixture(root)
            report = MODULE.build_semantic_review_observation_report(plan)
            self.assertEqual((report["state"], report["reason_code"]), ("not_available", "risk_generation_not_available"))
            self.assertEqual(set(report), {
                "schema_version", "state", "reason_code", "candidate_machine_fields", "materialization", "validated_chain", "errors"
            })

            plan.write_text(self._plan_text(self._risk_fence()), encoding="utf-8")
            report = MODULE.build_semantic_review_observation_report(plan)
            self.assertEqual((report["state"], report["reason_code"]), ("ready_to_materialize", "role_proposal_required"))

            evidence = self._risk_fence() + "\n\n" + self._proposal_fence()
            plan.write_text(self._plan_text(evidence), encoding="utf-8")
            report = MODULE.build_semantic_review_observation_report(plan)
            self.assertEqual((report["state"], report["reason_code"]), ("ready_to_materialize", "observation_not_materialized"))
            materialization = report["materialization"]
            self.assertIsInstance(materialization, dict)
            assert isinstance(materialization, dict)
            observation = materialization["observation"]
            self.assertIsInstance(observation, dict)
            assert isinstance(observation, dict)
            self.assertEqual(observation["schema_version"], "semantic_review_observation.v1")
            self.assertEqual(observation["predecessor_observation_id"], None)

            final_fence = "```json\n" + json.dumps(observation, ensure_ascii=False, indent=2) + "\n```"
            plan.write_text(self._plan_text(evidence + "\n\n" + final_fence), encoding="utf-8")
            report = MODULE.build_semantic_review_observation_report(plan)
            self.assertEqual((report["state"], report["reason_code"]), ("valid", "current_observation_valid"))
            self.assertEqual(report["validated_chain"], [observation["observation_id"]])

    def test_manual_machine_field_and_duplicate_proposal_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = self._write_fixture(root)
            evidence = self._risk_fence() + "\n\n" + self._proposal_fence()
            plan.write_text(self._plan_text(evidence), encoding="utf-8")
            materialization = MODULE.build_semantic_review_observation_report(plan)["materialization"]
            assert isinstance(materialization, dict)
            observation = dict(materialization["observation"])
            observation["observation_id"] = "sro_" + "0" * 64
            final_fence = "```json\n" + json.dumps(observation, ensure_ascii=False, indent=2) + "\n```"
            plan.write_text(self._plan_text(evidence + "\n\n" + final_fence), encoding="utf-8")
            report = MODULE.build_semantic_review_observation_report(plan)
            self.assertEqual(report["state"], "blocked")
            self.assertEqual(report["reason_code"], "current_head_mismatch")

            duplicate = self._risk_fence() + "\n\n" + self._proposal_fence() + "\n\n" + self._proposal_fence()
            plan.write_text(self._plan_text(duplicate), encoding="utf-8")
            report = MODULE.build_semantic_review_observation_report(plan)
            self.assertEqual(report["state"], "blocked")

    def test_same_family_reuses_machine_owned_family_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = self._write_fixture(root)
            (root / self.REVIEW_REL).write_text(
                self._review_text(self.SNAPSHOT, status="❌ S1 blocker(ы)", blockers=((1, "open"),)),
                encoding="utf-8",
            )
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
            first_evidence = self._risk_fence() + "\n\n" + self._proposal_fence(first_proposal)
            plan.write_text(self._plan_text(first_evidence), encoding="utf-8")
            first_materialization = MODULE.build_semantic_review_observation_report(plan)["materialization"]
            assert isinstance(first_materialization, dict)
            first_observation = first_materialization["observation"]
            assert isinstance(first_observation, dict)
            first_fence = "```json\n" + json.dumps(first_observation, ensure_ascii=False, indent=2) + "\n```"

            next_snapshot = self.SNAPSHOT
            (root / self.REVIEW_REL).write_text(
                self._review_text(next_snapshot, status="❌ S1 blocker(ы)", blockers=((1, "open"),)),
                encoding="utf-8",
            )
            same_proposal = {
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
            evidence = (
                self._risk_fence(current=False)
                + "\n\n"
                + self._proposal_fence(first_proposal)
                + "\n\n"
                + first_fence
                + "\n\n"
                + self._risk_fence(
                    run_id="reviewer_code_risk:fixture:20260802T190000Z",
                    snapshot=next_snapshot,
                )
                + "\n\n"
                + self._proposal_fence(same_proposal)
            )
            plan.write_text(self._plan_text(evidence), encoding="utf-8")
            report = MODULE.build_semantic_review_observation_report(plan)
            self.assertEqual((report["state"], report["reason_code"]), ("ready_to_materialize", "observation_not_materialized"))
            materialization = report["materialization"]
            assert isinstance(materialization, dict)
            observation = materialization["observation"]
            assert isinstance(observation, dict)
            self.assertEqual(
                observation["blockers"][0]["blocker_family_id"],
                first_observation["blockers"][0]["blocker_family_id"],
            )

    def test_unbound_and_nonadjacent_carriers_fail_before_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = self._write_fixture(root)
            unbound_final = {
                "schema_version": "semantic_review_observation.v1",
                "observation_id": "sro_" + "0" * 64,
            }
            plan.write_text(self._plan_text(self._final_fence(unbound_final)), encoding="utf-8")
            report = MODULE.build_semantic_review_observation_report(plan)
            self.assertEqual((report["state"], report["reason_code"]), ("blocked", "risk_lane_selection_blocked"))

            evidence = (
                self._risk_fence()
                + "\n\n"
                + self._proposal_fence()
                + "\n\n"
                + self._risk_fence(
                    run_id="reviewer_code_risk:fixture:20260802T181000Z",
                    current=False,
                )
            )
            plan.write_text(self._plan_text(evidence), encoding="utf-8")
            report = MODULE.build_semantic_review_observation_report(plan)
            self.assertEqual((report["state"], report["reason_code"]), ("blocked", "risk_lane_selection_blocked"))
            self.assertTrue(any(error["code"] == "semantic_proposal_positional_pairing_invalid" for error in report["errors"]))

    def test_resolved_and_independent_lineage_materialize_machine_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan, first_proposal, first_observation, _accepted_evidence = self._accepted_first_blocker(root)
            next_snapshot = self.SNAPSHOT
            (root / self.REVIEW_REL).write_text(
                self._review_text(next_snapshot, status="❌ S1 blocker(ы)", blockers=((2, "open"),)),
                encoding="utf-8",
            )
            next_proposal = {
                "schema_version": "semantic_review_observation_proposal.v1",
                "progress_verdict": "independent_boundary",
                "progress_evidence_refs": [f"{self.REVIEW_REL}#B2"],
                "blockers": [
                    {
                        "blocker_ref": f"{self.REVIEW_REL}#B2",
                        "lineage_relation": "independent_boundary",
                        "predecessor_blocker_ref": None,
                    }
                ],
                "resolved_predecessor_blocker_refs": [f"{self.REVIEW_REL}#B1"],
            }
            evidence = (
                self._risk_fence(current=False)
                + "\n\n"
                + self._proposal_fence(first_proposal)
                + "\n\n"
                + self._final_fence(first_observation)
                + "\n\n"
                + self._risk_fence(
                    run_id="reviewer_code_risk:fixture:20260802T190000Z",
                    snapshot=next_snapshot,
                )
                + "\n\n"
                + self._proposal_fence(next_proposal)
            )
            plan.write_text(self._plan_text(evidence), encoding="utf-8")
            report = MODULE.build_semantic_review_observation_report(plan)
            self.assertEqual((report["state"], report["reason_code"]), ("ready_to_materialize", "observation_not_materialized"))
            materialization = report["materialization"]
            assert isinstance(materialization, dict)
            observation = materialization["observation"]
            assert isinstance(observation, dict)
            first_family = first_observation["blockers"][0]["blocker_family_id"]
            self.assertEqual(observation["resolved_blocker_family_ids"], [first_family])
            self.assertNotEqual(observation["blockers"][0]["blocker_family_id"], first_family)

    def test_accepted_observation_remains_single_node_when_duplicate_generation_is_appended(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan, _proposal, observation, accepted_evidence = self._accepted_first_blocker(root)
            plan.write_text(
                self._plan_text(accepted_evidence + "\n\n" + self._final_fence(observation)),
                encoding="utf-8",
            )
            report = MODULE.build_semantic_review_observation_report(plan)
            self.assertEqual(report["state"], "blocked")
            self.assertEqual(report["validated_chain"], [observation["observation_id"]])
            self.assertTrue(any(error["code"] == "semantic_observation_unbound" for error in report["errors"]))

    def test_selected_risk_requires_successful_lane_aggregate_and_live_blocker_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = self._write_fixture(root)

            running_risk = self._risk_fence().replace('"lane_status": "complete"', '"lane_status": "running"')
            plan.write_text(self._plan_text(running_risk), encoding="utf-8")
            report = MODULE.build_semantic_review_observation_report(plan)
            self.assertEqual((report["state"], report["reason_code"]), ("blocked", "risk_lane_selection_blocked"))
            self.assertTrue(any(error["code"] == "semantic_selected_risk_lane_not_successful" for error in report["errors"]))

            (root / self.REVIEW_REL).write_text(
                "# Code review: semantic fixture\n\n**Target:** " + self.SNAPSHOT + "\n",
                encoding="utf-8",
            )
            plan.write_text(self._plan_text(self._risk_fence()), encoding="utf-8")
            report = MODULE.build_semantic_review_observation_report(plan)
            self.assertEqual((report["state"], report["reason_code"]), ("blocked", "live_review_artifact_invalid"))
            self.assertTrue(any(error["code"] == "semantic_aggregate_verdict_missing_or_ambiguous" for error in report["errors"]))

            (root / self.REVIEW_REL).write_text(
                self._review_text(self.SNAPSHOT)
                .replace("**Status:** ✅ OK", "**Status:** Черновик")
                .replace("Aggregate status: ✅ OK", "Aggregate status: draft"),
                encoding="utf-8",
            )
            plan.write_text(self._plan_text(self._risk_fence()), encoding="utf-8")
            report = MODULE.build_semantic_review_observation_report(plan)
            self.assertEqual((report["state"], report["reason_code"]), ("blocked", "live_review_artifact_invalid"))
            self.assertTrue(any(error["code"] == "semantic_live_review_status_not_final" for error in report["errors"]))
            self.assertTrue(any(error["code"] == "semantic_aggregate_status_not_final" for error in report["errors"]))

            (root / self.REVIEW_REL).write_text(
                self._review_text(self.SNAPSHOT, status="❌ S1 blocker(ы)", blockers=((1, "open"),)),
                encoding="utf-8",
            )
            missing_blocker = self._first_blocker_proposal()
            missing_blocker["blockers"] = [
                {
                    "blocker_ref": f"{self.REVIEW_REL}#B999",
                    "lineage_relation": "first_observation",
                    "predecessor_blocker_ref": None,
                }
            ]
            plan.write_text(
                self._plan_text(self._risk_fence() + "\n\n" + self._proposal_fence(missing_blocker)),
                encoding="utf-8",
            )
            report = MODULE.build_semantic_review_observation_report(plan)
            self.assertEqual((report["state"], report["reason_code"]), ("blocked", "live_review_artifact_invalid"))
            self.assertTrue(any(error["code"] == "semantic_live_review_blocker_ref_missing" for error in report["errors"]))

    def test_canonical_live_blocker_open_set_parity_is_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = self._write_fixture(root)
            review = root / self.REVIEW_REL
            risk = self._risk_fence()

            review.write_text(
                self._review_text(self.SNAPSHOT, blockers=((1, "open"),)),
                encoding="utf-8",
            )
            plan.write_text(self._plan_text(risk), encoding="utf-8")
            report = MODULE.build_semantic_review_observation_report(plan)
            self.assertEqual((report["state"], report["reason_code"]), ("blocked", "live_review_artifact_invalid"))
            self.assertTrue(any(error["code"] == "semantic_live_review_green_open_blockers" for error in report["errors"]))

            review.write_text(
                self._review_text(self.SNAPSHOT, blockers=((1, "historical-fixed"),)).replace(
                    "- Current state: historical-fixed\n", "", 1
                ),
                encoding="utf-8",
            )
            report = MODULE.build_semantic_review_observation_report(plan)
            self.assertEqual((report["state"], report["reason_code"]), ("blocked", "live_review_artifact_invalid"))
            self.assertTrue(
                any(error["code"] == "semantic_live_review_blocker_state_missing_or_ambiguous" for error in report["errors"])
            )

            review.write_text(
                self._review_text(self.SNAPSHOT, status="❌ S1 blocker(ы)", blockers=((1, "historical-fixed"),)),
                encoding="utf-8",
            )
            report = MODULE.build_semantic_review_observation_report(plan)
            self.assertEqual((report["state"], report["reason_code"]), ("blocked", "live_review_artifact_invalid"))
            self.assertTrue(any(error["code"] == "semantic_live_review_red_without_open_blockers" for error in report["errors"]))

            review.write_text(
                self._review_text(
                    self.SNAPSHOT,
                    status="❌ S1 blocker(ы)",
                    blockers=((1, "open"), (2, "open")),
                ),
                encoding="utf-8",
            )
            plan.write_text(self._plan_text(risk + "\n\n" + self._proposal_fence(self._first_blocker_proposal())), encoding="utf-8")
            report = MODULE.build_semantic_review_observation_report(plan)
            self.assertEqual((report["state"], report["reason_code"]), ("blocked", "live_review_artifact_invalid"))
            self.assertTrue(any(error["code"] == "semantic_live_review_blocker_ref_set_mismatch" for error in report["errors"]))

            full_proposal = {
                "schema_version": "semantic_review_observation_proposal.v1",
                "progress_verdict": "first_observation",
                "progress_evidence_refs": [f"{self.REVIEW_REL}#B1", f"{self.REVIEW_REL}#B2"],
                "blockers": [
                    {
                        "blocker_ref": f"{self.REVIEW_REL}#B1",
                        "lineage_relation": "first_observation",
                        "predecessor_blocker_ref": None,
                    },
                    {
                        "blocker_ref": f"{self.REVIEW_REL}#B2",
                        "lineage_relation": "first_observation",
                        "predecessor_blocker_ref": None,
                    },
                ],
                "resolved_predecessor_blocker_refs": [],
            }
            plan.write_text(self._plan_text(risk + "\n\n" + self._proposal_fence(full_proposal)), encoding="utf-8")
            report = MODULE.build_semantic_review_observation_report(plan)
            self.assertEqual((report["state"], report["reason_code"]), ("ready_to_materialize", "observation_not_materialized"))

    def test_green_historical_closure_requires_empty_current_blockers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = self._write_fixture(root)
            review = root / self.REVIEW_REL
            review.write_text(
                self._review_text(
                    self.SNAPSHOT,
                    status="❌ S1 blocker(ы)",
                    blockers=((1, "open"), (2, "open")),
                ),
                encoding="utf-8",
            )
            first_proposal = {
                "schema_version": "semantic_review_observation_proposal.v1",
                "progress_verdict": "first_observation",
                "progress_evidence_refs": [f"{self.REVIEW_REL}#B1", f"{self.REVIEW_REL}#B2"],
                "blockers": [
                    {
                        "blocker_ref": f"{self.REVIEW_REL}#B1",
                        "lineage_relation": "first_observation",
                        "predecessor_blocker_ref": None,
                    },
                    {
                        "blocker_ref": f"{self.REVIEW_REL}#B2",
                        "lineage_relation": "first_observation",
                        "predecessor_blocker_ref": None,
                    },
                ],
                "resolved_predecessor_blocker_refs": [],
            }
            first_evidence = self._risk_fence() + "\n\n" + self._proposal_fence(first_proposal)
            plan.write_text(self._plan_text(first_evidence), encoding="utf-8")
            first_materialization = MODULE.build_semantic_review_observation_report(plan)["materialization"]
            assert isinstance(first_materialization, dict)
            first_observation = first_materialization["observation"]
            assert isinstance(first_observation, dict)

            review.write_text(
                self._review_text(
                    self.SNAPSHOT,
                    blockers=((1, "historical-fixed"), (2, "historical-fixed")),
                ),
                encoding="utf-8",
            )
            closure_proposal = {
                "schema_version": "semantic_review_observation_proposal.v1",
                "progress_verdict": "same_contract_progress",
                "progress_evidence_refs": [f"{self.REVIEW_REL}#aggregate"],
                "blockers": [],
                "resolved_predecessor_blocker_refs": [f"{self.REVIEW_REL}#B1", f"{self.REVIEW_REL}#B2"],
            }
            evidence = (
                self._risk_fence(current=False)
                + "\n\n"
                + self._proposal_fence(first_proposal)
                + "\n\n"
                + self._final_fence(first_observation)
                + "\n\n"
                + self._risk_fence(run_id="reviewer_code_risk:fixture:20260802T190000Z")
                + "\n\n"
                + self._proposal_fence(closure_proposal)
            )
            plan.write_text(self._plan_text(evidence), encoding="utf-8")
            report = MODULE.build_semantic_review_observation_report(plan)
            self.assertEqual((report["state"], report["reason_code"]), ("ready_to_materialize", "observation_not_materialized"))
            materialization = report["materialization"]
            assert isinstance(materialization, dict)
            observation = materialization["observation"]
            assert isinstance(observation, dict)
            self.assertEqual(observation["blockers"], [])
            self.assertEqual(
                observation["resolved_blocker_family_ids"],
                sorted(item["blocker_family_id"] for item in first_observation["blockers"]),
            )

    def test_coder_stale_current_admission_is_warn_only_for_exact_rerun_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = self._write_fixture(root)
            current_target = build_current_bundle_snapshot(plan, project_root=root)["target"]
            assert isinstance(current_target, str)
            review = root / self.REVIEW_REL
            review.write_text(
                self._review_text(current_target, status="❌ S1 blocker(ы)", blockers=((1, "open"),)),
                encoding="utf-8",
            )
            proposal = self._first_blocker_proposal()
            evidence = self._risk_fence(snapshot=current_target) + "\n\n" + self._proposal_fence(proposal)
            plan.write_text(self._plan_text(evidence, status="In progress"), encoding="utf-8")
            materialization = MODULE.build_semantic_review_observation_report(plan)["materialization"]
            assert isinstance(materialization, dict)
            observation = materialization["observation"]
            assert isinstance(observation, dict)
            evidence += "\n\n" + self._final_fence(observation)
            notes = (
                f"- Stale note (2026-08-02 20:47 MSK): same review file `{self.REVIEW_REL}` remains red until rerun\n"
                f"- Rerun note (2026-08-02 20:47 MSK): same review file `{self.REVIEW_REL}` will be rewritten in place"
            )
            plan.write_text(self._plan_text(evidence, status="In progress", review_notes=notes), encoding="utf-8")
            (root / "scripts/example.py").write_text("# changed fixture\n", encoding="utf-8")

            report = MODULE.build_semantic_review_observation_report(plan)
            self.assertEqual((report["state"], report["reason_code"]), ("blocked", "current_head_mismatch"))
            self.assertEqual([error["code"] for error in report["errors"]], ["semantic_current_target_snapshot_stale"])
            for status in ("In progress", "Ready for Review"):
                with self.subTest(status=status):
                    plan.write_text(self._plan_text(evidence, status=status, review_notes=notes), encoding="utf-8")
                    findings = MODULE.validate_semantic_review_observation_contract(
                        plan,
                        plan.read_text(encoding="utf-8").splitlines(),
                        status_value=status,
                    )
                    self.assertEqual([finding.severity for finding in findings], ["WARN"])

            for status in ("In progress", "Ready for Review"):
                with self.subTest(status=status, contract_fingerprint_drift=True):
                    plan.write_text(
                        self._plan_text(evidence, status=status, review_notes=notes).replace(
                            "- Stable contract decision.",
                            "- Stable contract decision clarified during same-contract reroute.",
                        ),
                        encoding="utf-8",
                    )
                    report = MODULE.build_semantic_review_observation_report(plan)
                    self.assertEqual((report["state"], report["reason_code"]), ("blocked", "current_head_mismatch"))
                    self.assertEqual(
                        [error["code"] for error in report["errors"]],
                        [
                            "semantic_current_target_snapshot_stale",
                            "semantic_observation_machine_fields_mismatch",
                        ],
                    )
                    findings = MODULE.validate_semantic_review_observation_contract(
                        plan,
                        plan.read_text(encoding="utf-8").splitlines(),
                        status_value=status,
                    )
                    self.assertEqual([finding.severity for finding in findings], ["WARN"])

            for status, review_notes in (("Ready for Arch review", notes), ("In progress", "")):
                with self.subTest(status=status, review_notes=review_notes):
                    plan.write_text(self._plan_text(evidence, status=status, review_notes=review_notes), encoding="utf-8")
                    findings = MODULE.validate_semantic_review_observation_contract(
                        plan,
                        plan.read_text(encoding="utf-8").splitlines(),
                        status_value=status,
                    )
                    self.assertEqual([finding.severity for finding in findings], ["ERROR"])

    def test_progress_summary_precedence_requires_scope_churn_for_target_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan, first_proposal, first_observation, _accepted_evidence = self._accepted_first_blocker(root)
            next_snapshot = "semantic-fixture-target-drift"
            (root / self.REVIEW_REL).write_text(
                self._review_text(next_snapshot, status="❌ S1 blocker(ы)", blockers=((1, "open"),)),
                encoding="utf-8",
            )
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
            historical = self._risk_fence(current=False) + "\n\n" + self._proposal_fence(first_proposal) + "\n\n" + self._final_fence(first_observation)
            evidence = historical + "\n\n" + self._risk_fence(
                run_id="reviewer_code_risk:fixture:20260802T190000Z", snapshot=next_snapshot
            ) + "\n\n" + self._proposal_fence(second_proposal)
            plan.write_text(self._plan_text(evidence), encoding="utf-8")
            report = MODULE.build_semantic_review_observation_report(plan)
            self.assertEqual((report["state"], report["reason_code"]), ("blocked", "role_field_invalid"))
            self.assertTrue(any(error["code"] == "semantic_progress_precedence_invalid" for error in report["errors"]))

            second_proposal["progress_verdict"] = "scope_churn"
            evidence = historical + "\n\n" + self._risk_fence(
                run_id="reviewer_code_risk:fixture:20260802T190000Z", snapshot=next_snapshot
            ) + "\n\n" + self._proposal_fence(second_proposal)
            plan.write_text(self._plan_text(evidence), encoding="utf-8")
            report = MODULE.build_semantic_review_observation_report(plan)
            self.assertEqual((report["state"], report["reason_code"]), ("ready_to_materialize", "observation_not_materialized"))

    def test_accepted_history_rejects_duplicate_proposal_and_reuses_same_generation_readback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan, proposal, observation, accepted_evidence = self._accepted_first_blocker(root)
            historical = accepted_evidence.replace('"current": true', '"current": false', 1)
            retry = self._risk_fence()

            plan.write_text(self._plan_text(historical + "\n\n" + retry), encoding="utf-8")
            report = MODULE.build_semantic_review_observation_report(plan)
            self.assertEqual((report["state"], report["reason_code"]), ("valid", "current_observation_valid"))
            self.assertEqual(report["validated_chain"], [observation["observation_id"]])

            (root / self.REVIEW_REL).write_text(
                self._review_text(self.SNAPSHOT).replace("- Blocker ID: B1\n", ""),
                encoding="utf-8",
            )
            report = MODULE.build_semantic_review_observation_report(plan)
            self.assertEqual((report["state"], report["reason_code"]), ("blocked", "live_review_artifact_invalid"))
            self.assertTrue(any(error["code"] == "semantic_live_review_blocker_ref_missing" for error in report["errors"]))

            (root / self.REVIEW_REL).write_text(
                self._review_text(self.SNAPSHOT, status="❌ S1 blocker(ы)", blockers=((1, "open"),)),
                encoding="utf-8",
            )
            duplicate_proposal = self._proposal_fence(proposal)
            plan.write_text(
                self._plan_text(historical + "\n\n" + duplicate_proposal + "\n\n" + retry),
                encoding="utf-8",
            )
            report = MODULE.build_semantic_review_observation_report(plan)
            self.assertEqual((report["state"], report["reason_code"]), ("blocked", "role_proposal_invalid"))
            self.assertTrue(any(error["code"] == "semantic_accepted_generation_duplicate_proposal" for error in report["errors"]))

    def test_current_bundle_snapshot_and_non_task_checkbox_text_are_not_hash_stale_blind_spots(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = self._write_fixture(root)
            baseline = MODULE.build_semantic_review_contract_fingerprint(plan)
            self.assertIsInstance(baseline, dict)
            original = plan.read_text(encoding="utf-8")
            plan.write_text(original.replace("- Stable contract decision.", "- Stable contract decision [x]."), encoding="utf-8")
            self.assertNotEqual(baseline, MODULE.build_semantic_review_contract_fingerprint(plan))
            plan.write_text(original, encoding="utf-8")

            fenced_literal = original.replace(
                "## Scope\n",
                "## Scope\n\n```text\n- [x] literal contract example\n```\n",
            )
            plan.write_text(fenced_literal, encoding="utf-8")
            fenced_fingerprint = MODULE.build_semantic_review_contract_fingerprint(plan)
            self.assertIsInstance(fenced_fingerprint, dict)
            plan.write_text(
                fenced_literal.replace("- [x] literal contract example", "- [ ] literal contract example"),
                encoding="utf-8",
            )
            self.assertNotEqual(fenced_fingerprint, MODULE.build_semantic_review_contract_fingerprint(plan))
            plan.write_text(original, encoding="utf-8")

            current_target = build_current_bundle_snapshot(plan, project_root=root)["target"]
            (root / self.REVIEW_REL).write_text(self._review_text(str(current_target)), encoding="utf-8")
            evidence = self._risk_fence(snapshot=str(current_target)) + "\n\n" + self._proposal_fence()
            plan.write_text(self._plan_text(evidence), encoding="utf-8")
            materialization = MODULE.build_semantic_review_observation_report(plan)["materialization"]
            assert isinstance(materialization, dict)
            observation = materialization["observation"]
            assert isinstance(observation, dict)
            plan.write_text(self._plan_text(evidence + "\n\n" + self._final_fence(observation)), encoding="utf-8")
            self.assertEqual(MODULE.build_semantic_review_observation_report(plan)["state"], "valid")

            (root / "scripts/example.py").write_text("# changed fixture\n", encoding="utf-8")
            report = MODULE.build_semantic_review_observation_report(plan)
            self.assertEqual((report["state"], report["reason_code"]), ("blocked", "current_head_mismatch"))
            self.assertTrue(any(error["code"] == "semantic_current_target_snapshot_stale" for error in report["errors"]))

    def test_marker_absence_is_legacy_and_checkbox_completion_does_not_change_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = self._write_fixture(root)
            fingerprint = MODULE.build_semantic_review_contract_fingerprint(plan)
            self.assertIsInstance(fingerprint, dict)
            original = plan.read_text(encoding="utf-8")
            plan.write_text(original.replace("- [ ] semantic fixture scope.", "- [x] semantic fixture scope."), encoding="utf-8")
            self.assertEqual(fingerprint, MODULE.build_semantic_review_contract_fingerprint(plan))
            plan.write_text(original.replace("### Semantic review observation\n", ""), encoding="utf-8")
            report = MODULE.build_semantic_review_observation_report(plan)
            self.assertEqual((report["state"], report["reason_code"]), ("not_available", "feature_not_activated"))


class SemanticCycleCheckpointContractTests(unittest.TestCase):
    """Consumer-only fixtures built from the producer's accepted V1 history."""

    def _producer_marker(self) -> str:
        return (
            "### Semantic review observation\n"
            "- `schema=semantic_review_observation.v1`\n"
            "- `mode=required`\n"
            "- `writer=reviewer_code_contracts`"
        )

    def _checkpoint_marker(self) -> str:
        return (
            "### Semantic cycle checkpoint\n"
            "- `schema=semantic_cycle_checkpoint.v1`\n"
            "- `mode=required`\n"
            "- `writer=architect`"
        )

    def _activate_checkpoint(self, text: str) -> str:
        return text.replace(self._producer_marker(), self._producer_marker() + "\n\n" + self._checkpoint_marker())

    def _helper(self) -> SemanticReviewObservationContractTests:
        return SemanticReviewObservationContractTests(methodName="runTest")

    def _survival_fixture(
        self,
        root: Path,
        *,
        same_snapshot: bool = False,
        status: str = "Ready for Coder",
        helper: SemanticReviewObservationContractTests | None = None,
    ) -> tuple[SemanticReviewObservationContractTests, Path, str]:
        helper = helper or self._helper()
        plan, first_proposal, first_observation, _accepted_evidence = helper._accepted_first_blocker(root)
        next_snapshot = helper.SNAPSHOT if same_snapshot else helper.SNAPSHOT + "-corrected"
        (root / helper.REVIEW_REL).write_text(
            helper._review_text(next_snapshot, status="❌ S1 blocker(ы)", blockers=((1, "open"),)),
            encoding="utf-8",
        )
        second_proposal = {
            "schema_version": "semantic_review_observation_proposal.v1",
            "progress_verdict": "same_contract_stalled" if same_snapshot else "scope_churn",
            "progress_evidence_refs": [f"{helper.REVIEW_REL}#B1"],
            "blockers": [
                {
                    "blocker_ref": f"{helper.REVIEW_REL}#B1",
                    "lineage_relation": "same_family",
                    "predecessor_blocker_ref": f"{helper.REVIEW_REL}#B1",
                }
            ],
            "resolved_predecessor_blocker_refs": [],
        }
        evidence = (
            helper._risk_fence(current=False)
            + "\n\n"
            + helper._proposal_fence(first_proposal)
            + "\n\n"
            + helper._final_fence(first_observation)
            + "\n\n"
            + helper._risk_fence(
                run_id="reviewer_code_risk:checkpoint:20260802T234100Z",
                snapshot=next_snapshot,
            )
            + "\n\n"
            + helper._proposal_fence(second_proposal)
        )
        plan.write_text(self._activate_checkpoint(helper._plan_text(evidence, status=status)), encoding="utf-8")
        producer_materialization_report = MODULE.build_semantic_review_observation_report(plan)
        materialization = producer_materialization_report["materialization"]
        self.assertIsInstance(materialization, dict, producer_materialization_report)
        assert isinstance(materialization, dict)
        second_observation = materialization["observation"]
        self.assertIsInstance(second_observation, dict)
        assert isinstance(second_observation, dict)
        evidence += "\n\n" + helper._final_fence(second_observation)
        plan.write_text(self._activate_checkpoint(helper._plan_text(evidence, status=status)), encoding="utf-8")
        producer_report = MODULE.build_semantic_review_observation_report(plan)
        self.assertEqual((producer_report["state"], producer_report["reason_code"]), ("valid", "current_observation_valid"))
        return helper, plan, evidence

    def _independent_boundary_fixture(
        self,
        root: Path,
        *,
        status: str = "Ready for Coder",
        helper: SemanticReviewObservationContractTests | None = None,
    ) -> tuple[SemanticReviewObservationContractTests, Path, str]:
        """Materialize a permit-eligible V2 boundary without scope churn."""

        helper = helper or self._helper()
        plan, _first_proposal, _first_observation, evidence = helper._accepted_first_blocker(root)
        evidence = evidence.replace('"current": true', '"current": false', 1)
        (root / helper.REVIEW_REL).write_text(
            helper._review_text(
                helper.SNAPSHOT,
                status="❌ S1 blocker(ы)",
                blockers=((1, "historical-fixed"), (2, "open")),
            ),
            encoding="utf-8",
        )
        proposal = {
            "schema_version": "semantic_review_observation_proposal.v1",
            "progress_verdict": "independent_boundary",
            "progress_evidence_refs": [f"{helper.REVIEW_REL}#B2"],
            "blockers": [
                {
                    "blocker_ref": f"{helper.REVIEW_REL}#B2",
                    "lineage_relation": "independent_boundary",
                    "predecessor_blocker_ref": None,
                }
            ],
            "resolved_predecessor_blocker_refs": [f"{helper.REVIEW_REL}#B1"],
        }
        evidence += (
            "\n\n"
            + helper._risk_fence(
                run_id="reviewer_code_risk:checkpoint:20260815T233300Z",
                snapshot=helper.SNAPSHOT,
            )
            + "\n\n"
            + helper._proposal_fence(proposal)
        )
        plan.write_text(self._activate_checkpoint(helper._plan_text(evidence, status=status)), encoding="utf-8")
        materialization = MODULE.build_semantic_review_observation_report(plan)["materialization"]
        self.assertIsInstance(materialization, dict)
        assert isinstance(materialization, dict)
        observation = materialization["observation"]
        self.assertIsInstance(observation, dict)
        assert isinstance(observation, dict)
        evidence += "\n\n" + helper._final_fence(observation)
        plan.write_text(self._activate_checkpoint(helper._plan_text(evidence, status=status)), encoding="utf-8")
        producer_report = MODULE.build_semantic_review_observation_report(plan)
        self.assertEqual((producer_report["state"], producer_report["reason_code"]), ("valid", "current_observation_valid"))
        return helper, plan, evidence

    def _same_contract_resolution(self, report: dict[str, object]) -> dict[str, object]:
        trigger = report["trigger"]
        self.assertIsInstance(trigger, dict)
        assert isinstance(trigger, dict)
        families = trigger["required_blocker_family_ids"]
        self.assertIsInstance(families, list)
        return {
            "schema_version": "semantic_cycle_checkpoint_resolution.v1",
            "trigger_observation_id": trigger["observation_id"],
            "trigger_kind": trigger["trigger_kind"],
            "contract_fingerprint": trigger["contract_fingerprint"],
            "required_family_resolutions": [
                {"blocker_family_id": family, "decision": "same_contract_once"} for family in families
            ],
            "decision_evidence_refs": ["docs/code_reviews/checkpoint.md#B1"],
            "allowed_next_status": "Coder intake",
        }

    def _v2_subject_admission(
        self,
        root: Path,
        helper: SemanticReviewObservationContractTests,
        plan: Path,
        *,
        route_kind: str = "bounded_grammar",
    ) -> tuple[dict[str, object], list[str]]:
        """Install a self-bound bounded-grammar or structured admission fixture."""

        subject_rel = helper.PLAN_REL
        subject_id = "mad-260815-0100"
        decision = _fixture_required_machine_authority_decision(
            plan_rel=subject_rel,
            decision_id=subject_id,
            route_id=f"{route_kind}_fixture",
        )
        route = decision["recommended_route"]
        assert isinstance(route, dict)
        self.assertIn(route_kind, {"bounded_grammar", "structured_carrier"})
        route["id"] = f"{route_kind}_fixture"
        route["kind"] = route_kind
        authority_host = route["authority_host"]
        assert isinstance(authority_host, dict)
        authority_host["path"] = subject_rel
        axes = [
            {"axis_id": "fixture_axis_a", "description": "fixture grammar axis A"},
            {"axis_id": "fixture_axis_b", "description": "fixture grammar axis B"},
        ]
        if route_kind == "bounded_grammar":
            contour = {
                "contour_origin_plan": subject_rel,
                "contour_origin_decision_id": subject_id,
                "grammar_contour_id": "",
                "parser_owner": "Architect",
                "parser_or_library": "fixture_parser",
                "axes": axes,
                "proof_matrix_ref": f"{subject_rel}#Acceptance criteria / DoD",
                "budget_policy": "same_contract_once_total",
                "exit_rule": "structured_successor_or_literal_de_scope",
            }
            identity = {
                "schema_version": "grammar_contour_identity.v1",
                "contour_origin_plan": contour["contour_origin_plan"],
                "contour_origin_decision_id": contour["contour_origin_decision_id"],
                "authority_host": authority_host,
                "parser_owner": contour["parser_owner"],
                "parser_or_library": contour["parser_or_library"],
                "axes": contour["axes"],
                "proof_matrix_ref": contour["proof_matrix_ref"],
                "budget_policy": contour["budget_policy"],
                "exit_rule": contour["exit_rule"],
            }
            contour["grammar_contour_id"] = "gc_" + hashlib.sha256(
                json.dumps(
                    MODULE.plan_status_oracle._machine_authority_normalize_json(identity),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8")
            ).hexdigest()
            route["grammar_contour"] = contour
        else:
            route.pop("grammar_contour", None)
        decision["decision_id"] = subject_id
        confirmation = decision["owner_confirmation"]
        assert isinstance(confirmation, dict)
        confirmation.update({"state": "confirmed", "question_ref": "Q1", "decision_id": subject_id, "route_id": route["id"]})
        confirmation["carrier_sha256"] = MODULE.plan_status_oracle.machine_authority_decision_sha256(decision)
        meta = {"cluster": "process", "machine_authority_decision": decision}

        draft = root / f"docs/code_drafts/{plan.stem}__code_draft.md"
        draft.parent.mkdir(parents=True, exist_ok=True)
        draft_text = draft.read_text(encoding="utf-8")
        draft_start = draft_text.index("```json\n") + len("```json\n")
        draft_end = draft_text.index("\n```", draft_start)
        draft_payload = json.loads(draft_text[draft_start:draft_end])
        draft_meta = draft_payload["code_draft_meta"]
        assert isinstance(draft_meta, dict)
        draft_meta["plan"] = subject_rel
        draft_meta["machine_authority_decision_ref"] = {
            "applicability": "required",
            "decision_id": subject_id,
            "carrier_sha256": confirmation["carrier_sha256"],
        }
        draft.write_text(
            draft_text[:draft_start] + json.dumps(draft_payload, indent=2) + draft_text[draft_end:],
            encoding="utf-8",
        )
        return meta, [axis["axis_id"] for axis in axes]

    def _render_v2_subject(
        self,
        helper: SemanticReviewObservationContractTests,
        meta: dict[str, object],
        evidence: str,
        *,
        status: str,
    ) -> str:
        text = self._activate_checkpoint(helper._plan_text(evidence, status=status))
        meta_start = text.index("```json\n", text.index("## Meta")) + len("```json\n")
        meta_end = text.index("\n```", meta_start)
        text = text[:meta_start] + json.dumps({"plan_meta": meta}, indent=2) + text[meta_end:]
        qna = (
            "## Q&A log (chronological, append-only)\n\n"
            "### Architect Q&A\n\n"
            "- [2026-08-15 00:00 MSK] (Architect -> Owner, id=Q1, blocker=yes, needs_owner=yes, status=open) Q: Confirm fixture bounded grammar admission?\n"
            "- [2026-08-15 00:01 MSK] (Owner -> Architect, id=Q1, blocker=no, needs_owner=no, status=closed) A: Confirmed.\n\n"
        )
        return text.replace("## Evidence\n", qna + "## Evidence\n", 1)

    def _v2_resolution(self, report: dict[str, object], axes: list[str]) -> dict[str, object]:
        trigger = report["trigger"]
        self.assertIsInstance(trigger, dict)
        assert isinstance(trigger, dict)
        return {
            "schema_version": "semantic_cycle_checkpoint_resolution.v2",
            "resolution_state": "accepted",
            "authority_decision_id": report["authority_decision_id"],
            "authority_carrier_sha256": report["authority_carrier_sha256"],
            "grammar_contour_id": report["grammar_contour_id"],
            "trigger_observation_id": trigger["observation_id"],
            "trigger_kind": trigger["trigger_kind"],
            "contract_fingerprint": trigger["contract_fingerprint"],
            "required_family_resolutions": [
                {
                    "blocker_family_id": item["blocker_family_id"],
                    "blocker_ref": item["blocker_ref"],
                    "grammar_axis_ids": axes,
                    "decision": "same_contract_once",
                }
                for item in trigger["required_family_rows"]
            ],
            "decision_evidence_refs": ["docs/code_reviews/checkpoint.md#B1"],
            "allowed_next_status": "Coder intake",
        }

    def _write_v2_successor_fixture(
        self,
        root: Path,
        *,
        source_helper: SemanticReviewObservationContractTests,
        source_plan: Path,
        trigger: dict[str, object],
        rows: list[dict[str, object]],
        context: dict[str, object],
        structured: bool = False,
    ) -> str:
        """Materialize a bounded negative or structured positive successor fixture."""

        successor_helper = self._helper()
        successor_kind = "structured" if structured else "bounded_grammar"
        successor_helper.PLAN_REL = f"docs/plans/260815_0199_{successor_kind}_successor.md"
        successor_helper.DRAFT_REL = f"docs/code_drafts/260815_0199_{successor_kind}_successor__code_draft.md"
        successor_helper.REVIEW_REL = f"docs/code_reviews/260815_0199_{successor_kind}_successor.md"
        successor = root / successor_helper.PLAN_REL
        successor.parent.mkdir(parents=True, exist_ok=True)
        draft = root / successor_helper.DRAFT_REL
        draft.parent.mkdir(parents=True, exist_ok=True)
        draft.write_text(
            "# Code draft: successor fixture\n\n"
            "```json\n"
            + json.dumps({"code_draft_meta": {"plan": successor_helper.PLAN_REL, "targets": []}}, indent=2)
            + "\n```\n",
            encoding="utf-8",
        )
        successor_meta, _axes = self._v2_subject_admission(
            root,
            successor_helper,
            successor,
            route_kind="structured_carrier" if structured else "bounded_grammar",
        )
        successor_plan_rel = successor_helper.PLAN_REL
        successor_meta["depends_on"] = [source_helper.PLAN_REL]
        successor_meta["semantic_cycle_successor_intake"] = {
            "schema_version": "semantic_cycle_successor_intake.v1",
            "source_plan": source_helper.PLAN_REL,
            "source_trigger_observation_id": trigger["observation_id"],
            "source_grammar_contour_id": context["grammar_contour_id"],
            "inherited_family_refs": [
                {
                    "blocker_family_id": row["blocker_family_id"],
                    "blocker_ref": row["blocker_ref"],
                    "grammar_axis_ids": row["grammar_axis_ids"],
                }
                for row in rows
            ],
        }
        successor.write_text(
            f"# Plan: {successor_kind} successor fixture\n\n"
            "**Plan type:** dev\n"
            "**Status:** Architect initial draft\n\n"
            "## Meta\n```json\n"
            + json.dumps({"plan_meta": successor_meta}, indent=2)
            + "\n```\n\n"
            "## Acceptance criteria / DoD\n\n"
            "- [ ] Fixture only.\n\n"
            "## Q&A log\n\n"
            "### Architect Q&A\n\n"
            "- [2026-08-15 00:00 MSK] (Architect -> Owner, id=Q1, blocker=yes, needs_owner=yes, status=open) Q: Confirm fixture bounded grammar admission?\n"
            "- [2026-08-15 00:01 MSK] (Owner -> Architect, id=Q1, blocker=no, needs_owner=no, status=closed) A: Confirmed.\n",
            encoding="utf-8",
        )
        self.assertEqual(
            MODULE.plan_status_oracle.machine_authority_decision_readback(successor).state,
            "frozen_confirmed",
        )
        return successor_plan_rel

    def test_dual_marker_activation_waiting_and_missing_producer_are_distinct(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            helper = self._helper()
            plan = helper._write_fixture(root)
            plan.write_text(self._activate_checkpoint(helper._plan_text("", status="In progress")), encoding="utf-8")
            report = MODULE.build_semantic_cycle_checkpoint_report(plan)
            self.assertEqual((report["state"], report["reason_code"]), ("waiting", "risk_generation_not_available"))

            plan.write_text(
                self._activate_checkpoint(helper._plan_text("", status="In progress")).replace(self._producer_marker() + "\n\n", ""),
                encoding="utf-8",
            )
            report = MODULE.build_semantic_cycle_checkpoint_report(plan)
            self.assertEqual((report["state"], report["reason_code"]), ("blocked", "activation_invalid"))
            self.assertTrue(any(error["code"] == "checkpoint_dual_marker_missing_producer" for error in report["errors"]))

    def test_family_survival_requires_changed_snapshot_and_stops_q2_style_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _helper, plan, _evidence = self._survival_fixture(root)
            report = MODULE.build_semantic_cycle_checkpoint_report(plan)
            self.assertEqual(
                (report["state"], report["reason_code"]),
                ("required", "resolution_required"),
                report,
            )
            self.assertEqual(report["trigger"]["trigger_kind"], "family_survival")
            self.assertEqual(len(report["trigger"]["required_blocker_family_ids"]), 1)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _helper, plan, _evidence = self._survival_fixture(root, same_snapshot=True)
            report = MODULE.build_semantic_cycle_checkpoint_report(plan)
            self.assertEqual((report["state"], report["reason_code"]), ("not_required", "current_observation_no_checkpoint_trigger"))

    def test_resolution_exact_cover_release_and_duplicate_permit_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            helper, plan, evidence = self._survival_fixture(root, status="Coder intake")
            required = MODULE.build_semantic_cycle_checkpoint_report(plan)
            resolution = self._same_contract_resolution(required)
            resolution_fence = "```json\n" + json.dumps(resolution, ensure_ascii=False, indent=2) + "\n```"
            plan.write_text(
                self._activate_checkpoint(helper._plan_text(evidence + "\n\n" + resolution_fence, status="Coder intake")),
                encoding="utf-8",
            )
            report = MODULE.build_semantic_cycle_checkpoint_report(plan)
            self.assertEqual((report["state"], report["reason_code"]), ("permitted", "resolution_release_valid"))

            plan.write_text(
                self._activate_checkpoint(
                    helper._plan_text(evidence + "\n\n" + resolution_fence + "\n\n" + resolution_fence, status="Coder intake")
                ),
                encoding="utf-8",
            )
            report = MODULE.build_semantic_cycle_checkpoint_report(plan)
            self.assertEqual(report["state"], "blocked")
            self.assertTrue(any(error["code"] == "checkpoint_resolution_duplicate_for_trigger" for error in report["errors"]))

    def test_historical_resolution_keeps_fresh_reviewer_waiting_without_architect_guard(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            helper, plan, evidence = self._survival_fixture(root, status="Coder intake")
            historical_required = MODULE.build_semantic_cycle_checkpoint_report(plan)
            historical_resolution = self._same_contract_resolution(historical_required)
            historical_resolution_fence = "```json\n" + json.dumps(historical_resolution, ensure_ascii=False, indent=2) + "\n```"
            historical_evidence = evidence + "\n\n" + historical_resolution_fence
            plan.write_text(
                self._activate_checkpoint(helper._plan_text(historical_evidence, status="Coder intake")),
                encoding="utf-8",
            )
            self.assertEqual(
                (
                    MODULE.build_semantic_cycle_checkpoint_report(plan)["state"],
                    MODULE.build_semantic_cycle_checkpoint_report(plan)["reason_code"],
                ),
                ("permitted", "resolution_release_valid"),
            )
            historical_evidence = historical_evidence.replace('"current": true', '"current": false', 1)

            fresh_snapshot = helper.SNAPSHOT + "-corrected"
            (root / helper.REVIEW_REL).write_text(
                helper._review_text(
                    fresh_snapshot,
                    status="❌ S1 blocker(ы)",
                    blockers=((1, "historical-fixed"), (2, "open")),
                ),
                encoding="utf-8",
            )
            waiting_evidence = historical_evidence + "\n\n" + helper._risk_fence(
                run_id="reviewer_code_risk:checkpoint:20260803T014600Z",
                snapshot=fresh_snapshot,
            )
            plan.write_text(
                self._activate_checkpoint(helper._plan_text(waiting_evidence, status="Ready for Review")),
                encoding="utf-8",
            )
            producer_report = MODULE.build_semantic_review_observation_report(plan)
            self.assertEqual(
                (producer_report["state"], producer_report["reason_code"]),
                ("ready_to_materialize", "role_proposal_required"),
            )
            waiting_report = MODULE.build_semantic_cycle_checkpoint_report(plan)
            self.assertEqual(
                (waiting_report["state"], waiting_report["reason_code"]),
                ("waiting", "role_proposal_required"),
                waiting_report,
            )
            self.assertEqual(waiting_report["errors"], [])
            oracle = MODULE.plan_status_oracle.oracle_result(plan)
            self.assertFalse(oracle.route_guard_triggered)
            self.assertEqual(oracle.route_guard_kind, "none")

            unknown_resolution = {**historical_resolution, "trigger_observation_id": "sro_not_accepted"}
            unknown_resolution_fence = "```json\n" + json.dumps(unknown_resolution, ensure_ascii=False, indent=2) + "\n```"
            plan.write_text(
                self._activate_checkpoint(
                    helper._plan_text(waiting_evidence + "\n\n" + unknown_resolution_fence, status="Ready for Review")
                ),
                encoding="utf-8",
            )
            blocked_report = MODULE.build_semantic_cycle_checkpoint_report(plan)
            self.assertEqual((blocked_report["state"], blocked_report["reason_code"]), ("blocked", "resolution_invalid"))
            self.assertTrue(
                any(error["code"] == "checkpoint_resolution_trigger_unknown" for error in blocked_report["errors"]),
                blocked_report,
            )
            oracle = MODULE.plan_status_oracle.oracle_result(plan)
            self.assertTrue(oracle.route_guard_triggered)
            self.assertEqual(oracle.route_guard_kind, "semantic_cycle_checkpoint_invalid")

            fresh_proposal = {
                "schema_version": "semantic_review_observation_proposal.v1",
                "progress_verdict": "independent_boundary",
                "progress_evidence_refs": [f"{helper.REVIEW_REL}#B2"],
                "blockers": [
                    {
                        "blocker_ref": f"{helper.REVIEW_REL}#B2",
                        "lineage_relation": "independent_boundary",
                        "predecessor_blocker_ref": None,
                    }
                ],
                "resolved_predecessor_blocker_refs": [f"{helper.REVIEW_REL}#B1"],
            }
            fresh_evidence = waiting_evidence + "\n\n" + helper._proposal_fence(fresh_proposal)
            plan.write_text(
                self._activate_checkpoint(helper._plan_text(fresh_evidence, status="Ready for Review")),
                encoding="utf-8",
            )
            producer_report = MODULE.build_semantic_review_observation_report(plan)
            self.assertEqual(
                (producer_report["state"], producer_report["reason_code"]),
                ("ready_to_materialize", "observation_not_materialized"),
                producer_report,
            )
            materialization = producer_report["materialization"]
            self.assertIsInstance(materialization, dict, producer_report)
            assert isinstance(materialization, dict)
            fresh_observation = materialization["observation"]
            self.assertIsInstance(fresh_observation, dict, producer_report)
            assert isinstance(fresh_observation, dict)
            fresh_evidence += "\n\n" + helper._final_fence(fresh_observation)
            plan.write_text(
                self._activate_checkpoint(helper._plan_text(fresh_evidence, status="Ready for Review")),
                encoding="utf-8",
            )
            current_required = MODULE.build_semantic_cycle_checkpoint_report(plan)
            self.assertEqual(
                (current_required["state"], current_required["reason_code"]),
                ("required", "resolution_required"),
                current_required,
            )
            self.assertEqual(current_required["trigger"]["trigger_kind"], "independent_boundary")
            oracle = MODULE.plan_status_oracle.oracle_result(plan)
            self.assertTrue(oracle.route_guard_triggered)
            self.assertEqual(oracle.route_guard_kind, "semantic_cycle_checkpoint_required")

    def test_same_family_permit_is_consumed_across_fingerprint_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            helper, plan, evidence = self._survival_fixture(root, status="Coder intake")
            first_required = MODULE.build_semantic_cycle_checkpoint_report(plan)
            first_resolution = self._same_contract_resolution(first_required)
            first_resolution_fence = "```json\n" + json.dumps(first_resolution, ensure_ascii=False, indent=2) + "\n```"
            first_evidence = evidence + "\n\n" + first_resolution_fence
            plan.write_text(
                self._activate_checkpoint(helper._plan_text(first_evidence, status="Coder intake")),
                encoding="utf-8",
            )
            first_report = MODULE.build_semantic_cycle_checkpoint_report(plan)
            self.assertEqual((first_report["state"], first_report["reason_code"]), ("permitted", "resolution_release_valid"))
            historical_first_evidence = first_evidence.replace('"current": true', '"current": false', 1)

            third_snapshot = helper.SNAPSHOT + "-second-corrected"
            (root / helper.REVIEW_REL).write_text(
                helper._review_text(third_snapshot, status="❌ S1 blocker(ы)", blockers=((1, "open"),)),
                encoding="utf-8",
            )
            third_proposal = {
                "schema_version": "semantic_review_observation_proposal.v1",
                "progress_verdict": "scope_churn",
                "progress_evidence_refs": [f"{helper.REVIEW_REL}#B1"],
                "blockers": [
                    {
                        "blocker_ref": f"{helper.REVIEW_REL}#B1",
                        "lineage_relation": "same_family",
                        "predecessor_blocker_ref": f"{helper.REVIEW_REL}#B1",
                    }
                ],
                "resolved_predecessor_blocker_refs": [],
            }
            third_evidence = (
                historical_first_evidence
                + "\n\n"
                + helper._risk_fence(
                    run_id="reviewer_code_risk:checkpoint:20260803T003100Z",
                    snapshot=third_snapshot,
                )
                + "\n\n"
                + helper._proposal_fence(third_proposal)
            )
            fingerprint_drift_text = helper._plan_text(third_evidence, status="Coder intake").replace(
                "- Stable contract decision.",
                "- Stable contract decision changed after the first permitted correction.",
            )
            plan.write_text(self._activate_checkpoint(fingerprint_drift_text), encoding="utf-8")
            producer_report = MODULE.build_semantic_review_observation_report(plan)
            self.assertEqual((producer_report["state"], producer_report["reason_code"]), ("ready_to_materialize", "observation_not_materialized"))
            materialization = producer_report["materialization"]
            self.assertIsInstance(materialization, dict, producer_report)
            assert isinstance(materialization, dict)
            third_observation = materialization["observation"]
            self.assertIsInstance(third_observation, dict, producer_report)
            assert isinstance(third_observation, dict)
            third_evidence += "\n\n" + helper._final_fence(third_observation)
            fingerprint_drift_text = helper._plan_text(third_evidence, status="Coder intake").replace(
                "- Stable contract decision.",
                "- Stable contract decision changed after the first permitted correction.",
            )
            plan.write_text(self._activate_checkpoint(fingerprint_drift_text), encoding="utf-8")

            second_required = MODULE.build_semantic_cycle_checkpoint_report(plan)
            self.assertEqual((second_required["state"], second_required["reason_code"]), ("required", "resolution_required"))
            second_resolution = self._same_contract_resolution(second_required)
            self.assertNotEqual(first_resolution["contract_fingerprint"], second_resolution["contract_fingerprint"])
            second_resolution_fence = "```json\n" + json.dumps(second_resolution, ensure_ascii=False, indent=2) + "\n```"
            third_evidence += "\n\n" + second_resolution_fence
            fingerprint_drift_text = helper._plan_text(third_evidence, status="Coder intake").replace(
                "- Stable contract decision.",
                "- Stable contract decision changed after the first permitted correction.",
            )
            plan.write_text(self._activate_checkpoint(fingerprint_drift_text), encoding="utf-8")

            report = MODULE.build_semantic_cycle_checkpoint_report(plan)
            self.assertEqual((report["state"], report["reason_code"]), ("blocked", "resolution_invalid"))
            self.assertTrue(any(error["code"] == "checkpoint_same_contract_permit_reused" for error in report["errors"]))
            oracle = MODULE.plan_status_oracle.oracle_result(plan)
            self.assertTrue(oracle.route_guard_triggered)
            self.assertEqual(oracle.route_guard_kind, "semantic_cycle_checkpoint_invalid")
            self.assertEqual(oracle.route_guard_next_owner, "Architect")

    def test_v2_bounded_grammar_subject_spends_one_contour_permit_and_rejects_v1_mix(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            helper = self._helper()
            helper.PLAN_REL = "docs/plans/260815_0100_bounded_grammar_fixture.md"
            helper.DRAFT_REL = "docs/code_drafts/260815_0100_bounded_grammar_fixture__code_draft.md"
            helper.REVIEW_REL = "docs/code_reviews/260815_0100_bounded_grammar_fixture.md"
            _helper, plan, evidence = self._independent_boundary_fixture(root, status="Coder intake", helper=helper)
            meta, axes = self._v2_subject_admission(root, helper, plan)
            plan.write_text(self._render_v2_subject(helper, meta, evidence, status="Coder intake"), encoding="utf-8")

            required = MODULE.build_semantic_cycle_checkpoint_report(plan)
            self.assertEqual((required["state"], required["reason_code"]), ("required", "resolution_required"), required)
            self.assertEqual(required["authority_decision_id"], "mad-260815-0100")
            self.assertTrue(str(required["grammar_contour_id"]).startswith("gc_"))

            resolution = self._v2_resolution(required, axes)
            fence = "```json\n" + json.dumps(resolution, ensure_ascii=False, indent=2) + "\n```"
            plan.write_text(
                self._render_v2_subject(helper, meta, evidence + "\n\n" + fence, status="Coder intake"),
                encoding="utf-8",
            )
            permitted = MODULE.build_semantic_cycle_checkpoint_report(plan)
            self.assertEqual((permitted["state"], permitted["reason_code"]), ("permitted", "resolution_release_valid"), permitted)

            v1 = self._same_contract_resolution(required)
            mixed_fence = "```json\n" + json.dumps(v1, ensure_ascii=False, indent=2) + "\n```"
            plan.write_text(
                self._render_v2_subject(
                    helper,
                    meta,
                    evidence + "\n\n" + fence + "\n\n" + mixed_fence,
                    status="Coder intake",
                ),
                encoding="utf-8",
            )
            blocked = MODULE.build_semantic_cycle_checkpoint_report(plan)
            self.assertEqual((blocked["state"], blocked["reason_code"]), ("blocked", "resolution_invalid"), blocked)
            self.assertTrue(any(error["code"] == "checkpoint_v2_resolution_version_mixed" for error in blocked["errors"]))

    def test_v2_scope_churn_with_same_family_requires_a_structured_successor(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            helper = self._helper()
            helper.PLAN_REL = "docs/plans/260815_0105_bounded_grammar_scope_churn_fixture.md"
            helper.DRAFT_REL = "docs/code_drafts/260815_0105_bounded_grammar_scope_churn_fixture__code_draft.md"
            helper.REVIEW_REL = "docs/code_reviews/260815_0105_bounded_grammar_scope_churn_fixture.md"
            _helper, plan, evidence = self._survival_fixture(root, status="Architect response", helper=helper)
            meta, axes = self._v2_subject_admission(root, helper, plan)
            plan.write_text(self._render_v2_subject(helper, meta, evidence, status="Architect response"), encoding="utf-8")
            initial = MODULE.build_semantic_cycle_checkpoint_report(plan)
            trigger = initial["trigger"]
            self.assertIsInstance(trigger, dict)
            assert isinstance(trigger, dict)
            self.assertEqual(trigger["trigger_kind"], "scope_churn")

            def render(current_evidence: str, *, status: str) -> str:
                return self._render_v2_subject(helper, meta, current_evidence, status=status)

            plan.write_text(render(evidence, status="Architect response"), encoding="utf-8")
            required = MODULE.build_semantic_cycle_checkpoint_report(plan)
            self.assertEqual((required["state"], required["reason_code"]), ("required", "resolution_required"), required)
            resolution = self._v2_resolution(required, axes)

            same_contract_fence = "```json\n" + json.dumps(resolution, ensure_ascii=False, indent=2) + "\n```"
            plan.write_text(render(evidence + "\n\n" + same_contract_fence, status="Architect response"), encoding="utf-8")
            blocked = MODULE.build_semantic_cycle_checkpoint_report(plan)
            self.assertEqual((blocked["state"], blocked["reason_code"]), ("blocked", "resolution_invalid"), blocked)
            self.assertTrue(
                any(error["code"] == "checkpoint_v2_scope_churn_requires_successor" for error in blocked["errors"]),
                blocked,
            )

            de_scope = copy.deepcopy(resolution)
            for row in de_scope["required_family_resolutions"]:
                row["decision"] = "de_scope"
            de_scope["allowed_next_status"] = "Reviewer intake"
            de_scope_fence = "```json\n" + json.dumps(de_scope, ensure_ascii=False, indent=2) + "\n```"
            plan.write_text(render(evidence + "\n\n" + de_scope_fence, status="Architect response"), encoding="utf-8")
            blocked = MODULE.build_semantic_cycle_checkpoint_report(plan)
            self.assertEqual((blocked["state"], blocked["reason_code"]), ("blocked", "resolution_invalid"), blocked)
            self.assertTrue(
                any(error["code"] == "checkpoint_v2_scope_churn_requires_successor" for error in blocked["errors"]),
                blocked,
            )

            rows = resolution["required_family_resolutions"]
            self.assertIsInstance(rows, list)
            assert isinstance(rows, list)
            successor_ref = self._write_v2_successor_fixture(
                root,
                source_helper=helper,
                source_plan=plan,
                trigger=trigger,
                rows=rows,
                context={"grammar_contour_id": required["grammar_contour_id"]},
                structured=True,
            )
            successor = copy.deepcopy(resolution)
            for row in successor["required_family_resolutions"]:
                row["decision"] = "successor"
            successor.update({"allowed_next_status": "Superseded", "successor_plan_ref": successor_ref})
            successor_fence = "```json\n" + json.dumps(successor, ensure_ascii=False, indent=2) + "\n```"
            plan.write_text(render(evidence + "\n\n" + successor_fence, status="Architect response"), encoding="utf-8")
            accepted = MODULE.build_semantic_cycle_checkpoint_report(plan)
            self.assertEqual(
                (accepted["state"], accepted["reason_code"]),
                ("resolved", "architect_resolution_pending_release"),
                accepted,
            )
            plan.write_text(render(evidence + "\n\n" + successor_fence, status="Superseded"), encoding="utf-8")
            released = MODULE.build_semantic_cycle_checkpoint_report(plan)
            self.assertEqual((released["state"], released["reason_code"]), ("permitted", "resolution_release_valid"), released)

    def test_v2_historical_successor_receipt_survives_normal_terminal_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            helper = self._helper()
            helper.PLAN_REL = "docs/plans/260815_0106_bounded_grammar_successor_history_fixture.md"
            helper.DRAFT_REL = "docs/code_drafts/260815_0106_bounded_grammar_successor_history_fixture__code_draft.md"
            helper.REVIEW_REL = "docs/code_reviews/260815_0106_bounded_grammar_successor_history_fixture.md"
            _helper, plan, evidence = self._survival_fixture(root, status="Architect response", helper=helper)
            meta, axes = self._v2_subject_admission(root, helper, plan)
            plan.write_text(self._render_v2_subject(helper, meta, evidence, status="Architect response"), encoding="utf-8")
            required = MODULE.build_semantic_cycle_checkpoint_report(plan)
            trigger = required["trigger"]
            self.assertIsInstance(trigger, dict)
            assert isinstance(trigger, dict)
            self.assertEqual(trigger["trigger_kind"], "scope_churn")
            resolution = self._v2_resolution(required, axes)
            rows = resolution["required_family_resolutions"]
            self.assertIsInstance(rows, list)
            assert isinstance(rows, list)
            successor_ref = self._write_v2_successor_fixture(
                root,
                source_helper=helper,
                source_plan=plan,
                trigger=trigger,
                rows=rows,
                context={"grammar_contour_id": required["grammar_contour_id"]},
                structured=True,
            )
            successor = copy.deepcopy(resolution)
            for row in successor["required_family_resolutions"]:
                row["decision"] = "successor"
            successor.update({"allowed_next_status": "Superseded", "successor_plan_ref": successor_ref})
            successor_fence = "```json\n" + json.dumps(successor, ensure_ascii=False, indent=2) + "\n```"
            source_evidence = evidence + "\n\n" + successor_fence
            plan.write_text(self._render_v2_subject(helper, meta, source_evidence, status="Architect response"), encoding="utf-8")
            accepted = MODULE.build_semantic_cycle_checkpoint_report(plan)
            self.assertEqual(
                (accepted["state"], accepted["reason_code"]),
                ("resolved", "architect_resolution_pending_release"),
                accepted,
            )

            successor_path = root / successor_ref
            original_successor = successor_path.read_text(encoding="utf-8")
            successor_path.write_text(
                original_successor.replace("**Status:** Architect initial draft", "**Status:** Done", 1),
                encoding="utf-8",
            )
            terminal_before_release = MODULE.build_semantic_cycle_checkpoint_report(plan)
            self.assertEqual(
                (terminal_before_release["state"], terminal_before_release["reason_code"]),
                ("blocked", "resolution_invalid"),
                terminal_before_release,
            )
            self.assertTrue(
                any(error["code"] == "checkpoint_v2_successor_terminal" for error in terminal_before_release["errors"]),
                terminal_before_release,
            )

            plan.write_text(self._render_v2_subject(helper, meta, source_evidence, status="Superseded"), encoding="utf-8")
            for terminal_status in ("Done", "Superseded"):
                with self.subTest(successor_status=terminal_status):
                    successor_path.write_text(
                        original_successor.replace("**Status:** Architect initial draft", f"**Status:** {terminal_status}", 1),
                        encoding="utf-8",
                    )
                    historical = MODULE.build_semantic_cycle_checkpoint_report(plan)
                    self.assertEqual(
                        (historical["state"], historical["reason_code"]),
                        ("permitted", "resolution_release_valid"),
                        historical,
                    )
                    self.assertFalse(
                        any(error["code"] == "checkpoint_historical_resolution_missing" for error in historical["errors"]),
                        historical,
                    )

    def test_v2_resolution_rejects_noncanonical_rows_and_evidence_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            helper = self._helper()
            helper.PLAN_REL = "docs/plans/260815_0102_bounded_grammar_shape_fixture.md"
            helper.DRAFT_REL = "docs/code_drafts/260815_0102_bounded_grammar_shape_fixture__code_draft.md"
            helper.REVIEW_REL = "docs/code_reviews/260815_0102_bounded_grammar_shape_fixture.md"
            _helper, plan, evidence = self._independent_boundary_fixture(root, status="Coder intake", helper=helper)
            meta, axes = self._v2_subject_admission(root, helper, plan)
            plan.write_text(self._render_v2_subject(helper, meta, evidence, status="Coder intake"), encoding="utf-8")
            required = MODULE.build_semantic_cycle_checkpoint_report(plan)
            resolution = self._v2_resolution(required, axes)

            mutations: tuple[tuple[str, callable], ...] = (
                (
                    "unsorted evidence refs",
                    lambda value: value.update(
                        {"decision_evidence_refs": ["docs/code_reviews/z.md#B1", "docs/code_reviews/a.md#B1"]}
                    ),
                ),
                (
                    "stop decision",
                    lambda value: (
                        value["required_family_resolutions"][0].update({"decision": "stop"}),
                        value.update({"allowed_next_status": "Architect response"}),
                    ),
                ),
                (
                    "unknown axis",
                    lambda value: value["required_family_resolutions"][0].update(
                        {"grammar_axis_ids": ["fixture_axis_missing"]}
                    ),
                ),
                ("unknown field", lambda value: value.update({"owner_question_ref": "Q99"})),
            )
            expected_codes = (
                "checkpoint_v2_resolution_evidence_refs_invalid",
                "checkpoint_v2_resolution_decision_invalid",
                "checkpoint_v2_resolution_axes_invalid",
                "checkpoint_v2_resolution_fields_invalid",
            )
            for (label, mutate), expected_code in zip(mutations, expected_codes, strict=True):
                with self.subTest(label=label):
                    candidate = copy.deepcopy(resolution)
                    mutate(candidate)
                    fence = "```json\n" + json.dumps(candidate, ensure_ascii=False, indent=2) + "\n```"
                    plan.write_text(
                        self._render_v2_subject(helper, meta, evidence + "\n\n" + fence, status="Coder intake"),
                        encoding="utf-8",
                    )
                    report = MODULE.build_semantic_cycle_checkpoint_report(plan)
                    self.assertEqual((report["state"], report["reason_code"]), ("blocked", "resolution_invalid"), report)
                    self.assertTrue(any(error["code"] == expected_code for error in report["errors"]), report)

    def test_v2_successor_must_be_structured_not_another_bounded_contour(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            helper = self._helper()
            helper.PLAN_REL = "docs/plans/260815_0103_bounded_grammar_source.md"
            helper.DRAFT_REL = "docs/code_drafts/260815_0103_bounded_grammar_source__code_draft.md"
            helper.REVIEW_REL = "docs/code_reviews/260815_0103_bounded_grammar_source.md"
            _helper, plan, evidence = self._survival_fixture(root, status="Coder intake", helper=helper)
            meta, axes = self._v2_subject_admission(root, helper, plan)
            plan.write_text(self._render_v2_subject(helper, meta, evidence, status="Coder intake"), encoding="utf-8")
            report = MODULE.build_semantic_cycle_checkpoint_report(plan)
            trigger = report["trigger"]
            self.assertIsInstance(trigger, dict)
            assert isinstance(trigger, dict)
            context = {
                "grammar_contour_id": report["grammar_contour_id"],
            }
            resolution = self._v2_resolution(report, axes)
            rows = resolution["required_family_resolutions"]
            self.assertIsInstance(rows, list)
            assert isinstance(rows, list)
            successor_ref = self._write_v2_successor_fixture(
                root,
                source_helper=helper,
                source_plan=plan,
                trigger=trigger,
                rows=rows,
                context=context,
            )
            diagnostics: list[object] = []
            valid = MODULE._semantic_checkpoint_v2_successor_valid(
                plan_path=plan,
                plan_path_value=helper.PLAN_REL,
                successor_ref=successor_ref,
                trigger=trigger,
                rows=rows,
                context=context,
                repo_root=root,
                carrier_line_no=1,
                diagnostics=diagnostics,
            )
            self.assertFalse(valid)
            self.assertTrue(
                any(getattr(item, "code", "") == "checkpoint_v2_successor_admission_invalid" for item in diagnostics)
            )

    def test_v2_contour_budget_cannot_reset_for_a_new_family(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            helper = self._helper()
            helper.PLAN_REL = "docs/plans/260815_0101_bounded_grammar_budget_fixture.md"
            helper.DRAFT_REL = "docs/code_drafts/260815_0101_bounded_grammar_budget_fixture__code_draft.md"
            helper.REVIEW_REL = "docs/code_reviews/260815_0101_bounded_grammar_budget_fixture.md"
            _helper, plan, evidence = self._independent_boundary_fixture(root, status="Coder intake", helper=helper)
            meta, axes = self._v2_subject_admission(root, helper, plan)
            first_text = self._render_v2_subject(helper, meta, evidence, status="Coder intake")
            plan.write_text(first_text, encoding="utf-8")
            first_required = MODULE.build_semantic_cycle_checkpoint_report(plan)
            first_resolution = self._v2_resolution(first_required, axes)
            first_fence = "```json\n" + json.dumps(first_resolution, ensure_ascii=False, indent=2) + "\n```"
            historical = evidence.replace('"current": true', '"current": false', 1) + "\n\n" + first_fence

            next_snapshot = helper.SNAPSHOT
            (root / helper.REVIEW_REL).write_text(
                helper._review_text(next_snapshot, status="❌ S1 blocker(ы)", blockers=((2, "historical-fixed"), (3, "open"))),
                encoding="utf-8",
            )
            proposal = {
                "schema_version": "semantic_review_observation_proposal.v1",
                "progress_verdict": "independent_boundary",
                "progress_evidence_refs": [f"{helper.REVIEW_REL}#B3"],
                "blockers": [
                    {
                        "blocker_ref": f"{helper.REVIEW_REL}#B3",
                        "lineage_relation": "independent_boundary",
                        "predecessor_blocker_ref": None,
                    }
                ],
                "resolved_predecessor_blocker_refs": [f"{helper.REVIEW_REL}#B2"],
            }
            third_evidence = historical + "\n\n" + helper._risk_fence(
                run_id="reviewer_code_risk:checkpoint:20260815T000100Z",
                snapshot=next_snapshot,
            ) + "\n\n" + helper._proposal_fence(proposal)
            plan.write_text(self._render_v2_subject(helper, meta, third_evidence, status="Coder intake"), encoding="utf-8")
            producer = MODULE.build_semantic_review_observation_report(plan)
            materialization = producer["materialization"]
            self.assertIsInstance(materialization, dict, producer)
            assert isinstance(materialization, dict)
            observation = materialization["observation"]
            self.assertIsInstance(observation, dict)
            assert isinstance(observation, dict)
            third_evidence += "\n\n" + helper._final_fence(observation)
            plan.write_text(self._render_v2_subject(helper, meta, third_evidence, status="Coder intake"), encoding="utf-8")
            required = MODULE.build_semantic_cycle_checkpoint_report(plan)
            self.assertEqual((required["state"], required["reason_code"]), ("required", "resolution_required"), required)
            second_resolution = self._v2_resolution(required, axes)
            second_fence = "```json\n" + json.dumps(second_resolution, ensure_ascii=False, indent=2) + "\n```"
            plan.write_text(
                self._render_v2_subject(helper, meta, third_evidence + "\n\n" + second_fence, status="Coder intake"),
                encoding="utf-8",
            )
            blocked = MODULE.build_semantic_cycle_checkpoint_report(plan)
            self.assertEqual((blocked["state"], blocked["reason_code"]), ("blocked", "resolution_invalid"), blocked)
            self.assertTrue(any(error["code"] == "grammar_contour_same_contract_once_reused" for error in blocked["errors"]))

    def test_v2_scope_expansion_reroute_precedes_checkpoint_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            vocab = Path(__file__).resolve().parents[1] / "docs/_meta/plan_vocab.json"
            (root / "docs/_meta").mkdir(parents=True, exist_ok=True)
            (root / "docs/_meta/plan_vocab.json").write_text(vocab.read_text(encoding="utf-8"), encoding="utf-8")
            helper = self._helper()
            helper.PLAN_REL = "docs/plans/260815_0104_bounded_grammar_scope_fixture.md"
            helper.DRAFT_REL = "docs/code_drafts/260815_0104_bounded_grammar_scope_fixture__code_draft.md"
            helper.REVIEW_REL = "docs/code_reviews/260815_0104_bounded_grammar_scope_fixture.md"
            _helper, plan, evidence = self._survival_fixture(root, status="Coder intake", helper=helper)
            meta, _axes = self._v2_subject_admission(root, helper, plan)
            meta["scope_expansion"] = {
                "state": "reroute_required",
                "target_contour": "developer_wave",
                "source_ref": f"{helper.PLAN_REL}#Scope",
                "reason": "fixture scope expansion wins before checkpoint",
            }
            plan.write_text(self._render_v2_subject(helper, meta, evidence, status="Coder intake"), encoding="utf-8")

            checkpoint = MODULE.build_semantic_cycle_checkpoint_report(plan)
            oracle = MODULE.plan_status_oracle.oracle_result(plan)

            self.assertEqual(
                (checkpoint["state"], checkpoint["reason_code"]),
                ("waiting", "scope_expansion_reroute_precedes_checkpoint"),
            )
            self.assertTrue(oracle.route_guard_triggered)
            self.assertEqual(oracle.route_guard_kind, "scope_expansion_reroute_required")
            self.assertEqual(oracle.route_guard_next_owner, "Architect")

    def test_trigger_precedence_preserves_v1_and_gives_v2_scope_churn_priority(self) -> None:
        observations = [
            {
                "observation_id": "sro_previous",
                "target_snapshot": "snapshot-a",
                "contract_fingerprint": {"schema_version": "contract_fingerprint.v1", "sha256": "a"},
                "blockers": [{"blocker_ref": "review.md#B1", "blocker_family_id": "bf_a"}],
            },
            {
                "observation_id": "sro_current",
                "predecessor_observation_id": "sro_previous",
                "target_snapshot": "snapshot-b",
                "contract_fingerprint": {"schema_version": "contract_fingerprint.v1", "sha256": "a"},
                "progress_verdict": "scope_churn",
                "blockers": [
                    {
                        "blocker_ref": "review.md#B1",
                        "predecessor_blocker_ref": "review.md#B1",
                        "blocker_family_id": "bf_a",
                        "lineage_relation": "same_family",
                    },
                    {
                        "blocker_ref": "review.md#B2",
                        "predecessor_blocker_ref": None,
                        "blocker_family_id": "bf_b",
                        "lineage_relation": "independent_boundary",
                    },
                ],
            },
        ]
        v1_diagnostics: list[object] = []
        v1_trigger = MODULE._semantic_checkpoint_trigger_for_observation(
            observations,
            1,
            plan_path_value="fixture.md",
            diagnostics=v1_diagnostics,
        )
        self.assertEqual(v1_diagnostics, [])
        self.assertEqual(v1_trigger["trigger_kind"], "family_survival")
        self.assertEqual(v1_trigger["required_blocker_family_ids"], ["bf_a", "bf_b"])

        v2_diagnostics: list[object] = []
        v2_trigger = MODULE._semantic_checkpoint_trigger_for_observation(
            observations,
            1,
            plan_path_value="fixture.md",
            diagnostics=v2_diagnostics,
            scope_churn_precedes=True,
        )
        self.assertEqual(v2_diagnostics, [])
        self.assertEqual(v2_trigger["trigger_kind"], "scope_churn")
        self.assertEqual(v2_trigger["required_blocker_family_ids"], ["bf_a", "bf_b"])


class PlanRiskLaneSupportPreflightTests(unittest.TestCase):
    def _risk_payload(
        self,
        run_id: str,
        *,
        snapshot: str = "BUNDLE=staged",
        **overrides: object,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "run_id": run_id,
            "lane_id": "reviewer_code_risk",
            "target_snapshot": snapshot,
            "lane_status": "no_findings",
            "findings": [],
            "current": True,
        }
        payload.update(overrides)
        return payload

    def _write_plan(self, root: Path, payloads: list[dict[str, object]]) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        (root / ".git").mkdir(exist_ok=True)
        ensure_fixture_git(root)
        blocks = "\n".join(
            "- reviewer_code_risk lane-run artifact:\n"
            "  ```json\n"
            f"  {json.dumps(payload, ensure_ascii=False, indent=2)}\n"
            "  ```"
            for payload in payloads
        )
        return write_text_fixture(root, "docs/plans/260811_0004_risk_lane_fixture.md", f"# Plan\n\n## Evidence\n{blocks}\n")

    def _write_support(self, root: Path, rel_path: str, payload: dict[str, object]) -> tuple[str, str, Path]:
        path = write_text_fixture(root, rel_path, json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return rel_path, hashlib.sha256(path.read_bytes()).hexdigest(), path

    def test_risk_lane_timestamps_read_local_offsets_and_legacy_msk(self) -> None:
        # Engine stamps carry the numeric offset of the local zone; legacy `MSK` stamps stay readable.
        for value in (
            "2026-07-23 00:39 +0300",
            "2026-07-23 00:39 +03:00",
            "23.07.2026 00:39 +0300",
            "2026-07-22 21:39 +0000",
            "2026-07-23 00:39 MSK",
            "23.07.2026 00:39 MSK",
        ):
            with self.subTest(value=value):
                self.assertEqual(MODULE._sortable_timestamp_value(value), "20260722213900")
        # A zone abbreviation other than legacy `MSK` has no offset for ordering.
        self.assertIsNone(MODULE._sortable_timestamp_value("2026-07-23 00:39 CEST"))

    def test_lifecycle_graph_rejects_contradiction_and_invalid_links(self) -> None:
        cases = {
            "contradiction": (
                [
                    self._risk_payload(
                        "run-old",
                        current=True,
                        superseded_by="run-new",
                    ),
                    self._risk_payload("run-new", current=False),
                ],
                "risk_lane_lifecycle_contradiction",
            ),
            "false_like_lifecycle": (
                [self._risk_payload("run-current", current=True, lifecycle_status="historical")],
                "risk_lane_lifecycle_contradiction",
            ),
            "invalid": (
                [self._risk_payload("run-old", current=False, superseded_by=42)],
                "risk_lane_superseded_by_invalid",
            ),
            "self": (
                [self._risk_payload("run-old", current=False, superseded_by="run-old")],
                "risk_lane_superseded_by_self",
            ),
            "orphan": (
                [self._risk_payload("run-old", current=False, superseded_by="run-new")],
                "risk_lane_superseded_by_orphan",
            ),
            "ambiguous": (
                [
                    self._risk_payload("run-old", current=False, superseded_by="run-new"),
                    self._risk_payload("run-new", current=False),
                    self._risk_payload("run-new", current=True),
                ],
                "risk_lane_superseded_by_ambiguous",
            ),
        }
        for name, (payloads, expected_code) in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmpdir:
                plan_path = self._write_plan(Path(tmpdir) / "repo", payloads)
                selection = MODULE.select_plan_risk_lane_snapshot(plan_path)
                self.assertEqual(selection.error_code, expected_code)
                self.assertIsNone(selection.snapshot)
                self.assertIsNone(selection.payload)
                self.assertGreater(selection.line_no, 0)

    def test_lifecycle_graph_uses_document_order_for_competing_errors(self) -> None:
        invalid_link = self._risk_payload("run-invalid", current=False, superseded_by=42)
        self_link = self._risk_payload("run-self", current=False, superseded_by="run-self")
        cases = (
            (
                "invalid_before_self",
                [invalid_link, self_link],
                "risk_lane_superseded_by_invalid",
                "run-invalid",
            ),
            (
                "self_before_invalid",
                [self_link, invalid_link],
                "risk_lane_superseded_by_self",
                "run-self",
            ),
        )
        for name, payloads, expected_code, expected_run_id in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmpdir:
                plan_path = self._write_plan(Path(tmpdir) / "repo", payloads)
                selection = MODULE.select_plan_risk_lane_snapshot(plan_path)

            self.assertEqual(selection.error_code, expected_code)
            self.assertIsNone(selection.snapshot)
            self.assertIsNone(selection.payload)
            self.assertGreater(selection.line_no, 0)
            self.assertIn(expected_run_id, selection.message or "")

    def test_lifecycle_graph_accepts_canonical_old_to_new_rerun_pair(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "repo"
            old_support_path = write_text_fixture(
                root,
                "docs/code_reviews/assets/risk_lane/run-old-full-payload.json",
                '{"immutable":"old support"}',
            )
            accepted_pf_path = write_text_fixture(
                root,
                "docs/code_reviews/260811_0004_accepted_pf.md",
                "immutable accepted P/F\n",
            )
            plan_path = self._write_plan(
                root,
                [
                    self._risk_payload("run-old", current=False, superseded_by="run-new"),
                    self._risk_payload("run-new", current=True),
                ],
            )
            before_old_support = old_support_path.read_bytes()
            before_accepted_pf = accepted_pf_path.read_bytes()
            selection = MODULE.select_plan_risk_lane_snapshot(plan_path)
            immutable_inputs_unchanged = (
                old_support_path.read_bytes() == before_old_support
                and accepted_pf_path.read_bytes() == before_accepted_pf
            )

        self.assertIsNone(selection.error_code)
        self.assertEqual(selection.run_id, "run-new")
        self.assertEqual(selection.reason, "explicit current marker selected")
        self.assertTrue(immutable_inputs_unchanged)

    def test_current_bundle_preflight_requires_pair_without_changing_raw_selection(self) -> None:
        cases: dict[str, object] = {
            "hashed": "BUNDLE=current bundle_sha256=" + "0" * 64,
            "bare_string": "BUNDLE=current",
            "bare_object": {"target": "BUNDLE=current"},
        }
        for label, snapshot in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir) / "repo"
                plan_path = self._write_plan(
                    root,
                    [self._risk_payload("run-current", snapshot=snapshot)],
                )
                selection = MODULE.select_plan_risk_lane_snapshot(plan_path)
                diagnostics = MODULE.preflight_selected_risk_lane_support(plan_path, selection)

            self.assertIsNone(selection.error_code)
            self.assertEqual(selection.run_id, "run-current")
            self.assertEqual(
                [diagnostic.code for diagnostic in diagnostics],
                [
                    "missing_risk_lane_support_payload_ref",
                    "missing_risk_lane_support_payload_hash",
                ],
            )

    def test_preflight_uses_plan_root_fallback_and_never_writes_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "repo"
            support_payload = self._risk_payload("run-valid")
            support_rel, support_sha, support_path = self._write_support(
                root,
                "docs/code_reviews/assets/risk_lane/full_payload.json",
                support_payload,
            )
            compact_payload = self._risk_payload(
                "run-valid",
                full_payload_ref=support_rel,
                full_payload_sha256=support_sha,
            )
            plan_path = self._write_plan(root, [compact_payload])
            selection = MODULE.select_plan_risk_lane_snapshot(plan_path)
            before_plan = plan_path.read_bytes()
            before_support = support_path.read_bytes()
            previous_cwd = Path.cwd()
            try:
                os.chdir(Path(tmpdir).parent)
                diagnostics = MODULE.preflight_selected_risk_lane_support(plan_path, selection)
            finally:
                os.chdir(previous_cwd)

            self.assertEqual(diagnostics, ())
            self.assertEqual(plan_path.read_bytes(), before_plan)
            self.assertEqual(support_path.read_bytes(), before_support)

            in_root_link = root / "docs/code_reviews/assets/risk_lane/full_payload_link.json"
            in_root_link.symlink_to(support_path)
            linked_plan = self._write_plan(
                root,
                [
                    self._risk_payload(
                        "run-valid",
                        full_payload_ref=str(in_root_link.relative_to(root)),
                        full_payload_sha256=support_sha,
                    )
                ],
            )
            linked_selection = MODULE.select_plan_risk_lane_snapshot(linked_plan)
            self.assertEqual(
                [
                    diagnostic.code
                    for diagnostic in MODULE.preflight_selected_risk_lane_support(linked_plan, linked_selection)
                ],
                ["invalid_risk_lane_support_payload_ref"],
            )

    def test_preflight_orders_pair_before_json_and_enforces_ref_containment(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_root = Path(tmpdir)
            root = tmp_root / "repo"
            malformed_rel = "docs/code_reviews/assets/risk_lane/malformed.json"
            write_text_fixture(root, malformed_rel, "{")
            malformed_payload = self._risk_payload("run-malformed", full_payload_ref=malformed_rel)
            malformed_plan = self._write_plan(root, [malformed_payload])
            malformed_selection = MODULE.select_plan_risk_lane_snapshot(malformed_plan)
            diagnostics = MODULE.preflight_selected_risk_lane_support(malformed_plan, malformed_selection)
            self.assertEqual(
                [diagnostic.code for diagnostic in diagnostics],
                ["missing_risk_lane_support_payload_hash", "invalid_risk_lane_support_payload_json"],
            )

            outside_support = tmp_root / "outside.json"
            outside_support.write_text("{}", encoding="utf-8")
            escaped_link = root / "docs/code_reviews/assets/risk_lane/escaped.json"
            escaped_link.parent.mkdir(parents=True, exist_ok=True)
            escaped_link.symlink_to(outside_support)
            escaped_payload = self._risk_payload(
                "run-escaped",
                full_payload_ref=str(escaped_link.relative_to(root)),
                full_payload_sha256=hashlib.sha256(outside_support.read_bytes()).hexdigest(),
            )
            escaped_plan = self._write_plan(root, [escaped_payload])
            escaped_selection = MODULE.select_plan_risk_lane_snapshot(escaped_plan)
            escaped_diagnostics = MODULE.preflight_selected_risk_lane_support(escaped_plan, escaped_selection)

        self.assertEqual([diagnostic.code for diagnostic in escaped_diagnostics], ["invalid_risk_lane_support_payload_ref"])

    def test_all_history_manifest_keeps_historical_bytes_without_reselecting_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "repo"
            historical_rel = "docs/code_reviews/assets/risk_lane/historical-red.txt"
            historical_path = write_text_fixture(root, historical_rel, "legacy red payload; intentionally not JSON\n")
            historical_sha = hashlib.sha256(historical_path.read_bytes()).hexdigest()
            current_payload = self._risk_payload("run-current")
            current_rel, current_sha, _ = self._write_support(
                root,
                "docs/code_reviews/assets/risk_lane/current.json",
                current_payload,
            )
            plan_path = self._write_plan(
                root,
                [
                    {
                        "lane_id": "reviewer_code_risk",
                        "run_id": "run-historical",
                        "current": False,
                        "full_payload_ref": historical_rel,
                        "full_payload_sha256": historical_sha,
                    },
                    self._risk_payload(
                        "run-current",
                        full_payload_ref=current_rel,
                        full_payload_sha256=current_sha,
                    ),
                    {
                        "lane_id": "reviewer_code_risk",
                        "run_id": "run-historical-duplicate",
                        "current": False,
                        "full_payload_ref": historical_rel,
                        "full_payload_sha256": historical_sha,
                    },
                ],
            )
            before = (plan_path.read_bytes(), historical_path.read_bytes())
            manifest = MODULE.collect_plan_risk_lane_support_refs(plan_path, project_root=root)
            selection = MODULE.select_plan_risk_lane_snapshot(plan_path)
            unchanged = before == (plan_path.read_bytes(), historical_path.read_bytes())

        self.assertEqual(
            manifest.records,
            ((historical_rel, historical_sha), (current_rel, current_sha)),
        )
        self.assertEqual(manifest.diagnostics, ())
        self.assertEqual(selection.run_id, "run-current")
        self.assertTrue(unchanged)

    def test_all_history_manifest_rejects_incomplete_unsafe_and_conflicting_pairs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_root = Path(tmpdir)
            root = tmp_root / "repo"
            support_rel = "docs/code_reviews/assets/risk_lane/support.json"
            support_path = write_text_fixture(root, support_rel, "history bytes\n")
            support_sha = hashlib.sha256(support_path.read_bytes()).hexdigest()
            outside_path = tmp_root / "outside.json"
            outside_path.write_text("outside\n", encoding="utf-8")
            plan_path = self._write_plan(
                root,
                [
                    {"lane_id": "reviewer_code_risk", "full_payload_ref": support_rel},
                    {"lane_id": "reviewer_code_risk", "full_payload_sha256": support_sha},
                    {
                        "lane_id": "reviewer_code_risk",
                        "full_payload_ref": "../outside.json",
                        "full_payload_sha256": hashlib.sha256(outside_path.read_bytes()).hexdigest(),
                    },
                    {
                        "lane_id": "reviewer_code_risk",
                        "full_payload_ref": support_rel,
                        "full_payload_sha256": support_sha,
                    },
                    {
                        "lane_id": "reviewer_code_risk",
                        "full_payload_ref": support_rel,
                        "full_payload_sha256": "0" * 64,
                    },
                ],
            )
            before = (plan_path.read_bytes(), support_path.read_bytes())
            manifest = MODULE.collect_plan_risk_lane_support_refs(plan_path, project_root=root)
            unchanged = before == (plan_path.read_bytes(), support_path.read_bytes())

        self.assertEqual(manifest.records, ((support_rel, support_sha),))
        self.assertEqual(
            [diagnostic.code for diagnostic in manifest.diagnostics],
            [
                "missing_risk_lane_support_payload_hash",
                "missing_risk_lane_support_payload_ref",
                "invalid_risk_lane_support_payload_ref",
                "risk_lane_support_payload_hash_conflict",
            ],
        )
        self.assertTrue(unchanged)

    def test_all_history_manifest_rejects_leaf_and_ancestor_symlink_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "repo"
            leaf_target = write_text_fixture(
                root,
                "docs/code_reviews/assets/risk_lane/leaf-target.json",
                "leaf bytes\n",
            )
            ancestor_target = write_text_fixture(
                root,
                "docs/code_reviews/assets/risk_lane/ancestor-target/support.json",
                "ancestor bytes\n",
            )
            leaf_link = root / "docs/code_reviews/assets/risk_lane/leaf-link.json"
            leaf_link.symlink_to(leaf_target)
            ancestor_link = root / "docs/code_reviews/assets/risk_lane/ancestor-link"
            ancestor_link.symlink_to(ancestor_target.parent, target_is_directory=True)
            leaf_ref = str(leaf_link.relative_to(root))
            ancestor_ref = f"{ancestor_link.relative_to(root).as_posix()}/support.json"
            plan_path = self._write_plan(
                root,
                [
                    {
                        "lane_id": "reviewer_code_risk",
                        "run_id": "historical-leaf-link",
                        "current": False,
                        "full_payload_ref": leaf_ref,
                        "full_payload_sha256": hashlib.sha256(leaf_target.read_bytes()).hexdigest(),
                    },
                    {
                        "lane_id": "reviewer_code_risk",
                        "run_id": "historical-ancestor-link",
                        "current": False,
                        "full_payload_ref": ancestor_ref,
                        "full_payload_sha256": hashlib.sha256(ancestor_target.read_bytes()).hexdigest(),
                    },
                ],
            )
            before = (plan_path.read_bytes(), leaf_target.read_bytes(), ancestor_target.read_bytes())
            manifest = MODULE.collect_plan_risk_lane_support_refs(plan_path, project_root=root)
            unchanged = before == (plan_path.read_bytes(), leaf_target.read_bytes(), ancestor_target.read_bytes())

        self.assertEqual(manifest.records, ())
        self.assertEqual(
            [diagnostic.code for diagnostic in manifest.diagnostics],
            ["invalid_risk_lane_support_payload_ref", "invalid_risk_lane_support_payload_ref"],
        )
        self.assertTrue(unchanged)

    def test_all_history_manifest_reports_missing_and_mismatched_bytes_but_legacy_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "repo"
            missing_rel = "docs/code_reviews/assets/risk_lane/missing.json"
            mismatch_rel = "docs/code_reviews/assets/risk_lane/mismatch.json"
            mismatch_path = write_text_fixture(root, mismatch_rel, "bytes that do not match\n")
            plan_path = self._write_plan(
                root,
                [
                    {
                        "lane_id": "reviewer_code_risk",
                        "full_payload_ref": missing_rel,
                        "full_payload_sha256": "a" * 64,
                    },
                    {
                        "lane_id": "reviewer_code_risk",
                        "full_payload_ref": mismatch_rel,
                        "full_payload_sha256": "b" * 64,
                    },
                ],
            )
            manifest = MODULE.collect_plan_risk_lane_support_refs(plan_path, project_root=root)
            legacy_plan = self._write_plan(root, [{"lane_id": "reviewer_code_risk", "run_id": "legacy"}])
            legacy_manifest = MODULE.collect_plan_risk_lane_support_refs(legacy_plan, project_root=root)

        self.assertEqual(manifest.records, ())
        self.assertEqual(
            [diagnostic.code for diagnostic in manifest.diagnostics],
            ["missing_risk_lane_support_payload_file", "risk_lane_support_payload_hash_mismatch"],
        )
        self.assertEqual(legacy_manifest.records, ())
        self.assertEqual(legacy_manifest.diagnostics, ())


class MachineAuthorityAdmissionLintTests(unittest.TestCase):
    PLAN_REL = "docs/plans/260814_0900_machine_authority_fixture.md"
    DRAFT_REL = "docs/code_drafts/260814_0900_machine_authority_fixture__code_draft.md"

    def _write_required_fixture(self, root: Path, *, cutover_policy: object | None = None) -> Path:
        decision = _fixture_required_machine_authority_decision(
            plan_rel=self.PLAN_REL,
            decision_id="mad-260814-0900",
            route_id="fixture_route",
            cutover_policy=cutover_policy,
        )
        return _write_fixture_required_machine_authority_plan(
            root,
            plan_rel=self.PLAN_REL,
            decision=decision,
        )

    def _write_required_fixture_at(
        self,
        root: Path,
        rel_path: str,
        *,
        cutover_policy: object | None = None,
    ) -> Path:
        decision = _fixture_required_machine_authority_decision(
            plan_rel=rel_path,
            decision_id="mad-260814-0900",
            route_id="fixture_route",
            cutover_policy=cutover_policy,
        )
        return _write_fixture_required_machine_authority_plan(
            root,
            plan_rel=rel_path,
            decision=decision,
        )

    def _write_na_fixture(
        self,
        root: Path,
        rel_path: str,
        *,
        decision_extra: dict[str, object] | None = None,
        ref_extra: dict[str, object] | None = None,
    ) -> Path:
        (root / ".git").mkdir(exist_ok=True)
        ensure_fixture_git(root)
        plan = root / rel_path
        plan.parent.mkdir(parents=True, exist_ok=True)
        decision: dict[str, object] = {
            "schema_version": MODULE.plan_status_oracle.MACHINE_AUTHORITY_DECISION_SCHEMA,
            "applicability": "not_applicable",
            "reason_code": "no_machine_authority_change",
        }
        if decision_extra:
            decision.update(decision_extra)
        plan.write_text(
            "# Plan: N-A authority fixture\n\n"
            "**Plan type:** review-only\n"
            "**Status:** Reviewer intake\n\n"
            "## Meta\n```json\n"
            + json.dumps({"plan_meta": {"cluster": "process", "machine_authority_decision": decision}}, indent=2)
            + "\n```\n",
            encoding="utf-8",
        )
        digest = MODULE.plan_status_oracle.machine_authority_decision_sha256(decision)
        ref: dict[str, object] = {
            "applicability": "not_applicable",
            "reason_code": "no_machine_authority_change",
            "carrier_sha256": digest,
        }
        if ref_extra:
            ref.update(ref_extra)
        draft = root / f"docs/code_drafts/{plan.stem}__code_draft.md"
        draft.parent.mkdir(parents=True, exist_ok=True)
        draft.write_text(
            "# Code draft: N-A fixture\n\n```json\n"
            + json.dumps(
                {
                    "code_draft_meta": {
                        "plan": rel_path,
                        "cluster": "process",
                        "machine_authority_decision_ref": ref,
                    }
                },
                indent=2,
            )
            + "\n```\n",
            encoding="utf-8",
        )
        return plan

    def _rewrite_fixture_decision_and_ref(
        self,
        plan: Path,
        mutate: callable,
    ) -> None:
        plan_text = plan.read_text(encoding="utf-8")
        strict = MODULE.strict_plan_meta_json(plan_text.splitlines())
        self.assertEqual(strict.state, "valid")
        assert strict.plan_meta is not None
        plan_meta = json.loads(json.dumps(dict(strict.plan_meta)))
        plan_meta.pop("scope_expansion", None)
        decision = plan_meta["machine_authority_decision"]
        assert isinstance(decision, dict)
        mutate(decision)
        confirmation = decision["owner_confirmation"]
        assert isinstance(confirmation, dict)
        digest = MODULE.plan_status_oracle.machine_authority_decision_sha256(decision)
        confirmation["carrier_sha256"] = digest
        meta_start = plan_text.index("```json\n", plan_text.index("## Meta")) + len("```json\n")
        meta_end = plan_text.index("\n```", meta_start)
        plan.write_text(
            plan_text[:meta_start]
            + json.dumps({"plan_meta": plan_meta}, indent=2)
            + plan_text[meta_end:],
            encoding="utf-8",
        )

        draft = plan.parents[2] / "docs" / "code_drafts" / f"{plan.stem}__code_draft.md"
        draft_text = draft.read_text(encoding="utf-8")
        draft_start = draft_text.index("```json\n") + len("```json\n")
        draft_end = draft_text.index("\n```", draft_start)
        draft_payload = json.loads(draft_text[draft_start:draft_end])
        ref = draft_payload["code_draft_meta"]["machine_authority_decision_ref"]
        assert isinstance(ref, dict)
        ref["carrier_sha256"] = digest
        draft.write_text(
            draft_text[:draft_start]
            + json.dumps(draft_payload, indent=2)
            + draft_text[draft_end:],
            encoding="utf-8",
        )

    def _rewrite_plan_decision(
        self,
        plan: Path,
        mutate: callable,
        *,
        strip_scope_expansion: bool = False,
    ) -> None:
        plan_text = plan.read_text(encoding="utf-8")
        strict = MODULE.strict_plan_meta_json(plan_text.splitlines())
        self.assertEqual(strict.state, "valid")
        assert strict.plan_meta is not None
        plan_meta = json.loads(json.dumps(dict(strict.plan_meta)))
        if strip_scope_expansion:
            plan_meta.pop("scope_expansion", None)
        decision = plan_meta["machine_authority_decision"]
        assert isinstance(decision, dict)
        mutate(decision)
        confirmation = decision["owner_confirmation"]
        assert isinstance(confirmation, dict)
        confirmation["carrier_sha256"] = MODULE.plan_status_oracle.machine_authority_decision_sha256(decision)
        meta_start = plan_text.index("```json\n", plan_text.index("## Meta")) + len("```json\n")
        meta_end = plan_text.index("\n```", meta_start)
        plan.write_text(
            plan_text[:meta_start]
            + json.dumps({"plan_meta": plan_meta}, indent=2)
            + plan_text[meta_end:],
            encoding="utf-8",
        )

    @staticmethod
    def _grammar_contour_id(contour: dict[str, object], authority_host: dict[str, object]) -> str:
        identity = {
            "schema_version": "grammar_contour_identity.v1",
            "contour_origin_plan": contour["contour_origin_plan"],
            "contour_origin_decision_id": contour["contour_origin_decision_id"],
            "authority_host": authority_host,
            "parser_owner": contour["parser_owner"],
            "parser_or_library": contour["parser_or_library"],
            "axes": contour["axes"],
            "proof_matrix_ref": contour["proof_matrix_ref"],
            "budget_policy": contour["budget_policy"],
            "exit_rule": contour["exit_rule"],
        }
        canonical = json.dumps(
            MODULE.plan_status_oracle._machine_authority_normalize_json(identity),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return "gc_" + hashlib.sha256(canonical).hexdigest()

    def _set_bounded_grammar(
        self,
        decision: dict[str, object],
        *,
        origin_plan: str | None = None,
        origin_id: str | None = None,
        axes: list[dict[str, str]] | None = None,
        proof_matrix_ref: str | None = None,
        exit_rule: str = "structured_successor_or_literal_de_scope",
    ) -> None:
        route = decision["recommended_route"]
        assert isinstance(route, dict)
        authority_host = route["authority_host"]
        assert isinstance(authority_host, dict)
        decision_id = decision["decision_id"]
        assert isinstance(decision_id, str)
        contour: dict[str, object] = {
            "contour_origin_plan": origin_plan or self.PLAN_REL,
            "contour_origin_decision_id": origin_id or decision_id,
            "grammar_contour_id": "",
            "parser_owner": "Architect",
            "parser_or_library": "strict_json",
            "axes": axes
            or [
                {"axis_id": "admission", "description": "admission shape"},
                {"axis_id": "exit", "description": "structured successor exit"},
            ],
            "proof_matrix_ref": proof_matrix_ref or f"{self.PLAN_REL}#Acceptance criteria / DoD",
            "budget_policy": "same_contract_once_total",
            "exit_rule": exit_rule,
        }
        contour["grammar_contour_id"] = self._grammar_contour_id(contour, authority_host)
        route["kind"] = "bounded_grammar"
        route["grammar_contour"] = contour

    def test_machine_authority_requirement_depends_on_handoff_status_not_filename(self) -> None:
        def carrier_free_text(status: str) -> str:
            return (
                "# Plan: filename-invariant authority fixture\n\n"
                "**Plan type:** dev\n"
                f"**Status:** {status}\n\n"
                "## Meta\n```json\n{\"plan_meta\": {\"cluster\": \"process\"}}\n```\n"
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            root.joinpath(".git").mkdir()
            ensure_fixture_git(root)

            def write(rel_path: str, text: str) -> Path:
                path = root / rel_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
                return path

            names = (
                "260925_0100_current_name.md",
                "260101_0100_old_name.md",
                "undated_name.md",
                "260925_0100-nonstandard.MD",
            )
            downstream = []
            for status in ("Ready for Coder", "Planner intake", "Architect arch review"):
                for name in names:
                    path = write(f"docs/plans/{status.casefold().replace(' ', '_')}_{name}", carrier_free_text(status))
                    downstream.append(
                        (
                            status,
                            name,
                            MODULE.plan_status_oracle.machine_authority_decision_readback(path),
                            MODULE.plan_status_oracle.oracle_result(path),
                            MODULE.validate_machine_authority_decision(path, MODULE.read_text(path)),
                        )
                    )
            initial_paths = tuple(
                write(f"docs/plans/initial_{name}", carrier_free_text("Architect initial draft")) for name in names
            )
            template_path = write("docs/plans/_template.md", carrier_free_text("Ready for Coder"))
            initial = [
                (
                    MODULE.plan_status_oracle.machine_authority_decision_readback(path),
                    MODULE.validate_machine_authority_decision(path, MODULE.read_text(path)),
                )
                for path in initial_paths
            ]
            template = MODULE.plan_status_oracle.machine_authority_decision_readback(template_path)

        for status, name, readback, result, findings in downstream:
            with self.subTest(status=status, name=name):
                self.assertEqual(
                    (readback.state, readback.reason_code, readback.route_guard_required),
                    ("missing", "missing_required_carrier", True),
                )
                self.assertTrue(result.route_guard_triggered)
                self.assertEqual(result.route_guard_kind, "machine_authority_decision_missing_required_carrier")
                self.assertEqual(len(findings), 1)
                self.assertIn("missing_required_carrier", findings[0].message)

        for readback, findings in initial:
            self.assertEqual(
                (readback.state, readback.reason_code, readback.route_guard_required),
                ("not_required", "initial_architect_draft_no_carrier", False),
            )
            self.assertEqual(findings, [])

        self.assertEqual(
            (template.state, template.reason_code, template.route_guard_required),
            ("not_required", "template_no_carrier", False),
        )

    def test_machine_authority_guards_remain_strict_across_filename_shapes(self) -> None:
        names = (
            "260925_0100_current_name.md",
            "260101_0100_old_name.md",
            "undated_name.md",
            "260925_0100-nonstandard.MD",
        )
        cases = (
            (
                "invalid_data",
                "carrier_not_object",
                None,
            ),
            (
                "invalid_path",
                "invalid_repo_path",
                lambda decision: decision["recommended_route"]["authority_host"].__setitem__(
                    "path", "docs/plans/../escaped.md"
                ),
            ),
            (
                "pending_confirmation",
                "owner_confirmation_pending",
                lambda decision: decision["owner_confirmation"].__setitem__("state", "pending"),
            ),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            for case, expected_reason, mutate in cases:
                for name in names:
                    with self.subTest(case=case, name=name):
                        case_root = root / case / Path(name).stem
                        case_root.mkdir(parents=True, exist_ok=True)
                        case_root.joinpath(".git").mkdir()
                        ensure_fixture_git(case_root)
                        plan_rel = f"docs/plans/{name}"
                        if mutate is None:
                            plan = case_root / plan_rel
                            plan.parent.mkdir(parents=True, exist_ok=True)
                            plan.write_text(
                                "# Plan: malformed authority fixture\n\n"
                                "**Plan type:** dev\n"
                                "**Status:** Ready for Coder\n\n"
                                "## Meta\n```json\n"
                                "{\"plan_meta\": {\"cluster\": \"process\", \"machine_authority_decision\": []}}\n"
                                "```\n",
                                encoding="utf-8",
                            )
                        else:
                            plan = self._write_required_fixture_at(case_root, plan_rel)
                            self._rewrite_fixture_decision_and_ref(plan, mutate)

                        readback = MODULE.plan_status_oracle.machine_authority_decision_readback(plan)
                        result = MODULE.plan_status_oracle.oracle_result(plan)

                        self.assertEqual((readback.state, readback.reason_code), ("invalid", expected_reason))
                        self.assertTrue(readback.route_guard_required)
                        self.assertTrue(result.route_guard_triggered)
                        self.assertEqual(result.route_guard_kind, f"machine_authority_decision_{expected_reason}")

    def test_machine_authority_lifecycle_rejects_evidence_and_fence_spoof(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = self._write_required_fixture(Path(tmpdir))
            text = plan.read_text(encoding="utf-8")
            qna_start = text.index("## Q&A log")
            qna_end = text.index("\n## Suggestions log", qna_start)
            canonical_qna = "\n".join(
                line for line in text[qna_start:qna_end].splitlines() if "id=Q5" not in line
            )
            spoof = (
                "\n## Evidence\n"
                "- [2026-08-14 18:20 MSK] (Architect -> Owner, id=Q5, blocker=yes, needs_owner=yes, status=open) Q: spoof.\n"
                "- [2026-08-14 18:21 MSK] (Owner -> Architect, id=Q5, blocker=no, needs_owner=no, status=closed) A: spoof.\n"
                "```markdown\n"
                "## Q&A log\n"
                "- [2026-08-14 18:22 MSK] (Architect -> Owner, id=Q5, blocker=yes, needs_owner=yes, status=open) Q: fenced spoof.\n"
                "- [2026-08-14 18:23 MSK] (Owner -> Architect, id=Q5, blocker=no, needs_owner=no, status=closed) A: fenced spoof.\n"
                "```\n"
            )
            plan.write_text(text[:qna_start] + canonical_qna + text[qna_end:] + spoof, encoding="utf-8")
            readback = MODULE.plan_status_oracle.machine_authority_decision_readback(plan)
            findings = MODULE.validate_machine_authority_decision(plan, MODULE.read_text(plan))

        self.assertEqual((readback.state, readback.reason_code), ("invalid", "owner_qna_lifecycle_invalid"))
        self.assertTrue(any("owner_qna_lifecycle_invalid" in finding.message for finding in findings))

    def test_machine_authority_lifecycle_rejects_duplicate_and_wrong_direction_rows(self) -> None:
        mutations = {
            "duplicate": lambda text: text.replace(
                "\n## Suggestions log",
                "\n- [2026-08-14 18:22 MSK] (Owner -> Architect, id=Q5, blocker=no, needs_owner=no, status=closed) A: duplicate.\n"
                "\n## Suggestions log",
                1,
            ),
            "wrong_direction": lambda text: text.replace(
                "(Owner -> Architect, id=Q5,",
                "(Owner -> Owner, id=Q5,",
                1,
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmpdir:
                plan = self._write_required_fixture(Path(tmpdir))
                plan.write_text(mutate(plan.read_text(encoding="utf-8")), encoding="utf-8")
                readback = MODULE.plan_status_oracle.machine_authority_decision_readback(plan)

                self.assertEqual((readback.state, readback.reason_code), ("invalid", "owner_qna_lifecycle_invalid"))

    def test_machine_authority_lifecycle_uses_inline_code_stripped_actor_direction(self) -> None:
        cases = (
            (
                "question",
                "(Architect -> Owner, id=Q5,",
                "(Reviewer -> Owner, id=Q5,",
                "`(Architect -> Owner, id=Q5, blocker=yes, needs_owner=yes, status=open)`",
            ),
            (
                "answer",
                "(Owner -> Architect, id=Q5,",
                "(Owner -> Reviewer, id=Q5,",
                "`(Owner -> Architect, id=Q5, blocker=no, needs_owner=no, status=closed)`",
            ),
        )
        for label, actual, forged, inline_example in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmpdir:
                plan = self._write_required_fixture(Path(tmpdir))
                lines = plan.read_text(encoding="utf-8").splitlines()
                for index, line in enumerate(lines):
                    if actual in line:
                        lines[index] = line.replace(actual, forged, 1) + " " + inline_example
                        break
                else:
                    self.fail(f"missing Q5 {label} fixture row")
                plan.write_text("\n".join(lines) + "\n", encoding="utf-8")

                generic_state, _, _, _ = MODULE.plan_status_oracle.owner_qna_readback(plan.read_text(encoding="utf-8"))
                readback = MODULE.plan_status_oracle.machine_authority_decision_readback(plan)

                self.assertEqual(generic_state, "clean")
                self.assertEqual((readback.state, readback.reason_code), ("invalid", "owner_qna_lifecycle_invalid"))
                self.assertTrue(readback.route_guard_required)

    def test_machine_authority_lifecycle_rejects_plain_body_direction_spoof(self) -> None:
        cases = (
            (
                "question",
                "(Architect -> Owner, id=Q5,",
                "(Reviewer -> Owner, id=Q5,",
                "(Architect -> Owner, id=Q5, blocker=yes, needs_owner=yes, status=open)",
            ),
            (
                "answer",
                "(Owner -> Architect, id=Q5,",
                "(Owner -> Reviewer, id=Q5,",
                "(Owner -> Architect, id=Q5, blocker=no, needs_owner=no, status=closed)",
            ),
            (
                "ambiguous_leading_question",
                "(Architect -> Owner, id=Q5,",
                "(Architect -> Owner, id=Q5,",
                "(Architect -> Owner, id=Q5, blocker=yes, needs_owner=yes, status=open)",
            ),
        )
        for label, actual, forged, plain_body_tuple in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmpdir:
                plan = self._write_required_fixture(Path(tmpdir))
                lines = plan.read_text(encoding="utf-8").splitlines()
                for index, line in enumerate(lines):
                    if actual in line:
                        lines[index] = line.replace(actual, forged, 1) + " " + plain_body_tuple
                        break
                else:
                    self.fail(f"missing Q5 {label} fixture row")
                plan.write_text("\n".join(lines) + "\n", encoding="utf-8")

                generic_state, _, _, _ = MODULE.plan_status_oracle.owner_qna_readback(plan.read_text(encoding="utf-8"))
                readback = MODULE.plan_status_oracle.machine_authority_decision_readback(plan)

                self.assertEqual(generic_state, "clean")
                self.assertEqual((readback.state, readback.reason_code), ("invalid", "owner_qna_lifecycle_invalid"))
                self.assertTrue(readback.route_guard_required)

    def test_fixture_literal_arrays_are_sorted_and_rehashed_order_mutations_fail_closed(self) -> None:
        literal_arrays = {
            "impacts": ["authorization", "routing"],
            "derived_consumers": ["fixture_censor", "fixture_oracle"],
            "identity_fields": ["decision_id", "plan_path"],
            "alternative_ids": ["fixture_free_form", "fixture_prose"],
        }
        expected_sha = "817a45e216ebfe5de790250a93dd395a0436bba3e63cf55d8c8d19cfb55ba0cb"
        mutations = {
            "impacts": lambda decision: decision.__setitem__("impacts", list(reversed(decision["impacts"]))),
            "derived_consumers": lambda decision: decision["recommended_route"].__setitem__(
                "derived_consumers", list(reversed(decision["recommended_route"]["derived_consumers"]))
            ),
            "identity_fields": lambda decision: decision["recommended_route"].__setitem__(
                "identity_fields", list(reversed(decision["recommended_route"]["identity_fields"]))
            ),
            "alternative_ids": lambda decision: decision.__setitem__(
                "alternatives", list(reversed(decision["alternatives"]))
            ),
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            canonical = self._write_required_fixture(root)
            strict = MODULE.strict_plan_meta_json(MODULE.read_text(canonical))
            self.assertEqual(strict.state, "valid")
            assert strict.plan_meta is not None
            decision = strict.plan_meta["machine_authority_decision"]
            assert isinstance(decision, dict)
            route = decision["recommended_route"]
            assert isinstance(route, dict)
            self.assertEqual(decision["impacts"], literal_arrays["impacts"])
            self.assertEqual(route["derived_consumers"], literal_arrays["derived_consumers"])
            self.assertEqual(route["identity_fields"], literal_arrays["identity_fields"])
            self.assertEqual([item["id"] for item in decision["alternatives"]], literal_arrays["alternative_ids"])
            self.assertEqual(MODULE.plan_status_oracle.machine_authority_decision_sha256(decision), expected_sha)
            self.assertEqual(MODULE.plan_status_oracle.machine_authority_decision_readback(canonical).state, "frozen_confirmed")

            for label, mutate in mutations.items():
                with self.subTest(label=label):
                    plan = self._write_required_fixture(root)
                    self._rewrite_fixture_decision_and_ref(plan, mutate)
                    readback = MODULE.plan_status_oracle.machine_authority_decision_readback(plan)
                    result = MODULE.plan_status_oracle.oracle_result(plan)
                    self.assertEqual(readback.state, "invalid")
                    self.assertTrue(readback.route_guard_required)
                    self.assertTrue(result.route_guard_triggered)
                    expected_reason = "alternatives_invalid" if label == "alternative_ids" else "unsorted_array_value"
                    self.assertEqual(result.route_guard_kind, f"machine_authority_decision_{expected_reason}")

    def test_required_route_is_generic_and_rejects_retired_optional_field(self) -> None:
        def configure_generic_route(decision: dict[str, object]) -> None:
            route = decision["recommended_route"]
            assert isinstance(route, dict)
            authority_host = route["authority_host"]
            assert isinstance(authority_host, dict)
            authority_host["locator"] = "evidence_schema:fixture_authority.v1"
            route["canonical_reader"] = "fixture-reader-v2"
            route["schema"] = "fixture_authority.v1"
            route["cardinality"] = "one_per_current_plan"

        invalid_mutations = {
            "locator": (
                lambda decision: decision["recommended_route"]["authority_host"].__setitem__("locator", "manual:route"),
                "authority_locator_invalid",
            ),
            "canonical_reader": (
                lambda decision: decision["recommended_route"].__setitem__("canonical_reader", ""),
                "invalid_string",
            ),
            "schema": (
                lambda decision: decision["recommended_route"].__setitem__("schema", ""),
                "invalid_string",
            ),
            "cardinality": (
                lambda decision: decision["recommended_route"].__setitem__("cardinality", ""),
                "invalid_string",
            ),
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            generic = self._write_required_fixture(root)
            self._rewrite_fixture_decision_and_ref(generic, configure_generic_route)
            readback = MODULE.plan_status_oracle.machine_authority_decision_readback(generic)
            self.assertEqual(
                (readback.state, readback.reason_code, readback.decision_id, readback.route),
                ("frozen_confirmed", "ok", "mad-260814-0900", "fixture_route"),
            )

            for label, (mutate, expected_reason) in invalid_mutations.items():
                with self.subTest(field=label):
                    plan = self._write_required_fixture(root)
                    self._rewrite_fixture_decision_and_ref(plan, mutate)
                    invalid = MODULE.plan_status_oracle.machine_authority_decision_readback(plan)
                    self.assertEqual((invalid.state, invalid.reason_code), ("invalid", expected_reason))

            retired_optional_field = "boot" + "strap"
            plan = self._write_required_fixture(root)
            self._rewrite_fixture_decision_and_ref(
                plan,
                lambda decision: decision.__setitem__(retired_optional_field, {"mode": "retired"}),
            )
            invalid = MODULE.plan_status_oracle.machine_authority_decision_readback(plan)

        self.assertEqual((invalid.state, invalid.reason_code), ("invalid", "unknown_or_missing_keys"))

    def test_machine_authority_rejects_nfc_equivalent_identity_duplicates(self) -> None:
        duplicate_ids = ["e\u0301", "é"]

        def mutate_alternatives(decision: dict[str, object]) -> None:
            alternatives = decision["alternatives"]
            assert isinstance(alternatives, list)
            for alternative, duplicate_id in zip(alternatives, duplicate_ids, strict=True):
                assert isinstance(alternative, dict)
                alternative["id"] = duplicate_id

        def mutate_axes(decision: dict[str, object]) -> None:
            self._set_bounded_grammar(
                decision,
                axes=[
                    {"axis_id": duplicate_ids[0], "description": "first canonical identity"},
                    {"axis_id": duplicate_ids[1], "description": "second canonical identity"},
                ],
            )

        mutations = {
            "derived_consumers": (
                lambda decision: decision["recommended_route"].__setitem__("derived_consumers", duplicate_ids),
                "duplicate_array_value",
            ),
            "identity_fields": (
                lambda decision: decision["recommended_route"].__setitem__("identity_fields", duplicate_ids),
                "duplicate_array_value",
            ),
            "alternatives": (mutate_alternatives, "alternatives_invalid"),
            "grammar_axes": (mutate_axes, "grammar_contour_invalid"),
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            for label, (mutate, expected_reason) in mutations.items():
                with self.subTest(label=label):
                    plan = self._write_required_fixture(root)
                    self._rewrite_fixture_decision_and_ref(plan, mutate)
                    readback = MODULE.plan_status_oracle.machine_authority_decision_readback(plan)
                    result = MODULE.plan_status_oracle.oracle_result(plan)

                    self.assertEqual((readback.state, readback.reason_code), ("invalid", expected_reason))
                    self.assertTrue(readback.route_guard_required)
                    self.assertTrue(result.route_guard_triggered)
                    self.assertEqual(result.route_guard_kind, f"machine_authority_decision_{expected_reason}")

    def test_bounded_grammar_contour_requires_materialized_origin_and_proof_section(self) -> None:
        cases = (
            ("positive", {}, True),
            (
                "missing_origin",
                {
                    "origin_plan": "docs/plans/260814_1010_missing_origin.md",
                    "origin_id": "mad-260814-1010",
                },
                False,
            ),
            ("origin_id_drift", {"origin_id": "mad-260814-1011"}, False),
            ("missing_section", {"proof_matrix_ref": f"{self.PLAN_REL}#Missing proof matrix"}, False),
            (
                "malformed_proof_path",
                {"proof_matrix_ref": "docs/plans/../260814_0900_machine_authority_fixture.md#Acceptance criteria / DoD"},
                False,
            ),
            ("invalid_exit_rule", {"exit_rule": "continue_unbounded"}, False),
        )
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            for label, kwargs, green in cases:
                with self.subTest(label=label):
                    plan = self._write_required_fixture(root)
                    self._rewrite_fixture_decision_and_ref(
                        plan,
                        lambda decision, kwargs=kwargs: self._set_bounded_grammar(decision, **kwargs),
                    )
                    readback = MODULE.plan_status_oracle.machine_authority_decision_readback(plan)
                    result = MODULE.plan_status_oracle.oracle_result(plan)

                    if green:
                        self.assertEqual((readback.state, readback.reason_code), ("frozen_confirmed", "ok"))
                        self.assertFalse(result.route_guard_triggered)
                        self.assertEqual(
                            MODULE.validate_machine_authority_decision(plan, MODULE.read_text(plan)),
                            [],
                        )
                    else:
                        self.assertEqual((readback.state, readback.reason_code), ("invalid", "grammar_contour_invalid"))
                        self.assertTrue(readback.route_guard_required)
                        self.assertTrue(result.route_guard_triggered)
                        self.assertEqual(result.route_guard_kind, "machine_authority_decision_grammar_contour_invalid")

    def test_bounded_grammar_origin_cycle_returns_bounded_invalid_readback(self) -> None:
        rel_a = "docs/plans/260814_1100_cycle_a.md"
        rel_b = "docs/plans/260814_1101_cycle_b.md"
        id_a = "mad-260814-1100"
        id_b = "mad-260814-1101"

        def write_member(root: Path, rel_path: str) -> Path:
            timestamp, sequence, _ = Path(rel_path).stem.split("_", 2)
            decision = _fixture_required_machine_authority_decision(
                plan_rel=rel_path,
                decision_id=f"mad-{timestamp}-{sequence}",
                route_id="fixture_route",
            )
            return _write_fixture_required_machine_authority_plan(
                root,
                plan_rel=rel_path,
                decision=decision,
                write_draft=False,
            )

        def configure_member(plan: Path, rel_path: str, decision_id: str, origin_rel: str, origin_id: str) -> None:
            def mutate(decision: dict[str, object]) -> None:
                decision["decision_id"] = decision_id
                route = decision["recommended_route"]
                assert isinstance(route, dict)
                authority_host = route["authority_host"]
                assert isinstance(authority_host, dict)
                authority_host["path"] = rel_path
                self._set_bounded_grammar(
                    decision,
                    origin_plan=origin_rel,
                    origin_id=origin_id,
                    proof_matrix_ref=f"{rel_path}#Acceptance criteria / DoD",
                )
                confirmation = decision["owner_confirmation"]
                assert isinstance(confirmation, dict)
                confirmation["decision_id"] = decision_id
                confirmation["route_id"] = route["id"]

            self._rewrite_plan_decision(plan, mutate, strip_scope_expansion=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            root.joinpath(".git").mkdir()
            ensure_fixture_git(root)
            plan_a = write_member(root, rel_a)
            plan_b = write_member(root, rel_b)
            configure_member(plan_a, rel_a, id_a, rel_b, id_b)
            configure_member(plan_b, rel_b, id_b, rel_a, id_a)

            readback = MODULE.plan_status_oracle.machine_authority_decision_readback(plan_a)
            result = MODULE.plan_status_oracle.oracle_result(plan_a)

        self.assertEqual((readback.state, readback.reason_code), ("invalid", "grammar_contour_invalid"))
        self.assertTrue(readback.route_guard_required)
        self.assertTrue(result.route_guard_triggered)
        self.assertEqual(result.route_guard_kind, "machine_authority_decision_grammar_contour_invalid")

    def test_post_cutover_missing_carrier_is_a_lint_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = Path(tmpdir) / "docs/plans/260814_0917_machine_authority_missing.md"
            plan.parent.mkdir(parents=True, exist_ok=True)
            plan.write_text(
                "# Plan: missing machine authority\n\n"
                "**Plan type:** dev\n"
                "**Status:** Ready for Coder\n\n"
                "## Meta\n```json\n{\"plan_meta\": {\"cluster\": \"process\"}}\n```\n",
                encoding="utf-8",
            )
            findings = MODULE.validate_machine_authority_decision(plan, MODULE.read_text(plan))

        self.assertEqual(len(findings), 1)
        self.assertIn("missing_required_carrier", findings[0].message)

    def test_initial_architect_draft_can_record_machine_authority_later(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = Path(tmpdir) / "docs/plans/260924_1200_initial_authority_draft.md"
            plan.parent.mkdir(parents=True, exist_ok=True)
            plan.write_text(
                "# Plan: initial authority decision\n\n"
                "**Plan type:** dev\n"
                "**Status:** Architect initial draft\n\n"
                "## Meta\n```json\n{\"plan_meta\": {\"cluster\": \"process\"}}\n```\n",
                encoding="utf-8",
            )
            findings = MODULE.validate_machine_authority_decision(plan, MODULE.read_text(plan))

        self.assertEqual(findings, [])

    def test_strict_reader_ignores_meta_words_in_fenced_evidence_example(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = self._write_required_fixture(Path(tmpdir))
            plan.write_text(
                plan.read_text(encoding="utf-8")
                + "\n## Evidence\n\n```markdown\n## Meta\n```json\n{\"plan_meta\": {\"machine_authority_decision\": \"not-a-carrier\"}}\n```\n```\n",
                encoding="utf-8",
            )
            strict = MODULE.strict_plan_meta_json(MODULE.read_text(plan))
            readback = MODULE.plan_status_oracle.machine_authority_decision_readback(plan)

        self.assertEqual(strict.state, "valid")
        self.assertEqual(readback.state, "frozen_confirmed")

    def test_strict_reader_rejects_real_meta_after_info_string_fence(self) -> None:
        for marker in ("```", "~~~~"):
            for indent in ("", " ", "   "):
                with self.subTest(marker=marker, indent=len(indent)), tempfile.TemporaryDirectory() as tmpdir:
                    plan = self._write_required_fixture(Path(tmpdir))
                    plan.write_text(
                        plan.read_text(encoding="utf-8")
                        + "\n## Evidence\n\n"
                        + f"{indent}{marker}markdown\n"
                        + f"{indent}## Meta\n"
                        + f"{indent}{marker}json\n"
                        + '{"plan_meta": {"machine_authority_decision": "example-only"}}\n'
                        + f"{indent}{marker}\n"
                        + f"\n{indent}## Meta\n{indent}```json\n"
                        + '{"plan_meta": {"cluster": "process"}}\n'
                        + f"{indent}```\n",
                        encoding="utf-8",
                    )
                    strict = MODULE.strict_plan_meta_json(MODULE.read_text(plan))
                    readback = MODULE.plan_status_oracle.machine_authority_decision_readback(plan)
                    result = MODULE.plan_status_oracle.oracle_result(plan)

                    self.assertEqual((strict.state, strict.reason_code), ("invalid", "meta_section_ambiguous"))
                    self.assertEqual((readback.state, readback.reason_code), ("invalid", "meta_section_ambiguous"))
                    self.assertTrue(readback.route_guard_required)
                    self.assertTrue(result.route_guard_triggered)

    def test_strict_reader_applies_commonmark_indent_boundaries(self) -> None:
        for marker in ("```", "~~~~"):
            with self.subTest(marker=marker, case="four_space_opener"), tempfile.TemporaryDirectory() as tmpdir:
                plan = self._write_required_fixture(Path(tmpdir))
                plan.write_text(
                    plan.read_text(encoding="utf-8")
                    + "\n## Evidence\n\n"
                    + f"    {marker}markdown\n"
                    + "\n## Meta\n```json\n"
                    + '{"plan_meta": {"cluster": "process"}}\n'
                    + "```\n",
                    encoding="utf-8",
                )
                strict = MODULE.strict_plan_meta_json(MODULE.read_text(plan))
                readback = MODULE.plan_status_oracle.machine_authority_decision_readback(plan)
                result = MODULE.plan_status_oracle.oracle_result(plan)

                self.assertEqual((strict.state, strict.reason_code), ("invalid", "meta_section_ambiguous"))
                self.assertEqual((readback.state, readback.reason_code), ("invalid", "meta_section_ambiguous"))
                self.assertTrue(readback.route_guard_required)
                self.assertTrue(result.route_guard_triggered)

            with self.subTest(marker=marker, case="four_space_closer_and_meta"), tempfile.TemporaryDirectory() as tmpdir:
                plan = self._write_required_fixture(Path(tmpdir))
                plan.write_text(
                    plan.read_text(encoding="utf-8")
                    + "\n## Evidence\n\n"
                    + f"{marker}markdown\n"
                    + f"    {marker}\n"
                    + "## Meta\n"
                    + f"{marker}\n"
                    + "    ## Meta\n",
                    encoding="utf-8",
                )
                strict = MODULE.strict_plan_meta_json(MODULE.read_text(plan))
                readback = MODULE.plan_status_oracle.machine_authority_decision_readback(plan)

                self.assertEqual((strict.state, strict.reason_code), ("valid", "ok"))
                self.assertEqual(readback.state, "frozen_confirmed")

        with tempfile.TemporaryDirectory() as tmpdir:
            plan = self._write_required_fixture(Path(tmpdir))
            plan.write_text(
                plan.read_text(encoding="utf-8")
                + "\n## Evidence\n\n```markdown`\n"
                + "## Meta\n```json\n"
                + '{"plan_meta": {"cluster": "process"}}\n'
                + "```\n",
                encoding="utf-8",
            )
            strict = MODULE.strict_plan_meta_json(MODULE.read_text(plan))
            readback = MODULE.plan_status_oracle.machine_authority_decision_readback(plan)

        self.assertEqual((strict.state, strict.reason_code), ("invalid", "meta_section_ambiguous"))
        self.assertEqual((readback.state, readback.reason_code), ("invalid", "meta_section_ambiguous"))

        for indent in ("", " ", "   ", "    "):
            with self.subTest(indent=len(indent)), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                plan = self._write_na_fixture(root, "docs/plans/260814_0930_indented_carrier.md")
                text = plan.read_text(encoding="utf-8")
                text = text.replace("## Meta\n```json\n", f"{indent}## Meta\n{indent}```json\n", 1)
                fence_start = text.index("```json\n") + len("```json\n")
                fence_end = text.index("\n```", fence_start)
                text = text[:fence_end] + f"\n{indent}```" + text[fence_end + len("\n```") :]
                plan.write_text(text, encoding="utf-8")
                strict = MODULE.strict_plan_meta_json(MODULE.read_text(plan))
                readback = MODULE.plan_status_oracle.machine_authority_decision_readback(plan)

                if len(indent) <= 3:
                    self.assertEqual((strict.state, strict.reason_code), ("valid", "ok"))
                    self.assertEqual((readback.state, readback.ref_state), ("not_applicable", "valid"))
                else:
                    self.assertEqual(strict.state, "invalid")
                    self.assertTrue(readback.route_guard_required)

    def test_strict_reader_counts_atx_closing_meta_headings(self) -> None:
        for closing in ("#", "##"):
            for indent in ("", " ", "   ", "    "):
                with self.subTest(closing=closing, indent=len(indent)), tempfile.TemporaryDirectory() as tmpdir:
                    plan = self._write_required_fixture(Path(tmpdir))
                    plan.write_text(
                        plan.read_text(encoding="utf-8")
                        + f"\n{indent}## Meta {closing}\n{indent}```json\n"
                        + '{"plan_meta": {"machine_authority_decision": {"example": true}}}\n'
                        + f"{indent}```\n",
                        encoding="utf-8",
                    )
                    strict = MODULE.strict_plan_meta_json(MODULE.read_text(plan))
                    readback = MODULE.plan_status_oracle.machine_authority_decision_readback(plan)
                    result = MODULE.plan_status_oracle.oracle_result(plan)

                    if len(indent) <= 3:
                        self.assertEqual((strict.state, strict.reason_code), ("invalid", "meta_section_ambiguous"))
                        self.assertEqual((readback.state, readback.reason_code), ("invalid", "meta_section_ambiguous"))
                        self.assertTrue(readback.route_guard_required)
                        self.assertTrue(result.route_guard_triggered)
                    else:
                        self.assertEqual((strict.state, strict.reason_code), ("valid", "ok"))
                        self.assertEqual(readback.state, "frozen_confirmed")
                        self.assertFalse(readback.route_guard_required)

    def test_strict_reader_decodes_escaped_plan_meta_root_before_cardinality(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = self._write_required_fixture(root)
            escaped = plan.read_text(encoding="utf-8").replace('"plan_meta"', r'"\u0070lan_meta"', 1)
            plan.write_text(escaped, encoding="utf-8")
            sole = MODULE.strict_plan_meta_json(escaped.splitlines())
            sole_readback = MODULE.plan_status_oracle.machine_authority_decision_readback(plan)

            literal_and_escaped = escaped.replace(
                "\n```\n\n## Plan provenance / session context",
                "\n```\n```json\n{\"plan_meta\": {\"cluster\": \"process\"}}\n```\n\n## Plan provenance / session context",
                1,
            )
            plan.write_text(literal_and_escaped, encoding="utf-8")
            duplicate = MODULE.strict_plan_meta_json(literal_and_escaped.splitlines())
            duplicate_readback = MODULE.plan_status_oracle.machine_authority_decision_readback(plan)

            invalid = root / "docs/plans/260814_0929_escaped_invalid_root.md"
            invalid.parent.mkdir(parents=True, exist_ok=True)
            invalid.write_text(
                "# Plan: escaped invalid root\n\n**Status:** Ready for Coder\n\n"
                "## Meta\n```json\n{\"\\u0070lan_meta\": []}\n```\n",
                encoding="utf-8",
            )
            invalid_strict = MODULE.strict_plan_meta_json(MODULE.read_text(invalid))
            invalid_readback = MODULE.plan_status_oracle.machine_authority_decision_readback(invalid)

        self.assertEqual((sole.state, sole.reason_code), ("valid", "ok"))
        self.assertEqual(sole_readback.state, "frozen_confirmed")
        self.assertEqual((duplicate.state, duplicate.reason_code), ("invalid", "plan_meta_carrier_ambiguous"))
        self.assertEqual((duplicate_readback.state, duplicate_readback.reason_code), ("invalid", "plan_meta_carrier_ambiguous"))
        self.assertEqual((invalid_strict.state, invalid_strict.reason_code), ("invalid", "plan_meta_not_object"))
        self.assertEqual((invalid_readback.state, invalid_readback.reason_code), ("invalid", "plan_meta_not_object"))

    def test_strict_draft_reader_decodes_escaped_code_draft_meta_root_before_cardinality(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan = self._write_required_fixture(root)
            draft = root / self.DRAFT_REL
            escaped = draft.read_text(encoding="utf-8").replace('"code_draft_meta"', r'"\u0063ode_draft_meta"', 1)
            draft.write_text(escaped, encoding="utf-8")
            sole_readback = MODULE.plan_status_oracle.machine_authority_decision_readback(plan)

            draft.write_text(
                escaped
                + "\n```json\n{\"code_draft_meta\": {\"plan\": \""
                + self.PLAN_REL
                + "\"}}\n```\n",
                encoding="utf-8",
            )
            duplicate_readback = MODULE.plan_status_oracle.machine_authority_decision_readback(plan)

        self.assertEqual((sole_readback.state, sole_readback.ref_state), ("frozen_confirmed", "valid"))
        self.assertEqual((duplicate_readback.state, duplicate_readback.reason_code), ("invalid", "code_draft_ref_invalid"))

    def test_rejected_source_lint_accepts_old_name_successor_with_full_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            root.joinpath(".git").mkdir()
            ensure_fixture_git(root)
            source = self._write_required_fixture(root)
            source_text = source.read_text(encoding="utf-8")
            source_status_line = next(
                line for line in source_text.splitlines() if line.startswith("**Status:**")
            )
            strict = MODULE.strict_plan_meta_json(source_text.splitlines())
            self.assertEqual(strict.state, "valid")
            assert strict.plan_meta is not None
            source_meta = json.loads(json.dumps(dict(strict.plan_meta)))
            successor_rel = "docs/plans/260813_1915_old_name_successor.md"
            source_meta["next_plans"] = [successor_rel]
            source_decision = source_meta["machine_authority_decision"]
            assert isinstance(source_decision, dict)
            source_confirmation = source_decision["owner_confirmation"]
            assert isinstance(source_confirmation, dict)
            source_confirmation.update(
                {
                    "state": "rejected",
                    "successor_plan_ref": successor_rel,
                }
            )
            meta_start = source_text.index("```json\n", source_text.index("## Meta")) + len("```json\n")
            meta_end = source_text.index("\n```", meta_start)
            source.write_text(
                source_text[:meta_start]
                + json.dumps({"plan_meta": source_meta}, indent=2)
                + source_text[meta_end:],
                encoding="utf-8",
            )
            source.write_text(
                source.read_text(encoding="utf-8").replace(
                    source_status_line,
                    "**Status:** Superseded",
                    1,
                ),
                encoding="utf-8",
            )

            successor_meta = json.loads(json.dumps(source_meta))
            successor_meta["depends_on"] = [self.PLAN_REL]
            successor_meta["next_plans"] = []
            successor_decision = successor_meta["machine_authority_decision"]
            assert isinstance(successor_decision, dict)
            successor_decision["decision_id"] = "mad-260813-1916"
            route = successor_decision["recommended_route"]
            assert isinstance(route, dict)
            authority_host = route["authority_host"]
            assert isinstance(authority_host, dict)
            authority_host["path"] = successor_rel
            confirmation = successor_decision["owner_confirmation"]
            assert isinstance(confirmation, dict)
            confirmation.clear()
            confirmation.update(
                {
                    "state": "pending",
                    "question_ref": "Q3",
                    "decision_id": "mad-260813-1916",
                    "route_id": route["id"],
                    "carrier_sha256": MODULE.plan_status_oracle.machine_authority_decision_sha256(successor_decision),
                }
            )
            successor = root / successor_rel
            successor.parent.mkdir(parents=True, exist_ok=True)
            successor.write_text(
                "# Plan: old-name rejected-successor fixture\n\n"
                "**Plan type:** dev\n"
                "**Status:** Architect draft\n\n"
                "## Meta\n```json\n"
                + json.dumps({"plan_meta": successor_meta}, indent=2)
                + "\n```\n",
                encoding="utf-8",
            )
            findings = MODULE.validate_machine_authority_decision(source, MODULE.read_text(source))

        self.assertEqual(findings, [])

    def test_duplicate_key_in_sole_meta_fails_without_valid_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = self._write_required_fixture(Path(tmpdir))
            text = plan.read_text(encoding="utf-8")
            self.assertIn('"cluster": "process",', text)
            plan.write_text(
                text.replace('"cluster": "process",', '"cluster": "process",\n    "cluster": "other",', 1),
                encoding="utf-8",
            )
            strict = MODULE.strict_plan_meta_json(MODULE.read_text(plan))
            findings = MODULE.validate_machine_authority_decision(plan, MODULE.read_text(plan))

        self.assertEqual(strict.state, "invalid")
        self.assertEqual(strict.reason_code, "duplicate_json_key")
        self.assertEqual(len(findings), 1)
        self.assertIn("duplicate_json_key", findings[0].message)

    def test_na_and_status_required_binding_matrix_rejects_unknown_or_mixed_variants(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            green = self._write_na_fixture(root, "docs/plans/260814_0921_machine_authority_na.md")
            green_readback = MODULE.plan_status_oracle.machine_authority_decision_readback(green)
            unknown = self._write_na_fixture(
                root,
                "docs/plans/260814_0922_machine_authority_unknown.md",
                decision_extra={"unexpected": "no"},
            )
            unknown_readback = MODULE.plan_status_oracle.machine_authority_decision_readback(unknown)
            mixed = self._write_na_fixture(
                root,
                "docs/plans/260814_0923_machine_authority_mixed.md",
                ref_extra={"decision_id": "mad-260814-0999"},
            )
            mixed_readback = MODULE.plan_status_oracle.machine_authority_decision_readback(mixed)
            missing_required = root / "docs/plans/undated_status_required_no_carrier.md"
            missing_required.parent.mkdir(parents=True, exist_ok=True)
            missing_required.write_text(
                "# Plan: status-required missing-carrier fixture\n\n**Status:** Ready for Coder\n\n"
                "## Meta\n```json\n{\"plan_meta\": {\"cluster\": \"process\"}}\n```\n",
                encoding="utf-8",
            )
            missing_required_readback = MODULE.plan_status_oracle.machine_authority_decision_readback(missing_required)

        self.assertEqual(green_readback.state, "not_applicable")
        self.assertEqual(green_readback.ref_state, "valid")
        self.assertEqual(unknown_readback.state, "invalid")
        self.assertEqual(unknown_readback.reason_code, "unknown_or_missing_keys")
        self.assertEqual(mixed_readback.state, "invalid")
        self.assertEqual(mixed_readback.reason_code, "code_draft_ref_invalid")
        self.assertEqual(
            (missing_required_readback.state, missing_required_readback.reason_code, missing_required_readback.ref_state),
            ("missing", "missing_required_carrier", "missing"),
        )
        self.assertTrue(missing_required_readback.route_guard_required)

    def test_strict_meta_ambiguity_and_pending_confirmation_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            ambiguous = self._write_na_fixture(root, "docs/plans/260814_0924_machine_authority_ambiguous.md")
            ambiguous.write_text(
                ambiguous.read_text(encoding="utf-8")
                + "\n## Meta\n```json\n{\"plan_meta\": {\"cluster\": \"process\"}}\n```\n",
                encoding="utf-8",
            )
            strict = MODULE.strict_plan_meta_json(MODULE.read_text(ambiguous))
            ambiguous_readback = MODULE.plan_status_oracle.machine_authority_decision_readback(ambiguous)
            pending_source = self._write_required_fixture(root)
            pending_source.write_text(
                pending_source.read_text(encoding="utf-8").replace('"state": "confirmed"', '"state": "pending"', 1),
                encoding="utf-8",
            )
            pending_readback = MODULE.plan_status_oracle.machine_authority_decision_readback(pending_source)

        self.assertEqual(strict.state, "invalid")
        self.assertEqual(strict.reason_code, "meta_section_ambiguous")
        self.assertEqual(ambiguous_readback.state, "invalid")
        self.assertEqual(ambiguous_readback.reason_code, "meta_section_ambiguous")
        self.assertEqual(pending_readback.state, "invalid")
        self.assertEqual(pending_readback.reason_code, "owner_confirmation_pending")

    def _write_full_cardinality_fixture(self, root: Path, *, plan_stem: str) -> Path:
        """Return a complete initial-draft fixture before a cardinality mutation."""

        root.mkdir(parents=True, exist_ok=True)
        plan = PlanLintReviewRouteDeterminismTests()._write_fixture(
            root,
            plan_stem=plan_stem,
            plan_status="Architect initial draft",
            target_paths=["docs/fixture.md"],
            review_artifact_lines=[
                f"- Doc review (docs-only): `docs/doc_reviews/{plan_stem}.md`",
            ],
            complete=True,
        )
        write_text_fixture(root, "docs/fixture.md", "# fixture documentation target\n")

        plan_text = plan.read_text(encoding="utf-8")
        strict = MODULE.strict_plan_meta_json(plan_text.splitlines())
        self.assertEqual((strict.state, strict.reason_code), ("valid", "ok"))
        assert strict.plan_meta is not None
        plan_meta = copy.deepcopy(dict(strict.plan_meta))
        plan_meta["queue_activation"] = {
            "state": "n/a",
            "source_ref": "N/A (why=fixture)",
            "reason": "fixture initial-draft admission",
        }
        meta_start = plan_text.index("```json\n", plan_text.index("## Meta")) + len("```json\n")
        meta_end = plan_text.index("\n```", meta_start)
        plan.write_text(
            plan_text[:meta_start]
            + json.dumps({"plan_meta": plan_meta}, ensure_ascii=False, indent=2)
            + plan_text[meta_end:],
            encoding="utf-8",
        )
        return plan

    def test_q10_public_lint_valid_top_level_meta_carrier_cardinality(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            clean = self._write_full_cardinality_fixture(root / "clean", plan_stem="260125_0100_cardinality_clean")
            clean_findings = MODULE.lint_plan(clean)

            cases: list[tuple[str, list[str]]] = [
                (
                    "separate_valid_hosts",
                    [
                        "meta_section_ambiguous: expected at most one individually valid root plan_meta JSON carrier across actual top-level ## Meta hosts.",
                        "Machine-authority admission failed closed: meta_section_ambiguous: expected exactly one top-level ## Meta section, got 2.",
                    ],
                ),
                (
                    "same_host_duplicate_carriers",
                    [
                        "plan_meta_carrier_ambiguous: expected at most one individually valid duplicate-key-safe root plan_meta JSON carrier in each actual top-level ## Meta host.",
                        "Machine-authority admission failed closed: plan_meta_carrier_ambiguous: expected exactly one root plan_meta JSON fence in top-level ## Meta, got 2.",
                    ],
                ),
                (
                    "zero_actual_meta",
                    ["Missing required plan_meta JSON block (```json ... plan_meta ... ```)."],
                ),
            ]
            for label, expected_messages in cases:
                with self.subTest(label=label):
                    plan = self._write_full_cardinality_fixture(root / label, plan_stem=f"260125_0100_{label}")
                    plan_text = plan.read_text(encoding="utf-8")
                    meta_heading = plan_text.index("## Meta")
                    meta_start = plan_text.index("```json\n", meta_heading) + len("```json\n")
                    meta_end = plan_text.index("\n```", meta_start)

                    if label == "separate_valid_hosts":
                        first_host_end = meta_end + len("\n```")
                        plan_text = plan_text[:first_host_end] + "\n\n" + plan_text[meta_heading:first_host_end] + plan_text[first_host_end:]
                    elif label == "same_host_duplicate_carriers":
                        plan_text = (
                            plan_text[:meta_end]
                            + "\n```\n```json\n"
                            + plan_text[meta_start:meta_end]
                            + plan_text[meta_end:]
                        )
                    else:
                        first_host_end = meta_end + len("\n```")
                        plan_text = plan_text[:meta_heading] + plan_text[first_host_end:]
                    plan.write_text(plan_text, encoding="utf-8")

                    findings = MODULE.lint_plan(plan)
                    self.assertEqual(
                        [(finding.severity, finding.message) for finding in findings],
                        [("ERROR", message) for message in expected_messages],
                    )

        self.assertEqual(clean_findings, [])

    def test_status_required_meta_ambiguity_preserves_decoded_candidate_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            voluntary = self._write_na_fixture(root, "docs/plans/260813_1915_voluntary_ambiguous.md")
            voluntary.write_text(
                voluntary.read_text(encoding="utf-8")
                + "\n## Meta\n```json\n{\"plan_meta\": {\"cluster\": \"process\"}}\n```\n",
                encoding="utf-8",
            )
            voluntary_strict = MODULE.strict_plan_meta_json(MODULE.read_text(voluntary))
            voluntary_readback = MODULE.plan_status_oracle.machine_authority_decision_readback(voluntary)
            voluntary_result = MODULE.plan_status_oracle.oracle_result(voluntary)

            duplicate_carrier = self._write_na_fixture(root, "docs/plans/260813_1915_duplicate_carrier.md")
            duplicate_carrier.write_text(
                duplicate_carrier.read_text(encoding="utf-8").replace(
                    "\n```\n",
                    "\n```\n```json\n{\"plan_meta\": {\"cluster\": \"process\"}}\n```\n",
                    1,
                ),
                encoding="utf-8",
            )
            duplicate_carrier_strict = MODULE.strict_plan_meta_json(MODULE.read_text(duplicate_carrier))
            duplicate_carrier_readback = MODULE.plan_status_oracle.machine_authority_decision_readback(duplicate_carrier)
            duplicate_carrier_result = MODULE.plan_status_oracle.oracle_result(duplicate_carrier)

            carrier_free = root / "docs/plans/undated_ambiguous_required.md"
            carrier_free.parent.mkdir(parents=True, exist_ok=True)
            carrier_free.write_text(
                "# Plan: ambiguous status-required fixture\n\n**Status:** Ready for Coder\n\n"
                "## Meta\n```json\n{\"plan_meta\": {\"cluster\": \"process\"}}\n```\n\n"
                "## Meta\n```json\n{\"not_plan_meta\": {\"machine_authority_decision\": \"decoy\"}}\n```\n",
                encoding="utf-8",
            )
            carrier_free_strict = MODULE.strict_plan_meta_json(MODULE.read_text(carrier_free))
            carrier_free_readback = MODULE.plan_status_oracle.machine_authority_decision_readback(carrier_free)
            carrier_free_result = MODULE.plan_status_oracle.oracle_result(carrier_free)

            malformed_cases = {
                "malformed": "```json\n{\"plan_meta\": {\"machine_authority_decision\": }\n```",
                "duplicate_key": (
                    "```json\n{\"plan_meta\": {\"machine_authority_decision\": {}, "
                    "\"machine_authority_decision\": {}}}\n```"
                ),
                "unterminated": "```json\n{\"plan_meta\": {\"machine_authority_decision\": {}}\n````",
            }
            malformed_results: list[tuple[object, object, object, tuple[object, ...]]] = []
            for label, first_section in malformed_cases.items():
                malformed = root / f"docs/plans/260813_1915_{label}_ambiguous.md"
                malformed.write_text(
                    "# Plan: malformed voluntary carrier fixture\n\n**Status:** Ready for Coder\n\n"
                    "## Meta\n"
                    + first_section
                    + "\n\n## Meta\n```json\n{\"plan_meta\": {\"cluster\": \"process\"}}\n```\n",
                    encoding="utf-8",
                )
                malformed_strict = MODULE.strict_plan_meta_json(MODULE.read_text(malformed))
                malformed_readback = MODULE.plan_status_oracle.machine_authority_decision_readback(malformed)
                malformed_result = MODULE.plan_status_oracle.oracle_result(malformed)
                malformed_findings = MODULE.validate_machine_authority_decision(malformed, MODULE.read_text(malformed))
                malformed_results.append(
                    (malformed_strict, malformed_readback, malformed_result, malformed_findings)
                )

            ordered_marker_cases = {
                "marker_before_malformed_sibling": (
                    '{"plan_meta": {"machine_authority_decision": {}, "broken": }}'
                ),
                "malformed_sibling_before_marker": (
                    '{"plan_meta": {"broken":, "machine_authority_decision": {}}}'
                ),
                "escaped_keys_after_malformed_sibling": (
                    '{"\\u0070lan_meta": {"broken":, '
                    '"\\u006dachine_authority_decision": {}}}'
                ),
                "unterminated_literal_before_marker": (
                    '{"plan_meta": {"broken": tru, "machine_authority_decision": {}}}'
                ),
            }
            ordered_marker_results: list[tuple[object, object, object, tuple[object, ...]]] = []
            for label, raw in ordered_marker_cases.items():
                self.assertTrue(
                    MODULE.plan_status_oracle._machine_authority_raw_candidate_marker_seen(raw),
                    label,
                )
                ordered = root / f"docs/plans/260813_1915_{label}_ambiguous.md"
                ordered.write_text(
                    "# Plan: order-sensitive malformed voluntary carrier fixture\n\n"
                    "**Status:** Ready for Coder\n\n"
                    "## Meta\n```json\n"
                    + raw
                    + "\n```\n\n## Meta\n```json\n"
                    '{"plan_meta": {"cluster": "process"}}\n```\n',
                    encoding="utf-8",
                )
                ordered_text = MODULE.read_text(ordered)
                ordered_marker_results.append(
                    (
                        MODULE.strict_plan_meta_json(ordered_text),
                        MODULE.plan_status_oracle.machine_authority_decision_readback(ordered),
                        MODULE.plan_status_oracle.oracle_result(ordered),
                        MODULE.validate_machine_authority_decision(ordered, ordered_text),
                    )
                )

            unrelated_results: list[tuple[object, object, object]] = []
            unrelated_cases = {
                "malformed_unrelated": "```json\n{\"not_plan_meta\": }\n```",
                "unterminated_unrelated": "```json\n{\"not_plan_meta\": {\n````",
                "nested_decision_decoy_after_malformed_sibling": (
                    "```json\n{\"plan_meta\": {\"nested\": "
                    "{\"machine_authority_decision\": {}}, \"broken\": }}\n```"
                ),
            }
            for label, first_section in unrelated_cases.items():
                unrelated = root / f"docs/plans/260813_1915_{label}_ambiguous.md"
                unrelated.write_text(
                    "# Plan: unrelated malformed status-required fixture\n\n**Status:** Ready for Coder\n\n"
                    "## Meta\n"
                    + first_section
                    + "\n\n## Meta\n```json\n{\"plan_meta\": {\"cluster\": \"process\"}}\n```\n",
                    encoding="utf-8",
                )
                unrelated_results.append(
                    (
                        MODULE.strict_plan_meta_json(MODULE.read_text(unrelated)),
                        MODULE.plan_status_oracle.machine_authority_decision_readback(unrelated),
                        MODULE.plan_status_oracle.oracle_result(unrelated),
                    )
                )

        for strict, readback, result, expected_reason in (
            (voluntary_strict, voluntary_readback, voluntary_result, "meta_section_ambiguous"),
            (duplicate_carrier_strict, duplicate_carrier_readback, duplicate_carrier_result, "plan_meta_carrier_ambiguous"),
        ):
            self.assertEqual((strict.state, strict.reason_code), ("invalid", expected_reason))
            self.assertTrue(strict.has_machine_authority_marker)
            self.assertEqual((readback.state, readback.reason_code), ("invalid", expected_reason))
            self.assertEqual(readback.ref_state, "invalid")
            self.assertTrue(readback.route_guard_required)
            self.assertTrue(result.route_guard_triggered)
            self.assertEqual(result.route_guard_kind, f"machine_authority_decision_{expected_reason}")

        self.assertEqual((carrier_free_strict.state, carrier_free_strict.reason_code), ("invalid", "meta_section_ambiguous"))
        self.assertFalse(carrier_free_strict.has_machine_authority_marker)
        self.assertEqual((carrier_free_readback.state, carrier_free_readback.reason_code), ("invalid", "meta_section_ambiguous"))
        self.assertEqual(carrier_free_readback.ref_state, "invalid")
        self.assertTrue(carrier_free_readback.route_guard_required)
        self.assertTrue(carrier_free_result.route_guard_triggered)
        self.assertEqual(carrier_free_result.route_guard_kind, "machine_authority_decision_meta_section_ambiguous")

        for strict, readback, result, findings in malformed_results:
            self.assertEqual((strict.state, strict.reason_code), ("invalid", "meta_section_ambiguous"))
            self.assertTrue(strict.has_machine_authority_marker)
            self.assertEqual((readback.state, readback.reason_code), ("invalid", "meta_section_ambiguous"))
            self.assertEqual(readback.ref_state, "invalid")
            self.assertTrue(readback.route_guard_required)
            self.assertTrue(result.route_guard_triggered)
            self.assertEqual(result.route_guard_kind, "machine_authority_decision_meta_section_ambiguous")
            self.assertTrue(any("meta_section_ambiguous" in finding.message for finding in findings))

        for strict, readback, result, findings in ordered_marker_results:
            self.assertEqual((strict.state, strict.reason_code), ("invalid", "meta_section_ambiguous"))
            self.assertTrue(strict.has_machine_authority_marker)
            self.assertEqual((readback.state, readback.reason_code), ("invalid", "meta_section_ambiguous"))
            self.assertEqual(readback.ref_state, "invalid")
            self.assertTrue(readback.route_guard_required)
            self.assertTrue(result.route_guard_triggered)
            self.assertEqual(result.route_guard_kind, "machine_authority_decision_meta_section_ambiguous")
            self.assertTrue(any("meta_section_ambiguous" in finding.message for finding in findings))

        for strict, readback, result in unrelated_results:
            self.assertEqual((strict.state, strict.reason_code), ("invalid", "meta_section_ambiguous"))
            self.assertFalse(strict.has_machine_authority_marker)
            self.assertEqual((readback.state, readback.reason_code), ("invalid", "meta_section_ambiguous"))
            self.assertEqual(readback.ref_state, "invalid")
            self.assertTrue(readback.route_guard_required)
            self.assertTrue(result.route_guard_triggered)
            self.assertEqual(result.route_guard_kind, "machine_authority_decision_meta_section_ambiguous")

    def test_machine_authority_rejects_surrounding_whitespace_before_semantic_comparison(self) -> None:
        mutations = {
            "decision_id": lambda decision: decision.__setitem__("decision_id", " mad-260814-0900 "),
            "route_id": lambda decision: decision["recommended_route"].__setitem__("id", " meta_json_v1 "),
            "authority_host_path": lambda decision: decision["recommended_route"]["authority_host"].__setitem__(
                "path", f" {self.PLAN_REL} "
            ),
            "confirmation_question_ref": lambda decision: decision["owner_confirmation"].__setitem__("question_ref", " Q5 "),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmpdir:
                plan = self._write_required_fixture(Path(tmpdir))
                self._rewrite_fixture_decision_and_ref(plan, mutate)
                readback = MODULE.plan_status_oracle.machine_authority_decision_readback(plan)
                result = MODULE.plan_status_oracle.oracle_result(plan)
                findings = MODULE.validate_machine_authority_decision(plan, MODULE.read_text(plan))

                self.assertEqual((readback.state, readback.reason_code), ("invalid", "invalid_string"))
                self.assertTrue(readback.route_guard_required)
                self.assertTrue(result.route_guard_triggered)
                self.assertEqual(result.route_guard_kind, "machine_authority_decision_invalid_string")
                self.assertEqual(len(findings), 1)
                self.assertIn("invalid_string", findings[0].message)


class CurrentReviewProofPreflightTests(unittest.TestCase):
    """Direct contract matrix for the one current-review proof authority."""

    PLAN_REL = "docs/plans/260619_0242_current_proof_fixture.md"
    DRAFT_REL = "docs/code_drafts/260619_0242_current_proof_fixture__code_draft.md"
    REVIEW_REL = "docs/code_reviews/260619_0242_current_proof_fixture.md"
    SUPPORT_REL = "docs/code_reviews/assets/260619_0242_current_proof_fixture/full_payload.json"
    TARGET_REL = "scripts/current_proof_fixture.py"

    def _write_plan(self, root: Path, compact_payload: dict[str, object]) -> Path:
        return write_text_fixture(
            root,
            self.PLAN_REL,
            dedent(
                f"""\
                # Current proof fixture

                **Status:** In progress

                ## Code draft

                - Draft: `{self.DRAFT_REL}`

                ## Review artifacts

                - Code review (primary): `{self.REVIEW_REL}`

                ## Evidence

                - reviewer_code_risk lane-run artifact:
                  ```json
                  {json.dumps(compact_payload, ensure_ascii=False, indent=2, sort_keys=True)}
                  ```
                """
            ),
        )

    def _write_review(self, root: Path, target: str, *, prose: str = "") -> Path:
        return write_text_fixture(
            root,
            self.REVIEW_REL,
            "# Current proof review\n\n"
            f"**Target:** {target}\n"
            "**Status:** ✅ OK\n\n"
            f"{prose}",
        )

    def _fixture(self, root: Path) -> tuple[Path, dict[str, object], dict[str, object], str]:
        (root / ".git").mkdir(parents=True, exist_ok=True)
        ensure_fixture_git(root)
        write_text_fixture(root, self.TARGET_REL, "print('current proof')\n")
        write_text_fixture(
            root,
            self.DRAFT_REL,
            "# Code draft\n\n```json\n"
            + json.dumps(
                {"code_draft_meta": {"targets": [{"path": self.TARGET_REL, "kind": "py"}]}},
                sort_keys=True,
            )
            + "\n```\n",
        )
        seed_compact = {
            "lane_id": "reviewer_code_risk",
            "run_id": "reviewer_code_risk:fixture:20260619T024200Z",
            "target_snapshot": {"bundle_sha256": "0" * 64, "target": "BUNDLE=current"},
            "lane_status": "no_findings",
            "findings": [],
            "current": True,
        }
        plan_path = self._write_plan(root, seed_compact)
        snapshot = build_current_bundle_snapshot(plan_path, project_root=root)
        support_payload: dict[str, object] = {
            "lane_id": "reviewer_code_risk",
            "run_id": seed_compact["run_id"],
            "target_snapshot": snapshot,
            "lane_status": "no_findings",
            "findings": [],
            "current": True,
        }
        support_bytes = json.dumps(support_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        write_text_fixture(root, self.SUPPORT_REL, support_bytes.decode("utf-8"))
        compact_payload: dict[str, object] = {
            "lane_id": "reviewer_code_risk",
            "run_id": seed_compact["run_id"],
            "target_snapshot": snapshot["target_snapshot"],
            "lane_status": "no_findings",
            "findings": [],
            "current": True,
            "full_payload_ref": self.SUPPORT_REL,
            "full_payload_sha256": hashlib.sha256(support_bytes).hexdigest(),
        }
        plan_path = self._write_plan(root, compact_payload)
        self._write_review(root, str(snapshot["target"]))
        return plan_path, compact_payload, support_payload, str(snapshot["target"])

    def _rewrite_support_and_compact(
        self,
        root: Path,
        compact_payload: dict[str, object],
        support_payload: dict[str, object],
    ) -> Path:
        support_bytes = json.dumps(support_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        write_text_fixture(root, self.SUPPORT_REL, support_bytes.decode("utf-8"))
        compact_payload["full_payload_sha256"] = hashlib.sha256(support_bytes).hexdigest()
        return self._write_plan(root, compact_payload)

    def test_exact_four_layer_current_proof_is_green_and_unrelated_prose_is_not_a_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "repo"
            plan_path, compact, _support, target = self._fixture(root)

            green = MODULE.preflight_current_review_proof(plan_path, project_root=root)
            self.assertEqual((green.state, green.reason_code, green.target), ("current_green", None, target))

            compact["target_snapshot"] = "BUNDLE=staged"
            plan_path = self._write_plan(root, compact)
            self._write_review(root, "BUNDLE=staged")
            support_claim = MODULE.preflight_current_review_proof(plan_path, project_root=root)
            self.assertEqual(
                (support_claim.state, support_claim.reason_code),
                ("blocked", "current_review_proof_target_invalid"),
            )

            compact.pop("full_payload_ref")
            compact.pop("full_payload_sha256")
            plan_path = self._write_plan(root, compact)
            self._write_review(root, "BUNDLE=staged", prose="Narrative says BUNDLE=current with a random SHA only.\n")
            not_current = MODULE.preflight_current_review_proof(plan_path, project_root=root)

        self.assertEqual((not_current.state, not_current.reason_code), ("not_current", None))

    def test_current_proof_rejects_header_and_compact_aliases_before_any_fallback(self) -> None:
        header_cases = {
            "reordered": "bundle_sha256=" + "0" * 64 + " BUNDLE=current",
            "prefix": "prefix BUNDLE=current bundle_sha256=" + "0" * 64,
            "suffix": "BUNDLE=current bundle_sha256=" + "0" * 64 + " suffix",
        }
        for label, target in header_cases.items():
            with self.subTest(layer="header", label=label), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir) / "repo"
                plan_path, _compact, _support, _canonical = self._fixture(root)
                self._write_review(root, target)
                result = MODULE.preflight_current_review_proof(plan_path, project_root=root)
                self.assertEqual((result.state, result.reason_code), ("blocked", "current_review_proof_target_invalid"))

        compact_cases: dict[str, object] = {
            "reordered": {
                "bundle_sha256": "0" * 64,
                "target": "bundle_sha256=" + "0" * 64 + " BUNDLE=current",
            },
            "bare_string": "BUNDLE=current",
            "bare_object": {"target": "BUNDLE=current"},
        }
        for label, compact_target_snapshot in compact_cases.items():
            with self.subTest(layer="compact", label=label), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir) / "repo"
                _plan_path, compact, _support, _canonical = self._fixture(root)
                compact["target_snapshot"] = compact_target_snapshot
                plan_path = self._write_plan(root, compact)
                selection = MODULE.select_plan_risk_lane_snapshot(plan_path)
                selector_diagnostics = MODULE.preflight_selected_risk_lane_support(
                    plan_path,
                    selection,
                    project_root=root,
                )
                result = MODULE.preflight_current_review_proof(plan_path, project_root=root)

            self.assertEqual(selector_diagnostics[0].code, "current_review_proof_compact_snapshot_invalid")
            self.assertEqual((result.state, result.reason_code), ("blocked", "current_review_proof_compact_snapshot_invalid"))

    def test_selected_current_support_preflight_matches_fresh_producer_failure_codes(self) -> None:
        cases = {
            "target_drift": (
                lambda root: write_text_fixture(root, self.TARGET_REL, "print('current proof drift')\n"),
                "current_review_proof_producer_mismatch",
            ),
            "target_removed": (
                lambda root: (root / self.TARGET_REL).unlink(),
                "current_review_proof_producer_or_support_unavailable",
            ),
        }
        for label, (mutate_target, expected_code) in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir) / "repo"
                plan_path, _compact, _support, _target = self._fixture(root)
                selection = MODULE.select_plan_risk_lane_snapshot(plan_path)
                self.assertEqual(
                    MODULE.preflight_selected_risk_lane_support(
                        plan_path,
                        selection,
                        project_root=root,
                    ),
                    (),
                )

                mutate_target(root)
                selector_diagnostics = MODULE.preflight_selected_risk_lane_support(
                    plan_path,
                    selection,
                    project_root=root,
                )
                current_proof = MODULE.preflight_current_review_proof(plan_path, project_root=root)

                self.assertEqual([diagnostic.code for diagnostic in selector_diagnostics], [expected_code])
                self.assertEqual((current_proof.state, current_proof.reason_code), ("blocked", expected_code))

    def test_current_proof_rejects_missing_support_invalid_full_snapshot_and_producer_red(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "repo"
            _plan_path, compact, _support, _canonical = self._fixture(root)
            compact.pop("full_payload_ref")
            compact.pop("full_payload_sha256")
            plan_path = self._write_plan(root, compact)
            missing_support = MODULE.preflight_current_review_proof(plan_path, project_root=root)
            self.assertEqual((missing_support.state, missing_support.reason_code), ("blocked", "current_review_proof_support_invalid"))

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "repo"
            _plan_path, compact, support, _canonical = self._fixture(root)
            full_snapshot = dict(support["target_snapshot"])
            full_snapshot["target_snapshot"] = {"bundle_sha256": "0" * 64, "target": "BUNDLE=current"}
            support["target_snapshot"] = full_snapshot
            plan_path = self._rewrite_support_and_compact(root, compact, support)
            invalid_full = MODULE.preflight_current_review_proof(plan_path, project_root=root)
            self.assertEqual((invalid_full.state, invalid_full.reason_code), ("blocked", "current_review_proof_support_invalid"))

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "repo"
            plan_path, _compact, _support, _canonical = self._fixture(root)
            (root / self.TARGET_REL).unlink()
            producer_red = MODULE.preflight_current_review_proof(plan_path, project_root=root)

        self.assertEqual(
            (producer_red.state, producer_red.reason_code),
            ("blocked", "current_review_proof_producer_or_support_unavailable"),
        )

    def test_terminal_immutable_review_is_not_reclassified_as_fresh_current_proof(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "repo"
            plan_path, _compact, _support, _canonical = self._fixture(root)
            plan_path.write_text(
                plan_path.read_text(encoding="utf-8").replace(
                    "**Status:** In progress", "**Status:** Done", 1
                ),
                encoding="utf-8",
            )
            selection = MODULE.select_plan_risk_lane_snapshot(plan_path)
            write_text_fixture(root, self.TARGET_REL, "print('terminal historical drift')\n")
            selector_diagnostics = MODULE.preflight_selected_risk_lane_support(
                plan_path,
                selection,
                project_root=root,
            )

            result = MODULE.preflight_current_review_proof(plan_path, project_root=root)

        self.assertEqual(selector_diagnostics, ())
        self.assertEqual((result.state, result.reason_code), ("not_current", None))


class ReviewArtifactRefExtractionTests(unittest.TestCase):
    def test_literal_boundaries_preserve_valid_refs_only(self) -> None:
        lines = [
            "- Code: `docs/code_reviews/live.md`",
            "- Docs: `docs/doc_reviews/live.md`",
            "- Anchor: (docs/code_reviews/anchored.md#B1)",
            "- Delimited: docs/doc_reviews/delimited.md;",
            "- Invalid image: `docs/code_reviews/live.md.png`",
            "- Invalid extension: `docs/doc_reviews/live.mdx`",
            "- Invalid suffix: `docs/code_reviews/live.md@evil`",
            "- Invalid query: `docs/code_reviews/live.md?download=1`",
            "- Foreign path: `/tmp/docs/code_reviews/live.md`",
            "- Embedded path: `xdocs/code_reviews/live.md`",
            "- External colon: docs/code_reviews/colon.md: evidence",
            "- External comma: docs/code_reviews/comma.md, evidence",
            "- External pipe: docs/code_reviews/pipe.md | evidence",
            "- External parenthesis: (docs/code_reviews/paren.md)",
            "- Backticked anchor: ``docs/code_reviews/backticked-anchor.md#B1``",
            "- Anchored colon: docs/code_reviews/anchored-colon.md#B1: evidence",
        ]

        self.assertEqual(
            MODULE.extract_review_artifact_refs(lines),
            [
                (1, "docs/code_reviews/live.md"),
                (2, "docs/doc_reviews/live.md"),
                (3, "docs/code_reviews/anchored.md"),
                (4, "docs/doc_reviews/delimited.md"),
                (11, "docs/code_reviews/colon.md"),
                (12, "docs/code_reviews/comma.md"),
                (13, "docs/code_reviews/pipe.md"),
                (14, "docs/code_reviews/paren.md"),
                (15, "docs/code_reviews/backticked-anchor.md"),
                (16, "docs/code_reviews/anchored-colon.md"),
            ],
        )

    def test_backticked_punctuation_is_preserved_as_raw_literal(self) -> None:
        malformed_refs = (
            "docs/code_reviews/live.md:evil",
            "docs/code_reviews/live.md;evil",
            "docs/code_reviews/live.md,evil",
            "docs/code_reviews/live.md|evil",
            "docs/code_reviews/live.md)evil",
            "docs/code_reviews/live.md#B1:evil",
        )
        for code_delimiter in ("`", "``"):
            for malformed_ref in malformed_refs:
                with self.subTest(code_delimiter=code_delimiter, malformed_ref=malformed_ref):
                    literal = f"{code_delimiter}{malformed_ref}{code_delimiter}"
                    self.assertEqual(MODULE.extract_review_artifact_path_tokens(literal), [malformed_ref])
                    self.assertEqual(MODULE.extract_review_artifact_refs([f"- Code: {literal}"]), [])
                    self.assertFalse(MODULE.is_review_artifact_path_eligible(malformed_ref))

    def test_unbackticked_anchor_fragments_are_preserved_as_raw_literals(self) -> None:
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
        for malformed_ref in malformed_refs:
            with self.subTest(malformed_ref=malformed_ref):
                self.assertEqual(MODULE.extract_review_artifact_path_tokens(malformed_ref), [malformed_ref])
                self.assertEqual(MODULE.extract_review_artifact_refs([f"- Code: {malformed_ref}"]), [])
                self.assertFalse(MODULE.is_review_artifact_path_eligible(malformed_ref))

        valid_ref = "docs/code_reviews/live.md#B1"
        self.assertEqual(MODULE.extract_review_artifact_path_tokens(valid_ref), [valid_ref])
        self.assertEqual(MODULE.extract_review_artifact_refs([f"- Code: {valid_ref}"]), [(1, "docs/code_reviews/live.md")])

    def test_live_raw_presence_preserves_malformed_literals(self) -> None:
        lines = [
            "## Review artifacts",
            "- Code review (primary): `docs/code_reviews/live.md@evil`",
            "- Doc review (docs-only): `docs/doc_reviews/live.md?download=1`",
            "- Code review (primary): `/tmp/docs/code_reviews/live.md`",
            "- Doc review (docs-only): `xdocs/doc_reviews/live.md`",
            "- Historical review: `docs/code_reviews/history.md`",
        ]

        self.assertEqual(MODULE.extract_live_review_artifact_refs(lines), [])
        self.assertEqual(
            MODULE.extract_live_review_artifact_raw_rows(lines),
            [
                (2, ("docs/code_reviews/live.md@evil",)),
                (3, ("docs/doc_reviews/live.md?download=1",)),
                (4, ("/tmp/docs/code_reviews/live.md",)),
                (5, ("xdocs/doc_reviews/live.md",)),
            ],
        )
        self.assertEqual(
            MODULE.extract_live_review_artifact_raw_refs(lines),
            [
                (2, "docs/code_reviews/live.md@evil"),
                (3, "docs/doc_reviews/live.md?download=1"),
                (4, "/tmp/docs/code_reviews/live.md"),
                (5, "xdocs/doc_reviews/live.md"),
            ],
        )
        self.assertEqual(
            MODULE.extract_live_review_artifact_raw_rows(
                [
                    "## Review artifacts",
                    "- Code review (primary): `N/A (why=fixture)`",
                ]
            ),
            [(2, ())],
        )

    def test_backticked_punctuation_preserves_live_raw_presence(self) -> None:
        malformed_refs = (
            "docs/code_reviews/live.md:evil",
            "docs/code_reviews/live.md;evil",
            "docs/code_reviews/live.md,evil",
            "docs/code_reviews/live.md|evil",
            "docs/code_reviews/live.md)evil",
        )
        lines = [
            "## Review artifacts",
            *(f"- Code review (primary): `{malformed_ref}`" for malformed_ref in malformed_refs),
        ]

        self.assertEqual(MODULE.extract_live_review_artifact_refs(lines), [])
        self.assertEqual(
            MODULE.extract_live_review_artifact_raw_refs(lines),
            [(line_no, malformed_ref) for line_no, malformed_ref in enumerate(malformed_refs, start=2)],
        )

    def test_unbackticked_malformed_anchor_preserves_live_raw_presence(self) -> None:
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
        lines = [
            "## Review artifacts",
            *(f"- Code review (primary): {malformed_ref}" for malformed_ref in malformed_refs),
        ]

        self.assertEqual(MODULE.extract_live_review_artifact_refs(lines), [])
        self.assertEqual(
            MODULE.extract_live_review_artifact_raw_refs(lines),
            [(line_no, malformed_ref) for line_no, malformed_ref in enumerate(malformed_refs, start=2)],
        )

    def test_eligible_path_helper_keeps_legacy_root_explicit(self) -> None:
        self.assertTrue(MODULE.is_review_artifact_path_eligible("docs/code_reviews/live.md"))
        self.assertTrue(MODULE.is_review_artifact_path_eligible("docs/code_reviews/live.md#B1"))
        self.assertFalse(MODULE.is_review_artifact_path_eligible("docs/code_reviews/live.md.png"))
        self.assertFalse(MODULE.is_review_artifact_path_eligible("docs/code_reviews/live.md@evil"))
        self.assertFalse(MODULE.is_review_artifact_path_eligible("docs/code_reviews/live.md?download=1"))
        self.assertFalse(MODULE.is_review_artifact_path_eligible("docs/code_reviews/live.md:evil"))
        self.assertFalse(MODULE.is_review_artifact_path_eligible("docs/code_reviews/live.md;evil"))
        self.assertFalse(MODULE.is_review_artifact_path_eligible("docs/code_reviews/live.md,evil"))
        self.assertFalse(MODULE.is_review_artifact_path_eligible("docs/code_reviews/live.md|evil"))
        self.assertFalse(MODULE.is_review_artifact_path_eligible("docs/code_reviews/live.md)evil"))
        self.assertFalse(MODULE.is_review_artifact_path_eligible("docs/code_reviews/live.md#B1:evil"))
        self.assertFalse(MODULE.is_review_artifact_path_eligible("/tmp/docs/code_reviews/live.md"))
        self.assertFalse(MODULE.is_review_artifact_path_eligible("xdocs/code_reviews/live.md"))
        self.assertFalse(MODULE.is_review_artifact_path_eligible("docs/code_reviews/assets/live.md"))
        self.assertFalse(MODULE.is_review_artifact_path_eligible("docs/reviews/legacy.md"))
        self.assertTrue(
            MODULE.is_review_artifact_path_eligible(
                "docs/reviews/legacy.md",
                allow_legacy_root=True,
            )
        )

    def test_done_guard_rejects_invalid_canonical_prefix_despite_green_decoy(self) -> None:
        review_rel = "docs/code_reviews/live.md"
        for malformed_ref in (
            "docs/code_reviews/live.md.png",
            "docs/code_reviews/live.md@evil",
            "docs/code_reviews/live.md?download=1",
            "docs/code_reviews/live.md:evil",
            "docs/code_reviews/live.md;evil",
            "docs/code_reviews/live.md,evil",
            "docs/code_reviews/live.md|evil",
            "docs/code_reviews/live.md)evil",
            "docs/code_reviews/live.md#B1:evil",
            "/tmp/docs/code_reviews/live.md",
            "xdocs/code_reviews/live.md",
        ):
            with self.subTest(malformed_ref=malformed_ref), tempfile.TemporaryDirectory() as tmpdir:
                lines = [
                    "# Plan: exact review boundary fixture",
                    "",
                    "**Status:** Done",
                    "",
                    "**Plan type:** dev",
                    "",
                    "## Review artifacts",
                    f"- Code review (primary): `{malformed_ref}`",
                ]
                root = Path(tmpdir)
                review_path = root / review_rel
                review_path.parent.mkdir(parents=True, exist_ok=True)
                review_path.write_text("# Review\n\n**Status:** ✅ OK\n", encoding="utf-8")

                findings = MODULE.validate_done_executable_review_artifact_guard(
                    Path("docs/plans/260828_1032_exact_review_boundary_fixture.md"),
                    lines,
                    None,
                    status_value="Done",
                    plan_type="dev",
                    plan_repo_root=root,
                )

            self.assertEqual(len(findings), 1)
            self.assertIn("must carry one live review artifact", findings[0].message)

    def test_done_guard_rejects_unbackticked_malformed_anchor_despite_green_decoy(self) -> None:
        review_rel = "docs/code_reviews/live.md"
        for malformed_ref in (
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
        ):
            with self.subTest(malformed_ref=malformed_ref), tempfile.TemporaryDirectory() as tmpdir:
                lines = [
                    "# Plan: exact review boundary fixture",
                    "",
                    "**Status:** Done",
                    "",
                    "**Plan type:** dev",
                    "",
                    "## Review artifacts",
                    f"- Code review (primary): {malformed_ref}",
                ]
                root = Path(tmpdir)
                review_path = root / review_rel
                review_path.parent.mkdir(parents=True, exist_ok=True)
                review_path.write_text("# Review\n\n**Status:** ✅ OK\n", encoding="utf-8")

                findings = MODULE.validate_done_executable_review_artifact_guard(
                    Path("docs/plans/260828_1032_exact_review_boundary_fixture.md"),
                    lines,
                    None,
                    status_value="Done",
                    plan_type="dev",
                    plan_repo_root=root,
                )

            self.assertEqual(len(findings), 1)
            self.assertIn("must carry one live review artifact", findings[0].message)


if __name__ == "__main__":
    unittest.main()

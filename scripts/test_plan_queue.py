#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import io
import json
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from textwrap import dedent
from unittest import mock

try:
    from test_contract_authority_support import AuthorityFixture, commit_all, write as write_fixture_file
    from test_support.process_contract_fixtures import inside_git_work_tree
except ModuleNotFoundError:
    from scripts.test_contract_authority_support import AuthorityFixture, commit_all, write as write_fixture_file
    from scripts.test_support.process_contract_fixtures import inside_git_work_tree


MODULE_PATH = Path(__file__).with_name("plan_queue.py")
REPO_ROOT = MODULE_PATH.resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("plan_queue", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
REAL_PLAN_LINT_VOCAB_LOADER = MODULE.plan_lint.load_plan_vocab

METRICS_MODULE_PATH = Path(__file__).with_name("planqueue_metrics.py")
METRICS_SPEC = importlib.util.spec_from_file_location("planqueue_metrics_for_queue_tests", METRICS_MODULE_PATH)
assert METRICS_SPEC is not None and METRICS_SPEC.loader is not None
METRICS_MODULE = importlib.util.module_from_spec(METRICS_SPEC)
sys.modules[METRICS_SPEC.name] = METRICS_MODULE
METRICS_SPEC.loader.exec_module(METRICS_MODULE)


class PlanQueueTests(unittest.TestCase):
    QUEUE_INELIGIBLE_PLAN_ROWS = (
        (
            "docs/plans/260623_2315_process_architect_prompt_slimming_analysis.md",
            "docs/plans/260711_0131_process_custom_collab_post_smoke_hardening_wave.md#Follow-ups-deferred",
            "Architect prompt-slimming draft — source-only input для "
            "docs/plans/260708_1425_process_custom_pipeline_small_slice_overhead_taxonomy.md; "
            "independent queue item запрещён.",
        ),
        (
            "docs/plans/260623_2316_process_planner_prompt_slimming_analysis.md",
            "docs/plans/260711_0131_process_custom_collab_post_smoke_hardening_wave.md#Follow-ups-deferred",
            "Planner prompt-slimming draft — source-only input для "
            "docs/plans/260708_1425_process_custom_pipeline_small_slice_overhead_taxonomy.md; "
            "independent queue item запрещён.",
        ),
        (
            "docs/plans/260623_2317_process_coder_prompt_slimming_analysis.md",
            "docs/plans/260711_0131_process_custom_collab_post_smoke_hardening_wave.md#Follow-ups-deferred",
            "Coder prompt-slimming draft — source-only input для "
            "docs/plans/260708_1425_process_custom_pipeline_small_slice_overhead_taxonomy.md; "
            "independent queue item запрещён.",
        ),
        (
            "docs/plans/260623_2318_process_reviewer_prompt_slimming_analysis.md",
            "docs/plans/260711_0131_process_custom_collab_post_smoke_hardening_wave.md#Follow-ups-deferred",
            "Reviewer prompt-slimming draft — source-only input для "
            "docs/plans/260708_1425_process_custom_pipeline_small_slice_overhead_taxonomy.md; "
            "independent queue item запрещён.",
        ),
        (
            "docs/plans/260623_2319_process_manager_prompt_slimming_analysis.md",
            "docs/plans/260711_0131_process_custom_collab_post_smoke_hardening_wave.md#Follow-ups-deferred",
            "Manager prompt-slimming draft — source-only input для "
            "docs/plans/260708_1425_process_custom_pipeline_small_slice_overhead_taxonomy.md; "
            "independent queue item запрещён.",
        ),
        (
            "docs/plans/260624_1443_process_role_cost_telemetry_readback_decomposition.md",
            "docs/plans/260624_1442_process_role_cost_telemetry_manager_readback_analysis.md"
            "#Promoted-route-artifact",
            "Direct decomposition bootstrap через planveyor_decomposition_init допустим; queue import запрещён "
            "до одновременной materialization child graph, plan_meta.next_plans[] и approved queue_activation.",
        ),
    )

    def setUp(self) -> None:
        super().setUp()
        self._plan_lint_vocab_loader_patcher = mock.patch.object(
            MODULE.plan_lint,
            "load_plan_vocab",
        )
        self._plan_lint_vocab_loader = self._plan_lint_vocab_loader_patcher.start()
        self._plan_lint_runner_patcher = mock.patch.object(MODULE.plan_lint, "lint_plan")
        self._plan_lint_runner = self._plan_lint_runner_patcher.start()
        self._plan_lint_runner.return_value = []
        self.addCleanup(self._plan_lint_runner_patcher.stop)
        self.addCleanup(self._plan_lint_vocab_loader_patcher.stop)
        self._project_root_env = mock.patch.dict(MODULE.os.environ, {"PLANVEYOR_PROJECT_ROOT": ""})
        self._project_root_env.start()
        self.addCleanup(self._project_root_env.stop)

    def _ensure_fixture_git(self, root: Path) -> None:
        """Turn an intentional fixture Git directory into a real worktree.

        The authority boundary treats an empty ``.git`` directory as corrupt
        metadata rather than a legacy repository marker.  Most queue fixtures
        create that directory before writing their plan inputs, so make the
        smallest committed worktree once those inputs exist.  Negative broken
        Git coverage must deliberately bypass this helper.
        """

        git_path = root / ".git"
        if not git_path.exists():
            return
        # Read only this fixture's metadata: Git discovery would skip the empty
        # directory and answer for an enclosing work tree around TMPDIR.
        head = subprocess.run(
            ["git", f"--git-dir={git_path}", "rev-parse", "--verify", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
        )
        if head.returncode == 0:
            return
        subprocess.run(["git", "init", "--quiet", str(root)], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(root), "config", "user.email", 'queue' + '@' + 'example' + '.' + 'invalid'], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.name", "Queue fixture"], check=True)
        subprocess.run(["git", "-C", str(root), "add", "--all"], check=True)
        subprocess.run(
            ["git", "-C", str(root), "commit", "--quiet", "--allow-empty", "-m", "fixture"],
            check=True,
        )

    def _write_plan(
        self,
        root: Path,
        rel_path: str,
        *,
        status: str = "Ready for Coder",
        meta_json: str | None = None,
        machine_authority: bool = True,
        execution_queue: str | None = None,
        handoff_statuses: str | None = None,
        context_links: str | None = None,
        review_artifacts: str | None = None,
        rollout_packet_handoff: str | None = None,
        small_slice_classifier: str | None = None,
        visual_acceptance: str | None = None,
    ) -> Path:
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        stem = Path(rel_path).stem
        default_decision = self._na_machine_authority_decision()
        default_plan_meta: dict[str, object] = {
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
        if machine_authority:
            default_plan_meta["machine_authority_decision"] = default_decision
        meta_block = meta_json or json.dumps({"plan_meta": default_plan_meta}, ensure_ascii=False, indent=2)
        execution_block = execution_queue or "- `N/A (why=fixture)`"
        handoff_block = handoff_statuses or dedent(
            """\
            - `Ready for Planner` — Architect
            - `Ready for Coder` — Planner
            - `Ready for Review` — Coder
            - `Ready for Arch review` — Reviewer
            - `Done` — Architect
            """
        ).rstrip()
        context_block = context_links or f"- Code draft(s): `docs/code_drafts/{stem}__code_draft.md`"
        review_artifacts_block = review_artifacts or f"- Code review (primary): `docs/code_reviews/{stem}.md`"
        rollout_packet_block = rollout_packet_handoff or dedent(
            """\
            - Role: `N/A (why=fixture)`
            - Packet path: `N/A (why=fixture)`
            - Target repo: `N/A (why=fixture)`
            - Suggested target plan slug: `N/A (why=fixture)`
            - Queue after import: `N/A (why=fixture)`
            """
        ).rstrip()
        small_slice_block = small_slice_classifier or dedent(
            """\
            - Requested profile: `N/A (why=fixture)`
            - Expected bundle family: `N/A (why=fixture)`
            - Helper validation: `N/A (why=fixture)`
            - Drift behavior: `N/A (why=fixture)`
            """
        ).rstrip()
        visual_acceptance_block = visual_acceptance or "- `N/A (why=fixture)`"
        # Emit canonical column-0 markdown: the strict routing reader
        # (plan_status_oracle.strict_plan_meta_json) accepts `## Meta` headings
        # with at most three leading spaces, like real repo plans.
        target.write_text(
            "\n".join(
                [
                    "# Plan: fixture",
                    "",
                    "**Date:** 2026-03-28 01:27 MSK",
                    "**Stage:** Stage 1",
                    "**Priority:** P1",
                    "**Plan type:** dev",
                    f"**Status:** {status}",
                    "",
                    "**Handoff statuses (кто ставит):**",
                    handoff_block,
                    "",
                    "**Context links (source of truth):**",
                    context_block,
                    "",
                    "## Meta (machine-readable JSON; required for new plans)",
                    "```json",
                    meta_block,
                    "```",
                    "",
                    "## Execution queue",
                    execution_block,
                    "",
                    "## Review artifacts",
                    review_artifacts_block,
                    "",
                    "## Rollout packet handoff",
                    rollout_packet_block,
                    "",
                    "## Small-slice conveyor classifier",
                    small_slice_block,
                    "",
                    "## Visual Acceptance (browser, UI tasks)",
                    visual_acceptance_block,
                    "",
                    "## Problem",
                    "",
                    "1. Fixture.",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        decision = self._valid_na_machine_authority_decision(meta_block)
        if decision is not None and context_links is None:
            fixture_target = root / "scripts/machine_authority_fixture.py"
            if not fixture_target.exists():
                fixture_target.parent.mkdir(parents=True, exist_ok=True)
                fixture_target.write_text("# machine-authority fixture\n", encoding="utf-8")
            self._write_code_draft(
                root,
                rel_path,
                target_paths=["scripts/machine_authority_fixture.py"],
                machine_authority_decision=decision,
                overwrite=False,
            )
        self._ensure_fixture_git(root)
        return target

    def _na_machine_authority_decision(self) -> dict[str, str]:
        return {
            "schema_version": "machine_authority_decision.v1",
            "applicability": "not_applicable",
            "reason_code": "no_machine_authority_change",
        }

    def _valid_na_machine_authority_decision(self, meta_json: str) -> dict[str, str] | None:
        try:
            payload = json.loads(meta_json)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        plan_meta = payload.get("plan_meta")
        if not isinstance(plan_meta, dict):
            return None
        decision = plan_meta.get("machine_authority_decision")
        if not isinstance(decision, dict):
            return None
        if set(decision) != {"schema_version", "applicability", "reason_code"}:
            return None
        if decision.get("schema_version") != "machine_authority_decision.v1":
            return None
        if decision.get("applicability") != "not_applicable":
            return None
        reason = decision.get("reason_code")
        if reason not in MODULE.plan_status_oracle.MACHINE_AUTHORITY_DECISION_NA_REASONS:
            return None
        return {key: decision[key] for key in ("schema_version", "applicability", "reason_code")}

    def _valid_na_machine_authority_decision_from_plan_text(self, plan_text: str) -> dict[str, str] | None:
        strict_meta = MODULE.plan_status_oracle.strict_plan_meta_json(plan_text)
        plan_meta = strict_meta.plan_meta if strict_meta.state == "valid" else None
        if not isinstance(plan_meta, dict):
            return None
        return self._valid_na_machine_authority_decision(
            json.dumps({"plan_meta": plan_meta}, ensure_ascii=False)
        )

    def _write_code_draft(
        self,
        root: Path,
        rel_path: str,
        *,
        target_paths: list[str],
        machine_authority_decision: dict[str, str] | None = None,
        overwrite: bool = True,
    ) -> Path:
        draft_rel = f"docs/code_drafts/{Path(rel_path).stem}__code_draft.md"
        draft_path = root / draft_rel
        if not overwrite and (draft_path.exists() or draft_path.is_symlink()):
            return draft_path
        draft_path.parent.mkdir(parents=True, exist_ok=True)
        rendered_targets = [
            {"path": target_path, "kind": "doc" if target_path.startswith("docs/") else "py"}
            for target_path in target_paths
        ]
        if machine_authority_decision is None:
            plan_path = root / rel_path
            if plan_path.is_file():
                machine_authority_decision = self._valid_na_machine_authority_decision_from_plan_text(
                    plan_path.read_text(encoding="utf-8")
                )
        draft_meta: dict[str, object] = {
            "plan": rel_path,
            "cluster": "process",
            "targets": rendered_targets,
        }
        if machine_authority_decision is not None:
            draft_meta["machine_authority_decision_ref"] = {
                "applicability": "not_applicable",
                "reason_code": machine_authority_decision["reason_code"],
                "carrier_sha256": MODULE.plan_status_oracle.machine_authority_decision_sha256(
                    machine_authority_decision
                ),
            }
        draft_path.write_text(
            "# Code draft: fixture\n\n"
            "```json\n"
            + json.dumps(
                {
                    "code_draft_meta": draft_meta
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n```\n",
            encoding="utf-8",
        )
        self._ensure_fixture_git(root)
        return draft_path

    def _queue_paths(self, root: Path) -> MODULE.QueuePaths:
        self._ensure_fixture_git(root)
        return MODULE.QueuePaths(root=root, state_path=root / ".planveyor.planqueue.json", log_path=root / ".planveyor.planqueue.log")

    def test_empty_git_metadata_is_not_a_legacy_queue_root(self) -> None:
        """A fabricated root marker must not silently retain legacy behavior."""

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            # Git skips the empty directory; when TMPDIR lies inside a work tree
            # it resolves that tree, and the refusal names the root mismatch.
            reason = "git_root_mismatch" if inside_git_work_tree(root) else "git_discovery_failed"
            with self.assertRaisesRegex(
                MODULE.QueueError,
                f"contract_authority_preflight_failed:{reason}",
            ):
                MODULE.queue_paths(root)

    def _queue_bytes_snapshot(self, paths: MODULE.QueuePaths) -> tuple[bytes, bytes, bytes | None]:
        return (
            paths.state_path.read_bytes(),
            paths.log_path.read_bytes(),
            paths.txn_path.read_bytes() if paths.txn_path.exists() else None,
        )

    def _assert_queue_bytes_snapshot(
        self,
        paths: MODULE.QueuePaths,
        snapshot: tuple[bytes, bytes, bytes | None],
    ) -> None:
        state_before, log_before, txn_before = snapshot
        self.assertEqual(paths.state_path.read_bytes(), state_before)
        self.assertEqual(paths.log_path.read_bytes(), log_before)
        if txn_before is None:
            self.assertFalse(paths.txn_path.exists())
        else:
            self.assertEqual(paths.txn_path.read_bytes(), txn_before)

    def _lint_finding(
        self,
        root: Path,
        rel_path: str,
        line: int,
        severity: str,
        message: str,
    ) -> MODULE.plan_lint.Finding:
        return MODULE.plan_lint.Finding(root / rel_path, line, severity, message)

    def _save_active_pending_queue(
        self,
        paths: MODULE.QueuePaths,
        *,
        active_rel: str,
        pending_rels: list[str],
        now: str = "2026-06-14T14:40:00Z",
    ) -> None:
        items = [
            {
                "order": 1,
                "plan": active_rel,
                "source": "legacy_fixture",
                "state": "active",
                "added_at": now,
                "activated_at": now,
                "completed_at": None,
                "final_status": None,
                "runtime_class": None,
                "closeout_kind": None,
                "closeout_reason": None,
            }
        ]
        for offset, pending_rel in enumerate(pending_rels, start=2):
            items.append(
                {
                    "order": offset,
                    "plan": pending_rel,
                    "source": "legacy_fixture",
                    "state": "pending",
                    "added_at": now,
                    "activated_at": None,
                    "completed_at": None,
                    "final_status": None,
                    "runtime_class": None,
                    "closeout_kind": None,
                    "closeout_reason": None,
                }
            )
        MODULE.save_state(
            paths,
            {
                "version": 1,
                "mode": "manual_args",
                "source_plan": None,
                "parent_plan": None,
                "resume_parent": "none",
                "created_at": now,
                "updated_at": now,
                "cursor": 0,
                "parent_resume_pending_at": None,
                "parent_resumed_at": None,
                "last_stop": None,
                "last_transition": None,
                "last_planpath_override": None,
                "items": items,
            },
        )
        paths.log_path.write_text(f"{now}\tset\tmode=legacy_fixture\n", encoding="utf-8")

    def _write_plan_vocab(self, root: Path) -> None:
        target = root / "docs/_meta/plan_vocab.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {
                    "planning_contour": {
                        "queue_activation_states": [
                            "not_requested",
                            "owner_approved",
                            "architect_approved",
                            "n/a",
                        ]
                    }
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        self._ensure_fixture_git(root)

    def _meta_with_queue_activation(self, state: object = "architect_approved") -> str:
        queue_activation = state
        if isinstance(state, str):
            queue_activation = {
                "state": state,
                "source_ref": "docs/plans/parent.md#Execution-queue",
                "reason": "fixture",
            }
        return json.dumps(
            {
                "plan_meta": {
                    "cluster": "process",
                    "tags": [],
                    "required_manager_mode": "either",
                    "phase_overlay": None,
                    "phase_state": None,
                    "parent": None,
                    "next_plans": [],
                    "depends_on": [],
                    "queue_activation": queue_activation,
                    "followups_out": [],
                    "canon_updates": [],
                    "machine_authority_decision": self._na_machine_authority_decision(),
                }
            },
            ensure_ascii=False,
            indent=2,
        )

    def _blocking_dependency_meta(
        self,
        *,
        depends_on: list[str],
        blocking_depends_on: object,
    ) -> str:
        return json.dumps(
            {
                "plan_meta": {
                    "cluster": "process",
                    "tags": [],
                    "required_manager_mode": "either",
                    "phase_overlay": None,
                    "phase_state": None,
                    "parent": None,
                    "next_plans": [],
                    "depends_on": depends_on,
                    "blocking_depends_on": blocking_depends_on,
                    "followups_out": [],
                    "canon_updates": [],
                    "machine_authority_decision": self._na_machine_authority_decision(),
                }
            },
            ensure_ascii=False,
            indent=2,
        )

    def _queue_ineligible_meta(
        self,
        *,
        source_ref: str | None,
        reason: str | None,
    ) -> str:
        queue_activation: dict[str, object] = {"state": "n/a"}
        if source_ref is not None:
            queue_activation["source_ref"] = source_ref
        if reason is not None:
            queue_activation["reason"] = reason
        return json.dumps(
            {
                "plan_meta": {
                    "cluster": "process",
                    "tags": [],
                    "required_manager_mode": "manager-collab",
                    "phase_overlay": None,
                    "phase_state": None,
                    "parent": None,
                    "next_plans": [],
                    "depends_on": [],
                    "queue_activation": queue_activation,
                    "followups_out": [],
                    "canon_updates": [],
                    "machine_authority_decision": self._na_machine_authority_decision(),
                }
            },
            ensure_ascii=False,
            indent=2,
        )

    def _manager_mode_meta(self, required_mode: object = "either", *, include: bool = True) -> str:
        plan_meta: dict[str, object] = {
            "cluster": "process",
            "tags": [],
            "phase_overlay": None,
            "phase_state": None,
            "parent": None,
            "next_plans": [],
            "depends_on": [],
            "followups_out": [],
            "canon_updates": [],
            "machine_authority_decision": self._na_machine_authority_decision(),
        }
        if include:
            plan_meta["required_manager_mode"] = required_mode
        return json.dumps({"plan_meta": plan_meta}, ensure_ascii=False, indent=2)

    def _prepare_mode_closeout_queue(
        self,
        root: Path,
        *,
        candidate_kind: str,
        candidate_meta: str,
    ) -> tuple[MODULE.QueuePaths, str, str]:
        active_rel = "docs/plans/260717_2200_active_done.md"
        candidate_rel = f"docs/plans/260717_2201_{candidate_kind}.md"
        self._write_plan(
            root,
            active_rel,
            status="Done",
            meta_json=self._manager_mode_meta("either"),
        )
        self._write_plan(
            root,
            candidate_rel,
            status="Ready for Coder",
            meta_json=candidate_meta,
        )
        paths = self._queue_paths(root)
        plans = [active_rel, candidate_rel] if candidate_kind == "next_plan" else [active_rel]
        MODULE.set_queue(
            paths,
            plans=plans,
            resume_parent="run-parent-once" if candidate_kind == "resume_parent_plan" else "none",
            now="2026-07-17T19:00:00Z",
        )
        MODULE.activate_next(paths, now="2026-07-17T19:00:01Z")
        if candidate_kind == "resume_parent_plan":
            state = MODULE.load_state(paths)
            assert state is not None
            state["parent_plan"] = candidate_rel
            MODULE.save_state(paths, state)
        return paths, active_rel, candidate_rel

    def test_manual_queue_rejects_nonterminal_active_status_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            self._write_plan(root, "docs/plans/260328_0100_first.md", status="Ready for Coder")
            self._write_plan(root, "docs/plans/260328_0101_second.md", status="In progress")
            paths = self._queue_paths(root)

            snapshot = MODULE.set_queue(
                paths,
                plans=["docs/plans/260328_0101_second.md", "docs/plans/260328_0100_first.md"],
                now="2026-03-28T01:30:00Z",
            )
            activated = MODULE.activate_next(paths, now="2026-03-28T01:31:00Z")
            before = self._queue_bytes_snapshot(paths)
            with self.assertRaises(MODULE.QueueError) as raised:
                MODULE.advance_queue(paths, "Done", now="2026-03-28T01:32:00Z")
            self._assert_queue_bytes_snapshot(paths, before)

        self.assertTrue(snapshot["exists"])
        self.assertEqual([item["plan"] for item in snapshot["items"]], [
            "docs/plans/260328_0101_second.md",
            "docs/plans/260328_0100_first.md",
        ])
        self.assertEqual(snapshot["items"][0]["added_at"], "2026-03-28T01:30:00Z")
        self.assertEqual(activated["active_plan"], "docs/plans/260328_0101_second.md")
        self.assertEqual(activated["items"][0]["activated_at"], "2026-03-28T01:31:00Z")
        self.assertEqual(raised.exception.payload["reason_code"], "terminal_status_assertion_mismatch")
        self.assertEqual(raised.exception.payload["oracle_status"], "In progress")

    def test_manual_queue_preserves_order_and_timestamps_for_terminal_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            self._write_plan(root, "docs/plans/260328_0100_first.md", status="Ready for Coder")
            self._write_plan(root, "docs/plans/260328_0101_second.md", status="Done")
            paths = self._queue_paths(root)

            snapshot = MODULE.set_queue(
                paths,
                plans=["docs/plans/260328_0101_second.md", "docs/plans/260328_0100_first.md"],
                now="2026-03-28T01:30:00Z",
            )
            activated = MODULE.activate_next(paths, now="2026-03-28T01:31:00Z")
            advanced = MODULE.advance_queue(paths, "Done", now="2026-03-28T01:32:00Z")

        self.assertTrue(snapshot["exists"])
        self.assertEqual([item["plan"] for item in snapshot["items"]], [
            "docs/plans/260328_0101_second.md",
            "docs/plans/260328_0100_first.md",
        ])
        self.assertEqual(snapshot["items"][0]["added_at"], "2026-03-28T01:30:00Z")
        self.assertEqual(activated["active_plan"], "docs/plans/260328_0101_second.md")
        self.assertEqual(activated["items"][0]["activated_at"], "2026-03-28T01:31:00Z")
        self.assertEqual(advanced["finalized_plan"], "docs/plans/260328_0101_second.md")
        self.assertEqual(advanced["final_status"], "Done")
        self.assertEqual(advanced["next_plan"], "docs/plans/260328_0100_first.md")
        self.assertEqual(advanced["items"][0]["completed_at"], "2026-03-28T01:32:00Z")

    def test_cli_requires_mode_carriers_for_all_materialization_and_activation_commands(self) -> None:
        unqualified = (
            ["set", "docs/plans/example.md"],
            ["append", "docs/plans/example.md"],
            ["next"],
            ["advance", "--final-status", "Done"],
            ["closeout"],
        )
        for argv in unqualified:
            with self.subTest(argv=argv), mock.patch("sys.stderr", io.StringIO()), self.assertRaises(SystemExit) as exited:
                MODULE.build_parser().parse_args(argv)
            self.assertEqual(exited.exception.code, 2)

        qualified = (
            ["set", "docs/plans/example.md", "--for-manager-mode", "manager-collab"],
            ["append", "docs/plans/example.md", "--for-manager-mode", "manager-custom-pipeline"],
            ["next", "--manager-mode", "manager-collab"],
            ["advance", "--final-status", "Done", "--manager-mode", "manager-custom-pipeline"],
            ["closeout", "--manager-mode", "manager-collab"],
        )
        for argv in qualified:
            with self.subTest(argv=argv):
                self.assertEqual(MODULE.build_parser().parse_args(argv).command, argv[0])

    def test_append_fails_when_queue_is_uninitialized(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            self._write_plan(root, "docs/plans/260611_2232_append_target.md")
            stdout = io.StringIO()
            stderr = io.StringIO()

            with mock.patch("sys.stdout", stdout), mock.patch("sys.stderr", stderr):
                result = MODULE.main(
                    [
                        "--project-root",
                        str(root),
                        "append",
                        "docs/plans/260611_2232_append_target.md",
                        "--for-manager-mode",
                        "manager-collab",
                        "--json",
                    ]
                )

        self.assertEqual(result, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("Queue is not initialized; use planveyor_q_set first", stderr.getvalue())

    def test_append_preserves_active_item_and_last_stop(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            self._write_plan(root, "docs/plans/260611_2233_active.md")
            self._write_plan(root, "docs/plans/260611_2234_tail.md")
            paths = self._queue_paths(root)
            MODULE.set_queue(paths, plans=["docs/plans/260611_2233_active.md"], now="2026-06-11T22:33:00Z")
            MODULE.activate_next(paths, now="2026-06-11T22:34:00Z")
            stopped = MODULE.stop_queue(paths, "owner_questions_open", now="2026-06-11T22:35:00Z")

            snapshot = MODULE.append_queue(
                paths,
                ["docs/plans/260611_2234_tail.md"],
                now="2026-06-11T22:36:00Z",
            )

        self.assertEqual(snapshot["active_plan"], "docs/plans/260611_2233_active.md")
        self.assertEqual(snapshot["active_order"], 1)
        self.assertEqual(snapshot["cursor"], 0)
        self.assertEqual(snapshot["last_stop"], stopped["last_stop"])
        self.assertEqual(snapshot["appended"], ["docs/plans/260611_2234_tail.md"])
        self.assertEqual(snapshot["items"][1]["order"], 2)
        self.assertEqual(snapshot["items"][1]["state"], "pending")
        self.assertEqual(snapshot["items"][1]["source"], "manual_append")
        self.assertEqual(snapshot["items"][1]["added_at"], "2026-06-11T22:36:00Z")

    def test_append_skips_already_present_queue_items_and_logs_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            self._write_plan(root, "docs/plans/260611_2235_existing.md")
            self._write_plan(root, "docs/plans/260611_2236_new.md")
            paths = self._queue_paths(root)
            MODULE.set_queue(paths, plans=["docs/plans/260611_2235_existing.md"], now="2026-06-11T22:35:00Z")

            snapshot = MODULE.append_queue(
                paths,
                ["docs/plans/260611_2235_existing.md", "docs/plans/260611_2236_new.md"],
                now="2026-06-11T22:36:00Z",
            )
            log_lines = paths.log_path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(snapshot["appended"], ["docs/plans/260611_2236_new.md"])
        self.assertEqual(snapshot["skipped_duplicates"], ["docs/plans/260611_2235_existing.md"])
        self.assertEqual([item["plan"] for item in snapshot["items"]], [
            "docs/plans/260611_2235_existing.md",
            "docs/plans/260611_2236_new.md",
        ])
        self.assertIn("\tappend\t", log_lines[-1])
        self.assertIn("appended=1", log_lines[-1])
        self.assertIn("skipped_duplicates=1", log_lines[-1])
        self.assertIn("plans=docs/plans/260611_2236_new.md", log_lines[-1])
        self.assertIn("duplicates=docs/plans/260611_2235_existing.md", log_lines[-1])

    def test_append_rejects_duplicate_input_arguments_before_state_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            self._write_plan(root, "docs/plans/260611_2237_existing.md")
            self._write_plan(root, "docs/plans/260611_2238_duplicate.md")
            paths = self._queue_paths(root)
            MODULE.set_queue(paths, plans=["docs/plans/260611_2237_existing.md"], now="2026-06-11T22:37:00Z")
            before_state = paths.state_path.read_text(encoding="utf-8")
            before_log = paths.log_path.read_text(encoding="utf-8")
            stderr = io.StringIO()

            with mock.patch("sys.stderr", stderr):
                result = MODULE.main(
                    [
                        "--project-root",
                        str(root),
                        "append",
                        "docs/plans/260611_2238_duplicate.md",
                        "docs/plans/260611_2238_duplicate.md",
                        "--for-manager-mode",
                        "manager-collab",
                    ]
                )

            self.assertEqual(result, 1)
            self.assertIn("duplicate input arguments", stderr.getvalue())
            self.assertEqual(paths.state_path.read_text(encoding="utf-8"), before_state)
            self.assertEqual(paths.log_path.read_text(encoding="utf-8"), before_log)

    def test_append_rejects_invalid_paths_before_state_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            self._write_plan(root, "docs/plans/260611_2239_existing.md")
            not_plan = root / "docs/not_plans/260611_2240_not_plan.md"
            not_plan.parent.mkdir(parents=True, exist_ok=True)
            not_plan.write_text("# Not a plan\n", encoding="utf-8")
            outside_plan = root.parent / f"{root.name}_outside_plan.md"
            outside_plan.write_text("# Outside\n", encoding="utf-8")
            invalid_inputs = [
                "docs/plans/260611_2239_missing.md",
                "docs/not_plans/260611_2240_not_plan.md",
                "docs/plans/README.md",
                str(outside_plan),
            ]
            paths = self._queue_paths(root)
            MODULE.set_queue(paths, plans=["docs/plans/260611_2239_existing.md"], now="2026-06-11T22:39:00Z")

            try:
                for raw_path in invalid_inputs:
                    before_state = paths.state_path.read_text(encoding="utf-8")
                    before_log = paths.log_path.read_text(encoding="utf-8")
                    stderr = io.StringIO()
                    with self.subTest(raw_path=raw_path), mock.patch("sys.stderr", stderr):
                        result = MODULE.main(
                            [
                                "--project-root",
                                str(root),
                                "append",
                                raw_path,
                                "--for-manager-mode",
                                "manager-collab",
                            ]
                        )

                    self.assertEqual(result, 1)
                    self.assertEqual(paths.state_path.read_text(encoding="utf-8"), before_state)
                    self.assertEqual(paths.log_path.read_text(encoding="utf-8"), before_log)
            finally:
                outside_plan.unlink(missing_ok=True)

    def test_append_after_finalized_queue_is_pending_not_started_not_complete(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            self._write_plan(root, "docs/plans/260611_2241_done.md", status="Done")
            self._write_plan(root, "docs/plans/260611_2242_tail.md")
            paths = self._queue_paths(root)
            MODULE.set_queue(paths, plans=["docs/plans/260611_2241_done.md"], now="2026-06-11T22:41:00Z")
            MODULE.activate_next(paths, now="2026-06-11T22:42:00Z")
            MODULE.advance_queue(paths, "Done", now="2026-06-11T22:43:00Z")

            snapshot = MODULE.append_queue(
                paths,
                ["docs/plans/260611_2242_tail.md"],
                now="2026-06-11T22:44:00Z",
            )
            rendered = MODULE.render_snapshot(snapshot)

        self.assertIsNone(snapshot["active_plan"])
        self.assertEqual(snapshot["pending_count"], 1)
        self.assertFalse(snapshot["queue_empty"])
        self.assertEqual(snapshot["effective_phase"], "pending_not_started")
        self.assertNotIn("current=none (queue_complete)", rendered)
        self.assertIn("current=none (pending_not_started)", rendered)
        self.assertEqual(snapshot["items"][1]["order"], 2)

    def test_append_json_cli_returns_bounded_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            self._write_plan(root, "docs/plans/260611_2245_existing.md")
            self._write_plan(root, "docs/plans/260611_2246_tail.md")
            paths = self._queue_paths(root)
            MODULE.set_queue(paths, plans=["docs/plans/260611_2245_existing.md"], now="2026-06-11T22:45:00Z")
            stdout = io.StringIO()

            with mock.patch("sys.stdout", stdout):
                result = MODULE.main(
                    [
                        "--project-root",
                        str(root),
                        "append",
                        "docs/plans/260611_2246_tail.md",
                        "--for-manager-mode",
                        "manager-collab",
                        "--json",
                    ]
                )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(result, 0)
        self.assertEqual(payload["appended"], ["docs/plans/260611_2246_tail.md"])
        self.assertEqual(payload["skipped_duplicates"], [])
        self.assertEqual(payload["rejected"], [])
        self.assertIsNone(payload["active_plan"])
        self.assertEqual(payload["pending_count"], 2)
        self.assertEqual(payload["next_pending_plan"], "docs/plans/260611_2245_existing.md")

    def test_append_rejects_pending_parent_resume_before_state_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            self._write_plan(root, "docs/plans/260611_2247_parent.md")
            self._write_plan(root, "docs/plans/260611_2248_child.md")
            self._write_plan(root, "docs/plans/260611_2249_tail.md")
            paths = self._queue_paths(root)
            state = MODULE.build_state(
                mode="umbrella_children",
                items=[],
                now="2026-06-11T22:47:00Z",
                source_plan="docs/plans/260611_2247_parent.md",
                parent_plan="docs/plans/260611_2247_parent.md",
                resume_parent="run-parent-once",
            )
            state["parent_resume_pending_at"] = "2026-06-11T22:48:00Z"
            MODULE.save_state(paths, state)
            before_state = paths.state_path.read_text(encoding="utf-8")

            with self.assertRaises(MODULE.QueueError):
                MODULE.append_queue(paths, ["docs/plans/260611_2249_tail.md"])

            self.assertEqual(paths.state_path.read_text(encoding="utf-8"), before_state)

    def test_status_query_builds_sorted_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            self._write_plan(root, "docs/plans/260328_0102_beta.md", status="Ready for Coder")
            self._write_plan(root, "docs/plans/260328_0101_alpha.md", status="In progress")
            self._write_plan(root, "docs/plans/260328_0103_done.md", status="Done")
            paths = self._queue_paths(root)

            snapshot = MODULE.set_queue(
                paths,
                statuses=["ready for coder", "in progress"],
                now="2026-03-28T01:40:00Z",
            )

        self.assertEqual([item["plan"] for item in snapshot["items"]], [
            "docs/plans/260328_0101_alpha.md",
            "docs/plans/260328_0102_beta.md",
        ])
        self.assertTrue(all(item["source"] == "status_query" for item in snapshot["items"]))

    def test_status_query_rejects_invalid_queue_activation_without_state_or_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            self._write_plan_vocab(root)
            invalid_rel = "docs/plans/260614_1736_invalid_status_query_activation.md"
            self._write_plan(root, invalid_rel, status="Architect initial draft")
            paths = self._queue_paths(root)

            with self.assertRaisesRegex(MODULE.QueueError, "queue_activation_admission_blocked"):
                MODULE.set_queue(
                    paths,
                    statuses=["architect initial draft"],
                    now="2026-06-14T14:36:00Z",
                )

            self.assertFalse(paths.state_path.exists())
            self.assertFalse(paths.log_path.exists())

    def test_explicit_and_status_collection_reject_exact_queue_ineligible_plan_rows(self) -> None:
        for collection_kind in ("explicit", "status"):
            for plan_rel, source_ref, reason in self.QUEUE_INELIGIBLE_PLAN_ROWS:
                with (
                    self.subTest(collection_kind=collection_kind, plan=plan_rel),
                    tempfile.TemporaryDirectory() as tmpdir,
                ):
                    root = Path(tmpdir)
                    (root / ".git").mkdir()
                    self._write_plan_vocab(root)
                    self._write_plan(
                        root,
                        plan_rel,
                        status="Architect initial draft",
                        meta_json=self._queue_ineligible_meta(source_ref=source_ref, reason=reason),
                    )
                    paths = self._queue_paths(root)
                    expected = (
                        f"queue_activation_admission_blocked: {plan_rel}: "
                        "queue_collection_ineligible; state=n/a"
                    )

                    with self.assertRaises(MODULE.QueueError) as raised:
                        if collection_kind == "explicit":
                            MODULE.set_queue(
                                paths,
                                plans=[plan_rel],
                                manager_mode="manager-collab",
                                now="2026-07-19T08:30:00Z",
                            )
                        else:
                            MODULE.set_queue(
                                paths,
                                statuses=["architect initial draft"],
                                manager_mode="manager-collab",
                                now="2026-07-19T08:30:00Z",
                            )

                    self.assertEqual(str(raised.exception), expected)
                    self.assertIsNone(raised.exception.payload)
                    self.assertNotIn("skipped_incompatible", str(raised.exception))
                    self.assertNotIn("skip_manager_mode", str(raised.exception))
                    self.assertFalse(paths.state_path.exists())
                    self.assertFalse(paths.log_path.exists())

    def test_queue_ineligible_state_requires_complete_object_before_collection_rejection(self) -> None:
        for missing_field in ("source_ref", "reason"):
            with self.subTest(missing_field=missing_field), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                (root / ".git").mkdir()
                self._write_plan_vocab(root)
                plan_rel = f"docs/plans/260719_0831_missing_{missing_field}.md"
                source_ref = None if missing_field == "source_ref" else "docs/plans/parent.md#queue"
                reason = None if missing_field == "reason" else "intentional source-only carrier"
                self._write_plan(
                    root,
                    plan_rel,
                    status="Ready for Coder",
                    meta_json=self._queue_ineligible_meta(source_ref=source_ref, reason=reason),
                )
                paths = self._queue_paths(root)

                with self.assertRaisesRegex(
                    MODULE.QueueError,
                    rf"missing_or_invalid queue_activation carrier; state=n/a; missing_required={missing_field}",
                ):
                    MODULE.set_queue(
                        paths,
                        plans=[plan_rel],
                        manager_mode="manager-collab",
                        now="2026-07-19T08:31:00Z",
                    )

                self.assertFalse(paths.state_path.exists())
                self.assertFalse(paths.log_path.exists())

    def test_queue_activation_approved_and_later_status_absent_carriers_keep_mode_admission(self) -> None:
        cases = (
            ("owner_approved", "Architect initial draft", self._meta_with_queue_activation("owner_approved")),
            (
                "architect_approved",
                "Architect initial draft",
                self._meta_with_queue_activation("architect_approved"),
            ),
            ("later_status_absent", "Ready for Coder", None),
        )
        for label, status, meta_json in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                (root / ".git").mkdir()
                self._write_plan_vocab(root)
                plan_rel = f"docs/plans/260719_0832_{label}.md"
                self._write_plan(root, plan_rel, status=status, meta_json=meta_json)
                paths = self._queue_paths(root)

                snapshot = MODULE.set_queue(
                    paths,
                    plans=[plan_rel],
                    manager_mode="manager-collab",
                    now="2026-07-19T08:32:00Z",
                )

                self.assertEqual([item["plan"] for item in snapshot["items"]], [plan_rel])
                self.assertEqual(snapshot["skipped_incompatible"], [])
                self.assertNotIn("skip_manager_mode", paths.log_path.read_text(encoding="utf-8"))

    def test_umbrella_queue_ineligible_child_rejects_without_mutating_existing_state_or_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            self._write_plan_vocab(root)
            existing_rel = "docs/plans/260719_0833_existing.md"
            child_rel, source_ref, reason = self.QUEUE_INELIGIBLE_PLAN_ROWS[0]
            umbrella_rel = "docs/plans/260719_0833_umbrella.md"
            self._write_plan(root, existing_rel)
            self._write_plan(
                root,
                child_rel,
                status="Architect initial draft",
                meta_json=self._queue_ineligible_meta(source_ref=source_ref, reason=reason),
            )
            self._write_plan(
                root,
                umbrella_rel,
                meta_json=dedent(
                    f"""\
                    {{
                      "plan_meta": {{
                        "cluster": "process",
                        "tags": [],
                        "required_manager_mode": "manager-collab",
                        "phase_overlay": null,
                        "phase_state": null,
                        "parent": null,
                        "next_plans": ["{child_rel}"],
                        "depends_on": [],
                        "followups_out": [],
                        "canon_updates": []
                      }}
                    }}
                    """
                ).strip(),
                execution_queue=dedent(
                    f"""\
                    - Resume parent: `run-parent-once`
                    - Plan: `{child_rel}`
                    """
                ).rstrip(),
            )
            paths = self._queue_paths(root)
            MODULE.set_queue(
                paths,
                plans=[existing_rel],
                manager_mode="manager-collab",
                now="2026-07-19T08:33:00Z",
            )
            state_before = paths.state_path.read_bytes()
            log_before = paths.log_path.read_bytes()

            with self.assertRaisesRegex(
                MODULE.QueueError,
                rf"queue_activation_admission_blocked: {child_rel}: "
                r"queue_collection_ineligible; state=n/a",
            ):
                MODULE.set_queue(
                    paths,
                    umbrella=umbrella_rel,
                    manager_mode="manager-collab",
                    now="2026-07-19T08:33:01Z",
                )

            self.assertEqual(paths.state_path.read_bytes(), state_before)
            self.assertEqual(paths.log_path.read_bytes(), log_before)
            self.assertNotIn(b"skip_manager_mode", paths.log_path.read_bytes())

    def test_append_queue_ineligible_plan_rejects_without_mutating_existing_state_or_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            self._write_plan_vocab(root)
            existing_rel = "docs/plans/260719_0834_existing.md"
            plan_rel, source_ref, reason = self.QUEUE_INELIGIBLE_PLAN_ROWS[-1]
            self._write_plan(root, existing_rel)
            self._write_plan(
                root,
                plan_rel,
                status="Architect initial draft",
                meta_json=self._queue_ineligible_meta(source_ref=source_ref, reason=reason),
            )
            paths = self._queue_paths(root)
            MODULE.set_queue(
                paths,
                plans=[existing_rel],
                manager_mode="manager-collab",
                now="2026-07-19T08:34:00Z",
            )
            state_before = paths.state_path.read_bytes()
            log_before = paths.log_path.read_bytes()

            with self.assertRaisesRegex(
                MODULE.QueueError,
                rf"queue_activation_admission_blocked: {plan_rel}: "
                r"queue_collection_ineligible; state=n/a",
            ):
                MODULE.append_queue(
                    paths,
                    [plan_rel],
                    manager_mode="manager-collab",
                    now="2026-07-19T08:34:01Z",
                )

            self.assertEqual(paths.state_path.read_bytes(), state_before)
            self.assertEqual(paths.log_path.read_bytes(), log_before)
            self.assertNotIn(b"skip_manager_mode", paths.log_path.read_bytes())

    def test_umbrella_import_prefers_canonical_execution_queue_and_durable_parent_resume(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            self._write_plan(root, "docs/plans/260328_0201_child_a.md", status="Done")
            self._write_plan(root, "docs/plans/260328_0202_child_b.md", status="Done")
            umbrella = self._write_plan(
                root,
                "docs/plans/260328_0200_umbrella.md",
                meta_json=dedent(
                    """\
                    {
                      "plan_meta": {
                        "cluster": "process",
                        "tags": [],
                        "required_manager_mode": "either",
                        "phase_overlay": null,
                        "phase_state": null,
                        "parent": null,
                        "next_plans": [],
                        "depends_on": [],
                        "followups_out": [
                          {"cluster": "process", "summary": "legacy", "plan": "docs/plans/260328_9999_ignored.md"}
                        ],
                        "canon_updates": []
                      }
                    }
                    """
                ).strip(),
                execution_queue=dedent(
                    """\
                    - Resume parent: `run-parent-once`
                    - Plan: `docs/plans/260328_0201_child_a.md`
                    - Plan: `docs/plans/260328_0202_child_b.md`
                    """
                ).rstrip(),
            )
            paths = self._queue_paths(root)

            snapshot = MODULE.set_queue(paths, umbrella=str(umbrella), now="2026-03-28T01:50:00Z")
            MODULE.activate_next(paths, now="2026-03-28T01:51:00Z")
            advanced = MODULE.advance_queue(paths, "Done", now="2026-03-28T01:52:00Z")
            final_advance = MODULE.advance_queue(paths, "Done", now="2026-03-28T01:53:00Z")
            stdout = io.StringIO()
            with mock.patch("sys.stdout", stdout):
                result = MODULE.main(
                    [
                        "--project-root",
                        str(root),
                        "next",
                        "--manager-mode",
                        "manager-collab",
                        "--json",
                    ]
                )
            next_payload = json.loads(stdout.getvalue())
            override_snapshot = MODULE.mark_planpath_override(
                paths,
                "docs/plans/260328_0200_umbrella.md",
                reason="queue_resume_parent",
            )
            stored_state = MODULE.load_state(paths)

        self.assertEqual(snapshot["resume_parent"], "run-parent-once")
        self.assertEqual([item["source"] for item in snapshot["items"]], ["execution_queue", "execution_queue"])
        self.assertEqual(advanced["next_plan"], "docs/plans/260328_0202_child_b.md")
        self.assertFalse(final_advance["queue_complete"])
        self.assertEqual(final_advance["resume_parent_plan"], "docs/plans/260328_0200_umbrella.md")
        self.assertEqual(result, 0)
        self.assertEqual(next_payload["active_plan"], "docs/plans/260328_0200_umbrella.md")
        self.assertEqual(next_payload["resume_parent_plan"], "docs/plans/260328_0200_umbrella.md")
        self.assertFalse(next_payload["queue_empty"])
        assert stored_state is not None
        self.assertIsNone(override_snapshot["resume_parent_plan"])
        self.assertTrue(override_snapshot["queue_empty"])
        self.assertIsNone(stored_state["parent_resume_pending_at"])
        self.assertIsNotNone(stored_state["parent_resumed_at"])
        self.assertEqual(stored_state["last_transition"]["kind"], "parent_resumed")
        self.assertTrue(stored_state["last_transition"]["queue_complete"])
        self.assertIsNone(stored_state["last_transition"]["resume_parent_plan"])
        self.assertEqual(stored_state["last_transition"]["parent_plan"], "docs/plans/260328_0200_umbrella.md")
        self.assertEqual(override_snapshot["last_transition"]["kind"], "parent_resumed")
        self.assertTrue(override_snapshot["last_transition"]["queue_complete"])

    def test_legacy_resumed_parent_transition_requires_explicit_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            self._write_plan(root, "docs/plans/260328_0220_umbrella.md")
            self._write_plan(root, "docs/plans/260328_0221_child.md")
            paths = self._queue_paths(root)

            state = MODULE.build_state(
                mode="umbrella_children",
                items=[
                    {
                        "order": 1,
                        "plan": "docs/plans/260328_0221_child.md",
                        "source": "execution_queue",
                        "state": "done",
                        "added_at": "2026-03-28T02:20:00Z",
                        "activated_at": "2026-03-28T02:21:00Z",
                        "completed_at": "2026-03-28T02:22:00Z",
                        "final_status": "Done",
                        "runtime_class": None,
                        "closeout_kind": "terminal_status",
                        "closeout_reason": "terminal status Done requested explicitly",
                    }
                ],
                now="2026-03-28T02:20:00Z",
                source_plan="docs/plans/260328_0220_umbrella.md",
                parent_plan="docs/plans/260328_0220_umbrella.md",
                resume_parent="run-parent-once",
            )
            state["cursor"] = 1
            state["parent_resume_pending_at"] = None
            state["parent_resumed_at"] = "2026-03-28T02:23:00Z"
            state["last_transition"] = {
                "kind": "resume_parent_pending",
                "at": "2026-03-28T02:22:00Z",
                "finalized_plan": "docs/plans/260328_0221_child.md",
                "final_status": "Done",
                "runtime_class": None,
                "closeout_kind": "terminal_status",
                "closeout_reason": "terminal status Done requested explicitly",
                "next_plan": None,
                "resume_parent_plan": "docs/plans/260328_0220_umbrella.md",
                "queue_complete": False,
            }
            MODULE.save_state(paths, state)

            state_before = paths.state_path.read_bytes()
            with self.assertRaises(MODULE.QueueError) as show_error:
                MODULE.show_queue(paths)
            with self.assertRaises(MODULE.QueueError) as history_error:
                MODULE.queue_history_report(paths)
            self.assertEqual(show_error.exception.payload["error"], "recovery_required")
            self.assertEqual(show_error.exception.payload["classification"], "legacy_repair_required")
            self.assertEqual(history_error.exception.payload["classification"], "legacy_repair_required")
            self.assertEqual(paths.state_path.read_bytes(), state_before)
            self.assertFalse(paths.log_path.exists())

            recovered = MODULE.recover_queue(paths)
            snapshot = MODULE.show_queue(paths)
            rendered = MODULE.render_snapshot(snapshot)
            repaired_state = json.loads(paths.state_path.read_text(encoding="utf-8"))
            log_text = paths.log_path.read_text(encoding="utf-8")

        self.assertTrue(snapshot["queue_empty"])
        self.assertEqual(snapshot["last_transition"]["kind"], "parent_resumed")
        self.assertEqual(snapshot["last_transition"]["at"], "2026-03-28T02:23:00Z")
        self.assertTrue(snapshot["last_transition"]["queue_complete"])
        self.assertIsNone(snapshot["last_transition"]["resume_parent_plan"])
        self.assertIn("last_transition=parent_resumed", rendered)
        self.assertIn("-> queue_complete=yes", rendered)
        self.assertEqual(recovered["classification"], "legacy_repair_required")
        self.assertEqual(recovered["result"], "recovered")
        self.assertTrue(recovered["mutation_performed"])
        self.assertEqual(repaired_state["last_transition"]["kind"], "parent_resumed")
        self.assertTrue(repaired_state["last_transition"]["queue_complete"])
        self.assertIn("state_repair", log_text)
        self.assertIn("legacy_parent_resumed_transition", log_text)

    def test_legacy_followups_out_import_preserves_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            self._write_plan(root, "docs/plans/260328_0301_child_a.md")
            self._write_plan(root, "docs/plans/260328_0302_child_b.md")
            umbrella = self._write_plan(
                root,
                "docs/plans/260328_0300_umbrella.md",
                meta_json=dedent(
                    """\
                    {
                      "plan_meta": {
                        "cluster": "process",
                        "tags": [],
                        "phase_overlay": null,
                        "phase_state": null,
                        "parent": null,
                        "next_plans": [
                          "docs/plans/260328_0301_child_a.md"
                        ],
                        "depends_on": [],
                        "followups_out": [
                          {"cluster": "process", "summary": "first", "plan": "docs/plans/260328_0301_child_a.md"},
                          {"cluster": "process", "summary": "second", "plan": "docs/plans/260328_0302_child_b.md"}
                        ],
                        "canon_updates": []
                      }
                    }
                    """
                ).strip(),
            )
            paths = self._queue_paths(root)

            snapshot = MODULE.set_queue(paths, umbrella=str(umbrella), now="2026-03-28T02:00:00Z")

        self.assertEqual(snapshot["resume_parent"], "owner-restamp-required")
        self.assertEqual([item["source"] for item in snapshot["items"]], ["legacy_followups_out", "legacy_followups_out"])

    def test_v2_plan_rejects_legacy_local_outbox_before_queue_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            umbrella = self._write_plan(root, "docs/plans/260811_0070_v2_umbrella.md")
            text = umbrella.read_text(encoding="utf-8")
            umbrella.write_text(
                text.replace("**Status:** Ready for Coder\n", "**Status:** Ready for Coder\n**Schema version:** plan.v2\n"),
                encoding="utf-8",
            )
            paths = self._queue_paths(root)
            with self.assertRaisesRegex(MODULE.QueueError, "external backlog never enters queue"):
                MODULE.set_queue(paths, umbrella=str(umbrella), now="2026-08-11T22:00:00Z")
            self.assertFalse(paths.state_path.exists())

    def test_unsupported_plan_schema_cannot_enter_legacy_followups_out_queue_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            umbrella = self._write_plan(root, "docs/plans/260811_0071_unsupported_umbrella.md")
            text = umbrella.read_text(encoding="utf-8")
            umbrella.write_text(
                text.replace("**Status:** Ready for Coder\n", "**Status:** Ready for Coder\n**Schema version:** plan.v9\n"),
                encoding="utf-8",
            )
            paths = self._queue_paths(root)

            with self.assertRaisesRegex(MODULE.QueueError, "unsupported_plan_schema_for_legacy_queue_fallback"):
                MODULE.set_queue(paths, umbrella=str(umbrella), now="2026-08-12T00:00:00Z")

            self.assertFalse(paths.state_path.exists())

    def test_next_plans_import_is_used_when_followups_out_has_no_plan_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            self._write_plan(root, "docs/plans/260328_0311_child_a.md")
            self._write_plan(root, "docs/plans/260328_0312_child_b.md")
            umbrella = self._write_plan(
                root,
                "docs/plans/260328_0310_umbrella.md",
                meta_json=dedent(
                    """\
                    {
                      "plan_meta": {
                        "cluster": "process",
                        "tags": [],
                        "phase_overlay": null,
                        "phase_state": null,
                        "parent": null,
                        "next_plans": [
                          "docs/plans/260328_0311_child_a.md",
                          "docs/plans/260328_0312_child_b.md"
                        ],
                        "depends_on": [],
                        "followups_out": [],
                        "canon_updates": []
                      }
                    }
                    """
                ).strip(),
            )
            paths = self._queue_paths(root)

            snapshot = MODULE.set_queue(paths, umbrella=str(umbrella), now="2026-03-28T02:05:00Z")

        self.assertEqual([item["plan"] for item in snapshot["items"]], [
            "docs/plans/260328_0311_child_a.md",
            "docs/plans/260328_0312_child_b.md",
        ])
        self.assertEqual([item["source"] for item in snapshot["items"]], ["next_plans", "next_plans"])

    def test_umbrella_import_rejects_architect_initial_draft_without_queue_activation_before_state_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            child_rel = "docs/plans/260614_1701_missing_activation_child.md"
            self._write_plan(root, child_rel, status="Architect initial draft")
            self._write_plan(
                root,
                "docs/plans/260614_1700_umbrella.md",
                meta_json=dedent(
                    f"""\
                    {{
                      "plan_meta": {{
                        "cluster": "process",
                        "tags": [],
                        "phase_overlay": null,
                        "phase_state": null,
                        "parent": null,
                        "next_plans": ["{child_rel}"],
                        "depends_on": [],
                        "followups_out": [],
                        "canon_updates": []
                      }}
                    }}
                    """
                ).strip(),
                execution_queue=dedent(
                    f"""\
                    - Resume parent: `run-parent-once`
                    - Plan: `{child_rel}`
                    """
                ).rstrip(),
            )
            paths = self._queue_paths(root)

            with self.assertRaisesRegex(MODULE.QueueError, "queue_activation_admission_blocked"):
                MODULE.set_queue(
                    paths,
                    umbrella="docs/plans/260614_1700_umbrella.md",
                    now="2026-06-14T14:20:00Z",
                )

            self.assertFalse(paths.state_path.exists())
            self.assertFalse(paths.log_path.exists())

    def test_architect_initial_draft_queue_activation_shape_matrix_rejects_invalid_direct_set(self) -> None:
        invalid_cases: dict[str, str] = {
            "absent": dedent(
                """\
                {
                  "plan_meta": {
                    "cluster": "process",
                    "tags": [],
                    "phase_overlay": null,
                    "phase_state": null,
                    "parent": null,
                    "next_plans": [],
                    "depends_on": [],
                    "followups_out": [],
                    "canon_updates": []
                  }
                }
                """
            ).strip(),
            "null": self._meta_with_queue_activation(None),
            "non_object": json.dumps(
                {
                    "plan_meta": {
                        "cluster": "process",
                        "tags": [],
                        "phase_overlay": None,
                        "phase_state": None,
                        "parent": None,
                        "next_plans": [],
                        "depends_on": [],
                        "queue_activation": "not-a-carrier",
                        "followups_out": [],
                        "canon_updates": [],
                    }
                },
                ensure_ascii=False,
                indent=2,
            ),
            "missing_required": self._meta_with_queue_activation({}),
            "invalid_enum": self._meta_with_queue_activation("bogus_state"),
            "unapproved_enum": self._meta_with_queue_activation("not_requested"),
        }
        for case_name, meta_json in invalid_cases.items():
            with self.subTest(case_name=case_name), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                (root / ".git").mkdir()
                self._write_plan_vocab(root)
                plan_rel = f"docs/plans/260614_1720_{case_name}.md"
                self._write_plan(root, plan_rel, status="Architect initial draft", meta_json=meta_json)
                paths = self._queue_paths(root)

                with self.assertRaisesRegex(MODULE.QueueError, "queue_activation_admission_blocked"):
                    MODULE.set_queue(paths, plans=[plan_rel], now="2026-06-14T14:21:00Z")

                self.assertFalse(paths.state_path.exists())
                self.assertFalse(paths.log_path.exists())

    def test_explicit_queue_rejects_pending_queue_activation_on_architect_draft(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            self._write_plan_vocab(root)
            plan_rel = "docs/plans/260614_1723_pending_activation_draft.md"
            self._write_plan(
                root,
                plan_rel,
                status="Architect draft",
                meta_json=self._meta_with_queue_activation("not_requested"),
            )
            paths = self._queue_paths(root)

            with self.assertRaisesRegex(MODULE.QueueError, "queue_activation_admission_blocked"):
                MODULE.set_queue(paths, plans=[plan_rel], now="2026-06-14T14:23:30Z")

            self.assertFalse(paths.state_path.exists())
            self.assertFalse(paths.log_path.exists())

    def test_explicit_queue_rejects_malformed_queue_activation_on_architect_draft(self) -> None:
        invalid_cases: dict[str, str] = {
            "null": self._meta_with_queue_activation(None),
            "non_object": json.dumps(
                {
                    "plan_meta": {
                        "cluster": "process",
                        "tags": [],
                        "phase_overlay": None,
                        "phase_state": None,
                        "parent": None,
                        "next_plans": [],
                        "depends_on": [],
                        "queue_activation": "not-a-carrier",
                        "followups_out": [],
                        "canon_updates": [],
                    }
                },
                ensure_ascii=False,
                indent=2,
            ),
            "missing_required": self._meta_with_queue_activation({}),
            "invalid_enum": self._meta_with_queue_activation("bogus_state"),
        }
        for case_name, meta_json in invalid_cases.items():
            with self.subTest(case_name=case_name), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                (root / ".git").mkdir()
                self._write_plan_vocab(root)
                plan_rel = f"docs/plans/260614_1724_architect_draft_{case_name}.md"
                self._write_plan(root, plan_rel, status="Architect draft", meta_json=meta_json)
                paths = self._queue_paths(root)

                with self.assertRaisesRegex(MODULE.QueueError, "queue_activation_admission_blocked"):
                    MODULE.set_queue(paths, plans=[plan_rel], now="2026-06-14T14:23:40Z")

                self.assertFalse(paths.state_path.exists())
                self.assertFalse(paths.log_path.exists())

    def test_explicit_queue_rejects_approved_activation_with_child_queue_and_empty_next_plans(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            self._write_plan_vocab(root)
            child_rel = "docs/plans/260614_1726_child.md"
            parent_rel = "docs/plans/260614_1725_parent_missing_next_plans.md"
            self._write_plan(root, child_rel, status="Architect initial draft", meta_json=self._meta_with_queue_activation())
            self._write_plan(
                root,
                parent_rel,
                status="Ready for Planner",
                meta_json=self._meta_with_queue_activation("owner_approved"),
                execution_queue=dedent(
                    f"""\
                    - Resume parent: `owner-restamp-required`
                    - Plan: `{child_rel}`
                    """
                ).rstrip(),
            )
            paths = self._queue_paths(root)

            with self.assertRaisesRegex(MODULE.QueueError, "queue_activation_admission_blocked"):
                MODULE.set_queue(paths, plans=[parent_rel], now="2026-06-14T14:23:50Z")

            self.assertFalse(paths.state_path.exists())
            self.assertFalse(paths.log_path.exists())

    def test_set_queue_after_parent_resume_starts_fresh_pending_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            parent_rel = "docs/plans/260614_1727_parent.md"
            old_child_rel = "docs/plans/260614_1728_old_child.md"
            next_rel = "docs/plans/260614_1729_next_r1.md"
            self._write_plan(root, parent_rel)
            self._write_plan(root, old_child_rel, status="Done")
            self._write_plan(root, next_rel)
            paths = self._queue_paths(root)
            MODULE.set_queue(paths, plans=[old_child_rel], resume_parent="run-parent-once", now="2026-06-14T14:24:00Z")
            MODULE.activate_next(paths, now="2026-06-14T14:25:00Z")
            MODULE.advance_queue(paths, "Done", now="2026-06-14T14:26:00Z")
            state = MODULE.load_state(paths)
            assert state is not None
            state["parent_plan"] = parent_rel
            state["parent_resume_pending_at"] = "2026-06-14T14:27:00Z"
            MODULE.save_state(paths, state)
            MODULE.mark_planpath_override(paths, parent_rel, reason="queue_resume_parent")

            snapshot = MODULE.set_queue(paths, plans=[next_rel], now="2026-06-14T14:28:00Z")
            stored_state = MODULE.load_state(paths)

        assert stored_state is not None
        self.assertEqual(snapshot["effective_phase"], "pending_not_started")
        self.assertEqual(snapshot["pending_count"], 1)
        self.assertFalse(snapshot["queue_empty"])
        self.assertIsNone(stored_state["parent_resume_pending_at"])
        self.assertIsNone(stored_state["parent_resumed_at"])
        self.assertIsNone(stored_state["last_transition"])

    def test_set_queue_after_parent_resume_from_umbrella_starts_new_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            umbrella_rel = "docs/plans/260614_1730_umbrella.md"
            old_child_rel = "docs/plans/260614_1731_old_child.md"
            next_child_rel = "docs/plans/260614_1732_next_child.md"
            self._write_plan(root, old_child_rel, status="Done")
            self._write_plan(root, next_child_rel)
            umbrella = self._write_plan(
                root,
                umbrella_rel,
                execution_queue=dedent(
                    f"""\
                    - Resume parent: `run-parent-once`
                    - Plan: `{old_child_rel}`
                    """
                ).rstrip(),
            )
            paths = self._queue_paths(root)
            MODULE.set_queue(paths, umbrella=str(umbrella), now="2026-06-14T14:30:00Z")
            MODULE.activate_next(paths, now="2026-06-14T14:31:00Z")
            child_done = MODULE.advance_queue(paths, "Done", now="2026-06-14T14:32:00Z")
            parent_done = MODULE.mark_planpath_override(paths, umbrella_rel, reason="queue_resume_parent")

            snapshot = MODULE.set_queue(paths, plans=[next_child_rel], now="2026-06-14T14:33:00Z")
            stored_state = MODULE.load_state(paths)

        assert stored_state is not None
        self.assertFalse(child_done["queue_complete"])
        self.assertEqual(child_done["resume_parent_plan"], umbrella_rel)
        self.assertTrue(parent_done["last_transition"]["queue_complete"])
        self.assertEqual(snapshot["effective_phase"], "pending_not_started")
        self.assertEqual(snapshot["pending_count"], 1)
        self.assertFalse(snapshot["queue_empty"])
        self.assertIsNone(snapshot["parent_resumed_at"])
        self.assertEqual(snapshot["last_transition"], {})
        self.assertIsNone(stored_state["parent_resume_pending_at"])
        self.assertIsNone(stored_state["parent_resumed_at"])
        self.assertIsNone(stored_state["last_transition"])

    def test_architect_initial_draft_queue_activation_accepts_manifest_backed_approved_states(self) -> None:
        for state in ("owner_approved", "architect_approved"):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                (root / ".git").mkdir()
                self._write_plan_vocab(root)
                plan_rel = f"docs/plans/260614_1721_{state}.md"
                self._write_plan(
                    root,
                    plan_rel,
                    status="Architect initial draft",
                    meta_json=self._meta_with_queue_activation(state),
                )
                paths = self._queue_paths(root)

                snapshot = MODULE.set_queue(paths, plans=[plan_rel], now="2026-06-14T14:22:00Z")

                self.assertEqual(snapshot["items"][0]["plan"], plan_rel)
                self.assertNotIn("queue_activation_warning", snapshot["items"][0])
                self.assertIn("\tset\t", paths.log_path.read_text(encoding="utf-8"))

    def test_architect_initial_draft_queue_activation_fails_closed_when_manifest_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            plan_rel = "docs/plans/260614_1722_no_manifest.md"
            self._write_plan(
                root,
                plan_rel,
                status="Architect initial draft",
                meta_json=self._meta_with_queue_activation("architect_approved"),
            )
            paths = self._queue_paths(root)

            with self.assertRaisesRegex(MODULE.QueueError, "manifest_missing_or_malformed"):
                MODULE.set_queue(paths, plans=[plan_rel], now="2026-06-14T14:23:00Z")

            self.assertFalse(paths.state_path.exists())
            self.assertFalse(paths.log_path.exists())

    def test_append_rejects_invalid_queue_activation_without_mutating_existing_state_or_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            self._write_plan_vocab(root)
            existing_rel = "docs/plans/260614_1730_existing.md"
            invalid_rel = "docs/plans/260614_1731_invalid_activation.md"
            self._write_plan(root, existing_rel)
            self._write_plan(root, invalid_rel, status="Architect initial draft")
            paths = self._queue_paths(root)
            MODULE.set_queue(paths, plans=[existing_rel], now="2026-06-14T14:24:00Z")
            state_before = paths.state_path.read_text(encoding="utf-8")
            log_before = paths.log_path.read_text(encoding="utf-8")

            with self.assertRaisesRegex(MODULE.QueueError, "queue_activation_admission_blocked"):
                MODULE.append_queue(paths, [invalid_rel], now="2026-06-14T14:25:00Z")

            self.assertEqual(paths.state_path.read_text(encoding="utf-8"), state_before)
            self.assertEqual(paths.log_path.read_text(encoding="utf-8"), log_before)

    def test_activate_next_rejects_legacy_invalid_queue_activation_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            self._write_plan_vocab(root)
            invalid_rel = "docs/plans/260614_1732_legacy_invalid_activation.md"
            self._write_plan(root, invalid_rel, status="Architect initial draft")
            paths = self._queue_paths(root)
            legacy_state = {
                "version": 1,
                "mode": "manual_args",
                "source_plan": None,
                "parent_plan": None,
                "resume_parent": "none",
                "created_at": "2026-06-14T14:26:00Z",
                "updated_at": "2026-06-14T14:26:00Z",
                "cursor": 0,
                "parent_resume_pending_at": None,
                "parent_resumed_at": None,
                "last_stop": None,
                "last_transition": None,
                "last_planpath_override": None,
                "items": [
                    {
                        "order": 1,
                        "plan": invalid_rel,
                        "source": "legacy_warning_only",
                        "state": "pending",
                        "added_at": "2026-06-14T14:26:00Z",
                        "activated_at": None,
                        "completed_at": None,
                        "final_status": None,
                        "runtime_class": None,
                        "closeout_kind": None,
                        "closeout_reason": None,
                        "queue_activation_warning": "legacy warning",
                    }
                ],
            }
            MODULE.save_state(paths, legacy_state)
            paths.log_path.write_text("2026-06-14T14:26:00Z\tset\tmode=legacy\n", encoding="utf-8")
            state_before = paths.state_path.read_text(encoding="utf-8")
            log_before = paths.log_path.read_text(encoding="utf-8")

            with self.assertRaisesRegex(MODULE.QueueError, "queue_activation_admission_blocked"):
                MODULE.activate_next(paths, now="2026-06-14T14:27:00Z")

            self._plan_lint_runner.assert_not_called()
            self.assertEqual(paths.state_path.read_text(encoding="utf-8"), state_before)
            self.assertEqual(paths.log_path.read_text(encoding="utf-8"), log_before)

    def test_show_suppresses_stale_queue_activation_warning_when_plan_is_now_valid(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            self._write_plan_vocab(root)
            plan_rel = "docs/plans/260614_1740_restamped_valid_activation.md"
            self._write_plan(
                root,
                plan_rel,
                status="Architect arch review",
                meta_json=self._meta_with_queue_activation("owner_approved"),
            )
            paths = self._queue_paths(root)
            state = MODULE.build_state(
                mode="manual_args",
                items=[
                    {
                        "order": 1,
                        "plan": plan_rel,
                        "source": "legacy_warning_only",
                        "state": "active",
                        "added_at": "2026-06-14T14:40:00Z",
                        "activated_at": "2026-06-14T14:41:00Z",
                        "completed_at": None,
                        "final_status": None,
                        "runtime_class": None,
                        "closeout_kind": None,
                        "closeout_reason": None,
                        "queue_activation_warning": "missing_or_invalid queue_activation.state for Architect initial draft",
                    }
                ],
                now="2026-06-14T14:40:00Z",
            )
            MODULE.save_state(paths, state)
            state_before = paths.state_path.read_text(encoding="utf-8")

            snapshot = MODULE.queue_snapshot(MODULE.load_state(paths), paths)
            rendered = MODULE.render_snapshot(snapshot)

            self.assertNotIn("queue_activation_warning", snapshot["items"][0])
            self.assertNotIn("queue_activation_warning", rendered)
            self.assertEqual(paths.state_path.read_text(encoding="utf-8"), state_before)

    def test_queue_activation_warning_ignores_na_execution_queue_plan_placeholder(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            self._write_plan_vocab(root)
            plan_rel = "docs/plans/260614_1741_done_ordinary_child.md"
            plan_path = self._write_plan(
                root,
                plan_rel,
                status="Done",
                meta_json=self._meta_with_queue_activation("architect_approved"),
                execution_queue=dedent(
                    """\
                    - Resume parent: `N/A (why=ordinary child plan)`
                    - Plan: `N/A (why=ordinary child plan)`
                    """
                ).strip(),
            )
            paths = self._queue_paths(root)
            state = MODULE.build_state(
                mode="manual_args",
                items=[
                    {
                        "order": 1,
                        "plan": plan_rel,
                        "source": "legacy_done_child",
                        "state": "done",
                        "added_at": "2026-06-14T14:40:00Z",
                        "activated_at": "2026-06-14T14:41:00Z",
                        "completed_at": "2026-06-14T14:42:00Z",
                        "final_status": "Done",
                        "runtime_class": None,
                        "closeout_kind": "terminal_status",
                        "closeout_reason": "fixture",
                    }
                ],
                now="2026-06-14T14:40:00Z",
            )

            execution_plans, resume_parent = MODULE.parse_execution_queue(plan_path.read_text(encoding="utf-8"))
            snapshot = MODULE.queue_snapshot(state, paths)
            rendered = MODULE.render_snapshot(snapshot)

            self.assertEqual(execution_plans, [])
            self.assertEqual(resume_parent, "none")
            self.assertIsNone(MODULE.queue_activation_import_warning(root, plan_rel))
            self.assertNotIn("queue_activation_warning", snapshot["items"][0])
            self.assertNotIn("queue_activation_warning", rendered)

    def test_advance_rejects_invalid_next_queue_activation_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            self._write_plan_vocab(root)
            active_rel = "docs/plans/260614_1737_active_before_invalid.md"
            invalid_rel = "docs/plans/260614_1738_invalid_auto_advance_activation.md"
            self._write_plan(root, active_rel, status="Done")
            self._write_plan(root, invalid_rel, status="Architect initial draft")
            paths = self._queue_paths(root)
            self._save_active_pending_queue(paths, active_rel=active_rel, pending_rels=[invalid_rel])
            state_before = paths.state_path.read_text(encoding="utf-8")
            log_before = paths.log_path.read_text(encoding="utf-8")

            with self.assertRaisesRegex(MODULE.QueueError, "queue_activation_admission_blocked"):
                MODULE.advance_queue(paths, "Done", now="2026-06-14T14:41:00Z")

            self.assertEqual(paths.state_path.read_text(encoding="utf-8"), state_before)
            self.assertEqual(paths.log_path.read_text(encoding="utf-8"), log_before)

    def test_activate_next_rejects_same_queue_dependency_that_is_not_finalized(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            dependency_rel = "docs/plans/260614_1710_e3_dependency.md"
            dependent_rel = "docs/plans/260614_1711_e4_dependent.md"
            self._write_plan(root, dependency_rel)
            self._write_plan(
                root,
                dependent_rel,
                meta_json=dedent(
                    f"""\
                    {{
                      "plan_meta": {{
                        "cluster": "process",
                        "tags": [],
                        "phase_overlay": null,
                        "phase_state": null,
                        "parent": null,
                        "next_plans": [],
                        "depends_on": ["{dependency_rel}"],
                        "followups_out": [],
                        "canon_updates": []
                      }}
                    }}
                    """
                ).strip(),
            )
            paths = self._queue_paths(root)
            MODULE.set_queue(
                paths,
                plans=[dependent_rel, dependency_rel],
                now="2026-06-14T14:25:00Z",
            )

            with self.assertRaisesRegex(MODULE.QueueError, "queue_dependency_blocked"):
                MODULE.activate_next(paths, now="2026-06-14T14:26:00Z")

            self._plan_lint_runner.assert_not_called()

    def test_closeout_rejects_same_queue_dependency_for_next_item_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            active_rel = "docs/plans/260614_1739_done_before_blocked_dependency.md"
            dependent_rel = "docs/plans/260614_1740_dependent_auto_advance_blocked.md"
            dependency_rel = "docs/plans/260614_1741_unfinished_dependency.md"
            self._write_plan(root, active_rel, status="Done")
            self._write_plan(root, dependency_rel)
            self._write_plan(
                root,
                dependent_rel,
                meta_json=dedent(
                    f"""\
                    {{
                      "plan_meta": {{
                        "cluster": "process",
                        "tags": [],
                        "phase_overlay": null,
                        "phase_state": null,
                        "parent": null,
                        "next_plans": [],
                        "required_manager_mode": "either",
                        "depends_on": ["{dependency_rel}"],
                        "followups_out": [],
                        "canon_updates": []
                      }}
                    }}
                    """
                ).strip(),
            )
            paths = self._queue_paths(root)
            self._save_active_pending_queue(
                paths,
                active_rel=active_rel,
                pending_rels=[dependent_rel, dependency_rel],
                now="2026-06-14T14:42:00Z",
            )
            state_before = paths.state_path.read_text(encoding="utf-8")
            log_before = paths.log_path.read_text(encoding="utf-8")

            with self.assertRaisesRegex(MODULE.QueueError, "queue_dependency_blocked"):
                MODULE.closeout_queue(
                    paths,
                    manager_mode="manager-collab",
                    now="2026-06-14T14:43:00Z",
                )

            self.assertEqual(paths.state_path.read_text(encoding="utf-8"), state_before)
            self.assertEqual(paths.log_path.read_text(encoding="utf-8"), log_before)

    def test_activate_next_allows_same_queue_dependency_that_is_finalized(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            dependency_rel = "docs/plans/260614_1712_e3_dependency_done.md"
            dependent_rel = "docs/plans/260614_1713_e4_dependent_ready.md"
            self._write_plan(root, dependency_rel, status="Done")
            self._write_plan(
                root,
                dependent_rel,
                meta_json=dedent(
                    f"""\
                    {{
                      "plan_meta": {{
                        "cluster": "process",
                        "tags": [],
                        "phase_overlay": null,
                        "phase_state": null,
                        "parent": null,
                        "next_plans": [],
                        "depends_on": ["{dependency_rel}"],
                        "followups_out": [],
                        "canon_updates": []
                      }}
                    }}
                    """
                ).strip(),
            )
            paths = self._queue_paths(root)
            MODULE.set_queue(
                paths,
                plans=[dependency_rel, dependent_rel],
                now="2026-06-14T14:28:00Z",
            )
            MODULE.activate_next(paths, now="2026-06-14T14:29:00Z")
            advanced = MODULE.advance_queue(paths, "Done", now="2026-06-14T14:30:00Z")

            activated = MODULE.activate_next(paths, now="2026-06-14T14:31:00Z")

        self.assertEqual(advanced["next_plan"], dependent_rel)
        self.assertFalse(activated["activated"])
        self.assertEqual(activated["active_plan"], dependent_rel)

    def test_activate_next_ignores_dependency_not_present_in_same_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            external_dependency = "docs/plans/260614_1714_external_dependency.md"
            dependent_rel = "docs/plans/260614_1715_dependent_with_external_dependency.md"
            self._write_plan(
                root,
                dependent_rel,
                meta_json=dedent(
                    f"""\
                    {{
                      "plan_meta": {{
                        "cluster": "process",
                        "tags": [],
                        "phase_overlay": null,
                        "phase_state": null,
                        "parent": null,
                        "next_plans": [],
                        "depends_on": ["{external_dependency}"],
                        "followups_out": [],
                        "canon_updates": []
                      }}
                    }}
                    """
                ).strip(),
            )
            paths = self._queue_paths(root)
            MODULE.set_queue(paths, plans=[dependent_rel], now="2026-06-14T14:32:00Z")

            activated = MODULE.activate_next(paths, now="2026-06-14T14:33:00Z")

        self.assertTrue(activated["activated"])
        self.assertEqual(activated["active_plan"], dependent_rel)

    def test_activate_next_blocks_fresh_lint_error_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            plan_rel = "docs/plans/260805_1730_fresh_lint_red.md"
            self._write_plan(root, plan_rel)
            paths = self._queue_paths(root)
            MODULE.set_queue(paths, plans=[plan_rel], now="2026-08-05T14:30:00Z")
            before = self._queue_bytes_snapshot(paths)
            self._plan_lint_runner.return_value = [
                self._lint_finding(root, plan_rel, 41, "ERROR", "fresh plan failure"),
            ]

            with self.assertRaisesRegex(MODULE.QueueError, r"^plan_lint_activation_blocked: errors=1"):
                MODULE.activate_next(paths, now="2026-08-05T14:31:00Z")

            self._assert_queue_bytes_snapshot(paths, before)
            self.assertEqual(
                self._plan_lint_vocab_loader.call_args_list,
                [mock.call(root / "docs/_meta/plan_vocab.json")],
            )
            self.assertEqual(self._plan_lint_runner.call_args_list, [mock.call(root / plan_rel, context=mock.ANY)])

    def test_auto_activation_blocks_fresh_lint_error_without_mutation(self) -> None:
        for operation in ("advance", "closeout"):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                (root / ".git").mkdir()
                active_rel = f"docs/plans/260805_1731_{operation}_active.md"
                pending_rel = f"docs/plans/260805_1732_{operation}_pending.md"
                self._write_plan(root, active_rel, status="Done", meta_json=self._manager_mode_meta("either"))
                self._write_plan(root, pending_rel, meta_json=self._manager_mode_meta("either"))
                paths = self._queue_paths(root)
                self._save_active_pending_queue(paths, active_rel=active_rel, pending_rels=[pending_rel])
                before = self._queue_bytes_snapshot(paths)
                self._plan_lint_vocab_loader.reset_mock()
                self._plan_lint_runner.reset_mock()
                self._plan_lint_runner.return_value = [
                    self._lint_finding(root, pending_rel, 42, "ERROR", "fresh next failure"),
                ]

                with self.assertRaisesRegex(MODULE.QueueError, r"^plan_lint_activation_blocked: errors=1"):
                    if operation == "advance":
                        MODULE.advance_queue(paths, "Done", now="2026-08-05T14:32:00Z")
                    else:
                        MODULE.closeout_queue(
                            paths,
                            manager_mode="manager-collab",
                            now="2026-08-05T14:32:00Z",
                        )

                self._assert_queue_bytes_snapshot(paths, before)
                state = MODULE.load_state(paths)
                assert state is not None
                self.assertEqual([item["state"] for item in state["items"]], ["active", "pending"])
                self.assertEqual(
                    self._plan_lint_runner.call_args_list,
                    [mock.call(root / pending_rel, context=mock.ANY)],
                )

    def test_manager_mode_candidate_read_failures_reroute_to_fresh_lint_without_mutation(self) -> None:
        for operation in ("direct", "advance", "closeout"):
            for failure in ("missing", "permission"):
                with self.subTest(operation=operation, failure=failure), tempfile.TemporaryDirectory() as tmpdir:
                    root = Path(tmpdir)
                    (root / ".git").mkdir()
                    candidate_rel = f"docs/plans/260805_1733_{operation}_{failure}_pending.md"
                    candidate_path = root / candidate_rel
                    self._write_plan(root, candidate_rel, meta_json=self._manager_mode_meta("manager-collab"))
                    paths = self._queue_paths(root)
                    if operation == "direct":
                        MODULE.set_queue(paths, plans=[candidate_rel], now="2026-08-05T14:33:00Z")
                    else:
                        active_rel = f"docs/plans/260805_1733_{operation}_{failure}_active.md"
                        self._write_plan(
                            root,
                            active_rel,
                            status="Done",
                            meta_json=self._manager_mode_meta("either"),
                        )
                        self._save_active_pending_queue(paths, active_rel=active_rel, pending_rels=[candidate_rel])
                    before = self._queue_bytes_snapshot(paths)
                    self._plan_lint_vocab_loader.reset_mock()
                    self._plan_lint_runner.reset_mock()
                    self._plan_lint_runner.side_effect = OSError(
                        "/private/secret/fresh-lint-read-failure.md"
                    )

                    def invoke() -> None:
                        if operation == "direct":
                            MODULE.activate_next(
                                paths,
                                manager_mode="manager-collab",
                                now="2026-08-05T14:34:00Z",
                            )
                        elif operation == "advance":
                            MODULE.advance_queue(
                                paths,
                                "Done",
                                manager_mode="manager-collab",
                                now="2026-08-05T14:34:00Z",
                            )
                        else:
                            MODULE.closeout_queue(
                                paths,
                                manager_mode="manager-collab",
                                now="2026-08-05T14:34:00Z",
                            )

                    candidate_reads = 0
                    original_read_text = Path.read_text

                    def fail_manager_mode_candidate_read(path: Path, *args: object, **kwargs: object) -> str:
                        nonlocal candidate_reads
                        if path == candidate_path:
                            candidate_reads += 1
                            if candidate_reads == 4:
                                raise PermissionError("/private/secret/manager-mode.md")
                        return original_read_text(path, *args, **kwargs)

                    if failure == "missing":
                        candidate_path.unlink()

                    with self.assertRaisesRegex(
                        MODULE.QueueError,
                        r"^plan_lint_activation_blocked: lint_failed$",
                    ) as raised:
                        if failure == "permission":
                            with mock.patch.object(Path, "read_text", new=fail_manager_mode_candidate_read):
                                invoke()
                        else:
                            invoke()

                    self.assertIsNone(raised.exception.payload)
                    self.assertNotIn("manager_mode_admission_carrier_error", str(raised.exception))
                    self.assertNotIn("/private/secret", str(raised.exception))
                    self._assert_queue_bytes_snapshot(paths, before)
                    state = MODULE.load_state(paths)
                    assert state is not None
                    expected_states = ["pending"] if operation == "direct" else ["active", "pending"]
                    self.assertEqual([item["state"] for item in state["items"]], expected_states)
                    self.assertEqual(
                        self._plan_lint_vocab_loader.call_args_list,
                        [mock.call(root / "docs/_meta/plan_vocab.json")],
                    )
                    self.assertEqual(
                        self._plan_lint_runner.call_args_list,
                        [mock.call(candidate_path, context=mock.ANY)],
                    )
                    if failure == "permission":
                        self.assertEqual(candidate_reads, 4)

    def test_activation_lint_keeps_manager_skips_in_memory_on_red_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            active_rel = "docs/plans/260805_1733_active.md"
            incompatible_rel = "docs/plans/260805_1734_incompatible.md"
            compatible_rel = "docs/plans/260805_1735_compatible_red.md"
            self._write_plan(root, active_rel, status="Done", meta_json=self._manager_mode_meta("either"))
            self._write_plan(root, incompatible_rel, meta_json=self._manager_mode_meta("manager-custom-pipeline"))
            self._write_plan(root, compatible_rel, meta_json=self._manager_mode_meta("manager-collab"))
            paths = self._queue_paths(root)
            self._save_active_pending_queue(
                paths,
                active_rel=active_rel,
                pending_rels=[incompatible_rel, compatible_rel],
            )
            before = self._queue_bytes_snapshot(paths)
            self._plan_lint_runner.return_value = [
                self._lint_finding(root, compatible_rel, 43, "ERROR", "fresh compatible failure"),
            ]

            with self.assertRaisesRegex(MODULE.QueueError, r"^plan_lint_activation_blocked: errors=1"):
                MODULE.advance_queue(
                    paths,
                    "Done",
                    manager_mode="manager-collab",
                    now="2026-08-05T14:33:00Z",
                )

            self._assert_queue_bytes_snapshot(paths, before)
            state = MODULE.load_state(paths)
            assert state is not None
            self.assertEqual([item["state"] for item in state["items"]], ["active", "pending", "pending"])
            self.assertEqual(
                self._plan_lint_runner.call_args_list,
                [mock.call(root / compatible_rel, context=mock.ANY)],
            )
            self.assertNotIn("skip_manager_mode", [entry["event"] for entry in MODULE.parse_log_entries(paths)])

    def test_resume_parent_closeout_does_not_invoke_fresh_lint(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            paths, active_rel, parent_rel = self._prepare_mode_closeout_queue(
                root,
                candidate_kind="resume_parent_plan",
                candidate_meta=self._manager_mode_meta("either"),
            )
            self._plan_lint_vocab_loader.reset_mock()
            self._plan_lint_runner.reset_mock()

            closeout = MODULE.closeout_queue(
                paths,
                manager_mode="manager-collab",
                now="2026-08-05T14:33:30Z",
            )

        self.assertTrue(closeout["advanced"])
        self.assertEqual(closeout["finalized_plan"], active_rel)
        self.assertEqual(closeout["resume_parent_plan"], parent_rel)
        self._plan_lint_vocab_loader.assert_not_called()
        self._plan_lint_runner.assert_not_called()

    def test_activation_lint_detects_linked_carrier_drift_after_collection(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            plan_rel = "docs/plans/260805_1736_linked_carrier_drift.md"
            self._write_plan(root, plan_rel)
            draft_path = self._write_code_draft(root, plan_rel, target_paths=["scripts/plan_queue.py"])
            paths = self._queue_paths(root)
            MODULE.set_queue(paths, plans=[plan_rel], now="2026-08-05T14:34:00Z")
            draft_path.write_text("# Code draft: changed after collection\n", encoding="utf-8")
            before = self._queue_bytes_snapshot(paths)
            self._plan_lint_runner.return_value = [
                MODULE.plan_lint.Finding(draft_path, 7, "ERROR", "linked carrier drift"),
            ]

            with self.assertRaisesRegex(MODULE.QueueError, r"linked carrier drift") as raised:
                MODULE.activate_next(paths, now="2026-08-05T14:35:00Z")

            self.assertIn("docs/code_drafts/", str(raised.exception))
            self._assert_queue_bytes_snapshot(paths, before)

    def test_activation_lint_allows_warnings_and_reloads_each_target_root(self) -> None:
        roots: list[tuple[Path, str, MODULE.QueuePaths]] = []
        canonical_vocab_path = MODULE_PATH.parent.parent / "docs/_meta/plan_vocab.json"
        vocab_bytes = canonical_vocab_path.read_bytes()
        baseline_vocab = REAL_PLAN_LINT_VOCAB_LOADER(canonical_vocab_path)
        with (
            tempfile.TemporaryDirectory() as first_tmpdir,
            tempfile.TemporaryDirectory() as second_tmpdir,
            tempfile.TemporaryDirectory() as foreign_tmpdir,
        ):
            foreign_root = Path(foreign_tmpdir)
            (foreign_root / ".git").mkdir()
            foreign_vocab = foreign_root / "docs/_meta/plan_vocab.json"
            foreign_vocab.parent.mkdir(parents=True)
            foreign_payload = json.loads(vocab_bytes)
            foreign_payload["clusters"] = {
                "canonical": ["foreign-fixture-cluster"],
                "deprecated_aliases": {},
            }
            foreign_vocab.write_text(json.dumps(foreign_payload), encoding="utf-8")
            foreign_config = REAL_PLAN_LINT_VOCAB_LOADER(foreign_vocab)
            MODULE.plan_lint.apply_plan_vocab(foreign_config)
            self.addCleanup(MODULE.plan_lint.apply_plan_vocab, baseline_vocab)
            for index, tmpdir in enumerate((first_tmpdir, second_tmpdir), start=1):
                root = Path(tmpdir)
                (root / ".git").mkdir()
                vocab_path = root / "docs/_meta/plan_vocab.json"
                vocab_path.parent.mkdir(parents=True)
                vocab_path.write_bytes(vocab_bytes)
                plan_rel = f"docs/plans/260805_173{6 + index}_warn_{index}.md"
                self._write_plan(root, plan_rel)
                paths = self._queue_paths(root)
                MODULE.set_queue(paths, plans=[plan_rel], now=f"2026-08-05T14:3{5 + index}:00Z")
                roots.append((root, plan_rel, paths))
            self._plan_lint_vocab_loader.side_effect = REAL_PLAN_LINT_VOCAB_LOADER
            self._plan_lint_runner.return_value = [
                self._lint_finding(roots[0][0], roots[0][1], 9, "WARN", "advisory only"),
            ]

            for index, (_root, _plan_rel, paths) in enumerate(roots, start=1):
                activated = MODULE.activate_next(paths, now=f"2026-08-05T14:4{index}:00Z")
                self.assertTrue(activated["activated"])
                self.assertNotIn("plan_lint", [entry["event"] for entry in MODULE.parse_log_entries(paths)])

            self.assertEqual(MODULE.plan_lint.ALLOWED_CLUSTERS, foreign_config["canonical_clusters"])

        self.assertEqual(
            self._plan_lint_vocab_loader.call_args_list,
            [mock.call(root / "docs/_meta/plan_vocab.json") for root, _plan_rel, _paths in roots],
        )
        self.assertEqual(
            self._plan_lint_runner.call_args_list,
            [mock.call(root / plan_rel, context=mock.ANY) for root, plan_rel, _paths in roots],
        )

    def test_activation_lint_fails_closed_for_root_vocab_and_lint_failures(self) -> None:
        cases = ("foreign_root", "missing_vocab", "malformed_vocab", "lint_failure")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                (root / ".git").mkdir()
                plan_rel = f"docs/plans/260805_1740_{case}.md"
                self._write_plan(root, plan_rel)
                paths = self._queue_paths(root)
                MODULE.set_queue(paths, plans=[plan_rel], now="2026-08-05T14:45:00Z")
                before = self._queue_bytes_snapshot(paths)
                self._plan_lint_vocab_loader.reset_mock()
                self._plan_lint_runner.reset_mock()
                self._plan_lint_vocab_loader.side_effect = None
                self._plan_lint_vocab_loader.return_value = None
                self._plan_lint_runner.side_effect = None
                self._plan_lint_runner.return_value = []
                if case in {"missing_vocab", "malformed_vocab"}:
                    self._plan_lint_vocab_loader.side_effect = REAL_PLAN_LINT_VOCAB_LOADER
                    if case == "malformed_vocab":
                        vocab_path = root / "docs/_meta/plan_vocab.json"
                        vocab_path.parent.mkdir(parents=True)
                        vocab_path.write_text("{\n", encoding="utf-8")
                elif case == "lint_failure":
                    (root / plan_rel).unlink()
                    self._plan_lint_runner.side_effect = OSError("/private/secret/unreadable_plan.md")

                if case == "foreign_root":
                    with mock.patch.dict(MODULE.os.environ, {"PLANVEYOR_PROJECT_ROOT": str(root / "foreign-root")}):
                        with self.assertRaisesRegex(MODULE.QueueError, r"^plan_lint_activation_blocked:") as raised:
                            MODULE.activate_next(paths, now="2026-08-05T14:46:00Z")
                else:
                    with self.assertRaisesRegex(MODULE.QueueError, r"^plan_lint_activation_blocked:") as raised:
                        MODULE.activate_next(paths, now="2026-08-05T14:46:00Z")

                self.assertNotIn("/private/secret", str(raised.exception))
                self._assert_queue_bytes_snapshot(paths, before)
                if case in {"foreign_root", "missing_vocab", "malformed_vocab"}:
                    self._plan_lint_runner.assert_not_called()
                if case == "foreign_root":
                    self._plan_lint_vocab_loader.assert_not_called()

    def test_activation_lint_renders_only_bounded_sanitized_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            plan_rel = "docs/plans/260805_1741_bounded_renderer.md"
            self._write_plan(root, plan_rel)
            paths = self._queue_paths(root)
            MODULE.set_queue(paths, plans=[plan_rel], now="2026-08-05T14:47:00Z")
            errors = [
                self._lint_finding(
                    root,
                    f"docs/plans/{index:02d}.md",
                    index + 1,
                    "ERROR",
                    f"message-{index}" + ("\n/private/secret\x1f" if index == 3 else ""),
                )
                for index in reversed(range(12))
            ]
            self._plan_lint_runner.return_value = [
                *errors,
                self._lint_finding(root, "docs/plans/warn.md", 1, "WARN", "warning must not render"),
            ]

            with self.assertRaisesRegex(MODULE.QueueError, r"^plan_lint_activation_blocked: errors=12") as raised:
                MODULE.activate_next(paths, now="2026-08-05T14:48:00Z")

        rendered = str(raised.exception)
        self.assertIn("omitted=2", rendered)
        self.assertNotIn("/private/secret", rendered)
        self.assertNotIn("\n", rendered)
        self.assertNotIn("\x1f", rendered)
        self.assertNotIn("warning must not render", rendered)
        positions = [rendered.index(f"docs/plans/{index:02d}.md:{index + 1}:") for index in range(10)]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("docs/plans/10.md", rendered)
        self.assertNotIn("docs/plans/11.md", rendered)

    def test_activate_next_fails_closed_for_missing_external_blocking_dependency_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            missing_rel = "docs/plans/260614_1716_missing_external_outcome.md"
            dependent_rel = "docs/plans/260614_1717_blocked_by_missing_external_outcome.md"
            self._write_plan(
                root,
                dependent_rel,
                meta_json=self._blocking_dependency_meta(
                    depends_on=[missing_rel],
                    blocking_depends_on=[missing_rel],
                ),
            )
            paths = self._queue_paths(root)
            MODULE.set_queue(paths, plans=[dependent_rel], now="2026-06-14T14:34:00Z")
            state_before = paths.state_path.read_text(encoding="utf-8")
            log_before = paths.log_path.read_text(encoding="utf-8")

            with self.assertRaisesRegex(MODULE.QueueError, "blocking_depends_on_oracle_error") as raised:
                MODULE.activate_next(paths, now="2026-06-14T14:35:00Z")

            self.assertIn(missing_rel, str(raised.exception))
            self._plan_lint_runner.assert_not_called()
            self.assertEqual(paths.state_path.read_text(encoding="utf-8"), state_before)
            self.assertEqual(paths.log_path.read_text(encoding="utf-8"), log_before)

    def test_activate_next_fails_closed_for_malformed_external_blocking_dependency_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            malformed_rel = "docs/plans/260614_1718_malformed_external_outcome.md"
            dependent_rel = "docs/plans/260614_1719_blocked_by_malformed_external_outcome.md"
            malformed_path = root / malformed_rel
            malformed_path.parent.mkdir(parents=True, exist_ok=True)
            malformed_path.write_text("# malformed target without a status header\n", encoding="utf-8")
            self._write_plan(
                root,
                dependent_rel,
                meta_json=self._blocking_dependency_meta(
                    depends_on=[malformed_rel],
                    blocking_depends_on=[malformed_rel],
                ),
            )
            paths = self._queue_paths(root)
            MODULE.set_queue(paths, plans=[dependent_rel], now="2026-06-14T14:36:00Z")
            state_before = paths.state_path.read_text(encoding="utf-8")
            log_before = paths.log_path.read_text(encoding="utf-8")

            with self.assertRaisesRegex(MODULE.QueueError, "blocking_depends_on_oracle_error") as raised:
                MODULE.activate_next(paths, now="2026-06-14T14:37:00Z")

            self.assertIn(malformed_rel, str(raised.exception))
            self.assertEqual(paths.state_path.read_text(encoding="utf-8"), state_before)
            self.assertEqual(paths.log_path.read_text(encoding="utf-8"), log_before)

    def test_activate_next_fails_closed_for_unreadable_external_blocking_dependency_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            unreadable_rel = "docs/plans/260614_1719_unreadable_external_outcome.md"
            dependent_rel = "docs/plans/260614_1719_blocked_by_unreadable_external_outcome.md"
            (root / unreadable_rel).mkdir(parents=True, exist_ok=True)
            self._write_plan(
                root,
                dependent_rel,
                meta_json=self._blocking_dependency_meta(
                    depends_on=[unreadable_rel],
                    blocking_depends_on=[unreadable_rel],
                ),
            )
            paths = self._queue_paths(root)
            MODULE.set_queue(paths, plans=[dependent_rel], now="2026-06-14T14:37:30Z")
            state_before = paths.state_path.read_text(encoding="utf-8")
            log_before = paths.log_path.read_text(encoding="utf-8")

            with self.assertRaisesRegex(MODULE.QueueError, "blocking_depends_on_oracle_error") as raised:
                MODULE.activate_next(paths, now="2026-06-14T14:37:31Z")

            self.assertIn(unreadable_rel, str(raised.exception))
            self.assertEqual(paths.state_path.read_text(encoding="utf-8"), state_before)
            self.assertEqual(paths.log_path.read_text(encoding="utf-8"), log_before)

    def test_activate_next_requires_exact_green_outcome_not_terminal_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            reference_rel = "docs/plans/260614_1720_terminal_reference_only.md"
            outcome_rel = "docs/plans/260614_1721_exact_green_promoted_outcome.md"
            blocked_rel = "docs/plans/260614_1722_reference_only_consumer.md"
            green_rel = "docs/plans/260614_1723_exact_outcome_consumer.md"
            self._write_plan(root, reference_rel, status="Superseded")
            self._write_plan(root, outcome_rel, status="Done")
            self._write_plan(
                root,
                blocked_rel,
                meta_json=self._blocking_dependency_meta(
                    depends_on=[reference_rel],
                    blocking_depends_on=[reference_rel],
                ),
            )
            self._write_plan(
                root,
                green_rel,
                meta_json=self._blocking_dependency_meta(
                    depends_on=[outcome_rel],
                    blocking_depends_on=[outcome_rel],
                ),
            )
            blocked_paths = self._queue_paths(root)
            MODULE.set_queue(blocked_paths, plans=[blocked_rel], now="2026-06-14T14:38:00Z")

            with self.assertRaisesRegex(MODULE.QueueError, "blocking_depends_on_delivery_blocked") as raised:
                MODULE.activate_next(blocked_paths, now="2026-06-14T14:39:00Z")

            self.assertIn(reference_rel, str(raised.exception))
            MODULE.clear_queue(blocked_paths)
            MODULE.set_queue(blocked_paths, plans=[green_rel], now="2026-06-14T14:40:00Z")
            activated = MODULE.activate_next(blocked_paths, now="2026-06-14T14:41:00Z")

        self.assertTrue(activated["activated"])
        self.assertEqual(activated["active_plan"], green_rel)

    def test_activate_next_checks_every_external_blocking_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            green_rel = "docs/plans/260614_1724_green_first_dependency.md"
            red_rel = "docs/plans/260614_1725_red_second_dependency.md"
            dependent_rel = "docs/plans/260614_1726_multiple_external_dependencies.md"
            self._write_plan(root, green_rel, status="Done")
            self._write_plan(root, red_rel, status="Ready for Coder")
            self._write_plan(
                root,
                dependent_rel,
                meta_json=self._blocking_dependency_meta(
                    depends_on=[green_rel, red_rel],
                    blocking_depends_on=[green_rel, red_rel],
                ),
            )
            paths = self._queue_paths(root)
            MODULE.set_queue(paths, plans=[dependent_rel], now="2026-06-14T14:42:00Z")

            with self.assertRaisesRegex(MODULE.QueueError, "blocking_depends_on_delivery_blocked") as raised:
                MODULE.activate_next(paths, now="2026-06-14T14:43:00Z")

        self.assertIn(red_rel, str(raised.exception))

    def test_closeout_fails_closed_for_external_blocking_dependency_before_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            active_rel = "docs/plans/260614_1727_active_done_before_hard_gate.md"
            red_rel = "docs/plans/260614_1728_external_red_outcome.md"
            dependent_rel = "docs/plans/260614_1729_hard_gate_auto_advance.md"
            self._write_plan(root, active_rel, status="Done")
            self._write_plan(root, red_rel, status="Ready for Coder")
            self._write_plan(
                root,
                dependent_rel,
                meta_json=self._blocking_dependency_meta(
                    depends_on=[red_rel],
                    blocking_depends_on=[red_rel],
                ),
            )
            paths = self._queue_paths(root)
            self._save_active_pending_queue(paths, active_rel=active_rel, pending_rels=[dependent_rel])
            state_before = paths.state_path.read_text(encoding="utf-8")
            log_before = paths.log_path.read_text(encoding="utf-8")

            with self.assertRaisesRegex(MODULE.QueueError, "blocking_depends_on_delivery_blocked") as raised:
                MODULE.closeout_queue(
                    paths,
                    manager_mode="manager-collab",
                    now="2026-06-14T14:44:00Z",
                )

            self.assertIn(red_rel, str(raised.exception))
            self.assertEqual(paths.state_path.read_text(encoding="utf-8"), state_before)
            self.assertEqual(paths.log_path.read_text(encoding="utf-8"), log_before)

    def test_advance_fails_closed_for_external_blocking_dependency_before_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            active_rel = "docs/plans/260614_1730_active_before_hard_advance_gate.md"
            red_rel = "docs/plans/260614_1731_external_red_advance_outcome.md"
            dependent_rel = "docs/plans/260614_1732_hard_gate_advance.md"
            self._write_plan(root, active_rel, status="Done")
            self._write_plan(root, red_rel, status="Ready for Coder")
            self._write_plan(
                root,
                dependent_rel,
                meta_json=self._blocking_dependency_meta(
                    depends_on=[red_rel],
                    blocking_depends_on=[red_rel],
                ),
            )
            paths = self._queue_paths(root)
            self._save_active_pending_queue(paths, active_rel=active_rel, pending_rels=[dependent_rel])
            state_before = paths.state_path.read_text(encoding="utf-8")
            log_before = paths.log_path.read_text(encoding="utf-8")

            with self.assertRaisesRegex(MODULE.QueueError, "blocking_depends_on_delivery_blocked") as raised:
                MODULE.advance_queue(paths, "Done", now="2026-06-14T14:47:00Z")

            self.assertIn(red_rel, str(raised.exception))
            self.assertEqual(paths.state_path.read_text(encoding="utf-8"), state_before)
            self.assertEqual(paths.log_path.read_text(encoding="utf-8"), log_before)

    def test_activate_next_rejects_invalid_blocking_dependency_carrier_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            dependency_rel = "docs/plans/260614_1733_green_but_invalid_carrier_target.md"
            dependent_rel = "docs/plans/260614_1734_invalid_hard_carrier.md"
            self._write_plan(root, dependency_rel, status="Done")
            self._write_plan(
                root,
                dependent_rel,
                meta_json=self._blocking_dependency_meta(
                    depends_on=[],
                    blocking_depends_on=[dependency_rel],
                ),
            )
            paths = self._queue_paths(root)
            MODULE.set_queue(paths, plans=[dependent_rel], now="2026-06-14T14:45:00Z")
            state_before = paths.state_path.read_text(encoding="utf-8")
            log_before = paths.log_path.read_text(encoding="utf-8")

            with self.assertRaisesRegex(MODULE.QueueError, "blocking_depends_on_invalid"):
                MODULE.activate_next(paths, now="2026-06-14T14:46:00Z")

            self.assertEqual(paths.state_path.read_text(encoding="utf-8"), state_before)
            self.assertEqual(paths.log_path.read_text(encoding="utf-8"), log_before)

    def test_activate_next_rejects_unterminated_carrier_bearing_json_fence_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            dependency_rel = "docs/plans/260614_1735_red_unterminated_carrier_target.md"
            dependent_rel = "docs/plans/260614_1736_unterminated_hard_carrier.md"
            self._write_plan(root, dependency_rel, status="Ready for Coder")
            dependent_path = self._write_plan(
                root,
                dependent_rel,
                meta_json=self._blocking_dependency_meta(
                    depends_on=[dependency_rel],
                    blocking_depends_on=[dependency_rel],
                ),
            )
            # The queue is seeded while the plan is still valid: collection-time
            # admission now fail-closes on malformed Meta (strict routing
            # reader), so the carrier fence is broken only after set_queue.
            paths = self._queue_paths(root)
            MODULE.set_queue(paths, plans=[dependent_rel], now="2026-06-14T14:46:30Z")

            original_text = dependent_path.read_text(encoding="utf-8")
            unterminated_text = original_text.replace(
                "\n```\n\n## Execution queue",
                "\n\n## Execution queue",
                1,
            )
            self.assertNotEqual(unterminated_text, original_text)
            dependent_path.write_text(unterminated_text, encoding="utf-8")
            parsed_meta, parse_error = MODULE.parse_blocking_dependency_meta(unterminated_text)
            self.assertEqual(parsed_meta, {})
            self.assertEqual(parse_error, "unterminated plan_meta JSON fence")

            state_before = paths.state_path.read_bytes()
            log_before = paths.log_path.read_bytes()

            with self.assertRaisesRegex(
                MODULE.QueueError,
                "blocking_depends_on_invalid: .*unterminated plan_meta JSON fence",
            ):
                MODULE.activate_next(paths, now="2026-06-14T14:46:31Z")

            self.assertEqual(paths.state_path.read_bytes(), state_before)
            self.assertEqual(paths.log_path.read_bytes(), log_before)

    _MALFORMED_PLAN_META_JSON = (
        "{\n"
        '  "plan_meta": {\n'
        '    "cluster": "process",\n'
        '    "tags": [],\n'
    )
    _DUPLICATE_KEY_PLAN_META_JSON = (
        "{\n"
        '  "plan_meta": {\n'
        '    "cluster": "process",\n'
        '    "cluster": "process",\n'
        '    "tags": [],\n'
        '    "required_manager_mode": "either",\n'
        '    "phase_overlay": null,\n'
        '    "phase_state": null,\n'
        '    "parent": null,\n'
        '    "next_plans": [],\n'
        '    "depends_on": [],\n'
        '    "followups_out": [],\n'
        '    "canon_updates": []\n'
        "  }\n"
        "}\n"
    )

    def test_routing_lanes_read_meta_only_through_shared_strict_reader(self) -> None:
        self.assertFalse(
            hasattr(MODULE, "parse_plan_meta"),
            "plan_queue must not keep a local lenient plan_meta copy; routing "
            "call-sites go through plan_status_oracle.strict_plan_meta_json",
        )
        self.assertTrue(hasattr(MODULE, "plan_status_oracle"))
        self.assertTrue(hasattr(MODULE.plan_status_oracle, "strict_plan_meta_json"))

    def test_queue_activation_import_warning_fails_closed_on_malformed_and_duplicate_meta(self) -> None:
        for label, meta_json, expected_code in (
            ("malformed", self._MALFORMED_PLAN_META_JSON, "malformed_json"),
            ("duplicate_key", self._DUPLICATE_KEY_PLAN_META_JSON, "duplicate_json_key"),
        ):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                rel = f"docs/plans/260829_1700_{label}_warning.md"
                self._write_plan(root, rel, meta_json=meta_json)

                warning = MODULE.queue_activation_import_warning(root, rel)

                self.assertIsNotNone(warning)
                self.assertIn("plan_meta_strict_read_failed", warning)
                self.assertIn(f"reason_code={expected_code}", warning)

    def test_queue_collection_admission_fails_closed_on_malformed_and_duplicate_meta(self) -> None:
        for label, meta_json, expected_code in (
            ("malformed", self._MALFORMED_PLAN_META_JSON, "malformed_json"),
            ("duplicate_key", self._DUPLICATE_KEY_PLAN_META_JSON, "duplicate_json_key"),
        ):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                (root / ".git").mkdir()
                rel = f"docs/plans/260829_1701_{label}_candidate.md"
                self._write_plan(root, rel, meta_json=meta_json)
                paths = self._queue_paths(root)

                with self.assertRaisesRegex(
                    MODULE.QueueError,
                    rf"queue_activation_admission_blocked: {rel}: plan_meta_strict_read_failed; reason_code={expected_code}",
                ):
                    MODULE.set_queue(paths, plans=[rel], now="2026-08-29T14:00:00Z")

                self.assertFalse(paths.state_path.exists())
                self.assertFalse(paths.log_path.exists())

    def test_same_queue_dependency_blocker_fails_closed_on_malformed_meta(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pending_rel = "docs/plans/260829_1702_malformed_pending.md"
            self._write_plan(root, pending_rel, meta_json=self._MALFORMED_PLAN_META_JSON)
            state = {"items": [{"plan": "docs/plans/260829_1703_other.md", "state": "pending"}]}
            pending_item = {"plan": pending_rel}

            blocker = MODULE.same_queue_dependency_blocker(root, state, pending_item)

            self.assertIsNotNone(blocker)
            self.assertIn("plan_meta_strict_read_failed", blocker)
            self.assertIn(f"plan_meta_strict_read_failed: {pending_rel}: reason_code=malformed_json", blocker)

    def test_activate_next_rejects_duplicate_key_meta_via_same_queue_dependency_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            pending_rel = "docs/plans/260829_1703_duplicate_pending.md"
            pending_path = self._write_plan(root, pending_rel)
            paths = self._queue_paths(root)
            MODULE.set_queue(paths, plans=[pending_rel], now="2026-06-14T14:47:00Z")
            pending_text = pending_path.read_text(encoding="utf-8")
            meta_start = pending_text.index("```json\n") + len("```json\n")
            meta_end = pending_text.index("\n```", meta_start)
            pending_path.write_text(
                pending_text[:meta_start]
                + self._DUPLICATE_KEY_PLAN_META_JSON
                + pending_text[meta_end:],
                encoding="utf-8",
            )
            state_before = paths.state_path.read_bytes()
            log_before = paths.log_path.read_bytes()

            with self.assertRaises(MODULE.QueueError) as caught:
                MODULE.activate_next(paths, now="2026-06-14T14:47:01Z")

            self.assertEqual(
                str(caught.exception),
                f"plan_meta_strict_read_failed: {pending_rel}: reason_code=duplicate_json_key",
            )
            self.assertEqual(paths.state_path.read_bytes(), state_before)
            self.assertEqual(paths.log_path.read_bytes(), log_before)

    def test_umbrella_queue_seed_fallback_fails_closed_on_malformed_meta(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            umbrella_rel = "docs/plans/260829_1704_malformed_umbrella.md"
            self._write_plan(root, umbrella_rel, meta_json=self._MALFORMED_PLAN_META_JSON)
            paths = self._queue_paths(root)

            with self.assertRaisesRegex(
                MODULE.QueueError,
                rf"plan_meta_strict_read_failed: {umbrella_rel}: reason_code=malformed_json",
            ):
                MODULE.set_queue(paths, umbrella=umbrella_rel, now="2026-08-29T14:05:00Z")

            self.assertFalse(paths.state_path.exists())
            self.assertFalse(paths.log_path.exists())

    def test_umbrella_queue_seed_fallback_fails_closed_on_duplicate_key_meta(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            umbrella_rel = "docs/plans/260829_1705_duplicate_umbrella.md"
            self._write_plan(root, umbrella_rel, meta_json=self._DUPLICATE_KEY_PLAN_META_JSON)
            paths = self._queue_paths(root)

            with self.assertRaises(MODULE.QueueError) as caught:
                MODULE.set_queue(paths, umbrella=umbrella_rel, now="2026-08-29T14:06:00Z")

            self.assertEqual(
                str(caught.exception),
                f"plan_meta_strict_read_failed: {umbrella_rel}: reason_code=duplicate_json_key",
            )
            self.assertFalse(paths.state_path.exists())
            self.assertFalse(paths.log_path.exists())

    def test_blocking_dependency_meta_maps_strict_reason_codes_to_carrier_scoped_strings(self) -> None:
        malformed_carrier_text = (
            "# Plan: fixture\n\n"
            "**Status:** Ready for Coder\n\n"
            "## Meta (machine-readable JSON; required for new plans)\n"
            "```json\n"
            "{\n"
            '  "plan_meta": {\n'
            '    "depends_on": ["docs/plans/260829_1705_dep.md"],\n'
            '    "blocking_depends_on": ["docs/plans/260829_1705_dep.md"],\n'
            "  }\n"
            "```\n\n"
            "## Execution queue\n"
            "- `N/A (why=fixture)`\n"
        )
        meta, error = MODULE.parse_blocking_dependency_meta(malformed_carrier_text)
        self.assertEqual(meta, {})
        self.assertIsNotNone(error)
        self.assertTrue(error.startswith("malformed plan_meta JSON ("))

        duplicate_key_carrier_text = (
            "# Plan: fixture\n\n"
            "**Status:** Ready for Coder\n\n"
            "## Meta (machine-readable JSON; required for new plans)\n"
            "```json\n"
            "{\n"
            '  "plan_meta": {\n'
            '    "depends_on": ["docs/plans/260829_1705_dep.md"],\n'
            '    "depends_on": ["docs/plans/260829_1705_dep.md"],\n'
            '    "blocking_depends_on": ["docs/plans/260829_1705_dep.md"]\n'
            "  }\n"
            "}\n"
            "```\n\n"
            "## Execution queue\n"
            "- `N/A (why=fixture)`\n"
        )
        meta, error = MODULE.parse_blocking_dependency_meta(duplicate_key_carrier_text)
        self.assertEqual(meta, {})
        self.assertIsNotNone(error)
        self.assertTrue(error.startswith("malformed plan_meta JSON ("))
        self.assertIn("duplicate", error)

        malformed_without_carrier_text = malformed_carrier_text.replace(
            '    "blocking_depends_on": ["docs/plans/260829_1705_dep.md"],\n',
            "",
        )
        meta, error = MODULE.parse_blocking_dependency_meta(malformed_without_carrier_text)
        self.assertEqual(meta, {})
        self.assertIsNone(error)

    def test_recommendation_only_analysis_plan_does_not_create_queue_items_from_route_prose(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            umbrella_rel = "docs/plans/260614_1733_recommendation_only_analysis.md"
            analysis_plan = self._write_plan(
                root,
                umbrella_rel,
                meta_json=dedent(
                    """\
                    {
                      "plan_meta": {
                        "cluster": "process",
                        "tags": ["analysis-wave"],
                        "wave_family": "analysis_wave",
                        "phase_overlay": null,
                        "phase_state": null,
                        "parent": null,
                        "next_plans": [],
                        "depends_on": [],
                        "followups_out": [],
                        "canon_updates": []
                      }
                    }
                    """
                ).strip(),
                execution_queue="- `N/A (why=no child queue before accepted route)`",
            )
            analysis_plan.write_text(
                analysis_plan.read_text(encoding="utf-8")
                + dedent(
                    """\

                    ## Analysis pack
                    | Field | Value |
                    | --- | --- |
                    | `route_recommendation` | `primary route: decomposition_wave; Target refs: future child paths only after acceptance.` |

                    ## Promoted route artifact
                    `N/A (why=no accepted route before review and Architect arch review)`
                    """
                ),
                encoding="utf-8",
            )
            paths = self._queue_paths(root)

            snapshot = MODULE.set_queue(paths, umbrella=umbrella_rel, now="2026-06-14T14:34:00Z")

        self.assertEqual(snapshot["items"], [])

    def test_promoted_needs_analysis_child_imports_only_with_explicit_queue_activation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            self._write_plan_vocab(root)
            child_rel = "docs/plans/260614_1734_needs_analysis_child.md"
            child_plan = self._write_plan(
                root,
                child_rel,
                status="Architect initial draft",
                meta_json=json.dumps(
                    {
                        "plan_meta": {
                            "cluster": "process",
                            "tags": ["planning-contour", "analysis-wave", "needs-analysis"],
                            "wave_family": "analysis_wave",
                            "phase_overlay": None,
                            "phase_state": None,
                            "parent": "docs/plans/260614_1735_promoted_umbrella.md",
                            "next_plans": [],
                            "depends_on": [],
                            "queue_activation": {
                                "state": "architect_approved",
                                "source_ref": "docs/plans/260614_1735_promoted_umbrella.md#Execution-queue",
                                "reason": "needs_analysis fixture",
                            },
                            "followups_out": [],
                            "canon_updates": [],
                        }
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            )
            child_plan.write_text(
                child_plan.read_text(encoding="utf-8")
                + dedent(
                    """\

                    ## Small-model-ready child contract
                    | Field | Value |
                    | --- | --- |
                    | Task outcome | needs_analysis child produces reviewed planning route only |
                    | Local context bundle | `docs/plans/parent.md`, `docs/playbooks/analysis_wave.md` |
                    | Mutable surfaces | `docs/plans/child.md` |
                    | Read-only surfaces | `docs/playbooks/analysis_wave.md` |
                    | Forbidden scope | product/dev implementation |
                    | Inputs from parent/predecessor | parent execution queue row |
                    | Output to consumer | reviewed analysis pack for parent |
                    | Acceptance/proof lane | plan lint and docs review |
                    | Stop condition | return upstream if route carrier is missing |
                    | Expected reviewer lane | docs-only process analysis review |
                    | Runner suitability | frontier recommended for analysis |
                    | Task size/complexity | medium; planning return-edge analysis |
                    | Readiness notes | not product/dev queue work |
                    """
                ),
                encoding="utf-8",
            )
            self._write_plan(
                root,
                "docs/plans/260614_1735_promoted_umbrella.md",
                meta_json=dedent(
                    f"""\
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
                    """
                ).strip(),
                execution_queue=dedent(
                    f"""\
                    - Resume parent: `run-parent-once`
                    - Plan: `{child_rel}`
                    """
                ).rstrip(),
                small_slice_classifier=dedent(
                    f"""\
                    - Requested profile: `N/A (why=fixture)`
                    - Expected bundle family: `N/A (why=fixture)`
                    - Helper validation: `N/A (why=fixture)`
                    - Drift behavior: `N/A (why=fixture)`

                    ## Child plan map
                    | Queue order | Plan | Summary |
                    | --- | --- | --- |
                    | 1 | `{child_rel}` | needs_analysis child |
                    """
                ).rstrip(),
            )
            paths = self._queue_paths(root)

            snapshot = MODULE.set_queue(
                paths,
                umbrella="docs/plans/260614_1735_promoted_umbrella.md",
                now="2026-06-14T14:35:00Z",
            )

        self.assertEqual(snapshot["items"][0]["plan"], child_rel)
        self.assertNotIn("queue_activation_warning", snapshot["items"][0])
        self.assertEqual(snapshot["items"][0]["source"], "execution_queue")

    def test_next_plans_import_rejects_missing_child_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            self._write_plan(
                root,
                "docs/plans/260328_0315_umbrella.md",
                meta_json=dedent(
                    """\
                    {
                      "plan_meta": {
                        "cluster": "process",
                        "tags": [],
                        "phase_overlay": null,
                        "phase_state": null,
                        "parent": null,
                        "next_plans": [
                          "docs/plans/260328_0316_missing_child.md"
                        ],
                        "depends_on": [],
                        "followups_out": [],
                        "canon_updates": []
                      }
                    }
                    """
                ).strip(),
            )
            stdout = io.StringIO()
            stderr = io.StringIO()
            argv = [
                "--project-root",
                str(root),
                "set",
                "--from-umbrella",
                "docs/plans/260328_0315_umbrella.md",
                "--for-manager-mode",
                "manager-collab",
                "--json",
            ]

            with mock.patch("sys.stdout", stdout), mock.patch("sys.stderr", stderr):
                result = MODULE.main(argv)

        self.assertEqual(result, 1)
        self.assertIn("Missing plan file: docs/plans/260328_0316_missing_child.md", stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "")

    def test_next_plans_import_rejects_non_lintable_child_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            broken_child = root / "docs/plans/260328_0314_broken_child.md"
            broken_child.parent.mkdir(parents=True, exist_ok=True)
            broken_child.write_text(
                dedent(
                    """\
                    # Plan: broken child

                    **Date:** 2026-03-28 03:14 MSK
                    **Stage:** Stage 1
                    **Priority:** P1
                    **Plan type:** dev
                    **Status:** Ready for Coder
                    **Status:** In progress

                    ## Problem
                    1. Broken fixture.
                    """
                ),
                encoding="utf-8",
            )
            self._write_plan(
                root,
                "docs/plans/260328_0313_umbrella.md",
                meta_json=dedent(
                    """\
                    {
                      "plan_meta": {
                        "cluster": "process",
                        "tags": [],
                        "phase_overlay": null,
                        "phase_state": null,
                        "parent": null,
                        "next_plans": [
                          "docs/plans/260328_0314_broken_child.md"
                        ],
                        "depends_on": [],
                        "followups_out": [],
                        "canon_updates": []
                      }
                    }
                    """
                ).strip(),
            )
            stdout = io.StringIO()
            stderr = io.StringIO()
            argv = [
                "--project-root",
                str(root),
                "set",
                "--from-umbrella",
                "docs/plans/260328_0313_umbrella.md",
                "--for-manager-mode",
                "manager-collab",
                "--json",
            ]

            with mock.patch("sys.stdout", stdout), mock.patch("sys.stderr", stderr):
                result = MODULE.main(argv)

        self.assertEqual(result, 1)
        self.assertIn("Child plan is not queue-lintable", stderr.getvalue())
        self.assertIn("expected exactly 1 header **Status:** line", stderr.getvalue())

    def test_empty_umbrella_import_records_empty_expansion(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            umbrella = self._write_plan(root, "docs/plans/260328_0400_empty_umbrella.md")
            paths = self._queue_paths(root)

            snapshot = MODULE.set_queue(paths, umbrella=str(umbrella), now="2026-03-28T02:10:00Z")
            log_lines = paths.log_path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(snapshot["items"], [])
        self.assertIn("expansion=none", log_lines[-1])
        self.assertIn("count=0", log_lines[-1])

    def test_active_decomposition_umbrella_rejects_missing_child_graph(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            self._write_plan(
                root,
                "docs/plans/260517_1623_active_decomposition_missing_children.md",
                meta_json=dedent(
                    """\
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
                    """
                ).strip(),
                execution_queue=dedent(
                    """\
                    - Resume parent: `owner-restamp-required`
                    - Plan: `TBD`
                    """
                ).rstrip(),
            )
            stdout = io.StringIO()
            stderr = io.StringIO()
            argv = [
                "--project-root",
                str(root),
                "set",
                "--from-umbrella",
                "docs/plans/260517_1623_active_decomposition_missing_children.md",
                "--for-manager-mode",
                "manager-collab",
                "--json",
            ]

            with mock.patch("sys.stdout", stdout), mock.patch("sys.stderr", stderr):
                result = MODULE.main(argv)

        self.assertEqual(result, 1)
        self.assertIn("decomposition_children_missing", stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "")

    def test_active_decomposition_umbrella_imports_three_concrete_children(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            child_paths = [
                "docs/plans/260517_1630_decomposition_child_a.md",
                "docs/plans/260517_1631_decomposition_child_b.md",
                "docs/plans/260517_1632_decomposition_child_c.md",
            ]
            for rel_path in child_paths:
                self._write_small_model_ready_child(root, rel_path)
            next_plans_json = json.dumps(child_paths, indent=8)
            execution_rows = "\n".join(f"- Plan: `{rel_path}`" for rel_path in child_paths)
            child_map_rows = "\n".join(
                f"| {idx} | `{rel_path}` | child {idx} |"
                for idx, rel_path in enumerate(child_paths, start=1)
            )
            umbrella = self._write_plan(
                root,
                "docs/plans/260517_1624_active_decomposition_three_children.md",
                meta_json=dedent(
                    f"""\
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
                    """
                ).strip(),
                execution_queue=dedent(
                    f"""\
                    - Resume parent: `run-parent-once`
                    {execution_rows}
                    """
                ).rstrip(),
                small_slice_classifier=dedent(
                    """\
                    - Requested profile: `N/A (why=fixture)`
                    - Expected bundle family: `N/A (why=fixture)`
                    - Helper validation: `N/A (why=fixture)`
                    - Drift behavior: `N/A (why=fixture)`

                    ## Child plan map
                    | Queue order | Plan | Summary |
                    | --- | --- | --- |
                    {child_map_rows}
                    """
                ).rstrip().format(child_map_rows=child_map_rows),
            )
            paths = self._queue_paths(root)

            snapshot = MODULE.set_queue(paths, umbrella=str(umbrella), now="2026-05-17T13:24:00Z")

        self.assertEqual(snapshot["resume_parent"], "run-parent-once")
        self.assertEqual([item["plan"] for item in snapshot["items"]], child_paths)
        self.assertEqual([item["source"] for item in snapshot["items"]], ["execution_queue"] * 3)

    def _write_small_model_ready_child(
        self,
        root: Path,
        rel_path: str,
        *,
        complete: bool = True,
        omit_runner_suitability: bool = False,
        template_placeholders: bool = False,
    ) -> None:
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        contract = ""
        if complete:
            if template_placeholders:
                value_map = {
                    "Task outcome": "<one observable result>",
                    "Local context bundle": "<exact docs/plans/reviews/helpers to read first>",
                    "Mutable surfaces": "<exact paths/path families allowed to change>",
                    "Read-only surfaces": "<anchors allowed for reading only>",
                    "Forbidden scope": "<explicit non-goals / nearby tempting changes>",
                    "Inputs from parent/predecessor": "<artifact paths and dependency gates>",
                    "Output to consumer": "<artifact/status/queue effect and consumer>",
                    "Acceptance/proof lane": "<exact commands/checks/receipts/review lane>",
                    "Stop condition": "<when to return upstream instead of guessing>",
                    "Expected reviewer lane": "<docs-only/code/risk/contracts/visual>",
                    "Runner suitability": "<recommended runner class plus fallback/degraded condition>",
                    "Task size/complexity": "<small|medium|large and why>",
                    "Readiness notes": "<known clarity gaps / confidence notes>",
                }
            else:
                value_map = {
                    "Task outcome": "fixture child produces one observable helper result",
                    "Local context bundle": "`docs/plans/parent.md`, `docs/playbooks/decomposition_wave.md`",
                    "Mutable surfaces": "`scripts/fixture.py`, `scripts/test_fixture.py`",
                    "Read-only surfaces": "`docs/playbooks/decomposition_wave.md`",
                    "Forbidden scope": "model defaults and external runner wrappers",
                    "Inputs from parent/predecessor": "`docs/plans/parent.md` queue row",
                    "Output to consumer": "`docs/plans/child.md` status/evidence for Reviewer",
                    "Acceptance/proof lane": "`python -m unittest scripts.test_plan_queue`",
                    "Stop condition": "return to Planner if new helper CLI semantics are needed",
                    "Expected reviewer lane": "code",
                    "Runner suitability": "small runner OK; fallback to Coder if target bundle expands",
                    "Task size/complexity": "small; focused helper change",
                    "Readiness notes": "no known clarity gaps",
                }
            runner_row = (
                ""
                if omit_runner_suitability
                else f"| Runner suitability | {value_map['Runner suitability']} |\n"
            )
            contract = dedent(
                f"""\

                ## Small-model-ready child contract
                | Field | Value |
                | --- | --- |
                | Task outcome | {value_map['Task outcome']} |
                | Local context bundle | {value_map['Local context bundle']} |
                | Mutable surfaces | {value_map['Mutable surfaces']} |
                | Read-only surfaces | {value_map['Read-only surfaces']} |
                | Forbidden scope | {value_map['Forbidden scope']} |
                | Inputs from parent/predecessor | {value_map['Inputs from parent/predecessor']} |
                | Output to consumer | {value_map['Output to consumer']} |
                | Acceptance/proof lane | {value_map['Acceptance/proof lane']} |
                | Stop condition | {value_map['Stop condition']} |
                | Expected reviewer lane | {value_map['Expected reviewer lane']} |
                {runner_row.rstrip()}
                | Task size/complexity | {value_map['Task size/complexity']} |
                | Readiness notes | {value_map['Readiness notes']} |
                """
            )
        # Canonical column-0 markdown with a real `## Meta` carrier: the strict
        # routing reader fail-closes routing lanes on plans without a sole
        # top-level Meta section.
        decision = self._na_machine_authority_decision()
        meta_json = json.dumps(
            {
                "plan_meta": {
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
                    "machine_authority_decision": decision,
                }
            },
            ensure_ascii=False,
            indent=2,
        )
        target.write_text(
            "\n".join(
                [
                    "# Plan: small model child fixture",
                    "",
                    "**Date:** 2026-06-11 21:01 MSK",
                    "**Stage:** Stage 1",
                    "**Priority:** P1",
                    "**Plan type:** dev",
                    "**Status:** Ready for Coder",
                    "**Schema version:** plan.v1",
                    "",
                    "**Context links (source of truth):**",
                    f"- Code draft(s): `docs/code_drafts/{Path(rel_path).stem}__code_draft.md`",
                    "",
                    "## Meta (machine-readable JSON; required for new plans)",
                    "```json",
                    meta_json,
                    "```",
                    *([contract.lstrip("\n")] if contract.strip() else []),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        fixture_target = root / "scripts/machine_authority_fixture.py"
        if not fixture_target.exists():
            fixture_target.parent.mkdir(parents=True, exist_ok=True)
            fixture_target.write_text("# machine-authority fixture\n", encoding="utf-8")
        self._write_code_draft(
            root,
            rel_path,
            target_paths=["scripts/machine_authority_fixture.py"],
            machine_authority_decision=decision,
            overwrite=False,
        )

    def test_active_decomposition_import_rejects_current_child_missing_readiness_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            child_rel = "docs/plans/260611_2101_child_missing_readiness.md"
            self._write_small_model_ready_child(root, child_rel, complete=False)
            self._write_plan(
                root,
                "docs/plans/260611_2100_active_decomposition_missing_readiness.md",
                meta_json=dedent(
                    f"""\
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
                    """
                ).strip(),
                execution_queue=dedent(
                    f"""\
                    - Resume parent: `run-parent-once`
                    - Plan: `{child_rel}`
                    """
                ).rstrip(),
                small_slice_classifier=dedent(
                    f"""\
                    - Requested profile: `N/A (why=fixture)`
                    - Expected bundle family: `N/A (why=fixture)`
                    - Helper validation: `N/A (why=fixture)`
                    - Drift behavior: `N/A (why=fixture)`

                    ## Child plan map
                    | Queue order | Plan | Summary |
                    | --- | --- | --- |
                    | 1 | `{child_rel}` | missing readiness child |
                    """
                ).rstrip(),
            )
            stderr = io.StringIO()
            argv = [
                "--project-root",
                str(root),
                "set",
                "--from-umbrella",
                "docs/plans/260611_2100_active_decomposition_missing_readiness.md",
                "--for-manager-mode",
                "manager-collab",
                "--json",
            ]

            with mock.patch("sys.stderr", stderr):
                result = MODULE.main(argv)

        self.assertEqual(result, 1)
        self.assertIn("small_model_ready_child_blocked", stderr.getvalue())
        self.assertIn("Task outcome", stderr.getvalue())

    def test_active_decomposition_import_rejects_template_angle_placeholder_readiness_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            child_rel = "docs/plans/260611_2102_child_template_placeholders.md"
            self._write_small_model_ready_child(root, child_rel, complete=True, template_placeholders=True)
            self._write_plan(
                root,
                "docs/plans/260611_2101_active_decomposition_template_placeholders.md",
                meta_json=dedent(
                    f"""\
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
                    """
                ).strip(),
                execution_queue=dedent(
                    f"""\
                    - Resume parent: `run-parent-once`
                    - Plan: `{child_rel}`
                    """
                ).rstrip(),
                small_slice_classifier=dedent(
                    f"""\
                    - Requested profile: `N/A (why=fixture)`
                    - Expected bundle family: `N/A (why=fixture)`
                    - Helper validation: `N/A (why=fixture)`
                    - Drift behavior: `N/A (why=fixture)`

                    ## Child plan map
                    | Queue order | Plan | Summary |
                    | --- | --- | --- |
                    | 1 | `{child_rel}` | template placeholder child |
                    """
                ).rstrip(),
            )
            stderr = io.StringIO()
            argv = [
                "--project-root",
                str(root),
                "set",
                "--from-umbrella",
                "docs/plans/260611_2101_active_decomposition_template_placeholders.md",
                "--for-manager-mode",
                "manager-collab",
                "--json",
            ]

            with mock.patch("sys.stderr", stderr):
                result = MODULE.main(argv)

        self.assertEqual(result, 1)
        self.assertIn("small_model_ready_child_blocked", stderr.getvalue())
        self.assertIn("placeholder", stderr.getvalue())

    def test_active_decomposition_import_accepts_current_child_with_readiness_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            child_rel = "docs/plans/260611_2102_child_ready.md"
            self._write_small_model_ready_child(root, child_rel, complete=True)
            self._write_plan(
                root,
                "docs/plans/260611_2101_active_decomposition_ready_child.md",
                meta_json=dedent(
                    f"""\
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
                    """
                ).strip(),
                execution_queue=dedent(
                    f"""\
                    - Resume parent: `run-parent-once`
                    - Plan: `{child_rel}`
                    """
                ).rstrip(),
                small_slice_classifier=dedent(
                    f"""\
                    - Requested profile: `N/A (why=fixture)`
                    - Expected bundle family: `N/A (why=fixture)`
                    - Helper validation: `N/A (why=fixture)`
                    - Drift behavior: `N/A (why=fixture)`

                    ## Child plan map
                    | Queue order | Plan | Summary |
                    | --- | --- | --- |
                    | 1 | `{child_rel}` | ready child |
                    """
                ).rstrip(),
            )
            paths = self._queue_paths(root)

            snapshot = MODULE.set_queue(
                paths,
                umbrella="docs/plans/260611_2101_active_decomposition_ready_child.md",
                now="2026-06-11T18:01:00Z",
            )

        self.assertEqual([item["plan"] for item in snapshot["items"]], [child_rel])

    def test_active_decomposition_import_surfaces_warning_first_readiness_in_queue_readback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            child_rel = "docs/plans/260611_2103_child_warning_ready.md"
            self._write_small_model_ready_child(root, child_rel, complete=True, omit_runner_suitability=True)
            self._write_plan(
                root,
                "docs/plans/260611_2102_active_decomposition_warning_child.md",
                meta_json=dedent(
                    f"""\
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
                    """
                ).strip(),
                execution_queue=dedent(
                    f"""\
                    - Resume parent: `run-parent-once`
                    - Plan: `{child_rel}`
                    """
                ).rstrip(),
                small_slice_classifier=dedent(
                    f"""\
                    - Requested profile: `N/A (why=fixture)`
                    - Expected bundle family: `N/A (why=fixture)`
                    - Helper validation: `N/A (why=fixture)`
                    - Drift behavior: `N/A (why=fixture)`

                    ## Child plan map
                    | Queue order | Plan | Summary |
                    | --- | --- | --- |
                    | 1 | `{child_rel}` | warning-ready child |
                    """
                ).rstrip(),
            )
            paths = self._queue_paths(root)

            snapshot = MODULE.set_queue(
                paths,
                umbrella="docs/plans/260611_2102_active_decomposition_warning_child.md",
                now="2026-06-11T18:02:00Z",
            )
            active_snapshot = MODULE.activate_next(paths, now="2026-06-11T18:03:00Z")
            rendered = MODULE.render_snapshot(active_snapshot)

        item = snapshot["items"][0]
        self.assertEqual(item["small_model_readiness_state"], "warning")
        self.assertEqual(item["small_model_readiness_findings"][0]["field"], "Runner suitability")
        self.assertIn("active_child_readiness=warning", rendered)
        self.assertIn("Runner suitability", rendered)

    def test_non_decomposition_umbrella_does_not_require_small_model_readiness_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            child_rel = "docs/plans/260611_2110_non_decomposition_child.md"
            self._write_small_model_ready_child(root, child_rel, complete=False)
            self._write_plan(
                root,
                "docs/plans/260611_2109_non_decomposition_umbrella.md",
                meta_json=dedent(
                    f"""\
                    {{
                      "plan_meta": {{
                        "cluster": "process",
                        "tags": [],
                        "phase_overlay": null,
                        "phase_state": null,
                        "parent": null,
                        "next_plans": ["{child_rel}"],
                        "depends_on": [],
                        "followups_out": [],
                        "canon_updates": []
                      }}
                    }}
                    """
                ).strip(),
            )
            paths = self._queue_paths(root)

            snapshot = MODULE.set_queue(
                paths,
                umbrella="docs/plans/260611_2109_non_decomposition_umbrella.md",
                now="2026-06-11T18:09:00Z",
            )

        self.assertEqual([item["plan"] for item in snapshot["items"]], [child_rel])

    def test_resume_parent_rejects_embedded_reason_text(self) -> None:
        with self.assertRaises(MODULE.QueueError):
            MODULE.normalize_resume_parent("run-parent-once (why=fixture)")

    def test_resume_parent_treats_na_reason_as_none(self) -> None:
        self.assertEqual(MODULE.normalize_resume_parent("N/A (why=not a queue carrier)"), "none")

    def test_main_returns_non_zero_for_mismatched_legacy_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            self._write_plan(root, "docs/plans/260328_0501_child_a.md")
            self._write_plan(root, "docs/plans/260328_0502_child_b.md")
            self._write_plan(
                root,
                "docs/plans/260328_0500_bad_umbrella.md",
                meta_json=dedent(
                    """\
                    {
                      "plan_meta": {
                        "cluster": "process",
                        "tags": [],
                        "phase_overlay": null,
                        "phase_state": null,
                        "parent": null,
                        "next_plans": [
                          "docs/plans/260328_0502_child_b.md"
                        ],
                        "depends_on": [],
                        "followups_out": [
                          {"cluster": "process", "summary": "first", "plan": "docs/plans/260328_0501_child_a.md"}
                        ],
                        "canon_updates": []
                      }
                    }
                    """
                ).strip(),
            )
            stdout = io.StringIO()
            stderr = io.StringIO()
            argv = [
                "--project-root",
                str(root),
                "set",
                "--from-umbrella",
                "docs/plans/260328_0500_bad_umbrella.md",
                "--for-manager-mode",
                "manager-collab",
                "--json",
            ]
            with mock.patch("sys.stdout", stdout), mock.patch("sys.stderr", stderr):
                result = MODULE.main(argv)

        self.assertEqual(result, 1)
        self.assertIn("next_plans[]", stderr.getvalue())

    def test_cli_show_json_reports_active_item(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            self._write_plan(root, "docs/plans/260328_0600_first.md")
            paths = self._queue_paths(root)
            MODULE.set_queue(paths, plans=["docs/plans/260328_0600_first.md"], now="2026-03-28T02:20:00Z")
            MODULE.activate_next(paths, now="2026-03-28T02:21:00Z")
            stdout = io.StringIO()
            with mock.patch("sys.stdout", stdout):
                result = MODULE.main(["--project-root", str(root), "show", "--json"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(result, 0)
        self.assertEqual(payload["active_plan"], "docs/plans/260328_0600_first.md")
        self.assertFalse(payload["queue_empty"])

    def test_stop_queue_surfaces_checkpoint_metadata_in_show(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            self._write_plan(root, "docs/plans/260328_0700_first.md")
            self._write_plan(root, "docs/plans/260328_0701_second.md")
            paths = self._queue_paths(root)

            MODULE.set_queue(
                paths,
                plans=["docs/plans/260328_0700_first.md", "docs/plans/260328_0701_second.md"],
                now="2026-03-28T02:30:00Z",
            )
            MODULE.activate_next(paths, now="2026-03-28T02:31:00Z")
            stopped = MODULE.stop_queue(paths, "max_iterations_reached", now="2026-03-28T02:32:00Z")
            rendered = MODULE.render_snapshot(stopped)

        self.assertEqual(stopped["effective_plan"], "docs/plans/260328_0700_first.md")
        self.assertEqual(stopped["next_pending_plan"], "docs/plans/260328_0701_second.md")
        self.assertEqual(stopped["last_stop"]["reason"], "max_iterations_reached")
        self.assertEqual(stopped["last_stop"]["scope"], "current_active")
        self.assertTrue(stopped["queue_runtime_context"]["max_iterations_reached"])
        self.assertFalse(stopped["queue_runtime_context"]["repeated_blocker_detected"])
        self.assertEqual(stopped["queue_runtime_context"]["latest_stop_reason_scope"], "current_active")
        self.assertEqual(
            stopped["queue_runtime_context"]["latest_stop_item_ref"],
            "1:docs/plans/260328_0700_first.md",
        )
        self.assertIn("current=docs/plans/260328_0700_first.md (active_item)", rendered)
        self.assertIn("next_pending=docs/plans/260328_0701_second.md", rendered)
        self.assertIn("last_stop=max_iterations_reached @ 2026-03-28T02:32:00Z", rendered)
        self.assertIn("queue_context=plan=docs/plans/260328_0700_first.md", rendered)
        self.assertIn("stop_scope=current_active latest_stop=max_iterations_reached", rendered)

    def test_advance_scopes_previous_stop_as_historical_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            self._write_plan(root, "docs/plans/260328_0703_first.md", status="Done")
            self._write_plan(root, "docs/plans/260328_0704_second.md")
            paths = self._queue_paths(root)

            MODULE.set_queue(
                paths,
                plans=["docs/plans/260328_0703_first.md", "docs/plans/260328_0704_second.md"],
                now="2026-03-28T02:37:00Z",
            )
            MODULE.activate_next(paths, now="2026-03-28T02:38:00Z")
            MODULE.stop_queue(paths, "unchanged_status", now="2026-03-28T02:39:00Z")
            advanced = MODULE.advance_queue(paths, "Done", now="2026-03-28T02:40:00Z")
            rendered = MODULE.render_snapshot(advanced)

        queue_context = advanced["queue_runtime_context"]
        self.assertEqual(advanced["effective_plan"], "docs/plans/260328_0704_second.md")
        self.assertIsNone(advanced["last_stop"])
        self.assertIsNone(queue_context["latest_stop_reason"])
        self.assertEqual(queue_context["latest_stop_reason_scope"], "historical")
        self.assertEqual(queue_context["historical_stop_reason"], "unchanged_status")
        self.assertEqual(queue_context["historical_stop_plan"], "docs/plans/260328_0703_first.md")
        self.assertEqual(
            queue_context["historical_stop_item_ref"],
            "1:docs/plans/260328_0703_first.md",
        )
        self.assertFalse(queue_context["loop_detected"])
        self.assertIn("current=docs/plans/260328_0704_second.md (active_item)", rendered)
        self.assertIn("stop_scope=historical latest_stop=none", rendered)
        self.assertIn("historical_stop=unchanged_status", rendered)

    def test_queue_complete_keeps_previous_stop_historical_not_live(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            self._write_plan(root, "docs/plans/260328_0705_only.md", status="Done")
            paths = self._queue_paths(root)

            MODULE.set_queue(paths, plans=["docs/plans/260328_0705_only.md"], now="2026-03-28T02:41:00Z")
            MODULE.activate_next(paths, now="2026-03-28T02:42:00Z")
            MODULE.stop_queue(paths, "role_usage_limit", now="2026-03-28T02:43:00Z")
            advanced = MODULE.advance_queue(paths, "Done", now="2026-03-28T02:44:00Z")

        queue_context = advanced["queue_runtime_context"]
        self.assertTrue(advanced["queue_complete"])
        self.assertIsNone(advanced["effective_plan"])
        self.assertIsNone(queue_context["latest_stop_reason"])
        self.assertEqual(queue_context["latest_stop_reason_scope"], "historical")
        self.assertEqual(queue_context["historical_stop_reason"], "role_usage_limit")
        self.assertFalse(queue_context["max_iterations_reached"])

    def test_queue_runtime_context_marks_repeated_blockers_from_log_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            self._write_plan(root, "docs/plans/260328_0702_first.md")
            paths = self._queue_paths(root)

            MODULE.set_queue(paths, plans=["docs/plans/260328_0702_first.md"], now="2026-03-28T02:33:00Z")
            MODULE.activate_next(paths, now="2026-03-28T02:34:00Z")
            MODULE.stop_queue(paths, "unchanged_status", now="2026-03-28T02:35:00Z")
            stopped = MODULE.stop_queue(paths, "unchanged_status", now="2026-03-28T02:36:00Z")

        queue_context = stopped["queue_runtime_context"]
        self.assertTrue(queue_context["loop_detected"])
        self.assertTrue(queue_context["repeated_blocker_detected"])
        self.assertFalse(queue_context["max_iterations_reached"])
        self.assertEqual(queue_context["latest_stop_reason"], "unchanged_status")

    def test_history_report_marks_current_and_historical_stop_rows_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            self._write_plan(root, "docs/plans/260328_0710_first.md", status="Done")
            self._write_plan(root, "docs/plans/260328_0711_second.md")
            paths = self._queue_paths(root)

            MODULE.set_queue(
                paths,
                plans=["docs/plans/260328_0710_first.md", "docs/plans/260328_0711_second.md"],
                now="2026-03-28T02:50:00Z",
            )
            MODULE.activate_next(paths, now="2026-03-28T02:51:00Z")
            MODULE.stop_queue(paths, "unchanged_status", now="2026-03-28T02:52:00Z")
            MODULE.advance_queue(paths, "Done", now="2026-03-28T02:53:00Z")
            MODULE.stop_queue(paths, "max_iterations_reached", now="2026-03-28T02:54:00Z")
            state_before = paths.state_path.read_text(encoding="utf-8")
            log_before = paths.log_path.read_text(encoding="utf-8")

            report = MODULE.queue_history_report(paths, limit=0)
            rendered = MODULE.render_history_report(report)
            state_after = paths.state_path.read_text(encoding="utf-8")
            log_after = paths.log_path.read_text(encoding="utf-8")

        self.assertTrue(report["read_only"])
        self.assertEqual(state_after, state_before)
        self.assertEqual(log_after, log_before)
        stop_rows = [entry for entry in report["entries"] if entry["event"] == "stop"]
        self.assertEqual([entry["stop_scope"] for entry in stop_rows], ["historical", "current_active"])
        self.assertIn("event=stop plan=docs/plans/260328_0710_first.md", rendered)
        self.assertIn("stop_scope=historical", rendered)
        self.assertIn("event=stop plan=docs/plans/260328_0711_second.md", rendered)
        self.assertIn("stop_scope=current_active", rendered)

    def test_cli_history_json_is_read_only_and_limited(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            self._write_plan(root, "docs/plans/260328_0712_only.md")
            paths = self._queue_paths(root)
            MODULE.set_queue(paths, plans=["docs/plans/260328_0712_only.md"], now="2026-03-28T03:00:00Z")
            MODULE.activate_next(paths, now="2026-03-28T03:01:00Z")
            MODULE.stop_queue(paths, "role_usage_limit", now="2026-03-28T03:02:00Z")
            state_before = paths.state_path.read_text(encoding="utf-8")
            log_before = paths.log_path.read_text(encoding="utf-8")
            stdout = io.StringIO()

            with mock.patch("sys.stdout", stdout):
                result = MODULE.main(["--project-root", str(root), "history", "--limit", "1", "--json"])
            state_after = paths.state_path.read_text(encoding="utf-8")
            log_after = paths.log_path.read_text(encoding="utf-8")

        payload = json.loads(stdout.getvalue())
        self.assertEqual(result, 0)
        self.assertTrue(payload["read_only"])
        self.assertEqual(payload["shown_entries"], 1)
        self.assertEqual(payload["entries"][0]["event"], "stop")
        self.assertEqual(payload["entries"][0]["stop_scope"], "current_active")
        self.assertEqual(state_after, state_before)
        self.assertEqual(log_after, log_before)

    def test_terminal_tail_stop_keeps_item_7_runtime_clean_and_preserves_source_readback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            plans = [f"docs/plans/260328_08{index:02d}_item.md" for index in range(1, 8)]
            for plan in plans[:-1]:
                self._write_plan(root, plan, status="Done")
            self._write_plan(root, plans[-1])
            paths = self._queue_paths(root)
            MODULE.set_queue(paths, plans=plans, now="2026-03-28T04:00:00Z")
            MODULE.activate_next(paths, now="2026-03-28T04:01:00Z")
            for index in range(1, 7):
                MODULE.advance_queue(
                    paths,
                    "Done",
                    now=f"2026-03-28T04:{index + 1:02d}:00Z",
                )

            stopped = MODULE.stop_queue(
                paths,
                "docs_closeout_blocked",
                source_plan=plans[5],
                now="2026-03-28T04:10:00Z",
            )
            state_before_readback = paths.state_path.read_bytes()
            log_before_readback = paths.log_path.read_bytes()
            show_stdout = io.StringIO()
            history_stdout = io.StringIO()
            with mock.patch("sys.stdout", show_stdout):
                show_result = MODULE.main(["--project-root", str(root), "show", "--json"])
            with mock.patch("sys.stdout", history_stdout):
                history_result = MODULE.main(
                    ["--project-root", str(root), "history", "--limit", "0", "--json"]
                )
            state_after_readback = paths.state_path.read_bytes()
            log_after_readback = paths.log_path.read_bytes()

            current = MODULE.stop_queue(
                paths,
                "docs_closeout_blocked",
                now="2026-03-28T04:11:00Z",
            )
            events = MODULE.parse_log_entries(paths)

        context = stopped["queue_runtime_context"]
        self.assertEqual(stopped["active_plan"], plans[6])
        self.assertEqual(stopped["done_count"], 6)
        self.assertEqual(stopped["pending_count"], 0)
        self.assertEqual(stopped["last_stop"]["plan"], plans[6])
        self.assertEqual(stopped["last_stop"]["order"], 7)
        self.assertEqual(stopped["last_stop"]["scope"], "terminal_tail")
        self.assertEqual(stopped["last_stop"]["stop_source_plan"], plans[5])
        self.assertEqual(stopped["last_stop"]["stop_source_order"], 6)
        self.assertEqual(stopped["last_stop"]["stop_phase"], "terminal_docs_closeout")
        self.assertIsNone(context["latest_stop_reason"])
        self.assertEqual(context["latest_stop_reason_scope"], "historical")
        self.assertEqual(context["stop_reasons"], [])
        self.assertFalse(context["loop_detected"])
        self.assertFalse(context["repeated_blocker_detected"])
        self.assertFalse(context["max_iterations_reached"])
        self.assertEqual(context["historical_stop_plan"], plans[5])
        self.assertEqual(context["historical_stop_item_ref"], f"6:{plans[5]}")
        self.assertEqual(context["terminal_tail_stop_reason"], "docs_closeout_blocked")
        self.assertEqual(context["terminal_tail_stop_source_plan"], plans[5])
        self.assertEqual(context["terminal_tail_stop_source_item_ref"], f"6:{plans[5]}")
        self.assertEqual(context["terminal_tail_stop_active_item_ref"], f"7:{plans[6]}")

        show_payload = json.loads(show_stdout.getvalue())
        history_payload = json.loads(history_stdout.getvalue())
        tail_row = [entry for entry in history_payload["entries"] if entry["event"] == "stop"][-1]
        self.assertEqual(show_result, 0)
        self.assertEqual(history_result, 0)
        self.assertEqual(
            show_payload["queue_runtime_context"]["terminal_tail_stop_source_plan"],
            plans[5],
        )
        self.assertEqual(tail_row["stop_scope"], "terminal_tail")
        self.assertEqual(tail_row["active_stop_item_ref"], f"7:{plans[6]}")
        self.assertEqual(tail_row["stop_source_item_ref"], f"6:{plans[5]}")
        self.assertEqual(tail_row["stop_source_plan"], plans[5])
        self.assertEqual(tail_row["stop_source_order"], "6")
        self.assertEqual(tail_row["stop_phase"], "terminal_docs_closeout")
        self.assertEqual(state_after_readback, state_before_readback)
        self.assertEqual(log_after_readback, log_before_readback)

        current_context = current["queue_runtime_context"]
        self.assertEqual(current_context["latest_stop_reason"], "docs_closeout_blocked")
        self.assertEqual(current_context["latest_stop_reason_scope"], "current_active")
        self.assertEqual(current_context["stop_reasons"], ["docs_closeout_blocked"])
        self.assertFalse(current_context["repeated_blocker_detected"])
        self.assertFalse(current_context["max_iterations_reached"])
        self.assertEqual(current_context["terminal_tail_stop_source_plan"], plans[5])
        self.assertEqual(current_context["terminal_tail_stop_source_item_ref"], f"6:{plans[5]}")
        self.assertEqual([entry["event"] for entry in events[-2:]], ["stop", "stop"])

    def test_terminal_stop_source_validation_is_atomic_and_machine_readable(self) -> None:
        for case in ("missing", "ambiguous", "non_terminal"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                (root / ".git").mkdir()
                source = "docs/plans/260328_0900_source.md"
                alias = "docs/plans/260328_0901_alias.md"
                active = "docs/plans/260328_0902_active.md"
                self._write_plan(root, source)
                self._write_plan(root, active)
                items = [
                    {"order": 1, "plan": source, "source": "fixture", "state": "done"},
                    {"order": 2, "plan": active, "source": "fixture", "state": "active"},
                ]
                requested_source = source
                if case == "missing":
                    requested_source = "docs/plans/260328_0999_missing.md"
                elif case == "ambiguous":
                    (root / alias).symlink_to(Path(source).name)
                    items = [
                        {"order": 1, "plan": source, "source": "fixture", "state": "done"},
                        {"order": 2, "plan": alias, "source": "fixture", "state": "done"},
                        {"order": 3, "plan": active, "source": "fixture", "state": "active"},
                    ]
                elif case == "non_terminal":
                    requested_source = active

                paths = self._queue_paths(root)
                state = MODULE.build_state(
                    mode="source_validation_fixture",
                    items=items,
                    now="2026-03-28T05:00:00Z",
                )
                state["cursor"] = next(
                    item["order"] - 1 for item in items if item["state"] == "active"
                )
                MODULE.save_state(paths, state)
                paths.log_path.write_text(
                    "2026-03-28T05:00:00Z\tset\tmode=source_validation_fixture\n",
                    encoding="utf-8",
                )
                state_before = paths.state_path.read_bytes()
                log_before = paths.log_path.read_bytes()
                stdout = io.StringIO()
                with mock.patch("sys.stdout", stdout):
                    result = MODULE.main(
                        [
                            "--project-root",
                            str(root),
                            "stop",
                            "--reason",
                            "docs_closeout_blocked",
                            "--source-plan",
                            requested_source,
                            "--json",
                        ]
                    )

                payload = json.loads(stdout.getvalue())
                self.assertEqual(result, 1)
                self.assertEqual(payload["error"], "source_provenance_invalid")
                self.assertEqual(payload["reason_code"], "source_provenance_invalid")
                self.assertFalse(payload["mutation_performed"])
                self.assertEqual(paths.state_path.read_bytes(), state_before)
                self.assertEqual(paths.log_path.read_bytes(), log_before)

    def test_mode_aware_closeout_admits_matching_and_either_candidates(self) -> None:
        for actual_mode in MODULE.plan_status_oracle.ACTUAL_MANAGER_MODES:
            for required_mode in (actual_mode, "either"):
                for candidate_kind in ("next_plan", "resume_parent_plan"):
                    with (
                        self.subTest(
                            actual_mode=actual_mode,
                            required_mode=required_mode,
                            candidate_kind=candidate_kind,
                        ),
                        tempfile.TemporaryDirectory() as tmpdir,
                    ):
                        root = Path(tmpdir)
                        (root / ".git").mkdir()
                        paths, active_rel, candidate_rel = self._prepare_mode_closeout_queue(
                            root,
                            candidate_kind=candidate_kind,
                            candidate_meta=self._manager_mode_meta(required_mode),
                        )

                        closeout = MODULE.closeout_queue(
                            paths,
                            manager_mode=actual_mode,
                            now="2026-07-17T19:00:02Z",
                        )

                        self.assertTrue(closeout["advanced"])
                        self.assertEqual(closeout["finalized_plan"], active_rel)
                        self.assertEqual(
                            closeout["next_plan"] if candidate_kind == "next_plan" else closeout["resume_parent_plan"],
                            candidate_rel,
                        )
                        if candidate_kind == "next_plan":
                            self.assertEqual(closeout["active_plan"], candidate_rel)
                        else:
                            self.assertEqual(closeout["effective_plan"], candidate_rel)
                            self.assertEqual(closeout["effective_phase"], "resume_parent_pending")

    def test_collection_filters_manual_status_and_umbrella_candidates_in_stable_order(self) -> None:
        for source in ("manual", "status", "umbrella"):
            with self.subTest(source=source), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                (root / ".git").mkdir()
                mismatch = "docs/plans/260718_0100_custom.md"
                either = "docs/plans/260718_0101_either.md"
                matching = "docs/plans/260718_0102_collab.md"
                self._write_plan(root, mismatch, meta_json=self._manager_mode_meta("manager-custom-pipeline"))
                self._write_plan(root, either, meta_json=self._manager_mode_meta("either"))
                self._write_plan(root, matching, meta_json=self._manager_mode_meta("manager-collab"))
                paths = self._queue_paths(root)

                if source == "manual":
                    result = MODULE.set_queue(
                        paths,
                        plans=[mismatch, either, matching],
                        manager_mode="manager-collab",
                        now="2026-07-18T01:00:00Z",
                    )
                elif source == "status":
                    result = MODULE.set_queue(
                        paths,
                        statuses=["Ready for Coder"],
                        manager_mode="manager-collab",
                        now="2026-07-18T01:00:00Z",
                    )
                else:
                    umbrella = "docs/plans/260718_0103_umbrella.md"
                    self._write_plan(
                        root,
                        umbrella,
                        meta_json=self._manager_mode_meta("either"),
                        execution_queue=(
                            "- Resume parent: `none`\n"
                            f"- Plan: `{mismatch}`\n"
                            f"- Plan: `{either}`\n"
                            f"- Plan: `{matching}`"
                        ),
                    )
                    result = MODULE.set_queue(
                        paths,
                        umbrella=umbrella,
                        manager_mode="manager-collab",
                        now="2026-07-18T01:00:00Z",
                    )

                skip_logs = [
                    entry
                    for entry in MODULE.parse_log_entries(paths)
                    if entry["event"] == "skip_manager_mode"
                ]

            self.assertEqual([item["plan"] for item in result["items"]], [either, matching])
            self.assertEqual([item["order"] for item in result["items"]], [1, 2])
            self.assertEqual(
                result["skipped_incompatible"],
                [
                    {
                        "plan": mismatch,
                        "skip_phase": "collection",
                        "required_manager_mode": "manager-custom-pipeline",
                        "actual_manager_mode": "manager-collab",
                        "manager_mode_state": "mismatch",
                        "manager_mode_reason": "required_mode_mismatch",
                    }
                ],
            )
            self.assertEqual(len(skip_logs), 1)
            self.assertEqual(skip_logs[0]["skip_phase"], "collection")

    def test_all_filtered_set_preserves_state_bytes_and_append_separates_skip_from_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            existing = "docs/plans/260718_0110_existing.md"
            incompatible = "docs/plans/260718_0111_custom.md"
            self._write_plan(root, existing, meta_json=self._manager_mode_meta("either"))
            self._write_plan(root, incompatible, meta_json=self._manager_mode_meta("manager-custom-pipeline"))
            paths = self._queue_paths(root)
            MODULE.set_queue(paths, plans=[existing], now="2026-07-18T01:10:00Z")
            state_before = paths.state_path.read_bytes()
            log_before = paths.log_path.read_bytes()

            filtered = MODULE.set_queue(
                paths,
                plans=[incompatible],
                manager_mode="manager-collab",
                now="2026-07-18T01:10:01Z",
            )
            state_after = paths.state_path.read_bytes()
            log_after = paths.log_path.read_bytes()
            plain = MODULE.render_snapshot(filtered)
            appended = MODULE.append_queue(
                paths,
                [existing, incompatible],
                manager_mode="manager-collab",
                now="2026-07-18T01:10:02Z",
            )

        self.assertFalse(filtered["replaced"])
        self.assertEqual(state_after, state_before)
        self.assertNotEqual(log_after, log_before)
        self.assertIn("phase=collection", plain)
        self.assertIn("state=mismatch", plain)
        self.assertIn("reason=required_mode_mismatch", plain)
        self.assertEqual(appended["skipped_duplicates"], [existing])
        self.assertEqual([row["plan"] for row in appended["skipped_incompatible"]], [incompatible])
        self.assertEqual(appended["appended"], [])

    def test_all_filtered_set_without_existing_queue_keeps_state_absent_and_renders_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            incompatible = "docs/plans/260718_0112_custom.md"
            self._write_plan(
                root,
                incompatible,
                meta_json=self._manager_mode_meta("manager-custom-pipeline"),
            )
            paths = self._queue_paths(root)

            filtered = MODULE.set_queue(
                paths,
                plans=[incompatible],
                manager_mode="manager-collab",
                now="2026-07-18T01:11:00Z",
            )

            plain = MODULE.render_snapshot(filtered)
            history_plain = MODULE.render_history_report(
                MODULE.queue_history_report(paths, limit=0)
            )

        self.assertFalse(filtered["exists"])
        self.assertFalse(filtered["replaced"])
        self.assertFalse(paths.state_path.exists())
        self.assertEqual(filtered["skipped_incompatible"][0]["plan"], incompatible)
        self.assertIn("queue: empty", plain)
        self.assertIn(f"skipped_incompatible={incompatible}", plain)
        self.assertIn("phase=collection", plain)
        self.assertIn("event=skip_manager_mode", history_plain)
        self.assertIn("manager_mode_reason=required_mode_mismatch", history_plain)

    def test_set_refuses_active_replacement_before_filter_or_audit_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            active = "docs/plans/260718_0120_active.md"
            candidate = "docs/plans/260718_0121_custom.md"
            self._write_plan(root, active, meta_json=self._manager_mode_meta("either"))
            self._write_plan(root, candidate, meta_json=self._manager_mode_meta("manager-custom-pipeline"))
            paths = self._queue_paths(root)
            MODULE.set_queue(paths, plans=[active], now="2026-07-18T01:20:00Z")
            MODULE.activate_next(paths, now="2026-07-18T01:20:01Z")
            state_before = paths.state_path.read_bytes()
            log_before = paths.log_path.read_bytes()
            active_plan_before = (root / active).read_bytes()

            with self.assertRaises(MODULE.QueueError) as raised:
                MODULE.set_queue(
                    paths,
                    plans=[candidate],
                    manager_mode="manager-collab",
                    now="2026-07-18T01:20:02Z",
                )
            state_after = paths.state_path.read_bytes()
            log_after = paths.log_path.read_bytes()
            active_plan_after = (root / active).read_bytes()

        self.assertEqual(raised.exception.payload["error"], "queue_active_replacement_blocked")
        self.assertEqual(state_after, state_before)
        self.assertEqual(log_after, log_before)
        self.assertEqual(active_plan_after, active_plan_before)

    def test_pending_skip_blocks_compatible_dependent_without_status_rewrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            prerequisite = "docs/plans/260718_0130_custom_prerequisite.md"
            dependent = "docs/plans/260718_0131_collab_dependent.md"
            dependent_meta = json.loads(self._manager_mode_meta("manager-collab"))
            dependent_meta["plan_meta"]["depends_on"] = [prerequisite]
            self._write_plan(
                root,
                prerequisite,
                meta_json=self._manager_mode_meta("manager-custom-pipeline"),
            )
            self._write_plan(root, dependent, meta_json=json.dumps(dependent_meta))
            paths = self._queue_paths(root)
            MODULE.set_queue(
                paths,
                plans=[prerequisite, dependent],
                now="2026-07-18T01:30:00Z",
            )
            prerequisite_before = (root / prerequisite).read_bytes()

            with self.assertRaises(MODULE.QueueError) as raised:
                MODULE.activate_next(
                    paths,
                    manager_mode="manager-collab",
                    now="2026-07-18T01:30:01Z",
                )

            state = MODULE.load_state(paths)
            assert state is not None
            prerequisite_after = (root / prerequisite).read_bytes()

        self.assertIn("depends_on_skipped_incompatible", str(raised.exception))
        self.assertEqual(state["items"][0]["state"], "skipped_manager_mode")
        self.assertEqual(state["items"][1]["state"], "pending")
        self.assertEqual(prerequisite_after, prerequisite_before)

    def test_next_skips_pending_mismatch_and_activates_next_compatible_item(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            incompatible = "docs/plans/260718_0140_custom.md"
            compatible = "docs/plans/260718_0141_collab.md"
            self._write_plan(
                root,
                incompatible,
                meta_json=self._manager_mode_meta("manager-custom-pipeline"),
            )
            self._write_plan(
                root,
                compatible,
                meta_json=self._manager_mode_meta("manager-collab"),
            )
            paths = self._queue_paths(root)
            MODULE.set_queue(
                paths,
                plans=[incompatible, compatible],
                now="2026-07-18T01:40:00Z",
            )

            activated = MODULE.activate_next(
                paths,
                manager_mode="manager-collab",
                now="2026-07-18T01:40:01Z",
            )

        self.assertTrue(activated["activated"])
        self.assertEqual(activated["active_plan"], compatible)
        self.assertEqual(activated["items"][0]["state"], "skipped_manager_mode")
        self.assertEqual(activated["items"][1]["state"], "active")
        self.assertEqual(activated["skipped_manager_mode_count"], 1)
        self.assertEqual(
            self._plan_lint_runner.call_args_list,
            [mock.call(root / compatible, context=mock.ANY)],
        )

    def test_mode_aware_closeout_rejects_missing_invalid_and_resumed_parent_mismatch(self) -> None:
        cases = (
            ("missing", False, lambda _actual: None),
            ("invalid", True, lambda _actual: "manager-unknown"),
        )
        expected = {
            "missing": ("unclassified_missing", "required_mode_missing", "missing"),
            "invalid": ("invalid_required_mode", "required_mode_invalid", "plan_meta.required_manager_mode"),
        }
        for actual_mode in MODULE.plan_status_oracle.ACTUAL_MANAGER_MODES:
            for case_name, include, required_factory in cases:
                for candidate_kind in ("next_plan", "resume_parent_plan"):
                    with (
                        self.subTest(
                            actual_mode=actual_mode,
                            case=case_name,
                            candidate_kind=candidate_kind,
                        ),
                        tempfile.TemporaryDirectory() as tmpdir,
                    ):
                        root = Path(tmpdir)
                        (root / ".git").mkdir()
                        required_mode = required_factory(actual_mode)
                        paths, _active_rel, candidate_rel = self._prepare_mode_closeout_queue(
                            root,
                            candidate_kind=candidate_kind,
                            candidate_meta=self._manager_mode_meta(required_mode, include=include),
                        )
                        state_before = paths.state_path.read_bytes()
                        log_before = paths.log_path.read_bytes()
                        parsed_before = MODULE.load_state(paths)

                        with self.assertRaises(MODULE.QueueError) as raised:
                            MODULE.closeout_queue(
                                paths,
                                manager_mode=actual_mode,
                                now="2026-07-17T19:00:02Z",
                            )

                        payload = raised.exception.payload
                        assert payload is not None
                        state_name, reason, source = expected[case_name]
                        self.assertFalse(payload["advanced"])
                        self.assertEqual(payload["error"], "manager_mode_admission_blocked")
                        self.assertEqual(payload["candidate_kind"], candidate_kind)
                        self.assertEqual(payload["candidate_plan"], candidate_rel)
                        self.assertIsNone(payload["required_manager_mode"])
                        self.assertEqual(payload["actual_manager_mode"], actual_mode)
                        self.assertEqual(payload["manager_mode_source"], source)
                        self.assertEqual(payload["manager_mode_state"], state_name)
                        self.assertFalse(payload["manager_mode_admitted"])
                        self.assertEqual(payload["manager_mode_reason"], reason)
                        self.assertEqual(paths.state_path.read_bytes(), state_before)
                        self.assertEqual(paths.log_path.read_bytes(), log_before)
                        self.assertEqual(MODULE.load_state(paths), parsed_before)
                        self.assertFalse(paths.txn_path.exists())

            with self.subTest(actual_mode=actual_mode, case="resumed_parent_mismatch"), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                (root / ".git").mkdir()
                required_mode = next(
                    mode for mode in MODULE.plan_status_oracle.ACTUAL_MANAGER_MODES if mode != actual_mode
                )
                paths, _active_rel, candidate_rel = self._prepare_mode_closeout_queue(
                    root,
                    candidate_kind="resume_parent_plan",
                    candidate_meta=self._manager_mode_meta(required_mode),
                )
                state_before = paths.state_path.read_bytes()
                log_before = paths.log_path.read_bytes()

                with self.assertRaises(MODULE.QueueError) as raised:
                    MODULE.closeout_queue(
                        paths,
                        manager_mode=actual_mode,
                        now="2026-07-17T19:00:02Z",
                    )

                payload = raised.exception.payload
                assert payload is not None
                self.assertEqual(payload["closeout_kind"], "manager_mode_mismatch")
                self.assertEqual(payload["candidate_kind"], "resume_parent_plan")
                self.assertEqual(payload["candidate_plan"], candidate_rel)
                self.assertEqual(payload["manager_mode_state"], "mismatch")
                self.assertEqual(payload["manager_mode_reason"], "required_mode_mismatch")
                self.assertEqual(paths.state_path.read_bytes(), state_before)
                self.assertEqual(paths.log_path.read_bytes(), log_before)

    def test_mode_aware_closeout_skips_pending_mismatch_with_matching_state_log_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            paths, active_rel, candidate_rel = self._prepare_mode_closeout_queue(
                root,
                candidate_kind="next_plan",
                candidate_meta=self._manager_mode_meta("manager-custom-pipeline"),
            )
            candidate_before = (root / candidate_rel).read_bytes()

            closeout = MODULE.closeout_queue(
                paths,
                manager_mode="manager-collab",
                now="2026-07-17T19:00:02Z",
            )

            state = MODULE.load_state(paths)
            assert state is not None
            skipped = state["items"][1]
            receipt = closeout["skipped_incompatible"][0]
            skip_log = next(
                entry
                for entry in MODULE.parse_log_entries(paths)
                if entry["event"] == "skip_manager_mode"
            )
            candidate_after = (root / candidate_rel).read_bytes()

        self.assertTrue(closeout["advanced"])
        self.assertEqual(closeout["finalized_plan"], active_rel)
        self.assertTrue(closeout["queue_complete"])
        self.assertEqual(skipped["state"], "skipped_manager_mode")
        self.assertEqual(skipped["closeout_kind"], "manager_mode_mismatch")
        self.assertRegex(receipt["manager_mode_skip_id"], r"^[0-9a-f]{32}$")
        self.assertEqual(
            receipt,
            {
                "plan": candidate_rel,
                "order": 2,
                "skip_phase": "activation",
                "manager_mode_skip_id": receipt["manager_mode_skip_id"],
                "required_manager_mode": "manager-custom-pipeline",
                "actual_manager_mode": "manager-collab",
                "manager_mode_state": "mismatch",
                "manager_mode_reason": "required_mode_mismatch",
            },
        )
        for key, value in receipt.items():
            self.assertEqual(skipped[key], value)
            self.assertEqual(str(skip_log[key]), str(value))
        self.assertEqual(candidate_after, candidate_before)

    def test_closeout_surfaces_dependent_blocker_after_skipping_incompatible_prerequisite(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            active = "docs/plans/260718_0150_active_done.md"
            prerequisite = "docs/plans/260718_0151_custom_prerequisite.md"
            dependent = "docs/plans/260718_0152_collab_dependent.md"
            dependent_meta = json.loads(self._manager_mode_meta("manager-collab"))
            dependent_meta["plan_meta"]["depends_on"] = [prerequisite]
            self._write_plan(
                root,
                active,
                status="Done",
                meta_json=self._manager_mode_meta("either"),
            )
            self._write_plan(
                root,
                prerequisite,
                meta_json=self._manager_mode_meta("manager-custom-pipeline"),
            )
            self._write_plan(root, dependent, meta_json=json.dumps(dependent_meta))
            paths = self._queue_paths(root)
            MODULE.set_queue(
                paths,
                plans=[active, prerequisite, dependent],
                now="2026-07-18T01:50:00Z",
            )
            MODULE.activate_next(paths, now="2026-07-18T01:50:01Z")
            self._plan_lint_runner.reset_mock()
            prerequisite_before = (root / prerequisite).read_bytes()

            closeout = MODULE.closeout_queue(
                paths,
                manager_mode="manager-collab",
                now="2026-07-18T01:50:02Z",
            )

            shown = MODULE.show_queue(paths)
            history = MODULE.queue_history_report(paths, limit=0)
            plain = MODULE.render_snapshot(shown)
            history_plain = MODULE.render_history_report(history)
            prerequisite_after = (root / prerequisite).read_bytes()
            events = [entry["event"] for entry in MODULE.parse_log_entries(paths)]

        blocker = (
            f"depends_on_skipped_incompatible: {dependent} depends_on {prerequisite} "
            "state=skipped_manager_mode"
        )
        self.assertTrue(closeout["advanced"])
        self.assertFalse(closeout["queue_complete"])
        self.assertIsNone(closeout["next_plan"])
        self.assertEqual(closeout["activation_blocker"], blocker)
        self.assertEqual(closeout["skipped_incompatible"][0]["plan"], prerequisite)
        self.assertEqual([item["state"] for item in shown["items"]], ["done", "skipped_manager_mode", "pending"])
        self.assertEqual(shown["skipped_manager_mode_count"], 1)
        self.assertEqual(shown["last_transition"]["kind"], "advance_blocked")
        self.assertEqual(shown["last_transition"]["activation_blocker"], blocker)
        self.assertIn(f"activation_blocker={blocker}", plain)
        self.assertIn(f"plan={prerequisite}", history_plain)
        self.assertIn("event=skip_manager_mode", history_plain)
        self.assertIn("manager_mode_skip_id=", history_plain)
        self.assertIn("manager_mode_reason=required_mode_mismatch", history_plain)
        self.assertEqual(events.count("skip_manager_mode"), 1)
        self.assertEqual(events.count("complete"), 1)
        self.assertNotIn("advance", events)
        self.assertEqual(prerequisite_after, prerequisite_before)
        self._plan_lint_runner.assert_not_called()

    def test_mode_aware_closeout_carrier_error_is_not_a_mode_verdict(self) -> None:
        for candidate_kind in ("next_plan", "resume_parent_plan"):
            with self.subTest(candidate_kind=candidate_kind), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                (root / ".git").mkdir()
                paths, _active_rel, candidate_rel = self._prepare_mode_closeout_queue(
                    root,
                    candidate_kind=candidate_kind,
                    candidate_meta=self._manager_mode_meta("either"),
                )
                (root / candidate_rel).write_text(
                    "# Plan: malformed mode carrier\n\n"
                    "**Status:** Ready for Coder\n\n"
                    "```json\n"
                    '{"plan_meta":\n'
                    "```\n",
                    encoding="utf-8",
                )
                state_before = paths.state_path.read_bytes()
                log_before = paths.log_path.read_bytes()

                with self.assertRaises(MODULE.QueueError) as raised:
                    MODULE.closeout_queue(
                        paths,
                        manager_mode="manager-collab",
                        now="2026-07-17T19:00:02Z",
                    )

                payload = raised.exception.payload
                assert payload is not None
                self.assertEqual(payload["error"], "manager_mode_admission_carrier_error")
                self.assertFalse(payload["advanced"])
                self.assertEqual(payload["candidate_kind"], candidate_kind)
                self.assertEqual(payload["candidate_plan"], candidate_rel)
                self.assertNotIn("closeout_kind", payload)
                self.assertNotIn("manager_mode_state", payload)
                self.assertEqual(paths.state_path.read_bytes(), state_before)
                self.assertEqual(paths.log_path.read_bytes(), log_before)
                self.assertFalse(paths.txn_path.exists())

    def test_unqualified_closeout_cannot_activate_a_transition_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            paths, _active_rel, candidate_rel = self._prepare_mode_closeout_queue(
                root,
                candidate_kind="next_plan",
                candidate_meta=self._manager_mode_meta("either"),
            )
            state_before = paths.state_path.read_bytes()
            log_before = paths.log_path.read_bytes()

            with self.assertRaises(MODULE.QueueError) as raised:
                MODULE.closeout_queue(paths, now="2026-07-17T19:00:02Z")

            payload = raised.exception.payload
            assert payload is not None
            self.assertEqual(payload["error"], "manager_mode_required")
            self.assertEqual(payload["candidate_kind"], "next_plan")
            self.assertEqual(payload["candidate_plan"], candidate_rel)
            self.assertEqual(paths.state_path.read_bytes(), state_before)
            self.assertEqual(paths.log_path.read_bytes(), log_before)
            self.assertFalse(paths.txn_path.exists())
            stderr = io.StringIO()
            with mock.patch("sys.stderr", stderr), self.assertRaises(SystemExit) as exited:
                MODULE.main(
                    [
                        "--project-root",
                        str(root),
                        "closeout",
                        "--json",
                    ]
                )
            self.assertEqual(exited.exception.code, 2)
            self.assertIn("--manager-mode", stderr.getvalue())
            self.assertEqual(paths.state_path.read_bytes(), state_before)
            self.assertEqual(paths.log_path.read_bytes(), log_before)

    def test_cli_mode_rejection_allows_exactly_one_separate_bounded_stop(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            paths, active_rel, candidate_rel = self._prepare_mode_closeout_queue(
                root,
                candidate_kind="next_plan",
                candidate_meta=self._manager_mode_meta("either"),
            )
            self._write_plan(
                root,
                active_rel,
                status="Done",
                meta_json=self._manager_mode_meta("manager-custom-pipeline"),
            )
            state_before = paths.state_path.read_bytes()
            log_before = paths.log_path.read_bytes()
            semantic_before = MODULE.load_state(paths)
            stdout = io.StringIO()
            stderr = io.StringIO()

            with mock.patch("sys.stdout", stdout), mock.patch("sys.stderr", stderr):
                result = MODULE.main(
                    [
                        "--project-root",
                        str(root),
                        "closeout",
                        "--manager-mode",
                        "manager-collab",
                        "--json",
                    ]
                )

            payload = json.loads(stdout.getvalue())
            self.assertEqual(result, 1)
            self.assertEqual(stderr.getvalue(), "")
            self.assertEqual(payload["closeout_kind"], "manager_mode_mismatch")
            self.assertEqual(payload["candidate_kind"], "active_plan")
            self.assertEqual(payload["candidate_plan"], active_rel)
            self.assertEqual(paths.state_path.read_bytes(), state_before)
            self.assertEqual(paths.log_path.read_bytes(), log_before)

            stopped = MODULE.stop_queue(
                paths,
                "manager_mode_mismatch",
                now="2026-07-17T19:00:03Z",
            )
            semantic_after = MODULE.load_state(paths)
            assert semantic_before is not None and semantic_after is not None
            self.assertEqual(semantic_after["items"], semantic_before["items"])
            self.assertEqual(semantic_after["cursor"], semantic_before["cursor"])
            self.assertEqual(semantic_after["last_transition"], semantic_before["last_transition"])
            self.assertEqual(stopped["active_plan"], active_rel)
            self.assertEqual(stopped["last_stop"]["reason"], "manager_mode_mismatch")
            new_entries = MODULE.parse_log_entries(paths)[-1:]
            self.assertEqual([entry["event"] for entry in new_entries], ["stop"])
            self.assertFalse(paths.txn_path.exists())

    def test_mode_aware_closeout_skips_supported_append_after_advisory_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            active_rel = "docs/plans/260717_2210_interleaved_active_done.md"
            candidate_rel = "docs/plans/260717_2211_interleaved_opposite.md"
            self._write_plan(
                root,
                active_rel,
                status="Done",
                meta_json=self._manager_mode_meta("either"),
            )
            self._write_plan(
                root,
                candidate_rel,
                meta_json=self._manager_mode_meta("manager-custom-pipeline"),
            )
            paths = self._queue_paths(root)
            MODULE.set_queue(paths, plans=[active_rel], now="2026-07-17T19:10:00Z")
            MODULE.activate_next(paths, now="2026-07-17T19:10:01Z")

            advisory = MODULE.show_queue(paths)
            self.assertIsNone(advisory["next_pending_plan"])
            MODULE.append_queue(paths, [candidate_rel], now="2026-07-17T19:10:02Z")
            candidate_before = (root / candidate_rel).read_bytes()
            stdout = io.StringIO()

            with mock.patch("sys.stdout", stdout):
                result = MODULE.main(
                    [
                        "--project-root",
                        str(root),
                        "closeout",
                        "--manager-mode",
                        "manager-collab",
                        "--json",
                    ]
                )

            payload = json.loads(stdout.getvalue())
            self.assertEqual(result, 0)
            self.assertEqual(payload["skipped_incompatible"][0]["plan"], candidate_rel)
            self.assertEqual(payload["skipped_incompatible"][0]["skip_phase"], "activation")
            self.assertEqual(payload["skipped_incompatible"][0]["manager_mode_state"], "mismatch")
            self.assertEqual(
                payload["skipped_incompatible"][0]["manager_mode_reason"],
                "required_mode_mismatch",
            )
            state_after = MODULE.load_state(paths)
            assert state_after is not None
            self.assertEqual(state_after["cursor"], 2)
            self.assertEqual(state_after["items"][0]["state"], "done")
            self.assertEqual(state_after["items"][1]["state"], "skipped_manager_mode")
            self.assertEqual((root / candidate_rel).read_bytes(), candidate_before)
            self.assertIsNone(state_after["last_stop"])
            self.assertFalse(paths.txn_path.exists())

    def test_closeout_keeps_executable_ready_for_planner_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            self._write_plan(root, "docs/plans/260328_0800_exec.md", status="Ready for Planner")
            paths = self._queue_paths(root)

            MODULE.set_queue(paths, plans=["docs/plans/260328_0800_exec.md"], now="2026-03-28T02:40:00Z")
            MODULE.activate_next(paths, now="2026-03-28T02:41:00Z")
            closeout = MODULE.closeout_queue(paths, now="2026-03-28T02:42:00Z")

        self.assertFalse(closeout["advanced"])
        self.assertEqual(closeout["runtime_class"], "executable")
        self.assertEqual(closeout["closeout_kind"], "not_ready")
        self.assertEqual(closeout["active_plan"], "docs/plans/260328_0800_exec.md")
        self.assertFalse(closeout["queue_empty"])

    def test_closeout_advances_parked_umbrella_ready_for_planner(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            child_rel = "docs/plans/260328_0802_next.md"
            parked_meta = dedent(
                """\
                {
                  "plan_meta": {
                    "cluster": "process",
                    "tags": [],
                    "required_manager_mode": "either",
                    "phase_overlay": "decomposition_wave",
                    "phase_state": "parked",
                    "parent": null,
                    "next_plans": ["__CHILD__"],
                    "depends_on": [],
                    "followups_out": [],
                    "canon_updates": [],
                    "machine_authority_decision": {
                      "schema_version": "machine_authority_decision.v1",
                      "applicability": "not_applicable",
                      "reason_code": "no_machine_authority_change"
                    }
                  }
                }
                """
            ).replace("__CHILD__", child_rel).strip()
            parked_handoffs = dedent(
                """\
                - `Ready for Planner` — Architect
                - `Ready for Coder` — `N/A (parked umbrella)`
                - `Ready for Review` — `N/A (parked umbrella)`
                - `Ready for Arch review` — `N/A (parked umbrella)`
                - `Done` — Architect
                """
            ).rstrip()
            self._write_plan(
                root,
                "docs/plans/260328_0801_parent.md",
                status="Ready for Planner",
                meta_json=parked_meta,
                execution_queue=f"- Plan: `{child_rel}`",
                handoff_statuses=parked_handoffs,
                context_links="- Code draft(s): `N/A (why=parked umbrella)`",
            )
            self._write_small_model_ready_child(root, child_rel)
            paths = self._queue_paths(root)

            MODULE.set_queue(
                paths,
                plans=["docs/plans/260328_0801_parent.md", "docs/plans/260328_0802_next.md"],
                now="2026-03-28T02:45:00Z",
            )
            MODULE.activate_next(paths, now="2026-03-28T02:46:00Z")
            closeout = MODULE.closeout_queue(
                paths,
                manager_mode="manager-collab",
                now="2026-03-28T02:47:00Z",
            )

        self.assertTrue(closeout["advanced"])
        self.assertEqual(closeout["runtime_class"], "parked_umbrella")
        self.assertEqual(closeout["closeout_kind"], "non_executable_ready")
        self.assertEqual(closeout["final_status"], "Ready for Planner")
        self.assertEqual(closeout["next_plan"], "docs/plans/260328_0802_next.md")
        self.assertEqual(closeout["items"][0]["state"], MODULE.CLOSED_NON_EXECUTABLE_STATE)
        self.assertNotIn("final_docs_commit", closeout)

    def test_closeout_keeps_strict_na_candidate_with_missing_graph_non_queueable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            candidate_rel = "docs/plans/260823_1509_strict_na_candidate.md"
            candidate_meta = dedent(
                """\
                {
                  "plan_meta": {
                    "cluster": "process",
                    "tags": [],
                    "required_manager_mode": "either",
                    "phase_overlay": "decomposition_wave",
                    "phase_state": "active",
                    "parent": null,
                    "next_plans": [],
                    "depends_on": [],
                    "followups_out": [],
                    "canon_updates": [],
                    "machine_authority_decision": {
                      "schema_version": "machine_authority_decision.v1",
                      "applicability": "not_applicable",
                      "reason_code": "no_machine_authority_change"
                    }
                  }
                }
                """
            ).strip()
            self._write_plan(
                root,
                candidate_rel,
                status="Ready for Planner",
                meta_json=candidate_meta,
                execution_queue="- Plan: `N/A (why=child graph is not materialized)`",
                context_links="- Code draft(s): `N/A (why=strict candidate fixture)`",
            )
            paths = self._queue_paths(root)
            MODULE.set_queue(paths, plans=[candidate_rel], now="2026-08-23T12:00:00Z")
            MODULE.activate_next(paths, now="2026-08-23T12:01:00Z")
            closeout = MODULE.closeout_queue(paths, now="2026-08-23T12:02:00Z")

        self.assertFalse(closeout["advanced"])
        self.assertEqual(closeout["runtime_class"], "executable")
        self.assertEqual(closeout["closeout_kind"], "decomposition_children_missing")
        self.assertEqual(closeout["active_plan"], candidate_rel)

    def test_closeout_advances_routing_only_baseline_ready_for_planner(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            routing_handoffs = dedent(
                """\
                - `Ready for Planner` — Architect
                - `Ready for Coder` — `N/A (routing-only baseline)`
                - `Ready for Review` — `N/A (routing-only baseline)`
                - `Ready for Arch review` — `N/A (routing-only baseline)`
                - `Done` — Architect
                """
            ).rstrip()
            self._write_plan(
                root,
                "docs/plans/260328_0803_baseline.md",
                status="Ready for Planner",
                handoff_statuses=routing_handoffs,
                context_links="- Code draft(s): `N/A (routing-only baseline)`",
            )
            paths = self._queue_paths(root)

            MODULE.set_queue(paths, plans=["docs/plans/260328_0803_baseline.md"], now="2026-03-28T02:50:00Z")
            MODULE.activate_next(paths, now="2026-03-28T02:51:00Z")
            closeout = MODULE.closeout_queue(paths, now="2026-03-28T02:52:00Z")

        self.assertTrue(closeout["advanced"])
        self.assertEqual(closeout["runtime_class"], "routing_only_baseline")
        self.assertTrue(closeout["queue_complete"])
        self.assertEqual(closeout["items"][0]["final_status"], "Ready for Planner")

    def test_closeout_advances_verified_reference_child_ready_for_planner(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            child_meta = dedent(
                """\
                {
                  "plan_meta": {
                    "cluster": "process",
                    "tags": [],
                    "phase_overlay": null,
                    "phase_state": null,
                    "parent": "docs/plans/260328_0804_parent_master.md",
                    "next_plans": [],
                    "depends_on": [],
                    "followups_out": [],
                    "canon_updates": [],
                    "machine_authority_decision": {
                      "schema_version": "machine_authority_decision.v1",
                      "applicability": "not_applicable",
                      "reason_code": "no_machine_authority_change"
                    }
                  }
                }
                """
            ).strip()
            reference_handoffs = dedent(
                """\
                - `Ready for Planner` — Architect
                - `Ready for Coder` — `N/A (verified reference child)`
                - `Ready for Review` — `N/A (verified reference child)`
                - `Ready for Arch review` — `N/A (verified reference child)`
                - `Done` — Architect
                """
            ).rstrip()
            self._write_plan(
                root,
                "docs/plans/260328_0805_child.md",
                status="Ready for Planner",
                meta_json=child_meta,
                handoff_statuses=reference_handoffs,
                context_links="- Code draft(s): `N/A (verified reference child)`",
            )
            paths = self._queue_paths(root)

            MODULE.set_queue(paths, plans=["docs/plans/260328_0805_child.md"], now="2026-03-28T02:55:00Z")
            MODULE.activate_next(paths, now="2026-03-28T02:56:00Z")
            closeout = MODULE.closeout_queue(paths, now="2026-03-28T02:57:00Z")

        self.assertTrue(closeout["advanced"])
        self.assertEqual(closeout["runtime_class"], "verified_reference_child")
        self.assertEqual(closeout["items"][0]["state"], MODULE.CLOSED_NON_EXECUTABLE_STATE)

    def test_closeout_keeps_ambiguous_non_executable_markers_stopped(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            ambiguous_handoffs = dedent(
                """\
                - `Ready for Planner` — Architect
                - `Ready for Coder` — `N/A (maybe baseline)`
                - `Ready for Review` — Coder
                - `Ready for Arch review` — `N/A (maybe baseline)`
                - `Done` — Architect
                """
            ).rstrip()
            self._write_plan(
                root,
                "docs/plans/260328_0806_ambiguous.md",
                status="Ready for Planner",
                handoff_statuses=ambiguous_handoffs,
                context_links="- Code draft(s): `N/A (ambiguous markers)`",
            )
            paths = self._queue_paths(root)

            MODULE.set_queue(paths, plans=["docs/plans/260328_0806_ambiguous.md"], now="2026-03-28T03:00:00Z")
            MODULE.activate_next(paths, now="2026-03-28T03:01:00Z")
            closeout = MODULE.closeout_queue(paths, now="2026-03-28T03:02:00Z")

        self.assertFalse(closeout["advanced"])
        self.assertEqual(closeout["runtime_class"], "executable")
        self.assertEqual(closeout["closeout_kind"], "not_ready")

    def test_all_writer_entrypoints_emit_transaction_rows_and_keep_lock_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            first_rel = "docs/plans/260712_1844_first.md"
            second_rel = "docs/plans/260712_1845_second.md"
            self._write_plan(root, first_rel, status="Done")
            second = self._write_plan(root, second_rel)
            paths = self._queue_paths(root)

            MODULE.set_queue(paths, plans=[first_rel, second_rel], now="2026-07-12T15:44:00Z")
            lock_inode = paths.lock_path.stat().st_ino
            MODULE.activate_next(paths, now="2026-07-12T15:44:01Z")
            MODULE.stop_queue(paths, "fixture_stop", now="2026-07-12T15:44:02Z")
            MODULE.mark_planpath_override(paths, first_rel, reason="fixture_override")
            MODULE.advance_queue(paths, "Done", now="2026-07-12T15:44:03Z")
            MODULE.append_queue(paths, [first_rel], now="2026-07-12T15:44:04Z")
            second.write_text(
                second.read_text(encoding="utf-8").replace(
                    "**Status:** Ready for Coder",
                    "**Status:** Done",
                ),
                encoding="utf-8",
            )
            MODULE.closeout_queue(paths, now="2026-07-12T15:44:05Z")
            MODULE.clear_queue(paths)

            entries = MODULE.parse_log_entries(paths)
            metrics_log = METRICS_MODULE.parse_queue_log(paths.log_path)
            events = [entry["event"] for entry in entries]
            lock_exists = paths.lock_path.exists()
            lock_inode_after = paths.lock_path.stat().st_ino
            marker_exists = paths.txn_path.exists()
            state_exists = paths.state_path.exists()

        self.assertEqual(
            events,
            ["set", "activate", "stop", "planpath_override", "complete", "advance", "append", "complete", "clear"],
        )
        self.assertTrue(all(entry.get("transaction_id") for entry in entries))
        self.assertTrue(all(int(entry["transaction_seq"]) >= 1 for entry in entries))
        self.assertTrue(all(int(entry["transaction_size"]) >= int(entry["transaction_seq"]) for entry in entries))
        self.assertEqual(metrics_log.malformed_rows, [])
        self.assertEqual(metrics_log.malformed_field_chunks, [])
        self.assertTrue(
            all(
                {"transaction_id", "transaction_seq", "transaction_size"} <= set(entry)
                for entry in metrics_log.entries
            )
        )
        self.assertTrue(lock_exists)
        self.assertEqual(lock_inode_after, lock_inode)
        self.assertEqual(MODULE.LOCK_TIMEOUT_SECONDS, 10.0)
        self.assertFalse(marker_exists)
        self.assertFalse(state_exists)

    def test_writer_sanitizes_all_line_separators_before_history_commit(self) -> None:
        separators = ("\r", "\n", "\v", "\f", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029")
        for separator in separators:
            with self.subTest(separator=repr(separator)), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                (root / ".git").mkdir()
                plan_rel = "docs/plans/260712_1843_separator_fixture.md"
                self._write_plan(root, plan_rel)
                paths = self._queue_paths(root)
                MODULE.set_queue(paths, plans=[plan_rel], now="2026-07-12T15:43:00Z")
                MODULE.activate_next(paths, now="2026-07-12T15:43:01Z")

                MODULE.stop_queue(
                    paths,
                    f"left{separator}right",
                    now="2026-07-12T15:43:02Z",
                )

                entries = MODULE.parse_log_entries(paths)
                stop_entry = next(entry for entry in entries if entry["event"] == "stop")
                self.assertEqual(stop_entry["reason"], "left right")
                self.assertEqual(MODULE._classify_recovery(paths)["classification"], "clean")
                self.assertFalse(paths.txn_path.exists())

    def test_recovery_phase_matrix_is_idempotent_and_prefix_based(self) -> None:
        phase_expectations = {
            "marker": "not_applied",
            "state": "state_applied_history_missing",
            "history:1": "state_applied_history_missing",
            "history": "already_complete",
        }
        for phase, expected in phase_expectations.items():
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                (root / ".git").mkdir()
                paths = self._queue_paths(root)
                after_state = MODULE.build_state(
                    mode="phase_fixture",
                    items=[],
                    now="2026-07-12T15:45:00Z",
                )
                after_state["phase"] = phase

                def interrupt(current: str, _paths: MODULE.QueuePaths, _marker: dict[str, object]) -> None:
                    if current == phase:
                        raise RuntimeError(f"interrupt:{phase}")

                MODULE._TRANSACTION_PHASE_HOOK = interrupt
                try:
                    with self.assertRaisesRegex(RuntimeError, f"interrupt:{phase}"):
                        with MODULE.queue_lock(paths, "exclusive", command="fixture", timeout=0.1):
                            MODULE._commit_transaction(
                                paths,
                                operation="fixture",
                                after_state=after_state,
                                audit_rows=[
                                    MODULE._audit_row("first", at="2026-07-12T15:45:00Z", value="a"),
                                    MODULE._audit_row("second", at="2026-07-12T15:45:00Z", value="b"),
                                ],
                            )
                finally:
                    MODULE._TRANSACTION_PHASE_HOOK = None

                first_recover = MODULE.recover_queue(paths)
                second_recover = MODULE.recover_queue(paths)
                entries = MODULE.parse_log_entries(paths)

                self.assertEqual(first_recover["classification"], expected)
                self.assertEqual(first_recover["result"], "recovered")
                self.assertTrue(first_recover["mutation_performed"])
                self.assertEqual(second_recover["classification"], "clean")
                self.assertEqual(second_recover["result"], "clean")
                self.assertFalse(second_recover["mutation_performed"])
                self.assertFalse(paths.txn_path.exists())
                if phase == "marker":
                    self.assertFalse(paths.state_path.exists())
                    self.assertEqual(entries, [])
                else:
                    self.assertEqual(json.loads(paths.state_path.read_text(encoding="utf-8")), after_state)
                    self.assertEqual([entry["event"] for entry in entries], ["first", "second"])
                    self.assertEqual([entry["transaction_seq"] for entry in entries], ["1", "2"])

    def test_equal_state_digest_recovery_safely_rolls_forward_audit_intent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            paths = self._queue_paths(root)
            state = MODULE.build_state(mode="equal_digest_fixture", items=[], now="2026-07-12T15:45:00Z")
            MODULE.save_state(paths, state)

            def interrupt(phase: str, _paths: MODULE.QueuePaths, _marker: dict[str, object]) -> None:
                if phase == "marker":
                    raise RuntimeError("interrupt:equal-digest-marker")

            MODULE._TRANSACTION_PHASE_HOOK = interrupt
            try:
                with self.assertRaisesRegex(RuntimeError, "interrupt:equal-digest-marker"):
                    with MODULE.queue_lock(paths, "exclusive", command="equal-digest-fixture", timeout=0.1):
                        MODULE._commit_transaction(
                            paths,
                            operation="equal-digest-fixture",
                            after_state=state,
                            audit_rows=[MODULE._audit_row("no_op", at="2026-07-12T15:45:00Z")],
                        )
            finally:
                MODULE._TRANSACTION_PHASE_HOOK = None

            recovered = MODULE.recover_queue(paths)
            repeated = MODULE.recover_queue(paths)
            entries = MODULE.parse_log_entries(paths)
            stored_state = MODULE.load_state(paths)

        self.assertEqual(recovered["classification"], "state_applied_history_missing")
        self.assertEqual(recovered["result"], "recovered")
        self.assertEqual(repeated["classification"], "clean")
        self.assertEqual(stored_state, state)
        self.assertEqual([entry["event"] for entry in entries], ["no_op"])

    def test_recovery_preserves_exact_existing_history_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            paths = self._queue_paths(root)
            first_state = MODULE.build_state(
                mode="history_boundary_fixture",
                items=[],
                now="2026-07-12T15:45:00Z",
            )
            with MODULE.queue_lock(paths, "exclusive", command="first", timeout=0.1):
                MODULE._commit_transaction(
                    paths,
                    operation="first",
                    after_state=first_state,
                    audit_rows=[MODULE._audit_row("first", at="2026-07-12T15:45:00Z")],
                )
            history_before = paths.log_path.read_bytes()
            second_state = {**first_state, "updated_at": "2026-07-12T15:46:00Z"}

            def interrupt(phase: str, _paths: MODULE.QueuePaths, _marker: dict[str, object]) -> None:
                if phase == "state":
                    raise RuntimeError("interrupt:second-state")

            MODULE._TRANSACTION_PHASE_HOOK = interrupt
            try:
                with self.assertRaisesRegex(RuntimeError, "interrupt:second-state"):
                    with MODULE.queue_lock(paths, "exclusive", command="second", timeout=0.1):
                        MODULE._commit_transaction(
                            paths,
                            operation="second",
                            after_state=second_state,
                            audit_rows=[
                                MODULE._audit_row("second", at="2026-07-12T15:46:00Z")
                            ],
                        )
            finally:
                MODULE._TRANSACTION_PHASE_HOOK = None

            marker = json.loads(paths.txn_path.read_text(encoding="utf-8"))
            recovered = MODULE.recover_queue(paths)
            entries = MODULE.parse_log_entries(paths)

        self.assertEqual(marker["before_history_size_bytes"], len(history_before))
        self.assertEqual(marker["before_history_digest"], MODULE._state_digest(history_before))
        self.assertEqual(recovered["classification"], "state_applied_history_missing")
        self.assertEqual([entry["event"] for entry in entries], ["first", "second"])

    def test_clear_uses_absent_state_sentinel_and_recovers_after_unlink(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            paths = self._queue_paths(root)
            MODULE.save_state(
                paths,
                MODULE.build_state(
                    mode="clear_fixture",
                    items=[],
                    now="2026-07-12T15:46:00Z",
                ),
            )

            def interrupt(phase: str, _paths: MODULE.QueuePaths, _marker: dict[str, object]) -> None:
                if phase == "state":
                    raise RuntimeError("interrupt:clear-state")

            MODULE._TRANSACTION_PHASE_HOOK = interrupt
            try:
                with self.assertRaisesRegex(RuntimeError, "interrupt:clear-state"):
                    MODULE.clear_queue(paths)
            finally:
                MODULE._TRANSACTION_PHASE_HOOK = None

            marker = json.loads(paths.txn_path.read_text(encoding="utf-8"))
            recovered = MODULE.recover_queue(paths)
            repeated = MODULE.recover_queue(paths)

        self.assertEqual(marker["after_state_digest"], "absent")
        self.assertEqual(marker["version"], 1)
        self.assertEqual(
            set(marker),
            {
                "version",
                "transaction_id",
                "operation",
                "created_at",
                "before_state_digest",
                "after_state_digest",
                "before_history_digest",
                "before_history_size_bytes",
                "audit_rows",
            },
        )
        self.assertEqual(marker["audit_rows"][0]["transaction_seq"], 1)
        self.assertEqual(marker["audit_rows"][0]["transaction_size"], 1)
        self.assertFalse(paths.state_path.exists())
        self.assertEqual(recovered["classification"], "state_applied_history_missing")
        self.assertEqual(repeated["classification"], "clean")

    def test_diverged_digest_and_sequence_conflict_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            paths = self._queue_paths(root)

            def interrupt(phase: str, _paths: MODULE.QueuePaths, _marker: dict[str, object]) -> None:
                if phase == "state":
                    raise RuntimeError("interrupt:state")

            MODULE._TRANSACTION_PHASE_HOOK = interrupt
            try:
                with self.assertRaisesRegex(RuntimeError, "interrupt:state"):
                    with MODULE.queue_lock(paths, "exclusive", command="fixture", timeout=0.1):
                        MODULE._commit_transaction(
                            paths,
                            operation="fixture",
                            after_state=MODULE.build_state(
                                mode="sequence_conflict_fixture",
                                items=[],
                                now="2026-07-12T15:46:00Z",
                            ),
                            audit_rows=[MODULE._audit_row("fixture", at="2026-07-12T15:46:00Z")],
                        )
            finally:
                MODULE._TRANSACTION_PHASE_HOOK = None

            marker = json.loads(paths.txn_path.read_text(encoding="utf-8"))
            paths.log_path.write_text(
                "2026-07-12T15:46:00Z\tfixture"
                f"\ttransaction_id={marker['transaction_id']}"
                "\ttransaction_seq=2\ttransaction_size=1\n",
                encoding="utf-8",
            )
            state_before = paths.state_path.read_bytes()
            marker_before = paths.txn_path.read_bytes()
            log_before = paths.log_path.read_bytes()

            with self.assertRaises(MODULE.QueueError) as show_error:
                MODULE.show_queue(paths)
            recovered = MODULE.recover_queue(paths)
            state_after = paths.state_path.read_bytes()
            marker_after = paths.txn_path.read_bytes()
            log_after = paths.log_path.read_bytes()

        self.assertEqual(show_error.exception.payload["error"], "diverged")
        self.assertEqual(recovered["classification"], "diverged")
        self.assertEqual(recovered["result"], "blocked")
        self.assertFalse(recovered["mutation_performed"])
        self.assertEqual(state_after, state_before)
        self.assertEqual(marker_after, marker_before)
        self.assertEqual(log_after, log_before)

    def test_show_and_history_lock_timeout_json_is_exact_and_non_mutating(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            paths = self._queue_paths(root)
            MODULE.save_state(paths, {"version": 1, "items": []})
            state_before = paths.state_path.read_bytes()
            results: dict[str, tuple[int, dict[str, object]]] = {}

            with MODULE.queue_lock(paths, "exclusive", command="holder", timeout=0.1):
                for command in ("show", "history"):
                    stdout = io.StringIO()
                    with mock.patch.object(MODULE, "LOCK_TIMEOUT_SECONDS", 0.01), mock.patch("sys.stdout", stdout):
                        result = MODULE.main(["--project-root", str(root), command, "--json"])
                    results[command] = (result, json.loads(stdout.getvalue()))
            state_after = paths.state_path.read_bytes()
            lock_exists = paths.lock_path.exists()

        for command in ("show", "history"):
            result, payload = results[command]
            self.assertEqual(result, 1)
            self.assertEqual(
                payload,
                {
                    "ok": False,
                    "error": "lock_timeout",
                    "command": command,
                    "lock_mode": "shared",
                    "lock_path": ".planveyor.planqueue.lock",
                    "timeout_seconds": 0.01,
                },
            )
        self.assertEqual(state_after, state_before)
        self.assertTrue(lock_exists)

    def test_writer_and_recover_lock_timeout_json_is_exact_and_non_mutating(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            paths = self._queue_paths(root)
            MODULE.save_state(
                paths,
                MODULE.build_state(mode="exclusive_timeout", items=[], now="2026-07-12T18:20:00Z"),
            )
            state_before = paths.state_path.read_bytes()
            results: dict[str, tuple[int, dict[str, object]]] = {}

            with MODULE.queue_lock(paths, "exclusive", command="holder", timeout=0.1):
                for command in ("clear", "recover"):
                    stdout = io.StringIO()
                    with mock.patch.object(MODULE, "LOCK_TIMEOUT_SECONDS", 0.01), mock.patch(
                        "sys.stdout", stdout
                    ):
                        result = MODULE.main(["--project-root", str(root), command, "--json"])
                    results[command] = (result, json.loads(stdout.getvalue()))
            state_after = paths.state_path.read_bytes()

        for command in ("clear", "recover"):
            result, payload = results[command]
            self.assertEqual(result, 1)
            self.assertEqual(payload["error"], "lock_timeout")
            self.assertEqual(payload["command"], command)
            self.assertEqual(payload["lock_mode"], "exclusive")
            self.assertEqual(payload["timeout_seconds"], 0.01)
        self.assertEqual(state_after, state_before)

    def test_missing_marker_fields_fail_closed_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            paths = self._queue_paths(root)
            MODULE.save_state(paths, {"version": 1, "items": []})
            paths.txn_path.write_text('{"version": 1}\n', encoding="utf-8")
            state_before = paths.state_path.read_bytes()
            marker_before = paths.txn_path.read_bytes()

            with self.assertRaises(MODULE.QueueError) as show_error:
                MODULE.show_queue(paths)
            recovered = MODULE.recover_queue(paths)
            state_after = paths.state_path.read_bytes()
            marker_after = paths.txn_path.read_bytes()

        self.assertEqual(show_error.exception.payload["error"], "diverged")
        self.assertEqual(show_error.exception.payload["transaction_id"], None)
        self.assertEqual(recovered["classification"], "diverged")
        self.assertEqual(recovered["result"], "blocked")
        self.assertFalse(recovered["mutation_performed"])
        self.assertEqual(state_after, state_before)
        self.assertEqual(marker_after, marker_before)

    def test_marker_history_grammar_fields_fail_closed_without_replay(self) -> None:
        mutations = {
            "transaction_id": lambda marker: marker.__setitem__("transaction_id", "bad\nid"),
            "operation": lambda marker: marker.__setitem__("operation", "bad operation"),
            "timestamp": lambda marker: marker["audit_rows"][0].__setitem__("at", "bad\rtime"),
            "event": lambda marker: marker["audit_rows"][0].__setitem__("event", "bad\nevent"),
            "field_key": lambda marker: marker["audit_rows"][0].__setitem__(
                "fields", {"bad=key": "value"}
            ),
            "structural_field_key": lambda marker: marker["audit_rows"][0].__setitem__(
                "fields", {"event": "shadowed"}
            ),
        }
        for case, mutate in mutations.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                (root / ".git").mkdir()
                paths = self._queue_paths(root)

                def interrupt(phase: str, _paths: MODULE.QueuePaths, _marker: dict[str, object]) -> None:
                    if phase == "state":
                        raise RuntimeError("interrupt:marker-grammar")

                MODULE._TRANSACTION_PHASE_HOOK = interrupt
                try:
                    with self.assertRaisesRegex(RuntimeError, "interrupt:marker-grammar"):
                        with MODULE.queue_lock(paths, "exclusive", command="marker-grammar", timeout=0.1):
                            MODULE._commit_transaction(
                                paths,
                                operation="marker-grammar",
                                after_state=MODULE.build_state(
                                    mode="marker_grammar",
                                    items=[],
                                    now="2026-07-12T18:25:00Z",
                                ),
                                audit_rows=[
                                    MODULE._audit_row("fixture", at="2026-07-12T18:25:00Z")
                                ],
                            )
                finally:
                    MODULE._TRANSACTION_PHASE_HOOK = None

                marker = json.loads(paths.txn_path.read_text(encoding="utf-8"))
                mutate(marker)
                paths.txn_path.write_text(json.dumps(marker) + "\n", encoding="utf-8")
                state_before = paths.state_path.read_bytes()
                marker_before = paths.txn_path.read_bytes()

                recovered = MODULE.recover_queue(paths)

                self.assertEqual(recovered["classification"], "diverged")
                self.assertEqual(recovered["result"], "blocked")
                self.assertFalse(recovered["mutation_performed"])
                self.assertEqual(paths.state_path.read_bytes(), state_before)
                self.assertEqual(paths.txn_path.read_bytes(), marker_before)
                self.assertFalse(paths.log_path.exists())

    def test_malformed_state_without_marker_returns_structured_json_for_all_readback_commands(self) -> None:
        malformed_states = {
            "invalid_json": b"{broken\n",
            "invalid_utf8": b'{"version": 1, "mode": "fixture", "resume_parent": "none", "cursor": 0, "items": []}\xff\n',
            "empty_object": b"{}\n",
            "array": b"[]\n",
            "partial_object": b'{"version": 1, "items": []}\n',
            "unhashable_item_state": (
                b'{"version": 1, "mode": "fixture", "resume_parent": "none", "cursor": 0, '
                b'"items": [{"order": 1, "plan": "docs/plans/fixture.md", "state": []}]}\n'
            ),
            "cursor_exceeds_items": (
                b'{"version": 1, "mode": "fixture", "resume_parent": "none", "cursor": 2, '
                b'"items": [{"order": 1, "plan": "docs/plans/fixture.md", "state": "pending"}]}\n'
            ),
            "active_cursor_mismatch": (
                b'{"version": 1, "mode": "fixture", "resume_parent": "none", "cursor": 1, '
                b'"items": [{"order": 1, "plan": "docs/plans/fixture.md", "state": "active"}]}\n'
            ),
            "non_contiguous_orders": (
                b'{"version": 1, "mode": "fixture", "resume_parent": "none", "cursor": 0, '
                b'"items": [{"order": 2, "plan": "docs/plans/fixture.md", "state": "pending"}]}\n'
            ),
            "duplicate_plan_paths": (
                b'{"version": 1, "mode": "fixture", "resume_parent": "none", "cursor": 0, '
                b'"items": ['
                b'{"order": 1, "plan": "docs/plans/fixture.md", "state": "pending"}, '
                b'{"order": 2, "plan": "docs/plans/fixture.md", "state": "pending"}]}\n'
            ),
            "pending_before_active": (
                b'{"version": 1, "mode": "fixture", "resume_parent": "none", "cursor": 1, '
                b'"items": ['
                b'{"order": 1, "plan": "docs/plans/first.md", "state": "pending"}, '
                b'{"order": 2, "plan": "docs/plans/second.md", "state": "active"}]}\n'
            ),
            "active_before_finalized": (
                b'{"version": 1, "mode": "fixture", "resume_parent": "none", "cursor": 0, '
                b'"items": ['
                b'{"order": 1, "plan": "docs/plans/first.md", "state": "active"}, '
                b'{"order": 2, "plan": "docs/plans/second.md", "state": "done"}]}\n'
            ),
        }
        for case, malformed_state in malformed_states.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                (root / ".git").mkdir()
                paths = self._queue_paths(root)
                paths.state_path.write_bytes(malformed_state)
                observed_digest = MODULE._state_digest(malformed_state)
                payloads: dict[str, dict[str, object]] = {}

                for command in ("show", "history", "recover", "clear"):
                    stdout = io.StringIO()
                    stderr = io.StringIO()
                    with mock.patch("sys.stdout", stdout), mock.patch("sys.stderr", stderr):
                        result = MODULE.main(["--project-root", str(root), command, "--json"])
                    self.assertEqual(result, 1)
                    self.assertEqual(stderr.getvalue(), "")
                    self.assertEqual(len(stdout.getvalue().splitlines()), 1)
                    payloads[command] = json.loads(stdout.getvalue())
                    self.assertEqual(paths.state_path.read_bytes(), malformed_state)
                    self.assertFalse(paths.txn_path.exists())
                    self.assertFalse(paths.log_path.exists())

                common = {
                    "ok": False,
                    "classification": "diverged",
                    "transaction_id": None,
                    "operation": None,
                    "marker_path": ".planveyor.planqueue.txn.json",
                    "observed_state_digest": observed_digest,
                    "history_rows_expected": 0,
                    "history_rows_present": 0,
                    "mutation_performed": False,
                }
                self.assertEqual(payloads["show"], {**common, "error": "diverged", "command": "show", "recovery_command": None})
                self.assertEqual(payloads["history"], {**common, "error": "diverged", "command": "history", "recovery_command": None})
                self.assertEqual(payloads["clear"], {**common, "error": "diverged", "command": "clear", "recovery_command": None})
                self.assertEqual(
                    payloads["recover"],
                    {
                        **common,
                        "command": "recover",
                        "result": "blocked",
                    },
                )

    def test_schema_invalid_state_with_marker_blocks_recovery_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            paths = self._queue_paths(root)

            def interrupt(phase: str, _paths: MODULE.QueuePaths, _marker: dict[str, object]) -> None:
                if phase == "state":
                    raise RuntimeError("interrupt:invalid-state")

            MODULE._TRANSACTION_PHASE_HOOK = interrupt
            try:
                with self.assertRaisesRegex(RuntimeError, "interrupt:invalid-state"):
                    with MODULE.queue_lock(paths, "exclusive", command="invalid-state-fixture", timeout=0.1):
                        MODULE._commit_transaction(
                            paths,
                            operation="invalid-state-fixture",
                            after_state={},
                            audit_rows=[MODULE._audit_row("fixture", at="2026-07-12T18:25:00Z")],
                        )
            finally:
                MODULE._TRANSACTION_PHASE_HOOK = None

            state_before = paths.state_path.read_bytes()
            marker_before = paths.txn_path.read_bytes()
            stdout = io.StringIO()
            stderr = io.StringIO()
            with mock.patch("sys.stdout", stdout), mock.patch("sys.stderr", stderr):
                result = MODULE.main(["--project-root", str(root), "recover", "--json"])
            payload = json.loads(stdout.getvalue())
            state_after = paths.state_path.read_bytes()
            marker_after = paths.txn_path.read_bytes()
            log_exists = paths.log_path.exists()

        self.assertEqual(result, 1)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(payload["classification"], "diverged")
        self.assertEqual(payload["result"], "blocked")
        self.assertFalse(payload["mutation_performed"])
        self.assertEqual(state_after, state_before)
        self.assertEqual(marker_after, marker_before)
        self.assertFalse(log_exists)

    def test_invalid_utf8_marker_returns_structured_diverged_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            paths = self._queue_paths(root)
            state = MODULE.build_state(mode="marker_utf8", items=[], now="2026-07-12T18:25:00Z")
            MODULE.save_state(paths, state)
            paths.txn_path.write_bytes(b'{"version": 1}\xff\n')
            state_before = paths.state_path.read_bytes()
            marker_before = paths.txn_path.read_bytes()

            payloads: dict[str, dict[str, object]] = {}
            for command in ("show", "history", "recover"):
                stdout = io.StringIO()
                stderr = io.StringIO()
                with mock.patch("sys.stdout", stdout), mock.patch("sys.stderr", stderr):
                    result = MODULE.main(["--project-root", str(root), command, "--json"])
                self.assertEqual(result, 1)
                self.assertEqual(stderr.getvalue(), "")
                payloads[command] = json.loads(stdout.getvalue())
                self.assertEqual(paths.state_path.read_bytes(), state_before)
                self.assertEqual(paths.txn_path.read_bytes(), marker_before)

        self.assertEqual(payloads["show"]["classification"], "diverged")
        self.assertEqual(payloads["history"]["classification"], "diverged")
        self.assertEqual(payloads["recover"]["result"], "blocked")

    def test_malformed_history_returns_structured_diverged_without_mutation(self) -> None:
        malformed_histories = {
            "missing_final_newline": b"2026-07-12T18:26:00Z\tlegacy",
            "invalid_utf8": b"2026-07-12T18:26:00Z\tlegacy\tvalue=\xff\n",
            "missing_event": b"2026-07-12T18:26:00Z\n",
            "empty_event": b"2026-07-12T18:26:00Z\t\n",
            "bare_field_chunk": b"2026-07-12T18:26:00Z\tlegacy\tBROKEN_CHUNK\n",
            "empty_field_key": b"2026-07-12T18:26:00Z\tlegacy\t=value\n",
            "duplicate_field": b"2026-07-12T18:26:00Z\tlegacy\tkey=a\tkey=b\n",
            "partial_transaction": b"2026-07-12T18:26:00Z\tlegacy\ttransaction_id=abc\n",
            "incomplete_transaction_group": (
                b"2026-07-12T18:26:00Z\tset\ttransaction_id=abc"
                b"\ttransaction_seq=1\ttransaction_size=2\n"
            ),
            "duplicate_completed_transaction": (
                b"2026-07-12T18:26:00Z\tset\ttransaction_id=abc"
                b"\ttransaction_seq=1\ttransaction_size=1\n"
                b"2026-07-12T18:26:01Z\tset\ttransaction_id=abc"
                b"\ttransaction_seq=1\ttransaction_size=1\n"
            ),
            "non_contiguous_transaction_group": (
                b"2026-07-12T18:26:00Z\tset\ttransaction_id=abc"
                b"\ttransaction_seq=1\ttransaction_size=2\n"
                b"2026-07-12T18:26:01Z\tlegacy\tvalue=foreign\n"
                b"2026-07-12T18:26:02Z\texpand\ttransaction_id=abc"
                b"\ttransaction_seq=2\ttransaction_size=2\n"
            ),
        }
        for case, malformed_history in malformed_histories.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                (root / ".git").mkdir()
                paths = self._queue_paths(root)
                MODULE.save_state(
                    paths,
                    MODULE.build_state(mode="history_fixture", items=[], now="2026-07-12T18:26:00Z"),
                )
                paths.log_path.write_bytes(malformed_history)
                state_before = paths.state_path.read_bytes()
                log_before = paths.log_path.read_bytes()
                payloads: dict[str, dict[str, object]] = {}

                for command in ("show", "history", "recover", "clear"):
                    stdout = io.StringIO()
                    stderr = io.StringIO()
                    with mock.patch("sys.stdout", stdout), mock.patch("sys.stderr", stderr):
                        result = MODULE.main(["--project-root", str(root), command, "--json"])
                    self.assertEqual(result, 1)
                    self.assertEqual(stderr.getvalue(), "")
                    self.assertEqual(len(stdout.getvalue().splitlines()), 1)
                    payloads[command] = json.loads(stdout.getvalue())
                    self.assertEqual(paths.state_path.read_bytes(), state_before)
                    self.assertEqual(paths.log_path.read_bytes(), log_before)
                    self.assertFalse(paths.txn_path.exists())

                self.assertEqual(payloads["show"]["error"], "diverged")
                self.assertEqual(payloads["history"]["error"], "diverged")
                self.assertEqual(payloads["clear"]["error"], "diverged")
                self.assertEqual(payloads["recover"]["classification"], "diverged")
                self.assertEqual(payloads["recover"]["result"], "blocked")
                self.assertTrue(all(payload["mutation_performed"] is False for payload in payloads.values()))

    def test_malformed_history_blocks_transaction_before_state_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            paths = self._queue_paths(root)
            state = MODULE.build_state(mode="history_fixture", items=[], now="2026-07-12T18:27:00Z")
            MODULE.save_state(paths, state)
            paths.log_path.write_bytes(b"2026-07-12T18:27:00Z\tlegacy")
            state_before = paths.state_path.read_bytes()
            log_before = paths.log_path.read_bytes()

            with MODULE.queue_lock(paths, "exclusive", command="history-fixture", timeout=0.1):
                with self.assertRaises(MODULE.QueueError) as error:
                    MODULE._commit_transaction(
                        paths,
                        operation="history-fixture",
                        after_state={**state, "updated_at": "2026-07-12T18:28:00Z"},
                        audit_rows=[MODULE._audit_row("fixture", at="2026-07-12T18:28:00Z")],
                    )

            state_after = paths.state_path.read_bytes()
            log_after = paths.log_path.read_bytes()
            marker_exists = paths.txn_path.exists()

        self.assertEqual(error.exception.payload["error"], "diverged")
        self.assertFalse(error.exception.payload["mutation_performed"])
        self.assertEqual(state_after, state_before)
        self.assertEqual(log_after, log_before)
        self.assertFalse(marker_exists)

    def test_recovery_rejects_malformed_complete_row_without_removing_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            paths = self._queue_paths(root)

            def interrupt(phase: str, _paths: MODULE.QueuePaths, _marker: dict[str, object]) -> None:
                if phase == "history":
                    raise RuntimeError("interrupt:history-complete")

            MODULE._TRANSACTION_PHASE_HOOK = interrupt
            try:
                with self.assertRaisesRegex(RuntimeError, "interrupt:history-complete"):
                    with MODULE.queue_lock(paths, "exclusive", command="history-fixture", timeout=0.1):
                        MODULE._commit_transaction(
                            paths,
                            operation="history-fixture",
                            after_state=MODULE.build_state(
                                mode="history_fixture",
                                items=[],
                                now="2026-07-12T18:28:00Z",
                            ),
                            audit_rows=[MODULE._audit_row("fixture", at="2026-07-12T18:28:00Z")],
                        )
            finally:
                MODULE._TRANSACTION_PHASE_HOOK = None

            paths.log_path.write_bytes(
                paths.log_path.read_bytes().replace(b"\n", b"\tBROKEN_CHUNK\n")
            )
            marker_before = paths.txn_path.read_bytes()
            log_before = paths.log_path.read_bytes()
            recovered = MODULE.recover_queue(paths)
            marker_after = paths.txn_path.read_bytes()
            log_after = paths.log_path.read_bytes()

        self.assertEqual(recovered["classification"], "diverged")
        self.assertEqual(recovered["result"], "blocked")
        self.assertFalse(recovered["mutation_performed"])
        self.assertEqual(marker_after, marker_before)
        self.assertEqual(log_after, log_before)

    def test_recovery_rejects_duplicate_gapped_out_of_order_and_conflicting_rows(self) -> None:
        for case in (
            "duplicate",
            "gapped",
            "out_of_order",
            "conflicting",
            "interleaved",
            "foreign_before_current",
        ):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                (root / ".git").mkdir()
                paths = self._queue_paths(root)
                audit_rows = [
                    MODULE._audit_row("first", at="2026-07-12T18:29:00Z", value="a"),
                    MODULE._audit_row("second", at="2026-07-12T18:29:00Z", value="b"),
                ]

                def interrupt(
                    phase: str, _paths: MODULE.QueuePaths, _marker: dict[str, object]
                ) -> None:
                    if phase == "state":
                        raise RuntimeError("interrupt:sequence-state")

                MODULE._TRANSACTION_PHASE_HOOK = interrupt
                try:
                    with self.assertRaisesRegex(RuntimeError, "interrupt:sequence-state"):
                        with MODULE.queue_lock(paths, "exclusive", command="sequence-fixture", timeout=0.1):
                            MODULE._commit_transaction(
                                paths,
                                operation="sequence-fixture",
                                after_state=MODULE.build_state(
                                    mode="sequence_fixture",
                                    items=[],
                                    now="2026-07-12T18:29:00Z",
                                ),
                                audit_rows=audit_rows,
                            )
                finally:
                    MODULE._TRANSACTION_PHASE_HOOK = None

                marker = json.loads(paths.txn_path.read_text(encoding="utf-8"))
                transaction_id = marker["transaction_id"]
                first = MODULE._render_log_row(
                    audit_rows[0], transaction_id=transaction_id, sequence=1, size=2
                )
                second = MODULE._render_log_row(
                    audit_rows[1], transaction_id=transaction_id, sequence=2, size=2
                )
                malformed = {
                    "duplicate": first + first,
                    "gapped": second,
                    "out_of_order": second + first,
                    "conflicting": first.replace("\tfirst\t", "\twrong\t", 1),
                    "interleaved": (
                        first
                        + "2026-07-12T18:29:00Z\tlegacy\tvalue=outside-current-transaction\n"
                        + second
                    ),
                    "foreign_before_current": (
                        "2026-07-12T18:29:00Z\tlegacy\tvalue=outside-current-transaction\n"
                    ),
                }[case]
                paths.log_path.write_text(malformed, encoding="utf-8")
                marker_before = paths.txn_path.read_bytes()
                log_before = paths.log_path.read_bytes()

                recovered = MODULE.recover_queue(paths)

                self.assertEqual(recovered["classification"], "diverged")
                self.assertEqual(recovered["result"], "blocked")
                self.assertEqual(paths.txn_path.read_bytes(), marker_before)
                self.assertEqual(paths.log_path.read_bytes(), log_before)

    def test_recovery_rejects_transaction_id_collision_in_history_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            paths = self._queue_paths(root)
            historical_row = MODULE._audit_row("historical", at="2026-07-12T18:29:00Z")
            paths.log_path.write_text(
                MODULE._render_log_row(
                    historical_row,
                    transaction_id="collision_tx",
                    sequence=1,
                    size=1,
                ),
                encoding="utf-8",
            )

            def interrupt(phase: str, _paths: MODULE.QueuePaths, _marker: dict[str, object]) -> None:
                if phase == "state":
                    raise RuntimeError("interrupt:collision-state")

            MODULE._TRANSACTION_PHASE_HOOK = interrupt
            try:
                with self.assertRaisesRegex(RuntimeError, "interrupt:collision-state"):
                    with MODULE.queue_lock(paths, "exclusive", command="collision", timeout=0.1):
                        MODULE._commit_transaction(
                            paths,
                            operation="collision",
                            after_state=MODULE.build_state(
                                mode="collision_fixture",
                                items=[],
                                now="2026-07-12T18:29:01Z",
                            ),
                            audit_rows=[
                                MODULE._audit_row("current", at="2026-07-12T18:29:01Z")
                            ],
                        )
            finally:
                MODULE._TRANSACTION_PHASE_HOOK = None

            marker = json.loads(paths.txn_path.read_text(encoding="utf-8"))
            marker["transaction_id"] = "collision_tx"
            paths.txn_path.write_text(json.dumps(marker) + "\n", encoding="utf-8")
            marker_before = paths.txn_path.read_bytes()
            log_before = paths.log_path.read_bytes()

            recovered = MODULE.recover_queue(paths)
            marker_after = paths.txn_path.read_bytes()
            log_after = paths.log_path.read_bytes()

        self.assertEqual(recovered["classification"], "diverged")
        self.assertEqual(recovered["result"], "blocked")
        self.assertFalse(recovered["mutation_performed"])
        self.assertEqual(marker_after, marker_before)
        self.assertEqual(log_after, log_before)

    def test_atomic_write_uses_private_mode_for_new_file_and_preserves_existing_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / ".planveyor.planqueue.json"
            MODULE._atomic_write_bytes(path, b"first\n")
            new_mode = stat.S_IMODE(path.stat().st_mode)
            path.chmod(0o640)
            MODULE._atomic_write_bytes(path, b"second\n")
            existing_mode = stat.S_IMODE(path.stat().st_mode)

        self.assertEqual(new_mode, 0o600)
        self.assertEqual(existing_mode, 0o640)

    def test_recover_json_contract_and_readback_non_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            paths = self._queue_paths(root)

            def interrupt(phase: str, _paths: MODULE.QueuePaths, _marker: dict[str, object]) -> None:
                if phase == "state":
                    raise RuntimeError("interrupt:state")

            MODULE._TRANSACTION_PHASE_HOOK = interrupt
            try:
                with self.assertRaisesRegex(RuntimeError, "interrupt:state"):
                    with MODULE.queue_lock(paths, "exclusive", command="fixture", timeout=0.1):
                        MODULE._commit_transaction(
                            paths,
                            operation="fixture",
                            after_state=MODULE.build_state(
                                mode="recover_fixture",
                                items=[],
                                now="2026-07-12T15:47:00Z",
                            ),
                            audit_rows=[MODULE._audit_row("fixture", at="2026-07-12T15:47:00Z")],
                        )
            finally:
                MODULE._TRANSACTION_PHASE_HOOK = None

            state_before = paths.state_path.read_bytes()
            marker_before = paths.txn_path.read_bytes()
            stdout = io.StringIO()
            with mock.patch("sys.stdout", stdout):
                show_result = MODULE.main(["--project-root", str(root), "show", "--json"])
            show_payload = json.loads(stdout.getvalue())
            self.assertEqual(paths.state_path.read_bytes(), state_before)
            self.assertEqual(paths.txn_path.read_bytes(), marker_before)

            stdout = io.StringIO()
            with mock.patch("sys.stdout", stdout):
                recover_result = MODULE.main(["--project-root", str(root), "recover", "--json"])
            recover_payload = json.loads(stdout.getvalue())

        self.assertEqual(show_result, 1)
        self.assertEqual(show_payload["error"], "recovery_required")
        self.assertEqual(show_payload["recovery_command"], "planveyor_q_recover")
        self.assertEqual(show_payload["classification"], "state_applied_history_missing")
        self.assertFalse(show_payload["mutation_performed"])
        self.assertEqual(recover_result, 0)
        self.assertEqual(recover_payload["command"], "recover")
        self.assertEqual(recover_payload["classification"], "state_applied_history_missing")
        self.assertEqual(recover_payload["result"], "recovered")
        self.assertTrue(recover_payload["mutation_performed"])

    def test_recovery_payload_names_the_recover_command_unless_history_diverged(self) -> None:
        root = Path("/fixture/project")
        paths = MODULE.QueuePaths(
            root=root,
            state_path=root / MODULE.STATE_FILE_NAME,
            log_path=root / MODULE.LOG_FILE_NAME,
        )
        cases = {
            "not_applied": ("recovery_required", "planveyor_q_recover"),
            "state_applied_history_missing": ("recovery_required", "planveyor_q_recover"),
            "legacy_repair_required": ("recovery_required", "planveyor_q_recover"),
            "diverged": ("diverged", None),
        }
        for classification, (error, recovery_command) in cases.items():
            with self.subTest(classification=classification):
                payload = MODULE._recovery_payload(paths, command="show", recovery={"classification": classification})
                self.assertEqual(payload["error"], error)
                self.assertEqual(payload["recovery_command"], recovery_command)

    def test_real_process_writers_serialize_multi_row_transactions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            child_a = "docs/plans/260712_1848_child_a.md"
            child_b = "docs/plans/260712_1849_child_b.md"
            umbrella_a = "docs/plans/260712_1850_umbrella_a.md"
            umbrella_b = "docs/plans/260712_1851_umbrella_b.md"
            self._write_plan(root, child_a)
            self._write_plan(root, child_b)
            self._write_plan(root, umbrella_a, execution_queue=f"- Resume parent: `none`\n- Plan: `{child_a}`")
            self._write_plan(root, umbrella_b, execution_queue=f"- Resume parent: `none`\n- Plan: `{child_b}`")
            paths = self._queue_paths(root)
            commands = [
                [
                    sys.executable,
                    "-B",
                    str(MODULE_PATH),
                    "--project-root",
                    str(root),
                    "set",
                    "--from-umbrella",
                    umbrella,
                    "--for-manager-mode",
                    "manager-collab",
                    "--json",
                ]
                for umbrella in (umbrella_a, umbrella_b)
            ]

            processes: list[subprocess.Popen[str]] = []
            try:
                with MODULE.queue_lock(paths, "exclusive", command="test-holder", timeout=0.1):
                    processes = [
                        subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                        for command in commands
                    ]
                    time.sleep(0.05)
                    self.assertTrue(all(process.poll() is None for process in processes))

                # Each child resolves and revalidates authority before taking
                # the queue lock.  Keep one bounded window that exceeds the
                # queue's own lock contract, rather than granting each child
                # an independent unbounded extension under shard contention.
                completion_timeout = MODULE.LOCK_TIMEOUT_SECONDS + 2.0
                deadline = time.monotonic() + completion_timeout
                results = []
                for process in processes:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise subprocess.TimeoutExpired(process.args, completion_timeout)
                    results.append(process.communicate(timeout=remaining))
                return_codes = [process.returncode for process in processes]
                entries = MODULE.parse_log_entries(paths)
                transaction_ids = [entry["transaction_id"] for entry in entries]
            finally:
                for process in processes:
                    if process.poll() is None:
                        try:
                            process.terminate()
                        except ProcessLookupError:
                            pass
                for process in processes:
                    if process.poll() is None:
                        try:
                            process.communicate(timeout=1)
                        except subprocess.TimeoutExpired:
                            try:
                                process.kill()
                            except ProcessLookupError:
                                pass
                            process.communicate()

        self.assertEqual(return_codes, [0, 0], msg=results)
        self.assertEqual(len(entries), 4)
        self.assertEqual([entry["event"] for entry in entries], ["set", "expand", "set", "expand"])
        self.assertEqual(transaction_ids[0], transaction_ids[1])
        self.assertEqual(transaction_ids[2], transaction_ids[3])
        self.assertNotEqual(transaction_ids[0], transaction_ids[2])
        self.assertEqual([entry["transaction_seq"] for entry in entries], ["1", "2", "1", "2"])

    def test_real_process_readers_wait_for_complete_writer_transaction_snapshot(self) -> None:
        writer_code = dedent(
            """\
            import importlib.util
            import sys
            import time
            from pathlib import Path

            module_path, root_arg, ready_arg, release_arg = sys.argv[1:]
            spec = importlib.util.spec_from_file_location("plan_queue_writer_fixture", module_path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            root = Path(root_arg)
            ready = Path(ready_arg)
            release = Path(release_arg)
            paths = module.queue_paths(root)
            state = module.build_state(
                mode="reader_writer_fixture",
                items=[{
                    "order": 1,
                    "plan": "docs/plans/260712_2124_reader_writer_fixture.md",
                    "source": "fixture",
                    "state": "pending",
                    "added_at": "2026-07-12T18:24:00Z",
                    "activated_at": None,
                    "completed_at": None,
                    "final_status": None,
                    "runtime_class": None,
                    "closeout_kind": None,
                    "closeout_reason": None,
                }],
                now="2026-07-12T18:24:00Z",
            )

            def pause(phase, _paths, _marker):
                if phase != "state":
                    return
                ready.write_text("ready\\n", encoding="utf-8")
                deadline = time.monotonic() + 5
                while not release.exists():
                    if time.monotonic() >= deadline:
                        raise RuntimeError("release timeout")
                    time.sleep(0.01)

            module._TRANSACTION_PHASE_HOOK = pause
            with module.queue_lock(paths, "exclusive", command="writer-fixture", timeout=1):
                module._commit_transaction(
                    paths,
                    operation="writer-fixture",
                    after_state=state,
                    audit_rows=[module._audit_row("set", at="2026-07-12T18:24:00Z")],
                )
            """
        )
        context_reader_code = dedent(
            """\
            import importlib.util
            import json
            import sys
            from pathlib import Path

            module_path, root_arg = sys.argv[1:]
            spec = importlib.util.spec_from_file_location("plan_queue_reader_fixture", module_path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            paths = module.queue_paths(Path(root_arg))
            payload = module.queue_runtime_context_snapshot(
                paths,
                plan="docs/plans/260712_2124_reader_writer_fixture.md",
            )
            print(json.dumps(payload, sort_keys=True))
            """
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            self._ensure_fixture_git(root)
            ready = root / "writer.ready"
            release = root / "writer.release"
            writer = subprocess.Popen(
                [sys.executable, "-B", "-c", writer_code, str(MODULE_PATH), str(root), str(ready), str(release)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            deadline = time.monotonic() + 5
            while not ready.exists():
                if writer.poll() is not None:
                    self.fail(f"writer exited before phase barrier: {writer.communicate()}")
                if time.monotonic() >= deadline:
                    writer.kill()
                    self.fail("writer did not reach the state phase barrier")
                time.sleep(0.01)

            show_reader = subprocess.Popen(
                [sys.executable, "-B", str(MODULE_PATH), "--project-root", str(root), "show", "--json"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            context_reader = subprocess.Popen(
                [sys.executable, "-B", "-c", context_reader_code, str(MODULE_PATH), str(root)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            time.sleep(0.1)
            self.assertIsNone(show_reader.poll())
            self.assertIsNone(context_reader.poll())
            release.write_text("release\n", encoding="utf-8")

            writer_stdout, writer_stderr = writer.communicate(timeout=5)
            show_stdout, show_stderr = show_reader.communicate(timeout=5)
            context_stdout, context_stderr = context_reader.communicate(timeout=5)
            paths = self._queue_paths(root)
            entries = MODULE.parse_log_entries(paths)

        self.assertEqual(writer.returncode, 0, msg=writer_stdout + writer_stderr)
        self.assertEqual(show_reader.returncode, 0, msg=show_stderr)
        self.assertEqual(context_reader.returncode, 0, msg=context_stderr)
        show_payload = json.loads(show_stdout)
        context_payload = json.loads(context_stdout)
        self.assertEqual(show_payload["pending_count"], 1)
        self.assertEqual(show_payload["items"][0]["plan"], "docs/plans/260712_2124_reader_writer_fixture.md")
        self.assertTrue(context_payload["queue_mode_active"])
        self.assertTrue(context_payload["history_available"])
        self.assertEqual([entry["event"] for entry in entries], ["set"])
        self.assertFalse(paths.txn_path.exists())

    def test_small_slice_payload_accepts_docs_only_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            plan_rel = "docs/plans/260328_0900_docs_only.md"
            self._write_plan(
                root,
                plan_rel,
                review_artifacts="- Doc review (docs-only): `docs/doc_reviews/260328_0900_docs_only.md`",
                small_slice_classifier=dedent(
                    """\
                    - Requested profile: `reduced-same-session-censors`
                    - Expected bundle family: `docs-only`
                    - Helper validation: `exact-bundle-match`
                    - Drift behavior: `fail-closed-to-full-conveyor`
                    """
                ).rstrip(),
                visual_acceptance="- `N/A (why=docs-only fixture)`",
            )
            self._write_code_draft(root, plan_rel, target_paths=["docs/plans/README.md"])

            payload = MODULE.small_slice_payload(root, plan_rel)
            queue_files_created = any(
                (root / name).exists()
                for name in (
                    MODULE.STATE_FILE_NAME,
                    MODULE.LOG_FILE_NAME,
                    MODULE.LOCK_FILE_NAME,
                    MODULE.TXN_FILE_NAME,
                )
            )

        self.assertTrue(payload["reduced_conveyor_eligible"])
        self.assertFalse(queue_files_created)
        self.assertEqual(payload["actual_bundle_family"], "docs-only")
        self.assertEqual(payload["live_review_artifact"], "docs/doc_reviews/260328_0900_docs_only.md")
        self.assertEqual(payload["same_session_censors"], list(MODULE.SMALL_SLICE_CENSOR_ROLES))

    def test_small_slice_payload_accepts_plain_visual_acceptance_na_body(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            plan_rel = "docs/plans/260613_1452_docs_only_plain_visual_na.md"
            self._write_plan(
                root,
                plan_rel,
                review_artifacts="- Doc review (docs-only): `docs/doc_reviews/260613_1452_docs_only_plain_visual_na.md`",
                small_slice_classifier=dedent(
                    """\
                    - Requested profile: `reduced-same-session-censors`
                    - Expected bundle family: `docs-only`
                    - Helper validation: `exact-bundle-match`
                    - Drift behavior: `fail-closed-to-full-conveyor`
                    """
                ).rstrip(),
                visual_acceptance="N/A (why=docs-only reduced conveyor fixture)",
            )
            self._write_code_draft(root, plan_rel, target_paths=["docs/plans/README.md"])

            payload = MODULE.small_slice_payload(root, plan_rel)

        self.assertTrue(payload["visual_acceptance_is_na"])
        self.assertTrue(payload["reduced_conveyor_eligible"])
        self.assertNotIn("visual_acceptance_not_na", payload["fail_closed_reasons"])

    def test_small_slice_payload_accepts_visual_acceptance_na_with_na_subheading(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            plan_rel = "docs/plans/260613_1454_docs_only_visual_na_subheading.md"
            self._write_plan(
                root,
                plan_rel,
                review_artifacts="- Doc review (docs-only): `docs/doc_reviews/260613_1454_docs_only_visual_na_subheading.md`",
                small_slice_classifier=dedent(
                    """\
                    - Requested profile: `reduced-same-session-censors`
                    - Expected bundle family: `docs-only`
                    - Helper validation: `exact-bundle-match`
                    - Drift behavior: `fail-closed-to-full-conveyor`
                    """
                ).rstrip(),
                visual_acceptance=dedent(
                    """\
                    `N/A (why=process ADR; no browser UI surface)`

                    ### Visual regression scenarios (docs/smoke_visual.md)
                    `N/A (why=no browser/UI expectation changes)`
                    """
                ).rstrip(),
            )
            self._write_code_draft(root, plan_rel, target_paths=["docs/plans/README.md"])

            payload = MODULE.small_slice_payload(root, plan_rel)

        self.assertTrue(payload["visual_acceptance_is_na"])
        self.assertTrue(payload["reduced_conveyor_eligible"])
        self.assertNotIn("visual_acceptance_not_na", payload["fail_closed_reasons"])

    def test_small_slice_payload_accepts_tests_only_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            plan_rel = "docs/plans/260328_0901_tests_only.md"
            self._write_plan(
                root,
                plan_rel,
                review_artifacts="- Code review (primary): `docs/code_reviews/260328_0901_tests_only.md`",
                small_slice_classifier=dedent(
                    """\
                    - Requested profile: `reduced-same-session-censors`
                    - Expected bundle family: `tests-only`
                    - Helper validation: `exact-bundle-match`
                    - Drift behavior: `fail-closed-to-full-conveyor`
                    """
                ).rstrip(),
                visual_acceptance="- `N/A (why=tests-only fixture)`",
            )
            self._write_code_draft(root, plan_rel, target_paths=["scripts/test_plan_queue.py"])

            payload = MODULE.small_slice_payload(root, plan_rel)

        self.assertTrue(payload["reduced_conveyor_eligible"])
        self.assertEqual(payload["actual_bundle_family"], "tests-only")
        self.assertEqual(payload["live_review_artifact"], "docs/code_reviews/260328_0901_tests_only.md")

    def test_small_slice_payload_fails_closed_for_mixed_docs_and_scripts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            plan_rel = "docs/plans/260328_0902_mixed.md"
            self._write_plan(
                root,
                plan_rel,
                review_artifacts="- Code review (primary): `docs/code_reviews/260328_0902_mixed.md`",
                small_slice_classifier=dedent(
                    """\
                    - Requested profile: `reduced-same-session-censors`
                    - Expected bundle family: `docs-only`
                    - Helper validation: `exact-bundle-match`
                    - Drift behavior: `fail-closed-to-full-conveyor`
                    """
                ).rstrip(),
                visual_acceptance="- `N/A (why=mixed fixture)`",
            )
            self._write_code_draft(root, plan_rel, target_paths=["docs/plans/README.md", "scripts/plan_queue.py"])

            payload = MODULE.small_slice_payload(root, plan_rel)

        self.assertFalse(payload["reduced_conveyor_eligible"])
        self.assertIn("actual_bundle_family_not_small_slice", payload["fail_closed_reasons"])

    def test_small_slice_payload_fails_closed_for_rollout_packet_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            plan_rel = "docs/plans/260328_0903_packet.md"
            self._write_plan(
                root,
                plan_rel,
                review_artifacts="- Doc review (docs-only): `docs/doc_reviews/260328_0903_packet.md`",
                rollout_packet_handoff=dedent(
                    """\
                    - Role: `source-packet`
                    - Packet path: `docs/rollout_packets/260328_0903_planveyor_packet.md`
                    - Target repo: `planveyor`
                    - Suggested target plan slug: `fixture`
                    - Queue after import: `yes`
                    """
                ).rstrip(),
                small_slice_classifier=dedent(
                    """\
                    - Requested profile: `reduced-same-session-censors`
                    - Expected bundle family: `docs-only`
                    - Helper validation: `exact-bundle-match`
                    - Drift behavior: `fail-closed-to-full-conveyor`
                    """
                ).rstrip(),
                visual_acceptance="- `N/A (why=packet fixture)`",
            )
            self._write_code_draft(root, plan_rel, target_paths=["docs/plans/README.md"])

            payload = MODULE.small_slice_payload(root, plan_rel)

        self.assertFalse(payload["reduced_conveyor_eligible"])
        self.assertIn("cross_repo_rollout_packet_present", payload["fail_closed_reasons"])

    def test_small_slice_payload_fails_closed_for_runtime_visual_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            plan_rel = "docs/plans/260328_0904_runtime.md"
            self._write_plan(
                root,
                plan_rel,
                review_artifacts="- Doc review (docs-only): `docs/doc_reviews/260328_0904_runtime.md`",
                small_slice_classifier=dedent(
                    """\
                    - Requested profile: `reduced-same-session-censors`
                    - Expected bundle family: `docs-only`
                    - Helper validation: `exact-bundle-match`
                    - Drift behavior: `fail-closed-to-full-conveyor`
                    """
                ).rstrip(),
                visual_acceptance=dedent(
                    """\
                    - `Port`: `8044`
                    - `Modes to test`: `primary`
                    """
                ).rstrip(),
            )
            self._write_code_draft(root, plan_rel, target_paths=["docs/plans/README.md"])

            payload = MODULE.small_slice_payload(root, plan_rel)

        self.assertFalse(payload["reduced_conveyor_eligible"])
        self.assertIn("visual_acceptance_not_na", payload["fail_closed_reasons"])

    def test_small_slice_payload_fails_closed_for_plain_visual_acceptance_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            plan_rel = "docs/plans/260613_1453_docs_only_plain_visual_text.md"
            self._write_plan(
                root,
                plan_rel,
                review_artifacts="- Doc review (docs-only): `docs/doc_reviews/260613_1453_docs_only_plain_visual_text.md`",
                small_slice_classifier=dedent(
                    """\
                    - Requested profile: `reduced-same-session-censors`
                    - Expected bundle family: `docs-only`
                    - Helper validation: `exact-bundle-match`
                    - Drift behavior: `fail-closed-to-full-conveyor`
                    """
                ).rstrip(),
                visual_acceptance="Runtime browser smoke is required.",
            )
            self._write_code_draft(root, plan_rel, target_paths=["docs/plans/README.md"])

            payload = MODULE.small_slice_payload(root, plan_rel)

        self.assertFalse(payload["visual_acceptance_is_na"])
        self.assertFalse(payload["reduced_conveyor_eligible"])
        self.assertIn("visual_acceptance_not_na", payload["fail_closed_reasons"])

    def test_small_slice_payload_fails_closed_for_visual_acceptance_text_under_subheading(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            plan_rel = "docs/plans/260613_1455_docs_only_visual_subheading_text.md"
            self._write_plan(
                root,
                plan_rel,
                review_artifacts="- Doc review (docs-only): `docs/doc_reviews/260613_1455_docs_only_visual_subheading_text.md`",
                small_slice_classifier=dedent(
                    """\
                    - Requested profile: `reduced-same-session-censors`
                    - Expected bundle family: `docs-only`
                    - Helper validation: `exact-bundle-match`
                    - Drift behavior: `fail-closed-to-full-conveyor`
                    """
                ).rstrip(),
                visual_acceptance=dedent(
                    """\
                    `N/A (why=process ADR; no browser UI surface)`

                    ### Visual regression scenarios (docs/smoke_visual.md)
                    Open the browser and inspect the page.
                    """
                ).rstrip(),
            )
            self._write_code_draft(root, plan_rel, target_paths=["docs/plans/README.md"])

            payload = MODULE.small_slice_payload(root, plan_rel)

        self.assertFalse(payload["visual_acceptance_is_na"])
        self.assertFalse(payload["reduced_conveyor_eligible"])
        self.assertIn("visual_acceptance_not_na", payload["fail_closed_reasons"])

    def test_plan_runtime_payload_projects_oracle_terminal_disposition(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            rel_path = "docs/plans/260813_1218_terminal_payload.md"
            self._write_plan(root, rel_path, status="Done")

            payload = MODULE.plan_runtime_payload(root, rel_path)

        assert payload is not None
        self.assertEqual(payload["status_value"], "Done")
        self.assertEqual(payload["terminal_disposition"], "ordinary")
        self.assertTrue(payload["terminal_disposition_reason"])

    def test_post_cutover_authority_red_cannot_advance_terminal_queue_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").mkdir()
            active_rel = "docs/plans/260814_0920_machine_authority_terminal_red.md"
            self._write_plan(
                root,
                active_rel,
                status="Done",
                meta_json=json.dumps({"plan_meta": {"cluster": "process"}}),
                machine_authority=False,
            )
            paths = self._queue_paths(root)
            self._save_active_pending_queue(paths, active_rel=active_rel, pending_rels=[])
            before = self._queue_bytes_snapshot(paths)
            runtime = MODULE.plan_runtime_payload(root, active_rel)

            assert runtime is not None
            self.assertEqual(runtime["queue_closeout_kind"], "route_guard_blocked")
            self.assertFalse(runtime["queue_closeout_ready"])
            with self.assertRaises(MODULE.QueueError) as raised:
                MODULE.advance_queue(paths, "Done", now="2026-08-14T12:18:00Z")
            self._assert_queue_bytes_snapshot(paths, before)
            payload = raised.exception.payload
            assert payload is not None
            self.assertEqual(payload["error"], MODULE.TERMINAL_ADMISSION_ERROR)
            self.assertEqual(payload["reason_code"], "terminal_closeout_not_ready")
            self.assertEqual(payload["oracle_status"], "Done")
            self.assertEqual(payload["queue_closeout_kind"], "route_guard_blocked")
            self.assertFalse(payload["queue_closeout_ready"])

    def test_terminal_admission_rejections_are_structured_zero_write_and_preselector(self) -> None:
        cases = (
            ("advance_nonterminal_in_progress", "advance", "In progress", "ordinary", "not_ready", False, "terminal_status_assertion_mismatch"),
            ("advance_nonterminal_ready_for_coder", "advance", "Ready for Coder", "ordinary", "not_ready", False, "terminal_status_assertion_mismatch"),
            ("advance_done_vs_superseded", "advance", "Superseded", "ordinary", "terminal_status", True, "terminal_status_assertion_mismatch"),
            ("advance_superseded_vs_done", "advance", "Done", "ordinary", "terminal_status", True, "terminal_status_assertion_mismatch"),
            ("advance_manager_mode_preselector", "advance", "In progress", "ordinary", "not_ready", False, "terminal_status_assertion_mismatch"),
            ("advance_accepted_red_pending", "advance", "Done", "accepted_red_supersession", "terminal_status", True, "accepted_red_reconciliation_required"),
            ("advance_accepted_red_recovered", "advance", "Superseded", "accepted_red_supersession", "terminal_status", True, "accepted_red_reconciliation_required"),
            ("advance_accepted_red_mismatch", "advance", "Superseded", "accepted_red_supersession", "terminal_status", True, "accepted_red_reconciliation_required"),
            ("advance_route_guard", "advance", "Done", "ordinary", "route_guard_blocked", False, "terminal_closeout_not_ready"),
            ("advance_missing_disposition", "advance", "Done", None, "terminal_status", True, "terminal_disposition_invalid"),
            ("closeout_accepted_red", "closeout", "Superseded", "accepted_red_supersession", "terminal_status", True, "accepted_red_reconciliation_required"),
            ("closeout_accepted_red_recovered", "closeout", "Superseded", "accepted_red_supersession", "terminal_status", True, "accepted_red_reconciliation_required"),
            ("closeout_route_guard", "closeout", "Done", "ordinary", "route_guard_blocked", False, "terminal_closeout_not_ready"),
            ("closeout_ready_string", "closeout", "Done", "ordinary", "terminal_status", "true", "terminal_closeout_not_ready"),
            ("closeout_ready_missing", "closeout", "Done", "ordinary", "terminal_status", None, "terminal_closeout_not_ready"),
            ("closeout_unknown_disposition", "closeout", "Done", "unknown", "terminal_status", True, "terminal_disposition_invalid"),
            ("closeout_unknown_nonterminal_disposition", "closeout", "In progress", "unknown", "not_ready", False, "terminal_disposition_invalid"),
        )
        for (
            name,
            operation,
            status,
            disposition,
            closeout_kind,
            closeout_ready,
            reason_code,
        ) in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                (root / ".git").mkdir()
                active_rel = "docs/plans/260813_1218_active.md"
                self._write_plan(root, active_rel)
                pending_rels: list[str] = []
                if name == "advance_manager_mode_preselector":
                    pending_rel = "docs/plans/260813_1219_pending.md"
                    self._write_plan(root, pending_rel)
                    pending_rels.append(pending_rel)
                paths = self._queue_paths(root)
                self._save_active_pending_queue(paths, active_rel=active_rel, pending_rels=pending_rels)
                before = self._queue_bytes_snapshot(paths)
                runtime = {
                    "plan": active_rel,
                    "status_value": status,
                    "terminal_disposition": disposition,
                    "terminal_disposition_reason": "fixture",
                    "runtime_class": "executable",
                    "queue_closeout_kind": closeout_kind,
                    "queue_closeout_ready": closeout_ready,
                    "queue_closeout_reason": "fixture",
                }
                asserted_status = (
                    "Superseded"
                    if name in {"advance_accepted_red_recovered", "advance_superseded_vs_done"}
                    else "Done"
                )
                manager_mode = "manager-collab" if name == "advance_manager_mode_preselector" else None
                with mock.patch.object(MODULE, "plan_runtime_payload", return_value=runtime), mock.patch.object(
                    MODULE,
                    "_select_closeout_candidate",
                    side_effect=AssertionError("terminal admission must precede candidate selection"),
                ), mock.patch.object(
                    MODULE,
                    "_select_transition_candidate_with_manager_mode",
                    side_effect=AssertionError("terminal admission must precede manager-mode candidate selection"),
                ):
                    with self.assertRaises(MODULE.QueueError) as raised:
                        if operation == "advance":
                            MODULE.advance_queue(
                                paths,
                                asserted_status,
                                manager_mode=manager_mode,
                                now="2026-08-13T12:18:00Z",
                            )
                        else:
                            MODULE.closeout_queue(paths, now="2026-08-13T12:18:00Z")

                self._assert_queue_bytes_snapshot(paths, before)
                payload = raised.exception.payload
                assert payload is not None
                self.assertEqual(payload["error"], MODULE.TERMINAL_ADMISSION_ERROR)
                self.assertEqual(payload["reason_code"], reason_code)
                self.assertEqual(payload["advanced"], False)
                self.assertIsNone(payload["finalized_plan"])
                self.assertIsNone(payload["next_plan"])
                self.assertEqual(payload["queue_complete"], False)
                self.assertEqual(payload["active_plan"], active_rel)
                self.assertEqual(payload["asserted_final_status"], asserted_status if operation == "advance" else None)
                self.assertEqual(payload["oracle_status"], status)
                self.assertEqual(payload["terminal_disposition"], disposition)
                self.assertEqual(payload["queue_closeout_kind"], closeout_kind)
                self.assertEqual(payload["queue_closeout_ready"], closeout_ready)

    def test_terminal_admission_finalizes_only_oracle_confirmed_terminal_statuses(self) -> None:
        for operation in ("advance", "closeout"):
            for status in ("Done", "Superseded"):
                with self.subTest(operation=operation, status=status), tempfile.TemporaryDirectory() as tmpdir:
                    root = Path(tmpdir)
                    (root / ".git").mkdir()
                    active_rel = "docs/plans/260813_1218_active.md"
                    self._write_plan(root, active_rel)
                    paths = self._queue_paths(root)
                    self._save_active_pending_queue(paths, active_rel=active_rel, pending_rels=[])
                    runtime = {
                        "plan": active_rel,
                        "status_value": status,
                        "terminal_disposition": "ordinary",
                        "terminal_disposition_reason": "fixture",
                        "runtime_class": "executable",
                        "queue_closeout_kind": "terminal_status",
                        "queue_closeout_ready": True,
                        "queue_closeout_reason": "fixture",
                    }
                    with mock.patch.object(MODULE, "plan_runtime_payload", return_value=runtime):
                        if operation == "advance":
                            result = MODULE.advance_queue(paths, status, now="2026-08-13T12:18:00Z")
                        else:
                            result = MODULE.closeout_queue(paths, now="2026-08-13T12:18:00Z")

                    self.assertTrue(result["advanced"])
                    self.assertEqual(result["final_status"], status)
                    self.assertEqual(result["items"][0]["final_status"], status)
                    self.assertEqual(result["items"][0]["state"], status.lower())

    def test_terminal_admission_cli_json_rejections_preserve_payload_and_queue_bytes(self) -> None:
        cases = (
            ("advance", "Done", "ordinary", "route_guard_blocked", False, "terminal_closeout_not_ready"),
            ("closeout", "Superseded", "accepted_red_supersession", "terminal_status", True, "accepted_red_reconciliation_required"),
        )
        for operation, status, disposition, closeout_kind, closeout_ready, reason_code in cases:
            with self.subTest(operation=operation, reason_code=reason_code), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                (root / ".git").mkdir()
                active_rel = "docs/plans/260813_1218_active.md"
                self._write_plan(root, active_rel)
                paths = self._queue_paths(root)
                self._save_active_pending_queue(paths, active_rel=active_rel, pending_rels=[])
                before = self._queue_bytes_snapshot(paths)
                runtime = {
                    "plan": active_rel,
                    "status_value": status,
                    "terminal_disposition": disposition,
                    "terminal_disposition_reason": "fixture",
                    "runtime_class": "executable",
                    "queue_closeout_kind": closeout_kind,
                    "queue_closeout_ready": closeout_ready,
                    "queue_closeout_reason": "fixture",
                }
                stdout = io.StringIO()
                argv = [
                    "--project-root",
                    str(root),
                    operation,
                    "--manager-mode",
                    "manager-collab",
                    "--json",
                ]
                if operation == "advance":
                    argv[3:3] = ["--final-status", "Done"]
                with mock.patch.object(MODULE, "plan_runtime_payload", return_value=runtime), mock.patch("sys.stdout", stdout):
                    result = MODULE.main(argv)

                self._assert_queue_bytes_snapshot(paths, before)
                payload = json.loads(stdout.getvalue())
                self.assertEqual(result, 1)
                self.assertEqual(payload["error"], MODULE.TERMINAL_ADMISSION_ERROR)
                self.assertEqual(payload["reason_code"], reason_code)
                self.assertFalse(payload["advanced"])
                self.assertIsNone(payload["finalized_plan"])
                self.assertIsNone(payload["next_plan"])


class PlanQueueFacadeRecoveryTests(unittest.TestCase):
    """A sibling sees the recovery command and runs it through the public facade."""

    @staticmethod
    def _interrupt_transaction(paths: MODULE.QueuePaths) -> None:
        def interrupt(phase: str, _paths: MODULE.QueuePaths, _marker: dict[str, object]) -> None:
            if phase == "state":
                raise RuntimeError("interrupt:state")

        MODULE._TRANSACTION_PHASE_HOOK = interrupt
        try:
            with MODULE.queue_lock(paths, "exclusive", command="fixture", timeout=0.1):
                MODULE._commit_transaction(
                    paths,
                    operation="fixture",
                    after_state=MODULE.build_state(mode="recover_fixture", items=[], now="2026-10-01T00:00:00Z"),
                    audit_rows=[MODULE._audit_row("fixture", at="2026-10-01T00:00:00Z")],
                )
        except RuntimeError as exc:
            if str(exc) != "interrupt:state":
                raise
        else:
            raise AssertionError("fixture transaction was not interrupted")
        finally:
            MODULE._TRANSACTION_PHASE_HOOK = None

    def test_public_facade_names_and_runs_queue_recovery(self) -> None:
        with AuthorityFixture(identity="planveyor") as fixture:
            entry = write_fixture_file(
                fixture.runtime_root,
                "bin/planveyor",
                (REPO_ROOT / "bin" / "planveyor").read_bytes(),
                executable=True,
            )
            commit_all(fixture.runtime_root, "public queue facade")
            self._interrupt_transaction(MODULE.queue_paths(fixture.target_root))
            environment = fixture.environment()
            state_root = fixture.root / "state"
            state_root.mkdir()
            environment["PLANVEYOR_STATE_ROOT"] = str(state_root)
            for root in (fixture.runtime_root, fixture.target_root):
                physical_root = subprocess.check_output(
                    ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
                    env=environment,
                    text=True,
                ).strip()
                self.assertEqual(Path(physical_root).resolve(), root.resolve())
                subprocess.run(
                    ["git", "-C", str(root), "rev-parse", "--verify", "HEAD^{commit}"],
                    env=environment,
                    capture_output=True,
                    check=True,
                )
            paths = MODULE.queue_paths(fixture.target_root)
            before_state = paths.state_path.read_bytes()
            marker_path = fixture.target_root / MODULE.TXN_FILE_NAME
            before_marker = marker_path.read_bytes()

            def facade(*arguments: str) -> subprocess.CompletedProcess[str]:
                return subprocess.run(
                    [str(entry), "--project", str(fixture.target_root), *arguments],
                    cwd=fixture.target_root,
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=180,
                )

            shown = facade("planveyor_q_show", "--json")
            self.assertEqual(paths.state_path.read_bytes(), before_state)
            self.assertEqual(marker_path.read_bytes(), before_marker)
            self.assertFalse(paths.log_path.exists())
            recovered = facade("planveyor_q_recover", "--json")
            self.assertFalse(marker_path.exists())
            self.assertEqual(paths.state_path.read_bytes(), before_state)
            self.assertTrue(paths.log_path.read_text(encoding="utf-8").strip())
            rechecked = facade("planveyor_runtime_py", "plan_queue.py", "recover", "--json")

        self.assertEqual(shown.returncode, 1, shown.stdout + shown.stderr)
        shown_payload = json.loads(shown.stdout)
        self.assertEqual(shown_payload["error"], "recovery_required")
        self.assertEqual(shown_payload["recovery_command"], "planveyor_q_recover")
        self.assertEqual(recovered.returncode, 0, recovered.stdout + recovered.stderr)
        recovered_payload = json.loads(recovered.stdout)
        self.assertEqual(recovered_payload["result"], "recovered")
        self.assertTrue(recovered_payload["mutation_performed"])
        self.assertEqual(rechecked.returncode, 0, rechecked.stdout + rechecked.stderr)
        self.assertEqual(json.loads(rechecked.stdout)["result"], "clean")


if __name__ == "__main__":
    unittest.main()

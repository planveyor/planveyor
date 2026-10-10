#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import json
import shlex
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from pathlib import Path
from textwrap import dedent
from unittest import mock


MODULE_PATH = Path(__file__).with_name("plan_handoff_digest.py")
SPEC = importlib.util.spec_from_file_location("plan_handoff_digest", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
sys.path.insert(0, str(Path(__file__).with_name("plan_status_oracle.py").parent))
import plan_status_oracle as PLAN_STATUS_ORACLE
from test_support.process_contract_fixtures import temporary_git_root


PLAN_REL = "docs/plans/260624_1442_process_planner_coder_handoff_digest_helper.md"
DRAFT_REL = "docs/code_drafts/260624_1442_process_planner_coder_handoff_digest_helper__code_draft.md"
REVIEW_REL = "docs/code_reviews/260624_1442_process_planner_coder_handoff_digest_helper.md"
TARGET_REL = "scripts/plan_handoff_digest.py"
TEST_REL = "scripts/test_plan_handoff_digest.py"
RUNBOOK_REL = "docs/tools/owner_runbook_codex.md"


class PlanHandoffDigestTests(unittest.TestCase):
    def _write(self, root: Path, rel_path: str, text: str) -> Path:
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def _write_plan(
        self,
        root: Path,
        *,
        status: str = "Ready for Arch review",
        draft_refs: list[str] | None = None,
        review_refs: list[str] | None = None,
    ) -> Path:
        draft_refs = draft_refs if draft_refs is not None else [DRAFT_REL]
        review_refs = review_refs if review_refs is not None else [REVIEW_REL]
        context_lines = "\n".join(f"- Code draft(s): `{draft_ref}`" for draft_ref in draft_refs)
        review_lines = "\n".join(f"- Code review (primary): `{review_ref}`" for review_ref in review_refs)
        return self._write(
            root,
            PLAN_REL,
            dedent(
                f"""\
                # Plan: handoff digest fixture

                **Date:** 2026-06-24 18:45 MSK
                **Stage:** Stage 1
                **Priority:** P2
                **Plan type:** dev
                **Status:** {status}

                **Context links (source of truth):**
                - Source analysis review: `docs/doc_reviews/260624_1441_process_planner_coder_handoff_digest_analysis.md`
                {context_lines}

                ## Review artifacts
                {review_lines}
                """
            ),
        )

    def _write_code_draft(self, root: Path, *, targets: list[str] | None = None, plan: str = PLAN_REL) -> None:
        targets = targets or [TARGET_REL, TEST_REL, RUNBOOK_REL]
        payload = {
            "code_draft_meta": {
                "plan": plan,
                "cluster": "process",
                "targets": [{"path": target, "kind": "py"} for target in targets],
                "deleted_paths": [],
            }
        }
        self._write(
            root,
            DRAFT_REL,
            "# Code draft\n\n```json\n" + json.dumps(payload, indent=2) + "\n```\n",
        )
        for target in targets:
            self._write(root, target, "stub\n")

    def _write_review(self, root: Path, *, status: str = "✅ OK") -> None:
        self._write(
            root,
            REVIEW_REL,
            dedent(
                f"""\
                # Code review

                **Status:** {status}
                """
            ),
        )

    def _oracle(self, state: str = "current_green", *, status: str = "Ready for Arch review"):
        def runner(plan_path: Path, repo_root: Path):
            return MODULE.HostResult(
                "status_oracle",
                "ok" if state not in {"current_red", "needs_reviewer_rerun"} else "red_or_inconsistent",
                "fixture oracle",
                fields={
                    "status_value": status,
                    "status_norm": " ".join(status.lower().split()),
                    "review_readback_state": state,
                    "promoted_from_state": "valid",
                },
            )

        return runner

    def _bundle(self, state: str = "ok"):
        def runner(plan_path: Path, repo_root: Path):
            return MODULE.HostResult("bundle_preflight", state, "fixture bundle")

        return runner

    def _default_oracle_with_payload(self, root: Path, payload: dict[str, object]):
        launcher = self._write(root, "bin/planveyor", "#!/bin/sh\n")
        launcher.chmod(0o755)
        with mock.patch(
            "plan_handoff_digest.subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=["planveyor"],
                returncode=0,
                stdout=json.dumps(payload),
                stderr="",
            ),
        ), mock.patch.object(MODULE, "_runtime_root", return_value=root):
            return MODULE.default_oracle_runner(root / PLAN_REL, root)

    def _digest(self, root: Path, *, oracle=None, bundle=None):
        return MODULE.build_digest(
            PLAN_REL,
            repo_root=root,
            oracle_runner=oracle or self._oracle(),
            bundle_runner=bundle or self._bundle(),
        )

    def test_green_digest_summarizes_authoritative_hosts_without_becoming_authority(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            self._write_plan(root)
            self._write_code_draft(root)
            self._write_review(root)

            payload = self._digest(root)

        self.assertEqual(payload["schema"], "handoff_digest.v1")
        self.assertEqual(payload["state"], "ok")
        self.assertEqual(payload["authority"], "derived_read_only")
        self.assertIn("manager_routing", payload["non_authoritative_for"])
        self.assertIn("target_inventory", payload["non_authoritative_for"])
        self.assertEqual(payload["truth_hosts"]["review_artifact"]["state"], "ok")
        self.assertEqual(payload["summary"]["code_draft_targets"], [TARGET_REL, TEST_REL, RUNBOOK_REL])

    def test_machine_authority_tagged_ref_uses_canonical_digest_and_rejects_drift(self) -> None:
        plan_rel = "docs/plans/260814_0920_machine_authority_ref_fixture.md"
        draft_rel = "docs/code_drafts/260814_0920_machine_authority_ref_fixture__code_draft.md"
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            decision: dict[str, object] = {
                "schema_version": PLAN_STATUS_ORACLE.MACHINE_AUTHORITY_DECISION_SCHEMA,
                "decision_id": "mad-260814-0920",
                "applicability": "required",
                "state": "frozen",
                "impacts": ["authorization"],
                "cutover_policy": copy.deepcopy(PLAN_STATUS_ORACLE.MACHINE_AUTHORITY_DECISION_HANDOFF_POLICY),
                "recommended_route": {
                    "id": "fixture_route",
                    "kind": "structured_carrier",
                    "authority_host": {
                        "repo": "current",
                        "path": plan_rel,
                        "locator": "json_pointer:/plan_meta/machine_authority_decision",
                    },
                    "canonical_writer": "fixture-writer",
                    "canonical_reader": "fixture-reader",
                    "derived_consumers": ["fixture-consumer"],
                    "schema": "fixture.v1",
                    "identity_fields": ["decision_id"],
                    "cardinality": "one",
                    "failure_behavior": {
                        key: "fail_closed" for key in PLAN_STATUS_ORACLE.MACHINE_AUTHORITY_DECISION_FAILURE_KEYS
                    },
                },
                "alternatives": [
                    {
                        "id": "other_route",
                        "kind": "fixture",
                        "disposition": "rejected",
                        "tradeoff": "fixture",
                    }
                ],
                "owner_confirmation": {
                    "state": "confirmed",
                    "question_ref": "Q1",
                    "decision_id": "mad-260814-0920",
                    "route_id": "fixture_route",
                    "carrier_sha256": "",
                },
            }
            digest = PLAN_STATUS_ORACLE.machine_authority_decision_sha256(decision)
            confirmation = decision["owner_confirmation"]
            assert isinstance(confirmation, dict)
            confirmation["carrier_sha256"] = digest
            plan = self._write(
                root,
                plan_rel,
                "# Machine authority fixture\n\n"
                "**Status:** Ready for Coder\n\n"
                "## Meta\n\n```json\n"
                + json.dumps({"plan_meta": {"machine_authority_decision": decision}}, ensure_ascii=False, indent=2)
                + "\n```\n\n## Q&A log\n\n"
                "- [2026-08-14 09:20 MSK] (Architect -> Owner, id=Q1, status=open) Fixture question\n"
                "- [2026-08-14 09:21 MSK] (Owner -> Architect, id=Q1, status=closed) Fixture answer\n",
            )
            draft_payload = {
                "code_draft_meta": {
                    "plan": plan_rel,
                    "machine_authority_decision_ref": {
                        "applicability": "required",
                        "decision_id": "mad-260814-0920",
                        "carrier_sha256": digest,
                    },
                }
            }
            draft = self._write(
                root,
                draft_rel,
                "# Fixture code draft\n\n```json\n" + json.dumps(draft_payload, ensure_ascii=False, indent=2) + "\n```\n",
            )
            green = PLAN_STATUS_ORACLE.machine_authority_decision_readback(plan)

            draft_payload["code_draft_meta"]["machine_authority_decision_ref"]["carrier_sha256"] = "0" * 64
            draft.write_text(
                "# Fixture code draft\n\n```json\n" + json.dumps(draft_payload, ensure_ascii=False, indent=2) + "\n```\n",
                encoding="utf-8",
            )
            red = PLAN_STATUS_ORACLE.machine_authority_decision_readback(plan)

        self.assertEqual((green.state, green.reason_code, green.ref_state), ("frozen_confirmed", "ok", "valid"))
        self.assertEqual(green.carrier_sha256, digest)
        self.assertEqual((red.state, red.reason_code, red.ref_state), ("invalid", "code_draft_ref_invalid", "invalid"))

    def test_missing_code_draft_fails_closed(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            self._write_plan(root)
            self._write_review(root)

            payload = self._digest(root)

        self.assertEqual(payload["state"], "missing")
        self.assertEqual(payload["truth_hosts"]["code_draft"]["state"], "missing")
        self.assertIn("code_draft", {blocker["host"] for blocker in payload["blockers"]})

    def test_ambiguous_multiple_code_drafts_fail_closed(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            self._write_plan(
                root,
                draft_refs=[
                    DRAFT_REL,
                    "docs/code_drafts/260624_1442_process_planner_coder_handoff_digest_helper__other.md",
                ],
            )
            self._write_code_draft(root)
            self._write_review(root)

            payload = self._digest(root)

        self.assertEqual(payload["state"], "ambiguous")
        self.assertEqual(payload["truth_hosts"]["code_draft"]["state"], "ambiguous")

    def test_present_but_red_review_oracle_fails_closed(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            self._write_plan(root)
            self._write_code_draft(root)
            self._write_review(root, status="❌ S1 Blocker(s)")

            payload = self._digest(root, oracle=self._oracle("current_red"))

        self.assertEqual(payload["state"], "red_or_inconsistent")
        self.assertEqual(payload["truth_hosts"]["review_artifact"]["state"], "red_or_inconsistent")
        self.assertEqual(payload["truth_hosts"]["status_oracle"]["state"], "red_or_inconsistent")

    def test_default_oracle_runner_fails_closed_on_blocker_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            result = self._default_oracle_with_payload(
                root,
                {
                    "status_value": "Ready for Review",
                    "status_norm": "ready for review",
                    "review_readback_state": "none",
                    "promoted_from_state": "valid",
                    "route_guard_kind": "none",
                    "blocker_state": "blocked",
                    "terminal_ready_state": "blocked",
                },
            )

        self.assertEqual(result.state, "red_or_inconsistent")
        self.assertIn("blocking", result.reason)

    def test_default_oracle_runner_fails_closed_on_route_guard_kind(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            result = self._default_oracle_with_payload(
                root,
                {
                    "status_value": "Ready for Review",
                    "status_norm": "ready for review",
                    "review_readback_state": "none",
                    "promoted_from_state": "valid",
                    "route_guard_kind": "plan_gap",
                    "blocker_state": "unknown",
                    "terminal_ready_state": "unknown",
                },
            )

        self.assertEqual(result.state, "red_or_inconsistent")
        self.assertEqual(result.reason, "oracle route_guard_kind is blocking")

    def test_default_oracle_runner_fails_closed_on_owner_qna_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            result = self._default_oracle_with_payload(
                root,
                {
                    "status_value": "Ready for Review",
                    "status_norm": "ready for review",
                    "review_readback_state": "none",
                    "promoted_from_state": "valid",
                    "route_guard_kind": "none",
                    "blocker_state": "unknown",
                    "terminal_ready_state": "unknown",
                    "owner_qna_readback_state": "blocked",
                },
            )

        self.assertEqual(result.state, "red_or_inconsistent")
        self.assertEqual(result.reason, "oracle owner_qna_readback_state is blocking")

    def test_engaged_oracle_keeps_current_state_protocol(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = self._write(root, PLAN_REL, "# Fixture\n")
            runtime_root = root / "runtime"
            oracle_path = self._write(runtime_root, "scripts/plan_status_oracle.py", "# fixture\n")
            context = SimpleNamespace(
                state="engaged",
                runtime_pin=SimpleNamespace(runtime_root=runtime_root),
            )
            with mock.patch.object(MODULE, "context_for_reader", return_value=context), mock.patch.object(
                MODULE.contract_authority_children,
                "python_entry_argv",
                return_value=["authority-python", str(oracle_path)],
            ) as child_argv, mock.patch.object(MODULE, "context_to_json", return_value="{}"), mock.patch.object(
                MODULE.subprocess,
                "run",
                return_value=subprocess.CompletedProcess(
                    args=["authority-python"],
                    returncode=0,
                    stdout=(
                        "status_value=Ready for Coder\n"
                        "status_norm=ready for coder\n"
                        "review_readback_state=none\n"
                        "promoted_from_state=valid\n"
                        "route_guard_kind=none\n"
                        "blocker_state=unknown\n"
                        "terminal_ready_state=unknown\n"
                    ),
                    stderr="",
                ),
            ):
                result = MODULE.default_oracle_runner(plan_path, root, context=context)

        child_argv.assert_called_once_with(
            context,
            oracle_path,
            ("--current-state", PLAN_REL),
            python_executable=sys.executable,
        )
        self.assertEqual(result.state, "ok", result.reason)

    def test_missing_review_is_not_required_before_review_handoff(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            self._write_plan(root, status="Ready for Coder")
            self._write_code_draft(root)

            payload = self._digest(root, oracle=self._oracle("none", status="Ready for Coder"))

        self.assertEqual(payload["state"], "ok")
        self.assertEqual(payload["truth_hosts"]["review_artifact"]["state"], "not_required")

    def test_missing_review_is_required_after_review_handoff(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            self._write_plan(root, status="Ready for Arch review")
            self._write_code_draft(root)

            payload = self._digest(root)

        self.assertEqual(payload["state"], "missing")
        self.assertEqual(payload["truth_hosts"]["review_artifact"]["state"], "missing")

    def test_status_oracle_mismatch_fails_closed(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            self._write_plan(root, status="Ready for Arch review")
            self._write_code_draft(root)
            self._write_review(root)

            payload = self._digest(root, oracle=self._oracle(status="Ready for Review"))

        self.assertEqual(payload["state"], "red_or_inconsistent")
        self.assertEqual(payload["truth_hosts"]["status_oracle"]["state"], "red_or_inconsistent")

    def test_default_children_use_runtime_and_explicit_consumer_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            consumer_root = root / "consumer"
            runtime_root = root / "runtime"
            consumer_facade_hit = root / "consumer-facade-hit"
            consumer_root.mkdir()
            runtime_root.mkdir()
            plan_path = self._write(consumer_root, "docs/plans/fixture.md", "# Fixture\n")
            self._write(
                consumer_root,
                "scripts/planveyor.zsh",
                f": > {shlex.quote(str(consumer_facade_hit))}\n",
            )

            _write = self._write
            _write(
                runtime_root,
                "bin/planveyor",
                dedent(
                    f"""\
                    #!/bin/sh
                    [ "$1" = "--project" ] || exit 91
                    [ "$2" = {shlex.quote(str(consumer_root))} ] || exit 92
                    [ "$PWD" = {shlex.quote(str(consumer_root))} ] || exit 93
                    case "$3" in
                      planveyor_plan_status_oracle)
                        [ "$4" = "--json" ] || exit 94
                        [ "$5" = "docs/plans/fixture.md" ] || exit 95
                        printf '%s\\n' '{{"status_value":"Ready for Coder","status_norm":"ready for coder","review_readback_state":"none","promoted_from_state":"valid","route_guard_kind":"none","blocker_state":"unknown","terminal_ready_state":"unknown"}}'
                        ;;
                      planveyor_plan_bundle)
                        [ "$4" = "--preflight" ] || exit 96
                        [ "$5" = "docs/plans/fixture.md" ] || exit 97
                        ;;
                      *) exit 98 ;;
                    esac
                    """
                ),
            ).chmod(0o755)

            with mock.patch.object(MODULE, "_runtime_root", return_value=runtime_root):
                oracle = MODULE.default_oracle_runner(plan_path, consumer_root)
                bundle = MODULE.default_bundle_runner(plan_path, consumer_root)

        self.assertEqual(oracle.state, "ok", oracle.reason)
        self.assertEqual(bundle.state, "ok", bundle.reason)
        self.assertFalse(consumer_facade_hit.exists())


if __name__ == "__main__":
    unittest.main()

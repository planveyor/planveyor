#!/usr/bin/env python3
"""Focused finite-policy and engaged-tracker tests for merge-gate v1."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from types import SimpleNamespace
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in os.sys.path:
    os.sys.path.insert(0, str(SCRIPT_DIR))

import contract_authority_context as authority
import merge_gate_policy as module
from test_contract_authority_support import planveyor_merge_gate_policy


class MergeGatePolicyTests(unittest.TestCase):
    def parse(self, **kwargs: object) -> module.MergeGatePolicy:
        return module._parse_policy(planveyor_merge_gate_policy(**kwargs))

    def test_golden_without_migration_preserves_v1_commands_order_ledger_and_renderer(self) -> None:
        policy = self.parse()
        self.assertEqual(len(policy.commands), 2)
        self.assertEqual(
            policy.step_keys,
            (
                "step:review_range", "step:merge_notes", "step:plan_harvest",
                "step:canon_sweep", "step:packetization_gate", "step:docs_finalize",
                "step:doc_lint", "step:ledger_lint", "step:post_merge_audit",
                "step:docs_hygiene_archive", "step:docs_hygiene_suggest", "step:ready_to_push",
            ),
        )
        self.assertEqual(module.render_step(policy, "step:doc_lint").splitlines()[-1], "planveyor_doc_lint")
        self.assertEqual(module.render_step(policy, "step:ledger_lint").splitlines()[-1], "consumer_ledger_lint")

    def test_declared_consumer_schema_gate_reaches_tracker_step_and_safe_renderer(self) -> None:
        policy = self.parse(modes=("selected",))
        self.assertEqual(policy.step_keys[0], "step:migrations_gate")
        rendered = module.render_step(policy, "step:migrations_gate")
        self.assertIn("Declared consumer schema gate", rendered)
        self.assertIn("consumer_schema_check", rendered)
        self.assertIn("consumer_schema_precheck selected", rendered)
        self.assertIn("consumer_schema_apply selected", rendered)
        self.assertIn("consumer_schema_resolve", rendered)
        self.assertNotIn("django", rendered.lower())

    def test_missing_or_ambiguous_declared_schema_gate_rejects(self) -> None:
        for modes in ((), ("selected", "selected")):
            with self.subTest(modes=modes):
                with self.assertRaises(module.MergeGatePolicyError):
                    self.parse(modes=modes)
        with self.assertRaises(module.MergeGatePolicyError):
            self.parse(modes=tuple(f"mode{index}" for index in range(17)))
        payload = json.loads(planveyor_merge_gate_policy(modes=("selected",)).decode("utf-8"))
        payload["steps"][0]["migration"]["change_probe"] = "django_migration_paths.v1"
        with self.assertRaises(module.MergeGatePolicyError):
            module._parse_policy(json.dumps(payload).encode("utf-8"))

    def test_optional_ledger_and_declared_doc_lint_command_remain_finite(self) -> None:
        policy = self.parse(ledger_required=False, doc_lint_argv=("planveyor_doc_lint_changed",))
        self.assertNotIn("step:ledger_lint", policy.step_keys)
        self.assertEqual(module.render_step(policy, "step:doc_lint").splitlines()[-1], "planveyor_doc_lint_changed")
        with self.assertRaises(module.MergeGatePolicyError):
            module.render_step(policy, "step:ledger_lint")
        with self.assertRaises(module.MergeGatePolicyError):
            module.render_step(policy, "step:migrations_gate")

    def test_arbitrary_step_list_core_order_and_command_catalog_reject(self) -> None:
        payload = json.loads(planveyor_merge_gate_policy().decode("utf-8"))
        payload["steps"] = [{"id": "step:anything"}]
        with self.assertRaises(module.MergeGatePolicyError):
            module._parse_policy(json.dumps(payload).encode("utf-8"))
        payload = json.loads(planveyor_merge_gate_policy().decode("utf-8"))
        payload["steps"][0], payload["steps"][1] = payload["steps"][1], payload["steps"][0]
        with self.assertRaises(module.MergeGatePolicyError):
            module._parse_policy(json.dumps(payload).encode("utf-8"))
        payload = json.loads(planveyor_merge_gate_policy().decode("utf-8"))
        payload["commands"].append({"id": "unused", "argv": ["unused"]})
        with self.assertRaises(module.MergeGatePolicyError):
            module._parse_policy(json.dumps(payload).encode("utf-8"))

    def test_duplicate_member_rejects_before_dictionary_normalization(self) -> None:
        raw = b'{"schema":"planveyor_merge_gate_policy.v1","schema":"planveyor_merge_gate_policy.v1"}'
        with self.assertRaisesRegex(module.MergeGatePolicyError, "duplicate JSON key"):
            module._parse_policy(raw)

    def test_engaged_minimum_three_cannot_select_inline_or_policy_fallback(self) -> None:
        marker = SimpleNamespace(repository_id="planveyor", required_runtime_api=SimpleNamespace(minimum=3, maximum=5))
        context = SimpleNamespace(state="engaged", project_root=Path("/fixture/planveyor"), marker=marker,
                                  runtime_pin=SimpleNamespace(runtime_api_version=4), behavior_identity="planveyor")
        with mock.patch.object(module.authority, "context_for_reader", return_value=context):
            with self.assertRaisesRegex(module.MergeGatePolicyError, "does not advertise"):
                module._policy_for_context(context)

    def test_matching_generic_engaged_consumer_reads_planveyor_source_policy(self) -> None:
        identity = "consumer_42.alpha"
        marker = SimpleNamespace(repository_id=identity, required_runtime_api=SimpleNamespace(minimum=5, maximum=5))
        context = SimpleNamespace(state="engaged", project_root=Path("/fixture/consumer_42.alpha"), marker=marker,
                                  runtime_pin=SimpleNamespace(runtime_api_version=5), behavior_identity=identity)
        raw = planveyor_merge_gate_policy()
        with (mock.patch.object(module.authority, "context_for_reader", return_value=context),
              mock.patch.object(module.authority, "read_declared_bytes", return_value=raw)):
            policy = module._policy_for_context(context)
        self.assertIsNotNone(policy)
        assert policy is not None
        self.assertEqual(policy.raw_sha256, module.hashlib.sha256(raw).hexdigest())

    def test_invalid_generic_engaged_consumer_never_falls_back_to_legacy_policy(self) -> None:
        cases = (("default", "default"), ("consumer_42", "other_42"), ("consumer@42", "consumer@42"))
        for behavior_identity, marker_identity in cases:
            with self.subTest(behavior_identity=behavior_identity, marker_identity=marker_identity):
                context = SimpleNamespace(state="engaged", project_root=Path("/fixture/consumer"),
                    marker=SimpleNamespace(repository_id=marker_identity, required_runtime_api=SimpleNamespace(minimum=5, maximum=5)),
                    runtime_pin=SimpleNamespace(runtime_api_version=5), behavior_identity=behavior_identity)
                with mock.patch.object(module.authority, "context_for_reader", return_value=context):
                    with self.assertRaises(module.MergeGatePolicyError) as rejected:
                        module._policy_for_context(context)
                self.assertEqual(rejected.exception.reason_code, "merge_policy_capability_required")

    def test_source_policy_repository_id_remains_planveyor_only(self) -> None:
        payload = json.loads(planveyor_merge_gate_policy().decode("utf-8"))
        payload["repository_id"] = "consumer_42.alpha"
        with self.assertRaises(module.MergeGatePolicyError) as rejected:
            module._parse_policy(json.dumps(payload, sort_keys=True).encode("utf-8"))
        self.assertEqual(rejected.exception.reason_code, "merge_policy_identity_invalid")

    def test_markerless_unborn_git_stays_legacy_for_existing_report_callers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True, capture_output=True)
            inherited = os.environ.pop(authority.EXPECTED_CONTEXT_ENV, None)
            try:
                context, policy = module.policy_for_root(root)
            finally:
                if inherited is not None:
                    os.environ[authority.EXPECTED_CONTEXT_ENV] = inherited
        self.assertIsNone(context)
        self.assertIsNone(policy)

    def test_unborn_index_marker_missing_from_worktree_never_falls_back_to_legacy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True, capture_output=True)
            marker = root / authority._snapshot.MARKER_PATH
            marker.parent.mkdir(parents=True)
            marker.write_text("{}\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "--", authority._snapshot.MARKER_PATH], check=True, capture_output=True)
            marker.unlink()
            inherited = os.environ.pop(authority.EXPECTED_CONTEXT_ENV, None)
            try:
                with self.assertRaises(authority.ContractAuthorityError):
                    module.policy_for_root(root)
            finally:
                if inherited is not None:
                    os.environ[authority.EXPECTED_CONTEXT_ENV] = inherited

    def test_unborn_markerless_git_validates_malformed_inherited_context_before_legacy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True, capture_output=True)
            with mock.patch.dict(os.environ, {authority.EXPECTED_CONTEXT_ENV: "not-a-context-envelope"}):
                with self.assertRaisesRegex(authority.ContractAuthorityError, "context"):
                    module.policy_for_root(root)

    def test_binding_headers_are_counted_before_generic_parser_conversion(self) -> None:
        policy = self.parse()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tracker = root / ".planveyor.merge_tracker.md"
            context = SimpleNamespace(project_root=root, generation_sha256="a" * 64)
            tracker.write_text("\n".join((f"POLICY_SCHEMA={module.POLICY_SCHEMA}", f"POLICY_SHA256={policy.raw_sha256}",
                "AUTHORITY_GENERATION=" + "a" * 64, "- [ ] step:review_range", "")), encoding="utf-8")
            with mock.patch.object(module, "policy_for_root", return_value=(context, policy)):
                self.assertIsNotNone(module.validate_tracker_for_root(root, tracker))
                tracker.write_text(tracker.read_text(encoding="utf-8") + f"POLICY_SHA256={policy.raw_sha256}\n", encoding="utf-8")
                with self.assertRaisesRegex(module.MergeGatePolicyError, "exactly once"):
                    module.validate_tracker_for_root(root, tracker)

    def test_metadata_uses_one_capture_and_prints_one_coherent_block(self) -> None:
        context = SimpleNamespace(generation_sha256="a" * 64)
        policy = SimpleNamespace(raw_sha256="b" * 64)
        calls: list[Path] = []
        def capture(root: Path):
            calls.append(root)
            if len(calls) != 1:
                raise AssertionError("metadata must not capture policy twice")
            return context, policy
        stdout = io.StringIO()
        with mock.patch.object(module, "policy_for_root", side_effect=capture), redirect_stdout(stdout):
            result = module._cli(["--root", "/fixture/planveyor", "metadata"])
        self.assertEqual(result, 0)
        self.assertEqual(calls, [Path("/fixture/planveyor")])
        self.assertEqual(stdout.getvalue(), "\n".join(("STATE=engaged", f"POLICY_SCHEMA={module.POLICY_SCHEMA}",
            "POLICY_SHA256=" + "b" * 64, "AUTHORITY_GENERATION=" + "a" * 64, "")))

    def test_metadata_failure_writes_no_stdout(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (mock.patch.object(module, "policy_for_root", side_effect=module.MergeGatePolicyError("merge_policy_invalid", "fixture failure")),
              redirect_stdout(stdout), redirect_stderr(stderr)):
            result = module._cli(["--root", "/fixture/planveyor", "metadata"])
        self.assertEqual(result, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("merge_policy_invalid", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()

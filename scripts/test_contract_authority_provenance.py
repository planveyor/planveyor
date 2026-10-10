"""Historical receipt provenance remains usable after legitimate target changes."""

from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import contract_authority_context as authority
import codex_session_context as provenance
import planveyor_trace_extractor as trace
import role_outcome_receipt as outcome
from authority_bootstrap_test_support import run_bootstrapped_bridge
from test_contract_authority_support import AuthorityFixture, write


class AuthorityProvenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = AuthorityFixture()
        cls.fixture.activate_planveyor(authority.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS)
        pin = run_bootstrapped_bridge(
            cls.fixture,
            "runtime-pin",
            "--runtime-root",
            str(cls.fixture.runtime_root),
            "--entrypoint",
            str(cls.fixture.runtime_root / "scripts" / "planveyor.zsh"),
        )
        if pin.returncode != 0:
            raise AssertionError(pin.stdout + pin.stderr)
        context = run_bootstrapped_bridge(
            cls.fixture,
            "context",
            "--project-root",
            str(cls.fixture.target_root),
            "--runtime-pin-summary",
            pin.stdout.strip(),
        )
        if context.returncode != 0:
            raise AssertionError(context.stdout + context.stderr)
        cls.envelope = json.loads(context.stdout)
        if cls.envelope["schema_version"] != "planveyor_contract_context.v3":
            raise AssertionError(cls.envelope)
        # Receipts are historical evidence. Their parser must work after the
        # live selector becomes invalid and current engagement fails closed.
        write(cls.fixture.target_root, "docs/_meta/planveyor_contract_authority.v1.json", "changed after role\n")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.fixture.close()

    def test_trace_preserves_original_context_without_recapture(self) -> None:
        payload = {"authority_context": self.envelope, "other": "kept"}
        with mock.patch.object(authority, "resolve_top_level_context", side_effect=AssertionError("passive read")), mock.patch.object(
            authority, "validate_before_effect", side_effect=AssertionError("passive read")
        ):
            actual = trace._validated_receipt_authority(payload)
        self.assertEqual(actual, payload)
        self.assertEqual(actual["authority_context"]["schema_version"], "planveyor_contract_context.v3")
        self.assertEqual(trace._validated_receipt_authority({"legacy": True}), {"legacy": True})
        kv = trace._validated_receipt_authority({"authority_context": json.dumps(self.envelope)})
        self.assertEqual(kv["authority_context"], self.envelope)
        self.assertEqual(kv["authority_context"]["schema_version"], "planveyor_contract_context.v3")

    def test_partial_or_tampered_receipt_context_is_rejected(self) -> None:
        for value in ({"state": "engaged"}, {**self.envelope, "generation_sha256": "0" * 64}):
            with self.subTest(value=value):
                with self.assertRaises(authority.ContractAuthorityError):
                    trace._validated_receipt_authority({"authority_context": value})

    def test_session_context_keeps_receipt_entry_observation(self) -> None:
        receipt = write(self.fixture.target_root, ".planveyor.run_receipt.coder", "authority_context=" + json.dumps(self.envelope) + "\n")
        args = provenance.parse_args(["--root", str(self.fixture.target_root), "--run-receipt-path", str(receipt)])
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
            authority, "resolve_top_level_context", side_effect=AssertionError("passive read")
        ):
            observed = provenance.collect_context(args)
        self.assertEqual(observed.authority_context, self.envelope)
        self.assertIn("authority_context=", provenance.render_kv(observed))
        self.assertNotIn("authority_context=", provenance.render_kv(replace(observed, authority_context=None)))

    def test_passive_readers_reject_foreign_historical_root(self) -> None:
        receipt = write(self.fixture.target_root, ".planveyor.run_receipt.foreign", "authority_context=" + json.dumps(self.envelope) + "\n")
        args = provenance.parse_args(["--root", str(self.fixture.root), "--run-receipt-path", str(receipt)])
        with self.assertRaises(authority.ContractAuthorityError) as session_error:
            provenance.collect_context(args)
        self.assertEqual(session_error.exception.reason_code, "receipt_authority_root_mismatch")
        with self.assertRaises(authority.ContractAuthorityError) as trace_error:
            trace._run_receipt_event(receipt, self.fixture.root)
        self.assertEqual(trace_error.exception.reason_code, "receipt_authority_root_mismatch")

    def test_execution_receipt_validates_embedded_root_without_current_bytes(self) -> None:
        root = self.fixture.target_root
        plan_rel = "docs/plans/260101_0000_authority.md"
        receipt = root / ".tmp" / "execution-authority.json"
        paths = outcome.Paths(root=root, plan_rel=plan_rel, plan=root / plan_rel,
                              output_dir=receipt.parent, readback=receipt.parent / "readback.json",
                              preflight=receipt.parent / "preflight.json", execution_receipt=receipt)
        payload = {"schema_version": outcome.EXECUTION_SCHEMA, "run_id": "fixture", "role": "coder",
                   "target_plan": plan_rel, "state": "completed", "exit_code": 0,
                   "process_start_outcome": "started", "authority_context": self.envelope}
        write(root, ".tmp/execution-authority.json", json.dumps(payload))
        with mock.patch.object(authority, "resolve_top_level_context", side_effect=AssertionError("passive read")):
            actual = outcome.read_execution(paths, "coder", "fixture", preflight_blocked=False)
        self.assertEqual(actual["authority_context"], self.envelope)
        payload["authority_context"] = json.dumps(self.envelope)
        write(root, ".tmp/execution-authority.json", json.dumps(payload))
        string_result = outcome.read_execution(paths, "coder", "fixture", preflight_blocked=False)
        self.assertEqual(string_result["authority_context"], payload["authority_context"])
        with self.assertRaises(outcome.OutcomeError) as raised:
            outcome.read_execution(replace(paths, root=root.parent), "coder", "fixture", preflight_blocked=False)
        self.assertEqual(raised.exception.reason_code, "execution_authority_root_mismatch")

    def test_authority_rejection_can_be_persisted_and_read_back(self) -> None:
        from test_role_outcome_receipt import RoleOutcomeFixture, RUN_ID, PLAN_REL

        for value, reason in (({"state": "engaged"}, "execution_authority_context_invalid"),
                              (self.envelope, "execution_authority_root_mismatch")):
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as temporary:
                fixture = RoleOutcomeFixture(temporary)
                preflight, _ = fixture.preflight("coder")
                self.assertEqual(preflight.returncode, 0, preflight.stderr)
                receipt = fixture.execution_receipt("coder")
                data = json.loads(receipt.read_text())
                data["authority_context"] = value
                receipt.write_text(json.dumps(data))
                finished, result = fixture.finalize("coder", receipt)
                self.assertEqual(finished.returncode, 126, finished.stderr)
                self.assertTrue(result["role_outcome_readback_persisted"])
                self.assertEqual(result["reason_code"], reason)
                paths = outcome.Paths(root=fixture.root, plan_rel=PLAN_REL, plan=fixture.plan,
                                      output_dir=fixture.output, readback=fixture.output / "role_outcome_readback.json",
                                      preflight=fixture.output / "role_outcome_preflight.json", execution_receipt=receipt)
                persisted = json.loads(paths.readback.read_text())
                self.assertEqual(persisted["run_id"], RUN_ID)
                outcome.validate_readback(persisted, paths, "coder", fixture.plan.read_text())

    def test_receipt_parsers_and_triage_load_only_their_runtime_authority(self) -> None:
        poison = self.fixture.root / "import-poison"
        sentinel = poison / "executed"
        body = f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('foreign code')\n"
        write(poison, "scripts/__init__.py", body)
        write(poison, "scripts/contract_authority_context.py", body)
        write(poison, "contract_authority_context.py", body)
        program = """
import importlib.util, pathlib, sys, types
path, poison, forged = sys.argv[1:]
sys.path.insert(0, poison)
if forged == '1':
    module = types.ModuleType('contract_authority_context')
    module.__file__ = str(pathlib.Path(poison) / 'contract_authority_context.py')
    sys.modules[module.__name__] = module
try:
    spec = importlib.util.spec_from_file_location('receipt_probe', path)
    consumer = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = consumer
    spec.loader.exec_module(consumer)
    authority = consumer._authority_module()
except ImportError:
    if forged != '1':
        raise
else:
    assert forged == '0', 'foreign authority was accepted'
    assert pathlib.Path(authority.__file__).resolve() == pathlib.Path(path).with_name('contract_authority_context.py')
"""
        for filename in ("codex_session_context.py", "planveyor_trace_extractor.py",
                         "role_outcome_receipt.py", "followups_triage.py"):
            for forged in ("0", "1"):
                with self.subTest(filename=filename, forged=forged):
                    result = subprocess.run(
                        [sys.executable, "-B", "-c", program,
                         str(self.fixture.runtime_root / "scripts" / filename), str(poison), forged],
                        cwd=poison, env=self.fixture.environment(), text=True,
                        capture_output=True, check=False, timeout=20,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertFalse(sentinel.exists())


if __name__ == "__main__":
    unittest.main()

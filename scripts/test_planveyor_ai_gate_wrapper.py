#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

try:
    from scripts.test_support.process_contract_fixtures import run_zsh_fixture
    from scripts.test_contract_authority_support import AuthorityFixture, commit_all, git, write
except ModuleNotFoundError:
    from test_support.process_contract_fixtures import run_zsh_fixture
    from test_contract_authority_support import AuthorityFixture, commit_all, git, write


REPO_ROOT = Path(__file__).resolve().parent.parent


class PlanveyorAIGateWrapperTests(unittest.TestCase):
    def _run(self, command: str) -> subprocess.CompletedProcess[str]:
        return run_zsh_fixture(
            f"source scripts/planveyor.zsh && {command}",
            cwd=REPO_ROOT,
            path=os.environ.get("PATH", os.defpath),
            pybin=sys.executable,
            fixture_env={"PLANVEYOR_ROOT": str(REPO_ROOT)},
            capture_output=True,
            check=False,
        )

    def test_help_lists_ai_gate_commands(self) -> None:
        result = self._run("planveyor_help --all")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("planveyor_ai_gate", result.stdout)
        self.assertIn("planveyor_ai_gate_smoke", result.stdout)

    def test_smoke_writes_only_explicit_receipt_path(self) -> None:
        before = {
            path.resolve()
            for path in (REPO_ROOT / "docs" / "reviews").glob("*_ai_gate_*.json")
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            receipt_path = Path(tmpdir) / "ai_gate_smoke.json"
            result = self._run(
                f"planveyor_ai_gate_smoke --receipt-path {shlex.quote(str(receipt_path))}"
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(receipt_path.exists())
            self.assertIn(str(receipt_path), result.stdout)

            payload = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["verdict"]["status"], "PASS")
            self.assertEqual(payload["detection"]["status"], "CONFIRMED")
            self.assertEqual(payload["range"], "HEAD~1..HEAD")
            self.assertNotEqual(payload["project_root"], str(REPO_ROOT))

        after = {
            path.resolve()
            for path in (REPO_ROOT / "docs" / "reviews").glob("*_ai_gate_*.json")
        }
        self.assertEqual(after, before)


class AIGateSmokeFacadeProjectRootTests(unittest.TestCase):
    """A relative smoke receipt path belongs to the selected project."""

    def test_public_smoke_writes_relative_receipt_under_project(self) -> None:
        with AuthorityFixture(identity="planveyor") as fixture:
            entry = write(
                fixture.runtime_root,
                "bin/planveyor",
                (REPO_ROOT / "bin" / "planveyor").read_bytes(),
                executable=True,
            )
            runtime_commit = commit_all(fixture.runtime_root, "public AI gate smoke facade")
            target = fixture.target_root
            environment = fixture.environment()
            state_root = fixture.root / "state"
            state_root.mkdir()
            environment["PLANVEYOR_STATE_ROOT"] = str(state_root)

            result = subprocess.run(
                [
                    str(entry),
                    "--project",
                    str(target),
                    "planveyor_ai_gate_smoke",
                    "--receipt-path",
                    ".tmp/ai_gate_smoke.json",
                ],
                cwd=target,
                env=environment,
                stdin=subprocess.DEVNULL,
                text=True,
                capture_output=True,
                check=False,
                timeout=120,
            )
            receipt = target / ".tmp/ai_gate_smoke.json"
            payload = json.loads(receipt.read_text(encoding="utf-8")) if receipt.is_file() else None
            runtime_status = git(fixture.runtime_root, "status", "--short", "--untracked-files=all")
            runtime_head = git(fixture.runtime_root, "rev-parse", "HEAD")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIsNotNone(payload, result.stdout + result.stderr)
        self.assertEqual(payload["verdict"]["status"], "PASS")
        self.assertEqual(runtime_status, "")
        self.assertEqual(runtime_head, runtime_commit)


if __name__ == "__main__":
    unittest.main()

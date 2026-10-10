#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.test_contract_authority_support import AuthorityFixture, commit_all, git, write


class LedgerLintFacadeProjectRootTests(unittest.TestCase):
    """The retired facade rejects; explicit historical ledger reads remain available."""

    def test_retired_route_and_explicit_historical_reader(self) -> None:
        with AuthorityFixture(identity="planveyor") as fixture:
            entry = write(
                fixture.runtime_root,
                "bin/planveyor",
                (REPO_ROOT / "bin" / "planveyor").read_bytes(),
                executable=True,
            )
            runtime_commit = commit_all(fixture.runtime_root, "public ledger lint facade")
            target = fixture.target_root
            write(
                target,
                "docs/continuity/fixture_ledger.md",
                "# Fixture ledger\n\n**Status:** Done\n",
            )
            commit_all(target, "target ledger with a plan-only status line")
            environment = fixture.environment()
            state_root = fixture.root / "state"
            state_root.mkdir()
            environment["PLANVEYOR_STATE_ROOT"] = str(state_root)

            result = subprocess.run(
                [str(entry), "--project", str(target), "planveyor_ledger_lint_all"],
                cwd=target,
                env=environment,
                stdin=subprocess.DEVNULL,
                text=True,
                capture_output=True,
                check=False,
                timeout=120,
            )
            historical = subprocess.run(
                [sys.executable, "-B", str(REPO_ROOT / "scripts/ledger_lint.py"), "docs/continuity/fixture_ledger.md"],
                cwd=target, env=environment, text=True, capture_output=True, check=False,
            )
            runtime_status = git(fixture.runtime_root, "status", "--short", "--untracked-files=all")
            runtime_head = git(fixture.runtime_root, "rev-parse", "HEAD")

        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0, output)
        self.assertIn("planveyor_ledger_lint_all", result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(historical.returncode, 1, historical.stderr)
        self.assertIn("ERROR: docs/continuity/fixture_ledger.md:3:", historical.stdout)
        self.assertNotIn("no ledger files found", output)
        self.assertEqual(runtime_status, "")
        self.assertEqual(runtime_head, runtime_commit)


if __name__ == "__main__":
    unittest.main()

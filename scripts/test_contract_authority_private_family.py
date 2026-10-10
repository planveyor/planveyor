#!/usr/bin/env python3
"""Regression coverage for the retired private-family bridge command."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
import unittest


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from test_contract_authority_support import AuthorityFixture


class RetiredPrivateFamilyTests(unittest.TestCase):
    def test_bridge_no_longer_registers_the_retired_private_shell_family(self) -> None:
        with AuthorityFixture() as fixture:
            bootstrap = (fixture.runtime_root / "scripts" / "contract_authority_bootstrap.py").read_text(
                encoding="utf-8"
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-B",
                    "-c",
                    bootstrap,
                    str(fixture.runtime_root / "scripts" / "contract_authority_bridge.py"),
                    "private-shell-family",
                    "--runtime-pin-summary",
                    "{}",
                    "--family",
                    "provider",
                ],
                cwd=fixture.target_root,
                env=fixture.environment(),
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
            bridge_text = (fixture.runtime_root / "scripts" / "contract_authority_bridge.py").read_text(
                encoding="utf-8"
            )
            loader_text = (fixture.runtime_root / "scripts" / "contract_authority_shell_loader.zsh").read_text(
                encoding="utf-8"
            )

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertIn("invalid choice", result.stderr)
        self.assertNotIn("private-shell-family", bridge_text)
        self.assertNotIn("_planveyor_caller_private_family_buffer", loader_text)


if __name__ == "__main__":
    unittest.main()

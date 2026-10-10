#!/usr/bin/env python3
"""Keep the authority matrix CLI's explicit policy-input requirement."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import contract_authority_matrix_check as c1


class C1CliDispositionTests(unittest.TestCase):
    def test_rules_path_is_explicit_and_required(self) -> None:
        with self.assertRaises(c1.UsageError):
            c1.parser().parse_args(
                [
                    "emit",
                    "--source-root",
                    "/tmp/source",
                    "--source-commit",
                    "a" * 40,
                    "--source-tree",
                    "b" * 40,
                    "--target-root",
                    "/tmp/target",
                    "--target-commit",
                    "c" * 40,
                    "--target-tree",
                    "d" * 40,
                ]
            )


if __name__ == "__main__":
    unittest.main()

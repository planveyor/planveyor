#!/usr/bin/env python3
"""Regression tests for scripts/satd_scan.py."""

from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import satd_scan


DIFF_SAMPLE = """diff --git a/app/service.py b/app/service.py
index 1111111..2222222 100644
--- a/app/service.py
+++ b/app/service.py
@@ -10,1 +10,1 @@ def run():
-    # TODO relax retry window
+    # TODO tighten retry window
@@ -20,0 +21,2 @@ def run():
+    # broken fallback, временно оставляем
+    return value
@@ -40,1 +40,0 @@ def run():
-    # FIXME remove legacy path
diff --git a/tests/test_service.py b/tests/test_service.py
index 3333333..4444444 100644
--- a/tests/test_service.py
+++ b/tests/test_service.py
@@ -1,0 +1,2 @@
+# FIXME flaky fixture
+assert True
"""

DELETED_FILE_SAMPLE = """diff --git a/docs/legacy.py b/docs/legacy.py
deleted file mode 100644
index 5555555..0000000 100644
--- a/docs/legacy.py
+++ /dev/null
@@ -3,1 +0,0 @@
-# TODO remove legacy helper
"""


class SatdScanTest(unittest.TestCase):
    def test_parse_diff_text_collects_candidates(self) -> None:
        candidates = satd_scan.parse_diff_text(DIFF_SAMPLE)
        self.assertEqual(len(candidates), 4)
        first = candidates[0]
        self.assertEqual(first.file, "app/service.py")
        self.assertEqual(first.line, 10)
        self.assertEqual(first.lifecycle, "updated")
        self.assertEqual(first.old_line, 10)
        self.assertEqual(first.new_line, 10)
        self.assertEqual(first.keyword.upper(), "TODO")
        self.assertFalse(first.blocker_signal)
        self.assertFalse(first.test_context)
        self.assertEqual(first.old_snippet, "# TODO relax retry window")
        self.assertEqual(first.new_snippet, "# TODO tighten retry window")

        second = candidates[1]
        self.assertEqual(second.lifecycle, "created")
        self.assertTrue(second.blocker_signal)
        self.assertEqual(second.line, 21)
        self.assertIsNone(second.old_line)
        self.assertEqual(second.new_line, 21)

        third = candidates[2]
        self.assertEqual(third.lifecycle, "deleted")
        self.assertEqual(third.old_line, 40)
        self.assertIsNone(third.new_line)
        self.assertEqual(third.keyword.upper(), "FIXME")

        fourth = candidates[3]
        self.assertTrue(fourth.test_context)
        self.assertEqual(fourth.lifecycle, "created")
        self.assertEqual(fourth.keyword.upper(), "FIXME")

    def test_parse_diff_text_handles_deleted_file(self) -> None:
        candidates = satd_scan.parse_diff_text(DELETED_FILE_SAMPLE)
        self.assertEqual(len(candidates), 1)
        first = candidates[0]
        self.assertEqual(first.file, "docs/legacy.py")
        self.assertEqual(first.lifecycle, "deleted")
        self.assertEqual(first.old_line, 3)
        self.assertIsNone(first.new_line)

    def test_markdown_table_for_empty_candidates(self) -> None:
        self.assertEqual(
            satd_scan.to_markdown_table([]),
            "<!-- NO SATD CANDIDATES in range -->",
        )

    def test_markdown_table_renders_columns(self) -> None:
        rendered = satd_scan.to_markdown_table(satd_scan.parse_diff_text(DIFF_SAMPLE))
        self.assertIn(
            "| lifecycle | old anchor | new anchor | keyword | blocker? | test? | snippet | review |",
            rendered,
        )
        self.assertIn("| updated | `app/service.py:10` | `app/service.py:10` | TODO |", rendered)
        self.assertIn("| deleted | `app/service.py:40` |  | FIXME |", rendered)
        self.assertIn("UNCONFIRMED", rendered)


if __name__ == "__main__":
    unittest.main()

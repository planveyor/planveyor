#!/usr/bin/env python3
from __future__ import annotations

import unittest

import review_header_metadata as module


class ReviewHeaderMetadataTests(unittest.TestCase):
    def test_extracts_only_contiguous_post_h1_metadata(self) -> None:
        lines = (
            "# Review",
            "",
            "**Date:** 2026-07-13 03:00 MSK",
            "**Target:** BUNDLE=current",
            "**Status:** ✅ OK",
            "",
            "Summary body.",
            "**Target:** BUNDLE=body",
            "**Status:** ❌ S1 blocker(ы)",
        )

        self.assertEqual(
            module.header_values(lines, "target"),
            [(4, "BUNDLE=current")],
        )
        self.assertEqual(module.singleton_header_value(lines, "status"), ("✅ OK", 5))

    def test_requires_column_zero_h1_and_fields(self) -> None:
        self.assertEqual(
            module.extract_header_fields(("  # Review", "**Status:** ✅ OK")),
            [],
        )
        self.assertEqual(
            module.header_values(("# Review", "  **Status:** ✅ OK"), "status"),
            [],
        )

    def test_duplicate_singleton_is_ambiguous(self) -> None:
        lines = (
            "# Review",
            "**Target:** BUNDLE=first",
            "**Target:** BUNDLE=second",
            "**Status:** ✅ OK",
        )

        self.assertEqual(module.singleton_header_value(lines, "target"), (None, 3))
        self.assertEqual(
            module.duplicate_singleton_fields(lines, ("target", "status")),
            [(3, "target")],
        )

    def test_noncanonical_raw_label_is_not_singleton_proof(self) -> None:
        lines = ("# Review", "**Status :** ✅ OK")

        self.assertEqual(module.header_values(lines, "status"), [(2, "✅ OK")])
        self.assertEqual(module.singleton_header_value(lines, "status"), (None, 2))


if __name__ == "__main__":
    unittest.main()

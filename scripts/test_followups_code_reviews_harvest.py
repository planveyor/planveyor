#!/usr/bin/env python3
"""V2 code-review harvest emitter tests.

Coverage: V2 follow-ups ingress.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import followups_code_reviews_harvest
import followups_lint


class FollowupsCodeReviewsHarvestV2Tests(unittest.TestCase):
    def test_product_specific_titles_remain_source_intent(self) -> None:
        titles = (
            "DetailPageHelper inspect.signature hot path",
            "ProxyRequest duck typing",
            "query concatenation via urlencode",
            "Авто и техника",
            "local import transaction",
            "дублирующий import settings",
        )
        for title in titles:
            with self.subTest(title=title):
                item = followups_code_reviews_harvest.ReviewItem(
                    review_path="docs/code_reviews/example_line_by_line.md",
                    section="risk", num=1, title=title, line_no=4,
                )
                self.assertEqual(followups_code_reviews_harvest._canonical_summary(item), title)

    def test_harvest_emits_typed_v2_source_bound_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review = root / "docs/code_reviews/example_line_by_line.md"
            review.parent.mkdir(parents=True)
            review.write_text("# Review\n\n## Risk\n1) **Retry loop hides the original error**\n", encoding="utf-8")
            with mock.patch.object(followups_code_reviews_harvest, "REPO_ROOT", root):
                with mock.patch.object(
                    followups_code_reviews_harvest.followups_apply,
                    "apply_frozen_rows",
                    wraps=followups_code_reviews_harvest.followups_apply.apply_frozen_rows,
                ) as apply:
                    self.assertEqual(
                        followups_code_reviews_harvest.main(
                            ["--src", "docs/code_reviews/example_line_by_line.md", "--out", "docs/followups/review.md"]
                        ),
                        0,
                    )
                batch = apply.call_args.args[1]
                self.assertEqual(batch["schema_version"], "followups_generic_batch.v2")
                self.assertEqual(batch["source_kind"], "generic_harvest")
                self.assertEqual(batch["producer_id"], "code_reviews_harvest")
                self.assertTrue(apply.call_args.kwargs["mutate"])
            output = root / "docs/followups/review.md"
            parsed = followups_lint.parse_followup_file(output, root)
            self.assertEqual(followups_lint.classify_followups_schema_version(parsed)[0], "v2")
            self.assertEqual(followups_lint.lint_followup_files([parsed], root), [])
            row = parsed.items[0]
            self.assertEqual(row.source_ref, "docs/code_reviews/example_line_by_line.md#L4")
            self.assertTrue((row.item_id or "").startswith("review-"))
            self.assertEqual(row.status, "open")
            self.assertEqual(row.cluster, "process")

    def test_harvest_preserves_a_safe_existing_generic_cluster(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review = root / "docs/code_reviews/example_line_by_line.md"
            backlog = root / "docs/followups/quality_followups_master.md"
            review.parent.mkdir(parents=True)
            review.write_text(
                "# Review\n\n**Follow-ups backlog:** `docs/followups/quality_followups_master.md`\n\n"
                "## Risk\n1) **Existing generic route**\n",
                encoding="utf-8",
            )
            backlog.parent.mkdir(parents=True)
            backlog.write_text(
                "# Master\n\n## Follow-ups\n"
                "- P2 [ ] Existing generic route — cluster=quality — to=Owner — status=open "
                "— plan=null — why: Risk #1\n",
                encoding="utf-8",
            )
            with mock.patch.object(followups_code_reviews_harvest, "REPO_ROOT", root):
                self.assertEqual(
                    followups_code_reviews_harvest.main(
                        ["--src", "docs/code_reviews/example_line_by_line.md", "--out", "docs/followups/review.md"]
                    ),
                    0,
                )
            parsed = followups_lint.parse_followup_file(root / "docs/followups/review.md", root)
            self.assertEqual(parsed.items[0].cluster, "quality")

    def test_dry_run_keeps_the_code_review_carrier_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review = root / "docs/code_reviews/example_line_by_line.md"
            review.parent.mkdir(parents=True)
            review.write_text("# Review\n\n## Risk\n1) **Dry-run review**\n", encoding="utf-8")
            with mock.patch.object(followups_code_reviews_harvest, "REPO_ROOT", root):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(
                        followups_code_reviews_harvest.main(
                            [
                                "--src",
                                "docs/code_reviews/example_line_by_line.md",
                                "--out",
                                "docs/followups/review.md",
                                "--dry-run",
                            ]
                        ),
                        0,
                    )
            self.assertFalse((root / "docs/followups/review.md").exists())

    def test_public_harvest_blocks_a_duplicate_tuple_in_a_second_carrier_and_retries_owner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review = root / "docs/code_reviews/example_line_by_line.md"
            a_path = root / "docs/followups/a.md"
            b_path = root / "docs/followups/b.md"
            review.parent.mkdir(parents=True)
            review.write_text("# Review\n\n## Risk\n1) **Global owner finding**\n", encoding="utf-8")
            with mock.patch.object(followups_code_reviews_harvest, "REPO_ROOT", root):
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(
                        followups_code_reviews_harvest.main(
                            ["--src", "docs/code_reviews/example_line_by_line.md", "--out", "docs/followups/a.md"]
                        ),
                        0,
                    )
                    before_a = a_path.read_bytes()
                    self.assertEqual(
                        followups_code_reviews_harvest.main(
                            ["--src", "docs/code_reviews/example_line_by_line.md", "--out", "docs/followups/b.md"]
                        ),
                        2,
                    )
                    self.assertEqual(
                        followups_code_reviews_harvest.main(
                            ["--src", "docs/code_reviews/example_line_by_line.md", "--out", "docs/followups/a.md"]
                        ),
                        0,
                    )
            self.assertEqual(a_path.read_bytes(), before_a)
            self.assertFalse(b_path.exists())
            parsed = followups_lint.parse_followup_file(a_path, root)
            self.assertEqual(followups_lint.lint_followup_files([parsed], root), [])

    def test_source_mutation_between_discovery_and_freeze_blocks_without_a_carrier_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review = root / "docs/code_reviews/example_line_by_line.md"
            output = root / "docs/followups/review.md"
            review.parent.mkdir(parents=True)
            original_text = "# Review\n\n## Risk\n1) **Original review finding**\n"
            replacement_text = "# Review\n\n## Risk\n1) **Replaced review finding**\n"
            review.write_text(original_text, encoding="utf-8")
            frozen_batches: list[dict[str, object]] = []
            original_generic_batch = followups_code_reviews_harvest._generic_batch

            def mutate_source_before_freeze(*args: object, **kwargs: object) -> dict[str, object]:
                review.write_text(replacement_text, encoding="utf-8")
                batch = original_generic_batch(*args, **kwargs)
                frozen_batches.append(batch)
                return batch

            with mock.patch.object(followups_code_reviews_harvest, "REPO_ROOT", root):
                with mock.patch.object(
                    followups_code_reviews_harvest,
                    "_generic_batch",
                    side_effect=mutate_source_before_freeze,
                ):
                    stderr = io.StringIO()
                    with contextlib.redirect_stderr(stderr):
                        self.assertEqual(
                            followups_code_reviews_harvest.main(
                                [
                                    "--src",
                                    "docs/code_reviews/example_line_by_line.md",
                                    "--out",
                                    "docs/followups/review.md",
                                ]
                            ),
                            2,
                        )

            self.assertFalse(output.exists())
            self.assertIn("generic source object changed after discovery", stderr.getvalue())
            self.assertEqual(len(frozen_batches), 1)
            batch = frozen_batches[0]
            self.assertEqual(
                batch["source_objects"],
                [
                    {
                        "source_path": "docs/code_reviews/example_line_by_line.md",
                        "source_sha256": hashlib.sha256(original_text.encode("utf-8")).hexdigest(),
                        "anchors": ["L4"],
                    }
                ],
            )
            self.assertIn("Original review finding", str(batch["proposed_rows"]))
            self.assertNotIn("Replaced review finding", str(batch["proposed_rows"]))

    def test_public_harvest_rejects_foreign_explicit_v2_integrity_blocker_without_carrier_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            review = root / "docs/code_reviews/example.md"
            output = root / "docs/followups/review.md"
            foreign = root / "docs/followups/foreign.md"
            review.parent.mkdir(parents=True)
            review.write_text("# Review\n\n## Risk\n1) **Blocked review finding**\n", encoding="utf-8")
            malformed = "# foreign\n\n**Schema version:** followups.v2\n**Schema version:** followups.v2\n\n## Follow-ups\n"
            foreign.parent.mkdir(parents=True, exist_ok=True)
            foreign.write_text(malformed, encoding="utf-8")

            with mock.patch.object(followups_code_reviews_harvest, "REPO_ROOT", root):
                with contextlib.redirect_stderr(io.StringIO()):
                    result = followups_code_reviews_harvest.main(
                        ["--src", "docs/code_reviews/example.md", "--out", "docs/followups/review.md"]
                    )

            self.assertEqual(result, 2)
            self.assertFalse(output.exists())
            self.assertEqual(foreign.read_text(encoding="utf-8"), malformed)


if __name__ == "__main__":
    unittest.main()

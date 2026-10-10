#!/usr/bin/env python3
"""Regression tests for scripts/followups_index_rebuild.py."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import followups_index_rebuild


class FollowupsIndexRebuildTest(unittest.TestCase):
    def _write(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _write_check_fixture(self, root: Path) -> Path:
        index_path = root / "docs" / "followups" / "index.md"
        self._write(
            index_path,
            "# Follow-ups — index\n\n| File | Topic | Notes |\n| --- | --- | --- |\n"
            "| `docs/followups/process_followups_master.md` | Process | active |\n",
        )
        self._write(
            root / "docs" / "followups" / "process_followups_master.md",
            "# Follow-ups backlog — Process\n\n**Status:** Draft\n\n## Follow-ups (backlog)\n"
            "- P1 [ ] Active item — cluster=process — tags=docs — to=Architect — status=open — plan=null — why: active\n",
        )
        return index_path

    def test_rebuild_preserves_manual_index_and_writes_auto_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            self._write(
                root / "docs" / "followups" / "index.md",
                "# Follow-ups — index\n\n| File | Topic | Notes |\n| --- | --- | --- |\n"
                "| `docs/followups/process_followups_master.md` | Process | active |\n",
            )
            self._write(
                root / "docs" / "followups" / "process_followups_master.md",
                "# Follow-ups backlog — Process\n\n**Status:** Draft\n\n## Follow-ups (backlog)\n"
                "- P1 [ ] Master item — cluster=process — tags=docs — to=Architect — status=open — plan=null — why: master proof\n"
                "- P2 [x] Closed item — cluster=process — tags=docs — to=Architect — status=handled — plan=null — why: done\n",
            )
            self._write(
                root / "docs" / "followups" / "260401_1200_followups_range_deadbee_feed123.md",
                "# Follow-ups backlog — Range\n\n**Status:** Draft\n\n## Follow-ups (backlog)\n"
                "- P0 [ ] Standalone item — cluster=process — tags=runtime — to=Owner — status=UNCONFIRMED — plan=null — why: standalone proof\n",
            )
            self._write(
                root / "docs" / "followups" / "260401_1300_followups_range_deadbee_feed124.md",
                "# Follow-ups backlog — Imported\n\n**Status:** Draft\n"
                "**Imported into:** `docs/followups/process_followups_master.md`\n\n## Follow-ups (backlog)\n"
                "- P1 [ ] Imported item — cluster=process — tags=docs — to=Planner — status=open — plan=null — why: should stay hidden\n",
            )
            self._write(
                root / "docs" / "followups" / "260401_1400_followups_range_deadbee_feed125.md",
                "# Follow-ups backlog — Standalone N/A\n\n**Status:** ✅ Done\n"
                "**Imported into:** `N/A (why=standalone receipt; no master import row created)`\n\n## Follow-ups (backlog)\n"
                "- P2 [ ] N/A open item — cluster=process — tags=docs — to=Planner — status=open — plan=null — why: must stay visible\n",
            )

            followups_index_rebuild.rebuild_index(root, stamp="2026-04-16 23:44 MSK")
            text = (root / "docs" / "followups" / "index.md").read_text(encoding="utf-8")

            self.assertIn("| `docs/followups/process_followups_master.md` | Process | active |", text)
            self.assertIn("## Open follow-ups summary (auto)", text)
            self.assertIn(followups_index_rebuild.BANNER_LINE, text)
            self.assertIn("`docs/followups/process_followups_master.md:6`", text)
            self.assertIn("Master item", text)
            self.assertIn("Standalone item", text)
            self.assertIn("N/A open item", text)
            self.assertNotIn("Imported item", text)
            self.assertNotIn("Closed item", text)

    def test_rebuild_is_idempotent_with_existing_markers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            self._write(
                root / "docs" / "followups" / "index.md",
                "# Follow-ups — index\n\n"
                "<!-- AUTO-OPEN-SUMMARY:START -->\nold\n<!-- AUTO-OPEN-SUMMARY:END -->\n",
            )
            self._write(
                root / "docs" / "followups" / "process_followups_master.md",
                "# Follow-ups backlog — Process\n\n**Status:** Draft\n\n## Follow-ups (backlog)\n"
                "- P1 [ ] Active item — cluster=process — tags=docs — to=Architect — status=open — plan=null — why: active\n",
            )

            first = followups_index_rebuild.rebuild_index(
                root, stamp="2026-04-16 23:44 MSK"
            ).read_text(encoding="utf-8")
            second = followups_index_rebuild.rebuild_index(
                root, stamp="2026-04-16 23:44 MSK"
            ).read_text(encoding="utf-8")
            self.assertEqual(first, second)
            self.assertEqual(first.count("<!-- AUTO-OPEN-SUMMARY:START -->"), 1)
            self.assertEqual(first.count("<!-- AUTO-OPEN-SUMMARY:END -->"), 1)

    def test_v2_summary_uses_source_tuple_not_mutable_carrier_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            self._write(root / "docs/followups/index.md", "# Follow-ups — index\n")
            self._write(
                root / "docs/followups/process_followups_master.md",
                "# Follow-ups\n\n**Schema version:** followups.v2\n\n## Follow-ups\n"
                "- P1 [ ] Stable tuple — cluster=process — to=coder — status=open — plan=null "
                "— item_id=index-001 — source_ref=docs/plans/260811_0050_terminal.md#B1 "
                "— disposition_kind=null — disposition_ref=null — disposition_commit_oid=null — reason=null — why: index identity\n",
            )
            followups_index_rebuild.rebuild_index(root, stamp="2026-08-11 22:00 MSK")
            text = (root / "docs/followups/index.md").read_text(encoding="utf-8")
            result = followups_index_rebuild.check_index(root)
            self.assertIn("`docs/plans/260811_0050_terminal.md#B1#index-001`", text)
            self.assertNotIn("process_followups_master.md:5` | Stable tuple", text)
            self.assertEqual(result.expected_rows, 1)
            self.assertEqual(result.live_rows, 1)

    def test_bound_renderer_uses_only_supplied_source_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            index_path = self._write_check_fixture(root)
            source_path = "docs/followups/process_followups_master.md"
            source_bytes = {source_path: (root / source_path).read_bytes()}
            manifest = followups_index_rebuild.authoritative_followups_manifest(source_bytes)
            lifecycle = followups_index_rebuild.promoted_plan_lifecycle_manifest(
                root,
                source_bytes,
                manifest,
            )
            index_before = index_path.read_bytes()

            # A later ambient edit must not be silently reread by the pure
            # candidate renderer.
            (root / source_path).write_text(
                "# Follow-ups backlog — Process\n\n**Status:** Draft\n\n## Follow-ups (backlog)\n"
                "- P0 [ ] Ambient replacement — cluster=process — tags=docs — to=Owner — status=open — plan=null — why: must not leak\n",
                encoding="utf-8",
            )
            rendered = followups_index_rebuild.render_bound_index(
                root,
                source_bytes,
                manifest,
                index_before,
                promoted_plan_lifecycle=lifecycle,
                stamp="2026-08-31 20:00 MSK",
            )

        text = rendered.index_bytes.decode("utf-8")
        self.assertIn("Active item", text)
        self.assertNotIn("Ambient replacement", text)
        self.assertEqual(rendered.expected_rows, 1)

    def test_bound_renderer_rejects_unsafe_ignored_and_mismatched_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            index_path = self._write_check_fixture(root)
            source_path = "docs/followups/process_followups_master.md"
            source_bytes = {source_path: (root / source_path).read_bytes()}
            manifest = followups_index_rebuild.authoritative_followups_manifest(source_bytes)

            for source_map in (
                {"docs/followups/index.md": b"generated bytes are not raw truth\n"},
                {"../escape.md": b"unsafe\n"},
            ):
                with self.subTest(source_map=source_map), self.assertRaises(followups_index_rebuild.BoundIndexInputError):
                    followups_index_rebuild.authoritative_followups_manifest(source_map)

            stale_manifest = {
                source_path: {"sha256": "0" * 64, "st_size": len(source_bytes[source_path])},
            }
            with self.assertRaises(followups_index_rebuild.BoundIndexInputError):
                followups_index_rebuild.render_bound_index(
                    root,
                    source_bytes,
                    stale_manifest,
                    index_path.read_bytes(),
                    promoted_plan_lifecycle={},
                    stamp="2026-08-31 20:00 MSK",
                )

    def test_bound_renderer_authenticates_promoted_plan_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            index_path = self._write_check_fixture(root)
            target = root / "docs/plans/260831_0001_promoted_target.md"
            self._write(target, "# promoted target\n\n**Status:** In progress\n")
            source_path = "docs/followups/process_followups_master.md"
            self._write(
                root / source_path,
                "# Follow-ups backlog — Process\n\n**Status:** Draft\n\n## Follow-ups (backlog)\n"
                "- P1 [ ] Promoted visibility — cluster=process — tags=docs — to=Architect — status=promoted "
                "— plan=docs/plans/260831_0001_promoted_target.md — why: lifecycle proof\n",
            )
            source_bytes = {source_path: (root / source_path).read_bytes()}
            manifest = followups_index_rebuild.authoritative_followups_manifest(source_bytes)
            lifecycle_before = followups_index_rebuild.promoted_plan_lifecycle_manifest(
                root,
                source_bytes,
                manifest,
            )
            first = followups_index_rebuild.render_bound_index(
                root,
                source_bytes,
                manifest,
                index_path.read_bytes(),
                promoted_plan_lifecycle=lifecycle_before,
                stamp="2026-08-31 22:30 MSK",
            )

            self._write(target, "# promoted target\n\n**Status:** Done\n")
            same_bound_input = followups_index_rebuild.render_bound_index(
                root,
                source_bytes,
                manifest,
                index_path.read_bytes(),
                promoted_plan_lifecycle=lifecycle_before,
                stamp="2026-08-31 22:30 MSK",
            )
            lifecycle_after = followups_index_rebuild.promoted_plan_lifecycle_manifest(
                root,
                source_bytes,
                manifest,
            )
            second = followups_index_rebuild.render_bound_index(
                root,
                source_bytes,
                manifest,
                index_path.read_bytes(),
                promoted_plan_lifecycle=lifecycle_after,
                stamp="2026-08-31 22:30 MSK",
            )

        self.assertEqual(first.index_bytes, same_bound_input.index_bytes)
        self.assertEqual(
            first.authoritative_followups_manifest_sha256,
            same_bound_input.authoritative_followups_manifest_sha256,
        )
        self.assertNotEqual(first.index_bytes, second.index_bytes)
        self.assertNotEqual(
            first.authoritative_followups_manifest_sha256,
            second.authoritative_followups_manifest_sha256,
        )
        self.assertEqual(first.expected_rows, 1)
        self.assertEqual(second.expected_rows, 0)

    def test_check_mode_passes_without_writing_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            index_path = self._write_check_fixture(root)
            followups_index_rebuild.rebuild_index(root, stamp="2026-04-16 23:44 MSK")
            before_text = index_path.read_text(encoding="utf-8")
            before_mtime = index_path.stat().st_mtime_ns

            result = followups_index_rebuild.check_index(root)

            self.assertTrue(result.ok)
            self.assertEqual(result.expected_rows, 1)
            self.assertEqual(result.live_rows, 1)
            self.assertEqual(index_path.read_text(encoding="utf-8"), before_text)
            self.assertEqual(index_path.stat().st_mtime_ns, before_mtime)

    def test_check_mode_allows_timestamp_only_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            index_path = self._write_check_fixture(root)
            followups_index_rebuild.rebuild_index(root, stamp="2026-04-16 23:44 MSK")
            text = index_path.read_text(encoding="utf-8")
            index_path.write_text(
                text.replace("2026-04-16 23:44 MSK", "2026-04-17 00:05 MSK"),
                encoding="utf-8",
            )

            result = followups_index_rebuild.check_index(root)

            self.assertTrue(result.ok)
            self.assertTrue(result.timestamp_ignored)

    def test_check_mode_fails_for_stale_generated_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            self._write_check_fixture(root)
            followups_index_rebuild.rebuild_index(root, stamp="2026-04-16 23:44 MSK")
            self._write(
                root / "docs" / "followups" / "process_followups_master.md",
                "# Follow-ups backlog — Process\n\n**Status:** Draft\n\n## Follow-ups (backlog)\n"
                "- P1 [ ] Active item — cluster=process — tags=docs — to=Architect — status=open — plan=null — why: active\n"
                "- P2 [ ] Later item — cluster=process — tags=docs — to=Reviewer — status=open — plan=null — why: stale proof\n",
            )

            result = followups_index_rebuild.check_index(root)

            self.assertFalse(result.ok)
            self.assertIn("generated_content_mismatch", result.issues)
            self.assertEqual(result.expected_rows, 2)
            self.assertEqual(result.live_rows, 1)
            self.assertTrue(any("Later item" in line for line in result.diff))

    def test_check_mode_fails_for_hand_edited_generated_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            index_path = self._write_check_fixture(root)
            followups_index_rebuild.rebuild_index(root, stamp="2026-04-16 23:44 MSK")
            text = index_path.read_text(encoding="utf-8")
            index_path.write_text(text.replace("Active item", "Edited item"), encoding="utf-8")

            result = followups_index_rebuild.check_index(root)

            self.assertFalse(result.ok)
            self.assertIn("generated_content_mismatch", result.issues)
            self.assertEqual(result.expected_rows, 1)
            self.assertEqual(result.live_rows, 1)
            self.assertTrue(any("Edited item" in line for line in result.diff))

    def test_check_mode_fails_for_missing_banner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            index_path = self._write_check_fixture(root)
            followups_index_rebuild.rebuild_index(root, stamp="2026-04-16 23:44 MSK")
            text = index_path.read_text(encoding="utf-8")
            index_path.write_text(
                text.replace(followups_index_rebuild.BANNER_LINE + "\n", ""),
                encoding="utf-8",
            )

            result = followups_index_rebuild.check_index(root)

            self.assertFalse(result.ok)
            self.assertIn("missing_banner_line", result.issues)
            self.assertIn("generated_content_mismatch", result.issues)

    def test_check_mode_fails_for_missing_generated_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            self._write_check_fixture(root)

            result = followups_index_rebuild.check_index(root)

            self.assertFalse(result.ok)
            self.assertEqual(result.issues, ("missing_generated_block",))
            self.assertIsNone(result.live_rows)

    def test_check_mode_fails_for_malformed_or_duplicate_generated_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            index_path = self._write_check_fixture(root)
            followups_index_rebuild.rebuild_index(root, stamp="2026-04-16 23:44 MSK")
            text = index_path.read_text(encoding="utf-8")

            index_path.write_text(
                "# Follow-ups — index\n\n"
                f"{followups_index_rebuild.AUTO_START}{followups_index_rebuild.AUTO_END}\n",
                encoding="utf-8",
            )
            malformed = followups_index_rebuild.check_index(root)
            self.assertFalse(malformed.ok)
            self.assertEqual(malformed.issues, ("malformed_generated_block",))

            index_path.write_text(text.rstrip() + "\n" + text[text.index("<!-- AUTO-OPEN-SUMMARY:START -->") :], encoding="utf-8")
            duplicate = followups_index_rebuild.check_index(root)
            self.assertFalse(duplicate.ok)
            self.assertEqual(duplicate.issues, ("multiple_generated_blocks",))

    def test_check_json_reports_status_counts_and_no_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            index_path = self._write_check_fixture(root)
            followups_index_rebuild.rebuild_index(root, stamp="2026-04-16 23:44 MSK")
            before_text = index_path.read_text(encoding="utf-8")
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                exit_code = followups_index_rebuild.main(
                    ["--project-root", str(root), "--check", "--json"]
                )

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["status"], "ok")
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["expected_rows"], 1)
            self.assertEqual(payload["live_rows"], 1)
            self.assertTrue(payload["timestamp_ignored"])
            self.assertFalse(payload["would_write"])
            self.assertEqual(index_path.read_text(encoding="utf-8"), before_text)

    def test_check_json_reports_stale_rows_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            index_path = self._write_check_fixture(root)
            followups_index_rebuild.rebuild_index(root, stamp="2026-04-16 23:44 MSK")
            before_text = index_path.read_text(encoding="utf-8")
            self._write(
                root / "docs" / "followups" / "process_followups_master.md",
                "# Follow-ups backlog — Process\n\n**Status:** Draft\n\n## Follow-ups (backlog)\n"
                "- P1 [ ] Active item — cluster=process — tags=docs — to=Architect — status=open — plan=null — why: active\n"
                "- P2 [ ] Later item — cluster=process — tags=docs — to=Reviewer — status=open — plan=null — why: stale proof\n",
            )
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                exit_code = followups_index_rebuild.main(
                    ["--project-root", str(root), "--check", "--json"]
                )

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 1)
            self.assertEqual(payload["status"], "failed")
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["expected_rows"], 2)
            self.assertEqual(payload["live_rows"], 1)
            self.assertIn("generated_content_mismatch", payload["issues"])
            self.assertFalse(payload["would_write"])
            self.assertTrue(any("Later item" in line for line in payload["diff"]))
            self.assertEqual(index_path.read_text(encoding="utf-8"), before_text)


if __name__ == "__main__":
    unittest.main()

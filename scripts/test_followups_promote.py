#!/usr/bin/env python3
"""Focused V2 prepare / Commit-A / finalize promotion tests.

Coverage: V2 follow-ups ingress.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import followups_capture
import followups_lint
import followups_promote


class FollowupsPromoteV2Tests(unittest.TestCase):
    source_plan = "docs/plans/fixture_terminal_source.md"
    followup_path = "docs/followups/process_followups_master.md"
    item_id = "promote-001"
    target_plan = "docs/plans/260811_0001_promoted.md"

    def _git(self, root: Path, *args: str) -> str:
        result = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def _row(self, *, status: str = "open", commit: str | None = None) -> dict[str, object]:
        promoted = status == "promoted"
        return {
            "priority": "P1",
            "summary": "V2 promotion path",
            "cluster": "process",
            "to": "architect",
            "status": status,
            "plan": self.target_plan if promoted else None,
            "why": "prove prepare and finalization are separated",
            "tags": ["v2"],
            "item_id": self.item_id,
            "source_ref": self.source_plan,
            "disposition_kind": "promoted_plan" if promoted else None,
            "disposition_ref": self.target_plan if promoted else None,
            "disposition_commit_oid": commit if promoted else None,
            "reason": "Commit A contains source-bound artifacts" if promoted else None,
        }

    def _root(self) -> tuple[tempfile.TemporaryDirectory[str], Path, str, str]:
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        self._git(root, "init", "-q")
        self._git(root, "config", "user.email", 'test' + '@' + 'example' + '.' + 'invalid')
        self._git(root, "config", "user.name", "Test")
        plan = root / self.source_plan
        plan.parent.mkdir(parents=True)
        plan.write_text(
            "# terminal source\n\n**Status:** Done\n**Schema version:** plan.v2\n",
            encoding="utf-8",
        )
        self._git(root, "add", self.source_plan)
        self._git(root, "commit", "-qm", "terminal source")
        terminal_commit = self._git(root, "rev-parse", "HEAD")
        terminal_blob = self._git(root, "rev-parse", f"HEAD:{self.source_plan}")

        followup = root / self.followup_path
        followup.parent.mkdir(parents=True)
        followup.write_text(
            "# Follow-ups\n\n**Schema version:** followups.v2\n\n## Follow-ups (backlog)\n"
            + followups_lint.render_v2_row(self._row())
            + "\n",
            encoding="utf-8",
        )
        return temp, root, terminal_commit, terminal_blob

    def _manifest(self, root: Path, terminal_commit: str, terminal_blob: str, commit_a: str) -> dict[str, object]:
        open_row = self._row()
        promoted = self._row(status="promoted", commit=commit_a)
        snapshot, _ = followups_capture.snapshot_followups(root, include_bytes=True)
        tuple_key = f"{self.source_plan}\u0000{self.item_id}"
        return {
            "schema_version": "followups_capture_cycle.v2",
            "plan_ref": self.source_plan,
            "source_terminal_commit_oid": terminal_commit,
            "source_plan_blob_oid": terminal_blob,
            "baseline_followups_snapshot": snapshot,
            "declaration_roles": list(followups_capture.REQUIRED_ROLES),
            "expected_owned_tuples": [{"source_ref": self.source_plan, "item_id": self.item_id}],
            "tuple_owners": {tuple_key: "Reviewer"},
            "expected_current_row_digests": {tuple_key: followups_lint.v2_row_digest(open_row)},
            "expected_zero_reason": None,
            "proposed_rows": [
                {
                    "followup_path": self.followup_path,
                    "payload": promoted,
                    "row_digest": followups_lint.v2_row_digest(promoted),
                }
            ],
        }

    def test_prepare_keeps_open_row_then_finalize_cas_promotes_after_commit_a(self) -> None:
        temp, root, terminal_commit, terminal_blob = self._root()
        with temp:
            before = (root / self.followup_path).read_text(encoding="utf-8")
            result = followups_promote.main(
                [
                    "--project-root", str(root), "--file", self.followup_path,
                    "--item-id", self.item_id, "--plan-path", self.target_plan,
                    "--prepare-v2", "--apply", "--format", "json",
                ]
            )
            self.assertEqual(result, 0)
            self.assertEqual((root / self.followup_path).read_text(encoding="utf-8"), before)
            plan_text = (root / self.target_plan).read_text(encoding="utf-8")
            self.assertIn('"state": "n/a"', plan_text)
            self.assertIn("external row intentionally remains strict open", plan_text)
            self._git(root, "add", self.target_plan, "docs/code_drafts/260811_0001_promoted__code_draft.md")
            self._git(root, "commit", "-qm", "Commit A promotion artifacts")
            commit_a = self._git(root, "rev-parse", "HEAD")

            manifest_path = root / "frozen.json"
            manifest_path.write_text(
                json.dumps(self._manifest(root, terminal_commit, terminal_blob, commit_a)), encoding="utf-8"
            )
            with mock.patch.object(
                followups_promote.followups_apply,
                "apply_frozen_rows",
                wraps=followups_promote.followups_apply.apply_frozen_rows,
            ) as apply:
                result = followups_promote.main(
                    [
                        "--project-root", str(root), "--file", self.followup_path,
                        "--item-id", self.item_id, "--plan-path", self.target_plan,
                        "--finalize-v2", "--frozen-manifest", str(manifest_path),
                        "--commit-oid", commit_a, "--apply", "--format", "json",
                    ]
                )
            self.assertEqual(apply.call_count, 1)
            self.assertTrue(apply.call_args.kwargs["mutate"])
            self.assertEqual(result, 0)
            parsed = followups_lint.parse_followup_file(root / self.followup_path, root)
            self.assertEqual(parsed.items[0].status, "promoted")
            self.assertEqual(parsed.items[0].disposition_commit_oid, commit_a)

            # Byte-identical retry is idempotent rather than inventing another
            # promotion write or accepting a line-number based alias.
            self.assertEqual(
                followups_promote.main(
                    [
                        "--project-root", str(root), "--file", self.followup_path,
                        "--item-id", self.item_id, "--plan-path", self.target_plan,
                        "--finalize-v2", "--frozen-manifest", str(manifest_path),
                        "--commit-oid", commit_a, "--apply", "--format", "json",
                    ]
                ),
                0,
            )

    def test_finalize_rejects_bad_cas_before_writer(self) -> None:
        temp, root, terminal_commit, terminal_blob = self._root()
        with temp:
            (root / self.target_plan).write_text("# target\n", encoding="utf-8")
            self._git(root, "add", self.target_plan)
            self._git(root, "commit", "-qm", "Commit A")
            commit_a = self._git(root, "rev-parse", "HEAD")
            manifest = self._manifest(root, terminal_commit, terminal_blob, commit_a)
            key = f"{self.source_plan}\u0000{self.item_id}"
            manifest["expected_current_row_digests"] = {key: "0" * 64}
            manifest_path = root / "frozen.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            before = (root / self.followup_path).read_bytes()
            result = followups_promote.main(
                [
                    "--project-root", str(root), "--file", self.followup_path,
                    "--item-id", self.item_id, "--plan-path", self.target_plan,
                    "--finalize-v2", "--frozen-manifest", str(manifest_path),
                    "--commit-oid", commit_a, "--apply", "--format", "json",
                ]
            )
            self.assertEqual(result, 2)
            self.assertEqual((root / self.followup_path).read_bytes(), before)

    def test_prepare_blocks_foreign_explicit_v2_integrity_before_plan_or_draft_write(self) -> None:
        temp, root, _terminal_commit, _terminal_blob = self._root()
        with temp:
            source = root / self.followup_path
            before = source.read_bytes()
            foreign = root / "docs/followups/foreign.md"
            foreign.write_text(
                "# foreign\n\n**Schema version:** followups.v2\n**Schema version:** followups.v2\n\n## Follow-ups\n",
                encoding="utf-8",
            )
            result = followups_promote.main(
                [
                    "--project-root", str(root), "--file", self.followup_path,
                    "--item-id", self.item_id, "--plan-path", self.target_plan,
                    "--prepare-v2", "--apply", "--format", "json",
                ]
            )

            self.assertEqual(result, 2)
            self.assertEqual(source.read_bytes(), before)
            self.assertFalse((root / self.target_plan).exists())
            self.assertFalse((root / "docs/code_drafts/260811_0001_promoted__code_draft.md").exists())


if __name__ == "__main__":
    unittest.main()

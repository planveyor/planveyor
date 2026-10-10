#!/usr/bin/env python3
"""Regression tests for scripts/followups_triage.py."""

from __future__ import annotations

import os
import io
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import followups_triage
from test_support.process_contract_fixtures import run_zsh_fixture, temporary_git_root


class FollowupsTriageTest(unittest.TestCase):
    def _write(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _followup_bytes(self, root: Path) -> dict[str, bytes]:
        followups = root / "docs" / "followups"
        return {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted(followups.rglob("*"))
            if path.is_file()
        }

    def test_done_with_imported_na_is_not_fully_imported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            inbox = Path(tmp) / "docs" / "followups" / "260510_followups_range.md"
            self._write(
                inbox,
                "# Follow-ups backlog\n\n"
                "**Status:** ✅ Done\n"
                "**Imported into:** `N/A (why=standalone receipt; tracked in docs/followups/index.md)`\n\n"
                "## Follow-ups (backlog)\n"
                "- P2 [ ] Open row — cluster=process — to=Planner — status=open — plan=null — why: proof\n",
            )

            self.assertEqual(followups_triage._parse_imported_refs("**Imported into:** `N/A (why=standalone)`"), [])
            self.assertFalse(followups_triage._is_fully_imported_inbox(inbox))

    def test_done_with_real_import_ref_is_fully_imported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            inbox = Path(tmp) / "docs" / "followups" / "260510_followups_range.md"
            self._write(
                inbox,
                "# Follow-ups backlog\n\n"
                "**Status:** ✅ Done\n"
                "**Imported into:** `docs/followups/process_followups_master.md`\n\n"
                "## Follow-ups (backlog)\n"
                "- P2 [ ] Imported row — cluster=process — to=Planner — status=open — plan=null — why: proof\n",
            )

            self.assertEqual(
                followups_triage._parse_imported_refs(
                    "**Imported into:** `docs/followups/process_followups_master.md`"
                ),
                ["docs/followups/process_followups_master.md"],
            )
            self.assertTrue(followups_triage._is_fully_imported_inbox(inbox))

    def test_cluster_routing_uses_index_clusters_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            index = Path(tmp) / "docs" / "followups" / "index.md"
            self._write(
                index,
                "# Follow-ups — index\n\n"
                "| File | Topic | Notes |\n"
                "| --- | --- | --- |\n"
                "| `docs/followups/process_followups_master.md` | Process | active; clusters=process |\n",
            )

            self.assertEqual(
                followups_triage._load_cluster_routing(index),
                {"process": "docs/followups/process_followups_master.md"},
            )

    def test_explicit_file_mode_accepts_only_inbox_followups(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            inbox = root / "docs" / "followups" / "260510_followups_range.md"
            master = root / "docs" / "followups" / "process_followups_master.md"
            outside = root / "docs" / "plans" / "260510_plan.md"
            self._write(inbox, "# Follow-ups backlog\n")
            self._write(master, "# Follow-ups backlog — Process\n")
            self._write(outside, "# Plan\n")

            old_root = followups_triage.REPO_ROOT
            old_dir = followups_triage.FOLLOWUPS_DIR
            try:
                followups_triage.REPO_ROOT = root
                followups_triage.FOLLOWUPS_DIR = root / "docs" / "followups"

                self.assertEqual(followups_triage._collect_inbox_files_explicit([inbox.as_posix()]), [inbox])
                self.assertEqual(
                    followups_triage._collect_inbox_files_explicit(["docs/followups/260510_followups_range.md"]),
                    [inbox],
                )
                with self.assertRaises(ValueError):
                    followups_triage._collect_inbox_files_explicit(["docs/followups/process_followups_master.md"])
                with self.assertRaises(ValueError):
                    followups_triage._collect_inbox_files_explicit(["docs/plans/260510_plan.md"])
            finally:
                followups_triage.REPO_ROOT = old_root
                followups_triage.FOLLOWUPS_DIR = old_dir

    def test_wrapper_file_mode_does_not_require_saved_range(self) -> None:
        tooling_root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "-c", "user.name=Fixture", "-c", 'user.email=' + 'fixture' + '@' + 'example' + '.' + 'invalid',
                            "-c", "commit.gpgSign=false", "-c", "core.hooksPath=/dev/null", "commit", "-qm", "fixture",
                            "--allow-empty"], cwd=root, check=True)
            inbox = root / "docs" / "followups" / "260511_1237_followups_wrapper_repro.md"
            self._write(
                root / "docs" / "followups" / "index.md",
                "# Follow-ups — index\n\n"
                "| File | Topic | Notes |\n"
                "| --- | --- | --- |\n"
                "| `docs/followups/process_followups_master.md` | Process | active; clusters=process |\n",
            )
            self._write(
                root / "docs" / "followups" / "process_followups_master.md",
                "# Follow-ups backlog — Process\n\n"
                "**Status:** Draft\n\n"
                "## Follow-ups (backlog)\n",
            )
            self._write(
                inbox,
                "# Follow-ups backlog\n\n"
                "**Status:** Draft\n\n"
                "## Follow-ups (backlog)\n"
                "- P2 [ ] Wrapper file-mode repro — cluster=process — to=Planner — status=open — plan=null — why: proof\n",
            )

            fixture_env = {"PLANVEYOR_ROOT": tooling_root.as_posix()}
            command = (
                f"source {shlex.quote((tooling_root / 'scripts' / 'planveyor.zsh').as_posix())} && "
                "planveyor_followups_triage --file docs/followups/260511_1237_followups_wrapper_repro.md --dry-run"
            )
            result = run_zsh_fixture(
                command,
                cwd=root,
                path=os.environ.get("PATH", os.defpath),
                pybin=sys.executable,
                fixture_env=fixture_env,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("followups_triage mode=dry-run", result.stdout)
            self.assertIn("range=FILES", result.stdout)
            self.assertNotIn("Missing BASE sha", result.stderr)

    def test_exact_duplicate_merges_only_for_the_same_authority_source_ref(self) -> None:
        with temporary_git_root() as tmp:
            root = Path(tmp).resolve()
            inbox = root / "docs" / "followups" / "260721_0202_followups_capture.md"
            index = root / "docs" / "followups" / "index.md"
            master = root / "docs" / "followups" / "process_followups_master.md"
            self._write(
                index,
                "# Follow-ups — index\n\n"
                "| File | Topic | Notes |\n| --- | --- | --- |\n"
                "| `docs/followups/process_followups_master.md` | Process | active; clusters=process |\n",
            )
            row = (
                "- P1 [ ] Exact terminal finding — cluster=process — to=Coder — status=open — "
                "plan=null — source_ref=docs/plans/260716_1046_fixture.md — why: proof\n"
            )
            self._write(master, "# Master\n\n**Status:** Draft\n\n## Follow-ups\n" + row)
            self._write(inbox, "# Inbox\n\n**Status:** Draft\n\n## Follow-ups\n" + row)

            old_values = (
                followups_triage.REPO_ROOT,
                followups_triage.FOLLOWUPS_DIR,
                followups_triage.FOLLOWUPS_INDEX,
                followups_triage.FOLLOWUPS_TEMPLATE,
            )
            try:
                followups_triage.REPO_ROOT = root
                followups_triage.FOLLOWUPS_DIR = root / "docs" / "followups"
                followups_triage.FOLLOWUPS_INDEX = index
                followups_triage.FOLLOWUPS_TEMPLATE = root / "docs" / "followups" / "_template_followups_backlog.md"
                stdout = io.StringIO()
                with mock.patch("sys.stdout", stdout):
                    result = followups_triage.main(["--file", inbox.relative_to(root).as_posix(), "--dry-run"], project_root=root)
            finally:
                (
                    followups_triage.REPO_ROOT,
                    followups_triage.FOLLOWUPS_DIR,
                    followups_triage.FOLLOWUPS_INDEX,
                    followups_triage.FOLLOWUPS_TEMPLATE,
                ) = old_values

            self.assertEqual(result, 0)
            self.assertIn("merge_source", stdout.getvalue())
            self.assertNotIn("ambiguous_source_ref", stdout.getvalue())

    def test_cross_plan_exact_duplicate_is_blocked_as_ambiguous_source_ref(self) -> None:
        with temporary_git_root() as tmp:
            root = Path(tmp).resolve()
            inbox = root / "docs" / "followups" / "260721_0203_followups_capture.md"
            index = root / "docs" / "followups" / "index.md"
            master = root / "docs" / "followups" / "process_followups_master.md"
            self._write(
                index,
                "# Follow-ups — index\n\n"
                "| File | Topic | Notes |\n| --- | --- | --- |\n"
                "| `docs/followups/process_followups_master.md` | Process | active; clusters=process |\n",
            )
            self._write(
                master,
                "# Master\n\n**Status:** Draft\n\n## Follow-ups\n"
                "- P1 [ ] Exact terminal finding — cluster=process — to=Coder — status=open — "
                "plan=null — source_ref=docs/plans/260716_1046_fixture.md — why: proof\n",
            )
            self._write(
                inbox,
                "# Inbox\n\n**Status:** Draft\n\n## Follow-ups\n"
                "- P1 [ ] Exact terminal finding — cluster=process — to=Coder — status=open — "
                "plan=null — source_ref=docs/plans/260716_0136_foreign.md — why: proof\n",
            )

            old_values = (
                followups_triage.REPO_ROOT,
                followups_triage.FOLLOWUPS_DIR,
                followups_triage.FOLLOWUPS_INDEX,
                followups_triage.FOLLOWUPS_TEMPLATE,
            )
            try:
                followups_triage.REPO_ROOT = root
                followups_triage.FOLLOWUPS_DIR = root / "docs" / "followups"
                followups_triage.FOLLOWUPS_INDEX = index
                followups_triage.FOLLOWUPS_TEMPLATE = root / "docs" / "followups" / "_template_followups_backlog.md"
                stdout = io.StringIO()
                with mock.patch("sys.stdout", stdout):
                    result = followups_triage.main(["--file", inbox.relative_to(root).as_posix(), "--dry-run"], project_root=root)
            finally:
                (
                    followups_triage.REPO_ROOT,
                    followups_triage.FOLLOWUPS_DIR,
                    followups_triage.FOLLOWUPS_INDEX,
                    followups_triage.FOLLOWUPS_TEMPLATE,
                ) = old_values

            self.assertEqual(result, 0)
            self.assertIn("ambiguous_source_ref", stdout.getvalue())
            self.assertIn("pending", stdout.getvalue())
            self.assertNotIn("- merge_source: docs/", stdout.getvalue())

    def test_explicit_in_tree_symlink_cannot_bypass_nofollow_reader(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            followups = root / "docs" / "followups"
            real = followups / "260721_0205_real_followups.md"
            link = followups / "260721_0206_link_followups.md"
            self._write(
                real,
                "# Inbox\n\n**Status:** Draft\n\n## Follow-ups\n"
                "- P2 [ ] Symlink bypass — cluster=process — to=Coder — status=open — plan=null — why: proof\n",
            )
            link.symlink_to(real.name)

            old_values = (
                followups_triage.REPO_ROOT,
                followups_triage.FOLLOWUPS_DIR,
                followups_triage.FOLLOWUPS_INDEX,
                followups_triage.FOLLOWUPS_TEMPLATE,
            )
            try:
                followups_triage.REPO_ROOT = root
                followups_triage.FOLLOWUPS_DIR = followups
                followups_triage.FOLLOWUPS_INDEX = followups / "index.md"
                followups_triage.FOLLOWUPS_TEMPLATE = followups / "_template_followups_backlog.md"
                selected = followups_triage._collect_inbox_files_explicit(
                    [link.relative_to(root).as_posix()]
                )
                self.assertEqual(selected, [link])
                with self.assertRaisesRegex(Exception, "not a regular file"):
                    followups_triage._parse_followup_items(selected[0])
            finally:
                (
                    followups_triage.REPO_ROOT,
                    followups_triage.FOLLOWUPS_DIR,
                    followups_triage.FOLLOWUPS_INDEX,
                    followups_triage.FOLLOWUPS_TEMPLATE,
                ) = old_values

    def test_v2_inbox_is_not_copied_or_mutated_by_legacy_triage_apply(self) -> None:
        with temporary_git_root() as tmp:
            root = Path(tmp).resolve()
            inbox = root / "docs/followups/v2_inbox.md"
            index = root / "docs/followups/index.md"
            master = root / "docs/followups/process_followups_master.md"
            self._write(index, "# index\n\n| File | Topic | Notes |\n| --- | --- | --- |\n| `docs/followups/process_followups_master.md` | Process | clusters=process |\n")
            self._write(master, "# Master\n\n**Schema version:** followups.v2\n\n## Follow-ups\n")
            self._write(
                inbox,
                "# Inbox\n\n**Schema version:** followups.v2\n\n## Follow-ups\n"
                "- P1 [ ] Frozen tuple — cluster=process — to=coder — status=open — plan=null "
                "— item_id=triage-001 — source_ref=docs/plans/260811_0060_terminal.md "
                "— disposition_kind=null — disposition_ref=null — disposition_commit_oid=null — reason=null — why: no alternate writer\n",
            )
            old_values = (
                followups_triage.REPO_ROOT, followups_triage.FOLLOWUPS_DIR,
                followups_triage.FOLLOWUPS_INDEX, followups_triage.FOLLOWUPS_TEMPLATE,
            )
            try:
                followups_triage.REPO_ROOT = root
                followups_triage.FOLLOWUPS_DIR = root / "docs/followups"
                followups_triage.FOLLOWUPS_INDEX = index
                followups_triage.FOLLOWUPS_TEMPLATE = root / "docs/followups/_template_followups_backlog.md"
                before_master = master.read_bytes()
                stdout = io.StringIO()
                with mock.patch("sys.stdout", stdout):
                    code = followups_triage.main(["--file", "docs/followups/v2_inbox.md", "--apply"], project_root=root)
            finally:
                (
                    followups_triage.REPO_ROOT, followups_triage.FOLLOWUPS_DIR,
                    followups_triage.FOLLOWUPS_INDEX, followups_triage.FOLLOWUPS_TEMPLATE,
                ) = old_values
            self.assertEqual(code, 0)
            self.assertEqual(master.read_bytes(), before_master)
            self.assertIn("v2_declaration_required", stdout.getvalue())
            self.assertIn("followups_apply.v2 required", stdout.getvalue())

    def test_legacy_triage_apply_blocks_on_foreign_explicit_v2_integrity_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            inbox = root / "docs/followups/260811_inbox.md"
            index = root / "docs/followups/index.md"
            master = root / "docs/followups/process_followups_master.md"
            foreign = root / "docs/followups/foreign.md"
            self._write(index, "# index\n\n| File | Topic | Notes |\n| --- | --- | --- |\n| `docs/followups/process_followups_master.md` | Process | clusters=process |\n")
            self._write(master, "# Master\n\n## Follow-ups\n")
            self._write(
                inbox,
                "# Inbox\n\n## Follow-ups\n- P1 [ ] Legacy item — cluster=process — to=coder — status=open — plan=null — why: legacy write\n",
            )
            malformed = "# foreign\n\n**Schema version:** followups.v2\n**Schema version:** followups.v2\n\n## Follow-ups\n"
            self._write(foreign, malformed)
            old_values = (
                followups_triage.REPO_ROOT, followups_triage.FOLLOWUPS_DIR,
                followups_triage.FOLLOWUPS_INDEX, followups_triage.FOLLOWUPS_TEMPLATE,
            )
            try:
                followups_triage.REPO_ROOT = root
                followups_triage.FOLLOWUPS_DIR = root / "docs/followups"
                followups_triage.FOLLOWUPS_INDEX = index
                followups_triage.FOLLOWUPS_TEMPLATE = root / "docs/followups/_template_followups_backlog.md"
                before_master = master.read_bytes()
                with mock.patch("sys.stderr", io.StringIO()):
                    code = followups_triage.main(["--file", inbox.relative_to(root).as_posix(), "--apply"], project_root=root)
            finally:
                (
                    followups_triage.REPO_ROOT, followups_triage.FOLLOWUPS_DIR,
                    followups_triage.FOLLOWUPS_INDEX, followups_triage.FOLLOWUPS_TEMPLATE,
                ) = old_values

            self.assertEqual(code, 2)
            self.assertEqual(master.read_bytes(), before_master)
            self.assertEqual(foreign.read_text(encoding="utf-8"), malformed)

    def test_legacy_triage_apply_rejects_existing_valid_v2_destination_before_any_write(self) -> None:
        with temporary_git_root() as tmp:
            root = Path(tmp).resolve()
            inbox = root / "docs/followups/260812_legacy_inbox.md"
            index = root / "docs/followups/index.md"
            master = root / "docs/followups/process_followups_master.md"
            self._write(
                index,
                "# index\n\n| File | Topic | Notes |\n| --- | --- | --- |\n"
                "| `docs/followups/process_followups_master.md` | Process | clusters=process |\n",
            )
            self._write(master, "# Master\n\n**Schema version:** followups.v2\n\n## Follow-ups\n")
            self._write(
                inbox,
                "# Inbox\n\n## Follow-ups\n"
                "- P1 [ ] Legacy item — cluster=process — to=coder — status=open — plan=null — why: legacy write\n",
            )
            old_values = (
                followups_triage.REPO_ROOT, followups_triage.FOLLOWUPS_DIR,
                followups_triage.FOLLOWUPS_INDEX, followups_triage.FOLLOWUPS_TEMPLATE,
            )
            try:
                followups_triage.REPO_ROOT = root
                followups_triage.FOLLOWUPS_DIR = root / "docs" / "followups"
                followups_triage.FOLLOWUPS_INDEX = index
                followups_triage.FOLLOWUPS_TEMPLATE = root / "docs/followups/_template_followups_backlog.md"
                before = self._followup_bytes(root)
                stderr = io.StringIO()
                with mock.patch("sys.stderr", stderr), mock.patch("sys.stdout", io.StringIO()):
                    code = followups_triage.main(["--file", inbox.relative_to(root).as_posix(), "--apply"], project_root=root)
            finally:
                (
                    followups_triage.REPO_ROOT, followups_triage.FOLLOWUPS_DIR,
                    followups_triage.FOLLOWUPS_INDEX, followups_triage.FOLLOWUPS_TEMPLATE,
                ) = old_values

            self.assertEqual(code, 2)
            self.assertIn("legacy_triage_v2_destination_requires_apply", stderr.getvalue())
            self.assertEqual(self._followup_bytes(root), before)
            self.assertNotIn("**Imported into:**", inbox.read_text(encoding="utf-8"))

    def test_legacy_triage_apply_preflights_the_full_selected_batch_without_partial_import(self) -> None:
        with temporary_git_root() as tmp:
            root = Path(tmp).resolve()
            good_inbox = root / "docs/followups/260812_good_legacy_inbox.md"
            blocked_inbox = root / "docs/followups/260812_blocked_legacy_inbox.md"
            index = root / "docs/followups/index.md"
            good_master = root / "docs/followups/process_followups_master.md"
            blocked_master = root / "docs/followups/ops_followups_master.md"
            self._write(
                index,
                "# index\n\n| File | Topic | Notes |\n| --- | --- | --- |\n"
                "| `docs/followups/process_followups_master.md` | Process | clusters=process |\n"
                "| `docs/followups/ops_followups_master.md` | Ops | clusters=ops |\n",
            )
            self._write(good_master, "# Process\n\n**Schema version:** followups.v1\n\n## Follow-ups\n")
            self._write(blocked_master, "# Ops\n\n**Schema version:** followups.v2\n\n## Follow-ups\n")
            self._write(
                good_inbox,
                "# Inbox\n\n## Follow-ups\n"
                "- P1 [ ] Good legacy item — cluster=process — to=coder — status=open — plan=null — why: proof\n",
            )
            self._write(
                blocked_inbox,
                "# Inbox\n\n## Follow-ups\n"
                "- P1 [ ] Blocked legacy item — cluster=ops — to=coder — status=open — plan=null — why: proof\n",
            )
            old_values = (
                followups_triage.REPO_ROOT, followups_triage.FOLLOWUPS_DIR,
                followups_triage.FOLLOWUPS_INDEX, followups_triage.FOLLOWUPS_TEMPLATE,
            )
            try:
                followups_triage.REPO_ROOT = root
                followups_triage.FOLLOWUPS_DIR = root / "docs" / "followups"
                followups_triage.FOLLOWUPS_INDEX = index
                followups_triage.FOLLOWUPS_TEMPLATE = root / "docs/followups/_template_followups_backlog.md"
                before = self._followup_bytes(root)
                stderr = io.StringIO()
                with mock.patch("sys.stderr", stderr), mock.patch("sys.stdout", io.StringIO()):
                    code = followups_triage.main(
                        [
                            "--file", good_inbox.relative_to(root).as_posix(),
                            "--file", blocked_inbox.relative_to(root).as_posix(),
                            "--apply",
                        ]
                    , project_root=root)
            finally:
                (
                    followups_triage.REPO_ROOT, followups_triage.FOLLOWUPS_DIR,
                    followups_triage.FOLLOWUPS_INDEX, followups_triage.FOLLOWUPS_TEMPLATE,
                ) = old_values

            self.assertEqual(code, 2)
            self.assertIn("legacy_triage_v2_destination_requires_apply", stderr.getvalue())
            self.assertEqual(self._followup_bytes(root), before)
            self.assertNotIn("**Imported into:**", good_inbox.read_text(encoding="utf-8"))
            self.assertNotIn("**Imported into:**", blocked_inbox.read_text(encoding="utf-8"))

    def test_legacy_triage_apply_preserves_explicit_and_versionless_v1_routes(self) -> None:
        for schema_line in ("", "**Schema version:** followups.v1\n\n"):
            with self.subTest(schema_line=schema_line), temporary_git_root() as tmp:
                root = Path(tmp).resolve()
                inbox = root / "docs/followups/260812_legacy_inbox.md"
                index = root / "docs/followups/index.md"
                master = root / "docs/followups/process_followups_master.md"
                self._write(
                    index,
                    "# index\n\n| File | Topic | Notes |\n| --- | --- | --- |\n"
                    "| `docs/followups/process_followups_master.md` | Process | clusters=process |\n",
                )
                self._write(master, "# Master\n\n**Schema version:** followups.v1\n\n## Follow-ups\n")
                self._write(
                    inbox,
                    "# Inbox\n\n" + schema_line + "## Follow-ups\n"
                    "- P1 [ ] Legacy item — cluster=process — to=coder — status=open — plan=null — why: legacy write\n",
                )
                old_values = (
                    followups_triage.REPO_ROOT, followups_triage.FOLLOWUPS_DIR,
                    followups_triage.FOLLOWUPS_INDEX, followups_triage.FOLLOWUPS_TEMPLATE,
                )
                try:
                    followups_triage.REPO_ROOT = root
                    followups_triage.FOLLOWUPS_DIR = root / "docs" / "followups"
                    followups_triage.FOLLOWUPS_INDEX = index
                    followups_triage.FOLLOWUPS_TEMPLATE = root / "docs/followups/_template_followups_backlog.md"
                    with mock.patch("sys.stderr", io.StringIO()), mock.patch("sys.stdout", io.StringIO()):
                        code = followups_triage.main(["--file", inbox.relative_to(root).as_posix(), "--apply"], project_root=root)
                finally:
                    (
                        followups_triage.REPO_ROOT, followups_triage.FOLLOWUPS_DIR,
                        followups_triage.FOLLOWUPS_INDEX, followups_triage.FOLLOWUPS_TEMPLATE,
                    ) = old_values

                self.assertEqual(code, 0)
                self.assertIn("Legacy item", master.read_text(encoding="utf-8"))
                self.assertIn("**Imported into:**", inbox.read_text(encoding="utf-8"))


    def test_legacy_triage_accepts_safe_generic_clusters_and_falls_back_for_invalid_values(self) -> None:
        for raw_cluster, route_cluster, target_cluster, expect_fallback in (
            ("quality_lane", "quality_lane", "quality_lane", False),
            ("quality_lane", "process", "process", True),
            ("not-a-slug", "process", "process", True),
            (None, "process", "process", True),
        ):
            with self.subTest(raw_cluster=raw_cluster), temporary_git_root() as tmp:
                root = Path(tmp).resolve()
                inbox = root / "docs/followups/260813_legacy_inbox.md"
                index = root / "docs/followups/index.md"
                master = root / f"docs/followups/{route_cluster}_followups_master.md"
                self._write(
                    index,
                    "# index\n\n| File | Topic | Notes |\n| --- | --- | --- |\n"
                    f"| `docs/followups/{route_cluster}_followups_master.md` | Route | clusters={route_cluster} |\n",
                )
                self._write(master, "# Master\n\n**Schema version:** followups.v1\n\n## Follow-ups\n")
                self._write(
                    inbox,
                    "# Inbox\n\n## Follow-ups\n"
                    "- P1 [ ] Legacy route"
                    + (f" — cluster={raw_cluster}" if raw_cluster is not None else "")
                    + " — to=coder — status=open — plan=null — why: proof\n",
                )
                old_values = (
                    followups_triage.REPO_ROOT, followups_triage.FOLLOWUPS_DIR,
                    followups_triage.FOLLOWUPS_INDEX, followups_triage.FOLLOWUPS_TEMPLATE,
                )
                try:
                    followups_triage.REPO_ROOT = root
                    followups_triage.FOLLOWUPS_DIR = root / "docs/followups"
                    followups_triage.FOLLOWUPS_INDEX = index
                    followups_triage.FOLLOWUPS_TEMPLATE = root / "docs/followups/_template_followups_backlog.md"
                    stdout = io.StringIO()
                    with mock.patch("sys.stdout", stdout), mock.patch("sys.stderr", io.StringIO()):
                        code = followups_triage.main(
                            ["--file", inbox.relative_to(root).as_posix(), "--apply"], project_root=root
                        )
                finally:
                    (
                        followups_triage.REPO_ROOT, followups_triage.FOLLOWUPS_DIR,
                        followups_triage.FOLLOWUPS_INDEX, followups_triage.FOLLOWUPS_TEMPLATE,
                    ) = old_values

                self.assertEqual(code, 0)
                master_text = master.read_text(encoding="utf-8")
                self.assertIn(f"cluster={target_cluster}", master_text)
                if raw_cluster and raw_cluster != target_cluster:
                    self.assertNotIn(f"cluster={raw_cluster}", master_text)
                if expect_fallback:
                    self.assertIn("route_fallback: 1", stdout.getvalue())
                    self.assertIn("status=UNCONFIRMED", master_text)
                else:
                    self.assertIn("route_fallback: 0", stdout.getvalue())
                    self.assertNotIn("status=UNCONFIRMED", master_text)

    def test_legacy_safe_slug_without_a_route_or_master_writes_nothing(self) -> None:
        with temporary_git_root() as tmp:
            root = Path(tmp).resolve()
            inbox = root / "docs/followups/260814_legacy_inbox.md"
            index = root / "docs/followups/index.md"
            self._write(index, "# index\n\n| File | Topic | Notes |\n| --- | --- | --- |\n")
            self._write(
                inbox,
                "# Inbox\n\n## Follow-ups\n"
                "- P1 [ ] No route — cluster=quality_lane — to=coder — status=open — plan=null — why: proof\n",
            )
            old_values = (
                followups_triage.REPO_ROOT, followups_triage.FOLLOWUPS_DIR,
                followups_triage.FOLLOWUPS_INDEX, followups_triage.FOLLOWUPS_TEMPLATE,
            )
            try:
                followups_triage.REPO_ROOT = root
                followups_triage.FOLLOWUPS_DIR = root / "docs/followups"
                followups_triage.FOLLOWUPS_INDEX = index
                followups_triage.FOLLOWUPS_TEMPLATE = root / "docs/followups/_template_followups_backlog.md"
                before = self._followup_bytes(root)
                stderr = io.StringIO()
                with mock.patch("sys.stdout", io.StringIO()), mock.patch("sys.stderr", stderr):
                    code = followups_triage.main(
                        ["--file", inbox.relative_to(root).as_posix(), "--apply"], project_root=root
                    )
            finally:
                (
                    followups_triage.REPO_ROOT, followups_triage.FOLLOWUPS_DIR,
                    followups_triage.FOLLOWUPS_INDEX, followups_triage.FOLLOWUPS_TEMPLATE,
                ) = old_values

            self.assertEqual(code, 2)
            self.assertIn("legacy_triage_destination_not_legacy_v1", stderr.getvalue())
            self.assertIn("-> process", stderr.getvalue())
            self.assertEqual(self._followup_bytes(root), before)
            self.assertNotIn("**Imported into:**", inbox.read_text(encoding="utf-8"))

    def test_legacy_safe_route_keeps_the_v2_destination_guard(self) -> None:
        with temporary_git_root() as tmp:
            root = Path(tmp).resolve()
            inbox = root / "docs/followups/260814_legacy_inbox.md"
            index = root / "docs/followups/index.md"
            master = root / "docs/followups/quality_lane_followups_master.md"
            self._write(
                index,
                "# index\n\n| File | Topic | Notes |\n| --- | --- | --- |\n"
                "| `docs/followups/quality_lane_followups_master.md` | Quality | clusters=quality_lane |\n",
            )
            self._write(master, "# Master\n\n**Schema version:** followups.v2\n\n## Follow-ups\n")
            self._write(
                inbox,
                "# Inbox\n\n## Follow-ups\n"
                "- P1 [ ] Safe route guard — cluster=quality_lane — to=coder — status=open — plan=null — why: proof\n",
            )
            old_values = (
                followups_triage.REPO_ROOT, followups_triage.FOLLOWUPS_DIR,
                followups_triage.FOLLOWUPS_INDEX, followups_triage.FOLLOWUPS_TEMPLATE,
            )
            try:
                followups_triage.REPO_ROOT = root
                followups_triage.FOLLOWUPS_DIR = root / "docs/followups"
                followups_triage.FOLLOWUPS_INDEX = index
                followups_triage.FOLLOWUPS_TEMPLATE = root / "docs/followups/_template_followups_backlog.md"
                before = self._followup_bytes(root)
                stderr = io.StringIO()
                with mock.patch("sys.stdout", io.StringIO()), mock.patch("sys.stderr", stderr):
                    code = followups_triage.main(
                        ["--file", inbox.relative_to(root).as_posix(), "--apply"], project_root=root
                    )
            finally:
                (
                    followups_triage.REPO_ROOT, followups_triage.FOLLOWUPS_DIR,
                    followups_triage.FOLLOWUPS_INDEX, followups_triage.FOLLOWUPS_TEMPLATE,
                ) = old_values

            self.assertEqual(code, 2)
            self.assertIn("legacy_triage_v2_destination_requires_apply", stderr.getvalue())
            self.assertEqual(self._followup_bytes(root), before)
            self.assertNotIn("**Imported into:**", inbox.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

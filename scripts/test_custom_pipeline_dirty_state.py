#!/usr/bin/env python3
from __future__ import annotations

import io
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from textwrap import dedent
from unittest import mock


MODULE_PATH = Path(__file__).with_name("custom_pipeline_dirty_state.py")
SPEC = importlib.util.spec_from_file_location("custom_pipeline_dirty_state", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


PLAN_REL = "docs/plans/260708_2154_process_custom_pipeline_dirty_state_ownership_precheck.md"
DRAFT_REL = "docs/code_drafts/260708_2154_process_custom_pipeline_dirty_state_ownership_precheck__code_draft.md"
REVIEW_REL = "docs/code_reviews/260708_2154_process_custom_pipeline_dirty_state_ownership_precheck.md"
HELPER_REL = "scripts/custom_pipeline_dirty_state.py"
TEST_REL = "scripts/test_custom_pipeline_dirty_state.py"
PROMPT_TEST_REL = "scripts/test_manager_custom_pipeline_prompt_contract.py"
PROMPT_REL = "docs/tools/prompts/manager_custom_pipeline.md"
RUNBOOK_REL = "docs/tools/owner_runbook_codex.md"
TARGETS = [HELPER_REL, TEST_REL, PROMPT_TEST_REL, PROMPT_REL, RUNBOOK_REL]


class CustomPipelineDirtyStateTests(unittest.TestCase):
    def _run(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            list(args),
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )

    def _run_bytes(self, root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            list(args),
            cwd=root,
            text=False,
            capture_output=True,
            check=False,
        )

    def _write(self, root: Path, rel_path: str, text: str) -> Path:
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def _init_repo(self, root: Path) -> None:
        self.assertEqual(self._run(root, "git", "init").returncode, 0)
        self.assertEqual(self._run(root, "git", "config", "user.email", 'test' + '@' + 'example' + '.' + 'invalid').returncode, 0)
        self.assertEqual(self._run(root, "git", "config", "user.name", "Test User").returncode, 0)

    def _commit_all(self, root: Path, message: str = "base") -> None:
        self.assertEqual(self._run(root, "git", "add", ".").returncode, 0)
        result = self._run(root, "git", "commit", "-m", message)
        self.assertEqual(result.returncode, 0, result.stderr)

    def _write_draft_bundle(
        self,
        root: Path,
        *,
        targets: list[str],
        deleted_paths: object | None = None,
    ) -> None:
        payload = {
            "code_draft_meta": {
                "plan": PLAN_REL,
                "cluster": "process",
                "targets": [{"path": target, "kind": "py"} for target in targets],
                "deleted_paths": [] if deleted_paths is None else deleted_paths,
            }
        }
        self._write(root, DRAFT_REL, "# Code draft\n\n```json\n" + json.dumps(payload, indent=2) + "\n```\n")

    def _write_plan_bundle(self, root: Path, *, targets: list[str] | None = None) -> None:
        targets = targets or TARGETS
        self._write(
            root,
            PLAN_REL,
            dedent(
                f"""\
                # Plan: dirty state fixture

                **Status:** Ready for Coder

                **Context links (source of truth):**
                - Code draft(s): `{DRAFT_REL}`
                - Planned review artifact: `{REVIEW_REL}`

                ## Review artifacts
                - Code review (primary): `{REVIEW_REL}`
                """
            ),
        )
        self._write_draft_bundle(root, targets=targets)
        for target in targets:
            self._write(root, target, "base target\n")

    def _base_repo(self, *, targets: list[str] | None = None) -> tempfile.TemporaryDirectory[str]:
        tmpdir = tempfile.TemporaryDirectory()
        root = Path(tmpdir.name)
        self._init_repo(root)
        self._write_plan_bundle(root, targets=targets)
        self._commit_all(root)
        return tmpdir

    def _payload(self, root: Path, *, sibling_evidence: dict[str, str] | None = None):
        return MODULE.build_precheck(PLAN_REL, repo_root=root, sibling_evidence=sibling_evidence or {})

    def test_clean_repo_continues(self) -> None:
        with self._base_repo() as tmp:
            payload = self._payload(Path(tmp))

        self.assertEqual(payload["schema"], "custom_pipeline_dirty_state.v1")
        self.assertEqual(payload["verdict"], "continue")
        self.assertEqual(payload["summary"]["total"], 0)

    def test_cli_resolves_consumer_git_root_for_relative_plan_path(self) -> None:
        with self._base_repo() as tmp:
            root = Path(tmp)
            self._write(root, HELPER_REL, "changed helper\n")
            nested = root / "nested" / "child"
            nested.mkdir(parents=True)
            output = io.StringIO()
            previous_cwd = Path.cwd()
            try:
                os.chdir(nested)
                with redirect_stdout(output):
                    rc = MODULE.main([PLAN_REL, "--format", "json"])
            finally:
                os.chdir(previous_cwd)

        self.assertEqual(rc, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["plan_path"], PLAN_REL)
        self.assertEqual(payload["verdict"], "continue")
        self.assertEqual(payload["files"][0]["path"], HELPER_REL)
        self.assertEqual(payload["files"][0]["ownership_class"], "exact_bundle")

    def test_default_api_root_resolves_current_consumer_context(self) -> None:
        with self._base_repo() as tmp:
            root = Path(tmp)
            self._write(root, HELPER_REL, "changed helper\n")
            nested = root / "nested" / "child"
            nested.mkdir(parents=True)
            previous_cwd = Path.cwd()
            try:
                os.chdir(nested)
                payload = MODULE.build_precheck(PLAN_REL)
            finally:
                os.chdir(previous_cwd)

        self.assertEqual(payload["plan_path"], PLAN_REL)
        self.assertEqual(payload["verdict"], "continue")
        self.assertEqual(payload["files"][0]["path"], HELPER_REL)
        self.assertEqual(payload["files"][0]["ownership_class"], "exact_bundle")

    def test_exact_bundle_dirty_continues(self) -> None:
        with self._base_repo() as tmp:
            root = Path(tmp)
            self._write(root, HELPER_REL, "changed helper\n")

            payload = self._payload(root)

        self.assertEqual(payload["verdict"], "continue")
        self.assertEqual(payload["files"][0]["path"], HELPER_REL)
        self.assertEqual(payload["files"][0]["ownership_class"], "exact_bundle")
        self.assertIn(f"file={HELPER_REL} status= M", MODULE._render_text(payload))

    def test_untracked_outside_bundle_stops_as_ambiguous_owner(self) -> None:
        with self._base_repo() as tmp:
            root = Path(tmp)
            self._write(root, "docs/followups/sibling.md", "untracked followup\n")

            payload = self._payload(root)

        self.assertEqual(payload["verdict"], "stop")
        self.assertEqual(payload["files"][0]["ownership_class"], "ambiguous_owner")
        self.assertTrue(payload["files"][0]["blocking"])

    def test_tracked_outside_bundle_stops_as_unrelated_dirty(self) -> None:
        with self._base_repo() as tmp:
            root = Path(tmp)
            outside = "docs/process_improvements/sibling.md"
            self._write(root, outside, "committed sibling baseline\n")
            self._commit_all(root, "add outside path")
            self._write(root, outside, "dirty sibling path without evidence\n")

            payload = self._payload(root)

        self.assertEqual(payload["verdict"], "stop")
        self.assertEqual(payload["files"][0]["ownership_class"], "unrelated_dirty")

    def test_committed_sibling_followup_with_repo_backed_evidence_continues(self) -> None:
        with self._base_repo() as tmp:
            root = Path(tmp)
            outside = "docs/process_improvements/sibling.md"
            owner_ref = "docs/plans/260708_2157_process_custom_pipeline_compact_censor_evidence_dedupe.md"
            self._write(root, outside, "committed sibling baseline\n")
            self._write(root, owner_ref, "# Sibling plan\n")
            self._commit_all(root, "add sibling evidence")
            self._write(root, outside, "dirty sibling path with evidence\n")

            payload = self._payload(root, sibling_evidence={outside: owner_ref})

        self.assertEqual(payload["verdict"], "continue")
        self.assertEqual(payload["files"][0]["ownership_class"], "committed_sibling_followup")
        self.assertEqual(payload["files"][0]["owner_ref"], owner_ref)
        self.assertIn("path_commit", payload["files"][0]["evidence"])

    def test_sibling_evidence_mismatch_fails_closed(self) -> None:
        with self._base_repo() as tmp:
            root = Path(tmp)
            outside = "docs/process_improvements/untracked.md"
            owner_ref = "docs/plans/260708_2157_process_custom_pipeline_compact_censor_evidence_dedupe.md"
            self._write(root, owner_ref, "# Sibling plan\n")
            self._commit_all(root, "add sibling owner ref")
            self._write(root, outside, "untracked sibling path\n")

            payload = self._payload(root, sibling_evidence={outside: owner_ref})

        self.assertEqual(payload["verdict"], "stop")
        self.assertEqual(payload["files"][0]["ownership_class"], "ambiguous_owner")
        self.assertIn("path_commit", payload["files"][0]["reason"])

    def test_missing_code_draft_stops(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._init_repo(root)
            self._write(
                root,
                PLAN_REL,
                "# Plan\n\n**Status:** Ready for Coder\n\n## Review artifacts\n",
            )
            self._commit_all(root)

            payload = self._payload(root)

        self.assertEqual(payload["verdict"], "stop")
        self.assertEqual(payload["reason"], "missing_or_invalid_exact_bundle")
        self.assertEqual(payload["summary"]["blocking"], 1)

    def test_special_paths_round_trip_and_render_safely(self) -> None:
        non_utf8 = os.fsdecode(b"special/non-utf8-\xff.txt")
        special_paths = [
            "special/ leading.txt",
            "special/trailing.txt ",
            "special/tab\tname.txt",
            "special/newline\nname.txt",
            'special/"quote".txt',
            "special/Юникод.txt",
            "special/-leading-dash.txt",
            "special/back\\slash.txt",
        ]
        with self._base_repo(targets=[*TARGETS, *special_paths]) as tmp:
            root = Path(tmp)
            blob_result = subprocess.run(
                ["git", "-C", str(root), "hash-object", "-w", "--stdin"],
                input=b"non-utf8 tracked content\n",
                capture_output=True,
                check=False,
            )
            self.assertEqual(blob_result.returncode, 0, blob_result.stderr)
            blob = blob_result.stdout.decode("ascii").strip()
            cache_info = f"100644,{blob},{non_utf8}"
            self.assertEqual(
                self._run(root, "git", "update-index", "--add", "--cacheinfo", cache_info).returncode,
                0,
            )
            commit = self._run(root, "git", "commit", "-m", "add non-utf8 index path")
            self.assertEqual(commit.returncode, 0, commit.stderr)
            self._write_draft_bundle(
                root,
                targets=[*TARGETS, *special_paths],
                deleted_paths=[{"path": non_utf8, "kind": "py"}],
            )
            for path in special_paths:
                self._write(root, path, "changed target\n")

            payload = self._payload(root)

        self.assertEqual(payload["verdict"], "continue")
        expected_paths = {*special_paths, non_utf8}
        self.assertTrue(expected_paths.issubset({item["path"] for item in payload["files"]}))
        json_output = json.dumps(payload, sort_keys=True)
        text_output = MODULE._render_text(payload)
        self.assertIn(r"special/newline\nname.txt", text_output)
        self.assertIn(r"special/tab\tname.txt", text_output)
        self.assertIn(r'special/\"quote\".txt', text_output)
        self.assertIn(r"special/back\\slash.txt", text_output)
        self.assertIn(r"special/non-utf8-\udcff.txt", text_output)
        self.assertIn("special/Юникод.txt", text_output)
        self.assertIn(r"\udcff", json_output)
        self.assertEqual(len(text_output.splitlines()), 7 + len(payload["files"]))
        self.assertEqual(MODULE._compact_escape("\b\f\n\r\t"), r"\b\f\n\r\t")
        self.assertEqual(MODULE._compact_escape('\\"'), r'\\\"')
        self.assertEqual(MODULE._compact_escape("\x01\udcff"), r"\u0001\udcff")
        self.assertEqual(MODULE._compact_escape("Юникод"), "Юникод")

    def test_real_rename_uses_destination_then_owned_deleted_source(self) -> None:
        source = "rename/source.txt"
        destination = "rename/destination.txt"
        with self._base_repo() as tmp:
            root = Path(tmp)
            self._write(root, source, "rename content\n")
            self._commit_all(root, "add rename source")
            self.assertEqual(self._run(root, "git", "mv", source, destination).returncode, 0)
            self._write_draft_bundle(
                root,
                targets=[*TARGETS, destination],
                deleted_paths=[{"path": source, "kind": "py"}],
            )

            raw = self._run_bytes(
                root,
                "git",
                "status",
                "--porcelain=v1",
                "-z",
                "--untracked-files=all",
            ).stdout
            records = MODULE._parse_git_status(raw)
            rename = next(record for record in records if record.source_kind == "rename")
            payload = self._payload(root)

        self.assertEqual(rename.path, destination)
        self.assertEqual(rename.source_path, source)
        self.assertEqual(payload["verdict"], "continue")
        item = next(item for item in payload["files"] if item["path"] == destination)
        self.assertEqual(item["ownership_class"], "exact_bundle")
        self.assertNotIn("source_path", item)

    def test_cross_boundary_rename_source_stops_with_actionable_reason(self) -> None:
        source = 'rename/outside\n"source"\\path.txt'
        destination = "rename/owned-destination.txt"
        with self._base_repo() as tmp:
            root = Path(tmp)
            self._write(root, source, "rename content\n")
            self._commit_all(root, "add outside rename source")
            self.assertEqual(self._run(root, "git", "mv", source, destination).returncode, 0)
            self._write_draft_bundle(root, targets=[*TARGETS, destination])

            payload = self._payload(root)

        self.assertEqual(payload["verdict"], "stop")
        item = next(item for item in payload["files"] if item["path"] == destination)
        self.assertEqual(item["path"], destination)
        self.assertEqual(item["ownership_class"], "unrelated_dirty")
        self.assertIn(source, item["reason"])
        self.assertIn("ownership mismatch", item["reason"])
        self.assertNotIn("source_path", item)
        rendered = MODULE._render_text(payload)
        self.assertIn(
            r'rename source path=rename/outside\n\"source\"\\path.txt ownership mismatch',
            rendered,
        )
        self.assertEqual(len(rendered.splitlines()), 7 + len(payload["files"]))

    def test_real_copy_record_keeps_source_internal_and_read_only(self) -> None:
        source = "copy/source.txt"
        destination = "copy/destination.txt"
        owner_ref = "docs/plans/copy_source_owner.md"
        with self._base_repo() as tmp:
            root = Path(tmp)
            self._write(root, source, "copy source baseline\n")
            self._write(root, owner_ref, "# Copy source owner\n")
            self._commit_all(root, "add outside copy source evidence")
            self.assertEqual(self._run(root, "git", "config", "status.renames", "copies").returncode, 0)
            (root / destination).parent.mkdir(parents=True, exist_ok=True)
            (root / destination).write_bytes((root / source).read_bytes())
            with (root / source).open("ab") as stream:
                stream.write(b"changed source\n")
            self.assertEqual(self._run(root, "git", "add", source, destination).returncode, 0)
            self._write_draft_bundle(root, targets=[*TARGETS, destination])

            raw = self._run_bytes(
                root,
                "git",
                "status",
                "--porcelain=v1",
                "-z",
                "--untracked-files=all",
            ).stdout
            records = MODULE._parse_git_status(raw)
            copy_record = next(record for record in records if record.source_kind == "copy")
            payload = self._payload(root, sibling_evidence={source: owner_ref})

        self.assertEqual(copy_record.status, "C ")
        self.assertEqual(copy_record.path, destination)
        self.assertEqual(copy_record.source_path, source)
        self.assertEqual(payload["verdict"], "continue")
        copy_item = next(item for item in payload["files"] if item["git_status"] == "C ")
        self.assertEqual(copy_item["path"], destination)
        self.assertEqual(copy_item["ownership_class"], "exact_bundle")
        self.assertNotIn("source_path", copy_item)
        source_item = next(item for item in payload["files"] if item["path"] == source)
        self.assertEqual(source_item["ownership_class"], "committed_sibling_followup")

    def test_git_status_failure_decodes_bounded_bytes_without_traceback(self) -> None:
        with self._base_repo() as tmp:
            root = Path(tmp)
            status_result = subprocess.CompletedProcess(
                args=["git", "status"],
                returncode=128,
                stdout=b"",
                stderr=b"fatal: status failed \xff\n",
            )
            with mock.patch.object(MODULE, "_run_git_status", return_value=status_result):
                payload = self._payload(root)

        self.assertEqual(payload["verdict"], "stop")
        self.assertEqual(payload["reason"], "git_status_unavailable")
        self.assertEqual(payload["files"], [])
        self.assertEqual(payload["summary"], {"total": 0, "blocking": 1})
        self.assertIn("\udcff", payload["git_error"])
        self.assertIn(r"\udcff", json.dumps(payload))

    def test_deleted_paths_metadata_fails_closed_without_head_proof(self) -> None:
        cases: list[tuple[str, object]] = [
            ("malformed entry", ["deleted/not-a-mapping.txt"]),
            ("tree claim", [{"path": "scripts", "kind": "py"}]),
            (
                "untracked claim",
                [{"path": "deleted/untracked.txt", "kind": "py"}],
            ),
        ]
        for label, deleted_paths in cases:
            with self.subTest(label=label), self._base_repo() as tmp:
                root = Path(tmp)
                if label == "untracked claim":
                    self._write(root, "deleted/untracked.txt", "untracked\n")
                self._write_draft_bundle(root, targets=TARGETS, deleted_paths=deleted_paths)

                payload = self._payload(root)

                self.assertEqual(payload["verdict"], "stop")
                self.assertEqual(payload["reason"], "missing_or_invalid_exact_bundle")
                self.assertEqual(payload["files"], [])
                self.assertTrue(payload["exact_bundle"]["errors"])

    def test_malformed_byte_streams_fail_without_partial_classification(self) -> None:
        malformed_streams = {
            "missing final NUL": b"?? path",
            "short header": b"M \0",
            "empty path": b"M  \0",
            "invalid status": b"Z  path\0",
            "missing rename source": b"R  destination\0",
            "ambiguous rename copy": b"RC destination\0source\0",
            "malformed tail after valid record": b"?? valid\0M\0",
        }
        with self._base_repo() as tmp:
            root = Path(tmp)
            for label, stdout in malformed_streams.items():
                with self.subTest(label=label):
                    status_result = subprocess.CompletedProcess(
                        args=["git", "status"],
                        returncode=0,
                        stdout=stdout,
                        stderr=b"",
                    )
                    with mock.patch.object(MODULE, "_run_git_status", return_value=status_result):
                        payload = self._payload(root)

                    self.assertEqual(payload["verdict"], "stop")
                    self.assertEqual(payload["reason"], "git_status_malformed")
                    self.assertEqual(payload["files"], [])
                    self.assertEqual(payload["summary"], {"total": 0, "blocking": 1})
                    output = io.StringIO()
                    with (
                        mock.patch.object(MODULE, "build_precheck", return_value=payload),
                        redirect_stdout(output),
                    ):
                        returncode = MODULE.main([PLAN_REL, "--format", "json"])
                    self.assertEqual(returncode, 2)
                    self.assertEqual(json.loads(output.getvalue())["reason"], "git_status_malformed")


if __name__ == "__main__":
    unittest.main()

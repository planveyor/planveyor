from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

try:
    from scripts import contract_authority_snapshot as authority
except ImportError:
    import contract_authority_snapshot as authority

ROOT = Path(__file__).resolve().parents[1]
MARKER = "docs/_meta/planveyor_contract_authority.v1.json"
MANIFEST = "docs/_meta/contract_sources.v1.json"


def clean_git_env() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update({
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_OPTIONAL_LOCKS": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    return env


def git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(
        ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", "-C", str(root), *args],
        env=clean_git_env(), stderr=subprocess.PIPE,
    )


def filesystem_state(root: Path) -> dict[str, tuple[object, ...]]:
    state = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            state[relative] = ("link", os.readlink(path))
        elif path.is_file():
            state[relative] = ("file", path.stat().st_mode & 0o777, hashlib.sha256(path.read_bytes()).hexdigest())
        elif path.is_dir():
            state[relative] = ("dir", path.stat().st_mode & 0o777)
    return state


class AuthoritySnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="planveyor-authority-snapshot-")
        self.base = Path(self.tmp.name).resolve()
        self.repo = self.init_repo("planveyor")
        self.runtime_root = self.init_repo("runtime")
        self.write(self.runtime_root, "scripts/engine.py", b"# independent fixture runtime\n", 0o755)
        self.write(self.runtime_root, "docs/runtime_api.json", b'{"version":1}\n')
        self.commit(self.runtime_root, "runtime fixture")
        self.runtime = self.runtime_identity()
        self.write(self.repo, "docs/roles/coder.md", b"# Product coder contract\n")
        self.write(self.repo, "scripts/product_check.py", b"# Product proof fixture\n", 0o755)
        self.write(self.repo, "unrelated.txt", b"unrelated initial state\n")
        self.commit(self.repo, "product content")
        self.manifest = {
            "schema_version": 1,
            "required_content": [
                self.content_row("docs/roles/coder.md"),
                self.content_row("scripts/product_check.py"),
            ],
        }
        self.marker = {
            "schema_version": 1,
            "repository_id": "planveyor",
            "authority_mode": "target-local",
            "contract_root": ".",
            "required_runtime_api": {"minimum": 1, "maximum": 2},
            "closure_manifest": MANIFEST,
            "source_baseline": {"repository_id": "planveyor", "commit": "1" * 40},
        }

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def init_repo(self, name: str) -> Path:
        root = self.base / name
        root.mkdir()
        git(root, "init", "-q")
        git(root, "config", "user.name", "Authority Fixture")
        git(root, "config", "user.email", 'authority-fixture' + '@' + 'example' + '.' + 'invalid')
        git(root, "config", "core.filemode", "true")
        git(root, "commit", "--allow-empty", "-qm", "fixture root")
        return root

    def write(self, root: Path, relative: str, data: bytes, mode: int = 0o644) -> Path:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        path.chmod(mode)
        return path

    def commit(self, root: Path, message: str) -> None:
        git(root, "add", "-A")
        git(root, "commit", "-qm", message)

    def content_row(self, relative: str) -> dict[str, str]:
        path = self.repo / relative
        return {
            "path": relative,
            "mode": "100755" if path.stat().st_mode & 0o100 else "100644",
            "blob_oid": git(self.repo, "rev-parse", "HEAD:" + relative).decode().strip(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    def runtime_identity(self):
        inputs = []
        for name in ("scripts/engine.py", "docs/runtime_api.json"):
            path = self.runtime_root / name
            inputs.append(authority.RuntimeContent(
                path=name,
                mode="100755" if path.stat().st_mode & 0o100 else "100644",
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            ))
        return authority.RuntimeDiskIdentity(
            root=self.runtime_root,
            commit=git(self.runtime_root, "rev-parse", "HEAD").decode().strip(),
            tree=git(self.runtime_root, "rev-parse", "HEAD^{tree}").decode().strip(),
            api_version=1,
            executable_inputs=tuple(inputs),
        )

    def seal(self, *, marker: dict | None = None, manifest: dict | None = None) -> None:
        self.write(self.repo, MANIFEST, json.dumps(self.manifest if manifest is None else manifest).encode() + b"\n")
        self.write(self.repo, MARKER, json.dumps(self.marker if marker is None else marker).encode() + b"\n")
        self.commit(self.repo, "candidate declaration fixture")

    def capture(self, root: Path | None = None, runtime=None):
        return authority.capture_candidate_snapshot(
            self.repo if root is None else root,
            expected_repository_id="planveyor",
            runtime=self.runtime if runtime is None else runtime,
        )

    def assert_rejected(self, call, reason_code: str | None = None) -> None:
        with self.assertRaises(authority.ContractAuthorityError) as caught:
            call()
        self.assertTrue(caught.exception.reason_code)
        if reason_code is not None:
            self.assertEqual(caught.exception.reason_code, reason_code)

    def test_valid_candidate_has_no_effects_and_is_immutable(self) -> None:
        self.seal()
        before = filesystem_state(self.base)
        snapshot = self.capture()
        self.assertIsInstance(snapshot, authority.CandidateAuthoritySnapshot)
        self.assertEqual(snapshot.marker.repository_id, "planveyor")
        self.assertEqual(snapshot.git.head, git(self.repo, "rev-parse", "HEAD").decode().strip())
        self.assertEqual(snapshot.runtime, self.runtime)
        with self.assertRaises(FrozenInstanceError):
            snapshot.marker.repository_id = "other"
        verified = authority.verify_candidate_snapshot(snapshot, expected_repository_id="planveyor", runtime=self.runtime)
        self.assertEqual(verified, snapshot)
        self.assertEqual(filesystem_state(self.base), before)

    def test_source_baseline_is_not_the_current_runtime_revision(self) -> None:
        self.seal()
        self.assertNotEqual(self.marker["source_baseline"]["commit"], self.runtime.commit)
        self.assertIsInstance(self.capture(), authority.CandidateAuthoritySnapshot)

    def test_head_without_marker_is_explicit_legacy_and_writes_nothing(self) -> None:
        before = filesystem_state(self.base)
        observed = self.capture()
        self.assertIsInstance(observed, authority.LegacyAuthorityObservation)
        self.assertNotIsInstance(observed, authority.CandidateAuthoritySnapshot)
        self.assertEqual(filesystem_state(self.base), before)

    def test_working_only_marker_is_not_a_candidate(self) -> None:
        self.write(self.repo, MARKER, json.dumps(self.marker).encode())
        before = filesystem_state(self.base)
        self.assert_rejected(self.capture)
        self.assertEqual(filesystem_state(self.base), before)

    def test_index_only_marker_is_not_a_candidate(self) -> None:
        self.write(self.repo, MARKER, json.dumps(self.marker).encode())
        git(self.repo, "add", MARKER)
        (self.repo / MARKER).unlink()
        self.assert_rejected(self.capture)

    def test_staged_but_uncommitted_marker_is_not_a_candidate(self) -> None:
        self.write(self.repo, MARKER, json.dumps(self.marker).encode())
        git(self.repo, "add", MARKER)
        self.assert_rejected(self.capture)

    def test_missing_or_dirty_tracked_marker_is_rejected(self) -> None:
        self.seal()
        path = self.repo / MARKER
        original = path.read_bytes()
        for data in (None, original + b" ", b"not json"):
            with self.subTest(data=data):
                if data is None:
                    path.unlink()
                else:
                    path.write_bytes(data)
                self.assert_rejected(self.capture)
                path.write_bytes(original)

    def test_staged_marker_drift_cannot_be_hidden_by_restoring_worktree(self) -> None:
        self.seal()
        path = self.repo / MARKER
        original = path.read_bytes()
        path.write_bytes(original + b" ")
        git(self.repo, "add", MARKER)
        path.write_bytes(original)
        self.assert_rejected(self.capture)

    def test_manifest_missing_dirty_or_staged_drift_is_rejected(self) -> None:
        self.seal()
        path = self.repo / MANIFEST
        original = path.read_bytes()
        path.unlink()
        self.assert_rejected(self.capture)
        path.write_bytes(original + b" ")
        self.assert_rejected(self.capture)
        git(self.repo, "add", MANIFEST)
        path.write_bytes(original)
        self.assert_rejected(self.capture)

    def test_required_content_hash_oid_and_mode_are_independent_checks(self) -> None:
        for field, wrong in (("sha256", "0" * 64), ("blob_oid", "0" * 40), ("mode", "100755")):
            with self.subTest(field=field):
                manifest = copy.deepcopy(self.manifest)
                manifest["required_content"][0][field] = wrong
                self.seal(manifest=manifest)
                self.assert_rejected(self.capture)

    def test_required_content_missing_and_raw_byte_drift_are_rejected(self) -> None:
        self.seal()
        path = self.repo / "docs/roles/coder.md"
        original = path.read_bytes()
        path.unlink()
        self.assert_rejected(self.capture)
        path.write_bytes(original + b"changed\n")
        self.assert_rejected(self.capture)

    def test_required_staged_change_with_original_worktree_is_rejected(self) -> None:
        self.seal()
        path = self.repo / "docs/roles/coder.md"
        original = path.read_bytes()
        path.write_bytes(b"staged change\n")
        git(self.repo, "add", "docs/roles/coder.md")
        path.write_bytes(original)
        self.assert_rejected(self.capture)

    def test_mode_drift_is_not_hidden_by_core_filemode_false(self) -> None:
        self.seal()
        git(self.repo, "config", "core.filemode", "false")
        (self.repo / "docs/roles/coder.md").chmod(0o755)
        self.assert_rejected(self.capture)

    def test_assume_unchanged_flag_does_not_hide_content_drift(self) -> None:
        self.seal()
        git(self.repo, "update-index", "--assume-unchanged", "docs/roles/coder.md")
        (self.repo / "docs/roles/coder.md").write_bytes(b"hidden dirty content\n")
        self.assert_rejected(self.capture)

    def test_unmerged_index_is_rejected(self) -> None:
        self.seal()
        relative = "docs/roles/coder.md"
        oid = self.manifest["required_content"][0]["blob_oid"]
        payload = f"0 {'0' * 40}\t{relative}\n100644 {oid} 1\t{relative}\n100644 {oid} 2\t{relative}\n".encode()
        subprocess.run(
            ["git", "-C", str(self.repo), "update-index", "--index-info"],
            input=payload, check=True, env=clean_git_env(), capture_output=True,
        )
        self.assert_rejected(self.capture)

    def test_leaf_and_ancestor_symlinks_are_rejected_without_writes(self) -> None:
        self.seal()
        leaf = self.repo / "docs/roles/coder.md"
        original = leaf.read_bytes()
        other = self.write(self.base, "other.md", original)
        leaf.unlink()
        leaf.symlink_to(other)
        before = filesystem_state(self.base)
        self.assert_rejected(self.capture)
        self.assertEqual(filesystem_state(self.base), before)
        leaf.unlink()
        leaf.write_bytes(original)
        directory = self.repo / "docs/roles"
        moved = self.repo / "original-roles"
        directory.rename(moved)
        directory.symlink_to(moved, target_is_directory=True)
        self.assert_rejected(self.capture)

    def test_fifo_required_input_is_rejected_without_blocking(self) -> None:
        self.seal()
        path = self.repo / "docs/roles/coder.md"
        path.unlink()
        os.mkfifo(path)
        self.assert_rejected(self.capture)

    def test_symlink_marker_is_rejected_even_with_identical_body(self) -> None:
        self.seal()
        path = self.repo / MARKER
        original = path.read_bytes()
        other = self.write(self.base, "marker-copy.json", original)
        path.unlink()
        path.symlink_to(other)
        self.assert_rejected(self.capture)

    def test_unrelated_target_working_changes_are_permitted(self) -> None:
        self.seal()
        (self.repo / "unrelated.txt").write_bytes(b"unrelated work in progress\n")
        self.write(self.repo, "untracked-note.txt", b"unrelated untracked file\n")
        before = filesystem_state(self.base)
        self.assertIsInstance(self.capture(), authority.CandidateAuthoritySnapshot)
        self.assertEqual(filesystem_state(self.base), before)

    def test_wrong_expected_repository_identity_is_rejected(self) -> None:
        self.seal()
        self.assert_rejected(lambda: authority.capture_candidate_snapshot(
            self.repo, expected_repository_id="retired_profile", runtime=self.runtime,
        ))

    def test_preexisting_staged_unrelated_changes_are_permitted_and_preserved(self) -> None:
        self.seal()
        self.write(self.repo, "unrelated.txt", b"unrelated staged work\n")
        git(self.repo, "add", "unrelated.txt")
        before = filesystem_state(self.base)
        snapshot = self.capture()
        self.assertIsInstance(snapshot, authority.CandidateAuthoritySnapshot)
        self.assertEqual(authority.verify_candidate_snapshot(
            snapshot, expected_repository_id="planveyor", runtime=self.runtime), snapshot)
        self.assertEqual(filesystem_state(self.base), before)

    def test_malformed_target_and_runtime_roots_have_machine_readable_errors(self) -> None:
        for name in ("bad\x00root", "bad\ud800root"):
            root = self.base / name
            with self.subTest(root=repr(root)):
                before = filesystem_state(self.base)
                self.assert_rejected(lambda: self.capture(root=root), "root_unavailable")
                self.assert_rejected(lambda: authority.validate_runtime_disk_identity(
                    replace(self.runtime, root=root)), "root_unavailable")
                self.assertEqual(filesystem_state(self.base), before)

    def test_non_git_unborn_and_subdirectory_do_not_become_authority_root(self) -> None:
        non_git = self.base / "non-git"
        non_git.mkdir()
        unborn = self.base / "unborn"
        unborn.mkdir()
        git(unborn, "init", "-q")
        self.seal()
        for root in (non_git, unborn, self.repo / "docs", self.base / "missing"):
            with self.subTest(root=root):
                before = filesystem_state(self.base)
                self.assert_rejected(lambda: self.capture(root))
                self.assertEqual(filesystem_state(self.base), before)

    def test_ambient_git_overrides_do_not_retarget_explicit_repo(self) -> None:
        self.seal()
        expected = self.capture()
        hostile = {
            "GIT_DIR": str(self.runtime_root / ".git"),
            "GIT_WORK_TREE": str(self.runtime_root),
            "GIT_INDEX_FILE": str(self.runtime_root / ".git/index"),
            "GIT_OBJECT_DIRECTORY": str(self.runtime_root / ".git/objects"),
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "core.worktree",
            "GIT_CONFIG_VALUE_0": str(self.runtime_root),
        }
        before = filesystem_state(self.base)
        with mock.patch.dict(os.environ, hostile):
            result = self.capture()
        self.assertEqual(result, expected)
        self.assertEqual(filesystem_state(self.base), before)

    def test_runtime_root_commit_tree_api_and_content_are_bound(self) -> None:
        self.seal()
        invalid = (
            replace(self.runtime, root=self.repo),
            replace(self.runtime, commit="0" * 40),
            replace(self.runtime, tree="0" * 40),
            replace(self.runtime, api_version=3),
            replace(self.runtime, api_version=True),
            replace(self.runtime, executable_inputs=()),
            replace(self.runtime, executable_inputs=(replace(self.runtime.executable_inputs[0], sha256="0" * 64),)),
        )
        for runtime in invalid:
            with self.subTest(runtime=runtime):
                self.assert_rejected(lambda: self.capture(runtime=runtime))

    def test_runtime_content_and_index_drift_are_rejected(self) -> None:
        self.seal()
        path = self.runtime_root / "scripts/engine.py"
        original = path.read_bytes()
        path.write_bytes(original + b"drift\n")
        self.assert_rejected(self.capture)
        git(self.runtime_root, "add", "scripts/engine.py")
        path.write_bytes(original)
        self.assert_rejected(self.capture)

    def test_verify_rejects_target_head_index_and_content_changes(self) -> None:
        self.seal()
        snapshot = self.capture()
        path = self.repo / "docs/roles/coder.md"
        original = path.read_bytes()
        path.write_bytes(original + b"drift\n")
        self.assert_rejected(lambda: authority.verify_candidate_snapshot(
            snapshot, expected_repository_id="planveyor", runtime=self.runtime))
        path.write_bytes(original)
        (self.repo / "unrelated.txt").write_bytes(b"staged unrelated update\n")
        git(self.repo, "add", "unrelated.txt")
        self.assert_rejected(lambda: authority.verify_candidate_snapshot(
            snapshot, expected_repository_id="planveyor", runtime=self.runtime))
        git(self.repo, "commit", "-qm", "new target generation")
        self.assert_rejected(lambda: authority.verify_candidate_snapshot(
            snapshot, expected_repository_id="planveyor", runtime=self.runtime))

    def test_verify_rejects_runtime_revision_change(self) -> None:
        self.seal()
        snapshot = self.capture()
        self.write(self.runtime_root, "new-runtime.txt", b"new runtime revision\n")
        self.commit(self.runtime_root, "new runtime generation")
        new_runtime = self.runtime_identity()
        self.assert_rejected(lambda: authority.verify_candidate_snapshot(
            snapshot, expected_repository_id="planveyor", runtime=new_runtime))

    def _assert_runtime_drift_during_final_target_read(self, operation: str, event: str) -> None:
        self.seal()
        snapshot = self.capture()
        original = authority._git_blob
        index_path = Path(git(self.runtime_root, "rev-parse", "--path-format=absolute",
                              "--git-path", "index").decode().strip())
        before_head = git(self.runtime_root, "rev-parse", "HEAD")
        before_index = index_path.read_bytes()
        target_reads = 0

        def read_and_change(root, blob_oid, *, path):
            nonlocal target_reads
            data = original(root, blob_oid, path=path)
            if root == self.repo and path == "scripts/product_check.py":
                target_reads += 1
                if target_reads == 2:
                    if event == "head":
                        git(self.runtime_root, "commit", "--allow-empty", "-qm", "runtime tail HEAD drift")
                    elif event == "index":
                        self.write(self.runtime_root, "unrelated-runtime.txt", b"runtime tail index drift\n")
                        git(self.runtime_root, "add", "unrelated-runtime.txt")
                    elif event == "body":
                        (self.runtime_root / "scripts/engine.py").write_bytes(b"# runtime tail body drift\n")
                    elif event == "mode":
                        (self.runtime_root / "scripts/engine.py").chmod(0o644)
                    else:
                        self.fail(f"unknown runtime drift event: {event}")
            return data

        reasons = {
            "head": "runtime_commit_mismatch",
            "index": "snapshot_changed_during_read",
            "body": "tracked_path_worktree_bytes_mismatch",
            "mode": "tracked_path_worktree_mode_mismatch",
        }
        call = self.capture if operation == "capture" else lambda: authority.verify_candidate_snapshot(
            snapshot, expected_repository_id="planveyor", runtime=self.runtime)
        with mock.patch.object(authority, "_git_blob", side_effect=read_and_change):
            self.assert_rejected(call, reasons[event])
        self.assertEqual(target_reads, 2)
        if event != "head":
            self.assertEqual(git(self.runtime_root, "rev-parse", "HEAD"), before_head)
        if event in {"body", "mode"}:
            self.assertEqual(index_path.read_bytes(), before_index)
        elif event == "index":
            self.assertNotEqual(index_path.read_bytes(), before_index)

    def test_capture_rejects_runtime_head_drift_during_final_target_read(self) -> None:
        self._assert_runtime_drift_during_final_target_read("capture", "head")

    def test_verify_rejects_runtime_head_drift_during_final_target_read(self) -> None:
        self._assert_runtime_drift_during_final_target_read("verify", "head")

    def test_capture_rejects_runtime_index_drift_during_final_target_read(self) -> None:
        self._assert_runtime_drift_during_final_target_read("capture", "index")

    def test_verify_rejects_runtime_index_drift_during_final_target_read(self) -> None:
        self._assert_runtime_drift_during_final_target_read("verify", "index")

    def test_capture_rejects_runtime_body_drift_during_final_target_read(self) -> None:
        self._assert_runtime_drift_during_final_target_read("capture", "body")

    def test_verify_rejects_runtime_body_drift_during_final_target_read(self) -> None:
        self._assert_runtime_drift_during_final_target_read("verify", "body")

    def test_capture_rejects_runtime_mode_drift_during_final_target_read(self) -> None:
        self._assert_runtime_drift_during_final_target_read("capture", "mode")

    def test_verify_rejects_runtime_mode_drift_during_final_target_read(self) -> None:
        self._assert_runtime_drift_during_final_target_read("verify", "mode")

    def _assert_target_recheck_after_runtime_tail_read(self, operation: str) -> None:
        self.seal()
        snapshot = self.capture()
        original = authority._git_blob
        target_reads = 0
        changed = False

        def read_and_change(root, blob_oid, *, path):
            nonlocal target_reads, changed
            data = original(root, blob_oid, path=path)
            if root == self.repo and path == "scripts/product_check.py":
                target_reads += 1
            elif (root == self.runtime_root and path == "docs/runtime_api.json"
                  and target_reads == 2 and not changed):
                changed = True
                git(self.repo, "commit", "--allow-empty", "-qm", "target changes during runtime recheck")
            return data

        call = self.capture if operation == "capture" else lambda: authority.verify_candidate_snapshot(
            snapshot, expected_repository_id="planveyor", runtime=self.runtime)
        with mock.patch.object(authority, "_git_blob", side_effect=read_and_change):
            self.assert_rejected(call, "snapshot_changed_during_read")
        self.assertEqual(target_reads, 2)
        self.assertTrue(changed)

    def test_capture_rechecks_target_after_runtime_tail_revalidation(self) -> None:
        self._assert_target_recheck_after_runtime_tail_read("capture")

    def test_verify_rechecks_target_after_runtime_tail_revalidation(self) -> None:
        self._assert_target_recheck_after_runtime_tail_read("verify")

    def test_runtime_validation_rejects_head_change_during_last_input_read(self) -> None:
        original = authority._git_blob
        changed = False

        def read_and_change(root, blob_oid, *, path):
            nonlocal changed
            data = original(root, blob_oid, path=path)
            if root == self.runtime_root and path == "docs/runtime_api.json" and not changed:
                changed = True
                git(root, "commit", "--allow-empty", "-qm", "concurrent runtime HEAD change")
            return data

        with mock.patch.object(authority, "_git_blob", side_effect=read_and_change):
            self.assert_rejected(lambda: authority.validate_runtime_disk_identity(self.runtime))
        self.assertTrue(changed)

    def test_runtime_validation_rejects_index_change_during_last_input_read(self) -> None:
        original = authority._git_blob
        changed = False

        def read_and_change(root, blob_oid, *, path):
            nonlocal changed
            data = original(root, blob_oid, path=path)
            if root == self.runtime_root and path == "docs/runtime_api.json" and not changed:
                changed = True
                self.write(root, "unrelated-runtime.txt", b"concurrently staged runtime input\n")
                git(root, "add", "unrelated-runtime.txt")
            return data

        with mock.patch.object(authority, "_git_blob", side_effect=read_and_change):
            self.assert_rejected(lambda: authority.validate_runtime_disk_identity(self.runtime))
        self.assertTrue(changed)

    def test_capture_rejects_head_change_during_last_read_of_second_pass(self) -> None:
        self.seal()
        original = authority._git_blob
        reads = 0

        def read_and_change(root, blob_oid, *, path):
            nonlocal reads
            data = original(root, blob_oid, path=path)
            if root == self.repo and path == "scripts/product_check.py":
                reads += 1
                if reads == 2:
                    git(root, "commit", "--allow-empty", "-qm", "concurrent target HEAD change")
            return data

        with mock.patch.object(authority, "_git_blob", side_effect=read_and_change):
            self.assert_rejected(self.capture)
        self.assertEqual(reads, 2)

    def test_legacy_rejects_head_change_during_last_marker_probe(self) -> None:
        original = authority._marker_worktree_exists_without_head
        probes = 0

        def probe_and_change(root):
            nonlocal probes
            exists = original(root)
            probes += 1
            if probes == 2:
                git(root, "commit", "--allow-empty", "-qm", "concurrent legacy HEAD change")
            return exists

        with mock.patch.object(authority, "_marker_worktree_exists_without_head", side_effect=probe_and_change):
            self.assert_rejected(self.capture)
        self.assertEqual(probes, 2)

    def test_runtime_root_alias_cannot_retarget_a_snapshot_to_an_identical_clone(self) -> None:
        self.seal()
        clone = self.base / "same-commit-clone"
        shutil.copytree(self.runtime_root, clone)
        alias = self.base / "runtime-alias"
        alias.symlink_to(self.runtime_root, target_is_directory=True)
        runtime = replace(self.runtime, root=alias)
        snapshot = self.capture(runtime=runtime)
        self.assertEqual(snapshot.runtime.root, self.runtime_root)
        alias.unlink()
        alias.symlink_to(clone, target_is_directory=True)
        self.assert_rejected(lambda: authority.verify_candidate_snapshot(
            snapshot, expected_repository_id="planveyor", runtime=runtime))

    def test_local_marker_v3_has_exact_live_fields(self) -> None:
        body = {
            "schema_version": 3,
            "source_commit": "a" * 40,
            "repository_id": "planveyor",
            "authority_mode": "target-local",
            "contract_root": ".",
            "required_runtime_api": {"minimum": 5, "maximum": 5},
        }
        marker = authority.parse_local_marker_bytes(json.dumps(body, sort_keys=True).encode("utf-8"))
        self.assertEqual(marker.repository_id, "planveyor")
        self.assertEqual(marker.contract_root, ".")
        self.assertEqual((marker.required_runtime_api.minimum, marker.required_runtime_api.maximum), (5, 5))

    def test_local_marker_v3_rejects_old_and_extra_fields_deterministically(self) -> None:
        v1_body = {
            "schema_version": 1,
            "repository_id": "planveyor",
            "authority_mode": "target-local",
            "contract_root": ".",
            "required_runtime_api": {"minimum": 5, "maximum": 5},
            "closure_manifest": "docs/_meta/contract_sources.v1.json",
            "source_baseline": {"repository_id": "planveyor", "commit": "0" * 40},
        }
        with self.assertRaises(authority.ContractAuthorityError) as v1_error:
            authority.parse_local_marker_bytes(json.dumps(v1_body, sort_keys=True).encode("utf-8"))
        self.assertEqual(v1_error.exception.reason_code, "unsupported_live_marker_schema")

        v2_with_manifest = {
            **{key: value for key, value in v1_body.items() if key not in {"closure_manifest", "source_baseline"}},
            "schema_version": 3,
            "source_commit": "a" * 40,
            "closure_manifest": "docs/_meta/contract_sources.v1.json",
        }
        with self.assertRaises(authority.ContractAuthorityError) as field_error:
            authority.parse_local_marker_bytes(json.dumps(v2_with_manifest, sort_keys=True).encode("utf-8"))
        self.assertEqual(field_error.exception.reason_code, "marker_field_set_invalid")

        for schema_version in (None, "2", True, [], 1, 2):
            with self.subTest(schema_version=repr(schema_version)), self.assertRaises(authority.ContractAuthorityError) as schema_error:
                authority.parse_local_marker_bytes(
                    json.dumps({**v2_with_manifest, "schema_version": schema_version}, sort_keys=True).encode("utf-8")
                )
            self.assertEqual(schema_error.exception.reason_code, "unsupported_live_marker_schema")

    def test_strict_marker_rejects_wrong_types_fields_and_paths(self) -> None:
        changes = [
            ("schema_version", True), ("schema_version", 2),
            ("repository_id", ""), ("authority_mode", "shared"),
            ("contract_root", "../outside"), ("contract_root", "/absolute"),
            ("closure_manifest", "docs//bad.json"), ("closure_manifest", "docs/../bad.json"),
            ("required_runtime_api", {"minimum": True, "maximum": 2}),
            ("required_runtime_api", {"minimum": 2, "maximum": 1}),
            ("required_runtime_api", {"minimum": 1, "maximum": 2, "extra": 0}),
            ("source_baseline", {"repository_id": "planveyor", "commit": "bad"}),
        ]
        for field, value in changes:
            with self.subTest(field=field, value=value):
                marker = copy.deepcopy(self.marker)
                marker[field] = value
                self.assert_rejected(lambda: authority.parse_marker_bytes(json.dumps(marker).encode()))
        marker = copy.deepcopy(self.marker)
        marker["unknown"] = 1
        self.assert_rejected(lambda: authority.parse_marker_bytes(json.dumps(marker).encode()))
        for field in self.marker:
            marker = copy.deepcopy(self.marker)
            del marker[field]
            self.assert_rejected(lambda: authority.parse_marker_bytes(json.dumps(marker).encode()))

    def test_duplicate_json_keys_and_non_json_bytes_are_rejected(self) -> None:
        data = json.dumps(self.marker).encode()
        duplicate = data.replace(b'"schema_version": 1', b'"schema_version": 1, "schema_version": 1')
        for raw in (duplicate, b"[]", b"null", b"\xff", data + b"garbage"):
            with self.subTest(raw=raw[:40]):
                self.assert_rejected(lambda: authority.parse_marker_bytes(raw))

    def test_invalid_unicode_scalars_and_del_are_rejected_before_path_use(self) -> None:
        for invalid in ("bad\ud800text", "bad\udffftext", "bad\x7ftext"):
            for field in ("repository_id", "contract_root", "closure_manifest"):
                with self.subTest(field=field, invalid=repr(invalid)):
                    marker = copy.deepcopy(self.marker)
                    marker[field] = invalid
                    reason = "invalid_text" if field == "repository_id" else "invalid_relative_path"
                    self.assert_rejected(lambda: authority.parse_marker_bytes(json.dumps(marker).encode()), reason)
            marker = copy.deepcopy(self.marker)
            marker["source_baseline"]["repository_id"] = invalid
            self.assert_rejected(lambda: authority.parse_marker_bytes(json.dumps(marker).encode()), "invalid_text")
            manifest = copy.deepcopy(self.manifest)
            manifest["required_content"][0]["path"] = "docs/" + invalid
            self.assert_rejected(lambda: authority.parse_closure_manifest_bytes(json.dumps(manifest).encode()),
                                 "invalid_relative_path")
            runtime = replace(self.runtime, executable_inputs=(
                replace(self.runtime.executable_inputs[0], path="scripts/" + invalid),
            ))
            self.assert_rejected(lambda: authority.validate_runtime_disk_identity(runtime), "invalid_relative_path")

    def test_extreme_json_inputs_preserve_the_machine_readable_error_contract(self) -> None:
        huge_integer = b'"schema_version": ' + b"1" * 5000
        for parser, document in (
            (authority.parse_marker_bytes, self.marker),
            (authority.parse_closure_manifest_bytes, self.manifest),
        ):
            encoded = json.dumps(document).encode()
            oversized = encoded.replace(b'"schema_version": 1', huge_integer)
            deeply_nested = b"[" * 10000 + b"0" + b"]" * 10000
            for raw in (oversized, deeply_nested):
                with self.subTest(parser=parser.__name__, bytes=len(raw)):
                    self.assert_rejected(lambda: parser(raw), "invalid_json" if raw is deeply_nested else None)

    def test_manifest_duplicates_unknown_fields_and_escaping_paths_are_rejected(self) -> None:
        bad = []
        duplicate = copy.deepcopy(self.manifest)
        duplicate["required_content"].append(copy.deepcopy(duplicate["required_content"][0]))
        bad.append(duplicate)
        for path in ("../outside", "/absolute", "docs//bad", "docs/./bad", "docs/roles/"):
            manifest = copy.deepcopy(self.manifest)
            manifest["required_content"][0]["path"] = path
            bad.append(manifest)
        extra = copy.deepcopy(self.manifest)
        extra["required_content"][0]["unknown"] = 1
        bad.append(extra)
        empty = {"schema_version": 1, "required_content": []}
        bad.append(empty)
        for manifest in bad:
            with self.subTest(manifest=manifest):
                self.seal(manifest=manifest)
                self.assert_rejected(self.capture)

    def test_contract_root_constrains_required_content(self) -> None:
        marker = copy.deepcopy(self.marker)
        marker["contract_root"] = "docs"
        self.seal(marker=marker)
        self.assert_rejected(self.capture)

    def test_literal_git_paths_support_spaces_and_unicode(self) -> None:
        name = "docs/roles/кодер notes.md"
        self.write(self.repo, name, b"# precise literal path\n")
        self.commit(self.repo, "literal filename")
        self.manifest["required_content"].append(self.content_row(name))
        self.seal()
        self.assertIsInstance(self.capture(), authority.CandidateAuthoritySnapshot)

    def test_missing_git_executable_fails_without_writes(self) -> None:
        self.seal()
        empty_path = self.base / "empty-path"
        empty_path.mkdir()
        before = filesystem_state(self.base)
        with mock.patch.dict(os.environ, {"PATH": str(empty_path)}):
            self.assert_rejected(self.capture)
        self.assertEqual(filesystem_state(self.base), before)

    def test_external_incomplete_marker_blocks_bundle_content_resolution(self) -> None:
        """B never falls back to tooling bundle bodies after a target marker."""
        try:
            from scripts import build_role_bundles as bundles
            from scripts import contract_authority_context as authority_context
        except ImportError:
            import build_role_bundles as bundles
            import contract_authority_context as authority_context
        self.write(self.repo, "AGENTS.md", b"# Fixture agents\n")
        tooling_root = self.base / "tooling"
        prompt_path = self.write(
            tooling_root,
            "docs/tools/prompts/coder_init.md",
            b"Read docs/roles/coder.md before work.\n",
        )
        for relative_path, body in (
            ("docs/roles/coder.md", b"# Fixture public coder role\n"),
            ("docs/playbooks/docs_architecture.md", b"# Fixture docs architecture\n"),
            ("docs/_meta/plan_vocab.json", b"{}\n"),
            ("docs/_meta/doc_classes.json", b"{}\n"),
        ):
            self.write(tooling_root, relative_path, body)

        def selected_sources():
            previous_cwd = Path.cwd()
            try:
                os.chdir(self.repo)
                context = bundles._build_context(
                    "coder",
                    repo_root=self.repo,
                    tooling_root=tooling_root,
                    repo_profile_id="planveyor",
                    content_profile_id="planveyor",
                    prompt_path=prompt_path,
                    out_dir=self.base / "not-created",
                )
                return (
                    context.prompt_ref, context.role_doc_ref, context.architecture_ref,
                    context.plan_vocab_ref, context.doc_classes_ref,
                )
            finally:
                os.chdir(previous_cwd)

        before = selected_sources()
        self.seal()
        state = filesystem_state(self.base)
        # ``seal()`` writes the historical/candidate v1 marker.  A present
        # physical live marker is parsed only as the v3 local selector.
        expected_reason = "unsupported_live_marker_schema"
        with self.assertRaises(bundles.BuildError) as raised:
            selected_sources()
        self.assertIsInstance(raised.exception.__cause__, authority_context.ContractAuthorityError)
        self.assertEqual(raised.exception.__cause__.reason_code, expected_reason)
        self.assertEqual(before[0].abs_path, prompt_path)
        self.assertEqual(before[3].abs_path, tooling_root / "docs/_meta/plan_vocab.json")
        self.assertEqual(before[4].abs_path, tooling_root / "docs/_meta/doc_classes.json")
        self.assertFalse((self.base / "not-created").exists())
        self.assertEqual(filesystem_state(self.base), state)

    @unittest.skipUnless(shutil.which("zsh"), "zsh required for retained-wrapper proof")
    def test_external_marker_blocks_retained_routes_until_complete_authority_admission(self) -> None:
        """A historical candidate marker is a fail-closed live boundary.

        The fixture deliberately carries the narrow v1 candidate marker.
        Present live markers must use the v2 selector language, so this path
        rejects before any engaged-admission branch or retained route effect.
        """

        env = clean_git_env()
        env["PLANVEYOR_ROOT"] = str(ROOT)
        env["PYBIN"] = os.environ.get("PYBIN", "/usr/bin/python3")
        command = """
source "$PLANVEYOR_ROOT/scripts/planveyor.zsh" || exit
_planveyor_prompt_file_for_role_phase coder init || exit
_planveyor_prompt_file_for_role_phase manager collab_pipeline || exit
_planveyor_doc_template_source_path plans _template.md || exit
planveyor_role_bundle_prompt_manifest architect coder || exit
planveyor_session() { print -r -- "fixture-manager-sid"; }
_planveyor_codex() { print -rl -- "$@"; }
planveyor_manager_resume
"""
        def run():
            return subprocess.run(["zsh", "-f", "-c", command], cwd=self.repo, env=env, capture_output=True, text=True, timeout=30)
        before = run()
        self.assertEqual(before.returncode, 0, before.stderr)
        self.seal()
        state = filesystem_state(self.base)
        after = run()
        # This is the historical/candidate v1 fixture, so the live reader
        # rejects it before the engaged-admission branch.
        expected_reason = "unsupported_live_marker_schema"
        self.assertNotEqual(after.returncode, 0)
        self.assertIn(f"contract_authority_bridge: {expected_reason}:", after.stderr)
        self.assertEqual(after.stdout, "")
        self.assertEqual(filesystem_state(self.base), state)


if __name__ == "__main__":
    unittest.main()

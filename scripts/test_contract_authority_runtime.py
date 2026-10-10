from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError, replace
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

try:
    from scripts import contract_authority_runtime as runtime
except ImportError:
    import contract_authority_runtime as runtime


FIXTURE_REQUIRED_RUNTIME_PATHS = (
    "docs/_meta/runner_selection_resolution.v1.json",
    "scripts/planveyor.zsh",
    "scripts/planveyor/docs_finalize.zsh",
    "scripts/planveyor/role_runtime.zsh",
    "scripts/planveyor/session_init.zsh",
    "scripts/contract_authority_snapshot.py",
    "scripts/fs_object_identity.py",
    "scripts/contract_authority_runtime.py",
    "scripts/contract_authority_context.py",
    "scripts/contract_authority_bootstrap.py",
    "scripts/contract_authority_shell_loader.zsh",
    "scripts/contract_authority_bridge.py",
    "scripts/planveyor/contract_authority.zsh",
)


def clean_git_env() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_OPTIONAL_LOCKS": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    return env


def git(root: Path, *args: str, input_data: bytes | None = None) -> bytes:
    completed = subprocess.run(
        [
            "git",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "commit.gpgsign=false",
            "-C",
            os.fspath(root),
            *args,
        ],
        check=False,
        input=input_data,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=clean_git_env(),
    )
    if completed.returncode != 0:
        raise AssertionError(f"fixture Git command failed: {args!r}")
    return completed.stdout


class RuntimePinTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="planveyor-runtime-pin-")
        self.base = Path(self.tmp.name).resolve()
        self.repo = self.make_runtime_repo("runtime")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def make_runtime_repo(self, name: str) -> Path:
        root = self.base / name
        root.mkdir()
        git(root, "init", "-q")
        git(root, "config", "user.name", "Runtime Fixture")
        git(root, "config", "user.email", 'runtime-fixture' + '@' + 'example' + '.' + 'invalid')
        git(root, "config", "core.filemode", "true")
        for relative in FIXTURE_REQUIRED_RUNTIME_PATHS:
            self.write(root, relative, f"fixture required: {relative}\n".encode())
        self.write(root, "scripts/README.md", b"runtime fixture documentation\n")
        self.write(root, "scripts/alpha.py", b"print('alpha')\n", mode=0o755)
        self.write(root, "scripts/nested/raw.bin", b"\x00\xffraw\n")
        self.write(root, "private_shell/fixed-family.zsh", b"private family fixture\n")
        # This is a tracked contract-document lookalike, deliberately excluded
        # from the runtime closure selection rule.
        self.write(root, "docs/tools/prompts/hostile-contract.md", b"outside runtime pin\n")
        self.commit(root, "runtime fixture")
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

    def assert_rejected(self, call, reason_code: str | None = None) -> None:
        with self.assertRaises(runtime.ContractAuthorityError) as caught:
            call()
        self.assertTrue(caught.exception.reason_code)
        if reason_code is not None:
            self.assertEqual(caught.exception.reason_code, reason_code)

    def closure_paths(self, root: Path) -> tuple[str, ...]:
        script_paths = tuple(
            line
            for line in git(root, "ls-tree", "-r", "--name-only", "HEAD", "--", "scripts")
            .decode("utf-8")
            .splitlines()
            if line
        )
        templates = tuple(
            path for path in FIXTURE_REQUIRED_RUNTIME_PATHS if not path.startswith("scripts/")
        )
        return tuple(sorted((*script_paths, *templates)))

    def test_capture_enumerates_complete_closure_and_is_immutable(self) -> None:
        before_status = git(self.repo, "status", "--porcelain=v1", "--untracked-files=all")
        pin = runtime.capture_loaded_runtime_pin(self.repo)

        self.assertEqual(runtime.RUNTIME_API_VERSION, 5)
        self.assertEqual(runtime.REQUIRED_RUNTIME_PATHS, tuple(sorted(FIXTURE_REQUIRED_RUNTIME_PATHS)))
        self.assertEqual(pin.runtime_root, self.repo)
        self.assertTrue(pin.git_dir.is_absolute())
        self.assertEqual(tuple(row.path for row in pin.closure_rows), self.closure_paths(self.repo))
        self.assertNotIn("docs/tools/prompts/hostile-contract.md", {row.path for row in pin.closure_rows})
        self.assertEqual(pin.closure_spec_sha256, runtime.RUNTIME_CLOSURE_SPEC_SHA256)
        self.assertEqual(pin.closure_rows_sha256, runtime._closure_rows_digest(pin.closure_rows))
        self.assertEqual(pin.closure_sha256, runtime._closure_digest(
            closure_spec_sha256=pin.closure_spec_sha256,
            closure_rows_sha256=pin.closure_rows_sha256,
        ))
        self.assertEqual(pin.pin_sha256, runtime._pin_digest(pin))
        raw = self.repo / "scripts/nested/raw.bin"
        raw_row = next(row for row in pin.closure_rows if row.path == "scripts/nested/raw.bin")
        self.assertEqual(raw_row.blob_oid, git(self.repo, "rev-parse", "HEAD:scripts/nested/raw.bin").decode().strip())
        self.assertEqual(raw_row.sha256, hashlib.sha256(raw.read_bytes()).hexdigest())
        with self.assertRaises(FrozenInstanceError):
            pin.commit = "0" * 40
        self.assertEqual(runtime.verify_loaded_runtime_pin(pin), pin)
        self.assertEqual(
            git(self.repo, "status", "--porcelain=v1", "--untracked-files=all"),
            before_status,
        )

    def test_descriptor_reads_cover_every_closure_row_without_cat_file(self) -> None:
        descriptor_paths: set[str] = set()
        git_commands: list[tuple[str, ...]] = []
        real_snapshot = runtime.snapshot_regular_or_absent
        real_run = runtime.subprocess.run

        def record_snapshot(root: Path, relative: str, **kwargs):
            if root == self.repo:
                descriptor_paths.add(relative)
            return real_snapshot(root, relative, **kwargs)

        def record_run(command, *args, **kwargs):
            git_commands.append(tuple(command))
            return real_run(command, *args, **kwargs)

        with (
            mock.patch.object(runtime, "snapshot_regular_or_absent", side_effect=record_snapshot),
            mock.patch.object(runtime.subprocess, "run", side_effect=record_run),
        ):
            pin = runtime.capture_loaded_runtime_pin(self.repo)

        self.assertTrue({row.path for row in pin.closure_rows}.issubset(descriptor_paths))
        self.assertFalse(any("cat-file" in command for command in git_commands))

    def test_serialization_is_strict_and_row_digest_is_canonical(self) -> None:
        pin = runtime.capture_loaded_runtime_pin(self.repo)
        payload = runtime.loaded_runtime_pin_to_dict(pin)
        self.assertEqual(runtime.loaded_runtime_pin_from_dict(payload), pin)
        self.assertEqual(runtime.loaded_runtime_pin_from_dict(payload).observed_index_sha256, pin.observed_index_sha256)
        self.assertEqual(
            runtime._closure_rows_digest(tuple(reversed(pin.closure_rows))),
            pin.closure_rows_sha256,
        )

        reordered = copy.deepcopy(payload)
        reordered["closure_rows"] = list(reversed(reordered["closure_rows"]))
        self.assert_rejected(
            lambda: runtime.loaded_runtime_pin_from_dict(reordered),
            "runtime_pin_rows_not_canonical",
        )
        malformed = copy.deepcopy(payload)
        malformed["extra"] = True
        self.assert_rejected(
            lambda: runtime.loaded_runtime_pin_from_dict(malformed),
            "runtime_pin_schema_invalid",
        )

    def test_same_pin_verifies_but_different_root_or_commit_does_not(self) -> None:
        pin = runtime.capture_loaded_runtime_pin(self.repo)
        self.assertEqual(runtime.verify_loaded_runtime_pin(pin), pin)

        api_one = replace(pin, runtime_api_version=1, pin_sha256="")
        api_one = replace(api_one, pin_sha256=runtime._pin_digest(api_one))
        self.assertEqual(api_one.pin_sha256, runtime._pin_digest(api_one))
        self.assert_rejected(lambda: runtime.verify_loaded_runtime_pin(api_one), "runtime_api_mismatch")

        other = self.make_runtime_repo("other-runtime")
        other_pin = runtime.capture_loaded_runtime_pin(other)
        self.assertNotEqual(pin.runtime_root, other_pin.runtime_root)
        self.assertNotEqual(pin.pin_sha256, other_pin.pin_sha256)

        self.write(self.repo, "scripts/alpha.py", b"print('changed commit')\n", mode=0o755)
        self.commit(self.repo, "runtime change")
        self.assert_rejected(lambda: runtime.verify_loaded_runtime_pin(pin), "runtime_pin_mismatch")

    def test_unrelated_docs_staging_does_not_invalidate_a_stable_pin(self) -> None:
        pin = runtime.capture_loaded_runtime_pin(self.repo)
        self.write(self.repo, "docs/unrelated-staged.md", b"not a runtime input\n")
        git(self.repo, "add", "docs/unrelated-staged.md")
        current = runtime.verify_loaded_runtime_pin(pin)
        self.assertEqual(current, pin)
        self.assertEqual(current.pin_sha256, pin.pin_sha256)
        self.assertNotEqual(current.observed_index_sha256, pin.observed_index_sha256)
        self.assertEqual(runtime.loaded_runtime_pin_to_dict(pin)["observed_index_sha256"], pin.observed_index_sha256)

    def test_staged_new_closure_path_is_rejected(self) -> None:
        self.write(self.repo, "scripts/new_runtime_input.py", b"print('new')\n")
        git(self.repo, "add", "scripts/new_runtime_input.py")
        self.assert_rejected(
            lambda: runtime.capture_loaded_runtime_pin(self.repo),
            "runtime_closure_index_only",
        )

    def test_required_shell_loader_cannot_be_deleted(self) -> None:
        (self.repo / "scripts/contract_authority_shell_loader.zsh").unlink()
        self.assert_rejected(
            lambda: runtime.capture_loaded_runtime_pin(self.repo),
            "runtime_closure_missing_from_worktree",
        )

    def test_runner_policy_is_required_and_cannot_drift(self) -> None:
        relative = "docs/_meta/runner_selection_resolution.v1.json"
        cases = (
            ("missing", "runtime_closure_missing_from_worktree"),
            ("staged", "runtime_closure_index_mismatch"),
            ("dirty", "runtime_closure_worktree_blob_mismatch"),
            ("mode", "runtime_closure_worktree_mode_mismatch"),
            ("committed-removal", "runtime_closure_missing_required"),
        )
        for name, expected in cases:
            with self.subTest(name=name):
                root = self.make_runtime_repo(f"policy-{name}")
                pin = runtime.capture_loaded_runtime_pin(root)
                path = root / relative
                original = path.read_bytes()
                if name in {"missing", "committed-removal"}:
                    path.unlink()
                    if name == "committed-removal":
                        self.commit(root, "remove runtime policy")
                elif name == "staged":
                    path.write_bytes(b"different runner policy\n")
                    git(root, "add", relative)
                    path.write_bytes(original)
                elif name == "dirty":
                    path.write_bytes(b"different runner policy\n")
                else:
                    path.chmod(0o755)
                before = git(root, "status", "--porcelain=v1", "--untracked-files=all")
                self.assert_rejected(lambda: runtime.capture_loaded_runtime_pin(root), expected)
                self.assert_rejected(lambda: runtime.verify_loaded_runtime_pin(pin))
                self.assertEqual(git(root, "status", "--porcelain=v1", "--untracked-files=all"), before)

    def test_deleted_staged_dirty_and_mode_rows_are_rejected(self) -> None:
        cases = (
            ("deleted", "runtime_closure_missing_from_worktree"),
            ("staged", "runtime_closure_index_mismatch"),
            ("dirty", "runtime_closure_worktree_blob_mismatch"),
            ("mode", "runtime_closure_worktree_mode_mismatch"),
        )
        for name, expected in cases:
            with self.subTest(name=name):
                root = self.make_runtime_repo(f"case-{name}")
                path = root / "scripts/alpha.py"
                original = path.read_bytes()
                if name == "deleted":
                    path.unlink()
                elif name == "staged":
                    path.write_bytes(b"staged change\n")
                    git(root, "add", "scripts/alpha.py")
                    path.write_bytes(original)
                    path.chmod(0o755)
                elif name == "dirty":
                    path.write_bytes(b"dirty change\n")
                else:
                    path.chmod(0o644)
                self.assert_rejected(lambda root=root: runtime.capture_loaded_runtime_pin(root), expected)

    def test_symlink_and_tracked_nonregular_rows_are_rejected(self) -> None:
        path = self.repo / "scripts/alpha.py"
        path.unlink()
        path.symlink_to("nested/raw.bin")
        self.assert_rejected(lambda: runtime.capture_loaded_runtime_pin(self.repo), "symlink_forbidden")

        root = self.make_runtime_repo("git-symlink")
        link = root / "scripts/tracked-link.py"
        link.symlink_to("alpha.py")
        self.commit(root, "tracked symlink")
        self.assert_rejected(
            lambda: runtime.capture_loaded_runtime_pin(root),
            "runtime_closure_non_regular",
        )

    def test_unmerged_index_row_is_rejected(self) -> None:
        path = "scripts/alpha.py"
        oid = git(self.repo, "rev-parse", f"HEAD:{path}").decode("ascii").strip()
        git(self.repo, "update-index", "--force-remove", path)
        git(
            self.repo,
            "update-index",
            "--index-info",
            input_data=f"100755 {oid} 1\t{path}\n".encode("ascii"),
        )
        self.assert_rejected(
            lambda: runtime.capture_loaded_runtime_pin(self.repo),
            "runtime_closure_unmerged",
        )

    def test_raw_index_drift_during_observation_and_between_observations_is_rejected(self) -> None:
        original_snapshot = runtime.snapshot_regular_or_absent
        changed = False

        def mutate_after_descriptor(root: Path, relative: str, **kwargs):
            nonlocal changed
            observed = original_snapshot(root, relative, **kwargs)
            if root == self.repo and relative == "scripts/alpha.py" and not changed:
                changed = True
                git(self.repo, "update-index", "--assume-unchanged", relative)
            return observed

        try:
            with mock.patch.object(runtime, "snapshot_regular_or_absent", side_effect=mutate_after_descriptor):
                self.assert_rejected(
                    lambda: runtime.capture_loaded_runtime_pin(self.repo),
                    "snapshot_changed_during_read",
                )
        finally:
            git(self.repo, "update-index", "--no-assume-unchanged", "scripts/alpha.py")

        original_once = runtime._capture_loaded_runtime_pin_once
        calls = 0

        def mutate_between_observations(root: Path):
            nonlocal calls
            result = original_once(root)
            if calls == 0:
                git(self.repo, "update-index", "--assume-unchanged", "scripts/alpha.py")
            calls += 1
            return result

        try:
            with mock.patch.object(runtime, "_capture_loaded_runtime_pin_once", side_effect=mutate_between_observations):
                self.assert_rejected(
                    lambda: runtime.capture_loaded_runtime_pin(self.repo),
                    "snapshot_changed_during_capture",
                )
        finally:
            git(self.repo, "update-index", "--no-assume-unchanged", "scripts/alpha.py")

    def test_timeout_has_a_stable_typed_error(self) -> None:
        timeout = subprocess.TimeoutExpired(["git"], runtime.GIT_COMMAND_TIMEOUT_SECONDS)
        with mock.patch.object(runtime.subprocess, "run", side_effect=timeout):
            self.assert_rejected(
                lambda: runtime.capture_loaded_runtime_pin(self.repo),
                "git_timeout",
            )

    def test_batched_basis_preserves_detached_worktree_index_identity(self) -> None:
        linked = self.base / "detached runtime with spaces"
        git(self.repo, "worktree", "add", "--quiet", "--detach", str(linked), "HEAD")
        pin = runtime.capture_loaded_runtime_pin(linked)
        expected_dir = Path(git(linked, "rev-parse", "--absolute-git-dir").decode().strip())
        expected_index = Path(git(
            linked, "rev-parse", "--path-format=absolute", "--git-path", "index"
        ).decode().strip())

        self.assertEqual(pin.runtime_root, linked)
        self.assertEqual(pin.git_dir, expected_dir)
        self.assertNotEqual(pin.git_dir, self.repo / ".git")
        self.assertEqual(pin.commit, git(linked, "rev-parse", "--verify", "HEAD^{commit}").decode().strip())
        self.assertEqual(pin.tree, git(linked, "rev-parse", "--verify", "HEAD^{tree}").decode().strip())
        self.assertEqual(pin.observed_index_sha256, hashlib.sha256(expected_index.read_bytes()).hexdigest())
        self.assertEqual(runtime.verify_loaded_runtime_pin(pin), pin)

    def test_batched_basis_rejects_ambiguous_or_unsafe_metadata(self) -> None:
        basis = runtime._capture_git_basis(self.repo)
        fields = ["true", str(self.repo), str(basis.git_dir), str(basis.git_dir / "index"), basis.head, basis.tree]
        valid = ("\n".join(fields) + "\n").encode()
        malformed = {
            "extra_record": valid + b"unexpected\n",
            "missing_record": ("\n".join(fields[:-1]) + "\n").encode(),
            "unterminated": valid[:-1],
            "non_utf8": valid.replace(b"true", b"\xff", 1),
            "nul": valid.replace(b"true", b"true\x00", 1),
        }
        for label, field, replacement in (
            ("outside_worktree", 0, "false"),
            ("relative_root", 1, "runtime"),
            ("wrong_root", 1, str(self.base)),
            ("relative_gitdir", 2, ".git"),
            ("relative_index", 3, "index"),
            ("outside_index", 3, str(self.base / "index")),
            ("wrong_index_leaf", 3, str(basis.git_dir / "index-retained")),
            ("invalid_head", 4, "HEAD^{commit}"),
            ("invalid_tree", 5, "g" * 40),
        ):
            changed = fields.copy()
            changed[field] = replacement
            malformed[label] = ("\n".join(changed) + "\n").encode()

        for label, output in malformed.items():
            with self.subTest(case=label), mock.patch.object(runtime, "_run_git", return_value=output):
                self.assert_rejected(lambda: runtime._capture_git_basis(self.repo))

    def test_batched_basis_rejects_unborn_head_and_missing_or_symlinked_index(self) -> None:
        unborn = self.base / "unborn"
        unborn.mkdir()
        git(unborn, "init", "--quiet")
        self.assert_rejected(lambda: runtime._capture_git_basis(unborn))

        index = self.repo / ".git" / "index"
        retained_index = index.with_name("index-retained")
        index.rename(retained_index)
        self.assert_rejected(lambda: runtime._capture_git_basis(self.repo), "index_missing")
        index.symlink_to(retained_index.name)
        self.assert_rejected(lambda: runtime._capture_git_basis(self.repo), "symlink_forbidden")

    def test_git_subprocess_count_is_bounded_independent_of_closure_size(self) -> None:
        def capture_count() -> tuple[int, tuple[tuple[str, ...], ...]]:
            calls: list[tuple[str, ...]] = []
            real_run = runtime.subprocess.run

            def record(command, *args, **kwargs):
                calls.append(tuple(command))
                return real_run(command, *args, **kwargs)

            with mock.patch.object(runtime.subprocess, "run", side_effect=record):
                runtime.capture_loaded_runtime_pin(self.repo)
            return len(calls), tuple(calls)

        small_count, small_calls = capture_count()
        for index in range(128):
            self.write(self.repo, f"scripts/generated/item-{index:03d}.py", f"#{index}\n".encode())
        self.commit(self.repo, "large runtime closure")
        large_count, large_calls = capture_count()

        self.assertEqual(large_count, small_count)
        self.assertLessEqual(large_count, 8)
        self.assertFalse(any("cat-file" in command for command in (*small_calls, *large_calls)))
        self.assertEqual(sum("ls-tree" in command for command in large_calls), 2)
        self.assertEqual(sum("ls-files" in command for command in large_calls), 2)
        self.assertEqual(sum("rev-parse" in command for command in large_calls), 4)

    def test_capture_tracked_content_is_batched_and_exact(self) -> None:
        paths = (
            "scripts/nested/raw.bin",
            "private_shell/fixed-family.zsh",
        )
        git_identity, rows = runtime.capture_tracked_content(self.repo, tuple(reversed(paths)))
        self.assertIsInstance(git_identity, runtime.GitIdentity)
        self.assertEqual(git_identity.root, self.repo)
        self.assertEqual(tuple(row.path for row in rows), tuple(sorted(paths)))
        self.assertEqual(
            rows[0].blob_oid,
            git(self.repo, "rev-parse", "HEAD:" + rows[0].path).decode().strip(),
        )
        self.assert_rejected(
            lambda: runtime.capture_tracked_content(self.repo, (paths[0], paths[0])),
            "duplicate_tracked_content_path",
        )
        self.write(self.repo, paths[0], b"dirty target row\n")
        self.assert_rejected(
            lambda: runtime.capture_tracked_content(self.repo, paths),
            "runtime_closure_worktree_blob_mismatch",
        )


class AuthorityNamespaceImportTests(unittest.TestCase):
    def test_repeated_local_namespace_paths_preserve_alias_identity_without_admitting_foreign_paths(self) -> None:
        scripts_dir = Path(__file__).resolve().parent
        probe = """
import importlib, pathlib, sys, types
scripts_dir = pathlib.Path(sys.argv[1]).resolve()
foreign_dir = pathlib.Path(sys.argv[2]).resolve()
local_only = sys.argv[3] == "local"
sys.path.insert(0, str(scripts_dir))
package = types.ModuleType("scripts")
package.__path__ = [str(scripts_dir), str(scripts_dir if local_only else foreign_dir)]
sys.modules["scripts"] = package
direct = importlib.import_module("fs_object_identity")
try:
    packaged = importlib.import_module("scripts.fs_object_identity")
except ImportError:
    assert not local_only, "duplicate local namespace paths split the trusted import"
else:
    assert local_only, "foreign namespace path was admitted as a local authority package"
    assert packaged is direct, "the package import created a second authority identity"
    assert packaged.ObjectIdentityError is direct.ObjectIdentityError
"""
        with tempfile.TemporaryDirectory(prefix="authority-namespace-") as temporary:
            foreign = Path(temporary) / "scripts"
            foreign.mkdir()
            for mode in ("local", "foreign"):
                with self.subTest(namespace=mode):
                    result = subprocess.run(
                        [sys.executable, "-B", "-X", "pycache_prefix=" + os.devnull,
                         "-c", probe, str(scripts_dir), str(foreign), mode],
                        env=clean_git_env(), capture_output=True, text=True,
                        check=False, timeout=20,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

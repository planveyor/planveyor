from __future__ import annotations

import errno
import os
import stat
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest import mock

from scripts import fs_object_identity as identity


class ObjectIdentitySnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory(prefix="planveyor-object-identity-")
        self.root = Path(self.tempdir.name)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def write_file(
        self,
        relative_path: str,
        data: bytes = b"payload",
        *,
        mode: int = 0o600,
    ) -> Path:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        path.chmod(mode)
        return path

    def assert_reason(self, reason_code: str, callable_: object) -> identity.ObjectIdentityError:
        with self.assertRaises(identity.ObjectIdentityError) as caught:
            callable_()  # type: ignore[operator]
        self.assertEqual(caught.exception.reason_code, reason_code)
        return caught.exception

    def test_regular_snapshot_is_immutable_and_uses_only_declared_stages(self) -> None:
        target = self.write_file("nested/target.txt", b"stable")
        stages: list[str] = []

        snapshot = identity.snapshot_regular_or_absent(
            self.root,
            "nested/target.txt",
            _observer=stages.append,
        )

        target_stat = target.stat()
        self.assertEqual(snapshot.relative_path, "nested/target.txt")
        self.assertEqual(snapshot.state, "regular")
        self.assertEqual(snapshot.data, b"stable")
        self.assertEqual(snapshot.git_mode, "100644")
        self.assertNotIsInstance(snapshot.git_mode, int)
        self.assertEqual(snapshot.st_dev, target_stat.st_dev)
        self.assertEqual(snapshot.st_ino, target_stat.st_ino)
        self.assertEqual(snapshot.st_size, len(b"stable"))
        self.assertEqual(snapshot.st_mtime_ns, target_stat.st_mtime_ns)
        self.assertEqual(
            stages,
            ["after_ancestor_chain_opened", "after_leaf_read"],
        )
        with self.assertRaises(FrozenInstanceError):
            snapshot.state = "absent"  # type: ignore[misc]

    def test_git_mode_uses_owner_execute_bit_and_string_values(self) -> None:
        cases = (
            ("owner-executable", 0o700, "100755"),
            ("not-executable", 0o600, "100644"),
            ("group-only", 0o610, "100644"),
            ("other-only", 0o601, "100644"),
        )
        for name, mode, expected in cases:
            with self.subTest(name=name):
                self.write_file(name, mode=mode)
                snapshot = identity.snapshot_regular_or_absent(self.root, name)
                self.assertEqual(snapshot.git_mode, expected)
                self.assertIsInstance(snapshot.git_mode, str)

    def test_absent_requires_two_observations_under_one_parent(self) -> None:
        (self.root / "nested").mkdir()
        stages: list[str] = []

        snapshot = identity.snapshot_regular_or_absent(
            self.root,
            "nested/missing.txt",
            _observer=stages.append,
        )

        self.assertEqual(snapshot.state, "absent")
        self.assertIsNone(snapshot.data)
        self.assertIsNone(snapshot.git_mode)
        self.assertIsNone(snapshot.st_dev)
        self.assertIsNone(snapshot.st_ino)
        self.assertIsNone(snapshot.st_size)
        self.assertIsNone(snapshot.st_mtime_ns)
        self.assertEqual(
            stages,
            ["after_ancestor_chain_opened", "after_absence_observed"],
        )

    def test_invalid_relative_paths_fail_closed(self) -> None:
        invalid = (
            "",
            "/absolute",
            "trailing/",
            "double//segment",
            ".",
            "..",
            "a/./b",
            "a/../b",
            r"platform\dependent",
            "nul\x00byte",
        )
        for relative_path in invalid:
            with self.subTest(relative_path=relative_path):
                self.assert_reason(
                    "invalid_relative_path",
                    lambda path=relative_path: identity.snapshot_regular_or_absent(
                        self.root,
                        path,
                    ),
                )

    def test_unsafe_trusted_root_fails_closed(self) -> None:
        file_root = self.write_file("not-a-directory")
        self.assert_reason(
            "unsafe_trusted_root",
            lambda: identity.snapshot_regular_or_absent(file_root, "leaf"),
        )

        real_root = self.root / "real-root"
        real_root.mkdir()
        alias_root = self.root / "alias-root"
        alias_root.symlink_to(real_root, target_is_directory=True)
        self.assert_reason(
            "unsafe_trusted_root",
            lambda: identity.snapshot_regular_or_absent(alias_root, "leaf"),
        )

    def test_missing_and_non_directory_ancestors_are_not_absent(self) -> None:
        self.assert_reason(
            "ancestor_missing",
            lambda: identity.snapshot_regular_or_absent(
                self.root,
                "missing/leaf",
            ),
        )
        self.write_file("plain")
        self.assert_reason(
            "ancestor_not_directory",
            lambda: identity.snapshot_regular_or_absent(
                self.root,
                "plain/leaf",
            ),
        )

    def test_static_ancestor_and_leaf_symlinks_are_forbidden(self) -> None:
        real_dir = self.root / "real"
        real_dir.mkdir()
        (real_dir / "leaf").write_bytes(b"data")
        (self.root / "ancestor-alias").symlink_to(real_dir, target_is_directory=True)
        self.assert_reason(
            "symlink_forbidden",
            lambda: identity.snapshot_regular_or_absent(
                self.root,
                "ancestor-alias/leaf",
            ),
        )

        self.write_file("target")
        (self.root / "leaf-alias").symlink_to("target")
        self.assert_reason(
            "symlink_forbidden",
            lambda: identity.snapshot_regular_or_absent(
                self.root,
                "leaf-alias",
            ),
        )

    def test_non_regular_leaves_are_rejected_before_open(self) -> None:
        (self.root / "directory-leaf").mkdir()
        self.assert_reason(
            "leaf_not_regular",
            lambda: identity.snapshot_regular_or_absent(
                self.root,
                "directory-leaf",
            ),
        )

        fifo = self.root / "fifo-leaf"
        os.mkfifo(fifo)
        self.assert_reason(
            "leaf_not_regular",
            lambda: identity.snapshot_regular_or_absent(
                self.root,
                "fifo-leaf",
            ),
        )

    def test_regular_to_fifo_replacement_is_nonblocking_and_not_retried(self) -> None:
        target = self.write_file("parent/leaf", b"regular")
        detached = self.root / "detached-leaf"
        real_open = os.open
        open_calls: list[tuple[object, int, int | None]] = []
        leaf_open_attempts = 0
        stages: list[str] = []

        def replace_before_real_leaf_open(
            path: object,
            flags: int,
            mode: int = 0o777,
            *,
            dir_fd: int | None = None,
        ) -> int:
            nonlocal leaf_open_attempts
            open_calls.append((path, flags, dir_fd))
            is_leaf_open = (
                path == "leaf"
                and dir_fd is not None
                and not flags & os.O_DIRECTORY
            )
            if is_leaf_open:
                leaf_open_attempts += 1
                self.assertTrue(
                    flags & os.O_NONBLOCK,
                    "leaf open must fail quickly if regular entry became FIFO",
                )
                if leaf_open_attempts == 1:
                    os.rename(target, detached)
                    os.mkfifo(target)
            return real_open(path, flags, mode, dir_fd=dir_fd)  # type: ignore[arg-type]

        with (
            mock.patch.object(identity, "_capabilities_supported", return_value=True),
            mock.patch.object(
                identity.os,
                "open",
                side_effect=replace_before_real_leaf_open,
            ),
        ):
            self.assert_reason(
                "leaf_identity_changed",
                lambda: identity.snapshot_regular_or_absent(
                    self.root,
                    "parent/leaf",
                    _observer=stages.append,
                ),
            )

        directory_flags = [
            flags
            for _, flags, _ in open_calls
            if flags & os.O_DIRECTORY
        ]
        leaf_flags = [
            flags
            for path, flags, dir_fd in open_calls
            if path == "leaf"
            and dir_fd is not None
            and not flags & os.O_DIRECTORY
        ]
        self.assertEqual(len(directory_flags), 2)
        self.assertTrue(all(not flags & os.O_NONBLOCK for flags in directory_flags))
        self.assertEqual(len(leaf_flags), 1)
        self.assertTrue(leaf_flags[0] & os.O_NONBLOCK)
        self.assertEqual(leaf_open_attempts, 1)
        self.assertTrue(stat.S_ISFIFO(target.stat().st_mode))
        self.assertEqual(stages, ["after_ancestor_chain_opened"])

    def test_ancestor_replacement_is_detected_from_retained_chain(self) -> None:
        original = self.write_file("parent/leaf", b"original")
        del original
        stages: list[str] = []

        def replace(stage: str) -> None:
            stages.append(stage)
            if stage != "after_ancestor_chain_opened":
                return
            os.rename(self.root / "parent", self.root / "detached-parent")
            self.write_file("parent/leaf", b"replacement")

        self.assert_reason(
            "ancestor_identity_changed",
            lambda: identity.snapshot_regular_or_absent(
                self.root,
                "parent/leaf",
                _observer=replace,
            ),
        )
        self.assertEqual(stages, ["after_ancestor_chain_opened", "after_leaf_read"])

    def test_same_content_leaf_replacement_rejects_readable_detached_fd(self) -> None:
        self.write_file("leaf", b"identical")
        stages: list[str] = []

        def replace(stage: str) -> None:
            stages.append(stage)
            if stage != "after_leaf_read":
                return
            os.rename(self.root / "leaf", self.root / "detached-leaf")
            self.write_file("leaf", b"identical")

        self.assert_reason(
            "leaf_identity_changed",
            lambda: identity.snapshot_regular_or_absent(
                self.root,
                "leaf",
                _observer=replace,
            ),
        )
        self.assertEqual(
            stages,
            ["after_ancestor_chain_opened", "after_leaf_read"],
        )

    def test_appearing_leaf_after_absence_fails_without_retry(self) -> None:
        stages: list[str] = []

        def create(stage: str) -> None:
            stages.append(stage)
            if stage == "after_absence_observed":
                self.write_file("leaf", b"appeared")

        self.assert_reason(
            "leaf_identity_changed",
            lambda: identity.snapshot_regular_or_absent(
                self.root,
                "leaf",
                _observer=create,
            ),
        )
        self.assertEqual(
            stages,
            ["after_ancestor_chain_opened", "after_absence_observed"],
        )

    def test_detectable_same_inode_metadata_drift_is_rejected(self) -> None:
        target = self.write_file("leaf", b"before")
        original_ino = target.stat().st_ino

        def mutate(stage: str) -> None:
            if stage == "after_leaf_read":
                target.write_bytes(b"longer-after")

        self.assert_reason(
            "leaf_content_metadata_changed",
            lambda: identity.snapshot_regular_or_absent(
                self.root,
                "leaf",
                _observer=mutate,
            ),
        )
        self.assertEqual(target.stat().st_ino, original_ino)

    def test_same_inode_equal_metadata_hostile_write_is_declared_excluded(self) -> None:
        target = self.write_file("leaf", b"before")
        before = target.stat()

        def mutate_and_restore_declared_metadata(stage: str) -> None:
            if stage != "after_leaf_read":
                return
            target.write_bytes(b"after!")
            target.chmod(stat.S_IMODE(before.st_mode))
            os.utime(
                target,
                ns=(before.st_atime_ns, before.st_mtime_ns),
                follow_symlinks=False,
            )

        snapshot = identity.snapshot_regular_or_absent(
            self.root,
            "leaf",
            _observer=mutate_and_restore_declared_metadata,
        )

        self.assertEqual(snapshot.state, "regular")
        self.assertEqual(snapshot.data, b"before")
        self.assertEqual(target.read_bytes(), b"after!")
        self.assertEqual(target.stat().st_ino, before.st_ino)

    def test_capability_failure_has_no_weaker_fallback(self) -> None:
        self.write_file("leaf")
        with mock.patch.object(identity, "_capabilities_supported", return_value=False):
            self.assert_reason(
                "unsupported_capability",
                lambda: identity.snapshot_regular_or_absent(
                    self.root,
                    "leaf",
                ),
            )
        with mock.patch.object(identity.os, "O_NONBLOCK", 0):
            self.assert_reason(
                "unsupported_capability",
                lambda: identity.snapshot_regular_or_absent(
                    self.root,
                    "leaf",
                ),
            )

    def test_ambiguous_stat_failure_is_not_treated_as_absent(self) -> None:
        with (
            mock.patch.object(identity, "_capabilities_supported", return_value=True),
            mock.patch.object(
                identity.os,
                "stat",
                side_effect=PermissionError(errno.EACCES, "denied"),
            ),
        ):
            self.assert_reason(
                "filesystem_ambiguous",
                lambda: identity.snapshot_regular_or_absent(
                    self.root,
                    "leaf",
                ),
            )

    def test_all_descriptors_close_when_observer_raises(self) -> None:
        self.write_file("nested/leaf")
        real_open = os.open
        real_close = os.close
        opened: list[int] = []
        closed: list[int] = []

        def tracked_open(*args: object, **kwargs: object) -> int:
            fd = real_open(*args, **kwargs)  # type: ignore[arg-type]
            opened.append(fd)
            return fd

        def tracked_close(fd: int) -> None:
            closed.append(fd)
            real_close(fd)

        def stop(stage: str) -> None:
            if stage == "after_leaf_read":
                raise RuntimeError("observer stop")

        with (
            mock.patch.object(identity, "_capabilities_supported", return_value=True),
            mock.patch.object(identity.os, "open", side_effect=tracked_open),
            mock.patch.object(identity.os, "close", side_effect=tracked_close),
        ):
            with self.assertRaisesRegex(RuntimeError, "observer stop"):
                identity.snapshot_regular_or_absent(
                    self.root,
                    "nested/leaf",
                    _observer=stop,
                )

        self.assertCountEqual(closed, opened)
        self.assertEqual(len(closed), 3)


if __name__ == "__main__":
    unittest.main()

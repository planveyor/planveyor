"""Descriptor-anchored snapshots for trusted-root-relative filesystem objects."""

from __future__ import annotations

import errno
import hashlib
import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Final, Literal, TypeAlias


_AUTHORITY_SCRIPTS_DIR = Path(__file__).resolve().parent


def _module_has_expected_origin(module: object, expected: Path) -> bool:
    origin = getattr(module, "__file__", None)
    if not isinstance(origin, str):
        return False
    try:
        return Path(origin).resolve(strict=True) == expected
    except (OSError, RuntimeError, ValueError):
        return False


def _scripts_package_is_local() -> bool:
    """Whether an already imported ``scripts`` package belongs to this runtime."""

    package = sys.modules.get("scripts")
    if package is None:
        return True
    package_paths = getattr(package, "__path__", None)
    if package_paths is None:
        return False
    try:
        paths = tuple(Path(entry).resolve(strict=True) for entry in package_paths)
    except (OSError, RuntimeError, TypeError, ValueError):
        return False
    if not paths or any(path != _AUTHORITY_SCRIPTS_DIR for path in paths):
        return False
    package_file = getattr(package, "__file__", None)
    if package_file is not None and not _module_has_expected_origin(
        package, _AUTHORITY_SCRIPTS_DIR / "__init__.py"
    ):
        return False
    return True


def _bind_authority_aliases(package_name: str, direct_name: str) -> None:
    """Expose this trusted file under both import spellings without a split."""

    if __name__ == "__main__":
        return
    package_is_local = _scripts_package_is_local()
    current = sys.modules[__name__]
    expected = _AUTHORITY_SCRIPTS_DIR / f"{direct_name}.py"
    if not _module_has_expected_origin(current, expected):
        raise ImportError("authority module has an unsafe origin")
    direct = sys.modules.get(direct_name)
    packaged = sys.modules.get(package_name)
    for module in (direct, packaged):
        if module is not None and not _module_has_expected_origin(module, expected):
            raise ImportError("authority module has an unsafe origin")
    if (direct is not None and direct is not current) or (packaged is not None and packaged is not current):
        raise ImportError("authority module aliases are split")
    sys.modules[direct_name] = current
    if package_is_local:
        sys.modules[package_name] = current


# Keep the direct-script and package imports of this internal exception type
# identical.  Snapshot/runtime/context use it to distinguish a safe absence
# from a fail-closed filesystem observation.
_bind_authority_aliases("scripts.fs_object_identity", "fs_object_identity")


SnapshotState: TypeAlias = Literal["regular", "absent"]
GitMode: TypeAlias = Literal["100644", "100755"]
Observer: TypeAlias = Callable[[str], None]


@dataclass(frozen=True, slots=True)
class ObjectSnapshot:
    relative_path: str
    state: SnapshotState
    data: bytes | None
    git_mode: GitMode | None
    st_dev: int | None
    st_ino: int | None
    st_size: int | None
    st_mtime_ns: int | None


@dataclass(frozen=True, slots=True)
class _LoadedModuleSourceObservation:
    """Retained loader bytes recorded while one pre-runtime module loaded."""

    origin: str
    relative_path: str
    mode: GitMode
    sha256: str


SourceCapsule: TypeAlias = tuple[str, int, str, bytes]


class ObjectIdentityError(RuntimeError):
    """Fail-closed result with a stable internal reason code."""

    def __init__(self, reason_code: str, message: str) -> None:
        self.reason_code = reason_code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class _AncestorLink:
    parent_fd: int
    name: str
    child_fd: int


_RACE_ERRNOS = frozenset(
    value
    for value in (
        errno.ENOENT,
        errno.ENOTDIR,
        getattr(errno, "ELOOP", None),
    )
    if value is not None
)


def _fail(reason_code: str, message: str) -> ObjectIdentityError:
    return ObjectIdentityError(reason_code, message)


def _capabilities_supported() -> bool:
    required_flags = ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK")
    if any(
        not isinstance(getattr(os, name, None), int) or getattr(os, name) == 0
        for name in required_flags
    ):
        return False
    if not all(callable(getattr(os, name, None)) for name in ("open", "stat", "fstat", "read", "close")):
        return False
    if os.open not in getattr(os, "supports_dir_fd", ()):
        return False
    if os.stat not in getattr(os, "supports_dir_fd", ()):
        return False
    if os.stat not in getattr(os, "supports_follow_symlinks", ()):
        return False
    return hasattr(os.stat_result, "st_mtime_ns")


def _validated_parts(relative_path: str) -> tuple[str, ...]:
    if (
        not isinstance(relative_path, str)
        or not relative_path
        or relative_path.startswith("/")
        or relative_path.endswith("/")
        or "\\" in relative_path
        or "\x00" in relative_path
    ):
        raise _fail("invalid_relative_path", "path must be normalized relative POSIX text")
    parts = tuple(relative_path.split("/"))
    if any(part in {"", ".", ".."} for part in parts):
        raise _fail("invalid_relative_path", "path contains a forbidden segment")
    return parts


def _open_flags(*, directory: bool) -> int:
    flags = os.O_RDONLY | os.O_NOFOLLOW
    if directory:
        flags |= os.O_DIRECTORY
    else:
        flags |= os.O_NONBLOCK
    flags |= getattr(os, "O_CLOEXEC", 0)
    return flags


def _identity(value: os.stat_result) -> tuple[int, int, int]:
    return (value.st_dev, value.st_ino, stat.S_IFMT(value.st_mode))


def _stable_metadata(
    value: os.stat_result,
) -> tuple[int, int, int, bool, int, int]:
    try:
        mtime_ns = value.st_mtime_ns
    except AttributeError as exc:
        raise _fail("unsupported_capability", "nanosecond mtime is unavailable") from exc
    return (
        value.st_dev,
        value.st_ino,
        stat.S_IFMT(value.st_mode),
        bool(value.st_mode & stat.S_IXUSR),
        value.st_size,
        mtime_ns,
    )


def _fstat(fd: int, context: str) -> os.stat_result:
    try:
        return os.fstat(fd)
    except OSError as exc:
        raise _fail("filesystem_ambiguous", f"cannot inspect {context}") from exc


def _open_trusted_root(trusted_root: Path) -> int:
    try:
        root_fd = os.open(os.fspath(trusted_root), _open_flags(directory=True))
    except (OSError, TypeError, ValueError) as exc:
        raise _fail("unsafe_trusted_root", "trusted root cannot be opened safely") from exc
    try:
        root_stat = _fstat(root_fd, "trusted root")
        if not stat.S_ISDIR(root_stat.st_mode):
            raise _fail("unsafe_trusted_root", "trusted root is not a directory")
        return root_fd
    except BaseException:
        try:
            os.close(root_fd)
        except OSError:
            pass
        raise


def _stat_initial_ancestor(parent_fd: int, name: str) -> os.stat_result:
    try:
        value = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        if exc.errno == errno.ENOENT:
            raise _fail("ancestor_missing", f"ancestor is missing: {name}") from exc
        raise _fail("filesystem_ambiguous", f"cannot inspect ancestor: {name}") from exc
    if stat.S_ISLNK(value.st_mode):
        raise _fail("symlink_forbidden", f"ancestor is a symlink: {name}")
    if not stat.S_ISDIR(value.st_mode):
        raise _fail("ancestor_not_directory", f"ancestor is not a directory: {name}")
    return value


def _open_ancestor(parent_fd: int, name: str) -> int:
    entry_stat = _stat_initial_ancestor(parent_fd, name)
    try:
        child_fd = os.open(
            name,
            _open_flags(directory=True),
            dir_fd=parent_fd,
        )
    except OSError as exc:
        reason = (
            "ancestor_identity_changed"
            if exc.errno in _RACE_ERRNOS
            else "filesystem_ambiguous"
        )
        raise _fail(reason, f"cannot anchor ancestor: {name}") from exc
    try:
        child_stat = _fstat(child_fd, f"ancestor fd: {name}")
        if not stat.S_ISDIR(child_stat.st_mode) or _identity(entry_stat) != _identity(child_stat):
            raise _fail("ancestor_identity_changed", f"ancestor changed while opening: {name}")
        return child_fd
    except BaseException:
        try:
            os.close(child_fd)
        except OSError:
            pass
        raise


def _revalidate_ancestors(links: list[_AncestorLink]) -> None:
    for link in links:
        try:
            entry_stat = os.stat(
                link.name,
                dir_fd=link.parent_fd,
                follow_symlinks=False,
            )
        except OSError as exc:
            if exc.errno in _RACE_ERRNOS:
                raise _fail(
                    "ancestor_identity_changed",
                    f"ancestor entry changed: {link.name}",
                ) from exc
            raise _fail(
                "filesystem_ambiguous",
                f"cannot revalidate ancestor: {link.name}",
            ) from exc
        child_stat = _fstat(link.child_fd, f"retained ancestor: {link.name}")
        if (
            stat.S_ISLNK(entry_stat.st_mode)
            or not stat.S_ISDIR(entry_stat.st_mode)
            or not stat.S_ISDIR(child_stat.st_mode)
            or _identity(entry_stat) != _identity(child_stat)
        ):
            raise _fail(
                "ancestor_identity_changed",
                f"ancestor entry no longer matches retained fd: {link.name}",
            )


def _stat_initial_leaf(parent_fd: int, name: str) -> os.stat_result | None:
    try:
        value = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        if exc.errno == errno.ENOENT:
            return None
        raise _fail("filesystem_ambiguous", f"cannot inspect leaf: {name}") from exc
    if stat.S_ISLNK(value.st_mode):
        raise _fail("symlink_forbidden", f"leaf is a symlink: {name}")
    if not stat.S_ISREG(value.st_mode):
        raise _fail("leaf_not_regular", f"leaf is not a regular file: {name}")
    return value


def _observe(observer: Observer | None, stage: str) -> None:
    if observer is not None:
        observer(stage)


def _read_all(fd: int) -> bytes:
    chunks: list[bytes] = []
    while True:
        try:
            chunk = os.read(fd, 1024 * 1024)
        except OSError as exc:
            raise _fail("filesystem_ambiguous", "cannot read retained leaf fd") from exc
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def _snapshot_absent(
    relative_path: str,
    parent_fd: int,
    leaf_name: str,
    links: list[_AncestorLink],
    observer: Observer | None,
) -> ObjectSnapshot:
    _observe(observer, "after_absence_observed")
    _revalidate_ancestors(links)
    try:
        second = os.stat(leaf_name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        if exc.errno != errno.ENOENT:
            raise _fail(
                "filesystem_ambiguous",
                f"cannot repeat absence observation: {leaf_name}",
            ) from exc
    else:
        del second
        raise _fail(
            "leaf_identity_changed",
            f"leaf appeared after absence observation: {leaf_name}",
        )
    _revalidate_ancestors(links)
    return ObjectSnapshot(
        relative_path=relative_path,
        state="absent",
        data=None,
        git_mode=None,
        st_dev=None,
        st_ino=None,
        st_size=None,
        st_mtime_ns=None,
    )


def _open_regular_leaf(parent_fd: int, leaf_name: str, entry_stat: os.stat_result) -> int:
    try:
        leaf_fd = os.open(
            leaf_name,
            _open_flags(directory=False),
            dir_fd=parent_fd,
        )
    except OSError as exc:
        reason = (
            "leaf_identity_changed"
            if exc.errno in _RACE_ERRNOS
            else "filesystem_ambiguous"
        )
        raise _fail(reason, f"cannot anchor leaf: {leaf_name}") from exc
    try:
        fd_stat = _fstat(leaf_fd, f"leaf fd: {leaf_name}")
        if not stat.S_ISREG(fd_stat.st_mode) or _identity(entry_stat) != _identity(fd_stat):
            raise _fail("leaf_identity_changed", f"leaf changed while opening: {leaf_name}")
        if _stable_metadata(entry_stat) != _stable_metadata(fd_stat):
            raise _fail(
                "leaf_content_metadata_changed",
                f"leaf metadata changed while opening: {leaf_name}",
            )
        return leaf_fd
    except BaseException:
        try:
            os.close(leaf_fd)
        except OSError:
            pass
        raise


def _snapshot_regular(
    relative_path: str,
    parent_fd: int,
    leaf_name: str,
    entry_stat: os.stat_result,
    links: list[_AncestorLink],
    open_fds: list[int],
    observer: Observer | None,
) -> ObjectSnapshot:
    leaf_fd = _open_regular_leaf(parent_fd, leaf_name, entry_stat)
    open_fds.append(leaf_fd)
    before = _fstat(leaf_fd, f"leaf before read: {leaf_name}")
    data = _read_all(leaf_fd)
    _observe(observer, "after_leaf_read")
    after = _fstat(leaf_fd, f"leaf after read: {leaf_name}")
    if _identity(before) != _identity(after):
        raise _fail("leaf_identity_changed", f"leaf identity changed while reading: {leaf_name}")
    if _stable_metadata(before) != _stable_metadata(after):
        raise _fail(
            "leaf_content_metadata_changed",
            f"leaf metadata changed while reading: {leaf_name}",
        )

    _revalidate_ancestors(links)
    try:
        final_entry = os.stat(
            leaf_name,
            dir_fd=parent_fd,
            follow_symlinks=False,
        )
    except OSError as exc:
        if exc.errno in _RACE_ERRNOS:
            raise _fail(
                "leaf_identity_changed",
                f"leaf entry changed before return: {leaf_name}",
            ) from exc
        raise _fail(
            "filesystem_ambiguous",
            f"cannot revalidate leaf entry: {leaf_name}",
        ) from exc
    if (
        stat.S_ISLNK(final_entry.st_mode)
        or not stat.S_ISREG(final_entry.st_mode)
        or _identity(final_entry) != _identity(after)
    ):
        raise _fail(
            "leaf_identity_changed",
            f"leaf entry no longer matches retained fd: {leaf_name}",
        )
    if _stable_metadata(final_entry) != _stable_metadata(after):
        raise _fail(
            "leaf_content_metadata_changed",
            f"leaf metadata changed before return: {leaf_name}",
        )

    git_mode: GitMode = "100755" if after.st_mode & stat.S_IXUSR else "100644"
    return ObjectSnapshot(
        relative_path=relative_path,
        state="regular",
        data=data,
        git_mode=git_mode,
        st_dev=after.st_dev,
        st_ino=after.st_ino,
        st_size=after.st_size,
        st_mtime_ns=after.st_mtime_ns,
    )


def snapshot_regular_or_absent(
    trusted_root: Path,
    relative_path: str,
    *,
    _observer: Observer | None = None,
) -> ObjectSnapshot:
    """Return a fail-closed snapshot tied to one retained descriptor chain."""

    if not _capabilities_supported():
        raise _fail(
            "unsupported_capability",
            "required descriptor-relative no-follow primitives are unavailable",
        )
    parts = _validated_parts(relative_path)
    open_fds: list[int] = []
    links: list[_AncestorLink] = []
    try:
        root_fd = _open_trusted_root(trusted_root)
        open_fds.append(root_fd)
        parent_fd = root_fd
        for name in parts[:-1]:
            child_fd = _open_ancestor(parent_fd, name)
            open_fds.append(child_fd)
            links.append(
                _AncestorLink(
                    parent_fd=parent_fd,
                    name=name,
                    child_fd=child_fd,
                )
            )
            parent_fd = child_fd

        _observe(_observer, "after_ancestor_chain_opened")
        leaf_name = parts[-1]
        entry_stat = _stat_initial_leaf(parent_fd, leaf_name)
        if entry_stat is None:
            return _snapshot_absent(
                relative_path,
                parent_fd,
                leaf_name,
                links,
                _observer,
            )
        return _snapshot_regular(
            relative_path,
            parent_fd,
            leaf_name,
            entry_stat,
            links,
            open_fds,
            _observer,
        )
    finally:
        for fd in reversed(open_fds):
            try:
                os.close(fd)
            except OSError:
                pass


def _capture_loaded_module_source_observation(
    module: object,
    *,
    expected_path: Path,
    relative_path: str,
    source_capsule: object,
    source_reader: object,
) -> _LoadedModuleSourceObservation | None:
    """Freeze one module's loader-retained source bytes without disk rereads.

    This runs while ``module`` is being imported.  A later runtime pin uses the
    observation only as provenance evidence; a raw import has no injected
    capsule and therefore stays unattested rather than reading current disk
    bytes as proof of already executed code.
    """

    try:
        canonical_path = expected_path.resolve(strict=True)
        runtime_root = canonical_path.parent.parent
        if canonical_path.relative_to(runtime_root).as_posix() != relative_path:
            return None
        if not _module_has_expected_origin(module, canonical_path):
            return None
        if not callable(source_reader):
            return None
        return _source_capsule_observation(
            source_capsule,
            expected_path=canonical_path,
            relative_path=relative_path,
        )
    except (OSError, RuntimeError, TypeError, ValueError):
        return None


def _source_capsule_observation(
    source_capsule: object,
    *,
    expected_path: Path,
    relative_path: str,
) -> _LoadedModuleSourceObservation | None:
    """Validate an immutable loader capsule without reopening its source path."""

    try:
        canonical_path = expected_path.resolve(strict=True)
        if type(source_capsule) is not tuple or len(source_capsule) != 4:
            return None
        origin, stat_mode, sha256, data = source_capsule
        if (
            type(origin) is not str
            or type(stat_mode) is not int
            or type(sha256) is not str
            or type(data) is not bytes
            or origin != os.fspath(canonical_path)
            or not 0 <= stat_mode <= 0o777
            or len(sha256) != 64
            or any(character not in "0123456789abcdef" for character in sha256)
            or hashlib.sha256(data).hexdigest() != sha256
        ):
            return None
        runtime_root = canonical_path.parent.parent
        if canonical_path.relative_to(runtime_root).as_posix() != relative_path:
            return None
    except (OSError, RuntimeError, TypeError, ValueError):
        return None
    return _LoadedModuleSourceObservation(
        origin=os.fspath(canonical_path),
        relative_path=relative_path,
        mode="100755" if stat_mode & 0o111 else "100644",
        sha256=sha256,
    )


def _source_capsule_matches_runtime_row(
    source_capsule: object,
    *,
    expected_path: Path,
    relative_path: str,
    mode: object,
    sha256: object,
) -> bool:
    """Whether one retained source capsule equals an eventual closure row."""

    if type(mode) is not str or mode not in {"100644", "100755"}:
        return False
    if (
        type(sha256) is not str
        or len(sha256) != 64
        or any(character not in "0123456789abcdef" for character in sha256)
    ):
        return False
    observation = _source_capsule_observation(
        source_capsule,
        expected_path=expected_path,
        relative_path=relative_path,
    )
    return observation is not None and observation.mode == mode and observation.sha256 == sha256


def _first_loaded_module_source_matches_runtime_row(
    module: object,
    *,
    expected_path: Path,
    relative_path: str,
    mode: object,
    sha256: object,
) -> bool:
    """Whether the actual pre-runtime module matches one captured pin row."""

    try:
        accessor = getattr(module, "_first_loaded_source_observation", None)
        if not callable(accessor):
            return False
        canonical_path = expected_path.resolve(strict=True)
        observation = accessor()
        if type(observation) is not _LoadedModuleSourceObservation:
            return False
        if type(relative_path) is not str:
            return False
        if type(mode) is not str or mode not in {"100644", "100755"}:
            return False
        if (
            type(sha256) is not str
            or len(sha256) != 64
            or any(character not in "0123456789abcdef" for character in sha256)
        ):
            return False
        if (
            type(observation.origin) is not str
            or type(observation.relative_path) is not str
            or type(observation.mode) is not str
            or type(observation.sha256) is not str
        ):
            return False
        return (
            _module_has_expected_origin(module, canonical_path)
            and observation.origin == os.fspath(canonical_path)
            and observation.relative_path == relative_path
            and observation.mode == mode
            and observation.sha256 == sha256
        )
    # A caller-owned host can retain or replace a pre-runtime module object.
    # Malformed accessors are unattested provenance, never an import-time path.
    except Exception:
        return False


_FIRST_LOADED_SOURCE_OBSERVATION: Final[_LoadedModuleSourceObservation | None] = (
    _capture_loaded_module_source_observation(
        sys.modules[__name__],
        expected_path=_AUTHORITY_SCRIPTS_DIR / "fs_object_identity.py",
        relative_path="scripts/fs_object_identity.py",
        source_capsule=globals().get("__authority_source_capsule__"),
        source_reader=globals().get("__authority_read_source__"),
    )
)


def _first_loaded_source_observation() -> _LoadedModuleSourceObservation | None:
    """Return immutable provenance recorded while this module initialized."""

    return _FIRST_LOADED_SOURCE_OBSERVATION

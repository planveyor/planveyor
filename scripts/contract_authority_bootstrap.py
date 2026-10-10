"""Caller-trusted literal bootstrap for the contract-authority bridge.

This file is data for a trusted caller to pass to ``python -I -B -c``.  It is
deliberately not a script which attests itself: its source must already have
been retained by the caller.  The literal descriptor-walks the requested
bridge once, then compiles and executes those exact bytes with a small
process-local source capability.
"""

from __future__ import annotations

import hashlib
import os
import stat
import sys
import types


_CAPSULE_TYPE = tuple[str, int, str, bytes]
_READ_BLOCK_SIZE = 1024 * 1024


class _BootstrapError(RuntimeError):
    pass


def _fail(message: str) -> _BootstrapError:
    return _BootstrapError(message)


def _canonical_absolute_path(value: object) -> str:
    if type(value) is not str or not value or "\x00" in value or not os.path.isabs(value):
        raise _fail("bridge path is invalid")
    if value.startswith("//"):
        raise _fail("bridge path is not canonical")
    normalized = os.path.normpath(value)
    if value != normalized or normalized == os.path.sep:
        raise _fail("bridge path is not canonical")
    parts = normalized.split(os.path.sep)[1:]
    if not parts or any(not part or part in {".", ".."} for part in parts):
        raise _fail("bridge path is not canonical")
    return normalized


def _directory_flags() -> int:
    required = ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK")
    if any(type(getattr(os, name, None)) is not int or getattr(os, name) == 0 for name in required):
        raise _fail("required descriptor capabilities are unavailable")
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0)


def _file_flags() -> int:
    if type(getattr(os, "O_NOFOLLOW", None)) is not int or type(getattr(os, "O_NONBLOCK", None)) is not int:
        raise _fail("required descriptor capabilities are unavailable")
    return os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0)


def _same_stat(before: os.stat_result, after: os.stat_result) -> bool:
    return (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    ) == (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )


def _read_regular_source(value: object) -> _CAPSULE_TYPE:
    """Read one regular non-symlinked path through retained ancestor fds."""

    path = _canonical_absolute_path(value)
    parts = path.split(os.path.sep)[1:]
    descriptors: list[int] = []
    leaf_fd: int | None = None
    try:
        parent_fd = os.open(os.path.sep, _directory_flags())
        descriptors.append(parent_fd)
        for part in parts[:-1]:
            child_fd = os.open(part, _directory_flags(), dir_fd=parent_fd)
            child_stat = os.fstat(child_fd)
            if not stat.S_ISDIR(child_stat.st_mode):
                os.close(child_fd)
                raise _fail("source ancestor is not a directory")
            descriptors.append(child_fd)
            parent_fd = child_fd
        leaf_fd = os.open(parts[-1], _file_flags(), dir_fd=parent_fd)
        before = os.fstat(leaf_fd)
        if not stat.S_ISREG(before.st_mode):
            raise _fail("source is not a regular file")
        blocks: list[bytes] = []
        digest = hashlib.sha256()
        while True:
            block = os.read(leaf_fd, _READ_BLOCK_SIZE)
            if not block:
                break
            blocks.append(block)
            digest.update(block)
        after = os.fstat(leaf_fd)
        if not _same_stat(before, after):
            raise _fail("source changed while being read")
        return (path, stat.S_IMODE(before.st_mode), digest.hexdigest(), b"".join(blocks))
    except _BootstrapError:
        raise
    except OSError as exc:
        raise _fail("source descriptor is unavailable") from exc
    finally:
        if leaf_fd is not None:
            try:
                os.close(leaf_fd)
            except OSError:
                pass
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass


def _reader_with_cache(initial: _CAPSULE_TYPE):
    cache: dict[str, _CAPSULE_TYPE] = {initial[0]: initial}

    def read_source(path: object) -> _CAPSULE_TYPE:
        canonical = _canonical_absolute_path(path)
        cached = cache.get(canonical)
        if cached is None:
            cached = _read_regular_source(canonical)
            cache[canonical] = cached
        return cached

    return read_source


def _execute_bridge(argv: list[str]) -> int:
    if not argv:
        raise _fail("bridge path is required")
    bridge = _read_regular_source(argv[0])
    reader = _reader_with_cache(bridge)
    namespace = types.ModuleType("__main__")
    namespace.__file__ = bridge[0]
    namespace.__package__ = None
    namespace.__loader__ = None
    namespace.__spec__ = None
    namespace.__cached__ = None
    namespace.__dict__.update(
        {
            "__name__": "__main__",
            "__file__": bridge[0],
            "__package__": None,
            "__loader__": None,
            "__spec__": None,
            "__cached__": None,
            "__authority_source_capsule__": bridge,
            "__authority_read_source__": reader,
        }
    )
    sys.modules["__main__"] = namespace
    sys.argv = [bridge[0], *argv[1:]]
    code = compile(bridge[3], bridge[0], "exec", dont_inherit=True)
    exec(code, namespace.__dict__, namespace.__dict__)
    return 0


def main() -> int:
    sys.dont_write_bytecode = True
    sys.pycache_prefix = os.devnull
    try:
        return _execute_bridge(sys.argv[1:])
    except _BootstrapError as exc:
        print(f"contract_authority_bootstrap: source_load_failed: {exc}", file=sys.stderr)
        return 2
    except Exception:
        print("contract_authority_bootstrap: source_load_failed: bridge could not be loaded", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

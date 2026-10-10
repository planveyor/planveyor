#!/usr/bin/env python3
"""One-shot, read-only shell bridge for contract authority.

The shell keeps only compact, canonical JSON summaries.  Runtime closure rows
and context objects stay in this short-lived Python process, so they cannot be
smuggled through an environment variable or reconstructed with ``eval``.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import stat
import subprocess
import sys
import types
from pathlib import Path
from typing import Any, Mapping


# Standard-library imports above may use their normal interpreter cache.  Set
# the local policy before any authority sibling import: those verified source
# files must neither read a conventional ``__pycache__`` entry nor write one.
# An absolute bridge script is itself read as source before this point.
sys.dont_write_bytecode = True
sys.pycache_prefix = os.devnull


_SCRIPT_PATH = Path(__file__).resolve()
_RUNTIME_ROOT = _SCRIPT_PATH.parent.parent

# Authority modules are loaded by their verified sibling file paths, never by
# the target cwd's ``scripts`` package.  A target can legitimately contain a
# regular ``scripts/__init__.py``; normal package resolution would let that
# package win over the runtime's namespace directory even with a root-prepend.
# Keeping direct sibling aliases first also preserves one exception/dataclass
# identity across runtime, snapshot, and context.
_AUTHORITY_MODULE_FILENAMES = {
    "fs_object_identity": "fs_object_identity.py",
    "contract_authority_snapshot": "contract_authority_snapshot.py",
    "contract_authority_runtime": "contract_authority_runtime.py",
    "contract_authority_context": "contract_authority_context.py",
}
_AUTHORITY_MODULE_ORDER = (
    "fs_object_identity",
    "contract_authority_snapshot",
    "contract_authority_runtime",
    "contract_authority_context",
)
_AUTHORITY_MODULE_CACHE: dict[str, Any] = {}
SourceCapsule = tuple[str, int, str, bytes]
_BRIDGE_SOURCE_CAPSULE: SourceCapsule | None = None
_BRIDGE_SOURCE_READER: Any | None = None
_RETAINED_CORE_CAPSULES: tuple[tuple[str, SourceCapsule], ...] | None = None


class BridgeError(RuntimeError):
    """Stable failure which intentionally has no path or command echo."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":"), sort_keys=True)


def _emit(value: object) -> None:
    sys.stdout.write(_canonical_json(value))
    sys.stdout.write("\n")


def _load_json(text: str, *, field: str, maximum: int = 16 * 1024) -> object:
    if len(text.encode("utf-8", "strict")) > maximum:
        raise BridgeError("payload_too_large", f"{field} exceeds the compact authority limit")
    try:
        return json.loads(text)
    except (TypeError, UnicodeError, json.JSONDecodeError) as exc:
        raise BridgeError("invalid_json", f"{field} is not canonical JSON") from exc


def _absolute_path(text: str, *, field: str) -> Path:
    if not text or "\x00" in text:
        raise BridgeError("invalid_path", f"{field} is invalid")
    value = Path(text)
    if not value.is_absolute():
        raise BridgeError("path_not_absolute", f"{field} must be absolute")
    # ``abspath`` preserves a caller's path components long enough for the
    # lstat loop below to reject symlink traversal rather than silently bless it.
    return Path(os.path.abspath(os.fspath(value)))


def _safe_regular_path(path_text: str) -> Path:
    """Return one regular no-symlink path without reading its body."""

    raw = _absolute_path(path_text, field="path")
    cursor = Path(raw.root)
    for component in raw.parts[1:]:
        cursor /= component
        try:
            item = os.lstat(cursor)
        except OSError as exc:
            raise BridgeError("source_missing", "source descriptor path is unavailable") from exc
        if stat.S_ISLNK(item.st_mode):
            raise BridgeError("source_symlink", "source descriptor path contains a symlink")
    try:
        before = os.lstat(raw)
    except OSError as exc:
        raise BridgeError("source_missing", "source descriptor path is unavailable") from exc
    if not stat.S_ISREG(before.st_mode):
        raise BridgeError("source_not_regular", "source descriptor path is not a regular file")
    return raw


def _read_regular_source_from_disk(path_text: str) -> SourceCapsule:
    """Read one regular path once for legacy/passive direct execution."""

    raw = _safe_regular_path(path_text)
    before = os.lstat(raw)

    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(os.fspath(raw), flags)
    except OSError as exc:
        raise BridgeError("source_open_failed", "source descriptor cannot be opened") from exc
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise BridgeError("source_changed", "source descriptor changed while opening")
        digest = hashlib.sha256()
        blocks: list[bytes] = []
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            blocks.append(block)
            digest.update(block)
    finally:
        os.close(descriptor)
    try:
        after = os.lstat(raw)
    except OSError as exc:
        raise BridgeError("source_changed", "source descriptor changed while reading") from exc
    if (after.st_dev, after.st_ino, after.st_mode, after.st_size) != (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_size,
    ):
        raise BridgeError("source_changed", "source descriptor changed while reading")
    return (os.fspath(raw), stat.S_IMODE(before.st_mode), digest.hexdigest(), b"".join(blocks))


def _regular_descriptor(path_text: str) -> dict[str, str]:
    """Return a descriptor summary after one regular-file read."""

    path, mode, sha256, _data = _read_regular_source_from_disk(path_text)
    return {
        "schema_version": "planveyor_source_descriptor.v1",
        "path": path,
        "mode": format(mode, "06o"),
        "sha256": sha256,
    }


def _source_capsule_from_value(value: object, *, expected_path: Path) -> SourceCapsule:
    """Validate a bootstrap-owned immutable source capsule without rereading it."""

    expected = os.fspath(expected_path)
    if type(value) is not tuple or len(value) != 4:
        raise BridgeError("source_capsule_invalid", "source capsule is invalid")
    path, mode, sha256, data = value
    if (
        type(path) is not str
        or type(mode) is not int
        or type(sha256) is not str
        or type(data) is not bytes
        or path != expected
        or not 0 <= mode <= 0o777
        or len(sha256) != 64
        or any(character not in "0123456789abcdef" for character in sha256)
        or hashlib.sha256(data).hexdigest() != sha256
    ):
        raise BridgeError("source_capsule_invalid", "source capsule is invalid")
    return (path, mode, sha256, data)


def _bootstrap_source_capability() -> tuple[SourceCapsule | None, Any | None]:
    """Recognize only the caller-injected capability; raw entry stays legacy."""

    capsule = globals().get("__authority_source_capsule__")
    reader = globals().get("__authority_read_source__")
    if capsule is None and reader is None:
        return None, None
    if not callable(reader):
        return None, None
    try:
        return _source_capsule_from_value(capsule, expected_path=_SCRIPT_PATH), reader
    except BridgeError:
        return None, None


_BRIDGE_SOURCE_CAPSULE, _BRIDGE_SOURCE_READER = _bootstrap_source_capability()


def _authority_module_path(name: str) -> Path:
    filename = _AUTHORITY_MODULE_FILENAMES.get(name)
    if filename is None:
        raise BridgeError("authority_module_missing", "contract authority Python module is unavailable")
    return _RUNTIME_ROOT / "scripts" / filename


def _module_has_expected_origin(module: object, expected: Path) -> bool:
    origin = getattr(module, "__file__", None)
    if type(origin) is not str:
        return False
    try:
        # Keep alias/origin checks while avoiding a second source-body read.
        # The supported loader separately binds code bytes to its capsule.
        return _safe_regular_path(origin) == _safe_regular_path(os.fspath(expected))
    except (BridgeError, OSError):
        return False


def _assert_preloaded_authority_aliases_safe() -> None:
    """Reject foreign aliases and bootstrap-time ambient module reuse."""

    for module_name in _AUTHORITY_MODULE_ORDER:
        expected = _authority_module_path(module_name)
        for alias in (module_name, f"scripts.{module_name}"):
            existing = sys.modules.get(alias)
            cached = _AUTHORITY_MODULE_CACHE.get(module_name)
            if existing is not None and existing is not cached and _BRIDGE_SOURCE_READER is not None:
                raise BridgeError(
                    "authority_module_preloaded",
                    "supported authority loading requires fresh retained module buffers",
                )
            if existing is not None and not _module_has_expected_origin(existing, expected):
                raise BridgeError(
                    "authority_module_origin_mismatch",
                    "authority module origin differs from bridge runtime",
                )


def _retained_core_capsules() -> tuple[tuple[str, SourceCapsule], ...] | None:
    """Read all core buffers before one of them is executed."""

    global _RETAINED_CORE_CAPSULES
    if _BRIDGE_SOURCE_CAPSULE is None or _BRIDGE_SOURCE_READER is None:
        return None
    if _RETAINED_CORE_CAPSULES is not None:
        return _RETAINED_CORE_CAPSULES
    rows: list[tuple[str, SourceCapsule]] = [
        ("scripts/contract_authority_bridge.py", _BRIDGE_SOURCE_CAPSULE),
    ]
    for module_name in _AUTHORITY_MODULE_ORDER:
        expected = _authority_module_path(module_name)
        try:
            source = _BRIDGE_SOURCE_READER(os.fspath(expected))
        except Exception as exc:
            raise BridgeError("source_capsule_unavailable", "authority source cannot be retained") from exc
        rows.append(
            (
                f"scripts/{expected.name}",
                _source_capsule_from_value(source, expected_path=expected),
            )
        )
    _RETAINED_CORE_CAPSULES = tuple(rows)
    return _RETAINED_CORE_CAPSULES


def _retained_capsule_for_path(relative_path: str) -> SourceCapsule:
    table = _retained_core_capsules()
    if table is None:
        raise BridgeError("runtime_pin_unattested", "authority bridge has no retained source capability")
    for path, capsule in table:
        if path == relative_path:
            return capsule
    raise BridgeError("source_capsule_unavailable", "authority source cannot be retained")


def _authority_module(name: str) -> Any:
    """Load one authority sibling from this bridge's runtime, fail closed on aliases."""

    _assert_preloaded_authority_aliases_safe()
    cached = _AUTHORITY_MODULE_CACHE.get(name)
    if cached is not None:
        return cached
    expected = _authority_module_path(name)
    package_alias = f"scripts.{name}"
    for alias in (name, package_alias):
        existing = sys.modules.get(alias)
        if existing is not None and not _module_has_expected_origin(existing, expected):
            raise BridgeError("authority_module_origin_mismatch", "authority module origin differs from bridge runtime")
    direct_existing = sys.modules.get(name)
    if direct_existing is not None:
        if _BRIDGE_SOURCE_READER is not None:
            raise BridgeError("authority_module_preloaded", "authority module was loaded outside retained buffers")
        _AUTHORITY_MODULE_CACHE[name] = direct_existing
        return direct_existing

    relative_path = f"scripts/{expected.name}"
    table = _retained_core_capsules()
    source = (
        _retained_capsule_for_path(relative_path)
        if table is not None
        else _read_regular_source_from_disk(os.fspath(expected))
    )
    module = types.ModuleType(name)
    module.__file__ = source[0]
    module.__package__ = None
    module.__loader__ = None
    module.__spec__ = None
    module.__dict__["__cached__"] = None
    if table is not None:
        module.__dict__.update(
            {
                "__authority_source_capsule__": source,
                "__authority_read_source__": _BRIDGE_SOURCE_READER,
                "__authority_loaded_source_capsules__": table,
            }
        )
    sys.modules[name] = module
    try:
        code = compile(source[3], source[0], "exec", dont_inherit=True)
        exec(code, module.__dict__, module.__dict__)
    except BridgeError:
        sys.modules.pop(name, None)
        raise
    except Exception as exc:
        sys.modules.pop(name, None)
        raise BridgeError("authority_module_load_failed", "contract authority module could not be loaded") from exc
    package_loaded = sys.modules.get(package_alias)
    if package_loaded is not None and package_loaded is not module:
        sys.modules.pop(name, None)
        raise BridgeError("authority_module_origin_mismatch", "authority module aliases differ from bridge runtime")
    _AUTHORITY_MODULE_CACHE[name] = module
    return module


# These are every file that can change the source-time facade, its authority
# seam, or the Python boundary it invokes before later module imports.  The
# compact aggregate is intentionally part of a source descriptor even when a
# dirty/non-Git runtime cannot receive a full loaded-runtime pin.
_SOURCE_RUNTIME_INPUTS = (
    "scripts/planveyor.zsh",
    "scripts/planveyor/contract_authority.zsh",
    "scripts/planveyor/session_init.zsh",
    "scripts/planveyor/role_runtime.zsh",
    "scripts/planveyor/docs_finalize.zsh",
    "scripts/contract_authority_bootstrap.py",
    "scripts/contract_authority_shell_loader.zsh",
    "scripts/contract_authority_bridge.py",
    "scripts/contract_authority_context.py",
    "scripts/contract_authority_runtime.py",
    "scripts/contract_authority_snapshot.py",
    "scripts/fs_object_identity.py",
)


def _runtime_source_revision(runtime_root_text: str) -> dict[str, object]:
    """Capture a small re-source boundary without claiming a clean pin."""

    runtime_root = _absolute_path(runtime_root_text, field="runtime root")
    try:
        root_info = os.lstat(runtime_root)
    except OSError as exc:
        raise BridgeError("runtime_root_missing", "runtime root is unavailable") from exc
    if not stat.S_ISDIR(root_info.st_mode) or stat.S_ISLNK(root_info.st_mode):
        raise BridgeError("runtime_root_invalid", "runtime root is not a regular directory")

    rows: list[dict[str, str]] = []
    for relative_path in _SOURCE_RUNTIME_INPUTS:
        item = _regular_descriptor(os.fspath(runtime_root / relative_path))
        rows.append(
            {
                "path": relative_path,
                "mode": item["mode"],
                "sha256": item["sha256"],
            }
        )
    content_sha256 = hashlib.sha256(
        _canonical_json(rows).encode("ascii", "strict")
    ).hexdigest()

    # Git provenance is optional here: an unavailable/non-Git runtime remains
    # legacy, but a later re-source must reproduce the same observation.
    git: dict[str, str]
    try:
        snapshot = _authority_module("contract_authority_snapshot")
        basis = snapshot._capture_git_basis(runtime_root, context="source revision")
        git = {
            "state": "git",
            "root": os.fspath(basis.root),
            "git_dir": os.fspath(basis.git_dir),
            "head": basis.head,
            "tree": basis.tree,
        }
    except Exception:
        git = {"state": "unavailable"}

    return {
        "schema_version": "planveyor_source_runtime_revision.v1",
        "runtime_root": os.fspath(runtime_root),
        "inputs_sha256": content_sha256,
        "git": git,
    }


def _source_descriptor(path_text: str, runtime_root: str | None) -> dict[str, object]:
    descriptor: dict[str, object] = dict(_regular_descriptor(path_text))
    if runtime_root is None:
        return descriptor
    descriptor["schema_version"] = "planveyor_source_descriptor.v2"
    descriptor["runtime_revision"] = _runtime_source_revision(runtime_root)
    return descriptor


def _source_descriptor_from_capsule(
    source: SourceCapsule,
    runtime_root: str,
) -> dict[str, object]:
    """Build the existing descriptor schema from retained source bytes."""

    descriptor: dict[str, object] = {
        "schema_version": "planveyor_source_descriptor.v2",
        "path": source[0],
        "mode": format(source[1], "06o"),
        "sha256": source[2],
        "runtime_revision": _runtime_source_revision(runtime_root),
    }
    return descriptor


def _runtime_modules() -> tuple[Any, Any]:
    try:
        # Load the dependency order explicitly before context's dynamic sibling
        # imports can encounter a target-controlled package namespace.
        for module_name in _AUTHORITY_MODULE_ORDER:
            _authority_module(module_name)
        runtime = _authority_module("contract_authority_runtime")
        context = _authority_module("contract_authority_context")
    except (ImportError, OSError) as exc:
        raise BridgeError("authority_module_missing", "contract authority Python module is unavailable") from exc
    return runtime, context


def _runtime_only() -> Any:
    try:
        _authority_module("fs_object_identity")
        _authority_module("contract_authority_snapshot")
        runtime = _authority_module("contract_authority_runtime")
    except (ImportError, OSError) as exc:
        raise BridgeError("runtime_pin_module_missing", "runtime pin module is unavailable") from exc
    return runtime


def _snapshot_only() -> Any:
    """Load only the passive envelope parser and its verified dependency."""

    try:
        _authority_module("fs_object_identity")
        return _authority_module("contract_authority_snapshot")
    except (ImportError, OSError) as exc:
        raise BridgeError("authority_module_missing", "contract authority Python module is unavailable") from exc


def _supported_loaded_runtime_pin(runtime_root: Path) -> tuple[Any, Any]:
    """Return the one first-loaded pin only a retained-buffer bridge can use."""

    if _BRIDGE_SOURCE_CAPSULE is None or _BRIDGE_SOURCE_READER is None:
        raise BridgeError("runtime_pin_unattested", "raw bridge execution cannot attest a runtime pin")
    runtime, context = _runtime_modules()
    observation = runtime._first_loaded_runtime_observation()
    pin = observation.pin
    if pin is None:
        raise BridgeError("runtime_pin_unattested", "loaded authority code has no retained runtime pin")
    if observation.runtime_root != runtime_root or pin.runtime_root != runtime_root:
        raise BridgeError("runtime_source_mismatch", "runtime pin belongs to a different runtime root")
    if not context._first_loaded_context_source_matches_runtime_pin(pin):
        raise BridgeError("runtime_pin_unattested", "loaded context code has no retained runtime pin")
    try:
        verified = runtime.verify_loaded_runtime_pin(pin)
    except Exception as exc:
        _raise_authority_error(exc)
    if verified != pin:
        raise BridgeError("runtime_loaded_code_drift", "loaded runtime code differs from current runtime bytes")
    return runtime, pin


def _runtime_summary(runtime: Any, pin: object) -> dict[str, object]:
    return runtime.loaded_runtime_pin_summary(pin)


def _parse_runtime_pin_summary(text: str) -> tuple[dict[str, object], Path]:
    value = _load_json(text, field="runtime pin summary")
    if type(value) is not dict:
        raise BridgeError("runtime_pin_summary_invalid", "runtime pin summary must be an object")
    expected_fields = {
        "schema_version",
        "runtime_root",
        "git_dir",
        "runtime_api_version",
        "commit",
        "tree",
        "closure_spec_sha256",
        "closure_rows_sha256",
        "closure_sha256",
        "pin_sha256",
    }
    if set(value) != expected_fields or value.get("schema_version") != "planveyor_runtime_pin_summary.v1":
        raise BridgeError("runtime_pin_summary_invalid", "runtime pin summary has an invalid schema")
    root_value = value.get("runtime_root")
    if type(root_value) is not str:
        raise BridgeError("runtime_pin_summary_invalid", "runtime pin summary has no runtime root")
    runtime_root = _absolute_path(root_value, field="runtime root")
    return value, runtime_root


def _summary_to_pin(runtime: Any, text: str) -> Any:
    """Bind a supplied summary to this process's retained first-loaded pin."""

    value, runtime_root = _parse_runtime_pin_summary(text)
    supported_runtime, current = _supported_loaded_runtime_pin(runtime_root)
    if supported_runtime is not runtime:
        raise BridgeError("runtime_loaded_code_drift", "authority runtime aliases differ from retained buffers")
    actual = _runtime_summary(supported_runtime, current)
    if actual != value:
        raise BridgeError("runtime_pin_mismatch", "loaded runtime differs from its compact pin summary")
    return current


def _child_runtime_pin(runtime_summary: str | None) -> tuple[Any, Any]:
    """Bind an optional parent carrier before a buffered child can run.

    An initial supported caller has no parent summary and still captures the
    retained first-load pin for this process.  A buffered child instead must
    prove its current retained code and disk are exactly the parent's pin.
    """

    if runtime_summary is None:
        return _supported_loaded_runtime_pin(_RUNTIME_ROOT)
    runtime = _runtime_only()
    pin = _summary_to_pin(runtime, runtime_summary)
    if pin.runtime_root != _RUNTIME_ROOT:
        raise BridgeError("runtime_source_mismatch", "runtime pin summary belongs to a different bridge runtime")
    return runtime, pin


def _context_summary_to_first_loaded_pin(runtime: Any, text: str) -> Any:
    """Bind an active context request to this process's immutable code pin.

    This deliberately does not recapture disk before target observation.  The
    context layer retains its full post-target revalidation, while a supplied
    summary cannot upgrade or replace the Python code identity frozen when the
    runtime module first loaded in this bridge process.
    """

    value, supplied_root = _parse_runtime_pin_summary(text)
    observation = runtime._first_loaded_runtime_observation()
    if observation.runtime_root != supplied_root:
        raise BridgeError("runtime_source_mismatch", "runtime pin summary belongs to a different loaded runtime")
    pin = observation.pin
    if pin is None:
        raise BridgeError("runtime_pin_unattested", "loaded runtime code has no retained first observation")
    if pin.runtime_root != observation.runtime_root:
        raise BridgeError("runtime_source_mismatch", "loaded runtime pin belongs to a different runtime root")
    supported_runtime, supported_pin = _supported_loaded_runtime_pin(supplied_root)
    if supported_runtime is not runtime or supported_pin != pin:
        raise BridgeError("runtime_loaded_code_drift", "loaded runtime aliases differ from retained buffers")
    if _runtime_summary(runtime, pin) != value:
        raise BridgeError("runtime_loaded_code_drift", "loaded runtime code differs from its compact pin summary")
    return pin


def _pin_for_candidate(runtime_root: str, entrypoint: str) -> tuple[Any, object]:
    root = _absolute_path(runtime_root, field="runtime root")
    entry = _absolute_path(entrypoint, field="runtime entrypoint")
    expected = root / "scripts" / "planveyor.zsh"
    if entry != expected:
        raise BridgeError("runtime_entrypoint_mismatch", "runtime entrypoint is not the canonical facade")
    # Both the candidate facade and the runtime root itself must be descriptor
    # safe before asking the Git closure observer to pin it.
    _safe_regular_path(os.fspath(entry))
    runtime, pin = _supported_loaded_runtime_pin(root)
    return runtime, pin


@dataclasses.dataclass(frozen=True, slots=True)
class _BinaryResponse:
    header: Mapping[str, object] | None
    data: bytes


_SHELL_SOURCE_BUFFER_PATHS = frozenset(
    {
        "scripts/planveyor/contract_authority.zsh",
        "scripts/planveyor/session_init.zsh",
        "scripts/planveyor/role_runtime.zsh",
        "scripts/planveyor/docs_finalize.zsh",
        "scripts/planveyor/home_runtime.zsh",
        "scripts/planveyor/provider_runtime.zsh",
    }
)


def _runtime_row(pin: Any, relative_path: str) -> Any:
    row = next((item for item in pin.closure_rows if item.path == relative_path), None)
    if row is None:
        raise BridgeError("runtime_pin_mismatch", "runtime pin does not contain the requested source")
    return row


def _retained_runtime_source(
    *,
    runtime_root: Path,
    relative_path: str,
) -> SourceCapsule:
    if _BRIDGE_SOURCE_READER is None:
        raise BridgeError("runtime_pin_unattested", "raw bridge execution cannot retain runtime source")
    expected = runtime_root / relative_path
    try:
        source = _BRIDGE_SOURCE_READER(os.fspath(expected))
    except Exception as exc:
        raise BridgeError("source_capsule_unavailable", "requested source cannot be retained") from exc
    return _source_capsule_from_value(source, expected_path=expected)


def _capsule_matches_runtime_row(
    source: SourceCapsule,
    *,
    runtime_root: Path,
    relative_path: str,
    pin: Any,
) -> None:
    row = _runtime_row(pin, relative_path)
    expected_mode = "100755" if source[1] & 0o111 else "100644"
    if source[2] != row.sha256 or expected_mode != row.mode:
        raise BridgeError("runtime_loaded_code_drift", "retained source differs from the loaded runtime pin")
    expected = runtime_root / relative_path
    if source[0] != os.fspath(expected):
        raise BridgeError("source_capsule_invalid", "retained source path is invalid")


def _reverify_supported_pin(runtime: Any, pin: Any) -> None:
    try:
        verified = runtime.verify_loaded_runtime_pin(pin)
    except Exception as exc:
        _raise_authority_error(exc)
    if verified != pin:
        raise BridgeError("runtime_loaded_code_drift", "loaded runtime code differs from current runtime bytes")


def _shell_transport_body(source: SourceCapsule) -> bytes:
    """Return retained shell bytes only when they are safe for shell transport."""

    body = source[3]
    if b"\x00" in body:
        raise BridgeError("source_body_nul", "shell source body contains a NUL byte")
    return body


def _shell_source_response(args: argparse.Namespace) -> _BinaryResponse:
    runtime_root = _absolute_path(args.runtime_root, field="runtime root")
    if runtime_root != _RUNTIME_ROOT:
        raise BridgeError("runtime_source_mismatch", "runtime root differs from the bridge runtime")
    facade = _absolute_path(args.path, field="source path")
    expected = runtime_root / "scripts" / "planveyor.zsh"
    if facade != expected:
        raise BridgeError("runtime_entrypoint_mismatch", "source path is not the canonical facade")
    # A parent summary is checked before this process even retains facade
    # bytes.  It cannot be replaced by a clean child-side recapture.
    runtime, pin = _child_runtime_pin(args.runtime_pin_summary)
    if pin.runtime_root != runtime_root:
        raise BridgeError("runtime_source_mismatch", "runtime pin differs from the requested facade runtime")
    source = _retained_runtime_source(runtime_root=runtime_root, relative_path="scripts/planveyor.zsh")
    _capsule_matches_runtime_row(
        source,
        runtime_root=runtime_root,
        relative_path="scripts/planveyor.zsh",
        pin=pin,
    )
    descriptor = _source_descriptor_from_capsule(source, os.fspath(runtime_root))
    _reverify_supported_pin(runtime, pin)
    header: Mapping[str, object] = {
        "version": 1,
        "source_path": source[0],
        "runtime_root": os.fspath(runtime_root),
        # ``mode`` is the retained filesystem permission mode, not a Git
        # closure mode.  The descriptor preserves the same established field.
        "source": {"mode": format(source[1], "06o"), "sha256": source[2], "size": len(source[3])},
        "source_descriptor": descriptor,
        "runtime_pin": _runtime_summary(runtime, pin),
    }
    return _BinaryResponse(header=header, data=_shell_transport_body(source))


def _source_buffer_response(args: argparse.Namespace) -> _BinaryResponse:
    relative_path = args.relative_path
    if relative_path not in _SHELL_SOURCE_BUFFER_PATHS:
        raise BridgeError("source_buffer_path_invalid", "requested shell source path is not allowed")
    runtime = _runtime_only()
    pin = _summary_to_pin(runtime, args.runtime_pin_summary)
    runtime_root = pin.runtime_root
    source = _retained_runtime_source(runtime_root=runtime_root, relative_path=relative_path)
    _capsule_matches_runtime_row(source, runtime_root=runtime_root, relative_path=relative_path, pin=pin)
    _reverify_supported_pin(runtime, pin)
    return _BinaryResponse(header=None, data=_shell_transport_body(source))



def _shell_loader_response(args: argparse.Namespace) -> _BinaryResponse:
    runtime = _runtime_only()
    pin = _summary_to_pin(runtime, args.runtime_pin_summary)
    try:
        rendered = runtime.authority_shell_loader_literal(pin)
    except Exception as exc:
        _raise_authority_error(exc)
    _reverify_supported_pin(runtime, pin)
    return _BinaryResponse(header=None, data=rendered.encode("utf-8", "strict"))


def _runtime_entry_source(
    path_text: str,
    *,
    runtime_pin_summary: str | None,
) -> tuple[Any, SourceCapsule, Path]:
    path = _absolute_path(path_text, field="runtime Python entrypoint")
    runtime_root = _RUNTIME_ROOT
    try:
        relative_path = path.relative_to(runtime_root).as_posix()
    except ValueError as exc:
        raise BridgeError("runtime_entrypoint_mismatch", "runtime entrypoint lies outside the bridge runtime") from exc
    if not relative_path.startswith("scripts/") or not relative_path.endswith(".py"):
        raise BridgeError("runtime_entrypoint_mismatch", "runtime entrypoint is not an owned Python source")
    if relative_path == "scripts/contract_authority_bridge.py":
        raise BridgeError("runtime_entrypoint_mismatch", "bridge cannot dispatch itself as a Python entrypoint")
    runtime, pin = _child_runtime_pin(runtime_pin_summary)
    source = _retained_runtime_source(runtime_root=runtime_root, relative_path=relative_path)
    _capsule_matches_runtime_row(source, runtime_root=runtime_root, relative_path=relative_path, pin=pin)
    _reverify_supported_pin(runtime, pin)
    return runtime, source, path


def _execute_caller_python(
    *,
    source: bytes,
    filename: str,
    argv: list[str],
    entry_capsule: SourceCapsule | None,
) -> None:
    """Execute one already validated caller/runtime buffer as a temporary main."""

    module = types.ModuleType("__main__")
    module.__file__ = filename
    module.__package__ = None
    module.__loader__ = None
    module.__spec__ = None
    module.__dict__["__cached__"] = None
    table = _retained_core_capsules()
    if table is None or _BRIDGE_SOURCE_READER is None:
        raise BridgeError("runtime_pin_unattested", "authority bridge has no retained source capability")
    module.__dict__.update(
        {
            "__name__": "__main__",
            "__file__": filename,
            "__package__": None,
            "__loader__": None,
            "__spec__": None,
            "__cached__": None,
            "__authority_read_source__": _BRIDGE_SOURCE_READER,
            "__authority_loaded_source_capsules__": table,
        }
    )
    if entry_capsule is not None:
        module.__dict__["__authority_source_capsule__"] = entry_capsule
    original_main = sys.modules.get("__main__")
    original_argv = sys.argv
    entry_directory = os.path.dirname(filename) if filename != "<stdin>" else ""
    original_path = list(sys.path)
    try:
        code = compile(source, filename, "exec", dont_inherit=True)
    except (SyntaxError, ValueError) as exc:
        raise BridgeError("python_entry_invalid", "Python entry source cannot be compiled") from exc
    try:
        sys.modules["__main__"] = module
        sys.argv = argv
        import_paths = [
            path
            for path in (entry_directory, os.fspath(_RUNTIME_ROOT / "scripts"), os.fspath(_RUNTIME_ROOT))
            if path
        ]
        for path in reversed(import_paths):
            sys.path.insert(0, path)
        exec(code, module.__dict__, module.__dict__)
    finally:
        sys.argv = original_argv
        sys.path[:] = original_path
        if original_main is None:
            sys.modules.pop("__main__", None)
        else:
            sys.modules["__main__"] = original_main


def _entry_arguments(args: argparse.Namespace) -> list[str]:
    """Drop only argparse's documented separator before forwarding argv."""

    values = list(args.entry_args)
    if values[:1] == ["--"]:
        return values[1:]
    return values


def _python_entry(args: argparse.Namespace) -> None:
    _runtime, source, path = _runtime_entry_source(
        args.path,
        runtime_pin_summary=args.runtime_pin_summary,
    )
    _execute_caller_python(
        source=source[3],
        filename=source[0],
        argv=[os.fspath(path), *_entry_arguments(args)],
        entry_capsule=source,
    )


def _python_stdin(args: argparse.Namespace) -> None:
    runtime, pin = _child_runtime_pin(args.runtime_pin_summary)
    try:
        source = sys.stdin.buffer.read()
    except OSError as exc:
        raise BridgeError("python_stdin_read_failed", "caller Python source cannot be read") from exc
    _reverify_supported_pin(runtime, pin)
    _execute_caller_python(
        source=source,
        filename="<stdin>",
        argv=["-", *_entry_arguments(args)],
        entry_capsule=None,
    )


def _context_from_envelope(
    *,
    compact: str,
    runtime_summary: str | None,
    runtime_root: str | None,
    project_root: str | None,
    context_only_summary: bool = False,
) -> tuple[Any, Any]:
    runtime, context = _runtime_modules()
    pin: Any
    runtime_root_for_context: Any
    if runtime_summary:
        pin = (
            _context_summary_to_first_loaded_pin(runtime, runtime_summary)
            if context_only_summary
            else _summary_to_pin(runtime, runtime_summary)
        )
        runtime_root_for_context = pin.runtime_root
    else:
        pin = "unattested_legacy"
        runtime_root_for_context = _absolute_path(runtime_root or "", field="runtime root")
    root = _absolute_path(project_root, field="project root") if project_root else None
    try:
        value = context.validate_inherited_context(
            compact,
            project_root=root,
            runtime_root=runtime_root_for_context,
            loaded_pin=pin,
        )
    except Exception as exc:  # context keeps its own concise reason codes.
        _raise_authority_error(exc)
    return context, value


def _raise_authority_error(exc: Exception) -> None:
    code = getattr(exc, "reason_code", None)
    if type(code) is str and code:
        raise BridgeError(code, "contract authority validation failed") from exc
    raise BridgeError("authority_validation_failed", "contract authority validation failed") from exc


def _envelope_mapping(snapshot: Any, text: str) -> Mapping[str, object]:
    try:
        value = snapshot.parse_context_envelope(text)
    except Exception as exc:
        _raise_authority_error(exc)
    if type(value) is not dict:
        raise BridgeError("context_envelope_invalid", "context envelope is not an object")
    return value


def _field_value(mapping: Mapping[str, object], field: str) -> object:
    aliases = {
        "runtime_root": ("runtime_pin", "runtime_root"),
        "runtime_pin_sha256": ("runtime_pin", "pin_sha256"),
        "runtime_api_version": ("runtime_pin", "runtime_api_version"),
    }
    parts = aliases.get(field, tuple(field.split(".")))
    value: object = mapping
    for part in parts:
        if type(value) is not dict or part not in value:
            raise BridgeError("context_field_missing", "requested context field is unavailable")
        value = value[part]
    if type(value) not in (str, int, bool):
        raise BridgeError("context_field_not_scalar", "requested context field is not scalar")
    return value


def _runtime_summary_field(summary: Mapping[str, object], field: str) -> object:
    if field not in summary:
        raise BridgeError("runtime_pin_field_missing", "requested runtime pin field is unavailable")
    value = summary[field]
    if type(value) not in (str, int):
        raise BridgeError("runtime_pin_field_invalid", "requested runtime pin field is not scalar")
    return value


def _read_receipt_authority(path: Path) -> Mapping[str, object] | None:
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise BridgeError("receipt_read_failed", "initialization receipt cannot be read") from exc
    if len(raw) > 1024 * 1024:
        raise BridgeError("receipt_too_large", "initialization receipt is too large")
    try:
        value = json.loads(raw.decode("utf-8", "strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BridgeError("receipt_invalid", "initialization receipt is invalid JSON") from exc
    if type(value) is not dict:
        raise BridgeError("receipt_invalid", "initialization receipt is invalid")
    return value


def _receipt_context_binding(envelope: Mapping[str, object]) -> str:
    """Return the receipt identity after strict envelope validation.

    A v2 child keeps a parent's historical entry facts but must label them as
    inherited and unverified.  That provenance transition necessarily changes
    the envelope's version-bound self-digest.  The receipt still binds every
    historical/runtime fact, so exclude only the schema marker, provenance
    label, and digest after the passive parser has verified each envelope.
    """

    return _canonical_json(
        {
            field: value
            for field, value in envelope.items()
            if field not in {"schema_version", "entry_observation_provenance", "context_sha256"}
        }
    )


def _receipt_validate(args: argparse.Namespace) -> dict[str, object]:
    project_root = _absolute_path(args.project_root, field="project root")
    sid = args.sid
    session_key = args.session_key
    if not sid or any(character in sid for character in "/\\\x00\r\n"):
        raise BridgeError("receipt_sid_invalid", "session id is invalid")
    if not session_key or any(character in session_key for character in "/\\\x00\r\n"):
        raise BridgeError("receipt_key_invalid", "session key is invalid")
    receipt = _read_receipt_authority(project_root / ".planveyor.init_runs" / "by_sid" / sid / "meta.json")
    if args.mode == "legacy":
        if receipt is None:
            return {"mode": "legacy", "receipt": "absent", "ok": True}
        authority = receipt.get("authority_context")
        if authority is None:
            return {"mode": "legacy", "receipt": "legacy", "ok": True}
        raise BridgeError("engaged_receipt_in_legacy", "an engaged session cannot resume under legacy authority")
    if receipt is None:
        raise BridgeError("receipt_missing", "engaged session has no initialization receipt")
    if receipt.get("outcome") != "success" or receipt.get("sid") != sid or receipt.get("session_key") != session_key:
        raise BridgeError("receipt_binding_mismatch", "initialization receipt does not bind this session")
    authority = receipt.get("authority_context")
    if type(authority) is not dict:
        raise BridgeError("receipt_authority_missing", "engaged initialization receipt has no authority context")
    snapshot = _snapshot_only()
    expected = _envelope_mapping(snapshot, args.context)
    observed_text = _canonical_json(authority)
    observed = _envelope_mapping(snapshot, observed_text)
    if expected.get("state") != "engaged" or _receipt_context_binding(expected) != _receipt_context_binding(observed):
        raise BridgeError("receipt_authority_mismatch", "initialization receipt authority does not match current context")
    return {"mode": "engaged", "receipt": "matched", "ok": True}


def _command(args: argparse.Namespace) -> object:
    if args.command == "shell-source":
        return _shell_source_response(args)
    if args.command == "source-buffer":
        return _source_buffer_response(args)
    if args.command == "shell-loader":
        return _shell_loader_response(args)
    if args.command == "python-entry":
        _python_entry(args)
        return None
    if args.command == "python-stdin":
        _python_stdin(args)
        return None
    if args.command == "source-descriptor":
        return _source_descriptor(args.path, args.runtime_root)
    if args.command == "source-verify":
        expected = _load_json(args.descriptor, field="source descriptor")
        observed = _source_descriptor(args.path, args.runtime_root)
        if observed != expected:
            raise BridgeError("source_descriptor_mismatch", "source descriptor differs from the loaded source")
        return observed
    if args.command == "runtime-pin":
        runtime, pin = _pin_for_candidate(args.runtime_root, args.entrypoint)
        return _runtime_summary(runtime, pin)
    if args.command == "runtime-verify":
        runtime = _runtime_only()
        pin = _summary_to_pin(runtime, args.runtime_pin_summary)
        return _runtime_summary(runtime, pin)
    if args.command == "runtime-api":
        runtime = _runtime_only()
        api_pin = _summary_to_pin(runtime, args.runtime_pin_summary)
        minimum = args.minimum
        maximum = args.maximum if args.maximum is not None else minimum
        if minimum < 0 or maximum < minimum or not (minimum <= api_pin.runtime_api_version <= maximum):
            raise BridgeError("runtime_api_incompatible", "loaded runtime API is outside the requested range")
        return _runtime_summary(runtime, api_pin)
    if args.command == "runtime-api-version":
        runtime = _runtime_only()
        return str(runtime.RUNTIME_API_VERSION)
    if args.command == "runtime-field":
        runtime = _runtime_only()
        pin = _summary_to_pin(runtime, args.runtime_pin_summary)
        return str(_runtime_summary_field(_runtime_summary(runtime, pin), args.field))
    if args.command == "context":
        runtime, context = _runtime_modules()
        pin_context: Any
        context_runtime_root: Any
        if args.runtime_pin_summary:
            pin_context = _context_summary_to_first_loaded_pin(runtime, args.runtime_pin_summary)
            context_runtime_root = pin_context.runtime_root
        else:
            pin_context = "unattested_legacy"
            context_runtime_root = _absolute_path(args.runtime_root or "", field="runtime root")
        root = _absolute_path(args.project_root, field="project root") if args.project_root else None
        try:
            value = context.resolve_top_level_context(
                root,
                runtime_root=context_runtime_root,
                loaded_pin=pin_context,
                expected=args.expected,
            )
            return json.loads(context.context_to_json(value))
        except Exception as exc:
            _raise_authority_error(exc)
    if args.command == "context-validate":
        caller_fields = (args.caller_state, args.caller_generation_sha256)
        if any(field is not None for field in caller_fields):
            if any(field is None for field in caller_fields) or args.project_root is None:
                raise BridgeError("context_tuple_incomplete", "caller-local context fields must be supplied together")
            # These are assertions about a shell-local carrier, never another
            # authority source.  Reject a malformed or mismatched carrier before
            # observing any runtime or target Git state, then retain the full
            # active recapture below in this same process.
            mapping = _envelope_mapping(_snapshot_only(), args.context)
            expected = {
                "state": args.caller_state,
                "project_root": args.project_root,
                "generation_sha256": args.caller_generation_sha256,
            }
            if any(mapping.get(key) != value for key, value in expected.items()):
                raise BridgeError("context_tuple_mismatch", "caller-local context fields differ from the envelope")
        context, value = _context_from_envelope(
            compact=args.context,
            runtime_summary=args.runtime_pin_summary,
            runtime_root=args.runtime_root,
            project_root=args.project_root,
            context_only_summary=True,
        )
        try:
            if args.format == "state":
                return value.state
            return json.loads(context.context_to_json(value))
        except Exception as exc:
            _raise_authority_error(exc)
    if args.command == "context-field":
        snapshot = _snapshot_only()
        mapping = _envelope_mapping(snapshot, args.context)
        value = _field_value(mapping, args.field)
        if type(value) is bool:
            return "true" if value else "false"
        return str(value)
    if args.command == "context-canonical":
        snapshot = _snapshot_only()
        return _canonical_json(_envelope_mapping(snapshot, args.context))
    if args.command == "context-bindings":
        snapshot = _snapshot_only()
        mapping = _envelope_mapping(snapshot, args.context)
        # ``parse_context_envelope`` rejects every ASCII control character in
        # the path/text fields.  A tab-delimited scalar is therefore safe for
        # zsh's ``read -r`` and avoids three independent parser processes for
        # the fixed caller-local tuple.  It is data, never shell source.
        return "\t".join(
            (
                str(mapping["state"]),
                str(mapping["project_root"]),
                str(mapping["generation_sha256"]),
            )
        )
    if args.command == "context-match":
        snapshot = _snapshot_only()
        mapping = _envelope_mapping(snapshot, args.context)
        expected = {
            "state": args.state,
            "project_root": args.project_root,
            "generation_sha256": args.generation_sha256,
        }
        if any(mapping.get(key) != value for key, value in expected.items()):
            raise BridgeError("context_tuple_mismatch", "caller-local context fields differ from the envelope")
        return {"ok": True}
    if args.command == "contract-path":
        context, value = _context_from_envelope(
            compact=args.context,
            runtime_summary=args.runtime_pin_summary,
            runtime_root=args.runtime_root,
            project_root=args.project_root,
        )
        try:
            return os.fspath(context.require_declared_read(value, args.relative_path, args.purpose))
        except Exception as exc:
            _raise_authority_error(exc)
    if args.command == "contract-root":
        _, value = _context_from_envelope(
            compact=args.context,
            runtime_summary=args.runtime_pin_summary,
            runtime_root=args.runtime_root,
            project_root=args.project_root,
        )
        return os.fspath(value.contract_root)
    if args.command == "contract-read":
        context, value = _context_from_envelope(
            compact=args.context,
            runtime_summary=args.runtime_pin_summary,
            runtime_root=args.runtime_root,
            project_root=args.project_root,
        )
        try:
            sys.stdout.buffer.write(context.read_declared_bytes(value, args.relative_path, args.purpose))
            return None
        except Exception as exc:
            _raise_authority_error(exc)
    if args.command == "receipt-validate":
        return _receipt_validate(args)
    raise BridgeError("unknown_command", "unsupported authority bridge command")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="contract_authority_bridge.py", add_help=True)
    subparsers = parser.add_subparsers(dest="command", required=True)
    shell_source = subparsers.add_parser("shell-source")
    shell_source.add_argument("--path", required=True)
    shell_source.add_argument("--runtime-root", required=True)
    shell_source.add_argument("--runtime-pin-summary")
    source_buffer = subparsers.add_parser("source-buffer")
    source_buffer.add_argument("--runtime-pin-summary", required=True)
    source_buffer.add_argument("--relative-path", required=True)
    shell_loader = subparsers.add_parser("shell-loader")
    shell_loader.add_argument("--runtime-pin-summary", required=True)
    python_entry = subparsers.add_parser("python-entry")
    python_entry.add_argument("--path", required=True)
    python_entry.add_argument("--runtime-pin-summary")
    python_entry.add_argument("entry_args", nargs=argparse.REMAINDER)
    python_stdin = subparsers.add_parser("python-stdin")
    python_stdin.add_argument("--runtime-pin-summary")
    python_stdin.add_argument("entry_args", nargs=argparse.REMAINDER)
    source = subparsers.add_parser("source-descriptor")
    source.add_argument("--path", required=True)
    source.add_argument("--runtime-root")
    source_verify = subparsers.add_parser("source-verify")
    source_verify.add_argument("--path", required=True)
    source_verify.add_argument("--descriptor", required=True)
    source_verify.add_argument("--runtime-root")
    runtime_pin = subparsers.add_parser("runtime-pin")
    runtime_pin.add_argument("--runtime-root", required=True)
    runtime_pin.add_argument("--entrypoint", required=True)
    runtime_verify = subparsers.add_parser("runtime-verify")
    runtime_verify.add_argument("--runtime-pin-summary", required=True)
    runtime_api = subparsers.add_parser("runtime-api")
    runtime_api.add_argument("--runtime-pin-summary", required=True)
    runtime_api.add_argument("--minimum", required=True, type=int)
    runtime_api.add_argument("--maximum", type=int)
    subparsers.add_parser("runtime-api-version")
    runtime_field = subparsers.add_parser("runtime-field")
    runtime_field.add_argument("--runtime-pin-summary", required=True)
    runtime_field.add_argument("--field", required=True)
    context = subparsers.add_parser("context")
    context.add_argument("--project-root")
    context.add_argument("--runtime-pin-summary")
    context.add_argument("--runtime-root")
    context.add_argument("--expected")
    context_validate = subparsers.add_parser("context-validate")
    context_validate.add_argument("--context", required=True)
    context_validate.add_argument("--runtime-pin-summary")
    context_validate.add_argument("--runtime-root")
    context_validate.add_argument("--project-root")
    context_validate.add_argument("--caller-state")
    context_validate.add_argument("--caller-generation-sha256")
    context_validate.add_argument("--format", choices=("json", "state"), default="json")
    context_field = subparsers.add_parser("context-field")
    context_field.add_argument("--context", required=True)
    context_field.add_argument("--field", required=True)
    context_canonical = subparsers.add_parser("context-canonical")
    context_canonical.add_argument("--context", required=True)
    context_bindings = subparsers.add_parser("context-bindings")
    context_bindings.add_argument("--context", required=True)
    context_match = subparsers.add_parser("context-match")
    context_match.add_argument("--context", required=True)
    context_match.add_argument("--state", required=True)
    context_match.add_argument("--project-root", required=True)
    context_match.add_argument("--generation-sha256", required=True)
    for name in ("contract-path", "contract-read", "contract-root"):
        item = subparsers.add_parser(name)
        item.add_argument("--context", required=True)
        item.add_argument("--runtime-pin-summary")
        item.add_argument("--runtime-root")
        item.add_argument("--project-root")
        if name != "contract-root":
            item.add_argument("--relative-path", required=True)
            item.add_argument("--purpose", default="contract")
    receipt = subparsers.add_parser("receipt-validate")
    receipt.add_argument("--project-root", required=True)
    receipt.add_argument("--session-key", required=True)
    receipt.add_argument("--sid", required=True)
    receipt.add_argument("--context")
    receipt.add_argument("--mode", choices=("engaged", "legacy"), required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        value = _command(args)
    except BridgeError as exc:
        print(f"contract_authority_bridge: {exc.code}: {exc}", file=sys.stderr)
        return 2
    except Exception:
        print("contract_authority_bridge: internal_error: authority bridge failed", file=sys.stderr)
        return 2
    if isinstance(value, _BinaryResponse):
        output = sys.stdout.buffer
        if value.header is not None:
            output.write(_canonical_json(value.header).encode("ascii", "strict"))
            output.write(b"\n")
        output.write(value.data)
        output.flush()
        return 0
    if value is None:
        return 0
    if isinstance(value, str):
        # Scalar output deliberately is not JSON.  It is consumed as one shell
        # field and context paths reject control characters in the context lane.
        sys.stdout.write(value)
        sys.stdout.write("\n")
    else:
        _emit(value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

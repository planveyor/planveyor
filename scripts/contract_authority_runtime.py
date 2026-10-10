"""Read-only runtime identity pins for the authority integration.

The shell bridge uses these observations before and after loading the facade.
The module identifies repository bytes; the loader is responsible for binding
the matching observations to the code loaded in the shell.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Literal


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


def _assert_alias_origin(module: object | None, expected: Path) -> None:
    if module is not None and not _module_has_expected_origin(module, expected):
        raise ImportError("authority module has an unsafe origin")


def _bind_authority_aliases(package_name: str, direct_name: str) -> None:
    """Expose this trusted file under both import spellings without a split."""

    if __name__ == "__main__":
        return
    package_is_local = _scripts_package_is_local()
    current = sys.modules[__name__]
    expected = _AUTHORITY_SCRIPTS_DIR / f"{direct_name}.py"
    _assert_alias_origin(current, expected)
    direct = sys.modules.get(direct_name)
    packaged = sys.modules.get(package_name)
    _assert_alias_origin(direct, expected)
    _assert_alias_origin(packaged, expected)
    if (direct is not None and direct is not current) or (packaged is not None and packaged is not current):
        raise ImportError("authority module aliases are split")
    sys.modules[direct_name] = current
    if package_is_local:
        sys.modules[package_name] = current


def _load_authority_module(package_name: str, direct_name: str) -> Any:
    """Load a sibling authority file without consulting an untrusted package."""

    package_is_local = _scripts_package_is_local()
    expected = _AUTHORITY_SCRIPTS_DIR / f"{direct_name}.py"
    direct = sys.modules.get(direct_name)
    packaged = sys.modules.get(package_name)
    _assert_alias_origin(direct, expected)
    _assert_alias_origin(packaged, expected)
    if direct is not None and packaged is not None and direct is not packaged:
        raise ImportError("authority module aliases are split")
    module = direct or packaged
    if module is None:
        script_dir = os.fspath(_AUTHORITY_SCRIPTS_DIR)
        if script_dir in sys.path:
            sys.path.remove(script_dir)
        sys.path.insert(0, script_dir)
        module = importlib.import_module(direct_name)
        _assert_alias_origin(module, expected)
    sys.modules[direct_name] = module
    if package_is_local:
        sys.modules[package_name] = module
    return module


_snapshot_authority = _load_authority_module(
    "scripts.contract_authority_snapshot", "contract_authority_snapshot"
)
_fs_identity = _load_authority_module("scripts.fs_object_identity", "fs_object_identity")

if TYPE_CHECKING:
    from contract_authority_snapshot import ContractAuthorityError, GitIdentity, GitIndexEntry, TrackedFileIdentity
    from fs_object_identity import ObjectIdentityError, snapshot_regular_or_absent
else:
    ContractAuthorityError = _snapshot_authority.ContractAuthorityError
    GitIdentity = _snapshot_authority.GitIdentity
    GitIndexEntry = _snapshot_authority.GitIndexEntry
    TrackedFileIdentity = _snapshot_authority.TrackedFileIdentity
    ObjectIdentityError = _fs_identity.ObjectIdentityError
    snapshot_regular_or_absent = _fs_identity.snapshot_regular_or_absent


# See the matching aliases in snapshot/context.  A bridge and direct reader
# can share types only when both spellings identify this exact sibling file.
_bind_authority_aliases("scripts.contract_authority_runtime", "contract_authority_runtime")


# Raw imports deliberately have no source capsule.  A supported bootstrap
# injects the exact bytes it compiled plus its retained core-buffer table;
# those observations are the only basis on which this module can attest an
# engaged runtime pin.
_FIRST_LOADED_SOURCE_OBSERVATION: Final[object | None] = (
    _fs_identity._capture_loaded_module_source_observation(
        sys.modules[__name__],
        expected_path=_AUTHORITY_SCRIPTS_DIR / "contract_authority_runtime.py",
        relative_path="scripts/contract_authority_runtime.py",
        source_capsule=globals().get("__authority_source_capsule__"),
        source_reader=globals().get("__authority_read_source__"),
    )
)


def _first_loaded_source_observation() -> object | None:
    """Return immutable buffer provenance recorded while this module loaded."""

    return _FIRST_LOADED_SOURCE_OBSERVATION


def _loaded_source_capsule(relative_path: str) -> object | None:
    """Return one bridge-injected core capsule without accepting a mutable map."""

    table = globals().get("__authority_loaded_source_capsules__")
    if type(table) is not tuple:
        return None
    found: object | None = None
    for item in table:
        if type(item) is not tuple or len(item) != 2:
            return None
        candidate_path, candidate = item
        if type(candidate_path) is not str:
            return None
        if candidate_path == relative_path:
            if found is not None:
                return None
            found = candidate
    return found


def _authority_source_data_from_pin(pin: LoadedRuntimePin, relative_path: str) -> bytes:
    """Read one allowlisted caller literal through the retained source reader."""

    normalized = _validate_loaded_runtime_pin(pin)
    observation = _first_loaded_runtime_observation()
    if observation.pin is None:
        raise _fail("runtime_pin_unattested", "loaded runtime has no retained source pin")
    if observation.pin != normalized or not _pre_runtime_module_observations_match_closure(normalized):
        raise _fail("runtime_loaded_code_drift", "loaded runtime source differs from the supplied pin")
    try:
        verified = verify_loaded_runtime_pin(normalized)
    except ContractAuthorityError:
        raise
    if verified != normalized:
        raise _fail("runtime_loaded_code_drift", "loaded runtime source differs from current runtime bytes")
    reader = globals().get("__authority_read_source__")
    if not callable(reader):
        raise _fail("runtime_pin_unattested", "loaded runtime has no source reader capability")
    row = next((item for item in normalized.closure_rows if item.path == relative_path), None)
    if row is None:
        raise _fail("runtime_loaded_code_drift", "runtime pin does not contain the required source")
    expected_path = _AUTHORITY_SCRIPTS_DIR.parent / relative_path
    try:
        source = reader(os.fspath(expected_path))
    except Exception as exc:
        raise _fail("runtime_loaded_code_drift", "required source cannot be read through the loader") from exc
    if not _fs_identity._source_capsule_matches_runtime_row(
        source,
        expected_path=expected_path,
        relative_path=relative_path,
        mode=row.mode,
        sha256=row.sha256,
    ):
        raise _fail("runtime_loaded_code_drift", "required source differs from the supplied pin")
    try:
        return source[3]
    except (IndexError, TypeError) as exc:
        raise _fail("runtime_loaded_code_drift", "required source capsule is malformed") from exc


def authority_bootstrap_literal(pin: LoadedRuntimePin) -> str:
    """Return the trusted bootstrap literal bound to one loaded runtime pin.

    The bootstrap source is deliberately caller data, not a source file that
    attests itself.  A supported parent may copy this exact retained literal
    into a fresh ``python -I -B -c`` child only after its active context has
    already validated the supplied pin.
    """

    try:
        return _authority_source_data_from_pin(pin, "scripts/contract_authority_bootstrap.py").decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise _fail("runtime_loaded_code_drift", "bootstrap source is not valid Python text") from exc


def authority_shell_loader_literal(pin: LoadedRuntimePin) -> str:
    """Render the parent-owned shell loader with one row-verified bootstrap."""

    try:
        template = _authority_source_data_from_pin(pin, "scripts/contract_authority_shell_loader.zsh").decode(
            "utf-8", "strict"
        )
    except UnicodeDecodeError as exc:
        raise _fail("runtime_loaded_code_drift", "shell loader template is not valid UTF-8") from exc
    marker = "@PLANVEYOR_AUTHORITY_BOOTSTRAP_LITERAL@"
    if template.count(marker) != 1:
        raise _fail("runtime_loaded_code_drift", "shell loader template has an invalid bootstrap placeholder")
    return template.replace(marker, authority_bootstrap_literal(pin))


# This is a reviewed runtime ABI constant, not caller input.
RUNTIME_API_VERSION: Final[int] = 5
RUNTIME_PIN_SCHEMA_VERSION: Final[int] = 1
RUNTIME_PIN_SUMMARY_SCHEMA_VERSION: Final[str] = "planveyor_runtime_pin_summary.v1"
GIT_COMMAND_TIMEOUT_SECONDS: Final[float] = 10.0

_REGULAR_GIT_MODES: Final[frozenset[str]] = frozenset({"100644", "100755"})
_GIT_MODE_RE: Final[re.Pattern[str]] = re.compile(r"^[0-7]{6}$")

# Every tracked regular file below ``scripts/`` is part of the conservative
# repository-owned runtime closure.  These paths document the fixed external
# loader inputs and make their absence fail before a caller can load anything.
_EXTERNAL_RUNTIME_INPUT_PATHS: Final[tuple[str, ...]] = (
    "docs/_meta/runner_selection_resolution.v1.json",
)
_REQUIRED_SCRIPT_PATHS: Final[tuple[str, ...]] = (
    "scripts/planveyor.zsh",
    "scripts/planveyor/docs_finalize.zsh",
    "scripts/planveyor/role_runtime.zsh",
    "scripts/planveyor/session_init.zsh",
    "scripts/contract_authority_snapshot.py",
    "scripts/fs_object_identity.py",
    "scripts/contract_authority_runtime.py",
    "scripts/contract_authority_context.py",
    "scripts/contract_authority_bridge.py",
    "scripts/contract_authority_bootstrap.py",
    "scripts/contract_authority_shell_loader.zsh",
    "scripts/planveyor/contract_authority.zsh",
)
REQUIRED_RUNTIME_PATHS: Final[tuple[str, ...]] = tuple(
    sorted((*_EXTERNAL_RUNTIME_INPUT_PATHS, *_REQUIRED_SCRIPT_PATHS))
)


def _canonical_json_bytes(value: object) -> bytes:
    """Encode structural pin data deterministically, without a JSON CLI."""

    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


_CLOSURE_SPEC: Final[dict[str, object]] = {
    "schema_version": RUNTIME_PIN_SCHEMA_VERSION,
    "selector": {
        "all_tracked_regular_files_below": ["scripts"],
        "explicit_runtime_inputs": list(_EXTERNAL_RUNTIME_INPUT_PATHS),
    },
    "required_paths": list(REQUIRED_RUNTIME_PATHS),
}
RUNTIME_CLOSURE_SPEC_SHA256: Final[str] = hashlib.sha256(
    _canonical_json_bytes(_CLOSURE_SPEC)
).hexdigest()


@dataclass(frozen=True, slots=True)
class RuntimeClosureRow:
    """One descriptor-read runtime input, relative to the runtime Git root."""

    path: str
    mode: Literal["100644", "100755"]
    blob_oid: str
    sha256: str


@dataclass(frozen=True, slots=True)
class LoadedRuntimePin:
    """An immutable, verifiable observation of one runtime repository closure."""

    runtime_root: Path
    git_dir: Path
    runtime_api_version: int
    commit: str
    tree: str
    closure_spec_sha256: str
    closure_rows: tuple[RuntimeClosureRow, ...]
    closure_rows_sha256: str
    closure_sha256: str
    pin_sha256: str
    # Evidence from the capture, deliberately excluded from semantic equality
    # and pin_sha256: staging unrelated docs must not change runtime authority.
    observed_index_sha256: str | None = field(default=None, compare=False)


@dataclass(frozen=True, slots=True)
class _FirstLoadedRuntimeObservation:
    """The runtime closure available when this Python code was first imported."""

    runtime_root: Path
    pin: LoadedRuntimePin | None


@dataclass(frozen=True, slots=True)
class _GitBasis:
    root: Path
    git_dir: Path
    head: str
    tree: str
    index_sha256: str


@dataclass(frozen=True, slots=True)
class _GitTreeEntry:
    path: str
    mode: str
    blob_oid: str


@dataclass(frozen=True, slots=True)
class _GitIndexEntry:
    path: str
    mode: str
    blob_oid: str
    stage: int


def _fail(reason_code: str, message: str) -> ContractAuthorityError:
    return ContractAuthorityError(reason_code, message)


def _run_git(root: Path, *arguments: str, context: str) -> bytes:
    """Run fixed, read-only Git plumbing with A's sanitized environment."""

    command = [
        "git",
        "--literal-pathspecs",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "fetch.writeCommitGraph=false",
        "-C",
        os.fspath(root),
        "--no-optional-locks",
        *arguments,
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_snapshot_authority._clean_git_environment(),
            timeout=GIT_COMMAND_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise _fail("git_timeout", f"Git timed out while reading {context}") from exc
    except OSError as exc:
        raise _fail("git_unavailable", f"cannot run Git for {context}") from exc
    if completed.returncode != 0:
        raise _fail("git_command_failed", f"Git failed while reading {context}")
    return completed.stdout


def _single_text_line(data: bytes, *, context: str) -> str:
    try:
        text = data.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise _fail("git_output_invalid", f"Git returned non-text {context}") from exc
    if not text.endswith("\n") or text.count("\n") != 1:
        raise _fail("git_output_invalid", f"Git returned ambiguous {context}")
    value = text[:-1]
    if not value or "\x00" in value:
        raise _fail("git_output_invalid", f"Git returned invalid {context}")
    return value


def _text_lines(data: bytes, *, context: str, expected_count: int) -> tuple[str, ...]:
    try:
        text = data.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise _fail("git_output_invalid", f"Git returned non-text {context}") from exc
    if not text.endswith("\n") or "\x00" in text:
        raise _fail("git_output_invalid", f"Git returned invalid {context}")
    lines = tuple(text[:-1].split("\n"))
    if len(lines) != expected_count or any(not line for line in lines):
        raise _fail("git_output_invalid", f"Git returned ambiguous {context}")
    return lines


def _validate_object_id(value: object, *, field: str) -> str:
    return _snapshot_authority._validate_object_id(value, field=field)


def _validate_sha256(value: object, *, field: str) -> str:
    return _snapshot_authority._validate_sha256(value, field=field)


def _validate_relative_path(value: object, *, field: str) -> str:
    return _snapshot_authority._validate_relative_path(value, field=field)


def _validate_mode(value: object, *, field: str) -> Literal["100644", "100755"]:
    return _snapshot_authority._validate_mode(value, field=field)


def _validate_int(value: object, *, field: str) -> int:
    return _snapshot_authority._validate_int(value, field=field)


def _resolved_directory(value: object, *, context: str) -> Path:
    return _snapshot_authority._resolved_directory(value, context=context)


def _canonical_pin_directory(value: object, *, field: str) -> Path:
    if not isinstance(value, Path):
        raise _fail("invalid_runtime_pin", f"{field} must be a pathlib.Path")
    resolved = _resolved_directory(value, context=field)
    if resolved != value:
        raise _fail("runtime_pin_path_not_canonical", f"{field} is not canonical")
    return resolved


def _nul_records(data: bytes, *, context: str) -> tuple[bytes, ...]:
    if not data:
        return ()
    if not data.endswith(b"\0"):
        raise _fail("git_output_invalid", f"Git returned unterminated NUL records for {context}")
    records = tuple(data[:-1].split(b"\0"))
    if any(not record for record in records):
        raise _fail("git_output_invalid", f"Git returned an empty NUL record for {context}")
    return records


def _decode_git_path(value: bytes, *, context: str) -> str:
    try:
        decoded = value.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise _fail("git_output_invalid", f"Git returned a non-UTF-8 path for {context}") from exc
    return _validate_relative_path(decoded, field=f"Git {context} path")


def _git_root_and_dir(runtime_root: Path) -> tuple[Path, Path]:
    requested_root = _resolved_directory(runtime_root, context="runtime")
    inside, top_text, git_dir_text = _text_lines(
        _run_git(
            requested_root,
            "rev-parse",
            "--is-inside-work-tree",
            "--show-toplevel",
            "--absolute-git-dir",
            context="runtime Git root",
        ),
        context="runtime Git root",
        expected_count=3,
    )
    if inside != "true":
        raise _fail("git_non_worktree", "runtime root is not a Git worktree")
    top_path = Path(top_text)
    git_dir_path = Path(git_dir_text)
    if not top_path.is_absolute() or not git_dir_path.is_absolute():
        raise _fail("git_output_invalid", "Git returned a non-absolute runtime path")
    top = _resolved_directory(top_path, context="runtime Git top-level")
    git_dir = _resolved_directory(git_dir_path, context="runtime Git directory")
    if top != requested_root:
        raise _fail("git_root_mismatch", "runtime root is not the verified Git top-level")
    return top, git_dir


def _git_object_id(root: Path, expression: str, *, context: str) -> str:
    return _validate_object_id(
        _single_text_line(
            _run_git(root, "rev-parse", "--verify", expression, context=context),
            context=context,
        ),
        field=context,
    )


def _index_digest(index_text: str, git_dir: Path) -> str:
    """Hash the index path emitted by the one fixed basis command."""

    index_path = Path(index_text)
    if not index_path.is_absolute():
        raise _fail("git_output_invalid", "Git returned a non-absolute index path")
    try:
        index_relative = index_path.relative_to(git_dir).as_posix()
    except ValueError as exc:
        raise _fail("git_index_path_invalid", "Git index is outside its verified Git directory") from exc
    _validate_relative_path(index_relative, field="runtime Git index path")
    try:
        # Git's path reporters resolve an index symlink before returning an
        # absolute path.  The fixed repository-owned index is lexical
        # ``git_dir/index`` and must itself be descriptor-safe.
        snapshot = snapshot_regular_or_absent(git_dir, "index")
    except ObjectIdentityError as exc:
        raise _fail(exc.reason_code, "runtime Git index cannot be safely observed") from exc
    if snapshot.state != "regular" or snapshot.data is None:
        raise _fail("index_missing", "runtime Git index is absent")
    if index_path != git_dir / "index":
        raise _fail("git_index_path_invalid", "Git reported a non-canonical runtime index path")
    return hashlib.sha256(snapshot.data).hexdigest()


def _capture_git_basis(runtime_root: Path) -> _GitBasis:
    requested_root = _resolved_directory(runtime_root, context="runtime")
    inside, top_text, git_dir_text, index_text, head_text, tree_text = _text_lines(
        _run_git(
            requested_root,
            "rev-parse",
            "--revs-only",
            "--path-format=absolute",
            "--is-inside-work-tree",
            "--show-toplevel",
            "--absolute-git-dir",
            "--git-path",
            "index",
            "--end-of-options",
            "HEAD^{commit}",
            "HEAD^{tree}",
            context="runtime Git basis",
        ),
        context="runtime Git basis",
        expected_count=6,
    )
    if inside != "true":
        raise _fail("git_non_worktree", "runtime root is not a Git worktree")
    top_path = Path(top_text)
    git_dir_path = Path(git_dir_text)
    if not top_path.is_absolute() or not git_dir_path.is_absolute():
        raise _fail("git_output_invalid", "Git returned a non-absolute runtime path")
    root = _resolved_directory(top_path, context="runtime Git top-level")
    git_dir = _resolved_directory(git_dir_path, context="runtime Git directory")
    if root != requested_root:
        raise _fail("git_root_mismatch", "runtime root is not the verified Git top-level")
    return _GitBasis(
        root=root,
        git_dir=git_dir,
        head=_validate_object_id(head_text, field="runtime HEAD"),
        tree=_validate_object_id(tree_text, field="runtime HEAD tree"),
        index_sha256=_index_digest(index_text, git_dir),
    )


def _recheck_git_basis(before: _GitBasis) -> _GitBasis:
    after = _capture_git_basis(before.root)
    if after != before:
        raise _fail(
            "snapshot_changed_during_read",
            "runtime Git HEAD, tree, index, root, or Git directory changed while reading",
        )
    return after


def _is_closure_path(path: str) -> bool:
    return path.startswith("scripts/") or path in _EXTERNAL_RUNTIME_INPUT_PATHS


def _parse_tree_entries(data: bytes) -> dict[str, _GitTreeEntry]:
    entries: dict[str, _GitTreeEntry] = {}
    for record in _nul_records(data, context="runtime HEAD closure"):
        try:
            description, path_bytes = record.split(b"\t", 1)
            mode_bytes, kind_bytes, oid_bytes = description.split(b" ")
            mode = mode_bytes.decode("ascii", "strict")
            kind = kind_bytes.decode("ascii", "strict")
            blob_oid = oid_bytes.decode("ascii", "strict")
        except (UnicodeDecodeError, ValueError) as exc:
            raise _fail("git_output_invalid", "runtime HEAD closure entry is malformed") from exc
        path = _decode_git_path(path_bytes, context="runtime HEAD closure")
        if not _is_closure_path(path):
            raise _fail("git_output_invalid", "Git returned a path outside the runtime closure")
        if path in entries:
            raise _fail("git_output_invalid", f"Git repeated runtime closure path: {path}")
        if kind != "blob" or mode not in _REGULAR_GIT_MODES:
            raise _fail("runtime_closure_non_regular", f"runtime closure path is not regular: {path}")
        entries[path] = _GitTreeEntry(
            path=path,
            mode=mode,
            blob_oid=_validate_object_id(blob_oid, field=f"runtime HEAD blob {path}"),
        )
    return entries


def _read_tree_entries(basis: _GitBasis) -> dict[str, _GitTreeEntry]:
    return _parse_tree_entries(
        _run_git(
            basis.root,
            "ls-tree",
            "-r",
            "-z",
            "HEAD",
            "--",
            "scripts",
            *_EXTERNAL_RUNTIME_INPUT_PATHS,
            context="runtime HEAD closure",
        )
    )


def _parse_index_entries(data: bytes) -> dict[str, tuple[_GitIndexEntry, ...]]:
    grouped: dict[str, list[_GitIndexEntry]] = {}
    seen_stages: set[tuple[str, int]] = set()
    for record in _nul_records(data, context="runtime index closure"):
        try:
            description, path_bytes = record.split(b"\t", 1)
            mode_bytes, oid_bytes, stage_bytes = description.split(b" ")
            mode = mode_bytes.decode("ascii", "strict")
            blob_oid = oid_bytes.decode("ascii", "strict")
            stage = int(stage_bytes.decode("ascii", "strict"), 10)
        except (UnicodeDecodeError, ValueError) as exc:
            raise _fail("git_output_invalid", "runtime index closure entry is malformed") from exc
        path = _decode_git_path(path_bytes, context="runtime index closure")
        if not _is_closure_path(path):
            raise _fail("git_output_invalid", "Git returned a path outside the runtime closure")
        if _GIT_MODE_RE.fullmatch(mode) is None or stage not in {0, 1, 2, 3}:
            raise _fail("git_index_entry_invalid", f"runtime index entry is invalid: {path}")
        key = (path, stage)
        if key in seen_stages:
            raise _fail("git_index_entry_ambiguous", f"runtime index repeats a stage: {path}")
        seen_stages.add(key)
        grouped.setdefault(path, []).append(
            _GitIndexEntry(
                path=path,
                mode=mode,
                blob_oid=_validate_object_id(blob_oid, field=f"runtime index blob {path}"),
                stage=stage,
            )
        )
    return {path: tuple(entries) for path, entries in grouped.items()}


def _read_index_entries(basis: _GitBasis) -> dict[str, tuple[_GitIndexEntry, ...]]:
    return _parse_index_entries(
        _run_git(
            basis.root,
            "ls-files",
            "--stage",
            "-z",
            "--",
            "scripts",
            *_EXTERNAL_RUNTIME_INPUT_PATHS,
            context="runtime index closure",
        )
    )


def _normalize_requested_paths(paths: tuple[str, ...]) -> tuple[str, ...]:
    if type(paths) is not tuple or not paths:
        raise _fail("invalid_tracked_content_paths", "paths must be a non-empty immutable tuple")
    normalized: list[str] = []
    seen: set[str] = set()
    for position, value in enumerate(paths):
        path = _validate_relative_path(value, field=f"paths[{position}]")
        if path in seen:
            raise _fail("duplicate_tracked_content_path", f"paths repeats {path}")
        seen.add(path)
        normalized.append(path)
    return tuple(sorted(normalized))


def _parse_exact_tree_entries(
    data: bytes,
    *,
    requested_paths: frozenset[str],
) -> dict[str, _GitTreeEntry]:
    entries: dict[str, _GitTreeEntry] = {}
    for record in _nul_records(data, context="tracked content HEAD"):
        try:
            description, path_bytes = record.split(b"\t", 1)
            mode_bytes, kind_bytes, oid_bytes = description.split(b" ")
            mode = mode_bytes.decode("ascii", "strict")
            kind = kind_bytes.decode("ascii", "strict")
            blob_oid = oid_bytes.decode("ascii", "strict")
        except (UnicodeDecodeError, ValueError) as exc:
            raise _fail("git_output_invalid", "tracked content HEAD entry is malformed") from exc
        path = _decode_git_path(path_bytes, context="tracked content HEAD")
        if path not in requested_paths:
            raise _fail("git_output_invalid", "Git returned an unexpected tracked content path")
        if path in entries:
            raise _fail("git_output_invalid", f"Git repeated tracked content path: {path}")
        if kind != "blob" or mode not in _REGULAR_GIT_MODES:
            raise _fail("tracked_content_non_regular", f"tracked content path is not regular: {path}")
        entries[path] = _GitTreeEntry(
            path=path,
            mode=mode,
            blob_oid=_validate_object_id(blob_oid, field=f"tracked content HEAD blob {path}"),
        )
    return entries


def _parse_exact_index_entries(
    data: bytes,
    *,
    requested_paths: frozenset[str],
) -> dict[str, tuple[_GitIndexEntry, ...]]:
    grouped: dict[str, list[_GitIndexEntry]] = {}
    seen_stages: set[tuple[str, int]] = set()
    for record in _nul_records(data, context="tracked content index"):
        try:
            description, path_bytes = record.split(b"\t", 1)
            mode_bytes, oid_bytes, stage_bytes = description.split(b" ")
            mode = mode_bytes.decode("ascii", "strict")
            blob_oid = oid_bytes.decode("ascii", "strict")
            stage = int(stage_bytes.decode("ascii", "strict"), 10)
        except (UnicodeDecodeError, ValueError) as exc:
            raise _fail("git_output_invalid", "tracked content index entry is malformed") from exc
        path = _decode_git_path(path_bytes, context="tracked content index")
        if path not in requested_paths:
            raise _fail("git_output_invalid", "Git returned an unexpected tracked content path")
        if _GIT_MODE_RE.fullmatch(mode) is None or stage not in {0, 1, 2, 3}:
            raise _fail("git_index_entry_invalid", f"tracked content index entry is invalid: {path}")
        key = (path, stage)
        if key in seen_stages:
            raise _fail("git_index_entry_ambiguous", f"tracked content index repeats a stage: {path}")
        seen_stages.add(key)
        grouped.setdefault(path, []).append(
            _GitIndexEntry(
                path=path,
                mode=mode,
                blob_oid=_validate_object_id(blob_oid, field=f"tracked content index blob {path}"),
                stage=stage,
            )
        )
    return {path: tuple(entries) for path, entries in grouped.items()}


def _capture_tracked_content_once(
    root: Path,
    paths: tuple[str, ...],
) -> tuple[GitIdentity, tuple[TrackedFileIdentity, ...]]:
    basis = _capture_git_basis(root)
    requested = frozenset(paths)
    tree_entries = _parse_exact_tree_entries(
        _run_git(
            basis.root,
            "ls-tree",
            "-r",
            "-z",
            "HEAD",
            "--",
            *paths,
            context="tracked content HEAD",
        ),
        requested_paths=requested,
    )
    index_entries = _parse_exact_index_entries(
        _run_git(
            basis.root,
            "ls-files",
            "--stage",
            "-z",
            "--",
            *paths,
            context="tracked content index",
        ),
        requested_paths=requested,
    )
    for path in paths:
        head = tree_entries.get(path)
        if head is None:
            if path in index_entries:
                raise _fail("tracked_content_index_only", f"tracked content is index-only: {path}")
            raise _fail("tracked_content_missing_from_head", f"tracked content is absent from HEAD: {path}")
        entries = index_entries.get(path)
        if not entries:
            raise _fail("tracked_content_missing_from_index", f"tracked content is absent from index: {path}")
        if any(entry.stage != 0 for entry in entries):
            raise _fail("tracked_content_unmerged", f"tracked content is unmerged: {path}")
        if len(entries) != 1:
            raise _fail("git_index_entry_ambiguous", f"tracked content is ambiguous: {path}")
        index = entries[0]
        if index.mode not in _REGULAR_GIT_MODES:
            raise _fail("tracked_content_non_regular", f"tracked content index path is not regular: {path}")
        if index.mode != head.mode or index.blob_oid != head.blob_oid:
            raise _fail("tracked_content_index_mismatch", f"tracked content index differs from HEAD: {path}")

    rows = tuple(_observe_worktree_row(basis.root, tree_entries[path]) for path in paths)
    stable_basis = _recheck_git_basis(basis)
    index_evidence = tuple(
        GitIndexEntry(
            path=path,
            mode=index_entries[path][0].mode,
            blob_oid=index_entries[path][0].blob_oid,
            stage=0,
        )
        for path in paths
    )
    git = GitIdentity(
        root=stable_basis.root,
        git_dir=stable_basis.git_dir,
        head=stable_basis.head,
        tree=stable_basis.tree,
        index_sha256=stable_basis.index_sha256,
        index_entries=index_evidence,
    )
    identities = tuple(
        TrackedFileIdentity(
            path=row.path,
            mode=row.mode,
            blob_oid=row.blob_oid,
            sha256=row.sha256,
        )
        for row in rows
    )
    return git, identities


def capture_tracked_content(
    root: Path,
    paths: tuple[str, ...],
) -> tuple[GitIdentity, tuple[TrackedFileIdentity, ...]]:
    """Capture exact tracked rows using the runtime pin's batched primitives.

    ``GitIdentity.index_sha256`` is returned as entry evidence.  It is checked
    before and after each complete observation and between both observations.
    Callers compare the returned content rows separately when admitting an
    unrelated index change between independent invocations.
    """

    normalized_paths = _normalize_requested_paths(paths)
    first_git, first_rows = _capture_tracked_content_once(root, normalized_paths)
    second_git, second_rows = _capture_tracked_content_once(first_git.root, normalized_paths)
    if first_git != second_git or first_rows != second_rows:
        raise _fail("snapshot_changed_during_capture", "tracked content changed between observations")
    return second_git, second_rows


def _verify_index_matches_tree(
    tree_entries: dict[str, _GitTreeEntry],
    index_entries: dict[str, tuple[_GitIndexEntry, ...]],
) -> None:
    for path in index_entries:
        if path not in tree_entries:
            raise _fail(
                "runtime_closure_index_only",
                f"runtime closure has an index-only path: {path}",
            )
    for path, head in tree_entries.items():
        entries = index_entries.get(path)
        if not entries:
            raise _fail(
                "runtime_closure_missing_from_index",
                f"runtime closure path is absent from the index: {path}",
            )
        if any(entry.stage != 0 for entry in entries):
            raise _fail("runtime_closure_unmerged", f"runtime closure path is unmerged: {path}")
        if len(entries) != 1:
            raise _fail("git_index_entry_ambiguous", f"runtime closure path is ambiguous: {path}")
        index = entries[0]
        if index.mode not in _REGULAR_GIT_MODES:
            raise _fail("runtime_closure_non_regular", f"runtime closure index path is not regular: {path}")
        if index.mode != head.mode or index.blob_oid != head.blob_oid:
            raise _fail(
                "runtime_closure_index_mismatch",
                f"runtime closure index differs from HEAD: {path}",
            )


def _git_blob_oid_from_data(data: bytes) -> str:
    """Return the exact SHA-1 object name for a Git ``blob`` payload."""

    header = b"blob " + str(len(data)).encode("ascii") + b"\0"
    return hashlib.sha1(header + data).hexdigest()


def _observe_worktree_row(root: Path, head: _GitTreeEntry) -> RuntimeClosureRow:
    try:
        snapshot = snapshot_regular_or_absent(root, head.path)
    except ObjectIdentityError as exc:
        raise _fail(exc.reason_code, f"runtime closure path cannot be safely observed: {head.path}") from exc
    if snapshot.state != "regular" or snapshot.data is None or snapshot.git_mode is None:
        raise _fail(
            "runtime_closure_missing_from_worktree",
            f"runtime closure path is absent from the worktree: {head.path}",
        )
    if snapshot.git_mode != head.mode:
        raise _fail(
            "runtime_closure_worktree_mode_mismatch",
            f"runtime closure worktree mode differs from HEAD: {head.path}",
        )
    if _git_blob_oid_from_data(snapshot.data) != head.blob_oid:
        raise _fail(
            "runtime_closure_worktree_blob_mismatch",
            f"runtime closure worktree bytes differ from HEAD: {head.path}",
        )
    return RuntimeClosureRow(
        path=head.path,
        mode=_validate_mode(head.mode, field=f"runtime HEAD mode {head.path}"),
        blob_oid=head.blob_oid,
        sha256=hashlib.sha256(snapshot.data).hexdigest(),
    )


def _observe_closure_rows(basis: _GitBasis) -> tuple[RuntimeClosureRow, ...]:
    tree_entries = _read_tree_entries(basis)
    missing_required = [path for path in REQUIRED_RUNTIME_PATHS if path not in tree_entries]
    if missing_required:
        raise _fail(
            "runtime_closure_missing_required",
            f"runtime closure is missing required path: {missing_required[0]}",
        )
    index_entries = _read_index_entries(basis)
    _verify_index_matches_tree(tree_entries, index_entries)
    return tuple(_observe_worktree_row(basis.root, tree_entries[path]) for path in sorted(tree_entries))


def _closure_rows_payload(rows: tuple[RuntimeClosureRow, ...]) -> list[dict[str, str]]:
    return [
        {
            "path": row.path,
            "mode": row.mode,
            "blob_oid": row.blob_oid,
            "sha256": row.sha256,
        }
        for row in sorted(rows, key=lambda value: value.path)
    ]


def _closure_rows_digest(rows: tuple[RuntimeClosureRow, ...]) -> str:
    return hashlib.sha256(
        _canonical_json_bytes(
            {
                "schema_version": RUNTIME_PIN_SCHEMA_VERSION,
                "rows": _closure_rows_payload(rows),
            }
        )
    ).hexdigest()


def _closure_digest(*, closure_spec_sha256: str, closure_rows_sha256: str) -> str:
    return hashlib.sha256(
        _canonical_json_bytes(
            {
                "closure_rows_sha256": closure_rows_sha256,
                "closure_spec_sha256": closure_spec_sha256,
                "schema_version": RUNTIME_PIN_SCHEMA_VERSION,
            }
        )
    ).hexdigest()


def _pin_body(pin: LoadedRuntimePin) -> dict[str, object]:
    return {
        "schema_version": RUNTIME_PIN_SCHEMA_VERSION,
        "runtime_root": os.fspath(pin.runtime_root),
        "git_dir": os.fspath(pin.git_dir),
        "runtime_api_version": pin.runtime_api_version,
        "commit": pin.commit,
        "tree": pin.tree,
        "closure_spec_sha256": pin.closure_spec_sha256,
        "closure_rows": _closure_rows_payload(pin.closure_rows),
        "closure_rows_sha256": pin.closure_rows_sha256,
        "closure_sha256": pin.closure_sha256,
    }


def _pin_digest(pin: LoadedRuntimePin) -> str:
    return hashlib.sha256(_canonical_json_bytes(_pin_body(pin))).hexdigest()


def _build_pin(basis: _GitBasis, rows: tuple[RuntimeClosureRow, ...]) -> LoadedRuntimePin:
    rows_sha256 = _closure_rows_digest(rows)
    closure_sha256 = _closure_digest(
        closure_spec_sha256=RUNTIME_CLOSURE_SPEC_SHA256,
        closure_rows_sha256=rows_sha256,
    )
    provisional = LoadedRuntimePin(
        runtime_root=basis.root,
        git_dir=basis.git_dir,
        runtime_api_version=RUNTIME_API_VERSION,
        commit=basis.head,
        tree=basis.tree,
        closure_spec_sha256=RUNTIME_CLOSURE_SPEC_SHA256,
        closure_rows=rows,
        closure_rows_sha256=rows_sha256,
        closure_sha256=closure_sha256,
        pin_sha256="",
        observed_index_sha256=basis.index_sha256,
    )
    return LoadedRuntimePin(
        runtime_root=provisional.runtime_root,
        git_dir=provisional.git_dir,
        runtime_api_version=provisional.runtime_api_version,
        commit=provisional.commit,
        tree=provisional.tree,
        closure_spec_sha256=provisional.closure_spec_sha256,
        closure_rows=provisional.closure_rows,
        closure_rows_sha256=provisional.closure_rows_sha256,
        closure_sha256=provisional.closure_sha256,
        pin_sha256=_pin_digest(provisional),
        observed_index_sha256=provisional.observed_index_sha256,
    )


def _capture_loaded_runtime_pin_once(runtime_root: Path) -> tuple[LoadedRuntimePin, _GitBasis]:
    basis = _capture_git_basis(runtime_root)
    rows = _observe_closure_rows(basis)
    stable_basis = _recheck_git_basis(basis)
    return _build_pin(stable_basis, rows), stable_basis


def _validate_loaded_runtime_pin(pin: LoadedRuntimePin) -> LoadedRuntimePin:
    if type(pin) is not LoadedRuntimePin:
        raise _fail("invalid_runtime_pin", "pin must be a LoadedRuntimePin")
    root = _canonical_pin_directory(pin.runtime_root, field="runtime_root")
    git_dir = _canonical_pin_directory(pin.git_dir, field="git_dir")
    runtime_api_version = _validate_int(pin.runtime_api_version, field="runtime_api_version")
    if runtime_api_version != RUNTIME_API_VERSION:
        raise _fail("runtime_api_mismatch", "pin runtime API differs from the reviewed API")
    commit = _validate_object_id(pin.commit, field="commit")
    tree = _validate_object_id(pin.tree, field="tree")
    closure_spec_sha256 = _validate_sha256(pin.closure_spec_sha256, field="closure_spec_sha256")
    if closure_spec_sha256 != RUNTIME_CLOSURE_SPEC_SHA256:
        raise _fail("runtime_closure_spec_mismatch", "pin closure specification differs from reviewed source")
    if type(pin.closure_rows) is not tuple or not pin.closure_rows:
        raise _fail("invalid_runtime_pin", "pin closure rows must be a non-empty immutable tuple")
    rows: list[RuntimeClosureRow] = []
    seen_paths: set[str] = set()
    for position, row in enumerate(pin.closure_rows):
        if type(row) is not RuntimeClosureRow:
            raise _fail("invalid_runtime_pin", f"pin closure row {position} is invalid")
        path = _validate_relative_path(row.path, field=f"closure_rows[{position}].path")
        if not _is_closure_path(path):
            raise _fail("invalid_runtime_pin", f"pin closure row lies outside the runtime closure: {path}")
        if path in seen_paths:
            raise _fail("invalid_runtime_pin", f"pin closure repeats a path: {path}")
        seen_paths.add(path)
        rows.append(
            RuntimeClosureRow(
                path=path,
                mode=_validate_mode(row.mode, field=f"closure_rows[{position}].mode"),
                blob_oid=_validate_object_id(row.blob_oid, field=f"closure_rows[{position}].blob_oid"),
                sha256=_validate_sha256(row.sha256, field=f"closure_rows[{position}].sha256"),
            )
        )
    if tuple(row.path for row in rows) != tuple(sorted(row.path for row in rows)):
        raise _fail("runtime_pin_rows_not_canonical", "pin closure rows are not sorted by path")
    missing_required = [path for path in REQUIRED_RUNTIME_PATHS if path not in seen_paths]
    if missing_required:
        raise _fail(
            "runtime_closure_missing_required",
            f"pin closure is missing required path: {missing_required[0]}",
        )
    normalized = LoadedRuntimePin(
        runtime_root=root,
        git_dir=git_dir,
        runtime_api_version=runtime_api_version,
        commit=commit,
        tree=tree,
        closure_spec_sha256=closure_spec_sha256,
        closure_rows=tuple(rows),
        closure_rows_sha256=_validate_sha256(pin.closure_rows_sha256, field="closure_rows_sha256"),
        closure_sha256=_validate_sha256(pin.closure_sha256, field="closure_sha256"),
        pin_sha256=_validate_sha256(pin.pin_sha256, field="pin_sha256"),
        observed_index_sha256=(None if pin.observed_index_sha256 is None else
                               _validate_sha256(pin.observed_index_sha256, field="observed_index_sha256")),
    )
    if normalized.closure_rows_sha256 != _closure_rows_digest(normalized.closure_rows):
        raise _fail("runtime_pin_digest_mismatch", "pin closure row digest is invalid")
    if normalized.closure_sha256 != _closure_digest(
        closure_spec_sha256=normalized.closure_spec_sha256,
        closure_rows_sha256=normalized.closure_rows_sha256,
    ):
        raise _fail("runtime_pin_digest_mismatch", "pin closure digest is invalid")
    if normalized.pin_sha256 != _pin_digest(normalized):
        raise _fail("runtime_pin_digest_mismatch", "pin digest is invalid")
    return normalized


def capture_loaded_runtime_pin(runtime_root: Path) -> LoadedRuntimePin:
    """Capture two complete, matching runtime observations without writing.

    Each observation captures and rechecks the raw Git index around its full
    tree/index/descriptor read. The raw index digest is recorded as observation
    evidence, separate from semantic pin equality and the pin digest.
    """

    first, first_basis = _capture_loaded_runtime_pin_once(runtime_root)
    second, second_basis = _capture_loaded_runtime_pin_once(first.runtime_root)
    if first_basis != second_basis or first != second:
        raise _fail(
            "snapshot_changed_during_capture",
            "runtime closure changed between complete observations",
        )
    return second


def verify_loaded_runtime_pin(pin: LoadedRuntimePin) -> LoadedRuntimePin:
    """Re-capture a stored runtime pin and require exact canonical equality."""

    expected = _validate_loaded_runtime_pin(pin)
    current = capture_loaded_runtime_pin(expected.runtime_root)
    if current != expected:
        raise _fail("runtime_pin_mismatch", "current runtime differs from the loaded runtime pin")
    return current


def _pre_runtime_module_observations_match_closure(pin: LoadedRuntimePin) -> bool:
    """Require every already executed core buffer to match the first pin.

    The supported bridge compiles itself, filesystem identity, snapshot, and
    runtime from retained buffers before this observation.  A raw host import
    has no such buffer evidence and is therefore permanently unattested even
    if a later disk capture happens to be clean.
    """

    try:
        rows = {row.path: row for row in pin.closure_rows}
        bridge_row = rows.get("scripts/contract_authority_bridge.py")
        fs_row = rows.get("scripts/fs_object_identity.py")
        snapshot_row = rows.get("scripts/contract_authority_snapshot.py")
        runtime_row = rows.get("scripts/contract_authority_runtime.py")
        if bridge_row is None or fs_row is None or snapshot_row is None or runtime_row is None:
            return False
        return (
            _fs_identity._source_capsule_matches_runtime_row(
                _loaded_source_capsule("scripts/contract_authority_bridge.py"),
                expected_path=_AUTHORITY_SCRIPTS_DIR / "contract_authority_bridge.py",
                relative_path="scripts/contract_authority_bridge.py",
                mode=bridge_row.mode,
                sha256=bridge_row.sha256,
            )
            and _fs_identity._first_loaded_module_source_matches_runtime_row(
                sys.modules[__name__],
                expected_path=_AUTHORITY_SCRIPTS_DIR / "contract_authority_runtime.py",
                relative_path="scripts/contract_authority_runtime.py",
                mode=runtime_row.mode,
                sha256=runtime_row.sha256,
            )
            and _fs_identity._first_loaded_module_source_matches_runtime_row(
                _fs_identity,
                expected_path=_AUTHORITY_SCRIPTS_DIR / "fs_object_identity.py",
                relative_path="scripts/fs_object_identity.py",
                mode=fs_row.mode,
                sha256=fs_row.sha256,
            )
            and _fs_identity._first_loaded_module_source_matches_runtime_row(
                _snapshot_authority,
                expected_path=_AUTHORITY_SCRIPTS_DIR / "contract_authority_snapshot.py",
                relative_path="scripts/contract_authority_snapshot.py",
                mode=snapshot_row.mode,
                sha256=snapshot_row.sha256,
            )
        )
    except Exception:
        return False


def _capture_first_loaded_runtime_observation() -> _FirstLoadedRuntimeObservation:
    """Freeze the first import's closure state for this interpreter lifetime.

    A runtime which cannot be pinned while its code is first imported remains
    unattested for the lifetime of this module.  Later clean disk bytes cannot
    retroactively attest code that was already loaded from an earlier state.
    """

    runtime_root = _resolved_directory(_AUTHORITY_SCRIPTS_DIR.parent, context="loaded runtime")
    pin: LoadedRuntimePin | None
    try:
        pin = capture_loaded_runtime_pin(runtime_root)
        if not _pre_runtime_module_observations_match_closure(pin):
            pin = None
    except ContractAuthorityError:
        pin = None
    return _FirstLoadedRuntimeObservation(runtime_root=runtime_root, pin=pin)


_FIRST_LOADED_RUNTIME_OBSERVATION: Final[_FirstLoadedRuntimeObservation] = (
    _capture_first_loaded_runtime_observation()
)


def _first_loaded_runtime_observation() -> _FirstLoadedRuntimeObservation:
    """Return the immutable observation captured while this module loaded."""

    return _FIRST_LOADED_RUNTIME_OBSERVATION


def loaded_runtime_pin_to_dict(pin: LoadedRuntimePin) -> dict[str, object]:
    """Return a strict, JSON-ready representation; this does not recapture disk."""

    normalized = _validate_loaded_runtime_pin(pin)
    payload = _pin_body(normalized)
    payload["pin_sha256"] = normalized.pin_sha256
    payload["observed_index_sha256"] = normalized.observed_index_sha256
    return payload


def loaded_runtime_pin_summary(pin: LoadedRuntimePin) -> dict[str, object]:
    """Return the compact public pin carrier used by buffered children.

    This is derived only from an already validated immutable pin.  Callers
    serialize it as data for a later bridge process; they must not recapture
    the runtime to construct a replacement child identity.
    """

    full = loaded_runtime_pin_to_dict(pin)
    return {
        "schema_version": RUNTIME_PIN_SUMMARY_SCHEMA_VERSION,
        "runtime_root": full["runtime_root"],
        "git_dir": full["git_dir"],
        "runtime_api_version": full["runtime_api_version"],
        "commit": full["commit"],
        "tree": full["tree"],
        "closure_spec_sha256": full["closure_spec_sha256"],
        "closure_rows_sha256": full["closure_rows_sha256"],
        "closure_sha256": full["closure_sha256"],
        "pin_sha256": full["pin_sha256"],
    }


def loaded_runtime_pin_from_dict(value: object) -> LoadedRuntimePin:
    """Parse a strict JSON-ready pin representation without verifying current disk."""

    fields = frozenset(
        {
            "schema_version",
            "runtime_root",
            "git_dir",
            "runtime_api_version",
            "commit",
            "tree",
            "closure_spec_sha256",
            "closure_rows",
            "closure_rows_sha256",
            "closure_sha256",
            "pin_sha256",
            "observed_index_sha256",
        }
    )
    if type(value) is not dict or set(value) != fields:
        raise _fail("runtime_pin_schema_invalid", "runtime pin must contain exactly its documented fields")
    if _validate_int(value["schema_version"], field="schema_version") != RUNTIME_PIN_SCHEMA_VERSION:
        raise _fail("unsupported_runtime_pin_schema", "runtime pin schema_version is unsupported")
    runtime_root_text = value["runtime_root"]
    git_dir_text = value["git_dir"]
    if type(runtime_root_text) is not str or type(git_dir_text) is not str:
        raise _fail("runtime_pin_schema_invalid", "runtime pin paths must be strings")
    rows_value = value["closure_rows"]
    if type(rows_value) is not list or not rows_value:
        raise _fail("runtime_pin_schema_invalid", "runtime pin closure_rows must be a non-empty array")
    rows: list[RuntimeClosureRow] = []
    for position, row_value in enumerate(rows_value):
        row_fields = frozenset({"path", "mode", "blob_oid", "sha256"})
        if type(row_value) is not dict or set(row_value) != row_fields:
            raise _fail("runtime_pin_schema_invalid", f"runtime pin closure row {position} is invalid")
        rows.append(
            RuntimeClosureRow(
                path=row_value["path"],  # validated by _validate_loaded_runtime_pin
                mode=row_value["mode"],
                blob_oid=row_value["blob_oid"],
                sha256=row_value["sha256"],
            )
        )
    return _validate_loaded_runtime_pin(
        LoadedRuntimePin(
            runtime_root=Path(runtime_root_text),
            git_dir=Path(git_dir_text),
            runtime_api_version=value["runtime_api_version"],
            commit=value["commit"],
            tree=value["tree"],
            closure_spec_sha256=value["closure_spec_sha256"],
            closure_rows=tuple(rows),
            closure_rows_sha256=value["closure_rows_sha256"],
            closure_sha256=value["closure_sha256"],
            pin_sha256=value["pin_sha256"],
            observed_index_sha256=value["observed_index_sha256"],
        )
    )


__all__ = [
    "ContractAuthorityError",
    "GIT_COMMAND_TIMEOUT_SECONDS",
    "GitIdentity",
    "GitIndexEntry",
    "LoadedRuntimePin",
    "REQUIRED_RUNTIME_PATHS",
    "RUNTIME_API_VERSION",
    "RUNTIME_CLOSURE_SPEC_SHA256",
    "RUNTIME_PIN_SCHEMA_VERSION",
    "RUNTIME_PIN_SUMMARY_SCHEMA_VERSION",
    "RuntimeClosureRow",
    "TrackedFileIdentity",
    "authority_bootstrap_literal",
    "authority_shell_loader_literal",
    "capture_loaded_runtime_pin",
    "capture_tracked_content",
    "loaded_runtime_pin_from_dict",
    "loaded_runtime_pin_summary",
    "loaded_runtime_pin_to_dict",
    "verify_loaded_runtime_pin",
]

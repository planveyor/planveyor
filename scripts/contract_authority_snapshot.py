"""Read-only snapshots and passive envelopes for contract authority.

The integrated runtime uses this foundation to validate declared candidates
and frozen context envelopes.  This module has no command-line interface and
does not mutate the candidate or its repository.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
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


if TYPE_CHECKING:
    import fs_object_identity as _fs_identity
    from fs_object_identity import ObjectIdentityError, ObjectSnapshot, snapshot_regular_or_absent
else:
    _fs_identity = _load_authority_module("scripts.fs_object_identity", "fs_object_identity")
    ObjectIdentityError = _fs_identity.ObjectIdentityError
    ObjectSnapshot = _fs_identity.ObjectSnapshot
    snapshot_regular_or_absent = _fs_identity.snapshot_regular_or_absent


# The authority modules are imported both as ``scripts.*`` by the bridge and
# directly by long-standing scripts.  Only this exact sibling file is admitted
# under either spelling, so a target ``scripts`` package cannot split classes.
_bind_authority_aliases("scripts.contract_authority_snapshot", "contract_authority_snapshot")


# Snapshot may be imported before runtime by a caller-owned Python host.  Keep
# the loader-retained source capsule that module instance actually executed so
# runtime cannot later stamp newer clean disk bytes onto older loaded code.
_FIRST_LOADED_SOURCE_OBSERVATION: Final[object | None] = (
    _fs_identity._capture_loaded_module_source_observation(
        sys.modules[__name__],
        expected_path=_AUTHORITY_SCRIPTS_DIR / "contract_authority_snapshot.py",
        relative_path="scripts/contract_authority_snapshot.py",
        source_capsule=globals().get("__authority_source_capsule__"),
        source_reader=globals().get("__authority_read_source__"),
    )
)


def _first_loaded_source_observation() -> object | None:
    """Return immutable provenance recorded while this module initialized."""

    return _FIRST_LOADED_SOURCE_OBSERVATION


MARKER_PATH: Final[str] = "docs/_meta/planveyor_contract_authority.v1.json"
MARKER_SCHEMA_VERSION: Final[int] = 1
LOCAL_MARKER_SCHEMA_VERSION: Final[int] = 3
CLOSURE_MANIFEST_SCHEMA_VERSION: Final[int] = 1

# Compact authority envelopes cross process boundaries, but their structural
# validation is passive: it must never load the runtime pin or inspect a target.
# Keep this contract beside the other snapshot-only parsers so bridge readers
# can use it without importing ``contract_authority_context``.
# v2 adds an explicit provenance classification for historical entry facts.
# Keep v1 readable because passive receipt readers must retain old evidence
# without recapturing a now-changed target or runtime.
LEGACY_CONTEXT_SCHEMA_VERSION: Final[str] = "planveyor_contract_context.v1"
HISTORICAL_CONTEXT_SCHEMA_VERSION: Final[str] = "planveyor_contract_context.v2"
CONTEXT_SCHEMA_VERSION: Final[str] = "planveyor_contract_context.v3"
ENTRY_OBSERVATION_PROVENANCE_OBSERVED_LOCAL: Final[str] = "observed_local"
ENTRY_OBSERVATION_PROVENANCE_INHERITED_SUPPLIED_UNVERIFIED: Final[str] = (
    "inherited_supplied_unverified"
)
_ENTRY_OBSERVATION_PROVENANCE_VALUES: Final[frozenset[str]] = frozenset(
    {
        ENTRY_OBSERVATION_PROVENANCE_OBSERVED_LOCAL,
        ENTRY_OBSERVATION_PROVENANCE_INHERITED_SUPPLIED_UNVERIFIED,
    }
)
MAX_CONTEXT_ENVELOPE_BYTES: Final[int] = 16 * 1024

_REGULAR_GIT_MODES: Final[frozenset[str]] = frozenset({"100644", "100755"})
_GIT_OBJECT_ID_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")


class ContractAuthorityError(RuntimeError):
    """A fail-closed result with a stable machine-readable reason code."""

    def __init__(self, reason_code: str, message: str) -> None:
        self.reason_code = reason_code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ApiRange:
    minimum: int
    maximum: int


@dataclass(frozen=True, slots=True)
class SourceBaseline:
    """Copy provenance declared by a target; it is not a runtime pin."""

    repository_id: str
    commit: str


@dataclass(frozen=True, slots=True)
class RequiredContent:
    """One target-local contract input declared by the closure manifest."""

    path: str
    mode: Literal["100644", "100755"]
    blob_oid: str
    sha256: str


@dataclass(frozen=True, slots=True)
class RuntimeContent:
    """One caller-declared runtime executable input, relative to runtime root."""

    path: str
    mode: Literal["100644", "100755"]
    sha256: str


@dataclass(frozen=True, slots=True)
class RuntimeDiskIdentity:
    """Explicit caller data which this module verifies against runtime disk bytes.

    ``api_version`` is trusted compatibility input for this package.  It is not
    an assertion that a shell has loaded a particular runtime API.
    """

    root: Path
    commit: str
    tree: str
    api_version: int
    executable_inputs: tuple[RuntimeContent, ...]


@dataclass(frozen=True, slots=True)
class AuthorityMarker:
    schema_version: int
    repository_id: str
    authority_mode: Literal["target-local"]
    contract_root: str
    required_runtime_api: ApiRange
    closure_manifest: str
    source_baseline: SourceBaseline


@dataclass(frozen=True, slots=True)
class LocalAuthorityMarker:
    schema_version: int
    repository_id: str
    authority_mode: Literal["target-local"]
    contract_root: str
    required_runtime_api: ApiRange
    source_commit: str


@dataclass(frozen=True, slots=True)
class ClosureManifest:
    schema_version: int
    required_content: tuple[RequiredContent, ...]


@dataclass(frozen=True, slots=True)
class GitIndexEntry:
    path: str
    mode: str
    blob_oid: str
    stage: int


@dataclass(frozen=True, slots=True)
class GitIdentity:
    root: Path
    git_dir: Path
    head: str
    tree: str
    index_sha256: str
    index_entries: tuple[GitIndexEntry, ...]


@dataclass(frozen=True, slots=True)
class TrackedFileIdentity:
    path: str
    mode: Literal["100644", "100755"]
    blob_oid: str
    sha256: str


@dataclass(frozen=True, slots=True)
class LegacyAuthorityObservation:
    """A verified repository whose HEAD has no authority marker."""

    git: GitIdentity
    state: Literal["legacy"] = "legacy"


@dataclass(frozen=True, slots=True)
class CandidateAuthoritySnapshot:
    """An immutable observation of one fully matched candidate declaration."""

    git: GitIdentity
    marker: AuthorityMarker
    closure_manifest: ClosureManifest
    marker_file: TrackedFileIdentity
    closure_manifest_file: TrackedFileIdentity
    runtime: RuntimeDiskIdentity
    runtime_git: GitIdentity
    state: Literal["candidate"] = "candidate"


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
class _ObservedRuntime:
    identity: RuntimeDiskIdentity
    git: GitIdentity


def _fail(reason_code: str, message: str) -> ContractAuthorityError:
    return ContractAuthorityError(reason_code, message)


def _clean_git_environment() -> dict[str, str]:
    """Remove ambient Git retargeting and set read-only plumbing controls."""

    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment.update(
        {
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_NO_LAZY_FETCH": "1",
            "LC_ALL": "C",
            "LANG": "C",
        }
    )
    return environment


def _run_git(root: Path, *arguments: str, context: str) -> bytes:
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
            env=_clean_git_environment(),
        )
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


def _validate_object_id(value: object, *, field: str) -> str:
    if type(value) is not str or _GIT_OBJECT_ID_RE.fullmatch(value) is None:
        raise _fail("invalid_object_id", f"{field} must be one lowercase Git object id")
    return value


def _validate_sha256(value: object, *, field: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise _fail("invalid_sha256", f"{field} must be one lowercase SHA-256 digest")
    return value


def _validate_mode(value: object, *, field: str) -> Literal["100644", "100755"]:
    if type(value) is not str or value not in _REGULAR_GIT_MODES:
        raise _fail("invalid_git_mode", f"{field} must be 100644 or 100755")
    return value  # type: ignore[return-value]


def _validate_int(value: object, *, field: str) -> int:
    if type(value) is not int or isinstance(value, bool):
        raise _fail("invalid_integer", f"{field} must be an integer, never a boolean")
    return value


def _validate_text(value: object, *, field: str) -> str:
    if (
        type(value) is not str
        or not value
        or "\x00" in value
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise _fail("invalid_text", f"{field} must be non-empty printable text")
    try:
        value.encode("utf-8", "strict")
    except UnicodeEncodeError as exc:
        raise _fail("invalid_text", f"{field} must use Unicode scalar text") from exc
    return value


def _validate_relative_path(value: object, *, field: str, allow_dot: bool = False) -> str:
    if type(value) is not str:
        raise _fail("invalid_relative_path", f"{field} must be normalized relative POSIX text")
    try:
        value.encode("utf-8", "strict")
    except UnicodeEncodeError as exc:
        raise _fail("invalid_relative_path", f"{field} must use Unicode scalar text") from exc
    if value == "." and allow_dot:
        return value
    if (
        not value
        or value.startswith("/")
        or value.endswith("/")
        or "\\" in value
        or "\x00" in value
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise _fail("invalid_relative_path", f"{field} must be normalized relative POSIX text")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise _fail("invalid_relative_path", f"{field} contains a forbidden path segment")
    return value


def _require_exact_fields(value: object, *, fields: frozenset[str], context: str) -> dict[str, object]:
    if type(value) is not dict or set(value) != fields:
        raise _fail("json_schema_invalid", f"{context} must contain exactly its documented fields")
    return value


def _no_duplicate_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _fail("duplicate_json_field", f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise _fail("invalid_json", f"JSON constant is forbidden: {value}")


def _parse_json_object(data: bytes, *, context: str) -> dict[str, object]:
    if type(data) is not bytes:
        raise _fail("invalid_json", f"{context} must be bytes")
    try:
        decoded = data.decode("utf-8", "strict")
        value = json.loads(
            decoded,
            object_pairs_hook=_no_duplicate_object,
            parse_constant=_reject_json_constant,
        )
    except ContractAuthorityError:
        raise
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise _fail("invalid_json", f"{context} is not strict UTF-8 JSON") from exc
    if type(value) is not dict:
        raise _fail("json_schema_invalid", f"{context} must be a JSON object")
    return value


def _context_canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise _fail("context_serialization_invalid", "authority context cannot be canonically serialized") from exc


def _context_sha256_json(value: object) -> str:
    return hashlib.sha256(_context_canonical_json_bytes(value)).hexdigest()


def _parse_context_json_object(text: object, *, context: str) -> dict[str, object]:
    """Parse bounded strict JSON for a compact context-related assertion."""

    if type(text) is not str:
        raise _fail("context_envelope_invalid", f"{context} must be JSON text")
    try:
        raw = text.encode("utf-8", "strict")
    except UnicodeEncodeError as exc:
        raise _fail("context_envelope_invalid", f"{context} must be UTF-8 text") from exc
    if len(raw) > MAX_CONTEXT_ENVELOPE_BYTES:
        raise _fail("context_envelope_too_large", "authority context envelope exceeds its fixed bound")

    def no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise _fail("context_envelope_duplicate_field", f"duplicate {context} field: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise _fail("context_envelope_invalid", f"forbidden JSON constant in {context}: {value}")

    try:
        parsed = json.loads(
            text,
            object_pairs_hook=no_duplicates,
            parse_constant=reject_constant,
        )
    except ContractAuthorityError:
        raise
    except (TypeError, ValueError, RecursionError) as exc:
        raise _fail("context_envelope_invalid", f"{context} is not strict JSON") from exc
    if type(parsed) is not dict:
        raise _fail("context_envelope_invalid", f"{context} must be a JSON object")
    return parsed


def _validate_context_absolute_path_text(value: object, *, field: str) -> str:
    text = _validate_text(value, field=field)
    path = PurePosixPath(text)
    if not path.is_absolute() or text != path.as_posix() or "//" in text:
        raise _fail("context_envelope_schema_invalid", f"{field} must be canonical absolute POSIX text")
    if any(part in {".", ".."} for part in path.parts):
        raise _fail("context_envelope_schema_invalid", f"{field} contains an unsafe path component")
    return text


def _require_exact_context_fields(value: object, *, fields: frozenset[str], context: str) -> dict[str, object]:
    if type(value) is not dict or set(value) != fields:
        raise _fail("context_envelope_schema_invalid", f"{context} must contain exactly its documented fields")
    return value


def _validate_context_entry_envelope(value: object, *, state: str, project_root: str) -> dict[str, object]:
    mapping = _require_exact_context_fields(
        value,
        fields=frozenset({"root", "git_dir", "head", "tree", "index_sha256"}),
        context="entry_observation",
    )
    root = _validate_context_absolute_path_text(mapping["root"], field="entry_observation.root")
    if root != project_root:
        raise _fail("context_envelope_schema_invalid", "entry_observation.root must equal project_root")
    fields = ("git_dir", "head", "tree", "index_sha256")
    values = tuple(mapping[field] for field in fields)
    if all(value is None for value in values):
        if state != "legacy":
            raise _fail("context_envelope_schema_invalid", "engaged context requires Git entry evidence")
        return mapping
    if any(value is None for value in values):
        raise _fail("context_envelope_schema_invalid", "entry_observation Git evidence must be all-or-none")
    _validate_context_absolute_path_text(mapping["git_dir"], field="entry_observation.git_dir")
    _validate_object_id(mapping["head"], field="entry_observation.head")
    _validate_object_id(mapping["tree"], field="entry_observation.tree")
    _validate_sha256(mapping["index_sha256"], field="entry_observation.index_sha256")
    return mapping


def _validate_context_runtime_pin_summary(value: object, *, state: str) -> dict[str, object] | None:
    if value is None:
        if state == "engaged":
            raise _fail("context_envelope_schema_invalid", "engaged context requires runtime_pin summary")
        return None
    mapping = _require_exact_context_fields(
        value,
        fields=frozenset(
            {
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
        ),
        context="runtime_pin",
    )
    _validate_context_absolute_path_text(mapping["runtime_root"], field="runtime_pin.runtime_root")
    _validate_context_absolute_path_text(mapping["git_dir"], field="runtime_pin.git_dir")
    if _validate_int(mapping["runtime_api_version"], field="runtime_pin.runtime_api_version") < 0:
        raise _fail("context_envelope_schema_invalid", "runtime_pin.runtime_api_version must be non-negative")
    _validate_object_id(mapping["commit"], field="runtime_pin.commit")
    _validate_object_id(mapping["tree"], field="runtime_pin.tree")
    for name in ("closure_spec_sha256", "closure_rows_sha256", "closure_sha256", "pin_sha256"):
        _validate_sha256(mapping[name], field=f"runtime_pin.{name}")
    return mapping


def parse_context_envelope(text: str) -> dict[str, object]:
    """Validate a receipt/child envelope without importing runtime/context.

    This is structural validation of a supplied payload.  In particular, a
    valid digest never establishes that the payload's historical entry facts
    were observed by the current process or a trusted parent invocation.
    Active context construction owns that provenance decision.
    """

    mapping = _parse_context_json_object(text, context="authority context envelope")
    common_fields = frozenset(
        {
            "schema_version",
            "state",
            "project_root",
            "entry_observation",
            "behavior_identity",
            "runtime_pin",
            "generation_sha256",
            "fallback_used",
            "context_sha256",
        }
    )
    schema_version = mapping.get("schema_version")
    if schema_version == LEGACY_CONTEXT_SCHEMA_VERSION:
        expected_fields = common_fields
    elif type(schema_version) is str and schema_version in (
        HISTORICAL_CONTEXT_SCHEMA_VERSION,
        CONTEXT_SCHEMA_VERSION,
    ):
        expected_fields = common_fields | frozenset({"entry_observation_provenance"})
    else:
        raise _fail("context_envelope_schema_invalid", "authority context envelope schema is unsupported")
    if set(mapping) != expected_fields:
        raise _fail("context_envelope_schema_invalid", "authority context envelope has unexpected fields")
    state = mapping["state"]
    if not isinstance(state, str) or state not in {"legacy", "engaged"}:
        raise _fail("context_envelope_schema_invalid", "authority context envelope state is invalid")
    project_root = _validate_context_absolute_path_text(mapping["project_root"], field="project_root")
    _validate_context_entry_envelope(mapping["entry_observation"], state=state, project_root=project_root)
    behavior = _validate_text(mapping["behavior_identity"], field="behavior_identity")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", behavior) is None:
        raise _fail("context_envelope_schema_invalid", "authority context behavior_identity is invalid")
    if state == "engaged" and behavior == "default":
        raise _fail("context_envelope_schema_invalid", "engaged context cannot use an unknown behavior_identity")
    _validate_context_runtime_pin_summary(mapping["runtime_pin"], state=state)
    _validate_sha256(mapping["generation_sha256"], field="generation_sha256")
    if type(mapping["fallback_used"]) is not bool:
        raise _fail("context_envelope_schema_invalid", "fallback_used must be boolean")
    if state == "engaged" and mapping["fallback_used"] is not False:
        raise _fail("context_envelope_schema_invalid", "engaged context cannot use fallback")
    if state == "legacy" and mapping["fallback_used"] is not True:
        raise _fail("context_envelope_schema_invalid", "legacy context must record fallback")
    if schema_version in {HISTORICAL_CONTEXT_SCHEMA_VERSION, CONTEXT_SCHEMA_VERSION}:
        provenance = mapping["entry_observation_provenance"]
        if type(provenance) is not str or provenance not in _ENTRY_OBSERVATION_PROVENANCE_VALUES:
            raise _fail(
                "context_envelope_schema_invalid",
                "entry_observation_provenance is invalid",
            )
    supplied_digest = _validate_sha256(mapping["context_sha256"], field="context_sha256")
    body = {key: value for key, value in mapping.items() if key != "context_sha256"}
    if _context_sha256_json(body) != supplied_digest:
        raise _fail("context_envelope_digest_mismatch", "authority context envelope digest does not match its contents")
    return mapping


def _parse_api_range(value: object) -> ApiRange:
    mapping = _require_exact_fields(
        value,
        fields=frozenset({"minimum", "maximum"}),
        context="required_runtime_api",
    )
    minimum = _validate_int(mapping["minimum"], field="required_runtime_api.minimum")
    maximum = _validate_int(mapping["maximum"], field="required_runtime_api.maximum")
    if minimum < 0 or maximum < minimum:
        raise _fail("invalid_api_range", "required_runtime_api is not an ordered non-negative range")
    return ApiRange(minimum=minimum, maximum=maximum)


def _parse_source_baseline(value: object) -> SourceBaseline:
    mapping = _require_exact_fields(
        value,
        fields=frozenset({"repository_id", "commit"}),
        context="source_baseline",
    )
    return SourceBaseline(
        repository_id=_validate_text(mapping["repository_id"], field="source_baseline.repository_id"),
        commit=_validate_object_id(mapping["commit"], field="source_baseline.commit"),
    )


def parse_marker_bytes(data: bytes) -> AuthorityMarker:
    """Strictly parse one marker after its tracked bytes were observed."""

    mapping = _require_exact_fields(
        _parse_json_object(data, context="authority marker"),
        fields=frozenset(
            {
                "schema_version",
                "repository_id",
                "authority_mode",
                "contract_root",
                "required_runtime_api",
                "closure_manifest",
                "source_baseline",
            }
        ),
        context="authority marker",
    )
    schema_version = _validate_int(mapping["schema_version"], field="schema_version")
    if schema_version != MARKER_SCHEMA_VERSION:
        raise _fail("unsupported_marker_schema", "authority marker schema_version is unsupported")
    authority_mode = mapping["authority_mode"]
    if authority_mode != "target-local":
        raise _fail("invalid_authority_mode", "authority_mode must be target-local")
    closure_manifest = _validate_relative_path(
        mapping["closure_manifest"],
        field="closure_manifest",
    )
    if closure_manifest == MARKER_PATH:
        raise _fail("invalid_closure_manifest_path", "closure_manifest must not name the marker")
    return AuthorityMarker(
        schema_version=schema_version,
        repository_id=_validate_text(mapping["repository_id"], field="repository_id"),
        authority_mode="target-local",
        contract_root=_validate_relative_path(mapping["contract_root"], field="contract_root", allow_dot=True),
        required_runtime_api=_parse_api_range(mapping["required_runtime_api"]),
        closure_manifest=closure_manifest,
        source_baseline=_parse_source_baseline(mapping["source_baseline"]),
    )


def parse_local_marker_bytes(data: bytes) -> LocalAuthorityMarker:
    """Parse the sole supported physical selector used by the live local reader.

    This deliberately has no compatibility route through the strict v1
    candidate parser above. A present live marker is either current or fails closed.
    """

    mapping = _parse_json_object(data, context="local authority marker")
    schema_version = mapping.get("schema_version")
    if (
        type(schema_version) is not int
        or isinstance(schema_version, bool)
        or schema_version != LOCAL_MARKER_SCHEMA_VERSION
    ):
        raise _fail("unsupported_live_marker_schema", "live authority marker must use schema_version 3")
    if set(mapping) != {
        "schema_version",
        "repository_id",
        "authority_mode",
        "contract_root",
        "required_runtime_api",
        "source_commit",
    }:
        raise _fail("marker_field_set_invalid", "local authority marker has unexpected fields")
    if mapping["authority_mode"] != "target-local":
        raise _fail("invalid_authority_mode", "authority_mode must be target-local")
    return LocalAuthorityMarker(
        schema_version=LOCAL_MARKER_SCHEMA_VERSION,
        repository_id=_validate_text(mapping["repository_id"], field="repository_id"),
        authority_mode="target-local",
        contract_root=_validate_relative_path(mapping["contract_root"], field="contract_root", allow_dot=True),
        required_runtime_api=_parse_api_range(mapping["required_runtime_api"]),
        source_commit=_validate_object_id(mapping["source_commit"], field="source_commit"),
    )


def parse_closure_manifest_bytes(data: bytes) -> ClosureManifest:
    """Strictly parse the marker-referenced closure manifest."""

    mapping = _require_exact_fields(
        _parse_json_object(data, context="closure manifest"),
        fields=frozenset({"schema_version", "required_content"}),
        context="closure manifest",
    )
    schema_version = _validate_int(mapping["schema_version"], field="closure_manifest.schema_version")
    if schema_version != CLOSURE_MANIFEST_SCHEMA_VERSION:
        raise _fail("unsupported_manifest_schema", "closure manifest schema_version is unsupported")
    rows = mapping["required_content"]
    if type(rows) is not list or not rows:
        raise _fail("invalid_required_content", "required_content must be a non-empty array")
    parsed: list[RequiredContent] = []
    seen_paths: set[str] = set()
    for position, row in enumerate(rows):
        row_mapping = _require_exact_fields(
            row,
            fields=frozenset({"path", "mode", "blob_oid", "sha256"}),
            context=f"required_content[{position}]",
        )
        path = _validate_relative_path(row_mapping["path"], field=f"required_content[{position}].path")
        if path in seen_paths:
            raise _fail("duplicate_required_path", f"required_content repeats {path}")
        seen_paths.add(path)
        parsed.append(
            RequiredContent(
                path=path,
                mode=_validate_mode(row_mapping["mode"], field=f"required_content[{position}].mode"),
                blob_oid=_validate_object_id(row_mapping["blob_oid"], field=f"required_content[{position}].blob_oid"),
                sha256=_validate_sha256(row_mapping["sha256"], field=f"required_content[{position}].sha256"),
            )
        )
    return ClosureManifest(schema_version=schema_version, required_content=tuple(parsed))


def _resolved_directory(value: object, *, context: str) -> Path:
    if not isinstance(value, Path):
        raise _fail("invalid_root", f"{context} root must be a pathlib.Path")
    try:
        resolved = value.resolve(strict=True)
        is_directory = resolved.is_dir()
    except (OSError, RuntimeError, ValueError, UnicodeError) as exc:
        raise _fail("root_unavailable", f"{context} root cannot be resolved") from exc
    if not is_directory:
        raise _fail("invalid_root", f"{context} root is not a directory")
    return resolved


def _git_object_id(root: Path, expression: str, *, context: str) -> str:
    return _validate_object_id(
        _single_text_line(_run_git(root, "rev-parse", "--verify", expression, context=context), context=context),
        field=context,
    )


def _git_root_and_dir(repo_root: Path, *, context: str) -> tuple[Path, Path]:
    requested_root = _resolved_directory(repo_root, context=context)
    inside = _single_text_line(
        _run_git(requested_root, "rev-parse", "--is-inside-work-tree", context=f"{context} worktree"),
        context=f"{context} worktree",
    )
    if inside != "true":
        raise _fail("git_non_worktree", f"{context} is not a Git worktree")
    top_text = _single_text_line(
        _run_git(requested_root, "rev-parse", "--show-toplevel", context=f"{context} top-level"),
        context=f"{context} top-level",
    )
    top_path = Path(top_text)
    if not top_path.is_absolute():
        raise _fail("git_output_invalid", f"{context} Git top-level is not absolute")
    top = _resolved_directory(top_path, context=f"{context} top-level")
    if top != requested_root:
        raise _fail("git_root_mismatch", f"{context} argument is not the verified Git top-level")
    git_dir_text = _single_text_line(
        _run_git(requested_root, "rev-parse", "--absolute-git-dir", context=f"{context} git dir"),
        context=f"{context} git dir",
    )
    git_dir_path = Path(git_dir_text)
    if not git_dir_path.is_absolute():
        raise _fail("git_output_invalid", f"{context} Git directory is not absolute")
    git_dir = _resolved_directory(git_dir_path, context=f"{context} git dir")
    return top, git_dir


def _index_digest(root: Path, git_dir: Path) -> str:
    index_text = _single_text_line(
        _run_git(
            root,
            "rev-parse",
            "--path-format=absolute",
            "--git-path",
            "index",
            context="Git index path",
        ),
        context="Git index path",
    )
    index_path = Path(index_text)
    if not index_path.is_absolute():
        raise _fail("git_output_invalid", "Git index path is not absolute")
    try:
        index_relative = index_path.relative_to(git_dir).as_posix()
    except ValueError as exc:
        raise _fail("git_index_path_invalid", "Git index is outside its verified Git directory") from exc
    _validate_relative_path(index_relative, field="Git index path")
    try:
        snapshot = snapshot_regular_or_absent(git_dir, index_relative)
    except ObjectIdentityError as exc:
        raise _fail(exc.reason_code, "Git index cannot be safely observed") from exc
    if snapshot.state != "regular" or snapshot.data is None:
        raise _fail("index_missing", "Git index is absent")
    return hashlib.sha256(snapshot.data).hexdigest()


def _capture_git_basis(repo_root: Path, *, context: str) -> _GitBasis:
    root, git_dir = _git_root_and_dir(repo_root, context=context)
    head = _git_object_id(root, "HEAD^{commit}", context=f"{context} HEAD")
    tree = _git_object_id(root, "HEAD^{tree}", context=f"{context} HEAD tree")
    return _GitBasis(
        root=root,
        git_dir=git_dir,
        head=head,
        tree=tree,
        index_sha256=_index_digest(root, git_dir),
    )


def _recheck_git_basis(before: _GitBasis, *, context: str) -> _GitBasis:
    after = _capture_git_basis(before.root, context=context)
    if after != before:
        raise _fail(
            "snapshot_changed_during_read",
            f"{context} Git HEAD, tree, index, root, or Git directory changed while reading",
        )
    return after


def _nul_records(data: bytes, *, context: str) -> tuple[bytes, ...]:
    if not data:
        return ()
    if not data.endswith(b"\0"):
        raise _fail("git_output_invalid", f"Git returned unterminated NUL records for {context}")
    records = tuple(data[:-1].split(b"\0"))
    if any(not record for record in records):
        raise _fail("git_output_invalid", f"Git returned an empty NUL record for {context}")
    return records


def _decode_git_path(data: bytes, *, context: str) -> str:
    try:
        path = data.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise _fail("git_output_invalid", f"Git returned a non-UTF-8 path for {context}") from exc
    return _validate_relative_path(path, field=f"Git {context} path")


def _head_entry(root: Path, path: str) -> _GitTreeEntry | None:
    records = _nul_records(
        _run_git(root, "ls-tree", "-z", "HEAD", "--", path, context=f"HEAD entry {path}"),
        context=f"HEAD entry {path}",
    )
    if not records:
        return None
    if len(records) != 1:
        raise _fail("git_head_entry_ambiguous", f"HEAD has more than one entry for {path}")
    try:
        description, path_bytes = records[0].split(b"\t", 1)
        mode_bytes, kind_bytes, oid_bytes = description.split(b" ")
        mode = mode_bytes.decode("ascii")
        kind = kind_bytes.decode("ascii")
        blob_oid = oid_bytes.decode("ascii")
    except (UnicodeDecodeError, ValueError) as exc:
        raise _fail("git_output_invalid", f"HEAD entry is malformed for {path}") from exc
    returned_path = _decode_git_path(path_bytes, context=f"HEAD entry {path}")
    if returned_path != path or kind != "blob" or mode not in _REGULAR_GIT_MODES:
        raise _fail("git_head_entry_invalid", f"HEAD entry is not one regular file for {path}")
    return _GitTreeEntry(path=path, mode=mode, blob_oid=_validate_object_id(blob_oid, field=f"HEAD blob {path}"))


def _index_entries(root: Path, path: str) -> tuple[GitIndexEntry, ...]:
    records = _nul_records(
        _run_git(root, "ls-files", "--stage", "-z", "--", path, context=f"index entry {path}"),
        context=f"index entry {path}",
    )
    parsed: list[GitIndexEntry] = []
    seen_stages: set[int] = set()
    for record in records:
        try:
            description, path_bytes = record.split(b"\t", 1)
            mode_bytes, oid_bytes, stage_bytes = description.split(b" ")
            mode = mode_bytes.decode("ascii")
            blob_oid = oid_bytes.decode("ascii")
            stage = int(stage_bytes.decode("ascii"), 10)
        except (UnicodeDecodeError, ValueError) as exc:
            raise _fail("git_output_invalid", f"index entry is malformed for {path}") from exc
        returned_path = _decode_git_path(path_bytes, context=f"index entry {path}")
        if returned_path != path or mode not in _REGULAR_GIT_MODES or stage not in {0, 1, 2, 3}:
            raise _fail("git_index_entry_invalid", f"index entry is invalid for {path}")
        if stage in seen_stages:
            raise _fail("git_index_entry_ambiguous", f"index repeats stage {stage} for {path}")
        seen_stages.add(stage)
        parsed.append(
            GitIndexEntry(
                path=path,
                mode=mode,
                blob_oid=_validate_object_id(blob_oid, field=f"index blob {path}"),
                stage=stage,
            )
        )
    return tuple(parsed)


def _stage_zero_entry(entries: tuple[GitIndexEntry, ...], *, path: str, context: str) -> GitIndexEntry | None:
    if any(entry.stage != 0 for entry in entries):
        raise _fail("ambiguous_index_stage", f"{context} has a non-stage-0 index entry for {path}")
    if not entries:
        return None
    if len(entries) != 1:
        raise _fail("git_index_entry_ambiguous", f"{context} has ambiguous index entries for {path}")
    return entries[0]


def _git_blob(root: Path, blob_oid: str, *, path: str) -> bytes:
    return _run_git(root, "cat-file", "blob", blob_oid, context=f"Git blob {path}")


def _worktree_snapshot(root: Path, path: str, *, context: str) -> ObjectSnapshot:
    try:
        return snapshot_regular_or_absent(root, path)
    except ObjectIdentityError as exc:
        raise _fail(exc.reason_code, f"{context} cannot be safely observed") from exc


def _tracked_regular_file(
    basis: _GitBasis,
    path: str,
    *,
    context: str,
    expected_mode: Literal["100644", "100755"] | None = None,
    expected_blob_oid: str | None = None,
    expected_sha256: str | None = None,
) -> tuple[TrackedFileIdentity, tuple[GitIndexEntry, ...]]:
    head_entry = _head_entry(basis.root, path)
    if head_entry is None:
        raise _fail("tracked_path_missing_from_head", f"{context} is absent from HEAD: {path}")
    index_entries = _index_entries(basis.root, path)
    index_entry = _stage_zero_entry(index_entries, path=path, context=context)
    if index_entry is None:
        raise _fail("tracked_path_missing_from_index", f"{context} is absent from stage-0 index: {path}")
    if index_entry.mode != head_entry.mode or index_entry.blob_oid != head_entry.blob_oid:
        raise _fail("tracked_path_index_mismatch", f"{context} index differs from HEAD: {path}")
    if expected_mode is not None and head_entry.mode != expected_mode:
        raise _fail("tracked_path_mode_mismatch", f"{context} mode differs from declaration: {path}")
    if expected_blob_oid is not None and head_entry.blob_oid != expected_blob_oid:
        raise _fail("tracked_path_blob_mismatch", f"{context} Git blob differs from declaration: {path}")

    worktree = _worktree_snapshot(basis.root, path, context=context)
    if worktree.state != "regular" or worktree.data is None or worktree.git_mode is None:
        raise _fail("tracked_path_missing_from_worktree", f"{context} is absent from worktree: {path}")
    if worktree.git_mode != head_entry.mode:
        raise _fail("tracked_path_worktree_mode_mismatch", f"{context} worktree mode differs from HEAD: {path}")
    head_bytes = _git_blob(basis.root, head_entry.blob_oid, path=path)
    if worktree.data != head_bytes:
        raise _fail("tracked_path_worktree_bytes_mismatch", f"{context} worktree bytes differ from HEAD: {path}")
    digest = hashlib.sha256(head_bytes).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise _fail("tracked_path_digest_mismatch", f"{context} digest differs from declaration: {path}")
    return (
        TrackedFileIdentity(
            path=path,
            mode=head_entry.mode,  # type: ignore[arg-type]
            blob_oid=head_entry.blob_oid,
            sha256=digest,
        ),
        index_entries,
    )


def _git_identity(basis: _GitBasis, entries: list[GitIndexEntry]) -> GitIdentity:
    return GitIdentity(
        root=basis.root,
        git_dir=basis.git_dir,
        head=basis.head,
        tree=basis.tree,
        index_sha256=basis.index_sha256,
        index_entries=tuple(entries),
    )


def _path_is_under_contract_root(path: str, contract_root: str) -> bool:
    return contract_root == "." or path.startswith(f"{contract_root}/")


def _observe_runtime_disk_identity(runtime: RuntimeDiskIdentity) -> _ObservedRuntime:
    if not isinstance(runtime, RuntimeDiskIdentity):
        raise _fail("invalid_runtime_identity", "runtime must be a RuntimeDiskIdentity")
    root = _resolved_directory(runtime.root, context="runtime")
    commit = _validate_object_id(runtime.commit, field="runtime.commit")
    tree = _validate_object_id(runtime.tree, field="runtime.tree")
    api_version = _validate_int(runtime.api_version, field="runtime.api_version")
    if api_version < 0:
        raise _fail("invalid_runtime_api_version", "runtime.api_version must be non-negative")
    if type(runtime.executable_inputs) is not tuple:
        raise _fail("invalid_runtime_inputs", "runtime.executable_inputs must be an immutable tuple")
    if not runtime.executable_inputs:
        raise _fail("invalid_runtime_inputs", "runtime.executable_inputs must declare at least one input")

    basis = _capture_git_basis(root, context="runtime")
    if basis.root != root:
        raise _fail("runtime_root_mismatch", "runtime root differs from its verified Git root")
    if basis.head != commit:
        raise _fail("runtime_commit_mismatch", "runtime commit differs from disk HEAD")
    if basis.tree != tree:
        raise _fail("runtime_tree_mismatch", "runtime tree differs from disk HEAD tree")

    seen_paths: set[str] = set()
    index_entries: list[GitIndexEntry] = []
    normalized_inputs: list[RuntimeContent] = []
    for position, item in enumerate(runtime.executable_inputs):
        if not isinstance(item, RuntimeContent):
            raise _fail("invalid_runtime_inputs", f"runtime input {position} is not RuntimeContent")
        path = _validate_relative_path(item.path, field=f"runtime.executable_inputs[{position}].path")
        if path in seen_paths:
            raise _fail("duplicate_runtime_path", f"runtime input repeats {path}")
        seen_paths.add(path)
        mode = _validate_mode(item.mode, field=f"runtime.executable_inputs[{position}].mode")
        digest = _validate_sha256(item.sha256, field=f"runtime.executable_inputs[{position}].sha256")
        _, current_entries = _tracked_regular_file(
            basis,
            path,
            context="runtime executable input",
            expected_mode=mode,
            expected_sha256=digest,
        )
        index_entries.extend(current_entries)
        normalized_inputs.append(RuntimeContent(path=path, mode=mode, sha256=digest))
    stable_basis = _recheck_git_basis(basis, context="runtime post-read")
    return _ObservedRuntime(
        identity=RuntimeDiskIdentity(
            root=stable_basis.root,
            commit=stable_basis.head,
            tree=stable_basis.tree,
            api_version=api_version,
            executable_inputs=tuple(normalized_inputs),
        ),
        git=_git_identity(stable_basis, index_entries),
    )


def validate_runtime_disk_identity(runtime: RuntimeDiskIdentity) -> RuntimeDiskIdentity:
    """Verify explicit runtime disk facts without discovering a loaded runtime."""

    first = _observe_runtime_disk_identity(runtime)
    second = _observe_runtime_disk_identity(runtime)
    if first != second:
        raise _fail("snapshot_changed_during_read", "runtime inputs changed between observations")
    return second.identity


def _marker_worktree_exists_without_head(root: Path) -> bool:
    """Observe a possible untracked marker without treating absent parents as an error."""

    try:
        snapshot = snapshot_regular_or_absent(root, MARKER_PATH)
    except ObjectIdentityError as exc:
        if exc.reason_code == "ancestor_missing":
            return False
        raise _fail(exc.reason_code, "authority marker cannot be safely observed") from exc
    return snapshot.state != "absent"


def _capture_once(
    repo_root: Path,
    *,
    expected_repository_id: str,
    runtime: RuntimeDiskIdentity,
) -> LegacyAuthorityObservation | CandidateAuthoritySnapshot:
    expected_id = _validate_text(expected_repository_id, field="expected_repository_id")
    observed_runtime = _observe_runtime_disk_identity(runtime)
    basis = _capture_git_basis(repo_root, context="target")

    marker_head = _head_entry(basis.root, MARKER_PATH)
    marker_index_entries = _index_entries(basis.root, MARKER_PATH)
    marker_stage_zero = _stage_zero_entry(marker_index_entries, path=MARKER_PATH, context="authority marker")
    if marker_head is None:
        if marker_stage_zero is not None:
            raise _fail("marker_index_only", "authority marker exists in index but not HEAD")
        if _marker_worktree_exists_without_head(basis.root):
            raise _fail("marker_worktree_only", "authority marker exists in worktree but not HEAD")
        if _marker_worktree_exists_without_head(basis.root):
            raise _fail("snapshot_changed_during_read", "authority marker appeared while reading legacy state")
        stable_basis = _recheck_git_basis(basis, context="target legacy post-read")
        return LegacyAuthorityObservation(git=_git_identity(stable_basis, list(marker_index_entries)))
    if marker_stage_zero is None:
        raise _fail("marker_missing_from_index", "HEAD authority marker is missing from stage-0 index")
    marker_file, marker_entries = _tracked_regular_file(basis, MARKER_PATH, context="authority marker")
    marker = parse_marker_bytes(_git_blob(basis.root, marker_file.blob_oid, path=MARKER_PATH))
    if marker.repository_id != expected_id:
        raise _fail("repository_identity_mismatch", "marker repository_id differs from explicit expected identity")

    manifest_file, manifest_entries = _tracked_regular_file(
        basis,
        marker.closure_manifest,
        context="closure manifest",
    )
    manifest = parse_closure_manifest_bytes(
        _git_blob(basis.root, manifest_file.blob_oid, path=marker.closure_manifest)
    )

    entries = [*marker_entries, *manifest_entries]
    reserved_paths = {MARKER_PATH, marker.closure_manifest}
    for content in manifest.required_content:
        if content.path in reserved_paths:
            raise _fail("required_content_reserved_path", "required_content must not repeat marker metadata")
        if not _path_is_under_contract_root(content.path, marker.contract_root):
            raise _fail(
                "required_content_outside_contract_root",
                f"required content lies outside contract_root: {content.path}",
            )
        _, content_entries = _tracked_regular_file(
            basis,
            content.path,
            context="required content",
            expected_mode=content.mode,
            expected_blob_oid=content.blob_oid,
            expected_sha256=content.sha256,
        )
        entries.extend(content_entries)

    api = marker.required_runtime_api
    if not api.minimum <= observed_runtime.identity.api_version <= api.maximum:
        raise _fail("runtime_api_incompatible", "explicit runtime API version is outside marker range")
    if _observe_runtime_disk_identity(runtime) != observed_runtime:
        raise _fail("snapshot_changed_during_read", "runtime inputs changed while reading target")
    stable_basis = _recheck_git_basis(basis, context="target post-read")
    return CandidateAuthoritySnapshot(
        git=_git_identity(stable_basis, entries),
        marker=marker,
        closure_manifest=manifest,
        marker_file=marker_file,
        closure_manifest_file=manifest_file,
        runtime=observed_runtime.identity,
        runtime_git=observed_runtime.git,
    )


def capture_candidate_snapshot(
    repo_root: Path,
    *,
    expected_repository_id: str,
    runtime: RuntimeDiskIdentity,
) -> LegacyAuthorityObservation | CandidateAuthoritySnapshot:
    """Capture a stable, read-only observation of an explicit target repository.

    A missing marker in HEAD is a legacy observation.  A marker present only in
    the index or working tree is an error, never a candidate.  The module takes
    two complete observations and rejects drift between them; it does not claim
    a globally race-free Git/filesystem transaction.
    """

    first = _capture_once(repo_root, expected_repository_id=expected_repository_id, runtime=runtime)
    second = _capture_once(repo_root, expected_repository_id=expected_repository_id, runtime=runtime)
    if first != second:
        raise _fail("snapshot_changed_during_capture", "Git, index, or declared disk inputs changed during capture")
    return second


def verify_candidate_snapshot(
    snapshot: CandidateAuthoritySnapshot,
    *,
    expected_repository_id: str,
    runtime: RuntimeDiskIdentity,
) -> CandidateAuthoritySnapshot:
    """Re-capture one candidate and reject any relevant changed snapshot data."""

    if not isinstance(snapshot, CandidateAuthoritySnapshot):
        raise _fail("snapshot_not_candidate", "only a candidate snapshot can be verified")
    current = capture_candidate_snapshot(
        snapshot.git.root,
        expected_repository_id=expected_repository_id,
        runtime=runtime,
    )
    if not isinstance(current, CandidateAuthoritySnapshot):
        raise _fail("snapshot_no_longer_candidate", "candidate marker is no longer present in HEAD")
    if current != snapshot:
        raise _fail(
            "snapshot_changed_after_capture",
            "candidate snapshot no longer matches Git, index, or declared disk inputs",
        )
    return current


__all__ = [
    "ApiRange",
    "AuthorityMarker",
    "CandidateAuthoritySnapshot",
    "ClosureManifest",
    "CLOSURE_MANIFEST_SCHEMA_VERSION",
    "CONTEXT_SCHEMA_VERSION",
    "ContractAuthorityError",
    "ENTRY_OBSERVATION_PROVENANCE_INHERITED_SUPPLIED_UNVERIFIED",
    "ENTRY_OBSERVATION_PROVENANCE_OBSERVED_LOCAL",
    "GitIdentity",
    "GitIndexEntry",
    "HISTORICAL_CONTEXT_SCHEMA_VERSION",
    "LegacyAuthorityObservation",
    "LEGACY_CONTEXT_SCHEMA_VERSION",
    "LocalAuthorityMarker",
    "LOCAL_MARKER_SCHEMA_VERSION",
    "MARKER_PATH",
    "MARKER_SCHEMA_VERSION",
    "MAX_CONTEXT_ENVELOPE_BYTES",
    "RequiredContent",
    "RuntimeContent",
    "RuntimeDiskIdentity",
    "SourceBaseline",
    "TrackedFileIdentity",
    "capture_candidate_snapshot",
    "parse_closure_manifest_bytes",
    "parse_context_envelope",
    "parse_local_marker_bytes",
    "parse_marker_bytes",
    "validate_runtime_disk_identity",
    "verify_candidate_snapshot",
]

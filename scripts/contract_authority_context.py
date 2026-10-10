"""Immutable authority contexts for target-local contract reads.

This module is deliberately a Python boundary, not a dispatcher or a root
registry.  It captures one invocation-local context, admits a target-local
marker only when the compiled integration is complete, and gives readers a
small descriptor-verified read API.  Nothing here has a command-line entry
point: the shell bridge owns serialization at process boundaries.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Literal, cast


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


_runtime = _load_authority_module("scripts.contract_authority_runtime", "contract_authority_runtime")
_snapshot = _load_authority_module("scripts.contract_authority_snapshot", "contract_authority_snapshot")
_fs_identity = _load_authority_module("scripts.fs_object_identity", "fs_object_identity")

if TYPE_CHECKING:
    from contract_authority_runtime import LoadedRuntimePin
    from contract_authority_snapshot import (
        AuthorityMarker,
        ClosureManifest,
        ContractAuthorityError,
        GitIdentity,
        LocalAuthorityMarker,
        RequiredContent,
        TrackedFileIdentity,
    )
    from fs_object_identity import ObjectIdentityError, snapshot_regular_or_absent
else:
    ContractAuthorityError = _snapshot.ContractAuthorityError
    AuthorityMarker = _snapshot.AuthorityMarker
    ClosureManifest = _snapshot.ClosureManifest
    GitIdentity = _snapshot.GitIdentity
    LocalAuthorityMarker = _snapshot.LocalAuthorityMarker
    RequiredContent = _snapshot.RequiredContent
    TrackedFileIdentity = _snapshot.TrackedFileIdentity
    LoadedRuntimePin = _runtime.LoadedRuntimePin
    ObjectIdentityError = _fs_identity.ObjectIdentityError
    snapshot_regular_or_absent = _fs_identity.snapshot_regular_or_absent


# Preserve one import identity for package bridge callers and direct scripts.
# The aliases are set only after the dependency chain has imported cleanly, so
# they do not hide a missing internal dependency behind an unrelated fallback.
_bind_authority_aliases("scripts.contract_authority_context", "contract_authority_context")


# The supported bridge compiles this module from an injected retained buffer.
# A raw import lacks that evidence and may still serve passive/legacy callers,
# but it can never promote an engaged runtime pin after a later clean disk
# observation.
_FIRST_LOADED_SOURCE_OBSERVATION: Final[object | None] = (
    _fs_identity._capture_loaded_module_source_observation(
        sys.modules[__name__],
        expected_path=_AUTHORITY_SCRIPTS_DIR / "contract_authority_context.py",
        relative_path="scripts/contract_authority_context.py",
        source_capsule=globals().get("__authority_source_capsule__"),
        source_reader=globals().get("__authority_read_source__"),
    )
)


def _first_loaded_source_observation() -> object | None:
    """Return immutable buffer provenance recorded while this module loaded."""

    return _FIRST_LOADED_SOURCE_OBSERVATION


def _first_loaded_context_source_matches_runtime_pin(pin: LoadedRuntimePin) -> bool:
    """Whether this context's executed buffer belongs to one runtime pin."""

    try:
        rows = {row.path: row for row in pin.closure_rows}
        row = rows.get("scripts/contract_authority_context.py")
        return row is not None and _fs_identity._first_loaded_module_source_matches_runtime_row(
            sys.modules[__name__],
            expected_path=_AUTHORITY_SCRIPTS_DIR / "contract_authority_context.py",
            relative_path="scripts/contract_authority_context.py",
            mode=row.mode,
            sha256=row.sha256,
        )
    except Exception:
        return False


# The passive snapshot module owns the compact-envelope schema.  Keep these
# aliases for existing direct context consumers without creating a second
# parser/schema contract here.
CONTEXT_SCHEMA_VERSION: Final[str] = _snapshot.CONTEXT_SCHEMA_VERSION
EntryObservationProvenance = Literal["observed_local", "inherited_supplied_unverified"]
ENTRY_OBSERVATION_PROVENANCE_OBSERVED_LOCAL: Final[EntryObservationProvenance] = cast(
    EntryObservationProvenance,
    _snapshot.ENTRY_OBSERVATION_PROVENANCE_OBSERVED_LOCAL,
)
ENTRY_OBSERVATION_PROVENANCE_INHERITED_SUPPLIED_UNVERIFIED: Final[EntryObservationProvenance] = cast(
    EntryObservationProvenance,
    _snapshot.ENTRY_OBSERVATION_PROVENANCE_INHERITED_SUPPLIED_UNVERIFIED,
)
GENERATION_SCHEMA_VERSION: Final[str] = "planveyor_contract_generation.v1"
EXPECTED_CONTEXT_ENV: Final[str] = "_PLANVEYOR_AUTHORITY_CONTEXT_V1"
MAX_CONTEXT_ENVELOPE_BYTES: Final[int] = _snapshot.MAX_CONTEXT_ENVELOPE_BYTES

# This is intentionally a reviewed-source gate.  It is not configurable through
# an environment variable, command-line option, target marker, or fixture route.
# The complete consumer census and rejection regressions guard this source gate.
ENGAGED_ADMISSION_COMPLETE: Final[bool] = True


# Target-local subset of the finite ``_planveyor_prompt_filename_for_role_phase``
# output, with manager:merge_pipeline and manager:collab_merge_pipeline
# deduplicated to their one body. C1 binds this tuple through
# REQUIRED_ENGAGED_PATHS.
_TARGET_LOCAL_PROMPT_FILENAMES: Final[tuple[str, ...]] = (
    "architect_canon_sweep.md",
    "architect_censor.md",
    "architect_docs_finalize_followups.md",
    "architect_docs_finalize_general.md",
    "architect_draft_discussion.md",
    "architect_init.md",
    "architect_merge_notes.md",
    "architect_plan_harvest.md",
    "architect_post_merge_audit.md",
    "architect_status_driven.md",
    "architect_track_innovations.md",
    "architect_track_process_collab.md",
    "architect_track_process_roles.md",
    "coder_censor.md",
    "coder_docs_finalize_followups.md",
    "coder_docs_finalize_general.md",
    "coder_init.md",
    "coder_merge_conflicts.md",
    "coder_migrations_gate.md",
    "coder_status_driven.md",
    "manager_collab_merge_pipeline.md",
    "manager_collab_pipeline.md",
    "manager_custom_pipeline.md",
    "manager_init.md",
    "manager_router.md",
    "planner_censor.md",
    "planner_docs_finalize_followups.md",
    "planner_docs_finalize_general.md",
    "planner_init.md",
    "planner_status_driven.md",
    "reviewer_docs_finalize_followups.md",
    "reviewer_docs_finalize_general.md",
    "reviewer_init.md",
    "reviewer_status_driven.md",
)

# Full finite shell census. The public ZCode overlay has its own bootstrap
# contract and is not a Manager role-phase prompt.
_PROMPT_FILENAMES: Final[tuple[str, ...]] = _TARGET_LOCAL_PROMPT_FILENAMES

_ROLE_PATHS: Final[tuple[str, ...]] = (
    "docs/roles/architect.md",
    "docs/roles/planner.md",
    "docs/roles/coder.md",
    "docs/roles/reviewer.md",
    "docs/roles/manager.md",
)

# The merge-gate carrier is a capability-bound Planveyor input.  It is not a
# discovery candidate: only a marker whose minimum API advertises the merge
# capability adds this one static row to the declared-generation input set.
PLANVEYOR_MERGE_GATE_POLICY_PATH: Final[str] = "docs/_meta/planveyor_merge_gate_policy.v1.json"

# These are retained body-bearing templates rather than an inferred glob.  New
# consumers are added by the owning integration lane through an explicit source
# change to this tuple.
_TEMPLATE_PATHS: Final[tuple[str, ...]] = (
    "docs/adr/_template.md",
    "docs/code_drafts/_template.md",
    "docs/code_reviews/_template_merge_range.md",
    "docs/code_reviews/_template_single_commit.md",
    "docs/doc_reviews/_template_merge_range.md",
    "docs/doc_reviews/_template_single_commit.md",
    "docs/followups/_template_followups_backlog.md",
    "docs/plans/_template.md",
    "docs/process_improvements/_template_process_improvements_backlog.md",
    "docs/reviews/_template_merge_notes.md",
    "docs/reviews/_template_plan_harvest.md",
    "docs/reviews/_template_post_merge_audit.md",
    "docs/rollout_packets/_template.md",
    "docs/upstream_packets/_template.md",
)

STATIC_REQUIRED_ENGAGED_PREFIX: Final[tuple[str, ...]] = (
    *(f"docs/tools/prompts/{name}" for name in _TARGET_LOCAL_PROMPT_FILENAMES),
    *_ROLE_PATHS,
)

STATIC_REQUIRED_ENGAGED_TAIL: Final[tuple[str, ...]] = (
    "docs/playbooks/docs_architecture.md",
    "AGENTS.md",
    "docs/_meta/plan_vocab.json",
    "docs/_meta/doc_classes.json",
    "docs/smoke_visual.md",
    "docs/testing_runbook.md",
    *_TEMPLATE_PATHS,
)

# The public 59-path corpus is one finite source-owned required set.
# Keep tuple composition AST-expandable for the authority matrix checker.
REQUIRED_ENGAGED_PATHS: Final[tuple[str, ...]] = (
    *STATIC_REQUIRED_ENGAGED_PREFIX,
    *STATIC_REQUIRED_ENGAGED_TAIL,
)

STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS: Final[tuple[str, ...]] = (
    *STATIC_REQUIRED_ENGAGED_PREFIX,
    *STATIC_REQUIRED_ENGAGED_TAIL,
)

STATIC_PLANVEYOR_MERGE_REQUIRED_ENGAGED_PATHS: Final[tuple[str, ...]] = (
    *STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS,
    PLANVEYOR_MERGE_GATE_POLICY_PATH,
)

if (
    len(_TARGET_LOCAL_PROMPT_FILENAMES) != len(set(_TARGET_LOCAL_PROMPT_FILENAMES))
    or _PROMPT_FILENAMES != _TARGET_LOCAL_PROMPT_FILENAMES
):  # pragma: no cover - source invariant.
    raise RuntimeError("prompt filename partition is invalid")

if len(REQUIRED_ENGAGED_PATHS) != len(set(REQUIRED_ENGAGED_PATHS)):  # pragma: no cover - source invariant.
    raise RuntimeError("REQUIRED_ENGAGED_PATHS contains a duplicate")

if (
    len(STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS) != 59
    or len(STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS) != len(set(STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS))
    or STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS != REQUIRED_ENGAGED_PATHS
):  # pragma: no cover - source invariant.
    raise RuntimeError("STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS is invalid")

if (
    len(STATIC_PLANVEYOR_MERGE_REQUIRED_ENGAGED_PATHS) != 60
    or len(STATIC_PLANVEYOR_MERGE_REQUIRED_ENGAGED_PATHS) != len(set(STATIC_PLANVEYOR_MERGE_REQUIRED_ENGAGED_PATHS))
    or STATIC_PLANVEYOR_MERGE_REQUIRED_ENGAGED_PATHS[:-1] != STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS
    or STATIC_PLANVEYOR_MERGE_REQUIRED_ENGAGED_PATHS[-1] != PLANVEYOR_MERGE_GATE_POLICY_PATH
):  # pragma: no cover - source invariant.
    raise RuntimeError("STATIC_PLANVEYOR_MERGE_REQUIRED_ENGAGED_PATHS is invalid")


@dataclass(frozen=True, slots=True)
class EntryObservation:
    """Immutable raw entry facts, retained for receipts but never generation equality."""

    root: Path
    git_dir: Path | None
    head: str | None
    tree: str | None
    index_sha256: str | None


@dataclass(frozen=True, slots=True)
class ContractContext:
    """One immutable invocation context.

    Compatibility fields for historical v1 candidate evidence remain present,
    but a live v2 selector context binds no content rows.  Its reader observes
    allowed current target bytes only after selector/runtime revalidation.
    """

    state: Literal["legacy", "engaged"]
    project_root: Path
    contract_root: Path
    behavior_identity: str
    entry_observation: EntryObservation
    entry_observation_provenance: EntryObservationProvenance
    runtime_pin: LoadedRuntimePin | None
    generation_sha256: str
    marker_file: TrackedFileIdentity | None
    closure_manifest_file: TrackedFileIdentity | None
    declared_rows: tuple[TrackedFileIdentity, ...]
    marker: AuthorityMarker | LocalAuthorityMarker | None
    closure_manifest: ClosureManifest | None
    fallback_used: bool


@dataclass(frozen=True, slots=True)
class _LocalEngagedMaterial:
    entry_observation: EntryObservation
    marker: LocalAuthorityMarker
    contract_root: Path


def _fail(reason_code: str, message: str) -> ContractAuthorityError:
    return ContractAuthorityError(reason_code, message)


def _canonical_json_bytes(value: object) -> bytes:
    return _snapshot._context_canonical_json_bytes(value)


def _sha256_json(value: object) -> str:
    return _snapshot._context_sha256_json(value)


def _validate_text(value: object, *, field: str) -> str:
    return _snapshot._validate_text(value, field=field)


def _validate_sha256(value: object, *, field: str) -> str:
    return _snapshot._validate_sha256(value, field=field)


def _validate_object_id(value: object, *, field: str) -> str:
    return _snapshot._validate_object_id(value, field=field)


def _validate_int(value: object, *, field: str) -> int:
    return _snapshot._validate_int(value, field=field)


def _validate_relative_path(value: object, *, field: str) -> str:
    return _snapshot._validate_relative_path(value, field=field)


def _resolved_directory(value: object, *, context: str) -> Path:
    return _snapshot._resolved_directory(value, context=context)


def _parse_json_object(text: object, *, context: str) -> dict[str, object]:
    return _snapshot._parse_context_json_object(text, context=context)


def _identity_to_entry(git: GitIdentity) -> EntryObservation:
    return EntryObservation(
        root=git.root,
        git_dir=git.git_dir,
        head=git.head,
        tree=git.tree,
        index_sha256=git.index_sha256,
    )


def _entry_to_envelope(entry: EntryObservation) -> dict[str, object]:
    return {
        "root": os.fspath(entry.root),
        "git_dir": None if entry.git_dir is None else os.fspath(entry.git_dir),
        "head": entry.head,
        "tree": entry.tree,
        "index_sha256": entry.index_sha256,
    }


def _runtime_pin_summary(pin: LoadedRuntimePin | None) -> dict[str, object] | None:
    if pin is None:
        return None
    return {
        "runtime_root": os.fspath(pin.runtime_root),
        "git_dir": os.fspath(pin.git_dir),
        "runtime_api_version": pin.runtime_api_version,
        "commit": pin.commit,
        "tree": pin.tree,
        "closure_spec_sha256": pin.closure_spec_sha256,
        "closure_rows_sha256": pin.closure_rows_sha256,
        "closure_sha256": pin.closure_sha256,
        "pin_sha256": pin.pin_sha256,
    }


def _row_to_mapping(row: TrackedFileIdentity) -> dict[str, str]:
    return {
        "path": row.path,
        "mode": row.mode,
        "blob_oid": row.blob_oid,
        "sha256": row.sha256,
    }


def _generation_digest(
    *,
    state: Literal["legacy", "engaged"],
    project_root: Path,
    git_dir: Path | None,
    behavior_identity: str,
    runtime_pin: LoadedRuntimePin | None,
    local_marker: LocalAuthorityMarker | None = None,
) -> str:
    payload: dict[str, object] = {
        "schema_version": GENERATION_SCHEMA_VERSION,
        "state": state,
        "project_root": os.fspath(project_root),
        "git_dir": None if git_dir is None else os.fspath(git_dir),
        "behavior_identity": behavior_identity,
        "runtime_pin_sha256": None if runtime_pin is None else runtime_pin.pin_sha256,
    }
    if state == "engaged":
        if local_marker is None or runtime_pin is None:
            raise _fail("context_generation_invalid", "engaged generation lacks selector or runtime pin")
        payload["local_selector"] = {
            "schema_version": local_marker.schema_version,
            "repository_id": local_marker.repository_id,
            "authority_mode": local_marker.authority_mode,
            "contract_root": local_marker.contract_root,
            "required_runtime_api": {
                "minimum": local_marker.required_runtime_api.minimum,
                "maximum": local_marker.required_runtime_api.maximum,
            },
            "source_commit": local_marker.source_commit,
        }
    return _sha256_json(payload)


def _git_command(root: Path, *arguments: str, context: str) -> subprocess.CompletedProcess[bytes]:
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
        return subprocess.run(
            command,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_snapshot._clean_git_environment(),
            timeout=_runtime.GIT_COMMAND_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise _fail("git_timeout", f"Git timed out while discovering {context}") from exc
    except OSError as exc:
        raise _fail("git_unavailable", f"cannot run Git while discovering {context}") from exc


def _has_ancestor_git_metadata(root: Path) -> bool:
    """Distinguish an ordinary non-Git directory from a broken Git discovery.

    Git discovers parents for a worktree.  If discovery fails but any ancestor
    advertises ``.git``, silently treating a broken worktree as legacy would be
    a marker/HEAD bypass.
    """

    current = root
    while True:
        try:
            os.lstat(current / ".git")
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise _fail("filesystem_ambiguous", "cannot inspect local Git metadata") from exc
        else:
            return True
        if current.parent == current:
            return False
        current = current.parent


def _discover_project_root(value: object, *, explicit: bool) -> tuple[Path, bool]:
    requested = _resolved_directory(value, context="project")
    completed = _git_command(
        requested,
        "rev-parse",
        "--is-inside-work-tree",
        "--show-toplevel",
        "--absolute-git-dir",
        context="project root",
    )
    if completed.returncode != 0:
        if _has_ancestor_git_metadata(requested):
            raise _fail(
                "git_discovery_failed",
                f"Git failed while discovering project root (exit status {completed.returncode})",
            )
        return requested, False
    try:
        lines = completed.stdout.decode("utf-8", "strict").splitlines()
    except UnicodeDecodeError as exc:
        raise _fail("git_output_invalid", "Git returned non-text project discovery output") from exc
    if len(lines) != 3 or lines[0] != "true" or not lines[1] or not lines[2]:
        raise _fail("git_output_invalid", "Git returned ambiguous project discovery output")
    top_text, git_dir_text = lines[1], lines[2]
    top_path = Path(top_text)
    git_dir_path = Path(git_dir_text)
    if not top_path.is_absolute() or not git_dir_path.is_absolute():
        raise _fail("git_output_invalid", "Git returned non-absolute project paths")
    top = _resolved_directory(top_path, context="project Git top-level")
    _resolved_directory(git_dir_path, context="project Git directory")
    if explicit and top != requested:
        raise _fail("git_root_mismatch", "explicit project_root is not the verified Git top-level")
    return top, True


def _physical_marker_present(root: Path) -> bool:
    try:
        observed = snapshot_regular_or_absent(root, _snapshot.MARKER_PATH)
    except ObjectIdentityError as exc:
        if exc.reason_code == "ancestor_missing":
            return False
        raise _fail(exc.reason_code, "authority marker cannot be safely observed") from exc
    return observed.state == "regular"


def _capture_legacy_entry(root: Path) -> EntryObservation:
    basis = _runtime._capture_git_basis(root)
    stable = _runtime._recheck_git_basis(basis)
    return EntryObservation(
        root=stable.root,
        git_dir=stable.git_dir,
        head=stable.head,
        tree=stable.tree,
        index_sha256=stable.index_sha256,
    )


def _safe_contract_root(project_root: Path, relative_root: str) -> Path:
    if relative_root == ".":
        return project_root
    candidate = project_root.joinpath(*relative_root.split("/"))
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError, ValueError, UnicodeError) as exc:
        raise _fail("contract_root_unavailable", "declared contract_root cannot be resolved") from exc
    if resolved != candidate or not resolved.is_dir():
        raise _fail("contract_root_unsafe", "declared contract_root must be a canonical non-symlink directory")
    return resolved


_LOCAL_EXACT_CONTENT_PATHS: Final[frozenset[str]] = frozenset(
    {
        "AGENTS.md",
        "docs/_meta/plan_vocab.json",
        "docs/_meta/doc_classes.json",
        "docs/_meta/planveyor_merge_gate_policy.v1.json",
        "docs/_meta/review_range_policy.v1.json",
        "docs/smoke_visual.md",
        "docs/testing_runbook.md",
    }
)
_LOCAL_FLAT_MARKDOWN_DIRS: Final[frozenset[str]] = frozenset(
    {"docs/tools/prompts", "docs/roles", "docs/playbooks"}
)
_LOCAL_TEMPLATE_DIRS: Final[frozenset[str]] = frozenset(
    {
        "docs/adr",
        "docs/code_drafts",
        "docs/code_reviews",
        "docs/doc_reviews",
        "docs/followups",
        "docs/plans",
        "docs/process_improvements",
        "docs/reviews",
        "docs/rollout_packets",
        "docs/upstream_packets",
    }
)


def _local_content_path_allowed(relative_path: str) -> bool:
    if relative_path in _LOCAL_EXACT_CONTENT_PATHS:
        return True
    if relative_path == "docs/tools/prompts/zcode/manager_pipeline.md":
        return True
    parent, separator, leaf = relative_path.rpartition("/")
    if not separator:
        return False
    if parent in _LOCAL_FLAT_MARKDOWN_DIRS:
        return leaf.endswith(".md")
    return parent in _LOCAL_TEMPLATE_DIRS and leaf.startswith("_template") and leaf.endswith(".md")


def _local_marker_behavior_identity(marker: LocalAuthorityMarker) -> str:
    """Select the schema-v2 marker's semantic behavior identity."""

    repository_id = marker.repository_id
    if repository_id == "default":
        raise _fail("unknown_behavior_identity", "engaged authority requires a known marker behavior identity")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", repository_id) is None:
        raise _fail(
            "repository_identity_invalid",
            "authority marker repository_id is not a supported behavior identity",
        )
    return repository_id


def _local_marker_bytes_or_absent(root: Path) -> bytes | None:
    """Read the physical schema-v2 selector without parsing its claim yet."""

    try:
        observed = snapshot_regular_or_absent(root, _snapshot.MARKER_PATH)
    except ObjectIdentityError as exc:
        if exc.reason_code == "ancestor_missing":
            return None
        raise _fail(exc.reason_code, "authority marker cannot be safely observed") from exc
    if observed.state == "absent":
        return None
    assert observed.data is not None
    return observed.data


def _capture_local_engaged_material(
    project_root: Path,
    *,
    marker: LocalAuthorityMarker,
) -> _LocalEngagedMaterial:
    entry = _capture_legacy_entry(project_root)
    return _LocalEngagedMaterial(
        entry_observation=entry,
        marker=marker,
        contract_root=_safe_contract_root(entry.root, marker.contract_root),
    )


def _git_common_directory(project_root: Path, *, context: str) -> Path:
    """Return one strictly validated canonical Git common directory."""

    completed = _git_command(project_root, "rev-parse", "--git-common-dir", context=context)
    if completed.returncode != 0:
        raise _fail("git_command_failed", f"cannot discover Git common directory for {context}")
    try:
        raw = completed.stdout.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise _fail("git_output_invalid", "Git returned non-text common directory") from exc
    if not raw.endswith("\n") or raw.count("\n") != 1 or not raw[:-1]:
        raise _fail("git_output_invalid", "Git returned ambiguous common directory")
    common = Path(raw[:-1])
    if not common.is_absolute():
        common = project_root / common
    return _resolved_directory(common, context="Git common directory")


def _markerless_behavior_identity(project_root: Path, runtime_root: Path) -> str:
    """Select the legacy self profile from canonical Git identity only.

    A target must have a valid common directory.  An ordinary runtime with no
    Git metadata is an external/initial-unattested legacy environment and
    therefore selects the neutral profile.  A runtime that advertises Git
    metadata but cannot resolve it, and malformed runtime output, fail closed.
    """

    target_common = _git_common_directory(project_root, context="markerless behavior identity")
    try:
        runtime_common = _git_common_directory(runtime_root, context="executing runtime behavior identity")
    except ContractAuthorityError as exc:
        if exc.reason_code == "git_command_failed" and not _has_ancestor_git_metadata(runtime_root):
            return "default"
        raise
    if os.path.lexists(runtime_root / '.git'):
        discovered_root, is_git = _discover_project_root(runtime_root, explicit=False)
        if not is_git or discovered_root != runtime_root.resolve():
            raise _fail('git_command_failed', 'local runtime Git metadata does not bind this runtime root')
    return "planveyor" if target_common == runtime_common else "default"


def _executing_runtime_root() -> Path:
    return _resolved_directory(Path(__file__).resolve().parents[1], context="executing runtime")


def _normalize_runtime_root(value: Path | None) -> Path:
    actual = _executing_runtime_root()
    if value is None:
        return actual
    supplied = _resolved_directory(value, context="runtime")
    if supplied != actual:
        raise _fail("runtime_source_mismatch", "runtime_root differs from the runtime that imported this context module")
    return actual


def _parse_loaded_pin_value(value: object) -> LoadedRuntimePin | None:
    if value is None:
        return None
    if isinstance(value, LoadedRuntimePin):
        return value
    if value == "unattested_legacy":
        return None
    parsed: object = value
    if type(value) is str:
        parsed = _parse_json_object(value, context="loaded runtime pin")
    if type(parsed) is dict and set(parsed) == {"state"} and parsed["state"] == "unattested_legacy":
        return None
    if type(parsed) is dict and set(parsed) == {"state", "pin"} and parsed["state"] == "pinned":
        parsed = parsed["pin"]
    try:
        return _runtime.loaded_runtime_pin_from_dict(parsed)
    except ContractAuthorityError:
        raise
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensive for a future runtime parser.
        raise _fail("runtime_pin_invalid", "loaded runtime pin is invalid") from exc


def _captured_runtime_pin(
    *,
    actual_runtime_root: Path,
    loaded_pin: object,
    required_for_engagement: bool,
) -> LoadedRuntimePin | None:
    observation = _runtime._first_loaded_runtime_observation()
    if observation.runtime_root != actual_runtime_root:
        raise _fail("runtime_source_mismatch", "loaded runtime observation belongs to a different runtime root")
    # The runtime pin attests bridge/fs/snapshot/runtime.  Context is imported
    # immediately afterward, so bind its own retained capsule before this
    # module is allowed to treat that pin as an authority input.
    observed_pin = observation.pin
    if observed_pin is not None and not _first_loaded_context_source_matches_runtime_pin(observed_pin):
        observed_pin = None

    # An omitted assertion means the caller accepts the pin frozen with the
    # imported code.  Any supplied concrete value must be that same frozen
    # pin; a fresh disk capture cannot attest code that was already imported
    # from older bytes.  An explicit unattested sentinel preserves the
    # long-standing bridge request to remain legacy after a shell sourced an
    # initially dirty runtime, but it still verifies a concrete first-import
    # pin before it can return a legacy context.
    request_unattested = False
    if loaded_pin is None:
        asserted_pin = observed_pin
    else:
        asserted_pin = _parse_loaded_pin_value(loaded_pin)
        request_unattested = asserted_pin is None

    pin = observed_pin
    if request_unattested:
        if pin is not None:
            if pin.runtime_root != actual_runtime_root:
                raise _fail("runtime_source_mismatch", "loaded runtime pin belongs to a different runtime root")
            try:
                verified = _runtime.verify_loaded_runtime_pin(pin)
            except ContractAuthorityError as exc:
                raise _fail("runtime_loaded_code_drift", "loaded runtime code differs from current runtime bytes") from exc
            if verified != pin or verified.runtime_root != actual_runtime_root:
                raise _fail("runtime_loaded_code_drift", "loaded runtime code differs from current runtime bytes")
        if required_for_engagement:
            raise _fail("runtime_pin_unattested", "engaged authority requires a verified loaded runtime pin")
        return None

    if asserted_pin != observed_pin:
        raise _fail("runtime_loaded_code_drift", "loaded runtime code differs from the asserted runtime pin")

    if pin is None:
        if required_for_engagement:
            raise _fail("runtime_pin_unattested", "engaged authority requires a verified loaded runtime pin")
        return None
    if pin.runtime_root != actual_runtime_root:
        raise _fail("runtime_source_mismatch", "loaded runtime pin belongs to a different runtime root")
    # A concrete first-import pin is always revalidated against disk before an
    # effect.  Any changed closure is code/runtime drift, not legacy fallback.
    try:
        verified = _runtime.verify_loaded_runtime_pin(pin)
    except ContractAuthorityError as exc:
        raise _fail("runtime_loaded_code_drift", "loaded runtime code differs from current runtime bytes") from exc
    if verified != pin or verified.runtime_root != actual_runtime_root:
        raise _fail("runtime_loaded_code_drift", "loaded runtime code differs from current runtime bytes")
    return pin


def _require_runtime_environment_match(pin: LoadedRuntimePin) -> None:
    raw = os.environ.get("PLANVEYOR_ROOT")
    if raw is None:
        return
    try:
        supplied = _resolved_directory(Path(raw), context="PLANVEYOR_ROOT")
    except ContractAuthorityError as exc:
        raise _fail("runtime_environment_split_brain", "PLANVEYOR_ROOT is not a verified runtime directory") from exc
    if supplied != pin.runtime_root:
        raise _fail("runtime_environment_split_brain", "PLANVEYOR_ROOT differs from loaded runtime pin")


def _legacy_context(
    *,
    project_root: Path,
    entry: EntryObservation,
    behavior_identity: str,
    runtime_root: Path,
    runtime_pin: LoadedRuntimePin | None,
) -> ContractContext:
    return ContractContext(
        state="legacy",
        project_root=project_root,
        contract_root=runtime_root,
        behavior_identity=behavior_identity,
        entry_observation=entry,
        entry_observation_provenance=ENTRY_OBSERVATION_PROVENANCE_OBSERVED_LOCAL,
        runtime_pin=runtime_pin,
        generation_sha256=_generation_digest(
            state="legacy",
            project_root=project_root,
            git_dir=entry.git_dir,
            behavior_identity=behavior_identity,
            runtime_pin=runtime_pin,
        ),
        marker_file=None,
        closure_manifest_file=None,
        declared_rows=(),
        marker=None,
        closure_manifest=None,
        fallback_used=True,
    )


def _compare_expected_context(context: ContractContext, envelope: dict[str, object]) -> None:
    expected_entry = cast(dict[str, object], envelope["entry_observation"])
    if (
        envelope["state"] != context.state
        or envelope["project_root"] != os.fspath(context.project_root)
        or expected_entry["root"] != os.fspath(context.project_root)
        or expected_entry["git_dir"] != (None if context.entry_observation.git_dir is None else os.fspath(context.entry_observation.git_dir))
        or envelope["behavior_identity"] != context.behavior_identity
        or envelope["generation_sha256"] != context.generation_sha256
        or envelope["runtime_pin"] != _runtime_pin_summary(context.runtime_pin)
        or envelope["fallback_used"] != context.fallback_used
    ):
        raise _fail("context_expectation_mismatch", "actual authority context differs from inherited expectation")


def _resolve_top_level_context(
    project_root: Path | None = None,
    *,
    runtime_root: Path | None = None,
    loaded_pin: object = None,
    inherited: dict[str, object] | None = None,
) -> ContractContext:
    """Capture current authority facts and compare an already parsed assertion."""

    target, is_git = _discover_project_root(
        Path.cwd() if project_root is None else project_root,
        explicit=project_root is not None,
    )
    actual_runtime_root = _normalize_runtime_root(runtime_root)
    if not is_git:
        if _physical_marker_present(target):
            raise _fail("marker_in_non_git", "authority marker exists outside a verified Git worktree")
        pin = _captured_runtime_pin(
            actual_runtime_root=actual_runtime_root,
            loaded_pin=loaded_pin,
            required_for_engagement=False,
        )
        context = _legacy_context(
            project_root=target,
            entry=EntryObservation(root=target, git_dir=None, head=None, tree=None, index_sha256=None),
            behavior_identity="default",
            runtime_root=actual_runtime_root,
            runtime_pin=pin,
        )
        if inherited is not None:
            _compare_expected_context(context, inherited)
        return context

    marker_bytes = _local_marker_bytes_or_absent(target)
    if marker_bytes is None:
        behavior = _markerless_behavior_identity(target, actual_runtime_root)
        entry = _capture_legacy_entry(target)
        pin = _captured_runtime_pin(
            actual_runtime_root=actual_runtime_root,
            loaded_pin=loaded_pin,
            required_for_engagement=False,
        )
        context = _legacy_context(
            project_root=entry.root,
            entry=entry,
            behavior_identity=behavior,
            runtime_root=actual_runtime_root,
            runtime_pin=pin,
        )
        if inherited is not None:
            _compare_expected_context(context, inherited)
        return context

    # A physical marker is an opt-in.  It must never downgrade to legacy while
    # this reviewed source is still intentionally incomplete.  Validate its
    # canonical Git physical binding before parsing the semantic marker claim.
    _git_common_directory(target, context="local marker physical binding")
    marker = _snapshot.parse_local_marker_bytes(marker_bytes)
    if not ENGAGED_ADMISSION_COMPLETE:
        raise _fail("engaged_admission_incomplete", "target authority marker is present before complete admission")

    behavior = _local_marker_behavior_identity(marker)
    material = _capture_local_engaged_material(target, marker=marker)
    pin = _captured_runtime_pin(
        actual_runtime_root=actual_runtime_root,
        loaded_pin=loaded_pin,
        required_for_engagement=True,
    )
    if pin is None:  # pragma: no cover - required_for_engagement above guarantees this.
        raise _fail("runtime_pin_unattested", "engaged authority requires a runtime pin")
    _require_runtime_environment_match(pin)
    api = material.marker.required_runtime_api
    if not api.minimum <= pin.runtime_api_version <= api.maximum:
        raise _fail("runtime_api_incompatible", "loaded runtime API is outside the marker range")
    generation = _generation_digest(
        state="engaged",
        project_root=material.entry_observation.root,
        git_dir=material.entry_observation.git_dir,
        behavior_identity=behavior,
        runtime_pin=pin,
        local_marker=material.marker,
    )
    context = ContractContext(
        state="engaged",
        project_root=material.entry_observation.root,
        contract_root=material.contract_root,
        behavior_identity=behavior,
        entry_observation=material.entry_observation,
        entry_observation_provenance=ENTRY_OBSERVATION_PROVENANCE_OBSERVED_LOCAL,
        runtime_pin=pin,
        generation_sha256=generation,
        marker_file=None,
        closure_manifest_file=None,
        declared_rows=(),
        marker=material.marker,
        closure_manifest=None,
        fallback_used=False,
    )
    if inherited is not None:
        _compare_expected_context(context, inherited)
    return context


def _parse_active_context_envelope(text: str) -> dict[str, object]:
    parsed = parse_context_envelope(text)
    if parsed["schema_version"] != CONTEXT_SCHEMA_VERSION:
        raise _fail(
            "context_active_schema_unsupported",
            "active authority context requires the current context schema",
        )
    return parsed


def _inherited_envelope_from_expected(expected: str | None) -> dict[str, object] | None:
    selected = os.environ[EXPECTED_CONTEXT_ENV] if expected is None and EXPECTED_CONTEXT_ENV in os.environ else expected
    return None if selected is None else _parse_active_context_envelope(selected)


def _with_inherited_entry_observation(
    context: ContractContext,
    inherited: dict[str, object],
) -> ContractContext:
    """Keep supplied historical facts, without elevating their provenance.

    The compact envelope is an assertion, even when its self-digest was
    recomputed and it claims ``observed_local``.  Current root/gitdir,
    generation, and runtime checks make it safe to continue the invocation,
    but cannot prove what a parent invocation observed.
    """

    entry = cast(dict[str, object], inherited["entry_observation"])
    return replace(
        context,
        entry_observation=EntryObservation(
            root=context.entry_observation.root,
            git_dir=context.entry_observation.git_dir,
            head=cast(str | None, entry["head"]),
            tree=cast(str | None, entry["tree"]),
            index_sha256=cast(str | None, entry["index_sha256"]),
        ),
        entry_observation_provenance=ENTRY_OBSERVATION_PROVENANCE_INHERITED_SUPPLIED_UNVERIFIED,
    )


def resolve_top_level_context(
    project_root: Path | None = None,
    *,
    runtime_root: Path | None = None,
    loaded_pin: object = None,
    expected: str | None = None,
) -> ContractContext:
    """Capture one top-level context; inherited data is comparison-only.

    A supplied/default compact envelope never chooses current paths or bytes.
    When it compares successfully, its original entry observation remains in
    the receipt-facing result even if unrelated target history evolved, but is
    explicitly classified as supplied and unverified.
    """

    inherited = _inherited_envelope_from_expected(expected)
    context = _resolve_top_level_context(
        project_root,
        runtime_root=runtime_root,
        loaded_pin=loaded_pin,
        inherited=inherited,
    )
    return context if inherited is None else _with_inherited_entry_observation(context, inherited)


def validate_inherited_context(
    expected: str,
    project_root: Path | None = None,
    *,
    runtime_root: Path | None = None,
    loaded_pin: object = None,
) -> ContractContext:
    """Capture current facts and compare them with a compact parent assertion."""

    inherited = _parse_active_context_envelope(expected)
    context = _resolve_top_level_context(
        project_root,
        runtime_root=runtime_root,
        loaded_pin=loaded_pin,
        inherited=inherited,
    )
    return _with_inherited_entry_observation(context, inherited)


def _validate_context_type(context: object) -> ContractContext:
    if not isinstance(context, ContractContext):
        raise _fail("invalid_contract_context", "context must be a ContractContext")
    if context.state not in {"legacy", "engaged"}:
        raise _fail("invalid_contract_context", "context has an unknown state")
    if context.entry_observation_provenance not in {
        ENTRY_OBSERVATION_PROVENANCE_OBSERVED_LOCAL,
        ENTRY_OBSERVATION_PROVENANCE_INHERITED_SUPPLIED_UNVERIFIED,
    }:
        raise _fail("invalid_contract_context", "context has an unknown entry observation provenance")
    return context


def _same_project_root(value: Path, context: ContractContext) -> None:
    candidate, is_git = _discover_project_root(value, explicit=True)
    if candidate != context.project_root:
        raise _fail("context_project_root_mismatch", "reader project root differs from authority context")
    if context.entry_observation.git_dir is None and is_git:
        raise _fail("context_project_root_mismatch", "legacy non-Git context cannot become Git in a nested reader")
    if context.entry_observation.git_dir is not None and not is_git:
        raise _fail("context_project_root_mismatch", "Git context cannot become non-Git in a nested reader")


def context_for_reader(project_root: Path, context: ContractContext | None = None) -> ContractContext:
    """Return one explicit context for an imported reader, revalidating supplied state."""

    if context is None:
        return resolve_top_level_context(project_root)
    current = _validate_context_type(context)
    _same_project_root(project_root, current)
    validate_before_effect(current)
    return current


def _relative_declared_path(context: ContractContext, relative_path: str) -> tuple[str, TrackedFileIdentity | None]:
    path = _validate_relative_path(relative_path, field="relative_path")
    if context.state == "legacy":
        return path, None
    try:
        contract_relative = context.contract_root.relative_to(context.project_root).as_posix()
    except ValueError as exc:  # pragma: no cover - context construction guarantees this.
        raise _fail("invalid_contract_context", "contract_root is outside project_root") from exc
    target_relative = path if contract_relative == "." else f"{contract_relative}/{path}"
    row_by_path = {row.path: row for row in context.declared_rows}
    row = row_by_path.get(target_relative)
    if row is None:
        raise _fail("undeclared_contract_read", f"{path} is not a declared contract input")
    return target_relative, row


def _snapshot_verified_bytes(root: Path, relative_path: str, row: TrackedFileIdentity | None, *, purpose: str) -> bytes:
    try:
        observed = snapshot_regular_or_absent(root, relative_path)
    except ObjectIdentityError as exc:
        raise _fail(exc.reason_code, f"{purpose} cannot be safely observed") from exc
    if observed.state != "regular" or observed.data is None:
        raise _fail("declared_read_missing", f"{purpose} is absent: {relative_path}")
    if row is not None:
        digest = hashlib.sha256(observed.data).hexdigest()
        if observed.git_mode != row.mode:
            raise _fail("declared_read_mode_mismatch", f"{purpose} mode differs from captured declaration")
        if digest != row.sha256:
            raise _fail("declared_read_digest_mismatch", f"{purpose} bytes differ from captured declaration")
    return observed.data


def _local_read_snapshot(
    context: ContractContext,
    relative_path: str,
    *,
    purpose: str,
) -> tuple[str, Any]:
    """Safely observe one current v2-local content file.

    Revalidating the selector and runtime happens before reader membership so a
    changed selector cannot be hidden behind an otherwise-invalid input path.
    """

    validate_before_effect(context)
    logical = _validate_relative_path(relative_path, field="relative_path")
    if not _local_content_path_allowed(logical):
        raise _fail("undeclared_contract_read", f"{logical} is not an allowed local contract input")
    try:
        prefix = context.contract_root.relative_to(context.project_root).as_posix()
        target_relative = logical if prefix == "." else f"{prefix}/{logical}"
        observed = snapshot_regular_or_absent(context.project_root, target_relative)
    except ObjectIdentityError as exc:
        if exc.reason_code == "ancestor_missing":
            raise _fail("declared_read_missing", f"{purpose} is absent: {logical}") from exc
        raise _fail(exc.reason_code, f"{purpose} cannot be safely observed") from exc
    if observed.state != "regular" or observed.data is None:
        raise _fail("declared_read_missing", f"{purpose} is absent: {logical}")
    return logical, observed


def require_declared_read(context: ContractContext, relative_path: str, purpose: str = "contract") -> Path:
    """Return one verified canonical read path, without accepting containment as membership."""

    current = _validate_context_type(context)
    purpose_text = _validate_text(purpose, field="purpose")
    if current.state == "engaged":
        logical, _observed = _local_read_snapshot(current, relative_path, purpose=purpose_text)
        return current.contract_root.joinpath(*logical.split("/"))
    target_relative, _row = _relative_declared_path(current, relative_path)
    _snapshot_verified_bytes(current.contract_root, target_relative, None, purpose=purpose_text)
    return current.contract_root.joinpath(*target_relative.split("/"))


def read_declared_bytes(context: ContractContext, relative_path: str, purpose: str = "contract") -> bytes:
    """Read one selected body through a descriptor-verified declared row."""

    current = _validate_context_type(context)
    purpose_text = _validate_text(purpose, field="purpose")
    if current.state == "engaged":
        _logical, observed = _local_read_snapshot(current, relative_path, purpose=purpose_text)
        assert observed.data is not None
        return observed.data
    target_relative, _row = _relative_declared_path(current, relative_path)
    return _snapshot_verified_bytes(current.contract_root, target_relative, None, purpose=purpose_text)


def read_declared_text(context: ContractContext, relative_path: str, purpose: str = "contract") -> str:
    data = read_declared_bytes(context, relative_path, purpose)
    try:
        return data.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise _fail("declared_read_not_utf8", f"{purpose} is not valid UTF-8") from exc


def validate_before_effect(context: ContractContext) -> None:
    """Revalidate the current selector and runtime without replacing entry evidence."""

    current = _validate_context_type(context)
    runtime_root = current.runtime_pin.runtime_root if current.runtime_pin is not None else _executing_runtime_root()
    rechecked = resolve_top_level_context(
        current.project_root,
        runtime_root=runtime_root,
        loaded_pin=current.runtime_pin if current.runtime_pin is not None else "unattested_legacy",
        expected=None,
    )
    if (
        rechecked.state != current.state
        or rechecked.project_root != current.project_root
        or rechecked.entry_observation.git_dir != current.entry_observation.git_dir
        or rechecked.behavior_identity != current.behavior_identity
        or rechecked.generation_sha256 != current.generation_sha256
        or _runtime_pin_summary(rechecked.runtime_pin) != _runtime_pin_summary(current.runtime_pin)
    ):
        raise _fail("authority_generation_mismatch", "authority generation changed after context capture")


def _envelope_body(context: ContractContext) -> dict[str, object]:
    current = _validate_context_type(context)
    return {
        "schema_version": CONTEXT_SCHEMA_VERSION,
        "state": current.state,
        "project_root": os.fspath(current.project_root),
        "entry_observation": _entry_to_envelope(current.entry_observation),
        "entry_observation_provenance": current.entry_observation_provenance,
        "behavior_identity": current.behavior_identity,
        "runtime_pin": _runtime_pin_summary(current.runtime_pin),
        "generation_sha256": current.generation_sha256,
        "fallback_used": current.fallback_used,
    }


def context_to_json(context: ContractContext) -> str:
    """Return a compact, passive-read-safe canonical envelope for child assertions."""

    body = _envelope_body(context)
    envelope = {**body, "context_sha256": _sha256_json(body)}
    encoded = _canonical_json_bytes(envelope)
    if len(encoded) > MAX_CONTEXT_ENVELOPE_BYTES:
        raise _fail("context_envelope_too_large", "authority context envelope exceeds its fixed bound")
    return encoded.decode("utf-8")


def parse_context_envelope(text: str) -> dict[str, object]:
    """Compatibility API for the snapshot-owned passive envelope parser."""

    return _snapshot.parse_context_envelope(text)


__all__ = [
    "CONTEXT_SCHEMA_VERSION",
    "ContractAuthorityError",
    "ContractContext",
    "ENTRY_OBSERVATION_PROVENANCE_INHERITED_SUPPLIED_UNVERIFIED",
    "ENTRY_OBSERVATION_PROVENANCE_OBSERVED_LOCAL",
    "ENGAGED_ADMISSION_COMPLETE",
    "EXPECTED_CONTEXT_ENV",
    "EntryObservation",
    "EntryObservationProvenance",
    "MAX_CONTEXT_ENVELOPE_BYTES",
    "REQUIRED_ENGAGED_PATHS",
    "PLANVEYOR_MERGE_GATE_POLICY_PATH",
    "STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS",
    "STATIC_PLANVEYOR_MERGE_REQUIRED_ENGAGED_PATHS",
    "context_for_reader",
    "context_to_json",
    "parse_context_envelope",
    "read_declared_bytes",
    "read_declared_text",
    "require_declared_read",
    "resolve_top_level_context",
    "validate_before_effect",
    "validate_inherited_context",
]

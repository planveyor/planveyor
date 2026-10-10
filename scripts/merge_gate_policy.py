#!/usr/bin/env python3
"""Finite Planveyor merge-gate policy reader, renderer, and tracker binding.

This is deliberately a narrow authority reader.  It neither dispatches policy
commands nor discovers a policy carrier: engaged Planveyor callers receive the
single declared carrier through ``contract_authority_context``.  Legacy
trackers remain on their existing code paths.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Any, cast


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import contract_authority_context as authority


POLICY_PATH = "docs/_meta/planveyor_merge_gate_policy.v1.json"
POLICY_SCHEMA = "planveyor_merge_gate_policy.v1"
CONSUMER_SCHEMA_PROBE = "consumer_schema_paths.v1"
MINIMUM_MERGE_API = 4
BINDING_HEADERS = ("POLICY_SCHEMA", "POLICY_SHA256", "AUTHORITY_GENERATION")

CORE_IDS = (
    "step:review_range",
    "step:merge_notes",
    "step:plan_harvest",
    "step:canon_sweep",
    "step:packetization_gate",
    "step:docs_finalize",
    "step:doc_lint",
    "step:post_merge_audit",
    "step:docs_hygiene_archive",
    "step:docs_hygiene_suggest",
    "step:ready_to_push",
)
MIGRATIONS_ID = "step:migrations_gate"
LEDGER_ID = "step:ledger_lint"
_COMMAND_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_MODE_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_WORD_RE = re.compile(r"^[a-z][a-z0-9_-]{0,127}$")
_FLAG_RE = re.compile(r"^--[a-z][a-z0-9-]{0,127}$")
_HEADER_RE = re.compile(r"^(?P<key>[A-Z][A-Z0-9_]*)=(?P<value>.*)$")
_CONSUMER_REPOSITORY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class MergeGatePolicyError(ValueError):
    """One deterministic rejection without a policy or tracker fallback."""

    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


def _fail(reason_code: str, message: str) -> MergeGatePolicyError:
    return MergeGatePolicyError(reason_code, message)


def _object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in pairs:
        if not isinstance(key, str):  # json itself makes this unreachable.
            raise _fail("merge_policy_json_invalid", "JSON object key is not text")
        if key in out:
            raise _fail("merge_policy_duplicate_key", f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _json_object(raw: bytes) -> dict[str, object]:
    try:
        text = raw.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise _fail("merge_policy_not_utf8", "merge policy is not UTF-8") from exc
    try:
        parsed = json.loads(text, object_pairs_hook=_object_pairs)
    except MergeGatePolicyError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise _fail("merge_policy_json_invalid", "merge policy is not one valid JSON object") from exc
    if type(parsed) is not dict:
        raise _fail("merge_policy_json_invalid", "merge policy root must be an object")
    return parsed


def _mapping(value: object, *, field: str) -> dict[str, object]:
    if type(value) is not dict:
        raise _fail("merge_policy_shape_invalid", f"{field} must be an object")
    return value


def _list(value: object, *, field: str) -> list[object]:
    if type(value) is not list:
        raise _fail("merge_policy_shape_invalid", f"{field} must be an array")
    return value


def _text(value: object, *, field: str) -> str:
    if type(value) is not str or not value:
        raise _fail("merge_policy_shape_invalid", f"{field} must be nonempty text")
    return value


def _exact_keys(value: dict[str, object], keys: set[str], *, field: str) -> None:
    if set(value) != keys:
        raise _fail("merge_policy_shape_invalid", f"{field} has unknown, missing, or malformed fields")


def _label(position: int) -> str:
    # Policy bounds cap the result at R, avoiding an unbounded alphabet scheme.
    return chr(ord("A") + position)


@dataclass(frozen=True)
class Command:
    command_id: str
    argv: tuple[str, ...]


@dataclass(frozen=True)
class MigrationMode:
    name: str
    precheck_command_id: str
    apply_command_id: str


@dataclass(frozen=True)
class Migration:
    check_command_id: str
    modes: tuple[MigrationMode, ...]
    merge_command_id: str


@dataclass(frozen=True)
class MergeGatePolicy:
    raw_sha256: str
    commands: dict[str, Command]
    migration: Migration | None
    doc_lint_command_id: str
    ledger_command_id: str | None
    ledger_required: bool

    @property
    def step_keys(self) -> tuple[str, ...]:
        before = (MIGRATIONS_ID,) if self.migration is not None else ()
        ledger = (LEDGER_ID,) if self.ledger_required else ()
        return (*before, *CORE_IDS[:7], *ledger, *CORE_IDS[7:])

    def command(self, command_id: str) -> Command:
        try:
            return self.commands[command_id]
        except KeyError as exc:  # Parser guards every reference before construction.
            raise _fail("merge_policy_reference_invalid", f"unknown command reference: {command_id}") from exc


@dataclass(frozen=True)
class TrackerBinding:
    context: authority.ContractContext
    policy: MergeGatePolicy
    tracker_path: Path
    resolved_tracker_path: Path


@dataclass(frozen=True)
class _TrackerBoundary:
    """One discovered policy root and the unmodified spelling beneath it.

    ``root`` is the physical root used to select the authority context.  The
    other two fields deliberately retain the caller's spelling: a component
    after the boundary may be a symlink or ``..``, so replacing either with a
    resolved parent would select a different tracker before topology checks
    get a chance to reject it.
    """

    root: Path
    root_spelling: Path
    raw_suffix: tuple[str, ...]

    @property
    def tracker_path(self) -> Path:
        path = self.root_spelling
        for component in self.raw_suffix:
            path = path / component
        return path


def _parse_commands(value: object) -> dict[str, Command]:
    rows = _list(value, field="commands")
    if not 1 <= len(rows) <= 64:
        raise _fail("merge_policy_command_count_invalid", "commands must contain 1 through 64 rows")
    commands: dict[str, Command] = {}
    for index, item in enumerate(rows):
        row = _mapping(item, field=f"commands[{index}]")
        _exact_keys(row, {"id", "argv"}, field=f"commands[{index}]")
        command_id = _text(row["id"], field=f"commands[{index}].id")
        if not _COMMAND_ID_RE.fullmatch(command_id) or command_id in commands:
            raise _fail("merge_policy_command_id_invalid", "command IDs must be unique safe identifiers")
        tokens = _list(row["argv"], field=f"commands[{index}].argv")
        if not 1 <= len(tokens) <= 16:
            raise _fail("merge_policy_argv_invalid", "argv must contain 1 through 16 tokens")
        argv: list[str] = []
        for token_index, token in enumerate(tokens):
            text = _text(token, field=f"commands[{index}].argv[{token_index}]")
            allowed = _WORD_RE.fullmatch(text) if token_index == 0 else (_WORD_RE.fullmatch(text) or _FLAG_RE.fullmatch(text))
            if not allowed:
                raise _fail("merge_policy_argv_invalid", "argv contains an unsafe token")
            argv.append(text)
        commands[command_id] = Command(command_id=command_id, argv=tuple(argv))
    return commands


def _command_ref(value: object, *, field: str, references: list[str]) -> str:
    command_id = _text(value, field=field)
    if not _COMMAND_ID_RE.fullmatch(command_id):
        raise _fail("merge_policy_reference_invalid", f"{field} is not a safe command ID")
    references.append(command_id)
    return command_id


def _parse_policy(raw: bytes) -> MergeGatePolicy:
    root = _json_object(raw)
    _exact_keys(root, {"schema", "repository_id", "steps", "commands", "ledger_required"}, field="root")
    if root["schema"] != POLICY_SCHEMA or root["repository_id"] != "planveyor":
        raise _fail("merge_policy_identity_invalid", "merge policy schema or repository identity is invalid")
    if type(root["ledger_required"]) is not bool:
        raise _fail("merge_policy_ledger_invalid", "ledger_required must be boolean")
    ledger_required = bool(root["ledger_required"])
    commands = _parse_commands(root["commands"])
    steps = _list(root["steps"], field="steps")
    references: list[str] = []
    doc_lint_command_id = ""
    ledger_command_id: str | None = None
    position = 0
    migration: Migration | None = None
    if steps and _mapping(steps[0], field="steps[0]").get("id") == MIGRATIONS_ID:
        row = _mapping(steps[0], field="steps[0]")
        _exact_keys(row, {"id", "migration"}, field="steps[0]")
        migration_row = _mapping(row["migration"], field="steps[0].migration")
        _exact_keys(
            migration_row,
            {"change_probe", "check_command_id", "modes", "merge_command_id"},
            field="steps[0].migration",
        )
        if migration_row["change_probe"] != CONSUMER_SCHEMA_PROBE:
            raise _fail("merge_policy_probe_invalid", "consumer schema change_probe is not admitted by V1")
        check = _command_ref(migration_row["check_command_id"], field="migration.check_command_id", references=references)
        merge = _command_ref(migration_row["merge_command_id"], field="migration.merge_command_id", references=references)
        mode_rows = _list(migration_row["modes"], field="migration.modes")
        if not 1 <= len(mode_rows) <= 16:
            raise _fail("merge_policy_mode_count_invalid", "migration modes must contain 1 through 16 rows")
        modes: list[MigrationMode] = []
        names: set[str] = set()
        for index, item in enumerate(mode_rows):
            mode = _mapping(item, field=f"migration.modes[{index}]")
            _exact_keys(mode, {"mode", "precheck_command_id", "apply_command_id"}, field=f"migration.modes[{index}]")
            name = _text(mode["mode"], field=f"migration.modes[{index}].mode")
            if not _MODE_RE.fullmatch(name) or name in names:
                raise _fail("merge_policy_mode_invalid", "migration mode names must be unique safe identifiers")
            names.add(name)
            modes.append(
                MigrationMode(
                    name=name,
                    precheck_command_id=_command_ref(mode["precheck_command_id"], field="migration.precheck_command_id", references=references),
                    apply_command_id=_command_ref(mode["apply_command_id"], field="migration.apply_command_id", references=references),
                )
            )
        migration = Migration(check_command_id=check, modes=tuple(modes), merge_command_id=merge)
        position = 1

    for expected in CORE_IDS:
        if expected == "step:post_merge_audit" and ledger_required:
            if position >= len(steps):
                raise _fail("merge_policy_steps_invalid", "ledger step is required before post_merge_audit")
            ledger_row = _mapping(steps[position], field=f"steps[{position}]")
            _exact_keys(ledger_row, {"id", "command_id"}, field=f"steps[{position}]")
            if ledger_row["id"] != LEDGER_ID:
                raise _fail("merge_policy_steps_invalid", "ledger step order is invalid")
            ledger_command_id = _command_ref(ledger_row["command_id"], field="ledger.command_id", references=references)
            position += 1
        if position >= len(steps):
            raise _fail("merge_policy_steps_invalid", "core steps are missing")
        row = _mapping(steps[position], field=f"steps[{position}]")
        expected_keys = {"id", "command_id"} if expected == "step:doc_lint" else {"id"}
        _exact_keys(row, expected_keys, field=f"steps[{position}]")
        if row["id"] != expected:
            raise _fail("merge_policy_steps_invalid", "core step order is invalid")
        if expected == "step:doc_lint":
            doc_lint_command_id = _command_ref(row["command_id"], field="doc_lint.command_id", references=references)
        position += 1
    if position != len(steps):
        raise _fail("merge_policy_steps_invalid", "steps contain an unknown or duplicate row")
    if len(references) != len(set(references)):
        raise _fail("merge_policy_reference_invalid", "each command must be referenced exactly once")
    if set(references) != set(commands):
        raise _fail("merge_policy_reference_invalid", "commands must be exactly and only the referenced catalog")
    if not doc_lint_command_id or (ledger_required and ledger_command_id is None):  # pragma: no cover - row shape guards above.
        raise _fail("merge_policy_internal", "command-bearing policy rows were not retained")
    return MergeGatePolicy(
        raw_sha256=hashlib.sha256(raw).hexdigest(),
        commands=commands,
        migration=migration,
        doc_lint_command_id=doc_lint_command_id,
        ledger_command_id=ledger_command_id,
        ledger_required=ledger_required,
    )


def _policy_for_context(context: authority.ContractContext) -> MergeGatePolicy | None:
    current = authority.context_for_reader(context.project_root, context)
    if current.state == "legacy":
        return None
    marker = current.marker
    pin = current.runtime_pin
    identity = current.behavior_identity
    if (
        marker is None
        or pin is None
        or type(identity) is not str
        or identity == "default"
        or _CONSUMER_REPOSITORY_ID_RE.fullmatch(identity) is None
        or marker.repository_id != identity
    ):
        raise _fail("merge_policy_capability_required", "merge operations require an engaged Planveyor marker")
    api = marker.required_runtime_api
    if api.minimum < MINIMUM_MERGE_API or not api.minimum <= pin.runtime_api_version <= api.maximum:
        raise _fail("merge_policy_capability_required", "engaged marker does not advertise the merge capability")
    raw = authority.read_declared_bytes(current, POLICY_PATH, purpose="merge gate policy")
    return _parse_policy(raw)


def _markerless_unborn_legacy_root(root: Path) -> bool:
    """Recognize the historic report-fixture shape without masking engagement.

    Existing report callers support a newly initialized Git worktree before it
    has a first commit.  The full authority snapshot correctly requires a HEAD
    when it is asked to capture one, but no marker can be engaged only when
    the marker is absent from both the worktree and every index stage and no
    inherited context was supplied.  A present, staged, unmerged, or deleted
    marker, a committed HEAD, an inherited envelope, or an inconclusive Git
    result stays on the normal fail-closed authority path.
    """

    if os.environ.get(authority.EXPECTED_CONTEXT_ENV) is not None:
        return False
    project_root, is_git = authority._discover_project_root(root, explicit=False)
    if not is_git or authority._physical_marker_present(project_root):
        return False
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment["LC_ALL"] = "C"
    try:
        index = subprocess.run(
            [
                "git",
                "-C",
                os.fspath(project_root),
                "ls-files",
                "--stage",
                "-z",
                "--",
                authority._snapshot.MARKER_PATH,
            ],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            timeout=authority._runtime.GIT_COMMAND_TIMEOUT_SECONDS,
        )
        if index.returncode != 0 or not isinstance(index.stdout, bytes) or index.stdout:
            return False
        completed = subprocess.run(
            ["git", "-C", os.fspath(project_root), "rev-parse", "--verify", "--quiet", "HEAD"],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            timeout=authority._runtime.GIT_COMMAND_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return isinstance(completed.returncode, int) and completed.returncode == 1


def policy_for_root(root: Path) -> tuple[authority.ContractContext | None, MergeGatePolicy | None]:
    if _markerless_unborn_legacy_root(root):
        return None, None
    context = authority.resolve_top_level_context(root)
    return context, _policy_for_context(context)


def render_step(policy: MergeGatePolicy, step: str) -> str:
    """Render policy-owned command text only; it never executes a command."""

    if step == MIGRATIONS_ID:
        if policy.migration is None:
            raise _fail("merge_policy_step_invalid", "policy has no declared consumer schema gate")
        lines = [
            "# A) Declared consumer schema gate — primary check",
            " ".join(policy.command(policy.migration.check_command_id).argv),
        ]
        labels: list[str] = []
        for index, mode in enumerate(policy.migration.modes, start=1):
            label = _label(index)
            labels.append(label)
            lines.extend(
                [
                    "",
                    f"# {label}) Declared consumer schema gate ({mode.name}) — pre-check + apply",
                    " ".join(policy.command(mode.precheck_command_id).argv),
                    " ".join(policy.command(mode.apply_command_id).argv),
                ]
            )
        recovery = _label(len(policy.migration.modes) + 1)
        lines.extend(
            [
                "",
                f"# {recovery}) If declared consumer schema controls conflict — run the declared resolution command",
                " ".join(policy.command(policy.migration.merge_command_id).argv),
                f"# then repeat {'/'.join(labels)}",
            ]
        )
        return "\n".join(lines)
    if step == "step:doc_lint":
        return "# A) Gate: doc-lint\n" + " ".join(policy.command(policy.doc_lint_command_id).argv)
    if step == LEDGER_ID:
        if not policy.ledger_required:
            raise _fail("merge_policy_step_invalid", "policy does not require ledger lint")
        assert policy.ledger_command_id is not None  # parser guards ledger-required policy shape.
        return "# A) Gate: target-declared ledger lint\n" + " ".join(policy.command(policy.ledger_command_id).argv)
    raise _fail("merge_policy_step_invalid", "step has no policy-owned renderer")


def _absolute_unresolved(path: Path) -> Path:
    """Make a path absolute without collapsing an alias-bearing traversal."""

    raw = os.fspath(path)
    return Path(raw if os.path.isabs(raw) else os.path.join(os.getcwd(), raw))


def _lexically_contained(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath((os.fspath(path), os.fspath(root))) == os.fspath(root)
    except ValueError:
        return False


def _tracker_boundary_before_parent_alias(tracker_path: Path) -> _TrackerBoundary | None:
    """Admit lexical Git authority before crossing a tracker parent alias or ``..``.

    Aliases before a Git root are normalized.  At a discovered lexical root,
    policy_for_root must admit its authority before an alias or ``..`` is
    crossed: malformed authority fails closed.  An admitted markerless legacy
    root permits continued discovery on the caller's uncollapsed spelling, so
    an engaged root reached after a legacy ``..`` still fences its own
    post-root alias, while destination authority is independently admitted
    by the normal root policy validation.  An engaged root retains its
    lexical suffix and stops at the first post-root alias or ``..`` so escape
    is rejected before tracker effects.  A normal nested Git root supersedes
    its parent boundary, matching Git's worktree boundary behavior.
    """

    raw_tracker = _absolute_unresolved(tracker_path)
    parts = raw_tracker.parts
    if len(parts) < 2:
        return None
    parent_components = parts[1:-1]
    leaf = parts[-1]
    spelling = Path(parts[0])
    boundary: _TrackerBoundary | None = None

    for index, component in enumerate(parent_components):
        if boundary is not None and component == "..":
            # An engaged boundary keeps this uncollapsed token in its suffix.
            # Resolving it here could choose a different sibling before
            # validation.  A legacy boundary fences nothing, so ``..`` is
            # appended to the raw spelling like any other component; stopping
            # there would hide an engaged root and its post-root alias behind
            # a legacy ``..``.  Malformed authority still fails closed.
            _context, policy = policy_for_root(boundary.root)
            if policy is not None:
                break
        spelling = spelling / component
        try:
            node = spelling.lstat()
        except FileNotFoundError:
            break
        except OSError as exc:
            raise _fail(
                "engaged_tracker_lexical_discovery_invalid",
                "cannot inspect lexical tracker parent",
            ) from exc
        if boundary is not None and stat.S_ISLNK(node.st_mode):
            # Only an engaged boundary fences a post-root alias. A legacy
            # enclosing worktree must still admit discovery of a nested root
            # beyond its pre-root alias. Malformed authority still fails closed.
            _context, policy = policy_for_root(boundary.root)
            if policy is not None:
                break
        try:
            resolved = spelling.resolve(strict=True)
        except FileNotFoundError:
            break
        except (OSError, RuntimeError, ValueError) as exc:
            raise _fail(
                "engaged_tracker_lexical_discovery_invalid",
                "cannot resolve lexical tracker parent",
            ) from exc
        if not resolved.is_dir():
            break
        root, is_git = authority._discover_project_root(resolved, explicit=False)
        if is_git:
            # A regular nested worktree supersedes its parent boundary.  The
            # suffix remains the original component stream after *this* raw
            # spelling, rather than a synthesized resolved parent plus leaf.
            boundary = _TrackerBoundary(
                root=root,
                root_spelling=spelling,
                raw_suffix=(*parent_components[index + 1 :], leaf),
            )

    return boundary


def _physical_tracker_boundary(tracker_path: Path) -> _TrackerBoundary | None:
    """Find the Git root reached after fully resolving the tracker parent."""

    try:
        physical_tracker = _absolute_unresolved(tracker_path).resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as exc:
        raise _fail(
            "engaged_tracker_lexical_discovery_invalid",
            "cannot resolve physical tracker parent",
        ) from exc
    if not physical_tracker.parent.is_dir():
        return None
    root, is_git = authority._discover_project_root(physical_tracker.parent, explicit=False)
    return (
        _TrackerBoundary(
            root=root,
            root_spelling=physical_tracker.parent,
            raw_suffix=(physical_tracker.name,),
        )
        if is_git
        else None
    )


def _tracker_boundaries(tracker_path: Path) -> tuple[_TrackerBoundary, ...]:
    lexical = _tracker_boundary_before_parent_alias(tracker_path)
    physical = _physical_tracker_boundary(tracker_path)
    ordered = tuple(boundary for boundary in (lexical, physical) if boundary is not None)
    unique: list[_TrackerBoundary] = []
    for boundary in ordered:
        if any(boundary.root == prior.root for prior in unique):
            continue
        unique.append(boundary)
    return tuple(unique)


def _binding_header_errors(lines: list[str], policy: MergeGatePolicy, context: authority.ContractContext) -> list[str]:
    values: dict[str, list[str]] = {name: [] for name in BINDING_HEADERS}
    for line in lines:
        match = _HEADER_RE.match(line.strip())
        if match and match.group("key") in values:
            values[match.group("key")].append(match.group("value").strip())
    expected = {
        "POLICY_SCHEMA": POLICY_SCHEMA,
        "POLICY_SHA256": policy.raw_sha256,
        "AUTHORITY_GENERATION": context.generation_sha256,
    }
    errors: list[str] = []
    for name in BINDING_HEADERS:
        actual = values[name]
        if len(actual) != 1:
            errors.append(f"{name} must appear exactly once")
        elif actual[0] != expected[name]:
            errors.append(f"{name} does not match the live authority binding")
    return errors


def _tracker_paths_for_context(
    context: authority.ContractContext,
    root: Path,
    tracker_path: Path | None = None,
    *,
    root_spelling: Path | None = None,
    allow_absent: bool = False,
) -> tuple[Path, Path]:
    """Inspect topology without interpreting old tracker binding headers."""

    lexical_root = _absolute_unresolved(root if root_spelling is None else root_spelling)
    selected = Path(".planveyor.merge_tracker.md") if tracker_path is None else tracker_path
    lexical_tracker = _absolute_unresolved(selected if selected.is_absolute() else lexical_root / selected)
    if not _lexically_contained(lexical_tracker, lexical_root):
        raise _fail("engaged_tracker_escape", "engaged tracker escapes the bound repository root")
    try:
        snapshot = lexical_tracker.lstat()
    except FileNotFoundError as exc:
        if not allow_absent:
            raise _fail("engaged_tracker_missing", "engaged tracker is missing") from exc
        snapshot = None
    except OSError as exc:
        raise _fail("engaged_tracker_topology_invalid", "engaged tracker cannot be inspected safely") from exc
    if snapshot is not None and (stat.S_ISLNK(snapshot.st_mode) or not stat.S_ISREG(snapshot.st_mode)):
        raise _fail("engaged_tracker_topology_invalid", "engaged tracker must be a non-symlink regular file")
    try:
        if snapshot is None:
            parent = lexical_tracker.parent.resolve(strict=True)
            if not parent.is_dir():
                raise _fail("engaged_tracker_topology_invalid", "engaged tracker parent is not a directory")
            resolved_tracker = parent / lexical_tracker.name
        else:
            resolved_tracker = lexical_tracker.resolve(strict=True)
        resolved_root = context.project_root.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise _fail("engaged_tracker_topology_invalid", "engaged tracker cannot be resolved safely") from exc
    if not _lexically_contained(resolved_tracker, resolved_root):
        raise _fail("engaged_tracker_escape", "engaged tracker resolves outside the bound repository root")
    return lexical_tracker, resolved_tracker


def validate_tracker_init_for_root(root: Path, tracker_path: Path | None = None) -> TrackerBinding | None:
    """Admit an absent/regular init destination, including a stale tracker.

    Init intentionally replaces old headers. Only the current policy and the
    destination topology are admission inputs; old tracker text is not read.
    Shell callers supply their retained context through the existing bridge.
    """

    context, policy = policy_for_root(_absolute_unresolved(root))
    if policy is None:
        return None
    assert context is not None
    lexical, resolved = _tracker_paths_for_context(context, root, tracker_path, allow_absent=True)
    return TrackerBinding(context=context, policy=policy, tracker_path=lexical, resolved_tracker_path=resolved)


def validate_tracker_for_root(
    root: Path,
    tracker_path: Path | None = None,
    *,
    root_spelling: Path | None = None,
    expected_binding: TrackerBinding | None = None,
) -> TrackerBinding | None:
    """Validate a tracker, retaining a supplied binding across reader/effect calls.

    Legacy callers return ``None`` and retain their former parser/topology
    behavior. A supplied engaged binding is revalidated, never recaptured as
    a replacement generation, even if the new generation is coherent.
    """

    policy_root = _absolute_unresolved(root)
    if expected_binding is None:
        context, policy = policy_for_root(policy_root)
    else:
        context = authority.context_for_reader(policy_root, expected_binding.context)
        policy = _policy_for_context(context)
    if policy is None:
        return None
    assert context is not None
    lexical_tracker, resolved_tracker = _tracker_paths_for_context(
        context, root, tracker_path, root_spelling=root_spelling,
    )
    if expected_binding is not None and (
        lexical_tracker != expected_binding.tracker_path
        or resolved_tracker != expected_binding.resolved_tracker_path
        or policy.raw_sha256 != expected_binding.policy.raw_sha256
    ):
        raise _fail("engaged_tracker_selection_changed", "tracker selection differs from the retained binding")
    try:
        lines = lexical_tracker.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise _fail("engaged_tracker_read_failed", "engaged tracker cannot be read") from exc
    errors = _binding_header_errors(lines, policy, context)
    if errors:
        raise _fail("engaged_tracker_binding_invalid", "; ".join(errors))
    return TrackerBinding(
        context=context, policy=policy, tracker_path=lexical_tracker,
        resolved_tracker_path=resolved_tracker,
    )


def validate_tracker_for_path(tracker_path: Path) -> TrackerBinding | None:
    binding: TrackerBinding | None = None
    for boundary in _tracker_boundaries(tracker_path):
        candidate = validate_tracker_for_root(
            boundary.root,
            boundary.tracker_path,
            root_spelling=boundary.root_spelling,
        )
        if candidate is not None:
            binding = candidate
    return binding


def _cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Finite declared Planveyor merge-gate policy reader")
    parser.add_argument("--root", default=".", help="Bound repository root")
    parser.add_argument("--tracker", default=None, help="Tracker path for validate")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("mode")
    sub.add_parser("metadata")
    sub.add_parser("step-keys")
    render = sub.add_parser("render")
    render.add_argument("--step", required=True)
    sub.add_parser("validate")
    sub.add_parser("validate-init")
    ns = parser.parse_args(argv)
    try:
        root = Path(ns.root)
        if ns.command in {"validate", "validate-init"}:
            validator = validate_tracker_for_root if ns.command == "validate" else validate_tracker_init_for_root
            binding = validator(root, Path(ns.tracker) if ns.tracker else None)
            print("legacy" if binding is None else "engaged")
            return 0
        context, policy = policy_for_root(root)
        if ns.command == "mode":
            print("legacy" if policy is None else "engaged")
        elif ns.command == "metadata":
            if policy is None:
                lines = ["STATE=legacy"]
            else:
                # ``policy_for_root`` has already revalidated this same
                # context through ``context_for_reader``.  Assemble all four
                # rows before one print so a later capture cannot mix identity
                # or leak a partial header block.
                lines = [
                    "STATE=engaged",
                    f"POLICY_SCHEMA={POLICY_SCHEMA}",
                    f"POLICY_SHA256={policy.raw_sha256}",
                    f"AUTHORITY_GENERATION={cast(authority.ContractContext, context).generation_sha256}",
                ]
            print("\n".join(lines))
        elif ns.command == "step-keys":
            if policy is None:
                raise _fail("merge_policy_legacy", "legacy callers have no policy-owned step set")
            print("\n".join(policy.step_keys))
        elif ns.command == "render":
            if policy is None:
                raise _fail("merge_policy_legacy", "legacy callers have no policy renderer")
            print(render_step(policy, ns.step))
        return 0
    except (MergeGatePolicyError, authority.ContractAuthorityError) as exc:
        code = getattr(exc, "reason_code", "merge_policy_invalid")
        print(f"merge_gate_policy: {code}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv[1:]))

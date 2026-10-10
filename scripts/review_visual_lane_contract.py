#!/usr/bin/env python3
"""Discover and materialize a declared runtime-UI visual proof lane."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import importlib
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import re
import shlex
import stat
import subprocess
import sys
import tempfile
from typing import TYPE_CHECKING, Any, Iterable, Iterator, Mapping, Sequence, TypedDict

sys.dont_write_bytecode = True
sys.pycache_prefix = os.devnull


SCRIPT_DIR = Path(__file__).resolve().parent
_script_dir_text = os.fspath(SCRIPT_DIR)
if _script_dir_text in sys.path:
    sys.path.remove(_script_dir_text)
sys.path.insert(0, _script_dir_text)


def _module_has_expected_origin(module: object, expected: Path) -> bool:
    origin = getattr(module, "__file__", None)
    if not isinstance(origin, str):
        return False
    try:
        return Path(origin).resolve(strict=True) == expected
    except (OSError, RuntimeError, ValueError):
        return False


def _scripts_package_is_local() -> bool:
    """Whether a preloaded ``scripts`` package belongs to this runtime."""

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
    if not paths or any(path != SCRIPT_DIR for path in paths):
        return False
    package_file = getattr(package, "__file__", None)
    if package_file is not None and not _module_has_expected_origin(package, SCRIPT_DIR / "__init__.py"):
        return False
    return True


def _assert_alias_origin(module: object | None, expected: Path) -> None:
    if module is not None and not _module_has_expected_origin(module, expected):
        raise ImportError("authority module has an unsafe origin")


def _authority_module() -> Any:
    """Load only the sibling authority module under both trusted spellings."""

    package_is_local = _scripts_package_is_local()
    expected = SCRIPT_DIR / "contract_authority_context.py"
    direct = sys.modules.get("contract_authority_context")
    packaged = sys.modules.get("scripts.contract_authority_context")
    _assert_alias_origin(direct, expected)
    _assert_alias_origin(packaged, expected)
    if direct is not None and packaged is not None and direct is not packaged:
        raise ImportError("authority module aliases are split")
    module = direct or packaged
    if module is None:
        module = importlib.import_module("contract_authority_context")
        _assert_alias_origin(module, expected)
    sys.modules["contract_authority_context"] = module
    if package_is_local:
        sys.modules["scripts.contract_authority_context"] = module
    return module


_authority = _authority_module()
if TYPE_CHECKING:
    from contract_authority_context import (
        ContractAuthorityError,
        ContractContext,
        context_for_reader,
        read_declared_text,
        resolve_top_level_context,
        validate_before_effect,
    )
else:
    ContractAuthorityError = _authority.ContractAuthorityError
    ContractContext = _authority.ContractContext
    context_for_reader = _authority.context_for_reader
    read_declared_text = _authority.read_declared_text
    resolve_top_level_context = _authority.resolve_top_level_context
    validate_before_effect = _authority.validate_before_effect


SCHEMA_VERSION = "review_visual_lane_contract.v1"
FULL_SCHEMA_VERSION = "review_visual_lane_contract.v2"
REF_SCHEMA_VERSION = "review_visual_lane_contract_ref.v1"
MAX_INLINE_CONTENT_LINES = 120
MAX_INLINE_UTF8_BYTES = 16_384
AVAILABILITY_STATES = ("available", "missing", "malformed", "ambiguous", "not_applicable")
CONTRACT_FIELDS = (
    "schema_version",
    "availability_state",
    "runtime_ui_kind",
    "profile_id",
    "source_refs",
    "changed_path_evidence",
    "mandatory_modes",
    "comparator_command",
    "comparator_claim",
    "baseline_update_allowed",
    "human_commands_by_mode",
    "human_index_paths_by_mode",
    "human_output_roots_by_mode",
    "complete_index_required",
    "durable_review_asset_root",
    "reason",
)
FULL_IDENTITY_FIELDS = (
    "base",
    "head",
    "exclude_docs",
    "profile",
    "plan_ref",
    "review_artifact_ref",
    "changed_path_count",
    "changed_path_evidence_sha256",
)
FULL_CONTRACT_FIELDS = CONTRACT_FIELDS + FULL_IDENTITY_FIELDS
REF_CONTRACT_FIELDS = tuple(field for field in CONTRACT_FIELDS if field != "changed_path_evidence") + FULL_IDENTITY_FIELDS + (
    "full_payload_ref",
    "full_payload_sha256",
)
SOURCE_REFS = ("docs/smoke_visual.md", "docs/testing_runbook.md")
COMPARATOR_LANES = ("visual.check_1", "visual.check_2")
HUMAN_LANE = "vis.human_visual_review_local"
JSON_BLOCK_RE = re.compile(r"```json[^\n]*\n?(?P<body>.*?)\n?```", re.DOTALL)
REVIEW_TARGET_BULLET_RE = re.compile(
    r"(?mi)^\s*-\s+Review target:\s*(?P<value>.*)$"
)
REVIEW_TARGET_RE = re.compile(
    r"^`RANGE=(?P<base>[0-9a-f]{40})\.\.(?P<head>[0-9a-f]{40}) "
    r"\(EXCLUDE_DOCS=(?P<exclude>[01])\)`$"
)
MODE_RE = re.compile(r"(?:^|\s)--mode(?:=|\s+)(?P<mode>[A-Za-z0-9_-]+)(?:\s|$)")
ASSETS_DIR_RE = re.compile(r"(?:^|\s)--assets-dir(?:=|\s+)(?P<path>[^\s`]+)")
INLINE_REPO_COMMAND_RE = re.compile(r"^\s*[-*]\s+`(?P<command>\./[^`]+)`")
UPDATE_COMMAND_RE = re.compile(r"(?:visual[-_:]?baseline|update[-_:]?snapshot|baseline[-_:]?(?:update|refresh|generation))", re.IGNORECASE)
ENV_ASSIGNMENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=.*", re.DOTALL)
DIRECT_UI_SUFFIXES = frozenset((".html", ".css", ".scss", ".sass", ".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte"))
SHELL_CONTROL_CHARS = frozenset("();<>|&")


def _stable_dicts(values: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for value in values:
        key = json.dumps(value, ensure_ascii=False, sort_keys=True)
        by_key[key] = value
    return [by_key[key] for key in sorted(by_key)]


def _inside_root(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def _is_doc_path(path: str) -> bool:
    return path.startswith("docs/") or Path(path).suffix.lower() in {".md", ".mdx", ".rst"}


def looks_runtime_ui(path: str) -> bool:
    """Return whether a changed path can alter a rendered web surface."""
    normalized = path.strip().lstrip("./")
    if not normalized or _is_doc_path(normalized):
        return False
    parts = Path(normalized).parts
    if any(part in {"templates", "static", "frontend", "ui"} for part in parts):
        return True
    return Path(normalized).suffix.lower() in DIRECT_UI_SUFFIXES


def _entry_paths(entry: Mapping[str, Any]) -> tuple[str, ...]:
    values = []
    for key in ("old_path", "path"):
        value = str(entry.get(key) or "").strip()
        if value and value not in values:
            values.append(value)
    return tuple(values)


def git_changed_entries(project_root: Path, base: str, head: str) -> list[dict[str, str]]:
    proc = subprocess.run(
        ["git", "-C", str(project_root), "diff", "--name-status", "-M", f"{base}..{head}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or f"git diff failed for {base}..{head}"
        raise RuntimeError(detail)
    entries: list[dict[str, str]] = []
    for raw_line in proc.stdout.splitlines():
        parts = raw_line.split("\t")
        if len(parts) < 2:
            continue
        status = parts[0].strip()
        if status.startswith(("R", "C")) and len(parts) >= 3:
            entries.append({"status": status, "old_path": parts[1].strip(), "path": parts[2].strip()})
        else:
            entries.append({"status": status, "path": parts[-1].strip()})
    return entries


def _changed_path_evidence(
    entries: Sequence[Mapping[str, Any]], *, exclude_docs: bool
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for entry in entries:
        paths = _entry_paths(entry)
        if exclude_docs and paths and all(_is_doc_path(path) for path in paths):
            continue
        runtime_paths = [path for path in paths if looks_runtime_ui(path)]
        evidence.append(
            {
                "status": str(entry.get("status") or "M"),
                "path": str(entry.get("path") or ""),
                "old_path": str(entry.get("old_path") or ""),
                "runtime_ui": bool(runtime_paths),
                "runtime_ui_paths": runtime_paths,
            }
        )
    return _stable_dicts(evidence)


def _command_lines(text: str) -> tuple[str, ...]:
    commands: list[str] = []
    for raw in text.splitlines():
        inline = INLINE_REPO_COMMAND_RE.match(raw)
        line = inline.group("command").strip() if inline is not None else raw.strip()
        line = line.strip("`").strip()
        line = re.sub(r"^(?:\$|>)\s+", "", line)
        assignment_prefixed = re.match(
            r"^(?:[A-Za-z_][A-Za-z0-9_]*=[^\s]+\s+)+\./",
            line,
        )
        if line.startswith("./") or assignment_prefixed is not None:
            commands.append(line)
    return tuple(dict.fromkeys(commands))


def _option_value(tokens: Sequence[str], option: str) -> str | None:
    for index, token in enumerate(tokens):
        if token == option:
            return tokens[index + 1] if index + 1 < len(tokens) else None
        if token.startswith(option + "="):
            return token.split("=", 1)[1]
    return None


def _option_values(tokens: Sequence[str], option: str) -> tuple[str, ...]:
    values: list[str] = []
    for index, token in enumerate(tokens):
        if token == option:
            if index + 1 < len(tokens):
                values.append(tokens[index + 1])
        elif token.startswith(option + "="):
            values.append(token.split("=", 1)[1])
    return tuple(values)


def _bounded_tmp_path(value: str | None) -> bool:
    if not value:
        return False
    path = Path(value)
    return value.startswith(".tmp/") and not path.is_absolute() and ".." not in path.parts


def _bounded_plan_path(value: str | None) -> bool:
    if not value:
        return False
    path = Path(value)
    return (
        value.startswith("docs/plans/")
        and value.endswith(".md")
        and not path.is_absolute()
        and ".." not in path.parts
        and not any(character in value for character in "$`*?[]{}<>~\\")
    )


def _source_commands(text: str) -> tuple[tuple[str, ...], dict[str, tuple[str, ...]]]:
    comparator: list[str] = []
    humans: dict[str, list[str]] = {}
    for command in _command_lines(text):
        try:
            tokens = shlex.split(command)
        except ValueError:
            continue
        shell_safety_error = _shell_safety_error(command)
        repeat = _option_value(tokens, "--repeat")
        logs_dir = _option_value(tokens, "--logs-dir")
        run_id = _option_value(tokens, "--run-id")
        if (
            repeat is not None
            and run_id is not None
            and logs_dir is not None
            and "--mode" not in tokens
            and not run_id.startswith("<")
            and not logs_dir.startswith("<")
            and (
                shell_safety_error is not None
                or (
                    repeat.isdigit()
                    and int(repeat) >= 2
                )
            )
        ):
            comparator.append(command)
            continue
        match = MODE_RE.search(command)
        if match is None or "--no-server" in tokens or "--profile" in tokens:
            continue
        mode = match.group("mode")
        assets_dir = _option_value(tokens, "--assets-dir")
        port = _option_value(tokens, "--port")
        plan_ref = _option_value(tokens, "--plan")
        if (
            assets_dir is None
            or plan_ref is None
            or port is None
            or (not port.isdigit() and shell_safety_error is None)
        ):
            continue
        humans.setdefault(mode, []).append(command)
    return tuple(dict.fromkeys(comparator)), {
        mode: tuple(dict.fromkeys(commands)) for mode, commands in sorted(humans.items())
    }


def _verification_marker_state(text: str) -> str:
    markers = [line for line in text.splitlines() if "verification-receipt" in line]
    if not markers:
        return "missing"
    matching = [
        line
        for line in markers
        if all(f"lane={lane}" in line for lane in (*COMPARATOR_LANES, HUMAN_LANE))
    ]
    if not matching:
        return "missing"
    return "ok" if len(matching) == 1 else "ambiguous"


def _shell_safety_error(command: str) -> str | None:
    if "\n" in command or "\r" in command:
        return "command must be a single line"
    if "`" in command or "$(" in command:
        return "command substitutions are not allowed"
    quote: str | None = None
    escaped = False
    for index, character in enumerate(command):
        if escaped:
            escaped = False
            continue
        if quote == "'":
            if character == "'":
                quote = None
            continue
        if quote == '"':
            if character == '"':
                quote = None
            elif character == "\\":
                escaped = True
            continue
        if character == "\\":
            escaped = True
        elif character in {"'", '"'}:
            quote = character
        elif character == "#" and (index == 0 or command[index - 1].isspace()):
            return "unquoted shell comments are not allowed"
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars="();<>|&")
        lexer.whitespace_split = True
        lexer.commenters = ""
        tokens = list(lexer)
    except ValueError:
        return "command is not shell-parseable"
    control_tokens = [
        token
        for token in tokens
        if token and all(character in SHELL_CONTROL_CHARS for character in token)
    ]
    if control_tokens:
        return f"shell control syntax is not allowed: {control_tokens[0]}"
    try:
        plain_tokens = shlex.split(command)
    except ValueError:
        return "command is not shell-parseable"
    if plain_tokens and ENV_ASSIGNMENT_RE.fullmatch(plain_tokens[0]):
        return "environment assignment prefixes are not allowed"
    return None


def _materialize_plan_command(command: str, *, plan_ref: str) -> str:
    return command.replace("docs/plans/<plan>.md", plan_ref, 1)


def _referenced_executable(command: str) -> str | None:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    return tokens[0] if tokens else None


def _validate_command(project_root: Path, command: str) -> str | None:
    safety_error = _shell_safety_error(command)
    if safety_error:
        return safety_error
    executable = _referenced_executable(command)
    if executable is None:
        return "command is not shell-parseable"
    path = Path(executable)
    if not executable.startswith("./") or path.is_absolute() or ".." in path.parts:
        return f"command executable must be a safe repo-relative path: {executable}"
    resolved = project_root / path
    if not _inside_root(project_root, resolved):
        return f"command executable escapes project root: {executable}"
    if not resolved.is_file():
        return f"referenced executable does not exist: {executable}"
    if not os.access(resolved, os.X_OK):
        return f"referenced executable is not executable: {executable}"
    tokens = shlex.split(command)
    path_options = {
        "--logs-dir": _bounded_tmp_path,
        "--assets-dir": _bounded_tmp_path,
        "--plan": _bounded_plan_path,
    }
    for option, validator in path_options.items():
        values = _option_values(tokens, option)
        if len(values) > 1:
            return f"duplicate path-bearing option is not allowed: {option}"
        if values and not validator(values[0]):
            return f"unsafe path-bearing option {option}: {values[0]}"
    numeric_options = {"--repeat": 2, "--port": 1}
    for option, minimum in numeric_options.items():
        values = _option_values(tokens, option)
        if len(values) > 1:
            return f"duplicate numeric option is not allowed: {option}"
        if values and (not values[0].isdigit() or int(values[0]) < minimum):
            return f"invalid numeric option {option}: {values[0]}"
    return None


def _human_output_root(command: str, *, mode: str) -> tuple[str | None, str | None]:
    match = ASSETS_DIR_RE.search(command)
    if match is None:
        return None, f"human command for mode={mode} has no --assets-dir"
    raw = match.group("path").strip()
    path = Path(raw)
    if path.is_absolute() or ".." in path.parts or not raw.startswith(".tmp/"):
        return None, f"human output root for mode={mode} must be bounded under .tmp/: {raw}"
    return path.as_posix().rstrip("/"), None


class _ContractBaseKwargs(TypedDict):
    runtime_ui_kind: str
    profile_id: str
    source_refs: Sequence[str]
    changed_path_evidence: Sequence[dict[str, Any]]
    review_basename: str


def _empty_contract(
    *,
    availability_state: str,
    runtime_ui_kind: str,
    profile_id: str,
    source_refs: Sequence[str],
    changed_path_evidence: Sequence[dict[str, Any]],
    review_basename: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "availability_state": availability_state,
        "runtime_ui_kind": runtime_ui_kind,
        "profile_id": profile_id,
        "source_refs": list(source_refs),
        "changed_path_evidence": list(changed_path_evidence),
        "mandatory_modes": [],
        "comparator_command": "",
        "comparator_claim": "mechanical",
        "baseline_update_allowed": False,
        "human_commands_by_mode": {},
        "human_index_paths_by_mode": {},
        "human_output_roots_by_mode": {},
        "complete_index_required": True,
        "durable_review_asset_root": f"docs/code_reviews/assets/{review_basename}/",
        "reason": reason,
    }


def discover_review_visual_lane(
    *,
    project_root: str | Path,
    profile_id: str,
    content_profile_id: str | None = None,
    changed_entries: Sequence[Mapping[str, Any]],
    exclude_docs: bool,
    review_basename: str,
    plan_ref: str,
    context: ContractContext | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    resolved_context = context_for_reader(root, context=context)
    if (
        resolved_context.state == "engaged"
        and profile_id != resolved_context.behavior_identity
    ):
        # Repository identity is fixed by the authority context.  The content
        # selector is deliberately separate: an engaged target always reads
        # its declared local bodies, even when its effective content selector
        # is generic.
        raise ContractAuthorityError(
            "behavior_identity_mismatch",
            "review visual profile does not match the engaged behavior identity",
        )
    effective_profile_id = content_profile_id if content_profile_id is not None else profile_id
    evidence = _changed_path_evidence(changed_entries, exclude_docs=exclude_docs)
    runtime_ui = any(bool(entry["runtime_ui"]) for entry in evidence)
    non_doc_paths = [path for entry in evidence for path in _entry_paths(entry) if not _is_doc_path(path)]
    runtime_kind = "web" if runtime_ui else "none"
    base_kwargs: _ContractBaseKwargs = {
        "runtime_ui_kind": runtime_kind,
        # This is physical/repository identity for artifact provenance. The
        # effective content selector below controls compatibility behavior.
        "profile_id": profile_id,
        "source_refs": SOURCE_REFS,
        "changed_path_evidence": evidence,
        "review_basename": review_basename,
    }
    if not runtime_ui:
        reason = "docs_only" if evidence and not non_doc_paths else "no_runtime_ui_paths"
        return _empty_contract(availability_state="not_applicable", reason=reason, **base_kwargs)
    if resolved_context.state != "engaged":
        return _empty_contract(
            availability_state="not_applicable",
            reason=f"no_declared_runtime_visual_lane:{effective_profile_id}",
            **base_kwargs,
        )

    source_texts: dict[str, str] = {}
    for source_ref in SOURCE_REFS:
        # Runtime-UI instructions are content only when a caller has supplied
        # an engaged authority context.  Legacy identity names cannot select a
        # browser lane or cause an unverified source-tree read.
        source_texts[source_ref] = read_declared_text(
            resolved_context,
            source_ref,
            purpose="review visual lane source",
        )

    marker_state = _verification_marker_state(source_texts[SOURCE_REFS[0]])
    if marker_state != "ok":
        return _empty_contract(
            availability_state=marker_state,
            reason=f"{marker_state}_verification_receipt_visual_lanes:{SOURCE_REFS[0]}",
            **base_kwargs,
        )

    parsed = {source_ref: _source_commands(text) for source_ref, text in source_texts.items()}
    for source_ref, (comparators, human_commands) in parsed.items():
        if not comparators or not human_commands:
            return _empty_contract(
                availability_state="missing",
                reason=f"missing_comparator_or_human_command:{source_ref}",
                **base_kwargs,
            )
        if len(comparators) != 1 or any(len(commands) != 1 for commands in human_commands.values()):
            return _empty_contract(
                availability_state="ambiguous",
                reason=f"ambiguous_command_family:{source_ref}",
                **base_kwargs,
            )

    smoke_comparators, smoke_humans = parsed[SOURCE_REFS[0]]
    runbook_comparators, runbook_humans = parsed[SOURCE_REFS[1]]
    smoke_human_single = {mode: commands[0] for mode, commands in smoke_humans.items()}
    runbook_human_single = {mode: commands[0] for mode, commands in runbook_humans.items()}
    if smoke_comparators[0] != runbook_comparators[0] or smoke_human_single != runbook_human_single:
        return _empty_contract(
            availability_state="ambiguous",
            reason="source_command_disagreement",
            **base_kwargs,
        )
    if not _bounded_plan_path(plan_ref):
        return _empty_contract(
            availability_state="malformed",
            reason=f"generated plan path is unsafe: {plan_ref}",
            **base_kwargs,
        )
    smoke_human_single = {
        mode: _materialize_plan_command(command, plan_ref=plan_ref)
        for mode, command in smoke_human_single.items()
    }

    comparator_command = smoke_comparators[0]
    if UPDATE_COMMAND_RE.search(comparator_command):
        return _empty_contract(
            availability_state="malformed",
            reason="baseline_update_command_cannot_be_acceptance",
            **base_kwargs,
        )
    comparator_tokens = shlex.split(comparator_command)
    if not _bounded_tmp_path(_option_value(comparator_tokens, "--logs-dir")):
        return _empty_contract(
            availability_state="malformed",
            reason="comparator --logs-dir must be bounded under .tmp/",
            **base_kwargs,
        )
    command_errors = []
    for command in (comparator_command, *smoke_human_single.values()):
        error = _validate_command(root, command)
        if error:
            command_errors.append(error)
    if command_errors:
        return _empty_contract(
            availability_state="malformed",
            reason="; ".join(command_errors),
            **base_kwargs,
        )

    output_roots: dict[str, str] = {}
    index_paths: dict[str, str] = {}
    for mode, command in sorted(smoke_human_single.items()):
        output_root, error = _human_output_root(command, mode=mode)
        if error or output_root is None:
            return _empty_contract(
                availability_state="malformed",
                reason=error or f"missing output root for mode={mode}",
                **base_kwargs,
            )
        output_roots[mode] = output_root
        index_paths[mode] = f"{output_root}/human_visual_review_{mode}.md"

    contract = _empty_contract(availability_state="available", reason="repo_backed_visual_lane", **base_kwargs)
    contract.update(
        {
            "mandatory_modes": sorted(smoke_human_single),
            "comparator_command": comparator_command,
            "human_commands_by_mode": dict(sorted(smoke_human_single.items())),
            "human_index_paths_by_mode": index_paths,
            "human_output_roots_by_mode": output_roots,
        }
    )
    return contract


def validate_contract(payload: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if set(payload) != set(CONTRACT_FIELDS):
        errors.append(
            "field_set_mismatch: expected="
            + ",".join(CONTRACT_FIELDS)
            + " actual="
            + ",".join(sorted(str(key) for key in payload))
        )
        return errors
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version_mismatch")
    state = payload.get("availability_state")
    if state not in AVAILABILITY_STATES:
        errors.append("invalid_availability_state")
    if payload.get("baseline_update_allowed") is not False:
        errors.append("baseline_update_allowed_must_be_false")
    if payload.get("comparator_claim") != "mechanical":
        errors.append("comparator_claim_must_be_mechanical")
    if payload.get("complete_index_required") is not True:
        errors.append("complete_index_required_must_be_true")
    if not _valid_changed_path_evidence(payload.get("changed_path_evidence")):
        errors.append("changed_path_evidence_malformed")
    if state == "available":
        modes = payload.get("mandatory_modes")
        human_commands = payload.get("human_commands_by_mode")
        human_indexes = payload.get("human_index_paths_by_mode")
        human_roots = payload.get("human_output_roots_by_mode")
        if not isinstance(modes, list) or not modes or len(set(modes)) != len(modes):
            errors.append("available_contract_requires_unique_modes")
        expected_modes = set(modes) if isinstance(modes, list) else set()
        for key, value in (
            ("human_commands_by_mode", human_commands),
            ("human_index_paths_by_mode", human_indexes),
            ("human_output_roots_by_mode", human_roots),
        ):
            if not isinstance(value, dict) or set(value) != expected_modes:
                errors.append(f"{key}_mode_mismatch")
        comparator = payload.get("comparator_command")
        if not isinstance(comparator, str) or not comparator.strip():
            errors.append("available_contract_requires_comparator_command")
        elif UPDATE_COMMAND_RE.search(comparator):
            errors.append("baseline_update_command_cannot_be_acceptance")
    return errors


def _valid_changed_path_evidence(value: Any) -> bool:
    """Require the generated evidence shape before any digest dereferences it."""
    if not isinstance(value, list):
        return False
    expected_fields = {"status", "path", "old_path", "runtime_ui", "runtime_ui_paths"}
    for entry in value:
        if not isinstance(entry, Mapping) or set(entry) != expected_fields:
            return False
        if any(not isinstance(entry[field], str) for field in ("status", "path", "old_path")):
            return False
        if not isinstance(entry["runtime_ui"], bool):
            return False
        runtime_ui_paths = entry["runtime_ui_paths"]
        if not isinstance(runtime_ui_paths, list) or any(
            not isinstance(path, str) for path in runtime_ui_paths
        ):
            return False
        if entry["runtime_ui"] != bool(runtime_ui_paths):
            return False
    return True


def canonical_json_bytes(value: Any) -> bytes:
    """Return the one canonical JSON encoding used by v2 and ref-v1 carriers."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def changed_path_evidence_sha256(entries: Sequence[Mapping[str, Any]]) -> str:
    """Hash the documented evidence identity, not derived UI classification."""
    if not _valid_changed_path_evidence(entries):
        raise ValueError("changed_path_evidence_malformed")
    tuples = [
        {
            "status": str(entry.get("status") or ""),
            "path": str(entry.get("path") or ""),
            "old_path": str(entry.get("old_path") or ""),
        }
        for entry in entries
    ]
    return hashlib.sha256(canonical_json_bytes(tuples)).hexdigest()


def _review_target_identity_state(text: str) -> tuple[tuple[str, str, int] | None, str | None]:
    """Read every target bullet before accepting one durable range identity."""
    matches = list(REVIEW_TARGET_BULLET_RE.finditer(text))
    if len(matches) != 1:
        return None, "review_target_identity_invalid"
    match = REVIEW_TARGET_RE.fullmatch(matches[0].group("value").strip())
    if match is None:
        return None, "review_target_identity_invalid"
    return (
        match.group("base"),
        match.group("head"),
        int(match.group("exclude")),
    ), None


def review_target_identity(text: str) -> tuple[str, str, int] | None:
    """Return the one canonical full-40 scaffold identity, if present."""
    identity, _error = _review_target_identity_state(text)
    return identity


def review_target_identity_error(text: str) -> str | None:
    """Return the stable fail-closed reason for a noncanonical target bullet set."""
    _identity, error = _review_target_identity_state(text)
    return error


def _safe_repo_relative_path(value: str) -> PurePosixPath | None:
    if not isinstance(value, str) or not value.strip() or "\\" in value:
        return None
    candidate = PurePosixPath(value)
    if candidate.is_absolute() or ".." in candidate.parts or "." in candidate.parts:
        return None
    if any(not part for part in candidate.parts):
        return None
    return candidate


def _expected_full_payload_ref(review_artifact_ref: str) -> str | None:
    review_path = _safe_repo_relative_path(review_artifact_ref)
    if review_path is None or review_path.suffix != ".md":
        return None
    if tuple(review_path.parts[:2]) not in {("docs", "code_reviews"), ("docs", "doc_reviews")}:
        return None
    return (
        review_path.parent
        / "assets"
        / review_path.stem
        / "review_visual_lane_contract.v2.json"
    ).as_posix()


def _inline_metrics(markdown: str) -> tuple[int, int]:
    match = JSON_BLOCK_RE.fullmatch(markdown.strip())
    if match is None:
        return 0, 0
    body = match.group("body")
    return len(body.splitlines()), len(body.encode("utf-8"))


def _normalized_exclude_docs(value: bool | int | str) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int) and value in {0, 1}:
        return value
    if isinstance(value, str) and value in {"0", "1"}:
        return int(value)
    raise ValueError("exclude_docs must be 0 or 1")


def _full_contract_from_v1(
    payload: Mapping[str, Any],
    *,
    base: str,
    head: str,
    exclude_docs: bool | int | str,
    plan_ref: str,
    review_artifact_ref: str,
) -> dict[str, Any]:
    errors = validate_contract(payload)
    if errors:
        raise ValueError("invalid v1 contract: " + ", ".join(errors))
    if not base.strip() or not head.strip():
        raise ValueError("base and head are required")
    if _safe_repo_relative_path(plan_ref) is None:
        raise ValueError("plan_ref must be a safe repo-relative path")
    if _expected_full_payload_ref(review_artifact_ref) is None:
        raise ValueError("review_artifact_ref must be a safe review artifact path")
    evidence = payload["changed_path_evidence"]
    if not isinstance(evidence, list):
        raise ValueError("changed_path_evidence must be a list")
    full = dict(payload)
    full.update(
        {
            "schema_version": FULL_SCHEMA_VERSION,
            "base": base,
            "head": head,
            "exclude_docs": _normalized_exclude_docs(exclude_docs),
            "profile": str(payload["profile_id"]),
            "plan_ref": plan_ref,
            "review_artifact_ref": review_artifact_ref,
            "changed_path_count": len(evidence),
            "changed_path_evidence_sha256": changed_path_evidence_sha256(evidence),
        }
    )
    return full


def _reference_from_full(
    full: Mapping[str, Any], *, full_payload_ref: str, full_payload_sha256: str
) -> dict[str, Any]:
    reference = {
        field: full[field]
        for field in REF_CONTRACT_FIELDS
        if field not in {"full_payload_ref", "full_payload_sha256"}
    }
    reference["schema_version"] = REF_SCHEMA_VERSION
    reference["full_payload_ref"] = full_payload_ref
    reference["full_payload_sha256"] = full_payload_sha256
    return reference


def _effective_v1_from_full(full: Mapping[str, Any]) -> dict[str, Any]:
    payload = {field: full[field] for field in CONTRACT_FIELDS}
    payload["schema_version"] = SCHEMA_VERSION
    return payload


def validate_full_contract(full: Mapping[str, Any]) -> list[str]:
    if set(full) != set(FULL_CONTRACT_FIELDS):
        return ["identity_mismatch"]
    if full.get("schema_version") != FULL_SCHEMA_VERSION:
        return ["identity_mismatch"]
    try:
        payload = _effective_v1_from_full(full)
    except KeyError:
        return ["identity_mismatch"]
    errors = validate_contract(payload)
    if errors:
        if errors == ["changed_path_evidence_malformed"]:
            return errors
        return ["identity_mismatch"]
    if not isinstance(full.get("base"), str) or not str(full["base"]).strip():
        return ["identity_mismatch"]
    if not isinstance(full.get("head"), str) or not str(full["head"]).strip():
        return ["identity_mismatch"]
    if full.get("exclude_docs") not in {0, 1}:
        return ["identity_mismatch"]
    if full.get("profile") != full.get("profile_id"):
        return ["identity_mismatch"]
    if _safe_repo_relative_path(str(full.get("plan_ref") or "")) is None:
        return ["identity_mismatch"]
    if _expected_full_payload_ref(str(full.get("review_artifact_ref") or "")) is None:
        return ["identity_mismatch"]
    evidence = full.get("changed_path_evidence")
    if not isinstance(evidence, list):
        return ["changed_path_count_mismatch"]
    if full.get("changed_path_count") != len(evidence):
        return ["changed_path_count_mismatch"]
    if full.get("changed_path_evidence_sha256") != changed_path_evidence_sha256(evidence):
        return ["changed_path_digest_mismatch"]
    return []


def _validate_reference(reference: Mapping[str, Any]) -> list[str]:
    if set(reference) != set(REF_CONTRACT_FIELDS):
        return ["ref_missing"]
    if reference.get("schema_version") != REF_SCHEMA_VERSION:
        return ["ref_missing"]
    if _safe_repo_relative_path(str(reference.get("full_payload_ref") or "")) is None:
        return ["ref_unsafe"]
    digest = reference.get("full_payload_sha256")
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        return ["ref_missing"]
    if not isinstance(reference.get("changed_path_count"), int) or reference["changed_path_count"] < 0:
        return ["changed_path_count_mismatch"]
    for key in ("base", "head", "profile", "plan_ref", "review_artifact_ref", "changed_path_evidence_sha256"):
        if not isinstance(reference.get(key), str) or not str(reference[key]).strip():
            return ["identity_mismatch"]
    if reference.get("exclude_docs") not in {0, 1}:
        return ["identity_mismatch"]
    if _safe_repo_relative_path(str(reference["plan_ref"])) is None:
        return ["identity_mismatch"]
    expected_support_ref = _expected_full_payload_ref(str(reference["review_artifact_ref"]))
    if expected_support_ref is None or reference["full_payload_ref"] != expected_support_ref:
        return ["identity_mismatch"]
    return []


def render_materialized_contract(payload: Mapping[str, Any]) -> str:
    """Render a bounded inline carrier for legacy/v1 callers."""
    if payload.get("schema_version") == REF_SCHEMA_VERSION:
        wrapper = {"review_visual_lane_contract_ref": dict(payload)}
    else:
        wrapper = {"review_visual_lane_contract": dict(payload)}
    return "```json\n" + json.dumps(
        wrapper,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n```"


def prepare_materialized_contract(
    payload: Mapping[str, Any],
    *,
    base: str,
    head: str,
    exclude_docs: bool | int | str,
    plan_ref: str,
    review_artifact_ref: str,
) -> dict[str, Any]:
    """Choose the inline-v1 or external-v2/ref-v1 physical carrier once."""
    contract = dict(payload)
    errors = validate_contract(contract)
    if errors:
        raise ValueError("invalid v1 contract: " + ", ".join(errors))
    inline_markdown = render_materialized_contract(contract)
    inline_lines, inline_bytes = _inline_metrics(inline_markdown)
    base_materialization = {
        "contract": contract,
        "base": base,
        "head": head,
        "exclude_docs": _normalized_exclude_docs(exclude_docs),
        "plan_ref": plan_ref,
        "review_artifact_ref": review_artifact_ref,
    }
    if inline_lines <= MAX_INLINE_CONTENT_LINES and inline_bytes <= MAX_INLINE_UTF8_BYTES:
        return {
            **base_materialization,
            "mode": "inline",
            "markdown": inline_markdown,
            "support_ref": "",
            "support_sha256": "",
        }

    full = _full_contract_from_v1(
        contract,
        base=base,
        head=head,
        exclude_docs=exclude_docs,
        plan_ref=plan_ref,
        review_artifact_ref=review_artifact_ref,
    )
    support_ref = _expected_full_payload_ref(review_artifact_ref)
    assert support_ref is not None
    full_bytes = canonical_json_bytes(full)
    full_sha256 = hashlib.sha256(full_bytes).hexdigest()
    reference = _reference_from_full(
        full,
        full_payload_ref=support_ref,
        full_payload_sha256=full_sha256,
    )
    return {
        **base_materialization,
        "mode": "external",
        "markdown": render_materialized_contract(reference),
        "support_ref": support_ref,
        "support_sha256": full_sha256,
    }


def _path_has_symlink(root: Path, candidate: Path) -> bool:
    try:
        relative = candidate.relative_to(root)
    except ValueError:
        return True
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _safe_external_path(root: Path, raw_ref: str) -> tuple[Path | None, str | None]:
    rel = _safe_repo_relative_path(raw_ref)
    if rel is None:
        return None, "ref_unsafe"
    candidate = root.joinpath(*rel.parts)
    if _path_has_symlink(root, candidate):
        return None, "ref_unsafe"
    try:
        candidate.resolve(strict=False).relative_to(root.resolve())
    except (OSError, ValueError):
        return None, "ref_unsafe"
    return candidate, None


def _resolve_reference(
    reference: Mapping[str, Any],
    *,
    project_root: str | Path | None,
    expected_plan_ref: str | None,
    expected_range_identity: tuple[str, str, int] | None,
) -> tuple[dict[str, Any] | None, list[str]]:
    reference_errors = _validate_reference(reference)
    if reference_errors:
        return None, reference_errors
    if project_root is None:
        return None, ["full_payload_missing"]
    root = Path(project_root).resolve()
    support_ref = str(reference["full_payload_ref"])
    support_path, safety_error = _safe_external_path(root, support_ref)
    if safety_error:
        return None, [safety_error]
    assert support_path is not None
    if not support_path.exists():
        return None, ["full_payload_missing"]
    try:
        mode = support_path.stat().st_mode
    except OSError:
        return None, ["full_payload_missing"]
    if not stat.S_ISREG(mode) or support_path.is_symlink():
        return None, ["ref_unsafe"]
    try:
        raw_bytes = support_path.read_bytes()
        full = json.loads(raw_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None, ["full_payload_missing"]
    if not isinstance(full, dict):
        return None, ["full_payload_missing"]
    canonical = canonical_json_bytes(full)
    actual_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    if raw_bytes != canonical or actual_sha256 != reference["full_payload_sha256"]:
        return None, ["full_payload_sha256_mismatch"]
    full_errors = validate_full_contract(full)
    if full_errors:
        return None, full_errors
    expected_support_ref = _expected_full_payload_ref(str(full["review_artifact_ref"]))
    if expected_support_ref != support_ref:
        return None, ["identity_mismatch"]
    if expected_plan_ref is not None and full["plan_ref"] != expected_plan_ref:
        return None, ["identity_mismatch"]
    if expected_range_identity is not None and (
        full["base"],
        full["head"],
        full["exclude_docs"],
    ) != expected_range_identity:
        return None, ["identity_mismatch"]
    if full["changed_path_count"] != reference["changed_path_count"]:
        return None, ["changed_path_count_mismatch"]
    if full["changed_path_evidence_sha256"] != reference["changed_path_evidence_sha256"]:
        return None, ["changed_path_digest_mismatch"]
    if any(full[field] != reference[field] for field in FULL_IDENTITY_FIELDS):
        return None, ["identity_mismatch"]
    expected_reference = _reference_from_full(
        full,
        full_payload_ref=support_ref,
        full_payload_sha256=actual_sha256,
    )
    if dict(reference) != expected_reference:
        return None, ["projection_mismatch"]
    payload = _effective_v1_from_full(full)
    contract_errors = validate_contract(payload)
    return (payload, contract_errors) if contract_errors else (payload, [])


def parse_materialized_contract(
    text: str,
    *,
    project_root: str | Path | None = None,
    expected_plan_ref: str | None = None,
    expected_range_identity: tuple[str, str, int] | None = None,
    require_review_target_identity: bool = False,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Read exactly one inline-v1 or ref-v1 carrier into the effective v1 contract."""
    matches: list[tuple[str, dict[str, Any], str]] = []
    malformed = False
    for match in JSON_BLOCK_RE.finditer(text):
        body = match.group("body")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, dict):
            continue
        keys = set(parsed)
        if keys == {"review_visual_lane_contract"}:
            payload = parsed["review_visual_lane_contract"]
            if not isinstance(payload, dict):
                malformed = True
                continue
            matches.append(("inline", payload, body))
        elif keys == {"review_visual_lane_contract_ref"}:
            payload = parsed["review_visual_lane_contract_ref"]
            if not isinstance(payload, dict):
                malformed = True
                continue
            matches.append(("ref", payload, body))
        elif "review_visual_lane_contract" in parsed or "review_visual_lane_contract_ref" in parsed:
            malformed = True
    if len(matches) > 1:
        return None, ["multiple_materialized_visual_lane_contracts"]
    if not matches:
        return None, ["malformed_materialized_visual_lane_contract" if malformed else "missing_materialized_visual_lane_contract"]
    kind, payload, body = matches[0]
    if kind == "inline":
        lines = len(body.splitlines())
        byte_count = len(body.encode("utf-8"))
        if lines > MAX_INLINE_CONTENT_LINES:
            return None, ["inline_content_line_limit_exceeded"]
        if byte_count > MAX_INLINE_UTF8_BYTES:
            return None, ["inline_content_byte_limit_exceeded"]
        return payload, validate_contract(payload)
    if require_review_target_identity:
        literal_identity, literal_error = _review_target_identity_state(text)
        if literal_error:
            return None, [literal_error]
        assert literal_identity is not None
        if expected_range_identity is not None and expected_range_identity != literal_identity:
            return None, ["identity_mismatch"]
        expected_range_identity = literal_identity
    return _resolve_reference(
        payload,
        project_root=project_root,
        expected_plan_ref=expected_plan_ref,
        expected_range_identity=expected_range_identity,
    )


def referenced_full_payload_refs(text: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return literal refs only; callers must never discover an asset directory by glob."""
    refs: list[str] = []
    errors: list[str] = []
    for match in JSON_BLOCK_RE.finditer(text):
        try:
            parsed = json.loads(match.group("body"))
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, dict) or set(parsed) != {"review_visual_lane_contract_ref"}:
            continue
        reference = parsed["review_visual_lane_contract_ref"]
        if not isinstance(reference, dict):
            errors.append("ref_missing")
            continue
        reference_errors = _validate_reference(reference)
        if reference_errors:
            errors.extend(reference_errors)
            continue
        refs.append(str(reference["full_payload_ref"]))
    return tuple(dict.fromkeys(refs)), tuple(dict.fromkeys(errors))


class PublicationError(RuntimeError):
    """A fail-closed publication error whose text is a contract reason code."""


def _repo_output_path(root: Path, raw_path: str) -> Path:
    candidate, error = _safe_external_path(root, raw_path)
    if error or candidate is None:
        raise PublicationError("ref_unsafe")
    return candidate


def _atomic_write(path: Path, payload: bytes, *, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    temporary_path = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, mode)
        os.replace(temporary_path, path)
    except Exception:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _scaffold_publication_lock_path(root: Path) -> Path:
    lock_root = root / ".tmp" / "review_visual_lane_contract_locks"
    if _path_has_symlink(root, lock_root):
        raise PublicationError("ref_unsafe")
    try:
        lock_root.mkdir(parents=True, mode=0o700, exist_ok=True)
    except OSError as exc:
        raise PublicationError("ref_unsafe") from exc
    if _path_has_symlink(root, lock_root):
        raise PublicationError("ref_unsafe")
    try:
        if not stat.S_ISDIR(lock_root.stat().st_mode):
            raise PublicationError("ref_unsafe")
    except OSError as exc:
        raise PublicationError("ref_unsafe") from exc
    return lock_root / "publication.lock"


@contextmanager
def _scaffold_publication_lock(root: Path) -> Iterator[None]:
    """Serialize every generated scaffold publication in one checkout."""
    lock_path = _scaffold_publication_lock_path(root)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    old_umask = os.umask(0o077)
    fd = -1
    try:
        try:
            fd = os.open(lock_path, flags, 0o600)
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise PublicationError("ref_unsafe")
            os.fchmod(fd, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX)
        except PublicationError:
            raise
        except OSError as exc:
            raise PublicationError("ref_unsafe") from exc
        yield
    finally:
        if fd >= 0:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
        os.umask(old_umask)


def _json_object_without_duplicate_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    decoded: dict[str, Any] = {}
    for key, value in pairs:
        if key in decoded:
            raise ValueError("duplicate JSON object key")
        decoded[key] = value
    return decoded


def _declared_ref_v1_from_preimage(preimage: bytes) -> tuple[str, dict[str, Any]] | None:
    try:
        text = preimage.decode("utf-8")
    except UnicodeDecodeError as exc:
        if b"review_visual_lane_contract_ref" in preimage:
            raise PublicationError("publication_conflict") from exc
        return None
    references: list[dict[str, Any]] = []
    has_inline_carrier = False
    for match in JSON_BLOCK_RE.finditer(text):
        body = match.group("body")
        try:
            wrapper = json.loads(body)
        except json.JSONDecodeError as exc:
            if '"review_visual_lane_contract_ref"' in body:
                raise PublicationError("publication_conflict") from exc
            continue
        if not isinstance(wrapper, dict):
            continue
        if "review_visual_lane_contract_ref" in wrapper:
            try:
                strict_wrapper = json.loads(
                    body,
                    object_pairs_hook=_json_object_without_duplicate_keys,
                )
            except ValueError as exc:
                raise PublicationError("publication_conflict") from exc
            if not isinstance(strict_wrapper, dict):
                raise PublicationError("publication_conflict")
            wrapper = strict_wrapper
        if "review_visual_lane_contract" in wrapper:
            has_inline_carrier = True
        if "review_visual_lane_contract_ref" not in wrapper:
            continue
        if set(wrapper) != {"review_visual_lane_contract_ref"}:
            raise PublicationError("publication_conflict")
        reference = wrapper["review_visual_lane_contract_ref"]
        if not isinstance(reference, dict):
            raise PublicationError("publication_conflict")
        try:
            reference_errors = _validate_reference(reference)
        except (KeyError, TypeError, ValueError) as exc:
            raise PublicationError("publication_conflict") from exc
        if reference_errors:
            raise PublicationError("publication_conflict")
        references.append(dict(reference))
    if len(references) > 1 or (references and has_inline_carrier):
        raise PublicationError("publication_conflict")
    return (text, references[0]) if references else None


def _assert_inline_replacement_authority(
    *,
    root: Path,
    prepared: Mapping[str, Any],
    preimages: Mapping[Path, tuple[bool, bytes, int]],
    plan_path: Path,
    draft_path: Path,
) -> None:
    declared: list[tuple[str, dict[str, Any]]] = []
    for path in (plan_path, draft_path):
        existed, preimage, _mode = preimages[path]
        if not existed:
            continue
        carrier = _declared_ref_v1_from_preimage(preimage)
        if carrier is not None:
            declared.append(carrier)
    if not declared:
        return
    old_text, old_reference = declared[0]
    if any(reference != old_reference for _text, reference in declared[1:]):
        raise PublicationError("publication_conflict")
    try:
        _old_payload, errors = parse_materialized_contract(
            old_text,
            project_root=root,
            expected_plan_ref=str(prepared["plan_ref"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise PublicationError("publication_conflict") from exc
    if errors:
        raise PublicationError("publication_conflict")
    try:
        requested_full = _full_contract_from_v1(
            prepared["contract"],
            base=str(prepared["base"]),
            head=str(prepared["head"]),
            exclude_docs=prepared["exclude_docs"],
            plan_ref=str(prepared["plan_ref"]),
            review_artifact_ref=str(prepared["review_artifact_ref"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise PublicationError("publication_conflict") from exc
    if any(
        old_reference[field] != requested_full[field]
        for field in FULL_IDENTITY_FIELDS
    ):
        raise PublicationError("publication_conflict")


def publish_generated_scaffold(
    *,
    project_root: str | Path,
    plan_ref: str,
    plan_text: str,
    draft_ref: str,
    draft_text: str,
    materialization: Mapping[str, Any],
    inject_failure_after: str | None = None,
    context: ContractContext | None = None,
) -> None:
    """Publish support/plan/draft with rollback and no support-carrier overwrite."""
    root = Path(project_root).resolve()
    resolved_context = context_for_reader(root, context=context)
    # This function creates a checkout-local lock and can replace several
    # files.  Validate the captured generation before inspecting or creating
    # any publication path.
    validate_before_effect(resolved_context)
    try:
        prepared = prepare_materialized_contract(
            materialization["contract"],
            base=str(materialization["base"]),
            head=str(materialization["head"]),
            exclude_docs=materialization["exclude_docs"],
            plan_ref=str(materialization["plan_ref"]),
            review_artifact_ref=str(materialization["review_artifact_ref"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise PublicationError("identity_mismatch") from exc
    if str(prepared["markdown"]) not in plan_text or str(prepared["markdown"]) not in draft_text:
        raise PublicationError("projection_mismatch")
    if plan_ref != prepared["plan_ref"]:
        raise PublicationError("identity_mismatch")

    destinations: list[tuple[str, Path, bytes]] = []
    if prepared["mode"] == "external":
        support_ref = str(prepared["support_ref"])
        full = _full_contract_from_v1(
            prepared["contract"],
            base=str(prepared["base"]),
            head=str(prepared["head"]),
            exclude_docs=prepared["exclude_docs"],
            plan_ref=str(prepared["plan_ref"]),
            review_artifact_ref=str(prepared["review_artifact_ref"]),
        )
        support_bytes = canonical_json_bytes(full)
        if hashlib.sha256(support_bytes).hexdigest() != prepared["support_sha256"]:
            raise PublicationError("full_payload_sha256_mismatch")
        destinations.append(("support", _repo_output_path(root, support_ref), support_bytes))
    destinations.extend(
        [
            ("plan", _repo_output_path(root, plan_ref), plan_text.encode("utf-8")),
            ("draft", _repo_output_path(root, draft_ref), draft_text.encode("utf-8")),
        ]
    )

    destination_paths = {label: path for label, path, _payload in destinations}

    # Hold the fixed checkout-scoped lock from preimage inspection through
    # rollback. Per-file atomic replaces alone cannot make this triple atomic.
    with _scaffold_publication_lock(root):
        preimages: dict[Path, tuple[bool, bytes, int]] = {}
        for label, path, payload in destinations:
            if path.exists():
                if path.is_symlink() or not path.is_file():
                    raise PublicationError("ref_unsafe")
                try:
                    existing = path.read_bytes()
                    mode = stat.S_IMODE(path.stat().st_mode)
                except OSError as exc:
                    raise PublicationError("ref_unsafe") from exc
                if label == "support" and existing != payload:
                    raise PublicationError("publication_conflict")
                preimages[path] = (True, existing, mode)
            else:
                preimages[path] = (False, b"", 0o644)

        if prepared["mode"] == "inline":
            _assert_inline_replacement_authority(
                root=root,
                prepared=prepared,
                preimages=preimages,
                plan_path=destination_paths["plan"],
                draft_path=destination_paths["draft"],
            )

        # A repeated identical large-range invocation must not churn the generated
        # plan/draft merely because their human timestamp/port prose would be
        # regenerated.  The full support bytes are the identity; both derived refs
        # must resolve to the same effective contract before this no-write reuse.
        if prepared["mode"] == "external":
            expected_range_identity = (
                str(prepared["base"]),
                str(prepared["head"]),
                int(prepared["exclude_docs"]),
            )
            plan_path = _repo_output_path(root, plan_ref)
            draft_path = _repo_output_path(root, draft_ref)
            support_path = _repo_output_path(root, str(prepared["support_ref"]))
            if plan_path.is_file() and draft_path.is_file() and support_path.is_file():
                try:
                    existing_plan, plan_errors = parse_materialized_contract(
                        plan_path.read_text(encoding="utf-8"),
                        project_root=root,
                        expected_plan_ref=plan_ref,
                        expected_range_identity=expected_range_identity,
                        require_review_target_identity=True,
                    )
                    existing_draft, draft_errors = parse_materialized_contract(
                        draft_path.read_text(encoding="utf-8"),
                        project_root=root,
                        expected_plan_ref=plan_ref,
                        expected_range_identity=expected_range_identity,
                        require_review_target_identity=True,
                    )
                except OSError:
                    existing_plan, plan_errors = None, ["full_payload_missing"]
                    existing_draft, draft_errors = None, ["full_payload_missing"]
                if (
                    not plan_errors
                    and not draft_errors
                    and existing_plan == prepared["contract"]
                    and existing_draft == prepared["contract"]
                ):
                    return

        changed: list[tuple[Path, bytes]] = []
        try:
            for label, path, payload in destinations:
                existed, existing, mode = preimages[path]
                if existed and existing == payload:
                    continue
                _atomic_write(path, payload, mode=mode)
                changed.append((path, payload))
                if inject_failure_after == label:
                    raise OSError(f"injected publication failure after {label}")
        except Exception as exc:
            rollback_error = False
            for path, written_payload in reversed(changed):
                existed, payload, mode = preimages[path]
                try:
                    if path.is_symlink() or not path.is_file() or path.read_bytes() != written_payload:
                        rollback_error = True
                        continue
                    if existed:
                        _atomic_write(path, payload, mode=mode)
                    else:
                        path.unlink()
                except OSError:
                    rollback_error = True
            if rollback_error:
                raise PublicationError("publication_rollback_failed") from exc
            raise PublicationError(
                "publication_rollback_failed" if isinstance(exc, PublicationError) else "publication_conflict"
            ) from exc


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--profile-id", default="default")
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--exclude-docs", choices=("0", "1"), default="1")
    parser.add_argument("--review-artifact", required=True)
    parser.add_argument("--plan-artifact", required=True)
    parser.add_argument("--render-markdown", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(args.project_root).resolve()
    try:
        context = resolve_top_level_context(root)
        entries = git_changed_entries(root, args.base, args.head)
        payload = discover_review_visual_lane(
            project_root=root,
            profile_id=args.profile_id,
            changed_entries=entries,
            exclude_docs=args.exclude_docs == "1",
            review_basename=Path(args.review_artifact).stem,
            plan_ref=args.plan_artifact,
            context=context,
        )
    except (OSError, RuntimeError, ContractAuthorityError) as exc:
        print(f"review-visual-lane-contract: {exc}", file=sys.stderr)
        return 2
    errors = validate_contract(payload)
    if errors:
        print("review-visual-lane-contract: " + "; ".join(errors), file=sys.stderr)
        return 2
    if args.render_markdown:
        try:
            materialization = prepare_materialized_contract(
                payload,
                base=args.base,
                head=args.head,
                exclude_docs=args.exclude_docs,
                plan_ref=args.plan_artifact,
                review_artifact_ref=args.review_artifact,
            )
        except ValueError as exc:
            print(f"review-visual-lane-contract: {exc}", file=sys.stderr)
            return 2
        if materialization["mode"] != "inline":
            print(
                "review-visual-lane-contract: external materialization requires canonical scaffold publication",
                file=sys.stderr,
            )
            return 2
        print(materialization["markdown"])
    else:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

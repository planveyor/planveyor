#!/usr/bin/env python3
"""Emit or independently verify a pinned static authority-edge inventory.

This module reads only Git objects selected by explicit roots, commits, and
commit-tree identifiers.  It never imports repository code, reads repository
working-tree content, writes files, or invokes a runtime resolver.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable


RULES_SCHEMA_VERSION = "planveyor.contract_authority_matrix.rules.v1"
INVENTORY_SCHEMA_VERSION = "planveyor.contract_authority_matrix.inventory.v1"
CHECK_SCHEMA_VERSION = "planveyor.contract_authority_matrix.check.v1"
RESULT_SCHEMA_VERSION = "planveyor.contract_authority_matrix.result.v1"
FULL_OID_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
PHASE_CASE_RE = re.compile(
    r'^\s*([a-z_]+:[a-z_]+(?:\|[a-z_]+:[a-z_]+)*)\)\s+echo\s+"([^"]+)"\s+;;\s*$',
    re.MULTILINE,
)
PHASE_FILENAME_RE = re.compile(r"^[a-z][a-z0-9_]*\.md$")
DECISION_STATES = frozenset({"decided", "pending_owner", "unresolved_research"})
IMPLEMENTATION_EVIDENCE_STATES = frozenset({"unfulfilled", "not_applicable"})
DISPOSITION_KINDS = frozenset(
    {
        "retain_runtime",
        "retain_target",
        "keep_target",
        "copy_to_target",
        "planned_extraction",
        "localize_to_target",
        "split_policy_runtime",
        "not_applicable",
    }
)
SELECTOR_KINDS = frozenset(
    {
        "ast_tuple",
        "role_phase_map",
        "profile_file_tree",
        "direct_literal_reference_hits",
        "target_surface_tree",
    }
)


class MatrixError(RuntimeError):
    """A bounded input, Git-object fact, or inventory assertion failed."""


class UsageError(MatrixError):
    """The caller did not supply the explicit bounded invocation inputs."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def canonical_key(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _reject_duplicate_object_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise MatrixError(f"duplicate JSON key: {key!r}")
        value[key] = item
    return value


def _reject_json_constant(token: str) -> None:
    raise MatrixError(f"unsupported JSON constant: {token}")


def _require_utf8_json_strings(value: Any) -> None:
    """Reject escaped surrogate code points before they reach output or errors."""

    if isinstance(value, str):
        try:
            value.encode("utf-8", "strict")
        except UnicodeEncodeError as exc:
            raise MatrixError("JSON contains a non-UTF-8 string") from exc
    elif isinstance(value, list):
        for item in value:
            _require_utf8_json_strings(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            _require_utf8_json_strings(key)
            _require_utf8_json_strings(item)


def strict_json_loads(data: bytes, *, label: str) -> Any:
    try:
        value = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_object_keys,
            parse_constant=_reject_json_constant,
        )
        _require_utf8_json_strings(value)
        return value
    except (UnicodeDecodeError, json.JSONDecodeError, MatrixError, ValueError, RecursionError) as exc:
        raise MatrixError(f"{label} is not strict UTF-8 JSON: {exc}") from exc


def require_object(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MatrixError(f"{label} must be an object")
    return value


def require_list(value: Any, *, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise MatrixError(f"{label} must be a list")
    return value


def require_string(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise MatrixError(f"{label} must be a nonempty string")
    return value


def require_bool(value: Any, *, label: str) -> bool:
    if not isinstance(value, bool):
        raise MatrixError(f"{label} must be a boolean")
    return value


def reject_unknown_keys(value: dict[str, Any], allowed: Iterable[str], *, label: str) -> None:
    unknown = sorted(set(value) - set(allowed))
    if unknown:
        raise MatrixError(f"{label} has unknown key(s): {', '.join(unknown)}")


def require_full_oid(value: Any, *, label: str) -> str:
    oid = require_string(value, label=label)
    if not FULL_OID_RE.fullmatch(oid):
        raise UsageError(f"{label} must be a full 40- or 64-hex object identifier")
    return oid


def require_absolute_root(value: Any, *, label: str) -> Path:
    raw = require_string(value, label=label)
    path = Path(raw)
    if not path.is_absolute():
        raise UsageError(f"{label} must be absolute")
    return path


def require_repo_path(value: Any, *, label: str) -> str:
    path = require_string(value, label=label)
    try:
        path.encode("utf-8", "strict")
    except UnicodeEncodeError as exc:
        raise MatrixError(f"{label} is not UTF-8 encodable") from exc
    if "\x00" in path or any(ord(character) < 32 for character in path):
        raise MatrixError(f"{label} contains a control character")
    if path.startswith("/") or any(part in ("", ".", "..", ".git") for part in path.split("/")):
        raise MatrixError(f"{label} is not a canonical repository-relative path: {path!r}")
    pure = PurePosixPath(path)
    if pure.is_absolute() or path != pure.as_posix():
        raise MatrixError(f"{label} is not a canonical repository-relative path: {path!r}")
    return path


def object_fact(path: str | None, *, state: str, mode: str | None = None, blob_oid: str | None = None, sha256: str | None = None) -> dict[str, Any]:
    return {"path": path, "state": state, "mode": mode, "blob_oid": blob_oid, "sha256": sha256}


def safe_git_environment() -> dict[str, str]:
    """Build a whitelist; inherited Git configuration/object routing is ignored."""

    env = {
        "PATH": os.environ.get("PATH", os.defpath),
        "LC_ALL": "C",
        "LANG": "C",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_PAGER": "cat",
    }
    # Do not inherit any GIT_* variable, including object, alternate-object,
    # config, exec-path, and discovery-routing variables.
    return env


class GitObjectReader:
    """Read named Git objects without inspecting repository working state."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._env = safe_git_environment()

    def run(self, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[bytes]:
        result = subprocess.run(
            [
                "git",
                "--no-optional-locks",
                "--literal-pathspecs",
                "-c",
                "core.fsmonitor=false",
                "-C",
                os.fspath(self.root),
                *args,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env=self._env,
            cwd=os.fspath(Path("/")),
        )
        if check and result.returncode != 0:
            detail = result.stderr.decode("utf-8", "replace").strip()
            raise MatrixError(f"Git object read failed ({result.returncode}): {detail}")
        return result

    def text(self, args: list[str]) -> str:
        return self.run(args).stdout.decode("utf-8", "strict").strip()

    def verify_commit_tree(self, commit: str, tree: str, *, label: str) -> None:
        if self.text(["rev-parse", f"{commit}^{{commit}}"] ) != commit:
            raise MatrixError(f"{label} commit did not resolve exactly")
        if self.text(["rev-parse", f"{commit}^{{tree}}"] ) != tree:
            raise MatrixError(f"{label} commit tree differs from supplied tree")

    def blob(self, oid: str) -> bytes:
        return self.run(["cat-file", "blob", oid]).stdout

    @staticmethod
    def _parse_tree_record(raw: bytes, *, label: str) -> tuple[str, str, str, str]:
        try:
            head, path_bytes = raw.split(b"\t", 1)
            mode, object_type, oid = head.decode("ascii").split(" ")
            path = path_bytes.decode("utf-8", "surrogateescape")
        except ValueError as exc:
            raise MatrixError(f"malformed Git tree record for {label}") from exc
        return mode, object_type, oid, path

    def entry(self, commit: str, path: str | None) -> dict[str, Any]:
        if path is None:
            return object_fact(None, state="not_applicable")
        safe_path = require_repo_path(path, label="Git entry path")
        records = [item for item in self.run(["ls-tree", "-z", commit, "--", safe_path]).stdout.split(b"\0") if item]
        if not records:
            return object_fact(safe_path, state="absent")
        if len(records) != 1:
            raise MatrixError(f"Git entry lookup returned multiple records for {safe_path}")
        mode, object_type, oid, actual_path = self._parse_tree_record(records[0], label=safe_path)
        if actual_path != safe_path or object_type != "blob":
            raise MatrixError(f"Git entry is not one blob for {safe_path}")
        if mode not in {"100644", "100755"}:
            raise MatrixError(f"Git entry is not a regular file for {safe_path}")
        data = self.blob(oid)
        return object_fact(safe_path, state="present", mode=mode, blob_oid=oid, sha256=sha256_bytes(data))

    def text_file(self, commit: str, path: str) -> tuple[dict[str, Any], str]:
        fact = self.entry(commit, path)
        if fact["state"] != "present":
            raise MatrixError(f"required pinned source object is absent: {path}")
        if fact["mode"] not in {"100644", "100755"}:
            raise MatrixError(f"required pinned source object is not a regular file: {path}")
        return fact, self.blob(str(fact["blob_oid"])).decode("utf-8", "strict")

    def tree_entries(self, commit: str, prefixes: list[str]) -> list[dict[str, Any]]:
        entries: dict[str, dict[str, Any]] = {}
        for prefix in prefixes:
            safe_prefix = require_repo_path(prefix, label="tree prefix")
            records = [item for item in self.run(["ls-tree", "-r", "-z", commit, "--", safe_prefix]).stdout.split(b"\0") if item]
            for raw in records:
                mode, object_type, oid, path = self._parse_tree_record(raw, label=safe_prefix)
                safe_path = require_repo_path(path, label="tree entry path")
                if safe_path != safe_prefix and not safe_path.startswith(safe_prefix + "/"):
                    raise MatrixError("Git tree entry is outside its declared prefix")
                if object_type != "blob" or mode not in {"100644", "100755"}:
                    raise MatrixError(f"declared tree surface contains unsupported non-regular entry: {safe_path}")
                if safe_path in entries:
                    continue
                data = self.blob(oid)
                entries[safe_path] = object_fact(safe_path, state="present", mode=mode, blob_oid=oid, sha256=sha256_bytes(data))
        return [entries[path] for path in sorted(entries)]

    def literal_hits(self, commit: str, paths: list[str], literal: str) -> list[dict[str, Any]]:
        if not literal:
            raise MatrixError("literal selector must not use an empty literal")
        hits: list[dict[str, Any]] = []
        for path in sorted(set(paths)):
            fact, text = self.text_file(commit, path)
            for line_number, line in enumerate(text.splitlines(), start=1):
                if literal in line:
                    hits.append(
                        {
                            "path": path,
                            "line": line_number,
                            "literal": literal,
                            "line_sha256": sha256_bytes(line.encode("utf-8")),
                            "object": fact,
                        }
                    )
        return hits


@dataclass(frozen=True)
class ExpectedEdge:
    identity: dict[str, str]
    selector_id: str
    selector_kind: str
    consumer_repository: str
    consumer_path: str | None
    consumer_anchor_detail: dict[str, Any]
    source_surface_path: str | None
    target_surface_path: str | None
    provenance: dict[str, Any]
    description: str | None = None
    inline_decision: dict[str, Any] | None = None


def identity_for(consumer_anchor: str, logical_surface: str, target_scope: str) -> dict[str, str]:
    return {
        "consumer_anchor": require_string(consumer_anchor, label="consumer anchor"),
        "logical_referenced_surface": require_string(logical_surface, label="logical referenced surface"),
        "target_disposition_scope": require_string(target_scope, label="target disposition scope"),
    }


def identity_key(identity: dict[str, str]) -> str:
    if set(identity) != {"consumer_anchor", "logical_referenced_surface", "target_disposition_scope"}:
        raise MatrixError("edge identity must contain exactly its three stable components")
    return canonical_key(identity)


def _direct_module_bindings(module: ast.Module) -> tuple[dict[str, tuple[ast.AST, ast.Name]], set[str]]:
    bindings: dict[str, tuple[ast.AST, ast.Name]] = {}
    duplicates: set[str] = set()
    for node in module.body:
        targets: list[ast.Name] = []
        value: ast.AST | None = None
        if isinstance(node, ast.Assign):
            targets = [target for target in node.targets if isinstance(target, ast.Name)]
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            targets = [node.target]
            value = node.value
        if value is None:
            continue
        for target in targets:
            if target.id in bindings:
                duplicates.add(target.id)
            else:
                bindings[target.id] = (value, target)
    return bindings, duplicates


def _expression_references(expr: ast.AST, local_names: frozenset[str] = frozenset()) -> set[str]:
    """Collect static binding references while excluding generator-local names."""

    if isinstance(expr, ast.Name):
        return set() if expr.id in local_names else {expr.id}
    if isinstance(expr, ast.GeneratorExp):
        references: set[str] = set()
        local = set(local_names)
        for generator in expr.generators:
            references.update(_expression_references(generator.iter, frozenset(local)))
            if not isinstance(generator.target, ast.Name):
                raise MatrixError("AST tuple comprehension target must be a simple name")
            local.add(generator.target.id)
            for condition in generator.ifs:
                references.update(_expression_references(condition, frozenset(local)))
        references.update(_expression_references(expr.elt, frozenset(local)))
        return references
    references: set[str] = set()
    for child in ast.iter_child_nodes(expr):
        references.update(_expression_references(child, local_names))
    return references


def audited_assignment_bindings(text: str, root_binding: str) -> dict[str, ast.AST]:
    try:
        module = ast.parse(text)
    except SyntaxError as exc:
        raise MatrixError(f"AST tuple source does not parse: {exc}") from exc
    if any(
        isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names)
        for node in ast.walk(module)
    ):
        raise MatrixError("AST tuple source rejects wildcard imports")
    direct, duplicates = _direct_module_bindings(module)

    def other_binding_nodes(name: str) -> list[ast.AST]:
        """Return every Python binding form that can shadow an audited name."""

        result: list[ast.AST] = []
        for node in ast.walk(module):
            if isinstance(node, ast.Name) and node.id == name and isinstance(node.ctx, (ast.Store, ast.Del)):
                result.append(node)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == name:
                result.append(node)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    bound = alias.asname or alias.name.partition(".")[0]
                    if bound == name:
                        result.append(node)
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    bound = alias.asname or alias.name
                    if bound == name:
                        result.append(node)
            elif isinstance(node, ast.ExceptHandler) and node.name == name:
                result.append(node)
            elif isinstance(node, ast.arg) and node.arg == name:
                result.append(node)
            elif isinstance(node, ast.MatchAs) and node.name == name:
                result.append(node)
            elif isinstance(node, ast.MatchStar) and node.name == name:
                result.append(node)
            elif isinstance(node, ast.MatchMapping) and node.rest == name:
                result.append(node)
        return result

    reachable: set[str] = {root_binding}
    pending = [root_binding]
    while pending:
        name = pending.pop()
        if name in duplicates or name not in direct:
            raise MatrixError(f"AST tuple binding must have exactly one direct module assignment: {name}")
        value, selected_target = direct[name]
        binding_nodes = other_binding_nodes(name)
        if len(binding_nodes) != 1 or binding_nodes[0] is not selected_target:
            raise MatrixError(f"AST tuple binding is rebound, deleted, conditional, or mutated: {name}")
        if not isinstance(value, ast.Tuple):
            raise MatrixError(f"AST tuple binding must use a tuple declaration: {name}")
        if any(isinstance(node, ast.List) for node in ast.walk(value)):
            raise MatrixError(f"AST tuple binding rejects list values: {name}")
        for reference in _expression_references(value):
            if reference not in reachable:
                reachable.add(reference)
                pending.append(reference)
    for name in reachable:
        for generator in (node for node in ast.walk(direct[name][0]) if isinstance(node, ast.comprehension)):
            if not isinstance(generator.target, ast.Name):
                raise MatrixError("AST tuple comprehension target must be a simple name")
            if generator.target.id in reachable:
                raise MatrixError("AST tuple generator variable shadows a reachable binding")
    return {name: direct[name][0] for name in reachable}


def static_string(expr: ast.AST, variables: dict[str, str]) -> str:
    if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
        return expr.value
    if isinstance(expr, ast.JoinedStr):
        pieces: list[str] = []
        for item in expr.values:
            if isinstance(item, ast.Constant) and isinstance(item.value, str):
                pieces.append(item.value)
            elif isinstance(item, ast.FormattedValue) and isinstance(item.value, ast.Name) and item.value.id in variables:
                if item.conversion != -1 or item.format_spec is not None:
                    raise MatrixError("AST tuple does not support f-string conversions or format specifications")
                pieces.append(variables[item.value.id])
            else:
                raise MatrixError("AST tuple supports only literal f-string text and one bound name")
        return "".join(pieces)
    raise MatrixError("AST tuple contains an unsupported string expression")


def expand_ast_tuple(binding: str, bindings: dict[str, ast.AST], stack: tuple[str, ...] = ()) -> list[str]:
    if binding in stack:
        raise MatrixError(f"AST tuple binding cycle: {' -> '.join((*stack, binding))}")
    if binding not in bindings:
        raise MatrixError(f"AST tuple binding is absent: {binding}")

    def expand_tuple_declaration(expr: ast.AST, variables: dict[str, str]) -> list[str]:
        if not isinstance(expr, ast.Tuple):
            raise MatrixError("AST tuple binding must use a tuple declaration")
        values: list[str] = []
        for item in expr.elts:
            if isinstance(item, ast.Starred):
                values.extend(expand_starred_sequence(item.value, variables))
            else:
                # A bare name, tuple, list, or generator is one tuple element
                # in Python.  Only a literal static string is admissible here.
                values.append(static_string(item, variables))
        return values

    def expand_starred_sequence(expr: ast.AST, variables: dict[str, str]) -> list[str]:
        if isinstance(expr, ast.Name):
            if expr.id in variables:
                raise MatrixError("AST tuple rejects starring a scalar generator variable")
            return expand_ast_tuple(expr.id, bindings, (*stack, binding))
        if isinstance(expr, ast.Tuple):
            return expand_tuple_declaration(expr, variables)
        if isinstance(expr, ast.List):
            raise MatrixError("AST tuple rejects list values and mutation-prone carriers")
        if isinstance(expr, ast.GeneratorExp):
            if len(expr.generators) != 1:
                raise MatrixError("AST tuple supports only one-generator static comprehensions")
            generator = expr.generators[0]
            if generator.ifs or generator.is_async or not isinstance(generator.target, ast.Name):
                raise MatrixError("AST tuple comprehension shape is not static")
            values: list[str] = []
            for item in expand_starred_sequence(generator.iter, variables):
                nested = dict(variables)
                nested[generator.target.id] = item
                values.append(static_string(expr.elt, nested))
            return values
        raise MatrixError(f"AST tuple starred element is not a supported static sequence: {type(expr).__name__}")

    return expand_tuple_declaration(bindings[binding], {})


def parse_phase_cases(text: str, *, marker: str) -> list[dict[str, str]]:
    marker_count = text.count(marker)
    if marker_count != 1:
        raise MatrixError("role/phase selector marker must occur exactly once")
    start = text.find(marker)
    end = text.find("\n  esac", start)
    if end < 0:
        raise MatrixError("role/phase selector terminator is absent")
    section = text[start + len(marker):end]
    result: list[dict[str, str]] = []
    for raw_line in section.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line == "*) return 1 ;;":
            continue
        match = PHASE_CASE_RE.fullmatch(raw_line)
        if match is None:
            raise MatrixError("role/phase map has an unrecognized case clause")
        filename = match.group(2)
        if not PHASE_FILENAME_RE.fullmatch(filename):
            raise MatrixError("role/phase map emitted a nonliteral prompt filename")
        for item in match.group(1).split("|"):
            role, phase = item.split(":", 1)
            result.append({"role": role, "phase": phase, "filename": filename})
    if not result:
        raise MatrixError("role/phase selector emitted no literal cases")
    return result


def require_selector_common(selector: dict[str, Any], *, label: str) -> tuple[str, str]:
    selector_id = require_string(selector.get("id"), label=f"{label}.id")
    kind = require_string(selector.get("kind"), label=f"{label}.kind")
    if kind not in SELECTOR_KINDS:
        raise MatrixError(f"{label}.kind is unsupported: {kind!r}")
    return selector_id, kind


def ast_edges(reader: GitObjectReader, commit: str, selector: dict[str, Any]) -> list[ExpectedEdge]:
    reject_unknown_keys(
        selector,
        {"id", "kind", "source_path", "binding", "consumer_anchor_prefix", "logical_surface_prefix", "target_scope_prefix"},
        label="ast tuple selector",
    )
    selector_id, _ = require_selector_common(selector, label="ast tuple selector")
    source_path = require_repo_path(selector.get("source_path"), label=f"{selector_id}.source_path")
    binding = require_string(selector.get("binding"), label=f"{selector_id}.binding")
    consumer_prefix = require_string(selector.get("consumer_anchor_prefix"), label=f"{selector_id}.consumer_anchor_prefix")
    logical_prefix = require_string(selector.get("logical_surface_prefix"), label=f"{selector_id}.logical_surface_prefix")
    scope_prefix = require_string(selector.get("target_scope_prefix"), label=f"{selector_id}.target_scope_prefix")
    consumer_fact, text = reader.text_file(commit, source_path)
    values = expand_ast_tuple(binding, audited_assignment_bindings(text, binding))
    if len(values) != len(set(values)):
        raise MatrixError(f"{selector_id} AST tuple expanded duplicate values")
    result: list[ExpectedEdge] = []
    for index, value in enumerate(values):
        safe_value = require_repo_path(value, label=f"{selector_id} AST tuple value")
        result.append(
            ExpectedEdge(
                identity=identity_for(f"{consumer_prefix}:{index}", f"{logical_prefix}{safe_value}", f"{scope_prefix}{safe_value}"),
                selector_id=selector_id,
                selector_kind="ast_tuple",
                consumer_repository="source",
                consumer_path=source_path,
                consumer_anchor_detail={"binding": binding, "index": index, "object": consumer_fact},
                source_surface_path=safe_value,
                target_surface_path=safe_value,
                provenance={"kind": "ast_tuple", "binding": binding, "value": safe_value},
            )
        )
    return result


def phase_edges(reader: GitObjectReader, commit: str, selector: dict[str, Any]) -> list[ExpectedEdge]:
    reject_unknown_keys(
        selector,
        {
            "id",
            "kind",
            "source_path",
            "case_marker",
            "consumer_anchor_prefix",
            "logical_surface_prefix",
            "target_scope_prefix",
            "source_prompt_prefix",
            "target_prompt_prefix",
        },
        label="role phase selector",
    )
    selector_id, _ = require_selector_common(selector, label="role phase selector")
    source_path = require_repo_path(selector.get("source_path"), label=f"{selector_id}.source_path")
    marker = require_string(selector.get("case_marker"), label=f"{selector_id}.case_marker")
    consumer_prefix = require_string(selector.get("consumer_anchor_prefix"), label=f"{selector_id}.consumer_anchor_prefix")
    logical_prefix = require_string(selector.get("logical_surface_prefix"), label=f"{selector_id}.logical_surface_prefix")
    scope_prefix = require_string(selector.get("target_scope_prefix"), label=f"{selector_id}.target_scope_prefix")
    source_prefix = require_string(selector.get("source_prompt_prefix"), label=f"{selector_id}.source_prompt_prefix")
    target_prefix = require_string(selector.get("target_prompt_prefix"), label=f"{selector_id}.target_prompt_prefix")
    consumer_fact, text = reader.text_file(commit, source_path)
    result: list[ExpectedEdge] = []
    for case in parse_phase_cases(text, marker=marker):
        filename = case["filename"]
        source_surface = require_repo_path(f"{source_prefix}{filename}", label=f"{selector_id}.source prompt")
        target_surface = require_repo_path(f"{target_prefix}{filename}", label=f"{selector_id}.target prompt")
        result.append(
            ExpectedEdge(
                identity=identity_for(
                    f"{consumer_prefix}:{case['role']}:{case['phase']}",
                    f"{logical_prefix}{source_surface}",
                    f"{scope_prefix}{target_surface}",
                ),
                selector_id=selector_id,
                selector_kind="role_phase_map",
                consumer_repository="source",
                consumer_path=source_path,
                consumer_anchor_detail={**case, "object": consumer_fact},
                source_surface_path=source_surface,
                target_surface_path=target_surface,
                provenance={"kind": "role_phase_map", **case},
            )
        )
    return result


def profile_edges(reader: GitObjectReader, commit: str, selector: dict[str, Any]) -> list[ExpectedEdge]:
    reject_unknown_keys(
        selector,
        {"id", "kind", "source_prefix", "target_prefix", "consumer_anchor_prefix", "logical_surface_prefix", "target_scope_prefix", "require_nonempty"},
        label="profile file tree selector",
    )
    selector_id, _ = require_selector_common(selector, label="profile file tree selector")
    source_prefix = require_repo_path(selector.get("source_prefix"), label=f"{selector_id}.source_prefix").rstrip("/")
    target_prefix = require_repo_path(selector.get("target_prefix"), label=f"{selector_id}.target_prefix").rstrip("/")
    consumer_prefix = require_string(selector.get("consumer_anchor_prefix"), label=f"{selector_id}.consumer_anchor_prefix")
    logical_prefix = require_string(selector.get("logical_surface_prefix"), label=f"{selector_id}.logical_surface_prefix")
    scope_prefix = require_string(selector.get("target_scope_prefix"), label=f"{selector_id}.target_scope_prefix")
    require_nonempty = require_bool(selector.get("require_nonempty"), label=f"{selector_id}.require_nonempty")
    entries = reader.tree_entries(commit, [source_prefix])
    if require_nonempty and not entries:
        raise MatrixError(f"{selector_id} profile tree is empty")
    result: list[ExpectedEdge] = []
    for entry in entries:
        source_path = str(entry["path"])
        suffix = source_path.removeprefix(source_prefix + "/")
        if suffix == source_path or not suffix:
            raise MatrixError(f"{selector_id} profile tree path does not have its declared prefix")
        target_path = require_repo_path(f"{target_prefix}/{suffix}", label=f"{selector_id}.target profile path")
        result.append(
            ExpectedEdge(
                identity=identity_for(f"{consumer_prefix}:{source_path}", f"{logical_prefix}{source_path}", f"{scope_prefix}{target_path}"),
                selector_id=selector_id,
                selector_kind="profile_file_tree",
                consumer_repository="source",
                consumer_path=source_path,
                consumer_anchor_detail={"profile_path": source_path, "object": entry},
                source_surface_path=source_path,
                target_surface_path=target_path,
                provenance={"kind": "profile_file_tree", "profile_path": source_path, "target_path": target_path},
            )
        )
    return result


def literal_edges(source: GitObjectReader, target: GitObjectReader, source_commit: str, target_commit: str, selector: dict[str, Any]) -> list[ExpectedEdge]:
    reject_unknown_keys(
        selector,
        {
            "id",
            "kind",
            "repository",
            "paths",
            "literal",
            "consumer_anchor_prefix",
            "logical_referenced_surface",
            "target_disposition_scope",
            "require_hit",
        },
        label="literal selector",
    )
    selector_id, _ = require_selector_common(selector, label="literal selector")
    repository = require_string(selector.get("repository"), label=f"{selector_id}.repository")
    if repository not in {"source", "target"}:
        raise MatrixError(f"{selector_id}.repository must be source or target")
    paths = [require_repo_path(item, label=f"{selector_id}.paths") for item in require_list(selector.get("paths"), label=f"{selector_id}.paths")]
    if not paths or len(paths) != len(set(paths)):
        raise MatrixError(f"{selector_id}.paths must be a nonempty unique list")
    literal = require_string(selector.get("literal"), label=f"{selector_id}.literal")
    consumer_prefix = require_string(selector.get("consumer_anchor_prefix"), label=f"{selector_id}.consumer_anchor_prefix")
    logical_surface = require_string(selector.get("logical_referenced_surface"), label=f"{selector_id}.logical_referenced_surface")
    target_scope = require_string(selector.get("target_disposition_scope"), label=f"{selector_id}.target_disposition_scope")
    require_hit = require_bool(selector.get("require_hit"), label=f"{selector_id}.require_hit")
    reader = source if repository == "source" else target
    commit = source_commit if repository == "source" else target_commit
    hits = reader.literal_hits(commit, paths, literal)
    if require_hit and not hits:
        raise MatrixError(f"{selector_id} did not find its required literal")
    result: list[ExpectedEdge] = []
    for hit in hits:
        path = str(hit["path"])
        source_path = path if repository == "source" else None
        target_path = path if repository == "target" else None
        result.append(
            ExpectedEdge(
                identity=identity_for(f"{consumer_prefix}:{path}:{hit['line']}", logical_surface, target_scope),
                selector_id=selector_id,
                selector_kind="direct_literal_reference_hits",
                consumer_repository=repository,
                consumer_path=path,
                consumer_anchor_detail={"line": hit["line"], "literal": literal, "line_sha256": hit["line_sha256"], "object": hit["object"]},
                source_surface_path=source_path,
                target_surface_path=target_path,
                provenance={"kind": "direct_literal_reference_hits", "repository": repository, "path": path, "line": hit["line"], "literal": literal},
            )
        )
    return result


def target_surface_tree_entries(
    target: GitObjectReader,
    target_commit: str,
    *,
    selector_id: str,
    prefixes: list[str],
    require_nonempty: bool,
) -> list[dict[str, Any]]:
    """Read each declared prefix and return its stable deduplicated union."""

    entries_by_path: dict[str, dict[str, Any]] = {}
    for prefix in prefixes:
        prefix_entries = target.tree_entries(target_commit, [prefix])
        if require_nonempty and not prefix_entries:
            raise MatrixError(f"{selector_id} target surface prefix is empty: {prefix}")
        for entry in prefix_entries:
            entries_by_path.setdefault(str(entry["path"]), entry)
    return [entries_by_path[path] for path in sorted(entries_by_path)]


def target_surface_edges(target: GitObjectReader, target_commit: str, selector: dict[str, Any]) -> list[ExpectedEdge]:
    reject_unknown_keys(
        selector,
        {"id", "kind", "prefixes", "consumer_anchor_prefix", "logical_surface_prefix", "target_scope_prefix", "require_nonempty"},
        label="target surface selector",
    )
    selector_id, _ = require_selector_common(selector, label="target surface selector")
    prefixes = [require_repo_path(item, label=f"{selector_id}.prefixes") for item in require_list(selector.get("prefixes"), label=f"{selector_id}.prefixes")]
    if not prefixes or len(prefixes) != len(set(prefixes)):
        raise MatrixError(f"{selector_id}.prefixes must be a nonempty unique list")
    consumer_prefix = require_string(selector.get("consumer_anchor_prefix"), label=f"{selector_id}.consumer_anchor_prefix")
    logical_prefix = require_string(selector.get("logical_surface_prefix"), label=f"{selector_id}.logical_surface_prefix")
    scope_prefix = require_string(selector.get("target_scope_prefix"), label=f"{selector_id}.target_scope_prefix")
    require_nonempty = require_bool(selector.get("require_nonempty"), label=f"{selector_id}.require_nonempty")
    entries = target_surface_tree_entries(
        target,
        target_commit,
        selector_id=selector_id,
        prefixes=prefixes,
        require_nonempty=require_nonempty,
    )
    return [
        ExpectedEdge(
            identity=identity_for(f"{consumer_prefix}:{entry['path']}", f"{logical_prefix}{entry['path']}", f"{scope_prefix}{entry['path']}"),
            selector_id=selector_id,
            selector_kind="target_surface_tree",
            consumer_repository="target",
            consumer_path=str(entry["path"]),
            consumer_anchor_detail={"target_path": entry["path"], "object": entry},
            source_surface_path=None,
            target_surface_path=str(entry["path"]),
            provenance={"kind": "target_surface_tree", "target_path": entry["path"]},
        )
        for entry in entries
    ]


def manual_edges(source: GitObjectReader, source_commit: str, anchors: list[Any]) -> list[ExpectedEdge]:
    result: list[ExpectedEdge] = []
    for position, raw_anchor in enumerate(anchors):
        anchor = require_object(raw_anchor, label=f"manual_research_anchors[{position}]")
        reject_unknown_keys(
            anchor,
            {"id", "consumer_anchor", "logical_referenced_surface", "target_disposition_scope", "source_proof_path", "description", "decision"},
            label=f"manual_research_anchors[{position}]",
        )
        anchor_id = require_string(anchor.get("id"), label=f"manual_research_anchors[{position}].id")
        consumer_anchor = require_string(anchor.get("consumer_anchor"), label=f"manual_research_anchors[{position}].consumer_anchor")
        logical_surface = require_string(anchor.get("logical_referenced_surface"), label=f"manual_research_anchors[{position}].logical_referenced_surface")
        target_scope = require_string(anchor.get("target_disposition_scope"), label=f"manual_research_anchors[{position}].target_disposition_scope")
        source_path = require_repo_path(anchor.get("source_proof_path"), label=f"manual_research_anchors[{position}].source_proof_path")
        source_fact = source.entry(source_commit, source_path)
        if source_fact["state"] != "present":
            raise MatrixError(f"manual research anchor {anchor_id} lacks its pinned source proof object")
        description = require_string(anchor.get("description"), label=f"manual_research_anchors[{position}].description")
        decision = require_object(anchor.get("decision"), label=f"manual_research_anchors[{position}].decision")
        result.append(
            ExpectedEdge(
                identity=identity_for(consumer_anchor, logical_surface, target_scope),
                selector_id=f"manual:{anchor_id}",
                selector_kind="manual_dynamic_research_anchor",
                consumer_repository="source",
                consumer_path=source_path,
                consumer_anchor_detail={"manual_id": anchor_id, "object": source_fact},
                source_surface_path=source_path,
                target_surface_path=None,
                provenance={"kind": "manual_dynamic_research_anchor", "manual_id": anchor_id, "source_proof_path": source_path},
                description=description,
                inline_decision=decision,
            )
        )
    return result


def _source_selectors(rules: dict[str, Any]) -> list[Any]:
    return require_list(rules.get("source_selectors"), label="rules.source_selectors")


def _target_selectors(rules: dict[str, Any]) -> list[Any]:
    return require_list(rules.get("target_surface_selectors"), label="rules.target_surface_selectors")


def append_unique_manual_edges(
    edges: list[ExpectedEdge],
    selector_ids: set[str],
    source: GitObjectReader,
    source_commit: str,
    rules: dict[str, Any],
) -> None:
    """Add explicit research rows without allowing selector-ID aliasing."""

    manual = manual_edges(source, source_commit, require_list(rules.get("manual_research_anchors"), label="rules.manual_research_anchors"))
    manual_selector_ids = [edge.selector_id for edge in manual]
    if len(manual_selector_ids) != len(set(manual_selector_ids)):
        raise MatrixError("manual research anchors contain duplicate selector IDs")
    if selector_ids.intersection(manual_selector_ids):
        raise MatrixError("manual selector ID collides with a declared selector")
    selector_ids.update(manual_selector_ids)
    edges.extend(manual)


def enumerate_for_emit(source: GitObjectReader, target: GitObjectReader, source_commit: str, target_commit: str, rules: dict[str, Any]) -> list[ExpectedEdge]:
    """Generator enumeration.  Verification has a separately written walk."""

    edges: list[ExpectedEdge] = []
    seen_selector_ids: set[str] = set()
    for index, raw_selector in enumerate(_source_selectors(rules)):
        selector = require_object(raw_selector, label=f"rules.source_selectors[{index}]")
        selector_id, kind = require_selector_common(selector, label=f"rules.source_selectors[{index}]")
        if selector_id in seen_selector_ids:
            raise MatrixError(f"duplicate selector id: {selector_id}")
        seen_selector_ids.add(selector_id)
        if kind == "ast_tuple":
            edges.extend(ast_edges(source, source_commit, selector))
        elif kind == "role_phase_map":
            edges.extend(phase_edges(source, source_commit, selector))
        elif kind == "profile_file_tree":
            edges.extend(profile_edges(source, source_commit, selector))
        elif kind == "direct_literal_reference_hits":
            edges.extend(literal_edges(source, target, source_commit, target_commit, selector))
        else:
            raise MatrixError(f"{selector_id} is not valid in source_selectors")
    for index, raw_selector in enumerate(_target_selectors(rules)):
        selector = require_object(raw_selector, label=f"rules.target_surface_selectors[{index}]")
        selector_id, kind = require_selector_common(selector, label=f"rules.target_surface_selectors[{index}]")
        if selector_id in seen_selector_ids:
            raise MatrixError(f"duplicate selector id: {selector_id}")
        seen_selector_ids.add(selector_id)
        if kind != "target_surface_tree":
            raise MatrixError(f"{selector_id} is not valid in target_surface_selectors")
        edges.extend(target_surface_edges(target, target_commit, selector))
    append_unique_manual_edges(edges, seen_selector_ids, source, source_commit, rules)
    return ensure_unique_edges(edges)


def verify_ast_selector(reader: GitObjectReader, commit: str, selector: dict[str, Any]) -> list[ExpectedEdge]:
    """Independently reconstruct AST-selector edges for verification."""

    reject_unknown_keys(selector, {"id", "kind", "source_path", "binding", "consumer_anchor_prefix", "logical_surface_prefix", "target_scope_prefix"}, label="checker ast tuple selector")
    selector_id, kind = require_selector_common(selector, label="checker ast tuple selector")
    if kind != "ast_tuple":
        raise MatrixError("checker AST selector kind mismatch")
    source_path = require_repo_path(selector.get("source_path"), label=f"{selector_id}.source_path")
    binding = require_string(selector.get("binding"), label=f"{selector_id}.binding")
    consumer_prefix = require_string(selector.get("consumer_anchor_prefix"), label=f"{selector_id}.consumer_anchor_prefix")
    logical_prefix = require_string(selector.get("logical_surface_prefix"), label=f"{selector_id}.logical_surface_prefix")
    scope_prefix = require_string(selector.get("target_scope_prefix"), label=f"{selector_id}.target_scope_prefix")
    consumer_fact, text = reader.text_file(commit, source_path)
    values = expand_ast_tuple(binding, audited_assignment_bindings(text, binding))
    if len(values) != len(set(values)):
        raise MatrixError(f"checker {selector_id} AST tuple expanded duplicate values")
    reconstructed: list[ExpectedEdge] = []
    for ordinal, raw_value in enumerate(values):
        value = require_repo_path(raw_value, label=f"checker {selector_id} AST tuple value")
        reconstructed.append(ExpectedEdge(identity=identity_for(f"{consumer_prefix}:{ordinal}", f"{logical_prefix}{value}", f"{scope_prefix}{value}"), selector_id=selector_id, selector_kind="ast_tuple", consumer_repository="source", consumer_path=source_path, consumer_anchor_detail={"binding": binding, "index": ordinal, "object": consumer_fact}, source_surface_path=value, target_surface_path=value, provenance={"kind": "ast_tuple", "binding": binding, "value": value}))
    return reconstructed


def verify_phase_selector(reader: GitObjectReader, commit: str, selector: dict[str, Any]) -> list[ExpectedEdge]:
    """Independently reconstruct literal role/phase selector edges."""

    allowed = {"id", "kind", "source_path", "case_marker", "consumer_anchor_prefix", "logical_surface_prefix", "target_scope_prefix", "source_prompt_prefix", "target_prompt_prefix"}
    reject_unknown_keys(selector, allowed, label="checker role phase selector")
    selector_id, kind = require_selector_common(selector, label="checker role phase selector")
    if kind != "role_phase_map":
        raise MatrixError("checker role/phase selector kind mismatch")
    source_path = require_repo_path(selector.get("source_path"), label=f"{selector_id}.source_path")
    marker = require_string(selector.get("case_marker"), label=f"{selector_id}.case_marker")
    consumer_prefix = require_string(selector.get("consumer_anchor_prefix"), label=f"{selector_id}.consumer_anchor_prefix")
    logical_prefix = require_string(selector.get("logical_surface_prefix"), label=f"{selector_id}.logical_surface_prefix")
    scope_prefix = require_string(selector.get("target_scope_prefix"), label=f"{selector_id}.target_scope_prefix")
    source_prefix = require_string(selector.get("source_prompt_prefix"), label=f"{selector_id}.source_prompt_prefix")
    target_prefix = require_string(selector.get("target_prompt_prefix"), label=f"{selector_id}.target_prompt_prefix")
    consumer_fact, text = reader.text_file(commit, source_path)
    reconstructed: list[ExpectedEdge] = []
    for case in parse_phase_cases(text, marker=marker):
        source_surface = require_repo_path(f"{source_prefix}{case['filename']}", label=f"checker {selector_id}.source prompt")
        target_surface = require_repo_path(f"{target_prefix}{case['filename']}", label=f"checker {selector_id}.target prompt")
        reconstructed.append(ExpectedEdge(identity=identity_for(f"{consumer_prefix}:{case['role']}:{case['phase']}", f"{logical_prefix}{source_surface}", f"{scope_prefix}{target_surface}"), selector_id=selector_id, selector_kind="role_phase_map", consumer_repository="source", consumer_path=source_path, consumer_anchor_detail={**case, "object": consumer_fact}, source_surface_path=source_surface, target_surface_path=target_surface, provenance={"kind": "role_phase_map", **case}))
    return reconstructed


def verify_profile_selector(reader: GitObjectReader, commit: str, selector: dict[str, Any]) -> list[ExpectedEdge]:
    """Independently reconstruct profile-tree edges from pinned tree entries."""

    allowed = {"id", "kind", "source_prefix", "target_prefix", "consumer_anchor_prefix", "logical_surface_prefix", "target_scope_prefix", "require_nonempty"}
    reject_unknown_keys(selector, allowed, label="checker profile file tree selector")
    selector_id, kind = require_selector_common(selector, label="checker profile file tree selector")
    if kind != "profile_file_tree":
        raise MatrixError("checker profile selector kind mismatch")
    source_prefix = require_repo_path(selector.get("source_prefix"), label=f"{selector_id}.source_prefix").rstrip("/")
    target_prefix = require_repo_path(selector.get("target_prefix"), label=f"{selector_id}.target_prefix").rstrip("/")
    consumer_prefix = require_string(selector.get("consumer_anchor_prefix"), label=f"{selector_id}.consumer_anchor_prefix")
    logical_prefix = require_string(selector.get("logical_surface_prefix"), label=f"{selector_id}.logical_surface_prefix")
    scope_prefix = require_string(selector.get("target_scope_prefix"), label=f"{selector_id}.target_scope_prefix")
    require_nonempty = require_bool(selector.get("require_nonempty"), label=f"{selector_id}.require_nonempty")
    entries = reader.tree_entries(commit, [source_prefix])
    if require_nonempty and not entries:
        raise MatrixError(f"checker {selector_id} profile tree is empty")
    reconstructed: list[ExpectedEdge] = []
    for entry in entries:
        profile_path = str(entry["path"])
        suffix = profile_path.removeprefix(source_prefix + "/")
        if suffix == profile_path or not suffix:
            raise MatrixError(f"checker {selector_id} profile path lacks source prefix")
        target_path = require_repo_path(f"{target_prefix}/{suffix}", label=f"checker {selector_id}.target profile path")
        reconstructed.append(ExpectedEdge(identity=identity_for(f"{consumer_prefix}:{profile_path}", f"{logical_prefix}{profile_path}", f"{scope_prefix}{target_path}"), selector_id=selector_id, selector_kind="profile_file_tree", consumer_repository="source", consumer_path=profile_path, consumer_anchor_detail={"profile_path": profile_path, "object": entry}, source_surface_path=profile_path, target_surface_path=target_path, provenance={"kind": "profile_file_tree", "profile_path": profile_path, "target_path": target_path}))
    return reconstructed


def verify_literal_selector(source: GitObjectReader, target: GitObjectReader, source_commit: str, target_commit: str, selector: dict[str, Any]) -> list[ExpectedEdge]:
    """Independently reconstruct every literal frontier hit without a cap."""

    allowed = {"id", "kind", "repository", "paths", "literal", "consumer_anchor_prefix", "logical_referenced_surface", "target_disposition_scope", "require_hit"}
    reject_unknown_keys(selector, allowed, label="checker literal selector")
    selector_id, kind = require_selector_common(selector, label="checker literal selector")
    if kind != "direct_literal_reference_hits":
        raise MatrixError("checker literal selector kind mismatch")
    repository = require_string(selector.get("repository"), label=f"{selector_id}.repository")
    if repository not in {"source", "target"}:
        raise MatrixError(f"checker {selector_id}.repository is invalid")
    paths = [require_repo_path(item, label=f"checker {selector_id}.paths") for item in require_list(selector.get("paths"), label=f"{selector_id}.paths")]
    if not paths or len(paths) != len(set(paths)):
        raise MatrixError(f"checker {selector_id}.paths is not unique")
    literal = require_string(selector.get("literal"), label=f"{selector_id}.literal")
    consumer_prefix = require_string(selector.get("consumer_anchor_prefix"), label=f"{selector_id}.consumer_anchor_prefix")
    logical_surface = require_string(selector.get("logical_referenced_surface"), label=f"{selector_id}.logical_referenced_surface")
    target_scope = require_string(selector.get("target_disposition_scope"), label=f"{selector_id}.target_disposition_scope")
    require_hit = require_bool(selector.get("require_hit"), label=f"{selector_id}.require_hit")
    reader, commit = (source, source_commit) if repository == "source" else (target, target_commit)
    hits = reader.literal_hits(commit, paths, literal)
    if require_hit and not hits:
        raise MatrixError(f"checker {selector_id} did not find its required literal")
    reconstructed: list[ExpectedEdge] = []
    for hit in hits:
        path = str(hit["path"])
        reconstructed.append(ExpectedEdge(identity=identity_for(f"{consumer_prefix}:{path}:{hit['line']}", logical_surface, target_scope), selector_id=selector_id, selector_kind="direct_literal_reference_hits", consumer_repository=repository, consumer_path=path, consumer_anchor_detail={"line": hit["line"], "literal": literal, "line_sha256": hit["line_sha256"], "object": hit["object"]}, source_surface_path=path if repository == "source" else None, target_surface_path=path if repository == "target" else None, provenance={"kind": "direct_literal_reference_hits", "repository": repository, "path": path, "line": hit["line"], "literal": literal}))
    return reconstructed


def verify_target_surface_selector(target: GitObjectReader, target_commit: str, selector: dict[str, Any]) -> list[ExpectedEdge]:
    """Independently reconstruct declared bounded target-surface entries."""

    allowed = {"id", "kind", "prefixes", "consumer_anchor_prefix", "logical_surface_prefix", "target_scope_prefix", "require_nonempty"}
    reject_unknown_keys(selector, allowed, label="checker target surface selector")
    selector_id, kind = require_selector_common(selector, label="checker target surface selector")
    if kind != "target_surface_tree":
        raise MatrixError("checker target surface selector kind mismatch")
    prefixes = [require_repo_path(item, label=f"checker {selector_id}.prefixes") for item in require_list(selector.get("prefixes"), label=f"{selector_id}.prefixes")]
    if not prefixes or len(prefixes) != len(set(prefixes)):
        raise MatrixError(f"checker {selector_id}.prefixes is not unique")
    consumer_prefix = require_string(selector.get("consumer_anchor_prefix"), label=f"{selector_id}.consumer_anchor_prefix")
    logical_prefix = require_string(selector.get("logical_surface_prefix"), label=f"{selector_id}.logical_surface_prefix")
    scope_prefix = require_string(selector.get("target_scope_prefix"), label=f"{selector_id}.target_scope_prefix")
    require_nonempty = require_bool(selector.get("require_nonempty"), label=f"{selector_id}.require_nonempty")
    entries = target_surface_tree_entries(
        target,
        target_commit,
        selector_id=selector_id,
        prefixes=prefixes,
        require_nonempty=require_nonempty,
    )
    return [ExpectedEdge(identity=identity_for(f"{consumer_prefix}:{entry['path']}", f"{logical_prefix}{entry['path']}", f"{scope_prefix}{entry['path']}"), selector_id=selector_id, selector_kind="target_surface_tree", consumer_repository="target", consumer_path=str(entry["path"]), consumer_anchor_detail={"target_path": entry["path"], "object": entry}, source_surface_path=None, target_surface_path=str(entry["path"]), provenance={"kind": "target_surface_tree", "target_path": entry["path"]}) for entry in entries]


def verify_manual_anchors(source: GitObjectReader, source_commit: str, anchors: list[Any]) -> list[ExpectedEdge]:
    """Independently reconstruct explicit dynamic/behavior obligations."""

    reconstructed: list[ExpectedEdge] = []
    for position, raw_anchor in enumerate(anchors):
        anchor = require_object(raw_anchor, label=f"checker manual_research_anchors[{position}]")
        reject_unknown_keys(anchor, {"id", "consumer_anchor", "logical_referenced_surface", "target_disposition_scope", "source_proof_path", "description", "decision"}, label=f"checker manual_research_anchors[{position}]")
        anchor_id = require_string(anchor.get("id"), label=f"checker manual_research_anchors[{position}].id")
        consumer_anchor = require_string(anchor.get("consumer_anchor"), label=f"checker manual_research_anchors[{position}].consumer_anchor")
        logical_surface = require_string(anchor.get("logical_referenced_surface"), label=f"checker manual_research_anchors[{position}].logical_referenced_surface")
        target_scope = require_string(anchor.get("target_disposition_scope"), label=f"checker manual_research_anchors[{position}].target_disposition_scope")
        source_path = require_repo_path(anchor.get("source_proof_path"), label=f"checker manual_research_anchors[{position}].source_proof_path")
        source_fact = source.entry(source_commit, source_path)
        if source_fact["state"] != "present":
            raise MatrixError(f"checker manual research anchor lacks source proof: {anchor_id}")
        description = require_string(anchor.get("description"), label=f"checker manual_research_anchors[{position}].description")
        decision = require_object(anchor.get("decision"), label=f"checker manual_research_anchors[{position}].decision")
        reconstructed.append(ExpectedEdge(identity=identity_for(consumer_anchor, logical_surface, target_scope), selector_id=f"manual:{anchor_id}", selector_kind="manual_dynamic_research_anchor", consumer_repository="source", consumer_path=source_path, consumer_anchor_detail={"manual_id": anchor_id, "object": source_fact}, source_surface_path=source_path, target_surface_path=None, provenance={"kind": "manual_dynamic_research_anchor", "manual_id": anchor_id, "source_proof_path": source_path}, description=description, inline_decision=decision))
    return reconstructed


def enumerate_for_verify(source: GitObjectReader, target: GitObjectReader, source_commit: str, target_commit: str, rules: dict[str, Any]) -> list[ExpectedEdge]:
    """Checker-owned expected-set derivation from raw selector facts."""

    verified: list[ExpectedEdge] = []
    selector_ids: set[str] = set()
    for raw_selector in _source_selectors(rules):
        selector = require_object(raw_selector, label="checker source selector")
        selector_id, kind = require_selector_common(selector, label="checker source selector")
        if selector_id in selector_ids:
            raise MatrixError(f"checker found duplicate selector id: {selector_id}")
        selector_ids.add(selector_id)
        if kind == "ast_tuple":
            verified.extend(verify_ast_selector(source, source_commit, selector))
        elif kind == "role_phase_map":
            verified.extend(verify_phase_selector(source, source_commit, selector))
        elif kind == "profile_file_tree":
            verified.extend(verify_profile_selector(source, source_commit, selector))
        elif kind == "direct_literal_reference_hits":
            verified.extend(verify_literal_selector(source, target, source_commit, target_commit, selector))
        else:
            raise MatrixError(f"checker does not accept {kind} as a source selector")
    for raw_selector in _target_selectors(rules):
        selector = require_object(raw_selector, label="checker target selector")
        selector_id, kind = require_selector_common(selector, label="checker target selector")
        if selector_id in selector_ids:
            raise MatrixError(f"checker found duplicate selector id: {selector_id}")
        selector_ids.add(selector_id)
        if kind != "target_surface_tree":
            raise MatrixError(f"checker does not accept {kind} as a target selector")
        verified.extend(verify_target_surface_selector(target, target_commit, selector))
    manual = verify_manual_anchors(source, source_commit, require_list(rules.get("manual_research_anchors"), label="rules.manual_research_anchors"))
    manual_selector_ids = [edge.selector_id for edge in manual]
    if len(manual_selector_ids) != len(set(manual_selector_ids)):
        raise MatrixError("checker found duplicate manual selector IDs")
    if selector_ids.intersection(manual_selector_ids):
        raise MatrixError("checker found manual selector ID collision")
    selector_ids.update(manual_selector_ids)
    verified.extend(manual)
    return ensure_unique_edges(verified)


def ensure_unique_edges(edges: list[ExpectedEdge]) -> list[ExpectedEdge]:
    by_key: dict[str, ExpectedEdge] = {}
    for edge in edges:
        key = identity_key(edge.identity)
        if key in by_key:
            raise MatrixError(f"duplicate expected edge identity: {key}")
        by_key[key] = edge
    return [by_key[key] for key in sorted(by_key)]


def validate_rules(rules: Any) -> dict[str, Any]:
    document = require_object(rules, label="rules")
    reject_unknown_keys(
        document,
        {"schema_version", "rule_set_id", "source_selectors", "target_surface_selectors", "manual_research_anchors", "decisions", "n_a_reasons"},
        label="rules",
    )
    if document.get("schema_version") != RULES_SCHEMA_VERSION:
        raise MatrixError("rules schema_version is unsupported")
    require_string(document.get("rule_set_id"), label="rules.rule_set_id")
    _source_selectors(document)
    _target_selectors(document)
    require_list(document.get("manual_research_anchors"), label="rules.manual_research_anchors")
    require_list(document.get("decisions"), label="rules.decisions")
    reasons = require_list(document.get("n_a_reasons"), label="rules.n_a_reasons")
    reason_codes: set[str] = set()
    for index, raw_reason in enumerate(reasons):
        reason = require_object(raw_reason, label=f"rules.n_a_reasons[{index}]")
        reject_unknown_keys(reason, {"code", "description"}, label=f"rules.n_a_reasons[{index}]")
        code = require_string(reason.get("code"), label=f"rules.n_a_reasons[{index}].code")
        require_string(reason.get("description"), label=f"rules.n_a_reasons[{index}].description")
        if code in reason_codes:
            raise MatrixError(f"duplicate n/a reason code: {code}")
        reason_codes.add(code)
    return document


def decision_identity(raw: dict[str, Any], *, label: str) -> dict[str, str]:
    identity = require_object(raw.get("identity"), label=f"{label}.identity")
    reject_unknown_keys(identity, {"consumer_anchor", "logical_referenced_surface", "target_disposition_scope"}, label=f"{label}.identity")
    return identity_for(identity.get("consumer_anchor"), identity.get("logical_referenced_surface"), identity.get("target_disposition_scope"))


def source_literal_proof(source: GitObjectReader, source_commit: str, raw: Any, *, label: str) -> dict[str, Any]:
    proof = require_object(raw, label=label)
    reject_unknown_keys(proof, {"path", "literal", "line"}, label=label)
    path = require_repo_path(proof.get("path"), label=f"{label}.path")
    literal = require_string(proof.get("literal"), label=f"{label}.literal")
    line = proof.get("line")
    if type(line) is not int or line < 1:
        raise MatrixError(f"{label}.line must be a positive integer")
    fact, text = source.text_file(source_commit, path)
    lines = text.splitlines()
    if line > len(lines) or literal not in lines[line - 1]:
        raise MatrixError(f"{label} does not match its pinned source literal")
    return {"path": path, "literal": literal, "line": line, "object": fact, "line_sha256": sha256_bytes(lines[line - 1].encode("utf-8"))}


def implementation_evidence(raw: Any, *, label: str, planned_extraction: bool) -> dict[str, Any]:
    evidence = require_object(raw, label=label)
    reject_unknown_keys(evidence, {"state", "obligations"}, label=label)
    state = require_string(evidence.get("state"), label=f"{label}.state")
    if state not in IMPLEMENTATION_EVIDENCE_STATES:
        raise MatrixError(f"{label}.state is unsupported: {state}")
    obligations_raw = evidence.get("obligations", [])
    obligations = [require_string(item, label=f"{label}.obligations") for item in require_list(obligations_raw, label=f"{label}.obligations")]
    if len(obligations) != len(set(obligations)):
        raise MatrixError(f"{label}.obligations contains a duplicate")
    if planned_extraction and state == "not_applicable":
        raise MatrixError("planned_extraction requires implementation_evidence state unfulfilled")
    if planned_extraction and state == "unfulfilled" and not obligations:
        raise MatrixError("unfulfilled planned_extraction requires explicit implementation obligations")
    return {"state": state, "obligations": obligations}


def materialize_decision(
    raw: dict[str, Any],
    edge: ExpectedEdge,
    source: GitObjectReader,
    source_commit: str,
    reason_codes: set[str],
    *,
    origin: str,
) -> dict[str, Any]:
    state = require_string(raw.get("decision_state"), label="decision.decision_state")
    if state not in DECISION_STATES:
        raise MatrixError(f"unsupported decision_state: {state}")
    result: dict[str, Any] = {"decision_state": state, "decision_origin": origin}
    if state == "decided":
        reject_unknown_keys(raw, {"identity", "decision_state", "disposition", "decision_evidence", "implementation_evidence", "n_a"}, label="decided decision")
        disposition = require_object(raw.get("disposition"), label="decided decision.disposition")
        reject_unknown_keys(disposition, {"kind"}, label="decided decision.disposition")
        kind = require_string(disposition.get("kind"), label="decided decision.disposition.kind")
        if kind not in DISPOSITION_KINDS:
            raise MatrixError(f"unsupported decided disposition: {kind}")
        evidence_raw = require_list(raw.get("decision_evidence"), label="decided decision.decision_evidence")
        if not evidence_raw:
            raise MatrixError("decided decision requires pinned evidence")
        decision_evidence: list[dict[str, Any]] = []
        for index, raw_evidence in enumerate(evidence_raw):
            evidence = require_object(raw_evidence, label=f"decided evidence[{index}]")
            reject_unknown_keys(evidence, {"path"}, label=f"decided evidence[{index}]")
            path = require_repo_path(evidence.get("path"), label=f"decided evidence[{index}].path")
            fact = source.entry(source_commit, path)
            if fact["state"] != "present":
                raise MatrixError(f"decided evidence path is absent in pinned source: {path}")
            decision_evidence.append({"path": path, "object": fact})
        n_a_value: dict[str, Any] | None = None
        if kind == "not_applicable":
            n_a = require_object(raw.get("n_a"), label="not_applicable decision.n_a")
            reject_unknown_keys(n_a, {"reason_code", "source_proof"}, label="not_applicable decision.n_a")
            reason_code = require_string(n_a.get("reason_code"), label="not_applicable decision.n_a.reason_code")
            if reason_code not in reason_codes:
                raise MatrixError(f"not_applicable decision uses unsupported reason code: {reason_code}")
            n_a_value = {"reason_code": reason_code, "source_proof": source_literal_proof(source, source_commit, n_a.get("source_proof"), label="not_applicable decision.n_a.source_proof")}
        elif "n_a" in raw:
            raise MatrixError("only not_applicable decisions may contain n_a")
        result["disposition"] = {"kind": kind}
        result["decision_evidence"] = decision_evidence
        result["implementation_evidence"] = implementation_evidence(
            raw.get("implementation_evidence"),
            label="decided decision.implementation_evidence",
            planned_extraction=kind == "planned_extraction",
        )
        if n_a_value is not None:
            result["n_a"] = n_a_value
    elif state == "pending_owner":
        reject_unknown_keys(raw, {"identity", "decision_state", "question", "implementation_evidence"}, label="pending_owner decision")
        result["question"] = require_string(raw.get("question"), label="pending_owner decision.question")
        result["implementation_evidence"] = implementation_evidence(raw.get("implementation_evidence"), label="pending_owner decision.implementation_evidence", planned_extraction=False)
    else:
        reject_unknown_keys(raw, {"identity", "decision_state", "research_obligation", "implementation_evidence"}, label="unresolved_research decision")
        result["research_obligation"] = require_string(raw.get("research_obligation"), label="unresolved_research decision.research_obligation")
        result["implementation_evidence"] = implementation_evidence(raw.get("implementation_evidence"), label="unresolved_research decision.implementation_evidence", planned_extraction=False)
    return result


def default_research_decision(edge: ExpectedEdge) -> dict[str, Any]:
    return {
        "decision_state": "unresolved_research",
        "decision_origin": "default_research",
        "research_obligation": f"Classify bounded static edge from selector {edge.selector_id}: {identity_key(edge.identity)}",
        "implementation_evidence": {"state": "not_applicable", "obligations": []},
    }


def decision_map(rules: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(require_list(rules.get("decisions"), label="rules.decisions")):
        decision = require_object(raw, label=f"rules.decisions[{index}]")
        key = identity_key(decision_identity(decision, label=f"rules.decisions[{index}]"))
        if key in result:
            raise MatrixError(f"duplicate decision identity: {key}")
        result[key] = decision
    return result


def object_evidence_for_edge(edge: ExpectedEdge, source: GitObjectReader, target: GitObjectReader, source_commit: str, target_commit: str) -> dict[str, Any]:
    if edge.consumer_repository == "source":
        consumer_object = source.entry(source_commit, edge.consumer_path)
    elif edge.consumer_repository == "target":
        consumer_object = target.entry(target_commit, edge.consumer_path)
    else:
        raise MatrixError(f"unsupported consumer repository: {edge.consumer_repository}")
    source_surface = source.entry(source_commit, edge.source_surface_path)
    target_surface = target.entry(target_commit, edge.target_surface_path)

    def require_regular_if_present(fact: dict[str, Any], *, label: str) -> None:
        if fact["state"] == "present" and fact["mode"] not in {"100644", "100755"}:
            raise MatrixError(f"{label} is present but not a regular Git file")

    require_regular_if_present(consumer_object, label="consumer object")
    require_regular_if_present(source_surface, label="source surface")
    require_regular_if_present(target_surface, label="target surface")
    return {
        "consumer": {
            "repository": edge.consumer_repository,
            "path": edge.consumer_path,
            "anchor": edge.consumer_anchor_detail,
            "object": consumer_object,
        },
        "source_surface": source_surface,
        "target_surface": target_surface,
    }


def materialize_rows(
    edges: list[ExpectedEdge],
    source: GitObjectReader,
    target: GitObjectReader,
    source_commit: str,
    target_commit: str,
    rules: dict[str, Any],
) -> list[dict[str, Any]]:
    explicit = decision_map(rules)
    reason_codes = {
        require_string(require_object(item, label="n/a reason").get("code"), label="n/a reason.code")
        for item in require_list(rules.get("n_a_reasons"), label="rules.n_a_reasons")
    }
    rows: list[dict[str, Any]] = []
    expected_keys = {identity_key(edge.identity) for edge in edges}
    extra_decisions = sorted(set(explicit) - expected_keys)
    if extra_decisions:
        raise MatrixError(f"decision refers to an unexplained extra edge: {extra_decisions[0]}")
    for edge in edges:
        key = identity_key(edge.identity)
        inline = edge.inline_decision
        configured = explicit.get(key)
        if inline is not None and configured is not None:
            raise MatrixError(f"manual edge has duplicate inline/global decisions: {key}")
        if inline is not None:
            decision = materialize_decision(inline, edge, source, source_commit, reason_codes, origin="manual_explicit")
        elif configured is not None:
            decision = materialize_decision(configured, edge, source, source_commit, reason_codes, origin="explicit")
        else:
            decision = default_research_decision(edge)
        row: dict[str, Any] = {
            "identity": edge.identity,
            "selector": {"id": edge.selector_id, "kind": edge.selector_kind},
            "object_evidence": object_evidence_for_edge(edge, source, target, source_commit, target_commit),
            "provenance": edge.provenance,
            **decision,
        }
        if edge.description is not None:
            row["description"] = edge.description
        rows.append(row)
    return rows


def decision_outcome(rows: list[dict[str, Any]]) -> tuple[str, dict[str, int]]:
    counts = Counter(str(row.get("decision_state")) for row in rows)
    blocked = any(
        row.get("decision_state") in {"pending_owner", "unresolved_research"}
        or row.get("decision_origin") == "default_research"
        for row in rows
    )
    return ("blocked" if blocked else "complete"), dict(sorted(counts.items()))


def rules_fact(source: GitObjectReader, source_commit: str, rules_path: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read the declared rule file from the supplied pinned source tree."""

    fact = source.entry(source_commit, rules_path)
    if fact["state"] != "present" or fact["mode"] != "100644":
        raise MatrixError("rules must be a regular 100644 source Git object")
    raw = source.blob(str(fact["blob_oid"]))
    rules = validate_rules(strict_json_loads(raw, label="rules"))
    return rules, {"path": rules_path, "object": fact, "sha256": sha256_bytes(raw), "schema_version": rules["schema_version"], "rule_set_id": rules["rule_set_id"]}


def make_inventory(
    source: GitObjectReader,
    target: GitObjectReader,
    source_root: Path,
    target_root: Path,
    source_commit: str,
    source_tree: str,
    target_commit: str,
    target_tree: str,
    rules_path: str,
    *,
    enumeration: Callable[[GitObjectReader, GitObjectReader, str, str, dict[str, Any]], list[ExpectedEdge]],
) -> dict[str, Any]:
    rules, rule_fact = rules_fact(source, source_commit, rules_path)
    edges = enumeration(source, target, source_commit, target_commit, rules)
    rows = materialize_rows(edges, source, target, source_commit, target_commit, rules)
    completion, state_counts = decision_outcome(rows)
    identities = [edge.identity for edge in edges]
    return {
        "schema_version": INVENTORY_SCHEMA_VERSION,
        "artifact_kind": "pinned_static_authority_edge_inventory",
        "inputs": {
            "source": {"root": os.fspath(source_root), "commit": source_commit, "tree": source_tree},
            "target": {"root": os.fspath(target_root), "commit": target_commit, "tree": target_tree},
            "rules": rule_fact,
        },
        "expected_edges": {"count": len(edges), "sha256": sha256_bytes(canonical_json_bytes(identities))},
        "row_state_counts": state_counts,
        "outcomes": {
            "inventory_integrity": "passed",
            "enumerated_decision_completeness": completion,
            "semantic_closure": "not_claimed",
        },
        "rows": rows,
    }


def require_inventory_shape(value: Any) -> dict[str, Any]:
    inventory = require_object(value, label="inventory")
    expected_keys = {"schema_version", "artifact_kind", "inputs", "expected_edges", "row_state_counts", "outcomes", "rows"}
    reject_unknown_keys(inventory, expected_keys, label="inventory")
    if set(inventory) != expected_keys:
        raise MatrixError("inventory is missing a required top-level field")
    if inventory.get("schema_version") != INVENTORY_SCHEMA_VERSION:
        raise MatrixError("inventory schema_version is unsupported")
    if inventory.get("artifact_kind") != "pinned_static_authority_edge_inventory":
        raise MatrixError("inventory artifact_kind is unsupported")
    require_object(inventory.get("inputs"), label="inventory.inputs")
    require_object(inventory.get("expected_edges"), label="inventory.expected_edges")
    require_object(inventory.get("row_state_counts"), label="inventory.row_state_counts")
    outcomes = require_object(inventory.get("outcomes"), label="inventory.outcomes")
    reject_unknown_keys(outcomes, {"inventory_integrity", "enumerated_decision_completeness", "semantic_closure"}, label="inventory.outcomes")
    require_list(inventory.get("rows"), label="inventory.rows")
    return inventory


def verify_inventory(
    raw_inventory: bytes,
    source: GitObjectReader,
    target: GitObjectReader,
    source_root: Path,
    target_root: Path,
    source_commit: str,
    source_tree: str,
    target_commit: str,
    target_tree: str,
    rules_path: str,
) -> dict[str, Any]:
    candidate = require_inventory_shape(strict_json_loads(raw_inventory, label="inventory"))
    if raw_inventory != canonical_json_bytes(candidate):
        raise MatrixError("inventory input is not canonical JSON bytes")
    expected = make_inventory(
        source,
        target,
        source_root,
        target_root,
        source_commit,
        source_tree,
        target_commit,
        target_tree,
        rules_path,
        enumeration=enumerate_for_verify,
    )
    candidate_rows = require_list(candidate.get("rows"), label="inventory.rows")
    candidate_keys: list[str] = []
    for index, row in enumerate(candidate_rows):
        row_object = require_object(row, label=f"inventory.rows[{index}]")
        candidate_keys.append(identity_key(require_object(row_object.get("identity"), label=f"inventory.rows[{index}].identity")))
    if len(candidate_keys) != len(set(candidate_keys)):
        raise MatrixError("inventory contains duplicate row identities")
    expected_keys = [identity_key(row["identity"]) for row in expected["rows"]]
    if set(candidate_keys) != set(expected_keys):
        missing = sorted(set(expected_keys) - set(candidate_keys))
        extra = sorted(set(candidate_keys) - set(expected_keys))
        detail = f"missing={len(missing)} extra={len(extra)}"
        raise MatrixError(f"inventory expected-edge set differs: {detail}")
    if canonical_json_bytes(candidate) != canonical_json_bytes(expected):
        raise MatrixError("inventory has substituted object evidence, decision, or derived summary")
    completion = expected["outcomes"]["enumerated_decision_completeness"]
    return {
        "schema_version": CHECK_SCHEMA_VERSION,
        "artifact_kind": "pinned_static_authority_edge_inventory_check",
        "inventory_sha256": sha256_bytes(raw_inventory),
        "inputs": expected["inputs"],
        "expected_edges": expected["expected_edges"],
        "row_state_counts": expected["row_state_counts"],
        "outcomes": {
            "inventory_integrity": "passed",
            "enumerated_decision_completeness": completion,
            "semantic_closure": "not_claimed",
        },
    }


class MatrixArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise UsageError(message)


def parser() -> MatrixArgumentParser:
    result = MatrixArgumentParser(description=__doc__, add_help=False)
    subparsers = result.add_subparsers(dest="command", required=True, parser_class=MatrixArgumentParser)
    for command in ("emit", "verify"):
        child = subparsers.add_parser(command, add_help=False)
        child.add_argument("--source-root", required=True)
        child.add_argument("--source-commit", required=True)
        child.add_argument("--source-tree", required=True)
        child.add_argument("--target-root", required=True)
        child.add_argument("--target-commit", required=True)
        child.add_argument("--target-tree", required=True)
        child.add_argument("--rules-repo-path", required=True)
        child.add_argument("--require-enumerated-decision-completeness", action="store_true")
        if command == "verify":
            child.add_argument("--inventory", required=True)
    return result


def failure_document(message: str) -> dict[str, Any]:
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "outcomes": {
            "inventory_integrity": "failed",
            "enumerated_decision_completeness": "blocked",
            "semantic_closure": "not_claimed",
        },
        "error": {"kind": "integrity", "message": message},
    }


def safe_error_message(exc: Exception) -> str:
    """Keep a secondary failure document serializable after hostile input."""

    try:
        message = str(exc)
        message.encode("utf-8", "strict")
    except Exception:
        return "integrity check failed"
    return message or "integrity check failed"


FALLBACK_FAILURE_BYTES = (
    b'{\n'
    b'  "error": {\n'
    b'    "kind": "integrity",\n'
    b'    "message": "integrity check failed"\n'
    b'  },\n'
    b'  "outcomes": {\n'
    b'    "enumerated_decision_completeness": "blocked",\n'
    b'    "inventory_integrity": "failed",\n'
    b'    "semantic_closure": "not_claimed"\n'
    b'  },\n'
    b'  "schema_version": "planveyor.contract_authority_matrix.result.v1"\n'
    b'}\n'
)


def run(argv: list[str]) -> tuple[int, dict[str, Any]]:
    args = parser().parse_args(argv)
    source_root = require_absolute_root(args.source_root, label="--source-root")
    target_root = require_absolute_root(args.target_root, label="--target-root")
    source_commit = require_full_oid(args.source_commit, label="--source-commit")
    source_tree = require_full_oid(args.source_tree, label="--source-tree")
    target_commit = require_full_oid(args.target_commit, label="--target-commit")
    target_tree = require_full_oid(args.target_tree, label="--target-tree")
    rules_path = require_repo_path(args.rules_repo_path, label="--rules-repo-path")
    source = GitObjectReader(source_root)
    target = GitObjectReader(target_root)
    source.verify_commit_tree(source_commit, source_tree, label="source")
    target.verify_commit_tree(target_commit, target_tree, label="target")
    if args.command == "emit":
        document = make_inventory(
            source,
            target,
            source_root,
            target_root,
            source_commit,
            source_tree,
            target_commit,
            target_tree,
            rules_path,
            enumeration=enumerate_for_emit,
        )
    else:
        inventory_path = require_absolute_root(args.inventory, label="--inventory")
        document = verify_inventory(
            inventory_path.read_bytes(),
            source,
            target,
            source_root,
            target_root,
            source_commit,
            source_tree,
            target_commit,
            target_tree,
            rules_path,
        )
    code = 3 if args.require_enumerated_decision_completeness and document["outcomes"]["enumerated_decision_completeness"] == "blocked" else 0
    return code, document


def main(argv: list[str] | None = None) -> int:
    try:
        code, document = run(sys.argv[1:] if argv is None else argv)
        payload = canonical_json_bytes(document)
    except Exception as exc:
        code = 2
        try:
            payload = canonical_json_bytes(failure_document(safe_error_message(exc)))
        except Exception:
            payload = FALLBACK_FAILURE_BYTES
    try:
        sys.stdout.buffer.write(payload)
    except OSError:
        return 2
    return code


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import re
import shlex
import subprocess
import sys
import textwrap
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

sys.dont_write_bytecode = True
sys.pycache_prefix = os.devnull



SCRIPT_DIR = Path(__file__).resolve().parent
_RUNTIME_SCRIPT_DIR_TEXT = str(SCRIPT_DIR)
while _RUNTIME_SCRIPT_DIR_TEXT in sys.path:
    sys.path.remove(_RUNTIME_SCRIPT_DIR_TEXT)
sys.path.insert(0, _RUNTIME_SCRIPT_DIR_TEXT)


def _module_origin_is(module: object, expected_path: Path) -> bool:
    module_file = getattr(module, "__file__", None)
    if not isinstance(module_file, str):
        return False
    try:
        return Path(module_file).resolve(strict=True) == expected_path
    except (OSError, RuntimeError, ValueError):
        return False


def _scripts_package_is_local() -> bool:
    package = sys.modules.get("scripts")
    if package is None:
        return True
    locations = getattr(package, "__path__", None)
    if locations is None:
        return False
    try:
        resolved_locations = tuple(Path(location).resolve(strict=True) for location in locations)
    except (OSError, RuntimeError, TypeError, ValueError):
        return False
    if not resolved_locations or any(path != SCRIPT_DIR for path in resolved_locations):
        return False
    package_file = getattr(package, "__file__", None)
    if package_file is not None and not _module_origin_is(package, SCRIPT_DIR / "__init__.py"):
        return False
    return True


def _runtime_sibling_module(direct_name: str) -> Any:
    """Load a sibling only when every package/direct spelling names this runtime."""

    expected_path = SCRIPT_DIR / f"{direct_name}.py"
    aliases = (f"scripts.{direct_name}", direct_name)
    package_is_local = _scripts_package_is_local()
    loaded = [sys.modules[name] for name in aliases if name in sys.modules]
    if any(not _module_origin_is(module, expected_path) for module in loaded):
        raise ImportError(f"preloaded {direct_name} is not from the bundle builder runtime")
    if len({id(module) for module in loaded}) > 1:
        raise ImportError(f"package and direct {direct_name} aliases disagree")
    module = loaded[0] if loaded else importlib.import_module(direct_name)
    if not _module_origin_is(module, expected_path):
        raise ImportError(f"{direct_name} must be loaded from the bundle builder runtime")
    packaged, direct = aliases
    existing_direct = sys.modules.get(direct)
    if existing_direct is not None and existing_direct is not module:
        raise ImportError(f"package and direct {direct_name} aliases disagree")
    sys.modules[direct] = module
    if package_is_local:
        existing_packaged = sys.modules.get(packaged)
        if existing_packaged is not None and existing_packaged is not module:
            raise ImportError(f"package and direct {direct_name} aliases disagree")
        sys.modules[packaged] = module
    return module


def _authority_module() -> Any:
    return _runtime_sibling_module("contract_authority_context")


_authority = _authority_module()
if TYPE_CHECKING:
    from contract_authority_context import (
        ContractAuthorityError,
        ContractContext,
        context_for_reader,
        context_to_json,
        read_declared_bytes,
        require_declared_read,
        resolve_top_level_context,
        validate_before_effect,
    )
else:
    ContractAuthorityError = _authority.ContractAuthorityError
    ContractContext = _authority.ContractContext
    context_for_reader = _authority.context_for_reader
    context_to_json = _authority.context_to_json
    read_declared_bytes = _authority.read_declared_bytes
    require_declared_read = _authority.require_declared_read
    resolve_top_level_context = _authority.resolve_top_level_context
    validate_before_effect = _authority.validate_before_effect


_authority_children = _runtime_sibling_module("contract_authority_children")
AuthorityChildLaunchError = _authority_children.AuthorityChildLaunchError
shell_command = _authority_children.shell_command


ROLE_IDS = ("architect", "planner", "coder", "reviewer")
SCHEMA_VERSION = "v1"
PATH_SUFFIX_RE = r"[^`'\"<>\s()\[\],;:!?]+"


class BuildError(RuntimeError):
    """Runtime/data error while assembling role bundles."""


@dataclass(frozen=True)
class ResolvedRef:
    home: str
    rel_path: str
    abs_path: Path


@dataclass(frozen=True)
class BundleContext:
    role: str
    repo_root: Path
    tooling_root: Path
    repo_profile_id: str
    content_profile_id: str
    prompt_ref: ResolvedRef
    role_doc_ref: ResolvedRef
    agents_ref: ResolvedRef
    architecture_ref: ResolvedRef
    plan_vocab_ref: ResolvedRef
    doc_classes_ref: ResolvedRef
    docs_index_ref: ResolvedRef | None
    repo_meta_refs: tuple[ResolvedRef, ...]
    prompt_text: str
    role_doc_text: str
    agents_text: str
    architecture_text: str
    plan_vocab: dict
    doc_classes: dict
    out_path: Path
    authority_context: ContractContext | None = None


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build deterministic XML runtime bundles for role init bootstrap.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--role", choices=ROLE_IDS, help="Build/check a single role bundle.")
    group.add_argument("--all", action="store_true", help="Build/check all supported role bundles.")
    parser.add_argument(
        "--out-dir",
        default=".tmp/role_bundles",
        help="Directory for generated XML bundles (default: .tmp/role_bundles).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Do not write files; fail if bundle is missing or stale.",
    )
    return parser.parse_args(argv)


def _normalize_rel(path: Path) -> str:
    return path.as_posix()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _runtime_source_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _resolve_tooling_root() -> Path:
    return _runtime_source_root()


def _resolve_repo_root() -> Path:
    configured_root = os.environ.get("PLANVEYOR_PROJECT_ROOT")
    if configured_root:
        try:
            return Path(configured_root).resolve(strict=True)
        except OSError as exc:
            raise BuildError(
                "PLANVEYOR_PROJECT_ROOT cannot be resolved for role bundle build"
            ) from exc
    return Path.cwd().resolve()


def _is_engaged(context: ContractContext | None) -> bool:
    return context is not None and context.state == "engaged"


def _reader_context(repo_root: Path, context: ContractContext | None) -> ContractContext:
    try:
        return context_for_reader(repo_root, context)
    except ContractAuthorityError as exc:
        raise BuildError(f"Contract authority reader context is invalid: {exc}") from exc


def _contract_relative_path(
    context: ContractContext,
    path: Path,
    *,
    purpose: str,
) -> str:
    try:
        return path.resolve(strict=False).relative_to(context.contract_root).as_posix()
    except ValueError as exc:
        raise BuildError(
            f"{purpose} is outside the engaged contract root: {path}"
        ) from exc


def _declared_ref(context: ContractContext, relative_path: str, *, purpose: str) -> ResolvedRef:
    try:
        path = require_declared_read(context, relative_path, purpose)
    except ContractAuthorityError as exc:
        raise BuildError(f"Cannot use declared {purpose}: {exc}") from exc
    return ResolvedRef(home="contract", rel_path=relative_path, abs_path=path)


def _read_declared_utf8(context: ContractContext, relative_path: str, *, purpose: str) -> str:
    try:
        data = read_declared_bytes(context, relative_path, purpose)
    except ContractAuthorityError as exc:
        raise BuildError(f"Cannot read declared {purpose}: {exc}") from exc
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BuildError(f"Declared {purpose} is not UTF-8: {relative_path}") from exc


def _resolve_runtime_launcher(tooling_root: Path) -> Path:
    """Return the sealed child launcher owned by this bundle-builder runtime.

    ``repo_root`` is the consumer project whose prompts are being resolved.  It
    must never select or source a shell implementation.  The launcher creates
    a clean child and binds the runtime together with the explicit consumer
    project.
    """

    try:
        runtime_root = tooling_root.resolve(strict=True)
    except OSError as exc:
        raise BuildError(f"Bundle builder runtime root cannot be resolved: {tooling_root}") from exc
    launcher = runtime_root / "bin" / "planveyor"
    if not launcher.is_file() or not os.access(launcher, os.X_OK):
        raise BuildError(f"Missing executable bundle builder runtime launcher: {launcher}")
    return launcher


def _shell_quote_paths(values: list[str]) -> str:
    return " ".join(shlex.quote(value) for value in values)


def _load_prompt_manifest(
    repo_root: Path,
    tooling_root: Path,
    roles: list[str],
    *,
    context: ContractContext | None = None,
) -> tuple[str, str, dict[str, Path]]:
    context = _reader_context(repo_root, context)
    repo_root = context.project_root
    if _is_engaged(context):
        assert context is not None
        runtime_pin = context.runtime_pin
        if runtime_pin is None:
            raise BuildError("Engaged bundle builder has no verified runtime pin")
        runtime_root = runtime_pin.runtime_root
        source_root = _runtime_source_root()
        if runtime_root != source_root:
            raise BuildError(
                "Engaged bundle builder runtime pin does not match its actual __file__ root"
            )
        configured_root = os.environ.get("PLANVEYOR_ROOT")
        if configured_root is not None:
            try:
                configured_path = Path(configured_root).resolve(strict=True)
            except OSError as exc:
                raise BuildError("PLANVEYOR_ROOT cannot be resolved for engaged bundle build") from exc
            if configured_path != runtime_root:
                raise BuildError(
                    "PLANVEYOR_ROOT does not match the engaged builder runtime pin"
                )
        bridge_script = runtime_root / "scripts" / "planveyor.zsh"
        if not bridge_script.is_file():
            raise BuildError(f"Missing verified runtime facade: {bridge_script}")
        cmd = textwrap.dedent(
            """
            cd "$1" || exit
            _planveyor_runtime_api_guard 5 5 || exit
            _planveyor_pre_dispatch planveyor_role_bundle_prompt_manifest >/dev/null || exit
            shift
            planveyor_role_bundle_prompt_manifest "$@"
            """
        ).strip()
        env = os.environ.copy()
        # The loader anchors runtime code, while the parent-supplied envelope
        # pins the target generation that was validated before this child was
        # constructed.  Do not inherit an ambient (possibly absent or stale)
        # assertion here.
        env["PLANVEYOR_ROOT"] = str(runtime_root)
        env["_PLANVEYOR_AUTHORITY_CONTEXT_V1"] = context_to_json(context)
        try:
            command = shell_command(context, cmd)
        except AuthorityChildLaunchError as exc:
            raise BuildError("Cannot build anchored prompt-manifest child") from exc
        command.extend(
            [
                "planveyor_role_bundle_prompt_manifest",
                str(context.project_root),
                *roles,
            ]
        )
    else:
        consumer_project = repo_root.resolve()
        launcher = _resolve_runtime_launcher(tooling_root)
        env = os.environ.copy()
        # The launcher owns the runtime seal and clears inherited runtime
        # state.  ``--project`` is the one explicit consumer binding.
        command = [
            str(launcher),
            "--project",
            str(consumer_project),
            "planveyor_role_bundle_prompt_manifest",
            *roles,
        ]
    proc = subprocess.run(
        command,
        text=True,
        capture_output=True,
        cwd=repo_root,
        env=env,
        check=False,
    )
    if proc.returncode != 0:
        raise BuildError(
            "Prompt manifest resolution failed via planveyor_role_bundle_prompt_manifest:\n"
            + (proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}")
        )

    repo_profile_id = "default"
    content_profile_id: str | None = None
    resolved: dict[str, Path] = {}
    for raw_line in proc.stdout.splitlines():
        if not raw_line.strip():
            continue
        key, sep, value = raw_line.partition("\t")
        if not sep:
            raise BuildError(f"Malformed prompt manifest line: {raw_line}")
        if key == "repo_profile_id":
            repo_profile_id = value.strip() or "default"
            continue
        if key == "content_profile_id":
            if content_profile_id is not None:
                raise BuildError("Prompt manifest contains duplicate content_profile_id rows")
            content_profile_id = value.strip()
            if not content_profile_id:
                raise BuildError("Prompt manifest has an empty content_profile_id")
            continue
        if key not in ROLE_IDS:
            raise BuildError(f"Unknown role in prompt manifest: {key}")
        resolved[key] = Path(value.strip()).resolve()

    missing = [role for role in roles if role not in resolved]
    if missing:
        raise BuildError(f"Prompt manifest missing roles: {', '.join(missing)}")
    if content_profile_id is None:
        raise BuildError("Prompt manifest is missing content_profile_id")
    if content_profile_id not in {"default", "planveyor", "target-local"}:
        raise BuildError(f"Prompt manifest has unsupported content_profile_id: {content_profile_id!r}")
    return repo_profile_id, content_profile_id, resolved


def _resolve_ref(raw_path: Path, *, repo_root: Path, tooling_root: Path, preferred_home: str | None = None) -> ResolvedRef:
    raw_path = raw_path.resolve()
    homes: list[tuple[str, Path]] = []
    if preferred_home == "tooling":
        homes = [("tooling", tooling_root), ("repo", repo_root)]
    elif preferred_home == "repo":
        homes = [("repo", repo_root), ("tooling", tooling_root)]
    else:
        homes = [("repo", repo_root), ("tooling", tooling_root)]

    for home_name, home_root in homes:
        try:
            rel = raw_path.relative_to(home_root)
            return ResolvedRef(home=home_name, rel_path=_normalize_rel(rel), abs_path=raw_path)
        except ValueError:
            continue
    raise BuildError(f"Path is outside repo/tooling homes: {raw_path}")


def _read_utf8(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise BuildError(f"Failed to read {path}: {exc}") from exc


def _load_json(path: Path) -> dict:
    try:
        return json.loads(_read_utf8(path))
    except json.JSONDecodeError as exc:
        raise BuildError(f"Invalid JSON in {path}: {exc}") from exc


def _extract_role_doc_relative_path(prompt_text: str) -> str:
    match = re.search(r"(docs/roles/[A-Za-z0-9_./-]+\.md)", prompt_text)
    if not match:
        raise BuildError("Resolved init prompt does not reference a role doc under docs/roles/*.md")
    return match.group(1)


def _extract_role_doc_ref(prompt_text: str, *, tooling_root: Path) -> Path:
    role_doc = (tooling_root / _extract_role_doc_relative_path(prompt_text)).resolve()
    if not role_doc.exists():
        raise BuildError(f"Referenced role doc is missing: {role_doc}")
    return role_doc


def _extract_section(text: str, candidates: tuple[str, ...]) -> tuple[str, str] | None:
    titles = tuple(candidate.strip().lower() for candidate in candidates)
    lines = text.splitlines()
    current_title: str | None = None
    current: list[str] = []
    for line in lines:
        if line.startswith("## "):
            title = line[3:].strip()
            normalized = title.lower()
            if current_title is not None:
                return current_title, "\n".join(current).strip()
            if any(normalized == wanted or normalized.startswith(wanted) for wanted in titles):
                current_title = title
                current = []
            continue
        if current_title is not None:
            current.append(line)
    if current_title is None:
        return None
    return current_title, "\n".join(current).strip()


def _collect_markdown_items(text: str, *, max_items: int = 12) -> list[str]:
    items: list[str] = []
    current: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if current is not None:
                items.append(current)
                current = None
            continue
        if re.match(r"^\[/?[A-Z_ ]+\]$", line):
            continue
        if line.startswith(">"):
            continue
        if line.startswith("```"):
            break
        if re.match(r"^[-*]\s+", line):
            if current is not None:
                items.append(current)
            current = re.sub(r"^[-*]\s+", "", line).strip()
            continue
        if re.match(r"^\d+(?:\.\d+)*\)\s+", line):
            if current is not None:
                items.append(current)
            current = re.sub(r"^\d+(?:\.\d+)*\)\s+", "", line).strip()
            continue
        if current is not None:
            current = f"{current} {line}".strip()
            continue
        items.append(line)
        if len(items) >= max_items:
            break

    if current is not None and len(items) < max_items:
        items.append(current)
    return items[:max_items]


def _arch_runtime_bundle_row(text: str) -> str | None:
    for line in text.splitlines():
        if line.startswith("| `runtime bundles` |"):
            parts = [part.strip() for part in line.strip().strip("|").split("|")]
            if len(parts) >= 8:
                return " | ".join(parts[1:6])
            return " | ".join(parts)
    return None


def _sanitize_item_text(text: str, *, repo_root: Path, tooling_root: Path) -> str:
    def sanitize_home(raw_text: str, *, home_name: str, home_root: Path) -> str:
        prefix = str(home_root.resolve())
        path_re = re.compile(
            rf"(?<![A-Za-z0-9_$}}:-])(?P<path>{re.escape(prefix)}(?:/{PATH_SUFFIX_RE})*)"
        )

        def repl(match: re.Match[str]) -> str:
            raw = match.group("path")
            rel = raw[len(prefix) :].lstrip("/")
            return home_name if not rel else f"{home_name}:{rel}"

        return path_re.sub(repl, raw_text)

    sanitized = sanitize_home(text, home_name="tooling", home_root=tooling_root)
    if repo_root.resolve() != tooling_root.resolve():
        sanitized = sanitize_home(sanitized, home_name="repo", home_root=repo_root)
    return sanitized


def _render_slice(
    parent: ET.Element,
    *,
    slice_id: str,
    title: str,
    items: list[str],
    source_ref: ResolvedRef,
    repo_root: Path,
    tooling_root: Path,
    anchor: str | None = None,
) -> None:
    if not items:
        return
    slice_el = ET.SubElement(parent, "bootstrap_slice", {"id": slice_id, "title": title})
    ref_attrs = {"home": source_ref.home, "path": source_ref.rel_path}
    if anchor:
        ref_attrs["anchor"] = anchor
    ET.SubElement(slice_el, "source_ref", ref_attrs)
    for idx, item in enumerate(items, start=1):
        item_el = ET.SubElement(slice_el, "item", {"seq": str(idx)})
        item_el.text = _sanitize_item_text(item, repo_root=repo_root, tooling_root=tooling_root)


def _load_declared_json(context: ContractContext, relative_path: str, *, purpose: str) -> dict:
    try:
        return json.loads(_read_declared_utf8(context, relative_path, purpose=purpose))
    except json.JSONDecodeError as exc:
        raise BuildError(f"Invalid JSON in declared {purpose}: {relative_path}: {exc}") from exc


def _build_context(
    role: str,
    *,
    repo_root: Path,
    tooling_root: Path,
    repo_profile_id: str,
    content_profile_id: str,
    prompt_path: Path,
    out_dir: Path,
    context: ContractContext | None = None,
) -> BundleContext:
    authority_context = _reader_context(repo_root, context)
    repo_root = authority_context.project_root
    if _is_engaged(authority_context):
        assert authority_context is not None
        prompt_relative = _contract_relative_path(
            authority_context,
            prompt_path,
            purpose="resolved init prompt",
        )
        prompt_ref = _declared_ref(
            authority_context,
            prompt_relative,
            purpose="resolved init prompt",
        )
        prompt_text = _read_declared_utf8(
            authority_context,
            prompt_relative,
            purpose="resolved init prompt",
        )

        role_doc_relative = _extract_role_doc_relative_path(prompt_text)
        role_doc_ref = _declared_ref(
            authority_context,
            role_doc_relative,
            purpose="role document",
        )
        role_doc_text = _read_declared_utf8(
            authority_context,
            role_doc_relative,
            purpose="role document",
        )

        agents_ref = _declared_ref(authority_context, "AGENTS.md", purpose="AGENTS.md")
        agents_text = _read_declared_utf8(authority_context, "AGENTS.md", purpose="AGENTS.md")

        architecture_relative = "docs/playbooks/docs_architecture.md"
        architecture_ref = _declared_ref(
            authority_context,
            architecture_relative,
            purpose="docs architecture",
        )
        architecture_text = _read_declared_utf8(
            authority_context,
            architecture_relative,
            purpose="docs architecture",
        )

        plan_vocab_relative = "docs/_meta/plan_vocab.json"
        doc_classes_relative = "docs/_meta/doc_classes.json"
        plan_vocab_ref = _declared_ref(
            authority_context,
            plan_vocab_relative,
            purpose="plan vocabulary",
        )
        doc_classes_ref = _declared_ref(
            authority_context,
            doc_classes_relative,
            purpose="document classes",
        )
        plan_vocab = _load_declared_json(
            authority_context,
            plan_vocab_relative,
            purpose="plan vocabulary",
        )
        doc_classes = _load_declared_json(
            authority_context,
            doc_classes_relative,
            purpose="document classes",
        )
    else:
        prompt_ref = _resolve_ref(prompt_path, repo_root=repo_root, tooling_root=tooling_root, preferred_home="tooling")
        prompt_text = _read_utf8(prompt_path)

        role_doc_path = _extract_role_doc_ref(prompt_text, tooling_root=tooling_root)
        role_doc_ref = _resolve_ref(role_doc_path, repo_root=repo_root, tooling_root=tooling_root, preferred_home="tooling")
        role_doc_text = _read_utf8(role_doc_path)

        agents_path = (repo_root / "AGENTS.md").resolve()
        if not agents_path.exists():
            raise BuildError(f"Missing AGENTS.md in repo root: {repo_root}")
        agents_ref = _resolve_ref(agents_path, repo_root=repo_root, tooling_root=tooling_root, preferred_home="repo")
        agents_text = _read_utf8(agents_path)

        # Both public source-local identities use the runtime's one public
        # corpus.  An engaged ``target-local`` identity took the declared
        # carrier branch above; legacy resolution must never recreate or guess
        # a profile subtree below the runtime.
        architecture_path = (tooling_root / "docs" / "playbooks" / "docs_architecture.md").resolve()
        architecture_ref = _resolve_ref(architecture_path, repo_root=repo_root, tooling_root=tooling_root, preferred_home="tooling")
        architecture_text = _read_utf8(architecture_path)

        plan_vocab_path = (tooling_root / "docs" / "_meta" / "plan_vocab.json").resolve()
        doc_classes_path = (tooling_root / "docs" / "_meta" / "doc_classes.json").resolve()
        plan_vocab_ref = _resolve_ref(plan_vocab_path, repo_root=repo_root, tooling_root=tooling_root, preferred_home="tooling")
        doc_classes_ref = _resolve_ref(doc_classes_path, repo_root=repo_root, tooling_root=tooling_root, preferred_home="tooling")
        plan_vocab = _load_json(plan_vocab_path)
        doc_classes = _load_json(doc_classes_path)

    docs_index_ref = None
    if _is_engaged(authority_context):
        docs_index_relative = ".tmp/planveyor_docs_index.sqlite"
        docs_index_path = repo_root / docs_index_relative
        if docs_index_path.is_file() and not docs_index_path.is_symlink():
            docs_index_ref = ResolvedRef(
                home="project",
                rel_path=docs_index_relative,
                abs_path=docs_index_path,
            )
    else:
        docs_index_path = (repo_root / ".tmp" / "planveyor_docs_index.sqlite").resolve()
        if docs_index_path.exists():
            docs_index_ref = _resolve_ref(docs_index_path, repo_root=repo_root, tooling_root=tooling_root, preferred_home="repo")

    repo_meta_refs: list[ResolvedRef] = []
    if not _is_engaged(authority_context) and repo_root != tooling_root:
        repo_meta_dir = repo_root / "docs" / "_meta"
        if repo_meta_dir.exists():
            for path in sorted(repo_meta_dir.glob("*.json")):
                repo_meta_refs.append(_resolve_ref(path, repo_root=repo_root, tooling_root=tooling_root, preferred_home="repo"))

    return BundleContext(
        role=role,
        repo_root=repo_root,
        tooling_root=tooling_root,
        repo_profile_id=repo_profile_id,
        content_profile_id=content_profile_id,
        prompt_ref=prompt_ref,
        role_doc_ref=role_doc_ref,
        agents_ref=agents_ref,
        architecture_ref=architecture_ref,
        plan_vocab_ref=plan_vocab_ref,
        doc_classes_ref=doc_classes_ref,
        docs_index_ref=docs_index_ref,
        repo_meta_refs=tuple(repo_meta_refs),
        prompt_text=prompt_text,
        role_doc_text=role_doc_text,
        agents_text=agents_text,
        architecture_text=architecture_text,
        plan_vocab=plan_vocab,
        doc_classes=doc_classes,
        out_path=out_dir / f"{role}.xml",
        authority_context=authority_context,
    )


def _ref_attrs(
    ref: ResolvedRef,
    *,
    authority_context: ContractContext | None = None,
    **extra: str,
) -> dict[str, str]:
    if _is_engaged(authority_context) and ref.home == "contract":
        assert authority_context is not None
        try:
            digest = _sha256_bytes(
                read_declared_bytes(
                    authority_context,
                    ref.rel_path,
                    "role bundle source reference",
                )
            )
        except ContractAuthorityError as exc:
            raise BuildError(f"Cannot revalidate declared bundle source {ref.rel_path}: {exc}") from exc
    else:
        digest = _sha256_file(ref.abs_path)
    attrs = {"home": ref.home, "path": ref.rel_path, "sha256": digest}
    attrs.update(extra)
    return attrs


def _bundle_xml_bytes(ctx: BundleContext) -> bytes:
    root = ET.Element(
        "role_bundle",
        {
            "role": ctx.role,
            "schema_version": SCHEMA_VERSION,
            "consumer_phase": "init",
            "repo_profile_id": ctx.repo_profile_id,
            "content_profile_id": ctx.content_profile_id,
        },
    )

    meta = ET.SubElement(root, "meta")
    ET.SubElement(meta, "runtime_home", {"path": f".tmp/role_bundles/{ctx.role}.xml"})
    ET.SubElement(meta, "builder", {"home": "tooling", "path": "scripts/build_role_bundles.py"})
    ET.SubElement(meta, "prompt_resolution_bridge", {"helper": "planveyor_role_bundle_prompt_manifest"})
    if _is_engaged(ctx.authority_context):
        assert ctx.authority_context is not None
        ET.SubElement(
            meta,
            "authority_context",
            {
                "state": "engaged",
                "project_root": str(ctx.authority_context.project_root),
                "contract_root": str(ctx.authority_context.contract_root),
                "behavior_identity": ctx.authority_context.behavior_identity,
                "generation_sha256": ctx.authority_context.generation_sha256,
            },
        )
    ET.SubElement(meta, "prompt_ref", _ref_attrs(ctx.prompt_ref, authority_context=ctx.authority_context))

    source_refs = ET.SubElement(root, "source_refs")
    ET.SubElement(
        source_refs,
        "source_ref",
        _ref_attrs(ctx.agents_ref, authority_context=ctx.authority_context, anchor="Базовые правила"),
    )
    ET.SubElement(source_refs, "source_ref", _ref_attrs(ctx.role_doc_ref, authority_context=ctx.authority_context))
    ET.SubElement(source_refs, "source_ref", _ref_attrs(ctx.prompt_ref, authority_context=ctx.authority_context))
    ET.SubElement(
        source_refs,
        "source_ref",
        _ref_attrs(ctx.architecture_ref, authority_context=ctx.authority_context, anchor="4-layer model"),
    )

    control_plane_refs = ET.SubElement(root, "control_plane_refs")
    ET.SubElement(
        control_plane_refs,
        "control_plane_ref",
        _ref_attrs(ctx.plan_vocab_ref, authority_context=ctx.authority_context),
    )
    ET.SubElement(
        control_plane_refs,
        "control_plane_ref",
        _ref_attrs(ctx.doc_classes_ref, authority_context=ctx.authority_context),
    )

    derived_refs = ET.SubElement(root, "derived_refs")
    if ctx.docs_index_ref is not None:
        if _is_engaged(ctx.authority_context):
            ET.SubElement(
                derived_refs,
                "derived_ref",
                {
                    "home": "project",
                    "path": ctx.docs_index_ref.rel_path,
                    "kind": "docs_index",
                    "authority": "non_authoritative",
                },
            )
        else:
            ET.SubElement(derived_refs, "derived_ref", _ref_attrs(ctx.docs_index_ref, kind="docs_index"))
    for ref in ctx.repo_meta_refs:
        ET.SubElement(derived_refs, "derived_ref", _ref_attrs(ref, kind="repo_meta"))

    payload = ET.SubElement(root, "bundle_payload")

    runtime_items = [
        "Bundle is generated-only runtime context; it does not replace AGENTS.md, role docs, or the init prompt.",
        "Wrapper contract is best-effort: if refresh/check fails, raw-doc bootstrap continues and stale ROLE_BUNDLE_PATH must not leak.",
        f"Resolved init prompt for this role is {ctx.prompt_ref.home}:{ctx.prompt_ref.rel_path}.",
    ]
    _render_slice(
        payload,
        slice_id="runtime_contract",
        title="Runtime bundle contract",
        items=runtime_items,
        source_ref=ctx.architecture_ref,
        repo_root=ctx.repo_root,
        tooling_root=ctx.tooling_root,
        anchor="4-layer model",
    )

    prompt_items = _collect_markdown_items(ctx.prompt_text, max_items=10)
    _render_slice(
        payload,
        slice_id="init_prompt",
        title="Init prompt pointers",
        items=prompt_items,
        source_ref=ctx.prompt_ref,
        repo_root=ctx.repo_root,
        tooling_root=ctx.tooling_root,
        anchor="ALWAYS START",
    )

    source_of_truth = _extract_section(ctx.role_doc_text, ("Source of truth / precedence (если есть конфликт)",))
    if source_of_truth is not None:
        heading, body = source_of_truth
        _render_slice(
            payload,
            slice_id="source_of_truth",
            title=heading,
            items=_collect_markdown_items(body, max_items=10),
            source_ref=ctx.role_doc_ref,
            repo_root=ctx.repo_root,
            tooling_root=ctx.tooling_root,
            anchor=heading,
        )

    boundaries = _extract_section(
        ctx.role_doc_text,
        (
            "Границы роли (жёстко)",
            "Profile-specific architect contract",
            "Profile-specific planner contract",
            "Stack-specific contract",
            "Stack-specific review contract",
        ),
    )
    if boundaries is not None:
        heading, body = boundaries
        _render_slice(
            payload,
            slice_id="role_contract",
            title=heading,
            items=_collect_markdown_items(body, max_items=12),
            source_ref=ctx.role_doc_ref,
            repo_root=ctx.repo_root,
            tooling_root=ctx.tooling_root,
            anchor=heading,
        )

    bootstrap = _extract_section(ctx.role_doc_text, ("Обязательный старт (session bootstrap; 1 раз на role",))
    if bootstrap is not None:
        heading, body = bootstrap
        _render_slice(
            payload,
            slice_id="session_bootstrap",
            title=heading,
            items=_collect_markdown_items(body, max_items=12),
            source_ref=ctx.role_doc_ref,
            repo_root=ctx.repo_root,
            tooling_root=ctx.tooling_root,
            anchor=heading,
        )

    purpose_section = _extract_section(ctx.architecture_text, ("Purpose",))
    architecture_items: list[str] = []
    if purpose_section is not None:
        _, body = purpose_section
        architecture_items.extend(_collect_markdown_items(body, max_items=6))
    runtime_row = _arch_runtime_bundle_row(ctx.architecture_text)
    if runtime_row is not None:
        architecture_items.append(f"Runtime-bundles row: {runtime_row}")
    _render_slice(
        payload,
        slice_id="docs_layers",
        title="Docs layer model pointers",
        items=architecture_items[:8],
        source_ref=ctx.architecture_ref,
        repo_root=ctx.repo_root,
        tooling_root=ctx.tooling_root,
        anchor="4-layer model",
    )

    status_count = len(ctx.plan_vocab.get("plan_statuses", {}).get("canonical", []))
    doc_classes = [
        str(item.get("label", "")).strip()
        for item in ctx.doc_classes.get("classes", [])
        if str(item.get("label", "")).strip()
    ]
    control_items = [
        f"Canonical plan statuses available: {status_count}.",
        f"Doc classes available: {', '.join(doc_classes)}.",
        "Control-plane manifests stay in JSON; runtime bundles stay generated-only XML.",
    ]
    _render_slice(
        payload,
        slice_id="control_plane_summary",
        title="Control-plane summary",
        items=control_items,
        source_ref=ctx.plan_vocab_ref,
        repo_root=ctx.repo_root,
        tooling_root=ctx.tooling_root,
        anchor="plan_statuses",
    )

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _write_or_check(ctx: BundleContext, *, check: bool) -> tuple[bool, str]:
    xml_bytes = _bundle_xml_bytes(ctx)
    path = ctx.out_path
    if check:
        if not path.exists():
            return False, f"MISSING {path}"
        existing = path.read_bytes()
        if existing != xml_bytes:
            return False, f"STALE {path}"
        return True, f"OK {path}"

    if _is_engaged(ctx.authority_context):
        assert ctx.authority_context is not None
        try:
            validate_before_effect(ctx.authority_context)
        except ContractAuthorityError as exc:
            raise BuildError(f"Contract authority changed before bundle output: {exc}") from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    if _is_engaged(ctx.authority_context):
        assert ctx.authority_context is not None
        try:
            validate_before_effect(ctx.authority_context)
        except ContractAuthorityError as exc:
            raise BuildError(f"Contract authority changed before bundle write: {exc}") from exc
    previous = path.read_bytes() if path.exists() else None
    if previous == xml_bytes:
        return True, f"UNCHANGED {path}"
    path.write_bytes(xml_bytes)
    return True, f"WROTE {path}"


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    roles = [args.role] if args.role else list(ROLE_IDS)
    repo_root = _resolve_repo_root()
    tooling_root = _resolve_tooling_root()
    out_dir = Path(args.out_dir).expanduser()
    if not out_dir.is_absolute():
        out_dir = (repo_root / out_dir).resolve()

    try:
        authority_context = resolve_top_level_context(
            repo_root,
            runtime_root=_runtime_source_root(),
        )
        repo_profile_id, content_profile_id, prompt_manifest = _load_prompt_manifest(
            repo_root,
            tooling_root,
            roles,
            context=authority_context,
        )
        if content_profile_id == "target-local" and not _is_engaged(authority_context):
            raise BuildError(
                "target-local role bundles require an engaged consumer contract"
            )
        contexts = [
            _build_context(
                role,
                repo_root=repo_root,
                tooling_root=tooling_root,
                repo_profile_id=repo_profile_id,
                content_profile_id=content_profile_id,
                prompt_path=prompt_manifest[role],
                out_dir=out_dir,
                context=authority_context,
            )
            for role in roles
        ]
        results = [_write_or_check(ctx, check=bool(args.check)) for ctx in contexts]
    except (BuildError, ContractAuthorityError) as exc:
        print(str(exc), file=sys.stderr)
        return 3

    ok = True
    for success, line in results:
        print(line)
        ok = ok and success
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

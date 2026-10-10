#!/usr/bin/env python3
"""Collect loop-aware process-improvement suggestions into durable backlog files."""

from __future__ import annotations

import argparse
import contextlib
import difflib
import hashlib
import importlib
import json
import os
import re
import stat
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

sys.dont_write_bytecode = True
sys.pycache_prefix = os.devnull



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
    return package_file is None or _module_has_expected_origin(
        package, _AUTHORITY_SCRIPTS_DIR / "__init__.py"
    )


def _assert_authority_alias_origin(module: object | None, expected: Path) -> None:
    if module is not None and not _module_has_expected_origin(module, expected):
        raise ImportError("authority module has an unsafe origin")


def _load_authority_context() -> Any:
    """Load only the exact sibling context module under either import spelling."""

    package_name = "scripts.contract_authority_context"
    direct_name = "contract_authority_context"
    package_is_local = _scripts_package_is_local()
    expected = _AUTHORITY_SCRIPTS_DIR / f"{direct_name}.py"
    direct = sys.modules.get(direct_name)
    packaged = sys.modules.get(package_name)
    _assert_authority_alias_origin(direct, expected)
    _assert_authority_alias_origin(packaged, expected)
    if direct is not None and packaged is not None and direct is not packaged:
        raise ImportError("authority module aliases are split")
    module = direct or packaged
    if module is None:
        script_dir = os.fspath(_AUTHORITY_SCRIPTS_DIR)
        if script_dir in sys.path:
            sys.path.remove(script_dir)
        sys.path.insert(0, script_dir)
        module = importlib.import_module(direct_name)
        _assert_authority_alias_origin(module, expected)
    sys.modules[direct_name] = module
    if package_is_local:
        sys.modules[package_name] = module
    return module


authority_context = _load_authority_context()

if TYPE_CHECKING:
    from contract_authority_context import ContractContext
else:
    ContractContext = Any


PROCESS_IMPROVEMENTS_DIR = Path("docs/process_improvements")
CAPTURE_RECEIPT_DIR = Path(".tmp/process_improvements_capture")
CAPTURE_RECEIPT_V1_SCHEMA = "process_improvement_capture.v1"
CAPTURE_RECEIPT_V2_SCHEMA = "process_improvement_capture.v2"
PROCESS_TEMPLATE_PATH = PROCESS_IMPROVEMENTS_DIR / "_template_process_improvements_backlog.md"
INDEX_PATH = PROCESS_IMPROVEMENTS_DIR / "index.md"
DEFERRED_PATH = PROCESS_IMPROVEMENTS_DIR / "deferred.md"
PROMOTION_PATH = PROCESS_IMPROVEMENTS_DIR / "promotion_surface.md"
CORE_DOC_NAMES = {
    "README.md",
    "_template_process_improvements_backlog.md",
    "index.md",
    "deferred.md",
    "promotion_surface.md",
}
ENTRY_FIELD_ORDER = (
    "status",
    "priority",
    "role",
    "owner",
    "promotion_class",
    "target_canon_path",
    "target_repo_scope",
    "delivery_mode",
    "execution_kind",
    "execution_ref",
    "delivery_refs",
    "handled_ref",
    "promoted_at",
    "handled_at",
    "trigger_ref",
    "source_ref",
    "symptom",
    "process_gap",
    "suggested_fix",
    "created_at",
    "triage_note",
)
NO_PROCESS_IMPROVEMENT_REASONS = {
    "clean_run",
    "already_tracked",
    "out_of_scope",
    "deferred_pending_data",
}
PROMOTION_CLASSES = {
    "canon_update",
    "prompt_change",
    "helper_change",
    "routing_change",
    "followup_plan",
}
PROMOTION_CLASS_ALIASES = {
    "template_change": "canon_update",
    "template_update": "canon_update",
    "runbook_change": "canon_update",
    "gate_change": "canon_update",
}
# A target-bearing process-improvement row names one literal consumer repo.
# The parser does not maintain a source-side consumer registry: packetization
# validates the exact target and carrier later. ``multi_repo`` remains the one
# explicit non-literal scope so the gate can fail it closed. Its underscore
# spelling is deliberately distinct from the literal repo id ``multi-repo``.
TARGET_REPO_SCOPE_RESERVED = {"multi_repo"}
TARGET_REPO_SCOPE_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DELIVERY_MODES = {
    "source_only",
    "source_plus_rollout",
    "packet_only",
    "umbrella_mixed",
}
EXECUTION_KINDS = {
    "plan",
    "helper",
    "canon_doc",
    "rollout_packet",
    "umbrella_wave",
    "external_ref",
}
ALLOWED_ROLES = {
    "Architect",
    "Planner",
    "Coder",
    "Reviewer",
    "Manager",
    "Owner",
}
GENERAL_CAPTURE_ROLES = ("Architect", "Coder", "Planner", "Reviewer")
CAPTURE_STATE_VALUES = {
    "clean_noop",
    "materialized",
    "already_tracked",
    "blocked",
}
CAPTURE_CONTINUATION_STATES = {"clean_noop", "materialized", "already_tracked"}
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
ALLOWED_STATUSES = {
    "open",
    "triaged",
    "deferred",
    "promoted",
    "rejected",
    "handled",
    "unconfirmed",
}
ALLOWED_PRIORITIES = {"P0", "P1", "P2", "P?"}
DEFERRED_STATUSES = {"open", "deferred", "unconfirmed"}
PROMOTION_SURFACE_STATUSES = ALLOWED_STATUSES

PROCESS_SECTION_HEADING_RE = re.compile(r"^\s*##+\s+(?:\d+[.)]\s*)?Process improvements\b", re.IGNORECASE)
H2_RE = re.compile(r"^\s*##\s+")
H3_RE = re.compile(r"^\s*###\s+(?P<title>.+?)\s*$")
FIELD_RE = re.compile(r"^\s*-\s*(?P<key>[a-z_]+)\s*:\s*(?P<value>.+?)\s*$", re.IGNORECASE)
PROCESS_FIELD_RE = re.compile(r"^\s*(?:-\s*)?(?P<key>[a-z_]+)\s*:\s*(?P<value>.+?)\s*$", re.IGNORECASE)
NO_PROCESS_RE = re.compile(
    r"^\s*(?:[-*]\s+)?NO PROCESS IMPROVEMENTS\s*(?:—|–|-)\s*why:\s*(?P<reason>[a-z_]+)\s*$"
)
ENTRY_ID_RE = re.compile(r"^PI-(?P<number>\d{3})$")
SOURCE_REF_RE = re.compile(r"^\s*\*\*Source ref:\*\*\s*(?P<value>.+?)\s*$")
SUGGESTIONS_HEADING_RE = re.compile(r"^\s*##\s+Suggestions\b", re.IGNORECASE)
IMPORT_HEADER_FIELD_RE = re.compile(r"^\s*\*\*(?P<key>[A-Za-z ]+):\*\*\s*(?P<value>.+?)\s*$")
IMPORT_SUGGESTION_HEADING_RE = re.compile(
    r"^\s*#{2,3}\s+(?:Suggestion|Предложение)(?:\b|\s|$)",
    re.IGNORECASE,
)

INDEX_AUTO_START = "<!-- AUTO-PROCESS-INDEX:START -->"
INDEX_AUTO_END = "<!-- AUTO-PROCESS-INDEX:END -->"
DEFERRED_AUTO_START = "<!-- AUTO-PROCESS-DEFERRED:START -->"
DEFERRED_AUTO_END = "<!-- AUTO-PROCESS-DEFERRED:END -->"
PROMOTION_AUTO_START = "<!-- AUTO-PROCESS-PROMOTION:START -->"
PROMOTION_AUTO_END = "<!-- AUTO-PROCESS-PROMOTION:END -->"
PROCESS_TIMESTAMP_LINE_RE = re.compile(
    r"^_Auto-generated by `scripts/process_improvements_collect\.py` on .+\._$"
)
PROCESS_TIMESTAMP_PLACEHOLDER = (
    "_Auto-generated by `scripts/process_improvements_collect.py` on <timestamp>._"
)
PROCESS_DERIVED_BANNER_LINE = (
    "_DO NOT EDIT - производная поверхность; обновление через разрешённый "
    "PI/docs-closeout workflow: `docs/tools/prompts/manager_collab_pipeline.md`. "
    "Standalone `--rebuild-derived` недоступен при engaged authority._"
)
_LEGACY_PROCESS_DERIVED_BANNER_LINE = (
    "_DO NOT EDIT - regenerate via `PYTHONDONTWRITEBYTECODE=1 "
    "python3 -B scripts/process_improvements_collect.py --project-root . "
    "--rebuild-derived`._"
)
PROCESS_OUTPUT_FIELD_NAMES = {
    "symptom",
    "process_gap",
    "suggested_fix",
    "owner",
    "promotion_class",
    "trigger_ref",
    "source_ref",
}


@dataclass(frozen=True)
class ParsedSuggestion:
    role: str
    owner: str
    promotion_class: str
    trigger_ref: str
    source_ref: str
    symptom: str
    process_gap: str
    suggested_fix: str


@dataclass(frozen=True)
class ImportedSuggestion:
    role: str
    owner: str
    promotion_class: str
    trigger_ref: str
    original_source_ref: str
    symptom: str
    process_gap: str
    suggested_fix: str
    extra_note: str


@dataclass(frozen=True)
class ImportedProcessImprovementFile:
    source_path: Path
    source_ref: str
    source_status: str
    source_plan_ref: str
    source_label: str
    source_date: str
    suggestions: tuple[ImportedSuggestion, ...]


@dataclass(frozen=True)
class BacklogEntry:
    entry_id: str
    status: str
    priority: str
    role: str
    owner: str
    promotion_class: str
    target_canon_path: str
    target_repo_scope: str
    delivery_mode: str
    execution_kind: str
    execution_ref: str
    delivery_refs: str
    handled_ref: str
    promoted_at: str
    handled_at: str
    trigger_ref: str
    source_ref: str
    symptom: str
    process_gap: str
    suggested_fix: str
    created_at: str
    triage_note: str


@dataclass(frozen=True)
class BacklogFile:
    path: Path
    source_ref: str
    entries: tuple[BacklogEntry, ...]


@dataclass(frozen=True)
class TriageCarrierIssue:
    entry_id: str
    status: str
    field: str
    code: str
    message: str


def _now_local() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %z")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _private_writer_context(
    project_root: Path,
    context: ContractContext | None = None,
) -> ContractContext:
    """Bind a private-delivery writer to one context before it reads or writes."""

    writer_context = authority_context.context_for_reader(project_root, context)
    if writer_context.state == "engaged":
        raise authority_context.ContractAuthorityError(
            "engaged_private_delivery_unsupported",
            "process-improvements writers are unavailable in engaged authority",
        )
    return writer_context


def _load_capture_admission_module() -> Any:
    """Load the exact sibling capture module for the one public CLI admission."""

    expected = _AUTHORITY_SCRIPTS_DIR / "followups_capture.py"
    if __name__ == "__main__":
        current = sys.modules[__name__]
        existing = sys.modules.get("process_improvements_collect")
        if existing is None:
            # ``followups_capture`` imports this module directly.  Bind the
            # executing CLI module before that local import so it cannot create
            # a second collector module with divergent globals.
            sys.modules["process_improvements_collect"] = current
        elif existing is not current:
            raise ImportError("process-improvements collector module aliases are split")
    module = sys.modules.get("followups_capture")
    if module is not None and not _module_has_expected_origin(module, expected):
        raise ImportError("followups capture module has an unsafe origin")
    if module is None:
        module = importlib.import_module("followups_capture")
    if not _module_has_expected_origin(module, expected):
        raise ImportError("followups capture module has an unsafe origin")
    return module


def _general_collection_writer_context(
    project_root: Path,
    *,
    role: str,
    source_ref: str,
    followups_capture_cycle_id: str | None,
    context: ContractContext | None,
) -> tuple[ContractContext, bool, dict[str, object] | None]:
    """Admit the one engaged public CLI collector route before input is read."""

    writer_context = authority_context.context_for_reader(project_root, context)
    if writer_context.state != "engaged":
        return writer_context, False, None
    normalized_cycle_id = _normalize_followups_capture_cycle_id(followups_capture_cycle_id)
    if normalized_cycle_id is None:
        raise authority_context.ContractAuthorityError(
            "engaged_private_delivery_unsupported",
            "engaged process-improvement collection requires one exact capture cycle",
        )
    normalized_role = _normalize_role(role, field_name="role")
    normalized_source_ref = _normalize_ref(source_ref, field_name="source_ref")
    capture = _load_capture_admission_module()
    admission = capture.admit_active_general_pi_collection(
        project_root,
        normalized_source_ref,
        normalized_cycle_id,
        normalized_role,
    )
    return writer_context, True, admission


def _validate_active_general_pi_effect(
    project_root: Path,
    *,
    context: ContractContext | None,
    admission: dict[str, object] | None,
) -> None:
    """Fence a public collector effect with the exact admission that read stdin."""

    _validate_writer_effect(context)
    if admission is None:
        return
    capture = _load_capture_admission_module()
    refreshed = capture.admit_active_general_pi_collection(
        project_root,
        str(admission["plan_ref"]),
        str(admission["capture_cycle_id"]),
        str(admission["role"]),
    )
    fields = (
        "plan_ref",
        "capture_cycle_id",
        "role",
        "receipt_revision",
        "receipt_object_identity",
    )
    if tuple(refreshed.get(field) for field in fields) != tuple(admission.get(field) for field in fields):
        raise capture.CaptureError(
            "followup_capture_pi_general_collection_admission_drift",
            "general PI collection admission changed before an effect",
        )


def _validate_writer_effect(context: ContractContext | None) -> None:
    if context is not None:
        authority_context.validate_before_effect(context)


def _write_text(
    path: Path,
    text: str,
    *,
    context: ContractContext | None = None,
) -> None:
    _validate_writer_effect(context)
    path.parent.mkdir(parents=True, exist_ok=True)
    _validate_writer_effect(context)
    path.write_text(text, encoding="utf-8")


def resolve_project_root(raw: str | None) -> Path:
    root = Path(raw).expanduser() if raw else Path.cwd()
    return root.resolve()


def _receipt_slug(source_ref: str) -> str:
    source_name = Path(source_ref).stem if "/" in source_ref else source_ref.strip()
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", source_name).strip("_") or "source"
    digest = hashlib.sha256(source_ref.encode("utf-8")).hexdigest()[:12]
    return f"{digest}_{slug[:80]}"


def capture_receipt_rel_path(
    source_ref: str,
    role: str,
    followups_capture_cycle_id: str | None = None,
) -> Path:
    """Return the disjoint legacy-v1 or exact-cycle-v2 receipt location."""
    normalized_role = _normalize_role(role, field_name="role").lower()
    if followups_capture_cycle_id is None:
        return CAPTURE_RECEIPT_DIR / _receipt_slug(source_ref) / f"{normalized_role}.json"
    cycle_id = _normalize_followups_capture_cycle_id(followups_capture_cycle_id)
    assert cycle_id is not None
    return CAPTURE_RECEIPT_DIR / _receipt_slug(source_ref) / cycle_id / f"{normalized_role}.json"


def capture_receipt_dir_rel_path(source_ref: str, followups_capture_cycle_id: str | None = None) -> Path:
    directory = CAPTURE_RECEIPT_DIR / _receipt_slug(source_ref)
    if followups_capture_cycle_id is None:
        return directory
    cycle_id = _normalize_followups_capture_cycle_id(followups_capture_cycle_id)
    assert cycle_id is not None
    return directory / cycle_id


def _capture_state_from_payload(payload: dict[str, object]) -> tuple[str, str]:
    state = str(payload.get("state") or "blocked")
    if state == "no_process_improvements":
        reason = str(payload.get("reason_code") or "unknown")
        if reason == "already_tracked":
            return "already_tracked", reason
        return "clean_noop", reason
    if state == "collected":
        created = payload.get("created") or []
        duplicates = payload.get("duplicates") or []
        if created:
            return "materialized", "structured_suggestions_materialized"
        if duplicates:
            return "already_tracked", "duplicate_backlog_entries"
        return "blocked", "structured_suggestions_without_carrier"
    return "blocked", f"unsupported_collect_state:{state}"


def _capture_backlog_paths(payload: dict[str, object]) -> list[str]:
    paths: set[str] = set()
    for key in ("backlog_files",):
        for raw in payload.get(key) or []:
            if isinstance(raw, str) and raw.strip():
                paths.add(raw.strip())
    for key in ("created", "duplicates"):
        for item in payload.get(key) or []:
            if isinstance(item, dict):
                raw = item.get("file")
                if isinstance(raw, str) and raw.strip():
                    paths.add(raw.strip())
    return sorted(paths)


def _capture_pi_data_paths(source_ref: str) -> list[str]:
    return sorted(
        {
            backlog_rel_path_for_source_ref(source_ref),
            INDEX_PATH.as_posix(),
            DEFERRED_PATH.as_posix(),
            PROMOTION_PATH.as_posix(),
        }
    )


def _capture_pi_object_map(project_root: Path, source_ref: str) -> dict[str, dict[str, object]]:
    """Return exact regular-file identities for PI data that one lane can mutate."""
    objects: dict[str, dict[str, object]] = {}
    for rel_path in _capture_pi_data_paths(source_ref):
        path = project_root / rel_path
        try:
            before = path.lstat()
        except FileNotFoundError:
            continue
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"process-improvement capture path must be a regular file: {rel_path}")
        data = path.read_bytes()
        after = path.lstat()
        if not stat.S_ISREG(after.st_mode) or before.st_dev != after.st_dev or before.st_ino != after.st_ino:
            raise ValueError(f"process-improvement capture path changed while reading: {rel_path}")
        if len(data) != after.st_size:
            raise ValueError(f"process-improvement capture path size changed while reading: {rel_path}")
        objects[rel_path] = {
            "sha256": hashlib.sha256(data).hexdigest(),
            "file_type": "regular",
            "st_size": after.st_size,
        }
    return {path: objects[path] for path in sorted(objects)}


def _safe_pi_parts(rel_path: str) -> tuple[str, ...]:
    path = Path(rel_path)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"invalid engaged process-improvement path: {rel_path!r}")
    return path.parts


def _collector_stat_identity(observed: os.stat_result) -> tuple[int, int, int]:
    return observed.st_dev, observed.st_ino, stat.S_IFMT(observed.st_mode)


def _collector_regular_fingerprint(observed: os.stat_result) -> tuple[int, int, int, int, int, int]:
    """Return stable regular-leaf attributes that an atomic collector operation pins."""

    return (
        observed.st_dev,
        observed.st_ino,
        observed.st_mode,
        observed.st_size,
        observed.st_mtime_ns,
        observed.st_ctime_ns,
    )


def _collector_open_root(project_root: Path) -> tuple[int, tuple[int, int, int]]:
    """Pin the public collector to the declared project root directory."""

    try:
        before = os.stat(project_root, follow_symlinks=False)
    except OSError as exc:
        raise ValueError("cannot inspect engaged process-improvement project root") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISDIR(before.st_mode):
        raise ValueError("engaged process-improvement project root is unsafe")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        root_fd = os.open(project_root, flags)
    except OSError as exc:
        raise ValueError("cannot open engaged process-improvement project root") from exc
    try:
        opened = os.fstat(root_fd)
        after = os.stat(project_root, follow_symlinks=False)
        identity = _collector_stat_identity(before)
        if (
            not stat.S_ISDIR(opened.st_mode)
            or _collector_stat_identity(opened) != identity
            or _collector_stat_identity(after) != identity
        ):
            raise ValueError("engaged process-improvement project root changed while opening")
        return root_fd, identity
    except Exception:
        os.close(root_fd)
        raise


def _collector_validate_anchor(
    project_root: Path,
    *,
    root_fd: int,
    root_identity: tuple[int, int, int],
    links: tuple[tuple[int, str, tuple[int, int, int]], ...],
) -> None:
    """Reject a path substitution after one of its ancestors was opened."""

    try:
        current_root = os.stat(project_root, follow_symlinks=False)
    except OSError as exc:
        raise ValueError("engaged process-improvement project root changed while using it") from exc
    if (
        _collector_stat_identity(os.fstat(root_fd)) != root_identity
        or _collector_stat_identity(current_root) != root_identity
    ):
        raise ValueError("engaged process-improvement project root changed while using it")
    for parent_fd, name, expected in links:
        try:
            observed = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except OSError as exc:
            raise ValueError(f"engaged process-improvement ancestor changed while using it: {name}") from exc
        if not stat.S_ISDIR(observed.st_mode) or _collector_stat_identity(observed) != expected:
            raise ValueError(f"engaged process-improvement ancestor changed while using it: {name}")


@contextlib.contextmanager
def _collector_directory(
    project_root: Path,
    parts: tuple[str, ...],
    *,
    create: bool,
    context: ContractContext | None,
    active_admission: dict[str, object] | None = None,
) -> Any:
    """Yield a descriptor-anchored directory below the fixed project root."""

    root_fd, root_identity = _collector_open_root(project_root)
    fds = [root_fd]
    links: list[tuple[int, str, tuple[int, int, int]]] = []
    try:
        for name in parts:
            parent_fd = fds[-1]
            try:
                before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                if not create:
                    yield None
                    return
                _collector_validate_anchor(
                    project_root,
                    root_fd=root_fd,
                    root_identity=root_identity,
                    links=tuple(links),
                )
                _validate_active_general_pi_effect(
                    project_root,
                    context=context,
                    admission=active_admission,
                )
                try:
                    os.mkdir(name, 0o777, dir_fd=parent_fd)
                except FileExistsError:
                    pass
                except OSError as exc:
                    raise ValueError(f"cannot create engaged process-improvement directory: {name}") from exc
                try:
                    before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                except OSError as exc:
                    raise ValueError(f"cannot inspect engaged process-improvement directory: {name}") from exc
            except OSError as exc:
                raise ValueError(f"cannot inspect engaged process-improvement directory: {name}") from exc
            if stat.S_ISLNK(before.st_mode) or not stat.S_ISDIR(before.st_mode):
                raise ValueError(f"unsafe engaged process-improvement ancestor: {name}")
            flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
            try:
                child_fd = os.open(name, flags, dir_fd=parent_fd)
            except OSError as exc:
                raise ValueError(f"cannot safely open engaged process-improvement directory: {name}") from exc
            try:
                opened = os.fstat(child_fd)
                after = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            except OSError as exc:
                os.close(child_fd)
                raise ValueError(f"engaged process-improvement ancestor changed while opening: {name}") from exc
            identity = _collector_stat_identity(before)
            if (
                not stat.S_ISDIR(opened.st_mode)
                or _collector_stat_identity(opened) != identity
                or _collector_stat_identity(after) != identity
            ):
                os.close(child_fd)
                raise ValueError(f"engaged process-improvement ancestor changed while opening: {name}")
            links.append((parent_fd, name, identity))
            fds.append(child_fd)
        yield fds[-1], root_fd, root_identity, tuple(links)
    finally:
        for fd in reversed(fds):
            with contextlib.suppress(OSError):
                os.close(fd)


def _safe_pi_read_regular(project_root: Path, rel_path: str) -> tuple[bytes, os.stat_result]:
    parts = _safe_pi_parts(rel_path)
    with _collector_directory(project_root, parts[:-1], create=False, context=None) as anchor:
        if anchor is None:
            raise FileNotFoundError(rel_path)
        parent_fd, root_fd, root_identity, links = anchor
        try:
            before = os.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            raise
        except OSError as exc:
            raise ValueError(f"cannot inspect engaged process-improvement file: {rel_path}") from exc
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise ValueError(f"engaged process-improvement path must be a regular file: {rel_path}")
        try:
            fd = os.open(parts[-1], os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_fd)
        except OSError as exc:
            raise ValueError(f"cannot safely open engaged process-improvement file: {rel_path}") from exc
        try:
            opened = os.fstat(fd)
            if not stat.S_ISREG(opened.st_mode) or _collector_stat_identity(opened) != _collector_stat_identity(before):
                raise ValueError(f"engaged process-improvement path must be a regular file: {rel_path}")
            chunks: list[bytes] = []
            while True:
                chunk = os.read(fd, 1024 * 128)
                if not chunk:
                    break
                chunks.append(chunk)
            data = b"".join(chunks)
            after = os.fstat(fd)
        finally:
            os.close(fd)
        try:
            current = os.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
        except OSError as exc:
            raise ValueError(f"engaged process-improvement file changed while reading: {rel_path}") from exc
        _collector_validate_anchor(
            project_root,
            root_fd=root_fd,
            root_identity=root_identity,
            links=links,
        )
        if (
            not stat.S_ISREG(after.st_mode)
            or _collector_regular_fingerprint(before) != _collector_regular_fingerprint(opened)
            or _collector_regular_fingerprint(before) != _collector_regular_fingerprint(after)
            or _collector_regular_fingerprint(before) != _collector_regular_fingerprint(current)
            or len(data) != after.st_size
        ):
            raise ValueError(f"engaged process-improvement file changed while reading: {rel_path}")
        return data, after


def _safe_pi_read_optional(project_root: Path, rel_path: str) -> tuple[bytes, os.stat_result] | None:
    try:
        return _safe_pi_read_regular(project_root, rel_path)
    except FileNotFoundError:
        return None


def _safe_pi_object_map(project_root: Path, source_ref: str) -> dict[str, dict[str, object]]:
    objects: dict[str, dict[str, object]] = {}
    for rel_path in _capture_pi_data_paths(source_ref):
        loaded = _safe_pi_read_optional(project_root, rel_path)
        if loaded is None:
            continue
        data, observed = loaded
        objects[rel_path] = {
            "sha256": hashlib.sha256(data).hexdigest(),
            "file_type": "regular",
            "st_size": observed.st_size,
        }
    return {path: objects[path] for path in sorted(objects)}


def _safe_pi_backlog_rel_paths(project_root: Path) -> list[str]:
    with _collector_directory(
        project_root,
        tuple(PROCESS_IMPROVEMENTS_DIR.parts),
        create=False,
        context=None,
    ) as anchor:
        if anchor is None:
            return []
        parent_fd, root_fd, root_identity, links = anchor
        try:
            names = os.listdir(parent_fd)
        except OSError as exc:
            raise ValueError("cannot enumerate engaged process-improvement backlogs") from exc
        _collector_validate_anchor(
            project_root,
            root_fd=root_fd,
            root_identity=root_identity,
            links=links,
        )
        paths: list[str] = []
        for name in names:
            if not name.endswith(".md") or name in CORE_DOC_NAMES:
                continue
            try:
                observed = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            except OSError as exc:
                raise ValueError(f"cannot inspect engaged process-improvement backlog: {name}") from exc
            if not stat.S_ISREG(observed.st_mode):
                raise ValueError(f"engaged process-improvement backlog must be a regular file: {name}")
            paths.append((PROCESS_IMPROVEMENTS_DIR / name).as_posix())
        return sorted(paths)


def _safe_pi_backlogs(project_root: Path) -> list[BacklogFile]:
    backlogs: list[BacklogFile] = []
    for rel_path in _safe_pi_backlog_rel_paths(project_root):
        loaded = _safe_pi_read_regular(project_root, rel_path)
        try:
            text = loaded[0].decode("utf-8", "strict")
        except UnicodeDecodeError as exc:
            raise ValueError(f"engaged process-improvement backlog is not UTF-8: {rel_path}") from exc
        backlogs.append(parse_backlog_text(text, path=project_root / rel_path, project_root=project_root))
    return backlogs


def _safe_pi_write_text(
    project_root: Path,
    rel_path: str,
    text: str,
    *,
    context: ContractContext,
    active_admission: dict[str, object] | None = None,
) -> None:
    parts = _safe_pi_parts(rel_path)
    with _collector_directory(
        project_root,
        parts[:-1],
        create=True,
        context=context,
        active_admission=active_admission,
    ) as anchor:
        assert anchor is not None
        parent_fd, root_fd, root_identity, links = anchor
        try:
            existing = os.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            existing = None
        except OSError as exc:
            raise ValueError(f"cannot inspect engaged process-improvement output: {rel_path}") from exc
        if existing is not None and (stat.S_ISLNK(existing.st_mode) or not stat.S_ISREG(existing.st_mode)):
            raise ValueError(f"engaged process-improvement output must be a regular file: {rel_path}")
        mode = stat.S_IMODE(existing.st_mode) if existing is not None else 0o666
        data = text.encode("utf-8")
        temporary = f".{parts[-1]}.{uuid.uuid4().hex}.tmp"
        created = False
        try:
            _collector_validate_anchor(
                project_root,
                root_fd=root_fd,
                root_identity=root_identity,
                links=links,
            )
            _validate_active_general_pi_effect(
                project_root,
                context=context,
                admission=active_admission,
            )
            fd = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                mode,
                dir_fd=parent_fd,
            )
            created = True
            try:
                if existing is not None:
                    os.fchmod(fd, mode)
                offset = 0
                while offset < len(data):
                    _validate_active_general_pi_effect(
                        project_root,
                        context=context,
                        admission=active_admission,
                    )
                    written = os.write(fd, data[offset:])
                    if written <= 0:
                        raise OSError("cannot write engaged process-improvement output")
                    offset += written
                _validate_active_general_pi_effect(
                    project_root,
                    context=context,
                    admission=active_admission,
                )
                os.fsync(fd)
            finally:
                os.close(fd)
            try:
                current = os.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                current = None
            except OSError as exc:
                raise ValueError(f"cannot inspect engaged process-improvement output: {rel_path}") from exc
            if existing is None:
                if current is not None:
                    raise ValueError(f"engaged process-improvement output appeared while writing: {rel_path}")
            elif (
                current is None
                or stat.S_ISLNK(current.st_mode)
                or not stat.S_ISREG(current.st_mode)
                or _collector_regular_fingerprint(current) != _collector_regular_fingerprint(existing)
            ):
                raise ValueError(f"engaged process-improvement output changed while writing: {rel_path}")
            _collector_validate_anchor(
                project_root,
                root_fd=root_fd,
                root_identity=root_identity,
                links=links,
            )
            _validate_active_general_pi_effect(
                project_root,
                context=context,
                admission=active_admission,
            )
            os.replace(temporary, parts[-1], src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
            created = False
            _validate_active_general_pi_effect(
                project_root,
                context=context,
                admission=active_admission,
            )
            os.fsync(parent_fd)
        finally:
            if created:
                with contextlib.suppress(FileNotFoundError, OSError):
                    os.unlink(temporary, dir_fd=parent_fd)


def _safe_pi_rebuild_derived_surfaces(
    project_root: Path,
    *,
    context: ContractContext,
    active_admission: dict[str, object] | None = None,
) -> dict[str, str]:
    backlogs = _safe_pi_backlogs(project_root)
    surfaces = (
        (INDEX_PATH, INDEX_AUTO_START, INDEX_AUTO_END, default_index_text(), _render_index_summary(backlogs, project_root=project_root)),
        (DEFERRED_PATH, DEFERRED_AUTO_START, DEFERRED_AUTO_END, default_deferred_text(), _render_deferred_summary(backlogs, project_root=project_root)),
        (PROMOTION_PATH, PROMOTION_AUTO_START, PROMOTION_AUTO_END, default_promotion_text(), _render_promotion_summary(backlogs, project_root=project_root)),
    )
    updated: dict[str, str] = {}
    for path, start_marker, end_marker, default_text, rendered in surfaces:
        rel_path = path.as_posix()
        loaded = _safe_pi_read_optional(project_root, rel_path)
        if loaded is None:
            current = default_text
        else:
            try:
                current = loaded[0].decode("utf-8", "strict")
            except UnicodeDecodeError as exc:
                raise ValueError(f"engaged process-improvement surface is not UTF-8: {rel_path}") from exc
        _safe_pi_write_text(
            project_root,
            rel_path,
            _replace_auto_block(current, start_marker, end_marker, rendered),
            context=context,
            active_admission=active_admission,
        )
        updated[rel_path] = rel_path
    return updated


def _safe_pi_read_capture_receipt_regular(
    project_root: Path,
    rel_path: Path,
) -> tuple[dict[str, object], bytes, os.stat_result] | None:
    """Read one engaged V2 receipt through the collector's anchored reader."""

    try:
        data, observed = _safe_pi_read_regular(project_root, rel_path.as_posix())
    except FileNotFoundError:
        return None
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid process-improvement capture receipt JSON: {rel_path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"process-improvement capture receipt is not an object: {rel_path}")
    return payload, data, observed


def _safe_pi_write_v2_capture_receipt(
    *,
    project_root: Path,
    rel_path: Path,
    receipt: dict[str, object],
    replace_blocked: bool,
    context: ContractContext,
    active_admission: dict[str, object] | None,
) -> str:
    """Atomically publish the engaged V2 role receipt below pinned directory fds."""

    parts = _safe_pi_parts(rel_path.as_posix())
    existing_loaded = _safe_pi_read_capture_receipt_regular(project_root, rel_path)
    if replace_blocked:
        if existing_loaded is None or existing_loaded[0].get("capture_state") != "blocked":
            raise ValueError(f"process-improvement v2 continuation receipt cannot replace: {rel_path}")
        expected_existing = existing_loaded[2]
    else:
        if existing_loaded is not None:
            raise ValueError(f"process-improvement v2 receipt already exists: {rel_path}")
        expected_existing = None
    data = json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    with _collector_directory(
        project_root,
        parts[:-1],
        create=True,
        context=context,
        active_admission=active_admission,
    ) as anchor:
        assert anchor is not None
        parent_fd, root_fd, root_identity, links = anchor
        try:
            current = os.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            current = None
        except OSError as exc:
            raise ValueError(f"cannot inspect process-improvement capture receipt: {rel_path}") from exc
        if expected_existing is None:
            if current is not None:
                raise ValueError(f"process-improvement v2 receipt already exists: {rel_path}")
        elif (
            current is None
            or stat.S_ISLNK(current.st_mode)
            or not stat.S_ISREG(current.st_mode)
            or _collector_regular_fingerprint(current) != _collector_regular_fingerprint(expected_existing)
        ):
            raise ValueError(f"process-improvement v2 continuation receipt changed before replacement: {rel_path}")
        temporary = f".{parts[-1]}.{uuid.uuid4().hex}.tmp"
        created = False
        try:
            _collector_validate_anchor(
                project_root,
                root_fd=root_fd,
                root_identity=root_identity,
                links=links,
            )
            _validate_active_general_pi_effect(
                project_root,
                context=context,
                admission=active_admission,
            )
            fd = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=parent_fd,
            )
            created = True
            try:
                os.fchmod(fd, 0o600)
                offset = 0
                while offset < len(data):
                    _validate_active_general_pi_effect(
                        project_root,
                        context=context,
                        admission=active_admission,
                    )
                    written = os.write(fd, data[offset:])
                    if written <= 0:
                        raise OSError("cannot write process-improvement capture receipt")
                    offset += written
                _validate_active_general_pi_effect(
                    project_root,
                    context=context,
                    admission=active_admission,
                )
                os.fsync(fd)
            finally:
                os.close(fd)
            try:
                current = os.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                current = None
            except OSError as exc:
                raise ValueError(f"cannot inspect process-improvement capture receipt: {rel_path}") from exc
            if expected_existing is None:
                if current is not None:
                    raise ValueError(f"process-improvement v2 receipt appeared while writing: {rel_path}")
            elif (
                current is None
                or stat.S_ISLNK(current.st_mode)
                or not stat.S_ISREG(current.st_mode)
                or _collector_regular_fingerprint(current) != _collector_regular_fingerprint(expected_existing)
            ):
                raise ValueError(f"process-improvement v2 continuation receipt changed while writing: {rel_path}")
            _collector_validate_anchor(
                project_root,
                root_fd=root_fd,
                root_identity=root_identity,
                links=links,
            )
            _validate_active_general_pi_effect(
                project_root,
                context=context,
                admission=active_admission,
            )
            if replace_blocked:
                os.replace(temporary, parts[-1], src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
            else:
                os.link(
                    temporary,
                    parts[-1],
                    src_dir_fd=parent_fd,
                    dst_dir_fd=parent_fd,
                    follow_symlinks=False,
                )
            created = False
            with contextlib.suppress(FileNotFoundError, OSError):
                os.unlink(temporary, dir_fd=parent_fd)
            _validate_active_general_pi_effect(
                project_root,
                context=context,
                admission=active_admission,
            )
            os.fsync(parent_fd)
            return rel_path.as_posix()
        finally:
            if created:
                with contextlib.suppress(FileNotFoundError, OSError):
                    os.unlink(temporary, dir_fd=parent_fd)


def _capture_pi_path_results(
    before_objects: dict[str, dict[str, object]],
    after_objects: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    return [
        {
            "path": path,
            "before_object": before_objects.get(path),
            "after_object": after_objects.get(path),
        }
        for path in sorted(set(before_objects) | set(after_objects))
        if before_objects.get(path) != after_objects.get(path)
    ]


def _capture_receipt_regular_path(
    project_root: Path,
    rel_path: Path,
    *,
    create_parent: bool,
    context: ContractContext | None = None,
) -> Path:
    """Resolve a receipt path without accepting symlinked ancestors or a leaf."""
    if rel_path.is_absolute() or any(part in {"", ".", ".."} for part in rel_path.parts):
        raise ValueError(f"invalid process-improvement capture receipt path: {rel_path}")
    parent = project_root.absolute()
    for name in rel_path.parts[:-1]:
        parent = parent / name
        try:
            entry = parent.lstat()
        except FileNotFoundError:
            if not create_parent:
                raise
            _validate_writer_effect(context)
            parent.mkdir(mode=0o700)
            entry = parent.lstat()
        if stat.S_ISLNK(entry.st_mode) or not stat.S_ISDIR(entry.st_mode):
            raise ValueError(f"unsafe process-improvement capture receipt ancestor: {rel_path}")
    return parent / rel_path.parts[-1]


def _read_capture_receipt_regular(project_root: Path, rel_path: Path) -> tuple[dict[str, object], bytes] | None:
    """Return one exact regular receipt, never following a symlinked path component."""
    try:
        path = _capture_receipt_regular_path(project_root, rel_path, create_parent=False)
    except FileNotFoundError:
        return None
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ValueError(f"unsafe process-improvement capture receipt: {rel_path}") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"process-improvement capture receipt must be a regular file: {rel_path}")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            data = handle.read()
        after = os.fstat(fd)
    finally:
        os.close(fd)
    if (
        not stat.S_ISREG(after.st_mode)
        or before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or len(data) != after.st_size
    ):
        raise ValueError(f"process-improvement capture receipt changed while reading: {rel_path}")
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid process-improvement capture receipt JSON: {rel_path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"process-improvement capture receipt is not an object: {rel_path}")
    return payload, data


def _validate_capture_object(value: object, *, field: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != {"sha256", "file_type", "st_size"}:
        raise ValueError(f"{field} must be an exact process-improvement object")
    sha256 = value.get("sha256")
    file_type = value.get("file_type")
    st_size = value.get("st_size")
    if (
        not isinstance(sha256, str)
        or not HEX64_RE.fullmatch(sha256)
        or file_type != "regular"
        or not isinstance(st_size, int)
        or isinstance(st_size, bool)
        or st_size < 0
    ):
        raise ValueError(f"{field} contains an invalid process-improvement object")
    return {"sha256": sha256, "file_type": file_type, "st_size": st_size}


def _validate_capture_object_map(
    value: object,
    *,
    source_ref: str,
    field: str,
) -> dict[str, dict[str, object]]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object map")
    allowed = set(_capture_pi_data_paths(source_ref))
    paths = list(value)
    if paths != sorted(paths) or any(not isinstance(path, str) or path not in allowed for path in paths):
        raise ValueError(f"{field} must use sorted exact process-improvement data paths")
    return {
        path: _validate_capture_object(value[path], field=f"{field}[{path!r}]")
        for path in paths
    }


def _validate_capture_path_results(
    value: object,
    *,
    before_objects: dict[str, dict[str, object]],
    after_objects: dict[str, dict[str, object]],
) -> None:
    if not isinstance(value, list):
        raise ValueError("process_improvement_path_results must be a list")
    expected_paths = [
        path
        for path in sorted(set(before_objects) | set(after_objects))
        if before_objects.get(path) != after_objects.get(path)
    ]
    actual_paths: list[str] = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {"path", "before_object", "after_object"}:
            raise ValueError("process_improvement_path_results entry is invalid")
        path = item.get("path")
        if not isinstance(path, str):
            raise ValueError("process_improvement_path_results path is invalid")
        actual_paths.append(path)
        for key, expected in (("before_object", before_objects.get(path)), ("after_object", after_objects.get(path))):
            actual = item.get(key)
            if actual is None:
                if expected is not None:
                    raise ValueError(f"process_improvement_path_results {key} unexpectedly null")
            elif _validate_capture_object(actual, field=f"process_improvement_path_results.{key}") != expected:
                raise ValueError(f"process_improvement_path_results {key} differs from exact maps")
    if actual_paths != expected_paths:
        raise ValueError("process_improvement_path_results must exactly cover changed paths")


def _validate_v2_capture_receipt(
    receipt: dict[str, object],
    *,
    source_ref: str,
    role: str,
    followups_capture_cycle_id: str,
) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]]]:
    if receipt.get("receipt_schema") != CAPTURE_RECEIPT_V2_SCHEMA:
        raise ValueError("process-improvement receipt schema is not v2")
    if receipt.get("source_ref") != source_ref or receipt.get("role") != role:
        raise ValueError("process-improvement receipt source/role identity mismatch")
    if receipt.get("followups_capture_cycle_id") != followups_capture_cycle_id:
        raise ValueError("process-improvement receipt cycle identity mismatch")
    input_sha256 = receipt.get("input_sha256")
    if not isinstance(input_sha256, str) or not HEX64_RE.fullmatch(input_sha256):
        raise ValueError("process-improvement receipt input_sha256 is invalid")
    if receipt.get("capture_state") not in CAPTURE_STATE_VALUES:
        raise ValueError("process-improvement receipt capture state is invalid")
    before = _validate_capture_object_map(
        receipt.get("before_process_improvement_files"),
        source_ref=source_ref,
        field="before_process_improvement_files",
    )
    after = _validate_capture_object_map(
        receipt.get("after_process_improvement_files"),
        source_ref=source_ref,
        field="after_process_improvement_files",
    )
    _validate_capture_path_results(
        receipt.get("process_improvement_path_results"),
        before_objects=before,
        after_objects=after,
    )
    return before, after


def _v2_receipt_payload(
    *,
    role: str,
    source_ref: str,
    followups_capture_cycle_id: str,
    input_sha256: str,
    capture_state: str,
    reason_code: str,
    payload: dict[str, object],
    error: str | None = None,
) -> dict[str, object]:
    receipt: dict[str, object] = {
        "receipt_schema": CAPTURE_RECEIPT_V2_SCHEMA,
        "source_ref": source_ref,
        "role": role,
        "capture_state": capture_state,
        "reason_code": reason_code,
        "followups_capture_cycle_id": followups_capture_cycle_id,
        "input_sha256": input_sha256,
        "backlog_paths": _capture_backlog_paths(payload),
        "before_process_improvement_files": payload.get("before_process_improvement_files") or {},
        "after_process_improvement_files": payload.get("after_process_improvement_files") or {},
        "process_improvement_path_results": payload.get("process_improvement_path_results") or [],
        "created": payload.get("created") or [],
        "duplicates": payload.get("duplicates") or [],
        "written_at": _now_local(),
    }
    if error:
        receipt["error"] = error
    return receipt


def _write_fd_all(fd: int, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        written = os.write(fd, data[offset:])
        if written <= 0:
            raise OSError("cannot write process-improvement capture receipt")
        offset += written


def _write_v2_capture_receipt(
    *,
    project_root: Path,
    source_ref: str,
    role: str,
    followups_capture_cycle_id: str,
    receipt: dict[str, object],
    replace_blocked: bool,
    context: ContractContext | None = None,
    active_admission: dict[str, object] | None = None,
    engaged_public: bool = False,
) -> str:
    rel_path = capture_receipt_rel_path(source_ref, role, followups_capture_cycle_id)
    if engaged_public:
        if context is None:
            raise ValueError("engaged process-improvement receipt requires contract context")
        return _safe_pi_write_v2_capture_receipt(
            project_root=project_root,
            rel_path=rel_path,
            receipt=receipt,
            replace_blocked=replace_blocked,
            context=context,
            active_admission=active_admission,
        )
    path = _capture_receipt_regular_path(
        project_root,
        rel_path,
        create_parent=True,
        context=context,
    )
    data = json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    if replace_blocked:
        existing = _read_capture_receipt_regular(project_root, rel_path)
        if existing is None or existing[0].get("capture_state") != "blocked":
            raise ValueError(f"process-improvement v2 continuation receipt cannot replace: {rel_path}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    temporary_created = False
    try:
        _validate_active_general_pi_effect(
            project_root,
            context=context,
            admission=active_admission,
        )
        fd = os.open(temporary, flags, 0o600)
        temporary_created = True
        try:
            _validate_active_general_pi_effect(
                project_root,
                context=context,
                admission=active_admission,
            )
            _write_fd_all(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        if replace_blocked:
            _validate_active_general_pi_effect(
                project_root,
                context=context,
                admission=active_admission,
            )
            os.replace(temporary, path)
        else:
            try:
                _validate_active_general_pi_effect(
                    project_root,
                    context=context,
                    admission=active_admission,
                )
                os.link(temporary, path, follow_symlinks=False)
            except FileExistsError as exc:
                raise ValueError(f"process-improvement v2 receipt already exists: {rel_path}") from exc
        return rel_path.as_posix()
    finally:
        if temporary_created:
            _validate_writer_effect(context)
            with contextlib.suppress(FileNotFoundError):
                temporary.unlink()


def _v2_replay_response(
    receipt: dict[str, object],
    *,
    receipt_path: str,
    replay_kind: str,
) -> dict[str, object]:
    capture_state = str(receipt["capture_state"])
    reason_code = str(receipt["reason_code"])
    return {
        "state": "no_process_improvements" if capture_state in {"clean_noop", "already_tracked"} else "collected",
        "reason_code": reason_code,
        "created": receipt.get("created") or [],
        "duplicates": receipt.get("duplicates") or [],
        "backlog_files": receipt.get("backlog_paths") or [],
        "derived_surfaces": {},
        "before_process_improvement_files": receipt.get("before_process_improvement_files") or {},
        "after_process_improvement_files": receipt.get("after_process_improvement_files") or {},
        "process_improvement_path_results": receipt.get("process_improvement_path_results") or [],
        "process_improvement_capture_state": capture_state,
        "process_improvement_capture_reason": reason_code,
        "process_improvement_capture_replay": replay_kind,
        "process_improvement_receipt_path": receipt_path,
        "followups_capture_cycle_id": receipt["followups_capture_cycle_id"],
    }


def _admit_v2_replay(
    *,
    project_root: Path,
    source_ref: str,
    role: str,
    followups_capture_cycle_id: str,
    input_sha256: str,
    live_objects: dict[str, dict[str, object]],
    engaged_public: bool = False,
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    """Return an exact no-write replay response and receipt, or admission state for collection."""
    rel_path = capture_receipt_rel_path(source_ref, role, followups_capture_cycle_id)
    loaded = (
        _safe_pi_read_capture_receipt_regular(project_root, rel_path)
        if engaged_public
        else _read_capture_receipt_regular(project_root, rel_path)
    )
    if loaded is None:
        return None, None
    receipt, _data, *_observed = loaded
    before, after = _validate_v2_capture_receipt(
        receipt,
        source_ref=source_ref,
        role=role,
        followups_capture_cycle_id=followups_capture_cycle_id,
    )
    state = str(receipt["capture_state"])
    if state == "blocked":
        # Recovery adopts this receipt's original before-map in both authority
        # modes, so it may start only from the exact after-map it recorded.
        if live_objects != after:
            raise ValueError("process-improvement v2 blocked receipt live map conflicts before recovery")
        if before != after and receipt["input_sha256"] != input_sha256:
            raise ValueError(
                "process-improvement v2 blocked partial receipt input digest conflicts before recovery"
            )
        return None, receipt
    if receipt["input_sha256"] != input_sha256:
        raise ValueError("process-improvement v2 continuation receipt input digest conflicts before collection")
    if live_objects == after:
        return _v2_replay_response(
            receipt,
            receipt_path=rel_path.as_posix(),
            replay_kind="exact_leaf",
        ), receipt
    try:
        position = GENERAL_CAPTURE_ROLES.index(role)
    except ValueError as exc:
        raise ValueError("process-improvement v2 receipt live map drift is not replayable for this role") from exc
    cursor = after
    saw_successor = False
    for successor_role in GENERAL_CAPTURE_ROLES[position + 1 :]:
        if saw_successor and cursor == live_objects:
            return _v2_replay_response(
                receipt,
                receipt_path=rel_path.as_posix(),
                replay_kind="exact_proven_descendant",
            ), receipt
        successor_path = capture_receipt_rel_path(source_ref, successor_role, followups_capture_cycle_id)
        loaded_successor = (
            _safe_pi_read_capture_receipt_regular(project_root, successor_path)
            if engaged_public
            else _read_capture_receipt_regular(project_root, successor_path)
        )
        if loaded_successor is None:
            raise ValueError("process-improvement v2 receipt live map drift lacks a contiguous successor suffix")
        successor, _data, *_observed = loaded_successor
        before, successor_after = _validate_v2_capture_receipt(
            successor,
            source_ref=source_ref,
            role=successor_role,
            followups_capture_cycle_id=followups_capture_cycle_id,
        )
        if successor.get("capture_state") not in CAPTURE_CONTINUATION_STATES or before != cursor:
            raise ValueError("process-improvement v2 receipt successor suffix is not contiguous")
        cursor = successor_after
        saw_successor = True
    if not saw_successor or cursor != live_objects:
        raise ValueError("process-improvement v2 receipt live map drift is not proven by successors")
    return _v2_replay_response(
        receipt,
        receipt_path=rel_path.as_posix(),
        replay_kind="exact_proven_descendant",
    ), receipt


def _write_capture_receipt(
    *,
    project_root: Path,
    role: str,
    source_ref: str,
    capture_state: str,
    reason_code: str,
    followups_capture_cycle_id: str | None = None,
    payload: dict[str, object] | None = None,
    error: str | None = None,
    context: ContractContext | None = None,
) -> str:
    normalized_role = _normalize_role(role, field_name="role")
    if capture_state not in CAPTURE_STATE_VALUES:
        raise ValueError(f"Unsupported capture_state: {capture_state!r}")
    payload = payload or {}
    rel_path = capture_receipt_rel_path(source_ref, normalized_role)
    receipt = {
        "receipt_schema": CAPTURE_RECEIPT_V1_SCHEMA,
        "source_ref": source_ref,
        "role": normalized_role,
        "capture_state": capture_state,
        "reason_code": reason_code,
        "followups_capture_cycle_id": followups_capture_cycle_id or "none",
        "backlog_paths": _capture_backlog_paths(payload),
        "before_process_improvement_files": payload.get("before_process_improvement_files") or {},
        "after_process_improvement_files": payload.get("after_process_improvement_files") or {},
        "process_improvement_path_results": payload.get("process_improvement_path_results") or [],
        "created": payload.get("created") or [],
        "duplicates": payload.get("duplicates") or [],
        "written_at": _now_local(),
    }
    if error:
        receipt["error"] = error
    path = project_root / rel_path
    _validate_writer_effect(context)
    path.parent.mkdir(parents=True, exist_ok=True)
    _validate_writer_effect(context)
    path.write_text(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return rel_path.as_posix()


def _normalize_scalar(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = raw.strip()
    if value.startswith("`") and value.endswith("`") and len(value) >= 2:
        value = value[1:-1].strip()
    value = value.strip().strip("'").strip('"').strip()
    return value or None


def _normalize_followups_capture_cycle_id(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = raw
    try:
        parsed = uuid.UUID(value)
    except ValueError as exc:
        raise ValueError("followups_capture_cycle_id must be a canonical UUIDv4") from exc
    if parsed.version != 4 or str(parsed) != value:
        raise ValueError("followups_capture_cycle_id must be a canonical UUIDv4")
    return value


def _normalize_role(raw: str | None, *, field_name: str) -> str:
    value = _normalize_scalar(raw)
    if value is None:
        raise ValueError(f"Missing required field: {field_name}")
    lowered = value.lower()
    for role in ALLOWED_ROLES:
        if role.lower() == lowered:
            return role
    raise ValueError(f"Unsupported {field_name}: {value!r}")


def _normalize_promotion_class(raw: str | None) -> str:
    value = _normalize_scalar(raw)
    if value is None:
        raise ValueError("Missing required field: promotion_class")
    lowered = value.lower()
    lowered = PROMOTION_CLASS_ALIASES.get(lowered, lowered)
    if lowered not in PROMOTION_CLASSES:
        raise ValueError(f"Unsupported promotion_class: {value!r}")
    return lowered


def _normalize_status(raw: str | None) -> str:
    value = _normalize_scalar(raw)
    if value is None:
        return "open"
    lowered = value.lower()
    if lowered not in ALLOWED_STATUSES:
        raise ValueError(f"Unsupported status: {value!r}")
    return lowered


def _normalize_priority(raw: str | None) -> str:
    value = _normalize_scalar(raw)
    if value is None:
        return "P?"
    normalized = value.upper()
    if normalized not in ALLOWED_PRIORITIES:
        raise ValueError(f"Unsupported priority: {value!r}")
    return normalized


def _normalize_optional_path(raw: str | None) -> str:
    value = _normalize_scalar(raw)
    if value is None:
        return "null"
    lowered = value.lower()
    if lowered in {"null", "none", "unknown"}:
        return "null"
    return value


def _normalize_target_repo_scope(raw: str | None) -> str:
    value = _normalize_scalar(raw)
    if value is None:
        return "null"
    lowered = value.lower()
    if lowered in {"null", "none", "unknown"}:
        return "null"
    if lowered in TARGET_REPO_SCOPE_RESERVED:
        return lowered
    normalized = re.sub(r"-+", "-", lowered.replace("_", "-")).strip("-")
    if not TARGET_REPO_SCOPE_RE.fullmatch(normalized):
        raise ValueError(f"Unsupported target_repo_scope: {value!r}")
    return normalized


def _normalize_delivery_mode(raw: str | None) -> str:
    value = _normalize_scalar(raw)
    if value is None:
        return "null"
    lowered = value.lower()
    if lowered in {"null", "none", "unknown"}:
        return "null"
    if lowered not in DELIVERY_MODES:
        raise ValueError(f"Unsupported delivery_mode: {value!r}")
    return lowered


def _normalize_execution_kind(raw: str | None) -> str:
    value = _normalize_scalar(raw)
    if value is None:
        return "null"
    lowered = value.lower()
    if lowered in {"null", "none", "unknown"}:
        return "null"
    if lowered not in EXECUTION_KINDS:
        raise ValueError(f"Unsupported execution_kind: {value!r}")
    return lowered


def _normalize_optional_ref(raw: str | None, *, field_name: str) -> str:
    value = _normalize_scalar(raw)
    if value is None:
        return "null"
    lowered = value.lower()
    if lowered in {"null", "none", "unknown"}:
        return "null"
    if any(ch.isspace() for ch in value):
        raise ValueError(f"{field_name} must be a literal ref without whitespace: {value!r}")
    return value


def _normalize_optional_timestamp(raw: str | None, *, field_name: str) -> str:
    value = _normalize_scalar(raw)
    if value is None:
        return "null"
    lowered = value.lower()
    if lowered in {"null", "none", "unknown"}:
        return "null"
    return value


def _is_nullish_literal(value: str) -> bool:
    return value.strip().lower() in {"", "null", "none", "unknown", "n/a"}


AUTO_TRIAGE_NOTES = {
    "auto-collected from memory-finalize general lane",
    "none",
    "null",
    "unknown",
    "n/a",
}
STRICT_TRIAGE_CARRIER_STATUSES = {"triaged", "promoted", "handled"}
STAGED_TRIAGE_CARRIER_STATUSES = {"open", *STRICT_TRIAGE_CARRIER_STATUSES}
DECISION_NOTE_STATUSES = {"deferred", "rejected"}


def _has_literal_carrier(value: str) -> bool:
    return not _is_nullish_literal(value)


def _has_explicit_triage_note(entry: BacklogEntry) -> bool:
    value = entry.triage_note.strip()
    if _is_nullish_literal(value):
        return False
    return value.lower() not in AUTO_TRIAGE_NOTES


def triage_carrier_issues(entry: BacklogEntry) -> tuple[TriageCarrierIssue, ...]:
    issues: list[TriageCarrierIssue] = []

    def add(field: str, code: str, message: str) -> None:
        issues.append(
            TriageCarrierIssue(
                entry_id=entry.entry_id,
                status=entry.status,
                field=field,
                code=code,
                message=message,
            )
        )

    if entry.status in STAGED_TRIAGE_CARRIER_STATUSES:
        if entry.priority == "P?":
            add("priority", "missing_priority", "Triage carrier requires `priority` as urgency scalar.")
        if not _has_literal_carrier(entry.target_canon_path):
            add(
                "target_canon_path",
                "missing_target_canon_path",
                "Triage carrier requires literal `target_canon_path`.",
            )
        if not _has_literal_carrier(entry.target_repo_scope):
            add(
                "target_repo_scope",
                "missing_target_repo_scope",
                "Triage carrier requires literal `target_repo_scope`.",
            )
        if not _has_literal_carrier(entry.delivery_mode):
            add("delivery_mode", "missing_delivery_mode", "Triage carrier requires literal `delivery_mode`.")
        if entry.status == "open":
            if not _has_literal_carrier(entry.execution_kind):
                add(
                    "execution_kind",
                    "missing_execution_kind",
                    "Open row readback has no literal `execution_kind` carrier yet.",
                )
            if not _has_literal_carrier(entry.execution_ref):
                add(
                    "execution_ref",
                    "missing_execution_ref",
                    "Open row readback has no literal `execution_ref` carrier yet.",
                )
        if entry.status == "triaged" and not (
            _has_literal_carrier(entry.execution_ref)
            or _has_literal_carrier(entry.delivery_refs)
            or _has_explicit_triage_note(entry)
        ):
            add(
                "triage_note",
                "missing_triage_decision",
                "Triaged rows require execution/delivery refs or an explicit `triage_note` decision.",
            )

    if entry.status in DECISION_NOTE_STATUSES and not _has_explicit_triage_note(entry):
        add(
            "triage_note",
            "missing_decision_note",
            "Deferred/rejected rows require explicit reason/revisit context in `triage_note`.",
        )

    return tuple(issues)


def assert_complete_triage_carrier(entry: BacklogEntry) -> None:
    issues = triage_carrier_issues(entry)
    if not issues:
        return
    details = ", ".join(f"{issue.entry_id}:{issue.field}({issue.code})" for issue in issues)
    raise ValueError(f"Missing process-improvement triage carrier field(s): {details}")


def _normalize_delivery_refs(raw: str | None) -> str:
    value = _normalize_scalar(raw)
    if value is None:
        return "null"
    lowered = value.lower()
    if lowered in {"null", "none", "unknown"}:
        return "null"
    if value.startswith("[") or value.startswith("{") or value.endswith("]") or value.endswith("}"):
        raise ValueError("delivery_refs must be `null` or a `; `-separated literal ref list, not JSON/prose")
    if lowered in {"later", "tbd", "todo", "unknown", "maybe", "n/a"} or any(
        token in lowered for token in (" later", " tbd", " todo", " unknown", " maybe", " n/a")
    ):
        raise ValueError("delivery_refs must be deterministic literal refs, not prose")
    refs = value.split("; ")
    if "; " not in value or len(refs) < 2:
        refs = [value]
    if any(not ref.strip() for ref in refs):
        raise ValueError("delivery_refs contains an empty ref")
    for ref in refs:
        if ref.strip() != ref or any(ch.isspace() for ch in ref):
            raise ValueError(f"delivery_refs must contain literal refs without whitespace: {ref!r}")
    return "; ".join(refs)


def _normalize_ref(raw: str | None, *, field_name: str, fallback: str | None = None) -> str:
    value = _normalize_scalar(raw) or _normalize_scalar(fallback)
    if value is None:
        raise ValueError(f"Missing required field: {field_name}")
    return value


def _normalize_source_ref_for_lane(raw: str | None, *, lane_source_ref: str) -> str:
    normalized_lane = _normalize_ref(lane_source_ref, field_name="source_ref")
    value = _normalize_scalar(raw)
    if value is None:
        return normalized_lane
    lowered = value.lower()
    if lowered in {"unknown", "null", "none"}:
        return normalized_lane
    normalized_value = _normalize_ref(value, field_name="source_ref")
    if normalized_value != normalized_lane:
        raise ValueError(
            "Structured `source_ref` must match manager-fed/header source_ref "
            f"{normalized_lane!r}; got {normalized_value!r}"
        )
    return normalized_lane


def _normalize_import_scalar(raw: str | None) -> str:
    value = _normalize_scalar(raw)
    if value is None:
        return "unknown"
    return value.replace("`", "").strip() or "unknown"


def _triage_note_from_parts(parts: Iterable[tuple[str, str]]) -> str:
    rendered: list[str] = []
    for key, raw_value in parts:
        value = _normalize_import_scalar(raw_value)
        value = re.sub(r"\s+", "_", value)
        rendered.append(f"{key}={value}")
    return ";".join(rendered)


def _role_from_import_source(raw_source: str, *, owner: str) -> str:
    source = raw_source.lower()
    for role in ALLOWED_ROLES:
        if role.lower() in source:
            return role
    return owner


def _normalize_free_text(raw: str | None, *, field_name: str) -> str:
    value = _normalize_scalar(raw)
    if value is None:
        raise ValueError(f"Missing required field: {field_name}")
    return value


def _validate_execution_contract(entry: BacklogEntry) -> None:
    if entry.status == "deferred" and _is_nullish_literal(entry.triage_note):
        raise ValueError("Deferred process-improvement rows require `triage_note` with reason/revisit trigger")
    if entry.status == "deferred" and entry.delivery_refs == "null":
        note = entry.triage_note.lower()
        has_explicit_null_reason = any(
            token in note
            for token in (
                "delivery_refs=null",
                "delivery_refs_null",
                "no_delivery_refs",
                "no delivery",
                "без delivery",
            )
        )
        if not has_explicit_null_reason:
            raise ValueError(
                "Deferred process-improvement rows with `delivery_refs=null` require an explicit null-delivery reason in `triage_note`"
            )
    if entry.status in {"promoted", "handled"} and entry.target_canon_path == "null":
        raise ValueError("Promoted/handled process-improvement rows require literal `target_canon_path`")
    if entry.status in {"promoted", "handled"} and entry.target_repo_scope == "null":
        raise ValueError("Promoted/handled process-improvement rows require literal `target_repo_scope`")
    if entry.status in {"promoted", "handled"} and entry.delivery_mode == "null":
        raise ValueError("Promoted/handled process-improvement rows require literal `delivery_mode`")
    if entry.status in {"promoted", "handled"} and entry.execution_kind == "null":
        raise ValueError("Promoted/handled process-improvement rows require literal `execution_kind`")
    if entry.status in {"promoted", "handled"} and entry.execution_ref == "null":
        raise ValueError("Promoted/handled process-improvement rows require literal `execution_ref`")
    if entry.status in {"promoted", "handled"} and entry.promoted_at == "null":
        raise ValueError("Promoted/handled process-improvement rows require literal `promoted_at`")
    if entry.status == "handled" and entry.handled_ref == "null":
        raise ValueError("Handled process-improvement rows require literal `handled_ref`")
    if entry.status == "handled" and entry.handled_at == "null":
        raise ValueError("Handled process-improvement rows require literal `handled_at`")


def _replace_auto_block(text: str, start_marker: str, end_marker: str, rendered_block: str) -> str:
    if start_marker in text and end_marker in text:
        start = text.index(start_marker)
        end = text.index(end_marker) + len(end_marker)
        return text[:start].rstrip() + "\n\n" + rendered_block.rstrip() + "\n"
    return text.rstrip() + "\n\n" + rendered_block.rstrip() + "\n"


def _process_dir(root: Path) -> Path:
    return root / PROCESS_IMPROVEMENTS_DIR


def _backlog_title(source_ref: str) -> str:
    source_name = Path(source_ref).stem if "/" in source_ref else source_ref
    return source_name.replace("_", " ")


def backlog_rel_path_for_source_ref(source_ref: str) -> str:
    stem = Path(source_ref).stem if "/" in source_ref else re.sub(r"[^A-Za-z0-9_.-]+", "_", source_ref.strip())
    return (PROCESS_IMPROVEMENTS_DIR / f"{stem}__process_improvements_backlog.md").as_posix()


def resolve_backlog_path(project_root: Path, raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (project_root / path).resolve()


def iter_backlog_paths(project_root: Path) -> list[Path]:
    root = _process_dir(project_root)
    if not root.exists():
        return []
    return sorted(
        path
        for path in root.glob("*.md")
        if path.name not in CORE_DOC_NAMES
    )


def _next_entry_id(entries: Iterable[BacklogEntry]) -> str:
    max_id = 0
    for entry in entries:
        match = ENTRY_ID_RE.match(entry.entry_id)
        if match:
            max_id = max(max_id, int(match.group("number")))
    return f"PI-{max_id + 1:03d}"


def _entry_key(entry: BacklogEntry | ParsedSuggestion) -> tuple[str, ...]:
    return (
        entry.role.lower(),
        entry.owner.lower(),
        entry.promotion_class.lower(),
        entry.trigger_ref.lower(),
        entry.source_ref.lower(),
        entry.symptom.lower(),
        entry.process_gap.lower(),
        entry.suggested_fix.lower(),
    )


def _engaged_entry_key(entry: BacklogEntry | ParsedSuggestion) -> tuple[str, ...]:
    """Deduplicate one attested general-lane suggestion across its four roles."""

    return (
        entry.owner.lower(),
        entry.promotion_class.lower(),
        entry.trigger_ref.lower(),
        entry.source_ref.lower(),
        entry.symptom.lower(),
        entry.process_gap.lower(),
        entry.suggested_fix.lower(),
    )


def default_index_text() -> str:
    return "\n".join(
        [
            "# Process improvements — index",
            "",
            "Навигация по durable backlog-файлам в `docs/process_improvements/*`.",
            "",
            "- Truth surface: per-source backlog files `*__process_improvements_backlog.md`.",
            "- Derived surfaces: `index.md`, `deferred.md`, `promotion_surface.md`.",
            "- No-op receipts `NO PROCESS IMPROVEMENTS — why: <reason_code>` не materialize-ятся как backlog rows.",
            "- Mature rows carry execution pointer fields: `execution_kind`, `execution_ref`, `delivery_refs`, `handled_ref`, `promoted_at`, `handled_at`.",
            "",
            f"{INDEX_AUTO_START}",
            "## Live backlog summary (auto)",
            "- none",
            f"{INDEX_AUTO_END}",
        ]
    ) + "\n"


def default_deferred_text() -> str:
    return "\n".join(
        [
            "# Process improvements — deferred / parked",
            "",
            "Derived bridge surface для suggestions, которые ещё не promoted в живой canon/helper/follow-up work.",
            "Даже deferred/open rows показывают deterministic `delivery_refs` scalar из raw backlog truth.",
            "",
            f"{DEFERRED_AUTO_START}",
            "## Deferred suggestions (auto)",
            "- none",
            f"{DEFERRED_AUTO_END}",
        ]
    ) + "\n"


def default_promotion_text() -> str:
    return "\n".join(
        [
            "# Process improvements — promotion surface",
            "",
            "Derived surface для triage/promote state. `target_canon_path` должен быть literal field, а не prose-оговоркой.",
            "Для mature rows promotion surface также обязан держать literal `target_repo_scope` и `delivery_mode`, чтобы sibling-repo delivery не оставался в голове.",
            "Owner-facing urgency is existing `priority`; mature `triaged|promoted|handled` rows require non-`P?` priority plus target/delivery carrier fields.",
            "`promoted` rows require `execution_kind`, `execution_ref`, `promoted_at`; `handled` rows additionally require `handled_ref`, `handled_at`; rejected/handled reasons live in `triage_note`.",
            "`deferred` rows require owner, `triage_note` reason/revisit trigger, and either literal `delivery_refs` or an explicit null-delivery reason in `triage_note`.",
            "",
            f"{PROMOTION_AUTO_START}",
            "## Promotion surface (auto)",
            "- none",
            f"{PROMOTION_AUTO_END}",
        ]
    ) + "\n"


def _ensure_derived_surface_docs(
    project_root: Path,
    *,
    context: ContractContext,
    first_effect_guarded: bool = False,
) -> None:
    root = _process_dir(project_root)
    if not first_effect_guarded:
        _validate_writer_effect(context)
    root.mkdir(parents=True, exist_ok=True)
    defaults = (
        (INDEX_PATH, default_index_text()),
        (DEFERRED_PATH, default_deferred_text()),
        (PROMOTION_PATH, default_promotion_text()),
    )
    for rel_path, default_text in defaults:
        path = project_root / rel_path
        if not path.exists():
            _write_text(path, default_text, context=context)


def ensure_derived_surface_docs(
    project_root: Path,
    *,
    context: ContractContext | None = None,
) -> None:
    writer_context = _private_writer_context(project_root, context)
    # ``context_for_reader`` (or its fresh capture) is the immediate guard for
    # this first mkdir.  Subsequent file writes each revalidate in ``_write_text``.
    _ensure_derived_surface_docs(project_root, context=writer_context, first_effect_guarded=True)


def extract_process_improvements_section(text: str) -> str:
    lines = text.splitlines()
    start_idx = None
    for idx, line in enumerate(lines):
        if PROCESS_SECTION_HEADING_RE.match(line):
            start_idx = idx + 1
            break
    if start_idx is None:
        raise ValueError("Missing `Process improvements` section in input text")

    body: list[str] = []
    for line in lines[start_idx:]:
        if H2_RE.match(line):
            break
        body.append(line)
    rendered = "\n".join(body).strip()
    if not rendered:
        raise ValueError("`Process improvements` section is empty")
    return rendered


def parse_process_improvements_section(
    text: str,
    *,
    role: str,
    default_source_ref: str,
) -> dict[str, object]:
    body = extract_process_improvements_section(text)
    if "\n" not in body:
        match = NO_PROCESS_RE.match(body.strip())
        if match:
            reason = match.group("reason")
            if reason not in NO_PROCESS_IMPROVEMENT_REASONS:
                raise ValueError(f"Unsupported no-op reason: {reason!r}")
            return {
                "state": "no_process_improvements",
                "reason_code": reason,
                "suggestions": [],
            }

    suggestions: list[ParsedSuggestion] = []
    current_fields: dict[str, str] = {}
    saw_heading = False

    def flush_current() -> None:
        nonlocal current_fields
        if not current_fields:
            return
        parsed_role = _normalize_role(current_fields.get("owner"), field_name="owner")
        suggestion = ParsedSuggestion(
            role=_normalize_role(role, field_name="role"),
            owner=parsed_role,
            promotion_class=_normalize_promotion_class(current_fields.get("promotion_class")),
            trigger_ref=_normalize_ref(current_fields.get("trigger_ref"), field_name="trigger_ref", fallback="unknown"),
            source_ref=_normalize_source_ref_for_lane(
                current_fields.get("source_ref"),
                lane_source_ref=default_source_ref,
            ),
            symptom=_normalize_free_text(current_fields.get("symptom"), field_name="symptom"),
            process_gap=_normalize_free_text(current_fields.get("process_gap"), field_name="process_gap"),
            suggested_fix=_normalize_free_text(current_fields.get("suggested_fix"), field_name="suggested_fix"),
        )
        suggestions.append(suggestion)
        current_fields = {}

    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if NO_PROCESS_RE.match(line):
            raise ValueError("Literal no-op cannot be mixed with structured suggestions")
        if H3_RE.match(line):
            saw_heading = True
            flush_current()
            continue
        match = PROCESS_FIELD_RE.match(line)
        if not match:
            raise ValueError(f"Unsupported line inside `Process improvements`: {raw_line!r}")
        field_name = match.group("key").lower()
        if field_name not in PROCESS_OUTPUT_FIELD_NAMES:
            raise ValueError(f"Unsupported field inside `Process improvements`: {field_name!r}")
        current_fields[field_name] = match.group("value").strip()
    flush_current()

    if not suggestions:
        raise ValueError("No structured process-improvement suggestions found")
    if saw_heading and len(suggestions) == 0:
        raise ValueError("Process-improvement headings were present without fields")
    return {
        "state": "suggestions",
        "suggestions": suggestions,
    }


def _resolve_import_file(raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    resolved = path.resolve()
    if not resolved.exists():
        raise ValueError(f"Missing import-file path: {raw_path}")
    if not resolved.is_file():
        raise ValueError(f"--import-file accepts explicit files only, not directories: {raw_path}")
    if resolved.suffix != ".md" or resolved.parent.name != "process_improvements" or resolved.parent.parent.name != "docs":
        raise ValueError(
            "--import-file expects an explicit docs/process_improvements/*.md file: "
            f"{raw_path}"
        )
    return resolved


def parse_import_file(raw_path: str) -> ImportedProcessImprovementFile:
    path = _resolve_import_file(raw_path)
    text = _read_text(path)
    header_fields: dict[str, str] = {}
    suggestions: list[ImportedSuggestion] = []
    current_fields: dict[str, str] | None = None

    def flush_current() -> None:
        nonlocal current_fields
        if current_fields is None:
            return
        owner = _normalize_role(current_fields.get("owner"), field_name="owner")
        header_source = header_fields.get("source", "unknown")
        original_source_ref = _normalize_import_scalar(current_fields.get("source_ref"))
        note = current_fields.get("note")
        suggestions.append(
            ImportedSuggestion(
                role=_role_from_import_source(header_source, owner=owner),
                owner=owner,
                promotion_class=_normalize_promotion_class(current_fields.get("promotion_class")),
                trigger_ref=_normalize_ref(current_fields.get("trigger_ref"), field_name="trigger_ref", fallback="unknown"),
                original_source_ref=original_source_ref,
                symptom=_normalize_free_text(current_fields.get("symptom"), field_name="symptom"),
                process_gap=_normalize_free_text(current_fields.get("process_gap"), field_name="process_gap"),
                suggested_fix=_normalize_free_text(current_fields.get("suggested_fix"), field_name="suggested_fix"),
                extra_note=_normalize_import_scalar(note),
            )
        )
        current_fields = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if IMPORT_SUGGESTION_HEADING_RE.match(line):
            flush_current()
            current_fields = {}
            continue
        if current_fields is None:
            header_match = IMPORT_HEADER_FIELD_RE.match(line)
            if header_match:
                header_fields[header_match.group("key").strip().lower()] = _normalize_import_scalar(
                    header_match.group("value")
                )
            continue
        field_match = FIELD_RE.match(line)
        if not field_match:
            raise ValueError(f"Unsupported line inside imported suggestion in {path}: {raw_line!r}")
        current_fields[field_match.group("key").lower()] = field_match.group("value").strip()
    flush_current()

    if not suggestions:
        raise ValueError(f"Missing `## Suggestion` blocks in {path}")

    return ImportedProcessImprovementFile(
        source_path=path,
        source_ref=path.as_posix(),
        source_status=_normalize_import_scalar(header_fields.get("status")),
        source_plan_ref=_normalize_import_scalar(header_fields.get("plan ref")),
        source_label=_normalize_import_scalar(header_fields.get("source")),
        source_date=_normalize_import_scalar(header_fields.get("date")),
        suggestions=tuple(suggestions),
    )


def parse_backlog_text(text: str, *, path: Path, project_root: Path) -> BacklogFile:
    """Parse one raw backlog snapshot without consulting the working tree.

    Range-scoped consumers use this public surface for ``git show`` BASE/HEAD
    snapshots.  Keeping the parser here prevents packetization from growing a
    second, subtly different interpretation of process-improvement rows.
    """
    lines = text.splitlines()
    source_ref = None
    for line in lines:
        match = SOURCE_REF_RE.match(line)
        if match:
            source_ref = _normalize_ref(match.group("value"), field_name="source_ref")
            break
    if source_ref is None:
        raise ValueError(f"Missing `**Source ref:**` in {path}")

    in_suggestions = False
    current_id = None
    current_fields: dict[str, str] = {}
    entries: list[BacklogEntry] = []

    def flush_current() -> None:
        nonlocal current_id, current_fields
        if current_id is None:
            return
        entry = BacklogEntry(
            entry_id=current_id,
            status=_normalize_status(current_fields.get("status")),
            priority=_normalize_priority(current_fields.get("priority")),
            role=_normalize_role(current_fields.get("role"), field_name="role"),
            owner=_normalize_role(current_fields.get("owner"), field_name="owner"),
            promotion_class=_normalize_promotion_class(current_fields.get("promotion_class")),
            target_canon_path=_normalize_optional_path(current_fields.get("target_canon_path")),
            target_repo_scope=_normalize_target_repo_scope(current_fields.get("target_repo_scope")),
            delivery_mode=_normalize_delivery_mode(current_fields.get("delivery_mode")),
            execution_kind=_normalize_execution_kind(current_fields.get("execution_kind")),
            execution_ref=_normalize_optional_ref(current_fields.get("execution_ref"), field_name="execution_ref"),
            delivery_refs=_normalize_delivery_refs(current_fields.get("delivery_refs")),
            handled_ref=_normalize_optional_ref(current_fields.get("handled_ref"), field_name="handled_ref"),
            promoted_at=_normalize_optional_timestamp(current_fields.get("promoted_at"), field_name="promoted_at"),
            handled_at=_normalize_optional_timestamp(current_fields.get("handled_at"), field_name="handled_at"),
            trigger_ref=_normalize_ref(current_fields.get("trigger_ref"), field_name="trigger_ref"),
            source_ref=_normalize_source_ref_for_lane(
                current_fields.get("source_ref"),
                lane_source_ref=source_ref,
            ),
            symptom=_normalize_free_text(current_fields.get("symptom"), field_name="symptom"),
            process_gap=_normalize_free_text(current_fields.get("process_gap"), field_name="process_gap"),
            suggested_fix=_normalize_free_text(current_fields.get("suggested_fix"), field_name="suggested_fix"),
            created_at=_normalize_ref(current_fields.get("created_at"), field_name="created_at"),
            triage_note=_normalize_ref(current_fields.get("triage_note"), field_name="triage_note", fallback="none"),
        )
        _validate_execution_contract(entry)
        entries.append(entry)
        current_id = None
        current_fields = {}

    for line in lines:
        if SUGGESTIONS_HEADING_RE.match(line):
            in_suggestions = True
            continue
        if in_suggestions and H2_RE.match(line):
            flush_current()
            break
        if not in_suggestions:
            continue
        heading = H3_RE.match(line)
        if heading:
            flush_current()
            title = heading.group("title").strip()
            if not ENTRY_ID_RE.match(title):
                raise ValueError(f"Unsupported entry heading in {path}: {title!r}")
            current_id = title
            continue
        field_match = FIELD_RE.match(line)
        if field_match and current_id is not None:
            current_fields[field_match.group("key").lower()] = field_match.group("value").strip()
            continue

    flush_current()
    return BacklogFile(path=path, source_ref=source_ref, entries=tuple(entries))


def parse_backlog_file(path: Path, project_root: Path) -> BacklogFile:
    """Parse one on-disk raw backlog file through :func:`parse_backlog_text`."""

    return parse_backlog_text(_read_text(path), path=path, project_root=project_root)


def backlog_entry_line_numbers(path: Path) -> dict[str, int]:
    line_numbers: dict[str, int] = {}
    for line_no, line in enumerate(_read_text(path).splitlines(), start=1):
        heading = H3_RE.match(line)
        if not heading:
            continue
        title = heading.group("title").strip()
        if ENTRY_ID_RE.match(title):
            line_numbers[title] = line_no
    return line_numbers


def render_backlog_text(source_ref: str, entries: Iterable[BacklogEntry]) -> str:
    rendered_entries = list(entries)
    lines = [
        f"# Process improvements backlog — {_backlog_title(source_ref)}",
        "",
        f"**Date:** {_now_local()}",
        f"**Source ref:** `{source_ref}`",
        "**Status:** Draft",
        "",
        "Зачем этот файл: держать raw process-improvement suggestions отдельно от обычных follow-ups и канонических doc edits.",
        "",
        "Правила:",
        "- Truth surface = блоки `### PI-...` ниже; derived surfaces `index.md`, `deferred.md`, `promotion_surface.md` пересобираются helper'ом.",
        "- Literal no-op `NO PROCESS IMPROVEMENTS — why: <reason_code>` не materialize-ится как backlog row.",
        "- Wave 1 ограничен `collect + triage`: promotion paths фиксируются literal fields, но не auto-promote логикой.",
        "- Owner-facing `urgency` хранится в existing `priority`; отдельное поле `urgency` не добавляется.",
        "- Mature rows фиксируют non-`P?` `priority`, `target_canon_path`, `target_repo_scope`, `delivery_mode`, `execution_kind`, `execution_ref`, `delivery_refs`, `handled_ref`, `promoted_at`, `handled_at`.",
        "",
        "## Suggestions (truth)",
    ]
    if not rendered_entries:
        lines.append("- none")
    for entry in rendered_entries:
        lines.extend(
            [
                f"### {entry.entry_id}",
                f"- status: `{entry.status}`",
                f"- priority: `{entry.priority}`",
                f"- role: `{entry.role}`",
                f"- owner: `{entry.owner}`",
                f"- promotion_class: `{entry.promotion_class}`",
                f"- target_canon_path: `{entry.target_canon_path}`",
                f"- target_repo_scope: `{entry.target_repo_scope}`",
                f"- delivery_mode: `{entry.delivery_mode}`",
                f"- execution_kind: `{entry.execution_kind}`",
                f"- execution_ref: `{entry.execution_ref}`",
                f"- delivery_refs: `{entry.delivery_refs}`",
                f"- handled_ref: `{entry.handled_ref}`",
                f"- promoted_at: `{entry.promoted_at}`",
                f"- handled_at: `{entry.handled_at}`",
                f"- trigger_ref: `{entry.trigger_ref}`",
                f"- source_ref: `{entry.source_ref}`",
                f"- symptom: `{entry.symptom}`",
                f"- process_gap: `{entry.process_gap}`",
                f"- suggested_fix: `{entry.suggested_fix}`",
                f"- created_at: `{entry.created_at}`",
                f"- triage_note: `{entry.triage_note}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Notes",
            "- Если suggestion уже promoted в live plan/canon/helper, triage helper должен обновить `status`, `target_canon_path`, `target_repo_scope`, `delivery_mode`, а не переписывать historical fields по памяти.",
            "- `promoted`/`handled` rows должны хранить literal execution refs; `delivery_refs` допускает только `null` или `; `-separated literal refs.",
            "- `triaged` rows требуют non-`P?` `priority`, literal target/delivery carrier и execution/delivery refs либо explicit `triage_note` decision.",
            "- `deferred` rows должны хранить owner, reason/revisit trigger в `triage_note` и literal `delivery_refs` либо explicit null-delivery reason.",
            "- `docs/followups/*` остаётся отдельной carrier family: process-improvement row не дублируется туда без отдельного явного follow-up decision.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _summary_stamp() -> str:
    return _now_local()


def _record_from_entry(entry: BacklogEntry, *, file_rel: str) -> dict[str, str]:
    return {
        "file": file_rel,
        "entry_id": entry.entry_id,
        "status": entry.status,
        "priority": entry.priority,
        "role": entry.role,
        "owner": entry.owner,
        "promotion_class": entry.promotion_class,
        "target_canon_path": entry.target_canon_path,
        "target_repo_scope": entry.target_repo_scope,
        "delivery_mode": entry.delivery_mode,
        "execution_kind": entry.execution_kind,
        "execution_ref": entry.execution_ref,
        "delivery_refs": entry.delivery_refs,
        "handled_ref": entry.handled_ref,
        "promoted_at": entry.promoted_at,
        "handled_at": entry.handled_at,
        "trigger_ref": entry.trigger_ref,
        "source_ref": entry.source_ref,
        "symptom": entry.symptom,
        "triage_note": entry.triage_note,
    }


def _render_index_summary(backlogs: Iterable[BacklogFile], *, project_root: Path) -> str:
    rows = []
    for backlog in backlogs:
        file_rel = backlog.path.relative_to(project_root).as_posix()
        entries = list(backlog.entries)
        counts = {
            "open": sum(1 for entry in entries if entry.status == "open"),
            "deferred": sum(1 for entry in entries if entry.status == "deferred"),
            "promoted": sum(1 for entry in entries if entry.status == "promoted"),
            "handled": sum(1 for entry in entries if entry.status == "handled"),
        }
        rows.append((file_rel, backlog.source_ref, len(entries), counts))

    lines = [
        INDEX_AUTO_START,
        "## Live backlog summary (auto)",
        f"_Auto-generated by `scripts/process_improvements_collect.py` on {_summary_stamp()}._",
        PROCESS_DERIVED_BANNER_LINE,
        "",
    ]
    if not rows:
        lines.append("- none")
        lines.append(INDEX_AUTO_END)
        return "\n".join(lines)

    lines.extend(
        [
            "| File | Source ref | Entries | Open | Deferred | Promoted | Handled |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for file_rel, source_ref, total, counts in rows:
        lines.append(
            f"| `{file_rel}` | `{source_ref}` | {total} | {counts['open']} | {counts['deferred']} | {counts['promoted']} | {counts['handled']} |"
        )
    lines.append("")
    lines.append(INDEX_AUTO_END)
    return "\n".join(lines)


def _render_deferred_summary(backlogs: Iterable[BacklogFile], *, project_root: Path) -> str:
    rows: list[dict[str, str]] = []
    for backlog in backlogs:
        file_rel = backlog.path.relative_to(project_root).as_posix()
        for entry in backlog.entries:
            if entry.status not in DEFERRED_STATUSES:
                continue
            rows.append(_record_from_entry(entry, file_rel=file_rel))

    lines = [
        DEFERRED_AUTO_START,
        "## Deferred suggestions (auto)",
        f"_Auto-generated by `scripts/process_improvements_collect.py` on {_summary_stamp()}._",
        PROCESS_DERIVED_BANNER_LINE,
        "",
    ]
    if not rows:
        lines.append("- none")
        lines.append(DEFERRED_AUTO_END)
        return "\n".join(lines)

    lines.extend(
        [
            "| Entry | Source ref | Role | Owner | Status | Promotion class | Delivery refs | Trigger ref |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in rows:
        lines.append(
            f"| `{row['entry_id']}` | `{row['source_ref']}` | `{row['role']}` | `{row['owner']}` | `{row['status']}` | `{row['promotion_class']}` | `{row['delivery_refs']}` | `{row['trigger_ref']}` |"
        )
    lines.append("")
    lines.append(DEFERRED_AUTO_END)
    return "\n".join(lines)


def _render_promotion_summary(backlogs: Iterable[BacklogFile], *, project_root: Path) -> str:
    rows: list[dict[str, str]] = []
    for backlog in backlogs:
        file_rel = backlog.path.relative_to(project_root).as_posix()
        for entry in backlog.entries:
            if entry.status not in PROMOTION_SURFACE_STATUSES:
                continue
            rows.append(_record_from_entry(entry, file_rel=file_rel))

    lines = [
        PROMOTION_AUTO_START,
        "## Promotion surface (auto)",
        f"_Auto-generated by `scripts/process_improvements_collect.py` on {_summary_stamp()}._",
        PROCESS_DERIVED_BANNER_LINE,
        "",
    ]
    if not rows:
        lines.append("- none")
        lines.append(PROMOTION_AUTO_END)
        return "\n".join(lines)

    lines.extend(
        [
            "| Entry | Source ref | Status | Priority | Owner | Promotion class | Target canon path | Target repo scope | Delivery mode | Execution kind | Execution ref | Delivery refs | Handled ref | Promoted at | Handled at | Triage note | Symptom |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in rows:
        lines.append(
            f"| `{row['entry_id']}` | `{row['source_ref']}` | `{row['status']}` | `{row['priority']}` | `{row['owner']}` | `{row['promotion_class']}` | `{row['target_canon_path']}` | `{row['target_repo_scope']}` | `{row['delivery_mode']}` | `{row['execution_kind']}` | `{row['execution_ref']}` | `{row['delivery_refs']}` | `{row['handled_ref']}` | `{row['promoted_at']}` | `{row['handled_at']}` | `{row['triage_note']}` | `{row['symptom']}` |"
        )
    lines.append("")
    lines.append(PROMOTION_AUTO_END)
    return "\n".join(lines)


def _rebuild_derived_surfaces(
    project_root: Path,
    *,
    context: ContractContext,
    first_effect_guarded: bool = False,
) -> dict[str, str]:
    _ensure_derived_surface_docs(
        project_root,
        context=context,
        first_effect_guarded=first_effect_guarded,
    )
    backlogs = [parse_backlog_file(path, project_root) for path in iter_backlog_paths(project_root)]

    surfaces = (
        (INDEX_PATH, INDEX_AUTO_START, INDEX_AUTO_END, _render_index_summary(backlogs, project_root=project_root)),
        (DEFERRED_PATH, DEFERRED_AUTO_START, DEFERRED_AUTO_END, _render_deferred_summary(backlogs, project_root=project_root)),
        (PROMOTION_PATH, PROMOTION_AUTO_START, PROMOTION_AUTO_END, _render_promotion_summary(backlogs, project_root=project_root)),
    )

    updated: dict[str, str] = {}
    for rel_path, start_marker, end_marker, rendered in surfaces:
        path = project_root / rel_path
        current = _read_text(path)
        next_text = _replace_auto_block(current, start_marker, end_marker, rendered)
        _write_text(path, next_text, context=context)
        updated[rel_path.as_posix()] = path.relative_to(project_root).as_posix()
    return updated


def rebuild_derived_surfaces(
    project_root: Path,
    *,
    context: ContractContext | None = None,
) -> dict[str, str]:
    writer_context = _private_writer_context(project_root, context)
    return _rebuild_derived_surfaces(
        project_root,
        context=writer_context,
        first_effect_guarded=True,
    )


def _render_derived_surface_blocks(project_root: Path) -> tuple[tuple[Path, str, str, str], ...]:
    backlogs = [parse_backlog_file(path, project_root) for path in iter_backlog_paths(project_root)]
    return (
        (INDEX_PATH, INDEX_AUTO_START, INDEX_AUTO_END, _render_index_summary(backlogs, project_root=project_root)),
        (
            DEFERRED_PATH,
            DEFERRED_AUTO_START,
            DEFERRED_AUTO_END,
            _render_deferred_summary(backlogs, project_root=project_root),
        ),
        (
            PROMOTION_PATH,
            PROMOTION_AUTO_START,
            PROMOTION_AUTO_END,
            _render_promotion_summary(backlogs, project_root=project_root),
        ),
    )


def _extract_generated_block(
    text: str,
    *,
    start_marker: str,
    end_marker: str,
) -> tuple[str | None, tuple[str, ...]]:
    start_count = text.count(start_marker)
    end_count = text.count(end_marker)
    if start_count == 0 or end_count == 0:
        return None, ("missing_generated_block",)
    if start_count != 1 or end_count != 1:
        return None, ("multiple_generated_blocks",)

    start = text.index(start_marker)
    content_start = start + len(start_marker)
    end = text.index(end_marker)
    if end <= content_start:
        return None, ("malformed_generated_block",)
    return text[start : end + len(end_marker)], ()


def _normalize_generated_block(block: str) -> tuple[str, bool]:
    timestamp_seen = False
    lines: list[str] = []
    for line in block.splitlines():
        if PROCESS_TIMESTAMP_LINE_RE.match(line):
            lines.append(PROCESS_TIMESTAMP_PLACEHOLDER)
            timestamp_seen = True
        else:
            lines.append(line)
    return "\n".join(lines).rstrip() + "\n", timestamp_seen


def _check_derived_surface(
    *,
    project_root: Path,
    rel_path: Path,
    start_marker: str,
    end_marker: str,
    expected_block: str,
) -> dict[str, object]:
    path = project_root / rel_path
    if not path.exists():
        return {
            "path": rel_path.as_posix(),
            "ok": False,
            "issues": ["missing_surface"],
            "timestamp_ignored": False,
            "diff": [],
            "would_write": False,
        }

    live_block, marker_issues = _extract_generated_block(
        _read_text(path),
        start_marker=start_marker,
        end_marker=end_marker,
    )
    if marker_issues:
        return {
            "path": rel_path.as_posix(),
            "ok": False,
            "issues": list(marker_issues),
            "timestamp_ignored": False,
            "diff": [],
            "would_write": False,
        }
    assert live_block is not None

    expected_normalized, _ = _normalize_generated_block(expected_block)
    live_normalized, live_timestamp_seen = _normalize_generated_block(live_block)

    issues: list[str] = []
    if not live_timestamp_seen:
        issues.append("missing_timestamp_line")
    banner_lines = [
        line for line in live_block.splitlines()
        if line in (PROCESS_DERIVED_BANNER_LINE, _LEGACY_PROCESS_DERIVED_BANNER_LINE)
    ]
    if not banner_lines:
        issues.append("missing_banner_line")
    elif banner_lines == [_LEGACY_PROCESS_DERIVED_BANNER_LINE]:
        # Read the exact previous generated format without rewriting it or
        # granting its command text authority. The full block comparison still
        # rejects duplicate/moved banners and every other content difference.
        live_normalized = "\n".join(
            PROCESS_DERIVED_BANNER_LINE if line == _LEGACY_PROCESS_DERIVED_BANNER_LINE else line
            for line in live_normalized.splitlines()
        ) + "\n"

    diff: list[str] = []
    if expected_normalized != live_normalized:
        issues.append("generated_content_mismatch")
        diff = list(
            difflib.unified_diff(
                expected_normalized.splitlines(),
                live_normalized.splitlines(),
                fromfile="expected",
                tofile="live",
                lineterm="",
            )
        )

    return {
        "path": rel_path.as_posix(),
        "ok": not issues,
        "issues": issues,
        "timestamp_ignored": live_timestamp_seen,
        "diff": diff,
        "would_write": False,
    }


def check_derived_surfaces(project_root: Path) -> dict[str, object]:
    surfaces = [
        _check_derived_surface(
            project_root=project_root,
            rel_path=rel_path,
            start_marker=start_marker,
            end_marker=end_marker,
            expected_block=expected_block,
        )
        for rel_path, start_marker, end_marker, expected_block in _render_derived_surface_blocks(project_root)
    ]
    ok = all(bool(surface["ok"]) for surface in surfaces)
    return {
        "state": "derived_surfaces_check",
        "status": "ok" if ok else "failed",
        "ok": ok,
        "surfaces": surfaces,
        "would_write": False,
    }


def _collect_process_improvements_impl(
    *,
    project_root: Path,
    role: str,
    source_ref: str,
    text: str,
    context: ContractContext | None = None,
    engaged_public: bool = False,
    active_admission: dict[str, object] | None = None,
    repair_derived: bool = False,
) -> dict[str, object]:
    parsed = parse_process_improvements_section(text, role=role, default_source_ref=source_ref)
    if parsed["state"] == "no_process_improvements":
        return {
            "state": "no_process_improvements",
            "reason_code": parsed["reason_code"],
            "created": [],
            "duplicates": [],
            "backlog_files": [],
            "derived_surfaces": {},
        }

    suggestions = list(parsed["suggestions"])
    created: list[dict[str, str]] = []
    duplicates: list[dict[str, str]] = []
    touched_files: set[str] = set()

    grouped: dict[str, list[ParsedSuggestion]] = {}
    for suggestion in suggestions:
        grouped.setdefault(suggestion.source_ref, []).append(suggestion)

    for grouped_source_ref, grouped_suggestions in grouped.items():
        backlog_rel = backlog_rel_path_for_source_ref(grouped_source_ref)
        backlog_path = project_root / backlog_rel
        if engaged_public:
            loaded_backlog = _safe_pi_read_optional(project_root, backlog_rel)
            if loaded_backlog is None:
                existing_entries = []
            else:
                try:
                    backlog_text = loaded_backlog[0].decode("utf-8", "strict")
                except UnicodeDecodeError as exc:
                    raise ValueError(f"engaged process-improvement backlog is not UTF-8: {backlog_rel}") from exc
                existing_entries = list(
                    parse_backlog_text(backlog_text, path=backlog_path, project_root=project_root).entries
                )
        elif backlog_path.exists():
            backlog = parse_backlog_file(backlog_path, project_root)
            existing_entries = list(backlog.entries)
        else:
            existing_entries = []

        dedup_key = _engaged_entry_key if engaged_public else _entry_key
        existing_keys = {dedup_key(entry): entry for entry in existing_entries}
        next_entries = list(existing_entries)
        next_id = _next_entry_id(next_entries)
        next_index = int(next_id.split("-")[1])

        for suggestion in grouped_suggestions:
            key = dedup_key(suggestion)
            if key in existing_keys:
                duplicates.append(
                    {
                        "file": backlog_rel,
                        "entry_id": existing_keys[key].entry_id,
                        "source_ref": suggestion.source_ref,
                    }
                )
                continue
            entry = BacklogEntry(
                entry_id=f"PI-{next_index:03d}",
                status="open",
                priority="P?",
                role=suggestion.role,
                owner=suggestion.owner,
                promotion_class=suggestion.promotion_class,
                target_canon_path="null",
                target_repo_scope="null",
                delivery_mode="null",
                execution_kind="null",
                execution_ref="null",
                delivery_refs="null",
                handled_ref="null",
                promoted_at="null",
                handled_at="null",
                trigger_ref=suggestion.trigger_ref,
                source_ref=suggestion.source_ref,
                symptom=suggestion.symptom,
                process_gap=suggestion.process_gap,
                suggested_fix=suggestion.suggested_fix,
                created_at=_now_local(),
                triage_note="auto-collected from memory-finalize general lane",
            )
            next_entries.append(entry)
            existing_keys[key] = entry
            created.append(
                {
                    "file": backlog_rel,
                    "entry_id": entry.entry_id,
                    "source_ref": entry.source_ref,
                }
            )
            next_index += 1

        if len(next_entries) != len(existing_entries):
            rendered_backlog = render_backlog_text(grouped_source_ref, next_entries)
            if engaged_public:
                assert context is not None
                _safe_pi_write_text(
                    project_root,
                    backlog_rel,
                    rendered_backlog,
                    context=context,
                    active_admission=active_admission,
                )
            else:
                _write_text(backlog_path, rendered_backlog, context=context)
            touched_files.add(backlog_rel)

    if touched_files or repair_derived:
        if engaged_public:
            assert context is not None
            derived_surfaces = _safe_pi_rebuild_derived_surfaces(
                project_root,
                context=context,
                active_admission=active_admission,
            )
        else:
            derived_surfaces = _rebuild_derived_surfaces(project_root, context=context)
    else:
        derived_surfaces = {}
    return {
        "state": "collected",
        "created": created,
        "duplicates": duplicates,
        "backlog_files": sorted(touched_files),
        "derived_surfaces": derived_surfaces,
    }


def _collect_process_improvements(
    *,
    project_root: Path,
    role: str,
    source_ref: str,
    text: str | bytes,
    followups_capture_cycle_id: str | None = None,
    write_receipt: bool = True,
    context: ContractContext,
    engaged_public: bool = False,
    active_admission: dict[str, object] | None = None,
) -> dict[str, object]:
    writer_context = context
    normalized_role = _normalize_role(role, field_name="role")
    normalized_cycle_id = _normalize_followups_capture_cycle_id(followups_capture_cycle_id)
    raw_input = text.encode("utf-8") if isinstance(text, str) else bytes(text)
    input_sha256 = hashlib.sha256(raw_input).hexdigest()
    before_objects = (
        _safe_pi_object_map(project_root, source_ref)
        if engaged_public
        else _capture_pi_object_map(project_root, source_ref)
    )
    existing_v2_receipt: dict[str, object] | None = None
    recovery_original_before: dict[str, dict[str, object]] | None = None
    recovery_partial = False
    v2_admission_complete = normalized_cycle_id is None
    if normalized_cycle_id is not None and write_receipt:
        replay, existing_v2_receipt = _admit_v2_replay(
            project_root=project_root,
            source_ref=source_ref,
            role=normalized_role,
            followups_capture_cycle_id=normalized_cycle_id,
            input_sha256=input_sha256,
            live_objects=before_objects,
            engaged_public=engaged_public,
        )
        v2_admission_complete = True
        if replay is not None:
            return replay
        if existing_v2_receipt is not None:
            # Legacy and engaged V2 recovery share one meaning: the continuation
            # owns the whole effect since the blocked attempt's original before.
            recovery_original_before, recovery_blocked_after = _validate_v2_capture_receipt(
                existing_v2_receipt,
                source_ref=source_ref,
                role=normalized_role,
                followups_capture_cycle_id=normalized_cycle_id,
            )
            # Only a blocked attempt that already changed PI objects owns derived
            # repair; an effect-free one must not rewrite timestamped surfaces.
            recovery_partial = recovery_original_before != recovery_blocked_after
    try:
        decoded_text = raw_input.decode("utf-8")
        payload = _collect_process_improvements_impl(
            project_root=project_root,
            role=normalized_role,
            source_ref=source_ref,
            text=decoded_text,
            context=writer_context,
            engaged_public=engaged_public,
            active_admission=active_admission,
            repair_derived=recovery_partial,
        )
        after_objects = (
            _safe_pi_object_map(project_root, source_ref)
            if engaged_public
            else _capture_pi_object_map(project_root, source_ref)
        )
        payload["before_process_improvement_files"] = (
            recovery_original_before
            if recovery_original_before is not None
            else before_objects
        )
        payload["after_process_improvement_files"] = after_objects
        payload["process_improvement_path_results"] = _capture_pi_path_results(
            payload["before_process_improvement_files"], after_objects
        )
        capture_state, reason_code = _capture_state_from_payload(payload)
        if (
            recovery_original_before is not None
            and payload["process_improvement_path_results"]
            and capture_state in {"clean_noop", "already_tracked"}
        ):
            # The blocked attempt already wrote this role's rows, so the retry
            # sees duplicates; the receipt must describe the whole before->after
            # effect that it now owns.
            capture_state, reason_code = "materialized", "structured_suggestions_materialized"
        receipt_path = None
        if write_receipt:
            if normalized_cycle_id is None:
                receipt_path = _write_capture_receipt(
                    project_root=project_root,
                    role=normalized_role,
                    source_ref=source_ref,
                    capture_state=capture_state,
                    reason_code=reason_code,
                    followups_capture_cycle_id=None,
                    payload=payload,
                    context=writer_context,
                )
            else:
                if capture_state not in CAPTURE_CONTINUATION_STATES:
                    raise ValueError("process-improvement v2 blocked receipt cannot be replaced by another blocked result")
                receipt_path = _write_v2_capture_receipt(
                    project_root=project_root,
                    source_ref=source_ref,
                    role=normalized_role,
                    followups_capture_cycle_id=normalized_cycle_id,
                    receipt=_v2_receipt_payload(
                        role=normalized_role,
                        source_ref=source_ref,
                        followups_capture_cycle_id=normalized_cycle_id,
                        input_sha256=input_sha256,
                        capture_state=capture_state,
                        reason_code=reason_code,
                        payload=payload,
                    ),
                    replace_blocked=existing_v2_receipt is not None,
                    context=writer_context,
                    active_admission=active_admission,
                    engaged_public=engaged_public,
                )
        payload["process_improvement_capture_state"] = capture_state
        payload["process_improvement_capture_reason"] = reason_code
        payload["process_improvement_receipt_path"] = receipt_path or "N/A (why=receipt disabled)"
        payload["followups_capture_cycle_id"] = normalized_cycle_id or "none"
        if normalized_cycle_id is not None:
            payload["input_sha256"] = input_sha256
        return payload
    except Exception as exc:
        if write_receipt:
            try:
                after_objects = (
                    _safe_pi_object_map(project_root, source_ref)
                    if engaged_public
                    else _capture_pi_object_map(project_root, source_ref)
                )
            except Exception:
                # Blocked-recovery admission compares a V2 after-map with the live
                # map, so a V2 receipt never records an unobserved (empty) one.
                after_objects = None if engaged_public or normalized_cycle_id is not None else {}
            failure_before = (
                recovery_original_before
                if recovery_original_before is not None
                else before_objects
            )
            failure_payload = {
                "before_process_improvement_files": failure_before,
                "after_process_improvement_files": after_objects,
                "process_improvement_path_results": (
                    _capture_pi_path_results(failure_before, after_objects)
                    if after_objects is not None
                    else []
                ),
            }
            if after_objects is None:
                pass
            elif normalized_cycle_id is None:
                _write_capture_receipt(
                    project_root=project_root,
                    role=normalized_role,
                    source_ref=source_ref,
                    capture_state="blocked",
                    reason_code="collector_error",
                    followups_capture_cycle_id=None,
                    payload=failure_payload,
                    error=str(exc),
                    context=writer_context,
                )
            elif v2_admission_complete:
                # A failed recovery replaces its blocked receipt so the recorded
                # after-map stays the live map that the next admission requires.
                with contextlib.suppress(Exception):
                    _write_v2_capture_receipt(
                        project_root=project_root,
                        source_ref=source_ref,
                        role=normalized_role,
                        followups_capture_cycle_id=normalized_cycle_id,
                        receipt=_v2_receipt_payload(
                            role=normalized_role,
                            source_ref=source_ref,
                            followups_capture_cycle_id=normalized_cycle_id,
                            input_sha256=input_sha256,
                            capture_state="blocked",
                            reason_code="collector_error",
                            payload=failure_payload,
                            error=str(exc),
                        ),
                        replace_blocked=existing_v2_receipt is not None,
                        context=writer_context,
                        active_admission=active_admission,
                        engaged_public=engaged_public,
                    )
        raise


def collect_process_improvements(
    *,
    project_root: Path,
    role: str,
    source_ref: str,
    text: str | bytes,
    followups_capture_cycle_id: str | None = None,
    write_receipt: bool = True,
    context: ContractContext | None = None,
) -> dict[str, object]:
    writer_context = _private_writer_context(project_root, context)
    return _collect_process_improvements(
        project_root=project_root,
        role=role,
        source_ref=source_ref,
        text=text,
        followups_capture_cycle_id=followups_capture_cycle_id,
        write_receipt=write_receipt,
        context=writer_context,
    )


def import_process_improvements(
    *,
    project_root: Path,
    import_files: Iterable[str],
    apply: bool,
    context: ContractContext | None = None,
) -> dict[str, object]:
    writer_context = _private_writer_context(project_root, context)
    parsed_files = [parse_import_file(raw_path) for raw_path in import_files]
    if not parsed_files:
        raise ValueError("At least one --import-file path is required")

    imports: list[dict[str, object]] = []
    created: list[dict[str, str]] = []
    duplicates: list[dict[str, str]] = []
    touched_files: set[str] = set()

    for imported in parsed_files:
        backlog_rel = backlog_rel_path_for_source_ref(imported.source_ref)
        backlog_path = project_root / backlog_rel
        existing_entries = parse_backlog_file(backlog_path, project_root).entries if backlog_path.exists() else ()
        existing_keys = {_entry_key(entry): entry for entry in existing_entries}
        next_entries = list(existing_entries)
        next_index = int(_next_entry_id(next_entries).split("-")[1])
        import_entries: list[dict[str, str]] = []

        for suggestion in imported.suggestions:
            triage_note = _triage_note_from_parts(
                (
                    ("imported_from", imported.source_ref),
                    ("source_status", imported.source_status),
                    ("source_plan_ref", imported.source_plan_ref),
                    ("source_ref_original", suggestion.original_source_ref),
                    ("source_note", suggestion.extra_note),
                )
            )
            candidate = BacklogEntry(
                entry_id=f"PI-{next_index:03d}",
                status="open",
                priority="P?",
                role=suggestion.role,
                owner=suggestion.owner,
                promotion_class=suggestion.promotion_class,
                target_canon_path="null",
                target_repo_scope="null",
                delivery_mode="null",
                execution_kind="null",
                execution_ref="null",
                delivery_refs="null",
                handled_ref="null",
                promoted_at="null",
                handled_at="null",
                trigger_ref=suggestion.trigger_ref,
                source_ref=imported.source_ref,
                symptom=suggestion.symptom,
                process_gap=suggestion.process_gap,
                suggested_fix=suggestion.suggested_fix,
                created_at=_now_local(),
                triage_note=triage_note,
            )
            key = _entry_key(candidate)
            if key in existing_keys:
                existing = existing_keys[key]
                entry_id = existing.entry_id
                report_status = existing.status
                report_triage_note = existing.triage_note
                duplicates.append({"file": backlog_rel, "entry_id": entry_id, "source_ref": imported.source_ref})
            else:
                entry_id = candidate.entry_id
                report_status = candidate.status
                report_triage_note = candidate.triage_note
                if apply:
                    next_entries.append(candidate)
                    existing_keys[key] = candidate
                    created.append({"file": backlog_rel, "entry_id": entry_id, "source_ref": imported.source_ref})
                    next_index += 1
            import_entries.append(
                {
                    "entry_id": entry_id,
                    "owner": suggestion.owner,
                    "role": suggestion.role,
                    "promotion_class": suggestion.promotion_class,
                    "status": report_status,
                    "trigger_ref": suggestion.trigger_ref,
                    "original_source_ref": suggestion.original_source_ref,
                    "symptom": suggestion.symptom,
                    "triage_note": report_triage_note,
                }
            )

        if apply and len(next_entries) != len(existing_entries):
            _write_text(
                backlog_path,
                render_backlog_text(imported.source_ref, next_entries),
                context=writer_context,
            )
            touched_files.add(backlog_rel)

        imports.append(
            {
                "source_file": imported.source_ref,
                "source_status": imported.source_status,
                "source_plan_ref": imported.source_plan_ref,
                "source_label": imported.source_label,
                "source_date": imported.source_date,
                "backlog_file": backlog_rel,
                "entries": import_entries,
            }
        )

    derived_surfaces = _rebuild_derived_surfaces(project_root, context=writer_context) if apply and touched_files else {}
    return {
        "state": "imported" if apply else "import_report",
        "mode": "apply" if apply else "report",
        "imports": imports,
        "created": created,
        "duplicates": duplicates,
        "backlog_files": sorted(touched_files),
        "derived_surfaces": derived_surfaces,
    }


def update_backlog_entry(
    *,
    project_root: Path,
    backlog_path: Path,
    entry_id: str,
    status: str | None = None,
    priority: str | None = None,
    owner: str | None = None,
    promotion_class: str | None = None,
    target_canon_path: str | None = None,
    target_repo_scope: str | None = None,
    delivery_mode: str | None = None,
    execution_kind: str | None = None,
    execution_ref: str | None = None,
    delivery_refs: str | None = None,
    handled_ref: str | None = None,
    promoted_at: str | None = None,
    handled_at: str | None = None,
    triage_note: str | None = None,
    context: ContractContext | None = None,
) -> dict[str, object]:
    writer_context = _private_writer_context(project_root, context)
    backlog = parse_backlog_file(backlog_path, project_root)
    entries = list(backlog.entries)
    target_index = next((idx for idx, entry in enumerate(entries) if entry.entry_id == entry_id), None)
    if target_index is None:
        raise ValueError(f"Missing entry `{entry_id}` in {backlog_path.relative_to(project_root).as_posix()}")

    current = entries[target_index]
    next_entry = BacklogEntry(
        entry_id=current.entry_id,
        status=_normalize_status(status or current.status),
        priority=_normalize_priority(priority or current.priority),
        role=current.role,
        owner=_normalize_role(owner or current.owner, field_name="owner"),
        promotion_class=_normalize_promotion_class(promotion_class or current.promotion_class),
        target_canon_path=_normalize_optional_path(target_canon_path or current.target_canon_path),
        target_repo_scope=_normalize_target_repo_scope(target_repo_scope or current.target_repo_scope),
        delivery_mode=_normalize_delivery_mode(delivery_mode or current.delivery_mode),
        execution_kind=_normalize_execution_kind(execution_kind or current.execution_kind),
        execution_ref=_normalize_optional_ref(execution_ref or current.execution_ref, field_name="execution_ref"),
        delivery_refs=_normalize_delivery_refs(delivery_refs or current.delivery_refs),
        handled_ref=_normalize_optional_ref(handled_ref or current.handled_ref, field_name="handled_ref"),
        promoted_at=_normalize_optional_timestamp(promoted_at or current.promoted_at, field_name="promoted_at"),
        handled_at=_normalize_optional_timestamp(handled_at or current.handled_at, field_name="handled_at"),
        trigger_ref=current.trigger_ref,
        source_ref=current.source_ref,
        symptom=current.symptom,
        process_gap=current.process_gap,
        suggested_fix=current.suggested_fix,
        created_at=current.created_at,
        triage_note=_normalize_ref(triage_note or current.triage_note, field_name="triage_note"),
    )
    _validate_execution_contract(next_entry)
    if next_entry.status in STRICT_TRIAGE_CARRIER_STATUSES or next_entry.status in DECISION_NOTE_STATUSES:
        assert_complete_triage_carrier(next_entry)

    entries[target_index] = next_entry
    _write_text(
        backlog_path,
        render_backlog_text(backlog.source_ref, entries),
        context=writer_context,
    )
    derived_surfaces = _rebuild_derived_surfaces(project_root, context=writer_context)
    return {
        "state": "triaged",
        "file": backlog_path.relative_to(project_root).as_posix(),
        "entry_id": next_entry.entry_id,
        "status": next_entry.status,
        "priority": next_entry.priority,
        "owner": next_entry.owner,
        "promotion_class": next_entry.promotion_class,
        "target_canon_path": next_entry.target_canon_path,
        "target_repo_scope": next_entry.target_repo_scope,
        "delivery_mode": next_entry.delivery_mode,
        "execution_kind": next_entry.execution_kind,
        "execution_ref": next_entry.execution_ref,
        "delivery_refs": next_entry.delivery_refs,
        "handled_ref": next_entry.handled_ref,
        "promoted_at": next_entry.promoted_at,
        "handled_at": next_entry.handled_at,
        "triage_note": next_entry.triage_note,
        "derived_surfaces": derived_surfaces,
    }


def _text_payload(payload: dict[str, object]) -> str:
    if payload["state"] == "derived_surfaces_check":
        surfaces = payload.get("surfaces") or []
        if payload["ok"]:
            return "\n".join(
                [
                    "process-improvements-derived-check:",
                    " status=ok",
                    " would_write=false",
                    f" surfaces={len(surfaces)}",
                ]
            )
        lines = [
            "process-improvements-derived-check:",
            " status=failed",
            " would_write=false",
            f" surfaces={len(surfaces)}",
        ]
        for surface in surfaces:
            issues = ",".join(surface.get("issues") or [])
            lines.append(
                f" surface={surface['path']} "
                f"ok={str(surface['ok']).lower()} "
                f"issues={issues or 'none'}"
            )
            diff = surface.get("diff") or []
            if diff:
                lines.append(" diff:")
                lines.extend(str(line) for line in diff[:80])
        return "\n".join(lines)

    if payload["state"] == "derived_surfaces_rebuilt":
        surfaces = payload.get("derived_surfaces") or {}
        return "\n".join(
            [
                "process-improvements:",
                " state=derived_surfaces_rebuilt",
                f" surfaces={','.join(sorted(surfaces)) if surfaces else 'none'}",
            ]
        )

    if payload["state"] == "no_process_improvements":
        return "\n".join(
            [
                "process-improvements:",
                " state=no_process_improvements",
                f" reason={payload['reason_code']}",
                f" process_improvement_capture_state={payload.get('process_improvement_capture_state', 'unknown')}",
                f" process_improvement_capture_reason={payload.get('process_improvement_capture_reason', 'unknown')}",
                f" process_improvement_receipt_path={payload.get('process_improvement_receipt_path', 'unknown')}",
            ]
        )

    if payload["state"] == "triaged":
        return "\n".join(
            [
                "process-improvements:",
                " state=triaged",
                f" file={payload['file']}",
                f" entry_id={payload['entry_id']}",
                f" status={payload['status']}",
                f" priority={payload['priority']}",
                f" owner={payload['owner']}",
                f" target_canon_path={payload['target_canon_path']}",
                f" target_repo_scope={payload['target_repo_scope']}",
                f" delivery_mode={payload['delivery_mode']}",
                f" execution_kind={payload['execution_kind']}",
                f" execution_ref={payload['execution_ref']}",
                f" delivery_refs={payload['delivery_refs']}",
                f" handled_ref={payload['handled_ref']}",
                f" promoted_at={payload['promoted_at']}",
                f" handled_at={payload['handled_at']}",
            ]
        )

    if payload["state"] in {"import_report", "imported"}:
        imports = payload.get("imports") or []
        created = payload.get("created") or []
        duplicates = payload.get("duplicates") or []
        files = payload.get("backlog_files") or []
        lines = [
            "process-improvements:",
            f" state={payload['state']}",
            f" mode={payload['mode']}",
            f" imports={len(imports)}",
            f" created={len(created)}",
            f" duplicates={len(duplicates)}",
            f" backlog_files={','.join(files) if files else 'none'}",
        ]
        for item in imports:
            lines.append(f" import_file={item['source_file']}")
            lines.append(f" target_backlog={item['backlog_file']}")
        return "\n".join(lines)

    created = payload.get("created") or []
    duplicates = payload.get("duplicates") or []
    files = payload.get("backlog_files") or []
    lines = [
        "process-improvements:",
        f" state={payload['state']}",
        f" created={len(created)}",
        f" duplicates={len(duplicates)}",
        f" backlog_files={','.join(files) if files else 'none'}",
        f" process_improvement_capture_state={payload.get('process_improvement_capture_state', 'unknown')}",
        f" process_improvement_capture_reason={payload.get('process_improvement_capture_reason', 'unknown')}",
        f" process_improvement_receipt_path={payload.get('process_improvement_receipt_path', 'unknown')}",
    ]
    return "\n".join(lines)


def _read_input(raw_path: str) -> bytes:
    if raw_path == "-":
        raw_stdin = getattr(sys.stdin, "buffer", None)
        return raw_stdin.read() if raw_stdin is not None else sys.stdin.read().encode("utf-8")
    return Path(raw_path).read_bytes()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="process_improvements_collect",
        description="Collect structured `Process improvements` suggestions into durable backlog carriers.",
    )
    parser.add_argument("--project-root", default="", help="Repo root (default: cwd).")
    parser.add_argument("--role", help="Role that emitted the `Process improvements` section.")
    parser.add_argument("--source-ref", help="Manager-fed `plan_ref` / durable source reference.")
    parser.add_argument(
        "--followups-capture-cycle-id",
        help="Exact Manager-fed terminal followups cycle UUID for receipt freshness binding.",
    )
    parser.add_argument("--input", default="-", help="Text file with the prompt output, or '-' for stdin.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check committed process-improvements derived surfaces without writing.",
    )
    parser.add_argument(
        "--rebuild-derived",
        action="store_true",
        help="Refresh process-improvements derived surfaces from raw backlog files.",
    )
    parser.add_argument(
        "--import-file",
        action="append",
        default=[],
        help="Explicit external docs/process_improvements/*.md file to import; may be repeated.",
    )
    import_mode = parser.add_mutually_exclusive_group()
    import_mode.add_argument("--report", action="store_true", help="Preview --import-file rows without writing.")
    import_mode.add_argument("--apply", action="store_true", help="Write --import-file rows and derived surfaces.")
    parser.add_argument("--format", choices=("text", "json"), default="text", help="Output format.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    return parser


def main(
    argv: list[str] | None = None,
    *,
    context: ContractContext | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    project_root = resolve_project_root(args.project_root or None)
    if args.check and args.rebuild_derived:
        parser.error("--check and --rebuild-derived are mutually exclusive")
    if args.check:
        if args.import_file or args.report or args.apply or args.role or args.source_ref or args.followups_capture_cycle_id:
            parser.error("--check cannot be combined with collect/import arguments")
        _private_writer_context(project_root, context)
        payload = check_derived_surfaces(project_root)
        if args.json or args.format == "json":
            sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        else:
            stream = sys.stdout if payload["ok"] else sys.stderr
            print(_text_payload(payload), file=stream)
        return 0 if payload["ok"] else 1
    if args.rebuild_derived:
        if args.import_file or args.report or args.apply or args.role or args.source_ref or args.followups_capture_cycle_id:
            parser.error("--rebuild-derived cannot be combined with collect/import arguments")
        payload = {
            "state": "derived_surfaces_rebuilt",
            "derived_surfaces": rebuild_derived_surfaces(project_root, context=context),
        }
    elif args.import_file:
        if args.followups_capture_cycle_id:
            parser.error("--followups-capture-cycle-id is valid only for role collection")
        if not args.report and not args.apply:
            parser.error("--import-file requires either --report or --apply")
        payload = import_process_improvements(
            project_root=project_root,
            import_files=args.import_file,
            apply=bool(args.apply),
            context=context,
        )
    else:
        if args.report or args.apply:
            parser.error("--report/--apply are only valid with --import-file")
        if not args.role or not args.source_ref:
            parser.error("--role and --source-ref are required without --import-file")
        writer_context, engaged_public, active_admission = _general_collection_writer_context(
            project_root,
            role=args.role,
            source_ref=args.source_ref,
            followups_capture_cycle_id=args.followups_capture_cycle_id,
            context=context,
        )
        role = _normalize_role(args.role, field_name="role") if engaged_public else args.role
        source_ref = _normalize_ref(args.source_ref, field_name="source_ref") if engaged_public else args.source_ref
        cycle_id = (
            _normalize_followups_capture_cycle_id(args.followups_capture_cycle_id)
            if engaged_public
            else args.followups_capture_cycle_id
        )
        text = _read_input(args.input)
        if engaged_public:
            _validate_active_general_pi_effect(
                project_root,
                context=writer_context,
                admission=active_admission,
            )
        payload = _collect_process_improvements(
            project_root=project_root,
            role=role,
            source_ref=source_ref,
            text=text,
            followups_capture_cycle_id=cycle_id,
            context=writer_context,
            engaged_public=engaged_public,
            active_admission=active_admission,
        )
    if args.json or args.format == "json":
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    else:
        sys.stdout.write(_text_payload(payload) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

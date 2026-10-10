#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextvars
import fcntl
import functools
import hashlib
import importlib
import json
import os
import re
import stat
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, Callable, Iterator

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

import plan_lint
import plan_status_oracle


STATE_FILE_NAME = ".planveyor.planqueue.json"
LOG_FILE_NAME = ".planveyor.planqueue.log"
LOCK_FILE_NAME = ".planveyor.planqueue.lock"
TXN_FILE_NAME = ".planveyor.planqueue.txn.json"
TXN_VERSION = 1
STATE_VERSION = 1
LOCK_TIMEOUT_SECONDS = 10.0
RECOVERY_COMMAND = "planveyor_q_recover"
ABSENT_STATE_DIGEST = "absent"
LOG_LINE_BREAK_RE = re.compile(r"[\r\n\v\f\x1c-\x1e\x85\u2028\u2029]")
LOG_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")
LOG_DIGEST_RE = re.compile(r"^(?:absent|[0-9a-f]{64})$")
PLAN_LINT_ACTIVATION_BLOCKER_PREFIX = "plan_lint_activation_blocked:"
PLAN_LINT_BLOCKER_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]+")
PLAN_LINT_BLOCKER_ABSOLUTE_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_.~-])/(?:[^\s|;,:()\[\]{}]+(?:/[^\s|;,:()\[\]{}]+)*)?"
)
PLAN_LINT_BLOCKER_WINDOWS_PATH_RE = re.compile(r"(?i)\b[A-Z]:[\\/][^\s|;,:()\[\]{}]*")
VALID_RESUME_PARENT = {"none", "owner-restamp-required", "run-parent-once"}
ACTIVE_STATES = {"pending", "active"}
QUEUE_ACTIVATION_APPROVED_STATES = {"owner_approved", "architect_approved"}
FINAL_STATUS_TO_STATE = {
    "done": "done",
    "superseded": "superseded",
}
ORDINARY_TERMINAL_DISPOSITION = "ordinary"
ACCEPTED_RED_TERMINAL_DISPOSITION = "accepted_red_supersession"
TERMINAL_ADMISSION_ERROR = "terminal_closeout_admission_rejected"
CLOSED_NON_EXECUTABLE_STATE = "closed_non_executable"
SKIPPED_MANAGER_MODE_STATE = "skipped_manager_mode"
FINALIZED_STATES = {
    *FINAL_STATUS_TO_STATE.values(),
    CLOSED_NON_EXECUTABLE_STATE,
    SKIPPED_MANAGER_MODE_STATE,
}
VALID_ITEM_STATES = {*ACTIVE_STATES, *FINALIZED_STATES}
QUEUE_LOOP_STOP_REASONS = {"loop_escalation_recorded", "unchanged_status", "real_loop"}
SMALL_SLICE_SECTION_HEADING_RE = re.compile(r"^\s*##\s+Small-slice conveyor classifier\b", re.IGNORECASE)
ROLLOUT_PACKET_SECTION_HEADING_RE = re.compile(r"^\s*##\s+Rollout packet handoff\b", re.IGNORECASE)
VISUAL_ACCEPTANCE_SECTION_HEADING_RE = re.compile(r"^\s*##\s+Visual Acceptance\b", re.IGNORECASE)
REDUCED_CENSOR_PROFILE = "reduced-same-session-censors"
EXACT_BUNDLE_MATCH = "exact-bundle-match"
FAIL_CLOSED_TO_FULL_CONVEYOR = "fail-closed-to-full-conveyor"
ALLOWED_SMALL_SLICE_BUNDLE_FAMILIES = {"docs-only", "tests-only"}
SMALL_SLICE_CENSOR_ROLES = ("architect_censor", "planner_censor", "coder_censor")

class _CloseoutCandidateUnset:
    """Private sentinel that keeps an omitted candidate distinct from ``None``."""


_CLOSEOUT_CANDIDATE_UNSET = _CloseoutCandidateUnset()


@dataclass(frozen=True)
class SmallSliceCarrier:
    requested_profile: str | None
    expected_bundle_family: str | None
    helper_validation: str | None
    drift_behavior: str | None


class QueueError(RuntimeError):
    def __init__(self, message: str, *, payload: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.payload = payload


class _PendingActivationModeReadFailure(RuntimeError):
    """Private signal for a pending candidate unreadable during mode admission."""


@dataclass(frozen=True)
class QueuePaths:
    root: Path
    state_path: Path
    log_path: Path
    lock_path: Path | None = None
    txn_path: Path | None = None
    context: ContractContext | None = None

    def __post_init__(self) -> None:
        if self.lock_path is None:
            object.__setattr__(self, "lock_path", self.root / LOCK_FILE_NAME)
        if self.txn_path is None:
            object.__setattr__(self, "txn_path", self.root / TXN_FILE_NAME)

    def required_lock_path(self) -> Path:
        """Return the post-init lock-path invariant as a concrete path."""

        assert self.lock_path is not None
        return self.lock_path

    def required_txn_path(self) -> Path:
        """Return the post-init transaction-path invariant as a concrete path."""

        assert self.txn_path is not None
        return self.txn_path


_HELD_EXCLUSIVE_ROOTS: contextvars.ContextVar[frozenset[Path]] = contextvars.ContextVar(
    "plan_queue_held_exclusive_roots",
    default=frozenset(),
)
_ACTIVE_QUEUE_CONTEXT: contextvars.ContextVar[ContractContext | None] = contextvars.ContextVar(
    "plan_queue_active_contract_context",
    default=None,
)
_TRANSACTION_PHASE_HOOK: Callable[[str, QueuePaths, dict[str, Any]], None] | None = None


def iso_now() -> str:
    return datetime.now(tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_status(value: str) -> str:
    return " ".join(value.lower().split())


def normalize_resume_parent(value: str) -> str:
    if plan_status_oracle._is_na_value(value):
        return "none"
    normalized = normalize_status(value)
    if normalized not in VALID_RESUME_PARENT:
        raise QueueError(
            f"Unsupported resume_parent={value!r}; expected one of: "
            + ", ".join(sorted(VALID_RESUME_PARENT))
        )
    return normalized


def repo_root_from(start: Path) -> Path:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    raise QueueError(f"Could not find repo root from {start}")


def queue_paths(
    project_root: Path | None = None,
    *,
    context: ContractContext | None = None,
) -> QueuePaths:
    root = repo_root_from(project_root or Path.cwd())
    try:
        resolved_context = context_for_reader(root, context=context)
    except ContractAuthorityError as exc:
        raise QueueError(f"contract_authority_preflight_failed:{exc.reason_code}") from exc
    return QueuePaths(
        root=root,
        state_path=root / STATE_FILE_NAME,
        log_path=root / LOG_FILE_NAME,
        lock_path=root / LOCK_FILE_NAME,
        txn_path=root / TXN_FILE_NAME,
        context=resolved_context,
    )


def project_relative_path(root: Path, raw_path: str, *, require_exists: bool = True) -> str:
    candidate = Path(raw_path)
    filesystem_path = candidate if candidate.is_absolute() else root / candidate
    filesystem_path = filesystem_path.resolve()
    try:
        relative = filesystem_path.relative_to(root.resolve())
    except ValueError as exc:
        raise QueueError(f"Path is outside repo root: {raw_path}") from exc
    if require_exists and not filesystem_path.is_file():
        raise QueueError(f"Missing plan file: {relative.as_posix()}")
    return relative.as_posix()


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        target_mode = stat.S_IMODE(path.stat().st_mode)
    except FileNotFoundError:
        target_mode = None
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            if target_mode is not None:
                os.fchmod(fh.fileno(), target_mode)
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
        _fsync_directory(path.parent)
    except BaseException:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _state_bytes(paths: QueuePaths) -> bytes | None:
    try:
        return paths.state_path.read_bytes()
    except FileNotFoundError:
        return None


def _history_bytes(paths: QueuePaths) -> bytes | None:
    try:
        return paths.log_path.read_bytes()
    except FileNotFoundError:
        return None


def _state_digest(raw: bytes | None) -> str:
    if raw is None:
        return ABSENT_STATE_DIGEST
    return hashlib.sha256(raw).hexdigest()


def _sanitize_log_value(value: Any) -> str:
    return LOG_LINE_BREAK_RE.sub(" ", str(value)).replace("\t", " ")


def _log_scalar_is_safe(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and "\t" not in value
        and LOG_LINE_BREAK_RE.search(value) is None
    )


def _log_token_is_safe(value: Any) -> bool:
    return isinstance(value, str) and LOG_TOKEN_RE.fullmatch(value) is not None


def _audit_row(event: str, *, at: str | None = None, **fields: Any) -> dict[str, Any]:
    reserved = {"transaction_id", "transaction_seq", "transaction_size"} & set(fields)
    if reserved:
        raise QueueError(f"Reserved transaction audit fields: {', '.join(sorted(reserved))}")
    return {
        "at": at or iso_now(),
        "event": event,
        "fields": {key: value for key, value in fields.items() if value is not None},
    }


def _render_log_row(row: dict[str, Any], *, transaction_id: str, sequence: int, size: int) -> str:
    parts = [str(row["at"]), str(row["event"])]
    fields = {
        "transaction_id": transaction_id,
        "transaction_seq": sequence,
        "transaction_size": size,
    }
    fields.update(dict(row.get("fields") or {}))
    for key, value in fields.items():
        parts.append(f"{key}={_sanitize_log_value(value)}")
    return "\t".join(parts) + "\n"


def _append_transaction_rows(
    paths: QueuePaths,
    rows: list[dict[str, Any]],
    *,
    transaction_id: str,
    start_sequence: int = 1,
) -> None:
    if not rows:
        return
    paths.log_path.parent.mkdir(parents=True, exist_ok=True)
    with paths.log_path.open("a", encoding="utf-8") as fh:
        transaction_size = start_sequence + len(rows) - 1
        for offset, row in enumerate(rows, start=start_sequence):
            fh.write(
                _render_log_row(
                    row,
                    transaction_id=transaction_id,
                    sequence=offset,
                    size=transaction_size,
                )
            )
            fh.flush()
            os.fsync(fh.fileno())
            _run_transaction_phase_hook(f"history:{offset}", paths, {"transaction_id": transaction_id})
    _fsync_directory(paths.log_path.parent)


def append_log(paths: QueuePaths, event: str, **fields: Any) -> None:
    """Fixture/backward-compatible raw append; production mutations use transaction batches."""
    _queue_authority_preflight(paths)
    paths.log_path.parent.mkdir(parents=True, exist_ok=True)
    row = _audit_row(event, **fields)
    parts = [str(row["at"]), str(row["event"])]
    parts.extend(f"{key}={_sanitize_log_value(value)}" for key, value in row["fields"].items())
    with paths.log_path.open("a", encoding="utf-8") as fh:
        fh.write("\t".join(parts) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def _lock_payload(paths: QueuePaths, *, command: str, lock_mode: str, timeout: float) -> dict[str, Any]:
    return {
        "ok": False,
        "error": "lock_timeout",
        "command": command,
        "lock_mode": lock_mode,
        "lock_path": paths.required_lock_path().relative_to(paths.root).as_posix(),
        "timeout_seconds": timeout,
    }


def _engaged_queue_vocab_payload(context: ContractContext) -> dict[str, Any] | None:
    """Read the one vocabulary input that remains a queue authority carrier.

    Queue plan/evidence inputs deliberately remain ordinary project data.  Only
    the vocabulary controls queue admission semantics, so it is declared and
    current-byte checked when an engaged context is used.
    """

    if context.state != "engaged":
        return None
    raw_text = read_declared_text(
        context,
        "docs/_meta/plan_vocab.json",
        purpose="queue plan vocabulary",
    )
    try:
        # Queue activation is driven by the same schema vocabulary that the
        # plan linter admits.  Parsing only JSON here would turn a malformed
        # engaged schema into the old empty-vocabulary behavior.
        payload = plan_lint.load_plan_vocab(
            context.contract_root / "docs" / "_meta" / "plan_vocab.json",
            raw_text=raw_text,
        )
    except (plan_lint.ManifestError, ValueError, TypeError) as exc:
        raise QueueError("contract_authority_invalid_plan_vocab") from exc
    return payload


def _queue_authority_preflight(paths: QueuePaths) -> ContractContext:
    """Validate one captured generation before *any* queue filesystem effect."""

    inherited = paths.context or _ACTIVE_QUEUE_CONTEXT.get()
    try:
        context = context_for_reader(paths.root, context=inherited)
        # Invalid, missing, or undeclared vocabulary must fail before a shared
        # read operation opens its a+b lock file as well as before mutations.
        _engaged_queue_vocab_payload(context)
        validate_before_effect(context)
    except ContractAuthorityError as exc:
        raise QueueError(f"contract_authority_preflight_failed:{exc.reason_code}") from exc
    return context


@contextmanager
def queue_lock(
    paths: QueuePaths,
    lock_mode: str,
    *,
    command: str,
    timeout: float = LOCK_TIMEOUT_SECONDS,
) -> Iterator[None]:
    if lock_mode not in {"shared", "exclusive"}:
        raise ValueError(f"Unsupported lock mode: {lock_mode}")
    context = _queue_authority_preflight(paths)
    context_token = _ACTIVE_QUEUE_CONTEXT.set(context)
    try:
        lock_path = paths.required_lock_path()
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_flag = fcntl.LOCK_SH if lock_mode == "shared" else fcntl.LOCK_EX
        deadline = time.monotonic() + timeout
        with lock_path.open("a+b") as lock_fh:
            while True:
                try:
                    fcntl.flock(lock_fh.fileno(), lock_flag | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        payload = _lock_payload(
                            paths,
                            command=command,
                            lock_mode=lock_mode,
                            timeout=timeout,
                        )
                        raise QueueError(
                            "lock_timeout "
                            f"command={command} lock_mode={lock_mode} "
                            f"lock_path={payload['lock_path']} timeout_seconds={timeout}",
                            payload=payload,
                        )
                    time.sleep(min(0.01, max(0.0, deadline - time.monotonic())))
            try:
                yield
            finally:
                fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)
    finally:
        _ACTIVE_QUEUE_CONTEXT.reset(context_token)


def _run_transaction_phase_hook(phase: str, paths: QueuePaths, marker: dict[str, Any]) -> None:
    if _TRANSACTION_PHASE_HOOK is not None:
        _TRANSACTION_PHASE_HOOK(phase, paths, marker)


def _write_state_bytes(paths: QueuePaths, raw: bytes | None) -> None:
    if raw is None:
        try:
            paths.state_path.unlink()
        except FileNotFoundError:
            pass
        _fsync_directory(paths.state_path.parent)
        return
    _atomic_write_bytes(paths.state_path, raw)


def _commit_transaction(
    paths: QueuePaths,
    *,
    operation: str,
    after_state: dict[str, Any] | None,
    audit_rows: list[dict[str, Any]],
) -> str:
    txn_path = paths.required_txn_path()
    if txn_path.exists():
        raise _recovery_required_error(paths, command=operation)
    before_history_raw = _history_bytes(paths)
    try:
        parse_log_entries(paths)
        if _history_bytes(paths) != before_history_raw:
            raise QueueError(f"Queue history changed while preparing transaction: {paths.log_path}")
    except QueueError as exc:
        recovery = {
            "classification": "diverged",
            "transaction_id": None,
            "operation": operation,
            "observed_state_digest": _state_digest(_state_bytes(paths)),
            "history_rows_expected": 0,
            "history_rows_present": 0,
            "marker": None,
        }
        raise QueueError(
            f"diverged queue history blocks transaction operation={operation}",
            payload=_recovery_payload(paths, command=operation, recovery=recovery),
        ) from exc
    before_raw = _state_bytes(paths)
    after_raw = _json_bytes(after_state) if after_state is not None else None
    transaction_id = uuid.uuid4().hex
    transaction_size = len(audit_rows)
    marker_rows = []
    for sequence, row in enumerate(audit_rows, start=1):
        marker_rows.append(
            {
                "at": row["at"],
                "event": row["event"],
                "fields": dict(row.get("fields") or {}),
                "transaction_seq": sequence,
                "transaction_size": transaction_size,
            }
        )
    marker = {
        "version": TXN_VERSION,
        "transaction_id": transaction_id,
        "operation": operation,
        "created_at": iso_now(),
        "before_state_digest": _state_digest(before_raw),
        "after_state_digest": _state_digest(after_raw),
        "before_history_digest": _state_digest(before_history_raw),
        "before_history_size_bytes": len(before_history_raw or b""),
        "audit_rows": marker_rows,
    }
    _validated_marker(marker)
    _atomic_write_bytes(txn_path, _json_bytes(marker))
    _run_transaction_phase_hook("marker", paths, marker)
    _write_state_bytes(paths, after_raw)
    _run_transaction_phase_hook("state", paths, marker)
    _append_transaction_rows(paths, audit_rows, transaction_id=transaction_id)
    parse_log_entries(paths)
    _run_transaction_phase_hook("history", paths, marker)
    txn_path.unlink()
    _fsync_directory(txn_path.parent)
    _run_transaction_phase_hook("cleanup", paths, marker)
    return transaction_id


def _validate_state_schema(paths: QueuePaths, value: Any) -> dict[str, Any]:
    def invalid(reason: str) -> QueueError:
        return QueueError(f"Queue state schema is invalid: {paths.state_path}: {reason}")

    if not isinstance(value, dict):
        raise invalid("top-level value must be an object")
    if type(value.get("version")) is not int or value["version"] != STATE_VERSION:
        raise invalid(f"version must equal {STATE_VERSION}")
    if not isinstance(value.get("mode"), str) or not value["mode"].strip():
        raise invalid("mode must be a non-empty string")
    if not isinstance(value.get("resume_parent"), str) or value["resume_parent"] not in VALID_RESUME_PARENT:
        raise invalid("resume_parent is missing or unsupported")
    if type(value.get("cursor")) is not int or value["cursor"] < 0:
        raise invalid("cursor must be a non-negative integer")

    items = value.get("items")
    if not isinstance(items, list):
        raise invalid("items must be a list")
    seen_orders: set[int] = set()
    active_count = 0
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise invalid(f"items[{index}] must be an object")
        order = item.get("order")
        if type(order) is not int or order < 1:
            raise invalid(f"items[{index}].order must be a positive integer")
        if order in seen_orders:
            raise invalid(f"items[{index}].order duplicates {order}")
        seen_orders.add(order)
        if not isinstance(item.get("plan"), str) or not item["plan"].strip():
            raise invalid(f"items[{index}].plan must be a non-empty string")
        item_state = item.get("state")
        if not isinstance(item_state, str) or item_state not in VALID_ITEM_STATES:
            raise invalid(f"items[{index}].state is missing or unsupported")
        active_count += item_state == "active"
    if active_count > 1:
        raise invalid("items contain more than one active entry")
    orders = [item["order"] for item in items]
    if orders != list(range(1, len(items) + 1)):
        raise invalid("item orders must be contiguous and match list order")
    plans = [item["plan"] for item in items]
    if len(plans) != len(set(plans)):
        raise invalid("items contain duplicate plan paths")
    if value["cursor"] > len(items):
        raise invalid("cursor exceeds item count")
    active_item = next((item for item in items if item["state"] == "active"), None)
    if active_item is not None and value["cursor"] != active_item["order"] - 1:
        raise invalid("cursor does not point at the active item")
    lifecycle_rank = {
        "done": 0,
        "superseded": 0,
        CLOSED_NON_EXECUTABLE_STATE: 0,
        SKIPPED_MANAGER_MODE_STATE: 0,
        "active": 1,
        "pending": 2,
    }
    lifecycle = [lifecycle_rank[item["state"]] for item in items]
    if lifecycle != sorted(lifecycle):
        raise invalid("item lifecycle must be finalized prefix, optional active, pending suffix")
    if active_item is None:
        first_pending = next((item for item in items if item["state"] == "pending"), None)
        expected_cursor = first_pending["order"] - 1 if first_pending is not None else len(items)
        if value["cursor"] != expected_cursor:
            raise invalid("cursor does not point at the first pending item or queue end")

    for index, item in enumerate(items):
        if item.get("state") != SKIPPED_MANAGER_MODE_STATE:
            continue
        expected = {
            "skip_phase": "activation",
            "manager_mode_state": "mismatch",
            "manager_mode_reason": "required_mode_mismatch",
            "closeout_kind": "manager_mode_mismatch",
        }
        for key, expected_value in expected.items():
            if item.get(key) != expected_value:
                raise invalid(
                    f"items[{index}].{key} must equal {expected_value!r} "
                    f"for {SKIPPED_MANAGER_MODE_STATE}"
                )
        for key in ("required_manager_mode", "actual_manager_mode"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise invalid(
                    f"items[{index}].{key} must be a non-empty string "
                    f"for {SKIPPED_MANAGER_MODE_STATE}"
                )
            if item[key] not in plan_status_oracle.ACTUAL_MANAGER_MODES:
                raise invalid(
                    f"items[{index}].{key} must be a concrete supported Manager mode "
                    f"for {SKIPPED_MANAGER_MODE_STATE}"
                )
        if item["required_manager_mode"] == item["actual_manager_mode"]:
            raise invalid(
                f"items[{index}] Manager modes must differ for {SKIPPED_MANAGER_MODE_STATE}"
            )
        skip_id = item.get("manager_mode_skip_id")
        if not isinstance(skip_id, str) or re.fullmatch(r"[0-9a-f]{32}", skip_id) is None:
            raise invalid(
                f"items[{index}].manager_mode_skip_id must be a 32-character lowercase "
                f"hex lifecycle identity for {SKIPPED_MANAGER_MODE_STATE}"
            )

    for key in ("last_stop", "last_transition", "last_planpath_override"):
        if key in value and value[key] is not None and not isinstance(value[key], dict):
            raise invalid(f"{key} must be an object or null")
    return value


def load_state(paths: QueuePaths, *, repair_legacy: bool = False) -> dict[str, Any] | None:
    if not paths.state_path.exists():
        return None
    try:
        state = json.loads(paths.state_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QueueError(f"Queue state is not valid JSON: {paths.state_path}") from exc
    state = _validate_state_schema(paths, state)
    if repair_legacy and repair_legacy_parent_resumed_transition(state):
        raise QueueError("recovery_required classification=legacy_repair_required")
    return state


def save_state(paths: QueuePaths, state: dict[str, Any]) -> None:
    _queue_authority_preflight(paths)
    _atomic_write_bytes(paths.state_path, _json_bytes(state))


def parse_log_entries(
    paths: QueuePaths,
    *,
    allow_incomplete_transaction_id: str | None = None,
) -> list[dict[str, str]]:
    raw = _history_bytes(paths)
    if raw is None:
        return []
    return _parse_log_bytes(
        raw,
        source=paths.log_path,
        allow_incomplete_transaction_id=allow_incomplete_transaction_id,
    )


def _parse_log_bytes(
    raw: bytes,
    *,
    source: Path,
    allow_incomplete_transaction_id: str | None = None,
) -> list[dict[str, str]]:
    if raw and not raw.endswith(b"\n"):
        raise QueueError(f"Queue history is not newline-terminated: {source}")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise QueueError(f"Queue history is not valid UTF-8: {source}") from exc

    entries: list[dict[str, str]] = []
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    for line_number, raw_line in enumerate(lines, start=1):
        if LOG_LINE_BREAK_RE.search(raw_line):
            raise QueueError(f"Queue history row {line_number} has an invalid line separator: {source}")
        parts = raw_line.split("\t")
        if len(parts) < 2 or not parts[0] or not parts[1]:
            raise QueueError(
                f"Queue history row {line_number} is missing timestamp or event: {source}"
            )
        if not _log_scalar_is_safe(parts[0]) or not _log_token_is_safe(parts[1]):
            raise QueueError(f"Queue history row {line_number} has invalid timestamp or event: {source}")
        entry: dict[str, str] = {"at": parts[0], "event": parts[1]}
        for chunk in parts[2:]:
            if "=" not in chunk:
                raise QueueError(
                    f"Queue history row {line_number} has field without '=': {source}"
                )
            key, value = chunk.split("=", 1)
            if not _log_token_is_safe(key):
                raise QueueError(
                    f"Queue history row {line_number} has invalid field key: {source}"
                )
            if key in entry:
                raise QueueError(
                    f"Queue history row {line_number} has duplicate field {key}: {source}"
                )
            entry[key] = value
        transaction_keys = {"transaction_id", "transaction_seq", "transaction_size"}
        present_transaction_keys = transaction_keys & set(entry)
        if present_transaction_keys and present_transaction_keys != transaction_keys:
            raise QueueError(
                f"Queue history row {line_number} has incomplete transaction fields: {source}"
            )
        if present_transaction_keys:
            if not _log_token_is_safe(entry["transaction_id"]):
                raise QueueError(
                    f"Queue history row {line_number} has invalid transaction id: {source}"
                )
            try:
                sequence = int(entry["transaction_seq"])
                size = int(entry["transaction_size"])
            except ValueError as exc:
                raise QueueError(
                    f"Queue history row {line_number} has non-integer transaction sequence: {source}"
                ) from exc
            if sequence < 1 or size < 1 or sequence > size:
                raise QueueError(
                    f"Queue history row {line_number} has invalid transaction sequence: {source}"
                )
        entries.append(entry)

    transaction_groups: dict[str, list[tuple[int, dict[str, str]]]] = {}
    for index, entry in enumerate(entries):
        transaction_id = entry.get("transaction_id")
        if transaction_id:
            transaction_groups.setdefault(transaction_id, []).append((index, entry))
    for transaction_id, group in transaction_groups.items():
        positions = [index for index, _ in group]
        rows = [entry for _, entry in group]
        sizes = {int(entry["transaction_size"]) for entry in rows}
        sequences = [int(entry["transaction_seq"]) for entry in rows]
        contiguous = positions == list(range(positions[0], positions[0] + len(positions)))
        prefix = sequences == list(range(1, len(rows) + 1))
        one_size = len(sizes) == 1
        size = next(iter(sizes)) if one_size else 0
        complete = one_size and len(rows) == size
        allowed_incomplete = (
            transaction_id == allow_incomplete_transaction_id
            and one_size
            and len(rows) < size
        )
        if not contiguous or not prefix or not one_size or not (complete or allowed_incomplete):
            raise QueueError(
                f"Queue history transaction group {transaction_id} is incomplete or inconsistent: {source}"
            )
    return entries


def _read_marker(paths: QueuePaths) -> dict[str, Any] | None:
    txn_path = paths.required_txn_path()
    if not txn_path.exists():
        return None
    try:
        marker = json.loads(txn_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QueueError(f"diverged invalid transaction marker: {txn_path}") from exc
    if not isinstance(marker, dict):
        raise QueueError(f"diverged transaction marker must be an object: {txn_path}")
    return marker


def _validated_marker(marker: dict[str, Any]) -> dict[str, Any]:
    required = {
        "version",
        "transaction_id",
        "operation",
        "created_at",
        "before_state_digest",
        "after_state_digest",
        "before_history_digest",
        "before_history_size_bytes",
        "audit_rows",
    }
    if set(marker) != required or marker.get("version") != TXN_VERSION:
        raise QueueError("diverged invalid transaction marker schema")
    if not _log_token_is_safe(marker.get("transaction_id")):
        raise QueueError("diverged invalid transaction marker id")
    if not _log_token_is_safe(marker.get("operation")):
        raise QueueError("diverged invalid transaction marker operation")
    if not _log_scalar_is_safe(marker.get("created_at")):
        raise QueueError("diverged invalid transaction marker scalar fields")
    if not all(
        isinstance(marker.get(key), str) and LOG_DIGEST_RE.fullmatch(marker[key])
        for key in ("before_state_digest", "after_state_digest", "before_history_digest")
    ):
        raise QueueError("diverged invalid transaction marker digest fields")
    if type(marker.get("before_history_size_bytes")) is not int or marker["before_history_size_bytes"] < 0:
        raise QueueError("diverged invalid transaction marker history boundary")
    rows = marker.get("audit_rows")
    if not isinstance(rows, list) or not rows:
        raise QueueError("diverged transaction marker audit_rows must be a non-empty list")
    size = len(rows)
    for sequence, row in enumerate(rows, start=1):
        if not isinstance(row, dict) or set(row) != {
            "at",
            "event",
            "fields",
            "transaction_seq",
            "transaction_size",
        }:
            raise QueueError("diverged invalid transaction marker audit row schema")
        if not _log_scalar_is_safe(row.get("at")):
            raise QueueError("diverged invalid transaction marker audit row timestamp")
        if not _log_token_is_safe(row.get("event")):
            raise QueueError("diverged invalid transaction marker audit row event")
        if not isinstance(row.get("fields"), dict):
            raise QueueError("diverged invalid transaction marker audit row fields")
        if not all(_log_token_is_safe(key) for key in row["fields"]):
            raise QueueError("diverged invalid transaction marker audit row field key")
        if {"at", "event"} & set(row["fields"]):
            raise QueueError("diverged transaction marker audit row shadows structural fields")
        if {"transaction_id", "transaction_seq", "transaction_size"} & set(row["fields"]):
            raise QueueError("diverged transaction marker audit row uses reserved fields")
        if row.get("transaction_seq") != sequence or row.get("transaction_size") != size:
            raise QueueError("diverged invalid transaction marker audit sequence")
    return marker


def _expected_history_entry(marker: dict[str, Any], row: dict[str, Any]) -> dict[str, str]:
    expected = {
        "at": str(row["at"]),
        "event": str(row["event"]),
        "transaction_id": str(marker["transaction_id"]),
        "transaction_seq": str(row["transaction_seq"]),
        "transaction_size": str(row["transaction_size"]),
    }
    for key, value in row["fields"].items():
        if value is not None:
            expected[str(key)] = _sanitize_log_value(value)
    return expected


def _classify_recovery(paths: QueuePaths) -> dict[str, Any]:
    try:
        marker = _read_marker(paths)
    except QueueError:
        return {
            "classification": "diverged",
            "transaction_id": None,
            "operation": None,
            "observed_state_digest": _state_digest(_state_bytes(paths)),
            "history_rows_expected": 0,
            "history_rows_present": 0,
            "marker": None,
        }
    try:
        state = load_state(paths)
    except QueueError:
        return {
            "classification": "diverged",
            "transaction_id": marker.get("transaction_id") if isinstance(marker, dict) else None,
            "operation": marker.get("operation") if isinstance(marker, dict) else None,
            "observed_state_digest": _state_digest(_state_bytes(paths)),
            "history_rows_expected": (
                len(marker.get("audit_rows") or [])
                if isinstance(marker, dict) and isinstance(marker.get("audit_rows"), list)
                else 0
            ),
            "history_rows_present": 0,
            "marker": marker,
        }
    try:
        allow_incomplete_transaction_id = (
            marker.get("transaction_id")
            if isinstance(marker, dict) and isinstance(marker.get("transaction_id"), str)
            else None
        )
        log_entries = parse_log_entries(
            paths,
            allow_incomplete_transaction_id=allow_incomplete_transaction_id,
        )
    except QueueError:
        return {
            "classification": "diverged",
            "transaction_id": marker.get("transaction_id") if isinstance(marker, dict) else None,
            "operation": marker.get("operation") if isinstance(marker, dict) else None,
            "observed_state_digest": _state_digest(_state_bytes(paths)),
            "history_rows_expected": (
                len(marker.get("audit_rows") or [])
                if isinstance(marker, dict) and isinstance(marker.get("audit_rows"), list)
                else 0
            ),
            "history_rows_present": 0,
            "marker": marker,
        }
    if marker is None:
        if state is not None and repair_legacy_parent_resumed_transition(dict(state)):
            return {
                "classification": "legacy_repair_required",
                "transaction_id": None,
                "operation": "legacy_repair",
                "observed_state_digest": _state_digest(_state_bytes(paths)),
                "history_rows_expected": 1,
                "history_rows_present": 0,
                "marker": None,
            }
        return {
            "classification": "clean",
            "transaction_id": None,
            "operation": None,
            "observed_state_digest": _state_digest(_state_bytes(paths)),
            "history_rows_expected": 0,
            "history_rows_present": 0,
            "marker": None,
        }

    try:
        marker = _validated_marker(marker)
    except QueueError:
        return {
            "classification": "diverged",
            "transaction_id": marker.get("transaction_id") if isinstance(marker.get("transaction_id"), str) else None,
            "operation": marker.get("operation") if isinstance(marker.get("operation"), str) else None,
            "observed_state_digest": _state_digest(_state_bytes(paths)),
            "history_rows_expected": (
                len(marker.get("audit_rows") or [])
                if isinstance(marker.get("audit_rows"), list)
                else 0
            ),
            "history_rows_present": 0,
            "marker": marker,
        }

    transaction_id = str(marker["transaction_id"])
    expected_entries = [_expected_history_entry(marker, row) for row in marker["audit_rows"]]
    expected_row_bytes = [
        _render_log_row(
            {"at": row["at"], "event": row["event"], "fields": dict(row["fields"])},
            transaction_id=transaction_id,
            sequence=int(row["transaction_seq"]),
            size=int(row["transaction_size"]),
        ).encode("utf-8")
        for row in marker["audit_rows"]
    ]
    history_bytes = _history_bytes(paths) or b""
    before_history_size = int(marker["before_history_size_bytes"])
    history_boundary_valid = len(history_bytes) >= before_history_size
    history_prefix = history_bytes[:before_history_size]
    expected_history_digest = str(marker["before_history_digest"])
    if expected_history_digest == ABSENT_STATE_DIGEST:
        history_boundary_valid = history_boundary_valid and before_history_size == 0
    else:
        history_boundary_valid = (
            history_boundary_valid
            and _state_digest(history_prefix) == expected_history_digest
        )
    if history_boundary_valid:
        try:
            prefix_entries = _parse_log_bytes(history_prefix, source=paths.log_path)
        except QueueError:
            history_boundary_valid = False
        else:
            if any(entry.get("transaction_id") == transaction_id for entry in prefix_entries):
                history_boundary_valid = False
    history_suffix = history_bytes[before_history_size:] if history_boundary_valid else b""
    present_count: int | None = None
    if history_boundary_valid:
        for count in range(len(expected_row_bytes) + 1):
            if history_suffix == b"".join(expected_row_bytes[:count]):
                present_count = count
                break
    prefix_valid = present_count is not None
    transaction_entries = expected_entries[: present_count or 0]
    observed_digest = _state_digest(_state_bytes(paths))
    before_digest = str(marker["before_state_digest"])
    after_digest = str(marker["after_state_digest"])

    if not prefix_valid:
        classification = "diverged"
    elif before_digest == after_digest and observed_digest == after_digest:
        classification = (
            "already_complete"
            if len(transaction_entries) == len(expected_entries)
            else "state_applied_history_missing"
        )
    elif observed_digest == before_digest:
        classification = "not_applied" if not transaction_entries else "diverged"
    elif observed_digest == after_digest:
        classification = (
            "already_complete"
            if len(transaction_entries) == len(expected_entries)
            else "state_applied_history_missing"
        )
    else:
        classification = "diverged"

    return {
        "classification": classification,
        "transaction_id": transaction_id,
        "operation": str(marker["operation"]),
        "observed_state_digest": observed_digest,
        "history_rows_expected": len(expected_entries),
        "history_rows_present": len(transaction_entries),
        "marker": marker,
    }


def _recovery_payload(paths: QueuePaths, *, command: str, recovery: dict[str, Any]) -> dict[str, Any]:
    classification = str(recovery["classification"])
    return {
        "ok": False,
        "error": "diverged" if classification == "diverged" else "recovery_required",
        "command": command,
        # The facade command that runs ``recover``; it cannot repair a diverged history.
        "recovery_command": None if classification == "diverged" else RECOVERY_COMMAND,
        "classification": classification,
        "transaction_id": recovery.get("transaction_id"),
        "operation": recovery.get("operation"),
        "marker_path": paths.required_txn_path().relative_to(paths.root).as_posix(),
        "observed_state_digest": recovery.get("observed_state_digest"),
        "history_rows_expected": recovery.get("history_rows_expected", 0),
        "history_rows_present": recovery.get("history_rows_present", 0),
        "mutation_performed": False,
    }


def _recovery_required_error(paths: QueuePaths, *, command: str) -> QueueError:
    recovery = _classify_recovery(paths)
    payload = _recovery_payload(paths, command=command, recovery=recovery)
    return QueueError(
        f"{payload['error']} classification={payload['classification']} "
        f"marker_path={payload['marker_path']}",
        payload=payload,
    )


def _remove_marker(paths: QueuePaths) -> None:
    try:
        paths.required_txn_path().unlink()
    except FileNotFoundError:
        return
    _fsync_directory(paths.required_txn_path().parent)


def _repair_legacy_under_lock(paths: QueuePaths) -> bool:
    state = load_state(paths)
    if state is None:
        return False
    repaired_state = json.loads(json.dumps(state))
    if not repair_legacy_parent_resumed_transition(repaired_state):
        return False
    _commit_transaction(
        paths,
        operation="legacy_repair",
        after_state=repaired_state,
        audit_rows=[
            _audit_row(
                "state_repair",
                reason="legacy_parent_resumed_transition",
            )
        ],
    )
    return True


def _exclusive_operation(command: str) -> Callable[[Callable[..., dict[str, Any]]], Callable[..., dict[str, Any]]]:
    def decorate(function: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
        @functools.wraps(function)
        def wrapped(paths: QueuePaths, *args: Any, **kwargs: Any) -> dict[str, Any]:
            timeout = float(kwargs.pop("_lock_timeout", LOCK_TIMEOUT_SECONDS))
            root = paths.root.resolve()
            held_roots = _HELD_EXCLUSIVE_ROOTS.get()
            if root in held_roots:
                return function(paths, *args, **kwargs)
            with queue_lock(paths, "exclusive", command=command, timeout=timeout):
                token = _HELD_EXCLUSIVE_ROOTS.set(held_roots | {root})
                try:
                    if paths.required_txn_path().exists():
                        raise _recovery_required_error(paths, command=command)
                    recovery = _classify_recovery(paths)
                    if recovery["classification"] == "legacy_repair_required":
                        _repair_legacy_under_lock(paths)
                    elif recovery["classification"] != "clean":
                        raise QueueError(
                            f"recovery_required classification={recovery['classification']}",
                            payload=_recovery_payload(paths, command=command, recovery=recovery),
                        )
                    return function(paths, *args, **kwargs)
                finally:
                    _HELD_EXCLUSIVE_ROOTS.reset(token)

        return wrapped

    return decorate


def _shared_operation(command: str) -> Callable[[Callable[..., dict[str, Any]]], Callable[..., dict[str, Any]]]:
    def decorate(function: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
        @functools.wraps(function)
        def wrapped(paths: QueuePaths, *args: Any, **kwargs: Any) -> dict[str, Any]:
            timeout = float(kwargs.pop("_lock_timeout", LOCK_TIMEOUT_SECONDS))
            with queue_lock(paths, "shared", command=command, timeout=timeout):
                recovery = _classify_recovery(paths)
                if recovery["classification"] != "clean":
                    raise QueueError(
                        f"recovery_required classification={recovery['classification']}",
                        payload=_recovery_payload(paths, command=command, recovery=recovery),
                    )
                return function(paths, *args, **kwargs)

        return wrapped

    return decorate


def recover_queue(paths: QueuePaths, *, _lock_timeout: float | None = None) -> dict[str, Any]:
    timeout = LOCK_TIMEOUT_SECONDS if _lock_timeout is None else float(_lock_timeout)
    with queue_lock(paths, "exclusive", command="recover", timeout=timeout):
        recovery = _classify_recovery(paths)
        classification = str(recovery["classification"])
        mutation_performed = False
        if classification == "clean":
            result = "clean"
        elif classification == "diverged":
            result = "blocked"
        elif classification == "legacy_repair_required":
            mutation_performed = _repair_legacy_under_lock(paths)
            result = "recovered"
        elif classification == "not_applied":
            _remove_marker(paths)
            mutation_performed = True
            result = "recovered"
        elif classification in {"state_applied_history_missing", "already_complete"}:
            marker = recovery["marker"]
            assert isinstance(marker, dict)
            present = int(recovery["history_rows_present"])
            missing_rows = [
                {
                    "at": row["at"],
                    "event": row["event"],
                    "fields": dict(row["fields"]),
                }
                for row in marker["audit_rows"][present:]
            ]
            if missing_rows:
                _append_transaction_rows(
                    paths,
                    missing_rows,
                    transaction_id=str(marker["transaction_id"]),
                    start_sequence=present + 1,
                )
            parse_log_entries(paths)
            _remove_marker(paths)
            mutation_performed = True
            result = "recovered"
        else:
            raise AssertionError(f"Unhandled recovery classification: {classification}")
        return {
            "ok": classification != "diverged",
            "command": "recover",
            "classification": classification,
            "result": result,
            "transaction_id": recovery.get("transaction_id"),
            "operation": recovery.get("operation"),
            "marker_path": paths.required_txn_path().relative_to(paths.root).as_posix(),
            "observed_state_digest": recovery.get("observed_state_digest"),
            "history_rows_expected": recovery.get("history_rows_expected", 0),
            "history_rows_present": recovery.get("history_rows_present", 0),
            "mutation_performed": mutation_performed,
        }


def _scan_status_line_lenient(plan_text: str) -> str:
    non_quote: list[str] = []
    quote: list[str] = []
    for line in plan_text.splitlines():
        trimmed = line.lstrip()
        if trimmed.startswith("##"):
            break
        is_quote = False
        check = trimmed
        if check.startswith(">"):
            is_quote = True
            check = check[1:].lstrip()
        if check.startswith(("-", "*", "+")) and len(check) > 1 and check[1].isspace():
            check = check[1:].lstrip()
        if not check.startswith("**Status:**") or "|" in check:
            continue
        bucket = quote if is_quote else non_quote
        bucket.append(check)
    matches = non_quote or quote
    if not matches:
        raise QueueError("Plan hygiene: no header **Status:** line found")
    return matches[0]


def extract_status_value(plan_path: Path) -> str:
    text = plan_path.read_text(encoding="utf-8")
    line = _scan_status_line_lenient(text)
    value = line[len("**Status:**") :].strip()
    if not value:
        raise QueueError(f"Plan hygiene: empty **Status:** in {plan_path}")
    return value


_BLOCKING_DEPENDENCY_MALFORMED_REASON_CODES = frozenset(
    {"malformed_json", "duplicate_json_key", "nonfinite_json_value"}
)


def _blocking_dependency_meta_failure(strict: plan_status_oracle.StrictPlanMetaJsonResult) -> str:
    if strict.reason_code == "unterminated_meta_json":
        return "unterminated plan_meta JSON fence"
    if strict.reason_code == "plan_meta_not_object":
        return "missing object-shaped plan_meta"
    if strict.reason_code in _BLOCKING_DEPENDENCY_MALFORMED_REASON_CODES:
        return f"malformed plan_meta JSON ({strict.reason})"
    return f"plan_meta strict read failed ({strict.reason_code})"


def parse_blocking_dependency_meta(plan_text: str) -> tuple[dict[str, Any], str | None]:
    """Return the carrier-bearing meta block or a deterministic parse failure.

    Ordinary plans do not opt in, so their legacy ``depends_on`` rows remain
    untouched.  Once the explicit hard-carrier key appears in the plan, a
    malformed or duplicate-key Meta carrier must not silently downgrade to
    soft lineage.  The fence parse is delegated to the shared duplicate-safe
    strict reader; this wrapper keeps only the carrier-scoped failure reasons.
    """

    strict = plan_status_oracle.strict_plan_meta_json(plan_text)
    if strict.state == "valid" and isinstance(strict.plan_meta, dict):
        return dict(strict.plan_meta), None
    if plan_lint.BLOCKING_DEPENDENCY_CARRIER_FIELD in plan_text:
        return {}, _blocking_dependency_meta_failure(strict)
    return plan_status_oracle.parse_plan_meta(plan_text), None


def planning_contour_queue_activation_states(
    root: Path,
    *,
    context: ContractContext | None = None,
) -> frozenset[str]:
    manifest_path = root / "docs/_meta/plan_vocab.json"
    resolved_context = context_for_reader(root, context=context or _ACTIVE_QUEUE_CONTEXT.get())
    if resolved_context.state == "engaged":
        try:
            payload = _engaged_queue_vocab_payload(resolved_context)
        except ContractAuthorityError as exc:
            raise QueueError(f"contract_authority_preflight_failed:{exc.reason_code}") from exc
        assert payload is not None
    else:
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            # The historical empty-vocabulary behavior stays available only in
            # legacy mode.  Engaged mode has already failed above.
            return frozenset()
    planning_contour = payload.get("planning_contour") if isinstance(payload, dict) else None
    states = planning_contour.get("queue_activation_states") if isinstance(planning_contour, dict) else None
    if not isinstance(states, list):
        return frozenset()
    return frozenset(str(state).strip() for state in states if isinstance(state, str) and state.strip())


def clean_queue_activation_state(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if cleaned.startswith("`") and cleaned.endswith("`") and len(cleaned) >= 2:
        cleaned = cleaned[1:-1].strip()
    return cleaned or None


def queue_activation_import_warning(
    root: Path,
    rel_plan: str,
    *,
    context: ContractContext | None = None,
) -> str | None:
    plan_path = root / rel_plan
    try:
        text = plan_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    try:
        status_value = normalize_status(_scan_status_line_lenient(text)[len("**Status:**") :].strip())
    except QueueError:
        return None
    strict = plan_status_oracle.strict_plan_meta_json(text)
    if strict.state != "valid" or not isinstance(strict.plan_meta, dict):
        return f"plan_meta_strict_read_failed; reason_code={strict.reason_code}"
    meta = strict.plan_meta
    activation_required = status_value == "architect initial draft"
    activation_present = isinstance(meta, dict) and "queue_activation" in meta
    if not activation_required and not activation_present:
        return None

    if not isinstance(meta, dict) or "queue_activation" not in meta:
        shape = "absent"
        state = None
    else:
        queue_activation = meta.get("queue_activation")
        if queue_activation is None:
            shape = "null"
            state = None
        elif not isinstance(queue_activation, dict):
            shape = "non_object"
            state = None
        else:
            state = clean_queue_activation_state(queue_activation.get("state"))
            shape = "missing_required" if state is None else "object"

    allowed_states = planning_contour_queue_activation_states(
        root,
        context=context or _ACTIVE_QUEUE_CONTEXT.get(),
    )
    approved_states = allowed_states.intersection(QUEUE_ACTIVATION_APPROVED_STATES)
    allowed_queue_states = approved_states if activation_required else approved_states.union({"n/a"})
    if state is not None and state in allowed_queue_states:
        if state in approved_states:
            next_plans = meta.get("next_plans") if isinstance(meta, dict) else None
            next_plan_paths = [str(item).strip() for item in next_plans] if isinstance(next_plans, list) else []
            execution_queue_paths, _ = parse_execution_queue(text)
            if execution_queue_paths and not any(next_plan_paths):
                return (
                    "missing queue activation next_plans carrier; "
                    "state=approved and ## Execution queue has child plan(s), "
                    "but plan_meta.next_plans[] is empty"
                )
        return None
    state_detail = f"state={state}" if state is not None else f"shape={shape}"
    manifest_detail = "manifest_missing_or_malformed" if not allowed_states else "planning_contour.queue_activation_states"
    expected_states = "owner_approved|architect_approved" if activation_required else "owner_approved|architect_approved|n/a"
    return (
        f"missing_or_invalid queue_activation.state for {status_value}; "
        f"{state_detail}; expected {expected_states} from "
        f"docs/_meta/plan_vocab.json -> {manifest_detail}"
    )


def queue_activation_admission_blocker(
    root: Path,
    rel_plan: str,
    *,
    context: ContractContext | None = None,
) -> str | None:
    plan_path = root / rel_plan
    try:
        text = plan_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        # Unreadable candidates keep the legacy reroute: the fresh full-lint
        # gate owns fail-closed candidate read failures, not this lane.
        return None
    strict = plan_status_oracle.strict_plan_meta_json(text)
    if strict.state != "valid" or not isinstance(strict.plan_meta, dict):
        return (
            f"queue_activation_admission_blocked: {rel_plan}: "
            f"plan_meta_strict_read_failed; reason_code={strict.reason_code}"
        )
    meta = strict.plan_meta
    queue_activation = meta.get("queue_activation") if isinstance(meta, dict) else None
    if isinstance(queue_activation, dict):
        activation_state = clean_queue_activation_state(queue_activation.get("state"))
        if activation_state == "n/a":
            missing_fields = [
                field
                for field in ("source_ref", "reason")
                if not isinstance(queue_activation.get(field), str) or not queue_activation[field].strip()
            ]
            if missing_fields:
                return (
                    f"queue_activation_admission_blocked: {rel_plan}: "
                    "missing_or_invalid queue_activation carrier; state=n/a; "
                    f"missing_required={'|'.join(missing_fields)}"
                )
            return (
                f"queue_activation_admission_blocked: {rel_plan}: "
                "queue_collection_ineligible; state=n/a"
            )
    warning = queue_activation_import_warning(
        root,
        rel_plan,
        context=context or _ACTIVE_QUEUE_CONTEXT.get(),
    )
    if not warning:
        return None
    return f"queue_activation_admission_blocked: {rel_plan}: {warning}"


def enforce_queue_activation_admission(
    root: Path,
    rel_plan: str,
    *,
    context: ContractContext | None = None,
) -> None:
    blocker = queue_activation_admission_blocker(
        root,
        rel_plan,
        context=context or _ACTIVE_QUEUE_CONTEXT.get(),
    )
    if blocker:
        raise QueueError(blocker)


def same_queue_dependency_blocker(root: Path, state: dict[str, Any], pending_item: dict[str, Any]) -> str | None:
    queued_by_plan = {str(item.get("plan")): item for item in state.get("items", []) if item.get("plan")}
    plan = str(pending_item.get("plan") or "")
    if not plan:
        return None
    try:
        text = (root / plan).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    strict = plan_status_oracle.strict_plan_meta_json(text)
    if strict.state != "valid" or not isinstance(strict.plan_meta, dict):
        return f"plan_meta_strict_read_failed: {plan}: reason_code={strict.reason_code}"
    meta = strict.plan_meta
    depends_on = meta.get("depends_on") if isinstance(meta, dict) else None
    if not isinstance(depends_on, list):
        return None
    for raw_dependency in depends_on:
        dependency = str(raw_dependency).strip()
        if not dependency:
            continue
        queued_dependency = queued_by_plan.get(dependency)
        if queued_dependency and queued_dependency.get("state") == SKIPPED_MANAGER_MODE_STATE:
            return (
                f"depends_on_skipped_incompatible: {plan} depends_on {dependency} "
                f"state={SKIPPED_MANAGER_MODE_STATE}"
            )
        if queued_dependency and queued_dependency.get("state") not in FINALIZED_STATES:
            return (
                f"queue_dependency_blocked: {plan} depends_on {dependency} "
                f"state={queued_dependency.get('state') or 'unknown'}"
            )
    return None


def blocking_dependency_blocker(root: Path, pending_item: dict[str, Any]) -> str | None:
    """Fail closed for the opt-in external hard-dependency carrier only."""

    plan = str(pending_item.get("plan") or "")
    if not plan:
        return None
    try:
        text = (root / plan).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        # An unreadable candidate cannot prove that the opt-in carrier exists.
        # The fresh full-lint gate owns this fail-closed candidate read failure.
        return None

    meta, meta_error = parse_blocking_dependency_meta(text)
    if meta_error:
        return f"blocking_depends_on_invalid: {plan}: {meta_error}"
    entries, errors = plan_lint.parse_blocking_dependency_carrier(meta)
    if entries is None:
        return None
    if errors:
        return f"blocking_depends_on_invalid: {plan}: {' | '.join(errors)}"

    for dependency in entries:
        try:
            oracle = plan_status_oracle.oracle_result(
                root / dependency,
                context=_ACTIVE_QUEUE_CONTEXT.get(),
            )
        except Exception as exc:
            return (
                f"blocking_depends_on_oracle_error: {plan} blocking_depends_on {dependency} "
                f"({type(exc).__name__}: {exc})"
            )
        if oracle.delivery_green is not True:
            return (
                f"blocking_depends_on_delivery_blocked: {plan} blocking_depends_on {dependency} "
                "delivery_green=false"
            )
    return None


def _sanitize_plan_lint_blocker_text(value: object) -> str:
    """Render lint details without controls or host-local absolute paths."""

    text = PLAN_LINT_BLOCKER_CONTROL_RE.sub(" ", str(value))
    text = PLAN_LINT_BLOCKER_ABSOLUTE_PATH_RE.sub("<path>", text)
    text = PLAN_LINT_BLOCKER_WINDOWS_PATH_RE.sub("<path>", text)
    return " ".join(text.split()) or "invalid"


def _safe_plan_lint_blocker_path(root: Path, value: object) -> str:
    """Return a root-relative finding path or a non-sensitive fallback."""

    try:
        if not isinstance(value, (str, os.PathLike)):
            return "candidate"
        raw_path = Path(value)
        resolved = raw_path.resolve() if raw_path.is_absolute() else (root / raw_path).resolve()
        rendered = resolved.relative_to(root.resolve()).as_posix()
    except (OSError, RuntimeError, TypeError, ValueError):
        return "candidate"
    return _sanitize_plan_lint_blocker_text(rendered)


def _plan_lint_activation_blocker(
    root: Path,
    pending_item: dict[str, Any],
    *,
    context: ContractContext | None = None,
) -> str | None:
    """Run the authoritative lint at the last pending-to-active admission edge."""

    candidate_plan = str(pending_item.get("plan") or "").strip()
    if not candidate_plan:
        return f"{PLAN_LINT_ACTIVATION_BLOCKER_PREFIX} candidate_plan_missing"

    resolved_context = context or _ACTIVE_QUEUE_CONTEXT.get()
    configured_root = os.environ.get("PLANVEYOR_PROJECT_ROOT")
    if configured_root and (resolved_context is None or resolved_context.state != "engaged"):
        try:
            root_matches = Path(configured_root).resolve() == root.resolve()
        except (OSError, RuntimeError, ValueError):
            root_matches = False
        if not root_matches:
            return f"{PLAN_LINT_ACTIVATION_BLOCKER_PREFIX} project_root_mismatch"

    if resolved_context is None or resolved_context.state != "engaged":
        try:
            # Legacy queue activation still requires a valid vocabulary from
            # the candidate's project root.  Parse it without applying its
            # mutable values: ``lint_plan`` enters the target-local scoped
            # context below and restores the caller's compatibility globals.
            plan_lint.load_plan_vocab(root / "docs" / "_meta" / "plan_vocab.json")
        except Exception:
            return f"{PLAN_LINT_ACTIVATION_BLOCKER_PREFIX} vocab_reload_failed"

    try:
        # ``lint_plan`` scopes and restores its compatibility globals.  Passing
        # the queue context prevents a nested fresh capture and keeps an
        # engaged target bound to the vocabulary already preflighted here.
        findings = plan_lint.lint_plan(root / candidate_plan, context=resolved_context)
    except Exception:
        return f"{PLAN_LINT_ACTIVATION_BLOCKER_PREFIX} lint_failed"

    try:
        errors = [finding for finding in findings if finding.severity == "ERROR"]
    except Exception:
        return f"{PLAN_LINT_ACTIVATION_BLOCKER_PREFIX} lint_result_invalid"
    if not errors:
        return None

    normalized_errors: list[tuple[str, int, str]] = []
    for finding in errors:
        try:
            line = int(finding.line)
        except (TypeError, ValueError):
            line = 0
        normalized_errors.append(
            (
                _safe_plan_lint_blocker_path(root, finding.file),
                line,
                _sanitize_plan_lint_blocker_text(finding.message),
            )
        )
    normalized_errors.sort()
    rendered = [f"{path}:{line}: {message}" for path, line, message in normalized_errors[:10]]
    detail = " | ".join(rendered)
    if len(normalized_errors) > len(rendered):
        detail = f"{detail} | omitted={len(normalized_errors) - len(rendered)}"
    return f"{PLAN_LINT_ACTIVATION_BLOCKER_PREFIX} errors={len(normalized_errors)}; {detail}"


def parse_execution_queue(plan_text: str) -> tuple[list[str], str | None]:
    in_section = False
    plans: list[str] = []
    resume_parent: str | None = None
    for line in plan_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            title = normalize_status(stripped.lstrip("#").strip())
            if in_section:
                break
            if title == "execution queue":
                in_section = True
            continue
        if not in_section or not stripped:
            continue
        resume_match = re.match(r"^-\s*Resume parent:\s*`?([^`]+?)`?\s*$", stripped, re.IGNORECASE)
        if resume_match:
            resume_parent = normalize_resume_parent(resume_match.group(1))
            continue
        plan_match = re.match(r"^-\s*Plan:\s*`?([^`]+?)`?\s*$", stripped, re.IGNORECASE)
        if plan_match:
            plan = plan_match.group(1).strip()
            if not plan_status_oracle._is_na_value(plan):
                plans.append(plan)
    return plans, resume_parent


def _slice_h2_section_lines(plan_text: str, heading_re: re.Pattern[str]) -> list[str]:
    in_section = False
    collected: list[str] = []
    for line in plan_text.splitlines():
        if not in_section and heading_re.match(line):
            in_section = True
            continue
        if in_section and re.match(r"^\s*##\s+", line):
            break
        if in_section:
            collected.append(line)
    return collected


def _clean_inline_value(raw_value: str) -> str:
    cleaned = raw_value.strip()
    if cleaned.startswith("`") and cleaned.endswith("`") and len(cleaned) >= 2:
        cleaned = cleaned[1:-1].strip()
    return cleaned


def _parse_section_field(section_lines: list[str], label: str) -> str | None:
    pattern = re.compile(rf"^\s*-\s*`?{re.escape(label)}`?\s*:\s*(.+?)\s*$", re.IGNORECASE)
    for line in section_lines:
        match = pattern.match(line)
        if match:
            return _clean_inline_value(match.group(1))
    return None


def _section_is_na(section_lines: list[str]) -> bool:
    meaningful_lines: list[str] = []
    for line in section_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("("):
            continue
        if re.match(r"^#{3,}\s+", stripped):
            continue
        meaningful_lines.append(line)

    if len(meaningful_lines) == 1:
        body = _clean_inline_value(meaningful_lines[0].strip())
        if plan_status_oracle._is_na_value(body):
            return True

    meaningful_seen = False
    for line in meaningful_lines:
        stripped = line.strip()
        if not stripped.startswith("-"):
            body = _clean_inline_value(stripped)
            if not plan_status_oracle._is_na_value(body):
                return False
            meaningful_seen = True
            continue
        field_match = re.match(r"^\s*-\s*`?[^:]+`?\s*:\s*(.+?)\s*$", line)
        body = _clean_inline_value(field_match.group(1) if field_match else stripped[1:].strip())
        if not plan_status_oracle._is_na_value(body):
            return False
        meaningful_seen = True
    return meaningful_seen


def parse_small_slice_carrier(plan_text: str) -> SmallSliceCarrier:
    section_lines = _slice_h2_section_lines(plan_text, SMALL_SLICE_SECTION_HEADING_RE)
    return SmallSliceCarrier(
        requested_profile=_parse_section_field(section_lines, "Requested profile"),
        expected_bundle_family=_parse_section_field(section_lines, "Expected bundle family"),
        helper_validation=_parse_section_field(section_lines, "Helper validation"),
        drift_behavior=_parse_section_field(section_lines, "Drift behavior"),
    )


def _is_test_path(path_str: str) -> bool:
    path = PurePosixPath(path_str)
    name = path.name.lower()
    parts = [part.lower() for part in path.parts]
    return (
        "tests" in parts
        or name.startswith("test_")
        or name.endswith("_test.py")
    )


def classify_bundle_family(target_paths: list[str] | None) -> str | None:
    if not target_paths:
        return None

    families: set[str] = set()
    for target_path in target_paths:
        if target_path.startswith("docs/"):
            families.add("doc")
        elif _is_test_path(target_path):
            families.add("test")
        else:
            families.add("other")

    if families == {"doc"}:
        return "docs-only"
    if families == {"test"}:
        return "tests-only"
    if families <= {"doc", "test"}:
        return "docs+tests-mixed"
    return "mixed-non-small"


def small_slice_payload(
    root: Path,
    plan: str,
    *,
    context: ContractContext | None = None,
) -> dict[str, Any]:
    resolved_root = root.resolve()
    try:
        resolved_context = context_for_reader(
            resolved_root,
            context=context or _ACTIVE_QUEUE_CONTEXT.get(),
        )
        _engaged_queue_vocab_payload(resolved_context)
    except ContractAuthorityError as exc:
        raise QueueError(f"contract_authority_preflight_failed:{exc.reason_code}") from exc
    rel_plan = project_relative_path(resolved_root, plan)
    plan_path = resolved_root / rel_plan
    plan_text = plan_path.read_text(encoding="utf-8")
    plan_lines = plan_text.splitlines()
    carrier = parse_small_slice_carrier(plan_text)
    rollout_lines = _slice_h2_section_lines(plan_text, ROLLOUT_PACKET_SECTION_HEADING_RE)
    visual_lines = _slice_h2_section_lines(plan_text, VISUAL_ACCEPTANCE_SECTION_HEADING_RE)
    code_draft_refs = plan_lint.extract_code_draft_refs(plan_lines)
    code_draft_path = plan_lint.select_primary_code_draft_path(plan_path, code_draft_refs, plan_repo_root=resolved_root)
    target_paths = plan_lint.extract_code_draft_target_paths(code_draft_path) if code_draft_path else None
    actual_bundle_family = classify_bundle_family(target_paths)
    live_review_refs = plan_lint.extract_live_review_artifact_refs(plan_lines)
    live_review_artifact = live_review_refs[0][1] if len(live_review_refs) == 1 else None
    review_route_kind = None
    if live_review_artifact:
        if live_review_artifact.startswith("docs/doc_reviews/"):
            review_route_kind = "docs-review"
        elif live_review_artifact.startswith("docs/code_reviews/"):
            review_route_kind = "code-review"
        else:
            review_route_kind = "unknown"

    fail_closed_reasons: list[str] = []
    if carrier.requested_profile != REDUCED_CENSOR_PROFILE:
        fail_closed_reasons.append("requested_profile_not_reduced")
    if carrier.expected_bundle_family not in ALLOWED_SMALL_SLICE_BUNDLE_FAMILIES:
        fail_closed_reasons.append("expected_bundle_family_missing_or_unsupported")
    if carrier.helper_validation != EXACT_BUNDLE_MATCH:
        fail_closed_reasons.append("helper_validation_not_exact_bundle_match")
    if carrier.drift_behavior != FAIL_CLOSED_TO_FULL_CONVEYOR:
        fail_closed_reasons.append("drift_behavior_not_fail_closed")
    if target_paths is None:
        fail_closed_reasons.append("missing_code_draft_targets")
    if actual_bundle_family not in ALLOWED_SMALL_SLICE_BUNDLE_FAMILIES:
        fail_closed_reasons.append("actual_bundle_family_not_small_slice")
    elif carrier.expected_bundle_family and actual_bundle_family != carrier.expected_bundle_family:
        fail_closed_reasons.append("bundle_family_mismatch")
    if carrier.requested_profile == REDUCED_CENSOR_PROFILE and not rollout_lines:
        fail_closed_reasons.append("rollout_packet_section_missing")
    elif rollout_lines and not _section_is_na(rollout_lines):
        fail_closed_reasons.append("cross_repo_rollout_packet_present")
    if carrier.requested_profile == REDUCED_CENSOR_PROFILE and not visual_lines:
        fail_closed_reasons.append("visual_acceptance_section_missing")
    elif visual_lines and not _section_is_na(visual_lines):
        fail_closed_reasons.append("visual_acceptance_not_na")
    if len(live_review_refs) != 1:
        fail_closed_reasons.append("review_route_missing_or_ambiguous")
    elif actual_bundle_family == "docs-only" and (
        live_review_artifact is None or not live_review_artifact.startswith("docs/doc_reviews/")
    ):
        fail_closed_reasons.append("review_route_mismatch")
    elif actual_bundle_family == "tests-only" and (
        live_review_artifact is None or not live_review_artifact.startswith("docs/code_reviews/")
    ):
        fail_closed_reasons.append("review_route_mismatch")

    reduced_conveyor_eligible = not fail_closed_reasons
    return {
        "plan": rel_plan,
        "requested_profile": carrier.requested_profile,
        "expected_bundle_family": carrier.expected_bundle_family,
        "helper_validation": carrier.helper_validation,
        "drift_behavior": carrier.drift_behavior,
        "code_draft_path": code_draft_path.relative_to(resolved_root).as_posix() if code_draft_path else None,
        "target_paths": target_paths or [],
        "actual_bundle_family": actual_bundle_family,
        "live_review_artifact": live_review_artifact,
        "review_route_kind": review_route_kind,
        "rollout_packet_is_na": bool(rollout_lines) and _section_is_na(rollout_lines),
        "visual_acceptance_is_na": bool(visual_lines) and _section_is_na(visual_lines),
        "reduced_conveyor_eligible": reduced_conveyor_eligible,
        "skip_same_session_censors": reduced_conveyor_eligible,
        "same_session_censors": list(SMALL_SLICE_CENSOR_ROLES) if reduced_conveyor_eligible else [],
        "fail_closed_reasons": fail_closed_reasons,
    }


def render_small_slice(payload: dict[str, Any]) -> str:
    requested = payload.get("requested_profile") or "n/a"
    expected = payload.get("expected_bundle_family") or "n/a"
    actual = payload.get("actual_bundle_family") or "unknown"
    eligible = "yes" if payload.get("reduced_conveyor_eligible") else "no"
    review_artifact = payload.get("live_review_artifact") or "none"
    code_draft = payload.get("code_draft_path") or "none"
    reasons = payload.get("fail_closed_reasons") or []
    reason_text = ", ".join(str(reason) for reason in reasons) if reasons else "none"
    return "\n".join(
        [
            "small-slice:",
            f" plan={payload['plan']}",
            f" requested_profile={requested}",
            f" expected_bundle_family={expected}",
            f" actual_bundle_family={actual}",
            f" eligible={eligible}",
            f" code_draft={code_draft}",
            f" review_artifact={review_artifact}",
            f" fail_closed_reasons={reason_text}",
        ]
    )


def iter_plan_files(root: Path) -> list[Path]:
    plans_dir = root / "docs" / "plans"
    if not plans_dir.exists():
        return []
    files = []
    for path in plans_dir.rglob("*.md"):
        rel = path.relative_to(root).as_posix()
        if rel in {"docs/plans/README.md", "docs/plans/_template.md"}:
            continue
        files.append(path)
    return sorted(files, key=lambda item: item.relative_to(root).as_posix().lower())


def plan_runtime_payload(
    root: Path,
    plan: str | None,
    *,
    context: ContractContext | None = None,
) -> dict[str, Any] | None:
    if not plan:
        return None
    plan_path = root / plan
    if not plan_path.is_file():
        return {
            "plan": plan,
            "status_value": None,
            "status_norm": None,
            "terminal_disposition": None,
            "terminal_disposition_reason": "plan file is missing; terminal disposition is unavailable",
            "runtime_class": "missing_plan",
            "runtime_class_reason": "plan file is missing; queue runtime class cannot be derived",
            "queue_closeout_ready": False,
            "queue_closeout_kind": "missing_plan",
            "queue_closeout_reason": "plan file is missing; keep conservative stop behavior",
            "decomposition_child_state": "unknown",
            "decomposition_child_reason": "plan file is missing",
            "decomposition_child_paths": [],
            "small_model_ready_child": "unknown",
            "small_model_readiness_state": "not_applicable",
            "small_model_readiness_findings": [],
        }
    oracle = plan_status_oracle.oracle_result(
        plan_path,
        context=context or _ACTIVE_QUEUE_CONTEXT.get(),
    )
    return {
        "plan": plan,
        "status_value": oracle.status_value,
        "status_norm": oracle.status_norm,
        "terminal_disposition": oracle.terminal_disposition,
        "terminal_disposition_reason": oracle.terminal_disposition_reason,
        "runtime_class": oracle.runtime_class,
        "runtime_class_reason": oracle.runtime_class_reason,
        "queue_closeout_ready": oracle.queue_closeout_ready,
        "queue_closeout_kind": oracle.queue_closeout_kind,
        "queue_closeout_reason": oracle.queue_closeout_reason,
        "decomposition_child_state": oracle.decomposition_child_state,
        "decomposition_child_reason": oracle.decomposition_child_reason,
        "decomposition_child_paths": list(oracle.decomposition_child_paths),
        "small_model_ready_child": oracle.small_model_ready_child,
        "small_model_readiness_state": oracle.small_model_readiness_state,
        "small_model_readiness_findings": [
            {
                "child_path": finding.child_path,
                "line_no": finding.line_no,
                "field": finding.field,
                "severity": finding.severity,
                "finding_kind": finding.finding_kind,
                "value": finding.value,
                "message": finding.message,
                "blocks_queue": finding.blocks_queue,
            }
            for finding in oracle.small_model_readiness_findings
        ],
    }


def _stop_item_ref(entry: dict[str, str] | None, state: dict[str, Any] | None) -> str | None:
    if not entry:
        return None
    plan = entry.get("plan") or None
    if not plan:
        return None
    order = entry.get("order")
    if order is None and state is not None:
        matching_item = next((item for item in state.get("items", []) if item.get("plan") == plan), None)
        if matching_item is not None:
            order = str(matching_item.get("order"))
    return f"{order}:{plan}" if order else plan


def _terminal_tail_stop(entry: dict[str, str]) -> bool:
    return (
        entry.get("stop_phase") == "terminal_docs_closeout"
        and bool(entry.get("stop_source_plan"))
        and bool(entry.get("stop_source_order"))
    )


def _stop_source_item_ref(entry: dict[str, str] | None) -> str | None:
    if not entry:
        return None
    plan = entry.get("stop_source_plan") or None
    if not plan:
        return None
    order = entry.get("stop_source_order")
    return f"{order}:{plan}" if order else plan


def _attributed_stop_plan(entry: dict[str, str] | None) -> str | None:
    if not entry:
        return None
    if _terminal_tail_stop(entry):
        return entry.get("stop_source_plan") or None
    return entry.get("plan") or None


def _attributed_stop_item_ref(
    entry: dict[str, str] | None,
    state: dict[str, Any] | None,
) -> str | None:
    if entry and _terminal_tail_stop(entry):
        return _stop_source_item_ref(entry)
    return _stop_item_ref(entry, state)


def _stop_belongs_to_active_item(entry: dict[str, str], active_item: dict[str, Any] | None) -> bool:
    if _terminal_tail_stop(entry):
        return False
    if active_item is None:
        return False
    if entry.get("plan") != active_item.get("plan"):
        return False
    entry_order = entry.get("order")
    if entry_order is not None and entry_order != str(active_item.get("order")):
        return False
    activated_at = active_item.get("activated_at")
    if activated_at and entry.get("at") and entry["at"] < str(activated_at):
        return False
    return True


def normalized_last_transition(state: dict[str, Any] | None) -> dict[str, Any]:
    transition = dict((state or {}).get("last_transition") or {})
    if not transition or state is None:
        return transition

    has_open_item = any(item.get("state") in ACTIVE_STATES for item in state.get("items", []))
    if (
        transition.get("kind") == "resume_parent_pending"
        and state.get("parent_resumed_at")
        and not state.get("parent_resume_pending_at")
        and not has_open_item
    ):
        transition.update(
            {
                "kind": "parent_resumed",
                "at": state.get("parent_resumed_at"),
                "parent_plan": state.get("parent_plan"),
                "resume_parent_plan": None,
                "queue_complete": True,
            }
        )
    return transition


def repair_legacy_parent_resumed_transition(state: dict[str, Any] | None) -> bool:
    if state is None:
        return False
    current_transition = dict(state.get("last_transition") or {})
    repaired_transition = normalized_last_transition(state)
    if (
        current_transition.get("kind") == "resume_parent_pending"
        and repaired_transition.get("kind") == "parent_resumed"
        and repaired_transition != current_transition
    ):
        state["last_transition"] = repaired_transition
        return True
    return False


def queue_runtime_context(
    paths: QueuePaths,
    state: dict[str, Any] | None,
    *,
    plan: str | None,
) -> dict[str, Any]:
    plan_ref = None
    if plan:
        try:
            plan_ref = project_relative_path(paths.root, plan, require_exists=False)
        except QueueError:
            plan_ref = plan

    log_entries = parse_log_entries(paths)
    stop_entries = [entry for entry in log_entries if entry.get("event") == "stop"]
    active_item = next((item for item in (state or {}).get("items", []) if item.get("state") == "active"), None)
    current_stop_entries = [
        entry for entry in stop_entries if _stop_belongs_to_active_item(entry, active_item)
    ]
    stop_reasons = [reason for reason in (entry.get("reason") for entry in current_stop_entries) if reason]
    latest_stop = current_stop_entries[-1] if current_stop_entries else None
    terminal_tail_stop = next(
        (entry for entry in reversed(stop_entries) if _terminal_tail_stop(entry)),
        None,
    )
    historical_stop = next(
        (
            entry
            for entry in reversed(stop_entries)
            if not _stop_belongs_to_active_item(entry, active_item)
        ),
        None,
    )
    latest_stop_reason = latest_stop.get("reason") if latest_stop else None
    latest_stop_reason_scope = "current_active" if latest_stop else ("historical" if historical_stop else "none")
    has_queue_context = state is not None or bool(log_entries)
    repeated_blocker_detected = False
    if latest_stop_reason:
        repeated_blocker_detected = stop_reasons.count(latest_stop_reason) >= 2
    latest_transition = normalized_last_transition(state)

    return {
        "plan_ref": plan_ref,
        "queue_mode_active": state is not None,
        "history_available": bool(log_entries),
        "current_active_plan": active_item.get("plan") if active_item else None,
        "loop_detected": any(reason in QUEUE_LOOP_STOP_REASONS for reason in stop_reasons) if has_queue_context else None,
        "repeated_blocker_detected": repeated_blocker_detected if has_queue_context else None,
        "max_iterations_reached": any(reason == "max_iterations_reached" for reason in stop_reasons) if has_queue_context else None,
        "latest_stop_reason": latest_stop_reason,
        "latest_stop_reason_scope": latest_stop_reason_scope,
        "latest_stop_at": latest_stop.get("at") if latest_stop else None,
        "latest_stop_plan": latest_stop.get("plan") if latest_stop else None,
        "latest_stop_item_ref": _stop_item_ref(latest_stop, state),
        "historical_stop_reason": historical_stop.get("reason") if historical_stop else None,
        "historical_stop_at": historical_stop.get("at") if historical_stop else None,
        "historical_stop_plan": _attributed_stop_plan(historical_stop),
        "historical_stop_item_ref": _attributed_stop_item_ref(historical_stop, state),
        "terminal_tail_stop_reason": terminal_tail_stop.get("reason") if terminal_tail_stop else None,
        "terminal_tail_stop_at": terminal_tail_stop.get("at") if terminal_tail_stop else None,
        "terminal_tail_stop_source_plan": (
            terminal_tail_stop.get("stop_source_plan") if terminal_tail_stop else None
        ),
        "terminal_tail_stop_source_item_ref": _stop_source_item_ref(terminal_tail_stop),
        "terminal_tail_stop_active_item_ref": _stop_item_ref(terminal_tail_stop, state),
        "stop_reasons": stop_reasons[-5:],
        "last_transition_kind": latest_transition.get("kind"),
        "last_transition_at": latest_transition.get("at"),
        "last_transition_queue_complete": latest_transition.get("queue_complete"),
        "last_transition_finalized_plan": latest_transition.get("finalized_plan"),
    }


@_shared_operation("runtime-context")
def queue_runtime_context_snapshot(
    paths: QueuePaths,
    *,
    plan: str | None,
) -> dict[str, Any]:
    """Read queue state and history through one recovery-aware shared-lock boundary."""
    state = load_state(paths)
    return queue_runtime_context(paths, state, plan=plan)


@_shared_operation("state-history-snapshot")
def queue_state_history_snapshot(paths: QueuePaths) -> dict[str, Any]:
    """Capture canonical queue state and parsed history under one shared lock."""
    return {
        "state": load_state(paths),
        "log_entries": parse_log_entries(paths),
    }


@_shared_operation("history")
def queue_history_report(paths: QueuePaths, *, limit: int = 20) -> dict[str, Any]:
    state = load_state(paths)
    entries = parse_log_entries(paths)
    active_item = next((item for item in (state or {}).get("items", []) if item.get("state") == "active"), None)
    total_entries = len(entries)
    selected_entries = entries if limit <= 0 else entries[-limit:]
    first_index = total_entries - len(selected_entries) + 1

    rendered_entries: list[dict[str, Any]] = []
    for offset, entry in enumerate(selected_entries):
        row: dict[str, Any] = {
            "index": first_index + offset,
            "at": entry.get("at"),
            "event": entry.get("event"),
            "plan": entry.get("plan"),
            "reason": entry.get("reason"),
            "order": entry.get("order"),
            "transaction_id": entry.get("transaction_id"),
            "transaction_seq": entry.get("transaction_seq"),
            "transaction_size": entry.get("transaction_size"),
            "skip_phase": entry.get("skip_phase"),
            "manager_mode_skip_id": entry.get("manager_mode_skip_id"),
            "required_manager_mode": entry.get("required_manager_mode"),
            "actual_manager_mode": entry.get("actual_manager_mode"),
            "manager_mode_state": entry.get("manager_mode_state"),
            "manager_mode_reason": entry.get("manager_mode_reason"),
            "stop_source_plan": entry.get("stop_source_plan"),
            "stop_source_order": entry.get("stop_source_order"),
            "stop_phase": entry.get("stop_phase"),
        }
        if entry.get("event") == "stop":
            if _terminal_tail_stop(entry):
                row["stop_scope"] = "terminal_tail"
            else:
                current_active = _stop_belongs_to_active_item(entry, active_item)
                row["stop_scope"] = "current_active" if current_active else "historical"
            row["stop_item_ref"] = _stop_item_ref(entry, state)
            row["active_stop_item_ref"] = _stop_item_ref(entry, state)
            row["stop_source_item_ref"] = _stop_source_item_ref(entry)
        else:
            row["stop_scope"] = "n/a"
            row["stop_item_ref"] = None
            row["active_stop_item_ref"] = None
            row["stop_source_item_ref"] = None
        rendered_entries.append(row)

    return {
        "report_kind": "planqueue_log_history",
        "read_only": True,
        "state_path": paths.state_path.relative_to(paths.root).as_posix(),
        "log_path": paths.log_path.relative_to(paths.root).as_posix(),
        "log_exists": paths.log_path.exists(),
        "queue_state_exists": state is not None,
        "active_plan": active_item.get("plan") if active_item else None,
        "active_order": active_item.get("order") if active_item else None,
        "total_entries": total_entries,
        "shown_entries": len(rendered_entries),
        "limit": limit,
        "entries": rendered_entries,
    }


@_shared_operation("show")
def show_queue(paths: QueuePaths) -> dict[str, Any]:
    return queue_snapshot(load_state(paths), paths)


def items_with_current_queue_activation_warnings(root: Path, items: Any) -> list[dict[str, Any]]:
    snapshot_items: list[dict[str, Any]] = []
    if not isinstance(items, list):
        return snapshot_items
    for raw_item in items:
        if not isinstance(raw_item, dict):
            continue
        item = dict(raw_item)
        plan = str(item.get("plan") or "")
        current_warning = queue_activation_import_warning(root, plan) if plan else None
        if current_warning:
            item["queue_activation_warning"] = current_warning
        else:
            item.pop("queue_activation_warning", None)
        snapshot_items.append(item)
    return snapshot_items


def queue_snapshot(
    state: dict[str, Any] | None,
    paths: QueuePaths,
    *,
    context: ContractContext | None = None,
) -> dict[str, Any]:
    if state is None:
        return {
            "exists": False,
            "state_path": paths.state_path.relative_to(paths.root).as_posix(),
            "log_path": paths.log_path.relative_to(paths.root).as_posix(),
            "queue_empty": True,
            "items": [],
            "pending_count": 0,
            "done_count": 0,
            "superseded_count": 0,
            "closed_non_executable_count": 0,
            "skipped_manager_mode_count": 0,
        }
    snapshot_items = items_with_current_queue_activation_warnings(paths.root, state.get("items", []))
    resume_parent_plan = pending_parent_resume_plan(state)
    active_item = next((item for item in state["items"] if item["state"] == "active"), None)
    pending_items = [item for item in state["items"] if item["state"] == "pending"]
    done_items = [item for item in state["items"] if item["state"] == "done"]
    superseded_items = [item for item in state["items"] if item["state"] == "superseded"]
    closed_non_executable_items = [item for item in state["items"] if item["state"] == CLOSED_NON_EXECUTABLE_STATE]
    skipped_manager_mode_items = [
        item for item in state["items"] if item["state"] == SKIPPED_MANAGER_MODE_STATE
    ]
    effective_plan = active_item["plan"] if active_item else resume_parent_plan
    runtime_payload = plan_runtime_payload(
        paths.root,
        effective_plan,
        context=context or paths.context or _ACTIVE_QUEUE_CONTEXT.get(),
    )
    if active_item:
        effective_phase = "active_item"
    elif resume_parent_plan:
        effective_phase = "resume_parent_pending"
    elif pending_items:
        effective_phase = "pending_not_started"
    elif state["items"]:
        effective_phase = "queue_complete"
    else:
        effective_phase = None
    queue_context = queue_runtime_context(paths, state, plan=effective_plan)
    return {
        "exists": True,
        "state_path": paths.state_path.relative_to(paths.root).as_posix(),
        "log_path": paths.log_path.relative_to(paths.root).as_posix(),
        "queue_empty": not any(item["state"] in ACTIVE_STATES for item in state["items"])
        and resume_parent_plan is None,
        "mode": state["mode"],
        "resume_parent": state["resume_parent"],
        "resume_parent_plan": resume_parent_plan,
        "parent_plan": state.get("parent_plan"),
        "parent_resume_pending_at": state.get("parent_resume_pending_at"),
        "parent_resumed_at": state.get("parent_resumed_at"),
        "source_plan": state.get("source_plan"),
        "cursor": state["cursor"],
        "active_plan": active_item["plan"] if active_item else None,
        "active_order": active_item["order"] if active_item else None,
        "effective_plan": effective_plan,
        "effective_phase": effective_phase,
        "pending_count": len(pending_items),
        "done_count": len(done_items),
        "superseded_count": len(superseded_items),
        "closed_non_executable_count": len(closed_non_executable_items),
        "skipped_manager_mode_count": len(skipped_manager_mode_items),
        "next_pending_plan": pending_items[0]["plan"] if pending_items else None,
        "last_stop": state.get("last_stop"),
        "last_transition": normalized_last_transition(state),
        "last_planpath_override": state.get("last_planpath_override"),
        "effective_runtime": runtime_payload,
        "queue_runtime_context": queue_context,
        "items": snapshot_items,
    }


def build_state(
    *,
    mode: str,
    items: list[dict[str, Any]],
    now: str,
    source_plan: str | None = None,
    parent_plan: str | None = None,
    resume_parent: str = "none",
) -> dict[str, Any]:
    return {
        "version": STATE_VERSION,
        "mode": mode,
        "source_plan": source_plan,
        "parent_plan": parent_plan,
        "resume_parent": normalize_resume_parent(resume_parent),
        "created_at": now,
        "updated_at": now,
        "cursor": 0,
        "parent_resume_pending_at": None,
        "parent_resumed_at": None,
        "last_stop": None,
        "last_transition": None,
        "last_planpath_override": None,
        "items": items,
    }


def pending_parent_resume_plan(state: dict[str, Any]) -> str | None:
    if state.get("parent_resume_pending_at") and not state.get("parent_resumed_at") and state.get("parent_plan"):
        return str(state["parent_plan"])
    return None


def _terminal_admission_rejection(
    active_plan: str,
    runtime_payload: dict[str, Any],
    *,
    asserted_status: str | None,
    reason_code: str,
) -> QueueError:
    payload = {
        "advanced": False,
        "finalized_plan": None,
        "next_plan": None,
        "queue_complete": False,
        "active_plan": active_plan,
        "asserted_final_status": asserted_status,
        "oracle_status": runtime_payload.get("status_value"),
        "terminal_disposition": runtime_payload.get("terminal_disposition"),
        "queue_closeout_kind": runtime_payload.get("queue_closeout_kind"),
        "queue_closeout_ready": runtime_payload.get("queue_closeout_ready"),
        "error": TERMINAL_ADMISSION_ERROR,
        "reason_code": reason_code,
    }
    return QueueError(
        f"{TERMINAL_ADMISSION_ERROR}: reason_code={reason_code}",
        payload=payload,
    )


def _admit_terminal_closeout(
    active_plan: str,
    runtime_payload: dict[str, Any],
    *,
    asserted_status: str | None = None,
) -> tuple[str, str]:
    """Return the Oracle-confirmed final state and display status or fail closed."""

    oracle_status = normalize_status(str(runtime_payload.get("status_value") or ""))
    asserted_normalized = (
        normalize_status(asserted_status) if asserted_status is not None else None
    )
    disposition = runtime_payload.get("terminal_disposition")
    if disposition == ACCEPTED_RED_TERMINAL_DISPOSITION:
        raise _terminal_admission_rejection(
            active_plan,
            runtime_payload,
            asserted_status=asserted_status,
            reason_code="accepted_red_reconciliation_required",
        )
    if asserted_normalized is not None and asserted_normalized != oracle_status:
        raise _terminal_admission_rejection(
            active_plan,
            runtime_payload,
            asserted_status=asserted_status,
            reason_code="terminal_status_assertion_mismatch",
        )
    if disposition != ORDINARY_TERMINAL_DISPOSITION:
        raise _terminal_admission_rejection(
            active_plan,
            runtime_payload,
            asserted_status=asserted_status,
            reason_code="terminal_disposition_invalid",
        )
    if (
        oracle_status not in FINAL_STATUS_TO_STATE
        or runtime_payload.get("queue_closeout_kind") != "terminal_status"
        or runtime_payload.get("queue_closeout_ready") is not True
    ):
        raise _terminal_admission_rejection(
            active_plan,
            runtime_payload,
            asserted_status=asserted_status,
            reason_code="terminal_closeout_not_ready",
        )

    return (
        oracle_status,
        "Done" if oracle_status == "done" else "Superseded",
    )


def _select_closeout_candidate(state: dict[str, Any]) -> dict[str, Any] | None:
    next_item = next((item for item in state["items"] if item["state"] == "pending"), None)
    if next_item is not None:
        return {
            "kind": "next_plan",
            "plan": str(next_item["plan"]),
            "order": int(next_item["order"]),
        }
    if (
        state["resume_parent"] == "run-parent-once"
        and state.get("parent_plan")
        and not pending_parent_resume_plan(state)
        and not state.get("parent_resumed_at")
    ):
        return {
            "kind": "resume_parent_plan",
            "plan": str(state["parent_plan"]),
            "order": None,
        }
    return None


def _validate_manager_mode(manager_mode: str, *, command: str) -> None:
    if manager_mode not in plan_status_oracle.ACTUAL_MANAGER_MODES:
        raise QueueError(
            f"Queue {command} manager mode must be one of: "
            + ", ".join(plan_status_oracle.ACTUAL_MANAGER_MODES)
        )


def _closeout_candidate_mode_admission(
    paths: QueuePaths,
    plan: str,
    manager_mode: str,
    *,
    candidate_kind: str,
) -> dict[str, object]:
    _validate_manager_mode(manager_mode, command=candidate_kind)
    try:
        rel_plan = project_relative_path(
            paths.root,
            plan,
            require_exists=candidate_kind != "next_plan",
        )
        plan_text = (paths.root / rel_plan).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        if candidate_kind == "next_plan":
            raise _PendingActivationModeReadFailure from exc
        payload = {
            "advanced": False,
            "error": "manager_mode_admission_carrier_error",
            "candidate_kind": candidate_kind,
            "candidate_plan": plan,
            "actual_manager_mode": manager_mode,
            "detail": str(exc),
        }
        raise QueueError(
            f"manager_mode_admission_carrier_error candidate={plan}: {exc}",
            payload=payload,
        ) from exc
    except (ValueError, QueueError) as exc:
        payload = {
            "advanced": False,
            "error": "manager_mode_admission_carrier_error",
            "candidate_kind": candidate_kind,
            "candidate_plan": plan,
            "actual_manager_mode": manager_mode,
            "detail": str(exc),
        }
        raise QueueError(
            f"manager_mode_admission_carrier_error candidate={plan}: {exc}",
            payload=payload,
        ) from exc
    try:
        plan_meta = plan_status_oracle.parse_plan_meta_admission_carrier(plan_text)
    except (ValueError, QueueError) as exc:
        payload = {
            "advanced": False,
            "error": "manager_mode_admission_carrier_error",
            "candidate_kind": candidate_kind,
            "candidate_plan": plan,
            "actual_manager_mode": manager_mode,
            "detail": str(exc),
        }
        raise QueueError(
            f"manager_mode_admission_carrier_error candidate={plan}: {exc}",
            payload=payload,
        ) from exc

    admission = plan_status_oracle.manager_mode_admission(plan_meta, manager_mode)
    if (
        not admission["manager_mode_admitted"]
        and admission["manager_mode_state"] != "mismatch"
    ):
        payload = {
            "advanced": False,
            "error": "manager_mode_admission_blocked",
            "candidate_kind": candidate_kind,
            "candidate_plan": rel_plan,
            **admission,
        }
        raise QueueError(
            "manager_mode_admission_blocked "
            f"candidate_kind={candidate_kind} candidate_plan={rel_plan} "
            f"state={admission['manager_mode_state']} "
            f"reason={admission['manager_mode_reason']}",
            payload=payload,
        )
    return admission


def _pending_activation_mode_admission(
    paths: QueuePaths,
    pending_item: dict[str, Any],
    manager_mode: str,
) -> dict[str, object]:
    """Classify a pending activation candidate without bypassing fresh lint failures."""

    try:
        return _closeout_candidate_mode_admission(
            paths,
            str(pending_item["plan"]),
            manager_mode,
            candidate_kind="next_plan",
        )
    except _PendingActivationModeReadFailure:
        full_lint_blocker = _plan_lint_activation_blocker(paths.root, pending_item)
        if full_lint_blocker is None:
            full_lint_blocker = f"{PLAN_LINT_ACTIVATION_BLOCKER_PREFIX} candidate_unreadable"
        raise QueueError(full_lint_blocker) from None


def _raise_non_skippable_manager_mode_mismatch(
    *,
    plan: str,
    candidate_kind: str,
    admission: dict[str, object],
) -> None:
    payload = {
        "advanced": False,
        "closeout_kind": "manager_mode_mismatch",
        "candidate_kind": candidate_kind,
        "candidate_plan": plan,
        **admission,
    }
    raise QueueError(
        "manager_mode_mismatch "
        f"candidate_kind={candidate_kind} candidate_plan={plan} "
        f"state={admission['manager_mode_state']} "
        f"reason={admission['manager_mode_reason']}",
        payload=payload,
    )


def _assert_active_manager_mode(
    paths: QueuePaths,
    active_item: dict[str, Any],
    manager_mode: str,
) -> None:
    admission = _closeout_candidate_mode_admission(
        paths,
        str(active_item["plan"]),
        manager_mode,
        candidate_kind="active_plan",
    )
    if not admission["manager_mode_admitted"]:
        _raise_non_skippable_manager_mode_mismatch(
            plan=str(active_item["plan"]),
            candidate_kind="active_plan",
            admission=admission,
        )


def _manager_mode_skip_receipt(
    *,
    plan: str,
    skip_phase: str,
    admission: dict[str, object],
    order: int | None = None,
) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "plan": plan,
        "skip_phase": skip_phase,
        "required_manager_mode": admission["required_manager_mode"],
        "actual_manager_mode": admission["actual_manager_mode"],
        "manager_mode_state": "mismatch",
        "manager_mode_reason": "required_mode_mismatch",
    }
    if order is not None:
        receipt["order"] = order
        receipt["manager_mode_skip_id"] = uuid.uuid4().hex
    return receipt


def _skip_manager_mode_audit_row(receipt: dict[str, Any], *, at: str) -> dict[str, Any]:
    return _audit_row(
        "skip_manager_mode",
        at=at,
        plan=receipt["plan"],
        order=receipt.get("order"),
        skip_phase=receipt["skip_phase"],
        manager_mode_skip_id=receipt.get("manager_mode_skip_id"),
        required_manager_mode=receipt["required_manager_mode"],
        actual_manager_mode=receipt["actual_manager_mode"],
        manager_mode_state=receipt["manager_mode_state"],
        manager_mode_reason=receipt["manager_mode_reason"],
    )


def _mark_item_skipped_manager_mode(
    item: dict[str, Any],
    receipt: dict[str, Any],
    *,
    at: str,
) -> None:
    item.update(receipt)
    item["state"] = SKIPPED_MANAGER_MODE_STATE
    item["completed_at"] = at
    item["final_status"] = None
    item["runtime_class"] = None
    item["closeout_kind"] = "manager_mode_mismatch"
    item["closeout_reason"] = "required_mode_mismatch"


def _collection_mode_filter(
    paths: QueuePaths,
    items: list[dict[str, Any]],
    *,
    manager_mode: str,
    at: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    _validate_manager_mode(manager_mode, command="collection")
    admitted: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    for item in items:
        plan = str(item["plan"])
        admission = _closeout_candidate_mode_admission(
            paths,
            plan,
            manager_mode,
            candidate_kind="collection_plan",
        )
        if admission["manager_mode_admitted"]:
            copied = dict(item)
            copied["order"] = len(admitted) + 1
            admitted.append(copied)
            continue
        receipt = _manager_mode_skip_receipt(
            plan=plan,
            skip_phase="collection",
            admission=admission,
        )
        skipped.append(receipt)
        audit_rows.append(_skip_manager_mode_audit_row(receipt, at=at))
    return admitted, skipped, audit_rows


def manual_items(
    root: Path,
    plans: list[str],
    now: str,
    *,
    context: ContractContext | None = None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    resolved_context = context or _ACTIVE_QUEUE_CONTEXT.get()
    for index, raw_plan in enumerate(plans, start=1):
        plan = project_relative_path(root, raw_plan)
        enforce_queue_activation_admission(root, plan, context=resolved_context)
        item = {
            "order": index,
            "plan": plan,
            "source": "manual_args",
            "state": "pending",
            "added_at": now,
            "activated_at": None,
            "completed_at": None,
            "final_status": None,
            "runtime_class": None,
            "closeout_kind": None,
            "closeout_reason": None,
        }
        activation_warning = queue_activation_import_warning(root, plan, context=resolved_context)
        if activation_warning:
            item["queue_activation_warning"] = activation_warning
        items.append(item)
    return items


def validate_explicit_plan_for_queue(
    root: Path,
    raw_plan: str,
    *,
    context: ContractContext | None = None,
) -> str:
    plan = project_relative_path(root, raw_plan)
    plan_path = PurePosixPath(plan)
    if plan_path.parts[:2] != ("docs", "plans") or plan_path.suffix != ".md":
        raise QueueError(f"Queue append path must be a repo-relative docs/plans/*.md file: {plan}")
    if plan in {"docs/plans/README.md", "docs/plans/_template.md"}:
        raise QueueError(f"Queue append path is not an executable plan file: {plan}")
    try:
        plan_status_oracle.oracle_result(
            root / plan,
            context=context or _ACTIVE_QUEUE_CONTEXT.get(),
        )
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise QueueError(f"Queue append plan is not queue-lintable: {plan}: {exc}") from exc
    return plan


def validate_child_plan_for_queue(
    root: Path,
    raw_child: str,
    *,
    require_small_model_readiness: bool = False,
    context: ContractContext | None = None,
) -> str:
    child = project_relative_path(root, raw_child)
    child_path = PurePosixPath(child)
    if child_path.parts[:2] != ("docs", "plans") or child_path.suffix != ".md":
        raise QueueError(f"Child queue path must be a repo-relative docs/plans/*.md file: {child}")
    if child in {"docs/plans/README.md", "docs/plans/_template.md"}:
        raise QueueError(f"Child queue path is not an executable plan file: {child}")
    try:
        plan_status_oracle.oracle_result(
            root / child,
            context=context or _ACTIVE_QUEUE_CONTEXT.get(),
        )
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise QueueError(f"Child plan is not queue-lintable: {child}: {exc}") from exc
    if require_small_model_readiness:
        readiness_findings = plan_status_oracle.small_model_ready_child_findings(
            root / child,
            child_path=child,
            promoted=True,
        )
        readiness_blockers = [finding for finding in readiness_findings if finding.blocks_queue]
        if readiness_blockers:
            first_blocker = readiness_blockers[0]
            raise QueueError(
                "small_model_ready_child_blocked: "
                f"{child}: {first_blocker.field}: {first_blocker.finding_kind}: {first_blocker.message}"
            )
    return child


def small_model_readiness_payload(root: Path, child: str, *, required: bool) -> dict[str, Any]:
    findings: tuple[plan_status_oracle.SmallModelReadinessFinding, ...] = ()
    if required:
        findings = plan_status_oracle.small_model_ready_child_findings(
            root / child,
            child_path=child,
            promoted=True,
        )
    ready_child, readiness_state = plan_status_oracle.small_model_readiness_summary(
        findings,
        assessed_children=(child,) if required else (),
    )
    return {
        "small_model_ready_child": ready_child,
        "small_model_readiness_state": readiness_state,
        "small_model_readiness_findings": [
            {
                "child_path": finding.child_path,
                "line_no": finding.line_no,
                "field": finding.field,
                "severity": finding.severity,
                "finding_kind": finding.finding_kind,
                "value": finding.value,
                "message": finding.message,
                "blocks_queue": finding.blocks_queue,
            }
            for finding in findings
        ],
    }


def status_items(
    root: Path,
    statuses: list[str],
    now: str,
    *,
    context: ContractContext | None = None,
) -> list[dict[str, Any]]:
    wanted = {normalize_status(status) for status in statuses}
    items: list[dict[str, Any]] = []
    resolved_context = context or _ACTIVE_QUEUE_CONTEXT.get()
    for plan_path in iter_plan_files(root):
        status_value = normalize_status(extract_status_value(plan_path))
        if status_value not in wanted:
            continue
        rel_plan = plan_path.relative_to(root).as_posix()
        enforce_queue_activation_admission(root, rel_plan, context=resolved_context)
        item = {
            "order": len(items) + 1,
            "plan": rel_plan,
            "source": "status_query",
            "state": "pending",
            "added_at": now,
            "activated_at": None,
            "completed_at": None,
            "final_status": None,
            "runtime_class": None,
            "closeout_kind": None,
            "closeout_reason": None,
        }
        activation_warning = queue_activation_import_warning(
            root,
            str(item["plan"]),
            context=resolved_context,
        )
        if activation_warning:
            item["queue_activation_warning"] = activation_warning
        items.append(item)
    return items


def umbrella_items(
    root: Path,
    umbrella_plan: str,
    now: str,
    *,
    context: ContractContext | None = None,
) -> tuple[list[dict[str, Any]], str | None, str, str]:
    rel_plan = project_relative_path(root, umbrella_plan)
    plan_path = root / rel_plan
    text = plan_path.read_text(encoding="utf-8")
    resolved_context = context or _ACTIVE_QUEUE_CONTEXT.get()
    child_state = plan_status_oracle.decomposition_child_state(
        text,
        root=root,
        context=resolved_context,
    )
    if child_state.state in {"missing", "drafted"}:
        raise QueueError(f"decomposition_children_missing: {child_state.reason}")
    execution_plans, execution_resume_parent = parse_execution_queue(text)
    source = "execution_queue" if execution_plans else "none"

    if execution_plans:
        raw_plans = execution_plans
    else:
        strict = plan_status_oracle.strict_plan_meta_json(text)
        if strict.state != "valid" or not isinstance(strict.plan_meta, dict):
            raise QueueError(f"plan_meta_strict_read_failed: {rel_plan}: reason_code={strict.reason_code}")
        meta = strict.plan_meta
        schema_class, _schema_findings = plan_lint.classify_plan_schema_version(plan_path, text.splitlines())
        if schema_class == "v2" and isinstance(meta, dict) and "followups_out" in meta:
            raise QueueError("V2 plan illegally carries plan_meta.followups_out; external backlog never enters queue")
        if schema_class == "unsupported":
            raise QueueError("unsupported_plan_schema_for_legacy_queue_fallback")
        followups_out = meta.get("followups_out") if isinstance(meta, dict) and schema_class == "legacy_v1" else None
        followup_plans: list[str] = []
        if isinstance(followups_out, list):
            for row in followups_out:
                if isinstance(row, dict) and isinstance(row.get("plan"), str) and row["plan"].strip():
                    followup_plans.append(row["plan"].strip())
        next_plans = meta.get("next_plans") if isinstance(meta, dict) else None
        normalized_next: list[str] = []
        if isinstance(next_plans, list):
            normalized_next = [str(item).strip() for item in next_plans if str(item).strip()]
            if normalized_next and followup_plans and followup_plans[: len(normalized_next)] != normalized_next:
                raise QueueError(
                    "Legacy umbrella import is not truthful: `next_plans[]` does not match the prefix of "
                    "`followups_out[].plan`"
                )
        if followup_plans:
            raw_plans = followup_plans
            source = "legacy_followups_out"
        elif normalized_next:
            raw_plans = normalized_next
            source = "next_plans"
        else:
            raw_plans = []
            source = "none"

    items: list[dict[str, Any]] = []
    require_small_model_readiness = child_state.state == "queue_ready"
    for index, raw_child in enumerate(raw_plans, start=1):
        child = validate_child_plan_for_queue(
            root,
            raw_child,
            require_small_model_readiness=require_small_model_readiness,
            context=resolved_context,
        )
        enforce_queue_activation_admission(root, child, context=resolved_context)
        readiness_payload = small_model_readiness_payload(
            root,
            child,
            required=require_small_model_readiness,
        )
        item = {
            "order": index,
            "plan": child,
            "source": source,
            "state": "pending",
            "added_at": now,
            "activated_at": None,
            "completed_at": None,
            "final_status": None,
            "runtime_class": None,
            "closeout_kind": None,
            "closeout_reason": None,
            **readiness_payload,
        }
        activation_warning = queue_activation_import_warning(root, child, context=resolved_context)
        if activation_warning:
            item["queue_activation_warning"] = activation_warning
        items.append(item)
    return items, execution_resume_parent, rel_plan, source


@_exclusive_operation("set")
def set_queue(
    paths: QueuePaths,
    *,
    plans: list[str] | None = None,
    statuses: list[str] | None = None,
    umbrella: str | None = None,
    resume_parent: str | None = None,
    manager_mode: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    ts = now or iso_now()
    existing_state = load_state(paths)
    existing_active = next(
        (
            item
            for item in (existing_state or {}).get("items", [])
            if item.get("state") == "active"
        ),
        None,
    )
    if existing_active is not None:
        payload = {
            "replaced": False,
            "error": "queue_active_replacement_blocked",
            "active_plan": existing_active.get("plan"),
            "active_order": existing_active.get("order"),
        }
        raise QueueError(
            "queue_active_replacement_blocked: "
            f"active_plan={existing_active.get('plan')} "
            f"order={existing_active.get('order')}",
            payload=payload,
        )

    if umbrella:
        items, execution_resume, umbrella_plan, expansion_source = umbrella_items(paths.root, umbrella, ts)
        skipped_incompatible: list[dict[str, Any]] = []
        skip_rows: list[dict[str, Any]] = []
        if manager_mode is not None:
            items, skipped_incompatible, skip_rows = _collection_mode_filter(
                paths,
                items,
                manager_mode=manager_mode,
                at=ts,
            )
        if skipped_incompatible and not items:
            _commit_transaction(
                paths,
                operation="set",
                after_state=existing_state,
                audit_rows=skip_rows,
            )
            return {
                **queue_snapshot(existing_state, paths),
                "skipped_incompatible": skipped_incompatible,
                "replaced": False,
            }
        resolved_resume = normalize_resume_parent(resume_parent or execution_resume or "owner-restamp-required")
        state = build_state(
            mode="umbrella_children",
            items=items,
            now=ts,
            source_plan=umbrella_plan,
            parent_plan=umbrella_plan,
            resume_parent=resolved_resume,
        )
        _commit_transaction(
            paths,
            operation="set",
            after_state=state,
            audit_rows=[
                _audit_row(
                    "set",
                    at=ts,
                    mode="umbrella_children",
                    source_plan=umbrella_plan,
                    items=len(items),
                    resume_parent=resolved_resume,
                ),
                _audit_row(
                    "expand",
                    at=ts,
                    source_plan=umbrella_plan,
                    source=expansion_source,
                    count=len(items),
                    expansion=("items" if items else "none"),
                ),
                *skip_rows,
            ],
        )
        return {
            **queue_snapshot(state, paths),
            "skipped_incompatible": skipped_incompatible,
            "replaced": True,
        }

    if statuses:
        items = status_items(paths.root, statuses, ts)
        skipped_incompatible = []
        skip_rows = []
        if manager_mode is not None:
            items, skipped_incompatible, skip_rows = _collection_mode_filter(
                paths,
                items,
                manager_mode=manager_mode,
                at=ts,
            )
        if skipped_incompatible and not items:
            _commit_transaction(
                paths,
                operation="set",
                after_state=existing_state,
                audit_rows=skip_rows,
            )
            return {
                **queue_snapshot(existing_state, paths),
                "skipped_incompatible": skipped_incompatible,
                "replaced": False,
            }
        resolved_resume = normalize_resume_parent(resume_parent or "none")
        state = build_state(mode="status_query", items=items, now=ts, resume_parent=resolved_resume)
        _commit_transaction(
            paths,
            operation="set",
            after_state=state,
            audit_rows=[
                _audit_row(
                    "set",
                    at=ts,
                    mode="status_query",
                    items=len(items),
                    statuses="|".join(sorted(normalize_status(s) for s in statuses)),
                ),
                *skip_rows,
            ],
        )
        return {
            **queue_snapshot(state, paths),
            "skipped_incompatible": skipped_incompatible,
            "replaced": True,
        }

    if not plans:
        raise QueueError("Queue set requires explicit plans, `--status ...`, or `--from-umbrella <PLAN>`")
    items = manual_items(paths.root, plans, ts)
    skipped_incompatible = []
    skip_rows = []
    if manager_mode is not None:
        items, skipped_incompatible, skip_rows = _collection_mode_filter(
            paths,
            items,
            manager_mode=manager_mode,
            at=ts,
        )
    if skipped_incompatible and not items:
        _commit_transaction(
            paths,
            operation="set",
            after_state=existing_state,
            audit_rows=skip_rows,
        )
        return {
            **queue_snapshot(existing_state, paths),
            "skipped_incompatible": skipped_incompatible,
            "replaced": False,
        }
    resolved_resume = normalize_resume_parent(resume_parent or "none")
    state = build_state(mode="manual_args", items=items, now=ts, resume_parent=resolved_resume)
    _commit_transaction(
        paths,
        operation="set",
        after_state=state,
        audit_rows=[
            _audit_row(
                "set",
                at=ts,
                mode="manual_args",
                items=len(items),
                resume_parent=resolved_resume,
            ),
            *skip_rows,
        ],
    )
    return {
        **queue_snapshot(state, paths),
        "skipped_incompatible": skipped_incompatible,
        "replaced": True,
    }


@_exclusive_operation("append")
def append_queue(
    paths: QueuePaths,
    plans: list[str],
    *,
    manager_mode: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    state = load_state(paths)
    if state is None:
        raise QueueError(
            "Queue is not initialized; use planveyor_q_set first: "
            f"{paths.state_path.relative_to(paths.root).as_posix()}"
        )
    if not plans:
        raise QueueError("Queue append requires at least one explicit docs/plans/*.md path")
    if pending_parent_resume_plan(state) is not None:
        raise QueueError("Queue append is blocked while parent resume is pending; resume parent before appending")

    rel_plans = [validate_explicit_plan_for_queue(paths.root, raw_plan) for raw_plan in plans]
    seen_inputs: set[str] = set()
    duplicate_inputs: list[str] = []
    for rel_plan in rel_plans:
        if rel_plan in seen_inputs:
            duplicate_inputs.append(rel_plan)
        seen_inputs.add(rel_plan)
    if duplicate_inputs:
        duplicates = ", ".join(sorted(set(duplicate_inputs)))
        raise QueueError(f"Queue append duplicate input arguments are not allowed: {duplicates}")

    existing_plans = {str(item.get("plan")) for item in state.get("items", []) if item.get("plan")}
    skipped_duplicates = [rel_plan for rel_plan in rel_plans if rel_plan in existing_plans]
    appendable_plans = [rel_plan for rel_plan in rel_plans if rel_plan not in existing_plans]
    ts = now or iso_now()
    max_order = max((int(item.get("order", 0)) for item in state.get("items", [])), default=0)
    appended_items: list[dict[str, Any]] = []
    skipped_incompatible: list[dict[str, Any]] = []
    skip_rows: list[dict[str, Any]] = []
    for rel_plan in appendable_plans:
        enforce_queue_activation_admission(paths.root, rel_plan)
        if manager_mode is not None:
            admission = _closeout_candidate_mode_admission(
                paths,
                rel_plan,
                manager_mode,
                candidate_kind="collection_plan",
            )
            if not admission["manager_mode_admitted"]:
                receipt = _manager_mode_skip_receipt(
                    plan=rel_plan,
                    skip_phase="collection",
                    admission=admission,
                )
                skipped_incompatible.append(receipt)
                skip_rows.append(_skip_manager_mode_audit_row(receipt, at=ts))
                continue
        item = {
            "order": max_order + len(appended_items) + 1,
            "plan": rel_plan,
            "source": "manual_append",
            "state": "pending",
            "added_at": ts,
            "activated_at": None,
            "completed_at": None,
            "final_status": None,
            "runtime_class": None,
            "closeout_kind": None,
            "closeout_reason": None,
        }
        activation_warning = queue_activation_import_warning(paths.root, rel_plan)
        if activation_warning:
            item["queue_activation_warning"] = activation_warning
        appended_items.append(item)

    if appended_items:
        state["items"].extend(appended_items)
        state["updated_at"] = ts
    _commit_transaction(
        paths,
        operation="append",
        after_state=state,
        audit_rows=[
            _audit_row(
                "append",
                at=ts,
                appended=len(appended_items),
                skipped_duplicates=len(skipped_duplicates),
                plans="|".join(item["plan"] for item in appended_items),
                duplicates="|".join(skipped_duplicates),
            ),
            *skip_rows,
        ],
    )
    return {
        **queue_snapshot(state, paths),
        "appended": [item["plan"] for item in appended_items],
        "skipped_duplicates": skipped_duplicates,
        "skipped_incompatible": skipped_incompatible,
        "rejected": [],
        "append_event": {
            "at": ts,
            "appended_count": len(appended_items),
            "skipped_duplicate_count": len(skipped_duplicates),
            "skipped_incompatible_count": len(skipped_incompatible),
        },
    }


@_exclusive_operation("clear")
def clear_queue(paths: QueuePaths) -> dict[str, Any]:
    state_exists = paths.state_path.exists()
    _commit_transaction(
        paths,
        operation="clear",
        after_state=None,
        audit_rows=[_audit_row("clear", state_exists="yes" if state_exists else "no")],
    )
    return queue_snapshot(None, paths)


@_exclusive_operation("next")
def activate_next(
    paths: QueuePaths,
    *,
    manager_mode: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    state = load_state(paths)
    if state is None:
        raise QueueError(f"Queue is not initialized: {paths.state_path.relative_to(paths.root).as_posix()}")
    active_item = next((item for item in state["items"] if item["state"] == "active"), None)
    if active_item is not None:
        if manager_mode is not None:
            _assert_active_manager_mode(paths, active_item, manager_mode)
        return {
            **queue_snapshot(state, paths),
            "activated": False,
            "queue_empty": False,
            "skipped_incompatible": [],
        }

    ts = now or iso_now()
    skipped_incompatible: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []

    while True:
        pending_item = next((item for item in state["items"] if item["state"] == "pending"), None)
        if pending_item is None:
            resume_parent_plan = pending_parent_resume_plan(state)
            if resume_parent_plan is not None and manager_mode is not None:
                admission = _closeout_candidate_mode_admission(
                    paths,
                    resume_parent_plan,
                    manager_mode,
                    candidate_kind="resume_parent_plan",
                )
                if not admission["manager_mode_admitted"]:
                    if audit_rows:
                        state["cursor"] = len(state["items"])
                        state["updated_at"] = ts
                        state["last_transition"] = {
                            "kind": "skip_manager_mode",
                            "at": ts,
                            "plan": skipped_incompatible[-1]["plan"],
                            "order": skipped_incompatible[-1]["order"],
                            "queue_complete": False,
                        }
                        _commit_transaction(
                            paths,
                            operation="next",
                            after_state=state,
                            audit_rows=audit_rows,
                        )
                    _raise_non_skippable_manager_mode_mismatch(
                        plan=resume_parent_plan,
                        candidate_kind="resume_parent_plan",
                        admission=admission,
                    )
            if audit_rows:
                state["cursor"] = len(state["items"])
                state["updated_at"] = ts
                state["last_transition"] = {
                    "kind": "skip_manager_mode",
                    "at": ts,
                    "plan": skipped_incompatible[-1]["plan"],
                    "order": skipped_incompatible[-1]["order"],
                    "queue_complete": resume_parent_plan is None,
                }
                _commit_transaction(
                    paths,
                    operation="next",
                    after_state=state,
                    audit_rows=audit_rows,
                )
            if resume_parent_plan is not None:
                return {
                    **queue_snapshot(state, paths),
                    "activated": False,
                    "queue_empty": False,
                    "active_plan": resume_parent_plan,
                    "skipped_incompatible": skipped_incompatible,
                }
            return {
                **queue_snapshot(state, paths),
                "activated": False,
                "queue_empty": True,
                "skipped_incompatible": skipped_incompatible,
            }

        activation_blocker = queue_activation_admission_blocker(
            paths.root,
            str(pending_item.get("plan") or ""),
        )
        # Strict Meta read failures defer to the downstream fail-closed lanes
        # (manager-mode admission carrier error, fresh full-lint gate) so their
        # structured payloads keep precedence for malformed candidates.
        if activation_blocker and "plan_meta_strict_read_failed" not in activation_blocker:
            raise QueueError(activation_blocker)

        hard_dependency_blocker = blocking_dependency_blocker(paths.root, pending_item)
        if hard_dependency_blocker:
            payload = {
                **queue_snapshot(state, paths),
                "activated": False,
                "activation_blocker": hard_dependency_blocker,
                "skipped_incompatible": skipped_incompatible,
            }
            raise QueueError(hard_dependency_blocker, payload=payload)

        if manager_mode is not None:
            admission = _pending_activation_mode_admission(
                paths,
                pending_item,
                manager_mode,
            )
            if not admission["manager_mode_admitted"]:
                receipt = _manager_mode_skip_receipt(
                    plan=str(pending_item["plan"]),
                    order=int(pending_item["order"]),
                    skip_phase="activation",
                    admission=admission,
                )
                _mark_item_skipped_manager_mode(pending_item, receipt, at=ts)
                skipped_incompatible.append(receipt)
                audit_rows.append(_skip_manager_mode_audit_row(receipt, at=ts))
                continue

        dependency_blocker = same_queue_dependency_blocker(paths.root, state, pending_item)
        if dependency_blocker:
            if audit_rows:
                state["cursor"] = int(pending_item["order"]) - 1
                state["updated_at"] = ts
                state["last_transition"] = {
                    "kind": "skip_manager_mode",
                    "at": ts,
                    "plan": skipped_incompatible[-1]["plan"],
                    "order": skipped_incompatible[-1]["order"],
                    "queue_complete": False,
                    "activation_blocker": dependency_blocker,
                }
                _commit_transaction(
                    paths,
                    operation="next",
                    after_state=state,
                    audit_rows=audit_rows,
                )
            payload = {
                **queue_snapshot(state, paths),
                "activated": False,
                "activation_blocker": dependency_blocker,
                "skipped_incompatible": skipped_incompatible,
            }
            raise QueueError(dependency_blocker, payload=payload)

        full_lint_blocker = _plan_lint_activation_blocker(paths.root, pending_item)
        if full_lint_blocker:
            raise QueueError(full_lint_blocker)

        pending_item["state"] = "active"
        pending_item["activated_at"] = pending_item["activated_at"] or ts
        state["cursor"] = pending_item["order"] - 1
        state["updated_at"] = ts
        state["last_stop"] = None
        state["last_transition"] = {
            "kind": "activate",
            "at": ts,
            "plan": pending_item["plan"],
            "order": pending_item["order"],
        }
        audit_rows.append(
            _audit_row(
                "activate",
                at=ts,
                plan=pending_item["plan"],
                order=pending_item["order"],
            )
        )
        _commit_transaction(
            paths,
            operation="next",
            after_state=state,
            audit_rows=audit_rows,
        )
        return {
            **queue_snapshot(state, paths),
            "activated": True,
            "queue_empty": False,
            "skipped_incompatible": skipped_incompatible,
        }


def _select_transition_candidate_with_manager_mode(
    paths: QueuePaths,
    state: dict[str, Any],
    *,
    manager_mode: str,
    at: str,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[dict[str, Any]]]:
    _validate_manager_mode(manager_mode, command="activation")
    skipped_incompatible: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    while True:
        candidate = _select_closeout_candidate(state)
        if candidate is None:
            return None, skipped_incompatible, audit_rows
        candidate_kind = str(candidate["kind"])
        candidate_plan = str(candidate["plan"])
        if candidate_kind == "resume_parent_plan":
            admission = _closeout_candidate_mode_admission(
                paths,
                candidate_plan,
                manager_mode,
                candidate_kind=candidate_kind,
            )
            if not admission["manager_mode_admitted"]:
                _raise_non_skippable_manager_mode_mismatch(
                    plan=candidate_plan,
                    candidate_kind=candidate_kind,
                    admission=admission,
                )
            return candidate, skipped_incompatible, audit_rows

        pending_item = next(
            (
                item
                for item in state["items"]
                if item.get("state") == "pending"
                and item.get("order") == candidate.get("order")
                and item.get("plan") == candidate_plan
            ),
            None,
        )
        if pending_item is None:
            raise QueueError(
                "Queue closeout candidate drifted before mode classification: "
                f"kind={candidate_kind} plan={candidate_plan}"
            )
        activation_blocker = queue_activation_admission_blocker(paths.root, candidate_plan)
        # Strict Meta read failures defer to the downstream fail-closed lanes
        # (manager-mode admission carrier error, fresh full-lint gate) so their
        # structured payloads keep precedence for malformed candidates.
        if activation_blocker and "plan_meta_strict_read_failed" not in activation_blocker:
            raise QueueError(activation_blocker)
        hard_dependency_blocker = blocking_dependency_blocker(paths.root, pending_item)
        if hard_dependency_blocker:
            raise QueueError(hard_dependency_blocker)
        admission = _pending_activation_mode_admission(
            paths,
            pending_item,
            manager_mode,
        )
        if admission["manager_mode_admitted"]:
            return candidate, skipped_incompatible, audit_rows
        receipt = _manager_mode_skip_receipt(
            plan=candidate_plan,
            order=int(pending_item["order"]),
            skip_phase="activation",
            admission=admission,
        )
        _mark_item_skipped_manager_mode(pending_item, receipt, at=at)
        skipped_incompatible.append(receipt)
        audit_rows.append(_skip_manager_mode_audit_row(receipt, at=at))


def _finalize_active_item(
    paths: QueuePaths,
    state: dict[str, Any],
    active_item: dict[str, Any],
    *,
    ts: str,
    item_state: str,
    final_status: str,
    closeout_kind: str,
    closeout_reason: str,
    runtime_class: str | None = None,
    operation: str = "advance",
    transition_candidate: dict[str, Any] | None | _CloseoutCandidateUnset = _CLOSEOUT_CANDIDATE_UNSET,
    skipped_incompatible: list[dict[str, Any]] | None = None,
    skip_audit_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    skipped_incompatible = list(skipped_incompatible or [])
    skip_audit_rows = list(skip_audit_rows or [])
    if isinstance(transition_candidate, _CloseoutCandidateUnset):
        transition_candidate = _select_closeout_candidate(state)

    next_item: dict[str, Any] | None = None
    resume_parent_plan: str | None = None
    if transition_candidate is not None:
        candidate_kind = str(transition_candidate["kind"])
        candidate_plan = str(transition_candidate["plan"])
        if candidate_kind == "next_plan":
            candidate_order = int(transition_candidate["order"])
            next_item = next(
                (
                    item
                    for item in state["items"]
                    if item["state"] == "pending"
                    and item["order"] == candidate_order
                    and item["plan"] == candidate_plan
                ),
                None,
            )
            if next_item is None:
                raise QueueError(
                    "Queue closeout candidate drifted before commit: "
                    f"kind={candidate_kind} plan={candidate_plan}"
                )
        elif candidate_kind == "resume_parent_plan":
            if (
                any(item["state"] == "pending" for item in state["items"])
                or state["resume_parent"] != "run-parent-once"
                or str(state.get("parent_plan") or "") != candidate_plan
                or pending_parent_resume_plan(state)
                or state.get("parent_resumed_at")
            ):
                raise QueueError(
                    "Queue closeout candidate drifted before commit: "
                    f"kind={candidate_kind} plan={candidate_plan}"
                )
            resume_parent_plan = candidate_plan
        else:
            raise QueueError(f"Unsupported queue closeout candidate kind: {candidate_kind}")

    activation_blocker: str | None = None
    if next_item is not None:
        activation_blocker = queue_activation_admission_blocker(paths.root, str(next_item.get("plan") or ""))
        # Strict Meta read failures defer to the downstream fail-closed lanes
        # (manager-mode admission carrier error, fresh full-lint gate) so their
        # structured payloads keep precedence for malformed candidates.
        if activation_blocker and "plan_meta_strict_read_failed" not in activation_blocker:
            raise QueueError(activation_blocker)
        hard_dependency_blocker = blocking_dependency_blocker(paths.root, next_item)
        if hard_dependency_blocker:
            raise QueueError(hard_dependency_blocker)

        projected_state = {
            **state,
            "items": [dict(item) for item in state.get("items", [])],
        }
        projected_active_item = next(
            (
                item
                for item in projected_state["items"]
                if item.get("order") == active_item.get("order")
                and item.get("plan") == active_item.get("plan")
            ),
            None,
        )
        if projected_active_item is not None:
            projected_active_item["state"] = item_state
        projected_next_item = next(
            (
                item
                for item in projected_state["items"]
                if item.get("order") == next_item.get("order")
                and item.get("plan") == next_item.get("plan")
            ),
            next_item,
        )
        dependency_blocker = same_queue_dependency_blocker(paths.root, projected_state, projected_next_item)
        if dependency_blocker:
            if dependency_blocker.startswith("depends_on_skipped_incompatible:"):
                activation_blocker = dependency_blocker
                next_item = None
            else:
                raise QueueError(dependency_blocker)

        if next_item is not None:
            full_lint_blocker = _plan_lint_activation_blocker(paths.root, next_item)
            if full_lint_blocker:
                raise QueueError(full_lint_blocker)

    active_item["state"] = item_state
    active_item["final_status"] = final_status
    active_item["completed_at"] = ts
    active_item["closeout_kind"] = closeout_kind
    active_item["closeout_reason"] = closeout_reason
    if runtime_class is not None:
        active_item["runtime_class"] = runtime_class
    state["updated_at"] = ts
    state["last_stop"] = None

    event = {
        "done": "complete",
        "superseded": "supersede",
        CLOSED_NON_EXECUTABLE_STATE: "closeout_non_executable",
    }[item_state]
    audit_rows = [
        *skip_audit_rows,
        _audit_row(
            event,
            at=ts,
            plan=active_item["plan"],
            order=active_item["order"],
            final_status=final_status,
            runtime_class=runtime_class,
            closeout_kind=closeout_kind,
        )
    ]

    queue_complete = (
        next_item is None
        and resume_parent_plan is None
        and activation_blocker is None
    )
    if next_item is not None:
        next_item["state"] = "active"
        next_item["activated_at"] = next_item["activated_at"] or ts
        state["cursor"] = next_item["order"] - 1
        audit_rows.append(
            _audit_row(
                "advance",
                at=ts,
                from_plan=active_item["plan"],
                to_plan=next_item["plan"],
                order=next_item["order"],
            )
        )
    else:
        first_pending = next((item for item in state["items"] if item["state"] == "pending"), None)
        state["cursor"] = (
            int(first_pending["order"]) - 1
            if first_pending is not None
            else len(state["items"])
        )
        if resume_parent_plan is not None:
            state["parent_resume_pending_at"] = ts
            queue_complete = False

    transition_kind = "advance"
    if closeout_kind == "non_executable_ready":
        transition_kind = "runtime_reclassified"
    if next_item is None and resume_parent_plan is not None:
        transition_kind = "resume_parent_pending"
    elif activation_blocker is not None:
        transition_kind = "advance_blocked"
    elif next_item is None:
        transition_kind = "queue_complete"
    state["last_transition"] = {
        "kind": transition_kind,
        "at": ts,
        "finalized_plan": active_item["plan"],
        "final_status": final_status,
        "runtime_class": runtime_class,
        "closeout_kind": closeout_kind,
        "closeout_reason": closeout_reason,
        "next_plan": next_item["plan"] if next_item else None,
        "resume_parent_plan": resume_parent_plan,
        "queue_complete": queue_complete,
        "activation_blocker": activation_blocker,
    }
    _commit_transaction(
        paths,
        operation=operation,
        after_state=state,
        audit_rows=audit_rows,
    )
    return {
        **queue_snapshot(state, paths),
        "advanced": True,
        "finalized_plan": active_item["plan"],
        "final_status": final_status,
        "runtime_class": runtime_class,
        "closeout_kind": closeout_kind,
        "closeout_reason": closeout_reason,
        "next_plan": next_item["plan"] if next_item else None,
        "queue_complete": queue_complete,
        "resume_parent_plan": resume_parent_plan,
        "activation_blocker": activation_blocker,
        "skipped_incompatible": skipped_incompatible,
    }


@_exclusive_operation("advance")
def advance_queue(
    paths: QueuePaths,
    final_status: str,
    *,
    manager_mode: str | None = None,
    now: str | None = None,
    _operation: str = "advance",
) -> dict[str, Any]:
    state = load_state(paths)
    if state is None:
        raise QueueError(f"Queue is not initialized: {paths.state_path.relative_to(paths.root).as_posix()}")
    active_item = next((item for item in state["items"] if item["state"] == "active"), None)
    if active_item is None:
        raise QueueError("Queue advance requires an active item")
    if manager_mode is not None:
        _assert_active_manager_mode(paths, active_item, manager_mode)

    normalized_final = normalize_status(final_status)
    if normalized_final not in FINAL_STATUS_TO_STATE:
        raise QueueError("Queue advance supports only final statuses: Done | Superseded")

    runtime_payload = plan_runtime_payload(paths.root, active_item["plan"])
    if runtime_payload is None:
        raise QueueError("Queue advance could not read active plan runtime payload")
    oracle_final_norm, oracle_final_status = _admit_terminal_closeout(
        str(active_item["plan"]),
        runtime_payload,
        asserted_status=final_status,
    )

    ts = now or iso_now()
    transition_candidate: dict[str, Any] | None | _CloseoutCandidateUnset = _CLOSEOUT_CANDIDATE_UNSET
    skipped_incompatible: list[dict[str, Any]] = []
    skip_audit_rows: list[dict[str, Any]] = []
    if manager_mode is not None:
        (
            transition_candidate,
            skipped_incompatible,
            skip_audit_rows,
        ) = _select_transition_candidate_with_manager_mode(
            paths,
            state,
            manager_mode=manager_mode,
            at=ts,
        )
    return _finalize_active_item(
        paths,
        state,
        active_item,
        ts=ts,
        item_state=FINAL_STATUS_TO_STATE[oracle_final_norm],
        final_status=oracle_final_status,
        closeout_kind="terminal_status",
        closeout_reason=f"terminal status {final_status} requested explicitly",
        operation=_operation,
        transition_candidate=transition_candidate,
        skipped_incompatible=skipped_incompatible,
        skip_audit_rows=skip_audit_rows,
    )


@_exclusive_operation("closeout")
def closeout_queue(
    paths: QueuePaths,
    *,
    manager_mode: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    state = load_state(paths)
    if state is None:
        raise QueueError(f"Queue is not initialized: {paths.state_path.relative_to(paths.root).as_posix()}")
    active_item = next((item for item in state["items"] if item["state"] == "active"), None)
    if active_item is None:
        raise QueueError("Queue closeout requires an active item")
    if manager_mode is not None:
        _assert_active_manager_mode(paths, active_item, manager_mode)

    runtime_payload = plan_runtime_payload(paths.root, active_item["plan"])
    if runtime_payload is None:
        raise QueueError("Queue closeout could not read active plan runtime payload")

    oracle_status = normalize_status(str(runtime_payload.get("status_value") or ""))
    terminal_intent = (
        oracle_status in FINAL_STATUS_TO_STATE
        or runtime_payload.get("terminal_disposition") != ORDINARY_TERMINAL_DISPOSITION
    )
    non_executable_ready = (
        runtime_payload.get("queue_closeout_kind") == "non_executable_ready"
        and runtime_payload.get("queue_closeout_ready") is True
    )
    oracle_final_norm: str | None = None
    oracle_final_status: str | None = None
    if terminal_intent:
        oracle_final_norm, oracle_final_status = _admit_terminal_closeout(
            str(active_item["plan"]),
            runtime_payload,
        )
    elif not non_executable_ready:
        return {
            **queue_snapshot(state, paths),
            "advanced": False,
            "finalized_plan": None,
            "final_status": None,
            "runtime_class": runtime_payload["runtime_class"],
            "closeout_kind": runtime_payload["queue_closeout_kind"],
            "closeout_reason": runtime_payload["queue_closeout_reason"],
            "queue_closeout_ready": False,
            "next_plan": None,
            "queue_complete": False,
            "resume_parent_plan": pending_parent_resume_plan(state),
        }

    ts = now or iso_now()
    transition_candidate = _select_closeout_candidate(state)
    skipped_incompatible: list[dict[str, Any]] = []
    skip_audit_rows: list[dict[str, Any]] = []
    if transition_candidate is not None:
        if manager_mode is None:
            payload = {
                "advanced": False,
                "error": "manager_mode_required",
                "candidate_kind": transition_candidate["kind"],
                "candidate_plan": transition_candidate["plan"],
            }
            raise QueueError(
                "Queue closeout requires --manager-mode before activating "
                f"{transition_candidate['kind']}={transition_candidate['plan']}",
                payload=payload,
            )
        (
            transition_candidate,
            skipped_incompatible,
            skip_audit_rows,
        ) = _select_transition_candidate_with_manager_mode(
            paths,
            state,
            manager_mode=manager_mode,
            at=ts,
        )
    if terminal_intent:
        assert oracle_final_norm is not None
        assert oracle_final_status is not None
        return _finalize_active_item(
            paths,
            state,
            active_item,
            ts=ts,
            item_state=FINAL_STATUS_TO_STATE[oracle_final_norm],
            final_status=oracle_final_status,
            closeout_kind="terminal_status",
            closeout_reason=(
                f"terminal status {runtime_payload['status_value']} requested explicitly"
            ),
            operation="closeout",
            transition_candidate=transition_candidate,
            skipped_incompatible=skipped_incompatible,
            skip_audit_rows=skip_audit_rows,
        )

    if non_executable_ready:
        return _finalize_active_item(
            paths,
            state,
            active_item,
            ts=ts,
            item_state=CLOSED_NON_EXECUTABLE_STATE,
            final_status=str(runtime_payload["status_value"]),
            closeout_kind=str(runtime_payload["queue_closeout_kind"]),
            closeout_reason=str(runtime_payload["queue_closeout_reason"]),
            runtime_class=str(runtime_payload["runtime_class"]),
            operation="closeout",
            transition_candidate=transition_candidate,
            skipped_incompatible=skipped_incompatible,
            skip_audit_rows=skip_audit_rows,
        )

    raise AssertionError("terminal closeout admission did not select a closeout branch")


def _invalid_stop_source(source_plan: str, detail: str) -> QueueError:
    return QueueError(
        f"source_provenance_invalid: {detail}: {source_plan}",
        payload={
            "error": "source_provenance_invalid",
            "reason_code": "source_provenance_invalid",
            "source_provenance_detail": detail,
            "source_plan": source_plan,
            "mutation_performed": False,
        },
    )


def _resolve_terminal_stop_source(
    paths: QueuePaths,
    state: dict[str, Any],
    source_plan: str,
) -> tuple[str, dict[str, Any]]:
    try:
        normalized_source = project_relative_path(paths.root, source_plan)
    except QueueError as exc:
        raise _invalid_stop_source(source_plan, "missing_or_invalid") from exc

    matching_items: list[dict[str, Any]] = []
    for item in state.get("items", []):
        try:
            normalized_item_plan = project_relative_path(
                paths.root,
                str(item.get("plan") or ""),
                require_exists=False,
            )
        except QueueError:
            continue
        if normalized_item_plan == normalized_source:
            matching_items.append(item)

    if not matching_items:
        raise _invalid_stop_source(normalized_source, "not_in_queue")
    if len(matching_items) != 1:
        raise _invalid_stop_source(normalized_source, "ambiguous")
    source_item = matching_items[0]
    if source_item.get("state") not in FINALIZED_STATES:
        raise _invalid_stop_source(normalized_source, "non_terminal")
    return normalized_source, source_item


@_exclusive_operation("stop")
def stop_queue(
    paths: QueuePaths,
    reason: str,
    *,
    source_plan: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    state = load_state(paths)
    if state is None:
        raise QueueError(f"Queue is not initialized: {paths.state_path.relative_to(paths.root).as_posix()}")
    active_item = next((item for item in state["items"] if item["state"] == "active"), None)
    normalized_source = None
    source_item = None
    if source_plan is not None:
        normalized_source, source_item = _resolve_terminal_stop_source(paths, state, source_plan)
    ts = now or iso_now()
    state["updated_at"] = ts
    state["last_stop"] = {
        "at": ts,
        "reason": reason,
        "plan": active_item["plan"] if active_item else None,
        "order": active_item["order"] if active_item else None,
        "scope": "terminal_tail"
        if source_item is not None
        else ("current_active" if active_item else "none"),
        **(
            {
                "stop_source_plan": normalized_source,
                "stop_source_order": source_item["order"],
                "stop_phase": "terminal_docs_closeout",
            }
            if source_item is not None
            else {}
        ),
    }
    audit_fields = {
        "reason": reason,
        "plan": active_item["plan"] if active_item else None,
        "order": active_item["order"] if active_item else None,
    }
    if source_item is not None:
        audit_fields.update(
            {
                "stop_source_plan": normalized_source,
                "stop_source_order": source_item["order"],
                "stop_phase": "terminal_docs_closeout",
            }
        )
    _commit_transaction(
        paths,
        operation="stop",
        after_state=state,
        audit_rows=[
            _audit_row(
                "stop",
                at=ts,
                **audit_fields,
            )
        ],
    )
    return queue_snapshot(state, paths)


@_exclusive_operation("planpath-override")
def mark_planpath_override(paths: QueuePaths, plan: str, reason: str | None = None) -> dict[str, Any]:
    state = load_state(paths)
    if state is None:
        raise QueueError(f"Queue is not initialized: {paths.state_path.relative_to(paths.root).as_posix()}")
    rel_plan = project_relative_path(paths.root, plan)
    ts = iso_now()
    audit_rows: list[dict[str, Any]] = []
    if reason == "queue_resume_parent" and rel_plan == pending_parent_resume_plan(state):
        state["parent_resume_pending_at"] = None
        state["parent_resumed_at"] = ts
        transition = normalized_last_transition(state)
        transition.update(
            {
                "kind": "parent_resumed",
                "at": ts,
                "parent_plan": rel_plan,
                "resume_parent_plan": None,
                "queue_complete": True,
            }
        )
        state["last_transition"] = transition
        audit_rows.append(_audit_row("resume_parent", at=ts, plan=rel_plan, reason=reason))
    state["last_stop"] = None
    state["last_planpath_override"] = {
        "at": ts,
        "plan": rel_plan,
        "reason": reason or "queue_activation",
    }
    state["updated_at"] = ts
    audit_rows.append(
        _audit_row(
            "planpath_override",
            at=ts,
            plan=rel_plan,
            reason=reason or "queue_activation",
        )
    )
    _commit_transaction(
        paths,
        operation="planpath-override",
        after_state=state,
        audit_rows=audit_rows,
    )
    return queue_snapshot(state, paths)


def render_snapshot(snapshot: dict[str, Any]) -> str:
    if not snapshot["exists"]:
        lines = [f"queue: empty ({snapshot['state_path']} is missing)"]
        for receipt in snapshot.get("skipped_incompatible") or []:
            lines.append(
                " skipped_incompatible="
                f"{receipt.get('plan')}"
                f" phase={receipt.get('skip_phase')}"
                f" required={receipt.get('required_manager_mode')}"
                f" actual={receipt.get('actual_manager_mode')}"
                f" state={receipt.get('manager_mode_state')}"
                f" reason={receipt.get('manager_mode_reason')}"
            )
        return "\n".join(lines)
    current_plan = snapshot.get("effective_plan") or "none"
    current_phase = snapshot.get("effective_phase") or "empty"
    lines = [
        "queue:"
        f" mode={snapshot['mode']}"
        f" items={len(snapshot['items'])}"
        f" active={snapshot.get('active_order') or 'none'}"
        f" pending={snapshot.get('pending_count', 0)}"
        f" done={snapshot.get('done_count', 0)}"
        f" superseded={snapshot.get('superseded_count', 0)}"
        f" non_executable={snapshot.get('closed_non_executable_count', 0)}"
        f" skipped_manager_mode={snapshot.get('skipped_manager_mode_count', 0)}"
        f" resume_parent={snapshot['resume_parent']}"
        f" resume_target={snapshot.get('resume_parent_plan') or 'none'}"
        f" cursor={snapshot['cursor']}",
        f" current={current_plan} ({current_phase})",
    ]
    if (
        "appended" in snapshot
        or "skipped_duplicates" in snapshot
        or "skipped_incompatible" in snapshot
        or "rejected" in snapshot
    ):
        appended = snapshot.get("appended") or []
        skipped = snapshot.get("skipped_duplicates") or []
        skipped_incompatible = snapshot.get("skipped_incompatible") or []
        rejected = snapshot.get("rejected") or []
        lines.append(
            " mutation_result="
            f"appended={len(appended)}"
            f" skipped_duplicates={len(skipped)}"
            f" skipped_incompatible={len(skipped_incompatible)}"
            f" rejected={len(rejected)}"
        )
        if appended:
            lines.append(" appended=" + "|".join(str(plan) for plan in appended))
        if skipped:
            lines.append(" skipped_duplicates=" + "|".join(str(plan) for plan in skipped))
        for receipt in skipped_incompatible:
            lines.append(
                " skipped_incompatible="
                f"{receipt.get('plan')}"
                f" phase={receipt.get('skip_phase')}"
                f" required={receipt.get('required_manager_mode')}"
                f" actual={receipt.get('actual_manager_mode')}"
                f" state={receipt.get('manager_mode_state')}"
                f" reason={receipt.get('manager_mode_reason')}"
            )
    runtime_payload = snapshot.get("effective_runtime") or {}
    if runtime_payload:
        lines.append(
            " runtime_class="
            f"{runtime_payload.get('runtime_class') or 'unknown'}"
            f" status={runtime_payload.get('status_value') or 'n/a'}"
            f" closeout={runtime_payload.get('queue_closeout_kind') or 'n/a'}"
        )
        lines.append(f" runtime_reason={runtime_payload.get('queue_closeout_reason') or 'n/a'}")
        if runtime_payload.get("small_model_readiness_state") not in {None, "not_applicable"}:
            findings = runtime_payload.get("small_model_readiness_findings") or []
            lines.append(
                " small_model_readiness="
                f"{runtime_payload.get('small_model_readiness_state')}"
                f" ready={runtime_payload.get('small_model_ready_child')}"
                f" findings={len(findings)}"
            )
    active_item = next((item for item in snapshot.get("items", []) if item.get("state") == "active"), None)
    if active_item and active_item.get("small_model_readiness_state") not in {None, "not_applicable"}:
        findings = active_item.get("small_model_readiness_findings") or []
        lines.append(
            " active_child_readiness="
            f"{active_item.get('small_model_readiness_state')}"
            f" ready={active_item.get('small_model_ready_child')}"
            f" findings={len(findings)}"
        )
        if findings:
            first_finding = findings[0]
            lines.append(
                " active_child_readiness_first="
                f"{first_finding.get('child_path')}:{first_finding.get('field')}:"
                f"{first_finding.get('severity')}:{first_finding.get('finding_kind')}"
            )
    queue_context = snapshot.get("queue_runtime_context") or {}
    if queue_context.get("queue_mode_active") or queue_context.get("history_available"):
        loop_text = "unknown"
        repeated_text = "unknown"
        max_iter_text = "unknown"
        if queue_context.get("loop_detected") is True:
            loop_text = "yes"
        elif queue_context.get("loop_detected") is False:
            loop_text = "no"
        if queue_context.get("repeated_blocker_detected") is True:
            repeated_text = "yes"
        elif queue_context.get("repeated_blocker_detected") is False:
            repeated_text = "no"
        if queue_context.get("max_iterations_reached") is True:
            max_iter_text = "yes"
        elif queue_context.get("max_iterations_reached") is False:
            max_iter_text = "no"
        lines.append(
            " queue_context="
            f"plan={queue_context.get('plan_ref') or 'none'}"
            f" loop={loop_text}"
            f" repeated_blocker={repeated_text}"
            f" max_iterations={max_iter_text}"
            f" stop_scope={queue_context.get('latest_stop_reason_scope') or 'none'}"
            f" latest_stop={queue_context.get('latest_stop_reason') or 'none'}"
        )
        if queue_context.get("latest_stop_item_ref"):
            lines.append(f" latest_stop_item={queue_context.get('latest_stop_item_ref')}")
        if queue_context.get("historical_stop_reason"):
            lines.append(
                f" historical_stop={queue_context.get('historical_stop_reason')} @ "
                f"{queue_context.get('historical_stop_at')}"
                f" (item={queue_context.get('historical_stop_item_ref') or 'none'})"
            )
        if queue_context.get("terminal_tail_stop_reason"):
            lines.append(
                f" terminal_tail_stop={queue_context.get('terminal_tail_stop_reason')} @ "
                f"{queue_context.get('terminal_tail_stop_at')}"
                f" (source={queue_context.get('terminal_tail_stop_source_item_ref') or 'none'}"
                f" active={queue_context.get('terminal_tail_stop_active_item_ref') or 'none'})"
            )
    if snapshot.get("next_pending_plan"):
        lines.append(f" next_pending={snapshot['next_pending_plan']}")
    last_stop = snapshot.get("last_stop") or {}
    if last_stop:
        lines.append(
            f" last_stop={last_stop.get('reason')} @ {last_stop.get('at')}"
            f" (plan={last_stop.get('plan') or 'none'})"
        )
    last_transition = snapshot.get("last_transition") or {}
    if last_transition:
        transition_summary = (
            f" last_transition={last_transition.get('kind')} @ {last_transition.get('at')}"
            f" finalized={last_transition.get('finalized_plan') or 'none'}"
            f" status={last_transition.get('final_status') or 'n/a'}"
        )
        if last_transition.get("runtime_class"):
            transition_summary += f" runtime_class={last_transition.get('runtime_class')}"
        if last_transition.get("closeout_kind"):
            transition_summary += f" closeout={last_transition.get('closeout_kind')}"
        next_plan = last_transition.get("next_plan")
        resume_parent_plan = last_transition.get("resume_parent_plan")
        if next_plan:
            transition_summary += f" -> next={next_plan}"
        elif resume_parent_plan:
            transition_summary += f" -> resume_parent={resume_parent_plan}"
        elif last_transition.get("activation_blocker"):
            transition_summary += (
                f" -> activation_blocker={last_transition.get('activation_blocker')}"
            )
        elif last_transition.get("queue_complete"):
            transition_summary += " -> queue_complete=yes"
        lines.append(transition_summary)
    last_override = snapshot.get("last_planpath_override") or {}
    if last_override:
        lines.append(
            f" last_planpath_override={last_override.get('plan')} @ {last_override.get('at')}"
            f" reason={last_override.get('reason')}"
        )
    for item in snapshot["items"]:
        item_line = f"{item['order']:02d} {item['state']:<20} {item['source']:<20} {item['plan']}"
        if item.get("state") == SKIPPED_MANAGER_MODE_STATE:
            item_line += (
                f" skip_phase={item.get('skip_phase')}"
                f" manager_mode_skip_id={item.get('manager_mode_skip_id')}"
                f" required_manager_mode={item.get('required_manager_mode')}"
                f" actual_manager_mode={item.get('actual_manager_mode')}"
                f" manager_mode_reason={item.get('manager_mode_reason')}"
            )
        if item.get("queue_activation_warning"):
            item_line += f" queue_activation_warning={item['queue_activation_warning']}"
        lines.append(item_line)
    return "\n".join(lines)


def render_history_report(report: dict[str, Any]) -> str:
    lines = [
        "queue_history:"
        f" log={report['log_path']}"
        f" entries={report['total_entries']}"
        f" shown={report['shown_entries']}"
        f" active={report.get('active_plan') or 'none'}"
        f" read_only={'yes' if report.get('read_only') else 'no'}",
    ]
    if not report.get("log_exists"):
        lines.append(" no_log_entries")
        return "\n".join(lines)
    for entry in report.get("entries", []):
        details = [
            f"#{entry.get('index')}",
            str(entry.get("at") or "unknown"),
            f"event={entry.get('event') or 'unknown'}",
        ]
        if entry.get("plan"):
            details.append(f"plan={entry['plan']}")
        if entry.get("order"):
            details.append(f"order={entry['order']}")
        if entry.get("reason"):
            details.append(f"reason={entry['reason']}")
        if entry.get("event") == "skip_manager_mode":
            details.extend(
                [
                    f"skip_phase={entry.get('skip_phase') or 'unknown'}",
                    f"manager_mode_skip_id={entry.get('manager_mode_skip_id') or 'unknown'}",
                    f"required_manager_mode={entry.get('required_manager_mode') or 'unknown'}",
                    f"actual_manager_mode={entry.get('actual_manager_mode') or 'unknown'}",
                    f"manager_mode_state={entry.get('manager_mode_state') or 'unknown'}",
                    f"manager_mode_reason={entry.get('manager_mode_reason') or 'unknown'}",
                ]
            )
        if entry.get("transaction_id"):
            details.append(
                "transaction="
                f"{entry['transaction_id']}:{entry.get('transaction_seq') or '?'}"
                f"/{entry.get('transaction_size') or '?'}"
            )
        if entry.get("event") == "stop":
            details.append(f"stop_scope={entry.get('stop_scope') or 'unknown'}")
            details.append(f"stop_item={entry.get('stop_item_ref') or 'none'}")
            if entry.get("stop_scope") == "terminal_tail":
                details.append(f"active_stop_item={entry.get('active_stop_item_ref') or 'none'}")
                details.append(f"stop_source_item={entry.get('stop_source_item_ref') or 'none'}")
                details.append(f"stop_phase={entry.get('stop_phase') or 'unknown'}")
        lines.append(" ".join(details))
    return "\n".join(lines)


def render_recovery(snapshot: dict[str, Any]) -> str:
    return (
        "recover:"
        f" classification={snapshot['classification']}"
        f" result={snapshot['result']}"
        f" mutation_performed={'yes' if snapshot['mutation_performed'] else 'no'}"
        f" transaction_id={snapshot.get('transaction_id') or 'none'}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="plan_queue",
        description="Manage repo-local plan queue state for Manager collab queue mode.",
    )
    parser.add_argument(
        "--project-root",
        help="Repo root (defaults to the nearest ancestor with .git from the current working directory).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    set_parser = subparsers.add_parser("set", help="Create/replace queue state")
    set_parser.add_argument("plans", nargs="*", help="Explicit plan paths for manual queue mode")
    set_group = set_parser.add_mutually_exclusive_group()
    set_group.add_argument("--status", nargs="+", help="Build queue from all plans matching the given status values")
    set_group.add_argument("--from-umbrella", help="Import child plans from an umbrella/master-plan")
    set_parser.add_argument("--resume-parent", choices=sorted(VALID_RESUME_PARENT), help="Override resume_parent policy")
    set_parser.add_argument(
        "--for-manager-mode",
        required=True,
        choices=plan_status_oracle.ACTUAL_MANAGER_MODES,
        help="Concrete Manager mode used to filter collection candidates",
    )
    set_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON result")

    show_parser = subparsers.add_parser("show", help="Show current queue state")
    show_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON result")

    history_parser = subparsers.add_parser("history", help="Show read-only queue log history")
    history_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON result")
    history_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Number of newest log rows to show (<=0 means all rows)",
    )

    recover_parser = subparsers.add_parser(
        "recover",
        help="Recover an interrupted queue transaction or required legacy repair",
    )
    recover_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON result")

    clear_parser = subparsers.add_parser("clear", help="Clear queue state")
    clear_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON result")

    append_parser = subparsers.add_parser("append", help="Append explicit plan paths to the queue tail")
    append_parser.add_argument("plans", nargs="+", help="Explicit repo-local docs/plans/*.md paths to append")
    append_parser.add_argument(
        "--for-manager-mode",
        required=True,
        choices=plan_status_oracle.ACTUAL_MANAGER_MODES,
        help="Concrete Manager mode used to filter appended candidates",
    )
    append_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON result")

    next_parser = subparsers.add_parser("next", help="Ensure the current/next queue item is active")
    next_parser.add_argument(
        "--manager-mode",
        required=True,
        choices=plan_status_oracle.ACTUAL_MANAGER_MODES,
        help="Concrete Manager mode used before activating or reusing an item",
    )
    next_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON result")

    advance_parser = subparsers.add_parser("advance", help="Advance the queue after a terminal plan status")
    advance_parser.add_argument("--final-status", required=True, choices=["Done", "Superseded"], help="Terminal plan status")
    advance_parser.add_argument(
        "--manager-mode",
        required=True,
        choices=plan_status_oracle.ACTUAL_MANAGER_MODES,
        help="Concrete Manager mode used before activating a transition candidate",
    )
    advance_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON result")

    closeout_parser = subparsers.add_parser(
        "closeout",
        help="Advance the queue when the active item is terminal or repo-backed non-executable",
    )
    closeout_parser.add_argument(
        "--manager-mode",
        required=True,
        choices=plan_status_oracle.ACTUAL_MANAGER_MODES,
        help="Concrete Manager mode required before closeout activates a next/resumed plan",
    )
    closeout_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON result")

    small_slice_parser = subparsers.add_parser(
        "small-slice",
        help="Classify whether a plan is eligible for reduced same-session censors",
    )
    small_slice_parser.add_argument("plan", help="Plan path to classify")
    small_slice_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON result")

    stop_parser = subparsers.add_parser("stop", help="Log a non-terminal queue stop without changing the active item")
    stop_parser.add_argument("--reason", required=True, help="Bounded stop reason for the append-only queue log")
    stop_parser.add_argument(
        "--source-plan",
        help="Terminal plan whose docs-closeout tail produced this stop",
    )
    stop_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON result")

    override_parser = subparsers.add_parser("planpath-override", help="Record a queue-driven .planveyor.planpath change")
    override_parser.add_argument("--plan", required=True, help="Plan path written into .planveyor.planpath")
    override_parser.add_argument("--reason", default="queue_activation", help="Reason recorded in the queue log")
    override_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON result")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        # Capture once before any queue state, history, fallback vocabulary, or
        # lock-file access.  ``queue_lock`` repeats validation only.
        requested_root = Path(args.project_root) if args.project_root else None
        context = resolve_top_level_context(requested_root)
        paths = queue_paths(context.project_root, context=context)
        if args.command == "set":
            snapshot = set_queue(
                paths,
                plans=args.plans,
                statuses=args.status,
                umbrella=args.from_umbrella,
                resume_parent=args.resume_parent,
                manager_mode=args.for_manager_mode,
            )
        elif args.command == "show":
            snapshot = show_queue(paths)
        elif args.command == "history":
            snapshot = queue_history_report(paths, limit=args.limit)
        elif args.command == "recover":
            snapshot = recover_queue(paths)
        elif args.command == "clear":
            snapshot = clear_queue(paths)
        elif args.command == "append":
            snapshot = append_queue(
                paths,
                args.plans,
                manager_mode=args.for_manager_mode,
            )
        elif args.command == "next":
            snapshot = activate_next(paths, manager_mode=args.manager_mode)
        elif args.command == "advance":
            snapshot = advance_queue(
                paths,
                args.final_status,
                manager_mode=args.manager_mode,
            )
        elif args.command == "closeout":
            snapshot = closeout_queue(paths, manager_mode=args.manager_mode)
        elif args.command == "small-slice":
            snapshot = small_slice_payload(paths.root, args.plan, context=context)
        elif args.command == "stop":
            snapshot = stop_queue(paths, args.reason, source_plan=args.source_plan)
        elif args.command == "planpath-override":
            snapshot = mark_planpath_override(paths, args.plan, args.reason)
        else:
            raise AssertionError(f"Unhandled command: {args.command}")
    except QueueError as exc:
        if getattr(args, "json", False) and exc.payload is not None:
            sys.stdout.write(json.dumps(exc.payload, ensure_ascii=False, sort_keys=True) + "\n")
            return 1
        print(str(exc), file=sys.stderr)
        return 1
    except ContractAuthorityError as exc:
        print(f"contract_authority_preflight_failed:{exc.reason_code}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if getattr(args, "json", False):
        sys.stdout.write(json.dumps(snapshot, ensure_ascii=False, sort_keys=True) + "\n")
    elif args.command == "small-slice":
        sys.stdout.write(render_small_slice(snapshot) + "\n")
    elif args.command == "history":
        sys.stdout.write(render_history_report(snapshot) + "\n")
    elif args.command == "recover":
        sys.stdout.write(render_recovery(snapshot) + "\n")
    else:
        sys.stdout.write(render_snapshot(snapshot) + "\n")
    return 1 if args.command == "recover" and snapshot.get("result") == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())

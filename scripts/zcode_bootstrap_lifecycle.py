#!/usr/bin/env python3
"""Fail-closed cooperative bootstrap lineage for the ZCode Manager overlay.

This helper stores ordering evidence, not authentication or process identity.
The current ZCode Manager is its cooperative caller; the helper makes one
exact project-root carrier authoritative for an explicit team epoch and never
discovers or revives a carrier from disk. The historical CLI spelling
``tooling_root`` means the Planveyor runtime root; it may equal ``project_root``
for a standalone, non-Git product invocation.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import os
import re
import secrets
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterator, Mapping

try:  # Supported ZCode hosts are POSIX systems.
    import fcntl
except ImportError:  # pragma: no cover - defensive for unsupported hosts.
    fcntl = None


SCHEMA_VERSION = "zcode_bootstrap_lifecycle.v1"
MAX_CARRIER_BYTES = 64 * 1024
MAX_CONTRACT_READS = 16
REQUIRED_ZCODE_TOOLING_CONTRACT_PATHS = (
    ".zcode/commands/manager-init.md",
    ".zcode/agents/planveyor-role-agent.md",
    "docs/tools/prompts/zcode/manager_pipeline.md",
)
VALID_LANES = frozenset(
    {
        "architect",
        "planner",
        "coder",
        "reviewer_code_risk",
        "reviewer_code_contracts",
    }
)
VALID_CONTRACT_ROOT_CLASSES = frozenset({"project", "tooling"})
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_NONCE_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class LifecycleError(RuntimeError):
    """A deterministic fail-closed lifecycle error."""

    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


def _error(reason_code: str, message: str) -> LifecycleError:
    return LifecycleError(reason_code, message)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _require_exact_keys(value: Mapping[str, Any], keys: set[str], field: str) -> None:
    if set(value) != keys:
        raise _error("malformed_state", f"{field} has unexpected keys")


def _require_token(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _TOKEN_RE.fullmatch(value):
        raise _error("invalid_identity", f"{field} must be a canonical token")
    return value


def _canonical_root(value: str | Path, field: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise _error("invalid_root", f"{field} must be absolute")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise _error("invalid_root", f"{field} cannot be resolved") from exc
    if not resolved.is_dir() or path != resolved:
        raise _error("invalid_root", f"{field} must be an existing canonical directory")
    return resolved


def _optional_plan_path(value: str | Path | None, project_root: Path) -> None:
    if value is None:
        return
    path = Path(value)
    if not path.is_absolute():
        raise _error("invalid_plan_path", "plan_path must be absolute")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise _error("invalid_plan_path", "plan_path cannot be resolved") from exc
    if path != resolved or not resolved.is_file():
        raise _error("invalid_plan_path", "plan_path must be a canonical regular file")
    try:
        resolved.relative_to(project_root)
    except ValueError as exc:
        raise _error("cross_root", "plan_path must resolve under project_root") from exc


def _path_under_root(value: Any, root: Path, field: str, *, error_code: str) -> Path:
    if not isinstance(value, str):
        raise _error(error_code, f"{field} must be a string")
    path = Path(value)
    if not path.is_absolute():
        raise _error(error_code, f"{field} must be absolute")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise _error(error_code, f"{field} cannot be resolved") from exc
    if path != resolved or not resolved.is_file():
        raise _error(error_code, f"{field} must be a canonical regular file")
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise _error("cross_root", f"{field} must resolve under its declared root class") from exc
    return resolved


def _carrier_path(project_root: Path, team_epoch: str) -> Path:
    _require_token(team_epoch, "team_epoch")
    return project_root / f".planveyor.zcode.bootstrap.{team_epoch}.json"


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise _error("malformed_state", "duplicate JSON key")
        output[key] = value
    return output


def _strict_json_loads(raw: bytes | str, *, field: str) -> Any:
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise _error("malformed_state", f"{field} is not UTF-8") from exc
    try:
        return json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda _constant: (_ for _ in ()).throw(
                _error("malformed_state", f"{field} contains a non-finite JSON value")
            ),
        )
    except LifecycleError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise _error("malformed_state", f"{field} is not strict JSON") from exc


def _validate_json_value(value: Any, field: str) -> None:
    if value is None or isinstance(value, (str, bool)) or _is_int(value):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise _error("malformed_acknowledgement", f"{field} contains a non-finite number")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, f"{field}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise _error("malformed_acknowledgement", f"{field} has a non-string key")
            _validate_json_value(item, f"{field}.{key}")
        return
    raise _error("malformed_acknowledgement", f"{field} is not JSON-compatible")


def _normalise_acknowledgement_json(acknowledgement: Mapping[str, Any] | str) -> dict[str, Any]:
    if isinstance(acknowledgement, str):
        value = _strict_json_loads(acknowledgement, field="acknowledgement")
    elif isinstance(acknowledgement, Mapping):
        value = dict(acknowledgement)
    else:
        raise _error("malformed_acknowledgement", "acknowledgement must be a JSON object")
    if not isinstance(value, dict):
        raise _error("malformed_acknowledgement", "acknowledgement must be a JSON object")
    _validate_json_value(value, "acknowledgement")
    if "acknowledgement_digest" in value:
        raise _error("manager_digest_forbidden", "Manager-supplied acknowledgement_digest is forbidden")
    _require_exact_keys(
        value,
        {"team_epoch", "role_lane", "role_generation", "init_nonce", "read_contracts"},
        "acknowledgement",
    )
    _require_token(value["team_epoch"], "acknowledgement.team_epoch")
    if value["role_lane"] not in VALID_LANES:
        raise _error("malformed_acknowledgement", "acknowledgement.role_lane is invalid")
    if not _is_int(value["role_generation"]) or value["role_generation"] < 1:
        raise _error("malformed_acknowledgement", "acknowledgement.role_generation is invalid")
    if not isinstance(value["init_nonce"], str) or not _NONCE_RE.fullmatch(value["init_nonce"]):
        raise _error("malformed_acknowledgement", "acknowledgement.init_nonce is invalid")
    if not isinstance(value["read_contracts"], list) or not value["read_contracts"]:
        raise _error("malformed_acknowledgement", "acknowledgement.read_contracts must be non-empty")
    if len(value["read_contracts"]) > MAX_CONTRACT_READS:
        raise _error("malformed_acknowledgement", "acknowledgement.read_contracts is too large")
    return value


def acknowledgement_digest(acknowledgement: Mapping[str, Any] | str) -> str:
    """Return the helper-owned digest after strict acknowledgement validation."""

    value = _normalise_acknowledgement_json(acknowledgement)
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _normalise_contract_reads_input(value: Any, *, field: str) -> list[Any]:
    if isinstance(value, str):
        value = _strict_json_loads(value, field=field)
    if not isinstance(value, list) or not value:
        raise _error("malformed_contract_reads", f"{field} must be a non-empty JSON array")
    if len(value) > MAX_CONTRACT_READS:
        raise _error("malformed_contract_reads", f"{field} is too large")
    return value


def _canonical_contract_manifest(
    contract_reads: Any,
    *,
    project_root: Path,
    tooling_root: Path,
    field: str,
    hash_mismatch_reason: str,
) -> list[dict[str, str]]:
    """Validate actual contract files and return a root-classed canonical manifest."""

    manifest: list[dict[str, str]] = []
    seen_contracts: set[tuple[str, str]] = set()
    for index, contract in enumerate(_normalise_contract_reads_input(contract_reads, field=field)):
        item_field = f"{field}[{index}]"
        if not isinstance(contract, dict) or set(contract) != {"root_class", "path", "sha256"}:
            raise _error("malformed_contract_reads", f"{item_field} has unexpected keys")
        root_class = contract["root_class"]
        if root_class not in VALID_CONTRACT_ROOT_CLASSES:
            raise _error("malformed_contract_reads", f"{item_field}.root_class is invalid")
        root = project_root if root_class == "project" else tooling_root
        path = _path_under_root(
            contract["path"],
            root,
            f"{item_field}.path",
            error_code="malformed_contract_reads",
        )
        contract_hash = contract["sha256"]
        if not isinstance(contract_hash, str) or not _SHA256_RE.fullmatch(contract_hash):
            raise _error("malformed_contract_reads", f"{item_field}.sha256 is invalid")
        canonical_key = (root_class, str(path))
        if canonical_key in seen_contracts:
            raise _error("malformed_contract_reads", f"{field} contains a duplicate contract")
        seen_contracts.add(canonical_key)
        if hashlib.sha256(path.read_bytes()).hexdigest() != contract_hash:
            raise _error(hash_mismatch_reason, f"{item_field}.sha256 does not match the selected contract")
        manifest.append(
            {
                "root_class": root_class,
                "path": str(path),
                "sha256": contract_hash,
            }
        )
    return sorted(manifest, key=lambda item: (item["root_class"], item["path"]))


def _assert_required_zcode_tooling_contracts(
    manifest: list[dict[str, str]], *, tooling_root: Path, field: str
) -> None:
    """Require the three public ZCode bodies in every host-dispatch manifest.

    The names are stable contract locations, while their hashes are read from
    the live files for each reservation. They are lifecycle inputs and are not
    part of a runtime code-pin closure.
    """

    declared = {(item["root_class"], item["path"]) for item in manifest}
    missing: list[str] = []
    for relative_path in REQUIRED_ZCODE_TOOLING_CONTRACT_PATHS:
        path = _path_under_root(
            str(tooling_root / relative_path),
            tooling_root,
            f"{field}.{relative_path}",
            error_code="zcode_contract_assets_unavailable",
        )
        if ("tooling", str(path)) not in declared:
            missing.append(relative_path)
    if missing:
        raise _error(
            "zcode_contract_assets_missing",
            f"{field} must include the public ZCode contract assets: {', '.join(missing)}",
        )


def _manifest_digest(manifest: list[dict[str, str]]) -> str:
    return hashlib.sha256(_canonical_json_bytes(manifest)).hexdigest()


def _validate_stored_contract_manifest(value: Any, field: str) -> list[dict[str, str]]:
    """Validate the durable manifest shape without re-reading mutable files."""

    if not isinstance(value, list) or not value or len(value) > MAX_CONTRACT_READS:
        raise _error("malformed_state", f"{field} is invalid")
    manifest: list[dict[str, str]] = []
    seen_contracts: set[tuple[str, str]] = set()
    for index, contract in enumerate(value):
        item_field = f"{field}[{index}]"
        if not isinstance(contract, dict) or set(contract) != {"root_class", "path", "sha256"}:
            raise _error("malformed_state", f"{item_field} has unexpected keys")
        root_class = contract["root_class"]
        path = contract["path"]
        contract_hash = contract["sha256"]
        if root_class not in VALID_CONTRACT_ROOT_CLASSES:
            raise _error("malformed_state", f"{item_field}.root_class is invalid")
        if not isinstance(path, str) or not Path(path).is_absolute():
            raise _error("malformed_state", f"{item_field}.path is invalid")
        if not isinstance(contract_hash, str) or not _SHA256_RE.fullmatch(contract_hash):
            raise _error("malformed_state", f"{item_field}.sha256 is invalid")
        key = (root_class, path)
        if key in seen_contracts:
            raise _error("malformed_state", f"{field} contains a duplicate contract")
        seen_contracts.add(key)
        manifest.append({"root_class": root_class, "path": path, "sha256": contract_hash})
    if manifest != sorted(manifest, key=lambda item: (item["root_class"], item["path"])):
        raise _error("malformed_state", f"{field} is not canonical")
    return manifest


def _validate_acknowledgement(
    acknowledgement: Mapping[str, Any] | str,
    *,
    project_root: Path,
    tooling_root: Path,
    team_epoch: str,
    role_lane: str,
    role_generation: int,
    init_nonce: str,
    expected_contract_reads: Any,
) -> tuple[dict[str, Any], str]:
    value = _normalise_acknowledgement_json(acknowledgement)
    if (
        value["team_epoch"] != team_epoch
        or value["role_lane"] != role_lane
        or value["role_generation"] != role_generation
        or value["init_nonce"] != init_nonce
    ):
        raise _error("acknowledgement_mismatch", "acknowledgement does not match the pending identity")
    actual_contract_reads = _canonical_contract_manifest(
        value["read_contracts"],
        project_root=project_root,
        tooling_root=tooling_root,
        field="acknowledgement.read_contracts",
        hash_mismatch_reason="acknowledgement_mismatch",
    )
    _assert_required_zcode_tooling_contracts(
        actual_contract_reads,
        tooling_root=tooling_root,
        field="acknowledgement.read_contracts",
    )
    expected_manifest = _validate_stored_contract_manifest(
        expected_contract_reads,
        "carrier expected_contract_reads",
    )
    if actual_contract_reads != expected_manifest:
        raise _error(
            "contract_reads_mismatch",
            "acknowledgement.read_contracts must exactly match the reserved contract manifest",
        )
    value["read_contracts"] = actual_contract_reads
    return value, hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _validate_attempt(value: Any, field: str, high_water: int) -> None:
    if not isinstance(value, dict):
        raise _error("malformed_state", f"{field} must be an object")
    state = value.get("attempt_state")
    base_keys = {
        "attempt_state",
        "role_generation",
        "init_nonce",
        "nonce_state",
        "expected_contract_reads",
        "expected_contract_reads_digest",
    }
    if state == "current":
        _require_exact_keys(value, base_keys | {"agent_identity_audit", "acknowledgement_digest"}, field)
    elif state in {"pending", "abandoned"}:
        _require_exact_keys(value, base_keys, field)
    else:
        raise _error("malformed_state", f"{field}.attempt_state is invalid")
    generation = value.get("role_generation")
    if not _is_int(generation) or generation < 1 or generation != high_water:
        raise _error("malformed_state", f"{field}.role_generation is invalid")
    nonce = value.get("init_nonce")
    if not isinstance(nonce, str) or not _NONCE_RE.fullmatch(nonce):
        raise _error("malformed_state", f"{field}.init_nonce is invalid")
    required_nonce_state = "reserved" if state == "pending" else "consumed"
    if value.get("nonce_state") != required_nonce_state:
        raise _error("malformed_state", f"{field}.nonce_state is invalid")
    manifest = _validate_stored_contract_manifest(value.get("expected_contract_reads"), f"{field}.expected_contract_reads")
    expected_digest = value.get("expected_contract_reads_digest")
    if not isinstance(expected_digest, str) or not _SHA256_RE.fullmatch(expected_digest):
        raise _error("malformed_state", f"{field}.expected_contract_reads_digest is invalid")
    if _manifest_digest(manifest) != expected_digest:
        raise _error("malformed_state", f"{field}.expected_contract_reads_digest does not match the manifest")
    if state == "current":
        if not isinstance(value["agent_identity_audit"], str) or not value["agent_identity_audit"].strip():
            raise _error("malformed_state", f"{field}.agent_identity_audit is invalid")
        if not isinstance(value["acknowledgement_digest"], str) or not _SHA256_RE.fullmatch(
            value["acknowledgement_digest"]
        ):
            raise _error("malformed_state", f"{field}.acknowledgement_digest is invalid")


def _validate_record(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _error("malformed_state", "carrier root is not an object")
    _require_exact_keys(
        value,
        {
            "schema_version",
            "revision",
            "project_root",
            "tooling_root",
            "manager_session_identity",
            "team_epoch",
            "lanes",
        },
        "carrier",
    )
    if value["schema_version"] != SCHEMA_VERSION:
        raise _error("malformed_state", "carrier schema_version is invalid")
    if not _is_int(value["revision"]) or value["revision"] < 1:
        raise _error("malformed_state", "carrier revision is invalid")
    for field in ("project_root", "tooling_root"):
        if not isinstance(value[field], str) or not Path(value[field]).is_absolute():
            raise _error("malformed_state", f"carrier {field} is invalid")
    _require_token(value["manager_session_identity"], "carrier.manager_session_identity")
    _require_token(value["team_epoch"], "carrier.team_epoch")
    if not isinstance(value["lanes"], dict):
        raise _error("malformed_state", "carrier lanes is invalid")
    for lane_name, lane in value["lanes"].items():
        if lane_name not in VALID_LANES or not isinstance(lane, dict):
            raise _error("malformed_state", "carrier lane is invalid")
        _require_exact_keys(lane, {"generation_high_water", "attempt"}, f"carrier.lanes.{lane_name}")
        high_water = lane["generation_high_water"]
        if not _is_int(high_water) or high_water < 0:
            raise _error("malformed_state", "generation_high_water is invalid")
        if lane["attempt"] is not None:
            _validate_attempt(lane["attempt"], f"carrier.lanes.{lane_name}.attempt", high_water)
    return value


def _load_carrier(path: Path) -> dict[str, Any]:
    try:
        status = os.lstat(path)
    except FileNotFoundError as exc:
        raise _error("missing_state", "exact lifecycle carrier is missing") from exc
    if not stat.S_ISREG(status.st_mode):
        raise _error("malformed_state", "lifecycle carrier must be a regular file")
    if status.st_size > MAX_CARRIER_BYTES:
        raise _error("malformed_state", "lifecycle carrier exceeds its size limit")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise _error("malformed_state", "lifecycle carrier cannot be read") from exc
    if len(raw) > MAX_CARRIER_BYTES:
        raise _error("malformed_state", "lifecycle carrier exceeds its size limit")
    return _validate_record(_strict_json_loads(raw, field="lifecycle carrier"))


def _assert_record_identity(
    record: Mapping[str, Any],
    *,
    project_root: Path,
    tooling_root: Path,
    manager_session_identity: str,
    team_epoch: str,
) -> None:
    if (
        record["project_root"] != str(project_root)
        or record["tooling_root"] != str(tooling_root)
        or record["manager_session_identity"] != manager_session_identity
        or record["team_epoch"] != team_epoch
    ):
        raise _error("identity_mismatch", "lifecycle carrier does not match the exact invocation identity")
    # `_validate_record` already checks durable manifest shape and digest.
    # Live rehashing belongs to an exact admission readback so one stale lane
    # cannot prevent its explicit replacement or unrelated lane transitions.


def _assert_attempt_contracts_are_current(
    attempt: Mapping[str, Any],
    *,
    project_root: Path,
    tooling_root: Path,
    field: str,
) -> None:
    """Rehash one admission-relevant attempt without poisoning other lanes."""

    manifest = _canonical_contract_manifest(
        attempt["expected_contract_reads"],
        project_root=project_root,
        tooling_root=tooling_root,
        field=field,
        hash_mismatch_reason="malformed_state",
    )
    _assert_required_zcode_tooling_contracts(
        manifest,
        tooling_root=tooling_root,
        field=field,
    )
    if (
        manifest != attempt["expected_contract_reads"]
        or _manifest_digest(manifest) != attempt["expected_contract_reads_digest"]
    ):
        raise _error("malformed_state", "carrier contract manifest is not canonical")


def _new_record(
    *, project_root: Path, tooling_root: Path, manager_session_identity: str, team_epoch: str
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "revision": 1,
        "project_root": str(project_root),
        "tooling_root": str(tooling_root),
        "manager_session_identity": manager_session_identity,
        "team_epoch": team_epoch,
        "lanes": {},
    }


def _increment_revision(record: dict[str, Any]) -> None:
    record["revision"] += 1


@contextlib.contextmanager
def _write_lock(path: Path) -> Iterator[None]:
    if fcntl is None:  # pragma: no cover - supported runners are POSIX.
        raise _error("lock_unavailable", "POSIX advisory locks are required")
    lock_path = path.with_name(f"{path.name}.lock")
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write(path: Path, record: Mapping[str, Any]) -> None:
    data = _canonical_json_bytes(record)
    if len(data) > MAX_CARRIER_BYTES:
        raise _error("state_too_large", "lifecycle carrier would exceed its size limit")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        _fsync_directory(path.parent)
    except OSError as exc:
        raise _error("write_failed", "atomic lifecycle write failed") from exc
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _readback(
    record: Mapping[str, Any],
    *,
    role_lane: str | None = None,
    role_generation: int | None = None,
    init_nonce: str | None = None,
    expected_state: str | None = None,
) -> dict[str, Any]:
    output: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "revision": record["revision"],
        "project_root": record["project_root"],
        "tooling_root": record["tooling_root"],
        "manager_session_identity": record["manager_session_identity"],
        "team_epoch": record["team_epoch"],
    }
    if role_lane is None:
        output["verdict"] = "epoch_current"
        return output
    output.update(
        {
            "role_lane": role_lane,
            "role_generation": role_generation,
            "init_nonce": init_nonce,
        }
    )
    lane = record["lanes"].get(role_lane)
    attempt = lane.get("attempt") if isinstance(lane, dict) else None
    matches = (
        isinstance(attempt, dict)
        and attempt.get("role_generation") == role_generation
        and attempt.get("init_nonce") == init_nonce
    )
    if matches:
        output["attempt_state"] = attempt["attempt_state"]
        output["expected_contract_reads"] = attempt["expected_contract_reads"]
        output["expected_contract_reads_digest"] = attempt["expected_contract_reads_digest"]
        if attempt["attempt_state"] == "current":
            output["agent_identity_audit"] = attempt["agent_identity_audit"]
            output["acknowledgement_digest"] = attempt["acknowledgement_digest"]
    if matches and (expected_state is None or attempt["attempt_state"] == expected_state):
        output["verdict"] = attempt["attempt_state"]
    else:
        output["verdict"] = "zcode_bootstrap_lifecycle_not_current"
    return output


def _prepare_identity(
    *,
    project_root: str | Path,
    tooling_root: str | Path,
    manager_session_identity: str,
    team_epoch: str,
    plan_path: str | Path | None,
) -> tuple[Path, Path, str, str, Path]:
    canonical_project_root = _canonical_root(project_root, "project_root")
    canonical_tooling_root = _canonical_root(tooling_root, "tooling_root")
    _optional_plan_path(plan_path, canonical_project_root)
    session_identity = _require_token(manager_session_identity, "manager_session_identity")
    epoch = _require_token(team_epoch, "team_epoch")
    return (
        canonical_project_root,
        canonical_tooling_root,
        session_identity,
        epoch,
        _carrier_path(canonical_project_root, epoch),
    )


def init_epoch(
    *,
    project_root: str | Path,
    tooling_root: str | Path,
    manager_session_identity: str,
    team_epoch: str,
    plan_path: str | Path | None = None,
) -> dict[str, Any]:
    """Create one exact epoch or read the same valid session epoch unchanged."""

    project, tooling, session, epoch, carrier = _prepare_identity(
        project_root=project_root,
        tooling_root=tooling_root,
        manager_session_identity=manager_session_identity,
        team_epoch=team_epoch,
        plan_path=plan_path,
    )
    with _write_lock(carrier):
        if os.path.lexists(carrier):
            record = _load_carrier(carrier)
            _assert_record_identity(
                record,
                project_root=project,
                tooling_root=tooling,
                manager_session_identity=session,
                team_epoch=epoch,
            )
        else:
            record = _new_record(
                project_root=project,
                tooling_root=tooling,
                manager_session_identity=session,
                team_epoch=epoch,
            )
            _atomic_write(carrier, record)
    return _readback(record)


def reserve_agent(
    *,
    project_root: str | Path,
    tooling_root: str | Path,
    manager_session_identity: str,
    team_epoch: str,
    role_lane: str,
    contract_reads: Any,
    replace_current: bool = False,
    plan_path: str | Path | None = None,
) -> dict[str, Any]:
    """Consume a new generation and nonce before exactly one fresh Agent call."""

    if role_lane not in VALID_LANES:
        raise _error("invalid_lane", "role_lane is invalid")
    project, tooling, session, epoch, carrier = _prepare_identity(
        project_root=project_root,
        tooling_root=tooling_root,
        manager_session_identity=manager_session_identity,
        team_epoch=team_epoch,
        plan_path=plan_path,
    )
    expected_contract_reads = _canonical_contract_manifest(
        contract_reads,
        project_root=project,
        tooling_root=tooling,
        field="contract_reads",
        hash_mismatch_reason="contract_reads_mismatch",
    )
    _assert_required_zcode_tooling_contracts(
        expected_contract_reads,
        tooling_root=tooling,
        field="contract_reads",
    )
    expected_contract_reads_digest = _manifest_digest(expected_contract_reads)
    with _write_lock(carrier):
        record = _load_carrier(carrier)
        _assert_record_identity(
            record,
            project_root=project,
            tooling_root=tooling,
            manager_session_identity=session,
            team_epoch=epoch,
        )
        lane = record["lanes"].get(role_lane, {"generation_high_water": 0, "attempt": None})
        attempt = lane["attempt"]
        if isinstance(attempt, dict) and attempt["attempt_state"] == "pending":
            raise _error("pending_attempt_exists", "a pending attempt must be abandoned or promoted first")
        if isinstance(attempt, dict) and attempt["attempt_state"] == "current" and not replace_current:
            raise _error("current_attempt_exists", "reuse the live handle or explicitly replace a lost handle")
        generation = lane["generation_high_water"] + 1
        nonce = secrets.token_urlsafe(24)
        record["lanes"][role_lane] = {
            "generation_high_water": generation,
            "attempt": {
                "attempt_state": "pending",
                "role_generation": generation,
                "init_nonce": nonce,
                "nonce_state": "reserved",
                "expected_contract_reads": expected_contract_reads,
                "expected_contract_reads_digest": expected_contract_reads_digest,
            },
        }
        _increment_revision(record)
        _atomic_write(carrier, record)
    return _readback(
        record,
        role_lane=role_lane,
        role_generation=generation,
        init_nonce=nonce,
        expected_state="pending",
    )


def promote_ack(
    *,
    project_root: str | Path,
    tooling_root: str | Path,
    manager_session_identity: str,
    team_epoch: str,
    role_lane: str,
    role_generation: int,
    init_nonce: str,
    agent_identity_audit: str,
    acknowledgement: Mapping[str, Any] | str,
    plan_path: str | Path | None = None,
) -> dict[str, Any]:
    """Promote one matching pending attempt after a structured role acknowledgement."""

    if role_lane not in VALID_LANES or not _is_int(role_generation) or role_generation < 1:
        raise _error("invalid_identity", "role lane or generation is invalid")
    if not isinstance(init_nonce, str) or not _NONCE_RE.fullmatch(init_nonce):
        raise _error("invalid_identity", "init_nonce is invalid")
    if not isinstance(agent_identity_audit, str) or not agent_identity_audit.strip():
        raise _error("invalid_agent_id", "agent_identity_audit is invalid")
    project, tooling, session, epoch, carrier = _prepare_identity(
        project_root=project_root,
        tooling_root=tooling_root,
        manager_session_identity=manager_session_identity,
        team_epoch=team_epoch,
        plan_path=plan_path,
    )
    _normalise_acknowledgement_json(acknowledgement)
    with _write_lock(carrier):
        record = _load_carrier(carrier)
        _assert_record_identity(
            record,
            project_root=project,
            tooling_root=tooling,
            manager_session_identity=session,
            team_epoch=epoch,
        )
        lane = record["lanes"].get(role_lane)
        attempt = lane.get("attempt") if isinstance(lane, dict) else None
        if (
            not isinstance(attempt, dict)
            or attempt.get("attempt_state") != "pending"
            or attempt.get("role_generation") != role_generation
            or attempt.get("init_nonce") != init_nonce
        ):
            raise _error("pending_identity_mismatch", "only the exact pending attempt can be promoted")
        _acknowledgement, digest = _validate_acknowledgement(
            acknowledgement,
            project_root=project,
            tooling_root=tooling,
            team_epoch=epoch,
            role_lane=role_lane,
            role_generation=role_generation,
            init_nonce=init_nonce,
            expected_contract_reads=attempt["expected_contract_reads"],
        )
        del _acknowledgement  # The helper persists its digest, not Manager-provided text.
        lane["attempt"] = {
            "attempt_state": "current",
            "role_generation": role_generation,
            "init_nonce": init_nonce,
            "nonce_state": "consumed",
            "expected_contract_reads": attempt["expected_contract_reads"],
            "expected_contract_reads_digest": attempt["expected_contract_reads_digest"],
            "agent_identity_audit": agent_identity_audit,
            "acknowledgement_digest": digest,
        }
        _increment_revision(record)
        _atomic_write(carrier, record)
    return _readback(
        record,
        role_lane=role_lane,
        role_generation=role_generation,
        init_nonce=init_nonce,
        expected_state="current",
    )


def abandon_pending(
    *,
    project_root: str | Path,
    tooling_root: str | Path,
    manager_session_identity: str,
    team_epoch: str,
    role_lane: str,
    role_generation: int,
    init_nonce: str,
    plan_path: str | Path | None = None,
) -> dict[str, Any]:
    """Terminally consume a failed, ambiguous, or unacknowledged reservation."""

    if role_lane not in VALID_LANES or not _is_int(role_generation) or role_generation < 1:
        raise _error("invalid_identity", "role lane or generation is invalid")
    if not isinstance(init_nonce, str) or not _NONCE_RE.fullmatch(init_nonce):
        raise _error("invalid_identity", "init_nonce is invalid")
    project, tooling, session, epoch, carrier = _prepare_identity(
        project_root=project_root,
        tooling_root=tooling_root,
        manager_session_identity=manager_session_identity,
        team_epoch=team_epoch,
        plan_path=plan_path,
    )
    with _write_lock(carrier):
        record = _load_carrier(carrier)
        _assert_record_identity(
            record,
            project_root=project,
            tooling_root=tooling,
            manager_session_identity=session,
            team_epoch=epoch,
        )
        lane = record["lanes"].get(role_lane)
        attempt = lane.get("attempt") if isinstance(lane, dict) else None
        if (
            not isinstance(attempt, dict)
            or attempt.get("attempt_state") != "pending"
            or attempt.get("role_generation") != role_generation
            or attempt.get("init_nonce") != init_nonce
        ):
            raise _error("pending_identity_mismatch", "only the exact pending attempt can be abandoned")
        lane["attempt"] = {
            "attempt_state": "abandoned",
            "role_generation": role_generation,
            "init_nonce": init_nonce,
            "nonce_state": "consumed",
            "expected_contract_reads": attempt["expected_contract_reads"],
            "expected_contract_reads_digest": attempt["expected_contract_reads_digest"],
        }
        _increment_revision(record)
        _atomic_write(carrier, record)
    return _readback(
        record,
        role_lane=role_lane,
        role_generation=role_generation,
        init_nonce=init_nonce,
        expected_state="abandoned",
    )


def read_exact_epoch(
    *,
    project_root: str | Path,
    tooling_root: str | Path,
    manager_session_identity: str,
    team_epoch: str,
    role_lane: str | None = None,
    role_generation: int | None = None,
    init_nonce: str | None = None,
    expected_state: str | None = None,
    plan_path: str | Path | None = None,
) -> dict[str, Any]:
    """Read only the exact carrier; mismatched state yields a red verdict."""

    if role_lane is not None:
        if role_lane not in VALID_LANES:
            raise _error("invalid_lane", "role_lane is invalid")
        if not _is_int(role_generation) or role_generation < 1:
            raise _error("invalid_identity", "role_generation is invalid")
        if not isinstance(init_nonce, str) or not _NONCE_RE.fullmatch(init_nonce):
            raise _error("invalid_identity", "init_nonce is invalid")
    elif role_generation is not None or init_nonce is not None or expected_state is not None:
        raise _error("invalid_identity", "lane identity is incomplete")
    if expected_state not in {None, "pending", "current", "abandoned"}:
        raise _error("invalid_state", "expected_state is invalid")
    project, tooling, session, epoch, carrier = _prepare_identity(
        project_root=project_root,
        tooling_root=tooling_root,
        manager_session_identity=manager_session_identity,
        team_epoch=team_epoch,
        plan_path=plan_path,
    )
    record = _load_carrier(carrier)
    _assert_record_identity(
        record,
        project_root=project,
        tooling_root=tooling,
        manager_session_identity=session,
        team_epoch=epoch,
    )
    lane = record["lanes"].get(role_lane) if role_lane is not None else None
    attempt = lane.get("attempt") if isinstance(lane, dict) else None
    if (
        isinstance(attempt, dict)
        and attempt["attempt_state"] in {"pending", "current"}
        and attempt["role_generation"] == role_generation
        and attempt["init_nonce"] == init_nonce
    ):
        _assert_attempt_contracts_are_current(
            attempt,
            project_root=project,
            tooling_root=tooling,
            field=f"carrier.lanes.{role_lane}.expected_contract_reads",
        )
    return _readback(
        record,
        role_lane=role_lane,
        role_generation=role_generation,
        init_nonce=init_nonce,
        expected_state=expected_state,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)

    def add_identity(command: argparse.ArgumentParser) -> None:
        command.add_argument("--project-root", required=True)
        command.add_argument("--tooling-root", required=True)
        command.add_argument("--manager-session-identity", required=True)
        command.add_argument("--team-epoch", required=True)
        command.add_argument("--plan-path")

    init = subparsers.add_parser("init_epoch")
    add_identity(init)

    reserve = subparsers.add_parser("reserve_agent")
    add_identity(reserve)
    reserve.add_argument("--role-lane", required=True, choices=sorted(VALID_LANES))
    reserve.add_argument("--contract-reads-json", required=True)
    reserve.add_argument("--replace-current", action="store_true")

    promote = subparsers.add_parser("promote_ack")
    add_identity(promote)
    promote.add_argument("--role-lane", required=True, choices=sorted(VALID_LANES))
    promote.add_argument("--role-generation", required=True, type=int)
    promote.add_argument("--init-nonce", required=True)
    promote.add_argument("--agent-id", required=True)
    promote.add_argument("--ack-json", required=True)

    abandon = subparsers.add_parser("abandon_pending")
    add_identity(abandon)
    abandon.add_argument("--role-lane", required=True, choices=sorted(VALID_LANES))
    abandon.add_argument("--role-generation", required=True, type=int)
    abandon.add_argument("--init-nonce", required=True)

    read = subparsers.add_parser("read_exact_epoch")
    add_identity(read)
    read.add_argument("--role-lane", choices=sorted(VALID_LANES))
    read.add_argument("--role-generation", type=int)
    read.add_argument("--init-nonce")
    read.add_argument("--expected-state", choices=("pending", "current", "abandoned"))
    return parser


def _identity_kwargs(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "project_root": args.project_root,
        "tooling_root": args.tooling_root,
        "manager_session_identity": args.manager_session_identity,
        "team_epoch": args.team_epoch,
        "plan_path": args.plan_path,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        identity = _identity_kwargs(args)
        if args.operation == "init_epoch":
            output = init_epoch(**identity)
        elif args.operation == "reserve_agent":
            output = reserve_agent(
                **identity,
                role_lane=args.role_lane,
                contract_reads=args.contract_reads_json,
                replace_current=args.replace_current,
            )
        elif args.operation == "promote_ack":
            output = promote_ack(
                **identity,
                role_lane=args.role_lane,
                role_generation=args.role_generation,
                init_nonce=args.init_nonce,
                agent_identity_audit=args.agent_id,
                acknowledgement=args.ack_json,
            )
        elif args.operation == "abandon_pending":
            output = abandon_pending(
                **identity,
                role_lane=args.role_lane,
                role_generation=args.role_generation,
                init_nonce=args.init_nonce,
            )
        else:
            output = read_exact_epoch(
                **identity,
                role_lane=args.role_lane,
                role_generation=args.role_generation,
                init_nonce=args.init_nonce,
                expected_state=args.expected_state,
            )
            if output["verdict"] == "zcode_bootstrap_lifecycle_not_current":
                print(json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
                return 3
        print(json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return 0
    except LifecycleError as exc:
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "verdict": "zcode_bootstrap_lifecycle_not_current",
                    "reason_code": exc.reason_code,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Capture and verify one terminal docs-finalize ordinary-followup cycle.

The receipt written by this module is deliberately transient.  The durable
authority remains the lint-green row in ``docs/followups``; this helper only
proves which role created which no-follow regular file during one exact cycle.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import process_improvements_collect
import fs_object_identity


SCHEMA_VERSION = "followups_capture_receipt.v1"
IDENTITY_SCHEMA_VERSION = "followups_capture.semantic_closeout_identity.v1"
STAGING_SCHEMA_VERSION = "followups_staging_verification.v1"
PREFLIGHT_SCHEMA_VERSION = "followups_commit_preflight.v1"
COMMIT_RESULT_SCHEMA_VERSION = "followups_commit_exact_result.v1"
RECEIPT_NAME = "followups_capture_receipt.json"
FOLLOWUPS_INDEX_REFRESH_RECEIPT_NAME = "followups_index_refresh_receipt.json"
FOLLOWUPS_INDEX_REFRESH_RECEIPT_SCHEMA = "followups_index_refresh_receipt.v1"
FOLLOWUPS_INDEX_REFRESH_OWNER_ID = "followups_apply_index_refresh_v1"
FOLLOWUPS_INDEX_PATH = "docs/followups/index.md"
CAPTURE_COMPONENTS = (".tmp", "followups_capture")
REQUIRED_ROLES = ("Architect", "Coder", "Planner", "Reviewer")
UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
STATUS_RE = re.compile(r"^\s*\*\*Status:\*\*\s*(?P<value>.+?)\s*$")
PLAN_SCHEMA_VERSION_RE = re.compile(r"^\s*\*\*Schema version:\*\*\s*(?P<value>.+?)\s*$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
OID_RE = re.compile(r"^[0-9a-f]{40,64}$")
PI_DERIVED_SURFACE_PATHS = {
    process_improvements_collect.INDEX_PATH.as_posix(),
    process_improvements_collect.DEFERRED_PATH.as_posix(),
    process_improvements_collect.PROMOTION_PATH.as_posix(),
}
PI_CAPTURE_CONTINUATION_STATES = {"clean_noop", "materialized", "already_tracked"}
PI_FORMAT_CORRECTIONS_KEY = "general_pi_format_corrections"
PI_FORMAT_CORRECTION_SCHEMA = "general_pi_format_correction.v1"
PI_FORMAT_ADMISSION_SCHEMA = "general_pi_format_correction_admission.v1"
PI_OWNERSHIP_STATES = {"active", "finalized", "checkpointed_failure", "blocked"}
PI_ADOPTABLE_OWNERSHIP_STATES = {"finalized", "checkpointed_failure"}
GENERAL_PI_CHECKPOINT_FIELDS = {
    "input_receipts",
    "before_process_improvement_files",
    "after_process_improvement_files",
    "process_improvement_path_results",
    "prior_receipt_revision",
    "prior_receipt_content_sha256",
    "published_at",
}
V2_DECLARATION_SCHEMA = "followups_declaration.v2"
V2_CYCLE_SCHEMA = "followups_capture_cycle.v2"
V2_PROOF_SCHEMA = "followups_external_proof.v2"
V2_EXTERNAL_FOLLOWUP_STAGING_PROOF_SCHEMA = "v2_external_followup_staging_proof.v1"
V2_EXTERNAL_FOLLOWUP_STAGING_PROOF_KEYS = {
    "schema_version",
    "frozen_manifest_path",
    "frozen_manifest_object",
    "baseline_followups_snapshot_sha256",
    "source_identity",
    "carrier_path",
    "canonical_render_sha256",
    "carrier_object",
    "carrier_absence",
    "expected_parent_oid",
    "expected_rows",
}

# This is deliberately an in-memory, caller-selected witness rather than a
# receipt/payload schema.  The only admitted non-literal semantic readback is
# the one terminal post-CAS transition that consumed the existing ordinary-V2
# source evidence.  Every durable source remains the existing receipt/marker/
# manifest family and is reopened below.
POST_CAS_SEMANTIC_IDENTITY_TRANSITION_ROUTE = (
    "ordinary_v2_post_cas_semantic_identity_transition_v1"
)
POST_CAS_SEMANTIC_IDENTITY_PROOF_KEYS = {
    "route",
    "plan_ref",
    "capture_cycle_id",
    "receipt_content_sha256",
    "semantic_closeout_identity",
    "plan_sha256",
    "terminal_status_line",
    "receipt_semantic_fields",
    "current_semantic_fields",
    "source_terminal_commit_oid",
    "source_plan_blob_oid",
    "source_plan_sha256",
    "frozen_manifest_path",
    "frozen_manifest_sha256",
    "pi_final_objects",
    "current_head",
    "bundle_tree_entries",
}
POST_CAS_REVIEW_RE = re.compile(
    r"(?:/[A-Za-z0-9_./-]*/docs/(?:code_reviews|doc_reviews)/[A-Za-z0-9_./-]+\.md|docs/(?:code_reviews|doc_reviews)/[A-Za-z0-9_./-]+\.md)"
)
POST_CAS_REVIEW_ASSET_RE = re.compile(
    r"(?:/[A-Za-z0-9_./-]*/docs/(?:code_reviews|doc_reviews)/assets/[A-Za-z0-9_./-]+|docs/(?:code_reviews|doc_reviews)/assets/[A-Za-z0-9_./-]+)"
)
POST_CAS_REVIEW_JSON_RE = re.compile(
    r"(?:/[A-Za-z0-9_./-]*/docs/reviews/[A-Za-z0-9_./-]+\.json|docs/reviews/[A-Za-z0-9_./-]+\.json)"
)
POST_CAS_TRANSIENT_RECEIPT_MARKERS = (
    "command output",
    "debug-only",
    "debug only",
    "transient",
    "local sanity",
    "not checked in",
    "not checked-in",
    "not a checked-in artifact",
)

ORDINARY_V2_COMPACT_MAX_BYTES = 16384
ORDINARY_V2_BOUND_DIRECTORY = "ordinary_v2_bound"
ORDINARY_V2_BINDING_KEY = "ordinary_v2_compact_binding"
ORDINARY_V2_INPUT_DIRECTORY = "ordinary_v2_inputs"
ORDINARY_V2_SUBMISSION_DIRECTORY = "ordinary_v2_submissions"
ORDINARY_V2_SUBMISSION_SCHEMA = "ordinary_v2_role_submission.v1"
ORDINARY_V2_SUBMISSION_ACK_SCHEMA = "ordinary_v2_role_submission_ack.v1"
ORDINARY_V2_SUBMISSION_KEY = "ordinary_v2_submission"
BLOCKED_PREDECESSOR_RECOVERY_BINDING_KEY = "followups_blocked_predecessor_recovery_binding"
BLOCKED_PREDECESSOR_RECOVERY_BINDING_SCHEMA = "followups_blocked_predecessor_recovery_binding.v1"
BLOCKED_PREDECESSOR_RECOVERY_ADMISSION_SCHEMA = "followups_blocked_predecessor_recovery_admission.v1"
BLOCKED_PREDECESSOR_RECOVERY_PROFILES: dict[str, dict[str, str]] = {}
ORDINARY_V2_FULL_DECLARATION_KEYS = {
    "schema_version",
    "role",
    "plan_ref",
    "source_terminal_commit_oid",
    "source_plan_blob_oid",
    "baseline_followups_snapshot",
    "proposed_rows",
    "role_no_items_reason",
}


class CaptureError(RuntimeError):
    def __init__(self, reason_code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.details = details

    def payload(self, *, command: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "state": "blocked",
            "reason_code": self.reason_code,
            "message": str(self),
        }
        if command:
            payload["command"] = command
        payload.update(self.details)
        return payload


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_receipt_content_bytes(receipt: dict[str, Any]) -> bytes:
    value = dict(receipt)
    value.pop("receipt_content_sha256", None)
    return _canonical_json_bytes(value)


def receipt_content_sha256(receipt: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_receipt_content_bytes(receipt)).hexdigest()


def persisted_receipt_bytes(receipt: dict[str, Any]) -> bytes:
    return _canonical_json_bytes(receipt) + b"\n"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_type(st: os.stat_result) -> str:
    if stat.S_ISDIR(st.st_mode):
        return "directory"
    if stat.S_ISREG(st.st_mode):
        return "regular"
    if stat.S_ISLNK(st.st_mode):
        return "symlink"
    if stat.S_ISFIFO(st.st_mode):
        return "fifo"
    if stat.S_ISSOCK(st.st_mode):
        return "socket"
    if stat.S_ISCHR(st.st_mode):
        return "character"
    if stat.S_ISBLK(st.st_mode):
        return "block"
    return "unknown"


def _followup_object(st: os.stat_result, data: bytes) -> dict[str, Any]:
    return {
        "sha256": _sha256(data),
        "file_type": _file_type(st),
        "st_size": st.st_size,
    }


def _validate_uuid4(value: str) -> str:
    if not UUID4_RE.fullmatch(value):
        raise CaptureError("followup_capture_cycle_invalid", f"invalid canonical UUIDv4: {value!r}")
    parsed = uuid.UUID(value)
    if parsed.version != 4 or str(parsed) != value:
        raise CaptureError("followup_capture_cycle_invalid", f"invalid canonical UUIDv4: {value!r}")
    return value


def normalize_plan_ref(raw: str) -> str:
    value = raw.strip().replace("\\", "/")
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.as_posix() != value
        or not value.startswith("docs/plans/")
        or not value.endswith(".md")
    ):
        raise CaptureError("followup_capture_plan_ref_invalid", f"invalid plan_ref: {raw!r}")
    return value


def validate_followup_relpath(raw: str) -> str:
    value = raw.strip()
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or path.as_posix() != value
        or len(path.parts) != 3
        or path.parts[:2] != ("docs", "followups")
        or path.name in {"", ".", ".."}
        or not path.name.endswith(".md")
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise CaptureError("followup_capture_path_invalid", f"invalid ordinary followup path: {raw!r}")
    return value


def plan_stem(plan_ref: str) -> str:
    stem = PurePosixPath(normalize_plan_ref(plan_ref)).stem
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", stem):
        raise CaptureError("followup_capture_plan_ref_invalid", f"unsafe plan stem: {stem!r}")
    return stem


def _read_fd_all(fd: int) -> bytes:
    os.lseek(fd, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    while True:
        chunk = os.read(fd, 1024 * 128)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


class CaptureHost:
    def __init__(
        self,
        project_root: Path,
        plan_ref: str,
        *,
        create: bool = False,
    ) -> None:
        self.project_root = project_root.absolute()
        self.plan_ref = normalize_plan_ref(plan_ref)
        self.create = create
        self.family_path = self.project_root / ".tmp" / "followups_capture" / plan_stem(self.plan_ref)
        self._family_fd: int | None = None

    @property
    def family_fd(self) -> int:
        if self._family_fd is None:
            raise CaptureError("followup_capture_host_missing", "capture family is not open")
        return self._family_fd

    def transaction_host_identity(self) -> dict[str, Any]:
        return {
            "project_root": str(self.project_root),
            "plan_family": f".tmp/followups_capture/{plan_stem(self.plan_ref)}",
            "execution_model": "trusted_serial_manager",
        }

    def verify_host(self) -> None:
        try:
            st = self.family_path.lstat()
        except OSError as exc:
            raise CaptureError("followup_capture_host_missing", f"capture family is unavailable: {exc}") from exc
        if not stat.S_ISDIR(st.st_mode):
            raise CaptureError("followup_capture_host_unsafe", "capture family must be a plain directory")

    def __enter__(self) -> "CaptureHost":
        try:
            components = [
                self.project_root,
                self.project_root / ".tmp",
                self.project_root / ".tmp" / "followups_capture",
                self.family_path,
            ]
            for component in components:
                if not component.exists() and self.create:
                    try:
                        component.mkdir()
                    except OSError as exc:
                        raise CaptureError(
                            "followup_capture_host_unsafe",
                            f"cannot create capture directory {component}: {exc}",
                        ) from exc
                _plain_directory(component, "followup_capture_host_unsafe")
            self.verify_host()
            self._family_fd = os.open(self.family_path, os.O_RDONLY | os.O_DIRECTORY)
            return self
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        if self._family_fd is not None:
            with contextlib.suppress(OSError):
                os.close(self._family_fd)
            self._family_fd = None

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if exc is None:
            self.verify_host()
        self.close()

def _plain_directory(path: Path, reason: str) -> Path:
    try:
        st = path.lstat()
    except OSError as exc:
        raise CaptureError(reason, f"cannot read directory {path}: {exc}") from exc
    if not stat.S_ISDIR(st.st_mode):
        raise CaptureError(reason, f"path is not a plain directory: {path}")
    return path


def _read_regular_path(path: Path, rel_path: str) -> tuple[dict[str, Any], bytes]:
    try:
        before = path.lstat()
    except OSError as exc:
        raise CaptureError("followup_capture_path_unsafe", f"cannot lstat {rel_path}: {exc}", path=rel_path) from exc
    if not stat.S_ISREG(before.st_mode):
        raise CaptureError(
            "followup_capture_path_unsafe",
            f"path is not a regular file: {rel_path}",
            path=rel_path,
            file_type=_file_type(before),
        )
    try:
        data = path.read_bytes()
        after = path.lstat()
    except OSError as exc:
        raise CaptureError("followup_capture_path_unsafe", f"cannot read {rel_path}: {exc}", path=rel_path) from exc
    if not stat.S_ISREG(after.st_mode) or after.st_size != len(data):
        raise CaptureError("followup_capture_path_object_drift", f"file changed during read: {rel_path}", path=rel_path)
    return _followup_object(after, data), data


def snapshot_followups(project_root: Path, *, include_bytes: bool = False) -> tuple[dict[str, dict[str, Any]], dict[str, bytes]]:
    objects: dict[str, dict[str, Any]] = {}
    contents: dict[str, bytes] = {}
    followups_dir = project_root.absolute() / "docs" / "followups"
    if not followups_dir.exists():
        return {}, {}
    _plain_directory(followups_dir, "followup_capture_path_ancestor_unsafe")
    for path in sorted(followups_dir.iterdir(), key=lambda item: item.name):
        if not path.name.endswith(".md"):
            continue
        rel_path = validate_followup_relpath(f"docs/followups/{path.name}")
        obj, data = _read_regular_path(path, rel_path)
        objects[rel_path] = obj
        if include_bytes:
            contents[rel_path] = data
    return objects, contents


def _v2_source_identity(project_root: Path, plan_ref: str, commit_oid: str, blob_oid: str) -> dict[str, str]:
    """Validate the immutable terminal source binding used by V2 declarations."""

    plan_ref = normalize_plan_ref(plan_ref)
    if not OID_RE.fullmatch(commit_oid) or not OID_RE.fullmatch(blob_oid):
        raise CaptureError("followup_v2_source_oid_invalid", "V2 source commit/blob OIDs must be lower-case hexadecimal Git OIDs")
    commit = _git(project_root, "rev-parse", f"{commit_oid}^{{commit}}", check=False)
    if commit.returncode != 0:
        raise CaptureError("followup_v2_source_commit_missing", "V2 source terminal commit is not reachable")
    resolved_commit = commit.stdout.decode("utf-8", errors="replace").strip()
    ancestor = _git(project_root, "merge-base", "--is-ancestor", resolved_commit, "HEAD", check=False)
    if ancestor.returncode != 0:
        raise CaptureError(
            "followup_v2_source_commit_unreachable",
            "V2 source terminal commit is not reachable from current HEAD",
        )
    show = _git(project_root, "show", f"{resolved_commit}:{plan_ref}", check=False)
    if show.returncode != 0:
        raise CaptureError("followup_v2_source_plan_missing", "V2 source terminal commit does not contain the declared plan path")
    plan_bytes = show.stdout
    text = plan_bytes.decode("utf-8", errors="replace")
    statuses = [
        match.group("value").strip().lower()
        for line in text.splitlines()
        if (match := STATUS_RE.match(line))
    ]
    if len(statuses) != 1 or statuses[0] not in {"done", "superseded"}:
        raise CaptureError("followup_v2_source_not_terminal", "V2 source plan bytes are not one committed Done or Superseded terminal carrier")
    actual_blob = _git(project_root, "rev-parse", f"{resolved_commit}:{plan_ref}").stdout.decode("utf-8").strip()
    if actual_blob != blob_oid:
        raise CaptureError("followup_v2_source_blob_mismatch", "V2 source_plan_blob_oid does not match the declared plan blob in source commit")
    return {
        "plan_ref": plan_ref,
        "source_terminal_commit_oid": resolved_commit,
        "source_plan_blob_oid": actual_blob,
        "source_plan_sha256": _sha256(plan_bytes),
    }


def _v2_row_from_declaration(raw: object, *, declaration_role: str) -> tuple[str, dict[str, object], str]:
    """Normalize one role-proposed row without granting declaration write authority."""

    try:
        from followups_apply import ApplyError, load_frozen_manifest
    except ModuleNotFoundError:  # package import in focused unittest invocation
        from scripts.followups_apply import ApplyError, load_frozen_manifest

    if not isinstance(raw, dict):
        raise CaptureError("followup_v2_declaration_row_invalid", "V2 declaration proposed_rows entries must be objects")
    # Reuse the sole-writer parser by validating a one-row frozen manifest in
    # memory.  This keeps tuple/digest grammar identical at declaration and
    # apply boundaries without writing a file.
    followup_path = raw.get("followup_path")
    payload = raw.get("payload")
    digest = raw.get("row_digest")
    if not isinstance(payload, dict) or not isinstance(digest, str):
        raise CaptureError("followup_v2_declaration_row_invalid", "V2 declaration row needs followup_path, payload and row_digest")
    source_ref = payload.get("source_ref")
    item_id = payload.get("item_id")
    if not isinstance(source_ref, str) or not isinstance(item_id, str):
        raise CaptureError("followup_v2_declaration_row_invalid", "V2 declaration row payload lacks source_ref/item_id")
    manifest = {
        "schema_version": V2_CYCLE_SCHEMA,
        "plan_ref": "docs/plans/declaration_validation.md",
        "source_terminal_commit_oid": "a" * 40,
        "source_plan_blob_oid": "b" * 40,
        "baseline_followups_snapshot": {},
        "declaration_roles": list(REQUIRED_ROLES),
        "expected_owned_tuples": [{"source_ref": source_ref, "item_id": item_id}],
        "tuple_owners": {f"{source_ref}\u0000{item_id}": declaration_role},
        "expected_zero_reason": None,
        "proposed_rows": [{"followup_path": followup_path, "payload": payload, "row_digest": digest}],
    }
    try:
        _ignored, rows = load_frozen_manifest(manifest)
    except ApplyError as exc:
        raise CaptureError("followup_v2_declaration_row_invalid", str(exc)) from exc
    row = rows[0]
    return row.followup_path, row.payload, row.digest


def validate_v2_declaration(project_root: Path, plan_ref: str, declaration: dict[str, Any]) -> dict[str, Any]:
    """Validate one read-only role declaration and return its normalized shape."""

    try:
        import followups_lint
    except ModuleNotFoundError:  # package import in focused unittest invocation
        from scripts import followups_lint

    if declaration.get("schema_version") != V2_DECLARATION_SCHEMA:
        raise CaptureError("followup_v2_declaration_schema_invalid", f"schema_version must be {V2_DECLARATION_SCHEMA}")
    role = declaration.get("role")
    if role not in REQUIRED_ROLES:
        raise CaptureError("followup_v2_declaration_role_invalid", "V2 declaration role is not in the ordered role family")
    raw_plan_ref = declaration.get("plan_ref")
    if raw_plan_ref != normalize_plan_ref(plan_ref):
        raise CaptureError("followup_v2_declaration_plan_mismatch", "V2 declaration plan_ref does not match the requested source plan")
    commit = declaration.get("source_terminal_commit_oid")
    blob = declaration.get("source_plan_blob_oid")
    if not isinstance(commit, str) or not isinstance(blob, str):
        raise CaptureError("followup_v2_declaration_source_invalid", "V2 declaration lacks source commit/blob OIDs")
    source = _v2_source_identity(project_root, plan_ref, commit, blob)
    baseline = declaration.get("baseline_followups_snapshot")
    if not isinstance(baseline, dict):
        raise CaptureError("followup_v2_declaration_baseline_invalid", "V2 declaration requires a baseline followups snapshot object")
    current, _bytes = snapshot_followups(project_root)
    if baseline != current:
        raise CaptureError("followup_v2_declaration_baseline_drift", "V2 declaration baseline does not match the observed current followups object map")
    raw_rows = declaration.get("proposed_rows")
    no_items_reason = declaration.get("role_no_items_reason")
    if not isinstance(raw_rows, list):
        raise CaptureError("followup_v2_declaration_rows_invalid", "V2 declaration proposed_rows must be an array")
    if raw_rows:
        if no_items_reason is not None:
            raise CaptureError("followup_v2_declaration_no_items_invalid", "non-empty V2 declaration forbids role_no_items_reason")
    elif not isinstance(no_items_reason, str) or not no_items_reason.strip():
        raise CaptureError("followup_v2_declaration_no_items_invalid", "empty V2 declaration requires non-empty role_no_items_reason")
    rows: list[dict[str, object]] = []
    tuples: set[tuple[str, str]] = set()
    for raw_row in raw_rows:
        followup_path, payload, digest = _v2_row_from_declaration(raw_row, declaration_role=str(role))
        rendered = followups_lint.render_v2_row(payload)
        parsed = followups_lint.parse_followup_item(followup_path, 1, rendered)
        if parsed is None:
            raise CaptureError("followup_v2_declaration_row_invalid", "V2 declaration row cannot be parsed after canonical rendering")
        row_findings = followups_lint.lint_v2_item(parsed, project_root)
        if row_findings:
            raise CaptureError(
                "followup_v2_declaration_row_invalid",
                "V2 declaration row fails full field/source validation: "
                + ", ".join(sorted({finding.code for finding in row_findings})),
            )
        source_ref = str(payload["source_ref"])
        item_id = str(payload["item_id"])
        if source_ref != source["plan_ref"] and not source_ref.startswith(source["plan_ref"] + "#"):
            raise CaptureError(
                "followup_v2_declaration_source_ref_mismatch",
                "a terminal-plan declaration may propose only rows source-bound to that exact plan path or anchor",
            )
        tuple_value = (source_ref, item_id)
        if tuple_value in tuples:
            raise CaptureError("followup_v2_declaration_tuple_duplicate", "one declaration repeats a V2 tuple")
        tuples.add(tuple_value)
        rows.append({"followup_path": followup_path, "payload": payload, "row_digest": digest})
    return {
        "schema_version": V2_DECLARATION_SCHEMA,
        "role": role,
        "plan_ref": source["plan_ref"],
        **source,
        "baseline_followups_snapshot": baseline,
        "baseline_followups_snapshot_sha256": _sha256(_canonical_json_bytes(baseline)),
        "proposed_rows": rows,
        "role_no_items_reason": no_items_reason.strip() if isinstance(no_items_reason, str) else None,
    }


def freeze_v2_declarations(project_root: Path, plan_ref: str, declarations: list[dict[str, Any]]) -> dict[str, Any]:
    """Freeze exactly four compatible role declarations before the only durable writer."""

    if len(declarations) != len(REQUIRED_ROLES):
        raise CaptureError("followup_v2_declaration_set_incomplete", "V2 freeze requires exactly four role declarations")
    normalized = [validate_v2_declaration(project_root, plan_ref, value) for value in declarations]
    roles = [str(value["role"]) for value in normalized]
    if tuple(roles) != REQUIRED_ROLES:
        raise CaptureError("followup_v2_declaration_order_invalid", "V2 declarations must be Architect -> Coder -> Planner -> Reviewer")
    identity_keys = (
        "plan_ref",
        "source_terminal_commit_oid",
        "source_plan_blob_oid",
        "baseline_followups_snapshot_sha256",
    )
    first = normalized[0]
    if any(any(value[key] != first[key] for key in identity_keys) for value in normalized[1:]):
        raise CaptureError("followup_v2_declaration_identity_drift", "V2 declarations do not share one source/blob/baseline identity")
    proposed_rows: list[dict[str, object]] = []
    owners: dict[str, str] = {}
    expected: list[dict[str, str]] = []
    for declaration in normalized:
        role = str(declaration["role"])
        for row in declaration["proposed_rows"]:
            assert isinstance(row, dict)
            payload = row["payload"]
            assert isinstance(payload, dict)
            source_ref = str(payload["source_ref"])
            item_id = str(payload["item_id"])
            key = f"{source_ref}\u0000{item_id}"
            if key in owners:
                raise CaptureError("followup_v2_declaration_overlap", "V2 declarations overlap on one durable tuple")
            owners[key] = role
            expected.append({"source_ref": source_ref, "item_id": item_id})
            proposed_rows.append(dict(row))
    expected.sort(key=lambda item: (item["source_ref"], item["item_id"]))
    proposed_rows.sort(key=lambda row: (str(row["payload"]["source_ref"]), str(row["payload"]["item_id"])))
    empty_reason: str | None = None
    if not expected:
        empty_reason = " | ".join(
            f"{value['role']}: {value['role_no_items_reason']}" for value in normalized
        )
    return {
        "schema_version": V2_CYCLE_SCHEMA,
        "plan_ref": first["plan_ref"],
        "source_terminal_commit_oid": first["source_terminal_commit_oid"],
        "source_plan_blob_oid": first["source_plan_blob_oid"],
        "source_plan_sha256": first["source_plan_sha256"],
        "baseline_followups_snapshot": first["baseline_followups_snapshot"],
        "baseline_followups_snapshot_sha256": first["baseline_followups_snapshot_sha256"],
        "declaration_roles": roles,
        "expected_owned_tuples": expected,
        "tuple_owners": owners,
        "expected_zero_reason": empty_reason,
        "proposed_rows": proposed_rows,
    }


def _stat_identity(st: os.stat_result) -> tuple[int, int, int, int, int, int]:
    """Return immutable stat fields used for descriptor/path drift checks."""

    return (st.st_dev, st.st_ino, st.st_mode, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def _ordinary_v2_strict_json_object(
    raw: bytes,
    *,
    enforce_compact_limit: bool = True,
) -> dict[str, Any]:
    """Decode the ordinary compact declaration without accepting JSON ambiguity."""

    if enforce_compact_limit and len(raw) > ORDINARY_V2_COMPACT_MAX_BYTES:
        raise CaptureError(
            "followup_ordinary_v2_input_too_large",
            f"compact declaration exceeds {ORDINARY_V2_COMPACT_MAX_BYTES} bytes",
        )
    if raw.startswith(b"\xef\xbb\xbf"):
        raise CaptureError("followup_ordinary_v2_input_invalid", "compact declaration must not carry a UTF-8 BOM")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CaptureError("followup_ordinary_v2_input_invalid", f"compact declaration is not valid UTF-8: {exc}") from exc

    def no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise CaptureError("followup_ordinary_v2_input_invalid", f"duplicate compact declaration key: {key}")
            value[key] = item
        return value

    def reject_nonfinite(value: str) -> Any:
        raise CaptureError("followup_ordinary_v2_input_invalid", f"non-finite compact declaration value: {value}")

    decoder = json.JSONDecoder(object_pairs_hook=no_duplicate_keys, parse_constant=reject_nonfinite)
    start = len(text) - len(text.lstrip())
    try:
        value, end = decoder.raw_decode(text, start)
    except (json.JSONDecodeError, ValueError) as exc:
        raise CaptureError("followup_ordinary_v2_input_invalid", f"invalid compact declaration JSON: {exc}") from exc
    if text[end:].strip():
        raise CaptureError("followup_ordinary_v2_input_invalid", "compact declaration has a prefix, suffix, or second JSON value")
    if not isinstance(value, dict):
        raise CaptureError("followup_ordinary_v2_input_invalid", "compact declaration root must be an object")
    return value


def _ordinary_v2_read_compact_input(input_path: str) -> bytes:
    if input_path != "-":
        raise CaptureError(
            "followup_ordinary_v2_input_path_invalid",
            "submit-ordinary-v2 accepts compact role stdout only through --input -",
        )
    raw = sys.stdin.buffer.read(ORDINARY_V2_COMPACT_MAX_BYTES + 1)
    if len(raw) > ORDINARY_V2_COMPACT_MAX_BYTES:
        raise CaptureError(
            "followup_ordinary_v2_input_too_large",
            f"compact declaration exceeds {ORDINARY_V2_COMPACT_MAX_BYTES} bytes",
        )
    return raw


def _ordinary_v2_validate_compact_declaration(value: dict[str, Any], role: str) -> dict[str, Any]:
    required_fields = {"role", "proposed_rows", "role_no_items_reason"}
    if set(value) != required_fields:
        raise CaptureError(
            "followup_ordinary_v2_input_invalid",
            "compact declaration must contain exactly role, proposed_rows, and role_no_items_reason",
        )
    if role not in REQUIRED_ROLES or value.get("role") != role:
        raise CaptureError("followup_ordinary_v2_role_invalid", "compact declaration role must exactly match the CLI role")
    rows = value.get("proposed_rows")
    if not isinstance(rows, list):
        raise CaptureError("followup_ordinary_v2_input_invalid", "compact declaration proposed_rows must be an array")
    reason = value.get("role_no_items_reason")
    if rows:
        if reason is not None:
            raise CaptureError(
                "followup_ordinary_v2_no_items_invalid",
                "a non-empty compact declaration forbids role_no_items_reason",
            )
    elif not isinstance(reason, str) or not reason.strip():
        raise CaptureError(
            "followup_ordinary_v2_no_items_invalid",
            "an empty compact declaration requires a non-empty role_no_items_reason",
        )
    return {
        "role": role,
        "proposed_rows": json.loads(_canonical_json_bytes(rows).decode("utf-8")),
        "role_no_items_reason": reason.strip() if isinstance(reason, str) else None,
    }


def _ordinary_v2_submission_dir_relpath(plan_ref: str, cycle_id: str) -> str:
    _validate_uuid4(cycle_id)
    return f".tmp/followups_capture/{plan_stem(plan_ref)}/{cycle_id}/{ORDINARY_V2_SUBMISSION_DIRECTORY}"


def _ordinary_v2_input_dir_relpath(plan_ref: str, cycle_id: str) -> str:
    _validate_uuid4(cycle_id)
    return f".tmp/followups_capture/{plan_stem(plan_ref)}/{cycle_id}/{ORDINARY_V2_INPUT_DIRECTORY}"


def _ordinary_v2_input_role_relpath(plan_ref: str, cycle_id: str, role: str) -> str:
    if role not in REQUIRED_ROLES:
        raise CaptureError("followup_ordinary_v2_role_invalid", f"unsupported ordinary compact role: {role!r}")
    return f"{_ordinary_v2_input_dir_relpath(plan_ref, cycle_id)}/{role}.json"


def _ordinary_v2_open_input_directory(
    cycle_fd: int,
    *,
    plan_ref: str,
    cycle_id: str,
    create: bool,
) -> int:
    """Open the helper-derived transient input directory without path fallback."""

    rel_path = _ordinary_v2_input_dir_relpath(plan_ref, cycle_id)
    try:
        before = os.stat(ORDINARY_V2_INPUT_DIRECTORY, dir_fd=cycle_fd, follow_symlinks=False)
    except FileNotFoundError:
        if not create:
            raise CaptureError("followup_ordinary_v2_input_missing", f"missing ordinary current-input directory: {rel_path}")
        try:
            os.mkdir(ORDINARY_V2_INPUT_DIRECTORY, 0o700, dir_fd=cycle_fd)
        except FileExistsError:
            pass
        except OSError as exc:
            raise CaptureError("followup_ordinary_v2_input_path_unsafe", f"cannot create ordinary current-input directory: {exc}") from exc
        try:
            before = os.stat(ORDINARY_V2_INPUT_DIRECTORY, dir_fd=cycle_fd, follow_symlinks=False)
        except OSError as exc:
            raise CaptureError("followup_ordinary_v2_input_path_unsafe", f"cannot stat ordinary current-input directory: {exc}") from exc
    except OSError as exc:
        raise CaptureError("followup_ordinary_v2_input_path_unsafe", f"cannot stat ordinary current-input directory: {exc}") from exc
    if not stat.S_ISDIR(before.st_mode):
        raise CaptureError("followup_ordinary_v2_input_path_unsafe", f"ordinary current-input directory is not plain: {rel_path}")
    flags = os.O_RDONLY | os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(ORDINARY_V2_INPUT_DIRECTORY, flags, dir_fd=cycle_fd)
    except OSError as exc:
        raise CaptureError("followup_ordinary_v2_input_path_unsafe", f"cannot open ordinary current-input directory: {exc}") from exc
    opened = os.fstat(fd)
    if (
        not stat.S_ISDIR(opened.st_mode)
        or _stat_identity(before) != _stat_identity(opened)
    ):
        os.close(fd)
        raise CaptureError("followup_ordinary_v2_input_path_drift", f"ordinary current-input directory drifted: {rel_path}")
    if stat.S_IMODE(opened.st_mode) != 0o700:
        os.close(fd)
        raise CaptureError("followup_ordinary_v2_input_path_unsafe", f"ordinary current-input directory mode is not 700: {rel_path}")
    return fd


def _ordinary_v2_read_fd_limited(fd: int, *, limit: int) -> bytes:
    chunks: list[bytes] = []
    remaining = limit + 1
    while remaining:
        chunk = os.read(fd, min(1024 * 128, remaining))
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _ordinary_v2_read_current_input(
    input_fd: int,
    *,
    plan_ref: str,
    capture_cycle_id: str,
    role: str,
) -> bytes:
    role_name = f"{role}.json"
    rel_path = _ordinary_v2_input_role_relpath(plan_ref, capture_cycle_id, role)
    try:
        before = os.stat(role_name, dir_fd=input_fd, follow_symlinks=False)
    except FileNotFoundError as exc:
        raise CaptureError("followup_ordinary_v2_input_missing", f"missing ordinary current input: {rel_path}") from exc
    except OSError as exc:
        raise CaptureError("followup_ordinary_v2_input_path_unsafe", f"cannot stat ordinary current input: {exc}") from exc
    if not stat.S_ISREG(before.st_mode):
        raise CaptureError("followup_ordinary_v2_input_path_unsafe", f"ordinary current input is not a regular file: {rel_path}")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(role_name, flags, dir_fd=input_fd)
    except OSError as exc:
        raise CaptureError("followup_ordinary_v2_input_path_unsafe", f"cannot open ordinary current input: {exc}") from exc
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode) or _stat_identity(before) != _stat_identity(opened):
            raise CaptureError("followup_ordinary_v2_input_path_drift", f"ordinary current input drifted: {rel_path}")
        raw = _ordinary_v2_read_fd_limited(fd, limit=ORDINARY_V2_COMPACT_MAX_BYTES)
        after = os.fstat(fd)
    finally:
        os.close(fd)
    try:
        current = os.stat(role_name, dir_fd=input_fd, follow_symlinks=False)
    except OSError as exc:
        raise CaptureError("followup_ordinary_v2_input_path_drift", f"ordinary current input disappeared: {rel_path}") from exc
    if (
        _stat_identity(before) != _stat_identity(after)
        or _stat_identity(before) != _stat_identity(current)
    ):
        raise CaptureError("followup_ordinary_v2_input_path_drift", f"ordinary current input changed while reading: {rel_path}")
    if before.st_size > ORDINARY_V2_COMPACT_MAX_BYTES or len(raw) > ORDINARY_V2_COMPACT_MAX_BYTES:
        raise CaptureError(
            "followup_ordinary_v2_input_too_large",
            f"compact declaration exceeds {ORDINARY_V2_COMPACT_MAX_BYTES} bytes",
        )
    if len(raw) != before.st_size:
        raise CaptureError("followup_ordinary_v2_input_path_drift", f"ordinary current input changed while reading: {rel_path}")
    return raw


def _ordinary_v2_submission_role_relpath(plan_ref: str, cycle_id: str, role: str) -> str:
    if role not in REQUIRED_ROLES:
        raise CaptureError("followup_ordinary_v2_role_invalid", f"unsupported ordinary compact role: {role!r}")
    return f"{_ordinary_v2_submission_dir_relpath(plan_ref, cycle_id)}/{role}.json"


def _ordinary_v2_open_submission_directory(
    cycle_fd: int,
    *,
    plan_ref: str,
    cycle_id: str,
    create: bool,
) -> int:
    """Open the helper-owned submission slot directory without path fallback."""

    rel_path = _ordinary_v2_submission_dir_relpath(plan_ref, cycle_id)
    try:
        before = os.stat(ORDINARY_V2_SUBMISSION_DIRECTORY, dir_fd=cycle_fd, follow_symlinks=False)
    except FileNotFoundError:
        if not create:
            raise CaptureError("followup_ordinary_v2_submission_missing", f"missing ordinary submission directory: {rel_path}")
        try:
            os.mkdir(ORDINARY_V2_SUBMISSION_DIRECTORY, 0o700, dir_fd=cycle_fd)
        except FileExistsError:
            pass
        except OSError as exc:
            raise CaptureError("followup_ordinary_v2_submission_path_unsafe", f"cannot create ordinary submission directory: {exc}") from exc
        try:
            before = os.stat(ORDINARY_V2_SUBMISSION_DIRECTORY, dir_fd=cycle_fd, follow_symlinks=False)
        except OSError as exc:
            raise CaptureError("followup_ordinary_v2_submission_path_unsafe", f"cannot stat ordinary submission directory: {exc}") from exc
    except OSError as exc:
        raise CaptureError("followup_ordinary_v2_submission_path_unsafe", f"cannot stat ordinary submission directory: {exc}") from exc
    if not stat.S_ISDIR(before.st_mode):
        raise CaptureError("followup_ordinary_v2_submission_path_unsafe", f"ordinary submission directory is not plain: {rel_path}")
    flags = os.O_RDONLY | os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(ORDINARY_V2_SUBMISSION_DIRECTORY, flags, dir_fd=cycle_fd)
    except OSError as exc:
        raise CaptureError("followup_ordinary_v2_submission_path_unsafe", f"cannot open ordinary submission directory: {exc}") from exc
    opened = os.fstat(fd)
    if (
        not stat.S_ISDIR(opened.st_mode)
        or _stat_identity(before) != _stat_identity(opened)
    ):
        os.close(fd)
        raise CaptureError("followup_ordinary_v2_submission_path_drift", f"ordinary submission directory drifted: {rel_path}")
    if stat.S_IMODE(opened.st_mode) != 0o700:
        os.close(fd)
        raise CaptureError("followup_ordinary_v2_submission_path_unsafe", f"ordinary submission directory mode is not 700: {rel_path}")
    return fd


def _ordinary_v2_submission_carrier(
    *,
    plan_ref: str,
    capture_cycle_id: str,
    role: str,
    receipt: dict[str, Any],
    compact: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": ORDINARY_V2_SUBMISSION_SCHEMA,
        "plan_ref": plan_ref,
        "capture_cycle_id": capture_cycle_id,
        "role": role,
        "prepared_receipt_content_sha256": receipt["receipt_content_sha256"],
        "prepared_receipt_object_identity": json.loads(
            _canonical_json_bytes(receipt["receipt_object_identity"]).decode("utf-8")
        ),
        "compact_declaration": json.loads(_canonical_json_bytes(compact).decode("utf-8")),
        "compact_declaration_sha256": _sha256(_canonical_json_bytes(compact)),
    }


def _ordinary_v2_validate_submission_carrier(
    value: Any,
    *,
    plan_ref: str,
    capture_cycle_id: str,
    role: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CaptureError("followup_ordinary_v2_submission_invalid", "ordinary submission must be an object")
    required = {
        "schema_version",
        "plan_ref",
        "capture_cycle_id",
        "role",
        "prepared_receipt_content_sha256",
        "prepared_receipt_object_identity",
        "compact_declaration",
        "compact_declaration_sha256",
    }
    if set(value) != required:
        raise CaptureError("followup_ordinary_v2_submission_invalid", "ordinary submission has unknown or missing fields")
    if value.get("schema_version") != ORDINARY_V2_SUBMISSION_SCHEMA:
        raise CaptureError("followup_ordinary_v2_submission_invalid", "ordinary submission schema is invalid")
    if value.get("plan_ref") != plan_ref or value.get("capture_cycle_id") != capture_cycle_id or value.get("role") != role:
        raise CaptureError("followup_ordinary_v2_submission_invalid", "ordinary submission identity is invalid")
    if not isinstance(value.get("prepared_receipt_content_sha256"), str) or not HEX64_RE.fullmatch(value["prepared_receipt_content_sha256"]):
        raise CaptureError("followup_ordinary_v2_submission_invalid", "ordinary submission prepared receipt digest is invalid")
    identity = value.get("prepared_receipt_object_identity")
    if not isinstance(identity, dict) or identity.get("path") != _receipt_relpath(plan_ref, capture_cycle_id) or identity.get("file_type") != "regular":
        raise CaptureError("followup_ordinary_v2_submission_invalid", "ordinary submission prepared receipt object identity is invalid")
    compact = _ordinary_v2_validate_compact_declaration(value.get("compact_declaration"), role)
    compact_hash = value.get("compact_declaration_sha256")
    if not isinstance(compact_hash, str) or compact_hash != _sha256(_canonical_json_bytes(compact)):
        raise CaptureError("followup_ordinary_v2_submission_invalid", "ordinary submission compact declaration digest is invalid")
    return _ordinary_v2_submission_carrier(
        plan_ref=plan_ref,
        capture_cycle_id=capture_cycle_id,
        role=role,
        receipt={
            "receipt_content_sha256": value["prepared_receipt_content_sha256"],
            "receipt_object_identity": identity,
        },
        compact=compact,
    )


def _ordinary_v2_read_submission(
    submission_fd: int,
    *,
    plan_ref: str,
    capture_cycle_id: str,
    role: str,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    role_name = f"{role}.json"
    rel_path = _ordinary_v2_submission_role_relpath(plan_ref, capture_cycle_id, role)
    try:
        before = os.stat(role_name, dir_fd=submission_fd, follow_symlinks=False)
    except FileNotFoundError as exc:
        raise CaptureError("followup_ordinary_v2_submission_missing", f"missing ordinary submission: {rel_path}") from exc
    except OSError as exc:
        raise CaptureError("followup_ordinary_v2_submission_path_unsafe", f"cannot stat ordinary submission: {exc}") from exc
    if not stat.S_ISREG(before.st_mode) or stat.S_IMODE(before.st_mode) != 0o600:
        raise CaptureError("followup_ordinary_v2_submission_path_unsafe", f"ordinary submission is not a mode-0600 regular file: {rel_path}")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(role_name, flags, dir_fd=submission_fd)
    except OSError as exc:
        raise CaptureError("followup_ordinary_v2_submission_path_unsafe", f"cannot open ordinary submission: {exc}") from exc
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode) or _stat_identity(before) != _stat_identity(opened):
            raise CaptureError("followup_ordinary_v2_submission_path_drift", f"ordinary submission drifted: {rel_path}")
        raw = _read_fd_all(fd)
        after = os.fstat(fd)
    finally:
        os.close(fd)
    try:
        current = os.stat(role_name, dir_fd=submission_fd, follow_symlinks=False)
    except OSError as exc:
        raise CaptureError("followup_ordinary_v2_submission_path_drift", f"ordinary submission disappeared: {rel_path}") from exc
    if (
        len(raw) != before.st_size
        or _stat_identity(before) != _stat_identity(after)
        or _stat_identity(before) != _stat_identity(current)
    ):
        raise CaptureError("followup_ordinary_v2_submission_path_drift", f"ordinary submission changed while reading: {rel_path}")
    value = _ordinary_v2_strict_json_object(raw, enforce_compact_limit=False)
    carrier = _ordinary_v2_validate_submission_carrier(
        value,
        plan_ref=plan_ref,
        capture_cycle_id=capture_cycle_id,
        role=role,
    )
    if raw != _canonical_json_bytes(carrier) + b"\n":
        raise CaptureError("followup_ordinary_v2_submission_invalid", f"ordinary submission is not canonical: {rel_path}")
    return carrier, _sha256(raw), {"path": rel_path, **_followup_object(current, raw)}


def _ordinary_v2_write_submission(
    submission_fd: int,
    *,
    plan_ref: str,
    capture_cycle_id: str,
    role: str,
    carrier: dict[str, Any],
) -> tuple[str, str, dict[str, Any], bool]:
    """Publish exactly one immutable role-local submission, with exact replay only."""

    role_name = f"{role}.json"
    rel_path = _ordinary_v2_submission_role_relpath(plan_ref, capture_cycle_id, role)
    data = _canonical_json_bytes(carrier) + b"\n"
    try:
        existing = os.stat(role_name, dir_fd=submission_fd, follow_symlinks=False)
    except FileNotFoundError:
        existing = None
    except OSError as exc:
        raise CaptureError("followup_ordinary_v2_submission_path_unsafe", f"cannot stat ordinary submission: {exc}") from exc
    if existing is not None:
        existing_carrier, existing_sha256, existing_object = _ordinary_v2_read_submission(
            submission_fd,
            plan_ref=plan_ref,
            capture_cycle_id=capture_cycle_id,
            role=role,
        )
        if existing_carrier != carrier:
            raise CaptureError("followup_ordinary_v2_submission_conflict", f"ordinary submission already exists with different bytes: {rel_path}")
        return rel_path, existing_sha256, existing_object, False
    temp_name = f".ordinary-submission-tmp-{uuid.uuid4()}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    try:
        fd = os.open(temp_name, flags, 0o600, dir_fd=submission_fd)
    except OSError as exc:
        raise CaptureError("followup_ordinary_v2_submission_publish_failed", f"cannot create ordinary submission temp file: {exc}") from exc
    try:
        os.fchmod(fd, 0o600)
        _write_all(fd, data)
        os.fsync(fd)
        written = os.fstat(fd)
        if not stat.S_ISREG(written.st_mode) or stat.S_IMODE(written.st_mode) != 0o600 or written.st_size != len(data):
            raise CaptureError("followup_ordinary_v2_submission_publish_failed", "ordinary submission temp file is unsafe")
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(temp_name, dir_fd=submission_fd)
        raise
    finally:
        os.close(fd)
    try:
        os.link(temp_name, role_name, src_dir_fd=submission_fd, dst_dir_fd=submission_fd, follow_symlinks=False)
    except FileExistsError:
        existing_carrier, existing_sha256, existing_object = _ordinary_v2_read_submission(
            submission_fd,
            plan_ref=plan_ref,
            capture_cycle_id=capture_cycle_id,
            role=role,
        )
        if existing_carrier != carrier:
            raise CaptureError("followup_ordinary_v2_submission_conflict", f"ordinary submission already exists with different bytes: {rel_path}")
        return rel_path, existing_sha256, existing_object, False
    except OSError as exc:
        raise CaptureError("followup_ordinary_v2_submission_publish_failed", f"cannot publish ordinary submission: {exc}") from exc
    finally:
        with contextlib.suppress(OSError):
            os.unlink(temp_name, dir_fd=submission_fd)
    try:
        os.fsync(submission_fd)
    except OSError as exc:
        raise CaptureError("followup_ordinary_v2_submission_publish_failed", f"cannot sync ordinary submission directory: {exc}") from exc
    published, digest, object_identity = _ordinary_v2_read_submission(
        submission_fd,
        plan_ref=plan_ref,
        capture_cycle_id=capture_cycle_id,
        role=role,
    )
    if published != carrier or digest != _sha256(data):
        raise CaptureError("followup_ordinary_v2_submission_publish_failed", "published ordinary submission differs from complete input")
    return rel_path, digest, object_identity, True


def submit_ordinary_v2(
    project_root: Path,
    *,
    plan_ref: str,
    capture_cycle_id: str,
    role: str,
    write: bool,
    raw_input: bytes | None = None,
    input_current: bool = False,
) -> dict[str, Any]:
    """Publish a producer-local compact declaration without mutating the aggregate receipt."""

    plan_ref = normalize_plan_ref(plan_ref)
    _validate_uuid4(capture_cycle_id)
    if not write:
        raise CaptureError("followup_ordinary_v2_write_required", "submit-ordinary-v2 requires --write")
    if role not in REQUIRED_ROLES:
        raise CaptureError("followup_ordinary_v2_role_invalid", f"unsupported ordinary compact role: {role!r}")
    if input_current and raw_input is not None:
        raise CaptureError("followup_ordinary_v2_input_invalid", "current-input submission cannot also receive compact bytes")
    if not input_current and raw_input is None:
        raise CaptureError("followup_ordinary_v2_input_invalid", "ordinary submission requires compact bytes or --input-current")
    compact = (
        None
        if input_current
        else _ordinary_v2_validate_compact_declaration(_ordinary_v2_strict_json_object(raw_input), role)
    )
    with CaptureHost(project_root, plan_ref) as host:
        cycle_fd, cycle_identity = _open_cycle(host, capture_cycle_id)
        try:
            receipt, _raw, _receipt_identity_value = _read_receipt(cycle_fd, plan_ref, capture_cycle_id)
            if (
                receipt.get("cycle_directory_identity") != cycle_identity
                or receipt.get("transaction_host_identity") != host.transaction_host_identity()
            ):
                raise CaptureError("followup_capture_host_object_drift", "capture transaction identity mismatch")
            _current_plan_identity(project_root, receipt)
            if receipt.get("state") != "started":
                raise CaptureError("followup_ordinary_v2_family_closed", "ordinary compact submission requires an active capture cycle")
            prepared = receipt.get("role_results", {}).get(role)
            if not isinstance(prepared, dict) or prepared.get("state") != "prepared" or _expected_role(receipt) != role:
                raise CaptureError("followup_ordinary_v2_role_not_prepared", "ordinary compact submission requires the exact prepared next role")
            source = _ordinary_v2_current_source_identity(project_root, plan_ref, receipt)
            if input_current:
                try:
                    submission_fd = _ordinary_v2_open_submission_directory(
                        cycle_fd,
                        plan_ref=plan_ref,
                        cycle_id=capture_cycle_id,
                        create=False,
                    )
                except CaptureError as exc:
                    if exc.reason_code != "followup_ordinary_v2_submission_missing":
                        raise
                    submission_fd = None
                if submission_fd is not None:
                    try:
                        try:
                            existing, digest, object_identity = _ordinary_v2_read_submission(
                                submission_fd,
                                plan_ref=plan_ref,
                                capture_cycle_id=capture_cycle_id,
                                role=role,
                            )
                        except CaptureError as exc:
                            if exc.reason_code != "followup_ordinary_v2_submission_missing":
                                raise
                        else:
                            if (
                                existing["prepared_receipt_content_sha256"] != receipt["receipt_content_sha256"]
                                or existing["prepared_receipt_object_identity"] != receipt["receipt_object_identity"]
                            ):
                                raise CaptureError(
                                    "followup_ordinary_v2_submission_prepared_receipt_drift",
                                    "ordinary submission is not bound to the current prepared receipt",
                                )
                            return {
                                "schema_version": ORDINARY_V2_SUBMISSION_ACK_SCHEMA,
                                "state": "already_submitted",
                                "reason_code": "ordinary_v2_submission_exact_replay",
                                "plan_ref": plan_ref,
                                "capture_cycle_id": capture_cycle_id,
                                "role": role,
                                "submission_path": object_identity["path"],
                                "submission_sha256": digest,
                                "submission_object_identity": object_identity,
                            }
                    finally:
                        os.close(submission_fd)
            # Validate the compact payload against the current terminal source and
            # baseline before a role-local slot can be published.  The later bind
            # repeats these checks against the exact prepared receipt, but a
            # malformed row or non-plan.v2 source must not leave a seemingly
            # usable producer carrier behind for Manager to observe.
            input_fd: int | None = None
            try:
                if input_current:
                    input_fd = _ordinary_v2_open_input_directory(
                        cycle_fd,
                        plan_ref=plan_ref,
                        cycle_id=capture_cycle_id,
                        create=False,
                    )
                    raw_input = _ordinary_v2_read_current_input(
                        input_fd,
                        plan_ref=plan_ref,
                        capture_cycle_id=capture_cycle_id,
                        role=role,
                    )
                    compact = _ordinary_v2_validate_compact_declaration(_ordinary_v2_strict_json_object(raw_input), role)
                assert compact is not None
                current, _contents = snapshot_followups(project_root)
                validate_v2_declaration(
                    project_root,
                    plan_ref,
                    _ordinary_v2_declaration(source, current, compact),
                )
                carrier = _ordinary_v2_submission_carrier(
                    plan_ref=plan_ref,
                    capture_cycle_id=capture_cycle_id,
                    role=role,
                    receipt=receipt,
                    compact=compact,
                )
                submission_fd = _ordinary_v2_open_submission_directory(
                    cycle_fd,
                    plan_ref=plan_ref,
                    cycle_id=capture_cycle_id,
                    create=True,
                )
                try:
                    path, digest, object_identity, created = _ordinary_v2_write_submission(
                        submission_fd,
                        plan_ref=plan_ref,
                        capture_cycle_id=capture_cycle_id,
                        role=role,
                        carrier=carrier,
                    )
                finally:
                    os.close(submission_fd)
                # The canonical submission is the commit point.  Do not unlink
                # a producer-controlled pathname after publish: POSIX has no
                # atomic compare-and-unlink primitive, so retaining this
                # non-authority leaf is safer than a stat-to-unlink race.  A
                # later exact replay reads canonical bytes before this leaf.
                return {
                    "schema_version": ORDINARY_V2_SUBMISSION_ACK_SCHEMA,
                    "state": "submitted" if created else "already_submitted",
                    "reason_code": "ordinary_v2_submission_published" if created else "ordinary_v2_submission_exact_replay",
                    "plan_ref": plan_ref,
                    "capture_cycle_id": capture_cycle_id,
                    "role": role,
                    "submission_path": path,
                    "submission_sha256": digest,
                    "submission_object_identity": object_identity,
                }
            finally:
                if input_fd is not None:
                    os.close(input_fd)
        finally:
            os.close(cycle_fd)


def _ordinary_v2_bound_dir_relpath(plan_ref: str, cycle_id: str) -> str:
    _validate_uuid4(cycle_id)
    return f".tmp/followups_capture/{plan_stem(plan_ref)}/{cycle_id}/{ORDINARY_V2_BOUND_DIRECTORY}"


def _ordinary_v2_bound_role_relpath(plan_ref: str, cycle_id: str, role: str) -> str:
    if role not in REQUIRED_ROLES:
        raise CaptureError("followup_ordinary_v2_role_invalid", f"unsupported ordinary compact role: {role!r}")
    return f"{_ordinary_v2_bound_dir_relpath(plan_ref, cycle_id)}/{role}.json"


def _ordinary_v2_open_bound_directory(
    cycle_fd: int,
    *,
    plan_ref: str,
    cycle_id: str,
    create: bool,
) -> int:
    rel_path = _ordinary_v2_bound_dir_relpath(plan_ref, cycle_id)
    try:
        before = os.stat(ORDINARY_V2_BOUND_DIRECTORY, dir_fd=cycle_fd, follow_symlinks=False)
    except FileNotFoundError:
        if not create:
            raise CaptureError("followup_ordinary_v2_bound_family_missing", f"missing ordinary bound directory: {rel_path}")
        try:
            os.mkdir(ORDINARY_V2_BOUND_DIRECTORY, 0o700, dir_fd=cycle_fd)
        except FileExistsError:
            pass
        except OSError as exc:
            raise CaptureError("followup_ordinary_v2_path_unsafe", f"cannot create ordinary bound directory: {exc}") from exc
        try:
            before = os.stat(ORDINARY_V2_BOUND_DIRECTORY, dir_fd=cycle_fd, follow_symlinks=False)
        except OSError as exc:
            raise CaptureError("followup_ordinary_v2_path_unsafe", f"cannot stat ordinary bound directory: {exc}") from exc
    except OSError as exc:
        raise CaptureError("followup_ordinary_v2_path_unsafe", f"cannot stat ordinary bound directory: {exc}") from exc
    if not stat.S_ISDIR(before.st_mode):
        raise CaptureError("followup_ordinary_v2_path_unsafe", f"ordinary bound directory is not plain: {rel_path}")
    flags = os.O_RDONLY | os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(ORDINARY_V2_BOUND_DIRECTORY, flags, dir_fd=cycle_fd)
    except OSError as exc:
        raise CaptureError("followup_ordinary_v2_path_unsafe", f"cannot open ordinary bound directory: {exc}") from exc
    opened = os.fstat(fd)
    if (
        not stat.S_ISDIR(opened.st_mode)
        or _stat_identity(before) != _stat_identity(opened)
    ):
        os.close(fd)
        raise CaptureError("followup_ordinary_v2_path_object_drift", f"ordinary bound directory drifted: {rel_path}")
    if stat.S_IMODE(opened.st_mode) != 0o700:
        os.close(fd)
        raise CaptureError("followup_ordinary_v2_path_unsafe", f"ordinary bound directory mode is not 700: {rel_path}")
    return fd


def _ordinary_v2_write_bound_role(
    bound_fd: int,
    *,
    plan_ref: str,
    cycle_id: str,
    role: str,
    declaration: dict[str, Any],
) -> tuple[str, str]:
    role_name = f"{role}.json"
    rel_path = _ordinary_v2_bound_role_relpath(plan_ref, cycle_id, role)
    try:
        existing = os.stat(role_name, dir_fd=bound_fd, follow_symlinks=False)
    except FileNotFoundError:
        existing = None
    except OSError as exc:
        raise CaptureError("followup_ordinary_v2_path_unsafe", f"cannot stat ordinary role file: {exc}") from exc
    if existing is not None:
        if not stat.S_ISREG(existing.st_mode):
            raise CaptureError("followup_ordinary_v2_path_unsafe", f"ordinary role file is not regular: {rel_path}")
        raise CaptureError("followup_ordinary_v2_bound_role_exists", f"ordinary role file already exists: {rel_path}")
    data = _canonical_json_bytes(declaration) + b"\n"
    temp_name = f".ordinary-bound-role-tmp-{uuid.uuid4()}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    try:
        fd = os.open(temp_name, flags, 0o600, dir_fd=bound_fd)
    except OSError as exc:
        raise CaptureError("followup_ordinary_v2_publish_failed", f"cannot create ordinary role temp file: {exc}") from exc
    try:
        os.fchmod(fd, 0o600)
        _write_all(fd, data)
        os.fsync(fd)
        written = os.fstat(fd)
        if not stat.S_ISREG(written.st_mode) or stat.S_IMODE(written.st_mode) != 0o600 or written.st_size != len(data):
            raise CaptureError("followup_ordinary_v2_publish_failed", "ordinary role temp file is unsafe")
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(temp_name, dir_fd=bound_fd)
        raise
    finally:
        os.close(fd)
    try:
        os.link(temp_name, role_name, src_dir_fd=bound_fd, dst_dir_fd=bound_fd, follow_symlinks=False)
    except FileExistsError as exc:
        raise CaptureError("followup_ordinary_v2_bound_role_exists", f"ordinary role file already exists: {rel_path}") from exc
    except OSError as exc:
        raise CaptureError("followup_ordinary_v2_publish_failed", f"cannot publish ordinary role file: {exc}") from exc
    finally:
        with contextlib.suppress(OSError):
            os.unlink(temp_name, dir_fd=bound_fd)
    try:
        os.fsync(bound_fd)
    except OSError as exc:
        raise CaptureError("followup_ordinary_v2_publish_failed", f"cannot sync ordinary bound directory: {exc}") from exc
    return rel_path, _sha256(data)


def _ordinary_v2_read_bound_role(
    bound_fd: int,
    *,
    plan_ref: str,
    cycle_id: str,
    role: str,
) -> tuple[dict[str, Any], str]:
    role_name = f"{role}.json"
    rel_path = _ordinary_v2_bound_role_relpath(plan_ref, cycle_id, role)
    try:
        before = os.stat(role_name, dir_fd=bound_fd, follow_symlinks=False)
    except OSError as exc:
        raise CaptureError("followup_ordinary_v2_bound_family_invalid", f"cannot stat ordinary role file: {exc}") from exc
    if not stat.S_ISREG(before.st_mode) or stat.S_IMODE(before.st_mode) != 0o600:
        raise CaptureError("followup_ordinary_v2_bound_family_invalid", f"ordinary role file is not a mode-0600 regular file: {rel_path}")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(role_name, flags, dir_fd=bound_fd)
    except OSError as exc:
        raise CaptureError("followup_ordinary_v2_bound_family_invalid", f"cannot open ordinary role file: {exc}") from exc
    try:
        opened = os.fstat(fd)
        if (
            not stat.S_ISREG(opened.st_mode)
            or _stat_identity(before) != _stat_identity(opened)
        ):
            raise CaptureError("followup_ordinary_v2_path_object_drift", f"ordinary role file drifted: {rel_path}")
        raw = _read_fd_all(fd)
        after = os.fstat(fd)
    finally:
        os.close(fd)
    try:
        current = os.stat(role_name, dir_fd=bound_fd, follow_symlinks=False)
    except OSError as exc:
        raise CaptureError("followup_ordinary_v2_path_object_drift", f"ordinary role file disappeared: {rel_path}") from exc
    if (
        len(raw) != before.st_size
        or _stat_identity(before) != _stat_identity(after)
        or _stat_identity(before) != _stat_identity(current)
    ):
        raise CaptureError("followup_ordinary_v2_path_object_drift", f"ordinary role file changed while reading: {rel_path}")
    value = _ordinary_v2_strict_json_object(raw, enforce_compact_limit=False)
    if raw != _canonical_json_bytes(value) + b"\n":
        raise CaptureError("followup_ordinary_v2_bound_family_invalid", f"ordinary role file is not canonical: {rel_path}")
    return value, _sha256(raw)


def _ordinary_v2_validate_terminal_source_identity(
    project_root: Path,
    plan_ref: str,
    receipt: dict[str, Any],
    source_identity: dict[str, str],
    *,
    require_current_head: bool,
) -> dict[str, str]:
    """Validate immutable terminal source identity against the current worktree.

    Binding and freeze require the terminal source to be the current ``HEAD``.
    Post-CAS readback instead reuses the marker-owned terminal source while
    requiring the current committed plan to remain byte-identical to it.
    """

    plan_ref = normalize_plan_ref(plan_ref)
    if set(source_identity) != {
        "plan_ref",
        "source_terminal_commit_oid",
        "source_plan_blob_oid",
        "source_plan_sha256",
    } or source_identity.get("plan_ref") != plan_ref:
        raise CaptureError("followup_ordinary_v2_source_invalid", "ordinary compact source identity is invalid")
    source = _v2_source_identity(
        project_root,
        plan_ref,
        str(source_identity["source_terminal_commit_oid"]),
        str(source_identity["source_plan_blob_oid"]),
    )
    if source != source_identity:
        raise CaptureError("followup_ordinary_v2_source_or_baseline_drift", "ordinary compact source identity drifted")
    worktree_bytes, status_line = _read_plan(project_root, plan_ref)
    committed = _git(project_root, "show", f"{source['source_terminal_commit_oid']}:{plan_ref}").stdout
    if worktree_bytes != committed:
        raise CaptureError("followup_ordinary_v2_source_worktree_drift", "terminal worktree plan bytes differ from the marker source plan blob")
    schemas = [
        match.group("value").strip()
        for line in committed.decode("utf-8", errors="replace").splitlines()
        if (match := PLAN_SCHEMA_VERSION_RE.match(line))
    ]
    if schemas != ["plan.v2"]:
        raise CaptureError(
            "followup_ordinary_v2_plan_schema_invalid",
            "ordinary compact binding requires one committed Schema version: plan.v2 header",
        )
    if (
        receipt.get("plan_sha256") != source["source_plan_sha256"]
        or receipt.get("terminal_status_line") != status_line
    ):
        raise CaptureError("followup_ordinary_v2_source_worktree_drift", "capture receipt terminal identity differs from the marker source plan")
    head = (
        _git(project_root, "rev-parse", "--verify", "HEAD^{commit}")
        .stdout.decode("ascii", errors="replace")
        .strip()
    )
    head_blob = _git(project_root, "rev-parse", "--verify", f"HEAD:{plan_ref}", check=False)
    if (
        head_blob.returncode != 0
        or head_blob.stdout.decode("ascii", errors="replace").strip() != source["source_plan_blob_oid"]
    ):
        raise CaptureError("followup_ordinary_v2_source_or_baseline_drift", "current HEAD plan blob differs from the marker source")
    if require_current_head and head != source["source_terminal_commit_oid"]:
        raise CaptureError("followup_ordinary_v2_source_or_baseline_drift", "ordinary compact binding requires the terminal source to be current HEAD")
    return source


def _ordinary_v2_current_source_identity(
    project_root: Path,
    plan_ref: str,
    receipt: dict[str, Any],
) -> dict[str, str]:
    """Bind ordinary compact input to the current committed terminal plan only."""

    plan_ref = normalize_plan_ref(plan_ref)
    head = _git(project_root, "rev-parse", "--verify", "HEAD^{commit}").stdout.decode("ascii", errors="replace").strip()
    blob = _git(project_root, "rev-parse", "--verify", f"HEAD:{plan_ref}", check=False)
    if blob.returncode != 0:
        raise CaptureError("followup_ordinary_v2_source_invalid", "current HEAD does not contain the requested terminal plan")
    return _ordinary_v2_validate_terminal_source_identity(
        project_root,
        plan_ref,
        receipt,
        _v2_source_identity(
            project_root,
            plan_ref,
            head,
            blob.stdout.decode("ascii", errors="replace").strip(),
        ),
        require_current_head=True,
    )


def _ordinary_v2_declaration(
    source: dict[str, str],
    baseline: dict[str, Any],
    compact: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": V2_DECLARATION_SCHEMA,
        "role": compact["role"],
        "plan_ref": source["plan_ref"],
        "source_terminal_commit_oid": source["source_terminal_commit_oid"],
        "source_plan_blob_oid": source["source_plan_blob_oid"],
        "baseline_followups_snapshot": json.loads(_canonical_json_bytes(baseline).decode("utf-8")),
        "proposed_rows": json.loads(_canonical_json_bytes(compact["proposed_rows"]).decode("utf-8")),
        "role_no_items_reason": compact["role_no_items_reason"],
    }


def _ordinary_v2_validate_marker(
    marker: Any,
    *,
    project_root: Path,
    plan_ref: str,
    cycle_id: str,
    require_frozen: bool = False,
) -> dict[str, Any]:
    if not isinstance(marker, dict):
        raise CaptureError("followup_ordinary_v2_marker_invalid", "ordinary compact marker is missing or not an object")
    required = {
        "state",
        "capture_cycle_id",
        "plan_ref",
        "source_identity",
        "baseline_followups_snapshot_sha256",
        "bound_declarations",
        "frozen_manifest_path",
        "frozen_manifest_sha256",
    }
    if set(marker) != required:
        raise CaptureError("followup_ordinary_v2_marker_invalid", "ordinary compact marker has unknown or missing fields")
    if marker.get("state") not in {"binding", "frozen"} or (require_frozen and marker.get("state") != "frozen"):
        raise CaptureError("followup_ordinary_v2_marker_invalid", "ordinary compact marker state is invalid")
    if marker.get("capture_cycle_id") != cycle_id or marker.get("plan_ref") != plan_ref:
        raise CaptureError("followup_ordinary_v2_marker_invalid", "ordinary compact marker cycle/plan identity mismatch")
    source = marker.get("source_identity")
    if not isinstance(source, dict) or set(source) != {
        "plan_ref",
        "source_terminal_commit_oid",
        "source_plan_blob_oid",
        "source_plan_sha256",
    } or source.get("plan_ref") != plan_ref:
        raise CaptureError("followup_ordinary_v2_marker_invalid", "ordinary compact marker source identity is invalid")
    if not isinstance(marker.get("baseline_followups_snapshot_sha256"), str) or not HEX64_RE.fullmatch(marker["baseline_followups_snapshot_sha256"]):
        raise CaptureError("followup_ordinary_v2_marker_invalid", "ordinary compact marker baseline hash is invalid")
    bound = marker.get("bound_declarations")
    if not isinstance(bound, list) or [item.get("role") for item in bound if isinstance(item, dict)] != list(REQUIRED_ROLES[: len(bound)]):
        raise CaptureError("followup_ordinary_v2_marker_invalid", "ordinary compact marker role order is invalid")
    if len(bound) > len(REQUIRED_ROLES) or any(
        not isinstance(item, dict)
        or set(item) != {"role", "path", "sha256"}
        or item.get("path") != _ordinary_v2_bound_role_relpath(plan_ref, cycle_id, str(item.get("role") or ""))
        or not isinstance(item.get("sha256"), str)
        or not HEX64_RE.fullmatch(str(item.get("sha256")))
        for item in bound
    ):
        raise CaptureError("followup_ordinary_v2_marker_invalid", "ordinary compact marker bound-file proof is invalid")
    manifest_path = marker.get("frozen_manifest_path")
    manifest_hash = marker.get("frozen_manifest_sha256")
    if marker.get("state") == "binding":
        if manifest_path is not None or manifest_hash is not None:
            raise CaptureError("followup_ordinary_v2_marker_invalid", "unfrozen ordinary marker carries a manifest")
    elif (
        manifest_path != v2_frozen_manifest_path(project_root, plan_ref).relative_to(project_root.absolute()).as_posix()
        or not isinstance(manifest_hash, str)
        or not HEX64_RE.fullmatch(manifest_hash)
        or len(bound) != len(REQUIRED_ROLES)
    ):
        raise CaptureError("followup_ordinary_v2_marker_invalid", "frozen ordinary marker manifest proof is invalid")
    return marker


def v2_frozen_manifest_path(project_root: Path, plan_ref: str) -> Path:
    """Canonical transient proof host used by docs-closeout readback."""

    return project_root.absolute() / ".tmp" / "followups_capture" / plan_stem(plan_ref) / "v2_frozen_manifest.json"


def persist_v2_frozen_manifest(project_root: Path, plan_ref: str, manifest: dict[str, Any]) -> str:
    """Atomically persist the Manager-frozen union; it is coordination proof only."""

    target = v2_frozen_manifest_path(project_root, plan_ref)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".v2_frozen_manifest.", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(_canonical_json_bytes(manifest) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    except Exception:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temp_name)
        raise
    return target.relative_to(project_root.absolute()).as_posix()


def v2_external_proof(project_root: Path, frozen_manifest: dict[str, Any]) -> dict[str, Any]:
    """Read back durable V2 rows after apply without inferring truth from prose."""

    try:
        from followups_apply import ApplyError, load_frozen_manifest
        import followups_lint
    except ModuleNotFoundError:  # package import in focused unittest invocation
        from scripts.followups_apply import ApplyError, load_frozen_manifest
        from scripts import followups_lint

    try:
        frozen, rows = load_frozen_manifest(frozen_manifest)
    except ApplyError as exc:
        raise CaptureError("followup_v2_cycle_invalid", str(exc)) from exc
    source = _v2_source_identity(
        project_root,
        str(frozen_manifest.get("plan_ref") or ""),
        str(frozen["source_terminal_commit_oid"]),
        str(frozen["source_plan_blob_oid"]),
    )
    try:
        current, file_bytes = snapshot_followups(project_root, include_bytes=True)
    except CaptureError as exc:
        return {
            "schema_version": V2_PROOF_SCHEMA,
            "state": "external_invalid",
            "reason": "v2_integrity_blocker",
            "proof_rows": [],
            "errors": [f"{exc.reason_code}:{exc}"],
            "expected_owned_tuples": frozen["expected_owned_tuples"],
            "expected_zero_reason": frozen.get("expected_zero_reason"),
            **source,
        }
    inventory = followups_lint._inventory_followups_snapshot(project_root, current, file_bytes)
    if inventory.blockers:
        return {
            "schema_version": V2_PROOF_SCHEMA,
            "state": "external_invalid",
            "reason": "v2_integrity_blocker",
            "proof_rows": [],
            "errors": [finding.render() for finding in inventory.blockers],
            "expected_owned_tuples": frozen["expected_owned_tuples"],
            "expected_zero_reason": frozen.get("expected_zero_reason"),
            **source,
        }
    proof_rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for row in rows:
        parsed = inventory.valid_v2.get(row.followup_path)
        if parsed is None:
            errors.append(f"missing_row_file:{row.followup_path}")
            continue
        matching = [
            item
            for item in parsed.items
            if followups_lint.normalize_source_ref(item.source_ref) == row.tuple[0] and item.item_id == row.tuple[1]
        ]
        if len(matching) != 1 or followups_lint.v2_row_digest(matching[0]) != row.digest:
            errors.append(f"row_digest_or_identity_mismatch:{row.followup_path}#{row.tuple[1]}")
            continue
        proof_rows.append(
            {
                "proof_host": f"{row.followup_path}#{row.tuple[1]}",
                "source_ref": row.tuple[0],
                "item_id": row.tuple[1],
                "tuple_owner": row.owner,
                "declared_row_digest": row.digest,
                "applied_row_digest": row.digest,
                "file_after_sha256": _sha256(file_bytes[row.followup_path]),
                **source,
            }
        )
    expected = frozen["expected_owned_tuples"]
    if not expected:
        state = "external_clean_noop" if not errors else "external_invalid"
    else:
        state = "external_clean" if not errors and len(proof_rows) == len(expected) else "external_invalid"
    return {
        "schema_version": V2_PROOF_SCHEMA,
        "state": state,
        "reason": "exact_v2_tuple_proof" if state.startswith("external_clean") else "missing_or_mismatched_v2_tuple_proof",
        "proof_rows": proof_rows,
        "errors": errors,
        "expected_owned_tuples": expected,
        "expected_zero_reason": frozen.get("expected_zero_reason"),
        **source,
    }


def read_followup_path(project_root: Path, rel_path: str) -> tuple[dict[str, Any], bytes]:
    rel_path = validate_followup_relpath(rel_path)
    followups_dir = _plain_directory(
        project_root.absolute() / "docs" / "followups",
        "followup_capture_path_ancestor_unsafe",
    )
    return _read_regular_path(followups_dir / PurePosixPath(rel_path).name, rel_path)


def _normalize_repo_regular_relpath(raw: str) -> str:
    value = raw.strip()
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or path.as_posix() != value
        or len(path.parts) < 2
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise CaptureError("followup_staging_path_invalid", f"invalid repo-relative staging path: {raw!r}")
    return value


def read_repo_regular_path(project_root: Path, rel_path: str) -> tuple[dict[str, Any], bytes]:
    """Read one explicitly admitted regular repo file without following a leaf link."""
    rel_path = _normalize_repo_regular_relpath(rel_path)
    parts = PurePosixPath(rel_path).parts
    parent = project_root.absolute()
    for name in parts[:-1]:
        parent = _plain_directory(parent / name, "followup_staging_path_ancestor_unsafe")
    return _read_regular_path(parent / parts[-1], rel_path)


def _v2_external_staging_expected_parent(project_root: Path) -> str:
    """Return the attached-HEAD parent that must not already contain a carrier."""

    expected_ref_result = _git(project_root, "symbolic-ref", "-q", "HEAD", check=False)
    if expected_ref_result.returncode != 0:
        raise CaptureError(
            "missing_or_mismatched_v2_tuple_proof",
            "V2 external staging requires an attached HEAD",
        )
    expected_ref = expected_ref_result.stdout.decode("utf-8", errors="replace").strip()
    if not expected_ref.startswith("refs/"):
        raise CaptureError(
            "missing_or_mismatched_v2_tuple_proof",
            "V2 external staging requires a full symbolic ref",
        )
    parent_result = _git(project_root, "rev-parse", "--verify", f"{expected_ref}^{{commit}}", check=False)
    if parent_result.returncode != 0:
        raise CaptureError(
            "missing_or_mismatched_v2_tuple_proof",
            "V2 external staging requires an existing expected-parent commit",
        )
    expected_parent_oid = parent_result.stdout.decode("ascii", errors="replace").strip()
    if not OID_RE.fullmatch(expected_parent_oid):
        raise CaptureError(
            "missing_or_mismatched_v2_tuple_proof",
            "V2 external staging expected-parent OID is malformed",
        )
    head_oid = _git(project_root, "rev-parse", "--verify", "HEAD^{commit}").stdout.decode("ascii", errors="replace").strip()
    if head_oid != expected_parent_oid:
        raise CaptureError(
            "missing_or_mismatched_v2_tuple_proof",
            "V2 external staging HEAD and expected parent disagree",
        )
    return expected_parent_oid


def _v2_external_staging_require_tree_absence(
    project_root: Path,
    tree_oid: str,
    carrier_path: str,
    *,
    label: str,
) -> None:
    raw = _git(project_root, "ls-tree", "-z", tree_oid, "--", carrier_path).stdout
    if any(record for record in raw.split(b"\0")):
        raise CaptureError(
            "missing_or_mismatched_v2_tuple_proof",
            f"V2 carrier is already present in {label}: {carrier_path}",
        )


def v2_external_followup_staging_expectations(
    project_root: Path,
    admitting_plan_ref: str,
    *,
    capture_binding: dict[str, Any],
) -> list[dict[str, Any]]:
    """Freshly derive the one admissible V2 whole-file staging expectation.

    This is deliberately a read-only adapter around the existing frozen-manifest
    parser and sole-writer renderer.  It grants no write authority: callers may
    consume its result only after independently comparing it with the
    docs-closeout projection.
    """

    try:
        from followups_apply import ApplyError, _append_rows, load_frozen_manifest
    except ModuleNotFoundError:  # package import in focused unittest invocation
        from scripts.followups_apply import ApplyError, _append_rows, load_frozen_manifest

    admitting_plan_ref = normalize_plan_ref(admitting_plan_ref)
    if capture_binding.get("plan_ref") != admitting_plan_ref:
        raise CaptureError(
            "missing_or_mismatched_v2_tuple_proof",
            "V2 external staging capture binding plan_ref mismatch",
        )
    created_paths = capture_binding.get("created_paths")
    if not isinstance(created_paths, list) or any(not isinstance(path, str) for path in created_paths):
        raise CaptureError(
            "missing_or_mismatched_v2_tuple_proof",
            "V2 external staging capture binding created_paths is invalid",
        )
    for key in ("capture_cycle_id", "receipt_content_sha256"):
        if not isinstance(capture_binding.get(key), str) or not str(capture_binding[key]).strip():
            raise CaptureError(
                "missing_or_mismatched_v2_tuple_proof",
                f"V2 external staging capture binding lacks {key}",
            )
    if not isinstance(capture_binding.get("receipt_revision"), int) or isinstance(capture_binding.get("receipt_revision"), bool):
        raise CaptureError(
            "missing_or_mismatched_v2_tuple_proof",
            "V2 external staging capture binding lacks receipt_revision",
        )
    if not isinstance(capture_binding.get("receipt_object_identity"), dict):
        raise CaptureError(
            "missing_or_mismatched_v2_tuple_proof",
            "V2 external staging capture binding lacks receipt object identity",
        )

    manifest_path = v2_frozen_manifest_path(project_root, admitting_plan_ref)
    manifest_rel = manifest_path.relative_to(project_root.absolute()).as_posix()
    try:
        manifest_object, manifest_bytes = read_repo_regular_path(project_root, manifest_rel)
        manifest = _load_json_bytes(manifest_bytes, "missing_or_mismatched_v2_tuple_proof")
    except CaptureError as exc:
        raise CaptureError(
            "missing_or_mismatched_v2_tuple_proof",
            f"V2 external staging manifest is not a safe canonical object: {exc}",
        ) from exc
    if manifest_bytes != _canonical_json_bytes(manifest) + b"\n":
        raise CaptureError(
            "missing_or_mismatched_v2_tuple_proof",
            "V2 external staging manifest bytes are not canonical",
        )
    try:
        frozen, rows = load_frozen_manifest(manifest)
    except ApplyError as exc:
        raise CaptureError("missing_or_mismatched_v2_tuple_proof", str(exc)) from exc
    try:
        frozen_plan_ref = normalize_plan_ref(str(frozen.get("plan_ref") or ""))
    except CaptureError as exc:
        raise CaptureError(
            "missing_or_mismatched_v2_tuple_proof",
            f"V2 frozen manifest plan_ref is invalid: {exc}",
        ) from exc
    if frozen_plan_ref != admitting_plan_ref:
        raise CaptureError(
            "missing_or_mismatched_v2_tuple_proof",
            "V2 frozen manifest plan_ref differs from the admitting plan",
        )
    # ``load_frozen_manifest`` has already proved exact expected/proposed tuple
    # coverage.  Bind every member of that union to this admission instead of
    # authenticating a different terminal source through a plan-local manifest.
    for row in rows:
        row_source_ref = row.tuple[0]
        if row_source_ref != admitting_plan_ref and not row_source_ref.startswith(admitting_plan_ref + "#"):
            raise CaptureError(
                "missing_or_mismatched_v2_tuple_proof",
                "V2 frozen row source_ref differs from the admitting plan",
            )
    if not rows:
        raise CaptureError(
            "missing_or_mismatched_v2_tuple_proof",
            "an empty V2 frozen manifest cannot own a carrier",
        )
    carrier_paths = sorted({row.followup_path for row in rows})
    if len(carrier_paths) != 1:
        raise CaptureError(
            "missing_or_mismatched_v2_tuple_proof",
            "V2 external staging requires exactly one carrier path",
        )
    carrier_path = carrier_paths[0]
    if carrier_path in created_paths:
        raise CaptureError(
            "missing_or_mismatched_v2_tuple_proof",
            "a current-cycle ordinary capture path cannot be reclassified as V2 external",
        )

    baseline = frozen.get("baseline_followups_snapshot")
    baseline_sha256 = frozen.get("baseline_followups_snapshot_sha256")
    if not isinstance(baseline, dict) or not isinstance(baseline_sha256, str) or not HEX64_RE.fullmatch(baseline_sha256):
        raise CaptureError(
            "missing_or_mismatched_v2_tuple_proof",
            "V2 frozen manifest baseline identity is invalid",
        )
    if _sha256(_canonical_json_bytes(baseline)) != baseline_sha256 or carrier_path in baseline:
        raise CaptureError(
            "missing_or_mismatched_v2_tuple_proof",
            "V2 carrier baseline absence proof failed",
        )

    source = _v2_source_identity(
        project_root,
        frozen_plan_ref,
        str(frozen.get("source_terminal_commit_oid") or ""),
        str(frozen.get("source_plan_blob_oid") or ""),
    )
    if frozen.get("source_plan_sha256") != source["source_plan_sha256"]:
        raise CaptureError(
            "missing_or_mismatched_v2_tuple_proof",
            "V2 frozen manifest source digest drifted",
        )
    _v2_external_staging_require_tree_absence(
        project_root,
        source["source_terminal_commit_oid"],
        carrier_path,
        label="source terminal commit",
    )
    expected_parent_oid = _v2_external_staging_expected_parent(project_root)
    _v2_external_staging_require_tree_absence(
        project_root,
        expected_parent_oid,
        carrier_path,
        label="current expected-parent tree",
    )

    try:
        carrier_object, carrier_bytes = read_followup_path(project_root, carrier_path)
        canonical_bytes = _append_rows(b"", carrier_path, rows, project_root)
    except (CaptureError, ApplyError) as exc:
        raise CaptureError(
            "missing_or_mismatched_v2_tuple_proof",
            f"V2 external carrier cannot be read/rendered safely: {exc}",
        ) from exc
    if carrier_bytes != canonical_bytes:
        raise CaptureError(
            "missing_or_mismatched_v2_tuple_proof",
            "V2 external carrier bytes differ from the canonical sole-writer render",
        )

    proof = v2_external_proof(project_root, manifest)
    if proof.get("state") != "external_clean" or proof.get("reason") != "exact_v2_tuple_proof":
        raise CaptureError(
            "missing_or_mismatched_v2_tuple_proof",
            "V2 external tuple proof is not non-empty external_clean",
        )
    expected_rows = [
        {
            "source_ref": row.tuple[0],
            "item_id": row.tuple[1],
            "tuple_owner": row.owner,
            "row_digest": row.digest,
        }
        for row in rows
    ]
    expected_rows.sort(key=lambda item: (item["source_ref"], item["item_id"]))
    proof_rows = proof.get("proof_rows")
    if not isinstance(proof_rows, list):
        raise CaptureError("missing_or_mismatched_v2_tuple_proof", "V2 external tuple proof rows are invalid")
    actual_rows = [
        {
            "source_ref": row.get("source_ref"),
            "item_id": row.get("item_id"),
            "tuple_owner": row.get("tuple_owner"),
            "row_digest": row.get("declared_row_digest"),
        }
        for row in proof_rows
        if isinstance(row, dict)
    ]
    actual_rows.sort(key=lambda item: (str(item["source_ref"]), str(item["item_id"])))
    if len(actual_rows) != len(proof_rows) or actual_rows != expected_rows:
        raise CaptureError(
            "missing_or_mismatched_v2_tuple_proof",
            "V2 external tuple proof differs from the frozen row union",
        )

    ownership_proof = {
        "schema_version": V2_EXTERNAL_FOLLOWUP_STAGING_PROOF_SCHEMA,
        "frozen_manifest_path": manifest_rel,
        "frozen_manifest_object": manifest_object,
        "baseline_followups_snapshot_sha256": baseline_sha256,
        "source_identity": source,
        "carrier_path": carrier_path,
        "canonical_render_sha256": _sha256(canonical_bytes),
        "carrier_object": carrier_object,
        "carrier_absence": {
            "baseline": True,
            "source_terminal_commit": True,
            "expected_parent": True,
        },
        "expected_parent_oid": expected_parent_oid,
        "expected_rows": expected_rows,
    }
    expectations = [
        {
            "capture_cycle_id": capture_binding["capture_cycle_id"],
            "receipt_revision": capture_binding["receipt_revision"],
            "receipt_content_sha256": capture_binding["receipt_content_sha256"],
            "receipt_object_identity": capture_binding["receipt_object_identity"],
            "path": carrier_path,
            "ownership_class": "ordinary_followup",
            "expected_object": carrier_object,
            "expected_staged_mode": "100644",
            "ownership_proof": ownership_proof,
        }
    ]

    # Legacy V2 fixtures predate the generated index.  An index-bearing frozen
    # baseline, however, must prove one exact terminal-owner receipt before it
    # can join the same closeout allowance as the raw carrier.
    index_expectation = _terminal_index_refresh_expectation(
        project_root,
        plan_ref=admitting_plan_ref,
        frozen_manifest=manifest,
        capture_cycle_id=str(capture_binding["capture_cycle_id"]),
    )
    if (
        index_expectation is not None
        and FOLLOWUPS_INDEX_PATH in index_expectation["receipt"]["changed_paths"]
    ):
        expectations.append(
            {
                "capture_cycle_id": capture_binding["capture_cycle_id"],
                "receipt_revision": capture_binding["receipt_revision"],
                "receipt_content_sha256": capture_binding["receipt_content_sha256"],
                "receipt_object_identity": capture_binding["receipt_object_identity"],
                "path": index_expectation["path"],
                "ownership_class": "ordinary_followup",
                "expected_object": index_expectation["expected_object"],
                "expected_staged_mode": "100644",
            }
        )
    return sorted(expectations, key=lambda item: str(item["path"]))


def _process_improvement_observed_paths(
    plan_ref: str,
    capture_cycle_id: str | None = None,
) -> list[str]:
    paths = set(_process_improvement_data_paths(plan_ref))
    paths.update(
        process_improvements_collect.capture_receipt_rel_path(
            plan_ref,
            role,
            capture_cycle_id,
        ).as_posix()
        for role in process_improvements_collect.GENERAL_CAPTURE_ROLES
    )
    return sorted(str(path) for path in paths)


def _process_improvement_data_paths(plan_ref: str) -> list[str]:
    return sorted({
        str(process_improvements_collect.backlog_rel_path_for_source_ref(plan_ref)),
        *PI_DERIVED_SURFACE_PATHS,
    })


def _require_canonical_git_worktree(
    project_root: Path,
    *,
    reason_code: str,
    operation: str,
) -> None:
    expected_root = project_root.resolve()
    repo_probe = _git(project_root, "rev-parse", "--is-inside-work-tree", check=False)
    if repo_probe.returncode != 0 or repo_probe.stdout.strip() != b"true":
        raise CaptureError(
            reason_code,
            f"cannot prove canonical Git worktree identity {operation}",
            stderr=repo_probe.stderr.decode("utf-8", errors="replace").strip(),
        )
    top_level_probe = _git(project_root, "rev-parse", "--show-toplevel", check=False)
    if top_level_probe.returncode != 0:
        raise CaptureError(
            reason_code,
            f"cannot resolve canonical Git worktree root {operation}",
            stderr=top_level_probe.stderr.decode("utf-8", errors="replace").strip(),
        )
    actual_root = Path(top_level_probe.stdout.decode("utf-8", errors="replace").strip()).resolve()
    if actual_root != expected_root:
        raise CaptureError(
            reason_code,
            f"Git worktree root does not match canonical project root {operation}",
            expected_project_root=str(expected_root),
            actual_worktree_root=str(actual_root),
        )


def snapshot_dirty_process_improvement_paths(project_root: Path, plan_ref: str) -> list[str]:
    dirty: set[str] = set()
    _require_canonical_git_worktree(
        project_root,
        reason_code="followup_capture_pi_dirty_baseline_failed",
        operation="before process-improvement dirty snapshot",
    )
    commands = (
        ("diff", "--name-only", "-z", "--", "docs/process_improvements"),
        ("diff", "--cached", "--name-only", "-z", "--", "docs/process_improvements"),
        ("ls-files", "--others", "--exclude-standard", "-z", "--", "docs/process_improvements"),
    )
    for args in commands:
        result = _git(project_root, *args, check=False)
        if result.returncode != 0:
            raise CaptureError(
                "followup_capture_pi_dirty_baseline_failed",
                "cannot snapshot process-improvement dirty paths at capture begin",
                git_args=list(args),
                stderr=result.stderr.decode("utf-8", errors="replace").strip(),
            )
        dirty.update(item.decode("utf-8") for item in result.stdout.split(b"\0") if item)
    return sorted(dirty.intersection(_process_improvement_data_paths(plan_ref)))


def snapshot_process_improvement_files(
    project_root: Path,
    plan_ref: str,
    capture_cycle_id: str | None = None,
) -> dict[str, dict[str, Any]]:
    objects: dict[str, dict[str, Any]] = {}
    for rel_path in _process_improvement_observed_paths(plan_ref, capture_cycle_id):
        if not os.path.lexists(project_root.absolute() / rel_path):
            continue
        obj, _data = read_repo_regular_path(project_root, rel_path)
        objects[rel_path] = obj
    return objects


def snapshot_process_improvement_data_files(project_root: Path, plan_ref: str) -> dict[str, dict[str, Any]]:
    """Return only data objects that may become exact PI staging authority."""
    objects: dict[str, dict[str, Any]] = {}
    for rel_path in _process_improvement_data_paths(plan_ref):
        if not os.path.lexists(project_root.absolute() / rel_path):
            continue
        obj, _data = read_repo_regular_path(project_root, rel_path)
        objects[rel_path] = obj
    return {path: objects[path] for path in sorted(objects)}


def _validate_pi_object(path: str, value: Any, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CaptureError("followup_capture_pi_lineage_invalid", f"{field} entry must be an object: {path}")
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
        or set(value) != {"sha256", "file_type", "st_size"}
    ):
        raise CaptureError("followup_capture_pi_lineage_invalid", f"invalid exact PI object: {field}[{path!r}]")
    return {"sha256": sha256, "file_type": file_type, "st_size": st_size}


def _validate_pi_object_map(value: Any, plan_ref: str, *, field: str) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        raise CaptureError("followup_capture_pi_lineage_invalid", f"{field} must be an object map")
    allowed = set(_process_improvement_data_paths(plan_ref))
    keys = list(value)
    if keys != sorted(keys) or any(not isinstance(path, str) or path not in allowed for path in keys):
        raise CaptureError("followup_capture_pi_lineage_invalid", f"{field} paths must be exact sorted PI data paths")
    return {path: _validate_pi_object(path, value[path], field=field) for path in keys}


def _receipt_pi_lineage(receipt: dict[str, Any], *, require_terminal: bool = False) -> dict[str, Any]:
    """Validate the exact PI lineage fields without reconstructing live ownership."""
    plan_ref = str(receipt.get("plan_ref") or "")
    cycle_id = str(receipt.get("capture_cycle_id") or "")
    try:
        _validate_uuid4(cycle_id)
    except CaptureError as exc:
        raise CaptureError("followup_capture_pi_lineage_invalid", "receipt cycle identity is invalid") from exc
    required = (
        "pi_lineage_root_cycle_id",
        "pi_adopted_from_cycle_ids",
        "pi_ownership_state",
        "pi_final_objects",
        "pi_failure_checkpoint",
        "current_process_improvement_files",
    )
    missing = [field for field in required if field not in receipt]
    if missing:
        raise CaptureError(
            "followup_capture_pi_lineage_legacy",
            "receipt lacks the exact PI lineage field set and is non-adoptable",
            missing_fields=missing,
        )
    root_cycle_id = receipt.get("pi_lineage_root_cycle_id")
    if not isinstance(root_cycle_id, str):
        raise CaptureError("followup_capture_pi_lineage_invalid", "pi_lineage_root_cycle_id must be a UUIDv4")
    try:
        _validate_uuid4(root_cycle_id)
    except CaptureError as exc:
        raise CaptureError("followup_capture_pi_lineage_invalid", "pi_lineage_root_cycle_id must be a UUIDv4") from exc
    adopted = receipt.get("pi_adopted_from_cycle_ids")
    if (
        not isinstance(adopted, list)
        or any(not isinstance(item, str) for item in adopted)
        or adopted != list(dict.fromkeys(adopted))
        or cycle_id in adopted
    ):
        raise CaptureError("followup_capture_pi_lineage_invalid", "pi_adopted_from_cycle_ids must be an ordered unique non-self list")
    try:
        for item in adopted:
            _validate_uuid4(item)
    except CaptureError as exc:
        raise CaptureError("followup_capture_pi_lineage_invalid", "pi_adopted_from_cycle_ids contains an invalid UUIDv4") from exc
    retry_of = receipt.get("retry_of_capture_cycle_id")
    if retry_of is None:
        if root_cycle_id != cycle_id or adopted:
            raise CaptureError("followup_capture_pi_lineage_invalid", "root cycle must self-identify with an empty adopted chain")
    else:
        if not isinstance(retry_of, str) or not adopted or adopted[-1] != retry_of or root_cycle_id != adopted[0]:
            raise CaptureError("followup_capture_pi_lineage_invalid", "retry lineage must end at its direct predecessor and begin at root")
    ownership_state = receipt.get("pi_ownership_state")
    if ownership_state not in PI_OWNERSHIP_STATES:
        raise CaptureError("followup_capture_pi_lineage_invalid", "pi_ownership_state is invalid")
    final_objects = _validate_pi_object_map(receipt.get("pi_final_objects"), plan_ref, field="pi_final_objects")
    current_objects = _validate_pi_object_map(
        receipt.get("current_process_improvement_files"),
        plan_ref,
        field="current_process_improvement_files",
    )
    checkpoint = receipt.get("pi_failure_checkpoint")
    if checkpoint is not None:
        if not isinstance(checkpoint, dict):
            raise CaptureError("followup_capture_pi_lineage_invalid", "pi_failure_checkpoint must be null or an object")
        role = checkpoint.get("role")
        reason_code = checkpoint.get("reason_code")
        path_objects = _validate_pi_object_map(checkpoint.get("path_objects"), plan_ref, field="pi_failure_checkpoint.path_objects")
        if role not in REQUIRED_ROLES or not isinstance(reason_code, str) or not reason_code:
            raise CaptureError("followup_capture_pi_lineage_invalid", "pi_failure_checkpoint role/reason is invalid")
        if path_objects != final_objects:
            raise CaptureError("followup_capture_pi_lineage_invalid", "pi_failure_checkpoint must exact-match pi_final_objects")
    if ownership_state == "active":
        if checkpoint is not None or final_objects:
            raise CaptureError("followup_capture_pi_lineage_invalid", "active PI ownership cannot publish final objects or a checkpoint")
    elif ownership_state == "finalized":
        if checkpoint is not None or final_objects != current_objects:
            raise CaptureError("followup_capture_pi_lineage_invalid", "finalized PI ownership must exact-match current final objects")
    elif ownership_state == "checkpointed_failure":
        if checkpoint is None or final_objects != current_objects:
            raise CaptureError("followup_capture_pi_lineage_invalid", "checkpointed failure must publish one exact current object map")
    elif ownership_state == "blocked" and checkpoint is not None:
        raise CaptureError("followup_capture_pi_lineage_invalid", "blocked non-adoptable ownership cannot retain a failure checkpoint")
    if require_terminal and ownership_state not in PI_ADOPTABLE_OWNERSHIP_STATES:
        raise CaptureError("followup_capture_pi_lineage_nonadoptable", "receipt PI ownership is not terminal/adoptable")
    return {
        "root_cycle_id": root_cycle_id,
        "adopted_cycle_ids": list(adopted),
        "ownership_state": ownership_state,
        "final_objects": final_objects,
        "current_objects": current_objects,
        "failure_checkpoint": checkpoint,
    }


def _validate_pi_path_results(
    value: Any,
    *,
    plan_ref: str,
    before_objects: dict[str, dict[str, Any]],
    after_objects: dict[str, dict[str, Any]],
) -> None:
    if not isinstance(value, list):
        raise CaptureError("followup_capture_pi_lineage_invalid", "process_improvement_path_results must be a list")
    expected_paths = sorted(path for path in set(before_objects) | set(after_objects) if before_objects.get(path) != after_objects.get(path))
    actual_paths: list[str] = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {"path", "before_object", "after_object"}:
            raise CaptureError("followup_capture_pi_lineage_invalid", "PI path result must be an exact object")
        path = item.get("path")
        if not isinstance(path, str):
            raise CaptureError("followup_capture_pi_lineage_invalid", "PI path result path must be a string")
        actual_paths.append(path)
        for field, expected_object in (
            ("before_object", before_objects.get(path)),
            ("after_object", after_objects.get(path)),
        ):
            actual_object = item.get(field)
            if actual_object is None:
                if expected_object is not None:
                    raise CaptureError("followup_capture_pi_lineage_invalid", f"PI path result {field} unexpectedly null")
            elif _validate_pi_object(path, actual_object, field=f"process_improvement_path_results.{field}") != expected_object:
                raise CaptureError("followup_capture_pi_lineage_invalid", f"PI path result {field} does not match its exact map")
    if actual_paths != expected_paths:
        raise CaptureError("followup_capture_pi_lineage_invalid", "PI path results must exactly cover sorted changed paths")


def _pi_path_results(
    before_objects: dict[str, dict[str, Any]],
    after_objects: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "path": path,
            "before_object": before_objects.get(path),
            "after_object": after_objects.get(path),
        }
        for path in _changed_paths(before_objects, after_objects)
    ]


def _validate_general_pi_checkpoint_marker(
    value: Any,
    *,
    plan_ref: str,
    capture_cycle_id: str,
    current_objects: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Validate the stored aggregate bridge without rereading role receipts."""
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != GENERAL_PI_CHECKPOINT_FIELDS:
        raise CaptureError(
            "followup_capture_pi_general_checkpoint_invalid",
            "general_pi_checkpoint must contain the exact aggregate bridge fields",
        )
    before = _validate_pi_object_map(
        value.get("before_process_improvement_files"),
        plan_ref,
        field="general_pi_checkpoint.before_process_improvement_files",
    )
    after = _validate_pi_object_map(
        value.get("after_process_improvement_files"),
        plan_ref,
        field="general_pi_checkpoint.after_process_improvement_files",
    )
    _validate_pi_path_results(
        value.get("process_improvement_path_results"),
        plan_ref=plan_ref,
        before_objects=before,
        after_objects=after,
    )
    input_receipts = value.get("input_receipts")
    expected_roles = list(process_improvements_collect.GENERAL_CAPTURE_ROLES)
    if not isinstance(input_receipts, list) or len(input_receipts) != len(expected_roles):
        raise CaptureError(
            "followup_capture_pi_general_checkpoint_invalid",
            "general_pi_checkpoint must bind exactly four general collector receipts",
        )
    normalized_inputs: list[dict[str, Any]] = []
    for expected_role, item in zip(expected_roles, input_receipts):
        expected_path = process_improvements_collect.capture_receipt_rel_path(
            plan_ref,
            expected_role,
            capture_cycle_id,
        ).as_posix()
        if (
            not isinstance(item, dict)
            or set(item) != {"role", "path", "object_identity", "content_sha256"}
            or item.get("role") != expected_role
            or item.get("path") != expected_path
        ):
            raise CaptureError(
                "followup_capture_pi_general_checkpoint_invalid",
                "general_pi_checkpoint input receipt identity is not canonical",
            )
        identity = _validate_pi_object(
            expected_path,
            item.get("object_identity"),
            field="general_pi_checkpoint.input_receipts.object_identity",
        )
        content_sha256 = item.get("content_sha256")
        if not isinstance(content_sha256, str) or not HEX64_RE.fullmatch(content_sha256):
            raise CaptureError(
                "followup_capture_pi_general_checkpoint_invalid",
                "general_pi_checkpoint input receipt content digest is invalid",
            )
        if identity["sha256"] != content_sha256:
            raise CaptureError(
                "followup_capture_pi_general_checkpoint_invalid",
                "general_pi_checkpoint input receipt object/content identities disagree",
            )
        normalized_inputs.append(
            {
                "role": expected_role,
                "path": expected_path,
                "object_identity": identity,
                "content_sha256": content_sha256,
            }
        )
    revision = value.get("prior_receipt_revision")
    digest = value.get("prior_receipt_content_sha256")
    published_at = value.get("published_at")
    if (
        not isinstance(revision, int)
        or isinstance(revision, bool)
        or revision < 1
        or not isinstance(digest, str)
        or not HEX64_RE.fullmatch(digest)
        or not isinstance(published_at, str)
        or not published_at
    ):
        raise CaptureError(
            "followup_capture_pi_general_checkpoint_invalid",
            "general_pi_checkpoint revision/digest/timestamp fence is invalid",
        )
    if current_objects is not None and after != current_objects:
        raise CaptureError(
            "followup_capture_pi_general_checkpoint_invalid",
            "general_pi_checkpoint after-map differs from aggregate current PI map",
        )
    return {
        "input_receipts": normalized_inputs,
        "before_process_improvement_files": before,
        "after_process_improvement_files": after,
        "process_improvement_path_results": _pi_path_results(before, after),
        "prior_receipt_revision": revision,
        "prior_receipt_content_sha256": digest,
        "published_at": published_at,
    }


def _general_pi_capture_receipts_proof(
    project_root: Path,
    plan_ref: str,
    capture_cycle_id: str,
    *,
    expected_before: dict[str, dict[str, Any]] | None = None,
    expected_after: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Read the four canonical collector receipts and prove their object chain."""
    _validate_uuid4(capture_cycle_id)
    cursor = expected_before
    input_receipts: list[dict[str, Any]] = []
    role_receipts: list[dict[str, Any]] = []
    for role in process_improvements_collect.GENERAL_CAPTURE_ROLES:
        rel_path = process_improvements_collect.capture_receipt_rel_path(
            plan_ref,
            role,
            capture_cycle_id,
        ).as_posix()
        try:
            object_identity, data = read_repo_regular_path(project_root, rel_path)
        except CaptureError as exc:
            raise CaptureError(
                "followup_capture_pi_general_receipt_missing",
                f"missing or unsafe general collector receipt: {rel_path}",
                role=role,
                path=rel_path,
                source_reason=exc.reason_code,
            ) from exc
        receipt = _load_json_bytes(data, "followup_capture_pi_general_receipt_invalid")
        capture_state = receipt.get("capture_state")
        if capture_state == "blocked":
            raise CaptureError(
                "followup_capture_pi_general_receipt_blocked",
                f"general collector receipt is blocked: {rel_path}",
                role=role,
                path=rel_path,
            )
        if (
            receipt.get("receipt_schema") != process_improvements_collect.CAPTURE_RECEIPT_V2_SCHEMA
            or receipt.get("source_ref") != plan_ref
            or receipt.get("role") != role
            or receipt.get("followups_capture_cycle_id") != capture_cycle_id
            or capture_state not in PI_CAPTURE_CONTINUATION_STATES
            or not isinstance(receipt.get("input_sha256"), str)
            or not HEX64_RE.fullmatch(str(receipt.get("input_sha256") or ""))
        ):
            raise CaptureError(
                "followup_capture_pi_general_receipt_identity_mismatch",
                f"general collector receipt identity/state is invalid: {rel_path}",
                role=role,
                path=rel_path,
            )
        required = {
            "before_process_improvement_files",
            "after_process_improvement_files",
            "process_improvement_path_results",
        }
        missing = sorted(required.difference(receipt))
        if missing:
            raise CaptureError(
                "followup_capture_pi_general_receipt_legacy",
                f"general collector receipt lacks object-chain fields: {rel_path}",
                role=role,
                path=rel_path,
                missing_fields=missing,
            )
        try:
            before = _validate_pi_object_map(
                receipt.get("before_process_improvement_files"),
                plan_ref,
                field=f"general_collector.{role}.before_process_improvement_files",
            )
            after = _validate_pi_object_map(
                receipt.get("after_process_improvement_files"),
                plan_ref,
                field=f"general_collector.{role}.after_process_improvement_files",
            )
            _validate_pi_path_results(
                receipt.get("process_improvement_path_results"),
                plan_ref=plan_ref,
                before_objects=before,
                after_objects=after,
            )
        except CaptureError as exc:
            raise CaptureError(
                "followup_capture_pi_general_receipt_invalid",
                f"general collector receipt object chain is invalid: {rel_path}",
                role=role,
                path=rel_path,
                source_reason=exc.reason_code,
            ) from exc
        changed_paths = _changed_paths(before, after)
        if capture_state in {"clean_noop", "already_tracked"} and changed_paths:
            raise CaptureError(
                "followup_capture_pi_general_receipt_state_effect_mismatch",
                f"{capture_state} collector receipt must not change PI objects: {rel_path}",
                role=role,
                path=rel_path,
                capture_state=capture_state,
                changed_paths=changed_paths,
            )
        if capture_state == "materialized" and not changed_paths:
            raise CaptureError(
                "followup_capture_pi_general_receipt_state_effect_mismatch",
                f"materialized collector receipt must change PI objects: {rel_path}",
                role=role,
                path=rel_path,
                capture_state=capture_state,
            )
        if set(before).difference(after):
            raise CaptureError(
                "followup_capture_pi_general_checkpoint_chain_invalid",
                f"general collector receipt deletes a PI data object: {rel_path}",
                role=role,
                path=rel_path,
            )
        if cursor is None:
            cursor = before
        if before != cursor:
            raise CaptureError(
                "followup_capture_pi_general_checkpoint_chain_invalid",
                f"general collector receipts are not a contiguous object chain at {role}",
                role=role,
                path=rel_path,
            )
        cursor = after
        input_receipts.append(
            {
                "role": role,
                "path": rel_path,
                "object_identity": object_identity,
                "content_sha256": _sha256(data),
            }
        )
        role_receipts.append(receipt)
    assert cursor is not None  # GENERAL_CAPTURE_ROLES is fixed and non-empty.
    live = snapshot_process_improvement_data_files(project_root, plan_ref)
    if expected_after is not None and cursor != expected_after:
        raise CaptureError(
            "followup_capture_pi_general_checkpoint_chain_invalid",
            "general collector chain after-map differs from the aggregate checkpoint marker",
        )
    if cursor != live:
        raise CaptureError(
            "followup_capture_pi_general_checkpoint_live_drift",
            "live PI data map differs from the completed general collector chain",
            expected_paths=sorted(cursor),
            current_paths=sorted(live),
        )
    if live:
        try:
            derived = process_improvements_collect.check_derived_surfaces(project_root)
        except Exception as exc:
            raise CaptureError(
                "followup_capture_pi_general_checkpoint_derived_mismatch",
                f"cannot prove process-improvement derived surfaces: {exc}",
            ) from exc
        if not derived.get("ok"):
            raise CaptureError(
                "followup_capture_pi_general_checkpoint_derived_mismatch",
                "process-improvement derived surfaces are stale",
            )
    return {
        "input_receipts": input_receipts,
        "role_receipts": role_receipts,
        "before_process_improvement_files": expected_before if expected_before is not None else role_receipts[0]["before_process_improvement_files"],
        "after_process_improvement_files": live,
        "process_improvement_path_results": _pi_path_results(
            expected_before if expected_before is not None else role_receipts[0]["before_process_improvement_files"],
            live,
        ),
    }


def general_pi_capture_receipts_proof(
    project_root: Path,
    plan_ref: str,
    capture_cycle_id: str,
) -> dict[str, Any]:
    """Public read-only validator for capture-aware docs-closeout classification."""
    return _general_pi_capture_receipts_proof(project_root, plan_ref, capture_cycle_id)


def general_pi_checkpoint_proof(
    project_root: Path,
    plan_ref: str,
    receipt: dict[str, Any],
) -> dict[str, Any]:
    """Prove that an aggregate marker still binds the live canonical inputs."""
    if "general_pi_checkpoint" not in receipt:
        raise CaptureError(
            "followup_capture_pi_general_checkpoint_legacy",
            "aggregate receipt predates the general-PI checkpoint field",
        )
    current_objects = _validate_pi_object_map(
        receipt.get("current_process_improvement_files"),
        plan_ref,
        field="current_process_improvement_files",
    )
    marker = _validate_general_pi_checkpoint_marker(
        receipt.get("general_pi_checkpoint"),
        plan_ref=plan_ref,
        capture_cycle_id=str(receipt.get("capture_cycle_id") or ""),
        current_objects=current_objects,
    )
    if marker is None:
        raise CaptureError(
            "followup_capture_pi_general_checkpoint_missing",
            "aggregate receipt has not published the required general-PI checkpoint",
        )
    proof = _general_pi_capture_receipts_proof(
        project_root,
        plan_ref,
        str(receipt.get("capture_cycle_id") or ""),
        expected_before=marker["before_process_improvement_files"],
        expected_after=marker["after_process_improvement_files"],
    )
    if (
        marker["input_receipts"] != proof["input_receipts"]
        or marker["process_improvement_path_results"] != proof["process_improvement_path_results"]
    ):
        raise CaptureError(
            "followup_capture_pi_general_checkpoint_input_drift",
            "general-PI checkpoint inputs differ from their canonical receipt identities",
        )
    return {"marker": marker, "collector_proof": proof}


def _validate_pi_role_results(receipt: dict[str, Any]) -> None:
    plan_ref = str(receipt.get("plan_ref") or "")
    role_results = receipt.get("role_results")
    if not isinstance(role_results, dict):
        raise CaptureError("followup_capture_pi_lineage_invalid", "receipt role_results must be an object")
    required_fields = {
        "checkpoint_before_process_improvement_files",
        "prepared_process_improvement_files",
        "checkpoint_after_process_improvement_files",
        "process_improvement_path_results",
    }
    for role, result in role_results.items():
        if role not in REQUIRED_ROLES or not isinstance(result, dict):
            raise CaptureError("followup_capture_pi_lineage_invalid", "receipt role PI result is invalid")
        missing = sorted(required_fields.difference(result))
        if missing:
            raise CaptureError(
                "followup_capture_pi_lineage_legacy",
                "receipt role result lacks the full PI path-object field set",
                role=role,
                missing_fields=missing,
            )
        before_objects = _validate_pi_object_map(
            result.get("checkpoint_before_process_improvement_files"),
            plan_ref,
            field=f"role_results.{role}.checkpoint_before_process_improvement_files",
        )
        prepared_value = result.get("prepared_process_improvement_files")
        after_value = result.get("checkpoint_after_process_improvement_files")
        state = result.get("state")
        if state == "prepared":
            if after_value is not None:
                raise CaptureError("followup_capture_pi_lineage_invalid", "prepared role cannot publish a final PI checkpoint")
            prepared_objects = _validate_pi_object_map(
                prepared_value,
                plan_ref,
                field=f"role_results.{role}.prepared_process_improvement_files",
            )
            _validate_pi_path_results(
                result.get("process_improvement_path_results"),
                plan_ref=plan_ref,
                before_objects=before_objects,
                after_objects=prepared_objects,
            )
            continue
        if state not in {"finalized", "blocked"} or after_value is None:
            raise CaptureError("followup_capture_pi_lineage_invalid", "role PI result state/checkpoint is invalid")
        after_objects = _validate_pi_object_map(
            after_value,
            plan_ref,
            field=f"role_results.{role}.checkpoint_after_process_improvement_files",
        )
        if prepared_value is not None:
            _validate_pi_object_map(
                prepared_value,
                plan_ref,
                field=f"role_results.{role}.prepared_process_improvement_files",
            )
        _validate_pi_path_results(
            result.get("process_improvement_path_results"),
            plan_ref=plan_ref,
            before_objects=before_objects,
            after_objects=after_objects,
        )


def process_improvement_cycle_proof(
    project_root: Path,
    plan_ref: str,
    capture_binding: dict[str, Any],
) -> dict[str, Any]:
    baseline = capture_binding.get("baseline_process_improvement_files")
    if not isinstance(baseline, dict):
        raise CaptureError(
            "followup_staging_pi_cycle_invalid",
            "capture receipt omitted the process-improvement cycle baseline",
        )
    baseline_dirty = capture_binding.get("baseline_dirty_process_improvement_paths")
    if not isinstance(baseline_dirty, list) or any(not isinstance(path, str) for path in baseline_dirty):
        raise CaptureError(
            "followup_staging_pi_cycle_invalid",
            "capture receipt omitted the process-improvement dirty-path baseline",
        )
    lineage = _receipt_pi_lineage(capture_binding, require_terminal=True)
    if lineage["ownership_state"] != "finalized":
        raise CaptureError(
            "followup_staging_pi_cycle_invalid",
            "only a finalized aggregate receipt may authorize exact PI staging",
            pi_ownership_state=lineage["ownership_state"],
        )
    if baseline_dirty:
        raise CaptureError(
            "followup_staging_pi_cycle_invalid",
            "process-improvement paths were already dirty before the lineage root",
            baseline_dirty_paths=sorted(baseline_dirty),
        )
    checkpoint = general_pi_checkpoint_proof(project_root, plan_ref, capture_binding)
    baseline_data = {
        path: value
        for path, value in baseline.items()
        if path in set(_process_improvement_data_paths(plan_ref))
    }
    current = snapshot_process_improvement_data_files(project_root, plan_ref)
    final_objects = lineage["final_objects"]
    if current != final_objects:
        raise CaptureError(
            "followup_staging_pi_cycle_invalid",
            "current PI objects differ from the finalized exact lineage map",
            expected_paths=sorted(final_objects),
            current_paths=sorted(current),
        )
    changed_data_paths = sorted(
        path for path in set(baseline_data) | set(final_objects) if baseline_data.get(path) != final_objects.get(path)
    )
    changed_paths = list(changed_data_paths)
    receipt_paths = [
        process_improvements_collect.capture_receipt_rel_path(
            plan_ref,
            role,
            str(capture_binding["capture_cycle_id"]),
        ).as_posix()
        for role in process_improvements_collect.GENERAL_CAPTURE_ROLES
    ]
    return {
        "capture_cycle_id": capture_binding["capture_cycle_id"],
        "pi_lineage_root_cycle_id": lineage["root_cycle_id"],
        "pi_adopted_from_cycle_ids": lineage["adopted_cycle_ids"],
        "pi_final_objects": final_objects,
        "changed_paths": changed_paths,
        "changed_data_paths": changed_data_paths,
        "receipt_paths": receipt_paths,
        "general_pi_checkpoint": checkpoint["marker"],
    }


def _recovery_replay_pi_ownership_proof(
    project_root: Path,
    plan_ref: str,
    capture_binding: dict[str, Any],
    cycle_proof: dict[str, Any],
) -> dict[str, Any]:
    """Prove the exceptional no-materialization replay without inferring it.

    A recovery-bound successor repeats the four general lanes after its exact
    predecessor already materialized the source-bound PI objects.  Its current
    receipts therefore truthfully carry four ``already_tracked``/empty results.
    That shape is authority only when the immutable recovery binding, source
    identity, predecessor checkpoint, fresh checkpoint, and finalized object
    map all agree.  Ordinary empty unions never enter this branch.
    """
    capture_cycle_id = str(capture_binding.get("capture_cycle_id") or "")
    binding = _validate_blocked_predecessor_recovery_binding(
        capture_binding.get(BLOCKED_PREDECESSOR_RECOVERY_BINDING_KEY),
        plan_ref=plan_ref,
        capture_cycle_id=capture_cycle_id,
    )
    required_profile_keys = {
        "plan_ref",
        "predecessor_capture_cycle_id",
        "predecessor_receipt_sha256",
        "source_terminal_commit_oid",
        "source_plan_blob_oid",
        "source_plan_sha256",
    }
    registry = BLOCKED_PREDECESSOR_RECOVERY_PROFILES
    if not isinstance(registry, dict) or plan_ref not in registry:
        raise CaptureError(
            "followup_staging_pi_ownership_invalid",
            "recovery binding has no registered recovery profile",
        )
    profile = registry[plan_ref]
    if (
        not isinstance(profile, dict)
        or set(profile) != required_profile_keys
        or any(not isinstance(profile.get(key), str) or not profile[key] for key in required_profile_keys)
        or profile.get("plan_ref") != plan_ref
    ):
        raise CaptureError(
            "followup_staging_pi_ownership_invalid",
            "registered recovery profile is malformed",
        )
    for key in required_profile_keys:
        if binding.get(key) != profile[key]:
            raise CaptureError(
                "followup_staging_pi_ownership_invalid",
                "recovery binding differs from the registered recovery profile",
                field=key,
            )

    source_identity = {
        "plan_ref": plan_ref,
        "source_terminal_commit_oid": binding["source_terminal_commit_oid"],
        "source_plan_blob_oid": binding["source_plan_blob_oid"],
        "source_plan_sha256": binding["source_plan_sha256"],
    }
    _ordinary_v2_validate_terminal_source_identity(
        project_root,
        plan_ref,
        capture_binding,
        source_identity,
        require_current_head=True,
    )

    baseline = capture_binding.get("baseline_process_improvement_files")
    current = capture_binding.get("current_process_improvement_files")
    if not isinstance(baseline, dict) or not isinstance(current, dict):
        raise CaptureError(
            "followup_staging_pi_ownership_invalid",
            "recovery successor omitted the PI baseline or current map",
        )
    if (
        _sha256(_canonical_json_bytes(baseline)) != binding["baseline_process_improvement_files_sha256"]
        or _sha256(_canonical_json_bytes(current)) != binding["process_improvement_after_map_sha256"]
    ):
        raise CaptureError(
            "followup_staging_pi_ownership_invalid",
            "recovery successor PI maps differ from its immutable recovery binding",
        )

    final_objects = cycle_proof["pi_final_objects"]
    expected_paths = set(_process_improvement_data_paths(plan_ref))
    if set(final_objects) != expected_paths or current != final_objects:
        raise CaptureError(
            "followup_staging_pi_ownership_invalid",
            "recovery replay finalized objects are not the exact source-bound PI surface",
            expected_paths=sorted(expected_paths),
            final_paths=sorted(final_objects),
        )
    checkpoint = cycle_proof["general_pi_checkpoint"]
    if (
        checkpoint.get("before_process_improvement_files") != final_objects
        or checkpoint.get("after_process_improvement_files") != final_objects
    ):
        raise CaptureError(
            "followup_staging_pi_ownership_invalid",
            "fresh recovery replay checkpoint is not a no-materialization replay of final PI objects",
        )

    with CaptureHost(project_root, plan_ref) as host:
        predecessor_fd, _identity = _open_cycle(host, binding["predecessor_capture_cycle_id"])
        try:
            predecessor, raw, receipt_identity = _read_receipt(
                predecessor_fd,
                plan_ref,
                binding["predecessor_capture_cycle_id"],
            )
            stat_result = os.stat(RECEIPT_NAME, dir_fd=predecessor_fd, follow_symlinks=False)
        finally:
            os.close(predecessor_fd)
        predecessor_object = {"path": receipt_identity["path"], **_followup_object(stat_result, raw)}
        if (
            _sha256(raw) != binding["predecessor_receipt_sha256"]
            or predecessor_object != binding["predecessor_receipt_object_identity"]
            or predecessor.get("state") != "blocked"
            or predecessor.get("reason_code") != "followup_capture_role_order_mismatch"
            or predecessor.get("completed_roles") != []
            or predecessor.get("pi_ownership_state") != "blocked"
            or predecessor.get("pi_final_objects") != {}
            or predecessor.get("pi_failure_checkpoint") is not None
            or predecessor.get(ORDINARY_V2_BINDING_KEY) is not None
            or predecessor.get(BLOCKED_PREDECESSOR_RECOVERY_BINDING_KEY) is not None
            or predecessor.get("semantic_closeout_identity") != binding["semantic_closeout_identity"]
            or predecessor.get("transaction_host_identity") != binding["transaction_host_identity"]
            or predecessor.get("plan_sha256") != binding["source_plan_sha256"]
            or binding["transaction_host_identity"] != host.transaction_host_identity()
        ):
            raise CaptureError(
                "followup_staging_pi_ownership_invalid",
                "immutable blocked predecessor no longer matches the recovery binding",
            )
    predecessor_checkpoint = predecessor.get("general_pi_checkpoint")
    if (
        not isinstance(predecessor_checkpoint, dict)
        or _sha256(_canonical_json_bytes(predecessor_checkpoint)) != binding["general_pi_checkpoint_sha256"]
        or _sha256(_canonical_json_bytes(predecessor.get("baseline_process_improvement_files")))
        != binding["baseline_process_improvement_files_sha256"]
        or _sha256(_canonical_json_bytes(predecessor_checkpoint.get("after_process_improvement_files")))
        != binding["process_improvement_after_map_sha256"]
    ):
        raise CaptureError(
            "followup_staging_pi_ownership_invalid",
            "immutable blocked predecessor checkpoint differs from the recovery binding",
        )
    return binding


def _dirty_process_improvement_backlogs(project_root: Path, expected_backlog: str) -> list[str]:
    dirty: set[str] = set()
    _require_canonical_git_worktree(
        project_root,
        reason_code="followup_capture_pi_general_checkpoint_foreign_backlog_scan_failed",
        operation="before foreign process-improvement backlog scan",
    )
    commands = (
        ("diff", "--name-only", "-z", "--", "docs/process_improvements"),
        ("diff", "--cached", "--name-only", "-z", "--", "docs/process_improvements"),
        ("ls-files", "--others", "--exclude-standard", "-z", "--", "docs/process_improvements"),
    )
    for args in commands:
        result = _git(project_root, *args, check=False)
        if result.returncode != 0:
            raise CaptureError(
                "followup_capture_pi_general_checkpoint_foreign_backlog_scan_failed",
                "cannot scan foreign process-improvement backlog state",
                git_args=list(args),
                stderr=result.stderr.decode("utf-8", errors="replace").strip(),
            )
        dirty.update(item.decode("utf-8") for item in result.stdout.split(b"\0") if item)
    return sorted(
        path
        for path in dirty
        if path.endswith("__process_improvements_backlog.md") and path != expected_backlog
    )


def _require_no_post_checkpoint_foreign_backlogs(project_root: Path, plan_ref: str) -> None:
    expected_backlog = str(process_improvements_collect.backlog_rel_path_for_source_ref(plan_ref))
    try:
        foreign_backlogs = _dirty_process_improvement_backlogs(project_root, expected_backlog)
    except CaptureError as exc:
        raise CaptureError(
            "followup_capture_pi_post_checkpoint_foreign_backlog_scan_failed",
            "cannot prove foreign process-improvement backlog state after the general-PI checkpoint",
            expected_backlog=expected_backlog,
            source_reason=exc.reason_code,
        ) from exc
    if foreign_backlogs:
        raise CaptureError(
            "followup_capture_pi_post_checkpoint_foreign_backlog",
            "foreign process-improvement backlog is dirty after the general-PI checkpoint",
            expected_backlog=expected_backlog,
            foreign_backlog_paths=foreign_backlogs,
        )


def _process_improvement_capture_proof(
    project_root: Path,
    plan_ref: str,
    capture_cycle_id: str,
    *,
    capture_binding: dict[str, Any],
    cycle_proof: dict[str, Any],
) -> dict[str, Any]:
    try:
        general_pi_capture_receipts_proof(project_root, plan_ref, capture_cycle_id)
    except CaptureError as exc:
        raise CaptureError(
            "followup_staging_pi_receipt_invalid",
            "authoritative process-improvement collector chain is invalid",
            source_reason=exc.reason_code,
        ) from exc
    expected_backlog = str(process_improvements_collect.backlog_rel_path_for_source_ref(plan_ref))
    receipt_proofs: list[dict[str, Any]] = []
    backlog_paths: set[str] = set()
    states: set[str] = set()
    receipt_backlogs: list[list[str]] = []
    for role in process_improvements_collect.GENERAL_CAPTURE_ROLES:
        rel_path = process_improvements_collect.capture_receipt_rel_path(
            plan_ref,
            role,
            capture_cycle_id,
        ).as_posix()
        try:
            obj, data = read_repo_regular_path(project_root, rel_path)
            receipt = _load_json_bytes(data, "followup_staging_pi_receipt_invalid")
        except (FileNotFoundError, CaptureError) as exc:
            raise CaptureError(
                "followup_staging_pi_receipt_invalid",
                f"missing or unsafe authoritative process-improvement receipt: {rel_path}",
            ) from exc
        state = str(receipt.get("capture_state") or "")
        if (
            receipt.get("receipt_schema") != process_improvements_collect.CAPTURE_RECEIPT_V2_SCHEMA
            or receipt.get("source_ref") != plan_ref
            or receipt.get("role") != role
            or receipt.get("followups_capture_cycle_id") != capture_cycle_id
            or state not in PI_CAPTURE_CONTINUATION_STATES
            or not isinstance(receipt.get("input_sha256"), str)
            or not HEX64_RE.fullmatch(str(receipt.get("input_sha256") or ""))
        ):
            raise CaptureError(
                "followup_staging_pi_receipt_invalid",
                f"invalid authoritative process-improvement receipt: {rel_path}",
            )
        raw_backlogs = receipt.get("backlog_paths")
        if not isinstance(raw_backlogs, list) or any(not isinstance(item, str) for item in raw_backlogs):
            raise CaptureError(
                "followup_staging_pi_receipt_invalid",
                f"invalid backlog paths in process-improvement receipt: {rel_path}",
            )
        backlog_paths.update(_normalize_repo_regular_relpath(item) for item in raw_backlogs)
        states.add(state)
        receipt_backlogs.append([_normalize_repo_regular_relpath(item) for item in raw_backlogs])
        receipt_proofs.append({"path": rel_path, "expected_object": obj})
    if capture_binding.get(BLOCKED_PREDECESSOR_RECOVERY_BINDING_KEY) is not None:
        if states != {"already_tracked"} or any(backlogs for backlogs in receipt_backlogs):
            raise CaptureError(
                "followup_staging_pi_ownership_invalid",
                "recovery replay receipts are not the exact four-role already-tracked empty chain",
                receipt_backlogs=receipt_backlogs,
                receipt_states=sorted(states),
            )
        binding = _recovery_replay_pi_ownership_proof(
            project_root,
            plan_ref,
            capture_binding,
            cycle_proof,
        )
        return {
            "source_ref": plan_ref,
            "backlog_path": expected_backlog,
            "capture_receipts": receipt_proofs,
            "proof_kind": "recovery_replay",
            "recovery_binding": binding,
        }
    if backlog_paths != {expected_backlog} or not states.intersection({"materialized", "already_tracked"}):
        raise CaptureError(
            "followup_staging_pi_ownership_invalid",
            "process-improvement receipts do not prove the exact current-plan backlog",
            expected_backlog=expected_backlog,
            receipt_backlogs=sorted(backlog_paths),
        )
    return {
        "source_ref": plan_ref,
        "backlog_path": expected_backlog,
        "capture_receipts": receipt_proofs,
        "proof_kind": "ordinary",
    }


def process_improvement_staging_proof(
    project_root: Path,
    plan_ref: str,
    *,
    capture_binding: dict[str, Any],
) -> dict[str, Any]:
    """Build one fail-closed PI ownership proof for closeout and staging."""
    cycle_proof = process_improvement_cycle_proof(project_root, plan_ref, capture_binding)
    proof = _process_improvement_capture_proof(
        project_root,
        plan_ref,
        str(capture_binding["capture_cycle_id"]),
        capture_binding=capture_binding,
        cycle_proof=cycle_proof,
    )
    return {**proof, "cycle_proof": cycle_proof}


def process_improvement_staging_expectations(
    project_root: Path,
    plan_ref: str,
    paths: list[str],
    *,
    capture_binding: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build fresh object expectations from PI receipts and fixed allowed paths."""
    normalized = sorted(_normalize_repo_regular_relpath(path) for path in paths)
    if len(normalized) != len(set(normalized)):
        raise CaptureError("followup_staging_pi_ownership_invalid", "duplicate process-improvement staging paths")
    if not normalized:
        return []
    proof = process_improvement_staging_proof(
        project_root,
        plan_ref,
        capture_binding=capture_binding,
    )
    cycle_proof = proof["cycle_proof"]
    foreign_backlogs = _dirty_process_improvement_backlogs(project_root, proof["backlog_path"])
    if foreign_backlogs:
        raise CaptureError(
            "followup_staging_pi_foreign_delta",
            "foreign process-improvement backlog is dirty during current-plan terminal staging",
            foreign_backlog_paths=foreign_backlogs,
        )
    allowed = {proof["backlog_path"], *PI_DERIVED_SURFACE_PATHS}
    if proof["backlog_path"] not in normalized or not set(normalized).issubset(allowed):
        raise CaptureError(
            "followup_staging_pi_ownership_invalid",
            "process-improvement path set is outside the exact source-bound allowlist",
            allowed_paths=sorted(allowed),
            actual_paths=normalized,
        )
    final_objects = cycle_proof["pi_final_objects"]
    if not set(normalized).issubset(set(final_objects)):
        raise CaptureError(
            "followup_staging_pi_cycle_invalid",
            "process-improvement paths are absent from the finalized exact lineage map",
            final_object_paths=sorted(final_objects),
            actual_paths=normalized,
        )
    backlog_obj, backlog_data = read_repo_regular_path(project_root, proof["backlog_path"])
    try:
        backlog_text = backlog_data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CaptureError("followup_staging_pi_ownership_invalid", "process-improvement backlog is not UTF-8") from exc
    source_refs: list[str] = []
    for line in backlog_text.splitlines():
        match = process_improvements_collect.SOURCE_REF_RE.match(line)
        if not match:
            continue
        value = match.group("value").strip()
        if value.startswith("`") and value.endswith("`") and len(value) >= 2:
            value = value[1:-1].strip()
        source_refs.append(value)
    if source_refs != [plan_ref]:
        raise CaptureError(
            "followup_staging_pi_ownership_invalid",
            "process-improvement backlog does not carry one exact source_ref",
            actual_source_refs=source_refs,
        )
    if set(normalized).intersection(PI_DERIVED_SURFACE_PATHS):
        try:
            derived = process_improvements_collect.check_derived_surfaces(project_root)
        except Exception as exc:
            raise CaptureError(
                "followup_staging_pi_ownership_invalid",
                f"cannot prove process-improvement derived surfaces: {exc}",
            ) from exc
        if not derived.get("ok"):
            raise CaptureError("followup_staging_pi_ownership_invalid", "process-improvement derived surfaces are stale")
    expectations: list[dict[str, Any]] = []
    for path in normalized:
        obj, _data = (backlog_obj, backlog_data) if path == proof["backlog_path"] else read_repo_regular_path(project_root, path)
        if obj != final_objects[path]:
            raise CaptureError(
                "followup_staging_pi_cycle_invalid",
                "current PI object differs from finalized exact lineage map",
                path=path,
            )
        expectations.append(
            {
                "capture_cycle_id": capture_binding["capture_cycle_id"],
                "receipt_revision": capture_binding["receipt_revision"],
                "receipt_content_sha256": capture_binding["receipt_content_sha256"],
                "receipt_object_identity": capture_binding["receipt_object_identity"],
                "path": path,
                "ownership_class": "process_improvement",
                "ownership_proof": {
                    **proof,
                    "cycle_proof": cycle_proof,
                    "allowed_paths": sorted(allowed),
                },
                "expected_object": final_objects[path],
                "expected_staged_mode": "100644",
            }
        )
    return expectations


def _read_plan(project_root: Path, plan_ref: str) -> tuple[bytes, str]:
    plan_ref = normalize_plan_ref(plan_ref)
    path = project_root / plan_ref
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise CaptureError("followup_capture_plan_unreadable", f"cannot read terminal plan: {exc}") from exc
    matches = [line for line in data.decode("utf-8").splitlines() if STATUS_RE.match(line)]
    if len(matches) != 1:
        raise CaptureError("followup_capture_plan_status_invalid", "terminal plan must have exactly one status line")
    status = STATUS_RE.match(matches[0])
    assert status is not None
    if status.group("value").strip().lower() not in {"done", "superseded"}:
        raise CaptureError("followup_capture_plan_status_invalid", "capture requires terminal Done|Superseded plan")
    return data, matches[0]


def _identity_payload(
    *,
    plan_ref: str,
    plan_sha256: str,
    terminal_status_line: str,
    semantic_status: str,
    semantic_status_norm: str,
    semantic_closeout_kind: str,
    required_roles: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": IDENTITY_SCHEMA_VERSION,
        "plan_ref": plan_ref,
        "plan_sha256": plan_sha256,
        "terminal_status_line": terminal_status_line,
        "semantic_status": semantic_status,
        "semantic_status_norm": semantic_status_norm,
        "semantic_closeout_kind": semantic_closeout_kind,
        "required_roles": required_roles,
    }


def _semantic_identity(payload: dict[str, Any]) -> str:
    return _sha256(_canonical_json_bytes(payload))


def _validate_roles(value: Any) -> list[str]:
    if not isinstance(value, list) or value != list(REQUIRED_ROLES):
        raise CaptureError(
            "followup_capture_roles_invalid",
            f"required roles must be exact ordered set {list(REQUIRED_ROLES)!r}",
        )
    return list(REQUIRED_ROLES)


def _validate_begin_payload(payload: dict[str, Any], plan_ref: str) -> tuple[str, str, str]:
    if payload.get("schema") != "docs_closeout_payload.v1" or payload.get("schema_state") != "ok":
        raise CaptureError("followup_capture_begin_payload_invalid", "begin requires a schema-green docs_closeout_payload.v1")
    if payload.get("plan_ref") != plan_ref:
        raise CaptureError("followup_capture_begin_payload_invalid", "docs-closeout plan_ref mismatch")
    fields = tuple(str(payload.get(key) or "").strip() for key in ("semantic_status", "semantic_status_norm", "semantic_closeout_kind"))
    if not all(fields) or fields[1].lower() not in {"done", "superseded"}:
        raise CaptureError("followup_capture_begin_payload_invalid", "docs-closeout semantic identity is incomplete or non-terminal")
    return fields  # type: ignore[return-value]


def _revalidate_bootstrap_admission_before_begin(
    project_root: Path,
    plan_ref: str,
    docs_closeout_payload: dict[str, Any],
) -> None:
    """Consume one docs-closeout bootstrap permission only when it is still exact.

    This check happens before opening the mutable capture host and compares the
    entire derived object rather than trusting a serialized hint from an
    earlier readback. Only a currently ready admission activates this narrow
    path; ordinary callers whose current classifier result is blocked retain
    their existing capture behavior.
    """

    supplied = docs_closeout_payload.get("followups_bootstrap_admission")
    try:
        try:
            from docs_closeout import classify_followups_bootstrap_admission
        except ModuleNotFoundError:
            from scripts.docs_closeout import classify_followups_bootstrap_admission

        current = classify_followups_bootstrap_admission(project_root, plan_ref)
    except Exception as exc:
        raise CaptureError(
            "followup_capture_bootstrap_admission_invalid",
            f"cannot rederive bootstrap admission before capture begin: {exc}",
        ) from exc
    if current.get("state") == "ready":
        if supplied == current:
            return
        raise CaptureError(
            "followup_capture_bootstrap_admission_invalid",
            "bootstrap admission is missing, stale, blocked, or differs from current helper proof",
        )
    if isinstance(supplied, dict) and supplied.get("state") == "ready":
        raise CaptureError(
            "followup_capture_bootstrap_admission_invalid",
            "bootstrap admission is stale, blocked, or differs from current helper proof",
        )


def _revalidate_blocked_predecessor_recovery_before_begin(
    project_root: Path,
    plan_ref: str,
    docs_closeout_payload: dict[str, Any],
    *,
    recovery: bool,
) -> dict[str, Any] | None:
    """Keep blocked predecessor state out of both bare begin and generic retry.

    The classifier is a derived permission only.  A regular begin cannot
    reinterpret any present blocked/non-finalized candidate as an absent
    bootstrap, while the dedicated route compares the entire fresh admission
    before opening a mutable capture host.
    """

    supplied = docs_closeout_payload.get("followups_blocked_predecessor_recovery_admission")
    try:
        try:
            from docs_closeout import classify_followups_blocked_predecessor_recovery
        except ModuleNotFoundError:
            from scripts.docs_closeout import classify_followups_blocked_predecessor_recovery

        current = classify_followups_blocked_predecessor_recovery(project_root, plan_ref)
    except Exception as exc:
        raise CaptureError(
            "followup_capture_blocked_predecessor_recovery_admission_invalid",
            f"cannot rederive blocked predecessor recovery admission before capture begin: {exc}",
        ) from exc
    if recovery:
        if current.get("state") == "ready" and supplied == current:
            return current
        raise CaptureError(
            "followup_capture_blocked_predecessor_recovery_admission_invalid",
            "blocked predecessor recovery admission is missing, stale, or differs from current helper proof",
        )
    if current.get("state") != "not_applicable":
        raise CaptureError(
            "followup_capture_blocked_predecessor_recovery_required",
            "bare begin and generic retry cannot consume a blocked predecessor recovery admission",
            recovery_state=current.get("state"),
            recovery_reason=current.get("reason"),
        )
    return None


def _blocked_predecessor_recovery_binding(
    *,
    plan_ref: str,
    successor_capture_cycle_id: str,
    admission: dict[str, Any],
    predecessor: dict[str, Any],
) -> dict[str, Any]:
    checkpoint = predecessor["general_pi_checkpoint"]
    assert isinstance(checkpoint, dict)
    return {
        "schema": BLOCKED_PREDECESSOR_RECOVERY_BINDING_SCHEMA,
        "plan_ref": plan_ref,
        "successor_capture_cycle_id": successor_capture_cycle_id,
        "predecessor_capture_cycle_id": admission["predecessor_capture_cycle_id"],
        "predecessor_receipt_sha256": admission["predecessor_receipt_sha256"],
        "predecessor_receipt_object_identity": admission["predecessor_receipt_object_identity"],
        "semantic_closeout_identity": admission["semantic_closeout_identity"],
        "transaction_host_identity": admission["transaction_host_identity"],
        "source_terminal_commit_oid": admission["source_terminal_commit_oid"],
        "source_plan_blob_oid": admission["source_plan_blob_oid"],
        "source_plan_sha256": admission["source_plan_sha256"],
        "general_pi_checkpoint_sha256": _sha256(_canonical_json_bytes(checkpoint)),
        "baseline_process_improvement_files_sha256": _sha256(
            _canonical_json_bytes(predecessor["baseline_process_improvement_files"])
        ),
        "process_improvement_after_map_sha256": _sha256(
            _canonical_json_bytes(checkpoint["after_process_improvement_files"])
        ),
        "recovery_admission_sha256": _sha256(_canonical_json_bytes(admission)),
    }


def _validate_blocked_predecessor_recovery_binding(
    value: Any,
    *,
    plan_ref: str,
    capture_cycle_id: str,
) -> dict[str, Any]:
    required = {
        "schema",
        "plan_ref",
        "successor_capture_cycle_id",
        "predecessor_capture_cycle_id",
        "predecessor_receipt_sha256",
        "predecessor_receipt_object_identity",
        "semantic_closeout_identity",
        "transaction_host_identity",
        "source_terminal_commit_oid",
        "source_plan_blob_oid",
        "source_plan_sha256",
        "general_pi_checkpoint_sha256",
        "baseline_process_improvement_files_sha256",
        "process_improvement_after_map_sha256",
        "recovery_admission_sha256",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise CaptureError("followup_capture_blocked_predecessor_recovery_binding_invalid", "recovery binding has unknown or missing fields")
    if (
        value.get("schema") != BLOCKED_PREDECESSOR_RECOVERY_BINDING_SCHEMA
        or value.get("plan_ref") != plan_ref
        or value.get("successor_capture_cycle_id") != capture_cycle_id
    ):
        raise CaptureError("followup_capture_blocked_predecessor_recovery_binding_invalid", "recovery binding identity is invalid")
    for key in (
        "predecessor_capture_cycle_id",
        "predecessor_receipt_sha256",
        "semantic_closeout_identity",
        "source_terminal_commit_oid",
        "source_plan_blob_oid",
        "source_plan_sha256",
        "general_pi_checkpoint_sha256",
        "baseline_process_improvement_files_sha256",
        "process_improvement_after_map_sha256",
        "recovery_admission_sha256",
    ):
        item = value.get(key)
        if not isinstance(item, str) or not item:
            raise CaptureError("followup_capture_blocked_predecessor_recovery_binding_invalid", f"recovery binding {key} is invalid")
    for key in ("predecessor_receipt_object_identity", "transaction_host_identity"):
        if not isinstance(value.get(key), dict):
            raise CaptureError("followup_capture_blocked_predecessor_recovery_binding_invalid", f"recovery binding {key} is invalid")
    return value


def _revalidate_blocked_predecessor_recovery_seed(
    project_root: Path,
    *,
    host: CaptureHost,
    plan_ref: str,
    semantic_identity: str,
    admission: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Re-open the exact predecessor under the host before successor publish."""

    predecessor_cycle_id = admission.get("predecessor_capture_cycle_id")
    if not isinstance(predecessor_cycle_id, str):
        raise CaptureError("followup_capture_blocked_predecessor_recovery_admission_invalid", "recovery admission omits predecessor cycle identity")
    cycle_fd, cycle_identity = _open_cycle(host, predecessor_cycle_id)
    try:
        predecessor, raw, receipt_identity = _read_receipt(cycle_fd, plan_ref, predecessor_cycle_id)
        stat_result = os.stat(RECEIPT_NAME, dir_fd=cycle_fd, follow_symlinks=False)
    finally:
        os.close(cycle_fd)
    actual_object = {"path": receipt_identity["path"], **_followup_object(stat_result, raw)}
    if (
        _sha256(raw) != admission.get("predecessor_receipt_sha256")
        or actual_object != admission.get("predecessor_receipt_object_identity")
        or predecessor.get("semantic_closeout_identity") != semantic_identity
        or predecessor.get("transaction_host_identity") != host.transaction_host_identity()
        or predecessor.get("plan_sha256") != admission.get("source_plan_sha256")
        or predecessor.get("state") != "blocked"
        or predecessor.get("reason_code") != "followup_capture_role_order_mismatch"
        or predecessor.get("completed_roles") != []
        or predecessor.get("pi_ownership_state") != "blocked"
        or predecessor.get("pi_final_objects") != {}
        or predecessor.get("pi_failure_checkpoint") is not None
        or predecessor.get(ORDINARY_V2_BINDING_KEY) is not None
        or predecessor.get(BLOCKED_PREDECESSOR_RECOVERY_BINDING_KEY) is not None
    ):
        raise CaptureError("followup_capture_blocked_predecessor_recovery_predecessor_drift", "blocked predecessor no longer matches the admitted exact topology")
    checkpoint = predecessor.get("general_pi_checkpoint")
    try:
        lineage = _receipt_pi_lineage(predecessor)
        marker = _validate_general_pi_checkpoint_marker(
            checkpoint,
            plan_ref=plan_ref,
            capture_cycle_id=predecessor_cycle_id,
            current_objects=lineage["current_objects"],
        )
    except CaptureError as exc:
        raise CaptureError("followup_capture_blocked_predecessor_recovery_predecessor_drift", "blocked predecessor checkpoint drifted") from exc
    if (
        marker is None
        or predecessor.get("baseline_dirty_process_improvement_paths") != []
        or marker["before_process_improvement_files"] != predecessor.get("baseline_process_improvement_files")
        or marker["after_process_improvement_files"] != lineage["current_objects"]
        or _sha256(_canonical_json_bytes(marker)) != admission.get("general_pi_checkpoint_sha256")
        or _sha256(_canonical_json_bytes(marker["after_process_improvement_files"]))
        != admission.get("process_improvement_after_map_sha256")
    ):
        raise CaptureError("followup_capture_blocked_predecessor_recovery_predecessor_drift", "blocked predecessor checkpoint identity drifted")
    current_pi = snapshot_process_improvement_data_files(project_root, plan_ref)
    if current_pi != marker["after_process_improvement_files"]:
        raise CaptureError("followup_capture_blocked_predecessor_recovery_pi_drift", "current process-improvement map differs from admitted predecessor checkpoint")
    current_followups, _contents = snapshot_followups(project_root)
    if current_followups != predecessor.get("baseline_followup_files"):
        raise CaptureError("followup_capture_blocked_predecessor_recovery_followups_drift", "followups baseline differs from admitted predecessor")
    return predecessor, marker["before_process_improvement_files"], marker["after_process_improvement_files"]


def _receipt_relpath(plan_ref: str, cycle_id: str) -> str:
    return f".tmp/followups_capture/{plan_stem(plan_ref)}/{cycle_id}/{RECEIPT_NAME}"


def _cycle_dir_identity(plan_ref: str, cycle_id: str, st: os.stat_result) -> dict[str, Any]:
    return {
        "path": f".tmp/followups_capture/{plan_stem(plan_ref)}/{cycle_id}",
        "file_type": _file_type(st),
    }


def _receipt_identity(plan_ref: str, cycle_id: str, st: os.stat_result) -> dict[str, Any]:
    return {
        "path": _receipt_relpath(plan_ref, cycle_id),
        "file_type": _file_type(st),
    }


def _set_receipt_digest(receipt: dict[str, Any]) -> dict[str, Any]:
    receipt["receipt_content_sha256"] = receipt_content_sha256(receipt)
    return receipt


def _validate_receipt_object(receipt: dict[str, Any], raw: bytes, *, cycle_id: str, plan_ref: str) -> None:
    if raw != persisted_receipt_bytes(receipt):
        raise CaptureError("followup_capture_receipt_corrupt", "receipt bytes are not canonical full JSON plus one newline")
    if receipt.get("schema_version") != SCHEMA_VERSION:
        raise CaptureError("followup_capture_receipt_corrupt", "unsupported receipt schema")
    if receipt.get("capture_cycle_id") != cycle_id or receipt.get("plan_ref") != plan_ref:
        raise CaptureError("followup_capture_receipt_corrupt", "receipt cycle/plan identity mismatch")
    revision = receipt.get("receipt_revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise CaptureError("followup_capture_receipt_corrupt", "receipt_revision must be a positive integer")
    digest = receipt.get("receipt_content_sha256")
    if not isinstance(digest, str) or not HEX64_RE.fullmatch(digest) or digest != receipt_content_sha256(receipt):
        raise CaptureError("followup_capture_receipt_corrupt", "receipt canonical content digest mismatch")
    identity_payload = receipt.get("identity_payload")
    if not isinstance(identity_payload, dict) or receipt.get("semantic_closeout_identity") != _semantic_identity(identity_payload):
        raise CaptureError("followup_capture_receipt_corrupt", "semantic closeout identity mismatch")
    _validate_roles(receipt.get("required_roles"))
    if not isinstance(receipt.get("baseline_process_improvement_files"), dict):
        raise CaptureError("followup_capture_receipt_corrupt", "receipt omitted process-improvement baseline")
    baseline_dirty = receipt.get("baseline_dirty_process_improvement_paths")
    if not isinstance(baseline_dirty, list) or any(not isinstance(path, str) for path in baseline_dirty):
        raise CaptureError("followup_capture_receipt_corrupt", "receipt omitted process-improvement dirty baseline")
    _receipt_pi_lineage(receipt)
    try:
        _validate_general_pi_format_corrections(receipt)
    except (ValueError, TypeError, KeyError) as exc:
        raise CaptureError("pi_format_correction_carrier_invalid", "malformed correction reservation") from exc
    recovery_binding = receipt.get(BLOCKED_PREDECESSOR_RECOVERY_BINDING_KEY)
    if recovery_binding is not None:
        _validate_blocked_predecessor_recovery_binding(
            recovery_binding,
            plan_ref=plan_ref,
            capture_cycle_id=cycle_id,
        )
    if "general_pi_checkpoint" in receipt:
        _validate_general_pi_checkpoint_marker(
            receipt.get("general_pi_checkpoint"),
            plan_ref=plan_ref,
            capture_cycle_id=cycle_id,
            current_objects=_validate_pi_object_map(
                receipt.get("current_process_improvement_files"),
                plan_ref,
                field="current_process_improvement_files",
            ),
        )
    _validate_pi_role_results(receipt)


def _open_cycle(host: CaptureHost, cycle_id: str) -> tuple[int, dict[str, Any]]:
    _validate_uuid4(cycle_id)
    try:
        before = os.stat(cycle_id, dir_fd=host.family_fd, follow_symlinks=False)
        fd = os.open(cycle_id, os.O_RDONLY | os.O_DIRECTORY, dir_fd=host.family_fd)
    except OSError as exc:
        raise CaptureError("followup_capture_cycle_missing", f"cannot open exact capture cycle: {exc}") from exc
    after = os.fstat(fd)
    identity = _cycle_dir_identity(host.plan_ref, cycle_id, after)
    if not stat.S_ISDIR(before.st_mode) or not stat.S_ISDIR(after.st_mode):
        os.close(fd)
        raise CaptureError("followup_capture_cycle_missing", "capture cycle must be a plain directory")
    return fd, identity


def _read_receipt(cycle_fd: int, plan_ref: str, cycle_id: str) -> tuple[dict[str, Any], bytes, dict[str, Any]]:
    rel_path = _receipt_relpath(plan_ref, cycle_id)
    try:
        first = os.stat(RECEIPT_NAME, dir_fd=cycle_fd, follow_symlinks=False)
        fd = os.open(RECEIPT_NAME, os.O_RDONLY, dir_fd=cycle_fd)
    except OSError as exc:
        raise CaptureError("followup_capture_receipt_corrupt", f"cannot open capture receipt: {exc}") from exc
    try:
        opened = os.fstat(fd)
        identity = _receipt_identity(plan_ref, cycle_id, opened)
        if not stat.S_ISREG(first.st_mode) or not stat.S_ISREG(opened.st_mode):
            raise CaptureError("followup_capture_receipt_corrupt", "capture receipt must be a regular file")
        raw = _read_fd_all(fd)
    finally:
        os.close(fd)
    try:
        receipt = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CaptureError("followup_capture_receipt_corrupt", f"capture receipt JSON is invalid: {exc}") from exc
    if not isinstance(receipt, dict):
        raise CaptureError("followup_capture_receipt_corrupt", "capture receipt must be a JSON object")
    _validate_receipt_object(receipt, raw, cycle_id=cycle_id, plan_ref=plan_ref)
    if receipt.get("receipt_object_identity") != identity:
        raise CaptureError("followup_capture_receipt_corrupt", "capture receipt path/type identity mismatch")
    return receipt, raw, identity


def followups_index_refresh_receipt_relpath(plan_ref: str, cycle_id: str) -> str:
    """Return the transient exact receipt leaf for one ordinary V2 cycle."""

    plan_ref = normalize_plan_ref(plan_ref)
    _validate_uuid4(cycle_id)
    return (
        f".tmp/followups_capture/{plan_stem(plan_ref)}/{cycle_id}/"
        f"{FOLLOWUPS_INDEX_REFRESH_RECEIPT_NAME}"
    )


def _validate_followups_index_refresh_receipt(value: Any, *, plan_ref: str, cycle_id: str) -> dict[str, Any]:
    """Validate the fixed eight-field helper-derived refresh receipt.

    The filename is the schema discriminator.  Keeping the payload to the
    declared eight fields prevents a caller from smuggling an alternate
    manifest/profile identity through a transient sidecar.
    """

    if not isinstance(value, dict):
        raise CaptureError("followups_index_refresh_receipt_invalid", "index refresh receipt must be a JSON object")
    required = {
        "authoritative_followups_manifest_sha256",
        "capture_cycle_id",
        "changed_paths",
        "index_after_sha256",
        "index_before_sha256",
        "owner_id",
        "rendered_summary_sha256",
        "state",
    }
    if set(value) != required:
        raise CaptureError(
            "followups_index_refresh_receipt_invalid",
            "index refresh receipt has unknown or missing fixed fields",
        )
    if value.get("capture_cycle_id") != cycle_id:
        raise CaptureError("followups_index_refresh_receipt_invalid", "index refresh receipt cycle identity mismatches")
    if value.get("owner_id") != FOLLOWUPS_INDEX_REFRESH_OWNER_ID:
        raise CaptureError("followups_index_refresh_receipt_invalid", "index refresh receipt owner is not the terminal writer")
    state = value.get("state")
    if state not in {"updated", "clean_noop"}:
        raise CaptureError("followups_index_refresh_receipt_invalid", "index refresh receipt state is invalid")
    for key in (
        "authoritative_followups_manifest_sha256",
        "index_after_sha256",
        "index_before_sha256",
        "rendered_summary_sha256",
    ):
        raw = value.get(key)
        if not isinstance(raw, str) or not HEX64_RE.fullmatch(raw):
            raise CaptureError("followups_index_refresh_receipt_invalid", f"index refresh receipt {key} is invalid")
    changed_paths = value.get("changed_paths")
    if not isinstance(changed_paths, list) or any(not isinstance(path, str) for path in changed_paths):
        raise CaptureError("followups_index_refresh_receipt_invalid", "index refresh receipt changed_paths is invalid")
    normalized: list[str] = []
    for path in changed_paths:
        if path == FOLLOWUPS_INDEX_PATH:
            normalized.append(path)
            continue
        try:
            normalized.append(validate_followup_relpath(path))
        except CaptureError as exc:
            raise CaptureError(
                "followups_index_refresh_receipt_invalid",
                "index refresh receipt contains an invalid changed path",
            ) from exc
    if normalized != changed_paths or changed_paths != sorted(changed_paths) or len(changed_paths) != len(set(changed_paths)):
        raise CaptureError("followups_index_refresh_receipt_invalid", "index refresh receipt paths must be sorted and unique")
    if state == "updated" and not changed_paths:
        raise CaptureError("followups_index_refresh_receipt_invalid", "updated index refresh receipt lacks changed paths")
    if state == "clean_noop" and changed_paths:
        raise CaptureError("followups_index_refresh_receipt_invalid", "clean index refresh receipt has changed paths")
    return value


def _index_refresh_receipt_object(plan_ref: str, cycle_id: str, st: os.stat_result, raw: bytes) -> dict[str, Any]:
    return {
        "path": followups_index_refresh_receipt_relpath(plan_ref, cycle_id),
        **_followup_object(st, raw),
    }


def _read_followups_index_refresh_receipt(
    cycle_fd: int,
    *,
    plan_ref: str,
    cycle_id: str,
) -> tuple[dict[str, Any], bytes, dict[str, Any]]:
    rel_path = followups_index_refresh_receipt_relpath(plan_ref, cycle_id)
    try:
        before = os.stat(FOLLOWUPS_INDEX_REFRESH_RECEIPT_NAME, dir_fd=cycle_fd, follow_symlinks=False)
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(FOLLOWUPS_INDEX_REFRESH_RECEIPT_NAME, flags, dir_fd=cycle_fd)
    except FileNotFoundError as exc:
        raise CaptureError("followups_index_refresh_receipt_missing", "index refresh receipt is absent", path=rel_path) from exc
    except OSError as exc:
        raise CaptureError("followups_index_refresh_receipt_invalid", f"cannot open index refresh receipt: {exc}", path=rel_path) from exc
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not stat.S_ISREG(opened.st_mode):
            raise CaptureError("followups_index_refresh_receipt_invalid", "index refresh receipt must be regular", path=rel_path)
        if _stat_identity(before) != _stat_identity(opened):
            raise CaptureError("followups_index_refresh_receipt_invalid", "index refresh receipt changed while opening", path=rel_path)
        raw = _read_fd_all(fd)
        after = os.fstat(fd)
    finally:
        os.close(fd)
    try:
        current = os.stat(FOLLOWUPS_INDEX_REFRESH_RECEIPT_NAME, dir_fd=cycle_fd, follow_symlinks=False)
    except OSError as exc:
        raise CaptureError("followups_index_refresh_receipt_invalid", "index refresh receipt disappeared", path=rel_path) from exc
    if (
        len(raw) != before.st_size
        or _stat_identity(before) != _stat_identity(after)
        or _stat_identity(before) != _stat_identity(current)
    ):
        raise CaptureError("followups_index_refresh_receipt_invalid", "index refresh receipt changed while reading", path=rel_path)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CaptureError("followups_index_refresh_receipt_invalid", "index refresh receipt is not valid JSON", path=rel_path) from exc
    value = _validate_followups_index_refresh_receipt(value, plan_ref=plan_ref, cycle_id=cycle_id)
    if raw != _canonical_json_bytes(value) + b"\n":
        raise CaptureError("followups_index_refresh_receipt_invalid", "index refresh receipt is not canonical", path=rel_path)
    return value, raw, _index_refresh_receipt_object(plan_ref, cycle_id, current, raw)


def read_followups_index_refresh_receipt(
    project_root: Path,
    *,
    plan_ref: str,
    capture_cycle_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read one receipt from the existing capture-host family without mutation."""

    plan_ref = normalize_plan_ref(plan_ref)
    with CaptureHost(project_root, plan_ref) as host:
        cycle_fd, _identity = _open_cycle(host, capture_cycle_id)
        try:
            value, _raw, object_value = _read_followups_index_refresh_receipt(
                cycle_fd,
                plan_ref=plan_ref,
                cycle_id=capture_cycle_id,
            )
            return value, object_value
        finally:
            os.close(cycle_fd)


def publish_followups_index_refresh_receipt(
    project_root: Path,
    *,
    plan_ref: str,
    capture_cycle_id: str,
    receipt: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    """Publish one exact transient receipt without replacing a competing writer."""

    plan_ref = normalize_plan_ref(plan_ref)
    receipt = _validate_followups_index_refresh_receipt(receipt, plan_ref=plan_ref, cycle_id=capture_cycle_id)
    data = _canonical_json_bytes(receipt) + b"\n"
    with CaptureHost(project_root, plan_ref) as host:
        cycle_fd, _identity = _open_cycle(host, capture_cycle_id)
        try:
            try:
                existing, _existing_raw, existing_object = _read_followups_index_refresh_receipt(
                    cycle_fd,
                    plan_ref=plan_ref,
                    cycle_id=capture_cycle_id,
                )
            except CaptureError as exc:
                if exc.reason_code != "followups_index_refresh_receipt_missing":
                    raise
            else:
                if existing != receipt:
                    raise CaptureError(
                        "followups_index_refresh_receipt_conflict",
                        "a different index refresh receipt already occupies the exact cycle leaf",
                    )
                return existing, existing_object, False

            temp_name = f".index-refresh-receipt-tmp-{uuid.uuid4()}"
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_CLOEXEC"):
                flags |= os.O_CLOEXEC
            try:
                fd = os.open(temp_name, flags, 0o600, dir_fd=cycle_fd)
            except OSError as exc:
                raise CaptureError("followups_index_refresh_receipt_publish_failed", f"cannot create receipt temp file: {exc}") from exc
            try:
                os.fchmod(fd, 0o600)
                _write_all(fd, data)
                os.fsync(fd)
            finally:
                os.close(fd)
            try:
                os.link(
                    temp_name,
                    FOLLOWUPS_INDEX_REFRESH_RECEIPT_NAME,
                    src_dir_fd=cycle_fd,
                    dst_dir_fd=cycle_fd,
                    follow_symlinks=False,
                )
            except FileExistsError as exc:
                raise CaptureError(
                    "followups_index_refresh_receipt_conflict",
                    "another writer published an index refresh receipt first",
                ) from exc
            except OSError as exc:
                raise CaptureError("followups_index_refresh_receipt_publish_failed", f"cannot publish index refresh receipt: {exc}") from exc
            finally:
                with contextlib.suppress(OSError):
                    os.unlink(temp_name, dir_fd=cycle_fd)
            try:
                os.fsync(cycle_fd)
            except OSError as exc:
                raise CaptureError("followups_index_refresh_receipt_publish_failed", f"cannot sync index refresh receipt: {exc}") from exc
            published, published_raw, published_object = _read_followups_index_refresh_receipt(
                cycle_fd,
                plan_ref=plan_ref,
                cycle_id=capture_cycle_id,
            )
            if published != receipt or published_raw != data:
                raise CaptureError("followups_index_refresh_receipt_publish_failed", "published index refresh receipt drifted")
            return published, published_object, True
        finally:
            os.close(cycle_fd)


def remove_followups_index_refresh_receipt_if_exact(
    project_root: Path,
    *,
    plan_ref: str,
    capture_cycle_id: str,
    receipt: dict[str, Any],
) -> bool:
    """Rollback only this writer's receipt; never unlink a foreign replacement."""

    plan_ref = normalize_plan_ref(plan_ref)
    expected = _validate_followups_index_refresh_receipt(receipt, plan_ref=plan_ref, cycle_id=capture_cycle_id)
    with CaptureHost(project_root, plan_ref) as host:
        cycle_fd, _identity = _open_cycle(host, capture_cycle_id)
        try:
            try:
                current, _raw, _object = _read_followups_index_refresh_receipt(
                    cycle_fd,
                    plan_ref=plan_ref,
                    cycle_id=capture_cycle_id,
                )
            except CaptureError as exc:
                if exc.reason_code == "followups_index_refresh_receipt_missing":
                    return False
                raise
            if current != expected:
                return False
            os.unlink(FOLLOWUPS_INDEX_REFRESH_RECEIPT_NAME, dir_fd=cycle_fd)
            return True
        finally:
            os.close(cycle_fd)


def find_followups_index_refresh_binding(
    project_root: Path,
    frozen_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Derive one current ordinary-V2 binding for the terminal index owner.

    The apply caller receives no cycle selector.  This function instead proves
    the only capture receipt whose frozen marker is the exact canonical
    manifest supplied to the existing terminal writer.
    """

    raw_plan_ref = frozen_manifest.get("plan_ref")
    if not isinstance(raw_plan_ref, str):
        raise CaptureError("followups_index_refresh_binding_invalid", "frozen manifest lacks plan_ref")
    plan_ref = normalize_plan_ref(raw_plan_ref)
    manifest_path = v2_frozen_manifest_path(project_root, plan_ref)
    manifest_rel = manifest_path.relative_to(project_root.absolute()).as_posix()
    try:
        _manifest_object, manifest_bytes = read_repo_regular_path(project_root, manifest_rel)
        persisted_manifest = _load_json_bytes(manifest_bytes, "followups_index_refresh_binding_invalid")
    except CaptureError as exc:
        raise CaptureError("followups_index_refresh_binding_invalid", "canonical frozen manifest is unavailable") from exc
    if manifest_bytes != _canonical_json_bytes(persisted_manifest) + b"\n" or persisted_manifest != dict(frozen_manifest):
        raise CaptureError("followups_index_refresh_binding_invalid", "canonical frozen manifest bytes differ from the apply input")
    manifest_sha256 = _sha256(manifest_bytes)
    source = {
        "plan_ref": plan_ref,
        "source_terminal_commit_oid": frozen_manifest.get("source_terminal_commit_oid"),
        "source_plan_blob_oid": frozen_manifest.get("source_plan_blob_oid"),
        "source_plan_sha256": frozen_manifest.get("source_plan_sha256"),
    }
    if any(not isinstance(value, str) or not value for value in source.values()):
        raise CaptureError("followups_index_refresh_binding_invalid", "frozen manifest source identity is incomplete")
    baseline = frozen_manifest.get("baseline_followups_snapshot")
    if not isinstance(baseline, dict):
        raise CaptureError("followups_index_refresh_binding_invalid", "frozen manifest baseline is invalid")
    if FOLLOWUPS_INDEX_PATH not in baseline:
        raise CaptureError("followups_index_refresh_binding_unavailable", "terminal frozen baseline has no generated followups index")

    candidates: list[dict[str, Any]] = []
    with CaptureHost(project_root, plan_ref) as host:
        try:
            names = sorted(os.listdir(host.family_fd))
        except OSError as exc:
            raise CaptureError("followups_index_refresh_binding_invalid", f"cannot list capture cycles: {exc}") from exc
        for cycle_id in names:
            if UUID4_RE.fullmatch(cycle_id) is None:
                continue
            cycle_fd, _identity = _open_cycle(host, cycle_id)
            try:
                receipt, _raw, _receipt_identity = _read_receipt(cycle_fd, plan_ref, cycle_id)
                marker_value = receipt.get(ORDINARY_V2_BINDING_KEY)
                if marker_value is None:
                    continue
                marker = _ordinary_v2_validate_marker(
                    marker_value,
                    project_root=project_root,
                    plan_ref=plan_ref,
                    cycle_id=cycle_id,
                    require_frozen=False,
                )
                if marker["state"] == "binding":
                    continue
                marker, bound_source, _declarations = _ordinary_v2_load_frozen_binding(
                    project_root,
                    plan_ref=plan_ref,
                    cycle_id=cycle_id,
                    receipt=receipt,
                    cycle_fd=cycle_fd,
                )
                if marker.get("frozen_manifest_path") != manifest_rel or marker.get("frozen_manifest_sha256") != manifest_sha256:
                    raise CaptureError(
                        "followups_index_refresh_binding_invalid",
                        "ordinary capture marker points to a different frozen manifest",
                    )
                if bound_source != source or receipt.get("current_followup_files") != baseline:
                    raise CaptureError(
                        "followups_index_refresh_binding_invalid",
                        "ordinary capture source or baseline differs from the frozen manifest",
                    )
                if receipt.get("state") != "finalized" or receipt.get("completed_roles") != list(REQUIRED_ROLES):
                    raise CaptureError("followups_index_refresh_binding_invalid", "ordinary capture is not finalized")
                candidates.append(
                    {
                        "capture_cycle_id": cycle_id,
                        "plan_ref": plan_ref,
                        "source_identity": bound_source,
                        "baseline_followups_snapshot": baseline,
                        "frozen_manifest_path": manifest_rel,
                        "frozen_manifest_sha256": manifest_sha256,
                    }
                )
            finally:
                os.close(cycle_fd)
    if not candidates:
        raise CaptureError("followups_index_refresh_binding_missing", "no exact ordinary V2 capture binding owns the frozen manifest")
    if len(candidates) != 1:
        raise CaptureError("followups_index_refresh_binding_ambiguous", "more than one ordinary V2 capture binding owns the frozen manifest")
    return candidates[0]


def _terminal_index_refresh_expectation(
    project_root: Path,
    *,
    plan_ref: str,
    frozen_manifest: Mapping[str, Any],
    capture_cycle_id: str,
    current_snapshot: Mapping[str, Any] | None = None,
    current_bytes: Mapping[str, bytes] | None = None,
    index_before_bytes: bytes | None = None,
) -> dict[str, Any] | None:
    """Validate the one terminal-owned generated-index allowance, if enabled.

    The helper is deliberately read-only and takes a caller-selected snapshot
    when one is already open.  Both capture readback and docs-closeout staging
    must consume this exact proof rather than treating a current-looking index
    as authority on its own.
    """

    plan_ref = normalize_plan_ref(plan_ref)
    _validate_uuid4(capture_cycle_id)
    baseline = frozen_manifest.get("baseline_followups_snapshot")
    if not isinstance(baseline, Mapping):
        raise CaptureError("missing_or_mismatched_v2_tuple_proof", "V2 frozen manifest baseline is invalid")
    if FOLLOWUPS_INDEX_PATH not in baseline:
        return None
    index_before = baseline.get(FOLLOWUPS_INDEX_PATH)
    if not isinstance(index_before, Mapping) or not isinstance(index_before.get("sha256"), str):
        raise CaptureError("missing_or_mismatched_v2_tuple_proof", "V2 index refresh baseline before-image is invalid")
    if current_snapshot is None or current_bytes is None:
        current_snapshot, current_bytes = snapshot_followups(project_root, include_bytes=True)
    index_after = current_snapshot.get(FOLLOWUPS_INDEX_PATH)
    index_bytes = current_bytes.get(FOLLOWUPS_INDEX_PATH)
    if not isinstance(index_after, dict) or not isinstance(index_bytes, bytes):
        raise CaptureError("missing_or_mismatched_v2_tuple_proof", "V2 index refresh lacks exact after-image")

    try:
        try:
            import followups_index_rebuild
            import followups_lint
        except ModuleNotFoundError:  # package import in focused unittest invocation
            from scripts import followups_index_rebuild, followups_lint
        source_bytes = {
            path: current_bytes[path]
            for path in sorted(current_bytes)
            if Path(path).name not in followups_lint.FOLLOWUPS_IGNORE
        }
        source_manifest = followups_index_rebuild.authoritative_followups_manifest(source_bytes)
        rendered_index = followups_index_rebuild.render_bound_index(
            project_root,
            source_bytes,
            source_manifest,
            index_bytes if index_before_bytes is None else index_before_bytes,
            promoted_plan_lifecycle=followups_index_rebuild.promoted_plan_lifecycle_manifest(
                project_root,
                source_bytes,
                source_manifest,
            ),
            stamp=followups_index_rebuild.generated_summary_stamp(index_bytes),
        )
    except followups_index_rebuild.BoundIndexInputError as exc:
        raise CaptureError("missing_or_mismatched_v2_tuple_proof", str(exc)) from exc
    if rendered_index.index_bytes != index_bytes:
        raise CaptureError(
            "missing_or_mismatched_v2_tuple_proof",
            "V2 generated followups index differs from its bound-byte renderer output",
        )

    binding = find_followups_index_refresh_binding(project_root, frozen_manifest)
    if binding["capture_cycle_id"] != capture_cycle_id:
        raise CaptureError(
            "missing_or_mismatched_v2_tuple_proof",
            "V2 index refresh binding belongs to a different capture cycle",
        )
    receipt, receipt_object = read_followups_index_refresh_receipt(
        project_root,
        plan_ref=plan_ref,
        capture_cycle_id=capture_cycle_id,
    )
    changed_paths = sorted(
        path
        for path in set(baseline) | set(current_snapshot)
        if baseline.get(path) != current_snapshot.get(path)
    )
    expected_receipt = {
        "authoritative_followups_manifest_sha256": rendered_index.authoritative_followups_manifest_sha256,
        "capture_cycle_id": capture_cycle_id,
        "changed_paths": changed_paths,
        "index_after_sha256": _sha256(index_bytes),
        "index_before_sha256": index_before["sha256"],
        "owner_id": FOLLOWUPS_INDEX_REFRESH_OWNER_ID,
        "rendered_summary_sha256": rendered_index.rendered_summary_sha256,
        "state": "updated" if changed_paths else "clean_noop",
    }
    if receipt != expected_receipt:
        raise CaptureError(
            "missing_or_mismatched_v2_tuple_proof",
            "V2 index refresh receipt differs from the exact bound source/index proof",
        )
    return {
        "path": FOLLOWUPS_INDEX_PATH,
        "expected_object": index_after,
        "receipt": receipt,
        "receipt_object": receipt_object,
    }


def _next_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    next_receipt = json.loads(json.dumps(receipt, ensure_ascii=False))
    next_receipt["receipt_revision"] = receipt["receipt_revision"] + 1
    next_receipt.pop("receipt_content_sha256", None)
    return next_receipt


def _write_all(fd: int, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        written = os.write(fd, data[offset:])
        if written <= 0:
            raise CaptureError("followup_capture_publish_failed", "short write while publishing receipt")
        offset += written


def _publish_mutation(
    host: CaptureHost,
    cycle_fd: int,
    cycle_id: str,
    previous_raw: bytes,
    next_receipt: dict[str, Any],
) -> dict[str, Any]:
    host.verify_host()
    current, current_raw, _identity = _read_receipt(cycle_fd, host.plan_ref, cycle_id)
    del current
    if _sha256(current_raw) != _sha256(previous_raw) or current_raw != previous_raw:
        raise CaptureError("followup_capture_stale_writer", "persisted receipt bytes changed before replace")
    temp_name = f".receipt-tmp-{uuid.uuid4()}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    try:
        fd = os.open(temp_name, flags, 0o600, dir_fd=cycle_fd)
    except OSError as exc:
        raise CaptureError("followup_capture_publish_failed", f"cannot create receipt temp file: {exc}") from exc
    try:
        temp_st = os.fstat(fd)
        next_receipt["receipt_object_identity"] = _receipt_identity(host.plan_ref, cycle_id, temp_st)
        _set_receipt_digest(next_receipt)
        data = persisted_receipt_bytes(next_receipt)
        _write_all(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    try:
        os.replace(temp_name, RECEIPT_NAME, src_dir_fd=cycle_fd, dst_dir_fd=cycle_fd)
        os.fsync(cycle_fd)
    except OSError as exc:
        with contextlib.suppress(OSError):
            os.unlink(temp_name, dir_fd=cycle_fd)
        raise CaptureError("followup_capture_publish_failed", f"cannot atomically replace receipt: {exc}") from exc
    host.verify_host()
    published, published_raw, _ = _read_receipt(cycle_fd, host.plan_ref, cycle_id)
    if published_raw != data or published != next_receipt:
        raise CaptureError("followup_capture_publish_failed", "published receipt differs from complete next revision")
    return published


def _response(receipt: dict[str, Any], *, state: str, reason_code: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "state": state,
        "reason_code": reason_code,
        "capture_cycle_id": receipt["capture_cycle_id"],
        "plan_ref": receipt["plan_ref"],
        "receipt_path": _receipt_relpath(receipt["plan_ref"], receipt["capture_cycle_id"]),
        "receipt_revision": receipt["receipt_revision"],
        "receipt_content_sha256": receipt["receipt_content_sha256"],
        "semantic_closeout_identity": receipt["semantic_closeout_identity"],
    }


def _retry_lineage_from_predecessor(
    host: CaptureHost,
    *,
    plan_ref: str,
    predecessor_cycle_id: str,
    semantic_identity: str,
    current_pi_objects: dict[str, dict[str, Any]],
) -> tuple[str, list[str], dict[str, Any], list[str]]:
    """Return inherited root/prefix only after a side-effect-free exact predecessor check."""
    predecessor_fd, predecessor_identity = _open_cycle(host, predecessor_cycle_id)
    try:
        predecessor, _raw, _receipt_identity_value = _read_receipt(predecessor_fd, plan_ref, predecessor_cycle_id)
    except CaptureError as exc:
        if exc.reason_code == "followup_capture_pi_lineage_legacy":
            raise CaptureError(
                "followup_capture_retry_predecessor_legacy",
                "retry predecessor lacks the full PI lineage contract and is non-adoptable",
                predecessor_cycle_id=predecessor_cycle_id,
            ) from exc
        raise CaptureError(
            "followup_capture_retry_predecessor_invalid",
            "retry predecessor receipt is invalid",
            predecessor_cycle_id=predecessor_cycle_id,
            predecessor_reason=exc.reason_code,
        ) from exc
    finally:
        os.close(predecessor_fd)
    if predecessor.get("cycle_directory_identity") != predecessor_identity:
        raise CaptureError(
            "followup_capture_retry_predecessor_invalid",
            "retry predecessor cycle identity drifted",
            predecessor_cycle_id=predecessor_cycle_id,
        )
    if predecessor.get("semantic_closeout_identity") != semantic_identity:
        raise CaptureError(
            "followup_capture_retry_predecessor_semantic_mismatch",
            "retry predecessor semantic identity does not match the current terminal plan family",
            predecessor_cycle_id=predecessor_cycle_id,
        )
    if predecessor.get("transaction_host_identity") != host.transaction_host_identity():
        raise CaptureError(
            "followup_capture_retry_predecessor_host_mismatch",
            "retry predecessor transaction host does not match the opened capture family",
            predecessor_cycle_id=predecessor_cycle_id,
        )
    if predecessor.get("state") != "finalized" and "general_pi_checkpoint" not in predecessor:
        raise CaptureError(
            "followup_capture_retry_predecessor_legacy",
            "non-terminal retry predecessor predates the general-PI checkpoint field",
            predecessor_cycle_id=predecessor_cycle_id,
        )
    try:
        lineage = _receipt_pi_lineage(predecessor)
    except CaptureError as exc:
        if exc.reason_code == "followup_capture_pi_lineage_legacy":
            raise CaptureError(
                "followup_capture_retry_predecessor_legacy",
                "retry predecessor lacks the full PI lineage contract and is non-adoptable",
                predecessor_cycle_id=predecessor_cycle_id,
            ) from exc
        raise CaptureError(
            "followup_capture_retry_predecessor_invalid",
            "retry predecessor PI lineage is invalid or non-adoptable",
            predecessor_cycle_id=predecessor_cycle_id,
            predecessor_reason=exc.reason_code,
        ) from exc
    baseline_dirty = predecessor.get("baseline_dirty_process_improvement_paths")
    if not isinstance(baseline_dirty, list) or any(not isinstance(path, str) for path in baseline_dirty):
        raise CaptureError(
            "followup_capture_retry_predecessor_invalid",
            "retry predecessor omitted a valid root dirty-path baseline",
            predecessor_cycle_id=predecessor_cycle_id,
        )
    if baseline_dirty:
        raise CaptureError(
            "followup_capture_retry_pre_root_dirt",
            "retry cannot adopt PI ownership when the lineage root began dirty",
            predecessor_cycle_id=predecessor_cycle_id,
            baseline_dirty_paths=sorted(baseline_dirty),
        )
    if lineage["ownership_state"] not in PI_ADOPTABLE_OWNERSHIP_STATES:
        raise CaptureError(
            "followup_capture_retry_predecessor_nonadoptable",
            "retry predecessor PI ownership is not terminal/adoptable",
            predecessor_cycle_id=predecessor_cycle_id,
            pi_ownership_state=lineage["ownership_state"],
        )
    expected_state = "finalized" if lineage["ownership_state"] == "finalized" else "blocked"
    if predecessor.get("state") != expected_state:
        raise CaptureError(
            "followup_capture_retry_predecessor_nonadoptable",
            "retry predecessor receipt state does not match terminal PI ownership",
            predecessor_cycle_id=predecessor_cycle_id,
            predecessor_state=predecessor.get("state"),
            pi_ownership_state=lineage["ownership_state"],
        )
    if current_pi_objects != lineage["final_objects"]:
        raise CaptureError(
            "followup_capture_retry_predecessor_object_drift",
            "fresh PI objects differ from the exact predecessor final map",
            predecessor_cycle_id=predecessor_cycle_id,
            expected_paths=sorted(lineage["final_objects"]),
            current_paths=sorted(current_pi_objects),
        )
    baseline = predecessor.get("baseline_process_improvement_files")
    if not isinstance(baseline, dict):
        raise CaptureError(
            "followup_capture_retry_predecessor_invalid",
            "retry predecessor omitted the root PI baseline",
            predecessor_cycle_id=predecessor_cycle_id,
        )
    _validate_retry_lineage_chain(
        host,
        plan_ref=plan_ref,
        semantic_identity=semantic_identity,
        predecessor_cycle_id=predecessor_cycle_id,
        predecessor=predecessor,
        lineage=lineage,
    )
    return (
        lineage["root_cycle_id"],
        [*lineage["adopted_cycle_ids"], predecessor_cycle_id],
        json.loads(json.dumps(baseline, ensure_ascii=False)),
        list(baseline_dirty),
    )


def _validate_retry_lineage_chain(
    host: CaptureHost,
    *,
    plan_ref: str,
    semantic_identity: str,
    predecessor_cycle_id: str,
    predecessor: dict[str, Any],
    lineage: dict[str, Any],
) -> None:
    """Prove every persisted prefix edge before extending a retry lineage."""
    prefix = list(lineage["adopted_cycle_ids"])
    if not prefix:
        return
    root_cycle_id = prefix[0]
    root_baseline: dict[str, Any] | None = None
    root_dirty: list[str] | None = None
    for index, ancestor_cycle_id in enumerate(prefix):
        try:
            ancestor_fd, ancestor_identity = _open_cycle(host, ancestor_cycle_id)
            try:
                ancestor, _raw, _receipt_identity = _read_receipt(ancestor_fd, plan_ref, ancestor_cycle_id)
            finally:
                os.close(ancestor_fd)
        except CaptureError as exc:
            raise CaptureError(
                "followup_capture_retry_predecessor_invalid",
                "retry predecessor lineage prefix is unreadable or invalid",
                predecessor_cycle_id=predecessor_cycle_id,
                ancestor_cycle_id=ancestor_cycle_id,
                ancestor_reason=exc.reason_code,
            ) from exc
        if ancestor.get("cycle_directory_identity") != ancestor_identity:
            raise CaptureError(
                "followup_capture_retry_predecessor_invalid",
                "retry predecessor lineage prefix cycle identity drifted",
                predecessor_cycle_id=predecessor_cycle_id,
                ancestor_cycle_id=ancestor_cycle_id,
            )
        if ancestor.get("semantic_closeout_identity") != semantic_identity:
            raise CaptureError(
                "followup_capture_retry_predecessor_semantic_mismatch",
                "retry predecessor lineage prefix semantic identity does not match",
                predecessor_cycle_id=predecessor_cycle_id,
                ancestor_cycle_id=ancestor_cycle_id,
            )
        if ancestor.get("transaction_host_identity") != host.transaction_host_identity():
            raise CaptureError(
                "followup_capture_retry_predecessor_host_mismatch",
                "retry predecessor lineage prefix transaction host does not match",
                predecessor_cycle_id=predecessor_cycle_id,
                ancestor_cycle_id=ancestor_cycle_id,
            )
        try:
            ancestor_lineage = _receipt_pi_lineage(ancestor, require_terminal=True)
        except CaptureError as exc:
            raise CaptureError(
                "followup_capture_retry_predecessor_invalid",
                "retry predecessor lineage prefix PI ownership is invalid or non-adoptable",
                predecessor_cycle_id=predecessor_cycle_id,
                ancestor_cycle_id=ancestor_cycle_id,
                ancestor_reason=exc.reason_code,
            ) from exc
        expected_prefix = prefix[:index]
        expected_retry_of = None if index == 0 else prefix[index - 1]
        expected_state = "finalized" if ancestor_lineage["ownership_state"] == "finalized" else "blocked"
        if (
            ancestor_lineage["root_cycle_id"] != root_cycle_id
            or ancestor_lineage["adopted_cycle_ids"] != expected_prefix
            or ancestor.get("retry_of_capture_cycle_id") != expected_retry_of
            or ancestor.get("state") != expected_state
        ):
            raise CaptureError(
                "followup_capture_retry_predecessor_invalid",
                "retry predecessor lineage prefix does not form an exact root-to-predecessor chain",
                predecessor_cycle_id=predecessor_cycle_id,
                ancestor_cycle_id=ancestor_cycle_id,
            )
        ancestor_baseline = ancestor.get("baseline_process_improvement_files")
        ancestor_dirty = ancestor.get("baseline_dirty_process_improvement_paths")
        if not isinstance(ancestor_baseline, dict) or not isinstance(ancestor_dirty, list):
            raise CaptureError(
                "followup_capture_retry_predecessor_invalid",
                "retry predecessor lineage prefix omitted the root PI baseline",
                predecessor_cycle_id=predecessor_cycle_id,
                ancestor_cycle_id=ancestor_cycle_id,
            )
        if root_baseline is None:
            root_baseline = ancestor_baseline
            root_dirty = ancestor_dirty
        elif ancestor_baseline != root_baseline or ancestor_dirty != root_dirty:
            raise CaptureError(
                "followup_capture_retry_predecessor_invalid",
                "retry predecessor lineage prefix did not preserve the root PI baseline",
                predecessor_cycle_id=predecessor_cycle_id,
                ancestor_cycle_id=ancestor_cycle_id,
            )
    if (
        predecessor.get("retry_of_capture_cycle_id") != prefix[-1]
        or predecessor.get("baseline_process_improvement_files") != root_baseline
        or predecessor.get("baseline_dirty_process_improvement_paths") != root_dirty
    ):
        raise CaptureError(
            "followup_capture_retry_predecessor_invalid",
            "retry predecessor did not preserve its verified lineage prefix and root baseline",
            predecessor_cycle_id=predecessor_cycle_id,
        )


def begin_cycle(
    project_root: Path,
    plan_ref: str,
    docs_closeout_payload: dict[str, Any],
    *,
    required_roles: list[str] | None = None,
    retry_of_capture_cycle_id: str | None = None,
    _blocked_predecessor_recovery: bool = False,
) -> dict[str, Any]:
    plan_ref = normalize_plan_ref(plan_ref)
    roles = _validate_roles(required_roles or list(REQUIRED_ROLES))
    semantic_status, semantic_status_norm, semantic_closeout_kind = _validate_begin_payload(docs_closeout_payload, plan_ref)
    plan_bytes, terminal_status_line = _read_plan(project_root, plan_ref)
    plan_hash = _sha256(plan_bytes)
    if semantic_status_norm.lower() not in terminal_status_line.lower():
        raise CaptureError("followup_capture_begin_payload_invalid", "terminal status line and docs-closeout status disagree")
    if retry_of_capture_cycle_id is not None:
        _validate_uuid4(retry_of_capture_cycle_id)
    if _blocked_predecessor_recovery and retry_of_capture_cycle_id is not None:
        raise CaptureError(
            "followup_capture_blocked_predecessor_recovery_invalid",
            "blocked predecessor recovery must begin a fresh root without --retry-of-capture-cycle-id",
        )
    identity_payload = _identity_payload(
        plan_ref=plan_ref,
        plan_sha256=plan_hash,
        terminal_status_line=terminal_status_line,
        semantic_status=semantic_status,
        semantic_status_norm=semantic_status_norm,
        semantic_closeout_kind=semantic_closeout_kind,
        required_roles=roles,
    )
    semantic_identity = _semantic_identity(identity_payload)
    recovery_admission = _revalidate_blocked_predecessor_recovery_before_begin(
        project_root,
        plan_ref,
        docs_closeout_payload,
        recovery=_blocked_predecessor_recovery,
    )
    if not _blocked_predecessor_recovery:
        _revalidate_bootstrap_admission_before_begin(project_root, plan_ref, docs_closeout_payload)
    with CaptureHost(project_root, plan_ref, create=True) as host:
        recovery_predecessor: dict[str, Any] | None = None
        if _blocked_predecessor_recovery:
            # Repeat the full derived-admission readback after the host is open
            # and immediately before a new directory can be published.
            recovery_admission = _revalidate_blocked_predecessor_recovery_before_begin(
                project_root,
                plan_ref,
                docs_closeout_payload,
                recovery=True,
            )
            assert recovery_admission is not None
            recovery_predecessor, pi_baseline, current_pi_objects = _revalidate_blocked_predecessor_recovery_seed(
                project_root,
                host=host,
                plan_ref=plan_ref,
                semantic_identity=semantic_identity,
                admission=recovery_admission,
            )
            pi_lineage_root_cycle_id: str | None = None
            pi_adopted_from_cycle_ids: list[str] = []
            pi_dirty_baseline: list[str] = []
        else:
            current_pi_objects = snapshot_process_improvement_data_files(project_root, plan_ref)
        if not _blocked_predecessor_recovery and retry_of_capture_cycle_id is None:
            pi_lineage_root_cycle_id: str | None = None
            pi_adopted_from_cycle_ids: list[str] = []
            # Per-role collector receipts are current-cycle supporting inputs, not
            # baseline data authority.  In particular, never import a fixed v1
            # receipt into a newly-started explicit capture cycle.
            pi_baseline = snapshot_process_improvement_data_files(project_root, plan_ref)
            pi_dirty_baseline = snapshot_dirty_process_improvement_paths(project_root, plan_ref)
        elif not _blocked_predecessor_recovery:
            (
                pi_lineage_root_cycle_id,
                pi_adopted_from_cycle_ids,
                pi_baseline,
                pi_dirty_baseline,
            ) = _retry_lineage_from_predecessor(
                host,
                plan_ref=plan_ref,
                predecessor_cycle_id=retry_of_capture_cycle_id,
                semantic_identity=semantic_identity,
                current_pi_objects=current_pi_objects,
            )
        baseline, _ = snapshot_followups(project_root)
        for entry in os.listdir(host.family_fd):
            if not UUID4_RE.fullmatch(entry):
                continue
            if entry == retry_of_capture_cycle_id:
                continue
            cycle_fd = None
            try:
                cycle_fd, _ = _open_cycle(host, entry)
                existing, _raw, _identity = _read_receipt(cycle_fd, plan_ref, entry)
            except CaptureError:
                raise
            finally:
                if cycle_fd is not None:
                    os.close(cycle_fd)
            if existing.get("semantic_closeout_identity") == semantic_identity and existing.get("state") == "started":
                raise CaptureError(
                    "followup_capture_ambiguous_cycle",
                    "an active cycle already exists for this semantic closeout identity",
                    capture_cycle_id=entry,
                )
        cycle_id = str(uuid.uuid4())
        if pi_lineage_root_cycle_id is None:
            pi_lineage_root_cycle_id = cycle_id
        recovery_binding = (
            _blocked_predecessor_recovery_binding(
                plan_ref=plan_ref,
                successor_capture_cycle_id=cycle_id,
                admission=recovery_admission,
                predecessor=recovery_predecessor,
            )
            if recovery_admission is not None and recovery_predecessor is not None
            else None
        )
        temp_name = f".capture-tmp-{uuid.uuid4()}"

        os.mkdir(temp_name, 0o700, dir_fd=host.family_fd)
        temp_fd = os.open(temp_name, os.O_RDONLY | os.O_DIRECTORY, dir_fd=host.family_fd)
        try:
            os.fchmod(temp_fd, 0o700)
            cycle_st = os.fstat(temp_fd)
            receipt_fd = os.open(
                RECEIPT_NAME,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=temp_fd,
            )
            try:
                os.fchmod(receipt_fd, 0o600)
                receipt_st = os.fstat(receipt_fd)
                receipt: dict[str, Any] = {
                    "schema_version": SCHEMA_VERSION,
                    "state": "started",
                    "reason_code": "capture_started",
                    "capture_cycle_id": cycle_id,
                    "plan_ref": plan_ref,
                    "plan_sha256": plan_hash,
                    "terminal_status_line": terminal_status_line,
                    "identity_payload": identity_payload,
                    "semantic_closeout_identity": semantic_identity,
                    "receipt_revision": 1,
                    "transaction_host_identity": host.transaction_host_identity(),
                    "cycle_directory_identity": _cycle_dir_identity(plan_ref, cycle_id, cycle_st),
                    "receipt_object_identity": _receipt_identity(plan_ref, cycle_id, receipt_st),
                    "started_at": _utc_now(),
                    "finalized_at": None,
                    "retry_of_capture_cycle_id": retry_of_capture_cycle_id,
                    "required_roles": roles,
                    "completed_roles": [],
                    "created_paths": [],
                    "no_followups_roles": [],
                    "blocked_roles": [],
                    "baseline_followup_files": baseline,
                    "current_followup_files": baseline,
                    "baseline_process_improvement_files": pi_baseline,
                    "baseline_dirty_process_improvement_paths": pi_dirty_baseline,
                    "current_process_improvement_files": current_pi_objects,
                    "pi_lineage_root_cycle_id": pi_lineage_root_cycle_id,
                    "pi_adopted_from_cycle_ids": pi_adopted_from_cycle_ids,
                    "pi_ownership_state": "active",
                    "pi_final_objects": {},
                    "pi_failure_checkpoint": None,
                    "general_pi_checkpoint": None,
                    PI_FORMAT_CORRECTIONS_KEY: {},
                    "role_results": {},
                }
                if recovery_binding is not None:
                    receipt[BLOCKED_PREDECESSOR_RECOVERY_BINDING_KEY] = recovery_binding
                _set_receipt_digest(receipt)
                _write_all(receipt_fd, persisted_receipt_bytes(receipt))
            finally:
                os.close(receipt_fd)
            host.verify_host()
            os.rename(temp_name, cycle_id, src_dir_fd=host.family_fd, dst_dir_fd=host.family_fd)
        except Exception:
            with contextlib.suppress(OSError):
                os.unlink(RECEIPT_NAME, dir_fd=temp_fd)
            with contextlib.suppress(OSError):
                os.rmdir(temp_name, dir_fd=host.family_fd)
            raise
        finally:
            os.close(temp_fd)
        cycle_fd, cycle_identity = _open_cycle(host, cycle_id)
        try:
            published, raw, _ = _read_receipt(cycle_fd, plan_ref, cycle_id)
            del raw
            if published["cycle_directory_identity"] != cycle_identity:
                raise CaptureError("followup_capture_publish_failed", "published cycle identity mismatch")
        finally:
            os.close(cycle_fd)
    return _response(published, state="started", reason_code="capture_started")


def begin_cycle_blocked_predecessor_recovery(
    project_root: Path,
    plan_ref: str,
    docs_closeout_payload: dict[str, Any],
    *,
    required_roles: list[str] | None = None,
) -> dict[str, Any]:
    """Start the one admitted fresh root without relaxing generic retry."""

    return begin_cycle(
        project_root,
        plan_ref,
        docs_closeout_payload,
        required_roles=required_roles,
        _blocked_predecessor_recovery=True,
    )


def _current_plan_identity(project_root: Path, receipt: dict[str, Any]) -> None:
    plan_bytes, status_line = _read_plan(project_root, receipt["plan_ref"])
    if _sha256(plan_bytes) != receipt["plan_sha256"] or status_line != receipt["terminal_status_line"]:
        raise CaptureError("followup_capture_plan_identity_mismatch", "terminal plan bytes/status changed after capture begin")


def admit_active_general_pi_collection(
    project_root: Path,
    plan_ref: str,
    cycle_id: str,
    role: str,
) -> dict[str, Any]:
    """Read-only admission for the one engaged general-collector CLI route."""

    plan_ref = normalize_plan_ref(plan_ref)
    if role not in REQUIRED_ROLES:
        raise CaptureError(
            "followup_capture_pi_general_collection_role_invalid",
            "general PI collection requires one of the four ordinary roles",
            role=role,
        )
    _validate_uuid4(cycle_id)
    with CaptureHost(project_root, plan_ref, create=False) as host:
        cycle_fd, cycle_identity = _open_cycle(host, cycle_id)
        try:
            receipt, _raw, receipt_identity = _read_receipt(cycle_fd, plan_ref, cycle_id)
            if receipt.get("cycle_directory_identity") != cycle_identity:
                raise CaptureError(
                    "followup_capture_host_object_drift",
                    "general PI collection cycle identity changed before admission",
                )
            if receipt.get("transaction_host_identity") != host.transaction_host_identity():
                raise CaptureError(
                    "followup_capture_host_object_drift",
                    "general PI collection host identity changed before admission",
                )
            _current_plan_identity(project_root, receipt)
            if (
                receipt.get("state") != "started"
                or receipt.get("finalized_at") is not None
                or receipt.get("completed_roles") != []
                or receipt.get("role_results") != {}
                or receipt.get("blocked_roles") != []
            ):
                raise CaptureError(
                    "followup_capture_pi_general_collection_phase_closed",
                    "general PI collection is only admissible before followups progress",
                )
            if "general_pi_checkpoint" not in receipt or receipt.get("general_pi_checkpoint") is not None:
                raise CaptureError(
                    "followup_capture_pi_general_collection_checkpoint_closed",
                    "general PI collection is closed after checkpoint publication",
                )
            lineage = _receipt_pi_lineage(receipt)
            if (
                lineage["ownership_state"] != "active"
                or lineage["final_objects"]
                or lineage["failure_checkpoint"] is not None
            ):
                raise CaptureError(
                    "followup_capture_pi_general_collection_state_invalid",
                    "general PI collection requires active empty PI ownership",
                )
            return {
                "plan_ref": plan_ref,
                "capture_cycle_id": cycle_id,
                "role": role,
                "receipt_revision": receipt["receipt_revision"],
                "receipt_object_identity": receipt_identity,
            }
        finally:
            os.close(cycle_fd)


def _validate_general_pi_format_corrections(receipt: dict[str, Any]) -> dict[str, Any] | None:
    """Absent historical carriers remain readable, but never acquire a permit."""
    if PI_FORMAT_CORRECTIONS_KEY not in receipt:
        return None
    records = receipt[PI_FORMAT_CORRECTIONS_KEY]
    if not isinstance(records, dict) or set(records).difference(REQUIRED_ROLES):
        raise CaptureError("pi_format_correction_carrier_invalid", "invalid correction role map")
    keys = {"schema", "project_root", "source_identity", "plan_ref", "capture_cycle_id", "role",
            "reservation_id", "attempts_reserved", "reserved_revision", "original_receipt_path",
            "original_receipt_object", "original_receipt_identity", "original_receipt_utf8",
            "original_receipt_sha256"}
    for role, record in records.items():
        if (not isinstance(record, dict) or set(record) != keys
                or record.get("schema") != PI_FORMAT_CORRECTION_SCHEMA
                or record.get("role") != role or record.get("plan_ref") != receipt["plan_ref"]
                or record.get("capture_cycle_id") != receipt["capture_cycle_id"]
                or type(record.get("attempts_reserved")) is not int or record["attempts_reserved"] != 1
                or type(record.get("reserved_revision")) is not int or record["reserved_revision"] < 2
                or record["reserved_revision"] > receipt["receipt_revision"]
                or record.get("project_root") != receipt["transaction_host_identity"]["project_root"]):
            raise CaptureError("pi_format_correction_carrier_invalid", "invalid correction reservation")
        _validate_uuid4(record["reservation_id"])
        raw_text = record.get("original_receipt_utf8")
        if not isinstance(raw_text, str):
            raise CaptureError("pi_format_correction_carrier_invalid", "original receipt bytes are missing")
        raw = raw_text.encode("utf-8")
        original = _load_json_bytes(raw, "pi_format_correction_carrier_invalid")
        before, after = process_improvements_collect._validate_v2_capture_receipt(
            original, source_ref=receipt["plan_ref"], role=role,
            followups_capture_cycle_id=receipt["capture_cycle_id"])
        path = process_improvements_collect.capture_receipt_rel_path(
            receipt["plan_ref"], role, receipt["capture_cycle_id"]).as_posix()
        identity = record.get("original_receipt_identity")
        source = record.get("source_identity")
        if (original.get("error_type") != "pi_format_error" or original.get("capture_state") != "blocked"
                or before != after or original.get("process_improvement_path_results") != []
                or record.get("original_receipt_path") != path
                or record.get("original_receipt_sha256") != _sha256(raw)
                or record.get("original_receipt_object") != {"sha256": _sha256(raw), "file_type": "regular", "st_size": len(raw)}
                or not isinstance(identity, list) or len(identity) != 6
                or any(type(value) is not int for value in identity)
                or not isinstance(source, dict) or set(source) != {"plan_ref", "source_terminal_commit_oid", "source_plan_blob_oid", "source_plan_sha256"}
                or source.get("plan_ref") != receipt["plan_ref"] or source.get("source_plan_sha256") != receipt["plan_sha256"]
                or any(not OID_RE.fullmatch(str(source.get(key) or "")) for key in ("source_terminal_commit_oid", "source_plan_blob_oid"))):
            raise CaptureError("pi_format_correction_carrier_invalid", "correction original/source binding is invalid")
    if (len({record["reservation_id"] for record in records.values()}) != len(records)
            or sorted(record["reserved_revision"] for record in records.values()) != list(range(2, len(records) + 2))):
        raise CaptureError("pi_format_correction_carrier_invalid", "duplicate or noncontiguous correction reservations")
    return records


def _general_pi_correction_leaf_chain(project_root: Path, receipt: dict[str, Any]) -> dict[str, Any] | None:
    """Prove an ordered green prefix, one typed no-effect leaf and absent suffix."""
    plan_ref, cycle_id = receipt["plan_ref"], receipt["capture_cycle_id"]
    directory = process_improvements_collect.capture_receipt_dir_rel_path(plan_ref, cycle_id)
    with process_improvements_collect._collector_directory(project_root, directory.parts, create=False, context=None) as anchor:
        entries = set(os.listdir(anchor[0])) if anchor is not None else set()
    expected_names = {process_improvements_collect.capture_receipt_rel_path(plan_ref, role, cycle_id).name for role in REQUIRED_ROLES}
    if entries.difference(expected_names):
        raise CaptureError("pi_format_correction_extra_leaf", "unexpected general collector leaf or duplicate carrier")
    cursor = _validate_pi_object_map(receipt["baseline_process_improvement_files"], plan_ref, field="baseline_process_improvement_files")
    inputs: list[dict[str, Any]] = []
    blocked: dict[str, Any] | None = None
    missing = False
    for role in REQUIRED_ROLES:
        path = process_improvements_collect.capture_receipt_rel_path(plan_ref, role, cycle_id)
        loaded = process_improvements_collect._safe_pi_read_capture_receipt_regular(project_root, path)
        if loaded is None:
            missing = True
            continue
        if missing or blocked is not None:
            raise CaptureError("pi_format_correction_prefix_suffix_invalid", "general chain has a gap or a suffix after refusal")
        leaf, raw, observed = loaded
        before, after = process_improvements_collect._validate_v2_capture_receipt(
            leaf, source_ref=plan_ref, role=role, followups_capture_cycle_id=cycle_id)
        if before != cursor or set(before).difference(after):
            raise CaptureError("pi_format_correction_chain_invalid", "general PI prefix is not contiguous")
        state = leaf["capture_state"]
        if state == "blocked":
            if leaf.get("error_type") != "pi_format_error" or before != after or leaf["process_improvement_path_results"] != []:
                raise CaptureError("pi_format_correction_not_typed_no_effect", "refusal is not an exact typed no-effect format error")
            blocked = {"role": role, "path": path.as_posix(), "object": _followup_object(observed, raw),
                       "object_identity": list(_stat_identity(observed)), "sha256": _sha256(raw)}
        elif (state not in PI_CAPTURE_CONTINUATION_STATES
              or (state == "materialized") != bool(_changed_paths(before, after))):
            raise CaptureError("pi_format_correction_prefix_invalid", "general PI prefix is not green")
        inputs.append({"role": role, "path": path.as_posix(), "object": _followup_object(observed, raw),
                       "object_identity": list(_stat_identity(observed)), "sha256": _sha256(raw)})
        cursor = after
    if blocked is None:
        return None
    live = snapshot_process_improvement_data_files(project_root, plan_ref)
    if cursor != live:
        raise CaptureError("pi_format_correction_live_map_drift", "current PI objects differ from the proven chain")
    if live and process_improvements_collect.check_derived_surfaces(project_root).get("ok") is not True:
        raise CaptureError("pi_format_correction_derived_drift", "current derived PI surfaces are stale")
    return {"blocked": blocked, "input_receipts": inputs, "before": receipt["baseline_process_improvement_files"], "after": live}


def general_pi_format_correction_admission(
    project_root: Path, plan_ref: str, cycle_id: str | None, *,
    bundle_payload: dict[str, Any], context: Any = None, _ingest_reservation_id: str | None = None,
) -> dict[str, Any]:
    """Read-only bounded permission; retryable authorizes a reservation request only."""
    result: dict[str, Any] = {"schema": PI_FORMAT_ADMISSION_SCHEMA,
        "state": "blocked" if cycle_id else "not_applicable", "reason": "correction_selector_absent",
        "plan_ref": plan_ref, "capture_cycle_id": cycle_id, "role": None,
        "attempts_reserved": 0, "max_extra_attempts": 1, "next_dispatch": None, "proof": None}
    if not cycle_id:
        return result
    try:
        import docs_closeout
        plan_ref = normalize_plan_ref(plan_ref)
        _validate_uuid4(cycle_id)
        context = docs_closeout._reader_context(project_root, context)
        docs_closeout.validate_before_effect(context)
        oracle = docs_closeout.plan_status_oracle.oracle_result(project_root / plan_ref, context=context)
        review = docs_closeout.plan_lint.preflight_current_review_proof(project_root / plan_ref, project_root=project_root)
        mode = docs_closeout.plan_status_oracle.manager_mode_admission(
            docs_closeout.plan_status_oracle.parse_plan_meta_admission_carrier(oracle.captured_plan_text), "manager-collab")
        if (oracle.status_norm not in docs_closeout.TERMINAL_STATUSES or oracle.route_guard_triggered
                or not oracle.queue_closeout_ready or oracle.owner_qna_readback_state != "clean"
                or review.state == "blocked" or mode["manager_mode_admitted"] is not True
                or bundle_payload.get("plan") != plan_ref or bundle_payload.get("bundle_ok") is not True
                or bundle_payload.get("errors") != [] or bundle_payload.get("closeout_kind") != "already_materialized"):
            raise CaptureError("pi_format_correction_terminal_admission_blocked", "current terminal source/review/bundle is not admitted")
        if os.path.lexists(v2_frozen_manifest_path(project_root, plan_ref)):
            raise CaptureError("pi_format_correction_phase_closed", "ordinary V2 manifest already exists")
        with CaptureHost(project_root, plan_ref, create=False) as host:
            active = []
            for entry in os.listdir(host.family_fd):
                if not UUID4_RE.fullmatch(entry):
                    continue
                fd, identity = _open_cycle(host, entry)
                try:
                    candidate, _, _ = _read_receipt(fd, plan_ref, entry)
                    if candidate["cycle_directory_identity"] != identity or candidate["transaction_host_identity"] != host.transaction_host_identity():
                        raise CaptureError("pi_format_correction_host_drift", "capture host identity changed")
                    if candidate["state"] == "started":
                        active.append(entry)
                finally:
                    os.close(fd)
            if active != [cycle_id]:
                raise CaptureError("pi_format_correction_active_cycle_ambiguous", "one exact current cycle is required")
            fd, cycle_identity = _open_cycle(host, cycle_id)
            try:
                receipt, raw, receipt_identity = _read_receipt(fd, plan_ref, cycle_id)
                _current_plan_identity(project_root, receipt)
                records = _validate_general_pi_format_corrections(receipt)
                if records is None:
                    raise CaptureError("pi_format_correction_legacy_carrier", "correction map is absent; no backfill")
                if (receipt.get("state") != "started" or receipt.get("finalized_at") is not None
                        or receipt.get("completed_roles") != [] or receipt.get("blocked_roles") != []
                        or receipt.get("role_results") != {} or receipt.get("general_pi_checkpoint", "missing") is not None
                        or ORDINARY_V2_BINDING_KEY in receipt or receipt["receipt_revision"] != 1 + len(records)):
                    raise CaptureError("pi_format_correction_phase_closed", "general correction phase is closed")
                for directory in (ORDINARY_V2_BOUND_DIRECTORY, ORDINARY_V2_SUBMISSION_DIRECTORY, ORDINARY_V2_INPUT_DIRECTORY):
                    try:
                        os.stat(directory, dir_fd=fd, follow_symlinks=False)
                    except FileNotFoundError:
                        continue
                    raise CaptureError("pi_format_correction_phase_closed", "followups progress already exists")
                lineage = _receipt_pi_lineage(receipt)
                if (lineage["ownership_state"] != "active" or lineage["final_objects"] or lineage["failure_checkpoint"] is not None
                        or lineage["current_objects"] != receipt["baseline_process_improvement_files"]
                        or receipt["baseline_dirty_process_improvement_paths"] != []):
                    raise CaptureError("pi_format_correction_lineage_invalid", "PI ownership/baseline is not active and clean")
                source = _ordinary_v2_current_source_identity(project_root, plan_ref, receipt)
                if any(record["source_identity"] != source for record in records.values()):
                    raise CaptureError("pi_format_correction_source_drift", "correction slots belong to another terminal source")
                identity = _identity_payload(plan_ref=plan_ref, plan_sha256=source["source_plan_sha256"],
                    terminal_status_line=receipt["terminal_status_line"], semantic_status=oracle.status_value,
                    semantic_status_norm=oracle.status_norm, semantic_closeout_kind="already_materialized", required_roles=list(REQUIRED_ROLES))
                if identity != receipt["identity_payload"]:
                    raise CaptureError("pi_format_correction_source_drift", "current semantic identity differs")
                followups, _ = snapshot_followups(project_root)
                if followups != receipt["baseline_followup_files"] or followups != receipt["current_followup_files"]:
                    raise CaptureError("pi_format_correction_followups_drift", "followups changed before correction")
                chain = _general_pi_correction_leaf_chain(project_root, receipt)
                if chain is None:
                    result.update(state="not_applicable", reason="no_typed_blocked_leaf")
                    return result
                role = chain["blocked"]["role"]
                result["role"] = role
                result["attempts_reserved"] = int(role in records)
                docs_snapshot = docs_closeout._git_status_docs_paths(project_root)
                protected, delta_ok = docs_closeout._terminal_protected_docs_delta_paths(
                    root=project_root, plan_ref=plan_ref, status_norm=oracle.status_norm, docs_status_snapshot=docs_snapshot)
                owned = _changed_paths(chain["before"], chain["after"])
                _require_no_post_checkpoint_foreign_backlogs(project_root, plan_ref)
                if not docs_snapshot[1] or not delta_ok or protected or set(docs_snapshot[0]).difference(owned):
                    raise CaptureError("pi_format_correction_docs_delta_blocked", "protected, foreign or unknown docs delta")
                if role in records:
                    record = records[role]
                    if (_ingest_reservation_id is None or record["reservation_id"] != _ingest_reservation_id
                            or record["reserved_revision"] != receipt["receipt_revision"]
                            or record["source_identity"] != source or record["project_root"] != str(project_root.absolute())
                            or record["original_receipt_sha256"] != chain["blocked"]["sha256"]
                            or record["original_receipt_identity"] != chain["blocked"]["object_identity"]):
                        raise CaptureError("pi_format_correction_reservation_consumed", "one EXTRA correction reservation is already spent")
                elif _ingest_reservation_id is not None:
                    raise CaptureError("pi_format_correction_reservation_missing", "corrected ingest requires its stored reservation")
                _, now_raw, now_identity = _read_receipt(fd, plan_ref, cycle_id)
                if now_raw != raw or now_identity != receipt_identity:
                    raise CaptureError("pi_format_correction_receipt_drift", "aggregate changed during proof")
                result.update(state="retryable", reason="typed_no_effect_format_error", next_dispatch=f"{role}:general-format-correction",
                    proof={"project_root": str(project_root.absolute()), "source_identity": source,
                        "semantic_closeout_identity": receipt["semantic_closeout_identity"], "receipt_revision": receipt["receipt_revision"],
                        "receipt_sha256": _sha256(raw), "receipt_content_sha256": receipt["receipt_content_sha256"],
                        "receipt_object_identity": receipt_identity, "cycle_directory_identity": cycle_identity,
                        "transaction_host_identity": host.transaction_host_identity(), "collector_proof": chain,
                        "followup_files": followups, "docs_delta": {"paths": docs_snapshot[0], "protected_paths": protected, "owned_pi_paths": owned}})
                return result
            finally:
                os.close(fd)
    except (CaptureError, process_improvements_collect.authority_context.ContractAuthorityError, OSError, ValueError, KeyError, TypeError) as exc:
        result.update(state="blocked", reason=getattr(exc, "reason_code", "pi_format_correction_proof_unavailable"), next_dispatch=None, proof=None)
        return result


def reserve_general_pi_correction(project_root: Path, plan_ref: str, cycle_id: str, role: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Publish one spent slot before dispatch; replay never returns reserved."""
    import docs_closeout
    supplied = payload.get("general_pi_format_correction_admission")
    if (payload.get("schema") != "docs_closeout_payload.v1" or payload.get("schema_state") != "ok"
            or payload.get("schema_errors") != [] or payload.get("plan_ref") != plan_ref
            or payload.get("followups_capture_cycle_id") != cycle_id
            or docs_closeout.validate_docs_closeout_payload(dict(payload)).get("schema_state") != "ok"):
        raise CaptureError("pi_format_correction_retained_payload_invalid", "one full schema-green retained payload is required")
    fresh = general_pi_format_correction_admission(project_root, plan_ref, cycle_id,
        bundle_payload=_fresh_continuation_bundle_payload(project_root, plan_ref))
    if fresh.get("state") != "retryable" or fresh.get("role") != role or supplied != fresh:
        raise CaptureError("pi_format_correction_admission_stale", "retained correction proof is stale, blocked or spent")
    with CaptureHost(project_root, plan_ref, create=False) as host:
        fd, cycle_identity = _open_cycle(host, cycle_id)
        try:
            receipt, raw, identity = _read_receipt(fd, plan_ref, cycle_id)
            if (fresh["proof"]["receipt_sha256"] != _sha256(raw)
                    or fresh["proof"]["receipt_object_identity"] != identity
                    or fresh["proof"]["cycle_directory_identity"] != cycle_identity):
                raise CaptureError("pi_format_correction_admission_stale", "aggregate CAS witness changed")
            leaf = fresh["proof"]["collector_proof"]["blocked"]
            loaded = process_improvements_collect._safe_pi_read_capture_receipt_regular(project_root, Path(leaf["path"]))
            if loaded is None or _sha256(loaded[1]) != leaf["sha256"] or list(_stat_identity(loaded[2])) != leaf["object_identity"]:
                raise CaptureError("pi_format_correction_original_drift", "original blocked receipt changed")
            next_receipt = _next_receipt(receipt)
            reservation_id = str(uuid.uuid4())
            next_receipt[PI_FORMAT_CORRECTIONS_KEY][role] = {"schema": PI_FORMAT_CORRECTION_SCHEMA,
                "project_root": str(project_root.absolute()), "source_identity": fresh["proof"]["source_identity"],
                "plan_ref": plan_ref, "capture_cycle_id": cycle_id, "role": role, "reservation_id": reservation_id,
                "attempts_reserved": 1, "reserved_revision": next_receipt["receipt_revision"],
                "original_receipt_path": leaf["path"], "original_receipt_object": leaf["object"],
                "original_receipt_identity": leaf["object_identity"], "original_receipt_utf8": loaded[1].decode("utf-8"),
                "original_receipt_sha256": leaf["sha256"]}
            # Repeat every witness immediately before the existing atomic CAS.
            current = general_pi_format_correction_admission(project_root, plan_ref, cycle_id,
                bundle_payload=_fresh_continuation_bundle_payload(project_root, plan_ref))
            if current != fresh:
                raise CaptureError("pi_format_correction_admission_stale", "effect context changed before reservation")
            docs_closeout.validate_before_effect(docs_closeout._reader_context(project_root, None))
            published = _publish_mutation(host, fd, cycle_id, raw, next_receipt)
            return {**_response(published, state="reserved", reason_code="pi_format_correction_reserved"),
                    "role": role, "reservation_id": reservation_id, "attempts_reserved": 1, "max_extra_attempts": 1}
        finally:
            os.close(fd)


def validate_reserved_general_pi_ingest(project_root: Path, plan_ref: str, cycle_id: str, role: str, reservation_id: str) -> dict[str, Any]:
    """A stored reservation admits its one original leaf, never another send."""
    admission = general_pi_format_correction_admission(project_root, plan_ref, cycle_id,
        bundle_payload=_fresh_continuation_bundle_payload(project_root, plan_ref), _ingest_reservation_id=reservation_id)
    if admission.get("state") != "retryable" or admission.get("role") != role or admission.get("attempts_reserved") != 1:
        raise CaptureError("pi_format_correction_ingest_blocked", str(admission.get("reason")))
    return admission


def _expected_role(receipt: dict[str, Any]) -> str | None:
    completed = list(receipt.get("completed_roles") or [])
    roles = list(receipt["required_roles"])
    return roles[len(completed)] if len(completed) < len(roles) else None


def _block_cycle(
    host: CaptureHost,
    cycle_fd: int,
    cycle_id: str,
    receipt: dict[str, Any],
    raw: bytes,
    *,
    role: str,
    reason_code: str,
    message: str,
    process_improvement_files: dict[str, dict[str, Any]] | None = None,
    checkpoint_pi_failure: bool = True,
    preserve_current_process_improvement_files: bool = False,
) -> dict[str, Any]:
    if receipt.get("state") == "blocked":
        return _response(receipt, state="blocked", reason_code=str(receipt.get("reason_code") or reason_code))
    next_receipt = _next_receipt(receipt)
    next_receipt["state"] = "blocked"
    next_receipt["reason_code"] = reason_code
    if role not in next_receipt["blocked_roles"]:
        next_receipt["blocked_roles"].append(role)
    result = next_receipt["role_results"].get(role) or {
        "role": role,
        "prepared_at": None,
        "stdout_sha256": None,
        "role_output_kind": None,
        "declared_created_paths": [],
        "changed_followup_paths": [],
        "checkpoint_before_files": next_receipt["current_followup_files"],
        "checkpoint_after_files": None,
        "path_results": [],
        "checkpoint_before_process_improvement_files": next_receipt.get("current_process_improvement_files", {}),
        "prepared_process_improvement_files": None,
        "checkpoint_after_process_improvement_files": None,
        "process_improvement_path_results": [],
        "row_refs": [],
        "row_source_refs": [],
        "finalized_at": None,
    }
    result.update({"state": "blocked", "reason_code": reason_code, "message": message})
    if process_improvement_files is not None:
        exact_objects = {path: process_improvement_files[path] for path in sorted(process_improvement_files)}
        before_objects = result.get("checkpoint_before_process_improvement_files")
        if not isinstance(before_objects, dict):
            before_objects = next_receipt.get("current_process_improvement_files", {})
        result["process_improvement_path_results"] = [
            {
                "path": path,
                "before_object": before_objects.get(path),
                "after_object": exact_objects.get(path),
            }
            for path in _changed_paths(before_objects, exact_objects)
        ]
        result["checkpoint_after_process_improvement_files"] = exact_objects
        if not preserve_current_process_improvement_files:
            next_receipt["current_process_improvement_files"] = exact_objects
        if checkpoint_pi_failure:
            next_receipt["pi_final_objects"] = exact_objects
            next_receipt["pi_ownership_state"] = "checkpointed_failure"
            next_receipt["pi_failure_checkpoint"] = {
                "role": role,
                "reason_code": reason_code,
                "path_objects": exact_objects,
            }
        else:
            next_receipt["pi_final_objects"] = {}
            next_receipt["pi_ownership_state"] = "blocked"
            next_receipt["pi_failure_checkpoint"] = None
    next_receipt["role_results"][role] = result
    published = _publish_mutation(host, cycle_fd, cycle_id, raw, next_receipt)
    return _response(published, state="blocked", reason_code=reason_code)


def _fresh_continuation_bundle_payload(project_root: Path, plan_ref: str) -> dict[str, Any]:
    """Use the existing child-only public producer, never a retained bundle hint."""
    facade = Path(__file__).resolve().parent.parent / "bin" / "planveyor"
    result = subprocess.run(
        [str(facade), "--project", str(project_root), "planveyor_plan_bundle", "--closeout-json", plan_ref],
        cwd=project_root, capture_output=True, check=False,
    )
    if result.returncode != 0:
        raise CaptureError("followup_capture_continuation_admission_invalid", "fresh public bundle proof is unavailable")
    return _load_json_bytes(result.stdout, "followup_capture_continuation_admission_invalid")


def _revalidate_continuation_admission(
    project_root: Path, plan_ref: str, cycle_id: str, payload: dict[str, Any],
    receipt: dict[str, Any], raw: bytes, receipt_identity: dict[str, Any],
) -> None:
    try:
        from docs_closeout import classify_followups_continuation_admission, validate_docs_closeout_payload
    except ModuleNotFoundError:
        from scripts.docs_closeout import classify_followups_continuation_admission, validate_docs_closeout_payload
    supplied = payload.get("followups_continuation_admission")
    if (payload.get("schema") != "docs_closeout_payload.v1" or payload.get("schema_state") != "ok"
            or payload.get("schema_errors") != [] or payload.get("plan_ref") != plan_ref
            or payload.get("followups_capture_cycle_id") != cycle_id
            or validate_docs_closeout_payload(payload).get("schema_state") != "ok"
            or not isinstance(supplied, dict) or supplied.get("state") != "ready"):
        raise CaptureError("followup_capture_continuation_admission_invalid", "continuation requires an exact schema-green retained admission")
    current = classify_followups_continuation_admission(
        project_root, plan_ref, cycle_id, bundle_payload=_fresh_continuation_bundle_payload(project_root, plan_ref))
    proof = current.get("proof")
    if (current.get("state") != "ready" or supplied != current or not isinstance(proof, dict)
            or proof["receipt_revision"] != receipt["receipt_revision"]
            or proof["receipt_content_sha256"] != receipt["receipt_content_sha256"]
            or proof["receipt_sha256"] != _sha256(raw) or proof["receipt_object_identity"] != receipt_identity):
        raise CaptureError("followup_capture_continuation_admission_invalid", "continuation admission is stale, blocked, or differs from fresh helper proof")


def checkpoint_general_pi(
    project_root: Path,
    plan_ref: str,
    cycle_id: str,
    *,
    docs_closeout_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Publish the one exact bridge from general collector outputs to followups."""
    plan_ref = normalize_plan_ref(plan_ref)
    with CaptureHost(project_root, plan_ref) as host:
        cycle_fd, cycle_identity = _open_cycle(host, cycle_id)
        try:
            receipt, raw, receipt_identity = _read_receipt(cycle_fd, plan_ref, cycle_id)
            if receipt["cycle_directory_identity"] != cycle_identity:
                raise CaptureError("followup_capture_host_object_drift", "cycle directory identity mismatch")
            if receipt["transaction_host_identity"] != host.transaction_host_identity():
                raise CaptureError("followup_capture_host_object_drift", "capture transaction identity mismatch")
            _current_plan_identity(project_root, receipt)
            if (
                receipt.get("state") != "started"
                or receipt.get("completed_roles") != []
                or receipt.get("role_results") != {}
            ):
                raise CaptureError(
                    "followup_capture_pi_general_checkpoint_phase_closed",
                    "general-PI checkpoint is only admissible before the first followups role progresses",
                )
            expected_backlog = str(process_improvements_collect.backlog_rel_path_for_source_ref(plan_ref))
            foreign_backlogs = _dirty_process_improvement_backlogs(project_root, expected_backlog)
            if foreign_backlogs:
                raise CaptureError(
                    "followup_capture_pi_general_checkpoint_foreign_backlog",
                    "foreign process-improvement backlog is dirty before general-PI checkpoint publication",
                    expected_backlog=expected_backlog,
                    foreign_backlog_paths=foreign_backlogs,
                )
            if "general_pi_checkpoint" not in receipt:
                raise CaptureError(
                    "followup_capture_pi_general_checkpoint_legacy",
                    "non-terminal aggregate receipt predates the general-PI checkpoint field",
                )
            lineage = _receipt_pi_lineage(receipt)
            if (
                lineage["ownership_state"] != "active"
                or lineage["final_objects"]
                or lineage["failure_checkpoint"] is not None
            ):
                raise CaptureError(
                    "followup_capture_pi_general_checkpoint_state_invalid",
                    "general-PI checkpoint requires an active aggregate PI ownership state",
                )
            current_objects = lineage["current_objects"]
            marker_value = receipt.get("general_pi_checkpoint")
            if marker_value is not None:
                marker = _validate_general_pi_checkpoint_marker(
                    marker_value,
                    plan_ref=plan_ref,
                    capture_cycle_id=cycle_id,
                    current_objects=current_objects,
                )
                assert marker is not None
                if receipt["receipt_revision"] != marker["prior_receipt_revision"] + 1:
                    raise CaptureError(
                        "followup_capture_pi_general_checkpoint_stale_revision",
                        "general-PI checkpoint prior revision does not fence the current aggregate receipt",
                    )
                proof = _general_pi_capture_receipts_proof(
                    project_root,
                    plan_ref,
                    cycle_id,
                    expected_before=marker["before_process_improvement_files"],
                    expected_after=marker["after_process_improvement_files"],
                )
                if (
                    marker["input_receipts"] != proof["input_receipts"]
                    or marker["process_improvement_path_results"] != proof["process_improvement_path_results"]
                ):
                    raise CaptureError(
                        "followup_capture_pi_general_checkpoint_conflicting_replay",
                        "general-PI checkpoint replay inputs differ from the published aggregate marker",
                    )
                if docs_closeout_payload is not None:
                    _revalidate_continuation_admission(
                        project_root, plan_ref, cycle_id, docs_closeout_payload, receipt, raw, receipt_identity)
                return _response(
                    receipt,
                    state="started",
                    reason_code="followup_capture_pi_general_checkpoint_already_published",
                )

            proof = _general_pi_capture_receipts_proof(
                project_root,
                plan_ref,
                cycle_id,
                expected_before=current_objects,
            )
            if docs_closeout_payload is not None:
                _revalidate_continuation_admission(
                    project_root, plan_ref, cycle_id, docs_closeout_payload, receipt, raw, receipt_identity)
            next_receipt = _next_receipt(receipt)
            next_receipt["current_process_improvement_files"] = proof["after_process_improvement_files"]
            next_receipt["general_pi_checkpoint"] = {
                "input_receipts": proof["input_receipts"],
                "before_process_improvement_files": proof["before_process_improvement_files"],
                "after_process_improvement_files": proof["after_process_improvement_files"],
                "process_improvement_path_results": proof["process_improvement_path_results"],
                "prior_receipt_revision": receipt["receipt_revision"],
                "prior_receipt_content_sha256": receipt["receipt_content_sha256"],
                "published_at": _utc_now(),
            }
            published = _publish_mutation(host, cycle_fd, cycle_id, raw, next_receipt)
            return _response(
                published,
                state="started",
                reason_code="followup_capture_pi_general_checkpointed",
            )
        finally:
            os.close(cycle_fd)


def _require_general_pi_checkpoint_for_followups(
    project_root: Path,
    plan_ref: str,
    receipt: dict[str, Any],
) -> dict[str, Any]:
    del project_root
    if "general_pi_checkpoint" not in receipt:
        raise CaptureError(
            "followup_capture_pi_general_checkpoint_legacy",
            "non-terminal aggregate receipt predates the general-PI checkpoint field",
        )
    current_objects = _validate_pi_object_map(
        receipt.get("current_process_improvement_files"),
        plan_ref,
        field="current_process_improvement_files",
    )
    marker = _validate_general_pi_checkpoint_marker(
        receipt.get("general_pi_checkpoint"),
        plan_ref=plan_ref,
        capture_cycle_id=str(receipt.get("capture_cycle_id") or ""),
        current_objects=current_objects,
    )
    if marker is None:
        raise CaptureError(
            "followup_capture_pi_general_checkpoint_missing",
            "aggregate receipt has not published the required general-PI checkpoint",
        )
    return marker


def prepare_role(
    project_root: Path,
    plan_ref: str,
    cycle_id: str,
    role: str,
) -> dict[str, Any]:
    plan_ref = normalize_plan_ref(plan_ref)
    if role not in REQUIRED_ROLES:
        raise CaptureError("followup_capture_role_invalid", f"unsupported role: {role!r}")
    with CaptureHost(project_root, plan_ref) as host:
        cycle_fd, cycle_identity = _open_cycle(host, cycle_id)
        try:
            receipt, raw, _ = _read_receipt(cycle_fd, plan_ref, cycle_id)
            if receipt["cycle_directory_identity"] != cycle_identity:
                raise CaptureError("followup_capture_host_object_drift", "cycle directory identity mismatch")
            if receipt["transaction_host_identity"] != host.transaction_host_identity():
                raise CaptureError("followup_capture_host_object_drift", "transaction host identity mismatch")
            _current_plan_identity(project_root, receipt)
            if receipt["state"] == "finalized":
                return _response(receipt, state="finalized", reason_code="already_finalized")
            current, _ = snapshot_followups(project_root)
            current_pi = snapshot_process_improvement_data_files(project_root, plan_ref)
            if receipt["state"] == "blocked":
                return _response(receipt, state="blocked", reason_code=receipt["reason_code"])
            marker = _require_general_pi_checkpoint_for_followups(project_root, plan_ref, receipt)
            try:
                _require_no_post_checkpoint_foreign_backlogs(project_root, plan_ref)
            except CaptureError as exc:
                return _block_cycle(
                    host,
                    cycle_fd,
                    cycle_id,
                    receipt,
                    raw,
                    role=role,
                    reason_code=exc.reason_code,
                    message=str(exc),
                    process_improvement_files=current_pi,
                    checkpoint_pi_failure=False,
                    preserve_current_process_improvement_files=True,
                )
            if current_pi != marker["after_process_improvement_files"]:
                return _block_cycle(
                    host,
                    cycle_fd,
                    cycle_id,
                    receipt,
                    raw,
                    role=role,
                    reason_code="followup_capture_pi_post_checkpoint_drift",
                    message="process-improvement map changed after the general-PI checkpoint",
                    process_improvement_files=current_pi,
                    checkpoint_pi_failure=False,
                    preserve_current_process_improvement_files=True,
                )
            existing = receipt["role_results"].get(role)
            if existing and existing.get("state") == "prepared":
                if (
                    existing.get("checkpoint_before_files") == current == receipt["current_followup_files"]
                    and existing.get("prepared_process_improvement_files") == current_pi == marker["after_process_improvement_files"]
                ):
                    input_fd = _ordinary_v2_open_input_directory(
                        cycle_fd,
                        plan_ref=plan_ref,
                        cycle_id=cycle_id,
                        create=True,
                    )
                    os.close(input_fd)
                    return _response(receipt, state="started", reason_code="already_prepared")
                return _block_cycle(
                    host,
                    cycle_fd,
                    cycle_id,
                    receipt,
                    raw,
                    role=role,
                    reason_code="followup_capture_changed_duplicate",
                    message="duplicate prepare proof differs from persisted checkpoint",
                    process_improvement_files=current_pi,
                    checkpoint_pi_failure=False,
                )
            if receipt["state"] != "started" or _expected_role(receipt) != role or existing is not None:
                return _block_cycle(
                    host,
                    cycle_fd,
                    cycle_id,
                    receipt,
                    raw,
                    role=role,
                    reason_code="followup_capture_role_order_mismatch",
                    message="role is missing, duplicated or out of order",
                    process_improvement_files=current_pi,
                    checkpoint_pi_failure=False,
                )
            if current != receipt["current_followup_files"]:
                return _block_cycle(
                    host,
                    cycle_fd,
                    cycle_id,
                    receipt,
                    raw,
                    role=role,
                    reason_code="followup_capture_checkpoint_drift",
                    message="followups map changed before role dispatch",
                    process_improvement_files=current_pi,
                    checkpoint_pi_failure=False,
                )
            next_receipt = _next_receipt(receipt)
            next_receipt["reason_code"] = "role_prepared"
            next_receipt["role_results"][role] = {
                "role": role,
                "state": "prepared",
                "reason_code": "role_prepared",
                "prepared_at": _utc_now(),
                "stdout_sha256": None,
                "role_output_kind": None,
                "declared_created_paths": [],
                "changed_followup_paths": [],
                "checkpoint_before_files": current,
                "checkpoint_after_files": None,
                "path_results": [],
                "checkpoint_before_process_improvement_files": receipt["current_process_improvement_files"],
                "prepared_process_improvement_files": current_pi,
                "checkpoint_after_process_improvement_files": None,
                "process_improvement_path_results": [
                    {
                        "path": path,
                        "before_object": receipt["current_process_improvement_files"].get(path),
                        "after_object": current_pi.get(path),
                    }
                    for path in _changed_paths(receipt["current_process_improvement_files"], current_pi)
                ],
                "row_refs": [],
                "row_source_refs": [],
                "finalized_at": None,
            }
            published = _publish_mutation(host, cycle_fd, cycle_id, raw, next_receipt)
            input_fd = _ordinary_v2_open_input_directory(
                cycle_fd,
                plan_ref=plan_ref,
                cycle_id=cycle_id,
                create=True,
            )
            os.close(input_fd)
            return _response(published, state="started", reason_code="role_prepared")
        finally:
            os.close(cycle_fd)


def _parse_control(stdout: bytes) -> tuple[str, list[str]]:
    try:
        text = stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CaptureError("followup_capture_role_output_invalid", f"role stdout is not UTF-8: {exc}") from exc
    nonempty = [line.strip() for line in text.splitlines() if line.strip()]
    controls = [line for line in nonempty if line == "NO FOLLOWUPS" or line.startswith("Created:")]
    if not nonempty or len(controls) != 1 or nonempty[0] != controls[0]:
        raise CaptureError(
            "followup_capture_role_output_invalid",
            "first non-empty line must be exactly one NO FOLLOWUPS or Created: control line",
        )
    control = controls[0]
    if control == "NO FOLLOWUPS":
        return "no_followups", []
    raw_path = control.split(":", 1)[1].strip()
    return "created", [validate_followup_relpath(raw_path)]


def _changed_paths(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    return sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))


def _lint_created_bytes(project_root: Path, rel_path: str, data: bytes, plan_ref: str) -> tuple[list[str], list[str]]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CaptureError("followup_capture_lint_failed", f"created followup is not UTF-8: {exc}", path=rel_path) from exc
    try:
        import followups_lint
    except ModuleNotFoundError:  # package import in focused unittest invocation
        from scripts import followups_lint

    followup = followups_lint.parse_followup_text(text, rel_path, project_root / rel_path)
    findings = followups_lint.lint_followup_files([followup], project_root)
    if findings:
        raise CaptureError(
            "followup_capture_lint_failed",
            "created followup is not lint-green",
            path=rel_path,
            findings=[finding.render() for finding in findings],
        )
    active = [item for item in followup.items if item.status in {"open", "promoted", "unconfirmed"}]
    if not active:
        raise CaptureError("followup_capture_source_ref_missing", "created followup has no active ordinary row", path=rel_path)
    source_refs = [str(item.fields.get("source_ref") or "").strip() for item in active]
    if any(value != plan_ref for value in source_refs):
        raise CaptureError(
            "followup_capture_source_ref_mismatch",
            "every active row in a created followup must carry exact source_ref",
            path=rel_path,
            expected_source_ref=plan_ref,
            actual_source_refs=source_refs,
        )
    row_refs = [f"{rel_path}:{item.line_no}" for item in active]
    return row_refs, source_refs


def finalize_role(
    project_root: Path,
    plan_ref: str,
    cycle_id: str,
    role: str,
    stdout: bytes,
) -> dict[str, Any]:
    plan_ref = normalize_plan_ref(plan_ref)
    if role not in REQUIRED_ROLES:
        raise CaptureError("followup_capture_role_invalid", f"unsupported role: {role!r}")
    stdout_hash = _sha256(stdout)
    with CaptureHost(project_root, plan_ref) as host:
        cycle_fd, cycle_identity = _open_cycle(host, cycle_id)
        try:
            receipt, raw, _ = _read_receipt(cycle_fd, plan_ref, cycle_id)
            if receipt["cycle_directory_identity"] != cycle_identity or receipt["transaction_host_identity"] != host.transaction_host_identity():
                raise CaptureError("followup_capture_host_object_drift", "capture transaction identity mismatch")
            _current_plan_identity(project_root, receipt)
            current, contents = snapshot_followups(project_root, include_bytes=True)
            current_pi = snapshot_process_improvement_data_files(project_root, plan_ref)
            if receipt["state"] == "blocked":
                return _response(receipt, state="blocked", reason_code=receipt["reason_code"])
            marker = _require_general_pi_checkpoint_for_followups(project_root, plan_ref, receipt)
            existing = receipt["role_results"].get(role)
            if receipt["state"] != "finalized":
                try:
                    _require_no_post_checkpoint_foreign_backlogs(project_root, plan_ref)
                except CaptureError as exc:
                    return _block_cycle(
                        host,
                        cycle_fd,
                        cycle_id,
                        receipt,
                        raw,
                        role=role,
                        reason_code=exc.reason_code,
                        message=str(exc),
                        process_improvement_files=current_pi,
                        checkpoint_pi_failure=False,
                        preserve_current_process_improvement_files=True,
                    )
            if current_pi != marker["after_process_improvement_files"]:
                if receipt["state"] == "finalized":
                    raise CaptureError(
                        "followup_capture_pi_post_checkpoint_drift",
                        "process-improvement map changed after the general-PI checkpoint finalized",
                    )
                return _block_cycle(
                    host,
                    cycle_fd,
                    cycle_id,
                    receipt,
                    raw,
                    role=role,
                    reason_code="followup_capture_pi_post_checkpoint_drift",
                    message="process-improvement map changed after the general-PI checkpoint",
                    process_improvement_files=current_pi,
                    checkpoint_pi_failure=False,
                    preserve_current_process_improvement_files=True,
                )
            if existing and existing.get("state") == "finalized":
                if (
                    existing.get("stdout_sha256") == stdout_hash
                    and existing.get("checkpoint_after_files") == current
                    and existing.get("checkpoint_after_process_improvement_files") == current_pi
                ):
                    return _response(receipt, state=receipt["state"], reason_code="already_finalized")
                if receipt["state"] == "finalized":
                    raise CaptureError(
                        "followup_capture_changed_duplicate",
                        "duplicate finalize output or checkpoint differs from a finalized aggregate receipt",
                    )
                return _block_cycle(
                    host,
                    cycle_fd,
                    cycle_id,
                    receipt,
                    raw,
                    role=role,
                    reason_code="followup_capture_changed_duplicate",
                    message="duplicate finalize output or checkpoint differs",
                    process_improvement_files=current_pi,
                )
            if not existing or existing.get("state") != "prepared" or _expected_role(receipt) != role:
                return _block_cycle(
                    host,
                    cycle_fd,
                    cycle_id,
                    receipt,
                    raw,
                    role=role,
                    reason_code="followup_capture_role_not_prepared",
                    message="finalize requires the exact prepared next role",
                    process_improvement_files=current_pi,
                    checkpoint_pi_failure=False,
                )
            before = existing["checkpoint_before_files"]
            pi_before = existing.get("checkpoint_before_process_improvement_files")
            changed = _changed_paths(before, current)
            try:
                if not isinstance(pi_before, dict):
                    raise CaptureError(
                        "followup_capture_pi_lineage_invalid",
                        "prepared role omitted the prior persisted PI object map",
                    )
                if pi_before != marker["after_process_improvement_files"]:
                    raise CaptureError(
                        "followup_capture_pi_general_checkpoint_invalid",
                        "prepared followups role does not start from the general-PI checkpoint map",
                    )
                changed_pi = _changed_paths(pi_before, current_pi)
                if changed_pi:
                    raise CaptureError(
                        "followup_capture_pi_post_checkpoint_drift",
                        "followups role changed the frozen process-improvement map",
                        paths=changed_pi,
                    )
                deleted_pi = sorted(path for path in pi_before if path not in current_pi)
                if deleted_pi:
                    raise CaptureError(
                        "followup_capture_pi_path_deleted",
                        "PI path deletion is not an admissible capture mutation",
                        paths=deleted_pi,
                    )
                output_kind, declared = _parse_control(stdout)
                if output_kind == "no_followups" and changed:
                    raise CaptureError("followup_capture_undeclared_delta", "NO FOLLOWUPS interval changed ordinary followup paths", paths=changed)
                if output_kind == "created":
                    if changed != declared:
                        raise CaptureError(
                            "followup_capture_declared_delta_mismatch",
                            "Created path must equal the complete role interval delta",
                            declared_paths=declared,
                            changed_paths=changed,
                        )
                    if declared[0] in before or declared[0] not in current:
                        raise CaptureError("followup_capture_declared_delta_mismatch", "Created path must be absent before and regular after")
                    if declared[0] in receipt["created_paths"]:
                        raise CaptureError("followup_capture_ambiguous_ownership", "ordinary followup path was claimed by multiple roles")
                path_results: list[dict[str, Any]] = []
                pi_path_results: list[dict[str, Any]] = []
                row_refs: list[str] = []
                source_refs: list[str] = []
                for path in changed:
                    item_rows, item_sources = _lint_created_bytes(project_root, path, contents[path], plan_ref)
                    row_refs.extend(item_rows)
                    source_refs.extend(item_sources)
                    path_results.append(
                        {
                            "path": path,
                            "before_object": before.get(path),
                            "after_object": current.get(path),
                            "nofollow_state": "verified",
                            "lint_state": "green",
                            "row_refs": item_rows,
                            "row_source_refs": item_sources,
                        }
                    )
                for path in changed_pi:
                    pi_path_results.append(
                        {
                            "path": path,
                            "before_object": pi_before.get(path),
                            "after_object": current_pi.get(path),
                        }
                    )
            except CaptureError as exc:
                return _block_cycle(
                    host,
                    cycle_fd,
                    cycle_id,
                    receipt,
                    raw,
                    role=role,
                    reason_code=exc.reason_code,
                    message=str(exc),
                    process_improvement_files=current_pi,
                    checkpoint_pi_failure=exc.reason_code != "followup_capture_pi_path_deleted",
                    preserve_current_process_improvement_files=True,
                )
            next_receipt = _next_receipt(receipt)
            result = next_receipt["role_results"][role]
            result.update(
                {
                    "state": "finalized",
                    "reason_code": "role_finalized",
                    "stdout_sha256": stdout_hash,
                    "role_output_kind": output_kind,
                    "declared_created_paths": declared,
                    "changed_followup_paths": changed,
                    "checkpoint_after_files": current,
                    "path_results": path_results,
                    "checkpoint_after_process_improvement_files": current_pi,
                    "process_improvement_path_results": pi_path_results,
                    "row_refs": row_refs,
                    "row_source_refs": source_refs,
                    "finalized_at": _utc_now(),
                }
            )
            next_receipt["completed_roles"].append(role)
            next_receipt["current_followup_files"] = current
            next_receipt["current_process_improvement_files"] = current_pi
            if output_kind == "created":
                next_receipt["created_paths"].extend(declared)
            else:
                next_receipt["no_followups_roles"].append(role)
            if next_receipt["completed_roles"] == next_receipt["required_roles"]:
                if next_receipt["baseline_dirty_process_improvement_paths"]:
                    next_receipt["state"] = "blocked"
                    next_receipt["reason_code"] = "followup_capture_pi_pre_root_dirt"
                    next_receipt["pi_ownership_state"] = "blocked"
                    next_receipt["pi_final_objects"] = {}
                    next_receipt["pi_failure_checkpoint"] = None
                else:
                    next_receipt["state"] = "finalized"
                    next_receipt["reason_code"] = "capture_finalized"
                    next_receipt["pi_ownership_state"] = "finalized"
                    next_receipt["pi_final_objects"] = current_pi
                    next_receipt["pi_failure_checkpoint"] = None
                    next_receipt["finalized_at"] = _utc_now()
            else:
                next_receipt["reason_code"] = "role_finalized"
            published = _publish_mutation(host, cycle_fd, cycle_id, raw, next_receipt)
            return _response(published, state=published["state"], reason_code=published["reason_code"])
        finally:
            os.close(cycle_fd)


def bind_ordinary_v2(
    project_root: Path,
    *,
    plan_ref: str,
    capture_cycle_id: str,
    role: str,
    submission_current: bool,
    write: bool,
) -> dict[str, Any]:
    """Bind one helper-owned current compact submission to the capture cycle.

    Manager never supplies a path, JSON payload, or acknowledgement here.  The
    helper derives the one role slot and proves it still belongs to the exact
    prepared receipt before any aggregate receipt/bound-family mutation.
    """

    plan_ref = normalize_plan_ref(plan_ref)
    _validate_uuid4(capture_cycle_id)
    if not write:
        raise CaptureError("followup_ordinary_v2_write_required", "bind-ordinary-v2 requires --write")
    if role not in REQUIRED_ROLES:
        raise CaptureError("followup_ordinary_v2_role_invalid", f"unsupported ordinary compact role: {role!r}")
    if not submission_current:
        raise CaptureError("followup_ordinary_v2_submission_current_required", "bind-ordinary-v2 requires --submission-current")
    with CaptureHost(project_root, plan_ref) as host:
        cycle_fd, cycle_identity = _open_cycle(host, capture_cycle_id)
        try:
            receipt, raw, _receipt_identity_value = _read_receipt(cycle_fd, plan_ref, capture_cycle_id)
            if (
                receipt.get("cycle_directory_identity") != cycle_identity
                or receipt.get("transaction_host_identity") != host.transaction_host_identity()
            ):
                raise CaptureError("followup_capture_host_object_drift", "capture transaction identity mismatch")
            _current_plan_identity(project_root, receipt)
            if receipt.get("state") == "blocked":
                raise CaptureError("followup_ordinary_v2_family_closed", "ordinary compact binding cannot repair a blocked capture cycle")
            current, current_bytes = snapshot_followups(project_root, include_bytes=True)
            current_pi = snapshot_process_improvement_data_files(project_root, plan_ref)
            marker = _require_general_pi_checkpoint_for_followups(project_root, plan_ref, receipt)
            if receipt.get("state") != "started":
                raise CaptureError("followup_ordinary_v2_family_closed", "ordinary compact binding requires an active capture cycle")
            existing = receipt["role_results"].get(role)
            if not existing or existing.get("state") != "prepared" or _expected_role(receipt) != role:
                raise CaptureError("followup_ordinary_v2_role_not_prepared", "ordinary compact bind requires the exact prepared next role")
            submission_fd = _ordinary_v2_open_submission_directory(
                cycle_fd,
                plan_ref=plan_ref,
                cycle_id=capture_cycle_id,
                create=False,
            )
            try:
                submission, submission_hash, submission_object = _ordinary_v2_read_submission(
                    submission_fd,
                    plan_ref=plan_ref,
                    capture_cycle_id=capture_cycle_id,
                    role=role,
                )
            finally:
                os.close(submission_fd)
            if (
                submission["prepared_receipt_content_sha256"] != receipt["receipt_content_sha256"]
                or submission["prepared_receipt_object_identity"] != receipt["receipt_object_identity"]
            ):
                raise CaptureError(
                    "followup_ordinary_v2_submission_prepared_receipt_drift",
                    "ordinary submission does not belong to the exact current prepared receipt",
                )
            compact = submission["compact_declaration"]
            compact_hash = submission["compact_declaration_sha256"]
            if current != receipt.get("current_followup_files") or current != existing.get("checkpoint_before_files"):
                raise CaptureError("followup_ordinary_v2_baseline_drift", "followups map changed before ordinary compact bind")
            if (
                current_pi != marker["after_process_improvement_files"]
                or current_pi != existing.get("prepared_process_improvement_files")
            ):
                raise CaptureError("followup_ordinary_v2_pi_drift", "process-improvement map changed after the general-PI checkpoint")
            source = _ordinary_v2_current_source_identity(project_root, plan_ref, receipt)
            baseline_sha256 = _sha256(_canonical_json_bytes(current))
            binding_value = receipt.get(ORDINARY_V2_BINDING_KEY)
            if binding_value is None:
                binding: dict[str, Any] = {
                    "state": "binding",
                    "capture_cycle_id": capture_cycle_id,
                    "plan_ref": plan_ref,
                    "source_identity": source,
                    "baseline_followups_snapshot_sha256": baseline_sha256,
                    "bound_declarations": [],
                    "frozen_manifest_path": None,
                    "frozen_manifest_sha256": None,
                }
            else:
                binding = _ordinary_v2_validate_marker(
                    binding_value,
                    project_root=project_root,
                    plan_ref=plan_ref,
                    cycle_id=capture_cycle_id,
                )
                if binding["state"] != "binding":
                    raise CaptureError("followup_ordinary_v2_family_closed", "ordinary compact family is already frozen")
                if binding["source_identity"] != source or binding["baseline_followups_snapshot_sha256"] != baseline_sha256:
                    raise CaptureError("followup_ordinary_v2_source_or_baseline_drift", "ordinary compact family source or baseline drifted")
            expected_prior_roles = list(REQUIRED_ROLES[: len(binding["bound_declarations"])])
            if expected_prior_roles != receipt["completed_roles"] or role != _expected_role(receipt):
                raise CaptureError("followup_ordinary_v2_role_order_invalid", "ordinary compact family role sequence drifted")
            declaration = _ordinary_v2_declaration(source, current, compact)
            validate_v2_declaration(project_root, plan_ref, declaration)
            bound_fd = _ordinary_v2_open_bound_directory(
                cycle_fd,
                plan_ref=plan_ref,
                cycle_id=capture_cycle_id,
                create=True,
            )
            try:
                expected_names = [f"{item}.json" for item in expected_prior_roles]
                try:
                    names = sorted(os.listdir(bound_fd))
                except OSError as exc:
                    raise CaptureError("followup_ordinary_v2_bound_family_invalid", f"cannot list ordinary bound family: {exc}") from exc
                if names != sorted(expected_names):
                    raise CaptureError("followup_ordinary_v2_bound_family_invalid", "ordinary bound family has unexpected role files")
                bound_path, declaration_hash = _ordinary_v2_write_bound_role(
                    bound_fd,
                    plan_ref=plan_ref,
                    cycle_id=capture_cycle_id,
                    role=role,
                    declaration=declaration,
                )
            finally:
                os.close(bound_fd)
            next_receipt = _next_receipt(receipt)
            result = next_receipt["role_results"][role]
            result.update(
                {
                    "state": "finalized",
                    "reason_code": "ordinary_v2_compact_bound",
                    "stdout_sha256": compact_hash,
                    "role_output_kind": "ordinary_v2_compact",
                    "ordinary_compact_declaration": compact,
                    "ordinary_submission_path": submission_object["path"],
                    "ordinary_submission_sha256": submission_hash,
                    "ordinary_submission_object_identity": submission_object,
                    "ordinary_submission_prepared_receipt_content_sha256": submission[
                        "prepared_receipt_content_sha256"
                    ],
                    "ordinary_submission_prepared_receipt_object_identity": submission[
                        "prepared_receipt_object_identity"
                    ],
                    "bound_declaration_path": bound_path,
                    "bound_declaration_sha256": declaration_hash,
                    "declared_created_paths": [],
                    "changed_followup_paths": [],
                    "checkpoint_after_files": current,
                    "path_results": [],
                    "checkpoint_after_process_improvement_files": current_pi,
                    "process_improvement_path_results": [],
                    "row_refs": [],
                    "row_source_refs": [],
                    "finalized_at": _utc_now(),
                }
            )
            next_binding = json.loads(_canonical_json_bytes(binding).decode("utf-8"))
            next_binding["bound_declarations"].append(
                {"role": role, "path": bound_path, "sha256": declaration_hash}
            )
            next_receipt[ORDINARY_V2_BINDING_KEY] = next_binding
            next_receipt["completed_roles"].append(role)
            next_receipt["current_followup_files"] = current
            next_receipt["current_process_improvement_files"] = current_pi
            if not compact["proposed_rows"]:
                next_receipt["no_followups_roles"].append(role)
            if next_receipt["completed_roles"] == next_receipt["required_roles"]:
                if next_receipt["baseline_dirty_process_improvement_paths"]:
                    next_receipt["state"] = "blocked"
                    next_receipt["reason_code"] = "followup_capture_pi_pre_root_dirt"
                    next_receipt["pi_ownership_state"] = "blocked"
                    next_receipt["pi_final_objects"] = {}
                    next_receipt["pi_failure_checkpoint"] = None
                else:
                    next_receipt["state"] = "finalized"
                    next_receipt["reason_code"] = "capture_finalized"
                    next_receipt["pi_ownership_state"] = "finalized"
                    next_receipt["pi_final_objects"] = current_pi
                    next_receipt["pi_failure_checkpoint"] = None
                    next_receipt["finalized_at"] = _utc_now()
            else:
                next_receipt["reason_code"] = "ordinary_v2_compact_bound"
            published = _publish_mutation(host, cycle_fd, capture_cycle_id, raw, next_receipt)
            payload = _response(published, state="bound", reason_code="ordinary_v2_compact_bound")
            payload.update({"role": role, "bound_declaration_path": bound_path})
            return payload
        finally:
            os.close(cycle_fd)


def _ordinary_v2_load_frozen_binding(
    project_root: Path,
    *,
    plan_ref: str,
    cycle_id: str,
    receipt: dict[str, Any],
    cycle_fd: int,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Re-read the receipt-owned ordinary family before freeze or post-apply use."""

    marker = _ordinary_v2_validate_marker(
        receipt.get(ORDINARY_V2_BINDING_KEY),
        project_root=project_root,
        plan_ref=plan_ref,
        cycle_id=cycle_id,
        require_frozen=True,
    )
    source = _ordinary_v2_validate_terminal_source_identity(
        project_root,
        plan_ref,
        receipt,
        marker["source_identity"],
        require_current_head=False,
    )
    baseline = receipt.get("current_followup_files")
    if not isinstance(baseline, dict) or _sha256(_canonical_json_bytes(baseline)) != marker["baseline_followups_snapshot_sha256"]:
        raise CaptureError("followup_ordinary_v2_source_or_baseline_drift", "ordinary compact marker baseline identity drifted")
    submission_fd = _ordinary_v2_open_submission_directory(
        cycle_fd,
        plan_ref=plan_ref,
        cycle_id=cycle_id,
        create=False,
    )
    bound_fd = _ordinary_v2_open_bound_directory(
        cycle_fd,
        plan_ref=plan_ref,
        cycle_id=cycle_id,
        create=False,
    )
    try:
        names = sorted(os.listdir(bound_fd))
        expected_names = sorted(f"{role}.json" for role in REQUIRED_ROLES)
        if names != expected_names:
            raise CaptureError("followup_ordinary_v2_bound_family_invalid", "ordinary bound family must contain exactly four role files")
        declarations: list[dict[str, Any]] = []
        for role, bound in zip(REQUIRED_ROLES, marker["bound_declarations"], strict=True):
            declaration, actual_hash = _ordinary_v2_read_bound_role(
                bound_fd,
                plan_ref=plan_ref,
                cycle_id=cycle_id,
                role=role,
            )
            if actual_hash != bound["sha256"]:
                raise CaptureError("followup_ordinary_v2_path_object_drift", "ordinary bound role hash drifted")
            result = receipt["role_results"].get(role)
            if (
                not isinstance(result, dict)
                or result.get("role_output_kind") != "ordinary_v2_compact"
                or result.get("bound_declaration_path") != bound["path"]
                or result.get("bound_declaration_sha256") != actual_hash
                or not isinstance(result.get("ordinary_compact_declaration"), dict)
            ):
                raise CaptureError("followup_ordinary_v2_bound_family_invalid", "ordinary role receipt proof is invalid")
            submission, submission_hash, submission_object = _ordinary_v2_read_submission(
                submission_fd,
                plan_ref=plan_ref,
                capture_cycle_id=cycle_id,
                role=role,
            )
            if (
                result.get("ordinary_submission_path") != submission_object["path"]
                or result.get("ordinary_submission_sha256") != submission_hash
                or result.get("ordinary_submission_object_identity") != submission_object
                or result.get("ordinary_submission_prepared_receipt_content_sha256")
                != submission["prepared_receipt_content_sha256"]
                or result.get("ordinary_submission_prepared_receipt_object_identity")
                != submission["prepared_receipt_object_identity"]
                or result["ordinary_compact_declaration"] != submission["compact_declaration"]
                or result.get("stdout_sha256") != submission["compact_declaration_sha256"]
            ):
                raise CaptureError(
                    "followup_ordinary_v2_submission_path_drift",
                    "ordinary submission proof differs from the receipt-bound role result",
                )
            expected = _ordinary_v2_declaration(source, baseline, result["ordinary_compact_declaration"])
            if set(declaration) != ORDINARY_V2_FULL_DECLARATION_KEYS or declaration != expected:
                raise CaptureError("followup_ordinary_v2_bound_family_invalid", "ordinary bound declaration differs from helper-owned compact proof")
            declarations.append(declaration)
    finally:
        os.close(bound_fd)
        os.close(submission_fd)
    return marker, source, declarations


def _ordinary_v2_read_tree_entry(
    project_root: Path,
    *,
    tree_oid: str,
    carrier_path: str,
    reason_code: str,
) -> tuple[str, str, str] | None:
    """Read one exact carrier entry with the staging tree-entry grammar."""

    raw = _git(project_root, "ls-tree", "-z", tree_oid, "--", carrier_path).stdout
    records = [record for record in raw.split(b"\0") if record]
    if not records:
        return None
    if len(records) != 1:
        raise CaptureError(reason_code, "ordinary compact carrier tree identity is ambiguous", path=carrier_path)
    try:
        metadata, raw_path = records[0].split(b"\t", 1)
        raw_mode, raw_kind, raw_oid = metadata.split(b" ", 2)
        mode = raw_mode.decode("ascii")
        kind = raw_kind.decode("ascii")
        oid = raw_oid.decode("ascii")
        path = raw_path.decode("utf-8")
    except (UnicodeDecodeError, ValueError) as exc:
        raise CaptureError(reason_code, "ordinary compact carrier tree identity is malformed", path=carrier_path) from exc
    if path != carrier_path or not OID_RE.fullmatch(oid):
        raise CaptureError(reason_code, "ordinary compact carrier tree identity is malformed", path=carrier_path)
    return mode, kind, oid


def _ordinary_v2_canonical_carrier_entry(
    project_root: Path,
    *,
    carrier_path: str,
    carrier_bytes: bytes,
    reason_code: str,
) -> tuple[str, str, str]:
    """Derive the sole canonical ordinary-carrier Git tree entry."""

    oid = _git(project_root, "hash-object", "--stdin", input_bytes=carrier_bytes).stdout.decode("ascii").strip()
    if not OID_RE.fullmatch(oid):
        raise CaptureError(
            reason_code,
            "ordinary compact canonical carrier hash-object identity is malformed",
            path=carrier_path,
        )
    return "100644", "blob", oid


def _ordinary_v2_validate_post_apply_head(
    project_root: Path,
    *,
    source: dict[str, str],
    carrier_path: str,
    carrier_bytes: bytes,
    generated_entries: Mapping[str, bytes] | None = None,
) -> str:
    """Classify canonical generated entries independently of unrelated commits.

    The frozen source remains authoritative; the final CAS parent may advance.
    A pending descendant must preserve the source follow-ups and bundle, while
    a landed descendant must contain the complete canonical generated entries.
    """

    head = _git(project_root, "rev-parse", "--verify", "HEAD^{commit}").stdout.decode("ascii", errors="replace").strip()
    source_oid = source["source_terminal_commit_oid"]
    if head == source_oid:
        return "pending"
    ancestry = _git(project_root, "merge-base", "--is-ancestor", source_oid, head, check=False)
    if ancestry.returncode != 0:
        raise CaptureError(
            "followup_ordinary_v2_post_apply_invalid",
            "post-CAS HEAD is not a descendant of the terminal source",
        )

    changed = _git(
        project_root,
        "diff",
        "--name-only",
        "-z",
        source_oid,
        head,
        "--",
        "docs/followups",
    ).stdout
    changed_paths = sorted(item.decode("utf-8") for item in changed.split(b"\0") if item)
    expected_bytes = {carrier_path: carrier_bytes}
    if generated_entries is not None:
        for path, data in generated_entries.items():
            if path == carrier_path or not isinstance(path, str) or not isinstance(data, bytes):
                raise CaptureError(
                    "followup_ordinary_v2_post_apply_invalid",
                    "post-CAS generated follow-ups entry is invalid",
                )
            expected_bytes[path] = data
    expected_changed_paths: list[str] = []
    landed = True
    for path in sorted(expected_bytes):
        canonical_entry = _ordinary_v2_canonical_carrier_entry(
            project_root,
            carrier_path=path,
            carrier_bytes=expected_bytes[path],
            reason_code="followup_ordinary_v2_post_apply_invalid",
        )
        source_entry = _ordinary_v2_read_tree_entry(
            project_root,
            tree_oid=source_oid,
            carrier_path=path,
            reason_code="followup_ordinary_v2_post_apply_invalid",
        )
        head_entry = _ordinary_v2_read_tree_entry(
            project_root,
            tree_oid=head,
            carrier_path=path,
            reason_code="followup_ordinary_v2_post_apply_invalid",
        )
        if path == carrier_path and source_entry is not None and source_entry != canonical_entry:
            raise CaptureError(
                "followup_ordinary_v2_post_apply_invalid",
                "terminal source carrier tree entry differs from the canonical ordinary entry",
                path=path,
            )
        landed = landed and head_entry == canonical_entry
        if source_entry != canonical_entry:
            expected_changed_paths.append(path)
    if landed and changed_paths == expected_changed_paths:
        return "landed"
    if not changed_paths:
        _ordinary_v2_pending_bundle(project_root, source=source, head=head)
        return "pending"
    raise CaptureError(
        "followup_ordinary_v2_post_apply_invalid",
        "follow-ups HEAD is neither an unchanged source nor the complete canonical transaction",
        changed_paths=changed_paths,
    )


def _ordinary_v2_pending_bundle(
    project_root: Path, *, source: Mapping[str, str], head: str,
) -> tuple[str, ...]:
    """Bind the pending bundle to source/HEAD; allow only its index worktree delta.

    Inventory carriers themselves are checked, so altered metadata cannot
    authorize a smaller target set. Unrelated shared-index state is preserved.
    """
    paths = _post_cas_semantic_identity_canonical_bundle_paths(
        project_root, plan_ref=source.get("plan_ref", ""),
        _source_head=(source["source_terminal_commit_oid"], head),
    )
    for path in paths:
        source_entry = _ordinary_v2_read_tree_entry(
            project_root, tree_oid=source["source_terminal_commit_oid"],
            carrier_path=path, reason_code="followup_ordinary_v2_post_apply_invalid",
        )
        head_entry = _ordinary_v2_read_tree_entry(
            project_root, tree_oid=head, carrier_path=path,
            reason_code="followup_ordinary_v2_post_apply_invalid",
        )
        if source_entry is None or source_entry != head_entry:
            raise CaptureError("followup_ordinary_v2_post_apply_invalid", "pending canonical bundle changed from source", path=path)
        checks = [("diff", "--cached", "--quiet", head, "--", path)]
        if path != FOLLOWUPS_INDEX_PATH:
            try:
                snapshot = fs_object_identity.snapshot_regular_or_absent(project_root, path)
            except fs_object_identity.ObjectIdentityError as exc:
                raise _post_cas_semantic_identity_mismatch("pending bundle object is unsafe") from exc
            if snapshot.state != "regular" or snapshot.data is None:
                raise _post_cas_semantic_identity_mismatch("pending bundle object is not regular")
            oid = _git(project_root, "hash-object", "--stdin", input_bytes=snapshot.data).stdout.decode("ascii").strip()
            if source_entry != (snapshot.git_mode, "blob", oid):
                raise _post_cas_semantic_identity_mismatch("pending bundle bytes or mode differ from source")
            checks.append(("diff", "--quiet", head, "--", path))
        for args in checks:
            if _git(project_root, *args, check=False).returncode != 0:
                raise CaptureError("followup_ordinary_v2_post_apply_invalid", "pending canonical bundle has an unowned delta", path=path)
    return paths


def freeze_ordinary_v2(
    project_root: Path,
    *,
    plan_ref: str,
    capture_cycle_id: str,
    write: bool,
) -> dict[str, Any]:
    """Freeze exactly the receipt-owned ordinary compact family."""

    plan_ref = normalize_plan_ref(plan_ref)
    _validate_uuid4(capture_cycle_id)
    if not write:
        raise CaptureError("followup_ordinary_v2_write_required", "freeze-ordinary-v2 requires --write")
    with CaptureHost(project_root, plan_ref) as host:
        cycle_fd, cycle_identity = _open_cycle(host, capture_cycle_id)
        try:
            receipt, raw, _identity = _read_receipt(cycle_fd, plan_ref, capture_cycle_id)
            if (
                receipt.get("cycle_directory_identity") != cycle_identity
                or receipt.get("transaction_host_identity") != host.transaction_host_identity()
            ):
                raise CaptureError("followup_capture_host_object_drift", "capture transaction identity mismatch")
            _current_plan_identity(project_root, receipt)
            if receipt.get("state") != "finalized" or receipt.get("completed_roles") != list(REQUIRED_ROLES):
                raise CaptureError("followup_ordinary_v2_family_incomplete", "ordinary compact freeze requires all four finalized roles")
            marker = _ordinary_v2_validate_marker(
                receipt.get(ORDINARY_V2_BINDING_KEY),
                project_root=project_root,
                plan_ref=plan_ref,
                cycle_id=capture_cycle_id,
            )
            if marker["state"] != "binding":
                raise CaptureError("followup_ordinary_v2_already_frozen", "ordinary compact family was already frozen")
            if receipt.get("created_paths"):
                raise CaptureError("followup_ordinary_v2_bound_family_invalid", "ordinary compact family cannot mix V1 Created paths")
            current, contents = snapshot_followups(project_root, include_bytes=True)
            if current != receipt.get("current_followup_files"):
                raise CaptureError("followup_ordinary_v2_baseline_drift", "followups map changed before ordinary compact freeze")
            current_pi = snapshot_process_improvement_data_files(project_root, plan_ref)
            lineage = _receipt_pi_lineage(receipt, require_terminal=True)
            if current_pi != lineage["final_objects"]:
                raise CaptureError("followup_ordinary_v2_pi_drift", "process-improvement map changed before ordinary compact freeze")
            source = _ordinary_v2_current_source_identity(project_root, plan_ref, receipt)
            if marker["source_identity"] != source:
                raise CaptureError("followup_ordinary_v2_source_or_baseline_drift", "ordinary compact source identity drifted")
            baseline_sha256 = _sha256(_canonical_json_bytes(current))
            if marker["baseline_followups_snapshot_sha256"] != baseline_sha256:
                raise CaptureError("followup_ordinary_v2_source_or_baseline_drift", "ordinary compact baseline drifted")
            if os.path.lexists(v2_frozen_manifest_path(project_root, plan_ref)):
                raise CaptureError("followup_ordinary_v2_manifest_exists", "ordinary compact freeze requires an absent canonical frozen manifest")
            submission_fd = _ordinary_v2_open_submission_directory(
                cycle_fd,
                plan_ref=plan_ref,
                cycle_id=capture_cycle_id,
                create=False,
            )
            bound_fd = _ordinary_v2_open_bound_directory(
                cycle_fd,
                plan_ref=plan_ref,
                cycle_id=capture_cycle_id,
                create=False,
            )
            try:
                names = sorted(os.listdir(bound_fd))
                if names != sorted(f"{role}.json" for role in REQUIRED_ROLES):
                    raise CaptureError("followup_ordinary_v2_bound_family_invalid", "ordinary bound family must contain exactly four role files")
                declarations: list[dict[str, Any]] = []
                for role, bound in zip(REQUIRED_ROLES, marker["bound_declarations"], strict=True):
                    declaration, actual_hash = _ordinary_v2_read_bound_role(
                        bound_fd,
                        plan_ref=plan_ref,
                        cycle_id=capture_cycle_id,
                        role=role,
                    )
                    result = receipt["role_results"].get(role)
                    if (
                        actual_hash != bound["sha256"]
                        or not isinstance(result, dict)
                        or result.get("role_output_kind") != "ordinary_v2_compact"
                        or not isinstance(result.get("ordinary_compact_declaration"), dict)
                    ):
                        raise CaptureError("followup_ordinary_v2_bound_family_invalid", "ordinary compact role proof drifted")
                    submission, submission_hash, submission_object = _ordinary_v2_read_submission(
                        submission_fd,
                        plan_ref=plan_ref,
                        capture_cycle_id=capture_cycle_id,
                        role=role,
                    )
                    if (
                        result.get("ordinary_submission_path") != submission_object["path"]
                        or result.get("ordinary_submission_sha256") != submission_hash
                        or result.get("ordinary_submission_object_identity") != submission_object
                        or result.get("ordinary_submission_prepared_receipt_content_sha256")
                        != submission["prepared_receipt_content_sha256"]
                        or result.get("ordinary_submission_prepared_receipt_object_identity")
                        != submission["prepared_receipt_object_identity"]
                        or result["ordinary_compact_declaration"] != submission["compact_declaration"]
                        or result.get("stdout_sha256") != submission["compact_declaration_sha256"]
                    ):
                        raise CaptureError(
                            "followup_ordinary_v2_submission_path_drift",
                            "ordinary submission proof differs from the receipt-bound role result",
                        )
                    expected = _ordinary_v2_declaration(source, current, result["ordinary_compact_declaration"])
                    if set(declaration) != ORDINARY_V2_FULL_DECLARATION_KEYS or declaration != expected:
                        raise CaptureError("followup_ordinary_v2_bound_family_invalid", "ordinary bound declaration differs from helper-owned compact proof")
                    validate_v2_declaration(project_root, plan_ref, declaration)
                    declarations.append(declaration)
            finally:
                os.close(bound_fd)
                os.close(submission_fd)
            frozen = freeze_v2_declarations(project_root, plan_ref, declarations)
            carrier_paths = {str(row["followup_path"]) for row in frozen["proposed_rows"]}
            if len(carrier_paths) > 1:
                raise CaptureError(
                    "followup_ordinary_v2_bound_family_invalid",
                    "ordinary compact row-bearing family must derive exactly one carrier",
                )
            carrier_path = next(iter(carrier_paths), None)
            if carrier_path is not None:
                try:
                    from followups_apply import ApplyError, _append_rows, apply_frozen_rows, load_frozen_manifest
                except ModuleNotFoundError:  # package import in focused unittest invocation
                    from scripts.followups_apply import ApplyError, _append_rows, apply_frozen_rows, load_frozen_manifest
                source_entry = _ordinary_v2_read_tree_entry(
                    project_root,
                    tree_oid=source["source_terminal_commit_oid"],
                    carrier_path=carrier_path,
                    reason_code="followup_ordinary_v2_bound_family_invalid",
                )
                if source_entry is not None:
                    carrier_bytes = contents.get(carrier_path)
                    if carrier_bytes is None:
                        try:
                            _manifest, rows = load_frozen_manifest(frozen)
                            carrier_rows = [row for row in rows if row.followup_path == carrier_path]
                            carrier_bytes = _append_rows(b"", carrier_path, carrier_rows, project_root)
                        except ApplyError as exc:
                            raise CaptureError(
                                "followup_ordinary_v2_bound_family_invalid",
                                "ordinary compact source carrier cannot derive the canonical sole-writer entry",
                                ordinary_v2_reason=exc.reason_code,
                            ) from exc
                    if not isinstance(carrier_bytes, bytes):
                        raise CaptureError(
                            "followup_ordinary_v2_bound_family_invalid",
                            "ordinary compact carrier bytes are unavailable for immutable-source validation",
                        )
                    canonical_entry = _ordinary_v2_canonical_carrier_entry(
                        project_root,
                        carrier_path=carrier_path,
                        carrier_bytes=carrier_bytes,
                        reason_code="followup_ordinary_v2_bound_family_invalid",
                    )
                    if source_entry != canonical_entry:
                        raise CaptureError(
                            "followup_ordinary_v2_bound_family_invalid",
                            "ordinary compact source entry differs from the canonical ordinary entry",
                            path=carrier_path,
                        )
                if carrier_path in current:
                    try:
                        replay = apply_frozen_rows(project_root, frozen, mutate=False)
                    except ApplyError as exc:
                        raise CaptureError(
                            "followup_ordinary_v2_bound_family_invalid",
                            "ordinary compact existing carrier cannot satisfy sole-writer replay admission",
                            ordinary_v2_reason=exc.reason_code,
                        ) from exc
                    if replay.get("state") != "idempotent" or replay.get("changed_paths") != []:
                        raise CaptureError(
                            "followup_ordinary_v2_bound_family_invalid",
                            "ordinary compact existing carrier must be an exact idempotent replay",
                        )
            manifest_path = persist_v2_frozen_manifest(project_root, plan_ref, frozen)
            _manifest_file_object, manifest_bytes = read_repo_regular_path(project_root, manifest_path)
            manifest_object = _load_json_bytes(manifest_bytes, "followup_ordinary_v2_manifest_invalid")
            if manifest_bytes != _canonical_json_bytes(manifest_object) + b"\n" or manifest_object != frozen:
                raise CaptureError("followup_ordinary_v2_manifest_invalid", "ordinary compact frozen manifest bytes differ from the helper result")
            next_receipt = _next_receipt(receipt)
            next_marker = json.loads(_canonical_json_bytes(marker).decode("utf-8"))
            next_marker.update(
                {
                    "state": "frozen",
                    "frozen_manifest_path": manifest_path,
                    "frozen_manifest_sha256": _sha256(manifest_bytes),
                }
            )
            next_receipt[ORDINARY_V2_BINDING_KEY] = next_marker
            try:
                published = _publish_mutation(host, cycle_fd, capture_cycle_id, raw, next_receipt)
            except Exception:
                # A normal publication error must not strand a manifest that a
                # later fresh cycle could mistake for its own ordinary proof.
                with contextlib.suppress(OSError):
                    current_object, current_bytes = read_repo_regular_path(project_root, manifest_path)
                    del current_object
                    if _sha256(current_bytes) == next_marker["frozen_manifest_sha256"]:
                        os.unlink(project_root / manifest_path)
                raise
            payload = _response(published, state="frozen", reason_code="ordinary_v2_compact_frozen")
            payload.update(
                {
                    "declaration_roles": list(REQUIRED_ROLES),
                    "expected_owned_tuples": frozen["expected_owned_tuples"],
                    "frozen_manifest_path": manifest_path,
                }
            )
            return payload
        finally:
            os.close(cycle_fd)


def _ordinary_v2_post_apply_expectation(
    project_root: Path,
    *,
    plan_ref: str,
    cycle_id: str,
    receipt: dict[str, Any],
    cycle_fd: int,
    current_snapshot: Mapping[str, Any],
    current_bytes: Mapping[str, bytes],
) -> dict[str, Any]:
    """Return the one receipt-bound post-apply carrier that may differ from baseline."""

    marker, source, declarations = _ordinary_v2_load_frozen_binding(
        project_root,
        plan_ref=plan_ref,
        cycle_id=cycle_id,
        receipt=receipt,
        cycle_fd=cycle_fd,
    )
    manifest_path = str(marker["frozen_manifest_path"])
    _manifest_file_object, manifest_bytes = read_repo_regular_path(project_root, manifest_path)
    manifest_object = _load_json_bytes(manifest_bytes, "followup_ordinary_v2_manifest_invalid")
    if _sha256(manifest_bytes) != marker["frozen_manifest_sha256"] or manifest_bytes != _canonical_json_bytes(manifest_object) + b"\n":
        raise CaptureError("followup_ordinary_v2_manifest_invalid", "ordinary compact frozen manifest digest drifted")
    try:
        from followups_apply import ApplyError, _append_rows, load_frozen_manifest
    except ModuleNotFoundError:  # package import in focused unittest invocation
        from scripts.followups_apply import ApplyError, _append_rows, load_frozen_manifest
    try:
        frozen, rows = load_frozen_manifest(manifest_object)
    except ApplyError as exc:
        raise CaptureError("followup_ordinary_v2_manifest_invalid", str(exc)) from exc
    if (
        frozen.get("plan_ref") != plan_ref
        or frozen.get("source_terminal_commit_oid") != source["source_terminal_commit_oid"]
        or frozen.get("source_plan_blob_oid") != source["source_plan_blob_oid"]
        or frozen.get("source_plan_sha256") != source["source_plan_sha256"]
        or frozen.get("baseline_followups_snapshot") != receipt.get("current_followup_files")
        or frozen.get("baseline_followups_snapshot_sha256") != marker["baseline_followups_snapshot_sha256"]
        or frozen.get("declaration_roles") != list(REQUIRED_ROLES)
    ):
        raise CaptureError("followup_ordinary_v2_manifest_invalid", "ordinary compact manifest identity differs from receipt proof")
    expected_rows: list[dict[str, Any]] = []
    owners: dict[str, str] = {}
    for declaration in declarations:
        role = str(declaration["role"])
        for row in declaration["proposed_rows"]:
            followup_path, payload, digest = _v2_row_from_declaration(row, declaration_role=role)
            key = f"{payload['source_ref']}\u0000{payload['item_id']}"
            owners[key] = role
            expected_rows.append(
                {
                    "followup_path": followup_path,
                    "payload": payload,
                    "row_digest": digest,
                }
            )
    expected_rows.sort(key=lambda row: (str(row["payload"]["source_ref"]), str(row["payload"]["item_id"])))
    if frozen.get("tuple_owners") != owners or frozen.get("proposed_rows") != expected_rows:
        raise CaptureError(
            "followup_ordinary_v2_manifest_invalid",
            "ordinary compact manifest row union differs from bound declarations",
        )
    if not rows:
        raise CaptureError("followup_ordinary_v2_post_apply_invalid", "empty ordinary compact union has no post-apply carrier")

    carrier_paths = sorted({row.followup_path for row in rows})
    if len(carrier_paths) != 1:
        raise CaptureError("followup_ordinary_v2_post_apply_invalid", "ordinary compact proof did not derive exactly one carrier")
    carrier_path = carrier_paths[0]
    baseline = frozen.get("baseline_followups_snapshot")
    if not isinstance(baseline, dict):
        raise CaptureError("followup_ordinary_v2_post_apply_invalid", "ordinary compact carrier baseline proof is invalid")
    carrier_in_baseline = carrier_path in baseline
    try:
        carrier_object, carrier_bytes = read_followup_path(project_root, carrier_path)
        if carrier_in_baseline and carrier_object != baseline[carrier_path]:
            raise CaptureError(
                "followup_ordinary_v2_post_apply_invalid",
                "ordinary compact existing carrier object differs from the frozen baseline",
            )
        canonical_bytes = _append_rows(
            carrier_bytes if carrier_in_baseline else b"",
            carrier_path,
            rows,
            project_root,
        )
    except (CaptureError, ApplyError) as exc:
        raise CaptureError("followup_ordinary_v2_post_apply_invalid", str(exc), ordinary_v2_reason=exc.reason_code) from exc
    if carrier_bytes != canonical_bytes:
        raise CaptureError("followup_ordinary_v2_post_apply_invalid", "ordinary compact carrier bytes differ from the canonical sole-writer render")
    index_expectation = _terminal_index_refresh_expectation(
        project_root,
        plan_ref=plan_ref,
        frozen_manifest=manifest_object,
        capture_cycle_id=cycle_id,
        current_snapshot=current_snapshot,
        current_bytes=current_bytes,
    )
    generated_entries = (
        {str(index_expectation["path"]): current_bytes[str(index_expectation["path"])]}
        if index_expectation is not None
        else None
    )
    head_phase = _ordinary_v2_validate_post_apply_head(
        project_root,
        source=source,
        carrier_path=carrier_path,
        carrier_bytes=carrier_bytes,
        generated_entries=generated_entries,
    )
    proof = v2_external_proof(project_root, manifest_object)
    if proof.get("state") != "external_clean" or proof.get("reason") != "exact_v2_tuple_proof":
        raise CaptureError("followup_ordinary_v2_post_apply_invalid", "ordinary compact tuple proof is not non-empty external_clean")
    expected_rows = [
        {
            "source_ref": row.tuple[0],
            "item_id": row.tuple[1],
            "tuple_owner": row.owner,
            "row_digest": row.digest,
        }
        for row in rows
    ]
    expected_rows.sort(key=lambda item: (item["source_ref"], item["item_id"]))
    proof_rows = proof.get("proof_rows")
    if not isinstance(proof_rows, list):
        raise CaptureError("followup_ordinary_v2_post_apply_invalid", "ordinary compact tuple proof rows are invalid")
    actual_rows = [
        {
            "source_ref": row.get("source_ref"),
            "item_id": row.get("item_id"),
            "tuple_owner": row.get("tuple_owner"),
            "row_digest": row.get("declared_row_digest"),
        }
        for row in proof_rows
        if isinstance(row, dict)
    ]
    actual_rows.sort(key=lambda item: (str(item["source_ref"]), str(item["item_id"])))
    if len(actual_rows) != len(proof_rows) or actual_rows != expected_rows:
        raise CaptureError("followup_ordinary_v2_post_apply_invalid", "ordinary compact tuple proof differs from the frozen row union")
    result: dict[str, Any] = {"path": carrier_path, "expected_object": carrier_object, "head_phase": head_phase}
    if index_expectation is not None:
        result["index_expectation"] = index_expectation
    return result


def _ordinary_v2_pending_index_transition(
    project_root: Path, *, plan_ref: str, cycle_id: str,
    source: dict[str, str] | None, expectation: dict[str, Any] | None,
    current: Mapping[str, Any], current_bytes: Mapping[str, bytes],
) -> None:
    """Prove the inverse bundle-kind transition from immutable generated inputs."""
    if source is None or expectation is None or expectation["head_phase"] != "pending":
        raise _post_cas_semantic_identity_mismatch("semantic transition requires a pending ordinary transaction")
    head = _git(project_root, "rev-parse", "HEAD^{commit}").stdout.decode("ascii").strip()
    paths = _ordinary_v2_pending_bundle(project_root, source=source, head=head)
    carrier = expectation["path"]
    if FOLLOWUPS_INDEX_PATH not in paths or carrier in paths or not expectation.get("index_expectation"):
        raise _post_cas_semantic_identity_mismatch("semantic transition requires an owned index and external raw carrier")
    for tree in (source["source_terminal_commit_oid"], head):
        if _ordinary_v2_read_tree_entry(project_root, tree_oid=tree, carrier_path=carrier,
                                        reason_code="followup_capture_semantic_identity_mismatch") is not None:
            raise _post_cas_semantic_identity_mismatch("pending raw carrier must be absent from source and HEAD")
    if _git(project_root, "ls-files", "-z", "--", carrier).stdout:
        raise _post_cas_semantic_identity_mismatch("pending raw carrier must remain untracked")
    if _git(project_root, "diff", "--quiet", head, "--", FOLLOWUPS_INDEX_PATH, check=False).returncode != 1:
        raise _post_cas_semantic_identity_mismatch("pending generated index must be the canonical bundle delta")
    _, manifest_bytes = read_repo_regular_path(
        project_root, v2_frozen_manifest_path(project_root, plan_ref).relative_to(project_root).as_posix(),
    )
    manifest = _load_json_bytes(manifest_bytes, "followup_ordinary_v2_manifest_invalid")
    entry = _ordinary_v2_read_tree_entry(
        project_root, tree_oid=source["source_terminal_commit_oid"], carrier_path=FOLLOWUPS_INDEX_PATH,
        reason_code="followup_capture_semantic_identity_mismatch",
    )
    if entry is None or entry[:2] != ("100644", "blob"):
        raise _post_cas_semantic_identity_mismatch("pending index lacks a regular source before-image")
    before = _git(project_root, "cat-file", "blob", entry[2]).stdout
    baseline = manifest["baseline_followups_snapshot"].get(FOLLOWUPS_INDEX_PATH)
    if baseline != {"sha256": _sha256(before), "file_type": "regular", "st_size": len(before)}:
        raise _post_cas_semantic_identity_mismatch("pending index baseline differs from source")
    _terminal_index_refresh_expectation(
        project_root, plan_ref=plan_ref, frozen_manifest=manifest, capture_cycle_id=cycle_id,
        current_snapshot=current, current_bytes=current_bytes, index_before_bytes=before,
    )


def _post_cas_semantic_identity_mismatch(message: str) -> CaptureError:
    """Keep the exceptional reader route on the existing fail-closed surface."""

    return CaptureError("followup_capture_semantic_identity_mismatch", message)


def _post_cas_semantic_identity_fields(value: Any) -> tuple[str, str, str]:
    if (
        not isinstance(value, list)
        or len(value) != 3
        or any(not isinstance(item, str) or not item for item in value)
    ):
        raise _post_cas_semantic_identity_mismatch("post-CAS semantic fields are invalid")
    return value[0], value[1], value[2]


def _post_cas_semantic_identity_section(text: str, title: str) -> str:
    match = re.search(
        rf"^##[ \t]+{re.escape(title)}\s*$([\s\S]*?)(?=^##[ \t]+|\Z)",
        text,
        re.MULTILINE,
    )
    return match.group(1) if match else ""


def _post_cas_semantic_identity_normalize_bundle_path(project_root: Path, raw: str) -> str:
    value = raw.strip().strip("`")
    candidate = Path(value)
    root = project_root.resolve()
    if candidate.is_absolute():
        try:
            value = candidate.resolve().relative_to(root).as_posix()
        except ValueError as exc:
            raise _post_cas_semantic_identity_mismatch(
                "post-CAS canonical bundle member is outside the project root"
            ) from exc
    # Canonical source targets may be root files (e.g. SECURITY.md). This
    # reader grammar is separate from nested-only follow-up staging paths.
    parts = PurePosixPath(value).parts
    if (
        not value or not parts or PurePosixPath(value).is_absolute()
        or PurePosixPath(value).as_posix() != value
        or any(part in {".", ".."} for part in parts)
        or "\\" in value or "\x00" in value
    ):
        raise _post_cas_semantic_identity_mismatch("post-CAS canonical bundle member is invalid")
    return value


def _post_cas_semantic_identity_read_bundle_text(project_root: Path, rel_path: str) -> str:
    try:
        snapshot = fs_object_identity.snapshot_regular_or_absent(project_root, rel_path)
        if snapshot.state != "regular" or snapshot.data is None:
            raise _post_cas_semantic_identity_mismatch("canonical bundle member is not regular")
        return snapshot.data.decode("utf-8", errors="strict")
    except (CaptureError, fs_object_identity.ObjectIdentityError, UnicodeDecodeError) as exc:
        raise _post_cas_semantic_identity_mismatch(
            "post-CAS canonical bundle member is not a safe UTF-8 regular file"
        ) from exc


def _post_cas_semantic_identity_durable_review_json_refs(text: str) -> list[str]:
    refs: dict[str, None] = {}
    lines = text.splitlines()
    for index, line in enumerate(lines):
        context = " ".join(lines[max(0, index - 1) : index + 2]).lower()
        if any(marker in context for marker in POST_CAS_TRANSIENT_RECEIPT_MARKERS):
            continue
        for raw in POST_CAS_REVIEW_JSON_RE.findall(line):
            refs.setdefault(raw.strip("`'\""), None)
    return list(refs)


def _post_cas_semantic_identity_canonical_bundle_paths(
    project_root: Path,
    *,
    plan_ref: str,
    _source_head: tuple[str, str] | None = None,
) -> tuple[str, ...]:
    """Rebuild the current same-root closeout inventory without caller input.

    This is deliberately a narrow private mirror of the existing canonical
    bundle membership inputs: origin plan, primary code draft and targets,
    review carriers/assets, durable review JSON, and plan-resident risk support.
    Pending and post-CAS proofs cannot accept a caller's projected subset.
    The pending caller additionally binds membership metadata before parsing.
    """

    plan_ref = normalize_plan_ref(plan_ref)
    root = project_root.resolve()
    try:
        git_root = _git(root, "rev-parse", "--show-toplevel").stdout.decode("utf-8", errors="strict").strip()
    except (CaptureError, UnicodeDecodeError) as exc:
        raise _post_cas_semantic_identity_mismatch(
            "post-CAS canonical bundle cannot resolve the project Git root"
        ) from exc
    if not git_root or Path(git_root).resolve() != root:
        raise _post_cas_semantic_identity_mismatch(
            "post-CAS canonical bundle must stay in the supplied project root"
        )

    def read_metadata(path: str) -> str:
        text = _post_cas_semantic_identity_read_bundle_text(root, path)
        if _source_head is not None:
            source_oid, head = _source_head
            entries = [_ordinary_v2_read_tree_entry(
                root, tree_oid=tree, carrier_path=path,
                reason_code="followup_ordinary_v2_post_apply_invalid",
            ) for tree in (source_oid, head)]
            try:
                snapshot = fs_object_identity.snapshot_regular_or_absent(root, path)
            except fs_object_identity.ObjectIdentityError as exc:
                raise _post_cas_semantic_identity_mismatch("pending inventory metadata is unsafe") from exc
            if snapshot.state != "regular" or snapshot.data is None:
                raise _post_cas_semantic_identity_mismatch("pending inventory metadata is not regular")
            oid = _git(root, "hash-object", "--stdin", input_bytes=snapshot.data).stdout.decode("ascii").strip()
            if (
                entries[0] is None or entries[0] != entries[1]
                or entries[0] != (snapshot.git_mode, "blob", oid)
                or _git(root, "diff", "--cached", "--quiet", head, "--", path, check=False).returncode != 0
            ):
                raise CaptureError("followup_ordinary_v2_post_apply_invalid", "pending inventory metadata differs from source", path=path)
        return text

    # Bind membership-defining bytes before extracting targets or review assets.
    plan_text = read_metadata(plan_ref)
    paths: set[str] = {plan_ref}

    def add(raw: str) -> str:
        path = _post_cas_semantic_identity_normalize_bundle_path(root, raw)
        paths.add(path)
        return path

    try:
        import plan_lint
    except ImportError as exc:
        raise _post_cas_semantic_identity_mismatch(
            "post-CAS canonical bundle cannot load plan membership authority"
        ) from exc

    plan_path = root / plan_ref
    support_manifest = plan_lint.collect_plan_risk_lane_support_refs(plan_path, project_root=root)
    if support_manifest.diagnostics:
        raise _post_cas_semantic_identity_mismatch(
            "post-CAS canonical risk-support inventory is invalid"
        )
    for support_ref, _support_sha256 in support_manifest.records:
        add(support_ref)

    code_draft_refs = plan_lint.extract_code_draft_refs(plan_text.splitlines())
    code_draft_path = plan_lint.select_primary_code_draft_path(
        plan_path,
        code_draft_refs,
        plan_repo_root=root,
    )
    if code_draft_path is None:
        fallback = root / "docs" / "code_drafts" / f"{Path(plan_ref).stem}__code_draft.md"
        if fallback.exists():
            code_draft_path = fallback.resolve()
    if code_draft_path is None:
        raise _post_cas_semantic_identity_mismatch(
            "post-CAS canonical bundle lacks its primary code draft"
        )
    code_draft_rel = _post_cas_semantic_identity_normalize_bundle_path(root, str(code_draft_path))
    paths.add(code_draft_rel)
    code_draft_text = read_metadata(code_draft_rel)
    meta, meta_error = plan_lint.extract_code_draft_meta(root / code_draft_rel)
    if meta is None or meta_error or meta.get("plan") != plan_ref:
        raise _post_cas_semantic_identity_mismatch(
            "post-CAS canonical code-draft inventory is invalid"
        )
    targets = meta.get("targets")
    if not isinstance(targets, list) or not targets:
        raise _post_cas_semantic_identity_mismatch(
            "post-CAS canonical bundle lacks code-draft targets"
        )
    for target in targets:
        if not isinstance(target, dict) or not isinstance(target.get("path"), str):
            raise _post_cas_semantic_identity_mismatch(
                "post-CAS canonical code-draft target is invalid"
            )
        add(target["path"])
    deleted_paths = meta.get("deleted_paths") or []
    if not isinstance(deleted_paths, list) or deleted_paths:
        raise _post_cas_semantic_identity_mismatch(
            "post-CAS canonical bundle has unsupported deleted members"
        )

    review_refs = POST_CAS_REVIEW_RE.findall(
        _post_cas_semantic_identity_section(plan_text, "Review artifacts")
    )
    if not review_refs:
        raise _post_cas_semantic_identity_mismatch(
            "post-CAS canonical bundle lacks its review artifact"
        )
    review_texts: list[str] = []
    for raw_review_ref in review_refs:
        review_rel = add(raw_review_ref)
        review_text = read_metadata(review_rel)
        review_texts.append(review_text)
        for asset_ref in POST_CAS_REVIEW_ASSET_RE.findall(review_text):
            add(asset_ref)

    for carrier_text in (plan_text, code_draft_text, *review_texts):
        for durable_ref in _post_cas_semantic_identity_durable_review_json_refs(carrier_text):
            add(durable_ref)

    for path in sorted(paths):
        _post_cas_semantic_identity_read_bundle_text(root, path)
    return tuple(sorted(paths))


def _post_cas_semantic_identity_bundle_entries(
    project_root: Path,
    *,
    plan_ref: str,
    current_head: str,
    entries: Any,
) -> None:
    """Reopen the canonical current-tree entries without trusting the caller.

    The ordinary carrier proof above validates its own marker-bound follow-up
    entry.  The semantic transition additionally needs every exact closeout
    bundle object to be a regular current-worktree object, an exact HEAD tree
    entry, and absent from both the index and worktree deltas.  This avoids
    treating the derived ``already_materialized`` label as authority.
    """

    if not isinstance(entries, list) or not entries:
        raise _post_cas_semantic_identity_mismatch("post-CAS bundle tree proof is missing")
    expected_paths = _post_cas_semantic_identity_canonical_bundle_paths(
        project_root,
        plan_ref=plan_ref,
    )
    actual_entries: list[dict[str, str]] = []
    seen_paths: set[str] = set()
    for item in entries:
        if not isinstance(item, dict) or set(item) != {"path", "mode", "oid"}:
            raise _post_cas_semantic_identity_mismatch("post-CAS bundle tree proof is malformed")
        raw_path = item.get("path")
        mode = item.get("mode")
        oid = item.get("oid")
        if not isinstance(raw_path, str) or not isinstance(mode, str) or not isinstance(oid, str):
            raise _post_cas_semantic_identity_mismatch("post-CAS bundle tree proof has invalid values")
        try:
            path = _post_cas_semantic_identity_normalize_bundle_path(project_root, raw_path)
        except CaptureError as exc:
            raise _post_cas_semantic_identity_mismatch("post-CAS bundle path is invalid") from exc
        if (
            raw_path != path
            or path in seen_paths
            or mode not in {"100644", "100755"}
            or not OID_RE.fullmatch(oid)
        ):
            raise _post_cas_semantic_identity_mismatch("post-CAS bundle tree proof is ambiguous")
        seen_paths.add(path)
        try:
            snapshot = fs_object_identity.snapshot_regular_or_absent(project_root, path)
        except fs_object_identity.ObjectIdentityError as exc:
            raise _post_cas_semantic_identity_mismatch("post-CAS bundle object is unsafe") from exc
        if snapshot.state != "regular" or snapshot.data is None or snapshot.git_mode != mode:
            raise _post_cas_semantic_identity_mismatch("post-CAS bundle worktree object differs from its tree entry")
        expected = _ordinary_v2_read_tree_entry(
            project_root,
            tree_oid=current_head,
            carrier_path=path,
            reason_code="followup_capture_semantic_identity_mismatch",
        )
        if expected != (mode, "blob", oid):
            raise _post_cas_semantic_identity_mismatch("post-CAS bundle tree entry differs from its proof")
        actual_oid = _git(project_root, "hash-object", "--stdin", input_bytes=snapshot.data).stdout.decode(
            "ascii", errors="replace"
        ).strip()
        if actual_oid != oid:
            raise _post_cas_semantic_identity_mismatch("post-CAS bundle worktree bytes differ from HEAD")
        for args in (
            ("diff", "--quiet", "HEAD", "--", path),
            ("diff", "--cached", "--quiet", "HEAD", "--", path),
        ):
            if _git(project_root, *args, check=False).returncode != 0:
                raise _post_cas_semantic_identity_mismatch("post-CAS bundle has an unstaged or staged delta")
        untracked = _git(
            project_root,
            "ls-files",
            "--others",
            "--exclude-standard",
            "-z",
            "--",
            path,
        ).stdout
        if untracked:
            raise _post_cas_semantic_identity_mismatch("post-CAS bundle has an untracked object")
        actual_entries.append({"path": path, "mode": mode, "oid": oid})
    if actual_entries != sorted(actual_entries, key=lambda item: item["path"]):
        raise _post_cas_semantic_identity_mismatch("post-CAS bundle tree proof is not canonical")
    if entries != actual_entries:
        raise _post_cas_semantic_identity_mismatch("post-CAS bundle tree proof differs from fresh entries")
    if tuple(item["path"] for item in actual_entries) != expected_paths:
        raise _post_cas_semantic_identity_mismatch(
            "post-CAS bundle tree proof does not match the canonical inventory"
        )


def _validate_post_cas_semantic_identity_transition(
    project_root: Path,
    *,
    plan_ref: str,
    cycle_id: str,
    receipt: dict[str, Any],
    semantic_fields: tuple[str, str, str],
    proof: Any,
    marker: dict[str, Any] | None,
    source: dict[str, str] | None,
    ordinary_v2_expectation: dict[str, Any] | None,
    lineage: dict[str, Any],
    current_pi: dict[str, Any],
    checkpoint_proof: dict[str, Any] | None,
) -> None:
    """Accept precisely one already-landed ordinary-V2 semantic readback.

    The proof is intentionally ephemeral.  It records what the only caller
    (docs_closeout) just observed, then this reader rereads the receipt,
    source, ordinary binding, PI objects and current Git tree before returning
    a result.  No outcome-only closeout field participates in this check.
    """

    if not isinstance(proof, dict) or set(proof) != POST_CAS_SEMANTIC_IDENTITY_PROOF_KEYS:
        raise _post_cas_semantic_identity_mismatch("post-CAS semantic proof has unknown or missing fields")
    receipt_fields = _post_cas_semantic_identity_fields(proof.get("receipt_semantic_fields"))
    current_fields = _post_cas_semantic_identity_fields(proof.get("current_semantic_fields"))
    identity = receipt["identity_payload"]
    actual = (
        identity["semantic_status"],
        identity["semantic_status_norm"],
        identity["semantic_closeout_kind"],
    )
    if (
        actual != receipt_fields
        or semantic_fields != current_fields
        or actual[0] not in {"Done", "Superseded"}
        or actual[1] != actual[0].lower()
        or actual[2] != "staged_empty"
        or current_fields != (actual[0], actual[1], "already_materialized")
    ):
        raise _post_cas_semantic_identity_mismatch("post-CAS semantic transition is not the exact allowed one-way transition")
    if (
        proof.get("route") != POST_CAS_SEMANTIC_IDENTITY_TRANSITION_ROUTE
        or proof.get("plan_ref") != plan_ref
        or proof.get("capture_cycle_id") != cycle_id
        or proof.get("receipt_content_sha256") != receipt.get("receipt_content_sha256")
        or proof.get("semantic_closeout_identity") != receipt.get("semantic_closeout_identity")
        or proof.get("plan_sha256") != receipt.get("plan_sha256")
        or proof.get("terminal_status_line") != receipt.get("terminal_status_line")
        or proof.get("pi_final_objects") != lineage.get("final_objects")
        or proof.get("pi_final_objects") != current_pi
        or checkpoint_proof is None
        or marker is None
        or source is None
        or ordinary_v2_expectation is None
    ):
        raise _post_cas_semantic_identity_mismatch("post-CAS semantic proof does not bind the current receipt lineage")
    if (
        proof.get("source_terminal_commit_oid") != source.get("source_terminal_commit_oid")
        or proof.get("source_plan_blob_oid") != source.get("source_plan_blob_oid")
        or proof.get("source_plan_sha256") != source.get("source_plan_sha256")
        or proof.get("frozen_manifest_path") != marker.get("frozen_manifest_path")
        or proof.get("frozen_manifest_sha256") != marker.get("frozen_manifest_sha256")
    ):
        raise _post_cas_semantic_identity_mismatch("post-CAS semantic proof does not bind the frozen ordinary source")
    current_head = _git(project_root, "rev-parse", "--verify", "HEAD^{commit}").stdout.decode(
        "ascii", errors="replace"
    ).strip()
    if not OID_RE.fullmatch(current_head) or proof.get("current_head") != current_head:
        raise _post_cas_semantic_identity_mismatch("post-CAS semantic proof has a stale current HEAD")
    _post_cas_semantic_identity_bundle_entries(
        project_root,
        plan_ref=plan_ref,
        current_head=current_head,
        entries=proof.get("bundle_tree_entries"),
    )


def read_capture(
    project_root: Path,
    plan_ref: str,
    cycle_id: str,
    *,
    semantic_fields: tuple[str, str, str] | None = None,
    _post_cas_semantic_identity_proof: dict[str, Any] | None = None,
    _include_pending_transition: bool = False,
) -> dict[str, Any]:
    plan_ref = normalize_plan_ref(plan_ref)
    with CaptureHost(project_root, plan_ref) as host:
        cycle_fd, cycle_identity = _open_cycle(host, cycle_id)
        try:
            receipt, _raw, receipt_identity = _read_receipt(cycle_fd, plan_ref, cycle_id)
            if receipt["cycle_directory_identity"] != cycle_identity or receipt["transaction_host_identity"] != host.transaction_host_identity():
                raise CaptureError("followup_capture_host_object_drift", "capture transaction identity mismatch")
            _current_plan_identity(project_root, receipt)
            post_cas_transition_requested = False
            pending_transition_requested = False
            if _post_cas_semantic_identity_proof is not None and semantic_fields is None:
                raise _post_cas_semantic_identity_mismatch("post-CAS semantic proof requires explicit semantic fields")
            if semantic_fields is not None:
                identity = receipt["identity_payload"]
                actual = (identity["semantic_status"], identity["semantic_status_norm"], identity["semantic_closeout_kind"])
                if actual != semantic_fields:
                    pending_transition_requested = (
                        actual[0] in {"Done", "Superseded"}
                        and actual == (actual[0], actual[0].lower(), "already_materialized")
                        and semantic_fields == (actual[0], actual[1], "staged_empty")
                        and _post_cas_semantic_identity_proof is None
                    )
                    if not pending_transition_requested:
                        if _post_cas_semantic_identity_proof is None:
                            raise CaptureError("followup_capture_semantic_identity_mismatch", "fresh docs-closeout semantic identity differs from receipt")
                        post_cas_transition_requested = True
                elif _post_cas_semantic_identity_proof is not None:
                    raise _post_cas_semantic_identity_mismatch("post-CAS semantic proof cannot accompany literal semantic equality")
            if receipt["state"] != "finalized" or receipt["completed_roles"] != receipt["required_roles"]:
                raise CaptureError(
                    "followup_capture_incomplete",
                    "capture cycle is not aggregate finalized",
                    capture_state=receipt["state"],
                    completed_roles=receipt["completed_roles"],
                )
            lineage = _receipt_pi_lineage(receipt, require_terminal=True)
            if lineage["ownership_state"] != "finalized":
                raise CaptureError(
                    "followup_capture_incomplete",
                    "finalized aggregate receipt did not publish finalized PI ownership",
                    pi_ownership_state=lineage["ownership_state"],
                )
            checkpoint_proof: dict[str, Any] | None = None
            if "general_pi_checkpoint" in receipt:
                if receipt.get("general_pi_checkpoint") is None:
                    raise CaptureError(
                        "followup_capture_pi_general_checkpoint_missing",
                        "finalized current-schema aggregate receipt lacks the general-PI checkpoint",
                    )
                checkpoint_proof = general_pi_checkpoint_proof(project_root, plan_ref, receipt)
            current, current_bytes = snapshot_followups(project_root, include_bytes=True)
            ordinary_v2_expectation: dict[str, Any] | None = None
            ordinary_v2_marker: dict[str, Any] | None = None
            ordinary_v2_source: dict[str, str] | None = None
            if ORDINARY_V2_BINDING_KEY in receipt:
                marker = _ordinary_v2_validate_marker(
                    receipt.get(ORDINARY_V2_BINDING_KEY),
                    project_root=project_root,
                    plan_ref=plan_ref,
                    cycle_id=cycle_id,
                    require_frozen=True,
                )
                # A frozen zero family is still receipt authority: validate its
                # exact bound files/manifest even though it adds no durable path.
                if marker["state"] == "frozen":
                    ordinary_v2_marker, ordinary_v2_source, _declarations = _ordinary_v2_load_frozen_binding(
                        project_root,
                        plan_ref=plan_ref,
                        cycle_id=cycle_id,
                        receipt=receipt,
                        cycle_fd=cycle_fd,
                    )
                    _manifest_object, _manifest_bytes = read_repo_regular_path(
                        project_root,
                        str(marker["frozen_manifest_path"]),
                    )
                    if _sha256(_manifest_bytes) != marker["frozen_manifest_sha256"]:
                        raise CaptureError("followup_ordinary_v2_manifest_invalid", "ordinary compact frozen manifest digest drifted")
                    ordinary_v2_expectation = _ordinary_v2_post_apply_expectation(
                        project_root,
                        plan_ref=plan_ref,
                        cycle_id=cycle_id,
                        receipt=receipt,
                        cycle_fd=cycle_fd,
                        current_snapshot=current,
                        current_bytes=current_bytes,
                    ) if any(
                        bool(item.get("ordinary_compact_declaration", {}).get("proposed_rows"))
                        for item in receipt.get("role_results", {}).values()
                        if isinstance(item, dict)
                    ) else None
            if current != receipt["current_followup_files"]:
                if ordinary_v2_expectation is None:
                    raise CaptureError("followup_capture_path_object_drift", "current followups map differs from finalized receipt")
                expected_current = dict(receipt["current_followup_files"])
                expected_current[str(ordinary_v2_expectation["path"])] = ordinary_v2_expectation["expected_object"]
                index_expectation = ordinary_v2_expectation.get("index_expectation")
                if isinstance(index_expectation, dict):
                    expected_current[str(index_expectation["path"])] = index_expectation["expected_object"]
                if current != expected_current:
                    raise CaptureError("followup_capture_path_object_drift", "current followups map differs from the exact ordinary compact transaction")
            expectations: list[dict[str, Any]] = []
            for path in sorted(receipt["created_paths"]):
                expected_object = receipt["current_followup_files"].get(path)
                if expected_object is None or current.get(path) != expected_object:
                    raise CaptureError("followup_capture_path_object_drift", f"created path object drifted: {path}", path=path)
                expectations.append(
                    {
                        "capture_cycle_id": cycle_id,
                        "receipt_revision": receipt["receipt_revision"],
                        "receipt_content_sha256": receipt["receipt_content_sha256"],
                        "receipt_object_identity": receipt_identity,
                        "path": path,
                        "ownership_class": "ordinary_followup",
                        "expected_object": expected_object,
                        "expected_staged_mode": "100644",
                    }
                )
            host.verify_host()
            current_pi = snapshot_process_improvement_data_files(project_root, plan_ref)
            if current_pi != lineage["final_objects"]:
                raise CaptureError(
                    "followup_capture_pi_object_drift",
                    "current PI data objects differ from finalized receipt ownership",
                    expected_paths=sorted(lineage["final_objects"]),
                    current_paths=sorted(current_pi),
                )
            if pending_transition_requested:
                if checkpoint_proof is None:
                    raise _post_cas_semantic_identity_mismatch("pending transition requires general PI checkpoint")
                _ordinary_v2_pending_index_transition(
                    project_root, plan_ref=plan_ref, cycle_id=cycle_id,
                    source=ordinary_v2_source, expectation=ordinary_v2_expectation,
                    current=current, current_bytes=current_bytes,
                )
            if post_cas_transition_requested:
                assert semantic_fields is not None
                _validate_post_cas_semantic_identity_transition(
                    project_root,
                    plan_ref=plan_ref,
                    cycle_id=cycle_id,
                    receipt=receipt,
                    semantic_fields=semantic_fields,
                    proof=_post_cas_semantic_identity_proof,
                    marker=ordinary_v2_marker,
                    source=ordinary_v2_source,
                    ordinary_v2_expectation=ordinary_v2_expectation,
                    lineage=lineage,
                    current_pi=current_pi,
                    checkpoint_proof=checkpoint_proof,
                )
            host.verify_host()
            return {
                "schema_version": SCHEMA_VERSION,
                **({"_pending_index_transition": pending_transition_requested} if _include_pending_transition else {}),
                "state": "materialized" if expectations else "clean_noop",
                "reason_code": "capture_materialized" if expectations else "capture_finalized_noop",
                "capture_cycle_id": cycle_id,
                "retry_of_capture_cycle_id": receipt["retry_of_capture_cycle_id"],
                "plan_ref": plan_ref,
                "receipt_path": _receipt_relpath(plan_ref, cycle_id),
                "receipt_revision": receipt["receipt_revision"],
                "receipt_content_sha256": receipt["receipt_content_sha256"],
                "receipt_object_identity": receipt_identity,
                "semantic_closeout_identity": receipt["semantic_closeout_identity"],
                "plan_sha256": receipt["plan_sha256"],
                "terminal_status_line": receipt["terminal_status_line"],
                "required_roles": receipt["required_roles"],
                "completed_roles": receipt["completed_roles"],
                "created_paths": sorted(receipt["created_paths"]),
                "no_followups_roles": receipt["no_followups_roles"],
                "blocked_roles": receipt["blocked_roles"],
                "baseline_process_improvement_files": receipt["baseline_process_improvement_files"],
                "baseline_dirty_process_improvement_paths": receipt[
                    "baseline_dirty_process_improvement_paths"
                ],
                "current_process_improvement_files": current_pi,
                "pi_lineage_root_cycle_id": lineage["root_cycle_id"],
                "pi_adopted_from_cycle_ids": lineage["adopted_cycle_ids"],
                "pi_ownership_state": lineage["ownership_state"],
                "pi_final_objects": lineage["final_objects"],
                "pi_failure_checkpoint": lineage["failure_checkpoint"],
                "followups_blocked_predecessor_recovery_binding": receipt.get(
                    BLOCKED_PREDECESSOR_RECOVERY_BINDING_KEY
                ),
                "general_pi_checkpoint": receipt.get("general_pi_checkpoint"),
                "general_pi_checkpoint_proof": checkpoint_proof,
                "staging_expectations": expectations,
            }
        finally:
            os.close(cycle_fd)


def _git(
    root: Path,
    *args: str,
    input_bytes: bytes | None = None,
    check: bool = True,
    env_overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    env = os.environ.copy()
    # Repository identity must come from ``root`` itself.  Ambient Git state can
    # otherwise make a root without its own .git marker look like a worktree.
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE"):
        env.pop(name, None)
    if env_overrides:
        env.update(env_overrides)
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        input=input_bytes,
        capture_output=True,
        check=False,
        env=env,
    )
    if check and result.returncode != 0:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise CaptureError("followup_terminal_git_failed", message or f"git {' '.join(args)} failed")
    return result


def _load_json_bytes(data: bytes, reason_code: str) -> dict[str, Any]:
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CaptureError(reason_code, f"invalid JSON input: {exc}") from exc
    if not isinstance(payload, dict):
        raise CaptureError(reason_code, "JSON input must be an object")
    return payload


def _validate_v2_external_staging_payload_expectations(expectations: list[Any]) -> None:
    """Reject malformed optional V2 proof before any staging/Git operation."""

    for item in expectations:
        if not isinstance(item, dict) or item.get("ownership_class") != "ordinary_followup" or "ownership_proof" not in item:
            continue
        proof = item.get("ownership_proof")
        if not isinstance(proof, dict) or set(proof) != V2_EXTERNAL_FOLLOWUP_STAGING_PROOF_KEYS:
            raise CaptureError("followup_staging_payload_invalid", "ordinary V2 staging proof has unknown or missing fields")
        if proof.get("schema_version") != V2_EXTERNAL_FOLLOWUP_STAGING_PROOF_SCHEMA:
            raise CaptureError("followup_staging_payload_invalid", "ordinary V2 staging proof schema is invalid")
        for key in ("frozen_manifest_path", "carrier_path", "expected_parent_oid"):
            if not isinstance(proof.get(key), str) or not str(proof[key]).strip():
                raise CaptureError("followup_staging_payload_invalid", f"ordinary V2 staging proof lacks {key}")
        for key in ("baseline_followups_snapshot_sha256", "canonical_render_sha256"):
            if not isinstance(proof.get(key), str) or not HEX64_RE.fullmatch(str(proof[key])):
                raise CaptureError("followup_staging_payload_invalid", f"ordinary V2 staging proof has invalid {key}")
        for key in ("frozen_manifest_object", "carrier_object", "source_identity", "carrier_absence"):
            if not isinstance(proof.get(key), dict):
                raise CaptureError("followup_staging_payload_invalid", f"ordinary V2 staging proof lacks {key}")
        rows = proof.get("expected_rows")
        if not isinstance(rows, list) or not rows:
            raise CaptureError("followup_staging_payload_invalid", "ordinary V2 staging proof rows are missing")
        tuples: list[tuple[str, str]] = []
        for row in rows:
            if not isinstance(row, dict) or set(row) != {"source_ref", "item_id", "tuple_owner", "row_digest"}:
                raise CaptureError("followup_staging_payload_invalid", "ordinary V2 staging proof row shape is invalid")
            source_ref = row.get("source_ref")
            item_id = row.get("item_id")
            owner = row.get("tuple_owner")
            digest = row.get("row_digest")
            if (
                not isinstance(source_ref, str)
                or not source_ref.strip()
                or not isinstance(item_id, str)
                or not item_id.strip()
                or not isinstance(owner, str)
                or not owner.strip()
                or not isinstance(digest, str)
                or not HEX64_RE.fullmatch(digest)
            ):
                raise CaptureError("followup_staging_payload_invalid", "ordinary V2 staging proof row values are invalid")
            tuples.append((source_ref, item_id))
        if tuples != sorted(tuples) or len(tuples) != len(set(tuples)):
            raise CaptureError("followup_staging_payload_invalid", "ordinary V2 staging proof rows are not sorted and unique")


def _validate_docs_closeout_for_stage(project_root: Path, plan_ref: str, payload: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]], dict[str, Any]]:
    if payload.get("schema") != "docs_closeout_payload.v1" or payload.get("schema_state") != "ok":
        raise CaptureError("followup_staging_payload_invalid", "staging requires schema-green docs_closeout_payload.v1")
    if payload.get("plan_ref") != plan_ref:
        raise CaptureError("followup_staging_payload_invalid", "staging payload plan_ref mismatch")
    if payload.get("final_docs_commit") != "required":
        raise CaptureError("followup_staging_payload_invalid", "terminal staging requires final_docs_commit=required")
    final_paths = payload.get("final_docs_diff_paths")
    owned = payload.get("current_plan_owned_docs_delta_paths")
    blocked = payload.get("blocked_docs_delta_paths")
    if not isinstance(final_paths, list) or not isinstance(owned, list) or not isinstance(blocked, list):
        raise CaptureError("followup_staging_payload_invalid", "staging path classifications are incomplete")
    if (
        not final_paths
        or any(not isinstance(path, str) for path in final_paths)
        or final_paths != sorted(final_paths)
        or len(final_paths) != len(set(final_paths))
        or not set(final_paths).issubset(set(owned))
        or blocked
    ):
        raise CaptureError("followup_staging_payload_invalid", "final paths are duplicate, unowned or capture-blocked")
    for path in final_paths:
        _normalize_repo_regular_relpath(path)
    handoff = payload.get("architect_final_handoff")
    expectations = handoff.get("followups_staging_expectations") if isinstance(handoff, dict) else None
    if (
        not isinstance(handoff, dict)
        or handoff.get("required") is not True
        or handoff.get("plan_ref") != plan_ref
        or handoff.get("final_docs_diff_paths") != final_paths
        or not isinstance(expectations, list)
    ):
        raise CaptureError("followup_staging_payload_invalid", "missing required exact Architect handoff")
    expectation_paths = [item.get("path") for item in expectations if isinstance(item, dict)]
    if expectation_paths != final_paths or len(expectation_paths) != len(expectations):
        raise CaptureError("followup_staging_payload_invalid", "final path set does not exact-match staging expectations")
    _validate_v2_external_staging_payload_expectations(expectations)
    cycle_id = str(payload.get("followups_capture_cycle_id") or "")
    try:
        capture = read_capture(
            project_root,
            plan_ref,
            cycle_id,
            semantic_fields=(
                str(payload.get("semantic_status") or ""),
                str(payload.get("semantic_status_norm") or ""),
                str(payload.get("semantic_closeout_kind") or ""),
            ),
        )
    except CaptureError as exc:
        if exc.reason_code in {"followup_capture_path_object_drift", "followup_capture_path_unsafe"}:
            raise CaptureError("followup_staging_object_drift", str(exc), **exc.details) from exc
        raise
    ordinary_paths = [path for path in final_paths if path.startswith("docs/followups/")]
    ordinary_expectations = capture["staging_expectations"]
    v2_payload_expectations = [
        item
        for item in expectations
        if isinstance(item, dict)
        and item.get("ownership_class") == "ordinary_followup"
        and "ownership_proof" in item
    ]
    if v2_payload_expectations:
        try:
            v2_expectations = v2_external_followup_staging_expectations(
                project_root,
                plan_ref,
                capture_binding=capture,
            )
        except CaptureError as exc:
            raise CaptureError("followup_staging_receipt_drift", str(exc), **exc.details) from exc
    else:
        v2_expectations = []
    fresh_ordinary_expectations = sorted(
        [*ordinary_expectations, *v2_expectations],
        key=lambda item: item["path"],
    )
    if [item["path"] for item in fresh_ordinary_expectations] != ordinary_paths:
        raise CaptureError("followup_staging_receipt_drift", "fresh ordinary/V2 paths differ from final docs paths")
    pi_paths = [path for path in final_paths if not path.startswith("docs/followups/")]
    pi_expectations = process_improvement_staging_expectations(
        project_root,
        plan_ref,
        pi_paths,
        capture_binding=capture,
    )
    fresh_expectations = sorted([*fresh_ordinary_expectations, *pi_expectations], key=lambda item: item["path"])
    if fresh_expectations != expectations:
        raise CaptureError("followup_staging_receipt_drift", "fresh authoritative staging proof differs from docs-closeout payload")
    return sorted(final_paths), expectations, capture


def _prepare_verified_blob(
    project_root: Path,
    expectation: dict[str, Any],
    data: bytes,
    *,
    write_object: bool,
) -> dict[str, Any]:
    path = expectation["path"]
    hash_args = ("hash-object", "-w", "--stdin") if write_object else ("hash-object", "--stdin")
    oid = _git(project_root, *hash_args, input_bytes=data).stdout.decode("ascii").strip()
    if not OID_RE.fullmatch(oid):
        raise CaptureError("followup_staging_blob_mismatch", f"git hash-object returned malformed oid for {path}")
    blob = _git(project_root, "cat-file", "blob", oid).stdout if write_object else data
    expected = expectation["expected_object"]
    if blob != data or len(blob) != expected["st_size"] or _sha256(blob) != expected["sha256"]:
        raise CaptureError("followup_staging_blob_mismatch", f"prepared blob differs from verified owned bytes: {path}")
    return {
        "schema_version": STAGING_SCHEMA_VERSION,
        "path": path,
        "ownership_class": expectation["ownership_class"],
        "ownership_proof": expectation.get("ownership_proof"),
        "capture_cycle_id": expectation["capture_cycle_id"],
        "receipt_revision": expectation["receipt_revision"],
        "receipt_content_sha256": expectation["receipt_content_sha256"],
        "receipt_object_identity": expectation["receipt_object_identity"],
        "expected_object": expected,
        "blob_mode": "100644",
        "blob_oid": oid,
        "blob_sha256": _sha256(blob),
        "blob_size": len(blob),
        "object_written": write_object,
        "state": "verified",
        "reason_code": "owned_blob_verified",
    }


def stage_docs_closeout(project_root: Path, plan_ref: str, payload: dict[str, Any], *, mutate: bool) -> dict[str, Any]:
    final_paths, expectations, capture = _validate_docs_closeout_for_stage(project_root, plan_ref, payload)
    expectation_by_path = {item["path"]: item for item in expectations}
    verifications: list[dict[str, Any]] = []
    for path in final_paths:
        expectation = expectation_by_path[path]
        if expectation.get("ownership_class") == "ordinary_followup":
            obj, data = read_followup_path(project_root, path)
        elif expectation.get("ownership_class") == "process_improvement":
            obj, data = read_repo_regular_path(project_root, path)
        else:
            raise CaptureError("followup_staging_payload_invalid", f"unsupported staging ownership class for {path}")
        if obj != expectation["expected_object"]:
            raise CaptureError("followup_staging_object_drift", f"current owned object drifted before stage: {path}")
        verification = _prepare_verified_blob(project_root, expectation, data, write_object=mutate)
        if expectation.get("ownership_class") == "ordinary_followup":
            obj_after, data_after = read_followup_path(project_root, path)
        else:
            obj_after, data_after = read_repo_regular_path(project_root, path)
        if obj_after != obj or data_after != data:
            raise CaptureError("followup_staging_object_drift", f"current owned object drifted during stage: {path}")
        verifications.append(verification)
    capture_after = read_capture(
        project_root,
        plan_ref,
        capture["capture_cycle_id"],
        semantic_fields=(
            str(payload.get("semantic_status") or ""),
            str(payload.get("semantic_status_norm") or ""),
            str(payload.get("semantic_closeout_kind") or ""),
        ),
    )
    if capture_after["receipt_revision"] != capture["receipt_revision"] or capture_after["receipt_content_sha256"] != capture["receipt_content_sha256"]:
        raise CaptureError("followup_staging_receipt_drift", "capture receipt drifted during stage verification")
    final_after, expectations_after, _capture_after = _validate_docs_closeout_for_stage(project_root, plan_ref, payload)
    if final_after != final_paths or expectations_after != expectations:
        raise CaptureError("followup_staging_receipt_drift", "authoritative staging proof drifted during stage verification")
    return {
        "schema_version": STAGING_SCHEMA_VERSION,
        "state": "prepared" if mutate else "verified",
        "reason_code": "exact_docs_blobs_prepared" if mutate else "exact_docs_blobs_verified",
        "plan_ref": plan_ref,
        "capture_cycle_id": capture["capture_cycle_id"],
        "receipt_revision": capture["receipt_revision"],
        "receipt_content_sha256": capture["receipt_content_sha256"],
        "final_docs_diff_paths": final_paths,
        "staging_verifications": verifications,
    }


def _verified_entries(stage: dict[str, Any]) -> list[dict[str, str]]:
    entries = [
        {
            "path": item["path"],
            "mode": item["blob_mode"],
            "blob_oid": item["blob_oid"],
        }
        for item in stage["staging_verifications"]
    ]
    return sorted(entries, key=lambda item: item["path"])


def _verify_tree_delta(
    project_root: Path,
    expected_parent_oid: str,
    expected_tree_oid: str,
    entries: list[dict[str, str]],
) -> None:
    raw_paths = _git(
        project_root,
        "diff-tree",
        "--no-commit-id",
        "--name-only",
        "-r",
        "-z",
        expected_parent_oid,
        expected_tree_oid,
        "--",
    ).stdout
    actual_paths = sorted(item.decode("utf-8") for item in raw_paths.split(b"\0") if item)
    expected_paths = [item["path"] for item in entries]
    if actual_paths != expected_paths:
        raise CaptureError(
            "followup_terminal_tree_drift",
            "isolated tree delta differs from exact admitted path set",
            expected_paths=expected_paths,
            actual_paths=actual_paths,
        )
    _verify_commit_paths(project_root, expected_tree_oid, entries)


def _build_isolated_tree(
    project_root: Path,
    expected_parent_oid: str,
    entries: list[dict[str, str]],
) -> str:
    with tempfile.TemporaryDirectory(prefix="planveyor-followups-index-") as tmpdir:
        index_path = Path(tmpdir) / "index"
        index_env = {"GIT_INDEX_FILE": str(index_path)}
        _git(project_root, "read-tree", expected_parent_oid, env_overrides=index_env)
        for item in entries:
            _git(
                project_root,
                "update-index",
                "--add",
                "--cacheinfo",
                item["mode"],
                item["blob_oid"],
                item["path"],
                env_overrides=index_env,
            )
        tree_oid = _git(project_root, "write-tree", env_overrides=index_env).stdout.decode("ascii").strip()
    if not OID_RE.fullmatch(tree_oid):
        raise CaptureError("followup_terminal_tree_drift", "isolated write-tree returned malformed oid")
    _verify_tree_delta(project_root, expected_parent_oid, tree_oid, entries)
    return tree_oid


def commit_preflight(project_root: Path, plan_ref: str, payload: dict[str, Any]) -> dict[str, Any]:
    stage = stage_docs_closeout(project_root, plan_ref, payload, mutate=True)
    entries = _verified_entries(stage)
    expected_ref_result = _git(project_root, "symbolic-ref", "-q", "HEAD", check=False)
    if expected_ref_result.returncode != 0:
        raise CaptureError("followup_terminal_ref_unsupported", "terminal operation requires attached HEAD")
    expected_ref = expected_ref_result.stdout.decode("utf-8").strip()
    if not expected_ref.startswith("refs/"):
        raise CaptureError("followup_terminal_ref_unsupported", "symbolic HEAD is not a full ref name")
    parent_result = _git(project_root, "rev-parse", "--verify", f"{expected_ref}^{{commit}}", check=False)
    if parent_result.returncode != 0:
        raise CaptureError("followup_terminal_ref_unsupported", "terminal operation requires an existing commit parent")
    expected_parent_oid = parent_result.stdout.decode("ascii").strip()
    head_oid = _git(project_root, "rev-parse", "--verify", "HEAD^{commit}").stdout.decode("ascii").strip()
    if head_oid != expected_parent_oid:
        raise CaptureError("followup_terminal_parent_drift", "HEAD and expected ref parent disagree")
    tree_oid = _build_isolated_tree(project_root, expected_parent_oid, entries)
    bundle_identity = _sha256(_canonical_json_bytes({"plan_ref": plan_ref, "paths": entries}))
    return {
        "schema_version": PREFLIGHT_SCHEMA_VERSION,
        "state": "ready",
        "reason_code": "followup_commit_preflight_ready",
        "plan_ref": plan_ref,
        "capture_cycle_id": stage["capture_cycle_id"],
        "receipt_revision": stage["receipt_revision"],
        "receipt_content_sha256": stage["receipt_content_sha256"],
        "bundle_identity": bundle_identity,
        "staged_paths": entries,
        "tree_construction": "isolated_index_from_expected_parent",
        "expected_tree_oid": tree_oid,
        "expected_ref": expected_ref,
        "expected_parent_oid": expected_parent_oid,
        "docs_closeout_payload": payload,
    }


def _commit_headers(project_root: Path, oid: str) -> tuple[str, list[str]]:
    raw = _git(project_root, "cat-file", "-p", oid).stdout.decode("utf-8", errors="replace")
    tree = ""
    parents: list[str] = []
    for line in raw.splitlines():
        if not line:
            break
        if line.startswith("tree "):
            tree = line.split(" ", 1)[1]
        elif line.startswith("parent "):
            parents.append(line.split(" ", 1)[1])
    return tree, parents


def _verify_commit_paths(project_root: Path, commit_oid: str, staged_paths: list[dict[str, str]]) -> None:
    for item in staged_paths:
        result = _git(project_root, "ls-tree", "-z", commit_oid, "--", item["path"]).stdout
        records = [record for record in result.split(b"\0") if record]
        if len(records) != 1:
            raise CaptureError("followup_terminal_commit_mismatch", f"candidate missing expected path {item['path']}")
        metadata, raw_path = records[0].split(b"\t", 1)
        mode, kind, oid = metadata.decode("ascii").split(" ")
        if raw_path.decode("utf-8") != item["path"] or kind != "blob" or mode != item["mode"] or oid != item["blob_oid"]:
            raise CaptureError("followup_terminal_commit_mismatch", f"candidate path/blob mismatch for {item['path']}")


def _reconcile_real_index(project_root: Path, entries: list[dict[str, str]]) -> dict[str, Any]:
    try:
        for item in entries:
            _git(
                project_root,
                "update-index",
                "--add",
                "--cacheinfo",
                item["mode"],
                item["blob_oid"],
                item["path"],
            )
        raw = _git(project_root, "diff", "--cached", "--name-only", "-z", "--").stdout
        staged_paths = sorted(item.decode("utf-8") for item in raw.split(b"\0") if item)
        owned_paths = {item["path"] for item in entries}
        owned_diverged = sorted(path for path in staged_paths if path in owned_paths)
        return {
            "state": "matches_candidate" if not owned_diverged else "diverged_preserved",
            "owned_diverged_paths": owned_diverged,
            "other_staged_paths": sorted(path for path in staged_paths if path not in owned_paths),
        }
    except CaptureError as exc:
        return {
            "state": "diverged_preserved",
            "owned_diverged_paths": [item["path"] for item in entries],
            "other_staged_paths": [],
            "reason_code": exc.reason_code,
            "message": str(exc),
        }


def _resolve_commit_message(
    plan_ref: str,
    message_file: Path | None,
    *,
    message_auto: bool,
) -> bytes:
    has_message_file = message_file is not None
    if has_message_file == message_auto:
        raise CaptureError(
            "followup_terminal_commit_mismatch",
            "commit-exact requires exactly one message source",
        )
    if message_auto:
        return (
            f"docs(closeout): finalize {plan_stem(plan_ref)}\n\n"
            f"Planveyor-Plan: {plan_ref}\n"
        ).encode("utf-8")
    assert message_file is not None
    if not message_file.is_file():
        raise CaptureError("followup_terminal_commit_mismatch", "message_file must be an existing regular file")
    return message_file.read_bytes()


def commit_exact(
    project_root: Path,
    plan_ref: str,
    preflight: dict[str, Any],
    message_file: Path | None = None,
    *,
    message_auto: bool = False,
    before_ref_cas: Any | None = None,
    after_ref_cas: Any | None = None,
) -> dict[str, Any]:
    normalized_plan_ref = normalize_plan_ref(plan_ref)
    message = _resolve_commit_message(
        normalized_plan_ref,
        message_file,
        message_auto=message_auto,
    )
    if (
        preflight.get("schema_version") != PREFLIGHT_SCHEMA_VERSION
        or preflight.get("state") != "ready"
        or preflight.get("plan_ref") != normalized_plan_ref
    ):
        raise CaptureError("followup_terminal_commit_mismatch", "invalid followups_commit_preflight.v1 input")
    payload = preflight.get("docs_closeout_payload")
    if not isinstance(payload, dict):
        raise CaptureError("followup_terminal_commit_mismatch", "preflight omitted fresh docs-closeout payload")
    try:
        fresh = commit_preflight(project_root, normalized_plan_ref, payload)
    except CaptureError as exc:
        if exc.reason_code.startswith("followup_staging_"):
            raise CaptureError("followup_terminal_tree_drift", str(exc), **exc.details) from exc
        raise
    immutable_keys = (
        "capture_cycle_id",
        "receipt_revision",
        "receipt_content_sha256",
        "bundle_identity",
        "staged_paths",
        "tree_construction",
        "expected_tree_oid",
        "expected_ref",
        "expected_parent_oid",
    )
    for key in immutable_keys:
        if fresh.get(key) != preflight.get(key):
            reason = "followup_terminal_tree_drift" if key in {"staged_paths", "expected_tree_oid", "bundle_identity"} else "followup_terminal_parent_drift"
            raise CaptureError(reason, f"terminal preflight drifted at {key}")
    expected_ref = preflight["expected_ref"]
    expected_parent = preflight["expected_parent_oid"]
    ref_now = _git(project_root, "rev-parse", "--verify", expected_ref, check=False)
    if ref_now.returncode != 0 or ref_now.stdout.decode("ascii").strip() != expected_parent:
        raise CaptureError("followup_terminal_parent_drift", "expected ref moved before commit construction")
    candidate = _git(
        project_root,
        "commit-tree",
        preflight["expected_tree_oid"],
        "-p",
        expected_parent,
        input_bytes=message,
    ).stdout.decode("ascii").strip()
    if not OID_RE.fullmatch(candidate):
        raise CaptureError("followup_terminal_commit_mismatch", "commit-tree returned malformed oid")
    tree, parents = _commit_headers(project_root, candidate)
    if tree != preflight["expected_tree_oid"] or parents != [expected_parent]:
        raise CaptureError("followup_terminal_commit_mismatch", "candidate tree/parent proof failed")
    _verify_commit_paths(project_root, candidate, preflight["staged_paths"])
    _candidate_headers, separator, candidate_body = _git(
        project_root,
        "cat-file",
        "commit",
        candidate,
    ).stdout.partition(b"\n\n")
    if not separator or candidate_body != message:
        raise CaptureError("followup_terminal_commit_mismatch", "candidate commit message proof failed")
    if before_ref_cas is not None:
        before_ref_cas(candidate)
    update = _git(
        project_root,
        "update-ref",
        expected_ref,
        candidate,
        expected_parent,
        check=False,
    )
    if update.returncode != 0:
        raise CaptureError(
            "followup_terminal_ref_cas_failed",
            update.stderr.decode("utf-8", errors="replace").strip() or "expected ref CAS failed",
            unreachable_commit_oid=candidate,
        )
    if after_ref_cas is not None:
        after_ref_cas(candidate)
    final_ref_result = _git(project_root, "rev-parse", "--verify", expected_ref, check=False)
    final_ref = final_ref_result.stdout.decode("ascii", errors="replace").strip() if final_ref_result.returncode == 0 else ""
    post_cas_ref_state = "candidate_current" if final_ref == candidate else "advanced_after_commit"
    real_index = _reconcile_real_index(project_root, preflight["staged_paths"])
    return {
        "schema_version": COMMIT_RESULT_SCHEMA_VERSION,
        "state": "committed",
        "reason_code": "followup_terminal_commit_exact",
        "plan_ref": normalized_plan_ref,
        "expected_tree_oid": preflight["expected_tree_oid"],
        "expected_ref": expected_ref,
        "expected_parent_oid": expected_parent,
        "new_commit_oid": candidate,
        "tree_construction": preflight["tree_construction"],
        "staged_paths": preflight["staged_paths"],
        "post_cas_ref_state": post_cas_ref_state,
        "observed_ref_oid": final_ref or None,
        "real_index_state": real_index["state"],
        "real_index_readback": real_index,
    }


def _read_json_input(path: str) -> dict[str, Any]:
    data = sys.stdin.buffer.read() if path == "-" else Path(path).read_bytes()
    return _load_json_bytes(data, "followup_capture_input_invalid")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture and verify one terminal docs-finalize followups cycle.")
    sub = parser.add_subparsers(dest="command", required=True)

    begin = sub.add_parser("begin")
    begin.add_argument("--project-root", default=".")
    begin.add_argument("--plan-ref", required=True)
    begin.add_argument("--docs-closeout-json", default="-")
    begin.add_argument("--retry-of-capture-cycle-id")

    checkpoint = sub.add_parser("checkpoint-general-pi")
    checkpoint.add_argument("--project-root", default=".")
    checkpoint.add_argument("--plan-ref", required=True)
    checkpoint.add_argument("--capture-cycle-id", required=True)
    checkpoint.add_argument("--docs-closeout-json", help="Retained fresh explicit-continuation docs-closeout JSON; revalidated before publication.")

    correction = sub.add_parser("reserve-general-pi-correction")
    correction.add_argument("--project-root", default=".")
    correction.add_argument("--plan-ref", required=True)
    correction.add_argument("--capture-cycle-id", required=True)
    correction.add_argument("--role", required=True, choices=REQUIRED_ROLES)
    correction.add_argument("--docs-closeout-json", default="-")

    for name in ("prepare-role", "finalize-role"):
        command = sub.add_parser(name)
        command.add_argument("--project-root", default=".")
        command.add_argument("--plan-ref", required=True)
        command.add_argument("--capture-cycle-id", required=True)
        command.add_argument("--role", required=True, choices=REQUIRED_ROLES)
        if name == "finalize-role":
            command.add_argument("--input", default="-")

    submit_ordinary = sub.add_parser("submit-ordinary-v2")
    submit_ordinary.add_argument("--project-root", default=".")
    submit_ordinary.add_argument("--plan-ref", required=True)
    submit_ordinary.add_argument("--capture-cycle-id", required=True)
    submit_ordinary.add_argument("--role", required=True, choices=REQUIRED_ROLES)
    submit_input = submit_ordinary.add_mutually_exclusive_group(required=True)
    submit_input.add_argument("--input")
    submit_input.add_argument("--input-current", action="store_true")
    submit_ordinary.add_argument("--write", action="store_true", required=True)

    bind_ordinary = sub.add_parser("bind-ordinary-v2")
    bind_ordinary.add_argument("--project-root", default=".")
    bind_ordinary.add_argument("--plan-ref", required=True)
    bind_ordinary.add_argument("--capture-cycle-id", required=True)
    bind_ordinary.add_argument("--role", required=True, choices=REQUIRED_ROLES)
    bind_ordinary.add_argument("--submission-current", action="store_true", required=True)
    bind_ordinary.add_argument("--write", action="store_true", required=True)

    freeze_ordinary = sub.add_parser("freeze-ordinary-v2")
    freeze_ordinary.add_argument("--project-root", default=".")
    freeze_ordinary.add_argument("--plan-ref", required=True)
    freeze_ordinary.add_argument("--capture-cycle-id", required=True)
    freeze_ordinary.add_argument("--write", action="store_true", required=True)

    read = sub.add_parser("read")
    read.add_argument("--project-root", default=".")
    read.add_argument("--plan-ref", required=True)
    read.add_argument("--capture-cycle-id", required=True)

    for name in ("stage", "commit-ready", "preflight"):
        command = sub.add_parser(name)
        command.add_argument("--project-root", default=".")
        command.add_argument("--plan-ref", required=True)
        command.add_argument("--docs-closeout-json", default="-")

    exact = sub.add_parser("commit-exact")
    exact.add_argument("--project-root", default=".")
    exact.add_argument("--plan-ref", required=True)
    exact.add_argument("--preflight-json", default="-")
    exact.add_argument("--message-file", action="append")
    exact.add_argument("--message-auto", action="count", default=0)

    for name in ("validate-declaration-v2", "freeze-v2", "read-v2"):
        command = sub.add_parser(name)
        command.add_argument("--project-root", default=".")
        command.add_argument("--plan-ref", required=True)
        command.add_argument("--input", default="-")
        if name == "freeze-v2":
            command.add_argument("--write", action="store_true", help="Persist the transient frozen manifest for later external readback.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == "commit-exact":
        message_files = args.message_file or []
        message_auto_count = args.message_auto or 0
        if (
            len(message_files) > 1
            or message_auto_count > 1
            or len(message_files) + message_auto_count != 1
        ):
            parser.error("commit-exact requires exactly one of --message-auto or --message-file")
        args.message_file = Path(message_files[0]) if message_files else None
        args.message_auto = message_auto_count == 1
    root = Path(args.project_root).absolute()
    try:
        if args.command == "begin":
            payload = begin_cycle(
                root,
                args.plan_ref,
                _read_json_input(args.docs_closeout_json),
                retry_of_capture_cycle_id=args.retry_of_capture_cycle_id,
            )
        elif args.command == "reserve-general-pi-correction":
            payload = reserve_general_pi_correction(root, args.plan_ref, args.capture_cycle_id,
                args.role, _read_json_input(args.docs_closeout_json))
        elif args.command == "checkpoint-general-pi":
            payload = checkpoint_general_pi(
                root, args.plan_ref, args.capture_cycle_id,
                docs_closeout_payload=(None if args.docs_closeout_json is None else _read_json_input(args.docs_closeout_json)),
            )
        elif args.command == "prepare-role":
            payload = prepare_role(root, args.plan_ref, args.capture_cycle_id, args.role)
        elif args.command == "finalize-role":
            stdout = sys.stdin.buffer.read() if args.input == "-" else Path(args.input).read_bytes()
            payload = finalize_role(root, args.plan_ref, args.capture_cycle_id, args.role, stdout)
        elif args.command == "submit-ordinary-v2":
            payload = submit_ordinary_v2(
                root,
                plan_ref=args.plan_ref,
                capture_cycle_id=args.capture_cycle_id,
                role=args.role,
                write=args.write,
                raw_input=None if args.input_current else _ordinary_v2_read_compact_input(args.input),
                input_current=args.input_current,
            )
        elif args.command == "bind-ordinary-v2":
            payload = bind_ordinary_v2(
                root,
                plan_ref=args.plan_ref,
                capture_cycle_id=args.capture_cycle_id,
                role=args.role,
                submission_current=args.submission_current,
                write=args.write,
            )
        elif args.command == "freeze-ordinary-v2":
            payload = freeze_ordinary_v2(
                root,
                plan_ref=args.plan_ref,
                capture_cycle_id=args.capture_cycle_id,
                write=args.write,
            )
        elif args.command == "read":
            payload = read_capture(root, args.plan_ref, args.capture_cycle_id)
        elif args.command in {"stage", "commit-ready"}:
            payload = stage_docs_closeout(
                root,
                normalize_plan_ref(args.plan_ref),
                _read_json_input(args.docs_closeout_json),
                mutate=args.command == "stage",
            )
        elif args.command == "preflight":
            payload = commit_preflight(root, normalize_plan_ref(args.plan_ref), _read_json_input(args.docs_closeout_json))
        elif args.command == "validate-declaration-v2":
            payload = validate_v2_declaration(root, args.plan_ref, _read_json_input(args.input))
        elif args.command == "freeze-v2":
            input_payload = _read_json_input(args.input)
            declarations = input_payload.get("declarations")
            if not isinstance(declarations, list) or any(not isinstance(item, dict) for item in declarations):
                raise CaptureError("followup_v2_declaration_input_invalid", "freeze-v2 input requires a declarations array of objects")
            payload = freeze_v2_declarations(root, args.plan_ref, declarations)
            if args.write:
                payload["frozen_manifest_path"] = persist_v2_frozen_manifest(root, args.plan_ref, payload)
        elif args.command == "read-v2":
            payload = v2_external_proof(root, _read_json_input(args.input))
        else:
            payload = commit_exact(
                root,
                args.plan_ref,
                _read_json_input(args.preflight_json),
                args.message_file,
                message_auto=args.message_auto,
            )
    except CaptureError as exc:
        sys.stdout.write(json.dumps(exc.payload(command=args.command), ensure_ascii=False, sort_keys=True) + "\n")
        return 2
    except (OSError, ValueError, KeyError, TypeError) as exc:
        payload = {
            "state": "blocked",
            "reason_code": "followup_capture_internal_error",
            "command": args.command,
            "message": str(exc),
        }
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        return 2
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

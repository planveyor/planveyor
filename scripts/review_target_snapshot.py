#!/usr/bin/env python3
"""Emit a stdout-only reviewer target snapshot for the current code-draft bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import sys
from typing import Any, Mapping, Sequence

from fs_object_identity import ObjectIdentityError, ObjectSnapshot, snapshot_regular_or_absent


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

SNAPSHOT_SCHEMA_VERSION = "review_target_snapshot.v2"
HASH_BASIS_SCHEMA_VERSION = "review_target_snapshot.hash_basis.v2"
STRICT_NA_SNAPSHOT_SCHEMA_VERSION = "review_target_snapshot.v3"
STRICT_NA_HASH_BASIS_SCHEMA_VERSION = "review_target_snapshot.hash_basis.v3"
STRICT_NA_SOURCE_KIND = "strict_na_decomposition_graph"
CURRENT_BUNDLE_TARGET = "BUNDLE=current"
HASH_BASIS_DESCRIPTION = (
    "sha256 over canonical JSON (ensure_ascii=False, sort_keys=True, separators=(',', ':')) "
    "of hash_basis_payload; targets come from the primary code_draft_meta.targets, are normalized "
    "to repo-relative POSIX paths, sorted by path, and each file authenticates its bytes plus "
    "normalized git_mode (100755 iff the owner-execute bit is set, otherwise 100644)"
)
STRICT_NA_HASH_BASIS_DESCRIPTION = (
    "sha256 over canonical JSON (ensure_ascii=False, sort_keys=True, separators=(',', ':')) "
    "of hash_basis_payload; strict N-A targets come from source.child_plans and "
    "source.child_code_drafts, are normalized to repo-relative POSIX paths, sorted by path, "
    "and each file authenticates its bytes plus normalized git_mode (100755 iff the "
    "owner-execute bit is set, otherwise 100644)"
)


class SnapshotError(RuntimeError):
    """Raised when a deterministic target snapshot cannot be produced."""


def _find_project_root(start: Path) -> Path:
    current = start.resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return Path.cwd().resolve()


def _repo_relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError as exc:
        raise SnapshotError(f"path is outside project root: {path}") from exc


def _resolve_plan_path(raw_plan_path: str | Path, root: Path) -> Path:
    plan_path = Path(raw_plan_path)
    plan_abs = plan_path.resolve() if plan_path.is_absolute() else (root / plan_path).resolve()
    _repo_relative(root, plan_abs)
    if not plan_abs.exists():
        raise SnapshotError(f"missing plan: {_repo_relative(root, plan_abs)}")
    if not plan_abs.is_file():
        raise SnapshotError(f"plan is not a file: {_repo_relative(root, plan_abs)}")
    return plan_abs


def _primary_code_draft_path(plan_abs: Path, root: Path) -> Path:
    import plan_lint

    lines = plan_abs.read_text(encoding="utf-8").splitlines()
    refs = plan_lint.extract_code_draft_refs(lines)
    code_draft_path = plan_lint.select_primary_code_draft_path(plan_abs, refs, plan_repo_root=root)
    if code_draft_path is None:
        raise SnapshotError("missing existing code draft reference in plan")
    _repo_relative(root, code_draft_path)
    return code_draft_path


def _raw_target_paths(code_draft_path: Path) -> list[str]:
    import plan_lint

    meta, error = plan_lint.extract_code_draft_meta(code_draft_path)
    if meta is None:
        raise SnapshotError(f"cannot read code_draft_meta: {error or 'unknown error'}")

    targets = meta.get("targets")
    if not isinstance(targets, list) or not targets:
        raise SnapshotError("code_draft_meta.targets must be a non-empty list")

    raw_paths: list[str] = []
    for idx, item in enumerate(targets, start=1):
        if not isinstance(item, dict):
            raise SnapshotError(f"code_draft_meta.targets[{idx}] must be an object")
        raw_path = item.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            raise SnapshotError(f"code_draft_meta.targets[{idx}].path must be a non-empty string")
        raw_paths.append(raw_path)
    return raw_paths


def _normalize_target_path(raw_path: str, root: Path) -> tuple[str, Path]:
    if "\\" in raw_path:
        raise SnapshotError(f"target path must use POSIX separators: {raw_path}")

    posix_path = PurePosixPath(raw_path)
    if posix_path.is_absolute() or any(part in {"", ".", ".."} for part in posix_path.parts):
        raise SnapshotError(f"target path must be repo-relative without traversal: {raw_path}")

    abs_path = (root / Path(*posix_path.parts)).resolve()
    rel_path = _repo_relative(root, abs_path)
    if not abs_path.exists():
        raise SnapshotError(f"missing current target: {rel_path}")
    if not abs_path.is_file():
        raise SnapshotError(f"current target is not a file: {rel_path}")
    return rel_path, abs_path


def _resolve_current_targets(raw_paths: Sequence[str], root: Path) -> list[tuple[str, Path]]:
    resolved_by_path: dict[str, Path] = {}
    for raw_path in raw_paths:
        rel_path, abs_path = _normalize_target_path(raw_path, root)
        if rel_path in resolved_by_path:
            raise SnapshotError(f"duplicate target path: {rel_path}")
        resolved_by_path[rel_path] = abs_path
    return sorted(resolved_by_path.items(), key=lambda item: item[0])


def _reject_origin_plan_target(plan_abs: Path, targets: Sequence[tuple[str, Path]]) -> None:
    import plan_lint

    for rel_path, target_abs in targets:
        if plan_lint.same_file_object(plan_abs, target_abs):
            raise SnapshotError(
                f"{plan_lint.ORIGIN_PLAN_IN_REVIEW_TARGETS_REASON}: "
                f"current-bundle target `{rel_path}` is the origin plan file object"
            )


def _normalized_git_mode(stat_result: Any) -> str:
    return "100755" if stat_result.st_mode & stat.S_IXUSR else "100644"


def _stat_identity(stat_result: Any) -> tuple[int, int, int, int, int, str]:
    return (
        stat_result.st_dev,
        stat_result.st_ino,
        stat_result.st_size,
        stat_result.st_mtime_ns,
        stat_result.st_ctime_ns,
        _normalized_git_mode(stat_result),
    )


def _file_digest_and_size(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size_bytes = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size_bytes += len(chunk)
    return digest.hexdigest(), size_bytes


def _file_record(rel_path: str, abs_path: Path) -> dict[str, Any]:
    try:
        before = abs_path.stat()
        digest, size_bytes = _file_digest_and_size(abs_path)
        after = abs_path.stat()
    except OSError as exc:
        raise SnapshotError(f"cannot read current target: {rel_path}: {exc}") from exc
    if _stat_identity(before) != _stat_identity(after) or size_bytes != after.st_size:
        raise SnapshotError(f"current target changed while reading: {rel_path}")
    return {
        "git_mode": _normalized_git_mode(after),
        "path": rel_path,
        "sha256": digest,
        "size_bytes": size_bytes,
    }


def _capture_identity(path: Path, *, label: str) -> tuple[int, int, int, int, int, str]:
    try:
        return _stat_identity(path.stat())
    except OSError as exc:
        raise SnapshotError(f"cannot stat {label}: {exc}") from exc


def _require_identity(
    path: Path,
    expected: tuple[int, int, int, int, int, str],
    *,
    label: str,
) -> None:
    if _capture_identity(path, label=label) != expected:
        raise SnapshotError(f"{label} changed during snapshot")


def _bundle_sha256(hash_basis_payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        hash_basis_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _strict_normalize_repo_path(raw_path: object, *, label: str) -> str:
    """Return one already-normalized repo-relative POSIX path for the v3 graph."""

    if not isinstance(raw_path, str) or not raw_path:
        raise SnapshotError(f"{label} must be a non-empty string")
    if "\\" in raw_path:
        raise SnapshotError(f"{label} must use POSIX separators: {raw_path}")
    posix_path = PurePosixPath(raw_path)
    if posix_path.is_absolute() or any(part in {"", ".", ".."} for part in posix_path.parts):
        raise SnapshotError(f"{label} must be repo-relative without traversal: {raw_path}")
    normalized = "/".join(posix_path.parts)
    if raw_path != normalized:
        raise SnapshotError(f"{label} must be normalized repo-relative POSIX text: {raw_path}")
    return normalized


def _strict_same_stem_draft_path(child_plan_path: str) -> str:
    """Derive the one allowed seed-draft path for a strict-N-A child plan."""

    child_plan_path = _strict_normalize_repo_path(child_plan_path, label="strict N-A child plan path")
    child = PurePosixPath(child_plan_path)
    if child.parts[:2] != ("docs", "plans") or child.suffix != ".md" or not child.stem:
        raise SnapshotError(f"strict N-A child plan path is not a plan Markdown path: {child_plan_path}")
    return f"docs/code_drafts/{child.stem}__code_draft.md"


def _strict_snapshot(
    root: Path,
    relative_path: str,
    *,
    label: str,
    expected_state: str,
) -> ObjectSnapshot:
    """Read one trusted-root object through the existing no-follow primitive."""

    try:
        snapshot = snapshot_regular_or_absent(root, relative_path)
    except ObjectIdentityError as exc:
        raise SnapshotError(f"{label} cannot be captured safely ({exc.reason_code}): {exc}") from exc
    if snapshot.state != expected_state:
        if expected_state == "regular":
            raise SnapshotError(f"{label} must be a regular file: {relative_path}")
        raise SnapshotError(f"{label} must be absent: {relative_path}")
    if expected_state == "regular" and (
        snapshot.data is None
        or snapshot.git_mode not in {"100644", "100755"}
        or snapshot.st_dev is None
        or snapshot.st_ino is None
        or snapshot.st_size is None
        or snapshot.st_mtime_ns is None
    ):
        raise SnapshotError(f"{label} regular-file capture is incomplete: {relative_path}")
    return snapshot


def _strict_snapshot_signature(snapshot: ObjectSnapshot) -> tuple[object, ...]:
    """Compare bytes plus descriptor identity and normalized Git mode on re-read."""

    return (
        snapshot.state,
        snapshot.data,
        snapshot.git_mode,
        snapshot.st_dev,
        snapshot.st_ino,
        snapshot.st_size,
        snapshot.st_mtime_ns,
    )


def _require_strict_snapshot_unchanged(
    root: Path,
    relative_path: str,
    expected: ObjectSnapshot,
    *,
    label: str,
) -> ObjectSnapshot:
    current = _strict_snapshot(
        root,
        relative_path,
        label=label,
        expected_state=expected.state,
    )
    if _strict_snapshot_signature(current) != _strict_snapshot_signature(expected):
        raise SnapshotError(f"{label} changed during strict N-A snapshot: {relative_path}")
    return current


def _strict_snapshot_text(snapshot: ObjectSnapshot, *, label: str) -> str:
    if snapshot.data is None:
        raise SnapshotError(f"{label} capture has no bytes")
    try:
        return snapshot.data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SnapshotError(f"{label} is not UTF-8 text") from exc


def _strict_file_record(relative_path: str, snapshot: ObjectSnapshot) -> dict[str, Any]:
    if snapshot.data is None or snapshot.git_mode is None or snapshot.st_size is None:
        raise SnapshotError(f"strict N-A member capture is incomplete: {relative_path}")
    return {
        "git_mode": snapshot.git_mode,
        "path": relative_path,
        "sha256": hashlib.sha256(snapshot.data).hexdigest(),
        "size_bytes": snapshot.st_size,
    }


def _strict_object_identity(snapshot: ObjectSnapshot, *, label: str) -> tuple[int, int]:
    if snapshot.st_dev is None or snapshot.st_ino is None:
        raise SnapshotError(f"{label} capture has no file-object identity")
    return snapshot.st_dev, snapshot.st_ino


def _strict_validate_child_draft_meta(
    draft_snapshot: ObjectSnapshot,
    *,
    child_plan_path: str,
    child_draft_path: str,
) -> None:
    """Apply the existing strict child planning-carrier gates without a second parser."""

    import plan_status_oracle

    try:
        meta = plan_status_oracle._machine_authority_strict_code_draft_meta(
            _strict_snapshot_text(draft_snapshot, label=f"strict N-A child draft: {child_draft_path}")
        )
    except plan_status_oracle.MachineAuthorityDecisionError as exc:
        raise SnapshotError(f"invalid strict N-A child code draft `{child_draft_path}`: {exc}") from exc
    if meta.get("plan") != child_plan_path:
        raise SnapshotError(
            "strict N-A child code_draft_meta.plan mismatch: "
            f"expected {child_plan_path!r}, got {meta.get('plan')!r}"
        )

    # Match the existing strict-N-A bundle planning-carrier gate in planveyor.zsh:
    # metadata makes the child a real lintable draft, but its implementation
    # target/deletion inventory never becomes a parent v3 hash-basis member.
    targets = meta.get("targets") or []
    if not isinstance(targets, list) or not targets:
        raise SnapshotError(f"empty strict N-A child code_draft_meta.targets: {child_draft_path}")
    for target in targets:
        if not isinstance(target, Mapping) or not isinstance(target.get("path"), str) or not target["path"].strip():
            raise SnapshotError(
                f"invalid strict N-A child code_draft_meta.target entry: {child_draft_path}: {target!r}"
            )

    deleted_paths = meta.get("deleted_paths") or []
    if not isinstance(deleted_paths, list):
        raise SnapshotError(f"invalid strict N-A child code_draft_meta.deleted_paths: {child_draft_path}")
    for deleted_path in deleted_paths:
        if (
            not isinstance(deleted_path, Mapping)
            or not isinstance(deleted_path.get("path"), str)
            or not deleted_path["path"].strip()
        ):
            raise SnapshotError(
                "invalid strict N-A child code_draft_meta.deleted_path entry: "
                f"{child_draft_path}: {deleted_path!r}"
            )


def _strict_na_source_from_captured_parent(
    plan_abs: Path,
    plan_rel: str,
    root: Path,
) -> tuple[ObjectSnapshot, str, ObjectSnapshot, str, tuple[str, ...], tuple[str, ...]] | None:
    """Select the explicit strict-N-A source before ordinary draft resolution.

    The descriptor-captured parent bytes are the only input to strict shape
    classification.  A non-shaped plan returns ``None`` and takes the literal
    legacy v2 path below; a shaped plan either admits v3 completely or raises.
    """

    import plan_status_oracle

    parent_snapshot = _strict_snapshot(root, plan_rel, label="plan", expected_state="regular")
    plan_text = _strict_snapshot_text(parent_snapshot, label=f"plan: {plan_rel}")
    strict_meta = plan_status_oracle.strict_plan_meta_json(plan_text)
    if strict_meta.state != "valid" or strict_meta.plan_meta is None:
        if strict_meta.has_machine_authority_marker:
            raise SnapshotError(
                "strict N-A Meta carrier is malformed and cannot fall back to v2: "
                f"{strict_meta.reason_code}: {strict_meta.reason}"
            )
        return None
    plan_meta = strict_meta.plan_meta
    decision = plan_meta.get("machine_authority_decision")
    phase_overlay = str(plan_meta.get("phase_overlay") or "").strip().lower()
    phase_state = str(plan_meta.get("phase_state") or "").strip().lower()
    if (
        phase_overlay != "decomposition_wave"
        or phase_state not in {"active", "parked"}
        or not isinstance(decision, Mapping)
        or decision.get("applicability") != "not_applicable"
    ):
        return None

    parent_draft_rel = f"docs/code_drafts/{plan_abs.stem}__code_draft.md"
    parent_draft_snapshot = _strict_snapshot(
        root,
        parent_draft_rel,
        label="strict N-A parent code draft",
        expected_state="absent",
    )

    try:
        readback = plan_status_oracle.machine_authority_decision_readback(plan_abs, plan_text=plan_text)
    except (OSError, UnicodeDecodeError, plan_status_oracle.MachineAuthorityDecisionError) as exc:
        raise SnapshotError(f"strict N-A machine-authority readback is unavailable: {exc}") from exc
    if (
        readback.state != "not_applicable"
        or readback.reason_code != "ok"
        or readback.applicability != "not_applicable"
        or readback.ref_state != "not_required"
    ):
        raise SnapshotError(
            "strict N-A machine-authority admission failed: "
            f"state={readback.state!r}; applicability={readback.applicability!r}; "
            f"ref_state={readback.ref_state!r}; reason={readback.reason_code!r}"
        )

    child_state = plan_status_oracle.decomposition_child_state(plan_text, root=root)
    if child_state.state != "queue_ready" or not child_state.canonical_planning_child_paths:
        raise SnapshotError(f"strict N-A canonical child graph is not queue-ready: {child_state.reason}")
    child_plans = tuple(
        _strict_normalize_repo_path(path, label="strict N-A canonical child plan")
        for path in child_state.canonical_planning_child_paths
    )
    if len(set(child_plans)) != len(child_plans):
        raise SnapshotError("strict N-A canonical child graph contains duplicate paths")
    child_drafts = tuple(_strict_same_stem_draft_path(path) for path in child_plans)
    if len(set(child_drafts)) != len(child_drafts):
        raise SnapshotError("strict N-A canonical child graph has duplicate same-stem drafts")
    return parent_snapshot, plan_text, parent_draft_snapshot, parent_draft_rel, child_plans, child_drafts


def _require_exact_keys(value: dict[str, Any], expected: set[str], *, label: str) -> None:
    if set(value) != expected:
        raise SnapshotError(f"{label} must contain exactly: {', '.join(sorted(expected))}")


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _validate_v2_snapshot_payload(payload: object) -> dict[str, Any]:
    """Validate and return an exact finalized v2 current-bundle payload."""

    if not isinstance(payload, dict):
        raise SnapshotError("snapshot payload must be an object")
    _require_exact_keys(
        payload,
        {
            "bundle_sha256",
            "code_draft",
            "files",
            "hash_basis",
            "hash_basis_payload",
            "plan",
            "schema_version",
            "target",
            "target_paths",
            "target_snapshot",
        },
        label="snapshot payload",
    )
    if payload.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise SnapshotError(f"unsupported snapshot schema_version: {payload.get('schema_version')!r}")
    for key in ("plan", "code_draft", "hash_basis"):
        if not isinstance(payload.get(key), str) or not payload[key]:
            raise SnapshotError(f"snapshot payload {key} must be a non-empty string")

    files = payload.get("files")
    if not isinstance(files, list) or not files:
        raise SnapshotError("snapshot payload files must be a non-empty list")
    validated_files: list[dict[str, Any]] = []
    prior_path: str | None = None
    for index, raw_record in enumerate(files, start=1):
        if not isinstance(raw_record, dict):
            raise SnapshotError(f"snapshot payload files[{index}] must be an object")
        _require_exact_keys(
            raw_record,
            {"git_mode", "path", "sha256", "size_bytes"},
            label=f"snapshot payload files[{index}]",
        )
        path = raw_record.get("path")
        if not isinstance(path, str) or not path:
            raise SnapshotError(f"snapshot payload files[{index}].path must be a non-empty string")
        if "\\" in path:
            raise SnapshotError(f"snapshot payload files[{index}].path must use POSIX separators")
        posix_path = PurePosixPath(path)
        if posix_path.is_absolute() or any(part in {"", ".", ".."} for part in posix_path.parts):
            raise SnapshotError(f"snapshot payload files[{index}].path must be repo-relative without traversal")
        if prior_path is not None and path <= prior_path:
            raise SnapshotError("snapshot payload files must be sorted by unique path")
        prior_path = path
        if not _is_sha256(raw_record.get("sha256")):
            raise SnapshotError(f"snapshot payload files[{index}].sha256 must be lowercase sha256")
        size_bytes = raw_record.get("size_bytes")
        if isinstance(size_bytes, bool) or not isinstance(size_bytes, int) or size_bytes < 0:
            raise SnapshotError(f"snapshot payload files[{index}].size_bytes must be a non-negative integer")
        if raw_record.get("git_mode") not in {"100644", "100755"}:
            raise SnapshotError(f"snapshot payload files[{index}].git_mode must be 100644 or 100755")
        validated_files.append(raw_record)

    target_paths = payload.get("target_paths")
    if target_paths != [record["path"] for record in validated_files]:
        raise SnapshotError("snapshot payload target_paths must exactly match files inventory")

    hash_basis_payload = payload.get("hash_basis_payload")
    if not isinstance(hash_basis_payload, dict):
        raise SnapshotError("snapshot payload hash_basis_payload must be an object")
    _require_exact_keys(
        hash_basis_payload,
        {"algorithm", "files", "schema_version"},
        label="snapshot payload hash_basis_payload",
    )
    if hash_basis_payload.get("schema_version") != HASH_BASIS_SCHEMA_VERSION:
        raise SnapshotError(
            f"unsupported hash_basis_payload schema_version: {hash_basis_payload.get('schema_version')!r}"
        )
    if hash_basis_payload.get("algorithm") != "sha256":
        raise SnapshotError("snapshot payload hash_basis_payload.algorithm must be sha256")
    if hash_basis_payload.get("files") != validated_files:
        raise SnapshotError("snapshot payload hash_basis_payload.files must exactly match files")

    bundle_sha256 = payload.get("bundle_sha256")
    if not _is_sha256(bundle_sha256):
        raise SnapshotError("snapshot payload bundle_sha256 must be lowercase sha256")
    if _bundle_sha256(hash_basis_payload) != bundle_sha256:
        raise SnapshotError("snapshot payload bundle_sha256 does not match hash_basis_payload")

    target_snapshot = payload.get("target_snapshot")
    if not isinstance(target_snapshot, dict):
        raise SnapshotError("snapshot payload target_snapshot must be an object")
    _require_exact_keys(
        target_snapshot,
        {"bundle_sha256", "target"},
        label="snapshot payload target_snapshot",
    )
    expected_target = f"{CURRENT_BUNDLE_TARGET} bundle_sha256={bundle_sha256}"
    if target_snapshot != {"bundle_sha256": bundle_sha256, "target": CURRENT_BUNDLE_TARGET}:
        raise SnapshotError("snapshot payload target_snapshot does not match bundle_sha256")
    if payload.get("target") != expected_target:
        raise SnapshotError("snapshot payload target does not match bundle_sha256")
    return payload


def _validate_v3_snapshot_payload(payload: object) -> dict[str, Any]:
    """Validate the discriminated strict-N-A current-bundle payload."""

    if not isinstance(payload, dict):
        raise SnapshotError("snapshot payload must be an object")
    _require_exact_keys(
        payload,
        {
            "bundle_sha256",
            "files",
            "hash_basis",
            "hash_basis_payload",
            "plan",
            "schema_version",
            "source",
            "target",
            "target_paths",
            "target_snapshot",
        },
        label="strict N-A snapshot payload",
    )
    if payload.get("schema_version") != STRICT_NA_SNAPSHOT_SCHEMA_VERSION:
        raise SnapshotError(f"unsupported strict N-A snapshot schema_version: {payload.get('schema_version')!r}")
    for key in ("plan", "hash_basis"):
        if not isinstance(payload.get(key), str) or not payload[key]:
            raise SnapshotError(f"strict N-A snapshot payload {key} must be a non-empty string")
    if payload.get("hash_basis") != STRICT_NA_HASH_BASIS_DESCRIPTION:
        raise SnapshotError("strict N-A snapshot payload hash_basis must equal the canonical v3 description")
    normalized_plan = _strict_normalize_repo_path(payload["plan"], label="strict N-A snapshot payload plan")
    if payload["plan"] != normalized_plan:
        raise SnapshotError("strict N-A snapshot payload plan must be normalized")
    _strict_same_stem_draft_path(normalized_plan)

    source = payload.get("source")
    if not isinstance(source, dict):
        raise SnapshotError("strict N-A snapshot payload source must be an object")
    _require_exact_keys(
        source,
        {"child_code_drafts", "child_plans", "kind"},
        label="strict N-A snapshot payload source",
    )
    if source.get("kind") != STRICT_NA_SOURCE_KIND:
        raise SnapshotError("strict N-A snapshot payload source.kind is invalid")
    child_plans = source.get("child_plans")
    child_drafts = source.get("child_code_drafts")
    if not isinstance(child_plans, list) or not child_plans:
        raise SnapshotError("strict N-A snapshot payload source.child_plans must be a non-empty list")
    if not isinstance(child_drafts, list) or len(child_drafts) != len(child_plans):
        raise SnapshotError(
            "strict N-A snapshot payload source.child_code_drafts must have exactly one entry per child plan"
        )
    normalized_plans = [
        _strict_normalize_repo_path(path, label=f"strict N-A snapshot payload source.child_plans[{index}]")
        for index, path in enumerate(child_plans, start=1)
    ]
    normalized_drafts = [
        _strict_normalize_repo_path(path, label=f"strict N-A snapshot payload source.child_code_drafts[{index}]")
        for index, path in enumerate(child_drafts, start=1)
    ]
    if normalized_plans != child_plans or normalized_drafts != child_drafts:
        raise SnapshotError("strict N-A snapshot payload source paths must be normalized")
    if len(set(normalized_plans)) != len(normalized_plans) or len(set(normalized_drafts)) != len(normalized_drafts):
        raise SnapshotError("strict N-A snapshot payload source paths must be unique")
    if normalized_plan in normalized_plans:
        raise SnapshotError("strict N-A snapshot payload source must exclude the parent plan")
    for child_plan, child_draft in zip(normalized_plans, normalized_drafts, strict=True):
        if _strict_same_stem_draft_path(child_plan) != child_draft:
            raise SnapshotError("strict N-A snapshot payload source child plan/draft pairing is invalid")

    files = payload.get("files")
    if not isinstance(files, list) or len(files) != 2 * len(normalized_plans):
        raise SnapshotError("strict N-A snapshot payload files must contain exactly N+N records")
    validated_files: list[dict[str, Any]] = []
    prior_path: str | None = None
    for index, raw_record in enumerate(files, start=1):
        if not isinstance(raw_record, dict):
            raise SnapshotError(f"strict N-A snapshot payload files[{index}] must be an object")
        _require_exact_keys(
            raw_record,
            {"git_mode", "path", "sha256", "size_bytes"},
            label=f"strict N-A snapshot payload files[{index}]",
        )
        path = raw_record.get("path")
        normalized_path = _strict_normalize_repo_path(
            path,
            label=f"strict N-A snapshot payload files[{index}].path",
        )
        if path != normalized_path:
            raise SnapshotError(f"strict N-A snapshot payload files[{index}].path must be normalized")
        if prior_path is not None and normalized_path <= prior_path:
            raise SnapshotError("strict N-A snapshot payload files must be sorted by unique path")
        prior_path = normalized_path
        if not _is_sha256(raw_record.get("sha256")):
            raise SnapshotError(f"strict N-A snapshot payload files[{index}].sha256 must be lowercase sha256")
        size_bytes = raw_record.get("size_bytes")
        if isinstance(size_bytes, bool) or not isinstance(size_bytes, int) or size_bytes < 0:
            raise SnapshotError(
                f"strict N-A snapshot payload files[{index}].size_bytes must be a non-negative integer"
            )
        if raw_record.get("git_mode") not in {"100644", "100755"}:
            raise SnapshotError(f"strict N-A snapshot payload files[{index}].git_mode must be 100644 or 100755")
        validated_files.append(raw_record)

    expected_paths = sorted((*normalized_plans, *normalized_drafts))
    if [record["path"] for record in validated_files] != expected_paths:
        raise SnapshotError("strict N-A snapshot payload files must exactly match the N+N source inventory")
    if payload.get("target_paths") != expected_paths:
        raise SnapshotError("strict N-A snapshot payload target_paths must exactly match files inventory")

    hash_basis_payload = payload.get("hash_basis_payload")
    if not isinstance(hash_basis_payload, dict):
        raise SnapshotError("strict N-A snapshot payload hash_basis_payload must be an object")
    _require_exact_keys(
        hash_basis_payload,
        {"algorithm", "files", "schema_version", "source"},
        label="strict N-A snapshot payload hash_basis_payload",
    )
    if hash_basis_payload.get("schema_version") != STRICT_NA_HASH_BASIS_SCHEMA_VERSION:
        raise SnapshotError(
            "unsupported strict N-A hash_basis_payload schema_version: "
            f"{hash_basis_payload.get('schema_version')!r}"
        )
    if hash_basis_payload.get("algorithm") != "sha256":
        raise SnapshotError("strict N-A snapshot payload hash_basis_payload.algorithm must be sha256")
    if hash_basis_payload.get("files") != validated_files:
        raise SnapshotError("strict N-A snapshot payload hash_basis_payload.files must exactly match files")
    if hash_basis_payload.get("source") != source:
        raise SnapshotError("strict N-A snapshot payload hash_basis_payload.source must exactly match source")

    bundle_sha256 = payload.get("bundle_sha256")
    if not _is_sha256(bundle_sha256):
        raise SnapshotError("strict N-A snapshot payload bundle_sha256 must be lowercase sha256")
    if _bundle_sha256(hash_basis_payload) != bundle_sha256:
        raise SnapshotError("strict N-A snapshot payload bundle_sha256 does not match hash_basis_payload")

    target_snapshot = payload.get("target_snapshot")
    if not isinstance(target_snapshot, dict):
        raise SnapshotError("strict N-A snapshot payload target_snapshot must be an object")
    _require_exact_keys(
        target_snapshot,
        {"bundle_sha256", "target"},
        label="strict N-A snapshot payload target_snapshot",
    )
    expected_target = f"{CURRENT_BUNDLE_TARGET} bundle_sha256={bundle_sha256}"
    if target_snapshot != {"bundle_sha256": bundle_sha256, "target": CURRENT_BUNDLE_TARGET}:
        raise SnapshotError("strict N-A snapshot payload target_snapshot does not match bundle_sha256")
    if payload.get("target") != expected_target:
        raise SnapshotError("strict N-A snapshot payload target does not match bundle_sha256")
    return payload


def validate_snapshot_payload(payload: object) -> dict[str, Any]:
    """Validate a finalized current-bundle payload without cross-version coercion."""

    if isinstance(payload, dict) and payload.get("schema_version") == STRICT_NA_SNAPSHOT_SCHEMA_VERSION:
        return _validate_v3_snapshot_payload(payload)
    return _validate_v2_snapshot_payload(payload)


def _build_v2_current_bundle_snapshot(plan_abs: Path, root: Path) -> dict[str, Any]:
    """Preserve the ordinary code-draft source branch byte-for-byte."""

    plan_rel = _repo_relative(root, plan_abs)
    plan_identity = _capture_identity(plan_abs, label=f"plan: {plan_rel}")
    code_draft_abs = _primary_code_draft_path(plan_abs, root)
    _require_identity(plan_abs, plan_identity, label=f"plan: {plan_rel}")
    code_draft_rel = _repo_relative(root, code_draft_abs)
    code_draft_identity = _capture_identity(code_draft_abs, label=f"code draft: {code_draft_rel}")
    raw_target_paths = _raw_target_paths(code_draft_abs)
    _require_identity(code_draft_abs, code_draft_identity, label=f"code draft: {code_draft_rel}")
    targets = _resolve_current_targets(raw_target_paths, root)
    target_identities = {
        rel_path: _capture_identity(abs_path, label=f"current target: {rel_path}")
        for rel_path, abs_path in targets
    }
    _reject_origin_plan_target(plan_abs, targets)
    files = [_file_record(rel_path, abs_path) for rel_path, abs_path in targets]
    _require_identity(plan_abs, plan_identity, label=f"plan: {plan_rel}")
    _require_identity(code_draft_abs, code_draft_identity, label=f"code draft: {code_draft_rel}")
    for rel_path, abs_path in targets:
        _require_identity(
            abs_path,
            target_identities[rel_path],
            label=f"current target: {rel_path}",
        )
    hash_basis_payload = {
        "algorithm": "sha256",
        "files": files,
        "schema_version": HASH_BASIS_SCHEMA_VERSION,
    }
    bundle_sha256 = _bundle_sha256(hash_basis_payload)
    target = f"{CURRENT_BUNDLE_TARGET} bundle_sha256={bundle_sha256}"

    snapshot = {
        "bundle_sha256": bundle_sha256,
        "code_draft": code_draft_rel,
        "files": files,
        "hash_basis": HASH_BASIS_DESCRIPTION,
        "hash_basis_payload": hash_basis_payload,
        "plan": plan_rel,
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "target": target,
        "target_paths": [rel_path for rel_path, _ in targets],
        "target_snapshot": {
            "bundle_sha256": bundle_sha256,
            "target": CURRENT_BUNDLE_TARGET,
        },
    }
    return validate_snapshot_payload(snapshot)


def _build_strict_na_current_bundle_snapshot(
    plan_abs: Path,
    root: Path,
    context: tuple[ObjectSnapshot, str, ObjectSnapshot, str, tuple[str, ...], tuple[str, ...]],
) -> dict[str, Any]:
    """Build one v3 graph proof from a complete strict-N-A topology snapshot."""

    plan_rel = _repo_relative(root, plan_abs)
    (
        parent_snapshot,
        _plan_text,
        parent_draft_snapshot,
        parent_draft_rel,
        child_plans,
        child_drafts,
    ) = context
    source = {
        "kind": STRICT_NA_SOURCE_KIND,
        "child_plans": list(child_plans),
        "child_code_drafts": list(child_drafts),
    }
    member_paths = (*child_plans, *child_drafts)
    if len(member_paths) != 2 * len(child_plans) or len(set(member_paths)) != len(member_paths):
        raise SnapshotError("strict N-A source must resolve to exactly 2N unique graph members")

    member_snapshots: dict[str, ObjectSnapshot] = {}
    for member_path in member_paths:
        member_snapshots[member_path] = _strict_snapshot(
            root,
            member_path,
            label="strict N-A graph member",
            expected_state="regular",
        )

    seen_identities: dict[tuple[int, int], str] = {
        _strict_object_identity(parent_snapshot, label=f"plan: {plan_rel}"): plan_rel,
    }
    for member_path in member_paths:
        identity = _strict_object_identity(member_snapshots[member_path], label=f"strict N-A graph member: {member_path}")
        prior_path = seen_identities.get(identity)
        if prior_path is not None:
            raise SnapshotError(
                "strict N-A graph contains aliased file objects: "
                f"{prior_path} and {member_path}"
            )
        seen_identities[identity] = member_path

    for child_plan, child_draft in zip(child_plans, child_drafts, strict=True):
        _strict_validate_child_draft_meta(
            member_snapshots[child_draft],
            child_plan_path=child_plan,
            child_draft_path=child_draft,
        )

    files = [
        _strict_file_record(member_path, member_snapshots[member_path])
        for member_path in sorted(member_paths)
    ]

    # Every read-only dependent input must still denote the same bytes and
    # topology after all membership/metadata work.  A later rescan proves that
    # a bounded ``next_plans`` projection could not replace the canonical map.
    after_context = _strict_na_source_from_captured_parent(plan_abs, plan_rel, root)
    if after_context is None:
        raise SnapshotError("strict N-A source classification changed during snapshot")
    (
        after_parent_snapshot,
        _after_plan_text,
        after_parent_draft_snapshot,
        after_parent_draft_rel,
        after_child_plans,
        after_child_drafts,
    ) = after_context
    if _strict_snapshot_signature(after_parent_snapshot) != _strict_snapshot_signature(parent_snapshot):
        raise SnapshotError(f"plan changed during strict N-A snapshot: {plan_rel}")
    if after_parent_draft_rel != parent_draft_rel or _strict_snapshot_signature(after_parent_draft_snapshot) != _strict_snapshot_signature(parent_draft_snapshot):
        raise SnapshotError(f"strict N-A parent code-draft absence changed during snapshot: {parent_draft_rel}")
    if after_child_plans != child_plans or after_child_drafts != child_drafts:
        raise SnapshotError("strict N-A canonical child graph changed during snapshot")
    for member_path, member_snapshot in member_snapshots.items():
        _require_strict_snapshot_unchanged(
            root,
            member_path,
            member_snapshot,
            label="strict N-A graph member",
        )

    hash_basis_payload = {
        "algorithm": "sha256",
        "files": files,
        "schema_version": STRICT_NA_HASH_BASIS_SCHEMA_VERSION,
        "source": source,
    }
    bundle_sha256 = _bundle_sha256(hash_basis_payload)
    target = f"{CURRENT_BUNDLE_TARGET} bundle_sha256={bundle_sha256}"
    snapshot = {
        "bundle_sha256": bundle_sha256,
        "files": files,
        "hash_basis": STRICT_NA_HASH_BASIS_DESCRIPTION,
        "hash_basis_payload": hash_basis_payload,
        "plan": plan_rel,
        "schema_version": STRICT_NA_SNAPSHOT_SCHEMA_VERSION,
        "source": source,
        "target": target,
        "target_paths": [record["path"] for record in files],
        "target_snapshot": {
            "bundle_sha256": bundle_sha256,
            "target": CURRENT_BUNDLE_TARGET,
        },
    }
    return validate_snapshot_payload(snapshot)


def build_current_bundle_snapshot(raw_plan_path: str | Path, *, project_root: str | Path | None = None) -> dict[str, Any]:
    root = Path(project_root).resolve() if project_root is not None else _find_project_root(Path(raw_plan_path))
    plan_abs = _resolve_plan_path(raw_plan_path, root)
    plan_rel = _repo_relative(root, plan_abs)
    strict_context = _strict_na_source_from_captured_parent(plan_abs, plan_rel, root)
    if strict_context is not None:
        return _build_strict_na_current_bundle_snapshot(plan_abs, root, strict_context)
    return _build_v2_current_bundle_snapshot(plan_abs, root)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Emit deterministic target_snapshot JSON for the current code-draft target bundle.",
    )
    parser.add_argument("plan_path", help="Plan path that references the code draft.")
    parser.add_argument(
        "--current-bundle",
        action="store_true",
        help="Required mode: hash current filesystem bytes for code_draft_meta.targets.",
    )
    parser.add_argument(
        "--project-root",
        help="Project root for resolving repo-relative plan/code-draft/target paths; defaults to git root/cwd.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if not args.current_bundle:
        parser.error("--current-bundle is required")

    try:
        snapshot = build_current_bundle_snapshot(args.plan_path, project_root=args.project_root)
    except (OSError, SnapshotError) as exc:
        print(f"review_target_snapshot: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

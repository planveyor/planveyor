#!/usr/bin/env python3
"""Read-only guard for shared docs mirror drift.

The source of truth lives in planveyor. Sibling repos may keep runtime
mirror copies, but this helper only reports drift and never writes target files.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from fnmatch import fnmatchcase
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Iterable, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
DRIFT_STATUSES = {"drift", "missing_target"}
_KNOWN_CONTENT_PROFILES = frozenset({"default", "planveyor", "target-local"})


class MirrorPolicyError(ValueError):
    """The selected fixed shared-docs mirror policy is absent or malformed."""


@dataclass(frozen=True)
class MirrorPolicy:
    set_id: str
    static_paths: tuple[str, ...]
    glob_patterns: tuple[str, ...]
    target_repo: str | None
    target_kind: str | None


# Raw generic operations have no concealed target or mirror set. The caller
# may still supply --target-root, but it does not imply a target obligation.
GENERIC_MIRROR_POLICY = MirrorPolicy("generic", (), (), None, None)


def _strict_policy_object(data: bytes) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise MirrorPolicyError(f"shared-docs mirror policy: duplicate key {key!r}")
            result[key] = value
        return result

    try:
        raw = json.loads(data.decode("utf-8"), object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError, MirrorPolicyError) as exc:
        raise MirrorPolicyError("shared-docs mirror policy: invalid JSON") from exc
    if not isinstance(raw, dict):
        raise MirrorPolicyError("shared-docs mirror policy: expected object")
    return raw


def _safe_mirror_path(value: object, *, label: str, glob: bool = False) -> str:
    if not isinstance(value, str) or not value or value.startswith("/") or "\\" in value:
        raise MirrorPolicyError(f"shared-docs mirror policy: invalid {label}")
    parts = value.split("/")
    if any(not part or part in {".", ".."} for part in parts) or not value.startswith("docs/"):
        raise MirrorPolicyError(f"shared-docs mirror policy: invalid {label}")
    if not glob and any(character in value for character in "*?["):
        raise MirrorPolicyError(f"shared-docs mirror policy: invalid {label}")
    return value


def _parse_mirror_policy(data: bytes) -> MirrorPolicy:
    raw = _strict_policy_object(data)
    expected = {"schema_version", "set_id", "static_paths", "glob_patterns", "target_repo", "target_kind"}
    if set(raw) != expected or raw.get("schema_version") != "shared-docs-mirror-policy.v1":
        raise MirrorPolicyError("shared-docs mirror policy: unsupported schema")
    set_id = raw.get("set_id")
    target_repo = raw.get("target_repo")
    target_kind = raw.get("target_kind")
    if not all(isinstance(value, str) and value for value in (set_id, target_repo, target_kind)):
        raise MirrorPolicyError("shared-docs mirror policy: invalid selector")
    static_paths = raw.get("static_paths")
    glob_patterns = raw.get("glob_patterns")
    if not isinstance(static_paths, list) or not isinstance(glob_patterns, list):
        raise MirrorPolicyError("shared-docs mirror policy: invalid path list")
    parsed_static = tuple(_safe_mirror_path(value, label="static path") for value in static_paths)
    parsed_globs = tuple(_safe_mirror_path(value, label="glob pattern", glob=True) for value in glob_patterns)
    if not parsed_static or not parsed_globs or len(set(parsed_static)) != len(parsed_static) or len(set(parsed_globs)) != len(parsed_globs):
        raise MirrorPolicyError("shared-docs mirror policy: duplicate or empty path list")
    return MirrorPolicy(
        set_id=set_id,
        static_paths=parsed_static,
        glob_patterns=parsed_globs,
        target_repo=target_repo,
        target_kind=target_kind,
    )


def load_shared_docs_mirror_policy(
    *,
    content_profile_id: str = "default",
    policy_root: Path | None = None,
) -> MirrorPolicy:
    """Return the generic policy for a supported local or consumer identity.

    A source tree cannot infer a consumer's mirror targets.  Consumers that
    need one must pass an explicit checked-in policy to the pure callers below;
    no private profile file is consulted here.
    """

    profile = content_profile_id.strip()
    if profile not in _KNOWN_CONTENT_PROFILES:
        raise MirrorPolicyError(f"unsupported content_profile_id: {content_profile_id!r}")
    return GENERIC_MIRROR_POLICY


def _normalize_repo_relative_path(value: str) -> str | None:
    """Return one normalized relative POSIX pathname, or ``None`` when invalid.

    This intentionally does not touch the filesystem.  Packetization needs the
    declared mirror membership at the exact range snapshot, whereas this
    helper's ordinary drift report additionally observes live source/target
    files.
    """

    raw = value.strip().replace("\\", "/")
    if not raw or raw.startswith("/"):
        return None
    parts = raw.split("/")
    if any(not part or part in {".", ".."} for part in parts):
        return None
    return "/".join(parts)


def _declared_glob_match(path: str, pattern: str) -> bool:
    """Match the fixed mirror globs component by component.

    ``fnmatch`` alone lets ``*`` cross a slash.  The declared patterns are
    pathname patterns, so a nested path must not become a mirror member just
    because its basename happens to match.
    """

    path_parts = path.split("/")
    pattern_parts = pattern.split("/")
    return len(path_parts) == len(pattern_parts) and all(
        fnmatchcase(path_part, pattern_part)
        for path_part, pattern_part in zip(path_parts, pattern_parts)
    )


def is_declared_mirror_path(
    repo_relative_path: str,
    *,
    policy: MirrorPolicy = GENERIC_MIRROR_POLICY,
) -> bool:
    """Pure, snapshot-stable membership test for packetization applicability."""

    normalized = _normalize_repo_relative_path(repo_relative_path)
    if normalized is None:
        return False
    return normalized in policy.static_paths or any(
        _declared_glob_match(normalized, pattern) for pattern in policy.glob_patterns
    )


def declared_mirror_target_applicability(
    repo_relative_path: str,
    *,
    policy: MirrorPolicy = GENERIC_MIRROR_POLICY,
) -> dict[str, object] | None:
    """Return the checked-in target authority for one declared mirror pathname.

    The same relative pathname is the target-side mirror carrier.  This is a
    declared mirror relationship, not an inference from a live sibling checkout
    or from the report's ``recommended_outcome``.
    """

    normalized = _normalize_repo_relative_path(repo_relative_path)
    if (
        normalized is None
        or policy.target_repo is None
        or policy.target_kind is None
        or not is_declared_mirror_path(normalized, policy=policy)
    ):
        return None
    return {
        "target_repo": policy.target_repo,
        "target_kind": policy.target_kind,
        "target_writable_carriers": [normalized],
        "authority": "shared_docs_mirror_drift declared static_paths/glob_patterns",
    }


@dataclass(frozen=True)
class MirrorEntry:
    source: str
    target: str
    status: str
    recommended_outcome: str
    source_sha256: str | None = None
    target_sha256: str | None = None
    source_bytes: int | None = None
    target_bytes: int | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "source": self.source,
            "target": self.target,
            "status": self.status,
            "recommended_outcome": self.recommended_outcome,
            "source_sha256": self.source_sha256,
            "target_sha256": self.target_sha256,
            "source_bytes": self.source_bytes,
            "target_bytes": self.target_bytes,
        }


def _repo_relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def expand_mirror_set(
    source_root: Path,
    *,
    policy: MirrorPolicy = GENERIC_MIRROR_POLICY,
) -> list[str]:
    """Return the exact source-owned mirror-set paths in stable order."""
    source_root = source_root.resolve()
    rel_paths: set[str] = set(policy.static_paths)

    for pattern in policy.glob_patterns:
        for path in sorted(source_root.glob(pattern)):
            if path.is_file():
                rel_paths.add(_repo_relative(path, source_root))

    return sorted(rel_paths)


def _entry_for_path(source_root: Path, target_root: Path, rel_path: str) -> MirrorEntry:
    source_path = source_root / rel_path
    target_path = target_root / rel_path
    if not source_path.is_file():
        return MirrorEntry(
            source=rel_path,
            target=rel_path,
            status="missing_source",
            recommended_outcome="source_error",
        )

    source_data = _read_bytes(source_path)
    source_hash = _sha256(source_data)
    if not target_path.is_file():
        return MirrorEntry(
            source=rel_path,
            target=rel_path,
            status="missing_target",
            recommended_outcome="packet_required",
            source_sha256=source_hash,
            source_bytes=len(source_data),
        )

    target_data = _read_bytes(target_path)
    target_hash = _sha256(target_data)
    if source_data == target_data:
        status = "in_sync"
        outcome = "no_packet_required"
    else:
        status = "drift"
        outcome = "packet_required"

    return MirrorEntry(
        source=rel_path,
        target=rel_path,
        status=status,
        recommended_outcome=outcome,
        source_sha256=source_hash,
        target_sha256=target_hash,
        source_bytes=len(source_data),
        target_bytes=len(target_data),
    )


def build_report(
    source_root: Path,
    target_root: Path,
    *,
    policy: MirrorPolicy = GENERIC_MIRROR_POLICY,
) -> dict[str, object]:
    source_root = source_root.resolve()
    target_root = target_root.resolve()
    rel_paths = expand_mirror_set(source_root, policy=policy)
    entries = [_entry_for_path(source_root, target_root, rel_path) for rel_path in rel_paths]
    summary = {status: 0 for status in ("in_sync", "drift", "missing_target", "missing_source")}
    for entry in entries:
        summary[entry.status] = summary.get(entry.status, 0) + 1
    summary["total"] = len(entries)

    has_source_error = any(entry.status == "missing_source" for entry in entries)
    has_drift = any(entry.status in DRIFT_STATUSES for entry in entries)
    if has_source_error:
        recommended_outcome = "source_error"
    elif has_drift:
        recommended_outcome = "packet_required"
    else:
        recommended_outcome = "no_packet_required"

    return {
        "source_root": source_root.as_posix(),
        "target_root": target_root.as_posix(),
        "mirror_set": {
            "id": policy.set_id,
            "static_paths": list(policy.static_paths),
            "glob_patterns": list(policy.glob_patterns),
            "entry_count": len(entries),
        },
        "recommended_outcome": recommended_outcome,
        "summary": summary,
        "entries": [entry.to_json() for entry in entries],
    }


def _render_text(report: dict[str, object]) -> str:
    mirror_set = report["mirror_set"]
    assert isinstance(mirror_set, dict)
    summary = report["summary"]
    assert isinstance(summary, dict)
    lines = [
        "shared docs mirror drift",
        f"source_root: {report['source_root']}",
        f"target_root: {report['target_root']}",
        f"mirror_set: {mirror_set['id']}",
        f"recommended_outcome: {report['recommended_outcome']}",
        (
            "summary: "
            f"total={summary.get('total', 0)} "
            f"in_sync={summary.get('in_sync', 0)} "
            f"drift={summary.get('drift', 0)} "
            f"missing_target={summary.get('missing_target', 0)} "
            f"missing_source={summary.get('missing_source', 0)}"
        ),
        "entries:",
    ]
    entries = report["entries"]
    assert isinstance(entries, list)
    for raw_entry in entries:
        assert isinstance(raw_entry, dict)
        lines.append(
            f"- {str(raw_entry['status']).upper()} "
            f"{raw_entry['source']} -> {raw_entry['target']} "
            f"({raw_entry['recommended_outcome']})"
        )
    return "\n".join(lines)


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare the exact shared docs mirror set without writing target files.",
    )
    parser.add_argument(
        "--source-root",
        default=REPO_ROOT,
        type=Path,
        help="source repo root (default: this planveyor checkout)",
    )
    parser.add_argument(
        "--target-root",
        required=True,
        type=Path,
        help="explicit target repo root",
    )
    parser.add_argument(
        "--content-profile-id",
        default="default",
        choices=sorted(_KNOWN_CONTENT_PROFILES),
        help="Resolved local profile; it does not imply a target mirror policy.",
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument(
        "--fail-on-drift",
        action="store_true",
        help="return non-zero when drift or missing target files are found",
    )
    return parser.parse_args(argv)


def _has_drift(report: dict[str, object]) -> bool:
    return report.get("recommended_outcome") == "packet_required"


def _has_source_error(report: dict[str, object]) -> bool:
    return report.get("recommended_outcome") == "source_error"


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        policy = load_shared_docs_mirror_policy(content_profile_id=args.content_profile_id)
        report = build_report(args.source_root, args.target_root, policy=policy)
    except MirrorPolicyError as exc:
        print(f"shared_docs_mirror_drift: policy invalid: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(_render_text(report))

    if _has_source_error(report):
        return 2
    if args.fail_on_drift and _has_drift(report):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

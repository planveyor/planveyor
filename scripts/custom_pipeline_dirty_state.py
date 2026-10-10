#!/usr/bin/env python3
"""Read-only dirty-state ownership precheck for Manager custom pipeline.

The helper does not stage, restore, stash, delete or commit files. It only
classifies current git dirt relative to the active plan's exact bundle and
optional repo-backed sibling evidence supplied by the caller.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
SCHEMA = "custom_pipeline_dirty_state.v1"

_RUNTIME_SCRIPT_DIR_TEXT = str(SCRIPT_DIR)
while _RUNTIME_SCRIPT_DIR_TEXT in sys.path:
    sys.path.remove(_RUNTIME_SCRIPT_DIR_TEXT)
sys.path.insert(0, _RUNTIME_SCRIPT_DIR_TEXT)


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
    if package_file is not None and not _module_has_expected_origin(package, SCRIPT_DIR / "__init__.py"):
        return False
    return True


def _authority_module() -> Any:
    """Load the sibling authority module only from this helper's runtime."""

    package_is_local = _scripts_package_is_local()
    expected = SCRIPT_DIR / "contract_authority_context.py"
    direct = sys.modules.get("contract_authority_context")
    packaged = sys.modules.get("scripts.contract_authority_context")
    for module in (direct, packaged):
        if module is not None and not _module_has_expected_origin(module, expected):
            raise ImportError("authority module has an unsafe origin")
    if direct is not None and packaged is not None and direct is not packaged:
        raise ImportError("authority module aliases are split")
    module = direct or packaged
    if module is None:
        module = importlib.import_module("contract_authority_context")
        if not _module_has_expected_origin(module, expected):
            raise ImportError("authority module has an unsafe origin")
    sys.modules["contract_authority_context"] = module
    if package_is_local:
        sys.modules["scripts.contract_authority_context"] = module
    return module


_authority = _authority_module()
if TYPE_CHECKING:
    from contract_authority_context import ContractAuthorityError, resolve_top_level_context
else:
    ContractAuthorityError = _authority.ContractAuthorityError
    resolve_top_level_context = _authority.resolve_top_level_context

CODE_DRAFT_RE = re.compile(r"docs/code_drafts/[A-Za-z0-9][A-Za-z0-9_./-]*\.md")
REVIEW_ARTIFACT_RE = re.compile(r"docs/(?:code_reviews|doc_reviews)/[A-Za-z0-9][A-Za-z0-9_./-]*\.md")
JSON_FENCE_RE = re.compile(r"```json\s*(?P<body>.*?)```", re.DOTALL | re.IGNORECASE)

CONTINUE_CLASSES = {"exact_bundle", "committed_sibling_followup"}


@dataclass(frozen=True)
class DirtyRecord:
    status: str
    path: str
    source_path: str | None = None
    source_kind: str | None = None


class GitStatusParseError(ValueError):
    """Raised when porcelain v1 -z output is structurally malformed."""


def _repo_rel(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _resolve_plan_path(plan_path: str | Path, repo_root: Path) -> Path:
    path = Path(plan_path)
    if path.is_absolute():
        return path
    return repo_root / path


def _run_git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def _run_git_status(repo_root: Path) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
        ],
        text=False,
        capture_output=True,
        check=False,
    )


def _unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _section_text(text: str, heading: str) -> str:
    wanted = heading.strip().lower()
    lines = text.splitlines()
    start: int | None = None
    for index, line in enumerate(lines):
        if line.startswith("## ") and line[3:].strip().lower() == wanted:
            start = index + 1
            break
    if start is None:
        return ""
    end = len(lines)
    for index in range(start, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return "\n".join(lines[start:end])


def _extract_json_payload_with_key(text: str, key: str) -> dict[str, Any] | None:
    for match in JSON_FENCE_RE.finditer(text):
        try:
            payload = json.loads(match.group("body"))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and isinstance(payload.get(key), dict):
            return payload
    return None


def _parse_sibling_evidence(values: list[str]) -> tuple[dict[str, str], list[str]]:
    evidence: dict[str, str] = {}
    errors: list[str] = []
    for value in values:
        if "=" not in value:
            errors.append(f"invalid sibling evidence {value!r}; expected PATH=OWNER_REF")
            continue
        path, owner_ref = value.split("=", 1)
        # Preserve PATH exactly (incl. trailing/whitespace identity); trim only OWNER_REF.
        owner_ref = owner_ref.strip()
        if path == "" or owner_ref == "":
            errors.append(f"invalid sibling evidence {value!r}; expected non-empty PATH=OWNER_REF")
            continue
        evidence[path] = owner_ref
    return evidence, errors


def _parse_git_status(stdout: bytes) -> list[DirtyRecord]:
    if not stdout:
        return []
    if not stdout.endswith(b"\0"):
        raise GitStatusParseError("porcelain stream is missing final NUL")

    tokens = stdout[:-1].split(b"\0")
    parsed: list[tuple[bytes, bytes, bytes | None, str | None]] = []
    index = 0
    valid_status_bytes = b" MTADRCU?!"
    while index < len(tokens):
        token = tokens[index]
        if len(token) < 4 or token[2:3] != b" " or not token[3:]:
            raise GitStatusParseError(f"invalid porcelain record at token {index}")
        status = token[:2]
        if status == b"  " or any(byte not in valid_status_bytes for byte in status):
            raise GitStatusParseError(f"invalid porcelain status at token {index}")

        has_rename = b"R" in status
        has_copy = b"C" in status
        if has_rename and has_copy:
            raise GitStatusParseError(f"ambiguous rename/copy status at token {index}")

        source: bytes | None = None
        source_kind: str | None = None
        if has_rename or has_copy:
            index += 1
            if index >= len(tokens) or not tokens[index]:
                raise GitStatusParseError("rename/copy record is missing source path")
            source = tokens[index]
            source_kind = "rename" if has_rename else "copy"

        parsed.append((status, token[3:], source, source_kind))
        index += 1

    return [
        DirtyRecord(
            status=status.decode("ascii"),
            path=os.fsdecode(path),
            source_path=os.fsdecode(source) if source is not None else None,
            source_kind=source_kind,
        )
        for status, path, source, source_kind in parsed
    ]


def _committed_path(repo_root: Path, path: str) -> str:
    result = _run_git(repo_root, "log", "-1", "--format=%H", "--", path)
    if result.returncode != 0:
        return ""
    return result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""


def _committed_ref(repo_root: Path, owner_ref: str) -> str:
    ref_path = repo_root / owner_ref
    if ref_path.exists() and _committed_path(repo_root, owner_ref):
        return _committed_path(repo_root, owner_ref)
    result = _run_git(repo_root, "cat-file", "-e", f"{owner_ref}^{{commit}}")
    if result.returncode == 0:
        shown = _run_git(repo_root, "rev-parse", "--verify", owner_ref)
        return shown.stdout.strip() if shown.returncode == 0 else owner_ref
    return ""


def _path_is_tracked_in_head(repo_root: Path, path: str) -> bool:
    result = _run_git(repo_root, "cat-file", "-t", f"HEAD:{path}")
    return result.returncode == 0 and result.stdout.strip() in {"blob", "commit"}


def _exact_bundle_from_plan(
    plan_path: Path,
    repo_root: Path,
) -> tuple[list[str], set[str], list[str]]:
    plan_rel = _repo_rel(plan_path, repo_root)
    if not plan_path.exists():
        return [], set(), [f"PLAN_PATH does not exist: {plan_rel}"]
    try:
        plan_text = plan_path.read_text(encoding="utf-8")
    except OSError as exc:
        return [], set(), [f"PLAN_PATH cannot be read: {exc}"]

    draft_refs = _unique_preserve_order(CODE_DRAFT_RE.findall(plan_text))
    if not draft_refs:
        return [], set(), ["no code draft reference found in plan"]
    if len(draft_refs) > 1:
        return [], set(), [f"multiple code draft references found: {', '.join(draft_refs)}"]

    draft_rel = draft_refs[0]
    draft_path = repo_root / draft_rel
    if not draft_path.exists():
        return [], set(), [f"linked code draft does not exist: {draft_rel}"]
    try:
        draft_text = draft_path.read_text(encoding="utf-8")
    except OSError as exc:
        return [], set(), [f"linked code draft cannot be read: {exc}"]

    payload = _extract_json_payload_with_key(draft_text, "code_draft_meta")
    if payload is None:
        return [], set(), [f"code_draft_meta JSON carrier is missing: {draft_rel}"]
    meta = payload["code_draft_meta"]
    targets = meta.get("targets")
    if not isinstance(targets, list) or not targets:
        return [], set(), [f"code_draft_meta.targets is missing or empty: {draft_rel}"]

    target_paths: list[str] = []
    errors: list[str] = []
    for target in targets:
        if not isinstance(target, dict) or not isinstance(target.get("path"), str) or not target["path"]:
            errors.append(f"invalid code_draft_meta.targets entry: {target!r}")
            continue
        target_paths.append(target["path"])

    raw_deleted_paths = meta.get("deleted_paths", [])
    if raw_deleted_paths is None:
        raw_deleted_paths = []
    deleted_paths: list[str] = []
    if not isinstance(raw_deleted_paths, list):
        errors.append("code_draft_meta.deleted_paths must be a list when present")
    else:
        for deleted in raw_deleted_paths:
            if (
                not isinstance(deleted, dict)
                or not isinstance(deleted.get("path"), str)
                or not deleted["path"]
            ):
                errors.append(f"invalid code_draft_meta.deleted_paths entry: {deleted!r}")
                continue
            deleted_path = deleted["path"]
            if not _path_is_tracked_in_head(repo_root, deleted_path):
                errors.append(
                    "code_draft_meta.deleted_paths path is not tracked in HEAD: "
                    + repr(deleted_path)
                )
                continue
            deleted_paths.append(deleted_path)

    meta_plan = meta.get("plan")
    if meta_plan != plan_rel:
        errors.append(f"code_draft_meta.plan mismatch: expected {plan_rel}, got {meta_plan!r}")
    duplicate_targets = sorted({target for target in target_paths if target_paths.count(target) > 1})
    if duplicate_targets:
        errors.append(f"duplicate code_draft_meta.targets paths: {', '.join(duplicate_targets)}")
    duplicate_deleted_paths = sorted(
        {path for path in deleted_paths if deleted_paths.count(path) > 1}
    )
    if duplicate_deleted_paths:
        errors.append(
            "duplicate code_draft_meta.deleted_paths paths: " + ", ".join(duplicate_deleted_paths)
        )
    target_deletion_overlap = sorted(set(target_paths) & set(deleted_paths))
    if target_deletion_overlap:
        errors.append(
            "paths cannot appear in both code_draft_meta.targets and deleted_paths: "
            + ", ".join(target_deletion_overlap)
        )
    missing_targets = [target for target in target_paths if not (repo_root / target).exists()]
    if missing_targets:
        errors.append(f"missing code_draft_meta.targets paths: {', '.join(missing_targets)}")
    if errors:
        return [], set(), errors

    review_refs = REVIEW_ARTIFACT_RE.findall(_section_text(plan_text, "Review artifacts"))
    exact_paths = [plan_rel, draft_rel, *target_paths, *deleted_paths, *review_refs]
    return _unique_preserve_order(exact_paths), set(deleted_paths), []


def _classify_record(
    repo_root: Path,
    record: DirtyRecord,
    exact_paths: set[str],
    sibling_evidence: dict[str, str],
) -> dict[str, Any]:
    item = _classify_path(repo_root, record.path, record.status, exact_paths, sibling_evidence)
    if record.source_kind != "rename" or record.source_path is None:
        return item

    source_item = _classify_path(
        repo_root,
        record.source_path,
        " D",
        exact_paths,
        sibling_evidence,
    )
    if not source_item.get("blocking"):
        return item

    source_reason = (
        f"rename source path={record.source_path} ownership mismatch: {source_item['reason']}"
    )
    if item.get("blocking"):
        item["reason"] = f"{item['reason']}; {source_reason}"
        return item

    return {
        "path": record.path,
        "git_status": record.status,
        "ownership_class": source_item["ownership_class"],
        "owner_ref": source_item.get("owner_ref", ""),
        "reason": source_reason,
        "blocking": True,
    }


def _classify_path(
    repo_root: Path,
    path: str,
    status: str,
    exact_paths: set[str],
    sibling_evidence: dict[str, str],
) -> dict[str, Any]:
    if path in exact_paths:
        return {
            "path": path,
            "git_status": status,
            "ownership_class": "exact_bundle",
            "owner_ref": "current PLAN_PATH exact bundle",
            "reason": "path is part of the current plan exact bundle",
            "blocking": False,
        }

    owner_ref = sibling_evidence.get(path)
    if owner_ref:
        path_commit = _committed_path(repo_root, path)
        owner_commit = _committed_ref(repo_root, owner_ref)
        if path_commit and owner_commit:
            return {
                "path": path,
                "git_status": status,
                "ownership_class": "committed_sibling_followup",
                "owner_ref": owner_ref,
                "reason": "outside-bundle path has repo-backed sibling path/ref evidence",
                "blocking": False,
                "evidence": {
                    "path_commit": path_commit,
                    "owner_commit": owner_commit,
                },
            }
        missing = []
        if not path_commit:
            missing.append("path_commit")
        if not owner_commit:
            missing.append("owner_commit")
        return {
            "path": path,
            "git_status": status,
            "ownership_class": "ambiguous_owner",
            "owner_ref": owner_ref,
            "reason": "sibling evidence mismatch: missing " + ", ".join(missing),
            "blocking": True,
        }

    if status == "??":
        return {
            "path": path,
            "git_status": status,
            "ownership_class": "ambiguous_owner",
            "owner_ref": "",
            "reason": "untracked outside-bundle path has no repo-backed owner evidence",
            "blocking": True,
        }
    return {
        "path": path,
        "git_status": status,
        "ownership_class": "unrelated_dirty",
        "owner_ref": "",
        "reason": "tracked outside-bundle path has no repo-backed owner evidence",
        "blocking": True,
    }


def build_precheck(
    plan_path: str | Path,
    *,
    repo_root: Path | None = None,
    sibling_evidence: dict[str, str] | None = None,
) -> dict[str, Any]:
    if repo_root is None:
        repo_root = resolve_top_level_context().project_root
    else:
        repo_root = repo_root.resolve()
    sibling_evidence = sibling_evidence or {}
    resolved_plan = _resolve_plan_path(plan_path, repo_root)
    plan_rel = _repo_rel(resolved_plan, repo_root)

    exact_paths, _deleted_paths, bundle_errors = _exact_bundle_from_plan(resolved_plan, repo_root)
    if bundle_errors:
        return {
            "schema": SCHEMA,
            "plan_path": plan_rel,
            "verdict": "stop",
            "reason": "missing_or_invalid_exact_bundle",
            "safe_next_action": "fix PLAN_PATH/code_draft_meta exact bundle before running custom pipeline",
            "exact_bundle": {"paths": [], "errors": bundle_errors},
            "files": [],
            "summary": {"total": 0, "blocking": 1},
        }

    git_status = _run_git_status(repo_root)
    if git_status.returncode != 0:
        return {
            "schema": SCHEMA,
            "plan_path": plan_rel,
            "verdict": "stop",
            "reason": "git_status_unavailable",
            "safe_next_action": "fix git status/readback before running custom pipeline",
            "exact_bundle": {"paths": exact_paths, "errors": []},
            "files": [],
            "summary": {"total": 0, "blocking": 1},
            "git_error": os.fsdecode(git_status.stderr[:4096]),
        }

    try:
        records = _parse_git_status(git_status.stdout)
    except GitStatusParseError as exc:
        return {
            "schema": SCHEMA,
            "plan_path": plan_rel,
            "verdict": "stop",
            "reason": "git_status_malformed",
            "safe_next_action": "fix malformed git status/readback before running custom pipeline",
            "exact_bundle": {"paths": exact_paths, "errors": []},
            "files": [],
            "summary": {"total": 0, "blocking": 1},
            "git_error": str(exc),
        }
    files = [
        _classify_record(repo_root, record, set(exact_paths), sibling_evidence)
        for record in records
    ]
    blocking = [item for item in files if item.get("blocking")]
    verdict = "stop" if blocking else "continue"
    ownership_classes = sorted({str(item["ownership_class"]) for item in files})
    reason = "all_dirty_paths_owned" if verdict == "continue" else "dirty_paths_need_owner_attribution"
    safe_next_action = (
        "continue custom pipeline"
        if verdict == "continue"
        else "stop custom pipeline; resolve outside-bundle dirt or supply repo-backed sibling evidence"
    )
    return {
        "schema": SCHEMA,
        "plan_path": plan_rel,
        "verdict": verdict,
        "reason": reason,
        "safe_next_action": safe_next_action,
        "exact_bundle": {"paths": exact_paths, "errors": []},
        "files": files,
        "summary": {
            "total": len(files),
            "blocking": len(blocking),
            "ownership_classes": ownership_classes,
        },
    }


def _compact_escape(value: str) -> str:
    escaped: list[str] = []
    short_escapes = {
        "\b": r"\b",
        "\f": r"\f",
        "\n": r"\n",
        "\r": r"\r",
        "\t": r"\t",
    }
    for char in value:
        if char == "\\":
            escaped.append(r"\\")
        elif char == '"':
            escaped.append(r'\"')
        elif char in short_escapes:
            escaped.append(short_escapes[char])
        elif char.isprintable():
            escaped.append(char)
        else:
            codepoint = ord(char)
            if codepoint <= 0xFFFF:
                escaped.append(f"\\u{codepoint:04x}")
            else:
                codepoint -= 0x10000
                escaped.append(f"\\u{0xD800 + (codepoint >> 10):04x}")
                escaped.append(f"\\u{0xDC00 + (codepoint & 0x3FF):04x}")
    return "".join(escaped)


def _render_text(payload: dict[str, Any]) -> str:
    lines = [
        f"schema={payload['schema']}",
        f"plan_path={payload['plan_path']}",
        f"verdict={payload['verdict']}",
        f"reason={payload['reason']}",
        f"safe_next_action={payload['safe_next_action']}",
        f"dirty_total={payload['summary']['total']}",
        f"dirty_blocking={payload['summary']['blocking']}",
    ]
    for item in payload["files"]:
        lines.append(
            "file="
            + _compact_escape(item["path"])
            + f" status={item['git_status']} ownership_class={item['ownership_class']}"
            + f" blocking={str(item['blocking']).lower()}"
            + (
                f" owner_ref={_compact_escape(item['owner_ref'])}"
                if item.get("owner_ref")
                else ""
            )
            + f" reason={_compact_escape(item['reason'])}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan_path", help="Current PLAN_PATH to classify against")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--sibling-evidence",
        action="append",
        default=[],
        metavar="PATH=OWNER_REF",
        help="Repo-backed evidence that an outside-bundle dirty path belongs to a sibling follow-up",
    )
    args = parser.parse_args(argv)

    try:
        context = resolve_top_level_context()
    except ContractAuthorityError as exc:
        print(
            "custom-pipeline-dirty-state: contract authority preflight failed: "
            + exc.reason_code,
            file=sys.stderr,
        )
        return 2

    sibling_evidence, evidence_errors = _parse_sibling_evidence(args.sibling_evidence)
    if evidence_errors:
        payload = {
            "schema": SCHEMA,
            "plan_path": args.plan_path,
            "verdict": "stop",
            "reason": "invalid_sibling_evidence",
            "safe_next_action": "fix --sibling-evidence arguments before running custom pipeline",
            "exact_bundle": {"paths": [], "errors": []},
            "files": [],
            "summary": {"total": 0, "blocking": 1},
            "errors": evidence_errors,
        }
    else:
        payload = build_precheck(
            args.plan_path,
            repo_root=context.project_root,
            sibling_evidence=sibling_evidence,
        )

    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(_render_text(payload))
    return 0 if payload["verdict"] == "continue" else 2


if __name__ == "__main__":
    raise SystemExit(main())

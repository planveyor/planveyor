#!/usr/bin/env python3
"""Fail-closed local closeout for merge-tracker step:ready_to_push."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import merge_bundle_report
import merge_gate_policy
import range_review_risk_packet
from shared_docs_mirror_drift import (
    GENERIC_MIRROR_POLICY,
    MirrorPolicy,
    MirrorPolicyError,
    load_shared_docs_mirror_policy,
)


READY_STEP = "step:ready_to_push"
DIRTY_ACCEPTED_RECOVERY = "stage all report-accepted paths and rerun"
NO_STAGING_COMMAND = "N/A (why=no staging command for this blocker)"
NO_PATHSPEC_FILE = "N/A (why=no pathspec file generated)"
NO_PATHSPEC_FILE_FORMAT = "N/A (why=no pathspec file generated)"
SHORT_STAGING_COMMAND_MAX_PATHS = 8
SHORT_STAGING_COMMAND_MAX_LENGTH = 700
PATHSPEC_FILE_FORMAT_NUL = "NUL-delimited"
TERMINAL_PROOF_STATE = "terminal_ready_to_push_proof"
CLOSEOUT_RECEIPT_SCHEMA_VERSION = merge_bundle_report.READY_TO_PUSH_CLOSEOUT_SCHEMA_VERSION
CLOSEOUT_RECEIPT_HEADING = "Ready-to-push closeout receipt JSON"
GIT_DIAGNOSTIC_TIMEOUT_SECONDS = 30
GIT_TIMEOUT_RETURN_CODE = 124
STEP_LINE_RE = re.compile(
    r"^(?P<prefix>\s*[-*]\s*\[)(?P<mark>[ xX])(?P<suffix>\]\s+)"
    r"(?P<key>step:[^\s#]+)(?P<rest>.*)$"
)


def _git_timeout_detail(args: tuple[str, ...], timeout: float | int) -> str:
    return f"git {' '.join(args)} timed out after {timeout:g}s"


def _run_git(root: Path, *args: str) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        text=True,
        capture_output=True,
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _run_git_diagnostic(root: Path, *args: str) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            text=True,
            capture_output=True,
            check=False,
            timeout=GIT_DIAGNOSTIC_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        return (
            GIT_TIMEOUT_RETURN_CODE,
            stdout,
            _git_timeout_detail(args, GIT_DIAGNOSTIC_TIMEOUT_SECONDS),
        )
    return proc.returncode, proc.stdout, proc.stderr


def _git_lines(root: Path, *args: str) -> tuple[list[str], str | None]:
    rc, stdout, stderr = _run_git_diagnostic(root, *args)
    if rc != 0:
        return [], (stderr.strip() or stdout.strip() or f"git {' '.join(args)} failed")
    return [line.strip() for line in stdout.splitlines() if line.strip()], None


def _report_item_paths(report: dict[str, Any], bucket: str) -> list[str]:
    return [str(item.get("path", "")) for item in report.get("git_status", {}).get(bucket, []) if item.get("path")]


def _all_status_items(report: dict[str, Any]) -> list[dict[str, Any]]:
    status = report.get("git_status", {})
    out: list[dict[str, Any]] = []
    for bucket in ("required", "candidate_contextual", "suspicious"):
        for item in status.get(bucket, []):
            if isinstance(item, dict):
                copied = dict(item)
                copied["bucket"] = bucket
                out.append(copied)
    return out


def _paths_with_state(items: list[dict[str, Any]], needle: str) -> list[str]:
    paths: list[str] = []
    for item in items:
        state = str(item.get("git_state", ""))
        if needle == "unstaged" and "unstaged" in state:
            paths.append(str(item.get("path", "")))
        elif needle == "untracked" and state == "untracked":
            paths.append(str(item.get("path", "")))
    return sorted(path for path in paths if path)


def _unique_sorted(paths: list[str]) -> list[str]:
    return sorted({path for path in paths if path})


def _accepted_dirty_paths(diagnostics: dict[str, Any]) -> list[str]:
    return _unique_sorted(
        [
            *[str(path) for path in diagnostics.get("unstaged_tracked_paths", [])],
            *[str(path) for path in diagnostics.get("untracked_accepted_paths", [])],
        ]
    )


def _why_blocked(code: str) -> str:
    if code in {"unstaged_tracked_paths", "untracked_paths"}:
        return "dirty_report_accepted_paths"
    if code == "suspicious_paths":
        return "suspicious_paths"
    if code == "suspicious_staged_paths":
        return "unexpected_staged_paths"
    if code == "red_report":
        return "red_merge_bundle_report"
    if code in {"wrong_current_step", "missing_ready_step", "already_closed_with_staged_paths"}:
        return "merge_tracker_state"
    if code.startswith("git_") or code == "tracker_tick_failed":
        return "local_git_or_tracker_error"
    if "risk_packet" in code:
        return "risk_packet_precondition"
    return code or "unknown_blocker"


def _short_staging_command(paths: list[str]) -> str | None:
    if len(paths) > SHORT_STAGING_COMMAND_MAX_PATHS:
        return None
    command = "git add -- " + " ".join(shlex.quote(path) for path in paths)
    if len(command) > SHORT_STAGING_COMMAND_MAX_LENGTH:
        return None
    return command


def _pathspec_file_path(range_id: str) -> str:
    safe_range_id = re.sub(r"[^A-Za-z0-9._-]+", "_", range_id).strip("._-") or "unknown_range"
    return f".tmp/planveyor_ready_to_push_closeout/{safe_range_id}/accepted_paths.pathspec"


def _write_pathspec_file(root: Path, rel_path: str, paths: list[str]) -> None:
    destination = root / rel_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes("".join(f"{path}\0" for path in paths).encode("utf-8"))


def _blocked_staging_readback(
    *,
    root: Path,
    range_id: str,
    code: str,
    diagnostics: dict[str, Any],
) -> dict[str, Any]:
    accepted_dirty_paths = _accepted_dirty_paths(diagnostics)
    if code not in {"unstaged_tracked_paths", "untracked_paths"} or not accepted_dirty_paths:
        return {
            "why_blocked": _why_blocked(code),
            "staging_command": NO_STAGING_COMMAND,
            "pathspec_file": NO_PATHSPEC_FILE,
            "pathspec_file_format": NO_PATHSPEC_FILE_FORMAT,
            "pathspec_paths_count": 0,
            "pending_owner_gate": "git push",
        }

    short_command = _short_staging_command(accepted_dirty_paths)
    if short_command:
        return {
            "why_blocked": _why_blocked(code),
            "staging_command": short_command,
            "pathspec_file": "N/A (why=short git add command emitted)",
            "pathspec_file_format": "N/A (why=short git add command emitted)",
            "pathspec_paths_count": len(accepted_dirty_paths),
            "pending_owner_gate": "git push",
        }

    pathspec_file = _pathspec_file_path(range_id)
    _write_pathspec_file(root, pathspec_file, accepted_dirty_paths)
    return {
        "why_blocked": _why_blocked(code),
        "staging_command": (
            f"git add --pathspec-from-file {shlex.quote(pathspec_file)} --pathspec-file-nul"
        ),
        "pathspec_file": pathspec_file,
        "pathspec_file_format": PATHSPEC_FILE_FORMAT_NUL,
        "pathspec_paths_count": len(accepted_dirty_paths),
        "pending_owner_gate": "git push",
    }


def _not_blocked_staging_readback() -> dict[str, Any]:
    return {
        "why_blocked": "N/A (why=not blocked)",
        "staging_command": "N/A (why=not blocked)",
        "pathspec_file": "N/A (why=not blocked)",
        "pathspec_file_format": "N/A (why=not blocked)",
        "pathspec_paths_count": 0,
    }


def _paths_for_bucket(items: list[dict[str, Any]], bucket: str) -> list[str]:
    return _unique_sorted(
        [str(item.get("path", "")) for item in items if item.get("bucket") == bucket]
    )


def _staged_accepted_paths(staged_paths: list[str], report: dict[str, Any]) -> list[str]:
    accepted = set(_report_item_paths(report, "required")) | set(
        _report_item_paths(report, "candidate_contextual")
    )
    return sorted(path for path in staged_paths if path in accepted)


def _closeout_receipt_path(report: dict[str, Any]) -> str:
    terminal_proof = report.get("ready_to_push_terminal_proof") or {}
    existing_path = str(terminal_proof.get("path") or "")
    if existing_path:
        return existing_path
    range_info = report["range"]
    timestamp = datetime.now().strftime("%y%m%d_%H%M%S")
    return (
        f"docs/reviews/{timestamp}_ready_to_push_closeout_range_"
        f"{range_info['base_short']}_{range_info['head_short']}.md"
    )


def _closeout_receipt_path_is_unowned(root: Path, receipt_path: str) -> str | None:
    destination = root / receipt_path
    if destination.exists() or destination.is_symlink():
        return f"closeout receipt already exists; refusing to overwrite pre-existing receipt: {receipt_path}"

    rc, stdout, stderr = _run_git(root, "ls-files", "--stage", "--", receipt_path)
    if rc != 0:
        return stderr.strip() or stdout.strip() or "git ls-files closeout receipt pre-state failed"
    if stdout.strip():
        return f"closeout receipt is already staged; refusing to overwrite pre-existing index entry: {receipt_path}"

    rc, stdout, stderr = _run_git(root, "ls-tree", "--name-only", "HEAD", "--", receipt_path)
    if rc != 0:
        return stderr.strip() or stdout.strip() or "git ls-tree closeout receipt pre-state failed"
    if stdout.strip():
        return f"closeout receipt is already tracked in HEAD; refusing to overwrite pre-existing receipt: {receipt_path}"
    return None


def _repo_relative_tracker(root: Path, tracker_path: Path) -> str:
    try:
        return tracker_path.resolve().relative_to(root).as_posix()
    except ValueError:
        return tracker_path.as_posix()


def _build_closeout_receipt_payload(
    *,
    root: Path,
    tracker_path: Path,
    report: dict[str, Any],
    receipt_path: str,
    staged_paths: list[str],
    tracker_tick_result: str,
) -> dict[str, Any]:
    range_info = report["range"]
    status_items = _all_status_items(report)
    staged_with_receipt = _unique_sorted([*staged_paths, receipt_path])
    staged_accepted = _unique_sorted([*_staged_accepted_paths(staged_paths, report), receipt_path])
    return {
        "schema_version": CLOSEOUT_RECEIPT_SCHEMA_VERSION,
        "range": range_info["range"],
        "base": range_info["base"],
        "head": range_info["head"],
        "range_id": f"{range_info['base_short']}..{range_info['head_short']}",
        "tracker_path": _repo_relative_tracker(root, tracker_path),
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "generated_by": "scripts/post_merge_ready_to_push_closeout.py",
        "source_command": "planveyor_post_merge_ready_to_push_closeout",
        "terminal_state": TERMINAL_PROOF_STATE,
        "final_bundle_status": str(report.get("status") or ""),
        "required_paths": _paths_for_bucket(status_items, "required"),
        "contextual_paths": _paths_for_bucket(status_items, "candidate_contextual"),
        "staged_accepted_paths": staged_accepted,
        "staged_paths_at_closeout": staged_with_receipt,
        "unexpected_staged_paths": [],
        "suspicious_paths": _paths_for_bucket(status_items, "suspicious"),
        "unstaged_tracked_paths": _paths_with_state(status_items, "unstaged"),
        "untracked_accepted_paths": _paths_with_state(
            [item for item in status_items if item.get("bucket") != "suspicious"],
            "untracked",
        ),
        "action": "local_commit_and_tracker_tick",
        "tracker_tick": {
            "intent": f"tick {READY_STEP} before committing terminal proof",
            "result": tracker_tick_result,
        },
        "pending_owner_gate": "git push",
    }


def _render_closeout_receipt(payload: dict[str, Any]) -> str:
    return (
        "# Ready-to-push closeout receipt\n\n"
        "**Status:** ✅ Done\n\n"
        f"## {CLOSEOUT_RECEIPT_HEADING}\n"
        "```json\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)}\n"
        "```\n"
    )


def _write_and_stage_closeout_receipt(
    *,
    root: Path,
    tracker_path: Path,
    report: dict[str, Any],
    staged_paths: list[str],
    tracker_tick_result: str,
) -> tuple[str, str | None]:
    receipt_path = _closeout_receipt_path(report)
    path_precondition_error = _closeout_receipt_path_is_unowned(root, receipt_path)
    if path_precondition_error:
        return receipt_path, path_precondition_error
    payload = _build_closeout_receipt_payload(
        root=root,
        tracker_path=tracker_path,
        report=report,
        receipt_path=receipt_path,
        staged_paths=staged_paths,
        tracker_tick_result=tracker_tick_result,
    )
    destination = root / receipt_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    receipt_owned = False
    try:
        receipt_file = destination.open("x", encoding="utf-8")
    except FileExistsError:
        return receipt_path, f"closeout receipt already exists; refusing to overwrite pre-existing receipt: {receipt_path}"
    except OSError as exc:
        return receipt_path, f"closeout receipt write failed: {exc.strerror or exc.__class__.__name__}"
    receipt_owned = True

    try:
        with receipt_file:
            receipt_file.write(_render_closeout_receipt(payload))
            receipt_file.flush()
    except OSError as exc:
        rollback_error = None
        if receipt_owned:
            try:
                destination.unlink()
            except FileNotFoundError:
                pass
            except OSError as unlink_exc:
                rollback_error = (
                    "closeout receipt unlink failed: "
                    f"{unlink_exc.strerror or unlink_exc.__class__.__name__}"
                )
        return receipt_path, _with_closeout_receipt_rollback_detail(
            f"closeout receipt write failed: {exc.strerror or exc.__class__.__name__}",
            rollback_error,
        )
    rc, stdout, stderr = _run_git(root, "add", "--", receipt_path)
    if rc != 0:
        rollback_error = _rollback_invocation_owned_closeout_receipt(root, receipt_path)
        return receipt_path, _with_closeout_receipt_rollback_detail(
            stderr.strip() or stdout.strip() or "git add closeout receipt failed",
            rollback_error,
        )
    return receipt_path, None


def _recommended_action_for(code: str) -> str:
    if code in {"unstaged_tracked_paths", "untracked_paths"}:
        return DIRTY_ACCEPTED_RECOVERY
    if code == "suspicious_paths":
        return "resolve suspicious paths outside report-accepted buckets and rerun"
    if code == "suspicious_staged_paths":
        return "unstage or move unexpected staged paths outside report-accepted buckets and rerun"
    if code == "red_report":
        return "fix planveyor_merge_bundle_report blockers and rerun"
    if code in {"wrong_current_step", "missing_ready_step", "already_closed_with_staged_paths"}:
        return "fix merge tracker state and rerun"
    if code == "git_cached_diff_failed":
        return "fix git cached diff readback and rerun"
    if code == "git_head_readback_failed":
        return "fix git HEAD readback and rerun"
    if code == "git_add_closeout_receipt_failed":
        return "fix ready-to-push closeout receipt staging and rerun"
    if code == "git_commit_failed":
        return "fix git commit failure and rerun"
    if code == "tracker_tick_failed":
        return "fix merge tracker tick failure and rerun"
    if "risk_packet" in code:
        return "materialize/fix the range review risk packet and rerun"
    return "resolve blocker and rerun"


def _staging_diagnostics(
    report: dict[str, Any],
    *,
    primary_blocker_code: str,
    staged_paths: list[str] | None = None,
    unexpected_staged_paths: list[str] | None = None,
) -> dict[str, Any]:
    status_items = _all_status_items(report)
    effective_staged_paths = staged_paths or []
    return {
        "primary_blocker_code": primary_blocker_code,
        "recommended_action": _recommended_action_for(primary_blocker_code),
        "required_paths": _paths_for_bucket(status_items, "required"),
        "contextual_paths": _paths_for_bucket(status_items, "candidate_contextual"),
        "staged_accepted_paths": _staged_accepted_paths(effective_staged_paths, report),
        "unstaged_tracked_paths": _paths_with_state(status_items, "unstaged"),
        "untracked_accepted_paths": _paths_with_state(
            [item for item in status_items if item.get("bucket") != "suspicious"],
            "untracked",
        ),
        "suspicious_paths": _paths_for_bucket(status_items, "suspicious"),
        "unexpected_staged_paths": _unique_sorted(unexpected_staged_paths or []),
    }


def _block(
    code: str,
    detail: str,
    *,
    root: Path,
    report: dict[str, Any],
    paths: list[str] | None = None,
    errors: list[dict[str, str]] | None = None,
    staged_paths: list[str] | None = None,
    unexpected_staged_paths: list[str] | None = None,
) -> dict[str, Any]:
    range_info = report.get("range", {})
    tracker_info = report.get("tracker", {})
    diagnostics = _staging_diagnostics(
        report,
        primary_blocker_code=code,
        staged_paths=staged_paths,
        unexpected_staged_paths=unexpected_staged_paths,
    )
    range_id = f"{range_info.get('base_short', '')}..{range_info.get('head_short', '')}"
    return {
        "status": "blocked",
        "action": "blocked",
        "blocker": {
            "code": code,
            "detail": detail,
            "paths": sorted(paths or []),
            "report_errors": errors if errors is not None else report.get("errors", []),
        },
        "range": range_info.get("range", ""),
        "range_id": range_id,
        "tracker_current_step": tracker_info.get("current_step", ""),
        "commit": None,
        "message": None,
        "staging_diagnostics": diagnostics,
        **_blocked_staging_readback(
            root=root,
            range_id=range_id,
            code=code,
            diagnostics=diagnostics,
        ),
    }


def _commit_subject(report: dict[str, Any]) -> str:
    range_info = report["range"]
    date_prefix = datetime.now().strftime("%y%m%d")
    return (
        f"{date_prefix} - process: close post-merge range "
        f"{range_info['base_short']}..{range_info['head_short']}"
    )


def _head_commit(root: Path) -> tuple[str, str | None]:
    rc, stdout, stderr = _run_git_diagnostic(root, "rev-parse", "HEAD")
    if rc != 0:
        return "", (stderr.strip() or stdout.strip() or "git rev-parse HEAD failed")
    return stdout.strip(), None


def _tick_ready_step(tracker_path: Path) -> str:
    text = tracker_path.read_text(encoding="utf-8")
    changed = False
    found = False
    out: list[str] = []
    for line in text.splitlines(keepends=True):
        body = line[:-1] if line.endswith("\n") else line
        newline = "\n" if line.endswith("\n") else ""
        match = STEP_LINE_RE.match(body)
        if not match or match.group("key") != READY_STEP:
            out.append(line)
            continue
        found = True
        if match.group("mark").lower() == "x":
            out.append(line)
            continue
        out.append(f"{match.group('prefix')}x{match.group('suffix')}{READY_STEP}{match.group('rest')}{newline}")
        changed = True
    if not found:
        raise ValueError(f"{READY_STEP} not found in {tracker_path}")
    if changed:
        tracker_path.write_text("".join(out), encoding="utf-8")
        return "ticked"
    return "already_ticked"


def _restore_tracker_text(tracker_path: Path, original_text: str, *, tick_result: str) -> str | None:
    if tick_result != "ticked":
        return None
    try:
        tracker_path.write_text(original_text, encoding="utf-8")
    except OSError as exc:
        return str(exc)
    return None


def _with_tracker_rollback_detail(detail: str, rollback_error: str | None) -> str:
    if not rollback_error:
        return detail
    return f"{detail}; tracker rollback failed: {rollback_error}"


def _unstage_generated_receipt(root: Path, receipt_path: str) -> str | None:
    rc, stdout, stderr = _run_git(root, "reset", "-q", "HEAD", "--", receipt_path)
    if rc != 0:
        return stderr.strip() or stdout.strip() or "git reset closeout receipt failed"
    return None


def _rollback_invocation_owned_closeout_receipt(root: Path, receipt_path: str) -> str | None:
    errors: list[str] = []
    rc, stdout, stderr = _run_git(root, "update-index", "--force-remove", "--", receipt_path)
    if rc != 0:
        errors.append(stderr.strip() or stdout.strip() or "git update-index closeout receipt failed")
    try:
        (root / receipt_path).unlink()
    except FileNotFoundError:
        pass
    except OSError as exc:
        errors.append(f"closeout receipt unlink failed: {exc.strerror or exc.__class__.__name__}")
    return "; ".join(errors) if errors else None


def _with_closeout_receipt_rollback_detail(detail: str, rollback_error: str | None) -> str:
    if not rollback_error:
        return detail
    return f"{detail}; closeout receipt rollback failed: {rollback_error}"


def _unstage_generated_paths(root: Path, paths: list[str]) -> str | None:
    effective_paths = [path for path in paths if path]
    if not effective_paths:
        return None
    rc, stdout, stderr = _run_git(root, "reset", "-q", "HEAD", "--", *effective_paths)
    if rc != 0:
        return stderr.strip() or stdout.strip() or "git reset generated artifacts failed"
    return None


def _unlink_generated_paths(root: Path, paths: list[str]) -> str | None:
    errors: list[str] = []
    for rel_path in paths:
        if not rel_path:
            continue
        path = root / rel_path
        try:
            if path.is_file():
                path.unlink()
        except OSError as exc:
            errors.append(f"{rel_path}: {exc}")
    return "; ".join(errors) if errors else None


def _with_post_staging_rollback_detail(
    detail: str,
    *,
    tracker_rollback_error: str | None,
    receipt_unstage_error: str | None,
) -> str:
    parts = [detail]
    if tracker_rollback_error:
        parts.append(f"tracker rollback failed: {tracker_rollback_error}")
    if receipt_unstage_error:
        parts.append(f"closeout receipt unstage failed: {receipt_unstage_error}")
    return "; ".join(parts)


def _with_generated_rollback_detail(
    detail: str,
    *,
    tracker_rollback_error: str | None,
    generated_unstage_error: str | None,
    generated_unlink_error: str | None,
) -> str:
    parts = [detail]
    if tracker_rollback_error:
        parts.append(f"tracker rollback failed: {tracker_rollback_error}")
    if generated_unstage_error:
        parts.append(f"generated artifact unstage failed: {generated_unstage_error}")
    if generated_unlink_error:
        parts.append(f"generated artifact cleanup failed: {generated_unlink_error}")
    return "; ".join(parts)


def _active_artifact_path(report: dict[str, Any], kind: str) -> str | None:
    matches = [
        artifact
        for artifact in report.get("artifacts", [])
        if isinstance(artifact, dict) and artifact.get("kind") == kind and artifact.get("path")
    ]
    active = [artifact for artifact in matches if artifact.get("active_candidate", True)]
    selected = active[0] if active else (matches[0] if matches else None)
    return str(selected.get("path")) if selected else None


def _risk_packet_path_for_closeout(report: dict[str, Any], closeout_receipt_path: str) -> str:
    range_info = report["range"]
    closeout_name = Path(closeout_receipt_path).name
    marker = "_ready_to_push_closeout_range_"
    stamp = closeout_name.split(marker, 1)[0] if marker in closeout_name else datetime.now().strftime("%y%m%d_%H%M%S")
    return (
        f"docs/reviews/{stamp}_risk_packet_range_"
        f"{range_info['base_short']}_{range_info['head_short']}.md"
    )


def _risk_packet_host_paths(
    root: Path,
    report: dict[str, Any],
    *,
    closeout_receipt_path: str,
) -> dict[str, Path]:
    hosts = {
        "review_artifact": _active_artifact_path(report, "review_artifact"),
        "post_merge_audit": _active_artifact_path(report, "post_merge_audit"),
        "operational_receipt": _active_artifact_path(report, "post_merge_operational_receipt"),
        "ready_to_push_closeout": closeout_receipt_path,
        "packetization_report": _active_artifact_path(report, "packetization_gate"),
    }
    return {
        key: (root / value if value is not None else root / "__missing__" / key)
        for key, value in hosts.items()
    }


def _changed_files_for_risk_packet(root: Path, report: dict[str, Any]) -> list[str]:
    range_ref = str(report.get("range", {}).get("range") or "")
    if range_ref:
        try:
            return range_review_risk_packet.changed_files_for_range(root, range_ref)
        except RuntimeError:
            pass
    candidates = report.get("range_diff_candidates", {})
    return [str(path) for path in candidates.get("sample_paths", []) if path]


def _risk_packet_block_code(errors: list[range_review_risk_packet.PacketError]) -> str:
    codes = {error.code for error in errors}
    if "ambiguous_risk_packet" in codes:
        return "ambiguous_risk_packet_before_ready_to_push"
    if codes & {
        "unparseable_risk_packet",
        "risk_packet_schema_mismatch",
        "risk_packet_range_mismatch",
        "risk_packet_not_ok",
    }:
        return "invalid_risk_packet_before_ready_to_push"
    return "missing_risk_packet_before_ready_to_push"


def _risk_packet_error_detail(
    *,
    report: dict[str, Any],
    expected_path: str,
    errors: list[range_review_risk_packet.PacketError],
) -> str:
    range_info = report.get("range", {})
    missing_hosts = sorted(
        {
            error.detail.split(" path", 1)[0].strip()
            for error in errors
            if error.code == "missing_truth_host" and " path" in error.detail
        }
    )
    return (
        f"expected active risk packet {expected_path} for range "
        f"{range_info.get('base_short', '')}..{range_info.get('head_short', '')}; "
        f"missing_truth_hosts={missing_hosts or 'N/A'}; "
        "recovery=planveyor_post_merge_ready_to_push_closeout after required truth hosts are present; "
        "errors="
        + json.dumps([error.as_dict() for error in errors], ensure_ascii=False, sort_keys=True)
    )


def _risk_packet_preexisting_errors(
    *,
    root: Path,
    report: dict[str, Any],
) -> tuple[list[range_review_risk_packet.PacketError], str | None]:
    range_ref = str(report.get("range", {}).get("range") or "")
    if not range_ref:
        return [], None
    readback = range_review_risk_packet.read_risk_packet(root, range_ref=range_ref)
    if readback.state == "missing":
        return [], None
    if readback.ok:
        return [
            range_review_risk_packet.PacketError(
                code="ambiguous_risk_packet",
                detail=(
                    "pre-existing active same-range risk packet would conflict with "
                    f"same-transaction closeout packet: {readback.packet_path}"
                ),
                next_action="supersede stale risk packets before ready-to-push closeout",
            )
        ], readback.packet_path
    return list(readback.errors), readback.packet_path or None


def _write_stage_validate_risk_packet(
    *,
    root: Path,
    report: dict[str, Any],
    closeout_receipt_path: str,
) -> tuple[str, list[range_review_risk_packet.PacketError], str | None, bool]:
    risk_packet_path = _risk_packet_path_for_closeout(report, closeout_receipt_path)
    payload, errors = range_review_risk_packet.build_packet_payload(
        repo_root=root,
        range_ref=str(report["range"]["range"]),
        out_path=root / risk_packet_path,
        host_paths=_risk_packet_host_paths(root, report, closeout_receipt_path=closeout_receipt_path),
        changed_files=_changed_files_for_risk_packet(root, report),
    )
    if errors:
        return risk_packet_path, list(errors), None, False
    assert payload is not None
    destination = root / risk_packet_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(range_review_risk_packet.render_packet_markdown(payload), encoding="utf-8")
    rc, stdout, stderr = _run_git(root, "add", "--", risk_packet_path)
    if rc != 0:
        return risk_packet_path, [
            range_review_risk_packet.PacketError(
                code="risk_packet_stage_failed",
                detail=stderr.strip() or stdout.strip() or "git add risk packet failed",
                next_action="fix risk packet staging and rerun",
            )
        ], None, True
    readback = range_review_risk_packet.read_risk_packet(
        root,
        range_ref=str(report["range"]["range"]),
        same_transaction_created=True,
    )
    if readback.ok and readback.packet_path != risk_packet_path:
        return risk_packet_path, [
            range_review_risk_packet.PacketError(
                code="ambiguous_risk_packet",
                detail=(
                    "active same-range risk packet readback resolved a different packet "
                    f"{readback.packet_path}; expected {risk_packet_path}"
                ),
                next_action="supersede stale risk packets and rerun ready-to-push closeout",
            )
        ], "ambiguous", True
    return risk_packet_path, list(readback.errors), readback.state, True


def close_ready_to_push(
    root: Path,
    tracker_path: Path | None = None,
    *,
    mirror_policy: MirrorPolicy = GENERIC_MIRROR_POLICY,
) -> dict[str, Any]:
    # Bind the supplied lexical root and tracker before this lifecycle resolves
    # the leaf or builds its direct report.  Legacy roots receive ``None`` and
    # retain the established closeout path.
    merge_binding = merge_gate_policy.validate_tracker_for_root(root, tracker_path)
    binding_root = root
    root = root.resolve()
    effective_tracker = (root / ".planveyor.merge_tracker.md") if tracker_path is None else tracker_path
    if not effective_tracker.is_absolute():
        effective_tracker = root / effective_tracker

    if merge_binding is None:
        report = merge_bundle_report.build_report(
            root,
            effective_tracker,
            mirror_policy=mirror_policy,
        )
    else:
        # Keep the admitted lexical spelling, including a stable root alias,
        # across report admission and the final check; Git uses physical root.
        effective_tracker = merge_binding.tracker_path
        report = merge_bundle_report.build_report(
            binding_root,
            effective_tracker,
            merge_binding=merge_binding,
            mirror_policy=mirror_policy,
        )
    staged_paths, staged_error = _git_lines(root, "diff", "--cached", "--name-only")
    if staged_error:
        return _block("git_cached_diff_failed", staged_error, root=root, report=report)

    if report.get("status") != "ok":
        return _block(
            "red_report",
            "planveyor_merge_bundle_report is not green",
            root=root,
            report=report,
            errors=report.get("errors", []),
            staged_paths=staged_paths,
        )

    tracker_info = report.get("tracker", {})
    current_step = str(tracker_info.get("current_step", ""))
    ready_checked = any(
        step.get("key") == READY_STEP and bool(step.get("checked"))
        for step in tracker_info.get("steps", [])
        if isinstance(step, dict)
    )
    if current_step not in {READY_STEP, ""}:
        return _block(
            "wrong_current_step",
            f"current tracker step is {current_step or '(missing)'}; expected {READY_STEP}",
            root=root,
            report=report,
            staged_paths=staged_paths,
        )
    if current_step == "" and not ready_checked:
        return _block(
            "missing_ready_step",
            f"{READY_STEP} is not present as a completed step",
            root=root,
            report=report,
            staged_paths=staged_paths,
        )

    status_items = _all_status_items(report)
    allowed_staged = set(_report_item_paths(report, "required")) | set(
        _report_item_paths(report, "candidate_contextual")
    )
    unexpected_staged = sorted(path for path in staged_paths if path not in allowed_staged)
    suspicious_paths = _report_item_paths(report, "suspicious")
    if suspicious_paths:
        return _block(
            "suspicious_paths",
            "git status contains paths outside report-accepted required/contextual buckets",
            root=root,
            report=report,
            paths=suspicious_paths,
            staged_paths=staged_paths,
            unexpected_staged_paths=unexpected_staged,
        )

    unstaged_paths = _paths_with_state(status_items, "unstaged")
    if unstaged_paths:
        return _block(
            "unstaged_tracked_paths",
            "tracked unstaged changes must be resolved before local closeout",
            root=root,
            report=report,
            paths=unstaged_paths,
            staged_paths=staged_paths,
            unexpected_staged_paths=unexpected_staged,
        )

    untracked_paths = _paths_with_state(status_items, "untracked")
    if untracked_paths:
        return _block(
            "untracked_paths",
            "untracked report-relevant paths must be staged, committed separately, or removed",
            root=root,
            report=report,
            paths=untracked_paths,
            staged_paths=staged_paths,
            unexpected_staged_paths=unexpected_staged,
        )

    if unexpected_staged:
        return _block(
            "suspicious_staged_paths",
            "staged paths are outside report-accepted required/contextual buckets",
            root=root,
            report=report,
            paths=unexpected_staged,
            staged_paths=staged_paths,
            unexpected_staged_paths=unexpected_staged,
        )

    range_info = report["range"]
    range_id = f"{range_info['base_short']}..{range_info['head_short']}"
    if current_step == "":
        if staged_paths:
            return _block(
                "already_closed_with_staged_paths",
                f"{READY_STEP} is already ticked but staged paths remain",
                root=root,
                report=report,
                paths=staged_paths,
                staged_paths=staged_paths,
            )
        commit_hash, head_error = _head_commit(root)
        if head_error:
            return _block("git_head_readback_failed", head_error, root=root, report=report)
        return {
            "status": "ok",
            "action": "already_closed",
            "blocker": None,
            "range": range_info["range"],
            "range_id": range_id,
            "tracker_current_step": current_step,
            "commit": commit_hash,
            "message": "N/A (why=already closed)",
            "tracker_tick": "already_ticked",
            "pending_owner_gate": "git push",
            "terminal_state": TERMINAL_PROOF_STATE,
            "closeout_receipt_path": (report.get("ready_to_push_terminal_proof") or {}).get("path", ""),
            **_not_blocked_staging_readback(),
        }

    risk_packet_preexisting_errors, risk_packet_preexisting_path = _risk_packet_preexisting_errors(
        root=root,
        report=report,
    )
    if risk_packet_preexisting_errors:
        expected_path = risk_packet_preexisting_path or (
            f"docs/reviews/*_risk_packet_range_{range_info['base_short']}_{range_info['head_short']}.md"
        )
        return _block(
            _risk_packet_block_code(risk_packet_preexisting_errors),
            _risk_packet_error_detail(
                report=report,
                expected_path=expected_path,
                errors=risk_packet_preexisting_errors,
            ),
            root=root,
            report=report,
            paths=[expected_path],
            errors=[error.as_dict() for error in risk_packet_preexisting_errors],
            staged_paths=staged_paths,
        )

    pre_closeout_staged_paths = list(staged_paths)
    try:
        # Keep the report's original generation and lexical/physical tracker
        # selection. A newly coherent generation cannot replace this binding.
        merge_gate_policy.validate_tracker_for_root(
            root if merge_binding is None else binding_root,
            effective_tracker, expected_binding=merge_binding,
        )
    except (merge_gate_policy.MergeGatePolicyError, merge_gate_policy.authority.ContractAuthorityError) as exc:
        return _block(
            "merge_policy_revalidation_failed",
            f"{getattr(exc, 'reason_code', 'merge_policy_invalid')}: {exc}",
            root=root,
            report=report,
            staged_paths=staged_paths,
        )
    try:
        tracker_text_before_tick = effective_tracker.read_text(encoding="utf-8")
        tracker_tick = _tick_ready_step(effective_tracker)
    except OSError as exc:
        return _block("tracker_tick_failed", str(exc), root=root, report=report)
    except ValueError as exc:
        return _block("tracker_tick_failed", str(exc), root=root, report=report)

    terminal_proof = report.get("ready_to_push_terminal_proof") or {}
    closeout_receipt_path = str(terminal_proof.get("path") or "")
    generated_closeout_receipt = terminal_proof.get("state") != TERMINAL_PROOF_STATE
    if generated_closeout_receipt:
        closeout_receipt_path, receipt_error = _write_and_stage_closeout_receipt(
            root=root,
            tracker_path=effective_tracker,
            report=report,
            staged_paths=staged_paths,
            tracker_tick_result=tracker_tick,
        )
        if receipt_error:
            rollback_error = _restore_tracker_text(
                effective_tracker,
                tracker_text_before_tick,
                tick_result=tracker_tick,
            )
            return _block(
                "git_add_closeout_receipt_failed",
                _with_tracker_rollback_detail(receipt_error, rollback_error),
                root=root,
                report=report,
                paths=[closeout_receipt_path],
                staged_paths=staged_paths,
            )
        staged_paths, staged_error = _git_lines(root, "diff", "--cached", "--name-only")
        if staged_error:
            rollback_error = _restore_tracker_text(
                effective_tracker,
                tracker_text_before_tick,
                tick_result=tracker_tick,
            )
            unstage_error = _unstage_generated_receipt(root, closeout_receipt_path)
            return _block(
                "git_cached_diff_failed",
                _with_post_staging_rollback_detail(
                    staged_error,
                    tracker_rollback_error=rollback_error,
                    receipt_unstage_error=unstage_error,
                ),
                root=root,
                report=report,
                staged_paths=pre_closeout_staged_paths,
            )

    risk_packet_path, risk_packet_errors, risk_packet_state, risk_packet_written = (
        _write_stage_validate_risk_packet(
            root=root,
            report=report,
            closeout_receipt_path=closeout_receipt_path,
        )
    )
    if risk_packet_errors:
        rollback_error = _restore_tracker_text(
            effective_tracker,
            tracker_text_before_tick,
            tick_result=tracker_tick,
        )
        generated_paths = [risk_packet_path]
        if generated_closeout_receipt:
            generated_paths.append(closeout_receipt_path)
        unstage_error = _unstage_generated_paths(root, generated_paths)
        unlink_paths = [risk_packet_path] if risk_packet_written else []
        if generated_closeout_receipt:
            unlink_paths.append(closeout_receipt_path)
        unlink_error = _unlink_generated_paths(root, unlink_paths)
        return _block(
            _risk_packet_block_code(risk_packet_errors),
            _with_generated_rollback_detail(
                _risk_packet_error_detail(
                    report=report,
                    expected_path=risk_packet_path,
                    errors=risk_packet_errors,
                ),
                tracker_rollback_error=rollback_error,
                generated_unstage_error=unstage_error,
                generated_unlink_error=unlink_error,
            ),
            root=root,
            report=report,
            paths=[risk_packet_path],
            errors=[error.as_dict() for error in risk_packet_errors],
            staged_paths=pre_closeout_staged_paths,
        )

    staged_paths, staged_error = _git_lines(root, "diff", "--cached", "--name-only")
    if staged_error:
        rollback_error = _restore_tracker_text(
            effective_tracker,
            tracker_text_before_tick,
            tick_result=tracker_tick,
        )
        generated_paths = [risk_packet_path]
        if generated_closeout_receipt:
            generated_paths.append(closeout_receipt_path)
        unstage_error = _unstage_generated_paths(root, generated_paths)
        unlink_error = _unlink_generated_paths(root, generated_paths)
        return _block(
            "git_cached_diff_failed",
            _with_generated_rollback_detail(
                staged_error,
                tracker_rollback_error=rollback_error,
                generated_unstage_error=unstage_error,
                generated_unlink_error=unlink_error,
            ),
            root=root,
            report=report,
            staged_paths=pre_closeout_staged_paths,
        )

    if staged_paths:
        subject = _commit_subject(report)
        rc, stdout, stderr = _run_git(root, "commit", "-m", subject)
        if rc != 0:
            rollback_error = _restore_tracker_text(
                effective_tracker,
                tracker_text_before_tick,
                tick_result=tracker_tick,
            )
            generated_paths = [risk_packet_path]
            if generated_closeout_receipt:
                generated_paths.append(closeout_receipt_path)
            unstage_error = _unstage_generated_paths(root, generated_paths)
            unlink_error = _unlink_generated_paths(root, generated_paths)
            return _block(
                "git_commit_failed",
                _with_generated_rollback_detail(
                    stderr.strip() or stdout.strip() or "git commit failed",
                    tracker_rollback_error=rollback_error,
                    generated_unstage_error=unstage_error,
                    generated_unlink_error=unlink_error,
                ),
                root=root,
                report=report,
                paths=staged_paths,
                staged_paths=staged_paths,
            )
        commit_hash, head_error = _head_commit(root)
        if head_error:
            return _block("git_head_readback_failed", head_error, root=root, report=report)
        action = "committed"
        message = subject
    else:
        commit_hash, head_error = _head_commit(root)
        if head_error:
            return _block("git_head_readback_failed", head_error, root=root, report=report)
        action = "already_committed"
        message = "N/A (why=no staged paths; report green and tracker ready)"

    return {
        "status": "ok",
        "action": action,
        "blocker": None,
        "range": range_info["range"],
        "range_id": range_id,
        "tracker_current_step": current_step,
        "commit": commit_hash,
        "message": message,
        "tracker_tick": tracker_tick,
        "pending_owner_gate": "git push",
        "terminal_state": TERMINAL_PROOF_STATE,
        "closeout_receipt_path": closeout_receipt_path,
        "risk_packet_path": risk_packet_path,
        "risk_packet_state": risk_packet_state or "ok",
        "staged_paths": staged_paths,
        **_not_blocked_staging_readback(),
    }


def render_plain(result: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"post_merge_ready_to_push_closeout: {result['status']}")
    lines.append(f"  action: {result['action']}")
    lines.append(f"  range: {result.get('range') or '(missing)'}")
    lines.append(f"  range_id: {result.get('range_id') or '(missing)'}")
    for key in (
        "why_blocked",
        "staging_command",
        "pathspec_file",
        "pathspec_file_format",
        "pathspec_paths_count",
        "pending_owner_gate",
    ):
        if key in result:
            lines.append(f"  {key}: {result.get(key)}")
    if result["status"] == "ok":
        lines.append(f"  commit: {result.get('commit') or '(none)'}")
        lines.append(f"  message: {result.get('message') or '(none)'}")
        lines.append(f"  tracker_tick: {result.get('tracker_tick') or '(none)'}")
        lines.append(f"  terminal_state: {result.get('terminal_state') or '(none)'}")
        lines.append(f"  closeout_receipt_path: {result.get('closeout_receipt_path') or '(none)'}")
        lines.append(f"  risk_packet_path: {result.get('risk_packet_path') or '(none)'}")
        lines.append(f"  risk_packet_state: {result.get('risk_packet_state') or '(none)'}")
    else:
        blocker = result.get("blocker") or {}
        lines.append(f"  blocker: {blocker.get('code') or '(missing)'}")
        lines.append(f"  detail: {blocker.get('detail') or '(missing)'}")
        paths = blocker.get("paths") or []
        if paths:
            lines.append("  paths:")
            for path in paths:
                lines.append(f"    - {path}")
        errors = blocker.get("report_errors") or []
        if errors:
            lines.append("  report_errors:")
            for error in errors:
                lines.append(f"    - {error.get('code')}: {error.get('detail')}")
        diagnostics = result.get("staging_diagnostics") or {}
        if diagnostics:
            lines.append("  staging_diagnostics:")
            lines.append(f"    primary_blocker_code: {diagnostics.get('primary_blocker_code') or '(missing)'}")
            lines.append(f"    recommended_action: {diagnostics.get('recommended_action') or '(missing)'}")
            for key in (
                "required_paths",
                "contextual_paths",
                "staged_accepted_paths",
                "unstaged_tracked_paths",
                "untracked_accepted_paths",
                "suspicious_paths",
                "unexpected_staged_paths",
            ):
                lines.append(f"    {key}:")
                bucket_paths = diagnostics.get(key) or []
                if not bucket_paths:
                    lines.append("      - (none)")
                    continue
                for path in bucket_paths:
                    lines.append(f"      - {path}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail-closed local commit/tick helper for merge-tracker step:ready_to_push"
    )
    parser.add_argument("--root", default=".", help="Repository root (default: current directory)")
    parser.add_argument("--tracker", default=None, help="Tracker path (default: <root>/.planveyor.merge_tracker.md)")
    parser.add_argument(
        "--content-profile-id",
        default="default",
        choices=("default", "planveyor", "target-local"),
        help="Resolved public content profile for the generic mirror policy.",
    )
    parser.add_argument("--format", choices=("plain", "json"), default="plain", help="Output format")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    try:
        mirror_policy = load_shared_docs_mirror_policy(content_profile_id=args.content_profile_id)
        result = close_ready_to_push(
            Path(args.root),
            Path(args.tracker) if args.tracker else None,
            mirror_policy=mirror_policy,
        )
    except (
        merge_gate_policy.MergeGatePolicyError,
        merge_gate_policy.authority.ContractAuthorityError,
        MirrorPolicyError,
    ) as exc:
        print(f"post_merge_ready_to_push_closeout: {getattr(exc, 'reason_code', 'merge_policy_invalid')}: {exc}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print(render_plain(result))
    return 0 if result["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())

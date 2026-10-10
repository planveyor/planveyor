#!/usr/bin/env python3
"""Read-only queue-level finalizer report.

The report is a derived Owner readback. It intentionally does not advance,
repair, stage, commit, or push queue state.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import plan_lint
import plan_queue


SCHEMA_VERSION = "queue_finalizer_report.v1"
STATE_FILE_NAME = ".planveyor.planqueue.json"
LOG_FILE_NAME = ".planveyor.planqueue.log"
SKIPPED_MANAGER_MODE_STATE = "skipped_manager_mode"
TERMINAL_QUEUE_STATES = {"done", "superseded", "closed_non_executable", SKIPPED_MANAGER_MODE_STATE}
TERMINAL_PLAN_STATUSES = {"done", "superseded"}
NON_EXECUTABLE_PLAN_STATUSES = {"ready for planner"}
POLICY_DEFERRED_PLANS = {
    "plan_current_state_terminal_receipt": "current_state_authority",
    "pi_urgency_lanes_followups_split": "process_improvement_urgency_lanes",
}
PROMOTED_ROUTE_HEADING = "Promoted route artifact"
SUPPORTING_REVIEW_LABEL_RE = re.compile(
    r"^(?:supporting|historical|history|source|context|rerun)\b",
    re.IGNORECASE,
)


def _rel(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _repo_path(root: Path, raw_path: str) -> tuple[Path, str]:
    path = Path(raw_path.split("#", 1)[0])
    fs_path = path if path.is_absolute() else root / path
    return fs_path, _rel(root, fs_path)


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").lower().split())


def _add_error(errors: list[dict[str, Any]], code: str, truth_host: str, detail: str, **extra: Any) -> None:
    error = {"code": code, "truth_host": truth_host, "detail": detail}
    error.update({key: value for key, value in extra.items() if value is not None})
    errors.append(error)


def _status_from_text(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("##"):
            break
        if stripped.startswith(">"):
            stripped = stripped[1:].strip()
        if len(stripped) > 1 and stripped[0] in {"-", "*", "+"} and stripped[1].isspace():
            stripped = stripped[1:].strip()
        if stripped.startswith("**Status:**") and "|" not in stripped:
            value = stripped[len("**Status:**") :].strip()
            return value or None
    return None


def _section_text(markdown: str, heading: str) -> str:
    wanted = _normalize(heading)
    in_section = False
    lines: list[str] = []
    for line in markdown.splitlines():
        match = re.match(r"^\s*##\s+(.+?)\s*$", line)
        if match:
            current = _normalize(match.group(1).strip())
            if in_section:
                break
            in_section = current == wanted
            continue
        if in_section:
            lines.append(line)
    return "\n".join(lines).strip()


def _is_review_markdown_path(root: Path, raw_path: str, *, allow_legacy_root: bool) -> bool:
    """Return whether a shared-eligible review path is a usable local truth host."""
    if not plan_lint.is_review_artifact_path_eligible(
        raw_path,
        allow_legacy_root=allow_legacy_root,
    ):
        return False
    path, _ = _repo_path(root, raw_path)
    try:
        return not path.exists() or path.is_file()
    except OSError:
        # An inaccessible Markdown path remains eligible so the mandatory reader
        # can emit structured unreadable truth-host evidence.
        return True


def _legacy_review_row_is_supporting(line: str) -> bool:
    label = line.split(":", 1)[0]
    label = re.sub(r"^\s*(?:[-*+]\s*)?", "", label)
    return bool(SUPPORTING_REVIEW_LABEL_RE.match(_normalize(label)))


def _legacy_review_artifact_refs(root: Path, plan_text: str) -> list[str]:
    """Find bounded compatibility refs only when no canonical carrier exists."""
    section = plan_lint.slice_h2_section(
        plan_text.splitlines(),
        plan_lint.REVIEW_ARTIFACTS_HEADING_RE,
    )
    if not section:
        return []

    _, body = section
    refs: list[str] = []
    seen: set[str] = set()
    for line in body:
        if _legacy_review_row_is_supporting(line):
            continue
        for raw_path in plan_lint.extract_review_artifact_path_tokens(line):
            if raw_path in seen or not _is_review_markdown_path(
                root,
                raw_path,
                allow_legacy_root=True,
            ):
                continue
            seen.add(raw_path)
            refs.append(raw_path)
    return refs


def _review_artifact_refs(root: Path, plan_text: str) -> tuple[list[str], list[str]]:
    """Return (eligible_refs, raw_canonical_refs) with canonical precedence."""
    raw_canonical_rows = plan_lint.extract_live_review_artifact_raw_rows(plan_text.splitlines())
    if raw_canonical_rows:
        raw_canonical_refs = list(
            dict.fromkeys(path for _, refs in raw_canonical_rows for path in refs)
        )
        if any(
            not refs
            or any(
                not _is_review_markdown_path(root, path, allow_legacy_root=False)
                for path in refs
            )
            for _, refs in raw_canonical_rows
        ):
            return [], raw_canonical_refs
        return (
            list(
                dict.fromkeys(
                    path
                    for path in raw_canonical_refs
                    if _is_review_markdown_path(root, path, allow_legacy_root=False)
                )
            ),
            raw_canonical_refs,
        )
    return _legacy_review_artifact_refs(root, plan_text), []


def _read_mandatory_truth_host(
    path: Path,
    truth_host: str,
    errors: list[dict[str, Any]],
    *,
    item_plan: str,
) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        _add_error(
            errors,
            "unreadable_truth_host",
            truth_host,
            "Mandatory truth host cannot be read as UTF-8.",
            item_plan=item_plan,
        )
        return None


def _review_status(value: str | None) -> str:
    normalized = _normalize(value)
    if not normalized:
        return "unknown"
    if "\u274c" in str(value):
        return "red"
    if "\u2705" in str(value) or "ok" in normalized or "no blockers" in normalized:
        return "ok"
    if "blocker" in normalized or "blocked" in normalized or "fail" in normalized:
        return "red"
    return "unknown"


def _parse_table_value(section: str, key: str) -> str | None:
    key_norm = _normalize(key)
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 2:
            continue
        if _normalize(cells[0]) == key_norm:
            value = cells[1].strip().strip("`")
            return value or None
    return None


def _promoted_route(plan_text: str, plan_rel: str) -> dict[str, str] | None:
    section = _section_text(plan_text, PROMOTED_ROUTE_HEADING)
    if not section or section.startswith("N/A"):
        return None
    accepted_route = _parse_table_value(section, "accepted_route") or _parse_table_value(section, "Accepted route")
    promoted_ref = (
        _parse_table_value(section, "promoted_artifact_ref")
        or _parse_table_value(section, "Promoted artifact ref")
        or _parse_table_value(section, "Promoted artifact")
    )
    if not accepted_route and not promoted_ref:
        return None
    return {
        "source": f"{plan_rel}#Promoted-route-artifact",
        "accepted_route": accepted_route or "unknown",
        "promoted_artifact_ref": promoted_ref or "unknown",
    }


def _plan_cost_label(plan_rel: str, plan_text: str, queue_item: dict[str, Any]) -> str:
    runtime_class = _normalize(queue_item.get("runtime_class"))
    if runtime_class in {"parked_umbrella", "routing_only_baseline", "verified_reference_child"}:
        return "non_executable_reference"

    meta_wave_match = re.search(r'"wave_family"\s*:\s*"([^"]+)"', plan_text)
    wave_family = _normalize(meta_wave_match.group(1) if meta_wave_match else "")
    haystack = _normalize(f"{plan_rel}\n{plan_text}")

    if wave_family == "analysis_wave" or "analysis_wave" in haystack:
        return "planning_contour"
    if "docs_closeout" in haystack or "closeout" in plan_rel:
        return "docs_closeout_heavy"
    if "reviewer_code" in haystack or "code_reviews/" in haystack or "dual_review" in haystack:
        return "dual_review_required"
    return "simple"


def _policy_bucket_for_plan(plan_rel: str) -> str | None:
    for marker, bucket in POLICY_DEFERRED_PLANS.items():
        if marker in plan_rel:
            return bucket
    return None


def _process_improvements(root: Path) -> dict[str, Any]:
    candidates = [
        root / "docs/process_improvements/index.md",
        root / "docs/process_improvements/deferred.md",
        root / "docs/process_improvements/promotion_surface.md",
    ]
    truth_hosts = [_rel(root, path) for path in candidates if path.exists()]
    rows_by_urgency: dict[str, int] = {}
    for path in candidates:
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return {
                "state": "unavailable_or_deferred",
                "truth_hosts": truth_hosts,
                "rows_by_urgency": {},
            }
        for urgency in re.findall(r"\b(P[0-3])\b", text):
            rows_by_urgency[urgency] = rows_by_urgency.get(urgency, 0) + 1
    return {
        "state": "readback_available" if truth_hosts else "unavailable_or_deferred",
        "truth_hosts": truth_hosts,
        "rows_by_urgency": rows_by_urgency,
    }


def _owner_actions(root: Path, state_truth_host: str) -> list[dict[str, str]]:
    digest = root / "docs/plans/260617_2145_process_merge_range_verdict_digest.md"
    truth_host = f"{_rel(root, digest)}#Evidence" if digest.exists() else state_truth_host
    return [
        {
            "id": "git_push",
            "action": "git push",
            "state": "pending_owner_gate",
            "truth_host": truth_host,
        }
    ]


def _build_item(
    *,
    root: Path,
    raw_item: dict[str, Any],
    errors: list[dict[str, Any]],
    accepted_routes: list[dict[str, Any]],
    policy_buckets: list[dict[str, Any]],
    log_entries: list[dict[str, Any]],
) -> dict[str, Any]:
    plan_raw = str(raw_item.get("plan") or "")
    item: dict[str, Any] = {
        "order": raw_item.get("order"),
        "plan": plan_raw,
        "queue_state": raw_item.get("state"),
        "completed_at": raw_item.get("completed_at"),
        "final_status": raw_item.get("final_status"),
        "closeout_kind": raw_item.get("closeout_kind"),
        "closeout_reason": raw_item.get("closeout_reason"),
        "skip_phase": raw_item.get("skip_phase"),
        "manager_mode_skip_id": raw_item.get("manager_mode_skip_id"),
        "required_manager_mode": raw_item.get("required_manager_mode"),
        "actual_manager_mode": raw_item.get("actual_manager_mode"),
        "manager_mode_state": raw_item.get("manager_mode_state"),
        "manager_mode_reason": raw_item.get("manager_mode_reason"),
        "truth_hosts": [],
        "review_artifacts": [],
        "commits": {"state": "unavailable_or_deferred", "truth_host": LOG_FILE_NAME, "values": []},
    }
    if not plan_raw:
        _add_error(errors, "missing_truth_host", STATE_FILE_NAME, "Queue item has no plan path.")
        return item

    plan_path, plan_rel = _repo_path(root, plan_raw)
    item["plan"] = plan_rel
    item["truth_hosts"].append(f"{plan_rel}#Status")

    queue_state = _normalize(raw_item.get("state"))
    if queue_state not in TERMINAL_QUEUE_STATES:
        _add_error(
            errors,
            "non_terminal_queue_item",
            f"{STATE_FILE_NAME}:{plan_rel}",
            f"Queue item is not terminal: state={raw_item.get('state')!r}.",
            item_plan=plan_rel,
        )

    if not plan_path.exists():
        _add_error(errors, "missing_truth_host", plan_rel, "Child plan truth host is missing.", item_plan=plan_rel)
        return item

    plan_text = _read_mandatory_truth_host(
        plan_path,
        plan_rel,
        errors,
        item_plan=plan_rel,
    )
    if plan_text is None:
        item["plan_status"] = "unreadable"
        return item
    plan_status = _status_from_text(plan_text)
    item["plan_status"] = plan_status or "unknown"
    item["cost_profile"] = _plan_cost_label(plan_rel, plan_text, raw_item)

    plan_status_norm = _normalize(plan_status)
    if queue_state == SKIPPED_MANAGER_MODE_STATE:
        completed_at = raw_item.get("completed_at")
        expected_skip = {
            "plan": plan_rel,
            "order": raw_item.get("order"),
            "skip_phase": "activation",
            "manager_mode_skip_id": raw_item.get("manager_mode_skip_id"),
            "required_manager_mode": raw_item.get("required_manager_mode"),
            "actual_manager_mode": raw_item.get("actual_manager_mode"),
            "manager_mode_state": "mismatch",
            "manager_mode_reason": "required_mode_mismatch",
        }
        valid_modes = set(plan_queue.plan_status_oracle.ACTUAL_MANAGER_MODES)
        skip_valid = (
            raw_item.get("skip_phase") == expected_skip["skip_phase"]
            and raw_item.get("closeout_kind") == "manager_mode_mismatch"
            and raw_item.get("closeout_reason") == "required_mode_mismatch"
            and raw_item.get("manager_mode_state") == expected_skip["manager_mode_state"]
            and raw_item.get("manager_mode_reason") == expected_skip["manager_mode_reason"]
            and isinstance(raw_item.get("manager_mode_skip_id"), str)
            and len(str(raw_item.get("manager_mode_skip_id"))) == 32
            and raw_item.get("required_manager_mode") in valid_modes
            and raw_item.get("actual_manager_mode") in valid_modes
            and raw_item.get("required_manager_mode") != raw_item.get("actual_manager_mode")
            and isinstance(completed_at, str)
            and bool(completed_at.strip())
        )
        current_lifecycle_logs = [
            entry
            for entry in log_entries
            if entry.get("event") == "skip_manager_mode"
            and entry.get("plan") == plan_rel
            and str(entry.get("order")) == str(raw_item.get("order"))
            and entry.get("manager_mode_skip_id") == raw_item.get("manager_mode_skip_id")
        ]
        matching_logs = [
            entry
            for entry in current_lifecycle_logs
            if entry.get("at") == completed_at
            and all(
                str(entry.get(key)) == str(value)
                for key, value in expected_skip.items()
                if key not in {"plan", "order"}
            )
        ]
        if (
            not skip_valid
            or len(current_lifecycle_logs) != 1
            or len(matching_logs) != 1
        ):
            _add_error(
                errors,
                "inconsistent_manager_mode_skip",
                f"{STATE_FILE_NAME}:{plan_rel}",
                "Persisted Manager-mode skip fields do not have exactly one matching "
                "current lifecycle state/log identity.",
                item_plan=plan_rel,
            )
        item["truth_hosts"].append(
            f"{LOG_FILE_NAME}:skip_manager_mode:{raw_item.get('manager_mode_skip_id')}"
        )
        return item

    allowed_plan_statuses = set(TERMINAL_PLAN_STATUSES)
    if queue_state == "closed_non_executable":
        allowed_plan_statuses.update(NON_EXECUTABLE_PLAN_STATUSES)
    if queue_state in TERMINAL_QUEUE_STATES and plan_status_norm not in allowed_plan_statuses:
        _add_error(
            errors,
            "inconsistent_truth_host",
            f"{plan_rel}#Status",
            f"Queue item is terminal but plan status is not terminal: {plan_status!r}.",
            item_plan=plan_rel,
        )

    review_refs, raw_canonical_refs = _review_artifact_refs(root, plan_text)
    candidate_refs = raw_canonical_refs or review_refs
    if queue_state in {"done", "superseded"} and (
        not candidate_refs or (raw_canonical_refs and not review_refs)
    ):
        _add_error(
            errors,
            "missing_truth_host",
            f"{plan_rel}#Review-artifacts",
            "Semantic terminal queue item has no eligible review/receipt truth host.",
            item_plan=plan_rel,
        )
    if len(candidate_refs) > 1:
        _add_error(
            errors,
            "ambiguous_truth_host",
            f"{plan_rel}#Review-artifacts",
            "Multiple candidate review/receipt truth hosts for one item.",
            item_plan=plan_rel,
            candidates=candidate_refs,
        )
    for raw_ref in review_refs:
        review_path, review_rel = _repo_path(root, raw_ref)
        review = {"path": review_rel, "truth_host": f"{review_rel}#Status", "status": "missing"}
        item["review_artifacts"].append(review)
        item["truth_hosts"].append(f"{review_rel}#Status")
        if not review_path.exists():
            _add_error(errors, "missing_truth_host", review_rel, "Review/receipt truth host is missing.", item_plan=plan_rel)
            continue
        review_text = _read_mandatory_truth_host(
            review_path,
            review_rel,
            errors,
            item_plan=plan_rel,
        )
        if review_text is None:
            review["status"] = "unreadable"
            review["verdict"] = "unreadable"
            continue
        status = _status_from_text(review_text)
        review["status"] = status or "unknown"
        verdict = _review_status(status)
        review["verdict"] = verdict
        if verdict == "red":
            _add_error(
                errors,
                "red_truth_host",
                f"{review_rel}#Status",
                f"Review/receipt truth host is red: {status!r}.",
                item_plan=plan_rel,
            )
        elif verdict == "unknown":
            _add_error(
                errors,
                "inconsistent_truth_host",
                f"{review_rel}#Status",
                f"Review/receipt truth host has unknown status: {status!r}.",
                item_plan=plan_rel,
            )

    route = _promoted_route(plan_text, plan_rel)
    if route:
        promoted_ref = route["promoted_artifact_ref"]
        seed_path, seed_rel = _repo_path(root, promoted_ref)
        route["seed_truth_host"] = f"{seed_rel}#Status"
        if not seed_path.exists():
            route["state"] = "missing_seed_truth_host"
            _add_error(errors, "missing_truth_host", seed_rel, "Promoted seed truth host is missing.", item_plan=plan_rel)
        else:
            seed_text = _read_mandatory_truth_host(
                seed_path,
                seed_rel,
                errors,
                item_plan=plan_rel,
            )
            if seed_text is None:
                route["seed_status"] = "unreadable"
                route["state"] = "unreadable_seed_truth_host"
            else:
                seed_status = _status_from_text(seed_text)
                route["seed_status"] = seed_status or "unknown"
                route["state"] = (
                    "implemented"
                    if _normalize(seed_status) in TERMINAL_PLAN_STATUSES
                    else "accepted_seed_pending_implementation"
                )
        accepted_routes.append(route)
        policy_buckets.append(
            {
                "bucket": "dual_review_censor_policy",
                "state": route["state"],
                "source_ref": route["source"],
                "promoted_artifact_ref": promoted_ref,
            }
        )

    deferred_bucket = _policy_bucket_for_plan(plan_rel)
    if deferred_bucket:
        policy_buckets.append(
            {
                "bucket": deferred_bucket,
                "state": "unavailable_or_deferred",
                "source_ref": plan_rel,
            }
        )

    return item


def build_report(
    repo_root: Path,
    *,
    state_path: Path | None = None,
    log_path: Path | None = None,
) -> dict[str, Any]:
    root = repo_root.resolve()
    queue_state_path = (state_path or root / STATE_FILE_NAME).resolve()
    queue_log_path = (log_path or root / LOG_FILE_NAME).resolve()
    state_truth_host = _rel(root, queue_state_path)
    log_truth_host = _rel(root, queue_log_path)
    errors: list[dict[str, Any]] = []
    accepted_routes: list[dict[str, Any]] = []
    policy_buckets: list[dict[str, Any]] = []

    queue_paths = plan_queue.QueuePaths(
        root=root,
        state_path=queue_state_path,
        log_path=queue_log_path,
    )
    recovery_state = "clean"
    recovery_reason = "canonical shared snapshot is clean"
    try:
        queue_snapshot = plan_queue.queue_state_history_snapshot(queue_paths)
    except plan_queue.QueueError as exc:
        recovery_state = "blocked"
        recovery_reason = str(exc)
        raw_recovery_items: list[object] = []
        try:
            raw_recovery_state = json.loads(queue_state_path.read_text(encoding="utf-8"))
            if isinstance(raw_recovery_state, dict) and isinstance(raw_recovery_state.get("items"), list):
                raw_recovery_items = raw_recovery_state["items"]
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            pass
        if any(
            isinstance(item, dict) and _normalize(item.get("state")) == SKIPPED_MANAGER_MODE_STATE
            for item in raw_recovery_items
        ):
            _add_error(
                errors,
                "inconsistent_manager_mode_skip",
                state_truth_host,
                recovery_reason,
            )
        _add_error(
            errors,
            "queue_recovery_required",
            _rel(root, queue_paths.txn_path),
            recovery_reason,
            recovery=exc.payload,
        )
        state = None
        log_entries = []
    else:
        state = queue_snapshot["state"]
        log_entries = queue_snapshot["log_entries"]
        if state is None:
            _add_error(errors, "missing_truth_host", state_truth_host, "Queue state JSON is missing.")
        if not queue_log_path.exists():
            _add_error(errors, "missing_truth_host", log_truth_host, "Queue log is missing.")

    raw_items = state.get("items") if isinstance(state, dict) else []
    if state is not None and not isinstance(raw_items, list):
        _add_error(errors, "red_truth_host", state_truth_host, "Queue state `items` must be a list.")
        raw_items = []

    items: list[dict[str, Any]] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            _add_error(errors, "red_truth_host", state_truth_host, "Queue item must be an object.")
            continue
        items.append(
            _build_item(
                root=root,
                raw_item=raw_item,
                errors=errors,
                accepted_routes=accepted_routes,
                policy_buckets=policy_buckets,
                log_entries=log_entries,
            )
        )

    queue_complete = bool(raw_items) and all(_normalize(item.get("state")) in TERMINAL_QUEUE_STATES for item in raw_items)
    if state is not None and not queue_complete:
        _add_error(errors, "queue_not_complete", state_truth_host, "Queue does not have only terminal items.")

    cost_counts: dict[str, int] = {}
    for item in items:
        label = str(item.get("cost_profile") or "simple")
        cost_counts[label] = cost_counts.get(label, 0) + 1

    truth_hosts = [state_truth_host, log_truth_host]
    for item in items:
        truth_hosts.extend(str(host) for host in item.get("truth_hosts", []))
    truth_hosts.extend(host for route in accepted_routes for host in (route.get("source"), route.get("seed_truth_host")) if host)

    report = {
        "schema_version": SCHEMA_VERSION,
        "report_status": "blocked" if errors else "ok",
        "queue": {
            "state_path": state_truth_host,
            "log_path": log_truth_host,
            "source_plan": state.get("source_plan") if isinstance(state, dict) else None,
            "parent_plan": state.get("parent_plan") if isinstance(state, dict) else None,
            "mode": state.get("mode") if isinstance(state, dict) else None,
            "cursor": state.get("cursor") if isinstance(state, dict) else None,
            "item_count": len(raw_items),
            "finalized_count": sum(1 for item in raw_items if isinstance(item, dict) and _normalize(item.get("state")) in TERMINAL_QUEUE_STATES),
            "skipped_manager_mode_count": sum(
                1
                for item in raw_items
                if isinstance(item, dict) and _normalize(item.get("state")) == SKIPPED_MANAGER_MODE_STATE
            ),
            "queue_complete": queue_complete,
            "log_entries": len(log_entries),
            "recovery_state": recovery_state,
            "recovery_reason": recovery_reason,
        },
        "items": items,
        "cost_profile": {
            "state": "advisory_readback",
            "labels": ["simple", "dual_review_required", "docs_closeout_heavy", "non_executable_reference", "planning_contour"],
            "counts": cost_counts,
        },
        "blockers": {
            "state": "derived_from_truth_hosts",
            "truth_hosts": sorted({host for item in items for host in item.get("truth_hosts", [])}),
            "items": [
                {"code": error["code"], "truth_host": error["truth_host"], "detail": error["detail"]}
                for error in errors
                if error["code"]
                in {
                    "red_truth_host",
                    "inconsistent_truth_host",
                    "inconsistent_manager_mode_skip",
                    "non_terminal_queue_item",
                    "queue_not_complete",
                }
            ],
        },
        "process_improvements": _process_improvements(root),
        "docs_closeout": {
            "state": "derived_from_plan_evidence" if items else "unavailable_or_deferred",
            "truth_hosts": [f"{item['plan']}#Evidence" for item in items if item.get("plan")],
        },
        "accepted_routes": accepted_routes,
        "policy_buckets": policy_buckets,
        "owner_actions": _owner_actions(root, state_truth_host),
        "truth_hosts": sorted({host for host in truth_hosts if host}),
        "errors": errors,
    }
    return report


def render_plain(report: dict[str, Any]) -> str:
    lines = [
        f"schema_version: {report['schema_version']}",
        f"report_status: {report['report_status']}",
        f"queue_complete: {str(report['queue']['queue_complete']).lower()}",
        f"items: {report['queue']['item_count']}",
        f"skipped_manager_mode: {report['queue']['skipped_manager_mode_count']}",
        "",
        "Queue items:",
    ]
    for item in report.get("items", []):
        lines.append(
            "- {plan}: queue_state={queue_state}; plan_status={plan_status}; cost_profile={cost_profile}".format(
                plan=item.get("plan"),
                queue_state=item.get("queue_state"),
                plan_status=item.get("plan_status", "unknown"),
                cost_profile=item.get("cost_profile", "simple"),
            )
        )
        if item.get("queue_state") == SKIPPED_MANAGER_MODE_STATE:
            lines.append(
                "  manager_mode_skip:"
                f" required={item.get('required_manager_mode')}"
                f" actual={item.get('actual_manager_mode')}"
                f" reason={item.get('manager_mode_reason')}"
            )
    lines.append("")
    lines.append("Policy buckets:")
    for bucket in report.get("policy_buckets", []):
        lines.append(f"- {bucket.get('bucket')}: {bucket.get('state')} ({bucket.get('source_ref')})")
    if not report.get("policy_buckets"):
        lines.append("- none")
    lines.append("")
    lines.append("Owner actions:")
    for action in report.get("owner_actions", []):
        lines.append(f"- {action.get('action')}: {action.get('state')} ({action.get('truth_host')})")
    if report.get("errors"):
        lines.append("")
        lines.append("Errors:")
        for error in report["errors"]:
            lines.append(f"- {error['code']}: {error['truth_host']} - {error['detail']}")
    return "\n".join(lines)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a read-only queue-level finalizer report.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd(), help="Repository root to inspect.")
    parser.add_argument("--state-path", type=Path, help="Override queue state path.")
    parser.add_argument("--log-path", type=Path, help="Override queue log path.")
    parser.add_argument("--format", choices=("plain", "json"), default="plain", help="Output format.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(args.repo_root, state_path=args.state_path, log_path=args.log_path)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_plain(report))
    return 0 if report["report_status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())

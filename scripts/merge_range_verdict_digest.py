#!/usr/bin/env python3
"""Owner-facing read-only digest for the final merge-range verdict."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import merge_bundle_report  # noqa: E402
import range_review_risk_packet  # noqa: E402
from range_review_risk_packet_schema_contract import RANGE_REVIEW_RISK_PACKET_SCHEMA_VERSION
from shared_docs_mirror_drift import (  # noqa: E402
    GENERIC_MIRROR_POLICY,
    MirrorPolicy,
    MirrorPolicyError,
    load_shared_docs_mirror_policy,
)


SCHEMA_VERSION = "merge_range_verdict_digest.v1"
RISK_PACKET_SCHEMA_VERSION = RANGE_REVIEW_RISK_PACKET_SCHEMA_VERSION
READY_TO_PUSH_TERMINAL_STATE = "terminal_ready_to_push_proof"
PENDING_OWNER_GATE = "git push"

STATUS_RE = re.compile(r"^\*\*Status:\*\*\s*(?P<status>.+?)\s*$", re.MULTILINE)
JSON_BLOCK_RE = re.compile(r"```json\s*(?P<body>.*?)\s*```", re.DOTALL | re.IGNORECASE)

REQUIRED_TRUTH_HOSTS = (
    "review_artifact",
    "packetization_report",
    "post_merge_audit",
    "operational_receipt",
    "ready_to_push_closeout",
)


@dataclass(frozen=True)
class DigestError:
    code: str
    detail: str
    truth_host: str = "N/A"
    next_action: str = "rerun the owning merge-pipeline helper and re-read this digest"

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "detail": self.detail,
            "truth_host": self.truth_host,
            "next_action": self.next_action,
        }


def _repo_rel(path: Path | str | None, root: Path) -> str:
    if not path:
        return "N/A"
    path_obj = Path(str(path))
    try:
        if path_obj.is_absolute():
            return path_obj.resolve().relative_to(root.resolve()).as_posix()
        return path_obj.as_posix()
    except ValueError:
        return path_obj.as_posix()


def _resolve_repo_path(root: Path, value: str | None) -> Path | None:
    if not value or value.startswith("N/A"):
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    return root / path


def _status_text(text: str) -> str:
    match = STATUS_RE.search(text)
    if not match:
        return "N/A (why=missing status)"
    return match.group("status").strip()


def _is_superseded_status(status: str) -> bool:
    return "superseded" in status.casefold()


def _json_blocks(text: str) -> list[Any]:
    blocks: list[Any] = []
    for match in JSON_BLOCK_RE.finditer(text):
        try:
            blocks.append(json.loads(match.group("body")))
        except json.JSONDecodeError:
            continue
    return blocks


def _risk_payload_from_value(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    for key in ("risk_packet", "range_review_risk_packet"):
        nested = value.get(key)
        if isinstance(nested, dict):
            return nested
    if "schema_version" in value:
        return value
    return None


def _risk_payload_from_text(text: str) -> tuple[dict[str, Any] | None, str | None]:
    malformed_json_seen = False
    for match in JSON_BLOCK_RE.finditer(text):
        try:
            parsed = json.loads(match.group("body"))
        except json.JSONDecodeError:
            malformed_json_seen = True
            continue
        payload = _risk_payload_from_value(parsed)
        if payload is not None:
            return payload, None

    for parsed in _json_blocks(text):
        payload = _risk_payload_from_value(parsed)
        if payload is not None:
            return payload, None

    if malformed_json_seen:
        return None, "malformed_json"
    return None, "missing_schema_payload"


def _split_range(range_ref: str | None) -> tuple[str | None, str | None]:
    if not range_ref or ".." not in range_ref:
        return None, None
    base, head = range_ref.split("..", 1)
    base = base.strip()
    head = head.strip()
    return (base or None), (head or None)


def _report_range(report: dict[str, Any]) -> dict[str, str]:
    range_info = report.get("range")
    if not isinstance(range_info, dict):
        return {
            "base": "",
            "head": "",
            "range": "",
            "base_short": "",
            "head_short": "",
        }
    base = str(range_info.get("base") or "")
    head = str(range_info.get("head") or "")
    range_ref = str(range_info.get("range") or "")
    return {
        "base": base,
        "head": head,
        "range": range_ref,
        "base_short": str(range_info.get("base_short") or base[:7]),
        "head_short": str(range_info.get("head_short") or head[:7]),
    }


def _digest_errors_from_packet_readback(
    readback: range_review_risk_packet.RiskPacketReadback,
) -> list[DigestError]:
    return [
        DigestError(
            code=error.code,
            detail=error.detail,
            truth_host=readback.packet_path,
            next_action=error.next_action,
        )
        for error in readback.errors
    ]


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _risk_truth_hosts(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload:
        return {}
    return _as_dict(payload.get("truth_hosts"))


def _truth_host_state(hosts: dict[str, Any], key: str) -> dict[str, Any]:
    host = hosts.get(key)
    if isinstance(host, dict):
        return dict(host)
    return {
        "path": "N/A (why=missing truth host)",
        "status": "missing",
        "source": "range_review_risk_packet",
    }


def _review_status_is_blocking(status: Any) -> bool:
    normalized = str(status or "").casefold()
    return "❌" in normalized or "blocker" in normalized or "blocked" in normalized


def _truth_host_errors(root: Path, hosts: dict[str, Any]) -> list[DigestError]:
    errors: list[DigestError] = []
    for key in REQUIRED_TRUTH_HOSTS:
        host = _truth_host_state(hosts, key)
        path_value = str(host.get("path") or "")
        if not path_value or path_value.startswith("N/A"):
            errors.append(
                DigestError(
                    code="missing_truth_host",
                    detail=f"risk packet is missing required truth host {key}",
                    truth_host=key,
                    next_action="regenerate planveyor_review_risk_packet with exact truth-host paths",
                )
            )
            continue
        resolved = _resolve_repo_path(root, path_value)
        if resolved is None or not resolved.is_file():
            errors.append(
                DigestError(
                    code="missing_truth_host_path",
                    detail=f"truth host path for {key} does not exist: {path_value}",
                    truth_host=path_value,
                    next_action="materialize the missing artifact or regenerate the risk packet",
                )
            )
    return errors


def _artifact_by_kind(report: dict[str, Any], kind: str) -> dict[str, Any]:
    artifacts = _as_list(report.get("artifacts"))
    matches = [
        dict(artifact)
        for artifact in artifacts
        if isinstance(artifact, dict) and artifact.get("kind") == kind
    ]
    active = [artifact for artifact in matches if artifact.get("active_candidate")]
    if active:
        return active[0]
    if matches:
        return matches[0]
    return {}


def _artifact_state(
    report: dict[str, Any],
    kind: str,
    fallback_host: dict[str, Any] | None = None,
) -> dict[str, Any]:
    artifact = _artifact_by_kind(report, kind)
    fallback_host = fallback_host or {}
    path = artifact.get("path") or fallback_host.get("path") or "N/A (why=missing artifact)"
    return {
        "kind": kind,
        "path": path,
        "status": artifact.get("status") or fallback_host.get("status") or "missing",
        "status_final": artifact.get("status_final") if artifact else "N/A",
        "git_state": artifact.get("git_state") if artifact else "N/A",
        "required": bool(artifact.get("required", True)) if artifact else True,
        "source": "merge_bundle_report",
    }


def _active_packetization_report(
    report: dict[str, Any],
    hosts: dict[str, Any],
) -> dict[str, Any]:
    gate = _as_dict(report.get("packetization_gate"))
    host = _truth_host_state(hosts, "packetization_report")
    active = gate.get("active_packetization_report")
    path = active or host.get("path") or "N/A (why=missing active packetization report)"
    active_path = _meaningful_path(active)
    host_path = _meaningful_path(host.get("path"))
    return {
        "path": path,
        "gate_status": (
            (host.get("status") or "N/A")
            if active_path and active_path == host_path
            else "N/A"
        ),
        "blocking_rows_count": gate.get("blocking_rows_count", "N/A"),
        "draft_packets_created_count": gate.get("draft_packets_created_count", "N/A"),
        "source": "merge_bundle_report.packetization_gate",
    }


def _ready_to_push_state(report: dict[str, Any]) -> dict[str, Any]:
    proof = _as_dict(report.get("ready_to_push_terminal_proof"))
    return {
        "state": proof.get("state") or "missing",
        "path": proof.get("path") or "N/A (why=missing terminal proof)",
        "final_bundle_status": proof.get("final_bundle_status") or "missing",
        "pending_owner_gate": proof.get("pending_owner_gate") or PENDING_OWNER_GATE,
        "source": "merge_bundle_report.ready_to_push_terminal_proof",
    }


def _followups_state(report: dict[str, Any]) -> tuple[dict[str, Any], list[DigestError]]:
    reconciliation = _as_dict(report.get("followups_lane_reconciliation"))
    launch = _as_dict(report.get("followups_triage_launch_receipt"))
    index_rebuild = _as_dict(launch.get("index_rebuild"))
    state: dict[str, Any] = {
        "lane_status": "N/A",
        "owner_summary": reconciliation.get("owner_summary") or "N/A",
        "launch_receipt_status": "N/A",
        "source": "merge_bundle_report.followups_lane_reconciliation",
        "harvest_file_followups_result": reconciliation.get(
            "harvest_file_followups_result", "N/A"
        ),
        "harvest_file_followups_count": reconciliation.get(
            "harvest_file_followups_count", "N/A"
        ),
        "range_triage_mode": reconciliation.get("range_triage_mode", "N/A"),
        "range_append_new": reconciliation.get("range_append_new", "N/A"),
        "range_merge_source": reconciliation.get("range_merge_source", "N/A"),
        "range_possible_duplicate": reconciliation.get("range_possible_duplicate", "N/A"),
        "range_route_fallback": reconciliation.get("range_route_fallback", "N/A"),
        "range_unparsed_bullets": reconciliation.get("range_unparsed_bullets", "N/A"),
        "range_unresolved_append_new": reconciliation.get(
            "range_unresolved_append_new", "N/A"
        ),
        "range_unresolved_possible_duplicate": reconciliation.get(
            "range_unresolved_possible_duplicate", "N/A"
        ),
        "range_unresolved_route_fallback": reconciliation.get(
            "range_unresolved_route_fallback", "N/A"
        ),
        "range_unresolved_unparsed_bullets": reconciliation.get(
            "range_unresolved_unparsed_bullets", "N/A"
        ),
        "manual_decision_ref": reconciliation.get("manual_decision_ref", "N/A"),
        "already_tracked_ref": reconciliation.get("already_tracked_ref", "N/A"),
        "index_rebuild_status": index_rebuild.get("status", "N/A"),
        "index_readback_status": index_rebuild.get("readback_status", "N/A"),
        "index_path": index_rebuild.get("index_path", "N/A"),
        "unresolved_total": "N/A",
    }
    invalid_fields: list[tuple[str, str, str]] = []
    for key in (
        "owner_summary",
        "harvest_file_followups_result",
        "range_triage_mode",
        "manual_decision_ref",
        "already_tracked_ref",
    ):
        value = reconciliation.get(key)
        if not isinstance(value, str) or not value.strip():
            invalid_fields.append(
                (
                    f"followups_lane_reconciliation.{key}",
                    "non-empty string",
                    "reconciliation",
                )
            )
    for key in (
        "harvest_file_followups_count",
        "range_append_new",
        "range_merge_source",
        "range_possible_duplicate",
        "range_route_fallback",
        "range_unparsed_bullets",
    ):
        value = reconciliation.get(key)
        if type(value) is not int or value < 0:
            invalid_fields.append(
                (
                    f"followups_lane_reconciliation.{key}",
                    "non-negative integer",
                    "reconciliation",
                )
            )
    for key in (
        "range_unresolved_append_new",
        "range_unresolved_possible_duplicate",
        "range_unresolved_route_fallback",
        "range_unresolved_unparsed_bullets",
    ):
        value = reconciliation.get(key)
        if type(value) is not int or value < 0:
            invalid_fields.append(
                (
                    f"followups_lane_reconciliation.{key}",
                    "non-negative integer",
                    "reconciliation",
                )
            )
    for key in ("status", "readback_status", "index_path"):
        value = index_rebuild.get(key)
        if not isinstance(value, str) or not value.strip():
            invalid_fields.append(
                (
                    f"followups_triage_launch_receipt.index_rebuild.{key}",
                    "non-empty string",
                    "launch",
                )
            )

    errors: list[DigestError] = []
    for field, expected, source in invalid_fields:
        truth_host = (
            "merge_bundle_report.followups_lane_reconciliation"
            if source == "reconciliation"
            else "merge_bundle_report.followups_triage_launch_receipt"
        )
        errors.append(
            DigestError(
                code="invalid_followups_projection",
                detail=f"field={field}; expected={expected}",
                truth_host=truth_host,
                next_action="regenerate the merge-bundle followups reconciliation and launch receipt",
            )
        )
    if errors:
        return state, errors if report.get("status") == "ok" else []

    state["unresolved_total"] = sum(
        reconciliation[key]
        for key in (
            "range_unresolved_append_new",
            "range_unresolved_possible_duplicate",
            "range_unresolved_route_fallback",
            "range_unresolved_unparsed_bullets",
        )
    )
    if report.get("status") != "ok":
        return state, []
    state["lane_status"] = "reconciled"
    if index_rebuild["status"] == "ok" and index_rebuild["readback_status"] == "ok":
        state["launch_receipt_status"] = "ok"
    return state, errors


def _process_improvements_state(report: dict[str, Any]) -> dict[str, Any]:
    summary = _as_dict(report.get("process_improvements_open_summary"))
    counts = _as_dict(summary.get("counts_by_raw_status"))
    return {
        "lane_status": summary.get("lane_status") or summary.get("status") or "N/A",
        "open_count": counts.get("open", "N/A"),
        "source": "merge_bundle_report.process_improvements_open_summary",
    }


def _archive_snapshot_state(report: dict[str, Any]) -> dict[str, Any]:
    archive = _as_dict(report.get("archive_snapshot"))
    return {
        "status": archive.get("status") or "N/A",
        "readback_status": archive.get("readback_status") or "N/A",
        "manifest_path": archive.get("manifest_path") or "N/A",
        "artifact_path": archive.get("artifact_path")
        or archive.get("object_uri")
        or "N/A",
        "source": "merge_bundle_report.archive_snapshot",
    }


def _live_review_verdict(risk_payload: dict[str, Any] | None, hosts: dict[str, Any]) -> dict[str, Any]:
    live_blockers = _as_list((risk_payload or {}).get("live_blockers"))
    review_host = _truth_host_state(hosts, "review_artifact")
    if live_blockers or _review_status_is_blocking(review_host.get("status")):
        verdict = "blocked"
    else:
        verdict = "ok"
    return {
        "verdict": verdict,
        "live_blocker_count": len(live_blockers),
        "review_artifact": review_host.get("path") or "N/A",
        "review_status": review_host.get("status") or "N/A",
        "source": "range_review_risk_packet.truth_hosts.review_artifact",
    }


def _build_truth_hosts(
    root: Path,
    report: dict[str, Any],
    risk_packet_path: Path | None,
    risk_hosts: dict[str, Any],
) -> dict[str, Any]:
    tracker = _as_dict(report.get("tracker"))
    hosts: dict[str, Any] = {
        "merge_bundle_report": {
            "kind": "helper_readback",
            "source_command": "planveyor_merge_bundle_report",
            "status": report.get("status") or "missing",
        },
        "tracker": {
            "path": tracker.get("path") or "N/A",
            "current_step": tracker.get("current_step") or "N/A",
            "completed_steps": _as_list(tracker.get("completed_steps")),
            "source": "merge_bundle_report.tracker",
        },
        "risk_packet": {
            "path": _repo_rel(risk_packet_path, root) if risk_packet_path else "N/A",
            "schema_version": RISK_PACKET_SCHEMA_VERSION,
            "source": "range_review_risk_packet",
        },
    }
    for key in REQUIRED_TRUTH_HOSTS:
        hosts[key] = _truth_host_state(risk_hosts, key)
    return hosts


def _meaningful_path(value: Any) -> str:
    text = str(value or "").strip()
    if not text or text.startswith("N/A"):
        return ""
    return text


def _status_token(value: Any) -> str:
    text = str(value or "").replace("✅", "").strip().casefold()
    return " ".join(text.split())


def _digest_freshness_error(
    *,
    source: str,
    target: str,
    field: str,
    expected: Any,
    actual: Any,
) -> DigestError:
    return DigestError(
        code="stale_digest_readback",
        detail=(
            f"field={field}; source={source}; target={target}; "
            f"expected={expected or 'missing'}; actual={actual or 'missing'}"
        ),
        truth_host=target,
        next_action="regenerate the stale terminal/risk-packet readback from current truth hosts",
    )


def _validate_digest_truth_host_freshness(
    report: dict[str, Any],
    risk_hosts: dict[str, Any],
) -> list[DigestError]:
    errors: list[DigestError] = []

    gate = _as_dict(report.get("packetization_gate"))
    active_packetization = _meaningful_path(gate.get("active_packetization_report"))
    packetization_host = _truth_host_state(risk_hosts, "packetization_report")
    packetization_host_path = _meaningful_path(packetization_host.get("path"))
    if active_packetization and packetization_host_path and packetization_host_path != active_packetization:
        errors.append(
            _digest_freshness_error(
                source="merge_bundle_report.packetization_gate",
                target="range_review_risk_packet.truth_hosts.packetization_report",
                field="active_packetization_report.path",
                expected=active_packetization,
                actual=packetization_host_path,
            )
        )

    closeout_state = _ready_to_push_state(report)
    closeout_path = _meaningful_path(closeout_state.get("path"))
    closeout_host = _truth_host_state(risk_hosts, "ready_to_push_closeout")
    closeout_host_path = _meaningful_path(closeout_host.get("path"))
    if closeout_path and closeout_host_path and closeout_host_path != closeout_path:
        errors.append(
            _digest_freshness_error(
                source="merge_bundle_report.ready_to_push_terminal_proof",
                target="range_review_risk_packet.truth_hosts.ready_to_push_closeout",
                field="ready_to_push_state.path",
                expected=closeout_path,
                actual=closeout_host_path,
            )
        )

    closeout_artifact = _artifact_by_kind(report, "ready_to_push_closeout_receipt")
    artifact_status = _status_token(closeout_artifact.get("status"))
    host_status = _status_token(closeout_host.get("status"))
    if artifact_status and host_status and artifact_status != host_status:
        errors.append(
            _digest_freshness_error(
                source="merge_bundle_report.artifacts.ready_to_push_closeout_receipt",
                target="range_review_risk_packet.truth_hosts.ready_to_push_closeout",
                field="ready_to_push_state.status",
                expected=closeout_artifact.get("status"),
                actual=closeout_host.get("status"),
            )
        )

    return errors


def _validate_ready_to_push(report: dict[str, Any]) -> list[DigestError]:
    state = _ready_to_push_state(report)
    errors: list[DigestError] = []
    if state["state"] != READY_TO_PUSH_TERMINAL_STATE:
        errors.append(
            DigestError(
                code="missing_ready_to_push_terminal_proof",
                detail=(
                    "ready_to_push terminal proof state is "
                    f"{state['state']!r}, expected {READY_TO_PUSH_TERMINAL_STATE}"
                ),
                truth_host=str(state.get("path") or "ready_to_push_terminal_proof"),
                next_action="run planveyor_post_merge_ready_to_push_closeout for the range",
            )
        )
    if state["final_bundle_status"] != "ok":
        errors.append(
            DigestError(
                code="ready_to_push_final_bundle_not_ok",
                detail=(
                    "ready_to_push terminal proof final_bundle_status is "
                    f"{state['final_bundle_status']!r}, expected 'ok'"
                ),
                truth_host=str(state.get("path") or "ready_to_push_terminal_proof"),
                next_action="rerun planveyor_merge_bundle_report and fix blockers before closeout",
            )
        )
    if state["pending_owner_gate"] != PENDING_OWNER_GATE:
        errors.append(
            DigestError(
                code="ready_to_push_pending_gate_mismatch",
                detail=(
                    "ready_to_push terminal proof pending_owner_gate is "
                    f"{state['pending_owner_gate']!r}, expected {PENDING_OWNER_GATE!r}"
                ),
                truth_host=str(state.get("path") or "ready_to_push_terminal_proof"),
                next_action="rerun planveyor_post_merge_ready_to_push_closeout with the current helper",
            )
        )
    return errors


def build_digest(
    root: Path,
    *,
    tracker_path: Path | None = None,
    explicit_range: str | None = None,
    risk_packet_arg: Path | None = None,
    mirror_policy: MirrorPolicy = GENERIC_MIRROR_POLICY,
) -> dict[str, Any]:
    report = merge_bundle_report.build_report(root, tracker_path, mirror_policy=mirror_policy)
    range_info = _report_range(report)
    errors: list[DigestError] = []

    explicit_base, explicit_head = _split_range(explicit_range)
    if explicit_range and (explicit_base is None or explicit_head is None):
        errors.append(
            DigestError(
                code="range_argument_invalid",
                detail=f"--range must use BASE..HEAD form, got {explicit_range!r}",
                truth_host="--range",
                next_action="pass --range BASE..HEAD or omit --range",
            )
        )
    if explicit_base and range_info["base"] and explicit_base != range_info["base"]:
        errors.append(
            DigestError(
                code="range_argument_mismatch",
                detail=f"--range base {explicit_base} does not match tracker/report base {range_info['base']}",
                truth_host="--range",
                next_action="use the active tracker range or rerun planveyor_range_set",
            )
        )
    if explicit_head and range_info["head"] and explicit_head != range_info["head"]:
        errors.append(
            DigestError(
                code="range_argument_mismatch",
                detail=f"--range head {explicit_head} does not match tracker/report head {range_info['head']}",
                truth_host="--range",
                next_action="use the active tracker range or rerun planveyor_range_set",
            )
        )

    risk_packet_path: Path | None = None
    risk_payload: dict[str, Any] | None = None
    if not range_info["range"]:
        errors.append(
            DigestError(
                code="missing_range_context",
                detail="merge bundle report did not expose base/head for risk packet discovery",
                truth_host="merge_bundle_report.range",
                next_action="run planveyor_range_set and planveyor_merge_bundle_report before this digest",
            )
        )
    else:
        readback = range_review_risk_packet.read_risk_packet(
            root,
            range_ref=range_info["range"],
            risk_packet_path=risk_packet_arg,
        )
        errors.extend(_digest_errors_from_packet_readback(readback))
        risk_payload = readback.payload
        if risk_payload is not None and readback.packet_path and not readback.packet_path.startswith("docs/reviews/*"):
            risk_packet_path = root / readback.packet_path

    risk_hosts = _risk_truth_hosts(risk_payload)
    if risk_payload is not None:
        errors.extend(_truth_host_errors(root, risk_hosts))
        errors.extend(_validate_digest_truth_host_freshness(report, risk_hosts))

    if report.get("status") != "ok":
        errors.append(
            DigestError(
                code="red_merge_bundle_report",
                detail=(
                    "merge_bundle_report status is "
                    f"{report.get('status')!r}; errors={json.dumps(report.get('errors') or [], ensure_ascii=False)}"
                ),
                truth_host="planveyor_merge_bundle_report",
                next_action="fix planveyor_merge_bundle_report blockers before owner push",
            )
        )

    if risk_payload and risk_payload.get("packet_status") != "ok":
        errors.append(
            DigestError(
                code="risk_packet_not_ok",
                detail=f"risk packet packet_status is {risk_payload.get('packet_status')!r}",
                truth_host=_repo_rel(risk_packet_path, root) if risk_packet_path else "risk_packet",
                next_action="resolve review risk packet blockers before owner push",
            )
        )

    review_host = _truth_host_state(risk_hosts, "review_artifact")
    review_status = review_host.get("status")
    if _review_status_is_blocking(review_status):
        errors.append(
            DigestError(
                code="red_review_truth_host",
                detail=f"review truth host status is {review_status!r}",
                truth_host=str(review_host.get("path") or "review_artifact"),
                next_action="fix live review blockers and regenerate planveyor_review_risk_packet",
            )
        )

    live_blockers = _as_list((risk_payload or {}).get("live_blockers"))
    if live_blockers:
        errors.append(
            DigestError(
                code="live_review_blockers",
                detail=f"risk packet still lists {len(live_blockers)} live blocker(s)",
                truth_host=_truth_host_state(risk_hosts, "review_artifact").get("path", "review_artifact"),
                next_action="fix live review blockers and rerun range review/risk packet",
            )
        )

    errors.extend(_validate_ready_to_push(report))

    followups_state, followups_errors = _followups_state(report)
    errors.extend(followups_errors)

    pending_owner_gate = _ready_to_push_state(report)["pending_owner_gate"]
    if pending_owner_gate != PENDING_OWNER_GATE:
        pending_owner_gate = PENDING_OWNER_GATE

    payload = {
        "schema_version": SCHEMA_VERSION,
        "range_id": (risk_payload or {}).get("range_id")
        or f"{range_info['base_short']}_{range_info['head_short']}",
        "range": range_info["range"],
        "base": range_info["base"],
        "head": range_info["head"],
        "tracker_current_step": _as_dict(report.get("tracker")).get("current_step")
        or "N/A",
        "tracker_completed_steps": _as_list(_as_dict(report.get("tracker")).get("completed_steps")),
        "live_review_verdict": _live_review_verdict(risk_payload, risk_hosts),
        "live_blockers": live_blockers,
        "historical_blockers": _as_list((risk_payload or {}).get("historical_blockers")),
        "closure_artifacts": _as_list((risk_payload or {}).get("closure_artifacts")),
        "active_packetization_report": _active_packetization_report(report, risk_hosts),
        "followups_state": followups_state,
        "process_improvements_state": _process_improvements_state(report),
        "archive_snapshot_state": _archive_snapshot_state(report),
        "operational_receipt_state": _artifact_state(
            report,
            "post_merge_operational_receipt",
            _truth_host_state(risk_hosts, "operational_receipt"),
        ),
        "ready_to_push_state": _ready_to_push_state(report),
        "pending_owner_gate": pending_owner_gate,
        "truth_hosts": _build_truth_hosts(root, report, risk_packet_path, risk_hosts),
        "digest_status": "ok" if not errors else "blocked",
        "errors": [error.as_dict() for error in errors],
    }
    return payload


def render_plain(payload: dict[str, Any]) -> str:
    active_packetization = _as_dict(payload.get("active_packetization_report"))
    followups = _as_dict(payload.get("followups_state"))
    lines = [
        "Merge range verdict digest",
        f"schema_version: {payload.get('schema_version')}",
        f"digest_status: {payload.get('digest_status')}",
        f"range_id: {payload.get('range_id')}",
        f"range: {payload.get('range')}",
        f"tracker_current_step: {payload.get('tracker_current_step')}",
        "tracker_completed_steps: "
        + ", ".join(str(step) for step in payload.get("tracker_completed_steps", [])),
    ]
    verdict = _as_dict(payload.get("live_review_verdict"))
    lines.extend(
        [
            f"live_review_verdict: {verdict.get('verdict')}",
            f"live_blockers: {len(_as_list(payload.get('live_blockers')))}",
            f"historical_blockers: {len(_as_list(payload.get('historical_blockers')))}",
            "active_packetization_report: " + str(active_packetization.get("path")),
            "active_packetization_report.gate_status: "
            + str(active_packetization.get("gate_status")),
            "active_packetization_report.blocking_rows_count: "
            + str(active_packetization.get("blocking_rows_count")),
            "active_packetization_report.draft_packets_created_count: "
            + str(active_packetization.get("draft_packets_created_count")),
            "followups_state: " + str(followups.get("lane_status")),
            "followups_state.owner_summary: " + str(followups.get("owner_summary")),
            "followups_state.launch_receipt_status: "
            + str(followups.get("launch_receipt_status")),
            "followups_state.source: " + str(followups.get("source")),
            "followups_state.harvest_file_followups_result: "
            + str(followups.get("harvest_file_followups_result")),
            "followups_state.harvest_file_followups_count: "
            + str(followups.get("harvest_file_followups_count")),
            "followups_state.range_triage_mode: " + str(followups.get("range_triage_mode")),
            "followups_state.range_append_new: " + str(followups.get("range_append_new")),
            "followups_state.range_merge_source: " + str(followups.get("range_merge_source")),
            "followups_state.range_possible_duplicate: "
            + str(followups.get("range_possible_duplicate")),
            "followups_state.range_route_fallback: "
            + str(followups.get("range_route_fallback")),
            "followups_state.range_unparsed_bullets: "
            + str(followups.get("range_unparsed_bullets")),
            "followups_state.range_unresolved_append_new: "
            + str(followups.get("range_unresolved_append_new")),
            "followups_state.range_unresolved_possible_duplicate: "
            + str(followups.get("range_unresolved_possible_duplicate")),
            "followups_state.range_unresolved_route_fallback: "
            + str(followups.get("range_unresolved_route_fallback")),
            "followups_state.range_unresolved_unparsed_bullets: "
            + str(followups.get("range_unresolved_unparsed_bullets")),
            "followups_state.manual_decision_ref: "
            + str(followups.get("manual_decision_ref")),
            "followups_state.already_tracked_ref: "
            + str(followups.get("already_tracked_ref")),
            "followups_state.index_rebuild_status: "
            + str(followups.get("index_rebuild_status")),
            "followups_state.index_readback_status: "
            + str(followups.get("index_readback_status")),
            "followups_state.index_path: " + str(followups.get("index_path")),
            "followups_state.unresolved_total: " + str(followups.get("unresolved_total")),
            "process_improvements_state: "
            + str(_as_dict(payload.get("process_improvements_state")).get("lane_status")),
            "archive_snapshot_state: "
            + str(_as_dict(payload.get("archive_snapshot_state")).get("status")),
            "operational_receipt_state: "
            + str(_as_dict(payload.get("operational_receipt_state")).get("status")),
            "ready_to_push_state: " + str(_as_dict(payload.get("ready_to_push_state")).get("state")),
            f"pending_owner_gate: {payload.get('pending_owner_gate')}",
        ]
    )
    truth_hosts = _as_dict(payload.get("truth_hosts"))
    lines.append("truth_hosts:")
    for key in (
        "risk_packet",
        "review_artifact",
        "packetization_report",
        "post_merge_audit",
        "operational_receipt",
        "ready_to_push_closeout",
    ):
        host = _as_dict(truth_hosts.get(key))
        lines.append(f"  {key}: {host.get('path') or host.get('source_command') or 'N/A'}")
    if payload.get("errors"):
        lines.append("errors:")
        for error in payload.get("errors", []):
            if not isinstance(error, dict):
                continue
            lines.append(
                "  - "
                + str(error.get("code"))
                + ": "
                + str(error.get("detail"))
                + f" (truth_host={error.get('truth_host')})"
            )
    else:
        lines.append("errors: none")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only final merge-range verdict digest for Owner push decisions.",
    )
    parser.add_argument("--repo-root", default=".", help="Repository root (default: cwd)")
    parser.add_argument("--tracker", help="Explicit merge tracker path")
    parser.add_argument("--range", dest="range_ref", help="Optional expected BASE..HEAD")
    parser.add_argument("--risk-packet", help="Explicit active range risk packet path")
    parser.add_argument(
        "--content-profile-id",
        default="default",
        choices=("default", "planveyor", "target-local"),
        help="Resolved public content profile for the generic mirror policy.",
    )
    parser.add_argument(
        "--format",
        choices=("plain", "json"),
        default="plain",
        help="Output format (default: plain)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path(args.repo_root).resolve()
    tracker_path = Path(args.tracker) if args.tracker else None
    if tracker_path and not tracker_path.is_absolute():
        tracker_path = root / tracker_path
    risk_packet = Path(args.risk_packet) if args.risk_packet else None

    try:
        mirror_policy = load_shared_docs_mirror_policy(content_profile_id=args.content_profile_id)
        payload = build_digest(
            root,
            tracker_path=tracker_path,
            explicit_range=args.range_ref,
            risk_packet_arg=risk_packet,
            mirror_policy=mirror_policy,
        )
    except MirrorPolicyError as exc:
        print(f"merge_range_verdict_digest: mirror_policy_invalid: {exc}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps({"merge_range_verdict_digest": payload}, indent=2, ensure_ascii=False))
    else:
        print(render_plain(payload))
    return 0 if payload.get("digest_status") == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())

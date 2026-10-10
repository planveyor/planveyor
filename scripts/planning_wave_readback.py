#!/usr/bin/env python3
"""Read-only planning-wave operator readback helpers."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import plan_status_oracle


SCHEMA_VERSION = "planning_wave_readback.v1"
DEFAULT_JSON_OUT = ".tmp/planning_wave_readback.json"
PLAN_REF_RE = re.compile(r"docs/plans/[A-Za-z0-9_./-]+\.md")
TERMINAL_STATUSES = {"done", "superseded", "cancelled"}
VALID_WAVE_FAMILIES = {"analysis_wave"}
VALID_PHASE_OVERLAYS = {"decomposition_wave"}
VALID_PHASE_STATES = {"active", "parked"}
ROUTE_VALUES = {
    "developer_wave",
    "decomposition_wave",
    "analysis_wave",
    "human_gate",
    "defer",
    "reject",
    "qa_wave",
    "post_merge_wave",
}


@dataclass(frozen=True)
class PlanDoc:
    path: Path
    rel_path: str
    title: str
    status: str | None
    meta_read: plan_status_oracle.StrictPlanMetaJsonResult
    text: str

    @property
    def plan_meta(self) -> dict[str, Any]:
        if self.meta_read.state == "valid" and isinstance(self.meta_read.plan_meta, dict):
            return dict(self.meta_read.plan_meta)
        return {}

    @property
    def status_norm(self) -> str:
        return _normalize(self.status)

    @property
    def is_open(self) -> bool:
        return self.status_norm not in TERMINAL_STATUSES

    @property
    def wave_family(self) -> str | None:
        value = self.plan_meta.get("wave_family")
        return str(value) if value else None

    @property
    def phase_overlay(self) -> str | None:
        value = self.plan_meta.get("phase_overlay")
        return str(value) if value else None

    @property
    def phase_state(self) -> str | None:
        value = self.plan_meta.get("phase_state")
        return str(value) if value else None


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _rel(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _status_from_text(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("##"):
            break
        if stripped.startswith("**Status:**"):
            value = stripped[len("**Status:**") :].strip()
            return value or None
    return None


def _title_from_text(text: str, rel_path: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return rel_path


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
            suffix = current[len(wanted) :] if current.startswith(wanted) else ""
            in_section = current == wanted or suffix.startswith((" ", "(", ":", "-"))
            continue
        if in_section:
            lines.append(line)
    return "\n".join(lines).strip()


def _table_values(section: str, key: str) -> list[str]:
    key_norm = _normalize(key)
    values: list[str] = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip().strip("`") for cell in stripped.strip("|").split("|")]
        if len(cells) < 2:
            continue
        if set(cells[0]) <= {"-", ":", " "}:
            continue
        if _normalize(cells[0]) == key_norm:
            values.append(cells[1].strip())
    return values


def _table_value(section: str, key: str) -> str | None:
    values = _table_values(section, key)
    if not values:
        return None
    return values[0] or None


def _route_label(value: Any) -> str:
    raw = str(value or "").strip().strip("`<> ")
    normalized = _normalize(raw)
    for route in sorted(ROUTE_VALUES, key=len, reverse=True):
        if route in normalized:
            return route
    return raw or "unknown"


def _leading_token(value: Any) -> str:
    raw = str(value or "").strip().strip("`").strip()
    match = re.match(r"^[A-Za-z0-9_/-]+", raw)
    if not match:
        return ""
    return match.group(0).lower()


def _ref_plan_path(value: str) -> str:
    return str(value or "").strip().strip("`").split("#", 1)[0]


def _plan_refs(text: str) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for match in PLAN_REF_RE.finditer(text):
        ref = match.group(0)
        if ref not in seen:
            seen.add(ref)
            refs.append(ref)
    return refs


def _boolish_section_present(section: str) -> bool:
    if not section:
        return False
    first = next((line.strip() for line in section.splitlines() if line.strip()), "")
    return bool(first and not first.startswith("N/A"))


def load_plans(root: Path) -> list[PlanDoc]:
    docs: list[PlanDoc] = []
    plans_root = root / "docs/plans"
    if not plans_root.exists():
        return docs
    for path in sorted(plans_root.glob("*.md")):
        # Like the other plan scanners, skip the directory README and the templates.
        if path.name == "README.md" or path.name.startswith("_"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        rel_path = _rel(root, path)
        docs.append(
            PlanDoc(
                path=path,
                rel_path=rel_path,
                title=_title_from_text(text, rel_path),
                status=_status_from_text(text),
                meta_read=plan_status_oracle.strict_plan_meta_json(text),
                text=text,
            )
        )
    return docs


def _add_diag(
    diagnostics: list[dict[str, Any]],
    *,
    severity: str,
    code: str,
    plan: str,
    truth_host: str,
    detail: str,
    **extra: Any,
) -> None:
    row = {
        "severity": severity,
        "code": code,
        "plan": plan,
        "truth_host": truth_host,
        "detail": detail,
    }
    row.update({key: value for key, value in extra.items() if value is not None})
    diagnostics.append(row)


def _promoted_section(plan: PlanDoc) -> dict[str, str] | None:
    section = _section_text(plan.text, "Promoted route artifact")
    if not _boolish_section_present(section):
        return None
    accepted_route = _table_value(section, "accepted_route") or _table_value(section, "Accepted route")
    promoted_ref = (
        _table_value(section, "promoted_artifact_ref")
        or _table_value(section, "Promoted artifact ref")
        or _table_value(section, "Promoted artifact")
    )
    if not accepted_route and not promoted_ref:
        return None
    return {
        "accepted_route": _route_label(accepted_route),
        "promoted_artifact_ref": promoted_ref or "unknown",
        "truth_host": f"{plan.rel_path}#Promoted route artifact",
    }


def _promoted_from(plan: PlanDoc) -> dict[str, str] | None:
    value = plan.plan_meta.get("promoted_from")
    if not isinstance(value, dict):
        return None
    accepted_route = value.get("accepted_route")
    promoted_ref = value.get("promoted_artifact_ref")
    if not accepted_route and not promoted_ref:
        return None
    return {
        "accepted_route": _route_label(accepted_route),
        "promoted_artifact_ref": str(promoted_ref or "unknown"),
        "source_plan": str(value.get("source_plan") or "unknown"),
        "source_route_ref": str(value.get("source_route_ref") or "unknown"),
        "queue_admission": str(value.get("queue_admission_at_acceptance") or "unknown"),
        "runner_admission": str(value.get("runner_admission_at_acceptance") or "unknown"),
        "truth_host": f"{plan.rel_path}#plan_meta.promoted_from",
    }


def _analysis_pack_authority(
    plan: PlanDoc,
) -> plan_status_oracle.AnalysisPackAuthorityResolution:
    return plan_status_oracle.resolve_analysis_pack_authority(
        origin_plan_path=plan.path,
        plan_text=plan.text,
        effective_status=plan.status,
    )


def _analysis_pack_truth_host(
    plan: PlanDoc,
    authority: plan_status_oracle.AnalysisPackAuthorityResolution,
) -> str:
    if authority.mode == "legacy":
        return f"{plan.rel_path}#Analysis pack"
    return authority.truth_host or f"{plan.rel_path}#Analysis pack"


def _route_recommendation(
    plan: PlanDoc,
    authority: plan_status_oracle.AnalysisPackAuthorityResolution | None = None,
) -> str | None:
    authority = authority or _analysis_pack_authority(plan)
    if not authority.is_valid:
        return None
    section = _section_text(authority.authority_text, "Analysis pack")
    if not section:
        return None
    table_values = _table_values(section, "route_recommendation")
    if table_values:
        if len(table_values) != 1:
            return "unknown"
        candidate = table_values[0]
    else:
        candidate = None
        for line in section.splitlines():
            match = re.match(
                r"^\s*(?:[-*]\s*)?`?route(?:_| )recommendation`?\s*[:=]\s*(.*)$",
                line,
                re.IGNORECASE,
            )
            if match:
                candidate = match.group(1)
                break
    if candidate is None:
        return None
    primary = _leading_token(candidate)
    return primary if primary in ROUTE_VALUES else "unknown"


def _child_refs(plan: PlanDoc) -> tuple[list[str], list[str]]:
    child_map_refs = _plan_refs(_section_text(plan.text, "Child plan map"))
    queue_refs = _plan_refs(_section_text(plan.text, "Execution queue"))
    return child_map_refs, queue_refs


def _deferred_refs(plan: PlanDoc) -> list[str]:
    return _plan_refs(_section_text(plan.text, "Follow-ups (deferred)"))


def _dependencies(section: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for token in ("sequential", "parallel", "soft", "blocking"):
        if re.search(rf"\b{re.escape(token)}\b", section, re.IGNORECASE) and token not in seen:
            seen.add(token)
            found.append(token)
    return found


def _proof_lanes(section: str) -> list[str]:
    lanes: list[str] = []
    for line in section.splitlines():
        if re.search(r"\bproof\b|proof lane|proof-path", line, re.IGNORECASE):
            cleaned = line.strip().lstrip("-* ").strip()
            if cleaned:
                lanes.append(cleaned[:180])
    return lanes


def _open_decisions(plan: PlanDoc) -> list[str]:
    decisions: list[str] = []
    for heading in ("Open decisions", "Q&A log", "Owner questions"):
        section = _section_text(plan.text, heading)
        if not section:
            continue
        for line in section.splitlines():
            cleaned = line.strip()
            if re.search(r"needs_owner|open decision|owner|Q[0-9]+", cleaned, re.IGNORECASE):
                decisions.append(cleaned[:180])
    return decisions


def _plan_status(plans_by_rel: dict[str, PlanDoc], ref: str) -> str:
    plan = plans_by_rel.get(ref)
    if plan is None:
        return "missing"
    return plan.status or "unknown"


def _preview(plan: PlanDoc, plans_by_rel: dict[str, PlanDoc]) -> dict[str, Any]:
    child_map_section = _section_text(plan.text, "Child plan map")
    execution_queue_section = _section_text(plan.text, "Execution queue")
    child_refs, queue_refs = _child_refs(plan)
    dependencies = _dependencies(child_map_section + "\n" + execution_queue_section)
    proof_lanes = _proof_lanes(child_map_section + "\n" + _section_text(plan.text, "Decomposition quality gate"))
    child_statuses = {ref: _plan_status(plans_by_rel, ref) for ref in child_refs}
    pending_refs = [
        ref
        for ref, status in child_statuses.items()
        if _normalize(status) not in TERMINAL_STATUSES
    ]
    deferred_refs = _deferred_refs(plan)
    open_decisions = _open_decisions(plan)
    return {
        "plan": plan.rel_path,
        "status": plan.status,
        "phase_state": plan.phase_state,
        "child_count": len(child_refs),
        "child_refs": child_refs,
        "child_statuses": child_statuses,
        "pending_child_count": len(pending_refs),
        "pending_child_refs": pending_refs,
        "execution_queue_count": len(queue_refs),
        "execution_queue_refs": queue_refs,
        "dependency_types": dependencies,
        "proof_lanes": proof_lanes,
        "deferred_refs": deferred_refs,
        "open_decisions": open_decisions,
        "truth_hosts": [
            f"{plan.rel_path}#Child plan map",
            f"{plan.rel_path}#Execution queue",
            f"{plan.rel_path}#plan_meta",
        ],
    }


def _has_preview_carrier(plan: PlanDoc) -> bool:
    child_refs, queue_refs = _child_refs(plan)
    return plan.phase_overlay == "decomposition_wave" or bool(child_refs or queue_refs)


def _validate_plan(
    plan: PlanDoc,
    *,
    plans_by_rel: dict[str, PlanDoc],
    diagnostics: list[dict[str, Any]],
    analysis_authority: plan_status_oracle.AnalysisPackAuthorityResolution,
) -> None:
    if plan.meta_read.state != "valid":
        _add_diag(
            diagnostics,
            severity="warning",
            code="plan_meta_strict_read_failed",
            plan=plan.rel_path,
            truth_host=f"{plan.rel_path}#plan_meta",
            detail=(
                f"reader_state={plan.meta_read.state}; reason_code={plan.meta_read.reason_code}; "
                f"{plan.meta_read.reason}; derived routing fields are unknown."
            ),
            reason_code=plan.meta_read.reason_code,
        )
    if not analysis_authority.is_valid:
        _add_diag(
            diagnostics,
            severity="error",
            code=plan_status_oracle.ANALYSIS_PACK_AUTHORITY_INVALID,
            plan=plan.rel_path,
            truth_host=_analysis_pack_truth_host(plan, analysis_authority),
            detail=f"detail_category={analysis_authority.detail_category}; analysis recommendation suppressed.",
        )
    if plan.wave_family and plan.wave_family not in VALID_WAVE_FAMILIES:
        _add_diag(
            diagnostics,
            severity="error",
            code="invalid_wave_family",
            plan=plan.rel_path,
            truth_host=f"{plan.rel_path}#plan_meta.wave_family",
            detail=f"Unsupported wave_family={plan.wave_family}",
        )
    if plan.phase_overlay and plan.phase_overlay not in VALID_PHASE_OVERLAYS:
        _add_diag(
            diagnostics,
            severity="error",
            code="invalid_phase_overlay",
            plan=plan.rel_path,
            truth_host=f"{plan.rel_path}#plan_meta.phase_overlay",
            detail=f"Unsupported phase_overlay={plan.phase_overlay}",
        )
    if plan.phase_overlay == "decomposition_wave" and plan.phase_state not in VALID_PHASE_STATES:
        _add_diag(
            diagnostics,
            severity="error",
            code="invalid_phase_state",
            plan=plan.rel_path,
            truth_host=f"{plan.rel_path}#plan_meta.phase_state",
            detail=f"Unsupported phase_state={plan.phase_state}",
        )

    if plan.phase_overlay == "decomposition_wave":
        child_refs, queue_refs = _child_refs(plan)
        if plan.phase_state == "active" and not child_refs and not queue_refs:
            _add_diag(
                diagnostics,
                severity="warning",
                code="missing_child_graph",
                plan=plan.rel_path,
                truth_host=f"{plan.rel_path}#Child plan map",
                detail="Active decomposition plan has no child map or execution queue refs.",
            )
        if child_refs and queue_refs and set(child_refs) != set(queue_refs):
            _add_diag(
                diagnostics,
                severity="error",
                code="child_map_execution_queue_mismatch",
                plan=plan.rel_path,
                truth_host=f"{plan.rel_path}#Child plan map|#Execution queue",
                detail="Child map and execution queue refs disagree.",
                child_map_refs=child_refs,
                execution_queue_refs=queue_refs,
            )
        for ref in child_refs + queue_refs:
            if ref not in plans_by_rel:
                _add_diag(
                    diagnostics,
                    severity="error",
                    code="missing_child_plan",
                    plan=plan.rel_path,
                    truth_host=f"{plan.rel_path}#Child plan map|#Execution queue",
                    detail=f"Referenced child plan is missing: {ref}",
                    ref=ref,
                )

    promoted_meta = _promoted_from(plan)
    promoted_section = _promoted_section(plan)
    if promoted_meta and promoted_section:
        if _normalize(promoted_meta["accepted_route"]) != _normalize(promoted_section["accepted_route"]):
            _add_diag(
                diagnostics,
                severity="error",
                code="promoted_route_conflict",
                plan=plan.rel_path,
                truth_host=f"{promoted_meta['truth_host']}|{promoted_section['truth_host']}",
                detail="plan_meta.promoted_from accepted_route conflicts with Promoted route artifact.",
                meta_route=promoted_meta["accepted_route"],
                section_route=promoted_section["accepted_route"],
            )
    accepted = promoted_meta or promoted_section
    if accepted:
        ref = accepted.get("promoted_artifact_ref") or ""
        ref_plan_path = _ref_plan_path(ref)
        if ref_plan_path.startswith("docs/plans/") and ref_plan_path not in plans_by_rel:
            _add_diag(
                diagnostics,
                severity="error",
                code="missing_promoted_artifact_ref",
                plan=plan.rel_path,
                truth_host=accepted["truth_host"],
                detail=f"Accepted route ref points to a missing plan: {ref}",
                ref=ref,
            )

    recommendation = _route_recommendation(plan, analysis_authority)
    if recommendation and not accepted:
        _add_diag(
            diagnostics,
            severity="warning",
            code="recommendation_only_no_accepted_route",
            plan=plan.rel_path,
            truth_host=_analysis_pack_truth_host(plan, analysis_authority),
            detail="Analysis route recommendation exists without accepted Promoted route artifact/promoted_from carrier.",
            recommended_route=recommendation,
        )


def build_readback(*, root: Path, json_out: Path, generated_at: str) -> dict[str, Any]:
    root = root.resolve()
    plans = load_plans(root)
    plans_by_rel = {plan.rel_path: plan for plan in plans}
    analysis_authorities = {
        plan.rel_path: _analysis_pack_authority(plan)
        for plan in plans
    }
    diagnostics: list[dict[str, Any]] = []
    for plan in plans:
        _validate_plan(
            plan,
            plans_by_rel=plans_by_rel,
            diagnostics=diagnostics,
            analysis_authority=analysis_authorities[plan.rel_path],
        )

    analysis_open = [
        {"plan": plan.rel_path, "status": plan.status, "title": plan.title}
        for plan in plans
        if plan.wave_family == "analysis_wave" and plan.is_open
    ]
    decomposition_open = [
        {
            "plan": plan.rel_path,
            "status": plan.status,
            "phase_state": plan.phase_state,
            "title": plan.title,
        }
        for plan in plans
        if plan.phase_overlay == "decomposition_wave" and plan.phase_state == "active" and plan.is_open
    ]
    parked_umbrellas = [
        {"plan": plan.rel_path, "status": plan.status, "title": plan.title}
        for plan in plans
        if plan.phase_overlay == "decomposition_wave" and plan.phase_state == "parked"
    ]

    previews = [
        _preview(plan, plans_by_rel)
        for plan in plans
        if _has_preview_carrier(plan)
    ]
    pending_child_umbrellas = [
        {
            "plan": preview["plan"],
            "pending_child_count": preview["pending_child_count"],
            "pending_child_refs": preview["pending_child_refs"],
        }
        for preview in previews
        if preview["pending_child_count"] > 0
    ]

    accepted_entries: list[dict[str, Any]] = []
    recommendation_only_refs: list[dict[str, Any]] = []
    provenance_chains: list[dict[str, Any]] = []
    for plan in plans:
        promoted_meta = _promoted_from(plan)
        promoted_section = _promoted_section(plan)
        accepted = promoted_meta or promoted_section
        if accepted:
            accepted_entries.append(
                {
                    "plan": plan.rel_path,
                    "accepted_route": accepted["accepted_route"],
                    "promoted_artifact_ref": accepted["promoted_artifact_ref"],
                    "truth_host": accepted["truth_host"],
                    "route_truth_source": "plan_meta.promoted_from" if promoted_meta else "Promoted route artifact",
                    "queue_admission": accepted.get("queue_admission"),
                    "runner_admission": accepted.get("runner_admission"),
                }
            )
        analysis_authority = analysis_authorities[plan.rel_path]
        recommendation = _route_recommendation(plan, analysis_authority)
        if recommendation and not accepted:
            recommendation_only_refs.append(
                {
                    "plan": plan.rel_path,
                    "recommended_route": recommendation,
                    "truth_host": _analysis_pack_truth_host(plan, analysis_authority),
                    "state": "recommendation_only_no_accepted_route",
                }
            )

        parent = plan.plan_meta.get("parent")
        depends_on = plan.plan_meta.get("depends_on")
        if promoted_meta or parent or depends_on:
            hops: list[dict[str, str]] = []
            if parent:
                hops.append({"kind": "parent", "ref": str(parent)})
            if isinstance(depends_on, list):
                for ref in depends_on:
                    hops.append({"kind": "depends_on", "ref": str(ref)})
            if promoted_meta:
                hops.append({"kind": "source_plan", "ref": promoted_meta.get("source_plan") or "unknown"})
                hops.append({"kind": "source_route_ref", "ref": promoted_meta.get("source_route_ref") or "unknown"})
                hops.append({"kind": "promoted_artifact_ref", "ref": promoted_meta.get("promoted_artifact_ref") or "unknown"})
            provenance_chains.append({"plan": plan.rel_path, "hops": hops})

    route_counter = Counter(entry["accepted_route"] for entry in accepted_entries)
    if any(item["severity"] == "error" for item in diagnostics):
        confidence = {"status": "low", "reason": "red_truth_host_diagnostics_present"}
    elif diagnostics:
        confidence = {"status": "medium", "reason": "missing_or_ambiguous_truth_host_diagnostics_present"}
    else:
        confidence = {"status": "high", "reason": "all_readback_truth_hosts_consistent"}

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "inputs": {
            "root": root.as_posix(),
            "plans_glob": "docs/plans/*.md",
            "plan_count": len(plans),
            "json_out": _rel(root, json_out),
        },
        "buckets": {
            "open_analysis_waves": analysis_open,
            "open_decomposition_waves": decomposition_open,
            "parked_decomposition_umbrellas": parked_umbrellas,
            "pending_child_umbrellas": pending_child_umbrellas,
            "recommendation_only_refs": recommendation_only_refs,
        },
        "decomposition_previews": previews,
        "provenance_chains": provenance_chains,
        "accepted_routes": {
            "entries": accepted_entries,
            "by_route": dict(sorted(route_counter.items())),
        },
        "truth_source_boundary": {
            "route_truth_sources": [
                "## Promoted route artifact",
                "plan_meta.promoted_from",
                "oracle accepted-route readback fields",
            ],
            "recommendation_prose_is_truth": False,
            "helper_is_read_only": True,
            "persistent_registry": "out_of_scope",
        },
        "confidence": {
            **confidence,
            "diagnostics": diagnostics,
        },
    }


def _append_plan_rows(lines: list[str], title: str, rows: list[dict[str, Any]], fields: list[str]) -> None:
    lines.append(f"  {title}:")
    if not rows:
        lines.append("    - none")
        return
    for row in rows:
        rendered = " ".join(f"{field}={row.get(field, 'N/A')}" for field in fields)
        lines.append(f"    - {rendered}")


def render_plain(payload: dict[str, Any], mode: str = "all") -> str:
    buckets = payload["buckets"]
    routes = payload["accepted_routes"]
    confidence = payload["confidence"]
    lines = [
        "planning-wave-readback:",
        f"  schema_version: {payload['schema_version']}",
        f"  confidence: {confidence['status']} ({confidence['reason']})",
        f"  open_analysis_waves: {len(buckets['open_analysis_waves'])}",
        f"  open_decomposition_waves: {len(buckets['open_decomposition_waves'])}",
        f"  parked_decomposition_umbrellas: {len(buckets['parked_decomposition_umbrellas'])}",
        f"  pending_child_umbrellas: {len(buckets['pending_child_umbrellas'])}",
        f"  accepted_route_entries: {len(routes['entries'])}",
        f"  recommendation_only_refs: {len(buckets['recommendation_only_refs'])}",
        f"  diagnostics: {len(confidence['diagnostics'])}",
    ]
    if routes["by_route"]:
        rendered = ", ".join(f"{route}={count}" for route, count in sorted(routes["by_route"].items()))
        lines.append(f"  accepted_routes_by_route: {rendered}")
    if mode == "waves":
        _append_plan_rows(lines, "open_analysis_waves", buckets["open_analysis_waves"], ["plan", "status"])
        _append_plan_rows(lines, "open_decomposition_waves", buckets["open_decomposition_waves"], ["plan", "status", "phase_state"])
        _append_plan_rows(lines, "parked_decomposition_umbrellas", buckets["parked_decomposition_umbrellas"], ["plan", "status"])
        _append_plan_rows(lines, "pending_child_umbrellas", buckets["pending_child_umbrellas"], ["plan", "pending_child_count"])
    if mode == "preview":
        lines.append("  decomposition_previews:")
        previews = payload["decomposition_previews"]
        if not previews:
            lines.append("    - none")
        for preview in previews:
            lines.append(
                "    - "
                f"plan={preview['plan']} child_count={preview['child_count']} "
                f"execution_queue_count={preview['execution_queue_count']} "
                f"dependency_types={','.join(preview['dependency_types']) or 'none'} "
                f"proof_lanes={len(preview['proof_lanes'])} "
                f"deferred_refs={len(preview['deferred_refs'])} "
                f"open_decisions={len(preview['open_decisions'])}"
            )
    if mode == "provenance":
        lines.append("  provenance_chains:")
        chains = payload["provenance_chains"]
        if not chains:
            lines.append("    - none")
        for chain in chains:
            hop_text = " -> ".join(f"{hop['kind']}:{hop['ref']}" for hop in chain["hops"]) or "none"
            lines.append(f"    - plan={chain['plan']} hops={hop_text}")
    if mode == "accepted-routes":
        _append_plan_rows(
            lines,
            "accepted_route_entries",
            routes["entries"],
            ["plan", "accepted_route", "promoted_artifact_ref", "route_truth_source"],
        )
        _append_plan_rows(
            lines,
            "recommendation_only_refs",
            buckets["recommendation_only_refs"],
            ["plan", "recommended_route", "state"],
        )
    return "\n".join(lines)


def _resolve(root: Path, raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else root / path


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repo root")
    parser.add_argument("--json-out", default=DEFAULT_JSON_OUT, help="Write readback JSON to this path")
    parser.add_argument("--generated-at", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--json", action="store_true", help="Print JSON payload to stdout")
    parser.add_argument(
        "--mode",
        choices=("all", "waves", "preview", "provenance", "accepted-routes"),
        default="all",
        help="Plain-output focus; JSON always contains the full readback",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    json_out = _resolve(root, args.json_out)
    payload = build_readback(root=root, json_out=json_out, generated_at=args.generated_at or _now_utc())
    _write_json(json_out, payload)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_plain(payload, args.mode))
        print(f"wrote {_rel(root, json_out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

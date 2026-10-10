#!/usr/bin/env python3
"""Promote one follow-up backlog row into a real dev-plan scaffold."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

sys.dont_write_bytecode = True
sys.pycache_prefix = os.devnull



_AUTHORITY_SCRIPTS_DIR = Path(__file__).resolve().parent
SCRIPT_DIR = _AUTHORITY_SCRIPTS_DIR


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
    package_paths = getattr(package, "__path__", None)
    if package_paths is None:
        return False
    try:
        paths = tuple(Path(entry).resolve(strict=True) for entry in package_paths)
    except (OSError, RuntimeError, TypeError, ValueError):
        return False
    if not paths or any(path != _AUTHORITY_SCRIPTS_DIR for path in paths):
        return False
    package_file = getattr(package, "__file__", None)
    return package_file is None or _module_has_expected_origin(
        package, _AUTHORITY_SCRIPTS_DIR / "__init__.py"
    )


def _assert_authority_alias_origin(module: object | None, expected: Path) -> None:
    if module is not None and not _module_has_expected_origin(module, expected):
        raise ImportError("authority module has an unsafe origin")


def _load_authority_context() -> Any:
    """Load only the exact sibling context module under either import spelling."""

    package_name = "scripts.contract_authority_context"
    direct_name = "contract_authority_context"
    package_is_local = _scripts_package_is_local()
    expected = _AUTHORITY_SCRIPTS_DIR / f"{direct_name}.py"
    direct = sys.modules.get(direct_name)
    packaged = sys.modules.get(package_name)
    _assert_authority_alias_origin(direct, expected)
    _assert_authority_alias_origin(packaged, expected)
    if direct is not None and packaged is not None and direct is not packaged:
        raise ImportError("authority module aliases are split")
    module = direct or packaged
    if module is None:
        script_dir = os.fspath(_AUTHORITY_SCRIPTS_DIR)
        if script_dir in sys.path:
            sys.path.remove(script_dir)
        sys.path.insert(0, script_dir)
        module = importlib.import_module(direct_name)
        _assert_authority_alias_origin(module, expected)
    sys.modules[direct_name] = module
    if package_is_local:
        sys.modules[package_name] = module
    return module


authority_context = _load_authority_context()

if TYPE_CHECKING:
    from contract_authority_context import ContractContext
else:
    ContractContext = Any


import followups_lint as common
import followups_apply
import followups_capture


class V2PromotionError(RuntimeError):
    """Fail-closed V2 promotion boundary error."""


def _promotion_context(
    project_root: Path,
    context: ContractContext | None = None,
) -> ContractContext:
    """Bind every public promotion writer to one verified project context."""

    return authority_context.context_for_reader(project_root, context)


def _validate_promotion_effect(context: ContractContext) -> None:
    authority_context.validate_before_effect(context)


def _reject_engaged_legacy_promotion(context: ContractContext) -> None:
    if context.state == "engaged":
        raise authority_context.ContractAuthorityError(
            "engaged_legacy_promotion_unsupported",
            "legacy follow-up promotion renderer is unavailable in engaged authority",
        )


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, check=False)


def _now_local() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %z")


def _normalize_role(raw: str) -> str:
    lowered = raw.strip().lower()
    if lowered in {"architect", "arch"}:
        return "Architect"
    if lowered == "planner":
        return "Planner"
    if lowered == "coder":
        return "Coder"
    raise ValueError(f"Unsupported author role: {raw!r}")


def _resolve_rel_path(project_root: Path, raw_path: str) -> str:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        resolved = path.resolve()
    else:
        resolved = (project_root / path).resolve()
    try:
        rel = resolved.relative_to(project_root)
    except ValueError as exc:
        raise ValueError(f"Path must stay inside project root: {raw_path}") from exc
    return rel.as_posix()


def _derive_code_draft_rel(plan_rel: str) -> str:
    plan_path = Path(plan_rel)
    return (Path("docs/code_drafts") / f"{plan_path.stem}__code_draft.md").as_posix()


def _find_item(project_root: Path, file_arg: str, line_no: int) -> tuple[common.FollowupFile, common.FollowupItem]:
    source_path = common.resolve_followup_path(project_root, file_arg)
    if not source_path.exists():
        raise FileNotFoundError(f"Missing follow-ups file: {file_arg}")
    followup = common.parse_followup_file(source_path, project_root)
    for item in followup.items:
        if item.line_no == line_no:
            return followup, item
    raise ValueError(f"No follow-up item found at {followup.rel_path}:{line_no}")


def _require_clean_followups_inventory(project_root: Path) -> common._FollowupsSnapshotInventory:
    """Fail before any promote-side artifact or legacy-row mutation."""

    try:
        snapshot, file_bytes = followups_capture.snapshot_followups(project_root, include_bytes=True)
    except followups_capture.CaptureError as exc:
        raise V2PromotionError(f"Follow-ups snapshot is unsafe: {exc}") from exc
    inventory = common._inventory_followups_snapshot(project_root, snapshot, file_bytes)
    if inventory.blockers:
        codes = ", ".join(sorted({finding.code for finding in inventory.blockers}))
        raise V2PromotionError(f"Follow-ups V2 integrity blocker: {codes}")
    return inventory


def _render_plan(
    *,
    plan_rel: str,
    draft_rel: str,
    source_rel: str,
    item: common.FollowupItem,
) -> str:
    plan_meta = {
        "plan_meta": {
            "cluster": item.cluster or "UNCONFIRMED",
            "tags": list(item.tags),
            "required_manager_mode": "either",
            "phase_overlay": None,
            "phase_state": None,
            "parent": None,
            "next_plans": [],
            "depends_on": [],
            "queue_activation": {
                "state": "owner_approved",
                "source_ref": f"follow-up promotion command for {source_rel}:{item.line_no}",
                "reason": "The operator explicitly promoted this backlog row into a plan carrier.",
            },
            "followups_out": [],
            "canon_updates": [],
        }
    }
    sources_value = item.fields.get("sources")
    sources_line = f"- Sources: `{sources_value}`" if sources_value else "- Sources: `N/A (not declared in backlog row)`"
    assignee = item.assignee or "architect"
    return "\n".join(
        [
            f"# Plan: {item.summary}",
            "",
            f"**Date:** {_now_local()}",
            "**Stage:** Stage 1",
            f"**Priority:** {item.priority}",
            "**Plan type:** dev",
            "**Status:** Architect initial draft",
            "**Schema version:** plan.v1",
            "",
            "**Handoff statuses (кто ставит):**",
            "- `Ready for Planner` — Architect",
            "- `Ready for Coder` — Planner",
            "- `Ready for Review` — Coder",
            "- `Ready for Arch review` — Reviewer",
            "- `Done` — Architect",
            "",
            "**Context links (source of truth):**",
            f"- Follow-up source: `{source_rel}`:{item.line_no}",
            "- Follow-ups index: `docs/followups/index.md`",
            f"- Code draft(s): `{draft_rel}`",
            "",
            "## Meta (machine-readable JSON; required for new plans)",
            "```json",
            json.dumps(plan_meta, ensure_ascii=False, indent=2),
            "```",
            "",
            "## Problem",
            f"- План промоутнут из backlog-строки `{source_rel}:{item.line_no}`.",
            f"- Summary: {item.summary}",
            f"- Backlog owner lane: `to={assignee}`.",
            f"- Why: {item.why or 'UNCONFIRMED (carry over from backlog row in Architect intake)' }",
            sources_line,
            "",
            "## Как я понял задачу",
            "- `TBD (why=follow-up scaffold only; Architect intake must replace this with a 3-7 line human-readable summary before Architect draft)`",
            "",
            "## Solution (high level)",
            f"- Создать честный dev-plan carrier `{plan_rel}` вместо backlog-only `plan=null`/placeholder path.",
            "- Сохранить scaffold узким: переносим только deterministic metadata из backlog строки; scope/acceptance/tests уточняются обычным Architect/Planner intake.",
            "",
            "## Decisions (final)",
            "- ✅ Promote materialize-ит реальный `docs/plans/*` carrier и back-reference из backlog строки; fake future `plan=` path не используется.",
            "- ✅ Этот scaffold не пытается заранее декомпозировать решение и не закрывает Planner-owned code draft target inventory.",
            "",
            "### UI playbooks (micro-block; required for UI tasks)",
            "- Playbooks: `N/A (follow-up scaffold; confirm in Architect intake)`",
            "- Playbook fields: `N/A (follow-up scaffold; confirm in Planner finalize)`",
            "",
            "## Scope",
            f"- Seed scope from promoted backlog row: `{item.summary}`.",
            f"- Carry over deterministic metadata: `cluster={item.cluster or 'UNCONFIRMED'}`, `tags={list(item.tags)}`, `to={assignee}`, `plan={plan_rel}`.",
            "- Remaining architecture/acceptance/runtime proof details stay for normal status-driven intake on this plan.",
            "",
            "## Out of scope",
            "- Silent backlog-wide reconciliation or duplicate harvest cleanup.",
            "- Placeholder child-plan generation or speculative decomposition beyond the promoted row.",
            "",
            "## Follow-ups (deferred)",
            "- none",
            "",
            "## Close-out routing",
            "- Roadmap/queue sync: `N/A (why=promotion only materializes the selected plan carrier)`",
            f"- Follow-up sync: `update source backlog row in {source_rel}`",
            "- Next bounded slice: `N/A (why=Architect/Planner intake owns any later split)`",
            "- Terminal outcome: no — this scaffold starts normal Architect intake",
            "",
            "## Rollout packet handoff",
            "- Role: `N/A (why=same-repo follow-up promotion)`",
            "- Packet path: `N/A (why=no rollout packet)`",
            "- Target repo: `N/A (why=same repo)`",
            "- Suggested target plan slug: `N/A (why=plan already materialized)`",
            "- Queue after import: `N/A (why=no cross-repo import)`",
            "",
            "## Mechanism coverage",
            "- `N/A (why=single follow-up promote scaffold)`",
            "",
            "## Risks / Open questions (summary)",
            "- Если backlog summary оказался слишком широким или смешал несколько тем, Architect intake обязан сузить scope или завести follow-up вместо молчаливого расширения.",
            "- Planner later must replace scaffold-only `UNCONFIRMED` carriers and fill executable proof paths before `Ready for Coder`.",
            "",
            "## Changes (by area)",
            "- Data/schema (migrations if used): `N/A (follow-up scaffold)`",
            "- Logic/modules: `N/A (follow-up scaffold)`",
            "- Interfaces (API/CLI/UI): `N/A (follow-up scaffold)`",
            "- Config (keys/defaults): `N/A (follow-up scaffold)`",
            f"- Docs/registry: `{plan_rel}`, `{draft_rel}`, `{source_rel}`",
            "",
            "## Acceptance criteria / DoD",
            "- [ ] Architect intake restamps scope/context/constraints without losing promoted backlog source facts.",
            "- [ ] Linked code draft stub exists and keeps `code_draft_meta.plan` aligned with this plan path.",
            "- [ ] Source backlog row now points to this real plan path with `status=promoted`.",
            "",
            "## Tests",
            "### Critical runtime invariants (required for risky UI/layout/visibility/default-state/access tasks)",
            "- `N/A (why=follow-up scaffold only)`",
            "",
            "### Что написать / поправить",
            "- `TBD in Architect/Planner intake`",
            "",
            "### Что прогнать",
            "- `TBD in Architect/Planner intake`",
            "",
            "## Commands",
            "- `TBD in Architect/Planner intake`",
            "",
            "## Verification rerun / exec handoff",
            "- Mode: fresh-exec",
            "- Context source: `PLAN_PATH + promoted backlog row`",
            "- Prompt: `Validate the generated follow-up scaffold before Architect intake.`",
            f"- Command: `python3 -B scripts/plan_lint.py {plan_rel}`",
            f"- Expected artifact: `{plan_rel}` and `{draft_rel}`",
            "",
            "## Evidence (chronological, append-only)",
            f"- [{_now_local()}] (Promote) Scaffold created from `{source_rel}:{item.line_no}`; backlog row now points at `{plan_rel}` and linked code draft stub `{draft_rel}`.",
            "",
            "## Review artifacts",
            f"- Code review (primary): `docs/code_reviews/{Path(plan_rel).stem}.md`",
            "",
            "## Q&A log (chronological, append-only)",
            "",
            "### Architect Q&A",
            "- `NO QUESTIONS` — follow-up promote created only the deterministic scaffold; semantic intake continues in this plan.",
            "",
            "## Suggestions log (chronological, append-only)",
            "",
            "### Architect suggestions",
            "- Keep this promoted scaffold narrow: no fake future child plans, no speculative test matrix, and no invented canon pointers beyond the promoted row.",
            "",
            "## Objections / risks log (chronological, append-only)",
            "",
            "### Architect objections",
            "- Backlog line must keep the real `plan=` pointer until either implementation closes and reconcile marks it `handled`, or Architect/Planner explicitly reroute the work.",
            "",
            "## Intake prompts (optional)",
            "- Какая реальная bounded problem statement скрывается за promoted summary?",
            "- Нужны ли дополнительные canon pointers/constraints before `Ready for Planner`?",
            "",
        ]
    )


def _render_code_draft(
    *,
    plan_rel: str,
    source_rel: str,
    item: common.FollowupItem,
    author_role: str,
) -> str:
    payload = {
        "code_draft_meta": {
            "plan": plan_rel,
            "cluster": item.cluster or "UNCONFIRMED",
            "targets": [{"path": "UNCONFIRMED", "kind": "py"}],
        }
    }
    return "\n".join(
        [
            f"# Code draft: {item.summary}",
            "",
            f"**Date:** {_now_local()}",
            f"**Cluster:** {item.cluster or 'UNCONFIRMED'}",
            f"**Related plan:** `{plan_rel}`",
            f"**Author role:** {author_role}",
            "**Status:** draft",
            "",
            "---",
            "",
            "## Meta (machine-readable JSON)",
            "```json",
            json.dumps(payload, ensure_ascii=False, indent=2),
            "```",
            "",
            "## Purpose",
            f"Seed code draft for promoted backlog row `{source_rel}:{item.line_no}`. Planner rewrites targets/steps after Architect intake; this stub only keeps honest linkage.",
            "",
            "## Targeted changes (by file)",
            "- `UNCONFIRMED`: fill exact file set during Planner finalize; this promote step does not invent implementation targets.",
            "",
            "## Patch sketch (keep it small)",
            "```text",
            "1. Re-read the promoted backlog row and linked canon.",
            "2. Replace `UNCONFIRMED` targets with exact files only after scope/acceptance are materialized.",
            "3. Keep post-review selective staging honest: no stale/advisory paths by `Ready for Review`.",
            "```",
            "",
            "## Critical invariants / traps / bypass paths",
            "- `Invariant:` this draft stays a seed carrier until Planner finalize replaces `UNCONFIRMED` targets.",
            "  - `Trap:` treating promote-time metadata as final implementation bundle.",
            "  - `Bypass path:` `N/A (why=follow-up scaffold only)`",
            "",
            "## Assumptions / risks",
            "- Assumption: promoted backlog metadata is enough to open a bounded Architect draft without placeholder future plan paths.",
            "- Risk: if the backlog row actually mixes multiple topics, Planner/Coder must not implement straight from this stub without narrowing the plan first.",
            "",
            "## Notes for Coder",
            "- If the promoted summary is too broad, stop and push the plan through normal Architect/Planner narrowing instead of guessing the target bundle here.",
            "- Keep `code_draft_meta.targets` honest: `UNCONFIRMED` is allowed only at seed stage and must be reconciled before `Ready for Review`.",
            "",
            "## Review stamps (append-only)",
            f"- [{_now_local()}] (Promote) Seed stub created from `{source_rel}:{item.line_no}`; exact targets still intentionally `UNCONFIRMED`.",
            "",
        ]
    )


def _promoted_body(item: common.FollowupItem, plan_rel: str) -> str:
    updated = common.upsert_field(item.body, "status", "promoted")
    return common.upsert_field(updated, "plan", f"`{plan_rel}`")


def _find_v2_item(
    project_root: Path,
    file_arg: str,
    item_id: str,
) -> tuple[common.FollowupFile, common.FollowupItem]:
    """Resolve one V2 row by its durable identity, never by mutable line alone."""

    inventory = _require_clean_followups_inventory(project_root)
    source_path = common.resolve_followup_path(project_root, file_arg)
    if not source_path.exists():
        raise V2PromotionError(f"Missing follow-ups file: {file_arg}")
    try:
        rel_path = source_path.absolute().relative_to(project_root.absolute()).as_posix()
    except ValueError as exc:
        raise V2PromotionError(f"Follow-ups source is outside project root: {file_arg}") from exc
    followup = inventory.valid_v2.get(rel_path)
    if followup is None:
        raise V2PromotionError("V2 prepare/finalize requires a lint-green followups.v2 source carrier")
    matches = [item for item in followup.items if item.item_id == item_id]
    if len(matches) != 1:
        raise V2PromotionError(f"Expected exactly one V2 item_id={item_id!r} in {followup.rel_path}")
    return followup, matches[0]


def _require_v2_open(item: common.FollowupItem, project_root: Path) -> dict[str, object]:
    findings = common.lint_v2_item(item, project_root)
    if findings:
        raise V2PromotionError("V2 source row is not lint-green: " + "; ".join(f.code for f in findings))
    payload = common.v2_row_payload(item)
    if payload["status"] != "open" or any(
        payload[field] is not None
        for field in ("plan", "disposition_kind", "disposition_ref", "disposition_commit_oid")
    ):
        raise V2PromotionError(
            "V2 prepare/finalize only accepts strict open rows with null plan/disposition fields"
        )
    return payload


def _render_v2_plan(
    *,
    plan_rel: str,
    draft_rel: str,
    item: common.FollowupItem,
) -> str:
    """Create the Commit-A input without mutating the external row."""

    source_ref = common.normalize_source_ref(item.source_ref)
    assert source_ref is not None and item.item_id is not None
    meta = {
        "plan_meta": {
            "cluster": item.cluster or "process",
            "tags": list(item.tags),
            "required_manager_mode": "either",
            "wave_family": None,
            "phase_overlay": None,
            "phase_state": None,
            "parent": None,
            "next_plans": [],
            "depends_on": [],
            "promoted_from": {
                "authority_note": "derived_read_only",
                "source_ref": source_ref,
                "item_id": item.item_id,
            },
            "queue_activation": {
                "state": "n/a",
                "source_ref": f"{source_ref}#{item.item_id}",
                "reason": "V2 promotion prepare is deliberately out of queue until a normal plan intake admits it.",
            },
            "scope_expansion": None,
            "canon_updates": [],
        }
    }
    return "\n".join(
        [
            f"# Plan: {item.summary}",
            "",
            f"**Date:** {_now_local()}",
            "**Stage:** Stage 1",
            f"**Priority:** {item.priority}",
            "**Plan type:** dev",
            "**Status:** Architect initial draft",
            "**Schema version:** plan.v2",
            "",
            "**Handoff statuses (кто ставит):**",
            "- `Ready for Planner` — Architect",
            "- `Ready for Coder` — Planner",
            "- `Ready for Review` — Coder",
            "- `Ready for Arch review` — Reviewer",
            "- `Done` — Architect",
            "",
            "## Meta (machine-readable JSON)",
            "```json",
            json.dumps(meta, ensure_ascii=False, indent=2),
            "```",
            "",
            "## Plan provenance / session context",
            "- Relation: `continued-here`",
            "- Thread ID: `N/A (why=V2 promotion helper has no session identity)`",
            "- Parent thread ID: `N/A (why=external follow-up row is the source carrier)`",
            "- Session SID: `N/A (why=not exposed)`",
            "- Launch surface: `unknown (why=operator command)`",
            "- Captured from: `manual-owner`",
            "- Captured at: `N/A (why=Commit-A timestamp is Git authority)`",
            "",
            "## Documentation impact / provenance",
            f"- Source docs used: `{source_ref}`",
            f"- Synchronous doc/registry targets: `{plan_rel}`, `{draft_rel}`",
            "- Post-merge canon updates: `N/A (why=prepare only)`",
            "- Deferred documentation follow-ups: `N/A (why=source row remains authoritative)`",
            f"- Provenance refs: `{source_ref}#{item.item_id}`",
            "",
            "## Problem",
            f"- External V2 follow-up `{item.item_id}` needs a normal bounded plan intake.",
            "",
            "## Solution (high level)",
            "- Этот prepare создаёт только source-bound plan/draft artifacts. До отдельного Commit A и finalize source row остаётся `open` и не получает plan/disposition fields.",
            "",
            "## Scope",
            "- Создать честный source-bound scaffold для следующего Architect/Planner intake.",
            "",
            "## Out of scope",
            "- Queue activation, terminal-row rewrite и auto-finalize.",
            "",
            "## Follow-ups (deferred)",
            f"- Durable source row: `{source_ref}#{item.item_id}` (external authority; no copied disposition).",
            "",
            "## Acceptance criteria / DoD",
            "- [ ] Commit A materializes this plan and linked code draft without changing the external V2 row.",
            "- [ ] A separate finalize operation proves Commit A/blob and CAS-promotes exactly the source tuple.",
            "",
            "## Tests",
            "### Что написать / поправить",
            "- `N/A (why=prepare scaffold only; normal Planner intake supplies exact test matrix)`",
            "",
            "### Что прогнать",
            f"- `python3 -B scripts/plan_lint.py {plan_rel}` after normal intake completes the scaffold.",
            "",
            "## Commands",
            "- `git add <prepared plan and draft>; git commit` (Commit A before V2 finalize).",
            "",
            "## Verification rerun / exec handoff",
            "- Mode: fresh-exec",
            "- Context source: external V2 follow-up row + Commit A",
            "- Prompt: `Validate source-bound promotion artifacts before finalizing the V2 row.`",
            "",
            "## Evidence (chronological, append-only)",
            f"- [{_now_local()}] (V2 prepare) Generated source-bound artifacts from `{source_ref}#{item.item_id}`; external row intentionally remains strict open.",
            "",
            "## Review artifacts",
            f"- Code review (primary): `docs/code_reviews/{Path(plan_rel).stem}.md`",
            "",
            "## Q&A log (chronological, append-only)",
            "",
            "### Architect Q&A",
            "- NO QUESTIONS (prepare is mechanical and does not make disposition decisions).",
            "",
        ]
    )


def _render_v2_code_draft(
    *,
    plan_rel: str,
    item: common.FollowupItem,
    author_role: str,
) -> str:
    source_ref = common.normalize_source_ref(item.source_ref)
    assert source_ref is not None and item.item_id is not None
    payload = {
        "code_draft_meta": {
            "plan": plan_rel,
            "cluster": item.cluster or "process",
            "targets": [],
            "promotion_source": {"source_ref": source_ref, "item_id": item.item_id},
        }
    }
    return "\n".join(
        [
            f"# Code draft: {item.summary}",
            "",
            f"**Date:** {_now_local()}",
            f"**Cluster:** {item.cluster or 'process'}",
            f"**Related plan:** `{plan_rel}`",
            f"**Author role:** {author_role}",
            "**Status:** draft",
            "",
            "## Meta (machine-readable JSON)",
            "```json",
            json.dumps(payload, ensure_ascii=False, indent=2),
            "```",
            "",
            "## Purpose",
            f"Commit-A promotion scaffold from V2 source `{source_ref}#{item.item_id}`. Planner intake owns exact targets.",
            "",
            "## Targeted changes (by file)",
            "- `N/A (why=prepare does not invent implementation targets)`",
            "",
            "## Notes for Coder",
            "- Do not treat this seed as an authority to update the source V2 row; only `followups_apply.py` may write its disposition.",
            "",
        ]
    )


def _read_json(path: str) -> dict[str, object]:
    try:
        raw = sys.stdin.buffer.read() if path == "-" else Path(path).read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise V2PromotionError(f"Cannot read frozen promotion manifest: {exc}") from exc
    if not isinstance(value, dict):
        raise V2PromotionError("Frozen promotion manifest root must be an object")
    return value


def _reachable_commit(root: Path, raw_oid: str) -> str:
    probe = _git(root, "rev-parse", f"{raw_oid}^{{commit}}")
    if probe.returncode != 0:
        raise V2PromotionError("Commit A is not a reachable commit object")
    commit_oid = probe.stdout.decode("utf-8", errors="replace").strip()
    ancestor = _git(root, "merge-base", "--is-ancestor", commit_oid, "HEAD")
    if ancestor.returncode != 0:
        raise V2PromotionError("Commit A must be reachable from current HEAD before finalize")
    return commit_oid


def _commit_blob(root: Path, commit_oid: str, rel_path: str) -> str:
    probe = _git(root, "rev-parse", f"{commit_oid}:{rel_path}")
    if probe.returncode != 0:
        raise V2PromotionError("Commit A does not materialize the declared target plan path")
    blob_oid = probe.stdout.decode("utf-8", errors="replace").strip()
    if not common.GIT_OID_RE.fullmatch(blob_oid):
        raise V2PromotionError("Commit A target plan blob has an invalid Git OID")
    return blob_oid


def _v2_payload(
    *,
    project_root: Path,
    args: argparse.Namespace,
) -> tuple[common.FollowupFile, common.FollowupItem, str, str]:
    if not args.item_id:
        raise V2PromotionError("V2 prepare/finalize requires --item-id (line numbers are not durable identity)")
    followup, item = _find_v2_item(project_root, args.file, args.item_id)
    plan_rel = _resolve_rel_path(project_root, args.plan_path)
    draft_rel = _resolve_rel_path(project_root, args.code_draft_path) if args.code_draft_path else _derive_code_draft_rel(plan_rel)
    if not plan_rel.startswith("docs/plans/") or common.is_placeholder_plan(plan_rel):
        raise V2PromotionError("--plan-path must be one real docs/plans/*.md path")
    if not draft_rel.startswith("docs/code_drafts/"):
        raise V2PromotionError("--code-draft-path must live under docs/code_drafts/")
    return followup, item, plan_rel, draft_rel


def _run_v2_prepare(
    project_root: Path,
    args: argparse.Namespace,
    *,
    context: ContractContext | None = None,
) -> dict[str, object]:
    writer_context = _promotion_context(project_root, context)
    followup, item, plan_rel, draft_rel = _v2_payload(project_root=project_root, args=args)
    source_payload = _require_v2_open(item, project_root)
    author_role = _normalize_role(args.author_role)
    plan_path = project_root / plan_rel
    draft_path = project_root / draft_rel
    if args.apply and (plan_path.exists() or draft_path.exists()):
        raise V2PromotionError("V2 prepare refuses to overwrite an existing Commit-A plan or draft")
    payload = {
        "schema_version": "followups_promote_prepare.v2",
        "state": "prepared" if args.apply else "preflight",
        "source": {
            "followup_path": followup.rel_path,
            "source_ref": source_payload["source_ref"],
            "item_id": source_payload["item_id"],
            "row_digest": common.v2_row_digest(source_payload),
        },
        "plan_path": plan_rel,
        "code_draft_path": draft_rel,
        "queue_activation_state": "n/a",
        "row_state": "open",
    }
    if args.apply:
        _validate_promotion_effect(writer_context)
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        _validate_promotion_effect(writer_context)
        draft_path.parent.mkdir(parents=True, exist_ok=True)
        _validate_promotion_effect(writer_context)
        plan_path.write_text(_render_v2_plan(plan_rel=plan_rel, draft_rel=draft_rel, item=item), encoding="utf-8")
        _validate_promotion_effect(writer_context)
        draft_path.write_text(_render_v2_code_draft(plan_rel=plan_rel, item=item, author_role=author_role), encoding="utf-8")
    return payload


def _run_v2_finalize(
    project_root: Path,
    args: argparse.Namespace,
    *,
    context: ContractContext | None = None,
) -> dict[str, object]:
    writer_context = _promotion_context(project_root, context)
    if not args.frozen_manifest or not args.commit_oid:
        raise V2PromotionError("V2 finalize requires --frozen-manifest and --commit-oid")
    followup, item, plan_rel, _draft_rel = _v2_payload(project_root=project_root, args=args)
    item_findings = common.lint_v2_item(item, project_root)
    if item_findings:
        raise V2PromotionError("V2 source row is not lint-green: " + "; ".join(f.code for f in item_findings))
    current_payload = common.v2_row_payload(item)
    manifest = _read_json(args.frozen_manifest)
    try:
        frozen, rows = followups_apply.load_frozen_manifest(manifest)
    except followups_apply.ApplyError as exc:
        raise V2PromotionError(f"Frozen promotion manifest is invalid: {exc}") from exc
    if list(frozen.get("declaration_roles") or []) != list(followups_capture.REQUIRED_ROLES):
        raise V2PromotionError("V2 finalize requires the complete ordered four-role frozen declaration union")
    source_ref = str(current_payload["source_ref"])
    item_id = str(current_payload["item_id"])
    matching = [row for row in rows if row.tuple == (source_ref, item_id)]
    if len(matching) != 1 or len(rows) != 1:
        raise V2PromotionError("V2 finalize may mutate exactly one frozen tuple")
    row = matching[0]
    desired = row.payload
    commit_oid = _reachable_commit(project_root, args.commit_oid)
    if (
        desired.get("status") != "promoted"
        or desired.get("plan") != plan_rel
        or desired.get("disposition_kind") != "promoted_plan"
        or desired.get("disposition_ref") != plan_rel
        or desired.get("disposition_commit_oid") != commit_oid
    ):
        raise V2PromotionError("Frozen row is not the exact Commit-A-bound promoted disposition")
    expected_digests = frozen.get("expected_current_row_digests")
    tuple_key = f"{source_ref}\u0000{item_id}"
    current_digest = common.v2_row_digest(current_payload)
    if current_digest == row.digest:
        # A byte-identical retry after the first CAS write is intentionally
        # idempotent.  The writer will independently recheck this condition.
        retry = True
    else:
        retry = False
        _require_v2_open(item, project_root)
        if not isinstance(expected_digests, dict) or expected_digests.get(tuple_key) != current_digest:
            raise V2PromotionError("Frozen finalize CAS must bind the current strict-open row digest")
    blob_oid = _commit_blob(project_root, commit_oid, plan_rel)
    if args.apply:
        _validate_promotion_effect(writer_context)
    apply_payload = followups_apply.apply_frozen_rows(project_root, manifest, mutate=args.apply)
    return {
        "schema_version": "followups_promote_finalize.v2",
        "state": apply_payload["state"],
        "source": {
            "followup_path": followup.rel_path,
            "source_ref": source_ref,
            "item_id": item_id,
            "open_row_digest": None if retry else current_digest,
            "current_row_digest": current_digest,
        },
        "commit_a": commit_oid,
        "target_plan_path": plan_rel,
        "target_plan_blob_oid": blob_oid,
        "apply": apply_payload,
    }


def main(
    argv: list[str] | None = None,
    *,
    context: ContractContext | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        prog="followups_promote",
        description="Promote one backlog row into a real dev-plan scaffold and linked code-draft stub.",
    )
    parser.add_argument("--project-root", default="", help="Repo root that owns `docs/followups/*` and `docs/plans/*`.")
    parser.add_argument("--file", required=True, help="Followups file that contains the source row.")
    parser.add_argument("--line", type=int, help="1-based legacy V1 source line (V2 uses --item-id).")
    parser.add_argument("--item-id", default="", help="Durable V2 source item_id for --prepare-v2/--finalize-v2.")
    parser.add_argument("--plan-path", required=True, help="Real plan path to create (`docs/plans/...md`).")
    parser.add_argument("--code-draft-path", default="", help="Optional explicit code draft path (`docs/code_drafts/...md`).")
    parser.add_argument("--author-role", default="Architect", help="Code draft author role: Architect|Planner|Coder.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Preview without writing files (default).")
    mode.add_argument("--apply", action="store_true", help="Write the plan, code draft, and promoted backlog row.")
    v2_phase = parser.add_mutually_exclusive_group()
    v2_phase.add_argument("--prepare-v2", action="store_true", help="Create Commit-A artifacts while leaving a strict V2 open row unchanged.")
    v2_phase.add_argument("--finalize-v2", action="store_true", help="Verify Commit A/blob and invoke the sole frozen-row writer for exactly one V2 tuple.")
    parser.add_argument("--frozen-manifest", default="", help="Manager-frozen V2 declaration union for --finalize-v2.")
    parser.add_argument("--commit-oid", default="", help="Reachable Commit A required by --finalize-v2.")
    parser.add_argument("--format", choices=("text", "json"), default="text", help="Output format.")
    args = parser.parse_args(argv)

    project_root = common.resolve_project_root(args.project_root or None)
    if args.prepare_v2 or args.finalize_v2:
        try:
            v2_payload = (
                _run_v2_prepare(project_root, args, context=context)
                if args.prepare_v2
                else _run_v2_finalize(project_root, args, context=context)
            )
        except (V2PromotionError, ValueError, OSError, authority_context.ContractAuthorityError) as exc:
            if args.format == "json":
                blocked: dict[str, object] = {"state": "blocked", "reason": str(exc)}
                if isinstance(exc, authority_context.ContractAuthorityError):
                    blocked["reason_code"] = exc.reason_code
                sys.stdout.write(json.dumps(blocked, ensure_ascii=False, sort_keys=True) + "\n")
            else:
                sys.stdout.write(f"followups_promote: BLOCKED: {exc}\n")
            return 2
        if args.format == "json":
            sys.stdout.write(json.dumps(v2_payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        else:
            sys.stdout.write(
                "\n".join(f"{key}: {value}" for key, value in v2_payload.items()) + "\n"
            )
        return 0
    if args.line is None:
        parser.error("legacy promote requires --line; V2 promote requires --prepare-v2/--finalize-v2 with --item-id")
    writer_context = _promotion_context(project_root, context)
    try:
        _reject_engaged_legacy_promotion(writer_context)
    except authority_context.ContractAuthorityError as exc:
        if args.format == "json":
            sys.stdout.write(json.dumps({"state": "blocked", "reason": str(exc), "reason_code": exc.reason_code}, ensure_ascii=False, sort_keys=True) + "\n")
        else:
            sys.stdout.write(f"followups_promote: BLOCKED: {exc}\n")
        return 2
    followup, item = _find_item(project_root, args.file, args.line)
    try:
        inventory = _require_clean_followups_inventory(project_root)
    except V2PromotionError as exc:
        raise SystemExit(str(exc)) from exc
    if followup.rel_path not in inventory.legacy_v1:
        raise SystemExit("legacy promote requires one proven followups.v1 or versionless legacy source carrier")
    if item.status in {"promoted", "handled"}:
        raise SystemExit(f"Cannot promote item already in status={item.status!r}: {followup.rel_path}:{item.line_no}")

    try:
        author_role = _normalize_role(args.author_role)
        plan_rel = _resolve_rel_path(project_root, args.plan_path)
        draft_rel = _resolve_rel_path(project_root, args.code_draft_path) if args.code_draft_path else _derive_code_draft_rel(plan_rel)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    if not plan_rel.startswith("docs/plans/"):
        raise SystemExit("--plan-path must live under `docs/plans/`.")
    if common.is_placeholder_plan(plan_rel):
        raise SystemExit("--plan-path must be a real path, not a placeholder future name.")
    if not draft_rel.startswith("docs/code_drafts/"):
        raise SystemExit("--code-draft-path must live under `docs/code_drafts/`.")

    plan_path = (project_root / plan_rel).resolve()
    draft_path = (project_root / draft_rel).resolve()
    if args.apply and plan_path.exists():
        raise SystemExit(f"Plan already exists: {plan_rel}")
    if args.apply and draft_path.exists():
        raise SystemExit(f"Code draft already exists: {draft_rel}")

    plan_text = _render_plan(plan_rel=plan_rel, draft_rel=draft_rel, source_rel=followup.rel_path, item=item)
    draft_text = _render_code_draft(plan_rel=plan_rel, source_rel=followup.rel_path, item=item, author_role=author_role)
    promoted_line = item.render_line(body=_promoted_body(item, plan_rel))

    payload = {
        "project_root": str(project_root),
        "mode": "apply" if args.apply else "dry-run",
        "source": {"file": followup.rel_path, "line": item.line_no, "summary": item.summary},
        "plan_path": plan_rel,
        "code_draft_path": draft_rel,
        "updated_line": promoted_line,
    }

    if args.apply:
        _validate_promotion_effect(writer_context)
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        _validate_promotion_effect(writer_context)
        draft_path.parent.mkdir(parents=True, exist_ok=True)
        _validate_promotion_effect(writer_context)
        plan_path.write_text(plan_text, encoding="utf-8")
        _validate_promotion_effect(writer_context)
        draft_path.write_text(draft_text, encoding="utf-8")
        replacements = {item.line_no: promoted_line}
        _validate_promotion_effect(writer_context)
        followup.path.write_text(followup.updated_text(replacements), encoding="utf-8")

    if args.format == "json":
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    else:
        sys.stdout.write(
            "\n".join(
                [
                    f"mode: {payload['mode']}",
                    f"source: {followup.rel_path}:{item.line_no}",
                    f"plan_path: {plan_rel}",
                    f"code_draft_path: {draft_rel}",
                    f"updated_line: {promoted_line}",
                ]
            )
            + "\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

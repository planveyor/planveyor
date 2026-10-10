# Upstream request packet: <TOPIC>

**Date:** YYYY-MM-DD HH:MM ±HHMM
**Origin repo:** <origin-repo>
**Owning repo:** planveyor
**Status:** open | imported | decided | superseded | cancelled
**Schema version:** upstream_request.v1

**Context links (source of truth):**
- Origin plan: `docs/plans/<origin-plan>.md`
- Trigger ref: `docs/plans/<origin-plan>.md#...`, `docs/code_reviews/<review>.md#...` or `docs/process_improvements/<file>.md#PI-NNN`
- Source import plan: `N/A (why=not imported yet)`
- Source decision ref: `N/A (why=not decided yet)`
- Source execution ref: `N/A (why=not executed yet)`

Upstream request packet = target-originated evidence handoff into `planveyor`.
It is not an execution plan, not a queue item, and not permission for `planveyor` to write sibling repo files.
An accepted decision returns to the sibling through a Planveyor contract upgrade with a notice `docs/contract_notices/<id>.json`; the notice's `sibling_actions` tell the sibling what to do, including moving the sibling's copy of this request to `decided` with `source_decision_ref` pointing at the notice.

## Meta (machine-readable JSON)
```json
{
  "upstream_request_meta": {
    "id": "YYMMDD_HHMM_origin_topic",
    "origin_repo": "<origin-repo>",
    "owning_repo": "planveyor",
    "origin_plan": "docs/plans/<origin-plan>.md",
    "trigger_ref": "docs/plans/<origin-plan>.md#...",
    "status": "open",
    "requested_source_canon_path": null,
    "source_import_plan": null,
    "source_decision_ref": null,
    "source_execution_ref": null
  }
}
```

## Request
- symptom: <target-observed process/helper/prompt symptom>
- process_gap: <shared source-side gap to evaluate in planveyor>
- suggested_fix: <bounded source-side fix or triage proposal>

## Target-Specific Facts To Filter
- `N/A (why=no target-specific facts in this request)`

## Source Import Contract
- Import creates only source-local carriers in `planveyor`: a process-improvement row or a source-local plan.
- Import does not approve the request and does not update sibling repos.
- Source decision must later write `source_decision_ref` and, if accepted, `source_execution_ref`.
- Target-originated helper/canon gaps should name the exact source-side helper/canon carrier requested and whether the target already landed a local workaround. Source import records that evidence first; when the sibling must adopt an accepted change, it arrives through a Planveyor contract upgrade with a notice `docs/contract_notices/<id>.json`.

## Stop Conditions
- Do not queue this packet path directly.
- Do not edit target repo files from source import.
- Do not copy target-local product/runtime details into shared canon without source Architect review.
- Do not treat a target-local workaround or review note as accepted `planveyor` canon until a source-local decision/execution carrier exists.

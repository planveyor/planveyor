# Rollout packet: <TOPIC>

**Date:** YYYY-MM-DD HH:MM
**Source repo:** current-consumer
**Target repo:** <target-repo>
**Target kind:** plan_adoption | mirror_sync | checker_rollout | consumer_only
**Status:** open | imported | superseded | cancelled

**Context links (source of truth):**
- Source plan: `docs/plans/<YYMMDD_HHMM>_<topic>.md`
- Related source documentation/code drafts: `docs/code_drafts/...` / `docs/reviews/...` / `N/A`
- Target import receipt: same path as target local plan by default (`docs/plans/...`) или `N/A (why=not imported yet)`
- Target local plan: same path as target import receipt by default (`docs/plans/...`) или `N/A (why=not imported yet)`

> Rollout packet = handoff artifact между repo. Это не второй execution plan и не разрешение source repo писать в sibling repo на лету.

## Meta (machine-readable JSON)
```json
{
  "packet_meta": {
    "id": "YYMMDD_HHMM_target_topic",
    "source_repo": "current-consumer",
    "source_plan": "docs/plans/<YYMMDD_HHMM>_<topic>.md",
    "source_range": "<full-base-oid>..<full-head-oid>",
    "source_revision": "<full-head-oid>",
    "source_artifacts": [
      "docs/<exact-source-artifact>.md"
    ],
    "target_repo": "<target-repo>",
    "target_kind": "plan_adoption",
    "target_writable_carriers": [
      "docs/<truthful-target-carrier>.md"
    ],
    "status": "open",
    "depends_on_packets": [],
    "queue_after_import": true,
    "suggested_target_plan_slug": "<topic_slug>",
    "target_import_receipt": null,
    "target_local_plan": null
  }
}
```

Default import contract: after target import, `packet_meta.target_import_receipt` and `packet_meta.target_local_plan` point to the same direct generated target-local adoption plan path. A `null` value means the target repo has not materialized the import/adoption plan yet. New generated plans contain exactly one literal `planveyor:rollout_packet_carrier.v1` sentinel region with `rollout_packet_import` and `rollout_packet_outcomes.v1`; each item starts as `pending` / `null`. Source `reconcile --target-root` treats only one valid matching recorded structured item with the same equal pointer pair as terminal. Prose, Markdown fences, legacy standalone `rollout_packet_import` JSON, duplicate/malformed items or carriers, and partial/split/nonmatching pointers fail closed to the existing pending/readback family.

Current-delivery identity contract: before `planveyor_post_merge_packetization_gate_recover` can accept a packet, replace every placeholder with truthful values. `source_range` is the full resolved `BASE..HEAD` OID pair, `source_revision` is that pair's full HEAD OID, and `source_artifacts` is the sorted exact source-side artifact list for that range. `target_writable_carriers` is a separate, sorted target-local structural list: never copy `source_artifacts` into it, never infer it from source paths, and never use it as proof that target import/adoption already happened. Choose `target_kind` truthfully; `mirror_sync` is not a default or recovery guess.

Source readiness contract: target-facing `planveyor_rollout_packet_inbox` / `planveyor_rollout_packet_adoption_plan` hide `git_state=untracked` source packets by default in git worktrees and expose excluded rows separately. Use `--include-untracked` only for explicit draft intake; source `query` remains full visibility and reports `git_state`.

Source-side acknowledgement contract (both commands run from the physical Planveyor root): target records its decision through `./bin/planveyor --project /absolute/path/to/consumer planveyor_rollout_packet_outcome_set --target-plan ... --packet-id ... --packet-path ... --outcome ...`, then source runs `./bin/planveyor planveyor_rollout_packet_ack` to update this source packet. `imported` requires `--target-plan docs/plans/...` and writes both `packet_meta.target_import_receipt` and `packet_meta.target_local_plan` to that same path by default, but an imported ACK alone may still derive `target_adoption_state=awaiting-target-outcome` until the generated carrier has one canonical recorded outcome. Duplicate/malformed/pending/unknown carrier data or a pointer mismatch fail close in `bucket=unproven_target_outcome`, `target_adoption_state=awaiting-target-outcome`, `target_outcome=null`. `superseded` and `cancelled` source acknowledgements still require `--reason` and leave target pointers unset unless a truthful target-local receipt path is supplied. Helper stdout, target queue hints, prose, legacy fenced import JSON and report-only target readback are not source mutation truth. Report-only labels such as `target_adoption_state=awaiting-target-import` / `awaiting-target-outcome` / `pointer-preserved` / `parked` / `adopted` / `cancelled` are derived readback fields, not accepted `packet_meta.status` or `ack --status` values.

## Source provenance
(Bounded subset only. Source packet records where the shared/source bundle was created; target-local imported plan keeps its own full `## Plan provenance / session context` after import.)
- Relation: `created-here | continued-here | manual-backfill`
- Thread ID: `UUID/handle` или `N/A (why=...)`
- Session SID: `UUID/handle` или `N/A (why=...)`
- Launch surface: `codex-desktop | codex-cli | manager-collab | manager-custom-pipeline | unknown (why=...)`
- Captured from: `env | wrapper-session-file | session-stats | manual-owner`
- Captured at: `YYYY-MM-DDTHH:MM:SSZ`
- Target import expectation: `target repo generates one direct adoption plan carrier, then records the packet decision through the selected-consumer Planveyor facade and planveyor_rollout_packet_outcome_set with exact packet id/path and one canonical outcome`

## Why target repo action exists
- Shared/source change:
- Why target repo must react:
- Why this is not safe/clean as live cross-repo write:

## Source artifacts
- `docs/<exact-source-artifact>.md`

## Target writable carriers
- `docs/<truthful-target-carrier>.md`

## Import recipe
1. Open this packet in the target repo context.
2. Materialize a target-local adoption plan as the import receipt.
3. Record `target_import_receipt` and `target_local_plan` as the same generated plan path unless this packet explicitly overrides it.
4. Put only the target-local plan into the target repo queue/manager flow.
5. From the physical Planveyor root, run `./bin/planveyor --project /absolute/path/to/consumer planveyor_rollout_packet_outcome_set --target-plan docs/plans/<target-local-plan>.md --packet-id <id> --packet-path docs/rollout_packets/<packet>.md --outcome <canonical-or-alias>`. Do not use prose, Markdown fences or manual JSON edits as authority; legacy/no-carrier, pending, duplicate, malformed and pointer-mismatch cases remain `awaiting-target-outcome`.
6. Return to the Planveyor source root and run `./bin/planveyor planveyor_rollout_packet_ack --packet docs/rollout_packets/<packet>.md --status imported --target-plan docs/plans/<target-local-plan>.md` or close as `superseded` / `cancelled` with `--reason`.

## Stop conditions / not-in-scope
- Do not write target repo files from source repo.
- Do not treat this packet as executable queue item.
- Do not start target queue before a target-local plan exists.
- Do not treat linked governance/follow-up/helper targets as landed unless their source status and review evidence prove they are materialized.
- Do not treat existing target-local workflow files, wrapper mentions, or notification-only surfaces as proof that the imported rollout is already landed; if repo-local/on-repo signal matters, say that literal-но in the packet.
- Do not treat source packet delivery, existing workflow presence, or shared CI references as proof that required-check naming / branch protection already protects merges; that closeout remains target-local until explicit owner/review evidence says otherwise.
- Do not fabricate target-local mirror carriers purely to match source layout when truthful repo-local workflow/harness/docs surfaces already cover the imported intent differently.
- Do not silently queue or import `git_state=untracked` draft packets from a target-facing inbox; use `--include-untracked` only when the target plan explicitly owns that draft intake.
- If target repo no longer needs action, close the packet as `cancelled` or `superseded` with reason.

## Adoption completion signal
- Receipt path: same as target local plan path by default
- Target local plan path:
- Local terminal condition:
- Source-side follow-up needed after import/closure: `yes | no`

## Source-side acknowledgement
- `N/A (why=packet is still open; source-side ack is written by planveyor_rollout_packet_ack)`

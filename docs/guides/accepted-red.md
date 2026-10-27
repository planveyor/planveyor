# Accepted-red and forensic capture

**English** · [Русский](accepted-red.ru.md)

This document describes the contract that `planveyor_plan_bundle` (modes `--closeout-json`, `--capture-rejected`, `--verify-rejected`, `--cleanup-rejected`), the plan Oracle, `planveyor_docs_closeout`, and the queue helper implement. The commands below run through the facade from the project root: `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" <command>`.

## When a review is "accepted red"

The plan is closed by replacement, not by a green delivery: Reviewer left open S1 blockers, and Architect accepted the scope expansion and handed the work to a successor. Oracle (`planveyor_plan_status_oracle --json`) reports such a plan as `terminal_disposition=accepted_red_supersession` when all of these conditions hold:

- `**Status:** Superseded`;
- `plan_meta.scope_expansion.state` is `architect_accepted`, and `source_ref` is `<review>#B<N>`, one of the review blockers;
- `plan_meta.next_plans` holds exactly one successor; the successor's `plan_meta.parent` points to this plan, and the successor header (before the first `##` heading) has `<review>#B<N>` references to exactly all blockers of the review;
- the `## Review artifacts` section declares exactly one review with the same name as the plan: `docs/code_reviews/<stem>.md` or `docs/doc_reviews/<stem>.md`, and there is no second such file;
- the review is red: `**Status:**` contains `❌`, there is a line `**Target:** BUNDLE=current bundle_sha256=<64 hex>`, and there is one `## S1 Blocker` section where each blocker is a `### B<N>` subsection with the fields `- Blocker ID: B<N>` and `- Current state: open`;
- the code draft `docs/code_drafts/<stem>__code_draft.md` refers to this plan in `code_draft_meta.plan` and lists non-empty `targets`.

If the plan is in `Superseded`, `scope_expansion.state=architect_accepted`, and there is one successor, but the rest does not match, Oracle still reports the plan as accepted-red, with the reason `accepted_red_carrier_invalid`, `accepted_red_review_route_invalid`, or `accepted_red_review_invalid`. A plan without these signs that already has a ref `refs/planveyor/rejected-baselines/<stem>/…` is read the same way, with `accepted_red_carrier_invalid`. For a plan that meets all the conditions, the reason (`terminal_disposition_reason`) shows the stage: `accepted_red_current_snapshot` means there is no capture yet and the rejected bytes are in place; `accepted_red_durable_capture` means the ref exists and is intact; `accepted_red_snapshot_mismatch_without_durable_ref` means there is no ref and the bytes no longer match the review; `accepted_red_snapshot_mismatch_without_valid_durable_ref` means the ref is broken.

For an accepted-red plan, Oracle always answers `delivery_green=false`, `staging_policy=forbidden`, `durable_capture_required=true`. The target bytes that Reviewer saw are evidence, not a delivery: do not stage or commit them on behalf of this plan.

## Who runs what

- Architect accepts the route: sets `architect_accepted`, creates the successor, and moves the plan to `Superseded` (`docs/tools/prompts/architect_status_driven.md`).
- A separate unfinished recovery plan carries the fix through the normal role cycle.
- The Owner runs capture, verification, and cleanup by hand. Manager and the roles do not call these modes. In a queue, the queue helper answers an accepted-red plan with `terminal_closeout_admission_rejected` and `reason_code=accepted_red_reconciliation_required`, and Manager hands the payload to the Owner (`docs/roles/manager.md`). The docs closeout of such a plan stays `blocked` until cleanup. The Owner's steps during an incident are in `docs/playbooks/manual_terminal_recovery.md`.

## Lifecycle

```zsh
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_plan_bundle --verify-rejected <SOURCE_PLAN>
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_plan_bundle --capture-rejected --recovery-plan <RECOVERY_PLAN> <SOURCE_PLAN>
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_plan_bundle --cleanup-rejected <SOURCE_PLAN>
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_plan_bundle --closeout-json <SOURCE_PLAN>
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_docs_closeout <SOURCE_PLAN> --json
```

Successful rejected-baseline lifecycle operations answer with JSON `planveyor_plan_bundle_closeout.v1` on stdout and exit code 0. A refusal from the rejected-baseline helper answers with JSON `planveyor_rejected_baseline_error.v1` with `state=blocked` and `reason_code` on stderr and exit code 2. Invocation errors, such as a missing plan, `--recovery-plan` without `--capture-rejected`, or closeout, preflight, and message options in a recovery mode, print plain text on stderr and exit with code 1.

1. **Verification** (`--verify-rejected`) only reads. While there is no capture, the answer is `recovery_state=capture_required` if the target bytes match the review, or `snapshot_mismatch_without_durable_ref` if they no longer match: then the rejected bytes cannot be saved.
2. **Capture** (`--capture-rejected`) saves the rejected bytes in Git. It requires:
   - `--recovery-plan`: a recovery plan separate from the source, not in `Done` and not in `Superseded`, with the line ``- Superseded incident plan: `<SOURCE_PLAN>`.`` and exactly one code draft of its own, `docs/code_drafts/<recovery plan stem>__code_draft.md`, whose `targets` overlap the source targets;
   - the index for the targets matches HEAD: the rejected bytes are not staged;
   - the current `bundle_sha256` of the source matches the `bundle_sha256` in the review's `**Target:**` line.

   A repeated capture with an intact ref changes nothing and returns the current state. After capture: `recovery_state=cleanup_required`.
3. **Cleanup** (`--cleanup-rejected`) returns each target to its HEAD bytes and deletes a target that is not in HEAD. It requires an intact capture, the same HEAD as at capture, a target index equal to HEAD, and targets in only two states: the rejected bytes or the HEAD bytes. So the recovery plan changes these targets only after cleanup. After cleanup: `recovery_state=completed`, `closeout_kind=accepted_red_recovered`, `bundle_ok=true`; `delivery_green` stays `false`. A repeated cleanup changes nothing.
4. **Closeout.** For an accepted-red plan, `--closeout-json` prints the same payload instead of the usual exact-bundle one; with a broken carrier it refuses with `accepted_red_closeout_invalid_carrier`. `--stage`, `--commit-ready`, and `--commit-exact` refuse with `staging_forbidden` when classification succeeds and the durable capture is not invalid; otherwise they refuse with `staging_forbidden_invalid_carrier`. `planveyor_docs_closeout` answers `completed` with `reason_code=accepted_red_recovery_completed` only after cleanup and a receipt check. Before that it answers `blocked`, usually with `accepted_red_recovery_incomplete` or an `accepted_red_*` reason. If there are no other document edits, the answer contains `final_docs_commit=no_op` with the reason `accepted_red_evidence_ref_materialized`.

After cleanup, the recovery plan may change the targets from its own code draft: the state `active_checkout_state=recovery_owned_overlap` is allowed. A change to another rejected target gives `drifted`, and the check refuses with `active_checkout_drift`.

## What is stored

Capture creates a commit whose parent is the current HEAD (`captured_parent`) and a ref `refs/planveyor/rejected-baselines/<stem>/<review_bundle_sha256>` that points to it. The commit tree is the HEAD tree with these entries written into it:

- the rejected bytes of all source targets, as Reviewer saw them;
- four routing files: the source plan, its code draft, the review, and the successor;
- `.planveyor/rejected-baselines/<stem>/<review_bundle_sha256>/manifest.json` with the schema `planveyor_rejected_baseline.v1`: the source and recovery plans, the recovery code draft and targets, the review and its `bundle_sha256`, the successor, `captured_parent`, and for each target and routing file the path, sha256, size, mode, and blob oid.

Cleanup adds a child commit with `cleanup.json` next to the manifest (schema `planveyor_rejected_baseline_cleanup.v1`: the final state of each target and a repeated check of the routing files) and moves the ref to it.

Capture and cleanup do not change HEAD, branches, or the index; only cleanup changes the working tree. The ref is published in one `git update-ref` transaction, on the condition that HEAD has not moved; otherwise the refusal is `recovery_ref_cas_conflict`.

## How it is checked

- Every read checks the whole ref again: the parent chain, the manifest, the cleanup receipt, and the target blobs. A broken ref gives `durable_capture_state=invalid`; capture and cleanup on top of it refuse with `recovery_ref_invalid`.
- The four routing files must match the copies saved at capture byte for byte. Otherwise the result is `routing_carrier_drift`: `--closeout-json` refuses, and `planveyor_docs_closeout` answers `blocked`. An edit to the successor before the docs closeout of the source also counts as drift.
- If `GIT_DIR`, `GIT_WORK_TREE`, `GIT_COMMON_DIR`, or `GIT_INDEX_FILE` is present in the helper environment, parsing refuses with `not_accepted_red`. A non-empty `GIT_REPLACE_REF_BASE`, Git replace refs, or `info/grafts` makes durable-ref validation invalid: capture and cleanup refuse with `recovery_ref_invalid`, and staging refuses with `staging_forbidden_invalid_carrier`. The public facade starts its child through `env -i` and does not pass these Git variables.
- Workarounds for historical cases (snapshot bridge and route rebind) are not set in the neutral engine: capture is possible only while the current target bytes match the review.

## Common refusals

| `reason_code` | What it means | What to do |
|---|---|---|
| `not_accepted_red`, `routing_contract_invalid` | the accepted-red conditions do not hold, the carriers are incomplete, or the helper environment contains `GIT_DIR`, `GIT_WORK_TREE`, `GIT_COMMON_DIR`, or `GIT_INDEX_FILE` | check the plan, the successor, the code draft, and the review against the first section; remove any listed authority override from the helper environment |
| `recovery_plan_invalid` | the recovery plan does not fit | fix its source line, status, or code draft |
| `rejected_target_staged` | the rejected targets are staged | remove them from the index |
| `snapshot_mismatch` | the target bytes no longer match the review | capture is not possible; the decision belongs to the Owner |
| `recovery_ref_cas_conflict` | the ref transaction failed, for example because HEAD or the ref changed after validation | read `--verify-rejected`, then repeat with a stable HEAD and ref; an intact ref found before capture is reused, and an invalid one gives `recovery_ref_invalid` |
| `capture_required` | cleanup without capture | run capture first |
| `head_drift` | HEAD changed after capture | run cleanup on the same HEAD as capture (`captured_parent`) |
| `rejected_target_drift` | a target matches neither the rejected bytes nor HEAD | sort out the changes to this target |
| `routing_carrier_drift` | a routing file changed after capture | restore its bytes from the capture commit |
| `staging_forbidden`, `staging_forbidden_invalid_carrier` | an attempt to stage or commit an accepted-red plan; the second code means classification failed or the durable capture is invalid | do not stage; resolve the invalid carrier when reported, then close through cleanup |

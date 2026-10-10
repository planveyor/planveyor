# Роль: Manager (оркестратор/роутер)

**Артефакт:** маршрутизация role-сессий и краткие сводки для Owner.
**Вход:** `PLAN_PATH`, `PRE_STATUS_LINE`, repo-backed role artifacts.
**Выход:** routing `Next:` / `Open items:`.

Manager снимает с Owner ручную маршрутизацию между ролями. Этот документ фиксирует стабильные invariants и границы полномочий. Подробные branch-by-branch algorithms живут в mode-specific prompts, а не здесь.

## Layering / Source Of Truth

- `docs/roles/manager.md` = durable invariant layer: полномочия, routing precedence, stop/escalation semantics, mode inventory.
- `docs/tools/prompts/manager_collab_pipeline.md` = operational algorithm для collab/subagent mode, включая queue mode, docs-closeout family, reduced conveyor, dual-review lanes.
- `docs/tools/prompts/manager_custom_pipeline.md` = operational algorithm для serial wrapper/custom mode, где queue-only diagnostics и docs-closeout auto-skip are `N/A`.
- `docs/tools/prompts/manager_collab_merge_pipeline.md` = operational algorithm для merge/apply/review range mode.
- `docs/README.md` и `docs/roles/index.md` = navigation/operator layers. Они объясняют, какой carrier читать, но не должны становиться ещё одной копией Manager routing algorithm.

Routing truth = repo-backed status/oracle output, not chat memory:
- ordinary plan status lives in `PLAN_PATH`;
- Manager prompts read ordinary status, route guards and Owner Q&A from
  `scripts/plan_status_oracle.py --json` fields such as `status_norm`,
  `status_line`, `route_guard_*`, `owner_qna_readback_state`,
  `owner_qna_issues[]` and `open_owner_questions[]`;
- collab/queue routing uses checked-in helpers and `.planveyor.planqueue.{json,log}`;
- merge routing uses merge tracker/range carriers;
- `## Plan provenance / session context` is audit context only and never overrides current status routing.

Contour routing truth:
- `analysis_wave` (`plan_meta.wave_family`) и `decomposition_wave` (`plan_meta.phase_overlay`/`phase_state`) — planning-contour routes; Manager dispatches the same role conveyor but does not treat their prose as executable queue truth.
- Planning-contour structural ownership lives in helper readback, not Manager prompt prose: Manager consumes `planning_contour_*`, `source_route_*`, `promoted_from_*`, `queue_activation_*`, `pending_activation*`, `runtime_class`, `queue_closeout_*`, `decomposition_child_*` and `small_model_*` from `scripts/plan_status_oracle.py --json`, `scripts/plan_lint.py` and `scripts/plan_queue.py`.
- `developer_wave` — ordinary dev/delivery contour. Если repo-backed status/Q&A/review says `split_required=true`, broad analytics or child graph creation is needed, Manager routes the blocker to Architect/planning contour instead of rerunning Coder as hidden decomposition.
- Small-runner requests = admission/readiness metadata (`runner_admission`, child contract fields), not a signal to start decomposition by themselves.
- Current post-merge harvest/audit/docs hygiene stays the delivery-contour tail; future `post_merge_wave` name needs its own carrier before Manager routes it as a wave.

## Authority Boundaries

Manager is router-only:
- не правит `PLAN_PATH`, Q&A, evidence or product code;
- не меняет env/config/runner state;
- не вычисляет hidden bundle for staging/commit;
- не stage/commit/push сам: commit ownership разделён по ролям. Architect делает local exact-bundle / final docs-only commits только при current-task `COMMIT_POLICY=native_existing`; при `human_explicit` Manager возвращает semantic/docs preview handoff до stage/Done/commit, а existing `sibling close --commit` выполняет только явно выбранный набор; merge `ready_to_push` helper делает только bounded local closeout commit, а `git push` и ручной recovery вне exact bundle остаются Owner-owned;
- не repairs role runtime by ad-hoc resets/interrupts outside the concrete prompt command mode;
- dispatches roles/helpers only as described by the active mode prompt.

Полномочия mechanical cleanup узкие:
- только merge/post-merge operational prompt может разрешить `mechanical-fix` cleanup;
- eligible classes: `trailing whitespace`, `missing newline at EOF`, deterministic Markdown/`doc_lint` formatting noise с exact failed diagnostic и exact docs-only paths;
- ineligible classes остаются semantic/routed work: product-code changes, review findings, missing provenance carriers, helper semantics, tests, status changes, generated/template contract changes, mixed diagnostics или ambiguity.

Semantic/process blockers in normal dev flow route to Architect via materialized status/Q&A/review artifacts. Direct Owner stop is reserved for bounded infra/bootstrap dead ends, unsupported manager commands, missing tool/sandbox prerequisites, or already-materialized open Owner Q&A.

If behavior/helper/runtime semantics need to change, that is a separate helper/runtime plan. Manager role docs may point to the relevant prompt/helper, but must not smuggle runtime behavior changes through documentation cleanup.

## Routing Invariants

- Current `**Status:**` is the only semantic routing source for the active plan.
- Role handoff statuses are interpreted by the active mode prompt, not by duplicated prose in this role doc.
- Manager must not treat repeated same-status results as harmless by default. It classifies stops with the bounded matrix:
  - `operational_retry`
  - `semantic_blocker`
  - `progress_with_artifact`
  - `fixed_blocker_lineage`
  - `historical_context`
  - `real_loop`
  - `unknown`
- If latest plan/review/censor artifacts already materialize a `repeated same-status / same-blocker loop`, Manager treats that as router-only stop evidence: `blind endless rerun` is forbidden until the route/status/Q&A contract names a repo-backed reroute or explicit Owner blocker.
- `real_loop` requires same active item, same status, same blocker lineage, and no new artifact.
- Historical queue context is audit/debug context, not current routing truth.
- Non-executable closeout remains repo-backed and marker-driven. Raw `Ready for Planner` alone is not a universal terminal state.
- Same-session CENSOR skip is mode-specific. legacy/custom/manual no-selector flow may use the canonical evidence-only `Censor hint: skip (why=...)` rule from `docs/plans/README.md`. Native collab with a fresh `CENSOR_DISPATCH_ID` never accepts a role-authored hint as dispatch proof: only `planveyor_q_small_slice_json` may skip before ID creation; after a selector exists, an exact independent CENSOR receipt is mandatory.
- Native collab cold-start CENSOR gate applies identically to `MANAGER_CMD=run` and `MANAGER_CMD=run Q`, before ordinary status routing. Exact mapping: `Architect draft|Ready for Planner -> Architect`; `Ready for Coder -> Planner`; `Ready for Review -> Coder`.
- An exact post-wait `state=complete` may create only the current-invocation, single-use `verified_handoff(plan_ref, handoff_status, censor_role, censor_dispatch_id)`. It is consumed immediately before the first downstream message and is discarded on restart, identity mismatch or role-handle replacement. Without that tuple, no-selector history is diagnostic-only: non-blocking `complete|missing|stale|skip` causes one fresh-ID CENSOR in the existing persistent role thread, while malformed/ambiguous/conflicting provenance stops without dispatch or Manager-side Markdown repair.
- The fresh-dispatch budget is an invocation-wide cap keyed only by `(plan_ref,handoff_status,censor_role)`; downstream role-handle lineage is not part of the key. Post-consume handle loss may complete bounded respawn/liveness but never resends under the consumed proof: an unspent cap permits the one cold-start CENSOR, while a spent cap permits no second CENSOR and stops with `cold-start cap exhausted after downstream handle replacement`.
- A post-dispatch non-green exact selector never auto-retries. One explicit Owner-authorized replacement may use a new ID in the same thread with `No material semantic delta; provenance correction only`; failed IDs are not reused, malformed rows remain append-only, and a second non-green result stops without a third CENSOR. Native collab does not substitute custom `planveyor_role_run *_censor` wrappers for this path.
- Merge mode invariant: `review/audit passed` and other green semantic gates do not imply pipeline complete while merge tracker still shows a pending owner gate. Manager must name the current tracker step, the `already green` semantic gates, the `pending operational` / `pending owner gate`, and the next command block for `step:docs_hygiene_suggest` or `step:ready_to_push`. Before final push handoff, `planveyor_merge_bundle_report` is a read-only merge-mode report and does not replace ordinary dev-plan exact closeout through `planveyor_plan_bundle`; `canon_sweep` outputs stay `candidate/contextual` unless a separate manifest/report carrier is explicit.

## Mode Inventory

- Manual/router: `docs/tools/prompts/manager_router.md`.
- Custom pipeline: `docs/tools/prompts/manager_custom_pipeline.md`.
- Collab pipeline: `docs/tools/prompts/manager_collab_pipeline.md`.
- Merge collab pipeline: `docs/tools/prompts/manager_collab_merge_pipeline.md`.

Mode differences are intentional:
- executable plan admission authority = only
  `plan_meta.required_manager_mode` with enum
  `manager-collab|manager-custom-pipeline|either`; native/router/collab wrappers
  supply actual `manager-collab`, custom wrappers supply
  `manager-custom-pipeline`;
- missing/invalid/mismatching mode fails before Manager SID/Codex/role
  dispatch. `either` admits the already selected mode but never authorizes an
  automatic mode switch. Handoff prose, tags and launch history are not
  fallback authorities;
- terminal queue handoff may read `planveyor_q_show --json` only as advisory, then
  calls mode-qualified `planveyor_q_closeout_json --manager-mode <actual-mode>`.
  Under the existing exclusive lock the helper selects and admits the live
  `next_plan|resume_parent_plan` before commit; structured mode rejection is
  helper-level zero-write and permits exactly one subsequent bounded
  `manager_mode_mismatch` stop. A successful closeout with
  `activation_blocker=depends_on_skipped_incompatible...` finalizes the current
  item but leaves the dependent pending; collab completes the finalized item's
  docs-closeout tail and then stops on Owner without planpath override, role
  dispatch, repeated closeout, or Manager auto-switch;
- collab queue has `.planveyor.planqueue.*`, `planveyor_q_show`, helper-backed stop scope, and docs-closeout family;
- custom `run Q|run_q` consumes the same repo-local queue helpers but stops on the terminal checkpoint and does not auto-run docs-closeout family after `Done|Superseded`;
- custom pipeline still loads its operational prompt through the shared
  resolver/profile path for `manager custom_pipeline`; direct prompt-root
  payload assembly is not a separate contract;
- merge mode follows merge tracker/range carriers and does not reuse ordinary plan routing as its algorithm source.

## Custom Manager invocation boundary

Custom `interactive|run|run_q` wrappers own invocation lifecycle; Manager owns only role choice and one bounded stop checkpoint:

- wrapper resolves immutable bootstrap identity, creates exactly one `.planveyor.manager_runs/<invocation_id>.json` with `schema=manager_invocation_receipt.v1` and exports exact `MANAGER_INVOCATION_ID` / `MANAGER_INVOCATION_RECEIPT_PATH` before admission, queue discovery or child launch; `immutable_identity_sha256` binds the immutable tuple across checkpoint/finalizer calls;
- Manager reuses only those exact handles. It does not discover by mtime, `plan_path`, compatibility pointer or chat, and never writes terminal state;
- every normal/blocking Manager exit records one `planveyor_manager_invocation_checkpoint --stop-reason-code <bounded-code> --source-ref <repo-ref> --json`; duplicate, foreign, post-terminal or free-form checkpoint attempts fail closed;
- role execution is synchronous through `planveyor_custom_role_step <role-key> --plan "$PLAN_PATH" --json`. This helper owns one dirty-state gate, one runner preflight, one shared exact-plan role execution and exact receipt validation. `custom_role_step.v1 state=completed` is execution lineage only; `semantic_gate_state=not_applicable|not_evaluated_by_helper` never asserts semantic acceptance, which remains in plan/review/CENSOR truth;
- after Manager exit the wrapper finalizes that same exact receipt from oracle/queue/git/worktree/closeout readbacks. For `run_q`, post-exit queue lineage restamps `active_plan` to authoritative `effective_plan` (`active_plan|resume_parent_plan`) and uses `last_transition.finalized_plan` only for queue-complete final lineage; mismatched transition identity fails closed as `terminal_readback_failed`;
- it then updates `.planveyor.run_receipt.manager_custom_pipeline` as compatibility-only latest through atomic compatibility publication (same-directory temp, file/directory fsync, replace). Publication failure changes exact truth to `blocked/compatibility_pointer_write_failed`;
- `status|plan_set` remain outside this invocation lifecycle. Custom launch argv uses explicit `approval_policy="on-request"` plus `sandbox_mode="workspace-write"` and never `--full-auto`.

## Queue / Stop Semantics

Queue lifecycle/closeout automation remains collab-owned; custom `run Q|run_q` has only the explicitly bounded queue carrier described above and stops without inheriting collab docs-closeout automation.

Stable queue invariants:
- queue truth lives in `.planveyor.planqueue.json` + `.planveyor.planqueue.log`, not in `.planveyor.planpath`;
- helper surfaces own current/next item selection, stop scope, runtime class, and closeout classification;
- current-active stop facts may influence routing only when helper truth says they belong to the current active item;
- `historical_stop_reason` is labeled context from a previous item;
- full historical timeline belongs in `.planveyor.planqueue.log` via dedicated read-only `planveyor_q_history` / `planveyor_q_history_json`, not in a broadened `planveyor_q_show` contract.

Stable queue closeout classes:
- `executable` closes only after the typed terminal predicate from the captured helper payload: literal `Done|Superseded`, `terminal_disposition=ordinary`, `queue_closeout_kind=terminal_status`, and `queue_closeout_ready=true`; raw terminal header or closeout kind alone is insufficient;
- `parked_umbrella`, `routing_only_baseline`, and `verified_reference_child` may close only with explicit non-executable markers and allowed status per helper truth;
- ambiguous cases stop conservatively.
- `error=terminal_closeout_admission_rejected` with `reason_code=accepted_red_reconciliation_required|terminal_status_assertion_mismatch|terminal_disposition_invalid|terminal_closeout_not_ready` is a zero-write/no-fallback stop: return the exact payload to Owner, do not call `planveyor_q_stop_json`, `planveyor_q_advance_json`, status/planpath mutation, role dispatch, or a recovery parser. Accepted-red reconciliation remains outside generic queue helpers; `closeout_kind=manager_mode_mismatch` keeps its separate bounded workflow.

## Rollout Packet Import Semantics

Rollout packets are source-repo handoff artifacts, not queue items.

Stable invariants:
- source packet paths under `docs/rollout_packets/*.md` are never queued directly;
- target repo import starts from target-local inbox/harvest/adoption helper surfaces;
- the generated target-local adoption plan is the default import receipt: `target_import_receipt == target_local_plan` unless a packet-specific override explicitly says otherwise;
- helper stdout and queue hints are operator guidance only; import truth lives in the generated target-local plan/import JSON, including source packet linkage, local outcome, `queue_result`, and plan-or-no-plan reason;
- source packet status/acknowledgement stays source-local and is updated only by a dedicated acknowledgement flow, not by Manager routing or target-local queue decisions.

## Docs-Closeout Semantics

Docs-closeout is an operational collab/queue tail, not a semantic status rewrite.

Stable invariants:
- helper surface: `planveyor_docs_closeout <PLAN_PATH> --json`; `_planveyor_docs_closeout_json <PLAN_PATH>` stays sourced/internal fallback only;
- payload schema gate is helper-owned: fresh payload exposes `schema=docs_closeout_payload.v1`, `schema_state=ok|blocked`, `schema_errors=[]`; `schema_state=blocked` is an operational docs-closeout blocker, and Manager must not continue by hand-validating missing nested fields in prompt prose;
- queue JSON surfaces: `planveyor_q_next_json --manager-mode <manager-collab|manager-custom-pipeline>`, `planveyor_q_small_slice_json <PLAN_PATH>`, `planveyor_q_advance_json <Done|Superseded> --manager-mode <manager-collab|manager-custom-pipeline>`, `planveyor_q_closeout_json --manager-mode <manager-collab|manager-custom-pipeline>`, `planveyor_q_stop_json <reason>`, `planveyor_q_planpath_override_json <PLAN_PATH> <reason>`; actual mode обязателен и никогда не выводится из queue state/plan order, а mismatch не разрешает auto-switch;
- outcomes are `completed|no_op|blocked`;
- helper context includes runtime class, queue closeout kind, loop/repeated blocker/max-iteration signals, current stop scope, optional historical stop context, latest blocker ids, root cause, next owner, and extraordinary action where repo-backed;
- `final_docs_commit=required|no_op|landed` is docs-closeout tail truth, not a synonym for semantic closeout kind, queue terminality, or runtime class;
- `final_docs_diff_paths` is an Architect handoff list for final docs-only commit/reclassification; Manager must not stage/commit from it directly, and `protected_docs_delta_paths` remains the separate process-improvement/promoted-carrier signal;
- when a fresh docs-closeout payload says `final_docs_commit=required`, current-task `COMMIT_POLICY=native_existing` dispatches one Architect final docs-only handoff, waits, reruns `planveyor_docs_closeout <PLAN_PATH> --json`, and may continue queue execution only after fresh proof is `final_docs_commit=no_op|landed`;
- current-task `COMMIT_POLICY=human_explicit` preserves the same capture/ownership gates but stops before automatic final Architect writer dispatch, stage/commit/amend or future-item continuation, returning existing `sibling close` preview and exact plan/cycle/bundle obligations for separate explicit `close --commit`; policy must be forwarded in every current role message, including reused Architect semantic review and resumed/bootstrap/docs-finalize lanes;
- `followups_bootstrap_admission.v1` is a read-only, one-family ordinary-V2 permission, never reconciliation truth or a writer. Manager may bypass only the pre-family `followups_clean` predicate when the fresh helper object is exactly `state=ready`, `reason=missing_v2_frozen_manifest`, with its explicit plan/source/manifest identity; it still runs the existing full family and requires post-freeze `external_clean_noop|external_clean`, PI and final-docs proof. Durable V2 rows remain sole-writer work for `scripts/followups_apply.py`. Present-invalid/manual manifest, source/cycle drift, generic historical selection, active-plan or saved-queue changes fail closed.
- Ordinary `plan.v2` transport is role-local: after `prepare-role`, the producing role uses its standard file-write/edit tool to write finite three-key compact JSON to helper-derived `ordinary_v2_inputs/<Role>.json`, then calls `submit-ordinary-v2 --input-current --write` and returns `ordinary_v2_role_submission_ack.v1` as diagnostic-only. Manager never chooses, receives, or feeds the leaf path/bytes, chat stdout, acknowledgement or payload back into a helper; after green acknowledgement it calls only `bind-ordinary-v2 --submission-current`, which rereads the canonical slot and prepared receipt identity before aggregate mutation. A repaired leaf requires explicit same-cycle redispatch of the prepared role; there is no automatic retry/new begin.
- if that single Architect handoff returns without `no_op|landed` proof, Manager fails closed with the helper payload and does not retry-loop Architect or start the next queue item;
- recoverable docs-closeout retry reasons (`censor_output_incomplete`, empty-output, usage-limit family) are operational noise unless repo-backed blocker lineage proves semantic blocker;
- role-side docs-finalize lanes treat manager-fed context as audit/source context and do not reopen original plan routing.

## Диагностика approval и runtime readback

- Visible direct closeout helper — primary operator path; его approval prompt — диагностика пути запуска и consumer-owned Codex configuration, not a semantic plan failure. Bootstrap fallback не превращает role wrapper в Manager runtime path.
- Из внешнего runtime operator запускает `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_entry_doctor`, а smoke выполняет в fresh task. Planveyor не меняет consumer configuration или prompts; без launch receipt результат остаётся `unknown_without_session_launch_receipt`.
- Эта диагностика не даёт Manager права менять live consumer configuration, делать current-task hot reload или queue write as remediation; normal mode-specific queue and role-wrapper contracts stay unchanged.

## Reviewer / Model Invariants

Dual-model Reviewer flow is thread/lane split, not model switching:
- code-risk lane and contracts/finalizer lane are distinct carriers in collab mode;
- `followup_task` does not change model for an already-live thread;
- review artifacts, plan evidence, and exact bundle helpers are the source of review truth, not subagent chat memory.

## Bootstrap Pointers

At the start of a Manager session, read:
1. `AGENTS.md`
2. this role doc
3. Введение, roadmap и backlog выбранного проекта, если они существуют; пути берём из `Context links`.
4. `docs/plans/README.md` and `docs/plans/_template.md`

For concrete execution, always continue in the prompt matching the wrapper that launched Manager.

# Plan: <TOPIC>

**Date:** YYYY-MM-DD HH:MM
**Stage:** UNCONFIRMED (Stage 1/2/3)
**Priority:** UNCONFIRMED (P0/P1/P2)
**Plan type:** dev (dev | review-only)
**Status:** Architect initial draft | Architect draft | Ready for Planner | Planner intake | Ready for Architect response | Architect response | Planner finalize | Ready for Coder | Coder intake | In progress | Ready for Review | Reviewer intake | Reviewer code review | Reviewer visual review | Ready for Arch review | Architect arch review | Superseded | Done
**Schema version:** plan.v2

**Handoff statuses (кто ставит):**
- `Ready for Planner` — Architect
- `Ready for Coder` — Planner
- `Ready for Review` — Coder
- `Ready for Arch review` — Reviewer
- `Done` — Architect

> Для `**Handoff statuses**` допустимы обе separator forms между статусом и owner/comment: Unicode `—` и ASCII `-`. Держи whitespace around separator; raw prose без явного separator не считается handoff row.

> Если это umbrella/master-plan после decomposition, выше перечислены допустимые статусы, а не promise прямого executable handoff. `Decomposition wave` не заменяет umbrella: active wave = тот же umbrella/master-plan в planning-only conveyor, parked wave = тот же umbrella как reference artifact. Для parked/reference parent явно зафиксируй `N/A (...)` у `Ready for Coder` / `Ready for Review` / `Ready for Arch review`, `Code draft(s): N/A (...)`, parked state/closure contract в `## Solution` + `## Scope`; promoted child pointers держи отдельно (`## Child plan map`, `## Execution queue`, `plan_meta.next_plans`, `Child code draft(s)`). Для нового `plan.v2` deferred/backlog truth живёт только в source-bound `docs/followups/*` V2 row; `plan_meta.followups_out[]` остаётся read-only legacy V1 carrier.

> Рекомендуемое имя файла: `YYMMDD_HHMM_topic.md` (время нужно, чтобы не было коллизий и порядок был виден по сортировке).

> Язык: постановочные human-facing секции (`## Как я понял задачу`, `## Problem`, `## Solution`, `## Scope`, `## Out of scope`, `## Decisions`, `## Acceptance criteria / DoD`, Q&A/риски/предложения/logs) пишем **русским текстом**. Английский оставляем только для кода, идентификаторов, путей, команд, enum/API names, field names и коротких literal source terms.

**Context links (source of truth):**
- Target canon: `<existing repo-relative path>` (section; declared in target contract)
- API (если нужно): `docs/api.md` (section)
- UI/runtime contract (if applicable): `<target-declared UI/runtime contract carrier>`
- Visual scenario contract (if target declares UI work): `docs/smoke_visual.md` + `<target-declared scenario/harness>` (link section)
- Schema (если нужно): `docs/schema.md` (section)
- Registry (если target его ведёт): `docs/registry.md`
- Code draft(s): `docs/code_drafts/<PLAN_BASENAME>__code_draft.md` (или `N/A` для non-executable umbrella/master-plan после decomposition)
- Process ADRs (if shared process slice / contract-sensitive handoff): `docs/adr/001-plan-path-single-semantic-source-of-truth.md`, `docs/adr/003-single-live-review-route.md`, `docs/adr/004-exact-bundle-truth-and-closeout.md`, `docs/adr/005-rollout-packet-is-handoff-not-execution.md`
- Rollout packet(s) (if cross-repo handoff): `docs/rollout_packets/<YYMMDD_HHMM>_<target_repo>_<topic>.md` или `N/A`
- Related snapshot(s): `docs/snapshots/...` (if any)

> Shared-core vs profile-local carriers (if `planveyor` serves multiple repo-profiles): сначала фиксируй repo-agnostic invariant, а carrier/examples держи profile-local. Shared generic set = `alternate state / non-primary carrier proof`, `shared contract carrier bounded fan-out`, `truthful preconditions / harness drift vs live regression`, `reopened-blocker classification / same-contract reroute`. Web-only `HTMX`/`OOB`/DOM/browser/visual shell/CTA не становятся default wording для профилей без web UI; там тот же contract переводится в repo-local transport/session/log/API/harness semantics.

> Если plan включает post-review selective staging в dirty repo, authoritative implementation/doc input = `code_draft_meta.targets`. К `Ready for Review` этот список должен быть reconciled до exact final file set; final bundle затем добавляет `PLAN_PATH`, сам code draft, `## Review artifacts` и explicit asset refs из review-файла.

> Shared contract carrier check (if applicable): если меняется shared helper/adapter с externally visible HTTP/status/event/redirect/response-body semantics или repo-visible CLI/JSON/receipt fields, severity/verdict/exit-code/aggregation semantics, это bounded fan-out change. Зафиксируй helper/adapter path, dependent tests, dependent docs, known consumer paths и consumer contract semantics (`verdict/blocker` vs `candidate/evidence/prefill`, severity/warn/blocking behavior, schema compatibility) в `## Changes (by area)` и code draft; `audit later` к handoff запрещён.

> Reopened-blocker classification (if applicable): до scope rewrite явно назови `stale evidence / historical artifact mismatch`, `same-contract reroute`, `closed baseline + live blocker split` или `real scope expansion`. Если bundle, `code_draft_meta.targets`, `Scope/Acceptance/Tests/Commands` и Planner-owned contract не меняются, narrow reroute идёт на `Coder intake`; `Ready for Coder` не переиспользуем как shortcut.

> Composite executable lane fork threshold (if applicable): `same-cluster evidence reroute` (тот же cluster, те же targets и acceptance host; меняются только wording/preconditions/evidence) остаётся в исходном plan. Но `cluster-local material delta` (один cluster уже требует новый helper/support path, новые seed/docs targets, новый screenshot/review host или другой contextual carrier) требует blocking follow-up dev-plan, а старый executable file становится `Superseded` или explicit reference-only baseline.

---

## Meta (machine-readable JSON; required for current plan.v2 plans)
```json
{
  "plan_meta": {
    "cluster": "UNCONFIRMED",
    "tags": [],
    "required_manager_mode": "either",
    "wave_family": null,
    "phase_overlay": null,
    "phase_state": null,
    "parent": null,
    "next_plans": [],
    "depends_on": [],
    "queue_activation": {
      "state": "n/a",
      "source_ref": "N/A (why=initial draft is not queued)",
      "reason": "N/A (why=no executable child is admitted)"
    },
    "scope_expansion": {
      "state": "n/a",
      "target_contour": "N/A",
      "source_ref": "N/A (why=no scope expansion)",
      "reason": "N/A (why=initial draft has bounded scope)"
    },
    "canon_updates": []
  }
}
```

> Machine-authority admission: до downstream handoff Architect materialize-ит
> ровно один `plan_meta.machine_authority_decision`: полный `required` decision
> или точную трёхключевую `not_applicable` форму. Обязательность зависит от статуса
> и назначения, не даты/имени. `_template.md` и Architect-owned стадия до handoff
> допускают отсутствие carrier; присутствующий malformed carrier отклоняется.
> Prose, Evidence, Q&A, target count и code draft не заменяют decision;
> missing/pending/rejected carrier блокирует downstream handoff.
> Новое required-решение использует
> `"cutover_policy": {"kind": "status_and_purpose_handoff"}`; точное старое
> значение читается без миграции, с теми же проверками Owner confirmation,
> digest/ref и путей. Подробности: `docs/plans/README.md` → Machine-authority admission.

> `plan_meta.required_manager_mode` — единственный admission authority для Manager:
> `manager-collab`, `manager-custom-pipeline` или explicit `either`. Значения из
> `## Verification rerun / exec handoff`, команд, тегов и истории запуска не
> используются для inference или автоматического переключения Manager.

> Contour markers: ordinary bounded implementation использует implicit `developer_wave`; `analysis_wave` использует `plan_meta.wave_family = "analysis_wave"` + `## Analysis pack`; `decomposition_wave` использует `plan_meta.phase_overlay = "decomposition_wave"` + `phase_state` + decomposition carriers below. `planning contour` (`analysis_wave` / `decomposition_wave`) выпускает repo-backed planning artifacts, not product diff. Если ordinary dev plan обнаруживает `split_required=true`, broad analytics или child graph creation, остановись и reroute в planning contour вместо hidden implementation intake.
> Optional planning-contour receipts: `plan_meta.promoted_from` is a derived/read-only target snapshot (`authority_note=derived_read_only; source artifact is writable truth`), `plan_meta.queue_activation.state` uses `not_requested|owner_approved|architect_approved|n/a`, and `plan_meta.scope_expansion.state` uses `n/a|suspected|reroute_required|architect_accepted`. A complete `queue_activation.state=n/a` object is intentional queue-collection ineligibility: explicit/status/umbrella/append collection hard-fails before state/log mutation and never becomes `skipped_incompatible[]` / `skip_manager_mode`. Direct `planveyor_decomposition_init` is single-plan bootstrap, not queue collection. Machine-readable enums live in `docs/_meta/plan_vocab.json` -> `planning_contour`.

> Runner/model intent = admission metadata, not route selector. Small-runner requests живут в promoted route / queue / child-contract fields (`runner_admission`, `small_model_ready_state`, `Runner suitability`) и не форсят `decomposition_wave`, если scope/graph/boundaries не требуют structural split.

## Plan provenance / session context
(Required for current plan.v2 plans. Historical touch-on-edit/backfill still materializes this carrier instead of skipping it. Use repo-backed helper output; if a fact is missing, keep the field and write `N/A (why=...)`.)
- Relation: `created-here | continued-here | imported-from-packet | manual-backfill`
- Thread ID: `UUID/handle` или `N/A (why=...)`
- Parent thread ID: `UUID/handle` или `N/A (why=...)`
- Session SID: `UUID/handle` или `N/A (why=...)`
- Launch surface: `codex-desktop | codex-cli | manager-collab | manager-custom-pipeline | unknown (why=...)`
- Captured from: `env | wrapper-session-file | session-stats | packet-import | manual-owner`
- Captured at: `YYYY-MM-DDTHH:MM:SSZ`

> Этот carrier отвечает только на происхождение текущего plan context. Он не заменяет `plan_meta`, `## Verification rerun / exec handoff`, `.planveyor.session.*` attach-pointer и rollout packet. Canonical helper surface = `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_plan_provenance_stamp <PLAN_PATH> --session-key <role>`. Existing section сохраняем и обновляем только по truthful trigger: новый thread/session continuation, packet import или explicit manual backfill.

## Documentation impact / provenance
(Required for current plan.v2 plans. This is planning-time documentation impact, not session provenance and not a second exact-bundle target list. Use `N/A (why=...)` for fields that do not apply; blank/missing fields are not a complete carrier.)
- Source docs used: `docs/...` / reviews / retrieval hits / prior plans used while drafting, or `N/A (why=...)`
- Synchronous doc/registry targets: docs that must be edited in the same implementation slice, or `N/A (why=...)`
- Post-merge canon updates: durable facts/decisions to promote after implementation, or `N/A (why=...)`
- Deferred documentation follow-ups: explicitly deferred docs work with owner/reason, or `N/A (why=...)`
- Provenance refs: Owner input / review blocker / prior plan / rollout packet / retrieval hit, or `N/A (why=...)`

> `code_draft_meta.targets` remains the authoritative executable file set. This section explains why documentation is in scope, what must move together, and which doc work is post-merge or deferred; it does not replace `Context links`, `plan_meta.canon_updates[]`, or `## Plan provenance / session context`.
> For current `plan.v2` plans, `plan_lint.py` hard-fails execution/review handoffs when `Synchronous doc/registry targets` and linked `code_draft_meta.targets` drift. Missing/placeholder carrier fields remain warning-first so early drafts can be corrected before handoff.

## Problem

## Как я понял задачу
(Required for Architect intake. Коротко, по-человечески и по-русски: что меняем/решаем, границы, route/следующий contour, что не делаем, какие Owner-решения закрыты или не нужны. Этот блок не заменяет `## Q&A log` и не должен жить только в Evidence/CENSOR.)

## Solution (high level)

## Decisions (final)
(Фиксируем финальные решения без A/B хвостов. Удобный формат: `❌ альтернативы → ✅ final → Trade-offs`. Если нужен Owner или rollout/bridge matrix для phased rollout / feature flag / compatibility задач — см. `docs/plans/README.md` и зафиксируй итог в самом плане.)

## Scope

## Out of scope

## Follow-ups (deferred)
(Если что-то уходит “потом/не сейчас” — фиксируем это здесь или отдельным follow-up plan. Пункт, который умышленно выкинули из active scope, но не отменили owner-решением, не имеет права остаться только в `## Out of scope`: его literal-но дублируем здесь и даём судьбу `promote later | needs_owner | already tracked elsewhere | canon sync closed it`.)

> `plan.v2` не содержит `plan_meta.followups_out`: deferred work materialize-ится только в `docs/followups/*` как source-bound V2 row. `next_plans` / `## Execution queue` остаются единственным carrier для executable continuation; legacy `plan.v1` readers не переписываются этим default.

> Для decomposition child rows labels вроде `notes`, `analysis` или `prep` — warning signs. Это не executable children, если row явно не `slice_kind=needs_analysis` with bounded source refs, key unknowns, trigger for promotion, parent consumer decision and analysis-review return path.

## Rollout packet handoff
(Required if this plan emits or adopts a checked-in cross-repo handoff packet; otherwise `N/A (why)`. Packet живёт в source repo, target repo импортирует его в local plan и только после этого запускает local queue/execution.)
- Role: `N/A (why)` или `source-packet | target-import`
- Packet path: `N/A (why)` или `docs/rollout_packets/<YYMMDD_HHMM>_<target_repo>_<topic>.md`
- Target repo: `N/A (why)` или `<target-repo>`
- Suggested target plan slug: `N/A (why)` или `<topic_slug>`
- Queue after import: `N/A (why)` или `yes | no`

## Small-slice conveyor classifier
(Required only if this plan asks Manager to reduce same-session `Architect/Planner/Coder CENSOR`; otherwise `N/A (why)`. Helper-side validation is runtime-owned and any drift falls back to the full conveyor.)
- Requested profile: `N/A (why)` или `reduced-same-session-censors`
- Expected bundle family: `N/A (why)` или `docs-only | tests-only`
- Helper validation: `N/A (why)` или `exact-bundle-match`
- Drift behavior: `N/A (why)` или `fail-closed-to-full-conveyor`

> Compact CENSOR/reviewer receipts may use opened/read `Source refs` + concise `Delta` / `Outcome` instead of repeated narrative, but only when mandatory labels, gates, target snapshot parity, lane synthesis, blocker reconciliation and red-as-live lifecycle checks remain literal.

## Close-out routing
(Куда идти после closure этого slice. Это carrier для bounded next-step routing, а не дубль `## Post-merge gate`.)
- Roadmap/queue sync: N/A (why=initial draft; route on closeout)
- Follow-up sync: N/A (why=initial draft; route on closeout)
- Next bounded slice: N/A (why=initial draft; route on closeout)
- Terminal outcome: N/A (why=initial draft; route on closeout)

## Business decomposition framing
(Required if `plan_meta.phase_overlay = "decomposition_wave"` and parent is a business/task initiative; otherwise `N/A (why)`. Для technical/process-only decomposition пиши `N/A (why=technical/process decomposition, not business task)`.)
- Business outcome: `N/A (why)` или UNCONFIRMED
- Actor/operator: `N/A (why)` или UNCONFIRMED
- Current pain: `N/A (why)` или UNCONFIRMED
- Target behavior: `N/A (why)` или UNCONFIRMED
- Non-goals: `N/A (why)` или UNCONFIRMED
- Guardrails / trust boundaries / execution budget: `N/A (why)` или UNCONFIRMED
- Expected proof shape: `N/A (why)` или UNCONFIRMED
- Decomposition axes: `N/A (why)` или UNCONFIRMED

## Child plan map
(Required для active `decomposition_wave`; otherwise `N/A (why)`. Только promoted children. Для `plan.v2` deferred/backlog items живут в external `followups.v2` rows; `plan_meta.followups_out[]` — legacy V1-only compatibility context. `Dependency type` = `sequential | parallel | soft | blocking`.)
| Queue order | Plan | Purpose | Input | Output | Consumer | Depends on | Dependency type | Acceptance/proof lane | Independent-stop reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `N/A` | `N/A (why=not a decomposition wave or no promoted child yet)` | `N/A` | `N/A` | `N/A` | `N/A` | `N/A` | `N/A` | `N/A` | `N/A` |

## Small-model-ready child contract
(Required для promoted decomposition children; otherwise `N/A (why)`. Canonical field names live in `docs/playbooks/decomposition_wave.md` -> `Small-model-ready child contract`. Hard-required fields for promoted children should not be `TBD`; warning-first fields must exist but may carry bounded caveats.)
| Field | Value |
| --- | --- |
| Task outcome | `N/A (why=not a promoted decomposition child)` или `<one observable result>` |
| Local context bundle | `N/A (why=not a promoted decomposition child)` или `<exact documentation/plans/reviews/helpers to read first>` |
| Mutable surfaces | `N/A (why=not a promoted decomposition child)` или `<exact paths/path families allowed to change>` |
| Read-only surfaces | `N/A (why=not a promoted decomposition child)` или `<anchors allowed for reading only>` |
| Forbidden scope | `N/A (why=not a promoted decomposition child)` или `<explicit non-goals / nearby tempting changes>` |
| Inputs from parent/predecessor | `N/A (why=not a promoted decomposition child)` или `<artifact paths and dependency gates>` |
| Output to consumer | `N/A (why=not a promoted decomposition child)` или `<artifact/status/queue effect and consumer>` |
| Acceptance/proof lane | `N/A (why=not a promoted decomposition child)` или `<exact commands/checks/receipts/review lane>` |
| Stop condition | `N/A (why=not a promoted decomposition child)` или `<when to return upstream instead of guessing>` |
| Expected reviewer lane | `N/A (why=not a promoted decomposition child)` или `<docs-only/code/risk/contracts/visual>` |
| Runner suitability | `N/A (why=not a promoted decomposition child)` или `<recommended runner class plus fallback/degraded condition>` |
| Task size/complexity | `N/A (why=not a promoted decomposition child)` или `<small|medium|large and why>` |
| Readiness notes | `N/A (why=not a promoted decomposition child)` или `<known clarity gaps / confidence notes>` |

## Decomposition quality gate
(Required для active `decomposition_wave`; otherwise `N/A (why)`. Если child graph ещё не готов, пиши explicit `N/A (why=child graph not ready)` и не ставь child в `## Execution queue`.)
- Solvability: `N/A (why)` или `<каждый promoted child имеет owner/input/dependency gate/proof route>`
- Completeness: `N/A (why)` или `<umbrella + promoted children + deferred follow-ups покрывают исходный scope/обязательства/debt>`
- Non-redundancy: `N/A (why)` или `<нет duplicate owner/proof burden/side-effecting overlap без причины>`
- Mutable surface / runtime isolation: `N/A (why)` или `<touches/shared resources/worktree/runtime policy>`
- Recomposition / integration owner: `N/A (why)` или `<кто собирает child outputs обратно и какие integrated checks закрывают parent delivery>`

## Execution queue
(Required для umbrella/master-plan, если он хочет materialize-ить canonical queue order для `Manager run Q` / `--q`; иначе `N/A (why)`.)
- Resume parent: `N/A (why)` или `none | owner-restamp-required | run-parent-once`
- Plan: `N/A (why)` или `docs/plans/<child_plan>.md`
- Plan: `docs/plans/<another_child_plan>.md`

> Queue children must be materialized repo-relative `docs/plans/*.md` files. Missing/non-lintable child paths fail closed; do not synthesize child content from prose.

## Queue close-out
(Companion carrier для `## Execution queue`; если этот plan не queue carrier — `N/A (why)`.)
- On terminal child completion: UNCONFIRMED
- On non-terminal stop: UNCONFIRMED
- Parent resume: UNCONFIRMED

## Mechanism coverage
(Required if `plan_meta.phase_overlay = "decomposition_wave"`; otherwise `N/A (why)`.)
`N/A (why)` или helper-readable rows:

| Mechanism | Usage | Source refs | Proof anchor | State | Promoted child impact |
| --- | --- | --- | --- | --- | --- |
| `N/A (why=not a decomposition wave)` | `N/A (why=not a decomposition wave)` | `N/A (why=not a decomposition wave)` | `N/A (why=not a decomposition wave)` | `N/A (why=not a decomposition wave)` | `N/A (why=not a decomposition wave)` |

Для active `decomposition_wave` названные mechanisms (`golden-path`, backlog,
completed-plan index, retrieval, registry, `plan_meta` linkage) требуют concrete
`Source refs` и `Proof anchor` или explicit `N/A (why=...)`.

## Analysis pack
(Required if `plan_meta.wave_family = "analysis_wave"`; otherwise `N/A (why=not an analysis_wave plan)`. Full field semantics, route enum and review gates live in `docs/playbooks/analysis_wave.md`; не дублируй здесь Q&A/review/arch-review truth.)
(При переходе на `Planner finalize` Planner переносит эту таблицу в `docs/analysis_packs/<PLAN_STEM>.md` под тем же заголовком, а здесь остаётся одна строка `analysis_pack_ref` со ссылкой `docs/analysis_packs/<PLAN_STEM>.md#Analysis-pack`.)
- `N/A (why=not an analysis_wave plan)` или structured pack:

| Field | Value |
| --- | --- |
| `analysis_subject` | `<bounded subject>` |
| `desired_outcome` | `<decision/route this analysis must enable>` |
| `actor_current_pain` | `N/A (why=not business/product analysis)` или `<actor + current pain + target behavior>` |
| `scope_refs` | `<opened/read repo-backed refs; retrieval hits not read do not count>` |
| `documentation_impact_seed` | `<source docs, sync targets, deferred docs follow-ups, provenance refs>` |
| `constraints_non_goals_execution_budget` | `<guardrails / non-goals / trust boundaries / budget>` |
| `question_refs` | `N/A (why=no open/closed question refs needed)` или `<Q&A refs only>` |
| `assumptions` | `<supported assumptions>` или `unsupported_assumption: <...>` |
| `risks_escalation_triggers` | `N/A (why=none)` или `<needs_owner/security/integration/public API/canon triggers>` |
| `canon_conflicts_updates_seed` | `N/A (why=none)` или `<canon conflicts / candidate canon updates>` |
| `dependent_inventory_mutable_surfaces` | `N/A (why=non-executable route)` или `<helpers/tests/docs/known consumers/mutable/read-only surfaces>` |
| `options_considered` | `<options + trade-offs + rejected alternatives>` |
| `recommendation` | `<chosen answer / decision proposal>` |
| `requirement_slices` | `N/A (why=non-executable route)` или `<slice_kind=dev_candidate|decomposition_candidate|needs_analysis; executable candidates reuse small-model-ready child contract>` |
| `decomposition_sizing_rationale` | `N/A (why=route is not decomposition_wave)` или `<direct|slim|full + axes>` |
| `reviewability_seed` | `N/A (why=non-executable route)` или `<proof-path class / mandatory lanes / preconditions / reroute rule>` |
| `runner_handoff_seed` | `N/A (why=runner intent unknown/not applicable)` или `<runner intent/readiness/fallback>` |
| `route_recommendation` | `<developer_wave|decomposition_wave|human_gate|defer|reject> + reason + prerequisites + target refs` |
| `promoted_route_refs` | `N/A (why=not accepted by Architect arch review yet)` или `<refs only: seed plan / follow-up / human gate / rejection refs; do not copy accepted-route payload>` |
| `review_artifact_ref` | `N/A (why=review not materialized yet)` или `<documentation/code review artifact ref>` |
| `arch_review_routing_ref` | `N/A (why=not accepted by Architect arch review yet)` или `<accepted route status/linkage ref>` |

> `route_recommendation` — только recommendation. Accepted route truth lives in promoted route artifact/status/linkage after Architect arch review. `promoted_route_refs` is refs-only; do not duplicate `accepted_route`, `promoted_artifact_ref`, `queue_admission` or `runner_admission` there.

## Promoted route artifact
(Required only after `Architect arch review` accepts an `analysis_wave` route; otherwise `N/A (why=not accepted by Architect arch review yet)`. Full route-artifact semantics live in `docs/playbooks/analysis_wave.md`; не дублируй Q&A/review/arch-review payload.)
- `N/A (why=not accepted by Architect arch review yet)` или structured route artifact:

> Accepted route без materialized `promoted_artifact_ref` и explicit `next_action` = blocker. `human_gate` / `defer` / `reject` are non-executable gate/deferred/terminal outcomes, not a happy path for avoiding seed plan / umbrella creation.

| Field | Value |
| --- | --- |
| `route_id` | `<stable route id>` |
| `source_analysis_plan` | `<repo-relative source plan path>` |
| `source_analysis_pack_ref` | `<section/artifact ref>` |
| `accepted_route` | `<developer_wave|decomposition_wave|human_gate|defer|reject>` |
| `accepted_route_reason` | `<why accepted after review>` |
| `review_artifact_ref` | `<live review artifact ref>` |
| `arch_review_ref` | `<plan evidence/Q&A/status ref>` |
| `promoted_artifact_ref` | `<seed plan / follow-up / human gate / rejection receipt ref>` |
| `promoted_artifact_kind` | `<seed_dev_plan|decomposition_umbrella|owner_gate|followup|rejection_receipt>` |
| `next_action` | `<queue/admission path | await_owner_decision(...) | deferred_followup_promotion(trigger=...) | terminal_rejected>` |
| `revisit_when` | `N/A (why=not human_gate/defer)` или `<concrete owner/re-entry trigger>` |
| `subject_identity` | `N/A (why=not non-executable duplicate-sensitive route)` или `exact(<subject key>)` |
| `duplicate_of` | `N/A (why=not duplicate rejection)` или `<exact prior route/follow-up/source ref>` |
| `delivered_state` | `N/A (why=not decomposition_wave)` или `<framed|child_graph_ready|child_artifacts_materialized>` |
| `promoted_artifact_status` | `N/A (why=not seed plan)` или `Architect initial draft` |
| `mapping_summary` | `N/A (why=not seed plan)` или `<pack field -> target plan section mapping>` |
| `child_slice_policy` | `N/A (why=not decomposition_wave)` или `<dev_candidate/decomposition_candidate/needs_analysis policy>` |
| `analysis_child_materialization` | `N/A (why=no needs_analysis slices)` или `materialized_now` или `map_only(reason=...)` |
| `inherited_doc_impact` | `N/A (why=not inherited)` или `<doc impact refs>` |
| `inherited_guardrails_risks` | `N/A (why=not inherited)` или `<constraints / risks / escalation refs>` |
| `inherited_dependent_inventory` | `N/A (why=non-executable route)` или `<helpers/tests/docs/known consumers/mutable surfaces>` |
| `inherited_reviewability_seed` | `N/A (why=non-executable route)` или `<proof lanes / preconditions / reroute rule>` |
| `runner_intent` | `N/A (why=non-executable route)` или `<frontier_default|small_runner_requested|small_runner_allowed|small_runner_required>` |
| `small_model_ready_state` | `N/A (why=non-executable route)` или `<not_applicable|unchecked|ready|not_ready(reason=...)>` |
| `runner_admission` | `N/A (why=non-executable route)` или `<frontier_only|small_runner_ok|small_runner_blocked(reason=...)>` |
| `queue_admission` | `<queueable_now|needs_planner|needs_owner|not_queueable> + reason` |

For accepted `developer_wave` / `decomposition_wave`, `source_analysis_plan`
and `source_analysis_pack_ref` are helper-required source-artifact fields. A
decomposition target `plan_meta.promoted_from` must point back to an existing
`analysis_wave` source plan and matching `## Promoted route artifact`; do not
add a second writable target-side source receipt. Direct Owner/external reviewer
decomposition intake may use explicit `source_plan=N/A (why=...)`; source-route
parity does not apply to that direct-source case.

> V1 analysis-born seed dev plans start at `Architect initial draft`; do not promote directly to `Ready for Planner` without a future explicit fast-path contract.

## Constraints / Assumptions

## Risks / Open questions (summary)

## Reviewability preflight receipt
(Required if handoff depends on helper family, named non-primary carrier / contextual lane, or deterministic visual/native/stateful proof. Rules and examples — in `docs/plans/README.md` → `Reviewability preflight receipt`.)
- `proof-path class`: UNCONFIRMED
- `mandatory primary lane`: UNCONFIRMED
- `mandatory non-primary carrier / contextual lane`: `N/A (why)` или UNCONFIRMED
- `exact helper path + support files`: `N/A (why)` или UNCONFIRMED
- `dependent tests / dependent docs / known consumer paths`: `N/A (why)` или UNCONFIRMED
- `preconditions / seed-discovery`: `N/A (why)` или UNCONFIRMED
- `reroute rule`: UNCONFIRMED
- `perceptual truth-source split`: `structural/repo-backed carrier preferred; screenshot OCR/template matching/pixel search = debug-only; built-in LLM image reading over captured canonical artifact = bounded fallback; repeated image-based fallback => helper gap/follow-up`

<!--
### State-transition declarations
(Opt-in only. Copy this block out of the comment only when the current receipt needs the declarative transition contract; ordinary plans remain non-opt-in.)
- `before-state`: carrier=<authoritative-carrier>; identity=<stable-identity>; expected=<before-state>
- `allowed mutation inventory`: writer=<bounded-writer>; entrypoint=<bounded-entrypoint>; targets=["<canonical mutation identifier>"]
- `after-state`: carrier=<authoritative-carrier>; identity=<stable-identity>; expected=<after-state>
- `protected-target post-review continuity`: targets=["docs/<repo-relative-path>.md"]; on_change=same-file-review-rerun
-->

<!--
### Semantic review observation
(Только strict opt-in. Для обычных plan весь пример остаётся в comment: отсутствие marker-а означает legacy/non-opt-in и не создаёт Reviewer writer duty.)
- `schema=semantic_review_observation.v1`
- `mode=required`
- `writer=reviewer_code_contracts`

### Semantic cycle checkpoint
(Только paired strict opt-in. Materialize этот блок только вместе с exact producer marker после code draft; writer resolution = Architect, не Manager/Reviewer/Coder.)
- `schema=semantic_cycle_checkpoint.v1`
- `mode=required`
- `writer=architect`

<!-- `semantic_cycle_checkpoint_resolution.v2` не является default template
carrier. Его допускает только отдельный frozen+confirmed `bounded_grammar`
subject с finite grammar contour; Architect writes accepted Evidence, while
Planner/CENSOR/oracle consume helper readback. V1 stays compatible, V2 `stop`
is forbidden, and a new family never resets the contour-wide permit. -->

Когда plan с этим opt-in копирует из comment ровно эти три rows, sole writer — `reviewer_code_contracts`: после helper-selected current `reviewer_code_risk` block и aggregate verdict он append-ит один proposal-only `semantic_review_observation_proposal.v1`, повторно читает неизменный read-only helper, копирует только returned `materialization.observation`, затем читает `valid/current_observation_valid`. Не добавляй в template default proposal/final JSON block, machine fields, route/status text или extra marker prose.

Template также не materialize-ит default raw `BUNDLE=current` snapshot, compact receipt, support asset или checkpoint resolution JSON: ordinary plan остаётся legacy/non-opt-in до literal paired adoption в executable receipt.
-->

> К `Ready for Coder` этот receipt и `## Verification rerun / exec handoff` уже должны описывать current executable bundle из `code_draft_meta.targets`; `reread-only/context-only` carriers не возвращаются в `Command` / `Expected artifact` без реального scope rewrite.
> Если exact shared lane materialize-ится только в одном primary carrier, но paired contextual/no-dup carriers держат тот же contract honest (followups wrapper, manager bridge, alternate proof host), перечисляй их literal-но в `mandatory non-primary carrier / contextual lane` и/или `dependent tests / dependent docs / known consumer paths`; не оставляй их как “implicit grep later”.
> Manual writable current-state blocks are forbidden. If a plan needs current-state/terminal readback, cite generated helper output such as `scripts/plan_status_oracle.py --json <PLAN_PATH>` / `--current-state <PLAN_PATH>`, or write explicit `N/A (why=...)`; do not add a second hand-written status/current-state carrier in plan markdown, plan JSON or Evidence.
> Truth-host fixture matrix (required only when the slice changes a fan-in/readback helper that summarizes authoritative truth hosts; otherwise write `N/A (why=not a fan-in/readback helper with authoritative truth hosts)`): `authoritative_host`, `derived_summary_field`, `green_case`, `missing_case`, `ambiguous_case`, `present_but_red_or_inconsistent_case`, `expected_fail_closed_verdict`. The present-but-red/inconsistent case must prove that a derived green summary cannot override an authoritative red host.

Truth-host fixture matrix:
- `authoritative_host`: `N/A (why=not a fan-in/readback helper with authoritative truth hosts)` или exact truth carrier/path+field
- `derived_summary_field`: `N/A (why=...)` или helper/readback field
- `green_case`: fixture/proof for authoritative green -> derived green
- `missing_case`: fixture/proof for missing host -> fail-closed
- `ambiguous_case`: fixture/proof for multiple/current ambiguity -> fail-closed
- `present_but_red_or_inconsistent_case`: fixture/proof for authoritative red/mismatch while derived summary can look green
- `expected_fail_closed_verdict`: exact error/blocker/verdict; derived green cannot override authoritative red

> Для source-owned rollout-packet refresh slice primary lane обычно = `plan_lint` + packet-scoped `doc_lint`; `preconditions / seed-discovery` literal-но говорят, packet pair already materialized или создаётся впервые, а contextual lane читает packet на `Target writable carriers`, `Queue after import` и importable-boundary / not-yet-landed guards.
> Если slice materialize-ит новую carrier/helper family поверх already-landed baseline, split `existing baseline surfaces = ...; new targets = ...` должен быть literal и в plan, и в code draft; иначе Coder/Reviewer не отличат reference carriers от реально меняемого bundle.
> Для stateful multi-step / transient proof lane добавь literal-ный split `discovery-or-seed` vs `receipt-reuse-only`, stable identity fields, exact observer boundary, next canonical snapshot/readback как mutation truth source и `runtime-lineage preflight` / reroute там, где stale runtime может имитировать product regression.
> Если proof lane пишет receipt/output artifact, literal-но назови retention class для каждого path family: `transient local sanity only` vs `durable operator/review evidence`; `.tmp/...` по умолчанию transient и не подменяет durable carrier без явного contract note.

## Changes (by area)
- Data/schema (migrations if used):
- Logic/modules:
- Interfaces (API/CLI/UI):
- Config (keys/defaults):
- Docs/registry:

> Для risky visual/layout/visibility/default-state/access задач перечисли конкретные `risky touchpoints/surfaces` и alternate routes. Closure map и правила handoff — в `docs/plans/README.md` → `Critical runtime invariants` / `Plan gaps`.

## Acceptance criteria / DoD

### Backend/Domain contract checklist (required if touching data/logic/interfaces)
- [ ] Defaults: значения по умолчанию (дата/таймзона/лимиты/пороги) + ограничения (например, “в будущем нельзя”)
- [ ] Validations/corrections: что запрещено и как разрешить (checkbox/комментарий/override)
- [ ] Server-side invariants/validation: какие поля required/unique/>=0 и где это валидируется; selected target объявляет status/error contract для invalid interaction, если он применим
- [ ] After-mutation refresh: selected target объявляет применимый refresh/event contract и producer/consumer paths
- [ ] Access/error semantics: selected target объявляет применимые guards, response/status и user-visible outcome
- [ ] Config: список ключей + значения по умолчанию (если затрагиваем конфигурацию)
- [ ] Logging/notifications: что пишем и в какие объявленные target-ом каналы (журнал/уведомления/UI), кто получатели (без секретов/PII)

### UI contract checklist (required if touching UI)
(Если UI не меняется — вместо пунктов одна строка `N/A (why=no UI change)`.)
- [ ] UI contract: carrier/ref, который объявил target, и что в нём меняется
- [ ] User-visible acceptance: что пользователь видит и может сделать после изменения
- [ ] Interaction/error semantics: поведение при действиях, ошибках, пустых и граничных состояниях

### General DoD checklist (recommended)
- [ ] Secrets/PII: не пишем токены/ключи/пароли/cookie и персональные данные (только `<REDACTED>`)
- [ ] Migrations (если стек их использует): не редактируем существующие; новые — идемпотентные, с индексами/constraints где нужно; явно отражены в `## Changes`; если миграция ожидается — зафиксирован смысл/ожидаемое имя (чтобы в ревью не искать)
- [ ] Migrations drift gate (if applicable): selected target declares exact command and expected result; это про drift, а не про применение миграций к локальной БД.
- [ ] Server-side validation: не полагаемся на client-side `min/required`; критичные проверки есть на сервере; selected target объявляет applicable invalid-interaction status/error carrier
- [ ] Shared contract carrier audit (if applicable): если helper/adapter меняет externally visible HTTP/status/event/redirect/response-body semantics или repo-visible CLI/JSON/receipt fields, severity/verdict/exit-code/aggregation semantics, plan + code draft явно называют helper, dependent tests, dependent docs, known consumer paths и consumer contract semantics (`verdict/blocker` vs `candidate/evidence/prefill`, severity/warn/blocking behavior, schema compatibility); нет `audit later`
- [ ] API/payload field parity (if applicable): changed payload fields named exactly; emitter/helper path named; regression assertion/readback named, or explicit `N/A (why)`
- [ ] Registry (if target keeps one): при добавлении новых helpers/модулей/компонентов — обновлён target registry carrier (например `docs/registry.md`) и не задублили существующее
- [ ] No mass reformat: не делаем “массовый реформат” без отдельного плана/PR
- [ ] If adding status/field/type: обновлены все места маппинга/опций/порядка/отображения/веток логики/истории (не оставляем “else → default”); минимум проверить: хранилище (схема/миграции, если есть), логику, интерфейсы (API/CLI/UI), историю
- [ ] If money/time math involved: используем точный тип (`Decimal` или точный тип стека, не float), учитываем edge cases (0/null/div0/отрицательные), фиксируем единицы/округления/fallback‑логику и покрываем тестами
- [ ] Rollout/deploy-контракт (if phased rollout / feature flag / bridge / compatibility / migration-toggle): точная матрица из 6 пунктов зафиксирована в плане; `missing env/config pin behavior` явный; если safety зависит от external pin/manual step, текущая защита, зафиксированная в репо, названа прямо; нет неявной устной deploy-договорённости
- [ ] No silent defers: если пункт Scope/Acceptance/DoD не сделан — либо делаем сейчас, либо оформляем перенос в `Follow-ups (deferred)` / Goal Deviations (без “молчаливого потом”)

### Handoff checklist (Architect → Planner; before `Ready for Planner`)
- [ ] В плане нет “TBD/finalize later”; альтернативы выбраны и зафиксированы в `## Decisions (final)`
- [ ] Plan structure: `## Problem` (пронумерованные пункты), `## Solution (high level)` (стабильная структура), `## Scope` + `## Out of scope`, `## Acceptance criteria / DoD`
- [ ] `## Plan provenance / session context` materialized literal-но и sourced from helper/repo-backed facts; missing fields честно оставлены как `N/A (why=...)`, а не додуманы по памяти
- [ ] Reopened-blocker classification (if applicable): `same-contract reroute` явно отделён от `real scope expansion`, а `closed baseline` и `live blocker` названы явно; unchanged Planner-owned contract не маскируется под новый `Ready for Coder`
- [ ] Факты/идентификаторы: если в плане появились конкретные имена полей/URL/компонентов/events — они подтверждены в коде (через `rg`) или явно помечены как новые/`UNCONFIRMED`
- [ ] Для phased rollout / feature flag / bridge / compatibility / migration-toggle задач точный rollout-контракт из 6 пунктов зафиксирован без дрейфа терминов, а `safe to merge` / `safe to deploy` / `safe to flip` не противоречат `repo default`, `expected live default` и поведению без pin

### Handoff checklist (Planner → Coder; before `Ready for Coder`)
Owner: Planner (держать в синхронизации с `docs/roles/planner.md` → `Planner finalize gate`).

- [ ] `Stage`/`Priority`: заполнены (не `UNCONFIRMED`)
- [ ] `Context links`: есть BRD/ARCH якоря и вся нужная каноника по теме (а не “см. где-то”)
- [ ] `## Plan provenance / session context`: literal field set присутствует и не конфликтует с `Context source` / rerun receipt / packet ownership
- [ ] Code draft: `docs/code_drafts/<PLAN_BASENAME>__code_draft.md` существует, залинкован в `Context links` и к `Ready for Coder` уже не остаётся bare stub / `seed-only` wording
- [ ] `## Decisions (final)`: без “TBD/потом”, без A/B; выбор сделан и проверяем
- [ ] `## Scope` / `## Out of scope`: явные границы; “потом” оформлено как `## Follow-ups (deferred)`
- [ ] `## Changes (by area)`: для каждого слоя указаны конкретные файлы/модули/эндпоинты/команды (Coder не должен гадать “где править”)
- [ ] Shared contract carrier inventory (if applicable): plan + code draft называют helper/adapter path, dependent tests, dependent docs, known consumer paths и consumer contract semantics (`verdict/blocker` vs `candidate/evidence/prefill`, severity/warn/blocking behavior, schema compatibility); нет `audit later`
- [ ] Reviewability preflight receipt (if applicable): plan + code draft literal-но фиксируют `proof-path class`, helper/support files, mandatory lanes, preconditions, reroute rule и perceptual truth-source split; нет implicit reliance на OCR/template/pixel hacks или repeated image-based fallback
- [ ] Stateful multi-step / transient proof lane (if applicable): `Reviewability preflight receipt` и code draft literal-но называют `discovery-or-seed`, downstream `receipt-reuse-only`, stable identity fields, exact observer boundary, next canonical snapshot/readback как mutation truth source и `runtime-lineage preflight` / reroute там, где stale runtime может маскироваться под product regression
- [ ] Receipt retention class (if applicable): если proof lane пишет receipt/output artifact, plan + code draft literal-но отделяют transient local sanity path (`.tmp/...` или repo-local equivalent) от durable operator/review evidence path (`docs/reviews/...` или repo-local equivalent); smoke/helper sanity не маскируется под merge evidence
- [ ] Synthetic proof carrier (if applicable): если repo/profile ещё не содержит live corpus/entity set для этого контракта, plan + code draft literal-но называют temp-fixture/synthetic proof path и не расширяют bundle checked-in sample carriers или historical backfill "только ради теста"; если без этого closure нечестен, это reroute/follow-up
- [ ] Baseline vs new-target split (if applicable): если slice строит новый carrier/helper family поверх already-landed baseline, plan + code draft literal-но отделяют existing baseline surfaces от new targets; paired contextual/no-dup carriers названы в consumer inventory даже если exact lane materialize-ится только в primary surface
- [ ] Planner-time exact-bundle preflight (executable plan): перед `Ready for Coder` прошёл `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_plan_bundle --preflight <PLAN_PATH>`; malformed/missing top-level `code_draft_meta`, несовпадающий `code_draft_meta.plan` и missing/stale targets закрыты как Planner blockers; отсутствующий first-pass review artifact допустим только до Reviewer
- [ ] Exact executable bundle sync: `code_draft_meta.targets`, `## Changes`, `## Commands`, `## Verification rerun / exec handoff` и live `## Review artifacts` / `Expected artifact` описывают один current bundle; если package host materialize-ился только частью concrete files, restamp targets на literal file paths до `Ready for Review`; `plan_meta.canon_updates` не подменяет target inventory, а `reread-only/context-only` refs не маскируются под executable targets
- [ ] Planned new target paths (if applicable): new files either already exist as final implementation or carry a minimal fail-closed path-tracking stub with plan ref + `replace before Ready for Review`; no hidden `planned_new_paths`/future helper behavior without a separate helper/schema plan
- [ ] `## Acceptance criteria / DoD`: не общие слова — заполнены обязательные checklist’и из шаблона (backend/domain + UI если нужно)
- [ ] API/payload field parity (if touching API/payload canon): changed payload fields are listed exactly with emitter/helper path and regression assertion/readback, or explicit `N/A (why)`
- [ ] `## Visual Acceptance`: если есть UI — заполнен target-declared visual contract (modes/endpoint/account/harness) или explicit `N/A (why)`, плюс `### Visual checks (screenshots required for UI tasks)` с путями/шагами, проверкой и именами скриншотов.
- [ ] Risky runtime invariants: если task risky по visual/layout/visibility/default-state/access semantics, в `## Tests` есть 1–3 named `critical runtime invariants`, и для каждого зафиксированы `hook/test proof`, `runtime/browser proof`, `alternate surfaces / bypass paths`, включая same-surface `action/mode/state` variants там, где они релевантны (или explicit `N/A (why)` для control case)
- [ ] `## Tests`: разделено “что написать/поправить” vs “что прогнать”; указаны файлы/кейсы/границы (не оставлять кодеру выбор “тест или логика”)
- [ ] `## Commands`: команды copy‑paste runnable (с явным интерпретатором/окружением, как требует шаблон); если wrapper/prompt дал concrete `PYBIN`, plan + code draft используют тот же interpreter spelling во всех proof/command surfaces, без смеси `python3` / `$PYBIN` / absolute path
- [ ] `## Q&A log`: нет open‑вопросов; ответы “вкручены” в `Scope/Acceptance/Tests/Commands` (не остались только в логе)

### Arch review checklist (Architect; before `Done`)
- [ ] `## Review artifacts` заполнен ссылкой на review‑файл; в review‑файле есть “Arch review”
- [ ] `## Review artifacts` materialize-ит ровно один live path для текущего bundle; alternate route не лежит вторым literal path “на всякий случай”, а живёт только как scope-flip rule до реального изменения bundle
- [ ] “Discovered suggestions” обработаны: все `Coder suggestions`/`Reviewer suggestions` либо “вкручены” в `Scope/Acceptance/Tests/DoD`, либо явно вынесены в `Follow-ups (deferred)` (без молчаливого игнора)
- [ ] Visual evidence (if UI): скриншоты не только “существуют”, но и реально доказывают checks (Architect открыл/посмотрел, а не только `test -s`)

## Visual Acceptance (browser, UI tasks)
(Если UI не меняется — ставим `N/A (why)`. Правила, примеры и must-not-regress guidance — в `docs/plans/README.md` → `Visual Acceptance (UI-gate)`.)

### Visual gate (S1)
- Любая визуальная поломка/ошибка = **S1 Blocker**; status вперёд не двигаем до устранения и фиксации в review‑артефакте.

### Visual env (обязательно для UI-задач)
- Modes to test: `N/A (why=...)` или `<target-declared mode(s)>`
- Endpoint/port: `N/A (why=...)` или `<target-declared endpoint/port>`
- Visual evidence: `docs/code_reviews/assets/<REVIEW_BASENAME>/...`

### Login (Reviewer)
- Accounts/credentials: `N/A (why=...)` или `<target-declared role/account; secrets redacted>`

### How to run (Reviewer)
- Status: `N/A (why=...)` или `<target-declared status/readback command>`
- Start: `N/A (why=...)` или `<target-declared start command>`
- Stop: `N/A (why=...)` или `<target-declared stop command>`
- Preconditions: `N/A (why=...)` или `<repo-backed discovery/seed step>`

### Visual checks (screenshots required for UI tasks)
- `Mode: <target-declared mode>` — `Check: <target path/entrypoint> — <что проверяем> — Screenshot: <filename>`
- Truth source: `<target-declared structural/runtime proof>`; screenshot OCR/template matching/pixel search — debug-only, а не acceptance truth source.
- Perceptual fallback: screenshot OCR / template matching / pixel search = debug-only; built-in `LLM image reading` over captured canonical artifact = bounded fallback, not a substitute for missing helper decision
- Harness classification: `harness drift vs live regression` rule for helper-red/live-green cases (или `N/A (why)`)
- Deferred lane: if visual proof moves to follow-up/e2e/post-deploy, keep this subhead and write exact `N/A (why=...; follow_up_owner=...; ref=...)`; do not replace the whole `## Visual Acceptance` block with one paragraph.

### Visual regression scenarios (docs/smoke_visual.md)
- `N/A (why=...)` или `<target-declared scenario ref in docs/smoke_visual.md#...>`.
- Deferred lane: `N/A (why=...; follow_up_owner=...; ref=...)`.

### Perf checks (optional; recommended for perf tasks)
- `N/A (why)` или список `URL/path + action + expectation`

## Tests

### Critical runtime invariants (required for risky UI/layout/visibility/default-state/access tasks)
(Полные правила и примеры — в `docs/plans/README.md` → `Critical runtime invariants (risk-based UI handoff)`.)
- `N/A (why)` если task control/non-risky и alternate-surface/runtime drift risk не просматривается.
- `Invariant #1: <короткое имя risky expectation>`
  - `Risky touchpoints/surfaces:` `<file/route/partial/endpoint/mode-role exception>`
  - `Hook/test proof:` `<какой server/template/test signal удерживает contract>`
  - `Runtime/browser proof:` `<какой живой check в браузере доказывает contract>`
  - `Alternate surfaces / bypass paths:` `<page/fragment/list/api/supporting endpoint/same-surface action/mode/state/default/non-primary carrier variant>` или `N/A (why)`
- Если риск живёт в normalized/default state или non-primary carrier, назови этот carrier прямо здесь; `OOB`, hidden-field и selected slug используй только как repo-local examples, а не как обязательный общий словарь.

### Что написать / поправить
- `<tests/docs/smoke updates>`

### Что прогнать
- `<targeted tests / linters / smoke commands>`

## Commands
(Команды должны быть copy-paste runnable. Конвенции по interpreter, target-declared profile/harness и evidence — в `docs/plans/README.md` → `Tests / Commands / Evidence`.)

## Verification rerun / exec handoff
(Reusable verification surface. `.planveyor.session.*` остаётся attach-pointer, а run/verification receipt живёт отдельно.)
- Mode: N/A (why=initial draft; set before handoff)
- Context source: N/A (why=initial draft; set before handoff)
- Prompt: N/A (why=initial draft; set before handoff)
- Command: N/A (why=initial draft; set before handoff)
- Expected artifact: N/A (why=initial draft; set before handoff)

## Evidence (chronological, append-only)
(Если в DoD/AC отмечено `[x]` — здесь должна быть запись/артефакт. Формат и связь с `## Tests`/`## Commands` — см. `docs/plans/README.md` → `Tests / Commands / Evidence`.)

## Review artifacts
- Code review (primary): `docs/code_reviews/...` (создаёт Reviewer; Architect дописывает “Arch review” в этот же файл)
- Doc review (docs-only): `docs/doc_reviews/...` (только если изменения ограничены `docs/**`)

> В active plan оставляй **ровно один** concrete live path для текущего bundle. Пока bundle docs-only, не materialize-ь параллельно `docs/code_reviews/...`; если non-doc carrier реально входит в final diff, flip делай literal-но и синхронно в plan + code draft + review route.
> Если после reviewer blocker был coder fix-loop и rerun, lifecycle один: до reviewer rerun plan несёт в `## Review artifacts` explicit stale/superseded + rerun note именно для текущего review file / текущего rerun window; historical notes из закрытых циклов не засчитываются. После rerun Reviewer переписывает этот же review-файл in place новым verdict/timestamp/target и он остаётся единственным current state.
> Compact no-findings reviews still need lane metadata, target snapshot parity, lane synthesis and canonical no-findings provenance; source refs can compress narrative only after opened/read proof.

---

## Q&A log (chronological, append-only)
(Формат, closing rules и intake flow — в `docs/plans/README.md` → `Q&A log: как фиксировать вопросы/ответы` / `Plan intake flow`.)

### Intake prompts (optional)
См. `docs/plans/README.md` → `Plan intake flow` / `Intake prompts (optional)`.

### Architect Q&A

### Planner Q&A

### Coder Q&A

### Reviewer Q&A

### Owner answers (если owner хочет писать прямо сюда)

---

## Suggestions log (chronological, append-only)

### Architect suggestions

### Planner suggestions

### Coder suggestions

### Reviewer suggestions

---

## Objections / risks log (chronological, append-only)

### Architect objections

### Planner objections

### Coder objections

### Reviewer objections

---

## Post-merge gate (before deleting plan)
Применяется **после merge в `main`** и перед удалением временных артефактов. Полный контекст: `docs/playbooks/post_merge_docs_hygiene.md`, `docs/playbooks/post_merge_audit.md`, `docs/playbooks/review_merge_range.md`.

- [ ] Если это multi-plan тема: есть audit‑report `docs/reviews/YYMMDD_post_merge_audit_<topic>.md` (или явно принято решение “audit не нужен”).
- [ ] Если был крупный merge/конфликты: есть merge-range review‑отчёт `BASE..HEAD` и Architect triage по нему (follow-ups заведены или принято “merge as is”).
- [ ] Решения/контракты перенесены в релевантный shared canon или literal target-declared carrier; не создаём несуществующие UI/runtime paths только ради closeout.
- [ ] Follow-ups не потеряны: перенесены в backlog или оформлены отдельным follow-up plan (без “молчаливого потом”).
- [ ] В канонике нет ссылок на удаляемые файлы: `rg -n "<FILENAME or PLAN_PATH>" docs`.
- [ ] Doc lint по канону проходит: `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_doc_lint` (или literal explicit bundle из `docs/playbooks/doc_lint.md`; это ordinary gate, не closeout gate).
- [ ] Контекст сохранён (если нужно): snapshot `docs/snapshots/*` (почему/альтернативы/риски; без “истории по планам” в каноне).

## Strict N-A parent no-draft contract

`strict N-A parent` is an active/parked `decomposition_wave` parent with a
valid N-A MAD, literal `Code draft(s): N/A (why=...)`, no live parent-draft
ref, and no same-stem file. Its only admission is oracle-derived
`not_required`; this never waives a required/ordinary plan draft.

- Candidate mode is inspection-only; it never grants stage, queue, or terminal authority.
- Use files-first materialization: create canonical child plans and same-stem child drafts before linkage.
- The derived parent planning bundle has one parent review and literal review assets, with no recursive child-target import.
- Preserve active-to-parked child-path continuity and no fabricated parent draft.

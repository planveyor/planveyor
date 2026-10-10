# Playbook: Analysis Wave

## Назначение

`Analysis wave` = planning-contour wave для узких аналитических задач, где
нужно получить проверенный вывод и repo-backed route, а не сразу менять продукт.

Это не новая роль `Analyst` и не pre-pipeline заметка. Волна использует тот же
конвейер ролей:

- `Architect`
- `Planner`
- `Coder`
- `Reviewer`
- `Architect arch review`

Carrier V1 `## Analysis pack` живёт в два этапа:

1. **Вход.** На статусах `Architect initial draft`, `Architect draft`,
   `Ready for Planner`, `Planner intake`, `Ready for Architect response` и
   `Architect response` pack — таблица `## Analysis pack` в самом
   `docs/plans/*.md`. Architect и Planner заполняют её там.
2. **С `Planner finalize` до `Done`.** Pack — отдельный repo-backed файл
   `docs/analysis_packs/<plan_stem>.md` с тем же заголовком `## Analysis pack`.
   Его создаёт Planner при переходе на `Planner finalize` (см. «Перенос pack
   при переходе на `Planner finalize`»), дальше с ним работают Coder,
   Reviewer и Architect.

Перенос нужен, потому что plan-resident pack нельзя отревьюить: origin
`PLAN_PATH` запрещён в `code_draft_meta.targets` для mutable `BUNDLE=current`,
Reviewer пишет lane receipt обратно в plan, поэтому current hash такого target
недостижим. Stable reviewed-content route = отдельный repo-backed
`docs/analysis_packs/<plan_stem>.md`, а `PLAN_PATH` остаётся lifecycle/status/
Q&A/Evidence carrier и отдельным member финального exact bundle. Поэтому
внешний pack обязателен ровно там, где обязателен code draft: с
`Planner finalize` и дальше, включая `plan_lint --as-status Done`. Без
строки-ссылки на этих статусах `plan_lint` выдаёт
`analysis_pack_authority_invalid:ref_missing`. План, ставший `Superseded` до
переноса, может остаться с pack в plan. Явная строка `analysis_pack_ref`
включает внешний pack на любом статусе.

Отдельный pack закрывает только self-invalidating hash boundary. Он не даёт
global semantic green, пока operational consumers читают дубли тех же полей из
unhashed plan: pack должен стать единственной operational authority, а plan —
хранить refs/accepted-route truth и lifecycle. Этот ownership split уже
реализован: oracle, `plan_lint` и planning-wave readback читают advisory-поля
только из standalone pack через общий resolver движка, а копии
`recommendation`, `route_recommendation`, `execution_budget` или
`stale_trigger` в plan при внешнем pack дают
`analysis_pack_authority_invalid:operational_duplicate`.

## Когда использовать

Используй `analysis_wave`, когда задача:

- bounded и repo-backed;
- требует источников, assumptions, options, recommendation и route decision;
- может закончиться seed dev plan, decomposition umbrella, Owner gate,
  follow-up/defer или rejection;
- не должна молча превращаться в product diff.

Не используй `analysis_wave` для:

- open-ended market/business discovery без inspectable repo sources;
- обычной dev-реализации с уже bounded executable plan;
- decomposition split, где уже принят large intent и нужно нарезать child plans
  (это `decomposition_wave`);
- QA route до materialized `qa_wave` carrier.

### Tiny bounded work / no mini carrier

В текущем V1 нет `analysis_pack_mini`, `analysis_pack_lite` или другого
small-runner-ready mini carrier для analysis. Tiny documentation/process/test changes,
которые уже bounded и не требуют отдельного source/options analysis review,
идут как обычный direct `developer_wave` seed/dev plan с normal proof, exact
targets и review route.

Маленький размер задачи или small-runner intent сам по себе не создаёт новый
`plan_meta.wave_family`, route enum, accepted-route carrier, queue admission
или `runner_admission` value. Если tiny task всё же требует source/options
analysis, используй полный `## Analysis pack` V1.

Reduced analysis carrier можно вводить только отдельным helper/lint/schema
планом после V4 pilot или runner-quality evidence, которые доказывают, что
overhead full pack реально стал blocker для безопасных tiny analysis
decisions. Будущий carrier обязан сохранить single accepted-route authority,
source coverage rules и explicit runner admission; он не применяется к
business/security/schema/migration/shared-contract decisions.

## Маркер и carrier

Для V1 analysis plan добавляй в `plan_meta`:

- `wave_family = "analysis_wave"` как canonical machine marker;
- `tags` могут зеркалить `analysis-wave` для поиска, но не являются routing truth.

Plan должен содержать `## Analysis pack`: до `Planner finalize` — таблицу V1,
после переноса — одну строку `analysis_pack_ref`. Для ordinary dev/review plans
этот раздел не обязателен и может быть `N/A (why=not an analysis_wave plan)`.

### Перенос pack при переходе на `Planner finalize`

Переносит Planner в конце `Planner intake`, до записи
`**Status:** Planner finalize`: хелпер code draft из шага 3 работает, только
пока статус ещё не требует code draft. На `Planner finalize` без draft
machine-authority readback становится `invalid`, и хелпер откажет; если план
уже там, верни `Planner intake`, сделай перенос и снова поставь
`Planner finalize`. `<plan_stem>` — имя файла плана без `.md`.

1. Создай `docs/analysis_packs/<plan_stem>.md`: заголовок `## Analysis pack` и
   под ним таблица V1 из плана целиком, с теми же field names.
2. В плане в `## Analysis pack` оставь одну строку таблицы с подставленным
   `<plan_stem>`:

   ```text
   | Field | Value |
   | --- | --- |
   | `analysis_pack_ref` | `docs/analysis_packs/<plan_stem>.md#Analysis-pack` |
   ```

   После закрывающей обратной кавычки допустима короткая пометка без других
   путей `docs/...`, без второго `#Analysis-pack` и без имён operational-полей.
   Строки `recommendation`, `route_recommendation`, `execution_budget` и
   `stale_trigger` в плане не оставляй: это `operational_duplicate`.
3. Создай code draft хелпером
   `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_code_draft_stub_from_plan <PLAN_PATH> --role Planner`.
   Хелперу нужен уже записанный `plan_meta.machine_authority_decision`,
   `code_draft_meta.machine_authority_decision_ref` он впишет сам; существующий
   draft он не перезаписывает. В `code_draft_meta.targets` должна быть ровно
   одна запись с этим pack: `{"path": "docs/analysis_packs/<plan_stem>.md", "kind": "doc"}`.
   Заглушки шаблона (`UNCONFIRMED` target, пример в `deleted_paths`) убери,
   `deleted_paths` — `[]`.
4. Внеси `docs/analysis_packs/<plan_stem>.md` в
   `## Documentation impact / provenance` → `Synchronous doc/registry targets`.
5. Поставь `Planner finalize` и проверь: `plan_lint.py PLAN_PATH` без
   `analysis_pack_authority_invalid` и `planveyor_plan_bundle --preflight PLAN_PATH`.

После переноса V1-поля живут только в файле pack. Строки-указатели
`promoted_route_refs`, `review_artifact_ref` и `arch_review_routing_ref` в нём
остаются `N/A (why=...)`: pack — reviewed target, и его правка после
`BUNDLE=current` snapshot делает review stale. Живые ссылки держит план:
`## Review artifacts` и `## Promoted route artifact`.

`analysis_pack.route_recommendation` не является accepted route truth. Это
проверенная рекомендация. Accepted route materializes только после
`Architect arch review` через promoted route artifact/status/linkage carriers.
Если route принят, но promoted artifact не материализован или next action не
записан как repo-backed carrier/ref, это blocker route closeout, а не допустимая
пауза "потом разберём".

### Authority mapping

`analysis_wave` использует общую модель из `docs/playbooks/docs_architecture.md`,
но не владеет ею и не вводит второй route/status enum. Здесь
`analysis_pack.route_recommendation` = `analysis candidate` на lifecycle-оси и
не создаёт accepted route truth; literal `## Promoted route artifact` вместе со
status/linkage materializes accepted lifecycle state. `canonical_owner`,
`writer` и `duplication_class` остаются field-level contract полями, а не
заменой общего writable-owner/enforcement/proof distinction.

## Planning contour interlock

`analysis_wave` и `decomposition_wave` живут в planning contour, но отвечают на
разные вопросы:
- `analysis_wave` выбирает или рекомендует route по inspected sources.
- `decomposition_wave` режет уже accepted large intent на child plans,
  `needs_analysis` children и deferred follow-ups.

Analysis не должен впитывать decomposition semantics или queue work from prose.
Если recommendation = `decomposition_wave`, accepted route должен создать или
обновить normal decomposition umbrella с `phase_overlay` carriers и schema из
`docs/playbooks/decomposition_wave.md`.

Если decomposition child возвращается как `needs_analysis`, returned artifact =
reviewed `analysis_pack` plus promoted route artifact. Только accepted route
после этого может стать dev child, decomposition child, human gate, defer or
rejection.

## Роли

Architect:
- задаёт `analysis_subject`, `desired_outcome`, constraints, non-goals,
  trust boundaries, execution budget and expected proof shape;
- решает, это analysis, decomposition, direct dev, human gate, defer или reject;
- после review принимает/отклоняет route и materialize-ит promoted route truth:
  seed plan, decomposition umbrella, Owner gate, follow-up/defer carrier or
  rejection receipt plus explicit next action.

Planner:
- владеет source contract: какие documentation/plans/code paths/archive/sibling canon
  искать и почему;
- фиксирует expected `analysis_pack` shape and review gates before Coder;
- при переходе на `Planner finalize` переносит pack в
  `docs/analysis_packs/<plan_stem>.md` и делает его target code draft
  (см. «Перенос pack при переходе на `Planner finalize`»);
- держит exact target bundle честным, если analysis даёт docs-only changes.

Coder:
- выполняет analysis и записывает inspected source refs, assumptions, options,
  recommendation, requirement slices and route recommendation в файл pack
  `docs/analysis_packs/<plan_stem>.md`, а не в plan;
- записывает в `scope_refs` только opened/read sources;
- не реализует product changes и не создаёт executable child plans, если
  promoted route slice явно не владеет этой materialization.

Reviewer:
- проверяет файл pack: source coverage, unsupported assumptions,
  contradictions, option quality, route clarity, no-duplicate-truth boundaries
  and handoff readiness;
- пишет findings в live review artifact, а не внутрь `analysis_pack`; сам pack
  не правит.

Architect arch review:
- принимает reviewed route или возвращает его;
- materialize-ит route truth в `## Promoted route artifact` плана, а не в
  prose memory; файл pack после review не правит.

## Analysis pack V1

Используй эти field names буквально. Future schema/lint work может их парсить,
поэтому не вводи synonyms без явного mapping в plan.

| Field | Owner / writer | Required when | Meaning |
| --- | --- | --- | --- |
| `analysis_subject` | Architect | wave intake | One bounded sentence naming what is being analyzed. |
| `desired_outcome` | Architect | wave intake | Decision or route the analysis must enable. |
| `actor_current_pain` | Architect/Coder | business/product analysis only | Actor, current pain and target behavior seed for decomposition or dev plans. |
| `scope_refs` | Planner/Coder | before Coder handoff and final pack | Repo-backed files/documentation/plans/code paths actually inspected. Retrieval hits not opened/read do not count. |
| `documentation_impact_seed` | Architect/Planner/Coder | every final pack | Source docs used, synchronous doc/registry targets, deferred docs follow-ups and provenance refs for next wave. |
| `constraints_non_goals_execution_budget` | Architect/Planner | before Coder handoff | Guardrails, non-goals, trust boundaries, execution budget and allowed expansion boundary. |
| `execution_budget` | Architect/Planner/Coder | final pack when route may continue | Helper-readable lifecycle budget: `budget_status`, `source_ref_floor`, `route_iteration_limit`, `needs_analysis_depth_cap`, `current_needs_analysis_depth`, `stop_owner`, `exhaustion_action`, optional `override_ref`. |
| `stale_trigger` | Architect/Planner/Coder | final pack when route may continue | Baseline/current для source subject/source refs, либо `change_ref=...; action=architect_recheck`, если accepted route надо перепроверить. |
| `question_refs` | Planner/Coder | final pack if any remain | Pointers to `## Q&A log` rows, not a second question list. |
| `assumptions` | Coder | final pack | Assumptions that affect recommendation; unsupported assumptions must be labeled. |
| `risks_escalation_triggers` | Architect/Coder | final pack | Risks, `needs_owner` triggers, security/integration/public API/canon-exception markers. |
| `canon_conflicts_updates_seed` | Coder | final pack | Canon conflicts, required canon updates and candidate `plan_meta.canon_updates[]` entries. |
| `dependent_inventory_mutable_surfaces` | Planner/Coder | final pack when shared carrier or implementation route is possible | Helper/adapter paths, dependent tests, dependent docs, known consumers, mutable/read-only surfaces and shared resources. |
| `options_considered` | Coder | final pack | Options with trade-offs and rejection reasons. |
| `recommendation` | Coder | final pack | Chosen answer or decision proposal. |
| `requirement_slices` | Coder | final pack when route is executable/decomposition | Downstream slices with `slice_kind = dev_candidate | decomposition_candidate | needs_analysis`. Executable candidates reuse the small-model-ready child contract. |
| `decomposition_sizing_rationale` | Coder/Architect | route is `decomposition_wave` | Entry sizing rationale (`direct` / `slim` / `full`) and axes for seed decomposition umbrella. |
| `reviewability_seed` | Planner/Coder | next route is executable | Proof-path class, mandatory lanes, preconditions, seed-discovery and reroute rule for next wave. |
| `runner_handoff_seed` | Planner/Coder | executable route is possible | Runner intent/readiness and fallback condition; not a route enum. |
| `route_recommendation` | Coder, reviewed by Reviewer | final pack | Primary route enum plus reason, prerequisites and target refs. |
| `promoted_route_refs` | Architect after arch review / Manager helper later | after accepted route | Pointers to seed dev/decomposition plan, follow-up, human gate row or rejection/defer carrier. In the standalone pack it stays `N/A (why=...)`; the live pointer is the plan's `## Promoted route artifact`. |
| `review_artifact_ref` | Reviewer | review | Pointer to live review artifact, not findings content. In the standalone pack it stays `N/A (why=...)`; the live pointer is the plan's `## Review artifacts`. |
| `arch_review_routing_ref` | Architect | arch review | Pointer to accepted routing status/linkage row, not duplicated decision prose. In the standalone pack it stays `N/A (why=...)`; the live pointer is the plan's `## Promoted route artifact`. |

### Field admission metadata

До helper/lint/schema enforcement каждое поле, которое становится
machine-readable, должно объявить:

- `canonical_owner`;
- `materialization_phase`;
- `duplication_class`: `literal`, `derived-ref`, `snapshot-only` or
  `not-materialized`;
- `writer`.

Pointer fields вроде `question_refs`, `review_artifact_ref`,
`arch_review_routing_ref` и `promoted_route_refs` являются refs на existing
carriers. Не дублируй full Q&A, review findings или arch-review decisions в
pack. Во внешнем pack строки-указатели, которые заполняются после review,
остаются `N/A (why=...)`: правка reviewed target после snapshot делает review
stale.

## Route enum

Нужен ровно один primary `route_recommendation`:

- `developer_wave`: enough requirements and proof shape for a bounded dev plan.
- `decomposition_wave`: scope is large/multi-surface and must be split into
  child plans.
- `human_gate`: business/product/security/canon decision cannot be chosen by
  agents.
- `defer`: topic is valid but not worth current execution; create backlog or
  follow-up carrier.
- `reject`: topic is invalid, duplicate, unsupported by repo facts or out of
  project boundary.

`developer_wave` and `decomposition_wave` are executable/planning-work
continuations. `human_gate`, `defer` and `reject` are non-executable outcomes:
they are valid only when the reviewed pack proves that no current executable or
decomposition work should proceed. They must materialize a gate, deferred
follow-up or rejection receipt with owner/re-entry/terminal reason; they are not
happy-path substitutes for creating the next plan.

`qa_wave` is not a V1 route enum value. QA-shaped output uses `defer` with a
follow-up reason until `qa_wave` has a materialized carrier and public command
surface.

T1 reserved taxonomy:
- `qa_wave` остаётся `defer`, а не active route truth.
- `post_merge_wave` остаётся `defer`; post-merge governance всё ещё живёт в
  existing harvest/audit/docs-closeout playbooks.
- `post_merge_state` = deferred optional metadata, а не `route_recommendation`
  truth и не helper-required field.

Runner/model choice не является route enum. Используй `runner_handoff_seed` и
promoted route/queue admission fields.

Small-runner intent ужесточает handoff/readiness checks; сам по себе он не
выбирает `decomposition_wave`. Используй `runner_handoff_seed`,
`runner_admission` и `small_model_ready_state` на том же promoted route or child
carrier.

## Requirement slices

Каждая запись в `requirement_slices` должна объявлять `slice_kind`.

`dev_candidate`:
- готов seed-ить bounded `developer_wave` только если закрывает
  small-model-ready child contract из `docs/playbooks/decomposition_wave.md`;
- обязан назвать outcome, local context, mutable/read-only surfaces, forbidden
  scope, inputs, outputs, proof lane, stop condition and expected reviewer lane.

`decomposition_candidate`:
- слишком широк для direct dev;
- обязан включать sizing rationale, decomposition axes,
  recomposition/integration owner and proof/review boundary.

`needs_analysis`:
- planning/analytics child, а не executable child;
- обязан держать `analysis_subject`, `desired_outcome`, source refs to inspect,
  `key_unknowns`, `trigger_for_promotion`, parent/consumer decision, non-goals
  and expected analysis review lane;
- закрывается reviewed `analysis_pack` + promoted route artifact;
- не может queue-иться как product/dev work.

## Source discovery minimum

Planner owns source contract. Coder выполняет его и записывает в `scope_refs`
только реально opened/read material.

Минимальные правила:

- retrieval hit alone is not a source ref;
- если required lane не дал полезного результата, запиши `NO RELEVANT HITS` с
  `query=...`, `lane=...` and `reason=...` / `why=...`;
- warning-first lint checks that non-`reject` routes have either concrete
  opened/read `scope_refs` or bounded `NO RELEVANT HITS` with `query=...`,
  `lane=...` and `reason=...` / `why=...`;
- route-specific final fields are also checked warning-first: executable routes
  must carry requirement, reviewability and runner handoff seeds; gate/defer/reject
  routes must carry enough recommendation/source-discovery context to explain
  why no executable/decomposition work proceeds;
- для product/business topics проекта включай inspectable business canon
  вроде BRD, architecture, registry, schema или API docs, если применимо;
- unbounded business discovery routes to `reject`;
- business choices, которые agents cannot make, route to `human_gate`.

Используй existing retrieval surfaces, а не вводи новые:

- `planveyor_docs_index_build all`;
- `planveyor_docs_retrieve canon`;
- `planveyor_docs_retrieve plans`;
- `planveyor_docs_retrieve followups`;
- archive query/show for deleted docs when needed.

## Route lifecycle budget

Final packs, которые могут продолжиться в executable или decomposition work,
должны включать helper-readable rows `execution_budget` и `stale_trigger`.

Minimal `execution_budget` shape:

```text
budget_status=active; source_ref_floor=1; route_iteration_limit=1; needs_analysis_depth_cap=2; current_needs_analysis_depth=0; stop_owner=Architect; exhaustion_action=architect_recheck
```

Rules:

- missing or malformed lifecycle fields остаются warning-first для historical
  artifacts;
- explicit `budget_status=exhausted` route-ит к Architect, а не оставляет
  downstream Coder угадывать next action;
- `current_needs_analysis_depth > needs_analysis_depth_cap` route-ит к Architect,
  если нет literal Architect-owned override `override_ref=...`;
- stale detection опирается только на source subject/source refs: используй
  matching `source_subject_baseline/current_source_subject` или
  `source_refs_baseline/current_source_refs`, либо запиши
  `change_ref=...; action=architect_recheck`;
- calendar-age thresholds, content hashing и generic evidence churn вне этого
  контракта, пока отдельный helper/readback slice их не примет.

## Review gates

Reviewer должен отклонить или заблокировать `analysis_pack`, если:

- source coverage is missing or a recommendation lacks source refs;
- warning-first source-floor diagnostics are present and not explicitly accepted
  by Reviewer/Architect as current-run compatible;
- unsupported assumptions are not labeled;
- retrieval hits are counted as inspected sources without readback;
- broad scope is kept in analysis instead of routing to `decomposition_wave`;
- a meaningful choice has no rejected alternative or trade-off;
- more than one primary route is selected;
- executable/decomposition route lacks `documentation_impact_seed`,
  `dependent_inventory_mutable_surfaces`, `reviewability_seed` or honest
  `requirement_slices`;
- a `requirement_slices[]` entry lacks `slice_kind`;
- `needs_analysis` lacks `key_unknowns`, `trigger_for_promotion`, source refs,
  parent consumer decision or analysis review lane;
- `developer_wave` / `decomposition_wave` route has no concrete proof/evaluation
  seed for the next wave;
- `human_gate` / `defer` / `reject` still pretends to have executable proof
  instead of promoted route closure refs;
- `human_gate` / `defer` / `reject` is used as a vague escape hatch without a
  concrete gate/follow-up/rejection carrier and owner/re-entry/terminal reason;
- review findings, Q&A or arch-review decisions are duplicated in the pack;
- the pack smuggles product-code work into analysis closure.

## Promoted route boundary

Accepted route truth lives outside `route_recommendation`:

- route acceptance происходит в `Architect arch review`;
- promoted route artifact/status/linkage фиксирует, какой route accepted, какой
  artifact создан или почему executable artifact отсутствует;
- Manager/oracle не queue-ит work from recommendation prose alone;
- seed dev/decomposition plans ссылаются назад через `plan_meta.parent` или
  `depends_on`;
- non-executable outcomes materialize Owner gate, follow-up/defer or rejection
  carriers.
- accepted route without materialized `promoted_artifact_ref` and explicit next
  action is a blocker. For executable/planning continuations, next action is the
  target plan/umbrella status plus queue/admission path. For non-executable
  outcomes, next action is `await_owner_decision`, `deferred_followup_promotion`
  or `terminal_rejected` with a concrete carrier/ref and reason.

### Promoted route artifact V1

После reviewed `analysis_pack` Architect принимает route и materialize-ит
plan-resident promoted route artifact или route-specific carrier. Используй эти
field names literally, чтобы future helper/lint мог разобрать handoff без chat
memory.

| Field | Required when | Meaning |
| --- | --- | --- |
| `route_id` | every accepted route | Stable id for this accepted analysis route. |
| `source_analysis_plan` | every accepted route | Repo-relative source analysis plan path. |
| `source_analysis_pack_ref` | every accepted route | Ref to the reviewed pack: `docs/analysis_packs/<plan_stem>.md#Analysis-pack`. |
| `accepted_route` | every accepted route | `developer_wave`, `decomposition_wave`, `human_gate`, `defer` or `reject`. |
| `accepted_route_reason` | every accepted route | Why Architect accepted this route after review. |
| `review_artifact_ref` | after review | Live review artifact pointer. |
| `arch_review_ref` | every accepted route | Plan evidence/Q&A/status row where Architect accepted route. |
| `promoted_artifact_ref` | route-specific | Seed plan path, follow-up ref, human-gate row or rejection receipt. |
| `promoted_artifact_kind` | route-specific | `seed_dev_plan`, `decomposition_umbrella`, `owner_gate`, `followup` or `rejection_receipt`. |
| `next_action` | every accepted route | Queue/admission path, owner wait, deferred promotion trigger or terminal rejection disposition. |
| `revisit_when` | `human_gate` / `defer` | Concrete owner/re-entry trigger; required for non-executable gates/deferred work so helpers do not parse prose in `next_action`. |
| `subject_identity` | `human_gate` / `defer` / duplicate-sensitive `reject` | Exact subject key for repeated-defer/owner-gate checks; fuzzy/near-match subjects stay warning-only. |
| `duplicate_of` | duplicate `reject` only | Exact prior route/follow-up/source ref when rejection reason is duplicate; fuzzy duplicate refs stay warning-only. |
| `delivered_state` | `decomposition_wave` only | `framed`, `child_graph_ready` or `child_artifacts_materialized`; leave empty for other routes. |
| `promoted_artifact_status` | seed plans | V1 seed dev plans start at `Architect initial draft`. |
| `mapping_summary` | seed plans | Which pack fields map into the target plan. |
| `child_slice_policy` | `decomposition_wave` | How `dev_candidate`, `decomposition_candidate` and `needs_analysis` slices are admitted/deferred/returned. |
| `analysis_child_materialization` | `decomposition_wave` with `needs_analysis` | Default `materialized_now`; `map_only(reason=...)` only with explicit blocker. |
| `inherited_doc_impact` | seed plans/follow-ups | Documentation impact inherited from pack. |
| `inherited_guardrails_risks` | seed plans/human gates | Constraints, risks and escalation triggers inherited from pack. |
| `inherited_dependent_inventory` | executable routes | Helpers/tests/docs/known consumers and mutable surfaces inherited from pack. |
| `inherited_reviewability_seed` | executable routes | Proof-path class, mandatory lanes, preconditions and reroute rule. |
| `runner_intent` | executable routes | `frontier_default`, `small_runner_requested`, `small_runner_allowed` or `small_runner_required`. |
| `small_model_ready_state` | executable routes | `not_applicable`, `unchecked`, `ready` or `not_ready(reason=...)`. |
| `runner_admission` | seed plans/queue candidates | `frontier_only`, `small_runner_ok` or `small_runner_blocked(reason=...)`. |
| `queue_admission` | seed plans | `queueable_now`, `needs_planner`, `needs_owner` or `not_queueable` plus reason. |

Runner admission must come from explicit route/readiness evidence, not prose confidence:
- `small_runner_ok` requires a bounded exact bundle, local proof commands, no shared-contract/schema/security/runtime/default expansion, and a proof receipt with `runner_id`, `runner_result`, `small_runner_success=true`, `frontier_intervention=false|none`, and independent `reviewer_lane`.
- `small_runner_blocked(reason=...)` is the honest state for unavailable runner, partial output, tool/context failure or frontier intervention; it is not positive small-runner proof.
- `frontier_only` remains default for schema/migration/security/shared API/default/wrapper/model-policy changes or ambiguous proof ownership.

`## Promoted route artifact` is the single literal owner for accepted-route
fields after Architect arch review. Do not copy `accepted_route`,
`promoted_artifact_ref`, `queue_admission`, `runner_admission` or equivalent
route-receipt payload into `analysis_pack.promoted_route_refs`, review
summaries, evidence or docs-closeout receipts; those surfaces may carry refs or
historical snapshots only.

Promoted target artifacts may carry `plan_meta.promoted_from` as a
derived/read-only snapshot of the source route artifact. This target-side
receipt exists for readback/provenance only and must carry the authority note
`derived_read_only; source artifact is writable truth`.

For accepted `developer_wave` and `decomposition_wave` routes, helper/lint
validation treats `source_analysis_plan` and `source_analysis_pack_ref` as
required source-artifact fields. A target `plan_meta.promoted_from` is green
only when `source_plan` exists, is an `analysis_wave` plan, has a materialized
`## Promoted route artifact`, and the accepted route/artifact/admission fields
match the target readback. Direct Owner/external reviewer decomposition intake with explicit
`source_plan=N/A (why=...)` is not analysis-born and is handled by the ordinary
target-carrier shape/enums policy rather than this source-route parity check.

Pointer fields (`source_analysis_pack_ref`, `review_artifact_ref`,
`arch_review_ref`, `promoted_artifact_ref`) are refs, not copied payload.
Before helper/lint enforcement, every machine-readable field needs
`canonical_owner`, `materialization_phase`, `duplication_class` and `writer` in
the route-handoff plan or schema.

### Route-to-artifact mapping

- `developer_wave`: create a seed dev plan, link it back to the analysis plan,
  inherit doc impact/risks/dependent inventory/reviewability/requirement slices,
  set `promoted_artifact_kind = seed_dev_plan`, and start V1 status at
  `Architect initial draft`.
- `decomposition_wave`: create a normal decomposition umbrella using
  `phase_overlay = "decomposition_wave"` carriers; fill `delivered_state` only
  for this route and map child slices through the decomposition playbook.
- `human_gate`: materialize Owner Q&A or approval request; do not create a fake
  dev plan and do not present the gate as completed work. The source artifact
  uses `accepted_route=human_gate`, `promoted_artifact_kind=owner_gate`,
  `queue_admission=needs_owner`, `next_action=await_owner_decision(...)` and a
  `promoted_artifact_ref` pointing at the concrete Owner gate. It must also
  carry `revisit_when` and exact `subject_identity`.
- `defer`: materialize `followups_out[]` or a follow-up carrier with owner and
  reason. The source artifact uses `promoted_artifact_kind=followup`,
  `queue_admission=not_queueable` and
  `next_action=deferred_followup_promotion(trigger=...)`; it must also carry
  `revisit_when` and exact `subject_identity`.
- `reject`: record terminal rejection reason and source refs; no queue item.
  The source artifact uses `promoted_artifact_kind=rejection_receipt` and
  `queue_admission=not_queueable` plus `next_action=terminal_rejected`. If the
  reason is duplicate, it must carry exact `duplicate_of`; fuzzy duplicate refs
  are warning-only.

Machine-readable transition enums live in `docs/_meta/plan_vocab.json` ->
`planning_contour`. Oracle/queue/lint consumers must read that carrier when they
need status/route/queue semantics; this playbook remains explanatory.

### Route handoff review gates

Reviewer/Architect should block route acceptance when:

- accepted route lacks a materialized `promoted_artifact_ref` or explicit
  `next_action`;
- executable/decomposition route lacks `promoted_artifact_ref`;
- seed plan lacks reverse linkage to `source_analysis_plan`;
- seed plan loses doc-impact, risk, dependent-inventory or reviewability seeds;
- non-decomposition route fills `delivered_state`;
- V1 analysis-born seed dev plan attempts to bypass `Architect initial draft`
  by starting at `Ready for Planner`;
- queueability or small-runner admission is inferred from prose instead of
  explicit `queue_admission` / `runner_admission`;
- `human_gate` / `defer` / `reject` is treated as a happy path for avoiding
  current work rather than as a non-executable gate/deferred/terminal outcome
  with owner/re-entry/terminal reason;
- `analysis_pack.promoted_route_refs` or another non-artifact live section
  repeats literal accepted-route fields instead of pointing at the promoted
  route artifact;
- `needs_analysis` is queued as product/dev work before returned analysis
  closure.

## Deferred work

Не добавляй это молча внутри format slice:

- `analysis_pack_mini` / reduced analysis carrier;
- helper/lint/schema/oracle enforcement for pack fields;
- direct `qa_wave` route.

Promote them only through separate plans or rollout packets after the current pack
contract survives real runs.

## External-only V2 follow-up boundary

For a fresh `plan.v2`, analysis may identify deferred work but must not create
`plan_meta.followups_out`. Durable debt is a source-bound `followups.v2` row
with `(source_ref,item_id)`, typed status/disposition and exact source proof.
The four role declarations are read-only and ordered `Architect -> Coder ->
Planner -> Reviewer`; Manager freezes the tuple-owner union before the sole
serial/CAS writer applies it. A terminal source plan remains immutable, V1
rows stay compatibility-only, and V2 rows never become queue imports or receive
automatic historical backfill.

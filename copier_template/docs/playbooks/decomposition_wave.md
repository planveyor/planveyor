# Playbook: Decomposition Wave

## Назначение

`Decomposition wave` = planning-only phase overlay для крупных задач, которые нельзя честно протолкнуть сразу в обычный executable plan.

Это не новая роль и не отдельный forever-lane.
Это и не замена `umbrella/master-plan`: wave живёт поверх umbrella/master-plan и использует его как parent artifact.

Используются те же роли:
- `Architect`
- `Planner`
- `Coder`
- `Reviewer`
- `Architect arch review`

Но в этой фазе они выпускают planning artifacts, а не product diff.

## Contour boundary

`decomposition_wave` belongs to `planning contour` together with
`analysis_wave`. Она не является dev-contour exception и не даёт ordinary
`developer_wave` права делать broad analytics или child-graph creation как
скрытый implementation intake.

Контуры:
- `analysis_wave`: отвечает, сравнивает options, рекомендует route и возвращает
  reviewed `analysis_pack` + promoted route artifact.
- `decomposition_wave`: режет уже accepted large intent на promoted children,
  `needs_analysis` children и deferred follow-ups.
- `developer_wave`: исполняет только bounded executable handoff. Если внутри
  него появляется `split_required=true`, broad unknowns или child graph, это
  blocker/reroute в planning contour.

Planning-contour роли по умолчанию frontier-run: они держат исходный контекст,
route judgment и child-graph quality. Small/external runner admission начинается
только после small-model-ready executable child handoff или promoted route carrier.

## Как включать

В umbrella/master-plan:
- `plan_meta.phase_overlay = "decomposition_wave"`
- `plan_meta.phase_state = "active"`

Phase 1 keeps this dual-marker split:
- `analysis_wave` uses `plan_meta.wave_family = "analysis_wave"`;
- `decomposition_wave` uses `plan_meta.phase_overlay = "decomposition_wave"`
  plus `plan_meta.phase_state`.

T1 фиксирует этот split как `accept-current-split`: не переносим
`decomposition_wave` в `plan_meta.wave_family` ради симметрии с
`analysis_wave`. `post_merge_state` остаётся deferred optional metadata и не
нужен для decomposition overlay.

Machine-readable transition/readback vocabulary lives in
`docs/_meta/plan_vocab.json` -> `planning_contour`. E3/E4 oracle/queue helpers
must consume that carrier rather than re-encoding this playbook prose.

После успешного closure:
- обычно `plan_meta.phase_state = "parked"`
- umbrella остаётся reference artifact и не автоедет в новый implementation cycle.

## Как запускать

Owner-facing entrypoint для живого запуска этой волны = обычный `Manager collab`, но через decomposition wrapper или command-mode в уже открытом Manager TUI, чтобы не руками собирать `plan_set/init/run` и не создавать umbrella-plan отдельно.

Базовый TUI-старт:
- `planveyor_decomposition_collab_tui [PLAN_PATH] [--no-alt-screen]`

One-shot без TUI:
- `planveyor_decomposition_collab [PLAN_PATH]`

Только подготовить plan/context/session:
- `planveyor_decomposition_init [PLAN_PATH]`

Из уже открытого Manager TUI:
- `MANAGER_CMD=decomposition [PLAN_PATH] [-- <raw Owner intake>]`

Что делает wrapper / command-mode:
- если `PLAN_PATH` не передан — создаёт auto-seed `docs/plans/<YYMMDD_HHMM>_decomposition_seed*.md`;
- explicit `decomposition <PLAN_PATH>` transport не требует существующего target или `.planveyor.planpath`, но helper допускает только repo-local `docs/plans/*.md` текущего repo;
- если admissible `PLAN_PATH` ещё не существует и весь parent chain уже real/non-symlink — atomically создаёт umbrella/master-plan scaffold из canonical plan template;
- если plan уже есть, ставит active decomposition markers только на canonical template-neutral `Architect initial draft`: null route carriers, empty graph/canon arrays и template-placeholder bodies; marker absence сама по себе ничего не доказывает;
- compatible active decomposition umbrella reuse-ится byte-identical; populated/terminal/Superseded/`analysis_wave`/promoted/malformed plan, traversal/outside-root path, symlink и non-regular object fail-closed до plan/current-state/session/queue/staging mutation;
- ставит активный `PLAN_PATH` (если передан);
- валидирует, что plan реально active decomposition umbrella:
  - `plan_meta.phase_overlay = "decomposition_wave"`
  - `plan_meta.phase_state = "active"`
- при необходимости инициализирует `Manager`;
- дальше запускает обычный `manager collab` flow, где routing уже decomposition-aware.

Для `MANAGER_CMD=decomposition` raw Owner intake не передаётся в shell/helper: Manager вызывает только `planveyor_decomposition_init [PLAN_PATH]`, затем передаёт intake verbatim в первый Architect handoff и продолжает routing по oracle/`PLAN_PATH`.

Checked-in direct prompt остаётся authority для `/prompts:planveyor_decomposition`. Planveyor не копирует и не переписывает authentication, configuration или prompts.

Это один public entrypoint для выбранного проекта. Runtime выбирает только materialized shared prompt или declared target-local prompt; неизвестный profile остаётся ошибкой.

Важно:
- на входе этой wave допустима сырая задача/инициатива;
- wrapper рождает только scaffold/seed umbrella, а не финальную decomposition;
- саму decomposition дальше материализуют роли по конвейеру:
  - `Architect` → intake / framing
  - `Planner` → decomposition pack
  - `Coder` → umbrella + child plans + deferred follow-ups
  - `Reviewer` / `Architect arch review` → quality + closure
- если стартовали с auto-seed, `Architect` после intake может сам придумать осмысленный basename и переименовать файл через `planveyor_decomposition_seed_promote`, когда тема уже прояснилась.

## Entry decision

Direct `Developer wave` остаётся default. `Decomposition wave` нужна не потому, что задача “выглядит большой”, а потому что один executable contract больше не держит routing truth.

Перед split выбери честный путь:
- `direct`: один bounded executable plan ещё держит scope; хвосты можно явно вынести в `## Follow-ups (deferred)` / `Plan gaps`;
- `slim decomposition`: нужен split на 2-3 child plans, но без long-lived roadmap frame, multi-profile graph и тяжёлого backlog;
- `full decomposition`: нужен parked umbrella, 4+ child slices, rollout/multi-profile graph, много deferred debt или отдельное decomposition review/proof surface.

Практическая sizing-рамка:
- `1` child почти всегда означает `direct`, а не decomposition. Исключение: parent нужен как parked/reference carrier для уже существующего graph/routing context.
- `2-3` child plans = `slim decomposition`, если у каждого child есть свой delivery/proof boundary, owner/input/output/consumer и queue order.
- `4+` child plans = `full decomposition`: parent должен стать explicit umbrella с recomposition owner, deferred backlog policy и отдельной planning-artifact review lane.

Если direct path уже несколько раз переписывается без стабильного contract, это честный trigger на decomposition, а не повод ещё раз подлатать тот же vague plan.

### Lifecycle table

| Вход | Planning route | Output artifact | Next contour |
| --- | --- | --- | --- |
| Clear small formulation | `direct` / no decomposition | bounded seed dev plan | `developer_wave` |
| Clear complex accepted intent | `slim` или `full decomposition` | active decomposition umbrella with child map/queue/deferred split | promoted child `developer_wave` plans |
| Complex unclear subject | сначала `analysis_wave` | reviewed `analysis_pack` + promoted route artifact | `developer_wave`, `decomposition_wave`, `human_gate`, `defer` or `reject` |
| Decomposition child still unclear | `slice_kind=needs_analysis` | analysis child plan/pack + returned promoted route | parent decomposition recomposition or new child plan |

Unlisted transitions = `manual_only`: блокируй и проси Architect materialize-ить
route decision вместо guessing from prose.

State labels для owner-visible preview и manager readback:
- `bootstrap_only`: helper только создал/штампанул active umbrella; постановка и child graph ещё не доказаны.
- `framed`: Architect зафиксировал задачу, sizing decision и axes, но child graph ещё не materialized.
- `child_graph_ready`: child map/queue/deferred split описаны repo-backed, но child plan files ещё могут быть не готовы.
- `child_artifacts_materialized`: promoted child paths materialized, queue carrier согласован и helper/oracle не видит `decomposition_children_missing`.
- `parked`: umbrella принят как reference/non-executable parent; child execution живёт в promoted child plans.
- `blocker`: есть Owner/role/helper blocker, который запрещает execution handoff.

Owner-visible preview перед execution должен назвать: `state`, child count, `direct|slim|full` decision, queue order, dependencies, proof lanes, deferred items и open decisions. Preview не является proof сам по себе: queue readiness доказывают только repo-backed carriers (`## Child plan map`, `## Execution queue`, `plan_meta.next_plans[]`) и helper/oracle readback.

### Candidate-only materialization corridor

До materialization первого child-файла Planner может передать active umbrella как `candidate-only`, но это узкий lifecycle corridor, а не partial graph. Допустима только strict structural absence: нет concrete child path / `expansion_source`, `plan_meta.next_plans=[]`, в `## Child plan map` ровно section-level `N/A (why=...)`, а `## Execution queue` содержит только `Plan: N/A (why=...)` (и при необходимости `Resume parent`). Candidate contour slugs остаются semantic input, не links.

Corridor действует только в `Planner finalize`, `Ready for Coder`, `Coder intake`, `In progress`, `Ready for Architect response` и `Architect response`. `TBD`, named `N/A`, named/partial path, missing/non-lintable child, queue path либо mismatch — fail-closed, а не повод считать umbrella готовым. Planner handoff: `Planner finalize -> Ready for Coder`; Coder работает files-first, linkage-second; created child проходит template/lint gate и выходит `Ready for Planner`; parent получает `Ready for Review` только после materialized, carrier-consistent real graph.

Carrier boundary: `## Execution queue` владеет полным порядком child execution. `plan_meta.next_plans[]` — только bounded direct-navigation shortcut (`0..3`) для ближайших next slices; не копируй туда long/full queue, а stale/oversized значения очищай или сокращай до прямых next pointers. Для admitted strict N-A v3 current-review proof canonical child map (или valid equivalent queue fallback) остаётся полным hash input: bounded `next_plans[]` не может supply, replace или truncate его `N+N→2N` inventory.

## Выход волны

- один umbrella/master-plan как parent/reference artifact;
- явная рамка исходной задачи: бизнес-результат, актор/оператор, текущая боль, целевое поведение и non-goals;
- набор promoted child plans;
- объяснение, почему именно такой child split выбран;
- явный порядок выполнения child plans;
- deferred follow-up backlog;
- review artifact на planning artifacts;
- materialized `## Mechanism coverage`.

## Бизнес-декомпозиция

Если на входе не готовый технический scope, а сырая бизнес-задача/инициатива, wave обязана сначала зафиксировать смысл задачи, а уже потом нарезать child plans. Иначе есть риск получить красивую очередь из случайных планов, которая не закрывает исходный результат.

Umbrella/master-plan должен ответить:
- **Бизнес-результат:** что должно измениться для пользователя, оператора или бизнеса после всей волны.
- **Основной актор:** кто выполняет или получает новый flow (`client`, `manager`, `admin`, `operator`, `developer`, `owner` и т.д.).
- **Текущая боль:** что сейчас сломано, медленно, рискованно, неочевидно или требует ручной координации.
- **Целевое поведение:** какое наблюдаемое состояние должно стать правдой после закрытия child plans.
- **Non-goals:** что сознательно не входит в эту волну.
- **Guardrails / trust boundaries:** какие ограничения, approvals, sensitive zones и execution budget child plans не имеют права расширять молча.
- **Expected proof shape:** какой тип evidence должен доказать результат волны и promoted children.
- **Оси декомпозиции:** почему scope режется именно так, а не по случайным файлам/ролям.
- **Child plan map:** путь child plan, назначение, input/output/consumer, dependency position/type, acceptance/proof lane и причина, почему child можно остановить/ревьюить отдельно.
- **Queue policy:** `## Execution queue` или явная причина, почему очередь пока не готова.

Держи это в явных carriers:
- `## Business decomposition framing` — поля выше или `N/A (why=technical/process decomposition, not business task)`;
- `## Child plan map` — promoted children только как queue-ready candidates: `Plan`, `Purpose`, `Input`, `Output`, `Consumer`, `Depends on`, `Dependency type`, `Acceptance/proof lane`, `Independent-stop reason`, `Queue order`.
- `## Decomposition quality gate` — `solvability / completeness / non-redundancy`, mutable/runtime isolation, recomposition owner и state label для owner-visible preview. Эти поля должны быть helper-readable bullet/table rows, а не один summary paragraph.

Минимальный quality gate для split-а:
- `solvability`: child можно честно запустить сейчас, потому что понятны owner, inputs, dependency gate и proof route;
- `completeness`: umbrella + promoted children + deferred follow-ups покрывают исходный scope, обязательства и долг без потери в chat memory;
- `non-redundancy`: child plans не дублируют owner, proof burden, side-effecting work или один и тот же delivery unit без причины.
- `mutable_surface_runtime_isolation`: parallel/shared surfaces named or explicitly serialized;
- `recomposition_owner`: кто собирает child outputs обратно и какой integrated proof закрывает parent delivery.

Если один из этих трёх checks не держится, это ещё не promoted child. Это либо продолжение analysis decomposition, либо deferred follow-up.

Graph-shape warnings остаются review hints, не hard gates. Defaults:
- `0` materialized child plans on active umbrella + queue/roadmap signal требуют child graph или `decomposition_sizing_rationale`;
- `1` child требует `parent_reference_reason`, иначе обычно лучше direct dev plan;
- child count `>=10` требует `large_child_count_reason`;
- decomposition recursion depth `>4` требует `depth_override_reason`;
- cumulative nested child edges `>=20` требуют `cumulative_complexity_reason` или отдельный traversal/fan-out follow-up.

Reason values должны быть materialized prose, а не bare `N/A`, `TBD` или `none`.
Легитимные причины: parent держит recomposition proof/reference state, child graph
materialize-ится staged, full decomposition deliberately fan-out'ит независимые lanes,
или depth/complexity явно serialized и reviewable.

`Dependency type` использует закрытый словарь:
- `sequential`: successor ждёт predecessor completion;
- `parallel`: children можно dispatch-ить вместе только при explicit mutable/runtime isolation;
- `soft`: advisory scheduling signal, не hard blocker;
- `blocking`: successor ждёт predecessor плюс named proof/gate.

Child inheritance rule: promoted child наследует parent `why`, applicable guardrails/trust boundaries и proof obligations. Child может сужать scope/tool/runtime budget, но не расширять target, risk tier или approval boundary без нового Architect/Owner decision.

Наследование `## Documentation impact / provenance`: если parent держит carrier, promoted child должен унаследовать релевантные `Source docs used`, `Synchronous doc/registry targets`, `Deferred documentation follow-ups` и `N/A (why=...)` значения. Child может сузить target set до своего slice, но не теряет parent docs impact silently: нерелевантное помечается `N/A (why=...)`, deferred переносится с owner/reason, а synchronous docs targets попадают в child `code_draft_meta.targets` перед `Ready for Coder`.

Типовые оси разрезания:
- пользовательский vertical slice, если slice можно принять независимо;
- repo-local ownership boundary;
- rollout packet boundary для cross-repo доставки;
- data/migration risk;
- UI/browser evidence boundary;
- operational/debug tooling boundary;
- canon/prompt/process-only boundary;
- внешний dependency / third-party integration boundary.

Не режь задачу только по типу файлов (`schema`, `code`, `tests`, `docs`), если получившийся child нельзя принять независимо. Такой split выглядит аккуратно, но в пайплайне обычно превращается в имитацию прогресса: каждый child формально зелёный, а бизнес-результат всё ещё не собран.

## Analysis vs execution decomposition

`Analysis decomposition` = graph/dependencies/boundaries ещё меняются. Output
может быть `analysis_pack`, updated framing, `needs_analysis` rows, Owner gate
или deferred follow-up. Product code writes blocked.

`Execution decomposition` = decisions accepted, child/deferred split and
queue/readiness carriers materialize repo-backed. Output = promoted child plans,
child draft pointers, queue order, dependency/proof lanes и parked/reference
umbrella. Product code writes still live только в child `developer_wave` plans.

Если decomposition sub-contour начал писать product code, route уже вышел из
planning contour: останови волну и создай/продвинь bounded dev child instead.

## Проверка child boundary

Promoted child можно ставить в execution queue только если:
- у child есть один понятный результат;
- видны input, output, consumer, done condition и rejection/stop condition;
- есть одна причина существовать отдельно: другой owner, risk class, dependency boundary, retry cadence, approval path или proof boundary;
- child можно ревьюить без полного выполнения остальных child plans;
- зависимости перечислены явно и не сводятся к голому `B after A`: должно быть понятно, какой artifact/contract child получает от predecessor;
- mutable surfaces названы: какие файлы/модули/resources child может менять, какие read-only, какие shared;
- acceptance/proof lane не требует догадок;
- cross-repo часть либо вынесена в rollout packet, либо явно deferred;
- Owner/business decision уже закрыт или не нужен.

Если child зависит от незакрытого бизнес-решения, он не promoted child. Это deferred follow-up или Owner Q&A, а не строка в `## Execution queue`.

## Recursion stopping rules

Рекурсия нужна только пока добавляет control:
- новый owner или approval boundary;
- новый acceptance/proof boundary;
- новый dependency edge / queue order constraint;
- новый mutable/runtime isolation boundary;
- новый consumer/recomposition control point.

Если следующий уровень не добавляет ни одного такого control point, stop:
это polish-loop, а не decomposition value. Depth больше примерно `4` levels
требует explicit warning и reason в parent artifact. Нельзя продолжать рекурсию
только ради более красивых названий, активности `analysis/prep/notes` или
маленького runner'а.

## `needs_analysis` child semantics

`needs_analysis` child = planning work, not weaker dev child. Он допустим только
если parent materializes:
- `slice_kind=needs_analysis`;
- bounded `analysis_subject` and `desired_outcome`;
- source refs to inspect или explicit `NO RELEVANT HITS` lane;
- `key_unknowns`;
- `trigger_for_promotion`;
- parent/consumer decision, который использует returned route;
- non-goals and expected analysis review lane.

Closure = reviewed `analysis_pack` plus promoted route artifact/status/linkage.
До этого это не queueable product/dev work. Child rows named `notes`, `analysis`
or `prep` = decomposition smell, если они не несут full package.

### Recursion budget

`needs_analysis` может рекурсировать только внутри accepted analysis route
lifecycle budget. Default cap: `needs_analysis_depth_cap=2`.

Required lifecycle facts живут в returned analysis pack или promoted route
carrier:

- `current_needs_analysis_depth`;
- `needs_analysis_depth_cap`;
- `stop_owner=Architect`;
- `exhaustion_action=architect_recheck`;
- optional `override_ref=...`, если Architect явно принимает ещё один nested
  analysis round.

Если `current_needs_analysis_depth > needs_analysis_depth_cap` и literal
`override_ref` отсутствует, stop to Architect. Не queue-и ещё один product/dev
child и не придумывай narrower Coder scope из prose.

## Small-model-ready child contract

`Small-model-ready child` = promoted child plan, который можно отдать слабому runner'у без скрытого oral context, реконструкции parent-чата и догадок о том, что можно менять.

Small-model readiness = admission/readiness state, not a reason to start
decomposition. Direct bounded work может оставаться в `developer_wave`;
decomposition нужна для structural split. Runner suitability фиксируется на том
же child / promoted route / queue carrier, not in a parallel artifact route.

Playbook является canonical definition для field names. `docs/plans/_template.md` задаёт stable carrier location, `docs/plans/README.md` даёт примеры. Objective helper enforcement живёт в `scripts/plan_lint.py`, `scripts/plan_status_oracle.py` и `scripts/plan_queue.py`; этот контракт обязателен для promoted children как плановый quality gate.

| Field | Enforcement now | `N/A (why=...)` | Что должно быть literal |
| --- | --- | --- | --- |
| `Task outcome` | hard-required | only if child is not promoted | Один наблюдаемый результат child-а. |
| `Local context bundle` | hard-required | no for promoted child | Точные documentation/plans/reviews/helpers, которые надо открыть перед работой. |
| `Mutable surfaces` | hard-required | no for promoted child | Exact paths/path families, которые child может менять. |
| `Read-only surfaces` | hard-required | allowed if truly none | Context anchors, которые можно читать, но нельзя редактировать. |
| `Forbidden scope` | hard-required | allowed only with reason | Non-goals, соседние tempting changes, refactors/cleanup outside slice. |
| `Inputs from parent/predecessor` | hard-required | allowed only for independent first child | Artifact paths, dependency gates and predecessor outputs. |
| `Output to consumer` | hard-required | no for promoted child | Artifact/status/queue effect, который потребляет следующий child/parent/Reviewer. |
| `Acceptance/proof lane` | hard-required | no for promoted child | Exact commands/checks/receipts/review lane. |
| `Stop condition` | hard-required | no for promoted child | Когда возвращаться к Architect/Planner/Owner instead of guessing. |
| `Expected reviewer lane` | hard-required | allowed if no review lane applies | `code`, `docs-only`, `risk/contracts`, `visual` or explicit `N/A`. |
| `Runner suitability` | warning-first | allowed with reason while routing stabilizes | Recommended runner class plus fallback/degraded condition. |
| `Task size/complexity` | warning-first | allowed with reason | `small|medium|large`, why small runner can/cannot hold it. |
| `Readiness notes` | warning-first | allowed | Subjective clarity gaps, confidence notes, known brittle edge. |

Hard-required означает: promoted child не должен идти в queue, если field пустой, placeholder-only или держится на chat memory. Warning-first означает: field должен существовать и попадать в warning/readback, но пока не блокирует queue; Reviewer still may flag misleading/missing values as process risk.

`N/A (why=...)` допустим только если причина помогает downstream runner'у понять границу. `N/A` без причины или `TBD` в promoted child = неготовый handoff.

Small-runner admission matrix:
- `small_runner_ok`: bounded documentation/process/test/helper slice, exact mutable bundle is small enough for one focused runner context, proof commands are local, no schema/security/runtime/default/shared API expansion, and the proof receipt can name `runner_id`, `runner_result`, `small_runner_success=true`, `frontier_intervention=false|none`, and independent `reviewer_lane`.
- `small_runner_blocked(reason=...)`: small runner was requested or plausible, but runner is unavailable, produced partial output, hit context/tool limits, or needs frontier intervention. The reason must preserve runner identity/outcome and must not be counted as success proof.
- `frontier_only`: task changes shared contracts, schema/migrations, security, runtime/defaults, wrappers/model policy, broad cross-file architecture, or has ambiguous proof/reviewer ownership.

Bundle-size litmus is advisory, not permission: a tiny bundle is still `frontier_only` if it changes shared contract semantics, defaults or risk boundaries. Fallback after failed/partial/unavailable small-runner work is: record blocker/outcome, keep partial output traceable, then either rerun under frontier control or return to Planner/Architect if the task contract was ambiguous.

Для promoted decomposition target `plan_meta.promoted_from` остаётся
derived/read-only: source `## Promoted route artifact` является authority.
Lint/oracle должны fail-close, если `source_plan` отсутствует, не является
`analysis_wave`, не содержит materialized route artifact или если source
`accepted_route` / `promoted_artifact_ref` / queue-runner admission расходятся с
target readback. Direct Owner/external reviewer decomposition intake with explicit
`source_plan=N/A (why=...)` is a direct-source target, not analysis-born, and
therefore skips source-route parity while keeping ordinary target-carrier
shape/enums validation.

Examples:
- docs-only child: `Mutable surfaces=<declared playbook> docs/plans/README.md`; `Acceptance/proof lane=plan_lint + scoped doc_lint + exact git diff --check`; `Expected reviewer lane=docs-only`.
- process-helper child: `Mutable surfaces=<declared implementation path> <declared test path> docs/README.md`; `Read-only surfaces=linked playbook + prior review artifact`; `Stop condition=helper needs new CLI/status semantics outside listed paths`.
- runtime-code child: `Mutable surfaces=app/service.py tests/test_service.py`; `Forbidden scope=schema/migration/UI changes`; `Acceptance/proof lane=targeted unit tests + integration smoke`; `Runner suitability=small runner OK if target bundle <= listed paths, fallback to Coder if shared contract expands`.

## Parallel / recomposition checks

Параллельность не считается бесплатной. Если child plans потенциально идут параллельно, umbrella должен literal-но назвать:
- пересекаются ли `touches` / mutable surfaces;
- какие runtime surfaces общие: ports, DB branches, secrets, state stores, prompts/config/test baselines;
- shared resources изолированы, serialized или запрещают parallel dispatch;
- кто `integration_owner` для final fan-in;
- как child outputs собираются обратно: merge/rebase/order, integrated checks и parent-level acceptance.

Worktree изолирует code state, но не runtime state. Если runtime/shared resources не названы, child plans считаются sequential/serialized, а не parallel-ready.

Child completion не равен delivery completion. Parent/umbrella остаётся открытым, пока integration owner не подтвердил recomposed candidate и integrated proof.

## Failure modes

Reviewer/Architect arch review ловят не только template gaps, но и типовые провалы decomposition:
- `over_decomposition`: children стали activity/micro-steps без отдельной delivery value;
- `under_decomposition`: один child прячет несколько stable interfaces, risk boundaries или owner classes;
- `silent_scope_widening`: child тянет соседний scope под видом cleanup/refactor;
- `orphan_child`: output не имеет consumer-а, gate usage или delivery path;
- `hidden_dependency_drift`: declared independence конфликтует с shared schema/API/env/prompts/config/test baseline;
- `approval_or_risk_leakage`: cumulative risky branch спрятан в цепочке low-risk children;
- `parallel_conflict`: parallel заявлен без literal isolation/serialization policy.

В обычном `developer_wave` `silent_scope_widening` и
`hidden_dependency_drift` - это decomposition smells, а не разрешение продолжать
кодить в том же contour. Repair path: закрыть или заполнить
`plan_meta.scope_expansion`, reroute-ить в planning contour, либо записать
конкретный override / `integration_owner` / serialization policy. Валидные
active `decomposition_wave` carriers с child map и execution queue exempt; их
graph-shape diagnostics остаются отдельным lint семейством.

Локальный repair предпочтительнее global replan: чинить один child, один edge или один contract pin. Umbrella-wide replan нужен только если больше не держится parent intent, promoted/deferred split или graph-level routing truth.

## Контракт ролей

Роли не копируют полный список полей в свои prompts. Architect/Planner/Manager prompts должны ссылаться на `## Small-model-ready child contract` как canonical schema source, а конкретные child values materialize-ятся в repo-backed plan/code-draft carriers.

### Architect
- задаёт рамку decomposition;
- для бизнес-задачи сначала фиксирует бизнес-результат, актора, текущую боль, целевое поведение и non-goals;
- выбирает и объясняет оси декомпозиции;
- задаёт child-readiness framing: outcome, inherited guardrails/trust boundaries, expected proof shape, non-goals, stop-upstream condition и small-model suitability expectation;
- фиксирует expected child shape, promotion policy и closure contract umbrella;
- promoted children держит в `## Child plan map` + `## Execution queue`; `plan_meta.next_plans[]` использует только как bounded direct-navigation shortcut (`0..3`), а не mirror full queue; deferred items — в `plan_meta.followups_out[]` / `## Follow-ups (deferred)`;
- задаёт, какие общие механизмы downstream обязаны использовать или честно пометить как `N/A (why)`.

### Planner
- собирает decomposition pack;
- если pack пока `candidate-only`, передаёт его через `Planner finalize -> Ready for Coder` только в strict structural-absence форме; не использует generic same-contract reroute как замену Planner-owned handoff;
- проверяет child plan map: purpose, input/output/consumer, dependency position/type, acceptance/proof lane и independent-stop reason для каждого promoted child;
- заполняет child-level small-model-ready carrier: local context, mutable/read-only surfaces, forbidden scope, parent/predecessor inputs, output/consumer, proof lane, stop condition, reviewer lane и warning-first runner suitability;
- применяет `solvability / completeness / non-redundancy` gate и не promoted-ит child с неготовым owner/input/proof/dependency boundary;
- приводит порядок `## Execution queue` к dependency/reviewability order, а не к accidental order;
- тянет canonical links, backlog/index/registry surfaces и reuse anchors;
- оформляет `## Mechanism coverage` и критерии `promoted child` vs `deferred follow-up`.

### Coder
- не пишет продуктовый код;
- materialize-ит umbrella, promoted child plans, child code-draft pointers и deferred follow-up artifacts;
- держит machine-readable parent-child linkage и `plan_meta.followups_out[]`;
- для candidate-only pack сначала materialize-ит child files, затем links и queue (`files-first, linkage-second`); не превращает slugs в invented business contract;
- каждый materialized child становится template-complete `Ready for Planner`, а parent выходит `Ready for Review` только после graph/queue/meta parity;
- может создавать child-plan stubs/code-draft stubs, если это нужно для честного downstream handoff.

### Reviewer
- ревьюит planning artifacts, linkage, template/lint gates и `## Mechanism coverage`;
- ищет orphan scope, overlap, ложные promoted children, случайный child order, незакрытые business decisions, hidden dependency drift, parallel/runtime conflicts и тихо проигнорированные retrieval/governance surfaces;
- проверяет `solvability / completeness / non-redundancy` как promoted-child quality gate;
- не превращает review в product code review.

### Architect arch review
- подтверждает, что decomposition не потеряла смысл исходной задачи;
- утверждает promoted children;
- переводит umbrella в parked state или возвращает волну назад на доработку.

## Mechanism coverage

Для `decomposition_wave` должен быть materialized `## Mechanism coverage`, где видно:
- какие общие механизмы реально использованы;
- что ушло в `N/A (why)`;
- какие registry/index/backlog surfaces стали источником решений;
- какие machine-readable поля/refs обязательны для promoted child plans.

Минимальная helper-readable форма:

| Mechanism | Usage | Source refs | Proof anchor | State | Promoted child impact |
| --- | --- | --- | --- | --- | --- |
| `golden-path` | `<как использовано>` | `<declared target-local carrier>` or `"$PLANVEYOR_RUNTIME_ROOT/docs/guides/golden_paths.md#..."` for source-owned `tooling_process` | `<opened/read ref или event id>` | `used` | `<какие refs/fields наследуют children>` |

Названные mechanisms (`golden-path`, backlog, completed-plan index, retrieval, registry,
`plan_meta` linkage) не должны быть декоративными цитатами. Если mechanism не
использован, все missing proof/source fields пишутся как explicit
`N/A (why=...)`; bare `N/A`, `TBD`, empty prose и generic `ok` не закрывают
schema proof.

## Общий механизмовый слой

Если поверхность materialized в репозитории или профиле, wave не имеет права молча её игнорировать.

Типовой минимум:
- declared target-local Golden Path carrier и связанные entrypoints; для source-owned `tooling_process` — engine reference `"$PLANVEYOR_RUNTIME_ROOT/docs/guides/golden_paths.md"`;
- существующий repo-local backlog из `Context links`;
- docs retrieval/archive surfaces;
- `plan_meta` linkage (`phase_overlay`, `phase_state`, `followups_out`, `depends_on`, `canon_updates`);
- repo-native registry/index/reference bundle.

## promoted child vs deferred follow-up

### Promoted child
- отдельный bounded child plan;
- template-complete;
- без скрытых ownership дыр;
- по умолчанию выходит в `Ready for Planner`.

### Deferred follow-up
- ещё не bounded;
- или сознательно остаётся backlog item;
- не masquerade-ится под promoted child;
- живёт в `plan_meta.followups_out[]` и/или `## Follow-ups (deferred)`.

## Что не надо ломать

- `Decomposition wave` не создаёт роль `Decomposer`.
- `Decomposition wave` не отменяет и не переименовывает umbrella/master-plan.
- Не вводим отдельный status machine.
- Не подменяем обычный executable flow новой абстракцией.
- Не проталкиваем umbrella напрямую в продуктовый `Coder`/`Reviewer` lane после closure.

## Profile split

- Shared/default flow (`planveyor`) использует этот playbook как основной decomposition contract.
- Target-local consumer использует тот же skeleton, но объявляет собственные repo-local anchors, retrieval и harness surfaces в выбранном plan/canon.

## External-only V2 follow-up boundary

For `plan.v2`, a deferred decomposition discovery is not a child plan and not a
`plan_meta.followups_out` row. It is one source-bound `followups.v2` row with
exact `(source_ref,item_id)` and typed disposition. Four read-only role
declarations bind the same terminal commit/blob and baseline snapshot in order
`Architect -> Coder -> Planner -> Reviewer`; only the frozen union can enter
`scripts/followups_apply.py`. This keeps terminal parents immutable, preserves
V1 as read compatibility, and forbids V2 queue import, manual row edits and
automatic backfill.

## Strict N-A parent no-draft contract

`strict N-A parent` is an active/parked `decomposition_wave` parent with a
valid N-A MAD, literal `Code draft(s): N/A (why=...)`, no live parent-draft
ref, and no same-stem file. Its only admission is oracle-derived
`not_required`; this never waives a required/ordinary plan draft.

- Candidate mode is inspection-only; it never grants stage, queue, or terminal authority.
- Use files-first materialization: create canonical child plans and same-stem child drafts before linkage.
- The derived parent planning bundle has one parent review and literal review assets, with no recursive child-target import.
- Preserve active-to-parked child-path continuity and no fabricated parent draft.
- Versioned current-review branch выбирается только producer: `review_target_snapshot.v3` получает упорядоченные `source.child_plans` из `canonical_planning_child_paths` и сопоставляет каждый с одним same-stem child draft. Его exact hash basis — отсортированный уникальный carrier set `N+N→2N`, а не parent, Evidence, review/support files, child implementation/deletion targets или child reviews.
- Зелёное v3 proof означает только review freshness. Оно не активирует queue, не разрешает `run Q`, staging, создание parent draft или recursive child implementation selection.

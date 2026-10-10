# Plans — как работаем с `docs/plans/*.md`

## Зачем нужен plan
Plan в `docs/plans/*.md` — это **контракт на реализацию**: scope/acceptance/tests/DoD + зафиксированные ответы на вопросы.

Короткое правило (чтобы не тонуть в “хвостах”):
- **Бизнес‑фича / P0–P1 (берём в работу)** → сразу в dev‑plan со `**Status:** Architect initial draft` (дальше по конвейеру).
- **Follow-up / техдолг / “потом” (P2/P3)** → не в “черновики планов”, а в `docs/followups/*` (backlog), и только при созревании “промоутим” в отдельный dev‑plan.

Важно: plan — **временный** документ. Он не является “хранилищем знаний”.
- После реализации и merge в `main` plan можно удалять.
- Всё важное (решения/контракты/инварианты/гайд) должно быть отражено в канонических доках проекта (BRD/ARCH/Schema/API/UI/Registry/Guides); “хвосты” — в `docs/followups/*`, контекст/эволюция — в `docs/snapshots/*`.
- Перед удалением временных артефактов после merge используем `## Post-merge gate` в `docs/plans/_template.md` (см. также `docs/playbooks/post_merge_docs_hygiene.md`).
- В plan‑логах допускается разговорная лексика; в UI/коммитах/тестах/логах приложения и в канонических доках проекта — нет.
- Язык: постановочные human-facing секции плана (`## Как я понял задачу`, `## Problem`, `## Solution`, `## Scope`, `## Out of scope`, `## Decisions`, `## Acceptance criteria / DoD`, Q&A/риски/предложения/logs) пишем **русским текстом**. Английский оставляем только для кода, идентификаторов, путей, команд, enum/API names, field names и коротких literal source terms.

Если речь идёт о durable shared process invariant, не держим его только в `docs/plans/*`: accepted ADR layer живёт в `docs/adr/*`.
- `001` = `PLAN_PATH` как single semantic source of truth
- `003` = single live review route
- `004` = exact bundle truth / closeout
- `005` = rollout packet как handoff, а не execution

## Именование (чтобы не было коллизий)
Рекомендуемое имя файла (для новых планов):
- `YYMMDD_HHMM_topic.md` (пример: `260117_2011_roles_inputs_docs_audit.md`)

Почему время важно:
- мы часто делаем несколько планов за день по одной теме;
- сортировка по имени файла должна отражать порядок работ;
- меньше шансов “затереть” файл или ссылку.

Старые планы без `HHMM` не переименовываем.

## Status плана (кто ставит)
Канонический конвейер и “кто следующий” — `docs/roles/manager.md` и словарь статусов ниже.

Словарь статусов (v2; минимально нужное):
- `Architect initial draft` → Architect (живой диалог по постановке: фиксируем отдельный `## Как я понял задачу` + вопросы к Owner; обычно не переходим к `Architect draft` без явного “OK” от Owner. Исключение: если статус был возвращён только ради дозаполнения обязательных блоков шаблона / plan hygiene и после intake нет новых вопросов к Owner, нет изменения scope и нет новой развилки, Architect сам переводит plan в `Architect draft` без избыточного подтверждения.)
- `Architect draft` → Architect (черновик/скелет).
- `Ready for Planner` → Architect (контекст+scope готовы, ждём вопросов/детализации).
- `Planner intake` → Planner (вопросы/предложения/возражения по плану).
- `Ready for Architect response` → любой (если вопрос к Architect; ждём ответа).
- `Architect response` → Architect (ответы/решения; возвращает в `Ready for Planner`).
- `Planner finalize` → Planner (финализация для реализации).
- `Ready for Coder` → Planner (детализация готова для реализации).
- `Coder intake` → Coder (вопросы/предложения/возражения перед кодом).
- `In progress` → Coder (реализация; может быть выставлен Reviewer при возврате блокеров “просто фиксы”).
- `Ready for Review` → Coder (реализация завершена, DoD закрыт, можно ревьюить).
- `Reviewer intake` / `Reviewer code review` / `Reviewer visual review` → Reviewer (ревью‑этапы).
- `Ready for Arch review` → Reviewer (ревью завершено, ждём arch review).
- `Architect arch review` → Architect (arch review по ревью‑артефакту).
- `Superseded` → Architect (этот plan закрыт и заменён новым plan; продолжение работ — только в новом plan).
- `Done` → Architect (обычный `dev`-plan: exact-bundle local commit already closed, без push; review-only: triage verdict accepted для текущего flow).

Overlay caveat: для active `decomposition_wave` owner статусов тот же, но смысл planning-only. `Ready for Coder` = decomposition pack готов для materialization planning artifacts; `Ready for Review` = umbrella/child/deferred/linkage artifacts materialized; `Ready for Arch review` = planning-artifact review complete. Это не product implementation/review gate.

Формат `**Handoff statuses (кто ставит):**`:
- parser/tooling принимает обе separator forms между статусом и owner/comment: Unicode `—` и ASCII `-`;
- whitespace around separator обязателен; raw prose без явного separator не считается handoff row;
- semantics/status ownership от выбранного separator не меняются.

## Machine-authority admission

Перед downstream handoff план несёт ровно один
`plan_meta.machine_authority_decision` в единственном top-level `## Meta` JSON
fence. Обязательность определяется статусом и назначением плана, не датой или
форматом имени файла. В `_template.md` и на Architect-owned стадии до handoff
carrier может отсутствовать; присутствующий некорректный carrier отклоняется.
Это Architect-owned semantic carrier: допустимы полный `required` decision
или точный трёхключевой `not_applicable` object. `Evidence`, Q&A, review JSON,
code examples, target count и prose не заменяют authority.
`scripts/plan_lint.py:strict_plan_meta_json` и `scripts/plan_status_oracle.py`
используют один duplicate-safe результат. Missing/pending/rejected carrier
блокирует downstream handoff; ref, нормализованные пути и Owner confirmation
проверяются независимо от возраста или имени плана.

В новых `required` decisions Architect указывает
`"cutover_policy": {"kind": "status_and_purpose_handoff"}`. Валидатор также
читает точное прежнее значение `implementation_snapshot_basename_floor`
со всеми прежними полями, без переписывания данных или пересчёта digest/ref.
Оба значения проходят одинаковые проверки допуска по статусу; третье,
смешанное или изменённое значение недопустимо. Существующие планы не
мигрируются автоматически и не получают исключения из handoff-проверок.

Routing-readers (`plan_queue` activation/queue-seed lanes,
`planning_wave_readback`, `wave_telemetry_report`, `planveyor.zsh` routing helper
lanes) читают top-level `## Meta` только через единый strict reader
`scripts/plan_status_oracle.py:strict_plan_meta_json` (duplicate-safe):
routing/admission lanes получают fail-closed reason_code, readback/telemetry —
degraded diagnostics, не green summary. Governance-lane `docs_closeout.py`
остаётся на lenient `parse_plan_meta` by design.

Before `Ready for Coder`, Planner verifies only the derived
`code_draft_meta.machine_authority_decision_ref`: active
`{applicability,decision_id,carrier_sha256}` or N-A
`{applicability,reason_code,carrier_sha256}`. A draft never copies the semantic
core. Missing, duplicate, unknown, mixed or stale bindings fail closed; core,
schema, parser or route drift returns to Architect. Terminal consumers use the
generic oracle `route_guard_*` / `queue_closeout_ready` result, not a second
Manager parser.

## Schema version carrier
Для active artifact families используем один и тот же top-level header carrier сразу после `**Status:**`:
- `plans` → `**Schema version:** plan.v2`
- `followups` → `**Schema version:** followups.v2`
- `reviews` (`docs/reviews/*`) → `**Schema version:** review.v1`

Правила совместимости:
- `current` = файл явно несёт текущий literal family value.
- `legacy` = исторический versionless или explicit V1 artifact всё ещё читается/линтится по compatibility lane; V1 не требует массового backfill/archive rewrite.
- `unsupported` = файл явно несёт другой family token или неизвестную версию; сначала обновляем канон/контракт, потом создаём такой carrier.

Ограничения и ownership:
- canonical version source = top-level header line `**Schema version:**`; family-specific JSON/meta blocks остаются только для domain metadata и не дублируют schema version как второй truth source.
- current templates обязаны materialize-ить current family value; новые artifacts должны появляться из этих templates, а не через versionless copy-paste.
- `reviews` в этом контракте = post-merge carriers под `docs/reviews/*` (`merge notes`, `plan harvest`, `post-merge audit`); live reviewer artifacts в `docs/code_reviews/*` и `docs/doc_reviews/*` живут по своему grammar contract и не переименовываются в этот family автоматически.
- version bump делаем только когда меняется required header/section grammar или machine-readable meaning настолько, что старый carrier уже нельзя честно держать как `legacy`.
- prose-only clarifications, optional guidance и чисто редакционные правки без semantic drift version bump не требуют.

### Ordinary terminal `plan.v2` compact declarations

Для ordinary terminal `plan.v2` роль не публикует полный
`followups_declaration.v2` и не выбирает source/blob/baseline/family identity.
После helper-owned `begin`, checkpoint и `prepare-role` каждая роль в точном
порядке `Architect -> Coder -> Planner -> Reviewer` конструирует strict UTF-8
JSON object с ровно тремя keys: `role`, `proposed_rows` и
`role_no_items_reason`, standard file-write/edit tool записывает его в
helper-derived transient non-authority
`.tmp/followups_capture/<plan_stem>/<capture_cycle_id>/ordinary_v2_inputs/<Role>.json`
и возвращает Manager лишь diagnostic acknowledgement. Пустой `proposed_rows`
требует точную непустую причину; непустые rows остаются semantic `followups.v2`
input, но не дают роли права писать durable carrier. Compact input ограничен
16 384 bytes и reject-ит BOM, invalid UTF-8, duplicate keys, nonfinite values
и prefix/suffix/second JSON value.

Producing role затем передаёт свой exact compact JSON только helper-у через
`submit-ordinary-v2 --input-current --write`; returned
`ordinary_v2_role_submission_ack.v1` diagnostic-only. `--input-current` —
normal happy path, а explicit `--input -` остаётся compatibility API без pipe,
heredoc или PTY requirement. Manager не выбирает и не получает leaf
payload/path как binding input и вызывает только canonical-slot readback:

```zsh
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py followups_capture.py bind-ordinary-v2 \
  --project-root . --plan-ref "$PLAN_PATH" --capture-cycle-id "$followups_capture_cycle_id" \
  --role <Architect|Coder|Planner|Reviewer> --submission-current --write
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py followups_capture.py freeze-ordinary-v2 \
  --project-root . --plan-ref "$PLAN_PATH" --capture-cycle-id "$followups_capture_cycle_id" --write
```

Malformed/non-green current leaf останавливает lane. После repair допустим
только explicit same-cycle redispatch той же prepared role; Manager не делает
automatic retry и не запускает новый `begin`.

`bind-ordinary-v2` derives reachable terminal commit/blob, current worktree
equality and the complete current follow-ups baseline itself, materializes the
full declarations in helper-owned transient files and advances only the exact
prepared capture receipt. It has no profile/recovery-plan/family selector.
`freeze-ordinary-v2` accepts only that current cycle and ordered complete
family; it records a compact-binding marker with bound role hashes and frozen
manifest digest. Zero union performs no durable write and reads as
`external_clean_noop`; nonempty union still uses only existing
`scripts/followups_apply.py`, then `read_capture` accepts solely the exact
marker-derived canonical carrier. Any foreign, extra, stale or generic
manifest/object delta remains fail-closed.

Public full-envelope `freeze-v2` remains diagnostic compatibility for its
existing callers only. It cannot create the ordinary compact marker or satisfy
ordinary post-apply/staging authority. V1/versionless role output retains its
separate `NO FOLLOWUPS`/`Created:` control grammar.

### Missing ordinary-V2 frozen-manifest bootstrap

`followups_bootstrap_admission.v1` is a helper-derived, read-only permission
for exactly one otherwise deadlocked ordinary terminal `plan.v2` transition;
it is neither reconciliation truth nor a durable writer.  `state=ready` is
valid only for `reason=missing_v2_frozen_manifest` when the explicit terminal
plan ref, current committed terminal commit/blob/SHA-256 identity, lexically
absent canonical frozen-manifest path, and no active or ambiguous capture all
match.  Empty, malformed, stale, foreign, symlink or directory manifests,
legacy/versionless sources, source/HEAD/object drift, and stale or tampered
admission objects are `blocked`, never treated as absence.

The admission bypasses only the pre-family `followups_clean` predicate.
`begin` independently rederives it immediately before it publishes the fresh
capture cycle, then the normal `Architect -> Coder -> Planner -> Reviewer`
compact bind/freeze family, post-freeze reconciliation, process-improvement
and final-docs proofs remain mandatory.  Durable rows still pass solely
through `scripts/followups_apply.py`; do not hand-write a manifest, invoke a
generic historical selector or `freeze-v2`, switch the active plan/saved queue,
or use a legacy bridge as a bootstrap substitute.

### V2 external-only follow-ups

Новый `plan.v2` не содержит `plan_meta.followups_out`: deferred truth — только
одна durable `followups.v2` row в `docs/followups/*`, идентифицированная точной
парой `(source_ref,item_id)`. Row несёт `status`, `plan`,
`disposition_kind`, `disposition_ref`, `disposition_commit_oid` и `reason`;
для `status=open` все disposition-поля literal `null`. Поэтому `open` с
current-cycle exact proof — это корректный `external_clean`, а не незавершённый
terminal delivery.

V1/versionless plans и rows остаются только read-compatibility lane: их не
переписывают, не backfill-ят и не импортируют в V2 queue. Terminal plan
immutable. Перед durable write четыре read-only declarations строго в порядке
`Architect -> Coder -> Planner -> Reviewer` должны связывать один terminal
commit/blob и один baseline snapshot; Manager freeze-ит sorted unique tuple
union и owners, а единственный writer — `scripts/followups_apply.py` с serial
CAS. Missing/stale/overlap/source drift требуют нового полного declaration pass,
а не ручной правки row или plan.

Promotion не создаёт hidden pending state: `prepare` materialize-ит target
artifacts при строгом `open`, затем Commit A фиксирует их bytes, после чего
`finalize` через sole writer сравнивает tuple/row digest и reachable
commit/blob. Только exact retry идемпотентен.

Опциональный legacy bridge не делает V1 row writable: V2 row может нести только
полную hash-bound тройку `legacy_row_ref=plan_meta.followups_out[N]`,
`legacy_plan_sha256` и `legacy_row_sha256` для одного explicit `plan.v1`
source. Missing/stale/duplicate/hash-mismatched mapping остаётся red, без
summary matching или automatic backfill.

### Узкий terminal `plan.v1` bridge readback

`planveyor_docs_closeout` читает terminal `plan.v1` только через текущий полный
inventory `docs/followups/*.md`: для каждой локальной open row требуется ровно
один lint-green `followups.v2` item с exact `(source_ref, legacy_row_ref)` и
валидными `legacy_plan_sha256`/`legacy_row_sha256`. Его row digest
пересчитывается из текущих durable bytes и возвращается как proof; retained
declaration или `.tmp/followups_capture/.../v2_frozen_manifest.json` не
являются authority для последующего readback.

Полное уникальное покрытие даёт `external_clean` даже если V2 row остаётся
`status=open`: это externalization, а не вывод о terminal
`handled`/`cancelled`/`promoted`. Missing или partial coverage сохраняет
`open`; malformed explicit V2, stale hashes или duplicate identity дают
`external_invalid`. Reader не использует summary/path similarity, first-match
или backfill V1 bytes. Этот compatibility bridge не открывает generic source
selector и не меняет sole-writer boundary `scripts/followups_apply.py`.

## Быстрый просмотр “какие планы живые” (zsh helpers)
Если используешь zsh helpers из `scripts/planveyor.zsh`:
- Список активных планов (все, кроме `Done` и `Superseded`): `planveyor_plan_list`
- Планы по статусу (substring match, case-insensitive):
  - `planveyor_plan_list_status "architect initial draft"` — все черновики постановки (лучший индикатор “планов стало много”)
  - `planveyor_plan_list_status "ready for planner"` — очередь на Planner
  - `planveyor_plan_list_status "ready for coder"` — очередь на Coder
  - `planveyor_plan_list_status done` — все `Done` планы (кандидаты на post-merge cleanup после harvest/canon sweep)

## Plan type (dev vs review-only)
Поле `**Plan type:**` живёт в header plan (см. `docs/plans/_template.md`) и нужно, чтобы роли не путались в ветках.

- `dev` — обычный plan на разработку (можно/нужно возвращать статусы на Planner/Coder и фиксить код по plan).
- `review-only` — контракт на ревью (без кодовых правок в рамках этого plan; любые фиксы делаем отдельным follow-up `dev` plan).

## Shared core vs profile-local examples
Если `planveyor` обслуживает несколько repo-profile, каждый новый process slice сначала раскладываем на две части:
- shared core: repo-agnostic invariant, который должен одинаково переживать profile switch;
- profile-local carriers/examples: vocabulary, motivating incidents, proof surfaces и repo-local anchors для конкретного профиля.

Канонический generic набор для свежих cross-repo process slices:
- `alternate state / non-primary carrier proof`
- `shared contract carrier bounded fan-out`
- `truthful preconditions / harness drift vs live regression`
- `reopened-blocker classification / same-contract reroute`

`HTMX`, `OOB`, DOM/browser, visual shell/CTA и другие web carriers не становятся generic wording по умолчанию. Для target-local consumer тот же contract использует его explicitly declared transport, session, log, API или harness semantics.

## Wave / phase overlay
`planveyor` использует один role conveyor, но разные contour targets:
- `planning contour` = `analysis_wave` + `decomposition_wave`. Роли выпускают analysis packs, decomposition umbrellas, child graph/linkage, seed plans, follow-ups, Owner gates или rejection receipts. Product diff здесь запрещён.
- `dev contour` / `delivery contour` = `developer_wave` от bounded executable handoff до product/code/docs diff, review, Architect closeout и текущего post-merge governance tail.

Базовый executable flow в `planveyor` сейчас = обычный `developer_wave`, но мы не шумим этим в каждом плане отдельным полем.

Planning-contour continuity pointer:
- `"$PLANVEYOR_RUNTIME_ROOT/docs/guides/planning_contour_continuity.md"` - стартовая refs-only навигация движка для восстановления `analysis_wave` / `decomposition_wave` контекста между сессиями.
- Этот guide не является route/status/adoption truth; accepted route, queue admission, runner admission, review state and target adoption stay in the linked plan/playbook/helper carriers.

Важно: `phase overlay` не заменяет тип plan'а и не отменяет `umbrella/master-plan`. Если нужен decomposition, то артефакт остаётся тем же `umbrella/master-plan`, а `phase_overlay` только говорит, что этот umbrella сейчас идёт через специальную planning-only волну.

Allowed transition matrix V1 (всё, чего нет в таблице, считается `manual_only` / block до явного Architect route):

| Вход / state | Допустимый next | Required carrier | Запрещённое поведение |
| --- | --- | --- | --- |
| Clear small formulation | `developer_wave` seed/dev plan | bounded Scope/Changes/Tests/Commands + code draft | Включать `decomposition_wave` только из-за small-runner request |
| Clear large accepted intent | `decomposition_wave` umbrella | `phase_overlay`, `phase_state`, framing, child map, quality gate | Hidden child graph внутри ordinary dev plan |
| Complex unclear subject | `analysis_wave` | `wave_family`, `## Analysis pack` | Product diff или queue из analysis prose |
| Reviewed analysis route = `developer_wave` | seed dev plan | promoted route artifact with `queue_admission` / `runner_admission` | Direct `Ready for Planner` fast path без explicit future contract |
| Reviewed analysis route = `decomposition_wave` | decomposition umbrella | promoted route artifact + `phase_overlay` carriers | Второй child graph vocabulary вне decomposition playbook |
| Active decomposition child split | promoted child dev plans, `needs_analysis` children, deferred follow-ups | `## Child plan map`, `## Execution queue`, `plan_meta.next_plans[]`, `followups_out[]` | Deferred/prose child ideas queued as executable work |
| `developer_wave` discovers `split_required=true` or broad child graph | block and reroute to planning contour | Coder/Reviewer/Architect objection or route artifact | Продолжать implementation while inventing decomposition in dev lane |

Machine-readable transition vocabulary lives in `docs/_meta/plan_vocab.json` →
`planning_contour`. README/playbook prose explains the contract, but helper
consumers (`scripts/plan_status_oracle.py`, `scripts/plan_queue.py`,
`scripts/plan_lint.py`) must read the manifest carrier instead of re-encoding
the table as private constants.

Runner/model request не является route enum. Small-runner intent ужесточает executable handoff readiness и живёт в том же promoted route / queue carrier (`runner_admission`, `small_model_ready_state`, child contract fields); сам по себе он не включает `decomposition_wave`.

Текущие harvest/audit/docs-hygiene playbooks и лендившиеся post-merge governance carriers остаются delivery-contour tail after merge. Имя `post_merge_wave` зарезервировано только как future taxonomy/materialization topic; carrier count сам по себе не является route admission или revisit trigger, и active route требует отдельный repo-backed activation plan с route/proof/queue value.

T1 taxonomy decision:
- `qa_wave` = `defer`; QA-shaped работа допустима только как follow-up/deferred route до materialized QA carrier и public command surface.
- `post_merge_wave` = `defer`; текущей post-merge governance surface остаются harvest/audit/docs-closeout playbooks плюс лендившиеся governance carriers, признанные delivery-contour tail, а само имя и carrier count не являются route truth.
- decomposition marker split = `accept-current-split`; `analysis_wave` использует `plan_meta.wave_family`, а `decomposition_wave` использует `plan_meta.phase_overlay` плюс `plan_meta.phase_state`.
- `post_merge_state` = `defer`; позже это может стать optional metadata, но сейчас не является active route/schema truth.

Wave-doc reading map:

| Surface | What it answers | What it must not do |
| --- | --- | --- |
| `docs/playbooks/analysis_wave.md` | How to inspect sources, write/review `analysis_pack`, recommend route and promote accepted route truth | Split child graphs or implement product diff |
| `docs/playbooks/decomposition_wave.md` | How to frame/split accepted large intent, admit promoted children, `needs_analysis` children and deferred follow-ups | Become generic analytics or product implementation lane |
| `docs/roles/*.md` | Role-owned boundary and stop/reroute duties for any active wave | Duplicate full wave schemas |
| `docs/tools/prompts/*_status_driven.md` | Operational status routing and role-specific gates | Invent a second contour vocabulary |
| `docs/tools/prompts/manager_collab_pipeline.md` | Oracle/queue routing and owner-visible readback | Queue from prose-only route recommendations or child ideas |

Отдельно материализованный phase overlay на текущий момент только один:
- `plan_meta.phase_overlay = "decomposition_wave"`

Если overlay включён, рядом обязателен `plan_meta.phase_state`:
- `active` — umbrella/master-plan сейчас проходит planning-only decomposition conveyor через обычные роли;
- `parked` — decomposition уже закрыта, umbrella остаётся reference artifact и больше не автоедет в новый cycle.

Правила:
- overlay не создаёт новую first-class роль и не ломает общий status machine;
- если `phase_overlay` отсутствует, считаем план обычным executable flow без отдельного overlay;
- `QA wave` пока не materialized в `planveyor`: не выдумываем для неё поля/маршрутизацию до отдельного process slice.
- `post_merge_state` не является обязательным companion field для `decomposition_wave` или delivery-tail plans; если он понадобится, это отдельный documentation/helper/schema slice.

### Analysis wave / analysis pack

`analysis_wave` — planning-contour wave для узких repo-backed аналитических задач. Она использует тот же role conveyor, но её output = reviewed `analysis_pack` + promoted route artifact, а не product diff.

Для V1 analysis plans:
- `plan_meta.wave_family = "analysis_wave"` — canonical marker; `tags=["analysis-wave"]` допустимы только для поиска и не являются routing truth.
- `## Analysis pack` живёт в два этапа. До `Planner finalize` это таблица V1 в plan из `docs/plans/_template.md`. При переходе на `Planner finalize` (в конце `Planner intake`) Planner переносит её в `docs/analysis_packs/<plan_stem>.md` под тем же заголовком, оставляет в plan одну строку `analysis_pack_ref`, создаёт code draft хелпером `planveyor_code_draft_stub_from_plan` с target = pack и вносит pack в `Synchronous doc/registry targets`. С `Planner finalize` (и при `plan_lint --as-status Done`) plan без строки-ссылки получает `analysis_pack_authority_invalid:ref_missing`; `Superseded` plan без переноса допустим. Порядок переноса — `docs/playbooks/analysis_wave.md`.
- Подробный field contract, route enum, source-discovery minimum и review gates живут в `docs/playbooks/analysis_wave.md`.
- `analysis_pack.route_recommendation` — recommendation, не accepted route truth. Accepted route появляется только после `Architect arch review` и materialize-ится через promoted route artifact/status/linkage carriers.
- После accepted route заполняется promoted route artifact/carrier: `accepted_route`, `promoted_artifact_ref`, `promoted_artifact_kind`, reverse source linkage, `next_action`, `queue_admission` и, для executable routes, `runner_admission`.
- Accepted analysis route без materialized `promoted_artifact_ref` и explicit `next_action` — blocker route closeout, не ручная пауза. Для `developer_wave` / `decomposition_wave` next action указывает target plan/umbrella status + queue/admission path; для `human_gate` / `defer` / `reject` — concrete Owner gate, deferred follow-up promotion trigger or terminal rejection receipt.
- `human_gate`, `defer` и `reject` — non-executable terminal/deferred outcomes. Они не являются happy path и не заменяют создание seed plan/umbrella, если reviewed pack доказал executable/decomposition route.
- `## Promoted route artifact` — единственный literal owner accepted-route fields. `analysis_pack.promoted_route_refs`, review summaries, evidence и docs-closeout receipts могут хранить refs/snapshots, но не второй writable mini-receipt с `accepted_route`, `promoted_artifact_ref`, `queue_admission` или `runner_admission`.
- Promoted target plans may carry `plan_meta.promoted_from` as a derived/read-only
  snapshot of the source route artifact. It is not writable accepted-route
  truth; include `authority_note = derived_read_only; source artifact is writable truth`.
- V1 analysis-born seed dev plans стартуют с `**Status:** Architect initial draft`; direct fast path в `Ready for Planner` требует отдельного future Architect CENSOR contract.
- Direct `qa_wave` route в V1 запрещён; QA-shaped output идёт как `defer` с follow-up reason до materialized QA carrier.
- `requirement_slices` для executable/decomposition routes reuse-ят `docs/playbooks/decomposition_wave.md` → `Small-model-ready child contract`; `needs_analysis` explicitly не executable и возвращает reviewed `analysis_pack` + promoted route artifact.
- `decomposition_wave` route reuse-ит existing decomposition carriers (`phase_overlay`, child map, execution queue); route artifact может назвать `delivered_state = framed | child_graph_ready | child_artifacts_materialized`, но не создаёт второй child graph vocabulary.
- `plan_lint.py` emits warning-first diagnostics for route-specific `analysis_pack`
  completeness and inspected-source floor, reading the plan table before
  `Planner finalize` and `docs/analysis_packs/<plan_stem>.md` after the transfer:
  retrieval hits alone do not satisfy
  `scope_refs`, and `NO RELEVANT HITS` must name `query=...`, `lane=...` and
  `reason=...` / `why=...`.
  These warnings are reviewer aids; they do not promote
  `analysis_pack.route_recommendation` into accepted-route truth.

Ordinary `dev` / `review-only` plans без `plan_meta.wave_family = "analysis_wave"` не обязаны держать `## Analysis pack`; в шаблоне для них допустимо `N/A (why=not an analysis_wave plan)`.

### Planning-contour oracle/readback diagnostics

`scripts/plan_status_oracle.py --json` exposes additive warning/readback fields for planning-contour artifacts. They are diagnostics, not queue/lint hard gates and not a second route authority:
- Manager Owner-Q&A readback: `owner_qna_readback_state`,
  `owner_qna_readback_reason`, `open_owner_questions[]`,
  `owner_qna_issues[]`;
- marker/role: `planning_contour_marker`, `planning_contour_role`, `planning_contour_readback_state`, `planning_contour_readback_reason`;
- source route readback: `source_route_state`, `source_route_accepted_route`, `source_route_promoted_artifact_kind`, `source_route_promoted_artifact_ref`, `source_route_queue_admission`, `source_route_runner_admission`;
- target provenance readback: `promoted_from_state`, `promoted_from_authority_note`, `queue_activation_carrier_state`, `queue_activation_state`, `pending_activation`, `pending_activation_reason`;
- review freshness readback: `review_readback_state`, `review_readback_reason`.

`scripts/plan_status_oracle.py --json <PLAN_PATH>` also exposes top-level
`current_state` with schema `plan_current_state.v1`. `--current-state
<PLAN_PATH>` prints the same semantic readback in compact plain `key=value`
form. This readback is generated and read-only: it summarizes the header status,
oracle/runtime fields, source promoted route, derived `promoted_from` linkage,
live review readback and queue activation/closeout fields. It is not accepted
route truth, queue/runner admission, a review verdict, or a second status
source.

Docs-closeout/followups/process-improvement facts remain Manager closeout
context. If they are not supplied by `planveyor_docs_closeout` / Manager context,
`current_state` must report `contextual_unavailable` / `unknown` and fail
closed; it must not mine `final_docs_commit`, followups, process-improvement or
last-green claims from historical `## Evidence` prose.

Owner-Q&A readback uses append-only latest-status semantics per stable
`id=Qn`: an old `status=open` entry is not open after a later
`status=closed|superseded` entry for the same id. Malformed Owner-scoped Q&A
lines with only an id or status are surfaced through `owner_qna_issues[]` and
`owner_qna_readback_state=blocked`, so Manager prompts stop by oracle/helper
truth instead of guessing from markdown prose.

For source `## Promoted route artifact` and derived target
`plan_meta.promoted_from`, required field presence is not enough: route,
artifact-kind, queue-admission and runner-admission values must match
`docs/_meta/plan_vocab.json -> planning_contour` enums. Invalid enum values
stay warning/readback-visible as `missing_required`, not `valid`.
For fixture-backed accepted routes (`developer_wave`, `decomposition_wave`),
source artifacts also require `source_analysis_plan` and
`source_analysis_pack_ref`. A decomposition target `promoted_from` is valid only
when `source_plan` is a repo-backed `analysis_wave` plan, `source_route_ref`
points at that plan's `## Promoted route artifact`, and source
route/artifact/admission fields match the target readback.
Direct Owner/external reviewer decomposition intake may keep `source_plan=N/A (why=...)`;
that is not an analysis-born target, so source-route parity is skipped while the
ordinary `promoted_from` shape/enums/authority note still apply.

State contract:
- `planning_contour_marker`: `none | analysis_wave | decomposition_wave`.
- `planning_contour_role`: `ordinary | source_analysis | promoted_target | active_decomposition | parked_decomposition`.
- `source_route_state`: `not_applicable | absent | missing_required | valid`.
- object carrier states for `promoted_from_state` / `queue_activation_carrier_state`: `not_applicable | absent | null | non_object | missing_required | valid`.
- `review_readback_state`: `none | ok | live_blocker | stale_review_only | unknown`.

`stale_review_only` is allowed only when the same live review artifact still has a red header but `## Review artifacts` contains explicit same-artifact stale + rerun notes for the current cycle. A red live review artifact without that repo-backed note remains `live_blocker`.

For dual-lane reviews, historical plan-resident `reviewer_code_risk` JSON remains parseable evidence. Current risk snapshot selection is deterministic: `scripts/review_artifact_lint.py --origin-plan` prefers exactly one explicit current marker (`current=true` or equivalent), otherwise selects the latest sortable `written_at` / `run_id`; ambiguous unmarked multiples fail closed. Reruns should add compact risk receipts plus stable current target snapshot refs instead of duplicating bulky JSON or changing old fences to `json-stale`.

Routing remains owned by existing oracle fields (`status_norm`, `status_line`,
`route_guard_*`, `owner_qna_readback_state`, `open_owner_questions[]`,
`runtime_class`, `queue_closeout_*`, `decomposition_child_*`,
`small_model_*`) plus the queue/lint helper contracts. E4/E5 own any future
queue blocking or hard lint behavior based on these diagnostics.
Manager prompts must consume those helper fields as readback/debug/routing
inputs and must not maintain a private structural checklist for active
decomposition, source analysis, promoted targets, parked umbrellas or queue
activation.

### Planning-contour queue admission

`scripts/plan_queue.py` is the queue/import admission surface for planning-contour work. After E4, `Architect initial draft` queue admission is fail-closed:
- `plan_meta.queue_activation` must be a complete object carrier; `state=owner_approved|architect_approved` is queue-eligible, while `state=n/a` is intentional queue-collection ineligibility;
- the `state` value must validate against `docs/_meta/plan_vocab.json -> planning_contour.queue_activation_states`;
- absent, `null`, non-object, missing `state`, malformed state or unapproved enum values reject admission before a successful `.planveyor.planqueue.json` / `.planveyor.planqueue.log` write;
- a complete explicit `state=n/a` rejects the whole explicit/status/umbrella/append collection before state/log mutation with `queue_activation_admission_blocked: <repo-relative-plan>: queue_collection_ineligible; state=n/a`; this is a hard eligibility failure, not a Manager-mode skip, and it emits neither `skipped_incompatible[]` nor `skip_manager_mode`;
- for later statuses, an explicit `plan_meta.queue_activation.state=not_requested` (or malformed queue_activation carrier) also rejects queue admission; parked drafts must stay outside the queue until activation is materialized;
- approved activation with child entries in `## Execution queue` must also materialize `plan_meta.next_plans[]`; otherwise queue/lint reject the parent as an inconsistent activation carrier;
- `queue_activation_warning` text is diagnostic only on rejected/blocked or legacy readback paths, not a successful import signal.

`route_recommendation`, analysis summaries and future child-path prose are not queue authority. Queueable work must come from explicit repo-backed queue carriers, and `needs_analysis` remains planning-contour work unless a later accepted route promotes executable product/dev work. Dependency blocking is limited to unresolved dependencies present in the same imported queue; repo-wide dependency hardening belongs to E5/future plans.

Queue state contract:
- `.planveyor.planqueue.json` is mutable machine state, not an append-only audit log; `last_transition` must represent the canonical current queue transition.
- `.planveyor.planqueue.log` is the append-only audit trail.
- Materialization is explicitly mode-qualified: `planveyor_q_set <PLAN_PATH...> --for-manager-mode <manager-collab|manager-custom-pipeline>`; `--status` and `--from-umbrella` use the same carrier. Explicit append is `planveyor_q_append <PLAN_PATH...> --for-manager-mode <manager-collab|manager-custom-pipeline>` and does not gain status/umbrella expansion.
- Activation-capable commands require the live caller mode: `planveyor_q_next_json --manager-mode <MODE>`, `planveyor_q_advance_json <Done|Superseded> --manager-mode <MODE>`, and `planveyor_q_closeout_json --manager-mode <MODE>`. Queue state never infers or changes Manager mode.
- Generic executable terminal closeout is admitted only from one captured helper payload with literal `Done|Superseded`, `terminal_disposition=ordinary`, `queue_closeout_kind=terminal_status`, and `queue_closeout_ready=true`; a raw terminal header or closeout kind alone never authorizes mutation. `error=terminal_closeout_admission_rejected` with `reason_code=accepted_red_reconciliation_required|terminal_status_assertion_mismatch|terminal_disposition_invalid|terminal_closeout_not_ready` is a zero-write/no-fallback Owner stop: do not dispatch, retry/advance, rewrite status, or parse accepted-red recovery proof. `non_executable_ready` remains the separate valid helper branch.
- Collection mismatch is omitted from queue items and reported through canonical `skipped_incompatible[]` plus `skip_manager_mode` history. If every candidate is incompatible, queue state bytes remain unchanged while audit rows are appended.
- Pending activation mismatch becomes operational terminal `skipped_manager_mode` with matching state/log identity and no plan-status rewrite; compatible ordering continues. Missing/invalid mode carriers and path/lint/activation errors remain hard failures.
- `planveyor_q_set` refuses to replace any queue containing a non-terminal active item. Already-active mismatch and incompatible resumed parent are bounded stops, never auto-skips or alternate-Manager launches; a dependent of a skipped prerequisite remains pending with `depends_on_skipped_incompatible`.
- `planveyor_q_show` and history expose skipped count, required/actual mode and canonical reason but remain read-only.
- Legacy state where all items are closed, `parent_resumed_at` is set, but `last_transition.kind=resume_parent_pending` is repaired by `scripts/plan_queue.py` on load and logged as `state_repair reason=legacy_parent_resumed_transition`.
- New consumers should read through `scripts/plan_queue.py` / `planveyor_q_show` snapshots or treat raw `.planveyor.planqueue.json` as canonical only after helper repair has run.
- `planveyor_q_final_report` / `scripts/queue_finalizer_report.py` is a derived Owner readback after `queue_complete=true`: valid `skipped_manager_mode` items are operationally terminal but never semantic `Done|Superseded`; semantic terminal items still require terminal child status and one live green review/receipt. An activation skip binds the persisted item to the current audit lifecycle by exact `manager_mode_skip_id` (with matching `plan + order + completed_at`); older append-only rows for the same plan/order neither close a missing current receipt nor invalidate a valid current receipt. It fails closed on missing, ambiguous, red or inconsistent authoritative hosts and never mutates queue state, stages, commits or pushes.
- `planveyor_planning_wave_readback` / `scripts/planning_wave_readback.py` — derived operator readback для planning-wave carriers в repo-local `docs/plans/*.md`: показывает open `analysis_wave`, active/parked `decomposition_wave`, pending-child umbrellas, decomposition preview facts, provenance hops и accepted-route distribution. Default output держит короткий summary; detail lanes доступны через `--mode waves|preview|provenance|accepted-routes`. Helper должен оставаться read-only; accepted-route truth берётся только из `## Promoted route artifact`, `plan_meta.promoted_from` или oracle accepted-route readback fields. `Analysis pack.route_recommendation` prose остаётся recommendation-only, а child-map / execution-queue / promoted-route conflicts должны быть diagnostics с degraded confidence, а не green summaries.
- `planveyor_wave_telemetry_report` / `scripts/wave_telemetry_report.py` — derived per-wave telemetry and retrieval-corpus report. It groups plans from repo-backed wave carriers (`plan_meta.wave_family`, `plan_meta.phase_overlay`, `plan_meta.promoted_from`) and reads only local `.tmp/planveyor_docs_retrieve_*.jsonl` logs when present. Missing session/cost sources must stay `unknown` / `not_available`; token/cost values must not be inferred from prose, timestamps, model labels, filenames or `Analysis pack.route_recommendation`. The helper is read-only, does not import raw sibling/target repo logs, and reports inconsistent retrieval/route carriers as diagnostics with degraded confidence.

### Planning-contour lint/schema hardening

`scripts/plan_lint.py` hardens only repo-backed carrier shapes with reviewed
fixture coverage. For new E5-era plans:
- `plan_meta.promoted_from` is a derived target receipt; when applicable or
  present it must be an object with source refs, route/artifact refs,
  route/admission enum values and exact
  `authority_note=derived_read_only; source artifact is writable truth`;
- `plan_meta.queue_activation` must be an object if present, and is required
  for `Architect initial draft`; that status accepts only manifest-valid
  `owner_approved` or `architect_approved`;
- `plan_meta.scope_expansion`, when present, must be an object with
  `state`, `target_contour`, `source_ref` and `reason`, and `state` must match
  `planning_contour.scope_expansion_states`;
- source `## Promoted route artifact` rows for fixture-backed executable /
  decomposition routes (`developer_wave`, `decomposition_wave`) are hard lint
  errors when required source-analysis fields or manifest-backed enum values are
  malformed;
- decomposition target `plan_meta.promoted_from` is a hard lint error when its
  source plan is missing, non-analysis, lacks the promoted route artifact, or
  disagrees on promoted artifact / route / queue-runner admission fields;
- direct Owner/external reviewer decomposition targets with explicit `source_plan=N/A
  (why=...)` are not analysis-born and do not run source-route parity.

Warning/deferred lane:
- missing or `N/A` source route artifacts stay warning-first until an accepted
  route is materialized;
- non-decomposition route discrimination (`human_gate`, `defer`, `reject` and
  future V3/V2 return edges) does not become a hard lint gate from the V1
  happy-path fixture alone;
- review freshness/readback words such as `CURRENT-REVIEW-RED`,
  `stale_review_only` and historical blocker prose are not schema inputs.

## Umbrella / master-plans (aggregators)
Иногда один архитектурный вопрос приходится дробить на несколько bounded child plans. В этом случае допустим umbrella/master-plan, но только как scope/routing контракт, а не как бесконечный “общий dev-plan”.

Правила:
- umbrella/master-plan явно фиксирует, что executable handoff живёт только в child plans; direct executable `Ready for Coder` / `Ready for Review` / `Ready for Arch review` с umbrella-файла запрещён. В active `decomposition_wave` эти статусы допустимы только как planning-only role lanes поверх parent artifact и не считаются продуктовым executable handoff;
- после decomposition такой plan может временно стоять в `Ready for Planner` как parked/reference state для роутера; это не implicit handoff в новый Planner цикл и не обещание, что Planner должен что-то дописать именно в этот файл. Если все children terminal, `queue_closeout_ready=true`, direct executable handoffs `N/A` и AC закрыты, Architect может закрыть parked parent напрямую в `Done` без Planner/Coder pass;
- parked/reference umbrella должен быть machine-readable, а не prose-only: `Ready for Coder`, `Ready for Review`, `Ready for Arch review` в `**Handoff statuses:**` ставим `N/A (...)`, а `Context links` держит `Code draft(s): N/A (...)`. Promoted child pointers живут отдельно (`## Execution queue`, `plan_meta.next_plans`, `Child code draft(s)`), deferred/backlog pointers живут в `plan_meta.followups_out[]` и/или `## Follow-ups (deferred)`; иначе oracle/queue обязаны считать parent executable/ambiguous;
- `Ready for Architect response` для umbrella используется только при новом umbrella-level вопросе, cross-child contradiction/routing drift или когда нужен отдельный Architect-owned closure decision;
- `Done` на umbrella ставит только Architect и только когда umbrella реально исчерпан; `Superseded` — только если его заменяет новый umbrella/master-plan;
- `Done` на roadmap/scaleout umbrella нельзя ставить только потому, что текущая `## Execution queue` дошла до terminal child. Если title/scope/follow-ups ещё называют незакрытые tracks, перед `Done` должен появиться один из repo-backed исходов: successor activation plan materialized and linked (`Close-out routing`, `followups_out[]` and/or `next_plans[]`), parked/reference state with explicit non-executable discovery rule, or cancelled/handled tracks with Owner/canon refs. Queue completion closes only the current queue slice; it does not by itself close roadmap delivery.
- `scripts/plan_lint.py` держит это warning-first для legacy broad roadmap/scaleout `Done`: `plan_meta.followups_out[].plan=null` с non-cancelled tracks и без row-local plan/disposition, reference keep, superseded-by path или cancelled/handled disposition должен быть видимым lint finding. Файлы `plan.v2` и `plan.v1` fail-closed как `ERROR`; versionless legacy files остаются `WARN`, пока не пройдена отдельная migration/corpus boundary.
- `plan_meta.next_plans[]` закрывает только выбранные direct next slices и не считается blanket disposition для unrelated `followups_out[]` rows. Каждый `followups_out[].plan=null` row перед `Done` должен получить собственную судьбу: concrete `plan`, terminal `status/disposition` с reason/ref, explicit `superseded by`, parked/reference keep or no-successor/cancelled/handled rationale.
- selected roadmap child не закрывает транзитивный roadmap сам по себе: если child closeout говорит, что parent/roadmap должен выбрать `next bounded slice`, то до `Done` child обязан либо materialize-ить next activation/child carrier, либо перенести remaining tracks в repo-backed successor/follow-up carrier, либо записать explicit `no successor (why=...)` / cancelled / handled disposition. Формулировка `parent can choose next` без нового carrier = lifecycle drift; ссылка на существующий parent plan только в `Roadmap/queue sync` не считается successor carrier.
- parent resume after terminal child обязан записать next-step disposition: `next activation carrier`, `parked/reference keep`, `superseded by`, or `no successor (why=...)`. Пустой parent resume плюс оставшиеся roadmap tracks = lifecycle drift, даже если helper/readback green.
- routing/rollout backlog items держим в `plan_meta.followups_out[]` и/или `## Follow-ups (deferred)`, чтобы downstream роли не гадали, какой файл исполнимый.
- `## Out of scope` само по себе не является backlog-carrier'ом: если item умышленно сняли с active scope, но не отменили owner-решением, он обязан материализоваться в `plan_meta.followups_out[]` и/или `## Follow-ups (deferred)` с явной судьбой (`promote later | needs_owner | already tracked elsewhere | canon sync closed it`).

### Decomposition wave поверх umbrella
Если umbrella идёт через `plan_meta.phase_overlay = "decomposition_wave"`:
- это planning-only волна поверх тех же ролей (`Architect` / `Planner` / `Coder` / `Reviewer` / `Architect arch review`), а не новая роль `Decomposer`;
- umbrella/master-plan никуда не исчезает: `decomposition_wave` = overlay на его lifecycle, а не замена umbrella отдельной сущностью;
- `Coder` в этой фазе материализует planning artifacts, а не product diff;
- `Reviewer` ревьюит planning artifacts, linkage и gates, а не продуктовый код;
- общий механизмовый слой обязан быть видимым в `## Mechanism coverage`: какие registry/index/golden-path/backlog/retrieval surfaces использованы, что ушло в `N/A (why)`, и какие machine-readable связи обязательны для promoted child plans;
- promoted child plans по умолчанию materialize-ятся как обычные bounded планы со статусом `Ready for Planner`, если decomposition wave уже довела их до template-complete handoff без скрытых дыр;
- deferred items остаются в `plan_meta.followups_out[]` и/или `## Follow-ups (deferred)` и не притворяются promoted children;
- после успешного `Architect arch review` umbrella обычно переводится в `phase_state = "parked"`; если child queue ещё требует parent-level sync, он может временно стоять в `Ready for Planner` как parked/reference artifact, но когда все children terminal, `queue_closeout_ready=true` и AC закрыты, Architect закрывает parent напрямую в `Done` без Planner/Coder pass. Повторный run по parked parent допустим только для umbrella-level sync/closure, а не как новый implementation cycle.

Entry decision: обычный `Developer wave` остаётся default. `decomposition_wave` включаем только когда один executable contract больше не держит routing truth. `direct` = один bounded executable plan; `slim` = 2-3 child plans с отдельными delivery/proof boundaries; `full` = 4+ child slices, parked umbrella, rollout/multi-profile graph или тяжёлый deferred backlog. Один child обычно схлопывается в `direct`, если parent не нужен как parked/reference carrier.

Owner-visible preview перед execution должен быть repo-backed и коротким:
- `state`: `bootstrap_only | framed | child_graph_ready | child_artifacts_materialized | parked | blocker`;
- sizing decision: `direct | slim | full` и child count;
- queue order, dependencies, proof lanes, deferred items и open decisions;
- truth source: plan/oracle/queue carriers, а не chat memory.

State labels:
- `bootstrap_only`: есть только helper-created/stamped umbrella;
- `framed`: task framing/sizing/axes есть, child graph ещё не execution-ready;
- `child_graph_ready`: child map/queue/deferred split описаны repo-backed;
- `child_artifacts_materialized`: child files materialized, queue carrier согласован, helper/oracle не видит missing-child blocker;
- `parked`: umbrella reference state, execution живёт в child plans;
- `blocker`: Owner/role/helper blocker запрещает execution handoff.

### Business/task decomposition requirements

Если `decomposition_wave` стартует из широкой бизнес-задачи/инициативы, umbrella должен объяснять не только список child plans, но и почему этот split закрывает исходный бизнес-результат.

Обязательный umbrella-level минимум:
- бизнес-результат;
- основной актор/оператор;
- текущая боль;
- целевое поведение;
- non-goals;
- guardrails / trust boundaries / execution budget;
- expected proof shape;
- оси декомпозиции;
- ordered child plan map: путь child plan, назначение, input/output/consumer, dependency position/type, acceptance/proof lane, independent-stop reason;
- child quality gate: `solvability`, `completeness`, `non-redundancy`;
- parallel/runtime/recomposition policy, если child plans заявлены как independent/parallel или сходятся в один integration lane;
- queue policy: `## Execution queue` или явная причина, почему queue пока не готова.

Детерминированные carriers:
- `## Business decomposition framing` — если parent = бизнес-задача/инициатива, содержит поля выше; если нет, содержит `N/A (why=technical/process decomposition, not business task)`;
- `## Child plan map` — для каждого promoted child: `Plan`, `Purpose`, `Input`, `Output`, `Consumer`, `Depends on`, `Dependency type`, `Acceptance/proof lane`, `Independent-stop reason`, `Queue order`; deferred items здесь не смешиваем с promoted children.
- `## Decomposition quality gate` — helper-readable verdict rows по `solvability / completeness / non-redundancy`, `mutable_surface_runtime_isolation`, `recomposition_owner`, плюс `N/A (why)` для checks, если они реально не применяются. Generic `ok/pass/done` не считается proof.
- `## Mechanism coverage` — row-based table/list с полями `mechanism`, `usage`, `source_refs`, `proof_anchor`, `state`, `promoted_child_impact`. Названные mechanisms требуют opened/read proof anchors или explicit `N/A (why=...)`.

Promoted child plan валиден только если его можно проверить и остановить независимо. Минимум: есть input, output, consumer, done/rejection condition, bounded mutable surfaces, explicit dependency handoff и proof route. Если child зависит от незакрытого Owner/business decision, не ставь его в `## Execution queue`: оставь Owner Q&A или deferred follow-up.

Если child plans хотят идти параллельно, worktree сам по себе не доказывает isolation: ports, DB branches, secrets, state stores, prompts/config/test baselines и другие mutable runtime surfaces должны быть названы как isolated/serialized/shared. Если этого нет, queue считается sequential/serialized.

`Dependency type` допускает только `sequential | parallel | soft | blocking`:
- `sequential` = successor ждёт predecessor completion;
- `parallel` = можно dispatch-ить вместе только при explicit mutable/runtime isolation;
- `soft` = advisory scheduling signal без hard block;
- `blocking` = successor ждёт predecessor плюс named proof/gate.

Child completion не закрывает parent delivery. Если несколько children сходятся в один результат, umbrella должен назвать integration owner, merge/recomposition order и integrated proof surface.

Graph-shape diagnostics warning-first:
- active umbrella с `0` materialized children и roadmap/queue signal должен назвать `decomposition_sizing_rationale` или материализовать child graph;
- `1` child требует `parent_reference_reason`, иначе parent обычно надо схлопнуть в direct dev plan;
- child count `>=10` требует `large_child_count_reason`;
- decomposition depth `>4` требует `depth_override_reason`;
- cumulative nested complexity `>=20` child edges требует `cumulative_complexity_reason` или отдельный traversal/fan-out follow-up.

Эти warnings не заменяют Architect decision: reason values должны объяснять reviewable parent/reference/recomposition role, staged materialization или deliberate full fan-out. Bare `N/A`, `TBD`, `none` и prose без named reason field не закрывают warning path.

### Small-model-ready child contract

Для promoted decomposition child plan добавляй section `## Small-model-ready child contract` из шаблона. Его цель — сделать child исполнимым для слабого runner'а без hidden Manager payload, transcript replay или догадок по соседнему scope.

Ownership:
- Architect задаёт, почему child существует отдельно, какие parent guardrails наследуются и где stop upstream.
- Planner заполняет exact field carrier перед `Ready for Coder`: context bundle, mutable/read-only surfaces, inputs/outputs, proof lane and runner suitability.
- Coder не расширяет carrier по догадке; если в ходе реализации нужен новый mutable surface/helper/prompt target, фиксирует same-contract reroute или возвращает plan upstream.
- Reviewer проверяет, что field values действительно закрывают `solvability / completeness / non-redundancy`, а не просто присутствуют как prose.
- Reviewer проверяет mechanism rows: `golden-path`, backlog, completed-plan index, retrieval, registry и `plan_meta` linkage должны указывать на concrete `source_refs`/`proof_anchor` или explicit `N/A (why=...)`.
- Failure modes из `docs/playbooks/decomposition_wave.md` (`over_decomposition`, `under_decomposition`, `silent_scope_widening`, `orphan_child`, `hidden_dependency_drift`, `approval_or_risk_leakage`, `parallel_conflict`) требуют mitigation, reroute или deferred follow-up перед promotion.

Canonical fields:
- Hard-required for promoted children: `Task outcome`, `Local context bundle`, `Mutable surfaces`, `Read-only surfaces`, `Forbidden scope`, `Inputs from parent/predecessor`, `Output to consumer`, `Acceptance/proof lane`, `Stop condition`, `Expected reviewer lane`.
- Warning-first initially: `Runner suitability`, `Task size/complexity`, `Readiness notes`. Эти fields должны существовать, но helper/lint hard-gate включается отдельно после real-example enforcement slice.

`N/A (why=...)` policy:
- For promoted child, hard-required fields should almost never be `N/A`; if one is truly not applicable, the reason must explain why the child is still independently executable.
- Warning-first fields may use `N/A (why=...)` while runner routing and quality metrics are stabilizing.
- Plain `N/A`, `TBD`, `UNCONFIRMED`, "см. parent" or "Manager объяснит" are not enough for a promoted child handoff.
- Never put provider logs, full transcripts, private prompts, credentials or hidden chat payload into the carrier.

Examples:
- Docs-only/process schema child:
  - `Task outcome`: canonical section added to playbook/template/README.
  - `Mutable surfaces`: `docs/playbooks/decomposition_wave.md`, `docs/plans/_template.md`, `docs/plans/README.md`.
  - `Acceptance/proof lane`: `plan_lint`, scoped `run_doc_lint.sh`, exact `git diff --check`.
  - `Expected reviewer lane`: `docs-only`.
- Process-helper child:
  - `Local context bundle`: helper plan, existing script, script tests, owner runbook section.
  - `Mutable surfaces`: helper script, focused tests, one docs carrier.
  - `Stop condition`: helper needs new status/verdict semantics outside listed consumers.
  - `Runner suitability`: small runner OK for additive parser/test change; fallback to main Coder if CLI JSON contract expands.
- Runtime-code child:
  - `Inputs from parent/predecessor`: migration/schema child output or API contract path.
  - `Mutable surfaces`: exact module/tests path families.
  - `Read-only surfaces`: UI templates, docs, or migration files not owned by this child.
  - `Forbidden scope`: schema/UI/permission changes not explicitly listed.
  - `Acceptance/proof lane`: targeted tests plus named integration smoke.

Enforcement boundary:
- Child 1 defines this schema in playbook/template/README.
- Child 2 updates Architect/Planner prompts to produce the carrier.
- Child 3 owns helper/lint quality gates and warning-to-hard promotion decisions.

## Plan meta (machine-readable JSON; required for new plans)
Иногда полезно иметь небольшой machine‑readable блок (без отдельной системы трекинга), чтобы:
- помечать “кластер/тему” plan’а (и связывать с worktree у Owner),
- фиксировать follow‑ups “в другой кластер”,
- (опционально) хранить зависимости.

Формат: секция `## Meta (machine‑readable JSON; required for new plans)` в начале plan (см. `docs/plans/_template.md`).

Рекомендуемый минимум:
- `cluster`: основной кластер plan’а; выбери каноническое значение из `docs/_meta/plan_vocab.json` (например, `process`).
- `required_manager_mode`: executable Manager admission authority:
  `manager-collab | manager-custom-pipeline | either`. Только explicit `either`
  допускает оба уже выбранных runtime mode; Manager никогда не переключается
  автоматически.
- `tags`: дополнительные теги (опционально).
- `wave_family`: optional wave family marker; in V1 only `analysis_wave` materialize-ит plan-resident `## Analysis pack`. Omit/null для ordinary dev plans.
- `phase_overlay`: optional phase overlay (`decomposition_wave`), если plan идёт не как обычный executable flow.
- `phase_state`: required only вместе с `phase_overlay`; для `decomposition_wave` сейчас допустимы `active` / `parked`.
- `parent`: optional repo-relative path на direct umbrella/master-plan; `null`/omit для standalone slice.
- `next_plans[]`: optional bounded список (`0..3`) repo-relative plan paths для direct next slices; это не backlog dump и не замена external V2 follow-up row.
- `followups_out[]`: legacy V1-only список follow-ups; новые `plan.v2` files не несут это поле.
- `depends_on[]`: список путей на другие планы (опционально).
- `blocking_depends_on[]`: opt-in carrier для жёстких внешних зависимостей; каждый его путь обязан также быть в `depends_on[]`.
- `canon_updates[]`: список “что обновить в каноне после merge” (опционально, но полезно для UX/ARCH/process планов).
- `promoted_from`: optional derived/read-only snapshot for target artifacts
  promoted from an accepted `analysis_wave` route; it must not become second
  writable route truth.
- `queue_activation`: optional explicit queue activation marker. For
  `Architect initial draft`, a complete object may use `owner_approved`,
  `architect_approved` or intentional `n/a`; only the approved states are
  queue-eligible. Absent/null/malformed carriers remain fail-closed where the
  status contract requires the marker.
- `scope_expansion`: optional developer-wave reroute carrier for discovered
  broad analytics / `split_required=true` / hidden child graph. Use
  `reroute_required` and stop for Architect/planning-contour routing instead
  of widening implementation.

Примечание: поле `clusters` больше не используем (deprecated) — только `tags`.

### `cluster` (enum; канон)
`plan_meta.cluster` — **одна** тема из канонического списка (нижний регистр, без пробелов).
Это нужно для стабильной кластеризации/маршрутизации (и для post-merge harvest), чтобы значения не “расползались”.

Канонические значения `cluster` определены только в `docs/_meta/plan_vocab.json` → `clusters.canonical`; `scripts/plan_lint.py` читает этот declared vocabulary.

Правила:
- `cluster` всегда **один** (не список). Уточнения — в `tags[]`.
- `tags` — массив строк (можно 0..N тегов).
- Не придумывай локальные варианты `cluster`: выбери declared value, а уточнения перенеси в `tags[]`.

Поиск через `rg` (без скриптов):
- `rg -n \"\\\"cluster\\\"\" docs/plans`
- `rg -n \"\\\"tags\\\"\" docs/plans`
- `rg -n \"\\\"followups_out\\\"\" docs/plans`
- `rg -n \"\\\"depends_on\\\"\" docs/plans`
- `rg -n \"\\\"canon_updates\\\"\" docs/plans`

Пример `plan_meta` (c optional полями, которые часто нужны):
```json
{
  "plan_meta": {
    "cluster": "process",
    "tags": ["example"],
    "required_manager_mode": "either",
    "wave_family": null,
    "phase_overlay": null,
    "phase_state": null,
    "parent": null,
    "next_plans": [],
    "depends_on": [],
    "promoted_from": {
      "authority_note": "derived_read_only; source artifact is writable truth"
    },
    "queue_activation": {
      "state": "n/a",
      "source_ref": "N/A (why=not a queued Architect initial draft)",
      "reason": "N/A (why=not a queued Architect initial draft)"
    },
    "scope_expansion": {
      "state": "n/a",
      "target_contour": "N/A",
      "source_ref": "N/A (why=no scope expansion)",
      "reason": "N/A (why=no scope expansion)"
    },
    "followups_out": [
      {
        "cluster": "process",
        "summary": "Follow-up summary",
        "plan": null
      }
    ],
    "canon_updates": [
      {
        "doc": "docs/adr/...",
        "summary": "What should be updated post-merge"
      }
    ]
  }
}
```

Enforcement:
- Для новых планов `scripts/plan_lint.py` валидирует наличие `plan_meta`, `cluster` и его значение по declared vocabulary; если указан `phase_overlay`, он тоже должен быть каноническим и согласованным с `phase_state` (иначе handoff блокируется).
- Missing `required_manager_mode` — lint error для любого plan, кроме шаблона;
  runtime admission выбранного executable plan тоже fail-closed. Present invalid
  value всегда error.
- Runtime проверяется через
  `plan_status_oracle.py PLAN_PATH --json --manager-mode manager-collab|manager-custom-pipeline`.
  Exit `4` означает mismatch/missing/invalid declaration; Manager не выводит
  mode из `Verification rerun`/`Command`/tags и не запускает alternate wrapper.
- Для новых plan contracts навигационные carriers валидируются узко: `parent` должен быть repo-relative `docs/plans/...md` или `null`; `next_plans` — `0..3` repo-relative plan paths без превращения поля в мини-backlog.

### Planning-contour derived carriers

`plan_meta.promoted_from` используется только на promoted target artifacts как
derived/read-only receipt:
- `source_plan`, `source_route_ref`, `accepted_route`,
  `promoted_artifact_kind`, `promoted_artifact_ref`;
- `queue_admission_at_acceptance`, `runner_admission_at_acceptance`;
- `authority_note: derived_read_only; source artifact is writable truth`.

`plan_meta.queue_activation` materialize-ит explicit queue/run approval:
- `state`: `not_requested | owner_approved | architect_approved | n/a`;
- `source_ref`: parent execution queue / Owner answer / `N/A (why=...)`;
- `reason`: short bounded reason.

For `Architect initial draft`, a complete manifest-valid `state=n/a` carrier is
valid metadata but means durable queue-collection ineligibility. Any
explicit/status/umbrella/append collection attempt must hard-fail before
successful state/log mutation; it must not become `skipped_incompatible[]` or a
`skip_manager_mode` audit row. Queue import is allowed only when `state` is
`owner_approved` or `architect_approved`. Creation of a plan file never writes
this marker by itself. Manual Owner activation uses `owner_approved`, not a
separate queue-code bypass. `architect_approved` is limited to routing-only,
contract-only or docs-only planning artifacts with no product/runtime/helper
mutation in the exact bundle.

Direct `planveyor_decomposition_init PLAN_PATH` remains a single-plan bootstrap,
not queue collection. A decomposition source may truthfully carry `state=n/a`
until its child graph, matching `plan_meta.next_plans[]` and a separate approved
activation are materialized for later queue import.

Direct bootstrap artifact boundary:
- candidate target допускается только внутри current repo `docs/plans/*.md`; repo-relative и absolute-inside-root forms нормализуются в один repo-relative identity, а traversal/outside-root/symlink/non-regular target fail-closed до plan/current-state/session/queue/staging mutation;
- missing target может atomically получить только canonical neutral scaffold при existing real parent chain;
- existing plan stamp допустим только для literal `Architect initial draft`, структурно совпадающего с current canonical template после helper-owned header normalization: route carriers null, graph/canon arrays empty, Problem/Scope/Decisions/DoD template-placeholder-only;
- marker absence не является neutral predicate. Populated, terminal/Superseded, `analysis_wave`, promoted, malformed/ambiguous plan остаётся byte-identical; compatible active decomposition umbrella reuse-ится без rewrite.

Checked-in `docs/tools/prompts/planveyor_decomposition.md` — prompt authority. Codex configuration и authentication остаются consumer-owned и не меняют plan admission или queue truth.

`plan_meta.scope_expansion` materialize-ит developer-wave reroute:
- `state`: `n/a | suspected | reroute_required | architect_accepted`;
- `target_contour`: `N/A | analysis_wave | decomposition_wave | human_gate | defer | reject`;
- `source_ref` and `reason`: bounded evidence for the reroute.

Ordinary `developer_wave` that discovers broad analytics, hidden child graph or
`split_required=true` sets `reroute_required` and stops for Architect routing.
It does not silently create analysis/decomposition work inside Coder lane.

`scripts/plan_lint.py` has a warning-first drift guard for this case. Its
existing signals are promoted to a blocking `ERROR` only when all four
pre-Coder admission conditions hold:
- the raw `Plan type` header is the literal `dev`;
- the file is a plan, not the plan template;
- the plan is an ordinary developer contour, not an analysis/decomposition
  planning contour;
- the effective status is exactly `Planner finalize` or `Ready for Coder`.

Under that predicate, unresolved structured states `suspected`,
`reroute_required` and `architect_accepted`, or any signal already returned by
the warning-first detector, block the handoff. `scope_expansion.state=n/a`
does not introduce a free-prose override: `reason`, `source_ref`, owner and
policy wording receive no new interpretation in this slice. The unchanged
warning-first detector remains authoritative, including its existing signal
suppression behavior; only the severity of its final result changes. Absence
of an existing detector signal remains clean.

Outside the full predicate, the previous compatibility behavior is unchanged:
structured unresolved states and narrow legacy child-graph signals remain
`WARN`/no-finding as before; valid `decomposition_wave` carriers are exempt;
and `reroute_required` with `Ready for Architect response` remains the existing
Architect route rather than a failed pre-Coder handoff. E5 lint still hardens
only the object shape of `plan_meta.scope_expansion` when that carrier is
present.

V1 warning family also treats a few narrow legacy signals as smell evidence for
ordinary `developer_wave`, without making them stable routing carriers:
- explicit `failure_mode` / `smell` values `silent_scope_widening` or
  `hidden_dependency_drift`;
- concrete `docs/plans/*.md` child refs in child/promoted-child/next-plan/queue
  context when `plan_meta.scope_expansion` is absent or `null`;
- multiple `proof_lanes` without `integration_owner`, `recomposition_owner` or
  a serialization policy.

These warnings mean: close `plan_meta.scope_expansion` or reroute to planning
contour. V1 does not
define a numeric mutable-target or surface-diversity threshold; threshold tuning
needs a later documented slice with fixture/noise evidence.

## Forward navigation / close-out / verification contract
Это не новый tracker и не второй backlog. Это узкие carriers, чтобы plan честно отвечал на три вопроса:
- “От какого upstream artifact идёт этот slice?”
- “Куда идти после closure?”
- “Как воспроизвести bounded verification без восстановления контекста по памяти?”

### `## Plan provenance / session context`
Это обязательный origin-carrier для новых plan files. Он отвечает только на вопрос “из какого thread/session/import chain взялся текущий plan context” и не подменяет routing/verification carriers.

Literal field set:
- `Relation:` `created-here | continued-here | imported-from-packet | manual-backfill`
- `Thread ID:` current thread handle или `N/A (why=...)`
- `Parent thread ID:` optional upstream thread handle или `N/A (why=...)`
- `Session SID:` Codex session/audit pointer или `N/A (why=...)`
- `Launch surface:` `codex-desktop | codex-cli | manager-collab | manager-custom-pipeline | unknown (why=...)`
- `Captured from:` `env | wrapper-session-file | session-stats | packet-import | manual-owner`
- `Captured at:` timestamp

Canonical collection order:
1. live env (`CODEX_THREAD_ID`, optional `CODEX_PARENT_THREAD_ID`); facade `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor"` запускает команду в чистом окружении и передаёт в неё из live env только непустой `CODEX_THREAD_ID`, поэтому через facade `Parent thread ID` берётся из следующих источников;
2. `.planveyor.session.<role>` attach-pointer for `Session SID`;
3. `.planveyor.run_receipt.*` for bounded run context;
4. read-only fallback `scripts/codex_session_stats.py`;
5. explicit packet import / manual backfill inputs.

Canonical helper surfaces:
- `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_plan_provenance_stamp <PLAN_PATH> --session-key <role>`
- `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_plan_provenance_context --session-key <role> [HELPER_ARGS...]`
- Self-Planveyor only: `PYTHONDONTWRITEBYTECODE=1 "$PYBIN" -B scripts/codex_session_context.py ...` из physical Planveyor root; sibling использует два facade-вызова выше.

Rules:
- Architect materialize-ит carrier при создании нового plan; остальные роли сохраняют его и обновляют только по truthful trigger.
- Разрешённые rewrites: `created-here -> continued-here` на later session того же plan, packet-import restamp, explicit `manual-backfill`, refresh `captured_*` и repo-backed ids через helper.
- Недостающие значения не угадываем: пишем `N/A (why=...)` в конкретном поле, а не пропускаем раздел целиком.
- `Context source:` в `## Verification rerun / exec handoff` остаётся bounded human execution context, а provenance block остаётся audit/origin carrier.
- `docs/code_drafts/_template.md` зеркалит этот carrier как `## Provenance / session context`; `docs/rollout_packets/_template.md` несёт только bounded `## Source provenance` subset, а не весь mutable plan block.

### `## Documentation impact / provenance`
Это обязательный carrier для новых plan files, который отвечает на вопрос: какие документы повлияли на постановку и какие documentation/registry/canon updates должны двигаться вместе с реализацией.

Минимальные строки:
- `Source docs used:` documentation/reviews/retrieval hits/prior plans, использованные при drafting, или `N/A (why=...)`.
- `Synchronous doc/registry targets:` docs, которые должны меняться в этом же implementation slice, или `N/A (why=...)`.
- `Post-merge canon updates:` durable facts/decisions, которые нужно поднять после implementation/merge, или `N/A (why=...)`.
- `Deferred documentation follow-ups:` отложенная docs-работа с owner/reason, или `N/A (why=...)`.
- `Provenance refs:` Owner input / review blocker / prior plan / rollout packet / retrieval hit, или `N/A (why=...)`.

Границы:
- это planning-time documentation impact, а не `## Plan provenance / session context`: provenance отвечает за происхождение thread/session/import chain;
- это не `Context links`: context links показывают canonical sources of truth, а carrier фиксирует, какие docs реально использовались и что должно синхронно измениться;
- это не `plan_meta.canon_updates[]`: `canon_updates[]` остаётся machine-readable post-merge intent, а carrier даёт readable lifecycle/rationale и может ссылаться на `N/A (why=...)`;
- это не `code_draft_meta.targets`: exact executable doc files живут в code draft; carrier не становится вторым target list и не должен расходиться с draft targets.

Правила:
- для новых plans после adoption пустой/missing carrier считается plan gap; если docs impact отсутствует, заполняй поля явным `N/A (why=...)`;
- если `Synchronous doc/registry targets` называет файл как обязательный для текущего slice, он должен быть отражён в `code_draft_meta.targets` перед `Ready for Coder` или явно вынесен в `Deferred documentation follow-ups`;
- memory-finalize может добавить follow-up/process-improvement carrier после closure, но это не заменяет upfront documentation impact в executable plan.

### `plan_meta.parent` / `plan_meta.next_plans`
- `plan_meta.parent` = direct umbrella/master-plan path. Не “родительская тема вообще”, а один concrete upstream artifact.
- `plan_meta.next_plans[]` = direct next executable/follow-up slices (`0..3`). Если next slice ещё не materialized — поле можно omit/оставить пустым.
- `followups_out[]` остаётся backlog/follow-up carrier’ом. Разница простая:
  - `next_plans[]` = куда идти сразу после closure текущего slice;
  - `followups_out[]` = что остаётся в backlog/другом кластере и может ещё не иметь plan file.

### `plan_meta.blocking_depends_on[]`
- Это opt-in V1 carrier для dependency, которая обязана остановить queue даже тогда, когда target plan отсутствует из текущей runtime queue. Не переопределяет и не расширяет смысл обычного `depends_on[]`: он остаётся lineage carrier и input существующего same-queue blocker.
- Значение — JSON array уникальных, лексикографически отсортированных repo-relative строк вида `docs/plans/*.md`. Каждый путь обязан буквально присутствовать в `depends_on[]`; пустой массив допустим, но обычно field лучше omit, если hard edge нет.
- Перед pending activation и projected-next closeout/advance queue читает каждый exact target через `plan_status_oracle.oracle_result(target).delivery_green`. Единственный clearance — literal `delivery_green=true`; missing/unreadable/malformed target, oracle error или `delivery_green=false` останавливают queue до state/log mutation.
- Нельзя заменять этот predicate raw `Done`/`Superseded`, source-route prose, `queue_activation`, `promoted_from`, queue output или lint-derived verdict. Для outcome-qualified route hard path должен указывать на точный materialized green accepted/promoted outcome, а не на red reference/analysis artifact.
- Lint всегда выдаёт `ERROR` за shape/path/unique/sorted/subset mismatch. Readback non-green/error остаётся `WARN` только для immutable terminal history или ранних `Architect initial draft` / `Architect draft` / `Architect response` с explicit `queue_activation.state=n/a|not_requested`; после approved activation или на прочих non-terminal status это `ERROR`. Независимо от lint severity runtime queue всегда fail-closed.

### `## Close-out routing`
Это обязательный для новых close-out-sensitive plan shapes carrier с `N/A (why)`-friendly значениями для control/docs-only cases.

Минимальные строки:
- `Roadmap/queue sync:` что синхронизировать в repo-local queue/roadmap или почему `N/A`.
- `Follow-up sync:` какой bounded follow-up/backlog target обновляется или создаётся.
- `Next bounded slice:` direct next artifact/path или `none (terminal)`.
- `Terminal outcome:` `yes|no` + короткое `why` (или `N/A (why)` для control case).

Важно:
- `Close-out routing` отвечает на “куда идти после closure”.
- `## Post-merge gate` отвечает на “что проверить перед удалением временного plan”.
- Эти блоки не дублируют друг друга и не заменяют `followups_out`.

### `## Execution queue` / `## Queue close-out`
Это узкий carrier для umbrella/master-plan, который хочет честно materialize-ить canonical queue order для `Manager run Q` / `--q`, не превращая `next_plans[]` или `followups_out[]` в “магическую вторую систему”.

Минимальный `## Execution queue`:
- `Resume parent:` `none | owner-restamp-required | run-parent-once`
- повторяемые строки `Plan:` c repo-relative child-plan path в literal порядке выполнения
- если plan не queue-carrier — ставь `N/A (why)`, а не пустой блок

Минимальный `## Queue close-out`:
- `On terminal child completion:` что происходит после `Done` / `Superseded`
- `On non-terminal stop:` как queue halts и почему current item остаётся `active`
- `Parent resume:` краткий bounded contract для umbrella parent (`none | owner-restamp-required | run-parent-once`)

Правила:
- `next_plans[]` остаётся bounded forward-navigation carrier (`0..3`), а не full execution queue;
- `followups_out[].plan` остаётся legacy import bridge для старых umbrella plans, пока новый `## Execution queue` не materialized; новые promoted children туда не добавляем;
- queue import берёт children только из repo-backed carriers: сначала `## Execution queue`, затем legacy `followups_out[].plan`, затем bounded `plan_meta.next_plans[]` when no legacy plan paths exist;
- каждый child path для queue должен быть materialized repo-relative `docs/plans/*.md` и проходить queue-lint/oracle sanity (single header `**Status:**`, readable plan); missing/non-lintable child path = fail-closed blocker, не повод синтезировать child plan из prose;
- `- Plan: N/A (why=...)` в `## Execution queue` — explanatory non-child entry; он не является queueable child path и не требует `plan_meta.next_plans[]` parity. Queueable child = только materialized repo-relative `docs/plans/*.md`;
- если queue order не может быть доказан repo-backed carrier'ом, не выдумывай его из prose/backlog notes.

Для active `decomposition_wave` действует helper-backed child-state gate:
- role-facing owner-preview states (`bootstrap_only`, `framed`, `child_graph_ready`, `child_artifacts_materialized`, `parked`, `blocker`) должны согласовываться с helper truth below; prompt/prose не имеет права объявлять execution-ready состояние поверх missing helper proof;
- `queue_ready`: concrete repo-relative child paths есть в `## Execution queue` или `plan_meta.next_plans[]`, эти carriers согласованы между собой, а child files materialized и queue-lintable;
- `drafted`: child rows уже перечислены в `## Child plan map`, но queue carrier ещё не материализован; `planveyor_q_set --from-umbrella <PLAN_PATH> --for-manager-mode <MODE>` fail-closed с `decomposition_children_missing`;
- `missing`: child graph пустой, содержит `TBD`/`N/A`, invalid path, missing file, non-lintable child или mismatch между carriers; oracle/queue должны отдавать deterministic `decomposition_children_missing`, а lint hard-block включается для queue/closeout intent или promoted non-concrete child paths, но не для early `Architect draft` / `Ready for Planner` intake без queue carrier;
- `parked`: reference parent остаётся non-executable только при explicit `phase_state=parked` и repo-backed `N/A` executable handoffs/code draft markers.

#### Candidate-only materialization corridor

Для active `decomposition_wave` до первого child-файла допустим узкий `candidate-only` corridor: это не queue-ready graph и не ослабление oracle/queue readers. Он разрешён только при **одновременной** строгой форме: нет `expansion_source` и concrete child paths; `plan_meta.next_plans=[]`; `## Child plan map` содержит ровно section-level explanatory `N/A (why=...)`; `## Execution queue` не содержит child path и держит только `- Plan: N/A (why=...)` (допустим отдельный `Resume parent`); candidate contours остаются semantic slugs, не parent-child links.

Эта форма принимается только в статусах `Planner finalize`, `Ready for Coder`, `Coder intake`, `In progress`, `Ready for Architect response` и `Architect response`. Любой `TBD`, named `N/A`, concrete/partial/missing/non-lintable child, non-empty `next_plans[]`, queue entry или carrier mismatch остаётся fail-closed `decomposition_children_missing` во всех этих статусах. Правильный lifecycle: Planner завершает candidate pack через `Planner finalize -> Ready for Coder`; Coder materialize-ит files-first, linkage-second; каждый созданный child становится template-complete `Ready for Planner`; parent может стать `Ready for Review` только после real graph с lintable child paths и согласованными carriers.

`Resume parent` остаётся строгим enum `none | owner-restamp-required | run-parent-once`; reason text фиксируется отдельной строкой/заметкой, а не в значении enum.

### `## Rollout packet handoff`
Это carrier для controlled cross-repo handoff, когда shared/source repo должен сигнализировать downstream action в sibling repo, но не имеет права писать туда на лету и не должен владеть чужим executable bundle.

Когда использовать:
- shared change живёт в source repo, а target repo должен сделать свой repo-local adoption;
- packet живёт как checked-in artifact в source repo: `docs/rollout_packets/<YYMMDD_HHMM>_<target_repo>_<topic>.md`;
- если target repo action не нужен, packet не выпускаем.

Базовый контракт:
- source repo владеет только shared plan + rollout packet;
- target repo владеет generated target-local adoption plan, который по умолчанию является и import receipt;
- только target-local plan может попадать в local queue / `Manager run Q`;
- rollout packet не является вторым execution plan, не является queue item и не даёт source repo права трогать sibling writable files.

Target-side import receipt minimum:
- source packet path + packet id materialize-ятся literal-но в одном helper-owned `rollout_packet_outcomes.v1` item;
- import receipt materialization does not equal adoption; source `imported` with receipt pointers derives `target_adoption_state=awaiting-target-outcome` until `planveyor_rollout_packet_outcome_set` records that item's canonical outcome;
- generated direct `docs/plans/<name>.md` contains exactly one `planveyor:rollout_packet_carrier.v1` sentinel region with `rollout_packet_import` and `rollout_packet_outcomes` objects;
- receipt называет generated target-local adoption plan path или явно фиксирует `no local plan yet (why)`;
- default pointer contract for v1 is `target_import_receipt == target_local_plan ==` the direct carrier path; split pointers are fail-closed, not an override;
- queued/not-queued outcome фиксируется отдельно и остаётся target-local;
- `queue_after_import` = packet-specific hint after import, а не source-side queue authority.
- source packet сам по себе не доказывает, что target repo уже merge-protecting: repo-local required-check naming / branch-protection / external enforcement остаются target-owner-confirmed closeout, пока target-local receipt/review evidence не зафиксируют иное literal-но.

Минимальные строки для `## Rollout packet handoff`:
- `Role:` `source-packet | target-import | N/A (why)`
- `Packet path:` `docs/rollout_packets/...` или `N/A (why)`
- `Target repo:` literal repo id (`<target-repo>`)
- `Suggested target plan slug:` bounded basename/slug для local plan или `N/A (why)`
- `Queue after import:` `yes | no | N/A (why)`

Правила:
- same-repo next slices продолжают жить через `plan_meta.parent`, `plan_meta.next_plans[]`, `followups_out[]`, `## Execution queue`; rollout packet не подменяет эти carriers;
- source repo queue не владеет target-repo execution и не materialize-ит sibling writable bundle;
- `followups_out[]` может фиксировать сам факт downstream action, но literal packet path живёт в `Context links` и/или `## Rollout packet handoff`, а не маскируется под `next_plans[]`;
- `Packet path`, `Target repo`, `Suggested target plan slug` и concrete local plan path остаются packet-instance значениями; shared canon фиксирует только import-receipt invariants и target-local queue boundary;
- packet types вроде `plan_adoption`, `mirror_sync`, `checker_rollout`, `consumer_only` допустимы, но execution всё равно остаётся repo-local у target repo после import.
- Если source-owned slice refresh/validate-ит уже checked-in packet carrier, `preconditions / seed-discovery` и packet `## Source artifacts` literal-но говорят об already-materialized packet pair; не смешивай create-from-scratch wording с refresh-in-place targets.
- Для source-owned rollout-packet bundle green `plan_lint` сам по себе не доказывает handoff: primary proof lane обычно = `plan_lint` + packet-scoped `doc_lint`, а contextual lane читает сам packet на `Target writable carriers`, `Queue after import` и importable-boundary / not-yet-landed guards.
- Если packet доставляет source-owned CI/runbook/snippet baseline, не обещай merge protection как implicit side effect: source packet фиксирует shared references и target-local adoption boundary, а external required-check/branch-protection state остаётся downstream target-local closeout до literal owner/review evidence.

### Rollout packet helpers
Если shared/source repo всё же materialize-ит helper surface для packet, helper split должен совпадать с ownership split, а не становиться hidden cross-repo bridge.

Минимальный контракт:
- source-local helper может создать packet skeleton в текущем source repo, показать существующий packet, напечатать target-local import instructions и опционально text-only target-plan seed: `planveyor_rollout_packet_create`, `planveyor_rollout_packet_show`, `planveyor_rollout_packet_import_instructions`;
- target-local helper запускается через внешний facade `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project /absolute/path/to/consumer`; selected consumer становится target repo, а loaded runtime остаётся tooling root. Он показывает matching inbox и materialize-ит target-local adoption plan/import receipt: `planveyor_rollout_packet_inbox`, `planveyor_rollout_packet_harvest` / `planveyor_rollout_packet_adoption_plan`;
- target-local writer records one decision only through `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project /absolute/path/to/consumer planveyor_rollout_packet_outcome_set --target-plan docs/plans/<...>.md --packet-id <id> --packet-path docs/rollout_packets/<...>.md --outcome <canonical-or-alias>`;
- source-local helper не имеет права писать sibling-repo файлы, stage/commit sibling-repo изменения или запускать target-local queue actions;
- target-local helper не имеет права менять source packet status или писать в другие repos; он пишет только target-local plan/import receipt в текущем repo;
- helper naming не отменяет ownership split: packet/import/helper остаются разными carriers, а any truthful target-local mutation reroute-ится в target repo/local plan;
- generated carrier's `rollout_packet_import` object is linkage context; terminal readback requires its sibling recorded `rollout_packet_outcomes.v1` item, never prose or a standalone fenced JSON copy;
- optional extracted helper module (например `scripts/rollout_packet.py`) допустим только как support file для явных source-local/target-local wrapper surfaces, а не как вторая скрытая ownership lane.

### `## Upstream request packet`
Это reverse-flow carrier для ситуации, когда target repo нашёл shared/process gap, но source of truth живёт в `planveyor`.

Базовый контракт:
- request живёт как checked-in artifact `docs/upstream_packets/<YYMMDD_HHMM>_<origin_repo>_<topic>.md`;
- request не является execution plan, queue item или разрешением source repo писать sibling files;
- source import создаёт только source-local carrier: raw `docs/process_improvements/*` row или отдельный source-local plan;
- `source_import_plan` фиксирует импорт/triage carrier, а `source_decision_ref` и `source_execution_ref` появляются только после нормального source review/closeout.

Минимальные поля packet:
- `origin_repo`, `owning_repo`, `origin_plan`, `trigger_ref`;
- `symptom`, `process_gap`, `suggested_fix`;
- `source_import_plan`, `source_decision_ref`, `source_execution_ref`.

Helper surface:
- `planveyor_upstream_request_show docs/upstream_packets/<...>.md [--raw]` показывает packet summary;
- `planveyor_upstream_request_import --packet docs/upstream_packets/<...>.md` imports open request в source-local process-improvement row и обновляет только packet markdown/meta;
- `planveyor_upstream_request_ack --packet docs/upstream_packets/<...>.md --source-decision-ref docs/plans/<...> [--source-execution-ref docs/plans/<...>]` фиксирует source-side decision/execution refs после source review/closeout и обновляет только packet markdown/meta;
- `planveyor_upstream_request_query [--status open] [--origin-repo <sibling>] [--json]` даёт read-only inventory.

Правила:
- target-specific product/runtime facts остаются в packet context или фильтруются Architect review; shared canon не должен копировать их напрямую;
- если принятое source-side решение должен принять sibling, после source closeout оно доходит до sibling обновлением контракта с извещением `docs/contract_notices/<id>.json`: его `sibling_actions` говорят sibling, что сделать, включая перевод копии запроса в `decided`;
- reverse request helper не расширяет `scripts/rollout_packet.py` и не подменяет rollout packet import/ack flow.

### `## Small-slice conveyor classifier`
Это opt-in carrier для bounded reduced conveyor. По умолчанию full conveyor остаётся включённым; Manager может пропускать только same-session `Architect CENSOR` / `Planner CENSOR` / `Coder CENSOR` и только если explicit plan-side carrier и helper-side validation буквально совпали.

Минимальные строки:
- `Requested profile:` `reduced-same-session-censors` или `N/A (why)`
- `Expected bundle family:` `docs-only | tests-only` или `N/A (why)`
- `Helper validation:` `exact-bundle-match` или `N/A (why)`
- `Drift behavior:` `fail-closed-to-full-conveyor` или `N/A (why)`

Helper-side validation:
- canonical helper = `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_q_small_slice <PLAN_PATH> --json` (owner-facing wrapper: `planveyor_q_small_slice <PLAN_PATH>`);
- helper читает literal `Requested profile` / `Expected bundle family` / `Helper validation` / `Drift behavior`, затем сверяет их с exact current bundle через `code_draft_meta.targets`, live review route и control carriers;
- `docs-only` = все `code_draft_meta.targets` лежат под `docs/**`, а live review route literal-но указывает на `docs/doc_reviews/...`;
- `tests-only` = все targets являются repo-local test carriers (`tests/**`, `*/tests/**`, `test_*.py`, `*_test.py`, `scripts/test_*.py`), а live review route literal-но указывает на `docs/code_reviews/...`;
- любой mixed bundle, non-test code/helper path, ambiguous/missing live review route, non-`N/A` `## Rollout packet handoff` или non-`N/A` `## Visual Acceptance` = fail-closed to full conveyor.

Reduced matrix v1:
- при `reduced_conveyor_eligible=true` Manager пропускает только same-session `Architect CENSOR` / `Planner CENSOR` / `Coder CENSOR`;
- `Architect -> Planner -> Coder -> Reviewer -> Architect` остаётся тем же semantic route;
- Reviewer artifact и final Architect closeout обязательны всегда;
- helper mismatch/ошибка/отсутствующий carrier не являются blocker’ом сами по себе: это просто truthful fallback на обычный full conveyor.

### `## Verification rerun / exec handoff`
Это reusable verification surface, а не второй review-plan и не prose reminder в `Evidence`.

Минимальные строки:
- `Mode:` `reuse-thread` | `fresh-exec` | `manager-custom-pipeline` | `N/A (why)`.
- `Context source:` обычно `same thread_id` или `PLAN_PATH + PRE_STATUS_LINE + linked artifacts`.
- `Prompt:` короткий bounded verification prompt.
- `Command:` exact copy-paste command.
- `Expected artifact:` `docs/code_reviews/...` / `docs/doc_reviews/...` / `stdout receipt` / `snapshot path`.

Правило заполнения:
- Значение `Mode:` пишем bare token без Markdown backticks, например `- Mode: fresh-exec`. Backticks вокруг значения попадают в literal value и ломают `plan_lint`.
- если terminal result реально надо проверять воспроизводимо, block materialize-ится буквально;
- если rerun surface не нужен (например, documentation/control slice без runtime/session proof path), допускается `N/A (why)`, но это должно быть явным значением, а не пустотой.
- provenance и rerun не смешиваем: `Context source:` может ссылаться на `PLAN_PATH + PRE_STATUS_LINE + linked artifacts`, но literal `thread_id` / `session_sid` / `launch_surface` остаются в provenance block или в run receipt, а не “дописанными в prose”.

### Session pointer vs run receipt
- `.planveyor.session.<role>` = stable attach/resume pointer. Этот файл не превращаем в review/verification receipt.
- Run/verification receipt живёт отдельно и материализует bounded context: `thread_id`, optional `parent_thread_id`, `cwd`, `repo_root`, `worktree_id`, `launch_surface`, `pipeline_mode`, `plan_path`, `pre_status_line`, `started_at`, `finished_at`, `result_artifact`.
- Provenance helper/section использует эти surfaces как source inputs, но не подменяет ими сам receipt: plan provenance = checked-in audit carrier, run receipt = mutable execution receipt, session file = attach pointer.
- Vocabulary держим bounded:
  - `launch_surface` = `codex_desktop | codex_cli | codex_exec | collab_subagent`
  - `pipeline_mode` = `manual | manager_router | manager_custom_pipeline | collab | review_only`
- Формат receipt surface допустим как `key=value` или JSON, но pointer и receipt остаются разными contract layers.

## Mechanism coverage (для decomposition wave)
Для обычного executable plan отдельный блок не обязателен.

Для `plan_meta.phase_overlay = "decomposition_wave"` обязателен materialized `## Mechanism coverage`, чтобы downstream роли не гадали, какой knowledge/governance/retrieval слой реально использовался.

Минимум, который должен быть виден:
- какие общие механизмы реально использованы;
- что ушло в `N/A (why)`;
- какие registry/index/backlog surfaces стали источником решений;
- какие machine-readable поля и связи обязательны для promoted child plans.

Практическое правило:
- для shared runtime flow это обычно declared registry rows, docs retrieval/archive surfaces, `plan_meta` fields и релевантные target registries;
- для target-local consumer это тот же общий skeleton через declared repo-local anchors, registries и harness surfaces.

## Token hygiene (контент плана)
Правило: plan — контракт. Код в plan — только если он реально нужен для понимания/проверки и короткий.

Рекомендуется:
- не вставлять большие code blocks (особенно “полные функции/файлы”);
- вместо этого фиксировать: пути/селекторы/что должно измениться + acceptance;
- **Code draft обязателен для ordinary/required plan в execution/review flow:** создать `docs/code_drafts/<PLAN_BASENAME>__code_draft.md` (шаблон: `docs/code_drafts/_template.md`) и сослаться на него в plan → `Context links`. Даже если изменений мало — делаем stub (Targets + Steps + Notes). Единственное узкое исключение — admitted strict N-A `decomposition_wave` parent с oracle-derived `not_required`: он не фабрикует parent draft, а current-review proof берёт complete child graph.
  - Ownership: **Planner** создаёт/финализирует code draft на `**Status:** Planner finalize` (перед `Ready for Coder`). Architect может seed’ить минимальные заметки, но не должен “закрывать” работу Planner.
- длинные логи/tracebacks/выхлоп команд в fenced code blocks тоже запрещены (plan_lint считает строки, не “тип контента”): выносим в `docs/snapshots/` (или `.tmp/` для локала) и в plan оставляем ссылку + 1–2 строки “что это такое”.

## Tests / Commands / Evidence
Минимальный runnable contract:
- `## Tests` делим на две части:
  - `### Что написать / поправить` — какие тесты/смоуки/доки надо добавить или обновить.
  - `### Что прогнать` — какие проверки реально нужно выполнить перед handoff.
- `## Commands` — copy-paste runnable команды с явным interpreter/environment. Language, framework, database profile, runtime mode и harness объявляет selected target; при отсутствии такого contract — `N/A (why=...)` или blocker.
- Если wrapper/prompt уже дал concrete `PYBIN`, держи один interpreter spelling во всех command/proof surfaces (`Reviewability preflight receipt`, `Tests`, `Commands`, `Verification rerun / exec handoff`, code draft). Не смешивай `python3`, `$PYBIN` и absolute interpreter в одном handoff без явной причины.
- Если в рамках задачи сознательно ожидается force-push/переписывание истории, это нужно назвать прямо в `## Commands`; по умолчанию избегаем.
- `## Evidence` ведём append-only по времени. Любой чекбокс `[x]` в `Acceptance/DoD` должен опираться на запись/артефакт в evidence; иначе чекбокс не закрываем.
- Для rename/compatibility/docs-only slices, где acceptance завязана на отсутствие старого operator-facing имени/термина, proof surface должен ловить не только “новый exact pattern”, но и plain prose drift старого имени. Практическое правило: комбинируй narrow proof (например, точечный `rg` по новому wording) и broad proof по старому токену/имени, если старый термин может встретиться не только как function-call syntax.
- Для API/payload canon changes (`docs/api.md`, response schemas, helper output fields, JSON payload docs) handoff должен literal-но назвать changed payload fields, exact emitter/helper path и regression assertion/readback. Если поле описано в canon, но emitter/assertion/readback не названы и не помечены `N/A (why)`, это field-level parity gap: targeted suites могут быть зелёными, а Reviewer обязан блокировать как S1.

### Censor receipts (same-session structured second opinion)
`Architect CENSOR`, `Planner CENSOR`, `Coder CENSOR` остаются внутри того же `PLAN_PATH` → `## Evidence`; отдельный review/report file для каждого censor pass не создаём.

Manager/router не должен заново реализовывать markdown-парсер для completeness
этих receipt'ов в prompt prose. Canonical readback для Manager gate —
checked-in helper:
`scripts/censor_receipts_harvest.py --plan <PLAN_PATH> --censor-role <Role> --handoff-status <Status> --format json`.
Manager читает additive object `censor_evidence_lint`:
`state=not_applicable|skipped_by_valid_hint|complete|incomplete`,
`reason_code`, `missing_fields`, `invalid_reasons`, `receipt_line`.
`incomplete` — fail-closed stop with helper reason; prompt text must not keep a
second manual checklist for the same labels.

Native collab cold-start CENSOR gate:
- `MANAGER_CMD=run` и `MANAGER_CMD=run Q` выполняют gate до ordinary status routing с exact mapping: `Architect draft|Ready for Planner -> Architect`; `Ready for Coder -> Planner`; `Ready for Review -> Coder`.
- Только exact post-wait `state=complete` для current role/status/dispatch создаёт ordinary subcase общей invocation-local single-use identity `verified_handoff(plan_ref, handoff_status, censor_role, proof_kind, proof_id, top_level_invocation_lineage, downstream_role_handle_lineage)`, где `proof_kind=censor_receipt` и `proof_id=censor_dispatch_id`. Tuple consume-ится непосредственно перед первым downstream message и теряется при restart, identity mismatch или role-handle replacement.
- При отсутствии matching tuple no-selector result остаётся diagnostic-only: `complete|missing|stale|skip` ведёт к одному fresh-ID CENSOR dispatch в existing persistent same-role thread, а malformed/ambiguous/conflicting provenance fail-closed без dispatch, downstream route или Manager-side Markdown repair. Native path не вызывает custom `planveyor_role_run *_censor` wrappers.
- Fresh dispatch ограничен invocation-wide cap key `(plan_ref,handoff_status,censor_role)`; downstream role-handle lineage в key не входит и respawn не сбрасывает attempted marker. После post-consume handle loss bounded respawn/liveness разрешён без resend: unspent cap допускает единственный cold-start CENSOR, spent cap запрещает second CENSOR и завершает current invocation с `cold-start cap exhausted after downstream handle replacement`.
- Первый post-dispatch non-green запрещает automatic retry. Один explicit Owner-authorized replacement использует новый ID, тот же thread и literal `No material semantic delta; provenance correction only`; failed IDs не переиспользуются, malformed historical rows не редактируются и не удаляются, второй non-green останавливает flow без третьего CENSOR.
- При supplied ID каждый producer пишет ровно один raw `Censor dispatch id: <value>.`, `current=true`, canonical handoff header и одну `Observations:` boundary, затем сам запускает helper с exact role/status/dispatch. No-selector self-check не доказывает producer success; независимый Manager exact-selector readback остаётся routing authority.

Cross-iteration reduced handoff (`small_slice_parity`) для native `run|run Q` и custom single-plan/queue:
- Оба Manager mode переиспользуют одну invocation-local single-use identity `(plan_ref, handoff_status, censor_role, proof_kind, proof_id, top_level_invocation_lineage, downstream_role_handle_lineage)`. Existing ordinary path сохраняет `proof_kind=censor_receipt` и `proof_id=censor_dispatch_id`; reduced path использует `proof_kind=small_slice_parity` и raw `proof_id=(PRE_ROLE_SMALL_SLICE_PAYLOAD, POST_ROLE_SMALL_SLICE_PAYLOAD, post_role_oracle_run_id)`.
- `discovery-or-seed` разрешён только после primary completion, fresh post-role oracle и exact-green PRE/POST parity по ровно двенадцати полям: `plan`, `requested_profile`, `expected_bundle_family`, `helper_validation`, `drift_behavior`, `code_draft_path`, `target_paths`, `actual_bundle_family`, `live_review_artifact`, `review_route_kind`, `rollout_packet_is_na`, `visual_acceptance_is_na`. Missing field, red helper или drift запрещает seed и возвращает ordinary CENSOR.
- Tuple переживает только ровно одну следующую mapped iteration. Эта iteration является `receipt-reuse-only`: `current-helper-revalidation` выполняет `planveyor_q_small_slice_json <PLAN_PATH>` перед pending и повторно непосредственно перед consume для любого mapped downstream route, включая Reviewer; оба current payload должны быть green, иметь exact twelve-field shape и быть exact-equal stored PRE/POST payloads. Затем fresh oracle/status/censor role, top-level invocation и downstream lineage обязаны exact-match, а tuple consume-ится и очищается непосредственно перед первым downstream send. Native lineage = current persistent downstream role handle; custom lineage = current downstream role `session_key+SID`.
- Tuple является router permission only: он не выбирает status/role, не меняет plan/queue, не принимает semantic route и не заменяет oracle/helper/queue truth. No-selector receipt, plan Evidence, notice или success text и thread memory не восстанавливают permission (`notice/success text != mutation truth`).
- Pre-consume current helper error, missing/red payload, shape/field drift, identity drift, restart, replay, native handle replacement или custom `session_key+SID` mismatch очищают tuple и возвращают ordinary CENSOR. Current helper truth не становится новой authority family и не сохраняется durable. Duplicate consume запрещён.
- В custom mode такой возврат ставит invocation-local negative gate `REDUCED_REVALIDATION_FAILURE_KEY=(plan_ref,handoff_status,censor_role)` только после failed revalidation реально существующего `proof_kind=small_slice_parity` tuple или matching reduced pending. Штатный `verified_handoff=null` и non-opted ordinary `proof_kind=censor_receipt` не создают key и сохраняют existing `state=complete|skipped_by_valid_hint` route без wrapper dispatch. Пока exact key matching, no-selector `state=skipped_by_valid_hint` и pre-wrapper `state=complete` остаются diagnostic-only: Manager обязан запустить corresponding actual ordinary CENSOR wrapper, а только post-wrapper helper-confirmed `state=complete` снимает failure key и разрешает downstream send. Negative key не создаёт routing authority и очищается при другой current plan/status/censor-role identity.
- Native post-consume handle loss сохраняет existing no-resend/cap matrix: tuple/pending/consumed очищаются, send не повторяется; unspent `(plan_ref,handoff_status,censor_role)` cap разрешает ровно один ordinary cold-start CENSOR, spent cap завершает invocation с `cold-start cap exhausted after downstream handle replacement`.
- Custom post-consume loss остаётся helper-owned non-green stop: tuple/pending/consumed очищаются, resend/reuse/Manager recovery запрещены. Reviewer/final Architect, helper/runtime/schema и durable-state authority этим contract не сокращаются и не расширяются.

Каждая новая censor-запись materialize-ит короткий structured receipt с literal labels:
- `Artifacts opened`
- `Review verdict seen`
- `Blocker IDs considered`
- `Role-owned finding`
- `Reconciliation`
- `Final censor verdict`

Правила:
- `NO FINDINGS` без literal `Review verdict seen` + `Reconciliation` невалиден.
- `Blocker IDs considered` использует canonical `<review_artifact_path>#B<N>` when available; если blocker lineage ещё не materialized, пишем `N/A (why)`, а не prose alias.
- `Review verdict seen` честно называет одно из: live blocker verdict, `✅ OK (historical anchor only)` для rewritten-green append-only anchor, или `no live review artifact`.
- `Reconciliation` явно фиксирует одно из: `live blocker belongs here | live blocker does not belong here | historical anchor only | no live blocker`.
- Для repeated same-status / same-blocker loops к тому же receipt literal-но добавляем `Loop signal`, `Root cause class`, `Why previous rerun did not break the loop`, `Extraordinary action`.
- Post-merge audit оценивает quality censor именно по этому receipt, а не по prose-only self-praise.
- small-slice reduction не отменяет этот receipt-гейт глобально: same-session censor можно пропустить только когда `## Small-slice conveyor classifier` explicit opt-in и `_planveyor_q_small_slice_json <PLAN_PATH>` truthfully вернул `reduced_conveyor_eligible=true`; иначе full censor path остаётся обязательным.

Evidence-only CENSOR skip:
- Mode boundary: этот role-authored hint действует только в legacy/custom/manual no-selector flow. Native collab сначала применяет helper-backed `planveyor_q_small_slice_json`; если после non-skip routing Manager создал fresh `CENSOR_DISPATCH_ID`, role-authored hint не отменяет отдельный Manager dispatch и не удовлетворяет selector.
- Role-run может поставить `Censor hint: skip (why=...)` только для текущего same-session handoff, если diff действительно ограничен status/handoff wording, evidence chronicle, command/evidence restamp или equivalent docs-only audit wording и **не** меняет contract semantics.
- Запрещено ставить skip hint, если менялись `Decisions`, `Scope`, `Solution`, `Changes`, `Acceptance/DoD`, executable targets/code draft targets, reviewer route, test/smoke/repro contract, queue/oracle/lint semantics, promoted-route truth или any Owner/Architect decision.
- Каждая skip-запись обязана иметь explicit `why=` в `## Evidence`, чтобы Manager/Post-merge audit могли прочитать основание без chat memory.
- Anti-spam limit: для одного `PLAN_PATH` нельзя применять больше двух подряд same-role/same-status `Censor hint: skip` без полного same-session CENSOR pass или явного Owner/Architect stop. Третий подряд hint считается stale/unsafe и Manager запускает CENSOR.

## Shared contract carrier changes (bounded fan-out rule)
Trigger узкий: это shared helper/adapter, чей diff меняет externally visible HTTP/status/event/redirect/response-body semantics или repo-visible CLI/JSON/receipt fields, severity/verdict/exit-code/aggregation semantics для нескольких consumer paths. Это **не** blanket-rule на любой util/helper.

Что обязано появиться в executable handoff:
- helper/adapter path;
- dependent tests;
- dependent docs;
- known consumer paths.
- consumer contract semantics: `verdict/blocker` vs `candidate/evidence/prefill`, severity/warn/blocking behavior, output schema/field compatibility.

Owner-facing Manager command surfaces входят в этот контракт. Если plan
добавляет или меняет `MANAGER_CMD=<cmd> [PLAN_PATH]` /
`planveyor_manager_collab_cmd <subcommand> [PLAN_PATH]`, handoff обязан назвать
helper/runtime surface, one-shot dispatch surface (`scripts/planveyor/role_runtime.zsh`)
или explicit `N/A (why=dispatch path unchanged/not owner-facing/not one-shot)`,
owner documentation/help/readback surface, dependent tests и cold explicit-path
regression без cached `.planveyor.planpath`, если `[PLAN_PATH]` рекламируется.
Если dispatch behavior меняется, runtime/test files становятся mutable bundle targets;
если dispatch не меняется, он может оставаться contextual fixture только с explicit `N/A`.

Ownership по конвейеру:
- Architect: поднимает trigger и не отдаёт `Ready for Planner`, пока bounded dependent inventory не materialized в plan.
- Planner: переносит тот же inventory в plan + code draft; формулировки `audit later` / `dependents потом` / “grep потом найдём” к `Ready for Coder` запрещены.
- Coder: трактует change как fan-out slice и до `Ready for Review` reconcile-ит helper/tests/docs/known consumers; stale dependents не остаются implicit follow-up.
- Censors: rollback/hard fail, если literal handoff всё ещё позволяет “поменять helper локально, а dependents проверить потом”.

Граница правила:
- audit остаётся bounded repo-visible surfaces: helper, прямые dependents и известные consumer paths, которые реально находятся через канон/поиск;
- если helper output является только candidate/evidence/prefill lane, plan + code draft должны literal-но назвать это и добавить consumer regression; green helper tests без consumer-severity proof = false green;
- blanket repo-wide audit на любую похожую функцию не требуется.

## Reviewability preflight receipt
Используй literal `## Reviewability preflight receipt` в plan + code draft, если handoff зависит от checked-in helper family, named non-primary carrier / contextual lane или deterministic visual/native/stateful proof path.

Минимальные поля:
- `proof-path class`
- `mandatory primary lane`
- `mandatory non-primary carrier / contextual lane`
- `exact helper path + support files`
- `dependent tests / dependent docs / known consumer paths` (если carrier shared/fan-out sensitive)
- `preconditions / seed-discovery`
- `reroute rule`

Правила:
- receipt materialize-ится одновременно в plan и code draft; Coder/Reviewer не должны восстанавливать helper/screenshot/runtime contract из chat memory;
- `mandatory primary lane` = честный repo-backed truth lane по умолчанию;
- `mandatory non-primary carrier / contextual lane` = literal alternate/bypass/contextual proof, если тот же contract обещан вне primary lane; если такого lane нет, пиши `N/A (why)`;
- Для source-owned rollout-packet refresh slice `mandatory primary lane` обычно включает и `plan_lint`, и packet-scoped `doc_lint`; `preconditions / seed-discovery` literal-но говорят, packet pair already materialized или создаётся впервые, а contextual lane читает packet на queue/import boundary и importable-boundary / not-yet-landed guards.
- Если packet pair ещё не materialized в repo и текущий Planner pass только готовит create-from-scratch handoff, packet-scoped `doc_lint` остаётся честным coder-time proof lane после materialization, а не выдаётся за уже-пройденный gate этого planner/censor pass.
- если proof lane stateful и многошаговый, receipt обязан literal-но назвать: какой шаг `discovery-or-seed`, какие downstream steps `receipt-reuse-only`, какие stable identity fields должны пережить весь lane, и что потеря receipt continuity после первого шага = hard-fail, а не silent rediscovery/reseed другого entity;
- если proof закрывает race/lock/idempotency contract через retry/stale-instance regression вместо настоящего thread/process concurrency или DB-level uniqueness/constraint proof, receipt/AC/evidence должны назвать это как substitute proof boundary и не продавать его как полный concurrency proof; full proof или constraint hardening уходит в explicit follow-up/reroute.
- если proof lane содержит transient redirect/return/callback/wizard/pending carrier (`next`, return URL, callback URL, pending-auth state и аналоги), receipt/checklist должен назвать terminal sink assertion: доказан не только intermediate redirect/session propagation, но и финальный успешный sink того же carrier.
- если proof lane пишет receipt/output artifact, receipt обязан literal-но назвать retention class для каждого path family: `transient local sanity only` vs `durable operator/review evidence`; `.tmp/...` по умолчанию считается transient и не может молча подменять `docs/reviews/...` или другой durable carrier;
- если contract зависит от transient one-shot / first-read / next-snapshot semantics, receipt обязан назвать exact observer boundary, а не только eventual outcome;
- `notice/success text` не закрывает mutation truth сам по себе: receipt должен назвать next canonical snapshot/readback того же entity как closure carrier;
- если promised carrier зависит от active runtime/process/listener/build, receipt обязан назвать `runtime-lineage preflight` и runtime-owning reroute before coder/product reopen;
- если exact shared lane materialize-ится только в одном primary carrier, но paired contextual/no-dup carriers удерживают тот же contract honest (followups wrapper, manager bridge, alternate proof host, routing adapter), перечисляй их literal-но в `mandatory non-primary carrier / contextual lane` и/или `dependent tests / dependent docs / known consumer paths`; `primary lane green, contextual lane implicit` = planner-owned false green;
- если current repo/profile ещё не содержит truthful live corpus/entity set для этого contract, receipt обязан literal-но назвать synthetic proof carrier (`temp fixture`, `temp dir`, seed generator) и отдельно зафиксировать, что checked-in sample artifacts / historical backfill вне текущего bundle, пока они не materialized отдельным slice;
- если без synthetic proof closure не доказывается, не раздувай bundle молча: reroute в follow-up/new plan вместо ad-hoc sample corpus в текущем handoff;
- если scenario держится на visual/native proof, receipt обязан literal-но зафиксировать perceptual truth-source split:
  - structural/repo-backed carrier preferred whenever it exists;
  - screenshot OCR / template matching / pixel search по proof artifact = debug-only signal, не blocker/green proof;
  - built-in `LLM image reading` по уже захваченному canonical artifact допустим как bounded fallback, если нет более простого truthful carrier;
  - repeated image-based fallback по одному и тому же flow = helper/wrapper gap или target-repo follow-up, а не steady-state closure lane;
- receipt должен прямо называть, когда helper обязателен как `surface opener + capture + receipt`, а когда proof закрывается standard primitives без нового launcher.

### State-transition declarations (opt-in)

Если stateful handoff должен компактно зафиксировать только декларативную границу перехода, внутри уже materialized `## Reviewability preflight receipt` допустим ровно один literal subsection `### State-transition declarations` с четырьмя строками:

- `before-state`: carrier=<literal>; identity=<literal>; expected=<literal>
- `allowed mutation inventory`: writer=<literal>; entrypoint=<literal>; targets=["<canonical mutation identifier>", ...]
- `after-state`: carrier=<literal>; identity=<literal>; expected=<literal>
- `protected-target post-review continuity`: targets=["<repo-relative POSIX path>", ...]; on_change=same-file-review-rerun

Каноническая Markdown-форма — list item с label в backticks, colon и unquoted value. `plan_lint.py` игнорирует только outer whitespace у label/value и у разделителей subfield; scalar values case-sensitive. Labels и subfields идут ровно в показанном порядке, aliases/duplicates/placeholders не допускаются. `before-state` и `after-state` должны literal-но совпадать по `carrier` и `identity`; различаться может только `expected`.

Это opt-in structural aid, а не новая state machine или второй writable truth source. Active local block валидируется на любом status; на status, где уже обязателен code draft, plan и draft обязаны содержать нормализованно одинаковые четыре строки. Оба canonical templates держат пример только в HTML comment, поэтому обычный новый plan/draft не включается в этот lint автоматически.

`protected-target ... targets` — JSON array unique sorted repo-relative POSIX paths без absolute/backslash/empty/`.`/`..` segments; он точно равен normalized set `code_draft_meta.targets`. Это только implementation set: `PLAN_PATH`, code draft, единственный live review artifact, append-only Evidence/review stamps и explicit assets по-прежнему остаются отдельными full-bundle members ADR 004. `on_change=same-file-review-rerun` лишь называет уже существующий producer-backed route для доказанного mismatch: unavailable producer, concurrent replacement и generic lint failure сохраняют текущую fail-closed `unknown` classification.

Четыре декларации не заменяют applicable stateful receipt: `discovery-or-seed`, downstream `receipt-reuse-only`, stable identity, exact observer boundary, next canonical snapshot/readback и runtime-lineage preflight остаются обязательными, когда их требует реальный proof lane.

### Semantic review observation contract

Это отдельный opt-in producer/readback contract для plan, которому нужно хранить проверяемую semantic lineage блокеров между review generations. Он не меняет route, status, queue, budget, checkpoint или метрики: `PLAN_PATH` и live review artifact остаются truth hosts, а stdout helper — только производный readback.

Активация существует только при literal subsection внутри уже materialized `## Reviewability preflight receipt` с **ровно** тремя строками:

```markdown
### Semantic review observation
- `schema=semantic_review_observation.v1`
- `mode=required`
- `writer=reviewer_code_contracts`
```

Этот marker нельзя дополнять prose/aliases. Отсутствие subsection означает legacy/non-opt-in plan: helper возвращает `not_available/feature_not_activated`, у Reviewer нет writer duty и нельзя выводить inferred green. Пример, оставленный внутри HTML comment шаблона, marker не активирует.

#### Автор и единственный допустимый input

После helper-selected current plan-resident `reviewer_code_risk` JSON block и aggregate verdict только `reviewer_code_contracts` может append-ить ровно один fenced JSON proposal в `## Evidence`:

```json
{
  "schema_version": "semantic_review_observation_proposal.v1",
  "progress_verdict": "...",
  "progress_evidence_refs": [],
  "blockers": [],
  "resolved_predecessor_blocker_refs": []
}
```

Это весь role-owned input. У proposal ровно эти пять top-level keys. Каждый `blockers[]` имеет только `blocker_ref`, `lineage_relation` и `predecessor_blocker_ref`; список отсортирован по canonical `B<N>`, а `resolved_predecessor_blocker_refs` — sorted unique. Допустимые `lineage_relation`: `first_observation`, `same_family`, `independent_boundary`. Для `first_observation` и `independent_boundary` predecessor равен `null`; `same_family` обязан literal-но сослаться на blocker из immediately preceding accepted final head через `<review-artifact-path>#B<N>`.

Role никогда не вводит `risk_run_id`, target/review/fingerprint, `review_generation_id`, `observation_id`, `predecessor_observation_id`, `proposal_sha256`, `blocker_family_id`, `resolved_blocker_family_ids` или unknown fields. CENSOR, `reviewer_code_risk`, Manager, chat, env/status/queue input не могут создать proposal/final carrier.

#### Read-only materialization и lifecycle

Единственная operator surface — `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py semantic_review_observation.py --plan PLAN_PATH --format json|text`. У CLI нет write/proposal/route/status flags. Для активного marker-а `reviewer_code_contracts` исполняет один literal handshake:

1. Читает helper после selected risk generation и aggregate verdict.
2. При `ready_to_materialize/role_proposal_required` append-ит единственный proposal после selected risk block.
3. Повторно читает helper. При `ready_to_materialize/observation_not_materialized` копирует **без ручной сборки** exact `materialization.observation` в `## Evidence` как final `semantic_review_observation.v1` object.
4. Читает helper в третий раз. Только `valid/current_observation_valid` закрывает handoff; тот же valid result idempotent и ничего больше не append-ит.

`materialization.observation` уже содержит complete machine envelope с `observation_id`, `review_generation_id`, `risk_run_id`, `target_snapshot`, `review_artifact`, `contract_fingerprint`, `predecessor_observation_id`, `proposal_sha256`, composite `blockers` и `resolved_blocker_family_ids`; role копирует bytes/object exactly, а validator заново вычисляет их из `PLAN_PATH`.

JSON report имеет ровно top-level fields `schema_version`, `state`, `reason_code`, `candidate_machine_fields`, `materialization`, `validated_chain`, `errors`; его `schema_version` = `semantic_review_observation_report.v1`. `candidate_machine_fields` всегда сохраняет keys `risk_run_id`, `target_snapshot`, `review_artifact`, `review_generation_id`, `observation_id`, `contract_fingerprint`, `predecessor_observation_id`, `proposal_sha256`, `blocker_machine_fields`, `resolved_blocker_family_ids` (unavailable value = JSON `null`, не пропущенное prose). Returned final object имеет ровно `schema_version`, `observation_id`, `review_generation_id`, `risk_run_id`, `target_snapshot`, `review_artifact`, `contract_fingerprint`, `predecessor_observation_id`, `proposal_sha256`, `progress_verdict`, `progress_evidence_refs`, `blockers`, `resolved_blocker_family_ids`.

`contract_fingerprint` — helper-owned object с `schema_version=contract_fingerprint.v1`, `sha256`, sorted unique `target_paths` и `deleted_paths`. Его canonical payload включает normalized code-draft targets/deletions, единственный live review path, H2 sections `Decisions (final)`, `Scope`, `Out of scope`, `Changes (by area)`, `Acceptance criteria / DoD`, `Tests`, `Commands` и accepted state-transition declarations. Paths приводятся к repo-relative POSIX form, sections — к LF без trailing horizontal whitespace/outer blank lines; hash serializer использует canonical UTF-8 JSON. Reviewer не строит fingerprint и не меняет его schema/normalization без новой version.

| Helper state | `reason_code` | Семантика и действие |
| --- | --- | --- |
| `not_available` | `feature_not_activated` | Legacy/non-opt-in absence; не green и не writer duty. |
| `not_available` | `risk_generation_not_available` | Active marker, но ровно zero raw risk fences и zero proposal/final carriers: clean waiting, не legacy. |
| `ready_to_materialize` | `role_proposal_required` | Есть selected risk generation, но нет eligible proposal: contracts lane пишет только proposal. |
| `ready_to_materialize` | `observation_not_materialized` | Есть valid unconsumed proposal, но нет attempted final: можно скопировать только returned `materialization.observation`. |
| `valid` | `current_observation_valid` | Fresh accepted current head; idempotent readback и единственный downstream-eligible result. |
| `blocked` | первый validation failure | Не финализировать и не подменять red prose/route inference. |

State semantics validation-first: для active marker-а любой activation/selector/live-review/code-draft/fingerprint/proposal/final/chain/current-head/role error побеждает normal lifecycle. Canonical first-failure order: `activation_invalid`, `risk_lane_selection_blocked`, `live_review_artifact_invalid`, `code_draft_invalid`, `fingerprint_unavailable`, `role_proposal_invalid`, `observation_schema_invalid`, `observation_chain_invalid`, `current_head_mismatch`, `role_field_invalid`. Raw risk fence без unique selected source, unbound proposal/final, duplicate eligible proposal или malformed pairing — `blocked/risk_lane_selection_blocked`, а не waiting.

#### Current blockers и `BUNDLE=current` proof

Semantic input о blocker-ах берётся только из canonical `### B<N>)` records внутри одного `## S1 Blocker` live review artifact: heading и единственный `Blocker ID: B<N>` совпадают, `Current state` ровно один из `open`, `historical-fixed`, `superseded`, IDs unique. `✅ OK` header и aggregate verdict требуют zero `open` records и exact `blockers=[]`; `❌ S1 blocker(ы)` требуют non-empty canonical open set. Current proposal/final должен exact match этому open set; historical/superseded prose не является current lineage.

Для `BUNDLE=current` plan-resident `reviewer_code_risk` receipt остаётся compact selector truth: он хранит literal target/bundle SHA и обязательные `full_payload_ref` + `full_payload_sha256`. Полный raw `review_target_snapshot.v2` (ordinary primary-draft branch) или `review_target_snapshot.v3` (admitted strict-N-A child-graph branch) stdout живёт byte-for-byte только в immutable run-specific support JSON `docs/code_reviews/assets/<plan-stem>/reviewer_code_risk_<run-stamp>.json`; shared validator проверяет SHA, exact nested versioned producer payload, projection того же target/hash и exact canonical `findings` projection (`id`, `severity`, `domain`, `title`, `source_refs`). Равная cardinality не заменяет semantic parity; support-only detail fields не materialize-ятся в compact receipt. Полный raw stdout в plan и generic exemption для large JSON запрещены; rerun создаёт новый asset, а старый не переписывает.

Все parseable plan-resident `reviewer_code_risk` carriers с хотя бы одним `full_payload_ref` / `full_payload_sha256` одновременно образуют all-history exact-bundle manifest: пара обязательна, symlink-free по leaf и каждому ancestor, и byte-hash durable независимо от `current`. Historical red/legacy payload не проходит заново JSON/schema/parity validation; эти semantic checks принадлежат только helper-selected current carrier. Неполная пара, unsafe/out-of-root/symlink ref, missing file, SHA mismatch или conflicting hashes одного ref fail-closed блокируют bundle и closeout до mutation.

После Coder mutation protected target bytes helper остаётся `blocked/current_head_mismatch`. Ordinary `plan_lint` может показать только WARN, не semantic green, и только при всех условиях: status `In progress` или `Ready for Review`; один red same-file review с current-cycle `Stale note` и `Rerun note`; ровно одна diagnostic `semantic_current_target_snapshot_stale`, опционально вместе с ровно одним `semantic_observation_machine_fields_mismatch`, который сообщает только `contract_fingerprint`. Это сохраняет immutable historical P/F при same-contract clarification, но не делает их current. Любой другой diagnostic, missing note, green review или `Ready for Arch review` остаётся ERROR; новый selected risk receipt и P/F materialize-ит только Reviewer rerun.

#### Lineage, freshness и consumer boundary

Proposal `P` должен физически стоять после helper-selected current risk block. Он потребляется только final `F`, который является immediately next semantic carrier after `P`, имеет matching canonical `proposal_sha256` и совпадает с source risk generation по `risk_run_id`, `target_snapshot` и recomputed `review_generation_id`. Identical proposal bytes не разрешают потребить proposal из другой generation; historical proposal до current risk block не становится eligible.

Только fully validated `F` образует immutable node. Первый accepted node имеет `predecessor_observation_id=null`; каждый следующий указывает на immediately preceding accepted head. `first_observation` и `independent_boundary` получают helper-seeded `blocker_family_id`, `same_family` переиспользует family только по literal predecessor ref; закрытые predecessor refs helper отображает в sorted unique `resolved_blocker_family_ids`. Final progress verdict остаётся role-owned (`first_observation`, `same_contract_progress`, `same_contract_stalled`, `scope_churn`, `independent_boundary`), но helper его не изобретает и не принимает hand-authored machine identity. `first_observation` возможен только без predecessor; progress требует доказанного closure predecessor family, stalled — surviving family, churn — contract/target drift без доказанной independent boundary, а independent boundary — отдельного writer/consumer/lifecycle contour. Если применимо несколько описаний, summary precedence: `scope_churn` > `independent_boundary` > `same_contract_stalled` > `same_contract_progress` > `first_observation`.

Malformed unconsumed current proposal или attempted final до первого valid readback можно заменить in place. После consumed `P` + accepted `F` они immutable; новый final/proposal для той же selected generation запрещён. Historical nodes проверяются по сохранённым identity/lineage bytes, а только unique current head — по live selector, fingerprint и target snapshot.

`scripts/plan_lint.py` fail-closed для active malformed/stale/unbound carrier и для active final Reviewer handoff без valid head. Downstream checkpoint/metrics и любой иной consumer могут принимать только `valid/current_observation_valid`: `feature_not_activated` — legacy coverage absence, `risk_generation_not_available` — active waiting, `ready_to_materialize` — writer/readback work, а `blocked` никогда не превращается в route, metric или inferred progress.

### Semantic cycle checkpoint contract

`semantic_cycle_checkpoint.v1` — opt-in consumer accepted `semantic_review_observation.v1` history. Он не меняет producer schema, не читает review prose/CENSOR/retry и не создаёт Manager ledger. Активация требует **обе** literal subsections в одном `## Reviewability preflight receipt`:

```markdown
### Semantic review observation
- `schema=semantic_review_observation.v1`
- `mode=required`
- `writer=reviewer_code_contracts`

### Semantic cycle checkpoint
- `schema=semantic_cycle_checkpoint.v1`
- `mode=required`
- `writer=architect`
```

Отсутствующий checkpoint marker — legacy/non-opt-in. Наличие checkpoint без exact producer marker — `activation_invalid` и fail-closed. Template examples обоих markers остаются только в HTML comment. При active clean `risk_generation_not_available` checkpoint ждёт и сохраняет ordinary pre-review route; `ready_to_materialize/*` остаётся Reviewer duty, producer `blocked/*` сохраняет producer-owned failure. В projection входят только `valid/current_observation_valid` accepted heads.

Trigger считается только по adjacent accepted heads: `family_survival` требует `same_family`, тот же `blocker_family_id`, exact predecessor ref и changed `target_snapshot`; same-snapshot rerun не расходует budget. Open `independent_boundary` или `scope_churn` trigger-ят сразу. Primary kind выбирается строго `family_survival > independent_boundary > scope_churn`, но один trigger обязан покрыть sorted unique family ID **всех** current open blockers. Green `blockers=[]` идёт в ordinary Architect final gate.

Architect — единственный writer fenced `semantic_cycle_checkpoint_resolution.v1` в `PLAN_PATH::## Evidence`. У объекта ровно `schema_version`, `trigger_observation_id`, `trigger_kind`, `contract_fingerprint`, `required_family_resolutions`, `decision_evidence_refs`, `allowed_next_status` и conditional `successor_plan_ref` / `owner_question_ref`; unknown/duplicate keys и family entries запрещены. Family list exact-cover-ит trigger set и использует один compatible decision: `same_contract_once -> Coder intake`, `de_scope -> Reviewer intake`, `successor -> Superseded`, `stop -> Architect response`.

`same_contract_once` single-use для одного `blocker_family_id` и не разрешает второй `Coder intake`, в том числе после fingerprint/target drift. `contract_fingerprint` остаётся exact freshness/binding полем каждого resolution, но не создаёт новый consumption key. `de_scope` подтверждает только уже literal-но excluded family из unchanged `Out of scope` (без Scope/Acceptance/target delta). `successor` требует materialized distinct plan, `stop` требует decision evidence или open Owner question. Partial/mixed/stale resolution fail-closed.

`scripts/semantic_cycle_checkpoint.py --plan PLAN_PATH --format json|text` — read-only report. `scripts/plan_status_oracle.py` применяет его после `scope_expansion_*` и до review/raw status, выдавая Manager только existing `route_guard_*` и `route_guard_next_owner=Architect`; Manager не пишет resolution и не классифицирует families. Architect reread-ит oracle, нормализует guarded downstream status через `Ready for Architect response -> Architect response`, append-ит resolution, reread-ит oracle и ставит только exact decision exit.

### Bounded-grammar checkpoint V2

`semantic_cycle_checkpoint_resolution.v2` — отдельный opt-in overlay, а не
миграция V1. Он включается только в **другом** subject plan с
frozen+confirmed `recommended_route.kind=bounded_grammar`, valid
`grammar_contour`, paired V1 markers, current accepted checkpoint trigger и без
вышестоящего `scope_expansion` reroute. Сам implementation plan с
`structured_carrier` и ordinary V1/non-admitted plans не получают V2 write duty.

Architect — единственный semantic writer exact accepted V2 object в
`PLAN_PATH::## Evidence`. Он связывает current subject admission id/digest,
stable `grammar_contour_id`, immutable trigger/fingerprint и sorted exact family
rows `{blocker_family_id, blocker_ref, grammar_axis_ids, decision}`. Decision
всегда uniform: `same_contract_once`, `de_scope` или `successor`; V2 `stop`
запрещён. Permit `same_contract_once` расходуется один раз на весь stable
contour, не на новый family/fingerprint/snapshot. После его расхода
`de_scope` остаётся только для literal pre-existing exclusion, а `successor`
требует distinct non-terminal frozen+confirmed `structured_carrier` plan с exact
backlink и `semantic_cycle_successor_intake.v1` family transfer. `scope_churn`
разрешает только concrete successor; active scope-expansion guard всегда выше.

V2 history валидируется against each accepted trigger and its subject snapshot;
only strict `resolution_state=accepted` consumes budget. Explicit malformed,
duplicate, stale, mixed V1/V2 or partial carrier is fail-closed; review/CENSOR
prose и JSON other schemas не являются V2 carrier. `scripts/plan_lint.py`
остаётся sole selector, `scripts/semantic_cycle_checkpoint.py` and generic
oracle only project its result, and Manager/Planner/CENSOR never write or
reparse a V2 decision.

## Planner finalize: exact executable bundle sync
На `Ready for Coder` Planner уже замораживает current executable bundle, а не оставляет его на уровне seed hints.

Правила:
- authoritative exact executable bundle = `code_draft_meta.targets`;
- origin `PLAN_PATH` не может входить в `code_draft_meta.targets` для mutable `BUNDLE=current`: Reviewer append-ит lane receipt в plan и тем самым делает hash такого target самопротиворечивым. `plan_lint` классифицирует same-file aliases как `origin_plan_in_review_targets`, а direct snapshot producer fail-closed до hash output. Valid immutable `RANGE=<base>..<head>` review сохраняет собственный range contract. Exemption для immutable `COMMIT=<sha>` допустим только после однозначного разрешения ref в commit object внутри Git repo origin plan; missing/fabricated/unresolvable/ambiguous refs, `COMMIT=staged|current` и `BUNDLE=staged|current` остаются fail-closed;
- для executable plan перед `Ready for Coder` Planner запускает `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_plan_bundle --preflight <PLAN_PATH>`. Preflight использует ту же exact-bundle truth, что и final closeout: malformed/missing top-level `code_draft_meta`, несовпадающий `code_draft_meta.plan`, missing/stale targets = Planner blocker; отсутствующий first-pass review artifact допустим только до Reviewer и только как `PLANNED`. После materialized review artifact post-review/final truth остаётся `planveyor_plan_bundle --check`;
- `## Changes (by area)`, `## Commands`, `## Verification rerun / exec handoff` и live `## Review artifacts` / `Expected artifact` должны literal-но описывать тот же current bundle и тот же proof host; если один carrier всё ещё говорит про другой target set, handoff не готов;
- command/proof surfaces должны использовать один interpreter/env spelling. Если роль запущена wrapper'ом с concrete `PYBIN`, restamp plan + code draft на этот же interpreter перед handoff; generic `python3` остаётся допустим только когда concrete interpreter truthfully неизвестен.
- если bundle содержит новый target path, которого ещё нет до Coder implementation, допустим только минимальный fail-closed path-tracking stub в самом target file: он должен быть literal `code_draft_meta.targets` member, явно говорить `replace before Ready for Review`, иметь planned owner/plan ref и не проходить как финальный reviewable content. First-class helper metadata вроде `planned_new_paths` вводим только отдельным helper/schema slice, а не prose-only обещанием.
- если slice строит новую carrier/helper family поверх already-landed baseline, plan + code draft должны literal-но развести `existing baseline surfaces` и `new targets`; paired contextual/no-dup carriers остаются в `dependent tests / dependent docs / known consumer paths`, даже если они не входят в прямой edit-bundle;
- `plan_meta.canon_updates` остаётся post-merge canon carrier'ом и не превращается в shadow implementation target inventory;
- `reread-only` / `context-only` / `support-only` / `optional` refs держим только в `Context links` и/или `## Reviewability preflight receipt`; пока они не вошли в реальный diff/proof path, их нельзя silently возвращать в `code_draft_meta.targets`, exact команды или `Expected artifact`;
- к `Ready for Coder` wording вроде `seed-only`, `stub ok`, `Planner later decides exact patch wording`, `refresh before coder handoff` или “потом сузим bundle” уже невалидно;
- если truthful closure требует вернуть context-only carrier в executable bundle или расширить target set beyond current draft, это Planner/Architect reroute, а не silent symmetric churn.

## Reopened blockers: same-contract reroute vs scope rewrite
Когда dev-plan возвращается после blocker/review loop, сначала классифицируй кейс по repo-backed фактам, а не по prose/artifact drift:
- `stale evidence / historical artifact mismatch`
- `same-contract reroute`
- `closed baseline + live blocker split`
- `real scope expansion`
- `de-scoped follow-up`

Правила:
- `same-contract reroute` = corrected reviewer lane / precondition / evidence wording при неизменных bundle, `code_draft_meta.targets`, `Scope/Acceptance/Tests/Commands` и Planner-owned contract. Такой reroute идёт на `Coder intake`.
- Это ordinary reroute правило не подменяет active `decomposition_wave` candidate-only materialization: complete candidate pack со строгой structural-absence формой сначала идёт `Planner finalize -> Ready for Coder`, а затем в Coder lane materialize-ит реальный graph. Нельзя использовать generic `same-contract reroute` как shortcut, чтобы пропустить Planner-owned candidate handoff или объявить queue-ready состояние без файлов.
- Для executable composite lane держим более узкий literal split: `same-cluster evidence reroute` (тот же cluster, те же targets и acceptance host; меняются только wording/preconditions/evidence) остаётся в исходном plan по тем же правилам `same-contract reroute`.
- `Ready for Coder` остаётся Planner-owned handoff после `Planner finalize`; Architect не использует его как shortcut для same-contract reroute.
- `real scope expansion` = изменились bundle/targets или Planner-owned contract; здесь возвращаемся в обычный Planner cycle.
- `de-scoped follow-up` = issue явно выведен из current Scope/Acceptance/bundle; current plan может закрываться только если debt записан в `Follow-ups (deferred)` / backlog lane и не нужен для текущего DoD. Это post-closeout/promote lane, а не live route для unresolved current blocker.
- `cluster-local material delta` = один cluster внутри executable composite lane уже требует новый helper/support path, новые seed/docs targets, новый screenshot/review host или другой contextual carrier. Это не same-file execution loop: Architect открывает blocking follow-up dev-plan по этому cluster, а старый composite file становится `Superseded` (если это обычный executable plan) или explicit reference-only baseline/umbrella; в старом файле остаются только baseline/reference summary и follow-up pointer.
- Scope split owner: Architect классифицирует route; Planner materialize-ит новый executable contract/backlog только после этой классификации; Coder/Reviewer останавливаются на out-of-bundle gap вместо silent bundle widening.
- Если старый зелёный slice остаётся только regression context/history, пометь его как `closed baseline`; новый актуальный blocker surface пометь как `live blocker`. Historical wording само по себе не переоткрывает product scope.
- Stable blocker lineage:
  - live blocker ref открывается только в текущем review artifact, когда Reviewer materialize-ит `❌ S1 blocker(ы)` или другой bounded stop verdict;
  - локальные ids внутри review artifact = `B1`, `B2`, ...; canonical cross-artifact ref в plan/rerun/audit = `<review_artifact_path>#B<N>`;
  - `same-contract reroute` переиспользует тот же canonical blocker ref в plan evidence и rerun notes; новый blocker ref допустим только для `real scope expansion` или нового независимого defect;
  - если live review artifact отсутствует, blocker ref задним числом не выдумываем: пишем `UNCONFIRMED` или поднимаем follow-up/process gap.

## Review artifacts (где ссылка на ревью)
- Reviewer создаёт review‑файл и **вписывает ссылку в plan** в секцию `## Review artifacts` (см. `docs/plans/_template.md`).
- В active dev-plan `## Review artifacts` должен materialize-ить **ровно один** live path для текущего bundle. Пока bundle остаётся docs-only, держим только `docs/doc_reviews/...`; если в final diff входит любой non-doc carrier, flip делаем сразу и literal-но на `docs/code_reviews/...` вместе с plan + code draft. Не оставляем обе literal path-ветки одновременно “на всякий случай”: это ломает deterministic review route и exact bundle resolve.
- Для executable `dev` plan в terminal `Done` live review artifact должен уже существовать на диске (`Code review (primary)` или `Doc review (docs-only)`). `Ready for Coder` может ссылаться на planned first-pass artifact, но `Done` без materialized review file — plan-lint `ERROR`. Explicit non-executable umbrella/master-plan parents не попадают в этот executable guard.
- Короткий shared reference для этого правила плюс compact `reviewability preflight receipt` examples: `docs/playbooks/review_route_and_receipt_canon.md`.
- Для execution/review-flow plan’ов primary guard для этого контракта живёт в `scripts/plan_lint.py`: он падает на dual live route в `## Review artifacts` и на docs-only bundle, который всё ещё ведёт literal live carrier в `docs/code_reviews/...`. Helper parity в `planveyor_plan_bundle`/`scripts/planveyor.zsh` не считается скрытым обязательством этого же slice и при необходимости идёт отдельным follow-up.
- В review‑файле используем серьёзность: **S1 Blocker / S2 Risk / S3 Nit** (см. шаблоны `docs/code_reviews/*`, `docs/doc_reviews/*`).
- Architect дописывает “Arch review” в тот же review‑файл и возвращает план на `Coder intake` либо принимает его. При current-task `COMMIT_POLICY=native_existing` Architect сам ставит `Done`; при `COMMIT_POLICY=human_explicit` он останавливается на принятом Arch review, а `Done` ставит отдельный `sibling close --commit` после preview.
- Если после reviewer blocker был coder fix-loop и rerun, lifecycle один: до reviewer rerun plan в `## Review artifacts` явно несёт stale/superseded + rerun note именно для текущего review file / текущего rerun window; historical notes из уже закрытых циклов не засчитываются. После rerun Reviewer переписывает этот же review‑файл in place новым verdict/timestamp/target, и он остаётся единственным current state.

## Review-only plans (classic review / merge-range)
Если Owner просит “классическое ревью” (например, диапазон `BASE..HEAD` после merge/конфликтов) и **нет существующего plan**, создаём отдельный plan в `docs/plans/` как **контракт на ревью** (target + DoD + commands/evidence + ссылка на review‑артефакт).

Обязательные пометки в review-only plan:
- `**Plan type:** review-only`
- `**Status:** Reviewer intake`
- в `## Problem`: явно “review-only, без кодовых доработок; фиксы — отдельным dev-plan”
- для merge-range rerun после blocker fix: явно объявить `Rerun mode: incremental | full`; для `incremental` обязателен `Baseline artifact`. Детальная семантика `Trusted unaffected surfaces` / `Reused evidence` живёт в `docs/playbooks/review_merge_range.md`, `docs/playbooks/review_scoping_plan.md` и `docs/code_reviews/_template_merge_range.md`.

Маршрутный guard:
- `scripts/plan_status_oracle.py --json` обязан возвращать `plan_type_norm` и `route_guard_*`.
- Если `plan_type_norm == "review-only"`, а статус попал в Planner/Coder lane (`Ready for Planner`, `Planner intake`, `Planner finalize`, `Ready for Coder`, `Coder intake`, `In progress`), Manager проверяет `route_guard_triggered` до обычной status-route таблицы и fail-closed отправляет план на Architect normalization.
- Исключение не бывает implicit prose: Architect должен либо restamp plan как `dev`, либо добавить machine-readable `plan_meta.review_only_route_override` с `owner: "Architect"`, `allow_planner_coder_lane: true` и непустым `reason`.

Шаблон: `docs/plans/_template.md` (подсказка по заполнению: `docs/playbooks/review_scoping_plan.md`). Рекомендуемое имя файла: `YYMMDD_HHMM_reviewer_<topic>.md`.

Практическая пометка (anti-footgun):
- Если review-only range не содержит runtime UI изменений (UI paths, объявленные target), не активируй visual gate “на автомате”: укажи explicit `N/A (why=...)` для visual contract и запиши в review-файле `## Visual evidence: N/A` с причиной.
- Если target literal-но объявил modes, endpoint и harness, это считается явной активацией visual gate: потребуется минимум 1 валидный скриншот на каждый declared mode.

Truthful scaffold contract for `planveyor_review_range_init()`:
- generated merge-range plan должен приходить уже materialized по критическому минимуму: literal `Review target`, concrete `## Review artifacts`, плюс заполненные `## Problem` / `## Solution (high level)` / `## Scope` / `## Tests` / `## Commands`;
- default same-range rerun reuse-ит уже существующий scaffold path только когда literal compatibility tuple совпадает целиком: `BASE`, `HEAD`, `EXCLUDE_DOCS`, resolved repo `profile_id`, derived review-host family и explicit rerun carrier tuple;
- intentional parallel history не угадываем: новый side-by-side scaffold появляется только при explicit `planveyor_review_range_init --force-new ...`, а не от самого факта повторного запуска;
- same-path default reuse keeps `.planveyor.planpath` pointed at the reused scaffold, but `.planveyor.planpath.log` must not grow by an exact consecutive same-path duplicate on that reuse path;
- review artifact path тоже materialize-ится truthfully и single-source: docs-only generated bundle → `docs/doc_reviews/{plan_stem}.md`, любой final generated bundle с non-doc carrier → `docs/code_reviews/{plan_stem}.md`; generated code draft обязан держать тот же literal path;
- generated `## Documentation impact / provenance` в plan и code draft выводится из exact filtered target metadata / `code_draft_meta.targets`: doc targets, которые `plan_lint` считает documentation targets, должны быть перечислены в `Synchronous doc/registry targets`; scripts/tooling-only range без таких doc targets получает explicit `N/A (why=...)`, а generated plan/draft/review carriers остаются отдельной derived-carriers строкой;
- generated plan/code-draft header lines must not use trailing whitespace for Markdown hard breaks; range-review scaffolds and shared templates must stay green under exact `rg -n "[[:blank:]]$" <generated/shared header carriers>` proof when this lane is in scope;
- отсутствие уже созданного review-файла на момент Planner handoff не меняет host contract: docs-only bundle всё равно ведёт в `docs/doc_reviews/...`, а wrong/stale `docs/code_reviews/...` здесь считается route drift, а не harmless placeholder;
- если current pass уже rerun после blocker-fix, shared scaffold принимает только explicit current-flow carrier `PLANVEYOR_REVIEW_RERUN_MODE`, `PLANVEYOR_REVIEW_BASELINE_ARTIFACT`, optional `PLANVEYOR_REVIEW_PRIOR_ARTIFACTS`; те же literal values materialize-ятся в generated plan (`Prior review / rerun artifacts`, `Rerun mode`, `Baseline artifact`) и в generated code draft (`## Current-flow rerun lineage`);
- helper не угадывает rerun lineage из git history, старых plan names или repo archaeology; полное отсутствие carrier сохраняет truthful `N/A (first pass)`, partial/malformed carrier = fail-fast до записи scaffold;
- generic “почти шаблон, Reviewer дособерёт позже” = process drift, а не допустимый стартовый state;
- UI modes, endpoints, credentials, runtime commands и visual harness materialize-ятся только когда их literal-но объявил selected target;
- для non-UI/docs/backend-only range и profile-ambiguous/native lanes scaffold обязан оставлять explicit `N/A (why)` или target-local note, без shared fallback.

## Follow-ups backlog (это НЕ plan)
Иногда нужно собрать “что осталось сделать” (после merge/по итогам ревью/из памяти) **без** немедленного запуска нового dev‑plan.

Правило: такие списки **не** кладём в `docs/plans/*` (планы = контракт, их роутинг/линтинг и удаление после merge устроены иначе).

Вместо этого:
- backlog‑список follow-ups ведём в `docs/followups/*` (см. `docs/followups/index.md`; шаблон: `docs/followups/_template_followups_backlog.md`);
- когда follow-up готов к реализации → создаём отдельный dev‑plan в `docs/plans/` (`**Status:** Architect initial draft`) и ставим ссылку на него в backlog.
- если source plan прямо говорит `removed from active scope` / `intentionally removed` / `если по-прежнему нужно`, это презюмируется как de-scoped actionable debt, пока не случилось одно из четырёх:
  - follow-up promoted в `docs/plans/*`,
  - item зафиксирован в `docs/followups/*`,
  - item already tracked elsewhere,
  - item explicit owner/canon decision says it is no longer needed.
- `NO FOLLOWUPS` в harvest/audit при наличии такого unmatched de-scoped item = process bug, а не допустимое упрощение.

## Golden Paths (entrypoints)
`Golden Path` = короткий default entrypoint для повторяемого workflow. Реестр живёт в движке: `"$PLANVEYOR_RUNTIME_ROOT/docs/guides/golden_paths.md"`.

Для shared/default process slices registry source-owned именно здесь, а runtime handbooks принадлежат owning target. Не называй shared UI carrier, пока он не materialized literal row в registry.

Важно:
- `Golden Path` не равен `cluster`;
- у одного `cluster` может быть `0..N` golden paths;
- если для темы уже есть active golden path, его ссылка должна быть в `Context links` рядом с BRD/ARCH/API/Schema/UI.

Правило:
- если задача реально живёт внутри existing golden path, Architect/Planner добавляют в `Context links` `"$PLANVEYOR_RUNTIME_ROOT/docs/guides/golden_paths.md"` и exact materialized row; при отсутствии row — follow-up или `N/A (why=...)`, не invented pointer;
- если range/plan повторно рождает один и тот же reusable recipe или invariant, а подходящего golden path нет — это follow-up на создание нового entrypoint, а не ещё одна buried note в review.

## Visual Acceptance (UI-gate)
Если задача меняет UI — в plan обязателен раздел `## Visual Acceptance` (см. `docs/plans/_template.md`), включая:
- **Modes / endpoint:** selected target literal-но объявляет нужные modes или endpoint; при отсутствии контракта — `N/A (why=...)` или blocker.
- **Runtime access and credentials:** selected target объявляет роль, account source и безопасный способ доступа; секреты не попадают в plan.
- **How to run:** plan содержит exact target command или target-declared harness и воспроизводимые preconditions/seed recipe; historical placeholder не считается live proof.
- Для составных контролов проверяем не только присутствие, но и релевантные интерактивные состояния.
- **Visual checks (screenshots required):** в plan должен быть список конкретных проверок с target path/entrypoint, ожидаемыми визуальными признаками и именами скриншотов (чтобы Reviewer не угадывал “что снимать”).
- Если visual proof намеренно перенесён в follow-up/e2e/post-deploy lane, `## Visual Acceptance` всё равно остаётся структурным: required subheads (`### Visual checks...`, `### Visual regression scenarios...`, при необходимости `### How to run...`) не удаляются, а внутри каждого стоит exact `N/A (why=...; follow_up_owner=...; ref=...)`. Один общий N/A-paragraph вместо subheads = plan gap.
- Для shared fragments truth source должен быть DOM/subtree/anchor-scoped. Fixed-length HTML chunk helper или global string search допустимы только как debug signal, но не как blocker/green proof.
- Screenshot OCR / template matching / pixel search по уже снятым proof images не считаются acceptance truth source; built-in `LLM image reading` допустим только как bounded interpretation layer по canonical screenshot, если нет более простого truthful carrier и если это не подменяет missing helper decision.
- Если helper красный, а live reviewer lane зелёный, plan должен вести Reviewer через явную классификацию `harness drift vs live regression` до product/runtime escalation.
- Для каждого mode фиксируем минимум: как дойти до UI, что именно видно/меняется, какой визуальный признак доказывает прохождение, имя файла скриншота.
- Скриншот должен сам доказывать check: не кропим “в никуда” и не прикладываем кадр, где целевой элемент/текст не виден.
- Скриншоты храним в `docs/code_reviews/assets/<REVIEW_BASENAME>/`; в review‑файле даём ссылку и 1 строку “что именно доказано”.
- **Visual regression scenarios (must-not-regress):** если добавили/изменили UI‑поведение, добавь/обнови сценарий в `docs/smoke_visual.md` (и залинкуй секцию из plan), чтобы не забыть ожидание после merge.
- **Perf checks (optional):** если задача про performance (“быстро/без подвисаний/оптимизация запросов”) — добавь в `## Visual Acceptance` явные проверки: entrypoint + действие (например, открыть экран или выполнить поиск) + ожидание (“без подвисаний”, “после прогрева < N сек” и т.п.), чтобы Reviewer мог это воспроизвести и зафиксировать в ревью.
- Visual gate (канон): любая визуальная поломка/ошибка = **S1 Blocker**. В этом случае нельзя двигать status вперёд (например, `Ready for Arch review` запрещён).

## Critical runtime invariants (risk-based UI handoff)
Это правило не для “любой UI-задачи подряд”, а для тех случаев, где visual/runtime expectation может формально пройти через hooks/tests, но всё ещё развалиться в live UI, через alternate surface или через `default-state / non-primary carrier`.

Когда включать:
- shared CSS/layout/brand logic;
- visibility/default-state behavior;
- access/guard semantics, которые живут не только на page route, но и на `fragment/list/api/supporting endpoint`;
- формулировки уровня `centered`, `hidden`, `default`, `stays in place`, если без runtime proof они оставляют место для догадок.

Что должен сделать Planner на `Planner finalize`:
- назвать 1–3 `critical runtime invariants`;
- для каждого invariant зафиксировать связку `risky touchpoint/surface -> hook/test proof -> runtime/browser proof -> alternate surfaces / entrypoints / bypass paths`;
- если risky alternate surface или same-surface `action/mode/state` branch не существует — явно написать `N/A (why)`, а не молчаливо пропустить.

Расшифровка:
- `hook/test proof` = server/template/test signal, который доказывает, что нужный hook/guard/class/event действительно выставляется.
- `runtime/browser proof` = какой живой browser/runtime check доказывает, что invariant реально соблюдён в UI, а не только “атрибут есть в HTML”.
- `alternate surfaces / entrypoints / bypass paths` = page/fragment/list/api/supporting endpoint/mode-role exception и same-surface `action/mode/state` variants (`create/edit`, `add/save`, `happy/invalid`, `new/reopen`), через которые тот же contract может быть обойдён.
- если risky contract живёт в `default-state / non-primary carrier`, Planner должен назвать этот carrier прямо в invariant/proof/closure map рядом с `action/mode` branch или явно записать `N/A (why)`.
- `OOB`, hidden-field, selected slug, filter-payload normalization и похожие web tokens = только profile-specific examples этой оси, а не generic vocabulary по умолчанию.

Граница роли:
- Planner работает как `contract, not implementation`: фиксирует risky invariant/proof/closure map, но не пишет production-like patch и не забирает у Coder runtime sanity/implementation ownership.
- Control cases уровня header-only правки не нужно раздувать в pseudo-spec; там допустим explicit `N/A (why)`.

## Plan gaps (канон процесса)
Plan gap = отсутствует/не заполнена обязательная часть контракта (AC/DoD/Tests/Commands/Visual Acceptance/чеклисты из шаблона) или есть двусмысленность, из-за которой нельзя безопасно реализовать/проверить.

Для risky UI handoff сюда же относится отсутствие проверяемой связки `critical runtime invariant -> risky touchpoint/surface -> hook/test proof -> runtime/browser proof -> alternate surface note`, когда без неё Coder/Reviewer неизбежно начинают “додумывать”.
Для helper/visual/native/stateful proof lanes сюда же относится отсутствие literal `reviewability preflight receipt` или perceptual split, из-за которого OCR/template/pixel heuristics можно принять за truth source либо repeated image-based fallback выглядит как нормальный steady-state lane.
Для phased rollout / feature flag / bridge / compatibility / migration-toggle задач сюда же относится rollout/deploy-контракт без точной матрицы из 6 пунктов или с внутренним противоречием между `repo default`, `expected live default`, поведением без pin и `safe to merge|deploy|flip`.

Правило обработки:
- Для `**Plan type:** dev`: plan gap = **S1 Blocker**. Возвращаем plan в `**Status:** Planner finalize` (или `Planner intake`/`Ready for Architect response` если это вопрос), и **не** ставим статусы “вперёд” (`Ready for Coder`/`Ready for Review`/`Ready for Arch review`) пока план не исправлен.
- Для `**Plan type:** review-only`: plan gap фиксируем в review‑файле (раздел `## Plan gaps`) и в plan (`Reviewer objections`), но **не** роутим процесс обратно на Planner. Дальше — handoff на Architect triage через `**Status:** Ready for Arch review`; любые фиксы делаем отдельным follow-up `dev` plan.

## Rollout / Flag / Bridge Contract (merge-safe/deploy-safe)
Для phased rollout / feature flag / bridge / compatibility layer / migration-toggle задач план обязан явно фиксировать rollout/deploy-контракт в существующих секциях (`## Solution (high level)`, `## Changes (by area)`, `## Acceptance criteria / DoD`), не превращая документ в отдельный операционный мануал.

Одна и та же точная матрица:
- `repo default`
- `expected live default`
- `missing env/config pin behavior`
- `safe to merge`
- `safe to deploy`
- `safe to flip + after what follow-up/condition`

Правила:
- Если safety зависит от external pin/manual step, в плане должна быть названа текущая защита, зафиксированная в репо. Устная deploy-договорённость или “не забудем после merge” не считаются контрактом.
- `safe to merge` / `safe to deploy` / `safe to flip` не должны противоречить `repo default`, `expected live default` и поведению без pin.
- Противоречие класса `unsafe repo default + delayed rollout restriction` = plan gap ещё до handoff на Planner; downstream роли не должны разруливать это догадками.

## Plan intake flow (обязателен для каждой итерации)
Если тебе дали план ссылкой или сказали “возьми вот этот plan” — начинай **всегда** так:

0) **Прочитать базовые доки + свою роль.**
   - Всегда: `AGENTS.md` + `docs/roles/<role>.md` (обязательный старт, только нужные ссылки).
   - `README.md` — опционально: один раз на новое окружение/репозиторий или когда нужны команды quickstart (run/test/smoke).
1) **Прочитать план целиком.** Не “по диагонали”: plan может быть частью цепочки (follow-up) и опираться на предыдущие решения/доки.
   - Пройти по ссылкам из plan (BRD/ARCH/API/UI/Schema/Registry, snapshots, code refs).
   - Для Architect intake обновить или создать отдельный `## Как я понял задачу`: 3-7 строк человекочитаемого summary о результате, границах, route/следующем contour и закрытых/ненужных Owner-решениях. Это не `Q&A`, не Evidence и не длинный CENSOR paragraph; для новых планов после `Architect initial draft` отсутствие такого блока = lint error.
   - Постановочные секции пишем по-русски, даже если входной research/packet/кодовые названия на английском. Английские слова оставляем только как literal terms для путей, команд, enum/API/field names и quoted source refs.
2) **Сформировать вопросы** и занести их в plan:
   - указать **свою роль**, **кому вопрос** (Owner/Architect/Planner/Coder/Reviewer),
   - пометить: `blocker: yes/no`, `needs_owner: yes/no`.
3) **Сформировать предложения по улучшению плана** и занести их в plan:
   - указать, **в чьей зоне компетенции** правка (Architect/Planner/Coder/Reviewer/Owner),
   - отметить, блокирует ли это работу.
4) **Сформировать возражения/риски** и занести их в plan:
   - пометить `blocker: yes/no`, и нужно ли звать Owner.
5) **Только после этого** — переходить к собственно работе по plan.

> Каждая итерация обсуждения/доработки plan начинается с этого flow (даже если “кажется, что всё понятно”).

### Intake prompts (optional)
Если нужен быстрый список вопросов, который помогает не забыть contract gaps:
1) Что именно должно измениться в поведении? (роль/пользователь/сценарий)
2) Какие данные затрагиваются? (модели/поля, новые сущности?)
3) SLA/производительность/объёмы? (RPS, размер выгрузок, периодичность)
4) Безопасность/доступы? (роли, публичность, секреты, PII)
5) Интеграции? (внешние API, вебхуки, форматы)
6) Как проверяем? (target-declared automated/runtime/manual checks)
7) Ограничения по времени/релизу? (версия, миграции, фиче‑флаги)
8) UX‑контракт: какие exact target-declared тексты, labels, units и states видит пользователь или consumer?
9) После мутаций: что должно обновиться в затронутом UI или consumer contract и как это доказываем?
10) Инварианты данных: что считаем запрещённым, какой authoritative validator/guard это отвергает и каким check это доказано?
11) Документация: что обновляем синхронно (`docs/api.md`, `docs/schema.md`, `docs/registry.md`, guides) и где это источник истины?

## Кто фиксирует выбор (варианты) и “что уносим в новый plan”
Проблема: в черновиках часто остаются “вариант A/B”, “делать/не делать”, и это гоняется туда‑сюда между ролями.
Правило: **варианты не живут “вечно”** — перед handoff дальше должен остаться один выбранный путь, а остальное оформлено как `Deferred`/follow‑up.

### Кто принимает решение (канонически)
- **Architect**: основной “драйвер решений” по plan: выбирает тех‑вариант(ы), сводит их к одному выбранному, решает “оставляем в этом plan vs выносим в follow‑up”, учитывает связность по технике/контрактам.
- **Owner**: подключается точечно по бизнес‑фичам/приоритетам/интерпретации требований (и по UX — только если Architect пометил `needs_owner=yes` или есть явная неоднозначность “как должно работать”).
- **Planner**: не “выбирает вместо Owner/Architect”, а доводит plan до однозначности: задаёт вопрос, получает ответ и **вкручивает решение** в Scope/Acceptance/DoD/Tests.
- **Coder**: не выбирает; если видит двусмысленность/расползание scope — поднимает вопрос в plan (blocker/needs_owner).
- **Reviewer**: не выбирает; блокирует merge, если staged расходится с plan или если выбор не зафиксирован (см. роль Reviewer).

### Кто обязан “зафиксировать в файле”
Роль, которая **подняла вопрос**, обязана его **закрыть в plan** после ответа (см. Q&A log). Ответ “в чат” не считается фиксацией.
Практически:
- До статуса `Ready for Planner` это ответственность **Architect** (или Owner, если он пишет прямо в plan).
- До статуса `Ready for Coder` это ответственность **Planner**.

### Когда уносить в новый plan
- Если это **новый deliverable** / отдельный пользовательский сценарий / отдельный таб/модалка/интеграция — это **follow‑up plan**.
- Если это “хорошо бы”/полировка/не нужно для MVP — это `Deferred` и (если важно не потерять) follow‑up plan.
- Если это уточнение acceptance/edge case внутри того же deliverable — остаётся в текущем plan.

## Q&A log: как фиксировать вопросы/ответы
В каждом plan ведём “лог диалога” по ролям **с нарастанием времени вниз** (самое новое — внизу).

Формат записи (рекомендация):
- `[YYYY-MM-DD HH:MM] (ROLE → TO, id=Q1, blocker=yes/no, needs_owner=yes/no, status=open) Q: ...`
- `[YYYY-MM-DD HH:MM] (WHO, id=Q1) A: ...`
- `[YYYY-MM-DD HH:MM] (ROLE, id=Q1, status=closed) CLOSED: why/ok`

### Как “закрывать вопросы” (чтобы не писать километры)
На каждом повторном чтении plan роль обязана пройти по open‑вопросам и сделать одно из:
- **Закрыть** вопрос (`status=closed`) отдельной строкой в логе (append‑only).
- **Переформулировать** (если ответ частичный/туманный): закрыть старый как `status=superseded` и открыть новый вопрос `id=Q2` со ссылкой “следует из Q1”.

Закрывает вопрос обычно тот, кто его задавал (роль‑инициатор), после того как считает ответ достаточным.

Ответы “в чат” не считаются закрытием: итог обязателен в plan файле.

## Анти‑двусмысленности (чтобы не было “догадок” на реализации)
Цель: если пункт важен — он должен быть в Scope/Acceptance/DoD. Если не важен — он должен быть явно помечен как Out of scope / Deferred.

- **Никаких скрытых исключений.** “Важно, но не записали” = потом регрессия и спор в ревью.
- **Условия/контракты формулируем как if/then.** Пример: “derived state публикуем только если authoritative carrier валиден”; “fallback запрещён при ambiguous input”.
- **Запреты тоже фиксируем.** Например: “без неявного fallback”; target-specific UI/transport constraints ссылаются на literal selected-target carrier.
- **DoD без дыр.** Если в плане есть DoD‑чекбоксы `[ ]` — они закрываются кодом+тестом, либо официально переносятся (в plan как Deferred).
- **Plan учитывает workflow.** Если сознательно ожидается переписывание истории (`git commit --amend` на уже запушенном коммите) — в Commands/Notes явно указать `git push --force-with-lease` и последствия. По умолчанию лучше избегать force‑push в командном процессе.

## Post-review exact-bundle closeout в dirty repo
Для обычного `dev`-plan при `COMMIT_POLICY=native_existing` это default Architect closeout перед `Done`, а не opt-in “если plan вдруг вспомнил сказать про commit”. Не используй этот контракт как общий режим “почистить git”.

При `COMMIT_POLICY=human_explicit` Architect завершает accepted `Architect arch review` и останавливается: не stage-ит, не записывает provisional `Done` и не коммитит. Человек вызывает существующий `planveyor sibling close` для preview, затем отдельно `planveyor sibling close --commit`; этот helper повторно проверяет current oracle, accepted review и точный набор, выполняет Done/commit и cleanup при failed final gate. Coder/Planner не получают Done writer. Raw Done не заменяет current review/closeout proof. Automatic Architect stage/provisional Done/commit ниже относятся только к `native_existing`; правила exact bundle и отказа при чужом index сохраняются для обеих policies.

- Dirty repo сам по себе не blocker, если final bundle определяется только explicit paths.
- Authoritative implementation/doc input = `code_draft_meta.targets`; к `Ready for Review` этот список должен быть reconciled до exact final file set, а не оставаться seed/advisory sketch.
- Explicit deletions live in `code_draft_meta.deleted_paths` (list of `{path, kind}` entries). Это отдельный deletion carrier: ordinary entries are valid only for paths tracked in `HEAD`; review-only entries (`kind=review_only` or `review_only=true`) must also declare `base_ref` and `deletion_ref`, where `base_ref` contains the path and `deletion_ref` no longer does. Deleted paths become exact bundle members for `--print|--check|--stage|--commit-ready|--closeout-json`, but existing untracked files and ordinary missing/stale live `targets` still fail closed.
- Если package/dir umbrella materialize-ится в конкретные child files, `code_draft_meta.targets` restamp-ится на literal file paths до `--commit-ready`; abstract parent dir не считается commit-ready substitute.
- Final stageable bundle = `code_draft_meta.targets` + `code_draft_meta.deleted_paths` + `PLAN_PATH` + сам code draft + пути из `## Review artifacts` + explicit asset paths, на которые review artifact явно ссылается, + every valid all-history `reviewer_code_risk` support pair declared in the origin plan. Историческая пара добавляется по exact ref/hash, а не directory glob или filename inference.
- Поэтому origin plan остаётся отдельным lifecycle/status/Q&A/Evidence member финального exact bundle, но его bytes не входят в mutable current-review target hash. Context refs, `code_draft_meta.plan` и `deleted_paths` также не превращаются из-за этого в review targets.
- Если helper уже доступен, используй `planveyor_plan_bundle --print|--check|--stage|--commit-ready|--closeout-json <PLAN_PATH>` как inspectable exact-path resolve: он собирает bundle только по explicit артефактам, показывает группировку по git root, печатает exact local-commit skeleton per root и не подменяет contract эвристикой по `git status`.
- Только при `COMMIT_POLICY=native_existing` Owner/Manager не ждут отдельного plan-note “теперь Architect может commit”: для executable dev-plan это default flow после успешного `Architect arch review`. `human_explicit` требует отдельного `sibling close --commit` после preview, не автоматического role commit.
- До первой exact stage/preflight Architect запускает simulated-status lint без изменения файла: `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py plan_lint.py --as-status Done "$PLAN_PATH"`. Red verdict оставляет owning non-Done status, запрещает stage/commit и не создаёт отдельную lint authority; green разрешает первую exact `--stage` и pre-Done `planveyor_plan_closeout_preflight`.
- После green pre-Done preflight Architect записывает provisional `Done` и немедленно, до любого повторного exact `--stage`, final preflight или commit, запускает final ordinary lint: `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py plan_lint.py "$PLAN_PATH"`. Только этот ordinary run проверяет реально записанные terminal bytes и остаётся final lint authority.
- Red final ordinary lint или final exact preflight требует failed terminal transition cleanup: восстановить `Architect arch review`, повторить exact `--stage` с owning non-Done bytes, убедиться, что `Done` отсутствует в worktree и index, и остановиться без commit. Green ordinary lint разрешает exact restage, final preflight и один exact local commit; отдельный post-commit `Done`/второй commit запрещён.
- Если bundle охватывает несколько git roots (например, mirror-файлы в соседнем git root), closeout выполняется отдельно по каждому root, но всё ещё только exact paths и без heuristics.
- Допустимые действия closeout: `print/check explicit bundle`, затем exact-path `git add -- <explicit paths>`, затем `planveyor_plan_bundle --commit-ready <PLAN_PATH>` и только после `exit 0` локальный `git commit` по каждому затронутому root. `git push` в этот flow запрещён и остаётся отдельным Owner step.
- `--commit-ready` reuse-ит тот же explicit bundle resolver, всегда печатает per-root `git -C <root> commit -m "<message>" -- <explicit bundle paths>` skeleton и возвращает `exit 0` только когда `staged_set - explicit_bundle == ∅` по каждому root. Represented deletions count as explicit bundle paths only when they are listed in `code_draft_meta.deleted_paths`.
- `--closeout-json` reuse-ит тот же resolver и даёт machine-readable `closeout_kind` для local materialization state:
  - `commit_ready` = exact bundle staged, локальный commit ещё нужен;
  - `already_materialized` = pending bundle delta уже отсутствует, поэтому `git commit: no changes added to commit` можно трактовать как idempotent local closeout outcome, а не как semantic regression;
  - `staged_empty` = bundle delta живёт только в worktree и exact staging нужно повторить;
  - `staged_mismatch` = в индексе есть unrelated staged paths вне explicit bundle;
  - `needs_rerun` = bundle split/ambiguous (`staged + unstaged` вместе или resolution problem), включая invalid all-history risk-support manifest; поэтому сохраняем current conservative rerun behavior.
- `staged_mismatch` — это restamp blocker: если explicit bundle уже materialize-ился как concrete child files, broad commit по parent directory не использовать, а `code_draft_meta.targets` и related bundle wording сначала привести к literal paths.
- Если после `planveyor_plan_bundle --stage` в индексе уже лежат unrelated staged изменения, `planveyor_plan_bundle --commit-ready` обязан перечислить offending staged paths и вернуть non-zero; plain `git commit` по всему staged set запрещён: коммитим только explicit bundle paths (например, `git commit -m "..." -- <explicit paths>`) или отдельно очищаем чужой staged state вне текущего closeout. Иначе exact bundle превращается в heuristic commit и легко захватывает посторонний diff.
- Если локальный `git commit` не проходит или печатает `no changes added to commit`, сначала вызови `planveyor_plan_bundle --closeout-json <PLAN_PATH>` и branch only by `closeout_kind`: `already_materialized` не reopen-ит semantic closeout, а `staged_empty` / `staged_mismatch` / `needs_rerun` остаются local closeout blockers.
- Если `--check`, `--stage`, `--commit-ready`, `--closeout-json` или `git commit` не проходит, если bundle неполный/противоречивый или exact closeout не materialize'ится честно, это stop-the-line: `Done` не ставим, destructive recovery не делаем, проблему возвращаем на owning role. Foreign-only ordinary docs delta остаётся diagnostic-only и не может стать `final_docs_diff_paths`, staging expectations или final commit handoff; no-cycle exact-owned docs delta остаётся `blocked`/`no_op` до finalized capture proof и не получает synthetic expectations; protected reclassification не меняется.
- Запрещено именно broad/heuristic staging и destructive recovery: `git add -A`, broad globbing по теме/директории, выбор файлов “по смыслу”, `git restore`, `git checkout --`, `git reset`, `git clean`, массовый unstage/discard unrelated изменений. Exact-path `git add -- <explicit paths>` для bundle, наоборот, обязателен.
- Manager может только маршрутизировать explicit helper или handoff на Architect; сам file set он не придумывает и не вычисляет по `git status`.

### Как фиксировать варианты (A/B) без “гоняния туда‑сюда”
Паттерн:
1) Пока выбор не сделан — это **Q&A вопрос** (`status=open`, с `needs_owner=yes/no`).
2) Как только выбор сделан — **переписать исходный пункт в финальную формулировку** (без “либо/или”).
3) Если альтернативу важно не потерять — оставить её одной строкой в `## Follow-ups` (deferred) или в Objections log (“rejected alternative: …”).
4) Добавить 1–2 acceptance пункта, которые делают решение проверяемым (пример: точный текст заголовка и отсутствие его дубля в основном содержимом).

Мини‑шаблон для “Decisions (final)”:
- `### <Тема>`
  - ❌ Вариант 1: … (почему нет)
  - ❌ Вариант 2: … (почему нет)
  - ✅ Final: … (почему да)
  - Trade-offs: … (что теряем/выигрываем)

## Когда создавать новый plan (а не дописывать старый)
Создаём новый plan, если:
- меняется **Goal/Deliverable** или появляется новый “кусок” работ, который можно делать независимо;
- scope “расползается” и план превращается в мешанину из 2–3 задач;
- текущий plan уже помечен **Done**, но появились follow-ups/улучшения/UX-полировка;
- по итогам `Architect arch review` (или другого “stop-the-line”) выяснилось, что текущий plan **нужно переосмыслить/детализировать заново** так, что прежние DoD/evidence/чек‑листы становятся невалидны (в этом случае Architect создаёт новый plan и помечает старый как `Superseded`);
- появляются новые домены/таб/модалки/интеграции, которые не были частью исходного scope.

Оставляем правки в текущем plan, если:
- это уточнения acceptance/edge cases **в рамках того же deliverable**;
- это ответы на вопросы для текущей реализации/ревью;
- это небольшие корректировки без смены цели.

Жёсткое правило:
- Plan со статусом **Done** не “оживляем”. Любые продолжения — отдельный follow-up plan.
- Plan со статусом **Superseded** не “оживляем”. Продолжение работ — только в новом plan, на который он ссылается.

Рекомендуемый паттерн:
- Основной: `YYMMDD_HHMM_topic.md`
- Follow-up: `YYMMDD_HHMM_topic_followup.md` (или `_part2`, если follow-upов несколько)
- В старом plan в конце: ссылка на follow-up plan + кратко “почему вынесли”.

## Follow-up aggregators (аудит → список пунктов)
Иногда после аудита/ревью получается длинный список мелких follow-ups. Для этого допустим **aggregator plan** — файл в `docs/plans/`, который хранит список пунктов и ссылки на отдельные `dev` планы.

Правила (чтобы не путаться и не “ставить Done без изменений”):
- Aggregator = **backlog**, а не “контракт на реализацию”: его обычно **не** двигаем по статусам `Ready for Coder/Review/...`.
- Для гигиены можно держать aggregator в `**Status:** Architect draft` и просто обновлять список пунктов.
- Каждый пункт должен иметь явное состояние: `open | planned | in progress | done | deferred` + ссылка на артефакт (plan/review/commit).
- “Откусить” пункт = создать отдельный `dev` plan по `docs/plans/_template.md`, а в агрегаторе рядом с пунктом добавить ссылку и пометку `planned` (не `done`).
- Закрывать пункт в агрегаторе (`done`) — только когда follow-up реально завершён (обычно после merge) и есть ссылка на результат.

Практическая мелочь, которая экономит время: в `## Q&A log` делай вопросы **самодостаточными** (контекст + короткий пример), потому что ответы часто приходят спустя дни и без контекста Owner/Planner быстро забывает “про что вообще было”.

## Когда разбивать большой plan на части (а не держать “простыню”)
Сигналы:
- plan > **1500 строк** или 10+ проблем/блоков изменений;
- план мешает читать/закрывать вопросы и в нём тяжело найти “что сделать”.

Как разбивать (варианты):
- по домену/подсистеме,
- по слою (данные → логика → интерфейсы),
- по приоритету (P0 must‑have → P1 nice‑to‑have).

Правило разбиения:
- основной plan содержит Context + Decisions (final) + ссылки на sub‑plans;
- sub‑plans имеют свой Scope/DoD/Tests и проверяются независимо;
- sub‑plans не дублируют весь контекст, а “наследуют” ссылкой на основной.

## Plan lint (gate)
`scripts/plan_lint.py` — детерминированный gate “гигиены” plan.

Фактическое правило процесса:
- для **актуальных** plan’ов (`dev` и `review-only`) в execution/review flow (handoff’ы, ревью, вердикт `Done`) — **обязателен**;
- для исторических/legacy планов — best-effort (обычно не гоняем `--all` без причины).

Что проверяет (high level):
- ровно **одна** строка `**Status:**` (нет missing/duplicate и нет шаблонного значения с `|`),
- `**Status:**` — зарезервировано под workflow routing; не используем это слово для HTTP‑кодов/валидаторов (пиши `HTTP status` / `HTTP 422` / `status code` и т.п.),
- вопросы не “висят вечными” (`status=open` должен быть закрыт или superseded),
- plan не помечен `Done` при открытых вопросах.

Команды:
- `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_plan_lint docs/plans/YYMMDD_HHMM_topic.md`
- `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_plan_lint --all` (может быть шумно/падать на legacy plan’ах — используем в основном для текущих plan’ов).

## Generated readback freshness (gate)
Коммитимые derived surfaces остаются readback-only: raw truth живёт в `docs/followups/*.md` и `docs/process_improvements/*__process_improvements_backlog.md`. Обычный `planveyor_doc_lint` дополнительно гоняет family-scoped freshness checks:
- `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py followups_index_rebuild.py --project-root . --check`
- `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py process_improvements_collect.py --project-root . --check --json`

Если check красный, не правь generated block руками: перегенерируй exact helper command из `DO NOT EDIT` banner и затем повтори gate.

## Pre-delete checklist (когда чистим plans/reviews)
Перед тем как Owner удаляет закрытые `docs/plans/*` и обработанные `docs/code_reviews/*`/`docs/doc_reviews/*`:
1) Убедиться, что знания уехали в канон (BRD/ARCH/Schema/API/UI/Registry/Guides) или в `docs/reviews/*`, а follow-ups зафиксированы в `docs/followups/*`.
2) Запустить ссылочный линт по “живым” докам (обычно без `docs/plans/`, `docs/code_reviews/`, `docs/doc_reviews/`, `docs/snapshots/`):
   - `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_doc_lint` (или literal explicit bundle из `docs/playbooks/doc_lint.md`; это ordinary gate, не closeout gate)
3) Убедиться, что в канонических доках нет inline code ссылок на файлы, которые удаляем.

## Strict N-A parent no-draft contract

`strict N-A parent` is an active/parked `decomposition_wave` parent with a
valid N-A MAD, literal `Code draft(s): N/A (why=...)`, no live parent-draft
ref, and no same-stem file. Its only admission is oracle-derived
`not_required`; this never waives a required/ordinary plan draft.

- Candidate mode is inspection-only; it never grants stage, queue, or terminal authority.
- Use files-first materialization: create canonical child plans and same-stem child drafts before linkage.
- The derived parent planning bundle has one parent review and literal review assets, with no recursive child-target import.
- Preserve active-to-parked child-path continuity and no fabricated parent draft.
- Для этого admitted parent `BUNDLE=current` — producer-selected `review_target_snapshot.v3`: `source.child_plans` содержит полный oracle canonical graph, а `source.child_code_drafts` — его упорядоченное same-stem сопоставление. Hash basis v3 содержит ровно нормализованные carrier files `N+N→2N`; parent, Evidence, live review/support и child implementation/deletion targets исключены.
- `plan_meta.next_plans[]` остаётся только ограниченным routing shortcut. Он не поставляет и не сокращает v3 hash-basis graph, а v3 proof не означает queue activation, `run Q`, staging или child implementation authority.

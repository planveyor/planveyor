[ALWAYS START]
Ты работаешь как роль Architect в выбранном проекте и активном repo-profile.

Цель этого запуска: сделать post-merge “plan harvest” по диапазону `BASE..HEAD`:
- вытащить follow-ups / canon updates / key decisions из plan’ов и review-артефактов,
- учесть итоги ревью (не плодить дубликаты follow-ups),
- если range включал rerun после blocker fix: явно зафиксировать `Rerun mode`, `Baseline artifact` и границу между rerun closure и full-wave residual-debt extraction,
- заполнить harvest report `OUT` по template contract `profile override -> shared default` (shared default: `docs/reviews/_template_plan_harvest.md`) и довести его до `**Status:** ✅ Done`, если артефакт готов,
- создать follow-ups backlog `FOLLOWUPS_OUT` в `docs/followups/` (шаблон: `docs/followups/_template_followups_backlog.md`) и добавить его в `docs/followups/index.md`,
- выполнить followups triage/import для `FOLLOWUPS_OUT` через `planveyor_followups_triage --file "$FOLLOWUPS_OUT"` (dry-run/apply/idempotency), если в repo-profile существует `docs/followups/index.md`,
- пересобрать auto-summary открытых follow-up’ов в `docs/followups/index.md`, не ломая curated manual notes/table,
- при необходимости создать follow-up dev-plan(ы) в `docs/plans/`,
- если durable `Key decisions / constraints` переживают cleanup временных артефактов — materialize-ить ADR draft(s) в `docs/adr/*.md`,
- обновить канонику (по месту: declared canon проекта — например `docs/adr/*`, `docs/api.md`, `docs/schema.md`, guides и runtime handbooks в owning repo, если именно они владеют workflow) так, чтобы стало не страшно удалять `docs/plans/*`.
- если harvest/canon sweep меняет shared process canon carriers, явно зафиксировать, что следующий tracker step `step:packetization_gate` должен materialize report или source-only reason; без report не закрывать shared-canon closeout.
- если range затрагивал Golden Path-worthy знание, явно классифицировать lane: `product_runtime`, `tooling_process`, `target_adoption` или `N/A (why)`. Для source-owned `tooling_process` используй `"$PLANVEYOR_RUNTIME_ROOT/docs/guides/golden_paths.md"`; для остальных lane — declared target-local carrier.
- для выбранной lane зафиксировать `active carrier` и outcome: `updated`, `no changes needed (why)`, `follow-up created` или `deferred (why)`. Runtime interactive-form surface допустима только как selected-project `product_runtime` carrier, явно объявленный profile/plan; process/adoption workflows используют их declared `tooling_process` / `target_adoption` carriers.

Входные (уже переданы в окружении этого запуска):
- `BASE=<sha>`
- `HEAD=<sha>`
- `RANGE=<sha..sha>` (обычно `BASE..HEAD`)
- `OUT=<path>` (в `docs/reviews/*`; если файла нет — создай через тот же contract: `profiles/<repo_profile>/_template_plan_harvest.md` при наличии, иначе shared default `docs/reviews/_template_plan_harvest.md`)
- `FOLLOWUPS_OUT=<path>` (в `docs/followups/*`; если файла нет — создай из shared default `docs/followups/_template_followups_backlog.md`; отдельный profile override для backlog в этом slice не требуется)
- `PYBIN=...` (опциональный override для python interpreter; sibling запускает doc lint через внешний facade)

Жёстко:
- Это НЕ работа по конкретному dev-plan. Не меняй статусы/содержимое существующих `docs/plans/*`.
  - Разрешено создавать **НОВЫЕ** follow-up dev-plan’ы в `docs/plans/`.
- `OUT`, `FOLLOWUPS_OUT`, новые follow-up планы и чат пиши на русском; код/идентификаторы/пути/команды — на английском; UI-строки — на языке, объявленном проектом. Англоязычная narrative-проза в `OUT` / `FOLLOWUPS_OUT` = invalid output; перед `✅ Done` перепиши её на русский.
- Продуктовый код/шаблоны/миграции не трогаем.
- Разрешено менять только `docs/**` (включая `docs/reviews/*`, `docs/followups/*`, `docs/snapshots/*`).
- Не “додумывай”: если не уверен — помечай `UNCONFIRMED`.
- Для merge-tracker plain existence `OUT` недостаточно: успешный исход этого шага = `OUT` существует и в header стоит `**Status:** ✅ Done`.
- Snapshot'ы можно открывать только как historical breadcrumbs. Не используй snapshot как cited source / effective spec / pointer в `OUT`, `FOLLOWUPS_OUT` или active canon.

Что сделать:
1) Открой `docs/playbooks/post_merge_plan_harvest.md` и следуй ему.
2) Если `OUT` отсутствует — создай его через тот же deterministic contract: `profile override -> shared default`.
3) Заполни `OUT` фактами:
   - список plan’ов/ревью из диапазона (filenames only),
   - что уже “handled” (по итогам ревью/фиксов),
   - что осталось и превращаем в follow-up (или помечаем `needs_owner`),
   - если source plan literal-но вынес item из active scope (`removed from active scope`, `intentionally removed`, `если по-прежнему нужно`, `отдельный follow-up`), отдельно зафиксируй судьбу этого de-scoped debt: `promoted | backlog | already tracked elsewhere | explicit owner rejection`; формулировка `out of scope` сама по себе не считается closure,
   - `already tracked elsewhere` разрешён только когда у item уже есть durable pointer: existing backlog-row в `docs/followups/*`, promoted `docs/plans/*.md`, literal canon closure или explicit owner rejection. Ссылка только на `*_followups_memory_*.md` / memory dump без promoted plan, backlog-row или closure note = invalid handled-state,
   - какие key decisions/constraints уехали (или должны уехать) в канон (по месту),
   - какие durable decisions стоит поднять в `docs/adr/*` и почему это ADR, а не tactical note,
   - какие канонические доки обновлены/нужно обновить (коротко + pointers).
   - если в range был rerun после blocker fix: явно запиши `Rerun mode`, `Baseline artifact`, что именно закрыто rerun и что harvest всё ещё проверял как full-wave residual debt,
   - если plan попадает в downstream role-quality audit: запиши literal `Candidate source` + `Why flagged` по exact review ref / plan evidence; если strong signal нет — оставь summary lane `not audited` и не выдумывай deep matrix prose,
   - process-improvement governance: открой `docs/process_improvements/promotion_surface.md`; для каждой mature row запиши ровно одну строку в `Process-improvement promotion decisions` с полями `source_ref` (или exact unique plan slug), `entry_id`, `decision`, `reason`, `execution_kind`, `execution_ref`, `owner_or_next_step`,
   - если ordinary `docs/followups/*` result = `NO FOLLOWUPS`, но process-improvements surface содержит raw `open|triaged|promoted` rows, добавь в `Process-improvement promotion decisions` compact readback `process_improvements_open_summary: source=docs/process_improvements/promotion_surface.md; lane=separate; ordinary_followups=NO FOLLOWUPS; open=<n>; triaged=<n>; promoted=<n>; null_execution=<n>; owner_or_next_step=<...>`,
   - row resolution должен быть helper/lint-readable: explicit `source_ref` -> `entry_id` -> exact unique plan slug; ambiguous/missing match = `unresolved_process_improvement_row`,
   - допустимые terminal values: `promoted`, `deferred`, `rejected`, `handled`; `promoted` требует, чтобы raw row уже имел `status=promoted` и материализованный `execution_kind` + `execution_ref`, где `execution_kind` ∈ `plan | helper | canon_doc | rollout_packet | umbrella_wave | external_ref`; `handled` допустим только для raw `status=handled`; `deferred` требует `reason` + owner/next-step или revisit condition, а ordinary `docs/followups/*` bridge должен быть backlinked в raw `delivery_refs` и не может оставлять naked raw `open` row без execution carrier; `rejected` требует `reason`,
   - `triaged` row с terminal `execution_kind=plan` / `execution_ref` и null `handled_ref` / `promoted_at` / `handled_at` не называй handled/promoted в prose: сначала зафиксируй reconcile readback (`candidate_handled` / `needs_reconcile`) или оставь bounded deferred decision,
   - mature row без terminal decision = blocker для `✅ Done`; если execution carrier отсутствует, это `deferred` с reason/owner или `rejected` с reason, а не silent `promoted`,
   - terminal prose в report не является source of truth: raw `docs/process_improvements/*` row state / derived surfaces или helper receipt должны совпасть с decision; already-handled row нельзя снова назвать `promoted`,
   - не запускай helper, не создавай dev-plan/canon edit/rollout packet implicit из этого governance step; если нужен execution carrier, зафиксируй explicit follow-up/promoted plan по обычному harvest контракту,
   - не используй exact heading `Process improvements` для terminal harvest decisions: этот token зарезервирован для raw memory-finalize suggestions; harvest terminal decisions используют dedicated surface `Process-improvement promotion decisions`,
   - если в range были UI-изменения, process workflows, rollout/import/ack flow или повторяемые review findings по контрактам/паттернам: добавь lane-specific Golden Path receipt в `OUT`:
     - `lane`: `product_runtime | tooling_process | target_adoption | N/A (why)`;
     - `active carrier`: доставляемый target-local path либо source-engine `"$PLANVEYOR_RUNTIME_ROOT/docs/guides/golden_paths.md#<anchor>"`, или `N/A (why)`;
     - `outcome`: `updated | no changes needed (why) | follow-up created | deferred (why)`;
     - examples: interactive runtime/UI surface = `product_runtime`; post-merge/memory-finalize/process-improvement loops = `tooling_process`; rollout packet inbox/adoption-plan/harvest/ack = `target_adoption`.
   - если в `canon updates` есть shared process carriers, добавь packetization handoff line: `packetization_gate=<report required after canon_sweep>` или `source_only=<reason>`; не подменяй это broad canon prose.
   - current harvest `OUT` должен включать helper-backed receipt summaries, not prose-only `N/A`: `Follow-up harvest triage/import receipt`, `Process-improvement promotion decisions`, `Docs retrieval metrics receipt`, `Golden Path lane receipt`, `ADR candidates / durable decisions`, and `Canon/follow-up summary`; если shared canon applies, include `step:packetization_gate`.
   - в current `review.v1` `## Follow-up harvest triage/import receipt` обязательно запиши ровно по одному parseable literal: `harvest_file_followups_result` (`created/imported` или `NO FOLLOWUPS`) и `harvest_file_followups_count` (non-negative integer); `created/imported` требует positive exact count, а `NO FOLLOWUPS` — count `0` и одну разрешённую same-line reason (`handled in follow-up`, `already tracked elsewhere`, `canon sync closed it`, `no remaining actionable debt after full-wave harvest`).
   - idempotency receipt в current `review.v1` обязан содержать ровно по одному parseable non-negative integer для `append_new`, `possible_duplicate`, `route_fallback` и `unparsed_bullets`; missing, duplicate или malformed counter — blocker до closure semantics. Если любой из них non-zero, укажи durable `manual_decision_ref` или `already_tracked_ref` под `docs/followups/...` либо `docs/plans/...`; не подменяй file-lane inferred `UNCONFIRMED/1` или downstream summary. Любой explicit `review.v1` current независимо от возраста; legacy-compatible остаётся только versionless non-template historical host.
   - для `tooling_process` Golden Path anchors используй existing engine refs: `"$PLANVEYOR_RUNTIME_ROOT/docs/guides/golden_paths.md#post-merge-plan-harvest"`, `"$PLANVEYOR_RUNTIME_ROOT/docs/guides/golden_paths.md#post-merge-audit"`, `"$PLANVEYOR_RUNTIME_ROOT/docs/guides/golden_paths.md#process-improvement-promotion"`, `"$PLANVEYOR_RUNTIME_ROOT/docs/guides/golden_paths.md#source-rollout-packet-lifecycle"`.
4) Создай/обнови follow-ups backlog `FOLLOWUPS_OUT` (шаблон: `docs/followups/_template_followups_backlog.md`):
   - занеси туда только “actionable” follow-ups (без дублей),
   - любой item, который source plan явно вынес из active scope, но не отменил owner-решением, обязан либо попасть сюда, либо быть promoted в отдельный dev-plan, либо быть помечен `handled` с pointer'ом на already-tracked durable backlog/dev-plan/closure note или explicit owner rejection,
   - для пунктов с готовым dev-plan: `status=promoted`, `plan=docs/plans/...`,
   - для пунктов `needs_owner`: `status=UNCONFIRMED`, `to=Owner`,
   - если follow-ups **нет** — напиши в `FOLLOWUPS_OUT` `NO FOLLOWUPS` только с явной причиной (`handled in follow-up`, `already tracked elsewhere`, `canon sync closed it`, `no remaining actionable debt after full-wave harvest`) и оставь файл как артефакт диапазона; unmatched de-scoped item делает `NO FOLLOWUPS` invalid, и memory dump без promoted plan/backlog row/closure note не подходит как `already tracked elsewhere`,
   - `NO FOLLOWUPS` закрывает только ordinary followups lane; separate process-improvement rows не дублируй в `docs/followups/*`, а показывай через `process_improvements_open_summary`,
   - добавь ссылку на `FOLLOWUPS_OUT` в `OUT` (`## Follow-ups backlog (created)`),
   - добавь строку в `docs/followups/index.md` (File/Topic/Notes; если follow-ups нет — пометь это в Notes).
   - если `docs/followups/index.md` существует, сразу выполни import/apply cycle для freshly-created `FOLLOWUPS_OUT`:
     - `planveyor_followups_triage --file "$FOLLOWUPS_OUT" --dry-run`
     - `planveyor_followups_triage --file "$FOLLOWUPS_OUT" --apply`
     - `planveyor_followups_triage --file "$FOLLOWUPS_OUT" --apply` (idempotency)
   - `Imported into: N/A (...)` не считается реальным импортом; при open rows это blocker для `✅ Done`, если repo-profile поддерживает `docs/followups/index.md`.
   - после этого пересобери auto-summary через `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py followups_index_rebuild.py`
5) Если `Key decisions / constraints` явно содержат durable архитектурное решение:
   - создай ADR draft в `docs/adr/NNN-topic.md` по `docs/adr/_template.md`,
   - default status = `proposed`,
   - держи template contract literal-ным: frontmatter `status/date/decision-makers/source-range/source-plan/code-anchor` плюс секции `Canonical refs`, `Confirmation`, `Revisit signals`, `Superseded by / Supersedes`,
   - если supersession уже известен, фиксируй его только через `## Superseded by / Supersedes`: допустимы repo/file path до ADR markdown или bare ADR id, который резолвится в sibling `docs/adr/<id>.md`; live `status` token остаётся `superseded`,
   - tactical implementation choice не промоуть в ADR.
6) Если видишь “простыни” в каноне или в артефактах — не прячь durable facts за snapshot-ссылкой: подними устойчивые выводы прямо в `OUT`, `FOLLOWUPS_OUT`, канон или follow-up plan. Snapshot допустим только как отдельный history/handover артефакт и не должен цитироваться из `OUT` / `FOLLOWUPS_OUT` / active canon.
7) Финальный scrub durable artifacts:
   - `OUT`, `FOLLOWUPS_OUT` и другие долгоживущие артефакты не должны содержать ложный transient repo/session-state (`dirty`, `untracked`, “локально создано ...`), если это уже долгоживущий артефакт;
   - если repo-state важен для восстановления, либо зафиксируй exact live fact, либо явно отправь к live `git status -sb` / `git log -1 --oneline`;
   - не оставляй `UNCONFIRMED` там, где факт можно добрать локально за одну команду.
   - если harvest обновляет active canon/registry, не используй snapshot'ы как pointer/cited source; range snapshot допустим только как history/handover background вне нормативного контура.
8) Если `OUT` заполнен и harvest завершён — переведи header `**Status:**` в `✅ Done`.
9) Если сознательно оставляешь `Draft` (например, неясен статус follow-up'ов, не подтверждён канон, не собран backlog) — явно пометь пробелы как `UNCONFIRMED` и в чате верни blocker: такой шаг нельзя тикать.
10) (Опционально) Gate:
   - `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_doc_lint` — если в ходе harvest ты менял канонику и хочешь сразу проверить.
   - `git diff --check -- docs`
     - это показывает accidental trailing whitespace, CRLF, merge markers и лишние пустые строки в EOF в **текущем doc-diff**;
     - если новые hits идут только от Markdown hard-break formatting, перепиши changed block без raw trailing spaces перед `✅ Done`.

Дополнительный guard для этого slice:
- Не превращай `plan_harvest` в роль-аудит сам по себе: harvest only selects candidates and records `not audited`, а deep role-quality verdicts materialize-ятся уже в `post_merge_audit`.
- Для terminal `plan.v2` не materialize-ь `plan_meta.followups_out` и не правь source plan. Deferred truth — exact `followups.v2` `(source_ref,item_id)` row; `open + exact current-cycle proof` допускает `external_clean`. Four-role declarations are read-only in `Architect -> Coder -> Planner -> Reviewer` order, and only `scripts/followups_apply.py` can mutate the frozen union. V1 remains read-compatible; V2 never queue-imports/backfills history.

Выход (в чат):
- `OUT=<path>`
- `FOLLOWUPS_OUT=<path>`
- `STATUS=<Draft|✅ Done>`
- 5–15 bullets “что вытащил/что создал/что осталось”.

[/ALWAYS START]

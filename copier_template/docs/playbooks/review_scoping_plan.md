# Playbook: Reviewer plan — scoping (review-only plan)

Это **не роль**. Это короткий **гайд по созданию review-only plan** (контракт на ревью) под роль Reviewer.

Зачем:
- зафиксировать **target** (что ревьюим) + **scope/out of scope**,
- задать DoD/commands/evidence, чтобы ревью было воспроизводимым,
- дать место для Q&A/plan gaps и ссылки на review‑артефакт,
- упростить post‑merge чистку docs (планы/ревью удаляет Owner).

Когда использовать:
- Owner просит “сделай классическое ревью” (commit/range) и **нет существующего plan** по задаче.

## Как создать review-only plan
1) Создай новый файл в `docs/plans/` с именем `YYMMDD_HHMM_reviewer_<topic>.md`.

2) Возьми за основу **стандартный** шаблон plan: `docs/plans/_template.md`.
   - Это важно: в нём уже есть канонические чек‑листы/gates, `Q&A log` и `Review artifacts`.

3) Минимально заполни в plan:
   - Заголовок:
     - `# Plan: Reviewer — <topic> (review-only)`
   - Header:
     - `**Stage:**` / `**Priority:**`
     - `**Plan type:** review-only`
     - `**Status:** Reviewer intake`
   - `Context links`:
     - Role: `docs/roles/reviewer.md`
     - Spec/canon (если есть): объявленные product architecture/API/schema/registry
       links; не угадывай stack-specific handbook по имени задачи
     - (опционально) prior review pointers; snapshot'ы можно открыть как background, но не использовать как `Context links` / source of truth
   - `## Problem`:
     - что за ревью и зачем (например: “post-merge sanity review после конфликтов”).
     - явно: это **review-only plan** (без кодовых доработок в рамках этого plan).
   - `## Scope` / `## Out of scope`:
     - явно: что проверяем/что не проверяем (например: “docs/** исключаем”).
     - в `Out of scope`: любые правки кода/шаблонов/миграций (если по итогам нужны фиксы — отдельный dev-plan).
   - `## Changes (by area)`:
     - добавь строку `- Review target: <current HEAD | COMMIT=<sha|current|staged> | RANGE=BASE..HEAD | BUNDLE=<current|staged>>` (как минимум).
     - если нужен именно whole-index snapshot текущей поставки, пиши это явно как `COMMIT=staged`; если нужен bounded exact-plan review в dirty repo, пиши `BUNDLE=staged` или `BUNDLE=current`, чтобы Reviewer не гадал и не требовал лишнюю очистку индекса.
     - если это rerun после blocker fix: добавь строки
       - `- Rerun mode: incremental | full`
       - `- Baseline artifact: <prior review/plan filename> | N/A`
       - `- Rerun scope: <что перепроверяем сейчас>`
   - `## Acceptance criteria / DoD`:
     - [ ] Review‑report создан и содержит S1 Blocker / S2 Risk / S3 Nit / Follow-ups + `file:line`
     - [ ] Команды/тесты из `## Commands` (и/или `## Tests`) выполнены или явно помечены как “не удалось прогнать” с причиной
     - [ ] Для UI‑изменений заполнен `## Visual Acceptance` (Modes to test/Endpoint/port) и в отчёте есть visual evidence (скриншоты в `docs/code_reviews/assets/<REVIEW_BASENAME>/` + ссылки в review‑файле)
     - [ ] Для merge-range с runtime UI есть post-merge visual sanity на merged
       code по объявленным profile scenarios (не только “посмотрели diff”)
     - [ ] Для rerun после blocker fix review‑report явно фиксирует `Rerun mode`; для `incremental` дополнительно заполнены `Baseline artifact`, `Trusted unaffected surfaces` и `Reused evidence`
   - `## Commands`:
     - команды, которые реально будут прогнаны (copy‑paste runnable; с явным интерпретатором/окружением).

4) Если plan создаётся через `planveyor_review_range_init()`:
   - generated scaffold уже должен materialize-ить `## Problem`, `## Solution (high level)`, `## Scope`, `## Tests`, `## Commands` и concrete `## Review artifacts`, а не оставлять Reviewer первый pass на ручной cleanup почти template-only plan;
   - review artifact path должен branch-иться truthfully и single-source: docs-only generated bundle → `docs/doc_reviews/{plan_stem}.md`, любой final generated bundle с non-doc carrier → `docs/code_reviews/{plan_stem}.md`; generated code draft обязан materialize-ить тот же literal path;
   - generated code draft разделяет live и deletion carriers: текущие A/M/R/C/Rename paths идут в `code_draft_meta.targets`, tracked deletions из range идут в `code_draft_meta.deleted_paths`, при этом review-host classification всё ещё считается по full changed-path set;
   - generated `## Documentation impact / provenance` выводится из exact filtered target metadata / `code_draft_meta.targets`: process/doc targets (`docs/plans/**`, `docs/playbooks/**`, `docs/tools/**` и т.п.) перечисляются в `Synchronous doc/registry targets`, а scripts/tooling-only range без doc targets получает explicit `N/A (why=...)`;
   - для range-deletion scaffold `planveyor_plan_bundle --check` валидирует deletion carrier against `HEAD` для обычных working-tree deletions и against `Review target: RANGE=<BASE>..` для review-only ranges, чтобы удалённые в HEAD файлы не превращались обратно в fake live targets;
   - repeated invocation for the same literal compatibility tuple (`BASE`, `HEAD`, `EXCLUDE_DOCS`, resolved repo `profile_id`, derived review-host family, explicit rerun carrier tuple) default reuse-ит уже существующий scaffold path; новый side-by-side artifact допускается только через explicit `planveyor_review_range_init --force-new ...`;
   - same-path default reuse keeps `.planveyor.planpath` pointed at the reused scaffold, but `.planveyor.planpath.log` must not grow by an exact consecutive same-path duplicate on that reuse path;
   - если current pass уже является rerun после blocker-fix, caller передаёт explicit env carrier `PLANVEYOR_REVIEW_RERUN_MODE`, `PLANVEYOR_REVIEW_BASELINE_ARTIFACT` и optional `PLANVEYOR_REVIEW_PRIOR_ARTIFACTS`; scaffold обязан materialize-ить те же literal lineage fields в generated plan (`Prior review / rerun artifacts`, `Rerun mode`, `Baseline artifact`) и generated code draft (`## Current-flow rerun lineage`) без hidden git-history inference;
   - полное отсутствие carrier сохраняет truthful `N/A (first pass)`; partial/malformed carrier = fail-fast до записи mixed scaffold, а не silent downgrade;
   - visual/runtime lane должен быть truth-based:
     - Selected consumer declares required modes, command, endpoint/port and any authentication in its accepted visual contract; shared scaffold does not infer any of them;
     - для non-UI/docs/backend range и для profile-ambiguous/native lanes scaffold обязан ставить explicit `N/A (why)` или profile-local follow-up note, а не generic web fallback.
     - generated plan и code draft обязаны materialize-ить ровно один literal `## Review visual lane contract`, полученный одним helper `scripts/review_visual_lane_contract.py`: bounded inline `review_visual_lane_contract.v1` только при `<=120` content lines и `<=16384` UTF-8 bytes, иначе одинаковый derived `review_visual_lane_contract_ref.v1`, который безопасно dereference-ит единственный full `review_visual_lane_contract.v2` под matching review-assets root; ручная повторная реконструкция, latest/mtime/glob и вторая authority не допускаются;
     - `available` contract содержит exact mechanical comparator и отдельные per-mode human index commands; `missing|malformed|ambiguous` для runtime UI остаются fail-closed technical gap с owner `Architect`, а не превращаются в `N/A`;
     - comparator output и human screenshots пишутся в current review basename: `.tmp/**`, historical review assets и baseline-update команды остаются diagnostics/context only.

5) Дальше работа идёт по роли Reviewer: `docs/roles/reviewer.md`.

## Чем заканчивается review-only plan
- Если Architect принимает ревью для текущего flow → текущий review-only plan получает `**Status:** Done`.
- Если при этом есть deferable/non-blocking follow-up'ы, их можно завести отдельно, но статус review-only plan всё равно остаётся `**Status:** Done`.
- Если Architect считает, что нужен blocking follow-up до продолжения flow → текущий review-only plan получает `**Status:** Superseded`, а дальше работа идёт уже по follow-up plan со стартовым `**Status:** Architect initial draft`.
- Для post-merge / merge-tracker flow stop-the-line включается только в blocking-ветке: пока такой follow-up не реализован, не смержен и range review не прогнан заново, исходный merge flow дальше не идёт.

## Практическая пометка (чтобы не ловить ложный visual blocker)
- Для review-only диапазона, где changed paths и объявленный harness не указывают
  на runtime UI, не заполняй `Modes to test` “для галочки”.
- Если в plan всё же заполнены `Modes to test`, это включает visual gate: Architect будет требовать валидный `## Visual evidence` (по mode + файлы).
- Для truly non-UI review укажи в review-артефакте `## Visual evidence` как `N/A` с явным “почему” (например: “no runtime UI changes in range”).
- Если scaffold materialize-ит `## Visual Acceptance`, но это review-only range,
  profile-specific implementation checklist должен явно сказать
  `N/A (why=review-only range scaffold; implementation-specific checklist remains in affected dev plans)`
  или эквивалентную bounded формулировку, а не оставлять Reviewer додумывать
  implementation checklist.

## Практическая пометка для rerun
- `incremental` = closure blocker scope, а не повторный full-wave review.
- Если нельзя внятно назвать baseline artifact или объяснить, почему unaffected surfaces trusted, выбирай `full`, а не оставляй rerun mode неявным.
- Для shared scaffold current-flow rerun lineage приходит только через explicit env carrier; prior artifacts/history можно читать как background, но не как скрытый init input.

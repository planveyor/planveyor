---
name: planveyor-plan-draft
description: "Draft a Planveyor plan («заведи новый план драфт», «заведи план адаптации под стек», «draft a Planveyor plan»). Use when Codex needs to create or revise Planveyor-style repo artifacts: `docs/plans/*.md`, optional linked `docs/code_drafts/*__code_draft.md`, Architect initial drafts, Planner-ready plan scaffolds, or linted plan/code-draft skeletons."
---

# Planveyor Plan Draft

Создавайте Planveyor plans как repo-backed contracts, а не loose prose. Template, role prompt и current status определяют shape; skill помогает materialize его повторяемо и с проверяемым handoff.

## Project и sources of truth

Работайте с literal target project и выбранным trusted facade. Сначала используйте явно заданный непустой `PLANVEYOR_RUNTIME_ROOT`: executable находится в его `bin/planveyor`. Если переменная не задана, найдите public `planveyor` в trusted launch PATH через `command -v planveyor`. Принимайте только physical regular executable, не alias, shell function или symlink; существующий facade проверяет Git/runtime pin. Не ищите checkout по диску и не переходите на другой runtime при ошибке. Если ни один способ не доступен, спросите Owner только о trusted checkout; не требуйте повторного ручного пути, когда public executable уже доступен.

В примерах ниже `PLANVEYOR_ENTRY` — определённый агентом literal путь к этому executable, а не параметр, который Owner должен подставлять. Передайте этот же путь в каждом command; не изменяйте global shell config, Codex home или окружение установки.

```sh
"$PLANVEYOR_ENTRY" --project "$PWD" planveyor_help
```

Для низкоуровневых helper commands `--project "$PWD"` — physical корень выбранного sibling; выполняйте их из корня проекта. Группа `sibling` может определить Git top-level из подкаталога. Для работы над самим Planveyor тот же facade вызывается из его корня без `--project`. PATH/Python принадлежат trusted launch environment; target-local `.planveyor.pybin` не выбирает executable.

Перед drafting прочитайте target-local `AGENTS.md` и следующие checked-in carriers выбранного project:

- `docs/plans/_template.md`;
- `docs/code_drafts/_template.md`, если code draft нужен;
- `docs/plans/README.md` для status, cluster, queue, review route и UI-gate rules;
- role prompt, владеющий current status.

Public root corpus не задаёт application stack, test harness или UI defaults. Если target-local input отсутствует, зафиксируйте blocker вместо предположения.

## Draft workflow

1. Определите: новый plan или update существующего `PLAN_PATH`. Сначала прочитайте один literal `**Status:**`.
2. Для нового plan выполните bounded discovery через `rg` по `docs/plans`, `docs/followups` и `docs/reviews`. Прямое поручение Owner создаёт обычный (ordinary) plan, в том числе после адаптации sibling. Покажите matching open follow-up и добавьте literal `source_ref#item_id` в `Context links`, сохранив точные исходные `source_ref` и `item_id`. Matching row остаётся unchanged: `status=open`, `plan=null`, `disposition_kind=null`, `disposition_ref=null`, `disposition_commit_oid=null`; automatic backlink запрещён.
   Если совпадений нет, зафиксируйте отсутствие совпадений без искусственной row. Конфликт уже активного плана по тому же результату требует Architect/Owner triage; само совпадение открытой row не требует нового OK. Ordinary plan не является row promotion: prepare/finalize/backlink не являются его предусловиями. Настоящее продвижение row выполняет только штатный promotion writer с exact proof; V2/K1 port остаётся отдельной post-release работой.

3. Выберите intent, `cluster`, `plan_type`, status, tags и target file set. Если пользователь не задал status нового repo-backed plan, используйте `Architect initial draft`.
   Для плана адаптации sibling под стек (slug `stack_adaptation`) Scope включает создание `docs/stack_brief.md` из `docs/_template_stack_brief.md` и его заполнение подтверждёнными ответами Owner через `## Q&A log`, локальные секции восьми carriers (`docs/tools/prompts/architect_status_driven.md`, `docs/tools/prompts/planner_status_driven.md`, `docs/tools/prompts/coder_status_driven.md`, `docs/tools/prompts/coder_migrations_gate.md`, `docs/tools/prompts/reviewer_status_driven.md`, `docs/playbooks/review_staged_or_commit.md`, `docs/playbooks/review_merge_range.md`, `docs/playbooks/post_merge_audit.md`) и корневой `README.md` sibling (его создаёт план адаптации; не `docs/README.md`). §1 согласует назначение и готовность стека, следующая полезная задача — отдельное поручение Owner. Реальные findings capture-ятся штатно; zero findings допустимы.
4. Выберите unique filename: `docs/plans/YYMMDD_HHMM_<slug>.md` по policy выбранного project.
5. Materialize plan из template. Заполните обязательные carriers: header, `Context links`, `plan_meta`, provenance/session context, Problem, Solution, Decisions, Scope, Out of scope, Follow-ups, reviewability, Changes, Acceptance, Tests, Commands, verification handoff и review artifact.
6. Для `Architect initial draft` держите Owner questions в `## Q&A log`, дайте suggested defaults и не переходите в следующий status до explicit Owner answer, если вопрос влияет на scope, decision или acceptance.
7. Не создавайте full executable code draft в Architect initial draft. Planner владеет exact `code_draft_meta.targets` перед `Ready for Coder`. Architect может создать только explicit seed/path-tracking carrier, когда это требуется.
8. Когда code draft нужен, используйте public helper:

```zsh
"$PLANVEYOR_ENTRY" --project "$PWD" \
  planveyor_code_draft_stub_from_plan docs/plans/YYMMDD_HHMM_topic.md --role Architect
```

Для Planner finalization укажите `--role Planner`. Если helper недоступен, создайте template-based draft и укажите exact `code_draft_meta.plan`, `cluster`, `targets` и `deleted_paths: []`.

9. Выберите ровно один live review route из current `code_draft_meta.targets`: all-doc targets используют `docs/doc_reviews/<PLAN_BASENAME>.md`; non-doc target требует `docs/code_reviews/<PLAN_BASENAME>.md`.
10. До `Ready for Coder` exact targets обязательны. Missing planned-new paths можно сообщить только как explicit seed warning раннего draft, а не как green preflight.

## Hard rules

- Skill заводит или правит только plan и его code draft (п. 7–8), а для плана адаптации ещё копию шаблона анкеты `docs/stack_brief.md` (п. 3). Если Owner прямо просит сделать созданный план текущим, разрешено выбрать его через `sibling plan` после validation. Изменения из Scope не вносите, даже мелкие: целевые файлы правит Coder после `Ready for Coder`.
- Не меняйте runtime helpers, model defaults, Manager queue behavior или target-local configuration, если пользователь не авторизовал exact scope.
- Не превращайте plan в code dump. Большие implementation snippets живут в code draft.
- Не оставляйте `UNCONFIRMED`, `TBD` или prose-only promises в fields, где template/lint требует literal value.
- Non-UI plan держит UI fields как canonical `N/A`, без invented UI assumptions.
- Review, role response и historical receipt не заменяют validation current bytes.
- Не запускайте роли или `sibling close --commit` из одного запроса создать draft. Не фабрикуйте Owner answers, не переводите план в Done и не выполняйте commit/push/issue send без отдельного явного разрешения на конкретное действие.

## Validation

Перед handoff выполните target-required plan lint и relevant current checks. Для bundle используйте public facade:

```zsh
"$PLANVEYOR_ENTRY" --project "$PWD" \
  planveyor_plan_bundle --preflight docs/plans/YYMMDD_HHMM_topic.md
```

`--preflight` advisory для early draft и strict hard gate первого executable handoff перед `Ready for Coder`. Genuine refinement при materialized live review использует `planveyor_plan_bundle --scope-check <PLAN_PATH>` через ту же facade только для inventory/integrity со всеми прежними contract/lint/machine-authority/handoff gates. Semantic lint/derived handoff digest, same-contract skip-Planner и fingerprint status window не меняются; scope rc0 не даёт green/route/commit, strict final `--check` обязателен после review. Для Git-backed target выполните `git diff --check` и declared documentation check changed plan/code draft.

Интерпретируйте результат точно: planned review artifact до Reviewer допустим как `PLANNED`; missing/stale target перед Coder — blocker.

## External-only V2 follow-ups

В `plan.v2` deferred work materialize-ится как source-bound `followups.v2` row, не как plan-local mirror. Open row сохраняет null disposition fields; promotion и terminal closure требуют exact external proof. Не backfill-ьте versionless/historical carrier и не переписывайте terminal plan.

## Final response

Верните plan path, code-draft path, status и результат validation. Если Owner явно просил «создай и сделай текущим», после validation вызовите существующий facade для фактически созданного literal path:

```sh
"$PLANVEYOR_ENTRY" --project "$PWD" sibling plan docs/plans/YYMMDD_HHMM_topic.md
```

Дата и slug в примере заменяются агентом на actual filename, а не поручаются человеку. Без явного выбора Owner не меняйте current pointer: назовите готовую команду для этого конкретного плана. Для self-Planveyor сохраняется штатный `planveyor_plan_set` выбранного literal path. Human handoff для sibling — `planveyor sibling architect`; фактические вопросы идут через `planveyor sibling answer`, затем обычный `planveyor sibling run`. Подготовка коммита — `planveyor sibling close`, а `--commit` требует отдельного решения человека по показанному набору. Если что-то не green, назовите exact command и blocker.

[ALWAYS START]
Ты работаешь как роль Planner в выбранном проекте и активном repo-profile.

Цель этого запуска: “выгрузить из памяти” что надо закрепить в **общих доках** и planner-facing canon, перед сменой сессии/контекста.

ЭТО НЕ РАБОТА ПО PLAN: основа = твоя память о handoff/finalize/reviewability проблемах, которые всплыли в этой role-сессии.

Семейство `memory-finalize`:
- этот prompt = lane `general docs sync`; парный lane `followups backlog` описан в `docs/tools/prompts/planner_docs_finalize_followups.md`;
- точный token заголовка reserved process lane = `Process improvements`; числовой префикс в output допустим только как formatting;
- если процессных улучшений нет, в секции `Process improvements` пиши literal-но `NO PROCESS IMPROVEMENTS — why: <reason_code>`, где `reason_code` ∈ `clean_run | already_tracked | out_of_scope | deferred_pending_data`; эта строка должна быть standalone, без markdown-bullet (`-`/`*`), numbering или extra prose.
- если процессное улучшение есть, секция `Process improvements` обязана использовать exact machine-readable block:
  - `### Suggestion <N>`
  - `- symptom: <...>`
  - `- process_gap: <...>`
  - `- suggested_fix: <...>`
  - `- owner: <Architect|Planner|Coder|Reviewer|Manager|Owner>`
  - `- promotion_class: <canon_update|prompt_change|helper_change|routing_change|followup_plan>`
  - `- trigger_ref: <review/blocker/plan/queue ref|unknown>`
  - `- source_ref: <manager-fed plan_ref|unknown>`
- Роль выдаёт только canonical `- key: value` structured suggestions либо exact standalone no-op. Compatibility collector не разрешает numbering, prose или unknown fields в role output; весь body проверяется строгим parser, без удаления хвоста и без замены реального предложения на no-op.
- Единственный durable writer raw PI в `docs/process_improvements/*` — existing collector, который вызывает Manager. Роль не пишет durable PI ни вручную, ни через helper; обычный `Follow-ups` lane не должен shadow/double-write тот же raw row.
- После role output Manager обязан передать эту секцию в `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py process_improvements_collect.py --role Planner --source-ref <plan_ref> --followups-capture-cycle-id <capture_cycle_id> --input - --json`; helper-backed receipt (`clean_noop|materialized|already_tracked|blocked`) является proof path, а chat-only prose не считается proof.
- Граница прямой мутации active canon: после semantic `Done|Superseded` historical `code_draft_meta.targets` и promoted `docs/process_improvements/*` pointer остаются только provenance и не разрешают memory-finalize менять terminal plan, linked code draft, live review, `docs/tools/prompts/**`, `docs/playbooks/**`, active templates/README canon или другие protected paths. Новое предложение идёт в raw PI carrier и затем в отдельный live non-terminal execution carrier; reviewed exact bytes materialize-ятся только прежним pre-terminal exact-bundle closeout.

Жёстко:
- Текущий `PLAN_PATH` (если передан) **не меняй**.
- Весь текст в documentation/follow-up'ах/snapshot'ах и в чате этой role-сессии пиши на русском; код/идентификаторы/пути/команды — на английском; UI-строки — на языке, объявленном проектом.
- Разрешено править только `docs/**` (не трогай продуктовый код).
- `PLAN_PATH` может быть передан, но читать его необязательно. Если читаешь — только быстрый reread, чтобы освежить точные формулировки.
- Не дублируй plan целиком: поднимаем только долгоживущий canon/guardrail.
- Если не уверен — помечай `UNCONFIRMED`.

Что сделать:
1) Вспомни 3–10 planner-owned граблей:
   - exact bundle drift между plan и code draft,
   - reviewability gaps,
   - helper/proof lane ambiguity,
   - stale wording после rerun/restamp,
   - context-only vs executable bundle путаницу,
   - missing repo-local canon pointers.
2) Сформулируй 1–7 дешёвых улучшений канона, которые реально экономят следующий Planner/Coder/Reviewer cycle:
   - `docs/plans/README.md`, `docs/plans/_template.md`,
   - `docs/code_drafts/_template.md`,
   - `docs/README.md`,
   - repo-local docs только если файл реально существует в текущем repo-profile.
3) Для 1–5 самых дешёвых и понятных пунктов — **внеси правки прямо только в неприкрытые guard'ом docs**. Если пункт касается active canon/templates/prompts/playbooks и нет explicit terminal scope / promoted process-improvement carrier, оформи `Process improvements` row вместо прямой правки.
3.1) Если в этом запуске создаёшь/обновляешь `docs/reviews/*` или `docs/followups/*` как долгоживущие артефакты:
   - вычисти transient repo/session-state (`dirty`, `untracked`, “локально создано ...`) или замени его на exact live fact / live-command pointer;
   - прогони `git diff --check -- docs` и исправь accidental trailing whitespace / CRLF / merge markers / лишние пустые строки в EOF в текущем doc-diff;
   - если ругань только на новый Markdown hard-break style, перепиши changed block структурно (bullets/paragraphs), а не оставляй raw trailing spaces.
3.2) Если по явной необходимости создаёшь snapshot для history/handover:
   - не цитируй его из active canon / merge-report / follow-up backlog как source of truth или pointer;
   - durable факты всё равно подними в doc / follow-up / plan.
3.3) Если меняешь shared process documentation/template в `planveyor`, не пиши в sibling repo напрямую:
   - source-side carrier = `docs/process_improvements/*`, upstream request или rollout packet need;
   - если target repo тоже должен принять change, оформи target-local adoption handoff, а не правку из source-сессии;
   - repo-local stub/playbook/template в target repo меняется только через его локальный plan/import flow.
   - если ты роль в sibling, а находка касается общего движка Planveyor или доставляемых им файлов, а не собственного кода или правил стека sibling: запиши её в `Process improvements` (`target_repo_scope: planveyor` ставится строке `docs/process_improvements/*` при triage, в блоке `### Suggestion` этого поля нет) и предложи Owner upstream request по `docs/upstream_packets/_template.md` (runbook `"$PLANVEYOR_RUNTIME_ROOT/docs/guides/stack-sibling.md"`, раздел «Предложить изменение Planveyor»); в репозиторий Planveyor не пиши.
4) Если не хватает данных — оформи follow-up вместо “догадок”.
5) Отдельно выдели 0–5 bounded процессных улучшений для prompt/wrapper/runbook/template/gate surfaces:
   - это не product/runtime fixes и не дублирование already-materialized doc edit;
   - если улучшение уже честнее оформить backlog-item'ом, оставь его в `Follow-ups`, а в `Process improvements` не дублируй;
   - если structured suggestion surfaced, верни полный canonical block в `Process improvements` для collector Manager; не записывай durable PI этой ролью. Пояснение о передаче, если нужно, размести в другой секции ответа, вне `Process improvements`;
   - если таких улучшений нет, используй exact no-op literal из shared family contract.

Выход (в чат):
В `Process improvements` выбери ровно один из двух нижних образцов: первый — structured suggestion, второй — no-op. В ответ копируй только содержимое выбранного `md`-блока, без fences и без поясняющих строк; подставь конкретные значения вместо placeholders.
## 1) Общая документация — предложения
- `<file>`: <что меняем> — <почему> [UNCONFIRMED?]

## 2) Что я изменил в docs (факт)
- `<file>`: <кратко что сделал>

## 3) Process improvements
```md
### Suggestion <N>
- symptom: <что болит / где loop проявился>
- process_gap: <какой process/helper/prompt gap surfaced>
- suggested_fix: <bounded fix / guardrail>
- owner: <Architect|Planner|Coder|Reviewer|Manager|Owner>
- promotion_class: <canon_update|prompt_change|helper_change|routing_change|followup_plan>
- trigger_ref: <review/blocker/plan/queue ref|unknown>
- source_ref: <manager-fed plan_ref|unknown>
```

```md
NO PROCESS IMPROVEMENTS — why: <reason_code>
```

## 4) Follow-ups (если нужно)
- P? `<topic>` — to=<Planner|Architect|Coder|Reviewer|Owner> — why: <1 строка>

[/ALWAYS START]

# Ручное terminal recovery

Это редкий Owner-only playbook для terminal/immutable incident. Он не
автоматизирует recovery и не заменяет обычный conveyor, planveyor_plan_bundle
или его accepted-red helper contract (`--closeout-json`, `--capture-rejected`,
`--verify-rejected`, `--cleanup-rejected`).

## Граница процедуры

- Manager и роли не меняют terminal source plan, linked code draft или declared
  review, не создают successor, не запускают второй Manager и не меняют queue.
- .planveyor.planqueue.json и .planveyor.planqueue.log никогда не редактируются
  вручную.
- Эта процедура не делает source delivery green и не даёт права назвать
  результат accepted_red_recovered без durable proof, который требует
  существующий accepted-red contract.

## 1. Сначала выбрать обычный route

| Наблюдение | Правильный route | Что нельзя называть recovery |
| --- | --- | --- |
| live_blocker на current non-terminal plan | Оставить тот же plan и маршрутизировать Coder или Planner по владельцу blocker. | Owner forensic stop, capture или ручную queue-операцию. |
| Stale review | Попросить Reviewer переписать тот же review artifact на fresh bundle. | Любую same-file Reviewer rewrite. |
| real scope expansion | Маршрутизировать Architect/Planner для normal successor, materialized и linked до terminal state. | Manual terminal branch, пока source ещё можно корректно связать. |
| Material change в ещё валидном deliverable | Вернуть plan Planner для normal reroute в том же plan. | Новый workflow, пока исходный deliverable остаётся валидным. |
| Новый deliverable или invalid old DoD до terminal state | Materialize и связать normal successor до Superseded. | Позднюю дописку backlink в terminal source. |

К rare terminal manual branch можно перейти только если source plan и его
declared review уже terminal/immutable, ordinary same-plan route недоступен, а
pre-existing exact successor/backlink отсутствует или не годится для текущих
dirty bytes. Такой source не исправляют и не reopen-ят: Manager делает
source-attributed stop, а дальнейший выбор принадлежит Owner.

Отсутствие pre-existing exact successor/backlink означает, что continuation
старого source unsupported: не создавайте backlink постфактум и не выдавайте
его за route к safe resume.

## 2. Source-attributed stop без hidden action

Manager фиксирует один readback record и завершает turn. Минимальная identity:

- literal SOURCE_PLAN;
- observed source_HEAD;
- один declared review path;
- текущее состояние oracle, bundle/docs-closeout, queue и Git;
- таблица всех dirty paths из следующего раздела.

Для read-only наблюдения используйте существующие surfaces, а не новую
автоматизацию:

    "$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py plan_status_oracle.py --json <SOURCE_PLAN>
    "$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_plan_bundle --closeout-json <SOURCE_PLAN>
    "$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_docs_closeout <SOURCE_PLAN> --json
    "$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_q_show
    "$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_q_history_json --limit 20
    git rev-parse HEAD
    git status --short

Manager не создаёт plan, не запускает nested Manager, не выполняет capture или
cleanup, не меняет queue и не возобновляет работу автоматически. Нужный
readback не даёт права реконструировать отсутствующий successor или менять
terminal carrier.

## 3. Owner record для dirty paths

До любого нового role run Owner заводит один ряд на каждый dirty path:

| Path | State | Owning plan or workstream | Source HEAD | Disposition | Proof |
| --- | --- | --- | --- | --- |
| <path> | literal observed state | <plan-or-workstream> | <source_HEAD> | <one-explicit-disposition> | <readback-or-review-ref> |

Допустимые решения не угадываются из пути:

- ambiguous_owner блокирует role run. Нельзя делегировать Manager или роли
  stash, restore, reset либо broad staging.
- adopt_into_successor допустим только если path уже есть в
  code_draft_meta.targets successor-а, а inherited delta имеет ref,
  проверенный как часть exact successor bundle.
- Preservation перед destructive overwrite/cleanup требует отдельного явного
  Owner choice. Не переносите bytes в successor только потому, что они лежат
  рядом с terminal source.

## 4. Owner choices после readback

Owner выбирает один следующий top-level шаг, не continuation stopped Manager:

1. Оставить incident остановленным до обычного plan/routing решения.
2. При необходимости сохранить exact rejected bytes перед destructive
   overwrite/cleanup через существующий forensic capture contract
   planveyor_plan_bundle (`--capture-rejected`, затем readback
   `--verify-rejected`). Это optional preservation choice, а не
   automatic action и не proof successful closeout.
3. Позже запустить отдельный single-plan Manager для нового допустимого plan.
4. После fresh readback сознательно пересобрать queue вручную как replacement
   activity. Это отказ от прежнего live continuation, а не его successful
   resume.

Если existing accepted-red route требует durable proof, отказ от capture не
разрешает accepted_red_recovered, green docs-closeout или safe resume old
terminal tail.

## 5. Separate repair и resume proof

Repair выполняется в отдельном non-terminal plan. Перед любой последующей
Owner action заново подтвердите:

- repair plan имеет Done;
- его current review green;
- exact-bundle closeout repair plan завершён по canonical helper readback;
- каждый dirty path имеет resolved ownership/disposition;
- source docs-closeout перечитан заново;
- queue state перечитан заново;
- SOURCE_PLAN, source_HEAD и declared review path не были подменены.

Любое missing, ambiguous или red наблюдение остаётся stop condition. Нельзя
reuse repair result как proof для старого terminal source, нельзя reopen-ить
source и нельзя автоматически запустить Manager. Следующий запуск остаётся
новым явным Owner действием.

## Связанные каноны

- Accepted-red/bundle/capture semantics: режимы planveyor_plan_bundle
  (`--closeout-json`, `--capture-rejected`, `--verify-rejected`,
  `--cleanup-rejected`) и их readback описаны в
  `"$PLANVEYOR_RUNTIME_ROOT/docs/guides/accepted-red.md"`. Это документ
  движка, а не путь в sibling.
- Manager router-only boundary: docs/roles/manager.md.
- Plan/status canon: docs/plans/README.md.

[ALWAYS START]
Ты работаешь как роль Architect в выбранном проекте и активном repo-profile.

Цель этого запуска: предложить follow-ups (новые планы/док‑таски) **из памяти**, перед сменой сессии/контекста.

Семейство `memory-finalize`:
- этот prompt = lane `followups backlog`; парный lane `general docs sync` описан в `docs/tools/prompts/architect_docs_finalize_general.md`;
- exact shared heading token `Process improvements` и literal `NO PROCESS IMPROVEMENTS — why: <reason_code>` materialize-ятся только в `general` lane; здесь не дублируй их отдельной псевдосекцией, если item не требует отдельного backlog-file.
- Process/helper/prompt/canon suggestions не оформляй как обычный `docs/followups/*`; они принадлежат `general` lane `Process improvements` / `docs/process_improvements/*`, если это не отдельный lifecycle follow-up plan.

Жёстко:
- Текущий terminal `PLAN_PATH` (если передан) **не меняй ни при каких `followups_reconciliation_state`**: status, Evidence, checklist и `plan_meta.followups_out` byte-immutable. `open|unknown` = blocker upstream pre-Done contract, а не разрешение на repair в этой lane.
- Весь текст в backlog-файле и в чате этой role-сессии пиши на русском; код/идентификаторы/пути/команды — на английском; UI-строки — на языке, объявленном проектом.
- Разрешено создавать **новые** follow-ups backlog файлы только в `docs/followups/`.
- Generated follow-ups backlog files must not use raw trailing spaces for Markdown hard-breaks; metadata header lines are ordinary lines and must pass `git diff --check`.
- Успешный output `Created:` разрешён только после того, как `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py followups_lint.py <created path>` завершился с exit 0 для созданного backlog-файла; строка вида `P1 [ ] ...` без leading `-` malformed и должна считаться red lane result, а не created follow-up.
- Если helper context держит `followups_reconciliation_state=open|unknown`, верни blocker с `row_ref`/`proof_host`; не ремонтируй terminal plan и не подменяй ordinary proof backlog/prose/PI capture.
- `PLAN_PATH` можно читать только как repo-backed источник точных фактов и exact `source_ref=<Manager-fed plan_ref>`; найденный впервые post-terminal ordinary item materialize-ится ровно одной active lint-green row в existing `docs/followups/*.md` с `plan=null`.
- Follow-up’ы должны быть оформлены как отдельные задачи (которые можно превратить в новые plan’ы), без “тихих фиксов”.
- Прямое поручение Owner допускает независимый обычный (ordinary) plan после bounded discovery. Matching open follow-up раскрывается literal `source_ref#item_id` в `Context links`, но row остаётся unchanged: `status=open`, `plan=null`, `disposition_kind=null`, `disposition_ref=null`, `disposition_commit_oid=null`; automatic backlink запрещён. Если совпадений нет, не создавай искусственную row; конфликт уже активного плана требует Architect/Owner triage. Ordinary plan не является row promotion: prepare/finalize/backlink не являются его предусловиями. Реальный row backlink пишет только штатный promotion writer с exact proof; future plan pointer не выдумывается. Real debt capture обязателен, zero findings и честный no-op допустимы.
- Эта lane post-closeout only: не используй memory-finalize как live route для active blocker. Active scope/follow-up split сначала классифицирует Architect (`same-contract reroute` / `real scope expansion` / `de-scoped follow-up`), и только de-scoped debt попадает сюда после terminal closeout или explicit promote.
- Если не уверен — помечай `UNCONFIRMED`.

Что сделать:
1) Вспомни, что вы:
   - сознательно отложили “после”,
   - обнаружили в процессе (risks/suggestions),
   - сломали/чуть не сломали (и надо закрепить тестом/доком/гейтом).
2) Сгруппируй follow-ups:
   - documentation/process,
   - UI/interface contracts,
   - tests/smokes,
   - refactor/tech debt,
   - UX polish.
3) Если follow-up’ов **нет**:
   - не создавай файлы,
   - в чат верни `NO FOLLOWUPS` (не редактируй/не создавай файлы, не делай git‑операции; читать файлы можно).
4) Если follow-up’ы **есть** — создай один backlog‑файл в `docs/followups/`:
   - имя: `docs/followups/YYMMDD_HHMMSS_followups_memory_architect.md` (по местному времени; уникальное),
   - шаблон: `docs/followups/_template_followups_backlog.md`.
5) Внутри backlog‑файла выпиши follow-ups (списком), и для каждого follow-up укажи:
   - приоритет (P0/P1/P2),
   - `cluster` (основная доменная тема) и `tags` (опционально),
   - to=<Planner|Architect|Coder|Owner>,
   - краткий scope,
   - DoD в 1–3 пунктах,
   - `plan=null` (обязательно, пока follow-up не promoted в реальный dev-plan);
   - при настоящем row promotion plan path materialize-ится только штатным promotion writer с exact proof; независимый ordinary plan не разрешает backlink, в memory backlog не придумывай future `docs/plans/...` pointer.

V2 external-only boundary: for a `plan.v2` source, a created row must use
`followups.v2`, exact `source_ref=<plan_ref>` and stable `item_id`; it owns
typed `status/plan/disposition_kind/disposition_ref/disposition_commit_oid/reason`.
Do not add `plan_meta.followups_out`, mutate a terminal plan, queue-import a V2
row, or write a disposition directly. `open` keeps every disposition field
`null`; the sole writer is `scripts/followups_apply.py` after the frozen
`Architect -> Coder -> Planner -> Reviewer` declaration union.

## Ordinary terminal `plan.v2` compact declaration

Если Manager передал ordinary terminal `plan.v2` lane с exact
`followups_capture_cycle_id`, этот раздел supersedes backlog-file и
`Created:`/`NO FOLLOWUPS` tail. Не создавай durable файл и не вызывай writer.
Собери ровно один bare strict compact JSON object без fence, prefix, suffix
или summary:

```json
{"role":"Architect","proposed_rows":[],"role_no_items_reason":"<precise Architect reason>"}
```

Ровно три ключа: `role`, `proposed_rows`, `role_no_items_reason`. Для non-empty
`proposed_rows` reason обязан быть `null`; для empty — непустой строкой. Не
передавай schema, `plan_ref`, source commit/blob, full baseline или full
`followups_declaration.v2`; не материализуй `docs/followups/*`. Максимум
`16384` UTF-8 bytes. Helper owns current committed source/worktree equality,
complete baseline, ordered family `Architect -> Coder -> Planner -> Reviewer`
and full declaration binding; existing `scripts/followups_apply.py` remains
sole durable writer after Manager's freeze.

До chat return сама role стандартным file-write/edit tool записывает эти exact
compact bytes в helper-derived transient non-authority leaf
`.tmp/followups_capture/<plan_stem>/<capture_cycle_id>/ordinary_v2_inputs/Architect.json`,
затем вызывает canonical helper:

```sh
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py followups_capture.py submit-ordinary-v2 --project-root . --plan-ref "$PLAN_PATH" --capture-cycle-id "$followups_capture_cycle_id" --role Architect --input-current --write
```

`--input-current` — normal happy path; explicit `--input -` остаётся только
compatibility API и не требует pipe, heredoc или PTY. Проверь returned
`ordinary_v2_role_submission_ack.v1` (`state=submitted` или
`already_submitted`) и верни в чат только этот diagnostic acknowledgement.
Не возвращай compact declaration, leaf path или acknowledgement как
Manager-readable binding input; Manager не выбирает, не передаёт и не читает
их. Не создавай second carrier и не считай acknowledgement authority: только
последующий helper-owned `bind-ordinary-v2 --submission-current` rereads
canonical slot. Any malformed/oversize/ambiguous leaf или non-green
acknowledgement — blocker; после исправления leaf допустим только explicit
same-cycle redispatch этой prepared role, без automatic Manager retry/new begin.

Выход (в чат):
- Если создал: первая непустая machine control line — один bare `Created: docs/followups/<name>.md`; markdown/backticks вокруг control line запрещены. Human summary не добавляй.
- Иначе output ровно `NO FOLLOWUPS`, без summary и дополнительных строк.

[/ALWAYS START]

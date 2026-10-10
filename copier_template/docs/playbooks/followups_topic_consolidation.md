# Playbook: consolidate follow-ups backlog by topic

Указания на docs/followups/index.md применяются только при существующем
project-local индексе. Если его нет, используй standalone backlog и явно
фиксируй index/triage/import как `N/A (why=carrier absent)`; не создавай индекс
ради прохождения gate.

Зачем: когда было много merge-циклов и follow-ups расползлись по разным `docs/followups/*` и “хвостам” в `docs/plans/*`, собрать **один** master backlog по теме и подготовить безопасное удаление старых topic-followups файлов.

Важное:
- `docs/followups/*` — backlog, а не plan (grammar: `docs/followups/_template_followups_backlog.md`).
- Если в процессе всплывают спорные “done/не done” или границы темы — фиксируй как `UNCONFIRMED` и эскалируй на Owner (не додумывай).
- `Done + Imported into` делает source-followups файл только `cleanup-ready` кандидатом; перед удалением нужен `planveyor_followups_query cleanup-receipt --project-root ... --format json` и per-file `decision=delete-ready`.

## Inputs (что нужно определить перед стартом)
- **Topic**: краткое имя selected topic (например `integration-contracts`).
- **Keywords**: набор grep-ключей из selected project/plan (пример: `(<keyword-1>|<keyword-2>)`).
- **Topic boundaries**: что считаем “в теме” (например: declared interface / data contract / process hygiene).
- **Done criterion** (по умолчанию): если есть релевантный dev/review plan со `**Status:** Done` — считаем пункт `handled`, иначе `open`/`UNCONFIRMED`.
- **Cross-topic policy**: если пункт относится к другой “master” теме (например, related master), решить заранее:
  - где будет **единственная** “истина” (в каком master backlog),
  - а где будет только pointer (без дублирования пункта).

## Outputs (артефакты)
- Inventory snapshot: `docs/snapshots/<YYMMDD_HHMM>_<topic>_followups_inventory.md`
- Master backlog: `docs/followups/<YYMMDD_HHMM>_<topic>_followups_master.md`
- Updated index: docs/followups/index.md
- (опционально, но рекомендуется) Short “process plan” на саму консолидацию (docs-only), чтобы было где фиксировать evidence/gates:
  - `docs/plans/<YYMMDD_HHMM>_<topic>_followups_consolidation.md`

### Ручная индексация выбранного source document (link-only; без правки source)

Этот вариант применяй только когда Owner/intake/plan явно объявляет существующий
Owner-maintained source document: например,
`SOURCE_DOC=docs/playbooks/role_prompt_invariant_map.md`. Это concrete
repo-relative path; выбранный `SOURCE_DOC` должен существовать локально. Если цель —
добавить его темы в follow-ups так, чтобы:
- видеть общую картину в docs/followups/index.md,
- **не копировать** описания задач,
- и **не редактировать** source document,

используй manual link-only index.

#### Variant A: link to existing master backlog’и (1:1)

- В соответствующем master backlog по теме добавь секцию вида:
  - `## <SOURCE_DOC> topics (1:1 mapped; index-only)`
  - в ней — только exact heading titles: 1 строка = 1 title из `SOURCE_DOC`, например:
    - `docs/playbooks/role_prompt_invariant_map.md` — `Hard Invariants`
- Правило: добавляй title только если он “бьётся 1:1” с темой master backlog’а.
  - Если title пересекает 2+ master тем — **не дублируй**; оставь его в `SOURCE_DOC` или сделай pointer в “Other” backlog, если Owner попросит.
- Политика ссылок:
  - Source of truth по деталям = `SOURCE_DOC`,
  - в followups держим только “индексацию” и приоритизацию,
  - не копируй source text; не меняй source или backlinks без explicit Owner permission.

Note про “line numbers”: если `SOURCE_DOC` часто правят/чистят, ссылки вида `:123` быстро устаревают. В таких случаях лучше держать **exact heading title** (его легко найти поиском).

#### Variant B (optional): отдельный topics-index файл (если совсем нет 1:1 маппинга)

Если маппинга 1:1 почти нет (или тема — “сборник всего”), можно сделать отдельный index-файл:
- `docs/followups/<YYMMDD_HHMM>_<topic>_topics_index.md`
- внутри — один пункт на один exact heading title из `SOURCE_DOC`,
- каждый пункт содержит `src=<SOURCE_DOC>` (без копипасты описаний). Это plain
  index prose, не valid `followups.v2 source_ref` row.

## Procedure

### 0) Быстрый скан источников

1) Найди follow-ups и упоминания темы:
   - `rg -n "<KEYWORDS>" docs/followups docs/plans`
   - (опц.) `rg -n "^## Follow-ups \\(deferred\\)" docs/plans`

2) Зафиксируй список “источников” (filenames only):
   - topic-followups файлы (которые потенциально хотим заменить master backlog’ом),
   - планы, где тема встречается не случайно (feature candidates / follow-ups / контракты),
   - review/audit документы, которые ссылаются на старые followups.

### 0.5) (Optional) Подготовь manual index для `SOURCE_DOC`

Manual variant **does not select or run an extractor/checker**. Применяй heading
grammar только если его объявляет selected source contract; иначе открой
`SOURCE_DOC` и перечисли exact heading titles вручную.

Результат вставляй как строки в нужный backlog (Variant A) или отдельный topics-index (Variant B):
`<exact heading title> — status=open — src=<SOURCE_DOC>`

`src=` остаётся plain index prose, не valid `followups.v2 source_ref` row. Любой
helper требует собственного declared source contract; manual variant не обещает
arbitrary source support.

### 1) Нормализация пунктов (без потери смысла)

1) Составь **нормализованный список** пунктов:
  - каждому пункту дай стабильный ID (`TOPIC-1`, `TOPIC-2`, …) или просто нумерацию,
  - добавь `cluster` (см. `docs/plans/README.md` → `cluster (enum; канон)`) + `tags`,
   - добавь `to=<Planner|Architect|Coder|Owner>` (кто должен принять решение/взять в работу),
   - добавь `status=<open|promoted|handled|UNCONFIRMED>`,
   - добавь `plan=<docs/plans/...|null>` если пункт уже “promoted”.

2) Дедупликация:
   - если один и тот же пункт встречается в нескольких файлах — оставь одну строку и перечисли источники в `Sources:`/`Notes:`.
   - если пункт “изменился” (разные формулировки) — сохрани более точную формулировку, но не меняй смысл без подтверждения (иначе `UNCONFIRMED`).
   - если пункт явно “cross-topic” и уже есть (или должен быть) в другом master backlog — **не дублируй**:
     - в “не главном” backlog оставь pointer вида `(Tracked in <Other master>): <path>`,
     - в inventory snapshot зафиксируй “decision: tracked in <Other master>”.

3) Если нужно проставить отметки прямо в старых range-followups:
   - договорись о формате (например `(+)`/`(-)`),
   - `(+ )` = подтверждённо сделано, `(-)` = ещё не готово/не подтверждено.
   - если файл range-followups смешанный (несколько тем) — **не удаляй его** до консолидации всех тем:
     - пометь секцию как `(Consolidated): <master backlog path>`,
     - оставь в файле только “след” (что консолидировано) и не переноси туда новые пункты.

### 2) Inventory snapshot (чтобы можно было удалять старое)

Создай snapshot в `docs/snapshots/*` и помести туда:
- список источников (filenames),
- нормализованный список пунктов + `migrate=yes/no`,
- краткие пояснения “почему migrate/no-migrate”,
- open questions / что требует Owner-confirm.

Правило ссылок:
- если планируется удалять старые followups файлы, **не делай их “живыми” ссылками в каноне**; достаточно “git history: `<filename>`”.

### 3) Master backlog по теме

Создай master backlog файл в `docs/followups/*`:
- перенеси **только незавершённые** пункты (`open`/`promoted`/`UNCONFIRMED`),
- `handled` пункты не переносить (достаточно, что они остаются в истории/планах),
- для спорных пунктов ставь `status=UNCONFIRMED` и `to=Owner`.

Рекомендуется добавить в master:
- `Supersedes (git history; old files): ...`
- ссылку на inventory snapshot.

### 4) Обнови docs/followups/index.md

- Добавь строку на master backlog.
- Старые topic-followups:
  - либо убери из индекса (если готовим удаление),
  - либо пометь как superseded (если ещё не готовы удалять).

### 4.5) Обнови backlinks (чтобы можно было удалять старое)

Типовые места, где живут “живые” ссылки на старые followups:
- line-by-line code reviews: `docs/code_reviews/*` (обычно строка `**Follow-ups backlog:** ...`),
- планы, которые ссылались на “source aggregator”/range-followups: `docs/plans/*` (в `Context links` / `Sources`),
- audit/review отчёты по merge-range: `docs/reviews/*` (если там есть “Backlog:” ссылки).

Рекомендация по ссылкам:
- если старый followups файл планируется удалить, в “живых” доках лучше оставлять **только имя** (git history): `git history: \`<filename>\``.

### 5) Подготовь безопасный cleanup (удаление делает Owner)

0) Semantic receipt gate для `docs/followups/*`:
   - `planveyor_followups_query cleanup-ready --project-root ...` показывает только candidate set.
   - `planveyor_followups_query cleanup-receipt --project-root ... --format json` должен показать `decision=delete-ready` для каждого удаляемого файла; `retain` / `needs-richer-summary` остаются как durable context.

1) Sanity: убедись, что по `docs/**` не осталось ссылок на удаляемые followups (кроме snapshot, если это сознательно):
   - `rg -n \"docs/followups/<OLD_FILE>\" docs --glob '!docs/snapshots/**'`
   - (опционально) если хочешь “не держать битые ссылки” даже в ревью-артефактах/аудитах:
     - `rg -n \"docs/followups/<OLD_FILE>\" docs --glob '!docs/snapshots/**' --glob '!docs/reviews/**' --glob '!docs/doc_reviews/**' --glob '!docs/code_reviews/**'`

2) Gate:
   - `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_doc_lint`

3) После удаления повтори:
   - `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_doc_lint`

### 5.5) Cleanup “Done” triage plans (optional; reduces `docs/plans/` noise)

Иногда follow-ups живут не только в `docs/followups/*`, но и в маленьких “review-only / range triage” plan-файлах, которые уже `**Status:** Done` и содержат 1–2 пункта.
Чтобы не держать такие планы бесконечно:

1) Найди кандидатов (примерные паттерны):
   - `rg -n \"\\*\\*Status:\\*\\* Done\" docs/plans/*reviewer* docs/plans/*range* docs/plans/*memory*`
   - или по именам: `ls -1 docs/plans | rg -n \"reviewer_|reviewer_range|memory_followups\"`

2) Для каждого кандидата:
   - перенеси **все** ещё актуальные follow-ups в соответствующий master backlog (или в `Other topics backlog`, если тема спорная) и пометь как `UNCONFIRMED`, если нет фактов;
   - проверь backlinks: `rg -n \"<FILENAME>\" docs` и замени ссылки:
     - в “живых” доках → на master backlog / snapshot,
     - если это просто историческая отсылка → `git history: \`<FILENAME>\``;
   - удали plan-файл.

3) Gate:
   - `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_doc_lint`

### 5.6) Cleanup `docs/reviews/*post_merge_audit_range_*.md` (optional; reduces `docs/reviews/` noise)

Иногда post-merge audit’ы уже выполнили роль “разовый отчёт по диапазону”, а дальше все незавершённые задачи живут:
- в master backlog’ах `docs/followups/*_followups_master.md`,
- и/или в каноне (существующие architecture/API/schema/UI carriers выбранного проекта из `Context links`).

Тогда audit-файлы можно удалять (Owner обычно хочет “минус шум”), но важно не оставить битые ссылки.

Procedure:
1) Найди “живые” ссылки на audit-файлы вне `docs/reviews/`:
   - `rg -n \"docs/reviews/.*post_merge_audit_range_\" docs --glob '!docs/reviews/**'`
2) Заменяй ссылки так:
   - в каноне → `merge-range audit (git history): <FILENAME>`
   - в snapshots/inventory → `git history: <FILENAME>`
   - (если ссылка была “entrypoint”, но файл удаляем) → лучше дать pointer на backlog (docs/followups/index.md) или канон, а audit оставить только как `git history`.
3) Удали audit-файлы:
   - `rm docs/reviews/<...>post_merge_audit_range_...md`
4) Gate:
   - `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_doc_lint`

Note: если всё же хочешь сохранить 1 “entrypoint” audit на последние изменения — оставь только самый свежий, а остальные переведи в `git history` и удали.

### 6) Optional: post-merge hygiene helper

Если есть git-range и задача именно “после merge”:
- `planveyor_docs_hygiene_suggest --range BASE..HEAD --include-followups`
- если потом реально удаляешь temp docs вне normal `merge_run`, сначала прогони `planveyor_docs_hygiene_archive --range BASE..HEAD --apply`

## Definition of Done (for consolidation)
- Есть inventory snapshot (можно восстановить контекст после удаления старых файлов).
- Есть один master backlog по теме с **только незавершёнными** пунктами.
- docs/followups/index.md указывает на master backlog (а не на старые topic-followups).
- `doc-lint` зелёный.

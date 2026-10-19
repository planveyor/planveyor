# Playbook: Doc review — staged/current or single commit (documentation/registry)

Шаблон отчёта: `docs/doc_reviews/_template_single_commit.md`.

Это не роль проекта, а плейбук для ревью документации и реестра одного
commit/current bundle. Роль Reviewer и обязательный старт задаёт выбранный
role/profile source; общее тело не предполагает конкретный продукт, язык,
framework или структуру исходников.

Выбор шаблона и владение:

- общий шаблон по умолчанию находится в
  `docs/doc_reviews/_template_single_commit.md`;
- optional repo-profile override находится в
  `docs/doc_reviews/profiles/<repo_profile>/_template_single_commit.md`;
- repo-local mirrored defaults, если они существуют, не становятся вторым
  каноном и не должны неявно создавать новый artifact.

## Режим

Ты — строгий ревьюер документации. Анализируй только объявленный target и
фиксируй новые или изменённые contracts, дубли, противоречия и нужные
canonical updates. Пиши по-русски, деловым тоном; английский оставляй для
команд, путей, кода и literal error strings.

- Не придумывай facts: если объявленный search/harness ничего не нашёл, так и
  напиши.
- Не придумывай проблемы и не оставляй пустые секции.
- Называй symbols и paths буквально. Проверяй определения, ownership и
  consumers, а не случайные упоминания или imports.
- Если legacy artifact уже использует английские headings, не делай
  rename-only churn; новый prose остаётся Russian-first.

## Вход

- `COMMIT`: `<hash|current|staged|current bundle|staged bundle>`;
- `SPEC` (optional): source path, URL или heading;
- выбранный project/profile canon, если он объявляет registry schema, component
  taxonomy, code roots или validation harness.

Если `PLAN_PATH` уже есть, `current bundle` и `staged bundle` означают
bounded review exact plan bundle. Dirty files вне bundle не являются blocker.

## Scope

Проверяй только изменённые Markdown-carriers, которые описывают public
behavior, interfaces, ownership, operational workflow, registry entries или
планируемые components. Также читай только канонические documents, на которые
они ссылаются или которые названы выбранным profile/Context links.

Не исключай файл только по его имени: README, changelog или agent guide входят
в review, когда они меняют contract. И наоборот, не превращай review одного
commit в полный scan всех docs без объявленной причины.

## Процесс

1. Получи diff:
   - `current`/`working`/`changed`: `git diff HEAD --patch --find-renames --find-copies --stat`;
   - `staged`: `git diff --staged --patch --find-renames --find-copies --stat`;
   - `current bundle`/`staged bundle`: сначала `planveyor_plan_bundle --scope-check <PLAN_PATH>`, затем тот же diff с exact bundle paths из JSON. rc0/`scope_ok` подтверждают только inventory/integrity; planned absence и materialized red/stale review остаются completion debt, `not_selected` не validated. После review обязательны strict final lint и `planveyor_plan_bundle --check <PLAN_PATH>`; scope не разрешает green/handoff/commit;
   - literal hash: `git show --patch --find-renames --find-copies --stat <COMMIT>`.
2. Зафиксируй short target id: first seven hash characters, либо `current`,
   `staged`, `current_bundle` или `staged_bundle`. Время artifact —
   `YYMMDD_HHMM` в declared local timezone.
3. Прочитай SPEC и Context links. Сверь diff с source of truth, а не с
   запомненными product conventions.
4. Для каждого изменённого contract назови component/surface по объявленной
   taxonomy. Если taxonomy отсутствует, опиши фактический symbol/path и
   зафиксируй отсутствие классификации как gap, не угадывай framework type.
5. Используй только объявленные repo/profile search roots и commands. Проверь:
   - definition или authoritative declaration;
   - duplicate implementation/registry row;
   - contradictory name, path, state, owner или interface between changed and
     canonical documents;
   - documentation impact для нового/изменённого behavior.
6. Разнеси findings: `S1 Blocker`, `S2 Risk`, `S3 Nit`, follow-up. Каждая
   finding содержит why, concrete recommendation и `file:line`.
7. Создай `docs/doc_reviews/YYMMDD_HHMM_<SHORT>.md` по выбранному template.

## Проверки

- **Definitions and declarations.** Ищи literal names из diff в объявленных
  code, schema и docs roots. Не подменяй точный поиск broad global match.
- **Registry and canon.** У нового reusable component должен быть один
  canonical owner и согласованный lifecycle status. Если репозиторий не ведёт
  registry, зафиксируй это как bounded `N/A (why=...)`.
- **Interfaces and behavior.** Проверяй input/output, validation, error states,
  access/scope, data invariants и operational assumptions только там, где они
  объявлены target contract.
- **Generated and derived surfaces.** Не редактируй generated output как
  source of truth и не выдавай successful generation за proof исходного
  contract. Проверь owner, input и current readback.
- **Product-specific rules.** Framework examples, component names,
  template paths и checklists применяй лишь когда выбранный snapshot или
  project canon прямо их объявляет. Для другого profile выбирай его taxonomy,
  harness и acceptance criteria; общий playbook не добавляет универсальную
  команду.

## Формат результата

Отчёт содержит target, reviewed paths, source refs, actual commands/results и
findings. Для отсутствующих проверок пиши reason и next owner. Не называй
historical green report доказательством current bytes: current review должен
быть связан с exact commit/bundle и текущими evidence assets.

Создавай artifact по выбранному template без удаления его required header,
dual-lane/synthesis, severity, exact-bundle hygiene и Architect handoff
sections. Template задаёт machine-consumed report grammar; общий playbook не
разрешает заменить её свободным prose. Same-contract rerun обновляет тот же
live artifact, а новый path требует real scope expansion или independent
contract.

Architect later дописывает `Архитектурное ревью` или сохраняет legacy `Arch
review`; это не отменяет reviewer findings и не materialize-ит implementation
scope. Если remediation нужна, она идёт отдельным bounded follow-up, а не
скрытой правкой в review-only flow.

## Данные для анализа (optional transport input)

<<SPEC_TEXT>>
$SPEC_TEXT
<<END_SPEC_TEXT>>

<<DIFF>>
$DIFF
<<END_DIFF>>

Если вызывающая сторона не materialize-ила один из blocks, это означает отсутствие input,
а не приглашение реконструировать его из истории или другого profile.

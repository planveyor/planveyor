# Playbook: архитектура документации

Этот playbook определяет, где живёт правило, как оно доставляется consumer и
какой artifact может служить доказательством. Он применяется к публичному
Planveyor corpus и не устанавливает product-specific defaults.

## Слои

| Слой | Назначение | Writable owner |
| --- | --- | --- |
| Markdown source | решения, lifecycle, role guidance, templates | владелец документа |
| Control-plane metadata | компактные schema/vocabulary данные с declared consumer | владелец source carrier |
| Derived artifact | индекс, report, lint result, packet summary | generator или owner указанного artifact |
| Runtime bundle | materialized prompt, session input, generated view | runtime consumer; не второй canon |

Markdown остаётся source of truth для narrative и ownership. JSON допустим только
когда его читает конкретный deterministic consumer. Generated index или runtime
bundle не становится authorable substitute для source.

## Ownership и delivery

1. У каждого shared carrier есть один source owner.
2. Source change не копируется вручную в consumer. Изменение общего контракта
   или механики сопровождается `docs/contract_notices/<change-id>.json` с
   `summary`, `contract_changes`, `engine_changes`, `sibling_actions`, `checks`.
   Это JSON object: `summary` — непустая однострочная строка, остальные поля —
   массивы таких строк (пустые массивы допустимы); reader проверяет каждый
   historical blob до создания candidate и записывает фактические commit/path.
3. Consumer принимает новую версию через Copier upgrade и проверяет созданный
   локальный план адаптации. Извещение не хранит адресата и ACK.
4. Отсутствующий override не создают «на вырост»: shared default остаётся
   каноническим, а target-local surface появляется только у реального consumer.
5. Нельзя использовать mirror или stale copy как новый source для scaffold,
   review или plan.

Для точной проверки membership используй runtime readback, если он materialized:

~~~bash
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_shared_docs_mirror_drift \
  --target-root /absolute/path/to/target --json
~~~

Readback сообщает факты о текущем set; prose ниже не
создаёт второй writable mirror registry. Если declared contract требует
fail-closed stop, запускай соответствующий strict gate через public facade.
Ни readback, ни gate не изменяют consumer.

## Templates и prompts

- Shared template — default для всех consumers, пока у consumer нет
  materialized override с documented owner.
- Resolver выбирает target-local override только когда он существует и
  принадлежит consumer; иначе он возвращает shared default.
- Role prompt, plan/code-draft scaffold и review template не получают hidden
  stack assumptions. Product tests, UI harness и integration rules объявляет
  target plan или target-local canon.
- Artifact-only outputs (docs/reviews/, docs/code_reviews/,
  docs/doc_reviews/, generated assets) — evidence, не template authority.

## Repo-local metadata

Любой repo с shared plan grammar хранит собственный declared vocabulary рядом с
планами. Product schemas и catalogs живут рядом с product source. Не копируй
целое docs/_meta/ из другого consumer и не создавай central JSON repository.

Для каждого persisted metadata carrier зафиксируй:

- schema/version;
- owning source document;
- один или несколько deterministic consumers;
- lifecycle обновления и проверку.

Если такого consumer нет, держи правило в Markdown, а не заводи декоративный
JSON artifact.

## История, snapshots и receipts

Active canon содержит current decisions и короткие pointers. Исторический
контекст, raw tool output и dated debate остаются в history/archive или
handover artifact. Active canon не ссылается на docs/snapshots/*.

Archive JSON и version-pinned evidence сохраняют исходные bytes, digest и
provenance. Новый derived report может дать portable presentation, но не
переписывает historical archive ради единообразия.

## Проверка изменения

Перед closeout:

1. Определи слой и owner каждого changed carrier.
2. Проверь, что source, derived artifact и runtime bundle не перепутаны.
3. Если изменён общий контракт или механизм, проверь извещение за диапазон
   исходных commits и включение его действий в локальный план при upgrade.
   Существующий packetization gate для source-only отчёта остаётся применимым
   по собственному declared contract; извещение не становится rollout packet.
4. Запусти scoped doc lint для current exact bundle.
5. Сохрани current readback или receipt там, где change требует proof.

Не переносите lifecycle в unbounded profile tree, не заменяйте source Markdown
ручным JSON/XML и не принимайте chat prose как evidence доставки.

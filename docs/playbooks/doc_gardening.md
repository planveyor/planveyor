# Playbook: Doc Gardening (weekly canon GC)

Цель: регулярно уменьшать энтропию в каноне и превращать “правила/запреты” в **повторяемые рецепты** (golden paths), чтобы меньше упираться в память, а больше ехать по рельсам.

Этот плейбук **не заменяет** post-merge процессы:
- Post-merge harvest: `docs/playbooks/post_merge_plan_harvest.md`
- Post-merge docs hygiene: `docs/playbooks/post_merge_docs_hygiene.md`
- Canon sweep: `docs/playbooks/docs_canon_sweep.md`
- Doc lint policy/commands: `docs/playbooks/doc_lint.md`

Doc gardening отличается тем, что он **вне мержа**: раз в неделю (или раз в 2 недели) мы целенаправленно делаем “GC” одного канонического раздела.

---

## Inputs

- Тема/боль (что “вечно забываем” или “вечно ломаем”).
- Канонические документы по теме (1–3 файла/раздела максимум на одну сессию).
- Текущий backlog по теме из `Context links`, если он существует.
- Реестр source-owned active/candidate entrypoints: `"$PLANVEYOR_RUNTIME_ROOT/docs/guides/golden_paths.md"`. В sibling его не копируют: для target-local workflow читай declared local carrier.
- Свежие merge/review артефакты, если gardening вырос из post-merge range (чтобы не потерять повторяемые решения/ошибки после удаления plan'ов).

---

## Outputs (минимально достаточное)

1) Один понятный entrypoint (“start here” / golden path), который покрывает 80% кейсов.
2) Уменьшение дублирования между канонами (один источник истины).
3) Если всплыли новые работы: 1–3 follow-up пункта в backlog (без размазывания по 20 файлам).
4) Для объявленных runtime entrypoint'ов вне текущего source repo явно
зафиксировано: обновили / изменений не нужно (why) / нужен follow-up, и та же
судьба отражена в выбранном discovery registry как literal materialized row.
5) Для темы явно решено: existing golden path обновили / нового кандидата нет / новый кандидат промоутнули в engine registry `"$PLANVEYOR_RUNTIME_ROOT/docs/guides/golden_paths.md"` либо в declared target-local carrier.
6) Snapshot'ы не становятся pointer'ами из active canon. Если нужен durable хвост, поднимаем сам факт в канон / audit / follow-up, а snapshot оставляем только как history/handover artifact.

---

## Runbook (60–90 минут)

### 1) Выбери цель сессии (одна!)

Примеры хороших целей:
- “Объявленный form workflow: сделать golden path, чтобы не помнить правила”.
- “Runtime UI workflow: собрать short path по state/grid/smoke и перестать листать пять доков”.
- “Registry: убрать дубли и сделать один entrypoint по компонентам”.
- “Контракт между компонентами: собрать ‘как правильно’ в одном месте и убрать устаревшее”.

### 2) Выбери ограниченный scope

- 1 раздел канона.
- Не более 3 файлов правок за сессию (если иначе не получается — это сигнал, что нужна отдельная задача/plan).

### 3) Прогон sanity (чтобы не сломать базу)

Команды (локально):
```bash
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_doc_lint
```

Если gardening фокусируется на объявленном runtime handbook в owning target,
запусти его literal declared lint/check. Для shared Planveyor canon используй
`planveyor_doc_lint`; не копируй target path или command без materialized target contract.

### 4) Перепиши “запреты” в “рецепты”

Шаблон того, что стоит делать:
- вынести “что делать по умолчанию” в carrier, который реально принадлежит
  текущему repo: tooling process discovery использует собственный registry,
  runtime handbook — owning target entrypoint или literal materialized registry row;
- в глубину оставить детали, исключения и анти‑паттерны;
- для каждого “правила” дать либо:
  - “когда применяется” (trigger),
  - “как выглядит в коде” (скелет),
  - “как проверить” (команда/ожидаемый результат).
- если канонизируешь runtime-bypass lesson из ревью/плана — называй exact surface buckets (`page`, `fragment/partial`, `list/api`, `supporting endpoint`, `mode/role exception`), а не vague `sibling surfaces`; это превращает “граблю” в проверяемый рецепт.

### 5) Подкрепи процесс механикой (только если это дешево)

Проверки, которые обычно окупаются:
- commands из selected profile/harness с literal declared expected result; visual
  evidence добавляем только когда selected target объявил соответствующий scenario.

Если хочется добавить новый lint/gate: сначала зафиксируй рецепт (golden path), и только потом ужесточай.

### 6) Закрой петлю (коротко)

- Если возникли follow-ups: добавь в backlog и поставь приоритет.
- Если стало ясно, что канон противоречит коду: либо поправь канон, либо заведи follow-up на “привести код к канону”.
- Если тема пришла из post-merge review/harvest: явно зафиксируй судьбу
  объявленного runtime entrypoint и его literal materialized registry row.
- Если тема выросла из documentation/process-only slice, который обобщает реальный runtime blocker-class, держи рядом 1 motivating review artifact для sanity-check, но не превращай его в durable pointer/source of truth: в канон поднимай уже сам invariant/recipe.
- Отдельно ответь на discovery-вопрос: existing golden path хватил / нужен апдейт / появился новый кандидат, который надо промоутнуть в engine registry `"$PLANVEYOR_RUNTIME_ROOT/docs/guides/golden_paths.md"` либо в declared target-local carrier.

---

## Suggested starting target

- Выбранный tooling-process discovery registry.
- Runtime entrypoint, объявленный выбранным project/profile, с literal
  target-local carrier или `N/A (why=...)`.

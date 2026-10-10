# Playbook: split active work into git worktrees by topic

Указания на docs/followups/index.md применяются только при существующем
project-local индексе. Если его нет, используй standalone backlog и явно
фиксируй index/triage/import как `N/A (why=carrier absent)`; не создавай индекс
ради прохождения gate.

Зачем: когда активных планов/фоллоу-аппов стало много, разделить работу по “темам” так, чтобы:
- меньше конфликтов в голове (и в рабочем дереве),
- проще искать релевантные планы,
- `.planveyor.planpath` был “свой” на каждый worktree.

См. также:
- быстрые команды (`planveyor_plan_list`, `planveyor_plan_set`): `docs/README.md`
- git worktree troubleshooting: `git help worktree`

## Suggested mapping

> Это примерный скелет. Темы, каталог worktree, ветка, base ref и keywords берутся из выбранного project/plan. Если тема попадает сразу в 2 worktree — держи её в одном (source of truth), а в другом оставляй только pointer (без дублирования задач). Пример не назначает стек или профиль.

1) `integration`
- Внешние интеграции и их контрактные границы.

2) `interface`
- Интерфейс, шаблоны и пользовательские сценарии.

3) `data`
- Модели, контракты данных и migrations, если они объявлены plan.

4) `tooling`
- Скрипты, документация и инструменты разработки.

5) `research`
- Исследования и процессные утилиты, не смешанные с выбранной продуктовой работой.

## Create worktrees (пример)

Идея: 1 worktree = 1 долговременная ветка темы (или рабочая копия объявленного base ref под тему).

**EXAMPLE:** выбранный project может объявить `.worktrees/<topic>` как directory и `codex/<topic>` как family branch names; это не общая policy. Подставь объявленные `<worktree-dir>`, `<topic>`, `<branch-name>` и `<base-ref>`.

```bash
git worktree add <worktree-dir>/<topic> -b <branch-name> <base-ref>
```

## Plan discovery (как быстро найти нужное)

1) Подключать ничего не нужно: хелперы не попадают в shell, каждая команда
ниже — отдельный вызов фасада из корня worktree. Список команд:

```bash
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_help
```

2) Список активных plan (не Done/не Superseded):

```bash
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_plan_list
```

3) Фильтр по keywords из выбранного project/plan (OR; любое из слов):

```bash
# <topic>; keywords из выбранного project/plan
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_plan_list <keyword-1> <keyword-2> <keyword-3>
```

4) По статусу (когда нужно “снять очередь”):

```bash
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_plan_list_status "ready for planner"
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_plan_list_status "architect initial draft" <keyword>
```

5) Закрепить текущий plan за worktree (удобно для wrappers/role sessions):

```bash
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_plan_set "docs/plans/YYMMDD_HHMM_topic.md"
tail -n 1 .planveyor.planpath
```

## Follow-ups (не плодить планы)

Рекомендация:
- follow-ups живут в `docs/followups/*` (master backlog по темам + docs/followups/index.md),
- планы заводим только под “реальную работу” (или review-only), а не как хранилище задач.

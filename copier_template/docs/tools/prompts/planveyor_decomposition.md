---
description: "Manager: запустить decomposition wave"
argument-hint: "[PLAN_PATH] [TASK_TEXT]"
---

[ALWAYS START]
Запусти decomposition wave для выбранного проекта. Этот slash prompt остаётся
тонким entrypoint и не заменяет Manager pipeline.

### Self-Planveyor

Public entrypoint: ./bin/planveyor из physical Planveyor root.

### Sibling

Public entrypoint: `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD"`.

Helper contract: planveyor_decomposition_init [PLAN_PATH].
Manager contract: docs/tools/prompts/manager_collab_pipeline.md.
Preferred command: MANAGER_CMD=decomposition [PLAN_PATH] [-- <raw Owner intake>].

## Границы

- Helper принимает только plan path выбранного project. Repo-relative path или
  absolute path допустимы только если после normalisation они остаются внутри
  этого project.
- Не редактируй .planveyor.* вручную, не создавай child plans из prose и не
  выбирай target по существованию файла.
- Non-zero helper result, malformed output или inactive phase markers остаются
  blocker. Не продолжай через cached plan path.
- Init даёт bootstrap framing, не child-execution readiness. Контур готов
  только когда child carriers и declared proof lanes materialized.
- Этот prompt не запускает nested runtime, не ставит queue автоматически и не
  выполняет product code.

## Аргументы

Разбери Slash args так:

1. Первый token, выглядящий как docs/plans/*.md или absolute .md path, передай
   helper как candidate PLAN_PATH.
2. Остальной текст передай Manager/Architect как verbatim Owner intake.
3. Если plan path не указан, передай helper без path. Helper сам валидирует
   admissibility; внешний вид token не является разрешением.

## Выполнение

1. Выбери ровно один маршрут:
   - self-Planveyor: cwd — physical Planveyor root;
   - sibling: cwd — выбранный sibling, а `PLANVEYOR_RUNTIME_ROOT` указывает на внешний physical Planveyor checkout.
2. Запусти соответствующую команду:

   Self-Planveyor:

~~~bash
./bin/planveyor planveyor_decomposition_init [PLAN_PATH]
~~~

   Sibling:

~~~bash
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_decomposition_init [PLAN_PATH]
~~~

3. Прочитай output. При успехе открой prepared plan и проверь:

- plan_meta.phase_overlay = "decomposition_wave";
- plan_meta.phase_state = "active".

4. Продолжи в текущем диалоге как Manager с:

- ROLE=Manager;
- PLAN_PATH=<prepared plan path>;
- PRE_STATUS_LINE=<prepared status line>;
- MANAGER_CMD=decomposition <prepared plan path>, либо MANAGER_CMD=run после
  успешного init;
- Owner decomposition intake только если он был передан verbatim.

5. Если нет intake и active plan не содержит постановки задачи, верни
   Next: Owner с коротким запросом исходной формулировки. Не выдумывай задачу.

## Stop conditions

- Неподдерживаемый plan path, missing helper, unavailable facade или
  unavailable Manager runtime — конкретный blocker до continuation.
- Absence/mismatch phase markers — blocker, не fallback на обычный Manager run.
- Вопросы, child ideas и scaffold сами по себе не означают completion.
- Target-local dependencies, harness или provider readiness остаются declared
  consumer facts; generic prompt не подставляет им значения.

## Ответ

Не возвращай только summary после init. Нормальный результат — Manager
decomposition wave до первого штатного stop condition:

- Next: ...;
- Open items: ...;
- prepared plan path/status, если stop наступил до первого role dispatch.
[/ALWAYS START]

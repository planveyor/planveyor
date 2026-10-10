# MCP и target-local проверки

MCP и browser/native tools дополняют declared verification contract выбранного
проекта. Они не создают универсальный UI, framework или credentials policy.

## Выбор инструмента

1. Прочитай PLAN_PATH и target-local canon.
2. Выбери только tool/harness, который там объявлен для текущего scope.
3. Если UI/runtime lane не объявлен, запиши N/A (why=not declared); не
   подставляй browser, native helper, database или framework command.
4. Запускай Planveyor functions через public facade:

~~~bash
./bin/planveyor planveyor_verify [--format json] [--full | --module …]
~~~

Без флагов это быстрый integrity route. `--full` добавляет одну canonical unittest discovery и взаимоисключён с `--module`; facade передаёт argv без собственной ветки.

Facade проверяет собственный runtime. Target application command, credential и
test fixture принадлежат target project.

## UI evidence

Для declared UI lane зафиксируй:

- exact scenario и preconditions;
- chosen browser/native helper;
- command/result или readable receipt;
- complete visual artifact set;
- human verdict и finding disposition.

Automation result и human inspection независимы. Один screenshot не доказывает
полный UI contract, а успешный command не закрывает visual lane без declared
verdict.

## Ограничения среды

Если selected harness требует browser, network, device, local service или
elevated execution, сначала получи truthful runtime result. Недоступный
environment — blocker или diagnostic по target contract; не заменяй его
другим стеком и не invent credentials.

Не сохраняй credentials, cookies, authorization headers, session identifiers,
tokens или personal paths в plan, receipt, review artifact или screenshot
metadata. Используй <REDACTED>.

## MCP boundaries

MCP tool output — supporting evidence, пока plan/review не указывает его
роль в решении. Не принимай tool availability, chat prose или historical log
как proof current behavior. Сохраняй только необходимые public facts:
selected tool, declared target scope, result and stable artifact reference.

## Closeout

После UI/MCP lane:

1. Добавь result к role-owned review или plan evidence.
2. Перепроверь declared gate для exact changed bundle.
3. Если shared process docs изменились, обработай packetization отдельно.
4. Остановись на missing evidence; не выполняй target mutation, queue write,
   commit или push только ради завершения proof lane.


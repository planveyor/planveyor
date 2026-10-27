<!-- i18n: pair=docs/guides/harnesses.md pair-sha256=901297e5eaebc0ed8f1afdf8f9df6973af7f633ec8161aa9980b7ecf1783838f self-sha256=9a2db67322921b11ea6f27e3d8bd61f862e5a6fed4c504754cd77b4aa33fb156 -->
# Агентные харнесы

[English](harnesses.md) · **Русский**

Агентный харнес — программа, которая работает вокруг модели и ведёт сессию роли: читает и правит файлы, запускает команды, держит песочницу. Примеры агентных харнесов — Codex CLI, Claude Code и ZCode. Агентный харнес — не обвязка стека: обвязкой называются скрипты вашего проекта, которые собирают его, выкладывают в dev-среду и запускают тесты стека.

Агентный харнес вы устанавливаете, настраиваете и авторизуете сами. Planveyor запускает его с вашей конфигурацией и эту конфигурацию не создаёт и не меняет.

## Поддержка в первой версии

| Маршрут | Агентный харнес |
| --- | --- |
| Sibling, режим TUI: окно Manager `planveyor sibling tui` | Codex CLI |
| Sibling, ручной режим в консоли: `planveyor sibling architect` и `planveyor sibling run` | Codex CLI |
| Режим collab: `planveyor_manager_collab_tui`, `planveyor_manager_collab_cmd` | Codex CLI |
| Отдельный запуск роли и пошаговый режим Manager | Codex CLI; Claude Code для Planner и обеих линий Reviewer |
| Прямой маршрут Manager в ZCode | ZCode, только в корне Planveyor |
| Чат со скиллом плана в sibling | Codex (`$planveyor-plan-draft`) или ZCode (`/planveyor-plan-draft`) |

Других агентных харнесов первая версия не поддерживает. Поддержку мы будем расширять после выпуска.

## Codex CLI

Codex CLI ведёт оба режима sibling; пути работы у них разные, см. [«Два режима работы с планом»](stack-sibling.ru.md#два-режима-работы-с-планом).

- **Режим TUI.** `planveyor sibling tui` открывает интерактивное окно Codex CLI с Manager на весь план; внутри вызывается `planveyor_manager_collab_tui`. Роли — вложенные субагенты Codex этой сессии и живут, пока открыто окно. Вложенные субагенты в интерактивном окне — возможность Codex CLI.
- **Ручной режим в консоли.** `planveyor sibling architect` запускает Architect в его собственной сессии, отдельным `codex exec`. Каждый `planveyor sibling run` — один неинтерактивный ход режима collab: Manager поднимает пять ролей агентами Codex и выходит после принятой приёмки.

Planveyor передаёт Codex каталог Codex home из `PLANVEYOR_CODEX_HOME` или, если переменная не задана, `~/.codex`. Если команды `codex` нет в `PATH`, команда роли останавливается с сообщением `Codex CLI is required; install it and authenticate in the consumer-owned home first`.

Настройки описаны в разделе [«Настройка Codex»](launch-and-role-modes.ru.md#настройка-codex) руководства запуска. Его части перечислены в [последнем разделе](#что-вы-настраиваете) этой страницы.

## Claude Code и выбор харнеса для роли

Planveyor хранит выбор агентного харнеса для роли как runner этой роли. Задаёт выбор команда `planveyor_runner_set <role> <runner>`. Допустимы такие пары:

| Роль | Runner |
| --- | --- |
| Architect, Coder, Manager | `codex` |
| Planner, Reviewer | `codex` или `claude` |

По умолчанию у каждой роли `codex`. Обе линии Reviewer берут выбор роли `reviewer`. Выбор сохраняется в `.planveyor.runner.<role>` в корне проекта и действует только для этой копии. Показывает его команда `planveyor_runner <role>`:

```zsh
./bin/planveyor planveyor_runner_set planner claude
./bin/planveyor planveyor_runner planner
```

Для sibling передайте `--project /absolute/path/to/sibling` до команды, как в разделе [«Выбор проекта»](launch-and-role-modes.ru.md#выбор-проекта).

Выбор действует там, где роль запускает обёртка: при отдельном запуске роли и в пошаговом режиме Manager. Агентов Codex в режиме collab он не меняет и Claude Code ни в один из режимов sibling не добавляет: в первой версии Claude Code работает только для Planner и Reviewer, при отдельном запуске роли и в пошаговом режиме Manager.

Для Claude Code нужны установленный CLI и его обычный вход. Planveyor читает три переменные:

- `PLANVEYOR_CLAUDE_COMMAND` — имя команды или абсолютный путь, по умолчанию `claude`;
- `PLANVEYOR_CLAUDE_MODEL` — передаётся в Claude Code как `--model`;
- `PLANVEYOR_CLAUDE_EFFORT` — передаётся как `--effort`.

Planveyor запускает Claude Code с `--permission-mode acceptEdits`. Остальные разрешения берутся из настроек Claude Code, оттуда же берётся модель, если `PLANVEYOR_CLAUDE_MODEL` не задана. Если команда не найдена, роль останавливается с сообщением `Claude CLI is unavailable; configure the consumer provider first`.

## ZCode

У ZCode свой маршрут Manager, и работает он только в сессии ZCode, открытой в физическом корне Planveyor (Self-Planveyor). Маршруту служат два файла корня: `.zcode/commands/manager-init.md` даёт команду `/manager-init`, а `.zcode/agents/planveyor-role-agent.md` описывает агента роли. `/manager-init` готовит сессию как Manager, и следующее сообщение `MANAGER_CMD=run <PLAN_PATH>` запускает работу по плану. Правила транспорта — в надстройке [`docs/tools/prompts/zcode/manager_pipeline.md`](../tools/prompts/zcode/manager_pipeline.md) (англ.). Контракт Manager остаётся тем же, что в режиме collab. Сама надстройка записывает `live_zcode_state=not_run`: живой прогон ZCode она не подтверждает.

Файлы `.zcode/` в sibling не доставляются, поэтому там этот маршрут не поддержан, и Manager в sibling запускают через фасад. В sibling ZCode подходит для обычного чата со скиллом `/planveyor-plan-draft`. Команда `planveyor_runner_set` не принимает ZCode как runner. Planveyor не задаёт ни модель, ни вход ZCode.

## Что вы настраиваете

Codex CLI — по разделам руководства запуска:

- вход в выбранном Codex home и, если нужно, отдельный Codex home для Planveyor: [«Оговорка: окружение Codex попадает в роли»](launch-and-role-modes.ru.md#оговорка-окружение-codex-попадает-в-роли);
- модель и уровень рассуждения сессий: [«Обычный режим ролей»](launch-and-role-modes.ru.md#обычный-режим-ролей) и [«Модель и уровень рассуждения»](launch-and-role-modes.ru.md#модель-и-уровень-рассуждения);
- пять ролей `[agents.*]` для режима collab: [«Режим collab: роли `[agents.*]`»](launch-and-role-modes.ru.md#режим-collab-роли-agents);
- проектный каталог `.codex/` и доверие к папке проекта: [«Проектный каталог `.codex/`»](launch-and-role-modes.ru.md#проектный-каталог-codex);
- сеть в песочнице ролей: [«Доступ к dev-среде»](launch-and-role-modes.ru.md#доступ-к-dev-среде); песочница чата Codex, который выполняет команды за вас: [«Один раз: среда и создание проекта»](stack-sibling.ru.md#один-раз-среда-и-создание-проекта);
- проверка фактических моделей: [«Проверка фактических моделей»](launch-and-role-modes.ru.md#проверка-фактических-моделей).

Claude Code: вход и разрешения в самом Claude Code и три переменные `PLANVEYOR_CLAUDE_*` из [раздела выше](#claude-code-и-выбор-харнеса-для-роли). Роли `[agents.*]` ему не нужны. Проверка моделей из руководства запуска читает только сессии Codex.

ZCode: файлы маршрута уже лежат в корне Planveyor.

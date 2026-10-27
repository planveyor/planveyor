<!-- i18n: pair=docs/guides/launch-and-role-modes.md pair-sha256=092a1400a999176fa61297b8225dec236dd32d36e8cec8a659f344b25d334812 self-sha256=66beb4ce4151ff52b1b1cab5cefaa19d26c9ce62c0bfd592623dbb7b4e217472 -->
# Запуск и режимы ролей

[English](launch-and-role-modes.md) · **Русский**

Planveyor запускается из своего физического корня через фасад, который выполняет команды только в дочернем процессе. Фасад не подключается к оболочке вызывающего процесса и не меняет её функции, переменные и рабочий каталог.

До первой публичной команды проверьте, что доступен `git`, Planveyor лежит в физической копии Git-репозитория и `HEAD` указывает на коммит. Фасад выполняет эту предварительную проверку до разбора `--project` и до `planveyor_entry_doctor`. Doctor не может восстановить или обойти среду Git, которая эту проверку не прошла.

## Выбор проекта

Без `--project` команда работает с самим Planveyor. Чтобы работать с проектом, передайте его абсолютный канонический путь **до** публичной команды:

```zsh
./bin/planveyor --project /absolute/path/to/consumer \
  planveyor_plan_status_oracle --json docs/plans/<plan>.md
```

У выбранного проекта уже должны быть свой объявленный контракт и подготовленная среда (bootstrap). `--project` только выбирает контекст проекта. Он не создаёт ни контракт, ни план, ни SID, ни интерпретатор, ни аутентификацию, ни готовность провайдера.

Фасад запускает чистый дочерний процесс в корне выбранного проекта. Относительные пути в команде отсчитываются от этого проекта. Родительская оболочка не меняется, поэтому каждому новому вызову снова нужен свой префикс `--project`. `bin/planveyor` запускает дочерний процесс через `env -i` и `zsh -df`: унаследованный `CODEX_HOME` и необъявленные переменные других инструментов отбрасываются, но непустой `CODEX_THREAD_ID` явно передаётся для записи происхождения плана. Owner может явно передать канонический внешний путь в `PLANVEYOR_CODEX_HOME`. Фасад проверяет положение `PLANVEYOR_CODEX_HOME` и `PLANVEYOR_STATE_ROOT` вне дерева файлов Planveyor; для `HOME` он требует только абсолютный путь к существующему каталогу. Храните аутентификацию и состояние клиента вне дерева файлов Planveyor.

В корне выбранного проекта остаются игнорируемые артефакты процесса: указатели `.planveyor.planpath` и `.planveyor.session.*`, записи режима collab `.planveyor.collab.*`, квитанции инициализации `.planveyor.init_runs/` и временный каталог `.tmp/`. Это не учётные данные, но при копировании или переписывании истории проекта их нужно сохранять отдельно.

## Быстрое чтение состояния

```zsh
./bin/planveyor planveyor_entry_doctor
./bin/planveyor planveyor_runtime_info
./bin/planveyor planveyor_help
```

Эти команды только читают локальное состояние копии Planveyor и проекта и готовность к запуску не проверяют. Они не доказывают ни аутентификацию, ни доступность провайдера, ни допустимость плана, ни SID, ни вызов ролей через Manager, ни запуск роли.

### Поддерживаемая среда

Первая версия поддерживает одну среду: macOS и активированное окружение Python 3.12, где стоят Copier 9.18.2 и PyYAML в версиях из `requirements-dev.lock` (например, conda-окружение `planveyor`). Активируйте его до запуска ролей и проверок. Фасад выбирает первый совместимый Python 3.10–3.12 через `PATH`, проверяя по очереди `python3`, `python`, `python3.12`, `python3.11` и `python3.10`; вспомогательные скрипты используют выбранный интерпретатор. Локальный файл проекта `.planveyor.pybin` исполняемый файл не выбирает. Planveyor не устанавливает и не чинит зависимости. Если предпосылки нет, команда завершается и сообщает, что именно нужно. Загрузчик идентичности исходников (source identity) технически принимает Python 3.10–3.12, но поддерживаемый путь — среда, описанная выше. Настроенный агентный харнес и его обычная внешняя аутентификация нужны живой команде, которая вызывает этот харнес. Codex и аутентификация Codex относятся только к путям через Codex. `planveyor_entry_doctor`, `planveyor_runtime_info` и `planveyor_help` их не проверяют. Аутентификация остаётся в обычной среде клиента, которым вы пользуетесь. Planveyor не копирует в репозиторий данные учётной записи, токены и локальную конфигурацию.

Для работы ролей есть ещё два условия. Codex выполняет команды ролей в login shell, который читает ваш профиль оболочки и может поставить первым в `PATH` другой Python. Planveyor передаёт ролям свой интерпретатор через `PYBIN`, поэтому его вспомогательных скриптов это не касается. Но скрипты проекта, например обвязка sibling, могут вызывать голый `python3`, поэтому Python 3.12 должен стоять первым в `PATH` и в login shell. `TMPDIR` должен указывать на существующий каталог вне любого Git-репозитория. Если `TMPDIR` лежит внутри Git-репозитория, тесты движка, которым нужен корень проекта без Git, пропускаются. Проверьте оба условия до первого запуска ролей:

```zsh
zsh -lc 'python3 --version'
[ -n "$TMPDIR" ] && [ -d "$TMPDIR" ] && echo 'TMPDIR на месте'
git -C "$TMPDIR" rev-parse --is-inside-work-tree
```

Первая команда должна напечатать Python 3.12, а последняя — отказать с `fatal: not a git repository`. Как поставить Python 3.12 первым в login shell, решаете вы, например порядком `PATH` в `~/.zprofile`. Planveyor настройки оболочки не меняет.

## Контракт sibling

Для создания sibling нужны пустой новый каталог и полный коммит исходного Planveyor. Copier записывает в файл ответов публичный адрес репозитория Planveyor, но шаблон всегда берёт из локальной копии Planveyor, из которой запущена команда: адрес подменяется только в окружении процесса Copier. Поэтому выбранный коммит должен лежать на ветке или теге этой копии, а переход sibling на новую версию начинается с обновления этой копии. Движок и его скрипты остаются во внешней копии Planveyor.

```zsh
./bin/planveyor planveyor_consumer_init /absolute/path/to/new-sibling --source-commit <full-40-hex> \
  --author-name "Your Name" --author-email you@example.invalid
./bin/planveyor --project /absolute/path/to/new-sibling planveyor_consumer_doctor
```

Инициализация создаёт в sibling первый коммит. `--author-name` и `--author-email` задают его автора и передаются только вместе. Имя и адрес автора из конфигурации Git и переменных окружения не используются. Без этих флагов автором коммита становится служебный `Planveyor Initializer <planveyor-init@example.invalid>`, и команда сообщает об этом строкой в stderr.

После изменения общего контракта или движка выберите новый полный коммит. Обновление переносит файлы в отдельном кандидате обновления и проверяет маркер, ответы Copier, управляемые пути и локальные разделы. Затем оно создаёт внутри sibling план обновления со стартовым статусом Architect. Сам перенос этот план не закрывает и роли не запускает.

В выводе `sibling upgrade` этот же план называется «план адаптации» или «adaptation plan». В руководстве он назван «планом обновления», чтобы отличать его от первого плана адаптации нового sibling под стек.

Роли получают `PLANVEYOR_RUNTIME_ROOT` и вызывают объявленные вспомогательные скрипты на Python через `planveyor_runtime_py` того же фасада. Так сохраняется проверенная привязка к копии Planveyor, из которой идут команды (runtime pin). Прямой вызов файла `scripts/<helper>.py` из sibling допуск по полномочиям (authority admission) не проходит.

```zsh
./bin/planveyor --project /absolute/path/to/sibling planveyor_contract_upgrade --source-commit <new-full-40-hex>
```

Низкоуровневая команда `planveyor_contract_upgrade` из примера выводит JSON прямо в stdout. При успехе в нём есть поля `backup`, `plan`, `notices` и `warnings`. Если команда остановилась с кандидатом, в JSON будут поля `candidate`, `problems` и `resolution`, а код выхода — 3. При такой остановке исходный sibling остаётся на месте, резервная копия и план ещё не созданы. Команда `planveyor sibling upgrade` перехватывает этот JSON. При успехе она печатает пути к резервной копии и плану обновления, а извещения отдельно не выводит. При коде 3 она скрывает JSON из stdout с кандидатом и проблемами, а stderr остаётся видимым. Кандидат лежит рядом с sibling в `.<name>-upgrade-<first 12 characters of the new commit>`. Повторный запуск того же `sibling upgrade` назовёт точный путь: `candidate path already exists: …`.

В кандидате разберите возникшие конфликты, файлы `.rej` и изменения локальных разделов. Проверьте точный diff и то, что правила стека и локальное переопределение для Reviewer сохранились. После ревью закоммитьте результат в кандидате и явно примите его с тем же коммитом Planveyor:

```zsh
./bin/planveyor --project /absolute/path/to/sibling planveyor_contract_upgrade --source-commit <new-full-40-hex> --accept-candidate
```

Перед следующим обновлением проверьте локальный план и закоммитьте его вместе с другими принятыми изменениями sibling. Doctor сообщает, если коммит копии Planveyor, из которой идут команды, не совпадает с коммитом контракта. Обновить совместимый старый контракт с API 5 до текущего коммита это не мешает. До `Copier update` обновление отказывает, если диапазон одновременно удаляет и добавляет управляемые пути, байты или права удаляемого файла отличаются от старого результата шаблона, в удаляемом файле есть защищённый локальный раздел либо управляемого пути нет в sibling. Простое удаление неизменённого файла без защищённых разделов может дойти до Copier и остановиться с кандидатом обновления. Проверьте и закоммитьте этого кандидата, затем повторите вызов с `--accept-candidate`.

## Пример: Self-Planveyor

Без `--project` фасад выбирает физический корень самого Planveyor. Пример показывает подготовку и явный выбор плана, но не доказывает, что роли выполнены.

1. Owner выбирает поддерживаемый Python в доверенном окружении запуска:

   ```zsh
   ./bin/planveyor planveyor_plan_status_oracle --json docs/plans/<plan>.md
   ```

   Oracle читает только явно переданный путь к плану. Он не обращается к `.planveyor.planpath`, не выбирает активный план и не запускает ни Manager, ни очередь.

2. Owner отдельно выбирает план для дальнейших шагов процесса:

   ```zsh
   ./bin/planveyor planveyor_plan_set docs/plans/<plan>.md
   ./bin/planveyor planveyor_planpath
   ```

   `planveyor_plan_set` сохраняет путь как есть в локальный файл корня `.planveyor.planpath` и в локальный журнал `.planveyor.planpath.log`. Этот шаг закрепляет выбор плана в процессе и не служит технической проверкой полномочий роли. Сначала проверьте существующий путь через Oracle и только после успешной проверки сохраняйте указатель. Последующий вызов `planveyor_planpath` только читает последнюю сохранённую непустую строку. Он не проверяет, что путь существует, и не создаёт ни очередь, ни жизненный цикл. Если указателя нет, команда предлагает `planveyor_plan_set <PLAN_PATH>`. Пустой указатель даёт `Empty file: <path>` с кодом 1. Нечитаемый обычный файл указателя после ошибки чтения оболочки попадает в то же сообщение; отдельной диагностики вспомогательного скрипта для него нет.

3. Manager инициализируют отдельным шагом:

   ```zsh
   ./bin/planveyor planveyor_manager_init
   ```

   Эта команда создаёт сессию Manager. Если SID Manager нет, восстановление указывает на ту же `planveyor_manager_init`. Подготовка интерпретатора, Oracle, который только читает план, выбор плана и чтение указателя сами по себе не доказывают запуск ролей через Manager.

   Перед TUI включите в сессии запросы одобрения команд: выполните `./bin/planveyor planveyor_manager_resume`, введите `/permissions`, выберите «Ask for approval» и выйдите, как в главе [«Как Planveyor меняет себя»](learn/self-development.ru.md#изменение-в-самом-planveyor).

4. Обычный TUI режима native/collab запускается без `--q`:

   ```zsh
   ./bin/planveyor planveyor_manager_collab_tui
   ```

   Это живой путь Manager: после успешных предварительных проверок он передаёт `MANAGER_CMD=run`. Сам вызов ролей остаётся условным результатом этого запуска. `planveyor_manager_collab_cmd run docs/plans/<plan>.md` — альтернативный разовый живой путь, а не обязательный следующий шаг после TUI.

   До первого вызова ролей по записям `followups` можно явно продолжить один активный цикл обычного плана `plan.v2`, если четыре сборщика записей `general` прошли успешно:

   ```zsh
   ./bin/planveyor planveyor_manager_collab_cmd run docs/plans/<plan>.md --followups-capture-cycle-id <UUIDv4>
   ```

   Это разовый путь с уже заведённым SID Manager. План и UUID задаются явно, указатель и очередь не меняются. Допуск к закрытию документов вычисляется заново и проверяет смысловую идентичность плана в терминальном статусе, исходники, квитанции, карты объектов и изменения в Git. Если контрольная точка уже есть, её сохранённый JSON перед публикацией проверяется ещё раз. Затем выполняются только записи `followups` для Architect → Coder → Planner → Reviewer. Если цикл уже продвинулся, заблокирован или неоднозначен либо найдено расхождение, команда останавливается: нового `begin` и автоматической инициализации не будет. Допуск не заменяет итоговое доказательство закрытия.

5. Очередь — отдельный расширенный маршрут: сначала создайте очередь, затем запускайте TUI очереди или разовую команду.

   ```zsh
   ./bin/planveyor planveyor_q_set docs/plans/<plan>.md --for-manager-mode manager-collab
   ./bin/planveyor planveyor_manager_collab_tui --q
   # либо
   ./bin/planveyor planveyor_manager_collab_cmd run Q
   ```

Аутентификация и необязательный `PLANVEYOR_CODEX_HOME` остаются во внешнем окружении. Локальные указатели в корне — это не учётные данные, не внешний каталог настроек клиента и не профиль `target-local`. Профили `default` и `planveyor` читают общий корпус из корня. `target-local` возможен только по объявленному контракту sibling, без скрытого запасного варианта.

## Роли и входы

Роль читает текущий явно выбранный план, связанные документы контракта и свой промпт. Общий порядок работы: Architect → Planner → Coder → Reviewer → приёмка Architect → закрытие. При `COMMIT_POLICY=native_existing` закрытие выполняет Architect. В `planveyor sibling architect` и `run` действует `COMMIT_POLICY=human_explicit`: закрытие выполняет отдельная команда `planveyor sibling close --commit` после просмотра. Manager в TUI работает с `native_existing` и через `planveyor_manager_collab_tui`, и в sibling через `planveyor sibling tui`, которая его вызывает. План остаётся источником истины о статусе и следующем допустимом шаге.

| Задача | Команда |
| --- | --- |
| Инициализировать Manager | `./bin/planveyor planveyor_manager_init` |
| Запустить Manager в режиме collab для одного плана в живом TUI | `./bin/planveyor planveyor_manager_collab_tui` |
| Разово выполнить очередь в режиме collab | `./bin/planveyor planveyor_manager_collab_cmd run Q` |
| Открыть TUI пошагового режима Manager | `./bin/planveyor planveyor_manager_custom_pipeline_tui --no-alt-screen` |
| Разово выполнить очередь в пошаговом режиме Manager | `./bin/planveyor planveyor_manager_custom_pipeline_cmd run Q` |
| Продолжить сессию Manager | `./bin/planveyor planveyor_manager_resume` |

Таблица показывает команды для корня Planveyor, где движок и проект — одна копия репозитория. Если команды идут из одной копии Planveyor, а проект — другая копия, передавайте `--project <проект>` каждой команде, и в Self-Planveyor тоже: без него низкоуровневая команда возьмёт проектом сам движок, из какого бы каталога её ни вызвали.

В sibling то же окно Manager — это режим TUI, основной путь [руководства по sibling](stack-sibling.ru.md#два-режима-работы-с-планом). Передайте sibling низкоуровневым командам через `--project`, выполните `planveyor_manager_init`, включите в сессии запросы одобрения команд, как описано в руководстве, и затем откройте окно командой `planveyor sibling tui`; между этими шагами не меняйте файлы и индекс. `planveyor sibling tui` проверяет выбранный план и сессию и вызывает `planveyor_manager_collab_tui`. Роли — вложенные субагенты сессии Manager и сохраняют память, пока окно открыто. После коммита `planveyor sibling run` и `planveyor sibling tui` сами заводят нового Manager с новыми ролями; `tui` заводит новую сессию без запросов одобрения команд, поэтому сначала заведите новую сессию сами и включите в ней запросы одобрения команд. Запущенные напрямую `planveyor_manager_collab_tui` и `planveyor_manager_collab_cmd` отказывают с `receipt_authority_mismatch`, и продолжить работу можно только новой сессией. В корне Planveyor сессия к HEAD не привязана, и прежнюю сессию можно продолжить. Отдельные команды `planveyor sibling …` — ручной режим в консоли того же руководства.

Чтобы возобновить отдельную роль, используйте её явную команду из `planveyor_help`, например `planveyor_arch_resume`, `planveyor_planner_resume`, `planveyor_coder_resume`, `planveyor_reviewer_resume`, `planveyor_reviewer_code_risk_resume` или `planveyor_reviewer_code_contracts_resume`.

Пошаговому режиму Manager (custom pipeline) нужны отдельные SID для Manager и пяти линий ролей:

```zsh
planveyor_manager_init
planveyor_arch_init
planveyor_planner_init
planveyor_coder_init
planveyor_reviewer_code_risk_init
planveyor_reviewer_code_contracts_init
```

`planveyor_reviewer_init` не заменяет ни `planveyor_reviewer_code_risk_init`, ни `planveyor_reviewer_code_contracts_init`. TUI пошагового режима — тоже живой путь наблюдения и вызова ролей. Он не доказывает, что запустится каждая роль.

`planveyor_manager_init` выбирает допустимый режим до вызова ролей. Manager не переключает молча режим, агентный харнес, проект или план из-за очереди или старого состояния сессии. Прямой маршрут Manager в ZCode описан в `docs/tools/prompts/zcode/manager_pipeline.md` (англ.). Это транспортная надстройка: она сохраняет точки входа пошагового режима (Custom), режима native/collab, возобновления (resume), TUI и команд. В первой версии маршрут работает только в корне Planveyor: его стартовые файлы из `.zcode/` в sibling не доставляются, и в sibling этот маршрут не поддержан.

## Настройка Codex

Оба поддерживаемых режима sibling работают через Codex CLI: режим TUI (`planveyor sibling tui`, которая вызывает `planveyor_manager_collab_tui`) и ручной режим в консоли (`planveyor sibling architect` и `planveyor sibling run`). В режиме TUI и в `run` Manager поднимает пять агентов Codex в режиме native/collab. Planveyor запускает Codex с Codex home из `PLANVEYOR_CODEX_HOME`, а если переменная не задана, — с `~/.codex` и берёт настройки из `config.toml` этого каталога. В доверенном проекте Codex применяет и проектный каталог `.codex/`, см. раздел [«Проектный каталог `.codex/`»](#проектный-каталог-codex). Сам Planveyor эти файлы не создаёт и не меняет: всё, что описано ниже, настраиваете вы.

При отдельном запуске ролей и в пошаговом режиме Manager действует уже сделанный выбор агентного харнеса: Planner и обе линии Reviewer допускают `claude`, а Architect, Coder и Manager — `codex`. Выбор задаётся командой `planveyor_runner_set <role> <runner>`, и обе линии Reviewer берут выбор роли `reviewer`. Для Claude нужны установленный CLI и его обычная внешняя аутентификация. Команду, модель и уровень рассуждения задают `PLANVEYOR_CLAUDE_COMMAND`, `PLANVEYOR_CLAUDE_MODEL` и `PLANVEYOR_CLAUDE_EFFORT`. Этот выбор не меняет агентов Codex в режиме collab и не добавляет в `sibling run` транспорт Claude.

### Обычный режим ролей

При отдельном запуске ролей (`planveyor_arch`, `planveyor_planner`, `planveyor_coder`, `planveyor_reviewer`) и в пошаговом режиме Manager роли работают в сессиях, которые открывают команды `*_init`. Такую же сессию для Architect открывает и `planveyor sibling architect`. С агентным харнесом `codex` каждая такая сессия — отдельный `codex exec`, и модель Planveyor по умолчанию не выбирает. Модель и уровень рассуждения берутся из верхнего уровня `config.toml`:

```toml
model = "gpt-6.1-sol"
model_reasoning_effort = "ultra"
```

Уровень задавайте явно: у `gpt-6.1-sol` по умолчанию `low`. Роли `[agents.*]` этому режиму не нужны.

### Режим collab: роли `[agents.*]`

Режим collab (`planveyor_manager_collab_tui`, `planveyor_manager_collab_cmd`) нужен и владельцу, который ведёт роли вручную: через него идут закрытие документов плана и волны декомпозиции и анализа. Сам Manager — главная сессия Codex на модели из верхнего уровня `config.toml`. Роли он поднимает агентами Codex: `spawn_agent(..., agent_type=<type>)`. Промпт Manager запрашивает следующие пять значений `agent_type`. До запуска этого маршрута объявите их как роли `[agents.<name>]` в конфигурации Codex:

| `agent_type` | Кого поднимает Manager |
|---|---|
| `architect` | Architect |
| `planner` | Planner |
| `coder` | Coder |
| `reviewer_code_risk` | Reviewer, линия рисков |
| `reviewer_code_contracts` | Reviewer, линия контракта |

Режим merge (`planveyor_manager_collab_tui --merge`) поднимает те же роли, кроме `planner`.

Роли и сами могут поднимать встроенных агентов, например `explorer`. Чтобы и эти агенты работали на выбранной вами модели, добавьте записи для `default`, `worker` и `explorer` в том же формате.

У роли два поля: `description` и `config_file` — путь к файлу роли. Относительный путь отсчитывается от каталога этого `config.toml`, и файл должен существовать. В файле роли задаются `model` и `model_reasoning_effort`. `developer_instructions` не обязательны: задачу и промпт роли (`PROMPT_FILE`) Manager передаёт сообщением.

Manager держит пять потоков ролей открытыми весь запуск. Задайте `max_concurrent_threads_per_session` не меньше 6. По умолчанию Codex может разрешать меньше, и главный поток тоже может входить в этот лимит. Если лимита не хватит, Manager остановится с `collab thread limit reached`. Роли тоже могут поднимать встроенных агентов, поэтому оставьте запас сверх этого минимума. Инструменты Codex для работы нескольких агентов должны быть включены (`[agents] enabled`, по умолчанию `true`), иначе Manager остановится с `Codex collab is disabled/unavailable`.

Нейтральный пример `config.toml` в Codex home:

```toml
model = "gpt-6.1-sol"
model_reasoning_effort = "ultra"

[agents]
enabled = true
max_concurrent_threads_per_session = 6

[agents.architect]
description = "Planveyor Architect"
config_file = "agents/architect.toml"

[agents.planner]
description = "Planveyor Planner"
config_file = "agents/planner.toml"

[agents.coder]
description = "Planveyor Coder"
config_file = "agents/coder.toml"

[agents.reviewer_code_risk]
description = "Planveyor Reviewer, risk lane"
config_file = "agents/reviewer_code_risk.toml"

[agents.reviewer_code_contracts]
description = "Planveyor Reviewer, contracts lane"
config_file = "agents/reviewer_code_contracts.toml"

[agents.default]
description = "Codex default agent"
config_file = "agents/default.toml"

[agents.worker]
description = "Codex worker agent"
config_file = "agents/worker.toml"

[agents.explorer]
description = "Codex explorer agent"
config_file = "agents/explorer.toml"
```

Файл роли `agents/architect.toml` лежит в подкаталоге `agents/` рядом с `config.toml`. Остальные семь файлов используют тот же формат, со своими `name` и `description`:

```toml
name = "architect"
description = "Planveyor Architect"
model = "gpt-6.1-sol"
model_reasoning_effort = "ultra"
```

### Модель и уровень рассуждения

Рекомендация по умолчанию — GPT-6.1 Sol (`gpt-6.1-sol`) с уровнем `ultra` или `max`, не ниже `xhigh`, для каждой сессии конвейера. Каждая сессия берёт модель из своего места:

| Сессия | Модель и уровень |
| --- | --- |
| Architect в `planveyor sibling architect`; отдельный запуск ролей и пошаговый режим Manager с агентным харнесом `codex` | Верхний уровень `config.toml` |
| Manager в режиме TUI, в `planveyor sibling run` и в других запусках режима collab | Верхний уровень `config.toml` |
| Пять ролей, которых поднимает Manager | Их файлы ролей `[agents.<agent_type>]` |
| Встроенные агенты, которых поднимают роли | Файлы ролей `[agents.default]`, `[agents.worker]` и `[agents.explorer]` |
| Скилл `$planveyor-plan-draft` | Модель вашего чата |

Другую модель для отдельной роли задают в её файле.

### Проектный каталог `.codex/`

Модели для одного проекта можно задать в его собственном каталоге `.codex/`: `.codex/config.toml` в корне проекта и файлы ролей в `.codex/agents/`, в том же формате, что выше. Codex применяет этот каталог только в доверенном проекте. Интерактивный Codex при первом запуске в новой папке спрашивает, доверять ли ей, и сохраняет ответ в `config.toml` того Codex home, с которым работает этот чат. Роли видят этот ответ, только если работают с тем же Codex home. Для сессий этого проекта значения из проектного файла перекрывают значения Codex home. То, чего проектный файл не задаёт, например сеть, берётся из Codex home.

Шаблон sibling этот каталог не игнорирует. Исключите его из Git локальным правилом, которое в коммиты не попадает. Команды выполняются из корня проекта:

```zsh
mkdir -p .codex/agents
printf '%s\n' '.codex/' >> "$(git rev-parse --git-path info/exclude)"
```

Planveyor этот каталог не создаёт.

### Проверка фактических моделей

Имя роли модель не доказывает. Codex записывает каждую сессию в файл `rollout-*.jsonl` в каталоге `sessions/` своего Codex home. Запись `session_meta` хранит каталог запуска, источник и роль агента. Записи `turn_context` хранят модель и уровень каждого хода. Это локальные файлы самого Codex, другие инструменты для проверки не нужны.

Перед первым запуском ролей, например `planveyor sibling architect`, `run` или окна Manager, отметьте время:

```zsh
touch "$TMPDIR/planveyor-models.start"
```

Во время работы команды или после неё выполните из корня проекта:

```zsh
python3 -I - "$(pwd -P)" "${PLANVEYOR_CODEX_HOME:-$HOME/.codex}/sessions" "$TMPDIR/planveyor-models.start" <<'PY'
import json, pathlib, sys
from datetime import datetime

project, sessions, marker = sys.argv[1], pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3])
start = marker.stat().st_mtime
for path in sorted(sessions.rglob("rollout-*.jsonl")):
    if path.stat().st_mtime < start:
        continue
    meta, seen = None, set()
    with path.open(encoding="utf-8", errors="replace") as lines:
        for line in lines:
            try:
                item = json.loads(line)
            except ValueError:
                continue
            payload = item.get("payload") or {}
            if item.get("type") == "session_meta" and meta is None:
                meta = payload
            elif item.get("type") == "turn_context":
                try:
                    turn_time = datetime.fromisoformat(item.get("timestamp", "").replace("Z", "+00:00"))
                except (TypeError, ValueError, AttributeError):
                    continue
                if turn_time.tzinfo is not None and turn_time.timestamp() >= start:
                    seen.add(f"{payload.get('model')} / {payload.get('effort')}")
    if meta and meta.get("cwd") == project and seen:
        role = meta.get("agent_role") or ("main" if meta.get("source") == "exec" else "chat")
        print(role, ", ".join(sorted(seen)))
PY
```

Скрипт печатает по строке на сессию этого проекта: роль, модель и уровень. Содержимое сессий он не выводит. Строка `main` — основная сессия `codex exec` в этом проекте. Planveyor использует её для Architect в `planveyor sibling architect`, Manager в `planveyor sibling run` или отдельной роли. Сама метка не доказывает запуск через Planveyor. Роли и встроенные агенты названы по `agent_type`. Строка `chat` — ваш интерактивный чат в этой папке, у него своя модель.

Проверка нужна потому, что настройки Codex home действуют, даже если о них забыли. Например, запись `[agents.architect]`, сделанная раньше для другого проекта, молча задаёт Architect свою модель. Если модель расходится с вашей настройкой, остановитесь и исправьте настройку сами. Вероятная причина — проектный `.codex/`, который Codex не применил, потому что папка не доверена.

### Имена задач Manager

Manager создаёт агентов под постоянными именами: `/root/architect_sol_xhigh_v2`, `/root/planner_terra_ultra_v2`, `/root/coder_terra_ultra_v2`, `/root/reviewer_code_risk_sol_xhigh_v2`, `/root/reviewer_code_contracts_sol_xhigh_v2`. Части `sol`, `terra`, `xhigh` и `ultra` повторяют модели, на которых маршрут отлаживали, но это только имена: модель и уровень задают роли `[agents.*]`. Менять имена не нужно: движок принимает только их.

### Оговорка: окружение Codex попадает в роли

Manager и роли используют выбранный Codex home (`PLANVEYOR_CODEX_HOME`, а без него — `~/.codex`). В наблюдавшихся прогонах Codex глобальные инструкции, включённая память и пользовательские скиллы влияли на контекст ролей. Поиск этих данных — поведение Codex, а не гарантия, которую проверяет Planveyor. Перед запуском проверьте выбранный каталог настроек и пользовательские скиллы: правила и память, написанные для других проектов, могут менять поведение ролей.

Чтобы отделить их, заведите для Planveyor отдельный Codex home: создайте каталог вне копии Planveyor, войдите в Codex с ним (`CODEX_HOME=<directory> codex login`), положите туда `config.toml` по примеру выше и экспортируйте путь в `PLANVEYOR_CODEX_HOME` в оболочке, из которой вызываете фасад. Сеть для ролей тогда включается в конфигурации этого каталога.

### Доступ к dev-среде

Выберите в анкете стека один из вариантов по [существующему контракту dev-среды](../_template_stack_brief.md): роли с сетью в песочнице или живые команды, которые выполняет человек. Если живые цели запускают сами роли, сеть в их песочнице — обязательная предпосылка. Владелец включает её до первого `run` в `config.toml` выбранного Codex home:

```toml
[sandbox_workspace_write]
network_access = true
```

Настройка действует на песочницу `workspace-write` этого Codex home, файловая система остаётся в песочнице. Роли вызывают принятые команды стека, а те до записи проверяют dev-цель и права. Секреты читает только обвязка. Если живые команды выполняет только оператор, роль передаёт конкретную команду, а человек возвращает её фактический результат. Сеть, Codex home и окружение Planveyor автоматически не настраивает.

## Границы копии Planveyor, из которой идут команды

- Используйте фасад для запуска, инициализации, возобновления и TUI.
- Вызывайте вспомогательный скрипт напрямую, только если текущий план или руководство явно называет его проверкой, которая только читает состояние.
- Не выдавайте результат статического линтера, чтение промпта или доступность провайдера за доказательство настоящего запуска ролей через Manager.
- Контракты `target-local` должны быть явно объявлены выбранным проектом и планом. Общий корпус `default`/`planveyor` не подставляет скрытый профиль продукта.

Следующие рабочие шаги описаны в [lifecycle-and-packets.md](lifecycle-and-packets.ru.md).

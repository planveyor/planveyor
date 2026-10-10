# Запуск и режимы ролей

Planveyor запускается из своего физического корня через child-only facade. Он не подключается в shell вызывающего процесса и не меняет его функции, переменные или working directory.

До первого public command проверьте доступный `git`, physical Planveyor Git checkout и `HEAD`, разрешающийся в commit. Facade выполняет этот preflight до разбора `--project` и до `planveyor_entry_doctor`; doctor не может восстановить или обойти failed Git runtime.

## Выбор проекта

Без `--project` команда работает с самим Planveyor. Для consumer repository передай абсолютный canonical path **до** public command:

```zsh
./bin/planveyor --project /absolute/path/to/consumer \
  planveyor_plan_status_oracle --json docs/plans/<plan>.md
```

Выбранный consumer уже должен владеть своим declared contract и bootstrap. `--project` выбирает только consumer-контекст: он не создаёт contract, plan, SID, interpreter, authentication или provider readiness.

Facade запускает чистый child process в выбранном project root. Relative paths в команде относятся к этому проекту; parent shell не меняется, поэтому каждый новый вызов снова получает свой `--project` prefix. `bin/planveyor` запускает child через `env -i` и `zsh -df`, поэтому inherited `CODEX_HOME` и переменные другого tooling-окружения в него не попадают. Owner может явно передать canonical external `PLANVEYOR_CODEX_HOME`; `HOME`, аутентификация, client state и `PLANVEYOR_STATE_ROOT` остаются вне product tree.

В выбранном project root остаются ignored process artifacts: selectors `.planveyor.planpath` и `.planveyor.session.*`, collab records `.planveyor.collab.*`, init receipts `.planveyor.init_runs/` и временные `.tmp/`. Они не являются credentials, но требуют отдельного сохранения при копировании или переписывании project history.

## Быстрый readback

```zsh
./bin/planveyor planveyor_entry_doctor
./bin/planveyor planveyor_runtime_info
./bin/planveyor planveyor_help
```

Это local runtime/project readback, а не readiness gate: он не доказывает authentication, provider availability, plan admissibility, SID, Manager dispatch или запуск role.

Первая версия поддерживает одну среду: macOS и активированное Python-окружение с Python 3.12, Copier 9.18.2 и PyYAML по `requirements-dev.lock` (например, conda-окружение `planveyor`). Активируй его до role или validation work: facade и его helpers берут `python3` из `PATH` этого окружения, а project-local `.planveyor.pybin` не выбирает executable. Planveyor не устанавливает и не чинит зависимости; при отсутствующей предпосылке команда завершается с сообщением, что именно нужно. Загрузчик source identity технически принимает Python 3.10–3.12, но поддерживаемый путь — среда выше. Настроенный клиент и его обычная внешняя аутентификация нужны live-команде, вызывающей этот клиент; Codex и Codex-аутентификация относятся только к Codex-путям. Doctor, runtime info и help их не проверяют. Аутентификация остаётся в обычной среде используемого клиента; Planveyor не копирует account data, tokens или local configuration в репозиторий.

## Контракт sibling

Создание требует пустой новой директории и полного Git commit исходного Planveyor. В answers Copier записывает публичный source URL, но шаблон всегда берёт из локального checkout Planveyor, из которого запущена команда: адрес подменяется только в окружении процесса Copier. Поэтому выбранный commit должен лежать на ветке или теге этого checkout, а новая версия для sibling начинается с обновления checkout. Runtime и его scripts остаются во внешнем checkout.

```zsh
./bin/planveyor planveyor_consumer_init /absolute/path/to/new-sibling --source-commit <full-40-hex> \
  --author-name "Your Name" --author-email you@example.invalid
./bin/planveyor --project /absolute/path/to/new-sibling planveyor_consumer_doctor
```

Init создаёт в sibling первый commit. `--author-name` и `--author-email` задают его автора и передаются только вместе; Git identity из конфигурации и переменных окружения не используется. Без флагов commit подписывается служебным автором `Planveyor Initializer <planveyor-init@example.invalid>`, и init сообщает об этом строкой в stderr.

После изменения общего контракта или движка выбери новый полный commit. Upgrade переносит файлы в отдельном кандидате, проверяет marker, answers, managed paths и локальные секции, затем создаёт внутри sibling план адаптации со стартовым статусом Architect. Сам перенос не закрывает этот план и не запускает роли.

Роли получают `PLANVEYOR_RUNTIME_ROOT` и вызывают объявленные Python helpers через `planveyor_runtime_py` того же facade. Это сохраняет проверенный runtime pin; прямой вызов файла `scripts/<helper>.py` из sibling не проходит authority admission.

```zsh
./bin/planveyor --project /absolute/path/to/sibling planveyor_contract_upgrade --source-commit <new-full-40-hex>
```

Показанный низкоуровневый `planveyor_contract_upgrade` возвращает JSON напрямую в stdout: при успехе — поля `backup`, `plan`, `notices` и `warnings`; при остановке с кандидатом — `candidate`, `problems` и `resolution`, с кодом 3. При такой остановке исходный sibling остаётся на месте, backup и план ещё не созданы. Команда `planveyor sibling upgrade` захватывает этот JSON: при успехе печатает пути backup и плана адаптации, а извещения отдельно не выводит; при коде 3 скрывает JSON stdout с кандидатом и проблемами, тогда как stderr остаётся видимым. Кандидат находится рядом с sibling в `.<имя>-upgrade-<12 знаков нового коммита>`; повторный запуск того же `sibling upgrade` назовёт точный путь: `candidate path already exists: …`.

Разбери фактические конфликты, файлы `.rej` и изменения локальных секций в кандидате, проверь точный diff, сохранность правил стека и Reviewer override. После review закоммить результат в кандидате и явно прими его тем же source commit:

```zsh
./bin/planveyor --project /absolute/path/to/sibling planveyor_contract_upgrade --source-commit <new-full-40-hex> --accept-candidate
```

Перед новым переходом проверь локальный план, закоммить его и другие принятые изменения sibling. Doctor сообщает несовпадение runtime и contract commits; это не запрещает upgrade совместимого старого API 5 контракта к текущему commit. Исчезнувший или переименованный managed path требует отдельной миграции и останавливает команду до Copier.

## Пример: self-Planveyor

Без `--project` child-only facade выбирает физический root самого Planveyor. Это
пример подготовки и явного выбора plan, а не доказательство выполнения ролей.

1. Owner выбирает supported Python в доверенном окружении запуска:

   ```zsh
   ./bin/planveyor planveyor_plan_status_oracle --json docs/plans/<plan>.md
   ```

   Oracle
   читает только явно переданный plan path: он не обращается к
   `.planveyor.planpath`, не выбирает active plan и не запускает Manager или
   очередь.

2. Owner отдельно выбирает plan для последующих process steps:

   ```zsh
   ./bin/planveyor planveyor_plan_set docs/plans/<plan>.md
   ./bin/planveyor planveyor_planpath
   ```

   `planveyor_plan_set` сохраняет raw path в root-local
   `.planveyor.planpath` и local log `.planveyor.planpath.log`. Это process
   ownership выбора plan, а не технический role-authorization gate. Сначала
   передайте существующий path успешному oracle, затем сохраняйте pointer.
   Последующая `planveyor_planpath` только читает сохранённую последнюю непустую
   строку; она не проверяет существование path и не materialize-ит queue или
   lifecycle. При отсутствии pointer она предлагает
   `planveyor_plan_set <PLAN_PATH>`; empty и unreadable pointer остаются
   отдельными local failures.

3. Инициализацию Manager выполняют отдельным шагом:

   ```zsh
   ./bin/planveyor planveyor_manager_init
   ```

   Эта команда создаёт Manager session. При отсутствии Manager SID recovery
   указывает на ту же `planveyor_manager_init`. Подготовка interpreter,
   read-only oracle, выбор plan и readback pointer сами по себе не доказывают
   Manager-to-role execution.

4. Обычный native/collab TUI запускается без `--q`:

   ```zsh
   ./bin/planveyor planveyor_manager_collab_tui
   ```

   Это live Manager path: после успешных preflight gates он передаёт
   `MANAGER_CMD=run`. Фактический dispatch остаётся conditional result этого
   запуска. `planveyor_manager_collab_cmd run docs/plans/<plan>.md` —
   альтернативный one-shot live path, а не следующий обязательный шаг после
   TUI.

   До первого followups dispatch можно явно продолжить один active ordinary
   `plan.v2` cycle после четырёх green general collectors:

   ```zsh
   ./bin/planveyor planveyor_manager_collab_cmd run docs/plans/<plan>.md --followups-capture-cycle-id <UUIDv4>
   ```

   Это one-shot путь с existing Manager SID. План и UUID задаются явно;
   pointer и queue не меняются. Fresh docs-closeout admission проверяет
   terminal semantic identity, source, receipts, object maps и Git delta.
   Existing checkpoint повторно проверяет retained JSON перед publication;
   затем выполняются только Architect → Coder → Planner → Reviewer followups.
   Progressed/blocked/ambiguous cycle или drift дают bounded stop без нового
   `begin` и автоматического init. Допуск не заменяет final closeout proof.

5. Queue — отдельный advanced branch: сначала materialize очередь, затем
   запускайте queue TUI или existing one-shot command.

   ```zsh
   ./bin/planveyor planveyor_q_set docs/plans/<plan>.md --for-manager-mode manager-collab
   ./bin/planveyor planveyor_manager_collab_tui --q
   # либо
   ./bin/planveyor planveyor_manager_collab_cmd run Q
   ```

Аутентификация и optional `PLANVEYOR_CODEX_HOME` остаются во внешнем
окружении. Root-local pointers не являются credentials, внешним home или
target-local profile. Профили `default` и `planveyor` читают shared root corpus;
`target-local` возможен только по объявленному consumer contract без hidden
fallback.

## Роли и входы

Роль читает текущий explicit plan, связанные contract docs и собственный prompt. Общий порядок работы: Architect → Planner → Coder → Reviewer → Architect acceptance → closeout. При `COMMIT_POLICY=native_existing` closeout выполняет Architect; в `planveyor sibling architect` и `run` действует `COMMIT_POLICY=human_explicit`, и closeout выполняет отдельный `planveyor sibling close --commit` после preview. План остаётся source of truth для статуса и следующего допустимого шага.

| Задача | Команда |
| --- | --- |
| Инициализировать Manager | `./bin/planveyor planveyor_manager_init` |
| Запустить single-plan Manager collab в live TUI | `./bin/planveyor planveyor_manager_collab_tui` |
| Выполнить collab queue one-shot | `./bin/planveyor planveyor_manager_collab_cmd run Q` |
| Открыть custom-pipeline TUI | `./bin/planveyor planveyor_manager_custom_pipeline_tui --no-alt-screen` |
| Выполнить custom queue one-shot | `./bin/planveyor planveyor_manager_custom_pipeline_cmd run Q` |
| Продолжить Manager session | `./bin/planveyor planveyor_manager_resume` |

Для individual role resume используй explicit command из `planveyor_help`, например `planveyor_arch_resume`, `planveyor_planner_resume`, `planveyor_coder_resume`, `planveyor_reviewer_resume`, `planveyor_reviewer_code_risk_resume` или `planveyor_reviewer_code_contracts_resume`.

Custom pipeline требует отдельные SID Manager и пяти role lanes:

```zsh
planveyor_manager_init
planveyor_arch_init
planveyor_planner_init
planveyor_coder_init
planveyor_reviewer_code_risk_init
planveyor_reviewer_code_contracts_init
```

`planveyor_reviewer_init` не заменяет ни `planveyor_reviewer_code_risk_init`, ни `planveyor_reviewer_code_contracts_init`. Custom TUI тоже является live supervision/dispatch path и не доказывает, что каждая role будет запущена.

`planveyor_manager_init` выбирает допустимый mode до dispatch. Manager не переключает mode, runner, project или plan молча из-за очереди либо старого session state. Direct ZCode Manager route описан в `docs/tools/prompts/zcode/manager_pipeline.md`; это transport overlay, который сохраняет Custom, native/collab, resume, TUI и command entrypoints. В первой версии он работает только в корне Planveyor: его bootstrap-файлы из `.zcode/` в sibling не доставляются, и в sibling этот route не поддержан.

## Настройка Codex

Поддерживаемый sibling route (`planveyor sibling architect` и `planveyor sibling run`) использует Codex CLI; `run` поднимает пять native Codex-субагентов. Planveyor запускает Codex с home из `PLANVEYOR_CODEX_HOME`, а если переменная не задана, — с `~/.codex` и берёт настройки из `config.toml` этого каталога. Сам Planveyor этот файл не создаёт и не меняет: всё, что описано ниже, настраиваете вы.

Отдельный запуск ролей и custom pipeline сохраняют существующий выбор runner: Planner и обе линии Reviewer допускают `claude`, Architect, Coder и Manager — `codex`. Выбор задаётся через `planveyor_runner_set <роль> <клиент>`; обе линии Reviewer используют выбор роли `reviewer`. Для Claude нужны установленный CLI и его обычная внешняя аутентификация; команду, модель и уровень задают `PLANVEYOR_CLAUDE_COMMAND`, `PLANVEYOR_CLAUDE_MODEL` и `PLANVEYOR_CLAUDE_EFFORT`. Этот выбор не меняет Codex-субагентов collab и не добавляет Claude transport к `sibling run`.

### Обычный режим ролей

Роли по одной (`planveyor_arch`, `planveyor_planner`, `planveyor_coder`, `planveyor_reviewer`) и custom pipeline работают в сессиях, которые открывают `*_init`. При runner `codex` каждая такая сессия — отдельный `codex exec`, модель Planveyor по умолчанию не выбирает. Модель и уровень рассуждения берутся из верхнего уровня `config.toml`:

```toml
model = "gpt-6.1-sol"
model_reasoning_effort = "ultra"
```

Уровень задавайте явно: у `gpt-6.1-sol` по умолчанию `low`. Роли `[agents.*]` этому режиму не нужны.

### Manager collab: роли `[agents.*]`

Manager collab (`planveyor_manager_collab_tui`, `planveyor_manager_collab_cmd`) нужен и владельцу, который ведёт роли вручную: через него закрываются документы плана и идут волны декомпозиции и анализа. Сам Manager — главная сессия Codex на модели из верхнего уровня `config.toml`. Роли он поднимает субагентами Codex: `spawn_agent(..., agent_type=<тип>)`. Codex ищет тип среди ролей `[agents.<имя>]` конфига; кроме них он знает только встроенные `default`, `worker` и `explorer`, а на другое имя отвечает ошибкой `unknown agent_type`. Поэтому в `config.toml` нужны пять ролей ровно с такими именами:

| `agent_type` | Кого поднимает Manager |
|---|---|
| `architect` | Architect |
| `planner` | Planner |
| `coder` | Coder |
| `reviewer_code_risk` | Reviewer, линия рисков |
| `reviewer_code_contracts` | Reviewer, линия контрактов |

Режим merge (`planveyor_manager_collab_tui --merge`) поднимает те же роли, кроме `planner`.

У роли два поля: `description` и `config_file` — путь к файлу роли. Относительный путь отсчитывается от каталога этого `config.toml`, файл должен существовать. В файле роли задаются `model` и `model_reasoning_effort`. `developer_instructions` не обязательны: задачу и промпт роли (`PROMPT_FILE`) Manager передаёт сообщением.

Manager держит пять потоков ролей открытыми весь запуск. Задайте `max_concurrent_threads_per_session` не меньше 6: по умолчанию Codex может разрешать меньше, а главный поток может входить в этот лимит. Если лимита не хватит, Manager остановится с `collab thread limit reached`. Мультиагентные инструменты Codex должны быть включены (`[agents] enabled`, по умолчанию `true`), иначе Manager остановится с `Codex collab is disabled/unavailable`.

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
```

Файл роли `agents/architect.toml` рядом с `config.toml`; остальные четыре такие же, со своими `name` и `description`:

```toml
name = "architect"
description = "Planveyor Architect"
model = "gpt-6.1-sol"
model_reasoning_effort = "ultra"
```

### Модель и уровень рассуждения

Рекомендация по умолчанию — GPT-6.1 Sol (`gpt-6.1-sol`) с уровнем `ultra` или `max`, не ниже `xhigh`, и для Manager, и для всех пяти ролей. Другую модель отдельной роли задают в её файле.

### Имена задач Manager

Manager создаёт субагентов под постоянными именами: `/root/architect_sol_xhigh_v2`, `/root/planner_terra_ultra_v2`, `/root/coder_terra_ultra_v2`, `/root/reviewer_code_risk_sol_xhigh_v2`, `/root/reviewer_code_contracts_sol_xhigh_v2`. Части `sol`, `terra`, `xhigh` и `ultra` повторяют модели, на которых маршрут отлаживали, но это только имена: модель и уровень задают роли `[agents.*]`. Менять имена не нужно, движок принимает только их.

### Оговорка: окружение Codex попадает в роли

Manager и роли работают в вашем Codex home со всей его настройкой. Codex добавляет в каждую сессию глобальный `AGENTS.md` из этого каталога (`~/.codex/AGENTS.md`) рядом с `AGENTS.md` проекта. Если в Codex включена память (`memories`), Manager читает её из `~/.codex/memories`. Пользовательские скиллы из `~/.agents/skills` видны при любом Codex home. Правила и память, написанные для других проектов, могут менять поведение ролей.

Чтобы отделить их, заведите для Planveyor отдельный Codex home: создайте каталог вне checkout Planveyor, войдите в Codex с ним (`CODEX_HOME=<каталог> codex login`), положите туда `config.toml` по примеру выше и экспортируйте путь в `PLANVEYOR_CODEX_HOME` в shell, из которого вызываете facade. Сеть для ролей тогда включается в конфиге этого каталога.

### Доступ к dev-среде

Выберите в анкете стека роли с сетью в песочнице или выполнение живых команд человеком по [существующему контракту dev-среды](../_template_stack_brief.md). Для Codex-сценария сеть задаётся владельцем в `config.toml` выбранного home: `network_access = true` в секции `[sandbox_workspace_write]`. Она действует на workspace-write песочницу этого home; файловая система остаётся в песочнице. Роли вызывают принятые команды стека, которые проверяют dev-цель и права до записи; секреты читает только обвязка. В operator-only варианте роль передаёт конкретную команду, а человек возвращает её фактический результат. Planveyor сеть, home и окружение автоматически не настраивает.

## Границы runtime

- Используй facade для launch, init, resume и TUI.
- Запускай direct helper только когда текущий plan или guide явно называет его read-only проверкой.
- Не объявляй static lint, prompt readback или provider availability доказательством реального Manager-to-role запуска.
- Target-local contracts должны быть явно объявлены выбранным consumer и plan; shared `default`/`planveyor` corpus не подставляет скрытый product profile.

Следующие operational steps находятся в [lifecycle-and-packets.md](lifecycle-and-packets.md).

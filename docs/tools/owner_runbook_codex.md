# Owner runbook: role sessions Planveyor

Этот документ — публичный operating guide для checkout Planveyor. Он описывает переносимую lifecycle и оставляет consumer repositories их credentials, project-specific tests и local automation.

## Публичный launcher

Planveyor запускается через child-only facade. Не подключайте implementation shell files в parent shell.

До первого public command проверьте доступный `git`, physical Planveyor Git checkout и `HEAD`, разрешающийся в commit. Facade делает этот preflight до `--project` и до doctor; `planveyor_entry_doctor` не может восстановить или обойти failed Git runtime.

Из физического корня Planveyor начните с:

```zsh
./bin/planveyor planveyor_entry_doctor
./bin/planveyor planveyor_runtime_info
./bin/planveyor planveyor_help
```

Это local runtime/project readback, а не launch readiness: он не доказывает authentication, provider availability, admissibility plan, SID, dispatch Manager или запуск role.

Facade определяет свой root по `bin/planveyor`. Совместимый с Planveyor Python 3.10–3.12 executable нужен для загрузки source identity. Настроенный клиент и его обычная внешняя аутентификация нужны live-команде, вызывающей этот клиент; Codex и Codex-аутентификация относятся только к Codex-путям. Doctor, runtime info и help их не проверяют. Перед role или validation work выберите совместимый Python 3.10–3.12 через доверенное окружение запуска; facade и helpers используют его, а project-local `.planveyor.pybin` не выбирает executable. `bin/planveyor` запускает child через `env -i` и `zsh -df`, поэтому inherited `CODEX_HOME` и переменные другого tooling-окружения не передаются. `PLANVEYOR_CODEX_HOME` допустим только когда оператор явно задаёт canonical внешний путь вне product tree; `HOME`, authentication, client state и `PLANVEYOR_STATE_ROOT` остаются внешними.

В выбранном project root ignored selectors `.planveyor.planpath` и `.planveyor.session.*`, collab records `.planveyor.collab.*`, init receipts `.planveyor.init_runs/` и временные `.tmp/` остаются local process artifacts. Это не credentials и не внешний client home, но их нужно отдельно сохранять при переносе или переписывании project history.

## Явно выберите project и work

Вызов без `--project` работает с самим Planveyor. Для consumer project передайте `--project` до public command и используйте absolute canonical directory:

```zsh
./bin/planveyor --project /absolute/path/to/consumer \
  planveyor_plan_status_oracle --json docs/plans/YYYYMMDD_HHMM_topic.md
./bin/planveyor --project /absolute/path/to/consumer \
  planveyor_plan_set docs/plans/YYYYMMDD_HHMM_topic.md
./bin/planveyor --project /absolute/path/to/consumer \
  planveyor_planpath
```

Facade меняет directory только у чистого child process и задаёт project root только для этого вызова. Relative paths разрешаются внутри выбранного project; parent shell не меняется, и каждый новый вызов снова требует prefix `--project`. Для Planveyor-maintenance можно использовать форму без prefix: external client `HOME`/authentication/state и явно заданный `PLANVEYOR_CODEX_HOME` остаются вне product tree, а ignored selectors, collab records и receipts принадлежат выбранному project root.

У запуска Planveyor есть один active target и, для planning work, один explicit plan path. Не выводите plan из filename, предыдущей session или prose mention. Сначала убедитесь, что existing exact path успешно проходит oracle, затем сохраняйте pointer. `planveyor_planpath` доказывает только local selection: при отсутствии pointer он предлагает `planveyor_plan_set <PLAN_PATH>`, но pointer сам по себе не доказывает readiness или lifecycle admission. Зелёный static check, historical receipt или завершённая role session сами по себе не доказывают, что current bytes проходят следующий lifecycle gate.

Перед изменением consumer target прочитайте его contribution instructions и prerequisites. Target tests запускаются из target checkout; Planveyor их не заменяет.


## Подготовка собственного проекта

Для нового consumer-проекта сначала создайте или выберите его checkout средствами самого проекта. В его документации зафиксируйте contribution instructions, runtime bootstrap, service prerequisites, test/validation commands и владение credentials. Затем выберите совместимый с Planveyor Python 3.10–3.12 в доверенном окружении запуска до role или validation work. Передавайте absolute project path через `--project` перед public command; Python выбирается окружением запуска, а не файлом sibling.

## Адаптация к стеку consumer

Planveyor сохраняет lifecycle, evidence и handoff discipline, а language, framework, local services, migrations и target-specific checks определяет consumer repository. Перед execution запишите эти prerequisites в consumer plan или documentation, убедитесь, что доверенное окружение запуска предоставляет совместимый Python 3.10–3.12, и запускайте target validation из consumer checkout. Не переносите target-local configuration или credentials в product tree Planveyor.
## Режимы role и Manager

Planveyor поддерживает individual role sessions и Manager-led collaboration. Concrete command set установленной версии показывает `planveyor_help`.

```zsh
./bin/planveyor planveyor_manager_init
./bin/planveyor planveyor_manager_collab_tui
./bin/planveyor planveyor_manager_custom_pipeline_tui --no-alt-screen
./bin/planveyor planveyor_manager_resume
```

Перед обычным TUI подготовьте supported interpreter, успешный oracle для existing plan, pointer и Manager SID в этом порядке. При отсутствии SID recovery указывает на `planveyor_manager_init`. `planveyor_manager_collab_tui` без `--q` — live single-plan path: после успешных gates он передаёт `MANAGER_CMD=run`; фактический dispatch остаётся conditional result. `planveyor_manager_collab_cmd run <PLAN_PATH>` — альтернативный one-shot live path, а не следующий обязательный шаг после TUI.

Queue — отдельный advanced branch: после `planveyor_q_set <PLAN_PATH> --for-manager-mode manager-collab` используйте явный queue entrypoint:

```zsh
./bin/planveyor planveyor_manager_collab_tui --q
# либо
./bin/planveyor planveyor_manager_collab_cmd run Q
./bin/planveyor planveyor_manager_custom_pipeline_cmd run Q
```

Не создавайте `--queue` alias.

Для custom pipeline нужны отдельные SID Manager, Architect, Planner, Coder, `reviewer_code_risk` и `reviewer_code_contracts`: `planveyor_manager_init`, `planveyor_arch_init`, `planveyor_planner_init`, `planveyor_coder_init`, `planveyor_reviewer_code_risk_init`, `planveyor_reviewer_code_contracts_init`. Generic `planveyor_reviewer_init` не заменяет specialized reviewer lanes. Custom TUI — live supervision/dispatch path и не доказывает запуск каждой role.

Для individual role resume используйте role-specific `*_resume` command из `planveyor_help`. TUI и one-shot `*_cmd` — два public входа в выбранный mode; не воспроизводите pipeline algorithm в ad-hoc shell chain.

Direct ZCode Manager route описан в `docs/tools/prompts/zcode/manager_pipeline.md`. Это transport overlay: он сохраняет Custom, native/collab, resume, TUI и command entrypoints, а не заменяет их.

Обычный role cycle:

1. Выберите project и explicit plan.
2. Инициализируйте role или Manager session, указанную в help.
3. Передайте role только bounded task, current evidence и expected artifact.
4. Прочитайте artifact и направьте его declared status следующей допустимой role или gate.
5. Создайте новый receipt, если изменились plan, target revision или intended scope.

Owner выбирает operating mode и любой runner, доступный установленному runtime. Manager может координировать выбранные roles, но не меняет молча Owner-controlled runner, authentication source, project или plan.

## Init-run artifacts

Для диагностики init runtime сохраняет локальное состояние в выбранном checkout. `.planveyor.init_runs/by_sid/<SID>/` содержит `run.log` и `meta.json` после привязки session, а `.planveyor.init_runs/pending/<role>/<run_id>/` сохраняет те же файлы для попытки до привязки SID. `.planveyor.session.<role>` — только attach pointer; он не доказывает, что init или role run завершился успешно.

Этот init capture не охватывает `resume`, live `tee`, split `stdout/stderr` или interactive TTY adoption. Для этого нужны отдельные current evidence и applicable lifecycle gate.

## Bounded handoffs

Каждый handoff должен назвать:

- plan path и project root;
- exact files или revision range под review;
- expected output artifact;
- gate, который выбирает следующий шаг; и
- одного допустимого следующего owner, если gate проходит или блокирует.

После material changes читайте fresh status readback. Prose summary role полезен как context, но plan, review, validation output и packet metadata остаются durable handoff records.

## Lifecycle plan, review и closeout

Planveyor сохраняет plan-first lifecycle:

1. Architect или Planner создаёт bounded plan по repository templates.
2. Plan lint-ится, а его status проверяется до execution.
3. Coder меняет только authorized target scope и сообщает validation.
4. Reviewer оценивает current range и пишет findings или acceptance evidence.
5. Нужная CENSOR или follow-up работа закрывается explicit plan или accepted exception.
6. После merge выполняются post-merge checks target и создаются fresh documentation, follow-up и packet records, если они нужны.

Для executable plan проверьте exact bundle перед final handoff, если установленный runtime даёт этот gate:

```zsh
./bin/planveyor --project /absolute/path/to/consumer \
  planveyor_plan_bundle --preflight docs/plans/YYYYMMDD_HHMM_topic.md
./bin/planveyor --project /absolute/path/to/consumer \
  planveyor_plan_bundle --check docs/plans/YYYYMMDD_HHMM_topic.md
```

`--preflight` проверяет proposed bundle до review. `--check` оценивает completed bundle. Ни один из них не заменяет target tests, review current diff или обязательный semantic acceptance artifact.

## Queue discipline

Manager queue — это explicit ordered list plan paths. Materialize или inspect его через installed queue commands до того, как просить Manager его выполнить. Не вызывайте bare queue sentinel, не используйте старую queue после изменения plan и не считайте scratch file queue truth.

Если queued plan блокируется, остановитесь на указанном gate. Исправьте или замените plan, проверьте новый artifact, затем осознанно обновите queue.

## Review ranges и post-merge work

Review и post-merge evidence обязаны называть exact range или revision, которые они покрывают. Запишите base и head до создания review или packet. Повторите applicable checks, если range изменился.

Post-merge work обычно включает:

- target tests и нужный documentation lint;
- review/follow-up triage с concrete owner;
- process-improvement promotion только когда его evidence current; и
- packetization, если работа должна перейти между repositories.

Repository templates в `docs/reviews/`, `docs/followups/` и `docs/process_improvements/` определяют durable carrier formats. Generated summaries — derived views; пересобирайте их из current source artifacts, а не редактируйте руками timestamps или historical rows.

## Rollout packets

Rollout packet передаёт scoped work из source repository в target repository. Это не profile, credential или remote-execution mechanism.

Создавайте packet только когда известны source target, target repository и relevant plan. Разделяйте source и target roles: source публикует adoption request, а target записывает собственные local adoption evidence и outcome.

```zsh
./bin/planveyor planveyor_rollout_packet_create <target-repo> <topic-slug> \
  --source-plan docs/plans/<source>.md --target-kind plan_adoption
./bin/planveyor planveyor_rollout_packet_show docs/rollout_packets/<packet>.md
./bin/planveyor planveyor_rollout_packet_import_instructions \
  docs/rollout_packets/<packet>.md --print-target-plan-seed
```

Нормальный порядок delivery: consumer materialize-ит target-local adoption plan/import receipt, затем записывает одно outcome в выбранном consumer project через public facade:

```zsh
./bin/planveyor --project /absolute/path/to/consumer \
  planveyor_rollout_packet_outcome_set \
  --target-plan docs/plans/<target-adoption>.md --packet-id <id> \
  --packet-path docs/rollout_packets/<packet>.md --outcome <canonical-or-alias>
```

Эта запись меняет только target-local structured carrier. Затем source фиксирует отдельный receipt:

```zsh
./bin/planveyor planveyor_rollout_packet_ack \
  --packet docs/rollout_packets/<packet>.md --status imported \
  --target-plan docs/plans/<target-adoption>.md
```

ACK materialize-ит pointer на `docs/plans/<target-adoption>.md`, но сам по себе не доказывает готовый target outcome и может оставить packet в состоянии ожидания outcome.

Используйте `planveyor_rollout_packet_inbox`, `planveyor_rollout_packet_adoption_plan`, `planveyor_rollout_packet_query`, `planveyor_rollout_packet_reconcile` и `planveyor_rollout_packet_lint` для inspection current carrier state. Держите packet paths source-local и используйте generic `<target-repo>` identifiers в templates.

Для upstream requests используйте installed `planveyor_upstream_request_show`, `planveyor_upstream_request_import`, `planveyor_upstream_request_ack` и `planveyor_upstream_request_query`. ACK записывает receipt и не утверждает, что target merged или accepted change.

Report/reuse gate читает exact range без изменения packet:

```zsh
./bin/planveyor planveyor_post_merge_packetization_gate --range BASE..HEAD
```

Для recovery или restamp specific source-local packet назовите его явно:

```zsh
./bin/planveyor planveyor_post_merge_packetization_gate_recover \
  --range BASE..HEAD --packet docs/rollout_packets/<packet>.md \
  --source-plan docs/plans/<source>.md --stage-packets
```

`--range` обязателен для recovery. `--source-plan` — optional provenance, а recovery принимает repeated `--packet`. Gate без named packet — report/reuse path; это не packet update.

## Target-local boundaries

Planveyor несёт public `default` и `planveyor` source profiles. `target-local` profile, target-specific role prompt, integration credential или project policy принадлежат consumer repository. Если их нет или они не читаются там, остановитесь с clear blocker, а не создавайте local substitute.

Эта граница также относится к authentication, local shell configuration, editor setup, browsers, database access и external services. Держите их вне product tree Planveyor и документируйте в consumer repository, когда они нужны target work.

## Troubleshooting

1. Запустите `planveyor_entry_doctor` и `planveyor_runtime_info` из Planveyor root.
2. Прочитайте `planveyor_help` для installed command contract.
3. Проверьте, что selected project, plan path, review range и packet path explicit.
4. Повторите smallest read-only status, lint или oracle command, который объясняет blocker.
5. Исправьте только named prerequisite, затем создайте fresh receipt перед продолжением.

Не решайте runtime или authorization blocker копированием credentials, sourcing implementation files, изменением target-local configuration из product tree или повтором role с другим hidden context.

## Related guides

- `docs/guides/launch-and-role-modes.md` объясняет public launcher и role modes.
- `docs/guides/lifecycle-and-packets.md` даёт lifecycle plan, review, closeout и packets.
- `docs/guides/golden_paths.md` связывает common post-merge routes.
- `docs/roles/` определяет role responsibilities и handoff boundaries.
- `docs/playbooks/` содержит detailed process playbooks и templates.

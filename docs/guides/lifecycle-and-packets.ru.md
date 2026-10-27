<!-- i18n: pair=docs/guides/lifecycle-and-packets.md pair-sha256=462b46d4e3b8f4baffdeea6065b680d471a58ca7044d91ce610790ff3e095b89 self-sha256=85b79c68a9a3ce2bb3a3cea51910aa1e08f9fa434ae435dd1a155c080fa52eb7 -->
# Жизненный цикл и пакеты

[English](lifecycle-and-packets.md) · **Русский**

Эта инструкция описывает общий жизненный цикл Planveyor. Границы задачи, критерии приёмки и статус текущего плана она не заменяет.

## План, очередь и ревью

Явно укажите проект и путь к плану. Затем прочитайте через фасад источник истины о маршруте:

```zsh
./bin/planveyor --project /absolute/path/to/consumer \
  planveyor_plan_status_oracle --json docs/plans/<plan>.md
```

До передачи работы запустите линтер плана и проверки целевого проекта, которых требуют выбранный проект и текущий план. Состояние очереди создают только явные вспомогательные скрипты `planveyor_q_*`. Указатель активного плана не заменяет источник истины об очереди. Прежде чем заменить или очистить очередь, прочитайте её состояние через `planveyor_q_show`. Для `planveyor_q_set` и `planveyor_q_append` явно передайте `--for-manager-mode`; `planveyor_q_clear` режима Manager не принимает и допускает только необязательный флаг `--json`.

Точный набор файлов, файл ревью и CENSOR остаются отдельными записями доказательств. Положительный текст в ответе роли, старая квитанция или широкое статическое сканирование не закрывают текущий набор файлов без соответствующего чтения состояния.

## Проверка после слияния и закрытие

После поставки в терминальном статусе перенесите долговечные решения в канон. Реальные отложенные задачи и предложения по процессу сохраните в их собственных записях. Затем запустите проверки целевого проекта и проверки документации. Временные планы и файлы ревью удаляют, только когда есть свежие доказательства для очистки и явное решение Owner.

См. также:

- [аудит после слияния](../playbooks/post_merge_audit.md);
- [сбор решений из планов после слияния](../playbooks/post_merge_plan_harvest.md);
- [гигиена документов после слияния](../playbooks/post_merge_docs_hygiene.md).

## Адресная доставка, принятие и ACK

Пакет — это передача работы между исходным репозиторием Planveyor и проектом, а не исполняемый план в исходном репозитории. Вспомогательные скрипты исходного репозитория запускаются из физического корня Planveyor без `--project`. Указывайте только пути к пакетам в исходном репозитории и явное имя целевого репозитория `<target-repo>`.

```zsh
./bin/planveyor planveyor_rollout_packet_create <target-repo> <topic-slug> \
  --source-plan docs/plans/<source>.md --target-kind plan_adoption
./bin/planveyor planveyor_rollout_packet_show docs/rollout_packets/<packet>.md
./bin/planveyor planveyor_rollout_packet_import_instructions \
  docs/rollout_packets/<packet>.md --print-target-plan-seed
```

Обычный порядок доставки такой: проект создаёт у себя план принятия, он же квитанция импорта, а затем записывает один исход в выбранном проекте через публичный фасад:

```zsh
./bin/planveyor --project /absolute/path/to/consumer \
  planveyor_rollout_packet_outcome_set \
  --target-plan docs/plans/<target-adoption>.md --packet-id <id> \
  --packet-path docs/rollout_packets/<packet>.md --outcome <canonical-or-alias>
```

Эта команда меняет только структурированную запись в целевом проекте. Затем исходный репозиторий записывает отдельную квитанцию:

```zsh
./bin/planveyor planveyor_rollout_packet_ack \
  --packet docs/rollout_packets/<packet>.md --status imported \
  --target-plan docs/plans/<target-adoption>.md
```

ACK создаёт указатель на `docs/plans/<target-adoption>.md`, но сам по себе не доказывает, что исход в целевом проекте готов. Пакет после ACK может остаться в ожидании исхода.

Для чтения состояния и состояния планирования используйте `planveyor_rollout_packet_lint`, `planveyor_rollout_packet_inbox`, `planveyor_rollout_packet_adoption_plan`, `planveyor_rollout_packet_query` и `planveyor_rollout_packet_reconcile`. Запрос в Planveyor (upstream request) — отдельная запись. В публичном жизненном цикле с ним работают `planveyor_upstream_request_show`, `planveyor_upstream_request_import`, `planveyor_upstream_request_ack` и `planveyor_upstream_request_query`.

Проверка в режиме отчёта и повторного использования не меняет пакет, но создаёт новый отчёт `docs/reviews/*_packetization_gate_range_*.md` и при стандартном пути вывода помечает прежние отчёты того же диапазона как заменённые. При блокирующих строках код выхода — 2. В режиме отчёта `--range` необязателен, если диапазон уже сохранён; в примере он выбран явно:

```zsh
./bin/planveyor planveyor_post_merge_packetization_gate --range BASE..HEAD
```

Чтобы заново поставить отметку на пакете (restamp) или восстановить его, явно назовите пакет исходного репозитория:

```zsh
./bin/planveyor planveyor_post_merge_packetization_gate_recover \
  --range BASE..HEAD --packet docs/rollout_packets/<packet>.md \
  --source-plan docs/plans/<source>.md --stage-packets
```

Для восстановления `--range` обязателен. `--source-plan` необязателен и указывает происхождение, а `--packet` можно повторять. Вызов без названного пакета остаётся в режиме отчёта и повторного использования и обновление пакета не заменяет. Эти вспомогательные скрипты не разрешают ни прямую запись в sibling, ни включение очереди, ни публикацию.

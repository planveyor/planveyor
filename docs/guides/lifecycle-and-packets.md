# Lifecycle и пакеты

Эта инструкция описывает общую Planveyor lifecycle. Она не заменяет scope, acceptance criteria или status текущего plan.

## План, очередь и review

Выбери literal project и plan path, затем прочитай routing truth через facade:

```zsh
./bin/planveyor --project /absolute/path/to/consumer \
  planveyor_plan_status_oracle --json docs/plans/<plan>.md
```

Запусти plan lint и target validation, требуемые выбранным project и текущим plan, до handoff. Queue state materialize-ится только explicit `planveyor_q_*` helpers; active plan pointer не заменяет queue truth. Перед заменой или очисткой очереди сначала прочитай её состояние, затем используй явный Manager mode.

Exact bundle, review artifact и CENSOR остаются отдельными evidence carriers. Положительный текст role response, historical receipt или broad static scan не закрывают current bundle без соответствующего readback.

## Post-merge и closeout

После terminal delivery перенеси durable решения в canon, сохрани реальные follow-ups и process improvements в их собственных carriers, затем выполни target checks и documentation checks. Временные plans и review artifacts удаляются только после fresh cleanup evidence и явного Owner решения.

См. также:

- [post-merge audit](../playbooks/post_merge_audit.md);
- [post-merge plan harvest](../playbooks/post_merge_plan_harvest.md);
- [post-merge docs hygiene](../playbooks/post_merge_docs_hygiene.md).

## Rollout, adoption и ACK

Пакет — handoff между Planveyor source и consumer, не executable plan в source repository. Source-local helpers запускаются из physical Planveyor root без `--project`; используй только source-local packet paths и literal `<target-repo>`.

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

Используй `planveyor_rollout_packet_lint`, `planveyor_rollout_packet_inbox`, `planveyor_rollout_packet_adoption_plan`, `planveyor_rollout_packet_query` и `planveyor_rollout_packet_reconcile` для readback и planning state. Upstream request — отдельный carrier; public lifecycle использует `planveyor_upstream_request_show`, `planveyor_upstream_request_import`, `planveyor_upstream_request_ack` и `planveyor_upstream_request_query`.

Report/reuse gate читает exact range без изменения packet:

```zsh
./bin/planveyor planveyor_post_merge_packetization_gate --range BASE..HEAD
```

Для packet restamp/recovery назови source-local packet явно:

```zsh
./bin/planveyor planveyor_post_merge_packetization_gate_recover \
  --range BASE..HEAD --packet docs/rollout_packets/<packet>.md \
  --source-plan docs/plans/<source>.md --stage-packets
```

`--range` обязателен для recovery; `--source-plan` — optional provenance; можно повторять `--packet`. Вызов без named packet остаётся report/reuse path и не заменяет packet update. Эти helpers не разрешают direct sibling writes, queue activation или publication.

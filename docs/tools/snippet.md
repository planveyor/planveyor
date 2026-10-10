# Сниппеты Planveyor

Эта страница содержит короткие public recipes для lifecycle, evidence и
documentation search. Application-specific framework, database, worker, UI
protocol, deployment и credential recipes принадлежат selected consumer.

## Public entry

Запускай Planveyor из physical Planveyor root:

~~~bash
./bin/planveyor <planveyor_function> [args…]
~~~

До первого public command проверь доступный `git`, physical Planveyor Git checkout и `HEAD`, разрешающийся в commit. Facade делает это до `--project` и до doctor.

Для consumer project передай его явно:

~~~bash
./bin/planveyor --project /absolute/path/to/consumer <planveyor_function> [args…]
~~~

Не подключай implementation shell file через source. Один вызов не делает
постоянное изменение cwd, credentials или local state.

## Быстрая диагностика

~~~bash
./bin/planveyor planveyor_entry_doctor
./bin/planveyor planveyor_runtime_info
./bin/planveyor planveyor_verify --format json
~~~

Doctor/readback доказывает только runtime observation текущего вызова. Он не
доказывает semantic acceptance, provider availability, plan admissibility, SID
или dispatch. Cached plan pointer — только local selection; при его отсутствии
`planveyor_planpath` предлагает `planveyor_plan_set <PLAN_PATH>`, но не
подтверждает readiness. Полный first-hour route, normal TUI без `--q` и separate
queue находятся в `docs/guides/launch-and-role-modes.md`.

## Plan и exact bundle

~~~bash
./bin/planveyor planveyor_plan_status_oracle docs/plans/<plan>.md --json
./bin/planveyor planveyor_plan_bundle --preflight docs/plans/<plan>.md
./bin/planveyor planveyor_plan_bundle --check docs/plans/<plan>.md
~~~

Используй exact plan path. Cached plan pointer, chat prose и старый receipt не
являются routing truth. Перед финальным transition role owner сохраняет
current evidence в plan/review artifact; Manager не заменяет этот шаг.

## Range и review

~~~bash
./bin/planveyor planveyor_merge_range_stats_json BASE HEAD
./bin/planveyor planveyor_review_range_init --range BASE..HEAD
git diff --check BASE..HEAD
rg -n "^<<<<<<< |^======= |^>>>>>>> " .
~~~

Выбирай target-local harness только из plan/canon. Для UI work scenario,
preconditions, comparator, human verdict и assets обязаны быть declared
current target facts. При отсутствии lane используй N/A с причиной.

## Поиск документации

~~~bash
rg -n "<anchor-token>" docs
./bin/planveyor planveyor_docs_index_build all
./bin/planveyor planveyor_docs_retrieve --corpus canon "<anchor-token>"
./bin/planveyor planveyor_docs_context_check --corpus plans --format text
~~~

Держи запрос коротким и используй stable domain terms из текущего plan/canon.
Search result — discovery, не decision evidence. Если retrieval повлиял на
решение, добавь Retrieval telemetry receipt с current read/open result или
declared no-op reason.

Derived index и logs — local/disposable state. Не коммить их и не указывай
personal absolute path в artifact.

## Follow-ups и process improvements

~~~bash
./bin/planveyor planveyor_followups_query ready-candidates --format json
./bin/planveyor planveyor_followups_triage --file docs/followups/<backlog>.md --dry-run
./bin/planveyor planveyor_process_improvements_promote --help
~~~

Backlog row, promoted dev-plan и process-improvement row имеют разные owners.
NO FOLLOWUPS относится только к ordinary harvest lane; это не закрывает
separate process-improvement work и не authorizes deletion.

## Post-merge и docs hygiene

~~~bash
./bin/planveyor planveyor_post_merge_packetization_gate --range BASE..HEAD
./bin/planveyor planveyor_docs_closeout docs/plans/<plan>.md --json
./bin/planveyor planveyor_doc_lint
~~~

Если shared carrier требует delivery, source owner materializes source-local
rollout packet. Consumer owner принимает packet локально. Не заменяй этот flow
ручным copy или broad docs sweep.

Исторические plans, reviews и snapshots не являются active canon. До cleanup
сохрани durable facts в canon, audit или follow-up; active docs не должны
ссылаться на временные files как на source of truth.

## Packets

~~~bash
# source: physical Planveyor root
./bin/planveyor planveyor_rollout_packet_create <target-repo> <topic-slug> \
  --target-kind consumer_only --queue-after-import no
./bin/planveyor planveyor_rollout_packet_lint --all --json

# consumer: selected target repository
./bin/planveyor --project /absolute/path/to/consumer \
  planveyor_rollout_packet_inbox --target-repo <target-repo> --json
./bin/planveyor --project /absolute/path/to/consumer \
  planveyor_rollout_packet_adoption_plan --target-repo <target-repo> \
  --out docs/plans/<target-adoption>.md
./bin/planveyor --project /absolute/path/to/consumer \
  planveyor_rollout_packet_outcome_set \
  --target-plan docs/plans/<target-adoption>.md --packet-id <id> \
  --packet-path docs/rollout_packets/<packet>.md --outcome <canonical-or-alias>

# source: physical Planveyor root
./bin/planveyor planveyor_rollout_packet_ack \
  --packet docs/rollout_packets/<packet>.md --status imported \
  --target-plan docs/plans/<target-adoption>.md
~~~

Packet передаёт source evidence и requested adoption. Он не authorizes target
mutation, queue activation, commit или push. Unknown target writable carrier
остаётся blocker.

## Security и portability

- Не записывай credentials, cookies, tokens, headers, account paths или
  provider output в docs/receipts; используй <REDACTED>.
- Используй repo-relative paths, <source-repo>/<target-repo> placeholders и
  explicit /absolute/path/to/consumer только для documented facade selection.
- Не подменяй target-local command generic framework example.
- Если evidence отсутствует, зафиксируй blocker вместо fabricated proof.

См. также docs/guides/launch-and-role-modes.md,
docs/guides/lifecycle-and-packets.md и
docs/playbooks/portability_substitution_rules.md.

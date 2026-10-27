<!-- i18n: pair=docs/tools/snippet.md pair-sha256=816f6e26333a4d4be86ffd633b52c0e0cafbb4aa01673fab664fd59c5471a6be self-sha256=37f23b18e7a5a6010e1a02e67712c4abf32cd1723be38024b7b256998b21221e -->
# Сниппеты Planveyor

[English](snippet.md) · **Русский**

Здесь собраны короткие публичные рецепты для жизненного цикла, доказательств и
поиска по документации. Рецепты для фреймворка, базы данных, фоновых
обработчиков, протокола UI, развёртывания и учётных данных конкретного
приложения принадлежат выбранному проекту.

## Публичная точка входа

Запускайте Planveyor из его физического корня:

~~~bash
./bin/planveyor <planveyor_function> [args…]
~~~

До первой публичной команды проверьте, что доступен `git`, есть физическая копия репозитория Planveyor и `HEAD` указывает на коммит. Фасад проверяет это до `--project` и до doctor.

Для работы с проектом передайте его явно:

~~~bash
./bin/planveyor --project /absolute/path/to/consumer <planveyor_function> [args…]
~~~

Не подключайте через `source` shell-скрипты реализации. Фасад не меняет
текущий каталог и окружение родительской оболочки; изменения файлов и состояния,
предусмотренные командой, могут сохраняться после завершения дочернего процесса.

## Быстрая диагностика

~~~bash
./bin/planveyor planveyor_entry_doctor
./bin/planveyor planveyor_runtime_info
./bin/planveyor planveyor_verify --format json
~~~

Doctor и чтение состояния доказывают только то, что увидел текущий вызов. Они
не доказывают приёмку по смыслу, доступность провайдера, допустимость плана,
SID или вызов роли. Сохранённый указатель плана — только локальный выбор. Если
его нет, `planveyor_planpath` предлагает `planveyor_plan_set <PLAN_PATH>`, но
готовность не подтверждает. Полный маршрут первого часа, обычный TUI без `--q`
и отдельная очередь описаны в `docs/guides/launch-and-role-modes.ru.md`.

## План и точный набор файлов

~~~bash
./bin/planveyor planveyor_plan_status_oracle docs/plans/<plan>.md --json
./bin/planveyor planveyor_plan_bundle --preflight docs/plans/<plan>.md
./bin/planveyor planveyor_plan_bundle --check docs/plans/<plan>.md
~~~

Указывайте точный путь к плану. Маршрут не определяют ни сохранённый указатель
плана, ни текст из чата, ни старая квитанция. Перед последним переходом статуса
роль, которая отвечает за шаг, сохраняет текущие доказательства в плане или
файле ревью; Manager этот шаг не заменяет.

## Диапазон и ревью

~~~bash
./bin/planveyor planveyor_merge_range_stats_json BASE HEAD
./bin/planveyor planveyor_review_range_init BASE HEAD
git diff --check BASE..HEAD
rg -n "^<<<<<<< |^======= |^>>>>>>> " .
~~~

Обвязку целевого проекта выбирайте только по плану или канону. Для работы с UI
сценарий, предусловия, способ сравнения, вердикт человека и файлы-приложения
должны быть объявлены как текущие факты целевого проекта. Если линии нет, пишите
`N/A` с причиной.

## Поиск документации

~~~bash
rg -n "<anchor-token>" docs
./bin/planveyor planveyor_docs_index_build all
./bin/planveyor planveyor_docs_retrieve canon "<anchor-token>"
./bin/planveyor planveyor_docs_context_check --corpus plans --format text
~~~

Держите запрос коротким и берите устойчивые термины предметной области из текущего
плана или канона. Результат поиска помогает найти документ, но доказательством
для решения не служит. Если поиск повлиял на решение, добавьте квитанцию
`Retrieval telemetry receipt` с текущим результатом чтения или открытия либо с
объявленной причиной `no-op`.

Производный индекс и журналы — локальное временное состояние. Не коммитьте их и
не указывайте в артефакте личный абсолютный путь.

## Отложенные задачи и предложения по процессу

~~~bash
./bin/planveyor planveyor_followups_query ready-candidates --format json
./bin/planveyor planveyor_followups_triage --file docs/followups/<backlog>.md --dry-run
./bin/planveyor planveyor_process_improvements_promote --help
~~~

Строка списка отложенных задач, план разработки, созданный продвижением задачи,
и строка предложения по процессу принадлежат разным владельцам. `NO FOLLOWUPS`
относится только к обычной линии сбора отложенных задач. Отдельную работу по
предложениям процесса эта отметка не закрывает и удаление не разрешает.

## Проверка после слияния и гигиена документов

~~~bash
./bin/planveyor planveyor_post_merge_packetization_gate --range BASE..HEAD
./bin/planveyor planveyor_docs_closeout docs/plans/<plan>.md --json
./bin/planveyor planveyor_doc_lint
~~~

Если общую запись (carrier) нужно доставить, владелец репозитория Planveyor
создаёт у себя пакет адресной доставки. Владелец проекта принимает пакет у
себя. Не заменяйте этот путь ручным копированием или массовой правкой документов.

Старые планы, ревью и снимки не входят в действующий канон. До уборки сохраните
долговечные факты в каноне, аудите или отложенной задаче. Действующие документы
не должны ссылаться на временные файлы как на источник истины.

## Пакеты

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

Пакет передаёт доказательства из репозитория Planveyor и запрос на принятие
изменения. Он не разрешает менять целевой проект, включать очередь, делать
коммит или push. Неизвестная запись целевого проекта, в которую нужно писать,
остаётся блокером.

## Безопасность и переносимость

- Не записывайте в документы и квитанции учётные данные, cookies, токены,
  заголовки, пути учётных записей или вывод провайдера; используйте `<REDACTED>`.
- Используйте пути относительно репозитория и заглушки
  `<source-repo>`/`<target-repo>`; явный `/absolute/path/to/consumer` пишите
  только для выбора проекта через фасад, как описано в документации.
- Не подменяйте команду целевого проекта общим примером для фреймворка.
- Если доказательств нет, запишите блокер вместо выдуманного доказательства.

См. также `docs/guides/launch-and-role-modes.ru.md`,
`docs/guides/lifecycle-and-packets.ru.md` и
`docs/playbooks/portability_substitution_rules.md`.

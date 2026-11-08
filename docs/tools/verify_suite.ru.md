<!-- i18n: pair=docs/tools/verify_suite.md pair-sha256=484571ce081836362d628105df2c1cb8e83a9a2bf2c7344012f953ef8d31952b self-sha256=17244f3b188601f977f78e9f13cc8d3dfcca669d03b10fa7cbd25f3314c9d97a -->
# Руководство Owner: маршруты проверки

[English](verify_suite.md) · **Русский**

`planveyor_verify` — сводная проверка установленного корпуса Planveyor. Она запускает его зарегистрированные модули проверки целостности и ничего не меняет. По умолчанию идёт быстрый маршрут проверки целостности, а `--full` добавляет один канонический прогон тестов через `unittest discover`. Реализацию и точный набор модулей задаёт установленная копия Planveyor, а это руководство описывает контракт для оператора.

## Запуск

Запускайте команды из физического корня Planveyor через публичный фасад:

```zsh
./bin/planveyor planveyor_verify
./bin/planveyor planveyor_verify --format json
./bin/planveyor planveyor_verify --module <module-name>
./bin/planveyor planveyor_verify --full
make verify
make verify-full
make test-scripts
```

Маршрут по умолчанию выполняет зарегистрированные проверки целостности, кроме тестов `unittest`. Он не запускает ни `unittest discover`, ни прежний дублирующий прогон тестов переносимости внутри модуля. `--full` добавляет ровно один канонический прогон, и его нельзя сочетать с `--module`. `make verify` идёт маршрутом по умолчанию, `make verify-full` передаёт `--full`, а `make test-scripts` остаётся отдельной командой канонического прогона. Для одного заявления о полной проверке выберите что-то одно: `make verify-full` или `make test-scripts`. Не запускайте их вместе.

## Границы платформы и CI

Первый выпуск поддерживает работу на macOS с подготовленным окружением Python 3.12 и зависимостями из `requirements-dev.lock`. Ещё должны быть доступны Git, zsh и ripgrep. Загрузчик идентичности исходников (source identity) технически принимает Python 3.10–3.12, но поддержку первого выпуска это не расширяет. Профили CI на macOS и обязательный summary описаны ниже; сама настройка результатом hosted CI не считается. Нативная проверка на Windows и Linux не завершена.

Имена модулей, запущенных установленной версией, есть в JSON-отчёте
`planveyor_verify --format json`; передайте нужное имя через `--module`. Для работы с проектом выберите его явно через фасад, перед командой, если модуль рассчитан на проверку дерева проекта.

## Проверка совместимости в CI

Состав выборки `compat310` задаёт точный список ID в `scripts/test_shards.json`: тесты потока загрузчика и обработки отказов, выбора интерпретатора, разбора идентичности исходников и настоящего пути init, doctor и upgrade через публичный фасад и Copier. Это ограниченная проверка совместимости. Она не заменяет полный набор на Python 3.10 и не расширяет поддерживаемую среду первого выпуска. Целевая версия Python для mypy остаётся 3.10.

Команды запускаются из физической копии репозитория выбранным подготовленным интерпретатором:

```zsh
"$PYBIN" -B scripts/run_test_shard.py --matrix
"$PYBIN" -B scripts/run_test_shard.py --check
"$PYBIN" -B scripts/run_test_shard.py --subset compat310 --report <fresh-report-path>
```

`--matrix` читает структуру матрицы, не импортируя тесты. `--check` импортирует тесты через каноническое обнаружение и проверяет все ID настроенных выборок и полное разбиение: каждый тест должен стоять ровно в одной части. Тела тестов при этом не выполняются. Запуск выборки сначала повторяет эти проверки, а затем отбирает нужные тесты из исходных в каноническом порядке и сохраняет хуки уровня модуля и класса. Неизвестные, пустые, повторные или отсутствующие ID и неверное полное разбиение приводят к отказу. Каталог отчёта должен существовать, а файлов отчёта и событий по указанным путям ещё не должно быть. `--subset` нельзя совмещать с выбором полной части или локального профиля.

Отчёт и парный файл `.events.jsonl` связывают упорядоченный список ID, хеш манифеста, сведения об интерпретаторе Python, HEAD и учёт запущенных и завершённых тестов. В отчёте выборки стоят `selected_subset=compat310` и `selected_shards=[]`, в отчёте полного или локального запуска — ID его частей и `selected_subset=null`. Если учёт неполный, запуск прерван или HEAD после исполнения отличается от HEAD до него, результат не будет зелёным. Локальный результат проверки совместимости не доказывает ни успеха в hosted CI, ни покрытия полного набора на Python 3.10 и не обещает, сколько времени займёт проверка после push. Полные маршруты проверки, описанные выше, остаются отдельными.

## Fast/full CI и обязательный итог

Checked-in workflow направляет push в `main` и `pull_request` в **fast**: части Python 3.12 `core` (`--subset fast`), `contracts-a`, `contracts-b` и отдельную часть Python 3.10 `compat310`. Ежедневный `schedule` (`17 2 * * *` UTC) и `workflow_dispatch` выбирают **full**: все 14 частей Python 3.12 и `compat310`. Обхода для docs-only и release action нет. Bare `--matrix`, локальные профили и публичная полная проверка сохраняют прежние defaults.

До selection CI импортирует canonical discovery, проверяет полное exact-once разбиение и независимо от mutable subset IDs сверяет composition. Core сохраняет fixed16 целых safety witnesses; `contracts-a` содержит все discovered cases `test_planveyor_plan_bundle`; `contracts-b` — все cases explicit29-module policy в `scripts/run_test_shard.py`. Core/A/B не пересекаются. Fixed9 compatibility IDs проверяются отдельно. Числа растут с canonical methods; snapshots не являются потолками.

`shard-matrix` устанавливает существующие declared prerequisites до импорта tests и выполняет explicit composition check вне subset selection. Четыре metadata команды идут один раз: strict docs/i18n, changed-plan lint, typecheck с policy Python 3.10 и public scan. Их row — `contracts-b` для fast или `s01` для full. PR base для changed-plan lint — обязательный merge-base с target branch; недоступный PR base приводит к отказу. Push использует valid event-before commit либо root fallback; schedule/manual — `HEAD^1` либо root fallback. Выбранные event/base/head логируются.

Strict worker требует `--ci-strict`, `--ci-profile`, `--ci-part`, `--ci-python`, `--ci-event`, `--ci-run-id`, `--ci-run-attempt` и `--ci-expected-sha`. Profile вместе с execution selector без strict context отказывает до bodies. PR дополнительно требует `--ci-pr-head-sha`; другие events отвергают этот flag. Trusted expected checkout — `github.sha`, включая synthetic merge commit для PR; head SHA передаётся отдельно. Равенства двух observed HEAD недостаточно.

Просмотр profiles из подготовленного checkout не исполняет тела tests:

```zsh
"$PYBIN" -B scripts/run_test_shard.py --matrix --ci-profile fast
"$PYBIN" -B scripts/run_test_shard.py --check --ci-profile full
```

Strict report добавляет validated `ci_profile,ci_part,ci_event,ci_run_id,ci_run_attempt,ci_expected_sha,ci_pr_head_sha,ci_expected_python,ci_python` к existing report. Actual Python pair, manifest, trusted expected SHA, selector и непустые ordered planned/started/completed IDs должны совпадать с independently expected execution. Strict green требует полного accounting без failures, errors, skips, interruption или source drift; legacy local skip semantics сохраняются. Python 3.12 сохраняет native duration records, Python 3.10 — wall-only/null durations. Timing остаётся diagnostic.

Standard artifact actions с immutable pins передают только `result.json` в `planveyor-ci-<run>-<attempt>-<part>`; upload использует `if: always()`, отсутствие report считается ошибкой. Обязательный check **`ci-summary`** идёт с `if: always()`, зависит от `shard-matrix` и `verify` и независимо вызывает `--ci-summary DIRECTORY --ci-profile fast|full` с trusted event/run/attempt/SHA context и `--ci-needs-json JSON`. Он читает ровно current-attempt corpus, не повторяет workers и не берёт expected IDs из reports или preparation output. Union full shards обязан exact-once равняться всему canonical suite; fast union равен только core/A/B. Compatibility остаётся отдельной axis.

Missing, extra, malformed, duplicate-key, stale, foreign, duplicate, incomplete, red, cancelled или skipped parts/needs дают отказ. Успешный matrix aggregate не скрывает missing report, s02 с исполнением s01, два equal wrong HEAD или red authoritative report. Events — diagnostics; обязательной per-event reaggregation и GitHub API client нет.

Fast concurrency привязана к ref и использует latest-wins. Full groups содержат run ID и attempt, поэтому последующие full не вытесняют предыдущие pending full; runner capacity этим не резервируется. Deployment policy должна сохранять обязательный summary как required check; repository rulesets этот change не меняет. Перед будущим выпуском нужен full green на actual release SHA. Local synthetic checks и source configuration не доказывают hosted success, queue/cancellation qualification, публикацию или часовой budget.

## Что значит результат

- `GREEN` / код выхода `0` значит, что прошли все обязательные зарегистрированные проверки. Даже тогда `WARN` может потребовать, чтобы оператор прочитал подробности и выполнил локальное предварительное условие, прежде чем считать работу готовой.
- `RED` / ненулевой код выхода значит, что хотя бы одна обязательная проверка не прошла. Прежде чем менять какой-либо артефакт, прочитайте названные модуль, метрику и подробности.
- Успешный прогон маршрута проверки подтверждает только те проверки, о которых он сообщает. Он не доказывает, что роли отработали, тесты целевого проекта прошли, ревью принято, пакет принят или задача закрыта по смыслу.

## Когда запускать

Запускайте нужный модуль после изменения его контракта, перед публичным выпуском или когда сомнение в переносимости или целостности нужно проверить узким чтением состояния. Пока разбираете блокер, берите самый маленький подходящий модуль. `--full` нужен, когда один сводный маршрут должен добавить канонический прогон, который охватывает несколько зарегистрированных границ.

## Если проверка предупреждает или падает

1. Прочитайте результат именно этого модуля и его подробности.
2. Определите, к чему относится замечание: к текущему содержимому репозитория, к внешнему выбранному проекту или к временному локальному состоянию.
3. Исправьте только названную причину, через тот жизненный цикл, которому она принадлежит.
4. Запустите тот же модуль снова. Если результат важен для передачи работы, запишите свежие доказательства.

Не ослабляйте проверку, не переписывайте посторонний артефакт и не глушите текущий отказ старым зелёным результатом.

## Связанные документы

- `docs/guides/launch-and-role-modes.ru.md` — публичный фасад и выбор проекта.
- `docs/guides/lifecycle-and-packets.ru.md` — проверки плана, ревью, закрытия и пакетов.
- `docs/playbooks/portability_substitution_rules.md` — словарь переносимых публичных артефактов.

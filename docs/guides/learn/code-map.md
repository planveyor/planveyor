# Справочник по коду

Это приложение для разработчиков Planveyor. Сюда вынесены таблицы из всех глав: файлы и функции, с которых стоит начать чтение реализации, и именованные тесты с тем, что они проверяют. Разделы идут в порядке глав. Номера строк в коде меняются, поэтому ищите функцию или тест по имени.

Описания тестов сделаны по их исходному коду. Прошли ли эти тесты на вашей версии, показывает только их запуск: команды — в [маршрутах проверки](../../tools/verify_suite.ru.md).

## Роли и файлы задачи

Глава: [Роли и файлы задачи](roles-artifacts.md).

### Где читать реализацию

| Вопрос | Файл и ключевой символ |
| --- | --- |
| Как фаза получает имя prompt | [planveyor.zsh](../../../scripts/planveyor.zsh), `_planveyor_prompt_filename_for_role_phase()` |
| Как выбираются фактические bytes prompt | [planveyor.zsh](../../../scripts/planveyor.zsh), `_planveyor_prompt_file_for_role_phase()` |
| Как вызываются основные роли | [role_runtime.zsh](../../../scripts/planveyor/role_runtime.zsh), `planveyor_arch()`, `planveyor_planner()`, `planveyor_coder()` |
| Как запускается конкретная линия Reviewer | [role_runtime.zsh](../../../scripts/planveyor/role_runtime.zsh), `_planveyor_reviewer_run_for_session_key()` |
| Как Manager передаёт работу линиям | [manager_collab_pipeline.md](../../tools/prompts/manager_collab_pipeline.md), подпункт алгоритма о Reviewer dispatch |
| Как проверяется принадлежность источника | [contract_authority_context.py](../../../scripts/contract_authority_context.py), `context_for_reader()` и `read_declared_text()` |

### Что проверяют тесты

| Именованный тест | Точные проверки и предел вывода |
| --- | --- |
| [test_planveyor_codex_agent_roles.py](../../../scripts/test_planveyor_codex_agent_roles.py): `test_collab_prompt_dispatches_the_configured_role_types` | Через `assertIn` проверяет пары `architect/planner/coder → agent_type`, а также `followup_task` и `list_agents`; запрещает `planner → agent_type=default`. Это проверка текста prompt, не живого исполнения роли |
| [test_analysis_source_ownership.py](../../../scripts/test_analysis_source_ownership.py): `test_every_shipped_role_declares_shared_root_then_declared_target_local` | Для Architect, Planner, Coder и Reviewer проверяет наличие и порядок маркеров источника analysis-wave playbook: shared root, объявленный target-local источник, запрет guessed fallback. Это узкая проверка четырёх role docs; Manager и все прочие источники роли ею не проверяются |
| [test_planveyor_codex_agent_roles.py](../../../scripts/test_planveyor_codex_agent_roles.py): `test_home_ensure_selects_consumer_home_without_rewriting_agent_roles` | Общий fixture проверяет код `0`, возвращённый каталог, неизменность snapshot файлов и отсутствие нового `agents/planner.toml`. Клиент в fixture заменён заглушкой; проверка не доказывает аутентификацию |

## Сквозной пример: какие товары пора пополнить

Глава: [Сквозной пример: какие товары пора пополнить](sql-example.md). Здесь код SQL sibling из [снимка](examples/sql/README.md), а не код Planveyor. В снимке два из 40 тестов обвязки, остальные остались в sibling.

### Где читать реализацию

| Вопрос | Файл и ключевой символ |
| --- | --- |
| Как процедура считает дефицит | [GetReorderCandidates.sql](examples/sql/sql/Northwind/GetReorderCandidates.sql), `COALESCE` и `CAST(... AS INT)` внутри `CROSS APPLY` |
| Как запускаются два класса тестов и проверка порядка | [run-tests.sql](examples/sql/sql/tests/run-tests.sql), маркеры `PV_TEST_RESULT`, `PV_ORDER_BEGIN`, `PV_ORDER_END` |
| Что делает `make db-proof` | [sql.py](examples/sql/scripts/sql.py), `db_proof()` |
| Как проверяются исходники тестов и скрипт запуска | [sql.py](examples/sql/scripts/sql.py), `verify_test_files()`, `current_test_set()` |
| Как проверяется состояние классов в базе | [sql.py](examples/sql/scripts/sql.py), `existing_classes_are_safe()` |
| С какими параметрами идёт публикация | [sql.py](examples/sql/scripts/sql.py), `publish_args()` |
| Как разбираются результаты тестов и порядок строк | [sql.py](examples/sql/scripts/sql.py), `parse_test_results()`, `parse_order_rows()` |
| Как прогон привязан к коммиту и файлам | [sql.py](examples/sql/scripts/sql.py), `current_proof_bytes()`, `reusable_proof()` |
| Когда отчёт JUnit зелёный, а когда красный | [sql.py](examples/sql/scripts/sql.py), `junit_xml()`, `junit_matches()`, `failure_junit()` |

### Что проверяют тесты

| Именованный тест | Точные проверки и предел вывода |
| --- | --- |
| [test_sql_excerpt.py](examples/sql/test_sql_excerpt.py): `test_exact_result_and_direct_client_order_parsers` | На подставленном выводе базы принимает восемь успешных результатов и порядок `(10, 20, 30)`. Отвергает пропущенный, повторный, лишний и неуспешный результат; вывод без маркера `PV_ORDER_BEGIN` и с повторным маркером; ID 30 во второй строке вместо 20 (порядок 10, 30, 30); пропущенную и испорченную строку. Проверяет разбор вывода, база в тесте не участвует |
| [test_sql_excerpt.py](examples/sql/test_sql_excerpt.py): `test_wrong_client_order_writes_red_junit_and_no_green_proof` | Вызывает `db_proof()` с подменёнными командами: оба класса помечены, строки приходят в порядке 10, 30, 30. Ожидает ошибку `order observer sequence mismatch`, три запроса состояния классов и ровно один отчёт JUnit с `errors="1"`, который `junit_matches()` не принимает. Сборка, линтер, публикация и запросы к базе в тесте подменены |

## План и его статусы

Глава: [План и его статусы](plan-lifecycle.md).

### Где читать реализацию

| Механика | Файл и символ |
| --- | --- |
| Явный вход Oracle | [planveyor.zsh](../../../scripts/planveyor.zsh), `planveyor_plan_status_oracle()` |
| Header, authority и итоговый readback | [plan_status_oracle.py](../../../scripts/plan_status_oracle.py), `_scan_status_line()`, `machine_authority_decision_readback()`, `oracle_result()` |
| Проверки готовности handoff | [plan_lint.py](../../../scripts/plan_lint.py), `validate_exact_bundle_preflight()` и `lint_plan()` |
| Создание основы draft | [planveyor.zsh](../../../scripts/planveyor.zsh), `planveyor_code_draft_stub_from_plan()` |
| Выбор и чтение active plan | [planveyor.zsh](../../../scripts/planveyor.zsh), `planveyor_plan_set()` и `planveyor_planpath()` |
| Финальный состав и закрытие | [planveyor.zsh](../../../scripts/planveyor.zsh), `planveyor_plan_bundle()` и `planveyor_plan_closeout_preflight()` |
| Отдельный хвост документов | [docs_closeout.py](../../../scripts/docs_closeout.py), `classify_docs_closeout()` |
| Что печатает `planveyor sibling plan` | [sibling_runbook.py](../../../scripts/sibling_runbook.py), `show_plan()` |
| Как `planveyor sibling answer` записывает ответ Owner | [sibling_runbook.py](../../../scripts/sibling_runbook.py), `handle_answer()` |
| Что проверяет `planveyor sibling close` перед `Done` и как записывает `Done` | [sibling_closeout.py](../../../scripts/sibling_closeout.py), `validate_done_admission()` и `handle_close()`; сам статус пишет [sibling_runbook.py](../../../scripts/sibling_runbook.py), `Context.set_status()`, через `planveyor_sibling()` в [planveyor.zsh](../../../scripts/planveyor.zsh) (`--internal set-done`, допуск проверяется заново) |
| Почему открытый `## Post-merge gate` не пускает план в `Done` | [plan_lint.py](../../../scripts/plan_lint.py), `validate_done_post_merge_gate_checklist()` |

### Что проверяют тесты

| Именованный тест | Точные проверки и предел вывода |
| --- | --- |
| [test_plan_status_oracle.py](../../../scripts/test_plan_status_oracle.py): `test_json_output_uses_single_header_status_and_ignores_body_status` | Проверяет код `0`, `status_norm=ready for coder`, точную header-строку, переданный `plan_path` и hash длиной `64`; историческое `Done` в теле не выбирается. Это разбор fixture, не исполнение Coder |
| [test_plan_status_oracle.py](../../../scripts/test_plan_status_oracle.py): `test_duplicate_header_status_fails_with_line_details` | Проверяет код `3`, сообщение `expected exactly 1 header **Status:** line, got 2` и обе строки header. Это диагностика неоднозначного плана |
| [test_planveyor_plan_bundle.py](../../../scripts/test_planveyor_plan_bundle.py): `test_preflight_allows_missing_first_pass_review_artifact` | Подготовка возвращает `0` и `PLANNED`; финальный `--check` возвращает ненулевой код и `MISSING-PATH`, receipt указывает `next_owner=Reviewer`. Это различие стадий допуска, не готовое review |
| [test_planveyor_plan_bundle.py](../../../scripts/test_planveyor_plan_bundle.py): `test_preflight_rejects_stale_target_inventory` | Проверяет ненулевой код и `MISSING-PATH` с отсутствующим target. Несуществующий файл объявлен в `code_draft_meta.targets`; объявление без файла на диске не делает inventory пригодным |
| [test_plan_lint.py](../../../scripts/test_plan_lint.py): `test_done_plan_with_open_post_merge_gate_checkbox_fails` | Для плана в статусе `Done` с открытым пунктом `- [ ]` в `## Post-merge gate` возвращает одну находку `ERROR` с упоминанием `Post-merge gate` и `- [ ]`. Проверяется функция `validate_done_post_merge_gate_checklist()` на тексте fixture, без полного прогона линтера |
| [test_plan_lint.py](../../../scripts/test_plan_lint.py): `test_done_plan_with_post_merge_gate_section_level_na_passes` | Тот же `Done`-план, у которого раздел `## Post-merge gate` целиком заменён строкой `N/A (why=…)`, не даёт находок |
| [test_sibling_runbook.py](../../../scripts/test_sibling_runbook.py): `test_actual_question_closes_and_preserves_verbatim_multiline_text` | Ответ Owner дописывается в план строкой `(Owner, id=Q1, status=closed)` и строками `  > …` без изменения текста; прежнее содержимое плана сохраняется, `owner_qna_readback` после записи даёт `clean`, команда из текста ответа не выполняется. Проверка проекта и Oracle в fixture заменены чтением раздела вопросов из текста плана |
| [test_sibling_closeout.py](../../../scripts/test_sibling_closeout.py): `test_early_status_red_or_stale_review_and_owner_question_block` | По очереди подставляет в ответ Oracle статус `ready for arch review`, состояния ревью `stale_green_review` и `live_blocker`, открытый вопрос Owner и `route_guard_triggered=true`; каждый раз `handle_close()` с `--commit` останавливается, а HEAD, индекс и байты плана не меняются. Oracle, сборка набора и линтер в fixture заменены управляемыми ответами, Git настоящий |
| [test_sibling_closeout.py](../../../scripts/test_sibling_closeout.py): `test_failed_final_lint_restores_only_own_plan_bytes_and_does_not_commit` | Если финальный линтер после записи `Done` отказывает, `handle_close()` останавливается с сообщением «Статус восстановлен»: байты плана и HEAD прежние, в индексе исходная версия плана, целевой файл не тронут, `git reset` не вызывается. Линтер в fixture заменён управляемым ответом |

## Разработка, анализ и декомпозиция

Глава: [Разработка, анализ и декомпозиция](work-contours.md).

### Где читать реализацию

| Вопрос | Файл и символ |
| --- | --- |
| Подготовка существующего анализа | [planveyor.zsh](../../../scripts/planveyor.zsh), `planveyor_analysis_init()` |
| Подготовка и запуск decomposition | [planveyor.zsh](../../../scripts/planveyor.zsh), `planveyor_decomposition_init()`, `planveyor_decomposition_collab_tui()` |
| Как определяется authority analysis pack | [plan_status_oracle.py](../../../scripts/plan_status_oracle.py), `resolve_analysis_pack_authority()` |
| Как читается граф children | [plan_status_oracle.py](../../../scripts/plan_status_oracle.py), `decomposition_child_state()` |
| Как получается общая картина planning work | [planning_wave_readback.py](../../../scripts/planning_wave_readback.py), `build_readback()` |
| Как планы допускаются в очередь | [plan_queue.py](../../../scripts/plan_queue.py), `validate_explicit_plan_for_queue()` и `set_queue()` |
| Какие пять исходов анализа допустимы и что требует каждый | [plan_vocab.json](../../_meta/plan_vocab.json), `planning_contour.accepted_routes` и `status_transition_matrix`; [plan_status_oracle.py](../../../scripts/plan_status_oracle.py), `NON_EXECUTABLE_ROUTE_EXPECTED_FIELDS`, `NON_EXECUTABLE_ROUTE_REVISIT_REQUIRED` и `non_executable_source_route_carrier_issues()`; последнюю вызывает [plan_lint.py](../../../scripts/plan_lint.py) |

### Что проверяют тесты

| Именованный тест | Точные проверки и предел вывода |
| --- | --- |
| [test_plan_status_oracle.py](../../../scripts/test_plan_status_oracle.py): `test_plan_resident_statuses_are_exactly_the_statuses_without_code_draft` | Plan-resident статусы (ранние статусы и `Superseded`) равны canonical statuses за вычетом `code_draft_required`. Standalone-required множество равно самой группе `code_draft_required`: здесь authority уже во внешнем pack. Проверяется согласованность vocabulary, не качество анализа |
| [test_planning_wave_readback.py](../../../scripts/test_planning_wave_readback.py): `test_external_recommendation_uses_standalone_truth_host` | Проверяет schema `planning_wave_readback.v1`, plan reference, внешний `truth_host` pack и рекомендацию `developer_wave`. Наличие рекомендации в readback не доказывает dispatch |
| [test_plan_status_oracle.py](../../../scripts/test_plan_status_oracle.py): `test_operational_duplicate_warns_but_scalars_stay_pack_derived` | Требует `operational_duplicate` и lifecycle `warning`; при противоречащем plan budget возвращённые `budget_status=active` и depth `1` берутся из pack. Diagnostic warning не означает отсутствие проблемы |
| [test_plan_status_oracle.py](../../../scripts/test_plan_status_oracle.py): `test_active_decomposition_without_child_graph_exposes_missing_blocker` | При fixture с `Done` Oracle возвращает код `0`, но `queue_closeout_ready=false`, kind `decomposition_children_missing` и child state `missing`. Успешный readback не равен готовности закрытия |
| [test_plan_lint.py](../../../scripts/test_plan_lint.py): `test_operational_duplicate_with_ref_holds_on_every_status_family` | Для статусов `Architect initial draft`, `Ready for Planner`, `Ready for Review` и `Superseded` план со строкой `analysis_pack_ref` и продублированной строкой `route_recommendation` даёт ровно одну находку `ERROR` с `analysis_pack_authority_invalid:operational_duplicate` |
| [test_plan_lint.py](../../../scripts/test_plan_lint.py): `test_defer_source_route_requires_revisit_when` | Для плана анализа с принятым исходом `defer` без строки `revisit_when` в `## Promoted route artifact` линтер возвращает `ERROR` с упоминанием `revisit_when` |
| [test_plan_lint.py](../../../scripts/test_plan_lint.py): `test_human_gate_source_route_requires_revisit_when` | То же для исхода `human_gate`: без `revisit_when` линтер возвращает `ERROR` с упоминанием `revisit_when` |

## Ревью и приёмка

Глава: [Ревью и приёмка](review-acceptance.md).

### Где читать реализацию

| Вопрос | Файл и символ |
| --- | --- |
| Как получаются текущие target bytes | [review_target_snapshot.py](../../../scripts/review_target_snapshot.py), `build_current_bundle_snapshot()` |
| Где единая проверка current proof | [plan_lint.py](../../../scripts/plan_lint.py), `preflight_current_review_proof()` |
| Как проверяются lanes и общий artifact | [review_artifact_lint.py](../../../scripts/review_artifact_lint.py), `lint_review_artifacts()`; CLI selector `--select-risk-lane` |
| Как current review влияет на readback | [plan_status_oracle.py](../../../scripts/plan_status_oracle.py), `classify_review_readback()` |
| Как читается принятие Architect в sibling | [sibling_closeout.py](../../../scripts/sibling_closeout.py), `_arch_acceptance()` и `validate_done_admission()` |
| Где описана ответственность Architect | [architect.md](../../roles/architect.md), раздел `Architect arch review` |
| Как Manager запускает две линии Reviewer и скрипт выбора между ними | [manager_collab_pipeline.md](../../tools/prompts/manager_collab_pipeline.md), подпункт `4c) Reviewer logical dispatch` |
| Как команда выбирает политику коммита | [planveyor.zsh](../../../scripts/planveyor.zsh), `planveyor_sibling()` и `_planveyor_role_prompt_body()` |

### Что проверяют тесты

| Именованный тест | Точные проверки и предел вывода |
| --- | --- |
| [test_review_artifact_lint.py](../../../scripts/test_review_artifact_lint.py): `test_final_status_without_risk_lane_is_reported`, `test_final_status_without_contracts_lane_is_reported` | Каждый удаляет соответствующую lane секцию и требует один finding `missing_final_lane_sections` с её именем. Это структурная полнота финального artifact, не экспертное качество review |
| [test_review_artifact_lint.py](../../../scripts/test_review_artifact_lint.py): `test_select_risk_lane_cli_preflights_referenced_support_before_selected` | Проверяет код `0`, `state=selected`, совпадающий `run_id` и неизменность plan/support bytes. Fixture использует `BUNDLE=staged`; это не самостоятельный proof всей current-bundle цепочки |
| [test_review_artifact_lint.py](../../../scripts/test_review_artifact_lint.py): `test_final_dual_lane_rejects_stale_matching_current_bundle_hash` | Требует finding `current_review_proof_compact_snapshot_invalid` и отсутствие `dual_lane_target_snapshot_mismatch`: два одинаковых claims ещё могут быть непригодным current proof |
| [test_sibling_closeout.py](../../../scripts/test_sibling_closeout.py): `test_arch_verdict_uses_only_unique_actual_section_and_first_line` | Непринятие, условная/вторая строка, duplicate section и fenced пример вызывают `Blocked`; state не меняется. Точный verdict принимается и в верхнем регистре. Fixture context не доказывает реальный role run |
| [test_review_artifact_lint.py](../../../scripts/test_review_artifact_lint.py): `test_select_risk_lane_cli_blocks_referenced_support_and_clears_identity` | Подробный файл записи содержит развёрнутый путь к интерпретатору Homebrew: код `1`, `state=blocked`, `error_code=expanded_homebrew_python_command_evidence`; `selected_line`, `run_id` и `target_snapshot` пустые |
| [test_sibling_runbook.py](../../../scripts/test_sibling_runbook.py): `test_direct_native_after_human_call_ignores_ambient_selector_and_history` | После `planveyor sibling architect` задание Architect содержит `COMMIT_POLICY=human_explicit`; следующий прямой вызов `planveyor_arch` через фасад получает `COMMIT_POLICY=native_existing`, хотя в окружении задано `PLANVEYOR_SIBLING_COMMIT_POLICY=human_explicit`; индекс остаётся пустым. Клиент Codex в fixture заменён скриптом, который только записывает задание |

## Закрытие задачи

Глава: [Закрытие задачи](closeout.md).

### Где читать реализацию

| Вопрос | Файл и символ |
| --- | --- |
| Как `close` проверяет задачу и делает оба коммита, а `ready` читает итог | [sibling_closeout.py](../../../scripts/sibling_closeout.py), `handle_close()` и `handle_ready()` |
| Как собирается, ставится в индекс и проверяется точный набор файлов | [planveyor.zsh](../../../scripts/planveyor.zsh): `planveyor_plan_bundle`, `planveyor_plan_closeout_preflight` |
| Как классифицируется закрытие документов и в каком порядке вызываются роли | [docs_closeout.py](../../../scripts/docs_closeout.py): `classify_docs_closeout` и `DISPATCH_FAMILY` |
| Чем запускаются роли двух этапов | [docs_finalize.zsh](../../../scripts/planveyor/docs_finalize.zsh): публичные role wrappers двух семейств |
| Кто записывает предложения по процессу | [process_improvements_collect.py](../../../scripts/process_improvements_collect.py) |
| Кто записывает отложенные задачи | [followups_apply.py](../../../scripts/followups_apply.py) |
| Как строится сообщение коммита документов | [followups_capture.py](../../../scripts/followups_capture.py), `_resolve_commit_message()` |
| Почему план в `Done` не может держать открытые пункты `## Post-merge gate` | [plan_lint.py](../../../scripts/plan_lint.py), `validate_done_post_merge_gate_checklist()` |

### Что проверяют тесты

| Именованный тест | Точные проверки и предел вывода |
| --- | --- |
| [test_docs_closeout.py](../../../scripts/test_docs_closeout.py): `test_terminal_commit_ready_remains_blocked_until_semantic_commit_materializes` | Требует `blocked` и `semantic_closeout_commit_pending`; готовность коммита не засчитывается как его выполнение |
| [test_docs_closeout.py](../../../scripts/test_docs_closeout.py): `test_dispatch_family_orders_general_then_followups` | Проверяет точные восемь пар role/lane, а не реальный запуск восьми ИИ-сессий |
| [test_sibling_closeout.py](../../../scripts/test_sibling_closeout.py): `test_preview_and_declined_gates_have_no_status_index_or_history_effects` | `close` без `--commit` возвращает `semantic_ready`, полный список путей и сообщение коммита; `HEAD`, индекс и байты плана не меняются, статус не ставится, Manager не вызывается |
| [test_sibling_closeout.py](../../../scripts/test_sibling_closeout.py): `test_done_with_canonical_pending_semantic_delta_can_be_committed` | План в `Done` с незакоммиченным набором (`semantic_closeout_has_unstaged_delta`): `close` возвращает `semantic_ready`, `close --commit` — `semantic_committed`, изменённый целевой файл попадает в коммит |
| [test_sibling_closeout.py](../../../scripts/test_sibling_closeout.py): `test_ready_does_not_run_stack_commands_and_blocked_noop_is_not_ready` | При `state=blocked` закрытия документов `ready` возвращает `pending` и не вызывает `make`, `planveyor_plan_lint` и `planveyor_manager_init` |

## Тесты и доказательства: чему можно доверять

Глава: [Тесты и доказательства: чему можно доверять](testing-evidence.md).

### Где читать реализацию

| Вопрос | Файл и ключевой символ |
| --- | --- |
| Как проверяется форма плана | [plan_lint.py](../../../scripts/plan_lint.py), `lint_plan()` |
| Как проверяется набор файлов задачи | [planveyor.zsh](../../../scripts/planveyor.zsh), `planveyor_plan_bundle()` с режимами `--preflight` и `--check` |
| Как считается снимок целевых файлов для ревью | [review_target_snapshot.py](../../../scripts/review_target_snapshot.py), `build_current_bundle_snapshot()`, `_bundle_sha256()` |
| Как ревью сверяется с текущими файлами | [plan_lint.py](../../../scripts/plan_lint.py), `preflight_current_review_proof()`, `select_plan_risk_lane_snapshot()` |
| Как Oracle читает состояние ревью и выбирает роль | [plan_status_oracle.py](../../../scripts/plan_status_oracle.py), `classify_review_readback()`, `review_operational_route()` |
| Почему `planveyor sibling close` отказывает при устаревшем ревью | [sibling_closeout.py](../../../scripts/sibling_closeout.py), `validate_done_admission()`: требует `review_readback_state=ok`; повторная сверка ответа Oracle в `handle_close()` перед коммитом. Строку `Вердикт: принято.` отдельно проверяет `_arch_acceptance()` |

### Что проверяют тесты

| Именованный тест | Точные проверки и предел вывода |
| --- | --- |
| [test_review_artifact_lint.py](../../../scripts/test_review_artifact_lint.py): `test_select_risk_lane_cli_blocks_stale_or_removed_current_producer_target` | На временном Git-репозитории выбор записи линии рисков сначала возвращает `selected`. После правки целевого файла — код `1`, `state=blocked` и `current_review_proof_producer_mismatch`; после удаления файла — `current_review_proof_producer_or_support_unavailable`. Живой запуск ролей тест не делает |
| [test_plan_status_oracle.py](../../../scripts/test_plan_status_oracle.py): `test_green_review_snapshot_mismatch_routes_to_reviewer_and_blocks_terminal_state` | Подменяет lint ревью находкой о несовпадении снимка (`current_bundle_target_snapshot_mismatch` или `dual_lane_target_snapshot_mismatch`) и ждёт `stale_green_review`, маршрут `reviewer_same_file_rewrite_required`, следующую роль Reviewer и `terminal_ready_state=blocked`. Сам lint ревью в этом тесте заменён |
| [test_sibling_closeout.py](../../../scripts/test_sibling_closeout.py): `test_early_status_red_or_stale_review_and_owner_question_block` | Подменяет ответ Oracle: статус до приёмки, `stale_green_review`, `live_blocker`, открытый вопрос Owner или сработавшая защита маршрута. В каждом случае `handle_close()` с `--commit` отказывает, а HEAD, индекс и файл плана остаются прежними |

## Sibling: создание и обновление

Глава: [Sibling: создание и обновление](sibling-lifecycle.md).

### Где читать реализацию

| Вопрос | Файл и ключевой символ |
| --- | --- |
| Человеческий слой выбора и следующего действия | [sibling_runbook.py](../../../scripts/sibling_runbook.py): `handle_init`, `handle_upgrade` |
| Создание, проверка и перенос контракта | [consumer_contract.py](../../../scripts/consumer_contract.py): `init`, `upgrade`, `local_sections`, `notices`, `adaptation_plan`, `doctor` |
| Почему `sibling upgrade` при остановке с кандидатом не показывает причину | [sibling_runbook.py](../../../scripts/sibling_runbook.py): `Context.call` при ненулевом коде показывает только stderr, а `main` в [consumer_contract.py](../../../scripts/consumer_contract.py) печатает JSON с `problems` и `candidate` в stdout |
| Коммит плана, закрытие документов и готовность | [sibling_closeout.py](../../../scripts/sibling_closeout.py): `handle_close` показывает набор файлов, с `--commit` переводит принятый план в `Done` и коммитит его точный набор, а после хода Manager отдельным вызовом коммитит документы; `handle_ready` только читает состояние контракта, плана и закрытия документов |

| Маршрут | Каноническая инструкция | Точка входа в реализацию |
| --- | --- | --- |
| Init | [Руководство по sibling](../stack-sibling.ru.md), создание проекта | [sibling_runbook.py](../../../scripts/sibling_runbook.py): `handle_init()` → [consumer_contract.py](../../../scripts/consumer_contract.py): `init()` |
| Upgrade | [Руководство по sibling](../stack-sibling.ru.md), получение новой версии | [sibling_runbook.py](../../../scripts/sibling_runbook.py): `handle_upgrade()` → [consumer_contract.py](../../../scripts/consumer_contract.py): `upgrade()` и `adaptation_plan()` |

Имена Python-функций в таблице — адреса для чтения реализации. Пользовательские вызовы берутся из guide и `planveyor_help`; внутренние helpers не следует превращать в альтернативный публичный интерфейс.

### Что проверяют тесты

| Именованный тест | Точные проверки и предел вывода |
| --- | --- |
| [test_consumer_contract.py](../../../scripts/test_consumer_contract.py): `test_compatible_upgrade_preserves_local_section_and_swaps_only_after_checks` | Проверяет неизменность original до swap, bytes секции в target и backup, наличие плана и результат `updated_pending_adaptation` |
| [test_consumer_contract.py](../../../scripts/test_consumer_contract.py): `test_acceptance_refuses_uncommitted_candidate_and_preserves_original` | Требует отказ и прежнее состояние original; backup до принятия не появляется |
| [test_consumer_contract.py](../../../scripts/test_consumer_contract.py): `test_acceptance_refuses_lost_local_text_and_preserves_original` | Требует `blocked`, сохранность original и retained candidate даже после его коммита |
| [test_consumer_contract.py](../../../scripts/test_consumer_contract.py): `test_copier_and_lint_failures_retain_only_a_candidate` | При ошибке Copier ждёт `blocked` с `Copier exited 17`; при провале линтера созданного плана обновления — отказ `generated adaptation plan failed lint` и `candidate retained`. В обоих случаях original не меняется, candidate остаётся: план создаётся до замены каталогов |
| [test_sibling_runbook.py](../../../scripts/test_sibling_runbook.py): `test_upgrade_inside_target_refuses_before_any_swap` | `sibling upgrade` из каталога внутри проекта завершается ненулевым кодом со словом «Выйдите» в stderr; HEAD проекта прежний, резервной копии нет |
| [test_sibling_runbook.py](../../../scripts/test_sibling_runbook.py): `test_upgrade_from_outside_preserves_local_sections_and_selects_returned_plan` | Снаружи с `--project`: в выводе «адаптация ещё открыта», локальный текст сохранён, текущий план — `contract_upgrade_` со статусом `architect initial draft`, резервная копия одна |

Эти assertions устанавливают механику переноса на fixture. Они не принимают stack brief, не запускают реальные роли и не доказывают работоспособность вашего продукта.

## Обмен изменениями с Planveyor

Глава: [Обмен изменениями с Planveyor](change-packets.md).

### Где читать реализацию

| Вопрос | Файл и ключевой символ |
| --- | --- |
| Формат извещения и его путь в план обновления | [Формат notice](../../contract_notices/README.md) и [consumer_contract.py](../../../scripts/consumer_contract.py): `validate_notice`, `notices`, `adaptation_plan` |
| Импорт запроса и ACK | [upstream_request.py](../../../scripts/upstream_request.py): `cmd_import`, `cmd_ack`. `_ensure_source_local` сравнивает корень проекта с корнем движка; оба корня передаёт обёртка `_planveyor_upstream_request_helper_run` в [planveyor.zsh](../../../scripts/planveyor.zsh). `ack` не принимает ссылку на исполнение без ссылки на решение и не проверяет, существуют ли файлы по ссылкам (F28) |
| Адресный пакет и итог получателя | [rollout_packet.py](../../../scripts/rollout_packet.py): `cmd_create`, `cmd_adoption_plan`, `cmd_outcome_set`, `cmd_ack`; полный словарь итогов — `CANONICAL_TARGET_OUTCOMES`, неизвестное значение отвергается |
| Ownership между source и target | [Rollout ADR](../../adr/005-rollout-packet-is-handoff-not-execution.md) |
| Почему проверка после слияния не создаёт пакетов для sibling | [post_merge_packetization_gate.py](../../../scripts/post_merge_packetization_gate.py): пустая таблица `EXPLICIT_TARGET_APPLICABILITY`; производственный код не выводит обязательство sibling по догадке |

| Маршрут | Каноническая инструкция | Точка входа в реализацию |
| --- | --- | --- |
| Upstream | [CONTRIBUTING](../../../CONTRIBUTING.ru.md) и [Lifecycle и пакеты](../lifecycle-and-packets.ru.md) | [upstream_request.py](../../../scripts/upstream_request.py): `cmd_import()` и `cmd_ack()`; [шаблон запроса](../../upstream_packets/_template.md) |
| Rollout | [Lifecycle/packets](../lifecycle-and-packets.ru.md) | [rollout_packet.py](../../../scripts/rollout_packet.py): `cmd_create()`, `cmd_adoption_plan()`, `cmd_outcome_set()`, `cmd_reconcile()` |

### Что проверяют тесты

| Именованный тест | Точные проверки и предел вывода |
| --- | --- |
| [test_consumer_contract.py](../../../scripts/test_consumer_contract.py): `test_validate_notice_requires_five_clean_fields_and_every_array_item` | Проверяет формат всех пяти полей, включая каждую строку массива; семантическую полезность инструкции он не оценивает |
| [test_consumer_contract.py](../../../scripts/test_consumer_contract.py): `test_unreadable_non_deleted_notice_refuses_upgrade_before_candidate_or_backup` | Нечитаемое извещение в диапазоне даёт отказ `cannot read notice in source history`; состояние source и target прежнее, ни candidate, ни backup не появляются |
| [test_upstream_request.py](../../../scripts/test_upstream_request.py): `test_import_creates_source_local_process_row_and_updates_packet` | Требует PI-файл, статус `imported` и пустые decision/execution refs: import ещё не решение |
| [test_upstream_request.py](../../../scripts/test_upstream_request.py): `test_import_rejects_wrong_root_without_mutation` | Импорт с корнем репозитория, отличным от корня Planveyor, завершается кодом 1 и сообщением `source-local only`; запрос не меняется, у цели не появляется `docs/process_improvements` |
| [test_upstream_request.py](../../../scripts/test_upstream_request.py): `test_ack_rejects_execution_without_decision_and_does_not_mutate` | Требует отказ и неизменный request при execution ref без decision ref |
| [test_rollout_packet.py](../../../scripts/test_rollout_packet.py): `test_target_inbox_json_exposes_imported_as_awaiting_target_outcome` | Явно проверяет ожидание target outcome после ACK import |
| [test_rollout_packet.py](../../../scripts/test_rollout_packet.py): `test_reconcile_target_readback_accepts_only_structured_outcomes` | Принимает ровно соответствующий structured carrier, отвергает prose-only и несовпадающие id/path; bytes source и target остаются прежними |

Это helper fixtures, не доказательство отправки GitHub issue, принятия fix или завершённого rollout в вашем проекте.

## Что уже работает и что дальше

Глава: [Что уже работает и что дальше](capabilities-boundaries.md).

### Где читать реализацию

| Граница | Файл и ключевой символ |
| --- | --- |
| Какие версии Python пропускает проверка при запуске (3.10–3.12; поддерживается только 3.12) | [_pybin.sh](../../../scripts/_pybin.sh), `planveyor_pybin_validate_version()`; `requires-python` в [pyproject.toml](../../../pyproject.toml) |
| Явное восстановление очереди (F23) | [planveyor.zsh](../../../scripts/planveyor.zsh), `planveyor_q_recover()`; [plan_queue.py](../../../scripts/plan_queue.py), команда `recover` |
| Извещения при обновлении sibling (F27) | [consumer_contract.py](../../../scripts/consumer_contract.py), `validate_notice()`, `notices()`, `adaptation_plan()` |
| Адресные пакеты (F29) | [rollout_packet.py](../../../scripts/rollout_packet.py); команды `planveyor_rollout_packet_*` в [planveyor.zsh](../../../scripts/planveyor.zsh) |
| Деление путей при ревью диапазона (F43) | [range_review_risk_packet.py](../../../scripts/range_review_risk_packet.py), `RUNTIME_PREFIXES`, `classify_changed_paths()` |
| Файлы настроек проверки после слияния в sibling | [merge_gate_policy.py](../../../scripts/merge_gate_policy.py), `POLICY_PATH`, `_policy_for_context()`; [review_range_scaffold_engine.py](../../../scripts/review_range_scaffold_engine.py), `_engaged_inputs()`; [contract_authority_context.py](../../../scripts/contract_authority_context.py), `read_declared_bytes()` |
| Команды `planveyor sibling` | [sibling_runbook.py](../../../scripts/sibling_runbook.py): подкоманды `init`, `plan`, `architect`, `answer`, `run`, `close`, `ready`, `upgrade` |
| Какой клиент допустим для какой роли | [planveyor.zsh](../../../scripts/planveyor.zsh), `planveyor_runner_set()`: Architect, Coder и Manager — только `codex`; Planner и Reviewer — `codex` или `claude` |

### Что проверяют тесты

| Именованный тест | Точные проверки и предел вывода |
| --- | --- |
| [test_consumer_contract.py](../../../scripts/test_consumer_contract.py): `test_validate_notice_requires_five_clean_fields_and_every_array_item` | Извещение без любого из пяти полей, с полем неверного типа, с пустым или многострочным `summary` отвергается с `invalid notice schema`. Тест проверяет форму извещения; когда извещение обязательно, он не определяет (F27) |
| [test_planveyor_review_range_init.py](../../../scripts/test_planveyor_review_range_init.py): `test_local_v2_semantic_provenance_uses_current_content_metadata` | Помощник `_run_local_v2_render` сам записывает `review_range_policy.v1.json` во временный проект и только потом запускает подготовку ревью диапазона; тест ждёт код `0` и первым входом квитанции `policy_json`. В sibling, созданном из шаблона, этого файла нет |

## Запуск: команды, обёртки, клиенты

Глава: [Запуск: команды, обёртки, клиенты](runtime-launch.md).

### Где читать реализацию

| Что вы хотите понять | Где читать | Что искать |
| --- | --- | --- |
| Как выбираются движок и проект | [bin/planveyor](../../../bin/planveyor) | Обработка `--project`, отдельная ветка `sibling`, запуск дочернего `zsh -df` |
| Как имя команды попадает в обработчик | [scripts/planveyor.zsh](../../../scripts/planveyor.zsh) | `planveyor_cli()` и `planveyor_sibling()` |
| Как устроены обычные действия Owner | [scripts/sibling_runbook.py](../../../scripts/sibling_runbook.py) | `parser()`, `handle_init()`, `handle_answer()`, `handle_upgrade()`; `close` и `ready` — в [scripts/sibling_closeout.py](../../../scripts/sibling_closeout.py), `handle_close()` и `handle_ready()` |
| Как `sibling architect` и `run` готовят сессию | [scripts/planveyor.zsh](../../../scripts/planveyor.zsh) | `_planveyor_sibling_ensure_native_session()`; проверка квитанции — `session_check()` в [scripts/sibling_runbook.py](../../../scripts/sibling_runbook.py) |
| Как выглядит конкретный запуск Architect | [scripts/planveyor/role_runtime.zsh](../../../scripts/planveyor/role_runtime.zsh) | `planveyor_arch()`; это пример одного маршрута, не универсальный алгоритм всех ролей |
| Как создаётся сессия роли | [scripts/planveyor/session_init.zsh](../../../scripts/planveyor/session_init.zsh) | `planveyor_arch_init()`, `planveyor_manager_init()` |
| Откуда берётся инструкция фазы | [scripts/planveyor.zsh](../../../scripts/planveyor.zsh) | `_planveyor_role_prompt_body()`, первой строкой выводит `COMMIT_POLICY=…`; затем [architect_status_driven.md](../../tools/prompts/architect_status_driven.md) |
| Какой клиент допустим для роли | [scripts/planveyor.zsh](../../../scripts/planveyor.zsh) | `planveyor_runner_set()`, `_planveyor_default_runner_for_role()`; вызов Claude Code — `_planveyor_private_provider_claude_direct_run()` в [scripts/planveyor/provider_runtime.zsh](../../../scripts/planveyor/provider_runtime.zsh) |
| Как запускается Manager collab | [scripts/planveyor/role_runtime.zsh](../../../scripts/planveyor/role_runtime.zsh) | `planveyor_manager_collab_cmd()`; алгоритм Manager — [manager_collab_pipeline.md](../../tools/prompts/manager_collab_pipeline.md) |
| Как читается состояние плана | [scripts/plan_status_oracle.py](../../../scripts/plan_status_oracle.py) | `oracle_result()`; публичный wrapper `planveyor_plan_status_oracle()` определён в `scripts/planveyor.zsh` |

### Что проверяют тесты

| Тест | Что проверяет код теста | Граница вывода |
| --- | --- | --- |
| `test_collab_prompt_dispatches_the_configured_role_types` в [test_planveyor_codex_agent_roles.py](../../../scripts/test_planveyor_codex_agent_roles.py) | Prompt называет точные agent types, reuse-механизмы и допустимые collaboration API | Это проверка контракта текста, не фактического ответа модели |
| `test_home_ensure_selects_consumer_home_without_rewriting_agent_roles` в [том же файле](../../../scripts/test_planveyor_codex_agent_roles.py) | Существующая конфигурация выбранного клиента сохраняется; отсутствующие role files не создаются автоматически | Изоляция настройки подтверждается для тестового окружения; аутентификация не проверяется |
| `test_existing_home_startup_reconcile_preserves_root_model_runtime_and_extra_agents` в [том же файле](../../../scripts/test_planveyor_codex_agent_roles.py) | Настроенные Owner модель, runtime-параметры и дополнительные агенты остаются неизменными | Поддержка всех возможных конфигураций из одного теста не следует |
| `test_runner_matrix_readback_and_unknown_runner_fail_closed` в [test_planveyor_init_capture.py](../../../scripts/test_planveyor_init_capture.py) | После `planveyor_runner_set` читает выбор пяти ролей: `claude` у Planner и Reviewer, `codex` у остальных; `coder bogus` даёт `Usage`, `coder claude` — `Unsupported runner for role=coder: claude` | Проверяет выбор клиента, сами клиенты не запускаются |
| `test_custom_reviewer_lane_init_uses_distinct_session_keys_and_runner_matrix` в [том же файле](../../../scripts/test_planveyor_init_capture.py) | При клиенте `claude` у Reviewer две линии получают свои указатели `.planveyor.session.reviewer_code_risk` и `.planveyor.session.reviewer_code_contracts`, общего `.planveyor.session.reviewer` нет; вызов получает `--model`, `--effort`, `-p` и `--permission-mode acceptEdits` | Claude Code в тесте заменён заглушкой |
| `test_architect_wrong_status_refuses_before_native_init` в [test_sibling_runbook.py](../../../scripts/test_sibling_runbook.py) | `sibling architect` при статусе `Ready for Coder` завершается с ошибкой, не вызывает init и не создаёт `.planveyor.session.architect` | Init и обёртки Architect в тесте заменены заглушками |
| `test_actual_architect_cold_init_and_reused_resume_get_current_human_policy` в [том же файле](../../../scripts/test_sibling_runbook.py) | Три вызова `sibling architect` дают четыре вызова Codex: первый (init) идёт без `resume`, все следующие, включая ход в том же первом `sibling architect`, — с `resume`, `PLAN_PATH` и `PRE_STATUS_LINE`; во всех вызовах `COMMIT_POLICY=human_explicit` | Codex заменён заглушкой, которая записывает аргументы и сообщение |
| `test_direct_native_after_human_call_ignores_ambient_selector_and_history` в [том же файле](../../../scripts/test_sibling_runbook.py) | Прямой `planveyor_arch` после `sibling architect` получает `COMMIT_POLICY=native_existing`, даже если в окружении `PLANVEYOR_SIBLING_COMMIT_POLICY=human_explicit`; в индексе Git ничего не появляется | Codex заменён той же заглушкой |
| `test_direct_manager_resume_after_human_run_uses_fresh_native_policy` в [том же файле](../../../scripts/test_sibling_runbook.py) | Прямой `planveyor_manager_collab_cmd run <план>` после `sibling run` продолжает ту же сессию Manager, но с `COMMIT_POLICY=native_existing`, даже если в окружении `PLANVEYOR_SIBLING_COMMIT_POLICY=human_explicit`; файл очереди не появляется | Codex заменён той же заглушкой |

## Как Planveyor меняет себя

Глава: [Как Planveyor меняет себя](self-development.md).

### Где читать реализацию

- [Prompts README](../../tools/prompts/README.md): shared corpus и declared target-local источники.
- [Docs architecture](../../playbooks/docs_architecture.md): source ownership, delivery и производные outputs.
- [planveyor.zsh](../../../scripts/planveyor.zsh): `_planveyor_prompt_file_for_role_phase` и публичные entrypoints.
- [Runtime modules](../../../scripts/planveyor/README.ru.md): назначение и порядок загрузки модулей.
- [check_planveyor_profile_contract.py](../../../scripts/check_planveyor_profile_contract.py): `EXACT_BUNDLE`, `INVARIANT_IDS`, `_check_doc_lint`.
- [build_role_bundles.py](../../../scripts/build_role_bundles.py): сборка runtime-контекста из исходников.
- [shared_docs_mirror_drift.py](../../../scripts/shared_docs_mirror_drift.py): declared mirror membership и read-only report.
- [Collect](../../../scripts/process_improvements_collect.py) и [triage](../../../scripts/process_improvements_triage.py): сбор предложения и поля решения.
- [Promote](../../../scripts/process_improvements_promote.py) и [reconcile](../../../scripts/process_improvements_reconcile.py): execution pointer и подтверждение состояния raw PI.
- [Описание предложений по процессу](../../process_improvements/README.md): статусы строки PI, поля разбора, команды сбора, разбора, привязки и сверки.
- [consumer_contract.py](../../../scripts/consumer_contract.py): `validate_notice()` проверяет пять полей извещения, `notices()` читает извещения диапазона коммитов, `adaptation_plan()` переносит в план обновления путь, коммит и `summary` извещения (в `## Scope`), `checks` (в `## Tests`) и `sibling_actions` (строками «Действие:» в `## Evidence`).
- [docs_closeout.py](../../../scripts/docs_closeout.py): `classify_docs_closeout()`; правка общих промптов, плейбуков и ряда шаблонов при закрытии документов даёт `final_docs_commit_reason=canon_delta_requires_process_improvement`.
- [Извещения контракта](../../contract_notices/README.md): где лежат извещения и как обновление их читает.

### Что проверяют тесты

В [test_check_planveyor_profile_contract.py](../../../scripts/test_check_planveyor_profile_contract.py) `test_doc_lint_rejects_comment_only_dispatch` заменяет owning вызов комментарием и требует finding `doc_lint_gate`.
Это показывает, что наличие текста команды не считается достаточным dispatch contract.
`test_doc_lint_rejects_unrelated_function_dispatch` также отвергает перенос нужного текста в постороннюю функцию.
Эти fixtures не исполняют doc lint и не проверяют качество документов нового изменения.

В [test_build_role_bundles.py](../../../scripts/test_build_role_bundles.py) `test_target_local_content_fails_closed_without_engaged_consumer_contract` требует код 3, отсутствие XML и отсутствие вызова `_build_context`.
Assertion проверяет остановку до сборки fallback; он не доказывает, что client session получила правильную модель.

В [test_shared_docs_mirror_drift.py](../../../scripts/test_shared_docs_mirror_drift.py) `test_generic_policy_has_no_implicit_target_or_mirror_set` требует generic set с нулём путей.
`test_helper_is_read_only_against_target_files` сравнивает bytes target до и после report.
Они подтверждают declared membership и отсутствие записи, а не доставку обновления.

В [test_process_improvements_promote.py](../../../scripts/test_process_improvements_promote.py) `test_promote_apply_requires_existing_repo_local_ref_and_never_scaffolds_it` требует отказ для missing plan, отсутствие созданного файла и сохранение `triaged`. Он проверяет привязку PI, а не исполнение предложения.

В [test_sibling_contract_docs.py](../../../scripts/test_sibling_contract_docs.py) `test_template_copies_match_their_docs_sources_byte_for_byte` сравнивает каждую копию в `copier_template/` с её исходником в `docs/` или `skills/` побайтно и требует, чтобы каждый скопированный каталог был отмечен как полное или частичное зеркало.
В [test_censor_prompt_contract.py](../../../scripts/test_censor_prompt_contract.py) `test_copier_censor_prompts_deliver_the_shared_final_readback_contract` делает то же для трёх промптов CENSOR.

В [test_planveyor_profile_extraction.py](../../../scripts/test_planveyor_profile_extraction.py) `test_public_checker_uses_only_root_owners_and_passes_finite_fixture` запускает `check_planveyor_profile_contract` на корне Planveyor и ждёт пустой список замечаний; там же проверено, что правил девять. Через этот тест проверка профильного контракта входит в полный прогон юнит-тестов.

В [test_consumer_contract.py](../../../scripts/test_consumer_contract.py) `test_validate_notice_requires_five_clean_fields_and_every_array_item` отвергает извещение без любого из пяти полей, с полем не того типа, с пустой или многострочной строкой.
`test_unreadable_non_deleted_notice_refuses_upgrade_before_candidate_or_backup` проверяет, что нечитаемое извещение останавливает обновление: репозитории не меняются, кандидат и резервная копия не создаются.
`test_current_notice_history_and_strict_notice_are_valid` проверяет все извещения в истории репозитория от корневого коммита до `HEAD` и все текущие файлы в `docs/contract_notices/`.

В [test_docs_closeout.py](../../../scripts/test_docs_closeout.py) `test_final_docs_commit_blocks_unowned_protected_review_canon_delta` меняет защищённый шаблон ревью после `Done` и ждёт `final_docs_commit=required` с причиной `canon_delta_requires_process_improvement`; путь шаблона попадает в `protected_docs_delta_paths` и в передачу Architect.

## Проверка после слияния

Глава: [Проверка после слияния](postmerge.md).

### Где читать реализацию

| Вопрос | Файл и символ |
| --- | --- |
| Как Manager ведёт шаги трекера | [manager_collab_merge_pipeline.md](../../tools/prompts/manager_collab_merge_pipeline.md), команда `MANAGER_CMD=merge_run` |
| Какой шаг следующий | [merge_tracker_oracle.py](../../../scripts/merge_tracker_oracle.py) |
| Как запускается режим merge | [role_runtime.zsh](../../../scripts/planveyor/role_runtime.zsh), `planveyor_merge_collab_cmd()` и `planveyor_merge_apply_collab_cmd()` |
| Обёртки отдельных шагов | [planveyor.zsh](../../../scripts/planveyor.zsh): wrappers merge-шагов |
| Почему проекту с маркером нужен файл политики шагов | [merge_gate_policy.py](../../../scripts/merge_gate_policy.py), `_policy_for_context()` |
| Как создаётся range-review scaffold | [review_range_scaffold_engine.py](../../../scripts/review_range_scaffold_engine.py), `_host_family()` и `run()` |
| Какие файлы ревью диапазона читает в проекте с маркером | [review_range_scaffold_engine.py](../../../scripts/review_range_scaffold_engine.py), `_engaged_inputs()` |
| Где проверка артефакта отдельного шага | [post_merge_receipt_preflight.py](../../../scripts/post_merge_receipt_preflight.py): проверка артефакта отдельного шага |
| Как строится отчёт о пакетах адресной доставки | [post_merge_packetization_gate.py](../../../scripts/post_merge_packetization_gate.py), `build_payload()` |

### Что проверяют тесты

| Именованный тест | Точные проверки и предел вывода |
| --- | --- |
| [test_post_merge_receipt_preflight.py](../../../scripts/test_post_merge_receipt_preflight.py): `test_post_merge_audit_shared_range_requires_active_structural_packetization_report` | Отвергает missing, wrong-range, ambiguous и malformed report; зелёный fixture всё равно имеет `terminal_readiness=not_evaluated` |
| [test_merge_policy_effect_boundaries.py](../../../scripts/test_merge_policy_effect_boundaries.py): `test_matching_generic_consumer_admits_merge_tracker` | Проект с маркером Planveyor и объявленным файлом политики получает трекер: код `0`, в шапке `POLICY_SCHEMA=planveyor_merge_gate_policy.v1` и `AUTHORITY_GENERATION`. Файл политики fixture создаёт сам |
| [test_planveyor_review_range_init.py](../../../scripts/test_planveyor_review_range_init.py): `test_public_shell_generic_consumer_emits_lintable_matching_v2_receipt` | Проект с маркером Planveyor и файлом `review_range_policy.v1.json`: публичная команда `planveyor_review_range_init` даёт код `0`, план ревью несёт запись происхождения `review_range_semantic_provenance.v2` с identity проекта и проходит `plan_lint.py` с кодом `0`. Файл политики fixture создаёт сам |
| [test_merge_gate_policy.py](../../../scripts/test_merge_gate_policy.py): `test_invalid_generic_engaged_consumer_never_falls_back_to_legacy_policy` | Проект с маркером, у которого identity равна `default`, содержит недопустимые символы или расходится с маркером, получает `merge_policy_capability_required`; к встроенному списку шагов движок не откатывается |

## Тесты движка

Глава: [Тесты движка](engine-tests.md).

### Где читать реализацию

| Вопрос | Файл и ключевой символ |
| --- | --- |
| Какие цели запускают тесты и проверки | [Makefile](../../../Makefile): `test-scripts`, `verify`, `verify-full`, `doc-lint` |
| Как выбирается Python и проверяется его версия | [_pybin.sh](../../../scripts/_pybin.sh), `planveyor_pybin_resolve()`, `planveyor_pybin_validate_version()` |
| Как фасад запускает проверки целостности | [planveyor.zsh](../../../scripts/planveyor.zsh), `planveyor_verify()` |
| Как модули регистрируются и выбираются | [verify_suite.py](../../../scripts/verify_suite.py), `register()`, `_REGISTRY`, `_load_modules()` |
| Какие проверки входят в модуль `portability` и когда добавляется поиск тестов | [verify_suite.py](../../../scripts/verify_suite.py), `PortabilityModule.run()`, `check_test_scripts()` |
| Как считаются итог и код возврата | [verify_suite.py](../../../scripts/verify_suite.py), `Result`, `main()`, `_render_plain()`, `_render_json()` |
| Какие корни и ссылки проверяет линтер документации | [planveyor.zsh](../../../scripts/planveyor.zsh), `planveyor_doc_lint()`; [doc_lint.py](../../../scripts/doc_lint.py), `main()`, `lint_file()` |
| Что проверяет пример теста сводки передачи | [plan_handoff_digest.py](../../../scripts/plan_handoff_digest.py), `build_digest()`, `_read_code_draft_host()` |
| Общие помощники фикстур | [process_contract_fixtures.py](../../../scripts/test_support/process_contract_fixtures.py), `run_zsh_fixture()`; [test_contract_authority_support.py](../../../scripts/test_contract_authority_support.py), `AuthorityFixture` |

### Что проверяют тесты

| Файл и тест | Подготовка и assertion | Зачем он нужен |
| --- | --- | --- |
| [test_plan_handoff_digest.py](../../../scripts/test_plan_handoff_digest.py), `test_missing_code_draft_fails_closed` | Создаёт временные plan и review без draft; ожидает `state == "missing"` и blocker с `host == "code_draft"` | Сводка handoff сохраняет остановку при недостающем источнике |
| [test_planveyor_shared_corpus_contract.py](../../../scripts/test_planveyor_shared_corpus_contract.py), `test_generic_reviews_preserve_supplied_spec_and_diff_transport` | В двух playbooks каждый маркер SPEC/DIFF встречается ровно один раз; начало стоит перед концом | Контекст задания и diff имеют однозначные границы |
| [test_verify_suite.py](../../../scripts/test_verify_suite.py), `test_discovery_matches_makefile_and_streams_combined_transcript` | Подставляет процесс с exit `1`, одним ERROR и семью тестами; проверяет argv discovery и `Result(..., "fail", "Ran 7 tests, 1 FAIL/ERROR", ...)` | Агрегатор правильно формирует вызов discovery и интерпретирует transcript подставного процесса |
| [test_verify_suite.py](../../../scripts/test_verify_suite.py), `test_default_run_keeps_fast_integrity_checks_but_omits_unselected_inputs` | Проверяет список обычных integrity checks; discovery и проверки невыбранных plan/archive не вызываются | Быстрая проверка не расширяет своё заявление на отсутствующие входы |
| [test_verify_suite.py](../../../scripts/test_verify_suite.py), `test_full_run_adds_discovery_once_and_omits_portability_module_overlap` | `check_test_scripts` вызван ровно один раз; старый отдельный обход portability-тестов отсутствует | Полный маршрут имеет одну каноническую точку discovery |
| [test_planveyor_admission_integration.py](../../../scripts/test_planveyor_admission_integration.py), `test_real_downstream_na_admission_and_public_refusal_are_state_safe` | Публичный lint принимает fixture с carrier (exit `0`), отклоняет её без carrier (exit `1`); queue и state snapshots совпадают до и после отказа | Проверка допуска работает через facade и сохраняет состояние при отказе |

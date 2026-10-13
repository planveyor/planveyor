# Planveyor terms / Словарь терминов Planveyor

This list keeps the same terms in the English and Russian documentation of Planveyor. People and roles use it when they translate a document in either direction. Find a term here and use its pair. One concept keeps one term in every document. Text in backticks and in code blocks stays as it is. Notes in the tables are in Russian.

Section 1 lists terms written in Latin script in both languages: roles, products, statuses, plan sections, and commands. Section 2 gives the English and Russian forms of translated terms. Section 3 holds approved phrases about the mechanics; use them word for word. Section 4 lists strings that code reads; they are never translated. Section 5 lists wording that must not be used.

Словарь держит одни и те же термины в английской и русской документации Planveyor. Им пользуются люди и роли, когда переводят документ в любую сторону. Найдите термин здесь и возьмите его пару. Одно понятие — один термин во всех документах. Текст в обратных кавычках и в блоках кода не меняется.

В разделе 1 — термины, которые в обоих языках пишутся латиницей: роли, продукты, статусы, разделы плана и команды. В разделе 2 — английские и русские формы переводимых терминов. В разделе 3 — утверждённые фразы о механике, их берут дословно. В разделе 4 — строки, которые читает код, их не переводят. В разделе 5 — запрещённые формулировки.

## 1. Same in both languages / Одинаково в обоих языках

These terms stay in Latin script in Russian text too. Statuses, plan sections, values, and commands go in backticks.

Эти термины и в русском тексте пишутся латиницей. Роли не склоняются: «ответ Architect», «вопрос к Owner». Статусы, разделы плана, значения и команды стоят в обратных кавычках.

### Roles / Роли

| Термин | Примечание |
| --- | --- |
| Owner | Человек, владелец проекта. Сайт расшифровывает роль как «владелец продукта», «product owner». |
| Architect | Роль: план задачи, ответы на смысловые вопросы других ролей, приёмка. |
| Planner | Роль: черновик кода. |
| Coder | Роль: код и тесты по черновику кода, запуск проверок. |
| Reviewer | Роль: ревью в две линии, линия рисков и линия контракта. |
| Manager | Роль-координатор: по статусу плана запускает следующую роль. В тексте можно «координатор Manager». |

### Products and tools / Продукты и инструменты

| Термин | Примечание |
| --- | --- |
| Planveyor | Имя продукта. |
| Codex; Codex CLI | Имя продукта. |
| Claude Code | Имя продукта. |
| ZCode | Агентный харнес. |
| Git; GitHub; GitHub Issues; `gh` | Имена продуктов; `gh` — команда. |
| Copier | Инструмент шаблонов: им Planveyor создаёт и обновляет sibling. |
| SQL Server; MS SQL | Учебный раздел пишет «SQL Server», сайт — «MS SQL». |
| tSQLt; JUnit; JUnit XML; DACPAC; DacFx | Инструменты SQL-примера. |

### Planveyor terms / Термины Planveyor

| Термин | Примечание |
| --- | --- |
| sibling | Отдельный репозиторий проекта, созданный из Planveyor. Внутри фразы пишется со строчной. По-английски также «stack sibling», «sibling repository». |
| Oracle | Скрипт `scripts/plan_status_oracle.py`. Что он делает, сказано в разделе 3, чего не делает — в разделе 5. |
| CENSOR | Второй проход роли по своим файлам перед передачей работы: «второй проход», «second pass». |
| Arch review | Приёмка Architect: «приёмка (Arch review)». Заголовок раздела в файле ревью — в разделе 4. |
| PI | Предложение по процессу (process improvement), запись `### PI-NNN`. По-английски во множественном числе — PIs. |
| ACK | Отметка в Planveyor: решение по запросу из sibling (`planveyor_upstream_request_ack`) или получение адресного пакета. |
| SID | Идентификатор сессии ИИ-клиента. |
| Codex home | Каталог настроек Codex: `PLANVEYOR_CODEX_HOME` или `~/.codex`. |
| Self-Planveyor | Работа над самим Planveyor: проектом служит его корень. |
| doctor | Проверки без запуска модели: `planveyor_entry_doctor`, `planveyor_consumer_doctor`. |

### Developer words / Общие слова разработчиков

| Термин | Примечание |
| --- | --- |
| diff; PR (pull request); CI; ADR; worktree; push | Общепринятые слова разработчиков. |
| hosted CI; GitHub CI | В первой версии hosted CI не запускали. Перевод не утверждает обратного. |

### Plan statuses / Статусы плана

| Термин | Примечание |
| --- | --- |
| `**Status:**` | Строка статуса в шапке плана, одна на план. |
| `Architect initial draft` | Первый статус плана. |
| `Architect draft` | Статус плана. |
| `Ready for Planner` | Передача работы Planner. |
| `Planner intake`; `Planner finalize` | Статусы Planner. |
| `Ready for Architect response`; `Architect response` | Вопрос к Architect по смыслу задачи. |
| `Ready for Coder` | Передача работы Coder. |
| `Coder intake`; `In progress` | Статусы Coder. |
| `Ready for Review` | Передача работы Reviewer. |
| `Reviewer intake`; `Reviewer code review`; `Reviewer visual review` | Статусы Reviewer. |
| `Ready for Arch review` | Работа передана на приёмку. Сам статус приёмкой не считается. |
| `Architect arch review` | Статус приёмки. |
| `Done` | Работа принята и закоммичена. |
| `Superseded` | План заменён новым. Вместе с `Done` это терминальный статус. |

### Plan and review sections / Разделы плана и ревью

| Термин | Примечание |
| --- | --- |
| `## Scope`; `## Evidence`; `## Q&A log`; `## Meta`; `## Review artifacts` | Разделы плана, которые читают скрипты. В шаблоне у части заголовков есть пояснение в скобках. |
| `## Acceptance criteria / DoD`; `## Suggestions log`; `### Reviewer suggestions`; `## Follow-ups (deferred)`; `### Arch review checklist` | Разделы плана и чек-листа приёмки. |
| `## Post-merge gate (before deleting plan)` | Чек-лист на время после слияния. Если задачу закрывают до слияния, раздел заменяют строкой `N/A (why=…)` с причиной. |
| `## Critical invariants / traps / bypass paths` | Раздел черновика кода, по-русски — «ловушки черновика кода». |
| `## Analysis pack`; `## Promoted route artifact` | Разделы плана анализа. |
| `## Plan provenance / session context`; `## Rollout packet handoff` | Разделы плана. |
| `## Lane synthesis / aggregate verdict` | Итоговый раздел файла ревью. |

### Values and codes / Значения и коды

| Термин | Примечание |
| --- | --- |
| `S1 Blocker`; `S2 Risk`; `S3 Nit` | Шкала серьёзности замечаний ревью. |
| `COMMIT_POLICY`; `human_explicit`; `native_existing` | Политика коммита и её значения. |
| `selected`; `missing`; `blocked` | Ответы скрипта выбора записи линии рисков. |
| `PLANNED`; `MISSING-PATH` | Пометки проверки набора файлов. |
| `semantic_closeout_commit_pending`; `semantic_closeout_has_unstaged_delta` | Причины отказа скрипта закрытия. |
| `machine_authority_decision`; `not_applicable` | Решение Architect в разделе `## Meta` плана. |
| `review-only` | Тип плана, который заказывает только ревью. |
| `plan.v2`; `followups.v2` | Версии схем. |
| `developer_wave`; `analysis_wave`; `decomposition_wave` | Коды контуров. |
| `agent_type`; `spawn_agent`; `followup_task`; `list_agents` | Вызовы Codex в режиме collab. |
| `bundle_sha256`; `BUNDLE=current` | Снимок целевых файлов в строке `**Target:**` ревью. |

### Commands and numbers / Команды и номера

| Термин | Примечание |
| --- | --- |
| `planveyor sibling init`, `plan`, `architect`, `answer`, `run`, `close`, `close --commit`, `ready`, `upgrade` | Команды Owner. |
| `F<N>` | Номер пункта в `docs/release_backlog.md`. |

## 2. Translated terms / Переводимые термины

Use the pair from the table. In Russian text, the English term may follow in parentheses on first use. Names from code in the notes stay in backticks.

Берите пару из таблицы. В русском тексте при первом упоминании можно дать английский термин в скобках. Имена из кода в примечаниях стоят в обратных кавычках и не переводятся.

| English | Русский | Примечание |
| --- | --- | --- |
| A successful launch is not acceptance | Успешный запуск — ещё не приёмка | Формулировка сайта. |
| acceptance | приёмка | Решение Architect по результату, Arch review. |
| acceptance criteria | критерии приёмки | Раздел `## Acceptance criteria / DoD`. |
| accepted-red | план, принятый красным | Ревью красное, работу передали преемнику: `terminal_disposition=accepted_red_supersession`. При первом упоминании — с английским именем в скобках. Руководство `docs/guides/accepted-red.md`. |
| active plan pointer | указатель активного плана | Файл `.planveyor.planpath`. |
| adaptation | адаптация |   |
| adoption | принятие | Принятие адресного пакета в целевом проекте. |
| advanced branch | расширенный маршрут | Очередь Manager — «отдельный расширенный маршрут». |
| agent harness | агентный харнес; харнес | Программа вокруг модели, которая ведёт сессию роли: читает и правит файлы, запускает команды, держит песочницу. Примеры: Codex CLI, Claude Code, ZCode. По-английски всегда «agent harness»: голое «harness» означает обвязку стека. По-русски при первом упоминании «агентный харнес», дальше можно «харнес». Выбор харнеса для роли — `runner`. Руководство `docs/guides/harnesses.md`. |
| analysis | анализ | `analysis_wave`. |
| analysis outcome | исход анализа | Решение Architect при приёмке анализа, раздел `## Promoted route artifact`. |
| analysis pack | таблица анализа | Раздел `## Analysis pack`. На русском сайте — «пакет анализа». |
| artifact | артефакт |   |
| assertion | проверка в тесте |   |
| authority | основание решения; полномочия |   |
| backlog | список отложенных задач |   |
| backup | резервная копия | Прежний каталог проекта после обновления. |
| blocker | блокер | Замечание ревью `B<N>` в разделе `## S1 Blocker`. |
| bounded discovery | поиск совпадений в ограниченном объёме | Поиск открытой отложенной задачи по той же теме. |
| bundle check | проверка набора файлов | `planveyor_plan_bundle --preflight` и `--check`. |
| canon | канон | Действующие документы проекта. |
| carrier | запись | Запись, в которой хранится значение. При первом упоминании — с примером. |
| check; gate; verification; validation | проверка | Слово многозначное, английское выбирают по смыслу. «Gate» — проверка, которая разрешает переход: проверки закрытия — «closeout gates». «Verification» — маршрут вроде `make verify`. Ревью — «review», проверка в тесте — «assertion». |
| checkout; Planveyor checkout | копия репозитория; копия Planveyor |   |
| checkpoint | контрольная точка |   |
| checksum | контрольная сумма |   |
| child plan | дочерний план | План одной части большой цели. |
| cleanup | очистка | Режим `--cleanup-rejected` и шаг перед уборкой старых документов. |
| closeout | закрытие | Закрытие задачи. |
| closeout gates | проверки закрытия | Часть утверждённой фразы, раздел 3. |
| code draft | черновик кода | Файл Planner в `docs/code_drafts/`. Не «технический draft». |
| code draft traps | ловушки черновика кода | Раздел `## Critical invariants / traps / bypass paths`. |
| code snapshot | снимок кода | Файлы примера, приложенные к учебному разделу. |
| Codex agent | агент Codex | Агент роли внутри сессии Manager в режиме collab, `agent_type`. Сайт пишет «субагенты Codex», «Codex subagents». |
| collab mode; Manager collab | режим collab | Его запускает `planveyor sibling run`. Справка команды называет его «normal Manager», но «normal» — не название режима. |
| commit | коммит | Решено. На русском сайте местами «сохранение», в документации так не пишут. |
| commit policy | политика коммита | `COMMIT_POLICY`, значения не переводятся. |
| consumer contract | контракт sibling | Правила и файлы, которые проект получил из Planveyor. |
| context reset | сброс контекста |   |
| contour | контур | Вид работы со своим результатом: разработка, анализ или декомпозиция. |
| contract | контракт | Записанные правила, форматы и границы ответственности. |
| contract notice | извещение | JSON-файл в `docs/contract_notices/`: что изменилось и что проекту сделать. |
| contract test | контрактный тест | Тест движка, который проверяет обязательные маркеры в документе или промпте. |
| contracts lane | линия контракта | Решено. `reviewer_code_contracts`. Сайт называет её иначе: «requirements», «требования», «соответствие задаче». |
| Copier answers | ответы Copier; файл ответов Copier |   |
| core | ядро | Только на сайте. В документации — «engine», «движок». |
| current plan; selected plan | текущий план; выбранный план | Путь к нему хранится в `.planveyor.planpath`. |
| custom pipeline | пошаговый режим Manager | Manager по очереди вызывает роли через обёртки, каждую в своей сессии: `planveyor_manager_custom_pipeline_tui`. Не путать с отдельным запуском роли. |
| deadlock | тупик после вопроса Reviewer | В коде — `reviewer_manager_deadlock`. |
| decomposition | декомпозиция | `decomposition_wave`. |
| delivery wave | волна поставки |   |
| dev environment; dev database | dev-среда; dev-база | На сайте — «тестовая БД», «test database». |
| dev target | dev-цель | Выделенная dev-среда, в которую роли публикуют и где запускают тесты. |
| development; dev contour | разработка | Контур по умолчанию, `developer_wave`. |
| direct order check | прямая проверка порядка | Отдельный вызов процедуры в SQL-примере. |
| direct Owner assignment | прямое поручение Owner | На английском сайте — «a separate Owner assignment». |
| dispatch; role call | вызов роли |   |
| doc lint; documentation linter | линтер документации | `planveyor_doc_lint`, `make doc-lint`. |
| docs closeout | закрытие документов | Решено. Варианты «document closeout», «docs tail», «docs finalize» в тексте не используются. Имена `planveyor_docs_closeout` и промптов `*_docs_finalize_*` не меняются. |
| docs hygiene | гигиена документов |   |
| draft | черновик | Статусы вида `Architect draft` не переводятся. |
| drift | расхождение | Например, `routing_carrier_drift`, `head_drift`. |
| engine | движок | Решено. «Ядро» — только на сайте. |
| engine tests | тесты движка | `scripts/test_*.py`. |
| entry point | точка входа |   |
| evidence | доказательства | Результаты проверок, привязанные к версии файлов. Слово «proof» в английских текстах тоже переводится как «доказательство». |
| evidence carriers | записи доказательств |   |
| Evidence is tied to a version of the files | Доказательство привязано к версии файлов | Формулировка сайта. |
| evidence log | журнал проверок | Раздел плана `## Evidence`. |
| exact bundle; exact set | точный набор файлов | Решено, «exact set» — синоним. В учебном разделе — «точный набор файлов плана», коротко — «набор файлов». Скрипт — `planveyor_plan_bundle`. |
| exact proof | точное доказательство |   |
| executable bundle | набор файлов исполняемого плана |   |
| facade | фасад | `bin/planveyor`, общий вход во все команды. |
| final check | финальная проверка | Проверка набора после ревью, ключ `--check`. |
| finding | замечание | Замечание ревью. |
| first release; first version | первый выпуск; первая версия | Решено: «release» — «выпуск». |
| First-release backlog | обязательства первого выпуска | Список `docs/release_backlog.md`. Сам файл пока озаглавлен «Обязательства первого релиза». |
| fixture | фикстура |   |
| follow-up | отложенная задача | Работа, которую решили сделать позже; записи лежат в `docs/followups/`. На русском сайте — «последующие задачи». |
| forensic capture | сохранение доказательств | Сохранение отклонённых байтов, `--capture-rejected`. |
| Git ref | ссылка Git | Например, `refs/planveyor/rejected-baselines/…`. |
| Golden paths | Реестр повторяемых потоков | Название `docs/guides/golden_paths.md`. |
| Guides | Руководства | Название `docs/guides/README.md`. |
| handoff | передача; передача работы |   |
| handoff check | проверка передачи |   |
| handoff digest | сводка передачи работы | `scripts/plan_handoff_digest.py`. |
| harness; stack harness | обвязка; обвязка стека | Решено. Скрипты проекта, которые собирают его, выкладывают в dev-среду и запускают тесты стека. Не путать с агентным харнесом (agent harness). На сайте — «тестовая инфраструктура», «test infrastructure». |
| helper | вспомогательный скрипт |   |
| hidden fallback | скрытый запасной вариант |   |
| intake | первичный разбор задачи |   |
| integrity checks | проверки целостности | `planveyor_verify`. |
| intent | намерение | Слово из слогана сайта. |
| lane; review lane | линия; линия ревью | У Reviewer две линии: линия рисков и линия контракта. |
| Launch and role modes | Запуск и режимы ролей | Название `docs/guides/launch-and-role-modes.md`. |
| lifecycle | жизненный цикл |   |
| Lifecycle and packets | Жизненный цикл и пакеты | Название `docs/guides/lifecycle-and-packets.md`. Учебный раздел пока пишет «Lifecycle и пакеты». |
| live run; live check | живой прогон; живая проверка | Проверки стека на настоящей dev-среде. В английских текстах встречается и «live proof». |
| live target | живая цель | Раздел анкеты стека. |
| local sections | локальные разделы | Заголовки этих разделов не переводятся, см. раздел 4. На русском сайте — «локальные секции». |
| maintainer | сопровождающий |   |
| managed paths | управляемые пути |   |
| manifest | манифест |   |
| matching row | совпавшая запись | Запись списка отложенных задач по той же теме. |
| merge | слияние | Режим `merge` и имена команд пишутся латиницей. |
| merge mode | режим merge | Режим Manager для проверки после слияния. |
| merge tracker | трекер слияния | Локальный файл `.planveyor.merge_tracker.md`. |
| no-op | изменения не нужны; менять нечего | Исход без изменений, например `outcome=no changes needed`. |
| offline tests | тесты без среды; офлайн-тесты | Тесты на подготовленных входах вместо настоящей базы или сервиса. |
| one-shot | разовый |   |
| operator | оператор | Решено. Человек или агент с доступом к dev-базе; такой роли в Planveyor нет. На сайте — «исполнитель с доступом к тестовой БД». |
| operator receipt | квитанция оператора | Квитанция живого прогона: команда, время, код выхода, вывод. |
| ordinary plan | обычный план |   |
| outcome | исход | Исход принятия пакета. |
| Owner guide | Краткое руководство Owner | Название `planveyor_owner_book.md`. |
| Owner question | вопрос к Owner | Его закрывает `planveyor sibling answer`. |
| phase prompt | промпт фазы | Инструкция роли для текущего статуса плана. |
| PI collector | сборщик предложений | `scripts/process_improvements_collect.py`. |
| PI promotion | привязка PI | Статус `promoted`. |
| PI reconciliation | сверка PI | `scripts/process_improvements_reconcile.py --apply`. |
| PI triage | разбор PI |   |
| plan | план | Файл задачи в `docs/plans/`. |
| plan harvest | сбор решений из планов | Шаг `plan_harvest`. |
| plan header | шапка плана |   |
| plan linter | линтер плана | `planveyor_plan_lint`. |
| plan queue | очередь планов | Режим Manager для нескольких связанных планов подряд. |
| plan status | статус плана | Строка `**Status:**` в шапке плана. |
| planning contour | контур планирования | Анализ и декомпозиция. |
| planning wave | волна планирования |   |
| Planning-contour continuity | Непрерывность контура планирования | Название `docs/guides/planning_contour_continuity.md`. |
| playbook | плейбук | Документы в `docs/playbooks/`. |
| pointer (plan pointer, session pointer) | указатель (указатель плана, указатель сессии) | Локальные файлы вида `.planveyor.planpath`. |
| post-merge audit | аудит после слияния | Шаг `post_merge_audit`. |
| post-merge check | проверка после слияния | Проверка диапазона `BASE..HEAD`, уже слитого в основную ветку. |
| preflight | предварительная проверка | Проверка набора перед `Ready for Coder`, ключ `--preflight`. |
| preview | просмотр | Просмотр перед `close --commit`. |
| process improvement (PI) | предложение по процессу (PI) | Записи лежат в `docs/process_improvements/`. |
| product code | код продукта |   |
| product task; first product task | полезная задача; первая полезная задача | Задача проекта после адаптации. |
| product tree | дерево файлов Planveyor |   |
| project; consumer repository | проект | Sibling, в котором работают роли. В README встречается и `target-local`. |
| promotion writer | штатный скрипт продвижения | Продвигает отложенную задачу в план. |
| provenance | происхождение | `planveyor_plan_provenance_stamp`. |
| Q&A log | журнал вопросов | Раздел плана `## Q&A log`. |
| queue activation | включение очереди |   |
| queue admission | допуск в очередь |   |
| queue helper | вспомогательный скрипт очереди |   |
| queue mode | режим очереди |   |
| queue truth | источник истины об очереди |   |
| range review; merge-range review | ревью диапазона | Шаг `review_range`, шаблон `docs/code_reviews/_template_merge_range.md`. |
| readback | чтение состояния |   |
| receipt | квитанция | Запись о выполненном действии и его результате. |
| recovery | восстановление | Восстановление прерванной сессии Manager. |
| recovery plan | план восстановления | Отдельный план исправления после плана, принятого красным. |
| reorder level | уровень пополнения | Столбец `ReorderLevel`. Рядом `UnitsInStock` — «In stock» и `UnitsOnOrder` — «On order». |
| replace refs | замещающие ссылки Git | `git replace`. |
| restamp | заново поставить отметку на пакете |   |
| review; review artifact | ревью | Файл ревью лежит в `docs/code_reviews/` или `docs/doc_reviews/`, по-английски это «review artifact». |
| review assets | приложения к ревью | Каталог `docs/code_reviews/assets/`. |
| review freshness | свежесть ревью | Часть утверждённой фразы, раздел 3. |
| risk lane | линия рисков | `reviewer_code_risk`. На сайте — «Риски реализации», «Implementation risks». |
| risk selector | скрипт выбора записи линии рисков | `scripts/review_artifact_lint.py --select-risk-lane`. |
| role definition | документ роли | Документы в `docs/roles/`. В README ссылка на них называется «Role definitions». |
| rollout; rollout packet | адресная доставка; адресный пакет | Пакет изменения для одного репозитория, каталог `docs/rollout_packets/`. |
| route | маршрут | Часть утверждённой фразы, раздел 3. |
| route recommendation | рекомендация Coder | Поле `route_recommendation`. |
| route truth; routing truth | источник истины о маршруте | Текущий план и Oracle. |
| runner | агентный харнес роли | Выбор агентного харнеса для роли: Codex или Claude Code. Так в коде: `.planveyor.runner.<role>`, `planveyor_runner_set`. Идентификатор `runner` не переводится. |
| running example; end-to-end example | сквозной пример |   |
| runtime | копия Planveyor, из которой идут команды | Решено: по-английски «runtime» — только эта копия, как в `PLANVEYOR_RUNTIME_ROOT`. В остальных случаях «движок» по-английски — «engine». |
| runtime pin | привязка к копии Planveyor, из которой идут команды |   |
| sanitizer | очистка от личных данных |   |
| scope | границы задачи | Раздел плана — `## Scope`. |
| scope expansion | расширение границ задачи | `plan_meta.scope_expansion`. |
| second pass | второй проход | Проход CENSOR. |
| secrets; private local paths | секреты; личные пути |   |
| selectors | указатели | Локальные файлы `.planveyor.*`. |
| session; role session | сессия; сессия роли |   |
| session key | ключ сессии | Имя сессии роли в `.planveyor.session.<key>`. |
| shortage | дефицит | Столбец `Shortage` в SQL-примере. |
| sibling template | шаблон sibling | Каталог `copier_template/`. |
| single-role launch | отдельный запуск роли | Owner сам запускает одну роль через её обёртку. На сайте режим подписан «По шагам» и «Запускать выбранную роль», по-английски — «Step by step» и «Launch a chosen role». Не путать с пошаговым режимом Manager. |
| skill; plan skill | скилл; скилл плана | Скилл плана — `$planveyor-plan-draft`. |
| snapshot | снимок |   |
| source identity | идентичность исходников | При первом упоминании — с английским термином в скобках, как в `README.ru.md`. |
| source plan | исходный план |   |
| source repository | исходный репозиторий |   |
| stack adaptation plan; adaptation plan | план адаптации под стек | Первый план нового sibling. |
| stack brief | анкета стека | Файл `stack_brief.md` в `docs/` проекта, шаблон — `docs/_template_stack_brief.md`. |
| stack sibling runbook; stack sibling guide | руководство по sibling | `docs/guides/stack-sibling.md`. Не «runbook sibling» и не «постоянная инструкция». |
| Stack sibling: create, set up, and work | Sibling под свой стек: создание, настройка, работа | Так README и оглавление руководств ссылаются на `docs/guides/stack-sibling.md`. Заголовок самого руководства — «Sibling под свой стек». |
| stage (Git) | добавить в индекс |   |
| step limit | лимит шагов | Сколько шагов Manager делает за один запуск. |
| structural checks | проверки формы | Линтер плана, Oracle и проверка набора файлов. |
| successor | преемник | План-преемник, `plan_meta.next_plans`. |
| target snapshot | снимок целевых файлов | `bundle_sha256` в строке `**Target:**` ревью. |
| target stub | заглушка целевого файла | Файл с пометкой `replace before Ready for Review`. |
| targets; target files | целевые файлы | Поле `code_draft_meta.targets` черновика кода. |
| task commit | коммит задачи | В него попадают изменённые файлы точного набора, и только они. |
| terminal status | терминальный статус | `Done` или `Superseded`. Слово «terminal» в коде относится к статусу плана. |
| trace | трасса | Например, собственные трассы сессий ИИ-клиента. |
| tSQLt class marker | метка класса tSQLt | Расширенное свойство `tSQLt.TestClass`. |
| Turn intent into a result you can accept | Довести намерение до результата, который можно принять | Слоган сайта. |
| umbrella plan | зонтичный план | Главный план декомпозиции. |
| upgrade | обновление | Обновление sibling, `planveyor sibling upgrade`. |
| upgrade candidate | кандидат обновления | Копия проекта с новой версией Planveyor; принимают её ключом `--accept-candidate`. |
| upgrade plan | план обновления | План, который создаёт `planveyor sibling upgrade`. Вывод команды называет этот же план «план адаптации» / «adaptation plan»; английский сайт также пишет «adaptation plan». В документации «план обновления» / «upgrade plan» отличает его от первого плана адаптации sibling под стек. |
| upstream request | запрос в Planveyor | Файл по шаблону `docs/upstream_packets/_template.md`; Owner отправляет его в GitHub Issues. В английских текстах тот же запрос называют также «request», «proposal» и «upstream packet». |
| verdict; aggregate verdict; overall verdict | вердикт; итоговый вывод | Итоговый вывод — раздел `## Lane synthesis / aggregate verdict` файла ревью. |
| verification suite; verification routes | маршруты проверки | `docs/tools/verify_suite.md`. |
| visual check | визуальная проверка |   |
| wrapper | обёртка | Функция движка, которая готовит ход роли и запускает клиент. |

## 3. Approved phrases / Утверждённые фразы

These phrases describe the mechanics in public texts. Use them whole and do not retell them in other words.

Этими фразами публичные тексты описывают механику. Их берут целиком и не пересказывают своими словами.

| English | Русский | Примечание |
| --- | --- | --- |
| Oracle checks status, route, and review freshness | Oracle проверяет статус, маршрут и свежесть ревью |   |
| a separate review lane checks the result | результат проверяет отдельная линия ревью |   |
| receipt and closeout gates authorize progress | переход разрешают квитанции и проверки закрытия |   |
| chat is transport; the plan is durable semantic state | чат — транспорт, план — долговечное состояние задачи |   |
| green CI is evidence, but not sufficient on its own | зелёный CI — доказательство, но не достаточное само по себе |   |
| self-report may contribute evidence, but cannot override an authoritative gate | самоотчёт модели может быть доказательством, но не отменяет проверку | Русская фраза говорит «самоотчёт модели», английская — просто «self-report». Так утверждено. |
| derived from a private industrial AI delivery stack | вырос из закрытого промышленного стека разработки с ИИ | Публичная формулировка происхождения. Названия закрытых проектов не приводятся. |

## 4. Strings that code reads / Строки, которые читает код

Scripts look for these strings, so they are not translated in either language. English documents quote them word for word, in Russian, in backticks; a translation may follow in parentheses as an explanation. The last column of the first table shows the English form proposed for a future language mode. It is not in effect yet: code does not read it, except where noted.

Эти строки ищут скрипты, поэтому их не переводят ни в русском, ни в английском тексте. Английский документ цитирует их дословно, по-русски, в обратных кавычках; перевод можно дать в скобках как пояснение. В последней колонке первой таблицы — английская форма, предложенная для будущего режима языка. Она пока не действует: код её не читает, кроме отмеченного случая.

### Russian only / Только по-русски

| Строка | Где стоит и кто читает | Будущая английская форма, пока не действует |
| --- | --- | --- |
| `## Как я понял задачу` | Заголовок плана, обязательный блок Architect. `scripts/plan_lint.py` ищет его как заголовок второго–четвёртого уровня, `scripts/sibling_runbook.py` — строку целиком. Его же пишут генераторы планов. | `## How I understood the task` |
| `Черновик` | Статус файла ревью в строке `**Status:**`, задан в `scripts/review_schema_contract.py`. | `Draft` |
| `ОК:` | Начало первой строки итогового ревью; буквы О и К — кириллица. Читает `scripts/review_artifact_lint.py`, латинское `OK:` сейчас даёт ошибку. Статус `✅ OK` в шапке ревью, наоборот, пишется латиницей. | `OK:` |
| `Замечания:` | Начало первой строки итогового ревью, читает `scripts/review_artifact_lint.py`. | `Findings:` |
| `Вердикт:` | Начало первой строки итогового ревью, читает `scripts/review_artifact_lint.py`. Само по себе слово приёмкой не считается. | `Verdict:` |
| `Вердикт: принято.` | Первая непустая строка раздела `## Архитектурное ревью`: так Architect принимает работу. `scripts/sibling_closeout.py` сравнивает строку целиком, без учёта регистра; перевод приёмкой не засчитается. | `Verdict: accepted.` |
| `## Архитектурное ревью` | Раздел Architect в файле ревью. `scripts/sibling_closeout.py` принимает и `## Arch review`, `scripts/review_artifact_lint.py` знает только русский заголовок. | `## Arch review`; эту форму уже принимает `scripts/sibling_closeout.py` |
| `❌ S1 blocker(ы)` | Статус файла ревью с блокером, задан в `scripts/review_schema_contract.py`. | не выбрана |
| `## Источники` | Начало заголовка в отчётах сбора решений и аудита после слияния, под ним список `- Plans`. Читает `scripts/doc_lint.py`. | не выбрана |
| `## Follow-ups (extracted; без дублей)` | Обязательный раздел отчёта сбора решений из планов. `scripts/plan_harvest_lint.py` сравнивает заголовок целиком. | не выбрана |
| `## Source of truth / precedence (если есть конфликт)`; `## Границы роли (жёстко)`; заголовок, который начинается с `## Обязательный старт (session bootstrap; 1 раз на role` | Разделы документов ролей. `scripts/build_role_bundles.py` собирает их в пакет роли; раздел с изменённым заголовком молча выпадет из пакета. | не выбрана |
| `### Что написать / поправить`; `### Что прогнать` | Подразделы `## Tests` в шаблоне плана. Их же пишут `scripts/followups_promote.py` и `scripts/review_range_scaffold_engine.py`. | не выбрана |
| `**Handoff statuses (кто ставит):**` | Строка шапки плана. Её пишут шаблон и генераторы планов, Oracle читает её по началу `**Handoff statuses`. | не выбрана |
| `## Локальные правила стека`; `## Разрешённое локальное переопределение процесса` | Заголовки локальных разделов в промптах и плейбуках sibling. `scripts/consumer_contract.py` сверяет их побайтно; текст под ними принадлежит проекту. | нет: у английского комплекта ролей будут свои заголовки, их ещё не выбрали |
| строка, которая начинается с `_DO NOT EDIT - производная поверхность;` | Баннер производных сводок предложений по процессу. Его пишет и проверяет `scripts/process_improvements_collect.py`, сводки руками не правят. Код читает и прежний английский баннер, но это другой текст. | не выбрана |
| `Формат:`; `Формат (рекомендованный):` | Строки внутри раздела отложенных задач, которые `scripts/followups_lint.py` пропускает. `Формат:` пишет `scripts/followups_triage.py`. | не выбрана |

### Already read in both languages / Код уже читает на двух языках

Code already accepts an English form of these strings. A translation still quotes the string as it stands in the source.

Для этих строк код уже принимает и английскую форму. Перевод всё равно цитирует строку так, как она стоит в оригинале.

| Русская строка | Английская форма | Где стоит и кто читает |
| --- | --- | --- |
| `Контекст rerun` | `Rerun context` | Заголовок раздела ревью, `scripts/review_artifact_lint.py`. |
| `Визуальные доказательства` | `Visual evidence` | Заголовок раздела ревью, `scripts/review_artifact_lint.py` и `scripts/range_review_risk_packet.py`. |
| `Гигиена exact bundle`; `Гигиена exact-bundle` | `Exact bundle hygiene`; `Exact-bundle hygiene` | Заголовок раздела ревью, `scripts/review_artifact_lint.py`. |
| `этот же review-file`; `этот же review file` | `same review file`; `same review artifact` | Заметка о повторном ревью в разделе `## Review artifacts` плана: так она указывает на нынешний файл ревью. Читают `scripts/plan_lint.py` и `scripts/plan_status_oracle.py`. |
| `findings отсутствуют` | `no findings` | Значение поля `findings` в записи линии рисков, его читает `scripts/review_artifact_lint.py`. |
| `Отсутствуют`; `Нет`; `Не выявлено`; `` Отсутствуют (green verdict; канонические `B<N>` не открывались) `` | строка, которая начинается с `N/A`, `none` или `no` | Текст раздела `## S1 Blocker`, когда блокеров нет; читает `scripts/docs_closeout.py`. Русские варианты — закрытый список, точка в конце допустима. |
| `## Предложение` | `## Suggestion` | Заголовок второго или третьего уровня при импорте предложений по процессу, `scripts/process_improvements_collect.py`. |
| `без delivery` | `no delivery`; `no_delivery_refs`; `delivery_refs=null`; `delivery_refs_null` | Пометка в `triage_note` отложенного предложения без `delivery_refs`, `scripts/process_improvements_collect.py`. |

### Language checks / Проверки языка

`scripts/plan_lint.py` warns when the `plan.v2` plan sections `## Как я понял задачу`, `## Problem`, `## Solution`, `## Decisions`, `## Scope`, `## Out of scope`, and `## Acceptance criteria / DoD` have no Cyrillic text. `scripts/review_artifact_lint.py` reports an error when a final review with status `✅ OK` or `❌ S1 blocker(ы)` has no first line starting with `ОК:`, `Замечания:`, or `Вердикт:` before the lane sections.

`scripts/plan_lint.py` предупреждает, если в разделах плана `plan.v2` `## Как я понял задачу`, `## Problem`, `## Solution`, `## Decisions`, `## Scope`, `## Out of scope` и `## Acceptance criteria / DoD` нет кириллицы. `scripts/review_artifact_lint.py` выдаёт ошибку, если у итогового ревью со статусом `✅ OK` или `❌ S1 blocker(ы)` перед разделами линий нет первой строки с `ОК:`, `Замечания:` или `Вердикт:`.

## 5. Wording not to use / Запрещённые формулировки

Never use this wording, in either language.

Эти формулировки не используются ни в одном языке.

| Не писать | Do not write | Почему |
| --- | --- | --- |
| «Planveyor воспроизводит сессию терминала» | Planveyor replays the terminal session | В коде «terminal» — это терминальный статус плана: `Done` или `Superseded`. |
| «Oracle решает закрытие» | Oracle decides closeout | Oracle проверяет статус, маршрут и свежесть ревью. Переход разрешают квитанции и проверки закрытия. |

### Rejected variants / Отклонённые варианты

These variants were rejected when the pairs in section 2 were chosen. The site still uses some of them.

От этих вариантов отказались, когда выбирали пары раздела 2. На сайте часть из них остаётся.

| Вместо | Пишем | Примечание |
| --- | --- | --- |
| «релиз» | «выпуск», «release» | Заголовок `docs/release_backlog.md` пока «Обязательства первого релиза». |
| «сохранение» в значении «commit» | «коммит», «commit» |   |
| «тестовая инфраструктура», «test infrastructure» | «обвязка», «harness» |   |
| «исполнитель с доступом к тестовой БД», «a participant with access to the test database» | «оператор», «operator» |   |
| «требования», «соответствие задаче», «контракты», «requirements» о второй линии Reviewer | «линия контракта», «contracts lane» |   |
| «runtime» в значении движка | «движок», «engine» | «Runtime» — только копия Planveyor, из которой идут команды. |
| «ядро», «core» | «движок», «engine» | На сайте «ядро» допустимо. |
| «document closeout», «docs tail», «docs finalize» | «закрытие документов», «docs closeout» | Имена команд и промптов не меняются. |
| «по шагам», «пошаговый» об отдельном запуске роли | «отдельный запуск роли», «single-role launch» | «Пошаговый режим Manager» — только «custom pipeline». |

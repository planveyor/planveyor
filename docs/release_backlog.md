# Обязательства первого релиза

Это навигация по принятым исправлениям и оставшимся обязательствам, а не план выполнения или заявление о готовности выпуска. Полные V2 rows находятся в [release follow-ups carrier](followups/release_backlog.md) и [source follow-ups carrier](followups/261009_003241_followups_memory_architect.md). Raw PI rows находятся в [release process-improvements carrier](process_improvements/release__process_improvements_backlog.md) и [source process-improvements carrier](process_improvements/261007_1935_owner_task_sibling_flow__process_improvements_backlog.md). Учёт и dispositions задают raw carriers; этот документ показывает навигацию по ним.

В согласованном объёме ранее приняты 15 пунктов: F11, F15, F18, F20, F21, F23, F31, F36, F38, F41, F42, F44, F46, F47, F48. В public raw carriers сохранены 39 open follow-ups (2 P1 и 37 P2); отдельно 4 open PI в двух carriers. Commit-bound handled rows остаются в private source history и provenance mapping. Ниже сохранены все исходные находки и точный предел каждого принятого закрытия.

Очередь/runQ и предметный пример истории цен (`product_price_audit`) отложены до периода после первой публикации. Наличие guarded recover в F23 не означает сквозной проверки очереди. Первая публикация и последующий обмен issue/обновлениями — разные этапы.

Commit-bound dispositions действуют в private source history. Single-root Genesis сохраняет весь текущий открытый долг по raw carriers: 39 follow-ups и 4 PI; 15 ранее принятых пунктов остаются в сводке. Исходные source_ref открытых rows сохраняются дословно, включая pointers на private source plan; отсутствие этого плана в публичной копии не создаёт новый disposition и не мешает отдельному ordinary поручению Owner.

## Follow-ups

### F1

P1, Coder — нативно проверить runtime и shell contract на Windows.

### F2

P1, Coder — после F1 нативно проверить Linux, включая один аргумент до 128 KiB, BSD/GNU, zsh и native runner.

### F3

P2, Owner — определить, когда измерять и оптимизировать производительность и расход контекста; измерений пока нет.

### F4

P2, Coder — отдельным планом завершить bound family в `scripts/followups_capture.py` по пяти обязательствам D06 P5 (D06 — метка одного из пакетов доработки перед выпуском): helper-owned bind/freeze, строгие identity/source checks, защита от overwrite и pre-manifest drift, безопасные ancestor/leaf paths и ограниченный allowlisted stdin; вместе с ними вернуть защитные тесты.

Из F5–F52 приняты указанные выше 15 пунктов; оставшиеся 33 отложены на период после выпуска первой версии. F1–F4 остаются отдельными открытыми обязательствами.

### F5

P2, Coder — запустить GitHub CI через установленный `gh` и держать его зелёным; первая версия проверена только локально на macOS.

### F6

P2, Coder — проверить другие версии Python: границу загрузчика 3.10–3.12 и новые версии, например 3.13 и 3.14. Первая версия поддерживает только Python 3.12; Windows и Linux — в F1 и F2.

### F7

P2, Architect — восстановление Manager после сбоя: как прерванная сессия восстанавливает состояние маршрута и продолжает pipeline. Живой случай из репетиции sibling на SQL Server: после ошибки перегрузки модели (`Selected model is at capacity`) сброс роли (`planveyor_manager_collab_cmd reset role=reviewer`) стоил около 0,8 млн токенов, а повтор `MANAGER_CMD=analysis` сначала пытается заново создать существующих агентов (`agent path … already exists`) и только потом подбирает их, хотя шаг 3 промпта Manager (`docs/tools/prompts/manager_collab_pipeline.md`) велит до spawn проверить `list_agents`.

### F8

P2, Coder — страховки обновления sibling: переход через версию (A→C), миграция переименованного управляемого файла, повторный init с перечнем переносимого, две версии движка одновременно при смене runtime API, расширенный consumer doctor.

### F9

P2, Coder — кэш authority-преамбулы: не повторять проверки контекста authority в каждой команде; начинать после измерений F3.

### F10

P2, Coder — параллельный post-merge: запускать независимые шаги параллельно после измерений F3.

### F11

**Закрыто в принятом объёме:** Принята инструкция настройки обычных Codex ролей; документальная приёмка не заявляет нового live/provider proof.

Исходная находка:

P2, Coder — описать настройку Codex для основного режима ролей; сейчас используется уже настроенная конфигурация пользователя.

### F12

P2, Architect — коммит из песочницы роли: режим выбирается текущим входом. `planveyor sibling architect` и разовый `planveyor sibling run` сохраняют `human_explicit`: владелец смотрит preview через `sibling close` и отдельно разрешает `sibling close --commit` для конкретного набора. `planveyor sibling tui` открывает штатный Manager TUI с `native_existing`; Architect использует existing exact bundle, simulated Done lint, pre-Done stage/preflight, provisional `Done`, final ordinary lint, restage/preflight и один local exact commit. Failed final gate требует rollback к owning non-Done bytes; последующий docs closeout — отдельный gate, где fresh canonical `no_op` допустим.

Запись в `.git` остаётся конкретной предпосылкой команды: при отказе нужно точное сообщение native preflight и узкий запрос разрешения на показанную команду после проверки полного запроса, без blanket grants, sandbox bypass, смены home или выдуманной «сессии с writable .git». Эти два входа не исправляют глобально sandbox/diagnostic gaps: F12 остаётся open, более точная диагностика `git_writable=false`/`followup_terminal_git_failed` против общего `followup_terminal_commit_mismatch` требует своего решения. F13/rebinding, live recovery, push/publication и внешние постоянные разрешения этим изменением не закрыты.

### F13

P2, Coder — упростить привязку сессии роли: убрать из неё хеш `.git/index` (и проверить, нужен ли HEAD), чтобы после коммита не требовался повторный `*_init`.

### F14

P2, Coder — упростить файловый слой PI collector: один атомарный писатель, чтение через существующие helpers `followups_capture` и три проверки допуска вместо примерно тридцати, без потери отказа от symlink, границы корня и атомарной записи.

### F15

**Закрыто в принятом объёме:** Приняты местные offsets для новых записей и сохранение legacy instant/IDs; приёмка покрывает inventory и writer/parser/display checks.

Исходная находка:

P2, Coder — часовой пояс: имя плана обновления (`scripts/consumer_contract.py`), штампы времени (`_planveyor_now` в `scripts/planveyor.zsh`) и запуски ролей при закрытии документов (`scripts/planveyor/docs_finalize.zsh`) жёстко используют `Europe/Moscow`; так же остальные вызовы `TZ=Europe/Moscow` в `scripts/planveyor.zsh`, в том числе имя и дата seed декомпозиции, и `MSK` в строке `Date` шаблона запроса вверх `docs/upstream_packets/_template.md`. Москву задают и доставляемые docs: промпты `docs/tools/prompts/*_docs_finalize_followups.md` велят называть файл памяти по времени «(по Москве; уникальное)» (architect:39, coder:33, planner:34, reviewer:36), а шаблон `docs/process_improvements/_template_process_improvements_backlog.md` пишет `MSK` в строках 3 и 42; `scripts/process_improvements_collect.py:100` задаёт `MSK = ZoneInfo("Europe/Moscow")` для своих штампов. `Europe/Moscow` или метку `MSK` жёстко пишут и другие скрипты движка: `followups_triage.py`, `followups_promote.py`, `followups_code_reviews_harvest.py`, `followups_todo_harvest.py`, `review_range_scaffold_engine.py`, `codex_session_stats.py`, `planveyor_trace_extractor.py`; `rollout_packet.py`, `upstream_request.py` и `post_merge_packetization_gate.py` подписывают местное время как `MSK`. Брать часовой пояс владельца.

### F16

P2, Coder — подсказки ролей без фасада: Architect печатает `planveyor_owner_answers_set …` и `Run: planveyor_arch_initial` (`docs/tools/prompts/architect_draft_discussion.md`), а в sibling эти команды вызываются через `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project <sibling>`. Те же голые команды для Owner — в `manager_router.md`, в строках `Next: Owner` четырёх status-driven промптов и у оператора в варианте Б анкеты. `planveyor_analysis_init` (`scripts/planveyor.zsh`) печатает `Next: MANAGER_CMD=run <план>`, а вход аналитической волны — `planveyor_manager_collab_cmd analysis <план>`; `planveyor_decomposition_init` печатает голое `Next: planveyor_decomposition_collab_tui <план>`. Шаг 9 прежней версии `docs/guides/stack-sibling.md` велел эти подсказки не запускать.

### F17

P2, Coder — `planveyor_contract_upgrade` не назначает созданный план обновления текущим; сейчас владелец вызывает `planveyor_plan_set` сам.

### F18

**Закрыто в принятом объёме:** Принята безопасная передача CODEX_THREAD_ID через facade; runtime checks покрывают unset/empty/present и отсутствие parent ID, не live ownership.

Исходная находка:

P2, Coder — provenance через фасад: `bin/planveyor` запускает child через `env -i`, поэтому `CODEX_THREAD_ID` не доходит до `planveyor_plan_provenance_stamp`, а `docs/plans/README.md` называет live env первым источником. Выбрать безопасную передачу (явный `--thread-id` в вызове или отдельная переменная только для provenance) и поправить описание.

### F19

P2, Coder — доставляемые docs около 140 раз называют `scripts/<helper>.py`; в sibling этих файлов нет, а прямой запуск копии из движка берёт корень движка. Заменить на фасадные формы или пометить Self-Planveyor и расширить guard `test_sibling_contract_docs.py` (сейчас он запрещает только `scripts/codex_session_context.py`).

### F20

**Закрыто в принятом объёме:** Принята документация границы direct ZCode Manager: только self-режим в корне Planveyor; ZCode sibling runtime не реализован и не входит в закрытый объём.

Исходная находка:

P2, Architect — ZCode-маршрут в sibling: `docs/roles/index.md` и `docs/tools/prompts/zcode/manager_pipeline.md` ссылаются на `.zcode/…`, которого в sibling нет; не описано, как ZCode в sibling получает `/manager-init` и role-agent.

### F21

**Закрыто в принятом объёме:** Принят umask нового sibling root; runtime checks подтверждают сохранение прежнего mode при upgrade.

Исходная находка:

P2, Coder — корень sibling и backup создаются с правами 0700 (`mkdtemp` и rename в `scripts/consumer_contract.py`), каталоги внутри — 0755; решить, нужен ли `chmod` по umask.

### F22

P2, Coder — `planveyor_docs_closeout` без `--followups-capture-cycle-id` показывает `pending`, даже когда документы закрыты; брать цикл плана из `.tmp/followups_capture/<plan>/` или печатать подсказку с id. Сейчас id передаёт сама команда `planveyor sibling close` (раздел «Коммит и закрытие документов» `docs/guides/stack-sibling.md`).

### F23

**Закрыто в принятом объёме:** Принят явный guarded recover через facade и readback; приёмка покрывает interrupted transaction и recovery, решение остаётся у Owner без auto recovery.

Исходная находка:

P2, Coder — восстановление очереди планов из sibling: `scripts/plan_queue.py recover` есть, но его нет ни в фасаде, ни в allowlist `planveyor_runtime_py`, а payload `recovery_required` не называет команду; скилл `planveyor-plan-queue` пока велит остановиться и показать payload Owner.

### F24

P2, Coder — проверка закрытия документов старого плана (`planveyor_docs_closeout --followups-capture-cycle-id`) после закрытия следующего плана показывает `blocked` с `followup_capture_pi_general_checkpoint_live_drift`: следующее закрытие меняет общие `docs/process_improvements/deferred.md`, `index.md`, `promotion_surface.md`. Не считать это дрейфом, если закрытие старого плана уже закоммичено; пока `docs/guides/stack-sibling.md` велит проверять сразу после коммита хвоста.

### F25

P2, Coder — строгий проход `./bin/planveyor planveyor_doc_lint` в корне движка красный: пути, которые существуют только в sibling (`docs/README.md` в доставляемых ролях и playbooks, `docs/stack_brief.md` и `scripts/sql.py` в `docs/guides/stack-sibling.md`), он проверяет как пути движка. Гейт `make doc-lint` эти корни не проверяет и зелёный. Нужна разметка «путь sibling» или правило для таких упоминаний. Живая цена: в аналитической волне в корне движка Reviewer дал S1 за красный глобальный `planveyor_doc_lint` на неизменённых диагностиках, и это стоило лишнего круга Planner → Coder → Reviewer.

### F26

P2, Architect — pull request прямо из sibling (решение владельца 29.09): в первой версии запрос уходит в planveyor issue через `gh` (раздел «Предложить изменение Planveyor» `docs/guides/stack-sibling.md`, `CONTRIBUTING.md`), а во втором этапе — pull request, в который входят импортированный запрос, правка движка с тестами и извещение, если правка меняет доставляемые файлы или поведение sibling. Спроектировать этот путь и описать его в runbook и `CONTRIBUTING.md`.

### F27

P2, Coder — извещения `docs/contract_notices/`: нужны правило, когда извещение обязательно, и проверка (тест или шаг post-merge), потому что изменения `copier_template/` и рабочих скриптов в диапазоне без извещения сейчас ничто не останавливает. Надёжность `upgrade` в `scripts/consumer_contract.py`: битое извещение в истории навсегда блокирует обновление через этот диапазон, `copytree` кандидата стоит вне `try`, а `--accept-candidate` не сверяет управляемые файлы с новым рендером.

### F28

P2, Coder — запросы вверх в sibling: в извещении нет ссылки на запрос, `show` и `lint` из `scripts/upstream_request.py` работают в sibling только обходом `--repo-root . --tooling-root .`, нет команды или шага скилла для создания запроса, а `ack` не проверяет ссылки. `target_repo_scope: planveyor` в sibling ставится только ручной правкой (`process_improvements_triage.py` нет в allowlist `planveyor_runtime_py`), packetization gate считает PI-строку с `target_repo_scope: planveyor` без `delivery_mode` блокирующей, а режима доставки «вверх» в словаре PI нет.

### F29

P2, Architect — наследие rollout packet: раздел `## Rollout packet handoff` в шаблоне плана, его контракт и helpers в `docs/plans/README.md`, `scripts/rollout_packet.py` и команды `planveyor_rollout_packet_*` описывают адресную доставку в конкретный репозиторий, которой у sibling нет: изменения он получает обновлением с извещением. Решить, убрать механизм или оставить его только для self-режима.

### F30

P2, Coder — `planveyor_entry_doctor` или `planveyor_consumer_doctor` показывает, насколько sibling отстал от checkout planveyor: коммиты, изменённые файлы контракта и ожидающие извещения. Сейчас об отставании doctor говорит только `runtime commit … differs from contract …`, а подробности владелец смотрел блоком шага 10 прежней версии `docs/guides/stack-sibling.md`; дополняет расширенный doctor из F8.

### F31

**Закрыто в принятом объёме:** Принят Copier cache на physical runtime root; scoped runtime checks пройдены, отдельный simultaneous stress-run не заявляется.

Исходная находка:

P2, Coder — кэш Copier общий на машину: `process_env` в `scripts/consumer_contract.py` направляет `XDG_CACHE_HOME` в `planveyor-copier-cache` внутри `TMPDIR`, а Copier ключует зеркало по публичному URL; развести кэш по рантаймам. Параллельные прогоны `test_consumer_contract` сталкиваются (`cannot lock ref 'refs/heads/main'`), пока каждому не дать свой `TMPDIR`.

### F32

P2, Architect — разбор обновления ролями (предложение владельца 29.09): план обновления (`adaptation_plan` в `scripts/consumer_contract.py`) перечисляет только пути, поэтому вместо него — аналитическая волна по диапазону коммитов движка (Planner задаёт источники: коммиты, изменённые файлы, извещения; Coder пишет, что изменилось по функционалу; Reviewer проверяет), а затем план адаптации sibling следующим шагом. Строится на аналитической волне, поэтому делается вместе с F33. В первой версии остаётся текущий путь — извещения и план адаптации, подробно описанные в разделе «Получить новую версию Planveyor» `docs/guides/stack-sibling.md` (решение владельца 29.09).

### F33

P2, Architect — аналитическая волна без переноса pack (владелец: «починить конструкцию»; перенос файла — не работа Planner, в первой версии оставлена работающая конструкция): сейчас Architect и Planner пишут таблицу `## Analysis pack` в план, а Planner в конце Planner intake переносит её в `docs/analysis_packs/<stem>.md`. Цель — постановка (вопрос, ограничения, источники) остаётся в плане, а Coder сразу пишет результаты в отдельный файл; для этого разделить поля V1 между планом и pack в движке (resolver в `scripts/plan_status_oracle.py`, `scripts/plan_lint.py`, `scripts/planning_wave_readback.py`). Заодно: после принятия маршрута pack держит в ссылках маршрута `N/A (why=… ещё не …)`, и lint этого не ловит.

### F34

P2, Coder — волна декомпозиции: дети рождаются с `queue_activation.state=n/a`, одобрение зонтика на них не распространяется, и `q_set --from-umbrella` отказывает на первом ребёнке — принимать активацию зонтика или рождать детей с наследуемой (шаг 9 прежней версии runbook велел одобрять каждого). Кроме того: `planveyor_decomposition_init` не атомарен; one-shot `planveyor_decomposition_collab` шлёт `MANAGER_CMD=run` без постановки, а ответы `planveyor_owner_answers_set` Manager collab не читает; Architect переименовывает seed, а Manager держит старый `PLAN_PATH`; `planveyor_decomposition_seed_promote` переносит файл на любой путь без проверок; дети рождаются без `machine_authority_decision`, о котором плейбук молчит. В Manager one-shot ответ владельца строкой `(Owner, ids=Q5) A: …` в `### Owner answers` вопрос не закрывает: Manager стоит на `Next: Owner`, пока нет строки `(Owner, id=Q5, status=closed) CLOSED: …` (шаг 9 прежней версии runbook описывал обе строки); принимать ответ как закрытие или читать `planveyor_owner_answers_set`. Повторный `planveyor_manager_collab_cmd decomposition <зонтик>` после первого хода отказывает (`active decomposition overlay is incompatible with wave_family or promoted_from`): роли заполняют у зонтика `plan_meta.promoted_from`, а README обещает переиспользовать активный зонтик; сейчас волну продолжают `run`. Оракул отвечает `decomposition_child_state=queue_ready` зонтику, который ещё не прошёл ревью.

### F35

P2, Coder — тесты волн: нет тестов на `planveyor_decomposition_collab`, `planveyor_decomposition_collab_tui`, авто-seed и `planveyor_decomposition_seed_promote`; init декомпозиции в режиме `engaged` через `bin/planveyor --project` тестом не покрыт; нет сквозного прогона волны с поддельным Codex.

### F36

**Закрыто в принятом объёме:** Принята документация Manager collab agents/model/effort/Codex home; объём документальный и не требует нового live/provider proof.

Исходная находка:

P2, Coder — Manager collab требует ролей `[agents.*]` в конфиге Codex, и это нигде не описано для владельца (дополняет F11). Окружение Codex пользователя попадает в роли: Manager читает `~/.codex/memories`, роли получают глобальный `~/.codex/AGENTS.md`; описать это как оговорку. Рекомендация владельца (30.09): по умолчанию GPT-6.1 Sol в режиме ultra или max, не ниже xhigh. Сейчас у владельца Manager — gpt-6.1-sol xhigh, Architect и оба Reviewer — 5.6-sol xhigh, Planner, Coder и explorer — 5.6-terra ultra; имена задач Manager (`architect_sol_xhigh_v2`, `planner_terra_ultra_v2` и др.) совпадают с этими моделями.

### F37

P2, Coder — в self-режиме Codex не находит скилл `planveyor-plan-draft`: в корне движка он лежит в `skills/`, а Codex читает скиллы проекта из `.agents/skills/`, куда скилл доставляется только в sibling.

### F38

**Закрыто в принятом объёме:** Принято исключение README/template noise из planning_wave_readback; admission-null behavior сохранён, отдельный selector plan_lint из PI2 остаётся открытым.

Исходная находка:

P2, Coder — `planveyor_planning_wave_readback` читает `docs/plans/README.md` как план и поэтому даже на чистом дереве показывает `confidence: medium`; в записи маршрута из `## Promoted route artifact` `queue_admission` и `runner_admission` равны `null`, а оракул отвечает `needs_planner` и `frontier_only`.

### F39

P2, Coder — цена фасада: около 8 с на вызов `bin/planveyor` и медленный `planveyor_show --wide`; начинать после измерений F3.

### F40

P2, Coder — закрытие плана: шаблон создаёт `## Post-merge gate`, а lint для `Done` требует закрыть его до merge (лишний круг), и запись в `.git` проверяется поздно, уже внутри stage после ревью, поэтому нужен preflight до первого stage. Парсер пропускает Owner-вопросы нестандартной формы (`Q-CLOSEOUT-001` со `status=open` в плане `Done`, а оракул отвечает `open_owner_questions=[]`), а записи спавнов цикла `run` в `.planveyor.collab.agent.*.log` идут без столбца источника.

### F41

**Закрыто в принятом объёме:** Принята инструкция sibling.env: назначение PLAN_PATH/REQUEST и действие последней записи; отдельный raw zsh probe не заявляется.

Исходная находка:

P2, Coder — runbook sibling дописывал `PLAN_PATH=…` в `~/sibling.env` при каждом запуске блока (шаги 5 и 9 прежней версии `docs/guides/stack-sibling.md`, в шаге 10 так же `REQUEST=…`), действует последняя строка; решить, нужен ли отдельный файл.

### F42

**Закрыто в принятом объёме:** Принято удаление product-specific heuristics; visual/harvester checks подтверждают generic normalization, provenance и сохранение открытого F45.

Исходная находка:

P2, Coder — эвристики конкретного продукта в коде движка. `looks_runtime_ui` в `scripts/review_visual_lane_contract.py:190-205` узнаёт UI-правку по путям Django `apps/*/{admin,views,services,selectors}.py` (`BACKEND_UI_STEMS`, стр. 166), а также по веб-умолчаниям: именам каталогов `templates`, `static`, `frontend`, `ui` (стр. 196) и веб-расширениям `DIRECT_UI_SUFFIXES` (стр. 165). `_canonical_summary` в `scripts/followups_code_reviews_harvest.py:357-372` сводит заголовки находок к готовым по шести правилам продукта: `DetailPageHelper`/`inspect.signature`, `ProxyRequest` (Views), `urlencode`, «авто» + «техника», local import `transaction` во views, дубль import `settings`; первое правило закреплено `scripts/test_followups_lint.py:707-764`. Убрать их или брать из объявления проекта.

### F43

Исследование выполнено; реализация отложена, пункт остаётся открытым.

P2, Coder — risk packet делит пути по раскладке конкретного продукта: `RUNTIME_PREFIXES` в `scripts/range_review_risk_packet.py:36-46` — Django-раскладка (`apps/`, `config/`, `core/`, `templates/`, `static/`, `assets/`, `manage.py`, `requirements`, `pyproject.toml`), а `classify_changed_paths` (стр. 383) всё остальное считает helper/process, включая `scripts/`, который в sibling — код проекта. В sibling на SQL Server изменения в `db/`, `src/`, `tests/` попадут в helper. Инвертировать правило (process — `docs/`, `.github/`, `.planveyor*`, остальное — runtime) или брать префиксы из объявления target. Правка меняет `range_review_risk_packet.v1`, который цитирует post-merge audit.

### F44

**Закрыто в принятом объёме:** Принято удаление отменённых публичных todo/continuity writers и defaults; classification/public/ledger/census checks подтверждают сохранение historical readers и generic declared ledger.

Исходная находка:

P2, Architect — семейство todo_stage повторяет формат TODO-документов конкретного продукта: `DEFAULT_TODO_SOURCES` в `scripts/followups_todo_harvest.py:37-42` — `docs/todo_stage_1/2/3/3plus.md` с грамматикой «Темы:», «Статус (…)», «перенесено в stage»; тот же список — в `scripts/todo_stage_followups_check.py:26-31`. Наружу семейство выходит публичной командой `planveyor_followups_todo_harvest --all` (`scripts/planveyor.zsh`: функция, help, allowlist), producer `todo_stage_harvest` в `scripts/followups_apply.py:37` и строкой `scripts/README.md:41`. Убрать эти инструменты или требовать явный `--src` без значения по умолчанию; это смена API.

### F45

P2, Architect — веб-словарь методики UI-риска. Движок сам печатает `## Visual Acceptance (browser, UI tasks)` (`scripts/review_range_scaffold_engine.py`: стр. 51, 71, 96, 904, 1858, 1860 и хеш `SEMANTIC_SURFACE_SHA256`; шаблон `docs/plans/_template.md:462`) и `Runtime/browser proof:` (стр. 1762). Docs делают обязательными веб-таксономию page/fragment/list/api/supporting endpoint, носители hidden-field / selected slug / OOB-fragment refresh, «атрибут есть в HTML», правило «HTML chunk → DOM/subtree» и client-side `min/required`: `docs/plans/README.md:1507-1545`, `docs/plans/_template.md` (стр. 411, 451, 503–506), `docs/code_drafts/_template.md:152-153`, роли coder, planner и reviewer, status-driven и censor-промпты, playbooks `doc_gardening`, `review_staged_or_commit`, `post_merge_visual_review`, `role_prompt_invariant_map`. Часть этих мест уже называет веб-токены лишь примерами, но таксономия и заголовки остаются обязательными. Туда же enum видов цели `py|template|css|js|doc` (`docs/code_drafts/_template.md:20`) ↔ `infer_target_kind` (`scripts/review_range_scaffold_engine.py:1947`, возвращает ещё `sh` и `file`). Нужен единый нейтральный словарь и согласованное переименование в движке, тестах и хеше.

### F46

**Закрыто в принятом объёме:** Принято закрытие directory/glob/extensionless gaps в существующем delivery guard; guard/corpus checks подтверждают поддержанные references.

Исходная находка:

P2, Coder — дыры стража доставки: `DOC_PATH_MENTION_RE` в `scripts/test_sibling_contract_docs.py` пропускает упоминания без расширения, поэтому шаблоны вроде `docs/arch/*`, `docs/continuity/*`, `docs/todo_stage_*` не проверяются; так остатки продукта и прошли. Сейчас `docs/continuity/*` упоминают 12 доставляемых файлов, `docs/arch/*` — 9. Проверять и такие упоминания: каталог или префикс шаблона должен быть в sibling или объявлен принадлежащим sibling.

### F47

**Закрыто в принятом объёме:** Приняты fixtures с собственным Git root; two-TMPDIR и non-Git checks доведены до PASS.

Исходная находка:

P2, Coder — тесты падают, если `TMPDIR` лежит внутри Git-дерева: `scripts/test_review_artifact_lint.py` даёт 3 failures и 159 errors «explicit project_root is not the verified Git top-level» (`git_root_mismatch` в `scripts/contract_authority_context.py`): временный проект теста — не корень Git, и Git находит внешнее дерево. Вне Git тот же файл зелёный. Создавать временные проекты тестов вне Git-деревьев либо явно отказываться с понятным сообщением.

### F48

**Закрыто в принятом объёме:** Принята документация accepted-red/forensic contract; приёмка не заявляет нового Owner incident capture.

Исходная находка:

P2, Architect — контракт accepted-red и forensic capture описан только в коде: режимы `planveyor_plan_bundle` (`--closeout-json`, `--capture-rejected`, `--verify-rejected`, `--cleanup-rejected`), `scripts/plan_status_oracle.py` и `scripts/docs_closeout.py`; отдельного документа нет, `docs/playbooks/manual_terminal_recovery.md` ссылается прямо на режимы. Описать контракт в документе движка.

### F49

P2, Coder — тупик двух линий ревью: после вопроса `Reviewer → Architect` селектор блокирует артефакт risk-линии (`missing_risk_lane_support_payload_ref`), contracts-линия не запускается, а risk-линии менять статус нельзя, поэтому `Ready for Architect response` никто не ставит, и Manager останавливается с `stop_class=semantic_blocker`. Владелец ставил статус сам по шагу 11 прежней версии `docs/guides/stack-sibling.md`. Дать risk-линии перевод статуса для вопроса к Architect или маршрутизировать его в Manager.

### F50

P2, Coder — скилл плана адаптации записывает вопросы Owner по анкете (`Q1`…`Q10`) и оставляет их закрытие Architect, но под Manager Architect не получает хода, пока вопросы Owner открыты, и владелец закрывал их сам по шагу 5 прежней версии `docs/guides/stack-sibling.md`. При варианте Б вопросы не заводить или помечать отвеченными по заполненной анкете; либо давать Architect ход.

### F51

P2, Coder — отчёт JUnit, которым Coder доказывает цель проверки (`docs/code_reviews/assets/<plan>/…junit.xml`), не входит в набор плана `planveyor_plan_bundle`, хотя JUnit Reviewer входит; отчёт Coder попадает в историю только хвостом документов. Включать в набор отчёты Coder, на которые ссылается Evidence.

### F52

P2, Coder — зелёное ревью, где в `## S1 Blocker` остались только `historical-fixed` блокеры, закрытие документов читает как `review_blocker_status=blocking`, а lint ревью — как зелёное: разбор `## S1 Blocker` в `scripts/review_artifact_lint.py` и в закрытии документов расходится. Общий парсер и тест на зелёное ревью с историческими блокерами.

### F53

P2, Architect — [f53-v2-lifecycle-terminal-readback](followups/261009_003241_followups_memory_architect.md) с двумя раздельными механиками. После OSS release и отдельного принятого поручения предстоит:

- Перенести готовый V2/K1 lifecycle для promotion/close/cancel V2 rows, обеспечить sibling follow-ups index и исправить scaffold `--prepare-v2`.
- Отдельно исправить terminal source-readback после последующих валидных row/disposition или общих docs-capture изменений: читать ранее закрытый source по committed proof и сохранять отказ при реальном drift, без ручной правки source/receipt.

Перенос lifecycle сам по себе не закрывает вторую механику. Связанный [F24](#f24) сохраняет собственную identity; эта навигация не создаёт его дубликат и не меняет row/disposition.

### Вывод sibling upgrade

P2, Coder — [sibling-upgrade-output](followups/261009_003241_followups_memory_architect.md). Сейчас wrapper скрывает stdout с `candidate`/`problems` при `blocked` с rc 3 и непустом stderr; при успехе не печатает `notices`.

В отдельном исправлении после OSS release нужно сохранить отказ rc 3, показывать `candidate`/`problems` при непустом stderr и печатать полученные `notices` при успехе, сохранив backup, adaptation plan и существующие guards. Engine fix и реальный A→B rehearsal остаются после релиза и отдельного принятого поручения; этот документ не заявляет их выполнение.

## Process improvements

### PI1

P?, Coder — в status-driven handoff сопоставлять каждую literal-команду Acceptance и code draft с отдельной проверкой.

### PI2

Остаётся открытым: исправление F38 относится к `planning_wave_readback`, а эта находка — к selector `plan_lint`.

P?, Planner — исключить README/template code-draft из advisory выбора live primary draft, сохранив явные нестандартные refs.

### PI3

P?, Manager — до review dispatch сверять plan Mode с фактическим transport; native route требует factual `reuse-thread`, а custom-only semantics — custom invocation. Если custom mode заявлен, а фактического custom invocation нет, — остановиться до role-send и не создавать синтетический receipt. Метка C05 в исходной записи PI-003 обозначает один из пакетов доработки перед выпуском.

### Координация carrier перед capture

P?, Manager — [отдельная source-bound PI-001](process_improvements/261007_1935_owner_task_sibling_flow__process_improvements_backlog.md#pi-001): согласовать один fresh carrier до immutable binds. Первая роль с findings выбирает путь; последующие роли читают его из current helper-owned bound proof и сохраняют тот же carrier для самостоятельных новых items. Это открытое предложение для post-release изменения prompts; distinct item_id, независимые submissions, sole writer и one-carrier отказ сохраняются.

Все четыре PI — PI1–PI3 и отдельная source-bound PI-001 — остаются открытыми предложениями с неустановленным приоритетом. Для реализации после первой публикации создавайте отдельный обычный plan или follow-up по действующим шаблонам.

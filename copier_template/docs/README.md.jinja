# Рабочие документы sibling

Этот каталог — контракт sibling. Ваш код, планы, review и локальные правила
стека находятся здесь; движок Planveyor с его `bin/`, `scripts/` и `Makefile`
остаётся во внешнем checkout. Runtime файлы сюда не копируются.

## Обычная работа

В подготовленном окружении используйте trusted public executable `planveyor`
из `PATH`. Вызов из Self-Planveyor (physical Planveyor root) — `./bin/planveyor`.
Команды группы `sibling` определяют физический корень этого проекта по
текущему каталогу и используют уже выбранный план:

```sh
planveyor sibling plan
planveyor sibling architect
planveyor sibling answer
planveyor sibling run
planveyor sibling close
planveyor sibling close --commit
planveyor sibling ready
```

`plan` показывает выбранную задачу, фактические вопросы и следующий шаг.
`architect` ведёт обсуждение; `answer` принимает ваш фактический ответ и
оформляет существующий журнал. При нескольких вопросах укажите показанный
id: например, `planveyor sibling answer Q2`. `run` запускает обычный Manager.
После вопроса или лимита повторяется та же команда, а сессии подготавливаются
штатно. Передача ответа не означает автоматический переход статуса.

`close` только показывает проверенную подготовку: status, index и сессии не
меняет. `close --commit` — явное разрешение выполнить проверенный точный
коммит. Перед ним прочитайте набор и сообщение. Документы проходят отдельное
штатное закрытие; если оно ещё не готово, выполните указанный шаг и повторите
подготовку. Чужие staged файлы и неактуальные доказательства блокируют коммит.
Если правили данные после просмотра, сначала повторите preview. После
семантического коммита отдельный `run` готовит документы; новый preview и
`close --commit` принимают уже показанный хвост. `ready` — диагностика
текущего плана, а не запуск проверок стека, публикация или разрешение
production writes.

Полный постоянный runbook находится во внешнем runtime:
`"$PLANVEYOR_RUNTIME_ROOT/docs/guides/stack-sibling.md"`. Настройка клиента и
advanced modes — `"$PLANVEYOR_RUNTIME_ROOT/docs/guides/launch-and-role-modes.md"`.
Reference guides остаются source-owned и в sibling не копируются.

## Создать план и согласовать стек

Скиллы уже доставлены в `.agents/skills/`; Codex и ZCode находят их при работе
в этом проекте. Вызовите явно `$planveyor-plan-draft` в Codex или
`/planveyor-plan-draft` в ZCode:

```text
$planveyor-plan-draft Создай и сделай текущим план адаптации sibling под мой стек по docs/_template_stack_brief.md. Задай вопросы по неподтверждённым решениям. Следующую полезную задачу согласуем отдельно.
```

Скилл создаёт план из `docs/plans/_template.md` и входную анкету
`docs/stack_brief.md`. Начальный статус — `Architect initial draft`;
executable code draft и реализация ещё не требуются. Architect согласует
ответы Owner, Planner определяет точный набор, Coder реализует Scope,
Reviewer проверяет текущие bytes, затем Architect принимает итог.

Адаптация согласует назначение и готовность стека; реальные findings проходят
штатный capture, zero findings допустимы. Следующая полезная задача — отдельное
прямое поручение Owner:

```text
$planveyor-plan-draft Создай и сделай текущим обычный план по моему прямому поручению: <результат и наблюдаемая проверка>. Покажи matching open follow-up, сохрани его неизменным и добавь source_ref#item_id в Context links.
```

Скилл выполняет bounded discovery. Matching row остаётся unchanged:
`status=open`, `plan=null`, `disposition_kind=null`, `disposition_ref=null`,
`disposition_commit_oid=null`; literal `source_ref#item_id` — только контекст.
Automatic backlink запрещён. Если совпадений нет, фиксируется отсутствие
совпадений без искусственной row. Конфликт уже активного плана по тому же
результату требует Architect/Owner triage. Ordinary plan не является row
promotion: prepare/finalize/backlink не являются его предусловиями. Настоящее
продвижение row требует штатного promotion writer и exact proof; V2/K1 port
остаётся отдельной post-release работой.

`planveyor-plan-queue` остаётся отдельным скиллом для явно выбранной очереди;
`sibling run` сам её не создаёт.

## Среда и внешний facade

Требуются Git, zsh, rg и подготовленное окружение с Python 3.12, Copier 9.18.2
и PyYAML. Для live ролей нужен настроенный авторизованный Codex. Выбирайте
доверенное окружение до запуска; отсутствующая предпосылка означает отказ,
без установки, смены home или автоматического обхода. Project-local
`.planveyor.pybin` не выбирает executable.

Агент использует public `planveyor` из trusted launch PATH либо явно
выбранный `PLANVEYOR_RUNTIME_ROOT`. Если приложение не видит ни того ни
другого, укажите ему trusted checkout один раз. Не записывайте пути машины
в публичные планы и Local rules; shell config не нужно менять автоматически.
Для helper/advanced команды внешний facade явно получает этот проект:

```sh
planveyor --project "$PWD" planveyor_help
```

Выполняйте такую низкоуровневую команду из корня sibling. Для группы `sibling`
достаточно текущего каталога внутри проекта. Explicit `--project` выбирает
проект, но не создаёт plan, authentication, provider readiness или stack.

`.copier-answers.yml` и
`docs/_meta/planveyor_contract_authority.v1.json` — tracked contract files.
`.env.local`, `.planveyor.*` и `.tmp/` игнорируются. Credentials храните только
в объявленном стеком локальном защищённом файле; не передавайте их роли или
в отчёт. `.env.local`, если она нужна, игнорируется, не отслеживается и имеет
права 0600.

## Обновление и другие маршруты

Новая версия движка выбирается вами обычным способом. Завершите работу и
сессии в sibling, выйдите из его каталога, затем запустите `sibling upgrade`
через facade выбранного нового runtime с явным `--project`. Source commit
он определяет сам; скрытого pull или переключения branch нет.

Upgrade меняет каталоги местами, сохраняет local bodies, создаёт и выбирает
обычный план адаптации, а исходный проект сохраняет в backup. Выполните Architect → Manager → review
→ commit → docs closeout. До этого `updated_pending_adaptation` не означает
завершённое обновление. При retained candidate сначала разберите и примите
его проверенные изменения; `sibling upgrade --accept-candidate` выполняется
только для той же выбранной версии. Backup содержит credentials и локальное
состояние, его не публикуют и удаляют сами после принятой адаптации.

Analysis, decomposition, queue и custom pipeline остаются отдельными
advanced маршрутами со своими планами и prerequisites. Custom pipeline
требует executable code draft и matching role receipts; их не следует
требовать от initial draft обычного первого плана. Не вызывайте raw init
с `--help` как диагностическую пробу: обычная справка группы —
`planveyor sibling --help`.

Предложения общей правки Planveyor идут отдельным upstream request из
`docs/upstream_packets/_template.md`. Подготовьте публичный request, проверьте
и закоммитьте его обычным планом; отправка GitHub issue через installed `gh`
требует отдельного вашего разрешения. Source-only import/ack не запускаются
из sibling. Ответ возвращается извещением и планом адаптации обновления.

## Матрица локального контекста

Обязательный target-local контекст модели хранится в готовом файле роли или
фазы. Отдельный обязательный каталог stack docs и runtime assembly не используются.
После init тело двух локальных секций принадлежит sibling; общие правила
остаются снаружи этих секций, а обновление проверяет их байты строго.

Reference guides из Planveyor source намеренно не доставляются в sibling. Если выбранный маршрут
требует source-owned reference, используй явно назначенный путь из runtime,
например `"$PLANVEYOR_RUNTIME_ROOT/docs/guides/golden_paths.md"`; для
target-local workflow используй carrier, объявленный текущим project contract.

| Роль / фаза | Готовый файл | Команды / критерии в локальных секциях | Доставка |
| --- | --- | --- | --- |
| Architect / development | `docs/tools/prompts/architect_status_driven.md` | Архитектурные ограничения, предметные термины, условия применимости. | Copier доставляет файл; update сохраняет local bodies. |
| Planner / development | `docs/tools/prompts/planner_status_driven.md` | Точные команды проверок, данные/fixtures и критерии приёмки для plan. | Copier доставляет файл; update сохраняет local bodies. |
| Coder / development | `docs/tools/prompts/coder_status_driven.md` | Подготовка, build/test/smoke commands и ожидаемые результаты. | Copier доставляет файл; update сохраняет local bodies. |
| Coder / migration gate | `docs/tools/prompts/coder_migrations_gate.md` | Preconditions, migration commands и evidence. | Copier доставляет файл; update сохраняет local bodies. |
| Reviewer / role | `docs/tools/prompts/reviewer_status_driven.md` | Review commands, data and expected evidence. | Copier доставляет файл; update сохраняет local bodies. |
| Reviewer / staged or commit review | `docs/playbooks/review_staged_or_commit.md` | Review harness, preconditions and proof. | Copier доставляет файл; update сохраняет local bodies. |
| Reviewer / merge-range review | `docs/playbooks/review_merge_range.md` | Range commands, test data and evidence. | Copier доставляет файл; update сохраняет local bodies. |
| Post-merge / audit | `docs/playbooks/post_merge_audit.md` | Audit commands, data and retained receipt. | Copier доставляет файл; update сохраняет local bodies. |

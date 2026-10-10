# Planveyor Owner guide

Основной путь для проекта под свой стек — [постоянный runbook sibling](docs/guides/stack-sibling.md). Он ведёт от нового каталога до принятой адаптации и полезных задач одной группой `planveyor sibling`:

```sh
planveyor sibling init ~/my-stack
```

Затем в каталоге проекта: draft skill → `architect` → реальные ответы через `answer` → `run` → preview `close` → разрешённый `close --commit`. После коммита плана отдельный `run` закрывает документы; новый preview и `--commit` принимают именно подготовленный хвост. `ready` проверяет контракт, выбранный план и закрытие; живые проверки стека остаются частью принятого плана.

## Среда и facade

Из physical Planveyor root прямой вызов — `./bin/planveyor`. В подготовленной среде его public executable доступен как `planveyor` в PATH. Runtime определяется физическим путём facade; `git` и HEAD проверяются до первого действия. Нужен подготовленный поддерживаемый Python; Planveyor не устанавливает зависимости и не переписывает shell config. Настроенный авторизованный клиент требуется для выбранных live role/Manager команд.

Справка `planveyor sibling --help`, `planveyor_entry_doctor` и runtime info — диагностика. Doctor и выбранный pointer не подтверждают приёмку задачи и не разрешают commit, dispatch, upgrade или публикацию. Для низкоуровневой команды другого проекта explicit `--project` стоит перед command. У группы `sibling` физический проект выводится из текущего каталога; init получает новый путь от вас, upgrade запускается из внешнего каталога с явно выбранным проектом.

## Решения владельца

Вы выбираете проект, задачу, stack, dev target, credentials и допустимый live режим. Architect задаёт вопросы; только ваши фактические ответы попадают в журнал. Код стека, проверки и локальные правила принадлежат sibling. В public corpus не записывают private configuration, secrets и пути вашей машины.

Перед `close --commit` просмотрите текущий точный набор. Сам флаг подтверждает этот коммит; green preparation такого разрешения не даёт. Source version, role sessions, timestamps и technical hashes определяются механизмом. Push, deployment и отправка публичного issue требуют отдельного вашего решения.

## Навигация

- [Sibling: создание, задачи, обновление и upstream предложение](docs/guides/stack-sibling.md).
- [Запуск, сеть и режимы ролей](docs/guides/launch-and-role-modes.md).
- [Lifecycle, закрытие и пакеты](docs/guides/lifecycle-and-packets.md).
- [Проверки и их область](docs/tools/verify_suite.md).
- [Роли](docs/roles/index.md) и [playbooks](docs/playbooks/README.md).

Analysis, decomposition, queue и custom pipeline остаются самостоятельными штатными маршрутами. Manager не меняет молча выбранные plan, target, runner или authentication source; обычная работа с одним sibling plan не требует очереди.

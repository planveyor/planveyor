# Planveyor

Planveyor — самостоятельный repo-backed набор инструментов для plan-driven работы ролей Architect, Planner, Coder, Reviewer и Manager. Планы, ревью, follow-ups, packet records и process guidance остаются проверяемыми файлами репозитория.

## Старт

Проект под свой стек создаётся и ведётся по постоянному [runbook sibling](docs/guides/stack-sibling.md): создать проект, завести план, ответить Architect, провести Manager, просмотреть и явно закоммитить каждый точный набор. Команды для человека объединены в `planveyor sibling`; выбранный facade и контекст проекта определяют технические параметры сами.

Запускайте команды из корня Planveyor через child-only facade:

```zsh
./bin/planveyor planveyor_entry_doctor
./bin/planveyor planveyor_runtime_info
./bin/planveyor planveyor_help
```

Facade сам определяет корень по `bin/planveyor` и не ожидает фиксированный путь в домашней директории. До первого public command проверьте доступный `git`, physical Planveyor Git checkout и `HEAD`, разрешающийся в commit: этот preflight выполняется до `--project` и до doctor. Поддерживаемый Python нужен для загрузки source identity facade. Настроенный клиент и его обычная внешняя аутентификация нужны только live-команде, вызывающей этот клиент; Codex и Codex-аутентификация относятся только к Codex-путям. Doctor, runtime info и help их не проверяют. `PLANVEYOR_CODEX_HOME` задавайте только явно и только для внешнего каталога.

Не подключайте implementation shell files через `source`: публичный контракт запуска — команда выше.

`planveyor_entry_doctor` и `planveyor_runtime_info` дают только local readback, а не proof consumer contract, admissibility plan, SID, authentication, provider availability или role dispatch. Последовательность supported Python, exact-plan oracle, pointer, Manager SID, live TUI и отдельной queue описана в [launch-and-role-modes](docs/guides/launch-and-role-modes.md). Manager collab требует ещё пяти ролей `[agents.*]` в конфиге Codex: см. [настройку Codex](docs/guides/launch-and-role-modes.md#настройка-codex).

## Поддерживаемая среда верификации

Первая версия поддерживает одну среду: macOS и активированное Python-окружение с Python 3.12, Copier 9.18.2 и PyYAML по `requirements-dev.lock`; в `PATH` также нужны Git, zsh и ripgrep. Подготовьте окружение сами (например, conda-окружение `planveyor`, внутри которого выполнен `make bootstrap-python`) и активируйте его до вызова `bin/planveyor` или `make`: Planveyor берёт `python3` из `PATH`. Planveyor не устанавливает и не чинит зависимости; при отсутствующей предпосылке команда завершается с сообщением, что именно нужно. Загрузчик source identity технически принимает Python 3.10–3.12, но поддерживаемый путь — среда выше. Настроенный CI workflow не является результатом hosted run; hosted CI и другие версии Python — после выпуска.

Для локальной проверки `make verify` — быстрый default route. `make test-scripts` запускает direct canonical full discovery, а `make verify-full` — альтернативный aggregate full route; для одного full claim выбирайте один из этих маршрутов, а не оба. Native validation для Windows и Linux не завершена и этим текстом не заявляется.

## Состав

- shared role docs, prompts и playbooks;
- templates для plan, code draft, review, follow-up и process improvement;
- локальные validation/lifecycle gates;
- rollout и upstream packets для передачи работы между репозиториями;
- agent skills для создания и маршрутизации Planveyor artifacts;
- пошаговая инструкция: создать sibling под свой стек, настроить его и работать в нём.

Init доставляет skills в sibling как `.agents/skills/`, где их находят Codex и ZCode. Для работы в другом репозитории скопируйте `skills/<name>/` в `$HOME/.agents/skills/`, без symlink.

Sibling под свой стек создаётся и настраивается по [пошаговой инструкции](docs/guides/stack-sibling.md). Основные маршруты описаны в [launch-and-role-modes](docs/guides/launch-and-role-modes.md), [lifecycle-and-packets](docs/guides/lifecycle-and-packets.md), [golden paths](docs/guides/golden_paths.md), [кратком Owner guide](planveyor_owner_book.md), [verification suite](docs/tools/verify_suite.md), [roles](docs/roles/index.md) и [playbooks](docs/playbooks/). Открытые пункты первого выпуска сохранены в [release backlog](docs/release_backlog.md).

## Граница target-local

Root corpus описывает публичный процесс. Consumer repository владеет своим стеком, тестами, credentials, integration settings, UI modes и `target-local` profile. Если target-local contract отсутствует, Planveyor останавливается с blocker и не создаёт локальную замену.

Для изменений читайте [CONTRIBUTING.md](CONTRIBUTING.md), для security report — [SECURITY.md](SECURITY.md). Лицензия: [Apache-2.0](LICENSE).

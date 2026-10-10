# AGENTS.md — правила для ИИ-агентов в Planveyor

Цель: держать короткие и стабильные правила для работы со standalone Planveyor. Детали процесса живут в public docs и command help.

## Что это за репозиторий

Planveyor хранит shared role docs, prompts, playbooks, lifecycle templates и локальные helpers для plan-driven работы. Он не является runtime dependency consumer repository и не владеет его секретами, окружением или product-specific configuration.

## Начало работы

Из корня Planveyor используйте child-only facade:

```zsh
./bin/planveyor planveyor_entry_doctor
./bin/planveyor planveyor_runtime_info
./bin/planveyor planveyor_help
```

Facade определяет свой root по физическому пути `bin/planveyor`. До первого public command проверьте доступный `git`, physical Planveyor Git checkout и `HEAD`, разрешающийся в commit: этот preflight идёт до `--project` и до doctor. Не подключайте implementation shell files через `source` и не полагайтесь на fixed home-directory path. Совместимый Python 3.10–3.12 нужен для загрузки source identity facade. Настроенный клиент и его обычная внешняя аутентификация нужны только live-команде, вызывающей этот клиент; Codex и Codex-аутентификация относятся только к Codex-путям. Doctor, runtime info и help их не проверяют. Перед role или validation work выберите совместимый Python 3.10–3.12 через доверенное окружение запуска: активированный env или его `bin` в `PATH`. Helpers и Make/direct используют этот выбор; содержимое project-local `.planveyor.pybin` не выбирает executable. `PLANVEYOR_CODEX_HOME` допустим только как явно заданный внешний каталог.

Doctor/runtime readback не доказывает consumer contract, plan admissibility, SID, provider readiness или dispatch. Полная последовательность находится в `docs/guides/launch-and-role-modes.md`: normal `planveyor_manager_collab_tui` запускается без `--q` и является live path; queue materialize-ится отдельно.

## Границы

- Не пишите секреты, токены, cookies, private hostnames и private local paths. Используйте `<REDACTED>`.
- Не создавайте или не меняйте target-local profile, credentials, database access, editor/browser setup или integration settings из root corpus.
- Если target-local contract отсутствует, остановитесь с ясным blocker вместо выдуманного fallback.
- Не переносите historical plans, review receipts, packet history и local account state в новые public artifacts.
- Для поиска используйте `rg`; меняйте только необходимый scoped artifact.

## Процесс

1. Выберите literal plan path и target root.
2. Проверьте status и relevant lint до execution.
3. Передайте роли bounded scope, current evidence и ожидаемый artifact.
4. Ревьюируйте exact revision range, а не только prose summary.
5. После merge создайте fresh evidence, follow-up или packet только при наличии текущего основания.

Manager координирует выбранный Owner режим, но не меняет молча runner, target, plan или authentication source. Dedicated transport overlay используется только когда runtime явно его выбрал; не выводите его contract из этого файла.

## Навигация

- `docs/guides/launch-and-role-modes.md` — public launch и role modes.
- `docs/guides/lifecycle-and-packets.md` — plan/review/closeout/packet lifecycle.
- `planveyor_owner_book.md` — краткий Owner guide для consumer setup и stack boundary.
- `docs/tools/verify_suite.md` — public verification routes.
- `docs/roles/` — responsibilities и handoff boundaries.
- `docs/tools/prompts/` — shared prompts.
- `docs/playbooks/` — detailed process guidance.
- `docs/*/_template*` — canonical starts for durable artifacts.
- `skills/` — agent-facing workflow instructions.

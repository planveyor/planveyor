# `scripts/planveyor/`

Модульный слой для `scripts/planveyor.zsh`. Фасад владеет bootstrap и выбирает eager, lazy и conditional загрузку; эти файлы не запускаются напрямую.

## Runtime inventory

Фасад (не модуль): `scripts/planveyor.zsh`.

| Модуль | Режим загрузки | Граница |
| --- | --- | --- |
| `contract_authority.zsh` | eager bootstrap dependency | authority component до public wrapper use |
| `session_init.zsh` | eager | init-time helpers для артефактов, session id и новых role sessions |
| `role_runtime.zsh` | eager | status-driven entrypoints для ролей и Manager |
| `docs_finalize.zsh` | eager | wrappers для memory-finalize/doc-closeout слоя |
| `home_runtime.zsh` | lazy | consumer-owned Codex-home report/refusal adapter |
| `provider_runtime.zsh` | conditional | provider/provenance selector |

## Порядок eager-загрузки

1. `session_init.zsh`
2. `role_runtime.zsh`
3. `docs_finalize.zsh`

## Правила

- Новые user-facing команды должны иметь префикс `planveyor_`.
- Модуль не должен зависеть от файлов, которые загружаются позже него.
- Не добавляйте owner-local пути, fallback в домашний каталог, root override или repo-shim fallback. Physical runtime root определяется loaded Planveyor script; внешний consumer выбирается только facade prefix `--project /absolute/path/to/consumer`. Runtime state и optional `PLANVEYOR_CODEX_HOME` задаются явно вне product tree.
- Если меняется порядок загрузки или boundary между модулями, синхронизируй комментарий в `scripts/planveyor.zsh` и этот README.

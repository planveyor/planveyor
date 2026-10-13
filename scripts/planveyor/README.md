# `scripts/planveyor/`

**English** · [Русский](README.ru.md)

Module layer for `scripts/planveyor.zsh`. The facade owns bootstrap and chooses eager, lazy, and conditional loading; these files are not run directly.

## Runtime inventory

Facade (not a module): `scripts/planveyor.zsh`.

| Module | Load mode | Boundary |
| --- | --- | --- |
| `contract_authority.zsh` | eager bootstrap dependency | authority component before public wrapper use |
| `session_init.zsh` | eager | init-time helpers for artifacts, session ids, and new role sessions |
| `role_runtime.zsh` | eager | status-driven entrypoints for roles and Manager |
| `docs_finalize.zsh` | eager | wrappers for the memory-finalize/doc-closeout layer |
| `home_runtime.zsh` | lazy | consumer-owned Codex-home report/refusal adapter |
| `provider_runtime.zsh` | conditional | provider/provenance selector |

## Eager load order

1. `session_init.zsh`
2. `role_runtime.zsh`
3. `docs_finalize.zsh`

## Rules

- New user-facing commands must have the `planveyor_` prefix.
- A module must not depend on files that load after it.
- Do not add owner-local paths, a home-directory fallback, a root override, or a repo-shim fallback. The loaded Planveyor script determines the physical runtime root; an external consumer is selected only by the facade prefix `--project /absolute/path/to/consumer`. Runtime state and the optional `PLANVEYOR_CODEX_HOME` are set explicitly outside the product tree.
- If the load order or the boundary between modules changes, sync the comment in `scripts/planveyor.zsh` and this README.

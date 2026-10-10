# Правила переносимой нормализации

Этот playbook задаёт границу для публичных артефактов Planveyor: нормализация
устраняет локальные детали из нового текста, но не переписывает историю и не
создаёт новую policy-систему.

## Публичный контракт

Публичные content profile IDs `default`, `planveyor` и `target-local`
нормализуются одним generic interpreter. У него нет checked-in таблицы
пользовательских замен, JSON DSL, registry или скрытого выбора policy-файла.

Python API сохраняет два явных способа работы:

- `PortabilityRules` задаёт набор правил, уже выбранный вызывающим кодом.
- Параметр `rules=` позволяет тесту или bounded consumer передать такой набор
  в память для конкретного вызова.

Неизвестный content profile — ошибка до нормализации. Нельзя молча выбрать
`default`, угадать consumer или читать локальный профиль.

## Что нормализируется

| Ситуация | Portable form |
| --- | --- |
| Путь внутри выбранного проекта | literal repo-relative path, например `docs/...` |
| Consumer project для facade | `/absolute/path/to/consumer` только в documented `--project` example |
| Межрепозиторная identity | `<source-repo>` / `<target-repo>` |
| Secret-shaped value | `<REDACTED>` |
| Неизвестный target-local факт | `N/A (why=...)` или конкретный blocker |
| Local derived state | external/disposable state, не checked-in path |

Self-Planveyor commands начинаются с
`./bin/planveyor <planveyor_function> [args…]` из physical Planveyor root.
Sibling commands запускаются через внешний runtime:
`"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" <planveyor_function> [args…]`.
Когда в receipt нужен interpreter, используй `$PYBIN` или `python3`, а не
expanded local path.

## Семантика преобразования

- Применяй literal substitutions детерминированно. Если один source prefix
  является началом другого, сначала обрабатывай более длинный prefix; короткое
  правило не должно повреждать более точное совпадение.
- Generic grammar может заменить локальный путь к Python portable form, но
  version-pinned historical receipt сохраняет свой interpreter text, когда
  caller явно отметил его как pinned evidence.
- Нормализация не доказывает, что команда выполнялась, что provider доступен,
  или что target-local contract принят. Эти факты остаются отдельными evidence
  lanes.
- Не редактируй historical archive JSON или receipt задним числом ради
  косметической переносимости. Новый exported artifact может нести portable
  representation, сохраняя source digest, provenance и integrity boundary
  исходного archive.

## Target-local boundary

Consumer repository владеет своим стеком, credentials, integration policy,
test harness, UI modes и local automation. Planveyor переносит общий lifecycle.
Если для artifact нужен target-local input и он не получен, остановись с
конкретным blocker вместо выдуманной substitution.

## Проверка перед публикацией

1. Проверь changed public artifacts на private paths, account/profile terms,
   source-only identities и secret-shaped values.
2. Убедись, что source/target packet fields используют truthful IDs или
   literal placeholders.
3. Убедись, что command понятна без hidden local configuration.
4. Запусти relevant lint или scanner и запиши current evidence, если artifact
   входит в acceptance gate.

Автоматическая нормализация — guardrail. Она не даёт права публиковать
непроверенный historical artifact и не заменяет human review generic contract.

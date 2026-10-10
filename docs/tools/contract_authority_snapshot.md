# Снимок candidate contract authority (historical/candidate-only)

`scripts/contract_authority_snapshot.py` — чистый Python-модуль без CLI
и регистрации, фундамент пакета A. Он только читает явно переданный
Git worktree, его index и declared runtime worktree. Успешный снимок не
переключает resolver, не запускает provider/queue/SID, не создаёт receipt и не
доказывает, что shell уже source-нул совместимый runtime. Его подключение к
shell и потребителям описано в [интеграции пакета B](contract_authority_integration.md).

## Отдельный live selector

Описанный ниже строгий marker/manifest относится к historical/candidate-only
schema-v1. `capture_candidate_snapshot()` потребляет только v1 и отклоняет v2;
его не требуется вызывать при обычном редактировании local content.

Live resolver использует тот же физический путь
`<target>/docs/_meta/planveyor_contract_authority.v1.json` с отдельным parser
`parse_local_marker_v2_bytes()`. Schema-v2 содержит ровно `schema_version=2`,
`repository_id`, `authority_mode=target-local`, `contract_root` и
`required_runtime_api` (текущий runtime API — 5). Отсутствие marker выбирает
legacy; присутствующий некорректный selector не допускает fallback. Обычные
local reads проверяют корень, разрешённое семейство и regular file через
descriptor, читают текущие байты и сохраняют runtime-code pin. Content manifest,
restamp и равенство каждого content файла HEAD/index/worktree не требуются.

Live context выдаётся как `planveyor_contract_context.v3`; активное наследование
принимает только v3. Публичный `parse_context_envelope()` пассивно проверяет
структуру и digest v1/v2/v3 без runtime capture или чтения target. Эти parser
ветви сохраняют исторические receipts, но не активируют старый контекст.

## Входные данные

Вызывающий код передаёт точный Git top-level target, ожидаемый
`repository_id` и неизменяемый `RuntimeDiskIdentity`. Путь target не является
`pwd` fallback: он должен совпасть с Git `--show-toplevel`. Все Git-вызовы
получают буквальные pathspec, NUL-формат там, где Git его поддерживает, и
окружение без внешних `GIT_*` retargeting-переменных. Сам модуль устанавливает
только read-only controls для отключения replace objects, optional locks и lazy
fetch; это не заменяет доверие к локальному Git binary и repo configuration.

`RuntimeDiskIdentity` содержит:

- `root`, `commit`, `tree` — ожидаемые факты runtime worktree;
- `api_version` — явно переданные данные совместимости;
- `executable_inputs` — tuple `RuntimeContent(path, mode, sha256)` с
  declared, но не исчерпывающим, runtime closure.

Модуль проверяет, что disk Git root/HEAD/tree и каждый declared runtime input
совпадают с этими данными в HEAD, stage-0 index и working tree. В сохранённом
snapshot root заменяется на canonical verified Git top-level, поэтому смена
symlink root на другой clone не может переиспользовать прежний объект.
`executable_inputs` — непустой tuple, но всё равно не претендует на полный
runtime closure. API version внутри этого низкоуровневого API не обнаруживается
из загруженного shell: это trusted caller data. В интеграции B вызывающий слой
сверяет compiled API и loaded-runtime pin отдельно.

## Строгий v1 marker и closure manifest

Marker всегда имеет фиксированный repo-relative путь
`<target>/docs/_meta/planveyor_contract_authority.v1.json` (`MARKER_PATH`). Его JSON строго
UTF-8: duplicate key, неизвестное поле, булево вместо integer, ненормированный
путь или лишний path row приводят к `ContractAuthorityError`.
Text/path values обязаны состоять из Unicode scalar values, кодируемых strict
UTF-8: NUL, DEL и JSON-escaped lone surrogate отклоняются до Git/filesystem
calls. `json.loads` ValueError и RecursionError становятся `invalid_json`, а
caller `Path` с NUL либо lone surrogate — `root_unavailable`, а не uncaught
Python exception. Корректный JSON с другим верхним типом, например `[]`,
отвергается как `json_schema_invalid`; это отличается от ошибки decoder.

```json
{
  "schema_version": 1,
  "repository_id": "example-target",
  "authority_mode": "target-local",
  "contract_root": ".",
  "required_runtime_api": {"minimum": 1, "maximum": 1},
  "closure_manifest": "docs/_meta/planveyor_contract_closure.v1.json",
  "source_baseline": {
    "repository_id": "planveyor",
    "commit": "0123456789abcdef0123456789abcdef01234567"
  }
}
```

`source_baseline` — только declaration copy provenance. Он не обязан совпадать
с текущим runtime commit и не является loaded-runtime pin.

`closure_manifest` — отдельный tracked repo-relative JSON-файл:

```json
{
  "schema_version": 1,
  "required_content": [
    {
      "path": "docs/roles/coder.md",
      "mode": "100644",
      "blob_oid": "0123456789abcdef0123456789abcdef01234567",
      "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    }
  ]
}
```

`contract_root`, `closure_manifest`, rows `required_content.path` и runtime
input paths — repo-relative normalized POSIX paths. `contract_root` может быть
`.`. Каждая required-content row обязана лежать под ним, а marker и manifest
проверяются отдельно и не могут повторяться в `required_content`. Для paths
допустимы только tracked regular Git modes `100644` и `100755`.

V1 принимает только lowercase 40-character SHA-1 Git OID для `blob_oid` и
`source_baseline.commit`; SHA-256 Git repositories в этом пакете намеренно не
поддержаны. Ограничение действует также для HEAD/tree target и runtime,
включая legacy-наблюдение без marker.

## Наблюдение и проверки

`capture_candidate_snapshot(...)` возвращает один из двух immutable объектов:

- `LegacyAuthorityObservation`, только когда marker отсутствует в `HEAD`,
  stage-0 index и worktree;
- `CandidateAuthoritySnapshot`, только когда marker, manifest и каждая
  declared content row одинаковы в `HEAD`, stage-0 index и worktree.

Marker только в index или только в worktree — ошибка, а не legacy/candidate.
`expected_repository_id` сравнивается с marker только для candidate. Legacy
фиксирует отсутствие marker и не удостоверяет identity репозитория;
типизация переданной строки не является проверкой этой identity.
Для каждой required row проверяются Git mode/blob, raw bytes из `git cat-file`,
sha256 и descriptor-anchored worktree read. Symlink в required path либо любом
его ancestor не обходится. Raw Git index получает SHA-256 fingerprint, а
`git ls-files --stage -z` сохраняет parsed entries только для marker, manifest
и declared rows. Наличие unrelated WIP не запрещено; снимок не заявляет
cleanliness всего repo. Поздняя запись в index консервативно invalidates
snapshot, если меняет raw index fingerprint.

После чтения каждого declared runtime closure и target closure модуль повторно
читает Git root/HEAD/tree/raw index и возвращает
`snapshot_changed_during_read`, если basis дрейфовал. Legacy branch повторно
проверяет и отсутствие marker. `validate_runtime_disk_identity` делает две
полные runtime observations. Capture выполняет два полных read-only прохода и
отказывает при отличии между ними. В каждом candidate-проходе после чтения
target полностью повторяется наблюдение declared runtime: root/HEAD/tree,
raw index, stage-0 rows, mode и bytes всех объявленных inputs. Полный результат
сравнивается с первоначальным наблюдением runtime, затем сохраняется финальная
проверка target Git basis. Ошибки повторного runtime-read сохраняют свои reason
codes; изменение полного наблюдения даёт `snapshot_changed_during_read`.
В candidate также сохраняется runtime Git
identity с raw-index digest и stage-0 rows declared runtime inputs.
`verify_candidate_snapshot(snapshot, ..., runtime=...)` выполняет новый
capture и требует точного равенства immutable данных. Поэтому изменение HEAD,
raw index, marker/manifest/declared target input либо declared runtime input
после capture нельзя переиспользовать как старый candidate.

## Границы этого пакета

Снимок не является OS isolation, доказательством полного runtime/content
closure или race-free source pin: файловая primitive фиксирует descriptor chain,
но не может исключить write того же inode с восстановленными metadata между
наблюдениями. Git и файловая система также не дают общей atomic transaction.
Loaded-runtime pin, API assertion после source, pre-dispatch и подключение
readers/generators реализует отдельный слой пакета B. Сам snapshot-модуль
не включает engaged support и не меняет legacy resolvers; его строгая проверка
полного снимка также не заменяет проверку стабильной generation между детьми.

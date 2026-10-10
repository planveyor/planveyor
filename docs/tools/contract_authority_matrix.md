# Static contract-authority matrix

`scripts/contract_authority_matrix_check.py` строит или независимо сверяет
ограниченный статический инвентарь рёбер между зафиксированными Git-объектами.
Это инструмент аудита: он не импортирует код репозитория, не запускает shell-
обёртки, не читает рабочее дерево, не создаёт файлы и не меняет Git-объекты.
Единственный вывод инструмента — канонический JSON в stdout.

При `verify` инструмент дополнительно читает только bytes caller-supplied
serialized `--inventory`; это проверяемый кандидат, а не входной источник
полномочий. Все факты, по которым он реконструирует ожидаемые строки, остаются
чтениями указанного Git commit/tree.

До schema validation декодированный JSON проходит рекурсивную UTF-8 проверку
всех string keys и values. Escaped surrogate не допускается. Любая ошибка
этой проверки получает fixed ASCII error; guarded final serialization возвращает
один канонический failure document с exit code 2, без traceback.

Вызывающая сторона обязательно передаёт файл правил через `--rules-repo-path`.
Это существующий regular Git blob с mode `100644` и JSON по строгой v1 schema
в указанном source commit. Путь и SHA-256 этого объекта входят в вывод вместе
с явными source/target roots, commit и tree. Файл не является реестром
полномочий, конфигурацией runtime или диспетчером.

Публичное дерево не содержит файла правил C1 по умолчанию. Примеры ниже
показывают грамматику команд: до запуска вызывающая сторона должна выбрать
существующий объект правил в зафиксированном source commit.

## Запуск

Обе команды требуют абсолютные roots и полные object ID для каждого commit и
его tree. Перед перечислением инструмент проверяет, что каждый commit
резолвится ровно в переданный tree.

У CLI намеренно нет `-h` или `--help`: оба варианта для root, `emit` и
`verify` считаются ошибкой аргументов. Они возвращают exit code 2, один
канонический JSON failure document в stdout и пустой stderr. Полный способ
вызова зафиксирован в этом документе.

```sh
python3.11 -B scripts/contract_authority_matrix_check.py emit \
  --source-root /absolute/source \
  --source-commit <full-source-commit> \
  --source-tree <full-source-tree> \
  --target-root /absolute/target \
  --target-commit <full-target-commit> \
  --target-tree <full-target-tree> \
  --rules-repo-path <relative-path-to-rules.json>
```

Вызывающая сторона может сохранить stdout вне инструмента и передать этот файл
во вторую независимую реконструкцию:

```sh
python3.11 -B scripts/contract_authority_matrix_check.py verify \
  --source-root /absolute/source \
  --source-commit <full-source-commit> \
  --source-tree <full-source-tree> \
  --target-root /absolute/target \
  --target-commit <full-target-commit> \
  --target-tree <full-target-tree> \
  --rules-repo-path <relative-path-to-rules.json> \
  --inventory /absolute/caller-owned/inventory.json
```

Git вызовы работают с отдельным whitelist-окружением: наследованные `GIT_*`
маршруты и global/system config отбрасываются. Git может использовать локальную
repo config и object database/alternates этого репозитория, но каждый прочитанный
content привязан к указанному object ID. Rules и surface facts читаются только
из именованных Git-объектов; caller-supplied `--inventory` остаётся отдельным
кандидатом для сверки. Присутствующий файл должен быть обычным Git-файлом
`100644` или `100755`; symlink и gitlink в объявленной поверхности считаются
ошибкой целостности. Tree entry обязан быть UTF-8-encodable canonical
repository-relative path и лежать под тем prefix, которым он был запрошен.

## Что перечисляется

Правило задаёт конечный статический фронтир. Для каждого полученного ребра
идентичность состоит ровно из трёх строк:

1. `consumer_anchor`;
2. `logical_referenced_surface`;
3. `target_disposition_scope`.

Каждая строка также содержит pinned object facts потребителя, source surface и
target surface: path, состояние, mode, blob OID и SHA-256. `verify` заново
строит expected rows отдельными selector constructors из тех же Git blobs; он
разделяет только safe Git-object reader и ограниченные AST/phase/lexical
primitives, а не отдельный parser или oracle. Он не доверяет счётчикам, флагу
покрытия или переданным строкам. Missing, duplicate, substituted и extra строки
делают инвентарь невалидным.

Поддерживаемые источники фактов:

- отдельные статически разворачиваемые AST tuples `REQUIRED_ENGAGED_PATHS`
  и `STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS`;
- literal case-map `role:phase -> filename` из одного отмеченного блока;
- физические entries объявленных profile-tree;
- все literal hits в выбранных файлах;
- entries явно ограниченных target-surface tree;
- явные manual research anchors для generated, child-shell и иных поведенческих
  границ.

IDs source selectors, target selectors и `manual:<anchor id>` образуют один
уникальный namespace; duplicate или collision отклоняется до materialization.

AST grammar намеренно узкая: root и достижимые bindings должны иметь ровно одно
прямое module-level tuple-присваивание. Нестарred элементы tuple — только
статические строковые литералы; разворачивание последовательности допускается
только у `*` для статического tuple binding, tuple literal или однопроходного
static generator. Lists, повторные bindings, import/function/class/except/
pattern bindings, wildcard imports, mutation и нераспознанные выражения
отклоняются. `exec`, `globals()` и иные динамические способы менять значение
не входят в эту статическую grammar; они остаются отдельными manual research
obligations.

В `scripts/contract_authority_context.py` обычный статический tuple содержит
59 строк: общие prefix и tail. Merge tuple добавляет 60-ю строку, заданную
`PLANVEYOR_MERGE_GATE_POLICY_PATH`. Переданный
вызывающей стороной набор правил C1 может выбрать эти AST-expandable tuples;
встроенного merge selector у C1 нет. Аудит читает их как Git-object facts и
не исполняет runtime selector.

Политика merge принадлежит declared contract root потребителя. Согласно
`scripts/merge_gate_policy.py`, engaged consumer предоставляет этот carrier
явно, с согласованными identity, marker и API capability. Default, legacy
или неактивированный generic consumer не получает политику или допуск к merge
по умолчанию. Если engaged consumer заявляет merge capability без обязательного
объявленного carrier, проверка завершается отказом до создания tracker artifacts.
Отсутствие этого JSON в публичном source tree не доказывает готовность
engaged потребителя и не требует добавлять сюда его конфигурацию.

Никакой JSON carrier не выбирает UI bodies, и C1 не интерпретирует UI policy
JSON. C1 rows и существующие manual UI/generated anchors фиксируют обязанности
этого доказательства; статический selector не означает автоматического
исследования произвольных JSON, registry или globs.
При переносе строк исходника lexical decision anchors перепривязываются только
к тем же неизменённым literal строкам. Новое или изменённое вхождение требует
собственного решения, после чего `emit` и независимый `verify` заново проверяют
полный инвентарь по явным source/target commit и tree.

Phase selector фиксирует только плоские literal facts из case-блока и literal
имя `*.md`; он не интерпретирует legacy selection. Profile selector перечисляет
Git-tree entries, включая `README` и receipts, если они лежат под объявленным
prefix. Наличие такой entry не доказывает, что она является полным effective
body. Literal selectors — детекторы в заданном лексическом фронтире: новые hits
добавляют строку, но отсутствие hits не устанавливает отсутствие динамического
или generated поведения.

`target_surface_tree` читает каждый объявленный prefix отдельно. При
`require_nonempty: true` под каждым из них должна быть хотя бы одна regular
Git entry; overlap prefix разрешён, а итоговый union дедуплицируется по path и
сортируется. При `require_nonempty: false` каждый prefix optional, поэтому
отсутствующий prefix сам по себе не является ошибкой.

## Решения и результаты

У каждой строки один closed `decision_state`:

- `decided` содержит typed disposition и pinned decision evidence;
- `pending_owner` содержит конкретный вопрос;
- `unresolved_research` содержит конкретную исследовательскую обязанность.

`not_applicable` допустим только как `decided` disposition с объявленным
reason code и pinned source literal proof. Он не выводится из отсутствующего
объекта. Planned extraction может быть `decided` выбором, но его
`implementation_evidence` в версии v1 остаётся `unfulfilled`; `present` в v1
не допускается. Поле implementation evidence не меняет decision state и не
подменяет требуемое отдельное доказательство реализации.

В JSON всегда присутствуют ровно три outcome-поля:

- `inventory_integrity`: `passed` или `failed`;
- `enumerated_decision_completeness`: `complete` или `blocked`;
- `semantic_closure`: всегда `not_claimed`.

По умолчанию валидный инвентарь возвращает exit code 0, даже когда в
объявленном фронтире есть pending/research строки. Флаг
`--require-enumerated-decision-completeness` возвращает 3 для валидного,
но `blocked` результата. Ошибка аргументов, чтения Git-объекта, схемы или
сверки всегда возвращает 2 и имеет приоритет над этим флагом.

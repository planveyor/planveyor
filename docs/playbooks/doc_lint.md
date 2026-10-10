# Playbook: doc_lint (ссылки/код‑рефы)

Цель: держать **канонические** доки в состоянии, где ссылки/рефы не битые, а CI не “красный из‑за истории”.

`scripts/doc_lint.py` проверяет:
1) Markdown ссылки на локальные файлы.
2) (опционально) inline code spans: `...` на существование файлов в репо.

Architecture decision: `docs/adr/006-doc-lint-scoped-closeout-gate.md`.

## Коротко для Owner

### Self-Planveyor

- Обычный gate: `make doc-lint`
- Canonical closeout gate: `planveyor_doc_lint`
- Strict explicit bundle: команда в разделе «Strict canonical pass» ниже; optional project roots добавляем только если они существуют.

### Sibling

- Обычный и canonical closeout gate: `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_doc_lint`
- Strict exact bundle: `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_plan_bundle --check <PLAN_PATH>` вместе с объявленными в plan target-local checks
- Full `docs/**` scan запускаем только отдельной hygiene-задачей; это не повседневный gate.

## Repo-wide hygiene lane

Repo-wide pass по `docs/**` - это отдельная hygiene-задача, а не merge/closeout proof. Он не заменяет self-Planveyor `make doc-lint` / `planveyor_doc_lint`, sibling facade `planveyor_doc_lint`, `planveyor_plan_bundle --check` или объявленные target-local checks для текущего exact bundle.

Structured-doc family gates:
- Process-improvement backlog grammar проверяется отдельным read-only helper'ом: `PYTHONDONTWRITEBYTECODE=1 "$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py process_improvements_lint.py --project-root .`.
- Этот helper валидирует primary truth surface `docs/process_improvements/*__process_improvements_backlog.md` через parser/contract validation и не заменяет markdown link/code-ref lint.
- В `docs/process_improvements/` derived/support файлы index.md, deferred.md, promotion_surface.md, README.md и template backlog не считаются primary grammar truth для default process-improvements lint. Generated views появляются после materialization PI lane; bare init не требует их создания.
- Upstream request packet grammar проверяется source-local read-only helper'ом: `PYTHONDONTWRITEBYTECODE=1 "$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py upstream_request.py --repo-root . --tooling-root . lint [PACKET_OR_DIR ...] [--json]`.
- Этот helper валидирует primary truth surface `docs/upstream_packets/*.md` через `_parse_request` / `_validate_request`, исключает `_template.md` из default corpus и не заменяет markdown link/code-ref lint.
- Rollout packet grammar проверяется source-local read-only wrapper'ом: `planveyor_rollout_packet_lint (--all | docs/rollout_packets/<packet>.md|docs/rollout_packets) [--json]` (direct helper: `PYTHONDONTWRITEBYTECODE=1 "$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_runtime_py rollout_packet.py --repo-root . --tooling-root . lint ...`).
- Этот helper валидирует primary truth surface `docs/rollout_packets/*.md` через packet markdown/meta parser; selected packet core errors exit non-zero, while `--all` keeps historical extra/missing H2 shape drift as warning/report unless core header/meta/enum/context consistency is broken.

Carrier families:
- canonical roots: `AGENTS.md`, `docs/roles/`, `docs/playbooks/`, `<target-declared guide carrier>`, `<PROJECT_ARCH_DOC>` and active canon indexes;
- exact closeout roots: literal files from current plan/code draft/review bundle;
- historical/generated/local buckets: `docs/plans/*`, `docs/reviews/*`, `docs/code_reviews/*`, `docs/doc_reviews/*`, `docs/snapshots/*`, `.tmp/*`, archived or deleted-path references.

Exclusion policy:
- historical/generated/local buckets are explicit hygiene buckets, not silent closeout blockers;
- примерные template paths like `docs/plans/YYMMDD_HHMM_topic.md` stay examples unless a plan names them as real targets;
- deleted or git-history-only references should be fixed by a bounded hygiene plan or recorded as intentionally historical, not smuggled into the closeout gate.

Success condition:
- closeout success = scoped exact bundle/canonical roots are green;
- repo-wide hygiene success = bounded report says which debt buckets were fixed, intentionally excluded, or deferred;
- a red repo-wide scan can create follow-up debt, but it must not retroactively make an already scoped closeout false.

## Доставка shared documents

Для Copier-managed sibling доставка общего контракта идёт через версию
шаблона и локальный план адаптации; source-local извещение лежит в
`docs/contract_notices/`, а не в `docs/rollout_packets/`. Описанный ниже
packet flow применяется только к отдельно объявленным packet consumers.

Shared document delivery запускается только для changed source carrier с
объявленным target contract. Не существует universal sibling, скрытого profile
или broad copy rule.

1. Проверь exact membership публичным readback, если helper materialized:

   ~~~bash
   "$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_shared_docs_mirror_drift \
     --target-root /absolute/path/to/target --json
   ~~~

2. Readback остаётся diagnostic/evidence surface: он не создаёт target,
   не меняет target files и не заменяет packet delivery.
3. Если readback требует delivery, source owner создаёт source-local rollout
   packet для literal target identity и topic. Target owner проверяет и
   принимает packet локально.
4. Если declared contract требует fail-closed CI/manual stop, используй
   соответствующий strict gate через public facade. Он также не заменяет
   packet/adoption flow.

Не делай ручной cp, не сканируй чужой docs tree как writable authority и не
создавай profile overrides без реального consumer. Generated review artifacts,
playbook stubs и tooling-only files входят в delivery только при explicit
membership readback. Shared template остаётся source-owned; stale consumer copy
не должен seed'ить новый scaffold.

## Что считаем “каноническими” roots (strict)
Это подмножество, где broken refs считаем ошибкой (и хотим ловить в CI):
- `AGENTS.md`
- `docs/roles/`
- `docs/playbooks/`
- `<target-declared guide carrier>`
- `<PROJECT_ARCH_DOC>` (индекс)

Исторические/временные артефакты (plans/reviews/snapshots) в строгий линт **не включаем**.

Принцип (важно перед cleanup):
- В канонике избегаем “жёстких” ссылок на времянку, которую планируем удалять (`docs/plans/*`, `docs/code_reviews/*`, `docs/doc_reviews/*`).
- Вместо этого: audit/report в `docs/reviews/*`, follow-up / канон или указание “см. git history: <filename>”. Snapshot'ы не используем как pointer/source в каноне.
- Отдельное правило: active canon и все объявленные architecture/API/schema/registry
  carriers не должны ссылаться ни на какие `docs/snapshots/*`. Их пути берём из `Context links`
  выбранного проекта; shared corpus не задаёт default project inventory.
- Для выбранного registry carrier правило ещё жёстче: active entries указывают на
  canon/runtime/testing docs, audit'ы и follow-up'ы, но не на snapshot'ы.

## Рекомендуемые команды

### Self-Planveyor (physical Planveyor root)

```bash
make doc-lint
```

### Strict canonical pass (Self-Planveyor)
```bash
./bin/planveyor planveyor_doc_lint

# or, with literal roots:
bash "$PLANVEYOR_RUNTIME_ROOT/scripts/run_doc_lint.sh" \
  --root AGENTS.md \
  --root docs/roles \
  --root docs/playbooks \
  --root <target-declared guide carrier> \
  --root docs/arch.md \
  --check-code-refs --code-refs-scope repo
```

### Sibling (external facade)

```bash
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_doc_lint

# exact implementation/review bundle:
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" \
  planveyor_plan_bundle --check <PLAN_PATH>
```

## Про “примерные пути” в backticks
В доках часто встречаются примеры формата:
- `docs/plans/YYMMDD_HHMM_topic.md`
- `docs/code_reviews/YYMMDD_HHMM_topic.md`
- `docs/doc_reviews/YYMMDD_HHMM_topic.md`

Это **не** реальные файлы; линт должен их игнорировать (иначе мы ломаем полезные шаблоны).

## Когда включать “full scan”
“Full scan” по `docs/**` с `--check-code-refs --code-refs-scope repo` делаем только в отдельной задаче (Phase 2) и чиним ошибки пакетно,
потому что в исторических доках много ссылок на удалённые планы/файлы.

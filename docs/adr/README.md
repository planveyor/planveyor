# ADRs в `planveyor`

Зачем:
- держать долгоживущие архитектурные решения отдельно от временных `docs/plans/*` и `docs/*reviews/*`;
- не терять `Key decisions / Constraints`, которые реально ограничивают будущие решения;
- привязывать архитектурное решение к живому якорю реализации, а не к “истории из чата”.

Формат:
- markdown-файл в `docs/adr/`
- шаблон: `docs/adr/_template.md`
- правило именования shared/package: `NNN-topic.md`
- `planveyor/docs/adr/*` = общие process/package decisions; target-repo `adr/*` = repo-local product/runtime decisions и не зеркалятся обратно как второй канон

## Когда создавать ADR
- решение меняет или закрепляет инвариант канона (`AGENTS.md`, `docs/adr/*`, `docs/api.md`, shared playbooks/prompts/contracts`);
- решение ограничивает будущие изменения (“не добавлять второй механизм X без пересмотра этого решения”);
- компромисс иначе выглядит как баг или случайная реализация.

## Когда НЕ создавать ADR
- тактический выбор внутри одного ограниченного implementation slice;
- локальный workaround без долгоживущего contract impact;
- всё, что живёт только как step/command note внутри конкретного плана.

## Статусы
- `proposed`
- `accepted`
- `superseded`

Правило:
- `code-anchor` обязателен до перевода ADR в `accepted`;
- `source-plan` для post-merge/canon-sweep ADR не должен быть live-ссылкой на удаляемый timestamped plan; если plan уйдёт в cleanup, используй `git history: <plan_stem>`.
- supersession truth живёт в `## Superseded by / Supersedes`: новый ADR явно указывает `Supersedes`, а заменённый ADR остаётся со `status: "superseded"` и non-`N/A` значением `Superseded by`.
- в `Supersedes` / `Superseded by` допустимы repo/file path до ADR markdown или bare ADR id, который резолвится в sibling `docs/adr/<id>.md`.
- accepted ADR не пересказывает всю прозу prompt/playbook: долгоживущий invariant живёт в ADR, operational wording остаётся в role docs / prompts / playbooks и ссылается обратно на ADR.

## Как материализовать
- типичный вход = `post_merge_plan_harvest`, когда из `Key decisions / constraints` видно, что решение уже перестало быть временным;
- Architect создаёт черновик ADR;
- сам факт наличия ADR не заменяет canon update или follow-up plan, если реализация/доставка ещё не закрыта.

## Минимальный contract
- frontmatter:
  - `status`
  - `date`
  - `decision-makers`
  - `source-range`
  - `source-plan`
  - `code-anchor`
- секции prose:
  - `Context and Problem Statement`
  - `Decision Drivers`
  - `Considered Options`
  - `Decision Outcome`
  - `Consequences`
  - `Canonical refs`
  - `Confirmation`
  - `Revisit signals`
  - `Superseded by / Supersedes`

## Live shared ADR batch

- `docs/adr/001-plan-path-single-semantic-source-of-truth.md`
- `docs/adr/002-manager-router-only-and-oracle-routing-truth.md`
- `docs/adr/003-single-live-review-route.md`
- `docs/adr/004-exact-bundle-truth-and-closeout.md`
- `docs/adr/005-rollout-packet-is-handoff-not-execution.md`
- `docs/adr/006-doc-lint-scoped-closeout-gate.md`
- `docs/adr/007-planning-dev-contour-boundary.md`
- `docs/adr/009-lint-severity-and-legacy-compatibility.md`
- `docs/adr/010-trusted-local-git-metadata-boundary.md`

## Live ADR index / graph

Источник истины: live markdown-файлы под `docs/adr/[0-9][0-9][0-9]-*.md`.

Export helper: `N/A (why=текущий corpus достаточно мал, чтобы проверять его в этом markdown carrier; generated export/viewer требует отдельного plan с тестами и ownership)`.

| ADR | Статус | Решение | Code anchor | Supersession edges |
| --- | --- | --- | --- | --- |
| `001` | `accepted` | `PLAN_PATH` — единственный семантический источник истины для статуса, Q&A, evidence и handoff contract. | `docs/plans/README.md`; `docs/plans/_template.md`; `docs/roles/manager.md`; `docs/tools/prompts/manager_collab_pipeline.md` | `N/A` |
| `002` | `accepted` | Manager работает только как router; routing truth читается из oracle/repo-backed helper surfaces. | `docs/roles/manager.md`; `docs/tools/prompts/manager_collab_pipeline.md` | `N/A` |
| `003` | `accepted` | Один текущий bundle имеет ровно один live review route. | `docs/plans/README.md`; `docs/plans/_template.md`; `docs/playbooks/review_route_and_receipt_canon.md`; `docs/tools/prompts/reviewer_status_driven.md` | `N/A` |
| `004` | `accepted` | Exact bundle truth и closeout живут в явных file-backed carriers. | `docs/plans/README.md`; `docs/plans/_template.md`; `docs/roles/reviewer.md`; `docs/roles/architect.md` | `N/A` |
| `005` | `accepted` | Rollout packet — source-repo handoff artifact, а не target execution plan. | `docs/plans/README.md`; `docs/plans/_template.md`; `docs/roles/manager.md`; `docs/tools/prompts/manager_collab_pipeline.md` | `N/A` |
| `006` | `accepted` | Closeout через `doc_lint` ограничен exact bundle или canonical roots; broad scans — только hygiene. | `docs/playbooks/doc_lint.md`; `docs/plans/README.md`; `docs/plans/_template.md`; `scripts/run_doc_lint.sh`; `scripts/planveyor.zsh` | `N/A` |
| `007` | `accepted` | `analysis_wave` и `decomposition_wave` принадлежат planning contour; `developer_wave` исполняет только bounded executable handoff. | `docs/playbooks/analysis_wave.md`; `docs/playbooks/decomposition_wave.md`; `docs/plans/README.md`; `docs/plans/_template.md`; `docs/tools/prompts/manager_collab_pipeline.md` | `N/A` |
| `009` | `accepted` | `plan_lint` сохраняет warning-first legacy compatibility для существующих broad lifecycle gaps; global `ERROR` требует migration boundary, corpus report и отдельный accepted implementation plan. | `scripts/plan_lint.py`; `scripts/test_plan_lint.py`; `docs/adr/009-lint-severity-and-legacy-compatibility.md`; `docs/adr/README.md` | `N/A` |
| `010` | `accepted` | Ordinary repo-local tooling доверяет local Git metadata только в supported Owner-controlled environment; unsupported local tampering требует отдельного security scope. | `docs/adr/010-trusted-local-git-metadata-boundary.md`; `docs/tools/prompts/reviewer_status_driven.md`; `scripts/test_manager_custom_pipeline_prompt_contract.py` | `N/A` |

Правило supersession graph:
- edge carrier = `## Superseded by / Supersedes` внутри каждого ADR;
- текущий live graph не имеет edges, потому что у каждого live ADR стоят `Supersedes: N/A` и `Superseded by: N/A`;
- если будущий ADR использует non-`N/A` supersession value, обнови эту таблицу в той же bounded docs change или вынеси generator/helper plan.

Правило legacy/backfill:
- в текущем repo нет live legacy ADR corpus со статусом deprecated или неканоническими supersession carriers;
- legacy/backfill migration поэтому `N/A` для этого corpus, а не скрытое ослабление forward state machine;
- если будущий legacy corpus появится, создай новый follow-up/plan вместо ослабления принятых ADR lint rules здесь.

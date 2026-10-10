---
status: "accepted"
date: 2026-04-21
decision-makers: Architect
source-range: "N/A (why=formalized from already-landed process canon rather than one merge range)"
source-plan: "N/A (private history)"
code-anchor: "docs/plans/README.md; docs/plans/_template.md; docs/roles/manager.md; docs/tools/prompts/manager_collab_pipeline.md"
---

# `PLAN_PATH` как единственный semantic source of truth

## Context and Problem Statement

В shared process canon уже действует правило, что semantic state, routing truth и role-owned questions/evidence живут в `PLAN_PATH`. До formal ADR это знание было размазано по roles/prompts/helpers, поэтому новые slices могли временно вернуться к thread-memory, ledger shortcut или “manager передаст смысл дальше” как будто это допустимый transport.

## Decision Drivers

- один literal carrier для `**Status:**`, Q&A, evidence и “кто следующий”
- запрет на скрытый semantic transport через thread memory, ledger, snapshots или wrapper receipts
- детерминированный cross-role reread без реконструкции контекста по истории сессии

## Considered Options

- Distributed truth между plan, manager memory, ledger и ad-hoc handoff prose.
- `PLAN_PATH` как единственный semantic carrier, а provenance/oracle/helpers как audit или read-only routing surfaces.

## Decision Outcome

Выбранный вариант: **`PLAN_PATH` как единственный semantic source of truth**, потому что только он даёт один repo-backed carrier для `**Status:**`, Q&A, evidence и handoff contract. Ledger, queue/oracle, provenance blocks, snapshots и wrapper receipts могут помогать с routing или audit, но не подменяют plan как semantic truth.

## Consequences

- Плюс: все роли читают один и тот же живой carrier и не спорят о статусе по памяти.
- Плюс: audit/provenance surfaces остаются полезными, но не превращаются во второй semantic state machine.
- Риск: plan нужно держать literal-но актуальным; “потом допишем в evidence/Q&A” ломает этот ADR быстрее, чем drift в подсказках.

## Canonical refs

- `docs/plans/README.md`
- `docs/plans/_template.md`
- `docs/roles/manager.md`
- `docs/tools/prompts/manager_collab_pipeline.md`

## Related ADRs

- `docs/adr/002-manager-router-only-and-oracle-routing-truth.md`
- `docs/adr/003-single-live-review-route.md`
- `docs/adr/004-exact-bundle-truth-and-closeout.md`

## Confirmation

Команды ниже проверяют это ADR в checkout самого Planveyor (Self-Planveyor): они используют `scripts/` и документы движка, которых в sibling нет. В sibling их не запускай; свои docs sibling проверяет через `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_doc_lint`.

- `rg -n "PLAN_PATH|source of truth" docs/plans/README.md docs/plans/_template.md docs/roles/manager.md docs/tools/prompts/manager_collab_pipeline.md`
- `PYBIN="$PYBIN" bash ./scripts/run_doc_lint.sh --root docs/adr/001-plan-path-single-semantic-source-of-truth.md --root docs/plans/README.md --root docs/plans/_template.md --root docs/roles/manager.md --root docs/tools/prompts/manager_collab_pipeline.md`

## Revisit signals

- Нужен второй active semantic carrier помимо plan, а не только audit/read-only helper surface.
- Queue/oracle перестаёт быть status mirror и должен materialize-ить собственный canonical semantic state contract.

## Superseded by / Supersedes

- Supersedes: `N/A`
- Superseded by: `N/A`

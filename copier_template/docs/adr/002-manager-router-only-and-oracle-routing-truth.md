---
status: "accepted"
date: 2026-04-21
decision-makers: Architect
source-range: "N/A (why=formalized from already-landed process canon rather than one merge range)"
source-plan: "N/A (private history)"
code-anchor: "docs/roles/manager.md; docs/tools/prompts/manager_collab_pipeline.md"
---

# Manager = router-only, а routing truth читается через oracle

## Context and Problem Statement

Manager в normal dev flow нужен как router/orchestrator, а не как semantic handoff carrier. До formal ADR это правило уже существовало, но оставалось уязвимым к drift'у: новый prompt или collab-ветка могли начать трактовать manager thread, ledger или spawn handle как источник текущего смысла/статуса.

## Decision Drivers

- Manager не должен становиться скрытым semantic owner поверх Architect/Planner/Coder/Reviewer.
- Routing должен быть deterministic и repo-backed даже в collab/queue mode.
- Repeated same-status loops нельзя “лечить” blind rerun без explicit reroute.

## Considered Options

- Manager как умный semantic relay, который сам интерпретирует память треда и handoff prose.
- Manager как router-only role: status routing идёт через oracle/read-only helpers, semantic blockers поднимаются через plan status/Q&A contract.

## Decision Outcome

Выбранный вариант: **Manager = router-only, а routing truth читается через oracle поверх repo-backed artifacts**, потому что это сохраняет одну semantic ownership chain: роли пишут plan, Manager только читает status/oracle/helper outputs и dispatch'ит следующий шаг. Manager не правит `PLAN_PATH`, не выдумывает bundle и не заменяет Architect как first-line semantic sink.

## Consequences

- Плюс: collab/queue mode остаётся deterministic и не зависит от “помню, что role уже отвечала”.
- Плюс: repeated loop становится явным escalation signal, а не привычкой “запустить ещё раз”.
- Риск: helper/oracle surfaces должны оставаться read-only mirrors, иначе router-only начнёт размываться.

## Canonical refs

- `docs/roles/manager.md`
- `docs/tools/prompts/manager_collab_pipeline.md`

## Related ADRs

- `docs/adr/001-plan-path-single-semantic-source-of-truth.md`
- `docs/adr/004-exact-bundle-truth-and-closeout.md`

## Confirmation

Команды ниже проверяют это ADR в checkout самого Planveyor (Self-Planveyor): они используют `scripts/` и документы движка, которых в sibling нет. В sibling их не запускай; свои docs sibling проверяет через `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_doc_lint`.

- `rg -n "router-only|oracle|blind endless rerun|source of truth" docs/roles/manager.md docs/tools/prompts/manager_collab_pipeline.md`
- `"$PYBIN" -B scripts/doc_lint.py --root docs/roles/manager.md --root docs/tools/prompts/manager_collab_pipeline.md --check-code-refs --code-refs-scope repo --check-anchors`

## Revisit signals

- Manager должен начать владеть semantic mutation, а не только routing/execution orchestration.
- Oracle/helper surfaces больше не могут truthfully отражать repo-backed status без отдельного semantic store.

## Superseded by / Supersedes

- Supersedes: `N/A`
- Superseded by: `N/A`

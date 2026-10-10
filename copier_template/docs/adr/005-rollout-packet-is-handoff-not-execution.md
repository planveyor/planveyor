---
status: "accepted"
date: 2026-04-21
decision-makers: Architect
source-range: "N/A (why=formalized from already-landed process canon rather than one merge range)"
source-plan: "N/A (private history)"
code-anchor: "docs/plans/README.md; docs/plans/_template.md; docs/roles/manager.md; docs/tools/prompts/manager_collab_pipeline.md"
---

# Rollout packet = source-repo handoff artifact, а не execution plan

## Context and Problem Statement

Cross-repo rollout packets уже используются как checked-in handoff between source and target repos. Без formal ADR это правило легко деградирует в ложный mental model: будто packet сам по себе является target execution plan, queue item или license для source repo трогать sibling writable files.

## Decision Drivers

- жёсткий ownership split между source repo и target repo
- target-local import receipt и queue остаются repo-local
- source packet не маскируется под второй executable plan

## Considered Options

- Packet как прямой execution carrier, который source repo может тащить через queue и cross-repo writes.
- Packet как source-side handoff artifact; target repo импортирует его в local plan и только потом запускает local execution/queue.

## Decision Outcome

Выбранный вариант: **rollout packet остаётся только source-side handoff artifact**, потому что только target repo владеет writable bundle, local adoption plan, queueing и review/closeout. Source repo может выпустить packet и зафиксировать bounded target hint (`queue_after_import`), но packet не становится queue item и не даёт source-side execution authority.

## Consequences

- Плюс: ownership split остаётся явным даже для shared canon rollouts.
- Плюс: packet import receipt может truthfully показать, что receipt/linkage materialized, не смешивая это с source plan status или target execution.
- Плюс: target-local plan может отдельно классифицировать per-packet outcome как `adopted`, `pointer-preserved`, `parked`, `superseded` или `rejected/cancelled`.
- Риск: source-side packet status `imported` сам по себе не доказывает target-local adoption/merge protection; это требует explicit target-local per-packet outcome и review/closeout evidence.

## Canonical refs

- `docs/plans/README.md`
- `docs/plans/_template.md`
- `docs/roles/manager.md`
- `docs/tools/prompts/manager_collab_pipeline.md`

## Related ADRs

- `docs/adr/001-plan-path-single-semantic-source-of-truth.md`
- `docs/adr/004-exact-bundle-truth-and-closeout.md`

## Confirmation

Команды ниже проверяют это ADR в checkout самого Planveyor (Self-Planveyor): они используют `scripts/` и документы движка, которых в sibling нет. В sibling их не запускай; свои docs sibling проверяет через `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_doc_lint`.

- `rg -n "rollout packet|target-local|queue after import|source repo" docs/plans/README.md docs/plans/_template.md docs/roles/manager.md docs/tools/prompts/manager_collab_pipeline.md`
- `PYBIN="$PYBIN" bash ./scripts/run_doc_lint.sh --root docs/adr/005-rollout-packet-is-handoff-not-execution.md --root docs/plans/README.md --root docs/plans/_template.md --root docs/roles/manager.md --root docs/tools/prompts/manager_collab_pipeline.md`

## Revisit signals

- Source repo должен начать владеть target execution, а не только handoff artifact.
- Target-local import receipt/queue contract перестаёт существовать или переезжает в новый canonical carrier.

## Superseded by / Supersedes

- Supersedes: `N/A`
- Superseded by: `N/A`

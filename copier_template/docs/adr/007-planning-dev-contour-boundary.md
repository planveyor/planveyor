---
status: "accepted"
date: 2026-06-13
decision-makers: Architect
source-range: "N/A (why=decision promoted from reviewed analysis-wave plan rather than one merge range)"
source-plan: "N/A (private history)"
code-anchor: "docs/playbooks/analysis_wave.md; docs/playbooks/decomposition_wave.md; docs/plans/README.md; docs/plans/_template.md; docs/tools/prompts/manager_collab_pipeline.md"
---

# Граница planning/dev contour

## Context and Problem Statement

`analysis_wave` и `decomposition_wave` уже используют тот же role conveyor, что и ordinary dev work, но их результатом является planning artifact, а не implementation diff. Без отдельного ADR будущие prompt/helper edits могут принять broad analytics, child graph creation или `route_recommendation` prose за право dispatch-ить работу в `developer_wave`.

Это решение фиксирует durable boundary: planning contour выпускает reviewed analysis/decomposition artifacts и promoted route truth, а dev contour исполняет только bounded executable handoff.

## Decision Drivers

- Один conveyor не должен стирать границу между planning artifacts и executable work.
- `route_recommendation` является recommendation/provenance, а не queue или dispatch authority.
- Runner/model choice должен оставаться admission metadata, not route enum.
- Существующие ADR 001..006 фиксируют plan truth, Manager/router, review route, exact bundle, rollout packet и doc-lint boundaries, но не владеют planning/dev contour boundary.

## Considered Options

- Оставить boundary только в playbooks/prompts и source analysis plan.
- Зафиксировать planning/dev contour boundary как ADR, а operational wording оставить в playbooks/prompts.
- Ввести отдельную role/lane taxonomy для analysis/decomposition work.

## Decision Outcome

Выбранный вариант: **зафиксировать planning/dev contour boundary как ADR**, потому что это долгоживущий invariant, который ограничивает будущие prompts/helpers/routes без дублирования operational prose.

Решение:
- `planning contour` = `analysis_wave` + `decomposition_wave`. Эти runs выпускают repo-backed planning artifacts: `analysis_pack`, promoted route artifact, decomposition umbrella, child graph/linkage, seed plans, follow-ups, Owner gates или rejection/defer receipts.
- `dev contour` / `delivery contour` = ordinary `developer_wave` от bounded executable handoff до documentation/code/runtime diff, review, Architect closeout и post-merge governance tail.
- Ordinary `developer_wave` не имеет права молча делать broad analytics, child graph creation или hidden decomposition. Если появляются `split_required=true`, broad unknowns или child graph, роль должна блокировать работу или reroute-ить её в planning contour.
- `analysis_pack.route_recommendation` остаётся только recommendation. Accepted route truth появляется только после review и Architect arch review через promoted route artifact/status/linkage.
- `queue_admission` и `runner_admission` живут в promoted route / queue / child-contract fields. Runner/model choice является admission metadata, а не route selector и не причина запускать `decomposition_wave`.
- Этот ADR не supersede-ит ADR 001..006; он дополняет их, называя contour ownership.

## Consequences

- Плюс: будущая Manager/prompt/helper работа имеет один durable contour invariant вместо реконструкции из plan history.
- Плюс: analysis/decomposition могут использовать тот же role conveyor, не притворяясь executable `developer_wave` work.
- Плюс: queue and runner admission остаются explicit fields, а не выводятся из route prose или model preference.
- Риск: operational examples всё ещё могут drift-ить в prompts/playbooks; они должны ссылаться на этот ADR или сохранять его invariant, а не копировать весь decision text.
- Риск: будущий materialized QA route или новая runner family могут потребовать пересмотра admission fields без ослабления contour split.

## Canonical refs

- `docs/playbooks/analysis_wave.md`
- `docs/playbooks/decomposition_wave.md`
- `docs/plans/README.md`
- `docs/plans/_template.md`
- `docs/tools/prompts/manager_collab_pipeline.md`

## Related ADRs

- `docs/adr/001-plan-path-single-semantic-source-of-truth.md`
- `docs/adr/002-manager-router-only-and-oracle-routing-truth.md`
- `docs/adr/003-single-live-review-route.md`
- `docs/adr/004-exact-bundle-truth-and-closeout.md`
- `docs/adr/005-rollout-packet-is-handoff-not-execution.md`
- `docs/adr/006-doc-lint-scoped-closeout-gate.md`

## Confirmation

Команды ниже проверяют это ADR в checkout самого Planveyor (Self-Planveyor): они используют `scripts/` и документы движка, которых в sibling нет. В sibling их не запускай; свои docs sibling проверяет через `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_doc_lint`.

- `rg -n "planning contour|dev contour|developer_wave|analysis_wave|decomposition_wave|route_recommendation|runner_admission|queue_admission" docs/playbooks/analysis_wave.md docs/playbooks/decomposition_wave.md docs/plans/README.md docs/plans/_template.md docs/tools/prompts/manager_collab_pipeline.md docs/adr/007-planning-dev-contour-boundary.md`
- `PYBIN="$PYBIN" bash ./scripts/run_doc_lint.sh --root docs/adr/007-planning-dev-contour-boundary.md --root docs/adr/README.md --root docs/playbooks/analysis_wave.md --root docs/playbooks/decomposition_wave.md --root docs/plans/README.md --root docs/plans/_template.md --root docs/tools/prompts/manager_collab_pipeline.md`

## Revisit signals

- Новая materialized route family требует accepted route truth вне promoted route artifact/status/linkage.
- Runner/model admission становится route authority вместо readiness metadata.
- `developer_wave` намеренно начинает владеть broad analysis или child graph creation.
- Будущий ADR supersede-ит analysis/decomposition route semantics или переносит contour boundary в другой canonical carrier.

## Superseded by / Supersedes

- Supersedes: `N/A`
- Superseded by: `N/A`

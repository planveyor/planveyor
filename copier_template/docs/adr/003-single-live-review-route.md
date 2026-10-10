---
status: "accepted"
date: 2026-04-21
decision-makers: Architect
source-range: "N/A (why=formalized from already-landed process canon rather than one merge range)"
source-plan: "N/A (private history)"
code-anchor: "docs/plans/README.md; docs/plans/_template.md; docs/playbooks/review_route_and_receipt_canon.md; docs/tools/prompts/reviewer_status_driven.md"
---

# Для текущего bundle существует ровно один live review route

## Context and Problem Statement

Review host drift уже несколько раз появлялся как process bug: docs-only и mixed bundle могли держать разные live review paths одновременно или flip-аться не во всех carriers. Это ломает deterministic review route и заставляет Reviewer/Architect гадать, какой файл считается текущим.

## Decision Drivers

- один literal review artifact path для текущего bundle
- синхронный route flip между plan, code draft и review host
- запрет на parallel live `docs/doc_reviews/...` и `docs/code_reviews/...`

## Considered Options

- Держать несколько live review paths “на всякий случай”.
- Держать один literal current route, а остальные упоминания оставлять только как stale/history notes или future flip rule.

## Decision Outcome

Выбранный вариант: **ровно один live review route на текущий bundle**, потому что review host сам входит в exact bundle и должен быть reconstructable без эвристики. Docs-only bundle живёт в `docs/doc_reviews/...`; любой bundle с non-doc carrier живёт в `docs/code_reviews/...`; route flip materialize-ится literal-но и одновременно в plan, code draft и review file path contract.

## Consequences

- Плюс: Reviewer и Architect видят один current review artifact и один freshness lifecycle.
- Плюс: bundle classification (`docs-only` vs mixed) становится machine-checkable.
- Риск: stale historical notes нужно держать вне live carrier path, иначе легко создать ложный dual-route drift.

## Canonical refs

- `docs/plans/README.md`
- `docs/plans/_template.md`
- `docs/playbooks/review_route_and_receipt_canon.md`
- `docs/tools/prompts/reviewer_status_driven.md`

## Related ADRs

- `docs/adr/001-plan-path-single-semantic-source-of-truth.md`
- `docs/adr/004-exact-bundle-truth-and-closeout.md`

## Confirmation

Команды ниже проверяют это ADR в checkout самого Planveyor (Self-Planveyor): они используют `scripts/` и документы движка, которых в sibling нет. В sibling их не запускай; свои docs sibling проверяет через `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_doc_lint`.

- `rg -n "docs/code_reviews|docs/doc_reviews|single live review route" docs/plans/README.md docs/plans/_template.md docs/playbooks/review_route_and_receipt_canon.md docs/tools/prompts/reviewer_status_driven.md`
- `PYBIN="$PYBIN" bash ./scripts/run_doc_lint.sh --root docs/adr/003-single-live-review-route.md --root docs/playbooks/review_route_and_receipt_canon.md --root docs/plans/README.md --root docs/plans/_template.md --root docs/tools/prompts/reviewer_status_driven.md`

## Revisit signals

- Review flow действительно требует несколько одновременно живых reviewer artifacts для одного bundle, а не stale/history notes.
- Review host перестаёт быть частью exact closeout bundle и переносится в другой canonical carrier family.

## Superseded by / Supersedes

- Supersedes: `N/A`
- Superseded by: `N/A`

---
status: "accepted"
date: 2026-04-22
decision-makers: Architect
source-range: "N/A (why=decision formalized through the landed helper slice plus this dedicated ADR-text child, not a single merge range)"
source-plan: "N/A (private history)"
code-anchor: "docs/playbooks/doc_lint.md; docs/plans/README.md; docs/plans/_template.md; scripts/run_doc_lint.sh; scripts/planveyor.zsh"
---

# `doc_lint` closeout = только scoped exact bundle или canonical roots

## Context and Problem Statement

К моменту materialization этого ADR shared process canon уже разделил две разные функции `doc_lint`: closeout proof для bounded current bundle и broad repo-wide hygiene sweep по историческим/non-canonical carriers. Без отдельного ADR это правило жило в sibling helper slice, playbook wording и runbook anchors, поэтому его было легко снова спутать с “просто запускаем самый широкий scan и считаем это merge gate”.

## Decision Drivers

- merge/closeout proof должен быть deterministic и exact-bundle-backed, а не зависеть от исторического шума в repo
- repo-wide `docs/**` / historical scan остаётся полезным, но не должен ломать truthful bounded closeout
- durable shared invariant должен жить в ADR, а operator wording и wrappers могут только ссылаться на него

## Considered Options

- Считать repo-wide `doc_lint` sweep обычным closeout gate и принимать incidental red/green как truth.
- Держать closeout `doc_lint` scoped к exact bundle или canonical roots, а broad repo-wide sweep оставить отдельной hygiene-only lane.
- Вообще не фиксировать это как ADR и оставить правило только в playbook/runbook prose.

## Decision Outcome

Выбранный вариант: **closeout/merge `doc_lint` всегда scoped к exact bundle или canonical roots, а broad repo-wide sweep остаётся hygiene-only lane**, потому что только так closeout truth остаётся согласованным с ADR `004-exact-bundle-truth-and-closeout.md` и с literal bounded carriers, которые реально идут в review/commit. Repo-wide historical debt может жить отдельно, не подменяя собой merge truth.

## Consequences

- Плюс: bounded closeout не становится ложным красным из-за `.tmp/`, архивных review/doc carriers и других non-canonical хвостов.
- Плюс: operator wrappers и runbooks могут честно различать `planveyor_doc_lint` как canonical closeout gate и broad scan как отдельную hygiene-задачу.
- Риск: если кто-то снова захочет сделать repo-wide scan default merge gate, это уже будет conscious ADR revisit, а не “случайная удобная команда”.
- Риск: historical doc debt не исчезает сама собой; для genuinely green repo-wide sweep нужен отдельный hygiene slice.

## Canonical refs

- `docs/adr/004-exact-bundle-truth-and-closeout.md`
- `docs/playbooks/doc_lint.md`
- `docs/plans/README.md`
- `docs/plans/_template.md`

## Confirmation

Команды ниже проверяют это ADR в checkout самого Planveyor (Self-Planveyor): они используют `scripts/` и документы движка, которых в sibling нет. В sibling их не запускай; свои docs sibling проверяет через `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_doc_lint`.

- `rg -n "Canonical closeout gate|Full docs/\\*\\* scan|hygiene-only|planveyor_doc_lint" docs/playbooks/doc_lint.md docs/plans/README.md docs/plans/_template.md`
- `./bin/planveyor planveyor_doc_lint >/dev/null`
- `PYBIN="$PYBIN" bash ./scripts/run_doc_lint.sh --root docs/adr/006-doc-lint-scoped-closeout-gate.md --root docs/playbooks/doc_lint.md --root docs/plans/README.md --root docs/plans/_template.md`

## Revisit signals

- shared canonical root set для strict closeout materially меняется и current ADR больше не объясняет real gate surface
- repo-wide historical scan становится cheap/green enough, чтобы его сознательно подняли до merge/closeout default
- closeout truth перестаёт быть exact-bundle-backed и уходит в другой shared carrier family

## Superseded by / Supersedes

- Supersedes: `N/A`
- Superseded by: `N/A`

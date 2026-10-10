---
status: "accepted"
date: 2026-06-22
decision-makers: Architect
source-range: "N/A (why=decision promoted from reviewed analysis-wave plan rather than one merge range)"
source-plan: "N/A (private history)"
code-anchor: "scripts/plan_lint.py; scripts/test_plan_lint.py; docs/adr/README.md"
---

# ADR 009: lint severity и legacy compatibility

## Context and Problem Statement

`scripts/plan_lint.py` intentionally keeps broad roadmap/umbrella lifecycle gaps warning-first for the existing corpus. The reviewed source analysis found that current tests assert `WARN` for this family and that a blanket `WARN -> ERROR` flip would turn live historical plans red without a migration boundary.

This ADR records the durable policy boundary: warning-first legacy compatibility remains the default for existing broad lifecycle gaps, while stricter enforcement stays possible only through an explicit bounded implementation plan.

## Decision Drivers

- Preserve compatibility for existing terminal plans and warning-first fixtures.
- Prevent accidental global hard-fail behavior from prose-only process requirements.
- Keep a path to stricter enforcement through a named migration boundary, corpus report and tests.
- Separate policy canon from helper/test/runtime changes.

## Considered Options

- Flip all matching lifecycle warnings to `ERROR` immediately.
- Add bounded `ERROR` enforcement only for new files, schema-current plans or timestamped ranges.
- Add a separate strict gate command with its own corpus report, docs and tests.
- Keep `WARN` forever for this warning family.
- Accept an ADR-first policy and leave helper severity changes to later scoped plans.

## Decision Outcome

Выбранный вариант: **accepted ADR-first warning-compatible policy**, потому что он фиксирует инвариант без hidden helper/runtime change.

Решение:
- Existing broad roadmap/umbrella lifecycle gaps remain warning-first by default in `scripts/plan_lint.py`.
- Blanket global `WARN -> ERROR` for this family is forbidden without a migration boundary and corpus report.
- Stricter enforcement may be introduced later only by an accepted implementation plan that names the boundary, affected corpus, fixtures, public command/docs surface and dependent tests.
- This ADR does not change `plan_lint.py`, `scripts/test_plan_lint.py`, Manager commands or the old plan corpus by itself.

## Consequences

- Плюс: future severity work has a clear compatibility contract and cannot treat current warnings as silently hard-blocking.
- Плюс: old terminal plans do not become red just because a policy discussion was accepted.
- Плюс: bounded strict modes remain available with explicit proof.
- Риск: warning-first behavior can continue to let real lifecycle debt pass. Mitigation: create a later strict-gate or bounded-enforcement plan with corpus readback and fixtures.

## Canonical refs

- `scripts/plan_lint.py`
- `scripts/test_plan_lint.py`
- исходные plans и doc review анализа: `N/A (private history)`
- `docs/adr/README.md`

## Related ADRs

- `docs/adr/004-exact-bundle-truth-and-closeout.md`
- `docs/adr/006-doc-lint-scoped-closeout-gate.md`
- `docs/adr/007-planning-dev-contour-boundary.md`

## Confirmation

Команды ниже проверяют это ADR в checkout самого Planveyor (Self-Planveyor): они используют `scripts/` и документы движка, которых в sibling нет. В sibling их не запускай; свои docs sibling проверяет через `"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_doc_lint`.

- `rg -n "UMBRELLA_ROADMAP_LIFECYCLE_WARNING_PREFIX|Done roadmap/umbrella|Done selected roadmap child punts" scripts/plan_lint.py scripts/test_plan_lint.py`
- `bash scripts/run_doc_lint.sh --root docs/adr/009-lint-severity-and-legacy-compatibility.md --root docs/adr/README.md`

## Revisit signals

- A later accepted plan chooses a new-file/schema-current/timestamp boundary for `ERROR`.
- A public strict gate command is introduced for lifecycle warnings.
- Corpus cleanup removes the compatibility risk that currently requires warning-first behavior.
- `scripts/test_plan_lint.py` no longer asserts `WARN` for the existing broad roadmap/umbrella lifecycle warning family.

## Superseded by / Supersedes

- Supersedes: `N/A`
- Superseded by: `N/A`

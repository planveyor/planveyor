# Planning-contour continuity

**English** · [Русский](planning_contour_continuity.ru.md)

This file is a short reread pointer for planning work after a context reset. It
is not a history archive, a profile registry, or a second source of routing
truth.

## What to reread

1. `docs/adr/007-planning-dev-contour-boundary.md` for the planning/dev
   boundary.
2. `docs/plans/README.md` and `docs/plans/_template.md` for statuses, handoff,
   and the executable bundle.
3. `docs/_meta/plan_vocab.json` for the parser-facing vocabulary.
4. `docs/playbooks/analysis_wave.md` or
   `docs/playbooks/decomposition_wave.md`, if the selected task declares the
   matching mode.

## Rule

Route, queue admission, runner admission, review freshness, and target adoption
are checked by the current plan and their helpers. Do not infer them from this
guide, from an old receipt, or from a missing profile overlay.

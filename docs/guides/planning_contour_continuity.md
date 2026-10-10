# Planning-contour continuity

Этот file — короткий reread pointer для planning work после context reset. Он не
является history archive, profile registry или second source of routing truth.

## Что перечитать

1. `docs/adr/007-planning-dev-contour-boundary.md` для границы planning/dev.
2. `docs/plans/README.md` и `docs/plans/_template.md` для статусов, handoff и
   executable bundle.
3. `docs/_meta/plan_vocab.json` для parser-facing vocabulary.
4. `docs/playbooks/analysis_wave.md` или
   `docs/playbooks/decomposition_wave.md`, если выбранная задача объявляет
   соответствующий mode.

## Правило

Route, queue admission, runner admission, review freshness и target adoption
проверяются current plan и their helpers. Не выводи их из этого guide, из
старого receipt или из отсутствующего profile overlay.

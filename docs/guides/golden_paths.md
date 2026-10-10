# Реестр повторяемых потоков

Этот файл даёт короткие entrypoint pointers. Он не выбирает status, queue mode,
runner или target-local contract вместо текущего plan.

## Post-merge audit

- **Когда:** после delivery wave, когда нужен durable audit до cleanup.
- **Carrier:** `docs/playbooks/post_merge_audit.md` и review template.
- **Результат:** audit, explicit follow-ups или no-op reason; решение о cleanup остаётся у Owner.

## Post-merge plan harvest

- **Когда:** до cleanup, если terminal plans/reviews могли оставить actionable debt.
- **Carrier:** `docs/playbooks/post_merge_plan_harvest.md`.
- **Результат:** deduplicated follow-ups/process improvements или exact no-op.

## Process-improvement promotion

- **Когда:** role/review обнаружил gap в shared process.
- **Carrier:** `docs/process_improvements/README.md` и source backlog template.
- **Результат:** triage, bounded delivery carrier или explicit deferred/rejected decision.

## Source rollout packet lifecycle

- **Когда:** source change нужно передать consumer.
- **Carrier:** `docs/rollout_packets/_template.md` и
  `docs/guides/lifecycle-and-packets.md`.
- **Граница:** packet остаётся handoff; source не ставит его в execution queue.

## Target adoption rollout packet adoption

- **Когда:** consumer получает packet и должен применить его locally.
- **Carrier:** target-local adoption plan/import receipt и exact outcome carrier.
- **Граница:** outcome — решение consumer через facade prefix `--project /absolute/path/to/consumer`; source ACK materialize-ит receipt pointer и сам по себе может оставить packet в ожидании outcome. Обычный flow пишет outcome до ACK.

## Planning-contour continuity

- **Когда:** planning wave возобновляется после смены контекста.
- **Carrier:** `docs/guides/planning_contour_continuity.md`, ADR 007,
  `docs/plans/README.md` и `docs/_meta/plan_vocab.json`.
- **Граница:** guide — только navigation; current plan and Oracle own route truth.

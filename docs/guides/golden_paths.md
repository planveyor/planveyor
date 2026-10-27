# Golden paths

**English** · [Русский](golden_paths.ru.md)

This file gives short pointers to entry points. It does not choose the status,
queue mode, runner, or target-local contract in place of the current plan.

The prompts also name `memory-finalize/docs-closeout`, but it has no separate
supported Golden Path anchor. Follow the [launch guide](launch-and-role-modes.md)
for docs closeout. For harvest work, use the existing
`docs/guides/golden_paths.md#post-merge-plan-harvest` carrier below. If no existing
row fits the task, record a follow-up or `N/A (why=...)`; do not invent an anchor.

## Post-merge audit

- **When:** after a delivery wave, when a durable audit is needed before cleanup.
- **Carrier:** `docs/playbooks/post_merge_audit.md` and the review template.
- **Result:** an audit, explicit follow-ups, or a no-op reason; the cleanup decision stays with the Owner.

## Post-merge plan harvest

- **When:** before cleanup, if terminal plans or reviews may have left actionable debt.
- **Carrier:** `docs/playbooks/post_merge_plan_harvest.md`.
- **Result:** deduplicated follow-ups and process improvements, or an exact no-op.

## Process-improvement promotion

- **When:** a role or a review found a gap in the shared process.
- **Carrier:** `docs/process_improvements/README.md` and the source backlog template.
- **Result:** triage, a bounded delivery carrier, or an explicit decision to defer or reject.

## Source rollout packet lifecycle

- **When:** a source change has to be passed to a consumer.
- **Carrier:** `docs/rollout_packets/_template.md` and
  `docs/guides/lifecycle-and-packets.md`.
- **Boundary:** the packet stays a handoff; the source does not put it in an execution queue.

## Target adoption rollout packet adoption

- **When:** a consumer receives a packet and has to apply it locally.
- **Carrier:** the target-local adoption plan, which is also the import receipt, and the exact outcome carrier.
- **Boundary:** the outcome is the consumer's decision, made through the facade prefix `--project /absolute/path/to/consumer`. The source ACK materializes a receipt pointer and by itself may leave the packet waiting for the outcome. The normal flow writes the outcome before the ACK.

## Planning-contour continuity

- **When:** a planning wave resumes after a context change.
- **Carrier:** `docs/guides/planning_contour_continuity.md`, ADR 007,
  `docs/plans/README.md`, and `docs/_meta/plan_vocab.json`.
- **Boundary:** the guide is for navigation only; the route truth belongs to the current plan and Oracle.

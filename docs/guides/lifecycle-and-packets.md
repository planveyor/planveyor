# Lifecycle and packets

**English** · [Русский](lifecycle-and-packets.ru.md)

This guide describes the shared Planveyor lifecycle. It does not replace the scope, the acceptance criteria, or the status of the current plan.

## Plan, queue, and review

Choose the literal project and plan path, then read the routing truth through the facade:

```zsh
./bin/planveyor --project /absolute/path/to/consumer \
  planveyor_plan_status_oracle --json docs/plans/<plan>.md
```

Before the handoff, run the plan lint and the target validation that the selected project and the current plan require. Only the explicit `planveyor_q_*` helpers materialize the queue state; the active plan pointer does not replace the queue truth. Before you replace or clear the queue, read its state with `planveyor_q_show`. Pass an explicit `--for-manager-mode` to `planveyor_q_set` and `planveyor_q_append`; `planveyor_q_clear` takes no Manager mode and accepts only the optional `--json` flag.

The exact bundle, the review artifact, and CENSOR remain separate evidence carriers. Positive text in a role response, a historical receipt, or a broad static scan does not close the current bundle without the matching readback.

## Post-merge and closeout

After a delivery reaches a terminal status, move the durable decisions into the canon, save the real follow-ups and process improvements in their own carriers, then run the target checks and the documentation checks. Temporary plans and review artifacts are deleted only after fresh cleanup evidence and an explicit Owner decision.

See also:

- [post-merge audit](../playbooks/post_merge_audit.md) (in Russian);
- [post-merge plan harvest](../playbooks/post_merge_plan_harvest.md) (in Russian);
- [post-merge docs hygiene](../playbooks/post_merge_docs_hygiene.md) (in Russian).

## Rollout, adoption, and ACK

A packet is a handoff between the Planveyor source and a consumer, not an executable plan in the source repository. Source-local helpers run from the physical Planveyor root without `--project`; use only source-local packet paths and a literal `<target-repo>`.

```zsh
./bin/planveyor planveyor_rollout_packet_create <target-repo> <topic-slug> \
  --source-plan docs/plans/<source>.md --target-kind plan_adoption
./bin/planveyor planveyor_rollout_packet_show docs/rollout_packets/<packet>.md
./bin/planveyor planveyor_rollout_packet_import_instructions \
  docs/rollout_packets/<packet>.md --print-target-plan-seed
```

The normal delivery order: the consumer materializes the target-local adoption plan/import receipt, then records one outcome in the selected consumer project through the public facade:

```zsh
./bin/planveyor --project /absolute/path/to/consumer \
  planveyor_rollout_packet_outcome_set \
  --target-plan docs/plans/<target-adoption>.md --packet-id <id> \
  --packet-path docs/rollout_packets/<packet>.md --outcome <canonical-or-alias>
```

This write changes only the target-local structured carrier. Then the source records a separate receipt:

```zsh
./bin/planveyor planveyor_rollout_packet_ack \
  --packet docs/rollout_packets/<packet>.md --status imported \
  --target-plan docs/plans/<target-adoption>.md
```

ACK materializes a pointer to `docs/plans/<target-adoption>.md`, but by itself it does not prove a finished target outcome and may leave the packet waiting for the outcome.

Use `planveyor_rollout_packet_lint`, `planveyor_rollout_packet_inbox`, `planveyor_rollout_packet_adoption_plan`, `planveyor_rollout_packet_query`, and `planveyor_rollout_packet_reconcile` for readback and planning state. An upstream request is a separate carrier; the public lifecycle uses `planveyor_upstream_request_show`, `planveyor_upstream_request_import`, `planveyor_upstream_request_ack`, and `planveyor_upstream_request_query`.

The report/reuse gate does not change a packet, but it writes a new report under `docs/reviews/*_packetization_gate_range_*.md` and, with the default output path, marks previous reports for the same range as superseded. Blocking rows produce exit code 2. On this report path, `--range` is optional when a saved range is available; the example selects it explicitly:

```zsh
./bin/planveyor planveyor_post_merge_packetization_gate --range BASE..HEAD
```

To restamp or recover a packet, name the source-local packet explicitly:

```zsh
./bin/planveyor planveyor_post_merge_packetization_gate_recover \
  --range BASE..HEAD --packet docs/rollout_packets/<packet>.md \
  --source-plan docs/plans/<source>.md --stage-packets
```

`--range` is required for recovery; `--source-plan` is optional provenance; `--packet` can be repeated. A call without a named packet stays on the report/reuse path and does not replace a packet update. These helpers do not authorize direct sibling writes, queue activation, or publication.

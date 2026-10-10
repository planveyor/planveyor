---
name: planveyor-plan-queue
description: "Use when Codex needs to materialize, inspect, replace, clear, troubleshoot, or run a Planveyor Manager execution queue from repo-local `docs/plans/*.md` files, plan statuses, or an umbrella plan's `## Execution queue`."
---

# Planveyor Plan Queue

Работайте с Manager queue только через checked-in runtime helpers. Queue state — operational state выбранного project, а не hand-edited planning artifact.

## Project и queue truth

Все public commands идут через facade Planveyor с explicit project:

```zsh
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_q_show
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_q_history --limit 20
```

`PLANVEYOR_RUNTIME_ROOT` — абсолютный путь к checkout Planveyor (так же, как в `AGENTS.md` sibling), `--project "$PWD"` — корень выбранного проекта, в котором вы работаете. Если переменная не задана, спросите путь у владельца, не угадывайте. Для работы над самим Planveyor тот же facade вызывается из его корня без `--project`.

Queue state состоит из current queue, append-only history и, при незавершённой transaction, recovery journal/lock. Active plan pointer не является queue source of truth. Никогда не редактируйте queue state, history, journal или lock вручную.

## Recovery required

Если `planveyor_q_show`, `planveyor_q_history` или другой queue reader сообщает `recovery_required` либо `diverged`, остановите routing и покажите Owner structured payload:

```zsh
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_q_show --json
```

Payload называет `error`, `classification`, `transaction_id`, `operation`, `marker_path` и `recovery_command`. При `recovery_required` это `planveyor_q_recover`: команда завершает или откатывает прерванную transaction либо выполняет обязательный legacy repair. Запускайте её только по решению Owner:

```zsh
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" planveyor_q_recover --json
```

При `diverged` `recovery_command` равен `null`: история очереди разошлась, `planveyor_q_recover` её не чинит (`result=blocked`), и решение остаётся за Owner. Не продолжайте routing до решения Owner. Не удаляйте journal или lock, не угадывайте state и не обходите transaction.

## Safe workflow

1. Inspect existing queue before mutation.
2. Decide whether replacement is explicit. `planveyor_q_set` reconstructs the queue; it is not implicit append/merge.
   Никогда не заменяйте queue с non-terminal active item.
3. Determine the requested Manager mode before queueing: `manager-collab` или `manager-custom-pipeline`. Queue state and candidate plans never choose or switch mode.
4. Validate every explicit candidate plan through the target-required plan lint before queueing it.
5. Materialize with literal paths and mode:

```zsh
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" \
  planveyor_q_set docs/plans/YYMMDD_HHMM_first.md \
  docs/plans/YYMMDD_HHMM_second.md --for-manager-mode manager-collab
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" \
  planveyor_q_set --from-umbrella docs/plans/YYMMDD_HHMM_umbrella.md \
  --resume-parent owner-restamp-required --for-manager-mode manager-custom-pipeline
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" \
  planveyor_q_append docs/plans/YYMMDD_HHMM_tail.md \
  --for-manager-mode manager-collab
```

Use `--status` only when the user accepts its broad selection. `--from-umbrella` may expand only repo-backed children with explicit ordering; prose does not supply queue order. Append stays explicit-path-only.

6. Verify fresh state and report active item, pending count, next pending plan, stop reason, mode, and any incompatibility receipt.
7. Start the chosen Manager mode only after queue admission:

```zsh
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" \
  planveyor_manager_collab_tui --q
"$PLANVEYOR_RUNTIME_ROOT/bin/planveyor" --project "$PWD" \
  planveyor_manager_collab_cmd run Q
```

Use the Custom TUI/one-shot commands when the explicitly selected mode is Custom. Inside an open Manager TUI, `run Q` is the bounded queue command.

## Queue rules

- Queue only target-local `docs/plans/*.md` files.
- Do not queue rollout packets, review files, source packets for another repository, or sibling paths.
- Cross-repository work stays packet-based: source creates a packet; target imports it into a target-local plan; only that plan can enter the target queue.
- Missing or non-lintable umbrella children are blockers, never a reason to synthesize plans from prose.
- `Done` and `Superseded` are terminal for ordinary executable items.
- A mode mismatch is a recorded operational skip or blocker; it never authorizes automatic mode switching.
- `max_iterations_reached` is usually a checkpoint. Inspect current queue state before deciding whether to resume.
- Clear a queue only when explicitly requested or after an explicit reported replacement decision.

## External-only V2 follow-ups

Do not queue-import a `followups.v2` row and do not synthesize `plan_meta.followups_out` for a `plan.v2` artifact. Deferred V2 work stays external and is promoted through its own checked-in carrier.

## Final response

State whether the queue was inspected, created/replaced, cleared, or only diagnosed; list the exact command, active plan, pending count, next plan, and the selected Manager launch command.

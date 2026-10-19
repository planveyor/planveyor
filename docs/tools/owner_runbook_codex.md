# Owner runbook: Planveyor role sessions

**English** · [Русский](owner_runbook_codex.ru.md)

This document is the public operating guide for a Planveyor checkout. It describes the portable lifecycle and leaves credentials, project-specific tests, and local automation to consumer repositories.

## Public launcher

Planveyor runs through a child-only facade. Do not source implementation shell files into a parent shell.

Before the first public command, check for an available `git`, a physical Planveyor Git checkout, and a `HEAD` that resolves to a commit. The facade runs this preflight before `--project` and before doctor; `planveyor_entry_doctor` cannot recover or bypass a failed Git runtime.

From the physical Planveyor root, start with:

```zsh
./bin/planveyor planveyor_entry_doctor
./bin/planveyor planveyor_runtime_info
./bin/planveyor planveyor_help
```

This is a local runtime/project readback, not launch readiness: it does not prove authentication, provider availability, plan admissibility, a SID, Manager dispatch, or a role launch.

The facade finds its root from `bin/planveyor`. A Planveyor-compatible Python 3.10–3.12 executable is needed to load the source identity. A configured agent harness and its usual external authentication are needed by a live command that invokes that harness; Codex and Codex authentication apply only to Codex paths. Doctor, runtime info, and help do not check them. Before role or validation work, choose a compatible Python 3.10–3.12 through a trusted launch environment; the facade and helpers use it, and a project-local `.planveyor.pybin` does not select the executable. `bin/planveyor` starts the child through `env -i` and `zsh -df`, so an inherited `CODEX_HOME` and the variables of another tooling environment are not passed on. `PLANVEYOR_CODEX_HOME` is allowed only when the operator explicitly sets a canonical external path outside the product tree; `HOME`, authentication, client state, and `PLANVEYOR_STATE_ROOT` stay external.

In the selected project root, the ignored selectors `.planveyor.planpath` and `.planveyor.session.*`, the collab records `.planveyor.collab.*`, the init receipts `.planveyor.init_runs/`, and the temporary `.tmp/` remain local process artifacts. They are not credentials or an external client home, but you must preserve them separately when you move or rewrite the project history.

## Choose the project and work explicitly

A call without `--project` works on Planveyor itself. For a consumer project, pass `--project` before the public command and use an absolute canonical directory:

```zsh
./bin/planveyor --project /absolute/path/to/consumer \
  planveyor_plan_status_oracle --json docs/plans/YYYYMMDD_HHMM_topic.md
./bin/planveyor --project /absolute/path/to/consumer \
  planveyor_plan_set docs/plans/YYYYMMDD_HHMM_topic.md
./bin/planveyor --project /absolute/path/to/consumer \
  planveyor_planpath
```

The facade changes the directory only for a clean child process and sets the project root only for that call. Relative paths resolve inside the selected project; the parent shell does not change, and each new call needs the `--project` prefix again. For Planveyor maintenance, you can use the form without the prefix: the external client `HOME`/authentication/state and an explicitly set `PLANVEYOR_CODEX_HOME` stay outside the product tree, while the ignored selectors, collab records, and receipts belong to the selected project root.

A Planveyor run has one active target and, for planning work, one explicit plan path. Do not infer the plan from a filename, a previous session, or a mention in prose. First make sure that the existing exact path passes Oracle, then save the pointer. `planveyor_planpath` proves only a local selection: when the pointer is missing, it suggests `planveyor_plan_set <PLAN_PATH>`, but the pointer by itself does not prove readiness or lifecycle admission. A green static check, a historical receipt, or a finished role session does not by itself prove that the current bytes pass the next lifecycle gate.

Before you change a consumer target, read its contribution instructions and prerequisites. Target tests run from the target checkout; Planveyor does not replace them.

## Preparing your own project

For a new consumer project, first create or choose its checkout with the project's own tools. In its documentation, record the contribution instructions, runtime bootstrap, service prerequisites, test/validation commands, and credential ownership. Then choose a Planveyor-compatible Python 3.10–3.12 in the trusted launch environment before role or validation work. Pass the absolute project path through `--project` before the public command; the launch environment selects Python, not a sibling file.

## Adapting to the consumer stack

Planveyor keeps the lifecycle, evidence, and handoff discipline, while the consumer repository defines the language, framework, local services, migrations, and target-specific checks. Before execution, record these prerequisites in the consumer plan or documentation, make sure that the trusted launch environment provides a compatible Python 3.10–3.12, and run target validation from the consumer checkout. Do not move target-local configuration or credentials into the Planveyor product tree.

## Role and Manager modes

Planveyor supports individual role sessions and Manager-led collaboration. `planveyor_help` shows the concrete command set of the installed version.

```zsh
./bin/planveyor planveyor_manager_init
./bin/planveyor planveyor_manager_collab_tui
./bin/planveyor planveyor_manager_custom_pipeline_tui --no-alt-screen
./bin/planveyor planveyor_manager_resume
```

Before the normal TUI, prepare a supported interpreter, a successful Oracle check of the existing plan, the pointer, and the Manager SID, in this order. When the SID is missing, recovery points to `planveyor_manager_init`. `planveyor_manager_collab_tui` without `--q` is the live single-plan path: after successful gates it passes `MANAGER_CMD=run`; the actual dispatch remains a conditional result. `planveyor_manager_collab_cmd run <PLAN_PATH>` is an alternative one-shot live path, not the next required step after the TUI.

The queue is a separate advanced branch: after `planveyor_q_set <PLAN_PATH> --for-manager-mode manager-collab`, use an explicit queue entrypoint:

```zsh
./bin/planveyor planveyor_manager_collab_tui --q
# or
./bin/planveyor planveyor_manager_collab_cmd run Q
./bin/planveyor planveyor_manager_custom_pipeline_cmd run Q
```

Do not create a `--queue` alias.

The custom pipeline needs separate SIDs for Manager, Architect, Planner, Coder, `reviewer_code_risk`, and `reviewer_code_contracts`: `planveyor_manager_init`, `planveyor_arch_init`, `planveyor_planner_init`, `planveyor_coder_init`, `planveyor_reviewer_code_risk_init`, `planveyor_reviewer_code_contracts_init`. The generic `planveyor_reviewer_init` does not replace the specialized reviewer lanes. The custom TUI is a live supervision/dispatch path and does not prove that every role starts.

To resume an individual role, use the role-specific `*_resume` command from `planveyor_help`. The TUI and the one-shot `*_cmd` are two public entries into the selected mode; do not reproduce the pipeline algorithm in an ad-hoc shell chain.

The direct ZCode Manager route is described in `docs/tools/prompts/zcode/manager_pipeline.md`. It is a transport overlay: it keeps the Custom, native/collab, resume, TUI, and command entrypoints and does not replace them.

The usual role cycle:

1. Choose the project and an explicit plan.
2. Initialize the role or Manager session named in help.
3. Give the role only a bounded task, current evidence, and the expected artifact.
4. Read the artifact and route its declared status to the next allowed role or gate.
5. Create a new receipt if the plan, the target revision, or the intended scope changed.

Owner chooses the operating mode and any runner available to the installed runtime. Manager may coordinate the selected roles, but it does not silently change the Owner-controlled runner, authentication source, project, or plan.

## Init-run artifacts

For diagnostics, the init runtime keeps local state in the selected checkout. `.planveyor.init_runs/by_sid/<SID>/` holds `run.log` and `meta.json` after the session is bound, and `.planveyor.init_runs/pending/<role>/<run_id>/` keeps the same files for an attempt made before the SID is bound. `.planveyor.session.<role>` is only an attach pointer; it does not prove that the init or role run finished successfully.

This init capture does not cover `resume`, live `tee`, split `stdout/stderr`, or interactive TTY adoption. They need separate current evidence and the applicable lifecycle gate.

## Bounded handoffs

Every handoff must name:

- the plan path and project root;
- the exact files or revision range under review;
- the expected output artifact;
- the gate that chooses the next step; and
- one allowed next owner if the gate passes or blocks.

After material changes, read a fresh status readback. A role's prose summary is useful as context, but the plan, review, validation output, and packet metadata remain the durable handoff records.

## Plan, review, and closeout lifecycle

Planveyor keeps a plan-first lifecycle:

1. Architect or Planner creates a bounded plan from the repository templates.
2. The plan is linted, and its status is checked before execution.
3. Coder changes only the authorized target scope and reports validation.
4. Reviewer assesses the current range and writes findings or acceptance evidence.
5. Required CENSOR or follow-up work is closed by an explicit plan or an accepted exception.
6. After merge, the target's post-merge checks run, and fresh documentation, follow-up, and packet records are created if they are needed.

For an executable plan, check the exact bundle before the final handoff if the installed runtime provides this gate:

```zsh
./bin/planveyor --project /absolute/path/to/consumer \
  planveyor_plan_bundle --preflight docs/plans/YYYYMMDD_HHMM_topic.md
./bin/planveyor --project /absolute/path/to/consumer \
  planveyor_plan_bundle --scope-check docs/plans/YYYYMMDD_HHMM_topic.md
./bin/planveyor --project /absolute/path/to/consumer \
  planveyor_plan_bundle --check docs/plans/YYYYMMDD_HHMM_topic.md
```

The first executable Planner handoff requires strict `--preflight`. Reviewer uses `--scope-check` before the diff; genuine Planner refinement with a materialized live review uses it only for inventory and integrity alongside every existing contract, lint, machine-authority and handoff gate. Semantic lint, the derived handoff digest, same-contract skip-Planner and fingerprint status windows stay unchanged. `--scope-check` emits one `planveyor_plan_bundle_scope.v1` JSON document; rc0 means only `scope_ok=true`, and ordinary scope failure returns rc1. Planned absence and red/stale output remain completion debt, and `not_selected` is unvalidated. Scope grants no route, green verdict or commit permission. Final lint and strict `--check` still evaluate the completed review.

## Queue discipline

The Manager queue is an explicit ordered list of plan paths. Materialize or inspect it through the installed queue commands before you ask Manager to run it. Do not call a bare queue sentinel, do not use an old queue after the plan changes, and do not treat a scratch file as queue truth.

If a queued plan blocks, stop at the named gate. Fix or replace the plan, check the new artifact, then update the queue deliberately.

## Review ranges and post-merge work

Review and post-merge evidence must name the exact range or revision they cover. Record the base and head before you create a review or packet. Repeat the applicable checks if the range changed.

Post-merge work usually includes:

- target tests and the required documentation lint;
- review/follow-up triage with a concrete owner;
- process-improvement promotion only when its evidence is current; and
- packetization if the work must move between repositories.

The repository templates in `docs/reviews/`, `docs/followups/`, and `docs/process_improvements/` define the durable carrier formats. Generated summaries are derived views; rebuild them from the current source artifacts instead of editing timestamps or historical rows by hand.

## Rollout packets

A rollout packet carries scoped work from a source repository to a target repository. It is not a profile, a credential, or a remote-execution mechanism.

Create a packet only when the source repository, the target repository, and the relevant plan are known. Keep the source and target roles apart: the source publishes the adoption request, and the target records its own local adoption evidence and outcome.

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

Use `planveyor_rollout_packet_inbox`, `planveyor_rollout_packet_adoption_plan`, `planveyor_rollout_packet_query`, `planveyor_rollout_packet_reconcile`, and `planveyor_rollout_packet_lint` to inspect the current carrier state. Keep packet paths source-local and use generic `<target-repo>` identifiers in templates.

For upstream requests, use the installed `planveyor_upstream_request_show`, `planveyor_upstream_request_import`, `planveyor_upstream_request_ack`, and `planveyor_upstream_request_query`. ACK records a receipt and does not claim that the target merged or accepted the change.

The report/reuse gate reads the exact range without changing the packet:

```zsh
./bin/planveyor planveyor_post_merge_packetization_gate --range BASE..HEAD
```

To recover or restamp a specific source-local packet, name it explicitly:

```zsh
./bin/planveyor planveyor_post_merge_packetization_gate_recover \
  --range BASE..HEAD --packet docs/rollout_packets/<packet>.md \
  --source-plan docs/plans/<source>.md --stage-packets
```

`--range` is required for recovery. `--source-plan` is optional provenance, and recovery accepts a repeated `--packet`. The gate without a named packet is the report/reuse path; it is not a packet update.

## Target-local boundaries

Planveyor carries the public `default` and `planveyor` source profiles. A `target-local` profile, a target-specific role prompt, an integration credential, or a project policy belongs to the consumer repository. If they are missing or unreadable there, stop with a clear blocker instead of creating a local substitute.

This boundary also applies to authentication, local shell configuration, editor setup, browsers, database access, and external services. Keep them outside the Planveyor product tree and document them in the consumer repository when target work needs them.

## Troubleshooting

1. Run `planveyor_entry_doctor` and `planveyor_runtime_info` from the Planveyor root.
2. Read `planveyor_help` for the installed command contract.
3. Check that the selected project, plan path, review range, and packet path are explicit.
4. Repeat the smallest read-only status, lint, or Oracle command that explains the blocker.
5. Fix only the named prerequisite, then create a fresh receipt before you continue.

Do not resolve a runtime or authorization blocker by copying credentials, sourcing implementation files, changing target-local configuration from the product tree, or repeating a role with a different hidden context.

## Related guides

- `docs/guides/launch-and-role-modes.md` explains the public launcher and role modes.
- `docs/guides/lifecycle-and-packets.md` covers the plan, review, closeout, and packet lifecycle.
- `docs/guides/golden_paths.md` links common post-merge routes.
- `docs/roles/` defines role responsibilities and handoff boundaries.
- `docs/playbooks/` holds detailed process playbooks and templates.

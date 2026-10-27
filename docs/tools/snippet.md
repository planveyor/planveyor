# Planveyor snippets

**English** · [Русский](snippet.ru.md)

This page holds short public recipes for lifecycle, evidence, and
documentation search. Recipes for an application-specific framework, database,
worker, UI protocol, deployment, or credentials belong to the selected consumer.

## Public entry

Run Planveyor from the physical Planveyor root:

~~~bash
./bin/planveyor <planveyor_function> [args…]
~~~

Before the first public command, check for an available `git`, a physical Planveyor Git checkout, and a `HEAD` that resolves to a commit. The facade does this before `--project` and before doctor.

For a consumer project, pass it explicitly:

~~~bash
./bin/planveyor --project /absolute/path/to/consumer <planveyor_function> [args…]
~~~

Do not source an implementation shell file. The facade leaves the parent
shell's cwd and environment unchanged; command-defined file and state changes
can persist after the child exits.

## Quick diagnostics

~~~bash
./bin/planveyor planveyor_entry_doctor
./bin/planveyor planveyor_runtime_info
./bin/planveyor planveyor_verify --format json
~~~

Doctor and readbacks prove only what the current call observed. They do not
prove semantic acceptance, provider availability, plan admissibility, a SID, or
dispatch. The cached plan pointer is only a local selection; when it is missing,
`planveyor_planpath` suggests `planveyor_plan_set <PLAN_PATH>` but does not
confirm readiness. The full first-hour route, the normal TUI without `--q`, and
the separate queue are described in `docs/guides/launch-and-role-modes.md`.

## Plan and exact bundle

~~~bash
./bin/planveyor planveyor_plan_status_oracle docs/plans/<plan>.md --json
./bin/planveyor planveyor_plan_bundle --preflight docs/plans/<plan>.md
./bin/planveyor planveyor_plan_bundle --check docs/plans/<plan>.md
~~~

Use the exact plan path. The cached plan pointer, chat prose, and an old receipt
are not routing truth. Before the final transition, the role owner saves current
evidence in the plan or review artifact; Manager does not replace this step.

## Range and review

~~~bash
./bin/planveyor planveyor_merge_range_stats_json BASE HEAD
./bin/planveyor planveyor_review_range_init BASE HEAD
git diff --check BASE..HEAD
rg -n "^<<<<<<< |^======= |^>>>>>>> " .
~~~

Choose a target-local harness only from the plan or canon. For UI work, the
scenario, preconditions, comparator, human verdict, and assets must be declared
current target facts. If there is no lane, use `N/A` with a reason.

## Documentation search

~~~bash
rg -n "<anchor-token>" docs
./bin/planveyor planveyor_docs_index_build all
./bin/planveyor planveyor_docs_retrieve canon "<anchor-token>"
./bin/planveyor planveyor_docs_context_check --corpus plans --format text
~~~

Keep the query short and use stable domain terms from the current plan or canon.
A search result is discovery, not decision evidence. If retrieval influenced a
decision, add a `Retrieval telemetry receipt` with the current read/open result
or a declared `no-op` reason.

The derived index and logs are local, disposable state. Do not commit them, and
do not put a personal absolute path in an artifact.

## Follow-ups and process improvements

~~~bash
./bin/planveyor planveyor_followups_query ready-candidates --format json
./bin/planveyor planveyor_followups_triage --file docs/followups/<backlog>.md --dry-run
./bin/planveyor planveyor_process_improvements_promote --help
~~~

A backlog row, a promoted dev plan, and a process-improvement row have different
owners. `NO FOLLOWUPS` applies only to the ordinary harvest lane; it does not
close separate process-improvement work and does not authorize deletion.

## Post-merge and docs hygiene

~~~bash
./bin/planveyor planveyor_post_merge_packetization_gate --range BASE..HEAD
./bin/planveyor planveyor_docs_closeout docs/plans/<plan>.md --json
./bin/planveyor planveyor_doc_lint
~~~

If a shared carrier needs delivery, the source owner creates a source-local
rollout packet. The consumer owner accepts the packet locally. Do not replace
this flow with a manual copy or a broad docs sweep.

Historical plans, reviews, and snapshots are not the active canon. Before
cleanup, save durable facts in the canon, an audit, or a follow-up; active docs
must not point to temporary files as the source of truth.

## Packets

~~~bash
# source: physical Planveyor root
./bin/planveyor planveyor_rollout_packet_create <target-repo> <topic-slug> \
  --target-kind consumer_only --queue-after-import no
./bin/planveyor planveyor_rollout_packet_lint --all --json

# consumer: selected target repository
./bin/planveyor --project /absolute/path/to/consumer \
  planveyor_rollout_packet_inbox --target-repo <target-repo> --json
./bin/planveyor --project /absolute/path/to/consumer \
  planveyor_rollout_packet_adoption_plan --target-repo <target-repo> \
  --out docs/plans/<target-adoption>.md
./bin/planveyor --project /absolute/path/to/consumer \
  planveyor_rollout_packet_outcome_set \
  --target-plan docs/plans/<target-adoption>.md --packet-id <id> \
  --packet-path docs/rollout_packets/<packet>.md --outcome <canonical-or-alias>

# source: physical Planveyor root
./bin/planveyor planveyor_rollout_packet_ack \
  --packet docs/rollout_packets/<packet>.md --status imported \
  --target-plan docs/plans/<target-adoption>.md
~~~

A packet carries source evidence and the requested adoption. It does not
authorize a target mutation, queue activation, a commit, or a push. An unknown
writable carrier in the target remains a blocker.

## Security and portability

- Do not write credentials, cookies, tokens, headers, account paths, or provider
  output into docs or receipts; use `<REDACTED>`.
- Use repo-relative paths and `<source-repo>`/`<target-repo>` placeholders; use
  an explicit `/absolute/path/to/consumer` only for documented facade selection.
- Do not replace a target-local command with a generic framework example.
- If evidence is missing, record a blocker instead of fabricated proof.

See also `docs/guides/launch-and-role-modes.md`,
`docs/guides/lifecycle-and-packets.md`, and
`docs/playbooks/portability_substitution_rules.md`.

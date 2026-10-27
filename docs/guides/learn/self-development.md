# How Planveyor changes itself

**English** · [Русский](self-development.ru.md)

Changes to Planveyor go the same way as project tasks: a plan, the roles, a review, Architect acceptance. The remarks of the roles about the process itself are collected into process improvements (PIs), and such plans grow out of them too.

## What changes and where it lives

| Layer | What it sets | Where it lives |
| --- | --- | --- |
| Role definitions | The responsibility and limits of a role | `docs/roles/` |
| Prompts and playbooks | The instruction for a step and the detailed order of work | `docs/tools/prompts/`, `docs/playbooks/` |
| Skills | Help in a chat, for example creating a plan | `skills/` |
| Templates and metadata | The format of task files and machine-readable vocabularies, for example `plan_vocab.json` | `docs/*/_template*`, `docs/_meta/` |
| Commands and wrappers | Session preparation, checks before the launch, and the agent harness call | `bin/planveyor`, `scripts/planveyor.zsh`, `scripts/planveyor/` |
| Helper scripts and tests | Checks and processing of task files | `scripts/*.py`, `scripts/test_*.py` |
| Sibling template | The files that a new project receives | `copier_template/` |

A prompt explains to the model what to do, and a script checks the data and the conditions. So a new rule in a prompt does not become a check by itself. A new check in the code, if it changes the work of a role, needs matching text in the prompt.

Rules for such changes:

- Edit the copy in `copier_template/` together with the source in `docs/`; for skills, the source lies in `skills/` and the copy in `copier_template/.agents/skills/`. The `test_template_copies_match_their_docs_sources_byte_for_byte` test requires a byte-for-byte match.
- Do not edit derived files by hand. When a session is created, `build_role_bundles.py` builds the XML context of the role, `.tmp/role_bundles/<role>.xml`, from the role definitions and prompts, and the PI collector rebuilds the process improvement summaries in `docs/process_improvements/`.
- Shared files know nothing about the stack of a particular project. A sibling writes the product commands, databases, and checks into its own [local sections](sibling-lifecycle.md#local-sections); an engine upgrade carries them over unchanged.

One change usually touches several layers at once. When Manager learned to explicitly continue a started docs closeout cycle (`planveyor_manager_collab_cmd run <plan> --followups-capture-cycle-id <UUID>`), the change touched 12 files: the Manager prompt and its copy in `copier_template/`, the launch guide, the `docs_closeout.py` and `followups_capture.py` scripts, the wrappers in `scripts/planveyor.zsh` and `scripts/planveyor/role_runtime.zsh`, and five test files.

## A change in Planveyor itself

When the engine changes, Planveyor itself serves as the project: without `--project`, the facade selects its root. The documents call this mode Self-Planveyor, and Owner here is the Planveyor maintainer who drives the change. The plan is written from the `docs/plans/_template.md` template and put into `docs/plans/` of Planveyor. The `planveyor sibling` commands work only with a sibling; in the Planveyor root, only their help and `sibling init`, which creates a new project, are available. So the plan is selected and driven with the low-level commands from the [launch guide](../launch-and-role-modes.md):

```zsh
./bin/planveyor planveyor_plan_set docs/plans/YYMMDD_HHMM_topic.md
./bin/planveyor planveyor_manager_init
./bin/planveyor planveyor_manager_resume
./bin/planveyor planveyor_manager_collab_tui
```

`planveyor_manager_init` creates the Manager session without approval requests. So, before the work, Owner types `/permissions` in the empty `planveyor_manager_resume` window, chooses "Ask for approval", and exits. After that, Owner approves in the window the requests of Architect to write to `.git`. Approval applies to a specific call, not to the whole task closeout: when a task was closed in Planveyor itself, the window asked separately about `planveyor_plan_bundle --stage`, `planveyor_plan_closeout_preflight`, their repeated runs, and `git commit`, and Owner answered each time with the one-time "Yes, proceed".

If the commands come from a separate Planveyor checkout, pass `--project <project>` to each of them, as the [launch guide](../launch-and-role-modes.md#roles-and-entry-points) says: without it, the command takes that checkout itself as the project, from whatever directory it is called.

If the plan is in the `Architect initial draft` status, Manager starts with a discussion of the task with Architect; it asks Owner its questions in the TUI window and waits for the answer. The commit policy here is `native_existing` (the [Who makes the commit](review-acceptance.md#who-makes-the-commit) section): in an ordinary development plan, after acceptance Architect commits the exact bundle of the plan itself, and then, if the docs closeout requires it, the documents. `git push` stays with Owner.

![A Planveyor change goes through Architect, Planner, Coder, and Reviewer; the contract notice for siblings is part of the change itself; at the end, the commit and the closeout](assets/self-development-1.svg)

[CONTRIBUTING](../../../CONTRIBUTING.md) describes which checks to run before the review; the routes and the differences between them are in the [Engine tests](engine-tests.md) chapter.

If a new check needs a decision broader than the plan, the work returns to Architect. You must not weaken a check to make it pass. Work outside the plan scope is recorded as a follow-up.

## Process improvements (PIs)

A PI usually appears during the docs closeout (the [Task closeout](closeout.md) chapter). Each of the four roles answers with a `Process improvements` section: a proposal or the line `NO PROCESS IMPROVEMENTS — why: <reason>`, for example with the reason `clean_run`. The role does not edit the shared prompts and playbooks while doing so.

The path of a PI record:

1. Collection. After each role answers, Manager passes the answer to the PI collector `process_improvements_collect.py`. The collector adds a `### PI-NNN` record with the `open` status and the `P?` priority to the `docs/process_improvements/YYMMDD_HHMM_topic__process_improvements_backlog.md` file named after the plan, and rebuilds three summaries: `index.md`, `deferred.md`, and `promotion_surface.md`. Each file has its own PI numbers. An error of the collector stops the closeout, with one exception: after a format error in the `Process improvements` section, the same role may give one corrected answer.

   Automatic general PI format correction permits one additional response from the same role only when the helper proves that the failed collection had no effect and that every uncommitted documentation change belongs to the current PI chain. Changes to ordinary documents outside that chain block correction even when those files are not protected. Another malformed response or re-entry does not replenish the spent attempt; processing stops for an Owner decision.
2. Triage. Architect names the file where the change must land (`target_canon_path`), the repository (`target_repo_scope`), and the delivery mode (`delivery_mode`, see the table below). Owner changes `P?` to `P0`, `P1`, or `P2`: this is the urgency of the record. The change class is already recorded in `promotion_class`: `canon_update` for documents, templates, and playbooks, `prompt_change` for prompts, `helper_change` for scripts and wrappers, `routing_change` for routing and queue changes, and `followup_plan` for creating a follow-up plan. After triage, the record gets the status `triaged`, `deferred` (with a reason and a condition for coming back to it), or `rejected` (with a reason). The `process_improvements_triage.py` script writes the fields.
3. Promotion. `process_improvements_promote.py` links the record to an already existing execution, usually a plan (`execution_kind=plan` and the plan path in `execution_ref`). On success, the record gets the `promoted` status and the `promoted_at` time. The script does not create the plan: if the file does not exist, it refuses, and the record stays `triaged`.
4. Execution. The plan goes the usual way, with a review and acceptance.
5. Reconciliation. `process_improvements_reconcile.py --report` finds the records whose plan is already `Done`; with `--apply`, they get the `handled` status, the `handled_ref` reference, and the `handled_at` time.

| `delivery_mode` | What happens |
| --- | --- |
| `source_only` | The change stays in the current repository |
| `source_plus_rollout` | The change enters the rules of this repository and then travels to the recipient project as a packet |
| `packet_only` | This repository does not change its own rules and prepares only a packet for the receiving project |
| `umbrella_mixed` | The record needs a separate decomposition with an umbrella plan |

Packets are described in the [Exchanging changes with Planveyor](change-packets.md) chapter; for now, a sibling does not receive them ([F29](../../release_backlog.md#f29), in Russian).

Roles do not call the triage, promotion, and reconciliation scripts in an ordinary turn: these scripts are run with a separate command. For promotion and reconciliation, there are the facade commands `planveyor_process_improvements_promote` and `planveyor_process_improvements_reconcile`; for triage, there is the `process_improvements_triage.py` script. The scripts change only the record and the summaries: they do not create a plan, start roles, or enable the queue. Architect records the decisions on mature records at the `plan_harvest` step of the [post-merge check](postmerge.md), in the `Process-improvement promotion decisions` section. Records in `open`, `triaged`, and `promoted` are work that is not done yet; reconciliation sets `handled`.

The second source of records is an upstream request from a sibling. The `planveyor_upstream_request_import` command turns it into the same kind of `open` record, and the same triage follows (see [Exchanging changes with Planveyor](change-packets.md)). The record format and the rules are collected in the [description of process improvements](../../process_improvements/README.md) (in Russian).

Planveyor itself has three of its own PIs waiting for triage: `PI-001`, `PI-002`, and `PI-003` in `docs/process_improvements/release__process_improvements_backlog.md`, all `open` with `P?`. The [First-release backlog](../../release_backlog.md) calls them PI1–PI3.

## Example: the PI-001 record in the SQL project

In the SQL project, the PI-001 record appeared during the docs closeout of the GetReorderCandidates task (the [Task closeout](closeout.md#how-it-went-the-getreordercandidates-documents) chapter). Architect made the proposal, Planner answered `clean_run`, and Coder and Reviewer answered `already_tracked` because the proposal was already recorded. The number PI-001 belongs to the PI file of the project and is not related to the PIs of Planveyor itself. The triage fields, which that chapter hides behind “[…]”, are all empty:

```markdown
- target_canon_path: `null`
- target_repo_scope: `null`
- delivery_mode: `null`
- execution_kind: `null`
- execution_ref: `null`
- delivery_refs: `null`
- handled_ref: `null`
- promoted_at: `null`
- handled_at: `null`
```

The reference to the report of the previous task is in a [local section](sibling-lifecycle.md#local-sections) of the review playbook, so triage would assign the `source_only` delivery, and an ordinary plan in the project itself would carry out the change. An error in the shared part is fixed through an upstream request (the [Exchanging changes with Planveyor](change-packets.md) chapter).

At the latest project commit, `f4f707b`, the PI-001 record is still `open` with `P?`. The project history has no triage, no execution plan, and no `handled` status, and the local section still refers to the report of the previous task.

## How a change reaches the sibling

If a change touches the shared contract or mechanics, the same change includes a contract notice (the format is in the [Exchanging changes with Planveyor](change-packets.md#contract-notice-what-a-new-version-brings) chapter). An example from the development history is the notice about a change of three CENSOR prompts: its `engine_changes` is empty, and its `sibling_actions` asks to read the new prompts and to keep the local sections. The change reaches the project through an upgrade: Owner updates the Planveyor checkout and runs `planveyor sibling upgrade`, and the roles run the upgrade plan. How this works and how it went in the SQL project is told in the [Sibling: creation and upgrade](sibling-lifecycle.md#upgrading-to-a-new-planveyor-version) chapter. The SQL project was upgraded before the `sibling upgrade` command existed, with the low-level `planveyor_contract_upgrade` command.

## Common mistakes and what catches them

| Mistake | What catches it |
| --- | --- |
| Editing a prompt, playbook, or skill and forgetting the copy in `copier_template/` | The `test_template_copies_match_their_docs_sources_byte_for_byte` test |
| Losing a required phrase in a prompt or bringing back a forbidden one | Tests of the prompt text, for example in `scripts/test_censor_prompt_contract.py` and `scripts/test_planveyor_codex_agent_roles.py` |
| Commenting out the documentation linter (doc lint) call in `scripts/planveyor.zsh` or moving it to another function | The profile contract check `check_planveyor_profile_contract.py`, finding `doc_lint_gate` |
| Editing a shared prompt or playbook during the docs closeout | `planveyor_docs_closeout` sets the reason `canon_delta_requires_process_improvement`, and the closeout does not commit such an edit. Architect records it as a PI or moves it to a separate active plan; the closeout continues once its set of files has no protected edit left |
| Promoting a PI record to a plan that does not exist | `process_improvements_promote.py` refuses, and the record stays `triaged` |
| Writing a contract notice with a missing field, a field of the wrong type, or an empty or multi-line string | The `test_current_notice_history_and_strict_notice_are_valid` test in the full route; in a sibling, the upgrade stops before the candidate |
| Changing the shared contract without a contract notice | The check item before the closeout in [docs_architecture.md](../../playbooks/docs_architecture.md) (in Russian); without a notice, the upgrade plan in a sibling gets neither actions nor checks |

The functions and tests discussed here are in the [code map](code-map.md#how-planveyor-changes-itself).

Next: [Post-merge check](postmerge.md).

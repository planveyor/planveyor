# Roles and task files

**English** · [Русский](roles-artifacts.ru.md)

Planveyor splits a task between participants with different responsibilities. Each one does its step and writes the result into a file, and the next one takes the work from that file: there is no need to read the conversation. Below, everything is shown on a real task from an SQL project.

## Who is responsible for what

Owner is a person, the owner of the project. Architect, Planner, Coder, Reviewer, and Manager are agent harness sessions, Codex by default. A role is not tied to a specific model: the [Codex setup](../launch-and-role-modes.md#codex-setup) sets the model and the reasoning effort for each role, and the agent harness is chosen separately.

| Participant | What it is responsible for | What it passes on | What it does not do |
| --- | --- | --- | --- |
| Owner | The goal of the task and the decisions that only a person makes | The goal, answers to questions, permissions to commit | — |
| Architect | What to do, within what limits, and how to accept the result | The plan with the decisions; at the end, the acceptance verdict | Does not write product code |
| Planner | The exact list of files, steps, and checks | The code draft | Does not implement changes |
| Coder | Code and tests by the draft | The changed files and the check results | Does not silently expand the task |
| Reviewer | Risks and whether the result matches the plan | The review | Does not fix code instead of Coder |
| Manager | Which role to launch by the plan status | The turn of the next role | Does not edit the plan, the answers, or the code |

Nobody makes up answers for Owner. If Planner, Coder, or Reviewer has a question about the meaning of the task, they return it to Architect. Architect answers itself or formulates a question for Owner. More about the authority of the roles is in the [role definitions](../../roles/index.md) (in Russian).

![Owner gives the goal to Architect, then the work goes through Planner, Coder, and Reviewer and returns to Architect for acceptance](assets/roles-artifacts-1.svg)

The diagram shows the usual path without returns. A question or a finding can return the work to the role that owns the file: a gap in the steps to Planner, an implementation error to Coder, a question about meaning to Architect. The full order of returns is described in the [Manager rules](../../roles/manager.md).

## Task files

| File | What it contains | Who writes it |
| --- | --- | --- |
| Plan, `docs/plans/YYMMDD_HHMM_<topic>.md` | The goal, the decisions, the scope (`## Scope`), the acceptance criteria, the questions and answers, the status, the evidence log (`## Evidence`) | Architect; each next role adds its part |
| Code draft, `docs/code_drafts/<plan name>__code_draft.md` | The list of target files (`code_draft_meta.targets`) and the steps for Coder | Planner |
| Review, `docs/code_reviews/<plan name>.md` | The conclusions of the two Reviewer lanes and the verdict of Architect | Reviewer, then Architect |
| Follow-ups, `docs/followups/` | Work that was decided to be done later; each record has its own owner | The roles propose records at the docs closeout; the `followups_apply.py` script writes them |

The status in the plan header (`**Status:**`) shows which role is working now. The Oracle script reads the status together with the task files and reports the state of the plan and what blocks the transition, and Manager chooses the next role by this answer; more about it is in the [chapter about the plan](plan-lifecycle.md). Templates: [plan](../../plans/_template.md) (in Russian), [code draft](../../code_drafts/_template.md) (in Russian). During the task, deferred work is noted in the `## Follow-ups (deferred)` section of the plan, and at the docs closeout it becomes separate `followups.v2` records. The generated index helps to find them, but no decisions are made in it.

## How it went: the GetReorderCandidates task

On September 28, 2026, the roles solved this task in the SQL project on Planveyor. The `dbo.GetReorderCandidates` procedure must return the active products that are short in stock even when the delivery already on order is counted. The data and tests of the task are in the [running example](sql-example.md); here is who did what.

**Owner** gave the assignment in one paragraph: one read-only procedure, the shortage formula, the rules for `NULL`, the row order, seven test cases. The assignment stated that the run on the dev database is done by the operator, a person or an agent with access to this database; Planveyor has no such role. Owner made the decisions in advance, so there were no formal questions to Owner; Owner gave one clarification while Coder was working.

**Architect** wrote the plan in 7 minutes. At the end of the work, the plan header looked like this:

```markdown
**Plan type:** dev
**Status:** Done
**Schema version:** plan.v2

**Handoff statuses (кто ставит):**
- `Ready for Planner` — Architect
- `Ready for Coder` — Planner
- `Ready for Review` — Coder
- `Ready for Arch review` — Reviewer
- `Done` — Architect
```

Two decisions of Architect stand out in what follows. Table comparison in tSQLt tests ignores the row order, so the order is checked with a separate direct call of the procedure: the products are inserted in the order 30, 10, 20, and the harness (the script that builds the database and runs the tests) requires 10, 20, 30 on output. The second decision is to put into the list of target files also the existing files that the check depends on, even if they are not changed. On its first run, the plan linter found three form defects; Architect fixed them and handed the plan to Planner.

**Planner** wrote the code draft in 5 minutes. The main part of it is the list of target files. There are 16 of them: Coder changes six, and ten are in the list without changes, by the decision of Architect. Here are the six that change:

```json
{"path": "scripts/sql.py", "kind": "py"},
{"path": "scripts/test_sql.py", "kind": "py"},
{"path": "sql/Northwind/GetReorderCandidates.sql", "kind": "sql"},
{"path": "sql/tests/GetReorderCandidatesTests.sql", "kind": "sql"},
{"path": "sql/tests/run-tests.sql", "kind": "sql"},
{"path": "README.md", "kind": "doc"}
```

The unchanged ones are, for example, `Makefile`, `global.json`, and the database schema `sql/Northwind/Northwind.sql`.

For the two new SQL files, Planner created stubs that Coder must replace before review. The preflight of the exact bundle of the plan counted 19 files: 16 targets, the plan, the draft, and the review, which did not exist yet.

**Coder** wrote the procedure and the tests and adjusted the harness. Without a real database, everything passed: 40 of 40 harness tests, the build without errors or warnings, the linter, the secrets check. The run on the dev database was up to the operator, so Coder handed the work to the operator and left the `In progress` status.

**The operator** ran `make db-proof`, and the first run failed after 5 seconds: the harness stopped before publishing, because it could not determine the state of the test classes in the database unambiguously. A check showed that the `SqlHarnessSmoke` class had no tSQLt class marker. The likely cause is the DacFx publish setting `DropExtendedPropertiesNotInSource`, which removes such markers by default. Coder added `/p:DropExtendedPropertiesNotInSource=false` to the publish step, the operator restored the marker, and the second run passed in 13 seconds: 8 of 8 tests, the rows in the order 10, 20, 30. The offline tests did not show this: the marker disappeared in the database itself.

**Reviewer** checked in two lanes. The risk lane looks for errors and dangerous spots, and the contracts lane checks the result against the plan. Neither lane had findings. In the review, Reviewer stated the limits: it did not run SQL itself, and the green run applies to the code before the commit. The final check of the bundle counted 22 files; where the three extra ones came from is shown in the chapter [The plan and its statuses](plan-lifecycle.md#how-it-went-the-getreordercandidates-plan).

**Architect** verified the files and the checksums itself, wrote the acceptance verdict, and at 02:17 made commit `70526ee` with 12 files: the six changed target files, the plan, the draft, the review, and its three assets. The ten unchanged target files did not go into the commit. At 03:05, the second commit `edac1b9` closed the documents. It has one process improvement: the review playbook referred to the JUnit report of the previous task, while it should take the report of the current one (the [Task closeout](closeout.md) chapter).

This was before the `planveyor sibling` commands existed: the operator launched the roles, and Architect made the commit. Now a sibling has two modes. In TUI mode, the main path, Manager drives the task in one window, and Architect commits: Owner approves its requests to write to `.git` in the window. In manual console mode, Owner drives the task with the `planveyor sibling` commands: Architect writes the verdict and stops, and the `planveyor sibling close --commit` command makes the commit after Owner has looked at the bundle. Both modes are described in the [stack sibling guide](../stack-sibling.md#two-ways-to-work-on-a-plan).

## Manager and the handoff check

Manager is the coordinator. It reads the plan status, launches the role whose turn it is, and looks at what that role left. In the task, it does not change the plan, the answers, the code, or the settings, and it makes no commits. In one launch, Manager takes at most 12 steps; if the task is not finished, Manager stops: in manual console mode, the same command is run again, and in TUI mode, Owner tells Manager in the same window to continue.

Before passing the work on, Manager asks the role that hands it over to go through its files once more. This second pass of the same session is called CENSOR. Architect does it before Planner, Planner before Coder, and Coder before Reviewer: the prompts [architect_censor.md](../../tools/prompts/architect_censor.md) (in Russian), [planner_censor.md](../../tools/prompts/planner_censor.md) (in Russian), [coder_censor.md](../../tools/prompts/coder_censor.md) (in Russian).

On the second pass, the role checks whether everything discussed is written into the plan and the draft, and adds what is missing without going beyond its authority. It notes the result in the evidence log. If a question about the meaning of the task comes up, the work returns to Architect. Manager rereads the result of the pass itself and ties it to the number of its own call. The mark is valid only for this handoff: if the plan changes later, it no longer counts. CENSOR does not replace review: it is a self-check before the handoff.

For small edits, the second pass can be skipped (the conditions are in the [Launch: commands, wrappers, agent harnesses](runtime-launch.md#manager-collab) chapter).

In the GetReorderCandidates task, the operator launched the roles, so Manager and CENSOR are not visible in its files. How Manager launches the roles is told in the [launch chapter](runtime-launch.md).

## Role, prompt, and wrapper

Three things define a role:

- **the role definition**: what the role is responsible for and where its limits are: [architect.md](../../roles/architect.md) (in Russian);
- **the phase prompt**: what to do in the current status: [architect_status_driven.md](../../tools/prompts/architect_status_driven.md) (in Russian); for the first discussion of the task, a separate [architect_draft_discussion.md](../../tools/prompts/architect_draft_discussion.md) (in Russian);
- **the wrapper**: the engine function that prepares everything needed and starts the session: `planveyor_arch()`, and for the first discussion, `planveyor_arch_initial()`.

The prompt defines what the role does, and the wrapper defines how it is launched. In a sibling, the role reads a copy of the prompt from the project itself. The shared part of the prompt comes from Planveyor and is updated by `planveyor sibling upgrade` when you have updated your Planveyor checkout. Two [local sections](sibling-lifecycle.md#local-sections), `## Локальные правила стека` (local stack rules) and `## Разрешённое локальное переопределение процесса` (allowed local process override), belong to the project, and the upgrade keeps them.

## Common mistakes

- Looking for product code among the engine scripts. The product and its checks live in the sibling.
- Treating a role as a specific model.
- Taking a role's “done” answer for the result. Look at the changed files and a fresh check.
- Asking Manager to fix the plan. It will return the work to the role that owns the file.
- Referring to the reports of a previous task, as the review playbook did in the example above. Each task has its own reports.

The functions and tests mentioned here are in the [code map](code-map.md#roles-and-task-files).

Next: [Running example: which products to reorder](sql-example.md).

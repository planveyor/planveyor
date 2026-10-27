# What works now and what comes next

**English** · [Русский](capabilities-boundaries.ru.md)

The first version of Planveyor takes a task from the plan to the commit, but it has limits, and part of the further work is recorded for later. This chapter ends part 2: read it before you try Planveyor on your own project, and you will see in advance whether you will run into one of the limits.

![A mechanism is implemented, its behavior is covered by a check, the result is accepted in a task; open commitments are recorded separately](assets/capabilities-boundaries-1.svg)

How to tell a mechanism that merely exists from one checked by a test and from one accepted in a real task is told in the [Tests and evidence: what you can trust](testing-evidence.md) chapter.

## What the first version can do

| Capability | Where to read |
| --- | --- |
| Run a task through the roles: Architect writes the plan, Planner the code draft, Coder implements, two Reviewer lanes check, Architect accepts. Manager starts the roles by the plan status | [Roles and task files](roles-artifacts.md), [The plan and its statuses](plan-lifecycle.md), [Review and acceptance](review-acceptance.md) |
| In a sibling, commit only with Owner's consent: in TUI mode, Architect commits after Owner approves its requests to write to `.git` in the Manager window; in manual console mode, Owner runs `planveyor sibling close --commit` after a preview of the exact bundle of the plan. Then do the docs closeout of the task | [Task closeout](closeout.md) |
| Create a sibling, adapt it to the stack, and upgrade it to a new Planveyor version with an upgrade plan | [Sibling: creation and upgrade](sibling-lifecycle.md) |
| Pass a shared problem to Planveyor with an upstream request through a GitHub issue. The solution comes back with a sibling upgrade, together with a contract notice | [Exchanging changes with Planveyor](change-packets.md) |
| First research a large task or split it into several plans | [Development, analysis, and decomposition](work-contours.md) |
| Check a commit range after a merge; for now, only in Planveyor itself | [Post-merge check](postmerge.md) |
| Change Planveyor itself with the same process | [How Planveyor changes itself](self-development.md) |

On a real SQL project, the sibling creation, the adaptation to SQL Server, the `GetReorderCandidates` task, and the upgrade to the next Planveyor version were carried out on September 27 and 28, 2026. The adaptation and the task were closed with separate documents commits, and the upgrade plan got `Done` in a separate commit. All this happened before the `planveyor sibling` commands (see [Roles and task files](roles-artifacts.md)): they appeared on October 3, and the engine tests check them. There is no real task run with these commands among the examples of this section.

## Limits of the first version

F numbers are items of the [First-release backlog](../../release_backlog.md) (in Russian), which also has their full text.

| Area | Limit | Items |
| --- | --- | --- |
| Environment | One environment is supported: macOS and an activated environment with Python 3.12 and the dependencies from `requirements-dev.lock`. The version check at launch lets Python 3.10–3.12 through, but only 3.12 is supported. GitHub CI has not been run yet: the first version was checked locally on macOS | F1, F2, F5, F6 |
| Dependencies and the agent harness | A command names a missing prerequisite but does not install or configure it itself. Owner prepares Codex CLI, the sign-in to it, and the five role agents in `config.toml`; Planveyor does not create or change this file ([Codex setup](../launch-and-role-modes.md#codex-setup)) | — |
| Agent harnesses | TUI mode and `planveyor sibling run` start five role agents in Codex; in TUI mode, they are nested subagents of the Manager session, a capability of Codex CLI. Planner and Reviewer can run in Claude Code where a wrapper starts the role: in a single-role launch or in the Manager custom pipeline; Architect, Coder, and Manager work only in Codex ([Launch: commands, wrappers, agent harnesses](runtime-launch.md)). Manager in ZCode works only in the Planveyor root: its launch files are not delivered to a sibling | F20 about ZCode is closed: this limit is described |
| Manager recovery | It is not decided yet how an interrupted Manager session learns at which step it stopped and continues the work | F7 |
| Deadlock after a Reviewer question | If Reviewer asked Architect a question in the risk lane, the contracts lane does not start. The risk lane cannot change the status, so nobody can set `Ready for Architect response`, and Manager stops with `stop_class=semantic_blocker`. Then Owner sets this status in the plan header themselves: this is a known exception to the rule not to edit the status by hand | F49 |
| Plan queue | The engine has a queue of related plans, but it has no end-to-end check, and the work on it is deferred until after the first publication. `planveyor sibling run` drives one selected plan and does not create a queue. For an interrupted queue operation, there is only the explicit recovery `planveyor_q_recover`, and Owner makes the decision about it | A deferral without a number; F23 is closed: only the explicit recovery was added |
| Contract notices | A sibling upgrade checks how a contract notice is formatted but does not require one. It is not defined when a notice is mandatory, and nothing now stops a change of the sibling template or the working scripts without a notice | F27 |
| Post-merge check in a sibling | There is no `planveyor sibling …` command for it. The low-level commands need two settings files in `docs/_meta/`; the sibling template does not create them, and without them the commands stop ([Post-merge check](postmerge.md)) | Not in the backlog |
| Rollout | A sibling does not receive rollout packets (`planveyor_rollout_packet_*`): changes reach it through an upgrade with a contract notice. It is not decided yet whether to remove the mechanism or keep it only for Planveyor itself | F29 |
| Stack neutrality | Some engine rules were written for a web project on Django. When Reviewer checks a commit range, the changes of an SQL project in `db/`, `src/`, and `tests/` go to the list of helper files instead of product code. The interface check method requires web terms | F43, F45 |

If a limit gets in the way of your project, describe the problem in an upstream request: the steps are in the [Propose a change to Planveyor](../stack-sibling.md#propose-a-change-to-planveyor) section of the stack sibling guide.

## Where development is heading

In the First-release backlog, 15 items are closed and 37 are open, and there are three separate process improvements, PI1–PI3. Of the items F5–F52, the 33 open ones are deferred until after the release of the first version; F1–F4 remain separate open commitments. The further work has no deadlines.

| Direction | What lies ahead | Items |
| --- | --- | --- |
| Reliability | Recover an interrupted Manager session: in one of the sibling runs on SQL Server, after a model overload, a reset of one role cost about 0.8 million tokens. Check write access to `.git` before a commit is first prepared: now this only comes out after the review. Remove the manual steps of Owner: the status in the deadlock after a Reviewer question, and the closing of the stack brief questions, which Owner now closes themselves | F7, F40, F49, F50 |
| Environments | Check Windows, then Linux; other Python versions; start GitHub CI | F1, F2, F5, F6 |
| Sibling upgrade | A jump over a version, the transfer of a renamed file that comes from Planveyor, two engine versions at the same time when its API changes, a doctor that shows how far a sibling lags behind the engine. A successful upgrade on one transition does not check these cases. A rule and a check for contract notices. An analysis of the upgrade by the roles instead of a list of changed paths | F8, F27, F30, F32 |
| Exchange with Planveyor | A pull request straight from a sibling; commands for upstream requests from a sibling; a decision about rollout | F26, F28, F29 |
| Large tasks | An analysis of a large task in which Coder writes the results to a separate file right away; decomposition refinements; tests of analysis and decomposition, including an end-to-end run with a fake Codex. The end-to-end check of the plan queue is deferred separately, without a number | F33, F34, F35 |
| Speed and resource use | Measurements first. After them, a cache of the checks that now repeat in every command, parallel steps of the post-merge check, and a faster `bin/planveyor`: a call now takes about 8 seconds | F3, F9, F10, F39 |

To take an item into work, you create an ordinary plan from the templates: with high uncertainty, research first; for a broad solution, a decomposition; for a bounded edit, a development plan ([Development, analysis, and decomposition](work-contours.md)).

## Common mistakes

- Treating a backlog item as a promised deadline.
- Treating a closed item as closed in full. Closed items state what exactly is closed: for example, F23 added the explicit recovery of a queue operation but did not give an end-to-end check of the queue.

## How to maintain this documentation

This chapter briefly retells the [First-release backlog](../../release_backlog.md) and may fall behind it; if they differ, the backlog is right. Add a new capability to the chapter when it has fresh evidence: a check or an accepted task. When you change a role, a command, or a wrapper, also fix the chapter of this section that describes them. Before the review of an edit, run the checks from [Documentation architecture](../../playbooks/docs_architecture.md) (in Russian) and [CONTRIBUTING](../../../CONTRIBUTING.md): the documentation linter and the search for private paths and stale results of earlier runs.

The functions and tests discussed here are in the [code map](code-map.md#what-works-now-and-what-comes-next).

Next: [Launch: commands, wrappers, agent harnesses](runtime-launch.md).

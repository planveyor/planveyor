# Planveyor mechanics: process map

**English** · [Русский](mechanics.ru.md)

Here, a mechanic is a process rule with an explicit carrier: a document, a role instruction, or a script. Below is the list of the mechanisms of the first version, grouped by their role in the process. The chapter describes how they are built, based on the Planveyor code and documents. A description of a mechanism does not yet prove that it was used: what the published history shows of this is collected in one cross-section at the end of the chapter.

The task status is recorded in the plan header. Oracle checks status, route, and review freshness. Manager starts the needed role by this state; receipt and closeout gates authorize progress. The results of the work stay in the task files.

Planveyor is derived from a private industrial AI delivery stack.

## How the mechanics work together

![A task goes through the plan, the work, the review, and the commit, then the docs closeout with records of process improvements and follow-ups. Separately come the triage of the proposals, a fix plan, and the post-merge check with the docs sweep and the archive; the next tasks get the rules and documents from them](assets/mechanics-1.svg)

The solid arrow is the usual path of a task up to the docs closeout with records of process improvements and follow-ups. Dashed arrows are steps that are started separately: this part of the feedback is not yet confirmed in full in the published Planveyor history.

**Task path.** Architect writes the plan and the `## Как я понял задачу` section (how I understood the task), and Owner answers the questions. Planner lists the target files, and Coder changes them. At the matching handoffs, Manager runs the second pass of the role or checks the conditions of an explicitly chosen short route. The two Reviewer lanes check the target snapshot, and Architect accepts the work or returns it to the role that owns the fix. Only the exact bundle of the plan goes into the commit. After the commit, the roles do the docs closeout and record process improvements and follow-ups.

**How the work is handed on.** The status in the plan header hands on the turn: `Architect draft` → `Ready for Planner` → `Ready for Coder` → `Ready for Review` → `Ready for Arch review` → `Done`. A `Ready for …` status gives the work to the next role, and a return is recorded with the status of the role that owns the fix. All statuses and who sets them are in [The plan and its statuses](plan-lifecycle.md#statuses-and-who-sets-them).

**Path of a change to the projects.** The task commit is local; Owner does `git push`. A change to Planveyor itself is published in its GitHub repository, where the `Planveyor checks` workflow checks it. A project on its own stack gets the change when it runs `planveyor sibling upgrade` itself: the upgrade prepares a candidate and keeps the local sections, and the project roles run the upgrade plan. If the change touches the shared contract, a contract notice may come with it: what changed and what the project should do (mechanics 29 and 30). How this went for two tasks of Planveyor itself is shown in the [examples](#examples-two-planveyor-tasks) at the end of the chapter.

**Process change path.** The process improvement loop includes collecting observations, a separate triage, a fix plan, a review, and acceptance of the result. A proposal record does not change the rules: Owner sets the priority, and the change goes through a separate plan with a review and acceptance. The post-merge check (with the document sweep and the archive) and doc gardening are started separately and are not part of the route of every task.

The mechanics are linked through the task files:

- the code draft defines the target files;
- the snapshot ties the review to the bytes of these files: an edit of a target file after the review makes the snapshot stale and stops a closeout based on the earlier review;
- the exact bundle limits the commit: a file outside the bundle does not get into the standard task commit;
- the docs closeout keeps the results of the task and the records for later;
- a separate decision turns a record into a task.

The Golden paths registry, documentation search, and the archive do different jobs. The registry points to the standard entry point, the search finds the needed current document, and the archive keeps the history: why something was once decided exactly this way. The archive itself does not become a role instruction.

## Mechanics map

| Group | What it provides | Mechanics |
| --- | --- | --- |
| A. Understand the task and prepare the work | The scope, the Owner decisions, and the work plan are recorded before the roles start changing files | [1](#1-the-task-plan), [2](#2-qa-and-evidence-logs), [3](#3-task-intake), [4](#4-code-draft), [5](#5-three-work-contours) |
| B. Launch the roles and check the handoff | Each role is launched by the recorded state, and the next role checks its result | [6](#6-roles-with-separate-responsibilities)–[13](#13-stop-instead-of-guessing) |
| C. Keep changes within bounds | A check applies to specific bytes, and a commit to a declared set of files | [14](#14-evidence-is-tied-to-a-version-of-the-files)–[17](#17-range-check-before-the-merge) |
| D. Preserve the task results | Decisions, observations about the process, and work for later are not lost after the commit | [18](#18-docs-closeout)–[21](#21-follow-ups) |
| E. Check the overall picture and maintain the documents | Merged tasks are checked together, the documents stay short, and past decisions can be found | [22](#22-post-merge-check)–[26](#26-documentation-search-for-the-roles) |
| F. Separate the project from the engine and accept changes | The project owns its stack and its rules and decides itself when to take a new version | [27](#27-sibling-a-project-separate-from-the-engine)–[30](#30-upgrade-with-a-contract-notice) |

## Full list

| No. | Mechanic | What it provides | How it comes into play |
| --- | --- | --- | --- |
| 1 | [The task plan](#1-the-task-plan) | One coordinating file: the scope, the status in the header, the role sections | a step of the task route |
| 2 | [Q&A and evidence logs](#2-qa-and-evidence-logs) | Questions with Owner answers and checks with their results stay in the plan | a step of the task route |
| 3 | [Task intake](#3-task-intake) | Architect restates the task and asks questions before Planner starts work | a step of the task route |
| 4 | [Code draft](#4-code-draft) | Target files, steps, and checks for Coder | a step of the development task route |
| 5 | [Three work contours](#5-three-work-contours) | Development, analysis, or decomposition of a large goal into several plans | the contour is chosen by the task |
| 6 | [Roles with separate responsibilities](#6-roles-with-separate-responsibilities) | Some roles write, others check and accept | a step of the task route |
| 7 | [Manager](#7-manager) | Starts the roles by the plan status; does not edit the plan, the answers, or the code | a step of the task route |
| 8 | [Oracle](#8-oracle) | Oracle checks status, route, and review freshness | on every Manager turn |
| 9 | [Role launch](#9-role-launch) | The facade and the wrappers prepare the role input and start the agent harness | any command |
| 10 | [The role's second pass (CENSOR)](#10-the-roles-second-pass-censor) | The role checks its own work with a separate prompt before passing it on | at certain handoffs of Architect, Planner, and Coder |
| 11 | [Two Reviewer lanes and Architect acceptance](#11-two-reviewer-lanes-and-architect-acceptance) | The risk lane and the contracts lane, then the verdict of Architect | a step of the task route |
| 12 | [Return to the responsible role](#12-return-to-the-responsible-role) | The work goes back to the role that owns the fix | when a gap is found |
| 13 | [Stop instead of guessing](#13-stop-instead-of-guessing) | Anything unclear goes to Owner as a question; one Manager launch has a step limit | when something is unclear and at the step limit |
| 14 | [Evidence is tied to a version of the files](#14-evidence-is-tied-to-a-version-of-the-files) | The review is tied to the target snapshot and goes stale after the target files are edited | a step of the task route |
| 15 | [The exact bundle of the plan](#15-the-exact-bundle-of-the-plan) | Only the files declared in the plan go into the commit | a step of the task route |
| 16 | [Commit with Owner's consent](#16-commit-with-owners-consent) | The commit follows the commit policy; `git push` is an Owner step | Owner permission |
| 17 | [Range check before the merge](#17-range-check-before-the-merge) | Path rules, change size, tech debt, and a secrets search when a scanner is available | a separate command |
| 18 | [Docs closeout](#18-docs-closeout) | The roles carry the results of the task over into the shared project documents | a step after the task commit |
| 19 | [Architecture decision records (ADRs)](#19-architecture-decision-records-adrs) | Decisions that will outlive the task are kept apart from the plans | when a decision stops being temporary |
| 20 | [Process improvements (PIs)](#20-process-improvements-pis) | Each role proposes a process change or writes why there is none | collection at the docs closeout, triage separately |
| 21 | [Follow-ups](#21-follow-ups) | Work for later is recorded with a responsible party and a reason | at the docs closeout |
| 22 | [Post-merge check](#22-post-merge-check) | A review of the whole merged range, the plan harvest, an audit | a separate Manager route, in Planveyor itself |
| 23 | [Shared document sweep and doc gardening](#23-shared-document-sweep-and-doc-gardening) | The shared documents are cut down to the essentials and cleared of stale content | the sweep is a post-merge check step; doc gardening follows its playbook |
| 24 | [Golden paths](#24-golden-paths) | Short pointers to the entry points of recurring work | the role consults it itself |
| 25 | [Searchable archive](#25-searchable-archive) | Closed plans, drafts, and reviews are saved to an archive with full-text search | a post-merge check step |
| 26 | [Documentation search for the roles](#26-documentation-search-for-the-roles) | The role finds the needed document by an index instead of reading every document in turn | at the role's choice |
| 27 | [Sibling: a project separate from the engine](#27-sibling-a-project-separate-from-the-engine) | The project owns the code, the plans, and the local rules; the engine owns the process | when the project is created |
| 28 | [Upstream request](#28-upstream-request) | A shared problem of the project is passed to Planveyor | by Owner's decision |
| 29 | [Planveyor changes through the same process](#29-planveyor-changes-through-the-same-process) | Changes to the engine, the prompts, and the checks go through a plan, the roles, and a review | in Planveyor itself |
| 30 | [Upgrade with a contract notice](#30-upgrade-with-a-contract-notice) | The project takes a new Planveyor version itself, and the roles run the upgrade plan | by Owner's command |

## A. Understand the task and prepare the work

### 1. The task plan

A task has one coordinating file: the plan `docs/plans/YYMMDD_HHMM_topic.md`. It holds the goal and the scope, the status in the header, the role sections, and the logs. The plan itself names the other task files: the code draft, the review, and the review assets. The plan is created with the `$planveyor-plan-draft` skill. A role in a new session restores the task from the files, not from the conversation: chat is transport; the plan is durable semantic state. The `## Meta` block holds the machine-readable fields of the plan: the work contour, the dependencies on other plans, and the shared documents that the task will update. The plan linter `planveyor_plan_lint` checks the format: before a handoff and at the closeout.

Details: [The plan and its statuses](plan-lifecycle.md#the-plan-file). The decision that the plan is the only source of the meaning of the task is recorded in [ADR 001](../../adr/001-plan-path-single-semantic-source-of-truth.md) (in Russian).

### 2. Q&A and evidence logs

Questions and checks are kept in two sections of the plan. `## Q&A log` records the questions of the roles and the answers of Owner, and `## Evidence` records the checks and their results. New entries are appended to the end, so the log shows what happened and in what order. Oracle reads the current Owner questions, and while a question is open, Manager does not go further.

Details: [The plan and its statuses](plan-lifecycle.md#the-evidence-log-and-questions).

### 3. Task intake

Before the roles take up the work, Architect writes the `## Как я понял задачу` section (how I understood the task) in the plan and turns anything unclear into Owner questions. Owner answers with the `planveyor sibling answer` command, and the answer stays in the Q&A log. If the current turn is needed only to fill in the required blocks of the plan, and there are no new questions, no change of the scope, and no Owner decisions, Architect records this in the plan and moves the plan from `Architect initial draft` to `Architect draft` itself. After this move, the `sibling answer` command refuses when there is no open question, and the first version has no separate command to correct the section. So read the section before Planner starts work.

Details: the [stack sibling guide](../stack-sibling.md#the-task-understanding-section).

### 4. Code draft

Planner writes the code draft: the target files, the steps, and the checks that Coder must pass. The target files are part of the exact bundle of the plan (mechanic 15), so an edit outside the draft does not get into the standard task commit.

Details: [Roles and task files](roles-artifacts.md#task-files) and the [running example](sql-example.md#what-the-plan-and-the-code-draft-say).

### 5. Three work contours

A task goes through one of three contours. Development is for when the result and the scope are clear. Analysis is for when you first need to answer a narrow question and compare options. Decomposition is for when a large goal does not fit into one plan: the roles split it into child plans with an execution order and gather them in an umbrella plan. Related plans can be put into a queue, but the queue has no end-to-end check, and work on it is deferred; `planveyor sibling run` drives one selected plan.

Details: [Development, analysis, and decomposition](work-contours.md#three-work-contours).

## B. Launch the roles and check the handoff

### 6. Roles with separate responsibilities

Architect writes the plan and accepts the work, Planner writes the code draft, Coder changes the product files, and Reviewer checks in two lanes. Each role has its own responsibility for files and sections. Several roles append to the shared plan, and Architect adds the acceptance to the review file; the contract of the role and of the current stage defines which writes are allowed. Each role starts from what the previous one left, so its work also checks the result of the previous one.

Details: [Roles and task files](roles-artifacts.md#who-is-responsible-for-what).

### 7. Manager

Manager is the coordinator. It looks at the plan status, starts the next role, and checks what that role returned. It does not edit the plan, the answers, or the code, does not prepare files for the commit, and makes no commits. It learns what to do next from the plan status and the checks, not from the memory of its session.

Details: [Roles and task files](roles-artifacts.md#manager-and-the-handoff-check) and [ADR 002](../../adr/002-manager-router-only-and-oracle-routing-truth.md) (in Russian).

### 8. Oracle

Oracle is the `plan_status_oracle.py` script. Oracle checks status, route, and review freshness and reports what blocks the transition. The Manager instruction requires asking it on every turn instead of guessing the status from the conversation. Receipt and closeout gates authorize progress; Oracle makes no commits.

Details: [The plan and its statuses](plan-lifecycle.md#what-oracle-reads-and-reports).

### 9. Role launch

Public commands go through the `bin/planveyor` facade. It checks the Git checkout and the pinned engine version, starts a clean child process, and lets through only the allowed commands. In a single-role launch, the wrapper ties together the project, the plan, the role instruction, and the session and calls the agent harness; when it creates a separate role session, it also builds the XML context `.tmp/role_bundles/<role>.xml`. In collab mode, Manager hands the work to persistent Codex subagents, and none of them has a separate wrapper or XML context. By default, the roles work in Codex CLI. Planner and Reviewer can run in Claude Code in a single-role launch or in the Manager custom pipeline; both sibling modes, TUI mode and manual mode, use Codex.

Details: [Launch: commands, wrappers, agent harnesses](runtime-launch.md#the-facade-and-project-selection) and [agent harnesses](../harnesses.md).

### 10. The role's second pass (CENSOR)

In collab mode, at certain handoffs, Manager sends the same role a separate turn with the CENSOR prompt: the role checks its own result and fixes what it finds. This applies to Architect with the `Architect draft` or `Ready for Planner` status, Planner with `Ready for Coder`, and Coder with `Ready for Review`. Architect checks the work of Reviewer at acceptance. The work goes on only with a fresh record of the pass that the `censor_receipts_harvest.py` script has confirmed.

For tasks with only documents or only tests, you can explicitly choose the short route: the `planveyor_q_small_slice_json` command must confirm the same conditions before and after the role's work and right before the handoff. The size of an edit alone does not cancel the second pass. On the short route, the review and the final acceptance of Architect are not shortened.

Details: [Launch: commands, wrappers, agent harnesses](runtime-launch.md#manager-collab) and [Roles and task files](roles-artifacts.md#manager-and-the-handoff-check).

### 11. Two Reviewer lanes and Architect acceptance

Reviewer checks the work in two lanes: first the risk lane, then the contracts lane. Between them, the risk selector checks whether the result of the first lane, on which the second one relies, is ready. Then Architect reads the review and gives a verdict: accept the work or return it. If the review is stale, Owner still has a question, or the review has an S1 finding, Architect does not accept the work. The `planveyor sibling close` command requires exactly one `## Архитектурное ревью` or `## Arch review` section in the review file, where the first non-empty line outside a code block is `Вердикт: принято.` (verdict: accepted); the reasoning goes below it.

Details: [Review and acceptance](review-acceptance.md#two-reviewer-lanes).

### 12. Return to the responsible role

If the work is not ready, it goes back to the role that owns the fix. A gap in the meaning of the task goes to Architect, missing steps to Planner, and an implementation error to Coder. The return is recorded as the status in the plan header, and Manager starts the needed role by it. A known deadlock of the first version: if Reviewer asked Architect a question in the risk lane, Owner sets the needed status by hand (F49).

Details: [The plan and its statuses](plan-lifecycle.md#statuses-and-who-sets-them) and [Review and acceptance](review-acceptance.md).

### 13. Stop instead of guessing

Nobody makes up answers for Owner. If a role lacks a decision, it asks a question, and the route waits for the answer. A stop names its reason: for a semantic blocker, for example, `stop_class=semantic_blocker`. In addition, the Manager instruction limits one launch to twelve routing iterations on the active plan. At the limit, Manager stops with `Next: Owner`: in manual mode, Owner repeats `planveyor sibling run`, and in TUI mode, Owner asks Manager to continue in the same open window. How to continue an interrupted Manager session from the same step after a restart is not decided in the first version (F7).

Details: [If a command stops](../stack-sibling.md#if-a-command-stops) and [What works now and what comes next](capabilities-boundaries.md#limits-of-the-first-version).

## C. Keep changes within bounds

### 14. Evidence is tied to a version of the files

The review records the snapshot of the target files from the code draft, the `bundle_sha256` checksum. If a target file was changed after the review, the snapshot of the review no longer matches the current files: Oracle reports a stale review, and the task cannot be closed on it. Green CI is evidence, but not sufficient on its own; self-report may contribute evidence, but cannot override an authoritative gate.

Details: [Tests and evidence](testing-evidence.md#evidence-is-tied-to-a-version-of-the-files).

### 15. The exact bundle of the plan

The exact bundle is built from the target files and the declared deletions in the draft, the plan itself and the draft, the single review file, and the explicitly named review assets. The bundle also includes the immutable risk lane reports that the log of the plan refers to. The preflight runs before the work of Coder, and the final check after the review. Before Reviewer, the review file may only be planned, and a declared deletion is checked against Git. If another required file is missing, the check gives `MISSING-PATH`, and an extra path staged for the commit stops `close`. Only the changed files of the bundle go into the commit.

Details: [The plan and its statuses](plan-lifecycle.md#the-bundle-and-its-two-checks) and [ADR 004](../../adr/004-exact-bundle-truth-and-closeout.md) (in Russian).

### 16. Commit with Owner's consent

The commit policy sets who makes the commit, and the launch command chooses the policy. In manual mode (`human_explicit`), Owner looks at the exact bundle with `planveyor sibling close` and authorizes the commit with `close --commit`. In TUI mode (`native_existing`), Architect commits the exact bundle after acceptance, and each of its requests to write to `.git` is approved once in the Manager window, by Owner or by an operator whom Owner has authorized. `git push` is an Owner step: the engine only suggests the command.

Details: [Review and acceptance](review-acceptance.md#who-makes-the-commit).

### 17. Range check before the merge

The `planveyor_ai_gate` command separately checks a commit range against a policy file. It flags signs of AI work, checks the paths and the size of the changes, and looks for self-admitted technical debt (SATD): marks such as TODO and «временно» (temporarily). An external scanner, when it is enabled and available, does the secrets search. The example policy enables the optional `gitleaks`: if it is missing, the receipt records the skip and gives WARN. The final verdict is PASS, WARN, or BLOCK; the post-merge audit can read a ready receipt. This check is not part of the ordinary task route.

Details: the [post-merge audit playbook](../../playbooks/post_merge_audit.md) (in Russian); the example policy is `docs/tools/ai_gate_policy.example.json`.

## D. Preserve the task results

### 18. Docs closeout

After the task commit, the roles record the decisions and observations in the project documents. In the same TUI window, they can rely on the context of their sessions; a new manual `sibling run` restores the task from the files. In two stages, four roles carry the decisions and rules over into the shared project documents (the architecture, data, and API descriptions, and the guides) and propose follow-ups. During the docs closeout after `Done`, the roles do not change the plan, the draft, the review, the shared prompts, or the playbooks; a proposal to change the process is recorded separately. If the documents need a commit, it is a separate commit `docs(closeout): finalize <plan name>`.

Details: [Task closeout](closeout.md#docs-closeout).

### 19. Architecture decision records (ADRs)

A decision that constrains future changes is recorded apart from the plan, in `docs/adr/`. The plan is temporary, while an ADR stays and points to the place in the code where the decision is implemented. Architect usually writes the draft of an ADR during the post-merge plan harvest, when it is clear that the decision is no longer temporary; ADRs are not created for every task. This is how Planveyor records, for example, the plan as the only source of the meaning of the task (ADR 001), Manager that only starts the roles (ADR 002), and the exact bundle of the plan (ADR 004).

Details: the [ADR description](../../adr/README.md) (in Russian).

### 20. Process improvements (PIs)

At the docs closeout, each role answers with a `Process improvements` section: it proposes a process change or writes why there is none. The PI collector `process_improvements_collect.py` writes the proposal to `docs/process_improvements/`. Then Architect triages the record, Owner assigns the priority, and an ordinary plan carries out the change. Collection is part of the usual closeout, while triage, promotion, and reconciliation are started separately. A role does not edit the shared prompts and playbooks at the closeout: such a change goes only through a proposal.

Details: [How Planveyor changes itself](self-development.md#process-improvements-pis).

### 21. Follow-ups

Work that was decided to be done later is recorded as a follow-up with a responsible party and a reason. In the current `plan.v2` format, the roles submit proposals at the second stage of the docs closeout, and `followups_apply.py` writes them to `docs/followups/`. This way, work beyond the plan scope does not expand the current task. The triage of accumulated follow-ups is provided for at the post-merge plan harvest.

Details: [Task closeout](closeout.md#docs-closeout).

## E. Check the overall picture and maintain the documents

### 22. Post-merge check

The review of each task saw only the bundle of its own plan. The post-merge check looks at a commit range that has already reached the main branch: a range review in two lanes, merge notes, the harvest of decisions and deferred work from the plans, the shared document sweep, an audit, the archive, and a local commit of the check files. Manager runs it in merge mode, and the merge tracker keeps the steps. Owner starts it from the engine checkout: `./bin/planveyor planveyor_merge_collab_cmd --range <BASE>..<HEAD>`.

Out of the box, the check is set up for Planveyor itself. There is no `planveyor sibling …` subcommand for it; the low-level entry in a sibling needs separately declared range and merge-check policies, which the template does not create.

Details: [Post-merge check](postmerge.md#steps).

### 23. Shared document sweep and doc gardening

The documents that the roles work by gather stale content over time. At the `canon_sweep` step of the post-merge check, Architect cuts the shared Planveyor documents down to the essentials and leaves links to the details; if the documents are in order, the step may change nothing. Separately, there is the [doc gardening](../../playbooks/doc_gardening.md) playbook (in Russian): a manual session outside a merge in which long rules on one topic are folded into short entry points and stale content is cleaned up. Doc gardening has no script of its own.

Details: [Post-merge check](postmerge.md#steps).

### 24. Golden paths

The [Golden paths](../golden_paths.md) registry gives short pointers to the entry points of recurring work: the post-merge audit and plan harvest, the triage of process improvements, rollout, and the continuation of planning. A role does not work out the order anew; it starts from the pointer. If there is no matching row, the role records a follow-up or `N/A (why=…)` and does not invent a new anchor. The registry lives in Planveyor itself; it is not copied into a sibling.

### 25. Searchable archive

At the `docs_hygiene_archive` step, Manager saves the selected closed plans of the range that are safe to delete, together with their drafts and reviews, to a local SQLite archive with full-text search. The archive accumulates versions of the documents. Before the final closeout of the post-merge check, the route requires a separate export of a portable snapshot of the archive to Git and a check of this snapshot. Archiving itself deletes nothing: Owner chooses what to delete and deletes it in a separate commit after a fresh archiving and a fresh check of the candidates.

Details: [Post-merge check](postmerge.md#steps) and the [archive playbook](../../playbooks/post_merge_docs_hygiene.md) (in Russian).

### 26. Documentation search for the roles

A role finds the needed document by a local index instead of reading the whole directory: `planveyor_docs_retrieve` searches the current documents, and `planveyor_docs_get` reads what was found. The index is built with a separate command, `planveyor_docs_index_build all`; a role can call it too. If there is no index, the role instructions allow an ordinary search with `rg`. The role decides itself whether to search and records a search receipt in the plan.

Details: [documentation search](../../tools/snippet.md#documentation-search).

## F. Separate the project from the engine and accept changes

### 27. Sibling: a project separate from the engine

A project on its own stack lives in a separate repository (a sibling), and the engine lives in a separate Planveyor checkout. The project owns the product code, the stack harness, the plans, and the local sections of the role rules. The shared contract comes from Planveyor through Copier; eight files have local sections that an upgrade carries over unchanged. The project sets the stack and the local rules, and the engine checks its contract. The project decides itself when to take a new version.

Details: [Sibling: creation and upgrade](sibling-lifecycle.md#what-belongs-to-the-project-and-what-belongs-to-planveyor).

### 28. Upstream request

A shared problem of the project can be passed to Planveyor through a GitHub issue. Owner separately authorizes preparing the file and sending it through the installed `gh`. The maintainer imports the file into a process improvement, and after that the usual triage is needed. The project gets the accepted fix through an upgrade and its own upgrade plan.

Details: [Exchanging changes with Planveyor](change-packets.md#upstream-request).

### 29. Planveyor changes through the same process

Changes to Planveyor itself, to its prompts, checks, wrappers, and engine, go by the same route: a plan, the roles, a review, acceptance. After triage, a process improvement can become the basis of a separate plan. If a change concerns the shared contract, the projects learn about it on an upgrade (mechanic 30).

Details: [How Planveyor changes itself](self-development.md).

### 30. Upgrade with a contract notice

The project takes a new Planveyor version with the `planveyor sibling upgrade` command. The upgrade prepares a candidate, keeps the local sections, and creates an upgrade plan; the roles accept it by the usual route. A contract notice describes the change and the actions of the project, if the maintainer added one to the upgrade range. A contract notice has no addressee. A rule for when a notice is required and a check of its presence are not defined yet (F27).

Details: [Sibling: creation and upgrade](sibling-lifecycle.md#upgrading-to-a-new-planveyor-version) and [Exchanging changes with Planveyor](change-packets.md#contract-notice-what-a-new-version-brings).

## Examples: two Planveyor tasks

The numbers in parentheses are mechanics from the list.

### A new bundle check mode

The plan [`261018_2230_review_scope_closeout`](../../plans/261018_2230_review_scope_closeout.md) (in Russian) changed Planveyor itself. Before reading the changes, Reviewer had to run `planveyor_plan_bundle --check`, and this check requires an already finished review, so the steps went in a circle. The plan added the `--scope-check` mode: it checks only the composition and integrity of the bundle and grants no right to hand off the work, no green status, and no commit.

- From `Architect initial draft` to `Done`, the work was handed on with the usual statuses: `Architect draft` → `Ready for Planner` → `Ready for Coder` → `Ready for Review` → `Ready for Arch review`. Between them, the roles set their own working statuses (1, 12).
- Architect wrote the `## Как я понял задачу` section (how I understood the task); the Q&A log has no questions to Owner (2, 3).
- Planner put 32 target files and 45 test commands into the code draft (4).
- Architect made the second pass twice, Planner once, and Coder three times. On one of the passes, Coder found a gap in its own work: the results of the last checks were not recorded in the log, and Coder added them. The collecting script did not accept the record of this pass because of a tag in a neighboring entry, and the pass was repeated (10).
- The risk lane found an S1 finding: if the path of the future review matched the path of a target file, the new mode did not notice that the target file was missing. The contracts lane recorded blocker B1 and returned the work to Coder with the `In progress` status (11, 12).
- Coder fixed one condition in `scripts/planveyor.zsh`, added this case to a test, and handed the work back with `Ready for Review`. The snapshot of the target files changed, and the checks refused to go on with the old review (14).
- Both lanes checked the new snapshot. Architect ran Oracle and the risk selector and accepted the work (8, 11).
- The route commands ran from an unchanged copy of Planveyor, and only the tests ran the changed code (9, 29).
- 14 times the work stopped on an unexpected check result and went on only after a separate decision (13).
- Commit `cd48761`, 8 hours 25 minutes after the plan was created, contains 37 files: 32 target files, the plan, the code draft, the review, and two review assets (15, 16).
- The task did not change the Russian copy of the Owner runbook; its sync was recorded as a follow-up (21).
- The docs closeout commit `e9baf7c`, 1 hour 14 minutes later, added this follow-up and four process improvements. All four have the `open` status and the `P?` priority (18, 20).
- The edit touched 12 copies in the sibling template (`copier_template/`). Projects will get them with their next `planveyor sibling upgrade`, and the upgrade will keep their local sections. The edit has no contract notice: changes made before the first release were not carried into the notice directory (27, 30).
- Both commits are part of the published history of the first Planveyor version.

### Tests that depended on the machine

The plan [`261101_0052_ci_test_expectations_rebuild`](../../plans/261101_0052_ci_test_expectations_rebuild.md) (in Russian) is the first Planveyor task after the release. Seven tests depended on the machine they ran on. On the GitHub CI machine, the same Python file is called by a different name, and six tests compared the path as a string and took these names for different files. The seventh expected Moscow time, while the CI machine runs in UTC. The plan changed only two test modules: the tests compare the interpreter file itself and check both time zones explicitly.

- After the analysis, Architect set `Architect draft`; from there, the work was handed on with the usual statuses up to `Done`, and between them the roles set their own working statuses. Once, the plan went back from `Ready for Planner` to `Architect draft` (1, 12).
- Architect wrote the `## Как я понял задачу` section (how I understood the task). The plan pinned the final contents of both files by their Git object IDs. The roles recorded no questions to Owner in the Q&A log (2, 3).
- Planner completed the code draft: two target files, the order of checks, and the commands for Python 3.10 and 3.12 (4).
- Architect made the second pass three times, Planner and Coder once each. On the first pass, Architect found two inaccuracies in the plan and fixed them (10).
- After the second pass at `Ready for Planner`, the post-write check failed. In unchanged Planveyor role documents and playbooks, the documentation linter found five links to the `README.md` file in the `docs/` directory. This file exists in a project on its own stack but not in the engine copy; these links match the description of follow-up F25. Architect did not edit documents outside the plan scope and did not count the check as passed: it returned the plan to `Architect draft` and recorded a blocker in the `Objections / risks log` section (12, 13, 21).
- Owner's decision is recorded in the plan: the links stay an external debt, and of the documents, only the plan and the code draft of the task are checked, as [ADR 006](../../adr/006-doc-lint-scoped-closeout-gate.md) (in Russian) allows. Architect handed the plan to Planner again, and the second pass was run anew, with a new record (2, 10).
- Coder carried over both files and checked their IDs. Before and after the edit, Coder collected the list of all tests on both Python versions: 3517 identical IDs, and the split into 14 parts of the suite (`run_test_shard.py --check`) did not change (14).
- Then Coder ran each of the seven tests separately on Python 3.10 and 3.12, 14 runs in all. In each log, Coder checked `Ran 1 test` and `OK` with no skips: the plan did not count exit code 0 alone as enough (14).
- The risk lane recorded the target snapshot in an immutable review asset and found nothing. The contracts lane selected this record with the risk selector itself and assembled the single review file with the `✅ OK` result. Both lanes read all 14 Coder logs again. They did not rerun the tests themselves, and the review states this explicitly (11, 14).
- The first linter check of the new review failed: the `Visual env` line was missing. Reviewer added it, and the repeated checks passed (11).
- Architect read the changes, the review, and the logs. Oracle showed `review_route=review_green`, and Architect accepted the work (8, 11).
- The roles worked as Codex subagents in collab mode. The route commands ran from an unchanged copy of Planveyor, and only the tests ran the changed code (9, 29).
- Before the commit, Architect staged the exact bundle. The first staging failed: the sandbox did not allow creating the Git index lock file (`Operation not permitted`). After an approved request for elevated permission, the same command went through. The `oss_release_scan.py` scanner checked the whole public copy, the staged files included, for banned names and paths and found no blockers (15, 16).
- Commit `fd4f4b5`, 4 hours after the plan was created, contains six files: two test modules, the plan, the code draft, the review, and the risk lane asset (15, 16).
- The docs closeout commit `11ace6c` added one process improvement: Coder proposed to add a note on these CI pitfalls to the [verify suite runbook](../../tools/verify_suite.md). The record has the `open` status and the `P?` priority (18, 20).
- The edit did not touch the sibling template or the shared contract: a project on its own stack has nothing to change because of it (27, 30).
- `git push` to `main` was done outside the roles; it is a step of Owner (16). The `Planveyor checks` workflow passed on `11ace6c`: 29 jobs out of 29 in about 4 h 11 min. This is the first successful run in the published repository: the two earlier runs failed.
- Not all earlier failures concerned these seven tests. The plan did not analyze the others: they did not repeat in this run, but their causes are not established. One green run does not prove that CI is stable.

## What the published history shows

This cross-section describes the published materials of Planveyor at `11ace6c3` and of the published SQL project [`planveyor-mssql`](https://github.com/planveyor/planveyor-mssql) at `8099a1d9`, checked on November 1, 2026. This is not the unpublished SQL project that the examples in the other chapters of this section come from. A mechanism that exists, a separate check that was run, and an accepted task are different kinds of evidence. “End-to-end use not confirmed” means that no completed route was found in these materials; it does not claim that there were no runs anywhere.

| Group | Confirmed use | End-to-end use not confirmed |
| --- | --- | --- |
| A | Eight Planveyor plans and four plans of the SQL project in the `Done` status, all in the development contour, with logs and code drafts | analysis, decomposition, the plan queue |
| B | The roles, Manager, and Oracle in each of these plans. The second pass of the roles; in the SQL project, Coder found on its second pass its own error in parsing a long numeric counter in XML, fixed it, and repeated the full run. Returns: in the adaptation of the SQL project, review sent the protection against overwriting a tracked file back to Coder three times. Stops at the Manager step limit. Launches in Codex | the short route without the second pass; live launches in Claude Code and ZCode |
| C | Reviews with a target snapshot, and the snapshot going stale after an edit. Exact bundle commits: in the SQL project, two with `close --commit` in manual mode and two in TUI mode. The commit of the fourth plan was published after its local commits were combined, as the project guide notes | `planveyor_ai_gate` |
| D | Six docs closeout commits in Planveyor and two in the SQL project. They change only the records of process improvements and follow-ups and their summaries: moving decisions into the shared documents this way is not confirmed, and whether it was needed cannot be determined from the contents of the commits. There are 28 process improvements in Planveyor and seven in the SQL project. One follow-up was recorded through the docs closeout | PI triage: all records are in the `open` status with the `P?` priority, and there are no `promoted` or `handled` records; follow-up triage; new ADRs: all nine Planveyor ADRs are already in the first published commit |
| E | The SQL project keeps one documentation search request with `outcome=used`: the role opened the historical adaptation plan and relied on it when setting the next task | the post-merge check, the shared document sweep, doc gardening; there are no portable archive snapshots, and whether a local archive was created cannot be determined from the history |
| F | One upgrade of the SQL project to a new Planveyor version, without contract notices; changes to Planveyor itself through plans | the exchange of an upstream request through a GitHub issue: there are no exchange files, and at the time of the check the GitHub API returned no issues |

An example of a loop that is not closed. At the closeout of the `261015_0939_general_pi_format_correction` plan, Coder recorded the proposal PI-001: a check subprocess ended on a timeout, the temporary fixture was deleted, and the cause of the failure could not be determined. Coder proposed to keep the command trace and the partial output until the cleanup. The record lies in `docs/process_improvements/` with the `open` status and the `P?` priority. The next step is triage: Architect assigns the file and the delivery mode of the change, Owner assigns the priority, and then an ordinary plan carries out the change.

The first successful run of the `Planveyor checks` GitHub workflow came on November 1, 2026, at `11ace6c3`, the docs closeout commit of the [second example](#tests-that-depended-on-the-machine). Keeping CI green with an acceptable run time is still open work F5 in the [First-release backlog](../../release_backlog.md) (in Russian).

## What is not in the list

- **Measured pipeline efficiency.** Standalone commands for extracting traces and delivery metrics exist, but the guides do not describe them yet. Reports on sessions and waves are available too. Measurements of performance and context use, by which efficiency could be judged, remain open work F3 in the [First-release backlog](../../release_backlog.md) (in Russian).
- **Rollout.** A sibling does not receive change packets for a specific repository (`docs/rollout_packets/`). Whether to keep the mechanism only for Planveyor itself or to remove it is not decided yet (F29).
- **Project profiles.** Planveyor has no profiles of its own for projects: everything that concerns the stack lives in the sibling itself.
- **External practices.** Their analysis is mentioned in the materials about the origin of the process, but Planveyor has no separate route for it. A borrowed rule, if it is decided to adopt it, changes Planveyor through an ordinary plan.

Next: [Roles and task files](roles-artifacts.md).

# Sibling: creation and upgrade

**English** · [Русский](sibling-lifecycle.ru.md)

A sibling is a separate Git repository of your project, created from Planveyor: the product code, the stack harness (`Makefile` and the build and check scripts), the plans, and the role rules. This chapter explains what in it belongs to the project, how `planveyor sibling init` creates the project, and how `planveyor sibling upgrade` brings a new Planveyor version into it. The order of the commands is described in the [stack sibling guide](../stack-sibling.md).

## Which scenario you need

Choose a row by where the change should appear: in your project or in Planveyor.

| What you need | What to do | What you get | What remains |
| --- | --- | --- | --- |
| There is no project yet | `planveyor sibling init`; see [project creation](../stack-sibling.md#one-time-setup-environment-and-project-creation) | A new repository with the Planveyor contract and a first commit under your Git identity | Run the first plan: the stack adaptation |
| Change the product or the stack rules | An ordinary plan in the project; see [the plan and its statuses](plan-lifecycle.md) | Changed code, checks, or local sections of the rules | Review, acceptance, commit, and docs closeout |
| Move to a new Planveyor version | Update the Planveyor checkout, then `planveyor sibling upgrade`; see [getting a new version](../stack-sibling.md#get-a-new-planveyor-version) | The carried-over contract, a backup, and an upgrade plan | Run the upgrade plan with the roles up to acceptance and docs closeout |
| A shared Planveyor problem was found in the project | An upstream request; see [proposing a change](../stack-sibling.md#propose-a-change-to-planveyor) | A checked request file and, with your permission, a GitHub issue | The decision is made in Planveyor; if the proposal is accepted, the fix comes with a new version. Sending a request does not guarantee a fix |

Upstream requests, contract notices, and rollout packets are covered in the [Exchanging changes with Planveyor](change-packets.md) chapter. A sibling does not receive rollout packets now.

## Example: an SQL project

The examples come from the SQL project where the `GetReorderCandidates` task of the learning section's running example was solved. The project is not published; the files of its task are in the [snapshot](examples/sql/README.md). Its whole history fits into seven commits:

| Commit | When | What it contains |
| --- | --- | --- |
| `b2962f4` | September 27, 19:05 | Init: the Planveyor contract, 105 files |
| `fb6f9bf` | September 27, 20:41 | Adaptation to SQL Server: the harness, configuration, and local sections, 28 files |
| `60332b4` | September 28, 00:00 | Docs closeout of the adaptation |
| `70526ee` | September 28, 02:17 | The `GetReorderCandidates` task |
| `edac1b9` | September 28, 03:05 | Docs closeout of the task |
| `6a353de` | September 28, 11:06 | Upgrade plan to the next Planveyor version, 7 files |
| `f4f707b` | September 28, 11:15 | The `Done` status and the acceptance record in the upgrade plan |

All of this predates the `planveyor sibling` commands: an operator launched the roles and the live runs on the dev database (see [Roles and task files](roles-artifacts.md)), and the commits were made without `planveyor sibling close --commit`. The [Who makes the commit](review-acceptance.md#who-makes-the-commit) section explains how commits work now.

## What belongs to the project and what belongs to Planveyor

From Planveyor, the project gets the contract: role definitions, prompts, playbooks, templates, architecture decision records (ADRs), and skills in `.agents/skills/`. Copier, a project template tool, lays out and updates the contract. Two project files record the Planveyor version the contract was built from: `.copier-answers.yml` (the `_commit` field) and `planveyor_contract_authority.v1.json` in `docs/_meta/`.

| What | Who owns it | Example from the SQL project |
| --- | --- | --- |
| Shared role rules, prompts, playbooks, and templates | Planveyor; they come with the contract | `docs/roles/`, `docs/tools/prompts/`, the shared part of the review playbook `review_staged_or_commit.md` |
| Engine commands, wrappers, and scripts | Planveyor; they stay in the external checkout | The engine's `bin/planveyor` and `scripts/` live only in the Planveyor checkout |
| Product code, the stack harness, plans, and reviews | The project | The procedure [GetReorderCandidates.sql](examples/sql/sql/Northwind/GetReorderCandidates.sql), the harness [sql.py](examples/sql/scripts/sql.py), `Makefile`, plans in `docs/plans/` |
| Local sections of the role rules | The project | Six `make` targets in the Coder rules; the condition under which Reviewer does not repeat the run on the dev database |
| The agent harness, accounts, and the dev environment | Owner or whoever is responsible for the dev environment | `.env.local` with mode 0600, the dedicated dev database |
| The choice of the engine version and the upgrade | Owner | The move to the next Planveyor version on September 28 |

### Local sections

The stack rules are written in eight files: in the prompts `architect_status_driven.md`, `planner_status_driven.md`, `coder_status_driven.md`, `coder_migrations_gate.md`, and `reviewer_status_driven.md`, and in the playbooks `review_staged_or_commit.md`, `review_merge_range.md`, and `post_merge_audit.md`. Each of them has two sections with fixed headings: `## Локальные правила стека` (local stack rules) and `## Разрешённое локальное переопределение процесса` (allowed local process override). After init, their text belongs to the project, and Planveyor adds nothing there. The rest of the text of these files (shared rules, statuses, role permissions) belongs to Planveyor.

The contract delivers the section unfilled; here it is as written, in Russian:

```markdown
## Локальные правила стека

- Подготовка, build/test/smoke commands: N/A (why=stack-specific rule not configured)
```

After the adaptation, this line in the Coder rules of the SQL project began like this:

```markdown
- Подготовка, build/test/smoke commands: для текущей адаптации реализуй шесть interface targets `setup`, `db-extract`, `db-build`, `lint`, `check-secrets`, `db-proof` в `Makefile` и ignored local tools/cache/output до первого setup. …
```

The second section is for departures from the shared process. In the SQL project, it was filled in only in the review playbook. Reviewer need not repeat `make db-proof` if the SQL, tool, and configuration files match byte for byte the files on which the operator already did the run, and the set of tests matches the JUnit report of that run. The reason is written in the same place: publishing the schema again to a shared dev database may affect someone else's state. Such an override does not change the statuses or the review route.

## Creating the project

The `planveyor sibling init ~/my-stack` command creates a new repository outside the Planveyor checkout. It takes the Planveyor version from the current commit of the checkout, so everything in the checkout must be committed. The first commit is authored with your name and email, taken from the Git settings or from the `--author-name` and `--author-email` flags. The project directory must be new or empty.

The project is assembled in a temporary directory `.<name>-init-…` next to the target one. Copier lays out the contract; the command creates a repository with the `main` branch, saves your name and email in it for the next commits, makes the commit `Initialize Planveyor sibling contract`, and checks the contract. Only after a successful check does the temporary directory take the place of the project; if a step fails, the temporary directory stays next to the target for analysis.

Init creates neither a plan nor a stack brief. The command ends with a hint: open the project in a chat and ask the `$planveyor-plan-draft` skill to create and select the stack adaptation plan.

![How a sibling appears: the choice of the engine and the directory, init, the adaptation plan, the work of the roles, review, and docs closeout](assets/sibling-lifecycle-1.svg)

### The first plan: stack adaptation

The skill creates the plan and the stack brief `stack_brief.md` in the project's `docs/` from the `docs/_template_stack_brief.md` template. The stack brief has ten sections: from the purpose of the project and the stack to the live target (the dev database or service that the live checks work with), who runs these checks, and what is out of scope. If a field of the stack brief is empty, Architect asks Owner a question and suggests an answer.

Then the plan goes the usual way, from Architect to acceptance. Coder writes the harness, the checks, and the local sections, and Reviewer checks that the stack commands really check the product. The plan scope includes the stack harness, the root `README.md` of the project, and the local role rules. The adaptation is finished after the docs closeout (the [Task closeout](closeout.md) chapter).

The SQL project did not have a stack brief yet: that Planveyor version had no template for it. Owner gave the stack decisions in the assignment, and Architect wrote them directly into the adaptation plan `260927_1913_sql_server_adaptation`. Two items from its `## Solution (high level)` section:

```markdown
- В текущем sibling зафиксировать `.NET SDK 10.0.401`, `Microsoft.Build.Sql 2.3.0`, `tSQLt.Dacpacs 1.0.8083.3529` с `tSQLt.2019`, `SqlPackage 170.5.96`, SQLFluff `3.4.2` и `go-sqlcmd 1.10`. …
- `Makefile` предоставляет только существующий набор интерфейсов `setup`, `db-extract`, `db-build`, `lint`, `check-secrets`, `db-proof`; …
```

The plan covered 22 target files. Fourteen of them belong to the harness and configuration, among them `Makefile`, the harness [sql.py](examples/sql/scripts/sql.py), and the schema `sql/Northwind/Northwind.sql`. The other eight are the files with local sections. The adaptation commit `fb6f9bf` appeared at 20:41, 1 hour 36 minutes after init. It has 28 files: the 22 target files, the plan, the code draft, the review, and three review assets.

## Upgrading to a new Planveyor version

You choose the new version: update your Planveyor checkout, for example with `git pull` in it. The upgrade command itself does not run `git pull` and does not switch the branch. The new version must continue the earlier history and be on a branch or tag.

Before the upgrade, finish the current plan, including the docs closeout, end the role sessions, and leave the project directory. The upgrade swaps the directories, so you run it from outside:

```sh
planveyor --project ~/my-stack sibling upgrade
```

Usually the `planveyor sibling` commands find the project from the current directory; the `--project` flag names it explicitly.

### How the upgrade goes

1. **Checks before copying.** The command makes sure that everything is committed in the Planveyor checkout and in the project, that the project has its own `.git` directory (the command rejects a git worktree), and that the new version continues the earlier one. Then it compares the project with the contract of both versions: whether all files are in place and whether the local sections can be read. If the new version removes from the contract a file that the project changed, or some contract files disappear while others appear, the upgrade stops. At the same step, the command checks every contract notice between the versions, that is, a Planveyor JSON file about what has changed and what to do in the project (details are in the [Exchanging changes with Planveyor](change-packets.md) chapter).
2. **Upgrade candidate.** The command copies the project into the directory `.<name>-upgrade-<first 12 characters of the new commit>` next to it and runs Copier in the copy. Then it compares the local sections with the original ones byte for byte, looks for traces of a conflict (`<<<<<<<` markers, `.rej` files, unresolved conflicts in the Git index), and checks the contract of the candidate: whether all files are in place and whether the new version is recorded. Any problem stops the upgrade, and the original project stays as it was.
3. **Upgrade plan.** If everything is clean, the command creates in the candidate an adaptation plan for the upgrade (below, the upgrade plan) with the `Architect initial draft` status and checks it with the linter; if the plan fails the linter, the original project does not change either. The plan name is made of the date, the time, and the short hashes of both versions: `docs/plans/YYMMDD_HHMM_contract_upgrade_<old>_<new>.md`. In `## Scope`, the command writes both engine versions, the notices, and, as a list of paths, the changed contract and engine files (from `scripts`, `bin`, and `Makefile`). The roles find out for themselves what has changed in substance, from the notices and the diff.
4. **Backup and directory swap.** Only now is the original directory renamed to the backup `.<name>-before-<first 12 characters of the new commit>`, and the candidate takes its place. If the second rename fails, the command restores the original directory.
5. **Plan selection.** The command makes the upgrade plan current, prints the backup path and the message `Контракт обновлён; адаптация ещё открыта.` (the contract is updated; the adaptation is still open), and names `planveyor sibling architect` as the next step.

![How the upgrade goes: checks, the candidate, the upgrade plan before the directory swap, then the work of the roles and docs closeout](assets/sibling-lifecycle-2.svg)

The plan is created on every successful upgrade. After a regular upgrade, the files changed by Copier and the new plan lie in the project uncommitted. Then the upgrade plan goes through the same cycle as any task: `architect`, `run`, `close`, `close --commit`, and the docs closeout.

### How it went in the SQL project

The upgrade plan appeared on September 28 at 09:45. The command wrote into it three changed contract files (`.copier-answers.yml`, `planveyor_contract_authority.v1.json`, and the review playbook `review_staged_or_commit.md`), one engine test file, `scripts/test_consumer_contract.py`, and one contract notice.

In the text that belongs to Planveyor, the upgrade changed one line. Copier inserted it into the review playbook right above the local sections and did not touch the sections themselves (commit `6a353de`):

```diff
+При обновлении sibling укажи в локальном плане адаптации оба source commit и проверь сохранность bytes локальных секций до и после Copier.
+
 ## Локальные правила стека
```

The other two contract files store the Planveyor version, and the engine test file, as Architect recorded, belongs to Planveyor itself. Planner wrote a code draft with three target files: those same contract files. Coder and Reviewer compared the 16 local sections in eight files with the backup, and all of them matched byte for byte. Neither Reviewer lane had findings. At 11:06, commit `6a353de` recorded seven files: the three contract files, the plan, the code draft, the review, and a review asset.

### If the upgrade stopped

When the command stops before copying, it reports the reason. What to do:

- the project or the Planveyor checkout has uncommitted changes, the command was run from inside the project, or the project is opened as a git worktree: fix this and run the command again;
- the Planveyor checkout has the same version as the project, or a version that does not continue its history: select the right version in the checkout;
- the candidate path is occupied: an earlier run stopped with a candidate; finish resolving it up to `--accept-candidate`, or remove the candidate directory and start over;
- the new version removes a file that the project changed, contract files are renamed ambiguously, or the backup path is occupied: such cases need a separate analysis, and the command has no workaround;
- a broken contract notice lies in the Planveyor history and cannot be fixed in the project: the upgrade will not pass through this range of versions (item [F27](../../release_backlog.md#f27) of the First-release backlog, in Russian). Report it with an upstream request.

The upgrade stops with a candidate if Copier exited with an error, traces of a conflict remain in the candidate, a contract file removed in the new version is still in place, the text of a local section changed or disappeared, or the contract of the candidate failed the check. The original project then stays as it was, and there is no backup yet.

Currently, `planveyor sibling upgrade` exits with code 3 in this case and shows only the warning about the directory swap: the command does not print what failed or where the candidate is. The candidate lies next to the project, in `.<name>-upgrade-<first 12 characters of the new commit>`. A repeated run of the same command names the exact path: `candidate path already exists: …`. Look for the cause in the candidate itself: `git status` shows unresolved conflicts and `.rej` files, a search for `<<<<<<<` finds the conflict markers, and a comparison of the eight files of the candidate with the files of the project shows the changed local text.

The candidate has no upgrade plan yet. Open the candidate directory in a regular agent harness chat and ask the agent to resolve the conflicts and check the diff. After review, commit the result in the candidate's Git and accept the candidate from outside with the same command and a flag:

```sh
planveyor --project ~/my-stack sibling upgrade --accept-candidate
```

Between the stop and `--accept-candidate`, do not update the Planveyor checkout: you need the same version that the candidate was created with. The command checks that the history of the candidate continues the history of the project and that everything in the candidate is committed. Then it repeats the checks of the first step and, now without Copier, the candidate checks of the second step, creates the upgrade plan, and swaps the directories.

### Where the risk remains

The upgrade checks do not judge the meaning of the changes. The upgrade plan, the review, and the live checks of the roles show whether the commands of your stack work with the new rules. With `--accept-candidate`, the command does not compare the contents of the contract files with the new version of the template, and only the review of the candidate confirms that the conflict was resolved correctly. This is also recorded in item F27.

The backup contains the whole project, including `.env.local` and the local state. Do not publish it anywhere, and delete it yourself once the upgrade plan is accepted.

### If the Planveyor checkout has moved ahead

The engine runs from the external Planveyor checkout, and you need to keep track of its version. If you have updated the checkout but not yet the project, `planveyor --project ~/my-stack planveyor_consumer_doctor` exits with code 3 and a `blocked` JSON diagnostic with `runtime commit … differs from contract …` in `problems`. `planveyor sibling ready` also exits with code 3: it forwards the doctor diagnostic to `stderr` with the prefix `planveyor sibling:` and does not name a next command. Doctor compares the project contract with the engine version. In that case, run the upgrade or select a Planveyor checkout of the version recorded in `_commit` of the `.copier-answers.yml` file.

## What Owner does

1. Creates the project and runs the stack adaptation plan: `planveyor sibling init ~/my-stack`, the `$planveyor-plan-draft` skill, then `plan` to check the selected plan (select the created plan by its path if needed), followed, in TUI mode, by the answers to the open questions, the approval step, and the Manager window `planveyor sibling tui`, or, in manual console mode, by `architect`, `answer`, `run`, `close`, `close --commit` ([Adaptation to your stack](../stack-sibling.md#adaptation-to-your-stack)).
2. For a new version, updates the Planveyor checkout, finishes the current plan, leaves the project, and runs the upgrade ([Get a new Planveyor version](../stack-sibling.md#get-a-new-planveyor-version)).
3. Opens the project again and runs the upgrade plan with the same cycle.
4. If the upgrade stopped with a candidate, resolves it in the candidate directory, commits the result, and runs `--accept-candidate`.
5. Deletes the backup after the upgrade plan is accepted.

## Common mistakes

- Treating the message `Контракт обновлён` (contract updated) as a finished upgrade. The upgrade is finished when the upgrade plan is accepted and the documents are closed.
- Writing stack rules outside the two local sections. Only these sections are protected byte for byte during an upgrade.

The functions and tests discussed here are in the [code map](code-map.md#sibling-creation-and-upgrade).

Next: [Exchanging changes with Planveyor](change-packets.md).

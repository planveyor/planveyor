# Stack sibling

**English** · [Русский](stack-sibling.ru.md)

A sibling is a separate Git repository for your code, plans, and stack rules. The Planveyor engine stays in an external checkout. This guide takes you from project creation to the first product task, and then applies to every next task.

The main commands are `planveyor sibling …`. They find the project from the current directory, take the selected plan, and check the engine version in effect. You choose the task, answer the questions of the roles, and confirm the commits.

## One-time setup: environment and project creation

The first version supports macOS. You need Git, zsh, rg, and a prepared environment with Python 3.12, Copier 9.18.2, and PyYAML as pinned in `requirements-dev.lock`. Python 3.12 must come first in `PATH`, in a login shell too: roles run their commands there, and the stack harness may call a bare `python3`. The temporary directory `TMPDIR` must exist and lie outside any Git repository. The [Supported environment](launch-and-role-modes.md#supported-environment) section of the launch guide shows how to check this.

Roles need an authorized Codex CLI with configured roles. Your Codex configuration sets their models: the Codex home or the project `.codex/` directory. Planveyor does not create or show this configuration, so mark the time before the first launch, and after it check which models were applied. All of this is described in the [Codex setup](launch-and-role-modes.md#codex-setup) section.

You prepare the tools and the dev environment of your stack separately. Start the adaptation on a fresh, empty dev target, and recreate it before each repeat from scratch: leftovers of earlier runs cause false questions from the roles. The command names a missing prerequisite; Planveyor does not install or configure it automatically.

In the prepared terminal, open the directory of the selected Planveyor checkout with no uncommitted changes. `init` and `upgrade` check this themselves; you do not need a separate Git command. If `planveyor` is already on `PATH`, skip the next step. Otherwise, make the command available in this tab:

```sh
export PATH="$PWD/bin:$PATH"
```

This line uses the current checkout and does not change your shell config. A new tab needs the same selected checkout on `PATH`. From its root, the direct call is `./bin/planveyor`; no separate command installer is needed.

You can run the commands in your own terminal or ask an agent in a Codex chat to run them. The folder in which the chat is open sets the chat sandbox, and the sandbox may stop a command from writing where it needs to: `architect` and `run` write role sessions to the Codex home, and `init` and `close --commit` write to `.git`. For `init`, open the chat in the parent directory of the new project; for the other commands, open a new chat in the project root. You grant access beyond the sandbox for a specific operation. On a refusal, read the command's message: `planveyor sibling` also returns code 3 when its own checks refuse in the ordinary way, so code 3 alone does not prove an access denial.

Choose the directory of the new project. In the example, it is `~/my-stack`; replace only the project name with yours:

```sh
planveyor sibling init ~/my-stack
cd ~/my-stack
```

The parent directory must exist. The directory lies outside the Planveyor checkout, and its path goes through ordinary directories without symbolic links. The name starts with a Latin letter or a digit and contains only letters, digits, `.`, `_`, and `-`; the name `default` is not allowed. If a non-empty project already exists there, the command keeps it and refuses `init`.

`init` gets the version of the selected engine itself, makes the first commit with your Git identity, and saves that identity for the next commits of this sibling. If your name and email are not configured yet, set the pair explicitly:

```sh
planveyor sibling init ~/my-stack --author-name "Your Name" --author-email "you@example.invalid"
```

After a successful creation, the command checks the contract and reports the result. `init` does not create a plan or a filled-in stack brief yet.

## Adaptation to your stack

Open the sibling in a regular Codex or ZCode chat. The skills are already in `.agents/skills/`; you do not need to install them separately. In Codex, the skill is `$planveyor-plan-draft`; in ZCode, it is `/planveyor-plan-draft`.

Send in the chat:

```text
$planveyor-plan-draft Создай и сделай текущим план адаптации sibling под мой стек по docs/_template_stack_brief.md. Создай docs/stack_brief.md как вход плана. Задай вопросы по неподтверждённым решениям. Следующую полезную задачу согласуем отдельно.
```

In English, the request reads: “Create the stack adaptation plan of the sibling for my stack from docs/_template_stack_brief.md and make it current. Create docs/stack_brief.md as the plan input. Ask questions about unconfirmed decisions. We will agree on the next product task separately.”

Add the facts you know about your stack to the same message. The skill and Architect fill in the stack brief from them: the fuller the facts, the fewer questions Architect asks. It is convenient to collect them by the ten sections of the stack brief template, which lies in the sibling and is named in the request. The template sections suggest what to write and when the facts are enough (“Достаточно, если”):

1. the purpose of the project and how the readiness of its environment is checked;
2. the stack and the tool versions, where they are pinned, and forbidden features;
3. what the developer already has installed and what `make setup` installs;
4. the live target: the dev environment, its marker, and the target check before writing;
5. the credentials file and the key names, without values;
6. the stack commands: whether each needs network access or the live target, who runs it, and its exit codes;
7. how the result is proven: the format and the place of the test report;
8. the rules for the roles;
9. who runs the live targets: the roles with network access, or a person;
10. what is out of scope.

An example of such a block for SQL Server is section 6 of the guide in the `planveyor-mssql` repository (in Russian).

The skill creates the plan and the stack brief, and the plan scope includes the stack harness, the root `README.md` of the project, and the local role rules. Coder then implements the code in scope.

The skill uses the trusted facade selected in the launch environment. If the app does not see the `planveyor` command and does not get `PLANVEYOR_RUNTIME_ROOT`, it asks you once to choose the engine checkout. Do not write this path into public plans or stack rules.

Check which plan is selected. You can do this at any time:

```sh
planveyor sibling plan
```

The command prints the plan, its status, and the next step. The skill may create a plan and leave the plan pointer as it was. If no plan is selected yet, the command exits with code 3 and the message `Текущий plan не выбран или pointer повреждён. Выполните planveyor sibling plan docs/plans/NAME.md.` (the current plan is not selected or the pointer is damaged). If the pointer still points to an earlier plan, the command shows that earlier plan. In both cases, select the created plan by the path from the skill's answer:

```sh
planveyor sibling plan "docs/plans/<plan>.md"
```

The command does not pick a task by the latest file date.

Start the discussion with Architect:

```sh
planveyor sibling architect
```

The command prints the answer of Architect and, at the end, the plan, the status, and the line `Следующий шаг: …` (next step). The last such line is the one in effect. The output also has lines like these:

```text
- Next: Owner
- Open items: (to=Owner, needs_owner=yes) Provide `PLAN_PATH`
```

This is the fixed ending of the first turn of a role: the session first gets an introduction without the plan, and the facade passes the plan in the next message. You do not need to act on these lines.

If Architect asked questions, read them and the suggested options. Give your answer:

```sh
planveyor sibling answer
```

With several questions, the command shows their ids. For example, the answer to the shown question `Q2`:

```sh
planveyor sibling answer Q2
```

Type the answer as plain text; the command formats the log entry and the time itself. Empty input and cancellation do not confirm the suggested option. After it saves the answer, the command prints `Ответ сохранён. Следующий шаг: planveyor sibling architect` (answer saved; next step) or the same line with `run`. Run the printed step. While the plan is in the `Architect initial draft` status, the answer waits for the next Architect turn, and a second `answer` before that turn is refused with `Уже есть ожидающий Owner payload. Завершите соответствующий ход роли; существующие ответы сохранены.` (a pending Owner payload already exists; finish the matching role turn; the existing answers are kept). So in this status, answer several questions one at a time and run the printed step, `planveyor sibling architect`, after each answer. Default answers to common questions are in the [Common Architect questions](#common-architect-questions) section.

Repeat the discussion until Architect has agreed on the needed decisions. Extra role permissions and acceptance conditions need your explicit decision. When no choices are left for Owner, Architect moves the plan to the `Architect draft` status itself, and `planveyor sibling run` becomes the next step. Architect does not ask for a confirmation at this point: the pipeline is designed to work without a person.

### The task understanding section

The plan always has the `## Как я понял задачу` section (how I understood the task). Read it after `planveyor sibling architect` and before `run`, and compare it with your assignment and the stack brief. You can print the section like this:

```sh
awk '/^## Как я понял задачу/{p=1; print; next} p && /^## /{exit} p' "docs/plans/<plan>.md"
```

If the section differs from your assignment, do not start `run`. After the move to `Architect draft`, the first version has no standard way to correct the section: in this status, `answer` without an open question refuses with code 3 and the message `Открытых Owner вопросов нет.` (there are no open Owner questions).

To confirm the section yourself, add this to the skill request: “До перевода плана в Architect draft покажи мне раздел «Как я понял задачу» и дождись подтверждения” (before moving the plan to Architect draft, show me the «Как я понял задачу» section and wait for confirmation). Architect then usually opens a question, and you confirm the section through `planveyor sibling answer`. This is model behavior; the engine does not guarantee it.

If an agent runs the commands, ask it to print the section in the chat before every `run`. In the interactive Manager mode (`planveyor_manager_collab_tui`, see [Roles and entry points](launch-and-role-modes.md#roles-and-entry-points)), you talk to Manager directly and can ask it to print the section at the move to Planner. This mode uses `COMMIT_POLICY=native_existing`: Architect performs the closeout and the commit itself, without `close --commit`. You do not preview the commit, and this is the main difference from `planveyor sibling run`.

## Common Architect questions

Architect asks when the stack brief or the plan lacks a decision, and usually suggests an answer right away. Below are default answers to common questions of the adaptation and of an ordinary task. They fit any stack: put the facts of your stack from the stack brief and the assignment into the answer.

An agent may drive the pass on your behalf. Then it answers by this table and states in the answer that it answers on behalf of Owner. It does not revisit or re-agree decisions already made in the stack brief and the plan. It returns the other questions to you; they are listed below the table.

| Question | Default answer | What to fill in |
|---|---|---|
| Path to the Planveyor engine (the skill asks) | The path of your runtime: the Planveyor copy from which the commands run. It is not written into public plans, rules, or README. | The path of your copy |
| Confirm the `## Как я понял задачу` section | Re-read the current text. Confirm it if it matches the stack brief and the assignment and adds no work beyond the scope. Otherwise, name the difference and ask for a fix. In the adaptation, the next product task remains a separate assignment. | The project purpose and the readiness check of its environment |
| A stack brief field with a suggested answer | Accept it if the suggestion meets the “Достаточно, если” (enough if) condition of this section of the stack brief template. Otherwise, complete it to meet that condition. | The facts of your stack |
| Tool versions | Take the versions that are already installed and pinned in the project files. Do not choose new versions. Name a missing tool as a prerequisite. | The tools and the files that pin the versions |
| Which environment to use for project commands | The already prepared environment through `PATH` of the current process; the stack harness checks the actual version. Do not install system tools: only the `make setup` agreed in the stack brief installs project dependencies, and their caches live in `.tmp/`. Do not change the shell config, `HOME`, or the Codex config. Do not write private paths into the plan, README, or rules. | The interpreter or SDK of your environment |
| How to make sure that writes go to the dev environment | The code checks the agreed marker of the designated dev environment before every write. No marker means a refusal without a write. Roles do not change the server, the marker, or the accounts. | The marker and the way to check it in your storage |
| Check the presence of the marker or its value | Only the presence. The administrator sets the value; the harness does not read it. Do not introduce a new value, such as `value=1`. | The marker check query in your storage |
| Where the connection settings are | `.env.local` with mode 0600, in `.gitignore`, not tracked by Git. Only the key names go into the plan and README. | The key names |
| Which commands are allowed | The stack targets from the stack brief. Each one states whether it needs the network or a live target, who runs it, the expected exit code, and the report. | The `make` targets of your stack |
| Whether the harness tests need a separate offline target | Yes: the offline harness tests get their own target, such as `make test`, and run without the network and without a live target. Keep the stack brief and the plan in sync; Coder implements the target. | The target and the file of the offline tests |
| Who runs the live targets | Roles in a sandbox with network access, if the selected Codex home already has network access configured. Otherwise, a human operator. The agent does not enable the network itself. | The targets and the roles that run them |
| Acceptance conditions | Accept them if each condition names its test and checks the result, the inputs, and the outputs that the assignment requires. Add a missing negative or edge case. Do not introduce requirements beyond the assignment. | The tests of your framework |
| How to prove the result | With the report of a current run on the bytes under review. Reviewer repeats the check itself; in the operator-only variant, the operator repeats it at the request of Reviewer. An old green result and the report of another task do not carry over. | The format and location of the test report |
| A technical harness question: API, format, build, output parsing | This is not an Owner decision. Roles resolve it from the tool documentation and the stack brief facts, without changing the scope, the permissions, or the acceptance. If a fix needs a change to any of these, the role returns the question with options. | The documentation of the stack tools |
| Rebuild the harness differently or “better” | No. The stack brief decisions and the parts that already work stay. A new design is allowed only after a proven failure of the current approach, with the reason in the plan. | — |
| External models or MCP as part of the process | No: the process uses only the standard Planveyor tools. The requirement for external models and their receipts is dropped. | — |
| An open follow-up record on the same topic is found | Refer to it in the `Context links` of the plan and leave the record unchanged. Its promotion is not a condition of an ordinary task. | The `source_ref#item_id` reference |
| What is out of scope | Production, business data, server configuration, CI, and other operating systems, unless the assignment says otherwise. | The exclusions of your project |

The agent returns a question to you if it concerns:

- secret values (the agent may only check the file permissions);
- production, business data, or a target without the dev environment marker;
- administrator rights, or a change of the server, the marker, or the accounts;
- a scope expansion beyond the assignment and the stack brief, or a change of the stack or versions;
- enabling the network, or a change of the Codex configuration, `HOME`, or the selected engine;
- publication: remote, push, issue, repository visibility;
- a commit without your direct permission in this session;
- a decision that is in neither the stack brief, the assignment, nor this table.

An answer from the table does not replace the checks. A red result returns the work to the role. Confirming the `## Как я понял задачу` section does not authorize a commit.

## Run the plan

Before the first `run`, everything that the roles do not do themselves must be in place. This is your part of the work; the agent in the chat helps you prepare it:

- the environment from [One-time setup: environment and project creation](#one-time-setup-environment-and-project-creation): Python 3.12 first in `PATH`, in a login shell too, and `TMPDIR` outside Git;
- Codex CLI with a completed sign-in and the Manager collab roles in the selected Codex home or in the project `.codex/` directory; see [Codex setup](launch-and-role-modes.md#codex-setup); Codex applies the project directory only in a trusted project; see [Project `.codex/` directory](launch-and-role-modes.md#project-codex-directory);
- a time mark for the model check, set before the launch; see [Check the models in use](launch-and-role-modes.md#check-the-models-in-use);
- network access in the Codex home sandbox, if by the stack brief the roles run the live targets themselves;
- the credentials file, if the stack needs credentials;
- a fresh dev target with the designated dev environment marker and the permissions agreed in the stack brief.

The next two paragraphs describe the credentials and the access to the dev environment in more detail.

For a stack with credentials, the stack brief names the keys and the protected file, and after the adaptation the local `README.md` does. Enter the values in a local editor; secrets do not go into the chat, plans, or reports. `.env.local` needs mode 0600, must be ignored by Git, and must not be tracked. The harness reads the file, and the roles call only the accepted stack commands. The administrator prepares the dev environment with the needed markers and permissions; the harness must check it before writing.

If the roles need access to the dev environment, agree on one variant in the stack brief: network access for the selected Codex home, or live commands run by a person. The variant where the roles run the live targets themselves needs network access in their sandbox: it is enabled in the Codex home configuration before the first `run`; see the [Access to the dev environment](launch-and-role-modes.md#access-to-the-dev-environment) section of the launch guide. Planveyor itself does not open the network or change the Codex home. In the operator-only variant, the role stops with a specific command; after the command has run, pass the actual result through `answer`. A red result needs a fix and a repeated check.

When the Architect intake is complete, start Manager in collab mode:

```sh
planveyor sibling run
```

Manager drives the Architect, Planner, Coder, and Reviewer roles by the plan status. The command prepares the needed sessions; you do not need to remember their ids or refresh them after a commit. As after `architect`, the last `Следующий шаг: …` line of the output is the one in effect.

If Manager waits for your decision, run `planveyor sibling answer`, then the next step that this command prints. If Manager reaches its step limit, repeat the same `run`. A failed check returns the work to the responsible role; agreeing with an earlier green result cannot replace it.

During the adaptation, the roles create the stack harness, its checks, and its rules. The rules live in two local sections of eight files; an upgrade preserves exactly these sections:

| Role or phase | File |
|---|---|
| Architect | `docs/tools/prompts/architect_status_driven.md` |
| Planner | `docs/tools/prompts/planner_status_driven.md` |
| Coder | `docs/tools/prompts/coder_status_driven.md` |
| Coder: migrations | `docs/tools/prompts/coder_migrations_gate.md` |
| Reviewer | `docs/tools/prompts/reviewer_status_driven.md` |
| Commit review | `docs/playbooks/review_staged_or_commit.md` |
| Range review | `docs/playbooks/review_merge_range.md` |
| Post-merge audit | `docs/playbooks/post_merge_audit.md` |

### Stop `run` and continue the same plan

Stop when the work goes in circles: for example, review returns a finding on the same topic to Coder for the third time. Owner decides whether to stop `run` and whether to continue the same plan later.

1. Stop `run` with one SIGINT signal: press Ctrl-C in its terminal. An agent sends SIGINT to the process group of this `run`. Do not use `kill -9`. The command exits with a nonzero code, and the role may not have finished its turn.
2. Record the state without fixing anything:

   ```sh
   planveyor sibling plan
   git diff --cached --name-status
   git status --short --untracked-files=all > "$TMPDIR/planveyor-stop.status"
   git ls-files -m -o --exclude-standard -z | xargs -0 shasum -a 256 > "$TMPDIR/planveyor-stop.sha256"
   ```

   The index must be empty: `git diff --cached` prints nothing. The last two lines save the full list of the changed and new files and their checksums. The `--untracked-files=all` flag lists every new file, not only its directory.
3. Decide whether to keep the stop or to continue the same plan.
4. Before you continue, make sure that the files have not changed:

   ```sh
   git status --short --untracked-files=all > "$TMPDIR/planveyor-continue.status"
   diff "$TMPDIR/planveyor-stop.status" "$TMPDIR/planveyor-continue.status"
   shasum -a 256 -c --quiet "$TMPDIR/planveyor-stop.sha256"
   planveyor sibling plan
   ```

   `diff` prints nothing if the list of files is the same, and `shasum` prints nothing if all the sums match. This also shows new files inside new directories. `plan` shows the same plan and its next step. Run this step, usually the same `planveyor sibling run`: Manager continues the work by the plan status.

Do not edit the plan, the review, the statuses, or the receipts while `run` is stopped. Do not start a new plan to continue the work.

## Commit and docs closeout

When Architect has accepted the final review and Manager proposes the closeout, first look at the preparation:

```sh
planveyor sibling close
```

This call shows the state and the future set; it does not change the status, the index, or the sessions. If the plan is ready to commit, the first line of the output is `План принят. Следующий шаг: planveyor sibling close --commit.` (the plan is accepted; next step), followed by the file list and the line `Сообщение коммита: …` (commit message). An open question or a required check stops the preparation and gives the next step. Read the shown set and the message, and check its changes in an editor. If files were edited after the review, repeat the preview. Only then authorize the specific commit:

```sh
planveyor sibling close --commit
```

The `--commit` flag is your explicit confirmation to commit the checked current set; no extra general “yes” is needed. The command checks readiness again, moves the accepted plan to `Done`, and commits only its exact set. Staged files outside the set, a review that is not ready or is stale, and errors of the current checks mean a refusal. The roles get no hidden permission to commit.

`close` reads the acceptance of Architect in the review file. The file must have exactly one `## Архитектурное ревью` section (or `## Arch review`), and the first non-empty line of that section must be `Вердикт: принято.` (verdict: accepted). The heading from the template, `## Архитектурное ревью (Architect; optional)`, does not match: Architect removes the note in parentheses. Otherwise, `close` answers `Нужна одна секция «Архитектурное ревью» в review artifact. Следующий шаг: planveyor sibling architect.` (the review artifact needs exactly one such section) or `Первый вердикт Architect не даёт однозначной приёмки…` (the first verdict of Architect is not a clear acceptance). Run `planveyor sibling architect`, then `close` again. This is a technical return to Architect; no Owner answer is needed.

After the plan commit, the command prints `План закоммичен. Следующий шаг: planveyor sibling run для документов.` (the plan is committed; next step: `planveyor sibling run` for the documents). The docs closeout is a separate Manager turn:

```sh
planveyor sibling run
planveyor sibling close
```

If the documents need a separate commit, `close` prints `Документы готовы. Следующий шаг: planveyor sibling close --commit.` (the documents are ready; next step) and shows their set. Review it and run `planveyor sibling close --commit`: this is your separate confirmation of the already shown set. The first `--commit` does not start the roles and does not confirm documents that do not exist yet. After the documents commit, the command checks the closeout right away; if an obligation remains, repeat the step it names.

The work is finished after the message `План и документы закрыты. Можно начать следующую задачу.` (the plan and the documents are closed; you can start the next task). While the closeout is not complete, `close` may also exit with code 0 but print a different text, for example `Документы ещё не закрыты: <reason>. Следующий шаг: planveyor sibling run.` (the documents are not closed yet). Look at the text, not only at the exit code. `close` reports other incomplete states as a refusal with code 3, for example `Нет однозначного receipt-owned docs bundle; следующий шаг: planveyor sibling run.` (there is no unambiguous receipt-owned docs bundle). A `Done` status alone, the first commit, or a successful doctor does not yet mean that the whole step is complete. With several closeout cycles, the command asks you to name the actual cycle; it does not pick an arbitrary directory. A separate post-merge audit may stay open if the plan provides for it.

## Next task and readiness

Before the next task, check that the current one is closed:

```sh
planveyor sibling ready
```

The command checks the contract, the state of the selected plan, and the closeout of its documents. Readiness is confirmed only by the result `Consumer contract и выбранный план закрыты. Готовность отдельного release или SQL не проверялась.` (the consumer contract and the selected plan are closed; the readiness of a separate release or SQL was not checked). The command also prints other text with code 0, for example `Выбранный план ещё не закрыт. Следующий шаг: planveyor sibling run.` (the selected plan is not closed yet): the task is not finished, so run the printed step. Coder and Reviewer run the live checks of your stack by the accepted stack brief and plan; `ready` does not run them again. Compare the actual acceptance results: an old report or a report of another task does not replace them. The result does not mean a publication, a completed separate post-merge audit, or permission to write to production.

When `ready` has confirmed that the adaptation is closed, send in the same chat:

```text
$planveyor-plan-draft Создай и сделай текущим обычный план по моему прямому поручению: <result and observable check>. Покажи matching open follow-up, сохрани его неизменным и добавь source_ref#item_id в Context links.
```

In English, the request reads: “Create an ordinary plan for my direct assignment and make it current: <result and observable check>. Show the matching open follow-up, keep it unchanged, and add source_ref#item_id to Context links.”

Describe the result you want. The adaptation agrees on the purpose and the readiness of the stack; the next product task is a separate direct Owner assignment.

The skill checks whether an open deferred task covers the same topic and links it in the plan without changing it. The rules of this check are in [When an agent runs the pass](#when-an-agent-runs-the-pass).

The skill may leave the pointer on the earlier plan. Check the selection with `planveyor sibling plan` and, if needed, select the new plan by the path from the skill's answer, as in the [adaptation](#adaptation-to-your-stack).

Repeat the cycle: `architect`; for each question, `answer` and the step it prints, usually `architect` again; then `run` → `close` → a separate `close --commit`; for the documents, `run` → `close` → a separate `close --commit` when an obligation is shown; finally `ready`. Before the next task, finish the docs closeout of the current one. This sequence describes the expected steps, not a completed pass.

For a large task, the usual [analysis](../playbooks/analysis_wave.md) (in Russian) and [decomposition](../playbooks/decomposition_wave.md) (in Russian) routes remain. Ask the plan skill to choose the matching plan type with Architect. Separate low-level entry points and the queue are described in [Launch and role modes](launch-and-role-modes.md); `sibling run` works with the selected plan and does not create a queue itself.

## Return to work in an existing sibling

A sibling works with the engine version it is pinned to. If you continue working in an existing sibling, for example in a clone of the ready example or on another computer, select this version first and only then start a new task.

1. In the sibling root, look up the pinned version: it is the value of the `source_commit` field.

   ```sh
   cat docs/_meta/planveyor_contract_authority.v1.json
   ```

2. Switch your Planveyor checkout, with no uncommitted changes, to this version, and make its command available in this tab. Put the path of your checkout in place of `<Planveyor checkout>` and the `source_commit` value in place of `<version>`:

   ```sh
   git -C <Planveyor checkout> switch --detach <version>
   export PATH="<Planveyor checkout>/bin:$PATH"
   ```

   The version must be reachable on a branch or tag of this checkout. If it is missing there, first get it with the usual `git -C <Planveyor checkout> fetch`.
3. Check that the versions match:

   ```sh
   planveyor --project "$PWD" planveyor_consumer_doctor
   ```

   When they match, the command exits with code 0, its output has `"state": "ok"`, and `source_commit` equals `runtime_commit`. When they differ, the exit code is 3, `state` is `blocked`, and `problems` has the line `runtime commit … differs from contract …`. In this case `planveyor sibling ready` does not confirm readiness either: it prints `Consumer contract требует разбора; готовность не подтверждена.` (the consumer contract needs a review; readiness is not confirmed). If the checkout does not have this version, the command also exits with code 3 and names the cause in the `reason` field.

To move to a newer Planveyor version, first finish and close the current task, then select the new checkout and run the upgrade by the [Get a new Planveyor version](#get-a-new-planveyor-version) section. Start the new task after the upgrade plan is closed.

## Get a new Planveyor version

A sibling pins a specific engine version: roles, templates, and checks work by the same rules, and the result can be reproduced. The commands get this version and the technical identifiers themselves. You choose the new engine checkout first; the sibling upgrade goes through a separate ordinary plan.

Update the installed Planveyor checkout in your usual way. The `sibling upgrade` command does not do a hidden pull or switch the Git branch. The selected version must continue the earlier history and be reachable on a branch or tag. Finish and close the current work, save your changes, end the active sessions, and leave the sibling directory: `upgrade` swaps the directories.

From an outside directory, select your project:

```sh
planveyor --project ~/my-stack sibling upgrade
```

On a successful upgrade, the command gets the new version itself, checks that the local rules are preserved, and prints the paths of the backup and of the upgrade plan. The notices go into this plan, but the command does not print them separately. It creates the upgrade plan and selects it. Open the sibling again and run this plan through the same `architect` → `run` → `close` cycle. A message about the updated contract does not yet mean an accepted adaptation.

The `sibling upgrade` output calls this same plan “план адаптации” or “adaptation plan”. This guide calls it an “upgrade plan” to distinguish it from the first stack adaptation plan of a new sibling.

If the upgrade stopped with a candidate, the original sibling stays in place, and the backup and the upgrade plan are not created yet. The current wrapper returns code 3 and hides the stdout with the candidate path and the list of problems; stderr messages stay visible. The candidate lies next to the project in `.<name>-upgrade-<first 12 characters of the new commit>`. A repeated run of the same command names the exact path in the message `candidate path already exists: …`.

Open the candidate in a regular chat of your agent harness. Ask the agent to resolve the actual `git status` of the candidate, the `.rej` files, the `<<<<<<<` markers, and the changes of local sections, to check the exact diff, and to save the accepted result in the candidate. After a real review and a commit in the candidate, accept it from an outside directory:

```sh
planveyor --project ~/my-stack sibling upgrade --accept-candidate
```

The selected engine version must stay the same. A loss of local sections, an ambiguous rename, a broken notice, or an occupied backup path needs a separate analysis. The command does not fix them with a workaround. The backup holds a full copy of the project, including credentials and local state; keep it private and delete it yourself after the adaptation is accepted.

## Propose a change to Planveyor

You change the rules of your stack in the sibling. A shared problem of the engine or the process goes to Planveyor as an upstream request. This is the second public exchange scenario: a proposal from the sibling, a decision in the source, and the return of the fix through an upgrade.

In a regular sibling chat, ask for a request from `docs/upstream_packets/_template.md`: the symptom, the process gap, the suggested fix, and links to your task and to the place where the problem was found. Move the facts of your stack into `Target-Specific Facts To Filter`; secrets, server addresses, and absolute paths do not go into the request. The prepared request goes through checks and your review; asking to prepare the file does not yet authorize sending it.

After the request is accepted and committed, separately authorize sending the issue. This uses the installed and authorized GitHub CLI `gh` and the usual command `gh issue create --body-file <request file> --repo planveyor/planveyor --title "<request topic>"` with the exact prepared file. The `--repo` flag is required: without it, `gh` takes the repository from the remote of the current directory, that is, from your sibling, and stops if there is no remote. Ask the agent to show the ready command and the public body; you do not need to copy the text by hand or fill in technical ids. If `gh` is not set up, sending stops with a clear prerequisite. Creating an issue by itself does not mean that the proposal is accepted.

The Planveyor maintainer takes in the request with the standard source-local `planveyor_upstream_request_import` and `planveyor_upstream_request_ack`: they work only in the physical source root and are not run from a sibling. The decision and the fix go through an ordinary source plan. A change of the contract or behavior comes with a notice in `docs/contract_notices/` with checks and actions for the sibling.

After the selected version is published, run `sibling upgrade`. The created upgrade plan includes the notice and an update of the local copy of the request. The roles check the result on your stack; finish both commits and the docs closeout. The packet format and the low-level readbacks are described in [Lifecycle and packets](lifecycle-and-packets.md).

### Example: SQL Server sibling → provenance fix → upgrade

This is a hypothetical exchange after a version is published, not a report about an issue already sent. Suppose that in `planveyor-mssql`, the plan provenance loses the id of the current chat when the facade is called. SQL Server and tSQLt explain where the problem was found; passing the chat context is a shared Planveyor mechanism.

Ask for a request from the template with the actual links to the plan and the review of your sibling. For the example, the content is:

| Request field | Content |
|---|---|
| `origin_repo` | `planveyor-mssql` |
| `requested_source_canon_path` | `bin/planveyor` |
| `symptom` | Provenance has no id of the current chat after a facade call. |
| `process_gap` | The child facade loses the context of the calling chat. |
| `suggested_fix` | Pass the id as a provenance-only input and check the unset, empty, and present cases. |
| `Target-Specific Facts To Filter` | MSSQL/tSQLt stay the local stack and do not become engine defaults. |

Prepare and review the request, then separately authorize sending the issue with the same `gh issue create --body-file … --repo planveyor/planveyor` command. The source maintainer imports the request, makes a decision, and runs an ordinary fix plan. The notice in the [existing format](../contract_notices/README.md) (in Russian) includes a provenance check through the facade and `planveyor_consumer_doctor`; the sibling actions are to check its own SQL rules and to update the local copy of the request. Source-only ACK records the real decision/execution refs and the `decided` state in the source; ACK itself does not update the sibling.

After the publication, select the new Planveyor version and run `sibling upgrade`. In the upgrade plan, Coder checks the provenance and the real checks of your SQL stack, and reconciles the fields and refs of the local request with the notice. This target-local change goes through review, two exact commits, and the docs closeout; the source-only ACK is not called from the sibling. With a blocked candidate, first analyze its real cause. An issue, the source `decided` state, and a successful Copier run do not replace the acceptance of the adaptation.

## If a command stops

| What the command reports | Next step |
|---|---|
| A tool, a suitable Python, or authorization is missing | Prepare the named prerequisite and repeat the same command. |
| The project or the plan is not selected | Open the right sibling and select the created plan with `planveyor sibling plan` and its path; with several tasks, you choose. |
| Code 3 or a write denial in the agent chat | Read the message: code 3 alone does not prove an access denial. You grant access beyond the sandbox for a specific operation. |
| An Owner question is open | `planveyor sibling answer`, then the next step that this command prints. |
| `Уже есть ожидающий Owner payload…` after `answer` | The previous answer has not reached the role yet. Run the step printed then, usually `planveyor sibling architect`, and then answer the next question. |
| `Открытых Owner вопросов нет.` after `answer` | There is no question for you. In `Architect draft`, the `## Как я понял задачу` section has no standard fix; see [the section about it](#the-task-understanding-section). |
| Manager reached its step limit | Repeat `planveyor sibling run`. |
| Review returns the work on the same topic again and again | Stop `run` by the steps in [Stop `run` and continue the same plan](#stop-run-and-continue-the-same-plan); Owner decides whether to continue. |
| The review or the evidence is stale | Return to the named role; an old green result does not confirm new changes. |
| There is no single `## Архитектурное ревью` section, or its first line is not `Вердикт: принято.` | Run `planveyor sibling architect`, then `close` again. |
| The index has unrelated files | Sort them out separately; `close` does not clean up or commit unrelated work. |
| A commit is required | Review the `close` preview, then explicitly run and confirm `close --commit`. |
| The documents are not closed yet | Run the named Manager turn or closeout; start the next task after it completes. |
| `Consumer contract требует разбора; готовность не подтверждена.` after `ready` | Check the contract and the engine version with `planveyor --project "$PWD" planveyor_consumer_doctor`; see [Return to work in an existing sibling](#return-to-work-in-an-existing-sibling). |
| `ready` exited with code 0 but without the closeout result | The task is not finished: run the printed next step. |
| The runtime version differs from the sibling | Select the pinned version by [Return to work in an existing sibling](#return-to-work-in-an-existing-sibling) or run the upgrade plan. |
| The upgrade kept a candidate or a backup | On code 3, find the candidate and resolve its actual problems by the steps above; after success, check the upgrade plan and keep the backup until the plan is accepted. Do not replace the original by hand. |

Help is available through the usual `planveyor sibling --help` command. It does not start roles or change the project.

## When an agent runs the pass

This section is for an agent that runs the pass on behalf of Owner. A person does not need to read it.

### Deferred tasks for a new plan

Real findings of the adaptation go through the standard capture; zero findings are allowed.

The skill runs a bounded discovery. A matching row stays unchanged: `status=open`, `plan=null`, `disposition_kind=null`, `disposition_ref=null`, `disposition_commit_oid=null`; the literal `source_ref#item_id` is only plan context. An automatic backlink is forbidden. If there is no match, the absence of matches is recorded without an artificial row. A conflict with an already active plan for the same result requires Architect/Owner triage. A matching open row by itself does not block an ordinary plan: prepare/finalize/backlink are not its preconditions. Real promotion of a row requires the standard promotion writer and exact proof; the V2/K1 port is separate post-release work.

### Guide check and pass trace

Before a fresh init, read the whole guide and match every applicable step against the existing entry point and its help: the literal command or input, the prerequisites, the expected stdout, stderr, exit code, and result, and the action on failure. For the optional upgrade and upstream request branches, state whether they apply or why you skip them. Theoretical readiness does not prove a live pass. During the execution, keep a full private trace of all calls, inputs, stdout/stderr, exit codes, results, and retries; write the public description only after the execution, and replace private paths and credentials in it with `<REDACTED>`. Native session traces are kept separately; the trace extractor is neither a full command trace nor a sanitizer.

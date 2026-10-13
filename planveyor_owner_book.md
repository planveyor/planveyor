# Planveyor Owner guide

**English** · [Русский](planveyor_owner_book.ru.md)

For a project under your own stack, the main path is the permanent [stack sibling runbook](docs/guides/stack-sibling.md). It takes you from a new directory to an accepted adaptation and useful tasks with one command group, `planveyor sibling`:

```sh
planveyor sibling init ~/my-stack
```

Then, in the project directory: plan skill → `architect` → real answers through `answer` → `run` → `close` preview → authorized `close --commit`. After the plan commit, a separate `run` closes out the documents; a new preview and `--commit` accept exactly the prepared documentation changes. `ready` checks the contract, the selected plan, and the closeout; live stack checks remain part of the accepted plan.

## Environment and facade

From the physical Planveyor root, the direct call is `./bin/planveyor`. In a prepared environment, its public executable is available on `PATH` as `planveyor`. The physical path of the facade determines the runtime; `git` and `HEAD` are checked before the first action. You need a prepared, supported Python; Planveyor does not install dependencies and does not rewrite your shell config. Selected live role and Manager commands need a configured, authorized client.

`planveyor sibling --help`, `planveyor_entry_doctor`, and `planveyor_runtime_info` are diagnostics. Doctor and the selected plan pointer do not confirm task acceptance and do not authorize a commit, dispatch, upgrade, or publication. For a low-level command on another project, an explicit `--project` goes before the command. For the `sibling` group, the physical project is derived from the current directory; `init` gets the new path from you, and `upgrade` runs from an outside directory with the project selected explicitly.

## Owner decisions

You choose the project, the task, the stack, the dev target, credentials, and the allowed live mode. Architect asks questions; only your actual answers go into the log. Stack code, checks, and local rules belong to the sibling. Private configuration, secrets, and paths on your machine do not go into the public corpus.

Before `close --commit`, review the current exact set. The flag itself confirms this commit; a green preparation does not grant that permission. The mechanism determines the source version, role sessions, timestamps, and technical hashes. Push, deployment, and sending a public issue each need a separate decision from you.

## Navigation

- [Sibling: creation, tasks, upgrade, and upstream proposal](docs/guides/stack-sibling.md).
- [Launch, network, and role modes](docs/guides/launch-and-role-modes.md).
- [Lifecycle, closeout, and packets](docs/guides/lifecycle-and-packets.md).
- [Checks and their scope](docs/tools/verify_suite.md).
- [Roles](docs/roles/index.md) and [playbooks](docs/playbooks/README.md).

Analysis, decomposition, queue, and custom pipeline remain separate standard routes. Manager does not silently change the selected plan, target, runner, or authentication source; ordinary work with one sibling plan does not need a queue.

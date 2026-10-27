# Launch and role modes

**English** · [Русский](launch-and-role-modes.ru.md)

Planveyor runs from its physical root through the child-only facade. The facade is not loaded into the shell of the calling process and does not change that shell's functions, variables, or working directory.

Before the first public command, check for an available `git`, a physical Planveyor Git checkout, and a `HEAD` that resolves to a commit. The facade runs this preflight before it parses `--project` and before `planveyor_entry_doctor`; doctor cannot restore or bypass a Git environment that failed this check.

## Project selection

Without `--project`, a command works on Planveyor itself. For a consumer repository, pass the absolute canonical path **before** the public command:

```zsh
./bin/planveyor --project /absolute/path/to/consumer \
  planveyor_plan_status_oracle --json docs/plans/<plan>.md
```

The selected consumer must already own its declared contract and bootstrap. `--project` selects only the consumer context: it does not create a contract, a plan, a SID, an interpreter, authentication, or provider readiness.

The facade starts a clean child process in the selected project root. Relative paths in the command resolve inside this project. The parent shell does not change, so each new call needs its own `--project` prefix again. `bin/planveyor` starts the child through `env -i` and `zsh -df`: it drops an inherited `CODEX_HOME` and undeclared tooling variables, but explicitly passes a non-empty `CODEX_THREAD_ID` for plan provenance. Owner may explicitly pass a canonical external `PLANVEYOR_CODEX_HOME`. The facade checks that `PLANVEYOR_CODEX_HOME` and `PLANVEYOR_STATE_ROOT` are outside the product tree; for `HOME`, it requires only an absolute existing directory. Keep authentication and client state outside the product tree.

Ignored process artifacts stay in the selected project root: the selectors `.planveyor.planpath` and `.planveyor.session.*`, the collab records `.planveyor.collab.*`, the init receipts `.planveyor.init_runs/`, and the temporary `.tmp/`. They are not credentials, but you must preserve them separately when you copy or rewrite the project history.

## Quick readback

```zsh
./bin/planveyor planveyor_entry_doctor
./bin/planveyor planveyor_runtime_info
./bin/planveyor planveyor_help
```

This is a local runtime/project readback, not a readiness gate: it does not prove authentication, provider availability, plan admissibility, a SID, Manager dispatch, or a role launch.

### Supported environment

The first version supports one environment: macOS and an activated Python 3.12 environment with Copier 9.18.2 and PyYAML as pinned in `requirements-dev.lock` (for example, a conda environment named `planveyor`). Activate it before role or validation work. The facade selects the first compatible Python 3.10–3.12 found through `PATH`, checking `python3`, `python`, `python3.12`, `python3.11`, then `python3.10`; its helpers use that selected interpreter. A project-local `.planveyor.pybin` does not select the executable. Planveyor does not install or repair dependencies; when a prerequisite is missing, the command stops with a message that says exactly what is needed. The source identity loader technically accepts Python 3.10–3.12, but the supported path is the environment above. A configured agent harness and its usual external authentication are needed by a live command that invokes that harness; Codex and Codex authentication apply only to Codex paths. Doctor, runtime info, and help do not check them. Authentication stays in the usual environment of the client you use; Planveyor does not copy account data, tokens, or local configuration into the repository.

Role work has two more conditions. Codex runs the shell commands of roles in a login shell, which reads your shell profile and may put another Python first in `PATH`. Planveyor passes its own interpreter to the roles in `PYBIN`, so its helpers are not affected. Project scripts, such as the harness of a sibling, may still call a bare `python3`, so Python 3.12 must come first in `PATH` of a login shell too. `TMPDIR` must name an existing directory outside any Git work tree; with `TMPDIR` inside a work tree, the engine tests that need a project root without Git are skipped. Check both before the first role launch:

```zsh
zsh -lc 'python3 --version'
[ -n "$TMPDIR" ] && [ -d "$TMPDIR" ] && echo 'TMPDIR exists'
git -C "$TMPDIR" rev-parse --is-inside-work-tree
```

The first command must print Python 3.12, and the last one must fail with `fatal: not a git repository`. You choose how to put Python 3.12 first in a login shell, for example with the `PATH` order in `~/.zprofile`. Planveyor does not change your shell configuration.

## Sibling contract

Creating a sibling needs an empty new directory and a full Git commit of the source Planveyor. Copier records the public source URL in its answers, but it always takes the template from the local Planveyor checkout from which the command runs: the address is substituted only in the environment of the Copier process. So the selected commit must be on a branch or tag of this checkout, and a new version for a sibling starts with an update of the checkout. The engine and its scripts stay in the external checkout.

```zsh
./bin/planveyor planveyor_consumer_init /absolute/path/to/new-sibling --source-commit <full-40-hex> \
  --author-name "Your Name" --author-email you@example.invalid
./bin/planveyor --project /absolute/path/to/new-sibling planveyor_consumer_doctor
```

Init creates the first commit in the sibling. `--author-name` and `--author-email` set its author and are passed only together; the Git identity from the configuration and environment variables is not used. Without the flags, the commit gets the service author `Planveyor Initializer <planveyor-init@example.invalid>`, and init reports this in a line on stderr.

After a change of the shared contract or the engine, choose a new full commit. The upgrade carries the files over in a separate candidate, checks the marker, the answers, the managed paths, and the local sections, and then creates an upgrade plan inside the sibling with an Architect starting status. The transfer itself does not close this plan and does not start roles.

The `sibling upgrade` output calls this same plan “план адаптации” or “adaptation plan”. This guide calls it an “upgrade plan” to distinguish it from the first stack adaptation plan of a new sibling.

Roles receive `PLANVEYOR_RUNTIME_ROOT` and call the declared Python helpers through `planveyor_runtime_py` of the same facade. This keeps the verified runtime pin; a direct call of the file `scripts/<helper>.py` from a sibling does not pass authority admission.

```zsh
./bin/planveyor --project /absolute/path/to/sibling planveyor_contract_upgrade --source-commit <new-full-40-hex>
```

The low-level `planveyor_contract_upgrade` shown above returns JSON directly on stdout. On success, it has the fields `backup`, `plan`, `notices`, and `warnings`. When it stops with a candidate, it has `candidate`, `problems`, and `resolution`, with exit code 3. After such a stop, the original sibling stays in place, and the backup and the plan are not created yet. The `planveyor sibling upgrade` command captures this JSON. On success, it prints the paths of the backup and the upgrade plan and does not print the notices separately. On code 3, it hides the JSON stdout with the candidate and the problems, while stderr stays visible. The candidate lies next to the sibling in `.<name>-upgrade-<first 12 characters of the new commit>`; a repeated run of the same `sibling upgrade` names the exact path: `candidate path already exists: …`.

In the candidate, resolve the actual conflicts, the `.rej` files, and the changes of local sections. Check the exact diff and that the stack rules and the Reviewer override are preserved. After review, commit the result in the candidate and accept it explicitly with the same source commit:

```zsh
./bin/planveyor --project /absolute/path/to/sibling planveyor_contract_upgrade --source-commit <new-full-40-hex> --accept-candidate
```

Before the next upgrade, check the local plan and commit it together with the other accepted changes of the sibling. Doctor reports a mismatch between the runtime and contract commits; this does not forbid an upgrade of a compatible old API 5 contract to the current commit. Before Copier update, upgrade refuses a range that both removes and adds managed paths, a removed path whose bytes or permissions differ from the old render, a removed path with a protected local section, or a managed path missing from the sibling. A pure deletion of an unchanged, unprotected file can reach Copier and stop with a candidate; review and commit that candidate, then retry with `--accept-candidate`.

## Example: Self-Planveyor

Without `--project`, the child-only facade selects the physical root of Planveyor itself. This is an example of preparation and explicit plan selection, not proof that roles ran.

1. Owner selects a supported Python in the trusted launch environment:

   ```zsh
   ./bin/planveyor planveyor_plan_status_oracle --json docs/plans/<plan>.md
   ```

   Oracle reads only the explicitly passed plan path: it does not read `.planveyor.planpath`, does not choose an active plan, and does not start Manager or the queue.

2. Owner separately selects the plan for the next process steps:

   ```zsh
   ./bin/planveyor planveyor_plan_set docs/plans/<plan>.md
   ./bin/planveyor planveyor_planpath
   ```

   `planveyor_plan_set` saves the raw path to the root-local `.planveyor.planpath` and to the local log `.planveyor.planpath.log`. This records process ownership of the plan choice; it is not a technical role-authorization gate. First pass the existing path to a successful Oracle check, then save the pointer. A later `planveyor_planpath` only reads the last saved non-empty line; it does not check that the path exists and does not materialize a queue or a lifecycle. When the pointer is missing, it suggests `planveyor_plan_set <PLAN_PATH>`; an empty pointer returns `Empty file: <path>` with code 1. An unreadable regular pointer also reaches this message after the shell's read error, with no separate helper diagnostic.

3. Manager initialization is a separate step:

   ```zsh
   ./bin/planveyor planveyor_manager_init
   ```

   This command creates the Manager session. When the Manager SID is missing, recovery points to the same `planveyor_manager_init`. Interpreter preparation, the read-only Oracle check, the plan choice, and the pointer readback do not by themselves prove Manager-to-role execution.

   Before the TUI, switch the session to command approval requests: run `./bin/planveyor planveyor_manager_resume`, type `/permissions`, choose "Ask for approval", and exit, as in [How Planveyor changes itself](learn/self-development.md#a-change-in-planveyor-itself).

4. The normal native/collab TUI starts without `--q`:

   ```zsh
   ./bin/planveyor planveyor_manager_collab_tui
   ```

   This is the live Manager path: after the preflight gates succeed, it passes `MANAGER_CMD=run`. The actual dispatch remains a conditional result of this run. `planveyor_manager_collab_cmd run docs/plans/<plan>.md` is an alternative one-shot live path, not the next required step after the TUI.

   Before the first followups dispatch, you can explicitly continue one active ordinary `plan.v2` cycle after four green general collectors:

   ```zsh
   ./bin/planveyor planveyor_manager_collab_cmd run docs/plans/<plan>.md --followups-capture-cycle-id <UUIDv4>
   ```

   This is a one-shot path with an existing Manager SID. The plan and the UUID are set explicitly; the pointer and the queue do not change. A fresh docs closeout admission checks the terminal semantic identity, the source, the receipts, the object maps, and the Git delta. An existing checkpoint re-checks the retained JSON before publication; then only the Architect → Coder → Planner → Reviewer followups run. A progressed, blocked, or ambiguous cycle, or a drift, leads to a bounded stop without a new `begin` and without an automatic init. The admission does not replace the final closeout proof.

5. The queue is a separate advanced branch: first materialize the queue, then run the queue TUI or the existing one-shot command.

   ```zsh
   ./bin/planveyor planveyor_q_set docs/plans/<plan>.md --for-manager-mode manager-collab
   ./bin/planveyor planveyor_manager_collab_tui --q
   # or
   ./bin/planveyor planveyor_manager_collab_cmd run Q
   ```

Authentication and the optional `PLANVEYOR_CODEX_HOME` stay in the external environment. Root-local pointers are not credentials, an external home, or a target-local profile. The `default` and `planveyor` profiles read the shared root corpus; `target-local` is possible only through a declared consumer contract, without a hidden fallback.

## Roles and entry points

A role reads the current explicit plan, the related contract documents, and its own prompt. The general order of work: Architect → Planner → Coder → Reviewer → Architect acceptance → closeout. With `COMMIT_POLICY=native_existing`, Architect performs the closeout; in `planveyor sibling architect` and `run`, `COMMIT_POLICY=human_explicit` applies, and a separate `planveyor sibling close --commit` performs the closeout after a preview. Manager in the TUI runs with `native_existing`, both through `planveyor_manager_collab_tui` and, in a sibling, through `planveyor sibling tui`, which calls it. The plan remains the source of truth for the status and the next allowed step.

| Task | Command |
| --- | --- |
| Initialize Manager | `./bin/planveyor planveyor_manager_init` |
| Run single-plan Manager collab in the live TUI | `./bin/planveyor planveyor_manager_collab_tui` |
| Run the collab queue one-shot | `./bin/planveyor planveyor_manager_collab_cmd run Q` |
| Open the custom pipeline TUI | `./bin/planveyor planveyor_manager_custom_pipeline_tui --no-alt-screen` |
| Run the custom queue one-shot | `./bin/planveyor planveyor_manager_custom_pipeline_cmd run Q` |
| Resume the Manager session | `./bin/planveyor planveyor_manager_resume` |

The table shows the commands for the Planveyor root, where the engine and the project are one checkout. If the commands come from one Planveyor checkout and the project is another checkout, pass `--project <project>` to every command, in Self-Planveyor too: without it, a low-level command takes the engine itself as the project, from whatever directory it is called.

In a sibling, the same Manager window is TUI mode, the main path of the [stack sibling guide](stack-sibling.md#two-ways-to-work-on-a-plan). Pass the sibling to the low-level commands with `--project`, run `planveyor_manager_init`, switch the session to command approval requests as the guide describes, and then open the window with `planveyor sibling tui`; do not change files or the index between these steps. `planveyor sibling tui` checks the selected plan and the session and calls `planveyor_manager_collab_tui`. The roles are nested subagents of the Manager session and keep their memory while the window is open. After a commit, `planveyor sibling run` and `planveyor sibling tui` start a new Manager with new roles themselves; `tui` creates the new session without command approval requests, so first create the new session yourself and switch it to command approval requests. Started directly, `planveyor_manager_collab_tui` and `planveyor_manager_collab_cmd` refuse with `receipt_authority_mismatch`, and the work continues only with a new session. In the Planveyor root, the session is not bound to HEAD, and the earlier session can be continued. The separate `planveyor sibling …` commands are manual console mode of the same guide.

To resume an individual role, use the explicit command from `planveyor_help`, for example `planveyor_arch_resume`, `planveyor_planner_resume`, `planveyor_coder_resume`, `planveyor_reviewer_resume`, `planveyor_reviewer_code_risk_resume`, or `planveyor_reviewer_code_contracts_resume`.

The custom pipeline needs separate SIDs for Manager and five role lanes:

```zsh
planveyor_manager_init
planveyor_arch_init
planveyor_planner_init
planveyor_coder_init
planveyor_reviewer_code_risk_init
planveyor_reviewer_code_contracts_init
```

`planveyor_reviewer_init` does not replace either `planveyor_reviewer_code_risk_init` or `planveyor_reviewer_code_contracts_init`. The custom TUI is also a live supervision/dispatch path and does not prove that every role will start.

`planveyor_manager_init` selects an allowed mode before dispatch. Manager does not silently switch the mode, runner, project, or plan because of the queue or an old session state. The direct ZCode Manager route is described in `docs/tools/prompts/zcode/manager_pipeline.md`; it is a transport overlay that keeps the Custom, native/collab, resume, TUI, and command entrypoints. In the first version, it works only in the Planveyor root: its bootstrap files from `.zcode/` are not delivered to a sibling, and this route is not supported in a sibling.

## Codex setup

Both supported sibling modes use Codex CLI: TUI mode (`planveyor sibling tui`, which calls `planveyor_manager_collab_tui`) and manual console mode (`planveyor sibling architect` and `planveyor sibling run`). In TUI mode and in `run`, Manager starts five native Codex subagents. Planveyor starts Codex with the home from `PLANVEYOR_CODEX_HOME`, or with `~/.codex` when the variable is not set, and takes the settings from `config.toml` in that directory. In a trusted project, Codex also applies the project `.codex/` directory; see [Project `.codex/` directory](#project-codex-directory). Planveyor itself does not create or change these files: you configure everything described below.

Single-role launches and the custom pipeline keep the existing runner choice: Planner and both Reviewer lanes allow `claude`; Architect, Coder, and Manager allow `codex`. The choice is set with `planveyor_runner_set <role> <runner>`; both Reviewer lanes use the choice of the `reviewer` role. Claude needs the installed CLI and its usual external authentication; `PLANVEYOR_CLAUDE_COMMAND`, `PLANVEYOR_CLAUDE_MODEL`, and `PLANVEYOR_CLAUDE_EFFORT` set the command, the model, and the effort. This choice does not change the Codex subagents of collab and does not add a Claude transport to `sibling run`.

### Regular role mode

Single roles (`planveyor_arch`, `planveyor_planner`, `planveyor_coder`, `planveyor_reviewer`) and the custom pipeline work in sessions that `*_init` opens. `planveyor sibling architect` opens such a session for Architect too. With the `codex` runner, each such session is a separate `codex exec`; Planveyor does not choose a model by default. The model and the reasoning effort come from the top level of `config.toml`:

```toml
model = "gpt-6.1-sol"
model_reasoning_effort = "ultra"
```

Set the effort explicitly: `gpt-6.1-sol` defaults to `low`. This mode does not need the `[agents.*]` roles.

### Manager collab: `[agents.*]` roles

Owner needs Manager collab (`planveyor_manager_collab_tui`, `planveyor_manager_collab_cmd`) even when running the roles by hand: it runs the docs closeout of a plan and the decomposition and analysis waves. Manager itself is the main Codex session on the model from the top level of `config.toml`. It starts the roles as Codex subagents: `spawn_agent(..., agent_type=<type>)`. The Manager prompt requests the following five `agent_type` values; register them as `[agents.<name>]` roles in your Codex configuration before running this route:

| `agent_type` | Whom Manager starts |
|---|---|
| `architect` | Architect |
| `planner` | Planner |
| `coder` | Coder |
| `reviewer_code_risk` | Reviewer, risk lane |
| `reviewer_code_contracts` | Reviewer, contracts lane |

Merge mode (`planveyor_manager_collab_tui --merge`) starts the same roles except `planner`.

The roles can start the built-in agents themselves, for example `explorer`. To keep these agents on the model you chose, add entries for `default`, `worker`, and `explorer` in the same format.

A role has two fields: `description` and `config_file`, the path to the role file. A relative path is resolved from the directory of this `config.toml`, and the file must exist. The role file sets `model` and `model_reasoning_effort`. `developer_instructions` are optional: Manager passes the task and the role prompt (`PROMPT_FILE`) in a message.

Manager keeps five role threads open for the whole run. Set `max_concurrent_threads_per_session` to at least 6: by default, Codex may allow fewer, and the main thread may count toward this limit. If the limit is too low, Manager stops with `collab thread limit reached`. The roles may also start built-in agents, so leave a margin above this minimum. The Codex multi-agent tools must be enabled (`[agents] enabled`, `true` by default); otherwise, Manager stops with `Codex collab is disabled/unavailable`.

A neutral example of `config.toml` in the Codex home:

```toml
model = "gpt-6.1-sol"
model_reasoning_effort = "ultra"

[agents]
enabled = true
max_concurrent_threads_per_session = 6

[agents.architect]
description = "Planveyor Architect"
config_file = "agents/architect.toml"

[agents.planner]
description = "Planveyor Planner"
config_file = "agents/planner.toml"

[agents.coder]
description = "Planveyor Coder"
config_file = "agents/coder.toml"

[agents.reviewer_code_risk]
description = "Planveyor Reviewer, risk lane"
config_file = "agents/reviewer_code_risk.toml"

[agents.reviewer_code_contracts]
description = "Planveyor Reviewer, contracts lane"
config_file = "agents/reviewer_code_contracts.toml"

[agents.default]
description = "Codex default agent"
config_file = "agents/default.toml"

[agents.worker]
description = "Codex worker agent"
config_file = "agents/worker.toml"

[agents.explorer]
description = "Codex explorer agent"
config_file = "agents/explorer.toml"
```

The role file `agents/architect.toml` sits in the `agents/` subdirectory beside `config.toml`; the other seven files use the same format, with their own `name` and `description`:

```toml
name = "architect"
description = "Planveyor Architect"
model = "gpt-6.1-sol"
model_reasoning_effort = "ultra"
```

### Model and reasoning effort

The default recommendation is GPT-6.1 Sol (`gpt-6.1-sol`) with the `ultra` or `max` effort, never below `xhigh`, for every session of the pipeline. Each session takes its model from its own place:

| Session | Model and effort |
| --- | --- |
| Architect in `planveyor sibling architect`; single-role launches and the custom pipeline with the `codex` runner | The top level of `config.toml` |
| Manager in TUI mode, in `planveyor sibling run`, and in other Manager collab launches | The top level of `config.toml` |
| The five roles that Manager starts | Their `[agents.<agent_type>]` role files |
| The built-in agents that the roles start | The `[agents.default]`, `[agents.worker]`, and `[agents.explorer]` role files |
| The `$planveyor-plan-draft` skill | The model of your chat |

A different model for a single role is set in its file.

### Project `.codex/` directory

You can set the models for one project in its own `.codex/` directory: `.codex/config.toml` in the project root and the role files in `.codex/agents/`, in the same format as above. Codex applies this directory only in a trusted project. The interactive Codex asks whether to trust a new folder on its first start there and saves the answer in `config.toml` of the Codex home that this chat uses. Roles use this answer only when they run with the same Codex home. Values from the project file take precedence over the Codex home for the sessions of this project. Settings that the project file does not set, such as network access, come from the Codex home.

The sibling template does not ignore this directory. Exclude it from Git with a local rule that stays out of commits; run this from the project root:

```zsh
mkdir -p .codex/agents
printf '%s\n' '.codex/' >> "$(git rev-parse --git-path info/exclude)"
```

Planveyor does not create this directory.

### Check the models in use

The role name does not prove the model. Codex writes each session to a `rollout-*.jsonl` file under `sessions/` in its Codex home. The `session_meta` record holds the launch directory, the source, and the role of an agent. The `turn_context` records hold the model and the effort of each turn. These are local files of Codex itself, so the check needs no other tools.

Before the first role launch, such as `planveyor sibling architect`, `run`, or the Manager window, mark the time:

```zsh
touch "$TMPDIR/planveyor-models.start"
```

While the command runs or after it, run this from the project root:

```zsh
python3 -I - "$(pwd -P)" "${PLANVEYOR_CODEX_HOME:-$HOME/.codex}/sessions" "$TMPDIR/planveyor-models.start" <<'PY'
import json, pathlib, sys
from datetime import datetime

project, sessions, marker = sys.argv[1], pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3])
start = marker.stat().st_mtime
for path in sorted(sessions.rglob("rollout-*.jsonl")):
    if path.stat().st_mtime < start:
        continue
    meta, seen = None, set()
    with path.open(encoding="utf-8", errors="replace") as lines:
        for line in lines:
            try:
                item = json.loads(line)
            except ValueError:
                continue
            payload = item.get("payload") or {}
            if item.get("type") == "session_meta" and meta is None:
                meta = payload
            elif item.get("type") == "turn_context":
                try:
                    turn_time = datetime.fromisoformat(item.get("timestamp", "").replace("Z", "+00:00"))
                except (TypeError, ValueError, AttributeError):
                    continue
                if turn_time.tzinfo is not None and turn_time.timestamp() >= start:
                    seen.add(f"{payload.get('model')} / {payload.get('effort')}")
    if meta and meta.get("cwd") == project and seen:
        role = meta.get("agent_role") or ("main" if meta.get("source") == "exec" else "chat")
        print(role, ", ".join(sorted(seen)))
PY
```

The script prints one line per session of this project: the role, the model, and the effort. It does not print the contents of the sessions. A `main` line is a main `codex exec` session in this project. Planveyor uses it for Architect in `planveyor sibling architect`, Manager in `planveyor sibling run`, or a single-role session. The label alone does not prove that Planveyor started it. The roles and the built-in agents appear under their `agent_type`. A `chat` line is your interactive chat in this folder, with its own model.

The check is needed because the settings of the Codex home apply even when you have forgotten about them. For example, an `[agents.architect]` entry made earlier for another project silently sets its own model for Architect. If a model differs from your configuration, stop and fix the configuration yourself. A likely cause is a project `.codex/` that Codex did not apply because the folder is not trusted.

### Manager task names

Manager creates the subagents under fixed names: `/root/architect_sol_xhigh_v2`, `/root/planner_terra_ultra_v2`, `/root/coder_terra_ultra_v2`, `/root/reviewer_code_risk_sol_xhigh_v2`, `/root/reviewer_code_contracts_sol_xhigh_v2`. The parts `sol`, `terra`, `xhigh`, and `ultra` repeat the models on which the route was debugged, but they are only names: the `[agents.*]` roles set the model and the effort. You do not need to change the names; the engine accepts only these.

### Caveat: the Codex environment reaches the roles

Manager and the roles use the selected Codex home (`PLANVEYOR_CODEX_HOME`, or `~/.codex` when it is unset). Global instructions, enabled memory, and user skills affected role context in observed Codex runs; their discovery is Codex behavior, not a guarantee checked by Planveyor. Inspect the selected home and user skills before launch: rules and memory written for other projects can change how the roles behave.

To separate them, set up a separate Codex home for Planveyor: create a directory outside the Planveyor checkout, sign in to Codex with it (`CODEX_HOME=<directory> codex login`), put a `config.toml` there based on the example above, and export the path as `PLANVEYOR_CODEX_HOME` in the shell from which you call the facade. Network access for the roles is then enabled in the config of this directory.

### Access to the dev environment

In the stack brief, choose roles with network access in the sandbox or live commands run by a person, following the [existing dev environment contract](../_template_stack_brief.md) (in Russian). When the roles run the live targets themselves, network access in their sandbox is a prerequisite. Owner sets it before the first `run`, in `config.toml` of the selected home:

```toml
[sandbox_workspace_write]
network_access = true
```

It applies to the `workspace-write` sandbox of this home; the file system stays in the sandbox. Roles call the accepted stack commands, which check the dev target and the permissions before writing; only the harness reads secrets. In the operator-only variant, the role hands over a specific command, and a person returns its actual result. Planveyor does not configure the network, the home, or the environment automatically.

## Runtime boundaries

- Use the facade for launch, init, resume, and TUI.
- Run a direct helper only when the current plan or guide explicitly names it as a read-only check.
- Do not present a static lint, a prompt readback, or provider availability as proof of a real Manager-to-role launch.
- Target-local contracts must be declared explicitly by the selected consumer and plan; the shared `default`/`planveyor` corpus does not substitute a hidden product profile.

The next operational steps are in [lifecycle-and-packets.md](lifecycle-and-packets.md).

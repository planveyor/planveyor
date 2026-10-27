# Agent harnesses

**English** · [Русский](harnesses.ru.md)

An agent harness is the program that wraps a model and runs a role session: it reads and edits files, runs commands, and keeps the sandbox. Codex CLI, Claude Code, and ZCode are agent harnesses. Do not confuse an agent harness with the stack harness: the scripts of your project that build it, deploy it to the dev environment, and run the stack tests.

You install the agent harness, sign in, and configure it yourself. Planveyor starts it with your configuration and does not create or change that configuration.

## Support in the first version

| Route | Agent harness |
| --- | --- |
| Sibling, TUI mode: the Manager window `planveyor sibling tui` | Codex CLI |
| Sibling, manual console mode: `planveyor sibling architect` and `planveyor sibling run` | Codex CLI |
| Manager collab: `planveyor_manager_collab_tui`, `planveyor_manager_collab_cmd` | Codex CLI |
| Single-role launch and custom pipeline | Codex CLI; Claude Code for Planner and both Reviewer lanes |
| Direct ZCode Manager route | ZCode, only in the Planveyor root |
| Chat with the plan skill in a sibling | Codex (`$planveyor-plan-draft`) or ZCode (`/planveyor-plan-draft`) |

The first version supports no other agent harnesses. We will extend the support after the release.

## Codex CLI

Codex CLI serves both modes of a sibling; their paths differ, see [Two ways to work on a plan](stack-sibling.md#two-ways-to-work-on-a-plan).

- **TUI mode.** `planveyor sibling tui` opens the interactive Codex CLI window of Manager for the whole plan; it calls `planveyor_manager_collab_tui`. The roles are nested Codex subagents of this session and live while the window is open. Nested subagents in an interactive window are a feature of Codex CLI.
- **Manual console mode.** `planveyor sibling architect` runs Architect in its own session, a separate `codex exec`. Each `planveyor sibling run` is one non-interactive turn of Manager collab, where Manager starts the five roles as Codex subagents and exits after the accepted Arch Review.

Planveyor starts Codex with the Codex home from `PLANVEYOR_CODEX_HOME`, or with `~/.codex` when the variable is not set. If the `codex` command is not on `PATH`, a role command stops with `Codex CLI is required; install it and authenticate in the consumer-owned home first`.

The settings are described in the [Codex setup](launch-and-role-modes.md#codex-setup) section of the launch guide; the [last section](#what-you-configure) of this page lists its parts.

## Claude Code and the runner choice

Planveyor stores the choice of the agent harness for a role as the runner of the role. The `planveyor_runner_set <role> <runner>` command sets it. These pairs are allowed:

| Role | Runner |
| --- | --- |
| Architect, Coder, Manager | `codex` |
| Planner, Reviewer | `codex` or `claude` |

Every role uses `codex` by default. Both Reviewer lanes take the choice of the `reviewer` role. The choice is saved in `.planveyor.runner.<role>` in the project root and applies only to that checkout. `planveyor_runner <role>` shows it:

```zsh
./bin/planveyor planveyor_runner_set planner claude
./bin/planveyor planveyor_runner planner
```

For a sibling, pass `--project /absolute/path/to/sibling` before the command, as in [Project selection](launch-and-role-modes.md#project-selection).

The choice applies where a wrapper starts the role: single-role launches and the custom pipeline. It does not change the Codex subagents of Manager collab and does not add Claude Code to either sibling mode: in the first version, Claude Code works only for Planner and Reviewer, in a single-role launch and in the custom pipeline.

Claude Code needs the installed CLI and its usual sign-in. Planveyor reads three variables:

- `PLANVEYOR_CLAUDE_COMMAND`: the command name or absolute path, `claude` by default;
- `PLANVEYOR_CLAUDE_MODEL`: passed to Claude Code as `--model`;
- `PLANVEYOR_CLAUDE_EFFORT`: passed as `--effort`.

Planveyor starts Claude Code with `--permission-mode acceptEdits`. Other permissions come from the settings of Claude Code, and so does the model when `PLANVEYOR_CLAUDE_MODEL` is not set. If the command is not found, the role stops with `Claude CLI is unavailable; configure the consumer provider first`.

## ZCode

ZCode has its own Manager route, and it works only in a ZCode session opened in the physical Planveyor root (Self-Planveyor). Two files of the root serve it: `.zcode/commands/manager-init.md` gives the `/manager-init` command, and `.zcode/agents/planveyor-role-agent.md` defines the role agent. `/manager-init` prepares the session as Manager, and the next message `MANAGER_CMD=run <PLAN_PATH>` starts the work on the plan. The transport rules are in the overlay [`docs/tools/prompts/zcode/manager_pipeline.md`](../tools/prompts/zcode/manager_pipeline.md); the Manager contract stays the same as in collab. The overlay itself records `live_zcode_state=not_run`: it does not attest a live ZCode run.

A sibling does not receive the `.zcode/` files, so this route is not supported there, and Manager in a sibling runs through the facade. In a sibling, ZCode fits a regular chat with the `/planveyor-plan-draft` skill. `planveyor_runner_set` does not accept ZCode as a runner. Planveyor does not set the model or the sign-in of ZCode.

## What you configure

Codex CLI, by the sections of the launch guide:

- the sign-in in the selected Codex home, and a separate Codex home for Planveyor if you need one: [Caveat: the Codex environment reaches the roles](launch-and-role-modes.md#caveat-the-codex-environment-reaches-the-roles);
- the model and the reasoning effort of the sessions: [Regular role mode](launch-and-role-modes.md#regular-role-mode) and [Model and reasoning effort](launch-and-role-modes.md#model-and-reasoning-effort);
- the five `[agents.*]` roles for Manager collab: [Manager collab: `[agents.*]` roles](launch-and-role-modes.md#manager-collab-agents-roles);
- the project `.codex/` directory and the trust in the project folder: [Project `.codex/` directory](launch-and-role-modes.md#project-codex-directory);
- network in the role sandbox: [Access to the dev environment](launch-and-role-modes.md#access-to-the-dev-environment); the sandbox of a Codex chat that runs the commands for you: [One-time setup](stack-sibling.md#one-time-setup-environment-and-project-creation);
- the check of the models in use: [Check the models in use](launch-and-role-modes.md#check-the-models-in-use).

Claude Code: the sign-in and the permissions in Claude Code itself, and the three `PLANVEYOR_CLAUDE_*` variables from the [section above](#claude-code-and-the-runner-choice). It does not need `[agents.*]` roles. The model check of the launch guide reads only Codex sessions.

ZCode: the files of the route are already in the Planveyor root.

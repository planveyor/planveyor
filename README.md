# Planveyor

**English** · [Русский](README.ru.md)

Planveyor is a standalone, repo-backed toolkit for plan-driven work with coding agents in the Architect, Planner, Coder, Reviewer, and Manager roles. It keeps plans, reviews, follow-ups, packet records, and process guidance as inspectable repository artifacts.

## Start here

First install Planveyor as described in [Install Planveyor](docs/guides/install.md): the requirements, an example environment, and the checks. [Agent harnesses](docs/guides/harnesses.md) shows which agent harness each route uses.

For a project under your own stack, follow the permanent [stack sibling runbook](docs/guides/stack-sibling.md): create the sibling, draft a plan, and run it in one of two modes. TUI mode, the main path, is one Manager window for the whole plan, where Architect makes the commits. In manual console mode, you answer Architect, run Manager, and preview and explicitly commit each exact set with separate commands. These human commands use one group, `planveyor sibling`; project, selected plan and source version are discovered from the chosen facade and project context.

Run commands from the Planveyor root through the child-only facade:

```zsh
./bin/planveyor planveyor_entry_doctor
./bin/planveyor planveyor_runtime_info
./bin/planveyor planveyor_help
```

The facade discovers its own root from `bin/planveyor`; it does not require a checkout at a fixed home-directory path. Before any public command, confirm an executable `git`, a physical Planveyor Git checkout, and a `HEAD` that resolves to a commit: this preflight runs before `--project` and before doctor. A supported Python is needed to load the facade source identity. A configured agent harness and its usual external authentication are needed only by a live role or Manager command that invokes that harness; Codex and Codex authentication apply only to Codex paths. Doctor, runtime info, and help do not check them. Set `PLANVEYOR_CODEX_HOME` only when you explicitly need an external Codex-home location.

Do not source implementation shell files into a parent shell. The public command contract is the facade above.

`planveyor_entry_doctor` and `planveyor_runtime_info` are local readbacks, not proof of consumer contract, plan admission, session ID, authentication, provider availability, or role dispatch. For the supported interpreter, explicit-plan oracle, plan pointer, Manager SID, live TUI, and separate queue sequence, use [Launch and role modes](docs/guides/launch-and-role-modes.md). Manager collab also needs five agent roles in your Codex config; see [Codex setup](docs/guides/launch-and-role-modes.md#codex-setup).

## Supported verification environment

The first release supports one environment: macOS with an activated Python 3.12 environment that contains Copier 9.18.2 and PyYAML as pinned in `requirements-dev.lock`, plus Git, zsh, ripgrep, and `make` on `PATH`. Prepare that environment yourself (for example, a conda environment named `planveyor` with `make bootstrap-python` run inside it) and activate it before calling `bin/planveyor` or `make`: Planveyor uses the `python3` found on `PATH`. It never installs or repairs dependencies; a missing prerequisite stops the command with an error that names it. The source-identity loader technically accepts Python 3.10–3.12, but the environment above is the supported path. Support for other Python versions is planned after the first release.

For local verification, `make verify` is the fast default route. `make test-scripts` is direct canonical full discovery, while `make verify-full` is the alternative aggregate full route; use one of those full routes for a single full claim, not both. Windows and Linux native validation have not been completed and are not supported by this statement.

The first hosted CI run on the release commit, [run 41122296894](https://github.com/planveyor/planveyor/actions/runs/41122296894), used a GitHub macOS runner with Python 3.10 and 3.12, 14 shards for each version. The run took 3 h 44 min, and 8 of its 28 test jobs failed. The logs show three groups of failures. Six tests in `test_sibling_runbook` failed on both Python versions: they compare the interpreter path literally and expect `…/bin/python`, the path the runner starts the tests with, while the product writes `…/bin/python3.10` or `…/bin/python3.12` from the same installation. A dashboard test in `test_planveyor_bare_entrypoints` failed on both versions: the product shows the time in the machine's time zone, the test expects UTC+3, and the runner works in UTC. In these two groups, the test's expectation depends on the machine. Two more tests exceeded their time limits, on Python 3.12 only: the 5-second threshold in `test_planveyor_init_capture` (6.3 seconds on the runner) and the 120-second timeout for `sibling close --commit` in `test_contract_authority_shell`. Whether the runner's speed or a slowdown in the product caused this has not been established. Before the release, the full suite passed locally on macOS with Python 3.12: 3517 of 3517 tests. Next come an analysis of the failures and a rework of the CI workflow in several small plans; this is item [F5](docs/release_backlog.md#f5) of the First-release backlog (in Russian).

## What is included

- Role definitions, prompts, and playbooks for a plan-first lifecycle.
- Plan, code-draft, review, follow-up, and process-improvement templates.
- Local validation tools and lifecycle gates.
- Rollout and upstream-packet carriers for work that crosses repository boundaries.
- Skills that help a coding agent create and route Planveyor artifacts.
- A step-by-step guide to create a sibling repository for your stack, set it up, and work in it.

## Working lifecycle

1. Create or choose an explicit plan.
2. Check its status and lint it before execution.
3. Run the assigned role or Manager mode with bounded scope and current evidence.
4. Review the exact revision range and resolve required follow-up work.
5. Record fresh post-merge evidence; when the change alters the shared contract or engine behaviour, add a contract notice so siblings adopt it through an upgrade.

The focused public guides are:

- [Install Planveyor](docs/guides/install.md)
- [Stack sibling: create, set up, and work](docs/guides/stack-sibling.md)
- [Launch and role modes](docs/guides/launch-and-role-modes.md)
- [Agent harnesses](docs/guides/harnesses.md)
- [Lifecycle and packets](docs/guides/lifecycle-and-packets.md)
- [Golden paths](docs/guides/golden_paths.md)
- [Owner guide](planveyor_owner_book.md)
- [How Planveyor works](docs/guides/learn/README.md): the learning section
- [Verification suite](docs/tools/verify_suite.md)
- [First-release backlog](docs/release_backlog.md)
- [Role definitions](docs/roles/index.md)
- [Playbooks](docs/playbooks/)

## Repository layout

- `bin/` — public Planveyor command facade.
- `docs/roles/` — responsibilities and handoff boundaries.
- `docs/tools/prompts/` — shared role and Manager prompts.
- `docs/playbooks/` — detailed process guidance.
- `docs/plans/`, `docs/code_drafts/`, `docs/reviews/` — lifecycle templates and carriers.
- `docs/followups/`, `docs/process_improvements/` — durable outstanding-work and improvement records.
- `docs/rollout_packets/`, `docs/upstream_packets/` — cross-repository transfer templates.
- `skills/` — agent-facing workflow instructions. Init delivers them to a sibling as `.agents/skills/`, where Codex and ZCode find them. To use them in another repository, copy `skills/<name>/` into `$HOME/.agents/skills/`; do not symlink.

## Target-local boundary

The root corpus supplies public process guidance. A consumer repository owns its application stack, tests, credentials, integration settings, UI modes, and any `target-local` profile. Planveyor stops at that boundary when the target-local contract is missing; it does not create a substitute profile or copy private configuration into this repository.

## Contributing and security

Keep changes small, public-safe, and supported by the relevant validation. Read [CONTRIBUTING.md](CONTRIBUTING.md) before proposing a change and [SECURITY.md](SECURITY.md) before reporting a security issue.

## Contact

Contacts, including for companies and collaboration, are on the project website: [planveyor.dev](https://planveyor.dev/#contacts).

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE).

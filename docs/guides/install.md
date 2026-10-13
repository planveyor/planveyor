# Install Planveyor

**English** · [Русский](install.ru.md)

This guide takes you from the download to a checked Planveyor checkout from which you can create the first sibling. You prepare the environment yourself: Planveyor does not install, update, or repair anything. When a prerequisite is missing, the command names it and stops.

## 1. Requirements

The first version supports one environment:

- macOS;
- Git, zsh, ripgrep (`rg`), and `make` on `PATH`; on macOS, Git and `make` come with the Xcode Command Line Tools;
- an activated Python 3.12 environment with the packages pinned in `requirements-dev.lock`, including Copier 9.18.2 and PyYAML 6.0.3.

Check the tools:

```zsh
git --version
zsh --version
rg --version
make --version
```

Windows, Linux, and Python versions other than 3.12 are not supported in the first version.

## 2. Clone the repository

```zsh
git clone https://github.com/planveyor/planveyor.git
cd planveyor
```

The checkout can lie in any directory: the facade finds its root from the path of `bin/planveyor`. Before every command, the facade checks that `git` runs, that the checkout has Git metadata, and that `HEAD` resolves to a commit. In a copy without Git metadata, such as an unpacked archive, the command stops with `runtime Git preflight failed`.

Do not leave uncommitted changes or untracked files in the checkout: `planveyor sibling init` and `upgrade` refuse a checkout that has them.

## 3. Python environment

The environment needs Python 3.12 and must stay activated while you work with Planveyor: the facade uses the first Python 3.10–3.12 it finds on `PATH`, checking `python3`, `python`, `python3.12`, `python3.11`, and `python3.10` in this order; with the environment activated, that is its `python3`. Any way to create the environment works if the requirements are met.

### Example: conda

```zsh
conda create -n planveyor python=3.12
conda activate planveyor
```

### Install the pinned packages

In the activated environment, run this once from the root of the checkout:

```zsh
make bootstrap-python
```

The target selects the interpreter in this order: `PYBIN` when it is set, the `python` of the active conda environment, then the first `python3` on `PATH`. It stops when the version is outside 3.10–3.12; otherwise, it installs the packages from `requirements-dev.lock` with `pip`. The facade does not read `PYBIN`, so leave it unset or point it to the same environment.

## 4. Make the command available

From the root of the checkout, call the facade directly:

```zsh
./bin/planveyor planveyor_help
```

To call it as `planveyor` in the current tab, put the checkout on `PATH` from its root:

```zsh
export PATH="$PWD/bin:$PATH"
```

This line does not change your shell configuration, and a new tab needs it again. No separate command installer is needed. Do not link `bin/planveyor` into another directory: the facade refuses to start through a symbolic link.

## 5. Check the installation

```zsh
./bin/planveyor planveyor_entry_doctor
./bin/planveyor planveyor_runtime_info
./bin/planveyor planveyor_help
make verify
```

`planveyor_runtime_info` prints the runtime root, the project root, the source kind, and the Python that the facade uses. `planveyor_entry_doctor` also checks that the command runs through the facade and prints the same lines:

```text
runtime_root=/path/to/planveyor
project_root=/path/to/planveyor
source_state=pinned
source_kind=git
python_executable=/path/to/envs/planveyor/bin/python3.12
child_shell=planveyor-child-shell.v1
```

Check that `python_executable` points to the environment from step 3. `planveyor_help` lists the commands and shows the runner of each role, that is, its agent harness. `make verify` runs the fast route of the [verification suite](../tools/verify_suite.md): read-only integrity checks of the checkout. It ends with `VERDICT: GREEN` when they pass.

These checks show that the facade starts, finds the checkout and the Python of your environment, and that the checkout passes the integrity checks. They do not check an agent harness, its sign-in, or a role launch: only the commands that start roles need them.

## 6. Environment for roles

Roles have two more conditions. Python 3.12 must come first on `PATH` in a login shell too: Codex runs the commands of roles there, and the stack harness of a sibling may call a bare `python3`. `TMPDIR` must name an existing directory outside any Git work tree. The commands that check both are in the [Supported environment](launch-and-role-modes.md#supported-environment) section of the launch guide.

## 7. Agent harness

Roles work in an agent harness. The sibling route uses Codex CLI: install it, sign in, and configure the roles as described in [Codex setup](launch-and-role-modes.md#codex-setup). Which agent harness each route uses, and what you configure for it, is described in [Agent harnesses](harnesses.md).

## 8. Next: the first sibling

Create the first sibling as described in the [stack sibling guide](stack-sibling.md#one-time-setup-environment-and-project-creation).

Planveyor does not update itself. Update the checkout in your usual way, and move a sibling to the new version as described in [Get a new Planveyor version](stack-sibling.md#get-a-new-planveyor-version).

## If a command stops

| Message | What to do |
| --- | --- |
| `runtime Git preflight failed: category=missing_git` | Put `git` on `PATH`. |
| `runtime Git preflight failed: category=missing_repo` | Use the Git clone from step 2. |
| `ripgrep (rg) is required` or `zsh is required` | Put the named tool on `PATH`. |
| `no Python 3.10-3.12 found on PATH` | Activate the environment from step 3. |
| `Missing Copier 9.18.2`, `Copier 9.18.2 is required`, or `Missing PyYAML` | Run `make bootstrap-python` in the activated environment. |
| `Выбранный runtime содержит незакоммиченные изменения` (the selected runtime has uncommitted changes) | Commit the changes and untracked files of the Planveyor checkout or move them out of it. |

After the fix, repeat the same command.

#!/usr/bin/env python3
from __future__ import annotations

"""Regression coverage for bare planveyor entrypoints.

Why: protects the owner convenience layer (`Codex !` / fresh `zsh -c`) without
turning Manager/Architect runtime into a hard dependency on installed PATH shims.
"""

import os
import copy
import json
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parent.parent
PLANVEYOR_SCRIPT = REPO_ROOT / "scripts" / "planveyor.zsh"
AUTHORITY_BRIDGE_RUNTIME_FILES = (
    REPO_ROOT / "scripts" / "contract_authority_bootstrap.py",
    REPO_ROOT / "scripts" / "contract_authority_shell_loader.zsh",
    REPO_ROOT / "scripts" / "contract_authority_children.py",
    REPO_ROOT / "scripts" / "contract_authority_bridge.py",
    REPO_ROOT / "scripts" / "contract_authority_context.py",
    REPO_ROOT / "scripts" / "contract_authority_runtime.py",
    REPO_ROOT / "scripts" / "contract_authority_snapshot.py",
    REPO_ROOT / "scripts" / "fs_object_identity.py",
)
OWNER_RUNBOOK = REPO_ROOT / "docs" / "tools" / "owner_runbook_codex.md"
OWNER_RUNBOOK_RU = REPO_ROOT / "docs" / "tools" / "owner_runbook_codex.ru.md"
LAUNCH_GUIDE = REPO_ROOT / "docs" / "guides" / "launch-and-role-modes.md"
LAUNCH_GUIDE_RU = REPO_ROOT / "docs" / "guides" / "launch-and-role-modes.ru.md"
PROJECT_README = REPO_ROOT / "README.md"
PROJECT_README_RU = REPO_ROOT / "README.ru.md"
OWNER_BOOK = REPO_ROOT / "planveyor_owner_book.md"
TOOLS_SNIPPET = REPO_ROOT / "docs" / "tools" / "snippet.md"
AGENTS_GUIDE = REPO_ROOT / "AGENTS.md"
MANAGER_PROMPT = REPO_ROOT / "docs" / "tools" / "prompts" / "manager_collab_pipeline.md"
LEDGER_LINT = REPO_ROOT / "scripts" / "ledger_lint.py"
QUEUE_SKILL = REPO_ROOT / "skills" / "planveyor-plan-queue" / "SKILL.md"
PLAN_TEMPLATE = REPO_ROOT / "docs" / "plans" / "_template.md"
DECOMPOSITION_PROMPT = REPO_ROOT / "docs" / "tools" / "prompts" / "planveyor_decomposition.md"
PROMPTS_README = REPO_ROOT / "docs" / "tools" / "prompts" / "README.md"
DECOMPOSITION_PLAYBOOK = REPO_ROOT / "docs" / "playbooks" / "decomposition_wave.md"
PLANS_README = REPO_ROOT / "docs" / "plans" / "README.md"
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import plan_status_oracle as PLAN_STATUS_ORACLE
from test_contract_authority_support import AuthorityFixture, commit_all, git, write
from test_support import process_contract_fixtures
from test_support.process_contract_fixtures import temporary_git_root


class ProcessContractFixtureTests(unittest.TestCase):
    def test_run_zsh_fixture_uses_clean_environment_and_preserves_call_contract(self) -> None:
        command = 'print -r -- "$0|$1|$2|${ZDOTDIR-}"'
        fixture_env = {"FIXTURE_SETTING": "fixture-value"}
        pybin = str(Path(sys.executable).resolve())
        expected_result = subprocess.CompletedProcess([], 0, "fixture output\n", "")

        with tempfile.TemporaryDirectory(prefix="planveyor-zsh-fixture-") as tmpdir:
            home = Path(tmpdir) / "home"
            home.mkdir()
            child_temporary = tempfile.TemporaryDirectory(
                prefix="planveyor-zsh-fixture-child-",
            )
            child_tmp = Path(child_temporary.name).resolve()
            expected_env = {
                "PATH": "/fixture/bin",
                "PYBIN": pybin,
                "HOME": str(home),
                "TMPDIR": str(child_tmp),
                "TMPPREFIX": str(child_tmp / "zsh"),
                "FIXTURE_SETTING": "fixture-value",
            }
            hostile_parent = {
                "HOME": "/hostile/home",
                "TMPDIR": "/hostile/tmpdir",
                "TMPPREFIX": "/hostile/tmpprefix",
                "ZDOTDIR": "/hostile/zdotdir",
                "HOSTILE_ENV": "must-not-leak",
            }
            with mock.patch.dict(os.environ, hostile_parent, clear=True):
                helper = process_contract_fixtures.run_zsh_fixture
                with (
                    mock.patch.object(
                        process_contract_fixtures.tempfile,
                        "TemporaryDirectory",
                        return_value=child_temporary,
                    ) as temporary_directory,
                    mock.patch.object(
                        process_contract_fixtures.subprocess,
                        "run",
                        return_value=expected_result,
                    ) as run,
                ):
                    result = helper(
                        command,
                        cwd=REPO_ROOT,
                        path="/fixture/bin",
                        pybin=pybin,
                        fixture_env=fixture_env,
                        home=home,
                        argv0="fixture-zsh",
                        argv_tail=("first tail", "second tail"),
                        capture_output=True,
                        check=True,
                        timeout=17.5,
                    )
                observed = helper(
                    'print -r -- "$HOME|${ZDOTDIR-}|$TMPDIR|$TMPPREFIX"; '
                    '[[ -d "$HOME" && -d "$TMPDIR" && -w "$HOME" && -w "$TMPDIR" ]]',
                    cwd=REPO_ROOT,
                    path="/fixture/bin",
                    pybin=pybin,
                    fixture_env=fixture_env,
                    home=home,
                )
                self.assertEqual(observed.returncode, 0, observed.stderr)
                self.assertEqual(observed.stderr, "")
                observed_home, observed_zdotdir, observed_tmpdir, observed_tmpprefix = (
                    observed.stdout.rstrip("\n").split("|")
                )
                self.assertEqual(observed_home, str(home))
                self.assertEqual(observed_zdotdir, "")
                self.assertTrue(home.is_dir())
                self.assertTrue(Path(observed_tmpdir).is_absolute())
                self.assertTrue(
                    Path(observed_tmpdir).name.startswith(
                        "planveyor-zsh-fixture-child-",
                    )
                )
                self.assertEqual(
                    observed_tmpprefix,
                    str(Path(observed_tmpdir) / "zsh"),
                )

        self.assertIs(result, expected_result)
        self.assertEqual(fixture_env, {"FIXTURE_SETTING": "fixture-value"})
        temporary_directory.assert_called_once_with(
            prefix="planveyor-zsh-fixture-child-",
        )
        self.assertTrue(Path(expected_env["TMPDIR"]).is_absolute())
        self.assertEqual(
            expected_env["TMPPREFIX"],
            str(Path(expected_env["TMPDIR"]) / "zsh"),
        )
        run.assert_called_once_with(
            [
                "/bin/zsh",
                "-fc",
                command,
                "fixture-zsh",
                "first tail",
                "second tail",
            ],
            cwd=REPO_ROOT,
            env=expected_env,
            stdin=subprocess.DEVNULL,
            text=True,
            capture_output=True,
            check=True,
            timeout=17.5,
        )
        self.assertNotIn("ZDOTDIR", expected_env)
        self.assertNotIn("HOSTILE_ENV", expected_env)

    def test_run_zsh_fixture_defaults_argv0_to_zsh(self) -> None:
        helper = process_contract_fixtures.run_zsh_fixture
        pybin = str(Path(sys.executable).resolve())
        expected_result = subprocess.CompletedProcess([], 0, "", "")
        with tempfile.TemporaryDirectory(prefix="planveyor-zsh-default-") as tmpdir:
            home = Path(tmpdir) / "home"
            home.mkdir()
            with mock.patch.object(
                process_contract_fixtures.subprocess,
                "run",
                return_value=expected_result,
            ) as run:
                result = helper(
                    ":",
                    cwd=REPO_ROOT,
                    path="/fixture/bin",
                    pybin=pybin,
                    home=home,
                )
        self.assertIs(result, expected_result)
        self.assertEqual(run.call_args.args[0], ["/bin/zsh", "-fc", ":", "zsh"])

    def test_run_zsh_fixture_preserves_explicit_tmp_keys_without_deriving_peer(self) -> None:
        helper = process_contract_fixtures.run_zsh_fixture
        pybin = str(Path(sys.executable).resolve())
        expected_result = subprocess.CompletedProcess([], 0, "", "")
        with tempfile.TemporaryDirectory(prefix="planveyor-zsh-explicit-tmp-") as tmpdir:
            home = Path(tmpdir) / "home"
            home.mkdir()
            for fixture_env in (
                {"TMPDIR": "/hostile/explicit-tmpdir"},
                {"TMPPREFIX": "/hostile/explicit-tmpprefix"},
            ):
                with self.subTest(fixture_env=fixture_env):
                    expected_env = {
                        "PATH": "/fixture/bin",
                        "PYBIN": pybin,
                        "HOME": str(home),
                        **fixture_env,
                    }
                    with (
                        mock.patch.object(
                            process_contract_fixtures.tempfile,
                            "TemporaryDirectory",
                        ) as temporary_directory,
                        mock.patch.object(
                            process_contract_fixtures.subprocess,
                            "run",
                            return_value=expected_result,
                        ) as run,
                    ):
                        result = helper(
                            ":",
                            cwd=REPO_ROOT,
                            path="/fixture/bin",
                            pybin=pybin,
                            fixture_env=fixture_env,
                            home=home,
                        )
                    self.assertIs(result, expected_result)
                    temporary_directory.assert_not_called()
                    run.assert_called_once_with(
                        ["/bin/zsh", "-fc", ":", "zsh"],
                        cwd=REPO_ROOT,
                        env=expected_env,
                        stdin=subprocess.DEVNULL,
                        text=True,
                        capture_output=True,
                        check=False,
                        timeout=60.0,
                    )

    def test_run_zsh_fixture_rejects_relative_pybin(self) -> None:
        helper = process_contract_fixtures.run_zsh_fixture
        with self.assertRaisesRegex(ValueError, "absolute"):
            helper(
                ":",
                cwd=REPO_ROOT,
                path="/fixture/bin",
                pybin="relative-python",
                home=REPO_ROOT,
            )


class PlanveyorEntrypointGitPreflightTests(unittest.TestCase):
    _DETAILS = {
        "missing_git": "Git executable is unavailable",
        "missing_repo": "runtime root has no Git metadata",
        "missing_head": "HEAD does not resolve to a commit",
    }

    def _entry(self, fixture: AuthorityFixture) -> Path:
        entry = write(
            fixture.runtime_root,
            "bin/planveyor",
            (REPO_ROOT / "bin/planveyor").read_bytes(),
            executable=True,
        )
        commit_all(fixture.runtime_root, "public child entry")
        return entry

    def _run_entry(
        self,
        entry: Path,
        fixture: AuthorityFixture,
        *,
        path: str,
        arguments: tuple[str, ...] = ("--help",),
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        environment = fixture.environment()
        environment["PATH"] = path
        if extra_env:
            environment.update(extra_env)
        return subprocess.run(
            [str(entry), *arguments],
            cwd=fixture.runtime_root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )

    def _assert_failure(
        self,
        result: subprocess.CompletedProcess[str],
        *,
        category: str,
        runtime_root: Path,
        detail: str | None = None,
    ) -> None:
        expected_detail = self._DETAILS[category] if detail is None else detail
        self.assertEqual(result.returncode, 64)
        self.assertEqual(result.stdout, "")
        self.assertEqual(
            result.stderr,
            "planveyor: runtime Git preflight failed: "
            f"category={category}; root={runtime_root.resolve()}; detail={expected_detail}\n",
        )

    def _tool_path_without_git(self, root: Path) -> Path:
        dirname = shutil.which("dirname")
        self.assertIsNotNone(dirname)
        tool_dir = root / "tools"
        tool_dir.mkdir()
        (tool_dir / "dirname").symlink_to(dirname)
        return tool_dir

    def _link_tool(self, tool_dir: Path, name: str) -> None:
        executable = shutil.which(name)
        self.assertIsNotNone(executable, f"{name} must be available for this fixture")
        assert executable is not None
        (tool_dir / name).symlink_to(executable)

    def test_missing_git_is_distinguished_before_static_help(self) -> None:
        with AuthorityFixture() as fixture:
            entry = self._entry(fixture)
            tool_dir = self._tool_path_without_git(fixture.root)
            result = self._run_entry(entry, fixture, path=str(tool_dir))

            self._assert_failure(result, category="missing_git", runtime_root=fixture.runtime_root)

    def test_missing_repo_is_distinguished_before_static_help(self) -> None:
        with AuthorityFixture() as fixture:
            entry = self._entry(fixture)
            shutil.rmtree(fixture.runtime_root / ".git")
            result = self._run_entry(entry, fixture, path=os.environ.get("PATH", "/usr/bin:/bin"))

            self._assert_failure(result, category="missing_repo", runtime_root=fixture.runtime_root)

    def test_missing_head_is_distinguished_after_root_confirmation(self) -> None:
        with AuthorityFixture() as fixture:
            entry = self._entry(fixture)
            shutil.rmtree(fixture.runtime_root / ".git")
            git(fixture.runtime_root, "init", "--quiet", "--object-format=sha1")
            result = self._run_entry(entry, fixture, path=os.environ.get("PATH", "/usr/bin:/bin"))

            self._assert_failure(result, category="missing_head", runtime_root=fixture.runtime_root)

    def test_missing_rg_fails_after_git_preflight_before_loader_or_child_execution(self) -> None:
        with AuthorityFixture() as fixture:
            entry = self._entry(fixture)
            tool_dir = self._tool_path_without_git(fixture.root)
            for name in ("env", "chmod", "rm"):
                self._link_tool(tool_dir, name)
            git_marker = fixture.root / "git-preflight"
            real_git = shutil.which("git")
            self.assertIsNotNone(real_git)
            assert real_git is not None
            fake_git = tool_dir / "git"
            fake_git.write_text(
                "#!/bin/sh\n"
                f"printf '%s\\n' \"$*\" >> {shlex.quote(str(git_marker))}\n"
                f"exec {shlex.quote(real_git)} \"$@\"\n",
                encoding="utf-8",
            )
            fake_git.chmod(0o755)
            loader_marker = fixture.root / "loader-constructed"
            child_marker = fixture.root / "fake-zsh-executed"
            fake_mktemp = tool_dir / "mktemp"
            fake_mktemp.write_text(
                "#!/bin/sh\n"
                "template=$1\n"
                "loader=${template%XXXXXXXX}fixture\n"
                f"printf '%s\\n' constructed > {shlex.quote(str(loader_marker))}\n"
                ": > \"$loader\"\n"
                "printf '%s\\n' \"$loader\"\n",
                encoding="utf-8",
            )
            fake_mktemp.chmod(0o755)
            fake_zsh = tool_dir / "zsh"
            fake_zsh.write_text(
                "#!/bin/sh\n"
                f"printf '%s\\n' executed > {shlex.quote(str(child_marker))}\n"
                "exit 91\n",
                encoding="utf-8",
            )
            fake_zsh.chmod(0o755)
            tmpdir = fixture.root / "loader-tmp"
            tmpdir.mkdir()

            result = self._run_entry(
                entry,
                fixture,
                path=str(tool_dir),
                extra_env={"TMPDIR": str(tmpdir)},
            )

            self.assertEqual(result.returncode, 64)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "planveyor: ripgrep (rg) is required\n")
            self.assertEqual(
                git_marker.read_text(encoding="utf-8").splitlines(),
                [
                    "--version",
                    f"-C {fixture.runtime_root} rev-parse --show-toplevel",
                    f"-C {fixture.runtime_root} rev-parse --verify --quiet HEAD^{{commit}}",
                ],
            )
            self.assertFalse(loader_marker.exists(), "missing rg must stop before loader construction")
            self.assertFalse(child_marker.exists(), "missing rg must stop before child execution")

    def test_child_tmp_prefix_is_derived_from_sanitized_tmpdir_and_entry_doctor_is_pinned(self) -> None:
        with AuthorityFixture() as fixture:
            entry = self._entry(fixture)
            tool_dir = fixture.root / "child-tools"
            tool_dir.mkdir()
            child_environment = fixture.child_tmp / "authority-child-environment"
            fake_zsh = tool_dir / "zsh"
            fake_zsh.write_text(
                "#!/bin/sh\n"
                f"printf '%s\\t%s\\n' \"${{TMPDIR-}}\" \"${{TMPPREFIX-}}\" > {shlex.quote(str(child_environment))}\n"
                f"tool_prefix={shlex.quote(str(tool_dir) + os.pathsep)}\n"
                'case "${PATH-}" in\n'
                '  "$tool_prefix"*) PATH=${PATH#"$tool_prefix"} ;;\n'
                "  *) exit 93 ;;\n"
                "esac\n"
                f"TMPDIR={shlex.quote(str(fixture.child_tmp))}\n"
                f"TMPPREFIX={shlex.quote(str(fixture.child_tmp / 'zsh'))}\n"
                "export PATH TMPDIR TMPPREFIX\n"
                "exec /bin/zsh \"$@\"\n",
                encoding="utf-8",
            )
            fake_zsh.chmod(0o755)

            baseline = self._run_entry(
                entry,
                fixture,
                path=str(tool_dir) + os.pathsep + os.environ.get("PATH", os.defpath),
                arguments=("planveyor_entry_doctor",),
            )
            self.assertEqual(baseline.returncode, 0, baseline.stderr)
            self.assertIn("source_state=pinned\n", baseline.stdout)
            self.assertEqual(
                child_environment.read_text(encoding="utf-8"),
                f"{fixture.child_tmp}\t{fixture.child_tmp / 'zsh'}\n",
            )

            mktemp_argv = fixture.child_tmp / "hostile-loader-mktemp-argv"
            fake_mktemp = tool_dir / "mktemp"
            fake_mktemp.write_text(
                "#!/bin/sh\n"
                f"printf '%s\\t%s\\n' \"$#\" \"$1\" >> {shlex.quote(str(mktemp_argv))}\n"
                '[ "$#" -eq 1 ] && [ "$1" = "/tmp/planveyor-loader.XXXXXXXX" ] || exit 91\n'
                f"exec /usr/bin/mktemp {shlex.quote(str(fixture.child_tmp / 'planveyor-loader.XXXXXXXX'))}\n",
                encoding="utf-8",
            )
            fake_mktemp.chmod(0o755)

            result = self._run_entry(
                entry,
                fixture,
                path=str(tool_dir) + os.pathsep + os.environ.get("PATH", os.defpath),
                arguments=("planveyor_entry_doctor",),
                extra_env={
                    "TMPDIR": "relative-hostile-tmpdir",
                    "TMPPREFIX": "hostile-parent-prefix",
                },
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("source_state=pinned\n", result.stdout)
            self.assertEqual(child_environment.read_text(encoding="utf-8"), "/tmp\t/tmp/zsh\n")
            self.assertEqual(
                mktemp_argv.read_text(encoding="utf-8"),
                "1\t/tmp/planveyor-loader.XXXXXXXX\n",
            )
            self.assertEqual(
                list(fixture.child_tmp.glob("planveyor-loader.*")),
                [],
                "authority loader must remove the real scoped mktemp file",
            )

    def test_child_tmp_prefix_follows_valid_tmpdir_and_rejects_parent_prefix(self) -> None:
        with AuthorityFixture() as fixture:
            entry = self._entry(fixture)
            tool_dir = fixture.root / "valid-child-tools"
            tool_dir.mkdir()
            child_environment = fixture.root / "valid-child-environment"
            fake_zsh = tool_dir / "zsh"
            fake_zsh.write_text(
                "#!/bin/sh\n"
                f"printf '%s\t%s\n' \"${{TMPDIR-}}\" \"${{TMPPREFIX-}}\" > {shlex.quote(str(child_environment))}\n"
                "exec /bin/zsh \"$@\"\n",
                encoding="utf-8",
            )
            fake_zsh.chmod(0o755)
            tmpdir = fixture.root / "valid-child-tmp"
            tmpdir.mkdir()

            result = self._run_entry(
                entry,
                fixture,
                path=str(tool_dir) + os.pathsep + os.environ.get("PATH", os.defpath),
                arguments=("planveyor_entry_doctor",),
                extra_env={
                    "TMPDIR": str(tmpdir),
                    "TMPPREFIX": "hostile-parent-prefix",
                },
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("source_state=pinned\n", result.stdout)
            self.assertEqual(
                child_environment.read_text(encoding="utf-8"),
                f"{tmpdir}\t{tmpdir}/zsh\n",
            )

    def test_failing_git_probe_is_sanitized_before_rev_parse(self) -> None:
        with AuthorityFixture() as fixture:
            entry = self._entry(fixture)
            tool_dir = self._tool_path_without_git(fixture.root)
            marker = fixture.root / "git-argv"
            fake_git = tool_dir / "git"
            fake_git.write_text(
                "#!/bin/sh\n"
                f"printf '%s\\n' \"$1\" > {shlex.quote(str(marker))}\n"
                "printf '%s\\n' 'fixture-sensitive-detail=https://token" + "@" + "example" + ".test' >&2\n"
                "exit 73\n",
                encoding="utf-8",
            )
            fake_git.chmod(0o755)
            result = self._run_entry(
                entry,
                fixture,
                path=str(tool_dir) + os.pathsep + os.environ.get("PATH", "/usr/bin:/bin"),
            )

            self._assert_failure(
                result,
                category="git_command_failed",
                runtime_root=fixture.runtime_root,
                detail="Git --version exited status 73",
            )
            self.assertEqual(marker.read_text(encoding="utf-8"), "--version\n")
            self.assertNotIn("fixture-sensitive-detail", result.stderr)
            self.assertNotIn("token" + "@" + "example" + ".test", result.stderr)

    def test_failing_git_root_probe_reports_its_safe_stage_and_status(self) -> None:
        with AuthorityFixture() as fixture:
            entry = self._entry(fixture)
            tool_dir = self._tool_path_without_git(fixture.root)
            marker = fixture.root / "git-argv"
            fake_git = tool_dir / "git"
            fake_git.write_text(
                "#!/bin/sh\n"
                f"printf '%s\\n' \"$*\" >> {shlex.quote(str(marker))}\n"
                "case \"$*\" in\n"
                "  --version) exit 0 ;;\n"
                "  *'rev-parse --show-toplevel') "
                "printf '%s\\n' 'fixture-sensitive-root-detail' >&2; exit 74 ;;\n"
                "  *) exit 99 ;;\n"
                "esac\n",
                encoding="utf-8",
            )
            fake_git.chmod(0o755)
            result = self._run_entry(
                entry,
                fixture,
                path=str(tool_dir) + os.pathsep + os.environ.get("PATH", "/usr/bin:/bin"),
            )

            self._assert_failure(
                result,
                category="git_command_failed",
                runtime_root=fixture.runtime_root,
                detail="Git rev-parse --show-toplevel exited status 74",
            )
            self.assertEqual(
                marker.read_text(encoding="utf-8").splitlines(),
                ["--version", f"-C {fixture.runtime_root} rev-parse --show-toplevel"],
            )
            self.assertNotIn("fixture-sensitive-root-detail", result.stderr)

    def test_failing_git_head_probe_reports_its_safe_stage_and_status(self) -> None:
        with AuthorityFixture() as fixture:
            entry = self._entry(fixture)
            tool_dir = self._tool_path_without_git(fixture.root)
            marker = fixture.root / "git-argv"
            fake_git = tool_dir / "git"
            fake_git.write_text(
                "#!/bin/sh\n"
                f"printf '%s\\n' \"$*\" >> {shlex.quote(str(marker))}\n"
                "case \"$*\" in\n"
                "  --version) exit 0 ;;\n"
                "  *'rev-parse --show-toplevel') "
                f"printf '%s\\n' {shlex.quote(str(fixture.runtime_root))}; exit 0 ;;\n"
                "  *'rev-parse --verify --quiet HEAD^{commit}') "
                "printf '%s\\n' 'fixture-sensitive-head-detail' >&2; exit 75 ;;\n"
                "  *) exit 99 ;;\n"
                "esac\n",
                encoding="utf-8",
            )
            fake_git.chmod(0o755)
            result = self._run_entry(
                entry,
                fixture,
                path=str(tool_dir) + os.pathsep + os.environ.get("PATH", "/usr/bin:/bin"),
            )

            self._assert_failure(
                result,
                category="git_command_failed",
                runtime_root=fixture.runtime_root,
                detail="Git rev-parse --verify HEAD^{commit} exited status 75",
            )
            self.assertEqual(
                marker.read_text(encoding="utf-8").splitlines(),
                [
                    "--version",
                    f"-C {fixture.runtime_root} rev-parse --show-toplevel",
                    f"-C {fixture.runtime_root} rev-parse --verify --quiet HEAD^{{commit}}",
                ],
            )
            self.assertNotIn("fixture-sensitive-head-detail", result.stderr)


class PlanveyorFacadeDashboardTests(unittest.TestCase):
    """Help and dashboards through the public facade on an engaged sibling.

    Why: dashboard rows used to call guarded public readers (session, runner,
    range, collab carrier paths).  Each of them revalidated the authority
    context through the Python bridge, so `bin/planveyor --project <sibling>
    planveyor_help` made 81 revalidations and ran for about a minute; the
    forked `planveyor-child` subshells looked like a hang.
    """

    TIMEOUT_SECONDS = 90
    VALIDATE_CALL = re.compile(r"/contract_authority_bridge\.py context-validate(?: |$)")

    def _bridge_logging_interpreter(self, fixture: AuthorityFixture) -> tuple[Path, Path]:
        """A python3 shim that records every interpreter argv, then delegates.

        The facade child starts from a clean environment, so the log path is
        part of the shim instead of an environment variable.
        """

        log = fixture.root / "interpreter-argv.log"
        actual_python = shlex.quote(str(Path(sys.executable).resolve()))
        shim = write(
            fixture.root,
            "interpreter-bin/python3",
            "#!/bin/sh\n"
            "{ for arg do case \"$arg\" in *'\n'*) printf '%s ' '<caller-literal>';; "
            "*) printf '%s ' \"$arg\";; esac; done; printf '\\n'; } "
            f">> {shlex.quote(str(log))}\n"
            f"exec {actual_python} \"$@\"\n",
            executable=True,
        )
        return shim, log

    def _run_facade(
        self,
        entry: Path,
        fixture: AuthorityFixture,
        path: str,
        *arguments: str,
    ) -> subprocess.CompletedProcess[str]:
        environment = fixture.environment()
        environment["PATH"] = path
        command = [str(entry), "--project", str(fixture.target_root), *arguments]
        # A session of its own: on timeout the child and every forked
        # subshell die together, so this test can neither hang nor leak.
        process = subprocess.Popen(
            command,
            cwd=fixture.target_root,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        try:
            stdout, stderr = process.communicate(timeout=self.TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = process.communicate()
            self.fail(
                f"{' '.join(arguments)} did not finish within {self.TIMEOUT_SECONDS}s through the facade\n"
                f"stdout tail:\n{stdout[-2000:]}\nstderr tail:\n{stderr[-2000:]}"
            )
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)

    def test_help_and_dashboards_finish_without_per_row_authority_revalidation(self) -> None:
        architect_sid = "019f0000-1111-7222-8333-444444444444"
        process_sid = "019f0001-1111-7222-8333-444444444444"
        architect_task = "/root/architect_sol_xhigh_v2"
        base = "a" * 40
        head = "b" * 40
        with AuthorityFixture(identity="dashboard-sibling") as fixture:
            entry = write(
                fixture.runtime_root,
                "bin/planveyor",
                (REPO_ROOT / "bin" / "planveyor").read_bytes(),
                executable=True,
            )
            commit_all(fixture.runtime_root, "public child entry")
            fixture.activate_local((), required_runtime_api=(5, 5))
            for relative, text in {
                ".planveyor.session.architect": f"# fixture\n{architect_sid}\n",
                ".planveyor.session.architect.log": f"29.09.2026 05:03:00\t{architect_sid}\trunner=codex\n",
                ".planveyor.runner.reviewer": "claude\n",
                ".planveyor.session.architect_process_roles": f"# fixture\n{process_sid}\n",
                ".planveyor.collab.agent.architect": f"# fixture\n{architect_task}\n",
                ".planveyor.collab.agent.architect.log": (
                    f"29.09.2026 05:04:00\t{architect_task}\tspawn\tplanveyor_manager_collab\n"
                ),
                ".planveyor.range.base": f"{base}\n",
                ".planveyor.range.head": f"{head}\n",
            }.items():
                write(fixture.target_root, relative, text)
            shim, log = self._bridge_logging_interpreter(fixture)
            path = str(shim.parent) + os.pathsep + os.environ.get("PATH", os.defpath)

            def run_counted(*arguments: str) -> tuple[subprocess.CompletedProcess[str], list[str]]:
                log.write_text("", encoding="utf-8")
                result = self._run_facade(entry, fixture, path, *arguments)
                validations = [
                    line for line in log.read_text(encoding="utf-8").splitlines()
                    if self.VALIDATE_CALL.search(line)
                ]
                return result, validations

            usage, usage_validations = run_counted("planveyor_help", "planveyor_help")
            full_help, help_validations = run_counted("planveyor_help")
            dashboard, show_validations = run_counted("planveyor_show")

        self.assertEqual(usage.returncode, 0, usage.stdout + usage.stderr)
        self.assertEqual(usage.stdout, "planveyor_help [--all|--manual|--collab|--process|<command>]\n")
        # The fixture exercises the sibling path: every revalidation carries
        # the engaged context of the marked target.
        self.assertTrue(usage_validations)
        self.assertTrue(all('"state":"engaged"' in line for line in usage_validations), usage_validations[:1])

        self.assertEqual(full_help.returncode, 0, full_help.stdout + full_help.stderr)
        for marker in (
            "## Manual",
            "### Sessions (manual dashboard)",
            "## Collab",
            "## Process tracks (Architect)",
            "#### Catalog (process)",
            f'planveyor_merge_range_stats_json "{base}..{head}"',
            architect_task,
        ):
            self.assertIn(marker, full_help.stdout)
        self.assertRegex(full_help.stdout, r"(?m)^architect\s+codex\s+019f0000\s+29\.09 05:03$")
        self.assertRegex(full_help.stdout, r"(?m)^reviewer_code_risk\s+claude\s*$")
        self.assertRegex(full_help.stdout, r"(?m)^roles\s+019f0001\s+resume\s*$")
        # Rendering every block costs no more authority revalidations than
        # printing a single usage line: dashboard rows and catalog examples
        # read under the root the help owner has already validated.
        self.assertEqual(
            len(help_validations),
            len(usage_validations),
            f"planveyor_help revalidated {len(help_validations)} times, one usage line {len(usage_validations)}",
        )

        self.assertEqual(dashboard.returncode, 0, dashboard.stdout + dashboard.stderr)
        for marker in ("=== Manual ===", "=== Collab ===", "=== Process ===", architect_task, f"range: {base}..{head}"):
            self.assertIn(marker, dashboard.stdout)
        self.assertRegex(dashboard.stdout, r"(?m)^roles\s+019f0001\s+resume\s*$")
        # Without --wide the dashboard stays compact and skips the per-role
        # execution-ready preflights.
        self.assertNotIn("execution_ready:", dashboard.stdout)
        # Owner-level guarded readers only (22 when this budget was set); the
        # per-row revalidation and the forced wide view made it hundreds.
        self.assertLessEqual(len(show_validations), 30, f"planveyor_show revalidated {len(show_validations)} times")


class BareEntrypointsDoctorTests(unittest.TestCase):
    def _run_sourced(
        self,
        command: str,
        *,
        cwd: Path = REPO_ROOT,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        environment = dict(extra_env or {})
        path = environment.pop("PATH", os.environ.get("PATH", os.defpath))
        pybin = environment.pop("PYBIN", str(Path(sys.executable).resolve()))
        home = environment.pop("HOME", None)
        fixture_env = {"PLANVEYOR_ROOT": str(REPO_ROOT), **environment}
        options = {
            "cwd": cwd,
            "path": path,
            "pybin": pybin,
            "fixture_env": fixture_env,
            "argv0": "zsh",
            "argv_tail": (),
            "capture_output": True,
            "check": False,
            # The manual dashboard readback took 45 seconds on a loaded machine.
            "timeout": 240,
        }
        sourced_command = f"source {shlex.quote(str(PLANVEYOR_SCRIPT))} && {command}"
        if home is not None:
            return process_contract_fixtures.run_zsh_fixture(sourced_command, home=home, **options)
        with tempfile.TemporaryDirectory(prefix="planveyor-bare-entrypoints-home-") as temporary_home:
            return process_contract_fixtures.run_zsh_fixture(
                sourced_command,
                home=Path(temporary_home),
                **options,
            )

    def _root_split_shell(
        self,
        consumer_root: Path,
        runtime_root: Path,
        *,
        state: str = "legacy",
    ) -> str:
        """Bind a legacy reader context to a distinct consumer/runtime pair."""
        generation = "0" * 64
        return (
            "_planveyor_authority_context_for_reader() { print -r -- '{}'; }; "
            "_planveyor_authority_context_bindings() { "
            f"printf '%s\\t%s\\t%s\\t\\n' {shlex.quote(state)} {shlex.quote(str(consumer_root))} {generation}; "
            "}; "
            f"_planveyor_project_root() {{ print -r -- {shlex.quote(str(consumer_root))}; }}; "
            f"_planveyor_root() {{ print -r -- {shlex.quote(str(runtime_root))}; }}; "
        )


    def _write_minimal_plan(
        self,
        root: Path,
        rel_path: str,
        *,
        wave_family: str | None,
        status: str = "Ready for Review",
        required_manager_mode: str | None = None,
    ) -> Path:
        plan_path = root / rel_path
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        meta = {
            "plan_meta": {
                "cluster": "process",
                "tags": ["planning-contour"],
                "wave_family": wave_family,
                "phase_overlay": None,
                "phase_state": None,
                "parent": None,
                "next_plans": [],
                "depends_on": [],
                "followups_out": [],
                "canon_updates": [],
                "machine_authority_decision": {
                    "schema_version": PLAN_STATUS_ORACLE.MACHINE_AUTHORITY_DECISION_SCHEMA,
                    "applicability": "not_applicable",
                    "reason_code": "docs_or_tests_only",
                },
            }
        }
        if required_manager_mode is not None:
            meta["plan_meta"]["required_manager_mode"] = required_manager_mode
        plan_path.write_text(
            "\n".join(
                [
                    "# Plan: fixture",
                    "",
                    "**Date:** 2026-06-15 00:00 MSK",
                    "**Stage:** Stage 1",
                    "**Priority:** P2",
                    "**Plan type:** dev",
                    f"**Status:** {status}",
                    "**Schema version:** plan.v1",
                    "",
                    "## Meta (machine-readable JSON; required for new plans)",
                    "```json",
                    json.dumps(meta, indent=2),
                    "```",
                    "",
                    "## Promoted route artifact",
                    "`N/A (why=fixture has no promoted route)`",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return plan_path

    def _init_git_repo(self, root: Path) -> None:
        result = subprocess.run(
            ["git", "init", "-q"],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for key, value in (
            ("user.name", "Fixture"),
            ("user.email", 'fixture' + '@' + 'example' + '.' + 'test'),
        ):
            configured = subprocess.run(
                ["git", "config", key, value],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(configured.returncode, 0, configured.stderr)
        baseline = subprocess.run(
            ["git", "commit", "--allow-empty", "-qm", "fixture baseline"],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(baseline.returncode, 0, baseline.stderr)

    def _write_neutral_plan(self, root: Path, rel_path: str) -> Path:
        plan_path = root / rel_path
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        text = PLAN_TEMPLATE.read_text(encoding="utf-8")
        replacements = {
            "# Plan:": "# Plan: fixture",
            "**Date:**": "**Date:** 2026-08-01 00:00 MSK",
            "**Stage:**": "**Stage:** Stage 1",
            "**Priority:**": "**Priority:** P2",
            "**Plan type:**": "**Plan type:** dev",
            "**Status:**": "**Status:** Architect initial draft",
        }
        lines: list[str] = []
        for line in text.splitlines():
            replacement = next((value for prefix, value in replacements.items() if line.startswith(prefix)), None)
            lines.append(replacement if replacement is not None else line)
        plan_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return plan_path

    def _write_na_authority_plan(self, root: Path, rel_path: str) -> Path:
        plan_path = root / rel_path
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(
            "# Plan: N-A authority fixture\n\n"
            "**Plan type:** review-only\n"
            "**Status:** Ready for Planner\n\n"
            "## Meta\n```json\n"
            + json.dumps(
                {
                    "plan_meta": {
                        "cluster": "process",
                        "machine_authority_decision": {
                            "schema_version": PLAN_STATUS_ORACLE.MACHINE_AUTHORITY_DECISION_SCHEMA,
                            "applicability": "not_applicable",
                            "reason_code": "docs_or_tests_only",
                        },
                    }
                },
                indent=2,
            )
            + "\n```\n",
            encoding="utf-8",
        )
        return plan_path

    def _write_required_authority_plan(self, root: Path, rel_path: str) -> Path:
        decision_id = "mad-260917-0310-neutral-fixture"
        route_id = "fixture_meta_json_v1"
        decision: dict[str, object] = {
            "schema_version": PLAN_STATUS_ORACLE.MACHINE_AUTHORITY_DECISION_SCHEMA,
            "decision_id": decision_id,
            "applicability": "required",
            "state": "frozen",
            "impacts": ["authorization", "routing"],
            "cutover_policy": copy.deepcopy(PLAN_STATUS_ORACLE.MACHINE_AUTHORITY_DECISION_HANDOFF_POLICY),
            "recommended_route": {
                "id": route_id,
                "kind": "structured_carrier",
                "authority_host": {
                    "repo": "current",
                    "path": rel_path,
                    "locator": "json_pointer:/plan_meta/machine_authority_decision",
                },
                "canonical_writer": "fixture-writer",
                "canonical_reader": "fixture-reader",
                "derived_consumers": ["fixture_censor", "fixture_oracle"],
                "schema": "fixture.v1",
                "identity_fields": ["decision_id", "plan_path"],
                "cardinality": "one",
                "failure_behavior": {
                    key: "fail_closed"
                    for key in PLAN_STATUS_ORACLE.MACHINE_AUTHORITY_DECISION_FAILURE_KEYS
                },
            },
            "alternatives": [
                {
                    "id": "fixture_free_form",
                    "kind": "fixture",
                    "disposition": "rejected",
                    "tradeoff": "fixture",
                },
                {
                    "id": "fixture_prose",
                    "kind": "fixture",
                    "disposition": "rejected",
                    "tradeoff": "fixture",
                },
            ],
            "owner_confirmation": {
                "state": "confirmed",
                "question_ref": "Q1",
                "decision_id": decision_id,
                "route_id": route_id,
                "carrier_sha256": "",
            },
        }
        confirmation = decision["owner_confirmation"]
        assert isinstance(confirmation, dict)
        confirmation["carrier_sha256"] = PLAN_STATUS_ORACLE.machine_authority_decision_sha256(decision)
        plan = root / rel_path
        plan.parent.mkdir(parents=True, exist_ok=True)
        plan.write_text(
            "# Plan: machine-authority fixture\n\n"
            "**Plan type:** dev\n"
            "**Status:** Ready for Planner\n\n"
            "## Meta\n```json\n"
            + json.dumps(
                {"plan_meta": {"cluster": "process", "machine_authority_decision": decision}},
                indent=2,
            )
            + "\n```\n\n"
            "## Q&A log\n\n"
            "- [2026-09-17 03:10 MSK] (Architect -> Owner, id=Q1, blocker=yes, needs_owner=yes, status=open) Q: fixture\n"
            "- [2026-09-17 03:11 MSK] (Owner -> Architect, id=Q1, blocker=no, needs_owner=no, status=closed) A: fixture\n",
            encoding="utf-8",
        )
        return plan

    def _update_plan_meta(self, plan_path: Path, **changes: object) -> None:
        text = plan_path.read_text(encoding="utf-8")
        match = re.search(r"```json\n(.*?)\n```", text, flags=re.DOTALL)
        self.assertIsNotNone(match)
        assert match is not None
        payload = json.loads(match.group(1))
        payload["plan_meta"].update(changes)
        replacement = "```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```"
        plan_path.write_text(text[: match.start()] + replacement + text[match.end() :], encoding="utf-8")

    def _state_snapshot(self, root: Path) -> dict[str, bytes]:
        return {
            str(path.relative_to(root)): path.read_bytes()
            for path in sorted(root.glob(".planveyor*"))
            if path.is_file() and not path.is_symlink()
        }

    def _run_decomposition_init(self, root: Path, plan_arg: str) -> subprocess.CompletedProcess[str]:
        return self._run_sourced(
            "planveyor_manager_init() { print -r -- called > .manager_init_called; }; "
            f"planveyor_decomposition_init {shlex.quote(plan_arg)}",
            cwd=root,
        )

    def _tree_bytes(self, root: Path) -> dict[str, bytes]:
        if not root.exists():
            return {}
        return {
            str(path.relative_to(root)): path.read_bytes()
            for path in sorted(root.rglob("*"))
            if path.is_file() and not path.is_symlink()
        }




    def test_public_catalog_hides_installer_and_keeps_doctor(self) -> None:
        for command in ("planveyor_help --all", "planveyor_help --manual", "planveyor_show --all", "planveyor_show --manual"):
            with self.subTest(command=command):
                result = self._run_sourced(command)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn("planveyor_bare_entrypoints_install", result.stdout)
                self.assertIn("planveyor_bare_entrypoints_doctor", result.stdout)

        installer = self._run_sourced("planveyor_help planveyor_bare_entrypoints_install")
        self.assertEqual(installer.returncode, 1)
        self.assertEqual(installer.stdout, "")
        self.assertEqual(installer.stderr, "Unknown planveyor command: planveyor_bare_entrypoints_install\n")

        doctor = self._run_sourced("planveyor_help planveyor_bare_entrypoints_doctor")
        self.assertEqual(doctor.returncode, 0, doctor.stderr)
        self.assertEqual(doctor.stdout, "planveyor_bare_entrypoints_doctor [--bin-dir DIR]\n")

    def test_range_help_examples_are_quiet_and_preserve_markers(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_range_help_") as tmpdir:
            fixture_repo = Path(tmpdir)
            self._init_git_repo(fixture_repo)

            missing = self._run_sourced("planveyor_help --all", cwd=fixture_repo)
            self.assertEqual(missing.returncode, 0, missing.stderr)
            self.assertNotIn("Missing file: ", missing.stderr)
            self.assertIn('planveyor_merge_range_stats_json "BASE..HEAD"', missing.stdout)

            base = "a" * 40
            head = "b" * 40
            (fixture_repo / ".planveyor.range.base").write_text(base + "\n", encoding="utf-8")
            (fixture_repo / ".planveyor.range.head").write_text(head + "\n", encoding="utf-8")
            marked = self._run_sourced("planveyor_help --all", cwd=fixture_repo)
            self.assertEqual(marked.returncode, 0, marked.stderr)
            self.assertIn(f'planveyor_merge_range_stats_json "{base}..{head}"', marked.stdout)

    def test_managed_commands_include_doctor_and_docs_hygiene_wrappers(self) -> None:
        result = self._run_sourced('print -l -- "${(@f)$(_planveyor_bare_entrypoints_managed_commands)}"')

        self.assertEqual(result.returncode, 0, result.stderr)
        commands = set(result.stdout.splitlines())
        expected = {
            "planveyor_plan_bundle",
            "planveyor_plan_closeout_preflight",
            "planveyor_docs_closeout",
            "planveyor_role_runner_preflight",
            "planveyor_analysis_init",
            "planveyor_docs_index_build",
            "planveyor_collab_state_write_alive",
            "planveyor_decomposition_seed_promote",
            "planveyor_review_range_init",
            "planveyor_range_set",
            "planveyor_range_set_merge",
            "planveyor_range_set_auto_merge",
            "planveyor_range_base",
            "planveyor_range_head",
            "planveyor_range_merge",
            "planveyor_role_run_probe",
            "planveyor_merge_range_stats_json",
            "planveyor_merge_tracker_ensure",
            "planveyor_q_next_json",
            "planveyor_q_small_slice_json",
            "planveyor_q_advance_json",
            "planveyor_q_closeout_json",
            "planveyor_q_stop_json",
            "planveyor_q_planpath_override_json",
            "planveyor_q_final_report",
            "planveyor_bare_entrypoints_install",
            "planveyor_bare_entrypoints_doctor",
            "planveyor_docs_hygiene_list",
            "planveyor_docs_hygiene_suggest",
            "planveyor_docs_hygiene_archive",
            "planveyor_followups_apply",
            "planveyor_arch_initial",
            "planveyor_arch_censor",
            "planveyor_planner_censor",
            "planveyor_coder_censor",
        }
        self.assertTrue(expected.issubset(commands), sorted(expected - commands))

    def test_docs_finalize_merge_wrappers_bind_exact_readback_and_preflight_before_tick(self) -> None:
        base = "a" * 40
        head = "b" * 40
        receipt_path = "docs/reviews/260829_1808_docs_finalize_receipt_range_aaaaaaa_bbbbbbb.md"
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "fixture"
            root.mkdir()
            self._init_git_repo(root)
            (root / ".planveyor.range.base").write_text(f"{base}\n", encoding="utf-8")
            (root / ".planveyor.range.head").write_text(f"{head}\n", encoding="utf-8")
            tracker = root / ".planveyor.merge_tracker.md"
            tracker.write_text("# fixture tracker\n- [ ] step:docs_finalize\n", encoding="utf-8")
            tracker_before = tracker.read_bytes()

            dispatch = self._run_sourced(
                "planveyor_session() { print -r -- fixture-session; }; "
                "_planveyor_with_role_env() { shift 2; \"$@\"; }; "
                "_planveyor_codex() { cat > .architect_prompt; "
                f"print -r -- {shlex.quote('docs_finalize_receipt_path=' + receipt_path)}; }}; "
                f"planveyor_arch_docs_general --receipt-path {shlex.quote(receipt_path)}",
                cwd=root,
            )
            self.assertEqual(dispatch.returncode, 0, dispatch.stderr + dispatch.stdout)
            self.assertIn(f"docs_finalize_receipt_path={receipt_path}", dispatch.stdout)
            injected_prompt = (root / ".architect_prompt").read_text(encoding="utf-8")
            self.assertIn(f"DOCS_FINALIZE_RECEIPT_PATH={receipt_path}", injected_prompt)

            rejected = self._run_sourced(
                "planveyor_session() { print -r -- fixture-session; }; "
                "_planveyor_codex() { print -r -- called > .codex_called; }; "
                f"planveyor_arch_docs_general --receipt-path {shlex.quote(str(root / receipt_path))}",
                cwd=root,
            )
            self.assertEqual(rejected.returncode, 2, rejected.stderr + rejected.stdout)
            self.assertFalse((root / ".codex_called").exists())

            missing_path = self._run_sourced("planveyor_arch_docs_general --receipt-path", cwd=root)
            self.assertEqual(missing_path.returncode, 2, missing_path.stderr + missing_path.stdout)
            wrong_range_path = self._run_sourced(
                "planveyor_arch_docs_general --receipt-path "
                "docs/reviews/260829_1808_docs_finalize_receipt_range_ccccccc_ddddddd.md",
                cwd=root,
            )
            self.assertEqual(wrong_range_path.returncode, 2, wrong_range_path.stderr + wrong_range_path.stdout)

            red = self._run_sourced(
                "planveyor_post_merge_receipt_preflight() { print -r -- preflight >> .sequence; return 1; }; "
                "planveyor_merge_tracker_tick() { print -r -- tick >> .sequence; return 0; }; "
                f"planveyor_post_merge_docs_finalize_tick --role Architect --range {base}..{head} --path {receipt_path}",
                cwd=root,
            )
            self.assertEqual(red.returncode, 1, red.stderr + red.stdout)
            self.assertEqual((root / ".sequence").read_text(encoding="utf-8").splitlines(), ["preflight"])
            self.assertEqual(tracker.read_bytes(), tracker_before)

            (root / ".sequence").unlink()
            green = self._run_sourced(
                "planveyor_post_merge_receipt_preflight() { print -r -- preflight >> .sequence; return 0; }; "
                "planveyor_merge_tracker_tick() { print -r -- tick:$1 >> .sequence; return 0; }; "
                f"planveyor_post_merge_docs_finalize_tick --role Architect --range {base}..{head} --path {receipt_path}",
                cwd=root,
            )
            self.assertEqual(green.returncode, 0, green.stderr + green.stdout)
            self.assertEqual(
                (root / ".sequence").read_text(encoding="utf-8").splitlines(),
                ["preflight", "tick:step:docs_finalize"],
            )

            help_result = self._run_sourced("planveyor_help planveyor_post_merge_docs_finalize_tick", cwd=root)
            self.assertEqual(help_result.returncode, 0, help_result.stderr)
            self.assertIn("--role Architect --range BASE..HEAD --path", help_result.stdout)

    def test_followups_apply_wrapper_and_help_keep_v2_single_writer_surface(self) -> None:
        help_result = self._run_sourced("planveyor_help planveyor_followups_apply")
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("--frozen-manifest <cycle.json>", help_result.stdout)
        self.assertIn("serial CAS writer", PLANVEYOR_SCRIPT.read_text(encoding="utf-8"))

        forwarding = self._run_sourced(
            "planveyor_followups_apply --frozen-manifest frozen.json --apply",
            extra_env={"PYBIN": "/bin/echo"},
        )
        self.assertEqual(forwarding.returncode, 0, forwarding.stderr)
        self.assertIn("--frozen-manifest frozen.json --apply", forwarding.stdout)

    def test_rollout_packet_outcome_set_wrapper_help_and_forwarding(self) -> None:
        usage = (
            "planveyor_rollout_packet_outcome_set --target-plan docs/plans/<...>.md --packet-id <id> "
            "--packet-path docs/rollout_packets/<...>.md --outcome <canonical-or-alias>"
        )
        help_result = self._run_sourced("planveyor_help planveyor_rollout_packet_outcome_set")
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn(usage, help_result.stdout)

        forwarding = self._run_sourced(
            '_planveyor_rollout_packet_helper_run() { print -l -- "$@"; }; '
            "planveyor_rollout_packet_outcome_set --target-plan docs/plans/example.md "
            "--packet-id packet-1 --packet-path docs/rollout_packets/example.md --outcome adopted"
        )
        self.assertEqual(forwarding.returncode, 0, forwarding.stderr)
        self.assertEqual(
            forwarding.stdout.splitlines(),
            [
                "outcome-set",
                "--target-plan",
                "docs/plans/example.md",
                "--packet-id",
                "packet-1",
                "--packet-path",
                "docs/rollout_packets/example.md",
                "--outcome",
                "adopted",
            ],
        )

        commands_result = self._run_sourced('print -l -- "${(@f)$(_planveyor_bare_entrypoints_managed_commands)}"')
        self.assertEqual(commands_result.returncode, 0, commands_result.stderr)
        self.assertIn("planveyor_rollout_packet_outcome_set", commands_result.stdout.splitlines())
        script_text = PLANVEYOR_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("record one canonical target-local outcome through the structured rollout packet carrier", script_text)
        self.assertIn(usage, script_text)

    def test_collab_state_writer_persists_canonical_v2_task_names_without_sid_lookup(self) -> None:
        cases = (
            ("architect", "/root/architect_sol_xhigh_v2"),
            ("planner", "/root/planner_terra_ultra_v2"),
            ("coder", "/root/coder_terra_ultra_v2"),
            ("reviewer_code_risk", "/root/reviewer_code_risk_sol_xhigh_v2"),
            ("reviewer_code_contracts", "/root/reviewer_code_contracts_sol_xhigh_v2"),
        )
        for role, task_name in cases:
            with self.subTest(role=role, task_name=task_name), tempfile.TemporaryDirectory(
                prefix="planveyor_collab_v2_"
            ) as tmpdir:
                fixture_repo = Path(tmpdir)
                self._init_git_repo(fixture_repo)
                command = (
                    "_planveyor_expand_codex_sid_prefix() { return 91; }; "
                    "_planveyor_py_any() { return 92; }; "
                    f"planveyor_collab_state_write_alive {shlex.quote(role)} "
                    f"{shlex.quote(task_name)} spawn fixture"
                )

                result = self._run_sourced(command, cwd=fixture_repo)

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, f"{task_name}\n")
                state_path = fixture_repo / f".planveyor.collab.agent.{role}"
                self.assertEqual(state_path.read_text(encoding="utf-8").splitlines()[-1], task_name)
                log_fields = fixture_repo.joinpath(
                    f".planveyor.collab.agent.{role}.log"
                ).read_text(encoding="utf-8").splitlines()[-1].split("\t")
                self.assertEqual(log_fields[1:], [task_name, "spawn", "fixture"])

    def test_collab_state_writer_rejects_incompatible_v2_names_without_mutation(self) -> None:
        cases = (
            ("architect", "/root/planner_terra_ultra_v2"),
            ("architect", "/root/architect_sol_xhigh_v1"),
            ("architect", "/root/architect-sol-xhigh-v2"),
            ("architect", "/root/../architect_sol_xhigh_v2"),
            ("architect", "/root/manager/architect_sol_xhigh_v2"),
            ("architect", "/root/architect_sol_xhigh_v2\n/root/coder_terra_ultra_v2"),
            ("reviewer", "/root/reviewer_code_risk_sol_xhigh_v2"),
        )
        for role, task_name in cases:
            with self.subTest(role=role, task_name=task_name), tempfile.TemporaryDirectory(
                prefix="planveyor_collab_v2_reject_"
            ) as tmpdir:
                fixture_repo = Path(tmpdir)
                self._init_git_repo(fixture_repo)
                state_path = fixture_repo / f".planveyor.collab.agent.{role}"
                log_path = fixture_repo / f".planveyor.collab.agent.{role}.log"
                state_path.write_bytes(b"# fixture\nlegacy-state\n")
                log_path.write_bytes(b"fixture\tlegacy-state\tspawn\n")
                before = self._state_snapshot(fixture_repo)

                result = self._run_sourced(
                    f"planveyor_collab_state_write_alive {shlex.quote(role)} "
                    f"{shlex.quote(task_name)} respawn fixture",
                    cwd=fixture_repo,
                )

                self.assertEqual(result.returncode, 1)
                self.assertIn("incompatible V2 task name=", result.stderr)
                self.assertEqual(self._state_snapshot(fixture_repo), before)

    def test_collab_state_writer_rejects_invalid_event_without_mutation(self) -> None:
        invalid_event = "spawn\tforged\nrow"
        with tempfile.TemporaryDirectory(prefix="planveyor_collab_event_reject_") as tmpdir:
            fixture_repo = Path(tmpdir)
            self._init_git_repo(fixture_repo)
            state_path = fixture_repo / ".planveyor.collab.agent.architect"
            log_path = fixture_repo / ".planveyor.collab.agent.architect.log"
            state_path.write_bytes(b"# fixture\nlegacy-state\n")
            log_path.write_bytes(b"fixture\tlegacy-state\tspawn\n")
            before = self._state_snapshot(fixture_repo)

            result = self._run_sourced(
                "planveyor_collab_state_write_alive architect "
                f"/root/architect_sol_xhigh_v2 {shlex.quote(invalid_event)} fixture",
                cwd=fixture_repo,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("unsupported event; expected spawn|respawn|reset|close|sync", result.stderr)
            self.assertEqual(self._state_snapshot(fixture_repo), before)

    def test_collab_state_writer_preserves_state_when_log_append_fails(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_collab_log_fail_") as tmpdir:
            fixture_repo = Path(tmpdir)
            self._init_git_repo(fixture_repo)
            state_path = fixture_repo / ".planveyor.collab.agent.architect"
            log_path = fixture_repo / ".planveyor.collab.agent.architect.log"
            state_path.write_bytes(b"# fixture\nlegacy-state\n")
            log_path.write_bytes(b"fixture\tlegacy-state\tspawn\n")
            before = self._state_snapshot(fixture_repo)

            result = self._run_sourced(
                "_planveyor_collab_log_append() { return 1; }; "
                "planveyor_collab_state_write_alive architect "
                "/root/architect_sol_xhigh_v2 sync fixture",
                cwd=fixture_repo,
            )

            self.assertEqual(result.returncode, 1)
            self.assertEqual(self._state_snapshot(fixture_repo), before)
            self.assertFalse(any(fixture_repo.glob(".planveyor.collab.agent.architect.tmp.*")))

    def test_collab_state_writer_keeps_legacy_sid_rollout_guard(self) -> None:
        sid = "019f0000-1111-7222-8333-444444444444"
        with tempfile.TemporaryDirectory(prefix="planveyor_collab_v1_") as tmpdir:
            fixture_repo = Path(tmpdir)
            self._init_git_repo(fixture_repo)
            command = (
                "_planveyor_codex_session_stats_script() { print -r -- fixture-stats; }; "
                "_planveyor_codex_home_effective() { print -r -- /tmp/codex; }; "
                "_planveyor_py_any() { print -r -- 'sid=fixture'; }; "
                f"planveyor_collab_state_write_alive architect {shlex.quote(sid)} spawn legacy"
            )

            result = self._run_sourced(command, cwd=fixture_repo)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, f"{sid}\n")
            state_path = fixture_repo / ".planveyor.collab.agent.architect"
            self.assertEqual(state_path.read_text(encoding="utf-8").splitlines()[-1], sid)

    def test_collab_state_writer_expands_legacy_short_sid_before_rollout_lookup(self) -> None:
        sid_prefix = "019f0000"
        sid = "019f0000-1111-7222-8333-444444444444"
        with tempfile.TemporaryDirectory(prefix="planveyor_collab_v1_prefix_") as tmpdir:
            fixture_repo = Path(tmpdir)
            self._init_git_repo(fixture_repo)
            command = (
                f"_planveyor_expand_codex_sid_prefix() {{ print -r -- {shlex.quote(sid)}; }}; "
                "_planveyor_codex_session_stats_script() { print -r -- fixture-stats; }; "
                "_planveyor_codex_home_effective() { print -r -- /tmp/codex; }; "
                "_planveyor_py_any() { print -r -- \"$*\" > .stats_args; print -r -- 'sid=fixture'; }; "
                f"planveyor_collab_state_write_alive architect {shlex.quote(sid_prefix)} spawn legacy-prefix"
            )

            result = self._run_sourced(command, cwd=fixture_repo)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, f"{sid}\n")
            state_path = fixture_repo / ".planveyor.collab.agent.architect"
            self.assertEqual(state_path.read_text(encoding="utf-8").splitlines()[-1], sid)
            stats_args = fixture_repo.joinpath(".stats_args").read_text(encoding="utf-8")
            self.assertIn(f"--sid {sid}", stats_args)

    def test_collab_state_writer_rejects_missing_legacy_rollout_without_mutation(self) -> None:
        sid = "019f0000-1111-7222-8333-444444444444"
        with tempfile.TemporaryDirectory(prefix="planveyor_collab_v1_reject_") as tmpdir:
            fixture_repo = Path(tmpdir)
            self._init_git_repo(fixture_repo)
            state_path = fixture_repo / ".planveyor.collab.agent.architect"
            log_path = fixture_repo / ".planveyor.collab.agent.architect.log"
            state_path.write_bytes(b"# fixture\nlegacy-state\n")
            log_path.write_bytes(b"fixture\tlegacy-state\tspawn\n")
            before = self._state_snapshot(fixture_repo)
            command = (
                "_planveyor_codex_session_stats_script() { print -r -- fixture-stats; }; "
                "_planveyor_codex_home_effective() { print -r -- /tmp/codex; }; "
                "_planveyor_py_any() { return 1; }; "
                f"planveyor_collab_state_write_alive architect {shlex.quote(sid)} respawn legacy"
            )

            result = self._run_sourced(command, cwd=fixture_repo)

            self.assertEqual(result.returncode, 1)
            self.assertIn(f"no rollout found for sid={sid}", result.stderr)
            self.assertEqual(self._state_snapshot(fixture_repo), before)

    def test_queue_wrappers_and_help_forward_concrete_manager_mode(self) -> None:
        result = self._run_sourced(
            'function _planveyor_plan_queue() { print -l -- "$@"; }; '
            "planveyor_q_set docs/plans/example.md --for-manager-mode manager-collab; "
            "planveyor_q_append docs/plans/tail.md --for-manager-mode manager-custom-pipeline; "
            "planveyor_q_next_json --manager-mode manager-collab; "
            "planveyor_q_advance_json Done --manager-mode manager-custom-pipeline; "
            "planveyor_q_closeout_json --manager-mode manager-custom-pipeline; "
            "planveyor_q_stop_json docs_closeout_blocked --source-plan docs/plans/finalized.md; "
            "planveyor_q_recover --json; "
            "_planveyor_help_cmd_usage planveyor_q_set; "
            "_planveyor_help_cmd_usage planveyor_q_append; "
            "_planveyor_help_cmd_usage planveyor_q_next_json; "
            "_planveyor_help_cmd_usage planveyor_q_advance_json; "
            "_planveyor_help_cmd_usage planveyor_q_closeout_json; "
            "_planveyor_help_cmd_usage planveyor_q_stop_json; "
            "_planveyor_help_cmd_usage planveyor_q_recover"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertIn(
            ["set", "docs/plans/example.md", "--for-manager-mode", "manager-collab"],
            [lines[index : index + 4] for index in range(len(lines) - 3)],
        )
        self.assertIn("append", lines)
        self.assertIn("--for-manager-mode", lines)
        self.assertIn("next", lines)
        self.assertIn("advance", lines)
        self.assertIn("closeout", lines)
        self.assertIn("stop", lines)
        self.assertIn("--source-plan", lines)
        self.assertIn("docs/plans/finalized.md", lines)
        self.assertIn(["recover", "--json"], [lines[index : index + 2] for index in range(len(lines) - 1)])
        self.assertIn("planveyor_q_recover [--json]", result.stdout)
        self.assertIn(
            "planveyor_q_closeout_json --manager-mode <manager-collab|manager-custom-pipeline>",
            result.stdout,
        )
        self.assertIn(
            "planveyor_q_stop_json <REASON> [--source-plan <PLAN_PATH>]",
            result.stdout,
        )
        self.assertIn("planveyor_q_set <PLAN_PATH...> --for-manager-mode", result.stdout)
        self.assertIn("planveyor_q_append [--json] <PLAN_PATH...> --for-manager-mode", result.stdout)
        self.assertIn("planveyor_q_next_json --manager-mode", result.stdout)
        self.assertIn("planveyor_q_advance_json <Done|Superseded> --manager-mode", result.stdout)

        skill = QUEUE_SKILL.read_text(encoding="utf-8")
        self.assertIn("--for-manager-mode manager-collab", skill)
        self.assertIn("--for-manager-mode manager-custom-pipeline", skill)
        self.assertIn("Никогда не заменяйте queue с non-terminal active item.", skill)
        self.assertNotIn(
            "сначала завершите или остановите текущий item через поддерживаемый runtime route.",
            skill,
        )
        self.assertNotIn("planveyor_q_set docs/plans/260101_1200_first.md docs/plans/260101_1210_second.md\n", skill)

    def test_terminal_admission_rejection_payload_and_exit_pass_through_public_queue_wrappers(self) -> None:
        payload = json.dumps(
            {
                "advanced": False,
                "error": "terminal_closeout_admission_rejected",
                "reason_code": "accepted_red_reconciliation_required",
                "finalized_plan": None,
                "next_plan": None,
                "queue_complete": False,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        wrappers = (
            "planveyor_q_advance_json Done --manager-mode manager-collab",
            "planveyor_q_closeout_json --manager-mode manager-custom-pipeline",
        )
        for wrapper in wrappers:
            with self.subTest(wrapper=wrapper):
                result = self._run_sourced(
                    "function _planveyor_plan_queue() { "
                    f"print -r -- {shlex.quote(payload)}; return 1; "
                    "}; "
                    + wrapper
                )

                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual(result.stdout, payload + "\n")
                self.assertEqual(result.stderr, "")

    def test_new_shims_install_and_fresh_shell_invocation_paths_work(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_bare_helpers_") as tmpdir:
            tmp_path = Path(tmpdir)
            target_dir = tmp_path / "bin"
            install = self._run_sourced(f"planveyor_bare_entrypoints_install --bin-dir {shlex.quote(str(target_dir))}")
            self.assertEqual(install.returncode, 0, install.stderr)

            for command in (
                "planveyor_plan_bundle",
                "planveyor_plan_closeout_preflight",
                "planveyor_docs_closeout",
                "planveyor_role_runner_preflight",
                "planveyor_role_run_probe",
                "planveyor_analysis_init",
                    "planveyor_q_next_json",
                "planveyor_q_stop_json",
                "planveyor_q_final_report",
            ):
                shim_path = target_dir / command
                self.assertTrue(shim_path.is_file(), shim_path)
                self.assertTrue(os.access(shim_path, os.X_OK), shim_path)

            child_tmp = (tmp_path / "child_tmp").resolve()
            child_tmp.mkdir()
            home = tmp_path / "home"
            home.mkdir()
            parent_path = os.environ.get("PATH", os.defpath)
            hostile_parent = {
                "HOME": "/hostile/home",
                "TMPDIR": "/hostile/tmpdir",
                "TMPPREFIX": "/hostile/tmpprefix",
                "ZDOTDIR": "/hostile/zdotdir",
                "PATH": parent_path,
            }
            with mock.patch.dict(os.environ, hostile_parent, clear=True):
                env = {
                    "PATH": f"{target_dir}{os.pathsep}{os.environ.get('PATH', os.defpath)}",
                    "HOME": str(home),
                    "TMPDIR": str(child_tmp),
                    "TMPPREFIX": str(child_tmp / "zsh"),
                    "PLANVEYOR_ROOT": str(REPO_ROOT),
                }

            fixture_repo = tmp_path / "fixture_repo"
            fixture_repo.mkdir()
            self._init_git_repo(fixture_repo)

            child_marker = child_tmp / "fresh-shim-child-environment"
            queue_result = subprocess.run(
                [
                    "/bin/zsh",
                    "-c",
                    (
                        "planveyor_q_next_json --manager-mode manager-collab; "
                        "rc=$?; "
                        f'print -r -- "C03_FRESH_SHIM_TMP=$HOME|${{ZDOTDIR-}}|$TMPDIR|$TMPPREFIX" > {shlex.quote(str(child_marker))}; '
                        'exit "$rc"'
                    ),
                ],
                cwd=fixture_repo,
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertEqual(queue_result.returncode, 1)
            self.assertIn("Queue is not initialized", queue_result.stderr)
            self.assertEqual(
                child_marker.read_text(encoding="utf-8"),
                f"C03_FRESH_SHIM_TMP={home}||{child_tmp}|{child_tmp / 'zsh'}\n",
            )

            env["PYBIN"] = sys.executable
            canonical_vocab_bytes = (
                REPO_ROOT / "docs" / "_meta" / "plan_vocab.json"
            ).read_bytes()
            fixture_vocab = fixture_repo / "docs" / "_meta" / "plan_vocab.json"
            fixture_vocab.parent.mkdir(parents=True, exist_ok=True)
            fixture_vocab.write_bytes(canonical_vocab_bytes)
            self.assertEqual(fixture_vocab.read_bytes(), canonical_vocab_bytes)
            bare_target_rel = "scripts/bare_entrypoint_fixture_target.py"
            bare_target = fixture_repo / bare_target_rel
            bare_target.parent.mkdir(parents=True, exist_ok=True)
            bare_target.write_text("# synthetic bare-entrypoint fixture target\n", encoding="utf-8")

            def materialize_bare_plan_draft(plan_path: Path) -> None:
                plan_rel = plan_path.relative_to(fixture_repo).as_posix()
                draft_rel = f"docs/code_drafts/{plan_path.stem}__code_draft.md"
                review_rel = f"docs/code_reviews/{plan_path.stem}.md"
                authority_decision = {
                    "schema_version": PLAN_STATUS_ORACLE.MACHINE_AUTHORITY_DECISION_SCHEMA,
                    "applicability": "not_applicable",
                    "reason_code": "docs_or_tests_only",
                }
                plan_path.write_text(
                    plan_path.read_text(encoding="utf-8")
                    + "\n## Context links\n\n"
                    + f"- Code draft(s): `{draft_rel}`\n"
                    + "\n## Как я понял задачу\n\nНужно проверить путь вызова существующего shim.\n"
                    + "\n## Rollout packet handoff\n"
                    + "- Role: `N/A (why=fixture)`\n- Packet path: `N/A (why=fixture)`\n"
                    + "- Target repo: `N/A (why=fixture)`\n"
                    + "- Suggested target plan slug: `N/A (why=fixture)`\n"
                    + "- Queue after import: `N/A (why=fixture)`\n"
                    + "\n## Close-out routing\n"
                    + "- Roadmap/queue sync: `N/A (why=fixture)`\n"
                    + "- Follow-up sync: `N/A (why=fixture)`\n"
                    + "- Next bounded slice: `N/A (why=fixture)`\n"
                    + "- Terminal outcome: `N/A (why=fixture)`\n"
                    + "\n## Verification rerun / exec handoff\n"
                    + "- Mode: `N/A (why=fixture)`\n- Context source: `N/A (why=fixture)`\n"
                    + "- Prompt: `N/A (why=fixture)`\n- Command: `N/A (why=fixture)`\n"
                    + "- Expected artifact: `N/A (why=fixture)`\n"
                    + f"\n## Review artifacts\n- Code review (primary): `{review_rel}`\n",
                    encoding="utf-8",
                )
                review_path = fixture_repo / review_rel
                review_path.parent.mkdir(parents=True, exist_ok=True)
                review_path.write_text("# Review fixture\n", encoding="utf-8")
                draft_path = fixture_repo / draft_rel
                draft_path.parent.mkdir(parents=True, exist_ok=True)
                draft_path.write_text(
                    "# Code draft: bare-entrypoint fixture\n\n"
                    "```json\n"
                    + json.dumps(
                        {
                            "code_draft_meta": {
                                "plan": plan_rel,
                                "cluster": "process",
                                "targets": [{"path": bare_target_rel, "kind": "py"}],
                                "deleted_paths": [],
                                "machine_authority_decision_ref": {
                                    "applicability": "not_applicable",
                                    "reason_code": authority_decision["reason_code"],
                                    "carrier_sha256": PLAN_STATUS_ORACLE.machine_authority_decision_sha256(
                                        authority_decision
                                    ),
                                },
                            }
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                    + "\n```\n",
                    encoding="utf-8",
                )

            source_plan = "docs/plans/260101_0001_terminal_source.md"
            active_plan = "docs/plans/260101_0002_active.md"
            source_plan_path = self._write_minimal_plan(
                fixture_repo,
                source_plan,
                wave_family=None,
                status="Done",
                required_manager_mode="either",
            )
            active_plan_path = self._write_minimal_plan(
                fixture_repo,
                active_plan,
                wave_family=None,
                status="In progress",
                required_manager_mode="either",
            )
            materialize_bare_plan_draft(source_plan_path)
            materialize_bare_plan_draft(active_plan_path)
            queue_helper = REPO_ROOT / "scripts" / "plan_queue.py"
            for helper_args in (
                [
                    "set",
                    source_plan,
                    active_plan,
                    "--for-manager-mode",
                    "manager-collab",
                    "--json",
                ],
                ["next", "--manager-mode", "manager-collab", "--json"],
                [
                    "advance",
                    "--final-status",
                    "Done",
                    "--manager-mode",
                    "manager-collab",
                    "--json",
                ],
            ):
                prepared = subprocess.run(
                    [
                        sys.executable,
                        str(queue_helper),
                        "--project-root",
                        str(fixture_repo),
                        *helper_args,
                    ],
                    cwd=fixture_repo,
                    text=True,
                    capture_output=True,
                    env=env,
                    check=False,
                )
                self.assertEqual(
                    prepared.returncode,
                    0,
                    f"stdout={prepared.stdout}\nstderr={prepared.stderr}",
                )

            sourced_stop = subprocess.run(
                [
                    "/bin/zsh",
                    "-c",
                    "planveyor_q_stop_json docs_closeout_blocked "
                    f"--source-plan {shlex.quote(source_plan)}",
                ],
                cwd=fixture_repo,
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertEqual(sourced_stop.returncode, 0, sourced_stop.stderr)
            sourced_payload = json.loads(sourced_stop.stdout)
            self.assertEqual(sourced_payload["active_plan"], active_plan)
            self.assertEqual(sourced_payload["last_stop"]["plan"], active_plan)
            self.assertEqual(sourced_payload["last_stop"]["stop_source_plan"], source_plan)
            self.assertEqual(
                sourced_payload["queue_runtime_context"]["terminal_tail_stop_source_plan"],
                source_plan,
            )
            self.assertFalse((fixture_repo / ".planveyor.planpath").exists())

            final_report_help = subprocess.run(
                ["/bin/zsh", "-c", "planveyor_q_final_report --help"],
                cwd=fixture_repo,
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertEqual(final_report_help.returncode, 0, final_report_help.stderr)
            self.assertIn("queue-level finalizer report", final_report_help.stdout)

            plan_ref = "docs/plans/260101_0000_probe_fixture.md"
            self._write_minimal_plan(
                fixture_repo,
                plan_ref,
                wave_family=None,
                status="In progress",
            )
            probe = subprocess.run(
                [
                    "/bin/zsh",
                    "-c",
                    "planveyor_role_run_probe run --kind retention "
                    f"--target-plan {shlex.quote(plan_ref)} "
                    "--scenario terminal_recovery --json",
                ],
                cwd=fixture_repo,
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertEqual(probe.returncode, 0, probe.stderr)
            probe_payload = json.loads(probe.stdout)
            self.assertEqual(probe_payload["target_plan"], plan_ref)
            self.assertFalse((fixture_repo / ".planveyor.planpath").exists())

            recovered = subprocess.run(
                [
                    "/bin/zsh",
                    "-c",
                    "planveyor_role_run_probe recover "
                    f"--probe-id {shlex.quote(str(probe_payload['probe_id']))} --json",
                ],
                cwd=fixture_repo,
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertEqual(recovered.returncode, 0, recovered.stderr)

    def test_role_run_probe_help_catalog_is_exact_and_role_run_help_is_unchanged(self) -> None:
        result = self._run_sourced(
            "_planveyor_help_cmd_usage planveyor_role_run_probe; "
            "_planveyor_help_cmd_example planveyor_role_run_probe; "
            "_planveyor_help_cmd_summary planveyor_role_run_probe; "
            "_planveyor_help_cmd_usage planveyor_role_run"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            "planveyor_role_run_probe run --kind retention --target-plan docs/plans/<plan>.md",
            result.stdout,
        )
        self.assertIn("--scenario terminal_recovery --json", result.stdout)
        self.assertIn("isolated managed namespace", result.stdout)
        self.assertIn(
            "planveyor_role_run <architect|architect_initial|architect_censor|planner|planner_censor|coder|coder_censor|reviewer|reviewer_code_risk|reviewer_code_contracts> [--timeout SECONDS] [--json]",
            result.stdout,
        )

    def test_dashboards_read_repo_local_carriers_without_home_probes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_dashboard_local_carriers_") as tmpdir:
            fixture = Path(tmpdir)
            fixture_repo = fixture / "repo"
            fixture_repo.mkdir()
            self._init_git_repo(fixture_repo)
            empty_home = fixture / "empty-home"
            empty_home.mkdir()
            stats_marker = fixture / "stats-probe"
            sync_marker = fixture / "sync-probe"
            manager_sid = "019f0000-1111-7222-8333-444444444444"
            process_sid = "019f0001-1111-7222-8333-444444444444"
            architect_task = "/root/architect_sol_xhigh_v2"
            fixture_repo.joinpath(".planveyor.session.manager").write_text(
                f"# fixture\n{manager_sid}\n", encoding="utf-8"
            )
            fixture_repo.joinpath(".planveyor.session.manager.log").write_text(
                f"2026-09-19 12:00 MSK\t{manager_sid}\trunner=codex\n",
                encoding="utf-8",
            )
            fixture_repo.joinpath(".planveyor.session.architect_process_roles").write_text(
                f"# fixture\n{process_sid}\n", encoding="utf-8"
            )
            fixture_repo.joinpath(".planveyor.session.architect_process_roles.log").write_text(
                f"2026-09-19 12:00 MSK\t{process_sid}\trunner=codex\n",
                encoding="utf-8",
            )
            fixture_repo.joinpath(".planveyor.collab.agent.architect").write_text(
                f"# fixture\n{architect_task}\n", encoding="utf-8"
            )
            fixture_repo.joinpath(".planveyor.collab.agent.architect.log").write_text(
                f"2026-09-19 12:00 MSK\t{architect_task}\tspawn\tplanveyor_manager_collab\n",
                encoding="utf-8",
            )

            command = (
                "unset CODEX_HOME PLANVEYOR_CODEX_HOME; "
                "_planveyor_codex_session_stats_script() { print -r -- session-stats-probe; }; "
                f"_planveyor_py_any() {{ if [[ \"${{1:-}}\" == session-stats-probe ]]; then print -r -- probe >> {shlex.quote(str(stats_marker))}; return 91; fi; command \"$PYBIN\" \"$@\"; }}; "
                f"_planveyor_collab_agent_sync_all() {{ print -r -- sync >> {shlex.quote(str(sync_marker))}; }}; "
                "planveyor_show --manual && "
                "planveyor_show --collab --wide && "
                "planveyor_show --process --wide && "
                "planveyor_help --collab"
            )
            result = self._run_sourced(
                command,
                cwd=fixture_repo,
                extra_env={"HOME": str(empty_home)},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(manager_sid.split("-", 1)[0], result.stdout)
            self.assertIn(process_sid, result.stdout)
            self.assertIn(architect_task, result.stdout)
            self.assertFalse(stats_marker.exists(), result.stdout)
            self.assertFalse(sync_marker.exists(), result.stdout)
    def test_codex_home_adapter_rejects_invalid_paths_and_missing_cli_without_mutation(self) -> None:
        with AuthorityFixture() as runtime_fixture, \
                tempfile.TemporaryDirectory(prefix="planveyor_codex_home_adapter_") as tmpdir:
            fixture = Path(tmpdir)
            home = fixture / "home"
            target = fixture / "consumer-codex"
            (target / "agents").mkdir(parents=True)
            (target / "config.toml").write_text(
                'model = "owner-selected-model"\n', encoding="utf-8"
            )
            (target / "agents" / "worker.toml").write_text(
                'name = "owner-worker"\n', encoding="utf-8"
            )
            def snapshot_surfaces() -> dict[str, dict[str, bytes]]:
                return {
                    "target": self._tree_bytes(target),
                    "home": self._tree_bytes(home),
                    "zdotdir": self._tree_bytes(fixture / "zdotdir"),
                    "xdg_config": self._tree_bytes(fixture / "xdg-config"),
                    "xdg_cache": self._tree_bytes(fixture / "xdg-cache"),
                }

            surfaces_before = snapshot_surfaces()
            fake_bin = fixture / "bin"
            fake_bin.mkdir()
            for name in ("python3", f"python{sys.version_info.major}.{sys.version_info.minor}"):
                fake_bin.joinpath(name).symlink_to(sys.executable)
            env = {
                "HOME": str(home),
                "ZDOTDIR": str(fixture / "zdotdir"),
                "XDG_CONFIG_HOME": str(fixture / "xdg-config"),
                "XDG_CACHE_HOME": str(fixture / "xdg-cache"),
                "PATH": f"{fake_bin}:/usr/bin:/bin:/usr/sbin:/sbin",
            }
            child_tmp = (fixture / "child-tmp").resolve()
            child_tmp.mkdir()
            child_observation = child_tmp / "adapter-child-environment"

            def run_adapter(
                candidate: str, command: str = "_planveyor_codex_home_ensure"
            ) -> subprocess.CompletedProcess[str]:
                child_env = runtime_fixture.environment()
                child_env.update(
                    {
                        "PYBIN": sys.executable,
                        "PLANVEYOR_ROOT": str(runtime_fixture.runtime_root),
                        "PLANVEYOR_CODEX_HOME": candidate,
                        **env,
                        "TMPDIR": str(child_tmp),
                        "TMPPREFIX": str(child_tmp / "zsh"),
                    }
                )
                return subprocess.run(
                    [
                        "/bin/zsh",
                        "-dfc",
                        f'print -r -- "$TMPDIR|$TMPPREFIX" > {shlex.quote(str(child_observation))}; '
                        + runtime_fixture.shell_loader()
                        + f"planveyor_source_runtime {shlex.quote(str(runtime_fixture.runtime_root / 'scripts/planveyor.zsh'))} && {command}",
                    ],
                    cwd=runtime_fixture.target_root,
                    text=True,
                    capture_output=True,
                    env=child_env,
                    check=False,
                )

            invalid_cases = {
                "relative": ("consumer-codex", "Codex home must be an absolute path"),
                "noncanonical": (
                    f"{target}/../consumer-codex",
                    "Codex home must be an absolute path",
                ),
                "inside_product": (
                    str(runtime_fixture.runtime_root / "scripts"),
                    "Codex home must be an absolute path",
                ),
            }
            for label, (candidate, expected_error) in invalid_cases.items():
                with self.subTest(case=label):
                    result = run_adapter(candidate)

                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(result.stdout, "")
                    self.assertIn(expected_error, result.stderr)
                    self.assertEqual(snapshot_surfaces(), surfaces_before)

            missing_cli = run_adapter(str(target))

            self.assertEqual(missing_cli.returncode, 127)
            self.assertEqual(
                child_observation.read_text(encoding="utf-8"),
                f"{child_tmp}|{child_tmp / 'zsh'}\n",
            )
            self.assertEqual(missing_cli.stdout, "")
            self.assertEqual(
                missing_cli.stderr,
                "planveyor: Codex CLI is required; install it and authenticate in the consumer-owned home first\n",
            )
            self.assertEqual(snapshot_surfaces(), surfaces_before)

    def test_manual_dashboard_readback_keeps_reviewer_lane_identity_distinct(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_lane_readback_") as tmpdir:
            fixture_repo = Path(tmpdir)
            self._init_git_repo(fixture_repo)
            risk_sid = "risk-lane-session"
            contracts_sid = "contracts-lane-session"

            result = self._run_sourced(
                "planveyor_runner_set reviewer claude >/dev/null && "
                f"planveyor_session_set reviewer_code_risk {risk_sid} runner=claude >/dev/null && "
                f"planveyor_session_set reviewer_code_contracts {contracts_sid} runner=claude >/dev/null && "
                "planveyor_show --manual --wide",
                cwd=fixture_repo,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("reviewer_code_risk", result.stdout)
            self.assertIn("reviewer_code_contracts", result.stdout)
            self.assertIn("execution_ready:", result.stdout)
            self.assertRegex(result.stdout, rf"reviewer_code_risk\s+claude\s+{risk_sid}")
            self.assertRegex(result.stdout, rf"reviewer_code_contracts\s+claude\s+{contracts_sid}")

    def test_analysis_init_prepares_existing_analysis_wave_plan_and_persists_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_analysis_init_") as tmpdir:
            fixture_repo = Path(tmpdir)
            self._init_git_repo(fixture_repo)
            self._write_minimal_plan(
                fixture_repo,
                "docs/plans/analysis_wave_fixture.md",
                wave_family="analysis_wave",
            )

            result = self._run_sourced("planveyor_analysis_init docs/plans/analysis_wave_fixture.md", cwd=fixture_repo)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Prepared analysis wave: docs/plans/analysis_wave_fixture.md", result.stdout)
            self.assertIn("planning_contour_marker=analysis_wave", result.stdout)
            self.assertIn("source_route_state=absent", result.stdout)
            self.assertIn("Next: MANAGER_CMD=run docs/plans/analysis_wave_fixture.md", result.stdout)
            self.assertEqual(
                fixture_repo.joinpath(".planveyor.planpath").read_text(encoding="utf-8").splitlines()[-1],
                "docs/plans/analysis_wave_fixture.md",
            )

    def test_analysis_init_reuses_current_planpath(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_analysis_init_planpath_") as tmpdir:
            fixture_repo = Path(tmpdir)
            self._init_git_repo(fixture_repo)
            self._write_minimal_plan(
                fixture_repo,
                "docs/plans/current_analysis.md",
                wave_family="analysis_wave",
            )
            fixture_repo.joinpath(".planveyor.planpath").write_text(
                "# fixture\ndocs/plans/current_analysis.md\n",
                encoding="utf-8",
            )

            result = self._run_sourced("planveyor_analysis_init", cwd=fixture_repo)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Prepared analysis wave: docs/plans/current_analysis.md", result.stdout)

    def test_analysis_init_fails_closed_without_analysis_wave_plan(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_analysis_init_fail_") as tmpdir:
            fixture_repo = Path(tmpdir)
            self._init_git_repo(fixture_repo)
            self._write_minimal_plan(
                fixture_repo,
                "docs/plans/ordinary.md",
                wave_family=None,
            )

            ordinary = self._run_sourced("planveyor_analysis_init docs/plans/ordinary.md", cwd=fixture_repo)
            missing = self._run_sourced("planveyor_analysis_init docs/plans/missing.md", cwd=fixture_repo)

            self.assertNotEqual(ordinary.returncode, 0)
            self.assertIn("not an analysis-wave source", ordinary.stderr)
            self.assertIn("planning_contour_marker=none", ordinary.stderr)
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn("Missing analysis plan: docs/plans/missing.md", missing.stderr)
            self.assertFalse(fixture_repo.joinpath("docs/plans/missing.md").exists())

    def test_decomposition_init_rejects_semantic_and_incompatible_plans_without_state_mutation(self) -> None:
        cases = (
            ("populated", {}),
            ("terminal", {"status": "Done"}),
            ("superseded", {"status": "Superseded"}),
            ("invalid_status", {"status": "Unknown state"}),
            ("analysis", {"wave_family": "analysis_wave"}),
            ("promoted", {"promoted_from": {"artifact_ref": "docs/analysis_packs/source.md"}}),
            ("active_wrong_wave", {"wave_family": "analysis_wave", "phase_overlay": "decomposition_wave", "phase_state": "active"}),
        )
        for name, changes in cases:
            with self.subTest(case=name), tempfile.TemporaryDirectory(prefix="planveyor_decomposition_reject_") as tmpdir:
                root = Path(tmpdir)
                self._init_git_repo(root)
                plan = self._write_neutral_plan(root, f"docs/plans/{name}.md")
                if "status" in changes:
                    text = plan.read_text(encoding="utf-8").replace(
                        "**Status:** Architect initial draft", f"**Status:** {changes['status']}"
                    )
                    plan.write_text(text, encoding="utf-8")
                meta_changes = {key: value for key, value in changes.items() if key != "status"}
                if meta_changes:
                    self._update_plan_meta(plan, **meta_changes)
                if name == "populated":
                    plan.write_text(
                        plan.read_text(encoding="utf-8").replace("## Problem\n", "## Problem\n\nSemantic content.\n", 1),
                        encoding="utf-8",
                    )
                root.joinpath(".planveyor.planpath").write_text("sentinel-plan\n", encoding="utf-8")
                root.joinpath(".planveyor.queue.json").write_text('{"sentinel": true}\n', encoding="utf-8")
                root.joinpath(".planveyor.staging").write_text("sentinel-stage\n", encoding="utf-8")
                plan_before = plan.read_bytes()
                state_before = self._state_snapshot(root)

                result = self._run_decomposition_init(root, str(plan.relative_to(root)))

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Refusing decomposition init", result.stderr)
                self.assertEqual(plan.read_bytes(), plan_before)
                self.assertEqual(self._state_snapshot(root), state_before)
                self.assertFalse(root.joinpath(".manager_init_called").exists())

    def test_code_draft_stub_requires_architect_authority_before_any_scaffold_write(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_authority_stub_red_") as tmpdir:
            root = Path(tmpdir)
            self._init_git_repo(root)
            plan = self._write_neutral_plan(root, "docs/plans/260814_0919_neutral_post_cutover.md")
            plan_before = plan.read_bytes()
            state_before = self._state_snapshot(root)

            result = self._run_sourced(
                "planveyor_code_draft_stub_from_plan docs/plans/260814_0919_neutral_post_cutover.md",
                cwd=root,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Machine-authority scaffold admission failed", result.stderr)
            self.assertEqual(plan.read_bytes(), plan_before)
            self.assertEqual(self._state_snapshot(root), state_before)
            self.assertFalse((root / "docs" / "code_drafts").exists())

    def test_code_draft_stub_projects_only_validated_active_authority_ref(self) -> None:
        plan_rel = "docs/plans/260917_0310_machine_authority_fixture.md"
        with tempfile.TemporaryDirectory(prefix="planveyor_authority_stub_green_") as tmpdir:
            root = Path(tmpdir)
            self._init_git_repo(root)
            plan = self._write_required_authority_plan(root, plan_rel)
            before = PLAN_STATUS_ORACLE.machine_authority_decision_readback(plan)

            result = self._run_sourced(
                f"planveyor_code_draft_stub_from_plan {shlex.quote(plan_rel)}",
                cwd=root,
            )
            draft = root / f"docs/code_drafts/{plan.stem}__code_draft.md"

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(draft.is_file())
            draft_raw = draft.read_text(encoding="utf-8").split("```json", 1)[1].split("```", 1)[0].strip()
            draft_meta = json.loads(draft_raw)["code_draft_meta"]
            authority = PLAN_STATUS_ORACLE.machine_authority_decision_readback(plan)

        self.assertEqual(
            (before.state, before.reason_code, before.ref_state),
            ("frozen_confirmed", "ok", "missing"),
        )
        self.assertEqual(authority.state, "frozen_confirmed")
        self.assertEqual(authority.ref_state, "valid")
        self.assertEqual(
            draft_meta["machine_authority_decision_ref"],
            {
                "applicability": "required",
                "decision_id": authority.decision_id,
                "carrier_sha256": authority.carrier_sha256,
            },
        )
        self.assertEqual(set(draft_meta["machine_authority_decision_ref"]), {"applicability", "decision_id", "carrier_sha256"})

    def test_code_draft_stub_materializes_first_valid_na_ref(self) -> None:
        plan_rel = "docs/plans/260814_0927_first_na_scaffold.md"
        with tempfile.TemporaryDirectory(prefix="planveyor_authority_stub_na_green_") as tmpdir:
            root = Path(tmpdir)
            self._init_git_repo(root)
            plan = self._write_na_authority_plan(root, plan_rel)
            before = PLAN_STATUS_ORACLE.machine_authority_decision_readback(plan)

            result = self._run_sourced(
                f"planveyor_code_draft_stub_from_plan {shlex.quote(plan_rel)}",
                cwd=root,
            )
            draft = root / "docs/code_drafts/260814_0927_first_na_scaffold__code_draft.md"
            after = PLAN_STATUS_ORACLE.machine_authority_decision_readback(plan)
            draft_exists = draft.is_file()
            raw = draft.read_text(encoding="utf-8").split("```json", 1)[1].split("```", 1)[0].strip()
            draft_meta = json.loads(raw)["code_draft_meta"]

        self.assertEqual((before.state, before.reason_code, before.ref_state), ("not_applicable", "ok", "missing"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(draft_exists)
        self.assertEqual((after.state, after.reason_code, after.ref_state), ("not_applicable", "ok", "valid"))
        self.assertEqual(
            draft_meta["machine_authority_decision_ref"],
            {
                "applicability": "not_applicable",
                "reason_code": "docs_or_tests_only",
                "carrier_sha256": after.carrier_sha256,
            },
        )
        self.assertEqual(
            set(draft_meta["machine_authority_decision_ref"]),
            {"applicability", "reason_code", "carrier_sha256"},
        )

    def test_code_draft_stub_refuses_to_rewrite_invalid_existing_na_ref(self) -> None:
        plan_rel = "docs/plans/260814_0928_existing_na_scaffold.md"
        cases = {
            "malformed": None,
            "stale": {
                "applicability": "not_applicable",
                "reason_code": "docs_or_tests_only",
                "carrier_sha256": "0" * 64,
            },
            "wrong_variant": {
                "applicability": "required",
                "decision_id": "mad-260810-1235",
                "carrier_sha256": "0" * 64,
            },
        }
        for label, ref in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory(prefix="planveyor_authority_stub_na_red_") as tmpdir:
                root = Path(tmpdir)
                self._init_git_repo(root)
                plan = self._write_na_authority_plan(root, plan_rel)
                draft = root / "docs/code_drafts/260814_0928_existing_na_scaffold__code_draft.md"
                draft.parent.mkdir(parents=True, exist_ok=True)
                if ref is None:
                    draft.write_text(
                        "# Code draft: malformed N-A fixture\n\n```json\n{not-json\n```\n",
                        encoding="utf-8",
                    )
                else:
                    draft.write_text(
                        "# Code draft: invalid N-A fixture\n\n```json\n"
                        + json.dumps(
                            {
                                "code_draft_meta": {
                                    "plan": plan_rel,
                                    "cluster": "process",
                                    "machine_authority_decision_ref": ref,
                                }
                            },
                            indent=2,
                        )
                        + "\n```\n",
                        encoding="utf-8",
                    )
                plan_before = plan.read_bytes()
                draft_before = draft.read_bytes()
                state_before = self._state_snapshot(root)

                result = self._run_sourced(
                    f"planveyor_code_draft_stub_from_plan {shlex.quote(plan_rel)}",
                    cwd=root,
                )

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Machine-authority scaffold admission failed", result.stderr)
                self.assertEqual(plan.read_bytes(), plan_before)
                self.assertEqual(draft.read_bytes(), draft_before)
                self.assertEqual(self._state_snapshot(root), state_before)

    def test_decomposition_init_rejects_unsafe_paths_and_objects_before_mutation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_decomposition_paths_") as tmpdir:
            root = Path(tmpdir) / "repo"
            root.mkdir()
            self._init_git_repo(root)
            plans = root / "docs" / "plans"
            plans.mkdir(parents=True)
            outside = Path(tmpdir) / "outside.md"
            outside.write_text("outside\n", encoding="utf-8")
            symlink_target = plans / "symlink.md"
            symlink_target.symlink_to(outside)
            symlink_dir = plans / "linked"
            symlink_dir.symlink_to(Path(tmpdir), target_is_directory=True)
            directory_target = plans / "directory.md"
            directory_target.mkdir()
            fifo_target = plans / "fifo.md"
            os.mkfifo(fifo_target)
            root.joinpath(".planveyor.planpath").write_text("sentinel-plan\n", encoding="utf-8")
            root.joinpath(".planveyor.queue.json").write_text('{"sentinel": true}\n', encoding="utf-8")
            state_before = self._state_snapshot(root)
            cases = (
                "docs/plans/../escape.md",
                str(outside),
                "docs/plans/symlink.md",
                "docs/plans/linked/escape.md",
                "docs/plans/directory.md",
                "docs/plans/fifo.md",
                "docs/plans/missing-parent/nested.md",
                "docs/plans/not-markdown.txt",
            )

            for target in cases:
                with self.subTest(target=target):
                    result = self._run_decomposition_init(root, target)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("Refusing decomposition init", result.stderr)
                    self.assertEqual(self._state_snapshot(root), state_before)
                    self.assertEqual(outside.read_text(encoding="utf-8"), "outside\n")
                    self.assertFalse(root.joinpath(".manager_init_called").exists())
            self.assertFalse(plans.joinpath("missing-parent").exists())

    def test_decomposition_init_stamps_neutral_and_creates_missing_scaffold_idempotently(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_decomposition_green_") as tmpdir:
            root = Path(tmpdir)
            self._init_git_repo(root)
            neutral = self._write_neutral_plan(root, "docs/plans/neutral.md")

            stamped = self._run_decomposition_init(root, "docs/plans/neutral.md")

            self.assertEqual(stamped.returncode, 0, stamped.stderr)
            self.assertIn("Stamped decomposition overlay", stamped.stderr)
            stamped_text = neutral.read_text(encoding="utf-8")
            self.assertIn('"phase_overlay": "decomposition_wave"', stamped_text)
            self.assertIn('"phase_state": "active"', stamped_text)

            missing = root / "docs" / "plans" / "missing.md"
            created = self._run_decomposition_init(root, str(missing.resolve()))
            self.assertEqual(created.returncode, 0, created.stderr)
            self.assertIn("Created decomposition umbrella scaffold", created.stderr)
            self.assertTrue(missing.is_file())
            self.assertFalse(missing.is_symlink())
            self.assertEqual(
                root.joinpath(".planveyor.planpath").read_text(encoding="utf-8").splitlines()[-1],
                "docs/plans/missing.md",
            )
            created_bytes = missing.read_bytes()
            created_mtime = missing.stat().st_mtime_ns

            repeated = self._run_decomposition_init(root, "docs/plans/missing.md")
            self.assertEqual(repeated.returncode, 0, repeated.stderr)
            self.assertEqual(missing.read_bytes(), created_bytes)
            self.assertEqual(missing.stat().st_mtime_ns, created_mtime)

    def test_decomposition_init_rejects_ambiguous_plan_meta_without_rewrite(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_decomposition_ambiguous_") as tmpdir:
            root = Path(tmpdir)
            self._init_git_repo(root)
            plan = self._write_neutral_plan(root, "docs/plans/ambiguous.md")
            plan.write_text(
                plan.read_text(encoding="utf-8") + '\n```json\n{"plan_meta": {}}\n```\n',
                encoding="utf-8",
            )
            before = plan.read_bytes()

            result = self._run_decomposition_init(root, "docs/plans/ambiguous.md")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("exactly one parseable plan_meta", result.stderr)
            self.assertEqual(plan.read_bytes(), before)
            self.assertFalse(root.joinpath(".planveyor.planpath").exists())

    def test_manager_collab_cmd_analysis_explicit_plan_does_not_require_current_planpath(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_manager_analysis_cmd_") as tmpdir:
            fixture_repo = Path(tmpdir)
            self._init_git_repo(fixture_repo)
            self._write_minimal_plan(
                fixture_repo,
                "docs/plans/analysis_wave_fixture.md",
                wave_family="analysis_wave",
            )
            fixture_repo.joinpath(".planveyor.session.manager").write_text("fixture-session\n", encoding="utf-8")

            result = self._run_sourced(
                """
_planveyor_collab_snapshot_ids() { :; }
_planveyor_collab_log_transitions() { :; }
_planveyor_collab_agent_sync_all() { :; }
_planveyor_codex() {
  local payload="${argv[-1]}"
  print -r -- "$payload" > manager_payload.log
  return 0
}
planveyor_manager_collab_cmd analysis docs/plans/analysis_wave_fixture.md
""",
                cwd=fixture_repo,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(fixture_repo.joinpath(".planveyor.planpath").exists())
            payload = fixture_repo.joinpath("manager_payload.log").read_text(encoding="utf-8")
            self.assertEqual(payload.splitlines()[0], "ROLE=Manager")
            self.assertEqual(payload.splitlines()[-1], "MANAGER_CMD=analysis docs/plans/analysis_wave_fixture.md")
            self.assertNotIn("Plan status (pre):", result.stderr)

    def test_manager_collab_continuation_preserves_explicit_selector_and_canonical_prompt(self) -> None:
        cycle = "a651b30e-3eb5-4bc4-9ad5-3d087a0e1f79"
        with tempfile.TemporaryDirectory(prefix="planveyor_continuation_transport_") as d:
            root = Path(d); self._init_git_repo(root)
            self._write_minimal_plan(root, "docs/plans/continuation_fixture.md", wave_family="analysis_wave", required_manager_mode="either")
            root.joinpath(".planveyor.session.manager").write_text("fixture-session\n")
            root.joinpath(".planveyor.planpath").write_text("docs/plans/stale_pointer.md\n")
            root.joinpath(".planveyor.queue.json").write_text('{"sentinel": true}\n')
            before = self._state_snapshot(root)
            result = self._run_sourced('''
_planveyor_collab_snapshot_ids() { :; }
_planveyor_collab_log_transitions() { :; }
_planveyor_collab_agent_sync_all() { :; }
_planveyor_codex() { print -r -- "${argv[-1]}" > manager_payload.log; }
planveyor_manager_collab_cmd run docs/plans/continuation_fixture.md --followups-capture-cycle-id ''' + cycle + "\n", cwd=root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(before, self._state_snapshot(root))
            payload = root.joinpath("manager_payload.log").read_text()
            header, remainder = payload.split("[ALWAYS START]", 1)
            self.assertIn("PLAN_PATH=docs/plans/continuation_fixture.md\n", header)
            self.assertEqual(header.count("FOLLOWUPS_CAPTURE_CYCLE_ID="), 1)
            self.assertIn(f"FOLLOWUPS_CAPTURE_CYCLE_ID={cycle}\n", header)
            self.assertEqual(payload.splitlines()[-1], "MANAGER_CMD=run docs/plans/continuation_fixture.md")
            canonical = MANAGER_PROMPT.read_text().split("[ALWAYS START]", 1)[1]
            self.assertTrue(remainder.startswith(canonical.rstrip()))
            self.assertNotIn("stale_pointer", payload)

    def test_manager_collab_continuation_invalid_grammar_refuses_before_effects(self) -> None:
        cycle = "a651b30e-3eb5-4bc4-9ad5-3d087a0e1f79"
        forms = (
            "run docs/plans/p.md --followups-capture-cycle-id",
            f"run --followups-capture-cycle-id {cycle}",
            f"run Q --followups-capture-cycle-id {cycle}",
            f"status docs/plans/p.md --followups-capture-cycle-id {cycle}",
            "run docs/plans/p.md --followups-capture-cycle-id invalid",
            f"run docs/plans/p.md --followups-capture-cycle-id {cycle} extra",
            f"run docs/plans/p.md --followups-capture-cycle-id {cycle} --followups-capture-cycle-id {cycle}",
            f"run docs/plans/p.md --followups-capture-cycle-id={cycle}",
            f"run docs/plans/p.md {cycle}",
            f"run docs/plans/../p.md --followups-capture-cycle-id {cycle}",
        )
        with tempfile.TemporaryDirectory(prefix="planveyor_continuation_refusal_") as d:
            root = Path(d); self._init_git_repo(root)
            before = self._state_snapshot(root)
            for form in forms:
                with self.subTest(form=form):
                    result = self._run_sourced('''
_planveyor_authority_context_for_reader() { print EFFECT_AUTHORITY >&2; return 90; }
_planveyor_codex() { print EFFECT_PROVIDER >&2; return 91; }
planveyor_manager_collab_cmd ''' + form + "\n", cwd=root)
                    self.assertEqual(result.returncode, 1, result.stderr)
                    self.assertIn("Usage:", result.stderr)
                    self.assertNotIn("EFFECT_", result.stderr)
                    self.assertEqual(before, self._state_snapshot(root))

    def test_manager_collab_cmd_decomposition_explicit_plan_is_cold_transport_only(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_manager_decomposition_cmd_") as tmpdir:
            fixture_repo = Path(tmpdir)
            self._init_git_repo(fixture_repo)
            fixture_repo.joinpath(".planveyor.session.manager").write_text("fixture-session\n", encoding="utf-8")
            fixture_repo.joinpath(".planveyor.queue.json").write_text('{"sentinel": true}\n', encoding="utf-8")
            fixture_repo.joinpath(".planveyor.staging").write_text("sentinel\n", encoding="utf-8")
            state_before = self._state_snapshot(fixture_repo)
            target = "docs/plans/missing_decomposition.md"

            result = self._run_sourced(
                """
_planveyor_collab_snapshot_ids() { :; }
_planveyor_collab_log_transitions() { :; }
_planveyor_collab_agent_sync_all() { :; }
_planveyor_codex() {
  local payload="${argv[-1]}"
  print -r -- "$payload" > manager_payload.log
  return 0
}
planveyor_manager_collab_cmd decomposition docs/plans/missing_decomposition.md
""",
                cwd=fixture_repo,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(fixture_repo.joinpath(target).exists())
            self.assertFalse(fixture_repo.joinpath(".planveyor.planpath").exists())
            self.assertEqual(self._state_snapshot(fixture_repo), state_before)
            payload = fixture_repo.joinpath("manager_payload.log").read_text(encoding="utf-8")
            self.assertEqual(payload.splitlines()[0], "ROLE=Manager")
            self.assertEqual(payload.splitlines()[-1], f"MANAGER_CMD=decomposition {target}")
            self.assertNotIn("PLAN_PATH=", payload.split("[ALWAYS START]", 1)[0])
            self.assertNotIn("Plan status (pre):", result.stderr)

    def test_manager_custom_cmd_run_q_preserves_queue_sentinel_without_planpath(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_manager_custom_queue_cmd_") as tmpdir:
            fixture_repo = Path(tmpdir)
            self._init_git_repo(fixture_repo)
            fixture_repo.joinpath(".planveyor.session.manager").write_text("fixture-session\n", encoding="utf-8")

            for command, expected_cmd in (
                ("planveyor_manager_custom_pipeline_cmd run Q", "MANAGER_CMD=run Q"),
                ("planveyor_manager_custom_pipeline_cmd run_q", "MANAGER_CMD=run_q"),
            ):
                with self.subTest(command=command):
                    result = self._run_sourced(
                        """
_planveyor_collab_snapshot_ids() { :; }
_planveyor_collab_log_transitions() { :; }
_planveyor_collab_agent_sync_all() { :; }
_planveyor_codex() {
  local payload="${argv[-1]}"
  print -r -- "$payload" > manager_payload.log
  return 0
}
""" + command + "\n",
                        cwd=fixture_repo,
                    )

                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertFalse(fixture_repo.joinpath(".planveyor.planpath").exists())
                    payload = fixture_repo.joinpath("manager_payload.log").read_text(encoding="utf-8")
                    payload_header = payload.split("[ALWAYS START]", 1)[0]
                    self.assertEqual(payload.splitlines()[0], "ROLE=Manager")
                    self.assertEqual(payload.splitlines()[-1], expected_cmd)
                    self.assertNotIn("PLAN_PATH=Q", payload_header)
                    self.assertNotIn("PLAN_PATH=", payload_header)
                    self.assertNotIn("PRE_STATUS_LINE=", payload_header)
                    self.assertNotIn("Plan status (pre):", result.stderr)

            help_result = self._run_sourced(
                "_planveyor_help_cmd_usage planveyor_manager_custom_pipeline_cmd; "
                "_planveyor_help_cmd_example planveyor_manager_custom_pipeline_cmd; "
                "_planveyor_help_cmd_summary planveyor_manager_custom_pipeline_cmd",
                cwd=fixture_repo,
            )
            self.assertEqual(help_result.returncode, 0, help_result.stderr)
            self.assertIn("run [PLAN_PATH|Q]|run_q", help_result.stdout)
            self.assertIn("planveyor_manager_custom_pipeline_cmd run Q", help_result.stdout)
            self.assertIn("'run Q' = queue mode", help_result.stdout)

    def test_doctor_reports_target_and_fresh_shell_visibility(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_bare_doctor_") as tmpdir:
            target_dir = Path(tmpdir) / "bin"
            install = self._run_sourced(f"planveyor_bare_entrypoints_install --bin-dir {shlex.quote(str(target_dir))}")
            self.assertEqual(install.returncode, 0, install.stderr)

            child_tmp = (Path(tmpdir) / "child_tmp").resolve()
            child_tmp.mkdir()
            home = Path(tmpdir) / "home"
            home.mkdir()
            env = {
                "PATH": f"{target_dir}{os.pathsep}{os.environ.get('PATH', os.defpath)}",
                "HOME": str(home),
                "TMPDIR": str(child_tmp),
                "TMPPREFIX": str(child_tmp / "zsh"),
                "PLANVEYOR_ROOT": str(REPO_ROOT),
                "BIN_DIR": str(target_dir),
            }
            doctor = subprocess.run(
                [
                    "/bin/zsh",
                    "-c",
                    'planveyor_bare_entrypoints_doctor --bin-dir "$BIN_DIR" && '
                    'print -r -- "C03_DOCTOR_TMP=$TMPDIR|$TMPPREFIX"',
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )

            self.assertEqual(doctor.returncode, 0, doctor.stderr)
            self.assertIn(
                f"C03_DOCTOR_TMP={child_tmp}|{child_tmp / 'zsh'}",
                doctor.stdout.splitlines(),
            )
            out = doctor.stdout
            self.assertIn(f"Target dir: {target_dir}", out)
            self.assertIn("Target dir in PATH: yes", out)
            self.assertIn(f"installed planveyor_bare_entrypoints_doctor -> {target_dir / 'planveyor_bare_entrypoints_doctor'}", out)
            self.assertIn(f"installed planveyor_docs_hygiene_suggest -> {target_dir / 'planveyor_docs_hygiene_suggest'}", out)
            self.assertIn(f"visible   planveyor_bare_entrypoints_doctor -> {target_dir / 'planveyor_bare_entrypoints_doctor'}", out)
            self.assertIn(f"visible   planveyor_docs_hygiene_archive -> {target_dir / 'planveyor_docs_hygiene_archive'}", out)

    def test_bare_shim_provenance_is_runtime_neutral_and_static(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_bare_provenance_") as tmpdir:
            temp_root = Path(tmpdir)
            home = temp_root / "home"
            stable_root = home / "planveyor"
            linked_root = temp_root / "linked_worktree"
            for tooling_root in (stable_root, linked_root):
                scripts_dir = tooling_root / "scripts"
                scripts_dir.mkdir(parents=True)
                shutil.copy2(PLANVEYOR_SCRIPT, scripts_dir / "planveyor.zsh")
                shutil.copytree(REPO_ROOT / "scripts" / "planveyor", scripts_dir / "planveyor")
                for source_path in AUTHORITY_BRIDGE_RUNTIME_FILES:
                    shutil.copy2(source_path, scripts_dir / source_path.name)

            target_dir = temp_root / "bin"
            target_dir.mkdir()
            shim_path = target_dir / "planveyor_bare_entrypoints_doctor"
            rendered = self._run_sourced(
                "_planveyor_bare_entrypoints_render_shim planveyor_bare_entrypoints_doctor "
                f"{shlex.quote(str(linked_root))} > {shlex.quote(str(shim_path))} && "
                f"chmod 755 {shlex.quote(str(shim_path))}",
                extra_env={"HOME": str(home)},
            )
            self.assertEqual(rendered.returncode, 0, rendered.stderr)
            shim_text = shim_path.read_text(encoding="utf-8")
            self.assertIn("# planveyor_bare_entrypoints_shim_format=v1", shim_text)
            self.assertIn(f"# installer_tooling_root='{linked_root}'", shim_text)
            self.assertIn('stable_tooling_root="${HOME}/planveyor"', shim_text)
            self.assertNotIn("baked_tooling_root=", shim_text)
            self.assertNotIn(f'planveyor_root="{linked_root}"', shim_text)

            child_tmp = (temp_root / "child_tmp").resolve()
            child_tmp.mkdir()
            bare_env = {
                "PATH": f"{target_dir}{os.pathsep}{os.environ.get('PATH', os.defpath)}",
                "HOME": str(home),
                "TMPDIR": str(child_tmp),
                "TMPPREFIX": str(child_tmp / "zsh"),
                "BIN_DIR": str(target_dir),
            }
            stable = subprocess.run(
                [
                    "/bin/zsh",
                    "-c",
                    'planveyor_bare_entrypoints_doctor --bin-dir "$BIN_DIR" && '
                    'print -r -- "C03_PROVENANCE_TMP=$TMPDIR|$TMPPREFIX"',
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                env=bare_env,
                check=False,
            )
            self.assertEqual(stable.returncode, 0, stable.stderr)
            self.assertIn(
                f"C03_PROVENANCE_TMP={child_tmp}|{child_tmp / 'zsh'}",
                stable.stdout.splitlines(),
            )
            self.assertIn(
                "provenance planveyor_bare_entrypoints_doctor: "
                f"shim_state=installed; resolved_tooling_root={stable_root}; "
                "provenance_state=stable_default; "
                "repair_state=not_available_from_facade",
                stable.stdout,
            )

            override_env = bare_env.copy()
            override_env["PLANVEYOR_ROOT"] = str(linked_root)
            override = subprocess.run(
                ["/bin/zsh", "-c", 'planveyor_bare_entrypoints_doctor --bin-dir "$BIN_DIR"'],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                env=override_env,
                check=False,
            )
            self.assertEqual(override.returncode, 0, override.stderr)
            self.assertIn(
                "provenance planveyor_bare_entrypoints_doctor: "
                f"shim_state=installed; resolved_tooling_root={linked_root}; "
                "provenance_state=runtime_override; "
                "repair_state=not_available_from_facade",
                override.stdout,
            )

            arbitrary_marker = temp_root / "arbitrary_shim_executed"
            wrong_command = self._run_sourced(
                "_planveyor_bare_entrypoints_render_shim planveyor_docs_hygiene_suggest "
                f"{shlex.quote(str(linked_root))}",
                extra_env={"HOME": str(home)},
            )
            self.assertEqual(wrong_command.returncode, 0, wrong_command.stderr)
            truncated_shim = shim_text.split('script_path=', 1)[0]
            invalid_fixtures = {
                "arbitrary_executable": "#!/bin/zsh\n"
                f"touch {shlex.quote(str(arbitrary_marker))}\n",
                "truncated_managed_shim": truncated_shim,
                "wrong_command_shim": wrong_command.stdout,
            }
            expected_unmanaged = (
                "provenance planveyor_bare_entrypoints_doctor: "
                "shim_state=unmanaged; resolved_tooling_root=N/A; "
                "provenance_state=unreadable; "
                "repair_state=not_available_from_facade"
            )
            for fixture_name, fixture_text in invalid_fixtures.items():
                shim_path.write_text(fixture_text, encoding="utf-8")
                shim_path.chmod(0o755)
                for resolver_name, command, extra_env in (
                    (
                        "stable_default",
                        "unset PLANVEYOR_ROOT; "
                        f"planveyor_bare_entrypoints_doctor --bin-dir {shlex.quote(str(target_dir))}",
                        {"HOME": str(home)},
                    ),
                    (
                        "runtime_override",
                        f"planveyor_bare_entrypoints_doctor --bin-dir {shlex.quote(str(target_dir))}",
                        {"HOME": str(home), "PLANVEYOR_ROOT": str(linked_root)},
                    ),
                ):
                    with self.subTest(fixture=fixture_name, resolver=resolver_name):
                        invalid = self._run_sourced(command, extra_env=extra_env)
                        self.assertEqual(invalid.returncode, 0, invalid.stderr)
                        self.assertFalse(arbitrary_marker.exists(), "doctor must not execute inspected shims")
                        self.assertIn(expected_unmanaged, invalid.stdout)

            repaired = self._run_sourced(
                "_planveyor_bare_entrypoints_render_shim planveyor_bare_entrypoints_doctor "
                f"{shlex.quote(str(linked_root))} > {shlex.quote(str(shim_path))} && "
                f"chmod 755 {shlex.quote(str(shim_path))}",
                extra_env={"HOME": str(home)},
            )
            self.assertEqual(repaired.returncode, 0, repaired.stderr)
            repaired_stable = self._run_sourced(
                "unset PLANVEYOR_ROOT; "
                f"planveyor_bare_entrypoints_doctor --bin-dir {shlex.quote(str(target_dir))}",
                extra_env={"HOME": str(home)},
            )
            self.assertEqual(repaired_stable.returncode, 0, repaired_stable.stderr)
            self.assertIn(
                "provenance planveyor_bare_entrypoints_doctor: "
                f"shim_state=installed; resolved_tooling_root={stable_root}; "
                "provenance_state=stable_default; "
                "repair_state=not_available_from_facade",
                repaired_stable.stdout,
            )
            repaired_override = self._run_sourced(
                f"planveyor_bare_entrypoints_doctor --bin-dir {shlex.quote(str(target_dir))}",
                extra_env={"HOME": str(home), "PLANVEYOR_ROOT": str(linked_root)},
            )
            self.assertEqual(repaired_override.returncode, 0, repaired_override.stderr)
            self.assertIn(
                "provenance planveyor_bare_entrypoints_doctor: "
                f"shim_state=installed; resolved_tooling_root={linked_root}; "
                "provenance_state=runtime_override; "
                "repair_state=not_available_from_facade",
                repaired_override.stdout,
            )

            legacy_dir = temp_root / "legacy_bin"
            legacy_dir.mkdir()
            legacy_shim = legacy_dir / "planveyor_bare_entrypoints_doctor"
            legacy_marker = temp_root / "legacy_shim_executed"
            legacy_shim.write_text(
                "#!/bin/zsh\n"
                f"baked_tooling_root='{linked_root}'\n"
                f"touch '{legacy_marker}'\n",
                encoding="utf-8",
            )
            legacy_shim.chmod(0o755)
            legacy = self._run_sourced(
                "unset PLANVEYOR_ROOT; "
                f"planveyor_bare_entrypoints_doctor --bin-dir {shlex.quote(str(legacy_dir))}",
                extra_env={"HOME": str(home)},
            )
            self.assertEqual(legacy.returncode, 0, legacy.stderr)
            self.assertFalse(legacy_marker.exists(), "doctor must not execute inspected shims")
            self.assertIn(
                "provenance planveyor_bare_entrypoints_doctor: "
                f"shim_state=installed; resolved_tooling_root={linked_root}; "
                "provenance_state=legacy_baked_ephemeral; "
                "repair_state=not_available_from_facade",
                legacy.stdout,
            )

    def test_doctor_warns_when_target_dir_is_not_in_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_bare_doctor_") as tmpdir:
            target_dir = Path(tmpdir) / "bin"
            install = self._run_sourced(f"planveyor_bare_entrypoints_install --bin-dir {shlex.quote(str(target_dir))}")
            self.assertEqual(install.returncode, 0, install.stderr)

            doctor = self._run_sourced(f"planveyor_bare_entrypoints_doctor --bin-dir {shlex.quote(str(target_dir))}")

            self.assertEqual(doctor.returncode, 0, doctor.stderr)
            self.assertIn("Target dir in PATH: no", doctor.stdout)
            self.assertIn(f"Hint: prepend {target_dir} to PATH before testing bare commands in a fresh shell.", doctor.stdout)

    def test_owner_runbook_does_not_promise_unavailable_bare_installer(self) -> None:
        for runbook in (OWNER_RUNBOOK, OWNER_RUNBOOK_RU):
            with self.subTest(runbook=runbook.name):
                text = runbook.read_text(encoding="utf-8")

                self.assertNotIn("planveyor_bare_entrypoints_install", text)
                self.assertNotIn("repair_command=", text)

    def test_owner_runbook_documents_selected_gate_claims(self) -> None:
        for runbook in (OWNER_RUNBOOK, OWNER_RUNBOOK_RU):
            with self.subTest(runbook=runbook.name):
                text = runbook.read_text(encoding="utf-8")

                self.assertIn(
                    "planveyor_plan_bundle --preflight docs/plans/YYYYMMDD_HHMM_topic.md",
                    text,
                )
                self.assertIn(
                    "planveyor_plan_bundle --check docs/plans/YYYYMMDD_HHMM_topic.md",
                    text,
                )
                self.assertIn(
                    "planveyor_plan_bundle --scope-check docs/plans/YYYYMMDD_HHMM_topic.md",
                    text,
                )
                self.assertIn("`scope_ok=true`", text)
        self.assertIn(
            "The first executable Planner handoff requires strict `--preflight`.",
            OWNER_RUNBOOK.read_text(encoding="utf-8"),
        )
        self.assertIn(
            "требует строгой предварительной проверки `--preflight`.",
            OWNER_RUNBOOK_RU.read_text(encoding="utf-8"),
        )
        for runbook, inventory, permission, final in (
            (OWNER_RUNBOOK, "only for inventory and integrity", "Scope grants no route, green verdict or commit permission.",
             "Final lint and strict `--check` still evaluate the completed review."),
            (OWNER_RUNBOOK_RU, "только для состава и целостности набора",
             "Проверка состава набора не даёт ни маршрута, ни зелёного вердикта, ни разрешения на коммит.",
             "Готовое ревью по-прежнему оценивают финальный линтер и строгий `--check`."),
        ):
            with self.subTest(runbook=runbook.name):
                text = runbook.read_text(encoding="utf-8")
                self.assertIn(inventory, text)
                self.assertIn(permission, text)
                self.assertIn(final, text)

    def test_terminal_capture_options_are_forwarded_without_shell_reinterpretation(self) -> None:
        with temporary_git_root(prefix="planveyor_terminal_forwarding_") as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260721_0204_fixture.md"
            plan = root / plan_rel
            plan.parent.mkdir(parents=True)
            plan.write_text("# fixture\n", encoding="utf-8")
            scripts = root / "scripts"
            scripts.mkdir()
            shutil.copy2(REPO_ROOT / "scripts" / "followups_capture.py", scripts / "followups_capture.py")
            cycle_id = "123e4567-e89b-42d3-a456-426614174000"

            common = (
                f"function _planveyor_root() {{ print -r -- {shlex.quote(str(root))}; }}; "
                "function _planveyor_py_any() { "
                '[[ "${1:-}" == "-" && "${2:-}" == "applicable" ]] && return 3; '
                'print -l -- "$@"; '
                "}; "
            )
            docs_closeout = self._run_sourced(
                common
                + "function planveyor_plan_bundle() { print -r -- '{\"schema\":\"fixture\"}'; }; "
                + f"planveyor_docs_closeout {plan_rel} --followups-capture-cycle-id {cycle_id} --json",
                cwd=root,
            )
            self.assertEqual(docs_closeout.returncode, 0, docs_closeout.stderr)
            self.assertIn("--followups-capture-cycle-id", docs_closeout.stdout)
            self.assertIn(cycle_id, docs_closeout.stdout)
            self.assertIn("--bundle-json", docs_closeout.stdout)

            preflight = self._run_sourced(
                common
                + f"planveyor_plan_closeout_preflight --docs-closeout-json - --json {plan_rel}",
                cwd=root,
            )
            self.assertEqual(preflight.returncode, 0, preflight.stderr)
            self.assertIn("preflight", preflight.stdout)
            self.assertIn("--docs-closeout-json", preflight.stdout)
            self.assertIn("-", preflight.stdout.splitlines())

            commit = self._run_sourced(
                common
                + f"planveyor_plan_bundle --commit-exact --preflight-json - --message-auto {plan_rel}",
                cwd=root,
            )
            self.assertEqual(commit.returncode, 0, commit.stderr)
            self.assertIn("commit-exact", commit.stdout)
            self.assertIn("--preflight-json", commit.stdout)
            self.assertIn("--message-auto", commit.stdout)
            self.assertNotIn("--message-file", commit.stdout)

            usage = self._run_sourced("planveyor_help")
            self.assertEqual(usage.returncode, 0, usage.stderr)
            self.assertIn("--message-auto", usage.stdout)
            self.assertIn("--message-file <path>", usage.stdout)

    def test_closeout_helpers_use_consumer_project_and_runtime_scripts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_closeout_root_") as tmpdir:
            consumer_root = Path(tmpdir).resolve()
            runtime_root = REPO_ROOT.resolve()
            plan_rel = "docs/plans/fixture.md"
            plan = consumer_root / plan_rel
            plan.parent.mkdir(parents=True)
            plan.write_text("# fixture\n", encoding="utf-8")
            generation = "0" * 64
            common = (
                "_planveyor_authority_context_for_reader() { print -r -- '{}'; }; "
                "_planveyor_authority_context_bindings() { "
                f"printf '%s\\t%s\\t%s\\t\\n' legacy {shlex.quote(str(consumer_root))} {generation}; "
                "}; "
                f"_planveyor_project_root() {{ print -r -- {shlex.quote(str(consumer_root))}; }}; "
                f"_planveyor_root() {{ print -r -- {shlex.quote(str(runtime_root))}; }}; "
                f"_planveyor_closeout_tooling_root() {{ print -r -- {shlex.quote(str(runtime_root))}; }}; "
                "_planveyor_py_any() { print -l -- \"$@\"; }; "
            )
            docs_closeout = self._run_sourced(
                common
                + "planveyor_plan_bundle() { print -r -- '{\"schema\":\"fixture\"}'; }; "
                + f"planveyor_docs_closeout {shlex.quote(plan_rel)} --json",
                cwd=consumer_root,
            )
            self.assertEqual(docs_closeout.returncode, 0, docs_closeout.stderr)
            self.assertIn(str(runtime_root / "scripts" / "docs_closeout.py"), docs_closeout.stdout)
            self.assertIn("--project-root", docs_closeout.stdout)
            self.assertIn(str(consumer_root), docs_closeout.stdout)

            preflight = self._run_sourced(
                common + f"planveyor_plan_closeout_preflight --docs-closeout-json - --json {shlex.quote(plan_rel)}",
                cwd=consumer_root,
            )
            self.assertEqual(preflight.returncode, 0, preflight.stderr)
            self.assertIn(str(runtime_root / "scripts" / "followups_capture.py"), preflight.stdout)
            self.assertIn("--project-root", preflight.stdout)
            self.assertIn(str(consumer_root), preflight.stdout)

    def test_public_child_split_runtime_prefers_runtime_bundle_modules(self) -> None:
        """A populated consumer scripts tree cannot preempt the pinned runtime."""
        with AuthorityFixture(identity="planveyor") as fixture:
            entry = write(
                fixture.runtime_root,
                "bin/planveyor",
                (REPO_ROOT / "bin" / "planveyor").read_bytes(),
                executable=True,
            )
            commit_all(fixture.runtime_root, "public child entry")

            shutil.copytree(fixture.runtime_root / "scripts", fixture.target_root / "scripts")
            vocabulary = fixture.target_root / "docs" / "_meta" / "plan_vocab.json"
            vocabulary.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO_ROOT / "docs" / "_meta" / "plan_vocab.json", vocabulary)
            plan_rel = "docs/plans/260921_0000_split_runtime_fixture.md"
            self._write_na_authority_plan(fixture.target_root, plan_rel)
            write(fixture.target_root, ".planveyor.pybin", f"{Path(sys.executable).resolve()}\n")
            commit_all(fixture.target_root, "populated consumer scripts")

            state_root = fixture.root / "state"
            state_root.mkdir()
            environment = fixture.environment()
            environment["PLANVEYOR_STATE_ROOT"] = str(state_root)
            result = subprocess.run(
                [
                    str(entry),
                    "--project",
                    str(fixture.target_root),
                    "planveyor_docs_closeout",
                    plan_rel,
                    "--json",
                ],
                cwd=fixture.target_root,
                env=environment,
                stdin=subprocess.DEVNULL,
                text=True,
                capture_output=True,
                check=False,
                timeout=120,
            )

        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["schema"], "docs_closeout_payload.v1")
        self.assertEqual(payload["schema_state"], "ok")
        self.assertEqual(payload["plan_ref"], plan_rel)
        self.assertEqual(payload["semantic_status"], "Ready for Planner")
        self.assertEqual(payload["state"], "no_op")
        self.assertEqual(payload["semantic_closeout_kind"], "needs_rerun")
        self.assertNotIn("authority_module_origin_mismatch", output)
        self.assertNotIn("contract_authority_bridge: internal_error", output)

    def test_rollout_packet_helper_uses_consumer_repo_and_runtime_script(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_packet_root_") as tmpdir:
            fixture = Path(tmpdir).resolve()
            consumer_root = fixture / "consumer"
            consumer_root.mkdir()
            capture = fixture / "capture.sh"
            capture.write_text(
                "#!/bin/sh\n"
                'printf "cwd=%s\\n" "$PWD"\n'
                'for argument in "$@"; do printf "arg=%s\\n" "$argument"; done\n',
                encoding="utf-8",
            )
            capture.chmod(0o700)
            runtime_root = REPO_ROOT.resolve()
            generation = "0" * 64
            command = (
                "_planveyor_authority_context_for_reader() { print -r -- '{}'; }; "
                "_planveyor_authority_context_bindings() { "
                f"printf '%s\\t%s\\t%s\\t\\n' legacy {shlex.quote(str(consumer_root))} {generation}; "
                "}; "
                f"_planveyor_project_root() {{ print -r -- {shlex.quote(str(consumer_root))}; }}; "
                f"_planveyor_root() {{ print -r -- {shlex.quote(str(runtime_root))}; }}; "
                f"_planveyor_get_pybin() {{ print -r -- {shlex.quote(str(capture))}; }}; "
                "_planveyor_rollout_packet_helper_run query --json"
            )
            result = self._run_sourced(command, cwd=consumer_root)

            self.assertEqual(result.returncode, 0, result.stderr)
            observed = [
                line
                for line in result.stdout.splitlines()
                if line.startswith(("cwd=", "arg="))
            ]
            self.assertEqual(
                observed,
                [
                    f"cwd={consumer_root}",
                    f"arg={runtime_root / 'scripts' / 'rollout_packet.py'}",
                    "arg=--repo-root",
                    f"arg={consumer_root}",
                    "arg=--tooling-root",
                    f"arg={runtime_root}",
                    "arg=query",
                    "arg=--json",
                ],
            )

            marker = fixture / "unexpected-helper-execution"
            blocked = fixture / "blocked.sh"
            blocked.write_text(
                "#!/bin/sh\n"
                f"printf 'unexpected\\n' > {shlex.quote(str(marker))}\n",
                encoding="utf-8",
            )
            blocked.chmod(0o700)
            invalid = self._run_sourced(
                "_planveyor_authority_context_for_reader() { print -r -- '{}'; }; "
                "_planveyor_authority_context_bindings() { "
                f"printf '%s\\t%s\\t%s\\t\\n' legacy {shlex.quote(str(consumer_root))} {generation}; "
                "}; "
                "_planveyor_project_root() { return 1; }; "
                f"_planveyor_root() {{ print -r -- {shlex.quote(str(runtime_root))}; }}; "
                f"_planveyor_get_pybin() {{ print -r -- {shlex.quote(str(blocked))}; }}; "
                "_planveyor_rollout_packet_helper_run query --json",
                cwd=consumer_root,
            )
            self.assertNotEqual(invalid.returncode, 0)
            self.assertFalse(marker.exists(), invalid.stdout + invalid.stderr)

    def test_planpath_missing_recovers_with_setter_and_preserves_empty_failure(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_planpath_recovery_") as tmpdir:
            fixture = Path(tmpdir).resolve()
            consumer_root = fixture / "consumer"
            consumer_root.mkdir()
            common = self._root_split_shell(consumer_root, REPO_ROOT.resolve())

            missing = self._run_sourced(common + "planveyor_planpath", cwd=consumer_root)
            self.assertEqual(missing.returncode, 1)
            self.assertEqual(missing.stdout, "")
            self.assertEqual(
                missing.stderr,
                "No selected plan. Select an existing plan with:\n"
                "planveyor_plan_set <PLAN_PATH>\n",
            )

            pointer = consumer_root / ".planveyor.planpath"
            pointer.write_text("\n", encoding="utf-8")
            empty = self._run_sourced(common + "planveyor_planpath", cwd=consumer_root)
            self.assertEqual(empty.returncode, 1)
            self.assertEqual(empty.stdout, "")
            self.assertEqual(empty.stderr, f"Empty file: {pointer}\n")

            pointer.write_text("docs/plans/consumer.md\n", encoding="utf-8")
            selected = self._run_sourced(common + "planveyor_planpath", cwd=consumer_root)
            self.assertEqual(selected.returncode, 0, selected.stderr)
            self.assertEqual(selected.stdout, "docs/plans/consumer.md\n")

    def test_missing_session_recovery_names_existing_init_or_fallback_setter(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_session_recovery_") as tmpdir:
            consumer_root = (Path(tmpdir) / "consumer").resolve()
            consumer_root.mkdir()
            common = self._root_split_shell(consumer_root, REPO_ROOT.resolve())
            expected = {
                "manager": "planveyor_manager_init",
                "reviewer_code_risk": "planveyor_reviewer_code_risk_init",
                "reviewer_code_contracts": "planveyor_reviewer_code_contracts_init",
            }
            for session_state, session_stub in (
                ("missing", "planveyor_session() { return 1; }; "),
                ("placeholder", "planveyor_session() { print -r -- '<SESSION_ID>'; }; "),
            ):
                for key, init_command in expected.items():
                    with self.subTest(session_state=session_state, session_key=key):
                        result = self._run_sourced(
                            common
                            + session_stub
                            + f"_planveyor_session_sid_ensure_in_effective_codex_home {shlex.quote(key)}",
                            cwd=consumer_root,
                        )
                        self.assertEqual(result.returncode, 1)
                        self.assertEqual(result.stdout, "")
                        self.assertEqual(
                            result.stderr,
                            f"Missing session id. Initialize it first: {init_command}\n",
                        )

            fallback = self._run_sourced(
                common
                + "planveyor_session() { return 1; }; "
                + "_planveyor_session_sid_ensure_in_effective_codex_home another_role",
                cwd=consumer_root,
            )
            self.assertEqual(fallback.returncode, 1)
            self.assertEqual(fallback.stdout, "")
            self.assertEqual(
                fallback.stderr,
                "Missing session id. Set it first: planveyor_session_set another_role <SESSION_ID>\n",
            )

    def test_engaged_public_paths_recover_with_existing_init_without_downstream_effects(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_engaged_session_recovery_") as tmpdir:
            fixture = Path(tmpdir).resolve()
            consumer_root = fixture / "consumer"
            consumer_root.mkdir()
            marker = fixture / "downstream-called"
            common = self._root_split_shell(consumer_root, REPO_ROOT.resolve(), state="engaged")
            guard = (
                "_planveyor_role_prompt_body() { print -r -- fixture; }; "
                "_planveyor_profile_for_role_mode() { return 0; }; "
                "planveyor_session() { return 1; }; "
                "planveyor_planpath() { print -r -- docs/plans/fixture.md; }; "
                "_planveyor_resolve_pybin_for_role() { print -r -- /usr/bin/python3; }; "
                "planveyor_runner() { print -r -- codex; }; "
                f"_planveyor_session_authority_resume_validate() {{ print -r -- unexpected > {shlex.quote(str(marker))}; return 99; }}; "
                f"_planveyor_manager_mode_admit() {{ print -r -- unexpected > {shlex.quote(str(marker))}; return 99; }}; "
                f"_planveyor_codex() {{ print -r -- unexpected > {shlex.quote(str(marker))}; return 99; }}; "
                f"planveyor_manager_init() {{ print -r -- unexpected > {shlex.quote(str(marker))}; return 99; }}; "
                f"planveyor_reviewer_code_risk_init() {{ print -r -- unexpected > {shlex.quote(str(marker))}; return 99; }}; "
                f"planveyor_reviewer_code_contracts_init() {{ print -r -- unexpected > {shlex.quote(str(marker))}; return 99; }}; "
            )

            manager = self._run_sourced(common + guard + "planveyor_manager_collab_tui", cwd=consumer_root)
            self.assertEqual(manager.returncode, 1)
            self.assertEqual(manager.stdout, "")
            self.assertEqual(
                manager.stderr,
                "Missing session id. Initialize it first: planveyor_manager_init\n",
            )
            self.assertFalse(marker.exists(), manager.stdout + manager.stderr)

            manager_placeholder = self._run_sourced(
                common
                + guard
                + "planveyor_session() { print -r -- '<SESSION_ID>'; }; "
                + "planveyor_manager_collab_tui",
                cwd=consumer_root,
            )
            self.assertEqual(manager_placeholder.returncode, 1)
            self.assertEqual(manager_placeholder.stdout, "")
            self.assertEqual(
                manager_placeholder.stderr,
                "Missing session id. Initialize it first: planveyor_manager_init\n",
            )
            self.assertFalse(marker.exists(), manager_placeholder.stdout + manager_placeholder.stderr)

            for command, init_command in (
                ("planveyor_reviewer_code_risk", "planveyor_reviewer_code_risk_init"),
                ("planveyor_reviewer_code_contracts", "planveyor_reviewer_code_contracts_init"),
            ):
                with self.subTest(command=command):
                    result = self._run_sourced(common + guard + command, cwd=consumer_root)
                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(result.stdout, "")
                    self.assertEqual(
                        result.stderr,
                        f"Missing session id. Initialize it first: {init_command}\n",
                    )
                    self.assertFalse(marker.exists(), result.stdout + result.stderr)

            for session_key, init_command in (
                ("reviewer_code_risk", "planveyor_reviewer_code_risk_init"),
                ("reviewer_code_contracts", "planveyor_reviewer_code_contracts_init"),
            ):
                with self.subTest(managed_role=session_key):
                    managed_guard = (
                        guard
                        + f"_planveyor_role_runner_preflight_normalize() {{ print -r -- 'role=reviewer;session_key={session_key};wrapper=fixture;runner_role=reviewer;unsupported='; }}; "
                        + "_planveyor_explicit_plan_normalize() { print -r -- docs/plans/fixture.md; }; "
                        + "_planveyor_ui_source_binding_validate() { return 0; }; "
                    )
                    result = self._run_sourced(
                        common + managed_guard + f"planveyor_role_run {session_key}",
                        cwd=consumer_root,
                    )
                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(result.stdout, "")
                    self.assertEqual(
                        result.stderr,
                        f"Missing session id. Initialize it first: {init_command}\n",
                    )
                    self.assertFalse(marker.exists(), result.stdout + result.stderr)

    def test_launch_docs_keep_normal_tui_and_recovery_boundaries(self) -> None:
        guide = LAUNCH_GUIDE.read_text(encoding="utf-8")
        guide_ru = LAUNCH_GUIDE_RU.read_text(encoding="utf-8")
        runbook = OWNER_RUNBOOK.read_text(encoding="utf-8")
        runbook_ru = OWNER_RUNBOOK_RU.read_text(encoding="utf-8")
        facade = PLANVEYOR_SCRIPT.read_text(encoding="utf-8")
        readmes = (
            PROJECT_README.read_text(encoding="utf-8"),
            PROJECT_README_RU.read_text(encoding="utf-8"),
        )
        short_references = (
            OWNER_BOOK.read_text(encoding="utf-8"),
            TOOLS_SNIPPET.read_text(encoding="utf-8"),
            AGENTS_GUIDE.read_text(encoding="utf-8"),
        )

        for language, text, live_tui_row, stale_queue_row, queue_branch in (
            (
                "en",
                guide,
                "| Run single-plan Manager collab in the live TUI | `./bin/planveyor planveyor_manager_collab_tui` |",
                "| Open native/collab TUI | `./bin/planveyor planveyor_manager_collab_tui --q` |",
                "The queue is a separate advanced branch",
            ),
            (
                "ru",
                guide_ru,
                "| Запустить Manager в режиме collab для одного плана в живом TUI | `./bin/planveyor planveyor_manager_collab_tui` |",
                "| Открыть native/collab TUI | `./bin/planveyor planveyor_manager_collab_tui --q` |",
                "Очередь — отдельный расширенный маршрут",
            ),
        ):
            with self.subTest(launch_guide=language):
                self.assertIn(live_tui_row, text)
                self.assertNotIn(stale_queue_row, text)
                self.assertNotIn("| `./bin/planveyor planveyor_manager_collab_tui --q` |", text)
                self.assertIn(queue_branch, text)
                self.assertIn("planveyor_manager_collab_tui --q", text)
        for text in (runbook, runbook_ru):
            self.assertRegex(text, r"\n\./bin/planveyor planveyor_manager_collab_tui\n")
        self.assertIn("The queue is a separate advanced branch", runbook)
        self.assertIn("Очередь — отдельный расширенный маршрут", runbook_ru)
        self.assertIn(
            'planveyor_manager_collab_tui) echo "planveyor_manager_collab_tui" ;;',
            facade,
        )
        self.assertNotIn(
            'planveyor_manager_collab_tui) echo "planveyor_manager_collab_tui --q" ;;',
            facade,
        )

        for init_command in (
            "planveyor_manager_init",
            "planveyor_arch_init",
            "planveyor_planner_init",
            "planveyor_coder_init",
            "planveyor_reviewer_code_risk_init",
            "planveyor_reviewer_code_contracts_init",
        ):
            with self.subTest(init_command=init_command):
                self.assertIn(init_command, guide)
                self.assertIn(init_command, guide_ru)
                self.assertIn(init_command, runbook)
                self.assertIn(init_command, runbook_ru)

        self.assertIn("planveyor_reviewer_init` does not replace", guide)
        self.assertIn("planveyor_reviewer_init` не заменяет", guide_ru)
        self.assertIn("planveyor_reviewer_init` does not replace", runbook)
        self.assertIn("planveyor_reviewer_init` не заменяет", runbook_ru)
        for text in (guide, guide_ru):
            self.assertIn("planveyor_plan_set <PLAN_PATH>", text)
            self.assertIn("source identity", text)
        self.assertIn("does not prove authentication", guide)
        self.assertIn("не доказывают ни аутентификацию", guide_ru)
        self.assertIn("source identity", runbook)
        self.assertIn("source identity", runbook_ru)
        self.assertIn("configured agent harness", guide)
        self.assertIn("Настроенный агентный харнес", guide_ru)
        self.assertIn("configured agent harness", runbook)
        self.assertIn("Настроенный агентный харнес", runbook_ru)
        for readme in readmes:
            self.assertIn("source identity", readme)
        self.assertIn("configured agent harness", readmes[0])
        self.assertIn("Настроенный агентный харнес", readmes[1])
        self.assertIn("source identity", AGENTS_GUIDE.read_text(encoding="utf-8"))
        for document in readmes + short_references:
            self.assertIn("git", document)
            self.assertIn("doctor", document.lower())

    def test_decomposition_root_split_uses_consumer_plan_and_runtime_template(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_decomposition_root_split_") as tmpdir:
            fixture = Path(tmpdir).resolve()
            consumer_root = fixture / "consumer"
            consumer_root.joinpath("docs", "plans").mkdir(parents=True)
            runtime_root = REPO_ROOT.resolve()
            plan_rel = "docs/plans/consumer_only.md"
            runtime_plan = runtime_root / plan_rel
            self.assertFalse(runtime_plan.exists())
            common = self._root_split_shell(consumer_root, runtime_root)
            command = (
                common
                + f"row=\"$(_planveyor_decomposition_plan_admission {shlex.quote(plan_rel)})\" || exit $?; "
                "IFS=$'\\t' read -r admission plan_path plan_fs expected_hash expected_identity <<< \"$row\" || exit $?; "
                "_planveyor_decomposition_bootstrap_plan_file \"$plan_fs\" \"$plan_path\" \"$admission\" \"$expected_hash\" \"$expected_identity\" || exit $?; "
                "print -r -- \"admission=$row\"; "
                "_planveyor_plan_phase_overlay_state \"$plan_path\""
            )
            result = self._run_sourced(command, cwd=consumer_root)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(
                "admission=missing\t" + plan_rel + "\t" + str(consumer_root / plan_rel),
                result.stdout,
            )
            created = consumer_root / plan_rel
            self.assertTrue(created.is_file())
            self.assertIn('"phase_overlay": "decomposition_wave"', created.read_text(encoding="utf-8"))
            self.assertIn('"phase_state": "active"', created.read_text(encoding="utf-8"))
            self.assertFalse(runtime_plan.exists())

            marker = fixture / "unexpected-admission"
            blocked = self._run_sourced(
                common
                + "_planveyor_project_root() { return 1; }; "
                + f"_planveyor_py_any_authority_stdin() {{ print -r -- unexpected > {shlex.quote(str(marker))}; }}; "
                + "_planveyor_decomposition_plan_admission docs/plans/blocked.md",
                cwd=consumer_root,
            )
            self.assertNotEqual(blocked.returncode, 0)
            self.assertFalse(marker.exists(), blocked.stdout + blocked.stderr)
            self.assertFalse((consumer_root / "docs/plans/blocked.md").exists())

    def test_decomposition_overlay_state_ignores_project_script_modules(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_decomposition_project_scripts_") as tmpdir:
            fixture = Path(tmpdir).resolve()
            consumer_root = fixture / "consumer"
            consumer_root.joinpath("docs", "plans").mkdir(parents=True)
            marker = fixture / "project-module-imported"
            decoy = consumer_root / "scripts" / "plan_status_oracle.py"
            decoy.parent.mkdir(parents=True)
            decoy.write_text(
                "from pathlib import Path\n"
                f"Path({str(marker)!r}).write_text('imported', encoding='utf-8')\n"
                "raise ImportError('a project copy must not shadow the runtime oracle')\n",
                encoding="utf-8",
            )
            plan_rel = "docs/plans/project_scripts.md"
            common = self._root_split_shell(consumer_root, REPO_ROOT.resolve())
            # The pinned facade bridge starts Python with the runtime scripts already on sys.path.
            runtime_scripts = REPO_ROOT.resolve() / "scripts"
            command = (
                common
                + f"export PYTHONPATH={shlex.quote(str(runtime_scripts))}; "
                + f"row=\"$(_planveyor_decomposition_plan_admission {shlex.quote(plan_rel)})\" || exit $?; "
                "IFS=$'\\t' read -r admission plan_path plan_fs expected_hash expected_identity <<< \"$row\" || exit $?; "
                "_planveyor_decomposition_bootstrap_plan_file \"$plan_fs\" \"$plan_path\" \"$admission\" \"$expected_hash\" \"$expected_identity\" || exit $?; "
                "_planveyor_plan_phase_overlay_state \"$plan_path\""
            )
            result = self._run_sourced(command, cwd=consumer_root)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("decomposition_wave\tactive", result.stdout)
            self.assertFalse(marker.exists(), result.stdout + result.stderr)

    def test_role_session_root_failure_stops_before_init(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_session_root_failure_") as tmpdir:
            fixture = Path(tmpdir).resolve()
            marker = fixture / "unexpected-init"
            result = self._run_sourced(
                "_planveyor_project_root() { return 73; }; "
                "_planveyor_session_sid_ensure_in_effective_codex_home() { return 1; }; "
                + f"_fixture_init() {{ print -r -- unexpected > {shlex.quote(str(marker))}; return 0; }}; "
                + "_planveyor_role_session_sid_ensure_local_or_init fixture-session default _fixture_init",
                cwd=fixture,
            )

            self.assertEqual(result.returncode, 73, result.stderr)
            self.assertFalse(marker.exists(), result.stdout + result.stderr)

    def test_state_plan_and_owner_input_use_consumer_root(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_state_root_split_") as tmpdir:
            fixture = Path(tmpdir).resolve()
            consumer_root = fixture / "consumer"
            consumer_root.mkdir()
            self._init_git_repo(consumer_root)
            plan_rel = "docs/plans/consumer.md"
            self._write_minimal_plan(consumer_root, plan_rel, wave_family=None)
            runtime_root = REPO_ROOT.resolve()
            common = self._root_split_shell(consumer_root, runtime_root)
            result = self._run_sourced(
                common
                + f"planveyor_plan_set {shlex.quote(plan_rel)} || exit $?; "
                + f"print -r -- owner-answer | planveyor_owner_answers_set planner {shlex.quote(plan_rel)} || exit $?; "
                + f"planveyor_planpath; _planveyor_peek_owner_answers_for planner {shlex.quote(plan_rel)}",
                cwd=consumer_root,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(plan_rel, result.stdout)
            self.assertIn("owner-answer", result.stdout)
            self.assertEqual(
                consumer_root.joinpath(".planveyor.planpath").read_text(encoding="utf-8").splitlines()[-1],
                plan_rel,
            )
            answers = consumer_root / ".planveyor.owner_answers"
            self.assertTrue(answers.is_file())
            self.assertIn("TO=planner", answers.read_text(encoding="utf-8"))
            self.assertFalse((runtime_root / ".planveyor.owner_answers").exists())

            blocked = self._run_sourced(
                common
                + "_planveyor_project_root() { return 1; }; "
                + f"print -r -- unexpected | planveyor_owner_answers_set planner {shlex.quote(plan_rel)}",
                cwd=consumer_root,
            )
            self.assertNotEqual(blocked.returncode, 0)
            self.assertEqual(answers.read_text(encoding="utf-8"), "TO=planner\nPLAN_PATH=docs/plans/consumer.md\n---\nowner-answer\n")

    def test_manager_receipt_path_binds_consumer_root(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_manager_receipt_root_") as tmpdir:
            fixture = Path(tmpdir).resolve()
            consumer_root = fixture / "consumer"
            consumer_root.mkdir()
            self._init_git_repo(consumer_root)
            runtime_root = REPO_ROOT.resolve()
            invocation_id = "20260914T000000Z_123_456"
            common = self._root_split_shell(consumer_root, runtime_root)
            result = self._run_sourced(
                common
                + "_planveyor_authority_context_field() { [[ \"${2:-}\" == state ]] && print -r -- legacy; }; "
                + "_planveyor_authority_before_effect_json() { return 0; }; "
                + f"receipt_path=\"$(_planveyor_manager_invocation_receipt_path {invocation_id})\" || exit $?; "
                + f"_planveyor_manager_invocation_receipt_seed {invocation_id} \"$receipt_path\" manager-sid run docs/plans/consumer.md 2026-01-01T00:00:00Z >/dev/null || exit $?; "
                + "print -r -- \"$receipt_path\"",
                cwd=consumer_root,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = consumer_root / ".planveyor.manager_runs" / f"{invocation_id}.json"
            self.assertEqual(result.stdout.strip(), str(receipt))
            payload = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(payload["repo_root"], str(consumer_root))
            self.assertEqual(payload["receipt_path"], str(receipt))
            self.assertFalse((runtime_root / ".planveyor.manager_runs" / f"{invocation_id}.json").exists())

            blocked = self._run_sourced(
                common
                + "_planveyor_project_root() { return 1; }; "
                + f"_planveyor_manager_invocation_receipt_path {invocation_id}",
                cwd=consumer_root,
            )
            self.assertNotEqual(blocked.returncode, 0)
            self.assertEqual(sorted(consumer_root.joinpath(".planveyor.manager_runs").glob("*.json")), [receipt])

    def test_gate_and_followups_execute_from_consumer_root(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_gate_root_split_") as tmpdir:
            fixture = Path(tmpdir).resolve()
            consumer_root = fixture / "consumer"
            consumer_root.mkdir()
            runtime_root = REPO_ROOT.resolve()
            common = self._root_split_shell(consumer_root, runtime_root)
            result = self._run_sourced(
                common
                + "_planveyor_get_pybin() { print -r -- /fixture/python; }; "
                + "_planveyor_py_any() { print -r -- \"gate-cwd=$PWD\"; printf 'gate-arg=%s\\n' \"$@\"; }; "
                + "_planveyor_python_dispatch() { print -r -- \"followups-cwd=$PWD\"; printf 'followups-arg=%s\\n' \"$@\"; }; "
                + "planveyor_ai_gate --range base..head; planveyor_followups_lint --check",
                cwd=consumer_root,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"gate-cwd={consumer_root}", result.stdout)
            self.assertIn(f"gate-arg={runtime_root / 'scripts' / 'ai_gate.py'}", result.stdout)
            self.assertIn(f"gate-arg={consumer_root}", result.stdout)
            self.assertIn(f"followups-cwd={consumer_root}", result.stdout)
            self.assertIn(f"followups-arg={runtime_root / 'scripts' / 'followups_lint.py'}", result.stdout)

            marker = fixture / "unexpected-gate-dispatch"
            blocked = self._run_sourced(
                common
                + "_planveyor_project_root() { return 1; }; "
                + f"_planveyor_py_any() {{ print -r -- unexpected > {shlex.quote(str(marker))}; }}; "
                + "planveyor_ai_gate --range base..head",
                cwd=consumer_root,
            )
            self.assertNotEqual(blocked.returncode, 0)
            self.assertFalse(marker.exists(), blocked.stdout + blocked.stderr)

    def test_docs_retrieval_and_hygiene_use_consumer_root(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_docs_root_split_") as tmpdir:
            fixture = Path(tmpdir).resolve()
            consumer_root = fixture / "consumer"
            consumer_root.mkdir()
            runtime_root = REPO_ROOT.resolve()
            archive_db = consumer_root / ".tmp" / "archive.sqlite"
            capture = fixture / "capture.sh"
            capture.write_text(
                "#!/bin/sh\n"
                'printf "docs-cwd=%s\\n" "$PWD"\n'
                'for argument in "$@"; do printf "docs-arg=%s\\n" "$argument"; done\n',
                encoding="utf-8",
            )
            capture.chmod(0o700)
            common = self._root_split_shell(consumer_root, runtime_root)
            result = self._run_sourced(
                common
                + f"_planveyor_get_pybin() {{ print -r -- {shlex.quote(str(capture))}; }}; "
                + f"_planveyor_main_root() {{ print -r -- {shlex.quote(str(consumer_root))}; }}; "
                + f"_planveyor_docs_archive_db_default() {{ print -r -- {shlex.quote(str(archive_db))}; }}; "
                + "_planveyor_content_profile_id() { print -r -- default; }; "
                + "planveyor_docs_index_build plans --root docs; planveyor_docs_retrieve_log; planveyor_docs_hygiene_archive --range base..head",
                cwd=consumer_root,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertGreaterEqual(result.stdout.count(f"docs-cwd={consumer_root}"), 2)
            self.assertIn(f"docs-arg={runtime_root / 'scripts' / 'docs_index_build.py'}", result.stdout)
            self.assertIn(f"docs-arg={runtime_root / 'scripts' / 'docs_hygiene_archive.py'}", result.stdout)
            self.assertIn(str(consumer_root / ".tmp" / "planveyor_docs_retrieve_queries.jsonl"), result.stdout)
            self.assertIn(f"docs-arg={archive_db}", result.stdout)

            marker = fixture / "unexpected-docs-dispatch"
            blocked_pybin = fixture / "blocked.sh"
            blocked_pybin.write_text(
                "#!/bin/sh\n" + f"printf unexpected > {shlex.quote(str(marker))}\n",
                encoding="utf-8",
            )
            blocked_pybin.chmod(0o700)
            blocked = self._run_sourced(
                common
                + "_planveyor_project_root() { return 1; }; "
                + f"_planveyor_get_pybin() {{ print -r -- {shlex.quote(str(blocked_pybin))}; }}; "
                + "planveyor_docs_index_build plans",
                cwd=consumer_root,
            )
            self.assertNotEqual(blocked.returncode, 0)
            self.assertFalse(marker.exists(), blocked.stdout + blocked.stderr)

    def test_manager_prompt_documents_analysis_command_contract(self) -> None:
        text = MANAGER_PROMPT.read_text(encoding="utf-8")

        self.assertIn("MANAGER_CMD=analysis [PLAN_PATH]", text)
        self.assertIn("planveyor_analysis_init [PLAN_PATH]", text)
        self.assertIn("planning_contour_marker=analysis_wave", text)
        self.assertIn("Prepared analysis wave:", text)

    def test_decomposition_prompt_and_docs_publish_one_managed_contract(self) -> None:
        direct_prompt = DECOMPOSITION_PROMPT.read_text(encoding="utf-8")
        manager_prompt = MANAGER_PROMPT.read_text(encoding="utf-8")
        playbook = DECOMPOSITION_PLAYBOOK.read_text(encoding="utf-8")
        docs = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (PROMPTS_README, DECOMPOSITION_PLAYBOOK, OWNER_RUNBOOK, OWNER_RUNBOOK_RU, PLANS_README)
        )

        for text in (direct_prompt, manager_prompt, docs):
            self.assertIn("MANAGER_CMD=decomposition", text)
            self.assertIn("planveyor_decomposition_init", text)
        self.assertIn("docs/plans/*.md", direct_prompt)
        self.assertIn("./bin/planveyor planveyor_decomposition_init [PLAN_PATH]", direct_prompt)
        self.assertIn("не ставит queue автоматически", direct_prompt)
        self.assertRegex(direct_prompt, r"не\s+выполняет product code")
        self.assertIn("не копирует и не переписывает authentication, configuration или prompts", playbook)
        self.assertNotIn("запись разрешена только explicit", playbook)
        for retired_claim in ("source_hash", "target_hash", "unmanaged_conflict"):
            self.assertNotIn(retired_claim, playbook)
        self.assertNotIn("отдельной команды для decomposition нет", direct_prompt + manager_prompt + docs)

    def test_public_status_oracle_forwards_manager_mode(self) -> None:
        plan_rel = "docs/plans/260917_0300_manager_mode_fixture.md"
        with tempfile.TemporaryDirectory(prefix="planveyor_manager_mode_oracle_") as tmpdir:
            root = Path(tmpdir)
            self._init_git_repo(root)
            self._write_minimal_plan(
                root,
                plan_rel,
                wave_family=None,
                required_manager_mode="manager-collab",
            )
            result = self._run_sourced(
                f"planveyor_plan_status_oracle --json --manager-mode manager-collab {plan_rel}",
                cwd=root,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["actual_manager_mode"], "manager-collab")
        self.assertEqual(payload["required_manager_mode"], "manager-collab")
        self.assertEqual(payload["manager_mode_state"], "admitted")
        self.assertIs(payload["manager_mode_admitted"], True)

    def test_ledger_reader_requires_explicit_paths(self) -> None:
        for args in ([], ["--all"]):
            with self.subTest(args=args), tempfile.TemporaryDirectory(prefix="planveyor_ledger_lint_") as tmpdir:
                result = subprocess.run(
                    [sys.executable, "-B", str(LEDGER_LINT), *args],
                    cwd=tmpdir, text=True, capture_output=True, check=False,
                )
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(result.stdout, "")

    def test_ledger_lint_explicit_missing_path_stays_strict(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_ledger_lint_") as tmpdir:
            result = subprocess.run(
                [sys.executable, "-B", str(LEDGER_LINT), "docs/continuity/missing.md"],
                cwd=tmpdir,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("WARN: no ledger files found.", result.stdout)

    def test_ledger_lint_existing_ledger_errors_still_fail(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_ledger_lint_") as tmpdir:
            ledger = Path(tmpdir) / "docs" / "continuity" / "role.md"
            ledger.parent.mkdir(parents=True)
            ledger.write_text("## Duplicate\n## Duplicate\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-B", str(LEDGER_LINT), "docs/continuity/role.md"],
                cwd=tmpdir,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("ERROR: docs/continuity/role.md:2: Duplicate level-2 heading", result.stdout)

    def test_canceled_family_is_absent_from_public_commands_and_help(self) -> None:
        # Attest current candidate bytes in the existing disposable fixture;
        # the source checkout may contain the uncommitted fix under test.
        with AuthorityFixture() as fixture:
            entry = write(fixture.runtime_root, "bin/planveyor",
                (REPO_ROOT / "bin/planveyor").read_bytes(), executable=True)
            commit_all(fixture.runtime_root, "public child entry")
            environment = fixture.environment()
            help_result = subprocess.run(
                [str(entry), "--project", str(fixture.target_root), "planveyor_help", "--all"],
                cwd=fixture.target_root, env=environment, text=True, capture_output=True, check=False,
            )
            self.assertEqual(help_result.returncode, 0, help_result.stderr)
            for command in ("planveyor_followups_todo_harvest", "planveyor_ledger_lint_all"):
                with self.subTest(command=command):
                    self.assertNotIn(command, help_result.stdout)
                    result = subprocess.run(
                        [str(entry), "--project", str(fixture.target_root), command],
                        cwd=fixture.target_root, env=environment, text=True, capture_output=True, check=False,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(command, result.stderr)
            for helper in ("followups_todo_harvest.py", "todo_stage_followups_check.py"):
                self.assertFalse((fixture.runtime_root / "scripts" / helper).exists())

    def test_selected_project_root_readers_fail_stop_before_read(self) -> None:
        readers = (
            ('planveyor_planpath', ''),
            ('planveyor_session', 'planner'),
            ('planveyor_runner_file', 'planner'),
            ('planveyor_range_base', ''),
            ('planveyor_range_head', ''),
            ('planveyor_range_merge', ''),
        )
        with tempfile.TemporaryDirectory(prefix='planveyor_resolver_readers_') as tmpdir:
            fixture = Path(tmpdir).resolve()
            consumer_root = fixture / 'consumer'
            consumer_root.mkdir()
            marker = fixture / 'unexpected-read'
            common = self._root_split_shell(consumer_root, REPO_ROOT.resolve())
            calls = ' && '.join(
                f'_fixture_expect_73 {name}' + (f' {suffix}' if suffix else '')
                for name, suffix in readers
            )
            result = self._run_sourced(
                common
                + '_planveyor_project_root() { return 73; }; '
                + f'_planveyor_read() {{ print -r -- unexpected > {shlex.quote(str(marker))}; }}; '
                + '_fixture_expect_73() { "$@"; _fixture_rc=$?; (( _fixture_rc == 73 )) || return 91; }; '
                + calls,
                cwd=consumer_root,
            )
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertFalse(marker.exists(), result.stderr + result.stdout)

    def test_selected_project_root_dispatchers_fail_stop_and_preserve_split(self) -> None:
        dispatchers = (
            ('_planveyor_plan_queue', 'show', '--project-root', 'plan_queue.py'),
            ('_planveyor_planqueue_metrics', '--json', '--root', 'planqueue_metrics.py'),
            ('_planveyor_planning_wave_readback', '--json', '--root', 'planning_wave_readback.py'),
            ('_planveyor_wave_telemetry_report', '--json', '--root', 'wave_telemetry_report.py'),
            ('planveyor_q_final_report', '--json', '--repo-root', 'queue_finalizer_report.py'),
            ('planveyor_followups_capture', 'show', '--project-root', 'followups_capture.py'),
        )
        with tempfile.TemporaryDirectory(prefix='planveyor_resolver_dispatch_') as tmpdir:
            fixture = Path(tmpdir).resolve()
            consumer_root = fixture / 'consumer'
            consumer_root.mkdir()
            runtime_root = REPO_ROOT.resolve()
            common = self._root_split_shell(consumer_root, runtime_root)
            marker = fixture / 'unexpected-dispatch'
            calls = ' && '.join(f'{name} {argument}' for name, argument, _flag, _helper in dispatchers)
            blocked = self._run_sourced(
                common
                + '_planveyor_project_root() { return 73; }; '
                + f'_planveyor_py_any() {{ print -r -- unexpected > {shlex.quote(str(marker))}; }}; '
                + '_fixture_expect_73() { "$@"; _fixture_rc=$?; (( _fixture_rc == 73 )) || return 91; }; '
                + ' && '.join(f'_fixture_expect_73 {name} {argument}' for name, argument, _flag, _helper in dispatchers),
                cwd=consumer_root,
            )
            self.assertEqual(blocked.returncode, 0, blocked.stderr + blocked.stdout)
            self.assertFalse(marker.exists(), blocked.stderr + blocked.stdout)

            observed = self._run_sourced(
                common + '_planveyor_py_any() { printf "arg=%s\\n" "$@"; }; ' + calls,
                cwd=consumer_root,
            )
            self.assertEqual(observed.returncode, 0, observed.stderr + observed.stdout)
            for _name, _argument, flag, helper_name in dispatchers:
                self.assertEqual(
                    observed.stdout.count(f'arg={runtime_root / "scripts" / helper_name}'),
                    1,
                    observed.stdout,
                )
                self.assertIn(f'arg={flag}', observed.stdout)
            self.assertEqual(observed.stdout.count(f'arg={consumer_root}'), len(dispatchers), observed.stdout)
            self.assertNotIn(f'arg={runtime_root}\n', observed.stdout)

    def test_merge_tracker_ensure_helper_failure_precedes_pushd_and_preserves_shell_state(self) -> None:
        with tempfile.TemporaryDirectory(prefix='planveyor_tracker_ensure_resolver_') as tmpdir:
            fixture = Path(tmpdir).resolve()
            consumer_root = fixture / 'consumer'
            consumer_root.mkdir()
            marker = fixture / 'unexpected-pushd'
            common = self._root_split_shell(consumer_root, REPO_ROOT.resolve())
            command = (
                common
                + '_planveyor_merge_policy_mode() { print -r -- legacy; }; '
                + '_planveyor_merge_tracker_path() { return 73; }; '
                + 'planveyor_merge_tracker_init() { return 73; }; '
                + f'pushd() {{ print -r -- unexpected > {shlex.quote(str(marker))}; builtin pushd "$@"; }}; '
                + '_before_pwd="$PWD"; _before_stack="${(j.:.)dirstack}"; '
                + 'planveyor_merge_tracker_ensure; _rc=$?; '
                + '[[ "$PWD" == "$_before_pwd" && "${(j.:.)dirstack}" == "$_before_stack" ]] || exit 99; '
                + 'exit "$_rc"'
            )
            result = self._run_sourced(command, cwd=fixture)
            self.assertEqual(result.returncode, 73, result.stderr + result.stdout)
            self.assertFalse(marker.exists(), result.stderr + result.stdout)

    def test_docs_finalize_resolver_failures_stop_before_validation_and_tick(self) -> None:
        with tempfile.TemporaryDirectory(prefix='planveyor_docs_finalize_resolver_') as tmpdir:
            fixture = Path(tmpdir).resolve()
            consumer_root = fixture / 'consumer'
            consumer_root.mkdir()
            common = self._root_split_shell(consumer_root, REPO_ROOT.resolve())
            invocation = '--role Architect --range base..head --path receipt.md'

            # Keep the real range getters here: a root failure must happen before
            # either getter is entered, rather than being concealed by getter stubs.
            first_root_failed = self._run_sourced(
                common
                + '_planveyor_project_root() { return 73; }; '
                + "PS4='TRACE:%x:'; set -x; "
                + f'planveyor_post_merge_docs_finalize_tick {invocation}; '
                + '_fixture_rc=$?; set +x; exit "$_fixture_rc"',
                cwd=consumer_root,
            )
            self.assertEqual(first_root_failed.returncode, 73, first_root_failed.stderr + first_root_failed.stdout)
            self.assertNotIn('_planveyor_get_range_base', first_root_failed.stderr)
            self.assertNotIn('_planveyor_get_range_head', first_root_failed.stderr)

            def command_with(marker: Path, override: str) -> str:
                return (
                    common
                    + '_planveyor_get_range_base() { print -r -- base; }; '
                    + '_planveyor_get_range_head() { print -r -- head; }; '
                    + override
                    + f'_planveyor_merge_policy_validate_tracker() {{ print -r -- validation >> {shlex.quote(str(marker))}; }}; '
                    + f'planveyor_post_merge_receipt_preflight() {{ print -r -- preflight >> {shlex.quote(str(marker))}; }}; '
                    + f'planveyor_merge_tracker_tick() {{ print -r -- tick >> {shlex.quote(str(marker))}; }}; '
                    + f'planveyor_post_merge_docs_finalize_tick {invocation}'
                )

            root_marker = fixture / 'root-failure.actions'
            root_failed = self._run_sourced(
                command_with(root_marker, '_planveyor_project_root() { return 73; }; '),
                cwd=consumer_root,
            )
            self.assertEqual(root_failed.returncode, 73, root_failed.stderr + root_failed.stdout)
            self.assertFalse(root_marker.exists(), root_failed.stderr + root_failed.stdout)

            helper_marker = fixture / 'helper-failure.actions'
            helper_failed = self._run_sourced(
                command_with(helper_marker, '_planveyor_merge_tracker_path() { return 74; }; '),
                cwd=consumer_root,
            )
            self.assertEqual(helper_failed.returncode, 74, helper_failed.stderr + helper_failed.stdout)
            self.assertFalse(helper_marker.exists(), helper_failed.stderr + helper_failed.stdout)

            success_marker = fixture / 'success.actions'
            success = self._run_sourced(command_with(success_marker, ''), cwd=consumer_root)
            self.assertEqual(success.returncode, 0, success.stderr + success.stdout)
            self.assertEqual(success_marker.read_text(encoding='utf-8').splitlines(), ['validation', 'preflight', 'tick'])


    def test_merge_tracker_init_first_root_failure_stops_before_real_range_getters(self) -> None:
        with tempfile.TemporaryDirectory(prefix='planveyor_tracker_init_resolver_') as tmpdir:
            fixture = Path(tmpdir).resolve()
            consumer_root = fixture / 'consumer'
            consumer_root.mkdir()
            common = self._root_split_shell(consumer_root, REPO_ROOT.resolve())
            result = self._run_sourced(
                common
                + '_planveyor_project_root() { return 73; }; '
                + "PS4='TRACE:%x:'; set -x; "
                + 'planveyor_merge_tracker_init; '
                + '_fixture_rc=$?; set +x; exit "$_fixture_rc"',
                cwd=consumer_root,
            )
            self.assertEqual(result.returncode, 73, result.stderr + result.stdout)
            self.assertNotIn('_planveyor_get_range_base', result.stderr)
            self.assertNotIn('_planveyor_get_range_head', result.stderr)
            self.assertNotIn('_planveyor_merge_policy_mode', result.stderr)

    def test_tracker_root_revalidation_precedes_policy_dispatch(self) -> None:
        with tempfile.TemporaryDirectory(prefix='planveyor_tracker_revalidation_') as tmpdir:
            fixture = Path(tmpdir).resolve()
            consumer_root = fixture / 'consumer'
            consumer_root.mkdir()
            common = self._root_split_shell(consumer_root, REPO_ROOT.resolve())

            def root_once_then_fail(counter: Path) -> str:
                counter_q = shlex.quote(str(counter))
                consumer_q = shlex.quote(str(consumer_root))
                return (
                    '_planveyor_project_root() { '
                    'local _fixture_count=0; '
                    f'if [[ -f {counter_q} ]]; then read -r _fixture_count < {counter_q}; fi; '
                    '(( _fixture_count += 1 )); '
                    f'print -r -- "$_fixture_count" > {counter_q}; '
                    f'if (( _fixture_count == 1 )); then print -r -- {consumer_q}; return 0; fi; '
                    'return 73; '
                    '}; '
                )

            def policy_probe(marker: Path) -> str:
                marker_q = shlex.quote(str(marker))
                return (
                    '_planveyor_py_any() { '
                    f'print -r -- unexpected > {marker_q}; '
                    'print -r -- legacy; '
                    '}; '
                )

            init_marker = fixture / 'init-policy-dispatch'
            init_result = self._run_sourced(
                common
                + root_once_then_fail(fixture / 'init-root-calls')
                + '_planveyor_get_range_base() { print -r -- base; }; '
                + '_planveyor_get_range_head() { print -r -- head; }; '
                + 'planveyor_range_merge() { print -r -- merge; }; '
                + policy_probe(init_marker)
                + 'planveyor_merge_tracker_init',
                cwd=consumer_root,
            )
            self.assertEqual(init_result.returncode, 73, init_result.stderr + init_result.stdout)
            self.assertFalse(init_marker.exists(), init_result.stderr + init_result.stdout)

            ensure_marker = fixture / 'ensure-policy-dispatch'
            ensure_result = self._run_sourced(
                common
                + root_once_then_fail(fixture / 'ensure-root-calls')
                + policy_probe(ensure_marker)
                + 'planveyor_merge_tracker_ensure',
                cwd=consumer_root,
            )
            self.assertEqual(ensure_result.returncode, 73, ensure_result.stderr + ensure_result.stdout)
            self.assertFalse(ensure_marker.exists(), ensure_result.stderr + ensure_result.stdout)

            positive_marker = fixture / 'positive-policy-dispatch'
            positive_result = self._run_sourced(
                common
                + '_planveyor_get_range_base() { print -r -- base; }; '
                + '_planveyor_get_range_head() { print -r -- head; }; '
                + 'planveyor_range_merge() { print -r -- merge; }; '
                + policy_probe(positive_marker)
                + 'planveyor_merge_tracker_init',
                cwd=consumer_root,
            )
            self.assertEqual(positive_result.returncode, 0, positive_result.stderr + positive_result.stdout)
            self.assertTrue(positive_marker.exists(), positive_result.stderr + positive_result.stdout)
            self.assertTrue((consumer_root / '.planveyor.merge_tracker.md').is_file())


    def test_workspace_alias_surface_and_child_entries_are_absent(self) -> None:
        source_text = PLANVEYOR_SCRIPT.read_text(encoding="utf-8")
        child_start = source_text.index("_planveyor_cli_allowed_commands() {")
        child_end = source_text.index("\n}\n\n_planveyor_cli_require_attested_child", child_start)
        child_allowlist = source_text[child_start:child_end]
        manual_start = source_text.index("planveyor_show_manual() {")
        manual_end = source_text.index("\n}\n\nplanveyor_help()", manual_start)
        self.assertNotIn("codex_app_", source_text[manual_start:manual_end])
        self.assertNotIn("workspace_runtime.zsh", source_text)
        self.assertNotIn("_planveyor_codex_desktop_open", source_text)
        self.assertNotIn("_planveyor_private_family_load workspace", source_text)
        for command in (
            "planveyor_router_slots",
            "planveyor_router_status",
        ):
            self.assertNotIn(command, child_allowlist)
        self.assertEqual(
            set(re.findall(r"(?m)^(codex_[A-Za-z0-9_]+)\(\) \{", source_text)),
            {
                "codex_arch",
                "codex_arch_initial",
                "codex_coder",
                "codex_manager",
                "codex_manager_collab",
                "codex_manager_custom_pipeline",
            },
        )


if __name__ == "__main__":
    unittest.main()

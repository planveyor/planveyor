#!/usr/bin/env python3
"""Caller-anchor regressions using disposable runtimes, targets, and HOME."""

from __future__ import annotations

import os
from pathlib import Path
import shlex
import subprocess
import sys
import unittest

import contract_authority_context as authority
from test_contract_authority_support import AuthorityFixture, commit_all, tree_snapshot, write


class ContractAuthorityShellBufferTests(unittest.TestCase):
    def run_shell(self, fixture: AuthorityFixture, body: str, *, loader: str | None = None,
                  extra_environment: dict[str, str] | None = None):
        environment = fixture.environment()
        environment["PATH"] = os.pathsep.join(
            (str(Path(sys.executable).resolve().parent), environment.get("PATH", ""))
        )
        transport = fixture.root / "transport"
        transport.mkdir(exist_ok=True)
        if extra_environment:
            environment.update(extra_environment)
        environment["TMPDIR"] = str(transport)
        environment["TMPPREFIX"] = str(transport / "zsh")
        return subprocess.run(
            ["/bin/zsh", "-f", "-c", (fixture.shell_loader() if loader is None else loader) + "\n" + body],
            cwd=fixture.target_root, env=environment, capture_output=True, text=True,
            check=False, timeout=120,
        )

    def test_raw_clean_source_is_legacy_and_cannot_engage(self):
        with AuthorityFixture() as fixture:
            fixture.activate_planveyor(authority.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS)
            before = tree_snapshot(fixture.target_root)
            facade = shlex.quote(str(fixture.runtime_root / "scripts/planveyor.zsh"))
            result = self.run_shell(fixture, f"""
source {facade} || exit $?
print -r -- "STATE=$_PLANVEYOR_AUTHORITY_SOURCE_STATE"
if _planveyor_pre_dispatch raw_clean_source; then
  print -r -- RAW_ENGAGED
  exit 91
fi
""")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("STATE=unattested_legacy", result.stdout)
            self.assertNotIn("RAW_ENGAGED", result.stdout)
            self.assertIn("runtime_pin_unattested", result.stderr)
            self.assertEqual(tree_snapshot(fixture.target_root), before)

    def test_exported_foreign_runtime_and_valid_pin_cannot_select_shell_modules(self):
        with AuthorityFixture() as fixture, AuthorityFixture() as foreign:
            module = foreign.runtime_root / "scripts/planveyor/session_init.zsh"
            write(foreign.runtime_root, "scripts/planveyor/session_init.zsh",
                  "print -r -- FOREIGN_MODULE_EXECUTED\n" + module.read_text())
            commit_all(foreign.runtime_root, "fixture foreign shell module")
            bootstrap = (foreign.runtime_root / "scripts/contract_authority_bootstrap.py").read_text()
            pin_result = subprocess.run(
                [sys.executable, "-I", "-B", "-c", bootstrap,
                 str(foreign.runtime_root / "scripts/contract_authority_bridge.py"),
                 "runtime-pin", "--runtime-root", str(foreign.runtime_root),
                 "--entrypoint", str(foreign.runtime_root / "scripts/planveyor.zsh")],
                cwd=foreign.target_root, env=foreign.environment(),
                capture_output=True, text=True, check=False, timeout=60,
            )
            self.assertEqual(pin_result.returncode, 0, pin_result.stdout + pin_result.stderr)
            facade = shlex.quote(str(fixture.runtime_root / "scripts/planveyor.zsh"))
            result = self.run_shell(fixture, f"planveyor_source_runtime {facade}", extra_environment={
                "_PLANVEYOR_AUTHORITY_RUNTIME_ROOT": str(foreign.runtime_root),
                "_PLANVEYOR_AUTHORITY_RUNTIME_PIN_SUMMARY": pin_result.stdout.strip(),
            })
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("FOREIGN_MODULE_EXECUTED", result.stdout)
            self.assertIn("preseeded source carrier is rejected", result.stderr)

    def test_partial_raw_source_state_under_nounset_returns_without_aborting_the_shell(self):
        with AuthorityFixture() as fixture:
            facade = shlex.quote(str(fixture.runtime_root / "scripts/planveyor.zsh"))
            result = self.run_shell(fixture, f"""
setopt nounset
typeset -gr _PLANVEYOR_AUTHORITY_SOURCE_STATE=pinned
if source {facade}; then
  print -r -- PARTIAL_SOURCE_ACCEPTED
  exit 93
fi
print -r -- "C03_SHELL_BUFFER_TMP=$TMPDIR|$TMPPREFIX"
print -r -- CALLER_SURVIVED
""")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("CALLER_SURVIVED", result.stdout)
            self.assertIn(
                f"C03_SHELL_BUFFER_TMP={fixture.root / 'transport'}|{fixture.root / 'transport' / 'zsh'}",
                result.stdout.splitlines(),
            )
            self.assertNotIn("PARTIAL_SOURCE_ACCEPTED", result.stdout)
            self.assertNotIn("parameter not set", result.stderr)

    def test_raw_resourcing_cannot_replace_an_anchored_session(self):
        with AuthorityFixture() as fixture:
            facade = shlex.quote(str(fixture.runtime_root / "scripts/planveyor.zsh"))
            result = self.run_shell(fixture, f"""
planveyor_source_runtime {facade} || exit $?
planveyor_help() {{ print -r -- ORIGINAL_FUNCTION; }}
if source {facade}; then
  print -r -- RAW_RESOURCE_ACCEPTED
  exit 92
fi
planveyor_help
print -r -- "STATE=$_PLANVEYOR_AUTHORITY_SOURCE_STATE"
""")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("ORIGINAL_FUNCTION", result.stdout)
            self.assertIn("STATE=pinned", result.stdout)
            self.assertNotIn("RAW_RESOURCE_ACCEPTED", result.stdout)
            self.assertIn("pinned re-source requires planveyor_source_runtime", result.stderr)

    def test_failed_producer_never_executes_its_completed_output(self):
        with AuthorityFixture() as fixture:
            facade = shlex.quote(str(fixture.runtime_root / "scripts/planveyor.zsh"))
            sentinel = fixture.root / "producer-body-executed"
            template = (fixture.runtime_root / "scripts/contract_authority_shell_loader.zsh").read_text()
            # The caller deliberately chooses a failing test producer. This
            # tests the transport contract, without fabricating a source pin.
            failed_body = "unused-header\nprint -r -- BAD > " + shlex.quote(str(sentinel)) + "\n"
            producer = (
                "import sys\n"
                f"sys.stdout.write({failed_body!r})\n"
                "raise SystemExit(7)\n"
            )
            loader = template.replace("@PLANVEYOR_AUTHORITY_BOOTSTRAP_LITERAL@", producer)
            result = self.run_shell(fixture, f"planveyor_source_runtime {facade}", loader=loader)
            self.assertEqual(result.returncode, 7, result.stdout + result.stderr)
            self.assertFalse(sentinel.exists())
            self.assertEqual(list((fixture.root / "transport").iterdir()), [])

    def test_facade_selected_before_a_new_commit_cannot_claim_the_new_pin(self):
        for entry in ("source", "planveyor_source_runtime"):
            with self.subTest(entry=entry), AuthorityFixture() as fixture:
                facade_path = fixture.runtime_root / "scripts/planveyor.zsh"
                facade = shlex.quote(str(facade_path))
                root = shlex.quote(str(fixture.runtime_root))
                original = facade_path.read_text()
                hook = f"""print -r -- OLD_FACADE_EXECUTED
print -r -- '# later committed facade bytes' >> {facade}
git -C {root} add -- scripts/planveyor.zsh || return $?
git -C {root} commit --quiet -m fixture-later-facade || return $?
"""
                write(fixture.runtime_root, "scripts/planveyor.zsh", hook + original)
                commit_all(fixture.runtime_root, "fixture loaded facade race")
                result = self.run_shell(fixture, f"""
{entry} {facade}
source_rc=$?
print -r -- "SOURCE_RC=$source_rc"
print -r -- "STATE=${{_PLANVEYOR_AUTHORITY_SOURCE_STATE:-absent}}"
""")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("OLD_FACADE_EXECUTED", result.stdout)
                self.assertNotIn("STATE=pinned", result.stdout)
                if entry == "source":
                    self.assertIn("SOURCE_RC=0", result.stdout)
                    self.assertIn("STATE=unattested_legacy", result.stdout)
                else:
                    self.assertNotIn("SOURCE_RC=0", result.stdout)
                    self.assertIn("STATE=absent", result.stdout)

    def test_module_drift_after_facade_capture_rejects_before_module_execution(self):
        with AuthorityFixture() as fixture:
            facade_path = fixture.runtime_root / "scripts/planveyor.zsh"
            module = fixture.runtime_root / "scripts/planveyor/session_init.zsh"
            original = facade_path.read_text()
            replacement = "print -r -- CHANGED_MODULE_EXECUTED\n" + module.read_text()
            staged_source = write(fixture.root, "replacement-module", replacement)
            hook = f"cp {shlex.quote(str(staged_source))} {shlex.quote(str(module))} || return $?\n"
            write(fixture.runtime_root, "scripts/planveyor.zsh", hook + original)
            commit_all(fixture.runtime_root, "fixture module drift after facade capture")
            result = self.run_shell(fixture, f"planveyor_source_runtime {shlex.quote(str(facade_path))}")
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("CHANGED_MODULE_EXECUTED", result.stdout)
            self.assertIn("runtime_pin_unattested", result.stderr)
            self.assertEqual(list((fixture.root / "transport").iterdir()), [])


if __name__ == "__main__":
    unittest.main()

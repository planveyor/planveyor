#!/usr/bin/env python3
"""Focused shell-child authority transport regressions.

The shell facade owns the first retained-buffer pin.  These cases exercise
the two central Python child paths after a real shell context capture, rather
than invoking the bridge with a fabricated environment envelope.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import textwrap
import unittest


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import contract_authority_context as source_authority  # noqa: E402
from test_contract_authority_support import AuthorityFixture, commit_all, write  # noqa: E402


class ContractAuthorityShellChildrenTests(unittest.TestCase):
    """Exercise real zsh dynamic locals across buffered child dispatch."""

    def _run_shell(self, fixture: AuthorityFixture, body: str) -> subprocess.CompletedProcess[str]:
        environment = fixture.environment()
        environment["PATH"] = os.pathsep.join(
            (str(Path(sys.executable).resolve().parent), environment.get("PATH", ""))
        )
        # Public wrappers choose this interpreter before calling the central
        # dispatcher.  The test runner is deliberately Python 3.11.
        environment["PYBIN"] = sys.executable
        return subprocess.run(
            ["/bin/zsh", "-f", "-c", fixture.shell_loader() + "\n" + body],
            cwd=fixture.target_root,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
            timeout=90,
        )

    @staticmethod
    def _enable_fixture_admission(fixture: AuthorityFixture) -> None:
        """Keep the reviewed admission gate local to this disposable runtime."""

        context_path = fixture.runtime_root / "scripts" / "contract_authority_context.py"
        source = context_path.read_text(encoding="utf-8")
        old = "ENGAGED_ADMISSION_COMPLETE: Final[bool] = False"
        if old not in source:
            return
        new = "ENGAGED_ADMISSION_COMPLETE: Final[bool] = True"
        write(fixture.runtime_root, "scripts/contract_authority_context.py", source.replace(old, new, 1))
        commit_all(fixture.runtime_root, "enable shell-child fixture admission")

    def _prepare_fixture(self, fixture: AuthorityFixture) -> None:
        self._enable_fixture_admission(fixture)
        fixture.activate_planveyor(source_authority.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS)

    @staticmethod
    def _reader_source(*, sentinel: Path | None = None) -> str:
        lines = [
            "import hashlib",
            "import json",
            "import os",
            "import contract_authority_context as authority",
            "context = authority.resolve_top_level_context()",
            "declared = authority.read_declared_text(context, 'AGENTS.md', 'shell child regression')",
            "expected = json.loads(os.environ['_PLANVEYOR_AUTHORITY_CONTEXT_V1'])",
            "print(json.dumps({",
            "    'declared_sha256': hashlib.sha256(declared.encode('utf-8')).hexdigest(),",
            "    'expected_generation': expected['generation_sha256'],",
            "    'generation': context.generation_sha256,",
            "    'state': context.state,",
            "}, sort_keys=True))",
        ]
        if sentinel is not None:
            lines.extend(
                (
                    "from pathlib import Path",
                    f"Path({str(sentinel)!r}).write_text('child-effect', encoding='utf-8')",
                )
            )
        return "\n".join(lines) + "\n"

    @staticmethod
    def _binding_prologue(fixture: AuthorityFixture, *, between: str, dispatch: str) -> str:
        """Capture one real context and bind the supported caller-local tuple."""

        return textwrap.dedent(
            f"""\
            [[ -z "${{_PLANVEYOR_AUTHORITY_CONTEXT_V1+x}}" ]] || exit 90
            planveyor_source_runtime {shlex.quote(str(fixture.runtime_root / 'scripts' / 'planveyor.zsh'))} || exit $?
            [[ "${{_PLANVEYOR_AUTHORITY_SOURCE_STATE:-}}" == pinned ]] || exit 91
            [[ -z "${{_PLANVEYOR_AUTHORITY_CONTEXT_V1+x}}" ]] || exit 92
            shell_child_parent() {{
              emulate -L zsh
              local _planveyor_ctx_json=""
              _planveyor_ctx_json="$(_planveyor_pre_dispatch shell-child-parent)" || return $?
              local _planveyor_ctx_tuple=""
              _planveyor_ctx_tuple="$(_planveyor_authority_context_bindings "$_planveyor_ctx_json")" || return $?
              local _planveyor_ctx_state="" _planveyor_ctx_root="" _planveyor_ctx_generation="" _planveyor_ctx_remainder=""
              IFS=$'\\t' read -r _planveyor_ctx_state _planveyor_ctx_root _planveyor_ctx_generation _planveyor_ctx_remainder <<< "$_planveyor_ctx_tuple" || return 1
              [[ -z "${{_planveyor_ctx_remainder:-}}" && "$_planveyor_ctx_state" == engaged && -n "${{_planveyor_ctx_root//[[:space:]]/}}" && ${{#_planveyor_ctx_generation}} -eq 64 && "$_planveyor_ctx_generation" != *[^0-9A-Fa-f]* ]] || return 1
              local -r PLANVEYOR_CTX_SEAL='planveyor-contract-context.v1'
              local -r PLANVEYOR_CTX_ROOT="$_planveyor_ctx_root"
              local -r PLANVEYOR_CTX_GENERATION="$_planveyor_ctx_generation"
              local -r PLANVEYOR_CTX_JSON="$_planveyor_ctx_json"
              local -r PLANVEYOR_CTX_STATE="$_planveyor_ctx_state"
              print -r -- "PARENT_GENERATION=$PLANVEYOR_CTX_GENERATION"
            {textwrap.indent(between, '  ') if between else ''}
            {textwrap.indent(dispatch, '  ')}
            }}
            shell_child_parent
            """
        )

    def _shell_script(self, fixture: AuthorityFixture, *, between: str, dispatch: str) -> str:
        return self._binding_prologue(fixture, between=between, dispatch=dispatch)

    @staticmethod
    def _entry_dispatch(entry: Path) -> str:
        return f"_planveyor_python_dispatch {shlex.quote(sys.executable)} {shlex.quote(str(entry))}"

    @staticmethod
    def _stdin_dispatch(source_path: Path) -> str:
        return f"_planveyor_py_authority_stdin < {shlex.quote(str(source_path))}"

    @staticmethod
    def _parent_generation(stdout: str) -> str:
        lines = [line for line in stdout.splitlines() if line.startswith("PARENT_GENERATION=")]
        if len(lines) != 1:
            raise AssertionError(f"expected one parent generation line, got: {stdout!r}")
        return lines[0].partition("=")[2]

    def _child_payload(self, stdout: str) -> dict[str, object]:
        payloads = []
        for line in stdout.splitlines():
            if line.startswith("{"):
                payloads.append(json.loads(line))
        self.assertEqual(len(payloads), 1, stdout)
        return payloads[0]

    @staticmethod
    def _commit_target_change(fixture: AuthorityFixture, *, declared: bool) -> str:
        if declared:
            path = fixture.target_root / "AGENTS.md"
            relative = "AGENTS.md"
            body = "# committed current content update"
        else:
            path = fixture.target_root / "docs" / "shell-child-unrelated.md"
            relative = "docs/shell-child-unrelated.md"
            body = "unrelated target history"
        return "\n".join(
            (
                f"print -r -- {shlex.quote(body)} >> {shlex.quote(str(path))}",
                f"command git -C {shlex.quote(str(fixture.target_root))} add -- {shlex.quote(relative)} || return $?",
                f"command git -C {shlex.quote(str(fixture.target_root))} commit --quiet -m shell-child-target-change || return $?",
            )
        )

    @staticmethod
    def _commit_runtime_drift(fixture: AuthorityFixture) -> str:
        path = fixture.runtime_root / "scripts" / "contract_authority_runtime.py"
        return "\n".join(
            (
                f"print -r -- '# committed shell-child runtime drift' >> {shlex.quote(str(path))}",
                f"command git -C {shlex.quote(str(fixture.runtime_root))} add -- scripts/contract_authority_runtime.py || return $?",
                f"command git -C {shlex.quote(str(fixture.runtime_root))} commit --quiet -m shell-child-runtime-drift || return $?",
            )
        )

    def test_central_entry_and_stdin_carry_the_captured_generation_to_a_declared_read(self) -> None:
        for route in ("entry", "stdin"):
            with self.subTest(route=route), AuthorityFixture() as fixture:
                self._prepare_fixture(fixture)
                source = self._reader_source()
                if route == "entry":
                    entry = write(fixture.runtime_root, "scripts/shell_child_entry.py", source)
                    commit_all(fixture.runtime_root, "add shell child entry")
                    dispatch = self._entry_dispatch(entry)
                else:
                    dispatch = self._stdin_dispatch(write(fixture.root, "caller-entry-stdin.py", source))
                result = self._run_shell(fixture, self._shell_script(fixture, between="", dispatch=dispatch))

                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                parent_generation = self._parent_generation(result.stdout)
                payload = self._child_payload(result.stdout)
                self.assertEqual(payload["state"], "engaged")
                self.assertEqual(payload["generation"], parent_generation)
                self.assertEqual(payload["expected_generation"], parent_generation)
                self.assertEqual(
                    payload["declared_sha256"],
                    hashlib.sha256((fixture.target_root / "AGENTS.md").read_bytes()).hexdigest(),
                )
                self.assertNotIn("runtime_pin_unattested", result.stderr)

    def test_committed_allowed_content_change_reaches_central_entry_and_stdin_children(self) -> None:
        for route in ("entry", "stdin"):
            with self.subTest(route=route), AuthorityFixture() as fixture:
                self._prepare_fixture(fixture)
                sentinel = fixture.root / f"{route}-effect"
                source = self._reader_source(sentinel=sentinel)
                if route == "entry":
                    entry = write(fixture.runtime_root, "scripts/shell_child_declared_race.py", source)
                    commit_all(fixture.runtime_root, "add declared-race child entry")
                    dispatch = self._entry_dispatch(entry)
                else:
                    dispatch = self._stdin_dispatch(write(fixture.root, "caller-declared-race-stdin.py", source))
                result = self._run_shell(
                    fixture,
                    self._shell_script(
                        fixture,
                        between=self._commit_target_change(fixture, declared=True),
                        dispatch=dispatch,
                    ),
                )

                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertTrue(sentinel.is_file(), result.stdout + result.stderr)
                payload = self._child_payload(result.stdout)
                parent_generation = self._parent_generation(result.stdout)
                self.assertEqual(payload["generation"], parent_generation)
                self.assertEqual(payload["expected_generation"], parent_generation)
                self.assertEqual(
                    payload["declared_sha256"],
                    hashlib.sha256((fixture.target_root / "AGENTS.md").read_bytes()).hexdigest(),
                )
                self.assertIn("committed current content update", (fixture.target_root / "AGENTS.md").read_text())

    def test_unrelated_committed_target_history_keeps_central_entry_and_stdin_children_admitted(self) -> None:
        for route in ("entry", "stdin"):
            with self.subTest(route=route), AuthorityFixture() as fixture:
                self._prepare_fixture(fixture)
                source = self._reader_source()
                if route == "entry":
                    entry = write(fixture.runtime_root, "scripts/shell_child_unrelated_history.py", source)
                    commit_all(fixture.runtime_root, "add unrelated-history child entry")
                    dispatch = self._entry_dispatch(entry)
                else:
                    dispatch = self._stdin_dispatch(write(fixture.root, "caller-unrelated-history-stdin.py", source))
                result = self._run_shell(
                    fixture,
                    self._shell_script(
                        fixture,
                        between=self._commit_target_change(fixture, declared=False),
                        dispatch=dispatch,
                    ),
                )

                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                parent_generation = self._parent_generation(result.stdout)
                payload = self._child_payload(result.stdout)
                self.assertEqual(payload["generation"], parent_generation)
                self.assertEqual(payload["expected_generation"], parent_generation)
                self.assertTrue((fixture.target_root / "docs" / "shell-child-unrelated.md").is_file())

    def test_runtime_commit_after_shell_pin_rejects_central_entry_and_stdin_before_child_effect(self) -> None:
        for route in ("entry", "stdin"):
            with self.subTest(route=route), AuthorityFixture() as fixture:
                self._prepare_fixture(fixture)
                sentinel = fixture.root / f"{route}-runtime-effect"
                source = self._reader_source(sentinel=sentinel)
                if route == "entry":
                    entry = write(fixture.runtime_root, "scripts/shell_child_runtime_race.py", source)
                    commit_all(fixture.runtime_root, "add runtime-race child entry")
                    dispatch = self._entry_dispatch(entry)
                else:
                    dispatch = self._stdin_dispatch(write(fixture.root, "caller-runtime-race-stdin.py", source))
                result = self._run_shell(
                    fixture,
                    self._shell_script(
                        fixture,
                        between=self._commit_runtime_drift(fixture),
                        dispatch=dispatch,
                    ),
                )

                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertFalse(sentinel.exists(), result.stdout + result.stderr)
                self.assertRegex(result.stderr, r"runtime_pin_mismatch|runtime_loaded_code_drift")

    def test_public_followups_triage_dry_run_reaches_the_buffered_entry_from_an_engaged_shell(self) -> None:
        with AuthorityFixture() as fixture:
            self._prepare_fixture(fixture)
            result = self._run_shell(
                fixture,
                self._shell_script(fixture, between="", dispatch="planveyor_followups_triage --all --dry-run"),
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("followups_triage mode=dry-run", result.stdout)
        self.assertIn("inbox_files=0 items=0", result.stdout)
        self.assertNotIn("runtime_pin_unattested", result.stderr)


if __name__ == "__main__":
    unittest.main()

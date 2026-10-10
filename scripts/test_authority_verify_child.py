#!/usr/bin/env python3
"""Regression coverage for verify-suite's plan-lint authority child."""

from __future__ import annotations

import json
import textwrap
import unittest

from scripts import contract_authority_context as source_authority
from scripts.authority_bootstrap_test_support import run_python_stdin
from scripts.test_contract_authority_support import AuthorityFixture, commit_all


_PLAN_LINT_STUB = """\
from pathlib import Path
import sys

from contract_authority_context import resolve_top_level_context

try:
    resolve_top_level_context(Path.cwd())
except Exception as exc:
    print(f"STUB_AUTHORITY_ERROR={exc}", file=sys.stderr, flush=True)
    raise
if len(sys.argv) != 2 or not Path(sys.argv[1]).is_file():
    print("STUB_PLAN_INPUT_ERROR", file=sys.stderr, flush=True)
    raise SystemExit(2)
print("STUB_AUTHORITY_OK", file=sys.stderr, flush=True)
"""


_FIXTURE_PORTABILITY_PLANS = (
    "docs/plans/fixture-alpha.md",
    "docs/plans/fixture-beta.md",
    "docs/plans/fixture-gamma.md",
)


_VERIFY_HARNESS = textwrap.dedent(
    """\
    import json
    import os
    from pathlib import Path
    import subprocess
    import sys

    import contract_authority_context as authority
    import verify_suite

    root = Path.cwd()
    mode = sys.argv[1]
    actual_run = subprocess.run
    state = {
        "advanced": False,
        "commands": [],
        "child_authority_successes": [],
        "child_returncodes": [],
        "child_expectation_errors": [],
    }

    def commit_paths(paths, message):
        actual_run(
            ["git", "-C", str(root), "add", "--", *paths],
            text=True,
            capture_output=True,
            check=True,
        )
        actual_run(
            ["git", "-C", str(root), "commit", "--quiet", "-m", message],
            text=True,
            capture_output=True,
            check=True,
        )

    def advance_generation():
        selector_path = root / authority._snapshot.MARKER_PATH
        selector = json.loads(selector_path.read_text(encoding="utf-8"))
        selector["required_runtime_api"] = {"minimum": 4, "maximum": 5}
        selector_path.write_text(json.dumps(selector, ensure_ascii=False, sort_keys=True) + "\\n", encoding="utf-8")

    def advance_unrelated():
        path = root / "unrelated" / "verify-child.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("unrelated target evolution\\n", encoding="utf-8")
        commit_paths(["unrelated/verify-child.txt"], "unrelated verify child evolution")

    def command_summary(command, env):
        entry_path = None
        if isinstance(command, list) and "--path" in command:
            entry_path = command[command.index("--path") + 1]
        envelope = env.get(authority.EXPECTED_CONTEXT_ENV) if isinstance(env, dict) else None
        envelope_summary = None
        if isinstance(envelope, str):
            parsed = authority.parse_context_envelope(envelope)
            envelope_summary = {
                "state": parsed["state"],
                "project_root": parsed["project_root"],
                "generation_sha256": parsed["generation_sha256"],
            }
        return {
            "raw": isinstance(command, list)
            and len(command) == 4
            and command[0] == expected_pybin
            and command[1:] == ["-B", "scripts/plan_lint.py", command[3]],
            "isolated": isinstance(command, list) and command[1:4] == ["-I", "-B", "-c"],
            "bridge": isinstance(command, list)
            and len(command) > 5
            and command[5].endswith("/scripts/contract_authority_bridge.py"),
            "python_entry": isinstance(command, list) and "python-entry" in command,
            "entry_path": entry_path,
            "envelope": envelope_summary,
        }

    expected_legacy_env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    expected_pybin = verify_suite._resolve_pybin(root)
    outer = None
    result = None
    error = None
    if mode == "legacy":
        def intercept(command, *args, **kwargs):
            env = kwargs.get("env")
            summary = command_summary(command, env)
            summary["env_matches_legacy"] = env == expected_legacy_env
            state["commands"].append(summary)
            return subprocess.CompletedProcess(command, 0, "", "")
    else:
        outer = authority.resolve_top_level_context(root)
        os.environ[authority.EXPECTED_CONTEXT_ENV] = authority.context_to_json(outer)

        def intercept(command, *args, **kwargs):
            env = kwargs.get("env")
            is_child = isinstance(command, list) and "python-entry" in command
            if not is_child:
                return actual_run(command, *args, **kwargs)
            state["commands"].append(command_summary(command, env))
            if not state["advanced"]:
                state["advanced"] = True
                if mode == "generation":
                    advance_generation()
                else:
                    advance_unrelated()
            child = actual_run(command, *args, **kwargs)
            output = child.stdout + child.stderr
            state["child_returncodes"].append(child.returncode)
            state["child_authority_successes"].append("STUB_AUTHORITY_OK" in output)
            state["child_expectation_errors"].append(
                "actual authority context differs from inherited expectation"
                in output
            )
            return child

    verify_suite.subprocess.run = intercept
    try:
        result = verify_suite.PortabilityModule(
            portability_plans=__FIXTURE_PORTABILITY_PLANS__,
        ).check_plan_lint_portability_plans(root)
    except Exception as exc:
        error = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        verify_suite.subprocess.run = actual_run

    print(json.dumps({
        "advanced": state["advanced"],
        "child_authority_successes": state["child_authority_successes"],
        "commands": state["commands"],
        "child_expectation_errors": state["child_expectation_errors"],
        "child_returncodes": state["child_returncodes"],
        "error": error,
        "outer_generation": None if outer is None else outer.generation_sha256,
        "result": None if result is None else {
            "metric": result.metric,
            "status": result.status,
        },
    }, sort_keys=True))
    """
).replace("__FIXTURE_PORTABILITY_PLANS__", repr(_FIXTURE_PORTABILITY_PLANS))


class AuthorityVerifyChildTests(unittest.TestCase):
    def _run(self, mode: str) -> dict[str, object]:
        with AuthorityFixture(identity="planveyor") as fixture:
            plan_lint = fixture.runtime_root / "scripts" / "plan_lint.py"
            plan_lint.write_text(_PLAN_LINT_STUB, encoding="utf-8")
            fixture.runtime_commit = commit_all(fixture.runtime_root, "stub plan lint authority child")
            for relative_plan in _FIXTURE_PORTABILITY_PLANS:
                fixture_plan = fixture.target_root / relative_plan
                fixture_plan.parent.mkdir(parents=True, exist_ok=True)
                fixture_plan.write_text("**Status:** Done\n", encoding="utf-8")
            commit_all(fixture.target_root, "fixture selected portability plans")
            fixture.activate_planveyor(source_authority.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS)
            completed = run_python_stdin(fixture, _VERIFY_HARNESS, mode, timeout=120)

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        return json.loads(completed.stdout)

    def test_plain_legacy_launch_preserves_command_and_environment(self) -> None:
        payload = self._run("legacy")

        self.assertFalse(payload["advanced"])
        self.assertIsNone(payload["error"])
        self.assertEqual(payload["result"], {"metric": "3/3 exit=0", "status": "pass"})
        commands = payload["commands"]
        self.assertEqual(len(commands), 3)
        for command in commands:
            self.assertTrue(command["raw"])
            self.assertFalse(command["isolated"])
            self.assertTrue(command["env_matches_legacy"])
            self.assertIsNone(command["envelope"])

    def test_engaged_child_rejects_selector_generation_changed_after_parent_validation(self) -> None:
        payload = self._run("generation")

        self.assertTrue(payload["advanced"])
        commands = payload["commands"]
        self.assertEqual(len(commands), 1)
        command = commands[0]
        self.assertFalse(command["raw"])
        self.assertTrue(command["isolated"])
        self.assertTrue(command["bridge"])
        self.assertTrue(command["python_entry"])
        self.assertTrue(command["entry_path"].endswith("/scripts/plan_lint.py"))
        self.assertEqual(command["envelope"]["state"], "engaged")
        self.assertEqual(command["envelope"]["generation_sha256"], payload["outer_generation"])
        self.assertEqual(len(payload["child_returncodes"]), 1)
        self.assertNotEqual(payload["child_returncodes"][0], 0)
        self.assertEqual(payload["child_authority_successes"], [False])
        self.assertEqual(payload["child_expectation_errors"], [True])
        error = payload["error"]
        self.assertIsInstance(error, dict)
        assert isinstance(error, dict)
        self.assertIn("actual authority context differs from inherited expectation", error["message"])

    def test_engaged_child_accepts_unrelated_target_evolution(self) -> None:
        payload = self._run("unrelated")

        self.assertTrue(payload["advanced"])
        self.assertIsNone(payload["error"])
        self.assertEqual(payload["result"], {"metric": "3/3 exit=0", "status": "pass"})
        self.assertEqual(payload["child_returncodes"], [0, 0, 0])
        self.assertEqual(payload["child_authority_successes"], [True, True, True])
        self.assertEqual(payload["child_expectation_errors"], [False, False, False])
        commands = payload["commands"]
        self.assertEqual(len(commands), 3)
        for command in commands:
            self.assertTrue(command["isolated"])
            self.assertTrue(command["bridge"])
            self.assertTrue(command["python_entry"])
            self.assertEqual(command["envelope"]["state"], "engaged")
            self.assertEqual(command["envelope"]["generation_sha256"], payload["outer_generation"])


if __name__ == "__main__":
    unittest.main()

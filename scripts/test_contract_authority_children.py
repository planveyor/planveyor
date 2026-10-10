#!/usr/bin/env python3
"""Unit checks for retained-buffer child command builders."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shlex
import sys
from types import SimpleNamespace
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).with_name("contract_authority_children.py")
SPEC = importlib.util.spec_from_file_location("contract_authority_children", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class AuthorityChildCommandTests(unittest.TestCase):
    def _modules(self, *, events: list[str]) -> tuple[object, object]:
        def validate(context: object) -> None:
            self.assertIs(context, self.context)
            events.append("validate")

        def bootstrap(pin: object) -> str:
            self.assertIs(pin, self.pin)
            events.append("bootstrap")
            return "BOOTSTRAP-LITERAL"

        def summary(pin: object) -> dict[str, object]:
            self.assertIs(pin, self.pin)
            events.append("summary")
            return dict(self.summary)

        def shell_loader(pin: object) -> str:
            self.assertIs(pin, self.pin)
            events.append("shell-loader")
            return "loader_function() { :; }\n"

        return (
            SimpleNamespace(validate_before_effect=validate),
            SimpleNamespace(
                authority_bootstrap_literal=bootstrap,
                authority_shell_loader_literal=shell_loader,
                loaded_runtime_pin_summary=summary,
            ),
        )

    def setUp(self) -> None:
        self.runtime_root = Path("/runtime")
        self.pin = SimpleNamespace(runtime_root=self.runtime_root)
        self.context = SimpleNamespace(
            state="engaged",
            runtime_pin=self.pin,
            project_root=Path("/project"),
        )
        self.summary = {
            "schema_version": "planveyor_runtime_pin_summary.v1",
            "runtime_root": "/runtime",
            "git_dir": "/runtime/.git",
            "runtime_api_version": 1,
            "commit": "commit",
            "tree": "tree",
            "closure_spec_sha256": "spec",
            "closure_rows_sha256": "rows",
            "closure_sha256": "closure",
            "pin_sha256": "pin",
        }

    def _summary_text(self) -> str:
        return json.dumps(self.summary, ensure_ascii=True, allow_nan=False, separators=(",", ":"), sort_keys=True)

    def test_python_entry_uses_one_validated_bootstrap_and_exact_grammar(self) -> None:
        events: list[str] = []
        with mock.patch.object(MODULE, "_authority_modules", return_value=self._modules(events=events)):
            argv = MODULE.python_entry_argv(
                self.context,
                self.runtime_root / "scripts" / "review_target_snapshot.py",
                ("docs/plans/active.md", "--current-bundle"),
                python_executable="/usr/bin/python3",
            )

        self.assertEqual(events, ["validate", "summary", "bootstrap"])
        self.assertEqual(
            argv,
            [
                "/usr/bin/python3",
                "-I",
                "-B",
                "-c",
                "BOOTSTRAP-LITERAL",
                "/runtime/scripts/contract_authority_bridge.py",
                "python-entry",
                "--runtime-pin-summary",
                self._summary_text(),
                "--path",
                "/runtime/scripts/review_target_snapshot.py",
                "--",
                "docs/plans/active.md",
                "--current-bundle",
            ],
        )

    def test_python_stdin_uses_the_same_validated_bootstrap(self) -> None:
        events: list[str] = []
        with mock.patch.object(MODULE, "_authority_modules", return_value=self._modules(events=events)):
            argv = MODULE.python_stdin_argv(
                self.context,
                ("arg-one",),
                python_executable="/usr/bin/python3",
            )

        self.assertEqual(events, ["validate", "summary", "bootstrap"])
        self.assertEqual(argv[-5:], ["python-stdin", "--runtime-pin-summary", self._summary_text(), "--", "arg-one"])
        self.assertEqual(argv[5], "/runtime/scripts/contract_authority_bridge.py")

    def test_shell_command_installs_loader_before_the_only_facade_anchor(self) -> None:
        events: list[str] = []
        with mock.patch.object(MODULE, "_authority_modules", return_value=self._modules(events=events)):
            argv = MODULE.shell_command(
                self.context,
                "planveyor_plan_bundle --preflight docs/plans/active.md",
            )

        self.assertEqual(events, ["validate", "shell-loader", "summary"])
        self.assertEqual(argv[:2], ["/bin/zsh", "-dfc"])
        self.assertEqual(
            argv[2],
            "export PLANVEYOR_CHILD_SHELL_V1=planveyor-child-shell.v1\n"
            "export PLANVEYOR_RUNTIME_SOURCE_KIND=git\n"
            "export PLANVEYOR_ROOT=/runtime\n"
            "export PLANVEYOR_PROJECT_ROOT=/project\n"
            "loader_function() { :; }\n"
            "planveyor_source_runtime /runtime/scripts/planveyor.zsh "
            f"{shlex.quote(self._summary_text())} || exit $?\n"
            "planveyor_plan_bundle --preflight docs/plans/active.md",
        )
        self.assertNotIn("source scripts/planveyor.zsh", argv[2])

    def test_builder_rejects_legacy_context_without_creating_a_raw_fallback(self) -> None:
        legacy = SimpleNamespace(state="legacy", runtime_pin=None)
        with self.assertRaisesRegex(MODULE.AuthorityChildLaunchError, "engaged context"):
            MODULE.python_entry_argv(legacy, "/runtime/scripts/plan_lint.py")

    def test_python_entry_rejects_paths_outside_the_pinned_runtime(self) -> None:
        events: list[str] = []
        with mock.patch.object(MODULE, "_authority_modules", return_value=self._modules(events=events)):
            with self.assertRaisesRegex(MODULE.AuthorityChildLaunchError, "outside the pinned runtime root"):
                MODULE.python_entry_argv(self.context, "/other/scripts/plan_lint.py")

        self.assertEqual(events, ["validate"])


if __name__ == "__main__":
    unittest.main()

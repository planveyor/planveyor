#!/usr/bin/env python3
"""Regression coverage for post-merge content-profile parser and facade seams."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import textwrap
import unittest


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import contract_authority_context as source_context  # noqa: E402
from test_contract_authority_support import AuthorityFixture, commit_all, tree_snapshot  # noqa: E402


PUBLIC_IDENTITIES = ("default", "planveyor", "target-local")
REJECTED_IDENTITIES = ("retired_profile", "unknown")
PARSER_SCRIPTS = (
    (
        "post_merge_receipt_preflight.py",
        ("plan_harvest", "--path", "docs/reviews/missing.md", "--format", "json"),
        "--repo-root",
    ),
    ("merge_bundle_report.py", ("--format", "json"), "--root"),
    ("post_merge_ready_to_push_closeout.py", ("--format", "json"), "--root"),
    ("merge_range_verdict_digest.py", ("--format", "json"), "--repo-root"),
)
FACADE_WRAPPERS = (
    (
        "planveyor_post_merge_receipt_preflight",
        "post_merge_receipt_preflight.py",
        ("plan_harvest", "--path", "docs/reviews/missing.md", "--format", "json"),
        "--repo-root",
    ),
    ("planveyor_merge_bundle_report", "merge_bundle_report.py", ("--format", "json"), "--root"),
    (
        "planveyor_post_merge_ready_to_push_closeout",
        "post_merge_ready_to_push_closeout.py",
        ("--format", "json"),
        "--root",
    ),
    (
        "planveyor_merge_range_verdict_digest",
        "merge_range_verdict_digest.py",
        ("--format", "json"),
        "--repo-root",
    ),
)


class PostMergeContentProfileBoundaryTests(unittest.TestCase):
    def _run_parser(self, script_name: str, arguments: tuple[str, ...], root_flag: str, root: Path) -> subprocess.CompletedProcess[str]:
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run(
            [sys.executable, "-B", str(ROOT / "scripts" / script_name), *arguments, root_flag, str(root)],
            cwd=root,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def _enable_fixture_admission(self, fixture: AuthorityFixture) -> None:
        context_path = fixture.runtime_root / "scripts" / "contract_authority_context.py"
        original = context_path.read_text(encoding="utf-8")
        incomplete = "ENGAGED_ADMISSION_COMPLETE: Final[bool] = False"
        complete = "ENGAGED_ADMISSION_COMPLETE: Final[bool] = True"
        if incomplete not in original:
            self.assertIn(complete, original)
            return
        context_path.write_text(
            original.replace(
                incomplete,
                complete,
                1,
            ),
            encoding="utf-8",
        )
        fixture.runtime_commit = commit_all(fixture.runtime_root, "enable disposable engaged admission")

    def _run_pinned_shell(self, fixture: AuthorityFixture, command: str) -> subprocess.CompletedProcess[str]:
        environment = fixture.environment()
        environment["PYBIN"] = str(Path(sys.executable).resolve())
        facade = shlex.quote(str(fixture.runtime_root / "scripts" / "planveyor.zsh"))
        return subprocess.run(
            [
                "/bin/zsh",
                "-fc",
                fixture.shell_loader()
                + f"\nplanveyor_source_runtime {facade} || exit $?\n"
                + "[[ \"${_PLANVEYOR_AUTHORITY_SOURCE_STATE:-}\" == pinned ]] || exit 96\n"
                + command,
            ],
            cwd=fixture.target_root,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=90,
        )

    def _assert_semantic_payload(self, script_name: str, payload: object) -> None:
        self.assertIsInstance(payload, dict)
        if script_name == "post_merge_receipt_preflight.py":
            self.assertEqual(payload.get("schema_version"), "post_merge_receipt_preflight.v1")
            self.assertEqual(payload.get("status"), "blocked")
            self.assertEqual(payload.get("step"), "plan_harvest")
            errors = payload.get("errors")
            self.assertIsInstance(errors, list)
            self.assertTrue(errors)
            return
        if script_name == "merge_bundle_report.py":
            self.assertEqual(payload.get("status"), "blocked")
            errors = payload.get("errors")
            self.assertIsInstance(errors, list)
            self.assertTrue(errors)
            for error in errors:
                self.assertIsInstance(error, dict)
                self.assertTrue(error.get("code"), error)
                self.assertTrue(error.get("detail"), error)
            return
        if script_name == "post_merge_ready_to_push_closeout.py":
            self.assertEqual(payload.get("status"), "blocked")
            self.assertEqual(payload.get("action"), "blocked")
            blocker = payload.get("blocker")
            self.assertIsInstance(blocker, dict)
            self.assertEqual(blocker.get("code"), "red_report")
            self.assertEqual(payload.get("why_blocked"), "red_merge_bundle_report")
            return
        if script_name == "merge_range_verdict_digest.py":
            digest = payload.get("merge_range_verdict_digest")
            self.assertIsInstance(digest, dict)
            self.assertEqual(digest.get("schema_version"), "merge_range_verdict_digest.v1")
            self.assertEqual(digest.get("digest_status"), "blocked")
            return
        self.fail(f"unexpected F1 helper: {script_name}")

    def _write_bound_fixture_tracker(self, fixture: AuthorityFixture) -> None:
        context_result = self._run_pinned_shell(
            fixture,
            "_planveyor_authority_context_for_reader post-merge-content-profile-boundary",
        )
        self.assertEqual(context_result.returncode, 0, context_result.stdout + context_result.stderr)
        context = json.loads(context_result.stdout)
        self.assertEqual(context["state"], "engaged")
        policy_path = fixture.target_root / "docs/_meta/planveyor_merge_gate_policy.v1.json"
        tracker_path = fixture.target_root / ".planveyor.merge_tracker.md"
        tracker_path.write_text(
            "POLICY_SCHEMA=planveyor_merge_gate_policy.v1\n"
            f"POLICY_SHA256={hashlib.sha256(policy_path.read_bytes()).hexdigest()}\n"
            f"AUTHORITY_GENERATION={context['generation_sha256']}\n",
            encoding="utf-8",
        )

    def test_four_parsers_have_exact_public_identity_set_and_reject_retired_ids(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor-post-merge-profile-") as temporary:
            root = Path(temporary).resolve()
            subprocess.run(["git", "-C", str(root), "init", "--quiet"], check=True, capture_output=True)
            for script_name, arguments, root_flag in PARSER_SCRIPTS:
                source = (ROOT / "scripts" / script_name).read_text(encoding="utf-8")
                with self.subTest(script=script_name, assertion="exact_choices"):
                    self.assertIn('choices=("default", "planveyor", "target-local")', source)
                for identity in PUBLIC_IDENTITIES:
                    with self.subTest(script=script_name, identity=identity):
                        result = self._run_parser(
                            script_name,
                            (*arguments, "--content-profile-id", identity),
                            root_flag,
                            root,
                        )
                        self.assertIn(result.returncode, (1, 2), result.stdout + result.stderr)
                        self.assertNotIn("invalid choice", result.stderr)
                        self._assert_semantic_payload(script_name, json.loads(result.stdout))
                for identity in REJECTED_IDENTITIES:
                    with self.subTest(script=script_name, rejected_identity=identity):
                        result = self._run_parser(
                            script_name,
                            (*arguments, "--content-profile-id", identity),
                            root_flag,
                            root,
                        )
                        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                        self.assertIn("invalid choice", result.stderr)

    def test_engaged_pinned_facade_forwards_target_local_to_all_four_helpers(self) -> None:
        with AuthorityFixture(identity="planveyor") as fixture:
            self._enable_fixture_admission(fixture)
            fixture.activate_planveyor(source_context.STATIC_PLANVEYOR_MERGE_REQUIRED_ENGAGED_PATHS)
            for index, (wrapper, helper, arguments, root_flag) in enumerate(FACADE_WRAPPERS):
                with self.subTest(wrapper=wrapper):
                    capture = fixture.root / f"{index}-python-boundary.txt"
                    command = textwrap.dedent(
                        f"""\\
                        _planveyor_py_any() {{
                          : > {shlex.quote(str(capture))}
                          local argument
                          for argument in "$@"; do
                            print -r -- "$argument" >> {shlex.quote(str(capture))}
                          done
                        }}
                        {wrapper} {' '.join(shlex.quote(argument) for argument in arguments)}
                        """
                    )
                    result = self._run_pinned_shell(fixture, command)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    received = capture.read_text(encoding="utf-8").splitlines()
                    self.assertEqual(received[0], str(fixture.runtime_root / "scripts" / helper))
                    self.assertEqual(received[1:3], ["--content-profile-id", "target-local"])
                    root_index = received.index(root_flag)
                    self.assertEqual(received[root_index + 1], str(fixture.target_root))

    def test_engaged_pinned_facade_reaches_real_helpers_with_target_local_semantics(self) -> None:
        with AuthorityFixture(identity="planveyor") as fixture:
            self._enable_fixture_admission(fixture)
            fixture.activate_planveyor(source_context.STATIC_PLANVEYOR_MERGE_REQUIRED_ENGAGED_PATHS)
            self._write_bound_fixture_tracker(fixture)
            for wrapper, helper, arguments, _root_flag in FACADE_WRAPPERS:
                with self.subTest(wrapper=wrapper):
                    before = tree_snapshot(fixture.target_root)
                    result = self._run_pinned_shell(
                        fixture,
                        f"{wrapper} {' '.join(shlex.quote(argument) for argument in arguments)}",
                    )
                    self.assertIn(result.returncode, (1, 2), result.stdout + result.stderr)
                    self.assertNotIn("invalid choice", result.stderr)
                    self.assertNotIn("Traceback", result.stdout + result.stderr)
                    self.assertTrue(result.stdout.strip(), result.stdout + result.stderr)
                    self._assert_semantic_payload(helper, json.loads(result.stdout))
                    self.assertEqual(tree_snapshot(fixture.target_root), before)


if __name__ == "__main__":
    unittest.main()

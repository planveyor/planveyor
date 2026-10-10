#!/usr/bin/env python3
"""Focused authority-context regressions for docs closeout reader composition."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

try:
    from scripts import contract_authority_context as source_authority
    from scripts.test_contract_authority_support import AuthorityFixture, git, write
    from scripts.authority_bootstrap_test_support import run_python_stdin
except ImportError:  # pragma: no cover - supports direct ``scripts/`` execution.
    import contract_authority_context as source_authority
    from test_contract_authority_support import AuthorityFixture, git, write
    from authority_bootstrap_test_support import run_python_stdin


PLAN_REL = "docs/plans/authority_closeout_context.md"


class DocsCloseoutAuthorityContextTests(unittest.TestCase):
    """Run each regression against a copied, engaged disposable runtime."""

    def _prepare_fixture(self) -> AuthorityFixture:
        fixture = AuthorityFixture(identity="planveyor")
        fixture.activate_planveyor(source_authority.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS)
        write(
            fixture.target_root,
            PLAN_REL,
            "# Plan: authority closeout context fixture\n\n"
            "**Plan type:** dev\n"
            "**Status:** Draft\n",
        )
        git(fixture.target_root, "add", "--", PLAN_REL)
        git(fixture.target_root, "commit", "--quiet", "-m", "add authority closeout context plan")
        return fixture

    def _run_target_python(
        self,
        fixture: AuthorityFixture,
        source: str,
    ) -> subprocess.CompletedProcess[str]:
        return run_python_stdin(fixture, source)

    def test_closeout_rejects_valid_selector_generation_change_after_outer_validation(self) -> None:
        with self._prepare_fixture() as fixture:
            result = self._run_target_python(
                fixture,
                """
import json
from pathlib import Path

import contract_authority_context as authority
import docs_closeout
import plan_status_oracle

root = Path.cwd()
outer = authority.resolve_top_level_context(root)
records = {"outer_validation_calls": 0}
actual_oracle_result = plan_status_oracle.oracle_result

def record_oracle_result(plan_path, *, context=None):
    records["oracle_context_is_outer"] = context is outer
    return actual_oracle_result(plan_path, context=context)

plan_status_oracle.oracle_result = record_oracle_result
actual_validate = docs_closeout.validate_before_effect
advanced = False

def advance_after_outer_validation(context):
    global advanced
    records["outer_validation_calls"] += 1
    actual_validate(context)
    if advanced:
        return
    advanced = True
    selector_path = root / authority._snapshot.MARKER_PATH
    selector = json.loads(selector_path.read_text(encoding="utf-8"))
    selector["required_runtime_api"] = {"minimum": 4, "maximum": 5}
    selector_path.write_text(
        json.dumps(selector, ensure_ascii=False, sort_keys=True) + "\\n",
        encoding="utf-8",
    )

docs_closeout.validate_before_effect = advance_after_outer_validation
error = None
try:
    docs_closeout.classify_docs_closeout(
        plan_ref="docs/plans/authority_closeout_context.md",
        bundle_payload={"bundle_ok": False, "closeout_kind": "unknown"},
        root=root,
        context=outer,
        content_profile_id="target-local",
    )
except authority.ContractAuthorityError as exc:
    error = {"reason_code": exc.reason_code, "message": str(exc)}
finally:
    docs_closeout.validate_before_effect = actual_validate
    plan_status_oracle.oracle_result = actual_oracle_result

fresh = authority.resolve_top_level_context(root)
print(json.dumps({
    "advanced": advanced,
    "error": error,
    "final_generation": fresh.generation_sha256,
    "outer_generation": outer.generation_sha256,
    "records": records,
}, sort_keys=True))
""",
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["advanced"])
        self.assertNotEqual(payload["final_generation"], payload["outer_generation"])
        self.assertEqual(payload["records"]["outer_validation_calls"], 1)
        self.assertIs(payload["records"]["oracle_context_is_outer"], True)
        self.assertEqual(payload["error"]["reason_code"], "authority_generation_mismatch")

    def test_closeout_preserves_context_through_oracle_checkpoint_and_builder(self) -> None:
        with self._prepare_fixture() as fixture:
            result = self._run_target_python(
                fixture,
                """
import json
from pathlib import Path

import contract_authority_context as authority
import docs_closeout
import plan_lint
import plan_status_oracle

root = Path.cwd()
outer = authority.resolve_top_level_context(root)
records = {}
actual_oracle_result = plan_status_oracle.oracle_result
actual_checkpoint = plan_status_oracle.semantic_cycle_checkpoint_report
actual_builder = plan_lint.build_semantic_cycle_checkpoint_report

def record_oracle_result(plan_path, *, context=None):
    records["oracle_context_is_outer"] = context is outer
    return actual_oracle_result(plan_path, context=context)

def record_checkpoint(plan_path, *, context=None):
    records["checkpoint_context_is_outer"] = context is outer
    return actual_checkpoint(plan_path, context=context)

def record_builder(plan_path, *, context=None):
    records.setdefault("builder_context_is_outer", []).append(context is outer)
    return actual_builder(plan_path, context=context)

plan_status_oracle.oracle_result = record_oracle_result
plan_status_oracle.semantic_cycle_checkpoint_report = record_checkpoint
plan_lint.build_semantic_cycle_checkpoint_report = record_builder
try:
    closeout = docs_closeout.classify_docs_closeout(
        plan_ref="docs/plans/authority_closeout_context.md",
        bundle_payload={"bundle_ok": False, "closeout_kind": "unknown"},
        root=root,
        context=outer,
        content_profile_id="target-local",
    )
    direct = actual_checkpoint(root / "docs/plans/authority_closeout_context.md")
finally:
    plan_lint.build_semantic_cycle_checkpoint_report = actual_builder
    plan_status_oracle.semantic_cycle_checkpoint_report = actual_checkpoint
    plan_status_oracle.oracle_result = actual_oracle_result

print(json.dumps({
    "closeout_state": closeout["state"],
    "direct_report_state": direct["state"],
    "records": records,
}, sort_keys=True))
""",
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["closeout_state"], "no_op")
        self.assertIsInstance(payload["direct_report_state"], str)
        self.assertEqual(
            payload["records"],
            {
                "oracle_context_is_outer": True,
                "checkpoint_context_is_outer": True,
                "builder_context_is_outer": [True, False],
            },
        )

    def test_closeout_allows_unrelated_target_evolution_with_the_outer_context(self) -> None:
        with self._prepare_fixture() as fixture:
            result = self._run_target_python(
                fixture,
                """
import json
from pathlib import Path
import subprocess

import contract_authority_context as authority
import docs_closeout
import plan_status_oracle

root = Path.cwd()
outer = authority.resolve_top_level_context(root)
records = {"outer_validation_calls": 0}
actual_oracle_result = plan_status_oracle.oracle_result

def record_oracle_result(plan_path, *, context=None):
    records["oracle_context_is_outer"] = context is outer
    return actual_oracle_result(plan_path, context=context)

plan_status_oracle.oracle_result = record_oracle_result
actual_validate = docs_closeout.validate_before_effect
advanced = False

def advance_after_outer_validation(context):
    global advanced
    records["outer_validation_calls"] += 1
    actual_validate(context)
    if advanced:
        return
    advanced = True
    (root / "unrelated-target-evolution.txt").write_text("allowed\\n", encoding="utf-8")
    subprocess.run(
        [
            "git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgSign=false",
            "-C", str(root), "add", "--", "unrelated-target-evolution.txt",
        ],
        check=True,
    )
    subprocess.run(
        [
            "git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgSign=false",
            "-C", str(root), "commit", "--quiet", "-m", "unrelated target evolution",
        ],
        check=True,
    )

docs_closeout.validate_before_effect = advance_after_outer_validation
try:
    closeout = docs_closeout.classify_docs_closeout(
        plan_ref="docs/plans/authority_closeout_context.md",
        bundle_payload={"bundle_ok": False, "closeout_kind": "unknown"},
        root=root,
        context=outer,
        content_profile_id="target-local",
    )
finally:
    docs_closeout.validate_before_effect = actual_validate
    plan_status_oracle.oracle_result = actual_oracle_result

fresh = authority.resolve_top_level_context(root)
print(json.dumps({
    "advanced": advanced,
    "closeout_state": closeout["state"],
    "final_generation": fresh.generation_sha256,
    "outer_generation": outer.generation_sha256,
    "records": records,
}, sort_keys=True))
""",
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["advanced"])
        self.assertEqual(payload["closeout_state"], "no_op")
        self.assertEqual(payload["final_generation"], payload["outer_generation"])
        self.assertEqual(payload["records"]["outer_validation_calls"], 1)
        self.assertIs(payload["records"]["oracle_context_is_outer"], True)


if __name__ == "__main__":
    unittest.main()

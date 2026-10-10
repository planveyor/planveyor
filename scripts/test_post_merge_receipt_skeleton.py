#!/usr/bin/env python3
from __future__ import annotations

from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
from textwrap import dedent
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


MODULE = _load_module("post_merge_receipt_skeleton", Path(__file__).with_name("post_merge_receipt_skeleton.py"))
MERGE_BUNDLE_REPORT = _load_module("_skeleton_merge_bundle_report", Path(__file__).with_name("merge_bundle_report.py"))
PLAN_HARVEST_LINT = _load_module("_skeleton_plan_harvest_lint", Path(__file__).with_name("plan_harvest_lint.py"))
POST_MERGE_AUDIT_LINT = _load_module("_skeleton_post_merge_audit_lint", Path(__file__).with_name("post_merge_audit_lint.py"))

import post_merge_operational_receipt as OPERATIONAL_RECEIPT
import review_schema_contract
from test_support.process_contract_fixtures import run_zsh_fixture, temporary_git_root


class PostMergeReceiptSkeletonTests(unittest.TestCase):
    def _write_markdown(self, root: Path, rel_path: str, body: str) -> Path:
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        return target

    def _green_backlog(self) -> str:
        return dedent(
            """\
            # Follow-ups backlog — Architect range harvest

            **Date:** 2026-04-19 11:09 MSK
            **Source:** Architect plan harvest
            **Status:** closed

            ## Range result
            - `NO FOLLOWUPS` — reason: no remaining actionable debt after full-wave harvest.
            """
        )

    def _extract_operational_payload(self, text: str) -> dict[str, object]:
        before, _, after = text.partition("```json\n")
        self.assertTrue(after, f"missing operational JSON block after:\n{before}")
        raw_json, _, _ = after.partition("\n```")
        return json.loads(raw_json)

    def _run_wrapper(self, *args: str) -> subprocess.CompletedProcess[str]:
        command = (
            f"source {shlex.quote(str(REPO_ROOT / 'scripts' / 'planveyor.zsh'))} && "
            f"planveyor_post_merge_receipt_skeleton {' '.join(shlex.quote(arg) for arg in args)}"
        )
        return run_zsh_fixture(
            command,
            cwd=REPO_ROOT,
            path=os.environ.get("PATH", os.defpath),
            pybin=str(Path(sys.executable).resolve()),
            fixture_env={"PYTHONDONTWRITEBYTECODE": "1"},
            check=False,
        )

    def test_all_supported_families_render_without_stub_marker(self) -> None:
        for family in MODULE.SUPPORTED_FAMILIES:
            with self.subTest(family=family):
                rendered = MODULE.render_skeleton(family)
                self.assertTrue(rendered.endswith("\n"))
                self.assertNotIn("path-tracking stub", rendered.lower())

    def test_review_skeletons_use_shared_schema_contract(self) -> None:
        expected = f"**Schema version:** {review_schema_contract.CURRENT_REVIEW_SCHEMA_VERSION}"

        self.assertEqual(MODULE.CURRENT_REVIEW_SCHEMA_VERSION, review_schema_contract.CURRENT_REVIEW_SCHEMA_VERSION)
        self.assertIn(expected, MODULE.render_skeleton("plan_harvest"))
        self.assertIn(expected, MODULE.render_skeleton("post_merge_audit"))

    def test_plan_harvest_skeleton_passes_current_lint_with_companion_backlog(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            report_path = "docs/reviews/260419_1109_plan_harvest_range_deadbee_feed123.md"
            backlog_path = "docs/followups/260419_1109_followups_range_deadbee_feed123.md"
            rendered = MODULE.render_skeleton("plan_harvest")
            self.assertIn("used_for_decision", rendered)
            self.assertIn("not_used_for_decision", rendered)
            self.assertIn("harvest_file_followups_result: `NO FOLLOWUPS`", rendered)
            self.assertIn("harvest_file_followups_count: 0", rendered)
            self.assertIn(
                "(idempotency): append_new=0, merge_source=0, possible_duplicate=0, "
                "route_fallback=0, unparsed_bullets=0.",
                rendered,
            )
            self._write_markdown(root, report_path, rendered)
            self._write_markdown(root, backlog_path, self._green_backlog())

            artifacts = PLAN_HARVEST_LINT.load_harvest_artifacts(root, [report_path, backlog_path])
            findings = PLAN_HARVEST_LINT.lint_harvest_artifacts(artifacts)

        self.assertEqual(findings, [])

    def test_plan_harvest_stale_retrieval_skeleton_fails_current_lint(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            report_path = "docs/reviews/260419_1109_plan_harvest_range_deadbee_feed123.md"
            backlog_path = "docs/followups/260419_1109_followups_range_deadbee_feed123.md"
            stale_rendered = MODULE.render_skeleton("plan_harvest").replace(
                "used_for_decision",
                "stale_decision_flag",
            )
            self._write_markdown(root, report_path, stale_rendered)
            self._write_markdown(root, backlog_path, self._green_backlog())

            artifacts = PLAN_HARVEST_LINT.load_harvest_artifacts(root, [report_path, backlog_path])
            findings = PLAN_HARVEST_LINT.lint_harvest_artifacts(artifacts)

        self.assertTrue(findings)
        messages = "\n".join(finding.message for finding in findings)
        self.assertIn("Docs retrieval metrics receipt table is missing columns: used_for_decision", messages)

    def test_post_merge_audit_skeleton_passes_current_lint(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            report_path = "docs/reviews/260419_1112_post_merge_audit_schema_current.md"
            self._write_markdown(root, report_path, MODULE.render_skeleton("post_merge_audit"))

            artifacts = POST_MERGE_AUDIT_LINT.load_audit_artifacts(root, [report_path])
            findings = POST_MERGE_AUDIT_LINT.lint_audit_artifacts(artifacts)

        self.assertEqual(findings, [])

    def test_operational_receipt_skeleton_carries_required_schema_fields(self) -> None:
        rendered = MODULE.render_skeleton("post_merge_operational_receipt")
        payload = self._extract_operational_payload(rendered)

        self.assertEqual(MODULE.OPERATIONAL_SCHEMA_VERSION, OPERATIONAL_RECEIPT.SCHEMA_VERSION)
        self.assertEqual(payload["schema_version"], "post_merge_operational_receipt.v1")
        self.assertEqual(payload["schema_version"], OPERATIONAL_RECEIPT.SCHEMA_VERSION)
        self.assertIn("archive_snapshot", payload)
        self.assertIn("docs_hygiene_suggest_summary", payload)
        self.assertIn("followups_triage_launch_receipt", payload)
        self.assertIn("process_improvements_open_summary", payload)
        self.assertEqual(payload["steps"][0]["step"], "docs_hygiene_suggest")

    def test_canon_sweep_receipt_skeleton_carries_handoff_fields(self) -> None:
        rendered = MODULE.render_skeleton("canon_sweep_receipt")

        self.assertIn("proof_kind", rendered)
        self.assertIn("changed_shared_canon_files_count", rendered)
        self.assertIn("snapshot_path", rendered)
        self.assertIn("report_path", rendered)
        self.assertIn("no_op_reason", rendered)
        self.assertIn("target_repo_impact", rendered)
        self.assertIn("source_only|shared_consumer|shared_multi|none", rendered)
        self.assertNotIn("retired_impact", rendered)
        self.assertNotIn("unsupported_impact", rendered)
        self.assertIn("packetization_handoff", rendered)
        self.assertIn("step:packetization_gate", rendered)

    def test_canon_sweep_receipt_skeleton_uses_supported_non_final_proof_kind(self) -> None:
        rendered = MODULE.render_skeleton("canon_sweep_receipt")

        self.assertIn("- proof_kind: `report`", rendered)
        self.assertNotIn("structural_skeleton", rendered)
        self.assertNotIn("bounded_canon_sweep_report", rendered)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            rel_path = "docs/reviews/260419_1115_canon_sweep_receipt_range_deadbee_feed123.md"
            self._write_markdown(root, rel_path, rendered)
            _receipts, errors = MERGE_BUNDLE_REPORT._receipt_preflight_canon_sweep(
                root=root,
                rel_path=rel_path,
                packetization_required=False,
                packetization_reports=[],
            )

        details = "\n".join(error["detail"] for error in errors)
        self.assertIn("status=Draft is not final", details)
        self.assertIn("must have exactly one meaningful closure lane", details)
        self.assertNotIn("unsupported proof_kind", details)

    def test_docs_finalize_receipt_frame_is_deterministic_and_red_until_architect_fill(self) -> None:
        rendered = MODULE.render_skeleton("docs_finalize_receipt")
        self.assertIn("**Role:** Architect", rendered)
        self.assertIn("**Schema version:** review.v1", rendered)
        self.assertIn("docs_finalize_receipt_path=docs/reviews/<stamp>", rendered)
        self.assertIn("## Process improvements", rendered)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            rel_path = "docs/reviews/260829_1808_docs_finalize_receipt_range_deadbee_feed123.md"
            self._write_markdown(root, rel_path, rendered)
            payload = MERGE_BUNDLE_REPORT.validate_post_merge_receipt_preflight(
                root=root,
                step="docs_finalize",
                path=rel_path,
                role="Architect",
                docs_finalize_range="deadbeef..feed1234",
            )

        self.assertEqual(payload["status"], "blocked")
        codes = {error["code"] for error in payload["errors"]}
        self.assertIn("non_final_artifact_status", codes)
        self.assertIn("docs_finalize_receipt_identity_mismatch", codes)
        self.assertIn("docs_finalize_receipt_readback_mismatch", codes)

    def test_out_file_matches_stdout_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "nested" / "canon_sweep_receipt.md"
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                result = MODULE.main(["canon_sweep_receipt", "--out", str(out_path)])

            self.assertEqual(result, 0)
            self.assertEqual(stdout.getvalue(), out_path.read_text(encoding="utf-8"))

    def test_wrapper_help_exposes_all_families(self) -> None:
        result = self._run_wrapper("--help")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("canon_sweep_receipt", result.stdout)
        self.assertIn("docs_finalize_receipt", result.stdout)
        self.assertIn("post_merge_operational_receipt", result.stdout)

    def test_wrapper_output_matches_direct_renderer(self) -> None:
        result = self._run_wrapper("canon_sweep_receipt")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, MODULE.render_skeleton("canon_sweep_receipt"))


if __name__ == "__main__":
    unittest.main()

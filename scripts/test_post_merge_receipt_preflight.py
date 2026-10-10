#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from textwrap import dedent
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from test_support.process_contract_fixtures import run_zsh_fixture, temporary_git_root, write_text_fixture


MODULE_PATH = Path(__file__).with_name("post_merge_receipt_preflight.py")
REPO_ROOT = MODULE_PATH.parent.parent
SPEC = importlib.util.spec_from_file_location("post_merge_receipt_preflight", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

import merge_bundle_report


VALID_PLAN_HARVEST = """\
# Plan harvest

**Status:** Done

## Follow-up harvest triage/import receipt
- mode: range
- dry_run_append_new: 0
- apply_append_new: 0
- idempotency_append_new: 0

## Process-improvement promotion decisions
- process_improvements_open_summary: source=docs/process_improvements/promotion_surface.md; lane=separate; ordinary_followups=NO FOLLOWUPS; open=0; triaged=0; promoted=0; null_execution=0; owner_or_next_step=N/A

## Docs retrieval metrics receipt
| repo | query_total | evaluated_total | read_log_status | read_events_total |
| --- | ---: | ---: | --- | ---: |
| source | 0 | 0 | present | 0 |

## Golden Path lane receipt
- lane: tooling_process
- active carrier: docs/guides/golden_paths.md#post-merge-plan-harvest

## ADR candidates / durable decisions
- outcome: no changes needed (why=no durable decision)

## Canon/follow-up summary
- result: no remaining canon or follow-up debt

## Follow-ups (extracted; без дублей)
- Result: `NO FOLLOWUPS`
"""

VALID_CURRENT_PLAN_HARVEST = VALID_PLAN_HARVEST.replace(
    "**Status:** Done\n",
    "**Status:** Done\n**Schema version:** review.v1\n",
).replace(
    "## Follow-up harvest triage/import receipt\n",
    "## Follow-up harvest triage/import receipt\n"
    "- harvest_file_followups_result: `NO FOLLOWUPS` — no remaining actionable debt after full-wave harvest.\n"
    "- harvest_file_followups_count: 0\n"
    "- triage (idempotency): append_new=0, possible_duplicate=0, route_fallback=0, unparsed_bullets=0.\n",
)

BAD_PLAN_HARVEST = """\
# Plan harvest

**Status:** Done

## Follow-up harvest triage/import receipt
- mode: range

## Process-improvement promotion decisions
- process_improvements_open_summary: source=docs/process_improvements/promotion_surface.md; lane=separate; ordinary_followups=NO FOLLOWUPS; open=0; triaged=0; promoted=0; null_execution=0; owner_or_next_step=N/A

## Golden Path lane receipt
- lane: tooling_process

## ADR candidates / durable decisions
- outcome: no changes needed

## Canon/follow-up summary
- result: no debt

## Follow-ups (extracted; без дублей)
- Result: `NO FOLLOWUPS`
"""

VALID_CANON_SWEEP = """\
# Canon sweep receipt

**Status:** Done

## Canon sweep receipt
- changed_shared_canon_files_count: 0
- changed_shared_canon_files: none
- proof_kind: no_op
- target_repo_impact: none
- snapshot_path: N/A (why=no snapshot)
- report_path: N/A (why=no report)
- no_op_reason: no_shared_canon_delta
- packetization_handoff: N/A (why=no shared target impact)
"""

VALID_CANON_SWEEP_REPORT = """\
# Canon sweep receipt

**Status:** Done

## Canon sweep receipt
- changed_shared_canon_files_count: 1
- changed_shared_canon_files: docs/playbooks/docs_canon_sweep.md
- proof_kind: report
- target_repo_impact: source_only
- snapshot_path: N/A (why=no snapshot)
- report_path: docs/reviews/260505_1200_canon_sweep_report_range_aaaaaaa_bbbbbbb.md
- no_op_reason: N/A (why=no no-op)
- packetization_handoff: N/A (why=source-only impact)
"""

BAD_CANON_SWEEP = """\
# Canon sweep receipt

**Status:** Done

## Canon sweep receipt
- changed_shared_canon_files_count: 0
- changed_shared_canon_files: none
- proof_kind: mystery
- target_repo_impact: none
- snapshot_path: N/A (why=no snapshot)
- report_path: N/A (why=no report)
- no_op_reason: no_shared_canon_delta
- packetization_handoff: N/A (why=no shared target impact)
"""

VALID_POST_MERGE_AUDIT = """\
# Post-merge audit

**Status:** Done

## Audit matrix
- all tracked items reconciled

## Role-quality
- Role assessment: no live blocker missed

## Post-merge audit receipt citations
- Follow-up harvest triage/import receipt: docs/reviews/harvest.md
- Process-improvement promotion decisions: docs/reviews/harvest.md
- Docs retrieval metrics receipt: docs/reviews/harvest.md
"""

BAD_POST_MERGE_AUDIT = """\
# Post-merge audit

**Status:** Done

## Audit matrix
- all tracked items reconciled

## Post-merge audit receipt citations
- Follow-up harvest triage/import receipt: docs/reviews/harvest.md
- Process-improvement promotion decisions: docs/reviews/harvest.md
- Docs retrieval metrics receipt: docs/reviews/harvest.md
"""

VALID_PACKETIZATION_GATE = """\
# Packetization gate

**Status:** Done

| path | coverage |
| --- | --- |
| docs/playbooks/example.md | covered |
"""

BAD_PACKETIZATION_GATE = """\
# Packetization gate

**Status:** Done

| path | coverage |
| --- | --- |
| docs/playbooks/example.md | missing-packet |
"""

VALID_DOCS_FINALIZE = """\
# Docs finalize general output

## 3) Process improvements
NO PROCESS IMPROVEMENTS — why: clean_run
"""

VALID_DOCS_FINALIZE_FOLLOWUPS = """\
NO FOLLOWUPS
"""

BAD_DOCS_FINALIZE = """\
# Docs finalize general output

## Process improvements
NO PROCESS IMPROVEMENTS — why: bogus
"""


class PostMergeReceiptPreflightTests(unittest.TestCase):
    def _write(self, root: Path, rel_path: str, body: str) -> str:
        write_text_fixture(root, rel_path, body)
        return rel_path

    def _run_direct(self, root: Path, step: str, rel_path: str, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                step,
                "--repo-root",
                str(root),
                "--path",
                rel_path,
                *extra,
            ],
            text=True,
            capture_output=True,
            check=False,
        )

    def _strict_docs_finalize_body(
        self,
        *,
        rel_path: str,
        base: str,
        head: str,
        status: str = "Done",
        role: str = "Architect",
        process_body: str = "NO PROCESS IMPROVEMENTS — why: clean_run",
    ) -> str:
        return (
            "# Docs finalize receipt\n\n"
            "**Date:** 29.08.2026 18:08 MSK\n"
            f"**Role:** {role}\n"
            f"**BASE:** {base}\n"
            f"**HEAD:** {head}\n"
            f"**Status:** {status}\n"
            "**Schema version:** review.v1\n\n"
            f"docs_finalize_receipt_path={rel_path}\n\n"
            "## Process improvements\n\n"
            f"{process_body}\n"
        )

    def _git(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            text=True,
            capture_output=True,
            check=False,
        )

    def _commit_fixture_git(self, root: Path) -> None:
        self.assertEqual(
            self._git(root, "config", "user.email", 'test' + '@' + 'example' + '.' + 'com').returncode,
            0,
        )
        self.assertEqual(
            self._git(root, "config", "user.name", "Test User").returncode,
            0,
        )
        self.assertEqual(self._git(root, "add", "--all").returncode, 0)
        self.assertEqual(
            self._git(
                root,
                "commit",
                "--quiet",
                "--allow-empty",
                "-m",
                "fixture",
            ).returncode,
            0,
        )

    def _write_shared_canon_range(self, root: Path) -> tuple[str, str]:
        self.assertEqual(self._git(root, "init").returncode, 0)
        self.assertEqual(self._git(root, "config", "user.email", 'test' + '@' + 'example' + '.' + 'com').returncode, 0)
        self.assertEqual(self._git(root, "config", "user.name", "Test User").returncode, 0)
        self._write(root, "README.md", "seed\n")
        self.assertEqual(self._git(root, "add", ".").returncode, 0)
        self.assertEqual(self._git(root, "commit", "-m", "seed").returncode, 0)
        base = self._git(root, "rev-parse", "HEAD").stdout.strip()
        self._write(root, "docs/playbooks/shared_packetization_context.md", "# Shared process change\n")
        self.assertEqual(self._git(root, "add", ".").returncode, 0)
        self.assertEqual(self._git(root, "commit", "-m", "shared process change").returncode, 0)
        head = self._git(root, "rev-parse", "HEAD").stdout.strip()
        self._write(root, ".planveyor.range.base", f"{base}\n")
        self._write(root, ".planveyor.range.head", f"{head}\n")
        return base, head

    def _run_wrapper(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        script = dedent(
            """\
            source "$1"
            cd "$2"
            shift 2
            planveyor_post_merge_receipt_preflight "$@"
            """
        )
        return run_zsh_fixture(
            script,
            cwd=Path.cwd(),
            path=os.environ.get("PATH", os.defpath),
            pybin=sys.executable,
            argv0="zsh",
            argv_tail=(str(REPO_ROOT / "scripts/planveyor.zsh"), str(root), *args),
            capture_output=True,
            check=False,
        )

    def _shared_post_merge_audit_body(self) -> str:
        return VALID_POST_MERGE_AUDIT + "\n## Packetization handoff\n- next step: step:packetization_gate\n"

    def _write_packetization_report(
        self,
        root: Path,
        rel_path: str,
        *,
        range_ref: str,
        status: str = "Done",
        payload: dict[str, object] | None = None,
        raw_json: str | None = None,
    ) -> str:
        if raw_json is None:
            gate_payload: dict[str, object] = {
                "schema_version": "packetization_gate.v1",
                "range": range_ref,
                "rows": [],
                "blocking_count": 0,
                "blocking_rows_count": 0,
            }
            if payload:
                gate_payload.update(payload)
            raw_json = json.dumps({"packetization_gate": gate_payload}, indent=2)
        body = (
            "# Packetization gate\n\n"
            f"**Status:** {status}\n\n"
            "## Machine-readable JSON\n```json\n"
            f"{raw_json}\n"
            "```\n"
        )
        return self._write(root, rel_path, body)

    def test_good_fixtures_pass_for_all_steps(self) -> None:
        cases = {
            "plan_harvest": ("docs/reviews/good_plan_harvest.md", VALID_PLAN_HARVEST),
            "canon_sweep": ("docs/reviews/good_canon_sweep.md", VALID_CANON_SWEEP),
            "post_merge_audit": ("docs/reviews/good_post_merge_audit.md", VALID_POST_MERGE_AUDIT),
            "packetization_gate": ("docs/reviews/good_packetization_gate.md", VALID_PACKETIZATION_GATE),
            "docs_finalize": ("docs/reviews/good_docs_finalize.md", VALID_DOCS_FINALIZE),
        }
        with temporary_git_root() as tmp:
            root = Path(tmp)
            for step, (rel_path, body) in cases.items():
                with self.subTest(step=step):
                    self._write(root, rel_path, body)
                    proc = self._run_direct(root, step, rel_path, "--format", "json")
                    self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
                    payload = json.loads(proc.stdout)
                    self.assertEqual(payload["status"], "ok")
                    self.assertEqual(payload["errors"], [])

    def test_current_plan_harvest_preflight_preserves_created_imported_literals(self) -> None:
        current = VALID_CURRENT_PLAN_HARVEST.replace(
            "- harvest_file_followups_result: `NO FOLLOWUPS` — no remaining actionable debt after full-wave harvest.\n"
            "- harvest_file_followups_count: 0\n",
            "- harvest_file_followups_result: `created/imported`\n"
            "- harvest_file_followups_count: 2\n",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rel_path = self._write(root, "docs/reviews/current_plan_harvest.md", current)
            result = self._run_direct(root, "plan_harvest", rel_path)

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_current_plan_harvest_preflight_rejects_missing_file_followups_literal(self) -> None:
        current = VALID_CURRENT_PLAN_HARVEST.replace(
            "- harvest_file_followups_count: 0\n",
            "",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rel_path = self._write(root, "docs/reviews/current_plan_harvest_missing_count.md", current)
            result = self._run_direct(root, "plan_harvest", rel_path, "--format", "json")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing_harvest_file_followups_count", result.stdout)
        self.assertIn("file_followups_literal_contract", result.stdout)

    def test_current_plan_harvest_preflight_rejects_incomplete_idempotency_counters(self) -> None:
        cases = (
            (
                VALID_CURRENT_PLAN_HARVEST.replace(
                    ", unparsed_bullets=0.",
                    ".",
                ),
                "missing_harvest_file_followups_idempotency_counter",
            ),
            (
                VALID_CURRENT_PLAN_HARVEST.replace(
                    "unparsed_bullets=0.",
                    "unparsed_bullets=0, unparsed_bullets=0.",
                ),
                "duplicate_harvest_file_followups_idempotency_counter",
            ),
            (
                VALID_CURRENT_PLAN_HARVEST.replace(
                    "unparsed_bullets=0.",
                    "unparsed_bullets=invalid.",
                ),
                "invalid_harvest_file_followups_idempotency_counter",
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index, (current, expected_code) in enumerate(cases, start=1):
                with self.subTest(expected_code=expected_code):
                    rel_path = self._write(root, f"docs/reviews/current_plan_harvest_idempotency_{index}.md", current)
                    result = self._run_direct(root, "plan_harvest", rel_path, "--format", "json")

                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(expected_code, result.stdout)
                    self.assertIn("unparsed_bullets", result.stdout)
                    self.assertIn("file_followups_literal_contract", result.stdout)

    def test_post_merge_audit_preflight_inherits_visual_authority_readback(self) -> None:
        with temporary_git_root() as tmp:
            root = Path(tmp)
            rel_path = self._write(root, "docs/reviews/good_post_merge_audit.md", VALID_POST_MERGE_AUDIT)
            finding = merge_bundle_report.post_merge_audit_lint.Finding(
                rel_path=rel_path,
                line_no=4,
                code="audit_status_done_conflicts_with_visual_evidence",
                message="runtime UI visual evidence is red",
            )
            with mock.patch.object(
                merge_bundle_report.post_merge_audit_lint,
                "_lint_current_audit_status_authority",
                return_value=[finding],
            ):
                blocked = MODULE.validate_post_merge_receipt_preflight(
                    root=root,
                    step="post_merge_audit",
                    path=rel_path,
                )
            with mock.patch.object(
                merge_bundle_report.post_merge_audit_lint,
                "_lint_current_audit_status_authority",
                return_value=[],
            ):
                green = MODULE.validate_post_merge_receipt_preflight(
                    root=root,
                    step="post_merge_audit",
                    path=rel_path,
                )

        self.assertEqual(blocked["status"], "blocked")
        self.assertIn("post_merge_audit_authority_blocked", {error["code"] for error in blocked["errors"]})
        self.assertEqual(green["status"], "ok")

    def test_canon_sweep_report_fixture_passes_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rel_path = self._write(root, "docs/reviews/good_canon_sweep_report.md", VALID_CANON_SWEEP_REPORT)
            proc = self._run_direct(root, "canon_sweep", rel_path, "--format", "json")

        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["errors"], [])

    def test_canon_sweep_preflight_rejects_invented_proof_kinds_with_allowed_values(self) -> None:
        for proof_kind in ("bounded_canon_sweep_report", "structural_skeleton"):
            with self.subTest(proof_kind=proof_kind):
                body = VALID_CANON_SWEEP_REPORT.replace("proof_kind: report", f"proof_kind: {proof_kind}")
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    rel_path = self._write(root, f"docs/reviews/bad_{proof_kind}.md", body)
                    proc = self._run_direct(root, "canon_sweep", rel_path, "--format", "json")

                self.assertEqual(proc.returncode, 1, proc.stderr + proc.stdout)
                payload = json.loads(proc.stdout)
                self.assertEqual(payload["status"], "blocked")
                details = "\n".join(error["detail"] for error in payload["errors"])
                self.assertIn(f"unsupported proof_kind={proof_kind}", details)
                self.assertIn("allowed values: no_op, report, snapshot", details)

    def test_malformed_fixtures_fail_with_exact_diagnostics(self) -> None:
        cases = {
            "plan_harvest": (
                "docs/reviews/bad_plan_harvest.md",
                BAD_PLAN_HARVEST,
                "missing_required_receipt",
                "step:plan_harvest/docs_retrieval_metrics",
            ),
            "canon_sweep": (
                "docs/reviews/bad_canon_sweep.md",
                BAD_CANON_SWEEP,
                "inconsistent_receipt",
                "unsupported proof_kind=mystery",
            ),
            "post_merge_audit": (
                "docs/reviews/bad_post_merge_audit.md",
                BAD_POST_MERGE_AUDIT,
                "missing_required_receipt",
                "step:post_merge_audit/role_quality_matrix",
            ),
            "packetization_gate": (
                "docs/reviews/bad_packetization_gate.md",
                BAD_PACKETIZATION_GATE,
                "blocking_packetization_rows",
                "step:packetization_gate/packetization_gate",
            ),
            "docs_finalize": (
                "docs/reviews/bad_docs_finalize.md",
                BAD_DOCS_FINALIZE,
                "malformed_process_improvements",
                "Unsupported no-op reason: 'bogus'",
            ),
        }
        with temporary_git_root() as tmp:
            root = Path(tmp)
            for step, (rel_path, body, code, detail) in cases.items():
                with self.subTest(step=step):
                    self._write(root, rel_path, body)
                    proc = self._run_direct(root, step, rel_path, "--format", "json")
                    self.assertEqual(proc.returncode, 1, proc.stderr + proc.stdout)
                    payload = json.loads(proc.stdout)
                    self.assertEqual(payload["status"], "blocked")
                    self.assertEqual(payload["errors"][0]["code"], code)
                    self.assertIn(detail, payload["errors"][0]["detail"])
                    self.assertIn("next_action", payload["errors"][0])

    def test_docs_finalize_followups_lane_no_followups_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rel_path = self._write(root, "docs/reviews/docs_finalize_followups.md", VALID_DOCS_FINALIZE_FOLLOWUPS)
            proc = self._run_direct(root, "docs_finalize", rel_path, "--format", "json")
            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
            self.assertEqual(json.loads(proc.stdout)["status"], "ok")

    def test_docs_finalize_merge_receipt_requires_exact_architect_range_carrier(self) -> None:
        base = "a" * 40
        head = "b" * 40
        range_ref = f"{base}..{head}"
        valid_path = "docs/reviews/260829_1808_docs_finalize_receipt_range_aaaaaaa_bbbbbbb.md"
        structured = "\n".join(
            (
                "### Suggestion 1",
                "- symptom: Повторная ручная сверка пути receipt.",
                "- process_gap: Нет локального path readback gate.",
                "- suggested_fix: Проверять exact readback до tracker tick.",
                "- owner: Architect",
                "- promotion_class: helper_change",
                "- trigger_ref: unknown",
                "- source_ref: docs/reviews/260829_1809_docs_finalize_receipt_range_aaaaaaa_bbbbbbb.md",
            )
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(
                root,
                valid_path,
                self._strict_docs_finalize_body(rel_path=valid_path, base=base, head=head),
            )
            no_op = self._run_direct(
                root,
                "docs_finalize",
                valid_path,
                "--role",
                "Architect",
                "--range",
                range_ref,
                "--format",
                "json",
            )
            self.assertEqual(no_op.returncode, 0, no_op.stderr + no_op.stdout)
            self.assertEqual(json.loads(no_op.stdout)["status"], "ok")

            structured_path = "docs/reviews/260829_1809_docs_finalize_receipt_range_aaaaaaa_bbbbbbb.md"
            self._write(
                root,
                structured_path,
                self._strict_docs_finalize_body(
                    rel_path=structured_path,
                    base=base,
                    head=head,
                    process_body=structured,
                ),
            )
            structured_result = self._run_direct(
                root,
                "docs_finalize",
                structured_path,
                "--role",
                "Architect",
                "--range",
                range_ref,
                "--format",
                "json",
            )
            self.assertEqual(structured_result.returncode, 0, structured_result.stderr + structured_result.stdout)

            cases = {
                "wrong_role": (
                    valid_path,
                    self._strict_docs_finalize_body(rel_path=valid_path, base=base, head=head),
                    ("--role", "Coder"),
                    "docs_finalize_role_mismatch",
                ),
                "wrong_path_range": (
                    "docs/reviews/260829_1810_docs_finalize_receipt_range_ccccccc_ddddddd.md",
                    self._strict_docs_finalize_body(
                        rel_path="docs/reviews/260829_1810_docs_finalize_receipt_range_ccccccc_ddddddd.md",
                        base=base,
                        head=head,
                    ),
                    ("--role", "Architect"),
                    "docs_finalize_receipt_range_mismatch",
                ),
                "mismatched_readback": (
                    "docs/reviews/260829_1814_docs_finalize_receipt_range_aaaaaaa_bbbbbbb.md",
                    self._strict_docs_finalize_body(
                        rel_path="docs/reviews/260829_1815_docs_finalize_receipt_range_aaaaaaa_bbbbbbb.md",
                        base=base,
                        head=head,
                    ),
                    ("--role", "Architect"),
                    "docs_finalize_receipt_readback_mismatch",
                ),
                "no_followups": (
                    "docs/reviews/260829_1811_docs_finalize_receipt_range_aaaaaaa_bbbbbbb.md",
                    self._strict_docs_finalize_body(
                        rel_path="docs/reviews/260829_1811_docs_finalize_receipt_range_aaaaaaa_bbbbbbb.md",
                        base=base,
                        head=head,
                        process_body="NO FOLLOWUPS",
                    ),
                    ("--role", "Architect"),
                    "disallowed_docs_finalize_carrier",
                ),
                "progress_only": (
                    "docs/reviews/260829_1812_docs_finalize_receipt_range_aaaaaaa_bbbbbbb.md",
                    self._strict_docs_finalize_body(
                        rel_path="docs/reviews/260829_1812_docs_finalize_receipt_range_aaaaaaa_bbbbbbb.md",
                        base=base,
                        head=head,
                        process_body="NO PROGRESS UPDATES",
                    ),
                    ("--role", "Architect"),
                    "disallowed_docs_finalize_carrier",
                ),
                "skeleton": (
                    "docs/reviews/260829_1813_docs_finalize_receipt_range_aaaaaaa_bbbbbbb.md",
                    self._strict_docs_finalize_body(
                        rel_path="docs/reviews/260829_1813_docs_finalize_receipt_range_aaaaaaa_bbbbbbb.md",
                        base="<BASE>",
                        head="<HEAD>",
                        status="Draft",
                    ),
                    ("--role", "Architect"),
                    "non_final_artifact_status",
                ),
                "malformed_process": (
                    "docs/reviews/260829_1816_docs_finalize_receipt_range_aaaaaaa_bbbbbbb.md",
                    self._strict_docs_finalize_body(
                        rel_path="docs/reviews/260829_1816_docs_finalize_receipt_range_aaaaaaa_bbbbbbb.md",
                        base=base,
                        head=head,
                        process_body="NO PROCESS IMPROVEMENTS — why: bogus",
                    ),
                    ("--role", "Architect"),
                    "malformed_process_improvements",
                ),
            }
            for name, (rel_path, body, extra, expected_code) in cases.items():
                with self.subTest(name=name):
                    self._write(root, rel_path, body)
                    result = self._run_direct(
                        root,
                        "docs_finalize",
                        rel_path,
                        *extra,
                        "--range",
                        range_ref,
                        "--format",
                        "json",
                    )
                    self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
                    self.assertIn(expected_code, {error["code"] for error in json.loads(result.stdout)["errors"]})

            absolute = self._run_direct(
                root,
                "docs_finalize",
                str(root / valid_path),
                "--role",
                "Architect",
                "--range",
                range_ref,
                "--format",
                "json",
            )
            self.assertEqual(absolute.returncode, 1, absolute.stderr + absolute.stdout)
            self.assertIn("absolute_docs_finalize_receipt_path", absolute.stdout)

            missing = self._run_direct(
                root,
                "docs_finalize",
                "docs/reviews/260829_1817_docs_finalize_receipt_range_aaaaaaa_bbbbbbb.md",
                "--role",
                "Architect",
                "--range",
                range_ref,
                "--format",
                "json",
            )
            self.assertEqual(missing.returncode, 1, missing.stderr + missing.stdout)
            self.assertIn("missing_path", missing.stdout)

    def test_docs_finalize_merge_receipt_rejects_noncanonical_top_level_literals(self) -> None:
        base = "a" * 40
        head = "b" * 40
        range_ref = f"{base}..{head}"
        receipt_path = "docs/reviews/260829_1818_docs_finalize_receipt_range_aaaaaaa_bbbbbbb.md"
        canonical = self._strict_docs_finalize_body(
            rel_path=receipt_path,
            base=base,
            head=head,
        )
        cases = {
            "indented_role": (
                canonical.replace("**Role:** Architect", "  **Role:** Architect"),
                "docs_finalize_receipt_role_mismatch",
            ),
            "backticked_schema": (
                canonical.replace("**Schema version:** review.v1", "**Schema version:** `review.v1`"),
                "docs_finalize_receipt_schema_mismatch",
            ),
            "indented_status": (
                canonical.replace("**Status:** Done", "  **Status:** Done"),
                "non_final_artifact_status",
            ),
            "indented_readback": (
                canonical.replace(
                    f"docs_finalize_receipt_path={receipt_path}",
                    f"  docs_finalize_receipt_path={receipt_path}",
                ),
                "docs_finalize_receipt_readback_mismatch",
            ),
            "noncanonical_heading": (
                canonical.replace("## Process improvements", "### Process improvements"),
                "docs_finalize_process_improvements_heading_mismatch",
            ),
            "duplicate_role": (
                canonical.replace(
                    "**Role:** Architect",
                    "**Role:** Architect\n**Role:** Architect",
                ),
                "docs_finalize_receipt_role_mismatch",
            ),
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, (body, expected_code) in cases.items():
                with self.subTest(name=name):
                    self._write(root, receipt_path, body)
                    result = self._run_direct(
                        root,
                        "docs_finalize",
                        receipt_path,
                        "--role",
                        "Architect",
                        "--range",
                        range_ref,
                        "--format",
                        "json",
                    )
                    self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
                    self.assertIn(expected_code, {error["code"] for error in json.loads(result.stdout)["errors"]})

    def test_structural_packetization_report_requires_schema_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bad_path = self._write(
                root,
                "docs/reviews/bad_packetization_gate.md",
                "# Packetization gate\n\n**Status:** Done\n\n## Machine-readable JSON\n```json\n"
                + json.dumps({"packetization_gate": {"blocking_count": 0, "rows": []}}, indent=2)
                + "\n```\n",
            )
            good_path = self._write(
                root,
                "docs/reviews/good_packetization_gate.md",
                "# Packetization gate\n\n**Status:** Done\n\n## Machine-readable JSON\n```json\n"
                + json.dumps(
                    {
                        "packetization_gate": {
                            "schema_version": "packetization_gate.v1",
                            "blocking_count": 0,
                            "rows": [],
                        }
                    },
                    indent=2,
                )
                + "\n```\n",
            )

            bad = self._run_direct(root, "packetization_gate", bad_path, "--format", "json")
            good = self._run_direct(root, "packetization_gate", good_path, "--format", "json")

        self.assertEqual(bad.returncode, 1, bad.stdout)
        bad_payload = json.loads(bad.stdout)
        self.assertIn("missing_packetization_schema_version", {error["code"] for error in bad_payload["errors"]})
        self.assertEqual(good.returncode, 0, good.stdout)

    def test_structural_packetization_report_malformed_json_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rel_path = self._write(
                root,
                "docs/reviews/bad_packetization_gate.md",
                "# Packetization gate\n\n**Status:** Done\n\n## Machine-readable JSON\n```json\n"
                '{"packetization_gate": \n'
                "```\n",
            )
            proc = self._run_direct(root, "packetization_gate", rel_path, "--format", "json")

        self.assertEqual(proc.returncode, 1, proc.stdout)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["status"], "blocked")
        self.assertIn("malformed_packetization_json", {error["code"] for error in payload["errors"]})

    def test_structural_packetization_report_non_object_payload_fails_closed(self) -> None:
        cases = {
            "top_level_list": ["not", "an", "object"],
            "nested_gate_list": {"packetization_gate": []},
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, body in cases.items():
                with self.subTest(name=name):
                    rel_path = self._write(
                        root,
                        f"docs/reviews/bad_packetization_gate_{name}.md",
                        "# Packetization gate\n\n**Status:** Done\n\n## Machine-readable JSON\n```json\n"
                        + json.dumps(body)
                        + "\n```\n",
                    )
                    proc = self._run_direct(root, "packetization_gate", rel_path, "--format", "json")
                    self.assertEqual(proc.returncode, 1, proc.stdout)
                    payload = json.loads(proc.stdout)
                    self.assertEqual(payload["status"], "blocked")
                    self.assertIn("malformed_packetization_json", {error["code"] for error in payload["errors"]})

    def test_documented_default_path_derives_packetization_requirement_from_saved_range(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_shared_canon_range(root)
            rel_path = self._write(root, "docs/reviews/shared_plan_harvest.md", VALID_PLAN_HARVEST)
            proc = self._run_wrapper(root, "plan_harvest", "--path", rel_path, "--format", "json")
            self.assertEqual(proc.returncode, 1, proc.stderr + proc.stdout)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["status"], "blocked")
            self.assertTrue(payload["packetization_required"])
            self.assertEqual(payload["packetization_state"], "required_validation_blocked")
            self.assertTrue(
                any(
                    error["code"] == "missing_required_receipt"
                    and "step:plan_harvest/packetization_gate" in error["detail"]
                    for error in payload["errors"]
                ),
                payload["errors"],
            )

    def test_plan_harvest_shared_range_allows_packetization_handoff_before_report_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_shared_canon_range(root)
            body = (
                VALID_PLAN_HARVEST
                + "\n## Packetization handoff\n"
                + "- next step: step:packetization_gate\n"
                + "- expected report: docs/reviews/<stamp>_packetization_gate_range_<base7>_<head7>.md\n"
            )
            rel_path = self._write(root, "docs/reviews/shared_plan_harvest.md", body)
            proc = self._run_wrapper(root, "plan_harvest", "--path", rel_path, "--format", "json")
            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["status"], "ok")
            self.assertTrue(payload["packetization_required"])
            self.assertEqual(payload["packetization_reports"], [])
            self.assertEqual(payload["proof_scope"], "step_local_receipt")
            self.assertEqual(payload["terminal_readiness"], "not_evaluated")
            self.assertEqual(payload["packetization_state"], "handoff_recorded_future_step_pending")

            plain = self._run_wrapper(root, "plan_harvest", "--path", rel_path)
            self.assertEqual(plain.returncode, 0, plain.stderr + plain.stdout)
            self.assertIn("proof_scope=step_local_receipt", plain.stdout)
            self.assertIn("terminal_readiness=not_evaluated", plain.stdout)
            self.assertIn("packetization_state=handoff_recorded_future_step_pending", plain.stdout)
            self.assertIn("next_packetization_gate=step:packetization_gate", plain.stdout)

    def test_shared_range_requires_canon_sweep_packetization_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_shared_canon_range(root)
            rel_path = self._write(root, "docs/reviews/shared_canon_sweep.md", VALID_CANON_SWEEP)
            proc = self._run_wrapper(root, "canon_sweep", "--path", rel_path, "--format", "json")
            self.assertEqual(proc.returncode, 1, proc.stderr + proc.stdout)
            payload = json.loads(proc.stdout)
            self.assertTrue(payload["packetization_required"])
            self.assertEqual(payload["packetization_state"], "required_validation_blocked")
            details = "\n".join(error["detail"] for error in payload["errors"])
            self.assertIn("step:canon_sweep/canon_sweep_execution", details)
            self.assertIn("packetization_handoff with step:packetization_gate", details)

    def test_canon_sweep_shared_range_allows_packetization_handoff_before_report_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_shared_canon_range(root)
            body = (
                VALID_CANON_SWEEP_REPORT
                .replace("target_repo_impact: source_only", "target_repo_impact: shared_consumer")
                .replace("packetization_handoff: N/A (why=source-only impact)", "packetization_handoff: step:packetization_gate")
            )
            rel_path = self._write(root, "docs/reviews/shared_canon_sweep.md", body)
            proc = self._run_wrapper(root, "canon_sweep", "--path", rel_path, "--format", "json")
            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["status"], "ok")
            self.assertTrue(payload["packetization_required"])
            self.assertEqual(payload["packetization_reports"], [])
            self.assertEqual(payload["proof_scope"], "step_local_receipt")
            self.assertEqual(payload["terminal_readiness"], "not_evaluated")
            self.assertEqual(payload["packetization_state"], "handoff_recorded_future_step_pending")

    def test_post_merge_audit_shared_range_requires_active_structural_packetization_report(self) -> None:
        cases = {
            "missing": "inconsistent_receipt",
            "wrong_range": "inconsistent_receipt",
            "superseded_only": "superseded_packetization_report",
            "ambiguous": "ambiguous_artifact",
            "non_final": "non_final_artifact_status",
            "legacy": "missing_packetization_schema_version",
            "missing_schema": "missing_packetization_schema_version",
            "malformed": "malformed_packetization_json",
            "unsupported": "unsupported_packetization_schema_version",
            "missing_packet": "blocking_packetization_rows",
            "unknown_target_mapping": "blocking_packetization_rows",
            "green": "",
        }
        for name, expected_code in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                base, head = self._write_shared_canon_range(root)
                range_ref = f"{base}..{head}"
                audit_path = self._write(
                    root,
                    "docs/reviews/shared_post_merge_audit.md",
                    self._shared_post_merge_audit_body(),
                )
                report_path = (
                    "docs/reviews/260806_0001_packetization_gate_range_"
                    f"{base[:7]}_{head[:7]}.md"
                )
                extra: tuple[str, ...] = ()

                if name == "wrong_range":
                    wrong_path = "docs/reviews/260806_0001_packetization_gate_range_deadbee_feedbee.md"
                    self._write_packetization_report(
                        root,
                        wrong_path,
                        range_ref="deadbeef..feedbeef",
                    )
                    extra = ("--packetization-report", wrong_path)
                elif name == "superseded_only":
                    self._write_packetization_report(root, report_path, range_ref=range_ref, status="Superseded")
                elif name == "ambiguous":
                    self._write_packetization_report(root, report_path, range_ref=range_ref)
                    self._write_packetization_report(
                        root,
                        report_path.replace("260806_0001", "260806_0002"),
                        range_ref=range_ref,
                    )
                elif name == "non_final":
                    self._write_packetization_report(root, report_path, range_ref=range_ref, status="In progress")
                elif name == "legacy":
                    self._write(root, report_path, VALID_PACKETIZATION_GATE)
                elif name == "missing_schema":
                    self._write_packetization_report(
                        root,
                        report_path,
                        range_ref=range_ref,
                        payload={"schema_version": ""},
                    )
                elif name == "malformed":
                    self._write_packetization_report(
                        root,
                        report_path,
                        range_ref=range_ref,
                        raw_json='{"packetization_gate": ',
                    )
                elif name == "unsupported":
                    self._write_packetization_report(
                        root,
                        report_path,
                        range_ref=range_ref,
                        payload={"schema_version": "packetization_gate.v999"},
                    )
                elif name == "missing_packet":
                    self._write_packetization_report(
                        root,
                        report_path,
                        range_ref=range_ref,
                        payload={"rows": [{"coverage": "missing-packet"}]},
                    )
                elif name == "unknown_target_mapping":
                    self._write_packetization_report(
                        root,
                        report_path,
                        range_ref=range_ref,
                        payload={"rows": [{"coverage": "unknown_target_mapping"}]},
                    )
                elif name == "green":
                    self._write_packetization_report(root, report_path, range_ref=range_ref)

                proc = self._run_wrapper(
                    root,
                    "post_merge_audit",
                    "--path",
                    audit_path,
                    "--format",
                    "json",
                    *extra,
                )
                payload = json.loads(proc.stdout)
                if expected_code:
                    self.assertEqual(proc.returncode, 1, proc.stderr + proc.stdout)
                    self.assertEqual(payload["status"], "blocked")
                    self.assertEqual(payload["packetization_state"], "required_validation_blocked")
                    self.assertIn(expected_code, {error["code"] for error in payload["errors"]})
                else:
                    self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
                    self.assertEqual(payload["status"], "ok")
                    self.assertEqual(payload["proof_scope"], "step_local_receipt")
                    self.assertEqual(payload["terminal_readiness"], "not_evaluated")
                    self.assertEqual(payload["packetization_state"], "active_report_validated")

                    plain = self._run_wrapper(root, "post_merge_audit", "--path", audit_path)
                    self.assertEqual(plain.returncode, 0, plain.stderr + plain.stdout)
                    self.assertIn("packetization_state=active_report_validated", plain.stdout)

    def test_post_merge_audit_forced_packetization_without_resolved_range_fails_closed(self) -> None:
        with temporary_git_root() as tmp:
            root = Path(tmp)
            audit_path = self._write(
                root,
                "docs/reviews/shared_post_merge_audit.md",
                self._shared_post_merge_audit_body(),
            )
            payload = MODULE.validate_post_merge_receipt_preflight(
                root=root,
                step="post_merge_audit",
                path=audit_path,
                packetization_required=True,
            )

        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["packetization_state"], "required_validation_blocked")
        self.assertIn("inconsistent_receipt", {error["code"] for error in payload["errors"]})

    def test_post_merge_audit_invalid_implicit_saved_range_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(self._git(root, "init").returncode, 0)
            self._write(root, ".planveyor.range.base", "deadbeef\n")
            self._write(root, ".planveyor.range.head", "feedbeef\n")
            audit_path = self._write(
                root,
                "docs/reviews/shared_post_merge_audit.md",
                self._shared_post_merge_audit_body(),
            )
            self._commit_fixture_git(root)

            json_proc = self._run_wrapper(root, "post_merge_audit", "--path", audit_path, "--format", "json")
            plain_proc = self._run_wrapper(root, "post_merge_audit", "--path", audit_path)

        self.assertEqual(json_proc.returncode, 1, json_proc.stderr + json_proc.stdout)
        payload = json.loads(json_proc.stdout)
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["packetization_state"], "not_evaluated")
        self.assertIn(
            "range_packetization_context_unavailable",
            {error["code"] for error in payload["errors"]},
        )
        self.assertEqual(plain_proc.returncode, 1, plain_proc.stderr + plain_proc.stdout)
        self.assertIn("range_packetization_context_unavailable", plain_proc.stdout)
        self.assertIn("packetization_state=not_evaluated", plain_proc.stdout)
        self.assertNotIn("packetization_state=not_required", plain_proc.stdout)

    def test_post_merge_audit_dangling_implicit_saved_range_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(self._git(root, "init").returncode, 0)
            (root / ".planveyor.range.base").symlink_to("missing-range-base")
            audit_path = self._write(
                root,
                "docs/reviews/shared_post_merge_audit.md",
                self._shared_post_merge_audit_body(),
            )
            self._commit_fixture_git(root)

            json_proc = self._run_wrapper(root, "post_merge_audit", "--path", audit_path, "--format", "json")
            plain_proc = self._run_wrapper(root, "post_merge_audit", "--path", audit_path)

        self.assertEqual(json_proc.returncode, 1, json_proc.stderr + json_proc.stdout)
        payload = json.loads(json_proc.stdout)
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["packetization_state"], "not_evaluated")
        self.assertIn(
            "range_packetization_context_unavailable",
            {error["code"] for error in payload["errors"]},
        )
        self.assertEqual(plain_proc.returncode, 1, plain_proc.stderr + plain_proc.stdout)
        self.assertIn("range_packetization_context_unavailable", plain_proc.stdout)
        self.assertIn("packetization_state=not_evaluated", plain_proc.stdout)

    def test_post_merge_audit_authority_refusal_fails_closed_as_json(self) -> None:
        # --repo-root names a subdirectory of a real Git top-level, so the
        # contract authority guard refuses it; the CLI must answer with the
        # blocked JSON payload instead of a traceback.
        with temporary_git_root() as tmp:
            outer = Path(tmp)
            nested_root = outer / "sub"
            audit_path = self._write(nested_root, "docs/reviews/good_post_merge_audit.md", VALID_POST_MERGE_AUDIT)
            proc = self._run_direct(nested_root, "post_merge_audit", audit_path, "--format", "json")

        self.assertEqual(proc.returncode, 1, proc.stderr + proc.stdout)
        self.assertNotIn("Traceback", proc.stderr, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["errors"][0]["code"], "contract_authority_preflight_failed")
        self.assertEqual(payload["errors"][0]["detail"], "git_root_mismatch")
        for absolute_path in {outer, outer.resolve(), REPO_ROOT, REPO_ROOT.resolve()}:
            self.assertNotIn(str(absolute_path), proc.stdout)

    def test_required_packetization_gate_readback_is_coherent_in_json_and_plain(self) -> None:
        cases = {
            "green": ("packetization_gate_validated", 0, None),
            "blocking": ("required_validation_blocked", 1, {"rows": [{"coverage": "missing-packet"}]}),
        }
        for name, (expected_state, expected_returncode, payload) in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                base, head = self._write_shared_canon_range(root)
                report_path = (
                    "docs/reviews/260806_0001_packetization_gate_range_"
                    f"{base[:7]}_{head[:7]}.md"
                )
                self._write_packetization_report(
                    root,
                    report_path,
                    range_ref=f"{base}..{head}",
                    payload=payload,
                )

                json_proc = self._run_wrapper(root, "packetization_gate", "--path", report_path, "--format", "json")
                plain_proc = self._run_wrapper(root, "packetization_gate", "--path", report_path)

                self.assertEqual(json_proc.returncode, expected_returncode, json_proc.stderr + json_proc.stdout)
                result = json.loads(json_proc.stdout)
                self.assertTrue(result["packetization_required"])
                self.assertEqual(result["packetization_state"], expected_state)
                self.assertEqual(plain_proc.returncode, expected_returncode, plain_proc.stderr + plain_proc.stdout)
                self.assertIn(f"packetization_state={expected_state}", plain_proc.stdout)

    def test_plain_output_and_missing_path_exit_codes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rel_path = self._write(root, "docs/reviews/good_plan_harvest.md", VALID_PLAN_HARVEST)
            ok_proc = self._run_direct(root, "plan_harvest", rel_path)
            self.assertEqual(ok_proc.returncode, 0, ok_proc.stderr + ok_proc.stdout)
            self.assertIn("post_merge_receipt_preflight: ok", ok_proc.stdout)

            fail_proc = self._run_direct(root, "plan_harvest", "docs/reviews/missing.md")
            self.assertEqual(fail_proc.returncode, 1)
            self.assertIn("missing_path", fail_proc.stdout)

    def test_direct_help_lists_supported_steps(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(MODULE_PATH), "--help"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertIn("plan_harvest", proc.stdout)
        self.assertIn("docs_finalize", proc.stdout)

    def test_wrapper_help_and_json_explicit_path_match_direct_python(self) -> None:
        with temporary_git_root() as tmp:
            root = Path(tmp)
            help_proc = self._run_wrapper(root, "--help")
            self.assertEqual(help_proc.returncode, 0, help_proc.stderr + help_proc.stdout)
            self.assertIn("packetization_gate", help_proc.stdout)

            rel_path = self._write(root, "docs/reviews/good_plan_harvest.md", VALID_PLAN_HARVEST)
            direct = self._run_direct(root, "plan_harvest", rel_path, "--format", "json")
            wrapped = self._run_wrapper(root, "plan_harvest", "--path", rel_path, "--format", "json")
            self.assertEqual(direct.returncode, 0, direct.stderr + direct.stdout)
            self.assertEqual(wrapped.returncode, 0, wrapped.stderr + wrapped.stdout)
            self.assertEqual(json.loads(wrapped.stdout), json.loads(direct.stdout))


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import stat
import sys
import tempfile
import time
import unittest
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parent.parent
HELPER = REPO_ROOT / "scripts" / "role_outcome_receipt.py"
PLAN_REL = "docs/plans/260101_0000_outcome.md"
REVIEW_REL = "docs/code_reviews/260101_0000_outcome.md"
RUN_ID = "20260101T000000Z_coder_123_456"
EVIDENCE_HEADING = "## Evidence (chronological, append-only)"

SPEC = importlib.util.spec_from_file_location("role_outcome_receipt", HELPER)
assert SPEC and SPEC.loader
ROLE_OUTCOME = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ROLE_OUTCOME
SPEC.loader.exec_module(ROLE_OUTCOME)


def semantic_draft(*, invalid: str = "") -> str:
    rows = [ROLE_OUTCOME.DRAFT_MARKER]
    if invalid == "envelope":
        rows.append("  - role: reviewer")
    fields = list(ROLE_OUTCOME.SEMANTIC_FIELDS)
    if invalid == "order":
        fields[0], fields[1] = fields[1], fields[0]
    for field in fields:
        rows.append(f"  - {field}:")
        rows.append(f"    - scripts/role_outcome_receipt.py::{field}")
    if invalid == "additional":
        rows.extend(("  - summary:", "    - docs/plans/README.md"))
    if invalid == "json":
        rows[-1] = "    - {\"state\": \"green\"}"
    return "\n".join(rows)


def finalized_receipt(role: str, run_id: str, artifact_ref: str) -> str:
    rows = [ROLE_OUTCOME.RECEIPT_MARKER]
    values = {
        "role": role,
        "lane": role,
        "run_id": run_id,
        "target_plan": PLAN_REL,
        "artifact_ref": artifact_ref,
        "written_at": "2026-01-01T00:00:00Z",
    }
    rows.extend(f"  - {field}: {values[field]}" for field in ROLE_OUTCOME.ENVELOPE_FIELDS)
    for field in ROLE_OUTCOME.SEMANTIC_FIELDS:
        rows.extend((f"  - {field}:", f"    - scripts/role_outcome_receipt.py::{field}"))
    return "\n".join(rows)


class RoleOutcomeFixture:
    def __init__(self, base: str, *, mode: str = "manager-custom-pipeline") -> None:
        self.root = Path(base) / "repo"
        self.plan = self.root / PLAN_REL
        self.review = self.root / REVIEW_REL
        self.receipts = self.root / ".planveyor.role_runs"
        self.output = self.root / ".tmp" / "planveyor_role_runs" / RUN_ID
        for directory in (
            self.plan.parent,
            self.review.parent,
            self.receipts,
            self.output,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        self.write_plan(mode=mode)
        self.review.write_text("# Review\n\n## Evidence\n", encoding="utf-8")

    def write_plan(
        self,
        *,
        mode: str,
        evidence: str = "",
        plan_type: str = "dev",
        review_artifacts: str = f"- Code review (primary): `{REVIEW_REL}`",
    ) -> None:
        self.plan.write_text(
            "\n".join(
                (
                    "# Plan",
                    "",
                    f"**Plan type:** {plan_type}",
                    "**Status:** In progress",
                    "",
                    "## Verification rerun / exec handoff",
                    f"- Mode: {mode}",
                    "",
                    EVIDENCE_HEADING,
                    evidence,
                    "",
                    "## Review artifacts",
                    review_artifacts,
                    "",
                )
            ),
            encoding="utf-8",
        )

    def execution_receipt(
        self,
        role: str,
        *,
        state: str = "success",
        exit_code: int = 0,
        process_start_outcome: str = "started",
        non_green_reason: str = "",
        target_plan: str = PLAN_REL,
        run_id: str = RUN_ID,
        runner_id: str = "codex",
    ) -> Path:
        path = self.receipts / f"{run_id}.json"
        payload = {
            "schema_version": ROLE_OUTCOME.EXECUTION_SCHEMA,
            "run_id": run_id,
            "role": role,
            "target_plan": target_plan,
            "state": state,
            "exit_code": exit_code,
            "process_start_outcome": process_start_outcome,
            "non_green_reason": non_green_reason,
            "receipt_path": str(path),
            "runner_id": runner_id,
        }
        path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        return path

    def command(
        self,
        operation: str,
        role: str,
        *extra: str,
        run_id: str = RUN_ID,
    ) -> list[str]:
        command = [
            sys.executable,
            "-B",
            str(HELPER),
            operation,
            "--project-root",
            str(self.root),
            "--plan",
            PLAN_REL,
            "--role",
            role,
        ]
        if operation != "lint-draft":
            output = self.root / ".tmp" / "planveyor_role_runs" / run_id
            output.mkdir(parents=True, exist_ok=True)
            command.extend(("--run-id", run_id, "--output-dir", str(output)))
        command.extend(extra)
        command.extend(("--format", "json"))
        return command

    def run(
        self,
        operation: str,
        role: str,
        *extra: str,
        run_id: str = RUN_ID,
    ) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
        result = subprocess.run(
            self.command(operation, role, *extra, run_id=run_id),
            cwd=self.root,
            text=True,
            capture_output=True,
            check=False,
        )
        return result, json.loads(result.stdout)

    def lint(self, role: str) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
        return self.run("lint-draft", role)

    def preflight(self, role: str) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
        result, payload = self.run("preflight", role)
        self.output.joinpath("role_outcome_preflight.json").write_text(
            json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8"
        )
        return result, payload

    def finalize(self, role: str, receipt: Path) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
        return self.run(
            "finalize",
            role,
            "--execution-receipt",
            str(receipt),
            "--preflight-result",
            str(self.output / "role_outcome_preflight.json"),
        )

    def readback(self, role: str, receipt: Path) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
        return self.run("readback", role, "--execution-receipt", str(receipt))


class RoleOutcomeReceiptTests(unittest.TestCase):
    def test_lint_draft_exact_schema_incidents_and_read_only_contract(self) -> None:
        lint_fields = {
            "schema_version",
            "state",
            "reason_code",
            "role",
            "lane",
            "target_plan",
            "carrier_path",
            "artifact_ref",
            "semantic_draft_count",
            "semantic_draft_sha256",
            "diagnostics",
            "safe_action",
        }
        cases = {
            "punctuation": (
                "N/A (why=no blocker).",
                {
                    "rule_code": "na_trailing_punctuation",
                    "field": "worked",
                    "bullet_index": 1,
                },
            ),
            "519_chars": (
                "я" * 519,
                {
                    "rule_code": "bullet_too_long",
                    "field": "worked",
                    "bullet_index": 1,
                    "actual_chars": 519,
                    "max_allowed": 500,
                },
            ),
        }
        for case, (worked, expected) in cases.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmpdir:
                fixture = RoleOutcomeFixture(tmpdir)
                rows = semantic_draft().splitlines()
                rows[2] = f"    - {worked}"
                fixture.write_plan(
                    mode="manager-custom-pipeline",
                    evidence="\n".join(rows),
                )
                before = fixture.plan.read_bytes()

                first, payload = fixture.lint("coder")
                second, repeated = fixture.lint("coder")

                self.assertEqual(first.returncode, 125, first.stderr)
                self.assertEqual(second.returncode, 125, second.stderr)
                self.assertEqual(payload, repeated)
                self.assertEqual(set(payload), lint_fields)
                self.assertEqual(payload["schema_version"], ROLE_OUTCOME.LINT_SCHEMA)
                self.assertEqual(payload["state"], "invalid")
                self.assertEqual(payload["reason_code"], "semantic_draft_invalid")
                self.assertEqual(payload["safe_action"], "fix_current_draft")
                self.assertEqual(payload["diagnostics"], [expected])
                self.assertRegex(str(payload["semantic_draft_sha256"]), r"^[0-9a-f]{64}$")
                self.assertNotIn("run_id", payload)
                self.assertNotIn("written_at", payload)
                self.assertEqual(fixture.plan.read_bytes(), before)
                self.assertEqual(list(fixture.output.iterdir()), [])

        with tempfile.TemporaryDirectory() as tmpdir:
            fixture = RoleOutcomeFixture(tmpdir)
            fixture.write_plan(
                mode="manager-custom-pipeline",
                evidence=semantic_draft(),
            )
            result, payload = fixture.lint("coder")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(payload["state"], "valid")
            self.assertEqual(payload["reason_code"], "ok")
            self.assertEqual(payload["diagnostics"], [])
            self.assertEqual(payload["safe_action"], "continue_current_invocation")
            forbidden_identity = subprocess.run(
                fixture.command("lint-draft", "coder", "--run-id", RUN_ID),
                cwd=fixture.root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(forbidden_identity.returncode, 2)
            self.assertIn("unrecognized arguments: --run-id", forbidden_identity.stderr)

    def test_lint_draft_overlap_diagnostics_have_complete_stable_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            fixture = RoleOutcomeFixture(tmpdir)
            long_json = '{"value":"' + ("я" * 510) + '"}'
            rows = [
                ROLE_OUTCOME.DRAFT_MARKER,
                "  - blocked_by:",
                "  - worked:",
                "    - N/A (why=none).",
                "    - ```json",
                f"    - {long_json}",
            ]
            for field in ROLE_OUTCOME.SEMANTIC_FIELDS[2:]:
                rows.extend((f"  - {field}:", f"    - ok::{field}"))
            rows.extend(("  - summary:", "    - extra"))
            fixture.write_plan(
                mode="manager-custom-pipeline",
                evidence="\n".join(rows),
            )

            result, payload = fixture.lint("coder")

            self.assertEqual(result.returncode, 125, result.stderr)
            self.assertEqual(
                payload["diagnostics"],
                [
                    {
                        "rule_code": "field_order_invalid",
                        "field": "worked",
                        "observed_label": "blocked_by",
                    },
                    {
                        "rule_code": "bullet_count_out_of_range",
                        "field": "worked",
                    },
                    {
                        "rule_code": "field_order_invalid",
                        "field": "blocked_by",
                        "observed_label": "worked",
                    },
                    {
                        "rule_code": "na_must_be_single",
                        "field": "blocked_by",
                        "bullet_index": 1,
                    },
                    {
                        "rule_code": "na_trailing_punctuation",
                        "field": "blocked_by",
                        "bullet_index": 1,
                    },
                    {
                        "rule_code": "forbidden_fence",
                        "field": "blocked_by",
                        "bullet_index": 2,
                    },
                    {
                        "rule_code": "bullet_too_long",
                        "field": "blocked_by",
                        "bullet_index": 3,
                        "actual_chars": len(long_json),
                        "max_allowed": 500,
                    },
                    {
                        "rule_code": "forbidden_json",
                        "field": "blocked_by",
                        "bullet_index": 3,
                    },
                    {
                        "rule_code": "unexpected_label",
                        "observed_label": "summary",
                    },
                ],
            )

    def test_post_exit_diagnostic_and_exact_one_rerun_chain(self) -> None:
        rerun_id = "20260101T000100Z_coder_123_789"
        with tempfile.TemporaryDirectory() as tmpdir:
            fixture = RoleOutcomeFixture(tmpdir)
            clean, _ = fixture.preflight("coder")
            self.assertEqual(clean.returncode, 0, clean.stderr)
            malformed = semantic_draft().replace(
                "scripts/role_outcome_receipt.py::worked",
                "N/A (why=no blocker).",
            )
            fixture.write_plan(
                mode="manager-custom-pipeline",
                evidence=malformed,
            )
            receipt = fixture.execution_receipt("coder")

            final, blocked = fixture.finalize("coder", receipt)

            self.assertEqual(final.returncode, 126, final.stderr)
            self.assertEqual(blocked["reason_code"], "semantic_draft_invalid")
            diagnostic_path = fixture.output / "role_outcome_semantic_diagnostic.json"
            diagnostic = json.loads(diagnostic_path.read_text(encoding="utf-8"))
            self.assertEqual(
                set(diagnostic),
                {
                    "schema_version",
                    "state",
                    "reason_code",
                    "run_id",
                    "role",
                    "lane",
                    "target_plan",
                    "carrier_path",
                    "semantic_draft_sha256",
                    "diagnostics",
                    "recovery_state",
                    "safe_action",
                    "written_at",
                },
            )
            self.assertEqual(diagnostic["state"], "invalid")
            self.assertEqual(diagnostic["recovery_state"], "reject_required")
            self.assertEqual(
                diagnostic["safe_action"],
                "reject_then_explicit_same_role_rerun",
            )
            self.assertEqual(stat.S_IMODE(diagnostic_path.stat().st_mode), 0o600)
            before_rejection = fixture.plan.read_text(encoding="utf-8")
            before_lines = before_rejection.splitlines(keepends=True)
            draft_index = before_rejection.splitlines().index(ROLE_OUTCOME.DRAFT_MARKER)
            draft_end = ROLE_OUTCOME._block_end(
                before_rejection.splitlines(), draft_index
            )
            unchanged_prefix = "".join(before_lines[:draft_end])

            tampered = dict(diagnostic)
            tampered["semantic_draft_sha256"] = "0" * 64
            diagnostic_path.write_text(
                json.dumps(tampered, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            rejected_tamper, tamper_payload = fixture.run(
                "reject-rerun",
                "coder",
                "--execution-receipt",
                str(receipt),
            )
            self.assertEqual(rejected_tamper.returncode, 126, rejected_tamper.stderr)
            self.assertEqual(tamper_payload["state"], "blocked")
            self.assertFalse(tamper_payload["mutation_performed"])
            self.assertEqual(
                fixture.plan.read_text(encoding="utf-8"), before_rejection
            )
            diagnostic_path.write_text(
                json.dumps(diagnostic, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            wrong_role, wrong_role_payload = fixture.run(
                "reject-rerun",
                "planner",
                "--execution-receipt",
                str(receipt),
            )
            self.assertEqual(wrong_role.returncode, 126, wrong_role.stderr)
            self.assertEqual(wrong_role_payload["state"], "blocked")
            self.assertFalse(wrong_role_payload["mutation_performed"])
            self.assertEqual(
                fixture.plan.read_text(encoding="utf-8"), before_rejection
            )

            rejected, recovery = fixture.run(
                "reject-rerun",
                "coder",
                "--execution-receipt",
                str(receipt),
            )

            self.assertEqual(rejected.returncode, 0, rejected.stderr)
            self.assertEqual(recovery["schema_version"], ROLE_OUTCOME.RECOVERY_SCHEMA)
            self.assertEqual(recovery["state"], "ready")
            self.assertEqual(recovery["rerun_budget"], 1)
            self.assertTrue(recovery["mutation_performed"])
            self.assertRegex(
                str(recovery["rejection_receipt_sha256"]), r"^[0-9a-f]{64}$"
            )
            after_rejection = fixture.plan.read_text(encoding="utf-8")
            self.assertTrue(after_rejection.startswith(unchanged_prefix))
            self.assertIn(malformed, after_rejection)
            self.assertEqual(
                after_rejection.count(ROLE_OUTCOME.REJECTION_MARKER), 1
            )

            rerun_output = fixture.root / ".tmp" / "planveyor_role_runs" / rerun_id
            rerun_output.mkdir(parents=True)
            before_reservation = fixture.plan.read_bytes()
            wrong_hash, wrong_hash_payload = fixture.run(
                "reserve-rerun",
                "coder",
                "--recovery-of-run-id",
                RUN_ID,
                "--rejection-receipt-sha256",
                "0" * 64,
                run_id=rerun_id,
            )
            self.assertEqual(wrong_hash.returncode, 126, wrong_hash.stderr)
            self.assertEqual(wrong_hash_payload["state"], "blocked")
            self.assertFalse(wrong_hash_payload["mutation_performed"])
            self.assertEqual(fixture.plan.read_bytes(), before_reservation)
            reserved, reservation = fixture.run(
                "reserve-rerun",
                "coder",
                "--recovery-of-run-id",
                RUN_ID,
                "--rejection-receipt-sha256",
                str(recovery["rejection_receipt_sha256"]),
                run_id=rerun_id,
            )
            self.assertEqual(reserved.returncode, 0, reserved.stderr)
            self.assertEqual(
                set(reservation),
                {
                    "schema_version",
                    "state",
                    "reason_code",
                    "run_id",
                    "recovery_of_run_id",
                    "rejection_receipt_sha256",
                    "role",
                    "lane",
                    "target_plan",
                    "carrier_path",
                    "safe_action",
                    "written_at",
                    "mutation_performed",
                },
            )
            self.assertEqual(reservation["state"], "started")
            self.assertTrue(reservation["mutation_performed"])

            reserved_text = fixture.plan.read_text(encoding="utf-8")
            fixture.plan.write_text(
                reserved_text.replace(
                    malformed,
                    f"{semantic_draft()}\n{malformed}",
                    1,
                ),
                encoding="utf-8",
            )
            duplicate_before_rerun, duplicate_payload = fixture.run(
                "preflight", "coder", run_id=rerun_id
            )
            self.assertEqual(
                duplicate_before_rerun.returncode,
                125,
                duplicate_before_rerun.stderr,
            )
            self.assertEqual(duplicate_payload["state"], "blocked")
            self.assertEqual(
                duplicate_payload["reason_code"],
                "preexisting_semantic_draft",
            )
            self.assertEqual(duplicate_payload["semantic_draft_count"], 1)
            fixture.plan.write_text(reserved_text, encoding="utf-8")

            preflight, preflight_payload = fixture.run(
                "preflight", "coder", run_id=rerun_id
            )
            self.assertEqual(preflight.returncode, 0, preflight.stderr)
            self.assertEqual(preflight_payload["semantic_draft_count"], 0)
            (rerun_output / "role_outcome_preflight.json").write_text(
                json.dumps(preflight_payload, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            current = fixture.plan.read_text(encoding="utf-8")
            current_lines = current.splitlines()
            rerun_index = current_lines.index(ROLE_OUTCOME.RERUN_STARTED_MARKER)
            rerun_end = ROLE_OUTCOME._block_end(current_lines, rerun_index)
            fixture.plan.write_text(
                ROLE_OUTCOME._insert_after_block(
                    current,
                    rerun_end,
                    semantic_draft().splitlines(),
                ),
                encoding="utf-8",
            )
            rerun_receipt = fixture.execution_receipt(
                "coder",
                run_id=rerun_id,
            )
            finished, finished_payload = fixture.run(
                "finalize",
                "coder",
                "--execution-receipt",
                str(rerun_receipt),
                "--preflight-result",
                str(rerun_output / "role_outcome_preflight.json"),
                run_id=rerun_id,
            )
            self.assertEqual(finished.returncode, 0, finished.stderr)
            self.assertEqual(finished_payload["state"], "finalized")
            final_text = fixture.plan.read_text(encoding="utf-8")
            self.assertIn(malformed, final_text)
            self.assertEqual(final_text.count(ROLE_OUTCOME.DRAFT_MARKER), 1)
            self.assertEqual(final_text.count(ROLE_OUTCOME.REJECTION_MARKER), 1)
            self.assertEqual(final_text.count(ROLE_OUTCOME.RERUN_STARTED_MARKER), 1)
            self.assertIn(f"  - run_id: {rerun_id}", final_text)

            before_duplicate = fixture.plan.read_bytes()
            duplicate, duplicate_payload = fixture.run(
                "reserve-rerun",
                "coder",
                "--recovery-of-run-id",
                RUN_ID,
                "--rejection-receipt-sha256",
                str(recovery["rejection_receipt_sha256"]),
                run_id="20260101T000200Z_coder_123_999",
            )
            self.assertEqual(duplicate.returncode, 126, duplicate.stderr)
            self.assertEqual(duplicate_payload["state"], "blocked")
            self.assertFalse(duplicate_payload["mutation_performed"])
            self.assertEqual(fixture.plan.read_bytes(), before_duplicate)

    def test_historical_recovery_chain_uses_declared_role_identity(self) -> None:
        planner_rerun_id = "20260101T000100Z_planner_123_789"
        with tempfile.TemporaryDirectory() as tmpdir:
            fixture = RoleOutcomeFixture(tmpdir)
            clean, _ = fixture.preflight("planner")
            self.assertEqual(clean.returncode, 0, clean.stderr)
            malformed = semantic_draft().replace(
                "scripts/role_outcome_receipt.py::worked",
                "N/A (why=no blocker).",
            )
            fixture.write_plan(
                mode="manager-custom-pipeline",
                evidence=malformed,
            )
            receipt = fixture.execution_receipt("planner")
            final, blocked = fixture.finalize("planner", receipt)
            self.assertEqual(final.returncode, 126, final.stderr)
            self.assertEqual(blocked["reason_code"], "semantic_draft_invalid")
            rejected, recovery = fixture.run(
                "reject-rerun",
                "planner",
                "--execution-receipt",
                str(receipt),
            )
            self.assertEqual(rejected.returncode, 0, rejected.stderr)
            reserved, reservation = fixture.run(
                "reserve-rerun",
                "planner",
                "--recovery-of-run-id",
                RUN_ID,
                "--rejection-receipt-sha256",
                str(recovery["rejection_receipt_sha256"]),
                run_id=planner_rerun_id,
            )
            self.assertEqual(reserved.returncode, 0, reserved.stderr)
            self.assertEqual(reservation["state"], "started")

            planner_rerun_output = (
                fixture.root / ".tmp" / "planveyor_role_runs" / planner_rerun_id
            )
            planner_preflight, planner_preflight_payload = fixture.run(
                "preflight",
                "planner",
                run_id=planner_rerun_id,
            )
            self.assertEqual(
                planner_preflight.returncode,
                0,
                planner_preflight.stderr,
            )
            (planner_rerun_output / "role_outcome_preflight.json").write_text(
                json.dumps(planner_preflight_payload, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            current = fixture.plan.read_text(encoding="utf-8")
            current_lines = current.splitlines()
            rerun_start = current_lines.index(ROLE_OUTCOME.RERUN_STARTED_MARKER)
            rerun_end = ROLE_OUTCOME._block_end(current_lines, rerun_start)
            fixture.plan.write_text(
                ROLE_OUTCOME._insert_after_block(
                    current,
                    rerun_end,
                    semantic_draft().splitlines(),
                ),
                encoding="utf-8",
            )
            planner_rerun_receipt = fixture.execution_receipt(
                "planner",
                run_id=planner_rerun_id,
            )
            planner_finished, planner_finished_payload = fixture.run(
                "finalize",
                "planner",
                "--execution-receipt",
                str(planner_rerun_receipt),
                "--preflight-result",
                str(planner_rerun_output / "role_outcome_preflight.json"),
                run_id=planner_rerun_id,
            )
            self.assertEqual(
                planner_finished.returncode,
                0,
                planner_finished.stderr,
            )
            self.assertEqual(planner_finished_payload["state"], "finalized")

            valid_text = fixture.plan.read_text(encoding="utf-8")
            self.assertIsNotNone(
                ROLE_OUTCOME._current_recovery_chain(
                    valid_text,
                    "planner",
                    PLAN_REL,
                    PLAN_REL,
                    planner_rerun_id,
                )
            )
            self.assertIsNone(
                ROLE_OUTCOME._current_recovery_chain(
                    valid_text,
                    "coder",
                    PLAN_REL,
                    PLAN_REL,
                    planner_rerun_id,
                )
            )
            role_run_ids = {
                "coder": "20260101T000200Z_coder_123_999",
                "reviewer_code_risk": (
                    "20260101T000200Z_reviewer_code_risk_123_999"
                ),
            }
            role_preflights: dict[str, dict[str, object]] = {}
            for role, role_run_id in role_run_ids.items():
                with self.subTest(role=role):
                    current, payload = fixture.run(
                        "preflight",
                        role,
                        run_id=role_run_id,
                    )
                    self.assertEqual(current.returncode, 0, current.stderr)
                    self.assertEqual(payload["state"], "ready")
                    self.assertEqual(payload["semantic_draft_count"], 0)
                    role_preflights[role] = payload

            coder_run_id = role_run_ids["coder"]
            coder_output = fixture.root / ".tmp" / "planveyor_role_runs" / coder_run_id
            (coder_output / "role_outcome_preflight.json").write_text(
                json.dumps(role_preflights["coder"], sort_keys=True) + "\n",
                encoding="utf-8",
            )
            current_lines = valid_text.splitlines()
            receipt_start = current_lines.index(ROLE_OUTCOME.RECEIPT_MARKER)
            receipt_end = ROLE_OUTCOME._block_end(current_lines, receipt_start)
            fixture.plan.write_text(
                ROLE_OUTCOME._insert_after_block(
                    valid_text,
                    receipt_end,
                    malformed.splitlines(),
                ),
                encoding="utf-8",
            )
            coder_receipt = fixture.execution_receipt(
                "coder",
                run_id=coder_run_id,
            )
            coder_final, coder_blocked = fixture.run(
                "finalize",
                "coder",
                "--execution-receipt",
                str(coder_receipt),
                "--preflight-result",
                str(coder_output / "role_outcome_preflight.json"),
                run_id=coder_run_id,
            )
            self.assertEqual(coder_final.returncode, 126, coder_final.stderr)
            self.assertEqual(
                coder_blocked["reason_code"],
                "semantic_draft_invalid",
            )
            coder_rejected, coder_recovery = fixture.run(
                "reject-rerun",
                "coder",
                "--execution-receipt",
                str(coder_receipt),
                run_id=coder_run_id,
            )
            self.assertEqual(
                coder_rejected.returncode,
                0,
                coder_rejected.stderr,
            )
            coder_rerun_id = "20260101T000300Z_coder_123_111"
            coder_reserved, coder_reservation = fixture.run(
                "reserve-rerun",
                "coder",
                "--recovery-of-run-id",
                coder_run_id,
                "--rejection-receipt-sha256",
                str(coder_recovery["rejection_receipt_sha256"]),
                run_id=coder_rerun_id,
            )
            self.assertEqual(
                coder_reserved.returncode,
                0,
                coder_reserved.stderr,
            )
            self.assertEqual(coder_reservation["state"], "started")
            sequential_text = fixture.plan.read_text(encoding="utf-8")
            self.assertEqual(
                sequential_text.count(ROLE_OUTCOME.REJECTION_MARKER),
                2,
            )
            self.assertEqual(
                sequential_text.count(ROLE_OUTCOME.RERUN_STARTED_MARKER),
                2,
            )
            coder_fresh, coder_fresh_payload = fixture.run(
                "preflight",
                "coder",
                run_id=coder_rerun_id,
            )
            self.assertEqual(coder_fresh.returncode, 0, coder_fresh.stderr)
            self.assertEqual(coder_fresh_payload["state"], "ready")
            self.assertEqual(coder_fresh_payload["semantic_draft_count"], 0)

            rerun_offset = valid_text.index(ROLE_OUTCOME.RERUN_STARTED_MARKER)
            cross_identity = (
                valid_text[:rerun_offset]
                + valid_text[rerun_offset:].replace(
                    "  - role: planner\n  - lane: planner",
                    "  - role: coder\n  - lane: coder",
                    1,
                )
            )

            unsupported_lines = valid_text.splitlines()
            rejection_start = unsupported_lines.index(ROLE_OUTCOME.REJECTION_MARKER)
            rejection = ROLE_OUTCOME.parse_ordered_block(
                unsupported_lines,
                rejection_start,
                ROLE_OUTCOME.REJECTION_MARKER,
                ROLE_OUTCOME.REJECTION_FIELDS,
            )
            unsupported_lines[
                rejection.start + ROLE_OUTCOME.REJECTION_FIELDS.index("role") + 1
            ] = "  - role: architect"
            unsupported_lines[
                rejection.start + ROLE_OUTCOME.REJECTION_FIELDS.index("lane") + 1
            ] = "  - lane: architect"
            rejection_hash = ROLE_OUTCOME._block_sha256(
                unsupported_lines,
                rejection.start,
                rejection.end,
            )
            rerun_start = unsupported_lines.index(ROLE_OUTCOME.RERUN_STARTED_MARKER)
            rerun = ROLE_OUTCOME.parse_ordered_block(
                unsupported_lines,
                rerun_start,
                ROLE_OUTCOME.RERUN_STARTED_MARKER,
                ROLE_OUTCOME.RERUN_STARTED_FIELDS,
            )
            unsupported_lines[
                rerun.start
                + ROLE_OUTCOME.RERUN_STARTED_FIELDS.index(
                    "rejection_receipt_sha256"
                )
                + 1
            ] = f"  - rejection_receipt_sha256: {rejection_hash}"
            unsupported_lines[
                rerun.start + ROLE_OUTCOME.RERUN_STARTED_FIELDS.index("role") + 1
            ] = "  - role: architect"
            unsupported_lines[
                rerun.start + ROLE_OUTCOME.RERUN_STARTED_FIELDS.index("lane") + 1
            ] = "  - lane: architect"
            unsupported = "\n".join(unsupported_lines) + "\n"

            for case, malformed_chain in (
                ("cross_identity", cross_identity),
                ("unsupported_role", unsupported),
            ):
                with self.subTest(case=case):
                    fixture.plan.write_text(malformed_chain, encoding="utf-8")
                    current, payload = fixture.run(
                        "preflight",
                        "coder",
                        run_id="20260101T000300Z_coder_123_111",
                    )
                    self.assertEqual(current.returncode, 125, current.stderr)
                    self.assertEqual(payload["state"], "blocked")
                    self.assertEqual(
                        payload["reason_code"],
                        "recovery_chain_invalid",
                    )

    def test_pending_rejection_boundary_and_orphan_marker_fail_closed(self) -> None:
        next_run_id = "20260101T000100Z_coder_123_789"
        with tempfile.TemporaryDirectory() as tmpdir:
            fixture = RoleOutcomeFixture(tmpdir)
            clean, _ = fixture.preflight("coder")
            self.assertEqual(clean.returncode, 0, clean.stderr)
            malformed = semantic_draft().replace(
                "scripts/role_outcome_receipt.py::worked",
                "N/A (why=no blocker).",
            )
            fixture.write_plan(
                mode="manager-custom-pipeline",
                evidence=malformed,
            )
            receipt = fixture.execution_receipt("coder")
            final, blocked = fixture.finalize("coder", receipt)
            self.assertEqual(final.returncode, 126, final.stderr)
            self.assertEqual(blocked["reason_code"], "semantic_draft_invalid")
            rejected, _ = fixture.run(
                "reject-rerun",
                "coder",
                "--execution-receipt",
                str(receipt),
            )
            self.assertEqual(rejected.returncode, 0, rejected.stderr)

            pending_text = fixture.plan.read_text(encoding="utf-8")
            pending, pending_payload = fixture.run(
                "preflight",
                "coder",
                run_id=next_run_id,
            )
            self.assertEqual(pending.returncode, 125, pending.stderr)
            self.assertEqual(pending_payload["state"], "blocked")
            self.assertEqual(
                pending_payload["reason_code"],
                "preexisting_semantic_draft",
            )
            self.assertEqual(pending_payload["semantic_draft_count"], 1)

            pending_lines = pending_text.splitlines()
            draft_start = pending_lines.index(ROLE_OUTCOME.DRAFT_MARKER)
            draft_end = ROLE_OUTCOME._block_end(pending_lines, draft_start)
            rejection_end = ROLE_OUTCOME._block_end(pending_lines, draft_end)
            valid_pending_lines = pending_text.replace(
                malformed,
                semantic_draft(),
                1,
            ).splitlines()
            valid_draft_start = valid_pending_lines.index(
                ROLE_OUTCOME.DRAFT_MARKER
            )
            valid_rejection_start = valid_pending_lines.index(
                ROLE_OUTCOME.REJECTION_MARKER
            )
            valid_draft_hash = ROLE_OUTCOME._candidate_sha256(
                "\n".join(valid_pending_lines),
                valid_draft_start,
            )
            valid_pending_lines[
                valid_rejection_start
                + ROLE_OUTCOME.REJECTION_FIELDS.index(
                    "semantic_draft_sha256"
                )
                + 1
            ] = f"  - semantic_draft_sha256: {valid_draft_hash}"
            valid_rejection_end = ROLE_OUTCOME._block_end(
                valid_pending_lines,
                valid_rejection_start,
            )
            forged_rejection_hash = ROLE_OUTCOME._block_sha256(
                valid_pending_lines,
                valid_rejection_start,
                valid_rejection_end,
            )
            forged_pending_text = "\n".join(valid_pending_lines) + "\n"
            fixture.plan.write_text(forged_pending_text, encoding="utf-8")
            before_forged_reservation = fixture.plan.read_bytes()
            forged_reservation, forged_payload = fixture.run(
                "reserve-rerun",
                "coder",
                "--recovery-of-run-id",
                RUN_ID,
                "--rejection-receipt-sha256",
                forged_rejection_hash,
                run_id=next_run_id,
            )
            self.assertEqual(
                forged_reservation.returncode,
                126,
                forged_reservation.stderr,
            )
            self.assertEqual(forged_payload["state"], "blocked")
            self.assertEqual(
                forged_payload["reason_code"],
                "recovery_chain_invalid",
            )
            self.assertFalse(forged_payload["mutation_performed"])
            self.assertEqual(
                fixture.plan.read_bytes(),
                before_forged_reservation,
            )
            self.assertNotIn(
                ROLE_OUTCOME.RERUN_STARTED_MARKER,
                fixture.plan.read_text(encoding="utf-8"),
            )
            orphan_variants = {
                "valid_draft_with_forged_rejection": forged_pending_text,
                "valid_block_without_draft": (
                    "\n".join(
                        pending_lines[:draft_start] + pending_lines[draft_end:]
                    )
                    + "\n"
                ),
                "malformed_standalone_marker": (
                    "\n".join(
                        pending_lines[:draft_start]
                        + [ROLE_OUTCOME.REJECTION_MARKER]
                        + pending_lines[rejection_end:]
                    )
                    + "\n"
                ),
            }
            for case, orphan_text in orphan_variants.items():
                with self.subTest(case=case):
                    fixture.plan.write_text(orphan_text, encoding="utf-8")
                    orphan, orphan_payload = fixture.run(
                        "preflight",
                        "coder",
                        run_id=next_run_id,
                    )
                    self.assertEqual(orphan.returncode, 125, orphan.stderr)
                    self.assertEqual(orphan_payload["state"], "blocked")
                    self.assertEqual(
                        orphan_payload["reason_code"],
                        "recovery_chain_invalid",
                    )

    def test_inactive_and_unsupported_are_ephemeral_not_applicable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            fixture = RoleOutcomeFixture(tmpdir, mode="fresh-exec")
            result, payload = fixture.run("preflight", "coder")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(payload["state"], "not_applicable")
            self.assertEqual(payload["reason_code"], "mode_inactive")
            self.assertFalse((fixture.output / "role_outcome_readback.json").exists())

            fixture.write_plan(mode="manager-custom-pipeline")
            result, payload = fixture.run("preflight", "architect")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(payload["reason_code"], "unsupported_role")
            self.assertFalse((fixture.output / "role_outcome_readback.json").exists())

    def test_preflight_blocks_existing_draft_before_process_start(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            fixture = RoleOutcomeFixture(tmpdir)
            fixture.write_plan(mode="manager-custom-pipeline", evidence=semantic_draft())
            result, payload = fixture.preflight("coder")
            self.assertEqual(result.returncode, 125, result.stderr)
            self.assertEqual(payload["state"], "blocked")
            self.assertEqual(payload["reason_code"], "preexisting_semantic_draft")
            receipt = fixture.execution_receipt(
                "coder",
                state="precondition_failed",
                exit_code=125,
                process_start_outcome="not_started",
                non_green_reason="role_outcome_preflight_failed",
            )
            final, final_payload = fixture.finalize("coder", receipt)
            self.assertEqual(final.returncode, 125, final.stderr)
            self.assertEqual(final_payload["state"], "blocked")
            self.assertEqual(final_payload["reason_code"], "preexisting_semantic_draft")
            self.assertTrue(final_payload["role_outcome_readback_persisted"])
            persisted = json.loads(
                (fixture.output / "role_outcome_readback.json").read_text(encoding="utf-8")
            )
            self.assertEqual(persisted["state"], "blocked")
            self.assertNotIn("role_outcome_readback_persisted", persisted)

    def test_successful_finalization_preserves_semantics_and_owns_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            fixture = RoleOutcomeFixture(tmpdir)
            clean, preflight = fixture.preflight("coder")
            self.assertEqual(clean.returncode, 0, clean.stderr)
            self.assertEqual(preflight["state"], "ready")
            fixture.write_plan(mode="manager-custom-pipeline", evidence=semantic_draft())
            receipt = fixture.execution_receipt("coder", runner_id="codex")
            receipt_before = receipt.read_bytes()
            final, payload = fixture.finalize("coder", receipt)
            self.assertEqual(final.returncode, 0, final.stderr)
            self.assertEqual(payload["state"], "finalized")
            self.assertEqual(payload["reason_code"], "ok")
            self.assertTrue(payload["role_outcome_readback_persisted"])
            self.assertEqual(receipt.read_bytes(), receipt_before)
            self.assertEqual(
                json.loads(receipt.read_text(encoding="utf-8"))["runner_id"],
                "codex",
            )
            text = fixture.plan.read_text(encoding="utf-8")
            self.assertNotIn(ROLE_OUTCOME.DRAFT_MARKER, text)
            self.assertIn(ROLE_OUTCOME.RECEIPT_MARKER, text)
            self.assertIn("  - role: coder", text)
            self.assertIn("  - lane: coder", text)
            self.assertIn(f"  - run_id: {RUN_ID}", text)
            self.assertIn(f"  - target_plan: {PLAN_REL}", text)
            self.assertIn(f"  - artifact_ref: {PLAN_REL}::## Evidence", text)
            self.assertIn("    - scripts/role_outcome_receipt.py::worked", text)
            self.assertFalse(
                (fixture.output / "role_outcome_semantic_diagnostic.json").exists()
            )
            persisted_path = fixture.output / "role_outcome_readback.json"
            persisted = json.loads(persisted_path.read_text(encoding="utf-8"))
            self.assertEqual(
                set(persisted),
                {
                    "schema_version",
                    "state",
                    "reason_code",
                    "run_id",
                    "role",
                    "lane",
                    "target_plan",
                    "execution_receipt_path",
                    "carrier_path",
                    "artifact_ref",
                    "semantic_draft_count",
                    "finalized_receipt_count",
                    "forbidden_carrier_hits",
                    "written_at",
                },
            )
            read, read_payload = fixture.readback("coder", receipt)
            self.assertEqual(read.returncode, 0, read.stderr)
            self.assertEqual(read_payload["written_at"], persisted["written_at"])
            persisted["carrier_path"] = REVIEW_REL
            (fixture.output / "role_outcome_readback.json").write_text(
                json.dumps(persisted) + "\n", encoding="utf-8"
            )
            mismatched, mismatched_payload = fixture.readback("coder", receipt)
            self.assertEqual(mismatched.returncode, 126, mismatched.stderr)
            self.assertEqual(mismatched_payload["reason_code"], "execution_identity_mismatch")

    def test_exact_four_role_placement_matrix(self) -> None:
        roles = (
            "planner",
            "coder",
            "reviewer_code_risk",
            "reviewer_code_contracts",
        )
        for role in roles:
            with self.subTest(role=role), tempfile.TemporaryDirectory() as tmpdir:
                fixture = RoleOutcomeFixture(tmpdir)
                clean, _ = fixture.preflight(role)
                self.assertEqual(clean.returncode, 0, clean.stderr)
                if role == "reviewer_code_contracts":
                    fixture.review.write_text(
                        "# Review\n\n## Evidence\n" + semantic_draft() + "\n", encoding="utf-8"
                    )
                else:
                    fixture.write_plan(mode="manager-custom-pipeline", evidence=semantic_draft())
                receipt = fixture.execution_receipt(role)
                final, payload = fixture.finalize(role, receipt)
                self.assertEqual(final.returncode, 0, final.stderr)
                expected_rel = REVIEW_REL if role == "reviewer_code_contracts" else PLAN_REL
                self.assertEqual(payload["role"], role)
                self.assertEqual(payload["lane"], role)
                self.assertEqual(payload["carrier_path"], expected_rel)
                expected_text = (
                    fixture.review if role == "reviewer_code_contracts" else fixture.plan
                ).read_text(encoding="utf-8")
                forbidden_text = (
                    fixture.plan if role == "reviewer_code_contracts" else fixture.review
                ).read_text(encoding="utf-8")
                self.assertIn(f"  - role: {role}", expected_text)
                self.assertNotIn(ROLE_OUTCOME.RECEIPT_MARKER, forbidden_text)

    def test_plan_carrier_roles_accept_explicit_na_review_artifact(self) -> None:
        review_na = "- `N/A (why=child plans own review artifacts)`"
        for role in ("planner", "coder", "reviewer_code_risk"):
            with self.subTest(role=role), tempfile.TemporaryDirectory() as tmpdir:
                fixture = RoleOutcomeFixture(tmpdir)
                fixture.review.unlink()
                fixture.write_plan(
                    mode="manager-custom-pipeline",
                    plan_type="decomposition",
                    review_artifacts=review_na,
                )
                clean, preflight = fixture.preflight(role)
                self.assertEqual(clean.returncode, 0, clean.stderr)
                self.assertEqual(preflight["state"], "ready")
                self.assertIsNone(preflight["forbidden_carrier_path"])
                fixture.write_plan(
                    mode="manager-custom-pipeline",
                    evidence=semantic_draft(),
                    plan_type="decomposition",
                    review_artifacts=review_na,
                )
                receipt = fixture.execution_receipt(role)
                final, payload = fixture.finalize(role, receipt)
                self.assertEqual(final.returncode, 0, final.stderr)
                self.assertEqual(payload["state"], "finalized")
                self.assertEqual(payload["reason_code"], "ok")
                self.assertEqual(payload["carrier_path"], PLAN_REL)
                self.assertIn(
                    f"  - role: {role}",
                    fixture.plan.read_text(encoding="utf-8"),
                )

        with tempfile.TemporaryDirectory() as tmpdir:
            fixture = RoleOutcomeFixture(tmpdir)
            fixture.review.unlink()
            fixture.write_plan(
                mode="manager-custom-pipeline",
                plan_type="decomposition",
                review_artifacts=review_na,
            )
            blocked, payload = fixture.run("preflight", "reviewer_code_contracts")
            self.assertEqual(blocked.returncode, 125, blocked.stderr)
            self.assertEqual(payload["reason_code"], "carrier_resolution_failed")

    def test_plan_carrier_rejects_ambiguous_evidence_headings(self) -> None:
        for duplicate_heading in (EVIDENCE_HEADING, "## Evidence"):
            with self.subTest(duplicate_heading=duplicate_heading), tempfile.TemporaryDirectory() as tmpdir:
                fixture = RoleOutcomeFixture(tmpdir)
                plan_text = fixture.plan.read_text(encoding="utf-8")
                fixture.plan.write_text(
                    plan_text.replace(
                        f"{EVIDENCE_HEADING}\n",
                        f"{EVIDENCE_HEADING}\n\n{duplicate_heading}\n",
                        1,
                    ),
                    encoding="utf-8",
                )
                result, payload = fixture.run("preflight", "coder")
                self.assertEqual(result.returncode, 125, result.stderr)
                self.assertEqual(payload["reason_code"], "carrier_resolution_failed")

    def test_plan_carrier_roles_reject_ambiguous_or_unsafe_concrete_review(self) -> None:
        ambiguous_sections = (
            (
                f"- Code review (primary): `{REVIEW_REL}`\n"
                "- Code review (other): `docs/code_reviews/260101_0001_other.md`"
            ),
            (
                f"- Code review (primary): `{REVIEW_REL}`\n"
                "- `N/A (why=child plans own review artifacts)`"
            ),
        )
        for review_artifacts in ambiguous_sections:
            with self.subTest(review_artifacts=review_artifacts), tempfile.TemporaryDirectory() as tmpdir:
                fixture = RoleOutcomeFixture(tmpdir)
                fixture.write_plan(
                    mode="manager-custom-pipeline",
                    review_artifacts=review_artifacts,
                )
                result, payload = fixture.run("preflight", "coder")
                self.assertEqual(result.returncode, 125, result.stderr)
                self.assertEqual(payload["reason_code"], "carrier_resolution_failed")

        for role in ("coder", "reviewer_code_contracts"):
            with self.subTest(role=role), tempfile.TemporaryDirectory() as tmpdir:
                fixture = RoleOutcomeFixture(tmpdir)
                target = fixture.root / "actual-review.md"
                target.write_text("# Review\n", encoding="utf-8")
                fixture.review.unlink()
                fixture.review.symlink_to(target)
                result, payload = fixture.run("preflight", role)
                self.assertEqual(result.returncode, 125, result.stderr)
                self.assertEqual(payload["reason_code"], "unsafe_carrier_path")

    def test_wrong_placement_duplicate_and_invalid_semantics_have_distinct_reasons(self) -> None:
        cases = {
            "wrong_placement": ("review", semantic_draft()),
            "wrong_placement_outside_evidence": ("plan_outside", semantic_draft()),
            "semantic_draft_duplicate": ("plan", semantic_draft() + "\n" + semantic_draft()),
            "semantic_draft_invalid": ("plan", semantic_draft(invalid="envelope")),
        }
        for expected_reason, (carrier, content) in cases.items():
            with self.subTest(reason=expected_reason), tempfile.TemporaryDirectory() as tmpdir:
                fixture = RoleOutcomeFixture(tmpdir)
                clean, _ = fixture.preflight("coder")
                self.assertEqual(clean.returncode, 0, clean.stderr)
                if carrier == "plan":
                    fixture.write_plan(mode="manager-custom-pipeline", evidence=content)
                elif carrier == "plan_outside":
                    plan_text = fixture.plan.read_text(encoding="utf-8")
                    fixture.plan.write_text(
                        plan_text.replace(
                            f"{EVIDENCE_HEADING}\n",
                            f"{content}\n\n{EVIDENCE_HEADING}\n",
                            1,
                        ),
                        encoding="utf-8",
                    )
                else:
                    fixture.review.write_text("# Review\n\n" + content + "\n", encoding="utf-8")
                receipt = fixture.execution_receipt("coder")
                final, payload = fixture.finalize("coder", receipt)
                self.assertEqual(final.returncode, 126, final.stderr)
                self.assertEqual(
                    payload["reason_code"],
                    "wrong_placement" if expected_reason == "wrong_placement_outside_evidence" else expected_reason,
                )
                self.assertTrue(payload["role_outcome_readback_persisted"])

    def test_execution_identity_mismatch_cannot_be_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            fixture = RoleOutcomeFixture(tmpdir)
            clean, _ = fixture.preflight("reviewer_code_contracts")
            self.assertEqual(clean.returncode, 0, clean.stderr)
            fixture.review.write_text("# Review\n\n" + semantic_draft() + "\n", encoding="utf-8")
            receipt = fixture.execution_receipt("reviewer")
            final, payload = fixture.finalize("reviewer_code_contracts", receipt)
            self.assertEqual(final.returncode, 126, final.stderr)
            self.assertEqual(payload["reason_code"], "execution_identity_mismatch")
            self.assertNotIn(ROLE_OUTCOME.RECEIPT_MARKER, fixture.review.read_text(encoding="utf-8"))

    def test_forbidden_duplicate_incident_shape_remains_non_green(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            fixture = RoleOutcomeFixture(tmpdir)
            clean, _ = fixture.preflight("reviewer_code_contracts")
            self.assertEqual(clean.returncode, 0, clean.stderr)
            generic = finalized_receipt("reviewer", RUN_ID, REVIEW_REL)
            fixture.review.write_text("# Review\n\n" + generic + "\n", encoding="utf-8")
            fixture.write_plan(
                mode="manager-custom-pipeline",
                evidence=finalized_receipt("reviewer_code_contracts", RUN_ID, f"{PLAN_REL}::## Evidence"),
            )
            receipt = fixture.execution_receipt("reviewer_code_contracts")
            final, payload = fixture.finalize("reviewer_code_contracts", receipt)
            self.assertEqual(final.returncode, 126, final.stderr)
            self.assertIn(
                payload["reason_code"],
                {"current_outcome_duplicate", "forbidden_carrier_present"},
            )

    def test_recover_readback_is_exact_run_only_and_does_not_rewrite_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            fixture = RoleOutcomeFixture(tmpdir)
            artifact_ref = f"{PLAN_REL}::## Evidence"
            receipt_text = finalized_receipt("coder", RUN_ID, artifact_ref)
            fixture.write_plan(mode="manager-custom-pipeline", evidence=receipt_text)
            execution = fixture.execution_receipt("coder")
            before = fixture.plan.read_bytes()
            missing, missing_payload = fixture.run(
                "readback",
                "coder",
                "--execution-receipt",
                str(execution),
            )
            self.assertEqual(missing.returncode, 126, missing.stderr)
            self.assertEqual(missing_payload["reason_code"], "readback_write_failed")
            self.assertFalse(missing_payload["role_outcome_readback_persisted"])
            recovered, payload = fixture.run(
                "recover-readback",
                "coder",
                "--execution-receipt",
                str(execution),
            )
            self.assertEqual(recovered.returncode, 0, recovered.stderr)
            self.assertEqual(payload["reason_code"], "already_finalized")
            self.assertEqual(fixture.plan.read_bytes(), before)
            persisted = json.loads(
                (fixture.output / "role_outcome_readback.json").read_text(encoding="utf-8")
            )
            self.assertEqual(persisted["written_at"], "2026-01-01T00:00:00Z")

    def test_compare_before_replace_and_readback_failure_are_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            fixture = RoleOutcomeFixture(tmpdir)
            original = fixture.plan.read_bytes()
            fixture.plan.write_text("changed\n", encoding="utf-8")
            with self.assertRaises(ROLE_OUTCOME.CarrierChanged):
                ROLE_OUTCOME.atomic_write(
                    fixture.plan,
                    b"replacement\n",
                    expected_before=original,
                )

            paths = ROLE_OUTCOME.Paths(
                fixture.root,
                PLAN_REL,
                fixture.plan,
                fixture.output,
                fixture.output / "role_outcome_readback.json",
                fixture.output / "role_outcome_preflight.json",
                fixture.receipts / f"{RUN_ID}.json",
            )
            payload = ROLE_OUTCOME._readback_payload(
                paths,
                "coder",
                "finalized",
                "ok",
                execution_receipt_path=f".planveyor.role_runs/{RUN_ID}.json",
                carrier_path=PLAN_REL,
                artifact_ref=f"{PLAN_REL}::## Evidence",
                semantic_draft_count=1,
                finalized_receipt_count=1,
                forbidden_carrier_hits=[],
                written_at="2026-01-01T00:00:00Z",
            )
            with mock.patch.object(ROLE_OUTCOME, "persist_readback", side_effect=OSError("disk")):
                direct, rc = ROLE_OUTCOME._publish_or_direct_failure(paths, payload)
            self.assertEqual(rc, 126)
            self.assertEqual(direct["reason_code"], "readback_write_failed")
            self.assertFalse(direct["role_outcome_readback_persisted"])

    def test_concurrent_finalizers_have_exactly_one_green_writer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            fixture = RoleOutcomeFixture(tmpdir)
            clean, preflight = fixture.preflight("coder")
            self.assertEqual(clean.returncode, 0, clean.stderr)
            self.assertEqual(preflight["state"], "ready")
            fixture.write_plan(mode="manager-custom-pipeline", evidence=semantic_draft())
            receipt = fixture.execution_receipt("coder")
            paths = ROLE_OUTCOME.Paths(
                fixture.root,
                PLAN_REL,
                fixture.plan,
                fixture.output,
                fixture.output / "role_outcome_readback.json",
                fixture.output / "role_outcome_preflight.json",
                receipt,
            )
            placement = ROLE_OUTCOME.resolve_placement(
                paths,
                "coder",
                fixture.plan.read_text(encoding="utf-8"),
            )
            command = fixture.command(
                "finalize",
                "coder",
                "--execution-receipt",
                str(receipt),
                "--preflight-result",
                str(fixture.output / "role_outcome_preflight.json"),
            )
            with ROLE_OUTCOME.carrier_lock(paths, placement):
                processes = [
                    subprocess.Popen(
                        command,
                        cwd=fixture.root,
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                    for _ in range(2)
                ]
                time.sleep(0.2)
                self.assertTrue(all(process.poll() is None for process in processes))

            results = []
            for process in processes:
                stdout, stderr = process.communicate(timeout=10)
                results.append((process.returncode, json.loads(stdout), stderr))
            self.assertEqual(sorted(result[0] for result in results), [0, 126], results)
            green = next(result for result in results if result[0] == 0)
            blocked = next(result for result in results if result[0] == 126)
            self.assertEqual(green[1]["state"], "finalized")
            self.assertEqual(green[1]["reason_code"], "ok")
            self.assertTrue(green[1]["role_outcome_readback_persisted"])
            self.assertEqual(blocked[1]["state"], "blocked")
            self.assertEqual(blocked[1]["reason_code"], "current_outcome_duplicate")
            self.assertFalse(blocked[1]["role_outcome_readback_persisted"])
            plan_text = fixture.plan.read_text(encoding="utf-8")
            self.assertNotIn(ROLE_OUTCOME.DRAFT_MARKER, plan_text)
            self.assertEqual(plan_text.count(ROLE_OUTCOME.RECEIPT_MARKER), 1)
            persisted = json.loads(
                (fixture.output / "role_outcome_readback.json").read_text(encoding="utf-8")
            )
            self.assertEqual(persisted["state"], "finalized")
            self.assertEqual(persisted["reason_code"], "ok")

    def test_concurrent_loser_preserves_missing_readback_for_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            fixture = RoleOutcomeFixture(tmpdir)
            clean, preflight = fixture.preflight("coder")
            self.assertEqual(clean.returncode, 0, clean.stderr)
            self.assertEqual(preflight["state"], "ready")
            fixture.write_plan(mode="manager-custom-pipeline", evidence=semantic_draft())
            receipt = fixture.execution_receipt("coder")
            paths = ROLE_OUTCOME.Paths(
                fixture.root,
                PLAN_REL,
                fixture.plan,
                fixture.output,
                fixture.output / "role_outcome_readback.json",
                fixture.output / "role_outcome_preflight.json",
                receipt,
            )
            placement = ROLE_OUTCOME.resolve_placement(
                paths,
                "coder",
                fixture.plan.read_text(encoding="utf-8"),
            )
            command = fixture.command(
                "finalize",
                "coder",
                "--execution-receipt",
                str(receipt),
                "--preflight-result",
                str(fixture.output / "role_outcome_preflight.json"),
            )
            original_mode = fixture.output.stat().st_mode & 0o777
            processes: list[subprocess.Popen[str]] = []
            try:
                with ROLE_OUTCOME.carrier_lock(paths, placement):
                    fixture.output.chmod(0o500)
                    processes = [
                        subprocess.Popen(
                            command,
                            cwd=fixture.root,
                            text=True,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                        )
                        for _ in range(2)
                    ]
                    time.sleep(0.2)
                    self.assertTrue(all(process.poll() is None for process in processes))

                results = []
                for process in processes:
                    stdout, stderr = process.communicate(timeout=10)
                    results.append((process.returncode, json.loads(stdout), stderr))
            finally:
                fixture.output.chmod(original_mode)
                for process in processes:
                    if process.poll() is None:
                        process.terminate()
                        process.wait(timeout=5)

            self.assertEqual([result[0] for result in results], [126, 126], results)
            by_reason = {result[1]["reason_code"]: result[1] for result in results}
            self.assertEqual(
                set(by_reason),
                {"readback_write_failed", "current_outcome_duplicate"},
            )
            self.assertFalse(
                by_reason["readback_write_failed"]["role_outcome_readback_persisted"]
            )
            self.assertFalse(
                by_reason["current_outcome_duplicate"]["role_outcome_readback_persisted"]
            )
            self.assertFalse((fixture.output / "role_outcome_readback.json").exists())
            plan_text = fixture.plan.read_text(encoding="utf-8")
            self.assertEqual(plan_text.count(ROLE_OUTCOME.RECEIPT_MARKER), 1)

            recovered, payload = fixture.run(
                "recover-readback",
                "coder",
                "--execution-receipt",
                str(receipt),
            )
            self.assertEqual(recovered.returncode, 0, recovered.stderr)
            self.assertEqual(payload["state"], "finalized")
            self.assertEqual(payload["reason_code"], "already_finalized")
            self.assertTrue(payload["role_outcome_readback_persisted"])


if __name__ == "__main__":
    unittest.main()

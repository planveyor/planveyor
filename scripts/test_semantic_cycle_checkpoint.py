#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).with_name("semantic_cycle_checkpoint.py")
if str(SCRIPT_PATH.parent) not in sys.path:
    sys.path.insert(0, str(SCRIPT_PATH.parent))
SPEC = importlib.util.spec_from_file_location("semantic_cycle_checkpoint_under_test", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
CHECKPOINT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CHECKPOINT
SPEC.loader.exec_module(CHECKPOINT)


class SemanticCycleCheckpointCliTests(unittest.TestCase):
    def _run(self, plan: Path, output_format: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT_PATH), "--plan", str(plan), "--format", output_format],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_legacy_json_text_parity_and_read_only_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = Path(tmpdir) / "legacy.md"
            plan.write_text("# Plan: legacy fixture\n\n**Status:** In progress\n", encoding="utf-8")
            before = plan.read_bytes()

            json_result = self._run(plan, "json")
            text_result = self._run(plan, "text")

            self.assertEqual(json_result.returncode, 0, json_result.stderr)
            self.assertEqual(text_result.returncode, 0, text_result.stderr)
            payload = json.loads(json_result.stdout)
            text_fields = dict(line.split("=", 1) for line in text_result.stdout.splitlines())
            self.assertEqual((payload["state"], payload["reason_code"]), ("not_available", "feature_not_activated"))
            self.assertEqual(text_fields["state"], payload["state"])
            self.assertEqual(text_fields["reason_code"], payload["reason_code"])
            self.assertEqual(plan.read_bytes(), before)

    def test_active_invalid_checkpoint_returns_nonzero_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            plan = Path(tmpdir) / "checkpoint.md"
            plan.write_text(
                "# Plan: checkpoint fixture\n\n"
                "**Status:** Ready for Coder\n\n"
                "## Reviewability preflight receipt\n\n"
                "### Semantic cycle checkpoint\n"
                "- `schema=semantic_cycle_checkpoint.v1`\n"
                "- `mode=required`\n"
                "- `writer=architect`\n\n"
                "## Evidence\n",
                encoding="utf-8",
            )

            result = self._run(plan, "json")

            self.assertEqual(result.returncode, 2, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual((payload["state"], payload["reason_code"]), ("blocked", "activation_invalid"))
            self.assertTrue(any(error["code"] == "checkpoint_dual_marker_missing_producer" for error in payload["errors"]))

    def test_v2_text_projection_keeps_authority_and_contour_identity(self) -> None:
        report = {
            "schema_version": "semantic_cycle_checkpoint_report.v1",
            "state": "required",
            "reason_code": "resolution_required",
            "trigger": {
                "observation_id": "sro_fixture",
                "trigger_kind": "independent_boundary",
            },
            "resolution": None,
            "errors": [{"code": "checkpoint_resolution_required"}],
            "authority_decision_id": "mad-260815-0100",
            "authority_carrier_sha256": "a" * 64,
            "grammar_contour_id": "gc_" + "b" * 64,
        }

        fields = dict(line.split("=", 1) for line in CHECKPOINT.format_text(report).splitlines())

        self.assertEqual(fields["authority_decision_id"], report["authority_decision_id"])
        self.assertEqual(fields["authority_carrier_sha256"], report["authority_carrier_sha256"])
        self.assertEqual(fields["grammar_contour_id"], report["grammar_contour_id"])
        self.assertEqual(fields["error_codes"], "checkpoint_resolution_required")


if __name__ == "__main__":
    unittest.main()

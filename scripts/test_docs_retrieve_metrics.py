#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "docs_retrieve_metrics.py"


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


class DocsRetrieveMetricsTests(unittest.TestCase):
    def test_json_summary_keeps_missing_outcome_out_of_miss(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            query_log = tmp / "queries.jsonl"
            outcome_log = tmp / "outcomes.jsonl"
            read_log = tmp / "reads.jsonl"
            _write_jsonl(
                query_log,
                [
                    {"event_id": "e1", "hits": 1, "files": 1, "warnings": []},
                    {"event_id": "e2", "hits": 0, "files": 0, "warnings": ["retry"]},
                    {"event_id": "e3", "hits": 1, "files": 1, "warnings": []},
                ],
            )
            _write_jsonl(
                outcome_log,
                [
                    {"query_event_id": "e1", "outcome": "used"},
                    {"query_event_id": "e2", "outcome": "miss"},
                ],
            )
            _write_jsonl(
                read_log,
                [
                    {
                        "event_id": "read-1",
                        "event_type": "docs_get.read",
                        "tool": "docs_get",
                        "status": "ok",
                        "path": "docs/example.md",
                        "returned_bytes": 20,
                        "returned_lines": 2,
                        "truncated": False,
                    },
                    {
                        "event_id": "read-2",
                        "event_type": "docs_multi_get.read",
                        "tool": "docs_multi_get",
                        "status": "ok",
                        "files": [
                            {
                                "path": "docs/example.md",
                                "returned_bytes": 10,
                                "returned_lines": 1,
                                "truncated": True,
                            },
                            {
                                "path": "docs/other.md",
                                "returned_bytes": 30,
                                "returned_lines": 3,
                                "truncated": False,
                            },
                        ],
                    },
                    {
                        "event_id": "read-3",
                        "event_type": "docs_get.read",
                        "tool": "docs_get",
                        "status": "error",
                        "path": "docs/missing.md",
                        "returned_bytes": 0,
                        "returned_lines": 0,
                        "truncated": False,
                    },
                ],
            )

            proc = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SCRIPT),
                    "--query-log",
                    str(query_log),
                    "--outcome-log",
                    str(outcome_log),
                    "--read-log",
                    str(read_log),
                    "--format",
                    "json",
                ],
                text=True,
                capture_output=True,
                check=True,
            )

            payload = json.loads(proc.stdout)
            summary = payload["summary"]
            self.assertEqual(payload["query_log_status"], "present")
            self.assertEqual(payload["outcome_log_status"], "present")
            self.assertEqual(payload["read_log_status"], "present")
            self.assertEqual(summary["query_only"]["query_total"], 3)
            self.assertEqual(summary["query_only"]["with_hits"], 2)
            self.assertAlmostEqual(summary["query_only"]["hit_rate"], 2 / 3)
            self.assertEqual(summary["query_plus_outcome"]["evaluated_total"], 2)
            self.assertEqual(summary["query_plus_outcome"]["not_evaluated_total"], 1)
            self.assertAlmostEqual(summary["query_plus_outcome"]["outcome_evaluated_rate"], 2 / 3)
            self.assertEqual(summary["query_plus_outcome"]["outcomes"]["used"], 1)
            self.assertEqual(summary["query_plus_outcome"]["outcomes"]["miss"], 1)
            self.assertEqual(summary["query_plus_outcome"]["outcomes"]["not_evaluated"], 1)
            self.assertEqual(summary["read_open"]["read_events_total"], 3)
            self.assertAlmostEqual(summary["read_open"]["read_open_rate"], 1.0)
            self.assertEqual(summary["read_open"]["ok_events_total"], 2)
            self.assertEqual(summary["read_open"]["error_events_total"], 1)
            self.assertEqual(summary["read_open"]["files_total"], 4)
            self.assertEqual(summary["read_open"]["unique_paths"], 3)
            self.assertEqual(summary["read_open"]["returned_bytes_total"], 60)
            self.assertEqual(summary["read_open"]["returned_lines_total"], 6)
            self.assertEqual(summary["read_open"]["truncated_files_total"], 1)
            self.assertEqual(summary["read_open"]["tools"]["docs_get"], 2)
            self.assertEqual(summary["read_open"]["tools"]["docs_multi_get"], 1)
            self.assertEqual(summary["read_open"]["top_paths"][0]["path"], "docs/example.md")
            self.assertEqual(summary["read_open"]["top_paths"][0]["reads"], 2)
            self.assertEqual(
                summary["decision_usage"],
                {"used_for_decision": False, "accepted_no_op_reason": "not_used_for_decision"},
            )
            self.assertEqual(summary["process_findings"], [])

    def test_text_summary_names_query_and_outcome_views(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            query_log = tmp / "queries.jsonl"
            outcome_log = tmp / "outcomes.jsonl"
            read_log = tmp / "reads.jsonl"
            _write_jsonl(query_log, [{"event_id": "e1", "hits": 0, "files": 0, "warnings": []}])
            _write_jsonl(outcome_log, [])
            _write_jsonl(
                read_log,
                [
                    {
                        "event_id": "read-1",
                        "event_type": "docs_get.read",
                        "tool": "docs_get",
                        "status": "ok",
                        "path": "docs/example.md",
                        "returned_bytes": 8,
                        "returned_lines": 1,
                        "truncated": False,
                    }
                ],
            )

            proc = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SCRIPT),
                    "--query-log",
                    str(query_log),
                    "--outcome-log",
                    str(outcome_log),
                    "--read-log",
                    str(read_log),
                ],
                text=True,
                capture_output=True,
                check=True,
            )

            self.assertIn("query-only baseline:", proc.stdout)
            self.assertIn("query_log_status: present", proc.stdout)
            self.assertIn("outcome_log_status: present", proc.stdout)
            self.assertIn("read_log_status: present", proc.stdout)
            self.assertIn("used_for_decision: false", proc.stdout)
            self.assertIn("accepted_no_op_reason: not_used_for_decision", proc.stdout)
            self.assertIn("query+outcome view:", proc.stdout)
            self.assertIn("outcome_evaluated_rate: 0.0%", proc.stdout)
            self.assertIn("read/open view:", proc.stdout)
            self.assertIn("read_open_rate: 100.0%", proc.stdout)
            self.assertIn("process findings:", proc.stdout)
            self.assertIn("zero_outcome_coverage", proc.stdout)
            self.assertIn("read_events_total: 1", proc.stdout)
            self.assertIn("not_evaluated", proc.stdout)
            self.assertIn("not miss", proc.stdout)

    def test_json_summary_reports_missing_optional_log_statuses(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            query_log = tmp / "queries.jsonl"
            _write_jsonl(query_log, [{"event_id": "e1", "hits": 0, "files": 0, "warnings": []}])

            proc = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SCRIPT),
                    "--query-log",
                    str(query_log),
                    "--outcome-log",
                    str(tmp / "missing-outcomes.jsonl"),
                    "--read-log",
                    str(tmp / "missing-reads.jsonl"),
                    "--format",
                    "json",
                ],
                text=True,
                capture_output=True,
                check=True,
            )

            payload = json.loads(proc.stdout)
            summary = payload["summary"]
            self.assertEqual(payload["query_log_status"], "present")
            self.assertEqual(payload["outcome_log_status"], "missing")
            self.assertEqual(payload["read_log_status"], "missing")
            self.assertEqual(summary["query_plus_outcome"]["not_evaluated_total"], 1)
            self.assertEqual(summary["query_plus_outcome"]["outcome_evaluated_rate"], 0.0)
            self.assertEqual(summary["read_open"]["read_events_total"], 0)
            self.assertEqual(summary["read_open"]["read_open_rate"], 0.0)
            self.assertEqual(summary["read_open"]["unique_paths"], 0)
            self.assertEqual(
                {finding["code"] for finding in summary["process_findings"]},
                {"zero_outcome_coverage", "zero_read_open_coverage"},
            )

    def test_json_summary_reports_missing_query_log_as_zero_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)

            proc = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SCRIPT),
                    "--query-log",
                    str(tmp / "missing-queries.jsonl"),
                    "--outcome-log",
                    str(tmp / "missing-outcomes.jsonl"),
                    "--read-log",
                    str(tmp / "missing-reads.jsonl"),
                    "--format",
                    "json",
                ],
                text=True,
                capture_output=True,
                check=True,
            )

            payload = json.loads(proc.stdout)
            summary = payload["summary"]
            self.assertEqual(payload["query_log_status"], "missing")
            self.assertEqual(summary["query_only"]["query_total"], 0)
            self.assertEqual(summary["query_only"]["with_hits"], 0)
            self.assertEqual(summary["query_only"]["zero_hits"], 0)
            self.assertEqual(summary["query_plus_outcome"]["evaluated_total"], 0)
            self.assertEqual(summary["read_open"]["read_events_total"], 0)
            self.assertEqual(summary["query_plus_outcome"]["outcome_evaluated_rate"], 1.0)
            self.assertEqual(summary["read_open"]["read_open_rate"], 1.0)

    def test_json_summary_uses_quality_gate_thresholds(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            query_log = tmp / "queries.jsonl"
            outcome_log = tmp / "outcomes.jsonl"
            read_log = tmp / "reads.jsonl"
            _write_jsonl(query_log, [{"event_id": f"e{i}", "hits": 1, "files": 1, "warnings": []} for i in range(100)])
            _write_jsonl(outcome_log, [{"query_event_id": f"e{i}", "outcome": "used"} for i in range(10)])
            _write_jsonl(
                read_log,
                [
                    {
                        "event_id": "read-1",
                        "event_type": "docs_get.read",
                        "tool": "docs_get",
                        "status": "ok",
                        "path": "docs/example.md",
                        "returned_bytes": 8,
                        "returned_lines": 1,
                        "truncated": False,
                    }
                ],
            )

            proc = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SCRIPT),
                    "--query-log",
                    str(query_log),
                    "--outcome-log",
                    str(outcome_log),
                    "--read-log",
                    str(read_log),
                    "--format",
                    "json",
                ],
                text=True,
                capture_output=True,
                check=True,
            )

            summary = json.loads(proc.stdout)["summary"]
            self.assertEqual(summary["query_plus_outcome"]["outcome_evaluated_rate"], 0.10)
            self.assertEqual(summary["read_open"]["read_open_rate"], 0.01)
            self.assertEqual(
                {finding["code"] for finding in summary["process_findings"]},
                {"low_outcome_coverage", "low_read_open_coverage"},
            )

    def test_json_summary_accepts_decision_used_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            query_log = tmp / "queries.jsonl"
            outcome_log = tmp / "outcomes.jsonl"
            read_log = tmp / "reads.jsonl"
            _write_jsonl(query_log, [{"event_id": "e1", "hits": 1, "files": 1, "warnings": []}])
            _write_jsonl(outcome_log, [{"query_event_id": "e1", "outcome": "used"}])
            _write_jsonl(
                read_log,
                [
                    {
                        "event_id": "read-1",
                        "event_type": "docs_get.read",
                        "tool": "docs_get",
                        "status": "ok",
                        "path": "docs/example.md",
                    }
                ],
            )

            proc = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SCRIPT),
                    "--query-log",
                    str(query_log),
                    "--outcome-log",
                    str(outcome_log),
                    "--read-log",
                    str(read_log),
                    "--used-for-decision",
                    "true",
                    "--accepted-no-op-reason",
                    "accepted_no_op",
                    "--format",
                    "json",
                ],
                text=True,
                capture_output=True,
                check=True,
            )

            summary = json.loads(proc.stdout)["summary"]
            self.assertEqual(
                summary["decision_usage"],
                {"used_for_decision": True, "accepted_no_op_reason": "accepted_no_op"},
            )

    def test_rejects_not_used_reason_with_decision_used_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            query_log = tmp / "queries.jsonl"
            _write_jsonl(query_log, [{"event_id": "e1", "hits": 1, "files": 1, "warnings": []}])

            proc = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SCRIPT),
                    "--query-log",
                    str(query_log),
                    "--used-for-decision",
                    "true",
                    "--accepted-no-op-reason",
                    "not_used_for_decision",
                    "--format",
                    "json",
                ],
                text=True,
                capture_output=True,
            )

            self.assertEqual(proc.returncode, 2)
            self.assertIn("not_used_for_decision is invalid", proc.stderr)


if __name__ == "__main__":
    unittest.main()

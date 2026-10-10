from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("wave_telemetry_report.py")
SPEC = importlib.util.spec_from_file_location("wave_telemetry_report", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _plan(*, title: str, status: str, plan_meta: dict[str, object], body: str = "") -> str:
    # Keep the shared 8-space template indent on every substituted line so that
    # textwrap.dedent below really emits canonical column-0 ``## Meta`` headings
    # (the strict routing reader only accepts 0-3 leading spaces).
    meta = textwrap.indent(
        json.dumps({"plan_meta": plan_meta}, ensure_ascii=False, indent=2),
        "        ",
    )
    indented_body = textwrap.indent(body, "        ") if body else ""
    return textwrap.dedent(
        f"""\
        # Plan: {title}

        **Date:** 2026-06-19 00:00 MSK
        **Stage:** Stage 2
        **Priority:** P1
        **Plan type:** dev
        **Status:** {status}
        **Schema version:** plan.v1

        ## Meta (machine-readable JSON; required for new plans)
        ```json
        {meta}
        ```

        {indented_body}
        """
    )


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _append_jsonl(root: Path, rel: str, rows: list[dict[str, object]]) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def _build(root: Path) -> dict[str, object]:
    return MODULE.build_report(
        root=root,
        json_out=root / ".tmp/wave_telemetry_report.json",
        generated_at="2026-06-19T08:55:00Z",
        query_log=root / ".tmp/planveyor_docs_retrieve_queries.jsonl",
        outcome_log=root / ".tmp/planveyor_docs_retrieve_outcomes.jsonl",
        read_log=root / ".tmp/planveyor_docs_retrieve_reads.jsonl",
    )


class WaveTelemetryReportTests(unittest.TestCase):
    def test_green_fixture_groups_waves_and_retrieval_corpus_without_cost_guessing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _write(
                root,
                "docs/plans/260619_1000_analysis.md",
                _plan(
                    title="analysis",
                    status="Ready for Review",
                    plan_meta={"wave_family": "analysis_wave"},
                ),
            )
            _write(
                root,
                "docs/plans/260619_1001_decomp.md",
                _plan(
                    title="decomp",
                    status="In progress",
                    plan_meta={"phase_overlay": "decomposition_wave", "phase_state": "active"},
                ),
            )
            _write(
                root,
                "docs/plans/260619_1002_dev.md",
                _plan(
                    title="dev",
                    status="Ready for Coder",
                    plan_meta={
                        "promoted_from": {
                            "accepted_route": "developer_wave",
                            "promoted_artifact_ref": "docs/plans/260619_1002_dev.md",
                        }
                    },
                ),
            )
            _write(root, "docs/tools/snippet.md", "docs retrieval metrics\n")
            _append_jsonl(
                root,
                ".tmp/planveyor_docs_retrieve_queries.jsonl",
                [
                    {"event_id": "q1", "q": "docs retrieve", "hits": 2},
                    {"event_id": "q2", "q": "planning wave", "hits": 1},
                ],
            )
            _append_jsonl(
                root,
                ".tmp/planveyor_docs_retrieve_outcomes.jsonl",
                [
                    {"query_event_id": "q1", "outcome": "used"},
                    {"query_event_id": "q2", "outcome": "partial"},
                ],
            )
            _append_jsonl(
                root,
                ".tmp/planveyor_docs_retrieve_reads.jsonl",
                [
                    {
                        "read_event_id": "r1",
                        "status": "ok",
                        "tool": "docs_get",
                        "path": "docs/tools/snippet.md",
                    }
                ],
            )

            payload = _build(root)

        self.assertEqual(payload["schema_version"], "wave_telemetry_report.v1")
        self.assertEqual(payload["wave_counts"]["analysis_wave"], 1)
        self.assertEqual(payload["wave_counts"]["decomposition_wave"], 1)
        self.assertEqual(payload["wave_counts"]["developer_wave"], 1)
        self.assertEqual(payload["retrieval_metrics"]["query_total"], 2)
        self.assertEqual(payload["read_open_metrics"]["unique_paths"], 1)
        self.assertIn("docs/tools/snippet.md", payload["retrieval_corpus"]["opened_paths"])
        self.assertEqual(payload["session_metrics"]["state"], "unknown")
        self.assertEqual(payload["cost_fields"]["tokens"], "unknown")
        self.assertFalse(payload["truth_source_boundary"]["filename_or_prose_wave_truth"])
        self.assertFalse(payload["truth_source_boundary"]["raw_log_import"])
        self.assertEqual(payload["confidence"]["status"], "high")

    def test_missing_logs_are_explicit_not_available_not_synthesized(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _write(
                root,
                "docs/plans/260619_1100_dev.md",
                _plan(title="dev", status="Ready for Review", plan_meta={}),
            )

            payload = _build(root)

        self.assertEqual(payload["source_availability"]["retrieval_query_log"], "missing")
        self.assertEqual(payload["retrieval_metrics"]["state"], "not_available")
        self.assertEqual(payload["read_open_metrics"]["state"], "not_available")
        self.assertEqual(payload["cost_fields"]["cost"], "unknown")
        codes = {item["code"] for item in payload["confidence"]["diagnostics"]}
        self.assertIn("retrieval_query_log_missing", codes)
        self.assertEqual(payload["confidence"]["status"], "medium")

    def test_ambiguous_prose_wave_marker_does_not_promote_wave_truth(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _write(
                root,
                "docs/plans/260619_1200_prose.md",
                _plan(
                    title="prose only",
                    status="Ready for Review",
                    plan_meta={},
                    body="## Analysis pack\nroute_recommendation: analysis_wave\n",
                ),
            )
            _append_jsonl(root, ".tmp/planveyor_docs_retrieve_queries.jsonl", [])
            _append_jsonl(root, ".tmp/planveyor_docs_retrieve_outcomes.jsonl", [])
            _append_jsonl(root, ".tmp/planveyor_docs_retrieve_reads.jsonl", [])

            payload = _build(root)

        self.assertEqual(payload["wave_counts"]["analysis_wave"], 0)
        self.assertEqual(payload["wave_counts"]["unknown"], 1)
        codes = {item["code"] for item in payload["confidence"]["diagnostics"]}
        self.assertIn("ambiguous_prose_wave_marker", codes)

    def test_inconsistent_truth_hosts_downgrade_confidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _write(
                root,
                "docs/plans/260619_1300_conflict.md",
                _plan(
                    title="route conflict",
                    status="Ready for Review",
                    plan_meta={
                        "promoted_from": {
                            "accepted_route": "developer_wave",
                            "promoted_artifact_ref": "docs/plans/260619_1300_conflict.md",
                        }
                    },
                    body=textwrap.dedent(
                        """\
                        ## Promoted route artifact
                        | Field | Value |
                        | --- | --- |
                        | `accepted_route` | `decomposition_wave` |
                        | `promoted_artifact_ref` | `docs/plans/260619_1300_conflict.md` |
                        """
                    ),
                ),
            )
            _append_jsonl(root, ".tmp/planveyor_docs_retrieve_queries.jsonl", [{"event_id": "q1", "hits": 1}])
            _append_jsonl(
                root,
                ".tmp/planveyor_docs_retrieve_outcomes.jsonl",
                [{"query_event_id": "q-missing", "outcome": "used"}],
            )
            _append_jsonl(
                root,
                ".tmp/planveyor_docs_retrieve_reads.jsonl",
                [{"read_event_id": "r1", "status": "ok", "tool": "docs_get", "path": "docs/missing.md"}],
            )

            payload = _build(root)

        codes = {item["code"] for item in payload["confidence"]["diagnostics"]}
        self.assertIn("promoted_route_conflict", codes)
        self.assertIn("outcome_without_query", codes)
        self.assertIn("read_open_missing_path", codes)
        self.assertEqual(payload["confidence"]["status"], "low")

    def test_main_writes_json_and_prints_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _write(
                root,
                "docs/plans/260619_1400_analysis.md",
                _plan(title="analysis", status="Ready for Review", plan_meta={"wave_family": "analysis_wave"}),
            )
            _append_jsonl(root, ".tmp/planveyor_docs_retrieve_queries.jsonl", [])
            _append_jsonl(root, ".tmp/planveyor_docs_retrieve_outcomes.jsonl", [])
            _append_jsonl(root, ".tmp/planveyor_docs_retrieve_reads.jsonl", [])

            result = MODULE.main(["--root", str(root), "--generated-at", "2026-06-19T08:55:00Z"])
            payload = json.loads((root / ".tmp/wave_telemetry_report.json").read_text(encoding="utf-8"))
            plain = MODULE.render_text(payload)

        self.assertEqual(result, 0)
        self.assertEqual(payload["schema_version"], "wave_telemetry_report.v1")
        self.assertIn("wave-telemetry-report", plain)
        self.assertIn("analysis_wave", plain)


class WaveTelemetryStrictReaderTests(unittest.TestCase):
    """J1 strict-reader migration: degraded diagnostics, never green summaries."""

    def _write_carrier_plan(self, root: Path, rel: str, meta_body: str) -> None:
        text = (
            "# Plan: strict carrier fixture\n\n"
            "**Status:** Ready for Review\n\n"
            "## Meta (machine-readable JSON; required for new plans)\n"
            "```json\n"
            f"{meta_body}\n"
            "```\n"
        )
        _write(root, rel, text)

    def test_malformed_and_duplicate_meta_degrade_telemetry_not_green(self) -> None:
        cases = (
            (
                "malformed",
                '{\n  "plan_meta": {\n    "wave_family": "analysis_wave",\n',
                "malformed_json",
            ),
            (
                "duplicate_key",
                "{\n"
                '  "plan_meta": {\n'
                '    "wave_family": "analysis_wave",\n'
                '    "wave_family": "analysis_wave",\n'
                '    "promoted_from": {"accepted_route": "developer_wave"}\n'
                "  }\n"
                "}\n",
                "duplicate_json_key",
            ),
        )
        for label, meta_body, expected_code in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                self._write_carrier_plan(root, f"docs/plans/260829_1707_{label}_carrier.md", meta_body)
                _append_jsonl(root, ".tmp/planveyor_docs_retrieve_queries.jsonl", [])
                _append_jsonl(root, ".tmp/planveyor_docs_retrieve_outcomes.jsonl", [])
                _append_jsonl(root, ".tmp/planveyor_docs_retrieve_reads.jsonl", [])

                payload = _build(root)

            diagnostics = payload["confidence"]["diagnostics"]
            strict_row = next(
                (item for item in diagnostics if item["code"] == "plan_meta_strict_read_failed"),
                None,
            )
            self.assertIsNotNone(strict_row)
            self.assertEqual(strict_row["reason_code"], expected_code)
            self.assertEqual(strict_row["truth_host"], f"docs/plans/260829_1707_{label}_carrier.md#plan_meta")
            self.assertNotEqual(payload["confidence"]["status"], "high")
            self.assertEqual(payload["wave_counts"]["analysis_wave"], 0)
            self.assertEqual(payload["wave_counts"]["developer_wave"], 0)
            self.assertEqual(payload["wave_counts"]["unknown"], 1)

    def test_module_reuses_shared_strict_reader_without_local_fence_scanner(self) -> None:
        self.assertFalse(
            hasattr(MODULE, "_json_block_after"),
            "wave_telemetry_report must read Meta through "
            "plan_status_oracle.strict_plan_meta_json, not a local fence scanner",
        )
        self.assertTrue(hasattr(MODULE, "plan_status_oracle"))
        self.assertTrue(hasattr(MODULE.plan_status_oracle, "strict_plan_meta_json"))


if __name__ == "__main__":
    unittest.main()

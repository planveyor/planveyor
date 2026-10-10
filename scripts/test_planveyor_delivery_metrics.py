from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("planveyor_delivery_metrics.py")
SPEC = importlib.util.spec_from_file_location("planveyor_delivery_metrics", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )


def _trace_event(
    *,
    event_id: str,
    event_type: str,
    ts: str,
    status: str,
    plan_paths: list[str],
    source_path: str,
) -> dict[str, object]:
    return {
        "schema_version": "review_receipt.v1",
        "event_id": event_id,
        "event_type": event_type,
        "ts": ts,
        "trace_id": "N/A (why=test fixture keeps trace lineage sparse)",
        "span_id": f"span.{event_id}",
        "parent_span_id": "N/A (why=test)",
        "source_family": "review_receipt",
        "source_path": source_path,
        "source_root": "/tmp/planveyor-delivery-metrics",
        "payload": {
            "status": status,
            "plan_paths": plan_paths,
            "title": "Fixture review",
            "target": "COMMIT=current",
            "spec": plan_paths[0] if plan_paths else "",
            "blocker_ids": [],
        },
    }


def _failure_row(
    *,
    event_id: str,
    event_type: str,
    ts: str,
    failure_code: str,
    finding_ref: str,
    lineage_source: str = "trace_payload_only",
) -> dict[str, object]:
    return {
        "schema_version": "failure_attribution.v1",
        "event_id": f"evt.failure.{event_id}.{failure_code.lower()}",
        "event_type": "failure_attribution.review_receipt",
        "ts": ts,
        "trace_id": "N/A (why=test)",
        "span_id": f"span.failure.{event_id}",
        "parent_span_id": f"span.{event_id}",
        "source_family": "failure_attribution",
        "source_path": "docs/code_reviews/failure.md",
        "source_root": "/tmp/planveyor-delivery-metrics",
        "payload": {
            "failure_code": failure_code,
            "finding_ref": finding_ref,
            "current_state": "open",
            "classification_hint": "fixture",
            "primary_owner_gap": "Coder",
            "evidence_refs": ["docs/code_reviews/failure.md"],
            "reason": "fixture failure",
            "lineage_source": lineage_source,
            "source_event_id": event_id,
            "source_event_type": event_type,
            "source_event_family": "review_receipt",
        },
    }


class PlanveyorDeliveryMetricsTests(unittest.TestCase):
    def test_build_metrics_filters_positive_review_false_positive_and_counts_lane_metrics(self) -> None:
        events = [
            _trace_event(
                event_id="evt.blocked",
                event_type="review.code.single_commit",
                ts="2026-04-18T10:00:00Z",
                status="❌ S1 Blocker(s)",
                plan_paths=["docs/plans/one.md"],
                source_path="docs/code_reviews/one.md",
            ),
            _trace_event(
                event_id="evt.fixed",
                event_type="review.code.single_commit",
                ts="2026-04-18T12:30:00Z",
                status="✅ OK",
                plan_paths=["docs/plans/one.md"],
                source_path="docs/code_reviews/one_post_fix.md",
            ),
            _trace_event(
                event_id="evt.green",
                event_type="review.doc.single_commit",
                ts="2026-04-18T13:00:00Z",
                status="✅ No blockers",
                plan_paths=["docs/plans/two.md"],
                source_path="docs/doc_reviews/two.md",
            ),
            _trace_event(
                event_id="evt.ambiguous",
                event_type="review.code.single_commit",
                ts="2026-04-18T14:00:00Z",
                status="✅ OK",
                plan_paths=["docs/plans/a.md", "docs/plans/b.md"],
                source_path="docs/code_reviews/ambiguous.md",
            ),
            {
                "schema_version": "review_receipt.v1",
                "event_id": "evt.audit",
                "event_type": "review.post_merge_audit",
                "ts": "2026-04-18T15:00:00Z",
                "trace_id": "N/A (why=test)",
                "span_id": "span.evt.audit",
                "parent_span_id": "N/A (why=test)",
                "source_family": "review_receipt",
                "source_path": "docs/reviews/audit.md",
                "source_root": "/tmp/planveyor-delivery-metrics",
                "payload": {"status": "✅ Done", "plan_paths": ["docs/plans/one.md"]},
            },
        ]
        rows = [
            _failure_row(
                event_id="evt.blocked",
                event_type="review.code.single_commit",
                ts="2026-04-18T10:00:00Z",
                failure_code="ROUTING_FAILURE",
                finding_ref="docs/code_reviews/one.md#B1",
            ),
            _failure_row(
                event_id="evt.green",
                event_type="review.doc.single_commit",
                ts="2026-04-18T13:00:00Z",
                failure_code="UNKNOWN",
                finding_ref="N/A (why=false positive)",
            ),
            _failure_row(
                event_id="evt.audit",
                event_type="review.post_merge_audit",
                ts="2026-04-18T15:00:00Z",
                failure_code="GOVERNANCE_BLOCK",
                finding_ref="docs/reviews/audit.md#A1",
                lineage_source="live_audit_matrix",
            ),
        ]

        metrics = MODULE.build_metrics(
            events,
            rows,
            generated_at="2026-04-18T20:00:00Z",
            trace_jsonl_path=".tmp/planveyor_trace_events.jsonl",
            attribution_jsonl_path=".tmp/planveyor_failure_attribution.jsonl",
            metrics_json_path=".tmp/planveyor_delivery_metrics.json",
            scorecard_path="docs/reviews/planveyor_delivery_scorecard.md",
        )

        self.assertEqual(metrics["inputs"]["failure_row_count_total"], 3)
        self.assertEqual(metrics["inputs"]["failure_row_count_counted"], 2)
        self.assertEqual(metrics["trace_coverage"]["failure_rows_excluded_positive_review_false_positive"], 1)
        self.assertEqual(metrics["trace_coverage"]["review_events_total"], 4)
        self.assertEqual(metrics["trace_coverage"]["review_events_decisive"], 4)
        self.assertEqual(metrics["trace_coverage"]["review_events_unit_eligible"], 3)
        self.assertEqual(metrics["trace_coverage"]["review_events_excluded_ambiguous_plan_paths"], 1)
        self.assertEqual(metrics["metrics"]["inner_loop_cycles"]["review_lanes_considered"], 2)
        self.assertEqual(metrics["metrics"]["inner_loop_cycles"]["review_events_considered"], 3)
        self.assertEqual(metrics["metrics"]["inner_loop_cycles"]["rework_lanes"], 1)
        self.assertEqual(metrics["metrics"]["first_pass_success"]["success_lanes"], 1)
        self.assertAlmostEqual(metrics["metrics"]["first_pass_success"]["rate"], 0.5)
        self.assertEqual(metrics["metrics"]["blocked_or_escalated"]["blocked_or_escalated_lanes"], 1)
        self.assertAlmostEqual(metrics["metrics"]["blocked_or_escalated"]["blocked_review_event_rate"], 1 / 3, places=4)
        self.assertEqual(metrics["metrics"]["blocked_or_escalated"]["governance_escalation_lanes"], 0)
        self.assertEqual(metrics["metrics"]["failure_distribution"]["by_failure_code"]["GOVERNANCE_BLOCK"], 1)
        self.assertEqual(metrics["metrics"]["review_findings"]["literal_finding_refs"], 2)
        self.assertEqual(metrics["metrics"]["review_findings"]["inferred_finding_refs"], 0)
        self.assertEqual(metrics["metrics"]["latency"]["supported_lanes"], 1)
        self.assertEqual(metrics["metrics"]["latency"]["median_review_loop_span_hours"], 2.5)

    def test_render_scorecard_keeps_coverage_confidence_and_omissions_explicit(self) -> None:
        metrics = MODULE.build_metrics(
            [
                _trace_event(
                    event_id="evt.green",
                    event_type="review.code.single_commit",
                    ts="2026-04-18T10:00:00Z",
                    status="✅ OK",
                    plan_paths=["docs/plans/live.md"],
                    source_path="docs/code_reviews/live.md",
                )
            ],
            [],
            generated_at="2026-04-18T20:00:00Z",
            trace_jsonl_path=".tmp/planveyor_trace_events.jsonl",
            attribution_jsonl_path=".tmp/planveyor_failure_attribution.jsonl",
            metrics_json_path=".tmp/planveyor_delivery_metrics.json",
            scorecard_path="docs/reviews/planveyor_delivery_scorecard.md",
        )

        rendered = MODULE.render_scorecard(metrics)

        self.assertIn("Coverage window", rendered)
        self.assertIn("generated summary", rendered)
        self.assertIn("Failure attribution", rendered)
        self.assertIn("Omitted metrics", rendered)
        self.assertIn("complexity_adjusted_throughput", rendered)
        self.assertIn("end_to_end_task_latency", rendered)

    def test_main_writes_json_and_markdown_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _write_jsonl(
                root / ".tmp/planveyor_trace_events.jsonl",
                [
                    _trace_event(
                        event_id="evt.green",
                        event_type="review.code.single_commit",
                        ts="2026-04-18T10:00:00Z",
                        status="✅ OK",
                        plan_paths=["docs/plans/live.md"],
                        source_path="docs/code_reviews/live.md",
                    )
                ],
            )
            _write_jsonl(root / ".tmp/planveyor_failure_attribution.jsonl", [])

            result = MODULE.main(["--root", str(root)])
            json_payload = json.loads((root / ".tmp/planveyor_delivery_metrics.json").read_text(encoding="utf-8"))
            markdown = (root / "docs/reviews/planveyor_delivery_scorecard.md").read_text(encoding="utf-8")

        self.assertEqual(result, 0)
        self.assertEqual(json_payload["schema_version"], "delivery_metrics.v1")
        self.assertEqual(json_payload["metrics"]["first_pass_success"]["success_lanes"], 1)
        self.assertIn("Delivery scorecard", markdown)
        self.assertIn("First-pass success", markdown)


if __name__ == "__main__":
    unittest.main()

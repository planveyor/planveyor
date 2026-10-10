from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("planqueue_metrics.py")
SPEC = importlib.util.spec_from_file_location("planqueue_metrics", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _write_log(path: Path, rows: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _write_state(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _state(*, queue_complete: bool = False, warning: bool = False) -> dict[str, object]:
    active_item: dict[str, object] = {
        "order": 2,
        "plan": "docs/plans/next.md",
        "state": "active",
        "runtime_class": None,
    }
    if warning:
        active_item["queue_activation_warning"] = "queue_activation_admission_blocked: fixture"
    return {
        "version": 1,
        "mode": "manual_args",
        "cursor": 1,
        "last_transition": {
            "kind": "advance" if not queue_complete else "queue_complete",
            "queue_complete": queue_complete,
        },
        "items": [
            {"order": 1, "plan": "docs/plans/done.md", "state": "done"},
            active_item,
        ],
    }


def _build(root: Path) -> dict[str, object]:
    return MODULE.build_metrics(
        root=root,
        log_path=root / ".planveyor.planqueue.log",
        state_path=root / ".planveyor.planqueue.json",
        json_out_path=root / ".tmp/planveyor_planqueue_health_metrics.json",
        markdown_out_path=root / ".tmp/planveyor_planqueue_health_scorecard.md",
        generated_at="2026-06-19T07:00:00Z",
    )


class PlanqueueMetricsTests(unittest.TestCase):
    def test_raw_judgment_annotation_without_authority_refs_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _write_log(
                root / ".planveyor.planqueue.log",
                [
                    "2026-06-19T00:00:00Z\tset\tmode=manual_args\titems=2",
                    "2026-06-19T00:01:00Z\tactivate\tplan=docs/plans/one.md\torder=1",
                    "2026-06-19T00:02:00Z\tcomplete\tplan=docs/plans/one.md\torder=1\tfinal_status=Done",
                    "2026-06-19T00:02:00Z\tadvance\tfrom_plan=docs/plans/one.md\tto_plan=docs/plans/two.md\torder=2",
                    "2026-06-19T00:03:00Z\tactivate\tplan=docs/plans/two.md\torder=2\toutcome=true_positive",
                    "2026-06-19T00:04:00Z\tstate_repair\treason=legacy_parent_resumed_transition",
                ],
            )
            _write_state(root / ".planveyor.planqueue.json", _state())

            metrics = _build(root)

        self.assertEqual(metrics["schema_version"], "planqueue_health_metrics.v1")
        self.assertEqual(metrics["event_totals"]["valid_rows"], 6)
        self.assertEqual(metrics["event_totals"]["by_event"]["activate"], 2)
        self.assertEqual(metrics["health"]["state_repair"]["count"], 1)
        self.assertEqual(metrics["health"]["transitions"]["advance"], 1)
        self.assertFalse(metrics["health"]["transitions"]["queue_complete_from_state"])
        self.assertEqual(metrics["health"]["current_state"]["active_plan"], "docs/plans/next.md")
        self.assertEqual(metrics["outcome_quality"]["annotated_rows"], 1)
        self.assertEqual(metrics["outcome_quality"]["invalid_annotation_rows"], 1)
        self.assertEqual(metrics["outcome_quality"]["invalid_annotation_reasons"], {"missing_authority_fields": 1})
        self.assertEqual(metrics["outcome_quality"]["true_positive_rate"]["status"], "unknown")
        self.assertEqual(metrics["outcome_quality"]["true_positive_rate"]["reason"], "no_valid_judgment_annotations")
        self.assertEqual(metrics["confidence"]["status"], "medium")

    def test_authority_backed_judgment_annotations_compute_rate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _write_log(
                root / ".planveyor.planqueue.log",
                [
                    "2026-06-19T00:01:00Z\tactivate\tplan=docs/plans/one.md\torder=1\toutcome=true_positive\tstamper_role=Reviewer\tevidence_ref=docs/code_reviews/one.md#B1\tsource_event_ref=queue-log:1\tevidence_state=fixed",
                    "2026-06-19T00:02:00Z\tactivate\tplan=docs/plans/two.md\torder=2\toutcome=false_positive\tstamper_role=Architect\tevidence_ref=docs/doc_reviews/two.md#S1\tsource_event_ref=queue-log:2\tevidence_state=no_live_blocker",
                ],
            )
            _write_state(root / ".planveyor.planqueue.json", _state())

            metrics = _build(root)

        self.assertEqual(metrics["outcome_quality"]["annotated_rows"], 2)
        self.assertEqual(metrics["outcome_quality"]["valid_annotation_rows"], 2)
        self.assertEqual(metrics["outcome_quality"]["invalid_annotation_rows"], 0)
        self.assertEqual(metrics["outcome_quality"]["by_valid_annotation"], {"false_positive": 1, "true_positive": 1})
        self.assertEqual(metrics["outcome_quality"]["true_positive_rate"]["status"], "computed")
        self.assertEqual(metrics["outcome_quality"]["true_positive_rate"]["value"], 0.5)
        self.assertEqual(metrics["confidence"]["status"], "high")

    def test_mechanical_and_known_unknown_annotations_are_valid_but_not_judgment_rate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _write_log(
                root / ".planveyor.planqueue.log",
                [
                    "2026-06-19T00:01:00Z\tactivate\tplan=docs/plans/one.md\torder=1\toutcome=fixed\tstamper_role=Reviewer\tevidence_ref=docs/code_reviews/one.md#B1\tsource_event_ref=queue-log:1\tevidence_state=fixed",
                    "2026-06-19T00:02:00Z\tactivate\tplan=docs/plans/two.md\torder=2\toutcome=unknown\tstamper_role=Owner\tevidence_ref=owner:answer-1\tsource_event_ref=queue-log:2\tevidence_state=unknown",
                ],
            )
            _write_state(root / ".planveyor.planqueue.json", _state())

            metrics = _build(root)

        self.assertEqual(metrics["outcome_quality"]["valid_annotation_rows"], 2)
        self.assertEqual(metrics["outcome_quality"]["known_unknown_rows"], 1)
        self.assertEqual(metrics["outcome_quality"]["true_positive_rate"]["status"], "unknown")
        self.assertEqual(metrics["outcome_quality"]["true_positive_rate"]["reason"], "no_valid_judgment_annotations")

    def test_unsupported_evidence_host_and_present_red_state_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _write_log(
                root / ".planveyor.planqueue.log",
                [
                    "2026-06-19T00:01:00Z\tactivate\tplan=docs/plans/one.md\torder=1\toutcome=true_positive\tstamper_role=Reviewer\tevidence_ref=chat:thread-1\tsource_event_ref=queue-log:1\tevidence_state=fixed",
                    "2026-06-19T00:02:00Z\tactivate\tplan=docs/plans/two.md\torder=2\toutcome=false_positive\tstamper_role=Reviewer\tevidence_ref=docs/code_reviews/two.md#B2\tsource_event_ref=queue-log:2\tevidence_state=live_blocker",
                ],
            )
            _write_state(root / ".planveyor.planqueue.json", _state())

            metrics = _build(root)

        self.assertEqual(metrics["outcome_quality"]["valid_annotation_rows"], 0)
        self.assertEqual(metrics["outcome_quality"]["invalid_annotation_rows"], 2)
        self.assertEqual(
            metrics["outcome_quality"]["invalid_annotation_reasons"],
            {
                "authoritative_evidence_red_or_inconsistent": 1,
                "unsupported_evidence_ref_host": 1,
            },
        )
        self.assertEqual(metrics["outcome_quality"]["true_positive_rate"]["status"], "unknown")

    def test_ambiguous_lineage_annotation_requires_human_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _write_log(
                root / ".planveyor.planqueue.log",
                [
                    "2026-06-19T00:01:00Z\tactivate\tplan=docs/plans/one.md\torder=1\toutcome=true_positive\tstamper_role=Reviewer\tevidence_ref=docs/code_reviews/one.md#B1\tsource_event_ref=queue-log:1\tevidence_state=fixed\tlineage_status=ambiguous",
                ],
            )
            _write_state(root / ".planveyor.planqueue.json", _state())

            metrics = _build(root)

        self.assertEqual(metrics["outcome_quality"]["invalid_annotation_rows"], 1)
        self.assertEqual(metrics["outcome_quality"]["invalid_annotation_reasons"], {"ambiguous_lineage": 1})
        self.assertEqual(metrics["outcome_quality"]["human_gate_rows"], 1)

    def test_missing_log_and_state_are_bounded_warning_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            metrics = _build(root)

        self.assertEqual(metrics["event_totals"]["valid_rows"], 0)
        self.assertFalse(metrics["inputs"]["log_exists"])
        self.assertFalse(metrics["inputs"]["state_exists"])
        self.assertEqual(metrics["outcome_quality"]["true_positive_rate"]["status"], "unknown")
        self.assertEqual(metrics["outcome_quality"]["true_positive_rate"]["reason"], "outcome_annotation_missing")
        self.assertEqual(metrics["confidence"]["status"], "medium")
        self.assertEqual(
            {item["code"] for item in metrics["confidence"]["diagnostics"]},
            {"log_missing", "state_missing"},
        )

    def test_malformed_rows_stops_and_state_warnings_degrade_confidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _write_log(
                root / ".planveyor.planqueue.log",
                [
                    "malformed-only",
                    "2026-06-19T00:01:00Z\tappend\trejected=2\tfield_without_equals",
                    "2026-06-19T00:02:00Z\tstop\treason=loop_escalation_recorded\tplan=docs/plans/one.md",
                    "2026-06-19T00:03:00Z\tstop\treason=queue_activation_admission_blocked\tplan=docs/plans/two.md",
                ],
            )
            _write_state(root / ".planveyor.planqueue.json", _state(warning=True))

            metrics = _build(root)

        self.assertEqual(metrics["event_totals"]["malformed_rows"], 1)
        self.assertEqual(metrics["event_totals"]["malformed_field_chunks"], 1)
        self.assertEqual(metrics["health"]["observed_admission"]["append_rejected_items"], 2)
        self.assertEqual(metrics["health"]["observed_admission"]["admission_or_blocker_stop_rows"], 1)
        self.assertEqual(metrics["health"]["stops"]["loop_stop_count"], 1)
        self.assertEqual(metrics["health"]["observed_admission"]["current_warning_candidates"], 1)
        self.assertEqual(metrics["confidence"]["status"], "medium")

    def test_queue_complete_with_open_items_is_visible_error_diagnostic(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _write_log(root / ".planveyor.planqueue.log", ["2026-06-19T00:01:00Z\tcomplete\tplan=docs/plans/one.md"])
            _write_state(root / ".planveyor.planqueue.json", _state(queue_complete=True))

            metrics = _build(root)

        self.assertTrue(metrics["health"]["transitions"]["queue_complete_from_state"])
        self.assertEqual(metrics["confidence"]["status"], "low")
        self.assertIn("queue_complete_with_open_items", {item["code"] for item in metrics["confidence"]["diagnostics"]})

    def test_render_scorecard_and_main_write_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _write_log(root / ".planveyor.planqueue.log", ["2026-06-19T00:01:00Z\tactivate\tplan=docs/plans/one.md"])
            _write_state(root / ".planveyor.planqueue.json", _state())

            result = MODULE.main(
                [
                    "--root",
                    str(root),
                    "--generated-at",
                    "2026-06-19T07:00:00Z",
                ]
            )
            json_payload = json.loads((root / ".tmp/planveyor_planqueue_health_metrics.json").read_text(encoding="utf-8"))
            markdown = (root / ".tmp/planveyor_planqueue_health_scorecard.md").read_text(encoding="utf-8")

        self.assertEqual(result, 0)
        self.assertEqual(json_payload["schema_version"], "planqueue_health_metrics.v1")
        self.assertEqual(json_payload["outcome_quality"]["missing_annotation_rows"], 1)
        self.assertEqual(json_payload["outcome_quality"]["true_positive_rate"]["status"], "unknown")
        self.assertIn("Planqueue health scorecard", markdown)
        self.assertIn("Outcome quality", markdown)
        self.assertIn("generated readback", markdown.lower())


if __name__ == "__main__":
    unittest.main()

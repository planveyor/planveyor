from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from textwrap import dedent


MODULE_PATH = Path(__file__).with_name("planveyor_failure_attribution.py")
SPEC = importlib.util.spec_from_file_location("planveyor_failure_attribution", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _trace_event(**payload: object) -> dict[str, object]:
    event = {
        "schema_version": "review_receipt.v1",
        "event_type": "review.artifact",
        "ts": "2026-04-18T15:00:00Z",
        "event_id": "evt.test",
        "trace_id": "trace-test",
        "span_id": "span.test",
        "parent_span_id": "N/A (why=test)",
        "source_family": "review_receipt",
        "source_path": "docs/code_reviews/live.md",
        "source_root": "/tmp/planveyor-failure-attribution",
        "payload": {},
    }
    event.update(payload)
    return event


class PlanveyorFailureAttributionTests(unittest.TestCase):
    def test_main_writes_review_blocker_row_from_live_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _write(
                root / ".tmp/planveyor_trace_events.jsonl",
                "\n".join(
                    [
                        json.dumps(
                            _trace_event(
                                event_type="review.code.single_commit",
                                source_path="docs/code_reviews/live.md",
                                source_root=str(root),
                                payload={
                                    "title": "Code review — single commit",
                                    "status": "❌ S1 Blocker(s)",
                                    "target": "COMMIT=current",
                                    "spec": "docs/plans/failure.md",
                                    "topic": "",
                                    "plan_paths": ["docs/plans/failure.md"],
                                    "blocker_ids": ["B1"],
                                },
                            ),
                            ensure_ascii=False,
                            sort_keys=True,
                        )
                    ]
                )
                + "\n",
            )
            _write(
                root / "docs/code_reviews/live.md",
                dedent(
                    """\
                    # Code review — single commit

                    **Date:** 18.04.2026 18:00 MSK
                    **Target:** COMMIT=current
                    **Spec:** docs/plans/failure.md
                    **Status:** ❌ S1 Blocker(s)

                    ## S1 Blocker
                    ### B1) Review-only scaffold шьёт неверный live artifact host
                    - Blocker ID: B1
                    - Current state: open
                    - Classification: same-contract reroute
                    - Primary owner gap: Coder
                    - Evidence refs: `docs/code_reviews/live.md#B1`, `docs/plans/failure.md`
                    """
                ),
            )

            result = MODULE.main(["--root", str(root)])
            rows = [json.loads(line) for line in (root / ".tmp/planveyor_failure_attribution.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]

        self.assertEqual(result, 0)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["payload"]["failure_code"], "ROUTING_FAILURE")
        self.assertEqual(row["payload"]["finding_ref"], "docs/code_reviews/live.md#B1")
        self.assertEqual(row["payload"]["primary_owner_gap"], "Coder")
        self.assertIn("docs/plans/failure.md", row["payload"]["evidence_refs"])

    def test_audit_matrix_maps_partial_sanity_to_reviewability_gap(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            event = _trace_event(
                event_type="review.post_merge_audit",
                source_path="docs/reviews/audit.md",
                source_root=str(root),
                payload={
                    "title": "Review: Post-merge audit — failure attribution",
                    "status": "✅ Done",
                    "topic": "failure attribution",
                    "plan_paths": ["docs/plans/failure.md"],
                },
            )
            _write(root / ".tmp/planveyor_trace_events.jsonl", json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
            _write(
                root / "docs/reviews/audit.md",
                dedent(
                    """\
                    # Review: Post-merge audit — failure attribution

                    **Date:** 18.04.2026 19:10 MSK
                    **Topic:** failure attribution
                    **Stage:** Stage 1 (post-merge docs hygiene)
                    **Status:** ✅ Done

                    ## Audit matrix (summary)

                    ### A1) Reviewability gap on merged trace bundle
                    - Blocker refs: `N/A (no live blocker lineage)`
                    - Code anchors: `scripts/planveyor_failure_attribution.py:1`
                    - Tests/smokes: `scripts/test_planveyor_failure_attribution.py`
                    - Docs: `docs/tools/owner_runbook_codex.md`
                    - Status: partial
                    - Notes (optional): Missing visual sanity evidence and docs lint follow-up.
                    """
                ),
            )

            rows = MODULE.derive_attribution_rows(MODULE._load_jsonl(root / ".tmp/planveyor_trace_events.jsonl"), [root])

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["payload"]["failure_code"], "REVIEWABILITY_GAP")
        self.assertEqual(row["payload"]["finding_ref"], "docs/reviews/audit.md#A1")
        self.assertEqual(row["payload"]["current_state"], "partial")
        self.assertIn("N/A (no live blocker lineage)", row["payload"]["evidence_refs"][0])

    def test_runtime_env_mixed_and_unknown_fallbacks_are_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            rows = [
                _trace_event(
                    event_type="run_receipt.manager_custom_pipeline",
                    source_family="run_receipt",
                    source_path=".planveyor.run_receipt.manager_custom_pipeline",
                    source_root=str(root),
                    payload={
                        "status": "failed",
                        "stop_reason": "OperationalError: connection refused to Postgres",
                        "result_artifact": "stdout receipt",
                    },
                ),
                _trace_event(
                    event_type="review.code.single_commit",
                    source_path="docs/code_reviews/mixed.md",
                    source_root=str(root),
                    payload={
                        "title": "Scope expansion and missing evidence",
                        "status": "❌ S1 Blocker(s)",
                        "target": "COMMIT=current",
                        "spec": "docs/plans/failure.md",
                        "blocker_ids": [],
                    },
                ),
                _trace_event(
                    event_type="review.code.single_commit",
                    source_path="docs/code_reviews/unknown.md",
                    source_root=str(root),
                    payload={
                        "title": "General attention needed",
                        "status": "❌ S1 Blocker(s)",
                        "target": "COMMIT=current",
                        "spec": "docs/plans/failure.md",
                        "blocker_ids": [],
                    },
                ),
            ]
            _write(root / ".tmp/planveyor_trace_events.jsonl", "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n")

            derived = MODULE.derive_attribution_rows(MODULE._load_jsonl(root / ".tmp/planveyor_trace_events.jsonl"), [root])
            codes = [row["payload"]["failure_code"] for row in derived]

        self.assertIn("RUNTIME_ENV", codes)
        self.assertIn("MIXED", codes)
        self.assertIn("UNKNOWN", codes)

    def test_empty_trace_input_still_writes_empty_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _write(root / ".tmp/planveyor_trace_events.jsonl", "")
            result = MODULE.main(["--root", str(root)])
            output = (root / ".tmp/planveyor_failure_attribution.jsonl").read_text(encoding="utf-8")

        self.assertEqual(result, 0)
        self.assertEqual(output, "")


if __name__ == "__main__":
    unittest.main()

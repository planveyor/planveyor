#!/usr/bin/env python3
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from textwrap import dedent
from typing import Iterator
from unittest import mock

try:
    from scripts.test_contract_authority_support import AuthorityFixture, commit_all, write
except ModuleNotFoundError:
    from test_contract_authority_support import AuthorityFixture, commit_all, write


MODULE_PATH = Path(__file__).with_name("planveyor_trace_extractor.py")
SPEC = importlib.util.spec_from_file_location("planveyor_trace_extractor", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@contextmanager
def _local_time_zone(name: str) -> Iterator[None]:
    """Pin the process time zone so local-time expectations do not depend on the machine."""

    try:
        with mock.patch.dict(os.environ, {"TZ": name}):
            time.tzset()
            yield
    finally:
        time.tzset()


class PlanveyorTraceExtractorTests(unittest.TestCase):
    def test_extracts_run_receipts_collab_logs_and_review_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _write(
                root / ".planveyor.run_receipt.reviewer",
                dedent(
                    """\
                    schema_version=runtime_receipt.v1
                    event_type=run_receipt.reviewer
                    ts=2026-04-18T15:00:00Z
                    thread_id=thread-review-123
                    parent_thread_id=parent-thread-321
                    plan_path=docs/plans/fixture.md
                    started_at=2026-04-18T14:58:00Z
                    finished_at=2026-04-18T15:00:00Z
                    result_artifact=docs/code_reviews/260418_fixture.md
                    """
                ),
            )
            _write(
                root / ".planveyor.role_runs" / "role-run-123.json",
                json.dumps(
                    {
                        "schema_version": "role_execution_receipt.v1",
                        "run_id": "role-run-123",
                        "role": "reviewer",
                        "session_key": "reviewer_code_risk",
                        "wrapper": "planveyor_reviewer_code_risk",
                        "runner_id": "claude",
                        "runner_alias": "claude",
                        "profile": "direct_child",
                        "model": "fixture-claude-model",
                        "configured_model_id": "fixture-claude-model",
                        "observable_model_id": "N/A (why=provider model metadata not exposed)",
                        "model_id_state": "configured_explicit",
                        "sid": "reviewer-risk-sid",
                        "sid_before": "reviewer-risk-sid",
                        "sid_after": "reviewer-risk-sid",
                        "session_action_requested": "resume",
                        "session_pointer_relation": "same",
                        "process_start_outcome": "started",
                        "session_reset_performed": False,
                        "cli_process_mode": "one_shot",
                        "process_persistent": False,
                        "provider_error_class": "not_applicable",
                        "provider_http_status": "not_applicable",
                        "provider_error_code": "not_applicable",
                        "provider_retryability": "not_applicable",
                        "child_session": True,
                        "target_plan": "docs/plans/fixture_role_run.md",
                        "pre_status": "**Status:** Ready for Review",
                        "post_status": "**Status:** Ready for Review",
                        "exit_code": 0,
                        "timeout_seconds": 3600,
                        "duration_seconds": 30,
                        "elapsed_seconds": 30,
                        "timed_out": False,
                        "terminated_by_timeout": False,
                        "started_at": "2026-04-18T14:59:00Z",
                        "finished_at": "2026-04-18T14:59:30Z",
                        "receipt_written_at": "2026-04-18T14:59:30Z",
                        "result_artifact": "docs/code_reviews/260418_fixture_role_run.md",
                        "state": "success",
                        "success": True,
                        "interrupted": False,
                        "non_green_reason": "",
                    },
                    ensure_ascii=False,
                ),
            )
            _write(
                root / ".planveyor.role_runs" / "role-run-legacy.json",
                json.dumps(
                    {
                        "schema_version": "role_execution_receipt.v1",
                        "run_id": "role-run-legacy",
                        "role": "planner",
                        "session_key": "planner",
                        "target_plan": "docs/plans/fixture_legacy_role_run.md",
                        "receipt_written_at": "2026-04-18T14:58:30Z",
                        "state": "success",
                        "business_work_executed": True,
                    },
                    ensure_ascii=False,
                ),
            )
            _write(
                root / ".planveyor.role_runs" / "role-run-legacy-false.json",
                json.dumps(
                    {
                        "schema_version": "role_execution_receipt.v1",
                        "run_id": "role-run-legacy-false",
                        "role": "coder",
                        "session_key": "coder",
                        "target_plan": "docs/plans/fixture_legacy_role_run.md",
                        "receipt_written_at": "2026-04-18T14:58:31Z",
                        "state": "failed",
                        "business_work_executed": False,
                    },
                    ensure_ascii=False,
                ),
            )
            _write(
                root / ".planveyor.collab.agent.coder.log",
                "18.04.2026 18:04\tthread-collab-1\trespawn\tplanveyor_manager_collab_tui;prev=old\n",
            )
            _write(
                root / "docs/code_reviews/260418_fixture.md",
                dedent(
                    """\
                    # Code review — single commit

                    **Date:** 18.04.2026 18:00
                    **Target:** COMMIT=current (PLAN=`docs/plans/fixture.md`)
                    **Spec:** docs/plans/fixture.md
                    **Status:** ✅ OK

                    ОК: fixture review artifact.
                    """
                ),
            )
            _write(
                root / "docs/code_reviews/260418_fixture_role_run.md",
                dedent(
                    """\
                    # Code review — single commit

                    **Date:** 18.04.2026 17:59
                    **Target:** COMMIT=current (PLAN=`docs/plans/fixture_role_run.md`)
                    **Spec:** docs/plans/fixture_role_run.md
                    **Status:** ✅ OK

                    ОК: fixture role-run review artifact.
                    """
                ),
            )
            _write(
                root / "docs/reviews/260418_post_merge_audit_fixture.md",
                dedent(
                    """\
                    # Review: Post-merge audit — fixture

                    **Date:** 18.04.2026 18:10 MSK
                    **Topic:** fixture
                    **Status:** ✅ Done

                    ## Follow-ups
                    - none
                    """
                ),
            )

            events = MODULE.extract_root(root)

        self.assertEqual(len(events), 8)
        by_family = {event["source_family"]: [] for event in events}
        for event in events:
            by_family.setdefault(event["source_family"], []).append(event)

        run_receipt = by_family["run_receipt"][0]
        self.assertEqual(run_receipt["event_type"], "run_receipt.reviewer")
        self.assertEqual(run_receipt["trace_id"], "thread-review-123")
        self.assertEqual(run_receipt["schema_version"], "runtime_receipt.v1")

        role_execution = next(
            event for event in by_family["role_execution_receipt"] if event["trace_id"] == "role-run-123"
        )
        self.assertEqual(role_execution["event_type"], "role_execution.reviewer_code_risk")
        self.assertEqual(role_execution["trace_id"], "role-run-123")
        self.assertEqual(role_execution["schema_version"], "role_execution_receipt.v1")
        self.assertEqual(role_execution["payload"]["session_key"], "reviewer_code_risk")
        self.assertEqual(role_execution["payload"]["runner_alias"], "claude")
        self.assertEqual(role_execution["payload"]["configured_model_id"], "fixture-claude-model")
        self.assertEqual(role_execution["payload"]["observable_model_id"], "N/A (why=provider model metadata not exposed)")
        self.assertEqual(role_execution["payload"]["model_id_state"], "configured_explicit")
        self.assertEqual(role_execution["payload"]["elapsed_seconds"], 30)
        self.assertEqual(role_execution["payload"]["duration_seconds"], 30)
        self.assertFalse(role_execution["payload"]["terminated_by_timeout"])
        self.assertFalse(role_execution["payload"]["timed_out"])
        self.assertEqual(role_execution["payload"]["session_action_requested"], "resume")
        self.assertEqual(role_execution["payload"]["session_pointer_relation"], "same")
        self.assertEqual(role_execution["payload"]["process_start_outcome"], "started")
        self.assertFalse(role_execution["payload"]["session_reset_performed"])
        self.assertEqual(role_execution["payload"]["cli_process_mode"], "one_shot")
        self.assertFalse(role_execution["payload"]["process_persistent"])
        self.assertEqual(role_execution["payload"]["provider_error_class"], "not_applicable")
        self.assertEqual(role_execution["payload"]["provider_http_status"], "not_applicable")
        self.assertEqual(role_execution["payload"]["provider_error_code"], "not_applicable")
        self.assertEqual(role_execution["payload"]["provider_retryability"], "not_applicable")
        self.assertNotIn("business_work_executed", role_execution["payload"])
        self.assertNotIn("business_work_state", role_execution["payload"])

        legacy_role_execution = next(
            event for event in by_family["role_execution_receipt"] if event["trace_id"] == "role-run-legacy"
        )
        self.assertIs(legacy_role_execution["payload"]["business_work_executed"], True)
        legacy_false_role_execution = next(
            event
            for event in by_family["role_execution_receipt"]
            if event["trace_id"] == "role-run-legacy-false"
        )
        self.assertIs(legacy_false_role_execution["payload"]["business_work_executed"], False)
        self.assertNotIn("business_work_state", legacy_false_role_execution["payload"])
        for field in (
            "session_action_requested",
            "session_pointer_relation",
            "process_start_outcome",
            "session_reset_performed",
            "cli_process_mode",
            "process_persistent",
            "provider_error_class",
            "provider_http_status",
            "provider_error_code",
            "provider_retryability",
        ):
            self.assertNotIn(field, legacy_role_execution["payload"])

        collab = by_family["collab_agent_log"][0]
        self.assertEqual(collab["event_type"], "collab_agent.respawn")
        self.assertEqual(collab["trace_id"], "thread-collab-1")
        self.assertIn("prev=old", collab["payload"]["note"])
        self.assertTrue(str(collab["ts"]).endswith("Z"))

        review_events = by_family["review_receipt"]
        code_review = next(item for item in review_events if item["source_path"] == "docs/code_reviews/260418_fixture.md")
        self.assertEqual(code_review["event_type"], "review.code.single_commit")
        self.assertEqual(code_review["trace_id"], "thread-review-123")
        self.assertEqual(code_review["payload"]["trace_match"], "result_artifact")

        role_run_review = next(item for item in review_events if item["source_path"] == "docs/code_reviews/260418_fixture_role_run.md")
        self.assertEqual(role_run_review["trace_id"], "role-run-123")
        self.assertEqual(role_run_review["payload"]["trace_match"], "result_artifact")

        audit_review = next(item for item in review_events if item["source_path"].startswith("docs/reviews/"))
        self.assertEqual(audit_review["event_type"], "review.post_merge_audit")
        self.assertTrue(str(audit_review["trace_id"]).startswith("N/A (why="))

    def test_timestamps_read_local_offsets_and_preserve_legacy_moscow_instants(self) -> None:
        def normalized(raw: str) -> str:
            return MODULE._parse_timestamp(raw)[0]

        for zone in ("Asia/Tokyo", "UTC"):
            with self.subTest(zone=zone), _local_time_zone(zone):
                # Engine stamps carry the numeric offset of the local zone.
                self.assertEqual(normalized("18.04.2026 18:10 +0300"), "2026-04-18T15:10:00Z")
                self.assertEqual(normalized("18.04.2026 18:10:30 -0430"), "2026-04-18T22:40:30Z")
                self.assertEqual(normalized("2026-04-18 18:10 +0300"), "2026-04-18T15:10:00Z")
                self.assertEqual(normalized("18.04.2026 18:10:00 +0900"), "2026-04-18T09:10:00Z")
                self.assertEqual(normalized("2026-04-18T09:10:00Z"), "2026-04-18T09:10:00Z")
                self.assertEqual(normalized("2026-04-18T18:10:00+09:00"), "2026-04-18T09:10:00Z")
                # Legacy stamps keep their fixed +03:00 offset on any machine.
                self.assertEqual(normalized("18.04.2026 18:10 MSK"), "2026-04-18T15:10:00Z")
                self.assertEqual(normalized("18.04.2026 18:10:00 MSK"), "2026-04-18T15:10:00Z")
                self.assertEqual(normalized("18.04.2026 18:10:00 (Europe/Moscow)"), "2026-04-18T15:10:00Z")
                self.assertEqual(normalized("2026-04-18 18:10 MSK"), "2026-04-18T15:10:00Z")
                # The old collab writer had no offset; its instant must not depend on the reader.
                self.assertEqual(normalized("18.04.2026 18:10:00"), "2026-04-18T15:10:00Z")
                self.assertEqual(normalized("2026-04-18T18:10:00"), "2026-04-18T15:10:00Z")
                self.assertEqual(normalized("18.04.2026 18:10"), "2026-04-18T15:10:00Z")

    def test_legacy_collab_event_and_span_ids_stay_stable_across_reader_timezones(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            path = root / ".planveyor.collab.agent.coder.log"
            legacy = "18.04.2026 18:10:00\tlegacy-sid\tspawn\tfixture\n"
            _write(path, legacy)
            expected_event_suffix = "coder_2026-04-18t15_10_00z_spawn_legacy-sid"
            for zone in ("UTC", "Asia/Tokyo"):
                with self.subTest(zone=zone), _local_time_zone(zone):
                    event = MODULE._collab_log_events(path, root)[0]
                    self.assertEqual(event["ts"], "2026-04-18T15:10:00Z")
                    self.assertEqual(event["event_id"], f"evt.collab_agent.{expected_event_suffix}")
                    self.assertEqual(event["span_id"], f"span.collab_agent.{expected_event_suffix}")
                    self.assertEqual(path.read_text(encoding="utf-8"), legacy)

    def test_public_collab_writer_parser_and_display_follow_local_offset(self) -> None:
        with AuthorityFixture(identity="timezone-fixture") as fixture:
            entry = write(
                fixture.runtime_root, "bin/planveyor",
                (MODULE_PATH.parent.parent / "bin" / "planveyor").read_bytes(), executable=True,
            )
            commit_all(fixture.runtime_root, "public timezone fixture entry")
            fixture.activate_local((), required_runtime_api=(5, 5))

            def run(zone: str, *arguments: str) -> subprocess.CompletedProcess[str]:
                environment = fixture.environment()
                environment["TZ"] = zone
                result = subprocess.run(
                    [str(entry), "--project", str(fixture.target_root), *arguments],
                    cwd=fixture.target_root, env=environment, text=True, capture_output=True,
                    check=False, timeout=60,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                return result

            log = fixture.target_root / ".planveyor.collab.agent.coder.log"
            for writer_zone, offset in (("UTC", "+0000"), ("Asia/Tokyo", "+0900")):
                with self.subTest(writer_zone=writer_zone):
                    run(writer_zone, "planveyor_collab_state_write_alive", "coder", "/root/coder_terra_ultra_v2", "spawn", "timezone fixture")
                    raw_stamp = log.read_text(encoding="utf-8").splitlines()[-1].split("\t")[0]
                    self.assertTrue(raw_stamp.endswith(f" {offset}"), raw_stamp)
                    instant = datetime.strptime(raw_stamp, "%d.%m.%Y %H:%M:%S %z")
                    state = fixture.target_root / ".planveyor.collab.agent.coder"
                    state_stamp = state.read_text(encoding="utf-8").splitlines()[0][2:]
                    self.assertTrue(state_stamp.endswith(f" {offset}"), state_stamp)
                    for reader_zone in ("UTC", "Asia/Tokyo"):
                        with self.subTest(reader_zone=reader_zone), _local_time_zone(reader_zone):
                            parsed = MODULE._collab_log_events(log, fixture.target_root)[-1]
                            self.assertEqual(parsed["ts"], instant.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
                            display = run(reader_zone, "planveyor_show_collab", "--compact")
                            self.assertIn(instant.astimezone().strftime("%d.%m %H:%M"), display.stdout)

            stamp = "18.04.2026 18:10:00"
            write(fixture.target_root, ".planveyor.collab.agent.coder", f"# {stamp}\n/root/coder_terra_ultra_v2\n")
            write(fixture.target_root, ".planveyor.collab.agent.coder.log", f"{stamp}\t/root/coder_terra_ultra_v2\tspawn\ttimezone fixture\n")
            for zone, short in (("UTC", "18.04 15:10"), ("Asia/Tokyo", "19.04 00:10")):
                with self.subTest(stamp=stamp, reader_zone=zone):
                    self.assertIn(short, run(zone, "planveyor_show_collab", "--compact").stdout)

    def test_empty_root_still_writes_jsonl_and_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            jsonl_out = root / ".tmp/trace.jsonl"
            sqlite_out = root / ".tmp/trace.sqlite"

            result = MODULE.main(
                [
                    "--root",
                    str(root),
                    "--jsonl-out",
                    str(jsonl_out),
                    "--sqlite-out",
                    str(sqlite_out),
                ]
            )

            self.assertEqual(result, 0)
            self.assertEqual(jsonl_out.read_text(encoding="utf-8"), "")
            self.assertTrue(sqlite_out.exists())
            conn = sqlite3.connect(sqlite_out)
            try:
                count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            finally:
                conn.close()

        self.assertEqual(count, 0)

    def test_sqlite_index_builds_from_jsonl_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            jsonl_out = root / ".tmp/planveyor_trace_events.jsonl"
            sqlite_out = root / ".tmp/planveyor_trace_index.sqlite"
            _write(
                root / ".planveyor.run_receipt.manager_custom_pipeline",
                dedent(
                    """\
                    thread_id=thread-manager-1
                    plan_path=docs/plans/root.md
                    started_at=2026-04-18T14:00:00Z
                    finished_at=2026-04-18T14:05:00Z
                    """
                ),
            )

            events = MODULE.extract_root(root)
            MODULE._write_jsonl(jsonl_out, events)
            for path in root.glob(".planveyor.run_receipt.*"):
                path.unlink()

            inserted = MODULE.build_sqlite_index(jsonl_out, sqlite_out)

            conn = sqlite3.connect(sqlite_out)
            try:
                row = conn.execute("SELECT event_type, trace_id FROM events").fetchone()
            finally:
                conn.close()

        self.assertEqual(inserted, 1)
        self.assertEqual(row, ("run_receipt.manager_custom_pipeline", "thread-manager-1"))

    def test_plan_path_match_recovers_review_trace_id_when_result_artifact_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _write(
                root / ".planveyor.run_receipt.reviewer",
                dedent(
                    """\
                    thread_id=thread-from-plan
                    plan_path=docs/plans/another_fixture.md
                    started_at=2026-04-18T12:00:00Z
                    finished_at=2026-04-18T12:01:00Z
                    result_artifact=stdout receipt
                    """
                ),
            )
            _write(
                root / "docs/code_reviews/260418_another_fixture.md",
                dedent(
                    """\
                    # Code review — single commit

                    **Date:** 18.04.2026 15:01
                    **Target:** COMMIT=current (PLAN=`docs/plans/another_fixture.md`)
                    **Spec:** docs/plans/another_fixture.md
                    **Status:** ✅ OK
                    """
                ),
            )

            events = MODULE.extract_root(root)

        review_event = next(item for item in events if item["source_family"] == "review_receipt")
        self.assertEqual(review_event["trace_id"], "thread-from-plan")
        self.assertEqual(review_event["payload"]["trace_match"], "plan_path:docs/plans/another_fixture.md")


if __name__ == "__main__":
    unittest.main()

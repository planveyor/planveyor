#!/usr/bin/env python3
"""Tests for merge_range_verdict_digest."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parent
MODULE_PATH = SCRIPT_DIR / "merge_range_verdict_digest.py"
SPEC = importlib.util.spec_from_file_location("merge_range_verdict_digest", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

import range_review_risk_packet_schema_contract


BASE = "a" * 40
HEAD = "b" * 40
BASE7 = BASE[:7]
HEAD7 = HEAD[:7]


class MergeRangeVerdictDigestTests(unittest.TestCase):
    def test_risk_packet_schema_version_uses_shared_contract(self) -> None:
        self.assertEqual(
            MODULE.RISK_PACKET_SCHEMA_VERSION,
            range_review_risk_packet_schema_contract.RANGE_REVIEW_RISK_PACKET_SCHEMA_VERSION,
        )
        self.assertEqual(MODULE.RISK_PACKET_SCHEMA_VERSION, "range_review_risk_packet.v1")

    def _write(self, root: Path, rel: str, body: str = "ok\n") -> Path:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    def _host_paths(self, root: Path) -> dict[str, str]:
        paths = {
            "review_artifact": "docs/code_reviews/260617_2145_review.md",
            "packetization_report": f"docs/reviews/260617_2145_packetization_gate_range_{BASE7}_{HEAD7}.md",
            "post_merge_audit": f"docs/reviews/260617_2145_post_merge_audit_range_{BASE7}_{HEAD7}.md",
            "operational_receipt": f"docs/reviews/260617_2145_post_merge_operational_receipt_range_{BASE7}_{HEAD7}.md",
            "ready_to_push_closeout": f"docs/reviews/260617_2145_ready_to_push_closeout_range_{BASE7}_{HEAD7}.md",
        }
        for rel in paths.values():
            self._write(root, rel, "**Status:** ✅ Done\n")
        self._write(root, ".planveyor.merge_tracker.md", "# tracker\n")
        return paths

    def _risk_payload(
        self,
        paths: dict[str, str],
        *,
        packet_status: str = "ok",
        review_status: str = "✅ Done",
        live_blockers: list[dict[str, str]] | None = None,
        historical_blockers: list[dict[str, str]] | None = None,
        closure_artifacts: list[dict[str, str]] | None = None,
    ) -> dict[str, object]:
        return {
            "schema_version": "range_review_risk_packet.v1",
            "packet_status": packet_status,
            "range_id": f"{BASE7}_{HEAD7}",
            "range": f"{BASE}..{HEAD}",
            "base": BASE,
            "head": HEAD,
            "target_snapshot": f"RANGE={BASE}..{HEAD} (EXCLUDE_DOCS=0)",
            "live_blockers": live_blockers or [],
            "historical_blockers": historical_blockers or [],
            "closure_artifacts": closure_artifacts or [],
            "residual_risks": [],
            "truth_hosts": {
                "review_artifact": {"path": paths["review_artifact"], "status": review_status},
                "packetization_report": {"path": paths["packetization_report"], "status": "Done"},
                "post_merge_audit": {"path": paths["post_merge_audit"], "status": "✅ Done"},
                "operational_receipt": {"path": paths["operational_receipt"], "status": "✅ Done"},
                "ready_to_push_closeout": {"path": paths["ready_to_push_closeout"], "status": "✅ Done"},
            },
        }

    def _write_risk_packet(
        self,
        root: Path,
        payload: dict[str, object],
        *,
        suffix: str = "",
        status: str = "✅ Done",
    ) -> Path:
        path = root / "docs" / "reviews" / f"260617_2145{suffix}_risk_packet_range_{BASE7}_{HEAD7}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(
                [
                    f"**Status:** {status}",
                    "",
                    "## Risk packet JSON",
                    "",
                    "```json",
                    json.dumps({"risk_packet": payload}, indent=2),
                    "```",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return path

    def _green_report(
        self,
        paths: dict[str, str],
        *,
        status: str = "ok",
        errors: list[dict[str, str]] | None = None,
    ) -> dict[str, object]:
        return {
            "status": status,
            "errors": errors or [],
            "range": {
                "base": BASE,
                "head": HEAD,
                "range": f"{BASE}..{HEAD}",
                "base_short": BASE7,
                "head_short": HEAD7,
            },
            "tracker": {
                "path": ".planveyor.merge_tracker.md",
                "current_step": "step:ready_to_push",
                "completed_steps": [
                    "step:review_range",
                    "step:packetization_gate",
                    "step:ready_to_push",
                ],
                "steps": [],
            },
            "artifacts": [
                {
                    "kind": "packetization_gate",
                    "path": paths["packetization_report"],
                    "status": "✅ Done",
                    "status_final": True,
                    "required": True,
                    "git_state": "tracked",
                    "active_candidate": True,
                },
                {
                    "kind": "post_merge_operational_receipt",
                    "path": paths["operational_receipt"],
                    "status": "✅ Done",
                    "status_final": True,
                    "required": True,
                    "git_state": "tracked",
                    "active_candidate": True,
                },
                {
                    "kind": "ready_to_push_closeout_receipt",
                    "path": paths["ready_to_push_closeout"],
                    "status": "✅ Done",
                    "status_final": True,
                    "required": True,
                    "git_state": "tracked",
                    "active_candidate": True,
                },
            ],
            "packetization_gate": {
                "active_packetization_report": paths["packetization_report"],
                "blocking_rows_count": 0,
                "draft_packets_created_count": 0,
            },
            "followups_lane_reconciliation": {
                "harvest_file_followups_result": "NO FOLLOWUPS",
                "harvest_file_followups_count": 0,
                "range_triage_mode": "range",
                "range_append_new": 0,
                "range_merge_source": 11,
                "range_possible_duplicate": 0,
                "range_route_fallback": 0,
                "range_unparsed_bullets": 23,
                "range_unresolved_append_new": 0,
                "range_unresolved_possible_duplicate": 0,
                "range_unresolved_route_fallback": 0,
                "range_unresolved_unparsed_bullets": 23,
                "manual_decision_ref": (
                    f"docs/followups/260617_2145_followups_range_{BASE7}_{HEAD7}.md"
                ),
                "already_tracked_ref": "docs/followups/process_followups_master.md",
                "owner_summary": (
                    "file-lane=NO FOLLOWUPS (0); range-lane apply append_new=0, "
                    "possible_duplicate=0, route_fallback=0, unparsed_bullets=23; "
                    "triage_mode=range; unresolved=23"
                ),
            },
            "followups_triage_launch_receipt": {
                "index_rebuild": {
                    "status": "ok",
                    "readback_status": "ok",
                    "index_path": "docs/followups/index.md",
                },
            },
            "process_improvements_open_summary": {
                "lane_status": "separate",
                "counts_by_raw_status": {
                    "open": 0,
                    "triaged": 0,
                    "promoted": 0,
                },
            },
            "archive_snapshot": {
                "status": "ok",
                "readback_status": "ok",
                "manifest_path": "docs/_meta/archive_snapshots/current/manifest.json",
                "artifact_path": "docs/_meta/archive_snapshots/current/docs_archive.tar.zst",
            },
            "ready_to_push_terminal_proof": {
                "state": "terminal_ready_to_push_proof",
                "path": paths["ready_to_push_closeout"],
                "final_bundle_status": "ok",
                "pending_owner_gate": "git push",
            },
        }

    def _run_json(self, root: Path, *args: str) -> tuple[int, dict[str, object]]:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            rc = MODULE.main(["--repo-root", str(root), "--format", "json", *args])
        parsed = json.loads(stdout.getvalue())
        return rc, parsed["merge_range_verdict_digest"]

    def _run_plain(self, root: Path, *args: str) -> tuple[int, str]:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            rc = MODULE.main(["--repo-root", str(root), "--format", "plain", *args])
        return rc, stdout.getvalue()

    def test_production_shape_packetization_status_uses_matching_truth_host(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._host_paths(root)
            self._write_risk_packet(root, self._risk_payload(paths))
            report = self._green_report(paths)
            with mock.patch.object(MODULE.merge_bundle_report, "build_report", return_value=report):
                rc, digest = self._run_json(root)

        self.assertEqual(rc, 0)
        self.assertEqual(digest["schema_version"], "merge_range_verdict_digest.v1")
        self.assertEqual(digest["digest_status"], "ok")
        self.assertEqual(digest["pending_owner_gate"], "git push")
        self.assertNotIn("status", report["packetization_gate"])
        self.assertEqual(
            digest["active_packetization_report"]["path"],
            f"docs/reviews/260617_2145_packetization_gate_range_{BASE7}_{HEAD7}.md",
        )
        self.assertEqual(digest["active_packetization_report"]["gate_status"], "Done")
        self.assertEqual(
            digest["truth_hosts"]["review_artifact"]["path"],
            "docs/code_reviews/260617_2145_review.md",
        )
        self.assertEqual(digest["process_improvements_state"]["open_count"], 0)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._host_paths(root)
            risk_packet = self._write_risk_packet(root, self._risk_payload(paths))
            report = self._green_report(paths)
            with mock.patch.object(MODULE.merge_bundle_report, "build_report", return_value=report):
                rc, plain = self._run_plain(root, "--risk-packet", str(risk_packet))
        self.assertEqual(rc, 0)
        self.assertIn("truth_hosts:", plain)
        self.assertIn("review_artifact: docs/code_reviews/260617_2145_review.md", plain)
        self.assertTrue(
            {
                "active_packetization_report.gate_status: Done",
                "active_packetization_report.blocking_rows_count: 0",
                "active_packetization_report.draft_packets_created_count: 0",
            }.issubset(set(plain.splitlines()))
        )

    def test_production_shape_followups_projection_preserves_counts_refs_and_unresolved_total(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._host_paths(root)
            risk_packet = self._write_risk_packet(root, self._risk_payload(paths))
            report = self._green_report(paths)
            with mock.patch.object(MODULE.merge_bundle_report, "build_report", return_value=report):
                rc, digest = self._run_json(root, "--risk-packet", str(risk_packet))

        self.assertEqual(rc, 0)
        self.assertEqual(digest["digest_status"], "ok")
        followups_state = digest["followups_state"]
        self.assertEqual(
            {
                key: followups_state[key]
                for key in (
                    "lane_status",
                    "launch_receipt_status",
                    "source",
                    "owner_summary",
                    "harvest_file_followups_result",
                    "harvest_file_followups_count",
                    "range_triage_mode",
                    "range_append_new",
                    "range_merge_source",
                    "range_possible_duplicate",
                    "range_route_fallback",
                    "range_unparsed_bullets",
                    "range_unresolved_append_new",
                    "range_unresolved_possible_duplicate",
                    "range_unresolved_route_fallback",
                    "range_unresolved_unparsed_bullets",
                    "unresolved_total",
                    "manual_decision_ref",
                    "already_tracked_ref",
                    "index_rebuild_status",
                    "index_readback_status",
                    "index_path",
                )
            },
            {
                "lane_status": "reconciled",
                "launch_receipt_status": "ok",
                "source": "merge_bundle_report.followups_lane_reconciliation",
                "owner_summary": (
                    "file-lane=NO FOLLOWUPS (0); range-lane apply append_new=0, "
                    "possible_duplicate=0, route_fallback=0, unparsed_bullets=23; "
                    "triage_mode=range; unresolved=23"
                ),
                "harvest_file_followups_result": "NO FOLLOWUPS",
                "harvest_file_followups_count": 0,
                "range_triage_mode": "range",
                "range_append_new": 0,
                "range_merge_source": 11,
                "range_possible_duplicate": 0,
                "range_route_fallback": 0,
                "range_unparsed_bullets": 23,
                "range_unresolved_append_new": 0,
                "range_unresolved_possible_duplicate": 0,
                "range_unresolved_route_fallback": 0,
                "range_unresolved_unparsed_bullets": 23,
                "unresolved_total": 23,
                "manual_decision_ref": (
                    f"docs/followups/260617_2145_followups_range_{BASE7}_{HEAD7}.md"
                ),
                "already_tracked_ref": "docs/followups/process_followups_master.md",
                "index_rebuild_status": "ok",
                "index_readback_status": "ok",
                "index_path": "docs/followups/index.md",
            },
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._host_paths(root)
            risk_packet = self._write_risk_packet(root, self._risk_payload(paths))
            report = self._green_report(paths)
            with mock.patch.object(MODULE.merge_bundle_report, "build_report", return_value=report):
                rc, plain = self._run_plain(root, "--risk-packet", str(risk_packet))
        self.assertEqual(rc, 0)
        self.assertTrue(
            {
                "followups_state: reconciled",
                (
                    "followups_state.owner_summary: file-lane=NO FOLLOWUPS (0); "
                    "range-lane apply append_new=0, possible_duplicate=0, "
                    "route_fallback=0, unparsed_bullets=23; triage_mode=range; "
                    "unresolved=23"
                ),
                "followups_state.launch_receipt_status: ok",
                "followups_state.harvest_file_followups_result: NO FOLLOWUPS",
                "followups_state.harvest_file_followups_result: NO FOLLOWUPS",
                "followups_state.harvest_file_followups_count: 0",
                "followups_state.range_triage_mode: range",
                "followups_state.range_append_new: 0",
                "followups_state.range_merge_source: 11",
                "followups_state.range_possible_duplicate: 0",
                "followups_state.range_route_fallback: 0",
                "followups_state.range_unparsed_bullets: 23",
                "followups_state.range_unresolved_append_new: 0",
                "followups_state.range_unresolved_possible_duplicate: 0",
                "followups_state.range_unresolved_route_fallback: 0",
                "followups_state.range_unresolved_unparsed_bullets: 23",
                "followups_state.unresolved_total: 23",
                (
                    "followups_state.manual_decision_ref: "
                    f"docs/followups/260617_2145_followups_range_{BASE7}_{HEAD7}.md"
                ),
                "followups_state.already_tracked_ref: docs/followups/process_followups_master.md",
                "followups_state.index_rebuild_status: ok",
                "followups_state.index_readback_status: ok",
                "followups_state.index_path: docs/followups/index.md",
                "followups_state.source: merge_bundle_report.followups_lane_reconciliation",
            }.issubset(set(plain.splitlines()))
        )

    def test_process_improvements_open_count_uses_counts_by_raw_status_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._host_paths(root)
            risk_packet = self._write_risk_packet(root, self._risk_payload(paths))
            report = self._green_report(paths)
            report["process_improvements_open_summary"] = {
                "lane_status": "separate",
                "open_count": 9,
            }
            with mock.patch.object(MODULE.merge_bundle_report, "build_report", return_value=report):
                rc, digest = self._run_json(root, "--risk-packet", str(risk_packet))

        self.assertEqual(rc, 0)
        self.assertEqual(digest["process_improvements_state"]["open_count"], "N/A")

    def test_process_improvements_missing_summary_does_not_synthesize_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._host_paths(root)
            risk_packet = self._write_risk_packet(root, self._risk_payload(paths))
            report = self._green_report(paths)
            report.pop("process_improvements_open_summary")
            with mock.patch.object(MODULE.merge_bundle_report, "build_report", return_value=report):
                rc, digest = self._run_json(root, "--risk-packet", str(risk_packet))

        self.assertEqual(rc, 0)
        self.assertEqual(digest["process_improvements_state"]["lane_status"], "N/A")
        self.assertEqual(digest["process_improvements_state"]["open_count"], "N/A")

    def test_incomplete_or_red_followups_input_blocks_derived_green_labels(self) -> None:
        with self.subTest("missing nested index rebuild"):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                paths = self._host_paths(root)
                risk_packet = self._write_risk_packet(root, self._risk_payload(paths))
                report = self._green_report(paths)
                report["followups_triage_launch_receipt"] = {}
                with mock.patch.object(MODULE.merge_bundle_report, "build_report", return_value=report):
                    rc, digest = self._run_json(root, "--risk-packet", str(risk_packet))

            self.assertEqual(rc, 2)
            self.assertEqual(digest["digest_status"], "blocked")
            invalid_error = next(
                error
                for error in digest["errors"]
                if error["code"] == "invalid_followups_projection"
            )
            self.assertIn(
                "followups_triage_launch_receipt.index_rebuild.status",
                invalid_error["detail"],
            )
            self.assertEqual(digest["followups_state"]["lane_status"], "N/A")
            self.assertEqual(digest["followups_state"]["launch_receipt_status"], "N/A")

        with self.subTest("wrongly typed unresolved count"):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                paths = self._host_paths(root)
                risk_packet = self._write_risk_packet(root, self._risk_payload(paths))
                report = self._green_report(paths)
                report["followups_lane_reconciliation"][
                    "range_unresolved_unparsed_bullets"
                ] = True
                with mock.patch.object(MODULE.merge_bundle_report, "build_report", return_value=report):
                    rc, digest = self._run_json(root, "--risk-packet", str(risk_packet))

            self.assertEqual(rc, 2)
            self.assertEqual(digest["digest_status"], "blocked")
            invalid_error = next(
                error
                for error in digest["errors"]
                if error["code"] == "invalid_followups_projection"
            )
            self.assertIn(
                "followups_lane_reconciliation.range_unresolved_unparsed_bullets",
                invalid_error["detail"],
            )
            self.assertEqual(digest["followups_state"]["lane_status"], "N/A")
            self.assertEqual(digest["followups_state"]["launch_receipt_status"], "N/A")

        with self.subTest("red merge bundle"):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                paths = self._host_paths(root)
                risk_packet = self._write_risk_packet(root, self._risk_payload(paths))
                report = self._green_report(
                    paths,
                    status="blocked",
                    errors=[
                        {
                            "code": "stale_receipt_copy",
                            "detail": (
                                "field=followups_lane_reconciliation.range_append_new; "
                                "source=docs/reviews/plan_harvest.md; "
                                "target=docs/reviews/operational_receipt.md; expected=2; actual=1"
                            ),
                        }
                    ],
                )
                with mock.patch.object(MODULE.merge_bundle_report, "build_report", return_value=report):
                    rc, digest = self._run_json(root, "--risk-packet", str(risk_packet))

            self.assertEqual(rc, 2)
            self.assertEqual(digest["digest_status"], "blocked")
            red_error = next(
                error for error in digest["errors"] if error["code"] == "red_merge_bundle_report"
            )
            self.assertIn("stale_receipt_copy", red_error["detail"])
            self.assertIn("field=followups_lane_reconciliation.range_append_new", red_error["detail"])
            self.assertIn("source=docs/reviews/plan_harvest.md", red_error["detail"])
            self.assertIn("target=docs/reviews/operational_receipt.md", red_error["detail"])
            self.assertEqual(digest["followups_state"]["lane_status"], "N/A")
            self.assertEqual(digest["followups_state"]["launch_receipt_status"], "N/A")
            self.assertEqual(digest["followups_state"]["unresolved_total"], 23)

    def test_packetization_path_mismatch_blocks_without_green_gate_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._host_paths(root)
            stale_paths = dict(paths)
            stale_paths["packetization_report"] = (
                f"docs/reviews/260617_2130_packetization_gate_range_{BASE7}_{HEAD7}.md"
            )
            self._write(root, stale_paths["packetization_report"], "**Status:** ✅ Done\n")
            risk_packet = self._write_risk_packet(root, self._risk_payload(stale_paths))
            report = self._green_report(paths)
            with mock.patch.object(MODULE.merge_bundle_report, "build_report", return_value=report):
                rc, digest = self._run_json(root, "--risk-packet", str(risk_packet))

        self.assertEqual(rc, 2)
        self.assertEqual(digest["digest_status"], "blocked")
        self.assertEqual(digest["active_packetization_report"]["gate_status"], "N/A")
        self.assertTrue(
            any(
                error["code"] == "stale_digest_readback"
                and "field=active_packetization_report.path" in error["detail"]
                and paths["packetization_report"] in error["detail"]
                and stale_paths["packetization_report"] in error["detail"]
                for error in digest["errors"]
            )
        )

    def test_missing_and_ambiguous_risk_packet_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._host_paths(root)
            report = self._green_report(paths)
            with mock.patch.object(MODULE.merge_bundle_report, "build_report", return_value=report):
                rc, digest = self._run_json(root)
            self.assertEqual(rc, 2)
            self.assertIn("missing_risk_packet", {error["code"] for error in digest["errors"]})

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._host_paths(root)
            payload = self._risk_payload(paths)
            self._write_risk_packet(root, payload, suffix="_a")
            self._write_risk_packet(root, payload, suffix="_b")
            report = self._green_report(paths)
            with mock.patch.object(MODULE.merge_bundle_report, "build_report", return_value=report):
                rc, digest = self._run_json(root)
            self.assertEqual(rc, 2)
            self.assertIn("ambiguous_risk_packet", {error["code"] for error in digest["errors"]})

    def test_unsupported_risk_packet_schema_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._host_paths(root)
            payload = self._risk_payload(paths)
            payload["schema_version"] = "range_review_risk_packet.v0"
            risk_packet = self._write_risk_packet(root, payload)
            report = self._green_report(paths)
            with mock.patch.object(MODULE.merge_bundle_report, "build_report", return_value=report):
                rc, digest = self._run_json(root, "--risk-packet", str(risk_packet))

        self.assertEqual(rc, 2)
        errors = {error["code"]: error for error in digest["errors"]}
        self.assertIn("risk_packet_schema_mismatch", errors)
        self.assertIn("range_review_risk_packet.v0", errors["risk_packet_schema_mismatch"]["detail"])

    def test_missing_required_truth_host_path_blocks_digest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._host_paths(root)
            (root / paths["post_merge_audit"]).unlink()
            risk_packet = self._write_risk_packet(root, self._risk_payload(paths))
            report = self._green_report(paths)
            with mock.patch.object(MODULE.merge_bundle_report, "build_report", return_value=report):
                rc, digest = self._run_json(root, "--risk-packet", str(risk_packet))

        self.assertEqual(rc, 2)
        errors = {error["code"]: error for error in digest["errors"]}
        self.assertIn("missing_truth_host_path", errors)
        self.assertEqual(errors["missing_truth_host_path"]["truth_host"], paths["post_merge_audit"])

    def test_unparseable_and_range_mismatched_risk_packet_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._host_paths(root)
            malformed = root / "docs" / "reviews" / f"260617_2145_risk_packet_range_{BASE7}_{HEAD7}.md"
            malformed.parent.mkdir(parents=True, exist_ok=True)
            malformed.write_text("**Status:** ✅ Done\n\n```json\n{not-json}\n```\n", encoding="utf-8")
            report = self._green_report(paths)
            with mock.patch.object(MODULE.merge_bundle_report, "build_report", return_value=report):
                rc, digest = self._run_json(root)
            self.assertEqual(rc, 2)
            self.assertIn("unparseable_risk_packet", {error["code"] for error in digest["errors"]})

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._host_paths(root)
            payload = self._risk_payload(paths)
            payload["head"] = "c" * 40
            risk_packet = self._write_risk_packet(root, payload)
            report = self._green_report(paths)
            with mock.patch.object(MODULE.merge_bundle_report, "build_report", return_value=report):
                rc, digest = self._run_json(root, "--risk-packet", str(risk_packet))
            self.assertEqual(rc, 2)
            self.assertIn("risk_packet_range_mismatch", {error["code"] for error in digest["errors"]})

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._host_paths(root)
            payload = self._risk_payload(paths)
            payload["target_snapshot"] = {"changed_files": []}
            risk_packet = self._write_risk_packet(root, payload)
            report = self._green_report(paths)
            with mock.patch.object(MODULE.merge_bundle_report, "build_report", return_value=report):
                rc, digest = self._run_json(root, "--risk-packet", str(risk_packet))
            self.assertEqual(rc, 2)
            self.assertEqual(digest["digest_status"], "blocked")
            self.assertIn("risk_packet_target_mismatch", {error["code"] for error in digest["errors"]})

    def test_red_review_truth_host_blocks_even_when_risk_packet_omits_live_blockers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._host_paths(root)
            self._write(root, paths["review_artifact"], "**Status:** ❌ S1 blocker(ы)\n")
            risk_packet = self._write_risk_packet(
                root,
                self._risk_payload(paths, review_status="❌ S1 blocker(ы)"),
            )
            report = self._green_report(paths)
            with mock.patch.object(MODULE.merge_bundle_report, "build_report", return_value=report):
                rc, digest = self._run_json(root, "--risk-packet", str(risk_packet))

        self.assertEqual(rc, 2)
        self.assertEqual(digest["digest_status"], "blocked")
        self.assertEqual(digest["live_review_verdict"]["verdict"], "blocked")
        self.assertEqual(digest["live_review_verdict"]["review_status"], "❌ S1 blocker(ы)")
        self.assertIn("red_review_truth_host", {error["code"] for error in digest["errors"]})

    def test_historical_blocker_closed_digest_keeps_closure_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._host_paths(root)
            payload = self._risk_payload(
                paths,
                historical_blockers=[
                    {
                        "id": "B1",
                        "status": "closed",
                        "summary": "ready_to_push closeout blocker closed",
                    }
                ],
                closure_artifacts=[{"path": paths["ready_to_push_closeout"], "status": "✅ Done"}],
            )
            risk_packet = self._write_risk_packet(root, payload)
            report = self._green_report(paths)
            with mock.patch.object(MODULE.merge_bundle_report, "build_report", return_value=report):
                rc, digest = self._run_json(root, "--risk-packet", str(risk_packet))

        self.assertEqual(rc, 0)
        self.assertEqual(digest["digest_status"], "ok")
        self.assertEqual(digest["historical_blockers"][0]["id"], "B1")
        self.assertEqual(
            digest["closure_artifacts"][0]["path"],
            f"docs/reviews/260617_2145_ready_to_push_closeout_range_{BASE7}_{HEAD7}.md",
        )


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest import mock

try:
    from scripts.test_contract_authority_support import AuthorityFixture, commit_all, git, write
except ModuleNotFoundError:
    from test_contract_authority_support import AuthorityFixture, commit_all, git, write


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "upstream_request.py"


def _request_text(
    *,
    request_id: str = "260501_1817_planveyor_owner_runbook",
    origin_repo: str = "consumer-fixture",
    header_origin_repo: str | None = None,
    owning_repo: str = "planveyor",
    header_owning_repo: str | None = None,
    origin_plan: str = "docs/plans/260501_1800_process_example_target_plan.md",
    header_origin_plan: str | None = None,
    trigger_ref: str = "docs/code_reviews/260501_1800_process_example_target_plan.md#B1",
    header_trigger_ref: str | None = None,
    status: str = "open",
    header_status: str | None = None,
    source_import_plan: str | None = None,
    header_source_import_plan: str | None = None,
    source_decision_ref: str | None = None,
    header_source_decision_ref: str | None = None,
    source_execution_ref: str | None = None,
    header_source_execution_ref: str | None = None,
    omit_meta_keys: tuple[str, ...] = (),
) -> str:
    meta = {
        "upstream_request_meta": {
            "id": request_id,
            "origin_repo": origin_repo,
            "owning_repo": owning_repo,
            "origin_plan": origin_plan,
            "trigger_ref": trigger_ref,
            "status": status,
            "requested_source_canon_path": "docs/tools/owner_runbook_codex.md",
            "source_import_plan": source_import_plan,
            "source_decision_ref": source_decision_ref,
            "source_execution_ref": source_execution_ref,
        }
    }
    for key in omit_meta_keys:
        meta["upstream_request_meta"].pop(key, None)

    def _context_ref(value: str | None, fallback: str) -> str:
        return f"`{value}`" if value else f"`N/A (why={fallback})`"

    source_import_line = _context_ref(
        header_source_import_plan if header_source_import_plan is not None else source_import_plan,
        "not imported yet",
    )
    source_decision_line = _context_ref(
        header_source_decision_ref if header_source_decision_ref is not None else source_decision_ref,
        "not decided yet",
    )
    source_execution_line = _context_ref(
        header_source_execution_ref if header_source_execution_ref is not None else source_execution_ref,
        "not executed yet",
    )
    return textwrap.dedent(
        f"""\
        # Upstream request packet: Owner Runbook

        **Date:** 2026-05-01 18:17 MSK
        **Origin repo:** {header_origin_repo or origin_repo}
        **Owning repo:** {header_owning_repo or owning_repo}
        **Status:** {header_status or status}
        **Schema version:** upstream_request.v1

        **Context links (source of truth):**
        - Origin plan: `{header_origin_plan or origin_plan}`
        - Trigger ref: `{header_trigger_ref or trigger_ref}`
        - Source import plan: {source_import_line}
        - Source decision ref: {source_decision_line}
        - Source execution ref: {source_execution_line}

        ## Meta (machine-readable JSON)
        ```json
        {json.dumps(meta, indent=2)}
        ```

        ## Request
        - symptom: target repo found shared process wording drift
        - process_gap: source canon has no reverse upstream request import lane
        - suggested_fix: add source-local request import helper and canonical packet template
        """
    )


class UpstreamRequestCliTests(unittest.TestCase):
    def _root(self) -> Path:
        tmpdir = tempfile.TemporaryDirectory(prefix="upstream_request_cli_")
        self.addCleanup(tmpdir.cleanup)
        root = Path(tmpdir.name)
        subprocess.run(["git", "init"], cwd=root, text=True, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", 'test' + '@' + 'example' + '.' + 'invalid'], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=root, check=True)
        (root / ".fixture").write_text("fixture\n", encoding="utf-8")
        subprocess.run(["git", "add", ".fixture"], cwd=root, check=True)
        subprocess.run(
            ["git", "commit", "-m", "fixture"],
            cwd=root,
            text=True,
            capture_output=True,
            check=True,
        )
        return root

    def _write_file(self, root: Path, relative_path: str, content: str) -> Path:
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def _run(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return self._run_with_tooling(root, root, *args)

    def _run_with_tooling(self, root: Path, tooling_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--repo-root",
                str(root),
                "--tooling-root",
                str(tooling_root),
                *args,
            ],
            text=True,
            capture_output=True,
            check=False,
        )

    def _packet_meta_from_text(self, text: str) -> dict[str, object]:
        marker = "```json\n"
        start = text.index(marker) + len(marker)
        end = text.index("\n```", start)
        payload = json.loads(text[start:end])
        return payload["upstream_request_meta"]

    def test_show_parses_required_fields(self) -> None:
        root = self._root()
        packet_rel = "docs/upstream_packets/sample_request.md"
        self._write_file(root, packet_rel, _request_text())

        result = self._run(root, "show", packet_rel)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Origin repo: consumer-fixture", result.stdout)
        self.assertIn("Owning repo: planveyor", result.stdout)
        self.assertIn("Status: open", result.stdout)
        self.assertIn("Process gap: source canon has no reverse upstream request import lane", result.stdout)

    def test_import_creates_source_local_process_row_and_updates_packet(self) -> None:
        root = self._root()
        packet_rel = "docs/upstream_packets/sample_request.md"
        packet_path = self._write_file(root, packet_rel, _request_text())

        # Stamps follow the local time zone of the run, not a fixed one.
        with mock.patch.dict(os.environ, {"TZ": "Asia/Tokyo"}):
            result = self._run(root, "import", "--packet", packet_rel)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Result: source-local process-improvement row recorded", result.stdout)
        text = packet_path.read_text(encoding="utf-8")
        meta = self._packet_meta_from_text(text)
        self.assertIn("**Status:** imported", text)
        self.assertEqual(meta["status"], "imported")
        self.assertTrue(str(meta["source_import_plan"]).startswith("docs/process_improvements/sample_request"))
        self.assertIn(f"- Source import plan: `{meta['source_import_plan']}`", text)
        self.assertIsNone(meta["source_decision_ref"])
        self.assertIsNone(meta["source_execution_ref"])

        backlog_path = root / "docs/process_improvements/sample_request__process_improvements_backlog.md"
        self.assertTrue(backlog_path.is_file())
        backlog_text = backlog_path.read_text(encoding="utf-8")
        self.assertIn("source canon has no reverse upstream request import lane", backlog_text)
        self.assertIn("auto-imported from upstream request packet", backlog_text)
        self.assertRegex(text, r"(?m)^- \[\d{4}-\d{2}-\d{2} \d{2}:\d{2} \+0900\] source import: ")
        self.assertRegex(backlog_text, r"(?m)^\*\*Date:\*\* \d{4}-\d{2}-\d{2} \d{2}:\d{2} \+0900$")
        self.assertRegex(backlog_text, r"(?m)^- created_at: `\d{4}-\d{2}-\d{2} \d{2}:\d{2} \+0900`$")
        self.assertTrue((root / "docs/process_improvements/index.md").is_file())
        self.assertTrue((root / "docs/process_improvements/deferred.md").is_file())
        self.assertTrue((root / "docs/process_improvements/promotion_surface.md").is_file())

    def test_import_rejects_wrong_root_without_mutation(self) -> None:
        tooling_root = self._root()
        target_root = self._root()
        packet_rel = "docs/upstream_packets/sample_request.md"
        packet_path = self._write_file(tooling_root, packet_rel, _request_text())
        before = packet_path.read_text(encoding="utf-8")

        result = self._run_with_tooling(target_root, tooling_root, "import", "--packet", packet_rel)

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("source-local only", result.stderr)
        self.assertEqual(packet_path.read_text(encoding="utf-8"), before)
        self.assertFalse((target_root / "docs/process_improvements").exists())

    def test_omitted_tooling_root_is_the_helper_checkout(self) -> None:
        root = self._root()
        packet_rel = "docs/upstream_packets/sample_request.md"
        packet_path = self._write_file(root, packet_rel, _request_text())
        before = packet_path.read_text(encoding="utf-8")

        result = subprocess.run(
            [sys.executable, str(SCRIPT), "import", "--packet", packet_rel],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("source-local only", result.stderr)
        self.assertEqual(packet_path.read_text(encoding="utf-8"), before)
        self.assertFalse((root / "docs/process_improvements").exists())

    def test_rejects_non_upstream_packet_path_without_mutation(self) -> None:
        root = self._root()
        plan_path = self._write_file(root, "docs/plans/not_a_packet.md", _request_text())

        result = self._run(root, "show", "docs/plans/not_a_packet.md")

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("request path must stay under docs/upstream_packets/", result.stderr)
        self.assertEqual(plan_path.read_text(encoding="utf-8"), _request_text())

    def test_rejects_wrong_owning_repo_and_header_meta_status_drift(self) -> None:
        root = self._root()
        wrong_owner = self._write_file(
            root,
            "docs/upstream_packets/wrong_owner.md",
            _request_text(owning_repo="consumer-fixture"),
        )
        status_drift = self._write_file(
            root,
            "docs/upstream_packets/status_drift.md",
            _request_text(status="open", header_status="imported"),
        )

        wrong_owner_result = self._run(root, "show", "docs/upstream_packets/wrong_owner.md")
        status_drift_result = self._run(root, "show", "docs/upstream_packets/status_drift.md")

        self.assertEqual(wrong_owner_result.returncode, 1, wrong_owner_result.stdout)
        self.assertIn("owning_repo must be `planveyor`", wrong_owner_result.stderr)
        self.assertEqual(status_drift_result.returncode, 1, status_drift_result.stdout)
        self.assertIn("header Status `imported` disagrees with upstream_request_meta.status `open`", status_drift_result.stderr)
        self.assertIn("**Owning repo:** consumer-fixture", wrong_owner.read_text(encoding="utf-8"))
        self.assertIn("**Status:** imported", status_drift.read_text(encoding="utf-8"))

    def test_rejects_origin_repo_header_meta_drift_and_source_as_origin(self) -> None:
        root = self._root()
        origin_drift = self._write_file(
            root,
            "docs/upstream_packets/origin_drift.md",
            _request_text(origin_repo="consumer-fixture", header_origin_repo="partner-fixture"),
        )
        source_origin = self._write_file(
            root,
            "docs/upstream_packets/source_origin.md",
            _request_text(origin_repo="planveyor"),
        )

        origin_drift_result = self._run(root, "show", "docs/upstream_packets/origin_drift.md")
        source_origin_result = self._run(root, "show", "docs/upstream_packets/source_origin.md")

        self.assertEqual(origin_drift_result.returncode, 1, origin_drift_result.stdout)
        self.assertIn("header Origin repo", origin_drift_result.stderr)
        self.assertEqual(source_origin_result.returncode, 1, source_origin_result.stdout)
        self.assertIn("origin_repo must be a target repo", source_origin_result.stderr)
        self.assertIn("**Origin repo:** partner-fixture", origin_drift.read_text(encoding="utf-8"))
        self.assertIn("**Origin repo:** planveyor", source_origin.read_text(encoding="utf-8"))

    def test_rejects_context_meta_drift_before_import_mutation(self) -> None:
        root = self._root()
        origin_plan_drift_rel = "docs/upstream_packets/origin_plan_drift.md"
        trigger_drift_rel = "docs/upstream_packets/trigger_drift.md"
        origin_plan_drift = self._write_file(
            root,
            origin_plan_drift_rel,
            _request_text(header_origin_plan="docs/plans/260501_9999_visible_target_plan.md"),
        )
        trigger_drift = self._write_file(
            root,
            trigger_drift_rel,
            _request_text(header_trigger_ref="docs/code_reviews/260501_9999_visible_review.md#B9"),
        )
        origin_plan_before = origin_plan_drift.read_text(encoding="utf-8")
        trigger_before = trigger_drift.read_text(encoding="utf-8")

        show_result = self._run(root, "show", origin_plan_drift_rel)
        import_result = self._run(root, "import", "--packet", trigger_drift_rel)
        query_result = self._run(root, "query", "--status", "all", "--json")

        self.assertEqual(show_result.returncode, 1, show_result.stdout)
        self.assertIn("context link Origin plan", show_result.stderr)
        self.assertEqual(import_result.returncode, 1, import_result.stdout)
        self.assertIn("context link Trigger ref", import_result.stderr)
        self.assertEqual(query_result.returncode, 1, query_result.stdout)
        self.assertIn("context link Origin plan", query_result.stderr)
        self.assertEqual(origin_plan_drift.read_text(encoding="utf-8"), origin_plan_before)
        self.assertEqual(trigger_drift.read_text(encoding="utf-8"), trigger_before)
        self.assertFalse((root / "docs/process_improvements").exists())

    def test_context_source_of_truth_block_is_not_overridden_by_later_bullets(self) -> None:
        root = self._root()
        packet_rel = "docs/upstream_packets/later_bullets.md"
        text = (
            _request_text()
            + "\n## Non-Source Notes\n"
            + "- Origin plan: `docs/plans/999999_9999_not_source_of_truth.md`\n"
            + "- Trigger ref: `docs/code_reviews/999999_9999_not_source_of_truth.md#B9`\n"
        )
        self._write_file(root, packet_rel, text)

        result = self._run(root, "show", packet_rel)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Origin plan: docs/plans/260501_1800_process_example_target_plan.md", result.stdout)
        self.assertIn("Trigger ref: docs/code_reviews/260501_1800_process_example_target_plan.md#B1", result.stdout)

    def test_rejects_source_ref_context_drift_and_missing_meta_before_mutation(self) -> None:
        root = self._root()
        missing_import_line_rel = "docs/upstream_packets/missing_import_line.md"
        decision_drift_rel = "docs/upstream_packets/decision_drift.md"
        execution_drift_rel = "docs/upstream_packets/execution_drift.md"
        missing_execution_meta_rel = "docs/upstream_packets/missing_execution_meta.md"
        missing_import_text = _request_text().replace(
            "- Source import plan: `N/A (why=not imported yet)`\n",
            "",
        )
        missing_import_line = self._write_file(root, missing_import_line_rel, missing_import_text)
        decision_drift = self._write_file(
            root,
            decision_drift_rel,
            _request_text(header_source_decision_ref="docs/reviews/260501_visible_decision.md"),
        )
        execution_drift = self._write_file(
            root,
            execution_drift_rel,
            _request_text(header_source_execution_ref="docs/plans/260501_visible_execution.md"),
        )
        missing_execution_meta = self._write_file(
            root,
            missing_execution_meta_rel,
            _request_text(omit_meta_keys=("source_execution_ref",)),
        )
        missing_import_before = missing_import_line.read_text(encoding="utf-8")

        import_result = self._run(root, "import", "--packet", missing_import_line_rel)
        decision_result = self._run(root, "show", decision_drift_rel)
        execution_result = self._run(root, "show", execution_drift_rel)
        meta_result = self._run(root, "show", missing_execution_meta_rel)

        self.assertEqual(import_result.returncode, 1, import_result.stdout)
        self.assertIn("context link Source import plan is required", import_result.stderr)
        self.assertEqual(decision_result.returncode, 1, decision_result.stdout)
        self.assertIn("context link Source decision ref", decision_result.stderr)
        self.assertEqual(execution_result.returncode, 1, execution_result.stdout)
        self.assertIn("context link Source execution ref", execution_result.stderr)
        self.assertEqual(meta_result.returncode, 1, meta_result.stdout)
        self.assertIn("upstream_request_meta missing required field: source_execution_ref", meta_result.stderr)
        self.assertEqual(missing_import_line.read_text(encoding="utf-8"), missing_import_before)
        self.assertIn("docs/reviews/260501_visible_decision.md", decision_drift.read_text(encoding="utf-8"))
        self.assertIn("docs/plans/260501_visible_execution.md", execution_drift.read_text(encoding="utf-8"))
        self.assertIn("source_decision_ref", missing_execution_meta.read_text(encoding="utf-8"))
        self.assertFalse((root / "docs/process_improvements").exists())

        query_root = self._root()
        self._write_file(
            query_root,
            "docs/upstream_packets/decision_drift.md",
            _request_text(header_source_decision_ref="docs/reviews/260501_visible_decision.md"),
        )
        query_result = self._run(query_root, "query", "--status", "all", "--json")

        self.assertEqual(query_result.returncode, 1, query_result.stdout)
        self.assertIn("context link Source decision ref", query_result.stderr)
        self.assertFalse((query_root / "docs/process_improvements").exists())

    def test_rejects_duplicate_visible_carriers_before_import_mutation(self) -> None:
        root = self._root()
        duplicate_status_rel = "docs/upstream_packets/duplicate_status.md"
        duplicate_context_rel = "docs/upstream_packets/duplicate_context.md"
        duplicate_status_text = _request_text().replace(
            "**Status:** open\n",
            "**Status:** open\n**Status:** imported\n",
            1,
        )
        duplicate_context_text = _request_text().replace(
            "- Source import plan: `N/A (why=not imported yet)`\n",
            "- Source import plan: `N/A (why=not imported yet)`\n- Source import plan: `docs/process_improvements/duplicate.md#PI-1`\n",
            1,
        )
        duplicate_status = self._write_file(root, duplicate_status_rel, duplicate_status_text)
        duplicate_context = self._write_file(root, duplicate_context_rel, duplicate_context_text)
        duplicate_status_before = duplicate_status.read_text(encoding="utf-8")
        duplicate_context_before = duplicate_context.read_text(encoding="utf-8")

        status_result = self._run(root, "import", "--packet", duplicate_status_rel)
        context_result = self._run(root, "import", "--packet", duplicate_context_rel)

        self.assertEqual(status_result.returncode, 1, status_result.stdout)
        self.assertIn("exactly one **Status:** field", status_result.stderr)
        self.assertEqual(context_result.returncode, 1, context_result.stdout)
        self.assertIn("at most one `Source import plan` line", context_result.stderr)
        self.assertEqual(duplicate_status.read_text(encoding="utf-8"), duplicate_status_before)
        self.assertEqual(duplicate_context.read_text(encoding="utf-8"), duplicate_context_before)
        self.assertFalse((root / "docs/process_improvements").exists())

    def test_import_updates_scoped_context_when_non_source_row_precedes_block(self) -> None:
        root = self._root()
        packet_rel = "docs/upstream_packets/non_source_before_context.md"
        text = _request_text().replace(
            "**Context links (source of truth):**\n",
            "## Non-Source Prelude\n"
            "- Source import plan: `docs/process_improvements/non_source.md#PI-9999`\n\n"
            "**Context links (source of truth):**\n",
            1,
        )
        packet_path = self._write_file(root, packet_rel, text)

        import_result = self._run(root, "import", "--packet", packet_rel)
        show_result = self._run(root, "show", packet_rel)

        self.assertEqual(import_result.returncode, 0, import_result.stderr)
        updated = packet_path.read_text(encoding="utf-8")
        meta = self._packet_meta_from_text(updated)
        self.assertIn("- Source import plan: `docs/process_improvements/non_source.md#PI-9999`", updated)
        self.assertIn(f"- Source import plan: `{meta['source_import_plan']}`", updated)
        self.assertEqual(show_result.returncode, 0, show_result.stderr)
        self.assertIn("Status: imported", show_result.stdout)
        self.assertIn(f"Source import plan: {meta['source_import_plan']}", show_result.stdout)

    def test_ack_updates_scoped_decision_and_execution_refs_with_readback(self) -> None:
        root = self._root()
        packet_rel = "docs/upstream_packets/ack_packet.md"
        decision_ref = "docs/plans/260501_1900_source_decision.md#Decision"
        execution_ref = "docs/plans/260501_1930_source_execution.md#Evidence"
        text = _request_text(
            status="imported",
            source_import_plan="docs/process_improvements/ack_packet__process_improvements_backlog.md#PI-001",
        ).replace(
            "**Context links (source of truth):**\n",
            "## Non-Source Prelude\n"
            "- Source decision ref: `docs/plans/non_source_decision.md`\n"
            "- Source execution ref: `docs/plans/non_source_execution.md`\n\n"
            "**Context links (source of truth):**\n",
            1,
        )
        packet_path = self._write_file(root, packet_rel, text)

        with mock.patch.dict(os.environ, {"TZ": "Asia/Tokyo"}):
            ack_result = self._run(
                root,
                "ack",
                "--packet",
                packet_rel,
                "--source-decision-ref",
                decision_ref,
                "--source-execution-ref",
                execution_ref,
            )
        show_result = self._run(root, "show", packet_rel)

        self.assertEqual(ack_result.returncode, 0, ack_result.stderr)
        updated = packet_path.read_text(encoding="utf-8")
        meta = self._packet_meta_from_text(updated)
        self.assertRegex(updated, r"(?m)^- \[\d{4}-\d{2}-\d{2} \d{2}:\d{2} \+0900\] source ack: ")
        self.assertIn("- Source decision ref: `docs/plans/non_source_decision.md`", updated)
        self.assertIn("- Source execution ref: `docs/plans/non_source_execution.md`", updated)
        self.assertIn(f"- Source decision ref: `{decision_ref}`", updated)
        self.assertIn(f"- Source execution ref: `{execution_ref}`", updated)
        self.assertEqual(meta["status"], "decided")
        self.assertEqual(meta["source_decision_ref"], decision_ref)
        self.assertEqual(meta["source_execution_ref"], execution_ref)
        self.assertEqual(show_result.returncode, 0, show_result.stderr)
        self.assertIn("Status: decided", show_result.stdout)
        self.assertIn(f"Source decision ref: {decision_ref}", show_result.stdout)
        self.assertIn(f"Source execution ref: {execution_ref}", show_result.stdout)

    def test_ack_rejects_execution_without_decision_and_does_not_mutate(self) -> None:
        root = self._root()
        packet_rel = "docs/upstream_packets/ack_missing_decision.md"
        packet_path = self._write_file(
            root,
            packet_rel,
            _request_text(
                status="imported",
                source_import_plan="docs/process_improvements/ack_packet__process_improvements_backlog.md#PI-001",
            ),
        )
        before = packet_path.read_text(encoding="utf-8")

        result = self._run(
            root,
            "ack",
            "--packet",
            packet_rel,
            "--source-execution-ref",
            "docs/plans/260501_1930_source_execution.md#Evidence",
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("source_execution_ref requires source_decision_ref", result.stderr)
        self.assertEqual(packet_path.read_text(encoding="utf-8"), before)

    def test_lint_reports_clean_default_corpus_excluding_template(self) -> None:
        root = self._root()
        packet_rel = "docs/upstream_packets/sample_request.md"
        packet_path = self._write_file(root, packet_rel, _request_text())
        before = packet_path.read_text(encoding="utf-8")
        self._write_file(root, "docs/upstream_packets/_template.md", "not a live packet\n")

        text_result = self._run(root, "lint")
        json_result = self._run(root, "lint", "--json")

        self.assertEqual(text_result.returncode, 0, text_result.stderr)
        self.assertIn("upstream-request-lint: OK", text_result.stdout)
        self.assertIn("files checked: 1", text_result.stdout)
        self.assertEqual(json_result.returncode, 0, json_result.stderr)
        payload = json.loads(json_result.stdout)
        self.assertEqual(payload["findings"], [])
        self.assertEqual([entry["file"] for entry in payload["files"]], [packet_rel])
        self.assertEqual(packet_path.read_text(encoding="utf-8"), before)
        self.assertFalse((root / "docs/process_improvements").exists())

    def test_lint_reports_all_malformed_files_in_mixed_batch(self) -> None:
        root = self._root()
        self._write_file(root, "docs/upstream_packets/valid.md", _request_text())
        self._write_file(
            root,
            "docs/upstream_packets/wrong_owner.md",
            _request_text(owning_repo="consumer-fixture"),
        )
        self._write_file(
            root,
            "docs/upstream_packets/status_drift.md",
            _request_text(status="open", header_status="imported"),
        )
        self._write_file(
            root,
            "docs/upstream_packets/context_drift.md",
            _request_text(header_origin_plan="docs/plans/260501_9999_visible_target_plan.md"),
        )
        self._write_file(
            root,
            "docs/upstream_packets/missing_meta.md",
            _request_text(omit_meta_keys=("source_execution_ref",)),
        )

        result = self._run(root, "lint", "docs/upstream_packets")

        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("upstream-request-lint: FAIL", result.stdout)
        self.assertIn("files checked: 5", result.stdout)
        self.assertIn("findings: 4", result.stdout)
        self.assertIn("docs/upstream_packets/wrong_owner.md: invalid_packet", result.stdout)
        self.assertIn("owning_repo must be `planveyor`", result.stdout)
        self.assertIn("docs/upstream_packets/status_drift.md: invalid_packet", result.stdout)
        self.assertIn("header Status `imported` disagrees with upstream_request_meta.status `open`", result.stdout)
        self.assertIn("docs/upstream_packets/context_drift.md: invalid_packet", result.stdout)
        self.assertIn("context link Origin plan", result.stdout)
        self.assertIn("docs/upstream_packets/missing_meta.md: invalid_packet", result.stdout)
        self.assertIn("upstream_request_meta missing required field: source_execution_ref", result.stdout)
        self.assertFalse((root / "docs/process_improvements").exists())

    def test_lint_json_reports_missing_explicit_path_without_traceback(self) -> None:
        root = self._root()
        self._write_file(root, "docs/upstream_packets/valid.md", _request_text())

        result = self._run(
            root,
            "lint",
            "docs/upstream_packets/valid.md",
            "docs/upstream_packets/missing.md",
            "--json",
        )

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stderr, "")
        payload = json.loads(result.stdout)
        self.assertEqual([entry["file"] for entry in payload["files"]], ["docs/upstream_packets/valid.md"])
        self.assertEqual(len(payload["findings"]), 1)
        self.assertEqual(payload["findings"][0]["file"], "docs/upstream_packets/missing.md")
        self.assertEqual(payload["findings"][0]["code"], "missing")
        self.assertIn("request path does not exist", payload["findings"][0]["message"])
        self.assertFalse((root / "docs/process_improvements").exists())

    def test_query_json_lists_open_requests_and_filters_origin(self) -> None:
        root = self._root()
        self._write_file(
            root,
            "docs/upstream_packets/open_consumer.md",
            _request_text(request_id="open_consumer", origin_repo="consumer-fixture"),
        )
        self._write_file(
            root,
            "docs/upstream_packets/open_partner.md",
            _request_text(request_id="open_partner", origin_repo="partner-fixture"),
        )
        self._write_file(
            root,
            "docs/upstream_packets/imported_consumer.md",
            _request_text(request_id="imported_consumer", origin_repo="consumer-fixture", status="imported"),
        )

        result = self._run(root, "query", "--status", "open", "--origin-repo", "consumer-fixture", "--json")

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["requests"][0]["request_path"], "docs/upstream_packets/open_consumer.md")
        self.assertEqual(payload["requests"][0]["origin_repo"], "consumer-fixture")
        self.assertEqual(payload["requests"][0]["status"], "open")


class UpstreamRequestFacadeProjectRootTests(unittest.TestCase):
    """A sibling's public calls refuse before reaching the runtime's packets."""

    OPEN = "docs/upstream_packets/260929_1200_consumer-fixture_open_probe.md"
    IMPORTED = "docs/upstream_packets/260929_1201_consumer-fixture_imported_probe.md"

    @staticmethod
    def _run_public(
        entry: Path,
        project: Path,
        environment: dict[str, str],
        *arguments: str,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(entry), "--project", str(project), *arguments],
            cwd=project,
            env=environment,
            stdin=subprocess.DEVNULL,
            text=True,
            capture_output=True,
            check=False,
            timeout=120,
        )

    def test_sibling_calls_refuse_and_source_calls_still_work(self) -> None:
        with AuthorityFixture(identity="planveyor") as fixture:
            entry = write(
                fixture.runtime_root,
                "bin/planveyor",
                (REPO_ROOT / "bin" / "planveyor").read_bytes(),
                executable=True,
            )
            runtime = fixture.runtime_root
            target = fixture.target_root
            for root, owner in ((runtime, "runtime"), (target, "target")):
                write(root, self.OPEN, _request_text(request_id=f"260929_1200_{owner}_open"))
                write(
                    root,
                    self.IMPORTED,
                    _request_text(
                        request_id=f"260929_1201_{owner}_imported",
                        status="imported",
                        source_import_plan="docs/process_improvements/fixture__process_improvements_backlog.md",
                    ),
                )
            runtime_commit = commit_all(runtime, "runtime upstream packets")
            commit_all(target, "sibling upstream packet drafts")
            environment = fixture.environment()
            state_root = fixture.root / "state"
            state_root.mkdir()
            environment["PLANVEYOR_STATE_ROOT"] = str(state_root)

            sibling_calls = {
                "query": ("planveyor_upstream_request_query", "--json"),
                "show": ("planveyor_upstream_request_show", self.OPEN),
                "import": ("planveyor_upstream_request_import", "--packet", self.OPEN),
                "ack": (
                    "planveyor_upstream_request_ack",
                    "--packet",
                    self.IMPORTED,
                    "--source-decision-ref",
                    "docs/plans/260929_1300_process_decision.md",
                ),
                "helper_import_with_default_roots": (
                    "planveyor_runtime_py",
                    "upstream_request.py",
                    "import",
                    "--packet",
                    self.OPEN,
                ),
            }
            sibling = {
                label: self._run_public(entry, target, environment, *arguments)
                for label, arguments in sibling_calls.items()
            }
            # An explicit runtime root reaches the collector, whose authority
            # check must surface as a readable refusal, not a bridge failure.
            explicit_runtime_import = self._run_public(
                entry,
                target,
                environment,
                "planveyor_runtime_py",
                "upstream_request.py",
                "--repo-root",
                str(runtime),
                "--tooling-root",
                str(runtime),
                "import",
                "--packet",
                self.OPEN,
            )
            runtime_status = git(runtime, "status", "--short", "--untracked-files=all")
            runtime_head = git(runtime, "rev-parse", "HEAD")
            target_status = git(target, "status", "--short", "--untracked-files=all")
            source_facade = self._run_public(entry, runtime, environment, "planveyor_upstream_request_query", "--json")
            source_helper = self._run_public(
                entry, runtime, environment, "planveyor_runtime_py", "upstream_request.py", "query", "--json"
            )

        for label, result in sibling.items():
            with self.subTest(call=label):
                output = result.stdout + result.stderr
                self.assertEqual(result.returncode, 1, output)
                self.assertIn("source-local only", result.stderr)
                self.assertNotIn("internal_error", output)
        explicit_output = explicit_runtime_import.stdout + explicit_runtime_import.stderr
        self.assertEqual(explicit_runtime_import.returncode, 1, explicit_output)
        self.assertIn("context_expectation_mismatch", explicit_runtime_import.stderr)
        self.assertNotIn("internal_error", explicit_output)
        self.assertEqual(runtime_status, "")
        self.assertEqual(runtime_head, runtime_commit)
        self.assertEqual(target_status, "")
        for result in (source_facade, source_helper):
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["repo_root"], runtime.as_posix())
            self.assertEqual([row["id"] for row in payload["requests"]], ["260929_1200_runtime_open"])


if __name__ == "__main__":
    unittest.main()

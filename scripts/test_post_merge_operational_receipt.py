#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from textwrap import dedent


SCRIPT_PATH = Path(__file__).with_name("post_merge_operational_receipt.py")
BASE = "a" * 40
HEAD = "b" * 40
B7 = BASE[:7]
H7 = HEAD[:7]
SHA256 = "b1df5fca0ca714f91180f4da82fa8392891c95dff8a49ec0ff3140cebd4c6f11"


class PostMergeOperationalReceiptTests(unittest.TestCase):
    def _owner_home(self) -> str:
        return "/" + "Users/" + "fixture-user"

    def _write(self, root: Path, rel_path: str, body: str) -> Path:
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    def _write_range_and_tracker(self, root: Path) -> None:
        self._write(root, ".planveyor.range.base", f"{BASE}\n")
        self._write(root, ".planveyor.range.head", f"{HEAD}\n")
        self._write(
            root,
            ".planveyor.merge_tracker.md",
            dedent(
                f"""\
                # Merge tracker

                BASE={BASE}
                HEAD={HEAD}
                RANGE={BASE}..{HEAD}
                RANGE_ID=range_{B7}_{H7}

                ## Checklist
                - [x] step:docs_finalize
                - [x] step:doc_lint
                - [x] step:docs_hygiene_archive
                - [x] step:docs_hygiene_suggest
                - [ ] step:ready_to_push
                """
            ),
        )

    def _step_records(self) -> list[dict[str, object]]:
        captured_at = "2026-05-18T19:00:00+00:00"
        followups_source = f"docs/reviews/260505_1200_plan_harvest_range_{B7}_{H7}.md"

        def ran(step: str, command: str, artifact_path: str, count_summary: str, result: str) -> dict[str, object]:
            return {
                "step": step,
                "command": command,
                "exit_code": 0,
                "result": result,
                "artifact_path": artifact_path,
                "count_summary": count_summary,
                "no_op_reason": "N/A (why=ran)",
                "in_scope": "yes",
                "captured_at": captured_at,
                "source": "fixture command output",
            }

        def skipped(step: str, reason: str) -> dict[str, object]:
            return {
                "step": step,
                "command": f"N/A (why={reason})",
                "result": "skipped",
                "artifact_path": f"N/A (why={reason})",
                "count_summary": f"N/A (why={reason})",
                "no_op_reason": reason,
                "in_scope": "no",
                "captured_at": captured_at,
                "source": "fixture no-op reason",
            }

        return [
            ran("docs_finalize", "planveyor_arch_docs_general", "docs/plans/fixture.md", "docs_changed=0", "ok"),
            ran("doc_lint", "bash ./scripts/run_doc_lint.sh", "N/A (why=stdout only)", "errors=0", "ok"),
            ran("docs_hygiene_archive", f"planveyor_docs_hygiene_archive --range {BASE}..{HEAD} --apply", ".tmp/docs_hygiene_archive.json", "inserted=0 skipped_existing=2 missing_on_disk=0", "ok"),
            ran("docs_hygiene_suggest", f"planveyor_docs_hygiene_suggest --range {BASE}..{HEAD}", ".tmp/docs_hygiene_suggest.md", "candidates=2 report_only=yes", "ok"),
            ran(
                "docs_index_context",
                "planveyor_docs_index_build all; docs_context_check --corpus plans; docs_context_check --corpus followups",
                "N/A (why=stdout summary)",
                (
                    "plans_total=2; plans_covered=2; plans_uncovered=0; plans_state=covered; "
                    "followups_total=1; followups_covered=1; followups_uncovered=0; followups_state=covered; "
                    "canon_state=advisory"
                ),
                "ok",
            ),
            ran(
                "retrieval_metrics",
                "scripts/docs_retrieve_metrics.py --format json",
                "N/A (why=stdout summary)",
                (
                    "query_total=10; evaluated_total=3; outcome_evaluated_rate=0.30; "
                    "read_log_status=present; read_events_total=1; read_open_rate=0.10; "
                    "used_for_decision=true; triage=not_required"
                ),
                "ok",
            ),
            ran(
                "followups_triage_launch",
                (
                    f"planveyor_followups_triage --file docs/followups/260505_1200_followups_range_{B7}_{H7}.md "
                    "--dry-run; "
                    f"planveyor_followups_triage --file docs/followups/260505_1200_followups_range_{B7}_{H7}.md "
                    "--apply; "
                    f"planveyor_followups_triage --file docs/followups/260505_1200_followups_range_{B7}_{H7}.md "
                    "--apply; "
                    "scripts/followups_index_rebuild.py --project-root ."
                ),
                followups_source,
                (
                    f"source_harvest_receipt_path={followups_source}; triage_mode=file; "
                    "dry_run_append_new=2; dry_run_merge_source=0; dry_run_possible_duplicate=0; dry_run_route_fallback=0; "
                    "apply_append_new=2; apply_merge_source=0; apply_possible_duplicate=0; apply_route_fallback=0; "
                    "idempotency_append_new=0; idempotency_merge_source=2; idempotency_possible_duplicate=0; "
                    "idempotency_route_fallback=0; index_rebuild_status=ok; readback_status=ok; "
                    "index_path=docs/followups/index.md; process_improvements_lane=separate; "
                    f"process_improvements_ref={followups_source}#process-improvement-promotion-decisions"
                ),
                "ok",
            ),
            skipped("canon_sweep", "canon sweep not completed in fixture"),
            ran("planveyor_merge_bundle_report", "planveyor_merge_bundle_report", "N/A (why=read-only stdout)", "status=ok errors=0", "status=ok"),
        ]

    def _archive_snapshot(self, **overrides: object) -> dict[str, object]:
        payload: dict[str, object] = {
            "status": "ok",
            "storage_backend": "git_text_export",
            "manifest_path": "docs/_meta/archive_snapshots/current/manifest.json",
            "artifact_path": "docs/_meta/archive_snapshots/current/archived_docs.jsonl",
            "object_uri": "N/A (why=git-backed artifact)",
            "checksum": SHA256,
            "format_version": "1",
            "access_status": "not_required",
            "restore_status": "ok",
            "readback_status": "ok",
            "no_op_reason": "N/A (why=ran)",
            "blocker_reason": "N/A (why=none)",
            "source": (
                "planveyor_docs_archive_snapshot_export + planveyor_docs_archive_snapshot_validate + "
                "planveyor_docs_archive_snapshot_restore"
            ),
            "export_command": (
                "planveyor_docs_archive_snapshot_export --backend git_text_export "
                "--output-dir docs/_meta/archive_snapshots/current --force"
            ),
            "export_status": "ok",
            "snapshot_created_at_utc": "2026-05-18T19:01:00+00:00",
            "snapshot_source_db_sha256": "c" * 64,
            "snapshot_source_docs_count": "2",
        }
        payload.update(overrides)
        return payload

    def _docs_hygiene_suggest_stdout(
        self,
        *,
        paths: list[str] | None = None,
        malformed: bool = False,
        range_ref: str | None = None,
    ) -> str:
        range_ref = range_ref or f"{BASE}..{HEAD}"
        if malformed:
            return f"[planveyor] Range: {range_ref}\nmalformed\n"
        if paths is None:
            paths = [
                "docs/plans/260505_1200_done_plan.md",
                "docs/code_reviews/260505_1200_review.md",
            ]
        lines = [
            f"[planveyor] Range: {range_ref}",
            "",
        ]
        if paths:
            plan_paths = [path for path in paths if path.startswith("docs/plans/")]
            code_paths = [
                path
                for path in paths
                if path.startswith(("docs/code_reviews/", "docs/doc_reviews/", "docs/code_drafts/"))
                and not path.startswith("docs/code_reviews/assets/")
            ]
            if plan_paths:
                lines.append(f"[planveyor] Terminal plans in range (`Done` + `Superseded`) ({len(plan_paths)}):")
                lines.extend(f"  - {path}" for path in plan_paths)
                lines.append("")
            else:
                lines.append("[planveyor] Terminal plans in range (`Done` + `Superseded`): none")
                lines.append("")
            if code_paths:
                lines.append(f"[planveyor] Review/code drafts safe to delete ({len(code_paths)}):")
                for path in code_paths:
                    lines.append(f"  - {path}")
                    lines.append("      reason: referenced only by terminal plan(s)")
                lines.append("")
            lines.append("[planveyor] REQUIRED before any git rm: archive temp docs into the central SQLite archive:")
            lines.append(f"  python3 scripts/docs_hygiene_archive.py --range {range_ref} --apply")
            lines.append("")
        else:
            lines.append("[planveyor] Terminal plans in range (`Done` + `Superseded`): none")
            lines.append("")
        lines.append("[planveyor] Suggested (Owner) command:")
        if not paths:
            lines.append("  # nothing to remove (or nothing detected as safe)")
            return "\n".join(lines) + "\n"
        lines.append("  git rm -r \\")
        for path in paths:
            lines.append(f"    {path} \\")
        lines.append("  # (copy, then remove trailing backslash on the last line)")
        return "\n".join(lines) + "\n"

    def _write_docs_hygiene_suggest_stdout(
        self,
        root: Path,
        *,
        rel_path: str = ".tmp/docs_hygiene_suggest.md",
        paths: list[str] | None = None,
        malformed: bool = False,
        range_ref: str | None = None,
    ) -> None:
        self._write(root, rel_path, self._docs_hygiene_suggest_stdout(paths=paths, malformed=malformed, range_ref=range_ref))

    def _write_followups_triage_launch_source(
        self,
        root: Path,
        *,
        schema_version: str | None = None,
        harvest_result: str = "NO FOLLOWUPS",
        harvest_count: int = 0,
        include_current_literals: bool = True,
    ) -> None:
        schema_line = f"**Schema version:** {schema_version}\n" if schema_version else ""
        source_result_line = (
            f"- Result: `{harvest_result}` - no remaining actionable debt in the harvest file-lane."
            if harvest_result == "NO FOLLOWUPS"
            else f"- Result: `{harvest_result}`."
        )
        current_literals = (
            f"- harvest_file_followups_result: `{harvest_result}`"
            + (" — no remaining actionable debt after full-wave harvest." if harvest_result == "NO FOLLOWUPS" else "")
            + f"\n- harvest_file_followups_count: {harvest_count}\n"
            if schema_version == "review.v1" and include_current_literals
            else ""
        )
        self._write(
            root,
            f"docs/reviews/260505_1200_plan_harvest_range_{B7}_{H7}.md",
            dedent(
                f"""\
                # Plan harvest

                **Status:** ✅ Done
                {schema_line}

                ## Follow-ups (extracted; без дублей)
                {source_result_line}

                ## Follow-up harvest triage/import receipt
                {current_literals}
                | command | mode | append_new | merge_source | possible_duplicate | route_fallback | unparsed_bullets | result |
                | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
                | `planveyor_followups_triage --file docs/followups/260505_1200_followups_range_{B7}_{H7}.md --dry-run` | dry-run | 2 | 0 | 0 | 0 | 0 | dry-run only |
                | `planveyor_followups_triage --file docs/followups/260505_1200_followups_range_{B7}_{H7}.md --apply` | apply | 2 | 0 | 0 | 0 | 0 | imported |
                | `planveyor_followups_triage --file docs/followups/260505_1200_followups_range_{B7}_{H7}.md --apply` | idempotency apply | 0 | 2 | 0 | 0 | 0 | no file changes |
                | `scripts/followups_index_rebuild.py --project-root .` | rebuild | 0 | 0 | 0 | 0 | 0 | index updated |

                ## Process-improvement promotion decisions
                - process_improvements_open_summary: source=docs/process_improvements/promotion_surface.md; lane=separate; ordinary_followups=NO FOLLOWUPS; open=2; triaged=0; promoted=0; null_execution=2; owner_or_next_step=Planner triage in process-improvement promotion lane
                | source_ref | entry_id | raw_status | execution_kind | execution_ref | owner_or_next_step |
                | --- | --- | --- | --- | --- | --- |
                | `docs/process_improvements/promotion_surface.md` | `PI-001` | `open` | `null` | `null` | `Planner triage in process-improvement promotion lane` |
                | `docs/process_improvements/promotion_surface.md` | `PI-002` | `open` | `null` | `null` | `Planner triage in process-improvement promotion lane` |
                """
            ),
        )

    def _run_writer(
        self,
        root: Path,
        *,
        archive_snapshot: dict[str, object] | None,
        records: list[dict[str, object]] | None = None,
        write_suggest_stdout: bool = True,
        write_followups_receipt: bool = True,
        suggest_stdout_paths: list[str] | None = None,
        malformed_suggest_stdout: bool = False,
        suggest_stdout_range: str | None = None,
        followups_schema_version: str | None = None,
        followups_harvest_result: str = "NO FOLLOWUPS",
        followups_harvest_count: int = 0,
        include_current_followups_literals: bool = True,
        out_path: str | None = f"docs/reviews/260505_1200_post_merge_operational_receipt_range_{B7}_{H7}.md",
        content_profile_id: str = "default",
    ) -> subprocess.CompletedProcess[str]:
        effective_records = records if records is not None else self._step_records()
        if write_suggest_stdout:
            suggest_record = next((record for record in effective_records if record.get("step") == "docs_hygiene_suggest"), None)
            if suggest_record is not None:
                rel_path = str(suggest_record.get("artifact_path", ".tmp/docs_hygiene_suggest.md"))
                self._write_docs_hygiene_suggest_stdout(
                    root,
                    rel_path=rel_path,
                    paths=suggest_stdout_paths,
                    malformed=malformed_suggest_stdout,
                    range_ref=suggest_stdout_range,
                )
        if write_followups_receipt and any(record.get("step") == "followups_triage_launch" for record in effective_records):
            self._write_followups_triage_launch_source(
                root,
                schema_version=followups_schema_version,
                harvest_result=followups_harvest_result,
                harvest_count=followups_harvest_count,
                include_current_literals=include_current_followups_literals,
            )
        cmd = [
            sys.executable,
            "-B",
            str(SCRIPT_PATH),
            "--repo-root",
            str(root),
        ]
        if out_path is not None:
            cmd.extend(["--out", out_path])
        cmd.extend(["--content-profile-id", content_profile_id])
        cmd.append("--print-path")
        for record in effective_records:
            cmd.extend(["--record-json", json.dumps(record)])
        if archive_snapshot is not None:
            cmd.extend(["--archive-snapshot-json", json.dumps(archive_snapshot)])
        return subprocess.run(cmd, text=True, capture_output=True, check=False)

    def test_writer_records_git_text_export_archive_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_range_and_tracker(root)

            result = self._run_writer(root, archive_snapshot=self._archive_snapshot())
            receipt_path = root / f"docs/reviews/260505_1200_post_merge_operational_receipt_range_{B7}_{H7}.md"
            receipt_text = receipt_path.read_text(encoding="utf-8")
            payload = json.loads(receipt_text.split("```json", 1)[1].split("```", 1)[0])

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("archive_snapshot_status: ok", receipt_text)
        self.assertIn("archive_snapshot_backend: git_text_export", receipt_text)
        self.assertIn("docs/_meta/archive_snapshots/current/manifest.json", receipt_text)
        self.assertIn(SHA256, receipt_text)
        self.assertIn("archive_snapshot_export_status: ok", receipt_text)
        self.assertIn("archive_snapshot_source_docs_count: 2", receipt_text)
        self.assertIn("plans_uncovered=0", receipt_text)
        self.assertIn("outcome_evaluated_rate=0.30", receipt_text)
        self.assertIn("docs_hygiene_suggest_report_only: True", receipt_text)
        self.assertIn("docs_hygiene_suggest_deletion_executed: False", receipt_text)
        self.assertIn('"docs_hygiene_suggest_summary"', receipt_text)
        self.assertIn('"suggest_result": "ok"', receipt_text)
        self.assertIn('"omitted_count": 0', receipt_text)
        self.assertIn('"followups_triage_launch_receipt"', receipt_text)
        self.assertIn('"triage_mode": "file"', receipt_text)
        self.assertIn('"readback_status": "ok"', receipt_text)
        self.assertIn('"followups_lane_reconciliation"', receipt_text)
        self.assertIn("followups_lane_reconciliation_summary", receipt_text)
        self.assertIn("harvest_file_followups_result", receipt_text)
        self.assertIn("range_append_new", receipt_text)
        self.assertIn('"process_improvements_open_summary"', receipt_text)
        self.assertIn("process_improvements_open_summary_counts", receipt_text)
        summary = payload["docs_hygiene_suggest_summary"]
        self.assertEqual(summary["command"], f"planveyor_docs_hygiene_suggest --range {BASE}..{HEAD}")
        self.assertEqual(summary["gate_command"], f"planveyor_docs_hygiene_suggest --range {BASE}..{HEAD}")
        self.assertEqual(summary["suggested_owner_rerun_command"], f"planveyor_docs_hygiene_suggest --range {BASE}..{HEAD}")
        pi_summary = payload["process_improvements_open_summary"]
        self.assertEqual(pi_summary["ordinary_followups_result"], "NO FOLLOWUPS")
        self.assertEqual(pi_summary["lane_status"], "separate")
        self.assertEqual(pi_summary["counts_by_raw_status"], {"open": 2, "promoted": 0, "triaged": 0})
        self.assertEqual(pi_summary["null_execution_rows"], 2)
        self.assertEqual(
            pi_summary["decision_receipt_path"],
            f"docs/reviews/260505_1200_plan_harvest_range_{B7}_{H7}.md#process-improvement-promotion-decisions",
        )
        reconciliation = payload["followups_lane_reconciliation"]
        self.assertEqual(reconciliation["harvest_file_followups_result"], "NO FOLLOWUPS")
        self.assertEqual(reconciliation["harvest_file_followups_count"], 0)
        self.assertEqual(reconciliation["range_triage_mode"], "file")
        self.assertEqual(reconciliation["range_append_new"], 2)
        self.assertEqual(reconciliation["range_merge_source"], 0)
        self.assertEqual(reconciliation["range_unparsed_bullets"], 0)
        self.assertIn("file-lane=NO FOLLOWUPS", reconciliation["owner_summary"])
        self.assertIn("range-lane apply append_new=2", reconciliation["owner_summary"])
        self.assertIn("triage_mode=file", reconciliation["owner_summary"])
        self.assertNotIn("file-lane apply append_new=2", reconciliation["owner_summary"])
        snapshot = payload["archive_snapshot"]
        self.assertIn("planveyor_docs_archive_snapshot_export", snapshot["export_command"])
        self.assertEqual(snapshot["export_status"], "ok")
        self.assertEqual(snapshot["snapshot_source_db_sha256"], "c" * 64)
        self.assertEqual(snapshot["snapshot_source_docs_count"], "2")

    def test_writer_preserves_current_harvest_file_followups_literals(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_range_and_tracker(root)
            result = self._run_writer(
                root,
                archive_snapshot=self._archive_snapshot(),
                followups_schema_version="review.v1",
                followups_harvest_result="created/imported",
                followups_harvest_count=2,
            )
            receipt_path = root / f"docs/reviews/260505_1200_post_merge_operational_receipt_range_{B7}_{H7}.md"
            payload = json.loads(receipt_path.read_text(encoding="utf-8").split("```json", 1)[1].split("```", 1)[0])

        self.assertEqual(result.returncode, 0, result.stderr)
        reconciliation = payload["followups_lane_reconciliation"]
        self.assertEqual(reconciliation["harvest_file_followups_result"], "created/imported")
        self.assertEqual(reconciliation["harvest_file_followups_count"], 2)

    def test_writer_rejects_current_harvest_missing_literals_before_legacy_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_range_and_tracker(root)
            result = self._run_writer(
                root,
                archive_snapshot=self._archive_snapshot(),
                followups_schema_version="review.v1",
                include_current_followups_literals=False,
            )

        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid current source harvest receipt", result.stderr)
        self.assertIn("missing_harvest_file_followups_result", result.stderr)

    def test_writer_rejects_current_harvest_missing_idempotency_counter_before_legacy_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_range_and_tracker(root)
            self._write_followups_triage_launch_source(root, schema_version="review.v1")
            source_path = root / f"docs/reviews/260505_1200_plan_harvest_range_{B7}_{H7}.md"
            source_path.write_text(
                source_path.read_text(encoding="utf-8").replace(" | unparsed_bullets", ""),
                encoding="utf-8",
            )
            result = self._run_writer(
                root,
                archive_snapshot=self._archive_snapshot(),
                write_followups_receipt=False,
            )

        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid current source harvest receipt", result.stderr)
        self.assertIn("missing_harvest_file_followups_idempotency_counter", result.stderr)
        self.assertIn("unparsed_bullets", result.stderr)

    def test_writer_uses_default_output_path_when_out_is_omitted(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_range_and_tracker(root)

            result = self._run_writer(root, archive_snapshot=self._archive_snapshot(), out_path=None)

            self.assertEqual(result.returncode, 0, result.stderr)
            receipt_rel_path = result.stdout.strip()
            self.assertRegex(
                receipt_rel_path,
                rf"^docs/reviews/\d{{6}}_\d{{4}}_post_merge_operational_receipt_range_{B7}_{H7}\.md$",
            )
            receipt_path = root / receipt_rel_path
            matches = list(
                (root / "docs" / "reviews").glob(
                    f"*_post_merge_operational_receipt_range_{B7}_{H7}.md"
                )
            )
            self.assertEqual(matches, [receipt_path])
            self.assertNotEqual(receipt_path, root)
            self.assertTrue(receipt_path.is_file())
            payload = json.loads(receipt_path.read_text(encoding="utf-8").split("```json", 1)[1].split("```", 1)[0])

        self.assertEqual(payload["receipt_path"], receipt_rel_path)

    def test_writer_preserves_explicit_relative_and_absolute_output_paths(self) -> None:
        for path_kind in ("relative", "absolute"):
            with self.subTest(path_kind=path_kind), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                self._write_range_and_tracker(root)
                receipt_rel_path = (
                    f"docs/reviews/260505_1200_{path_kind}_post_merge_operational_receipt_range_{B7}_{H7}.md"
                )
                out_path = receipt_rel_path if path_kind == "relative" else str(root / receipt_rel_path)

                result = self._run_writer(root, archive_snapshot=self._archive_snapshot(), out_path=out_path)

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), receipt_rel_path)
                receipt_path = root / receipt_rel_path
                self.assertTrue(receipt_path.is_file())
                payload = json.loads(receipt_path.read_text(encoding="utf-8").split("```json", 1)[1].split("```", 1)[0])
                self.assertEqual(payload["receipt_path"], receipt_rel_path)

    def test_writer_requires_current_range_before_creating_default_output(self) -> None:
        for missing_name in (".planveyor.range.base", ".planveyor.range.head"):
            with self.subTest(missing_name=missing_name), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                self._write_range_and_tracker(root)
                missing_path = root / missing_name
                missing_path.unlink()

                result = self._run_writer(
                    root,
                    archive_snapshot=self._archive_snapshot(),
                    out_path=None,
                    write_suggest_stdout=False,
                    write_followups_receipt=False,
                )

                self.assertEqual(result.returncode, 2)
                self.assertIn(f"missing {missing_path}", result.stderr)
                self.assertFalse((root / "docs" / "reviews").exists())

    def test_writer_portabilizes_interpreters_with_explicit_portable_tool_paths(self) -> None:
        owner_home = self._owner_home()
        owner_python = owner_home + "/miniforge3/envs/planveyor/bin/python"
        owner_tooling = "${PLANVEYOR_ROOT:-$HOME/planveyor}"
        records = self._step_records()
        for record in records:
            if record["step"] == "docs_index_context":
                record["command"] = f"{owner_python} -B {owner_tooling}/scripts/docs_context_check.py --corpus plans"
            if record["step"] == "followups_triage_launch":
                record["command"] = (
                    f"planveyor_followups_triage --file docs/followups/260505_1200_followups_range_{B7}_{H7}.md "
                    "--dry-run; "
                    f"{owner_python} -B {owner_tooling}/scripts/followups_index_rebuild.py --project-root ."
                )
            if record["step"] == "planveyor_merge_bundle_report":
                record["command"] = f"{owner_python} -B {owner_tooling}/scripts/merge_bundle_report.py --format json"
        archive_snapshot = self._archive_snapshot(
            export_command=(
                f"{owner_python} -B {owner_tooling}/scripts/archive_snapshot_probe.py; "
                "planveyor_docs_archive_snapshot_export --backend git_text_export "
                "--output-dir docs/_meta/archive_snapshots/current --force"
            )
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_range_and_tracker(root)

            result = self._run_writer(
                root,
                archive_snapshot=archive_snapshot,
                records=records,
                content_profile_id="planveyor",
            )
            receipt_path = root / f"docs/reviews/260505_1200_post_merge_operational_receipt_range_{B7}_{H7}.md"
            receipt_text = receipt_path.read_text(encoding="utf-8")
            payload = json.loads(receipt_text.split("```json", 1)[1].split("```", 1)[0])

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(owner_home, receipt_text)
        self.assertNotIn("miniforge3/envs/planveyor/bin/python", receipt_text)
        self.assertIn(
            "python3 -B ${PLANVEYOR_ROOT:-$HOME/planveyor}/scripts/docs_context_check.py --corpus plans",
            receipt_text,
        )
        commands = {record["step"]: record["command"] for record in payload["steps"]}
        self.assertEqual(
            commands["docs_index_context"],
            "python3 -B ${PLANVEYOR_ROOT:-$HOME/planveyor}/scripts/docs_context_check.py --corpus plans",
        )
        self.assertIn(
            "python3 -B ${PLANVEYOR_ROOT:-$HOME/planveyor}/scripts/followups_index_rebuild.py --project-root .",
            commands["followups_triage_launch"],
        )
        self.assertEqual(payload["followups_triage_launch_receipt"]["command"], commands["followups_triage_launch"])
        self.assertEqual(
            payload["followups_lane_reconciliation"]["source_range_command"],
            commands["followups_triage_launch"],
        )
        self.assertIn(
            "python3 -B ${PLANVEYOR_ROOT:-$HOME/planveyor}/scripts/archive_snapshot_probe.py",
            payload["archive_snapshot"]["export_command"],
        )

    def test_generic_writer_does_not_select_owner_command_map(self) -> None:
        owner_home = self._owner_home()
        records = self._step_records()
        next(record for record in records if record["step"] == "docs_index_context")["command"] = (
            f"{owner_home}/miniforge3/envs/planveyor/bin/python -B "
            f"{owner_home}/planveyor/scripts/docs_context_check.py --corpus plans"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_range_and_tracker(root)
            result = self._run_writer(root, archive_snapshot=self._archive_snapshot(), records=records)
            receipt = (
                root / f"docs/reviews/260505_1200_post_merge_operational_receipt_range_{B7}_{H7}.md"
            ).read_text(encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"python3 -B {owner_home}/planveyor/scripts/docs_context_check.py", receipt)

    def test_writer_requires_archive_snapshot_export_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_range_and_tracker(root)

            result = self._run_writer(
                root,
                archive_snapshot=self._archive_snapshot(export_command="N/A (why=validate-only)"),
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("archive_snapshot: ok status requires export_command", result.stderr)

    def test_writer_normalizes_wrapper_docs_hygiene_command_pair(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_range_and_tracker(root)
            records = self._step_records()
            for record in records:
                if record["step"] == "docs_hygiene_suggest":
                    record["command"] = "planveyor_post_merge_docs_hygiene_suggest_gate"
                    break

            result = self._run_writer(root, archive_snapshot=self._archive_snapshot(), records=records)
            receipt_path = root / f"docs/reviews/260505_1200_post_merge_operational_receipt_range_{B7}_{H7}.md"
            payload = json.loads(receipt_path.read_text(encoding="utf-8").split("```json", 1)[1].split("```", 1)[0])

        self.assertEqual(result.returncode, 0, result.stderr)
        summary = payload["docs_hygiene_suggest_summary"]
        self.assertEqual(summary["command"], f"planveyor_docs_hygiene_suggest --range {BASE}..{HEAD}")
        self.assertEqual(summary["gate_command"], "planveyor_post_merge_docs_hygiene_suggest_gate")
        self.assertEqual(summary["suggested_owner_rerun_command"], f"planveyor_docs_hygiene_suggest --range {BASE}..{HEAD}")
        self.assertTrue(summary["report_only"])
        self.assertFalse(summary["deletion_executed"])
        self.assertFalse(summary["ready_to_push_ticked_by_suggest_gate"])

    def test_writer_records_no_candidate_docs_hygiene_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_range_and_tracker(root)

            result = self._run_writer(
                root,
                archive_snapshot=self._archive_snapshot(),
                suggest_stdout_paths=[],
            )
            receipt_path = root / f"docs/reviews/260505_1200_post_merge_operational_receipt_range_{B7}_{H7}.md"
            receipt_text = receipt_path.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"suggested_owner_command_items": 0', receipt_text)
        self.assertIn('"top_candidates": []', receipt_text)

    def test_writer_bounds_long_docs_hygiene_summary(self) -> None:
        paths = [f"docs/plans/260505_{index:04d}_done_plan.md" for index in range(22)]
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_range_and_tracker(root)

            result = self._run_writer(
                root,
                archive_snapshot=self._archive_snapshot(),
                suggest_stdout_paths=paths,
            )
            receipt_path = root / f"docs/reviews/260505_1200_post_merge_operational_receipt_range_{B7}_{H7}.md"
            payload = json.loads(receipt_path.read_text(encoding="utf-8").split("```json", 1)[1].split("```", 1)[0])

        self.assertEqual(result.returncode, 0, result.stderr)
        summary = payload["docs_hygiene_suggest_summary"]
        self.assertEqual(summary["candidate_counts"]["suggested_owner_command_items"], 22)
        self.assertEqual(len(summary["top_candidates"]), 20)
        self.assertEqual(summary["omitted_count"], 2)

    def test_writer_rejects_missing_docs_hygiene_stdout(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_range_and_tracker(root)

            result = self._run_writer(
                root,
                archive_snapshot=self._archive_snapshot(),
                write_suggest_stdout=False,
            )

        self.assertEqual(result.returncode, 2)
        self.assertIn("docs_hygiene_suggest_summary: source stdout missing on disk", result.stderr)

    def test_writer_rejects_malformed_docs_hygiene_stdout(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_range_and_tracker(root)

            result = self._run_writer(
                root,
                archive_snapshot=self._archive_snapshot(),
                malformed_suggest_stdout=True,
            )

        self.assertEqual(result.returncode, 2)
        self.assertIn("docs_hygiene_suggest_summary: source stdout missing Suggested", result.stderr)

    def test_writer_rejects_stale_docs_hygiene_stdout_range(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_range_and_tracker(root)

            result = self._run_writer(
                root,
                archive_snapshot=self._archive_snapshot(),
                suggest_stdout_range=f"{'c' * 40}..{HEAD}",
            )

        self.assertEqual(result.returncode, 2)
        self.assertIn("docs_hygiene_suggest_summary: stdout range=", result.stderr)

    def test_writer_rejects_unrelated_docs_hygiene_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_range_and_tracker(root)
            records = self._step_records()
            for record in records:
                if record["step"] == "docs_hygiene_suggest":
                    record["command"] = "planveyor_docs_hygiene_suggest"
                    break

            result = self._run_writer(root, archive_snapshot=self._archive_snapshot(), records=records)

        self.assertEqual(result.returncode, 2)
        self.assertIn("docs_hygiene_suggest_summary: command must be exact", result.stderr)

    def test_writer_rejects_missing_followups_launch_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_range_and_tracker(root)

            result = self._run_writer(
                root,
                archive_snapshot=self._archive_snapshot(),
                write_followups_receipt=False,
            )

        self.assertEqual(result.returncode, 2)
        self.assertIn("followups_triage_launch_receipt: source_harvest_receipt_path missing on disk", result.stderr)

    def test_writer_rejects_malformed_followups_launch_counts(self) -> None:
        records = self._step_records()
        for record in records:
            if record["step"] == "followups_triage_launch":
                record["count_summary"] = str(record["count_summary"]).replace("readback_status=ok; ", "")
                break
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_range_and_tracker(root)

            result = self._run_writer(root, archive_snapshot=self._archive_snapshot(), records=records)

        self.assertEqual(result.returncode, 2)
        self.assertIn("followups_triage_launch: count_summary missing field(s): readback_status", result.stderr)

    def test_writer_rejects_followups_file_mode_pointing_at_reviews(self) -> None:
        records = self._step_records()
        for record in records:
            if record["step"] == "followups_triage_launch":
                record["command"] = str(record["command"]).replace(
                    "docs/followups/260505_1200_followups_range_",
                    "docs/reviews/260505_1200_plan_harvest_range_",
                )
                break
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_range_and_tracker(root)

            result = self._run_writer(root, archive_snapshot=self._archive_snapshot(), records=records)

        self.assertEqual(result.returncode, 2)
        self.assertIn("command --file target must be a repo-relative docs/followups/*.md inbox", result.stderr)

    def test_writer_rejects_followups_file_mode_non_inbox_targets(self) -> None:
        invalid_targets = (
            "docs/followups/index.md",
            "docs/followups/process_followups_master.md",
            "docs/notes/not_followups.md",
        )
        for target in invalid_targets:
            with self.subTest(target=target):
                records = self._step_records()
                for record in records:
                    if record["step"] == "followups_triage_launch":
                        record["command"] = str(record["command"]).replace(
                            f"docs/followups/260505_1200_followups_range_{B7}_{H7}.md",
                            target,
                        )
                        break
                with tempfile.TemporaryDirectory() as tmpdir:
                    root = Path(tmpdir).resolve()
                    self._write_range_and_tracker(root)

                    result = self._run_writer(root, archive_snapshot=self._archive_snapshot(), records=records)

                self.assertEqual(result.returncode, 2)
                self.assertIn("command --file target must be a repo-relative docs/followups/*.md inbox", result.stderr)

    def test_writer_accepts_valid_range_mode_followups_launch(self) -> None:
        records = self._step_records()
        range_ref = f"{BASE}..{HEAD}"
        for record in records:
            if record["step"] == "followups_triage_launch":
                record["command"] = (
                    f"planveyor_followups_triage --range {range_ref} --dry-run; "
                    f"planveyor_followups_triage --range {range_ref} --apply; "
                    f"planveyor_followups_triage --range {range_ref} --apply; "
                    "scripts/followups_index_rebuild.py --project-root ."
                )
                record["count_summary"] = str(record["count_summary"]).replace(
                    "triage_mode=file",
                    "triage_mode=range",
                )
                record["count_summary"] += (
                    "; dry_run_unparsed_bullets=0; apply_unparsed_bullets=0; "
                    "idempotency_unparsed_bullets=0"
                )
                break
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_range_and_tracker(root)

            result = self._run_writer(root, archive_snapshot=self._archive_snapshot(), records=records)

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_writer_rejects_followups_launch_mode_mismatch(self) -> None:
        records = self._step_records()
        for record in records:
            if record["step"] == "followups_triage_launch":
                record["count_summary"] = str(record["count_summary"]).replace(
                    "triage_mode=file",
                    "triage_mode=range",
                )
                record["count_summary"] += (
                    "; dry_run_unparsed_bullets=0; apply_unparsed_bullets=0; "
                    "idempotency_unparsed_bullets=0"
                )
                break
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_range_and_tracker(root)

            result = self._run_writer(root, archive_snapshot=self._archive_snapshot(), records=records)

        self.assertEqual(result.returncode, 2)
        self.assertIn("command mode file does not match triage_mode=range", result.stderr)

    def test_writer_rejects_range_followups_launch_without_unparsed_counts(self) -> None:
        records = self._step_records()
        range_ref = f"{BASE}..{HEAD}"
        for record in records:
            if record["step"] == "followups_triage_launch":
                record["command"] = (
                    f"planveyor_followups_triage --range {range_ref} --dry-run; "
                    f"planveyor_followups_triage --range {range_ref} --apply; "
                    f"planveyor_followups_triage --range {range_ref} --apply; "
                    "scripts/followups_index_rebuild.py --project-root ."
                )
                record["count_summary"] = str(record["count_summary"]).replace(
                    "triage_mode=file",
                    "triage_mode=range",
                )
                break
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_range_and_tracker(root)

            result = self._run_writer(root, archive_snapshot=self._archive_snapshot(), records=records)

        self.assertEqual(result.returncode, 2)
        self.assertIn("count_summary missing field(s): dry_run_unparsed_bullets", result.stderr)

    def test_writer_rejects_unresolved_range_unparsed_followups_counts(self) -> None:
        records = self._step_records()
        range_ref = f"{BASE}..{HEAD}"
        for record in records:
            if record["step"] == "followups_triage_launch":
                record["command"] = (
                    f"planveyor_followups_triage --range {range_ref} --dry-run; "
                    f"planveyor_followups_triage --range {range_ref} --apply; "
                    f"planveyor_followups_triage --range {range_ref} --apply; "
                    "scripts/followups_index_rebuild.py --project-root ."
                )
                record["count_summary"] = str(record["count_summary"]).replace(
                    "triage_mode=file",
                    "triage_mode=range",
                )
                record["count_summary"] += (
                    "; dry_run_unparsed_bullets=0; apply_unparsed_bullets=0; "
                    "idempotency_unparsed_bullets=1"
                )
                break
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_range_and_tracker(root)

            result = self._run_writer(root, archive_snapshot=self._archive_snapshot(), records=records)

        self.assertEqual(result.returncode, 2)
        self.assertIn("count_summary.idempotency_unparsed_bullets must be 0 at final proof", result.stderr)

    def test_writer_rejects_unresolved_idempotency_followups_counts(self) -> None:
        records = self._step_records()
        for record in records:
            if record["step"] == "followups_triage_launch":
                record["count_summary"] = str(record["count_summary"]).replace(
                    "idempotency_possible_duplicate=0",
                    "idempotency_possible_duplicate=1",
                )
                break
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_range_and_tracker(root)

            result = self._run_writer(root, archive_snapshot=self._archive_snapshot(), records=records)

        self.assertEqual(result.returncode, 2)
        self.assertIn("count_summary.idempotency_possible_duplicate must be 0 at final proof", result.stderr)

    def test_writer_accepts_unresolved_followups_counts_with_manual_decision_ref(self) -> None:
        records = self._step_records()
        range_ref = f"{BASE}..{HEAD}"
        for record in records:
            if record["step"] == "followups_triage_launch":
                record["command"] = (
                    f"planveyor_followups_triage --range {range_ref} --dry-run; "
                    f"planveyor_followups_triage --range {range_ref} --apply; "
                    f"planveyor_followups_triage --range {range_ref} --apply; "
                    "scripts/followups_index_rebuild.py --project-root ."
                )
                record["count_summary"] = str(record["count_summary"]).replace(
                    "triage_mode=file",
                    "triage_mode=range",
                )
                record["count_summary"] += (
                    "; dry_run_unparsed_bullets=0; apply_unparsed_bullets=0; "
                    "idempotency_unparsed_bullets=1; "
                    "manual_decision_ref=docs/reviews/260505_1200_plan_harvest_range_aaaaaaa_bbbbbbb.md#manual-followups-decision"
                )
                break
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_range_and_tracker(root)

            result = self._run_writer(root, archive_snapshot=self._archive_snapshot(), records=records)
            receipt_path = root / f"docs/reviews/260505_1200_post_merge_operational_receipt_range_{B7}_{H7}.md"
            payload = json.loads(receipt_path.read_text(encoding="utf-8").split("```json", 1)[1].split("```", 1)[0])

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            payload["followups_triage_launch_receipt"]["manual_decision_ref"],
            "docs/reviews/260505_1200_plan_harvest_range_aaaaaaa_bbbbbbb.md#manual-followups-decision",
        )
        self.assertEqual(
            payload["followups_lane_reconciliation"]["manual_decision_ref"],
            "docs/reviews/260505_1200_plan_harvest_range_aaaaaaa_bbbbbbb.md#manual-followups-decision",
        )
        self.assertEqual(payload["followups_lane_reconciliation"]["range_unresolved_unparsed_bullets"], 1)

    def test_writer_rejects_unresolved_followups_counts_with_weak_manual_decision_ref(self) -> None:
        records = self._step_records()
        for record in records:
            if record["step"] == "followups_triage_launch":
                record["count_summary"] = str(record["count_summary"]).replace(
                    "idempotency_possible_duplicate=0",
                    "idempotency_possible_duplicate=1",
                )
                record["count_summary"] += "; manual_decision_ref=handled"
                break
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_range_and_tracker(root)

            result = self._run_writer(root, archive_snapshot=self._archive_snapshot(), records=records)

        self.assertEqual(result.returncode, 2)
        self.assertIn("count_summary.manual_decision_ref must be a durable docs/*.md ref", result.stderr)

    def test_writer_rejects_missing_followups_index_readback(self) -> None:
        records = self._step_records()
        for record in records:
            if record["step"] == "followups_triage_launch":
                record["count_summary"] = str(record["count_summary"]).replace(
                    "readback_status=ok",
                    "readback_status=missing",
                )
                break
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_range_and_tracker(root)

            result = self._run_writer(root, archive_snapshot=self._archive_snapshot(), records=records)

        self.assertEqual(result.returncode, 2)
        self.assertIn("followups_triage_launch: count_summary.readback_status must be ok", result.stderr)

    def test_writer_rejects_missing_process_improvements_open_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_range_and_tracker(root)
            self._write_docs_hygiene_suggest_stdout(root)
            self._write(
                root,
                f"docs/reviews/260505_1200_plan_harvest_range_{B7}_{H7}.md",
                dedent(
                    f"""\
                    # Plan harvest

                    **Status:** ✅ Done

                    ## Follow-up harvest triage/import receipt
                    - `planveyor_followups_triage --file docs/followups/260505_1200_followups_range_{B7}_{H7}.md --dry-run`: append_new=2, merge_source=0, possible_duplicate=0, route_fallback=0.
                    - `planveyor_followups_triage --file docs/followups/260505_1200_followups_range_{B7}_{H7}.md --apply`: append_new=2, merge_source=0, possible_duplicate=0, route_fallback=0.
                    - `scripts/followups_index_rebuild.py --project-root .`: status=ok; readback_status=ok.

                    ## Process-improvement promotion decisions
                    | source_ref | entry_id | raw_status | execution_kind | execution_ref | owner_or_next_step |
                    | --- | --- | --- | --- | --- | --- |
                    | `docs/process_improvements/promotion_surface.md` | `PI-001` | `open` | `null` | `null` | `Planner triage in process-improvement promotion lane` |
                    """
                ),
            )
            result = self._run_writer(
                root,
                archive_snapshot=self._archive_snapshot(),
                write_suggest_stdout=False,
                write_followups_receipt=False,
            )

        self.assertEqual(result.returncode, 2)
        self.assertIn("process_improvements_open_summary: source harvest receipt missing", result.stderr)

    def test_writer_rejects_missing_process_improvements_open_summary_for_bullet_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_range_and_tracker(root)
            self._write_docs_hygiene_suggest_stdout(root)
            self._write(
                root,
                f"docs/reviews/260505_1200_plan_harvest_range_{B7}_{H7}.md",
                dedent(
                    f"""\
                    # Plan harvest

                    **Status:** ✅ Done

                    ## Follow-up harvest triage/import receipt
                    - `planveyor_followups_triage --file docs/followups/260505_1200_followups_range_{B7}_{H7}.md --dry-run`: append_new=0, merge_source=0, possible_duplicate=0, route_fallback=0.
                    - `planveyor_followups_triage --file docs/followups/260505_1200_followups_range_{B7}_{H7}.md --apply`: append_new=0, merge_source=0, possible_duplicate=0, route_fallback=0.
                    - `scripts/followups_index_rebuild.py --project-root .`: status=ok; readback_status=ok.

                    ## Process-improvement promotion decisions
                    - Detected open raw rows, but this harvest keeps them in the PI lane:
                      - source_ref=`docs/plans/260517_1310_process_pending_followups_decision_wave.md`; entry_id=`PI-001`; raw_status=`open`; execution_kind=`null`; execution_ref=`null`; owner_or_next_step=`Planner triage in process-improvement promotion lane`.
                    """
                ),
            )
            result = self._run_writer(
                root,
                archive_snapshot=self._archive_snapshot(),
                write_suggest_stdout=False,
                write_followups_receipt=False,
            )

        self.assertEqual(result.returncode, 2)
        self.assertIn("process_improvements_open_summary: source harvest receipt missing", result.stderr)

    def test_writer_allows_no_open_pi_without_process_improvements_open_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_range_and_tracker(root)
            self._write_docs_hygiene_suggest_stdout(root)
            self._write(
                root,
                f"docs/reviews/260505_1200_plan_harvest_range_{B7}_{H7}.md",
                dedent(
                    f"""\
                    # Plan harvest

                    **Status:** ✅ Done

                    ## Follow-up harvest triage/import receipt
                    - `planveyor_followups_triage --file docs/followups/260505_1200_followups_range_{B7}_{H7}.md --dry-run`: append_new=0, merge_source=0, possible_duplicate=0, route_fallback=0.
                    - `planveyor_followups_triage --file docs/followups/260505_1200_followups_range_{B7}_{H7}.md --apply`: append_new=0, merge_source=0, possible_duplicate=0, route_fallback=0.
                    - `scripts/followups_index_rebuild.py --project-root .`: status=ok; readback_status=ok.

                    ## Process-improvement promotion decisions
                    - `N/A (why=no open/triaged/promoted process-improvement rows in range)`
                    """
                ),
            )
            result = self._run_writer(
                root,
                archive_snapshot=self._archive_snapshot(),
                write_suggest_stdout=False,
                write_followups_receipt=False,
            )
            receipt_path = root / f"docs/reviews/260505_1200_post_merge_operational_receipt_range_{B7}_{H7}.md"
            receipt_text = receipt_path.read_text(encoding="utf-8")
            payload = json.loads(receipt_text.split("```json", 1)[1].split("```", 1)[0])

        self.assertEqual(result.returncode, 0, result.stderr)
        pi_summary = payload["process_improvements_open_summary"]
        self.assertEqual(pi_summary["counts_by_raw_status"], {"open": 0, "promoted": 0, "triaged": 0})
        self.assertEqual(pi_summary["null_execution_rows"], 0)
        self.assertIn("no open/triaged/promoted", pi_summary["owner_or_next_step"])

    def test_writer_requires_archive_snapshot_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_range_and_tracker(root)

            result = self._run_writer(root, archive_snapshot=None)

        self.assertEqual(result.returncode, 2)
        self.assertIn("--archive-snapshot-json", result.stderr)

    def test_writer_allows_truthful_archive_snapshot_no_op(self) -> None:
        no_op_snapshot = self._archive_snapshot(
            status="no_op",
            storage_backend="N/A (why=no selected backend for range)",
            manifest_path="N/A (why=no archive candidates for current range)",
            artifact_path="N/A (why=no archive candidates for current range)",
            object_uri="N/A (why=no archive candidates for current range)",
            checksum="N/A (why=no archive candidates for current range)",
            access_status="not_required",
            restore_status="no_op",
            readback_status="no_op",
            no_op_reason="no_archive_candidates_for_current_range",
            blocker_reason="N/A (why=none)",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_range_and_tracker(root)

            result = self._run_writer(root, archive_snapshot=no_op_snapshot)

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_writer_rejects_generic_docs_index_no_op(self) -> None:
        records = self._step_records()
        for record in records:
            if record["step"] == "docs_index_context":
                record.update(
                    {
                        "command": "N/A (why=legacy profile skip)",
                        "result": "skipped",
                        "artifact_path": "N/A (why=legacy profile skip)",
                        "count_summary": "N/A (why=legacy profile skip)",
                        "no_op_reason": "not_applicable_repo_profile_no_separate_docs_index_context_gate",
                        "in_scope": "no",
                    }
                )
                break
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_range_and_tracker(root)

            result = self._run_writer(root, archive_snapshot=self._archive_snapshot(), records=records)

        self.assertEqual(result.returncode, 2)
        self.assertIn("docs_index_context: no_op_reason must be one of", result.stderr)

    def test_writer_rejects_low_retrieval_without_triage(self) -> None:
        records = self._step_records()
        for record in records:
            if record["step"] == "retrieval_metrics":
                record["count_summary"] = (
                    "query_total=100; evaluated_total=10; outcome_evaluated_rate=0.10; "
                    "read_log_status=present; read_events_total=1; read_open_rate=0.01; "
                    "used_for_decision=true"
                )
                break
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_range_and_tracker(root)

            result = self._run_writer(root, archive_snapshot=self._archive_snapshot(), records=records)

        self.assertEqual(result.returncode, 2)
        self.assertIn("retrieval_metrics: low coverage requires follow_up_ref or accepted_no_op_reason", result.stderr)

    def test_writer_accepts_telemetry_only_low_retrieval_with_no_op_reason(self) -> None:
        records = self._step_records()
        for record in records:
            if record["step"] == "retrieval_metrics":
                record["count_summary"] = (
                    "query_total=100; evaluated_total=10; outcome_evaluated_rate=0.10; "
                    "read_log_status=present; read_events_total=1; read_open_rate=0.01; "
                    "used_for_decision=false; accepted_no_op_reason=not_used_for_decision"
                )
                break
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_range_and_tracker(root)

            result = self._run_writer(root, archive_snapshot=self._archive_snapshot(), records=records)

        self.assertEqual(result.returncode, 0)

    def test_writer_rejects_telemetry_only_retrieval_without_no_op_reason(self) -> None:
        records = self._step_records()
        for record in records:
            if record["step"] == "retrieval_metrics":
                record["count_summary"] = (
                    "query_total=100; evaluated_total=10; outcome_evaluated_rate=0.10; "
                    "read_log_status=present; read_events_total=1; read_open_rate=0.01; "
                    "used_for_decision=false"
                )
                break
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_range_and_tracker(root)

            result = self._run_writer(root, archive_snapshot=self._archive_snapshot(), records=records)

        self.assertEqual(result.returncode, 2)
        self.assertIn(
            "retrieval_metrics: used_for_decision=false requires accepted_no_op_reason=not_used_for_decision",
            result.stderr,
        )

    def test_writer_rejects_snapshot_failure_disguised_as_no_op(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_range_and_tracker(root)

            result = self._run_writer(
                root,
                archive_snapshot=self._archive_snapshot(
                    status="no_op",
                    restore_status="no_op",
                    readback_status="no_op",
                    no_op_reason="current_db_migration_failed",
                ),
            )

        self.assertEqual(result.returncode, 2)
        self.assertIn("no_op status requires", result.stderr)

    def test_writer_rejects_secret_like_s3_snapshot_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_range_and_tracker(root)

            result = self._run_writer(
                root,
                archive_snapshot=self._archive_snapshot(
                    storage_backend="s3_minio_sqlite",
                    artifact_path="N/A (why=object-store backend)",
                    object_uri=(
                        "s3"
                        + "://"
                        + "AKIA"
                        + ":"
                        + "SECRET"
                        + "@"
                        + "example-bucket/archive.sqlite"
                    ),
                    access_status="ok",
                ),
            )

        self.assertEqual(result.returncode, 2)
        self.assertIn("object_uri appears to contain inline credentials", result.stderr)


if __name__ == "__main__":
    unittest.main()

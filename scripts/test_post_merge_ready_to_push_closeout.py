from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from textwrap import dedent
from unittest import mock


MODULE_PATH = Path(__file__).with_name("post_merge_ready_to_push_closeout.py")
SPEC = importlib.util.spec_from_file_location("post_merge_ready_to_push_closeout", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

import post_merge_packetization_gate


PACKETIZATION_NOW = datetime(2026, 5, 19, tzinfo=timezone.utc)
SHA256 = "b1df5fca0ca714f91180f4da82fa8392891c95dff8a49ec0ff3140cebd4c6f11"
DB_SHA256 = "c" * 64


class ReadyToPushCloseoutTests(unittest.TestCase):
    def test_closeout_schema_constant_reuses_merge_bundle_authority(self) -> None:
        self.assertEqual(
            MODULE.CLOSEOUT_RECEIPT_SCHEMA_VERSION,
            MODULE.merge_bundle_report.READY_TO_PUSH_CLOSEOUT_SCHEMA_VERSION,
        )
        self.assertEqual(MODULE.CLOSEOUT_RECEIPT_SCHEMA_VERSION, "ready_to_push_closeout_receipt.v1")

    def _git(self, root: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            text=True,
            capture_output=True,
            check=True,
        )
        return result.stdout.strip()

    def _init_repo(self, root: Path) -> tuple[str, str]:
        subprocess.run(["git", "-C", str(root), "init"], check=True, capture_output=True)
        self._git(root, "config", "user.email", 'test' + '@' + 'example' + '.' + 'com')
        self._git(root, "config", "user.name", "Test User")
        self._write(root, ".gitignore", ".planveyor.*\n.tmp/\n")
        self._write(root, "README.md", "seed\n")
        self._write(
            root,
            "docs/tools/owner_runbook_codex.md",
            "# Owner runbook\n\nseed\n",
        )
        base = self._commit_all(root, "seed")
        self._write(
            root,
            "docs/tools/owner_runbook_codex.md",
            "# Owner runbook\n\nsource-only change\n",
        )
        head = self._commit_all(root, "source-only owner runbook change")
        self.assertEqual(
            self._git(root, "rev-parse", "--verify", f"{base}^{{commit}}"),
            base,
        )
        self.assertEqual(
            self._git(root, "rev-parse", "--verify", f"{head}^{{commit}}"),
            head,
        )
        self.assertEqual(self._git(root, "merge-base", "--is-ancestor", base, head), "")
        self.assertEqual(
            self._git(root, "diff", "--name-only", f"{base}..{head}").splitlines(),
            ["docs/tools/owner_runbook_codex.md"],
        )
        return base, head

    def _write(self, root: Path, rel_path: str, body: str) -> Path:
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    def _commit_all(self, root: Path, message: str) -> str:
        self._git(root, "add", ".")
        self._git(root, "commit", "-m", message)
        return self._git(root, "rev-parse", "HEAD")

    def _write_tracker(
        self,
        root: Path,
        *,
        base: str,
        head: str,
        ready_checked: bool = False,
        review_range_checked: bool = False,
    ) -> None:
        self._write(root, ".planveyor.range.base", f"{base}\n")
        self._write(root, ".planveyor.range.head", f"{head}\n")
        ready_mark = "x" if ready_checked else " "
        review_line = "- [x] step:review_range\n" if review_range_checked else ""
        self._write(
            root,
            ".planveyor.merge_tracker.md",
            dedent(
                f"""\
                # Merge tracker

                BASE={base}
                HEAD={head}
                RANGE={base}..{head}
                RANGE_ID=range_{base[:7]}_{head[:7]}

                ## Checklist
                {review_line}\
                - [x] step:docs_hygiene_archive
                - [x] step:docs_hygiene_suggest
                - [{ready_mark}] step:ready_to_push
                """
            ),
        )

    def _archive_snapshot(self) -> dict[str, object]:
        return {
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
            "snapshot_created_at_utc": "2026-05-19T00:00:01+00:00",
            "snapshot_source_db_sha256": DB_SHA256,
            "snapshot_source_docs_count": "2",
        }

    def _operational_steps(self, *, base: str, head: str) -> list[dict[str, object]]:
        captured_at = "2026-05-19T00:00:00+00:00"

        def ran(step: str, command: str, artifact_path: str, count_summary: str) -> dict[str, object]:
            return {
                "step": step,
                "command": command,
                "exit_code": 0,
                "result": "ok",
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
            ran("docs_finalize", "planveyor_arch_docs_general", "docs/plans/fixture.md", "docs_changed=0"),
            ran("doc_lint", "bash ./scripts/run_doc_lint.sh --root docs/tools/prompts/manager_collab_merge_pipeline.md", "N/A (why=stdout only)", "errors=0"),
            ran("docs_hygiene_archive", f"planveyor_docs_hygiene_archive --range {base}..{head} --apply", ".tmp/docs_hygiene_archive.json", "inserted=0"),
            ran("docs_hygiene_suggest", f"planveyor_docs_hygiene_suggest --range {base}..{head}", ".tmp/docs_hygiene_suggest.md", "candidates=0"),
            skipped("docs_index_context", "not in scope for fixture"),
            skipped("retrieval_metrics", "no retrieval-backed evidence in fixture"),
            skipped("canon_sweep", "canon sweep not completed in fixture"),
            ran("planveyor_merge_bundle_report", "planveyor_merge_bundle_report", "N/A (why=read-only stdout)", "status=ok errors=0"),
        ]

    def _write_operational_receipt(self, root: Path, *, base: str, head: str) -> None:
        snapshot = self._archive_snapshot()
        self._write(root, str(snapshot["artifact_path"]), "artifact fixture\n")
        manifest = {
            "snapshot_manifest_version": snapshot["format_version"],
            "storage_backend": snapshot["storage_backend"],
            "created_at_utc": snapshot["snapshot_created_at_utc"],
            "artifact": {
                "path": Path(str(snapshot["artifact_path"])).name,
                "sha256": snapshot["checksum"],
                "record_count": int(str(snapshot["snapshot_source_docs_count"])),
            },
            "source_db": {
                "db_sha256": snapshot["snapshot_source_db_sha256"],
                "docs_count": int(str(snapshot["snapshot_source_docs_count"])),
            },
        }
        self._write(root, str(snapshot["manifest_path"]), json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        payload = {
            "schema_version": "post_merge_operational_receipt.v1",
            "range": f"{base}..{head}",
            "base": base,
            "head": head,
            "tracker_path": ".planveyor.merge_tracker.md",
            "generated_at": "2026-05-19T00:00:00+00:00",
            "generated_by": "scripts/post_merge_operational_receipt.py",
            "receipt_path": f"docs/reviews/260519_0000_post_merge_operational_receipt_range_{base[:7]}_{head[:7]}.md",
            "archive_snapshot": snapshot,
            "steps": self._operational_steps(base=base, head=head),
        }
        self._write(
            root,
            f"docs/reviews/260519_0000_post_merge_operational_receipt_range_{base[:7]}_{head[:7]}.md",
            dedent(
                f"""\
                # Post-merge operational receipt

                **Status:** \u2705 Done

                ## Operational receipt JSON
                ```json
                {json.dumps(payload, indent=2, sort_keys=True)}
                ```
                """
            ),
        )

    def _range_target(self, *, base: str, head: str) -> str:
        return f"RANGE={base}..{head} (EXCLUDE_DOCS=0)"

    def _write_origin_plan(self, root: Path, *, base: str, head: str) -> str:
        rel_path = "docs/plans/260519_0000_reviewer_range_plan.md"
        payload = {
            "lane_id": "reviewer_code_risk",
            "target_snapshot": self._range_target(base=base, head=head),
            "lane_status": "no_findings",
            "current": True,
            "written_at": "2026-05-19T00:00:00Z",
        }
        self._write(
            root,
            rel_path,
            "# Plan\n\n**Status:** Done\n\n## Evidence\n```json\n"
            + json.dumps(payload, indent=2, sort_keys=True)
            + "\n```\n",
        )
        return rel_path

    def _packetization_report_path(self, *, base: str, head: str) -> str:
        return (
            "docs/reviews/260519_0002_packetization_gate_range_"
            f"{base[:7]}_{head[:7]}.md"
        )

    def _write_packetization_report(self, root: Path, *, base: str, head: str) -> str:
        report_path = self._packetization_report_path(base=base, head=head)
        range_ref = f"{base}..{head}"
        changed_files = post_merge_packetization_gate.changed_files_for_range(root, range_ref)
        self.assertEqual(changed_files, ["docs/tools/owner_runbook_codex.md"])
        packet_payload = post_merge_packetization_gate.build_payload(
            root,
            range_ref=range_ref,
            changed_files=changed_files,
            create_drafts=False,
            source_revision=head,
            now=PACKETIZATION_NOW,
        )
        packet_payload["report_path"] = report_path
        self.assertEqual(packet_payload["range"], range_ref)
        self.assertEqual(packet_payload["source_range"], range_ref)
        self.assertEqual(packet_payload["source_revision"], head)
        self.assertEqual(
            packet_payload["rows"],
            [
                {
                    "changed_file": "docs/tools/owner_runbook_codex.md",
                    "target_repo": "current-consumer",
                    "target_kind": "source_only",
                    "target_source_artifacts": [],
                    "target_writable_carriers": [],
                    "authority": "checked-in source-only root policy",
                    "packet_path": "N/A",
                    "packet_status": "N/A",
                    "target_adoption_state": "N/A",
                    "coverage": "source_only",
                    "blocking": False,
                    "action": "owner runbook is planveyor operator guidance",
                }
            ],
        )
        self.assertEqual(packet_payload["blocking_count"], 0)
        self.assertEqual(packet_payload["blocking_rows_count"], 0)
        self.assertEqual(packet_payload["blocking_coverages"], [])
        self.assertEqual(
            packet_payload["blocking_coverage_counts"],
            {
                "legacy-create-drafts-refused": 0,
                "missing-packet": 0,
                "source_only": 1,
                "unknown_target_mapping": 0,
            },
        )
        self._write(
            root,
            report_path,
            post_merge_packetization_gate.render_report(packet_payload),
        )
        return report_path

    def _write_risk_packet_truth_hosts(self, root: Path, *, base: str, head: str) -> dict[str, str]:
        b7 = base[:7]
        h7 = head[:7]
        plan_rel = self._write_origin_plan(root, base=base, head=head)
        paths = {
            "review_artifact": f"docs/code_reviews/260519_0000_reviewer_range_{b7}_{h7}.md",
            "post_merge_audit": f"docs/reviews/260519_0001_post_merge_audit_range_{b7}_{h7}.md",
        }
        self._write(
            root,
            paths["review_artifact"],
            dedent(
                f"""\
                # Review

                **Status:** ✅ OK
                **Target:** {self._range_target(base=base, head=head)}
                **Spec:** {plan_rel}

                ## S1 Blocker

                N/A (why=fixture green review)

                ## S2 Risk

                N/A (why=fixture)

                ## Визуальные доказательства

                - Visual env: `N/A (why=process helper)`
                """
            ),
        )
        self._write(root, paths["post_merge_audit"], "# Post-merge audit\n\n**Status:** ✅ Done\n\n`review.post_merge_audit`\n")
        paths["packetization_report"] = self._write_packetization_report(
            root,
            base=base,
            head=head,
        )
        return paths

    def _write_ready_closeout_receipt(self, root: Path, *, base: str, head: str) -> str:
        path = f"docs/reviews/260519_0003_ready_to_push_closeout_range_{base[:7]}_{head[:7]}.md"
        payload = {
            "schema_version": "ready_to_push_closeout_receipt.v1",
            "range": f"{base}..{head}",
            "base": base,
            "head": head,
            "range_id": f"{base[:7]}..{head[:7]}",
            "tracker_path": ".planveyor.merge_tracker.md",
            "generated_at_utc": "2026-06-07T11:30:00+00:00",
            "generated_by": "scripts/post_merge_ready_to_push_closeout.py",
            "source_command": "planveyor_post_merge_ready_to_push_closeout",
            "terminal_state": "terminal_ready_to_push_proof",
            "final_bundle_status": "ok",
            "required_paths": [
                f"docs/reviews/260519_0000_post_merge_operational_receipt_range_{base[:7]}_{head[:7]}.md"
            ],
            "contextual_paths": [],
            "staged_accepted_paths": [path],
            "staged_paths_at_closeout": [path],
            "unexpected_staged_paths": [],
            "suspicious_paths": [],
            "unstaged_tracked_paths": [],
            "untracked_accepted_paths": [],
            "action": "local_commit_and_tracker_tick",
            "tracker_tick": {"intent": "tick step:ready_to_push before committing terminal proof", "result": "ticked"},
            "pending_owner_gate": "git push",
        }
        self._write(
            root,
            path,
            "# Ready-to-push closeout\n\n**Status:** ✅ Done\n\n## Ready-to-push closeout receipt JSON\n```json\n"
            + json.dumps(payload, indent=2, sort_keys=True)
            + "\n```\n",
        )
        return path

    def _write_existing_risk_packet(
        self,
        root: Path,
        closeout_path: str,
        *,
        base: str,
        head: str,
        target_snapshot: str | None = None,
    ) -> str:
        b7 = base[:7]
        h7 = head[:7]
        hosts = {
            "review_artifact": f"docs/code_reviews/260519_0000_reviewer_range_{b7}_{h7}.md",
            "post_merge_audit": f"docs/reviews/260519_0001_post_merge_audit_range_{b7}_{h7}.md",
            "operational_receipt": f"docs/reviews/260519_0000_post_merge_operational_receipt_range_{b7}_{h7}.md",
            "packetization_report": f"docs/reviews/260519_0002_packetization_gate_range_{b7}_{h7}.md",
            "ready_to_push_closeout": closeout_path,
        }
        payload = {
            "schema_version": "range_review_risk_packet.v1",
            "packet_status": "ok",
            "range": f"{base}..{head}",
            "range_id": f"{b7}..{h7}",
            "base": base,
            "head": head,
            "target_snapshot": target_snapshot or self._range_target(base=base, head=head),
            "runtime_touched_paths": [],
            "helper_process_touched_paths": [],
            "visual_status": {"status": "N/A", "reason": "fixture"},
            "live_blockers": [],
            "historical_blockers": [],
            "closure_artifacts": [{"kind": key, "path": value} for key, value in hosts.items() if key != "review_artifact"],
            "residual_risks": [],
            "truth_hosts": {key: {"path": value, "status": "✅ Done"} for key, value in hosts.items()},
        }
        path = f"docs/reviews/260519_0003_risk_packet_range_{b7}_{h7}.md"
        self._write(
            root,
            path,
            "# Range review risk packet\n\n**Status:** ✅ Done\n\n## Risk packet JSON\n```json\n"
            + json.dumps({"risk_packet": payload}, indent=2, sort_keys=True)
            + "\n```\n",
        )
        return path

    def _write_malformed_risk_packet(
        self,
        root: Path,
        *,
        stamp: str,
        base: str,
        head: str,
    ) -> str:
        path = f"docs/reviews/{stamp}_risk_packet_range_{base[:7]}_{head[:7]}.md"
        self._write(
            root,
            path,
            "# Range review risk packet\n\n**Status:** ✅ Done\n\n## Risk packet JSON\n```json\n{\"risk_packet\": \n```\n",
        )
        return path

    def _ready_fixture(
        self,
        root: Path,
        *,
        ready_checked: bool = False,
        review_range_checked: bool = False,
    ) -> tuple[str, str]:
        base, head = self._init_repo(root)
        self._write_tracker(
            root,
            base=base,
            head=head,
            ready_checked=ready_checked,
            review_range_checked=review_range_checked,
        )
        self._write_risk_packet_truth_hosts(root, base=base, head=head)
        self._write_operational_receipt(root, base=base, head=head)
        if ready_checked:
            closeout_path = self._write_ready_closeout_receipt(root, base=base, head=head)
            self._write_existing_risk_packet(root, closeout_path, base=base, head=head)
        artifact_head = self._commit_all(root, "operational receipt")
        self.assertNotEqual(artifact_head, head)
        if not review_range_checked:
            report = MODULE.merge_bundle_report.build_report(root)
            self.assertEqual(report["errors"], [], report)
        return base, head

    def _stage_expected_doc(self, root: Path, rel_path: str = "docs/reviews/260519_0001_closeout_note.md") -> str:
        self._write(root, rel_path, "# Closeout note\n\n**Status:** Done\n")
        self._git(root, "add", rel_path)
        return rel_path

    def _tracker_text(self, root: Path) -> str:
        return (root / ".planveyor.merge_tracker.md").read_text(encoding="utf-8")

    def _staged_blob_id(self, root: Path, rel_path: str) -> str:
        return self._git(root, "rev-parse", f":{rel_path}")

    def test_green_closeout_commits_staged_contextual_bundle_and_ticks_ready_to_push(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            base, head = self._ready_fixture(root)
            staged_path = self._stage_expected_doc(root)

            result = MODULE.close_ready_to_push(root)

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["action"], "committed")
            self.assertRegex(result["message"], rf"^\d{{6}} - process: close post-merge range {base[:7]}\.\.{head[:7]}$")
            self.assertIn("- [x] step:ready_to_push", self._tracker_text(root))
            self.assertEqual(self._git(root, "log", "-1", "--pretty=%s"), result["message"])
            committed_paths = set(self._git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").splitlines())
            receipt_path = result["closeout_receipt_path"]
            risk_packet_path = result["risk_packet_path"]
            self.assertIn(staged_path, committed_paths)
            self.assertIn(receipt_path, committed_paths)
            self.assertIn(risk_packet_path, committed_paths)
            self.assertTrue(receipt_path.startswith("docs/reviews/"))
            self.assertIn("_ready_to_push_closeout_range_", receipt_path)
            self.assertIn("_risk_packet_range_", risk_packet_path)
            receipt_text = (root / receipt_path).read_text(encoding="utf-8")
            self.assertIn("ready_to_push_closeout_receipt.v1", receipt_text)
            self.assertIn("terminal_ready_to_push_proof", receipt_text)
            self.assertIn('"pending_owner_gate": "git push"', receipt_text)
            risk_packet_text = (root / risk_packet_path).read_text(encoding="utf-8")
            self.assertIn("range_review_risk_packet.v1", risk_packet_text)
            self.assertEqual(result["terminal_state"], "terminal_ready_to_push_proof")
            self.assertEqual(result["risk_packet_state"], "ok")
            self.assertEqual(result["pending_owner_gate"], "git push")
            post_report = MODULE.merge_bundle_report.build_report(root)
            self.assertEqual(post_report["status"], "ok")
            self.assertEqual(
                post_report["ready_to_push_terminal_proof"]["state"],
                "terminal_ready_to_push_proof",
            )
            self.assertNotIn("staging_diagnostics", result)

    def test_current_shaped_review_target_blocks_before_packet_write_stage_or_terminal_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            base, head = self._ready_fixture(root)
            staged_path = self._stage_expected_doc(root)
            review_path = root / f"docs/code_reviews/260519_0000_reviewer_range_{base[:7]}_{head[:7]}.md"
            review_path.write_text(
                review_path.read_text(encoding="utf-8").replace(
                    self._range_target(base=base, head=head),
                    "BUNDLE=current",
                    1,
                ),
                encoding="utf-8",
            )
            self._git(root, "add", str(review_path.relative_to(root)))
            before_head = self._git(root, "rev-parse", "HEAD")
            before_tree = self._git(root, "write-tree")

            result = MODULE.close_ready_to_push(root)

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["blocker"]["code"], "missing_risk_packet_before_ready_to_push")
            self.assertIn("risk_packet_target_mismatch", json.dumps(result, ensure_ascii=False))
            self.assertEqual(self._git(root, "rev-parse", "HEAD"), before_head)
            self.assertEqual(self._git(root, "write-tree"), before_tree)
            self.assertTrue((root / staged_path).exists())
            self.assertFalse(list((root / "docs/reviews").glob(f"*_risk_packet_range_{base[:7]}_{head[:7]}.md")))
            self.assertFalse(list((root / "docs/reviews").glob(f"*_ready_to_push_closeout_range_{base[:7]}_{head[:7]}.md")))

    def test_suspicious_staged_file_blocks_without_commit_or_tick(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._ready_fixture(root)
            self._write(root, "scripts/unrelated.py", "print('x')\n")
            self._git(root, "add", "scripts/unrelated.py")
            before = self._git(root, "rev-parse", "HEAD")

            result = MODULE.close_ready_to_push(root)
            plain = MODULE.render_plain(result)

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["blocker"]["code"], "suspicious_paths")
            self.assertIn("scripts/unrelated.py", result["blocker"]["paths"])
            diagnostics = result["staging_diagnostics"]
            self.assertEqual(diagnostics["primary_blocker_code"], "suspicious_paths")
            self.assertNotEqual(diagnostics["recommended_action"], MODULE.DIRTY_ACCEPTED_RECOVERY)
            self.assertIn("scripts/unrelated.py", diagnostics["suspicious_paths"])
            self.assertIn("scripts/unrelated.py", diagnostics["unexpected_staged_paths"])
            self.assertEqual(result["why_blocked"], "suspicious_paths")
            self.assertEqual(result["staging_command"], MODULE.NO_STAGING_COMMAND)
            self.assertEqual(result["pathspec_file"], MODULE.NO_PATHSPEC_FILE)
            self.assertEqual(result["pathspec_paths_count"], 0)
            self.assertEqual(result["pending_owner_gate"], "git push")
            self.assertIn("pending_owner_gate: git push", plain)
            self.assertEqual(self._git(root, "rev-parse", "HEAD"), before)
            self.assertIn("- [ ] step:ready_to_push", self._tracker_text(root))

    def test_unstaged_tracked_diff_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._ready_fixture(root)
            rel_path = "docs/reviews/tracked_context.md"
            self._write(root, rel_path, "clean\n")
            self._commit_all(root, "tracked context")
            self._write(root, rel_path, "dirty\n")

            result = MODULE.close_ready_to_push(root)

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["blocker"]["code"], "unstaged_tracked_paths")
            self.assertIn(rel_path, result["blocker"]["paths"])
            diagnostics = result["staging_diagnostics"]
            self.assertEqual(diagnostics["primary_blocker_code"], "unstaged_tracked_paths")
            self.assertEqual(diagnostics["recommended_action"], MODULE.DIRTY_ACCEPTED_RECOVERY)
            self.assertIn(rel_path, diagnostics["unstaged_tracked_paths"])
            self.assertEqual(result["why_blocked"], "dirty_report_accepted_paths")
            self.assertEqual(result["staging_command"], f"git add -- {rel_path}")
            self.assertEqual(result["pathspec_file"], "N/A (why=short git add command emitted)")
            self.assertEqual(result["pathspec_file_format"], "N/A (why=short git add command emitted)")
            self.assertEqual(result["pathspec_paths_count"], 1)
            self.assertEqual(result["pending_owner_gate"], "git push")

    def test_untracked_relevant_doc_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._ready_fixture(root)
            rel_path = "docs/reviews/untracked_context.md"
            self._write(root, rel_path, "# untracked\n")

            result = MODULE.close_ready_to_push(root)

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["blocker"]["code"], "untracked_paths")
            self.assertIn(rel_path, result["blocker"]["paths"])
            diagnostics = result["staging_diagnostics"]
            self.assertEqual(diagnostics["primary_blocker_code"], "untracked_paths")
            self.assertEqual(diagnostics["recommended_action"], MODULE.DIRTY_ACCEPTED_RECOVERY)
            self.assertIn(rel_path, diagnostics["untracked_accepted_paths"])
            self.assertEqual(result["why_blocked"], "dirty_report_accepted_paths")
            self.assertEqual(result["staging_command"], f"git add -- {rel_path}")
            self.assertEqual(result["pathspec_paths_count"], 1)

    def test_mixed_dirty_state_reports_unstaged_and_untracked_accepted_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._ready_fixture(root)
            tracked_path = "docs/reviews/tracked_context.md"
            untracked_path = "docs/reviews/untracked_context.md"
            self._write(root, tracked_path, "clean\n")
            self._commit_all(root, "tracked context")
            staged_path = self._stage_expected_doc(root)
            self._write(root, tracked_path, "dirty\n")
            self._write(root, untracked_path, "# untracked\n")

            result = MODULE.close_ready_to_push(root)
            plain = MODULE.render_plain(result)

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["blocker"]["code"], "unstaged_tracked_paths")
        diagnostics = result["staging_diagnostics"]
        self.assertEqual(diagnostics["primary_blocker_code"], "unstaged_tracked_paths")
        self.assertEqual(diagnostics["recommended_action"], MODULE.DIRTY_ACCEPTED_RECOVERY)
        self.assertIn(staged_path, diagnostics["staged_accepted_paths"])
        self.assertIn(tracked_path, diagnostics["unstaged_tracked_paths"])
        self.assertIn(untracked_path, diagnostics["untracked_accepted_paths"])
        self.assertIn(tracked_path, diagnostics["contextual_paths"])
        self.assertIn(untracked_path, diagnostics["contextual_paths"])
        self.assertEqual(result["why_blocked"], "dirty_report_accepted_paths")
        self.assertEqual(
            result["staging_command"],
            f"git add -- {tracked_path} {untracked_path}",
        )
        self.assertEqual(result["pathspec_paths_count"], 2)
        self.assertIn("staging_diagnostics:", plain)
        self.assertIn("why_blocked: dirty_report_accepted_paths", plain)
        self.assertIn(f"staging_command: git add -- {tracked_path} {untracked_path}", plain)
        self.assertIn("pending_owner_gate: git push", plain)
        self.assertIn("recommended_action: stage all report-accepted paths and rerun", plain)
        self.assertIn(tracked_path, plain)
        self.assertIn(untracked_path, plain)

    def test_long_dirty_accepted_paths_emit_nul_pathspec_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            base, head = self._ready_fixture(root)
            paths = [f"docs/reviews/untracked_context_{index:02d}.md" for index in range(9)]
            for rel_path in paths:
                self._write(root, rel_path, "# untracked\n")

            result = MODULE.close_ready_to_push(root)

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["blocker"]["code"], "untracked_paths")
            self.assertEqual(result["why_blocked"], "dirty_report_accepted_paths")
            self.assertEqual(result["pathspec_paths_count"], len(paths))
            self.assertEqual(result["pathspec_file_format"], MODULE.PATHSPEC_FILE_FORMAT_NUL)
            self.assertEqual(
                result["pathspec_file"],
                f".tmp/planveyor_ready_to_push_closeout/{base[:7]}..{head[:7]}/accepted_paths.pathspec",
            )
            self.assertEqual(
                result["staging_command"],
                f"git add --pathspec-from-file {result['pathspec_file']} --pathspec-file-nul",
            )
            pathspec_bytes = (root / result["pathspec_file"]).read_bytes()
            self.assertEqual(pathspec_bytes.split(b"\0")[:-1], [path.encode("utf-8") for path in paths])
            self.assertTrue(pathspec_bytes.endswith(b"\0"))

    def test_missing_operational_receipt_blocks_as_red_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            base, head = self._init_repo(root)
            self._write_tracker(root, base=base, head=head)

            result = MODULE.close_ready_to_push(root)

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["blocker"]["code"], "red_report")
            self.assertIn("missing_required_receipt", {error["code"] for error in result["blocker"]["report_errors"]})
            self.assertNotEqual(
                result["staging_diagnostics"]["recommended_action"],
                MODULE.DIRTY_ACCEPTED_RECOVERY,
            )
            self.assertEqual(result["why_blocked"], "red_merge_bundle_report")
            self.assertEqual(result["staging_command"], MODULE.NO_STAGING_COMMAND)
            self.assertEqual(result["pathspec_paths_count"], 0)

    def test_runtime_visual_authority_error_from_report_blocks_ready_to_push(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            base, head = self._init_repo(root)
            self._write_tracker(root, base=base, head=head)
            report = {
                "status": "blocked",
                "errors": [
                    {
                        "code": "post_merge_audit_authority_blocked",
                        "detail": "runtime_ui_visual_evidence_red",
                    }
                ],
                "git_status": {"required": [], "candidate_contextual": [], "suspicious": []},
                "tracker": {"steps": [], "current_step": "step:ready_to_push"},
            }
            with mock.patch.object(MODULE.merge_bundle_report, "build_report", return_value=report):
                result = MODULE.close_ready_to_push(root)

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["blocker"]["code"], "red_report")
        self.assertEqual(result["why_blocked"], "red_merge_bundle_report")
        self.assertIn(
            "post_merge_audit_authority_blocked",
            {error["code"] for error in result["blocker"]["report_errors"]},
        )

    def test_missing_risk_packet_truth_hosts_blocks_before_closeout_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            base, head = self._init_repo(root)
            self._write_tracker(root, base=base, head=head)
            self._write_operational_receipt(root, base=base, head=head)
            self._write_packetization_report(root, base=base, head=head)
            self._commit_all(root, "operational receipt without packet truth hosts")
            before = self._git(root, "rev-parse", "HEAD")

            result = MODULE.close_ready_to_push(root)

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["blocker"]["code"], "missing_risk_packet_before_ready_to_push")
            self.assertIn("missing_truth_hosts", result["blocker"]["detail"])
            self.assertEqual(self._git(root, "rev-parse", "HEAD"), before)
            self.assertIn("- [ ] step:ready_to_push", self._tracker_text(root))
            working_paths = [path.as_posix() for path in (root / "docs/reviews").glob("*_ready_to_push_closeout_range_*.md")]
            self.assertEqual(working_paths, [])
            risk_paths = [path.as_posix() for path in (root / "docs/reviews").glob("*_risk_packet_range_*.md")]
            self.assertEqual(risk_paths, [])

    def test_preexisting_ambiguous_risk_packets_block_before_tick_or_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            base, head = self._ready_fixture(root)
            self._write_malformed_risk_packet(root, stamp="260519_0003", base=base, head=head)
            self._write_malformed_risk_packet(root, stamp="260519_0004", base=base, head=head)
            self._commit_all(root, "preexisting ambiguous risk packets")
            before = self._git(root, "rev-parse", "HEAD")

            result = MODULE.close_ready_to_push(root)

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["blocker"]["code"], "ambiguous_risk_packet_before_ready_to_push")
            self.assertIn("ambiguous_risk_packet", {error["code"] for error in result["blocker"]["report_errors"]})
            self.assertEqual(self._git(root, "rev-parse", "HEAD"), before)
            self.assertIn("- [ ] step:ready_to_push", self._tracker_text(root))
            closeout_paths = list((root / "docs/reviews").glob("*_ready_to_push_closeout_range_*.md"))
            self.assertEqual(closeout_paths, [])

    def test_preexisting_unparseable_risk_packet_blocks_before_tick_or_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            base, head = self._ready_fixture(root)
            risk_path = self._write_malformed_risk_packet(
                root,
                stamp="260519_0003",
                base=base,
                head=head,
            )
            self._commit_all(root, "preexisting unparseable risk packet")
            before = self._git(root, "rev-parse", "HEAD")

            result = MODULE.close_ready_to_push(root)

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["blocker"]["code"], "invalid_risk_packet_before_ready_to_push")
            self.assertEqual(result["blocker"]["paths"], [risk_path])
            self.assertIn("unparseable_risk_packet", {error["code"] for error in result["blocker"]["report_errors"]})
            self.assertEqual(self._git(root, "rev-parse", "HEAD"), before)
            self.assertIn("- [ ] step:ready_to_push", self._tracker_text(root))
            closeout_paths = list((root / "docs/reviews").glob("*_ready_to_push_closeout_range_*.md"))
            self.assertEqual(closeout_paths, [])

    def test_stale_tracker_range_blocks_as_red_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._ready_fixture(root)
            self._write(root, ".planveyor.range.head", f"{'c' * 40}\n")

            result = MODULE.close_ready_to_push(root)

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["blocker"]["code"], "red_report")
            self.assertIn("range_mismatch", {error["code"] for error in result["blocker"]["report_errors"]})
            self.assertNotEqual(
                result["staging_diagnostics"]["recommended_action"],
                MODULE.DIRTY_ACCEPTED_RECOVERY,
            )
            self.assertEqual(result["why_blocked"], "red_merge_bundle_report")
            self.assertEqual(result["staging_command"], MODULE.NO_STAGING_COMMAND)

    def test_red_bundle_report_blocks_before_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._ready_fixture(root, review_range_checked=True)
            self._stage_expected_doc(root)
            before = self._git(root, "rev-parse", "HEAD")

            result = MODULE.close_ready_to_push(root)

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["blocker"]["code"], "red_report")
            self.assertIn("missing_required_artifact", {error["code"] for error in result["blocker"]["report_errors"]})
            self.assertEqual(self._git(root, "rev-parse", "HEAD"), before)

    def test_ready_step_without_existing_bundle_commits_terminal_receipt_and_ticks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._ready_fixture(root)
            before = self._git(root, "rev-parse", "HEAD")

            result = MODULE.close_ready_to_push(root)

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["action"], "committed")
            self.assertNotEqual(result["commit"], before)
            self.assertEqual(self._git(root, "rev-parse", "HEAD"), result["commit"])
            committed_paths = set(self._git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").splitlines())
            self.assertEqual(committed_paths, {result["closeout_receipt_path"], result["risk_packet_path"]})
            self.assertIn("- [x] step:ready_to_push", self._tracker_text(root))
            self.assertNotIn("staging_diagnostics", result)

    def test_already_closed_is_idempotent_when_tracker_is_done(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._ready_fixture(root, ready_checked=True)
            before = self._git(root, "rev-parse", "HEAD")

            result = MODULE.close_ready_to_push(root)

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["action"], "already_closed")
            self.assertEqual(result["commit"], before)
            self.assertEqual(self._git(root, "rev-parse", "HEAD"), before)
            self.assertNotIn("staging_diagnostics", result)

    def test_head_readback_timeout_blocks_without_reporting_empty_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._ready_fixture(root, ready_checked=True)
            before = self._git(root, "rev-parse", "HEAD")
            original_diagnostic = MODULE._run_git_diagnostic

            def timeout_head(root_arg: Path, *args: str) -> tuple[int, str, str]:
                if args == ("rev-parse", "HEAD"):
                    return MODULE.GIT_TIMEOUT_RETURN_CODE, "", "git rev-parse HEAD timed out after 30s"
                return original_diagnostic(root_arg, *args)

            with mock.patch.object(MODULE, "_run_git_diagnostic", side_effect=timeout_head):
                result = MODULE.close_ready_to_push(root)

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["blocker"]["code"], "git_head_readback_failed")
            self.assertIn("timed out after 30s", result["blocker"]["detail"])
            self.assertIsNone(result["commit"])
            self.assertEqual(self._git(root, "rev-parse", "HEAD"), before)

    def test_tracker_tick_failure_blocks_before_terminal_receipt_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._ready_fixture(root)
            before = self._git(root, "rev-parse", "HEAD")

            with mock.patch.object(MODULE, "_tick_ready_step", side_effect=ValueError("tick failed")):
                result = MODULE.close_ready_to_push(root)

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["blocker"]["code"], "tracker_tick_failed")
            self.assertEqual(self._git(root, "rev-parse", "HEAD"), before)
            committed_paths = self._git(root, "ls-tree", "-r", "--name-only", "HEAD").splitlines()
            self.assertFalse(any("_ready_to_push_closeout_range_" in path for path in committed_paths))
            working_paths = [path.as_posix() for path in (root / "docs/reviews").glob("*_ready_to_push_closeout_range_*.md")]
            self.assertEqual(working_paths, [])

    def test_preflight_cached_diff_timeout_blocks_before_tracker_tick(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._ready_fixture(root)
            before = self._git(root, "rev-parse", "HEAD")
            original_diagnostic = MODULE._run_git_diagnostic

            def timeout_preflight(root_arg: Path, *args: str) -> tuple[int, str, str]:
                if args == ("diff", "--cached", "--name-only"):
                    return MODULE.GIT_TIMEOUT_RETURN_CODE, "", "git diff --cached --name-only timed out after 30s"
                return original_diagnostic(root_arg, *args)

            with mock.patch.object(MODULE, "_run_git_diagnostic", side_effect=timeout_preflight):
                result = MODULE.close_ready_to_push(root)

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["blocker"]["code"], "git_cached_diff_failed")
            self.assertIn("timed out after 30s", result["blocker"]["detail"])
            self.assertEqual(self._git(root, "rev-parse", "HEAD"), before)
            self.assertIn("- [ ] step:ready_to_push", self._tracker_text(root))
            working_paths = [path.as_posix() for path in (root / "docs/reviews").glob("*_ready_to_push_closeout_range_*.md")]
            self.assertEqual(working_paths, [])

    def test_post_staging_cached_diff_timeout_rolls_back_tracker_and_generated_receipt_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._ready_fixture(root)
            expected_doc = self._stage_expected_doc(root)
            before = self._git(root, "rev-parse", "HEAD")
            original_diagnostic = MODULE._run_git_diagnostic
            cached_diff_calls = 0

            def timeout_post_staging(root_arg: Path, *args: str) -> tuple[int, str, str]:
                nonlocal cached_diff_calls
                if args == ("diff", "--cached", "--name-only"):
                    cached_diff_calls += 1
                    if cached_diff_calls == 2:
                        return MODULE.GIT_TIMEOUT_RETURN_CODE, "", "git diff --cached --name-only timed out after 30s"
                return original_diagnostic(root_arg, *args)

            with mock.patch.object(MODULE, "_run_git_diagnostic", side_effect=timeout_post_staging):
                result = MODULE.close_ready_to_push(root)

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["blocker"]["code"], "git_cached_diff_failed")
            self.assertIn("timed out after 30s", result["blocker"]["detail"])
            self.assertEqual(self._git(root, "rev-parse", "HEAD"), before)
            self.assertIn("- [ ] step:ready_to_push", self._tracker_text(root))
            cached_paths = self._git(root, "diff", "--cached", "--name-only").splitlines()
            self.assertEqual(cached_paths, [expected_doc])
            self.assertFalse(any("_ready_to_push_closeout_range_" in path for path in cached_paths))
            committed_paths = self._git(root, "ls-tree", "-r", "--name-only", "HEAD").splitlines()
            self.assertFalse(any("_ready_to_push_closeout_range_" in path for path in committed_paths))

    def test_partial_receipt_write_flush_and_close_failures_cleanup_owned_output_before_staging(self) -> None:
        for phase in ("write", "flush", "close"):
            with self.subTest(phase=phase):
                with tempfile.TemporaryDirectory() as tmpdir:
                    root = Path(tmpdir).resolve()
                    base, head = self._ready_fixture(root)
                    expected_doc = self._stage_expected_doc(root)
                    receipt_path = f"docs/reviews/260519_0003_ready_to_push_closeout_range_{base[:7]}_{head[:7]}.md"
                    receipt = root / receipt_path
                    tracker_before = self._tracker_text(root)
                    cached_paths_before = self._git(root, "diff", "--cached", "--name-only").splitlines()
                    tree_before = self._git(root, "write-tree")
                    head_before = self._git(root, "rev-parse", "HEAD")
                    staged_blob_before = self._staged_blob_id(root, expected_doc)
                    original_open = Path.open
                    original_run_git = MODULE._run_git
                    calls: list[tuple[str, ...]] = []
                    partial_prefixes: list[bytes] = []

                    class PartialReceiptFile:
                        def __init__(self, handle: object) -> None:
                            self._handle = handle

                        def __enter__(self) -> "PartialReceiptFile":
                            return self

                        def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
                            self.close()
                            return False

                        def write(self, text: str) -> int:
                            self._handle.write(text[:32])
                            self._handle.flush()
                            partial_prefixes.append(receipt.read_bytes())
                            if phase == "write":
                                raise OSError(5, "forced write failure")
                            return len(text)

                        def flush(self) -> object:
                            self._handle.flush()
                            if phase == "flush":
                                raise OSError(5, "forced flush failure")
                            return None

                        def close(self) -> None:
                            self._handle.close()
                            if phase == "close":
                                raise OSError(5, "forced close failure")

                    def partial_open(
                        path_arg: Path,
                        mode: str = "r",
                        buffering: int = -1,
                        encoding: str | None = None,
                        errors: str | None = None,
                        newline: str | None = None,
                    ) -> object:
                        handle = original_open(
                            path_arg,
                            mode=mode,
                            buffering=buffering,
                            encoding=encoding,
                            errors=errors,
                            newline=newline,
                        )
                        if path_arg == receipt and mode == "x":
                            return PartialReceiptFile(handle)
                        return handle

                    def record_git_calls(root_arg: Path, *args: str) -> tuple[int, str, str]:
                        calls.append(args)
                        return original_run_git(root_arg, *args)

                    with mock.patch.object(MODULE, "_closeout_receipt_path", return_value=receipt_path):
                        with mock.patch.object(MODULE, "_run_git", side_effect=record_git_calls):
                            with mock.patch.object(Path, "open", autospec=True, side_effect=partial_open):
                                result = MODULE.close_ready_to_push(root)

                        self.assertEqual(result["status"], "blocked")
                        self.assertEqual(result["blocker"]["code"], "git_add_closeout_receipt_failed")
                        self.assertEqual(
                            result["staging_diagnostics"]["recommended_action"],
                            "fix ready-to-push closeout receipt staging and rerun",
                        )
                        self.assertEqual(len(partial_prefixes), 1)
                        self.assertTrue(partial_prefixes[0])
                        self.assertFalse(receipt.exists())
                        self.assertEqual(self._tracker_text(root), tracker_before)
                        self.assertEqual(self._git(root, "diff", "--cached", "--name-only").splitlines(), cached_paths_before)
                        self.assertEqual(self._git(root, "write-tree"), tree_before)
                        self.assertEqual(self._git(root, "rev-parse", "HEAD"), head_before)
                        self.assertEqual(self._staged_blob_id(root, expected_doc), staged_blob_before)
                        self.assertNotIn(("add", "--", receipt_path), calls)
                        self.assertFalse(any(args and args[0] == "update-index" for args in calls))
                        self.assertFalse(list((root / "docs/reviews").glob(f"*_risk_packet_range_{base[:7]}_{head[:7]}.md")))

                        rerun = MODULE.close_ready_to_push(root)

                    self.assertEqual(rerun["status"], "ok")
                    self.assertEqual(rerun["closeout_receipt_path"], receipt_path)
                    self.assertEqual(self._git(root, "rev-parse", f"HEAD:{expected_doc}"), staged_blob_before)
                    closeout_paths = sorted(
                        path.relative_to(root).as_posix()
                        for path in (root / "docs/reviews").glob(f"*_ready_to_push_closeout_range_{base[:7]}_{head[:7]}.md")
                    )
                    risk_packet_paths = sorted(
                        path.relative_to(root).as_posix()
                        for path in (root / "docs/reviews").glob(f"*_risk_packet_range_{base[:7]}_{head[:7]}.md")
                    )
                    self.assertEqual(closeout_paths, [receipt_path])
                    self.assertEqual(risk_packet_paths, [rerun["risk_packet_path"]])

    def test_partial_receipt_cleanup_missing_is_benign_and_cleanup_error_stays_red(self) -> None:
        for cleanup_case in ("missing", "error"):
            with self.subTest(cleanup_case=cleanup_case):
                with tempfile.TemporaryDirectory() as tmpdir:
                    root = Path(tmpdir).resolve()
                    base, head = self._ready_fixture(root)
                    expected_doc = self._stage_expected_doc(root)
                    receipt_path = f"docs/reviews/260519_0003_ready_to_push_closeout_range_{base[:7]}_{head[:7]}.md"
                    receipt = root / receipt_path
                    tracker_before = self._tracker_text(root)
                    tree_before = self._git(root, "write-tree")
                    head_before = self._git(root, "rev-parse", "HEAD")
                    staged_blob_before = self._staged_blob_id(root, expected_doc)
                    original_open = Path.open
                    original_unlink = Path.unlink
                    original_run_git = MODULE._run_git
                    calls: list[tuple[str, ...]] = []

                    class FailingWriteReceiptFile:
                        def __init__(self, handle: object) -> None:
                            self._handle = handle

                        def __enter__(self) -> "FailingWriteReceiptFile":
                            return self

                        def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
                            self.close()
                            return False

                        def write(self, text: str) -> int:
                            self._handle.write(text[:32])
                            self._handle.flush()
                            raise OSError(5, "forced write failure")

                        def flush(self) -> None:
                            self._handle.flush()

                        def close(self) -> None:
                            self._handle.close()

                    def failing_open(
                        path_arg: Path,
                        mode: str = "r",
                        buffering: int = -1,
                        encoding: str | None = None,
                        errors: str | None = None,
                        newline: str | None = None,
                    ) -> object:
                        handle = original_open(
                            path_arg,
                            mode=mode,
                            buffering=buffering,
                            encoding=encoding,
                            errors=errors,
                            newline=newline,
                        )
                        if path_arg == receipt and mode == "x":
                            return FailingWriteReceiptFile(handle)
                        return handle

                    def cleanup_unlink(path_arg: Path, missing_ok: bool = False) -> None:
                        if path_arg != receipt:
                            original_unlink(path_arg, missing_ok=missing_ok)
                            return
                        if cleanup_case == "missing":
                            original_unlink(path_arg, missing_ok=missing_ok)
                            raise FileNotFoundError()
                        raise OSError(5, "forced cleanup failure")

                    def record_git_calls(root_arg: Path, *args: str) -> tuple[int, str, str]:
                        calls.append(args)
                        return original_run_git(root_arg, *args)

                    with mock.patch.object(MODULE, "_closeout_receipt_path", return_value=receipt_path):
                        with mock.patch.object(MODULE, "_run_git", side_effect=record_git_calls):
                            with mock.patch.object(Path, "open", autospec=True, side_effect=failing_open):
                                with mock.patch.object(Path, "unlink", autospec=True, side_effect=cleanup_unlink):
                                    result = MODULE.close_ready_to_push(root)

                        self.assertEqual(result["status"], "blocked")
                        self.assertEqual(result["blocker"]["code"], "git_add_closeout_receipt_failed")
                        self.assertEqual(self._tracker_text(root), tracker_before)
                        self.assertEqual(self._git(root, "write-tree"), tree_before)
                        self.assertEqual(self._git(root, "rev-parse", "HEAD"), head_before)
                        self.assertEqual(self._staged_blob_id(root, expected_doc), staged_blob_before)
                        self.assertNotIn(("add", "--", receipt_path), calls)
                        self.assertFalse(any(args and args[0] == "update-index" for args in calls))
                        self.assertFalse(list((root / "docs/reviews").glob(f"*_risk_packet_range_{base[:7]}_{head[:7]}.md")))

                        if cleanup_case == "missing":
                            self.assertFalse(receipt.exists())
                            self.assertNotIn("closeout receipt rollback failed", result["blocker"]["detail"])
                            rerun = MODULE.close_ready_to_push(root)
                            self.assertEqual(rerun["status"], "ok")
                            self.assertEqual(rerun["closeout_receipt_path"], receipt_path)
                        else:
                            self.assertTrue(receipt.exists())
                            self.assertIn("closeout receipt rollback failed", result["blocker"]["detail"])
                            self.assertIn("forced cleanup failure", result["blocker"]["detail"])
                            self.assertNotIn("terminal_state", result)

    def test_first_closeout_receipt_add_failure_rolls_back_owned_output_and_reruns_same_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            base, head = self._ready_fixture(root)
            expected_doc = self._stage_expected_doc(root)
            receipt_path = f"docs/reviews/260519_0003_ready_to_push_closeout_range_{base[:7]}_{head[:7]}.md"
            tracker_before = self._tracker_text(root)
            tree_before = self._git(root, "write-tree")
            staged_blob_before = self._staged_blob_id(root, expected_doc)
            original_run_git = MODULE._run_git
            calls: list[tuple[str, ...]] = []
            failed_add = False

            def fail_first_receipt_add(root_arg: Path, *args: str) -> tuple[int, str, str]:
                nonlocal failed_add
                calls.append(args)
                if args == ("add", "--", receipt_path) and not failed_add:
                    failed_add = True
                    original_run_git(root_arg, *args)
                    return 1, "", "forced first closeout receipt add failure"
                return original_run_git(root_arg, *args)

            with mock.patch.object(MODULE, "_closeout_receipt_path", return_value=receipt_path):
                with mock.patch.object(MODULE, "_run_git", side_effect=fail_first_receipt_add):
                    result = MODULE.close_ready_to_push(root)

                self.assertEqual(result["status"], "blocked")
                self.assertEqual(result["blocker"]["code"], "git_add_closeout_receipt_failed")
                self.assertNotIn(str(root), result["blocker"]["detail"])
                self.assertEqual(self._tracker_text(root), tracker_before)
                self.assertEqual(self._git(root, "write-tree"), tree_before)
                self.assertEqual(self._staged_blob_id(root, expected_doc), staged_blob_before)
                self.assertEqual(self._git(root, "diff", "--cached", "--name-only").splitlines(), [expected_doc])
                self.assertFalse((root / receipt_path).exists())
                self.assertFalse(list((root / "docs/reviews").glob(f"*_risk_packet_range_{base[:7]}_{head[:7]}.md")))
                self.assertNotIn("init", [args[0] for args in calls])
                self.assertNotIn("clone", [args[0] for args in calls])

                rerun = MODULE.close_ready_to_push(root)

            self.assertEqual(rerun["status"], "ok")
            self.assertEqual(rerun["closeout_receipt_path"], receipt_path)
            self.assertEqual(self._git(root, "rev-parse", f"HEAD:{expected_doc}"), staged_blob_before)
            closeout_paths = sorted(
                path.relative_to(root).as_posix()
                for path in (root / "docs/reviews").glob(f"*_ready_to_push_closeout_range_{base[:7]}_{head[:7]}.md")
            )
            risk_packet_paths = sorted(
                path.relative_to(root).as_posix()
                for path in (root / "docs/reviews").glob(f"*_risk_packet_range_{base[:7]}_{head[:7]}.md")
            )
            self.assertEqual(closeout_paths, [receipt_path])
            self.assertEqual(risk_packet_paths, [rerun["risk_packet_path"]])

    def test_existing_receipt_collision_preserves_bytes_and_staged_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            base, head = self._ready_fixture(root)
            expected_doc = self._stage_expected_doc(root)
            report_before_collision = MODULE.merge_bundle_report.build_report(root)
            self.assertEqual(report_before_collision["errors"], [], report_before_collision)
            receipt_path = f"docs/reviews/260519_0003_ready_to_push_closeout_range_{base[:7]}_{head[:7]}.md"
            receipt_bytes = b"pre-existing closeout receipt bytes\n"
            receipt = root / receipt_path
            receipt.parent.mkdir(parents=True, exist_ok=True)
            receipt.write_bytes(receipt_bytes)
            tracker_before = self._tracker_text(root)
            tree_before = self._git(root, "write-tree")
            staged_blob_before = self._staged_blob_id(root, expected_doc)
            original_run_git = MODULE._run_git
            calls: list[tuple[str, ...]] = []

            def record_git_calls(root_arg: Path, *args: str) -> tuple[int, str, str]:
                calls.append(args)
                return original_run_git(root_arg, *args)

            with mock.patch.object(
                MODULE.merge_bundle_report,
                "build_report",
                return_value=report_before_collision,
            ):
                with mock.patch.object(MODULE, "_closeout_receipt_path", return_value=receipt_path):
                    with mock.patch.object(MODULE, "_run_git", side_effect=record_git_calls):
                        result = MODULE.close_ready_to_push(root)

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["blocker"]["code"], "git_add_closeout_receipt_failed")
            self.assertEqual(receipt.read_bytes(), receipt_bytes)
            self.assertEqual(self._tracker_text(root), tracker_before)
            self.assertEqual(self._git(root, "write-tree"), tree_before)
            self.assertEqual(self._staged_blob_id(root, expected_doc), staged_blob_before)
            self.assertEqual(self._git(root, "diff", "--cached", "--name-only").splitlines(), [expected_doc])
            self.assertNotIn(("add", "--", receipt_path), calls)
            self.assertNotIn("init", [args[0] for args in calls])
            self.assertNotIn("clone", [args[0] for args in calls])
            self.assertFalse(list((root / "docs/reviews").glob(f"*_risk_packet_range_{base[:7]}_{head[:7]}.md")))

    def test_staged_receipt_collision_preserves_receipt_index_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            base, head = self._ready_fixture(root)
            expected_doc = self._stage_expected_doc(root)
            report_before_collision = MODULE.merge_bundle_report.build_report(root)
            self.assertEqual(report_before_collision["errors"], [], report_before_collision)
            receipt_path = f"docs/reviews/260519_0003_ready_to_push_closeout_range_{base[:7]}_{head[:7]}.md"
            receipt = self._write(root, receipt_path, "pre-existing staged closeout receipt\n")
            self._git(root, "add", receipt_path)
            receipt.unlink()
            report_before_collision["git_status"]["candidate_contextual"].append(
                {"path": receipt_path, "git_state": "staged"}
            )
            tracker_before = self._tracker_text(root)
            tree_before = self._git(root, "write-tree")
            expected_doc_blob_before = self._staged_blob_id(root, expected_doc)
            receipt_blob_before = self._staged_blob_id(root, receipt_path)
            original_run_git = MODULE._run_git
            calls: list[tuple[str, ...]] = []

            def record_git_calls(root_arg: Path, *args: str) -> tuple[int, str, str]:
                calls.append(args)
                return original_run_git(root_arg, *args)

            with mock.patch.object(
                MODULE.merge_bundle_report,
                "build_report",
                return_value=report_before_collision,
            ):
                with mock.patch.object(MODULE, "_closeout_receipt_path", return_value=receipt_path):
                    with mock.patch.object(MODULE, "_run_git", side_effect=record_git_calls):
                        result = MODULE.close_ready_to_push(root)

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["blocker"]["code"], "git_add_closeout_receipt_failed")
            self.assertFalse(receipt.exists())
            self.assertEqual(self._tracker_text(root), tracker_before)
            self.assertEqual(self._git(root, "write-tree"), tree_before)
            self.assertEqual(self._staged_blob_id(root, expected_doc), expected_doc_blob_before)
            self.assertEqual(self._staged_blob_id(root, receipt_path), receipt_blob_before)
            self.assertEqual(
                self._git(root, "diff", "--cached", "--name-only").splitlines(),
                sorted([expected_doc, receipt_path]),
            )
            self.assertNotIn(("add", "--", receipt_path), calls)
            self.assertNotIn("init", [args[0] for args in calls])
            self.assertNotIn("clone", [args[0] for args in calls])
            self.assertFalse(list((root / "docs/reviews").glob(f"*_risk_packet_range_{base[:7]}_{head[:7]}.md")))

    def test_head_receipt_collision_preserves_committed_bytes_and_staged_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            base, head = self._ready_fixture(root)
            expected_doc = self._stage_expected_doc(root)
            report_before_collision = MODULE.merge_bundle_report.build_report(root)
            self.assertEqual(report_before_collision["errors"], [], report_before_collision)
            receipt_path = f"docs/reviews/260519_0003_ready_to_push_closeout_range_{base[:7]}_{head[:7]}.md"
            receipt_bytes = b"pre-existing committed closeout receipt bytes\n"
            receipt = self._write(root, receipt_path, receipt_bytes.decode("utf-8"))
            self._git(root, "add", receipt_path)
            self._git(root, "commit", "-m", "head receipt collision", "--", receipt_path)
            tracker_before = self._tracker_text(root)
            tree_before = self._git(root, "write-tree")
            head_before = self._git(root, "rev-parse", "HEAD")
            expected_doc_blob_before = self._staged_blob_id(root, expected_doc)
            receipt_blob_before = self._git(root, "rev-parse", f"HEAD:{receipt_path}")
            original_run_git = MODULE._run_git
            calls: list[tuple[str, ...]] = []

            def record_git_calls(root_arg: Path, *args: str) -> tuple[int, str, str]:
                calls.append(args)
                return original_run_git(root_arg, *args)

            with mock.patch.object(
                MODULE.merge_bundle_report,
                "build_report",
                return_value=report_before_collision,
            ):
                with mock.patch.object(MODULE, "_closeout_receipt_path", return_value=receipt_path):
                    with mock.patch.object(MODULE, "_run_git", side_effect=record_git_calls):
                        result = MODULE.close_ready_to_push(root)

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["blocker"]["code"], "git_add_closeout_receipt_failed")
            self.assertEqual(receipt.read_bytes(), receipt_bytes)
            self.assertEqual(self._tracker_text(root), tracker_before)
            self.assertEqual(self._git(root, "rev-parse", "HEAD"), head_before)
            self.assertEqual(self._git(root, "write-tree"), tree_before)
            self.assertEqual(self._staged_blob_id(root, expected_doc), expected_doc_blob_before)
            self.assertEqual(self._git(root, "rev-parse", f"HEAD:{receipt_path}"), receipt_blob_before)
            self.assertNotIn(("add", "--", receipt_path), calls)
            self.assertFalse(any(args and args[0] == "update-index" for args in calls))
            self.assertFalse(list((root / "docs/reviews").glob(f"*_risk_packet_range_{base[:7]}_{head[:7]}.md")))

    def test_commit_failure_rolls_back_tracker_without_terminal_receipt_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._ready_fixture(root)
            before = self._git(root, "rev-parse", "HEAD")
            original_run_git = MODULE._run_git

            def fail_commit(root_arg: Path, *args: str) -> tuple[int, str, str]:
                if args[0] == "commit":
                    return 1, "", "forced commit failure"
                return original_run_git(root_arg, *args)

            with mock.patch.object(MODULE, "_run_git", side_effect=fail_commit):
                result = MODULE.close_ready_to_push(root)

            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["blocker"]["code"], "git_commit_failed")
            self.assertEqual(self._git(root, "rev-parse", "HEAD"), before)
            self.assertIn("- [ ] step:ready_to_push", self._tracker_text(root))
            committed_paths = self._git(root, "ls-tree", "-r", "--name-only", "HEAD").splitlines()
            self.assertFalse(any("_ready_to_push_closeout_range_" in path for path in committed_paths))

            rerun = MODULE.close_ready_to_push(root)
            self.assertEqual(rerun["status"], "ok")
            self.assertEqual(rerun["action"], "committed")
            self.assertIn("- [x] step:ready_to_push", self._tracker_text(root))

    def test_helper_never_runs_git_push_or_unrelated_git_add(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._ready_fixture(root)
            self._stage_expected_doc(root)
            calls: list[tuple[str, ...]] = []
            original_run_git = MODULE._run_git

            def guarded_run_git(root_arg: Path, *args: str) -> tuple[int, str, str]:
                calls.append(args)
                self.assertNotEqual(args[0], "push")
                if args[0] == "add":
                    self.assertIn("--", args)
                    self.assertTrue(
                        "_ready_to_push_closeout_range_" in args[-1]
                        or "_risk_packet_range_" in args[-1]
                    )
                return original_run_git(root_arg, *args)

            with mock.patch.object(MODULE, "_run_git", side_effect=guarded_run_git):
                result = MODULE.close_ready_to_push(root)

            self.assertEqual(result["status"], "ok")
            self.assertNotIn("push", [args[0] for args in calls])
            add_calls = [args for args in calls if args[0] == "add"]
            self.assertEqual(len(add_calls), 2)


if __name__ == "__main__":
    unittest.main()

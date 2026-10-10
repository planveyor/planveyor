#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from textwrap import dedent


def _load_script_module(name: str):
    path = Path(__file__).with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


COLLECT = _load_script_module("process_improvements_collect")
PROMOTE = _load_script_module("process_improvements_promote")
RECONCILE = _load_script_module("process_improvements_reconcile")


class ProcessImprovementsPromoteTests(unittest.TestCase):
    def _root(self) -> Path:
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        root = Path(tmpdir.name)
        subprocess.run(["git", "init", "--quiet", os.fspath(root)], check=True)
        (root / ".authority-fixture").write_text("fixture\n", encoding="utf-8")
        subprocess.run(["git", "-C", os.fspath(root), "add", ".authority-fixture"], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                os.fspath(root),
                "-c",
                "user.name=Authority Fixture",
                "-c",
                'user.email=' + 'authority-fixture' + '@' + 'example' + '.' + 'invalid',
                "commit",
                "--quiet",
                "-m",
                "fixture",
            ],
            check=True,
        )
        return root

    def _write(self, root: Path, rel_path: str, text: str = "fixture\n") -> Path:
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def _collect_rows(self, root: Path, count: int = 1) -> str:
        suggestions = []
        for idx in range(1, count + 1):
            suggestions.append(
                dedent(
                    f"""\
                    ### Suggestion {idx}
                    - symptom: process row {idx} needs deterministic promotion
                    - process_gap: helper must not rely on chat memory {idx}
                    - suggested_fix: use explicit execution pointer {idx}
                    - owner: Architect
                    - promotion_class: helper_change
                    - trigger_ref: docs/plans/source.md#S{idx}
                    - source_ref: docs/plans/source.md
                    """
                ).rstrip()
            )
        payload = COLLECT.collect_process_improvements(
            project_root=root,
            role="Coder",
            source_ref="docs/plans/source.md",
            text="## Process improvements\n" + "\n".join(suggestions) + "\n",
        )
        return payload["backlog_files"][0]

    def _triage_row(self, root: Path, backlog_rel: str, entry_id: str) -> None:
        COLLECT.update_backlog_entry(
            project_root=root,
            backlog_path=root / backlog_rel,
            entry_id=entry_id,
            status="triaged",
            priority="P1",
            owner="Architect",
            target_canon_path="docs/tools/owner_runbook_codex.md",
            target_repo_scope="current-consumer",
            delivery_mode="source_only",
            triage_note="ready for execution pointer promotion",
        )

    def _promote_apply(self, root: Path, backlog_rel: str, entry_id: str, execution_ref: str) -> None:
        with redirect_stdout(io.StringIO()):
            rc = PROMOTE.main(
                [
                    "--project-root",
                    str(root),
                    "--backlog",
                    backlog_rel,
                    "--entry",
                    entry_id,
                    "--execution-kind",
                    "plan",
                    "--execution-ref",
                    execution_ref,
                    "--promoted-at",
                    "2026-04-30 14:45 MSK",
                    "--apply",
                ]
            )
        self.assertEqual(rc, 0)

    def _promote_non_plan(
        self,
        root: Path,
        backlog_rel: str,
        entry_id: str,
        *,
        execution_kind: str,
        execution_ref: str,
    ) -> None:
        COLLECT.update_backlog_entry(
            project_root=root,
            backlog_path=root / backlog_rel,
            entry_id=entry_id,
            status="promoted",
            priority="P1",
            owner="Architect",
            target_canon_path="docs/tools/owner_runbook_codex.md",
            target_repo_scope="current-consumer",
            delivery_mode="source_only",
            execution_kind=execution_kind,
            execution_ref=execution_ref,
            promoted_at="2026-04-30 14:47 MSK",
        )

    def test_promote_report_is_dry_run_and_lists_exact_mutation(self) -> None:
        root = self._root()
        backlog_rel = self._collect_rows(root)
        self._triage_row(root, backlog_rel, "PI-001")
        self._write(root, "docs/plans/execution.md", "**Status:** In progress\n")

        out = io.StringIO()
        with redirect_stdout(out):
            rc = PROMOTE.main(
                [
                    "--project-root",
                    str(root),
                    "--backlog",
                    backlog_rel,
                    "--entry",
                    "PI-001",
                    "--execution-kind",
                    "plan",
                    "--execution-ref",
                    "docs/plans/execution.md",
                    "--delivery-refs",
                    "null",
                    "--promoted-at",
                    "2026-04-30 14:45 MSK",
                    "--report",
                    "--format",
                    "json",
                ]
            )

        self.assertEqual(rc, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["mode"], "report")
        self.assertEqual(payload["mutation"]["status"], "promoted")
        self.assertEqual(payload["mutation"]["execution_ref"], "docs/plans/execution.md")
        self.assertIn("docs/process_improvements/promotion_surface.md", payload["writes"])

        backlog = COLLECT.parse_backlog_file(root / backlog_rel, root)
        self.assertEqual(backlog.entries[0].status, "triaged")
        self.assertEqual(backlog.entries[0].execution_ref, "null")

    def test_promote_apply_requires_existing_repo_local_ref_and_never_scaffolds_it(self) -> None:
        root = self._root()
        backlog_rel = self._collect_rows(root)
        self._triage_row(root, backlog_rel, "PI-001")

        with self.assertRaises(SystemExit) as raised:
            PROMOTE.main(
                [
                    "--project-root",
                    str(root),
                    "--backlog",
                    backlog_rel,
                    "--entry",
                    "PI-001",
                    "--execution-kind",
                    "plan",
                    "--execution-ref",
                    "docs/plans/missing.md",
                    "--promoted-at",
                    "2026-04-30 14:45 MSK",
                    "--apply",
                ]
            )

        self.assertIn("Missing execution_ref", str(raised.exception))
        self.assertFalse((root / "docs/plans/missing.md").exists())
        backlog = COLLECT.parse_backlog_file(root / backlog_rel, root)
        self.assertEqual(backlog.entries[0].status, "triaged")

    def test_promote_report_requires_priority_carrier(self) -> None:
        root = self._root()
        backlog_rel = self._collect_rows(root)
        COLLECT.update_backlog_entry(
            project_root=root,
            backlog_path=root / backlog_rel,
            entry_id="PI-001",
            target_canon_path="docs/tools/owner_runbook_codex.md",
            target_repo_scope="current-consumer",
            delivery_mode="source_only",
            triage_note="target carrier exists but priority still missing",
        )
        self._write(root, "docs/plans/execution.md", "**Status:** In progress\n")

        with self.assertRaisesRegex(ValueError, "priority"):
            PROMOTE.build_payload(
                project_root=root,
                backlog_path=root / backlog_rel,
                entry_id="PI-001",
                execution_kind="plan",
                execution_ref="docs/plans/execution.md",
                promoted_at="2026-04-30 14:45 MSK",
                delivery_refs=None,
                triage_note=None,
                apply=False,
            )

    def test_promote_apply_mutates_raw_backlog_and_regenerates_surfaces(self) -> None:
        root = self._root()
        backlog_rel = self._collect_rows(root)
        self._triage_row(root, backlog_rel, "PI-001")
        self._write(root, "docs/plans/execution.md", "**Status:** In progress\n")

        self._promote_apply(root, backlog_rel, "PI-001", "docs/plans/execution.md")

        backlog = COLLECT.parse_backlog_file(root / backlog_rel, root)
        entry = backlog.entries[0]
        self.assertEqual(entry.status, "promoted")
        self.assertEqual(entry.execution_kind, "plan")
        self.assertEqual(entry.execution_ref, "docs/plans/execution.md")
        self.assertEqual(entry.promoted_at, "2026-04-30 14:45 MSK")

        promotion_text = (root / "docs/process_improvements/promotion_surface.md").read_text(encoding="utf-8")
        self.assertIn("docs/plans/execution.md", promotion_text)
        self.assertIn("promoted", promotion_text)
        self.assertFalse((root / "docs/tools/owner_runbook_codex.md").exists())

    def test_promote_accepts_existing_helper_and_canon_doc_refs(self) -> None:
        root = self._root()
        backlog_rel = self._collect_rows(root, count=2)
        self._triage_row(root, backlog_rel, "PI-001")
        self._triage_row(root, backlog_rel, "PI-002")
        self._write(root, "scripts/example_helper.py")
        self._write(root, "docs/process_improvements/README.md")

        helper = PROMOTE.build_payload(
            project_root=root,
            backlog_path=root / backlog_rel,
            entry_id="PI-001",
            execution_kind="helper",
            execution_ref="scripts/example_helper.py",
            promoted_at="2026-04-30 14:45 MSK",
            delivery_refs=None,
            triage_note=None,
            apply=False,
        )
        canon = PROMOTE.build_payload(
            project_root=root,
            backlog_path=root / backlog_rel,
            entry_id="PI-002",
            execution_kind="canon_doc",
            execution_ref="docs/process_improvements/README.md",
            promoted_at="2026-04-30 14:46 MSK",
            delivery_refs=None,
            triage_note=None,
            apply=False,
        )

        self.assertEqual(helper["mutation"]["execution_ref"], "scripts/example_helper.py")
        self.assertEqual(canon["mutation"]["execution_ref"], "docs/process_improvements/README.md")

    def test_reconcile_report_separates_candidate_stale_and_missing_rows(self) -> None:
        root = self._root()
        backlog_rel = self._collect_rows(root, count=3)
        for entry_id in ("PI-001", "PI-002", "PI-003"):
            self._triage_row(root, backlog_rel, entry_id)
        self._write(root, "docs/plans/done.md", "**Status:** Done\n")
        self._write(root, "docs/plans/live.md", "**Status:** Ready for Coder\n")
        self._promote_apply(root, backlog_rel, "PI-001", "docs/plans/done.md")
        self._promote_apply(root, backlog_rel, "PI-002", "docs/plans/live.md")
        COLLECT.update_backlog_entry(
            project_root=root,
            backlog_path=root / backlog_rel,
            entry_id="PI-003",
            status="promoted",
            priority="P1",
            owner="Architect",
            target_canon_path="docs/tools/owner_runbook_codex.md",
            target_repo_scope="current-consumer",
            delivery_mode="source_only",
            execution_kind="helper",
            execution_ref="scripts/missing_helper.py",
            promoted_at="2026-04-30 14:47 MSK",
        )

        payload = RECONCILE.report_payload(project_root=root)

        self.assertEqual([row["entry_id"] for row in payload["candidate_handled"]], ["PI-001"])
        self.assertEqual([row["entry_id"] for row in payload["stale_promoted"]], ["PI-002"])
        self.assertEqual([row["entry_id"] for row in payload["missing_execution_ref"]], ["PI-003"])
        self.assertEqual(payload["candidate_handled"][0]["reason"], "done_plan")
        self.assertEqual(payload["stale_promoted"][0]["target_status"], "ready for coder")

    def test_reconcile_report_surfaces_triaged_done_plan_rows(self) -> None:
        root = self._root()
        backlog_rel = self._collect_rows(root)
        self._triage_row(root, backlog_rel, "PI-001")
        self._write(root, "docs/plans/done.md", "**Status:** Done\n")
        COLLECT.update_backlog_entry(
            project_root=root,
            backlog_path=root / backlog_rel,
            entry_id="PI-001",
            execution_kind="plan",
            execution_ref="docs/plans/done.md",
        )

        payload = RECONCILE.report_payload(project_root=root)

        self.assertEqual([row["entry_id"] for row in payload["candidate_handled"]], ["PI-001"])
        self.assertEqual(payload["candidate_handled"][0]["status"], "triaged")
        self.assertEqual(payload["candidate_handled"][0]["reason"], "done_plan")
        self.assertIs(payload["candidate_handled"][0]["needs_reconcile"], True)
        self.assertEqual(payload["stale_promoted"], [])
        self.assertEqual(payload["missing_execution_ref"], [])

    def test_reconcile_does_not_candidate_triaged_rows_missing_carrier(self) -> None:
        root = self._root()
        backlog_rel = self._collect_rows(root)
        path = root / backlog_rel
        text = path.read_text(encoding="utf-8")
        text = text.replace("- status: `open`", "- status: `triaged`")
        text = text.replace("- execution_kind: `null`", "- execution_kind: `plan`")
        text = text.replace("- execution_ref: `null`", "- execution_ref: `docs/plans/done.md`")
        text = text.replace("- triage_note: `auto-collected from memory-finalize general lane`", "- triage_note: `needs carrier target`")
        path.write_text(text, encoding="utf-8")
        self._write(root, "docs/plans/done.md", "**Status:** Done\n")

        payload = RECONCILE.report_payload(project_root=root)

        self.assertEqual(payload["candidate_handled"], [])
        self.assertEqual(payload["missing_carrier"][0]["entry_id"], "PI-001")
        self.assertIn("target_canon_path", payload["missing_carrier"][0]["missing_carrier_fields"])

    def test_reconcile_apply_handles_only_safe_terminal_rows(self) -> None:
        root = self._root()
        backlog_rel = self._collect_rows(root, count=2)
        for entry_id in ("PI-001", "PI-002"):
            self._triage_row(root, backlog_rel, entry_id)
        self._write(root, "docs/plans/done.md", "**Status:** Done\n")
        self._write(root, "docs/plans/live.md", "**Status:** In progress\n")
        self._promote_apply(root, backlog_rel, "PI-001", "docs/plans/done.md")
        self._promote_apply(root, backlog_rel, "PI-002", "docs/plans/live.md")

        payload = RECONCILE.apply_candidate_handled(
            project_root=root,
            backlogs=None,
            entries=None,
            handled_at="2026-04-30 14:55 MSK",
            handled_ref=None,
        )

        self.assertEqual(payload["applied"]["candidate_handled"][0]["entry_id"], "PI-001")
        backlog = COLLECT.parse_backlog_file(root / backlog_rel, root)
        by_id = {entry.entry_id: entry for entry in backlog.entries}
        self.assertEqual(by_id["PI-001"].status, "handled")
        self.assertEqual(by_id["PI-001"].handled_ref, "docs/plans/done.md")
        self.assertEqual(by_id["PI-001"].handled_at, "2026-04-30 14:55 MSK")
        self.assertEqual(by_id["PI-002"].status, "promoted")

    def test_reconcile_keeps_external_refs_report_only(self) -> None:
        root = self._root()
        backlog_rel = self._collect_rows(root)
        self._triage_row(root, backlog_rel, "PI-001")
        with redirect_stdout(io.StringIO()):
            rc = PROMOTE.main(
                [
                    "--project-root",
                    str(root),
                    "--backlog",
                    backlog_rel,
                    "--entry",
                    "PI-001",
                    "--execution-kind",
                    "external_ref",
                    "--execution-ref",
                    "ticket:PROC-1",
                    "--promoted-at",
                    "2026-04-30 14:45 MSK",
                    "--apply",
                ]
            )
        self.assertEqual(rc, 0)

        payload = RECONCILE.report_payload(project_root=root)
        self.assertEqual(payload["candidate_handled"], [])
        self.assertEqual(payload["stale_promoted"][0]["reason"], "external_ref_not_file_backed")

    def test_reconcile_requires_process_improvement_id_for_non_plan_carriers(self) -> None:
        root = self._root()
        backlog_rel = self._collect_rows(root)
        self._triage_row(root, backlog_rel, "PI-001")
        self._write(
            root,
            "scripts/process_receipt.md",
            "delivery receipt\nprocess_improvement_id: PI-001\n",
        )
        self._promote_non_plan(
            root,
            backlog_rel,
            "PI-001",
            execution_kind="helper",
            execution_ref="scripts/process_receipt.md",
        )

        payload = RECONCILE.report_payload(project_root=root)

        self.assertEqual([row["entry_id"] for row in payload["candidate_handled"]], ["PI-001"])
        self.assertEqual(payload["candidate_handled"][0]["reason"], "verified_process_improvement_id")
        self.assertEqual(payload["candidate_handled"][0]["handled_ref"], "scripts/process_receipt.md")
        self.assertEqual(payload["stale_promoted"], [])
        self.assertEqual(payload["missing_execution_ref"], [])

    def test_reconcile_fails_closed_for_missing_wrong_and_ambiguous_process_improvement_id(self) -> None:
        root = self._root()
        backlog_rel = self._collect_rows(root, count=4)
        for entry_id in ("PI-001", "PI-002", "PI-003", "PI-004"):
            self._triage_row(root, backlog_rel, entry_id)
        self._write(root, "scripts/missing_receipt.md", "delivery receipt without row id\n")
        self._write(root, "scripts/wrong_receipt.md", "process_improvement_id: PI-999\n")
        self._write(
            root,
            "scripts/ambiguous_receipt.md",
            "process_improvement_id: PI-003\nprocess_improvement_id: PI-004\n",
        )
        self._write(
            root,
            "scripts/duplicate_receipt.md",
            "process_improvement_id: PI-004\nprocess_improvement_id: PI-004\n",
        )
        self._promote_non_plan(
            root,
            backlog_rel,
            "PI-001",
            execution_kind="helper",
            execution_ref="scripts/missing_receipt.md",
        )
        self._promote_non_plan(
            root,
            backlog_rel,
            "PI-002",
            execution_kind="canon_doc",
            execution_ref="scripts/wrong_receipt.md",
        )
        self._promote_non_plan(
            root,
            backlog_rel,
            "PI-003",
            execution_kind="rollout_packet",
            execution_ref="scripts/ambiguous_receipt.md",
        )
        self._promote_non_plan(
            root,
            backlog_rel,
            "PI-004",
            execution_kind="umbrella_wave",
            execution_ref="scripts/duplicate_receipt.md",
        )

        payload = RECONCILE.report_payload(project_root=root)

        self.assertEqual(payload["candidate_handled"], [])
        by_id = {row["entry_id"]: row for row in payload["stale_promoted"]}
        self.assertEqual(by_id["PI-001"]["reason"], "missing_process_improvement_id")
        self.assertEqual(by_id["PI-002"]["reason"], "process_improvement_id_mismatch")
        self.assertEqual(by_id["PI-003"]["reason"], "ambiguous_process_improvement_id")
        self.assertEqual(by_id["PI-004"]["reason"], "ambiguous_process_improvement_id")
        self.assertEqual(payload["missing_execution_ref"], [])

    def test_reconcile_apply_mutates_only_non_plan_rows_with_matching_process_improvement_id(self) -> None:
        root = self._root()
        backlog_rel = self._collect_rows(root, count=2)
        for entry_id in ("PI-001", "PI-002"):
            self._triage_row(root, backlog_rel, entry_id)
        self._write(root, "scripts/verified_receipt.md", "process_improvement_id: PI-001\n")
        self._write(root, "scripts/missing_receipt.md", "delivery receipt without row id\n")
        self._promote_non_plan(
            root,
            backlog_rel,
            "PI-001",
            execution_kind="helper",
            execution_ref="scripts/verified_receipt.md",
        )
        self._promote_non_plan(
            root,
            backlog_rel,
            "PI-002",
            execution_kind="helper",
            execution_ref="scripts/missing_receipt.md",
        )

        payload = RECONCILE.apply_candidate_handled(
            project_root=root,
            backlogs=None,
            entries=None,
            handled_at="2026-04-30 15:01 MSK",
            handled_ref=None,
        )

        self.assertEqual([row["entry_id"] for row in payload["applied"]["candidate_handled"]], ["PI-001"])
        backlog = COLLECT.parse_backlog_file(root / backlog_rel, root)
        by_id = {entry.entry_id: entry for entry in backlog.entries}
        self.assertEqual(by_id["PI-001"].status, "handled")
        self.assertEqual(by_id["PI-001"].handled_ref, "scripts/verified_receipt.md")
        self.assertEqual(by_id["PI-002"].status, "promoted")
        self.assertEqual(payload["stale_promoted"][0]["entry_id"], "PI-002")
        self.assertEqual(payload["stale_promoted"][0]["reason"], "missing_process_improvement_id")


if __name__ == "__main__":
    unittest.main()

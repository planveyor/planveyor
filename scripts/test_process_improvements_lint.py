#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path


LINT_PATH = Path(__file__).with_name("process_improvements_lint.py")
LINT_SPEC = importlib.util.spec_from_file_location("process_improvements_lint", LINT_PATH)
assert LINT_SPEC is not None and LINT_SPEC.loader is not None
LINT = importlib.util.module_from_spec(LINT_SPEC)
sys.modules[LINT_SPEC.name] = LINT
LINT_SPEC.loader.exec_module(LINT)


def backlog_text(
    *,
    source_ref: str = "docs/plans/source.md",
    entry_id: str = "PI-001",
    status: str = "open",
    priority: str = "P?",
    owner: str | None = "Architect",
    target_canon_path: str = "null",
    target_repo_scope: str = "null",
    delivery_mode: str = "null",
    execution_kind: str = "null",
    execution_ref: str = "null",
    delivery_refs: str = "null",
    triage_note: str = "auto-collected from memory-finalize general lane",
) -> str:
    lines = [
        "# Process improvements backlog - source",
        "",
        "**Date:** 2026-06-19 00:00 MSK",
        f"**Source ref:** `{source_ref}`",
        "**Status:** Draft",
        "",
        "## Suggestions (truth)",
        "",
        f"### {entry_id}",
        f"- status: `{status}`",
        f"- priority: `{priority}`",
        "- role: `Coder`",
    ]
    if owner is not None:
        lines.append(f"- owner: `{owner}`")
    lines.extend(
        [
            "- promotion_class: `helper_change`",
            f"- target_canon_path: `{target_canon_path}`",
            f"- target_repo_scope: `{target_repo_scope}`",
            f"- delivery_mode: `{delivery_mode}`",
            f"- execution_kind: `{execution_kind}`",
            f"- execution_ref: `{execution_ref}`",
            f"- delivery_refs: `{delivery_refs}`",
            "- handled_ref: `null`",
            "- promoted_at: `null`",
            "- handled_at: `null`",
            "- trigger_ref: `docs/code_reviews/current.md#B1`",
            f"- source_ref: `{source_ref}`",
            "- symptom: `process improvements can stay malformed`",
            "- process_gap: `no standalone lint command`",
            "- suggested_fix: `add process improvements lint`",
            "- created_at: `2026-06-19 00:00 MSK`",
            f"- triage_note: `{triage_note}`",
            "",
        ]
    )
    return "\n".join(lines)


class ProcessImprovementsLintTests(unittest.TestCase):
    def _root(self) -> Path:
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        root = Path(tmpdir.name)
        (root / ".git").mkdir()
        return root

    def _write(self, root: Path, rel_path: str, text: str) -> Path:
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def _run(self, *args: str) -> tuple[int, str]:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = LINT.main(list(args))
        return code, stdout.getvalue()

    def test_valid_fixture_passes_text_lint(self) -> None:
        root = self._root()
        self._write(
            root,
            "docs/process_improvements/source__process_improvements_backlog.md",
            backlog_text(),
        )

        code, output = self._run("--project-root", str(root))

        self.assertEqual(code, 0)
        self.assertEqual(output, "process-improvements-lint: OK\n")

    def test_pi_only_statuses_pass_lint_in_process_improvements_backlog(self) -> None:
        root = self._root()
        fixtures = (
            ("triaged", "null", "triaged before execution carrier exists"),
            ("deferred", "docs/followups/pi_delivery.md", "deferred with explicit delivery bridge"),
            ("rejected", "null", "rejected as duplicate process feedback"),
        )
        for status, delivery_refs, triage_note in fixtures:
            self._write(
                root,
                f"docs/process_improvements/{status}__process_improvements_backlog.md",
                backlog_text(
                    source_ref=f"docs/plans/{status}.md",
                    status=status,
                    delivery_refs=delivery_refs,
                    triage_note=triage_note,
                ),
            )

        code, output = self._run("--project-root", str(root))

        self.assertEqual(code, 0)
        self.assertEqual(output, "process-improvements-lint: OK\n")

    def test_malformed_enum_and_required_field_report_per_file(self) -> None:
        root = self._root()
        self._write(
            root,
            "docs/process_improvements/bad_status__process_improvements_backlog.md",
            backlog_text(source_ref="docs/plans/bad_status.md", status="waiting"),
        )
        self._write(
            root,
            "docs/process_improvements/missing_owner__process_improvements_backlog.md",
            backlog_text(source_ref="docs/plans/missing_owner.md", owner=None),
        )
        self._write(
            root,
            "docs/process_improvements/valid__process_improvements_backlog.md",
            backlog_text(source_ref="docs/plans/valid.md"),
        )

        code, output = self._run("--project-root", str(root))

        self.assertEqual(code, 1)
        self.assertIn("bad_status__process_improvements_backlog.md: parse_error: Unsupported status", output)
        self.assertIn(
            "missing_owner__process_improvements_backlog.md: parse_error: Missing required field: owner",
            output,
        )
        self.assertIn("process-improvements-lint: FAIL (2 findings)", output)

    def test_execution_contract_error_reports_finding(self) -> None:
        root = self._root()
        self._write(
            root,
            "docs/process_improvements/deferred__process_improvements_backlog.md",
            backlog_text(
                source_ref="docs/plans/deferred.md",
                status="deferred",
                delivery_refs="null",
                triage_note="parked until later",
            ),
        )

        code, output = self._run("--project-root", str(root))

        self.assertEqual(code, 1)
        self.assertIn("Deferred process-improvement rows with `delivery_refs=null`", output)

    def test_json_carrier_readback_reports_staged_triage_gaps(self) -> None:
        root = self._root()
        self._write(
            root,
            "docs/process_improvements/triaged__process_improvements_backlog.md",
            backlog_text(
                source_ref="docs/plans/triaged.md",
                status="triaged",
                priority="P?",
                triage_note="needs target owner decision",
            ),
        )

        code, output = self._run("--project-root", str(root), "--format", "json")
        payload = json.loads(output)

        self.assertEqual(code, 0)
        self.assertEqual(payload["findings"], [])
        self.assertEqual(payload["carrier_readback"]["mode"], "staged")
        rows = payload["carrier_readback"]["rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["file"], "docs/process_improvements/triaged__process_improvements_backlog.md")
        self.assertEqual(rows[0]["entry_id"], "PI-001")
        self.assertIn("priority", rows[0]["missing_fields"])
        self.assertIn("target_canon_path", rows[0]["missing_fields"])
        self.assertIn("target_repo_scope", rows[0]["missing_fields"])
        self.assertIn("delivery_mode", rows[0]["missing_fields"])

    def test_json_carrier_readback_reports_open_rows_without_default_failure(self) -> None:
        root = self._root()
        self._write(
            root,
            "docs/process_improvements/open__process_improvements_backlog.md",
            backlog_text(
                source_ref="docs/plans/open.md",
                status="open",
                priority="P?",
                triage_note="auto-collected from memory-finalize general lane",
            ),
        )

        code, output = self._run("--project-root", str(root), "--format", "json")
        payload = json.loads(output)

        self.assertEqual(code, 0)
        self.assertEqual(payload["findings"], [])
        rows = payload["carrier_readback"]["rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "open")
        self.assertEqual(rows[0]["entry_id"], "PI-001")
        self.assertIn("priority", rows[0]["missing_fields"])
        self.assertIn("target_canon_path", rows[0]["missing_fields"])
        self.assertIn("target_repo_scope", rows[0]["missing_fields"])
        self.assertIn("delivery_mode", rows[0]["missing_fields"])
        self.assertIn("execution_kind", rows[0]["missing_fields"])
        self.assertIn("execution_ref", rows[0]["missing_fields"])

    def test_require_triage_carrier_turns_readback_into_hard_findings(self) -> None:
        root = self._root()
        self._write(
            root,
            "docs/process_improvements/triaged__process_improvements_backlog.md",
            backlog_text(
                source_ref="docs/plans/triaged.md",
                status="triaged",
                priority="P?",
                triage_note="needs target owner decision",
            ),
        )

        code, output = self._run("--project-root", str(root), "--require-triage-carrier")

        self.assertEqual(code, 1)
        self.assertIn("docs/process_improvements/triaged__process_improvements_backlog.md", output)
        self.assertIn("missing_triage_carrier", output)
        self.assertIn("PI-001 missing triage carrier field(s): priority", output)

    def test_require_triage_carrier_fails_on_open_rows_with_null_carrier(self) -> None:
        root = self._root()
        self._write(
            root,
            "docs/process_improvements/open__process_improvements_backlog.md",
            backlog_text(
                source_ref="docs/plans/open.md",
                status="open",
                priority="P?",
                triage_note="auto-collected from memory-finalize general lane",
            ),
        )

        code, output = self._run("--project-root", str(root), "--require-triage-carrier")

        self.assertEqual(code, 1)
        self.assertIn("docs/process_improvements/open__process_improvements_backlog.md", output)
        self.assertIn("PI-001 missing triage carrier field(s): priority", output)
        self.assertIn("execution_ref", output)

    def test_default_and_directory_selection_exclude_derived_surfaces(self) -> None:
        root = self._root()
        self._write(
            root,
            "docs/process_improvements/source__process_improvements_backlog.md",
            backlog_text(),
        )
        for support_name in ("README.md", "index.md", "deferred.md", "promotion_surface.md"):
            self._write(root, f"docs/process_improvements/{support_name}", "not a backlog\n")

        code, output = self._run(
            "--project-root",
            str(root),
            "--format",
            "json",
            "docs/process_improvements",
        )
        payload = json.loads(output)

        self.assertEqual(code, 0)
        self.assertEqual(payload["files"], ["docs/process_improvements/source__process_improvements_backlog.md"])
        self.assertEqual(payload["findings"], [])

    def test_missing_explicit_path_fails_closed(self) -> None:
        root = self._root()

        code, output = self._run(
            "--project-root",
            str(root),
            "docs/process_improvements/missing__process_improvements_backlog.md",
        )

        self.assertEqual(code, 1)
        self.assertIn("missing_path", output)

    def test_lint_does_not_mutate_input_files(self) -> None:
        root = self._root()
        path = self._write(
            root,
            "docs/process_improvements/source__process_improvements_backlog.md",
            backlog_text(),
        )
        before = path.read_text(encoding="utf-8")

        code, _ = self._run("--project-root", str(root), str(path))
        after = path.read_text(encoding="utf-8")

        self.assertEqual(code, 0)
        self.assertEqual(after, before)

    def test_empty_directory_is_explicit_ok_with_no_files(self) -> None:
        root = self._root()
        (root / "docs" / "process_improvements").mkdir(parents=True)

        code, output = self._run("--project-root", str(root), "--format", "json")
        payload = json.loads(output)

        self.assertEqual(code, 0)
        self.assertEqual(payload["files"], [])
        self.assertEqual(payload["findings"], [])


if __name__ == "__main__":
    unittest.main()

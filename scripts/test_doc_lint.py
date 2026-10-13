#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from textwrap import dedent
from unittest import mock


MODULE_PATH = Path(__file__).with_name("doc_lint.py")
SPEC = importlib.util.spec_from_file_location("doc_lint", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
I18N_HELPER_PATH = Path(__file__).with_name("i18n_pairs.py")


class DocLintBasicHygieneTests(unittest.TestCase):
    def _write(self, root: Path, rel_path: str, text: str) -> Path:
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return target

    def test_basic_hygiene_green_explicit_root_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target = self._write(root, "docs/reviews/new_report.md", "# Report\n\nClean line.\n")

            findings = MODULE.lint_basic_hygiene([target])

        self.assertEqual(findings, [])

    def test_basic_hygiene_trailing_whitespace_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target = self._write(root, "docs/reviews/new_report.md", "# Report\n\nDirty line.  \n")

            findings = MODULE.lint_basic_hygiene([target])

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].line, 3)
        self.assertEqual(findings[0].message, "Trailing whitespace")

    def test_memory_followups_generated_header_passes_git_diff_check(self) -> None:
        if shutil.which("git") is None:
            self.skipTest("git is required for git diff --check proof")

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            subprocess.run(["git", "init"], cwd=root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            target = self._write(
                root,
                "docs/followups/260617_092300_followups_memory_coder.md",
                "\n".join(
                    [
                        "# Follow-ups backlog - memory finalize",
                        "",
                        "**Date:** 2026-06-17 09:23 MSK",
                        "**Source:** memory-finalize",
                        "**Status:** Draft",
                        "**Schema version:** followups.v1",
                        "",
                    ]
                ),
            )

            subprocess.run(["git", "add", str(target.relative_to(root))], cwd=root, check=True)
            good = subprocess.run(["git", "diff", "--cached", "--check"], cwd=root, text=True, capture_output=True)

            target.write_text(
                "\n".join(
                    [
                        "# Follow-ups backlog - memory finalize",
                        "",
                        "**Date:** 2026-06-17 09:23 MSK  ",
                        "**Source:** memory-finalize  ",
                        "**Status:** Draft  ",
                        "**Schema version:** followups.v1",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            subprocess.run(["git", "add", str(target.relative_to(root))], cwd=root, check=True)
            bad = subprocess.run(["git", "diff", "--cached", "--check"], cwd=root, text=True, capture_output=True)

        self.assertEqual(good.returncode, 0, good.stdout + good.stderr)
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn("trailing whitespace", bad.stdout + bad.stderr)

    def test_source_template_metadata_headers_pass_basic_hygiene(self) -> None:
        source_templates = [
            MODULE.REPO_ROOT / "docs/rollout_packets/_template.md",
            MODULE.REPO_ROOT / "docs/reviews/_template_post_merge_audit.md",
            MODULE.REPO_ROOT / "docs/doc_reviews/_template_merge_range.md",
            MODULE.REPO_ROOT / "docs/code_reviews/_template_merge_range.md",
            MODULE.REPO_ROOT / "docs/doc_reviews/_template_single_commit.md",
            MODULE.REPO_ROOT / "docs/code_reviews/_template_single_commit.md",
        ]

        missing = [str(path) for path in source_templates if not path.exists()]
        findings = MODULE.lint_basic_hygiene(source_templates)

        self.assertEqual(missing, [])
        self.assertEqual(findings, [])

    def test_source_template_metadata_hard_break_headers_fail_basic_hygiene(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target = self._write(
                root,
                "docs/code_reviews/generated_review.md",
                "\n".join(
                    [
                        "# Code review - generated",
                        "",
                        "**Date:** DD.MM.YYYY HH:MM  ",
                        "**Range:** BASE=<sha> .. HEAD=<sha|HEAD>  ",
                        "**Status:** Черновик  ",
                        "",
                    ]
                ),
            )

            findings = MODULE.lint_basic_hygiene([target])

        self.assertEqual(
            [(finding.line, finding.message) for finding in findings],
            [
                (3, "Trailing whitespace"),
                (4, "Trailing whitespace"),
                (5, "Trailing whitespace"),
            ],
        )

    def test_basic_hygiene_raw_merge_marker_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target = self._write(root, "docs/reviews/new_report.md", "# Report\n<<<<<<< HEAD\n")

            findings = MODULE.lint_basic_hygiene([target])

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].line, 2)
        self.assertEqual(findings[0].message, "Raw merge marker")

    def test_main_basic_hygiene_scans_untracked_explicit_root_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            good = self._write(root, "docs/reviews/new_report.md", "# Report\n\nClean line.\n")
            bad = self._write(root, "docs/reviews/dirty_report.md", "# Dirty\n\nDirty line.  \n")
            stdout = io.StringIO()
            argv = ["doc_lint.py", "--check-basic-hygiene", "--root", str(good), "--root", str(bad)]

            with mock.patch.object(MODULE, "REPO_ROOT", root):
                with mock.patch.object(sys, "argv", argv):
                    with mock.patch("sys.stdout", stdout):
                        result = MODULE.main()

        self.assertEqual(result, 1)
        output = stdout.getvalue()
        self.assertIn("docs/reviews/dirty_report.md:3: ERROR: Trailing whitespace", output)
        self.assertIn("doc-lint: FAIL", output)

    def test_main_basic_hygiene_honors_explicit_roots_in_default_excluded_buckets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            dirty_plan = self._write(root, "docs/plans/new_plan.md", "# Plan\n\nDirty line.  \n")
            dirty_review = self._write(root, "docs/code_reviews/new_review.md", "# Review\n>>>>>>> branch\n")
            stdout = io.StringIO()
            argv = [
                "doc_lint.py",
                "--check-basic-hygiene",
                "--root",
                str(dirty_plan),
                "--root",
                str(dirty_review),
            ]
            default_excludes = (
                root / "docs" / "snapshots",
                root / "docs" / "plans",
                root / "docs" / "code_reviews",
                root / "docs" / "doc_reviews",
            )

            with mock.patch.object(MODULE, "REPO_ROOT", root):
                with mock.patch.object(MODULE, "DEFAULT_EXCLUDES", default_excludes):
                    with mock.patch.object(sys, "argv", argv):
                        with mock.patch("sys.stdout", stdout):
                            result = MODULE.main()

        self.assertEqual(result, 1)
        output = stdout.getvalue()
        self.assertIn("docs/plans/new_plan.md:3: ERROR: Trailing whitespace", output)
        self.assertIn("docs/code_reviews/new_review.md:2: ERROR: Raw merge marker", output)


class DocLintReviewabilityReceiptTests(unittest.TestCase):
    def _write_green_bundle(self, root: Path) -> None:
        for rel_path in MODULE.REVIEWABILITY_RECEIPT_BUNDLE:
            target = root / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            lines = [
                f"# Fixture for {rel_path}",
                "",
                f"- `{MODULE.REVIEWABILITY_RECEIPT_ANCHOR}`",
            ]
            if rel_path in MODULE.PROOF_PATH_CLASS_REQUIRED_FILES:
                lines.append(f"- `{MODULE.PROOF_PATH_CLASS_ANCHOR}`")
            if rel_path in MODULE.ANTI_FALSE_GREEN_REQUIRED_FILES:
                lines.append(f"- `{MODULE.ANTI_FALSE_GREEN_ANCHOR}`")
            target.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _remove_anchor(self, root: Path, rel_path: str, anchor: str) -> None:
        target = root / rel_path
        lines = target.read_text(encoding="utf-8").splitlines()
        filtered = [line for line in lines if anchor not in line]
        target.write_text("\n".join(filtered) + "\n", encoding="utf-8")

    def test_reviewability_receipt_green_bundle_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_green_bundle(root)

            findings = MODULE.lint_reviewability_preflight_receipt_bundle(root)

        self.assertEqual(findings, [])

    def test_missing_required_bundle_member_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_green_bundle(root)
            missing_rel = MODULE.REVIEWABILITY_RECEIPT_BUNDLE[0]
            (root / missing_rel).unlink()

            findings = MODULE.lint_reviewability_preflight_receipt_bundle(root)

        self.assertEqual(len(findings), 1)
        self.assertIn("Missing required reviewability bundle file:", findings[0].message)
        self.assertIn(missing_rel, findings[0].message)

    def test_missing_proof_path_class_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_green_bundle(root)
            broken_rel = "docs/roles/architect.md"
            self._remove_anchor(root, broken_rel, MODULE.PROOF_PATH_CLASS_ANCHOR)

            findings = MODULE.lint_reviewability_preflight_receipt_bundle(root)

        self.assertEqual(len(findings), 1)
        self.assertIn(MODULE.PROOF_PATH_CLASS_ANCHOR, findings[0].message)
        self.assertTrue(str(findings[0].file).endswith(broken_rel))

    def test_missing_anti_false_green_phrase_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_green_bundle(root)
            broken_rel = "docs/roles/coder.md"
            self._remove_anchor(root, broken_rel, MODULE.ANTI_FALSE_GREEN_ANCHOR)

            findings = MODULE.lint_reviewability_preflight_receipt_bundle(root)

        self.assertEqual(len(findings), 1)
        self.assertIn(MODULE.ANTI_FALSE_GREEN_ANCHOR, findings[0].message)
        self.assertTrue(str(findings[0].file).endswith(broken_rel))

    def test_main_surfaces_reviewability_receipt_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_green_bundle(root)
            broken_rel = "docs/tools/prompts/planner_status_driven.md"
            self._remove_anchor(root, broken_rel, MODULE.ANTI_FALSE_GREEN_ANCHOR)
            stdout = io.StringIO()
            argv = ["doc_lint.py", "--root", str(root / "docs")]

            with mock.patch.object(MODULE, "REPO_ROOT", root):
                with mock.patch.object(sys, "argv", argv):
                    with mock.patch("sys.stdout", stdout):
                        result = MODULE.main()

        self.assertEqual(result, 1)
        output = stdout.getvalue()
        self.assertIn(broken_rel, output)
        self.assertIn(MODULE.ANTI_FALSE_GREEN_ANCHOR, output)
        self.assertIn("doc-lint: FAIL", output)

    def test_main_skips_reviewability_guard_for_targeted_root_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_green_bundle(root)
            broken_rel = "docs/tools/prompts/planner_status_driven.md"
            self._remove_anchor(root, broken_rel, MODULE.ANTI_FALSE_GREEN_ANCHOR)
            stdout = io.StringIO()
            argv = ["doc_lint.py", "--root", str(root / "docs" / "roles" / "architect.md")]

            with mock.patch.object(MODULE, "REPO_ROOT", root):
                with mock.patch.object(sys, "argv", argv):
                    with mock.patch("sys.stdout", stdout):
                        result = MODULE.main()

        self.assertEqual(result, 0)
        output = stdout.getvalue()
        self.assertEqual(output.strip(), "doc-lint: OK")


class DocLintReceiptSchemaEmitterInventoryBundleTests(unittest.TestCase):
    def _write_green_bundle(self, root: Path) -> None:
        for rel_path in MODULE.RECEIPT_SCHEMA_EMITTER_INVENTORY_BUNDLE:
            target = root / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            lines = [f"# Fixture for {rel_path}", ""]
            lines.extend(f"- `{anchor}`" for anchor in MODULE.RECEIPT_SCHEMA_EMITTER_INVENTORY_ANCHORS)
            target.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _remove_anchor(self, root: Path, rel_path: str, anchor: str) -> None:
        target = root / rel_path
        lines = target.read_text(encoding="utf-8").splitlines()
        filtered = [line for line in lines if anchor not in line]
        target.write_text("\n".join(filtered) + "\n", encoding="utf-8")

    def _bundle_roots(self, root: Path) -> list[str]:
        return [
            item
            for rel_path in MODULE.RECEIPT_SCHEMA_EMITTER_INVENTORY_BUNDLE
            for item in ("--root", str(root / rel_path))
        ]

    def test_receipt_schema_emitter_inventory_green_bundle_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_green_bundle(root)

            findings = MODULE.lint_receipt_schema_emitter_inventory_bundle(root)

        self.assertEqual(findings, [])

    def test_missing_receipt_schema_emitter_inventory_anchor_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_green_bundle(root)
            broken_rel = "docs/code_drafts/_template.md"
            self._remove_anchor(root, broken_rel, "target decision")

            findings = MODULE.lint_receipt_schema_emitter_inventory_bundle(root)

        self.assertEqual(len(findings), 1)
        self.assertIn("Missing required receipt schema emitter inventory anchor", findings[0].message)
        self.assertIn("target decision", findings[0].message)
        self.assertTrue(str(findings[0].file).endswith(broken_rel))

    def test_main_surfaces_receipt_schema_emitter_inventory_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_green_bundle(root)
            broken_rel = "docs/tools/prompts/coder_censor.md"
            self._remove_anchor(root, broken_rel, "generated skeleton/bootstrap/readback emitters")
            stdout = io.StringIO()
            argv = ["doc_lint.py", *self._bundle_roots(root)]

            with mock.patch.object(MODULE, "REPO_ROOT", root):
                with mock.patch.object(sys, "argv", argv):
                    with mock.patch("sys.stdout", stdout):
                        result = MODULE.main()

        self.assertEqual(result, 1)
        output = stdout.getvalue()
        self.assertIn(broken_rel, output)
        self.assertIn("generated skeleton/bootstrap/readback emitters", output)
        self.assertIn("doc-lint: FAIL", output)

    def test_main_default_scope_surfaces_receipt_schema_emitter_inventory_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_green_bundle(root)
            broken_rel = "docs/code_drafts/_template.md"
            self._remove_anchor(root, broken_rel, "target decision")
            stdout = io.StringIO()
            argv = ["doc_lint.py"]
            default_roots = (
                root / "AGENTS.md",
                root / "README.md",
                root / "planveyor_owner_book.md",
                root / "docs" / "roles",
                root / "docs" / "playbooks",
                root / "docs" / "tools",
            )
            default_excludes = (
                root / "docs" / "snapshots",
                root / "docs" / "plans",
                root / "docs" / "code_reviews",
                root / "docs" / "doc_reviews",
            )

            with mock.patch.object(MODULE, "REPO_ROOT", root):
                with mock.patch.object(MODULE, "DEFAULT_ROOTS", default_roots):
                    with mock.patch.object(MODULE, "DEFAULT_EXCLUDES", default_excludes):
                        with mock.patch.object(MODULE, "lint_adr_bundle", return_value=[]):
                            with mock.patch.object(MODULE, "lint_descoped_debt_guard_bundle", return_value=[]):
                                with mock.patch.object(MODULE, "lint_generated_surface_freshness", return_value=[]):
                                    with mock.patch.object(sys, "argv", argv):
                                        with mock.patch("sys.stdout", stdout):
                                            result = MODULE.main()

        self.assertEqual(result, 1)
        output = stdout.getvalue()
        self.assertIn(broken_rel, output)
        self.assertIn("target decision", output)
        self.assertIn("doc-lint: FAIL", output)

    def test_main_skips_receipt_schema_guard_for_partial_targeted_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_green_bundle(root)
            broken_rel = "docs/tools/prompts/coder_censor.md"
            self._remove_anchor(root, broken_rel, "generated skeleton/bootstrap/readback emitters")
            stdout = io.StringIO()
            argv = ["doc_lint.py", "--root", str(root / "docs" / "tools" / "prompts" / "planner_status_driven.md")]

            with mock.patch.object(MODULE, "REPO_ROOT", root):
                with mock.patch.object(sys, "argv", argv):
                    with mock.patch("sys.stdout", stdout):
                        result = MODULE.main()

        self.assertEqual(result, 0)
        output = stdout.getvalue()
        self.assertEqual(output.strip(), "doc-lint: OK")


class DocLintReviewerManagerDeadlockBundleTests(unittest.TestCase):
    def _write_green_bundle(self, root: Path) -> None:
        for rel_path, anchors in MODULE.REVIEWER_MANAGER_DEADLOCK_FILE_ANCHORS:
            target = root / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            lines = [f"# Fixture for {rel_path}", ""]
            lines.extend(f"- `{anchor}`" for anchor in anchors)
            target.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _remove_anchor(self, root: Path, rel_path: str, anchor: str) -> None:
        target = root / rel_path
        lines = target.read_text(encoding="utf-8").splitlines()
        filtered = [line for line in lines if anchor not in line]
        target.write_text("\n".join(filtered) + "\n", encoding="utf-8")

    def test_reviewer_manager_deadlock_green_bundle_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_green_bundle(root)

            findings = MODULE.lint_reviewer_manager_deadlock_bundle(root)

        self.assertEqual(findings, [])

    def test_missing_reviewer_anchor_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_green_bundle(root)
            broken_rel = "docs/tools/prompts/reviewer_status_driven.md"
            self._remove_anchor(root, broken_rel, "Next owner")

            findings = MODULE.lint_reviewer_manager_deadlock_bundle(root)

        self.assertEqual(len(findings), 1)
        self.assertIn("Missing required reviewer/manager deadlock anchor", findings[0].message)
        self.assertIn("Next owner", findings[0].message)
        self.assertTrue(str(findings[0].file).endswith(broken_rel))

    def test_missing_manager_anchor_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_green_bundle(root)
            broken_rel = "docs/tools/prompts/manager_collab_merge_pipeline.md"
            self._remove_anchor(root, broken_rel, "blind endless rerun")

            findings = MODULE.lint_reviewer_manager_deadlock_bundle(root)

        self.assertEqual(len(findings), 1)
        self.assertIn("Missing required reviewer/manager deadlock anchor", findings[0].message)
        self.assertIn("blind endless rerun", findings[0].message)
        self.assertTrue(str(findings[0].file).endswith(broken_rel))

    def test_main_surfaces_reviewer_manager_deadlock_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_green_bundle(root)
            broken_rel = "docs/tools/prompts/manager_collab_merge_pipeline.md"
            self._remove_anchor(root, broken_rel, "blind endless rerun")
            stdout = io.StringIO()
            argv = ["doc_lint.py", "--root", str(root / "docs")]

            with mock.patch.object(MODULE, "REPO_ROOT", root):
                with mock.patch.object(sys, "argv", argv):
                    with mock.patch("sys.stdout", stdout):
                        result = MODULE.main()

        self.assertEqual(result, 1)
        output = stdout.getvalue()
        self.assertIn(broken_rel, output)
        self.assertIn("blind endless rerun", output)
        self.assertIn("doc-lint: FAIL", output)

    def test_main_skips_reviewer_manager_guard_for_targeted_root_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_green_bundle(root)
            broken_rel = "docs/tools/prompts/manager_collab_merge_pipeline.md"
            self._remove_anchor(root, broken_rel, "blind endless rerun")
            stdout = io.StringIO()
            argv = ["doc_lint.py", "--root", str(root / "docs" / "roles" / "reviewer.md")]

            with mock.patch.object(MODULE, "REPO_ROOT", root):
                with mock.patch.object(sys, "argv", argv):
                    with mock.patch("sys.stdout", stdout):
                        result = MODULE.main()

        self.assertEqual(result, 0)
        output = stdout.getvalue()
        self.assertEqual(output.strip(), "doc-lint: OK")


class DocLintDeScopedDebtGuardBundleTests(unittest.TestCase):
    def _write_green_bundle(self, root: Path) -> None:
        for rel_path, anchors in MODULE.DE_SCOPED_SHARED_GUARD_REQUIREMENTS:
            target = root / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            lines = [f"# Fixture for {rel_path}", ""]
            lines.extend(f"- `{anchor}`" for anchor in anchors)
            target.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_descoped_guard_green_bundle_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_green_bundle(root)

            findings = MODULE.lint_descoped_debt_guard_bundle(root)

        self.assertEqual(findings, [])

    def test_missing_descoped_guard_anchor_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_green_bundle(root)
            broken_rel = "docs/playbooks/post_merge_audit.md"
            target = root / broken_rel
            target.write_text("# Broken bundle\n", encoding="utf-8")

            findings = MODULE.lint_descoped_debt_guard_bundle(root)

        self.assertEqual(len(findings), 2)
        self.assertEqual(
            {finding.message for finding in findings},
            {
                "Missing required de-scoped debt guard anchor 'removed from active scope'",
                "Missing required de-scoped debt guard anchor 'lost follow-up during harvest/promotion'",
            },
        )
        self.assertTrue(all(str(finding.file).endswith(broken_rel) for finding in findings))


class DocLintAdrBundleTests(unittest.TestCase):
    GREEN_README = dedent(
        """\
        # ADRs в `planveyor`

        ## Статусы
        - `proposed`
        - `accepted`
        - `superseded`

        Правило:
        - `code-anchor` обязателен до перевода ADR в `accepted`;
        - shared/package naming: `NNN-topic.md`;
        - supersession truth lives in `## Superseded by / Supersedes`: новый ADR явно указывает `Supersedes`, а заменённый ADR остаётся со `status: "superseded"` и non-`N/A` значением `Superseded by`.
        - README должен описывать разделы `Canonical refs` и `Revisit signals`.

        ## Canonical refs

        - `docs/adr/_template.md`

        ## Revisit signals

        - `code-anchor` changed
        """
    )

    GREEN_TEMPLATE = dedent(
        """\
        ---
        status: "proposed"
        date: YYYY-MM-DD
        decision-makers: Architect
        source-range: "BASE..HEAD"
        source-plan: "docs/plans/YYMMDD_HHMM_topic.md"
        code-anchor: "N/A (required before accepted)"
        ---

        # <Короткий заголовок решения>

        ## Context and Problem Statement

        <Почему это решение понадобилось именно сейчас. 2–3 предложения.>

        ## Decision Drivers

        - <constraint / quality goal / risk>

        ## Considered Options

        - <option A>
        - <option B>

        ## Decision Outcome

        Chosen option: **<option>**, because <обоснование>.

        ## Consequences

        - Good: <позитивный эффект>
        - Bad / Watch: <trade-off / на что смотреть дальше>

        ## Confirmation

        <Как проверить, что решение materialized в репо>

        ## Canonical Refs

        - `docs/adr/README.md`

        ## Revisit Signals

        - `code-anchor` changed

        ## Superseded by / Supersedes

        - Supersedes: `N/A`
        - Superseded by: `N/A`
        """
    )

    def _write(self, root: Path, rel_path: str, text: str) -> Path:
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return target

    def _write_green_bundle(self, root: Path) -> None:
        self._write(root, "docs/adr/README.md", self.GREEN_README)
        self._write(root, "docs/adr/_template.md", self.GREEN_TEMPLATE)

    def _write_adr(
        self,
        root: Path,
        filename: str,
        *,
        status: str = "proposed",
        code_anchor: str = "N/A",
        supersedes: str = "N/A",
        superseded_by: str = "N/A",
    ) -> Path:
        return self._write(
            root,
            f"docs/adr/{filename}",
            dedent(
                f"""\
                ---
                status: "{status}"
                date: 2026-04-20
                decision-makers: Architect
                source-range: "deadbee..feed123"
                source-plan: "docs/plans/260417_0942_process_adr_state_machine_and_supersession_lint.md"
                code-anchor: "{code_anchor}"
                ---

                # Fixture ADR

                ## Context and Problem Statement

                Fixture.

                ## Decision Drivers

                - Keep ADR canon stable

                ## Considered Options

                - Docs-only
                - Linted carrier

                ## Decision Outcome

                Chosen option: **linted carrier**, because ADR drift should fail fast.

                ## Consequences

                - Good: consistent state machine
                - Bad / Watch: supersession links must stay reciprocal

                ## Confirmation

                - `python -B scripts/doc_lint.py --root docs/adr`

                ## Canonical Refs

                - `docs/adr/README.md`

                ## Revisit Signals

                - `code-anchor` changed

                ## Superseded by / Supersedes

                - Supersedes: `{supersedes}`
                - Superseded by: `{superseded_by}`
                """
            ),
        )

    def test_green_bundle_without_live_adrs_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_green_bundle(root)

            findings = MODULE.lint_adr_bundle(root)

        self.assertEqual(findings, [])

    def test_deprecated_status_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_green_bundle(root)
            broken_name = "260420_0100_legacy.md"
            self._write_adr(root, broken_name, status="deprecated")

            findings = MODULE.lint_adr_bundle(root)

        self.assertTrue(any("ADR status must be one of" in finding.message for finding in findings))
        self.assertTrue(any(str(finding.file).endswith(f"docs/adr/{broken_name}") for finding in findings))

    def test_accepted_requires_non_na_code_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_green_bundle(root)
            broken_name = "260420_0101_accepted.md"
            self._write_adr(root, broken_name, status="accepted", code_anchor="N/A")

            findings = MODULE.lint_adr_bundle(root)

        self.assertTrue(any("`accepted` ADR must carry a non-empty `code-anchor`" in finding.message for finding in findings))
        self.assertTrue(any(str(finding.file).endswith(f"docs/adr/{broken_name}") for finding in findings))

    def test_superseded_requires_superseded_by_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_green_bundle(root)
            broken_name = "260420_0102_old.md"
            self._write_adr(root, broken_name, status="superseded", superseded_by="N/A")

            findings = MODULE.lint_adr_bundle(root)

        self.assertTrue(
            any("`status: superseded` requires a non-`N/A` `Superseded by` ADR pointer" in finding.message for finding in findings)
        )
        self.assertTrue(any(str(finding.file).endswith(f"docs/adr/{broken_name}") for finding in findings))

    def test_supersession_missing_target_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_green_bundle(root)
            broken_name = "260420_0103_new.md"
            self._write_adr(root, broken_name, supersedes="260420_9999_missing.md")

            findings = MODULE.lint_adr_bundle(root)

        self.assertTrue(any("points to missing ADR file" in finding.message for finding in findings))
        self.assertTrue(any(str(finding.file).endswith(f"docs/adr/{broken_name}") for finding in findings))

    def test_supersession_reciprocity_drift_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_green_bundle(root)
            self._write_adr(root, "260420_0104_new.md", supersedes="260420_0105_old.md")
            broken_name = "260420_0105_old.md"
            self._write_adr(root, broken_name, status="superseded", superseded_by="N/A")

            findings = MODULE.lint_adr_bundle(root)

        self.assertTrue(any("ADR reciprocity drift" in finding.message for finding in findings))
        self.assertTrue(any(str(finding.file).endswith(f"docs/adr/{broken_name}") for finding in findings))

    def test_supersession_bare_id_pair_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_green_bundle(root)
            self._write_adr(root, "001-old.md", status="superseded", superseded_by="002-new")
            self._write_adr(root, "002-new.md", status="accepted", code_anchor="scripts/doc_lint.py:1", supersedes="001-old")

            findings = MODULE.lint_adr_bundle(root)

        self.assertEqual(findings, [])

    def test_supersession_missing_bare_id_target_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_green_bundle(root)
            broken_name = "002-new.md"
            self._write_adr(root, broken_name, status="accepted", code_anchor="scripts/doc_lint.py:1", supersedes="999-missing")

            findings = MODULE.lint_adr_bundle(root)

        self.assertTrue(any("points to missing ADR file" in finding.message for finding in findings))
        self.assertTrue(any(str(finding.file).endswith(f"docs/adr/{broken_name}") for finding in findings))

    def test_supersession_bare_id_reciprocity_drift_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_green_bundle(root)
            self._write_adr(root, "001-old.md", status="superseded", superseded_by="N/A")
            broken_name = "002-new.md"
            self._write_adr(root, broken_name, status="accepted", code_anchor="scripts/doc_lint.py:1", supersedes="001-old")

            findings = MODULE.lint_adr_bundle(root)

        self.assertTrue(any("ADR reciprocity drift" in finding.message for finding in findings))
        self.assertTrue(any(str(finding.file).endswith("docs/adr/001-old.md") for finding in findings))

    def test_main_surfaces_adr_bundle_drift_for_docs_adr_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_green_bundle(root)
            broken_rel = "docs/adr/260420_0106_accepted.md"
            self._write_adr(root, "260420_0106_accepted.md", status="accepted", code_anchor="N/A")
            stdout = io.StringIO()
            argv = ["doc_lint.py", "--root", str(root / "docs" / "adr")]

            with mock.patch.object(MODULE, "REPO_ROOT", root):
                with mock.patch.object(sys, "argv", argv):
                    with mock.patch("sys.stdout", stdout):
                        result = MODULE.main()

        self.assertEqual(result, 1)
        output = stdout.getvalue()
        self.assertIn(broken_rel, output)
        self.assertIn("`accepted` ADR must carry a non-empty `code-anchor`", output)
        self.assertIn("doc-lint: FAIL", output)

    def test_main_skips_adr_guard_for_unrelated_targeted_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_green_bundle(root)
            self._write_adr(root, "260420_0107_accepted.md", status="accepted", code_anchor="N/A")
            target = self._write(root, "docs/tools/placeholder.md", "# Placeholder\n")
            stdout = io.StringIO()
            argv = ["doc_lint.py", "--root", str(target)]

            with mock.patch.object(MODULE, "REPO_ROOT", root):
                with mock.patch.object(sys, "argv", argv):
                    with mock.patch("sys.stdout", stdout):
                        result = MODULE.main()

        self.assertEqual(result, 0)
        self.assertEqual(stdout.getvalue().strip(), "doc-lint: OK")

    def test_main_ignores_adr_template_placeholder_code_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write(root, "docs/adr/_template.md", "# ADR template\n")
            playbook = self._write(
                root,
                "docs/playbooks/post_merge_plan_harvest.md",
                "# Playbook: Post-merge — plan harvest\n\n"
                "- Если нужно, создай ADR draft в `docs/adr/NNN-topic.md` по `docs/adr/_template.md`.\n",
            )
            stdout = io.StringIO()
            argv = ["doc_lint.py", "--root", str(playbook), "--check-code-refs", "--code-refs-scope", "repo"]

            with mock.patch.object(MODULE, "REPO_ROOT", root):
                with mock.patch.object(sys, "argv", argv):
                    with mock.patch("sys.stdout", stdout):
                        result = MODULE.main()

        self.assertEqual(result, 0)
        self.assertEqual(stdout.getvalue().strip(), "doc-lint: OK")


class DocLintExplicitRootContractTests(unittest.TestCase):
    def _write(self, root: Path, rel_path: str, text: str) -> Path:
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return target

    def _run_main(
        self,
        root: Path,
        argv: list[str],
        *,
        default_excludes: tuple[Path, ...],
    ) -> tuple[int, str]:
        stdout = io.StringIO()
        with mock.patch.object(MODULE, "REPO_ROOT", root):
            with mock.patch.object(MODULE, "PRODUCT_REPO_ROOT", None):
                with mock.patch.object(MODULE, "DEFAULT_EXCLUDES", default_excludes):
                    with mock.patch.object(MODULE, "DEFAULT_EXCLUDE_FILES", ()):
                        with mock.patch.object(sys, "argv", argv):
                            with mock.patch("sys.stdout", stdout):
                                result = MODULE.main()
        return result, stdout.getvalue()

    def test_main_scans_exact_default_excluded_file_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target = self._write(root, "docs/plans/_template.md", "`docs/missing.md`\n")
            result, output = self._run_main(
                root,
                [
                    "doc_lint.py",
                    "--root",
                    str(target),
                    "--check-code-refs",
                    "--code-refs-scope",
                    "repo",
                ],
                default_excludes=(root / "docs/plans",),
            )

        self.assertEqual(result, 1)
        self.assertIn("Missing referenced file: docs/missing.md", output)

    def test_main_keeps_history_and_explicit_exclusion_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plans_dir = root / "docs/plans"
            target = self._write(plans_dir, "_template.md", "`docs/missing.md`\n")
            common_args = ["--check-code-refs", "--code-refs-scope", "repo"]
            cases = (
                (
                    "default_directory_root",
                    ["doc_lint.py", "--root", str(plans_dir), *common_args],
                ),
                (
                    "explicit_directory_exclude",
                    ["doc_lint.py", "--root", str(target), "--exclude", str(plans_dir), *common_args],
                ),
                (
                    "explicit_file_exclude",
                    ["doc_lint.py", "--root", str(target), "--exclude-file", str(target), *common_args],
                ),
            )
            for name, argv in cases:
                with self.subTest(name=name):
                    result, output = self._run_main(
                        root,
                        argv,
                        default_excludes=(plans_dir,),
                    )
                    self.assertEqual(result, 0)
                    self.assertEqual(output.strip(), "doc-lint: OK")

    def test_main_keeps_placeholder_exception_narrow(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target = self._write(
                root,
                "docs/tools/placeholders.md",
                "`docs/plans/...md` `docs/plans/...md_suffix.py` "
                "`docs/plans/...md/real_missing.md` `docs/other/...md` `docs/missing.md`\n",
            )
            result, output = self._run_main(
                root,
                [
                    "doc_lint.py",
                    "--root",
                    str(target),
                    "--check-code-refs",
                    "--code-refs-scope",
                    "repo",
                ],
                default_excludes=(root / "docs/plans",),
            )

        self.assertEqual(result, 1)
        self.assertNotIn("Missing referenced file: docs/plans/...md\n", output)
        self.assertIn("Missing referenced file: docs/plans/...md_suffix.py", output)
        self.assertIn("Missing referenced file: docs/plans/...md/real_missing.md", output)
        self.assertIn("Missing referenced file: docs/other/...md", output)
        self.assertIn("Missing referenced file: docs/missing.md", output)
        self.assertEqual(output.count("Missing referenced file:"), 4)

    def test_scope_selection_matches_explicit_default_excluded_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plans_dir = root / "docs/plans"
            target = self._write(plans_dir, "_template.md", "# Template\n")

            self.assertTrue(
                MODULE._target_is_selected_by_scope(
                    target,
                    [target],
                    [plans_dir],
                    [],
                    allow_default_excluded_explicit_files=[target],
                )
            )
            self.assertFalse(MODULE._target_is_selected_by_scope(target, [plans_dir], [plans_dir], []))
            self.assertFalse(MODULE._target_is_selected_by_scope(target, [target], [plans_dir], []))
            self.assertFalse(
                MODULE._target_is_selected_by_scope(
                    target,
                    [target],
                    [plans_dir],
                    [target],
                    allow_default_excluded_explicit_files=[target],
                )
            )

    def test_main_keeps_target_marker_nonlocal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            target = self._write(
                root,
                "docs/tools/marker.md",
                "`<target>/docs/_meta/planveyor_contract_authority.v1.json` "
                "`docs/_meta/planveyor_contract_authority.v1.json` "
                "`docs/_meta/real_missing.json`\n",
            )
            result, output = self._run_main(
                root,
                [
                    "doc_lint.py",
                    "--root",
                    str(target),
                    "--check-code-refs",
                    "--code-refs-scope",
                    "repo",
                ],
                default_excludes=(root / "docs/plans",),
            )

        self.assertEqual(result, 1)
        self.assertIn("Missing referenced file: docs/_meta/planveyor_contract_authority.v1.json", output)
        self.assertIn("Missing referenced file: docs/_meta/real_missing.json", output)
        self.assertEqual(output.count("Missing referenced file:"), 2)


class DocLintHarvestDurableCarrierTests(unittest.TestCase):
    def _write(self, root: Path, rel_path: str, text: str) -> Path:
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return target

    def _write_sibling_repo_bad_pair(self, product_root: Path) -> tuple[Path, Path]:
        report = self._write(
            product_root,
            "docs/reviews/260327_1700_plan_harvest_range_deadbee_feed123.md",
            "# Review: Plan harvest — range deadbee..feed123\n\n"
            "## Follow-ups (extracted; без дублей)\n\n"
            "- P1 `Owner smoke tail` — to=Planner — status=handled — why: already tracked in `260321_0115_followups_memory_architect.md`.\n",
        )
        backlog = self._write(
            product_root,
            "docs/followups/260327_1700_followups_range_deadbee_feed123.md",
            "# Follow-ups backlog — Architect range harvest\n\n"
            "## Range result\n\n"
            "- `NO FOLLOWUPS` — reason: already tracked elsewhere (`260321_0051_followups_memory_coder.md`).\n",
        )
        self._write(
            product_root,
            "docs/followups/260321_0115_followups_memory_architect.md",
            "# Follow-ups backlog — Architect memory dump\n",
        )
        self._write(
            product_root,
            "docs/followups/260321_0051_followups_memory_coder.md",
            "# Follow-ups backlog — Coder memory dump\n",
        )
        return report, backlog

    def _write_descoped_source_plan(self, root: Path) -> Path:
        return self._write(
            root,
            "docs/plans/260324_0020_router_slot_lease_controls_and_activity_timestamps.md",
            "# Plan: router slot lease controls and activity timestamps\n\n"
            "## Out of scope\n\n"
            "- Per-account `occupied by slot-XX` / `free` hint on `Accounts` cards intentionally removed from the active scope of this slice; если этот UX по-прежнему нужен, его надо вести отдельным Accounts-oriented follow-up.\n",
        )

    def test_no_followups_with_memory_dump_only_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            backlog = self._write(
                root,
                "docs/followups/260327_1700_followups_range_deadbee_feed123.md",
                "# Follow-ups backlog — Architect range harvest\n\n"
                "## Range result\n\n"
                "- `NO FOLLOWUPS` — reason: already tracked elsewhere (`260321_0051_followups_memory_coder.md`).\n",
            )
            self._write(
                root,
                "docs/followups/260321_0051_followups_memory_coder.md",
                "# Follow-ups backlog — Coder memory dump\n",
            )

            findings = MODULE.lint_harvest_durable_followup_carriers([backlog], root)

        self.assertEqual(len(findings), 1)
        self.assertIn("NO FOLLOWUPS cannot rely only on memory-dump carriers", findings[0].message)

    def test_handled_state_with_memory_dump_only_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            report = self._write(
                root,
                "docs/reviews/260327_1700_plan_harvest_range_deadbee_feed123.md",
                "# Review: Plan harvest — range deadbee..feed123\n\n"
                "## Follow-ups (extracted; без дублей)\n\n"
                "- P1 `Owner smoke tail` — to=Planner — status=handled — why: already tracked in `260321_0115_followups_memory_architect.md`.\n",
            )
            self._write(
                root,
                "docs/followups/260321_0115_followups_memory_architect.md",
                "# Follow-ups backlog — Architect memory dump\n",
            )

            findings = MODULE.lint_harvest_durable_followup_carriers([report], root)

        self.assertEqual(len(findings), 1)
        self.assertIn("Handled-state cannot rely only on memory-dump carriers", findings[0].message)

    def test_durable_backlog_and_canon_closure_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            report = self._write(
                root,
                "docs/reviews/260327_1700_plan_harvest_range_deadbee_feed123.md",
                "# Review: Plan harvest — range deadbee..feed123\n\n"
                "## Follow-ups (extracted; без дублей)\n\n"
                "- P0 `Primary tail` — to=Planner — status=handled — why: already tracked in `260327_1710_followups_range_deadbee_feed123.md`.\n"
                "- P1 `Canonized tail` — to=Planner — status=handled — why: closed by canon sync in `docs/roadmap.md`.\n",
            )
            self._write(
                root,
                "docs/followups/260327_1710_followups_range_deadbee_feed123.md",
                "# Follow-ups backlog — Architect range harvest\n",
            )
            self._write(
                root,
                "docs/roadmap.md",
                "# Roadmap\n",
            )

            findings = MODULE.lint_harvest_durable_followup_carriers([report], root)

        self.assertEqual(findings, [])

    def test_main_surfaces_harvest_memory_dump_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            report = self._write(
                root,
                "docs/reviews/260327_1700_plan_harvest_range_deadbee_feed123.md",
                "# Review: Plan harvest — range deadbee..feed123\n\n"
                "## Follow-ups (extracted; без дублей)\n\n"
                "- P1 `Owner smoke tail` — to=Planner — status=handled — why: already tracked in `260321_0115_followups_memory_architect.md`.\n",
            )
            self._write(
                root,
                "docs/followups/260321_0115_followups_memory_architect.md",
                "# Follow-ups backlog — Architect memory dump\n",
            )
            stdout = io.StringIO()
            argv = ["doc_lint.py", "--root", str(report)]

            with mock.patch.object(MODULE, "REPO_ROOT", root):
                with mock.patch.object(sys, "argv", argv):
                    with mock.patch("sys.stdout", stdout):
                        result = MODULE.main()

        self.assertEqual(result, 1)
        output = stdout.getvalue()
        self.assertIn("Handled-state cannot rely only on memory-dump carriers", output)
        self.assertIn("doc-lint: FAIL", output)

    def test_main_does_not_treat_playbook_as_harvest_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            playbook = self._write(
                root,
                "docs/playbooks/post_merge_plan_harvest.md",
                "# Playbook: Post-merge — plan harvest\n\n"
                "- `already tracked elsewhere` не означает ссылку только на `260321_0051_followups_memory_coder.md`.\n",
            )
            self._write(
                root,
                "docs/followups/260321_0051_followups_memory_coder.md",
                "# Follow-ups backlog — Coder memory dump\n",
            )
            stdout = io.StringIO()
            argv = ["doc_lint.py", "--root", str(playbook)]

            with mock.patch.object(MODULE, "REPO_ROOT", root):
                with mock.patch.object(sys, "argv", argv):
                    with mock.patch("sys.stdout", stdout):
                        result = MODULE.main()

        self.assertEqual(result, 0)
        self.assertEqual(stdout.getvalue().strip(), "doc-lint: OK")

    def test_guard_uses_product_repo_root_for_sibling_repo_files(self) -> None:
        with tempfile.TemporaryDirectory() as tooling_tmpdir:
            with tempfile.TemporaryDirectory() as product_tmpdir:
                tooling_root = Path(tooling_tmpdir)
                product_root = Path(product_tmpdir)
                report, backlog = self._write_sibling_repo_bad_pair(product_root)

                with mock.patch.object(MODULE, "REPO_ROOT", tooling_root):
                    with mock.patch.object(MODULE, "PRODUCT_REPO_ROOT", product_root):
                        findings = MODULE.lint_harvest_durable_followup_carriers([report, backlog])

        self.assertEqual(len(findings), 2)
        messages = [finding.message for finding in findings]
        self.assertTrue(any("Handled-state cannot rely only on memory-dump carriers" in message for message in messages))
        self.assertTrue(any("NO FOLLOWUPS cannot rely only on memory-dump carriers" in message for message in messages))

    def test_cli_surfaces_sibling_repo_failure_for_explicit_roots(self) -> None:
        with tempfile.TemporaryDirectory() as product_tmpdir:
            product_root = Path(product_tmpdir)
            report, backlog = self._write_sibling_repo_bad_pair(product_root)
            env = dict(os.environ)
            env["PLANVEYOR_PRODUCT_ROOT"] = str(product_root)

            result = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--root",
                    str(report.relative_to(product_root)),
                    "--root",
                    str(backlog.relative_to(product_root)),
                ],
                cwd=product_root,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("Handled-state cannot rely only on memory-dump carriers", result.stdout)
        self.assertIn("NO FOLLOWUPS cannot rely only on memory-dump carriers", result.stdout)
        self.assertIn("doc-lint: FAIL", result.stdout)

    def test_descoped_debt_missing_from_harvest_bundle_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_descoped_source_plan(root)
            report = self._write(
                root,
                "docs/reviews/260327_1038_plan_harvest_range_deadbee_feed123.md",
                "# Review: Plan harvest — range deadbee..feed123\n\n"
                "## Источники (git history; может быть удалено после harvest)\n"
                "- Plans (filenames only):\n"
                "  - `260324_0020_router_slot_lease_controls_and_activity_timestamps.md`\n\n"
                "## Follow-ups backlog (created)\n"
                "- `docs/followups/260327_1038_followups_range_deadbee_feed123.md`\n",
            )
            self._write(
                root,
                "docs/followups/260327_1038_followups_range_deadbee_feed123.md",
                "# Follow-ups backlog — Architect range harvest\n\n"
                "## Range result\n\n"
                "- `NO FOLLOWUPS` — reason: no remaining actionable debt after full-wave harvest.\n",
            )

            findings = MODULE.lint_harvest_durable_followup_carriers([report], root)

        self.assertEqual(len(findings), 1)
        self.assertIn("De-scoped actionable debt is not materialized", findings[0].message)
        self.assertIn("occupied by slot-XX", findings[0].message)

    def test_descoped_debt_with_promoted_followup_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_descoped_source_plan(root)
            report = self._write(
                root,
                "docs/reviews/260327_1038_plan_harvest_range_deadbee_feed123.md",
                "# Review: Plan harvest — range deadbee..feed123\n\n"
                "## Источники (git history; может быть удалено после harvest)\n"
                "- Plans (filenames only):\n"
                "  - `260324_0020_router_slot_lease_controls_and_activity_timestamps.md`\n\n"
                "## Follow-ups backlog (created)\n"
                "- `docs/followups/260327_1038_followups_range_deadbee_feed123.md`\n",
            )
            self._write(
                root,
                "docs/followups/260327_1038_followups_range_deadbee_feed123.md",
                "# Follow-ups backlog — Architect range harvest\n\n"
                "## Follow-ups (backlog)\n\n"
                "- P1 [ ] `occupied by slot-XX` / `free` hint on `Accounts` cards — cluster=ops — tags=accounts — to=Planner — status=promoted — plan=docs/plans/260327_2001_accounts_slot_hint_followup.md — why: already tracked elsewhere from `260324_0020_router_slot_lease_controls_and_activity_timestamps.md`\n",
            )
            self._write(
                root,
                "docs/plans/260327_2001_accounts_slot_hint_followup.md",
                "# Plan: Accounts slot hint follow-up\n\n"
                "**Status:** Architect initial draft\n\n"
                "## Out of scope\n\n"
                "- Unrelated promoted-plan-only cleanup intentionally removed from active scope; если по-прежнему нужно, вести отдельным follow-up.\n",
            )

            findings = MODULE.lint_harvest_durable_followup_carriers([report], root)

        self.assertEqual(findings, [])


class I18nPairFixture(unittest.TestCase):
    SOURCE = "docs/guides/guide.md"
    COPY = "docs/guides/guide.ru.md"
    SOURCE_TEXT = "# Guide\n\n**English** · [Русский](guide.ru.md)\n\nKeep pairs fresh.\n"
    COPY_BODY = "# Руководство\n\n[English](guide.md) · **Русский**\n\nДержите пары свежими.\n"

    def _write(self, root: Path, rel_path: str, data: str | bytes) -> Path:
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data.encode("utf-8") if isinstance(data, str) else data)
        return target

    def _write_source_markers(self, root: Path) -> None:
        self._write(root, "copier.yml", "_subdirectory: copier_template\n")
        (root / "copier_template").mkdir(exist_ok=True)
        self._write(root, "bin/planveyor", "#!/bin/sh\n")
        self._write(root, "scripts/planveyor.zsh", "# Runtime fixture\n")

    def _write_registry(self, root: Path, pairs: object, *, schema: object = None) -> Path:
        payload = {"schema": MODULE.I18N_PAIRS_SCHEMA if schema is None else schema, "pairs": pairs}
        return self._write(root, "i18n/pairs.json", json.dumps(payload, indent=2) + "\n")

    def _stamp_line(self, source_bytes: bytes, body: bytes, *, pair: str | None = None) -> bytes:
        # Built here, not through doc_lint, so the byte rule itself is under test.
        return (
            f"<!-- i18n: pair={pair or self.SOURCE} "
            f"pair-sha256={hashlib.sha256(source_bytes).hexdigest()} "
            f"self-sha256={hashlib.sha256(body).hexdigest()} -->\n"
        ).encode("utf-8")

    def _write_fresh_pair(self, root: Path, *, copy_body: str | None = None) -> tuple[Path, Path]:
        source = self._write(root, self.SOURCE, self.SOURCE_TEXT)
        body = (self.COPY_BODY if copy_body is None else copy_body).encode("utf-8")
        copy = self._write(root, self.COPY, self._stamp_line(source.read_bytes(), body) + body)
        self._write_registry(root, [{"source": self.SOURCE, "copy": self.COPY}])
        return source, copy

    def _findings(self, root: Path, *, strict: bool = False) -> list[tuple[str, int, str, str]]:
        return [
            (finding.file.relative_to(root.resolve()).as_posix(), finding.line, finding.severity, finding.message)
            for finding in MODULE.lint_i18n_pairs(root, strict=strict)
        ]

    def _run_helper(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", str(I18N_HELPER_PATH), "--project-root", str(root), *args],
            cwd=root,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
            capture_output=True,
            text=True,
            check=False,
        )


class DocLintI18nPairsTests(I18nPairFixture):
    def test_without_registry_there_are_no_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write(root, "README.md", "# Readme\n")
            self._write(root, "README.ru.md", "# Readme\n\nNo stamp and no registry.\n")

            self.assertIsNone(MODULE.load_i18n_pairs_registry(root))
            for strict in (False, True):
                with self.subTest(strict=strict):
                    self.assertEqual(MODULE.lint_i18n_pairs(root, strict=strict), [])

    def test_source_checkout_requires_registry_without_affecting_sibling(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write(root, "README.ru.md", "# Readme\n")
            # A generic Copier consumer is not the Planveyor source checkout.
            self._write(root, "copier.yml", "_subdirectory: copier_template\n")
            self.assertEqual(self._findings(root, strict=True), [])
            (root / "copier_template").mkdir()
            self.assertEqual(self._findings(root, strict=True), [])
            self._write(root, "bin/planveyor", "#!/bin/sh\n")
            self.assertEqual(self._findings(root, strict=True), [])
            self._write(root, "scripts/planveyor.zsh", "# Runtime fixture\n")
            for strict in (False, True):
                findings = self._findings(root, strict=strict)
                self.assertEqual(len(findings), 1, findings)
                self.assertEqual(findings[0][:3], ("i18n/pairs.json", 1, "ERROR"))
                self.assertIn("is missing from the Planveyor source checkout", findings[0][3])

    def test_bom_in_source_or_body_is_hashed_without_normalization(self) -> None:
        for role in ("source", "body"):
            with self.subTest(role=role), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                source_bytes = self.SOURCE_TEXT.encode("utf-8")
                body = self.COPY_BODY.encode("utf-8")
                if role == "source":
                    source_bytes = b"\xef\xbb\xbf" + source_bytes
                else:
                    body = b"\xef\xbb\xbf" + body
                self._write(root, self.SOURCE, source_bytes)
                self._write(root, self.COPY, self._stamp_line(source_bytes, body) + body)
                self._write_registry(root, [{"source": self.SOURCE, "copy": self.COPY}])
                self.assertEqual(self._findings(root, strict=True), [])

    def test_fresh_pair_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_fresh_pair(root)

            for strict in (False, True):
                with self.subTest(strict=strict):
                    self.assertEqual(self._findings(root, strict=strict), [])

    def test_changed_source_warns_and_strict_mode_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source, _copy = self._write_fresh_pair(root)
            source.write_bytes(source.read_bytes() + b"\nOne more English line.\n")

            for strict, severity in ((False, "WARN"), (True, "ERROR")):
                with self.subTest(strict=strict):
                    findings = self._findings(root, strict=strict)
                    self.assertEqual(len(findings), 1, findings)
                    self.assertEqual(findings[0][:3], (self.COPY, 1, severity))
                    self.assertIn(f"source {self.SOURCE} changed after the last sync", findings[0][3])
                    self.assertIn("pair-sha256 mismatch", findings[0][3])

    def test_changed_copy_warns_and_strict_mode_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _source, copy = self._write_fresh_pair(root)
            copy.write_bytes(copy.read_bytes() + "Новая строка без сверки.\n".encode("utf-8"))

            for strict, severity in ((False, "WARN"), (True, "ERROR")):
                with self.subTest(strict=strict):
                    findings = self._findings(root, strict=strict)
                    self.assertEqual(len(findings), 1, findings)
                    self.assertEqual(findings[0][:3], (self.COPY, 1, severity))
                    self.assertIn("self-sha256 mismatch", findings[0][3])

    def test_missing_or_malformed_stamp_fails(self) -> None:
        source_bytes = self.SOURCE_TEXT.encode("utf-8")
        body = self.COPY_BODY.encode("utf-8")
        good = self._stamp_line(source_bytes, body)
        pair_hash = hashlib.sha256(source_bytes).hexdigest().encode("ascii")
        self_hash = hashlib.sha256(body).hexdigest().encode("ascii")
        cases = {
            "no_stamp": (body, "stamp is missing"),
            "bom_before_stamp": (b"\xef\xbb\xbf" + good + body, "stamp is missing"),
            "short_hash": (good.replace(pair_hash, pair_hash[:-1]) + body, "stamp is malformed"),
            "uppercase_hash": (good.replace(self_hash, self_hash.upper()) + body, "stamp is malformed"),
            "extra_field": (good.replace(b" -->", b" lang=ru -->") + body, "stamp is malformed"),
            "extra_space": (good.replace(b" -->", b"  -->") + body, "stamp is malformed"),
            "no_lf_after_stamp": (good.rstrip(b"\n"), "stamp is malformed"),
            "invalid_utf8_stamp": (b"<!-- i18n: \xff -->\n" + body, "stamp is malformed"),
        }
        for name, (copy_bytes, expected) in cases.items():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                _source, copy = self._write_fresh_pair(root)
                copy.write_bytes(copy_bytes)

                findings = self._findings(root)

                self.assertEqual(len(findings), 1, findings)
                self.assertEqual(findings[0][:3], (self.COPY, 1, "ERROR"))
                self.assertIn(expected, findings[0][3])

    def test_wrong_pair_name_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source, copy = self._write_fresh_pair(root)
            body = self.COPY_BODY.encode("utf-8")
            copy.write_bytes(self._stamp_line(source.read_bytes(), body, pair="docs/guides/other.md") + body)

            findings = self._findings(root, strict=False)

        self.assertEqual(len(findings), 1, findings)
        self.assertEqual(findings[0][:3], (self.COPY, 1, "ERROR"))
        self.assertIn(f"names pair=docs/guides/other.md, but i18n/pairs.json pairs this copy with {self.SOURCE}", findings[0][3])

    def test_missing_source_or_copy_fails(self) -> None:
        for missing, expected in (
            (self.COPY, f"i18n pair copy is missing: {self.COPY} (source {self.SOURCE})"),
            (self.SOURCE, f"i18n pair source is missing: {self.SOURCE} (copy {self.COPY})"),
        ):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                self._write_fresh_pair(root)
                (root / missing).unlink()

                findings = self._findings(root)

                self.assertEqual(findings, [(missing, 1, "ERROR", expected)])

    def test_unregistered_copy_fails_outside_skipped_trees(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_fresh_pair(root)
            self._write(root, "docs/guides/extra.ru.md", "# Лишняя копия\n")
            for skipped in (
                ".git/README.ru.md",
                ".tmp/i18n/draft.ru.md",
                ".worktrees/branch/README.ru.md",
                "docs/plans/README.ru.md",
                "docs/snapshots/old.ru.md",
                "docs/code_reviews/review.ru.md",
                "docs/doc_reviews/review.ru.md",
                "node_modules/package/README.ru.md",
                "vendor/checkout/README.ru.md",
            ):
                self._write(root, skipped, "# Копия вне проверки\n")
            # A nested checkout is another repository, not part of this tree.
            self._write(root, "vendor/checkout/.git", "gitdir: elsewhere\n")

            findings = self._findings(root)

        self.assertEqual(len(findings), 1, findings)
        self.assertEqual(findings[0][:3], ("docs/guides/extra.ru.md", 1, "ERROR"))
        self.assertIn("docs/guides/extra.ru.md is not registered in i18n/pairs.json", findings[0][3])

    def test_cr_bytes_fail_without_normalization(self) -> None:
        for role, rel_path in (("source", self.SOURCE), ("copy", self.COPY)):
            with self.subTest(role=role), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                self._write_fresh_pair(root)
                target = root / rel_path
                lines = target.read_bytes().split(b"\n")
                lines[2] += b"\r"
                target.write_bytes(b"\n".join(lines))

                findings = self._findings(root)

                self.assertEqual(len(findings), 1, findings)
                self.assertEqual(findings[0][:3], (rel_path, 3, "ERROR"))
                self.assertIn(f"i18n pair {role} contains CR bytes", findings[0][3])

    def test_copy_must_sit_next_to_its_source(self) -> None:
        for copy_rel in ("docs/guide.ru.md", "docs/guides/other.ru.md"):
            with self.subTest(copy=copy_rel), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                self._write(root, self.SOURCE, self.SOURCE_TEXT)
                self._write(root, copy_rel, "# Руководство\n")
                self._write_registry(root, [{"source": self.SOURCE, "copy": copy_rel}])

                findings = self._findings(root)

                # The misplaced copy is named by the registry entry, so it is
                # reported once, as a registry problem.
                self.assertEqual(len(findings), 1, findings)
                self.assertEqual(findings[0][:3], ("i18n/pairs.json", 1, "ERROR"))
                self.assertIn(f"pairs[0].copy must sit next to its source as '{self.COPY}'", findings[0][3])

    def test_unreadable_or_wrong_registry_is_an_error(self) -> None:
        schema = MODULE.I18N_PAIRS_SCHEMA
        cases = {
            "not_json": "{not json\n",
            "duplicate_key": f'{{"schema": "{schema}", "schema": "{schema}", "pairs": []}}\n',
            "wrong_schema": json.dumps({"schema": "planveyor_i18n_pairs.v0", "pairs": []}),
            "extra_key": json.dumps({"schema": schema, "pairs": [], "notes": "x"}),
            "pairs_not_list": json.dumps({"schema": schema, "pairs": {}}),
        }
        for name, text in cases.items():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                self._write(root, "i18n/pairs.json", text)
                self._write(root, "README.ru.md", "# Readme\n")

                findings = self._findings(root)

                # An unusable registry names no pairs, so the scan for
                # unregistered copies is skipped instead of flagging them all.
                self.assertEqual(len(findings), 1, findings)
                self.assertEqual(findings[0][:3], ("i18n/pairs.json", 1, "ERROR"))
                self.assertTrue(findings[0][3].startswith("i18n pairs registry: "), findings[0][3])

    def test_bad_registry_entries_are_errors(self) -> None:
        cases = {
            "extra_entry_key": ([{"source": "README.md", "copy": "README.ru.md", "lang": "ru"}], "exactly the keys"),
            "absolute_path": ([{"source": "/README.md", "copy": "/README.ru.md"}], "pairs[0].source must be a repository-relative"),
            "parent_path": ([{"source": "../README.md", "copy": "../README.ru.md"}], "pairs[0].source must be a repository-relative"),
            "space_in_path": ([{"source": "docs/my guide.md", "copy": "docs/my guide.ru.md"}], "without spaces"),
            "copy_as_source": ([{"source": "README.ru.md", "copy": "README.ru.ru.md"}], "pairs[0].source must name"),
            "not_markdown": ([{"source": "README.txt", "copy": "README.ru.md"}], "pairs[0].source must name"),
        }
        for name, (pairs, expected) in cases.items():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                self._write_registry(root, pairs)

                findings = self._findings(root)

                self.assertEqual(len(findings), 1, findings)
                self.assertEqual(findings[0][:3], ("i18n/pairs.json", 1, "ERROR"))
                self.assertIn(expected, findings[0][3])

    def test_duplicate_pair_is_reported_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_fresh_pair(root)
            entry = {"source": self.SOURCE, "copy": self.COPY}
            self._write_registry(root, [entry, entry])

            findings = self._findings(root)

        self.assertEqual(len(findings), 1, findings)
        self.assertEqual(findings[0][:3], ("i18n/pairs.json", 1, "ERROR"))
        self.assertIn(f"pairs[1] repeats the pair for '{self.SOURCE}'", findings[0][3])


class DocLintI18nPairsHelperTests(I18nPairFixture):
    def test_stamp_writes_only_the_first_line_and_check_turns_clean(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = self._write(root, self.SOURCE, self.SOURCE_TEXT)
            body = self.COPY_BODY.encode("utf-8")
            copy = self._write(root, self.COPY, body)
            self._write_registry(root, [{"source": self.SOURCE, "copy": self.COPY}])
            self.assertIn("stamp is missing", self._findings(root)[0][3])

            first = self._run_helper(root, "stamp", self.COPY)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(first.stdout.strip(), f"{self.COPY}: stamped")
            self.assertEqual(copy.read_bytes(), self._stamp_line(source.read_bytes(), body) + body)
            check = self._run_helper(root, "check", "--strict")
            self.assertEqual((check.returncode, check.stdout.strip()), (0, "i18n-pairs: OK"), check.stderr)
            self.assertEqual(self._findings(root, strict=True), [])

            # A later sync replaces the stamp line and keeps the new body bytes.
            addition = "Новый абзац после сверки.\n".encode("utf-8")
            source.write_bytes(source.read_bytes() + b"A new paragraph.\n")
            copy.write_bytes(copy.read_bytes() + addition)
            second = self._run_helper(root, "stamp", str(copy))

            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(copy.read_bytes(), self._stamp_line(source.read_bytes(), body + addition) + body + addition)
            self.assertEqual(self._findings(root, strict=True), [])
            third = self._run_helper(root, "stamp", self.COPY)
            self.assertEqual((third.returncode, third.stdout.strip()), (0, f"{self.COPY}: stamp already current"))

    def test_stamp_replaces_a_malformed_stamp_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source, copy = self._write_fresh_pair(root)
            body = self.COPY_BODY.encode("utf-8")
            copy.write_bytes(b"<!-- i18n: pair=README.md broken -->\n" + body)

            result = self._run_helper(root, "stamp", self.COPY)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(copy.read_bytes(), self._stamp_line(source.read_bytes(), body) + body)

    def test_stamp_refuses_unregistered_copy_source_path_and_cr(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _source, copy = self._write_fresh_pair(root)
            extra = self._write(root, "docs/guides/extra.ru.md", "# Лишняя копия\n")

            unregistered = self._run_helper(root, "stamp", "docs/guides/extra.ru.md")
            self.assertEqual(unregistered.returncode, 1)
            self.assertIn("docs/guides/extra.ru.md is not a registered copy in i18n/pairs.json", unregistered.stderr)
            self.assertEqual(extra.read_text(encoding="utf-8"), "# Лишняя копия\n")

            source_path = self._run_helper(root, "stamp", self.SOURCE)
            self.assertEqual(source_path.returncode, 1)
            self.assertIn(f"stamp its copy {self.COPY}", source_path.stderr)

            crlf = copy.read_bytes().replace(b"\n", b"\r\n")
            copy.write_bytes(crlf)
            with_cr = self._run_helper(root, "stamp", self.COPY)
            self.assertEqual(with_cr.returncode, 1)
            self.assertIn(f"{self.COPY}:1 contains CR bytes", with_cr.stderr)
            self.assertEqual(copy.read_bytes(), crlf)

    def test_stamp_refuses_source_or_copy_symlink_before_changing_files(self) -> None:
        for role in ("source", "copy"):
            with self.subTest(role=role), tempfile.TemporaryDirectory() as tmpdir:
                fixture_root = Path(tmpdir)
                root = fixture_root / "project"
                source, copy = self._write_fresh_pair(root)
                target = source if role == "source" else copy
                external = self._write(fixture_root, "external/document.md", b"# External fixture\n")
                target.unlink()
                target.symlink_to(external)
                source_before = source.read_bytes()
                copy_before = copy.read_bytes()
                external_before = external.read_bytes()
                result = self._run_helper(root, "stamp", self.COPY)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn(f"{role} ", result.stderr)
                self.assertIn("must be a regular file, not a symlink", result.stderr)
                self.assertEqual(source.read_bytes(), source_before)
                self.assertEqual(copy.read_bytes(), copy_before)
                self.assertEqual(external.read_bytes(), external_before)

    def test_check_and_status_report_the_doc_lint_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source, _copy = self._write_fresh_pair(root)
            source.write_bytes(source.read_bytes() + b"Changed after the sync.\n")
            expected_lines = [
                f"{rel_path}:{line}: {severity}: {message}"
                for rel_path, line, severity, message in self._findings(root)
            ]

            check = self._run_helper(root, "check")
            strict = self._run_helper(root, "check", "--strict")
            status = self._run_helper(root, "status")

        self.assertEqual(check.returncode, 0, check.stderr)
        self.assertEqual(check.stdout.splitlines(), [*expected_lines, "i18n-pairs: OK (1 warnings)"])
        self.assertEqual(strict.returncode, 1)
        self.assertIn(f"{self.COPY}:1: ERROR: i18n pair is stale", strict.stdout)
        self.assertIn("i18n-pairs: FAIL (1 errors, 0 warnings)", strict.stdout)
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn("i18n/pairs.json: 1 pairs", status.stdout)
        self.assertIn(f"stale  {self.SOURCE} -> {self.COPY}", status.stdout)

    def test_helper_without_registry_reports_pair_checks_off(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write(root, "README.ru.md", "# Readme\n")

            check = self._run_helper(root, "check", "--strict")
            stamp = self._run_helper(root, "stamp", "README.ru.md")

        self.assertEqual(check.returncode, 0, check.stderr)
        self.assertIn("pair checks are off", check.stdout)
        self.assertEqual(stamp.returncode, 1)
        self.assertIn("no registry at i18n/pairs.json", stamp.stderr)

    def test_helper_strict_rejects_missing_source_registry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_source_markers(root)
            self._write(root, "README.ru.md", "# Readme\n")
            result = self._run_helper(root, "check", "--strict")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("i18n/pairs.json is missing from the Planveyor source checkout", result.stdout)
        self.assertIn("FAIL (1 errors, 0 warnings)", result.stdout)
        self.assertNotIn("pair checks are off", result.stdout)

    def test_cli_help_describes_the_commands_and_the_strict_flag(self) -> None:
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        helper = subprocess.run(
            [sys.executable, "-B", str(I18N_HELPER_PATH), "--help"],
            env=env, capture_output=True, text=True, check=False,
        )
        lint = subprocess.run(
            [sys.executable, "-B", str(MODULE_PATH), "--help"],
            env=env, capture_output=True, text=True, check=False,
        )

        self.assertEqual(helper.returncode, 0, helper.stderr)
        for command in ("stamp", "check", "status"):
            self.assertIn(command, helper.stdout)
        self.assertIn(MODULE.I18N_STAMP_SHAPE, helper.stdout)
        self.assertEqual(lint.returncode, 0, lint.stderr)
        self.assertIn("--i18n-strict", lint.stdout)


class DocLintI18nPairsMainTests(I18nPairFixture):
    def _run_main(self, root: Path, argv: list[str]) -> tuple[int, str]:
        stdout = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(MODULE, "REPO_ROOT", root))
            stack.enter_context(mock.patch.object(MODULE, "PRODUCT_REPO_ROOT", None))
            stack.enter_context(
                mock.patch.object(
                    MODULE,
                    "DEFAULT_ROOTS",
                    (root / "README.md", root / "README.ru.md", root / "docs" / "guides"),
                )
            )
            stack.enter_context(
                mock.patch.object(
                    MODULE,
                    "DEFAULT_EXCLUDES",
                    tuple(root / rel_dir for rel_dir in MODULE.DEFAULT_EXCLUDE_DIRS_REL),
                )
            )
            stack.enter_context(mock.patch.object(MODULE, "DEFAULT_EXCLUDE_FILES", ()))
            for name in (
                "lint_receipt_schema_emitter_inventory_bundle",
                "lint_adr_bundle",
                "lint_descoped_debt_guard_bundle",
                "lint_generated_surface_freshness",
            ):
                stack.enter_context(mock.patch.object(MODULE, name, return_value=[]))
            stack.enter_context(mock.patch.object(sys, "argv", argv))
            stack.enter_context(mock.patch("sys.stdout", stdout))
            result = MODULE.main()
        return result, stdout.getvalue()

    def test_default_roots_cover_human_documents(self) -> None:
        for rel_path in ("README.ru.md", "CONTRIBUTING.md", "SECURITY.md", "docs/guides"):
            with self.subTest(root=rel_path):
                self.assertIn(MODULE.REPO_ROOT / rel_path, MODULE.DEFAULT_ROOTS)
        self.assertEqual(
            MODULE.DEFAULT_EXCLUDES,
            tuple(MODULE.REPO_ROOT / rel_dir for rel_dir in MODULE.DEFAULT_EXCLUDE_DIRS_REL),
        )

    def test_main_default_scope_runs_the_pair_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            source, _copy = self._write_fresh_pair(root)
            source.write_bytes(source.read_bytes() + b"Changed after the sync.\n")

            result, output = self._run_main(root, ["doc_lint.py"])
            strict_result, strict_output = self._run_main(root, ["doc_lint.py", "--i18n-strict"])

        self.assertEqual(result, 0, output)
        self.assertIn(f"{self.COPY}:1: WARN: i18n pair is stale", output)
        self.assertIn("doc-lint: OK (1 warnings)", output)
        self.assertEqual(strict_result, 1, strict_output)
        self.assertIn(f"{self.COPY}:1: ERROR: i18n pair is stale", strict_output)
        self.assertIn("doc-lint: FAIL (1 errors, 0 warnings)", strict_output)

    def test_main_default_scope_without_registry_stays_green(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write(root, "README.md", "# Readme\n")
            self._write(root, "README.ru.md", "# Readme\n\nNo stamp and no registry.\n")

            result, output = self._run_main(root, ["doc_lint.py"])

        self.assertEqual((result, output.strip()), (0, "doc-lint: OK"))

    def test_registered_copy_is_linted_with_its_source_once(self) -> None:
        broken_body = self.COPY_BODY + "\nСм. [пропавший файл](missing.md).\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_fresh_pair(root, copy_body=broken_body)
            copy_lines = (root / self.COPY).read_text(encoding="utf-8").splitlines()
            line_no = next(index for index, line in enumerate(copy_lines, start=1) if "missing.md" in line)
            broken_line = f"{self.COPY}:{line_no}: ERROR: Broken link target: missing.md"
            source = str(root / self.SOURCE)
            copy = str(root / self.COPY)
            runs = {
                "source_root": ["doc_lint.py", "--root", source],
                "source_and_copy_roots": ["doc_lint.py", "--root", source, "--root", copy],
                "default_scope": ["doc_lint.py"],
            }
            outputs = {name: self._run_main(root, argv) for name, argv in runs.items()}
            excluded = MODULE.with_registered_i18n_copies([root / self.SOURCE], root, [root / self.COPY])
            (root / "i18n" / "pairs.json").unlink()
            without_registry = self._run_main(root, ["doc_lint.py", "--root", source])

        for name, (result, output) in outputs.items():
            with self.subTest(run=name):
                self.assertEqual(result, 1, output)
                self.assertEqual(output.count(broken_line), 1, output)
        self.assertEqual(excluded, [root / self.SOURCE])
        self.assertEqual(without_registry, (0, "doc-lint: OK\n"))

    def test_main_explicit_roots_check_selected_pairs_and_strict_checks_all(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_fresh_pair(root)
            self._write(root, "docs/guides/extra.ru.md", "# Лишняя копия\n")
            argv = ["doc_lint.py", "--root", str(root / self.SOURCE)]

            result, output = self._run_main(root, argv)
            strict_result, strict_output = self._run_main(root, [*argv, "--i18n-strict"])

        self.assertEqual((result, output.strip()), (0, "doc-lint: OK"))
        self.assertEqual(strict_result, 1, strict_output)
        self.assertIn("docs/guides/extra.ru.md:1: ERROR: docs/guides/extra.ru.md is not registered", strict_output)

    def test_main_selected_source_or_copy_reports_stale_pair_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            source, copy = self._write_fresh_pair(root)
            source.write_bytes(source.read_bytes() + b"Changed after the sync.\n")
            for selected in ((source,), (copy,), (source, copy)):
                argv = ["doc_lint.py"]
                for path in selected:
                    argv.extend(["--root", str(path)])
                result, output = self._run_main(root, argv)
                self.assertEqual(result, 0, output)
                self.assertEqual(output.count("WARN: i18n pair is stale:"), 1, output)
                self.assertIn("doc-lint: OK (1 warnings)", output)

    def test_main_unrelated_root_does_not_report_stale_pair(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            source, _copy = self._write_fresh_pair(root)
            source.write_bytes(source.read_bytes() + b"Changed after the sync.\n")
            unrelated = self._write(root, "docs/guides/unrelated.md", "# Unrelated\n")
            result, output = self._run_main(root, ["doc_lint.py", "--root", str(unrelated)])
        self.assertEqual((result, output.strip()), (0, "doc-lint: OK"))

    def test_main_selected_pair_catches_missing_or_invalid_members(self) -> None:
        cases = {
            "missing_source": "i18n pair source is missing",
            "missing_copy": "i18n pair copy is missing",
            "missing_stamp": "i18n sync stamp is missing",
            "malformed_stamp": "i18n sync stamp is malformed",
            "wrong_pair": "i18n sync stamp names pair=",
            "crlf": "i18n pair copy contains CR bytes",
        }
        for name, expected in cases.items():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                source, copy = self._write_fresh_pair(root)
                body = self.COPY_BODY.encode("utf-8")
                if name == "missing_source":
                    source.unlink()
                elif name == "missing_copy":
                    copy.unlink()
                elif name == "missing_stamp":
                    copy.write_bytes(body)
                elif name == "malformed_stamp":
                    copy.write_bytes(b"<!-- i18n: broken -->\n" + body)
                elif name == "wrong_pair":
                    copy.write_bytes(self._stamp_line(source.read_bytes(), body, pair="other.md") + body)
                else:
                    copy.write_bytes(copy.read_bytes().replace(b"\n", b"\r\n"))
                result, output = self._run_main(root, ["doc_lint.py", "--root", str(source)])
                self.assertEqual(result, 1, output)
                self.assertEqual(output.count(expected), 1, output)
                # A deleted copy also breaks the source's language-switch link.
                self.assertEqual(output.count("ERROR:"), 2 if name == "missing_copy" else 1, output)

    def test_main_missing_directory_root_still_checks_registered_pair(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_registry(root, [{"source": self.SOURCE, "copy": self.COPY}])
            selected_root = root / "docs/guides"
            self.assertFalse(selected_root.exists())
            result, output = self._run_main(root, ["doc_lint.py", "--root", str(selected_root)])
            self.assertEqual(result, 1, output)
            self.assertEqual(output.count("ERROR:"), 2, output)
            self.assertIn("i18n pair source is missing", output)
            self.assertIn("i18n pair copy is missing", output)
            self.assertEqual(
                MODULE.lint_i18n_pairs(root, strict=False, roots=[selected_root], exclude_dirs=[selected_root]),
                [],
            )
            unrelated_missing = root / "docs/unrelated"
            self.assertEqual(MODULE.lint_i18n_pairs(root, strict=False, roots=[unrelated_missing]), [])

    def test_main_anchors_keep_utf8_target_provenance_and_source_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            source, copy = self._write_fresh_pair(root)
            source.write_text("# Source\n\n[Missing](missing.md)\n[Copy](guide.ru.md#copy)\n", encoding="utf-8")
            copy.write_bytes(b"<!-- i18n: \xff -->\n# Copy\n")
            result, output = self._run_main(
                root, ["doc_lint.py", "--root", str(source), "--check-anchors"],
            )
            self.assertEqual(result, 1, output)
            self.assertEqual(output.count("ERROR:"), 2, output)
            self.assertIn(f"{self.SOURCE}:3: ERROR: Broken link target: missing.md", output)
            self.assertIn(f"{self.COPY}:1: ERROR: i18n sync stamp is malformed:", output)
            self.assertNotIn("Markdown file is not UTF-8", output)
            direct = MODULE.lint_file(source, None, True, {})
            utf8 = [finding for finding in direct if finding.message == "Markdown file is not UTF-8"]
            self.assertEqual([finding.file for finding in utf8], [copy])
            cli = subprocess.run(
                [sys.executable, "-B", str(MODULE_PATH), "--product-root", str(root),
                 "--root", str(source), "--check-anchors"],
                cwd=root,
                env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(cli.returncode, 1, cli.stderr)
            self.assertEqual(cli.stdout.count("ERROR:"), 2, cli.stdout)
            self.assertNotIn("Markdown file is not UTF-8", cli.stdout)
            self.assertNotIn("Traceback", cli.stderr)

    def test_main_explicit_root_catches_unregistered_selected_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_fresh_pair(root)
            extra = self._write(root, "docs/guides/extra.ru.md", "# Extra\n")
            result, output = self._run_main(root, ["doc_lint.py", "--root", str(extra)])
        self.assertEqual(result, 1, output)
        self.assertEqual(output.count("ERROR:"), 1, output)
        self.assertIn("extra.ru.md is not registered", output)

    def test_main_explicit_root_catches_malformed_registry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            source, _copy = self._write_fresh_pair(root)
            self._write(root, "i18n/pairs.json", "{broken\n")
            result, output = self._run_main(root, ["doc_lint.py", "--root", str(source)])
        self.assertEqual(result, 1, output)
        self.assertEqual(output.count("ERROR:"), 1, output)
        self.assertIn("i18n pairs registry:", output)

    def test_main_source_checkout_without_registry_fails_default_and_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_source_markers(root)
            source = self._write(root, "README.md", "# Readme\n")
            for args in ([], ["--i18n-strict"], ["--root", str(source)]):
                result, output = self._run_main(root, ["doc_lint.py", *args])
                self.assertEqual(result, 1, output)
                self.assertEqual(output.count("ERROR:"), 1, output)
                self.assertIn("i18n/pairs.json is missing from the Planveyor source checkout", output)

    def test_main_invalid_utf8_stamp_reports_one_error_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            source, copy = self._write_fresh_pair(root)
            copy.write_bytes(b"<!-- i18n: \xff -->\n" + self.COPY_BODY.encode("utf-8"))
            for args in ([], ["--i18n-strict"], ["--root", str(source)]):
                result, output = self._run_main(root, ["doc_lint.py", *args])
                self.assertEqual(result, 1, output)
                self.assertEqual(output.count("ERROR:"), 1, output)
                self.assertIn("i18n sync stamp is malformed:", output)
                self.assertIn("doc-lint: FAIL (1 errors, 0 warnings)", output)
            cli = subprocess.run(
                [sys.executable, "-B", str(MODULE_PATH), "--product-root", str(root),
                 "--root", str(source), "--i18n-strict"],
                cwd=root,
                env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(cli.returncode, 1, cli.stderr)
            self.assertEqual(cli.stdout.count("ERROR:"), 1, cli.stdout)
            self.assertIn("i18n sync stamp is malformed:", cli.stdout)
            self.assertNotIn("Traceback", cli.stderr)

    def test_main_invalid_utf8_document_without_pair_fails_normally(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            document = self._write(root, "README.md", b"# Readme\n\xff\n")
            result, output = self._run_main(root, ["doc_lint.py", "--root", str(document)])
        self.assertEqual(result, 1, output)
        self.assertIn("Markdown file is not UTF-8", output)
        self.assertIn("doc-lint: FAIL (1 errors, 0 warnings)", output)

    def test_selected_pair_scope_honors_explicit_exclusions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            source, copy = self._write_fresh_pair(root)
            source.write_bytes(source.read_bytes() + b"Changed after the sync.\n")
            findings = MODULE.lint_i18n_pairs(
                root,
                strict=False,
                roots=[root / "docs/guides"],
                exclude_files=[source, copy],
            )
        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()

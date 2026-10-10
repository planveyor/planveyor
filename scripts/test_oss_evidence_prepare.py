#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent.parent
HELPER = ROOT / "scripts" / "oss_evidence_prepare.py"


class OssEvidencePrepareTests(unittest.TestCase):
    def run_helper(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        self.assertGreaterEqual(len(args), 1)
        return subprocess.run(
            [sys.executable, "-B", str(HELPER), args[0], "--root", str(root), *args[1:]],
            text=True,
            capture_output=True,
            check=False,
        )

    def write(self, root: Path, rel: str, text: str) -> None:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def selected_row(
        self,
        source_path: str = "docs/tools/policy.md",
        category: str = "canon_notes",
        public_filename: str = "policy.md",
        why_included: str = "Reusable public workflow proof.",
    ) -> str:
        return "\t".join([source_path, category, public_filename, why_included]) + "\n"

    def test_inventory_scans_configured_markdown_corpus(self) -> None:
        with tempfile.TemporaryDirectory(prefix="oss_evidence_inventory_") as tmpdir:
            root = Path(tmpdir)
            self.write(root, "docs/plans/a.md", "# Plan A\n**Status:** Done\nwords\n")
            self.write(root, "docs/tools/policy.md", "# Policy\n")
            self.write(root, "docs/reviews/sources/source.md", "# Excluded\n")
            self.write(root, "README.md", "# Root readme\n")

            result = self.run_helper(root, "inventory", "--out", ".tmp/oss_release/candidates.tsv")

            self.assertEqual(result.returncode, 0, result.stderr)
            with (root / ".tmp/oss_release/candidates.tsv").open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle, delimiter="\t"))
            by_path = {row["source_path"]: row for row in rows}
            self.assertEqual(by_path["docs/plans/a.md"]["category"], "plans")
            self.assertEqual(by_path["docs/plans/a.md"]["status"], "Done")
            self.assertEqual(by_path["docs/tools/policy.md"]["category"], "canon_notes")
            self.assertNotIn("docs/reviews/sources/source.md", by_path)
            self.assertNotIn("README.md", by_path)

    def test_score_template_preserves_inventory_without_selecting(self) -> None:
        with tempfile.TemporaryDirectory(prefix="oss_evidence_score_") as tmpdir:
            root = Path(tmpdir)
            self.write(root, "docs/plans/a.md", "# Plan A\n")
            self.assertEqual(
                self.run_helper(root, "inventory", "--out", ".tmp/oss_release/candidates.tsv").returncode,
                0,
            )

            result = self.run_helper(
                root,
                "score-template",
                "--inventory",
                ".tmp/oss_release/candidates.tsv",
                "--out",
                ".tmp/oss_release/score.tsv",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            with (root / ".tmp/oss_release/score.tsv").open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle, delimiter="\t"))
            self.assertEqual(rows[0]["source_path"], "docs/plans/a.md")
            self.assertEqual(rows[0]["suggested_public_filename"], "a.md")
            self.assertEqual(rows[0]["why_included"], "")
            self.assertEqual(rows[0]["total_score"], "")

    def test_validate_selected_defaults_and_smoke_override(self) -> None:
        with tempfile.TemporaryDirectory(prefix="oss_evidence_validate_") as tmpdir:
            root = Path(tmpdir)
            self.write(root, "docs/tools/policy.md", "# Policy\n")
            self.write(root, ".tmp/oss_release/selected.tsv", self.selected_row())

            default_result = self.run_helper(
                root,
                "validate-selected",
                "--selected",
                ".tmp/oss_release/selected.tsv",
            )
            smoke_result = self.run_helper(
                root,
                "validate-selected",
                "--selected",
                ".tmp/oss_release/selected.tsv",
                "--min-count",
                "1",
                "--max-count",
                "50",
            )

            self.assertEqual(default_result.returncode, 2)
            self.assertIn("outside required range 30-50", default_result.stderr)
            self.assertEqual(smoke_result.returncode, 0, smoke_result.stderr)

    def test_validate_selected_rejects_unsafe_fields(self) -> None:
        with tempfile.TemporaryDirectory(prefix="oss_evidence_unsafe_") as tmpdir:
            root = Path(tmpdir)
            self.write(root, "docs/tools/policy.md", "# Policy\n")
            cases = {
                "bad_category.tsv": self.selected_row(category="plans"),
                "bad_filename.tsv": self.selected_row(public_filename="../policy.md"),
                "bad_source.tsv": self.selected_row(source_path="../docs/tools/policy.md"),
                "bad_sources_dir.tsv": self.selected_row(
                    source_path="docs/reviews/sources/source.md",
                    category="doc_reviews",
                ),
            }
            self.write(root, "docs/reviews/sources/source.md", "# Excluded\n")
            for filename, text in cases.items():
                self.write(root, f".tmp/oss_release/{filename}", text)

                result = self.run_helper(
                    root,
                    "validate-selected",
                    "--selected",
                    f".tmp/oss_release/{filename}",
                    "--min-count",
                    "1",
                    "--max-count",
                    "50",
                )

                self.assertEqual(result.returncode, 2, filename)

    def test_copy_layout_matches_manifest_public_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="oss_evidence_copy_") as tmpdir:
            root = Path(tmpdir)
            self.write(root, "docs/tools/policy.md", "# Policy\nBody\n")
            self.write(root, ".tmp/oss_release/selected.tsv", self.selected_row())
            staged = ".tmp/oss_release/staged_evidence"

            copy_result = self.run_helper(
                root,
                "copy-selected",
                "--selected",
                ".tmp/oss_release/selected.tsv",
                "--dest",
                staged + "/docs/evidence",
                "--min-count",
                "1",
                "--max-count",
                "50",
            )
            manifest_result = self.run_helper(
                root,
                "manifest",
                "--selected",
                ".tmp/oss_release/selected.tsv",
                "--out",
                ".tmp/oss_release/manifest.json",
                "--min-count",
                "1",
                "--max-count",
                "50",
            )

            self.assertEqual(copy_result.returncode, 0, copy_result.stderr)
            self.assertEqual(manifest_result.returncode, 0, manifest_result.stderr)
            stage_root = root / staged
            copied = stage_root / "docs/evidence/canon_notes/policy.md"
            self.assertEqual(copied.read_text(encoding="utf-8"), "# Policy\nBody\n")
            payload = json.loads((root / ".tmp/oss_release/manifest.json").read_text(encoding="utf-8"))
            manifest_paths = {item["public_path"] for item in payload["items"]}
            staged_paths = {
                path.relative_to(stage_root).as_posix()
                for path in stage_root.rglob("*")
                if path.is_file()
            }
            self.assertEqual(staged_paths, manifest_paths)

    def test_copy_selected_rejects_destination_outside_root(self) -> None:
        with tempfile.TemporaryDirectory(prefix="oss_evidence_copy_outside_") as tmpdir:
            root = Path(tmpdir)
            self.write(root, "docs/tools/policy.md", "# Policy\n")
            self.write(root, ".tmp/oss_release/selected.tsv", self.selected_row())

            result = self.run_helper(
                root,
                "copy-selected",
                "--selected",
                ".tmp/oss_release/selected.tsv",
                "--dest",
                "../outside",
                "--min-count",
                "1",
                "--max-count",
                "50",
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("must stay under repository root", result.stderr)

    def test_manifest_omits_private_source_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="oss_evidence_manifest_") as tmpdir:
            root = Path(tmpdir)
            self.write(root, "docs/tools/policy.md", "# Policy\n")
            self.write(root, ".tmp/oss_release/selected.tsv", self.selected_row())

            result = self.run_helper(
                root,
                "manifest",
                "--selected",
                ".tmp/oss_release/selected.tsv",
                "--out",
                ".tmp/oss_release/manifest.json",
                "--min-count",
                "1",
                "--max-count",
                "50",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads((root / ".tmp/oss_release/manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], "oss-evidence-manifest.v1")
            self.assertEqual(payload["items"][0]["public_path"], "docs/evidence/canon_notes/policy.md")
            self.assertEqual(payload["items"][0]["sanitization_status"], "pending")
            self.assertNotIn("source_path", json.dumps(payload))


if __name__ == "__main__":
    unittest.main()

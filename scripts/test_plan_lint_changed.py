#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest import mock
import unittest


REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = Path(__file__).with_name("plan_lint_changed.py")
SPEC = importlib.util.spec_from_file_location("plan_lint_changed", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class PlanLintChangedTests(unittest.TestCase):
    def _git(self, root: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            text=True,
            capture_output=True,
            check=True,
        )
        return result.stdout.strip()

    def _write(self, root: Path, rel_path: str, text: str) -> None:
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def _commit(self, root: Path, message: str) -> str:
        self._git(root, "add", ".")
        self._git(root, "commit", "-m", message)
        return self._git(root, "rev-parse", "HEAD")

    def _init_repo_with_base(self, root: Path) -> str:
        self._git(root, "init")
        self._git(root, "config", "user.name", "Test User")
        self._git(root, "config", "user.email", 'test' + '@' + 'example' + '.' + 'com')
        self._write(root, "docs/plans/260101_0000_historical_bad.md", "template-only historical plan\n")
        self._write(root, "docs/plans/README.md", "# plans readme\n")
        self._write(root, "scripts/plan_lint.py", "raise SystemExit(99)\n")
        return self._commit(root, "base")

    def test_filter_changed_paths_keeps_only_lintable_plan_files(self) -> None:
        paths = [
            "docs/plans/260615_1200_real_plan.md",
            "docs/plans/README.md",
            "docs/plans/_template.md",
            "docs/plans/_meta.md",
            "docs/plans/_archive/260615_1200_archived.md",
            "docs/plans/not_markdown.txt",
            "docs/reviews/260615_1200_review.md",
        ]

        self.assertEqual(MODULE.filter_plan_paths(paths), ["docs/plans/260615_1200_real_plan.md"])

    def test_print_only_reports_only_changed_plan_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            base = self._init_repo_with_base(root)
            self._write(root, "docs/plans/260615_1210_new_plan.md", "# Plan: new\n")
            self._write(root, "docs/plans/README.md", "# plans readme\n\nUpdated.\n")
            self._write(root, "docs/reviews/260615_1210_review.md", "# Review\n")
            head = self._commit(root, "changed plans")
            stdout = io.StringIO()

            with mock.patch("sys.stdout", stdout):
                result = MODULE.main(["--root", str(root), "--base", base, "--head", head, "--print-only"])

        self.assertEqual(result, 0)
        self.assertEqual(stdout.getvalue().splitlines(), ["docs/plans/260615_1210_new_plan.md"])

    def test_main_runs_plan_lint_only_for_changed_plan_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            base = self._init_repo_with_base(root)
            self._write(root, "docs/plans/260615_1220_new_plan.md", "# Plan: new\n")
            self._write(root, "docs/plans/README.md", "# plans readme\n\nUpdated.\n")
            head = self._commit(root, "changed plan")
            fake_lint = root / "fake_plan_lint.py"
            receipt = root / "lint_args.json"
            fake_lint.write_text(
                "from pathlib import Path\n"
                "import json\n"
                "import sys\n"
                f"Path({str(receipt)!r}).write_text(json.dumps(sys.argv[1:]), encoding='utf-8')\n",
                encoding="utf-8",
            )

            result = MODULE.main(["--root", str(root), "--base", base, "--head", head, "--plan-lint", str(fake_lint)])
            receipt_args = json.loads(receipt.read_text(encoding="utf-8"))

        self.assertEqual(result, 0)
        self.assertEqual(receipt_args, ["docs/plans/260615_1220_new_plan.md"])

    def test_main_propagates_plan_lint_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            base = self._init_repo_with_base(root)
            self._write(root, "docs/plans/260615_1230_new_plan.md", "# Plan: new\n")
            head = self._commit(root, "changed plan")
            fake_lint = root / "fake_plan_lint.py"
            fake_lint.write_text("import sys\nraise SystemExit(7)\n", encoding="utf-8")

            result = MODULE.main(["--root", str(root), "--base", base, "--head", head, "--plan-lint", str(fake_lint)])

        self.assertEqual(result, 7)

    def test_ci_workflow_runs_changed_plan_lint(self) -> None:
        workflow = (REPO_ROOT / ".github/workflows/checks.yml").read_text(encoding="utf-8")

        self.assertIn("fetch-depth: 0", workflow)
        self.assertIn(
            'planveyor_ci_base="$(git merge-base "origin/$BASE_BRANCH" HEAD)"',
            workflow,
        )
        self.assertIn("BEFORE_COMMIT: ${{ github.event.before }}", workflow)
        self.assertIn('planveyor_ci_base="$BEFORE_COMMIT"', workflow)
        self.assertIn('git cat-file -e "$planveyor_ci_base^{commit}"', workflow)
        self.assertIn(
            'planveyor_ci_base="$(git rev-list --max-parents=0 HEAD)"',
            workflow,
        )
        self.assertIn(
            'echo "PYBIN=$(python -c \'import sys; print(sys.executable)\')" >> "$GITHUB_ENV"',
            workflow,
        )
        self.assertIn(
            '"$PYBIN" -B scripts/plan_lint_changed.py --base "$planveyor_ci_base" --head HEAD',
            workflow,
        )


if __name__ == "__main__":
    unittest.main()

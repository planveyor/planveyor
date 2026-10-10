#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("strip_trailing_ws.py")
SPEC = importlib.util.spec_from_file_location("strip_trailing_ws", MODULE_PATH)


def _load_module():
    assert SPEC is not None and SPEC.loader is not None
    module = importlib.util.module_from_spec(SPEC)
    sys.modules[SPEC.name] = module
    SPEC.loader.exec_module(module)
    return module


class StripTrailingWsLoadTests(unittest.TestCase):
    def test_module_exposes_strip_text(self) -> None:
        module = _load_module()
        self.assertTrue(hasattr(module, "strip_text"))


class StripTextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = _load_module()

    def test_strips_trailing_spaces(self) -> None:
        out, stripped, skipped = self.module.strip_text(b"a   \nb  \n")
        self.assertEqual(out, b"a\nb\n")
        self.assertEqual(stripped, 2)
        self.assertEqual(skipped, 0)

    def test_strips_trailing_tabs(self) -> None:
        out, stripped, skipped = self.module.strip_text(b"a\t\t\n")
        self.assertEqual(out, b"a\n")
        self.assertEqual(stripped, 1)
        self.assertEqual(skipped, 0)

    def test_clean_text_unchanged(self) -> None:
        out, stripped, skipped = self.module.strip_text(b"a\nb\n")
        self.assertEqual(out, b"a\nb\n")
        self.assertEqual(stripped, 0)
        self.assertEqual(skipped, 0)

    def test_fence_content_is_preserved_and_reported(self) -> None:
        # Contract: fenced content is not rewritten by the mechanical stripper;
        # fenced trailing whitespace is reported as a manual-review hazard.
        text = b"text  \n```python\nx = 1   \n```\nmore  \n"
        out, stripped, skipped = self.module.strip_text(text)
        self.assertEqual(out, b"text\n```python\nx = 1   \n```\nmore\n")
        self.assertEqual(stripped, 2)
        self.assertEqual(skipped, 1)

    def test_fence_delimiters_are_stripped_but_content_is_preserved(self) -> None:
        text = b"```  \nx   \n```  \n"
        out, stripped, skipped = self.module.strip_text(text)
        self.assertEqual(out, b"```\nx   \n```\n")
        self.assertEqual(stripped, 2)
        self.assertEqual(skipped, 1)

    def test_tilde_fence_content_is_preserved_and_reported(self) -> None:
        text = b"a  \n~~~\nb   \n~~~\n"
        out, stripped, skipped = self.module.strip_text(text)
        self.assertEqual(out, b"a\n~~~\nb   \n~~~\n")
        self.assertEqual(stripped, 1)
        self.assertEqual(skipped, 1)

    def test_crlf_preserved_and_stripped(self) -> None:
        out, stripped, skipped = self.module.strip_text(b"a  \r\nb\r\n")
        self.assertEqual(out, b"a\r\nb\r\n")
        self.assertEqual(stripped, 1)
        self.assertEqual(skipped, 0)

    def test_lf_preserved(self) -> None:
        out, stripped, skipped = self.module.strip_text(b"a  \nb\n")
        self.assertEqual(out, b"a\nb\n")
        self.assertEqual(stripped, 1)
        self.assertEqual(skipped, 0)

    def test_no_final_newline_preserved(self) -> None:
        out, stripped, skipped = self.module.strip_text(b"a   ")
        self.assertEqual(out, b"a")
        self.assertEqual(stripped, 1)
        self.assertEqual(skipped, 0)

    def test_idempotent_clean_text_is_noop(self) -> None:
        dirty = b"a   \n```python\nx = 1   \n```\nmore  \n"
        once, _, _ = self.module.strip_text(dirty)
        twice, stripped2, skipped2 = self.module.strip_text(once)
        # second pass: nothing to strip outside fences; fenced content remains
        # an explicit manual-review hazard rather than a silent rewrite.
        self.assertEqual(once, twice)
        self.assertEqual(stripped2, 0)
        self.assertEqual(skipped2, 1)


class ProcessFilesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = _load_module()

    def _write(self, root: Path, rel_path: str, text: bytes) -> Path:
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text)
        return target

    def test_process_files_strips_and_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            f = self._write(root, "docs/a.md", b"x   \ny\n")
            files_changed, lines_stripped, fenced_skipped = self.module.process_files(
                [f], dry_run=False
            )
            self.assertEqual(files_changed, 1)
            self.assertEqual(lines_stripped, 1)
            self.assertEqual(fenced_skipped, 0)
            self.assertEqual(f.read_bytes(), b"x\ny\n")

    def test_process_files_dry_run_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            f = self._write(root, "docs/a.md", b"x   \ny\n")
            files_changed, lines_stripped, fenced_skipped = self.module.process_files(
                [f], dry_run=True
            )
            self.assertEqual(files_changed, 1)
            self.assertEqual(lines_stripped, 1)
            # file untouched
            self.assertEqual(f.read_bytes(), b"x   \ny\n")

    def test_main_dry_run_zero_exit_with_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write(root, "docs/a.md", b"x   \n")
            rc = self.module.main(
                ["--root", str(root / "docs"), "--dry-run"]
            )
            self.assertEqual(rc, 0)

    def test_main_nonzero_when_fenced_skip_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            f = self._write(root, "docs/a.md", b"```\nx   \n```\n")
            rc = self.module.main(
                ["--root", str(root / "docs"), "--dry-run"]
            )
            self.assertNotEqual(rc, 0)
            self.assertEqual(f.read_bytes(), b"```\nx   \n```\n")

    def test_main_exclude_file_skips_file(self) -> None:
        # Strong test: --exclude-file must actually prevent the file from being
        # changed (not just yield exit 0). Asserting on file contents, not rc,
        # because rc==0 is also true if excludes were silently ignored.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            excluded = self._write(root, "docs/_template.md", b"x   \n")
            real = self._write(root, "docs/real.md", b"y   \n")
            rc = self.module.main(
                [
                    "--root", str(root / "docs"),
                    "--exclude-file", str(excluded),
                ]
            )
            self.assertEqual(rc, 0)
            # real.md is cleaned; excluded _template.md is left untouched
            self.assertEqual(real.read_bytes(), b"y\n")
            self.assertEqual(excluded.read_bytes(), b"x   \n")


if __name__ == "__main__":
    unittest.main()

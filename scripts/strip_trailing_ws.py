#!/usr/bin/env python3
"""One-shot fence-aware trailing-whitespace stripper for docs/** markdown.

Strips trailing spaces/tabs from lines outside code fences, preserving
line endings exactly (LF/CRLF) and final-newline state. Reports fenced
trailing-whitespace lines as a non-zero-exit hazard.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from pathlib import Path
from typing import Sequence


# Reuse doc_lint's file-discovery helper, loaded by path like the test modules.
_DOC_LINT_PATH = Path(__file__).resolve().with_name("doc_lint.py")
_doc_lint_spec = importlib.util.spec_from_file_location("doc_lint", _DOC_LINT_PATH)
assert _doc_lint_spec is not None and _doc_lint_spec.loader is not None
_doc_lint = importlib.util.module_from_spec(_doc_lint_spec)
sys.modules[_doc_lint_spec.name] = _doc_lint
_doc_lint_spec.loader.exec_module(_doc_lint)
iter_markdown_files = _doc_lint.iter_markdown_files


def _split_eol(line: str) -> tuple[str, str]:
    """Split a line into (body, eol); eol is '' if the line has none."""
    for cand in ("\r\n", "\n", "\r"):
        if line.endswith(cand):
            return line[: -len(cand)], cand
    return line, ""


def _strip_line(line: str) -> tuple[str, bool]:
    """Strip trailing whitespace from one line, preserving its EOL.

    Naive ``re.sub(r'[ \\t]+$', '', line)`` does NOT strip spaces before a
    CRLF (``$`` sits before ``\\n`` and ``\\r`` is between them). So we split
    the EOL off, strip the body, and re-attach the original EOL.
    Returns (new_line, was_stripped).
    """
    body, eol = _split_eol(line)
    new_body = re.sub(r"[ \t]+$", "", body)
    return new_body + eol, new_body != body


def _has_trailing_ws(line: str) -> bool:
    body, _ = _split_eol(line)
    return bool(re.search(r"[ \t]+$", body))


def _is_fence_delimiter(line: str) -> bool:
    stripped = line.lstrip()
    return stripped.startswith("```") or stripped.startswith("~~~")


def _toggle_fence(line: str, fence: str | None) -> str | None:
    stripped = line.lstrip()
    if fence is None:
        if stripped.startswith("```"):
            return "```"
        if stripped.startswith("~~~"):
            return "~~~"
        return None
    if stripped.startswith(fence):
        return None
    return fence


def strip_text(text: bytes) -> tuple[bytes, int, int]:
    """Strip trailing whitespace from ``text`` outside code fences.

    Returns ``(new_bytes, stripped_count, fenced_skip_count)``.
    """
    raw = text.decode("utf-8")
    fence: str | None = None
    stripped_count = 0
    fenced_skip_count = 0
    out_parts: list[str] = []

    # splitlines(keepends=True) preserves the exact EOL of each line.
    for line in raw.splitlines(keepends=True):
        if _is_fence_delimiter(line):
            new_line, was_stripped = _strip_line(line)
            if was_stripped:
                stripped_count += 1
            fence = _toggle_fence(new_line, fence)
            out_parts.append(new_line)
            continue
        if fence is not None:
            if _has_trailing_ws(line):
                fenced_skip_count += 1
            out_parts.append(line)
            continue
        new_line, was_stripped = _strip_line(line)
        if was_stripped:
            stripped_count += 1
        out_parts.append(new_line)

    return b"".join(p.encode("utf-8") for p in out_parts), stripped_count, fenced_skip_count


def process_files(
    files: Sequence[Path], dry_run: bool
) -> tuple[int, int, int]:
    """Strip each file in ``files`` in place (unless ``dry_run``).

    Returns ``(files_changed, lines_stripped, fenced_skipped)``.
    """
    files_changed = 0
    total_stripped = 0
    total_fenced = 0
    for path in files:
        original = path.read_bytes()
        new_bytes, stripped, fenced = strip_text(original)
        total_stripped += stripped
        total_fenced += fenced
        if new_bytes != original:
            files_changed += 1
            if not dry_run:
                path.write_bytes(new_bytes)
    return files_changed, total_stripped, total_fenced


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Strip trailing whitespace from markdown, fence-aware.",
    )
    parser.add_argument("--root", action="append", default=[],
                        help="Root dir/file to scan. Repeatable.")
    parser.add_argument("--exclude-file", action="append", default=[],
                        help="File to exclude. Repeatable.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report without writing.")
    args = parser.parse_args(argv)

    roots = [Path(p) for p in args.root]
    excludes = [Path(p).resolve() for p in args.exclude_file]
    # iter_markdown_files filters files via its exclude_file_set (it resolves
    # both sides internally), so no extra filtering is needed here.
    files = iter_markdown_files(roots, [], excludes)

    files_changed, lines_stripped, fenced_skipped = process_files(
        files, dry_run=args.dry_run
    )

    print(f"stripped {lines_stripped} lines across {files_changed} files")
    print(
        f"skipped {fenced_skipped} fenced trailing-whitespace lines "
        f"across {'some' if fenced_skipped else 0} files"
    )
    if fenced_skipped > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

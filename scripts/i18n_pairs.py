#!/usr/bin/env python3
"""Maintain the Russian copies of human documents registered in ``i18n/pairs.json``.

Commands:

- ``stamp <copy>`` writes or replaces the sync stamp in the first line of a
  registered copy and keeps every other byte;
- ``check [--strict]`` reports the same pair findings as ``doc_lint.py``;
- ``status`` lists the registered pairs and their state.

The pair rules live in ``doc_lint.py``; this helper calls the same functions.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import doc_lint


class StampRefused(RuntimeError):
    """The requested copy cannot be stamped."""


def _display_path(root: Path, path: Path) -> str:
    return doc_lint.rel_to(path, root)


def _print_findings(root: Path, findings: Sequence[doc_lint.Finding]) -> tuple[int, int]:
    ordered = sorted(findings, key=lambda finding: (_display_path(root, finding.file), finding.line, finding.message))
    for finding in ordered:
        print(f"{_display_path(root, finding.file)}:{finding.line}: {finding.severity}: {finding.message}")
    errors = sum(1 for finding in findings if finding.severity == "ERROR")
    warnings = sum(1 for finding in findings if finding.severity == "WARN")
    return errors, warnings


def stamp_copy(root: Path, copy_arg: str) -> tuple[str, bool]:
    """Stamp one registered copy; return its repository path and whether its bytes changed."""
    registry = doc_lint.load_i18n_pairs_registry(root)
    if registry is None:
        raise StampRefused(f"no registry at {doc_lint.I18N_PAIRS_REGISTRY}")
    if not registry.usable:
        raise StampRefused("; ".join(finding.message for finding in registry.findings))

    copy_path = Path(copy_arg).expanduser()
    if not copy_path.is_absolute():
        copy_path = Path.cwd() / copy_path
    copy_path = copy_path.parent.resolve() / copy_path.name
    try:
        rel_copy = copy_path.relative_to(root).as_posix()
    except ValueError:
        raise StampRefused(f"{copy_arg} is outside the project root {root}") from None

    pair = next((item for item in registry.pairs if item.copy == rel_copy), None)
    if pair is None:
        source_pair = next((item for item in registry.pairs if item.source == rel_copy), None)
        hint = f"; stamp its copy {source_pair.copy}" if source_pair is not None else ""
        raise StampRefused(f"{rel_copy} is not a registered copy in {doc_lint.I18N_PAIRS_REGISTRY}{hint}")

    source_path = root / pair.source
    for role, rel_path, path in (("source", pair.source, source_path), ("copy", pair.copy, copy_path)):
        if path.is_symlink():
            raise StampRefused(f"{role} {rel_path} must be a regular file, not a symlink")
        if not path.is_file():
            raise StampRefused(f"{role} {rel_path} is missing")
    source_bytes = source_path.read_bytes()
    copy_bytes = copy_path.read_bytes()
    for rel_path, data in ((pair.source, source_bytes), (pair.copy, copy_bytes)):
        cr_line = doc_lint.i18n_first_cr_line(data)
        if cr_line is not None:
            raise StampRefused(f"{rel_path}:{cr_line} contains CR bytes; convert the file to LF line endings first")

    # A first line that starts like a stamp is replaced, even a malformed one;
    # otherwise the stamp is prepended.  The body bytes stay as they are.
    _state, _stamp, body = doc_lint.read_i18n_stamp(copy_bytes)
    pair_sha256, self_sha256 = doc_lint.i18n_pair_digests(source_bytes, body)
    stamp_line = doc_lint.format_i18n_stamp(pair.source, pair_sha256, self_sha256)
    stamped = stamp_line.encode("utf-8") + b"\n" + body
    if stamped == copy_bytes:
        return pair.copy, False
    copy_path.write_bytes(stamped)
    return pair.copy, True


def _cmd_stamp(root: Path, copy_arg: str) -> int:
    try:
        rel_copy, changed = stamp_copy(root, copy_arg)
    except StampRefused as exc:
        print(f"i18n-pairs: stamp refused: {exc}", file=sys.stderr)
        return 1
    print(f"{rel_copy}: {'stamped' if changed else 'stamp already current'}")
    return 0


def _cmd_check(root: Path, *, strict: bool) -> int:
    if doc_lint.load_i18n_pairs_registry(root) is None:
        print(f"i18n-pairs: OK (no {doc_lint.I18N_PAIRS_REGISTRY}; pair checks are off)")
        return 0
    errors, warnings = _print_findings(root, doc_lint.lint_i18n_pairs(root, strict=strict))
    if errors:
        print(f"i18n-pairs: FAIL ({errors} errors, {warnings} warnings)")
        return 1
    print(f"i18n-pairs: OK ({warnings} warnings)" if warnings else "i18n-pairs: OK")
    return 0


def _cmd_status(root: Path) -> int:
    report = doc_lint.inspect_i18n_pairs(root, strict=False)
    if report is None:
        print(f"{doc_lint.I18N_PAIRS_REGISTRY}: absent; pair checks are off")
        return 0
    print(f"{doc_lint.I18N_PAIRS_REGISTRY}: {len(report.pair_findings)} pairs")
    for pair, findings in report.pair_findings:
        if not findings:
            state = "ok"
        elif all(finding.severity == "WARN" for finding in findings):
            state = "stale"
        else:
            state = "error"
        print(f"{state:<6} {pair.source} -> {pair.copy}")
        for finding in findings:
            print(f"       {finding.severity}: {finding.message}")
    other_findings = [*report.registry.findings, *report.unregistered_findings]
    if other_findings:
        print("other findings:")
        _print_findings(root, other_findings)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Maintain the Russian copies `name.ru.md` of human documents registered in\n"
            f"{doc_lint.I18N_PAIRS_REGISTRY}. The pair rules are shared with doc_lint.py."
        ),
        epilog=(
            "Sync stamp: the first line of a copy, followed by LF:\n"
            f"  {doc_lint.I18N_STAMP_SHAPE}\n"
            "pair-sha256 covers every byte of the source; self-sha256 covers the copy\n"
            "without exactly that line and its LF. CR bytes are refused and nothing is\n"
            "normalized.\n"
            "\n"
            "Exit status: 0 success, 1 error findings or a refused stamp, 2 usage error."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--project-root",
        default="",
        help=f"Repository root that owns {doc_lint.I18N_PAIRS_REGISTRY} (default: the repository of this script).",
    )
    commands = parser.add_subparsers(dest="command", required=True, metavar="command")
    stamp = commands.add_parser(
        "stamp",
        help="Write or replace the sync stamp in the first line of a registered copy.",
        description=(
            "Compute the hashes of a registered pair and write the stamp as the first line of the copy. "
            "A first line that starts with '<!-- i18n:' is replaced; otherwise the stamp is prepended. "
            "Other bytes are kept. A copy that is not registered, or a pair with CR bytes, is refused."
        ),
    )
    stamp.add_argument("copy", help="Path of the registered *.ru.md copy, relative to the current directory or absolute.")
    check = commands.add_parser(
        "check",
        help="Report the translation-pair findings of doc_lint.py; exit 1 on errors.",
    )
    check.add_argument(
        "--strict",
        action="store_true",
        help="Treat a stale pair as an error, like doc_lint.py --i18n-strict.",
    )
    commands.add_parser("status", help="List the registered pairs and their state.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path(args.project_root).expanduser() if args.project_root else doc_lint.REPO_ROOT
    if not root.is_dir():
        print(f"i18n-pairs: project root is not a directory: {root}", file=sys.stderr)
        return 2
    root = root.resolve()
    if args.command == "stamp":
        return _cmd_stamp(root, args.copy)
    if args.command == "check":
        return _cmd_check(root, strict=args.strict)
    return _cmd_status(root)


if __name__ == "__main__":
    raise SystemExit(main())

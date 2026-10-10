#!/usr/bin/env python3
"""Scan a git diff range for lifecycle-aware SATD/blocker candidates."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


SATD_PATTERNS = re.compile(
    r"\b(TODO|FIXME|HACK|XXX|BUG|OPTIMIZE|DEBT|NOCOMMIT|WORKAROUND|TBD)\b"
    r"|(?:временно|потом\s+убра(?:ть|ем)|костыл(?:ь|и)?|заглушк\w*|техдолг)",
    re.IGNORECASE,
)
BLOCKER_KEYWORDS = re.compile(
    r"\b(broken|unsafe|insecure|race|deadlock|not implemented|placeholder|stub)\b"
    r"|(?:сломано|небезопасно|не\s+реализовано|заглушк\w*|временн\w+)",
    re.IGNORECASE,
)
TEST_PATH_RE = re.compile(r"(^|/)(tests?|__tests__|specs?)(/|$)|test_", re.IGNORECASE)
HUNK_RE = re.compile(
    r"@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))? "
    r"\+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@"
)


@dataclass(frozen=True)
class MatchedLine:
    file: str
    line: int
    keyword: str
    blocker_signal: bool
    test_context: bool
    snippet: str


@dataclass(frozen=True)
class Candidate:
    file: str
    line: int
    keyword: str
    blocker_signal: bool
    test_context: bool
    snippet: str
    lifecycle: str
    old_line: int | None
    new_line: int | None
    old_snippet: str
    new_snippet: str


def is_test_path(path: str | None) -> bool:
    return bool(path and TEST_PATH_RE.search(path))


def _match_line(path: str, line_number: int, line_text: str) -> MatchedLine | None:
    satd = SATD_PATTERNS.search(line_text)
    blocker = BLOCKER_KEYWORDS.search(line_text)
    if not satd and not blocker:
        return None
    return MatchedLine(
        file=path,
        line=line_number,
        keyword=satd.group(0) if satd else "",
        blocker_signal=bool(blocker),
        test_context=is_test_path(path),
        snippet=line_text.strip()[:160],
    )


def _build_candidate(removed: MatchedLine | None, added: MatchedLine | None) -> Candidate:
    base = added or removed
    assert base is not None
    lifecycle = "updated" if removed and added else "created" if added else "deleted"
    old_line = removed.line if removed else None
    new_line = added.line if added else None
    old_snippet = removed.snippet if removed else ""
    new_snippet = added.snippet if added else ""
    return Candidate(
        file=base.file,
        line=new_line if new_line is not None else old_line or 0,
        keyword=(added.keyword if added and added.keyword else "") or (removed.keyword if removed else ""),
        blocker_signal=bool((removed and removed.blocker_signal) or (added and added.blocker_signal)),
        test_context=base.test_context,
        snippet=new_snippet or old_snippet,
        lifecycle=lifecycle,
        old_line=old_line,
        new_line=new_line,
        old_snippet=old_snippet,
        new_snippet=new_snippet,
    )


def _flush_hunk(
    candidates: list[Candidate],
    removed_matches: list[MatchedLine],
    added_matches: list[MatchedLine],
) -> tuple[list[MatchedLine], list[MatchedLine]]:
    pair_count = min(len(removed_matches), len(added_matches))
    for index in range(pair_count):
        candidates.append(_build_candidate(removed_matches[index], added_matches[index]))
    for added in added_matches[pair_count:]:
        candidates.append(_build_candidate(None, added))
    for removed in removed_matches[pair_count:]:
        candidates.append(_build_candidate(removed, None))
    return [], []


def parse_diff_text(diff_text: str) -> list[Candidate]:
    candidates: list[Candidate] = []
    current_old_file: str | None = None
    current_new_file: str | None = None
    next_old_line = 0
    next_new_line = 0
    removed_matches: list[MatchedLine] = []
    added_matches: list[MatchedLine] = []

    for raw in diff_text.splitlines():
        if raw.startswith("diff --git "):
            removed_matches, added_matches = _flush_hunk(candidates, removed_matches, added_matches)
            current_old_file = None
            current_new_file = None
            continue
        if raw.startswith("--- "):
            current_old_file = None if raw == "--- /dev/null" else raw[6:] if raw.startswith("--- a/") else raw[4:]
            continue
        if raw.startswith("+++ "):
            current_new_file = None if raw == "+++ /dev/null" else raw[6:] if raw.startswith("+++ b/") else raw[4:]
            continue
        if raw.startswith("@@ "):
            match = HUNK_RE.match(raw)
            removed_matches, added_matches = _flush_hunk(candidates, removed_matches, added_matches)
            next_old_line = int(match.group("old_start")) if match else 0
            next_new_line = int(match.group("new_start")) if match else 0
            continue
        if raw.startswith("-") and not raw.startswith("---"):
            current_file = current_old_file or current_new_file
            if current_file:
                matched = _match_line(current_file, next_old_line, raw[1:])
                if matched:
                    removed_matches.append(matched)
            next_old_line += 1
            continue
        if raw.startswith("+") and not raw.startswith("+++"):
            current_file = current_new_file or current_old_file
            if current_file:
                matched = _match_line(current_file, next_new_line, raw[1:])
                if matched:
                    added_matches.append(matched)
            next_new_line += 1
            continue
        if raw.startswith(" "):
            next_old_line += 1
            next_new_line += 1

    removed_matches, added_matches = _flush_hunk(candidates, removed_matches, added_matches)
    return candidates


def scan_range(range_ref: str, repo_root: Path | None = None) -> list[Candidate]:
    root = (repo_root or Path.cwd()).resolve()
    proc = subprocess.run(
        ["git", "diff", range_ref, "-U0", "--diff-filter=AMD"],
        cwd=root,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"git diff {range_ref} failed")
    return parse_diff_text(proc.stdout)


def to_markdown_table(candidates: list[Candidate]) -> str:
    if not candidates:
        return "<!-- NO SATD CANDIDATES in range -->"

    rows = [
        "| lifecycle | old anchor | new anchor | keyword | blocker? | test? | snippet | review |",
        "|-----------|------------|------------|---------|----------|-------|---------|--------|",
    ]
    for item in candidates:
        old_anchor = f"`{item.file}:{item.old_line}`" if item.old_line is not None else ""
        new_anchor = f"`{item.file}:{item.new_line}`" if item.new_line is not None else ""
        blocker = "yes" if item.blocker_signal else ""
        test = "yes" if item.test_context else ""
        if item.lifecycle == "updated" and item.old_snippet and item.new_snippet:
            snippet = f"{item.old_snippet} -> {item.new_snippet}"
        else:
            snippet = item.new_snippet or item.old_snippet
        snippet = snippet.replace("|", "\\|")
        rows.append(
            f"| {item.lifecycle} | {old_anchor} | {new_anchor} | {item.keyword or ''} | {blocker} | {test} | {snippet} | UNCONFIRMED |"
        )
    return "\n".join(rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scan git diff for lifecycle-aware SATD/blocker candidates."
    )
    parser.add_argument(
        "--range",
        required=True,
        dest="range_ref",
        help="Git range to scan, for example BASE..HEAD.",
    )
    parser.add_argument(
        "--output",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format.",
    )
    parser.add_argument(
        "--project-root",
        default="",
        help="Repo root owning the git range (default: cwd).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path(args.project_root).expanduser().resolve() if args.project_root else Path.cwd()

    try:
        candidates = scan_range(args.range_ref, root)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.output == "json":
        print(json.dumps([asdict(item) for item in candidates], ensure_ascii=False, indent=2))
    else:
        print(to_markdown_table(candidates))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

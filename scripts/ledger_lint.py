#!/usr/bin/env python3
"""Lint explicitly selected historical ledger files for basic hygiene.

Checks (errors):
- No `**Status:** ...` lines (reserved for plan routing).
- No per-thread `Status:` lines (ledger must not store per-plan status).
- No per-thread `Next:` lines (ledger must not route per-plan).
- No duplicate level-2 headings (e.g. repeated "## Recent handoffs (Done)").

Checks (warnings):
- "git history" references (usually indicates stale pointers after docs hygiene).

This is intentionally lightweight and deterministic (no markdown parser).
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable, Sequence


# IMPORTANT:
# This standalone reader may be executed from another repository,
# so paths must be resolved relative to the current working directory (repo/worktree root),
# not relative to the tooling repo where this script lives.
REPO_ROOT = Path.cwd().resolve()
CONTINUITY_ROOT = REPO_ROOT / "docs" / "continuity"

DEFAULT_EXCLUDES = {
    CONTINUITY_ROOT / "README.md",
    CONTINUITY_ROOT / "index.md",
}

# Allow old plan headers that used Markdown blockquotes (`> **Status:** ...`).
STATUS_LINE_RE = re.compile(r"^\s*(?:>\s*)?\*\*Status:\*\*\s*(?P<status>.+?)\s*$")
INLINE_STATUS_RE = re.compile(r"^\s*-?\s*Status:\s+.+$", re.IGNORECASE)
# Disallow nested per-thread routing hints, but allow top-level `## Next:` heading.
INLINE_NEXT_RE = re.compile(r"^\s{2,}-\s*Next:\s+.+$", re.IGNORECASE)
INLINE_NEXT_PLAIN_RE = re.compile(r"^\s{2,}Next:\s+.+$", re.IGNORECASE)

H2_HEADING_RE = re.compile(r"^##\s+(?P<heading>.+?)\s*$")
GIT_HISTORY_RE = re.compile(r"\bgit history\b", re.IGNORECASE)


@dataclass(frozen=True)
class Finding:
    file: Path
    line: int
    severity: str  # "ERROR" | "WARN"
    message: str


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def iter_ledger_files(paths: Sequence[Path], *, missing_ok: Iterable[Path] = ()) -> list[Path]:
    resolved: set[Path] = set()
    missing_ok_resolved = {path.resolve() for path in missing_ok}
    for path in paths:
        candidate = path.resolve()
        if not candidate.exists() and candidate in missing_ok_resolved:
            continue
        if candidate.is_dir():
            for ledger in candidate.rglob("*.md"):
                if ledger.resolve() in DEFAULT_EXCLUDES:
                    continue
                resolved.add(ledger.resolve())
        else:
            if candidate in DEFAULT_EXCLUDES:
                continue
            resolved.add(candidate)
    return sorted(resolved)


def read_text(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def normalize_heading(text: str) -> str:
    # Case-insensitive, ignore trailing colon/spaces.
    cleaned = re.sub(r"[:\s]+$", "", text.strip())
    return cleaned.lower()


def lint_ledger(path: Path) -> list[Finding]:
    findings: list[Finding] = []
    lines = read_text(path)

    seen_h2: dict[str, int] = {}

    for idx, line in enumerate(lines, start=1):
        if STATUS_LINE_RE.match(line):
            findings.append(
                Finding(
                    path,
                    idx,
                    "ERROR",
                    "`**Status:**` is reserved for plans; remove it from role-ledger.",
                )
            )

        if INLINE_STATUS_RE.match(line):
            findings.append(
                Finding(
                    path,
                    idx,
                    "ERROR",
                    "`Status:` lines inside role-ledger are forbidden (ledger is not routing/state machine).",
                )
            )

        if INLINE_NEXT_RE.match(line) or INLINE_NEXT_PLAIN_RE.match(line):
            findings.append(
                Finding(
                    path,
                    idx,
                    "ERROR",
                    "`Next:` lines inside threads are forbidden (ledger is not routing). Use only top-level `## Next:`.",
                )
            )

        h2 = H2_HEADING_RE.match(line)
        if h2:
            key = normalize_heading(h2.group("heading"))
            if key in seen_h2:
                findings.append(
                    Finding(
                        path,
                        idx,
                        "ERROR",
                        f"Duplicate level-2 heading: '## {h2.group('heading')}'. Keep headings unique.",
                    )
                )
            else:
                seen_h2[key] = idx

        if GIT_HISTORY_RE.search(line):
            findings.append(
                Finding(
                    path,
                    idx,
                    "WARN",
                    "Contains 'git history' reference. Consider replacing with a stable doc pointer (review/audit/canon) or remove.",
                )
            )

    return findings


def print_findings(findings: Iterable[Finding]) -> None:
    for finding in findings:
        print(f"{finding.severity}: {rel(finding.file)}:{finding.line}: {finding.message}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Lint explicitly selected historical ledgers for hygiene.")
    parser.add_argument(
        "paths",
        nargs="+",
        help="Historical ledger file(s) or directories to read.",
    )
    args = parser.parse_args()

    ledger_files = iter_ledger_files([Path(arg) for arg in args.paths])
    if not ledger_files:
        print("WARN: no ledger files found.")
        return 0

    all_findings: list[Finding] = []
    for ledger in ledger_files:
        all_findings.extend(lint_ledger(ledger))

    print_findings(all_findings)
    has_errors = any(f.severity == "ERROR" for f in all_findings)
    return 1 if has_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

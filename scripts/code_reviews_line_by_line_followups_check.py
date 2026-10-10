#!/usr/bin/env python3
"""Verify that follow-ups from docs/code_reviews/*_line_by_line.md are imported into follow-ups masters.

Intent:
- We sometimes treat line-by-line code review docs as one-shot "source findings".
- Before deleting them, ensure Risk/Nit/Follow-up items are captured in `docs/followups/*_master.md`
  via `sources=["docs/code_reviews/<file>:<line>", ...]`.

Notes:
- Blocker items are ignored by default (they should be handled via plans/hotfixes, not follow-ups backlog).
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


# IMPORTANT:
# This tool is executed from other repos via shell wrappers (`source scripts/planveyor.zsh`),
# so paths must be resolved relative to the current working directory (repo/worktree root),
# not relative to the tooling repo where this script lives.
REPO_ROOT = Path.cwd().resolve()
DEFAULT_GLOB = "docs/code_reviews/*_line_by_line.md"

FOLLOWUPS_DIR = REPO_ROOT / "docs" / "followups"
MASTER_GLOB = "docs/followups/*_followups_master.md"

# Sections in review doc.
REVIEW_ITEM_RE = re.compile(r"^\s*(?P<num>[0-9]+)\)\s+\*\*(?P<title>.+?)\*\*\s*$")

# Follow-ups backlog lines.
FOLLOWUPS_BACKLOG_RE = re.compile(r"^\s*\*\*Follow-ups backlog:\*\*\s+(?P<rest>.+?)\s*$")

# Follow-up items in master files.
ITEM_RE = re.compile(r"^\s*-\s*(?P<prio>P[0-9?])\s+\[(?P<mark>[ xX])\]\s+(?P<body>.+?)\s*$")
SECTION_H2_RE = re.compile(r"^\s*##\s+")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _normalize_scalar(value: str) -> str:
    v = value.strip().strip("`").strip().strip("'").strip('"').strip()
    v = v.replace("\u00a0", " ")
    return v


def _split_tokens(body: str) -> tuple[str, list[str]]:
    if " — " in body:
        parts = [p.strip() for p in body.split(" — ")]
    elif " - " in body:
        parts = [p.strip() for p in body.split(" - ")]
    else:
        parts = [body.strip()]
    summary = parts[0] if parts else body.strip()
    tokens = parts[1:] if len(parts) > 1 else []
    return summary, tokens


def _token_key(token: str) -> str | None:
    t = token.strip()
    if not t:
        return None
    if t.lower().startswith("why:"):
        return "why"
    if "=" in t:
        key = t.split("=", 1)[0].strip().lower()
        if re.fullmatch(r"[a-z_][a-z0-9_]*", key):
            return key
    return None


def _extract_field(body: str, key: str) -> str | None:
    _, tokens = _split_tokens(body)
    want = key.lower()
    for token in tokens:
        tkey = _token_key(token)
        if tkey != want:
            continue
        if want == "why":
            return token.split(":", 1)[1].strip() if ":" in token else ""
        if "=" in token:
            return token.split("=", 1)[1].strip()
    return None


def _parse_sources(value: str | None) -> list[str]:
    if value is None:
        return []
    raw = value.strip()
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    out: list[str] = []
    for part in raw.split(","):
        v = _normalize_scalar(part)
        if v:
            out.append(v)
    return out


@dataclass(frozen=True)
class ReviewItem:
    review_path: str  # rel path
    section: str  # blocker|risk|nit|followup
    num: int
    title: str
    line_no: int

    @property
    def source_ref(self) -> str:
        return f"{self.review_path}:{self.line_no}"


def _parse_review_items(path: Path, *, include_blockers: bool) -> tuple[str | None, list[ReviewItem]]:
    rel = path.relative_to(REPO_ROOT).as_posix()
    lines = _read_text(path).splitlines()

    backlog_line: str | None = None
    for line in lines[:60]:
        m = FOLLOWUPS_BACKLOG_RE.match(line.strip())
        if m:
            backlog_line = m.group("rest").strip()
            break

    items: list[ReviewItem] = []
    section: str | None = None
    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("## "):
            title = stripped[3:].strip().lower()
            if title.startswith("risk"):
                section = "risk"
            elif title.startswith("nit"):
                section = "nit"
            elif title.startswith("follow-up"):
                section = "followup"
            elif title.startswith("blocker"):
                section = "blocker" if include_blockers else None
            else:
                section = None
            continue

        if not section:
            continue
        m = REVIEW_ITEM_RE.match(line)
        if not m:
            continue
        items.append(
            ReviewItem(
                review_path=rel,
                section=section,
                num=int(m.group("num")),
                title=m.group("title").strip(),
                line_no=i,
            )
        )

    return backlog_line, items


def _collect_master_sources() -> set[str]:
    sources: set[str] = set()
    for master_path in sorted(REPO_ROOT.glob(MASTER_GLOB)):
        lines = _read_text(master_path).splitlines()
        in_followups = False
        for line in lines:
            stripped = line.strip()
            if stripped.lower().startswith("## follow-ups"):
                in_followups = True
                continue
            if in_followups and SECTION_H2_RE.match(line):
                break
            if not in_followups:
                continue
            m = ITEM_RE.match(line)
            if not m:
                continue
            body = m.group("body").strip()
            sources.update(_parse_sources(_extract_field(body, "sources")))
    return sources


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Check that line-by-line code review findings are imported into follow-ups masters.")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--all", action="store_true", help="Scan default pattern docs/code_reviews/*_line_by_line.md")
    src.add_argument("--src", action="append", default=[], help="Path to one review file (repeatable)")
    p.add_argument("--include-blockers", action="store_true", help="Also require Blocker items to be present in follow-ups sources (default: ignore)")
    return p


def main(argv: list[str]) -> int:
    args = _build_arg_parser().parse_args(argv)
    if args.all:
        sources = sorted(REPO_ROOT.glob(DEFAULT_GLOB))
    else:
        sources = [REPO_ROOT / p for p in args.src]

    missing_files = [p.as_posix() for p in sources if not p.exists()]
    if missing_files:
        print("ERROR: missing review files:", file=sys.stderr)
        for p in missing_files:
            print(f"- {p}", file=sys.stderr)
        return 2

    master_sources = _collect_master_sources()

    total = 0
    total_missing = 0
    per_file_missing: dict[str, list[ReviewItem]] = {}

    for review_path in sources:
        backlog_line, items = _parse_review_items(review_path, include_blockers=args.include_blockers)
        rel = review_path.relative_to(REPO_ROOT).as_posix()
        print(f"\n== {rel} ==")
        if backlog_line:
            print(f"followups_backlog: {backlog_line}")
        else:
            print("followups_backlog: (not found)")

        missing: list[ReviewItem] = []
        for it in items:
            total += 1
            if it.source_ref not in master_sources:
                missing.append(it)
        if missing:
            per_file_missing[rel] = missing
            total_missing += len(missing)
            print(f"missing_items={len(missing)}/{len(items)}")
            for it in missing:
                print(f"- {it.section}#{it.num} at {it.source_ref}: {it.title}")
        else:
            print(f"missing_items=0/{len(items)}")

    print("\nsummary:")
    print(f"- review_files={len(sources)}")
    print(f"- items_total={total}")
    print(f"- items_missing={total_missing}")

    return 1 if total_missing > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

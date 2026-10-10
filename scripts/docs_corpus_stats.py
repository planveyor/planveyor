#!/usr/bin/env python3
"""
Lightweight corpus stats for `docs/**` to support A0.1 (pre-index sizing).

Goal: get a stable, reproducible estimate of corpus size without external APIs.
This intentionally uses a rough token heuristic (chars/4) to avoid extra deps.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_EXCLUDE_PREFIXES = (
    "docs/snapshots/",
    "docs/reviews/",
    "docs/code_reviews/",
    "docs/doc_reviews/",
    "docs/followups/",
)


def estimate_tokens_chars4(text: str) -> int:
    # Very rough: ~4 chars/token heuristic.
    return max(1, len(text) // 4)


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


@dataclass(frozen=True)
class CorpusFileStats:
    path: str
    chars: int
    tokens_est: int
    headings_total: int


@dataclass(frozen=True)
class CorpusStats:
    root: str
    include_plans: bool
    exclude_prefixes: tuple[str, ...]
    files_total: int
    chars_total: int
    tokens_est_total: int
    headings_total: int
    chunk_target_tokens: int
    chunks_est: int
    top_files_by_tokens: list[CorpusFileStats]


def should_exclude(rel_path: str, exclude_prefixes: Iterable[str], include_plans: bool) -> bool:
    if not include_plans and rel_path.startswith("docs/plans/"):
        return True
    return any(rel_path.startswith(prefix) for prefix in exclude_prefixes)


def build_stats(
    root: Path,
    *,
    exclude_prefixes: tuple[str, ...],
    include_plans: bool,
    chunk_target_tokens: int,
    top_n: int,
) -> CorpusStats:
    if chunk_target_tokens <= 0:
        raise ValueError("chunk_target_tokens must be > 0")
    if top_n <= 0:
        raise ValueError("top_n must be > 0")

    file_stats: list[CorpusFileStats] = []
    chars_total = 0
    tokens_total = 0
    headings_total = 0

    for path in sorted(root.rglob("*.md")):
        rel_path = path.as_posix()
        if should_exclude(rel_path, exclude_prefixes, include_plans):
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # Ignore non-utf8 docs (should not happen, but keep tool robust).
            continue

        chars = len(text)
        tokens_est = estimate_tokens_chars4(text)
        headings = len(HEADING_RE.findall(text))

        chars_total += chars
        tokens_total += tokens_est
        headings_total += headings
        file_stats.append(
            CorpusFileStats(
                path=rel_path,
                chars=chars,
                tokens_est=tokens_est,
                headings_total=headings,
            )
        )

    chunks_est = int(math.ceil(tokens_total / chunk_target_tokens)) if tokens_total else 0
    top_files_by_tokens = sorted(file_stats, key=lambda s: s.tokens_est, reverse=True)[:top_n]

    return CorpusStats(
        root=root.as_posix(),
        include_plans=include_plans,
        exclude_prefixes=exclude_prefixes,
        files_total=len(file_stats),
        chars_total=chars_total,
        tokens_est_total=tokens_total,
        headings_total=headings_total,
        chunk_target_tokens=chunk_target_tokens,
        chunks_est=chunks_est,
        top_files_by_tokens=top_files_by_tokens,
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Compute lightweight stats for docs corpus (pre-index sizing).")
    parser.add_argument("--root", default="docs", help="Root directory to scan (default: docs)")
    parser.add_argument(
        "--exclude-prefix",
        action="append",
        default=list(DEFAULT_EXCLUDE_PREFIXES),
        help="Exclude path prefix (repeatable). Default excludes snapshots/reviews/code_reviews/doc_reviews/followups.",
    )
    parser.add_argument(
        "--include-plans",
        action="store_true",
        help="Include docs/plans/** in the corpus (default: excluded).",
    )
    parser.add_argument(
        "--chunk-target-tokens",
        type=int,
        default=900,
        help="Token target per chunk (for rough chunk-count estimate). Default: 900.",
    )
    parser.add_argument("--top", type=int, default=15, help="Show top N largest docs by tokens (default: 15).")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of human-readable text.")

    args = parser.parse_args(argv)

    root = Path(args.root)
    if not root.exists() or not root.is_dir():
        print(f"ERROR: root not found or not a directory: {root}", file=sys.stderr)
        return 2

    stats = build_stats(
        root,
        exclude_prefixes=tuple(args.exclude_prefix),
        include_plans=bool(args.include_plans),
        chunk_target_tokens=int(args.chunk_target_tokens),
        top_n=int(args.top),
    )

    if args.json:
        payload = asdict(stats)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print("docs_corpus_stats")
    print(f"- root: {stats.root}")
    print(f"- include_plans: {stats.include_plans}")
    print(f"- excluded prefixes: {', '.join(stats.exclude_prefixes)}")
    print(f"- files: {stats.files_total}")
    print(f"- chars: {stats.chars_total}")
    print(f"- tokens_est (~chars/4): {stats.tokens_est_total}")
    print(f"- headings_total: {stats.headings_total}")
    print(f"- chunk_target_tokens: {stats.chunk_target_tokens}")
    print(f"- chunks_est: {stats.chunks_est}")
    print()
    print(f"top_files_by_tokens (top {len(stats.top_files_by_tokens)}):")
    for row in stats.top_files_by_tokens:
        print(f"- {row.tokens_est:>7} tok  {row.headings_total:>4} headings  {row.chars:>8} chars  {row.path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

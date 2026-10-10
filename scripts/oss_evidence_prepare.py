#!/usr/bin/env python3
from __future__ import annotations

"""Prepare structural OSS evidence inventory, staging, and manifest files."""

import argparse
import csv
from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
from typing import Iterable


DEFAULT_MIN_COUNT = 30
DEFAULT_MAX_COUNT = 50

ALLOWED_CATEGORIES = (
    "plans",
    "code_drafts",
    "code_reviews",
    "doc_reviews",
    "followups",
    "canon_notes",
)

CORPUS_DIRS: tuple[tuple[str, str], ...] = (
    ("docs/plans", "plans"),
    ("docs/code_drafts", "code_drafts"),
    ("docs/code_reviews", "code_reviews"),
    ("docs/doc_reviews", "doc_reviews"),
    ("docs/reviews", "doc_reviews"),
    ("docs/followups", "followups"),
    ("docs/process_improvements", "canon_notes"),
    ("docs/_meta", "canon_notes"),
    ("docs/tools", "canon_notes"),
    ("docs/playbooks", "canon_notes"),
    ("docs/guides", "canon_notes"),
    ("docs/adr", "canon_notes"),
)

SKIP_DIRS = {
    "docs/reviews/sources",
}

INVENTORY_HEADER = ("source_path", "category", "title", "status", "bytes", "words")
SCORE_TEMPLATE_HEADER = (
    "source_path",
    "category",
    "suggested_public_filename",
    "why_included",
    "mechanism_score",
    "outcome_score",
    "cleanup_cost_score",
    "diversity_score",
    "linkage_score",
    "external_usefulness_score",
    "total_score",
    "operator_notes",
)


@dataclass(frozen=True)
class Candidate:
    source_path: str
    category: str
    title: str
    status: str
    bytes: int
    words: int


@dataclass(frozen=True)
class SelectedEvidence:
    source_path: str
    category: str
    public_filename: str
    why_included: str

    @property
    def public_path(self) -> str:
        return f"docs/evidence/{self.category}/{self.public_filename}"


def relpath(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def is_under(rel: str, parent: str) -> bool:
    return rel == parent or rel.startswith(f"{parent}/")


def category_for_path(rel: str) -> str | None:
    for parent, category in CORPUS_DIRS:
        if is_under(rel, parent):
            return category
    return None


def is_skipped(rel: str) -> bool:
    return any(is_under(rel, parent) for parent in SKIP_DIRS)


def read_text_lossy(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def extract_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip() or fallback
    return fallback


def extract_status(text: str) -> str:
    match = re.search(r"^\*\*Status:\*\*\s*(.+)$", text, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def iter_candidates(root: Path) -> Iterable[Candidate]:
    for parent, category in CORPUS_DIRS:
        base = root / parent
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.md")):
            if not path.is_file():
                continue
            rel = relpath(path, root)
            if is_skipped(rel):
                continue
            text = read_text_lossy(path)
            yield Candidate(
                source_path=rel,
                category=category,
                title=extract_title(text, path.stem),
                status=extract_status(text),
                bytes=path.stat().st_size,
                words=len(re.findall(r"\S+", text)),
            )


def ensure_root(path_value: str) -> Path:
    root = Path(path_value).resolve()
    if not root.is_dir():
        raise ValueError(f"root is not a directory: {root}")
    return root


def resolve_under_root(root: Path, path_value: str, *, label: str) -> Path:
    path = Path(path_value)
    resolved = (path if path.is_absolute() else root / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} must stay under repository root: {path_value}") from exc
    return resolved


def open_tsv_writer(path: Path) -> tuple[object, csv.writer]:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("w", encoding="utf-8", newline="")
    return handle, csv.writer(handle, delimiter="\t", lineterminator="\n")


def command_inventory(args: argparse.Namespace) -> int:
    root = ensure_root(args.root)
    out_path = resolve_under_root(root, args.out, label="--out")
    handle, writer = open_tsv_writer(out_path)
    with handle:
        writer.writerow(INVENTORY_HEADER)
        for candidate in iter_candidates(root):
            writer.writerow(
                [
                    candidate.source_path,
                    candidate.category,
                    candidate.title,
                    candidate.status,
                    candidate.bytes,
                    candidate.words,
                ]
            )
    print(f"inventory wrote {out_path}")
    return 0


def read_inventory(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames != list(INVENTORY_HEADER):
            raise ValueError(f"inventory header mismatch in {path}")
        return list(reader)


def suggested_filename(source_path: str) -> str:
    name = Path(source_path).name
    return name if name.endswith(".md") else f"{Path(name).stem}.md"


def command_score_template(args: argparse.Namespace) -> int:
    root = ensure_root(args.root)
    inventory_path = resolve_under_root(root, args.inventory, label="--inventory")
    out_path = resolve_under_root(root, args.out, label="--out")
    rows = read_inventory(inventory_path)
    handle, writer = open_tsv_writer(out_path)
    with handle:
        writer.writerow(SCORE_TEMPLATE_HEADER)
        for row in rows:
            writer.writerow(
                [
                    row["source_path"],
                    row["category"],
                    suggested_filename(row["source_path"]),
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                ]
            )
    print(f"score-template wrote {out_path}")
    return 0


def validate_source_path(root: Path, source_path: str) -> Path:
    if "\\" in source_path:
        raise ValueError(f"source_path must use POSIX separators: {source_path}")
    pure = PurePosixPath(source_path)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError(f"unsafe source_path: {source_path}")
    category = category_for_path(source_path)
    if category is None:
        raise ValueError(f"source_path is outside configured corpus: {source_path}")
    if is_skipped(source_path):
        raise ValueError(f"source_path is excluded from public evidence corpus: {source_path}")
    if pure.suffix.lower() != ".md":
        raise ValueError(f"source_path must be markdown: {source_path}")
    resolved = (root / source_path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"source_path escapes repository root: {source_path}") from exc
    if not resolved.is_file():
        raise ValueError(f"source_path does not exist: {source_path}")
    return resolved


def validate_public_filename(public_filename: str) -> None:
    if "\\" in public_filename or "/" in public_filename:
        raise ValueError(f"public_filename must be filename-only: {public_filename}")
    pure = PurePosixPath(public_filename)
    if pure.name != public_filename or pure.is_absolute():
        raise ValueError(f"public_filename must be filename-only: {public_filename}")
    if public_filename in {"", ".", ".."} or ".." in pure.parts or public_filename.startswith("."):
        raise ValueError(f"unsafe public_filename: {public_filename}")
    if pure.suffix.lower() != ".md" or not pure.stem:
        raise ValueError(f"public_filename must be a markdown filename: {public_filename}")


def read_selected(root: Path, selected_path: Path, *, min_count: int, max_count: int) -> list[SelectedEvidence]:
    rows: list[SelectedEvidence] = []
    with selected_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        for line_no, fields in enumerate(reader, start=1):
            if not fields or all(not field.strip() for field in fields):
                continue
            if len(fields) != 4:
                raise ValueError(f"{selected_path}:{line_no}: expected 4 TSV fields")
            source_path, category, public_filename, why_included = [field.strip() for field in fields]
            if category not in ALLOWED_CATEGORIES:
                raise ValueError(f"{selected_path}:{line_no}: unknown category: {category}")
            expected_category = category_for_path(source_path)
            if expected_category != category:
                raise ValueError(
                    f"{selected_path}:{line_no}: category mismatch for {source_path}: "
                    f"expected {expected_category}, got {category}"
                )
            if not why_included:
                raise ValueError(f"{selected_path}:{line_no}: why_included is required")
            validate_source_path(root, source_path)
            validate_public_filename(public_filename)
            rows.append(SelectedEvidence(source_path, category, public_filename, why_included))
    if not (min_count <= len(rows) <= max_count):
        raise ValueError(f"selected row count {len(rows)} is outside required range {min_count}-{max_count}")
    seen_public_paths: set[str] = set()
    for row in rows:
        if row.public_path in seen_public_paths:
            raise ValueError(f"duplicate public path: {row.public_path}")
        seen_public_paths.add(row.public_path)
    return rows


def command_validate_selected(args: argparse.Namespace) -> int:
    root = ensure_root(args.root)
    selected_path = resolve_under_root(root, args.selected, label="--selected")
    rows = read_selected(root, selected_path, min_count=args.min_count, max_count=args.max_count)
    print(f"validate-selected OK: {len(rows)} row(s)")
    return 0


def command_copy_selected(args: argparse.Namespace) -> int:
    root = ensure_root(args.root)
    selected_path = resolve_under_root(root, args.selected, label="--selected")
    dest_root = resolve_under_root(root, args.dest, label="--dest")
    rows = read_selected(root, selected_path, min_count=args.min_count, max_count=args.max_count)
    copied = 0
    for row in rows:
        source = validate_source_path(root, row.source_path)
        target = (dest_root / row.category / row.public_filename).resolve()
        try:
            target.relative_to(dest_root)
        except ValueError as exc:
            raise ValueError(f"copy target escapes destination: {target}") from exc
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied += 1
    print(f"copy-selected copied {copied} file(s) into {dest_root}")
    return 0


def command_manifest(args: argparse.Namespace) -> int:
    root = ensure_root(args.root)
    selected_path = resolve_under_root(root, args.selected, label="--selected")
    out_path = resolve_under_root(root, args.out, label="--out")
    rows = read_selected(root, selected_path, min_count=args.min_count, max_count=args.max_count)
    payload = {
        "schema_version": "oss-evidence-manifest.v1",
        "items": [
            {
                "public_path": row.public_path,
                "category": row.category,
                "why_included": row.why_included,
                "sanitization_status": "pending",
            }
            for row in rows
        ],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"manifest wrote {out_path}")
    return 0


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", default=".", help="Repository root. Defaults to current working directory.")


def add_selected_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--selected", required=True, help="Selected evidence TSV.")
    parser.add_argument("--min-count", type=int, default=DEFAULT_MIN_COUNT)
    parser.add_argument("--max-count", type=int, default=DEFAULT_MAX_COUNT)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    inventory = subparsers.add_parser("inventory", help="Write candidate evidence inventory TSV.")
    add_common(inventory)
    inventory.add_argument("--out", required=True)
    inventory.set_defaults(func=command_inventory)

    score = subparsers.add_parser("score-template", help="Write an operator-fillable score template TSV.")
    add_common(score)
    score.add_argument("--inventory", required=True)
    score.add_argument("--out", required=True)
    score.set_defaults(func=command_score_template)

    validate = subparsers.add_parser("validate-selected", help="Validate selected evidence TSV.")
    add_common(validate)
    add_selected_args(validate)
    validate.set_defaults(func=command_validate_selected)

    copy = subparsers.add_parser("copy-selected", help="Copy selected files into a staging directory.")
    add_common(copy)
    add_selected_args(copy)
    copy.add_argument("--dest", required=True)
    copy.set_defaults(func=command_copy_selected)

    manifest = subparsers.add_parser("manifest", help="Write public evidence manifest JSON.")
    add_common(manifest)
    add_selected_args(manifest)
    manifest.add_argument("--out", required=True)
    manifest.set_defaults(func=command_manifest)

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(sys.argv[1:] if argv is None else argv))
    try:
        return args.func(args)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

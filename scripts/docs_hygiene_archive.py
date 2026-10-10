#!/usr/bin/env python3
"""
Archive temp docs (terminal plans/reviews/drafts) slated for deletion by docs hygiene.

This is a helper for the post-merge hygiene workflow:
- compute the same deletion candidates as `scripts/docs_hygiene_suggest.py`
- archive the markdown artifacts into a local SQLite FTS DB (gitignored)
- print the same `git rm -r ...` suggestion for Owner to run
"""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path

import docs_archive
import docs_hygiene_suggest
from portability_substitution import (
    PortabilityPolicyError,
    load_portability_rules,
    portabilize_text,
)


DEFAULT_DB = ".tmp/planveyor_docs_archive.sqlite"


def _rel_exists(rel_path: str) -> bool:
    p = docs_hygiene_suggest.REPO_ROOT / rel_path
    return p.exists()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Archive docs hygiene candidates (local SQLite FTS) and print git-rm suggestion."
    )
    parser.add_argument("--range", required=True, help="Git range, e.g. BASE..HEAD")
    parser.add_argument(
        "--db",
        default=DEFAULT_DB,
        help=f"Archive SQLite DB path (default: {DEFAULT_DB})",
    )
    parser.add_argument(
        "--content-profile-id",
        default="default",
        choices=("default", "planveyor", "target-local"),
        help="Public content profile; normalization uses generic interpreter rules.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write to the archive DB (default: dry-run; only prints what would be archived).",
    )
    parser.add_argument(
        "--include-followups",
        action="store_true",
        help="Include Done followups in the suggested git rm command (default: list separately).",
    )
    parser.add_argument(
        "--include-snapshots",
        action="store_true",
        help="Include docs/snapshots/* referenced by terminal plans (default: never delete snapshots).",
    )
    parser.add_argument(
        "--dirs",
        nargs="*",
        default=docs_hygiene_suggest.DEFAULT_GIT_DIRS,
        help="Docs roots to scan in git diff (advanced).",
    )
    args = parser.parse_args(argv)
    try:
        portability_rules = load_portability_rules(content_profile_id=args.content_profile_id)
    except PortabilityPolicyError as e:
        print(f"ERROR: portability policy invalid: {e}", file=sys.stderr)
        return 2

    range_ref: str = str(args.range).strip()
    touched = docs_hygiene_suggest._git_touched_docs(range_ref, args.dirs)
    state = docs_hygiene_suggest._compute_state(
        touched=touched,
        include_snapshots=bool(args.include_snapshots),
        include_followups=bool(args.include_followups),
    )

    terminal_plans: list[str] = state["terminal_plans"]  # type: ignore[assignment]
    rm_items: list[str] = state["rm_items"]  # type: ignore[assignment]
    delete_dirs: list[str] = state["delete_dirs"]  # type: ignore[assignment]

    archive_candidates = sorted(
        {
            p
            for p in (terminal_plans + rm_items)
            if p.endswith(".md") and _rel_exists(p)
        }
    )

    print(f"[planveyor] Range: {range_ref}")
    print(f"[planveyor] Archive DB: {args.db}")
    db_path = Path(str(args.db))
    if db_path.exists():
        conn = docs_archive.sqlite3.connect(docs_archive._sqlite_uri_readonly(db_path), uri=True)
        try:
            conn.execute("PRAGMA query_only = ON")
            summary = docs_archive.archive_db_summary(
                conn,
                db_path=db_path,
                portability_rules=portability_rules,
            )
        finally:
            conn.close()
        print(
            "[planveyor] Archive DB facts: "
            f"docs={summary['docs_count']} "
            f"kinds={json.dumps(summary['kind_counts'], ensure_ascii=False, sort_keys=True)} "
            f"size_bytes={summary['db_size_bytes']} "
            f"range={summary['archived_at_min_utc']}..{summary['archived_at_max_utc']}"
        )
    print("")

    if not archive_candidates:
        print("[planveyor] Archive candidates: none")
    else:
        print(f"[planveyor] Archive candidates ({len(archive_candidates)}):")
        for p in archive_candidates:
            print(f"  - {p}")
    print("")

    if archive_candidates:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        if bool(args.apply):
            extra = {"source": "docs_hygiene_archive", "range": range_ref}
            extra_json = json.dumps(extra, ensure_ascii=False, sort_keys=True)
            # Use the library function directly to keep it fast and deterministic.
            conn = docs_archive.sqlite3.connect(db_path.as_posix())
            try:
                conn.execute("PRAGMA foreign_keys = ON")
                conn.execute("PRAGMA journal_mode = WAL")
                docs_archive.sqlite_fts5_self_check(conn)
                docs_archive.ensure_schema(conn)
                stats = docs_archive.archive_markdown_paths(
                    conn,
                    archive_candidates,
                    # Portabilize db_label so archived records carry a portable
                    # path in extra_json.db (mirrors the docs_archive ingest
                    # command path; closes the same owner-local leak vector).
                    db_label=portabilize_text(db_path.as_posix(), rules=portability_rules),
                    chunk_target_tokens=docs_archive.DEFAULT_CHUNK_TARGET_TOKENS,
                    extra_meta=json.loads(extra_json),
                    dry_run=False,
                    portability_rules=portability_rules,
                )
                conn.commit()
            finally:
                conn.close()

            print("[planveyor] Archive result:")
            print(f"  - inserted: {stats.inserted}")
            print(f"  - skipped_existing: {stats.skipped_existing}")
            print(f"  - missing_on_disk: {stats.missing}")
            print("")
        else:
            print("[planveyor] Archive mode: dry-run (pass --apply to write to DB)")
            print("")

    print("[planveyor] Suggested (Owner) command:")
    if not rm_items and not delete_dirs:
        print("  # nothing to remove (or nothing detected as safe)")
        return 0

    print("  git rm -r \\")
    for p in rm_items:
        print(f"    {p} \\")
    for d in delete_dirs:
        print(f"    {d} \\")
    print("  # (copy, then remove trailing backslash on the last line)")
    print("")

    print("[planveyor] Tip:")
    if bool(args.apply):
        print("  # Search in the archive DB")
        print(f"  python3 scripts/docs_archive.py --db {shlex.quote(str(args.db))} query --k 12 \"<query>\"")
        print(f"  python3 scripts/docs_archive.py --db {shlex.quote(str(args.db))} show --id <doc_id>")
    else:
        print("  # Archive first, then delete")
        print(f"  python3 scripts/docs_hygiene_archive.py --range {shlex.quote(range_ref)} --apply")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

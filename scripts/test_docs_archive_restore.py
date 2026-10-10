#!/usr/bin/env python3
from __future__ import annotations

import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import docs_archive
from scripts.test_contract_authority_support import AuthorityFixture, commit_all, git, write


DOCS_ARCHIVE = REPO_ROOT / "scripts/docs_archive.py"


def _run_docs_archive(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(DOCS_ARCHIVE), *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _write_archive_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path.as_posix())
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        docs_archive.sqlite_fts5_self_check(conn)
        docs_archive.ensure_schema(conn)
        records = [
            {
                "kind": "plan",
                "original_path": "docs/plans/260101_1200_fresh_clone_restore_plan.md",
                "sha256": docs_archive._sha256_hex(
                    "# Restore Plan\n\nfresh clone restore proof through archive query\n"
                ),
                "archived_at_utc": "2026-05-17T00:00:00Z",
                "title": "Restore Plan",
                "extra_json": "{}",
                "content": "# Restore Plan\n\nfresh clone restore proof through archive query\n",
            },
            {
                "kind": "code_review",
                "original_path": "docs/code_reviews/260101_1200_fresh_clone_restore_plan.md",
                "sha256": docs_archive._sha256_hex(
                    "# Restore Review\n\nsnapshot checksum readback stays searchable\n"
                ),
                "archived_at_utc": "2026-05-17T00:01:00Z",
                "title": "Restore Review",
                "extra_json": "{}",
                "content": "# Restore Review\n\nsnapshot checksum readback stays searchable\n",
            },
        ]
        for record in records:
            inserted = docs_archive._insert_archived_doc_record(
                conn,
                record,
                chunk_target_tokens=docs_archive.DEFAULT_CHUNK_TARGET_TOKENS,
            )
            assert inserted
        conn.commit()
    finally:
        conn.close()


class DocsArchiveFreshCloneRestoreTests(unittest.TestCase):
    def test_git_text_snapshot_restores_archive_query_without_original_tmp(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            source_repo = tmp / "source_repo"
            fresh_clone = tmp / "fresh_clone"
            source_db = source_repo / ".tmp/planveyor_docs_archive.sqlite"
            source_snapshot_dir = source_repo / "docs/_meta/archive_snapshots/current"
            fresh_snapshot_dir = fresh_clone / "docs/_meta/archive_snapshots/current"
            restored_db = fresh_clone / ".tmp/planveyor_docs_archive.sqlite"
            _write_archive_db(source_db)

            export = _run_docs_archive(
                "--db",
                source_db.as_posix(),
                "snapshot-export",
                "--backend",
                "git_text_export",
                "--output-dir",
                source_snapshot_dir.as_posix(),
                "--force",
                "--created-at-utc",
                "2026-05-17T00:02:00Z",
            )
            self.assertEqual(export.returncode, 0, export.stderr)
            shutil.copytree(source_snapshot_dir, fresh_snapshot_dir)
            shutil.rmtree(source_repo / ".tmp")

            restore = _run_docs_archive(
                "snapshot-restore",
                "--manifest",
                (fresh_snapshot_dir / "manifest.json").as_posix(),
                "--dest-db",
                restored_db.as_posix(),
                "--replace",
                "--query",
                "fresh clone restore proof",
                "--expect-min-hits",
                "1",
            )
            self.assertEqual(restore.returncode, 0, restore.stderr)
            self.assertIn("result: OK", restore.stdout)
            self.assertTrue(restored_db.exists())
            self.assertFalse(source_db.exists())

            query = _run_docs_archive(
                "--db",
                restored_db.as_posix(),
                "query",
                "--profile",
                "signal",
                "--k",
                "5",
                "fresh clone restore proof",
            )
            self.assertEqual(query.returncode, 0, query.stderr)
            self.assertIn("docs/plans/260101_1200_fresh_clone_restore_plan.md", query.stdout)

            show = _run_docs_archive(
                "--db",
                restored_db.as_posix(),
                "show",
                "--path",
                "docs/plans/260101_1200_fresh_clone_restore_plan.md",
            )
            self.assertEqual(show.returncode, 0, show.stderr)
            self.assertIn("fresh clone restore proof through archive query", show.stdout)

    def test_s3_minio_manifest_restore_fails_closed_without_object_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            source_db = tmp / "object.sqlite"
            manifest_dir = tmp / "s3_manifest"
            restored_db = tmp / "restored.sqlite"
            _write_archive_db(source_db)
            object_sha = docs_archive._sha256_file(source_db)
            object_size = source_db.stat().st_size

            export = _run_docs_archive(
                "--db",
                source_db.as_posix(),
                "snapshot-export",
                "--backend",
                "s3_minio_sqlite",
                "--output-dir",
                manifest_dir.as_posix(),
                "--force",
                "--object-uri",
                "s3://archive-snapshots/planveyor/current.sqlite",
                "--object-sha256",
                object_sha,
                "--object-size-bytes",
                str(object_size),
                "--created-at-utc",
                "2026-05-17T00:03:00Z",
            )
            self.assertEqual(export.returncode, 0, export.stderr)

            missing_object = _run_docs_archive(
                "snapshot-restore",
                "--manifest",
                (manifest_dir / "manifest.json").as_posix(),
                "--dest-db",
                restored_db.as_posix(),
                "--replace",
                "--query",
                "fresh clone restore proof",
                "--expect-min-hits",
                "1",
            )
            self.assertEqual(missing_object.returncode, 2)
            self.assertIn("failing closed", missing_object.stderr)

            restore = _run_docs_archive(
                "snapshot-restore",
                "--manifest",
                (manifest_dir / "manifest.json").as_posix(),
                "--dest-db",
                restored_db.as_posix(),
                "--replace",
                "--object-file",
                source_db.as_posix(),
                "--query",
                "fresh clone restore proof",
                "--expect-min-hits",
                "1",
            )
            self.assertEqual(restore.returncode, 0, restore.stderr)
            self.assertIn("backend: s3_minio_sqlite", restore.stdout)

    def test_owner_docs_name_restore_recipe_and_proof_gated_object_store_lane(self) -> None:
        snippet = (REPO_ROOT / "docs/tools/snippet.md").read_text(encoding="utf-8")
        playbook = (REPO_ROOT / "docs/playbooks/post_merge_docs_hygiene.md").read_text(encoding="utf-8")
        combined = f"{snippet}\n{playbook}"

        self.assertIn("Fresh-clone restore", combined)
        self.assertIn("planveyor_docs_archive_snapshot_restore", combined)
        self.assertIn("--dest-db .tmp/planveyor_docs_archive.sqlite", combined)
        self.assertIn("planveyor_docs_archive_query --db .tmp/planveyor_docs_archive.sqlite", combined)
        self.assertIn('"post merge docs hygiene"', combined)
        self.assertIn("s3_minio_sqlite", combined)
        self.assertIn("object-file", combined)
        self.assertIn("credentials", combined)
        self.assertIn("Deployment-specific facts remain deferred", combined)

    def test_restore_dedups_records_sharing_path_and_sha(self) -> None:
        # Decision pin (owner-approved 2026-06-28): the dedup key on restore is
        # (original_path, sha256). When a portability sweep collapses two
        # historically-distinct records (which differed only in owner-local path
        # tokens) into identical content, they become the same (path, sha) and the
        # second restore insert is a skipped duplicate. This is semantically
        # correct -- there is no value in storing two byte-identical copies of a
        # document -- and the JSONL artifact still physically carries every record.
        # This test pins the behavior so a future change is intentional, not accidental.
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            # Write the JSONL directly with two records sharing (path, sha), mirroring
            # the post-sweep archive where a portability substitution collapsed two
            # historical versions into identical content. We bypass the ingest path
            # (which dedups on insert) because the real archive accumulated these
            # across separate ingestion cycles.
            content = "# Doc\n\nportable content\n"
            sha = docs_archive._sha256_hex(content)
            records = []
            for ts in ("2026-03-30T22:19:53Z", "2026-06-23T22:04:24Z"):
                records.append(
                    {
                        "kind": "plan",
                        "original_path": "docs/plans/260101_1200_x.md",
                        "sha256": sha,
                        "archived_at_utc": ts,
                        "title": "Doc",
                        "extra_json": "{}",
                        "content": content,
                    }
                )

            out_dir = tmp / "snapshot"
            out_dir.mkdir(parents=True)
            docs_path = out_dir / "archived_docs.jsonl"
            with docs_path.open("w", encoding="utf-8") as f:
                for record in records:
                    f.write(docs_archive._json_dumps_stable(record))
                    f.write("\n")

            manifest = {
                "artifact": {
                    "content_type": "application/x-jsonlines; charset=utf-8",
                    "path": "archived_docs.jsonl",
                    "record_count": len(records),
                    "sha256": docs_archive._sha256_file(docs_path),
                    "size_bytes": docs_path.stat().st_size,
                },
                "created_at_utc": "2026-06-28T00:00:00Z",
                "restore": {
                    "preconditions": ["python sqlite3 with FTS5"],
                    "requires_original_tmp_db": False,
                    "restores_to": "sqlite_fts5",
                },
                "schema_version": "1",
                "snapshot_manifest_version": "1",
                "stable_identity_fields": ["original_path", "kind", "sha256"],
                "storage_backend": "git_text_export",
                "tool": "docs_archive",
                "tool_version": "1",
            }
            manifest_path = out_dir / "manifest.json"
            manifest_path.write_text(
                docs_archive._json_dumps_pretty(manifest), encoding="utf-8"
            )

            dest_db = tmp / "restored.sqlite"
            restore = docs_archive.restore_snapshot_from_manifest(
                manifest_path=manifest_path,
                dest_db=dest_db,
            )
            # The JSONL has 2 records; restore dedups to 1 unique (path, sha).
            self.assertEqual(1, restore.restored_docs)
            self.assertEqual(1, restore.skipped_existing)


class DocsArchiveFacadeProjectRootTests(unittest.TestCase):
    """Relative archive paths resolve in the selected project, never the runtime."""

    @staticmethod
    def _worktree_snapshot(root: Path) -> dict[str, bytes]:
        return {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted(root.rglob("*"))
            if path.is_file() and ".git" not in path.relative_to(root).parts
        }

    def test_public_archive_routes_use_project_relative_paths(self) -> None:
        with AuthorityFixture(identity="planveyor") as fixture:
            entry = write(
                fixture.runtime_root,
                "bin/planveyor",
                (REPO_ROOT / "bin" / "planveyor").read_bytes(),
                executable=True,
            )
            runtime_commit = commit_all(fixture.runtime_root, "public docs archive facade")
            target = fixture.target_root
            _write_archive_db(target / ".tmp/planveyor_docs_archive.sqlite")
            environment = fixture.environment()
            state_root = fixture.root / "state"
            state_root.mkdir()
            environment["PLANVEYOR_STATE_ROOT"] = str(state_root)
            runtime_before = self._worktree_snapshot(fixture.runtime_root)
            manifest_rel = "docs/_meta/archive_snapshots/current/manifest.json"
            restored_rel = ".tmp/planveyor_docs_archive_restored.sqlite"
            plan_path = "docs/plans/260101_1200_fresh_clone_restore_plan.md"
            commands = {
                "export": (
                    "planveyor_docs_archive_snapshot_export",
                    "--backend",
                    "git_text_export",
                    "--output-dir",
                    "docs/_meta/archive_snapshots/current",
                    "--force",
                    "--created-at-utc",
                    "2026-09-29T00:00:00Z",
                ),
                "validate": (
                    "planveyor_docs_archive_snapshot_validate",
                    "--manifest",
                    manifest_rel,
                    "--verify-artifact",
                ),
                "restore": (
                    "planveyor_docs_archive_snapshot_restore",
                    "--manifest",
                    manifest_rel,
                    "--dest-db",
                    restored_rel,
                    "--replace",
                    "--query",
                    "fresh clone restore proof",
                    "--expect-min-hits",
                    "1",
                ),
                "info": ("planveyor_docs_archive_snapshot_info", "--db", restored_rel),
                "query": (
                    "planveyor_docs_archive_query",
                    "--db",
                    restored_rel,
                    "--k",
                    "5",
                    "fresh clone restore proof",
                ),
                "show": ("planveyor_docs_archive_show", "--db", restored_rel, "--path", plan_path),
            }
            results = {}
            for label, arguments in commands.items():
                results[label] = subprocess.run(
                    [str(entry), "--project", str(target), *arguments],
                    cwd=target,
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=120,
                )
            manifest_in_target = (target / manifest_rel).is_file()
            restored_in_target = (target / restored_rel).is_file()
            runtime_after = self._worktree_snapshot(fixture.runtime_root)
            runtime_head = git(fixture.runtime_root, "rev-parse", "HEAD")

        for label, result in results.items():
            with self.subTest(route=label):
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(manifest_in_target)
        self.assertTrue(restored_in_target)
        self.assertIn("result: OK", results["validate"].stdout)
        self.assertIn("docs_count: 2", results["info"].stdout)
        self.assertIn(plan_path, results["query"].stdout)
        self.assertIn("fresh clone restore proof through archive query", results["show"].stdout)
        self.assertEqual(runtime_after, runtime_before)
        self.assertEqual(runtime_head, runtime_commit)


if __name__ == "__main__":
    unittest.main()

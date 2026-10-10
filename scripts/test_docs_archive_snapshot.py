#!/usr/bin/env python3
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import docs_archive


def _write_archive_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path.as_posix())
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        docs_archive.sqlite_fts5_self_check(conn)
        docs_archive.ensure_schema(conn)
        records = [
            {
                "kind": "plan",
                "original_path": "docs/plans/260101_1200_archive_snapshot_plan.md",
                "sha256": docs_archive._sha256_hex("# Plan A\n\nalpha portable snapshot restore\n"),
                "archived_at_utc": "2026-05-16T22:03:11Z",
                "title": "Plan A",
                "extra_json": "{}",
                "content": "# Plan A\n\nalpha portable snapshot restore\n",
            },
            {
                "kind": "code_review",
                "original_path": "docs/code_reviews/260101_1200_archive_snapshot_plan.md",
                "sha256": docs_archive._sha256_hex("# Review A\n\nbeta checksum manifest proof\n"),
                "archived_at_utc": "2026-05-17T00:00:00Z",
                "title": "Review A",
                "extra_json": "{}",
                "content": "# Review A\n\nbeta checksum manifest proof\n",
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


def _write_many_archive_db(db_path: Path, *, doc_count: int = 25) -> None:
    conn = sqlite3.connect(db_path.as_posix())
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        docs_archive.sqlite_fts5_self_check(conn)
        docs_archive.ensure_schema(conn)
        for i in range(doc_count):
            body = f"# Large Range {i}\n\nlarge range proof {i} shared token\n"
            record = {
                "kind": "plan",
                "original_path": f"docs/plans/260101_1200_large_range_{i:02d}.md",
                "sha256": docs_archive._sha256_hex(body),
                "archived_at_utc": f"2026-05-17T00:{i:02d}:00Z",
                "title": f"Large Range {i}",
                "extra_json": "{}",
                "content": body,
            }
            inserted = docs_archive._insert_archived_doc_record(
                conn,
                record,
                chunk_target_tokens=docs_archive.DEFAULT_CHUNK_TARGET_TOKENS,
            )
            assert inserted
        conn.commit()
    finally:
        conn.close()


class DocsArchiveSnapshotTests(unittest.TestCase):
    def test_git_text_export_restores_searchable_archive_without_source_db(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            source_db = tmp / "source.sqlite"
            out_dir = tmp / "snapshot"
            restored_db = tmp / "restored.sqlite"
            _write_archive_db(source_db)

            source = sqlite3.connect(docs_archive._sqlite_uri_readonly(source_db), uri=True)
            try:
                result = docs_archive.export_git_text_snapshot(
                    source,
                    db_path=source_db,
                    output_dir=out_dir,
                    force=False,
                    created_at_utc="2026-05-17T00:00:00Z",
                )
            finally:
                source.close()

            self.assertEqual("git_text_export", result.backend)
            self.assertEqual(2, result.docs_count)
            self.assertTrue((out_dir / "manifest.json").exists())
            self.assertTrue((out_dir / "archived_docs.jsonl").exists())
            manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual("git_text_export", manifest["storage_backend"])
            self.assertEqual(2, manifest["source_db"]["docs_count"])
            self.assertEqual(docs_archive._sha256_file(source_db), manifest["source_db"]["db_sha256"])
            self.assertEqual("2026-05-17T00:00:00Z", manifest["created_at_utc"])
            self.assertEqual(manifest["artifact"]["sha256"], docs_archive._sha256_file(out_dir / "archived_docs.jsonl"))
            self.assertFalse(manifest["restore"]["requires_original_tmp_db"])
            matrix = {row["backend"]: row for row in manifest["storage_matrix"]}
            self.assertTrue(matrix["git_text_export"]["selected"])
            self.assertIn("s3_minio_sqlite", matrix)

            source_db.unlink()
            restore = docs_archive.restore_snapshot_from_manifest(
                manifest_path=out_dir / "manifest.json",
                dest_db=restored_db,
                query="portable snapshot",
            )
            self.assertEqual("git_text_export", restore.backend)
            self.assertEqual(2, restore.restored_docs)
            self.assertGreaterEqual(int(restore.query_hits or 0), 1)

            again = docs_archive.restore_snapshot_from_manifest(
                manifest_path=out_dir / "manifest.json",
                dest_db=restored_db,
            )
            self.assertEqual(0, again.restored_docs)
            self.assertEqual(2, again.skipped_existing)

    def test_query_hits_and_snapshot_restore_are_bounded_by_record_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            source_db = tmp / "source.sqlite"
            out_dir = tmp / "snapshot"
            restored_db = tmp / "restored.sqlite"
            _write_many_archive_db(source_db, doc_count=25)

            source = sqlite3.connect(docs_archive._sqlite_uri_readonly(source_db), uri=True)
            try:
                hits = docs_archive.query_hits(
                    source,
                    query="large range proof",
                    kinds=("plan",),
                    k=7,
                )
                result = docs_archive.export_git_text_snapshot(
                    source,
                    db_path=source_db,
                    output_dir=out_dir,
                    force=False,
                    created_at_utc="2026-05-17T00:00:00Z",
                )
            finally:
                source.close()

            self.assertEqual(7, len(hits))
            self.assertTrue(
                all(hit.original_path.startswith("docs/plans/260101_1200_large_range_") for hit in hits)
            )
            self.assertEqual(25, result.docs_count)
            self.assertTrue((out_dir / "manifest.json").exists())
            manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(25, manifest["source_db"]["docs_count"])
            self.assertEqual(25, manifest["artifact"]["record_count"])

            source_db.unlink()
            restore = docs_archive.restore_snapshot_from_manifest(
                manifest_path=out_dir / "manifest.json",
                dest_db=restored_db,
                query="large range proof",
            )
            self.assertEqual(25, restore.restored_docs)
            self.assertEqual(5, restore.query_hits)

    def test_git_whole_sqlite_snapshot_restores_with_schema_readback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            source_db = tmp / "source.sqlite"
            out_dir = tmp / "whole"
            restored_db = tmp / "restored.sqlite"
            _write_archive_db(source_db)

            source = sqlite3.connect(docs_archive._sqlite_uri_readonly(source_db), uri=True)
            try:
                result = docs_archive.export_git_whole_sqlite_snapshot(
                    source,
                    db_path=source_db,
                    output_dir=out_dir,
                    force=False,
                    created_at_utc="2026-05-17T00:00:00Z",
                )
            finally:
                source.close()

            self.assertEqual("git_whole_sqlite", result.backend)
            restore = docs_archive.restore_snapshot_from_manifest(
                manifest_path=out_dir / "manifest.json",
                dest_db=restored_db,
                query="checksum manifest",
            )
            self.assertEqual(2, restore.restored_docs)
            self.assertGreaterEqual(int(restore.query_hits or 0), 1)

    def test_s3_minio_manifest_fails_closed_without_object_and_verifies_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            source_db = tmp / "source.sqlite"
            out_dir = tmp / "s3"
            restored_db = tmp / "restored.sqlite"
            _write_archive_db(source_db)
            object_sha = docs_archive._sha256_file(source_db)
            object_size = source_db.stat().st_size

            source = sqlite3.connect(docs_archive._sqlite_uri_readonly(source_db), uri=True)
            try:
                result = docs_archive.export_s3_minio_manifest(
                    source,
                    db_path=source_db,
                    output_dir=out_dir,
                    object_uri="s3://archive-snapshots/planveyor/current.sqlite",
                    object_sha256=object_sha,
                    object_size_bytes=object_size,
                    force=False,
                    created_at_utc="2026-05-17T00:00:00Z",
                )
            finally:
                source.close()
            self.assertEqual("s3_minio_sqlite", result.backend)

            with self.assertRaisesRegex(RuntimeError, "failing closed"):
                docs_archive.restore_snapshot_from_manifest(
                    manifest_path=out_dir / "manifest.json",
                    dest_db=restored_db,
                )

            restore = docs_archive.restore_snapshot_from_manifest(
                manifest_path=out_dir / "manifest.json",
                dest_db=restored_db,
                object_file=source_db,
                query="portable snapshot",
            )
            self.assertEqual("s3_minio_sqlite", restore.backend)
            self.assertGreaterEqual(int(restore.query_hits or 0), 1)

            manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
            manifest["artifact"]["sha256"] = "0" * 64
            bad_manifest = out_dir / "bad_manifest.json"
            bad_manifest.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "checksum mismatch"):
                docs_archive.restore_snapshot_from_manifest(
                    manifest_path=bad_manifest,
                    dest_db=tmp / "bad.sqlite",
                    object_file=source_db,
                )

    def test_s3_manifest_rejects_secret_like_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "manifest.json"
            manifest = {
                "snapshot_manifest_version": docs_archive.SNAPSHOT_FORMAT_VERSION,
                "storage_backend": "s3_minio_sqlite",
                "artifact": {
                    "object_uri": "s3://archive-snapshots/current.sqlite",
                    "size_bytes": 1,
                    "sha256": "1" * 64,
                    "secret_access_key": "<REDACTED>",
                },
            }
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "secret-like"):
                docs_archive.load_snapshot_manifest(manifest_path)


if __name__ == "__main__":
    unittest.main()

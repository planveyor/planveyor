#!/usr/bin/env python3
"""Tests for portability normalization on the docs_archive ingest path.

The append path (`docs_archive.archive_markdown_paths`) normalizes owner-local
paths in archived content before computing the sha256, so archived records carry
portable paths and the latent archive-contamination vector (plan 260621_1204:301)
is closed at its source. These tests verify the hook end-to-end through the real
ingest path: content, sha, dedup key, and FTS chunks all reflect the swept form.
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import docs_archive
from scripts import portability_substitution as ps

# Owner-home prefix assembled by concatenation to keep the test source clean of
# the literal owner token (which the runtime-portability regression test flags).
_OWNER = "/" + "Users/" + "fixture-user"
_FIXTURE_RULES = ps.PortabilityRules(
    literal_rules=(
        (_OWNER + "/sample_tools", "${SOURCE_ROOT:-$HOME/sample_tools}"),
        (_OWNER + "/sample.worktrees", "${CONSUMER_WORKTREES_ROOT:-$HOME/sample.worktrees}"),
        (_OWNER + "/peer-one", "${PEER_ONE_ROOT:-$HOME/peer-one}"),
        (_OWNER + "/peer-two", "${PEER_TWO_ROOT:-$HOME/peer-two}"),
        (_OWNER + "/peer-three", "${PEER_THREE_ROOT:-$HOME/peer-three}"),
        (_OWNER + "/sample_front", "${CONSUMER_FRONT_ROOT:-$HOME/sample_front}"),
        *((_OWNER + "/" + item, "$HOME/" + item)
          for item in (".provider-state", ".codex", "Downloads", "Documents", "Library", ".local")),
    ), miniforge_replacement="python3", homebrew_source="/opt/homebrew/bin/python",
    homebrew_replacement="python3", primary_product_source=_OWNER + "/sample",
    primary_product_replacement="${CONSUMER_PRODUCT_ROOT:-$HOME/sample}",
    preserve_version_pinned_receipt=True,
)


class ArchiveIngestNormalizationTests(unittest.TestCase):
    """archive_markdown_paths must portabilize content at ingest."""

    def _ingest(self, tmp: Path, content: str, path_name: str = "docs/plans/260101_1200_x.md") -> sqlite3.Connection:
        # Write the dirty fixture to disk, then run the real append path, which
        # reads it back and applies portabilize_text before sha/insert. We pass an
        # absolute path: archive_markdown_paths uses `disk_path = REPO_ROOT /
        # original_path` only for relative paths; an absolute path is used as-is.
        dirty = tmp / path_name
        dirty.parent.mkdir(parents=True, exist_ok=True)
        dirty.write_text(content, encoding="utf-8")

        db_path = tmp / "archive.sqlite"
        conn = sqlite3.connect(db_path.as_posix())
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            docs_archive.sqlite_fts5_self_check(conn)
            docs_archive.ensure_schema(conn)
        except Exception:
            conn.close()
            raise
        stats = docs_archive.archive_markdown_paths(
            conn,
            [dirty.as_posix()],
            db_label="test",
            chunk_target_tokens=docs_archive.DEFAULT_CHUNK_TARGET_TOKENS,
            extra_meta=None,
            dry_run=False,
            portability_rules=_FIXTURE_RULES,
        )
        self.assertEqual(1, stats.inserted, "fixture must ingest exactly one record")
        return conn

    def test_owner_local_miniforge_path_swept_in_stored_content(self) -> None:
        dirty = f"# Plan\n\nRun `{_OWNER}/miniforge3/envs/sample/bin/python -B scripts/foo.py`.\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            conn = self._ingest(tmp, dirty)
            try:
                row = conn.execute(
                    "SELECT content, sha256 FROM archived_docs ORDER BY doc_id LIMIT 1"
                ).fetchone()
                self.assertIsNotNone(row)
                stored_content, stored_sha = row
                # The owner-local interpreter must be gone from stored content.
                self.assertNotIn(_OWNER, stored_content)
                self.assertIn("python3", stored_content)
                # sha must match the swept content (proves normalization ran pre-sha).
                self.assertEqual(
                    stored_sha,
                    docs_archive._sha256_hex(ps.portabilize_text(dirty, rules=_FIXTURE_RULES)),
                )
            finally:
                conn.close()

    def test_repo_root_path_swept_in_stored_content(self) -> None:
        dirty = f"source {_OWNER}/sample_tools/scripts/sample.zsh\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            conn = self._ingest(tmp, dirty)
            try:
                stored = conn.execute(
                    "SELECT content FROM archived_docs ORDER BY doc_id LIMIT 1"
                ).fetchone()[0]
                self.assertIn("${SOURCE_ROOT:-$HOME/sample_tools}", stored)
                self.assertNotIn(_OWNER, stored)
            finally:
                conn.close()

    def test_fts_chunks_built_from_swept_content(self) -> None:
        # The FTS chunks are built from the same `text` variable that was portabilized,
        # so the chunk body must contain the swept (portable) form and NOT the
        # owner-local token. Verified by direct SELECT (the chunk is the FTS index
        # row) rather than via query_hits, which is a separate concern.
        dirty = f"# Plan\n\nrun `{_OWNER}/miniforge3/envs/sample/bin/python foo.py` here\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            conn = self._ingest(tmp, dirty)
            try:
                body = conn.execute("SELECT body FROM archived_chunks_fts ORDER BY rowid LIMIT 1").fetchone()[0]
                self.assertIn("python3", body)
                self.assertNotIn(_OWNER, body)
                self.assertNotIn("miniforge3", body)
            finally:
                conn.close()

    def test_dedup_key_uses_swept_content_sha(self) -> None:
        # Two ingests of the same logical content (one dirty, one pre-swept) must
        # dedup: same (original_path, sha) -> second is skipped. This proves the
        # sha is computed from the portabilized form, not the raw disk form.
        dirty = f"# X\n\n{_OWNER}/miniforge3/envs/sample/bin/python a.py\n"
        clean = ps.portabilize_text(dirty, rules=_FIXTURE_RULES)
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            dirty_p = tmp / "docs/plans/260101_1200_x.md"
            dirty_p.parent.mkdir(parents=True, exist_ok=True)

            conn = sqlite3.connect((tmp / "archive.sqlite").as_posix())
            try:
                conn.execute("PRAGMA foreign_keys = ON")
                docs_archive.sqlite_fts5_self_check(conn)
                docs_archive.ensure_schema(conn)
                dirty_p.write_text(dirty, encoding="utf-8")
                s1 = docs_archive.archive_markdown_paths(
                    conn, [dirty_p.as_posix()], db_label="t",
                    chunk_target_tokens=docs_archive.DEFAULT_CHUNK_TARGET_TOKENS,
                    extra_meta=None, dry_run=False, portability_rules=_FIXTURE_RULES,
                )
                dirty_p.write_text(clean, encoding="utf-8")  # already-swept content
                s2 = docs_archive.archive_markdown_paths(
                    conn, [dirty_p.as_posix()], db_label="t",
                    chunk_target_tokens=docs_archive.DEFAULT_CHUNK_TARGET_TOKENS,
                    extra_meta=None, dry_run=False, portability_rules=_FIXTURE_RULES,
                )
                self.assertEqual(1, s1.inserted)
                self.assertEqual(0, s2.inserted, "pre-swept content must dedup against dirty ingest")
                self.assertEqual(1, s2.skipped_existing)
            finally:
                conn.close()

    def test_already_clean_content_round_trips_unchanged(self) -> None:
        clean = "# Plan\n\nRun `python3 -B scripts/foo.py`.\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            conn = self._ingest(tmp, clean)
            try:
                stored = conn.execute(
                    "SELECT content FROM archived_docs ORDER BY doc_id LIMIT 1"
                ).fetchone()[0]
                self.assertEqual(stored, clean)
            finally:
                conn.close()


class ArchiveDbLabelPortabilityProducerTests(unittest.TestCase):
    """The producer entrypoints must write a PORTABLE extra_json.db.

    Locks the S1 fix end-to-end: ``docs_archive ingest`` and the
    ``docs_hygiene_archive`` apply path both portabilize the db_label before it
    is stored, and the export chokepoint re-portabilizes any pre-fix records —
    so a snapshot cannot reintroduce an owner-local db path regardless of DB
    state. (The library function ``archive_markdown_paths`` itself is label-
    agnostic; the portabilization happens at the entrypoint, mirroring how the
    content portabilization in _ingest above is the library's own job.)
    """

    def test_ingest_cli_writes_portable_extra_json_db(self) -> None:
        import json

        dirty = "# Plan\n\nRun `python3 -B scripts/foo.py`.\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            doc = tmp / "docs" / "plans" / "260101_1200_x.md"
            doc.parent.mkdir(parents=True, exist_ok=True)
            doc.write_text(dirty, encoding="utf-8")
            # An absolute, owner-local DB path mirroring what
            # _sample_docs_archive_db_default yields on the owner's machine
            # (~/sample_tools/.tmp/...). portabilize_text only touches owner-
            # pattern paths, so the db_label must be swept on the way in.
            owner_tree = tmp / _OWNER.strip("/") / "sample_tools" / ".tmp"
            owner_tree.mkdir(parents=True, exist_ok=True)
            db_path = owner_tree / "archive.sqlite"
            with mock.patch.object(docs_archive, "load_portability_rules", return_value=_FIXTURE_RULES) as load_rules:
                rc = docs_archive.main(
                    [
                        "--db",
                        db_path.as_posix(),
                        "--content-profile-id",
                        "planveyor",
                        "ingest",
                        doc.as_posix(),
                    ]
                )
            load_rules.assert_called_once_with(content_profile_id="planveyor")
            self.assertEqual(rc, 0, "ingest must succeed")
            conn = sqlite3.connect(db_path.as_posix())
            try:
                extra_json = conn.execute("SELECT extra_json FROM archived_docs LIMIT 1").fetchone()[0]
            finally:
                conn.close()
        meta = json.loads(extra_json)
        self.assertIn("db", meta)
        self.assertNotIn(_OWNER, meta["db"])
        self.assertIn("${SOURCE_ROOT", meta["db"])

    def test_export_chokepoint_normalizes_pre_fix_dirty_db(self) -> None:
        """Even if the DB holds a raw owner-local db_label, export must portabilize.

        Simulates a pre-fix record ingested with db_label="test" replaced by a
        raw absolute path, then verifies the export chokepoint
        (_iter_archived_doc_records) emits a portable extra_json.db AND a sha
        that equals sha256(exported content).
        """
        import hashlib
        import json

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            db_path = tmp / "archive.sqlite"
            conn = sqlite3.connect(db_path.as_posix())
            try:
                conn.execute("PRAGMA foreign_keys = ON")
                docs_archive.sqlite_fts5_self_check(conn)
                docs_archive.ensure_schema(conn)
                # Insert a record carrying a RAW owner-local db_label (as a
                # pre-fix DB would), bypassing the CLI portabilization. The
                # stored sha is intentionally garbage ("sha") to prove the
                # chokepoint does NOT trust the stored sha.
                raw_meta = {"tool": "docs_archive", "db": f"{_OWNER}/sample_tools/x.sqlite"}
                conn.execute(
                    "INSERT INTO archived_docs(kind, original_path, sha256, archived_at_utc, title, extra_json, content) "
                    "VALUES (?,?,?,?,?,?,?)",
                    ("plan", "docs/x.md", "sha", "2026-01-01T00:00:00Z", "X", json.dumps(raw_meta), "# X\n"),
                )
                conn.commit()
                records = list(docs_archive._iter_archived_doc_records(conn, portability_rules=_FIXTURE_RULES))
            finally:
                conn.close()
        self.assertEqual(len(records), 1)
        exported_meta = json.loads(records[0]["extra_json"])
        self.assertNotIn(_OWNER, exported_meta["db"])
        self.assertIn("${SOURCE_ROOT", exported_meta["db"])
        # The garbage stored sha MUST be replaced by sha256(exported content):
        # content and sha must agree (producer contract enforced at chokepoint).
        self.assertEqual(records[0]["sha256"], hashlib.sha256(records[0]["content"].encode()).hexdigest())
        self.assertNotEqual(records[0]["sha256"], "sha")

    def test_export_chokepoint_portabilizes_dirty_content_and_recomputes_sha(self) -> None:
        """A DB record with owner-local CONTENT must be portabilized at export.

        Locks the S2 producer fix: a dirty source DB cannot produce a dirty
        export. The chokepoint portabilizes content AND recomputes sha so it is
        the sha of the (cleaned) emitted content, not the dirty-content sha.
        """
        import hashlib
        import json

        dirty_content = f"# Plan\n\nrun `{_OWNER}/sample_tools/scripts/foo.py`\n"
        # Stored sha is the sha of the DIRTY content (what a pre-fix DB holds).
        dirty_sha = hashlib.sha256(dirty_content.encode()).hexdigest()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            db_path = tmp / "archive.sqlite"
            conn = sqlite3.connect(db_path.as_posix())
            try:
                conn.execute("PRAGMA foreign_keys = ON")
                docs_archive.sqlite_fts5_self_check(conn)
                docs_archive.ensure_schema(conn)
                conn.execute(
                    "INSERT INTO archived_docs(kind, original_path, sha256, archived_at_utc, title, extra_json, content) "
                    "VALUES (?,?,?,?,?,?,?)",
                    ("plan", "docs/x.md", dirty_sha, "2026-01-01T00:00:00Z", "X", "{}", dirty_content),
                )
                conn.commit()
                records = list(docs_archive._iter_archived_doc_records(conn, portability_rules=_FIXTURE_RULES))
            finally:
                conn.close()
        self.assertEqual(len(records), 1)
        # Content portabilized: no owner token.
        self.assertNotIn(_OWNER, records[0]["content"])
        # sha is the sha of the EMITTED (clean) content, not the dirty-content sha.
        self.assertEqual(records[0]["sha256"], hashlib.sha256(records[0]["content"].encode()).hexdigest())
        self.assertNotEqual(records[0]["sha256"], dirty_sha)

    def test_export_chokepoint_rejects_none_content(self) -> None:
        """None content/extra_json must raise (NOT NULL contract), not coerce."""
        with self.assertRaises(TypeError):
            docs_archive._normalize_record_for_export(
                kind="plan",
                original_path="docs/x.md",
                sha="x",
                archived_at="2026-01-01T00:00:00Z",
                title="X",
                extra_json="{}",
                content=None,
            )


class ArchiveDbSummaryContentBytesTests(unittest.TestCase):
    """archive_db_summary content_bytes must be a UTF-8 BYTE count, not codepoints.

    Locks the round-5 fix: ``length(CAST(content AS BLOB))`` counts bytes, so
    multibyte content (Russian corpus) reports the real byte length, not the
    codepoint count that ``length(content)`` returned. A 4.7% delta on the real
    corpus would otherwise go undetected on revert.
    """

    def _summary(self, tmp: Path, content: str) -> dict:
        db_path = tmp / "archive.sqlite"
        conn = sqlite3.connect(db_path.as_posix())
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            docs_archive.sqlite_fts5_self_check(conn)
            docs_archive.ensure_schema(conn)
            conn.execute(
                "INSERT INTO archived_docs(kind, original_path, sha256, archived_at_utc, title, extra_json, content) "
                "VALUES (?,?,?,?,?,?,?)",
                ("plan", "docs/x.md", "sha", "2026-01-01T00:00:00Z", "X", "{}", content),
            )
            conn.commit()
            return docs_archive.archive_db_summary(conn, db_path=db_path)
        finally:
            conn.close()

    def test_multibyte_content_counts_bytes_not_codepoints(self) -> None:
        # 3 Cyrillic chars = 3 codepoints but 6 UTF-8 bytes.
        multibyte = "плл"
        self.assertEqual(len(multibyte), 3)  # codepoints
        self.assertEqual(len(multibyte.encode("utf-8")), 6)  # bytes
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = self._summary(Path(tmpdir), multibyte)
        self.assertEqual(summary["content_bytes"], 6)  # bytes, not 3

    def test_ascii_content_byte_count_equals_codepoint_count(self) -> None:
        ascii_content = "abc"
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = self._summary(Path(tmpdir), ascii_content)
        self.assertEqual(summary["content_bytes"], 3)


if __name__ == "__main__":
    unittest.main()

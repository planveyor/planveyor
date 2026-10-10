#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shlex
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:
    from scripts.test_support.process_contract_fixtures import run_zsh_fixture, temporary_git_root
except ModuleNotFoundError:
    from test_support.process_contract_fixtures import run_zsh_fixture, temporary_git_root


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "docs_retrieve.py"
DOCS_GET = ROOT / "scripts" / "docs_get.py"
DOCS_MULTI_GET = ROOT / "scripts" / "docs_multi_get.py"
PLANVEYOR_ZSH = ROOT / "scripts" / "planveyor.zsh"
FORBIDDEN_READ_LOG_KEYS = {"content", "snippet", "transcript", "prompt", "command_output"}


def _write_index(db_path: Path) -> None:
    conn = sqlite3.connect(db_path.as_posix())
    try:
        conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute(
            """
            CREATE VIRTUAL TABLE doc_chunks_fts USING fts5(
              corpus UNINDEXED,
              path UNINDEXED,
              start_line UNINDEXED,
              heading,
              body,
              tokenize = 'porter'
            )
            """
        )
        conn.execute("INSERT INTO meta(key, value) VALUES('schema_version', '1')")
        conn.execute("INSERT INTO meta(key, value) VALUES('tool_version', 'test')")
        conn.execute(
            "INSERT INTO doc_chunks_fts(corpus, path, start_line, heading, body) VALUES(?, ?, ?, ?, ?)",
            ("canon", "docs/example.md", "3", "Example", "alpha beta gamma"),
        )
        conn.commit()
    finally:
        conn.close()


def _write_docs_fixture(root: Path) -> None:
    docs_dir = root / "docs"
    docs_dir.mkdir()
    docs_dir.joinpath("example.md").write_text("one\ntwo\nthree\n", encoding="utf-8")
    docs_dir.joinpath("second.md").write_text("alpha\nbeta\n", encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _assert_no_forbidden_keys(testcase: unittest.TestCase, value: object) -> None:
    if isinstance(value, dict):
        testcase.assertTrue(FORBIDDEN_READ_LOG_KEYS.isdisjoint(value), value)
        for child in value.values():
            _assert_no_forbidden_keys(testcase, child)
    elif isinstance(value, list):
        for child in value:
            _assert_no_forbidden_keys(testcase, child)


class DocsRetrieveTests(unittest.TestCase):
    def test_json_output_and_log_share_event_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            db_path = tmp / "docs.sqlite"
            log_path = tmp / "queries.jsonl"
            _write_index(db_path)

            proc = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SCRIPT),
                    "--db",
                    str(db_path),
                    "--corpus",
                    "canon",
                    "--format",
                    "json",
                    "--log-file",
                    str(log_path),
                    "alpha",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            payload = json.loads(proc.stdout)
            event_id = payload["meta"]["event_id"]
            self.assertIsInstance(event_id, str)
            self.assertTrue(event_id)
            self.assertEqual(payload["hits"][0]["path"], "docs/example.md")

            rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["event_id"], event_id)
            self.assertEqual(rows[0]["hits"], 1)

    def test_text_output_exposes_event_id_without_files_mode_noise(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            db_path = tmp / "docs.sqlite"
            log_path = tmp / "queries.jsonl"
            _write_index(db_path)

            text_proc = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SCRIPT),
                    "--db",
                    str(db_path),
                    "--corpus",
                    "canon",
                    "--log-file",
                    str(log_path),
                    "alpha",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("event_id=", text_proc.stdout.splitlines()[0])

            files_proc = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SCRIPT),
                    "--db",
                    str(db_path),
                    "--corpus",
                    "canon",
                    "--files",
                    "--log-file",
                    str(log_path),
                    "alpha",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertEqual(files_proc.stdout.strip(), "docs/example.md")

    def test_docs_get_emits_path_only_read_log_and_env_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _write_docs_fixture(tmp)
            read_log = tmp / "reads.jsonl"
            env = {"PLANVEYOR_DOCS_RETRIEVE_READ_LOG": str(read_log)}

            proc = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(DOCS_GET),
                    "docs/example.md:2",
                    "--lines",
                    "2",
                    "--format",
                    "json",
                ],
                cwd=tmp,
                text=True,
                capture_output=True,
                env={**os.environ.copy(), **env},
                check=True,
            )

            payload = json.loads(proc.stdout)
            self.assertTrue(payload["ok"])
            self.assertTrue(str(payload["meta"]["read_event_id"]).startswith("read-"))
            rows = _read_jsonl(read_log)
            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row["event_type"], "docs_get.read")
            self.assertEqual(row["tool"], "docs_get")
            self.assertEqual(row["status"], "ok")
            self.assertEqual(row["path"], "docs/example.md")
            self.assertEqual(row["mode"], "around")
            self.assertEqual(row["returned_lines"], 2)
            self.assertEqual(row["format"], "json")
            _assert_no_forbidden_keys(self, row)

    def test_docs_get_read_log_cli_disable_and_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _write_docs_fixture(tmp)
            disabled_log = tmp / "disabled.jsonl"
            override_log = tmp / "override.jsonl"

            subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(DOCS_GET),
                    "docs/example.md:1",
                    "--lines",
                    "1",
                    "--read-log",
                    str(disabled_log),
                    "--no-read-log",
                ],
                cwd=tmp,
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertFalse(disabled_log.exists())

            subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(DOCS_GET),
                    "docs/example.md:1",
                    "--lines",
                    "1",
                    "--read-log",
                    str(override_log),
                ],
                cwd=tmp,
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertEqual(len(_read_jsonl(override_log)), 1)

    def test_docs_multi_get_emits_batch_read_log_without_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _write_docs_fixture(tmp)
            read_log = tmp / "multi_reads.jsonl"

            proc = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(DOCS_MULTI_GET),
                    "docs/*.md",
                    "--format",
                    "json",
                    "--read-log",
                    str(read_log),
                ],
                cwd=tmp,
                text=True,
                capture_output=True,
                check=True,
            )

            payload = json.loads(proc.stdout)
            self.assertTrue(payload["ok"])
            self.assertTrue(str(payload["meta"]["read_event_id"]).startswith("read-"))
            rows = _read_jsonl(read_log)
            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row["event_type"], "docs_multi_get.read")
            self.assertEqual(row["tool"], "docs_multi_get")
            self.assertEqual(row["status"], "ok")
            self.assertEqual(row["inputs_count"], 1)
            self.assertEqual(row["emitted_files"], 2)
            self.assertEqual(len(row["files"]), 2)
            self.assertEqual(row["skipped_inputs_count"], 0)
            self.assertGreater(row["total_bytes"], 0)
            _assert_no_forbidden_keys(self, row)

    def test_planveyor_docs_lookup_writes_query_and_read_logs_and_prints_receipt(self) -> None:
        with temporary_git_root() as tmpdir:
            tmp = Path(tmpdir)
            _write_docs_fixture(tmp)
            db_path = tmp / ".tmp" / "planveyor_docs_index.sqlite"
            db_path.parent.mkdir()
            _write_index(db_path)
            query_log = tmp / ".tmp" / "queries.jsonl"
            read_log = tmp / ".tmp" / "reads.jsonl"
            fixture_env = {
                "PLANVEYOR_ROOT": str(ROOT),
                "PLANVEYOR_DOCS_RETRIEVE_LOG": str(query_log),
                "PLANVEYOR_DOCS_RETRIEVE_READ_LOG": str(read_log),
            }
            command = (
                f"source {shlex.quote(str(PLANVEYOR_ZSH))} && "
                f"planveyor_docs_lookup canon --db {shlex.quote(str(db_path))} alpha"
            )

            proc = run_zsh_fixture(
                command,
                cwd=tmp,
                path=os.environ.get("PATH", os.defpath),
                pybin=sys.executable,
                fixture_env=fixture_env,
                capture_output=True,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}")

            self.assertIn("docs_lookup (corpus=canon", proc.stdout)
            self.assertIn("## Retrieval telemetry receipt", proc.stdout)
            self.assertIn("- used_for_decision: false", proc.stdout)
            self.assertIn("- read_open: ok", proc.stdout)
            self.assertIn("- read_log_status: present", proc.stdout)
            self.assertIn("- read_event_id: read-", proc.stdout)
            self.assertIn("- no_op_reason: not_used_for_decision", proc.stdout)
            self.assertIn("planveyor_docs_retrieve_outcome --event-id", proc.stdout)
            self.assertEqual(len(_read_jsonl(query_log)), 1)
            read_rows = _read_jsonl(read_log)
            self.assertEqual(len(read_rows), 1)
            self.assertEqual(read_rows[0]["tool"], "docs_multi_get")

    def test_docs_multi_get_env_zero_disables_read_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _write_docs_fixture(tmp)
            env = {**os.environ.copy(), "PLANVEYOR_DOCS_RETRIEVE_READ_LOG": "0"}

            subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(DOCS_MULTI_GET),
                    "docs/example.md",
                    "--format",
                    "json",
                ],
                cwd=tmp,
                text=True,
                capture_output=True,
                env=env,
                check=True,
            )
            self.assertFalse((tmp / ".tmp" / "planveyor_docs_retrieve_reads.jsonl").exists())


if __name__ == "__main__":
    unittest.main()

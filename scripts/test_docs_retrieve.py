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
DOCS_INDEX_BUILD = ROOT / "scripts" / "docs_index_build.py"
PLANVEYOR_ZSH = ROOT / "scripts" / "planveyor.zsh"
FORBIDDEN_READ_LOG_KEYS = {"content", "snippet", "transcript", "prompt", "command_output"}
RUSSIAN_GUIDE_TEXT = "# Sibling под свой стек\n\nalpha русская копия\n"


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
        index_build = _docs_index_build_module()
        rules = index_build.corpus_rules("canon", "docs", index_build.DEFAULT_CHUNK_TARGET_TOKENS, project_root=db_path.parent)
        conn.executemany(
            "INSERT INTO meta(key, value) VALUES(?, ?)",
            [("tool_version", "1"), ("fingerprint", index_build.compute_fingerprint(rules)),
             ("index_config_json", json.dumps(rules))],
        )
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


def _write_translation_fixture(root: Path, *, registry: bool = True) -> None:
    """English originals with Russian copies `name.ru.md` next to them."""

    if registry:
        registry_path = root / "i18n/pairs.json"
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry_path.write_text(json.dumps({"schema": "planveyor_i18n_pairs.v1", "pairs": []}), encoding="utf-8")
    files = {
        "docs/guides/stack-sibling.md": "# Stack sibling\n\nalpha english guide\n",
        "docs/guides/stack-sibling.ru.md": RUSSIAN_GUIDE_TEXT,
        "docs/tools/owner_runbook_codex.md": "# Owner runbook\n\nalpha english runbook\n",
        "docs/tools/owner_runbook_codex.ru.md": "# Runbook Owner\n\nalpha русский runbook\n",
        "docs/plans/260101_0000_fixture.md": "# Plan: fixture\n\nalpha plan\n",
        "docs/plans/README.ru.md": "# Планы\n\nalpha копия\n",
        "docs/followups/fixture__followups_backlog.md": "# Followups\n\n- [ ] alpha followup\n",
        "docs/followups/README.ru.md": "# Хвосты\n\n- [ ] alpha копия\n",
    }
    for rel_path, text in files.items():
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _write_legacy_index(db_path: Path, *, config: dict[str, object], fingerprint: str, stale_path: str) -> None:
    """An index written by an older build, before a corpus rule existed."""

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
        meta = {
            "schema_version": "1",
            "tool_version": "1",
            "fingerprint": fingerprint,
            "index_config_json": json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        }
        conn.executemany("INSERT INTO meta(key, value) VALUES(?, ?)", sorted(meta.items()))
        conn.execute(
            "INSERT INTO doc_chunks_fts(corpus, path, start_line, heading, body) VALUES(?, ?, ?, ?, ?)",
            ("canon", stale_path, "1", "Stale", "alpha stale copy"),
        )
        conn.commit()
    finally:
        conn.close()


def _indexed_paths(db_path: Path) -> list[tuple[str, str]]:
    conn = sqlite3.connect(db_path.as_posix())
    try:
        rows = conn.execute("SELECT DISTINCT corpus, path FROM doc_chunks_fts ORDER BY corpus, path").fetchall()
    finally:
        conn.close()
    return [(str(corpus), str(path)) for corpus, path in rows]


def _docs_index_build_module():
    scripts_dir = str(ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import docs_index_build

    return docs_index_build


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

    def test_docs_index_build_skips_russian_copies_in_every_corpus(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _write_translation_fixture(tmp)
            db_path = tmp / ".tmp" / "docs.sqlite"
            for corpus in ("canon", "followups", "plans"):
                subprocess.run(
                    [sys.executable, "-B", str(DOCS_INDEX_BUILD), "--db", str(db_path), "--corpus", corpus],
                    cwd=tmp,
                    text=True,
                    capture_output=True,
                    check=True,
                )
            indexed = _indexed_paths(db_path)

        self.assertEqual(
            indexed,
            [
                ("canon", "docs/guides/stack-sibling.md"),
                ("canon", "docs/tools/owner_runbook_codex.md"),
                ("followups", "docs/followups/fixture__followups_backlog.md"),
                ("plans", "docs/plans/260101_0000_fixture.md"),
            ],
        )

    def test_docs_index_migrates_only_additive_russian_copy_rule(self) -> None:
        index_build = _docs_index_build_module()
        rules = index_build.corpus_rules("canon", "docs", index_build.DEFAULT_CHUNK_TARGET_TOKENS, project_root=ROOT)
        self.assertEqual(rules["exclude_suffixes"], [".ru.md"])
        rules_before = {key: value for key, value in rules.items() if key != "exclude_suffixes"}
        configs_before = {
            "before_rule": rules_before,
            "before_rule_and_plans": {key: value for key, value in rules_before.items() if key != "plans"},
            "per_corpus": {**rules_before, "corpus": "canon"},
        }
        paths = {
            "canon": "docs/guides/stack-sibling.md",
            "followups": "docs/followups/fixture__followups_backlog.md",
            "plans": "docs/plans/260101_0000_fixture.md",
        }
        for requested in paths:
            for label, config in configs_before.items():
                with self.subTest(corpus=requested, index=label), tempfile.TemporaryDirectory() as tmpdir:
                    tmp = Path(tmpdir)
                    _write_translation_fixture(tmp)
                    db_path = tmp / "docs.sqlite"
                    _write_legacy_index(
                        db_path, config=config, fingerprint=index_build.compute_fingerprint(config),
                        stale_path="docs/guides/stack-sibling.ru.md",
                    )
                    conn = sqlite3.connect(str(db_path))
                    try:
                        if label == "per_corpus":
                            conn.execute("UPDATE meta SET key = 'corpus_rules_json' WHERE key = 'index_config_json'")
                        for corpus, path in paths.items():
                            conn.execute(
                                "INSERT INTO doc_chunks_fts VALUES(?, ?, ?, ?, ?)",
                                (corpus, path, "1", "Preserved", "alpha stable original"),
                            )
                            if corpus != "canon":
                                conn.execute(
                                    "INSERT INTO doc_chunks_fts VALUES(?, ?, ?, ?, ?)",
                                    (corpus, path[:-3] + ".ru.md", "1", "Stale", "alpha"),
                                )
                            conn.executemany("INSERT INTO meta VALUES(?, ?)", [
                                (f"built_at_utc.{corpus}", "1"),
                                (f"files_total.{corpus}", "2"), (f"chunks_total.{corpus}", "2"),
                            ])
                        conn.commit()
                    finally:
                        conn.close()

                    # Read old indexes safely without rewriting them. Exclusion
                    # happens before LIMIT, so a copy cannot crowd out an original.
                    before = db_path.read_bytes()
                    for corpus, path in paths.items():
                        retrieve = subprocess.run(
                            [sys.executable, "-B", str(SCRIPT), "--db", str(db_path), "--corpus", corpus,
                             "--k", "1", "--format", "json", "--no-log", "alpha"],
                            cwd=tmp, text=True, capture_output=True,
                        )
                        self.assertEqual(retrieve.returncode, 0, retrieve.stdout + retrieve.stderr)
                        self.assertEqual(json.loads(retrieve.stdout)["files"], [path])
                    self.assertEqual(db_path.read_bytes(), before)

                    rebuilt = subprocess.run(
                        [sys.executable, "-B", str(DOCS_INDEX_BUILD), "--db", str(db_path), "--corpus", requested],
                        cwd=tmp, text=True, capture_output=True,
                    )
                    self.assertEqual(rebuilt.returncode, 0, rebuilt.stdout + rebuilt.stderr)
                    self.assertIn("index_migration: translation_copy_exclusion", rebuilt.stdout)
                    indexed = _indexed_paths(db_path)
                    self.assertFalse([path for _, path in indexed if path.endswith(".ru.md")], indexed)
                    conn = sqlite3.connect(str(db_path))
                    try:
                        meta = dict(conn.execute("SELECT key, value FROM meta"))
                        self.assertEqual(meta["fingerprint"], index_build.compute_fingerprint(rules))
                        for corpus, path in paths.items():
                            if corpus != requested:
                                row = conn.execute(
                                    "SELECT heading FROM doc_chunks_fts WHERE corpus = ? AND path = ?", (corpus, path)
                                ).fetchone()
                                self.assertEqual(row, ("Preserved",))
                                self.assertEqual(meta[f"built_at_utc.{corpus}"], "1")
                                self.assertEqual(meta[f"files_total.{corpus}"], "1")
                                self.assertEqual(meta[f"chunks_total.{corpus}"], "1")
                    finally:
                        conn.close()

    def test_docs_index_and_globs_keep_sibling_russian_files_without_registry(self) -> None:
        index_build = _docs_index_build_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _write_translation_fixture(tmp, registry=False)
            rules = index_build.corpus_rules("canon", "docs", index_build.DEFAULT_CHUNK_TARGET_TOKENS, project_root=tmp)
            self.assertNotIn("exclude_suffixes", rules)
            source_rules = index_build.corpus_rules("canon", "docs", index_build.DEFAULT_CHUNK_TARGET_TOKENS, project_root=ROOT)
            self.assertEqual(rules, {key: value for key, value in source_rules.items() if key != "exclude_suffixes"})
            db_path = tmp / "docs.sqlite"
            _write_legacy_index(db_path, config=rules, fingerprint=index_build.compute_fingerprint(rules),
                                stale_path="docs/guides/stack-sibling.ru.md")
            env = {**os.environ, "PLANVEYOR_ROOT": str(ROOT)}
            before = subprocess.run(
                [sys.executable, "-B", str(SCRIPT), "--db", str(db_path), "--corpus", "canon",
                 "--format", "json", "--no-log", "alpha"], cwd=tmp, env=env, text=True, capture_output=True,
            )
            self.assertEqual(before.returncode, 0, before.stdout + before.stderr)
            self.assertEqual(json.loads(before.stdout)["files"], ["docs/guides/stack-sibling.ru.md"])
            for corpus in ("canon", "followups", "plans"):
                build = subprocess.run(
                    [sys.executable, "-B", str(DOCS_INDEX_BUILD), "--db", str(db_path), "--corpus", corpus],
                    cwd=tmp, env=env, text=True, capture_output=True,
                )
                self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
                self.assertNotIn("index_migration", build.stdout)
            indexed = _indexed_paths(db_path)
            self.assertEqual({corpus for corpus, path in indexed if path.endswith(".ru.md")}, {"canon", "followups", "plans"})
            multi = subprocess.run(
                [sys.executable, "-B", str(DOCS_MULTI_GET), "docs/guides/*.md", "--format", "json", "--no-read-log"],
                cwd=tmp, env=env, text=True, capture_output=True,
            )
            self.assertEqual(multi.returncode, 0, multi.stdout + multi.stderr)
            self.assertEqual([file["path"] for file in json.loads(multi.stdout)["files"]],
                             ["docs/guides/stack-sibling.md", "docs/guides/stack-sibling.ru.md"])

    def test_docs_index_rejects_unrelated_rules_and_damaged_metadata(self) -> None:
        index_build = _docs_index_build_module()
        changes = ("canon", "tool_version", "root", "tokens", "fingerprint", "config", "missing_config", "missing_fingerprint")
        for change in changes:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as tmpdir:
                tmp = Path(tmpdir)
                _write_translation_fixture(tmp)
                rules = index_build.corpus_rules("canon", "docs", index_build.DEFAULT_CHUNK_TARGET_TOKENS, project_root=tmp)
                config = {key: value for key, value in rules.items() if key != "exclude_suffixes"}
                if change == "canon":
                    config["canon"] = {"exclude_prefixes": []}
                elif change == "tool_version":
                    config["tool_version"] = "other"
                elif change == "root":
                    config["root"] = "other-docs"
                elif change == "tokens":
                    config["chunk_target_tokens"] = 1200
                db_path = tmp / "docs.sqlite"
                _write_legacy_index(db_path, config=config, fingerprint=index_build.compute_fingerprint(config),
                                    stale_path="docs/guides/stack-sibling.ru.md")
                conn = sqlite3.connect(str(db_path))
                try:
                    if change == "fingerprint":
                        conn.execute("UPDATE meta SET value = 'bad' WHERE key = 'fingerprint'")
                    elif change == "config":
                        conn.execute("UPDATE meta SET value = '{' WHERE key = 'index_config_json'")
                    elif change.startswith("missing_"):
                        key = "index_config_json" if change == "missing_config" else "fingerprint"
                        conn.execute("DELETE FROM meta WHERE key = ?", (key,))
                    conn.commit()
                    before = conn.execute("SELECT key, value FROM meta ORDER BY key").fetchall()
                finally:
                    conn.close()
                build = subprocess.run(
                    [sys.executable, "-B", str(DOCS_INDEX_BUILD), "--db", str(db_path), "--corpus", "followups"],
                    cwd=tmp, text=True, capture_output=True,
                )
                self.assertEqual(build.returncode, 2, build.stdout + build.stderr)
                # Retrieval preserves the stored chunk/root parameters; only
                # unknown rules or broken metadata make that read unsafe.
                retrieve = subprocess.run(
                    [sys.executable, "-B", str(SCRIPT), "--db", str(db_path), "--corpus", "canon",
                     "--format", "json", "--no-log", "alpha"], cwd=tmp, text=True, capture_output=True,
                )
                if change in {"root", "tokens"}:
                    self.assertEqual(retrieve.returncode, 0, retrieve.stdout + retrieve.stderr)
                else:
                    self.assertEqual(retrieve.returncode, 1, retrieve.stdout + retrieve.stderr)
                    self.assertEqual(json.loads(retrieve.stdout)["files"], [])
                self.assertEqual(_indexed_paths(db_path), [("canon", "docs/guides/stack-sibling.ru.md")])
                conn = sqlite3.connect(str(db_path))
                try:
                    self.assertEqual(conn.execute("SELECT key, value FROM meta ORDER BY key").fetchall(), before)
                finally:
                    conn.close()

    def test_docs_index_policy_removal_requires_explicit_rebuild(self) -> None:
        index_build = _docs_index_build_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _write_translation_fixture(tmp, registry=False)
            rules = index_build.corpus_rules("canon", "docs", index_build.DEFAULT_CHUNK_TARGET_TOKENS, project_root=tmp)
            config = {**rules, "exclude_suffixes": [".ru.md"]}
            db_path = tmp / "docs.sqlite"
            _write_legacy_index(db_path, config=config, fingerprint=index_build.compute_fingerprint(config),
                                stale_path="docs/guides/stack-sibling.md")
            build = subprocess.run(
                [sys.executable, "-B", str(DOCS_INDEX_BUILD), "--db", str(db_path), "--corpus", "followups"],
                cwd=tmp, text=True, capture_output=True,
            )
            self.assertEqual(build.returncode, 2, build.stdout + build.stderr)
            self.assertIn("Index fingerprint mismatch", build.stderr)
            retrieve = subprocess.run(
                [sys.executable, "-B", str(SCRIPT), "--db", str(db_path), "--corpus", "canon",
                 "--format", "json", "--no-log", "alpha"], cwd=tmp, text=True, capture_output=True,
            )
            self.assertEqual(retrieve.returncode, 1, retrieve.stdout + retrieve.stderr)
            self.assertEqual(json.loads(retrieve.stdout)["files"], [])

    def test_docs_retrieve_missing_and_corrupt_index_still_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            for label in ("missing", "corrupt", "no_tables"):
                with self.subTest(index=label):
                    db_path = tmp / (label + ".sqlite")
                    if label == "corrupt":
                        db_path.write_bytes(b"not sqlite")
                    elif label == "no_tables":
                        sqlite3.connect(str(db_path)).close()
                    retrieve = subprocess.run(
                        [sys.executable, "-B", str(SCRIPT), "--db", str(db_path), "--corpus", "canon",
                         "--format", "json", "--no-log", "alpha"], cwd=tmp, text=True, capture_output=True,
                    )
                    self.assertEqual(retrieve.returncode, 1, retrieve.stdout + retrieve.stderr)
                    self.assertEqual(json.loads(retrieve.stdout)["files"], [])
                    self.assertNotIn("Traceback", retrieve.stderr)
                    if label == "missing":
                        self.assertFalse(db_path.exists())

    def test_invalid_target_registry_keeps_copy_filter_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _write_translation_fixture(tmp)
            (tmp / "i18n/pairs.json").write_text("{", encoding="utf-8")
            build = subprocess.run(
                [sys.executable, "-B", str(DOCS_INDEX_BUILD), "--db", "docs.sqlite", "--corpus", "canon"],
                cwd=tmp, text=True, capture_output=True,
            )
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            self.assertFalse([path for _, path in _indexed_paths(tmp / "docs.sqlite") if path.endswith(".ru.md")])
            multi = subprocess.run(
                [sys.executable, "-B", str(DOCS_MULTI_GET), "docs/guides/*.md", "--format", "json", "--no-read-log"],
                cwd=tmp, text=True, capture_output=True,
            )
            self.assertEqual(multi.returncode, 0, multi.stdout + multi.stderr)
            self.assertEqual([file["path"] for file in json.loads(multi.stdout)["files"]], ["docs/guides/stack-sibling.md"])

    def test_docs_multi_get_glob_skips_russian_copies_but_explicit_path_reads(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _write_translation_fixture(tmp)

            def run_multi_get(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
                return subprocess.run(
                    [sys.executable, "-B", str(DOCS_MULTI_GET), *args, "--format", "json", "--no-read-log"],
                    cwd=tmp,
                    input=stdin,
                    text=True,
                    capture_output=True,
                    check=False,
                )

            by_glob = run_multi_get("docs/guides/*.md", "docs/tools/*")
            recursive = run_multi_get("docs/**/*.md")
            explicit = run_multi_get("docs/guides/stack-sibling.ru.md", "docs/guides/*.md")
            from_stdin = run_multi_get("-", stdin="docs/tools/owner_runbook_codex.ru.md\n")
            only_copies = run_multi_get("docs/guides/*.ru.md")

        self.assertEqual(by_glob.returncode, 0, by_glob.stderr)
        by_glob_payload = json.loads(by_glob.stdout)
        self.assertEqual(
            [doc["path"] for doc in by_glob_payload["files"]],
            ["docs/guides/stack-sibling.md", "docs/tools/owner_runbook_codex.md"],
        )
        self.assertEqual(
            by_glob_payload["meta"]["skipped_inputs"],
            [
                {"input": "docs/guides/stack-sibling.ru.md", "reason": "translation_copy"},
                {"input": "docs/tools/owner_runbook_codex.ru.md", "reason": "translation_copy"},
            ],
        )

        self.assertEqual(recursive.returncode, 0, recursive.stderr)
        recursive_paths = [doc["path"] for doc in json.loads(recursive.stdout)["files"]]
        self.assertIn("docs/plans/260101_0000_fixture.md", recursive_paths)
        self.assertFalse([path for path in recursive_paths if path.endswith(".ru.md")], recursive_paths)

        self.assertEqual(explicit.returncode, 0, explicit.stderr)
        explicit_payload = json.loads(explicit.stdout)
        self.assertEqual(
            [doc["path"] for doc in explicit_payload["files"]],
            ["docs/guides/stack-sibling.ru.md", "docs/guides/stack-sibling.md"],
        )
        self.assertEqual(explicit_payload["files"][0]["content"], RUSSIAN_GUIDE_TEXT)
        self.assertEqual(explicit_payload["meta"]["skipped_inputs"], [])

        self.assertEqual(from_stdin.returncode, 0, from_stdin.stderr)
        self.assertEqual(
            [doc["path"] for doc in json.loads(from_stdin.stdout)["files"]],
            ["docs/tools/owner_runbook_codex.ru.md"],
        )

        self.assertEqual(only_copies.returncode, 1, only_copies.stdout + only_copies.stderr)
        only_copies_payload = json.loads(only_copies.stdout)
        self.assertFalse(only_copies_payload["ok"])
        self.assertEqual(
            only_copies_payload["meta"]["skipped_inputs"],
            [{"input": "docs/guides/stack-sibling.ru.md", "reason": "translation_copy"}],
        )

    def test_docs_get_reads_explicit_russian_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _write_translation_fixture(tmp)

            proc = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(DOCS_GET),
                    "docs/guides/stack-sibling.ru.md",
                    "--full",
                    "--format",
                    "json",
                    "--no-read-log",
                ],
                cwd=tmp,
                text=True,
                capture_output=True,
                check=True,
            )

        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["path"], "docs/guides/stack-sibling.ru.md")
        self.assertEqual(payload["content"], RUSSIAN_GUIDE_TEXT)


if __name__ == "__main__":
    unittest.main()

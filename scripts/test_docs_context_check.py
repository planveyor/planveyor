#!/usr/bin/env python3
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.test_contract_authority_support import AuthorityFixture, commit_all, git, write


def _write_decoy_index(db_path: Path) -> None:
    """A minimal index that docs_context_check accepts, with one engine-only path."""

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path.as_posix())
    try:
        conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute(
            "CREATE VIRTUAL TABLE doc_chunks_fts USING fts5("
            "corpus UNINDEXED, path UNINDEXED, start_line UNINDEXED, heading, body)"
        )
        conn.execute(
            "INSERT INTO doc_chunks_fts(corpus, path, start_line, heading, body) "
            "VALUES ('plans', 'engine_only/decoy_plan.md', 1, 'Decoy', 'runtime decoy')"
        )
        conn.commit()
    finally:
        conn.close()


class DocsContextRegistryTests(unittest.TestCase):
    def test_arch_and_brd_contexts_require_explicit_target_rules(self) -> None:
        from scripts import docs_context_registry as registry

        for path in ("docs/arch/decision.md", "docs/brd/requirements.md"):
            with self.subTest(path=path):
                self.assertEqual(registry.contexts_for_path(path), [])
        rule = registry.ContextRule("docs/arch/", "Decisions", "Target-declared canon")
        self.assertEqual(
            registry.contexts_for_path("./docs/arch/decision.md", rules=[rule]),
            [{"prefix": "docs/arch/", "label": "Decisions", "text": "Target-declared canon"}],
        )
        self.assertEqual(registry.contexts_for_path("docs/guides/setup.md")[0]["label"], "Guides")


class DocsContextCheckFacadeProjectRootTests(unittest.TestCase):
    """The public coverage check reads the index the project built."""

    def _run_public(
        self,
        entry: Path,
        project: Path,
        environment: dict[str, str],
        *arguments: str,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(entry), "--project", str(project), *arguments],
            cwd=project,
            env=environment,
            stdin=subprocess.DEVNULL,
            text=True,
            capture_output=True,
            check=False,
            timeout=120,
        )

    def test_public_context_check_reads_project_index_for_relative_db(self) -> None:
        with AuthorityFixture(identity="planveyor") as fixture:
            write(
                fixture.runtime_root,
                "bin/planveyor",
                (REPO_ROOT / "bin" / "planveyor").read_bytes(),
                executable=True,
            )
            # A same-named index inside the runtime checkout must not answer
            # for the consumer.
            _write_decoy_index(fixture.runtime_root / ".tmp/planveyor_docs_index.sqlite")
            runtime_commit = commit_all(fixture.runtime_root, "public context check facade")
            entry = fixture.runtime_root / "bin/planveyor"
            target = fixture.target_root
            write(target, "docs/plans/260929_1200_context_fixture.md", "# Plan: context fixture\n\nBody.\n")
            commit_all(target, "context coverage plan fixture")
            environment = fixture.environment()
            state_root = fixture.root / "state"
            state_root.mkdir()
            environment["PLANVEYOR_STATE_ROOT"] = str(state_root)

            build = self._run_public(entry, target, environment, "planveyor_docs_index_build", "plans")
            check_arguments = ("--corpus", "plans", "--db", ".tmp/planveyor_docs_index.sqlite", "--format", "json")
            wrapper = self._run_public(
                entry, target, environment, "planveyor_docs_context_check", *check_arguments
            )
            runtime_helper = self._run_public(
                entry, target, environment, "planveyor_runtime_py", "docs_context_check.py", *check_arguments
            )
            default_db = self._run_public(
                entry, target, environment, "planveyor_docs_context_check", "--corpus", "plans", "--format", "json"
            )
            runtime_status = git(fixture.runtime_root, "status", "--short", "--untracked-files=all")
            runtime_head = git(fixture.runtime_root, "rev-parse", "HEAD")

        for label, result in (
            ("build", build),
            ("wrapper", wrapper),
            ("runtime_helper", runtime_helper),
            ("default_db", default_db),
        ):
            with self.subTest(step=label):
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("engine_only/decoy_plan.md", wrapper.stdout)
        payload = json.loads(wrapper.stdout)
        self.assertTrue(payload["ok"], payload)
        self.assertEqual(payload["meta"]["total_paths"], 1)
        self.assertEqual(payload["uncovered_paths"], [])
        # The wrapper and the documented runtime helper form are equivalent.
        self.assertEqual(payload, json.loads(runtime_helper.stdout))
        default_payload = json.loads(default_db.stdout)
        default_payload["meta"].pop("db")
        payload["meta"].pop("db")
        self.assertEqual(default_payload, payload)
        self.assertEqual(runtime_status, "")
        self.assertEqual(runtime_head, runtime_commit)


if __name__ == "__main__":
    unittest.main()

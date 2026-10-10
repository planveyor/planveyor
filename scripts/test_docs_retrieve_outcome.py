#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "docs_retrieve_outcome.py"


def _write_query_log(path: Path, cwd: Path) -> None:
    rows = [
        {
            "event_id": "20260502T080000Z-alpha-00000001",
            "ts": "2026-05-02T08:00:00Z",
            "cwd": cwd.as_posix(),
            "corpus": "canon",
            "query": "alpha",
            "hits": 1,
            "files": 1,
        },
        {
            "event_id": "20260502T080001Z-beta-00000002",
            "ts": "2026-05-02T08:00:01Z",
            "cwd": cwd.as_posix(),
            "corpus": "plans",
            "query": "beta",
            "hits": 0,
            "files": 0,
        },
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


class DocsRetrieveOutcomeTests(unittest.TestCase):
    def test_marks_exact_event_id_append_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            query_log = root / "queries.jsonl"
            outcome_log = root / "outcomes.jsonl"
            _write_query_log(query_log, root)

            proc = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SCRIPT),
                    "--query-log",
                    str(query_log),
                    "--outcome-log",
                    str(outcome_log),
                    "--event-id",
                    "20260502T080000Z-alpha-00000001",
                    "--outcome",
                    "used",
                    "--opened-file",
                    "docs/a.md",
                    "--cited-file",
                    "docs/a.md",
                    "--note",
                    "used for plan scope",
                    "--json",
                ],
                cwd=root,
                text=True,
                capture_output=True,
                check=True,
            )

            receipt = json.loads(proc.stdout)
            self.assertTrue(receipt["ok"])
            rows = [json.loads(line) for line in outcome_log.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["query_event_id"], "20260502T080000Z-alpha-00000001")
            self.assertEqual(rows[0]["outcome"], "used")
            self.assertEqual(rows[0]["opened_files"], ["docs/a.md"])
            self.assertEqual(rows[0]["cited_files"], ["docs/a.md"])
            self.assertEqual(rows[0]["query"], "alpha")

    def test_latest_is_scoped_to_current_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            query_log = root / "queries.jsonl"
            outcome_log = root / "outcomes.jsonl"
            _write_query_log(query_log, root)

            subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SCRIPT),
                    "--query-log",
                    str(query_log),
                    "--outcome-log",
                    str(outcome_log),
                    "--latest",
                    "--outcome",
                    "miss",
                ],
                cwd=root,
                text=True,
                capture_output=True,
                check=True,
            )

            row = json.loads(outcome_log.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(row["query_event_id"], "20260502T080001Z-beta-00000002")
            self.assertEqual(row["outcome"], "miss")

    def test_invalid_outcome_and_note_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            query_log = root / "queries.jsonl"
            outcome_log = root / "outcomes.jsonl"
            _write_query_log(query_log, root)

            bad_outcome = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SCRIPT),
                    "--query-log",
                    str(query_log),
                    "--outcome-log",
                    str(outcome_log),
                    "--event-id",
                    "20260502T080000Z-alpha-00000001",
                    "--outcome",
                    "helpful",
                ],
                cwd=root,
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(bad_outcome.returncode, 0)

            bad_note = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SCRIPT),
                    "--query-log",
                    str(query_log),
                    "--outcome-log",
                    str(outcome_log),
                    "--event-id",
                    "20260502T080000Z-alpha-00000001",
                    "--outcome",
                    "used",
                    "--note",
                    "bad\nnote",
                ],
                cwd=root,
                text=True,
                capture_output=True,
            )
            self.assertEqual(bad_note.returncode, 2)


if __name__ == "__main__":
    unittest.main()

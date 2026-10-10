#!/usr/bin/env python3
"""Local timestamp output preserves the session snapshot's UTC fields."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("codex_session_stats.py")


class CodexSessionStatsTimestampTests(unittest.TestCase):
    def test_local_json_kv_and_table_outputs_keep_utc_instants(self) -> None:
        sid = "00000000-0000-0000-0000-000000000001"
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            rollout = home / "sessions" / f"rollout-2026-04-18T15-10-00-{sid}.jsonl"
            rollout.parent.mkdir()
            rollout.write_text(
                json.dumps({"type": "session_meta", "timestamp": "2026-04-18T15:10:00Z", "payload": {"timestamp": "2026-04-18T15:10:00Z", "cwd": tmpdir}})
                + "\n" + json.dumps({"type": "turn_context", "timestamp": "2026-04-18T15:11:00Z", "payload": {"model": "fixture"}}) + "\n",
                encoding="utf-8",
            )
            for zone, created, last in (
                ("UTC", "18.04.2026 15:10:00 +0000", "18.04.2026 15:11:00 +0000"),
                ("Asia/Tokyo", "19.04.2026 00:10:00 +0900", "19.04.2026 00:11:00 +0900"),
            ):
                environment = {**os.environ, "TZ": zone}
                for mode in ("quick", "full"):
                    for fmt in ("json", "kv"):
                        with self.subTest(zone=zone, mode=mode, fmt=fmt):
                            result = subprocess.run(
                                [sys.executable, "-B", str(SCRIPT), "--sid", sid, "--codex-home", str(home), "--mode", mode, "--format", fmt],
                                env=environment, text=True, capture_output=True, check=False, timeout=20,
                            )
                            self.assertEqual(result.returncode, 0, result.stderr)
                            payload = json.loads(result.stdout) if fmt == "json" else dict(line.split("=", 1) for line in result.stdout.splitlines())
                            self.assertEqual(payload["created_utc"], "2026-04-18T15:10:00Z")
                            self.assertEqual(payload["last_utc"], "2026-04-18T15:11:00Z")
                            self.assertEqual(payload["created_local"], created)
                            self.assertEqual(payload["last_local"], last)
                            self.assertEqual(payload["sid"], sid)
                            self.assertNotIn("created_msk", payload)
                            self.assertNotIn("last_msk", payload)
                table = subprocess.run(
                    [sys.executable, "-B", str(SCRIPT), "--list", "--null-sessions", "--codex-home", str(home), "--days", "0"],
                    env=environment, text=True, capture_output=True, check=False, timeout=20,
                )
                self.assertEqual(table.returncode, 0, table.stderr)
                self.assertIn("created_local\tlast_local", table.stdout)
                self.assertIn(created, table.stdout)
                self.assertIn(last, table.stdout)


if __name__ == "__main__":
    unittest.main()

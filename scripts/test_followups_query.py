#!/usr/bin/env python3
"""V2 identity/readback tests for `followups_query`.

Coverage: V2 follow-ups ingress.
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import followups_lint
import followups_query


class FollowupsQueryV2Tests(unittest.TestCase):
    def _write_v2(self, root: Path) -> None:
        row = {
            "priority": "P1", "summary": "Query by immutable identity", "cluster": "process", "to": "coder",
            "status": "open", "plan": None, "why": "verify exact query", "tags": [],
            "item_id": "query-001", "source_ref": "docs/plans/260811_0030_terminal.md#B1",
            "disposition_kind": None, "disposition_ref": None, "disposition_commit_oid": None, "reason": None,
        }
        path = root / "docs/followups/process_followups_master.md"
        path.parent.mkdir(parents=True)
        path.write_text(
            "# Follow-ups\n\n**Schema version:** followups.v2\n\n## Follow-ups (backlog)\n"
            + followups_lint.render_v2_row(row) + "\n",
            encoding="utf-8",
        )

    def test_exact_tuple_filter_returns_v2_record_without_line_authority(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_v2(root)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = followups_query.main(
                    [
                        "ready-candidates", "--project-root", str(root), "--source-ref",
                        "docs/plans/260811_0030_terminal.md#B1", "--item-id", "query-001", "--format", "json",
                    ]
                )
            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["count"], 1)
            row = payload["rows"][0]
            self.assertEqual(row["source_ref"], "docs/plans/260811_0030_terminal.md#B1")
            self.assertEqual(row["item_id"], "query-001")
            self.assertIn("line", row)  # diagnostic only; filters use tuple fields.

    def test_mismatched_tuple_does_not_fall_back_to_summary_or_path_similarity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_v2(root)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = followups_query.main(
                    [
                        "ready-candidates", "--project-root", str(root), "--source-ref",
                        "docs/plans/260811_0030_terminal.md#B1", "--item-id", "query-999", "--format", "json",
                    ]
                )
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(stdout.getvalue())["rows"], [])


if __name__ == "__main__":
    unittest.main()

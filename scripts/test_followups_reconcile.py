#!/usr/bin/env python3
"""V2 reconciliation remains read-only and never infers a disposition.

Coverage: V2 follow-ups ingress.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import followups_lint
import followups_reconcile


class FollowupsReconcileV2Tests(unittest.TestCase):
    def test_apply_does_not_promote_or_handle_v2_row_from_path_or_prose(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = root / "docs/plans/260811_0040_done.md"
            plan.parent.mkdir(parents=True)
            plan.write_text(
                "# plan\n\n**Status:** Done\n\n"
                "planveyor_plan_bundle --commit-ready\n", encoding="utf-8"
            )
            row = {
                "priority": "P1", "summary": "Do not infer handled", "cluster": "process", "to": "coder",
                "status": "open", "plan": None, "why": "prose is not disposition proof", "tags": [],
                "item_id": "reconcile-001", "source_ref": "docs/plans/260811_0040_done.md",
                "disposition_kind": None, "disposition_ref": None, "disposition_commit_oid": None, "reason": None,
            }
            followup = root / "docs/followups/process_followups_master.md"
            followup.parent.mkdir(parents=True)
            followup.write_text(
                "# Follow-ups\n\n**Schema version:** followups.v2\n\n## Follow-ups\n"
                + followups_lint.render_v2_row(row) + "\n", encoding="utf-8"
            )
            before = followup.read_bytes()
            payload = followups_reconcile._apply_candidate_handled(root, None)
            self.assertEqual(followup.read_bytes(), before)
            self.assertEqual(payload["candidate_handled"], [])
            self.assertEqual(payload["external_v2_observed"][0]["item_id"], "reconcile-001")

    def test_legacy_apply_blocks_on_foreign_explicit_v2_integrity_without_mutating_legacy_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = root / "docs/plans/260811_0041_done.md"
            plan.parent.mkdir(parents=True)
            plan.write_text(
                "# plan\n\n**Status:** Done\n\nplanveyor_plan_bundle --commit-ready\n", encoding="utf-8"
            )
            legacy = root / "docs/followups/legacy.md"
            legacy.parent.mkdir(parents=True)
            legacy.write_text(
                "# legacy\n\n**Schema version:** followups.v1\n\n## Follow-ups\n"
                "- P1 [ ] Legacy handled candidate — cluster=process — to=coder — status=promoted "
                "— plan=docs/plans/260811_0041_done.md — why: proof\n",
                encoding="utf-8",
            )
            foreign = root / "docs/followups/foreign.md"
            foreign.write_text(
                "# foreign\n\n**Schema version:** followups.v2\n**Schema version:** followups.v2\n\n## Follow-ups\n",
                encoding="utf-8",
            )
            before = legacy.read_bytes()

            result = followups_reconcile.main(["--project-root", str(root), "--apply", "--format", "json"])

            self.assertEqual(result, 2)
            self.assertEqual(legacy.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

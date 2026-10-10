#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import os
import shlex
import subprocess
import sys
import tempfile
import textwrap
import unittest

try:
    from scripts.test_support.process_contract_fixtures import run_zsh_fixture, temporary_git_root
except ModuleNotFoundError:
    from test_support.process_contract_fixtures import run_zsh_fixture, temporary_git_root


REPO_ROOT = Path(__file__).resolve().parent.parent
PLANVEYOR_SCRIPT = REPO_ROOT / "scripts" / "planveyor.zsh"


class PlanveyorPlanListTests(unittest.TestCase):
    def _run(self, root: Path, command: str) -> subprocess.CompletedProcess[str]:
        shell = f"source {shlex.quote(str(PLANVEYOR_SCRIPT))} && {command}"
        return run_zsh_fixture(
            shell,
            cwd=root,
            path=os.environ.get("PATH", os.defpath),
            pybin=sys.executable,
            check=True,
            capture_output=True,
        )

    def _write_plan(self, root: Path, name: str, body: str) -> None:
        plan_path = root / "docs" / "plans" / name
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(textwrap.dedent(body), encoding="utf-8")

    def test_plan_list_hides_non_executable_ready_for_planner_by_default(self) -> None:
        with temporary_git_root() as tmp:
            root = Path(tmp)
            self._write_plan(
                root,
                "260101_1000_live_planner_item.md",
                """\
                # Plan: live planner item

                **Date:** 2026-01-01
                **Stage:** Stage 1
                **Priority:** P1
                **Plan type:** dev
                **Status:** Ready for Planner

                **Handoff statuses (кто ставит):**
                - `Ready for Planner` - Architect
                - `Ready for Coder` - Planner
                - `Ready for Review` - Coder
                - `Ready for Arch review` - Reviewer

                **Context links (source of truth):**
                - Code draft(s): `docs/code_drafts/live.md`
                """,
            )
            self._write_plan(
                root,
                "260101_1010_parked_umbrella.md",
                """\
                # Plan: parked umbrella

                **Date:** 2026-01-01
                **Stage:** Stage 1
                **Priority:** P1
                **Plan type:** dev
                **Status:** Ready for Planner

                **Handoff statuses (кто ставит):**
                - `Ready for Planner` - Architect
                - `Ready for Coder` - `N/A (parked umbrella)`
                - `Ready for Review` - `N/A (parked umbrella)`
                - `Ready for Arch review` - `N/A (parked umbrella)`

                **Context links (source of truth):**
                - Code draft(s): `N/A (parked umbrella)`

                ## Meta (machine-readable JSON; required for new plans)
                ```json
                {
                  "plan_meta": {
                    "cluster": "process",
                    "tags": ["test"],
                    "phase_overlay": null,
                    "phase_state": "parked",
                    "parent": null,
                    "next_plans": [],
                    "depends_on": [],
                    "followups_out": [],
                    "canon_updates": [],
                    "machine_authority_decision": {
                      "schema_version": "machine_authority_decision.v1",
                      "applicability": "not_applicable",
                      "reason_code": "no_machine_authority_change"
                    }
                  }
                }
                ```
                """,
            )

            default_out = self._run(root, "planveyor_plan_list").stdout
            self.assertIn("260101_1000_live_planner_item.md", default_out)
            self.assertNotIn("260101_1010_parked_umbrella.md", default_out)

            status_out = self._run(root, 'planveyor_plan_list_status "ready for planner"').stdout
            self.assertIn("260101_1000_live_planner_item.md", status_out)
            self.assertNotIn("260101_1010_parked_umbrella.md", status_out)

            included_out = self._run(root, "planveyor_plan_list --include-non-executable").stdout
            self.assertIn("260101_1000_live_planner_item.md", included_out)
            self.assertIn("260101_1010_parked_umbrella.md", included_out)
            self.assertIn("[parked_umbrella]", included_out)

            included_status_out = self._run(
                root,
                'planveyor_plan_list_status "ready for planner" --include-non-executable',
            ).stdout
            self.assertIn("260101_1000_live_planner_item.md", included_status_out)
            self.assertIn("260101_1010_parked_umbrella.md", included_status_out)
            self.assertIn("[parked_umbrella]", included_status_out)


if __name__ == "__main__":
    unittest.main()

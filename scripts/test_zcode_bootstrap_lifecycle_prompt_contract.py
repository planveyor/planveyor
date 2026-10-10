#!/usr/bin/env python3
"""Literal contracts for the public, neutral ZCode transport surface."""

from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MANAGER_INIT = REPO_ROOT / ".zcode" / "commands" / "manager-init.md"
ROLE_AGENT = REPO_ROOT / ".zcode" / "agents" / "planveyor-role-agent.md"
OVERLAY = REPO_ROOT / "docs" / "tools" / "prompts" / "zcode" / "manager_pipeline.md"


class ZCodeBootstrapPromptContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manager_init = MANAGER_INIT.read_text(encoding="utf-8")
        self.role_agent = ROLE_AGENT.read_text(encoding="utf-8")
        self.overlay = OVERLAY.read_text(encoding="utf-8")

    def test_public_artifacts_use_one_neutral_layout(self) -> None:
        self.assertTrue(MANAGER_INIT.is_file())
        self.assertTrue(ROLE_AGENT.is_file())
        self.assertTrue(OVERLAY.is_file())
        self.assertIn("docs/tools/prompts/zcode/manager_pipeline.md", self.manager_init)
        self.assertIn("public ZCode bodies", self.manager_init)
        self.assertIn("name: planveyor-role-agent", self.role_agent)
        self.assertIn("public Manager command", self.role_agent)
        self.assertIn('subagent_type="planveyor-role-agent"', self.overlay)

    def test_manager_init_bootstraps_exact_epoch_before_agents(self) -> None:
        for token in (
            "## Lifecycle bootstrap before any Agent",
            "PROJECT_ROOT",
            "PLANVEYOR_RUNTIME_ROOT",
            "MANAGER_SESSION_ID",
            "TEAM_EPOCH",
            "init_epoch",
            "read_exact_epoch",
            "exact-idempotent",
            "carrier, mtime или agentId",
            "manager_attested_cooperative_lineage",
        ):
            self.assertIn(token, self.manager_init)
        self.assertLess(self.manager_init.index("init_epoch"), self.manager_init.index("не запускай роли"))

    def test_documents_pin_one_interpreter_and_never_exec_helper_directly(self) -> None:
        command = '"$PYBIN" -B "$PLANVEYOR_RUNTIME_ROOT/scripts/zcode_bootstrap_lifecycle.py"'
        self.assertIn('PYBIN="${PYBIN:-python3}"', self.manager_init)
        self.assertIn(command, self.manager_init)
        self.assertIn('PYBIN="${PYBIN:-python3}"', self.overlay)
        self.assertIn(command, self.overlay)
        self.assertIn("Do not call the Python file directly", self.overlay)

    def test_overlay_orders_reservation_promotion_and_work_delivery(self) -> None:
        reserve = self.overlay.index("1. `reserve_agent`")
        pending = self.overlay.index("2. `read_exact_epoch --expected-state pending`")
        init_agent = self.overlay.index("3. `Agent(init envelope only)`")
        promote = self.overlay.index("4. `promote_ack`")
        work = self.overlay.index("5. Only after `verdict=current`")
        self.assertLess(reserve, pending)
        self.assertLess(pending, init_agent)
        self.assertLess(init_agent, promote)
        self.assertLess(promote, work)
        self.assertIn("abandon_pending", self.overlay)
        self.assertIn("greater\ngeneration and a new nonce", self.overlay)
        self.assertIn("zcode_bootstrap_lifecycle_not_current", self.overlay)

    def test_overlay_keeps_manifest_and_censor_admission_explicit(self) -> None:
        for token in (
            'root_class="project"',
            'root_class="tooling"',
            '"team_epoch"',
            '"read_contracts"',
            "acknowledgement_digest",
            "verified_handoff",
            "CENSOR",
            "reviewer_code_risk",
            "reviewer_code_contracts",
            "live_zcode_state=not_run",
        ):
            self.assertIn(token, self.overlay)
        self.assertIn("Manager-supplied `acknowledgement_digest` is forbidden", self.overlay)
        self.assertIn("do not automatically resend earlier work", self.overlay)

    def test_public_definition_keeps_neutral_contracts(self) -> None:
        self.assertIn("Do not infer a project root", self.role_agent)
        self.assertIn("A result from this\nrole is never Owner approval", self.role_agent)


if __name__ == "__main__":
    unittest.main()

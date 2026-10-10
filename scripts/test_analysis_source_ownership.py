#!/usr/bin/env python3
"""Ownership checks for the shipped analysis corpus and target-local carrier."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from authority_bootstrap_test_support import run_python_stdin  # noqa: E402
import contract_authority_context as authority  # noqa: E402
from test_contract_authority_support import AuthorityFixture  # noqa: E402


ROLES = ("architect", "planner", "coder", "reviewer")
ANALYSIS_PATH = "docs/playbooks/analysis_wave.md"
SOURCE_MARKERS = (
    "Analysis logical locator `docs/playbooks/analysis_wave.md` читается из root\n  shared corpus для content IDs `default` и `planveyor`.",
    "`target-local` может выбрать consumer-owned carrier только когда его path,\n  owner и current digest явно объявлены selected target contract. Unknown,\n  missing, malformed или stale selection — gap/reroute.",
    "Не используй target mirror, saved copy, prior map или guessed path как\n  fallback. Role не создаёт source map и не восстанавливает carrier по памяти.",
)


class AnalysisSourceOwnershipTests(unittest.TestCase):
    def _target_read(self, fixture: AuthorityFixture) -> subprocess.CompletedProcess[str]:
        return run_python_stdin(
            fixture,
            f"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(os.environ["PLANVEYOR_ROOT"]) / "scripts"))
import contract_authority_context as authority
authority.ENGAGED_ADMISSION_COMPLETE = True

context = authority.resolve_top_level_context(Path.cwd())
body = authority.read_declared_text(context, {ANALYSIS_PATH!r}, "analysis source")
print(json.dumps({{
    "state": context.state,
    "contract_root": str(context.contract_root),
    "body": body,
}}, sort_keys=True))
""",
            environment=fixture.environment(),
            timeout=90,
        )

    def test_every_shipped_role_declares_shared_root_then_declared_target_local(self) -> None:
        for role in ROLES:
            relative = f"docs/roles/{role}.md"
            text = (ROOT / relative).read_text(encoding="utf-8")
            with self.subTest(role=role):
                start = text.index("## Source of truth / precedence")
                end = text.index("\n## Shared-core rule", start)
                section = text[start:end]
                self.assertEqual([section.index(marker) for marker in SOURCE_MARKERS], sorted(section.index(marker) for marker in SOURCE_MARKERS))
                for marker in SOURCE_MARKERS:
                    self.assertIn(marker, section)

    def test_analysis_wave_is_the_shipped_schema_and_not_a_profile_compatibility_copy(self) -> None:
        text = (ROOT / ANALYSIS_PATH).read_text(encoding="utf-8")
        for marker in (
            "# Playbook: Analysis Wave",
            "## Analysis pack V1",
            "| Field | Owner / writer | Required when | Meaning |",
            "`analysis_subject`",
            "`route_recommendation`",
            "## Роли",
        ):
            self.assertIn(marker, text)
        self.assertFalse((ROOT / "docs/playbooks/profiles").exists())
        self.assertFalse((ROOT / "docs/roles/profiles").exists())

    def test_declared_target_local_analysis_source_is_positive_then_rejects_missing_and_malformed_selection(self) -> None:
        with AuthorityFixture(identity="planveyor") as fixture:
            fixture.activate_planveyor(
                authority.STATIC_PLANVEYOR_MERGE_REQUIRED_ENGAGED_PATHS,
                contract_root="contract",
            )
            selected = fixture.target_root / "contract" / ANALYSIS_PATH
            selected.write_text("# TARGET-LOCAL ANALYSIS BODY\n", encoding="utf-8")
            positive = self._target_read(fixture)

            mirror = fixture.target_root / ANALYSIS_PATH
            mirror.parent.mkdir(parents=True, exist_ok=True)
            mirror.write_text("# ROOT MIRROR MUST NOT BE READ\n", encoding="utf-8")
            selected.unlink()
            missing = self._target_read(fixture)

            marker = fixture.target_root / "docs/_meta/planveyor_contract_authority.v1.json"
            marker.write_text("{", encoding="utf-8")
            malformed = self._target_read(fixture)

        self.assertEqual(positive.returncode, 0, positive.stdout + positive.stderr)
        payload = json.loads(positive.stdout)
        self.assertEqual(payload["state"], "engaged")
        self.assertEqual(payload["body"], "# TARGET-LOCAL ANALYSIS BODY\n")
        self.assertNotEqual(missing.returncode, 0)
        self.assertNotIn("ROOT MIRROR MUST NOT BE READ", missing.stdout + missing.stderr)
        self.assertNotEqual(malformed.returncode, 0)


if __name__ == "__main__":
    unittest.main()

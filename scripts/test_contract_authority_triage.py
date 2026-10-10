"""Triage binds vocabulary and validates the complete batch before mutation."""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import contract_authority_context as authority
from authority_bootstrap_test_support import run_python_entry
from test_contract_authority_support import AuthorityFixture, commit_all, tree_snapshot, write


class AuthorityTriageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = AuthorityFixture()
        self.addCleanup(self.fixture.close)
        self._enable_isolated_admission()
        self.fixture.activate_planveyor(authority.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS, overrides={
            "docs/_meta/plan_vocab.json": json.dumps({"clusters": {
                "canonical": ["custom"], "deprecated_aliases": {"old_custom": "custom"},
            }}),
        })
        self.root = self.fixture.target_root
        self.inbox = "docs/followups/260101_0000_inbox.md"
        self.master = "docs/followups/custom_followups_master.md"
        write(self.root, "docs/followups/index.md", f"| `{self.master}` | Custom | clusters=old_custom |\n")
        write(self.root, self.master, "# Master\n\n## Follow-ups (backlog)\n")

    def _enable_isolated_admission(self) -> None:
        context_path = self.fixture.runtime_root / "scripts" / "contract_authority_context.py"
        original = context_path.read_text(encoding="utf-8")
        revised, substitutions = re.subn(
            r"ENGAGED_ADMISSION_COMPLETE: Final\[bool\] = (?:True|False)",
            "ENGAGED_ADMISSION_COMPLETE: Final[bool] = True",
            original,
            count=1,
        )
        self.assertEqual(substitutions, 1, "copied runtime must expose exactly one admission gate")
        if revised != original:
            context_path.write_text(revised, encoding="utf-8")
            self.fixture.runtime_commit = commit_all(
                self.fixture.runtime_root,
                "test-only engaged admission",
            )

    def invoke(self, *arguments: str):
        return run_python_entry(
            self.fixture,
            self.fixture.runtime_root / "scripts" / "followups_triage.py",
            "--file",
            self.inbox,
            *arguments,
            cwd=self.root,
            environment=self.fixture.environment(),
        )

    def test_current_vocabulary_alias_and_custom_cluster_do_not_fallback(self) -> None:
        vocabulary_path = self.root / "docs/_meta/plan_vocab.json"
        vocabulary = json.loads(vocabulary_path.read_text(encoding="utf-8"))
        vocabulary["clusters"]["deprecated_aliases"]["new_custom"] = "custom"
        write(self.root, "docs/_meta/plan_vocab.json", json.dumps(vocabulary, sort_keys=True) + "\n")
        write(self.root, self.inbox, "# Inbox\n\n## Follow-ups (backlog)\n- P2 [ ] Custom issue — cluster=new_custom\n")
        before = tree_snapshot(self.root)
        completed = self.invoke("--dry-run")
        self.assertEqual((completed.returncode, completed.stderr), (0, ""))
        self.assertIn(self.master, completed.stdout)
        self.assertIn("- route_fallback: 0", completed.stdout)
        self.assertEqual(tree_snapshot(self.root), before)

    def test_late_unknown_source_rejects_whole_batch_before_write(self) -> None:
        write(self.root, self.inbox, "# Inbox\n\n## Follow-ups (backlog)\n"
              "- P2 [ ] Valid first — cluster=custom\n- P2 [ ] Invalid last — cluster=vehicles\n")
        before = tree_snapshot(self.root)
        completed = self.invoke("--apply")
        self.assertEqual(completed.returncode, 2)
        self.assertIn("triage_cluster_unknown", completed.stderr)
        self.assertEqual(tree_snapshot(self.root), before)

    def test_missing_route_does_not_create_master(self) -> None:
        write(self.root, self.inbox, "# Inbox\n\n## Follow-ups (backlog)\n- P2 [ ] Custom issue — cluster=custom\n")
        write(self.root, "docs/followups/index.md", "# No routes\n")
        before = tree_snapshot(self.root)
        completed = self.invoke("--apply")
        self.assertEqual(completed.returncode, 2)
        self.assertIn("triage_route_missing", completed.stderr)
        self.assertEqual(tree_snapshot(self.root), before)

    def test_unknown_routing_key_rejects_before_any_write(self) -> None:
        write(self.root, self.inbox, "# Inbox\n\n## Follow-ups (backlog)\n- P2 [ ] Custom issue — cluster=custom\n")
        write(self.root, "docs/followups/index.md", f"| `{self.master}` | Custom | clusters=custom,vehicles |\n")
        before = tree_snapshot(self.root)
        completed = self.invoke("--apply")
        self.assertEqual(completed.returncode, 2)
        self.assertIn("triage_route_unknown", completed.stderr)
        self.assertEqual(tree_snapshot(self.root), before)

    def test_explicit_traversal_cannot_read_or_mark_outside_followups(self) -> None:
        (self.root / "docs" / "outside.md").mkdir(parents=True)
        self.inbox = "docs/followups/../outside.md"
        before = tree_snapshot(self.root)
        completed = self.invoke("--apply")
        self.assertEqual(completed.returncode, 2)
        self.assertIn("direct followups carrier", completed.stderr)
        self.assertEqual(tree_snapshot(self.root), before)


if __name__ == "__main__":
    unittest.main()

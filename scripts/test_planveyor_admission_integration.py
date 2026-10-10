#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import plan_lint
from scripts import plan_status_oracle
from scripts.test_contract_authority_support import AuthorityFixture, commit_all, write


class PlanveyorAdmissionIntegrationTests(unittest.TestCase):
    """Exercise the real lint admission through the supported process facade."""

    def _write_downstream_fixture(
        self,
        root: Path,
        *,
        stem: str,
        include_carrier: bool,
    ) -> tuple[Path, dict[str, object], dict[str, object]]:
        plan_rel = f"docs/plans/{stem}.md"
        draft_rel = f"docs/code_drafts/{stem}__code_draft.md"
        target_rel = "scripts/machine_authority_fixture.py"
        decision = {
            "schema_version": plan_status_oracle.MACHINE_AUTHORITY_DECISION_SCHEMA,
            "applicability": "not_applicable",
            "reason_code": "no_machine_authority_change",
        }
        plan_meta: dict[str, object] = {
            "cluster": "process",
            "tags": [],
            "required_manager_mode": "either",
            "phase_overlay": None,
            "phase_state": None,
            "parent": None,
            "next_plans": [],
            "depends_on": [],
            "followups_out": [],
            "canon_updates": [],
        }
        if include_carrier:
            plan_meta["machine_authority_decision"] = decision
        draft_meta = {
            "code_draft_meta": {
                "plan": plan_rel,
                "cluster": "process",
                "targets": [{"path": target_rel, "kind": "py"}],
                "deleted_paths": [],
                "machine_authority_decision_ref": {
                    "applicability": "not_applicable",
                    "reason_code": "no_machine_authority_change",
                    "carrier_sha256": plan_status_oracle.machine_authority_decision_sha256(
                        decision
                    ),
                },
            }
        }
        target = root / target_rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# machine-authority fixture\n", encoding="utf-8")
        draft = root / draft_rel
        draft.parent.mkdir(parents=True, exist_ok=True)
        draft.write_text(
            "# Code draft: admission fixture\n\n"
            "**Status:** Planner finalized\n\n"
            "## Meta (machine-readable JSON)\n"
            "```json\n"
            + json.dumps(draft_meta, ensure_ascii=False, indent=2)
            + "\n```\n",
            encoding="utf-8",
        )
        plan = root / plan_rel
        plan.parent.mkdir(parents=True, exist_ok=True)
        plan.write_text(
            "\n".join(
                [
                    "# Plan: machine-authority admission fixture",
                    "",
                    "**Date:** 2026-09-26 12:00 MSK",
                    "**Stage:** Stage 2",
                    "**Priority:** P1",
                    "**Plan type:** dev",
                    "**Status:** Ready for Coder",
                    "",
                    "**Context links (source of truth):**",
                    f"- Code draft(s): `{draft_rel}`",
                    "",
                    "## Meta (machine-readable JSON; required for new plans)",
                    "```json",
                    json.dumps({"plan_meta": plan_meta}, ensure_ascii=False, indent=2),
                    "```",
                    "",
                    "## Как я понял задачу",
                    "",
                    "Фикстура проверяет реальный downstream admission через публичный Planveyor facade.",
                    "",
                    "## Problem",
                    "",
                    "1. Нужна проверка carrier и tagged code-draft ref.",
                    "",
                    "## Solution (high level)",
                    "",
                    "1. Использовать один N/A carrier с совпадающим digest.",
                    "",
                    "## Decisions (final)",
                    "",
                    "- ✅ Final: fixture остаётся локальной и не меняет queue state.",
                    "",
                    "## Scope",
                    "",
                    "- Проверить admission fixture.",
                    "",
                    "## Out of scope",
                    "",
                    "- Runtime UI не входит в fixture.",
                    "",
                    "## Follow-ups (deferred)",
                    "",
                    "- none",
                    "",
                    "## Rollout packet handoff",
                    "",
                    "- Role: `N/A (why=fixture)`",
                    "- Packet path: `N/A`",
                    "- Target repo: `N/A`",
                    "- Suggested target plan slug: `N/A`",
                    "- Queue after import: `N/A`",
                    "",
                    "## Close-out routing",
                    "",
                    "- Roadmap/queue sync: `N/A (why=fixture)`",
                    "- Follow-up sync: `none`",
                    "- Next bounded slice: `none (fixture)`",
                    "- Terminal outcome: yes (fixture)",
                    "",
                    "## Mechanism coverage",
                    "",
                    "- `N/A (why=fixture)`",
                    "",
                    "## Risks / Open questions (summary)",
                    "",
                    "- none",
                    "",
                    "## Changes (by area)",
                    "",
                    "- Scripts/tools:",
                    f"  - `{target_rel}`",
                    "",
                    "## Acceptance criteria / DoD",
                    "",
                    "- [ ] Реальный lint принимает fixture с согласованным N/A carrier/ref.",
                    "",
                    "## Tests",
                    "",
                    "### Critical runtime invariants (required for risky UI/layout/visibility/default-state/access tasks)",
                    "",
                    "- `N/A (why=fixture)`",
                    "",
                    "### Что написать / поправить",
                    "",
                    "- `scripts/test_planveyor_admission_integration.py`",
                    "",
                    "### Что прогнать",
                    "",
                    "- `python3 scripts/test_planveyor_admission_integration.py`",
                    "",
                    "## Commands",
                    "",
                    "- `python3 scripts/test_planveyor_admission_integration.py`",
                    "",
                    "## Verification rerun / exec handoff",
                    "",
                    "- Mode: `N/A (why=fixture)`",
                    "- Context source: `N/A`",
                    "- Prompt: `N/A`",
                    "- Command: `N/A`",
                    "- Expected artifact: `N/A`",
                    "",
                    "## Evidence (chronological, append-only)",
                    "",
                    "- [2026-09-26 12:00 MSK] (Planner) Fixture materialized.",
                    "",
                    "## Review artifacts",
                    "",
                    "- Code review (primary): `docs/code_reviews/fixture.md`",
                    "",
                    "## Documentation impact / provenance",
                    "",
                    "- Source docs used: `N/A (why=fixture)`.",
                    "- Synchronous doc/registry targets: `N/A (why=fixture)`.",
                    "- Post-merge canon updates: `N/A (why=fixture)`.",
                    "- Deferred documentation follow-ups: `N/A (why=fixture)`.",
                    "- Provenance refs: fixture.",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return plan, plan_meta, decision

    def _queue_state_snapshot(self, root: Path) -> dict[str, bytes | None]:
        paths = (
            ".planveyor.planqueue.json",
            ".planveyor.planqueue.log",
            ".planveyor.planqueue.lock",
            ".planveyor.planqueue.txn.json",
            ".planveyor.planpath",
            ".planveyor.planpath.log",
        )
        return {
            rel: (root / rel).read_bytes() if (root / rel).exists() else None
            for rel in paths
        }

    @staticmethod
    def _state_tree_snapshot(root: Path) -> dict[str, tuple[str, bytes | str]]:
        if not root.exists():
            return {}
        snapshot: dict[str, tuple[str, bytes | str]] = {}
        for path in sorted(root.rglob("*")):
            rel = path.relative_to(root).as_posix()
            if path.is_symlink():
                snapshot[rel] = ("symlink", path.readlink().as_posix())
            elif path.is_file():
                snapshot[rel] = ("file", path.read_bytes())
        return snapshot

    def _run_public_lint(
        self,
        entry: Path,
        root: Path,
        environment: dict[str, str],
        rel_path: str,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                str(entry),
                "--project",
                str(root),
                "planveyor_plan_lint",
                rel_path,
            ],
            cwd=root,
            env=environment,
            stdin=subprocess.DEVNULL,
            text=True,
            capture_output=True,
            check=False,
            timeout=120,
        )

    def test_real_downstream_na_admission_and_public_refusal_are_state_safe(self) -> None:
        with AuthorityFixture(identity="planveyor") as fixture:
            entry = write(
                fixture.runtime_root,
                "bin/planveyor",
                (REPO_ROOT / "bin" / "planveyor").read_bytes(),
                executable=True,
            )
            commit_all(fixture.runtime_root, "public admission facade")
            root = fixture.target_root
            vocab = root / "docs/_meta/plan_vocab.json"
            vocab.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO_ROOT / "docs/_meta/plan_vocab.json", vocab)
            valid, valid_meta, decision = self._write_downstream_fixture(
                root,
                stem="260926_1200_na_admission",
                include_carrier=True,
            )
            draft = root / "docs/code_drafts/260926_1200_na_admission__code_draft.md"
            valid_text = valid.read_text(encoding="utf-8")
            valid_draft_bytes = draft.read_bytes()
            write(root, ".planveyor.pybin", f"{Path(sys.executable).resolve()}\n")
            commit_all(root, "valid downstream admission fixture")

            environment = fixture.environment()
            state_root = fixture.root / "state"
            state_root.mkdir()
            environment["PLANVEYOR_STATE_ROOT"] = str(state_root)
            original_lint = plan_lint.lint_plan
            with mock.patch.object(plan_lint, "lint_plan", wraps=original_lint) as observed:
                valid_findings = plan_lint.lint_plan(valid)
                valid_public = self._run_public_lint(
                    entry,
                    root,
                    environment,
                    valid.relative_to(root).as_posix(),
                )
                queue_after_valid = self._queue_state_snapshot(root)
                state_after_valid = self._state_tree_snapshot(state_root)
                rejected, rejected_meta, _ = self._write_downstream_fixture(
                    root,
                    stem="260926_1200_na_admission",
                    include_carrier=False,
                )
                rejected_findings = plan_lint.lint_plan(rejected)
            self.assertEqual(observed.call_count, 2)
            self.assertEqual(valid, rejected)
            self.assertEqual(
                valid_meta,
                {**rejected_meta, "machine_authority_decision": decision},
            )
            valid_meta_block = json.dumps({"plan_meta": valid_meta}, ensure_ascii=False, indent=2)
            rejected_meta_block = json.dumps({"plan_meta": rejected_meta}, ensure_ascii=False, indent=2)
            rejected_text = rejected.read_text(encoding="utf-8")
            self.assertEqual(valid_text.count(valid_meta_block), 1)
            self.assertEqual(rejected_text.count(rejected_meta_block), 1)
            self.assertEqual(rejected_text, valid_text.replace(valid_meta_block, rejected_meta_block))
            self.assertEqual(draft.read_bytes(), valid_draft_bytes)
            self.assertEqual([item for item in valid_findings if item.severity == "ERROR"], [])
            rejected_errors = [item.message for item in rejected_findings if item.severity == "ERROR"]
            self.assertEqual(len(rejected_errors), 1, rejected_errors)
            self.assertIn("missing_required_carrier", rejected_errors[0])

            commit_all(root, "missing carrier refusal fixture")
            rejected_public = self._run_public_lint(
                entry,
                root,
                environment,
                rejected.relative_to(root).as_posix(),
            )
            after = self._queue_state_snapshot(root)
            state_after_rejection = self._state_tree_snapshot(state_root)

        self.assertEqual(valid_public.returncode, 0, valid_public.stdout + valid_public.stderr)
        self.assertEqual(rejected_public.returncode, 1, rejected_public.stdout + rejected_public.stderr)
        rejected_output = rejected_public.stdout + rejected_public.stderr
        error_lines = [line for line in rejected_output.splitlines() if line.startswith("ERROR:")]
        self.assertEqual(len(error_lines), 1, rejected_output)
        self.assertIn("missing_required_carrier", error_lines[0])
        self.assertEqual(after, queue_after_valid)
        self.assertEqual(state_after_rejection, state_after_valid)


if __name__ == "__main__":
    unittest.main()

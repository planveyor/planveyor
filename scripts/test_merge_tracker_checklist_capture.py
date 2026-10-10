#!/usr/bin/env python3
"""Pre-write capture coverage for engaged merge-tracker checklist rendering."""

from __future__ import annotations

import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parent.parent
PLANVEYOR_SCRIPT = REPO_ROOT / "scripts" / "planveyor.zsh"
GENERATION = "a" * 64


class MergeTrackerChecklistCaptureTests(unittest.TestCase):
    def _run_init(
        self,
        root: Path,
        tracker: Path,
        backup: Path,
        *,
        step_function: str,
    ) -> subprocess.CompletedProcess[str]:
        program = f"""
source {shlex.quote(str(PLANVEYOR_SCRIPT))}
FIXTURE_ROOT={shlex.quote(str(root))}
TRACKER_PATH={shlex.quote(str(tracker))}
BACKUP_PATH={shlex.quote(str(backup))}
FIXTURE_GENERATION={GENERATION}
_planveyor_authority_context_for_reader() {{ print -r -- fixture-context; }}
_planveyor_authority_context_bindings() {{
  printf '%s\\t%s\\t%s\\t\\n' engaged "$FIXTURE_ROOT" "$FIXTURE_GENERATION"
}}
_planveyor_get_range_base() {{ print -r -- base; }}
_planveyor_get_range_head() {{ print -r -- head; }}
planveyor_range_merge() {{ print -r -- ''; }}
_planveyor_root() {{ print -r -- "$FIXTURE_ROOT"; }}
_planveyor_merge_policy_mode() {{ print -r -- engaged; }}
_planveyor_merge_policy_metadata() {{
  print -r -- POLICY_SCHEMA=planveyor.merge_gate_policy.v1
  print -r -- POLICY_SHA256=fixture-policy-sha
  print -r -- AUTHORITY_GENERATION="$FIXTURE_GENERATION"
}}
_planveyor_merge_policy_step_keys() {{
{step_function}
}}
# This suite isolates capture ordering; real guards have separate coverage.
_planveyor_merge_policy_validate_tracker() {{ return 0; }}
_planveyor_authority_before_effect_json() {{ return 0; }}
_planveyor_merge_tracker_path() {{ print -r -- "$TRACKER_PATH"; }}
_planveyor_merge_tracker_backup_path() {{ print -r -- "$BACKUP_PATH"; }}
_planveyor_now() {{ print -r -- fixture-now; }}
_planveyor_repo_profile_id() {{ print -r -- planveyor; }}
_planveyor_sha7() {{ print -r -- "${{1}}"; }}
planveyor_merge_tracker_init
rc=$?
print -r -- "C03_MERGE_TMP=$TMPDIR|$TMPPREFIX"
print -r -- "INIT_EXIT=$rc"
exit "$rc"
"""
        with tempfile.TemporaryDirectory(
            prefix="planveyor-merge-checklist-child-",
            dir=root.parent,
        ) as temporary_child:
            child_tmp = Path(temporary_child).resolve()
            environment = os.environ.copy()
            environment.update(
                TMPDIR=str(child_tmp),
                TMPPREFIX=str(child_tmp / "zsh"),
            )
            return subprocess.run(
                ["/bin/zsh", "-f", "-c", program],
                text=True,
                capture_output=True,
                env=environment,
                check=False,
            )

    def _assert_child_tmp_pair(self, result: subprocess.CompletedProcess[str], root: Path) -> None:
        observed = next(
            line.removeprefix("C03_MERGE_TMP=")
            for line in result.stdout.splitlines()
            if line.startswith("C03_MERGE_TMP=")
        )
        tmpdir, tmpprefix = observed.split("|")
        tmp_path = Path(tmpdir)
        self.assertTrue(tmp_path.is_absolute())
        self.assertEqual(tmp_path.parent, root.parent.resolve())
        self.assertTrue(tmp_path.name.startswith("planveyor-merge-checklist-child-"))
        self.assertEqual(tmpprefix, f"{tmp_path}/zsh")

    def test_engaged_step_key_failure_happens_before_new_or_existing_tracker_effects(self) -> None:
        failing_steps = "  print -u2 -r -- fixture-step-key-failure\n  return 77"
        with tempfile.TemporaryDirectory(prefix="planveyor_merge_checklist_capture_") as tmpdir:
            root = Path(tmpdir)
            fresh_tracker = root / ".planveyor.merge_tracker.md"
            fresh_backup = root / ".planveyor.merge_tracker.previous.md"
            fresh = self._run_init(
                root,
                fresh_tracker,
                fresh_backup,
                step_function=failing_steps,
            )
            self.assertEqual(fresh.returncode, 77, fresh.stderr)
            self.assertIn("fixture-step-key-failure", fresh.stderr)
            self.assertIn("INIT_EXIT=77", fresh.stdout)
            self._assert_child_tmp_pair(fresh, root)
            self.assertFalse(fresh_tracker.exists())
            self.assertFalse(fresh_backup.exists())
            self.assertNotIn("Saved:", fresh.stderr)
            self.assertNotIn("Backed up previous tracker:", fresh.stderr)

            existing_tracker = root / "existing.md"
            existing_backup = root / "existing.previous.md"
            original = b"existing tracker bytes\n"
            existing_tracker.write_bytes(original)
            existing = self._run_init(
                root,
                existing_tracker,
                existing_backup,
                step_function=failing_steps,
            )
            self.assertEqual(existing.returncode, 77, existing.stderr)
            self._assert_child_tmp_pair(existing, root)
            self.assertEqual(existing_tracker.read_bytes(), original)
            self.assertFalse(existing_backup.exists())
            self.assertNotIn("Saved:", existing.stderr)
            self.assertNotIn("Backed up previous tracker:", existing.stderr)

    def test_engaged_captured_checklist_renders_normally(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_merge_checklist_capture_") as tmpdir:
            root = Path(tmpdir)
            tracker = root / ".planveyor.merge_tracker.md"
            backup = root / ".planveyor.merge_tracker.previous.md"
            result = self._run_init(
                root,
                tracker,
                backup,
                step_function="  print -r -- step:review_range\n  print -r -- step:ready_to_push",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("INIT_EXIT=0", result.stdout)
            self._assert_child_tmp_pair(result, root)
            self.assertTrue(tracker.is_file())
            self.assertFalse(backup.exists())
            self.assertIn("POLICY_SCHEMA=planveyor.merge_gate_policy.v1\n", tracker.read_text(encoding="utf-8"))
            self.assertIn(
                "- [ ] step:review_range\n- [ ] step:ready_to_push\n## Notes\n",
                tracker.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Real API4 fixture regressions at merge tracker and closeout effects."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import unittest

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import contract_authority_context as authority
from authority_bootstrap_test_support import run_python_entry
from test_contract_authority_support import (
    AuthorityFixture,
    commit_all,
    git,
    planveyor_merge_gate_policy,
    tree_snapshot,
)


def fixture_policy() -> bytes:
    supplied = os.environ.get("PLANVEYOR_TEST_MERGE_POLICY_DATUM")
    return Path(supplied).read_bytes() if supplied else planveyor_merge_gate_policy()


CLOSEOUT_PROBE = r'''
import json, pathlib, subprocess, sys
import merge_gate_policy as policy
import post_merge_ready_to_push_closeout as closeout

root = pathlib.Path(sys.argv[1])
mode = sys.argv[2]
events = []
tracker = root / '.planveyor.merge_tracker.md'
if mode == 'tracker_switch':
    first, second = root / 'first', root / 'second'
    first.mkdir(); second.mkdir()
    alias = root / 'selected'
    alias.symlink_to(first, target_is_directory=True)
    tracker = alias / 'tracker.md'

def bind_tracker():
    context, datum = policy.policy_for_root(root)
    tracker.write_text(
        f'POLICY_SCHEMA={policy.POLICY_SCHEMA}\nPOLICY_SHA256={datum.raw_sha256}\n'
        f'AUTHORITY_GENERATION={context.generation_sha256}\n- [ ] step:ready_to_push\n')
    return context.generation_sha256, datum.raw_sha256

old_generation, old_policy = bind_tracker()
new_generation, new_policy = old_generation, old_policy
original_tracker = tracker.read_bytes()
if mode == 'tracker_switch':
    (second / 'tracker.md').write_bytes(original_tracker)

def git(*arguments):
    return subprocess.check_output([
        'git', '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false',
        '-C', str(root), *arguments], text=True).strip()

def rebind():
    global new_generation, new_policy
    path = root / policy.POLICY_PATH
    path.write_bytes(path.read_bytes() + b'\n')
    git('add', '--', policy.POLICY_PATH)
    git('commit', '-qm', 'fixture coherent policy change')
    selector_path = root / policy.authority._snapshot.MARKER_PATH
    selector = json.loads(selector_path.read_text())
    selector['required_runtime_api'] = {'minimum': 4, 'maximum': 5}
    selector_path.write_text(json.dumps(selector, sort_keys=True) + '\n')
    new_generation, new_policy = bind_tracker()

real_report = closeout.merge_bundle_report.build_report
def report(*args, **kwargs):
    if mode == 'report_rebind':
        rebind()
        return real_report(*args, **kwargs)
    return {'status': 'ok', 'tracker': {'current_step': 'step:ready_to_push',
        'steps': [{'key': 'step:ready_to_push', 'checked': False}]},
        'range': {'base_short': 'aaaaaaa', 'head_short': 'bbbbbbb', 'range': 'a..b'},
        'git_status': {}}

def before_tick(**kwargs):
    if mode == 'rebind':
        rebind()
    elif mode == 'tracker_switch':
        alias.unlink()
        alias.symlink_to(second, target_is_directory=True)
    return [], None

class StopProbe(Exception):
    pass

def tick(path):
    events.append('tick_reached')
    raise StopProbe('stop before tick write, receipt and closeout commit')

closeout.merge_bundle_report.build_report = report
closeout._risk_packet_preexisting_errors = before_tick
closeout._tick_ready_step = tick
try:
    result = closeout.close_ready_to_push(root, tracker)
except StopProbe:
    result = {'probe': 'stopped_at_tick'}
except (policy.MergeGatePolicyError, policy.authority.ContractAuthorityError) as exc:
    result = {'rejection': exc.reason_code}
print(json.dumps({'mode': mode, 'events': events, 'result': result,
    'old_generation': old_generation, 'new_generation': new_generation,
    'old_policy': old_policy, 'new_policy': new_policy,
    'ready_unchecked': b'- [ ] step:ready_to_push' in tracker.read_bytes()}))
'''


ROOT_ALIAS_PROBE = r'''
import contextlib, io, json, pathlib, subprocess, sys
import merge_gate_policy as policy
import merge_bundle_report as bundle_report
import post_merge_ready_to_push_closeout as closeout

root = pathlib.Path(sys.argv[1])
mode = sys.argv[2]
context, datum = policy.policy_for_root(root)
tracker = root / '.planveyor.merge_tracker.md'
tracker.write_text(
    f'POLICY_SCHEMA={policy.POLICY_SCHEMA}\nPOLICY_SHA256={datum.raw_sha256}\n'
    f'AUTHORITY_GENERATION={context.generation_sha256}\n- [ ] step:ready_to_push\n')
original = tracker.read_bytes()
alias = root.parent / 'stable-root-alias'
alias.symlink_to(root, target_is_directory=True)

def git(*args):
    return subprocess.check_output(['git', '-C', str(root), *args])

before_git = [git('rev-parse', 'HEAD'), git('ls-files', '--stage', '-z'),
              git('status', '--porcelain=v1', '-z', '--untracked-files=all')]
rows = []
events = []
if mode == 'tick':
    # Exercise production report admission and the final closeout validator,
    # isolating the green report body and stopping before a real tick write.
    def report(selected_root, selected_tracker=None, **kwargs):
        policy.validate_tracker_for_root(
            selected_root, selected_tracker, expected_binding=kwargs.get('merge_binding'))
        events.append('report_admitted')
        return {'status': 'ok', 'tracker': {'current_step': 'step:ready_to_push',
            'steps': [{'key': 'step:ready_to_push', 'checked': False}]},
            'range': {'base_short': 'aaaaaaa', 'head_short': 'bbbbbbb', 'range': 'a..b'},
            'git_status': {}}
    class StopProbe(Exception):
        pass
    def tick(selected_tracker):
        assert selected_tracker.resolve() == tracker
        events.append('tick_reached')
        raise StopProbe()
    closeout.merge_bundle_report.build_report = report
    closeout._risk_packet_preexisting_errors = lambda **kwargs: ([], None)
    closeout._tick_ready_step = tick

for spelling in (root, alias):
    for relative in (False, True):
        selected_tracker = pathlib.Path('.planveyor.merge_tracker.md') if relative else None
        initial = policy.validate_tracker_for_root(spelling, selected_tracker)
        events.clear()
        if mode == 'cli':
            # All production validators, report and mutators remain untouched.
            # Assert a red fixture before invoking the real CLI entry point.
            direct_report = bundle_report.build_report(spelling, selected_tracker)
            assert direct_report['status'] != 'ok'
            argv = ['--root', str(spelling), '--format', 'json']
            if relative:
                argv.extend(['--tracker', str(selected_tracker)])
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = closeout.main(argv)
            result = {'rc': rc, 'stdout': out.getvalue(), 'stderr': err.getvalue()}
        else:
            try:
                result = closeout.close_ready_to_push(spelling, selected_tracker)
            except StopProbe:
                result = {'probe': 'stopped_before_write'}
            except (policy.MergeGatePolicyError, policy.authority.ContractAuthorityError) as exc:
                result = {'rejection': exc.reason_code}
        rows.append({'alias': spelling == alias, 'relative_tracker': relative,
                     'initial_admission': initial is not None, 'events': list(events), 'result': result})

assert tracker.read_bytes() == original
assert alias.readlink() == root
assert policy.policy_for_root(root)[0].generation_sha256 == context.generation_sha256
assert before_git == [git('rev-parse', 'HEAD'), git('ls-files', '--stage', '-z'),
                      git('status', '--porcelain=v1', '-z', '--untracked-files=all')]
print(json.dumps({'mode': mode, 'rows': rows, 'tracker_generation_alias_git_unchanged': True}))
'''


class MergePolicyEffectBoundaryTests(unittest.TestCase):
    def _activate(self, fixture: AuthorityFixture) -> None:
        fixture.activate_planveyor(
            authority.STATIC_PLANVEYOR_MERGE_REQUIRED_ENGAGED_PATHS,
            required_runtime_api=(5, 5), merge_policy=fixture_policy(),
        )
        head = git(fixture.target_root, "rev-parse", "HEAD")
        for name in ("base", "head"):
            (fixture.target_root / f".planveyor.range.{name}").write_text(head + "\n")

    def _activate_generic_consumer(
        self, fixture: AuthorityFixture, *, merge_policy: bytes | None = None,
    ) -> None:
        """Build a narrow generic fixture without changing Planveyor-only helpers."""

        fixture.activate_local(
            authority.STATIC_PLANVEYOR_MERGE_REQUIRED_ENGAGED_PATHS,
            overrides={
                authority.PLANVEYOR_MERGE_GATE_POLICY_PATH: (
                    fixture_policy() if merge_policy is None else merge_policy
                ),
            },
            required_runtime_api=(5, 5),
        )
        head = git(fixture.target_root, "rev-parse", "HEAD")
        for name in ("base", "head"):
            (fixture.target_root / f".planveyor.range.{name}").write_text(head + "\n")

    def _runtime_command(
        self, fixture: AuthorityFixture, command: str,
    ) -> subprocess.CompletedProcess[str]:
        facade = shlex.quote(str(fixture.runtime_root / "scripts/planveyor.zsh"))
        program = fixture.shell_loader() + f"\nplanveyor_source_runtime {facade} || exit $?;\n" + command + "\n"
        environment = fixture.environment()
        environment["PYBIN"] = sys.executable
        environment["PLANVEYOR_RUNTIME_SOURCE_KIND"] = "git"
        return subprocess.run(
            ["/bin/zsh", "-fc", program], cwd=fixture.target_root, env=environment,
            capture_output=True, text=True, timeout=120, check=False,
        )

    def _init(self, fixture: AuthorityFixture, hook: str = "") -> subprocess.CompletedProcess[str]:
        return self._runtime_command(fixture, hook + "\nplanveyor_merge_tracker_init")

    def test_matching_generic_consumer_admits_merge_tracker(self) -> None:
        for marker_identity in ("consumer_42", "other_42"):
            with self.subTest(repository_id=marker_identity), AuthorityFixture(identity="consumer_42") as fixture:
                self._activate_generic_consumer(fixture)
                marker_path = fixture.target_root / authority._snapshot.MARKER_PATH
                marker = json.loads(marker_path.read_text(encoding="utf-8"))
                marker["repository_id"] = marker_identity
                marker_path.write_text(json.dumps(marker, sort_keys=True) + "\n", encoding="utf-8")
                captured = self._runtime_command(
                    fixture, "_planveyor_authority_context_for_reader planveyor_merge_tracker_init",
                )
                self.assertEqual(captured.returncode, 0, captured.stdout + captured.stderr)
                context = authority.parse_context_envelope(captured.stdout)
                self.assertEqual(context["schema_version"], authority.CONTEXT_SCHEMA_VERSION)
                self.assertEqual(context["state"], "engaged")
                self.assertEqual(context["behavior_identity"], marker_identity)
                result = self._init(fixture)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                tracker = fixture.target_root / ".planveyor.merge_tracker.md"
                self.assertTrue(tracker.is_file())
                text = tracker.read_text(encoding="utf-8")
                self.assertIn("POLICY_SCHEMA=planveyor_merge_gate_policy.v1\n", text)
                self.assertIn(f"AUTHORITY_GENERATION={context['generation_sha256']}\n", text)

    def test_declared_generic_schema_gate_routes_safe_manager_output(self) -> None:
        with AuthorityFixture(identity="consumer_42") as fixture:
            self._activate_generic_consumer(
                fixture, merge_policy=planveyor_merge_gate_policy(modes=("selected",)),
            )
            result = self._init(fixture)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            tracker = fixture.target_root / ".planveyor.merge_tracker.md"
            steps = [line for line in tracker.read_text(encoding="utf-8").splitlines() if line.startswith("- [ ] step:")]
            self.assertEqual(steps[0], "- [ ] step:migrations_gate")

            result = self._runtime_command(fixture, "planveyor_merge_next")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("manual_next: step:migrations_gate", result.stdout)
            self.assertIn("auto_next:   step:migrations_gate", result.stdout)
            self.assertIn("Suggested command(s):", result.stdout)
            for command in (
                "consumer_schema_check",
                "consumer_schema_precheck selected",
                "consumer_schema_apply selected",
                "consumer_schema_resolve",
            ):
                self.assertIn(command, result.stdout)
            self.assertNotIn("django", result.stdout.lower())
            self.assertNotIn("manage.py", result.stdout.lower())
            self.assertNotIn(" default", result.stdout.lower())

    def test_invalid_declared_generic_schema_gate_rejects_before_tracker_mutation(self) -> None:
        for label, modes in (("missing", ()), ("ambiguous", ("selected", "selected"))):
            with self.subTest(case=label), AuthorityFixture(identity="consumer_42") as fixture:
                self._activate_generic_consumer(
                    fixture, merge_policy=planveyor_merge_gate_policy(modes=modes),
                )
                before = tree_snapshot(fixture.target_root)
                result = self._init(fixture)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(tree_snapshot(fixture.target_root), before)
                self.assertFalse((fixture.target_root / ".planveyor.merge_tracker.md").exists())
                self.assertFalse(any(fixture.target_root.glob(".planveyor.merge_tracker.*.md")))

    def test_engaged_generic_tracker_ensure_reinitializes_missing_declared_core_step(self) -> None:
        with AuthorityFixture(identity="consumer_42") as fixture:
            self._activate_generic_consumer(
                fixture, merge_policy=planveyor_merge_gate_policy(modes=("selected",)),
            )
            result = self._init(fixture)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            tracker = fixture.target_root / ".planveyor.merge_tracker.md"
            tracker.write_text(
                tracker.read_text(encoding="utf-8").replace("- [ ] step:packetization_gate\n", "", 1),
                encoding="utf-8",
            )
            self.assertNotIn("- [ ] step:packetization_gate\n", tracker.read_text(encoding="utf-8"))

            result = self._runtime_command(fixture, "planveyor_merge_tracker_ensure")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            steps = [line for line in tracker.read_text(encoding="utf-8").splitlines() if line.startswith("- [ ] step:")]
            self.assertEqual(steps[0], "- [ ] step:migrations_gate")
            self.assertIn("- [ ] step:packetization_gate", steps)

    def test_invalid_generic_consumer_rejects_before_tracker_backup_or_artifacts(self) -> None:
        cases = (
            ("inherited_mismatch", "consumer_42", "other_42"),
            ("default", "default", "default"),
            ("grammar", "consumer invalid", "consumer invalid"),
        )
        for label, fixture_identity, marker_identity in cases:
            with self.subTest(case=label), AuthorityFixture(identity=fixture_identity) as fixture:
                self._activate_generic_consumer(fixture)
                hook = ""
                if label == "inherited_mismatch":
                    captured = self._runtime_command(
                        fixture, "_planveyor_authority_context_for_reader planveyor_merge_tracker_init",
                    )
                    self.assertEqual(captured.returncode, 0, captured.stdout + captured.stderr)
                    context = authority.parse_context_envelope(captured.stdout)
                    self.assertEqual(context["schema_version"], authority.CONTEXT_SCHEMA_VERSION)
                    self.assertEqual(context["state"], "engaged")
                    self.assertEqual(context["behavior_identity"], fixture_identity)
                    hook = "export _PLANVEYOR_AUTHORITY_CONTEXT_V1=" + shlex.quote(captured.stdout.strip())
                marker_path = fixture.target_root / authority._snapshot.MARKER_PATH
                marker = json.loads(marker_path.read_text(encoding="utf-8"))
                marker["repository_id"] = marker_identity
                marker_path.write_text(json.dumps(marker, sort_keys=True) + "\n", encoding="utf-8")
                before = tree_snapshot(fixture.target_root)
                result = self._init(fixture, hook)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                if label == "inherited_mismatch":
                    self.assertIn("context_expectation_mismatch", result.stdout + result.stderr)
                self.assertEqual(tree_snapshot(fixture.target_root), before)
                self.assertFalse((fixture.target_root / ".planveyor.merge_tracker.md").exists())
                self.assertFalse(any(fixture.target_root.glob(".planveyor.merge_tracker.*.md")))

    @staticmethod
    def _semantic_selector_mutation(marker_path: Path) -> str:
        program = (
            "import json, sys; from pathlib import Path; path = Path(sys.argv[1]); "
            "selector = json.loads(path.read_text(encoding='utf-8')); "
            "selector['required_runtime_api'] = {'minimum': 4, 'maximum': 5}; "
            "path.write_text(json.dumps(selector, sort_keys=True) + '\\n', encoding='utf-8')"
        )
        return "${PYBIN:?} -c " + shlex.quote(program) + " " + shlex.quote(str(marker_path))

    def test_late_selector_drift_preserves_tracker_and_backup(self) -> None:
        for existing in (False, True):
            with self.subTest(existing=existing), AuthorityFixture(identity="planveyor") as fixture:
                self._activate(fixture)
                root = fixture.target_root
                tracker = root / ".planveyor.merge_tracker.md"
                backup = root / ".planveyor.merge_tracker.test-backup.md"
                original = b"stale tracker retained on rejection\n"
                if existing:
                    tracker.write_bytes(original)
                backup.write_bytes(b"previous backup retained\n")
                selector_path = root / authority._snapshot.MARKER_PATH
                hook = (
                    "_planveyor_merge_tracker_backup_path() {\n"
                    f"  {self._semantic_selector_mutation(selector_path)} || return $?\n"
                    f"  print -r -- {shlex.quote(str(backup))}\n}}\n"
                )
                result = self._init(fixture, hook)
                self.assertEqual(
                    json.loads(selector_path.read_text(encoding="utf-8"))["required_runtime_api"],
                    {"minimum": 4, "maximum": 5},
                )
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(tracker.read_bytes() if tracker.exists() else None, original if existing else None)
                self.assertEqual(backup.read_bytes(), b"previous backup retained\n")
                self.assertNotIn("Saved:", result.stderr)
                self.assertNotIn("Backed up previous tracker:", result.stderr)

    def test_init_rejects_tracker_topology_before_any_backup_or_write(self) -> None:
        for kind in ("symlink", "broken_symlink", "directory", "fifo", "parent_escape", "dotdot_escape", "backup_symlink"):
            with self.subTest(kind=kind), AuthorityFixture(identity="planveyor") as fixture:
                self._activate(fixture)
                root = fixture.target_root
                outside = (root.parent if kind == "dotdot_escape" else fixture.root) / "outside-tracker.txt"
                outside.write_bytes(b"preserve outside bytes\n")
                tracker = root / ".planveyor.merge_tracker.md"
                backup = root / ".planveyor.merge_tracker.test-backup.md"
                if kind == "symlink":
                    tracker.symlink_to(outside)
                elif kind == "broken_symlink":
                    tracker.symlink_to(fixture.root / "missing-referent")
                elif kind == "directory":
                    tracker.mkdir()
                elif kind == "fifo":
                    os.mkfifo(tracker)
                elif kind == "parent_escape":
                    alias = root / "outside-alias"
                    alias.symlink_to(fixture.root, target_is_directory=True)
                    tracker = alias / outside.name
                elif kind == "dotdot_escape":
                    tracker = root / ".." / outside.name
                else:
                    tracker.write_bytes(b"stale tracker\n")
                    backup.symlink_to(outside)
                before = tracker.lstat()
                hook = (
                    f"_planveyor_merge_tracker_path() {{ print -r -- {shlex.quote(str(tracker))}; }}\n"
                    f"_planveyor_merge_tracker_backup_path() {{ print -r -- {shlex.quote(str(backup))}; }}\n"
                )
                result = self._init(fixture, hook)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(outside.read_bytes(), b"preserve outside bytes\n")
                self.assertEqual(tracker.lstat().st_ino, before.st_ino)
                self.assertEqual(tracker.lstat().st_mode, before.st_mode)
                if kind == "backup_symlink":
                    self.assertTrue(backup.is_symlink())
                    self.assertEqual(tracker.read_bytes(), b"stale tracker\n")
                else:
                    self.assertFalse(backup.exists())
                self.assertNotIn("Saved:", result.stderr)
                self.assertNotIn("Backed up previous tracker:", result.stderr)

    def test_init_allows_absent_and_stale_regular_tracker(self) -> None:
        for existing in (False, True):
            with self.subTest(existing=existing), AuthorityFixture(identity="planveyor") as fixture:
                self._activate(fixture)
                tracker = fixture.target_root / ".planveyor.merge_tracker.md"
                backup = fixture.target_root / ".planveyor.merge_tracker.test-backup.md"
                original = b"POLICY_SHA256=stale\nAUTHORITY_GENERATION=stale\n"
                if existing:
                    tracker.write_bytes(original)
                hook = f"_planveyor_merge_tracker_backup_path() {{ print -r -- {shlex.quote(str(backup))}; }}\n"
                result = self._init(fixture, hook)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(f"POLICY_SHA256={hashlib.sha256(fixture_policy()).hexdigest()}\n", tracker.read_text())
                self.assertIn("- [ ] step:ready_to_push\n", tracker.read_text())
                self.assertEqual(backup.read_bytes() if backup.exists() else None, original if existing else None)

    def test_final_frozen_guard_rejects_selector_drift_after_topology_preparation(self) -> None:
        with AuthorityFixture(identity="planveyor") as fixture:
            self._activate(fixture)
            tracker = fixture.target_root / ".planveyor.merge_tracker.md"
            backup = fixture.target_root / ".planveyor.merge_tracker.test-backup.md"
            tracker.write_bytes(b"keep tracker before late drift\n")
            selector_path = fixture.target_root / authority._snapshot.MARKER_PATH
            hook = f"""
_planveyor_merge_tracker_backup_path() {{ print -r -- {shlex.quote(str(backup))}; }}
functions[_fixture_validate_tracker]=$functions[_planveyor_merge_policy_validate_tracker]
_planveyor_merge_policy_validate_tracker() {{
  _fixture_validate_tracker "$@" || return $?
  if [[ "$2" == {shlex.quote(str(backup))} ]]; then
    {self._semantic_selector_mutation(selector_path)} || return $?
  fi
}}
"""
            result = self._init(fixture, hook)
            self.assertEqual(
                json.loads(selector_path.read_text(encoding="utf-8"))["required_runtime_api"],
                {"minimum": 4, "maximum": 5},
            )
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(tracker.read_bytes(), b"keep tracker before late drift\n")
            self.assertFalse(backup.exists())
            self.assertNotIn("Backed up previous tracker:", result.stderr)
            self.assertNotIn("Saved:", result.stderr)

    def test_init_rechecks_tracker_after_backup_before_publication(self) -> None:
        with AuthorityFixture(identity="planveyor") as fixture:
            self._activate(fixture)
            tracker = fixture.target_root / ".planveyor.merge_tracker.md"
            backup = fixture.target_root / ".planveyor.merge_tracker.test-backup.md"
            outside = fixture.root / "outside-after-backup.txt"
            tracker.write_bytes(b"old regular tracker\n")
            outside.write_bytes(b"outside retained\n")
            hook = f"""
_planveyor_merge_tracker_backup_path() {{ print -r -- {shlex.quote(str(backup))}; }}
cp() {{
  command cp "$@" || return $?
  command rm -- "$1" || return $?
  command ln -s {shlex.quote(str(outside))} "$1"
}}
"""
            result = self._init(fixture, hook)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(backup.read_bytes(), b"old regular tracker\n")
            self.assertTrue(tracker.is_symlink())
            self.assertEqual(outside.read_bytes(), b"outside retained\n")
            self.assertNotIn("Saved:", result.stderr)

    def test_closeout_retains_report_generation_and_tracker_selection(self) -> None:
        for mode in ("normal", "rebind", "report_rebind", "tracker_switch"):
            with self.subTest(mode=mode), AuthorityFixture(identity="planveyor") as fixture:
                harness = fixture.runtime_root / "scripts/merge_effect_probe.py"
                harness.write_text(CLOSEOUT_PROBE)
                fixture.runtime_commit = commit_all(fixture.runtime_root, "fixture closeout boundary probe")
                self._activate(fixture)
                result = run_python_entry(fixture, harness, str(fixture.target_root), mode, timeout=120)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                payload = json.loads(result.stdout)
                self.assertTrue(payload["ready_unchecked"])
                if mode == "normal":
                    self.assertEqual(payload["events"], ["tick_reached"], payload)
                else:
                    self.assertEqual(payload["events"], [], payload)
                    rejection = payload["result"].get("rejection") or payload["result"].get("blocker")
                    self.assertTrue(rejection, payload)
                    if mode == "report_rebind":
                        self.assertEqual(payload["result"].get("rejection"), "authority_generation_mismatch", payload)
                    if mode in {"rebind", "report_rebind"}:
                        self.assertNotEqual(payload["old_generation"], payload["new_generation"])
                        self.assertNotEqual(payload["old_policy"], payload["new_policy"])
                    else:
                        self.assertEqual(payload["old_generation"], payload["new_generation"])

    def _root_alias_probe(self, mode: str) -> dict:
        with AuthorityFixture(identity="planveyor") as fixture:
            harness = fixture.runtime_root / "scripts/merge_root_alias_probe.py"
            harness.write_text(ROOT_ALIAS_PROBE)
            fixture.runtime_commit = commit_all(fixture.runtime_root, "fixture stable root alias probe")
            self._activate(fixture)
            result = run_python_entry(fixture, harness, str(fixture.target_root), mode, timeout=120)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return json.loads(result.stdout)

    def test_closeout_cli_accepts_stable_root_alias_with_default_and_relative_tracker(self) -> None:
        payload = self._root_alias_probe("cli")
        self.assertTrue(payload["tracker_generation_alias_git_unchanged"])
        self.assertEqual(len(payload["rows"]), 4)
        for row in payload["rows"]:
            with self.subTest(alias=row["alias"], relative_tracker=row["relative_tracker"]):
                self.assertTrue(row["initial_admission"], row)
                result = row["result"]
                self.assertEqual(result["rc"], 2, row)
                self.assertEqual(result["stderr"], "", row)
                self.assertEqual(json.loads(result["stdout"])["blocker"]["code"], "red_report", row)

    def test_closeout_reaches_tick_through_stable_root_alias_with_default_and_relative_tracker(self) -> None:
        payload = self._root_alias_probe("tick")
        self.assertTrue(payload["tracker_generation_alias_git_unchanged"])
        self.assertEqual(len(payload["rows"]), 4)
        for row in payload["rows"]:
            with self.subTest(alias=row["alias"], relative_tracker=row["relative_tracker"]):
                self.assertTrue(row["initial_admission"], row)
                self.assertEqual(row["events"], ["report_admitted", "tick_reached"], row)
                self.assertEqual(row["result"], {"probe": "stopped_before_write"}, row)


if __name__ == "__main__":
    unittest.main()

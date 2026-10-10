#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from textwrap import dedent
from unittest import mock


MODULE_PATH = Path(__file__).with_name("merge_tracker_oracle.py")
SPEC = importlib.util.spec_from_file_location("merge_tracker_oracle", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

import contract_authority_context as authority
from authority_bootstrap_test_support import run_python_entry, run_python_stdin
from test_contract_authority_support import AuthorityFixture
from test_support.process_contract_fixtures import standalone_git_root


# Runs one oracle command in the fixture runtime and reports its tracker reads
# and written files, so a refusal can be shown to precede every effect.
_ORACLE_EFFECT_OBSERVER = dedent(
    """
    import contextlib
    import io
    import json
    import sys
    from pathlib import Path
    from unittest import mock
    import merge_tracker_oracle as oracle

    tracker = Path(sys.argv[1])
    command = sys.argv[2]
    argv = ["--tracker", str(tracker), "--format", "json", command]
    if command == "tick":
        argv.append("step:review_range")
    captured = io.StringIO()
    with (
        contextlib.redirect_stdout(captured),
        mock.patch.object(oracle, "_read_snapshot", wraps=oracle._read_snapshot) as read_snapshot,
        mock.patch.object(oracle, "_write_lines", wraps=oracle._write_lines) as write_lines,
    ):
        return_code = oracle.main(argv)
    print(json.dumps({
        "returncode": return_code,
        "stdout": captured.getvalue(),
        "read_calls": read_snapshot.call_count,
        "write_paths": [str(Path(call.args[0]).resolve()) for call in write_lines.call_args_list],
    }))
    """
)


class MergeTrackerOracleTests(unittest.TestCase):
    def _git(self, root: Path, *arguments: str) -> None:
        subprocess.run(
            [
                "git",
                "-c", "core.hooksPath=/dev/null",
                "-c", "commit.gpgsign=false",
                "-C", str(root),
                *arguments,
            ],
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def _init_git_root(self, root: Path) -> None:
        root.mkdir(parents=True)
        self._git(root, "init", "-q")
        self._git(root, "config", "user.email", 'oracle' + '@' + 'example' + '.' + 'test')
        self._git(root, "config", "user.name", "Oracle Test")
        self._write_tracker(root, "README.md", "fixture\n")
        self._git(root, "add", "README.md")
        self._git(root, "commit", "-q", "-m", "fixture")

    def _run_fixture_oracle(
        self,
        fixture: AuthorityFixture,
        tracker: Path,
        command: str,
    ) -> subprocess.CompletedProcess[str]:
        return run_python_entry(
            fixture,
            fixture.runtime_root / "scripts/merge_tracker_oracle.py",
            "--tracker",
            str(tracker),
            "--format",
            "json",
            command,
            *(("step:review_range",) if command == "tick" else ()),
            timeout=60,
        )

    def _write_tracker(self, root: Path, rel_path: str, body: str) -> Path:
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    def test_next_returns_first_unchecked_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            tracker = self._write_tracker(
                root,
                ".planveyor.merge_tracker.md",
                dedent(
                    """\
                    # Merge tracker

                    - [x] step:review_range — done
                    - [ ] step:plan_harvest — next
                    - [ ] step:post_merge_audit — later
                    """
                ),
            )
            stdout = io.StringIO()

            with mock.patch("sys.stdout", stdout):
                result = MODULE.main(["--tracker", str(tracker), "--format", "json", "next"])

        self.assertEqual(result, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["next_step"], "step:plan_harvest")
        self.assertEqual(payload["done"], 0)
        self.assertEqual(payload["tracker"], str(tracker))

    def test_tick_marks_step_done_and_next_advances(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            tracker = self._write_tracker(
                root,
                ".planveyor.merge_tracker.md",
                dedent(
                    """\
                    # Merge tracker

                    - [ ] step:review_range — first
                    - [ ] step:plan_harvest — second
                    """
                ),
            )
            tick_stdout = io.StringIO()
            next_stdout = io.StringIO()

            with mock.patch("sys.stdout", tick_stdout):
                tick_result = MODULE.main(["--tracker", str(tracker), "--format", "json", "tick", "step:review_range"])
            with mock.patch("sys.stdout", next_stdout):
                next_result = MODULE.main(["--tracker", str(tracker), "--format", "json", "next"])

            tracker_text = tracker.read_text(encoding="utf-8")

        self.assertEqual(tick_result, 0)
        tick_payload = json.loads(tick_stdout.getvalue())
        self.assertEqual(tick_payload["changed"], 1)
        self.assertEqual(tick_payload["key"], "step:review_range")
        self.assertIn("- [x] step:review_range — first", tracker_text)

        self.assertEqual(next_result, 0)
        next_payload = json.loads(next_stdout.getvalue())
        self.assertEqual(next_payload["next_step"], "step:plan_harvest")
        self.assertEqual(next_payload["done"], 0)

    def test_malformed_tracker_returns_no_steps_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            tracker = self._write_tracker(
                root,
                ".planveyor.merge_tracker.md",
                dedent(
                    """\
                    # Merge tracker

                    - no canonical step markers here
                    """
                ),
            )
            stdout = io.StringIO()

            with mock.patch("sys.stdout", stdout):
                result = MODULE.main(["--tracker", str(tracker), "--format", "json", "next"])

        self.assertEqual(result, 2)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["error"], "no_steps_found")
        self.assertEqual(payload["tracker"], str(tracker))
        self.assertEqual(payload["next_step"], "")
        self.assertEqual(payload["done"], 0)

    def test_header_mismatch_fails_closed_before_next_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            base = "a" * 40
            head = "b" * 40
            self._write_tracker(root, ".planveyor.range.base", f"{base}\n")
            self._write_tracker(root, ".planveyor.range.head", f"{head}\n")
            tracker = self._write_tracker(
                root,
                ".planveyor.merge_tracker.md",
                dedent(
                    f"""\
                    # Merge tracker

                    BASE={base}
                    HEAD={'c' * 40}
                    RANGE={base}..{head}
                    RANGE_ID=range_{base[:7]}_{head[:7]}

                    - [ ] step:review_range
                    """
                ),
            )
            stdout = io.StringIO()

            with mock.patch("sys.stdout", stdout):
                result = MODULE.main(["--tracker", str(tracker), "--format", "json", "next"])

        self.assertEqual(result, 2)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["error"], "tracker_header_inconsistent")
        self.assertEqual(payload["header_errors"][0]["field"], "HEAD")
        self.assertEqual(payload["header_errors"][0]["expected"], head)

    def test_direct_oracle_admits_lexical_parent_marker_before_symlink_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            outer = Path(tmpdir).resolve() / "project"
            outside = outer.parent / "outside"
            self._init_git_root(outer)
            outside.mkdir()
            marker = outer / "docs/_meta/planveyor_contract_authority.v1.json"
            marker.parent.mkdir(parents=True)
            marker.write_text("{}\n", encoding="utf-8")
            tracker = self._write_tracker(
                outside,
                ".planveyor.merge_tracker.md",
                "# Tracker\n\n- [ ] step:review_range\n",
            )
            pivot = outer / "pivot"
            pivot.symlink_to(outside, target_is_directory=True)
            stdout = io.StringIO()

            with mock.patch("sys.stdout", stdout):
                result = MODULE.main(
                    ["--tracker", str(pivot / tracker.name), "--format", "json", "next"]
                )

        self.assertEqual(result, 2)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["error"], "unsupported_live_marker_schema")
        self.assertNotIn("next_step", payload)

    def test_nested_git_boundary_keeps_legacy_parent_alias_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            outer = Path(tmpdir).resolve() / "outer"
            nested = outer / "nested"
            outside = outer.parent / "outside"
            self._init_git_root(outer)
            self._init_git_root(nested)
            outside.mkdir()
            marker = outer / "docs/_meta/planveyor_contract_authority.v1.json"
            marker.parent.mkdir(parents=True)
            marker.write_text("{}\n", encoding="utf-8")
            tracker = self._write_tracker(
                outside,
                ".planveyor.merge_tracker.md",
                "# Tracker\n\n- [ ] step:review_range\n",
            )
            pivot = nested / "pivot"
            pivot.symlink_to(outside, target_is_directory=True)
            stdout = io.StringIO()

            with mock.patch("sys.stdout", stdout):
                result = MODULE.main(
                    ["--tracker", str(pivot / tracker.name), "--format", "json", "next"]
                )

        self.assertEqual(result, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["next_step"], "step:review_range")

    def test_alias_destination_marker_is_admitted_after_legacy_origin(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            outer = Path(tmpdir).resolve() / "outer"
            external = outer.parent / "external"
            self._init_git_root(outer)
            self._init_git_root(external)
            tracker = self._write_tracker(
                external,
                ".planveyor.merge_tracker.md",
                "# Tracker\n\n- [ ] step:review_range\n",
            )
            initial = io.StringIO()
            with mock.patch("sys.stdout", initial):
                legacy_result = MODULE.main(
                    ["--tracker", str(tracker), "--format", "json", "next"]
                )
            self.assertEqual(legacy_result, 0)
            self.assertEqual(json.loads(initial.getvalue())["next_step"], "step:review_range")

            marker = external / "docs/_meta/planveyor_contract_authority.v1.json"
            marker.parent.mkdir(parents=True)
            marker.write_text("{}\n", encoding="utf-8")
            pivot = outer / "pivot"
            pivot.symlink_to(external, target_is_directory=True)
            tracker_before = tracker.read_bytes()
            paths_before = {p.relative_to(outer.parent).as_posix() for p in outer.parent.rglob("*")}
            escaped = io.StringIO()
            with (
                mock.patch("sys.stdout", escaped),
                mock.patch.object(MODULE, "_read_snapshot", wraps=MODULE._read_snapshot) as read_snapshot,
                mock.patch.object(MODULE, "_write_lines", wraps=MODULE._write_lines) as write_lines,
            ):
                result = MODULE.main(
                    ["--tracker", str(pivot / tracker.name), "--format", "json", "next"]
                )

            read_snapshot.assert_not_called()
            write_lines.assert_not_called()
            self.assertEqual(tracker.read_bytes(), tracker_before)
            self.assertEqual(
                {p.relative_to(outer.parent).as_posix() for p in outer.parent.rglob("*")},
                paths_before,
            )

        self.assertEqual(result, 2)
        self.assertEqual(json.loads(escaped.getvalue())["error"], "unsupported_live_marker_schema")

    def test_prefix_alias_keeps_valid_engaged_root_and_rejects_post_root_escape(self) -> None:
        with AuthorityFixture(identity="planveyor") as fixture:
            fixture.activate_planveyor(
                authority.STATIC_PLANVEYOR_MERGE_REQUIRED_ENGAGED_PATHS,
                required_runtime_api=(5, 5),
            )
            metadata = run_python_entry(
                fixture,
                fixture.runtime_root / "scripts/merge_gate_policy.py",
                "--root",
                str(fixture.target_root),
                "metadata",
                timeout=60,
            )
            self.assertEqual(metadata.returncode, 0, metadata.stderr)
            tracker = self._write_tracker(
                fixture.target_root,
                ".planveyor.merge_tracker.md",
                metadata.stdout + "- [ ] step:review_range\n",
            )
            alias_parent = fixture.root.with_name(f"{fixture.root.name}-prefix-alias")
            alias_parent.symlink_to(fixture.root, target_is_directory=True)
            alias_target = alias_parent / fixture.target_root.relative_to(fixture.root)
            success = self._run_fixture_oracle(
                fixture,
                alias_target / tracker.name,
                "next",
            )
            self.assertEqual(success.returncode, 0, success.stderr)
            self.assertEqual(json.loads(success.stdout)["next_step"], "step:review_range")

            outside = fixture.root / "outside"
            outside.mkdir()
            escaped_tracker = self._write_tracker(
                outside,
                tracker.name,
                metadata.stdout + "- [ ] step:review_range\n",
            )
            pivot = fixture.target_root / "pivot"
            pivot.symlink_to(outside, target_is_directory=True)
            before = escaped_tracker.read_bytes()
            validation = run_python_entry(
                fixture,
                fixture.runtime_root / "scripts/merge_gate_policy.py",
                "--root",
                str(alias_target),
                "--tracker",
                str(alias_target / pivot.name / tracker.name),
                "validate",
                timeout=60,
            )
            next_result = self._run_fixture_oracle(
                fixture,
                alias_target / pivot.name / tracker.name,
                "next",
            )
            tick_result = self._run_fixture_oracle(
                fixture,
                alias_target / pivot.name / tracker.name,
                "tick",
            )
            untouched = escaped_tracker.read_bytes() == before

        self.assertEqual(validation.returncode, 2, validation.stdout + validation.stderr)
        self.assertIn("engaged_tracker_escape", validation.stdout + validation.stderr)
        self.assertEqual(next_result.returncode, 2, next_result.stdout + next_result.stderr)
        self.assertEqual(tick_result.returncode, 2, tick_result.stdout + tick_result.stderr)
        self.assertEqual(json.loads(next_result.stdout)["error"], "engaged_tracker_escape")
        self.assertEqual(json.loads(tick_result.stdout)["error"], "engaged_tracker_escape")
        self.assertTrue(untouched)

    def test_post_root_alias_preserves_intermediate_suffix_and_mutates_only_requested_tracker(self) -> None:
        with AuthorityFixture(identity="planveyor") as fixture:
            fixture.activate_planveyor(
                authority.STATIC_PLANVEYOR_MERGE_REQUIRED_ENGAGED_PATHS,
                required_runtime_api=(5, 5),
            )
            metadata = run_python_entry(
                fixture,
                fixture.runtime_root / "scripts/merge_gate_policy.py",
                "--root",
                str(fixture.target_root),
                "metadata",
                timeout=60,
            )
            self.assertEqual(metadata.returncode, 0, metadata.stderr)
            real = fixture.target_root / "real"
            requested = self._write_tracker(
                real,
                "subdir/tracker.md",
                metadata.stdout + "- [ ] step:review_range — requested\n",
            )
            sibling = self._write_tracker(
                real,
                "tracker.md",
                metadata.stdout + "- [ ] step:plan_harvest — sibling\n",
            )
            pivot = fixture.target_root / "pivot"
            pivot.symlink_to(real, target_is_directory=True)
            raw = pivot / "subdir" / "tracker.md"
            sibling_before = sibling.read_bytes()

            next_result = self._run_fixture_oracle(fixture, raw, "next")
            tick_result = self._run_fixture_oracle(fixture, raw, "tick")

            next_payload = json.loads(next_result.stdout)
            tick_payload = json.loads(tick_result.stdout)
            next_targets_raw = Path(next_payload["tracker"]).samefile(raw)
            tick_targets_raw = Path(tick_payload["tracker"]).samefile(raw)
            requested_after = requested.read_text(encoding="utf-8")
            sibling_after = sibling.read_bytes()

        self.assertEqual(next_result.returncode, 0, next_result.stderr)
        self.assertEqual(tick_result.returncode, 0, tick_result.stderr)
        self.assertTrue(next_targets_raw)
        self.assertTrue(tick_targets_raw)
        self.assertEqual(next_payload["next_step"], "step:review_range")
        self.assertEqual(tick_payload["changed"], 1)
        self.assertIn("- [x] step:review_range — requested", requested_after)
        self.assertEqual(sibling_after, sibling_before)

    def test_post_root_dotdot_preserves_requested_file_and_never_selects_sibling(self) -> None:
        with AuthorityFixture(identity="planveyor") as fixture:
            fixture.activate_planveyor(
                authority.STATIC_PLANVEYOR_MERGE_REQUIRED_ENGAGED_PATHS,
                required_runtime_api=(5, 5),
            )
            metadata = run_python_entry(
                fixture,
                fixture.runtime_root / "scripts/merge_gate_policy.py",
                "--root",
                str(fixture.target_root),
                "metadata",
                timeout=60,
            )
            self.assertEqual(metadata.returncode, 0, metadata.stderr)
            requested = self._write_tracker(
                fixture.target_root,
                "real/tracker.md",
                metadata.stdout + "- [ ] step:review_range — requested\n",
            )
            sibling = self._write_tracker(
                fixture.target_root,
                "real/subdir/tracker.md",
                metadata.stdout + "- [ ] step:plan_harvest — sibling\n",
            )
            raw = fixture.target_root / "real" / "subdir" / ".." / "tracker.md"
            sibling_before = sibling.read_bytes()

            next_result = self._run_fixture_oracle(fixture, raw, "next")
            tick_result = self._run_fixture_oracle(fixture, raw, "tick")

            next_payload = json.loads(next_result.stdout)
            tick_payload = json.loads(tick_result.stdout)
            next_targets_raw = Path(next_payload["tracker"]).samefile(raw)
            tick_targets_raw = Path(tick_payload["tracker"]).samefile(raw)
            requested_after = requested.read_text(encoding="utf-8")
            sibling_after = sibling.read_bytes()

        self.assertEqual(next_result.returncode, 0, next_result.stderr)
        self.assertEqual(tick_result.returncode, 0, tick_result.stderr)
        self.assertTrue(next_targets_raw)
        self.assertTrue(tick_targets_raw)
        self.assertEqual(next_payload["next_step"], "step:review_range")
        self.assertEqual(tick_payload["changed"], 1)
        self.assertIn("- [x] step:review_range — requested", requested_after)
        self.assertEqual(sibling_after, sibling_before)


    def test_legacy_git_alias_admits_engaged_destination_and_rejects_pivot_before_effects(self) -> None:
        with AuthorityFixture(identity="planveyor") as fixture:
            fixture.activate_planveyor(
                authority.STATIC_PLANVEYOR_MERGE_REQUIRED_ENGAGED_PATHS,
                required_runtime_api=(5, 5),
            )
            metadata = run_python_entry(
                fixture,
                fixture.runtime_root / "scripts/merge_gate_policy.py",
                "--root", str(fixture.target_root), "metadata",
                timeout=60,
            )
            self.assertEqual(metadata.returncode, 0, metadata.stderr)
            tracker = self._write_tracker(
                fixture.target_root, ".planveyor.merge_tracker.md",
                metadata.stdout + "- [ ] step:review_range\n",
            )
            legacy_origin = fixture.root / "legacy-origin"
            self._init_git_root(legacy_origin)
            alias = legacy_origin / "alias"
            alias.symlink_to(fixture.target_root, target_is_directory=True)
            outside = fixture.root / "outside"
            outside.mkdir()
            escaped_tracker = self._write_tracker(
                outside, tracker.name, metadata.stdout + "- [ ] step:review_range\n",
            )
            pivot = fixture.target_root / "pivot"
            pivot.symlink_to(outside, target_is_directory=True)
            tracker_before = tracker.read_bytes()
            escaped_before = escaped_tracker.read_bytes()
            paths_before = {p.relative_to(fixture.root).as_posix() for p in fixture.root.rglob("*")}
            observer_source = dedent(
                """
                import contextlib
                import io
                import json
                import sys
                from pathlib import Path
                from unittest import mock
                import merge_tracker_oracle as oracle

                tracker = Path(sys.argv[1])
                command = sys.argv[2]
                argv = ["--tracker", str(tracker), "--format", "json", command]
                if command == "tick":
                    argv.append("step:review_range")
                captured = io.StringIO()
                with (
                    contextlib.redirect_stdout(captured),
                    mock.patch.object(oracle, "_read_snapshot", wraps=oracle._read_snapshot) as read_snapshot,
                    mock.patch.object(oracle, "_write_lines", wraps=oracle._write_lines) as write_lines,
                ):
                    return_code = oracle.main(argv)
                print(json.dumps({
                    "returncode": return_code,
                    "stdout": captured.getvalue(),
                    "read_calls": read_snapshot.call_count,
                    "write_calls": write_lines.call_count,
                    "read_paths": [str(Path(call.args[0]).resolve()) for call in read_snapshot.call_args_list],
                }))
                """
            )
            positive = run_python_stdin(
                fixture, observer_source, str(alias / tracker.name), "next", timeout=60,
            )
            self.assertEqual(positive.returncode, 0, positive.stdout + positive.stderr)
            positive_observation = json.loads(positive.stdout)
            self.assertEqual(positive_observation["returncode"], 0)
            self.assertEqual(json.loads(positive_observation["stdout"])["next_step"], "step:review_range")
            self.assertGreaterEqual(positive_observation["read_calls"], 1)
            self.assertEqual(positive_observation["read_paths"], [str(tracker.resolve())])
            self.assertEqual(positive_observation["write_calls"], 0)
            self.assertEqual(tracker.read_bytes(), tracker_before)
            self.assertEqual(escaped_tracker.read_bytes(), escaped_before)
            self.assertEqual(
                {p.relative_to(fixture.root).as_posix() for p in fixture.root.rglob("*")},
                paths_before,
            )

            negative_paths_before = {
                p.relative_to(fixture.root).as_posix() for p in fixture.root.rglob("*")
            }
            negative = run_python_stdin(
                fixture, observer_source, str(alias / pivot.name / tracker.name), "tick", timeout=60,
            )
            self.assertEqual(negative.returncode, 0, negative.stdout + negative.stderr)
            negative_observation = json.loads(negative.stdout)
            self.assertEqual(negative_observation["returncode"], 2)
            self.assertEqual(
                json.loads(negative_observation["stdout"])["error"], "engaged_tracker_escape"
            )
            self.assertEqual(negative_observation["read_calls"], 0)
            self.assertEqual(negative_observation["write_calls"], 0)
            self.assertEqual(tracker.read_bytes(), tracker_before)
            self.assertEqual(escaped_tracker.read_bytes(), escaped_before)
            self.assertEqual(
                {p.relative_to(fixture.root).as_posix() for p in fixture.root.rglob("*")},
                negative_paths_before,
            )

    def test_legacy_dotdot_before_alias_still_rejects_engaged_pivot_before_effects(self) -> None:
        # A legacy Git root holds an alias into the engaged root, whose own
        # post-root alias leaves it.  A ``..`` after the legacy root must not
        # hide the engaged root and that post-root alias.
        with AuthorityFixture(identity="planveyor") as fixture:
            fixture.activate_planveyor(
                authority.STATIC_PLANVEYOR_MERGE_REQUIRED_ENGAGED_PATHS,
                required_runtime_api=(5, 5),
            )
            metadata = run_python_entry(
                fixture,
                fixture.runtime_root / "scripts/merge_gate_policy.py",
                "--root", str(fixture.target_root), "metadata",
                timeout=60,
            )
            self.assertEqual(metadata.returncode, 0, metadata.stderr)
            tracker = self._write_tracker(
                fixture.target_root, ".planveyor.merge_tracker.md",
                metadata.stdout + "- [ ] step:review_range\n",
            )
            legacy_origin = fixture.root / "legacy-origin"
            legacy_origin.mkdir()
            standalone_git_root(legacy_origin)
            legacy_tracker = self._write_tracker(legacy_origin, tracker.name, "- [ ] step:review_range\n")
            (legacy_origin / "spare").mkdir()
            (legacy_origin / "alias").symlink_to(fixture.target_root, target_is_directory=True)
            # Physically hop/.. is real/, so real/deep-alias is crossed; a
            # lexical normalization would name the absent legacy-origin/deep-alias.
            (legacy_origin / "real" / "deeper").mkdir(parents=True)
            (legacy_origin / "hop").symlink_to(legacy_origin / "real" / "deeper", target_is_directory=True)
            (legacy_origin / "real" / "deep-alias").symlink_to(fixture.target_root, target_is_directory=True)
            outside = fixture.root / "outside"
            outside.mkdir()
            escaped_tracker = self._write_tracker(
                outside, tracker.name, metadata.stdout + "- [ ] step:review_range\n",
            )
            (fixture.target_root / "pivot").symlink_to(outside, target_is_directory=True)
            escaped_before = escaped_tracker.read_bytes()
            tracker_before = tracker.read_bytes()
            legacy_before = legacy_tracker.read_bytes()
            paths_before = {p.relative_to(fixture.root).as_posix() for p in fixture.root.rglob("*")}

            def observe(path: Path) -> dict[str, object]:
                completed = run_python_stdin(
                    fixture, _ORACLE_EFFECT_OBSERVER, str(path), "tick", timeout=60,
                )
                self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
                return json.loads(completed.stdout)

            escapes = {
                "without_dotdot": legacy_origin / "alias" / "pivot" / tracker.name,
                "legacy_dotdot": legacy_origin / "spare" / ".." / "alias" / "pivot" / tracker.name,
                "alias_then_dotdot": legacy_origin / "hop" / ".." / "deep-alias" / "pivot" / tracker.name,
            }
            refusals = {label: observe(path) for label, path in escapes.items()}
            escaped_after_refusals = escaped_tracker.read_bytes()
            tracker_after_refusals = tracker.read_bytes()
            legacy_after_refusals = legacy_tracker.read_bytes()
            paths_after_refusals = {p.relative_to(fixture.root).as_posix() for p in fixture.root.rglob("*")}

            engaged_tick = observe(legacy_origin / "spare" / ".." / "alias" / tracker.name)
            legacy_tick = observe(legacy_origin / "spare" / ".." / tracker.name)
            engaged_write_target = str(tracker.resolve())
            legacy_write_target = str(legacy_tracker.resolve())
            tracker_after = tracker.read_text(encoding="utf-8")
            legacy_after = legacy_tracker.read_text(encoding="utf-8")
            escaped_after = escaped_tracker.read_bytes()

        for label, observation in refusals.items():
            with self.subTest(path=label):
                self.assertEqual(observation["returncode"], 2, observation)
                self.assertEqual(json.loads(observation["stdout"])["error"], "engaged_tracker_escape")
                self.assertEqual(observation["read_calls"], 0, observation)
                self.assertEqual(observation["write_paths"], [], observation)
        self.assertEqual(escaped_after_refusals, escaped_before)
        self.assertEqual(tracker_after_refusals, tracker_before)
        self.assertEqual(legacy_after_refusals, legacy_before)
        self.assertEqual(paths_after_refusals, paths_before)

        self.assertEqual(engaged_tick["returncode"], 0, engaged_tick)
        self.assertEqual(json.loads(engaged_tick["stdout"])["changed"], 1)
        self.assertEqual(engaged_tick["write_paths"], [engaged_write_target])
        self.assertIn("- [x] step:review_range", tracker_after)
        self.assertEqual(legacy_tick["returncode"], 0, legacy_tick)
        self.assertEqual(json.loads(legacy_tick["stdout"])["changed"], 1)
        self.assertEqual(legacy_tick["write_paths"], [legacy_write_target])
        self.assertIn("- [x] step:review_range", legacy_after)
        self.assertEqual(escaped_after, escaped_before)

    def test_engaged_tick_revalidates_the_same_snapshot_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            tracker = self._write_tracker(root, ".planveyor.merge_tracker.md", "- [ ] step:review_range\n")
            binding = mock.Mock(
                tracker_path=tracker,
                context=mock.Mock(project_root=root, generation_sha256="a" * 64),
                policy=mock.Mock(raw_sha256="b" * 64),
            )
            stdout = io.StringIO()
            with (
                mock.patch.object(
                    MODULE.merge_gate_policy,
                    "validate_tracker_for_path",
                    side_effect=(binding, binding),
                ) as validate,
                mock.patch.object(
                    MODULE,
                    "_read_snapshot",
                    side_effect=(
                        (b"- [ ] step:review_range\n", ["- [ ] step:review_range"]),
                        (b"- [x] step:review_range\n", ["- [x] step:review_range"]),
                    ),
                ),
                mock.patch.object(MODULE, "_write_lines") as write_lines,
                mock.patch("sys.stdout", stdout),
            ):
                result = MODULE.main(
                    ["--tracker", str(tracker), "--format", "json", "tick", "step:review_range"]
                )

        self.assertEqual(result, 2)
        self.assertEqual(validate.call_count, 2)
        write_lines.assert_not_called()
        self.assertEqual(json.loads(stdout.getvalue())["error"], "engaged_tracker_changed_before_tick")


if __name__ == "__main__":
    unittest.main()

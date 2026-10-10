#!/usr/bin/env python3
"""Unit tests for the verify-suite registry, portability checks, and reporting.

These tests target the pure logic of verify_suite.py: Result validation, the
module registry, the corruption/allowlist classifiers, the interpretation of
responsibility, and the JSON/plain renderers. Heavy subprocess checks
(``make test-scripts``) are not exercised here; current-repository coverage is
a separate integration concern through ``make verify-full`` or ``make test-scripts``.

The module under test is loaded via importlib (mirroring test_merge_bundle_report.py)
because it sits next to other scripts rather than being an importable package.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "scripts" / "verify_suite.py"

_SPEC = importlib.util.spec_from_file_location("verify_suite", MODULE_PATH)
_VERIFY = importlib.util.module_from_spec(_SPEC)
sys.modules["verify_suite"] = _VERIFY
_SPEC.loader.exec_module(_VERIFY)


def _write(root: Path, rel: str, body: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def _init_and_track(root: Path) -> None:
    for argv in (("/usr/bin/git", "init", "-q"), ("/usr/bin/git", "add", "--all")):
        subprocess.run(argv, cwd=root, check=True, capture_output=True)


def _fictional_home(name: str = "fixture-user") -> Path:
    """Build a scanner-clean generic fixture path."""
    return Path("/Users") / name


class ResultTests(unittest.TestCase):
    def test_status_must_be_normalized(self) -> None:
        with self.assertRaises(ValueError):
            _VERIFY.Result("x", "bogus")

    def test_pass_warn_fail_accepted(self) -> None:
        for ok in ("pass", "warn", "fail"):
            _VERIFY.Result("x", ok)  # no raise

    def test_default_metric_detail_empty(self) -> None:
        r = _VERIFY.Result("x", "pass")
        self.assertEqual(r.metric, "")
        self.assertEqual(r.detail, "")


class RegistryTests(unittest.TestCase):
    def test_register_appends_class(self) -> None:
        before = len(_VERIFY._REGISTRY)

        @_VERIFY.register
        class _Temp(_VERIFY.ModuleBase):
            name = "_tmp_test_module"

            def run(self, repo_root):
                return []

            def interpret(self, results):
                return ""

        # Rollback via addCleanup so a failed assert cannot leak _Temp into the
        # global registry and poison later runs.
        self.addCleanup(_VERIFY._REGISTRY.pop)
        self.assertEqual(len(_VERIFY._REGISTRY), before + 1)
        self.assertIs(_VERIFY._REGISTRY[-1], _Temp)

    def test_portability_module_is_registered(self) -> None:
        names = [cls.name for cls in _VERIFY._REGISTRY]
        self.assertIn("portability", names)


class _FakeFinding:
    """Minimal stand-in for oss_release_scan.Finding used in mocks."""

    def __init__(self, path: str, line: int, category: str, severity: str, token: str) -> None:
        self.path = path
        self.line = line
        self.category = category
        self.severity = severity
        self.token = token


class PersonalPathCheckTests(unittest.TestCase):
    def test_green_when_no_personal_path_blockers(self) -> None:
        mod = _VERIFY.PortabilityModule()
        fake_findings = [
            _FakeFinding("docs/x.md", 1, "third_party_source_path", "blocker", "x"),
            _FakeFinding("docs/y.md", 2, "username_marker", "warning", "fixture-user"),
        ]
        with mock.patch("oss_release_scan.scan", return_value=fake_findings):
            r = mod.check_oss_scan_scope_all_personal_path(Path("/nonexistent"))
        self.assertEqual(r.status, "pass")
        self.assertEqual(r.metric, "0 blockers")

    def test_red_when_personal_path_blocker_present(self) -> None:
        mod = _VERIFY.PortabilityModule()
        fixture_token = str(_fictional_home())
        fake_findings = [
            _FakeFinding("docs/plans/x.md", 9, "personal_path", "blocker", fixture_token),
        ]
        with mock.patch("oss_release_scan.scan", return_value=fake_findings):
            r = mod.check_oss_scan_scope_all_personal_path(Path("/nonexistent"))
        self.assertEqual(r.status, "fail")
        self.assertIn("1 blockers", r.metric)
        # detail surfaces the offending path for triage
        self.assertIn("docs/plans/x.md:9", r.detail)


class CorruptionClassifierTests(unittest.TestCase):
    def test_meta_lesson_backtick_in_allowlist_is_not_corruption(self) -> None:
        mod = _VERIFY.PortabilityModule()
        marker = _VERIFY._TABLE_COLLAPSE_MARKER
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # An allowlisted reference that documents the hazard.
            allowed_rel = "docs/plans/portability-hazard-reference.md"
            _write(root, allowed_rel, f"# plan\n\nSee hazard: {marker} is bad.\n")
            fake_allowed = frozenset({allowed_rel})
            with mock.patch.object(_VERIFY, "_CORRUPTION_LESSON_ALLOWLIST", fake_allowed):
                r = mod.check_corruption_artifacts(root)
        self.assertEqual(r.status, "pass")
        self.assertIn("local-lesson backticks=1", r.metric)

    def test_real_table_collapse_outside_allowlist_is_corruption(self) -> None:
        mod = _VERIFY.PortabilityModule()
        marker = _VERIFY._TABLE_COLLAPSE_MARKER
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "docs/plans/some_other_plan.md", f"# plan\n\n| {marker} extra |\n")
            r = mod.check_corruption_artifacts(root)
        self.assertEqual(r.status, "fail")
        self.assertIn("real table-collapse=1", r.metric)

    def test_double_substitution_is_corruption(self) -> None:
        mod = _VERIFY.PortabilityModule()
        marker = _VERIFY._DOUBLE_SUB_MARKER
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "docs/plans/other.md", f"# plan\n\n{marker}/foo\n")
            r = mod.check_corruption_artifacts(root)
        self.assertEqual(r.status, "fail")
        self.assertIn("double-substitution=1", r.metric)


class PublicCopyPersonalPathCheckTests(unittest.TestCase):
    def _run_public_copy(self, root: Path) -> _VERIFY.Result:
        import oss_release_scan as scan_mod

        env = dict(os.environ)
        env.pop(scan_mod.MARKER_ENV, None)
        with mock.patch.dict(os.environ, env, clear=True):
            return _VERIFY.PortabilityModule().check_oss_scan_public_copy_personal_path(root)

    def test_red_when_public_copy_has_personal_path(self) -> None:
        rel = "docs/plans/fixture-reference.md"
        fixture_path = _fictional_home() / "fixture-project" / "tool.py"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, rel, f"run {fixture_path}\n")
            _init_and_track(root)
            r = self._run_public_copy(root)
        self.assertEqual(r.status, "fail")
        self.assertEqual(r.metric, "1 blockers")
        self.assertIn(rel, r.detail)

    def test_green_when_public_copy_has_no_personal_path(self) -> None:
        placeholder = f"{_fictional_home().parent}/..."
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "docs/reference.md", f"the generic syntax is `{placeholder}`\n")
            _init_and_track(root)
            r = self._run_public_copy(root)
        self.assertEqual(r.status, "pass")
        self.assertEqual(r.metric, "0 blockers")


class TestScriptsCheckTests(unittest.TestCase):
    def test_discovery_matches_makefile_and_streams_combined_transcript(self) -> None:
        mod = _VERIFY.PortabilityModule()
        child_stdout = "Ran 7 tests in 0.001s\n\nFAILED (errors=1, skipped=1)\n"
        child_stderr = (
            "test_skipped (fixture) ... skipped 'fixture skip reason'\n"
            "ERROR: test_fixture (fixture)\n"
        )
        combined = child_stdout + child_stderr
        proc = mock.Mock(returncode=1, stdout=child_stdout, stderr=child_stderr)
        stderr = mock.Mock()

        with (
            mock.patch.object(_VERIFY, "_resolve_pybin", return_value="/fixture/python"),
            mock.patch.object(_VERIFY.subprocess, "run", return_value=proc) as run,
            mock.patch.object(_VERIFY.sys, "stderr", stderr),
        ):
            result = mod.check_test_scripts(Path("/fixture/repo"))

        run.assert_called_once()
        self.assertEqual(
            run.call_args.args[0],
            [
                "/fixture/python",
                "-B",
                "-m",
                "unittest",
                "discover",
                "-s",
                "scripts",
                "-p",
                "test_*.py",
                "-v",
            ],
        )
        self.assertNotIn("timeout", run.call_args.kwargs)
        stderr.write.assert_called_once_with(combined)
        self.assertEqual(
            result,
            _VERIFY.Result(
                "test-scripts (unittest discover)",
                "fail",
                "Ran 7 tests, 1 FAIL/ERROR",
                "ERROR: test_fixture (fixture)",
            ),
        )


class ScannerInputErrorTests(unittest.TestCase):
    def test_direct_scanner_input_errors_become_failed_results(self) -> None:
        import oss_release_scan as scan_mod

        mod = _VERIFY.PortabilityModule()
        with mock.patch("oss_release_scan.scan", side_effect=scan_mod.ScanInputError("fixture")):
            all_result = mod.check_oss_scan_scope_all_personal_path(Path("/nonexistent"))
            public_result = mod.check_oss_scan_public_copy_personal_path(Path("/nonexistent"))
        for result in (all_result, public_result):
            self.assertEqual(result.status, "fail")
            self.assertEqual(result.metric, "scanner input error")
            self.assertEqual(result.detail, "scanner configuration failed")

    def test_keepset_subprocess_input_error_is_failed_result(self) -> None:
        mod = _VERIFY.PortabilityModule()
        proc = mock.Mock(returncode=2, stdout="", stderr="error: scanner input is invalid\n")
        with mock.patch.object(_VERIFY.subprocess, "run", return_value=proc):
            result = mod.check_oss_scan_keepset(Path("/nonexistent"))
        self.assertEqual(result.status, "fail")
        self.assertEqual(result.metric, "scanner input error")
        self.assertEqual(result.detail, "scanner configuration failed")


class ResolvedUserHomePathTests(unittest.TestCase):
    def test_windows_child_path_is_resolved(self) -> None:
        import oss_release_scan as scan_mod

        home = "C:" + "\\" + "Users" + "\\" + "fixture-user"
        self.assertTrue(_VERIFY._has_resolved_user_home_path(home + "\\work", scan_mod.PERSONAL_PATH_RE))
        self.assertFalse(_VERIFY._has_resolved_user_home_path(home, scan_mod.PERSONAL_PATH_RE))


class InterpretTests(unittest.TestCase):
    def test_all_pass_interprets_clean(self) -> None:
        mod = _VERIFY.PortabilityModule()
        results = [
            _VERIFY.Result("make test-scripts", "pass", "0 fail"),
            _VERIFY.Result("oss-scan --scope all personal_path", "pass", "0 blockers"),
        ]
        self.assertIn("All applicable portability gates pass", mod.interpret(results))

    def test_warn_interpretation_surfaces_remediation(self) -> None:
        mod = _VERIFY.PortabilityModule()
        results = [
            _VERIFY.Result("manifest validity", "pass"),
            _VERIFY.Result(
                "manifest self-consistency",
                "warn",
                "3 field drift(s): committed=0, ignored_db=3",
                "ignored local archive DB drift: .tmp/planveyor_docs_archive.sqlite; remediation: delete",
            ),
        ]
        note = mod.interpret(results)
        self.assertIn("VERDICT remains GREEN", note)
        self.assertIn("manifest self-consistency", note)
        self.assertIn("ignored local archive DB drift", note)

    def test_personal_path_fail_flags_generic_responsibility(self) -> None:
        mod = _VERIFY.PortabilityModule()
        results = [
            _VERIFY.Result("make test-scripts", "pass"),
            _VERIFY.Result("oss-scan --scope all personal_path", "fail", "8 blockers"),
        ]
        note = mod.interpret(results)
        self.assertIn("portable-path verification VIOLATED", note)
        self.assertIn("responsibility", note)

    def test_non_personal_fail_does_not_claim_generic_responsibility(self) -> None:
        mod = _VERIFY.PortabilityModule()
        results = [_VERIFY.Result("manifest validity", "fail", "parse error")]
        note = mod.interpret(results)
        self.assertNotIn("portable-path verification VIOLATED", note)
        self.assertIn("manifest validity", note)


class RendererTests(unittest.TestCase):
    def _modules_out(self) -> list[dict]:
        return [
            {
                "name": "portability",
                "results": [
                    {"name": "check a", "status": "pass", "metric": "ok", "detail": ""},
                    {"name": "check b", "status": "fail", "metric": "bad", "detail": "why"},
                ],
                "interpretation": "2 check(s) failed",
            }
        ]

    def test_plain_includes_verdict_red_and_failures(self) -> None:
        out = _VERIFY._render_plain(self._modules_out())
        self.assertIn("VERDICT: RED", out)
        self.assertIn("[portability]", out)
        self.assertIn("FAIL", out)

    def test_json_is_parseable_and_carries_verdict(self) -> None:
        import json

        out = _VERIFY._render_json(self._modules_out())
        payload = json.loads(out)
        self.assertEqual(payload["verdict"], "RED")
        self.assertEqual(payload["modules"][0]["name"], "portability")

    def test_plain_green_when_all_pass(self) -> None:
        out = _VERIFY._render_plain(
            [{"name": "portability", "results": [{"name": "c", "status": "pass", "metric": "ok", "detail": ""}], "interpretation": "clean"}]
        )
        self.assertIn("VERDICT: GREEN", out)

    def test_plain_green_when_warn(self) -> None:
        out = _VERIFY._render_plain(
            [
                {
                    "name": "portability",
                    "results": [{"name": "c", "status": "warn", "metric": "stale local state", "detail": "remediate"}],
                    "interpretation": "warning only",
                }
            ]
        )
        self.assertIn("VERDICT: GREEN", out)
        self.assertIn("WARN", out)

    def test_json_green_when_warn(self) -> None:
        out = _VERIFY._render_json(
            [{"name": "portability", "results": [{"name": "c", "status": "warn", "metric": "stale", "detail": ""}], "interpretation": ""}]
        )
        payload = json.loads(out)
        self.assertEqual(payload["verdict"], "GREEN")
        self.assertEqual(payload["modules"][0]["results"][0]["status"], "warn")


class FullJsonOutputTests(unittest.TestCase):
    def test_full_json_keeps_child_transcript_on_stderr(self) -> None:
        mod = _VERIFY.PortabilityModule(full=True)
        child_stdout = "test_fixture (fixture) ... ok\nRan 3 tests in 0.001s\n"
        child_stderr = "ERROR: test_fixture (fixture)\n"
        proc = mock.Mock(returncode=1, stdout=child_stdout, stderr=child_stderr)
        stdout = io.StringIO()
        stderr = io.StringIO()

        def run_only_test_scripts(repo_root: Path) -> list[_VERIFY.Result]:
            return [mod.check_test_scripts(repo_root)]

        with (
            mock.patch.object(_VERIFY, "load_portability_rules", return_value=_VERIFY.GENERIC_PORTABILITY_RULES),
            mock.patch.object(_VERIFY, "_load_modules", return_value=[mod]) as load_modules,
            mock.patch.object(mod, "run", side_effect=run_only_test_scripts),
            mock.patch.object(_VERIFY, "_resolve_pybin", return_value="/fixture/python"),
            mock.patch.object(_VERIFY.subprocess, "run", return_value=proc),
            mock.patch.object(_VERIFY.sys, "stdout", stdout),
            mock.patch.object(_VERIFY.sys, "stderr", stderr),
        ):
            rc = _VERIFY.main(["--full", "--format", "json"])

        self.assertEqual(rc, 2)
        load_modules.assert_called_once()
        self.assertTrue(load_modules.call_args.kwargs["full"])
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["verdict"], "RED")
        self.assertEqual(payload["modules"][0]["results"][0]["metric"], "Ran 3 tests, 1 FAIL/ERROR")
        self.assertNotIn(child_stdout, stdout.getvalue())
        self.assertEqual(stderr.getvalue(), child_stdout + child_stderr)


class MainExitCodeTests(unittest.TestCase):
    def test_exit_2_on_fail(self) -> None:
        with mock.patch.object(_VERIFY, "_load_modules") as lm:
            mod = mock.Mock()
            mod.name = "portability"
            mod.run.return_value = [_VERIFY.Result("c", "fail", "bad")]
            mod.interpret.return_value = "failed"
            lm.return_value = [mod]
            with mock.patch("sys.stdout"):
                rc = _VERIFY.main(["--format", "json"])
        self.assertEqual(rc, 2)

    def test_exit_0_on_pass(self) -> None:
        with mock.patch.object(_VERIFY, "_load_modules") as lm:
            mod = mock.Mock()
            mod.name = "portability"
            mod.run.return_value = [_VERIFY.Result("c", "pass", "ok")]
            mod.interpret.return_value = "clean"
            lm.return_value = [mod]
            with mock.patch("sys.stdout"):
                rc = _VERIFY.main(["--format", "json"])
        self.assertEqual(rc, 0)

    def test_exit_0_on_warn(self) -> None:
        with mock.patch.object(_VERIFY, "_load_modules") as lm:
            mod = mock.Mock()
            mod.name = "portability"
            mod.run.return_value = [_VERIFY.Result("c", "warn", "stale local state")]
            mod.interpret.return_value = "warning only"
            lm.return_value = [mod]
            with mock.patch("sys.stdout"):
                rc = _VERIFY.main(["--format", "json"])
        self.assertEqual(rc, 0)

    def test_unknown_module_exits_nonzero(self) -> None:
        # Gate-script convention: usage errors exit 2 (not argparse's 1).
        with self.assertRaises(SystemExit) as cm:
            _VERIFY._load_modules(["does_not_exist"])
        self.assertEqual(cm.exception.code, 2)


class PybinResolveTests(unittest.TestCase):
    """The verifier must use its trusted interpreter, not a project file."""

    def test_project_file_and_ambient_pybin_cannot_select_executable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            canary = root / "executed"
            hostile = root / "hostile-python"
            hostile.write_text(f"#!/bin/sh\nprintf ran > {canary}\n", encoding="utf-8")
            hostile.chmod(0o755)
            (root / ".planveyor.pybin").write_text(f"{hostile}\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"PYBIN": str(hostile)}, clear=False):
                resolved = _VERIFY._resolve_pybin(root)
            self.assertEqual(resolved, sys.executable)
            self.assertFalse(canary.exists())

    def test_missing_cache_uses_current_executable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(_VERIFY._resolve_pybin(Path(tmp)), sys.executable)


class SelfExclusionTests(unittest.TestCase):
    """The verifier must not flag its own marker literals."""

    def test_verify_suite_source_excluded_from_iter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "scripts/verify_suite.py", "# fake\n")
            _write(root, "scripts/other.py", "# real\n")
            files = [p.relative_to(root).as_posix() for p in _VERIFY._iter_text_files(root, ("scripts",))]
        self.assertNotIn("scripts/verify_suite.py", files)
        self.assertIn("scripts/other.py", files)


class ScopeAllKwargsTests(unittest.TestCase):
    """check_oss_scan_scope_all_personal_path must call scan with scope='all'.

    Locks the regression that once produced a false-green: the gate exists to
    catch historical-corpus residuals, so scope must be 'all' (which includes
    HISTORICAL_DIRS), never 'keep-set' (which skips them).
    """

    def test_scan_called_with_scope_all(self) -> None:
        mod = _VERIFY.PortabilityModule()
        with mock.patch("oss_release_scan.scan", return_value=[]) as mocked:
            mod.check_oss_scan_scope_all_personal_path(Path("/nonexistent"))
        mocked.assert_called_once()
        self.assertEqual(mocked.call_args.kwargs.get("scope"), "all")


class HomebrewOutsideMetaScopeTests(unittest.TestCase):
    """The homebrew check must scan ALL docs/ text files, not just *.md."""

    def test_red_when_homebrew_in_non_md_file(self) -> None:
        mod = _VERIFY.PortabilityModule()
        homebrew = _VERIFY._HOMEBREW_PY
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # A dotfile NOT in the homebrew allowlist (arbitrary name) — must fail.
            _write(root, "docs/tools/dotfiles/other/zshrc", f"  zcode_python=\"{homebrew}\"\n")
            r = mod.check_homebrew_outside_meta(root)
        self.assertEqual(r.status, "fail")
        self.assertIn("docs/tools/dotfiles/other/zshrc", r.detail)

    def test_green_when_homebrew_only_in_allowlisted_file(self) -> None:
        mod = _VERIFY.PortabilityModule()
        homebrew = _VERIFY._HOMEBREW_PY
        # The canonical allowlisted dotfile (docs/tools/dotfiles/zsh/zshrc).
        allowed_rel = "docs/tools/dotfiles/zsh/zshrc"
        self.assertIn(allowed_rel, _VERIFY._HOMEBREW_GATE_ALLOWLIST)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, allowed_rel, f"  zcode_python=\"{homebrew}\"\n")
            r = mod.check_homebrew_outside_meta(root)
        self.assertEqual(r.status, "pass")

    def test_zshrc_exception_is_verifier_local(self) -> None:
        gate = set(_VERIFY._HOMEBREW_GATE_ALLOWLIST)
        self.assertIn("docs/tools/dotfiles/zsh/zshrc", gate)
        self.assertNotIn("docs/tools/dotfiles/zsh/zshrc", _VERIFY._CORRUPTION_LESSON_ALLOWLIST)


class _ExplicitArchiveSnapshotTestCase(unittest.TestCase):
    """Keep existing archive-negative bodies explicit without changing their assertions."""

    def setUp(self) -> None:
        super().setUp()
        original = _VERIFY.PortabilityModule

        def construct(*args, **kwargs):
            kwargs.setdefault("archive_snapshot", "docs/_meta/archive_snapshots/current")
            return original(*args, **kwargs)

        patcher = mock.patch.object(_VERIFY, "PortabilityModule", new=construct)
        patcher.start()
        self.addCleanup(patcher.stop)


class ArchiveDbLabelPortabilityTests(_ExplicitArchiveSnapshotTestCase):
    """check_archive_db_label_portability must catch generic user-home paths."""

    def _record(self, db_label: str) -> str:
        import json

        meta = {"tool": "docs_archive", "db": db_label}
        rec = {"original_path": "docs/x.md", "extra_json": json.dumps(meta)}
        return json.dumps(rec)

    def _minimal_manifest(self, root) -> Path:
        """Write a minimal manifest so checks can read manifest.artifact.path."""
        root = Path(root)
        man = root / "docs" / "_meta" / "archive_snapshots" / "current" / "manifest.json"
        man.parent.mkdir(parents=True, exist_ok=True)
        man.write_text(json.dumps({"artifact": {"path": "archived_docs.jsonl"}}) + "\n", encoding="utf-8")
        return man

    def test_red_when_db_label_carries_generic_resolved_path(self) -> None:
        mod = _VERIFY.PortabilityModule()
        db_path = _fictional_home() / "fixture-project" / "x.sqlite"
        with tempfile.TemporaryDirectory() as tmp:
            self._minimal_manifest(tmp)
            self._dump(tmp, self._record(str(db_path)) + "\n")
            r = mod.check_archive_db_label_portability(Path(tmp))
        self.assertEqual(r.status, "fail")
        self.assertIn("0/1 records clean", r.metric)

    def test_green_when_db_label_portable(self) -> None:
        mod = _VERIFY.PortabilityModule()
        with tempfile.TemporaryDirectory() as tmp:
            self._minimal_manifest(tmp)
            portable = "${PLANVEYOR_ROOT:-$HOME/planveyor}/x.sqlite"
            self._dump(tmp, self._record(portable) + "\n")
            r = mod.check_archive_db_label_portability(Path(tmp))
        self.assertEqual(r.status, "pass")
        self.assertIn("1/1 records clean", r.metric)

    def test_fail_when_manifest_missing(self) -> None:
        """Fail-closed: no manifest means the gate checks nothing -> FAIL."""
        mod = _VERIFY.PortabilityModule()
        with tempfile.TemporaryDirectory() as tmp:
            r = mod.check_archive_db_label_portability(Path(tmp))
        self.assertEqual(r.status, "fail")

    def test_fail_when_dump_absent_but_manifest_present(self) -> None:
        """Fail-closed: manifest present but dump file missing -> FAIL (not warn)."""
        mod = _VERIFY.PortabilityModule()
        with tempfile.TemporaryDirectory() as tmp:
            self._minimal_manifest(tmp)  # manifest exists, dump does not
            r = mod.check_archive_db_label_portability(Path(tmp))
        self.assertEqual(r.status, "fail")
        self.assertIn("archive dump absent", r.detail)

    def _dump(self, root, body: str) -> Path:
        root = Path(root)
        dump = root / "docs" / "_meta" / "archive_snapshots" / "current" / "archived_docs.jsonl"
        dump.parent.mkdir(parents=True, exist_ok=True)
        dump.write_text(body, encoding="utf-8")
        return dump

    def test_red_when_db_label_carries_bare_generic_home_token(self) -> None:
        """A db label is a location field, so a bare home token is invalid."""
        mod = _VERIFY.PortabilityModule()
        bare_home = _fictional_home("bare-fixture-user")
        with tempfile.TemporaryDirectory() as tmp:
            self._minimal_manifest(tmp)
            self._dump(tmp, self._record(str(bare_home)) + "\n")
            r = mod.check_archive_db_label_portability(Path(tmp))
        self.assertEqual(r.status, "fail")
        self.assertIn("0/1 records clean", r.metric)

    def test_dump_located_via_manifest_renamed_artifact_path(self) -> None:
        """The dump is found via manifest.artifact.path, not a hardcoded basename.

        Locks the S3 gap: check_archive_db_label_portability must read the
        manifest-declared artifact name. A manifest naming a NON-default file
        (renamed_docs.jsonl) with a clean record under THAT name must PASS; a
        hardcode would look for archived_docs.jsonl and report 'archive dump
        absent' instead. (Nested/absolute paths are rejected by the contract —
        see verify_suite.py _manifest_artifact_path guard — so only a bare
        renamed basename is valid.)
        """
        mod = _VERIFY.PortabilityModule()
        portable = "${PLANVEYOR_ROOT:-$HOME/planveyor}/x.sqlite"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snap = root / "docs" / "_meta" / "archive_snapshots" / "current"
            snap.mkdir(parents=True, exist_ok=True)
            (snap / "manifest.json").write_text(
                json.dumps({"artifact": {"path": "renamed_docs.jsonl"}}) + "\n", encoding="utf-8"
            )
            (snap / "renamed_docs.jsonl").write_text(self._record(portable) + "\n", encoding="utf-8")
            r = mod.check_archive_db_label_portability(root)
        self.assertEqual(r.status, "pass")
        self.assertNotIn("absent", r.detail)  # proves it read the renamed file, not defaulted
        self.assertIn("1/1 records clean", r.metric)

    def test_red_when_jsonl_record_malformed(self) -> None:
        """Fail-closed: a malformed JSONL line is a leak, not a silent skip."""
        mod = _VERIFY.PortabilityModule()
        with tempfile.TemporaryDirectory() as tmp:
            self._minimal_manifest(tmp)
            self._dump(tmp, "{not valid json\n")
            r = mod.check_archive_db_label_portability(Path(tmp))
        self.assertEqual(r.status, "fail")
        self.assertIn("malformed JSONL", r.detail)

    def test_red_when_extra_json_malformed(self) -> None:
        """Fail-closed: valid JSONL but malformed extra_json is a leak."""
        mod = _VERIFY.PortabilityModule()
        with tempfile.TemporaryDirectory() as tmp:
            rec = json.dumps({"original_path": "docs/x.md", "extra_json": "{bad extra"})
            self._minimal_manifest(tmp)
            self._dump(tmp, rec + "\n")
            r = mod.check_archive_db_label_portability(Path(tmp))
        self.assertEqual(r.status, "fail")
        self.assertIn("malformed extra_json", r.detail)

    def test_red_when_record_missing_extra_json_key(self) -> None:
        """Fail-closed: a record lacking the extra_json key is a leak."""
        mod = _VERIFY.PortabilityModule()
        with tempfile.TemporaryDirectory() as tmp:
            self._minimal_manifest(tmp)
            self._dump(tmp, json.dumps({"original_path": "docs/x.md"}) + "\n")
            r = mod.check_archive_db_label_portability(Path(tmp))
        self.assertEqual(r.status, "fail")
        self.assertIn("missing extra_json", r.detail)

    def test_red_when_extra_json_is_non_object(self) -> None:
        """Fail-closed: valid-but-non-object extra_json (e.g. [], 42) is a leak.

        A non-object cannot carry/inspect a db key, so it cannot be trusted
        clean. Locks the S3 fail-open shape case.
        """
        mod = _VERIFY.PortabilityModule()
        with tempfile.TemporaryDirectory() as tmp:
            self._minimal_manifest(tmp)
            self._dump(tmp, json.dumps({"original_path": "docs/x.md", "extra_json": "[]"}) + "\n")
            r = mod.check_archive_db_label_portability(Path(tmp))
        self.assertEqual(r.status, "fail")
        self.assertIn("non-object extra_json", r.detail)

    def test_mixed_clean_and_leaking_reports_leak_count(self) -> None:
        """One clean + one leaking record -> 1/2 clean, status fail."""
        mod = _VERIFY.PortabilityModule()
        personal_db = _fictional_home() / "x.sqlite"
        portable = "${PLANVEYOR_ROOT:-$HOME/planveyor}/x.sqlite"
        with tempfile.TemporaryDirectory() as tmp:
            self._minimal_manifest(tmp)
            self._dump(tmp, self._record(portable) + "\n" + self._record(str(personal_db)) + "\n")
            r = mod.check_archive_db_label_portability(Path(tmp))
        self.assertEqual(r.status, "fail")
        self.assertIn("1/2 records clean", r.metric)


class ArchiveContentPortabilityTests(_ExplicitArchiveSnapshotTestCase):
    """Content must be rule-idempotent and free of resolved user-home paths."""

    def _minimal_manifest(self, root) -> Path:
        root = Path(root)
        man = root / "docs" / "_meta" / "archive_snapshots" / "current" / "manifest.json"
        man.parent.mkdir(parents=True, exist_ok=True)
        man.write_text(json.dumps({"artifact": {"path": "archived_docs.jsonl"}}) + "\n", encoding="utf-8")
        return man

    def _dump(self, root, body: str) -> Path:
        root = Path(root)
        dump = root / "docs" / "_meta" / "archive_snapshots" / "current" / "archived_docs.jsonl"
        dump.parent.mkdir(parents=True, exist_ok=True)
        dump.write_text(body, encoding="utf-8")
        return dump

    def _record(self, content: str) -> str:
        import hashlib as _h

        rec = {"original_path": "docs/x.md", "sha256": _h.sha256(content.encode()).hexdigest(), "content": content}
        return json.dumps(rec)

    def test_red_when_content_non_idempotent_under_explicit_rules(self) -> None:
        home = _fictional_home()
        rules = _VERIFY.PortabilityRules(
            literal_rules=((str(home), _VERIFY._PORTABLE_FULL),),
            miniforge_replacement="python3",
            homebrew_source="/opt/homebrew/bin/python",
            homebrew_replacement="python3",
            primary_product_source=None,
            primary_product_replacement=None,
            preserve_version_pinned_receipt=True,
        )
        mod = _VERIFY.PortabilityModule(portability_rules=rules)
        dirty_content = f"# Plan\n\nrun `{home}`\n"
        with tempfile.TemporaryDirectory() as tmp:
            self._minimal_manifest(tmp)
            self._dump(tmp, self._record(dirty_content) + "\n")
            r = mod.check_archive_content_portability(Path(tmp))
        self.assertEqual(r.status, "fail")
        self.assertIn("0/1 records portability-clean", r.metric)
        self.assertIn("non-idempotent", r.detail)

    def test_green_when_content_already_portabilized(self) -> None:
        mod = _VERIFY.PortabilityModule()
        clean = "# Plan\n\nrun ${PLANVEYOR_ROOT:-$HOME/planveyor}/scripts/foo.py\n"
        with tempfile.TemporaryDirectory() as tmp:
            self._minimal_manifest(tmp)
            self._dump(tmp, self._record(clean) + "\n")
            r = mod.check_archive_content_portability(Path(tmp))
        self.assertEqual(r.status, "pass")

    def test_green_for_idempotent_prose_placeholder(self) -> None:
        """A literal scanner placeholder quoted as subject is NOT a leak.

        portabilize_text leaves escaped/redacted placeholder forms unchanged;
        such content is idempotent and must PASS the gate.
        """
        mod = _VERIFY.PortabilityModule()
        # content already equal to its portabilized form (idempotent).
        placeholder = f"{_fictional_home().parent}/..."
        prose = f"# Plan\n\nthe pattern `{placeholder}` denotes generic user-home syntax.\n"
        import sys

        sys.path.insert(0, "scripts")
        from portability_substitution import portabilize_text  # noqa: E402

        self.assertEqual(prose, portabilize_text(prose))  # precondition: idempotent
        with tempfile.TemporaryDirectory() as tmp:
            self._minimal_manifest(tmp)
            self._dump(tmp, self._record(prose) + "\n")
            r = mod.check_archive_content_portability(Path(tmp))
        self.assertEqual(r.status, "pass")

    def test_red_for_generic_resolved_path_independent_of_rules(self) -> None:
        """A resolved generic user-home path fails even when rule-idempotent."""
        mod = _VERIFY.PortabilityModule()
        personal_path = _fictional_home() / "private-project" / "foo.py"
        content = f"# Plan\n\nrun {personal_path}\n"
        with tempfile.TemporaryDirectory() as tmp:
            self._minimal_manifest(tmp)
            self._dump(tmp, self._record(content) + "\n")
            r = mod.check_archive_content_portability(Path(tmp))
        self.assertEqual(r.status, "fail")
        self.assertIn("0/1 records portability-clean", r.metric)
        self.assertIn("resolved-user-home-path", r.detail)

    def test_red_for_generic_deep_path(self) -> None:
        """A deep path is rejected without a user-specific substitution rule."""
        mod = _VERIFY.PortabilityModule()
        deep_path = _fictional_home("second-fixture-user") / "unknown-sibling" / "foo.py"
        content = f"# Plan\n\nrun `{deep_path}`\n"
        with tempfile.TemporaryDirectory() as tmp:
            self._minimal_manifest(tmp)
            self._dump(tmp, self._record(content) + "\n")
            r = mod.check_archive_content_portability(Path(tmp))
        self.assertEqual(r.status, "fail")
        self.assertIn("0/1 records portability-clean", r.metric)
        self.assertIn("resolved-user-home-path", r.detail)

    def test_red_for_generic_single_component_paths(self) -> None:
        """One-component paths and dotfiles are resolved paths, not prose."""
        mod = _VERIFY.PortabilityModule()
        home = _fictional_home("single-fixture-user")
        private_path = home / "private-project"
        zsh_path = home / ".zshrc"
        bash_path = home / ".bash_profile"
        with tempfile.TemporaryDirectory() as tmp:
            self._minimal_manifest(tmp)
            self._dump(tmp, self._record(f"# Plan\n\nrun `{private_path}`\n") + "\n"
                       + self._record(f"# Plan\n\ncat `{zsh_path}`\n") + "\n"
                       + self._record(f"# Plan\n\nsource `{bash_path}`\n") + "\n")
            r = mod.check_archive_content_portability(Path(tmp))
        self.assertEqual(r.status, "fail")
        self.assertIn("0/3 records portability-clean", r.metric)
        self.assertIn("resolved-user-home-path", r.detail)

    def test_red_for_sentence_and_redacted_resolved_forms(self) -> None:
        """Legacy prose-shaped resolved paths are still concrete paths."""
        mod = _VERIFY.PortabilityModule()
        home = _fictional_home("legacy-fixture-user")
        prose_period = f"# Plan\n\n...without editing {home / 'fixture-project'}.\n"
        prose_redacted = f"# Plan\n\nrunnable receipts (`PYBIN={home / 'miniforge3'}/...`)\n"
        home_redacted = f"# Plan\n\nlegacy root `{home / '...'}`\n"
        with tempfile.TemporaryDirectory() as tmp:
            self._minimal_manifest(tmp)
            self._dump(tmp, self._record(prose_period) + "\n"
                       + self._record(prose_redacted) + "\n"
                       + self._record(home_redacted) + "\n")
            r = mod.check_archive_content_portability(Path(tmp))
        self.assertEqual(r.status, "fail")
        self.assertIn("0/3 records portability-clean", r.metric)
        self.assertIn("resolved-user-home-path", r.detail)

    def test_green_for_bare_user_home_token_in_prose(self) -> None:
        """A bare generic home token can be prose rather than a resolved path."""
        mod = _VERIFY.PortabilityModule()
        home = _fictional_home()
        prose_isolated = f"# Plan\n\ngit grep: `{home}` = fixture references.\n"
        with tempfile.TemporaryDirectory() as tmp:
            self._minimal_manifest(tmp)
            self._dump(tmp, self._record(prose_isolated) + "\n")
            r = mod.check_archive_content_portability(Path(tmp))
        self.assertEqual(r.status, "pass")
        self.assertIn("1/1 records portability-clean", r.metric)

    def test_dump_located_via_manifest_renamed_artifact_path(self) -> None:
        """The dump is found via manifest.artifact.path, not a hardcoded basename.

        Locks the S3 gap for the content gate: a manifest declaring a non-default
        artifact name (renamed_docs.jsonl) must cause the check to read THAT
        file. A hardcode would report 'archive dump absent'. (The contract
        rejects nested paths — verify_suite.py _manifest_artifact_path guard —
        so only a bare renamed basename is valid.)
        """
        mod = _VERIFY.PortabilityModule()
        clean = "# Plan\nrun ${PLANVEYOR_ROOT:-$HOME/planveyor}/scripts/foo.py\n"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snap = root / "docs" / "_meta" / "archive_snapshots" / "current"
            snap.mkdir(parents=True, exist_ok=True)
            (snap / "manifest.json").write_text(
                json.dumps({"artifact": {"path": "renamed_docs.jsonl"}}) + "\n", encoding="utf-8"
            )
            (snap / "renamed_docs.jsonl").write_text(self._record(clean) + "\n", encoding="utf-8")
            r = mod.check_archive_content_portability(root)
        self.assertEqual(r.status, "pass")
        self.assertNotIn("absent", r.detail)
        self.assertIn("1/1 records portability-clean", r.metric)

    def test_red_when_jsonl_malformed(self) -> None:
        """Fail-closed: malformed JSONL is a leak, not a skip."""
        mod = _VERIFY.PortabilityModule()
        with tempfile.TemporaryDirectory() as tmp:
            self._minimal_manifest(tmp)
            self._dump(tmp, "{not json\n")
            r = mod.check_archive_content_portability(Path(tmp))
        self.assertEqual(r.status, "fail")
        self.assertIn("malformed JSONL", r.detail)

    def test_fail_when_manifest_missing(self) -> None:
        """Fail-closed: no manifest -> the gate checks nothing -> FAIL."""
        mod = _VERIFY.PortabilityModule()
        with tempfile.TemporaryDirectory() as tmp:
            r = mod.check_archive_content_portability(Path(tmp))
        self.assertEqual(r.status, "fail")

    def test_fail_when_dump_absent_but_manifest_present(self) -> None:
        """Fail-closed: manifest present but dump missing -> FAIL (not warn)."""
        mod = _VERIFY.PortabilityModule()
        with tempfile.TemporaryDirectory() as tmp:
            self._minimal_manifest(tmp)
            r = mod.check_archive_content_portability(Path(tmp))
        self.assertEqual(r.status, "fail")
        self.assertIn("archive dump absent", r.detail)


class ManifestSelfConsistencyTests(_ExplicitArchiveSnapshotTestCase):
    """check_manifest_self_consistency must catch stale derived fields.

    Locks the S2 finding: a sweep that patches artifact.size_bytes/sha256 but
    leaves storage_matrix[git_text_export].size_bytes stale must FAIL, not GREEN.
    """

    def _setup(self, tmp: str, *, record_body: str, manifest: dict) -> Path:
        root = Path(tmp)
        art = root / "docs" / "_meta" / "archive_snapshots" / "current" / "archived_docs.jsonl"
        art.parent.mkdir(parents=True, exist_ok=True)
        art.write_text(record_body, encoding="utf-8")
        man = root / "docs" / "_meta" / "archive_snapshots" / "current" / "manifest.json"
        man.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        return root

    def _consistent_manifest(self, *, size: int, sha: str, records: int, kind_counts: dict | None = None) -> dict:
        # Default kind_counts mirrors the test fixtures' records (which carry no
        # `kind` field, so the actual per-kind distribution is {"": records}).
        if kind_counts is None:
            kind_counts = {"": records}
        return {
            "artifact": {"path": "archived_docs.jsonl", "size_bytes": size, "sha256": sha, "record_count": records},
            "storage_matrix": [{"backend": "git_text_export", "selected": True, "size_bytes": size}],
            "source_db": {"docs_count": records, "kind_counts": kind_counts, "content_bytes": 0},
        }

    def test_green_when_all_fields_match_artifact(self) -> None:
        mod = _VERIFY.PortabilityModule()
        import hashlib

        body = '{"original_path":"docs/a.md"}\n{"original_path":"docs/b.md"}\n'
        size = len(body.encode("utf-8"))
        sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup(tmp, record_body=body, manifest=self._consistent_manifest(size=size, sha=sha, records=2))
            r = mod.check_manifest_self_consistency(root)
        self.assertEqual(r.status, "pass")
        self.assertIn("0 field drift", r.metric)

    def test_green_when_optional_ignored_db_matches_manifest(self) -> None:
        mod = _VERIFY.PortabilityModule()
        import hashlib
        import sqlite3

        body = '{"original_path":"docs/a.md"}\n'
        size = len(body.encode("utf-8"))
        sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup(tmp, record_body=body, manifest=self._consistent_manifest(size=size, sha=sha, records=1))
            dbp = root / ".tmp" / "fake.sqlite"
            dbp.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(dbp))
            conn.execute("CREATE TABLE archived_docs (content TEXT)")
            conn.execute("INSERT INTO archived_docs VALUES ('hello')")
            conn.commit()
            conn.close()
            db_bytes = dbp.read_bytes()
            manifest = self._consistent_manifest(size=size, sha=sha, records=1)
            manifest["source_db"]["db_path"] = ".tmp/fake.sqlite"
            manifest["source_db"]["db_sha256"] = hashlib.sha256(db_bytes).hexdigest()
            manifest["source_db"]["db_size_bytes"] = len(db_bytes)
            manifest["source_db"]["content_bytes"] = len("hello")
            (root / "docs" / "_meta" / "archive_snapshots" / "current" / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
            )
            r = mod.check_manifest_self_consistency(root)
        self.assertEqual(r.status, "pass")
        self.assertIn("0 field drift", r.metric)

    def test_red_when_storage_matrix_size_stale(self) -> None:
        mod = _VERIFY.PortabilityModule()
        import hashlib

        body = '{"original_path":"docs/a.md"}\n'
        size = len(body.encode("utf-8"))
        sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
        manifest = self._consistent_manifest(size=size, sha=sha, records=1)
        # Simulate the exact S2 bug: storage_matrix size left at a stale value.
        manifest["storage_matrix"][0]["size_bytes"] = size - 999
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup(tmp, record_body=body, manifest=manifest)
            r = mod.check_manifest_self_consistency(root)
        self.assertEqual(r.status, "fail")
        self.assertIn("storage_matrix[git_text_export].size_bytes", r.detail)

    def test_red_when_artifact_sha_mismatch(self) -> None:
        mod = _VERIFY.PortabilityModule()
        body = '{"original_path":"docs/a.md"}\n'
        size = len(body.encode("utf-8"))
        manifest = self._consistent_manifest(size=size, sha="deadbeef" + "0" * 56, records=1)
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup(tmp, record_body=body, manifest=manifest)
            r = mod.check_manifest_self_consistency(root)
        self.assertEqual(r.status, "fail")
        self.assertIn("artifact.sha256", r.detail)

    def test_red_when_committed_artifact_drift_even_with_ignored_db_drift(self) -> None:
        mod = _VERIFY.PortabilityModule()
        import hashlib

        body = '{"original_path":"docs/a.md"}\n'
        size = len(body.encode("utf-8"))
        manifest = self._consistent_manifest(size=size, sha="deadbeef" + "0" * 56, records=1)
        db_bytes = b"FAKE-SQLITE-BYTES"
        manifest["source_db"]["db_path"] = ".tmp/fake.sqlite"
        manifest["source_db"]["db_size_bytes"] = len(db_bytes) + 1
        manifest["source_db"]["db_sha256"] = hashlib.sha256(db_bytes).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup(tmp, record_body=body, manifest=manifest)
            self._write_db(root, ".tmp/fake.sqlite", db_bytes)
            r = mod.check_manifest_self_consistency(root)
        self.assertEqual(r.status, "fail")
        self.assertIn("artifact.sha256", r.detail)
        self.assertIn("ignored local archive DB drift", r.detail)
        self.assertIn("source_db.db_size_bytes", r.detail)

    def test_red_when_record_count_vs_docs_count_mismatch(self) -> None:
        mod = _VERIFY.PortabilityModule()
        import hashlib

        body = '{"original_path":"docs/a.md"}\n'
        size = len(body.encode("utf-8"))
        sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
        manifest = self._consistent_manifest(size=size, sha=sha, records=1)
        manifest["source_db"]["docs_count"] = 99  # drifts from artifact records
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup(tmp, record_body=body, manifest=manifest)
            r = mod.check_manifest_self_consistency(root)
        self.assertEqual(r.status, "fail")
        self.assertIn("docs_count=99", r.detail)

    def _write_db(self, root: Path, rel: str, db_bytes: bytes) -> None:
        dbp = root / rel
        dbp.parent.mkdir(parents=True, exist_ok=True)
        dbp.write_bytes(db_bytes)

    def test_warn_when_content_bytes_drift_in_ignored_db(self) -> None:
        """WHEN ignored .tmp DB exists, content_bytes drift is warning-only.

        content_bytes is a DB-DESCRIBING metric (producer docs_archive.py:449
        sum(length(CAST(content AS BLOB))) over the RAW DB, NOT the portabilized
        JSONL — portabilize changes byte length). So it is verified against the
        DB when present (recomputed via the same SQL) and skipped when absent.
        Because this DB is ignored local state, DB-only drift is WARN/GREEN with
        remediation instead of RED.
        This test writes a real minimal sqlite so the SQL can run, and declares a
        drifted content_bytes -> WARN. db_sha256/db_size_bytes are set to the
        REAL file values so the failure ISOLATES to content_bytes (not masked by
        a simultaneous sha/size drift).
        """
        mod = _VERIFY.PortabilityModule()
        import hashlib
        import sqlite3

        body = '{"original_path":"docs/a.md"}\n'
        size = len(body.encode("utf-8"))
        sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup(tmp, record_body=body, manifest=self._consistent_manifest(size=size, sha=sha, records=1))
            # Build a REAL minimal sqlite matching the producer's archived_docs
            # schema so the content_bytes SQL can execute.
            dbp = root / ".tmp" / "fake.sqlite"
            dbp.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(dbp))
            conn.execute("CREATE TABLE archived_docs (content TEXT)")
            conn.execute("INSERT INTO archived_docs VALUES ('hello')")
            conn.commit()
            conn.close()
            # Pin db_sha256/db_size_bytes to the REAL file so ONLY content_bytes
            # drifts (isolation): content 'hello' -> actual content_bytes = 5,
            # but we declare 999 below.
            real_db_bytes = dbp.read_bytes()
            manifest = self._consistent_manifest(size=size, sha=sha, records=1)
            manifest["source_db"]["db_path"] = ".tmp/fake.sqlite"
            manifest["source_db"]["db_sha256"] = hashlib.sha256(real_db_bytes).hexdigest()
            manifest["source_db"]["db_size_bytes"] = len(real_db_bytes)
            manifest["source_db"]["content_bytes"] = 999  # actual = len("hello") = 5 -> drift
            # Re-write the manifest with the isolated (only-content_bytes-drift) source_db.
            (root / "docs" / "_meta" / "archive_snapshots" / "current" / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
            )
            r = mod.check_manifest_self_consistency(root)
        self.assertEqual(r.status, "warn")
        self.assertIn("VERDICT: GREEN", _VERIFY._render_plain([{"name": "portability", "results": [r.__dict__], "interpretation": ""}]))
        self.assertIn("ignored local archive DB drift", r.detail)
        self.assertIn("remediation", r.detail)
        self.assertIn("source_db.content_bytes", r.detail)
        # Isolation: sha/size do NOT also drift (only content_bytes in detail).
        self.assertNotIn("source_db.db_sha256", r.detail)
        self.assertNotIn("source_db.db_size_bytes", r.detail)

    def test_warn_when_malformed_ignored_db_present(self) -> None:
        """A present unreadable ignored DB is warning-only with remediation.

        The fake DB need not be real sqlite. The suite still hashes file bytes,
        and the SQLite read failure is reported as local ignored state rather
        than committed manifest corruption.
        """
        mod = _VERIFY.PortabilityModule()
        import hashlib

        body = '{"original_path":"docs/a.md"}\n'
        size = len(body.encode("utf-8"))
        sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
        db_bytes = b"FAKE-SQLITE-BYTES"
        manifest = self._consistent_manifest(size=size, sha=sha, records=1)
        manifest["source_db"]["db_path"] = ".tmp/fake.sqlite"
        manifest["source_db"]["db_size_bytes"] = len(db_bytes)
        manifest["source_db"]["db_sha256"] = "deadbeef" + "0" * 56  # mutated
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup(tmp, record_body=body, manifest=manifest)
            self._write_db(root, ".tmp/fake.sqlite", db_bytes)
            r = mod.check_manifest_self_consistency(root)
        self.assertEqual(r.status, "warn")
        self.assertIn("ignored local archive DB drift", r.detail)
        self.assertIn("content_bytes recompute failed", r.detail)
        self.assertIn("source_db.db_sha256", r.detail)

    def test_warn_when_db_size_bytes_drift_in_ignored_db(self) -> None:
        """WHEN the ignored .tmp DB exists, db_size_bytes drift is warning-only."""
        mod = _VERIFY.PortabilityModule()
        import hashlib

        body = '{"original_path":"docs/a.md"}\n'
        size = len(body.encode("utf-8"))
        sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
        db_bytes = b"FAKE-SQLITE-BYTES"
        manifest = self._consistent_manifest(size=size, sha=sha, records=1)
        manifest["source_db"]["db_path"] = ".tmp/fake.sqlite"
        manifest["source_db"]["db_size_bytes"] = len(db_bytes) + 1  # mutated
        manifest["source_db"]["db_sha256"] = hashlib.sha256(db_bytes).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup(tmp, record_body=body, manifest=manifest)
            self._write_db(root, ".tmp/fake.sqlite", db_bytes)
            r = mod.check_manifest_self_consistency(root)
        self.assertEqual(r.status, "warn")
        self.assertIn("ignored local archive DB drift", r.detail)
        self.assertIn("source_db.db_size_bytes", r.detail)

    def test_db_sha_checked_when_db_path_is_producer_default_env_substituted(self) -> None:
        """db_sha256 is verified even when db_path is the producer's DEFAULT form.

        Locks the HOLE-1 follow-up: the producer emits db_path =
        portabilize_text(absolute) = ``${PLANVEYOR_ROOT:-$HOME/planveyor}/
        .tmp/...`` (docs_archive.py:464). A resolver that only handled the
        repo-relative ``.tmp/...`` form would silently SKIP db_sha/db_size for
        every producer-regenerated manifest (a permanent false-green). The
        env-substituted form MUST expand to repo_root so the present DB is
        actually checked. Here a mutated db_sha256 under that form must WARN.
        """
        mod = _VERIFY.PortabilityModule()
        import hashlib

        body = '{"original_path":"docs/a.md"}\n'
        size = len(body.encode("utf-8"))
        sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
        db_bytes = b"FAKE-SQLITE-BYTES"
        # Producer-default db_path form: env-substituted tooling-root prefix.
        portable_prefix = _VERIFY._PORTABLE_FULL
        manifest = self._consistent_manifest(size=size, sha=sha, records=1)
        manifest["source_db"]["db_path"] = f"{portable_prefix}/.tmp/fake.sqlite"
        manifest["source_db"]["db_size_bytes"] = len(db_bytes)
        manifest["source_db"]["db_sha256"] = "deadbeef" + "0" * 56  # mutated
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup(tmp, record_body=body, manifest=manifest)
            self._write_db(root, ".tmp/fake.sqlite", db_bytes)
            r = mod.check_manifest_self_consistency(root)
        self.assertEqual(r.status, "warn")
        self.assertIn("ignored local archive DB drift", r.detail)
        self.assertIn("source_db.db_sha256", r.detail)

    def test_skips_db_fields_when_db_absent_no_false_red(self) -> None:
        """Fresh clone: .tmp DB is gitignored/absent -> the three DB-describing
        metrics (content_bytes, db_sha256, db_size_bytes) are ALL SKIPPED.

        content_bytes is a DB-describing metric (producer docs_archive.py:449
        computes it over the RAW DB, not the portabilized JSONL), so like
        db_sha256/db_size_bytes it cannot be verified without the DB and is
        skipped on a fresh clone. Adversarial: sets ALL THREE to bogus values to
        prove they are skipped (not failed) when the DB is absent.
        """
        mod = _VERIFY.PortabilityModule()
        import hashlib

        body = '{"original_path":"docs/a.md","content":"hi"}\n'
        size = len(body.encode("utf-8"))
        sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
        manifest = self._consistent_manifest(size=size, sha=sha, records=1)
        manifest["source_db"]["content_bytes"] = 999999  # bogus, skipped (DB absent)
        manifest["source_db"]["db_path"] = ".tmp/absent.sqlite"
        manifest["source_db"]["db_sha256"] = "bogus_but_db_is_absent"
        manifest["source_db"]["db_size_bytes"] = 999999
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup(tmp, record_body=body, manifest=manifest)
            # Intentionally do NOT create .tmp/absent.sqlite.
            r = mod.check_manifest_self_consistency(root)
        self.assertEqual(r.status, "pass")
        self.assertIn("0 field drift", r.metric)

    def test_red_when_storage_matrix_empty(self) -> None:
        """Fail-closed: missing storage_matrix must FAIL, not silently pass.

        Locks the false-green where storage_matrix=[] or lacks a selected
        git_text_export row reported pass/0-field-drift.
        """
        mod = _VERIFY.PortabilityModule()
        import hashlib

        body = '{"original_path":"docs/a.md"}\n'
        size = len(body.encode("utf-8"))
        sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
        manifest = self._consistent_manifest(size=size, sha=sha, records=1)
        manifest["storage_matrix"] = []  # no selected row at all
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup(tmp, record_body=body, manifest=manifest)
            r = mod.check_manifest_self_consistency(root)
        self.assertEqual(r.status, "fail")
        self.assertIn("no selected git_text_export row", r.detail)

    def test_red_when_git_text_export_not_selected(self) -> None:
        """A git_text_export row that is not selected must FAIL (not skipped)."""
        mod = _VERIFY.PortabilityModule()
        import hashlib

        body = '{"original_path":"docs/a.md"}\n'
        size = len(body.encode("utf-8"))
        sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
        manifest = self._consistent_manifest(size=size, sha=sha, records=1)
        # Row present but deselected — selection drifted.
        manifest["storage_matrix"] = [{"backend": "git_text_export", "selected": False, "size_bytes": size}]
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup(tmp, record_body=body, manifest=manifest)
            r = mod.check_manifest_self_consistency(root)
        self.assertEqual(r.status, "fail")
        self.assertIn("no selected git_text_export row", r.detail)

    def test_artifact_path_read_from_manifest_not_hardcoded(self) -> None:
        """The artifact is located via manifest.artifact.path, not a hardcode.

        Locks the fix: a manifest pointing artifact.path at a non-default name
        must check that file (and report missing if it doesn't exist), rather
        than silently checking a hardcoded archived_docs.jsonl.
        """
        mod = _VERIFY.PortabilityModule()
        import hashlib

        body = '{"original_path":"docs/a.md"}\n'
        size = len(body.encode("utf-8"))
        sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
        manifest = self._consistent_manifest(size=size, sha=sha, records=1)
        manifest["artifact"]["path"] = "renamed_docs.jsonl"  # non-default name
        with tempfile.TemporaryDirectory() as tmp:
            # Write the artifact under the manifest-declared name only.
            root = Path(tmp)
            art = root / "docs" / "_meta" / "archive_snapshots" / "current" / "renamed_docs.jsonl"
            art.parent.mkdir(parents=True, exist_ok=True)
            art.write_text(body, encoding="utf-8")
            man = root / "docs" / "_meta" / "archive_snapshots" / "current" / "manifest.json"
            man.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
            r = mod.check_manifest_self_consistency(root)
        # Resolves the renamed artifact (exists) -> all fields match -> pass.
        self.assertEqual(r.status, "pass")

    def test_red_when_kind_counts_sum_exceeds_docs_count(self) -> None:
        """kind_counts that disagree with the ACTUAL JSONL distribution -> FAIL.

        Locks the S1/S2 finding: a hand-edit of kind_counts (sum or per-kind)
        that no longer matches the artifact must FAIL. The check compares the
        full per-kind distribution, not merely the sum, so a redistribution
        (same sum, different per-kind values) is also caught.
        """
        mod = _VERIFY.PortabilityModule()
        import hashlib

        body = '{"original_path":"docs/a.md"}\n'
        size = len(body.encode("utf-8"))
        sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
        manifest = self._consistent_manifest(size=size, sha=sha, records=1)
        # kind_counts disagrees with the actual distribution {"": 1}.
        manifest["source_db"]["kind_counts"] = {"plan": 1112, "code_draft": 593, "code_review": 401, "doc_review": 244}
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup(tmp, record_body=body, manifest=manifest)
            r = mod.check_manifest_self_consistency(root)
        self.assertEqual(r.status, "fail")
        self.assertIn("kind_counts", r.detail)

    def test_red_when_kind_counts_redistributed_same_sum(self) -> None:
        """A redistribution (same sum, different per-kind) must FAIL.

        Locks the S2 finding specifically: sum(kind_counts) == docs_count is NOT
        sufficient; the per-kind values must match the actual JSONL.
        """
        mod = _VERIFY.PortabilityModule()
        import hashlib

        # 2 records, both kind="plan" -> actual distribution {"plan": 2}.
        body = '{"kind":"plan","original_path":"docs/a.md"}\n{"kind":"plan","original_path":"docs/b.md"}\n'
        size = len(body.encode("utf-8"))
        sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
        manifest = self._consistent_manifest(size=size, sha=sha, records=2)
        # Same SUM (2) but redistributed across kinds the JSONL doesn't have.
        manifest["source_db"]["kind_counts"] = {"plan": 1, "code_draft": 1}
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup(tmp, record_body=body, manifest=manifest)
            r = mod.check_manifest_self_consistency(root)
        self.assertEqual(r.status, "fail")
        self.assertIn("per-kind", r.detail)

    def test_red_when_artifact_path_missing(self) -> None:
        """Missing artifact.path must FAIL, not silently default+pass."""
        mod = _VERIFY.PortabilityModule()
        import hashlib

        body = '{"original_path":"docs/a.md"}\n'
        size = len(body.encode("utf-8"))
        sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
        manifest = self._consistent_manifest(size=size, sha=sha, records=1)
        del manifest["artifact"]["path"]  # path missing entirely
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup(tmp, record_body=body, manifest=manifest)
            r = mod.check_manifest_self_consistency(root)
        self.assertEqual(r.status, "fail")
        self.assertIn("artifact.path missing", r.detail)

    def test_red_when_artifact_path_absolute(self) -> None:
        """Absolute artifact.path must FAIL (must be a relative basename)."""
        mod = _VERIFY.PortabilityModule()
        import hashlib

        body = '{"original_path":"docs/a.md"}\n'
        size = len(body.encode("utf-8"))
        sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
        manifest = self._consistent_manifest(size=size, sha=sha, records=1)
        # Absolute path escapes snap_dir via Path joining — must be rejected.
        manifest["artifact"]["path"] = str(Path("/tmp/archived_docs.jsonl"))
        with tempfile.TemporaryDirectory() as tmp:
            root = self._setup(tmp, record_body=body, manifest=manifest)
            r = mod.check_manifest_self_consistency(root)
        self.assertEqual(r.status, "fail")
        self.assertIn("relative basename", r.detail)

    def test_red_when_artifact_path_nested_relative(self) -> None:
        """Nested relative artifact.path (contains "/") must FAIL.

        Locks S3: the producer writes a bare basename (docs_path.name); a
        declared relative path WITH a "/" is a contract violation rejected at
        verify_suite.py (~:472 guard). Mirrors test_red_when_artifact_path_absolute
        but asserts the precise "absolute/nested" token (the absolute test's broad
        "relative basename" substring would also match nested, giving zero
        dedicated coverage). The artifact is written under the nested name so the
        failure is the basename guard, NOT the missing-file branch.
        """
        mod = _VERIFY.PortabilityModule()
        import hashlib

        body = '{"original_path":"docs/a.md"}\n'
        size = len(body.encode("utf-8"))
        sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
        manifest = self._consistent_manifest(size=size, sha=sha, records=1)
        # Relative path WITH a "/" — the absolute/nested guard branch.
        manifest["artifact"]["path"] = "nested/archived_docs.jsonl"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snap = root / "docs" / "_meta" / "archive_snapshots" / "current"
            snap.mkdir(parents=True, exist_ok=True)
            # Write the artifact under the NESTED declared name (not the default),
            # so the only failing issue is the basename guard, not "artifact missing".
            nested = snap / "nested" / "archived_docs.jsonl"
            nested.parent.mkdir(parents=True, exist_ok=True)
            nested.write_text(body, encoding="utf-8")
            (snap / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            r = mod.check_manifest_self_consistency(root)
        self.assertEqual(r.status, "fail")
        self.assertIn("absolute/nested", r.detail)

    def test_red_when_source_db_missing_contract_fields(self) -> None:
        """Each missing producer-contract key must FAIL independently.

        Locks S2: every cross-check is `if X is not None`-gated, so a MISSING
        docs_count/kind_counts/content_bytes silently short-circuits to no-drift.
        The producer (docs_archive.py:458-476) ALWAYS emits these, so their
        absence is a contract violation = drift. Split into per-key subtests so
        a regression that only asserts ONE key's presence (and skips the other
        two) is caught independently.
        """
        import hashlib

        body = '{"original_path":"docs/a.md"}\n'
        size = len(body.encode("utf-8"))
        sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
        for missing in ("docs_count", "kind_counts", "content_bytes"):
            with self.subTest(missing=missing):
                mod = _VERIFY.PortabilityModule()
                manifest = self._consistent_manifest(size=size, sha=sha, records=1)
                # Start from a full producer-shaped source_db, drop ONE key so
                # the failure isolates to that single field.
                del manifest["source_db"][missing]
                with tempfile.TemporaryDirectory() as tmp:
                    root = self._setup(tmp, record_body=body, manifest=manifest)
                    r = mod.check_manifest_self_consistency(root)
                self.assertEqual(r.status, "fail")
                self.assertIn(
                    f"source_db.{missing} missing (producer contract)", r.detail
                )


class ExtractSectionTests(unittest.TestCase):
    """_extract_section must scope marker search to the DoD body, not the plan.

    Locks the S2 finding: stale evidence/log prose carrying gate strings must
    not keep the DoD check green after acceptance criteria regress.
    """

    def test_extracts_body_between_headings(self) -> None:
        text = (
            "## Problem\nsome prose\n\n"
            "## Acceptance criteria / DoD\n"
            "- [x] 0 personal_path blockers with --scope all\n"
            "- [x] 0 outside META\n\n"
            "## Tests\nunit tests here\n"
        )
        body = _VERIFY._extract_section(text, "Acceptance criteria / DoD")
        self.assertIn("--scope all", body)
        self.assertIn("outside META", body)
        self.assertNotIn("unit tests here", body)
        self.assertNotIn("some prose", body)

    def test_missing_heading_returns_empty(self) -> None:
        self.assertEqual(_VERIFY._extract_section("# no match\n", "Acceptance criteria / DoD"), "")


class PortabilityApplicabilityTests(unittest.TestCase):
    """Explicit plan/archive inputs govern only the corresponding gates."""

    _GENERIC_CHECKS = (
        "check_oss_scan_keepset",
        "check_oss_scan_scope_all_personal_path",
        "check_homebrew_outside_meta",
        "check_corruption_artifacts",
        "check_oss_scan_public_copy_personal_path",
    )

    def _stub_generic_checks(self, mod) -> None:
        for name in self._GENERIC_CHECKS:
            setattr(mod, name, lambda _root, _name=name: _VERIFY.Result(_name, "pass", "ok"))

    def test_default_run_keeps_fast_integrity_checks_but_omits_unselected_inputs(self) -> None:
        mod = _VERIFY.PortabilityModule()
        self._stub_generic_checks(mod)
        test_scripts_calls: list[Path] = []
        module_overlap_calls: list[Path] = []

        def test_scripts(root: Path) -> _VERIFY.Result:
            test_scripts_calls.append(root)
            raise AssertionError("default test discovery ran")

        def module_overlap(root: Path) -> _VERIFY.Result:
            module_overlap_calls.append(root)
            raise AssertionError("default portability module overlap ran")

        mod.check_test_scripts = test_scripts
        mod.check_portability_test_modules = module_overlap
        plan_lint = mock.Mock(side_effect=AssertionError("unselected plan gate ran"))
        plan_status = mock.Mock(side_effect=AssertionError("unselected plan gate ran"))
        archive_checks = [
            mock.Mock(side_effect=AssertionError("unselected archive gate ran"))
            for _ in range(4)
        ]
        mod.check_plan_lint_portability_plans = plan_lint
        mod.check_plans_status = plan_status
        (
            mod.check_manifest_validity,
            mod.check_manifest_self_consistency,
            mod.check_archive_db_label_portability,
            mod.check_archive_content_portability,
        ) = archive_checks

        results = mod.run(Path("/nonexistent"))

        self.assertEqual([r.name for r in results], list(self._GENERIC_CHECKS))
        self.assertIn("no verification claim", mod.interpret(results))
        self.assertEqual(test_scripts_calls, [])
        self.assertEqual(module_overlap_calls, [])
        plan_lint.assert_not_called()
        plan_status.assert_not_called()
        for check in archive_checks:
            check.assert_not_called()

    def test_full_run_adds_discovery_once_and_omits_portability_module_overlap(self) -> None:
        mod = _VERIFY.PortabilityModule(full=True)
        self._stub_generic_checks(mod)
        test_scripts = mock.Mock(return_value=_VERIFY.Result("test-scripts", "pass", "ok"))
        module_overlap_calls: list[Path] = []

        def module_overlap(root: Path) -> _VERIFY.Result:
            module_overlap_calls.append(root)
            raise AssertionError("full portability module overlap ran")

        mod.check_test_scripts = test_scripts
        mod.check_portability_test_modules = module_overlap

        results = mod.run(Path("/nonexistent"))

        self.assertEqual(
            [result.name for result in results],
            ["test-scripts", *self._GENERIC_CHECKS],
        )
        test_scripts.assert_called_once_with(Path("/nonexistent"))
        self.assertEqual(module_overlap_calls, [])

    def test_selected_plan_and_archive_gates_are_added(self) -> None:
        mod = _VERIFY.PortabilityModule(
            portability_plans=("docs/plans/included.md",),
            archive_snapshot="docs/archive-fixture",
        )
        self._stub_generic_checks(mod)
        test_scripts_calls: list[Path] = []
        module_overlap_calls: list[Path] = []

        def test_scripts(root: Path) -> _VERIFY.Result:
            test_scripts_calls.append(root)
            raise AssertionError("selected fast route ran discovery")

        def module_overlap(root: Path) -> _VERIFY.Result:
            module_overlap_calls.append(root)
            raise AssertionError("selected fast route ran module overlap")

        mod.check_test_scripts = test_scripts
        mod.check_portability_test_modules = module_overlap
        selected = {
            "check_plan_lint_portability_plans": mock.Mock(return_value=_VERIFY.Result("plan lint", "pass")),
            "check_plans_status": mock.Mock(return_value=_VERIFY.Result("plan status", "pass")),
            "check_manifest_validity": mock.Mock(return_value=_VERIFY.Result("manifest", "pass")),
            "check_manifest_self_consistency": mock.Mock(return_value=_VERIFY.Result("consistency", "pass")),
            "check_archive_db_label_portability": mock.Mock(return_value=_VERIFY.Result("db labels", "pass")),
            "check_archive_content_portability": mock.Mock(return_value=_VERIFY.Result("content", "pass")),
        }
        for name, check in selected.items():
            setattr(mod, name, check)

        results = mod.run(Path("/nonexistent"))

        self.assertEqual(len(results), len(self._GENERIC_CHECKS) + len(selected))
        self.assertEqual(test_scripts_calls, [])
        self.assertEqual(module_overlap_calls, [])
        for check in selected.values():
            check.assert_called_once_with(Path("/nonexistent"))

    def test_requested_missing_plan_fails_instead_of_reporting_verified(self) -> None:
        mod = _VERIFY.PortabilityModule(portability_plans=("docs/plans/missing.md",))
        with mock.patch.object(_VERIFY.subprocess, "run", return_value=mock.Mock(returncode=1)):
            lint = mod.check_plan_lint_portability_plans(Path("/nonexistent"))
        self.assertEqual(lint.status, "fail")
        self.assertIn("docs/plans/missing.md", lint.detail)
        with tempfile.TemporaryDirectory() as tmp:
            status = mod.check_plans_status(Path(tmp))
        self.assertEqual(status.status, "fail")
        self.assertIn("unreadable", status.detail)

    def test_requested_missing_or_corrupt_archive_fails(self) -> None:
        mod = _VERIFY.PortabilityModule(archive_snapshot="docs/archive-fixture")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing = mod.check_manifest_validity(root)
            self.assertEqual(missing.status, "fail")
            self.assertEqual(mod.check_archive_db_label_portability(root).status, "fail")
            _write(root, "docs/archive-fixture/manifest.json", "{not json\n")
            corrupt = mod.check_manifest_self_consistency(root)
        self.assertEqual(corrupt.status, "fail")
        self.assertIn("parse error", corrupt.detail)

    def test_direct_archive_check_without_input_fails_closed(self) -> None:
        mod = _VERIFY.PortabilityModule()
        with tempfile.TemporaryDirectory() as tmp:
            result = mod.check_manifest_validity(Path(tmp))
        self.assertEqual(result.status, "fail")
        self.assertIn("not selected", result.detail)

    def test_explicit_archive_snapshot_preserves_portable_db_prefix_resolution(self) -> None:
        import hashlib

        body = '{"original_path":"docs/a.md"}\n'
        size = len(body.encode("utf-8"))
        manifest = {
            "artifact": {
                "path": "archive.jsonl",
                "size_bytes": size,
                "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
                "record_count": 1,
            },
            "storage_matrix": [{"backend": "git_text_export", "selected": True, "size_bytes": size}],
            "source_db": {
                "docs_count": 1,
                "kind_counts": {"": 1},
                "content_bytes": 0,
                "db_path": f"{_VERIFY._PORTABLE_FULL}/.tmp/absent.sqlite",
            },
        }
        mod = _VERIFY.PortabilityModule(archive_snapshot="docs/archive-fixture")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root, "docs/archive-fixture/archive.jsonl", body)
            _write(root, "docs/archive-fixture/manifest.json", json.dumps(manifest))
            result = mod.check_manifest_self_consistency(root)
        self.assertEqual(result.status, "pass")

    def test_content_profile_does_not_imply_applicability_inputs(self) -> None:
        with mock.patch.object(_VERIFY, "load_portability_rules", return_value=_VERIFY.GENERIC_PORTABILITY_RULES), \
                mock.patch.object(_VERIFY, "_load_modules", return_value=[]) as lm, \
                mock.patch("sys.stdout"):
            self.assertEqual(_VERIFY.main(["--content-profile-id", "default"]), 0)
            self.assertEqual(
                _VERIFY.main(
                    [
                        "--content-profile-id", "planveyor",
                        "--portability-plan", "docs/plans/included.md",
                        "--archive-snapshot", "docs/archive-fixture",
                    ]
                ),
                0,
            )
        first, second = lm.call_args_list
        self.assertEqual(first.kwargs["portability_plans"], ())
        self.assertIsNone(first.kwargs["archive_snapshot"])
        self.assertEqual(second.kwargs["portability_plans"], ("docs/plans/included.md",))
        self.assertEqual(second.kwargs["archive_snapshot"], "docs/archive-fixture")
        self.assertFalse(first.kwargs["full"])
        self.assertFalse(second.kwargs["full"])

    def test_public_profiles_load_real_rules_before_module_dispatch(self) -> None:
        for profile in ("default", "planveyor", "target-local"):
            with self.subTest(profile=profile), \
                    mock.patch.object(_VERIFY, "_load_modules", return_value=[]) as modules, \
                    mock.patch("sys.stdout"):
                self.assertEqual(_VERIFY.main(["--content-profile-id", profile]), 0)
                modules.assert_called_once_with(
                    [], portability_rules=_VERIFY.GENERIC_PORTABILITY_RULES,
                    portability_plans=(), archive_snapshot=None, full=False,
                )
        with mock.patch.object(_VERIFY, "_load_modules") as modules, \
                mock.patch("sys.stderr"), self.assertRaises(SystemExit) as error:
            _VERIFY.main(["--content-profile-id", "unknown-consumer"])
        self.assertEqual(error.exception.code, 2)
        modules.assert_not_called()

    def test_cli_rejects_repo_escape_for_applicability_inputs(self) -> None:
        for option, value in (("--portability-plan", "../private.md"), ("--archive-snapshot", "/tmp/archive")):
            with self.subTest(option=option):
                with self.assertRaises(SystemExit) as cm:
                    _VERIFY.main([option, value])
                self.assertEqual(cm.exception.code, 2)


class ModuleIsolationTests(unittest.TestCase):
    """A top-level exception in one check must not abort the whole module run."""

    def test_failing_check_recorded_as_fail_not_raised(self) -> None:
        mod = _VERIFY.PortabilityModule(full=True)

        def _boom(_repo_root):
            raise RuntimeError("simulated check crash")

        # Patch every OTHER check to a cheap pass Result. Use a default-arg
        # factory to avoid the classic closure late-binding bug (all lambbas
        # would otherwise see the loop's final `name` value).
        def _noop(_repo_root, _name="placeholder"):
            return _VERIFY.Result(_name, "pass", "ok")

        noop_names = [
            "check_oss_scan_keepset",
            "check_oss_scan_scope_all_personal_path",
            "check_homebrew_outside_meta",
            "check_corruption_artifacts",
            "check_oss_scan_public_copy_personal_path",
        ]
        patchers = []
        for name in noop_names:
            bound = (lambda _r, _n=name: _noop(_r, _n))
            p = mock.patch.object(mod, name, bound)
            p.start()
            patchers.append(p)
            self.addCleanup(p.stop)
        with mock.patch.object(mod, "check_test_scripts", _boom):
            out = mod.run(Path("/nonexistent"))
        # The boomy check is captured as a fail Result (name derived from the
        # function's __name__ with the check_ prefix stripped).
        fails = [r for r in out if r.status == "fail"]
        self.assertEqual(len(fails), 1)
        self.assertIn("simulated check crash", fails[0].detail)
        # All other checks still ran and passed.
        self.assertEqual(len(out), len(noop_names) + 1)


class CliFormatAndModuleFilterTests(unittest.TestCase):
    """--format wiring and --module filtering must reach the renderers."""

    def test_format_json_dispatches_to_json_renderer(self) -> None:
        with mock.patch.object(_VERIFY, "_load_modules") as lm, \
                mock.patch.object(_VERIFY, "_render_json", return_value="{}\n") as rj:
            mod = mock.Mock()
            mod.name = "portability"
            mod.run.return_value = [_VERIFY.Result("c", "pass", "ok")]
            mod.interpret.return_value = "clean"
            lm.return_value = [mod]
            with mock.patch("sys.stdout"):
                _VERIFY.main(["--format", "json"])
        rj.assert_called_once()

    def test_module_filter_passes_selected_name_to_load_modules(self) -> None:
        with mock.patch.object(_VERIFY, "_load_modules", return_value=[]) as lm:
            with mock.patch("sys.stdout"):
                _VERIFY.main(["--module", "portability", "--format", "json"])
        lm.assert_called_once()
        self.assertEqual(lm.call_args.args, (["portability"],))
        self.assertEqual(
            lm.call_args.kwargs["portability_rules"],
            _VERIFY.GENERIC_PORTABILITY_RULES,
        )
        self.assertEqual(lm.call_args.kwargs["portability_plans"], ())
        self.assertIsNone(lm.call_args.kwargs["archive_snapshot"])
        self.assertFalse(lm.call_args.kwargs["full"])

    def test_repeated_module_filter_remains_repeatable(self) -> None:
        with mock.patch.object(_VERIFY, "_load_modules", return_value=[]) as lm:
            with mock.patch("sys.stdout"):
                self.assertEqual(
                    _VERIFY.main(
                        ["--module", "portability", "--module", "portability", "--format", "json"]
                    ),
                    0,
                )
        self.assertEqual(lm.call_args.args, (["portability", "portability"],))
        self.assertFalse(lm.call_args.kwargs["full"])

    def test_full_mode_passes_true_to_load_modules(self) -> None:
        with mock.patch.object(_VERIFY, "_load_modules", return_value=[]) as lm:
            with mock.patch("sys.stdout"):
                self.assertEqual(_VERIFY.main(["--full", "--format", "json"]), 0)
        self.assertEqual(lm.call_args.args, ([],))
        self.assertTrue(lm.call_args.kwargs["full"])

    def test_full_and_module_are_rejected_before_module_dispatch(self) -> None:
        with mock.patch.object(_VERIFY, "_load_modules") as lm, \
                mock.patch("sys.stderr", new_callable=io.StringIO) as stderr, self.assertRaises(SystemExit) as error:
            _VERIFY.main(["--full", "--module", "portability"])
        self.assertEqual(error.exception.code, 2)
        self.assertIn("not allowed with argument", stderr.getvalue())
        lm.assert_not_called()


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Process-lifetime code/runtime coherence regressions for contract authority.

The copied runtime is first imported at v1, then changed through a clean Git
commit inside the same child interpreter.  A later authority capture must not
combine that already-loaded v1 code with an x1 runtime pin, or upgrade an
initially dirty runtime after it becomes clean.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from authority_bootstrap_test_support import run_bootstrapped_bridge, supported_bridge_module
from test_contract_authority_support import AuthorityFixture


class ContractAuthorityLoadedCodeTests(unittest.TestCase):
    def _run_candidate(
        self,
        fixture: AuthorityFixture,
        body: str,
        *,
        arguments: tuple[str, ...] = (),
    ) -> subprocess.CompletedProcess[str]:
        environment = fixture.environment()
        environment["PYTHONPATH"] = os.pathsep.join(
            (str(fixture.runtime_root / "scripts"), str(fixture.runtime_root))
        )
        return subprocess.run(
            [sys.executable, "-B", "-X", "pycache_prefix=/dev/null", "-c", body, *arguments],
            cwd=fixture.target_root,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def _runtime_pin_summary(self, fixture: AuthorityFixture) -> dict[str, object]:
        result = run_bootstrapped_bridge(
            fixture,
            "runtime-pin",
            "--runtime-root",
            str(fixture.runtime_root),
            "--entrypoint",
            str(fixture.runtime_root / "scripts" / "planveyor.zsh"),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_raw_context_rejects_before_target_capture_and_cannot_promote_loaded_dirty_runtime(self) -> None:
        """A raw bridge remains unattested before it can inspect target Git."""

        harness = textwrap.dedent(
            """\
            import contextlib
            import io
            import json
            import os
            from pathlib import Path
            import runpy
            import subprocess
            import sys

            target = Path(sys.argv[1]).resolve()
            runtime = Path(sys.argv[2]).resolve()
            summary = json.loads(sys.argv[3])
            mode = sys.argv[4]
            bridge = runtime / "scripts" / "contract_authority_bridge.py"
            target_calls = []
            original_run = subprocess.run

            def guarded_run(command, *args, **kwargs):
                values = tuple(os.fspath(value) for value in command) if isinstance(command, (tuple, list)) else ()
                if str(target) in values:
                    target_calls.append(values)
                    raise AssertionError("TARGET_CAPTURE_FORBIDDEN")
                return original_run(command, *args, **kwargs)

            def invoke(*arguments):
                stdout = io.StringIO()
                stderr = io.StringIO()
                previous_argv = sys.argv
                sys.argv = [str(bridge), *arguments]
                try:
                    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                        try:
                            runpy.run_path(bridge, run_name="__main__")
                        except SystemExit as exited:
                            code = 0 if exited.code is None else int(exited.code)
                finally:
                    sys.argv = previous_argv
                return code, stdout.getvalue(), stderr.getvalue()

            subprocess.run = guarded_run
            try:
                if mode == "wrong_summary":
                    summary["pin_sha256"] = "0" * 64
                elif mode == "dirty_then_clean":
                    loaded_code, _loaded_stdout, loaded_stderr = invoke("runtime-api-version")
                    assert loaded_code == 0, loaded_stderr
                    subprocess.run(
                        ["git", "-C", str(runtime), "checkout", "--", "scripts/plan_lint.py"],
                        check=True,
                    )
                else:
                    raise AssertionError(mode)
                code, _stdout, stderr = invoke(
                    "context",
                    "--project-root",
                    str(target),
                    "--runtime-pin-summary",
                    json.dumps(summary, sort_keys=True, separators=(",", ":")),
                )
            finally:
                subprocess.run = original_run
            print(json.dumps({
                "code": code,
                "stderr": stderr,
                "target_calls": target_calls,
            }, sort_keys=True))
            """
        )

        with self.subTest(case="wrong_summary"), AuthorityFixture() as fixture:
            summary = self._runtime_pin_summary(fixture)
            result = self._run_candidate(
                fixture,
                harness,
                arguments=(
                    str(fixture.target_root),
                    str(fixture.runtime_root),
                    json.dumps(summary, sort_keys=True, separators=(",", ":")),
                    "wrong_summary",
                ),
            )
            payload = json.loads(result.stdout)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(payload["code"], 2)
            self.assertIn("runtime_pin_unattested", payload["stderr"])
            self.assertEqual(payload["target_calls"], [])

        with self.subTest(case="dirty_then_clean"), AuthorityFixture() as fixture:
            summary = self._runtime_pin_summary(fixture)
            dirty_path = fixture.runtime_root / "scripts" / "plan_lint.py"
            dirty_path.write_bytes(dirty_path.read_bytes() + b"\n# disposable dirty first load\n")
            result = self._run_candidate(
                fixture,
                harness,
                arguments=(
                    str(fixture.target_root),
                    str(fixture.runtime_root),
                    json.dumps(summary, sort_keys=True, separators=(",", ":")),
                    "dirty_then_clean",
                ),
            )
            payload = json.loads(result.stdout)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(payload["code"], 2)
            self.assertIn("runtime_pin_unattested", payload["stderr"])
            self.assertEqual(payload["target_calls"], [])

    def test_raw_runtime_pin_is_unattested_and_supported_verify_rechecks_disk(self) -> None:
        """Raw bridge loads cannot mint pins; supported verification rechecks disk."""

        with AuthorityFixture() as fixture:
            raw_result = self._run_candidate(
                fixture,
                textwrap.dedent(
                    """\
                    import contextlib
                    import io
                    import json
                    from pathlib import Path
                    import runpy
                    import sys

                    runtime = Path(sys.argv[1]).resolve()
                    bridge = runtime / "scripts" / "contract_authority_bridge.py"

                    def invoke(*arguments):
                        stdout = io.StringIO()
                        stderr = io.StringIO()
                        previous_argv = sys.argv
                        sys.argv = [str(bridge), *arguments]
                        try:
                            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                                try:
                                    runpy.run_path(bridge, run_name="__main__")
                                except SystemExit as exited:
                                    code = 0 if exited.code is None else int(exited.code)
                        finally:
                            sys.argv = previous_argv
                        return code, stdout.getvalue(), stderr.getvalue()

                    code, _stdout, stderr = invoke(
                        "runtime-pin",
                        "--runtime-root",
                        str(runtime),
                        "--entrypoint",
                        str(runtime / "scripts" / "planveyor.zsh"),
                    )
                    print(json.dumps({"code": code, "stderr": stderr}, sort_keys=True))
                    """
                ),
                arguments=(str(fixture.runtime_root),),
            )
            self.assertEqual(raw_result.returncode, 0, raw_result.stdout + raw_result.stderr)
            raw_payload = json.loads(raw_result.stdout)
            self.assertEqual(raw_payload["code"], 2)
            self.assertIn("runtime_pin_unattested", raw_payload["stderr"])

            with supported_bridge_module(fixture) as bridge:
                pin_stdout = io.StringIO()
                pin_stderr = io.StringIO()
                with contextlib.redirect_stdout(pin_stdout), contextlib.redirect_stderr(pin_stderr):
                    pin_code = bridge.main([
                        "runtime-pin",
                        "--runtime-root",
                        str(fixture.runtime_root),
                        "--entrypoint",
                        str(fixture.runtime_root / "scripts" / "planveyor.zsh"),
                    ])
                self.assertEqual(pin_code, 0, pin_stdout.getvalue() + pin_stderr.getvalue())
                self.assertIn("contract_authority_runtime", sys.modules)
                loaded_runtime = sys.modules["contract_authority_runtime"]

                drift = fixture.runtime_root / "scripts" / "plan_lint.py"
                drift.write_bytes(drift.read_bytes() + b"\n# disposable post-load disk drift\n")
                verify_stdout = io.StringIO()
                verify_stderr = io.StringIO()
                with contextlib.redirect_stdout(verify_stdout), contextlib.redirect_stderr(verify_stderr):
                    verify_code = bridge.main([
                        "runtime-verify",
                        "--runtime-pin-summary",
                        pin_stdout.getvalue().strip(),
                    ])
                self.assertIs(sys.modules["contract_authority_runtime"], loaded_runtime)

        self.assertEqual(verify_code, 2, verify_stdout.getvalue() + verify_stderr.getvalue())
        self.assertEqual(verify_stdout.getvalue(), "")
        self.assertIn("runtime_closure_worktree_blob_mismatch", verify_stderr.getvalue())

    def test_host_preload_before_clean_source_commit_stays_unattested_after_revert(self) -> None:
        """A retained preloaded sibling cannot be blessed by later clean bytes."""

        harness = textwrap.dedent(
            """\
            import importlib
            import json
            from pathlib import Path
            import subprocess
            import sys

            runtime_root = Path(sys.argv[1]).resolve()
            target = Path(sys.argv[2]).resolve()
            preloaded_name = sys.argv[3]
            source_relative = f"scripts/{preloaded_name}.py"
            source = runtime_root / source_relative
            assert not (target / "docs" / "_meta" / "planveyor_contract_authority.v1.json").exists()

            preloaded = importlib.import_module(preloaded_name)
            original = source.read_bytes()
            assert not hasattr(preloaded, "_HOST_PRELOAD_TEST_CONSTANT")
            source.write_bytes(
                original
                + bytes((10,))
                + b'_HOST_PRELOAD_TEST_CONSTANT = "changed"'
                + bytes((10,))
            )
            subprocess.run(
                ["git", "-C", str(runtime_root), "add", "--", source_relative],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(runtime_root), "commit", "--quiet", "-m", "host preload source change"],
                check=True,
            )
            assert source.read_bytes() != original
            assert sys.modules[preloaded_name] is preloaded
            assert not hasattr(preloaded, "_HOST_PRELOAD_TEST_CONSTANT")

            runtime = importlib.import_module("contract_authority_runtime")
            authority = importlib.import_module("contract_authority_context")
            if preloaded_name == "contract_authority_snapshot":
                assert authority._snapshot is preloaded
            else:
                assert authority._fs_identity is preloaded
            first = runtime._first_loaded_runtime_observation()
            assert first.pin is None
            legacy_after_change = authority.resolve_top_level_context(target, loaded_pin=None)
            assert legacy_after_change.state == "legacy"
            assert legacy_after_change.runtime_pin is None
            fresh_after_change = runtime.capture_loaded_runtime_pin(runtime_root)
            try:
                authority.resolve_top_level_context(target, loaded_pin=fresh_after_change)
            except authority.ContractAuthorityError as error:
                explicit_after_change = error.reason_code
            else:
                raise SystemExit("host_preload_promoted_after_clean_commit")

            source.write_bytes(original)
            subprocess.run(
                ["git", "-C", str(runtime_root), "add", "--", source_relative],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(runtime_root), "commit", "--quiet", "-m", "host preload source revert"],
                check=True,
            )
            assert source.read_bytes() == original
            assert sys.modules[preloaded_name] is preloaded
            assert not hasattr(preloaded, "_HOST_PRELOAD_TEST_CONSTANT")
            assert runtime._first_loaded_runtime_observation().pin is None
            legacy_after_revert = authority.resolve_top_level_context(target, loaded_pin=None)
            assert legacy_after_revert.state == "legacy"
            assert legacy_after_revert.runtime_pin is None
            fresh_after_revert = runtime.capture_loaded_runtime_pin(runtime_root)
            try:
                authority.resolve_top_level_context(target, loaded_pin=fresh_after_revert)
            except authority.ContractAuthorityError as error:
                explicit_after_revert = error.reason_code
            else:
                raise SystemExit("host_preload_promoted_after_revert")
            print(json.dumps({
                "explicit_after_change": explicit_after_change,
                "explicit_after_revert": explicit_after_revert,
                "first_pin_is_none": first.pin is None,
                "preloaded_name": preloaded_name,
            }, sort_keys=True))
            """
        )

        for preloaded_name in ("contract_authority_snapshot", "fs_object_identity"):
            with self.subTest(preloaded_name=preloaded_name), AuthorityFixture() as fixture:
                result = self._run_candidate(
                    fixture,
                    harness,
                    arguments=(str(fixture.runtime_root), str(fixture.target_root), preloaded_name),
                )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["preloaded_name"], preloaded_name)
            self.assertTrue(payload["first_pin_is_none"])
            self.assertEqual(payload["explicit_after_change"], "runtime_loaded_code_drift")
            self.assertEqual(payload["explicit_after_revert"], "runtime_loaded_code_drift")

    def test_same_byte_raw_host_preload_remains_unattested(self) -> None:
        """Unchanged disk bytes cannot attest a host import without capsules."""

        harness = textwrap.dedent(
            """\
            import importlib
            import json
            from pathlib import Path
            import sys

            runtime_root = Path(sys.argv[1]).resolve()
            target = Path(sys.argv[2]).resolve()
            preloaded_name = sys.argv[3]
            assert not (target / "docs" / "_meta" / "planveyor_contract_authority.v1.json").exists()
            preloaded = importlib.import_module(preloaded_name)
            runtime = importlib.import_module("contract_authority_runtime")
            authority = importlib.import_module("contract_authority_context")
            if preloaded_name == "contract_authority_snapshot":
                assert authority._snapshot is preloaded
            else:
                assert authority._fs_identity is preloaded
            first = runtime._first_loaded_runtime_observation()
            assert first.pin is None
            legacy = authority.resolve_top_level_context(target, loaded_pin=None)
            assert legacy.state == "legacy"
            assert legacy.runtime_pin is None
            fresh = runtime.capture_loaded_runtime_pin(runtime_root)
            try:
                authority.resolve_top_level_context(target, loaded_pin=fresh)
            except authority.ContractAuthorityError as error:
                explicit_reason = error.reason_code
            else:
                raise SystemExit("raw_host_preload_promoted")
            print(json.dumps({
                "explicit_reason": explicit_reason,
                "first_pin_is_none": first.pin is None,
                "preloaded_name": preloaded_name,
            }, sort_keys=True))
            """
        )

        for preloaded_name in ("contract_authority_snapshot", "fs_object_identity"):
            with self.subTest(preloaded_name=preloaded_name), AuthorityFixture() as fixture:
                result = self._run_candidate(
                    fixture,
                    harness,
                    arguments=(str(fixture.runtime_root), str(fixture.target_root), preloaded_name),
                )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["preloaded_name"], preloaded_name)
            self.assertTrue(payload["first_pin_is_none"])
            self.assertEqual(payload["explicit_reason"], "runtime_loaded_code_drift")

    def test_raw_loaded_context_cannot_promote_after_a_clean_runtime_commit(self) -> None:
        with AuthorityFixture() as fixture:
            result = self._run_candidate(
                fixture,
                textwrap.dedent(
                    """\
                    import json
                    from pathlib import Path
                    import subprocess

                    import contract_authority_context as authority

                    target = Path.cwd()
                    first = authority.resolve_top_level_context(target, loaded_pin=None)
                    assert first.state == "legacy"
                    assert first.runtime_pin is None
                    runtime = Path(authority.__file__).resolve().parents[1]
                    source = runtime / "scripts" / "contract_authority_context.py"
                    original = source.read_text(encoding="utf-8")
                    before = "CONTEXT_SCHEMA_VERSION: Final[str] = _snapshot.CONTEXT_SCHEMA_VERSION"
                    replacement = 'CONTEXT_SCHEMA_VERSION: Final[str] = "planveyor_contract_context.x1"'
                    assert before in original
                    assert len(replacement) < len(before)
                    after = replacement + " " * (len(before) - len(replacement))
                    assert len(before) == len(after)
                    source.write_text(original.replace(before, after, 1), encoding="utf-8")
                    subprocess.run(["git", "-C", str(runtime), "add", "--", "scripts/contract_authority_context.py"], check=True)
                    subprocess.run(["git", "-C", str(runtime), "commit", "--quiet", "-m", "clean runtime source drift"], check=True)

                    fresh = authority._runtime.capture_loaded_runtime_pin(runtime)
                    second = authority.resolve_top_level_context(target, loaded_pin=None)
                    assert second.state == "legacy"
                    assert second.runtime_pin is None
                    try:
                        authority.resolve_top_level_context(target, loaded_pin=fresh)
                    except authority.ContractAuthorityError as error:
                        explicit_reason = error.reason_code
                    else:
                        raise SystemExit("raw_loaded_context_promoted_after_clean_runtime_commit")
                    print(json.dumps({
                        "explicit_reason": explicit_reason,
                        "fresh_pin_sha256": fresh.pin_sha256,
                        "first_state": first.state,
                        "second_state": second.state,
                    }, sort_keys=True))
                    """
                ),
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(len(payload["fresh_pin_sha256"]), 64)
        self.assertEqual(payload["first_state"], "legacy")
        self.assertEqual(payload["second_state"], "legacy")
        self.assertEqual(payload["explicit_reason"], "runtime_loaded_code_drift")

    def test_initially_dirty_loaded_runtime_cannot_promote_after_cleanup(self) -> None:
        with AuthorityFixture() as fixture:
            dirty_path = fixture.runtime_root / "scripts" / "plan_lint.py"
            dirty_path.write_bytes(dirty_path.read_bytes() + b"\n# disposable initial runtime drift\n")
            result = self._run_candidate(
                fixture,
                textwrap.dedent(
                    """\
                    import json
                    from pathlib import Path
                    import subprocess

                    import contract_authority_context as authority

                    target = Path.cwd()
                    first = authority.resolve_top_level_context(target, loaded_pin=None)
                    assert first.state == "legacy"
                    assert first.runtime_pin is None
                    runtime = Path(authority.__file__).resolve().parents[1]
                    subprocess.run(
                        ["git", "-C", str(runtime), "checkout", "--", "scripts/plan_lint.py"],
                        check=True,
                    )
                    fresh = authority._runtime.capture_loaded_runtime_pin(runtime)
                    second = authority.resolve_top_level_context(target, loaded_pin=None)
                    assert second.state == "legacy"
                    assert second.runtime_pin is None
                    try:
                        authority.resolve_top_level_context(target, loaded_pin=fresh)
                    except authority.ContractAuthorityError as error:
                        print(json.dumps({
                            "explicit_reason": error.reason_code,
                            "fresh_pin_sha256": fresh.pin_sha256,
                        }, sort_keys=True))
                    else:
                        raise SystemExit("initially_dirty_runtime_promoted_after_cleanup")
                    """
                ),
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(len(payload["fresh_pin_sha256"]), 64)
        self.assertEqual(payload["explicit_reason"], "runtime_loaded_code_drift")


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Fresh-process regressions for passive authority-envelope bridge commands.

The five compact-envelope commands are deliberately permitted to examine
historical receipts whose former project/runtime roots no longer exist.  They
must therefore parse only the snapshot-owned envelope contract: no Git
subprocess, runtime pin, or live context module is admissible on this path.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import py_compile
import stat
import subprocess
import sys
import textwrap
import unittest


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from test_contract_authority_support import AuthorityFixture, git, write


class ContractAuthorityPassiveBridgeTests(unittest.TestCase):
    """Exercise the passive bridge route in clean child interpreters."""

    @staticmethod
    def _canonical(value: object) -> str:
        return json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":"), sort_keys=True)

    @classmethod
    def _with_digest(cls, body: dict[str, object]) -> dict[str, object]:
        current = {key: value for key, value in body.items() if key != "context_sha256"}
        digest = hashlib.sha256(cls._canonical(current).encode("utf-8")).hexdigest()
        return {**current, "context_sha256": digest}

    @classmethod
    def _historical_envelope(cls, missing_root: Path) -> dict[str, object]:
        """Build a structurally valid engaged receipt with no live roots."""

        root = str(missing_root)
        body: dict[str, object] = {
            "schema_version": "planveyor_contract_context.v1",
            "state": "engaged",
            "project_root": root,
            "entry_observation": {
                "root": root,
                "git_dir": f"{root}/.git",
                "head": "a" * 40,
                "tree": "b" * 40,
                "index_sha256": "c" * 64,
            },
            "behavior_identity": "planveyor",
            "runtime_pin": {
                "runtime_root": "/historical/missing/runtime",
                "git_dir": "/historical/missing/runtime/.git",
                "runtime_api_version": 1,
                "commit": "d" * 40,
                "tree": "e" * 40,
                "closure_spec_sha256": "f" * 64,
                "closure_rows_sha256": "1" * 64,
                "closure_sha256": "2" * 64,
                "pin_sha256": "3" * 64,
            },
            "generation_sha256": "4" * 64,
            "fallback_used": False,
        }
        return cls._with_digest(body)

    def _install_timestamp_valid_stale_snapshot_cache(self, fixture: AuthorityFixture) -> Path:
        """Leave v1 source bytes behind a timestamp-valid x1 snapshot cache."""

        source = fixture.runtime_root / "scripts" / "contract_authority_snapshot.py"
        original = source.read_bytes()
        original_stat = source.stat()
        original_mode = stat.S_IMODE(original_stat.st_mode)
        original_git_row = git(
            fixture.runtime_root,
            "ls-files",
            "-s",
            "--",
            "scripts/contract_authority_snapshot.py",
        )
        before = b'CONTEXT_SCHEMA_VERSION: Final[str] = "planveyor_contract_context.v3"'
        after = b'CONTEXT_SCHEMA_VERSION: Final[str] = "planveyor_contract_context.x1"'
        self.assertIn(before, original)
        self.assertEqual(len(before), len(after))
        source.write_bytes(original.replace(before, after, 1))
        os.utime(source, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        cache = source.parent / "__pycache__" / f"{source.stem}.{sys.implementation.cache_tag}.pyc"
        cache.parent.mkdir(exist_ok=True)
        py_compile.compile(
            str(source),
            cfile=str(cache),
            doraise=True,
            invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP,
        )
        source.write_bytes(original)
        source.chmod(original_mode)
        os.utime(source, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(source.stat().st_size, original_stat.st_size)
        self.assertEqual(source.stat().st_mtime_ns, original_stat.st_mtime_ns)
        self.assertEqual(stat.S_IMODE(source.stat().st_mode), original_mode)
        self.assertEqual(
            git(
                fixture.runtime_root,
                "ls-files",
                "-s",
                "--",
                "scripts/contract_authority_snapshot.py",
            ),
            original_git_row,
        )
        self.assertTrue(cache.is_file())
        return cache

    def _run_passive_bridge(
        self,
        fixture: AuthorityFixture,
        *arguments: str,
    ) -> dict[str, object]:
        """Run one bridge command with Git calls forbidden inside that process."""

        bridge = fixture.runtime_root / "scripts" / "contract_authority_bridge.py"
        harness = textwrap.dedent(
            """\
            import contextlib
            import io
            import json
            import runpy
            import subprocess
            import sys

            bridge = sys.argv[1]
            command_args = sys.argv[2:]
            calls = []
            original_run = subprocess.run

            def forbid_git(*args, **kwargs):
                calls.append(args[0] if args else None)
                raise AssertionError("GIT_SUBPROCESS_FORBIDDEN")

            subprocess.run = forbid_git
            stdout = io.StringIO()
            stderr = io.StringIO()
            old_argv = sys.argv
            sys.argv = [bridge, *command_args]
            try:
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    try:
                        runpy.run_path(bridge, run_name="__main__")
                    except SystemExit as exited:
                        code = 0 if exited.code is None else int(exited.code)
            finally:
                sys.argv = old_argv
                subprocess.run = original_run

            forbidden_modules = (
                "contract_authority_runtime",
                "scripts.contract_authority_runtime",
                "contract_authority_context",
                "scripts.contract_authority_context",
            )
            print(json.dumps({
                "code": code,
                "forbidden_git_calls": len(calls),
                "loaded_forbidden_modules": [
                    name for name in forbidden_modules if name in sys.modules
                ],
                "stderr": stderr.getvalue(),
                "stdout": stdout.getvalue(),
            }, sort_keys=True))
            """
        )
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                "-X",
                "pycache_prefix=/dev/null",
                "-c",
                harness,
                str(bridge),
                *arguments,
            ],
            cwd=fixture.target_root,
            env=fixture.environment(),
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def _assert_passive_result(self, result: dict[str, object], *, code: int) -> None:
        self.assertEqual(result["code"], code, result)
        self.assertEqual(result["forbidden_git_calls"], 0, result)
        self.assertEqual(result["loaded_forbidden_modules"], [], result)

    def test_all_passive_commands_accept_a_historical_envelope_without_git_or_active_modules(self) -> None:
        with AuthorityFixture() as fixture:
            missing_root = fixture.root / "historical-root-that-does-not-exist"
            self.assertFalse(missing_root.exists())
            envelope = self._historical_envelope(missing_root)
            self.assertEqual(envelope["schema_version"], "planveyor_contract_context.v1")
            self.assertNotIn("entry_observation_provenance", envelope)
            compact = self._canonical(envelope)
            sid = "passive-historical"
            session_key = "passive-session-key"
            write(
                fixture.target_root,
                f".planveyor.init_runs/by_sid/{sid}/meta.json",
                self._canonical(
                    {
                        "outcome": "success",
                        "sid": sid,
                        "session_key": session_key,
                        "authority_context": envelope,
                    }
                )
                + "\n",
            )
            commands = {
                "context-field": (
                    "context-field",
                    "--context",
                    compact,
                    "--field",
                    "project_root",
                ),
                "context-canonical": ("context-canonical", "--context", compact),
                "context-bindings": ("context-bindings", "--context", compact),
                "context-match": (
                    "context-match",
                    "--context",
                    compact,
                    "--state",
                    "engaged",
                    "--project-root",
                    str(missing_root),
                    "--generation-sha256",
                    "4" * 64,
                ),
                "receipt-validate": (
                    "receipt-validate",
                    "--project-root",
                    str(fixture.target_root),
                    "--session-key",
                    session_key,
                    "--sid",
                    sid,
                    "--mode",
                    "engaged",
                    "--context",
                    compact,
                ),
            }

            results = {
                name: self._run_passive_bridge(fixture, *arguments)
                for name, arguments in commands.items()
            }

        for name, result in results.items():
            with self.subTest(command=name):
                self._assert_passive_result(result, code=0)
        self.assertEqual(results["context-field"]["stdout"], f"{missing_root}\n")
        self.assertEqual(results["context-canonical"]["stdout"], f"{compact}\n")
        self.assertEqual(
            results["context-bindings"]["stdout"],
            f"engaged\t{missing_root}\t{'4' * 64}\n",
        )
        self.assertEqual(json.loads(str(results["context-match"]["stdout"])), {"ok": True})
        self.assertEqual(
            json.loads(str(results["receipt-validate"]["stdout"])),
            {"mode": "engaged", "receipt": "matched", "ok": True},
        )

    def test_direct_passive_bridge_ignores_timestamp_valid_stale_snapshot_bytecode(self) -> None:
        """The bridge source policy precedes its snapshot-only passive import."""

        with AuthorityFixture() as fixture:
            cache = self._install_timestamp_valid_stale_snapshot_cache(fixture)
            missing_root = fixture.root / "missing-passive-root"
            compact = self._canonical(self._historical_envelope(missing_root))
            bridge = fixture.runtime_root / "scripts" / "contract_authority_bridge.py"
            command = [
                sys.executable,
                "-B",
                str(bridge),
                "context-field",
                "--context",
                compact,
                "--field",
                "schema_version",
            ]
            result = subprocess.run(
                command,
                cwd=fixture.target_root,
                env=fixture.environment(),
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
            cache_exists = cache.is_file()

        self.assertEqual(command[:3], [sys.executable, "-B", str(bridge)])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(cache_exists)
        self.assertEqual(result.stdout, "planveyor_contract_context.v1\n")
        self.assertNotIn("planveyor_contract_context.x1", result.stdout + result.stderr)

    def test_passive_parser_keeps_its_bounded_stable_failure_codes_without_active_imports(self) -> None:
        with AuthorityFixture() as fixture:
            envelope = self._historical_envelope(fixture.root / "missing-root")
            compact = self._canonical(envelope)

            tampered = json.loads(compact)
            tampered["generation_sha256"] = "5" * 64

            schema_invalid = json.loads(compact)
            schema_invalid["behavior_identity"] = "unknown behavior"
            schema_invalid = self._with_digest(schema_invalid)

            control_character = json.loads(compact)
            bad_root = "/historical/\x01control"
            control_character["project_root"] = bad_root
            control_character["entry_observation"]["root"] = bad_root
            control_character = self._with_digest(control_character)

            cases = {
                "invalid": ("{", "context_envelope_invalid"),
                "too_large": ("{" + "x" * (16 * 1024 + 1), "context_envelope_too_large"),
                "duplicate": (compact[:-1] + ',"state":"engaged"}', "context_envelope_duplicate_field"),
                "schema": (self._canonical(schema_invalid), "context_envelope_schema_invalid"),
                "digest": (self._canonical(tampered), "context_envelope_digest_mismatch"),
                # Preserve the direct-context parser contract: `_validate_text`
                # exposes this as invalid_text before the enclosing schema check.
                "control": (self._canonical(control_character), "invalid_text"),
            }
            for invalid_state in ([], {}):
                invalid = self._with_digest({**envelope, "state": invalid_state})
                cases[f"state_{type(invalid_state).__name__}"] = (
                    self._canonical(invalid), "context_envelope_schema_invalid"
                )
            for invalid_schema in ([], {}):
                invalid = self._with_digest({**envelope, "schema_version": invalid_schema})
                cases[f"schema_{type(invalid_schema).__name__}"] = (
                    self._canonical(invalid), "context_envelope_schema_invalid"
                )
            results = {
                name: self._run_passive_bridge(
                    fixture,
                    "context-field",
                    "--context",
                    payload,
                    "--field",
                    "state",
                )
                for name, (payload, _code) in cases.items()
            }

        for name, result in results.items():
            with self.subTest(parser_case=name):
                self._assert_passive_result(result, code=2)
                expected_code = cases[name][1]
                self.assertIn(f"contract_authority_bridge: {expected_code}:", str(result["stderr"]))


if __name__ == "__main__":
    unittest.main()

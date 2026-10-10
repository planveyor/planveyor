#!/usr/bin/env python3
"""Focused same-buffer loader regressions for contract authority."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import textwrap
import unittest


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import contract_authority_context as context_authority  # noqa: E402
from test_contract_authority_support import AuthorityFixture, commit_all, write  # noqa: E402


class ContractAuthorityBufferLoaderTests(unittest.TestCase):
    def _bootstrap_run(
        self,
        fixture: AuthorityFixture,
        *arguments: str,
        input_data: bytes | None = None,
        bootstrap_literal: str | None = None,
    ) -> subprocess.CompletedProcess[bytes]:
        literal = bootstrap_literal
        if literal is None:
            literal = (fixture.runtime_root / "scripts" / "contract_authority_bootstrap.py").read_text(
                encoding="utf-8"
            )
        return subprocess.run(
            [
                sys.executable,
                "-I",
                "-B",
                "-c",
                literal,
                str(fixture.runtime_root / "scripts" / "contract_authority_bridge.py"),
                *arguments,
            ],
            cwd=fixture.target_root,
            env=fixture.environment(),
            input=input_data,
            check=False,
            capture_output=True,
            timeout=60,
        )

    def _runtime_pin(self, fixture: AuthorityFixture) -> dict[str, object]:
        result = self._bootstrap_run(
            fixture,
            "runtime-pin",
            "--runtime-root",
            str(fixture.runtime_root),
            "--entrypoint",
            str(fixture.runtime_root / "scripts" / "planveyor.zsh"),
        )
        self.assertEqual(result.returncode, 0, result.stdout.decode() + result.stderr.decode())
        return json.loads(result.stdout)

    @staticmethod
    def _compact(value: object) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"))

    def test_raw_bridge_cannot_mint_runtime_pin_but_supported_bootstrap_can(self) -> None:
        with AuthorityFixture() as fixture:
            raw = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(fixture.runtime_root / "scripts" / "contract_authority_bridge.py"),
                    "runtime-pin",
                    "--runtime-root",
                    str(fixture.runtime_root),
                    "--entrypoint",
                    str(fixture.runtime_root / "scripts" / "planveyor.zsh"),
                ],
                cwd=fixture.target_root,
                env=fixture.environment(),
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
            pinned = self._runtime_pin(fixture)

        self.assertEqual(raw.returncode, 2)
        self.assertEqual(raw.stdout, "")
        self.assertIn("runtime_pin_unattested", raw.stderr)
        self.assertEqual(pinned["runtime_root"], str(fixture.runtime_root))
        self.assertEqual(len(str(pinned["pin_sha256"])), 64)

    def test_parent_runtime_pin_summary_admits_unchanged_buffered_children(self) -> None:
        """A compact parent carrier preserves the normal supported child paths."""

        with AuthorityFixture() as fixture:
            entry = write(
                fixture.runtime_root,
                "scripts/parent_pin_entry.py",
                (
                    "import json, sys\n"
                    "print(json.dumps({'argv': sys.argv, "
                    "'has_capsule': '__authority_source_capsule__' in globals()}, sort_keys=True))\n"
                ),
            )
            commit_all(fixture.runtime_root, "add parent-pin child entry")
            pin = self._runtime_pin(fixture)
            summary = self._compact(pin)
            facade = fixture.runtime_root / "scripts" / "planveyor.zsh"
            entry_result = self._bootstrap_run(
                fixture,
                "python-entry",
                "--runtime-pin-summary",
                summary,
                "--path",
                str(entry),
                "--",
                "entry-arg",
            )
            stdin_result = self._bootstrap_run(
                fixture,
                "python-stdin",
                "--runtime-pin-summary",
                summary,
                "--",
                "stdin-arg",
                input_data=(
                    b"import json, sys\n"
                    b"print(json.dumps({'argv': sys.argv, 'has_capsule': '__authority_source_capsule__' in globals()}, sort_keys=True))\n"
                ),
            )
            source_result = self._bootstrap_run(
                fixture,
                "shell-source",
                "--runtime-pin-summary",
                summary,
                "--path",
                str(facade),
                "--runtime-root",
                str(fixture.runtime_root),
            )
            expected_facade = facade.read_bytes()

        self.assertEqual(entry_result.returncode, 0, entry_result.stderr.decode())
        self.assertEqual(
            json.loads(entry_result.stdout),
            {"argv": [str(entry), "entry-arg"], "has_capsule": True},
        )
        self.assertEqual(stdin_result.returncode, 0, stdin_result.stderr.decode())
        self.assertEqual(
            json.loads(stdin_result.stdout),
            {"argv": ["-", "stdin-arg"], "has_capsule": False},
        )
        self.assertEqual(source_result.returncode, 0, source_result.stderr.decode())
        header_bytes, body = source_result.stdout.split(b"\n", 1)
        self.assertEqual(json.loads(header_bytes)["runtime_pin"], pin)
        self.assertEqual(body, expected_facade)

    def test_parent_runtime_pin_summary_rejects_clean_v2_before_child_execution(self) -> None:
        """V1 parent commands cannot let a clean V2 child recapture authority."""

        with AuthorityFixture() as fixture:
            entry_sentinel = fixture.root / "entry-executed"
            stdin_sentinel = fixture.root / "stdin-executed"
            entry = write(
                fixture.runtime_root,
                "scripts/parent_pin_race_entry.py",
                f"from pathlib import Path\nPath({str(entry_sentinel)!r}).write_text('entry executed', encoding='utf-8')\n",
            )
            commit_all(fixture.runtime_root, "add parent-pin race entry")
            pin = self._runtime_pin(fixture)
            summary = self._compact(pin)
            bootstrap_v1 = (fixture.runtime_root / "scripts" / "contract_authority_bootstrap.py").read_text(
                encoding="utf-8"
            )
            loader_v1 = fixture.shell_loader()
            runtime_source = fixture.runtime_root / "scripts" / "contract_authority_runtime.py"
            runtime_source.write_bytes(
                runtime_source.read_bytes() + b"\n# parent v1 / child clean v2 regression\n"
            )
            commit_all(fixture.runtime_root, "advance clean child runtime to v2")

            entry_result = self._bootstrap_run(
                fixture,
                "python-entry",
                "--runtime-pin-summary",
                summary,
                "--path",
                str(entry),
                bootstrap_literal=bootstrap_v1,
            )
            stdin_result = self._bootstrap_run(
                fixture,
                "python-stdin",
                "--runtime-pin-summary",
                summary,
                input_data=(
                    f"from pathlib import Path\nPath({str(stdin_sentinel)!r}).write_text('stdin executed', encoding='utf-8')\n".encode(
                        "utf-8"
                    )
                ),
                bootstrap_literal=bootstrap_v1,
            )
            facade = fixture.runtime_root / "scripts" / "planveyor.zsh"
            shell_result = subprocess.run(
                [
                    "/bin/zsh",
                    "-fc",
                    loader_v1
                    + "\n"
                    + f"planveyor_source_runtime {shlex.quote(str(facade))} {shlex.quote(summary)} || exit $?\n"
                    + "print -r -- shell-child-executed\n",
                ],
                cwd=fixture.target_root,
                env=fixture.environment(),
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )

        for result in (entry_result, stdin_result):
            self.assertEqual(result.returncode, 2, result.stdout.decode() + result.stderr.decode())
            self.assertEqual(result.stdout, b"")
            self.assertIn(b"runtime_pin_mismatch", result.stderr)
        self.assertFalse(entry_sentinel.exists())
        self.assertFalse(stdin_sentinel.exists())
        self.assertEqual(shell_result.returncode, 2, shell_result.stdout + shell_result.stderr)
        self.assertEqual(shell_result.stdout, "")
        self.assertIn("runtime_pin_mismatch", shell_result.stderr)

    def test_shell_source_and_source_buffer_emit_exact_retained_bytes(self) -> None:
        with AuthorityFixture() as fixture:
            facade = fixture.runtime_root / "scripts" / "planveyor.zsh"
            source = self._bootstrap_run(
                fixture,
                "shell-source",
                "--path",
                str(facade),
                "--runtime-root",
                str(fixture.runtime_root),
            )
            self.assertEqual(source.returncode, 0, source.stderr.decode())
            header_bytes, body = source.stdout.split(b"\n", 1)
            header = json.loads(header_bytes)
            pin = header["runtime_pin"]
            module = self._bootstrap_run(
                fixture,
                "source-buffer",
                "--runtime-pin-summary",
                self._compact(pin),
                "--relative-path",
                "scripts/planveyor/role_runtime.zsh",
            )

            expected_facade = facade.read_bytes()
            expected_module = (fixture.runtime_root / "scripts" / "planveyor" / "role_runtime.zsh").read_bytes()

        self.assertEqual(header["version"], 1)
        self.assertEqual(header["source_path"], str(facade))
        self.assertEqual(header["runtime_root"], str(fixture.runtime_root))
        self.assertEqual(header["source"]["sha256"], header["source_descriptor"]["sha256"])
        self.assertEqual(header["source"]["size"], len(body))
        self.assertEqual(body, expected_facade)
        self.assertEqual(module.returncode, 0, module.stderr.decode())
        self.assertEqual(module.stdout, expected_module)

    def test_generic_home_and_legacy_modules_remain_source_buffered(self) -> None:
        with AuthorityFixture() as fixture:
            pin = self._runtime_pin(fixture)
            results = {
                relative: self._bootstrap_run(
                    fixture,
                    "source-buffer",
                    "--runtime-pin-summary",
                    self._compact(pin),
                    "--relative-path",
                    relative,
                )
                for relative in (
                    "scripts/planveyor/home_runtime.zsh",
                )
            }

        self.assertEqual(results["scripts/planveyor/home_runtime.zsh"].returncode, 0)
        self.assertIn(
            b"Consumer-owned Codex-home adapter",
            results["scripts/planveyor/home_runtime.zsh"].stdout,
        )

    def test_shell_transport_rejects_nul_retained_body(self) -> None:
        cases = (
            ("shell-source", "scripts/planveyor.zsh"),
            ("source-buffer", "scripts/planveyor/role_runtime.zsh"),
        )
        for command, relative_path in cases:
            with self.subTest(command=command), AuthorityFixture() as fixture:
                source_path = fixture.runtime_root / relative_path
                source_path.write_bytes(source_path.read_bytes() + b"\0")
                commit_all(fixture.runtime_root, "add shell transport NUL fixture")
                pin = self._runtime_pin(fixture)
                if command == "shell-source":
                    result = self._bootstrap_run(
                        fixture,
                        command,
                        "--path",
                        str(source_path),
                        "--runtime-root",
                        str(fixture.runtime_root),
                    )
                else:
                    result = self._bootstrap_run(
                        fixture,
                        command,
                        "--runtime-pin-summary",
                        self._compact(pin),
                        "--relative-path",
                        relative_path,
                    )
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, b"")
                self.assertIn(b"source_body_nul", result.stderr)

    def test_supported_engaged_context_and_python_callers_are_admitted(self) -> None:
        with AuthorityFixture() as fixture:
            context_path = fixture.runtime_root / "scripts" / "contract_authority_context.py"
            original_context = context_path.read_text(encoding="utf-8")
            context_path.write_text(
                original_context.replace(
                    "ENGAGED_ADMISSION_COMPLETE: Final[bool] = False",
                    "ENGAGED_ADMISSION_COMPLETE: Final[bool] = True",
                    1,
                ),
                encoding="utf-8",
            )
            commit_all(fixture.runtime_root, "enable disposable engaged admission")
            fixture.activate_planveyor(context_authority.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS)
            entry = write(
                fixture.runtime_root,
                "scripts/buffer_loader_entry.py",
                "import json, sys\nprint(json.dumps({'name': __name__, 'file': __file__, 'argv': sys.argv, 'has_capsule': '__authority_source_capsule__' in globals()}, sort_keys=True))\n",
            )
            commit_all(fixture.runtime_root, "add buffer loader entry fixture")
            pin = self._runtime_pin(fixture)
            context = self._bootstrap_run(
                fixture,
                "context",
                "--project-root",
                str(fixture.target_root),
                "--runtime-pin-summary",
                self._compact(pin),
            )
            entry_result = self._bootstrap_run(
                fixture,
                "python-entry",
                "--path",
                str(entry),
                "--",
                "one",
                "two",
            )
            stdin_result = self._bootstrap_run(
                fixture,
                "python-stdin",
                "--",
                "stdin-arg",
                input_data=b"import json, sys\nprint(json.dumps({'name': __name__, 'file': __file__, 'argv': sys.argv, 'has_capsule': '__authority_source_capsule__' in globals()}, sort_keys=True))\n",
            )

        self.assertEqual(context.returncode, 0, context.stdout.decode() + context.stderr.decode())
        context_payload = json.loads(context.stdout)
        self.assertEqual(context_payload["state"], "engaged")
        self.assertEqual(context_payload["schema_version"], "planveyor_contract_context.v3")
        self.assertEqual(entry_result.returncode, 0, entry_result.stdout.decode() + entry_result.stderr.decode())
        self.assertEqual(
            json.loads(entry_result.stdout),
            {
                "argv": [str(entry), "one", "two"],
                "file": str(entry),
                "has_capsule": True,
                "name": "__main__",
            },
        )
        self.assertEqual(stdin_result.returncode, 0, stdin_result.stdout.decode() + stdin_result.stderr.decode())
        self.assertEqual(
            json.loads(stdin_result.stdout),
            {"argv": ["-", "stdin-arg"], "file": "<stdin>", "has_capsule": False, "name": "__main__"},
        )

    def test_before_first_pin_drift_for_every_retained_core_source_stays_unattested(self) -> None:
        """The reader returns v1 bytes, then a clean v2 commit occurs before exec."""

        harness = textwrap.dedent(
            """\
            import contextlib
            import io
            import json
            from pathlib import Path
            import subprocess
            import sys
            import types

            runtime = Path(sys.argv[1]).resolve()
            trigger = sys.argv[2]
            bridge_path = runtime / "scripts" / "contract_authority_bridge.py"
            literal = (runtime / "scripts" / "contract_authority_bootstrap.py").read_text(encoding="utf-8")
            bootstrap = {"__name__": "trusted_test_bootstrap", "__file__": "<trusted-bootstrap>"}
            exec(compile(literal, "<trusted-bootstrap>", "exec"), bootstrap, bootstrap)
            bridge_capsule = bootstrap["_read_regular_source"](str(bridge_path))
            reader_base = bootstrap["_reader_with_cache"](bridge_capsule)
            mutated = False

            def mutate():
                global mutated
                if mutated:
                    return
                source = runtime / "scripts" / (trigger + ".py")
                source.write_bytes(source.read_bytes() + b"\\n# retained-v1 / disk-v2 test drift\\n")
                subprocess.run(["git", "-C", str(runtime), "add", "--", str(source.relative_to(runtime))], check=True)
                subprocess.run(["git", "-C", str(runtime), "commit", "--quiet", "-m", "retained source drift"], check=True)
                mutated = True

            if trigger == "contract_authority_bridge":
                mutate()

            def reader(path):
                capsule = reader_base(path)
                if trigger != "contract_authority_bridge" and Path(path).name == trigger + ".py":
                    mutate()
                return capsule

            module = types.ModuleType("supported_buffer_bridge")
            module.__file__ = bridge_capsule[0]
            module.__dict__.update({
                "__name__": "supported_buffer_bridge",
                "__file__": bridge_capsule[0],
                "__authority_source_capsule__": bridge_capsule,
                "__authority_read_source__": reader,
            })
            sys.modules[module.__name__] = module
            exec(compile(bridge_capsule[3], bridge_capsule[0], "exec"), module.__dict__, module.__dict__)
            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = module.main([
                    "runtime-pin", "--runtime-root", str(runtime), "--entrypoint", str(runtime / "scripts" / "planveyor.zsh"),
                ])
            print(json.dumps({"code": code, "stderr": stderr.getvalue(), "mutated": mutated}, sort_keys=True))
            """
        )
        triggers = (
            "none",
            "contract_authority_bridge",
            "fs_object_identity",
            "contract_authority_snapshot",
            "contract_authority_runtime",
            "contract_authority_context",
        )
        for trigger in triggers:
            with self.subTest(trigger=trigger), AuthorityFixture() as fixture:
                result = subprocess.run(
                    [sys.executable, "-I", "-B", "-c", harness, str(fixture.runtime_root), trigger],
                    cwd=fixture.target_root,
                    env=fixture.environment(),
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                payload = json.loads(result.stdout)
                if trigger == "none":
                    self.assertEqual(payload["code"], 0, payload)
                    self.assertFalse(payload["mutated"])
                else:
                    self.assertEqual(payload["code"], 2, payload)
                    self.assertTrue(payload["mutated"])
                    self.assertIn("runtime_pin_unattested", payload["stderr"])


if __name__ == "__main__":
    unittest.main()

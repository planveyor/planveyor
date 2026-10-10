#!/usr/bin/env python3
"""Portable production-loader regressions for the consumed stream header."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest


class ContractAuthorityLoaderStreamTests(unittest.TestCase):
    def test_missing_supported_python_explains_how_to_select_it(self) -> None:
        source_root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory(prefix="planveyor-loader-python-") as temporary:
            root = Path(temporary).resolve()
            fake_bin = root / "bin"
            fake_bin.mkdir()
            # Only an interpreter that rejects the supported-version probe is visible.
            fake_python = fake_bin / "python3"
            fake_python.write_text("#!/bin/sh\nexit 1\n")
            fake_python.chmod(0o700)
            template = (source_root / "scripts/contract_authority_shell_loader.zsh").read_text()
            loader = root / "caller-loader.zsh"
            loader.write_text(template.replace("@PLANVEYOR_AUTHORITY_BOOTSTRAP_LITERAL@", "raise SystemExit(99)"))
            facade = source_root / "scripts/planveyor.zsh"
            command = (
                f"source {shlex.quote(str(loader))} || exit 90\n"
                f"planveyor_source_runtime {shlex.quote(str(facade))}\n"
            )
            result = subprocess.run(
                ["/bin/zsh", "-f", "-c", command], cwd=root,
                env={"HOME": str(root), "TMPDIR": str(root), "PATH": str(fake_bin)},
                text=True, capture_output=True, timeout=30,
            )
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertIn("no Python 3.10-3.12 found on PATH", result.stderr)
            self.assertIn("activate the Planveyor environment with Python 3.12", result.stderr)
            self.assertIn("requirements-dev.lock", result.stderr)
            self.assertEqual(len(result.stderr.splitlines()), 1, result.stderr)

    def test_header_is_not_executed_and_body_status_stays_in_current_shell(self) -> None:
        source_root = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory(prefix="planveyor-loader-stream-") as temporary:
            root = Path(temporary).resolve()
            runtime = root / "runtime"
            def git(*args: str) -> str:
                result = subprocess.run(
                    ["git", "-C", str(runtime), *args], check=True,
                    text=True, capture_output=True,
                )
                return result.stdout.strip()
            subprocess.run(
                ["git", "clone", "--quiet", "--no-hardlinks", str(source_root), str(runtime)],
                check=True, capture_output=True, text=True,
            )
            # Include the candidate loader before its corrective commit as well.
            shutil.copy2(source_root / "scripts/contract_authority_shell_loader.zsh",
                         runtime / "scripts/contract_authority_shell_loader.zsh")
            git("add", "scripts/contract_authority_shell_loader.zsh")
            git("-c", "user.name=Loader regression", "-c", 'user.email=' + 'loader' + '@' + 'example' + '.' + 'invalid',
                "commit", "--quiet", "--allow-empty", "-m", "fixture candidate loader")
            template = (runtime / "scripts/contract_authority_shell_loader.zsh").read_text()
            bootstrap = (runtime / "scripts/contract_authority_bootstrap.py").read_text()
            marker = "@PLANVEYOR_AUTHORITY_BOOTSTRAP_LITERAL@"
            self.assertEqual(template.count(marker), 1)
            loader = root / "caller-loader.zsh"
            loader.write_text(template.replace(marker, bootstrap))
            home = root / "home"
            home.mkdir()
            environment = {
                "HOME": str(home), "TMPDIR": str(root), "TMPPREFIX": str(root / "zsh"),
                "LANG": "C.UTF-8",
                "PATH": str(Path(sys.executable).resolve().parent) + os.pathsep + os.defpath,
                "PYTHONDONTWRITEBYTECODE": "1",
            }
            facade = runtime / "scripts/planveyor.zsh"
            for expected_rc in (0, 37, 47):
                with self.subTest(body_return=expected_rc):
                    if expected_rc == 37:
                        with facade.open("a") as handle:
                            handle.write("\ntypeset -g PLANVEYOR_LOADER_BODY_SENTINEL=body-ran\nreturn 37\n")
                        git("add", "scripts/planveyor.zsh")
                        git("-c", "user.name=Loader regression", "-c", 'user.email=' + 'loader' + '@' + 'example' + '.' + 'invalid',
                            "commit", "--quiet", "-m", "fixture body failure")
                    if expected_rc == 47:
                        fake_bin = root / "fake-bin"
                        fake_bin.mkdir()
                        counter = root / "cat-count"
                        fake_cat = fake_bin / "cat"
                        fake_cat.write_text(
                            "#!/bin/sh\n"
                            'if [ ! -e "$PLANVEYOR_TEST_CAT_COUNT" ]; then\n'
                            '  : > "$PLANVEYOR_TEST_CAT_COUNT"\n'
                            '  exec /bin/cat "$@"\n'
                            "fi\n"
                            "printf 'typeset -g PLANVEYOR_LOADER_BODY_SENTINEL=partial-ran\\n'\n"
                            "exit 47\n"
                        )
                        fake_cat.chmod(0o700)
                        environment["PLANVEYOR_TEST_CAT_COUNT"] = str(counter)
                        environment["PATH"] = str(fake_bin) + os.pathsep + environment["PATH"]
                    command = f'''source {shlex.quote(str(loader))} || exit $?
rc=0
planveyor_source_runtime {shlex.quote(str(facade))} || rc=$?
print -r -- "BODY_RC=$rc"
print -r -- "BODY_EFFECT=${{PLANVEYOR_LOADER_BODY_SENTINEL:-}}"
print -r -- "PIN=$_PLANVEYOR_AUTHORITY_RUNTIME_PIN_SUMMARY"
print -r -- "C03_LOADER_TMP=$TMPDIR|$TMPPREFIX"
exit "$rc"
'''
                    result = subprocess.run(
                        ["/bin/zsh", "-f", "-c", command], cwd=root, env=environment,
                        text=True, capture_output=True, timeout=90,
                    )
                    self.assertEqual(result.returncode, expected_rc, result.stdout + result.stderr)
                    self.assertEqual(result.stderr, "", result.stderr)
                    self.assertIn(f"BODY_RC={expected_rc}", result.stdout.splitlines())
                    self.assertIn("BODY_EFFECT=" + ("body-ran" if expected_rc == 37 else ""), result.stdout.splitlines())
                    self.assertIn(
                        f"C03_LOADER_TMP={root}|{root / 'zsh'}",
                        result.stdout.splitlines(),
                    )
                    self.assertEqual(list(root.glob("planveyor-authority-source.*")), [])
                    if expected_rc == 47:
                        self.assertIn("PIN=", result.stdout.splitlines())
                        continue
                    pin = json.loads(next(line[4:] for line in result.stdout.splitlines() if line.startswith("PIN=")))
                    self.assertEqual(pin["commit"], git("rev-parse", "HEAD"))
                    self.assertEqual(pin["tree"], git("rev-parse", "HEAD^{tree}"))
                    self.assertEqual(pin["runtime_root"], str(runtime))
                    self.assertEqual(pin["runtime_api_version"], 5)
                    self.assertTrue(pin["pin_sha256"])


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
from __future__ import annotations

"""Regression coverage for scripts/_pybin.sh interpreter resolution."""

import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parent.parent
PYBIN_SH = REPO_ROOT / "scripts" / "_pybin.sh"
PLANVEYOR_ZSH = REPO_ROOT / "scripts" / "planveyor.zsh"
MAKEFILE = REPO_ROOT / "Makefile"


class PybinResolveTests(unittest.TestCase):
    def _write_executable(self, path: Path) -> None:
        path.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        path.chmod(0o755)

    def _run_resolve(
        self,
        root: Path,
        *,
        env_updates: dict[str, str | None] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.pop("PYBIN", None)
        env.pop("CONDA_PREFIX", None)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        if env_updates:
            for key, value in env_updates.items():
                if value is None:
                    env.pop(key, None)
                else:
                    env[key] = value

        command = (
            f"source {shlex.quote(str(PYBIN_SH))}; "
            f"planveyor_pybin_resolve {shlex.quote(str(root))}; "
            'printf "PYBIN=%s\\n" "${PYBIN}"'
        )
        return subprocess.run(
            ["/bin/bash", "-c", command],
            cwd=root,
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )

    def _run_set(
        self,
        root: Path,
        pybin: Path,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        selected_python = Path(sys.executable).absolute()
        home = root / "home"
        home.mkdir()
        child_tmp = (root / ".child-tmp").resolve()
        child_tmp.mkdir()
        child_observation = child_tmp / "pybin-set-child-environment"
        env.update(
            {
                "HOME": str(home),
                "TMPDIR": str(child_tmp),
                "TMPPREFIX": str(child_tmp / "zsh"),
                "PATH": f"{selected_python.parent}{os.pathsep}{env.get('PATH', '')}",
                "PLANVEYOR_ROOT": str(REPO_ROOT),
                "PYBIN": str(selected_python),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )

        generation = "0" * 64
        command = (
            f'print -r -- "$TMPDIR|$TMPPREFIX" > {shlex.quote(str(child_observation))}; '
            f"source {shlex.quote(str(PLANVEYOR_ZSH))} || exit $?; "
            "_planveyor_authority_context_for_reader() { print -r -- '{}'; }; "
            "_planveyor_authority_context_bindings() { "
            f"printf '%s\t%s\t%s\t\n' legacy {shlex.quote(str(root))} {generation}; "
            "}; "
            f"_planveyor_project_root() {{ print -r -- {shlex.quote(str(root))}; }}; "
            "_planveyor_now() { print -r -- '2026-09-16 00:00:00'; }; "
            f"planveyor_pybin_set {shlex.quote(str(pybin))}"
        )
        return subprocess.run(
            ["/bin/zsh", "-f", "-c", command],
            cwd=root,
            text=True,
            capture_output=True,
            env=env,
            check=False,
            timeout=30,
        )

    def test_project_cache_is_ignored_in_favor_of_path_python3(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_pybin_stale_") as tmpdir:
            root = Path(tmpdir)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            fake_python = fake_bin / "python3"
            self._write_executable(fake_python)
            (root / ".planveyor.pybin").write_text("/no/such/python\n", encoding="utf-8")

            result = self._run_resolve(
                root,
                env_updates={"PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}"},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"PYBIN={fake_python}", result.stdout)
            self.assertEqual(result.stderr, "")

    def test_missing_cache_falls_back_to_path_python3(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_pybin_missing_") as tmpdir:
            root = Path(tmpdir)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            fake_python = fake_bin / "python3"
            self._write_executable(fake_python)

            result = self._run_resolve(
                root,
                env_updates={"PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}"},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), f"PYBIN={fake_python}")

    def test_explicit_invalid_pybin_stays_strict(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_pybin_explicit_") as tmpdir:
            root = Path(tmpdir)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            fake_python = fake_bin / "python3"
            self._write_executable(fake_python)

            result = self._run_resolve(
                root,
                env_updates={
                    "PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}",
                    "PYBIN": "/no/such/python",
                },
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("PYBIN not executable: /no/such/python", result.stderr)
            self.assertEqual(result.stdout, "")

    def test_conda_prefix_precedes_path_python3(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_pybin_conda_") as tmpdir:
            root = Path(tmpdir)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            fake_python = fake_bin / "python3"
            self._write_executable(fake_python)
            conda_python = root / "conda" / "bin" / "python"
            conda_python.parent.mkdir(parents=True)
            self._write_executable(conda_python)

            result = self._run_resolve(
                root,
                env_updates={
                    "CONDA_PREFIX": str(conda_python.parent.parent),
                    "PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}",
                },
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), f"PYBIN={conda_python}")

    def test_valid_project_cache_cannot_override_conda(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_pybin_cache_") as tmpdir:
            root = Path(tmpdir)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            fake_python = fake_bin / "python3"
            self._write_executable(fake_python)
            conda_python = root / "conda" / "bin" / "python"
            conda_python.parent.mkdir(parents=True)
            self._write_executable(conda_python)
            cached_python = root / "cached" / "python"
            cached_python.parent.mkdir()
            self._write_executable(cached_python)
            (root / ".planveyor.pybin").write_text(f"{cached_python}\n", encoding="utf-8")

            result = self._run_resolve(
                root,
                env_updates={
                    "CONDA_PREFIX": str(conda_python.parent.parent),
                    "PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}",
                },
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), f"PYBIN={conda_python}")

    def test_retired_pybin_set_never_writes_project_selector(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_pybin_set_") as tmpdir:
            root = Path(tmpdir)
            selected_python = Path(sys.executable).absolute()
            result = self._run_set(root, selected_python)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("project files cannot select executables", result.stderr)
            self.assertFalse((root / ".planveyor.pybin").exists())
            self.assertFalse((root / ".planveyor.pybin.log").exists())

    def test_retired_setter_does_not_execute_project_supplied_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_pybin_set_reject_") as tmpdir:
            root = Path(tmpdir)
            canary = root / "executed"
            hostile = root / "hostile-python"
            hostile.write_text(f"#!/bin/sh\nprintf ran > {shlex.quote(str(canary))}\nexit 0\n", encoding="utf-8")
            hostile.chmod(0o755)
            selector = root / ".planveyor.pybin"
            log = root / ".planveyor.pybin.log"
            selector_before = f"{hostile}\n".encode()
            log_before = b"existing-log\n"
            selector.write_bytes(selector_before)
            log.write_bytes(log_before)
            result = self._run_set(root, hostile)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertFalse(canary.exists())
            self.assertEqual(selector.read_bytes(), selector_before)
            self.assertEqual(log.read_bytes(), log_before)

    def test_doc_lint_validates_even_an_explicit_pybin(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor-doc-lint-pybin-") as directory:
            root = Path(directory)
            executable = root / "python-fixture"
            marker = root / "doc-lint-executed"
            executable.write_text(
                '#!/bin/bash\n'
                'if [[ "${1:-}" == "-c" ]]; then exit "${FIXTURE_VERSION_STATUS}"; fi\n'
                'printf ran > "${DOC_LINT_EXEC_MARKER}"\n', encoding="utf-8")
            executable.chmod(0o755)
            for version_status, expected_status in (("1", 2), ("0", 0)):
                with self.subTest(version_status=version_status):
                    marker.unlink(missing_ok=True)
                    env = dict(os.environ, PYBIN=str(executable),
                               FIXTURE_VERSION_STATUS=version_status, DOC_LINT_EXEC_MARKER=str(marker))
                    result = subprocess.run(["/bin/bash", str(REPO_ROOT / "scripts/run_doc_lint.sh"), "--help"],
                                            env=env, text=True, capture_output=True, check=False)
                    self.assertEqual(result.returncode, expected_status, result.stderr)
                    self.assertEqual(marker.exists(), version_status == "0")
                    if version_status == "1":
                        self.assertIn("<3.13 required by pyproject.toml", result.stderr)

    def test_makefile_pybin_recipes_preserve_inherited_path(self) -> None:
        makefile = MAKEFILE.read_text(encoding="utf-8")

        self.assertNotIn("bash -lc 'source ./scripts/_pybin.sh", makefile)


if __name__ == "__main__":
    sys.exit(unittest.main())

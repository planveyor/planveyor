#!/usr/bin/env python3
from __future__ import annotations

"""Regression coverage for runtime path portability.

Plan: docs/plans/260605_0057_process_runtime_path_portability_hardening.md
"""

import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

from oss_release_scan import PERSONAL_PATH_RE
from test_support.process_contract_fixtures import run_zsh_fixture


REPO_ROOT = Path(__file__).resolve().parent.parent
PLANVEYOR_SCRIPT = REPO_ROOT / "scripts" / "planveyor.zsh"
PLANVEYOR_MODULE_DIR = REPO_ROOT / "scripts" / "planveyor"
DOCS_FINALIZE_MODULE = PLANVEYOR_MODULE_DIR / "docs_finalize.zsh"
ROLE_RUNTIME_MODULE = PLANVEYOR_MODULE_DIR / "role_runtime.zsh"
RUNTIME_MODULE_INVENTORY = (
    ("contract_authority.zsh", "eager bootstrap dependency"),
    ("session_init.zsh", "eager"),
    ("role_runtime.zsh", "eager"),
    ("docs_finalize.zsh", "eager"),
    ("home_runtime.zsh", "lazy"),
    ("provider_runtime.zsh", "conditional"),
)
_RUNTIME_CLOSURE_FILES = (
    "contract_authority_bootstrap.py",
    "contract_authority_shell_loader.zsh",
    "contract_authority_children.py",
    "contract_authority_bridge.py",
    "contract_authority_context.py",
    "contract_authority_runtime.py",
    "contract_authority_snapshot.py",
    "fs_object_identity.py",
)


def _zsh_function_source(path: Path, function_name: str) -> str:
    match = re.search(
        rf"(?ms)^{re.escape(function_name)}\(\) \{{\n(?P<body>.*?)(?=^[A-Za-z_][A-Za-z0-9_]*\(\) \{{|\Z)",
        path.read_text(encoding="utf-8"),
    )
    if match is None:
        raise AssertionError(f"missing zsh function {function_name} in {path}")
    return match.group("body")


def _runtime_surface_paths() -> list[Path]:
    """Return the loaded facade, its source-time closure, and this regression test.

    This is intentionally narrower than a documentation corpus scan. Runtime
    portability needs a generic concrete-user-home check on the executable
    surface without historical META-reference exceptions.
    """
    paths = [PLANVEYOR_SCRIPT, Path(__file__)]
    paths.extend(sorted((REPO_ROOT / "scripts" / "planveyor").glob("*.zsh")))
    paths.extend(REPO_ROOT / "scripts" / name for name in _RUNTIME_CLOSURE_FILES)
    return [path for path in paths if path.is_file()]


def _banner_source_paths() -> list[Path]:
    """Builder scripts that emit regenerate-via banners / lint messages.

    These must not bake `/opt/homebrew/bin/python3` so regeneration stays
    portable across machines without Homebrew. Scoped narrowly: golden test
    fixtures that intentionally carry historical evidence paths are excluded.
    """
    paths = [
        REPO_ROOT / "scripts" / "followups_index_rebuild.py",
        REPO_ROOT / "scripts" / "process_improvements_collect.py",
        REPO_ROOT / "scripts" / "doc_lint.py",
    ]
    return [path for path in paths if path.is_file()]


def _homebrew_python_pattern() -> re.Pattern[str]:
    return re.compile("/opt/homebrew/bin/python3")


class RuntimePortabilityTests(unittest.TestCase):
    def _run_zsh(
        self,
        command: str,
        *,
        cwd: Path = REPO_ROOT,
        extra_env: dict[str, str | None] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        fixture_env = {
            key: value
            for key, value in (extra_env or {}).items()
            if value is not None
        }
        return run_zsh_fixture(
            command,
            cwd=cwd,
            path=os.environ.get("PATH", os.defpath),
            pybin=str(Path(sys.executable).resolve()),
            fixture_env=fixture_env or None,
            check=False,
        )

    def _copy_minimal_tooling_tree(self, target_root: Path) -> None:
        target_scripts = target_root / "scripts"
        target_modules = target_scripts / "planveyor"
        target_modules.mkdir(parents=True)
        shutil.copy2(PLANVEYOR_SCRIPT, target_scripts / "planveyor.zsh")
        for module in sorted(PLANVEYOR_MODULE_DIR.glob("*.zsh")):
            shutil.copy2(module, target_modules / module.name)
        # The facade's first lines now authenticate their own Python bridge
        # and its fixed source-time closure.  A relocation fixture must carry
        # that closure itself; falling back to the real checkout would make
        # this portability assertion accidentally pass or fail by host state.
        for name in _RUNTIME_CLOSURE_FILES:
            shutil.copy2(REPO_ROOT / "scripts" / name, target_scripts / name)

    def _run_temp_home_shell(
        self,
        home: Path,
        command: str,
        *,
        cwd: Path,
        flags: str = "-fc",
        extra_env: dict[str, str | None] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        for key in (
            "PLANVEYOR_ROOT",
            "PLANVEYOR_RUNTIME_ROOT",
            "PLANVEYOR_BARE_BIN_DIR",
            "PLANVEYOR_CODEX_HOME",
            "PLANVEYOR_LEGACY_PROFILE",
            "PLANVEYOR_WRAPPERS_LOADED_PID",
            "PLANVEYOR_WRAPPERS_LOADED_FROM",
            "PLANVEYOR_WRAPPERS_REPO_ROOT",
            "_PLANVEYOR_THIS_SCRIPT_PATH",
            "CODEX_HOME",
            "ZDOTDIR",
        ):
            env.pop(key, None)
        env["HOME"] = str(home)
        if extra_env:
            for key, value in extra_env.items():
                if value is None:
                    env.pop(key, None)
                else:
                    env[key] = value
        child_tmp = (home.parent / ".child-tmp").resolve()
        child_tmp.mkdir(exist_ok=True)
        env["TMPDIR"] = str(child_tmp)
        env["TMPPREFIX"] = str(child_tmp / "zsh")
        return subprocess.run(
            ["/bin/zsh", flags, command],
            cwd=cwd,
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )

    def test_runtime_module_inventory_is_exact_and_documented(self) -> None:
        expected_names = tuple(sorted(name for name, _ in RUNTIME_MODULE_INVENTORY))
        actual_names = tuple(sorted(path.name for path in PLANVEYOR_MODULE_DIR.glob("*.zsh")))
        self.assertEqual(actual_names, expected_names)

        readme = (PLANVEYOR_MODULE_DIR / "README.md").read_text(encoding="utf-8")
        start = readme.index("## Runtime inventory")
        end = readme.index("\n## Порядок eager-загрузки", start)
        inventory = readme[start:end]
        self.assertIn("Фасад (не модуль): `scripts/planveyor.zsh`.", inventory)
        rows = tuple(
            (name, mode.strip())
            for name, mode in re.findall(r"^\| `([^`]+)` \| ([^|]+) \|", inventory, flags=re.MULTILINE)
        )
        self.assertEqual(rows, RUNTIME_MODULE_INVENTORY)

    def test_unset_tooling_root_resolves_from_loaded_script_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_copy_") as tmpdir:
            fixture_root = Path(tmpdir)
            copied_root = fixture_root / "relocated_tooling"
            home = fixture_root / "home"
            home.mkdir()
            self._copy_minimal_tooling_tree(copied_root)
            child_observation = (
                fixture_root / ".child-tmp" / "runtime-portability-child-environment"
            )

            result = self._run_temp_home_shell(
                home,
                f'print -r -- "$TMPDIR|$TMPPREFIX" > {shlex.quote(str(child_observation))}; '
                "unset PLANVEYOR_ROOT; "
                f"source {shlex.quote(str(copied_root / 'scripts' / 'planveyor.zsh'))}; "
                "_planveyor_root",
                cwd=copied_root,
                flags="-fc",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), str(copied_root.resolve()))
            self.assertEqual(
                child_observation.read_text(encoding="utf-8"),
                f"{(fixture_root / '.child-tmp').resolve()}|{(fixture_root / '.child-tmp' / 'zsh').resolve()}\n",
            )

    def test_loaded_script_path_wins_over_ambient_root_and_cwd(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_copy_") as tmpdir:
            fixture_root = Path(tmpdir)
            copied_root = fixture_root / "relocated_tooling"
            home = fixture_root / "home"
            home.mkdir()
            self._copy_minimal_tooling_tree(copied_root)

            result = self._run_temp_home_shell(
                home,
                f"PLANVEYOR_ROOT={shlex.quote(str(REPO_ROOT))}; "
                f"source {shlex.quote(str(copied_root / 'scripts' / 'planveyor.zsh'))}; "
                "_planveyor_root; _planveyor_script plan_lint.py; "
                f"cd {shlex.quote(str(home))}; "
                "_planveyor_root; _planveyor_script plan_lint.py",
                cwd=copied_root,
                flags="-fc",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                result.stdout.splitlines(),
                [
                    str(copied_root.resolve()),
                    str(copied_root.resolve() / "scripts" / "plan_lint.py"),
                    str(copied_root.resolve()),
                    str(copied_root.resolve() / "scripts" / "plan_lint.py"),
                ],
            )

    def test_main_root_override_is_safe_under_nounset(self) -> None:
        override = "/tmp/planveyor-main-root-override"
        result = self._run_zsh(
            "setopt nounset; "
            f"source {shlex.quote(str(PLANVEYOR_SCRIPT))}; "
            f"PLANVEYOR_MAIN_ROOT={shlex.quote(override)} _planveyor_main_root",
            extra_env={"PLANVEYOR_MAIN_ROOT": None},
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip().splitlines()[-1], override)

    def test_arch_track_accepts_absolute_prompt_path(self) -> None:
        prompt = REPO_ROOT / "docs" / "tools" / "prompts" / "architect_track_process_roles.md"
        with tempfile.TemporaryDirectory(prefix="planveyor_arch_track_bound_prompt_") as tmpdir:
            trace_root = Path(tmpdir)
            consumer = trace_root / "portable-consumer"
            consumer.mkdir()
            subprocess.run(["git", "init"], cwd=consumer, check=True, capture_output=True, text=True)
            subprocess.run(["git", "config", "user.email", "test" + "@" + "example" + "." + "invalid"], cwd=consumer, check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=consumer, check=True)
            (consumer / "seed").write_text("fixture\n", encoding="utf-8")
            subprocess.run(["git", "add", "seed"], cwd=consumer, check=True)
            subprocess.run(["git", "commit", "-m", "fixture"], cwd=consumer, check=True, capture_output=True, text=True)
            provider_path = trace_root / "provider-path"
            provider_mode = trace_root / "provider-mode"
            provider_body = trace_root / "provider-body"
            # This fake provider records the prompt but cannot create a Codex SID.
            result = self._run_zsh(
                f"source {shlex.quote(str(PLANVEYOR_SCRIPT))}; "
                "_planveyor_codex() { "
                "local arg='' prompt_file='' next=0; "
                "for arg in \"$@\"; do "
                "if (( next )); then prompt_file=\"$arg\"; break; fi; "
                "[[ \"$arg\" == '--prompt-file' ]] && next=1; "
                "done; "
                "[[ -n \"$prompt_file\" ]] || return 1; "
                f"print -r -- \"$prompt_file\" > {shlex.quote(str(provider_path))}; "
                "\"$PYBIN\" -c 'import os, stat, sys; print(f\"{stat.S_IMODE(os.stat(sys.argv[1]).st_mode):04o}\")' \"$prompt_file\" "
                f"> {shlex.quote(str(provider_mode))}; "
                f"cat -- \"$prompt_file\" > {shlex.quote(str(provider_body))}; "
                "}; "
                "_planveyor_latest_codex_sid_for_cwd_prefix() { return 1; }; "
                f"_planveyor_arch_track_tui portability_audit {shlex.quote(str(prompt))}",
                cwd=consumer,
                extra_env={
                    "PLANVEYOR_LEGACY_PROFILE": None,
                    "PLANVEYOR_ROOT": str(REPO_ROOT),
                    "PLANVEYOR_RUNTIME_ROOT": None,
                },
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(
                "NOTE: Could not detect a new SID for portability_audit; set it manually: "
                "planveyor_session_set portability_audit <SESSION_ID>",
                result.stderr,
            )
            forwarded_path = Path(provider_path.read_text(encoding="utf-8").strip())
            self.assertTrue(forwarded_path.is_absolute())
            self.assertNotEqual(forwarded_path, prompt)
            self.assertEqual(provider_mode.read_text(encoding="utf-8").strip(), "0600")
            self.assertFalse(forwarded_path.exists())
            runtime_header = "COMMIT_POLICY=native_existing\n" + f"PLANVEYOR_RUNTIME_ROOT={REPO_ROOT}\n"
            self.assertEqual(
                provider_body.read_text(encoding="utf-8"),
                runtime_header + prompt.read_text(encoding="utf-8").rstrip("\n") + "\n",
            )
            self.assertNotIn(f"{REPO_ROOT}/{prompt}", result.stderr)



    def test_generic_consumer_root_uses_default_profile(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_profile_consumer_") as tmpdir:
            consumer = Path(tmpdir) / "portable-consumer"
            consumer.mkdir()
            subprocess.run(["git", "init"], cwd=consumer, check=True, capture_output=True, text=True)
            subprocess.run(["git", "config", "user.email", "test" + "@" + "example" + "." + "invalid"], cwd=consumer, check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=consumer, check=True)
            (consumer / "seed").write_text("fixture\n", encoding="utf-8")
            subprocess.run(["git", "add", "seed"], cwd=consumer, check=True)
            subprocess.run(["git", "commit", "-m", "fixture"], cwd=consumer, check=True, capture_output=True, text=True)
            result = self._run_zsh(
                f"source {shlex.quote(str(PLANVEYOR_SCRIPT))}; "
                "_planveyor_repo_profile_id",
                cwd=consumer,
                extra_env={"PLANVEYOR_LEGACY_PROFILE": None, "PLANVEYOR_ROOT": None, "PLANVEYOR_RUNTIME_ROOT": None},
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["default"])

    def test_generic_worktree_uses_common_directory_identity(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_profile_worktree_") as tmpdir:
            tmp = Path(tmpdir)
            source_repo = tmp / "portable-consumer"
            worktree = tmp / "feature-checkout"
            source_repo.mkdir()
            subprocess.run(
                ["git", "init"],
                cwd=source_repo,
                text=True,
                capture_output=True,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.email", "test" + "@" + "example" + "." + "invalid"],
                cwd=source_repo,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test User"],
                cwd=source_repo,
                check=True,
            )
            (source_repo / "seed").write_text("fixture\n", encoding="utf-8")
            subprocess.run(["git", "add", "seed"], cwd=source_repo, check=True)
            subprocess.run(
                ["git", "commit", "-m", "fixture"],
                cwd=source_repo,
                text=True,
                capture_output=True,
                check=True,
            )
            subprocess.run(
                ["git", "worktree", "add", "-b", "feature", str(worktree)],
                cwd=source_repo,
                text=True,
                capture_output=True,
                check=True,
            )

            result = self._run_zsh(
                f"source {shlex.quote(str(PLANVEYOR_SCRIPT))}; "
                "_planveyor_repo_profile_id",
                cwd=worktree,
                extra_env={"PLANVEYOR_LEGACY_PROFILE": None, "PLANVEYOR_ROOT": None, "PLANVEYOR_RUNTIME_ROOT": None},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.splitlines(), ["default"])

    def test_role_modules_use_profile_driven_env_helper(self) -> None:
        docs_finalize_roles = {
            "planveyor_arch_followups": "architect",
            "planveyor_coder_docs_general": "coder",
            "planveyor_coder_followups": "coder",
            "planveyor_planner_docs_general": "planner",
            "planveyor_planner_followups": "planner",
            "planveyor_reviewer_docs_general": "reviewer",
            "planveyor_reviewer_followups": "reviewer",
        }
        arch_general = _zsh_function_source(
            DOCS_FINALIZE_MODULE,
            "planveyor_arch_docs_general",
        )
        arch_expected = '_planveyor_with_role_env architect "$pybin" _planveyor_codex'
        arch_branches = re.search(
            r'(?ms)^  if \[\[ -n "\$receipt_path" \]\]; then\n'
            r"(?P<receipt>.*?)^  else\n"
            r"(?P<default>.*?)^  fi\n",
            arch_general,
        )
        self.assertIsNotNone(arch_branches, "planveyor_arch_docs_general")
        assert arch_branches is not None
        self.assertEqual(arch_general.count(arch_expected), 2, "planveyor_arch_docs_general")
        self.assertEqual(arch_branches.group("receipt").count(arch_expected), 1, "receipt-path")
        self.assertEqual(arch_branches.group("default").count(arch_expected), 1, "default")
        self.assertNotIn("TZ=", DOCS_FINALIZE_MODULE.read_text(encoding="utf-8"))

        for function_name, role in docs_finalize_roles.items():
            body = _zsh_function_source(DOCS_FINALIZE_MODULE, function_name)
            expected = f'_planveyor_with_role_env {role} "$pybin" _planveyor_codex'
            self.assertEqual(body.count(expected), 1, function_name)

        for function_name in (
            "planveyor_manager_custom_pipeline",
            "planveyor_manager_custom_pipeline_tui",
            "planveyor_manager_custom_pipeline_cmd",
        ):
            body = _zsh_function_source(ROLE_RUNTIME_MODULE, function_name)
            self.assertIn("_planveyor_manager_custom_pipeline_supervise", body, function_name)

        expected = '_planveyor_with_role_env manager "$pybin" _planveyor_codex'
        supervisor_body = _zsh_function_source(
            ROLE_RUNTIME_MODULE,
            "_planveyor_manager_custom_pipeline_supervise",
        )
        self.assertEqual(supervisor_body.count(expected), 2)

        nonrun_body = _zsh_function_source(
            ROLE_RUNTIME_MODULE,
            "_planveyor_manager_custom_pipeline_nonrun_cmd",
        )
        self.assertEqual(nonrun_body.count(expected), 1)

    def test_explicit_runtime_config_wrapper_matches_direct_source_and_rejects_cwd_discovery(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_wrapper_parity_") as tmpdir:
            tmp = Path(tmpdir)
            home = tmp / "home"
            home.mkdir()
            unrelated = tmp / "unrelated"
            unrelated.mkdir()
            wrapper = tmp / "bin" / "planveyor_bare_entrypoints_doctor"
            wrapper.parent.mkdir()
            runtime_env = {"PLANVEYOR_ROOT": str(REPO_ROOT)}

            rendered = self._run_temp_home_shell(
                home,
                f"source {shlex.quote(str(PLANVEYOR_SCRIPT))}; "
                "_planveyor_bare_entrypoints_render_shim planveyor_bare_entrypoints_doctor "
                f"{shlex.quote(str(REPO_ROOT))} > {shlex.quote(str(wrapper))}",
                cwd=unrelated,
                flags="-fc",
                extra_env=runtime_env,
            )
            self.assertEqual(rendered.returncode, 0, rendered.stderr)
            wrapper.chmod(0o755)

            direct = self._run_temp_home_shell(
                home,
                f"source {shlex.quote(str(PLANVEYOR_SCRIPT))}; planveyor_bare_entrypoints_doctor --help",
                cwd=unrelated,
                flags="-fc",
                extra_env=runtime_env,
            )
            wrapped = self._run_temp_home_shell(
                home,
                f"export PATH={shlex.quote(str(wrapper.parent))}:$PATH; planveyor_bare_entrypoints_doctor --help",
                cwd=unrelated,
                flags="-fc",
                extra_env=runtime_env,
            )

            self.assertEqual(direct.returncode, 0, direct.stderr)
            self.assertEqual(wrapped.returncode, 0, wrapped.stderr)
            self.assertEqual(wrapped.stdout, direct.stdout)
            self.assertEqual(wrapped.stderr, direct.stderr)

            missing_config = self._run_temp_home_shell(
                home,
                f"export PATH={shlex.quote(str(wrapper.parent))}:$PATH; planveyor_bare_entrypoints_doctor --help",
                cwd=unrelated,
                flags="-fc",
            )
            self.assertEqual(missing_config.returncode, 1)
            self.assertIn(
                f"Missing tooling wrapper for planveyor_bare_entrypoints_doctor: "
                f"{home}/planveyor/scripts/planveyor.zsh",
                missing_config.stderr,
            )
            self.assertNotIn(str(unrelated / "scripts" / "planveyor.zsh"), missing_config.stderr)

    def test_runtime_surfaces_do_not_bake_generic_user_home_paths(self) -> None:
        findings: list[str] = []
        for path in _runtime_surface_paths():
            rel_path = path.relative_to(REPO_ROOT)
            for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if PERSONAL_PATH_RE.search(line):
                    findings.append(f"{rel_path}:{line_no}: {line}")

        self.assertEqual(findings, [])

    def test_banner_sources_do_not_bake_homebrew_python(self) -> None:
        pattern = _homebrew_python_pattern()
        findings: list[str] = []
        for path in _banner_source_paths():
            rel_path = path.relative_to(REPO_ROOT)
            for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if pattern.search(line):
                    findings.append(f"{rel_path}:{line_no}: {line}")

        self.assertEqual(
            findings,
            [],
            "banner-bearing builder scripts must invoke `python3` (assume on PATH via "
            "scripts/_pybin.sh) instead of `/opt/homebrew/bin/python3`, so regeneration "
            "stays portable across machines without Homebrew",
        )


if __name__ == "__main__":
    unittest.main()

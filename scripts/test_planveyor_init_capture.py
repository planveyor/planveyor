#!/usr/bin/env python3
from __future__ import annotations

import json
import hashlib
import fcntl
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
import uuid
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parent.parent
PLANVEYOR_SCRIPT = REPO_ROOT / "scripts" / "planveyor.zsh"
OWNER_RUNBOOK = REPO_ROOT / "docs" / "tools" / "owner_runbook_codex.md"

SUCCESS_SIDS = {
    "architect": "00000000-0000-4000-8000-000000000101",
    "manager": "00000000-0000-4000-8000-000000000102",
    "coder": "00000000-0000-4000-8000-000000000103",
    "planner": "00000000-0000-4000-8000-000000000104",
    "reviewer": "00000000-0000-4000-8000-000000000105",
}

REVIEWER_LANE_SIDS = {
    "reviewer_code_risk": "00000000-0000-4000-8000-000000000106",
    "reviewer_code_contracts": "00000000-0000-4000-8000-000000000107",
}

# Public Codex uses the consumer default configuration.  Profile identifiers
# are intentionally not persisted or selected by Planveyor.
EXPECTED_PROFILES = {
    "architect": "",
    "manager": "",
    "coder": "",
    "planner": "",
    "reviewer": "",
}

RUNNER_MATRIX = {
    "architect": ("codex",),
    "coder": ("codex",),
    "manager": ("codex",),
    "planner": ("codex", "claude"),
    "reviewer": ("codex", "claude"),
}


class InitCaptureTests(unittest.TestCase):
    def _git(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            text=True,
            capture_output=True,
        )

    def _install_fake_codex(self, root: Path) -> tuple[Path, Path]:
        bin_dir = root / "bin"
        log_dir = root / ".fake_codex"
        bin_dir.mkdir(parents=True, exist_ok=True)
        log_dir.mkdir(parents=True, exist_ok=True)

        codex_script = bin_dir / "codex"
        codex_script.write_text(
            textwrap.dedent(
                """\
                #!/usr/bin/env python3
                from pathlib import Path
                import json
                import os
                import sys

                log_dir = Path(os.environ["PLANVEYOR_FAKE_CODEX_DIR"])
                log_dir.mkdir(parents=True, exist_ok=True)
                sid_map = json.loads(os.environ.get("PLANVEYOR_FAKE_CODEX_ROLE_SIDS_JSON", "{}"))
                fail_role = os.environ.get("PLANVEYOR_FAKE_CODEX_FAIL_ROLE", "").strip().lower()
                fail_code = int(os.environ.get("PLANVEYOR_FAKE_CODEX_FAIL_CODE", "17"))

                counter_path = log_dir / "counter"
                try:
                    counter = int(counter_path.read_text(encoding="utf-8").strip())
                except FileNotFoundError:
                    counter = 0
                counter += 1
                counter_path.write_text(str(counter), encoding="utf-8")

                stdin_text = sys.stdin.read()
                role = ""
                lane = ""
                for line in stdin_text.splitlines():
                    if line.startswith("ROLE="):
                        role = line.split("=", 1)[1].strip().lower()
                    if line.startswith("REVIEWER_LANE="):
                        lane = line.split("=", 1)[1].strip().lower()

                stdin_path = log_dir / f"stdin-{counter}.txt"
                stdin_path.write_text(stdin_text, encoding="utf-8")

                identity = lane if role == "reviewer" and lane else role
                entry = {
                    "argv": sys.argv[1:],
                    "cwd": os.getcwd(),
                    "role": role,
                    "lane": lane,
                    "identity": identity,
                    "stdin_path": str(stdin_path),
                    "role_run_env_keys": sorted(k for k in os.environ if k.startswith("PLANVEYOR_ROLE_RUN_")),
                }
                with (log_dir / "calls.jsonl").open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry) + "\\n")

                if role and role == fail_role:
                    print(f"Fake Codex failure for {role}")
                    sys.exit(fail_code)

                sid = sid_map.get(identity, sid_map.get(role, ""))
                print(f"Fake Codex session {sid}")
                print(f"role={role}")
                if lane:
                    print(f"lane={lane}")
                """
            ),
            encoding="utf-8",
        )
        codex_script.chmod(0o755)

        for command_name in ("claude",):
            claude_script = bin_dir / command_name
            claude_script.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env python3
                    from pathlib import Path
                    import json
                    import os
                    import sys

                    log_dir = Path(os.environ["PLANVEYOR_FAKE_CODEX_DIR"])
                    log_dir.mkdir(parents=True, exist_ok=True)

                    args = sys.argv[1:]
                    sid = ""
                    for idx, arg in enumerate(args):
                        if arg in {"--session-id", "--resume", "-r"} and idx + 1 < len(args):
                            sid = args[idx + 1]
                    prompt = args[-1] if args else ""

                    role = ""
                    lane = ""
                    for line in prompt.splitlines():
                        if line.startswith("ROLE="):
                            role = line.split("=", 1)[1].strip().lower()
                        if line.startswith("REVIEWER_LANE="):
                            lane = line.split("=", 1)[1].strip().lower()

                    entry = {
                        "command": Path(sys.argv[0]).name,
                        "argv": args,
                        "cwd": os.getcwd(),
                        "role": role,
                        "lane": lane,
                        "sid": sid,
                        "prompt": prompt,
                    }
                    with (log_dir / "claude_calls.jsonl").open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps(entry) + "\\n")

                    fail_role = os.environ.get("PLANVEYOR_FAKE_CODEX_FAIL_ROLE", "").strip().lower()
                    fail_code = int(os.environ.get("PLANVEYOR_FAKE_CODEX_FAIL_CODE", "17"))
                    if role and role == fail_role:
                        print(f"Fake {Path(sys.argv[0]).name} failure for {role}")
                        sys.exit(fail_code)

                    print(f"Fake {Path(sys.argv[0]).name} session {sid}")
                    print(f"role={role}")
                    if lane:
                        print(f"lane={lane}")
                    """
                ),
                encoding="utf-8",
            )
            claude_script.chmod(0o755)
        return bin_dir, log_dir

    def _write_runtime_facade_shim(
        self,
        path: Path,
        *,
        source_script: Path = PLANVEYOR_SCRIPT,
    ) -> None:
        """Keep a fixture facade regular while loading the complete runtime."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "#!/bin/zsh\n"
            "# Test fixture shim: source the same complete runtime as its login child.\n"
            f"source {shlex.quote(str(source_script))}\n",
            encoding="utf-8",
        )

    def _complete_runtime_manifest(self, root: Path) -> str:
        """Hash the complete regular runtime closure used by legacy fixtures."""
        rows: list[str] = []
        for relative_root in (Path("scripts"), Path("docs")):
            source_root = root / relative_root
            self.assertTrue(source_root.is_dir(), source_root)
            for path in sorted(source_root.rglob("*")):
                relative_path = path.relative_to(root)
                if "__pycache__" in relative_path.parts or path.name.endswith(".pyc"):
                    continue
                self.assertFalse(path.is_symlink(), path)
                if path.is_file():
                    digest = hashlib.sha256(path.read_bytes()).hexdigest()
                    mode = stat.S_IMODE(path.stat().st_mode)
                    rows.append(f"{relative_path.as_posix()}\t{mode:04o}\t{digest}")
        return hashlib.sha256(("\n".join(rows) + "\n").encode("utf-8")).hexdigest()

    def _copy_complete_legacy_runtime_fixture(self, root: Path) -> str:
        """Copy a complete unattested runtime without creating Git metadata."""
        source_manifest = self._complete_runtime_manifest(REPO_ROOT)
        for relative_root in (Path("scripts"), Path("docs")):
            shutil.copytree(
                REPO_ROOT / relative_root,
                root / relative_root,
                symlinks=False,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
        self.assertFalse((root / ".git").exists())
        copied_manifest = self._complete_runtime_manifest(root)
        self.assertEqual(copied_manifest, source_manifest)
        return copied_manifest

    def _assert_legacy_complete_runtime_identity(
        self,
        root: Path,
        env: dict[str, str],
        *,
        expected_manifest: str | None = None,
    ) -> str:
        """Keep parent and legacy child on one unchanged unattested runtime."""
        runtime_root = Path(env["PLANVEYOR_ROOT"])
        self.assertTrue(runtime_root.is_dir(), runtime_root)
        self.assertFalse((runtime_root / ".git").exists())
        self.assertEqual(
            self._git(root, "rev-parse", "--is-inside-work-tree").stdout.strip(),
            "true",
        )
        expected_facade = (
            "#!/bin/zsh\n"
            "# Test fixture shim: source the same complete runtime as its login child.\n"
            f"source {shlex.quote(str(runtime_root / 'scripts' / 'planveyor.zsh'))}\n"
        )
        self.assertEqual(
            (root / "scripts" / "planveyor.zsh").read_text(encoding="utf-8"),
            expected_facade,
        )
        manifest = self._complete_runtime_manifest(runtime_root)
        if expected_manifest is not None:
            self.assertEqual(manifest, expected_manifest)

        identity = self._run(
            root,
            env,
            'context="$(_planveyor_pre_dispatch init_capture_legacy_complete_identity)" || exit $?; '
            'print -r -- "$_PLANVEYOR_AUTHORITY_SOURCE_STATE"; '
            'print -r -- "$_PLANVEYOR_AUTHORITY_RUNTIME_ROOT"; '
            'print -r -- "$context"',
        )
        self.assertEqual(identity.returncode, 0, identity.stderr)
        source_state, loaded_runtime_root, context_json = identity.stdout.splitlines()
        context = json.loads(context_json)
        self.assertEqual(source_state, "unattested_legacy")
        self.assertEqual(Path(loaded_runtime_root), runtime_root.resolve())
        self.assertEqual(context["state"], "legacy")
        self.assertEqual(Path(context["project_root"]), root.resolve())
        self.assertIsNone(context["runtime_pin"])
        return manifest

    def _monotonic_timestamp_writer(self, path: Path, env: dict[str, str]) -> str:
        """Return a fixture-local command that writes one durable monotonic time."""
        writer = (
            "import os\n"
            "import pathlib\n"
            "import sys\n"
            "import time\n"
            "path = pathlib.Path(sys.argv[1])\n"
            "flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, 'O_NOFOLLOW', 0)\n"
            "fd = os.open(path, flags, 0o600)\n"
            "with os.fdopen(fd, 'w', encoding='ascii') as handle:\n"
            "    handle.write(f'{time.monotonic():.9f}\\n')\n"
            "    handle.flush()\n"
            "    os.fsync(handle.fileno())\n"
            "os.chmod(path, 0o600)\n"
        )
        return (
            f"{shlex.quote(env['PYBIN'])} -c {shlex.quote(writer)} "
            f"{shlex.quote(str(path))}"
        )

    def _read_monotonic_timestamp(self, path: Path, label: str) -> float:
        """Fail closed when a fixture fault/close timestamp is unavailable."""
        try:
            info = path.lstat()
            self.assertTrue(stat.S_ISREG(info.st_mode), f"{label} is not regular: {path}")
            self.assertEqual(stat.S_IMODE(info.st_mode), 0o600, path)
            value = float(path.read_text(encoding="ascii").strip())
        except (FileNotFoundError, OSError, ValueError) as exc:
            self.fail(f"missing or malformed {label}: {path}: {exc}")
        self.assertGreater(value, 0.0, f"malformed {label}: {path}")
        return value

    def _copy_complete_runtime_fixture(self, root: Path) -> None:
        """Create a committed distinct runtime root for launcher-root drift."""
        shutil.copytree(
            REPO_ROOT / "scripts",
            root / "scripts",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        for relative_path in (
            Path("docs/_meta/runner_selection_resolution.v1.json"),
            Path("docs/tools/dotfiles/bx/bxconfig.toml"),
            Path("docs/tools/dotfiles/bx/bxignore"),
            Path("docs/tools/dotfiles/zsh/zprofile"),
            Path("docs/tools/dotfiles/zsh/zshrc"),
        ):
            destination = root / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO_ROOT / relative_path, destination)
        self._git(root, "init")
        self._git(root, "config", "user.name", "Test User")
        self._git(root, "config", "user.email", 'test' + '@' + 'example' + '.' + 'com')
        self._git(root, "add", "--", "scripts", "docs")
        self._git(root, "commit", "-m", "fixture full runtime")

    def _prepare_repo(
        self,
        tmpdir: str,
        *,
        sid_map: dict[str, str] | None = None,
        fail_role: str = "",
        fail_code: int = 17,
        runtime_mode: str = "default_git",
    ) -> tuple[Path, dict[str, str], Path]:
        root = Path(tmpdir) / "planveyor-init-capture"
        runtime_root = REPO_ROOT
        if runtime_mode == "legacy_complete":
            runtime_root = Path(tmpdir) / "planveyor-legacy-complete-runtime"
            self._copy_complete_legacy_runtime_fixture(runtime_root)
        elif runtime_mode != "default_git":
            raise ValueError(f"Unsupported runtime fixture mode: {runtime_mode}")
        self._write_runtime_facade_shim(
            root / "scripts" / "planveyor.zsh",
            source_script=runtime_root / "scripts" / "planveyor.zsh",
        )

        self._git(root, "init")
        self._git(root, "config", "user.name", "Test User")
        self._git(root, "config", "user.email", 'test' + '@' + 'example' + '.' + 'com')
        # These are positive legacy-Git fixtures.  Give each one a valid
        # committed HEAD and index so authority admission does not conflate it
        # with the separately covered unborn-Git fail-closed boundary.
        self._git(root, "add", "--", "scripts/planveyor.zsh")
        self._git(root, "commit", "-m", "fixture baseline")

        bin_dir, log_dir = self._install_fake_codex(root)
        home_dir = root / ".home"
        codex_home = root / ".codex-home"
        home_dir.mkdir(parents=True, exist_ok=True)
        codex_home.mkdir(parents=True, exist_ok=True)
        child_tmp = (Path(tmpdir) / "planveyor-init-capture-child-tmp").resolve()
        child_tmp.mkdir(exist_ok=True)

        # Strip ambient PLANVEYOR_ROLE_RUN_* (e.g. when the suite runs inside a
        # planveyor_role_run session, which exports these to its own process env) so
        # tests assert helper-injection isolation only, not caller-exported env.
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("PLANVEYOR_ROLE_RUN_")
        }
        for key in (
            "PLANVEYOR_CLAUDE_COMMAND",
            "PLANVEYOR_CLAUDE_MODEL",
            "PLANVEYOR_CLAUDE_EFFORT",
        ):
            env.pop(key, None)
        env["HOME"] = str(home_dir)
        env["CODEX_HOME"] = str(codex_home)
        env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
        env["TMPDIR"] = str(child_tmp)
        env["TMPPREFIX"] = str(child_tmp / "zsh")
        env["PYBIN"] = sys.executable
        env["PLANVEYOR_ROOT"] = str(runtime_root)
        env["PLANVEYOR_FAKE_CODEX_DIR"] = str(log_dir)
        env["PLANVEYOR_FAKE_CODEX_BIN"] = str(bin_dir)
        env["PLANVEYOR_FAKE_CODEX_ROLE_SIDS_JSON"] = json.dumps(sid_map or {})
        env["PLANVEYOR_FAKE_CODEX_FAIL_ROLE"] = fail_role
        env["PLANVEYOR_FAKE_CODEX_FAIL_CODE"] = str(fail_code)
        return root, env, log_dir

    def _source_repo_id(self) -> str:
        remote = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "config", "--get", "remote.origin.url"],
            text=True,
            capture_output=True,
            check=False,
        ).stdout.strip()
        if remote:
            remote = re.sub(r"^([A-Za-z][A-Za-z0-9+.-]*://)[^/@]+@", r"\1", remote)
            identity = f"remote:{remote}"
        else:
            common_dir = subprocess.run(
                ["git", "-C", str(REPO_ROOT), "rev-parse", "--git-common-dir"],
                text=True,
                capture_output=True,
                check=True,
            ).stdout.strip()
            if not os.path.isabs(common_dir):
                common_dir = str((REPO_ROOT / common_dir).resolve())
            identity = f"git-common-dir:{common_dir}"
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()


    def _run(
        self,
        root: Path,
        env: dict[str, str],
        command: str,
        *,
        source_script: Path | str = Path("scripts/planveyor.zsh"),
        timeout_seconds: float = 60,
    ) -> subprocess.CompletedProcess[str]:
        shell_command = (
            f'export PATH={shlex.quote(env["PLANVEYOR_FAKE_CODEX_BIN"])}:$PATH; '
            f"source {shlex.quote(str(source_script))} && {command}"
        )
        argv = ["/bin/zsh", "-fc", shell_command]
        try:
            return subprocess.run(
                argv,
                cwd=root,
                text=True,
                capture_output=True,
                stdin=subprocess.DEVNULL,
                timeout=timeout_seconds,
                env=env,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            self.fail(
                "\x1b[31mtest child timed out: "
                f"argv={argv!r}; cwd={root}; timeout={exc.timeout!r}; "
                f"stdout={exc.stdout!r}; stderr={exc.stderr!r}\x1b[0m"
            )

    def _codex_expected_model_for_profile(
        self, root: Path, env: dict[str, str], profile: str
    ) -> str:
        result = self._run(
            root,
            env,
            f"_planveyor_codex_expected_model_for_profile {shlex.quote(profile)}",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        expected_model = result.stdout.strip()
        self.assertTrue(expected_model)
        return expected_model

    def test_run_timeout_is_fail_closed_with_context(self) -> None:
        root = Path("/tmp/planveyor-init-timeout")
        env = {"PLANVEYOR_FAKE_CODEX_BIN": "/tmp/planveyor-fake-bin"}
        expired = subprocess.TimeoutExpired(
            ["/bin/zsh", "-fc", "timeout-fixture"],
            60,
            output="fake stdout",
            stderr="fake stderr",
        )

        with mock.patch.object(subprocess, "run", side_effect=expired) as run:
            with self.assertRaisesRegex(AssertionError, "test child timed out") as raised:
                self._run(root, env, "timeout-fixture")

        message = str(raised.exception)
        self.assertIn("argv=", message)
        self.assertIn("cwd=/tmp/planveyor-init-timeout", message)
        self.assertIn("stdout='fake stdout'", message)
        self.assertIn("stderr='fake stderr'", message)
        self.assertEqual(run.call_args.kwargs["stdin"], subprocess.DEVNULL)
        self.assertEqual(run.call_args.kwargs["timeout"], 60)

    def _codex_calls(self, log_dir: Path) -> list[dict[str, object]]:
        log_path = log_dir / "calls.jsonl"
        if not log_path.exists():
            return []
        return [
            json.loads(line)
            for line in log_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def _claude_calls(self, log_dir: Path) -> list[dict[str, object]]:
        log_path = log_dir / "claude_calls.jsonl"
        if not log_path.exists():
            return []
        return [
            json.loads(line)
            for line in log_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def _write_runtime_plan(self, root: Path, *, status: str = "In progress") -> Path:
        plan_path = root / "docs" / "plans" / "260101_0000_test_runtime.md"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(
            textwrap.dedent(
                f"""\
                # Plan: runtime test

                **Date:** 2026-01-01 00:00 MSK
                **Plan type:** dev
                **Status:** {status}

                ## Evidence
                """
            ),
            encoding="utf-8",
        )
        return plan_path

    def _write_role_outcome_runtime_plan(
        self,
        root: Path,
        *,
        evidence: str = "",
    ) -> Path:
        plan_path = root / "docs" / "plans" / "260101_0000_test_runtime.md"
        review_path = root / "docs" / "code_reviews" / "260101_0000_test_runtime.md"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        review_path.parent.mkdir(parents=True, exist_ok=True)
        review_path.write_text("# Runtime review\n\n## Evidence\n", encoding="utf-8")
        plan_path.write_text(
            "\n".join(
                (
                    "# Plan: role outcome runtime test",
                    "",
                    "**Date:** 2026-01-01 00:00 MSK",
                    "**Plan type:** dev",
                    "**Status:** In progress",
                    "",
                    "## Verification rerun / exec handoff",
                    "- Mode: manager-custom-pipeline",
                    "",
                    "## Review artifacts",
                    "- Code review (primary): `docs/code_reviews/260101_0000_test_runtime.md`",
                    "",
                    "## Evidence",
                    evidence,
                    "",
                )
            ),
            encoding="utf-8",
        )
        return plan_path

    def _role_outcome_semantic_draft(self) -> str:
        fields = (
            "worked",
            "blocked_by",
            "helped_by",
            "residuals",
            "candidate_followups",
            "gates",
        )
        rows = ["- Role outcome semantic draft"]
        for field in fields:
            rows.extend((f"  - {field}:", f"    - scripts/test_planveyor_init_capture.py::{field}"))
        return "\n".join(rows)

    def test_in_scope_init_wrappers_promote_run_artifacts_by_sid(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_init_capture_") as tmpdir:
            root, env, log_dir = self._prepare_repo(
                tmpdir,
                sid_map=SUCCESS_SIDS,
                runtime_mode="legacy_complete",
            )
            runtime_manifest = self._assert_legacy_complete_runtime_identity(root, env)

            result = self._run(
                root,
                env,
                "planveyor_runner_set planner codex >/dev/null && "
                "planveyor_runner_set reviewer codex >/dev/null && "
                "planveyor_arch_init >/dev/null && "
                "planveyor_manager_init >/dev/null && "
                "planveyor_coder_init >/dev/null && "
                "planveyor_planner_init >/dev/null && "
                "planveyor_reviewer_init >/dev/null",
            )

            self.assertEqual(result.returncode, 0, result.stderr)

            calls = self._codex_calls(log_dir)
            self.assertEqual([str(call["role"]) for call in calls], list(SUCCESS_SIDS.keys()))

            for role, sid in SUCCESS_SIDS.items():
                session_file = root / f".planveyor.session.{role}"
                self.assertTrue(session_file.exists(), role)
                session_text = session_file.read_text(encoding="utf-8")
                self.assertEqual(session_text.splitlines()[-1], sid)

                artifact_dir = root / ".planveyor.init_runs" / "by_sid" / sid
                self.assertTrue((artifact_dir / "run.log").exists(), role)
                self.assertTrue((artifact_dir / "meta.json").exists(), role)

                run_log = (artifact_dir / "run.log").read_text(encoding="utf-8")
                self.assertIn(f"Fake Codex session {sid}", run_log)
                self.assertIn(f"role={role}", run_log)

                meta = json.loads((artifact_dir / "meta.json").read_text(encoding="utf-8"))
                self.assertEqual(meta["role"], role)
                self.assertEqual(meta["session_key"], role)
                self.assertEqual(meta["runner"], "codex")
                self.assertEqual(meta["profile"], EXPECTED_PROFILES[role])
                self.assertEqual(os.path.realpath(meta["cwd"]), os.path.realpath(str(root)))
                self.assertEqual(os.path.realpath(meta["repo_root"]), os.path.realpath(str(root)))
                self.assertEqual(meta["provider_home_state"], "consumer-default")
                self.assertNotIn("codex_home", meta)
                self.assertEqual(meta["exit_code"], 0)
                self.assertEqual(meta["sid"], sid)
                self.assertTrue(meta["launched_at"].endswith("Z"))
                self.assertFalse(any("selection" in key for key in meta), role)
                self.assertNotIn("selection_digest", session_text)
                self.assertNotIn("init_attempt_id", session_text)

                pending_role_dir = root / ".planveyor.init_runs" / "pending" / role
                if pending_role_dir.exists():
                    self.assertEqual(list(pending_role_dir.iterdir()), [], role)

            self._assert_legacy_complete_runtime_identity(
                root,
                env,
                expected_manifest=runtime_manifest,
            )

    def test_failed_init_without_sid_stays_under_pending(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_init_capture_") as tmpdir:
            root, env, _ = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS, fail_role="coder", fail_code=17)

            result = self._run(root, env, "planveyor_coder_init >/dev/null")

            self.assertEqual(result.returncode, 17)
            self.assertIn("Could not detect session id", result.stderr)
            self.assertFalse((root / ".planveyor.session.coder").exists())

            pending_role_dir = root / ".planveyor.init_runs" / "pending" / "coder"
            self.assertTrue(pending_role_dir.exists())
            pending_runs = sorted(path for path in pending_role_dir.iterdir() if path.is_dir())
            self.assertEqual(len(pending_runs), 1)

            artifact_dir = pending_runs[0]
            run_log = (artifact_dir / "run.log").read_text(encoding="utf-8")
            meta = json.loads((artifact_dir / "meta.json").read_text(encoding="utf-8"))

            self.assertIn("Fake Codex failure for coder", run_log)
            self.assertIsNone(meta["sid"])
            self.assertEqual(meta["role"], "coder")
            self.assertEqual(meta["session_key"], "coder")
            self.assertEqual(meta["runner"], "codex")
            self.assertEqual(meta["profile"], EXPECTED_PROFILES["coder"])
            self.assertEqual(meta["exit_code"], 17)

            by_sid_dir = root / ".planveyor.init_runs" / "by_sid"
            self.assertFalse(by_sid_dir.exists() and any(by_sid_dir.iterdir()))

    def test_strict_runner_selection_matrix_policy_and_consumer_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_runner_selection_") as tmpdir:
            root, env, _ = self._prepare_repo(tmpdir)
            fields = {
                "carrier_state",
                "init_attempt_id",
                "role",
                "runner",
                "schema_version",
                "selection_digest",
            }

            for role, runners in RUNNER_MATRIX.items():
                for runner in runners:
                    with self.subTest(role=role, runner=runner):
                        attempt = str(uuid.uuid4())
                        result = self._run(
                            root,
                            env,
                            f"planveyor_runner_set {role} {runner} >/dev/null 2>&1 && "
                            f"planveyor_runner_resolve_strict {role} {attempt}",
                        )
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(result.stderr, "")
                        self.assertEqual(len(result.stdout.splitlines()), 1)
                        payload = json.loads(result.stdout)
                        self.assertEqual(set(payload), fields)
                        self.assertEqual(payload["schema_version"], "runner_selection_resolution.v1")
                        self.assertEqual(payload["carrier_state"], "present_valid")
                        self.assertEqual(payload["init_attempt_id"], attempt)
                        self.assertEqual(payload["role"], role)
                        self.assertEqual(payload["runner"], runner)
                        identity = {
                            "carrier_state": "present_valid",
                            "role": role,
                            "runner": runner,
                            "schema_version": "runner_selection_identity.v1",
                        }
                        canonical = json.dumps(
                            identity,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                        self.assertEqual(
                            payload["selection_digest"],
                            hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
                        )

            for role in RUNNER_MATRIX:
                with self.subTest(absent_default=role):
                    carrier = root / f".planveyor.runner.{role}"
                    carrier.unlink(missing_ok=True)
                    result = self._run(
                        root,
                        env,
                        f"planveyor_runner_resolve_strict {role} {uuid.uuid4()}",
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    payload = json.loads(result.stdout)
                    self.assertEqual(payload["carrier_state"], "absent_default")
                    self.assertEqual(payload["runner"], "codex")

            carrier = root / ".planveyor.runner.coder"
            red_carriers = (
                ("blank", lambda: carrier.write_text("\n", encoding="utf-8")),
                ("unknown", lambda: carrier.write_text("unknown\n", encoding="utf-8")),
                ("role_invalid", lambda: carrier.write_text("claude\n", encoding="utf-8")),
                ("malformed", lambda: carrier.write_text("codex\ncodex\n", encoding="utf-8")),
            )
            for state, write_carrier in red_carriers:
                with self.subTest(carrier_state=state):
                    carrier.unlink(missing_ok=True)
                    if carrier.is_dir():
                        shutil.rmtree(carrier)
                    write_carrier()
                    result = self._run(
                        root,
                        env,
                        f"planveyor_runner_resolve_strict coder {uuid.uuid4()}",
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(result.stdout, "")
                    self.assertIn("runner_selection_error=", result.stderr)

            carrier.unlink(missing_ok=True)
            carrier.mkdir()
            non_regular = self._run(
                root,
                env,
                f"planveyor_runner_resolve_strict coder {uuid.uuid4()}",
            )
            self.assertNotEqual(non_regular.returncode, 0)
            self.assertIn("runner_selection_error=carrier_non_regular", non_regular.stderr)
            carrier.rmdir()

            carrier.write_text("codex\n", encoding="utf-8")
            carrier.chmod(0)
            unreadable = self._run(
                root,
                env,
                f"planveyor_runner_resolve_strict coder {uuid.uuid4()}",
            )
            self.assertNotEqual(unreadable.returncode, 0)
            self.assertIn("runner_selection_error=carrier_unreadable", unreadable.stderr)
            carrier.chmod(0o600)

            attempt = str(uuid.uuid4())
            green = self._run(root, env, f"planveyor_runner_resolve_strict coder {attempt}")
            self.assertEqual(green.returncode, 0, green.stderr)
            payload = json.loads(green.stdout)
            consumer = self._run(
                root,
                env,
                "_planveyor_runner_selection_init_consume coder "
                f"{attempt} {shlex.quote(green.stdout.strip())}",
            )
            self.assertEqual(consumer.returncode, 0, consumer.stderr)
            self.assertEqual(consumer.stdout.strip(), f"codex\t{payload['selection_digest']}")

            invalid_payloads = {
                "multiple": f"{green.stdout.strip()} {green.stdout.strip()}",
                "wrong_role": json.dumps({**payload, "role": "planner"}),
                "foreign_attempt": json.dumps({**payload, "init_attempt_id": str(uuid.uuid4())}),
                "bad_digest": json.dumps({**payload, "selection_digest": "0" * 64}),
            }
            for state, raw_payload in invalid_payloads.items():
                with self.subTest(consumer_state=state):
                    result = self._run(
                        root,
                        env,
                        "_planveyor_runner_selection_init_consume coder "
                        f"{attempt} {shlex.quote(raw_payload)}",
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(result.stdout, "")
                    self.assertIn("runner_selection_error=", result.stderr)

            # Keep the fixture on its pinned runtime and replace only the
            # reader seam that locates the policy host.  An environment-root
            # override would make the source facade and login child disagree.
            policy_path = root / "policy-fixture" / "runner_selection_resolution.v1.json"
            policy_path.parent.mkdir(parents=True)
            policy_reader = (
                "_planveyor_runner_selection_policy_path() { print -r -- "
                f"{shlex.quote(str(policy_path))}; }}; "
            )
            missing_policy = self._run(
                root,
                env,
                policy_reader + f"planveyor_runner_resolve_strict coder {uuid.uuid4()}",
            )
            self.assertNotEqual(missing_policy.returncode, 0)
            self.assertIn("runner_selection_error=policy_host_missing", missing_policy.stderr)
            policy_path.write_text("{\"schema_version\":\n", encoding="utf-8")
            malformed_policy = self._run(
                root,
                env,
                policy_reader + f"planveyor_runner_resolve_strict coder {uuid.uuid4()}",
            )
            self.assertNotEqual(malformed_policy.returncode, 0)
            self.assertIn("runner_selection_error=policy_host_invalid", malformed_policy.stderr)

    def test_runner_selection_init_precedes_artifacts_and_consumes_captured_bytes_once(self) -> None:
        init_commands = {
            "architect": "planveyor_arch_init",
            "manager": "planveyor_manager_init",
            "coder": "planveyor_coder_init",
            "planner": "planveyor_planner_init",
            "reviewer": "planveyor_reviewer_init",
        }
        for role, command in init_commands.items():
            with self.subTest(fail_before_mutation=role), tempfile.TemporaryDirectory(
                prefix="planveyor_runner_selection_pre_sid_"
            ) as tmpdir:
                root, env, log_dir = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
                (root / f".planveyor.runner.{role}").write_text("\n", encoding="utf-8")
                bundle_marker = root / f"{role}.bundle-marker"
                result = self._run(
                    root,
                    env,
                    "_planveyor_prepare_role_bundle() { touch "
                    f"{shlex.quote(str(bundle_marker))}; }}; {command}",
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("runner_selection_error=carrier_blank", result.stderr)
                self.assertFalse(bundle_marker.exists())
                self.assertEqual(self._codex_calls(log_dir), [])
                self.assertEqual(self._claude_calls(log_dir), [])
                self.assertFalse((root / f".planveyor.session.{role}").exists())
                self.assertFalse((root / ".planveyor.init_runs").exists())

        with tempfile.TemporaryDirectory(prefix="planveyor_runner_selection_once_") as tmpdir:
            root, env, log_dir = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
            result = self._run(
                root,
                env,
                "functions -c planveyor_runner_resolve_strict _test_original_runner_resolve; "
                "planveyor_runner_resolve_strict() { _test_original_runner_resolve \"$@\"; "
                "local rc=$?; printf 'invalid_runner\\n' > .planveyor.runner.coder; return $rc; }; "
                "planveyor_runner() { print -r -- invalid_runner; }; "
                "planveyor_coder_init >/dev/null",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual([call["role"] for call in self._codex_calls(log_dir)], ["coder"])
            self.assertEqual(self._claude_calls(log_dir), [])
            meta = json.loads(
                (root / ".planveyor.init_runs" / "by_sid" / SUCCESS_SIDS["coder"] / "meta.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(meta["runner"], "codex")
            self.assertFalse(any("selection" in key for key in meta))
            session_text = (root / ".planveyor.session.coder").read_text(encoding="utf-8")
            self.assertNotIn("selection_digest", session_text)
            self.assertNotIn("init_attempt_id", session_text)

            before = (root / ".planveyor.runner.coder").read_bytes()
            atomic_failure = self._run(
                root,
                env,
                "mv() { return 92; }; planveyor_runner_set coder codex",
            )
            self.assertNotEqual(atomic_failure.returncode, 0)
            self.assertEqual((root / ".planveyor.runner.coder").read_bytes(), before)

        playbook = (REPO_ROOT / "docs" / "playbooks" / "external_runner_bootstrap.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("runner_selection_resolution.v1", playbook)
        self.assertIn("planveyor_runner_resolve_strict", playbook)
        self.assertIn("target_writable_carriers", playbook)

    def test_direct_claude_planner_init_forwards_explicit_options_and_saves_neutral_session(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_init_capture_") as tmpdir:
            root, env, log_dir = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
            env["PLANVEYOR_CLAUDE_MODEL"] = "fixture-claude-model"
            env["PLANVEYOR_CLAUDE_EFFORT"] = "fixture-claude-effort"

            result = self._run(
                root,
                env,
                "planveyor_runner_set planner claude >/dev/null && planveyor_planner_init >/dev/null",
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            calls = self._claude_calls(log_dir)
            self.assertEqual(len(calls), 1)
            call = calls[0]
            self.assertEqual(call["command"], "claude")
            self.assertEqual(call["role"], "planner")
            sid = str(call["sid"])
            self.assertRegex(sid, r"^[0-9a-f-]{36}$")
            argv = [str(item) for item in call["argv"]]
            self.assertEqual(
                argv[:10],
                [
                    "--model",
                    "fixture-claude-model",
                    "--effort",
                    "fixture-claude-effort",
                    "-p",
                    "--session-id",
                    sid,
                    "--permission-mode",
                    "acceptEdits",
                    argv[9],
                ],
            )
            self.assertIn("ROLE=Planner", str(call["prompt"]))

            session_text = (root / ".planveyor.session.planner").read_text(encoding="utf-8")
            self.assertEqual(session_text.splitlines()[-1], sid)
            self.assertIn("runner=claude", session_text)
            self.assertIn("profile=direct_child", session_text)
            self.assertNotIn(env["HOME"], session_text)
            self.assertNotIn("codex_home=", session_text)

            init_meta = json.loads(
                (root / ".planveyor.init_runs" / "by_sid" / sid / "meta.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(init_meta["role"], "planner")
            self.assertEqual(init_meta["session_key"], "planner")
            self.assertEqual(init_meta["runner"], "claude")
            self.assertEqual(init_meta["profile"], "direct_child")
            self.assertEqual(init_meta["provider_home_state"], "unavailable")
            self.assertEqual(init_meta["configured_model_id"], "fixture-claude-model")
            self.assertEqual(init_meta["model_id_state"], "configured_explicit")
            self.assertEqual(init_meta["configured_effort"], "fixture-claude-effort")
            self.assertEqual(init_meta["effort_state"], "configured_explicit")
            self.assertNotIn(env["HOME"], json.dumps(init_meta, sort_keys=True))



    def test_censor_variants_have_exact_preflight_help_and_readiness_mappings(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_censor_preflight_") as tmpdir:
            root, env, _ = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
            variants = {
                "architect_censor": ("architect", "planveyor_arch_censor"),
                "planner_censor": ("planner", "planveyor_planner_censor"),
                "coder_censor": ("coder", "planveyor_coder_censor"),
            }

            for role_key, (runner_role, wrapper) in variants.items():
                sid = SUCCESS_SIDS[runner_role]
                result = self._run(
                    root,
                    env,
                    f"planveyor_session_set {runner_role} {sid} runner=codex >/dev/null && "
                    f"planveyor_role_runner_preflight {role_key} --json",
                )

                self.assertEqual(result.returncode, 0, result.stderr)
                payload = json.loads(result.stdout)
                self.assertEqual(payload["role"], role_key)
                self.assertEqual(payload["session_key"], runner_role)
                self.assertEqual(payload["wrapper"], wrapper)
                self.assertEqual(payload["runner_role"], runner_role)
                self.assertEqual(payload["runner_id"], "codex")
                self.assertEqual(payload["profile"], "N/A (why=profile not readable)")
                self.assertEqual(payload["model"], "")
                self.assertTrue(payload["execution_ready"])

                override_profile = f"test-{runner_role}-censor"
                override_result = self._run(
                    root,
                    env,
                    f"planveyor_profile_set {runner_role} {override_profile} censor >/dev/null && "
                    f"planveyor_role_runner_preflight {role_key} --json",
                )
                self.assertEqual(override_result.returncode, 0, override_result.stderr)
                override_payload = json.loads(override_result.stdout)
                self.assertEqual(override_payload["profile"], override_profile)
                self.assertEqual(override_payload["model"], "")

            preflight_help = self._run(root, env, "planveyor_role_runner_preflight --help")
            role_run_help = self._run(root, env, "planveyor_role_run --help")
            # The public wide readback synchronously aggregates the fixed ten-role
            # readiness table.
            readiness = self._run(
                root,
                env,
                "planveyor_show_manual --wide",
                timeout_seconds=120,
            )
            for result in (preflight_help, role_run_help, readiness):
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("planner_censor", result.stderr + result.stdout)
                self.assertIn("coder_censor", result.stderr + result.stdout)

            public_preflight_help = self._run(root, env, "planveyor_help planveyor_role_runner_preflight")
            public_role_run_help = self._run(root, env, "planveyor_help planveyor_role_run")
            for result in (public_preflight_help, public_role_run_help):
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("planner_censor", result.stdout)
                self.assertIn("coder_censor", result.stdout)

    def test_preflight_codex_capture_uses_only_required_success_identity(self) -> None:
        """Codex capture success does not prove optional model or effort identity."""

        with tempfile.TemporaryDirectory(prefix="planveyor_codex_capture_preflight_") as tmpdir:
            root, env, _ = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
            codex_sid = "00000000-0000-4000-8000-000000000151"
            setup = self._run(
                root,
                env,
                f"planveyor_session_set architect {codex_sid} runner=codex >/dev/null",
            )
            self.assertEqual(setup.returncode, 0, setup.stderr)
            meta_path = root / ".planveyor.init_runs" / "by_sid" / codex_sid / "meta.json"
            base_meta = {
                "role": "architect",
                "runner": "codex",
                "session_key": "architect",
                "exit_code": 0,
            }

            def write_meta(meta: dict[str, object]) -> None:
                meta_path.parent.mkdir(parents=True, exist_ok=True)
                meta_path.write_text(json.dumps(meta), encoding="utf-8")

            def read_codex_preflight() -> dict[str, object]:
                result = self._run(root, env, "planveyor_role_runner_preflight architect --json")
                self.assertEqual(result.returncode, 0, result.stderr)
                return json.loads(result.stdout)

            write_meta(base_meta)
            success = read_codex_preflight()
            self.assertEqual(success["init_run_outcome"], "success")
            self.assertTrue(success["execution_ready"])
            self.assertEqual(success["reason"], "ok")
            self.assertEqual(success["model_id_state"], "unknown")
            self.assertTrue(str(success["init_run_configured_model_id"]).startswith("N/A"))
            self.assertTrue(str(success["init_run_effort_state"]).startswith("N/A"))

            nonzero_meta = dict(base_meta, exit_code=23)
            write_meta(nonzero_meta)
            nonzero = read_codex_preflight()
            self.assertEqual(nonzero["init_run_outcome"], "failed")
            self.assertTrue(nonzero["execution_ready"])

            missing_exit_meta = dict(base_meta)
            del missing_exit_meta["exit_code"]
            for name, meta in (
                ("missing_exit", missing_exit_meta),
                ("malformed_exit", dict(base_meta, exit_code="not-an-integer")),
                ("wrong_role", dict(base_meta, role="planner")),
                ("wrong_runner", dict(base_meta, runner="claude")),
                ("wrong_session_key", dict(base_meta, session_key="planner")),
            ):
                with self.subTest(case=name):
                    write_meta(meta)
                    invalid = read_codex_preflight()
                    self.assertEqual(invalid["init_run_outcome"], "invalid")
                    self.assertTrue(invalid["execution_ready"])

            claude_sid = "00000000-0000-4000-8000-000000000152"
            claude_env = dict(env)
            claude_env["PLANVEYOR_CLAUDE_MODEL"] = "fixture-claude-model"
            claude_env["PLANVEYOR_CLAUDE_EFFORT"] = "fixture-claude-effort"
            claude_setup = self._run(
                root,
                claude_env,
                "planveyor_runner_set planner claude >/dev/null && "
                f"planveyor_session_set planner {claude_sid} runner=claude >/dev/null",
            )
            self.assertEqual(claude_setup.returncode, 0, claude_setup.stderr)
            claude_meta_path = root / ".planveyor.init_runs" / "by_sid" / claude_sid / "meta.json"
            claude_meta_path.parent.mkdir(parents=True, exist_ok=True)
            claude_meta_path.write_text(
                json.dumps(
                    {
                        "role": "planner",
                        "runner": "claude",
                        "session_key": "planner",
                        "exit_code": 0,
                        "model_id_state": "configured_explicit",
                        "configured_model_id": "wrong-known-model",
                        "effort_state": "configured_explicit",
                        "configured_effort": "fixture-claude-effort",
                    }
                ),
                encoding="utf-8",
            )
            claude_result = self._run(root, claude_env, "planveyor_role_runner_preflight planner --json")
            self.assertNotEqual(claude_result.returncode, 0, claude_result.stderr)
            claude_payload = json.loads(claude_result.stdout)
            self.assertEqual(claude_payload["init_run_outcome"], "invalid")
            self.assertFalse(claude_payload["execution_ready"])
            self.assertEqual(claude_payload["reason"], "init_run_configured_model_mismatch")





    def test_censor_wrapper_fails_when_current_handoff_receipt_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_censor_receipt_gate_") as tmpdir:
            root, env, log_dir = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
            self._write_runtime_plan(root, status="Ready for Coder")
            planner_sid = "00000000-0000-4000-8000-000000000214"

            result = self._run(
                root,
                env,
                "planveyor_plan_set docs/plans/260101_0000_test_runtime.md >/dev/null && "
                "planveyor_runner_set planner codex >/dev/null && "
                f"planveyor_session_set planner {planner_sid} runner=codex >/dev/null && "
                "planveyor_planner_censor",
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("CENSOR receipt blocked", result.stderr)
            self.assertIn("helper_state=incomplete", result.stderr)
            self.assertIn("reason_code=missing_current_receipt", result.stderr)
            calls = self._codex_calls(log_dir)
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0]["role"], "planner")

    def test_censor_wrapper_accepts_valid_skip_hint_for_current_handoff(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_censor_receipt_gate_skip_") as tmpdir:
            root, env, log_dir = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
            plan_path = self._write_runtime_plan(root, status="Ready for Coder")
            with plan_path.open("a", encoding="utf-8") as fh:
                fh.write(
                    "- [2026-01-01 00:00 MSK] (Planner) Censor hint: skip "
                    "(why=evidence-only delta; previous planner-owned contract unchanged; "
                    "handoff_status=Ready for Coder)\n"
                )
            planner_sid = "00000000-0000-4000-8000-000000000215"

            result = self._run(
                root,
                env,
                "planveyor_plan_set docs/plans/260101_0000_test_runtime.md >/dev/null && "
                "planveyor_runner_set planner codex >/dev/null && "
                f"planveyor_session_set planner {planner_sid} runner=codex >/dev/null && "
                "planveyor_planner_censor",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("CENSOR receipt blocked", result.stderr)
            calls = self._codex_calls(log_dir)
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0]["role"], "planner")

    def test_role_run_probe_isolated_manifest_allowlist_and_exact_recovery(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_role_run_probe_") as tmpdir:
            root, env, _ = self._prepare_repo(tmpdir)
            plan_path = self._write_runtime_plan(root)
            plan_ref = str(plan_path.relative_to(root))
            probe_root = root / ".tmp" / "planveyor_role_run_probes"
            production_receipts = root / ".planveyor.role_runs"
            production_outputs = root / ".tmp" / "planveyor_role_runs"

            rejected = self._run(
                root,
                env,
                "planveyor_role_run_probe run --kind arbitrary "
                f"--target-plan {shlex.quote(plan_ref)} --scenario terminal_recovery --json",
            )
            self.assertEqual(rejected.returncode, 2, rejected.stderr)
            rejected_payload = json.loads(rejected.stdout)
            self.assertEqual(rejected_payload["reason_code"], "allowlist_rejected")
            self.assertFalse(rejected_payload["mutation_performed"])
            self.assertFalse(probe_root.exists())

            cached_plan = root / ".planveyor.planpath"
            cached_plan.write_text("docs/plans/not-the-explicit-plan.md\n", encoding="utf-8")
            payloads: list[dict[str, object]] = []
            expected_readback_fields = {
                "schema_version",
                "ok",
                "operation",
                "probe_id",
                "probe_state",
                "reason_code",
                "mutation_performed",
                "manifest_path",
                "fixture_root",
                "lease_state",
                "target_plan",
            }
            for scenario in ("terminal_recovery", "orphan_output", "malformed_receipt"):
                run = self._run(
                    root,
                    env,
                    "planveyor_role_run_probe run --kind retention "
                    f"--target-plan {shlex.quote(plan_ref)} "
                    f"--scenario {scenario} --json",
                )
                self.assertEqual(run.returncode, 0, run.stderr)
                payload = json.loads(run.stdout)
                payloads.append(payload)
                self.assertEqual(set(payload), expected_readback_fields)
                self.assertEqual(payload["schema_version"], "role_run_probe_readback.v1")
                self.assertTrue(payload["ok"])
                self.assertEqual(payload["operation"], "run")
                self.assertRegex(str(payload["probe_id"]), r"^probe_[0-9a-f]{32}$")
                self.assertEqual(payload["probe_state"], "passed")
                self.assertEqual(payload["reason_code"], "ok")
                self.assertTrue(payload["mutation_performed"])
                self.assertEqual(payload["target_plan"], plan_ref)

                probe_path = probe_root / str(payload["probe_id"])
                manifest_path = root / str(payload["manifest_path"])
                fixture_path = root / str(payload["fixture_root"])
                self.assertEqual(probe_path, manifest_path.parent)
                self.assertEqual(fixture_path.parent, probe_path)
                self.assertEqual(stat.S_IMODE(probe_root.stat().st_mode), 0o700)
                self.assertEqual(stat.S_IMODE(probe_path.stat().st_mode), 0o700)
                self.assertEqual(stat.S_IMODE(manifest_path.stat().st_mode), 0o600)
                self.assertEqual(
                    stat.S_IMODE((probe_path / "lease.lock").stat().st_mode),
                    0o600,
                )
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                self.assertEqual(
                    set(manifest),
                    {
                        "schema_version",
                        "probe_id",
                        "probe_kind",
                        "scenario",
                        "producer",
                        "target_plan",
                        "created_at",
                        "state",
                        "finished_at",
                        "fixture_root",
                        "worker_pgid",
                        "retain_reason",
                    },
                )
                self.assertEqual(manifest["schema_version"], "role_run_probe.v1")
                self.assertEqual(manifest["probe_id"], payload["probe_id"])
                self.assertEqual(manifest["scenario"], scenario)
                self.assertEqual(manifest["producer"], "planveyor_role_run_probe")
                self.assertEqual(manifest["target_plan"], plan_ref)
                self.assertEqual(manifest["fixture_root"], "fixture")
                self.assertEqual(manifest["state"], "passed")
                self.assertIsInstance(manifest["worker_pgid"], int)
                self.assertIsNone(manifest["retain_reason"])
                self.assertEqual(list(probe_path.glob(".probe.json.*")), [])

            self.assertNotEqual(payloads[0]["probe_id"], payloads[1]["probe_id"])
            self.assertFalse(production_receipts.exists())
            self.assertFalse(production_outputs.exists())

            for payload in payloads:
                probe_id = str(payload["probe_id"])
                inspected = self._run(
                    root,
                    env,
                    f"planveyor_role_run_probe inspect --probe-id {probe_id} --json",
                )
                self.assertEqual(inspected.returncode, 0, inspected.stderr)
                inspected_payload = json.loads(inspected.stdout)
                self.assertEqual(set(inspected_payload), expected_readback_fields)
                self.assertEqual(inspected_payload["probe_state"], "passed")
                self.assertEqual(inspected_payload["lease_state"], "free")
                self.assertFalse(inspected_payload["mutation_performed"])

                recovered = self._run(
                    root,
                    env,
                    f"planveyor_role_run_probe recover --probe-id {probe_id} --json",
                )
                self.assertEqual(recovered.returncode, 0, recovered.stderr)
                recovered_payload = json.loads(recovered.stdout)
                self.assertEqual(set(recovered_payload), expected_readback_fields)
                self.assertEqual(recovered_payload["probe_state"], "absent")
                self.assertEqual(recovered_payload["reason_code"], "ok")
                self.assertTrue(recovered_payload["mutation_performed"])

                repeated = self._run(
                    root,
                    env,
                    f"planveyor_role_run_probe recover --probe-id {probe_id} --json",
                )
                self.assertEqual(repeated.returncode, 0, repeated.stderr)
                repeated_payload = json.loads(repeated.stdout)
                self.assertEqual(set(repeated_payload), expected_readback_fields)
                self.assertEqual(repeated_payload["reason_code"], "already_absent")
                self.assertFalse(repeated_payload["mutation_performed"])

    def test_role_run_probe_malformed_identity_and_symlink_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_role_run_probe_invalid_") as tmpdir:
            root, env, _ = self._prepare_repo(tmpdir)
            plan_ref = str(self._write_runtime_plan(root).relative_to(root))
            created = self._run(
                root,
                env,
                "planveyor_role_run_probe run --kind retention "
                f"--target-plan {shlex.quote(plan_ref)} --scenario terminal_recovery --json",
            )
            self.assertEqual(created.returncode, 0, created.stderr)
            created_payload = json.loads(created.stdout)
            probe_id = str(created_payload["probe_id"])
            probe_path = root / ".tmp" / "planveyor_role_run_probes" / probe_id
            manifest_path = probe_path / "probe.json"
            original_manifest = manifest_path.read_bytes()

            manifest = json.loads(original_manifest)
            manifest["unexpected"] = "forbidden"
            manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
            malformed = self._run(
                root,
                env,
                f"planveyor_role_run_probe inspect --probe-id {probe_id} --json",
            )
            self.assertNotEqual(malformed.returncode, 0)
            malformed_payload = json.loads(malformed.stdout)
            self.assertEqual(malformed_payload["reason_code"], "manifest_invalid")
            self.assertFalse(malformed_payload["mutation_performed"])
            self.assertTrue(probe_path.is_dir())
            manifest_path.write_bytes(original_manifest)

            terminal_finished_at = json.loads(original_manifest)["finished_at"]
            for state, retain_reason, operation in (
                ("running", None, "mark-interrupted"),
                ("passed", None, "recover"),
                ("interrupted", "interrupted", "recover"),
            ):
                null_worker_manifest = json.loads(original_manifest)
                null_worker_manifest["state"] = state
                null_worker_manifest["finished_at"] = (
                    None if state == "running" else terminal_finished_at
                )
                null_worker_manifest["retain_reason"] = retain_reason
                null_worker_manifest["worker_pgid"] = None
                manifest_path.write_text(
                    json.dumps(null_worker_manifest) + "\n",
                    encoding="utf-8",
                )

                invalid_inspect = self._run(
                    root,
                    env,
                    f"planveyor_role_run_probe inspect --probe-id {probe_id} --json",
                )
                self.assertNotEqual(invalid_inspect.returncode, 0)
                invalid_inspect_payload = json.loads(invalid_inspect.stdout)
                self.assertEqual(
                    invalid_inspect_payload["reason_code"],
                    "manifest_invalid",
                )
                self.assertFalse(invalid_inspect_payload["mutation_performed"])

                invalid_mutation = self._run(
                    root,
                    env,
                    f"planveyor_role_run_probe {operation} --probe-id {probe_id} --json",
                )
                self.assertNotEqual(invalid_mutation.returncode, 0)
                invalid_mutation_payload = json.loads(invalid_mutation.stdout)
                self.assertEqual(
                    invalid_mutation_payload["reason_code"],
                    "manifest_invalid",
                )
                self.assertFalse(invalid_mutation_payload["mutation_performed"])
                self.assertTrue(probe_path.is_dir())
            manifest_path.write_bytes(original_manifest)

            fixture_path = probe_path / "fixture"
            original_fixture = probe_path / "fixture.original"
            fixture_path.rename(original_fixture)
            outside = root / "outside-probe-fixture"
            outside.mkdir()
            marker = outside / "owner.marker"
            marker.write_text("preserve\n", encoding="utf-8")
            fixture_path.symlink_to(outside, target_is_directory=True)
            unsafe = self._run(
                root,
                env,
                f"planveyor_role_run_probe recover --probe-id {probe_id} --json",
            )
            self.assertNotEqual(unsafe.returncode, 0)
            unsafe_payload = json.loads(unsafe.stdout)
            self.assertEqual(unsafe_payload["reason_code"], "manifest_invalid")
            self.assertFalse(unsafe_payload["mutation_performed"])
            self.assertEqual(marker.read_text(encoding="utf-8"), "preserve\n")
            fixture_path.unlink()
            original_fixture.rename(fixture_path)

            for invalid_id in ("../escape", "probe_not_hex"):
                rejected = self._run(
                    root,
                    env,
                    "planveyor_role_run_probe inspect "
                    f"--probe-id {shlex.quote(invalid_id)} --json",
                )
                self.assertNotEqual(rejected.returncode, 0)
                rejected_payload = json.loads(rejected.stdout)
                self.assertEqual(rejected_payload["reason_code"], "unsafe_probe_path")
                self.assertFalse(rejected_payload["mutation_performed"])

            recovered = self._run(
                root,
                env,
                f"planveyor_role_run_probe recover --probe-id {probe_id} --json",
            )
            self.assertEqual(recovered.returncode, 0, recovered.stderr)

    def test_role_run_probe_rejects_symlink_namespace_without_touching_target(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_role_run_probe_root_link_") as tmpdir:
            root, env, _ = self._prepare_repo(tmpdir)
            plan_ref = str(self._write_runtime_plan(root).relative_to(root))
            tmp_root = root / ".tmp"
            tmp_root.mkdir(mode=0o700)
            outside = root / "outside-probe-root"
            outside.mkdir(mode=0o755)
            outside.chmod(0o755)
            probe_root = tmp_root / "planveyor_role_run_probes"
            probe_root.symlink_to(outside, target_is_directory=True)

            rejected = self._run(
                root,
                env,
                "planveyor_role_run_probe run --kind retention "
                f"--target-plan {shlex.quote(plan_ref)} --scenario terminal_recovery --json",
            )
            self.assertNotEqual(rejected.returncode, 0)
            payload = json.loads(rejected.stdout)
            self.assertEqual(payload["reason_code"], "unsafe_probe_path")
            self.assertFalse(payload["mutation_performed"])
            self.assertEqual(stat.S_IMODE(outside.stat().st_mode), 0o755)
            self.assertEqual(list(outside.iterdir()), [])

    def test_role_run_probe_lease_survives_supervisor_crash_and_gates_recovery(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_role_run_probe_crash_") as tmpdir:
            root, env, _ = self._prepare_repo(
                tmpdir,
                runtime_mode="legacy_complete",
            )
            runtime_manifest = self._assert_legacy_complete_runtime_identity(root, env)
            plan_ref = str(self._write_runtime_plan(root).relative_to(root))
            run_env = dict(env)
            # Pause the real active worker after its running manifest is
            # committed.  This keeps its inherited lease held through both
            # negative mutator checks without changing the fixture worker.
            run_env["PLANVEYOR_ROLE_RUN_PROBE_TEST_HOLD_SECONDS"] = "2.0"
            command = (
                f"source {shlex.quote(str(root / 'scripts' / 'planveyor.zsh'))}; "
                "planveyor_role_run_probe run --kind retention "
                f"--target-plan {shlex.quote(plan_ref)} --scenario active_lease --json"
            )
            supervisor = subprocess.Popen(
                ["/bin/zsh", "-fc", command],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=run_env,
                start_new_session=True,
            )
            probe_root = root / ".tmp" / "planveyor_role_run_probes"
            manifest_path: Path | None = None
            worker_pgid: int | None = None
            try:
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    manifests = list(probe_root.glob("probe_*/probe.json"))
                    if manifests:
                        candidate = manifests[0]
                        try:
                            if json.loads(candidate.read_text(encoding="utf-8"))["state"] == "running":
                                manifest_path = candidate
                                break
                        except (FileNotFoundError, json.JSONDecodeError):
                            pass
                    time.sleep(0.02)
                self.assertIsNotNone(manifest_path)
                assert manifest_path is not None
                running_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                worker_pgid_raw = running_manifest["worker_pgid"]
                self.assertIsInstance(worker_pgid_raw, int)
                self.assertNotIsInstance(worker_pgid_raw, bool)
                assert isinstance(worker_pgid_raw, int)
                self.assertGreater(worker_pgid_raw, 1)
                self.assertEqual(os.getpgid(worker_pgid_raw), worker_pgid_raw)
                self.assertEqual(os.getpgid(supervisor.pid), supervisor.pid)
                self.assertNotEqual(worker_pgid_raw, os.getpgrp())
                self.assertNotEqual(worker_pgid_raw, os.getpgid(supervisor.pid))
                self.assertNotEqual(os.getpgid(supervisor.pid), os.getpgrp())
                worker_pgid = worker_pgid_raw
                probe_id = manifest_path.parent.name
                lease_path = manifest_path.parent / "lease.lock"
                lease_info = lease_path.lstat()
                self.assertTrue(stat.S_ISREG(lease_info.st_mode), lease_path)
                self.assertEqual(stat.S_IMODE(lease_info.st_mode), 0o600)
                os.killpg(worker_pgid, signal.SIGSTOP)

                os.killpg(supervisor.pid, signal.SIGKILL)
                supervisor.communicate(timeout=2)

                live = self._run(
                    root,
                    env,
                    f"planveyor_role_run_probe inspect --probe-id {probe_id} --json",
                )
                self.assertEqual(live.returncode, 0, live.stderr)
                live_payload = json.loads(live.stdout)
                self.assertEqual(live_payload["probe_state"], "running")
                self.assertEqual(live_payload["lease_state"], "held_external")

                for operation in ("mark-interrupted", "recover"):
                    blocked = self._run(
                        root,
                        env,
                        f"planveyor_role_run_probe {operation} --probe-id {probe_id} --json",
                    )
                    self.assertNotEqual(blocked.returncode, 0)
                    blocked_payload = json.loads(blocked.stdout)
                    self.assertEqual(blocked_payload["reason_code"], "lease_held")
                    self.assertFalse(blocked_payload["mutation_performed"])

                os.killpg(worker_pgid, signal.SIGCONT)
                deadline = time.monotonic() + 5
                lease_free = False
                worker_exited = False
                while time.monotonic() < deadline:
                    try:
                        os.getpgid(worker_pgid)
                    except ProcessLookupError:
                        worker_exited = True
                        break
                    fd = os.open(
                        lease_path,
                        os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
                    )
                    try:
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        pass
                    else:
                        lease_free = True
                        fcntl.flock(fd, fcntl.LOCK_UN)
                        break
                    finally:
                        os.close(fd)
                    time.sleep(0.02)
                self.assertTrue(
                    lease_free or worker_exited,
                    "active worker neither exited nor released its lease after SIGCONT",
                )
                inspect = self._run(
                    root,
                    env,
                    f"planveyor_role_run_probe inspect --probe-id {probe_id} --json",
                )
                self.assertEqual(inspect.returncode, 0, inspect.stderr)
                inspect_payload = json.loads(inspect.stdout)
                self.assertEqual(inspect_payload["lease_state"], "free")
                self.assertEqual(inspect_payload["probe_state"], "running")

                interrupted = self._run(
                    root,
                    env,
                    f"planveyor_role_run_probe mark-interrupted --probe-id {probe_id} --json",
                )
                self.assertEqual(interrupted.returncode, 0, interrupted.stderr)
                interrupted_payload = json.loads(interrupted.stdout)
                self.assertEqual(interrupted_payload["probe_state"], "interrupted")
                self.assertEqual(interrupted_payload["lease_state"], "held_by_helper")
                self.assertTrue(interrupted_payload["mutation_performed"])

                recovered = self._run(
                    root,
                    env,
                    f"planveyor_role_run_probe recover --probe-id {probe_id} --json",
                )
                self.assertEqual(recovered.returncode, 0, recovered.stderr)
                self._assert_legacy_complete_runtime_identity(
                    root,
                    env,
                    expected_manifest=runtime_manifest,
                )
            finally:
                if supervisor.poll() is None:
                    try:
                        os.killpg(supervisor.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    supervisor.communicate(timeout=2)
                if worker_pgid is not None:
                    try:
                        worker_group_live = os.getpgid(worker_pgid) == worker_pgid
                    except ProcessLookupError:
                        worker_group_live = False
                    if worker_group_live:
                        try:
                            os.killpg(worker_pgid, signal.SIGCONT)
                            os.killpg(worker_pgid, signal.SIGTERM)
                        except ProcessLookupError:
                            pass
                        else:
                            cleanup_deadline = time.monotonic() + 2
                            while time.monotonic() < cleanup_deadline:
                                try:
                                    os.getpgid(worker_pgid)
                                except ProcessLookupError:
                                    break
                                time.sleep(0.02)
                            else:
                                try:
                                    if os.getpgid(worker_pgid) == worker_pgid:
                                        os.killpg(worker_pgid, signal.SIGKILL)
                                except ProcessLookupError:
                                    pass

    def test_role_run_probe_prepared_hard_kill_has_exact_terminalization_and_recovery(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_role_run_probe_prepared_kill_") as tmpdir:
            root, env, _ = self._prepare_repo(tmpdir)
            plan_ref = str(self._write_runtime_plan(root).relative_to(root))
            run_env = dict(env)
            run_env["PLANVEYOR_ROLE_RUN_PROBE_TEST_KILL_AFTER_PREPARED"] = "1"
            child_observation = Path(run_env["TMPDIR"]) / "prepared-child-environment"
            command = (
                f'print -r -- "$TMPDIR|$TMPPREFIX" > {shlex.quote(str(child_observation))}; '
                f"source {shlex.quote(str(root / 'scripts' / 'planveyor.zsh'))}; "
                "planveyor_role_run_probe run --kind retention "
                f"--target-plan {shlex.quote(plan_ref)} "
                "--scenario terminal_recovery --json"
            )
            supervisor = subprocess.Popen(
                ["/bin/zsh", "-fc", command],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=run_env,
                start_new_session=True,
            )
            stdout, stderr = supervisor.communicate(timeout=5)
            self.assertNotEqual(supervisor.returncode, 0)
            self.assertEqual(stdout, "")
            self.assertEqual(stderr, "")
            self.assertEqual(
                child_observation.read_text(encoding="utf-8"),
                f"{run_env['TMPDIR']}|{run_env['TMPPREFIX']}\n",
            )

            probe_root = root / ".tmp" / "planveyor_role_run_probes"
            probe_paths = sorted(
                path
                for path in probe_root.iterdir()
                if re.fullmatch(r"probe_[0-9a-f]{32}", path.name)
            )
            self.assertEqual(len(probe_paths), 1)
            probe_path = probe_paths[0]
            probe_id = probe_path.name
            manifest_path = probe_path / "probe.json"
            fixture_path = probe_path / "fixture"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["state"], "prepared")
            self.assertIsNone(manifest["worker_pgid"])
            self.assertTrue(fixture_path.is_dir())

            inspected = self._run(
                root,
                env,
                f"planveyor_role_run_probe inspect --probe-id {probe_id} --json",
            )
            self.assertEqual(inspected.returncode, 0, inspected.stderr)
            inspected_payload = json.loads(inspected.stdout)
            self.assertEqual(inspected_payload["probe_state"], "prepared")
            self.assertEqual(inspected_payload["lease_state"], "free")

            blocked_recover = self._run(
                root,
                env,
                f"planveyor_role_run_probe recover --probe-id {probe_id} --json",
            )
            self.assertNotEqual(blocked_recover.returncode, 0)
            blocked_payload = json.loads(blocked_recover.stdout)
            self.assertEqual(blocked_payload["reason_code"], "transition_invalid")
            self.assertFalse(blocked_payload["mutation_performed"])

            failed = self._run(
                root,
                env,
                f"planveyor_role_run_probe mark-interrupted --probe-id {probe_id} --json",
            )
            self.assertEqual(failed.returncode, 0, failed.stderr)
            failed_payload = json.loads(failed.stdout)
            self.assertEqual(failed_payload["probe_state"], "failed")
            self.assertEqual(failed_payload["reason_code"], "ok")
            self.assertEqual(failed_payload["lease_state"], "held_by_helper")
            self.assertTrue(failed_payload["mutation_performed"])
            failed_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(failed_manifest["state"], "failed")
            self.assertEqual(failed_manifest["retain_reason"], "failed")
            self.assertIsNone(failed_manifest["worker_pgid"])

            recovered = self._run(
                root,
                env,
                f"planveyor_role_run_probe recover --probe-id {probe_id} --json",
            )
            self.assertEqual(recovered.returncode, 0, recovered.stderr)
            recovered_payload = json.loads(recovered.stdout)
            self.assertEqual(recovered_payload["probe_state"], "absent")
            self.assertTrue(recovered_payload["mutation_performed"])

    def test_role_run_probe_clean_signal_stops_worker_before_interrupted_transition(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_role_run_probe_signal_") as tmpdir:
            root, env, _ = self._prepare_repo(tmpdir)
            plan_ref = str(self._write_runtime_plan(root).relative_to(root))
            signal_env = dict(env)
            signal_env["PLANVEYOR_ROLE_RUN_PROBE_TEST_HOLD_SECONDS"] = "5"
            signal_env["PLANVEYOR_ROLE_RUN_PROBE_TEST_SIGNAL_SUPERVISOR"] = "1"
            run = self._run(
                root,
                signal_env,
                "planveyor_role_run_probe run --kind retention "
                f"--target-plan {shlex.quote(plan_ref)} --scenario active_lease --json",
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            payload = json.loads(run.stdout)
            self.assertEqual(payload["probe_state"], "interrupted")
            self.assertEqual(payload["reason_code"], "ok")
            probe_id = str(payload["probe_id"])
            manifest_path = root / str(payload["manifest_path"])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["state"], "interrupted")
            self.assertEqual(manifest["retain_reason"], "interrupted")
            worker_pgid = int(manifest["worker_pgid"])
            with self.assertRaises(ProcessLookupError):
                os.killpg(worker_pgid, 0)

            inspected = self._run(
                root,
                env,
                f"planveyor_role_run_probe inspect --probe-id {probe_id} --json",
            )
            self.assertEqual(inspected.returncode, 0, inspected.stderr)
            self.assertEqual(json.loads(inspected.stdout)["lease_state"], "free")
            recovered = self._run(
                root,
                env,
                f"planveyor_role_run_probe recover --probe-id {probe_id} --json",
            )
            self.assertEqual(recovered.returncode, 0, recovered.stderr)

    def test_role_run_probe_setup_failure_is_terminal_and_recoverable(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_role_run_probe_setup_failure_") as tmpdir:
            root, env, _ = self._prepare_repo(tmpdir)
            plan_ref = str(self._write_runtime_plan(root).relative_to(root))
            failure_env = dict(env)
            failure_env["PLANVEYOR_ROLE_RUN_PROBE_TEST_HOLD_SECONDS"] = "121"
            run = self._run(
                root,
                failure_env,
                "planveyor_role_run_probe run --kind retention "
                f"--target-plan {shlex.quote(plan_ref)} --scenario active_lease --json",
            )
            self.assertEqual(run.returncode, 126, run.stderr)
            payload = json.loads(run.stdout)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["reason_code"], "internal_error")
            self.assertEqual(payload["probe_state"], "failed")
            self.assertTrue(payload["mutation_performed"])
            probe_id = str(payload["probe_id"])

            inspected = self._run(
                root,
                env,
                f"planveyor_role_run_probe inspect --probe-id {probe_id} --json",
            )
            self.assertEqual(inspected.returncode, 0, inspected.stderr)
            inspected_payload = json.loads(inspected.stdout)
            self.assertEqual(inspected_payload["probe_state"], "failed")
            self.assertEqual(inspected_payload["lease_state"], "free")

            recovered = self._run(
                root,
                env,
                f"planveyor_role_run_probe recover --probe-id {probe_id} --json",
            )
            self.assertEqual(recovered.returncode, 0, recovered.stderr)
            self.assertEqual(json.loads(recovered.stdout)["probe_state"], "absent")

    def test_role_run_probe_concurrent_starts_receive_unique_owned_ids(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_role_run_probe_parallel_") as tmpdir:
            root, env, _ = self._prepare_repo(tmpdir)
            plan_ref = str(self._write_runtime_plan(root).relative_to(root))
            command = (
                f"source {shlex.quote(str(root / 'scripts' / 'planveyor.zsh'))}; "
                "planveyor_role_run_probe run --kind retention "
                f"--target-plan {shlex.quote(plan_ref)} --scenario terminal_recovery --json"
            )
            workers = [
                subprocess.Popen(
                    ["/bin/zsh", "-fc", command],
                    cwd=root,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env,
                )
                for _ in range(3)
            ]
            payloads: list[dict[str, object]] = []
            for worker in workers:
                stdout, stderr = worker.communicate(timeout=5)
                self.assertEqual(worker.returncode, 0, stderr)
                payloads.append(json.loads(stdout))
            probe_ids = [str(payload["probe_id"]) for payload in payloads]
            self.assertEqual(len(set(probe_ids)), len(probe_ids))
            for probe_id in probe_ids:
                recovered = self._run(
                    root,
                    env,
                    f"planveyor_role_run_probe recover --probe-id {probe_id} --json",
                )
                self.assertEqual(recovered.returncode, 0, recovered.stderr)

    def test_role_run_probe_recovery_rejects_path_replacement_before_mutation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_role_run_probe_replace_") as tmpdir:
            root, env, _ = self._prepare_repo(tmpdir)
            plan_ref = str(self._write_runtime_plan(root).relative_to(root))
            created = self._run(
                root,
                env,
                "planveyor_role_run_probe run --kind retention "
                f"--target-plan {shlex.quote(plan_ref)} --scenario terminal_recovery --json",
            )
            self.assertEqual(created.returncode, 0, created.stderr)
            probe_id = str(json.loads(created.stdout)["probe_id"])
            probe_path = root / ".tmp" / "planveyor_role_run_probes" / probe_id
            lease_path = probe_path / "lease.lock"
            delayed_env = dict(env)
            delayed_env["PLANVEYOR_ROLE_RUN_PROBE_TEST_PRE_MUTATION_DELAY"] = "1.0"
            command = (
                f"source {shlex.quote(str(root / 'scripts' / 'planveyor.zsh'))}; "
                f"planveyor_role_run_probe recover --probe-id {probe_id} --json"
            )
            recovery = subprocess.Popen(
                ["/bin/zsh", "-fc", command],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=delayed_env,
            )
            deadline = time.monotonic() + 3
            while True:
                fd = os.open(lease_path, os.O_RDWR)
                try:
                    try:
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        break
                    else:
                        fcntl.flock(fd, fcntl.LOCK_UN)
                finally:
                    os.close(fd)
                self.assertLess(time.monotonic(), deadline)
                time.sleep(0.01)

            original_path = probe_path.with_name(f"{probe_id}.original")
            probe_path.rename(original_path)
            probe_path.mkdir(mode=0o700)
            marker = probe_path / "replacement.marker"
            marker.write_text("must survive\n", encoding="utf-8")
            stdout, stderr = recovery.communicate(timeout=4)
            self.assertNotEqual(recovery.returncode, 0, stderr)
            replacement_payload = json.loads(stdout)
            self.assertEqual(replacement_payload["reason_code"], "unsafe_probe_path")
            self.assertFalse(replacement_payload["mutation_performed"])
            self.assertEqual(marker.read_text(encoding="utf-8"), "must survive\n")
            self.assertTrue(original_path.is_dir())

            shutil.rmtree(probe_path)
            original_path.rename(probe_path)
            cleaned = self._run(
                root,
                env,
                f"planveyor_role_run_probe recover --probe-id {probe_id} --json",
            )
            self.assertEqual(cleaned.returncode, 0, cleaned.stderr)

    def test_role_run_writes_fresh_success_receipt_and_compat_readback(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_role_run_success_") as tmpdir:
            root, env, log_dir = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
            self._write_runtime_plan(root, status="In progress")
            planner_sid = "00000000-0000-4000-8000-000000000304"

            setup = self._run(
                root,
                env,
                "planveyor_plan_set docs/plans/260101_0000_test_runtime.md >/dev/null && "
                "planveyor_runner_set planner codex >/dev/null && "
                f"planveyor_session_set planner {planner_sid} runner=codex >/dev/null",
                timeout_seconds=60,
            )
            self.assertEqual(setup.returncode, 0, setup.stderr)
            result = self._run(
                root,
                env,
                "planveyor_role_run planner --json",
                timeout_seconds=60,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["schema_version"], "role_execution_receipt.v1")
            self.assertEqual(payload["role"], "planner")
            self.assertEqual(payload["session_key"], "planner")
            self.assertEqual(payload["wrapper"], "planveyor_planner")
            self.assertEqual(payload["runner_id"], "codex")
            self.assertEqual(payload["runner_alias"], "codex")
            self.assertEqual(payload["profile"], "N/A (why=profile not readable)")
            self.assertIn("codex model comes from profile/session stats", payload["configured_model_id"])
            self.assertEqual(payload["observable_model_id"], "N/A (why=provider model metadata not exposed)")
            self.assertEqual(payload["model_id_state"], "unknown")
            self.assertEqual(payload["sid"], planner_sid)
            self.assertEqual(payload["sid_before"], planner_sid)
            self.assertEqual(payload["sid_after"], planner_sid)
            self.assertEqual(payload["session_action_requested"], "resume")
            self.assertEqual(payload["session_pointer_relation"], "same")
            self.assertEqual(payload["process_start_outcome"], "started")
            self.assertFalse(payload["session_reset_performed"])
            self.assertEqual(payload["cli_process_mode"], "one_shot")
            self.assertFalse(payload["process_persistent"])
            self.assertEqual(payload["provider_error_class"], "not_applicable")
            self.assertEqual(payload["provider_http_status"], "not_applicable")
            self.assertEqual(payload["provider_error_code"], "not_applicable")
            self.assertEqual(payload["provider_retryability"], "not_applicable")
            self.assertEqual(payload["target_plan"], "docs/plans/260101_0000_test_runtime.md")
            self.assertEqual(payload["exit_code"], 0)
            self.assertEqual(payload["timeout_seconds"], 3600)
            self.assertIsInstance(payload["duration_seconds"], int)
            self.assertEqual(payload["elapsed_seconds"], payload["duration_seconds"])
            self.assertEqual(payload["state"], "success")
            self.assertTrue(payload["success"])
            self.assertFalse(payload["timed_out"])
            self.assertFalse(payload["terminated_by_timeout"])
            self.assertFalse(payload["child_session"])
            self.assertNotIn("business_work_executed", payload)
            self.assertNotIn("business_work_state", payload)
            self.assertEqual(payload["retention_prune_state"], "completed")
            self.assertEqual(payload["retention_prune_reason"], "ok")
            self.assertEqual(
                payload["retention_prune_paths"],
                sorted(set(payload["retention_prune_paths"])),
            )
            self.assertIsInstance(payload["retention_prune_mutation_performed"], bool)
            self.assertIn("**Status:** In progress", payload["pre_status"])
            self.assertIn("**Status:** In progress", payload["post_status"])
            self.assertTrue(Path(payload["receipt_path"]).exists())
            self.assertTrue(Path(payload["latest_receipt_path"]).exists())
            self.assertTrue(str(payload["receipt_path"]).endswith(f"{payload['run_id']}.json"))
            self.assertIn(".planveyor.role_runs", str(payload["receipt_path"]))

            latest = Path(payload["latest_receipt_path"]).read_text(encoding="utf-8")
            self.assertIn("schema_version=role_execution_receipt.v1", latest)
            self.assertIn(f"run_id={payload['run_id']}", latest)
            self.assertIn("runner_alias=codex", latest)
            self.assertIn("profile=N/A (why=profile not readable)", latest)
            self.assertIn("model_id_state=unknown", latest)
            self.assertIn("timeout_seconds=3600", latest)
            self.assertIn(f"duration_seconds={payload['duration_seconds']}", latest)
            self.assertIn(f"elapsed_seconds={payload['elapsed_seconds']}", latest)
            self.assertIn("timed_out=false", latest)
            self.assertIn("terminated_by_timeout=false", latest)
            self.assertIn("session_action_requested=resume", latest)
            self.assertIn("session_pointer_relation=same", latest)
            self.assertIn("process_start_outcome=started", latest)
            self.assertIn("session_reset_performed=false", latest)
            self.assertIn("cli_process_mode=one_shot", latest)
            self.assertIn("process_persistent=false", latest)
            self.assertIn("provider_error_class=not_applicable", latest)
            self.assertIn("provider_http_status=not_applicable", latest)
            self.assertIn("provider_error_code=not_applicable", latest)
            self.assertIn("provider_retryability=not_applicable", latest)
            self.assertNotIn("business_work_executed=", latest)
            self.assertNotIn("business_work_state=", latest)
            self.assertNotIn("event_type=run_receipt.manager_custom_pipeline", latest)

            receipt_path = Path(payload["receipt_path"])
            output_dir = Path(payload["stdout_path"]).parent
            private_dirs = [
                root / ".planveyor.role_runs",
                root / ".tmp" / "planveyor_role_runs",
                root / ".tmp" / "planveyor_role_runs" / ".locks",
                output_dir,
            ]
            private_files = [
                receipt_path,
                Path(payload["latest_receipt_path"]),
                output_dir / "stdout.log",
                output_dir / "stderr.log",
                output_dir / "wrapper.zsh",
                output_dir / "preflight.json",
                output_dir / "preflight.stderr",
                output_dir / "lock.ready.json",
                output_dir / "lock.release",
                output_dir / "transaction.done",
                root / ".tmp" / "planveyor_role_runs" / ".locks" / "planner.lock",
            ]
            for path in private_dirs:
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700, path)
            for path in private_files:
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600, path)
            persisted = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertNotIn("readback_state", persisted)
            self.assertNotIn("readback_reason", persisted)
            self.assertNotIn("retention_prune_state", persisted)
            self.assertNotIn("retention_prune_reason", persisted)
            self.assertNotIn("retention_prune_paths", persisted)
            self.assertNotIn("retention_prune_mutation_performed", persisted)

            check = self._run(
                root,
                env,
                "planveyor_role_run_receipt_check "
                f"{shlex.quote(str(payload['receipt_path']))} "
                f"--run-id {payload['run_id']} --session-key planner "
                "--target-plan docs/plans/260101_0000_test_runtime.md --json",
            )
            self.assertEqual(check.returncode, 0, check.stderr)
            check_payload = json.loads(check.stdout)
            self.assertEqual(check_payload["readback_state"], "ok")
            self.assertEqual(check_payload["lifecycle_provider_contract_state"], "current")

            calls = self._codex_calls(log_dir)
            self.assertEqual([call["role"] for call in calls], ["planner"])

            claude_runner_setup = self._run(
                root,
                env,
                "planveyor_plan_set docs/plans/260101_0000_test_runtime.md >/dev/null && "
                "planveyor_runner_set planner claude >/dev/null && "
                "planveyor_planner_init >/dev/null",
                timeout_seconds=60,
            )
            self.assertEqual(
                claude_runner_setup.returncode,
                0,
                claude_runner_setup.stderr,
            )
            claude_runner_result = self._run(
                root,
                env,
                "planveyor_role_run planner --json",
                timeout_seconds=60,
            )
            self.assertEqual(claude_runner_result.returncode, 0, claude_runner_result.stderr)
            claude_runner_payload = json.loads(claude_runner_result.stdout)
            self.assertEqual(claude_runner_payload["state"], "success")
            self.assertEqual(claude_runner_payload["runner_id"], "claude")
            self.assertEqual(claude_runner_payload["profile"], "direct_child")
            self.assertEqual(claude_runner_payload["model"], "N/A (why=consumer default)")
            self.assertEqual(
                claude_runner_payload["configured_model_id"],
                "N/A (why=consumer default)",
            )
            self.assertEqual(claude_runner_payload["model_id_state"], "consumer_default")
            self.assertEqual(claude_runner_payload["readback_state"], "ok")
            claude_calls = self._claude_calls(log_dir)
            self.assertEqual(len(claude_calls), 2)
            self.assertEqual(claude_calls[-1]["command"], "claude")
            self.assertEqual(claude_calls[-1]["role"], "planner")
            self.assertIn("--session-id", claude_calls[0]["argv"])
            self.assertIn("--resume", claude_calls[-1]["argv"])

    def test_role_run_ignores_ambient_preflight_marker_and_uses_fresh_proof(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_role_run_preflight_marker_") as tmpdir:
            root, env, log_dir = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
            self._write_runtime_plan(root, status="In progress")
            planner_sid = "00000000-0000-4000-8000-000000000405"

            result = self._run(
                root,
                env,
                "planveyor_plan_set docs/plans/260101_0000_test_runtime.md >/dev/null && "
                "planveyor_runner_set planner codex >/dev/null && "
                f"planveyor_session_set planner {planner_sid} runner=codex >/dev/null && "
                "functions -c planveyor_role_runner_preflight _planveyor_test_preflight_original && "
                "planveyor_role_runner_preflight() { "
                "mkdir -p .tmp; print -r -- current-proof >> .tmp/preflight.calls; "
                "_planveyor_test_preflight_original \"$@\"; "
                "} && "
                "PLANVEYOR_ROLE_RUN_PREFLIGHT_DONE=true planveyor_role_run planner --json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["state"], "success")
            self.assertEqual(payload["runner_id"], "codex")
            proof = json.loads(
                (Path(payload["stdout_path"]).parent / "preflight.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertTrue(proof["execution_ready"])
            self.assertEqual(proof["role"], "planner")
            self.assertEqual(proof["runner"], "codex")
            self.assertEqual(proof["session_key"], "planner")
            self.assertEqual(proof["sid"], planner_sid)
            self.assertEqual(proof["selection_schema_version"], "runner_selection_resolution.v1")
            self.assertIn(proof["carrier_state"], {"absent_default", "present_valid"})
            self.assertRegex(proof["init_attempt_id"], r"^[0-9a-f-]{36}$")
            self.assertRegex(proof["selection_digest"], r"^[0-9a-f]{64}$")
            self.assertEqual(
                (root / ".tmp" / "preflight.calls").read_text(encoding="utf-8").splitlines(),
                ["current-proof"],
            )
            self.assertEqual([call["role"] for call in self._codex_calls(log_dir)], ["planner"])

    def test_role_run_rejects_bad_or_changed_preflight_identity_before_child(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_role_run_preflight_identity_") as tmpdir:
            root, env, log_dir = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
            self._write_runtime_plan(root, status="In progress")
            plan_rel = "docs/plans/260101_0000_test_runtime.md"
            planner_sid = "00000000-0000-4000-8000-000000000406"
            setup = (
                f"planveyor_plan_set {plan_rel} >/dev/null && "
                "planveyor_runner_set planner codex >/dev/null && "
                f"planveyor_session_set planner {planner_sid} runner=codex >/dev/null && "
            )

            changed = self._run(
                root,
                env,
                setup
                + "functions -c planveyor_role_runner_preflight _planveyor_test_preflight_original && "
                + "planveyor_role_runner_preflight() { "
                + "local proof rc; proof=\"$(_planveyor_test_preflight_original \"$@\")\"; rc=$?; "
                + "print -r -- \"$proof\"; planveyor_runner_set planner claude >/dev/null; return $rc; "
                + "} && planveyor_role_run planner --json",
            )
            self.assertEqual(changed.returncode, 125, changed.stderr)
            changed_payload = json.loads(changed.stdout)
            self.assertEqual(changed_payload["state"], "precondition_failed")
            self.assertEqual(changed_payload["non_green_reason"], "runner_changed_since_preflight")
            self.assertEqual(changed_payload["process_start_outcome"], "not_started")
            self.assertEqual(self._codex_calls(log_dir), [])
            self.assertEqual(self._claude_calls(log_dir), [])

            captured = self._run(
                root,
                env,
                setup + "planveyor_role_runner_preflight planner --json",
            )
            self.assertEqual(captured.returncode, 0, captured.stderr)
            valid_proof = json.loads(captured.stdout)
            bad_proofs: dict[str, tuple[str, str]] = {
                "malformed": ('{"execution_ready":true}', "precondition_failed"),
                "duplicate": (
                    '{"execution_ready":true,"execution_ready":true}',
                    "precondition_failed",
                ),
                "wrong_role": (
                    json.dumps({**valid_proof, "role": "coder"}, separators=(",", ":")),
                    "precondition_failed",
                ),
                "wrong_runner": (
                    json.dumps(
                        {**valid_proof, "runner": "claude", "runner_id": "claude"},
                        separators=(",", ":"),
                    ),
                    "runner_changed_since_preflight",
                ),
                "wrong_session": (
                    json.dumps({**valid_proof, "session_key": "coder"}, separators=(",", ":")),
                    "precondition_failed",
                ),
                "wrong_sid": (
                    json.dumps(
                        {
                            **valid_proof,
                            "sid": "00000000-0000-4000-8000-000000000499",
                        },
                        separators=(",", ":"),
                    ),
                    "precondition_failed",
                ),
                "wrong_digest": (
                    json.dumps(
                        {**valid_proof, "selection_digest": "0" * 64},
                        separators=(",", ":"),
                    ),
                    "runner_changed_since_preflight",
                ),
                "explicit_red": (
                    json.dumps(
                        {
                            **valid_proof,
                            "execution_ready": False,
                            "reason": "runner_not_readable",
                        },
                        separators=(",", ":"),
                    ),
                    "runner_not_readable",
                ),
            }
            for name, (proof, expected_reason) in bad_proofs.items():
                with self.subTest(proof=name):
                    rejected = self._run(
                        root,
                        env,
                        setup
                        + "_planveyor_role_run_execute_for_plan planner "
                        + f"{plan_rel} --preflight-proof {shlex.quote(proof)} --json",
                    )
                    self.assertEqual(rejected.returncode, 125, rejected.stderr)
                    rejected_payload = json.loads(rejected.stdout)
                    self.assertEqual(rejected_payload["state"], "precondition_failed")
                    self.assertEqual(rejected_payload["non_green_reason"], expected_reason)
                    self.assertEqual(rejected_payload["process_start_outcome"], "not_started")
                    self.assertEqual(self._codex_calls(log_dir), [])
                    self.assertEqual(self._claude_calls(log_dir), [])

            unreadable = self._run(
                root,
                env,
                setup
                + "functions -c planveyor_role_runner_preflight _planveyor_test_preflight_original && "
                + "planveyor_role_runner_preflight() { "
                + "local proof rc; proof=\"$(_planveyor_test_preflight_original \"$@\")\"; rc=$?; "
                + "print -r -- \"$proof\"; "
                + "mv .planveyor.runner.planner .planveyor.runner.planner.saved && "
                + "ln -s .planveyor.runner.planner.saved .planveyor.runner.planner; return $rc; "
                + "} && planveyor_role_run planner --json",
            )
            self.assertEqual(unreadable.returncode, 125, unreadable.stderr)
            unreadable_payload = json.loads(unreadable.stdout)
            self.assertEqual(unreadable_payload["state"], "precondition_failed")
            self.assertEqual(unreadable_payload["non_green_reason"], "runner_not_readable")
            self.assertEqual(unreadable_payload["process_start_outcome"], "not_started")
            self.assertEqual(self._codex_calls(log_dir), [])
            self.assertEqual(self._claude_calls(log_dir), [])

    def test_role_run_binds_post_match_carrier_swap_to_proof_runner(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_role_run_post_match_runner_swap_") as tmpdir:
            root, env, log_dir = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
            self._write_runtime_plan(root, status="In progress")
            plan_rel = "docs/plans/260101_0000_test_runtime.md"
            planner_sid = "00000000-0000-4000-8000-000000000409"

            result = self._run(
                root,
                env,
                f"planveyor_plan_set {plan_rel} >/dev/null && "
                "planveyor_runner_set planner codex >/dev/null && "
                f"planveyor_session_set planner {planner_sid} runner=codex >/dev/null && "
                "functions -c _planveyor_role_run_supervise _planveyor_test_supervise_original && "
                "_planveyor_role_run_supervise() { "
                "planveyor_runner_set planner claude >/dev/null; "
                "_planveyor_test_supervise_original \"$@\"; "
                "} && planveyor_role_run planner --json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["state"], "success")
            self.assertEqual(payload["runner_id"], "codex")
            self.assertEqual(payload["process_start_outcome"], "started")
            self.assertEqual([call["role"] for call in self._codex_calls(log_dir)], ["planner"])
            self.assertEqual(self._claude_calls(log_dir), [])

            carrier = self._run(root, env, "planveyor_runner planner")
            self.assertEqual(carrier.returncode, 0, carrier.stderr)
            self.assertEqual(carrier.stdout.strip(), "claude")
            persisted = json.loads(Path(payload["receipt_path"]).read_text(encoding="utf-8"))
            self.assertEqual(persisted["runner_id"], "codex")

    def test_role_run_projects_non_codex_runner_only_from_current_proof(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_role_run_direct_provider_proof_") as tmpdir:
            root, env, log_dir = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
            self._write_runtime_plan(root, status="In progress")
            env["PLANVEYOR_CLAUDE_MODEL"] = "fixture-claude-model"
            env["PLANVEYOR_CLAUDE_EFFORT"] = "fixture-claude-effort"

            result = self._run(
                root,
                env,
                "planveyor_plan_set docs/plans/260101_0000_test_runtime.md >/dev/null && "
                "planveyor_runner_set planner claude >/dev/null && "
                "planveyor_planner_init >/dev/null && "
                "_planveyor_custom_role_step_dirty_json() { "
                "print -r -- '{\"schema\":\"custom_pipeline_dirty_state.v1\","
                "\"verdict\":\"continue\"}'; } && "
                "planveyor_custom_role_step planner --plan "
                "docs/plans/260101_0000_test_runtime.md --json",
                timeout_seconds=180,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["state"], "completed")
            self.assertEqual(payload["reason_code"], "execution_receipt_valid")
            persisted = json.loads(
                Path(payload["execution_receipt_path"]).read_text(encoding="utf-8")
            )
            self.assertEqual(persisted["runner_id"], "claude")
            calls = self._claude_calls(log_dir)
            self.assertEqual(len(calls), 2)
            self.assertEqual([call["role"] for call in calls], ["planner", "planner"])
            self.assertIn("--session-id", calls[0]["argv"])
            self.assertIn("--resume", calls[1]["argv"])
            self.assertEqual(calls[0]["sid"], calls[1]["sid"])
            self.assertEqual(self._codex_calls(log_dir), [])

    def test_custom_role_step_uses_explicit_plan_without_mutating_cached_pointer(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_custom_role_step_") as tmpdir:
            root, env, log_dir = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
            explicit_plan = self._write_runtime_plan(root, status="In progress")
            stale_plan = root / "docs" / "plans" / "260101_0001_stale_runtime.md"
            stale_plan.write_text(
                explicit_plan.read_text(encoding="utf-8").replace(
                    "test runtime", "stale runtime"
                ),
                encoding="utf-8",
            )
            planner_sid = "00000000-0000-4000-8000-000000000404"

            result = self._run(
                root,
                env,
                "planveyor_plan_set docs/plans/260101_0001_stale_runtime.md >/dev/null && "
                "planveyor_runner_set planner codex >/dev/null && "
                f"planveyor_session_set planner {planner_sid} runner=codex >/dev/null && "
                "functions -c planveyor_role_runner_preflight _planveyor_test_custom_preflight_original && "
                "planveyor_role_runner_preflight() { "
                "mkdir -p .tmp; print -r -- captured-proof >> .tmp/custom-preflight.calls; "
                "_planveyor_test_custom_preflight_original \"$@\"; "
                "} && "
                "_planveyor_custom_role_step_dirty_json() { "
                "print -r -- '{\"schema\":\"custom_pipeline_dirty_state.v1\","
                "\"verdict\":\"continue\"}'; } && "
                "planveyor_custom_role_step planner "
                "--plan docs/plans/260101_0000_test_runtime.md --json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["schema"], "custom_role_step.v1")
            self.assertEqual(payload["state"], "completed")
            self.assertEqual(payload["reason_code"], "execution_receipt_valid")
            self.assertEqual(payload["role"], "planner")
            self.assertEqual(
                payload["target_plan"],
                "docs/plans/260101_0000_test_runtime.md",
            )
            self.assertEqual(payload["execution_readback_state"], "ok")
            self.assertEqual(payload["semantic_gate_state"], "not_applicable")
            self.assertIsNone(payload["semantic_gate_artifact"])
            self.assertTrue(Path(payload["execution_receipt_path"]).exists())
            self.assertEqual(
                (root / ".planveyor.planpath").read_text(encoding="utf-8").splitlines()[-1],
                "docs/plans/260101_0001_stale_runtime.md",
            )
            self.assertEqual(
                [call["role"] for call in self._codex_calls(log_dir)],
                ["planner"],
            )
            self.assertEqual(
                (root / ".tmp" / "custom-preflight.calls").read_text(encoding="utf-8").splitlines(),
                ["captured-proof"],
            )

    def test_custom_role_step_fail_closed_prechild_and_semantic_pointer_matrix(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_custom_role_step_red_") as tmpdir:
            root, env, log_dir = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
            self._write_runtime_plan(root, status="In progress")
            plan_rel = "docs/plans/260101_0000_test_runtime.md"

            dirty = self._run(
                root,
                env,
                "_planveyor_custom_role_step_dirty_json() { "
                "print -r -- '{\"schema\":\"custom_pipeline_dirty_state.v1\","
                "\"verdict\":\"stop\"}'; } && "
                f"planveyor_custom_role_step planner --plan {plan_rel} --json",
            )
            self.assertEqual(dirty.returncode, 125, dirty.stderr)
            dirty_payload = json.loads(dirty.stdout)
            self.assertEqual(dirty_payload["state"], "blocked")
            self.assertEqual(dirty_payload["reason_code"], "dirty_state_blocked")
            self.assertEqual(self._codex_calls(log_dir), [])

            unsupported = self._run(
                root,
                env,
                f"planveyor_custom_role_step manager --plan {plan_rel} --json",
            )
            self.assertEqual(unsupported.returncode, 2, unsupported.stderr)
            unsupported_payload = json.loads(unsupported.stdout)
            self.assertEqual(unsupported_payload["state"], "blocked")
            self.assertEqual(unsupported_payload["reason_code"], "internal_error")
            self.assertEqual(self._codex_calls(log_dir), [])

            fake_receipt = root / ".tmp" / "fake-role-receipt.json"
            fake_receipt.parent.mkdir(parents=True, exist_ok=True)
            fake_receipt.write_text("{}\n", encoding="utf-8")
            fake_payload = json.dumps(
                {
                    "run_id": "fake-run-id",
                    "session_key": "planner",
                    "target_plan": plan_rel,
                    "receipt_path": str(fake_receipt),
                    "state": "success",
                    "readback_state": "ok",
                    "non_green_reason": "",
                    "role_outcome_readback_persisted": True,
                }
            )
            missing_semantic_payload = dict(json.loads(fake_payload))
            missing_semantic_payload.update(
                {
                    "role_outcome_state": "finalized",
                    "role_outcome_reason_code": "outcome_finalized",
                    "role_outcome_readback_path": ".tmp/missing-role-outcome.json",
                }
            )
            partial_semantic = self._run(
                root,
                env,
                "_planveyor_custom_role_step_dirty_json() { "
                "print -r -- '{\"schema\":\"custom_pipeline_dirty_state.v1\","
                "\"verdict\":\"continue\"}'; }; "
                "planveyor_role_runner_preflight() { print -r -- '{\"execution_ready\":true}'; }; "
                f"_planveyor_role_run_execute_for_plan() {{ print -r -- {shlex.quote(json.dumps(missing_semantic_payload))}; }}; "
                "planveyor_role_run_receipt_check() { return 0; }; "
                f"planveyor_custom_role_step planner --plan {plan_rel} --json",
            )
            self.assertEqual(partial_semantic.returncode, 125, partial_semantic.stderr)
            semantic_payload = json.loads(partial_semantic.stdout)
            self.assertEqual(semantic_payload["state"], "blocked")
            self.assertEqual(
                semantic_payload["reason_code"],
                "semantic_gate_artifact_missing",
            )
            self.assertEqual(semantic_payload["execution_readback_state"], "ok")
            self.assertIsNone(semantic_payload["semantic_gate_artifact"])
            self.assertEqual(semantic_payload["role_outcome_state"], "finalized")
            self.assertEqual(
                semantic_payload["role_outcome_reason_code"],
                "outcome_finalized",
            )
            self.assertEqual(
                semantic_payload["role_outcome_readback_path"],
                ".tmp/missing-role-outcome.json",
            )
            self.assertTrue(semantic_payload["role_outcome_readback_persisted"])
            self.assertEqual(self._codex_calls(log_dir), [])

            overlap_payload = dict(json.loads(fake_payload))
            overlap_payload.update(
                {
                    "state": "precondition_failed",
                    "readback_state": "ok",
                    "non_green_reason": "role_run_lock_contended",
                    "role_outcome_readback_persisted": False,
                }
            )
            overlap = self._run(
                root,
                env,
                "_planveyor_custom_role_step_dirty_json() { "
                "print -r -- '{\"schema\":\"custom_pipeline_dirty_state.v1\","
                "\"verdict\":\"continue\"}'; }; "
                "planveyor_role_runner_preflight() { print -r -- '{\"execution_ready\":true}'; }; "
                f"_planveyor_role_run_execute_for_plan() {{ print -r -- "
                f"{shlex.quote(json.dumps(overlap_payload))}; }}; "
                f"planveyor_custom_role_step planner --plan {plan_rel} --json",
            )
            self.assertEqual(overlap.returncode, 125, overlap.stderr)
            self.assertEqual(
                json.loads(overlap.stdout)["reason_code"],
                "role_step_in_progress",
            )

            missing_receipt_payload = dict(json.loads(fake_payload))
            missing_receipt_payload.update(
                {
                    "receipt_path": str(root / ".tmp" / "missing-role-receipt.json"),
                    "role_outcome_readback_persisted": False,
                }
            )
            missing_receipt = self._run(
                root,
                env,
                "_planveyor_custom_role_step_dirty_json() { "
                "print -r -- '{\"schema\":\"custom_pipeline_dirty_state.v1\","
                "\"verdict\":\"continue\"}'; }; "
                "planveyor_role_runner_preflight() { print -r -- '{\"execution_ready\":true}'; }; "
                f"_planveyor_role_run_execute_for_plan() {{ print -r -- "
                f"{shlex.quote(json.dumps(missing_receipt_payload))}; }}; "
                f"planveyor_custom_role_step planner --plan {plan_rel} --json",
            )
            self.assertEqual(missing_receipt.returncode, 125, missing_receipt.stderr)
            self.assertEqual(
                json.loads(missing_receipt.stdout)["reason_code"],
                "execution_receipt_missing",
            )

            invalid_receipt = self._run(
                root,
                env,
                "_planveyor_custom_role_step_dirty_json() { "
                "print -r -- '{\"schema\":\"custom_pipeline_dirty_state.v1\","
                "\"verdict\":\"continue\"}'; }; "
                "planveyor_role_runner_preflight() { print -r -- '{\"execution_ready\":true}'; }; "
                f"_planveyor_role_run_execute_for_plan() {{ print -r -- "
                f"{shlex.quote(fake_payload)}; }}; "
                "planveyor_role_run_receipt_check() { return 1; }; "
                f"planveyor_custom_role_step planner --plan {plan_rel} --json",
            )
            self.assertEqual(invalid_receipt.returncode, 125, invalid_receipt.stderr)
            self.assertEqual(
                json.loads(invalid_receipt.stdout)["reason_code"],
                "execution_receipt_invalid",
            )

            outcome_path = root / ".tmp" / "fake-role-outcome.json"
            outcome_path.write_text('{"state":"finalized"}\n', encoding="utf-8")
            persisted_payload = dict(json.loads(fake_payload))
            persisted_payload.update(
                {
                    "role_outcome_state": "finalized",
                    "role_outcome_reason_code": "outcome_finalized",
                    "role_outcome_readback_path": outcome_path.relative_to(root).as_posix(),
                }
            )
            persisted = self._run(
                root,
                env,
                "_planveyor_custom_role_step_dirty_json() { "
                "print -r -- '{\"schema\":\"custom_pipeline_dirty_state.v1\","
                "\"verdict\":\"continue\"}'; }; "
                "planveyor_role_runner_preflight() { print -r -- '{\"execution_ready\":true}'; }; "
                f"_planveyor_role_run_execute_for_plan() {{ print -r -- "
                f"{shlex.quote(json.dumps(persisted_payload))}; }}; "
                "planveyor_role_run_receipt_check() { return 0; }; "
                f"planveyor_custom_role_step planner --plan {plan_rel} --json",
            )
            self.assertEqual(persisted.returncode, 0, persisted.stderr)
            persisted_step = json.loads(persisted.stdout)
            self.assertEqual(persisted_step["state"], "completed")
            self.assertEqual(
                persisted_step["semantic_gate_state"],
                "not_evaluated_by_helper",
            )
            self.assertEqual(
                persisted_step["semantic_gate_artifact"],
                outcome_path.relative_to(root).as_posix(),
            )
            self.assertEqual(persisted_step["role_outcome_state"], "finalized")
            self.assertEqual(
                persisted_step["role_outcome_reason_code"],
                "outcome_finalized",
            )
            self.assertEqual(
                persisted_step["role_outcome_readback_path"],
                outcome_path.relative_to(root).as_posix(),
            )
            self.assertTrue(persisted_step["role_outcome_readback_persisted"])
            self.assertEqual(self._codex_calls(log_dir), [])

    def test_custom_role_step_projects_complete_outcome_groups_at_public_boundary(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_custom_role_step_outcome_projection_") as tmpdir:
            root, env, log_dir = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
            self._write_runtime_plan(root, status="In progress")
            plan_rel = "docs/plans/260101_0000_test_runtime.md"
            fake_receipt = root / ".tmp" / "fake-role-receipt.json"
            fake_receipt.parent.mkdir(parents=True, exist_ok=True)
            fake_receipt.write_text("{}\n", encoding="utf-8")

            base_payload: dict[str, object] = {
                "run_id": "fake-run-id",
                "session_key": "planner",
                "target_plan": plan_rel,
                "receipt_path": str(fake_receipt),
                "state": "success",
                "readback_state": "ok",
                "non_green_reason": "",
            }
            outcome_fields = (
                "role_outcome_state",
                "role_outcome_reason_code",
                "role_outcome_readback_path",
                "role_outcome_readback_persisted",
                "role_outcome_diagnostic_state",
                "role_outcome_diagnostic_reason_code",
                "role_outcome_diagnostic_path",
                "role_outcome_recovery_state",
                "role_outcome_safe_action",
            )

            def run_step(
                payload: dict[str, object],
                *,
                execution_rc: int = 0,
                receipt_valid: bool = True,
            ) -> subprocess.CompletedProcess[str]:
                return self._run(
                    root,
                    env,
                    "_planveyor_custom_role_step_dirty_json() { "
                    "print -r -- '{\"schema\":\"custom_pipeline_dirty_state.v1\","
                    "\"verdict\":\"continue\"}'; }; "
                    "planveyor_role_runner_preflight() { print -r -- '{\"execution_ready\":true}'; }; "
                    f"_planveyor_role_run_execute_for_plan() {{ print -r -- {shlex.quote(json.dumps(payload))}; "
                    f"return {execution_rc}; }}; "
                    f"planveyor_role_run_receipt_check() {{ return {0 if receipt_valid else 1}; }}; "
                    f"planveyor_custom_role_step planner --plan {plan_rel} --json",
                )

            core_payload = dict(base_payload)
            core_payload.update(
                {
                    "role_outcome_state": "finalized",
                    "role_outcome_reason_code": "outcome_finalized",
                    "role_outcome_readback_path": ".tmp/fake-role-outcome.json",
                    "role_outcome_readback_persisted": False,
                }
            )
            core = run_step(core_payload)
            self.assertEqual(core.returncode, 0, core.stderr)
            core_step = json.loads(core.stdout)
            self.assertEqual(core_step["state"], "completed")
            self.assertEqual(core_step["reason_code"], "execution_receipt_valid")
            self.assertEqual(
                {name: core_step[name] for name in outcome_fields[:4]},
                {
                    "role_outcome_state": "finalized",
                    "role_outcome_reason_code": "outcome_finalized",
                    "role_outcome_readback_path": ".tmp/fake-role-outcome.json",
                    "role_outcome_readback_persisted": False,
                },
            )
            self.assertIsNone(core_step["semantic_gate_artifact"])
            self.assertEqual(core_step["semantic_gate_state"], "not_applicable")

            diagnostic_payload = dict(base_payload)
            diagnostic_payload.update(
                {
                    "role_outcome_diagnostic_state": "blocked",
                    "role_outcome_diagnostic_reason_code": "field_missing",
                    "role_outcome_diagnostic_path": ".tmp/fake-diagnostic.json",
                }
            )
            diagnostic = run_step(diagnostic_payload)
            self.assertEqual(diagnostic.returncode, 0, diagnostic.stderr)
            diagnostic_step = json.loads(diagnostic.stdout)
            self.assertEqual(diagnostic_step["state"], "completed")
            self.assertEqual(
                {name: diagnostic_step[name] for name in outcome_fields[4:7]},
                {
                    "role_outcome_diagnostic_state": "blocked",
                    "role_outcome_diagnostic_reason_code": "field_missing",
                    "role_outcome_diagnostic_path": ".tmp/fake-diagnostic.json",
                },
            )
            self.assertTrue(all(name not in diagnostic_step for name in outcome_fields[:4]))
            self.assertTrue(all(name not in diagnostic_step for name in outcome_fields[7:]))

            recovery_only_payload = dict(base_payload)
            recovery_only_payload.update(
                {
                    "role_outcome_recovery_state": "rerun_available",
                    "role_outcome_safe_action": "reject_rerun",
                }
            )
            recovery_only = run_step(recovery_only_payload)
            self.assertEqual(recovery_only.returncode, 0, recovery_only.stderr)
            recovery_only_step = json.loads(recovery_only.stdout)
            self.assertEqual(recovery_only_step["state"], "completed")
            self.assertEqual(
                {name: recovery_only_step[name] for name in outcome_fields[7:]},
                {
                    "role_outcome_recovery_state": "rerun_available",
                    "role_outcome_safe_action": "reject_rerun",
                },
            )
            self.assertTrue(all(name not in recovery_only_step for name in outcome_fields[:7]))

            combined_payload = dict(diagnostic_payload)
            combined_payload.update(
                {
                    "role_outcome_recovery_state": "rerun_available",
                    "role_outcome_safe_action": "reject_rerun",
                }
            )
            combined = run_step(combined_payload)
            self.assertEqual(combined.returncode, 0, combined.stderr)
            combined_step = json.loads(combined.stdout)
            self.assertEqual(
                {name: combined_step[name] for name in outcome_fields[4:]},
                {
                    "role_outcome_diagnostic_state": "blocked",
                    "role_outcome_diagnostic_reason_code": "field_missing",
                    "role_outcome_diagnostic_path": ".tmp/fake-diagnostic.json",
                    "role_outcome_recovery_state": "rerun_available",
                    "role_outcome_safe_action": "reject_rerun",
                },
            )

            red_execution_payload = dict(core_payload)
            red_execution_payload.update(
                {
                    "state": "failed",
                    "non_green_reason": "role_run_failed",
                }
            )
            red_execution = run_step(red_execution_payload, execution_rc=17)
            self.assertEqual(red_execution.returncode, 125, red_execution.stderr)
            red_execution_step = json.loads(red_execution.stdout)
            self.assertEqual(red_execution_step["state"], "blocked")
            self.assertEqual(red_execution_step["reason_code"], "role_run_failed")
            self.assertEqual(
                {name: red_execution_step[name] for name in outcome_fields[:4]},
                {name: core_payload[name] for name in outcome_fields[:4]},
            )

            lock_payload = dict(core_payload)
            lock_payload.update(
                {
                    "state": "precondition_failed",
                    "non_green_reason": "role_run_lock_contended",
                }
            )
            lock = run_step(lock_payload, execution_rc=125)
            self.assertEqual(lock.returncode, 125, lock.stderr)
            lock_step = json.loads(lock.stdout)
            self.assertEqual(lock_step["reason_code"], "role_step_in_progress")
            self.assertEqual(
                {name: lock_step[name] for name in outcome_fields[:4]},
                {name: core_payload[name] for name in outcome_fields[:4]},
            )

            missing_receipt_payload = dict(core_payload)
            missing_receipt_payload["receipt_path"] = str(
                root / ".tmp" / "missing-role-receipt.json"
            )
            missing_receipt = run_step(missing_receipt_payload)
            self.assertEqual(missing_receipt.returncode, 125, missing_receipt.stderr)
            missing_receipt_step = json.loads(missing_receipt.stdout)
            self.assertEqual(missing_receipt_step["state"], "blocked")
            self.assertEqual(
                missing_receipt_step["reason_code"],
                "execution_receipt_missing",
            )
            self.assertEqual(missing_receipt_step["execution_readback_state"], "missing")
            self.assertEqual(
                {name: missing_receipt_step[name] for name in outcome_fields[:4]},
                {name: core_payload[name] for name in outcome_fields[:4]},
            )

            invalid_receipt = run_step(core_payload, receipt_valid=False)
            self.assertEqual(invalid_receipt.returncode, 125, invalid_receipt.stderr)
            invalid_receipt_step = json.loads(invalid_receipt.stdout)
            self.assertEqual(invalid_receipt_step["state"], "blocked")
            self.assertEqual(
                invalid_receipt_step["reason_code"],
                "execution_receipt_invalid",
            )
            self.assertEqual(invalid_receipt_step["execution_readback_state"], "blocked")
            self.assertEqual(
                {name: invalid_receipt_step[name] for name in outcome_fields[:4]},
                {name: core_payload[name] for name in outcome_fields[:4]},
            )

            ordinary = run_step(dict(base_payload))
            self.assertEqual(ordinary.returncode, 0, ordinary.stderr)
            ordinary_step = json.loads(ordinary.stdout)
            self.assertEqual(ordinary_step["state"], "completed")
            self.assertTrue(all(name not in ordinary_step for name in outcome_fields))

            malformed_payloads = (
                {"role_outcome_state": "finalized"},
                {
                    **core_payload,
                    "role_outcome_diagnostic_state": "blocked",
                },
                {
                    "role_outcome_recovery_state": "rerun_available",
                },
                {
                    **core_payload,
                    "role_outcome_readback_persisted": "false",
                },
                {
                    **core_payload,
                    "role_outcome_diagnostic_state": "blocked",
                    "role_outcome_diagnostic_reason_code": "field_missing",
                    "role_outcome_diagnostic_path": "",
                },
                {
                    **core_payload,
                    "role_outcome_unknown": "forbidden",
                },
            )
            for malformed in malformed_payloads:
                payload = dict(base_payload)
                payload.update(malformed)
                result = run_step(payload)
                self.assertEqual(result.returncode, 125, result.stderr)
                step = json.loads(result.stdout)
                self.assertEqual(step["state"], "blocked")
                self.assertEqual(step["reason_code"], "internal_error")
                self.assertTrue(all(name not in step for name in outcome_fields))

            self.assertEqual(self._codex_calls(log_dir), [])

    def test_manager_public_native_collab_resume_tui_and_custom_status_surfaces(self) -> None:
        """Exercise public Manager routes against a disposable local session record."""
        with tempfile.TemporaryDirectory(prefix="planveyor_manager_public_surfaces_") as tmpdir:
            root, env, log_dir = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
            plan = root / "docs" / "plans" / "260101_0000_manager_surface.md"
            plan.parent.mkdir(parents=True, exist_ok=True)
            plan.write_text(
                textwrap.dedent(
                    """\
                    # Plan: manager surface fixture

                    **Date:** 2026-01-01 00:00 MSK
                    **Plan type:** dev
                    **Status:** In progress

                    ## Meta (machine-readable JSON; required for new plans)

                    ```json
                    {"plan_meta":{"cluster":"ops","tags":[],"required_manager_mode":"either"}}
                    ```

                    ## Evidence
                    """
                ),
                encoding="utf-8",
            )
            plan_rel = plan.relative_to(root).as_posix()
            sid = SUCCESS_SIDS["manager"]
            rollout = (
                Path(env["HOME"])
                / ".codex"
                / "sessions"
                / "2026"
                / "09"
                / f"rollout-2026-09-14T00-00-00-{sid}.jsonl"
            )
            rollout.parent.mkdir(parents=True, exist_ok=True)
            rollout.write_text(
                json.dumps(
                    {
                        "type": "session_meta",
                        "payload": {"id": sid, "cwd": str(root)},
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            surfaces = (
                ("init", "planveyor_manager_init"),
                ("resume", "planveyor_manager_resume"),
                (
                    "native",
                    f"planveyor_plan_set {plan_rel} >/dev/null && planveyor_manager",
                ),
                (
                    "collab",
                    f"planveyor_plan_set {plan_rel} >/dev/null && planveyor_manager_collab",
                ),
                ("collab_cmd", "planveyor_manager_collab_cmd status"),
                (
                    "collab_tui",
                    f"planveyor_plan_set {plan_rel} >/dev/null && "
                    "planveyor_manager_collab_tui --no-alt-screen",
                ),
                ("custom_cmd", "planveyor_manager_custom_pipeline_cmd status"),
            )
            for surface, command in surfaces:
                with self.subTest(surface=surface):
                    result = self._run(root, env, command)
                    self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

            calls = self._codex_calls(log_dir)
            self.assertEqual(len(calls), len(surfaces))
            self.assertEqual(
                [str(call["role"]) for call in calls],
                ["manager", "", "manager", "", "", "", ""],
            )
            self.assertTrue(
                all(
                    os.path.realpath(str(call["cwd"])) == os.path.realpath(str(root))
                    for call in calls
                )
            )
            self.assertTrue(all(not call["role_run_env_keys"] for call in calls))
            self.assertEqual(calls[1]["argv"], ["resume", sid])
            self.assertIn("resume", calls[2]["argv"])
            self.assertIn("MANAGER_CMD=run", str(calls[3]["argv"][-1]))
            self.assertIn("MANAGER_CMD=status", str(calls[4]["argv"][-1]))
            self.assertIn("--no-alt-screen", calls[5]["argv"])
            self.assertIn("-s", calls[5]["argv"])
            self.assertIn("workspace-write", calls[5]["argv"])
            self.assertIn("MANAGER_CMD=status", str(calls[6]["argv"][-1]))

    def test_manager_invocation_receipt_checkpoint_and_terminal_exact_readback(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_manager_invocation_") as tmpdir:
            root, env, _ = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
            plan = self._write_runtime_plan(root, status="In progress")
            plan_rel = plan.relative_to(root).as_posix()
            command = (
                "id=$(_planveyor_manager_invocation_id); "
                "receipt_path=$(_planveyor_manager_invocation_receipt_path \"$id\"); "
                f"_planveyor_manager_invocation_receipt_seed \"$id\" \"$receipt_path\" "
                f"{SUCCESS_SIDS['manager']} run {shlex.quote(plan_rel)} "
                "2026-01-01T00:00:00Z >/dev/null; "
                "MANAGER_INVOCATION_ID=\"$id\" MANAGER_INVOCATION_RECEIPT_PATH=\"$receipt_path\" "
                "planveyor_manager_invocation_checkpoint --stop-reason-code terminal_status "
                f"--source-ref {shlex.quote(plan_rel + '#Evidence')} --json >/dev/null; "
                "_planveyor_manager_invocation_receipt_finalize \"$receipt_path\" \"$id\" "
                f"completed manager_process_exited 0 {shlex.quote(plan_rel)} {shlex.quote(plan_rel)} "
                "'{\"state\":\"ok\"}' '{\"state\":\"not_applicable\"}' "
                "0123456789abcdef "
                "'{\"state\":\"dirty\",\"changed_path_count\":1}' "
                "'{\"state\":\"non_terminal_status\"}' "
                f"{shlex.quote(plan_rel + '#Evidence')} >/dev/null; "
                "_planveyor_manager_invocation_receipt_pointer \"$receipt_path\" \"$id\" updated >/dev/null; "
                "_planveyor_manager_invocation_receipt_read \"$receipt_path\" \"$id\" terminal"
            )

            result = self._run(root, env, command)

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["schema"], "manager_invocation_receipt.v1")
            self.assertEqual(payload["command"], "run")
            self.assertEqual(payload["pipeline_mode"], "manager_custom_pipeline")
            self.assertRegex(payload["immutable_identity_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(payload["state"], "completed")
            self.assertEqual(payload["reason_code"], "manager_process_exited")
            self.assertEqual(payload["stop_checkpoint_state"], "recorded")
            self.assertEqual(payload["stop_reason_code"], "terminal_status")
            self.assertEqual(payload["stop_source_refs"], [f"{plan_rel}#Evidence"])
            self.assertEqual(payload["compatibility_pointer_state"], "updated")
            self.assertTrue(Path(payload["receipt_path"]).is_file())
            self.assertEqual(
                stat.S_IMODE(Path(payload["receipt_path"]).stat().st_mode),
                0o600,
            )

            blocked_command = (
                "id=$(_planveyor_manager_invocation_id); "
                "receipt_path=$(_planveyor_manager_invocation_receipt_path \"$id\"); "
                f"_planveyor_manager_invocation_receipt_seed \"$id\" \"$receipt_path\" "
                f"{SUCCESS_SIDS['manager']} run {shlex.quote(plan_rel)} "
                "2026-01-01T00:00:00Z >/dev/null; "
                "_planveyor_manager_invocation_receipt_finalize \"$receipt_path\" \"$id\" "
                f"blocked prompt_body_binding_changed '' {shlex.quote(plan_rel)} "
                f"{shlex.quote(plan_rel)} "
                "'{\"state\":\"not_evaluated\",\"reason\":\"prompt_body_binding_changed\"}' "
                "'{\"state\":\"not_evaluated\",\"reason\":\"prompt_body_binding_changed\"}' "
                "0123456789abcdef "
                "'{\"state\":\"not_evaluated\",\"reason\":\"prompt_body_binding_changed\"}' "
                "'{\"state\":\"blocked\",\"reason\":\"prompt_body_binding_changed\"}' "
                f"{shlex.quote(plan_rel + '#Evidence')} >/dev/null; "
                "_planveyor_manager_invocation_receipt_pointer \"$receipt_path\" \"$id\" "
                "updated >/dev/null; "
                "_planveyor_manager_invocation_receipt_read \"$receipt_path\" \"$id\" terminal"
            )
            blocked = self._run(root, env, blocked_command)

            self.assertEqual(blocked.returncode, 0, blocked.stderr)
            blocked_payload = json.loads(blocked.stdout)
            self.assertEqual(blocked_payload["state"], "blocked")
            self.assertEqual(
                blocked_payload["reason_code"], "prompt_body_binding_changed"
            )
            self.assertIsNone(blocked_payload["manager_exit_code"])
            self.assertEqual(blocked_payload["stop_checkpoint_state"], "missing")
            self.assertIsNone(blocked_payload["stop_reason_code"])
            self.assertEqual(blocked_payload["stop_source_refs"], [])
            self.assertEqual(
                blocked_payload["compatibility_pointer_state"], "updated"
            )
            self.assertEqual(
                blocked_payload["blocker"],
                {
                    "reason_code": "prompt_body_binding_changed",
                    "stop_reason_code": None,
                    "source_refs": [],
                },
            )

    def test_manager_invocation_receipt_rejects_foreign_partial_and_repeated_mutations(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_manager_invocation_red_") as tmpdir:
            root, env, _ = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
            plan = self._write_runtime_plan(root, status="In progress")
            plan_rel = plan.relative_to(root).as_posix()

            def seed() -> tuple[str, Path]:
                seeded = self._run(
                    root,
                    env,
                    "id=$(_planveyor_manager_invocation_id); "
                    "receipt_path=$(_planveyor_manager_invocation_receipt_path \"$id\"); "
                    f"_planveyor_manager_invocation_receipt_seed \"$id\" \"$receipt_path\" "
                    f"{SUCCESS_SIDS['manager']} run {shlex.quote(plan_rel)} "
                    "2026-01-01T00:00:00Z >/dev/null; "
                    "print -r -- \"$id\"; print -r -- \"$receipt_path\"",
                )
                self.assertEqual(seeded.returncode, 0, seeded.stderr)
                invocation_id, path_raw = seeded.stdout.splitlines()
                return invocation_id, Path(path_raw)

            invocation_id, receipt_path = seed()
            first = self._run(
                root,
                env,
                f"MANAGER_INVOCATION_ID={shlex.quote(invocation_id)} "
                f"MANAGER_INVOCATION_RECEIPT_PATH={shlex.quote(str(receipt_path))} "
                "planveyor_manager_invocation_checkpoint "
                "--stop-reason-code terminal_status "
                f"--source-ref {shlex.quote(plan_rel + '#Evidence')} --json",
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            checkpoint_bytes = receipt_path.read_bytes()

            repeated = self._run(
                root,
                env,
                f"MANAGER_INVOCATION_ID={shlex.quote(invocation_id)} "
                f"MANAGER_INVOCATION_RECEIPT_PATH={shlex.quote(str(receipt_path))} "
                "planveyor_manager_invocation_checkpoint "
                "--stop-reason-code terminal_status "
                f"--source-ref {shlex.quote(plan_rel + '#Evidence')} --json",
            )
            self.assertEqual(repeated.returncode, 125, repeated.stderr)
            self.assertEqual(
                json.loads(repeated.stdout)["reason_code"],
                "checkpoint_already_recorded",
            )
            self.assertEqual(receipt_path.read_bytes(), checkpoint_bytes)

            foreign = self._run(
                root,
                env,
                "MANAGER_INVOCATION_ID=foreign-invocation "
                f"MANAGER_INVOCATION_RECEIPT_PATH={shlex.quote(str(receipt_path))} "
                "planveyor_manager_invocation_checkpoint "
                "--stop-reason-code terminal_status "
                f"--source-ref {shlex.quote(plan_rel + '#Evidence')} --json",
            )
            self.assertEqual(foreign.returncode, 125, foreign.stderr)
            self.assertEqual(
                json.loads(foreign.stdout)["reason_code"],
                "invalid_receipt_path",
            )
            self.assertEqual(receipt_path.read_bytes(), checkpoint_bytes)

            finalized = self._run(
                root,
                env,
                f"_planveyor_manager_invocation_receipt_finalize "
                f"{shlex.quote(str(receipt_path))} {shlex.quote(invocation_id)} "
                f"completed manager_process_exited 0 {shlex.quote(plan_rel)} "
                f"{shlex.quote(plan_rel)} '{{\"state\":\"ok\"}}' "
                "'{\"state\":\"not_applicable\"}' 0123456789abcdef "
                "'{\"state\":\"clean\",\"changed_path_count\":0}' "
                "'{\"state\":\"non_terminal_status\"}' "
                f"{shlex.quote(plan_rel + '#Evidence')} >/dev/null; "
                f"_planveyor_manager_invocation_receipt_pointer "
                f"{shlex.quote(str(receipt_path))} {shlex.quote(invocation_id)} "
                "updated >/dev/null",
            )
            self.assertEqual(finalized.returncode, 0, finalized.stderr)
            terminal_bytes = receipt_path.read_bytes()
            post_terminal = self._run(
                root,
                env,
                f"MANAGER_INVOCATION_ID={shlex.quote(invocation_id)} "
                f"MANAGER_INVOCATION_RECEIPT_PATH={shlex.quote(str(receipt_path))} "
                "planveyor_manager_invocation_checkpoint "
                "--stop-reason-code terminal_status "
                f"--source-ref {shlex.quote(plan_rel + '#Evidence')} --json",
            )
            self.assertEqual(post_terminal.returncode, 125, post_terminal.stderr)
            self.assertEqual(
                json.loads(post_terminal.stdout)["reason_code"],
                "checkpoint_not_running",
            )
            self.assertEqual(receipt_path.read_bytes(), terminal_bytes)

            partial_id, partial_path = seed()
            invalid_completed = self._run(
                root,
                env,
                f"_planveyor_manager_invocation_receipt_finalize "
                f"{shlex.quote(str(partial_path))} {shlex.quote(partial_id)} "
                f"completed manager_process_exited 0 {shlex.quote(plan_rel)} "
                f"{shlex.quote(plan_rel)} '{{\"state\":\"ok\"}}' "
                "'{\"state\":\"not_applicable\"}' 0123456789abcdef "
                "'{\"state\":\"clean\",\"changed_path_count\":0}' "
                "'{\"state\":\"non_terminal_status\"}' "
                f"{shlex.quote(plan_rel + '#Evidence')}",
            )
            self.assertEqual(invalid_completed.returncode, 125, invalid_completed.stderr)
            self.assertEqual(
                json.loads(invalid_completed.stdout)["reason_code"],
                "receipt_phase_invalid",
            )
            partial_payload = json.loads(partial_path.read_text(encoding="utf-8"))
            self.assertEqual(partial_payload["state"], "running")
            self.assertEqual(partial_payload["stop_checkpoint_state"], "missing")


            unknown_id, unknown_path = seed()
            unknown = self._run(
                root,
                env,
                f"_planveyor_manager_invocation_receipt_finalize "
                f"{shlex.quote(str(unknown_path))} {shlex.quote(unknown_id)} "
                f"blocked unlisted_uif2_reason '' {shlex.quote(plan_rel)} "
                f"{shlex.quote(plan_rel)} '{{\"state\":\"not_evaluated\"}}' "
                "'{\"state\":\"not_evaluated\"}' 0123456789abcdef "
                "'{\"state\":\"not_evaluated\"}' "
                "'{\"state\":\"blocked\"}' "
                f"{shlex.quote(plan_rel + '#Evidence')}",
            )
            self.assertEqual(unknown.returncode, 125, unknown.stderr)
            self.assertEqual(
                json.loads(unknown.stdout)["reason_code"], "invalid_terminal_reason"
            )
            unknown_payload = json.loads(unknown_path.read_text(encoding="utf-8"))
            self.assertEqual(unknown_payload["state"], "running")
            self.assertEqual(unknown_payload["stop_checkpoint_state"], "missing")

            malformed_id, malformed_path = seed()
            malformed_bytes = malformed_path.read_bytes()
            malformed_ref = self._run(
                root,
                env,
                f"MANAGER_INVOCATION_ID={shlex.quote(malformed_id)} "
                f"MANAGER_INVOCATION_RECEIPT_PATH={shlex.quote(str(malformed_path))} "
                "planveyor_manager_invocation_checkpoint "
                "--stop-reason-code terminal_status --source-ref '#only' --json",
            )
            self.assertEqual(malformed_ref.returncode, 125, malformed_ref.stderr)
            self.assertEqual(
                json.loads(malformed_ref.stdout)["reason_code"],
                "checkpoint_invalid",
            )
            self.assertEqual(malformed_path.read_bytes(), malformed_bytes)

            forged_id, forged_path = seed()
            forged_payload = json.loads(forged_path.read_text(encoding="utf-8"))
            forged_payload["manager_sid"] = "foreign-sid"
            forged_path.write_text(
                json.dumps(forged_payload, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            forged = self._run(
                root,
                env,
                f"_planveyor_manager_invocation_receipt_read "
                f"{shlex.quote(str(forged_path))} {shlex.quote(forged_id)}",
            )
            self.assertEqual(forged.returncode, 125, forged.stderr)
            self.assertEqual(
                json.loads(forged.stdout)["reason_code"],
                "immutable_identity_mismatch",
            )

        with tempfile.TemporaryDirectory(prefix="planveyor_manager_invocation_symlink_") as tmpdir:
            root, env, _ = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
            external = root / ".tmp" / "foreign-manager-runs"
            external.mkdir(parents=True)
            (root / ".planveyor.manager_runs").symlink_to(external, target_is_directory=True)
            unsafe = self._run(
                root,
                env,
                "id=$(_planveyor_manager_invocation_id); "
                "receipt_path=$(_planveyor_manager_invocation_receipt_path \"$id\"); "
                f"_planveyor_manager_invocation_receipt_seed \"$id\" \"$receipt_path\" "
                f"{SUCCESS_SIDS['manager']} interactive '' "
                "2026-01-01T00:00:00Z",
            )
            self.assertEqual(unsafe.returncode, 125, unsafe.stderr)
            self.assertEqual(
                json.loads(unsafe.stdout)["reason_code"],
                "unsafe_receipt_root",
            )
            self.assertEqual(list(external.iterdir()), [])

    def test_role_run_finalizes_machine_owned_outcome_without_execution_schema_widening(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_role_outcome_runtime_") as tmpdir:
            root, env, _ = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
            plan_path = self._write_role_outcome_runtime_plan(root)
            draft = self._role_outcome_semantic_draft()
            coder_sid = SUCCESS_SIDS["coder"]
            command = (
                "planveyor_plan_set docs/plans/260101_0000_test_runtime.md >/dev/null && "
                f"planveyor_session_set coder {coder_sid} runner=codex >/dev/null && "
                "planveyor_coder() { "
                f"print -r -- {shlex.quote(draft)} >> {shlex.quote(str(plan_path))}; "
                "return 0; } && "
                "planveyor_role_run coder --json"
            )

            result = self._run(root, env, command)

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["state"], "success")
            self.assertEqual(payload["role_outcome_state"], "finalized")
            self.assertEqual(payload["role_outcome_reason_code"], "ok")
            self.assertTrue(payload["role_outcome_readback_persisted"])
            readback_path = root / payload["role_outcome_readback_path"]
            self.assertEqual(
                readback_path,
                root / ".tmp" / "planveyor_role_runs" / payload["run_id"] / "role_outcome_readback.json",
            )
            readback = json.loads(readback_path.read_text(encoding="utf-8"))
            self.assertEqual(readback["schema_version"], "role_outcome_readback.v1")
            self.assertEqual(readback["role"], "coder")
            self.assertEqual(readback["lane"], "coder")
            self.assertEqual(readback["run_id"], payload["run_id"])
            self.assertEqual(readback["carrier_path"], "docs/plans/260101_0000_test_runtime.md")
            plan_text = plan_path.read_text(encoding="utf-8")
            self.assertNotIn("- Role outcome semantic draft", plan_text)
            self.assertIn("- Role outcome receipt", plan_text)
            self.assertIn(f"  - run_id: {payload['run_id']}", plan_text)
            persisted = json.loads(Path(payload["receipt_path"]).read_text(encoding="utf-8"))
            self.assertNotIn("lane", persisted)
            self.assertFalse(any(key.startswith("role_outcome_") for key in persisted))
            self.assertEqual(stat.S_IMODE(readback_path.stat().st_mode), 0o600)

    def test_role_run_outcome_preflight_blocks_stale_draft_before_child_start(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_role_outcome_preflight_") as tmpdir:
            root, env, _ = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
            self._write_role_outcome_runtime_plan(
                root,
                evidence=self._role_outcome_semantic_draft(),
            )
            child_marker = root / ".tmp" / "child-started"
            coder_sid = SUCCESS_SIDS["coder"]
            command = (
                "planveyor_plan_set docs/plans/260101_0000_test_runtime.md >/dev/null && "
                f"planveyor_session_set coder {coder_sid} runner=codex >/dev/null && "
                f"planveyor_coder() {{ touch {shlex.quote(str(child_marker))}; return 0; }} && "
                "planveyor_role_run coder --json"
            )

            result = self._run(root, env, command)

            self.assertEqual(result.returncode, 125, result.stderr + result.stdout)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["state"], "precondition_failed")
            self.assertEqual(payload["process_start_outcome"], "not_started")
            self.assertEqual(payload["exit_code"], 125)
            self.assertEqual(payload["non_green_reason"], "role_outcome_preflight_failed")
            self.assertEqual(payload["role_outcome_state"], "blocked")
            self.assertEqual(payload["role_outcome_reason_code"], "preexisting_semantic_draft")
            self.assertTrue(payload["role_outcome_readback_persisted"])
            self.assertFalse(child_marker.exists())

    def test_role_run_keeps_non_green_child_and_green_outcome_independent(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_role_outcome_non_green_") as tmpdir:
            root, env, _ = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
            plan_path = self._write_role_outcome_runtime_plan(root)
            draft = self._role_outcome_semantic_draft()
            coder_sid = SUCCESS_SIDS["coder"]
            command = (
                "planveyor_plan_set docs/plans/260101_0000_test_runtime.md >/dev/null && "
                f"planveyor_session_set coder {coder_sid} runner=codex >/dev/null && "
                "planveyor_coder() { "
                f"print -r -- {shlex.quote(draft)} >> {shlex.quote(str(plan_path))}; "
                "return 23; } && "
                "planveyor_role_run coder --json"
            )

            result = self._run(root, env, command)

            self.assertEqual(result.returncode, 23, result.stderr + result.stdout)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["state"], "failed")
            self.assertEqual(payload["exit_code"], 23)
            self.assertEqual(payload["role_outcome_state"], "finalized")
            self.assertEqual(payload["role_outcome_reason_code"], "ok")
            self.assertTrue(payload["role_outcome_readback_persisted"])

    def test_role_run_reports_semantic_diagnostic_without_recovery_mutation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_role_outcome_diagnostic_") as tmpdir:
            root, env, _ = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
            plan_path = self._write_role_outcome_runtime_plan(root)
            malformed = self._role_outcome_semantic_draft().replace(
                "scripts/test_planveyor_init_capture.py::worked",
                "N/A (why=no blocker).",
            )
            coder_sid = SUCCESS_SIDS["coder"]
            command = (
                "planveyor_plan_set docs/plans/260101_0000_test_runtime.md >/dev/null && "
                f"planveyor_session_set coder {coder_sid} runner=codex >/dev/null && "
                "planveyor_coder() { "
                f"print -r -- {shlex.quote(malformed)} >> {shlex.quote(str(plan_path))}; "
                "return 0; } && "
                "planveyor_role_run coder --json"
            )

            result = self._run(root, env, command)

            self.assertEqual(result.returncode, 126, result.stderr + result.stdout)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["state"], "success")
            self.assertEqual(payload["exit_code"], 0)
            self.assertEqual(payload["role_outcome_state"], "blocked")
            self.assertEqual(
                payload["role_outcome_reason_code"], "semantic_draft_invalid"
            )
            self.assertEqual(payload["role_outcome_diagnostic_state"], "invalid")
            self.assertEqual(
                payload["role_outcome_diagnostic_reason_code"],
                "semantic_draft_invalid",
            )
            self.assertEqual(payload["role_outcome_recovery_state"], "reject_required")
            self.assertEqual(
                payload["role_outcome_safe_action"],
                "reject_then_explicit_same_role_rerun",
            )
            diagnostic_path = root / payload["role_outcome_diagnostic_path"]
            self.assertTrue(diagnostic_path.is_file())
            self.assertEqual(stat.S_IMODE(diagnostic_path.stat().st_mode), 0o600)
            persisted = json.loads(Path(payload["receipt_path"]).read_text(encoding="utf-8"))
            self.assertFalse(any(key.startswith("role_outcome_") for key in persisted))
            plan_text = plan_path.read_text(encoding="utf-8")
            self.assertNotIn("- Role outcome rejection receipt", plan_text)
            self.assertNotIn("- Role outcome rerun started", plan_text)

    def test_role_run_recovery_tuple_is_one_shot_and_exactly_once(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_role_outcome_recovery_") as tmpdir:
            root, env, _ = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
            plan_path = self._write_role_outcome_runtime_plan(root)
            malformed = self._role_outcome_semantic_draft().replace(
                "scripts/test_planveyor_init_capture.py::worked",
                "N/A (why=no blocker).",
            )
            coder_sid = SUCCESS_SIDS["coder"]
            setup = (
                "planveyor_plan_set docs/plans/260101_0000_test_runtime.md >/dev/null && "
                f"planveyor_session_set coder {coder_sid} runner=codex >/dev/null && "
            )
            first = self._run(
                root,
                env,
                setup
                + "planveyor_coder() { "
                + f"print -r -- {shlex.quote(malformed)} >> {shlex.quote(str(plan_path))}; "
                + "return 0; } && planveyor_role_run coder --json",
            )
            self.assertEqual(first.returncode, 126, first.stderr + first.stdout)
            failed = json.loads(first.stdout)
            failed_output = (
                root / ".tmp" / "planveyor_role_runs" / str(failed["run_id"])
            )
            reject = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(REPO_ROOT / "scripts" / "role_outcome_receipt.py"),
                    "reject-rerun",
                    "--project-root",
                    str(root.resolve()),
                    "--plan",
                    "docs/plans/260101_0000_test_runtime.md",
                    "--role",
                    "coder",
                    "--run-id",
                    str(failed["run_id"]),
                    "--execution-receipt",
                    str(failed["receipt_path"]),
                    "--output-dir",
                    str(failed_output.resolve()),
                    "--format",
                    "json",
                ],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(reject.returncode, 0, reject.stderr + reject.stdout)
            recovery = json.loads(reject.stdout)
            rejection_hash = str(recovery["rejection_receipt_sha256"])
            fresh = self._role_outcome_semantic_draft()
            child_env_marker = root / ".tmp" / "recovery-env-leaked"
            second = self._run(
                root,
                env,
                setup
                + f"export PLANVEYOR_ROLE_OUTCOME_RECOVERY_OF_RUN_ID={shlex.quote(str(failed['run_id']))}; "
                + f"export PLANVEYOR_ROLE_OUTCOME_REJECTION_RECEIPT_SHA256={shlex.quote(rejection_hash)}; "
                + "planveyor_coder() { "
                + "[[ -z \"${PLANVEYOR_ROLE_OUTCOME_RECOVERY_OF_RUN_ID:-}\" && "
                + "-z \"${PLANVEYOR_ROLE_OUTCOME_REJECTION_RECEIPT_SHA256:-}\" ]] || "
                + f"touch {shlex.quote(str(child_env_marker))}; "
                + f"print -r -- {shlex.quote(fresh)} >> {shlex.quote(str(plan_path))}; "
                + "return 0; } && planveyor_role_run coder --json",
            )
            self.assertEqual(second.returncode, 0, second.stderr + second.stdout)
            rerun = json.loads(second.stdout)
            self.assertEqual(rerun["role_outcome_state"], "finalized")
            self.assertEqual(rerun["role_outcome_recovery_state"], "rerun_available")
            self.assertEqual(
                rerun["role_outcome_safe_action"], "continue_same_role_dispatch"
            )
            self.assertFalse(child_env_marker.exists())
            persisted = json.loads(Path(rerun["receipt_path"]).read_text(encoding="utf-8"))
            self.assertFalse(any(key.startswith("role_outcome_") for key in persisted))
            text = plan_path.read_text(encoding="utf-8")
            self.assertEqual(text.count("- Role outcome rejection receipt"), 1)
            self.assertEqual(text.count("- Role outcome rerun started"), 1)
            self.assertEqual(text.count("- Role outcome semantic draft"), 1)

            child_started = root / ".tmp" / "duplicate-child-started"
            duplicate = self._run(
                root,
                env,
                setup
                + f"export PLANVEYOR_ROLE_OUTCOME_RECOVERY_OF_RUN_ID={shlex.quote(str(failed['run_id']))}; "
                + f"export PLANVEYOR_ROLE_OUTCOME_REJECTION_RECEIPT_SHA256={shlex.quote(rejection_hash)}; "
                + f"planveyor_coder() {{ touch {shlex.quote(str(child_started))}; return 0; }} && "
                + "planveyor_role_run coder --json",
            )
            self.assertEqual(duplicate.returncode, 125, duplicate.stderr + duplicate.stdout)
            duplicate_payload = json.loads(duplicate.stdout)
            self.assertEqual(
                duplicate_payload["non_green_reason"],
                "role_outcome_recovery_preflight_failed",
            )
            self.assertEqual(duplicate_payload["process_start_outcome"], "not_started")
            self.assertEqual(
                duplicate_payload["role_outcome_recovery_state"], "unavailable"
            )
            self.assertFalse(child_started.exists())

            partial_started = root / ".tmp" / "partial-child-started"
            partial = self._run(
                root,
                env,
                setup
                + f"export PLANVEYOR_ROLE_OUTCOME_RECOVERY_OF_RUN_ID={shlex.quote(str(failed['run_id']))}; "
                + "unset PLANVEYOR_ROLE_OUTCOME_REJECTION_RECEIPT_SHA256; "
                + f"planveyor_coder() {{ touch {shlex.quote(str(partial_started))}; return 0; }} && "
                + "planveyor_role_run coder --json",
            )
            self.assertEqual(partial.returncode, 125, partial.stderr + partial.stdout)
            partial_payload = json.loads(partial.stdout)
            self.assertEqual(
                partial_payload["non_green_reason"],
                "role_outcome_recovery_preflight_failed",
            )
            self.assertFalse(partial_started.exists())

    def test_role_run_reports_invalid_outcome_helper_transport_without_starting_child(self) -> None:
        wrong_identity = {
            "schema_version": "role_outcome_preflight.v1",
            "state": "ready",
            "reason_code": "ok",
            "run_id": "wrong-run",
            "role": "coder",
            "lane": "coder",
            "target_plan": "docs/plans/260101_0000_test_runtime.md",
            "carrier_path": "docs/plans/260101_0000_test_runtime.md",
            "artifact_ref": "docs/plans/260101_0000_test_runtime.md::## Evidence",
            "forbidden_carrier_path": "docs/code_reviews/260101_0000_test_runtime.md",
            "semantic_draft_count": 0,
            "finalized_receipt_count": 0,
            "forbidden_carrier_hits": [],
        }
        cases = {
            "invalid_json": "print -r -- not-json",
            "wrong_identity": f"print -r -- {shlex.quote(json.dumps(wrong_identity))}",
        }
        for case, helper_body in cases.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory(
                prefix="planveyor_role_outcome_transport_"
            ) as tmpdir:
                root, env, _ = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
                self._write_role_outcome_runtime_plan(root)
                child_marker = root / ".tmp" / "child-started"
                coder_sid = SUCCESS_SIDS["coder"]
                command = (
                    "planveyor_plan_set docs/plans/260101_0000_test_runtime.md >/dev/null && "
                    f"planveyor_session_set coder {coder_sid} runner=codex >/dev/null && "
                    f"planveyor_coder() {{ touch {shlex.quote(str(child_marker))}; return 0; }} && "
                    f"_planveyor_role_outcome_helper_json() {{ {helper_body}; return 0; }} && "
                    "planveyor_role_run coder --json"
                )

                result = self._run(root, env, command)

                self.assertEqual(result.returncode, 126, result.stderr)
                payload = json.loads(result.stdout)
                self.assertEqual(payload["state"], "precondition_failed")
                self.assertEqual(payload["role_outcome_state"], "blocked")
                self.assertEqual(payload["role_outcome_reason_code"], "helper_output_invalid")
                self.assertFalse(payload["role_outcome_readback_persisted"])
                self.assertFalse(child_marker.exists())

    def test_role_run_lock_contention_is_fail_fast_and_preserves_winner_latest(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_role_run_lock_") as tmpdir:
            root, env, _ = self._prepare_repo(
                tmpdir,
                sid_map=SUCCESS_SIDS,
                runtime_mode="legacy_complete",
            )
            runtime_manifest = self._assert_legacy_complete_runtime_identity(root, env)
            self._write_runtime_plan(root, status="In progress")
            planner_sid = "00000000-0000-4000-8000-000000000330"
            setup = self._run(
                root,
                env,
                "planveyor_plan_set docs/plans/260101_0000_test_runtime.md >/dev/null && "
                "planveyor_runner_set planner codex >/dev/null && "
                f"planveyor_session_set planner {planner_sid} runner=codex >/dev/null",
            )
            self.assertEqual(setup.returncode, 0, setup.stderr)

            barrier = root / ".tmp" / "role-lock-release"
            wrapper_calls = root / ".tmp" / "role-lock-wrapper-calls"
            role_command = (
                "planveyor_planner() { "
                "print -r -- \"$$\" >> .tmp/role-lock-wrapper-calls; "
                "while [[ ! -f .tmp/role-lock-release ]]; do sleep 0.02; done; "
                "} && planveyor_role_run planner --json"
            )
            winner_shell = (
                f'export PATH={shlex.quote(env["PLANVEYOR_FAKE_CODEX_BIN"])}:$PATH; '
                f"source scripts/planveyor.zsh && {role_command}"
            )
            winner = subprocess.Popen(
                ["/bin/zsh", "-fc", winner_shell],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
            try:
                deadline = time.monotonic() + 10
                lock_ready = False
                while not lock_ready and time.monotonic() < deadline:
                    for ready_path in sorted(
                        (root / ".tmp" / "planveyor_role_runs").glob("*/lock.ready.json")
                    ):
                        ready_payload = json.loads(
                            ready_path.read_text(encoding="utf-8")
                        )
                        if (
                            ready_payload.get("state") == "acquired"
                            and ready_payload.get("parent_pid") == winner.pid
                        ):
                            lock_ready = True
                            break
                    if not lock_ready:
                        time.sleep(0.02)
                self.assertTrue(lock_ready, "winner did not acquire role lock")

                contender = self._run(root, env, role_command)
                self.assertEqual(contender.returncode, 125, contender.stderr)
                contender_payload = json.loads(contender.stdout)
                self.assertEqual(contender_payload["state"], "precondition_failed")
                self.assertEqual(contender_payload["process_start_outcome"], "not_started")
                self.assertEqual(contender_payload["exit_code"], 125)
                self.assertEqual(contender_payload["non_green_reason"], "role_run_lock_contended")
                self.assertEqual(contender_payload["readback_state"], "ok")
                self.assertNotIn("business_work_executed", contender_payload)
            finally:
                barrier.touch()
                winner_stdout, winner_stderr = winner.communicate(timeout=15)
            self.assertEqual(winner.returncode, 0, winner_stderr)
            self.assertEqual(len(wrapper_calls.read_text(encoding="utf-8").splitlines()), 1)
            winner_payload = json.loads(winner_stdout)
            self.assertEqual(winner_payload["state"], "success")
            self.assertNotEqual(winner_payload["run_id"], contender_payload["run_id"])
            latest = Path(winner_payload["latest_receipt_path"]).read_text(encoding="utf-8")
            self.assertIn(f"run_id={winner_payload['run_id']}", latest)
            self.assertNotIn(f"run_id={contender_payload['run_id']}", latest)
            self.assertTrue(Path(contender_payload["receipt_path"]).exists())
            self._assert_legacy_complete_runtime_identity(
                root,
                env,
                expected_manifest=runtime_manifest,
            )

    def test_role_run_supervisor_closes_inherited_stdin(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_role_run_stdin_") as tmpdir:
            root, env, _ = self._prepare_repo(
                tmpdir,
                sid_map=SUCCESS_SIDS,
                runtime_mode="legacy_complete",
            )
            runtime_manifest = self._assert_legacy_complete_runtime_identity(root, env)
            output_dir = root / ".tmp" / "stdin-probe"
            output_dir.mkdir(parents=True, exist_ok=True)
            wrapper_source = output_dir / "wrapper.zsh"
            probe_path = output_dir / "stdin.bin"
            stdout_path = output_dir / "stdout.log"
            stderr_path = output_dir / "stderr.log"
            wrapper_source.write_text(
                "planveyor_test_stdin_probe() { cat > \"$PLANVEYOR_STDIN_PROBE\"; }\n",
                encoding="utf-8",
            )

            result = self._run(
                root,
                env,
                "_planveyor_role_run_supervise "
                f"{shlex.quote(str(root.resolve()))} planveyor_test_stdin_probe "
                f"{shlex.quote(str(wrapper_source))} "
                f"{shlex.quote(str(stdout_path))} {shlex.quote(str(stderr_path))} 5 "
                f"PLANVEYOR_STDIN_PROBE={shlex.quote(str(probe_path))}",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["process_started"])
            self.assertEqual(payload["exit_code"], 0)
            self.assertFalse(payload["timed_out"])
            self.assertEqual(probe_path.read_bytes(), b"")
            self._assert_legacy_complete_runtime_identity(
                root,
                env,
                expected_manifest=runtime_manifest,
            )

    def test_role_run_rejects_symlinked_managed_root_and_restores_caller_umask(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_role_run_symlink_") as tmpdir:
            root, env, log_dir = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
            self._write_runtime_plan(root, status="In progress")
            planner_sid = "00000000-0000-4000-8000-000000000331"
            (root / ".tmp").mkdir(exist_ok=True)
            outside = root / "outside-role-runs"
            outside.mkdir()
            (root / ".tmp" / "planveyor_role_runs").symlink_to(outside, target_is_directory=True)

            result = self._run(
                root,
                env,
                "planveyor_plan_set docs/plans/260101_0000_test_runtime.md >/dev/null && "
                "planveyor_runner_set planner codex >/dev/null && "
                f"planveyor_session_set planner {planner_sid} runner=codex >/dev/null && "
                "umask 002; before=$(umask); "
                "payload=$(planveyor_role_run planner --json); rc=$?; after=$(umask); "
                "print -r -- \"$payload\"; print -r -- \"UMASK=$before:$after:$rc\"",
            )
            lines = result.stdout.splitlines()
            payload = json.loads(lines[0])
            self.assertEqual(payload["error"], "unsafe_managed_path")
            self.assertFalse(payload["mutation_performed"])
            self.assertEqual(payload["session_key"], "planner")
            umask_before, umask_after, rc = lines[1].split("=", 1)[1].split(":")
            self.assertEqual(umask_before, umask_after)
            self.assertEqual(rc, "125")
            self.assertFalse((root / ".planveyor.role_runs").exists())
            self.assertFalse((root / ".planveyor.run_receipt.role.planner").exists())
            self.assertEqual(self._codex_calls(log_dir), [])

        with tempfile.TemporaryDirectory(prefix="planveyor_role_run_escape_") as tmpdir:
            root, env, log_dir = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
            self._write_runtime_plan(root, status="In progress")
            planner_sid = "00000000-0000-4000-8000-000000000331"
            result = self._run(
                root,
                env,
                "planveyor_plan_set docs/plans/260101_0000_test_runtime.md >/dev/null && "
                "planveyor_runner_set planner codex >/dev/null && "
                f"planveyor_session_set planner {planner_sid} runner=codex >/dev/null && "
                "_planveyor_role_runner_preflight_normalize() { "
                "print -r -- 'role=planner;session_key=../../escaped;wrapper=planveyor_planner;runner_role=planner'; "
                "} && planveyor_role_run planner --json",
            )
            self.assertEqual(result.returncode, 125, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["error"], "unsafe_managed_path")
            self.assertEqual(payload["reason"], "managed_root_escape")
            self.assertFalse(payload["mutation_performed"])
            self.assertFalse((root / "escaped").exists())
            self.assertEqual(self._codex_calls(log_dir), [])

        with tempfile.TemporaryDirectory(prefix="planveyor_role_run_umask_") as tmpdir:
            root, env, _ = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
            self._write_runtime_plan(root, status="In progress")
            planner_sid = "00000000-0000-4000-8000-000000000332"
            result = self._run(
                root,
                env,
                "planveyor_plan_set docs/plans/260101_0000_test_runtime.md >/dev/null && "
                "planveyor_runner_set planner codex >/dev/null && "
                f"planveyor_session_set planner {planner_sid} runner=codex >/dev/null && "
                "planveyor_planner() { :; } && umask 002; before=$(umask); "
                "planveyor_role_run planner --json >/dev/null; rc=$?; after=$(umask); "
                "print -r -- \"$before:$after:$rc\"",
            )
            umask_before, umask_after, rc = result.stdout.strip().split(":")
            self.assertEqual(umask_before, umask_after)
            self.assertEqual(rc, "0")

    def test_role_run_control_markers_are_nofollow_bounded_and_interrupt_safe(self) -> None:
        for marker_name, expected_reason in (
            ("transaction.done", "transaction_done_publication_failed"),
            ("lock.release", "lock_release_failed"),
        ):
            with self.subTest(marker=marker_name), tempfile.TemporaryDirectory(
                prefix=f"planveyor_role_run_marker_{marker_name.replace('.', '_')}_"
            ) as tmpdir:
                root, env, _ = self._prepare_repo(
                    tmpdir,
                    sid_map=SUCCESS_SIDS,
                    runtime_mode="legacy_complete",
                )
                runtime_manifest = self._assert_legacy_complete_runtime_identity(root, env)
                self._write_runtime_plan(root, status="In progress")
                planner_sid = "00000000-0000-4000-8000-000000000337"
                target = root / "marker-target.txt"
                target.write_text("preserve-me", encoding="utf-8")
                timing_root = root / ".tmp" / "control-marker-timing"
                timing_root.mkdir(parents=True)
                fault_timestamp = timing_root / f"{marker_name}.fault.monotonic"
                close_timestamp = timing_root / f"{marker_name}.close.monotonic"
                fault_writer = self._monotonic_timestamp_writer(fault_timestamp, env)
                close_writer = self._monotonic_timestamp_writer(close_timestamp, env)
                whole_command_started = time.monotonic()
                result = self._run(
                    root,
                    env,
                    "planveyor_plan_set docs/plans/260101_0000_test_runtime.md >/dev/null && "
                    "planveyor_runner_set planner codex >/dev/null && "
                    f"planveyor_session_set planner {planner_sid} runner=codex >/dev/null && "
                    "planveyor_planner() { "
                    f"{fault_writer}; "
                    f"ln -s {shlex.quote(str(target))} \"$PLANVEYOR_ROLE_RUN_OUTPUT_DIR/{marker_name}\"; "
                    "} && planveyor_role_run planner --json; role_rc=$?; "
                    f"{close_writer}; close_rc=$?; "
                    '(( close_rc == 0 )) || exit "$close_rc"; exit "$role_rc"',
                )
                whole_command_elapsed = time.monotonic() - whole_command_started
                self.assertEqual(result.returncode, 126, result.stderr)
                self.assertLess(whole_command_elapsed, 60.0, result.stderr)
                fault_started = self._read_monotonic_timestamp(
                    fault_timestamp, f"{marker_name} fault timestamp"
                )
                closed_at = self._read_monotonic_timestamp(
                    close_timestamp, f"{marker_name} close timestamp"
                )
                self.assertGreaterEqual(closed_at, fault_started)
                self.assertLess(
                    closed_at - fault_started,
                    5.0,
                    f"whole_command_elapsed={whole_command_elapsed:.3f}s; marker={marker_name}",
                )
                payload = json.loads(result.stdout)
                self.assertEqual(payload["readback_state"], "blocked")
                self.assertEqual(payload["readback_reason"], expected_reason)
                self.assertEqual(target.read_text(encoding="utf-8"), "preserve-me")
                marker = Path(payload["stdout_path"]).parent / marker_name
                self.assertTrue(marker.is_symlink())
                persisted = json.loads(Path(payload["receipt_path"]).read_text(encoding="utf-8"))
                self.assertEqual(persisted["state"], "success")
                self.assertEqual(persisted["exit_code"], 0)
                self._assert_legacy_complete_runtime_identity(
                    root,
                    env,
                    expected_manifest=runtime_manifest,
                )

        with tempfile.TemporaryDirectory(prefix="planveyor_role_run_release_symlink_lock_") as tmpdir:
            root, env, _ = self._prepare_repo(
                tmpdir,
                sid_map=SUCCESS_SIDS,
                runtime_mode="legacy_complete",
            )
            runtime_manifest = self._assert_legacy_complete_runtime_identity(root, env)
            probe_root = root / ".tmp" / "release-symlink-probe"
            owner_dir = probe_root / "owner"
            contender_dir = probe_root / "contender"
            owner_dir.mkdir(parents=True)
            contender_dir.mkdir(parents=True)
            lock_path = probe_root / "planner.lock"
            owner_ready = owner_dir / "lock.ready.json"
            owner_release = owner_dir / "lock.release"
            contender_ready = contender_dir / "lock.ready.json"
            contender_release = contender_dir / "lock.release"
            target = root / "release-target.txt"
            target.write_text("preserve-me", encoding="utf-8")
            release_symlink_probe = self._run(
                root,
                env,
                f"_planveyor_role_run_lock_holder {shlex.quote(str(lock_path))} "
                f"{shlex.quote(str(owner_ready))} {shlex.quote(str(owner_release))} \"$$\" >/dev/null 2>&1 & "
                "owner=$!; i=0; while (( i < 500 )) && [[ ! -f "
                f"{shlex.quote(str(owner_ready))} ]]; do sleep 0.01; (( i += 1 )); done; "
                f"ln -s {shlex.quote(str(target))} {shlex.quote(str(owner_release))}; sleep 0.1; "
                f"_planveyor_role_run_lock_holder {shlex.quote(str(lock_path))} "
                f"{shlex.quote(str(contender_ready))} {shlex.quote(str(contender_release))} \"$$\" >/dev/null 2>&1 & "
                "contender=$!; i=0; while (( i < 500 )) && [[ ! -f "
                f"{shlex.quote(str(contender_ready))} ]]; do sleep 0.01; (( i += 1 )); done; "
                f"cat {shlex.quote(str(contender_ready))}; wait \"$contender\"; "
                f"owner_holder=$(_planveyor_py_any -c 'import json; print(json.load(open(\"{owner_ready}\"))[\"holder_pid\"])'); "
                f"_planveyor_role_run_lock_release {shlex.quote(str(owner_release))} \"$owner\" \"$owner_holder\" || true",
            )
            self.assertEqual(release_symlink_probe.returncode, 0, release_symlink_probe.stderr)
            self.assertEqual(json.loads(release_symlink_probe.stdout)["state"], "contended")
            self.assertEqual(target.read_text(encoding="utf-8"), "preserve-me")
            self._assert_legacy_complete_runtime_identity(
                root,
                env,
                expected_manifest=runtime_manifest,
            )

        for parent_state in ("missing",):
            with self.subTest(release_parent=parent_state), tempfile.TemporaryDirectory(
                prefix=f"planveyor_role_run_release_{parent_state}_"
            ) as tmpdir:
                root, env, _ = self._prepare_repo(
                    tmpdir,
                    sid_map=SUCCESS_SIDS,
                    runtime_mode="legacy_complete",
                )
                runtime_manifest = self._assert_legacy_complete_runtime_identity(root, env)
                self._write_runtime_plan(root, status="In progress")
                planner_sid = "00000000-0000-4000-8000-000000000338"
                mutate_parent = 'rm -rf -- "$PLANVEYOR_ROLE_RUN_OUTPUT_DIR"'
                first_result = root / "release-failure-first.json"
                second_result = root / "release-failure-second.json"
                timing_root = root / ".tmp" / "control-marker-timing"
                timing_root.mkdir(parents=True)
                first_fault_timestamp = timing_root / "release-parent-first.fault.monotonic"
                first_close_timestamp = timing_root / "release-parent-first.close.monotonic"
                second_start_timestamp = timing_root / "release-parent-second.start.monotonic"
                second_close_timestamp = timing_root / "release-parent-second.close.monotonic"
                first_fault_writer = self._monotonic_timestamp_writer(
                    first_fault_timestamp, env
                )
                first_close_writer = self._monotonic_timestamp_writer(
                    first_close_timestamp, env
                )
                second_start_writer = self._monotonic_timestamp_writer(
                    second_start_timestamp, env
                )
                second_close_writer = self._monotonic_timestamp_writer(
                    second_close_timestamp, env
                )
                whole_command_started = time.monotonic()
                result = self._run(
                    root,
                    env,
                    "planveyor_plan_set docs/plans/260101_0000_test_runtime.md >/dev/null && "
                    "planveyor_runner_set planner codex >/dev/null && "
                    f"planveyor_session_set planner {planner_sid} runner=codex >/dev/null && "
                    f"planveyor_planner() {{ {first_fault_writer}; {mutate_parent}; }}; "
                    f"planveyor_role_run planner --json > {shlex.quote(str(first_result))}; first_rc=$?; "
                    f"{first_close_writer}; first_close_rc=$?; "
                    '(( first_close_rc == 0 )) || exit "$first_close_rc"; '
                    f"planveyor_planner() {{ {second_start_writer}; :; }}; "
                    f"planveyor_role_run planner --json > {shlex.quote(str(second_result))}; second_rc=$?; "
                    f"{second_close_writer}; second_close_rc=$?; "
                    '(( second_close_rc == 0 )) || exit "$second_close_rc"; '
                    'print -r -- "$first_rc:$second_rc"',
                )
                whole_command_elapsed = time.monotonic() - whole_command_started
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertLess(whole_command_elapsed, 60.0, result.stderr)
                first_fault_started = self._read_monotonic_timestamp(
                    first_fault_timestamp, "release-parent first fault timestamp"
                )
                first_closed_at = self._read_monotonic_timestamp(
                    first_close_timestamp, "release-parent first close timestamp"
                )
                second_started_at = self._read_monotonic_timestamp(
                    second_start_timestamp, "release-parent second start timestamp"
                )
                second_closed_at = self._read_monotonic_timestamp(
                    second_close_timestamp, "release-parent second close timestamp"
                )
                self.assertGreaterEqual(first_closed_at, first_fault_started)
                self.assertGreaterEqual(second_closed_at, second_started_at)
                self.assertLess(
                    first_closed_at - first_fault_started,
                    5.0,
                    f"whole_command_elapsed={whole_command_elapsed:.3f}s; call=first_fault",
                )
                self.assertLess(
                    second_closed_at - second_started_at,
                    5.0,
                    f"whole_command_elapsed={whole_command_elapsed:.3f}s; call=retry",
                )
                self.assertEqual(result.stdout.strip(), "126:0")
                payload = json.loads(first_result.read_text(encoding="utf-8"))
                self.assertEqual(payload["readback_state"], "blocked")
                self.assertEqual(payload["readback_reason"], "lock_release_failed")
                self.assertTrue(Path(payload["receipt_path"]).exists())
                retry_payload = json.loads(second_result.read_text(encoding="utf-8"))
                self.assertEqual(retry_payload["state"], "success")
                self.assertEqual(retry_payload["readback_state"], "ok")
                output_dir = Path(payload["stdout_path"]).parent
                if output_dir.exists():
                    output_dir.chmod(0o700)
                self._assert_legacy_complete_runtime_identity(
                    root,
                    env,
                    expected_manifest=runtime_manifest,
                )

        with tempfile.TemporaryDirectory(prefix="planveyor_role_run_interrupted_holder_") as tmpdir:
            root, env, _ = self._prepare_repo(
                tmpdir,
                sid_map=SUCCESS_SIDS,
                runtime_mode="legacy_complete",
            )
            runtime_manifest = self._assert_legacy_complete_runtime_identity(root, env)
            lock_root = root / ".tmp" / "holder-probe"
            first_dir = lock_root / "first"
            second_dir = lock_root / "second"
            first_dir.mkdir(parents=True)
            second_dir.mkdir(parents=True)
            lock_path = lock_root / "planner.lock"
            ready_path = first_dir / "lock.ready.json"
            release_path = first_dir / "lock.release"
            holder_pid_path = first_dir / "holder.pid"
            parent_command = "\n".join(
                (
                    "source scripts/planveyor.zsh",
                    f"_planveyor_role_run_lock_holder {shlex.quote(str(lock_path))} "
                    f"{shlex.quote(str(ready_path))} {shlex.quote(str(release_path))} \"$$\" >/dev/null 2>&1 &",
                    "holder=$!",
                    f"print -r -- \"$holder\" > {shlex.quote(str(holder_pid_path))}",
                    'wait "$holder"',
                )
            )
            parent = subprocess.Popen(
                ["/bin/zsh", "-fc", parent_command],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
            deadline = time.monotonic() + 5
            while not ready_path.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(ready_path.exists(), "first lock holder did not publish readiness")
            self.assertEqual(json.loads(ready_path.read_text(encoding="utf-8"))["state"], "acquired")
            holder_pid = int(holder_pid_path.read_text(encoding="utf-8"))
            parent.terminate()
            parent.communicate(timeout=5)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                try:
                    os.kill(holder_pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.02)
            else:
                self.fail("lock holder survived interrupted caller")

            second_ready = second_dir / "lock.ready.json"
            second_release = second_dir / "lock.release"
            reacquire = self._run(
                root,
                env,
                f"_planveyor_role_run_lock_holder {shlex.quote(str(lock_path))} "
                f"{shlex.quote(str(second_ready))} {shlex.quote(str(second_release))} \"$$\" >/dev/null 2>&1 & "
                "holder=$!; i=0; while (( i < 500 )) && [[ ! -f "
                f"{shlex.quote(str(second_ready))} ]]; do sleep 0.01; (( i += 1 )); done; "
                f"cat {shlex.quote(str(second_ready))}; "
                f"actual_holder=$(_planveyor_py_any -c 'import json; print(json.load(open(\"{second_ready}\"))[\"holder_pid\"])'); "
                f"_planveyor_role_run_lock_release {shlex.quote(str(second_release))} \"$holder\" \"$actual_holder\"",
            )
            self.assertEqual(reacquire.returncode, 0, reacquire.stderr)
            self.assertEqual(json.loads(reacquire.stdout)["state"], "acquired")
            self._assert_legacy_complete_runtime_identity(
                root,
                env,
                expected_manifest=runtime_manifest,
            )

    def test_role_run_atomic_failure_transport_preserves_primary_authority(self) -> None:
        primary_stages = ("temp_create", "write", "flush", "fsync", "replace", "dir_fsync")
        for stage in primary_stages:
            with self.subTest(stage=stage), tempfile.TemporaryDirectory(
                prefix=f"planveyor_role_run_primary_{stage}_"
            ) as tmpdir:
                root, env, _ = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
                self._write_runtime_plan(root, status="In progress")
                planner_sid = "00000000-0000-4000-8000-000000000333"
                result = self._run(
                    root,
                    env,
                    "planveyor_plan_set docs/plans/260101_0000_test_runtime.md >/dev/null && "
                    "planveyor_runner_set planner codex >/dev/null && "
                    f"planveyor_session_set planner {planner_sid} runner=codex >/dev/null && "
                    "planveyor_planner() { :; } && "
                    f"_planveyor_role_run_test_fail_stage() {{ [[ \"$1\" == primary ]] && print -r -- {stage}; }} && "
                    "planveyor_role_run planner --json",
                )
                self.assertEqual(result.returncode, 126, result.stderr)
                payload = json.loads(result.stdout)
                self.assertEqual(payload["error"], "primary_publication_failed")
                self.assertFalse(payload["mutation_performed"])
                self.assertFalse(Path(payload["receipt_path"]).exists())
                self.assertFalse((root / ".planveyor.run_receipt.role.planner").exists())
                self.assertEqual(list((root / ".planveyor.role_runs").glob(".*.tmp-*")), [])

        for stage in primary_stages:
            with self.subTest(latest_stage=stage), tempfile.TemporaryDirectory(
                prefix=f"planveyor_role_run_latest_{stage}_"
            ) as tmpdir:
                root, env, _ = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
                self._write_runtime_plan(root, status="In progress")
                planner_sid = "00000000-0000-4000-8000-000000000334"
                latest_path = root / ".planveyor.run_receipt.role.planner"
                old_latest = b"schema_version=role_execution_receipt.v1\nrun_id=old-owner\n"
                latest_path.write_bytes(old_latest)
                result = self._run(
                    root,
                    env,
                    "planveyor_plan_set docs/plans/260101_0000_test_runtime.md >/dev/null && "
                    "planveyor_runner_set planner codex >/dev/null && "
                    f"planveyor_session_set planner {planner_sid} runner=codex >/dev/null && "
                    "planveyor_planner() { :; } && "
                    f"_planveyor_role_run_test_fail_stage() {{ [[ \"$1\" == latest ]] && print -r -- {stage}; }} && "
                    "planveyor_role_run planner --json",
                )
                self.assertEqual(result.returncode, 126, result.stderr)
                payload = json.loads(result.stdout)
                self.assertEqual(payload["readback_reason"], "latest_publication_failed")
                self.assertEqual(latest_path.read_bytes(), old_latest)
                self.assertEqual(stat.S_IMODE(latest_path.stat().st_mode), 0o600)
                primary_path = Path(payload["receipt_path"])
                primary_bytes = primary_path.read_bytes()
                persisted = json.loads(primary_bytes)
                self.assertEqual(persisted["state"], "success")
                self.assertEqual(persisted["exit_code"], 0)
                self.assertNotIn("readback_state", persisted)
                self.assertNotIn("readback_reason", persisted)
                self.assertNotIn(b"business_work_executed", primary_bytes)
                self.assertEqual(list(root.glob(".*.tmp-*")), [])

        for failure_kind in ("readback", "prune"):
            with self.subTest(failure_kind=failure_kind), tempfile.TemporaryDirectory(
                prefix=f"planveyor_role_run_{failure_kind}_"
            ) as tmpdir:
                root, env, _ = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
                self._write_runtime_plan(root, status="In progress")
                planner_sid = "00000000-0000-4000-8000-000000000335"
                hook = (
                    "_planveyor_role_run_check_latest_json() { print -r -- "
                    "'{'\"'\"'readback_state'\"'\"':'\"'\"'blocked'\"'\"','\"'\"'reason'\"'\"':'\"'\"'synthetic'\"'\"'}'; return 1; }"
                    if failure_kind == "readback"
                    else "_planveyor_role_run_test_prune_failure() { return 0; }"
                )
                result = self._run(
                    root,
                    env,
                    "planveyor_plan_set docs/plans/260101_0000_test_runtime.md >/dev/null && "
                    "planveyor_runner_set planner codex >/dev/null && "
                    f"planveyor_session_set planner {planner_sid} runner=codex >/dev/null && "
                    f"planveyor_planner() {{ :; }} && {hook} && planveyor_role_run planner --json",
                )
                self.assertEqual(result.returncode, 126, result.stderr)
                payload = json.loads(result.stdout)
                expected = "receipt_readback_failed" if failure_kind == "readback" else "synthetic_prune_failure"
                self.assertEqual(payload["readback_reason"], expected)
                self.assertEqual(
                    payload["retention_prune_state"],
                    "not_run" if failure_kind == "readback" else "blocked",
                )
                self.assertEqual(
                    payload["retention_prune_reason"],
                    expected,
                )
                self.assertEqual(payload["retention_prune_paths"], [])
                self.assertFalse(payload["retention_prune_mutation_performed"])
                persisted = json.loads(Path(payload["receipt_path"]).read_text(encoding="utf-8"))
                self.assertEqual(persisted["state"], "success")
                self.assertEqual(persisted["exit_code"], 0)
                self.assertNotIn("readback_state", persisted)
                self.assertNotIn("readback_reason", persisted)

    def test_role_run_retention_is_deterministic_paired_and_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_role_run_retention_") as tmpdir:
            root, env, _ = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
            self._write_runtime_plan(root, status="In progress")
            planner_sid = "00000000-0000-4000-8000-000000000336"
            receipt_root = root / ".planveyor.role_runs"
            output_root = root / ".tmp" / "planveyor_role_runs"
            receipt_root.mkdir(parents=True)
            output_root.mkdir(parents=True)
            historical_ids = [f"historical-{index:02d}" for index in range(23)]
            for index, run_id in enumerate(historical_ids):
                payload = {
                    "schema_version": "role_execution_receipt.v1",
                    "run_id": run_id,
                    "session_key": "planner",
                    "receipt_written_at": "2026-01-01T00:00:00Z",
                    "state": "success" if index % 2 == 0 else "failed",
                }
                (receipt_root / f"{run_id}.json").write_text(
                    json.dumps(payload), encoding="utf-8"
                )
                if index != 0:
                    run_dir = output_root / run_id
                    run_dir.mkdir()
                    (run_dir / "stdout.log").write_text("private log", encoding="utf-8")

            base_command = (
                "planveyor_plan_set docs/plans/260101_0000_test_runtime.md >/dev/null && "
                "planveyor_runner_set planner codex >/dev/null && "
                f"planveyor_session_set planner {planner_sid} runner=codex >/dev/null && "
                "planveyor_planner() { :; } && planveyor_role_run planner --json"
            )
            first = self._run(root, env, base_command)
            self.assertEqual(first.returncode, 0, first.stderr)
            for run_id in historical_ids[:4]:
                self.assertFalse((receipt_root / f"{run_id}.json").exists(), run_id)
                self.assertFalse((output_root / run_id).exists(), run_id)
            for run_id in historical_ids[4:]:
                self.assertTrue((receipt_root / f"{run_id}.json").exists(), run_id)
                self.assertEqual(
                    stat.S_IMODE((receipt_root / f"{run_id}.json").stat().st_mode),
                    0o600,
                )
                if (output_root / run_id).exists():
                    self.assertEqual(stat.S_IMODE((output_root / run_id).stat().st_mode), 0o700)
                    self.assertEqual(
                        stat.S_IMODE((output_root / run_id / "stdout.log").stat().st_mode),
                        0o600,
                    )

            second = self._run(root, env, base_command)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertFalse((receipt_root / "historical-04.json").exists())
            self.assertFalse((output_root / "historical-04").exists())
            self.assertEqual(len(list(receipt_root.glob("*.json"))), 20)

            active_dir = output_root / "active-without-primary"
            active_dir.mkdir()
            (active_dir / "lock.ready.json").write_text(
                json.dumps(
                    {
                        "state": "acquired",
                        "holder_pid": os.getpid(),
                        "parent_pid": os.getpid(),
                    }
                ),
                encoding="utf-8",
            )
            latest_path = root / ".planveyor.run_receipt.role.planner"
            active_probe = self._run(
                root,
                env,
                "_planveyor_role_run_prune "
                f"{shlex.quote(str(receipt_root))} {shlex.quote(str(output_root))} "
                f"planner active-probe {shlex.quote(str(latest_path))}",
            )
            self.assertEqual(active_probe.returncode, 0, active_probe.stderr)
            (active_dir / "transaction.done").touch()
            completed_probe = self._run(
                root,
                env,
                "_planveyor_role_run_prune "
                f"{shlex.quote(str(receipt_root))} {shlex.quote(str(output_root))} "
                f"planner active-probe {shlex.quote(str(latest_path))}",
            )
            self.assertNotEqual(completed_probe.returncode, 0)
            completed_probe_payload = json.loads(completed_probe.stdout)
            self.assertEqual(
                completed_probe_payload["reason"],
                "unclassified_orphan_output_dir",
            )
            self.assertIn(
                active_dir.resolve(),
                {Path(path).resolve() for path in completed_probe_payload["paths"]},
            )
            self.assertEqual(
                completed_probe_payload["affected_paths"],
                sorted(set(completed_probe_payload["affected_paths"])),
            )
            self.assertFalse(completed_probe_payload["mutation_performed"])
            shutil.rmtree(active_dir)

            production_orphans = [
                output_root / "empty",
                output_root / "probe_deadbeef",
                output_root / "20260719T000000Z_planner_123_456",
            ]
            for production_orphan in production_orphans:
                production_orphan.mkdir()
            orphan_blocked = self._run(root, env, base_command)
            self.assertEqual(orphan_blocked.returncode, 126, orphan_blocked.stderr)
            orphan_blocked_payload = json.loads(orphan_blocked.stdout)
            self.assertEqual(
                orphan_blocked_payload["readback_reason"],
                "unclassified_orphan_output_dir",
            )
            self.assertEqual(orphan_blocked_payload["retention_prune_state"], "blocked")
            self.assertEqual(
                orphan_blocked_payload["retention_prune_reason"],
                "unclassified_orphan_output_dir",
            )
            self.assertFalse(
                orphan_blocked_payload["retention_prune_mutation_performed"]
            )
            mapped_paths = {
                Path(path).resolve()
                for path in orphan_blocked_payload["retention_prune_paths"]
            }
            for production_orphan in production_orphans:
                self.assertIn(production_orphan.resolve(), mapped_paths)
                self.assertTrue(production_orphan.is_dir())
                production_orphan.rmdir()

            remaining_before = {path.name for path in receipt_root.glob("*.json")}
            malformed = receipt_root / "malformed.json"
            malformed.write_text("{not-json", encoding="utf-8")
            symlink_receipt = receipt_root / "symlink.json"
            symlink_receipt.symlink_to(next(receipt_root.glob("*.json")))
            orphan = output_root / "orphan-output"
            orphan.mkdir()
            blocked = self._run(root, env, base_command)
            self.assertEqual(blocked.returncode, 126, blocked.stderr)
            blocked_payload = json.loads(blocked.stdout)
            self.assertEqual(blocked_payload["readback_reason"], "unclassified_carriers")
            self.assertEqual(blocked_payload["retention_prune_state"], "blocked")
            self.assertEqual(blocked_payload["retention_prune_reason"], "unclassified_carriers")
            self.assertEqual(
                blocked_payload["retention_prune_paths"],
                sorted(set(blocked_payload["retention_prune_paths"])),
            )
            self.assertIn(str(malformed.resolve()), blocked_payload["retention_prune_paths"])
            self.assertIn(
                str(symlink_receipt.parent.resolve() / symlink_receipt.name),
                blocked_payload["retention_prune_paths"],
            )
            self.assertIn(str(orphan.resolve()), blocked_payload["retention_prune_paths"])
            self.assertFalse(blocked_payload["retention_prune_mutation_performed"])
            self.assertTrue(remaining_before.issubset({path.name for path in receipt_root.glob("*.json")}))
            self.assertTrue(malformed.exists())
            self.assertTrue(symlink_receipt.is_symlink())
            self.assertTrue(orphan.exists())

    def test_role_run_retention_outer_mapping_uses_only_authoritative_prune_fields(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_role_run_retention_mapping_") as tmpdir:
            root, env, _ = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
            self._write_runtime_plan(root, status="In progress")
            planner_sid = "00000000-0000-4000-8000-000000000337"
            affected_paths = [
                str(root.resolve() / ".planveyor.role_runs" / ".prune-txn-a.committed"),
                str(root.resolve() / ".tmp" / "planveyor_role_runs" / ".prune-txn-a.output"),
            ]
            prune_payload = {
                "ok": False,
                "reason": "committed_cleanup_pending",
                "affected_paths": affected_paths,
                "mutation_performed": True,
                "pruned": ["must-not-be-mapped-as-a-path"],
                "recovered": [{"run_id": "also-not-a-path", "action": "cleanup_completed"}],
                "cleanup_pending_paths": ["/optional-key-must-not-be-unioned"],
            }
            result = self._run(
                root,
                env,
                "planveyor_plan_set docs/plans/260101_0000_test_runtime.md >/dev/null && "
                "planveyor_runner_set planner codex >/dev/null && "
                f"planveyor_session_set planner {planner_sid} runner=codex >/dev/null && "
                "planveyor_planner() { :; } && "
                "_planveyor_role_run_prune() { "
                f"print -r -- {shlex.quote(json.dumps(prune_payload, sort_keys=True))}; "
                "return 1; "
                "} && planveyor_role_run planner --json",
            )
            self.assertEqual(result.returncode, 126, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["readback_reason"], "committed_cleanup_pending")
            self.assertEqual(payload["retention_prune_state"], "blocked")
            self.assertEqual(payload["retention_prune_reason"], "committed_cleanup_pending")
            self.assertEqual(payload["retention_prune_paths"], affected_paths)
            self.assertTrue(payload["retention_prune_mutation_performed"])
            self.assertNotIn("must-not-be-mapped-as-a-path", payload["retention_prune_paths"])
            self.assertNotIn("/optional-key-must-not-be-unioned", payload["retention_prune_paths"])

            primary_bytes = Path(payload["receipt_path"]).read_bytes()
            persisted = json.loads(primary_bytes)
            self.assertNotIn("retention_prune_state", persisted)
            self.assertNotIn("retention_prune_reason", persisted)
            self.assertNotIn("retention_prune_paths", persisted)
            self.assertNotIn("retention_prune_mutation_performed", persisted)

    def test_role_run_retention_pair_faults_roll_back_and_report_affected_run(self) -> None:
        def prepare_fixture(
            tmpdir: str,
        ) -> tuple[Path, dict[str, str], Path, Path, list[str], Path, Path, Path, Path]:
            root, env, _ = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
            receipt_root = root / ".planveyor.role_runs"
            output_root = root / ".tmp" / "planveyor_role_runs"
            receipt_root.mkdir(parents=True)
            output_root.mkdir(parents=True)
            run_ids = [f"historical-{index:02d}" for index in range(21)]
            for run_id in run_ids:
                (receipt_root / f"{run_id}.json").write_text(
                    json.dumps(
                        {
                            "schema_version": "role_execution_receipt.v1",
                            "run_id": run_id,
                            "session_key": "planner",
                            "receipt_written_at": "2026-01-01T00:00:00Z",
                            "state": "success",
                        }
                    ),
                    encoding="utf-8",
                )
            oldest_run_id = run_ids[0]
            oldest_receipt = receipt_root / f"{oldest_run_id}.json"
            oldest_output = output_root / oldest_run_id
            oldest_output.mkdir()
            oldest_log = oldest_output / "stdout.log"
            oldest_log.write_text("preserve-on-recovery", encoding="utf-8")
            latest_path = root / ".planveyor.run_receipt.role.planner"
            latest_path.write_text(
                f"schema_version=role_execution_receipt.v1\nrun_id={run_ids[-1]}\n",
                encoding="utf-8",
            )
            return (
                root,
                env,
                receipt_root,
                output_root,
                run_ids,
                oldest_receipt,
                oldest_output,
                oldest_log,
                latest_path,
            )

        def prune_command(
            receipt_root: Path,
            output_root: Path,
            latest_path: Path,
            *,
            hook: str = "",
            stage: str = "",
        ) -> str:
            prefix = ""
            if hook:
                prefix = f"{hook}() {{ print -r -- {stage}; }}; "
            return (
                prefix
                + f"_planveyor_role_run_prune {shlex.quote(str(receipt_root))} "
                + f"{shlex.quote(str(output_root))} planner current-run "
                + f"{shlex.quote(str(latest_path))}"
            )

        for failure_stage in ("output_remove", "receipt_unlink", "dir_fsync"):
            with self.subTest(failure_stage=failure_stage), tempfile.TemporaryDirectory(
                prefix=f"planveyor_role_run_retention_pair_{failure_stage}_"
            ) as tmpdir:
                (
                    root,
                    env,
                    receipt_root,
                    output_root,
                    run_ids,
                    oldest_receipt,
                    oldest_output,
                    oldest_log,
                    latest_path,
                ) = prepare_fixture(tmpdir)
                oldest_run_id = run_ids[0]
                command = prune_command(
                    receipt_root,
                    output_root,
                    latest_path,
                    hook="_planveyor_role_run_test_prune_fail_stage",
                    stage=failure_stage,
                )
                failed = self._run(root, env, command)
                self.assertEqual(failed.returncode, 1, failed.stderr)
                failure = json.loads(failed.stdout)
                self.assertEqual(failure["failure_stage"], failure_stage)
                self.assertEqual(failure["affected_run_id"], oldest_run_id)
                self.assertEqual(failure["rollback_state"], "complete")
                self.assertFalse(failure["mutation_performed"])
                self.assertEqual(failure["pruned_before_failure"], [])
                self.assertTrue(oldest_receipt.exists())
                self.assertTrue(oldest_output.is_dir())
                self.assertEqual(oldest_log.read_text(encoding="utf-8"), "preserve-on-recovery")
                self.assertEqual(list(receipt_root.glob(".prune-txn-*")), [])
                self.assertEqual(list(output_root.glob(".prune-txn-*")), [])

                recovered = self._run(
                    root,
                    env,
                    prune_command(receipt_root, output_root, latest_path),
                )
                self.assertEqual(recovered.returncode, 0, recovered.stderr)
                self.assertIn(oldest_run_id, json.loads(recovered.stdout)["pruned"])
                self.assertFalse(oldest_receipt.exists())
                self.assertFalse(oldest_output.exists())

                oldest_receipt.write_text(
                    json.dumps(
                        {
                            "schema_version": "role_execution_receipt.v1",
                            "run_id": oldest_run_id,
                            "session_key": "planner",
                            "receipt_written_at": "2026-01-01T00:00:00Z",
                            "state": "success",
                        }
                    ),
                    encoding="utf-8",
                )
                oldest_output.mkdir()
                (oldest_output / "stdout.log").write_text(
                    "truthful-after-commit-failure", encoding="utf-8"
                )
                cleanup_stage = {
                    "output_remove": "output_cleanup",
                    "receipt_unlink": "receipt_cleanup",
                    "dir_fsync": "dir_fsync_cleanup",
                }[failure_stage]
                committed_failure = self._run(
                    root,
                    env,
                    prune_command(
                        receipt_root,
                        output_root,
                        latest_path,
                        hook="_planveyor_role_run_test_prune_fail_stage",
                        stage=cleanup_stage,
                    ),
                )
                self.assertEqual(committed_failure.returncode, 1, committed_failure.stderr)
                committed = json.loads(committed_failure.stdout)
                self.assertEqual(committed["failure_stage"], cleanup_stage)
                self.assertEqual(committed["affected_run_id"], oldest_run_id)
                self.assertEqual(committed["rollback_state"], "committed_cleanup_pending")
                self.assertTrue(committed["mutation_performed"])
                self.assertEqual(committed["pruned_before_failure"], [oldest_run_id])
                self.assertFalse(oldest_receipt.exists())
                self.assertFalse(oldest_output.exists())
                recovery_journal = Path(committed["recovery_journal_path"])
                self.assertTrue(recovery_journal.is_dir())
                self.assertTrue(recovery_journal.name.endswith(".committed"))
                if cleanup_stage == "output_cleanup":
                    self.assertEqual(len(committed["cleanup_pending_paths"]), 2)
                elif cleanup_stage == "receipt_cleanup":
                    self.assertEqual(len(committed["cleanup_pending_paths"]), 1)
                else:
                    self.assertEqual(committed["cleanup_pending_paths"], [])

                cleanup_retry = self._run(
                    root,
                    env,
                    prune_command(receipt_root, output_root, latest_path),
                )
                self.assertEqual(cleanup_retry.returncode, 0, cleanup_retry.stderr)
                cleanup_retry_payload = json.loads(cleanup_retry.stdout)
                self.assertEqual(
                    cleanup_retry_payload["recovered"],
                    [{"action": "cleanup_completed", "run_id": oldest_run_id}],
                )
                self.assertEqual(list(receipt_root.glob(".prune-txn-*")), [])
                self.assertEqual(list(output_root.glob(".prune-txn-*")), [])

        death_stages = {
            "output_remove": ("prepared", "rolled_back"),
            "receipt_unlink": ("prepared", "rolled_back"),
            "dir_fsync": ("prepared", "rolled_back"),
            "journal_commit": ("committed", "cleanup_completed"),
            "output_cleanup": ("committed", "cleanup_completed"),
            "receipt_cleanup": ("committed", "cleanup_completed"),
            "dir_fsync_cleanup": ("committed", "cleanup_completed"),
        }
        for death_stage, (journal_phase, recovery_action) in death_stages.items():
            with self.subTest(death_stage=death_stage), tempfile.TemporaryDirectory(
                prefix=f"planveyor_role_run_retention_death_{death_stage}_"
            ) as tmpdir:
                (
                    root,
                    env,
                    receipt_root,
                    output_root,
                    run_ids,
                    oldest_receipt,
                    oldest_output,
                    _,
                    latest_path,
                ) = prepare_fixture(tmpdir)
                oldest_run_id = run_ids[0]
                killed = self._run(
                    root,
                    env,
                    prune_command(
                        receipt_root,
                        output_root,
                        latest_path,
                        hook="_planveyor_role_run_test_prune_kill_stage",
                        stage=death_stage,
                    ),
                )
                self.assertEqual(killed.returncode, 97, killed.stderr)
                journal_paths = list(receipt_root.glob(f".prune-txn-*.{journal_phase}"))
                self.assertEqual(len(journal_paths), 1)
                self.assertEqual(stat.S_IMODE(journal_paths[0].stat().st_mode), 0o700)
                self.assertEqual(
                    stat.S_IMODE((journal_paths[0] / "journal.json").stat().st_mode), 0o600
                )

                retry = self._run(
                    root,
                    env,
                    prune_command(receipt_root, output_root, latest_path),
                )
                self.assertEqual(retry.returncode, 0, retry.stderr)
                retry_payload = json.loads(retry.stdout)
                self.assertEqual(
                    retry_payload["recovered"],
                    [{"action": recovery_action, "run_id": oldest_run_id}],
                )
                if recovery_action == "rolled_back":
                    self.assertIn(oldest_run_id, retry_payload["pruned"])
                self.assertFalse(oldest_receipt.exists())
                self.assertFalse(oldest_output.exists())
                self.assertEqual(list(receipt_root.glob(".prune-txn-*")), [])
                self.assertEqual(list(output_root.glob(".prune-txn-*")), [])

        with self.subTest(recovery_before_unclassified="authoritative_fields"), tempfile.TemporaryDirectory(
            prefix="planveyor_role_run_retention_recover_then_block_"
        ) as tmpdir:
            (
                root,
                env,
                receipt_root,
                output_root,
                _,
                oldest_receipt,
                oldest_output,
                _,
                latest_path,
            ) = prepare_fixture(tmpdir)
            killed = self._run(
                root,
                env,
                prune_command(
                    receipt_root,
                    output_root,
                    latest_path,
                    hook="_planveyor_role_run_test_prune_kill_stage",
                    stage="output_remove",
                ),
            )
            self.assertEqual(killed.returncode, 97, killed.stderr)
            orphan = output_root / "manual-probe-orphan"
            orphan.mkdir()

            blocked = self._run(
                root,
                env,
                prune_command(receipt_root, output_root, latest_path),
            )
            self.assertEqual(blocked.returncode, 1, blocked.stderr)
            blocked_payload = json.loads(blocked.stdout)
            self.assertEqual(
                blocked_payload["reason"],
                "unclassified_orphan_output_dir",
            )
            self.assertTrue(blocked_payload["mutation_performed"])
            self.assertEqual(
                blocked_payload["affected_paths"],
                sorted(set(blocked_payload["affected_paths"])),
            )
            self.assertIn(str(orphan), blocked_payload["affected_paths"])
            self.assertTrue(oldest_receipt.exists())
            self.assertTrue(oldest_output.exists())
            self.assertEqual(list(receipt_root.glob(".prune-txn-*")), [])
            orphan.rmdir()

        journal_edge_stages = {
            "journal_mkdir": "building",
            "journal_write": "building",
            "journal_file_fsync": "building",
            "journal_phase_fsync": "building",
            "journal_publish": "prepared",
            "journal_root_fsync": "prepared",
            "journal_retire": "retired",
            "journal_retire_root_fsync": "retired",
            "journal_payload_unlink": "retired",
            "journal_rmdir": "",
            "journal_cleanup_root_fsync": "",
        }
        for death_stage, expected_phase in journal_edge_stages.items():
            with self.subTest(journal_death_stage=death_stage), tempfile.TemporaryDirectory(
                prefix=f"planveyor_role_run_journal_death_{death_stage}_"
            ) as tmpdir:
                (
                    root,
                    env,
                    receipt_root,
                    output_root,
                    run_ids,
                    oldest_receipt,
                    oldest_output,
                    _,
                    latest_path,
                ) = prepare_fixture(tmpdir)
                oldest_run_id = run_ids[0]
                killed = self._run(
                    root,
                    env,
                    prune_command(
                        receipt_root,
                        output_root,
                        latest_path,
                        hook="_planveyor_role_run_test_prune_kill_stage",
                        stage=death_stage,
                    ),
                )
                self.assertEqual(killed.returncode, 97, killed.stderr)
                phase_paths = list(receipt_root.glob(".prune-txn-*"))
                if expected_phase:
                    self.assertEqual(len(phase_paths), 1)
                    self.assertTrue(phase_paths[0].name.endswith(f".{expected_phase}"))
                else:
                    self.assertEqual(phase_paths, [])

                retry = self._run(
                    root,
                    env,
                    prune_command(receipt_root, output_root, latest_path),
                )
                self.assertEqual(retry.returncode, 0, retry.stderr)
                retry_payload = json.loads(retry.stdout)
                if expected_phase == "prepared":
                    self.assertEqual(
                        retry_payload["recovered"],
                        [{"action": "rolled_back", "run_id": oldest_run_id}],
                    )
                self.assertFalse(oldest_receipt.exists())
                self.assertFalse(oldest_output.exists())
                self.assertEqual(list(receipt_root.glob(".prune-txn-*")), [])
                self.assertEqual(list(output_root.glob(".prune-txn-*")), [])

        for failure_stage in journal_edge_stages:
            with self.subTest(journal_failure_stage=failure_stage), tempfile.TemporaryDirectory(
                prefix=f"planveyor_role_run_journal_failure_{failure_stage}_"
            ) as tmpdir:
                (
                    root,
                    env,
                    receipt_root,
                    output_root,
                    _,
                    oldest_receipt,
                    oldest_output,
                    _,
                    latest_path,
                ) = prepare_fixture(tmpdir)
                failed = self._run(
                    root,
                    env,
                    prune_command(
                        receipt_root,
                        output_root,
                        latest_path,
                        hook="_planveyor_role_run_test_prune_fail_stage",
                        stage=failure_stage,
                    ),
                )
                self.assertEqual(failed.returncode, 1, failed.stderr)
                failure_payload = json.loads(failed.stdout)
                self.assertEqual(failure_payload["failure_stage"], failure_stage)
                self.assertEqual(
                    failure_payload["mutation_performed"],
                    failure_stage
                    in {
                        "journal_retire",
                        "journal_retire_root_fsync",
                        "journal_payload_unlink",
                        "journal_rmdir",
                        "journal_cleanup_root_fsync",
                    },
                )

                retry = self._run(
                    root,
                    env,
                    prune_command(receipt_root, output_root, latest_path),
                )
                self.assertEqual(retry.returncode, 0, retry.stderr)
                self.assertFalse(oldest_receipt.exists())
                self.assertFalse(oldest_output.exists())
                self.assertEqual(list(receipt_root.glob(".prune-txn-*")), [])
                self.assertEqual(list(output_root.glob(".prune-txn-*")), [])

        with self.subTest(pid_reuse="lease_authority"), tempfile.TemporaryDirectory(
            prefix="planveyor_role_run_retention_pid_reuse_"
        ) as tmpdir:
            (
                root,
                env,
                receipt_root,
                output_root,
                run_ids,
                oldest_receipt,
                oldest_output,
                _,
                latest_path,
            ) = prepare_fixture(tmpdir)
            oldest_run_id = run_ids[0]
            killed = self._run(
                root,
                env,
                prune_command(
                    receipt_root,
                    output_root,
                    latest_path,
                    hook="_planveyor_role_run_test_prune_kill_stage",
                    stage="output_remove",
                ),
            )
            self.assertEqual(killed.returncode, 97, killed.stderr)
            prepared_paths = list(receipt_root.glob(".prune-txn-*.prepared"))
            self.assertEqual(len(prepared_paths), 1)
            journal_file = prepared_paths[0] / "journal.json"
            journal_payload = json.loads(journal_file.read_text(encoding="utf-8"))
            journal_payload["owner_pid"] = os.getpid()
            journal_file.write_text(
                json.dumps(journal_payload, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            retry = self._run(
                root,
                env,
                prune_command(receipt_root, output_root, latest_path),
            )
            self.assertEqual(retry.returncode, 0, retry.stderr)
            retry_payload = json.loads(retry.stdout)
            self.assertEqual(
                retry_payload["recovered"],
                [{"action": "rolled_back", "run_id": oldest_run_id}],
            )
            self.assertIn(oldest_run_id, retry_payload["pruned"])
            self.assertFalse(oldest_receipt.exists())
            self.assertFalse(oldest_output.exists())
            self.assertEqual(list(receipt_root.glob(".prune-txn-*")), [])
            self.assertEqual(list(output_root.glob(".prune-txn-*")), [])

        with self.subTest(active_lease="exact_run_protected"), tempfile.TemporaryDirectory(
            prefix="planveyor_role_run_retention_active_lease_"
        ) as tmpdir:
            (
                root,
                env,
                receipt_root,
                output_root,
                _,
                oldest_receipt,
                oldest_output,
                oldest_log,
                latest_path,
            ) = prepare_fixture(tmpdir)
            lock_root = output_root / ".locks"
            lock_root.mkdir(mode=0o700)
            lease_path = lock_root / "retention-prune.lock"
            with lease_path.open("w+", encoding="utf-8") as lease_handle:
                os.chmod(lease_path, 0o600)
                fcntl.flock(lease_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                blocked = self._run(
                    root,
                    env,
                    prune_command(receipt_root, output_root, latest_path),
                )
                self.assertEqual(blocked.returncode, 1, blocked.stderr)
                blocked_payload = json.loads(blocked.stdout)
                self.assertEqual(blocked_payload["reason"], "retention_prune_lock_contended")
                self.assertFalse(blocked_payload["mutation_performed"])
                self.assertTrue(oldest_receipt.exists())
                self.assertTrue(oldest_output.exists())
                self.assertEqual(oldest_log.read_text(encoding="utf-8"), "preserve-on-recovery")
                self.assertEqual(list(receipt_root.glob(".prune-txn-*")), [])
                fcntl.flock(lease_handle.fileno(), fcntl.LOCK_UN)

            retry = self._run(
                root,
                env,
                prune_command(receipt_root, output_root, latest_path),
            )
            self.assertEqual(retry.returncode, 0, retry.stderr)
            self.assertFalse(oldest_receipt.exists())
            self.assertFalse(oldest_output.exists())

        for phase in ("prepared", "committed"):
            for incomplete_kind in ("empty", "partial"):
                with self.subTest(
                    legacy_phase=phase,
                    incomplete_kind=incomplete_kind,
                ), tempfile.TemporaryDirectory(
                    prefix=f"planveyor_role_run_retention_legacy_{phase}_{incomplete_kind}_"
                ) as tmpdir:
                    (
                        root,
                        env,
                        receipt_root,
                        output_root,
                        _,
                        oldest_receipt,
                        oldest_output,
                        _,
                        latest_path,
                    ) = prepare_fixture(tmpdir)
                    legacy_phase = receipt_root / f".prune-txn-{'f' * 32}.{phase}"
                    legacy_phase.mkdir(mode=0o700)
                    if incomplete_kind == "partial":
                        (legacy_phase / "journal.json").write_text("{", encoding="utf-8")

                    recovered = self._run(
                        root,
                        env,
                        prune_command(receipt_root, output_root, latest_path),
                    )
                    self.assertEqual(recovered.returncode, 0, recovered.stderr)
                    self.assertFalse(oldest_receipt.exists())
                    self.assertFalse(oldest_output.exists())
                    self.assertFalse(legacy_phase.exists())
                    self.assertEqual(list(receipt_root.glob(".prune-txn-*")), [])

        with self.subTest(forged_journal="fail_closed"), tempfile.TemporaryDirectory(
            prefix="planveyor_role_run_retention_forged_journal_"
        ) as tmpdir:
            (
                root,
                env,
                receipt_root,
                output_root,
                _,
                oldest_receipt,
                oldest_output,
                oldest_log,
                latest_path,
            ) = prepare_fixture(tmpdir)
            forged = receipt_root / f".prune-txn-{'0' * 32}.prepared"
            forged.mkdir(mode=0o700)
            (forged / "journal.json").write_text("{}\n", encoding="utf-8")
            blocked = self._run(
                root,
                env,
                prune_command(receipt_root, output_root, latest_path),
            )
            self.assertEqual(blocked.returncode, 1, blocked.stderr)
            blocked_payload = json.loads(blocked.stdout)
            self.assertEqual(blocked_payload["reason"], "unclassified_carriers")
            self.assertIn(str(forged), blocked_payload["paths"])
            self.assertTrue(oldest_receipt.exists())
            self.assertTrue(oldest_output.exists())
            self.assertEqual(oldest_log.read_text(encoding="utf-8"), "preserve-on-recovery")

    def test_role_run_supports_architect_variants_with_shared_session_key(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_role_run_architect_") as tmpdir:
            root, env, log_dir = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
            self._write_runtime_plan(root, status="In progress")
            architect_sid = "00000000-0000-4000-8000-000000000310"
            variants = {
                "architect": "planveyor_arch",
                "architect_initial": "planveyor_arch_initial",
                "architect_censor": "planveyor_arch_censor",
            }

            for role_key, wrapper in variants.items():
                result = self._run(
                    root,
                    env,
                    "planveyor_plan_set docs/plans/260101_0000_test_runtime.md >/dev/null && "
                    "planveyor_runner_set architect codex >/dev/null && "
                    f"planveyor_session_set architect {architect_sid} runner=codex >/dev/null && "
                    f"planveyor_role_run {role_key} --json",
                )

                self.assertEqual(result.returncode, 0, result.stderr)
                payload = json.loads(result.stdout)
                self.assertEqual(payload["schema_version"], "role_execution_receipt.v1")
                self.assertEqual(payload["role"], role_key)
                self.assertEqual(payload["session_key"], "architect")
                self.assertEqual(payload["wrapper"], wrapper)
                self.assertEqual(payload["runner_id"], "codex")
                self.assertEqual(payload["profile"], "N/A (why=profile not readable)")
                self.assertEqual(payload["model"], "N/A (why=no explicit Codex profile)")
                self.assertEqual(payload["sid"], architect_sid)
                self.assertFalse(payload["child_session"])
                self.assertEqual(payload["target_plan"], "docs/plans/260101_0000_test_runtime.md")
                self.assertEqual(payload["state"], "success")
                self.assertEqual(payload["timeout_seconds"], 3600)
                self.assertTrue(Path(payload["stdout_path"]).exists())
                self.assertTrue(Path(payload["stderr_path"]).exists())
                self.assertIn("**Status:** In progress", payload["pre_status"])
                self.assertIn("**Status:** In progress", payload["post_status"])

            calls = self._codex_calls(log_dir)
            self.assertEqual([call["role"] for call in calls], ["architect", "architect", "architect"])
            self.assertTrue(all(call.get("role_run_env_keys") for call in calls))
            for call in calls:
                self.assertNotIn("-p", call["argv"])

    def test_role_run_supports_planner_and_coder_censor_variants_without_schema_expansion(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_role_run_censor_") as tmpdir:
            root, env, log_dir = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
            variants = {
                "planner_censor": ("planner", "planveyor_planner_censor", "Ready for Coder", "Planner"),
                "coder_censor": ("coder", "planveyor_coder_censor", "Ready for Review", "Coder"),
            }

            for role_key, (session_key, wrapper, handoff_status, censor_role) in variants.items():
                plan_path = self._write_runtime_plan(root, status=handoff_status)
                with plan_path.open("a", encoding="utf-8") as fh:
                    fh.write(
                        f"- [2026-01-01 00:00 MSK] ({censor_role}) Censor hint: skip "
                        f"(why=evidence-only delta; previous {censor_role.lower()}-owned contract unchanged; "
                        f"handoff_status={handoff_status})\n"
                    )
                sid = SUCCESS_SIDS[session_key]
                result = self._run(
                    root,
                    env,
                    "planveyor_plan_set docs/plans/260101_0000_test_runtime.md >/dev/null && "
                    f"planveyor_session_set {session_key} {sid} runner=codex >/dev/null && "
                    f"planveyor_role_run {role_key} --json",
                )

                self.assertEqual(result.returncode, 0, result.stderr)
                payload = json.loads(result.stdout)
                self.assertEqual(payload["schema_version"], "role_execution_receipt.v1")
                self.assertEqual(payload["role"], role_key)
                self.assertEqual(payload["session_key"], session_key)
                self.assertEqual(payload["wrapper"], wrapper)
                self.assertEqual(payload["runner_id"], "codex")
                self.assertEqual(payload["profile"], "N/A (why=profile not readable)")
                self.assertEqual(payload["model"], "N/A (why=no explicit Codex profile)")
                self.assertFalse(payload["child_session"])
                self.assertNotIn("runner_role", payload)
                self.assertEqual(payload["state"], "success")
                self.assertEqual(payload["target_plan"], "docs/plans/260101_0000_test_runtime.md")
                self.assertIn(f"**Status:** {handoff_status}", payload["pre_status"])
                self.assertIn(f"**Status:** {handoff_status}", payload["post_status"])
                self.assertEqual(payload["session_action_requested"], "resume")
                self.assertEqual(payload["session_pointer_relation"], "same")
                self.assertEqual(payload["process_start_outcome"], "started")
                self.assertFalse(payload["session_reset_performed"])
                self.assertEqual(payload["cli_process_mode"], "one_shot")
                self.assertFalse(payload["process_persistent"])
                self.assertEqual(payload["provider_error_class"], "not_applicable")
                self.assertEqual(payload["provider_http_status"], "not_applicable")
                self.assertEqual(payload["provider_error_code"], "not_applicable")
                self.assertEqual(payload["provider_retryability"], "not_applicable")

            calls = self._codex_calls(log_dir)
            self.assertEqual([call["role"] for call in calls], ["planner", "coder"])
            for call in calls:
                self.assertNotIn("-p", call["argv"])

    def test_role_run_architect_variant_missing_session_fails_before_wrapper(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_role_run_architect_missing_") as tmpdir:
            root, env, log_dir = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
            self._write_runtime_plan(root, status="In progress")

            result = self._run(
                root,
                env,
                "planveyor_plan_set docs/plans/260101_0000_test_runtime.md >/dev/null && "
                "planveyor_runner_set architect codex >/dev/null && "
                "planveyor_role_run architect_initial --json",
            )

            self.assertEqual(result.returncode, 125)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["role"], "architect_initial")
            self.assertEqual(payload["session_key"], "architect")
            self.assertEqual(payload["wrapper"], "planveyor_arch_initial")
            self.assertEqual(payload["state"], "precondition_failed")
            self.assertEqual(payload["non_green_reason"], "missing_session_sid")
            self.assertEqual(payload["session_pointer_relation"], "missing")
            self.assertEqual(payload["process_start_outcome"], "not_started")
            self.assertEqual(payload["provider_error_class"], "not_applicable")
            self.assertEqual(payload["provider_retryability"], "not_applicable")
            self.assertFalse(payload["success"])
            self.assertEqual(self._codex_calls(log_dir), [])

    def test_role_run_missing_wrapper_and_spawn_error_are_not_started(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_role_run_not_started_") as tmpdir:
            root, env, _ = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
            self._write_runtime_plan(root, status="In progress")
            planner_sid = "00000000-0000-4000-8000-000000000311"
            setup = (
                "planveyor_plan_set docs/plans/260101_0000_test_runtime.md >/dev/null && "
                "planveyor_runner_set planner codex >/dev/null && "
                f"planveyor_session_set planner {planner_sid} runner=codex >/dev/null && "
            )

            missing_wrapper = self._run(
                root,
                env,
                setup + "unfunction planveyor_planner && planveyor_role_run planner --json",
            )
            self.assertEqual(missing_wrapper.returncode, 125, missing_wrapper.stderr)
            missing_payload = json.loads(missing_wrapper.stdout)
            self.assertEqual(missing_payload["state"], "precondition_failed")
            self.assertEqual(missing_payload["non_green_reason"], "missing_wrapper_function")
            self.assertEqual(missing_payload["process_start_outcome"], "not_started")
            self.assertEqual(missing_payload["session_pointer_relation"], "same")
            self.assertEqual(missing_payload["provider_error_class"], "not_applicable")
            self.assertEqual(missing_payload["readback_state"], "ok")

            preflight_failed = self._run(
                root,
                env,
                "planveyor_plan_set docs/plans/260101_0000_test_runtime.md >/dev/null && "
                "planveyor_runner_set planner codex >/dev/null && "
                f"planveyor_session_set planner {planner_sid} runner=codex >/dev/null && "
                "planveyor_role_runner_preflight() { print -r -- 'synthetic preflight failure' >&2; return 1; } && "
                "planveyor_role_run planner --json",
            )
            self.assertEqual(preflight_failed.returncode, 125, preflight_failed.stderr)
            preflight_payload = json.loads(preflight_failed.stdout)
            self.assertEqual(preflight_payload["state"], "precondition_failed")
            self.assertEqual(preflight_payload["non_green_reason"], "precondition_failed")
            self.assertEqual(preflight_payload["process_start_outcome"], "not_started")
            self.assertEqual(preflight_payload["provider_error_class"], "not_applicable")
            self.assertEqual(preflight_payload["readback_state"], "ok")

            supervise_payload = json.dumps(
                {
                    "exit_code": 125,
                    "timed_out": False,
                    "process_started": False,
                    "supervisor_error": "OSError: synthetic spawn failure",
                }
            )
            spawn_error = self._run(
                root,
                env,
                setup
                + f"_planveyor_role_run_supervise() {{ print -r -- {shlex.quote(supervise_payload)}; }} && "
                + "planveyor_role_run planner --json",
            )
            self.assertEqual(spawn_error.returncode, 125, spawn_error.stderr)
            spawn_payload = json.loads(spawn_error.stdout)
            self.assertEqual(spawn_payload["state"], "failed")
            self.assertEqual(spawn_payload["process_start_outcome"], "not_started")
            self.assertEqual(spawn_payload["provider_error_class"], "not_applicable")
            self.assertEqual(spawn_payload["provider_retryability"], "not_applicable")
            self.assertEqual(spawn_payload["readback_state"], "ok")

    def test_role_run_provider_error_classifier_is_bounded_and_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_role_run_provider_errors_") as tmpdir:
            root, env, _ = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
            self._write_runtime_plan(root, status="In progress")
            planner_sid = "00000000-0000-4000-8000-000000000312"
            setup = (
                "planveyor_plan_set docs/plans/260101_0000_test_runtime.md >/dev/null && "
                "planveyor_runner_set planner codex >/dev/null && "
                f"planveyor_session_set planner {planner_sid} runner=codex >/dev/null && "
            )

            cases = {
                "model_invalid": (
                    "API Error: status 400 code 1211 invalid model secret=NEVER_COPY_PROVIDER_TEXT",
                    ("400", "1211", "model_invalid", "not_retryable"),
                ),
                "overload": (
                    "API Error: status 529 code 1305 overload",
                    ("529", "1305", "overload", "retryable"),
                ),
                "authentication_401": (
                    "API Error: status 401 authentication failed for credential",
                    ("401", "unknown", "authentication", "not_retryable"),
                ),
                "authentication_403": (
                    "API Error: status 403 forbidden authentication failure",
                    ("403", "unknown", "authentication", "not_retryable"),
                ),
                "authentication_status_conflict": (
                    "API Error: status 401 or 403 authentication failed",
                    ("unknown", "unknown", "unknown", "unknown"),
                ),
                "rate_limit": (
                    "API Error: HTTP status 429 rate limit exceeded",
                    ("429", "unknown", "rate_limit", "retryable"),
                ),
                "no_match": (
                    "provider request failed without a bounded numeric signature",
                    ("unknown", "unknown", "unknown", "unknown"),
                ),
                "conflict": (
                    "API Error: status 400 code 1211 invalid model\nAPI Error: status 529 code 1305 overload",
                    ("unknown", "unknown", "unknown", "unknown"),
                ),
                "outside_tail": (
                    "API Error: status 529 code 1305 overload\n" + ("x" * (70 * 1024)) + "\nrequest failed",
                    ("unknown", "unknown", "unknown", "unknown"),
                ),
            }

            for name, (message, expected) in cases.items():
                with self.subTest(name=name):
                    result = self._run(
                        root,
                        env,
                        setup
                        + f"planveyor_planner() {{ print -r -- {shlex.quote(message)} >&2; return 23; }} && "
                        + "planveyor_role_run planner --json",
                    )
                    self.assertEqual(result.returncode, 23, result.stderr)
                    payload = json.loads(result.stdout)
                    actual = (
                        payload["provider_http_status"],
                        payload["provider_error_code"],
                        payload["provider_error_class"],
                        payload["provider_retryability"],
                    )
                    self.assertEqual(actual, expected)
                    self.assertEqual(payload["process_start_outcome"], "started")
                    self.assertEqual(payload["readback_state"], "ok")
                    self.assertNotIn("NEVER_COPY_PROVIDER_TEXT", json.dumps(payload, ensure_ascii=False))
                    persisted = json.loads(Path(payload["receipt_path"]).read_text(encoding="utf-8"))
                    self.assertEqual(
                        (
                            persisted["provider_http_status"],
                            persisted["provider_error_code"],
                            persisted["provider_error_class"],
                            persisted["provider_retryability"],
                        ),
                        expected,
                    )
                    latest = Path(payload["latest_receipt_path"]).read_text(encoding="utf-8")
                    for key, value in zip(
                        (
                            "provider_http_status",
                            "provider_error_code",
                            "provider_error_class",
                            "provider_retryability",
                        ),
                        expected,
                    ):
                        self.assertIn(f"{key}={value}", latest)
                    self.assertNotIn("NEVER_COPY_PROVIDER_TEXT", latest)

            success_noise = self._run(
                root,
                env,
                setup
                + "planveyor_planner() { print -r -- 'API Error: status 529 code 1305 overload' >&2; return 0; } && "
                + "planveyor_role_run planner --json",
            )
            self.assertEqual(success_noise.returncode, 0, success_noise.stderr)
            success_payload = json.loads(success_noise.stdout)
            self.assertEqual(success_payload["provider_error_class"], "not_applicable")
            self.assertEqual(success_payload["provider_http_status"], "not_applicable")
            self.assertEqual(success_payload["provider_error_code"], "not_applicable")
            self.assertEqual(success_payload["provider_retryability"], "not_applicable")

    def test_role_run_nonzero_and_timeout_are_non_green_receipts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_role_run_fail_") as tmpdir:
            root, env, _ = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
            self._write_runtime_plan(root, status="In progress")
            planner_sid = "00000000-0000-4000-8000-000000000305"

            failed = self._run(
                root,
                env,
                "planveyor_plan_set docs/plans/260101_0000_test_runtime.md >/dev/null && "
                "planveyor_runner_set planner codex >/dev/null && "
                f"planveyor_session_set planner {planner_sid} runner=codex >/dev/null && "
                "planveyor_planner() { print -r -- wrapper-failed; return 23; } && "
                "planveyor_role_run planner --json",
            )
            self.assertEqual(failed.returncode, 23)
            failed_payload = json.loads(failed.stdout)
            self.assertEqual(failed_payload["state"], "failed")
            self.assertEqual(failed_payload["exit_code"], 23)
            self.assertFalse(failed_payload["success"])
            self.assertFalse(failed_payload["timed_out"])
            self.assertFalse(failed_payload["terminated_by_timeout"])
            self.assertEqual(failed_payload["elapsed_seconds"], failed_payload["duration_seconds"])
            self.assertEqual(failed_payload["non_green_reason"], "exit_code_23")
            self.assertEqual(failed_payload["process_start_outcome"], "started")
            self.assertEqual(failed_payload["provider_error_class"], "unknown")
            self.assertEqual(failed_payload["provider_http_status"], "unknown")
            self.assertEqual(failed_payload["provider_error_code"], "unknown")
            self.assertEqual(failed_payload["provider_retryability"], "unknown")
            self.assertIn("wrapper-failed", Path(failed_payload["stdout_path"]).read_text(encoding="utf-8"))

            timed_out = self._run(
                root,
                env,
                "planveyor_plan_set docs/plans/260101_0000_test_runtime.md >/dev/null && "
                "planveyor_runner_set planner codex >/dev/null && "
                f"planveyor_session_set planner {planner_sid} runner=codex >/dev/null && "
                "planveyor_planner() { print -r -- 'API Error: status 529 code 1305 overload' >&2; sleep 3; return 0; } && "
                "planveyor_role_run planner --timeout 1 --json",
            )
            self.assertEqual(timed_out.returncode, 124)
            timeout_payload = json.loads(timed_out.stdout)
            self.assertEqual(timeout_payload["state"], "timeout")
            self.assertTrue(timeout_payload["timed_out"])
            self.assertTrue(timeout_payload["terminated_by_timeout"])
            self.assertEqual(timeout_payload["elapsed_seconds"], timeout_payload["duration_seconds"])
            self.assertFalse(timeout_payload["success"])
            self.assertEqual(timeout_payload["non_green_reason"], "timeout")
            self.assertEqual(timeout_payload["process_start_outcome"], "started")
            self.assertEqual(timeout_payload["provider_error_class"], "not_applicable")
            self.assertEqual(timeout_payload["provider_retryability"], "not_applicable")

            marker = root / ".tmp" / "role-run-descendant-survived"
            marker.parent.mkdir(parents=True, exist_ok=True)
            child_script = (
                "import pathlib, signal, time; "
                "signal.signal(signal.SIGHUP, signal.SIG_IGN); "
                "time.sleep(2); "
                f"pathlib.Path({str(marker)!r}).write_text('survived', encoding='utf-8')"
            )
            descendant = self._run(
                root,
                env,
                "planveyor_plan_set docs/plans/260101_0000_test_runtime.md >/dev/null && "
                "planveyor_runner_set planner codex >/dev/null && "
                f"planveyor_session_set planner {planner_sid} runner=codex >/dev/null && "
                f"planveyor_planner() {{ {shlex.quote(sys.executable)} -c {shlex.quote(child_script)} & wait; }} && "
                "planveyor_role_run planner --timeout 1 --json",
            )
            self.assertEqual(descendant.returncode, 124, descendant.stderr)
            descendant_payload = json.loads(descendant.stdout)
            self.assertEqual(descendant_payload["state"], "timeout")
            time.sleep(2.5)
            self.assertFalse(marker.exists(), marker.read_text(encoding="utf-8") if marker.exists() else "")

            default_marker = root / ".tmp" / "role-run-default-timeout-descendant-survived"
            default_child_script = (
                "import pathlib, signal, time; "
                "signal.signal(signal.SIGHUP, signal.SIG_IGN); "
                "time.sleep(2); "
                f"pathlib.Path({str(default_marker)!r}).write_text('survived', encoding='utf-8')"
            )
            default_timeout = self._run(
                root,
                env,
                "planveyor_plan_set docs/plans/260101_0000_test_runtime.md >/dev/null && "
                "planveyor_runner_set planner codex >/dev/null && "
                f"planveyor_session_set planner {planner_sid} runner=codex >/dev/null && "
                f"planveyor_planner() {{ {shlex.quote(sys.executable)} -c {shlex.quote(default_child_script)} & wait; }} && "
                "PLANVEYOR_ROLE_RUN_DEFAULT_TIMEOUT_SECONDS=1 planveyor_role_run planner --json",
            )
            self.assertEqual(default_timeout.returncode, 124, default_timeout.stderr)
            default_payload = json.loads(default_timeout.stdout)
            self.assertEqual(default_payload["state"], "timeout")
            self.assertEqual(default_payload["timeout_seconds"], 1)
            self.assertTrue(default_payload["terminated_by_timeout"])
            self.assertEqual(default_payload["elapsed_seconds"], default_payload["duration_seconds"])
            time.sleep(2.5)
            self.assertFalse(
                default_marker.exists(),
                default_marker.read_text(encoding="utf-8") if default_marker.exists() else "",
            )

            interrupted = self._run(
                root,
                env,
                "planveyor_plan_set docs/plans/260101_0000_test_runtime.md >/dev/null && "
                "planveyor_runner_set planner codex >/dev/null && "
                f"planveyor_session_set planner {planner_sid} runner=codex >/dev/null && "
                "planveyor_planner() { print -r -- 'API Error: status 529 code 1305 overload' >&2; return 130; } && "
                "planveyor_role_run planner --json",
            )
            self.assertEqual(interrupted.returncode, 130)
            interrupted_payload = json.loads(interrupted.stdout)
            self.assertEqual(interrupted_payload["state"], "interrupted")
            self.assertTrue(interrupted_payload["interrupted"])
            self.assertFalse(interrupted_payload["timed_out"])
            self.assertFalse(interrupted_payload["terminated_by_timeout"])
            self.assertEqual(interrupted_payload["elapsed_seconds"], interrupted_payload["duration_seconds"])
            self.assertFalse(interrupted_payload["success"])
            self.assertEqual(interrupted_payload["non_green_reason"], "interrupted")
            self.assertEqual(interrupted_payload["process_start_outcome"], "started")
            self.assertEqual(interrupted_payload["provider_error_class"], "not_applicable")
            self.assertEqual(interrupted_payload["provider_retryability"], "not_applicable")

    def test_role_run_rejects_stale_and_wrong_schema_receipts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_role_run_stale_") as tmpdir:
            root, env, _ = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
            self._write_runtime_plan(root, status="In progress")
            receipt_dir = root / ".planveyor.role_runs"
            receipt_dir.mkdir(parents=True, exist_ok=True)
            stale_path = receipt_dir / "stale.json"
            stale_path.write_text(
                json.dumps(
                    {
                        "schema_version": "role_execution_receipt.v1",
                        "run_id": "old-run",
                        "role": "planner",
                        "session_key": "planner",
                        "wrapper": "planveyor_planner",
                        "runner_id": "codex",
                        "runner_alias": "codex",
                        "profile": "N/A (why=profile not readable)",
                        "model": "N/A (why=no explicit Codex profile)",
                        "configured_model_id": "N/A (why=codex model comes from profile/session stats)",
                        "observable_model_id": "N/A (why=provider model metadata not exposed)",
                        "model_id_state": "unknown",
                        "sid": "sid",
                        "child_session": False,
                        "target_plan": "docs/plans/260101_0000_test_runtime.md",
                        "pre_status": "**Status:** In progress",
                        "post_status": "**Status:** In progress",
                        "exit_code": 0,
                        "timeout_seconds": 3600,
                        "duration_seconds": 1,
                        "elapsed_seconds": 1,
                        "timed_out": False,
                        "terminated_by_timeout": False,
                        "state": "success",
                        "started_at": "2026-06-23T13:00:00Z",
                        "finished_at": "2026-06-23T13:00:01Z",
                        "receipt_written_at": "2026-06-23T13:00:01Z",
                    }
                ),
                encoding="utf-8",
            )
            wrong_schema_path = receipt_dir / "wrong_schema.json"
            wrong_schema_path.write_text(
                json.dumps({"schema_version": "runtime_receipt.v1", "run_id": "wrong"}),
                encoding="utf-8",
            )
            missing_canonical_path = receipt_dir / "missing_canonical.json"
            missing_canonical_path.write_text(
                json.dumps(
                    {
                        "schema_version": "role_execution_receipt.v1",
                        "run_id": "missing-canonical",
                        "role": "planner",
                        "session_key": "planner",
                        "wrapper": "planveyor_planner",
                        "runner_id": "codex",
                        "runner_alias": "codex",
                        "profile": "N/A (why=profile not readable)",
                        "model": "N/A (why=no explicit Codex profile)",
                        "configured_model_id": "N/A (why=codex model comes from profile/session stats)",
                        "observable_model_id": "N/A (why=provider model metadata not exposed)",
                        "model_id_state": "unknown",
                        "sid": "sid",
                        "child_session": False,
                        "target_plan": "docs/plans/260101_0000_test_runtime.md",
                        "pre_status": "**Status:** In progress",
                        "post_status": "**Status:** In progress",
                        "exit_code": 0,
                        "timeout_seconds": 3600,
                        "duration_seconds": 1,
                        "timed_out": False,
                        "terminated_by_timeout": False,
                        "state": "success",
                        "started_at": "2026-06-23T13:00:00Z",
                        "finished_at": "2026-06-23T13:00:01Z",
                        "receipt_written_at": "2026-06-23T13:00:01Z",
                    }
                ),
                encoding="utf-8",
            )
            timing_mismatch_path = receipt_dir / "timing_mismatch.json"
            timing_mismatch_path.write_text(
                json.dumps(
                    {
                        "schema_version": "role_execution_receipt.v1",
                        "run_id": "timing-mismatch",
                        "role": "planner",
                        "session_key": "planner",
                        "wrapper": "planveyor_planner",
                        "runner_id": "codex",
                        "runner_alias": "codex",
                        "profile": "N/A (why=profile not readable)",
                        "model": "N/A (why=no explicit Codex profile)",
                        "configured_model_id": "N/A (why=codex model comes from profile/session stats)",
                        "observable_model_id": "N/A (why=provider model metadata not exposed)",
                        "model_id_state": "unknown",
                        "sid": "sid",
                        "child_session": False,
                        "target_plan": "docs/plans/260101_0000_test_runtime.md",
                        "pre_status": "**Status:** In progress",
                        "post_status": "**Status:** In progress",
                        "exit_code": 0,
                        "timeout_seconds": 3600,
                        "duration_seconds": 1,
                        "elapsed_seconds": 2,
                        "timed_out": False,
                        "terminated_by_timeout": False,
                        "state": "success",
                        "started_at": "2026-06-23T13:00:00Z",
                        "finished_at": "2026-06-23T13:00:01Z",
                        "receipt_written_at": "2026-06-23T13:00:01Z",
                    }
                ),
                encoding="utf-8",
            )
            timeout_mismatch_path = receipt_dir / "timeout_mismatch.json"
            timeout_mismatch_path.write_text(
                json.dumps(
                    {
                        "schema_version": "role_execution_receipt.v1",
                        "run_id": "timeout-mismatch",
                        "role": "planner",
                        "session_key": "planner",
                        "wrapper": "planveyor_planner",
                        "runner_id": "codex",
                        "runner_alias": "codex",
                        "profile": "N/A (why=profile not readable)",
                        "model": "N/A (why=no explicit Codex profile)",
                        "configured_model_id": "N/A (why=codex model comes from profile/session stats)",
                        "observable_model_id": "N/A (why=provider model metadata not exposed)",
                        "model_id_state": "unknown",
                        "sid": "sid",
                        "child_session": False,
                        "target_plan": "docs/plans/260101_0000_test_runtime.md",
                        "pre_status": "**Status:** In progress",
                        "post_status": "**Status:** In progress",
                        "exit_code": 124,
                        "timeout_seconds": 1,
                        "duration_seconds": 1,
                        "elapsed_seconds": 1,
                        "timed_out": False,
                        "terminated_by_timeout": True,
                        "state": "timeout",
                        "started_at": "2026-06-23T13:00:00Z",
                        "finished_at": "2026-06-23T13:00:01Z",
                        "receipt_written_at": "2026-06-23T13:00:01Z",
                    }
                ),
                encoding="utf-8",
            )
            timeout_state_mismatch_path = receipt_dir / "timeout_state_mismatch.json"
            timeout_state_mismatch_path.write_text(
                json.dumps(
                    {
                        "schema_version": "role_execution_receipt.v1",
                        "run_id": "timeout-state-mismatch",
                        "role": "planner",
                        "session_key": "planner",
                        "wrapper": "planveyor_planner",
                        "runner_id": "codex",
                        "runner_alias": "codex",
                        "profile": "N/A (why=profile not readable)",
                        "model": "N/A (why=no explicit Codex profile)",
                        "configured_model_id": "N/A (why=codex model comes from profile/session stats)",
                        "observable_model_id": "N/A (why=provider model metadata not exposed)",
                        "model_id_state": "unknown",
                        "sid": "sid",
                        "child_session": False,
                        "target_plan": "docs/plans/260101_0000_test_runtime.md",
                        "pre_status": "**Status:** In progress",
                        "post_status": "**Status:** In progress",
                        "exit_code": 124,
                        "timeout_seconds": 1,
                        "duration_seconds": 1,
                        "elapsed_seconds": 1,
                        "timed_out": False,
                        "terminated_by_timeout": False,
                        "state": "timeout",
                        "started_at": "2026-06-23T13:00:00Z",
                        "finished_at": "2026-06-23T13:00:01Z",
                        "receipt_written_at": "2026-06-23T13:00:01Z",
                    }
                ),
                encoding="utf-8",
            )
            (root / ".planveyor.run_receipt.manager_custom_pipeline").write_text(
                "schema_version=runtime_receipt.v1\nplan_path=docs/plans/old.md\n",
                encoding="utf-8",
            )

            stale = self._run(
                root,
                env,
                "planveyor_role_run_receipt_check .planveyor.role_runs/stale.json "
                "--run-id new-run --session-key planner "
                "--target-plan docs/plans/260101_0000_test_runtime.md --json",
            )
            self.assertNotEqual(stale.returncode, 0)
            self.assertEqual(json.loads(stale.stdout)["reason"], "run_id_mismatch")

            stale_session = self._run(
                root,
                env,
                "planveyor_role_run_receipt_check .planveyor.role_runs/stale.json "
                "--run-id old-run --session-key coder "
                "--target-plan docs/plans/260101_0000_test_runtime.md --json",
            )
            self.assertNotEqual(stale_session.returncode, 0)
            self.assertEqual(json.loads(stale_session.stdout)["reason"], "session_key_mismatch")

            stale_plan = self._run(
                root,
                env,
                "planveyor_role_run_receipt_check .planveyor.role_runs/stale.json "
                "--run-id old-run --session-key planner "
                "--target-plan docs/plans/260101_0001_other_runtime.md --json",
            )
            self.assertNotEqual(stale_plan.returncode, 0)
            self.assertEqual(json.loads(stale_plan.stdout)["reason"], "target_plan_mismatch")

            stale_status = self._run(
                root,
                env,
                "planveyor_role_run_receipt_check .planveyor.role_runs/stale.json "
                "--run-id old-run --session-key planner "
                "--target-plan docs/plans/260101_0000_test_runtime.md "
                "--pre-status '**Status:** Ready for Review' --json",
            )
            self.assertNotEqual(stale_status.returncode, 0)
            self.assertEqual(json.loads(stale_status.stdout)["reason"], "pre_status_mismatch")

            wrong_schema = self._run(
                root,
                env,
                "planveyor_role_run_receipt_check .planveyor.role_runs/wrong_schema.json --json",
            )
            self.assertNotEqual(wrong_schema.returncode, 0)
            self.assertEqual(json.loads(wrong_schema.stdout)["reason"], "wrong_schema_version")

            missing_canonical = self._run(
                root,
                env,
                "planveyor_role_run_receipt_check .planveyor.role_runs/missing_canonical.json --json",
            )
            self.assertNotEqual(missing_canonical.returncode, 0)
            missing_payload = json.loads(missing_canonical.stdout)
            self.assertEqual(missing_payload["reason"], "missing_required_fields")
            self.assertIn("elapsed_seconds", missing_payload["missing_fields"])

            timing_mismatch = self._run(
                root,
                env,
                "planveyor_role_run_receipt_check .planveyor.role_runs/timing_mismatch.json --json",
            )
            self.assertNotEqual(timing_mismatch.returncode, 0)
            self.assertEqual(json.loads(timing_mismatch.stdout)["reason"], "timing_alias_mismatch")

            timeout_mismatch = self._run(
                root,
                env,
                "planveyor_role_run_receipt_check .planveyor.role_runs/timeout_mismatch.json --json",
            )
            self.assertNotEqual(timeout_mismatch.returncode, 0)
            self.assertEqual(json.loads(timeout_mismatch.stdout)["reason"], "timeout_alias_mismatch")

            timeout_state_mismatch = self._run(
                root,
                env,
                "planveyor_role_run_receipt_check .planveyor.role_runs/timeout_state_mismatch.json --json",
            )
            self.assertNotEqual(timeout_state_mismatch.returncode, 0)
            self.assertEqual(json.loads(timeout_state_mismatch.stdout)["reason"], "timeout_state_mismatch")

            legacy = self._run(
                root,
                env,
                "planveyor_role_run_receipt_check .planveyor.role_runs/stale.json "
                "--run-id old-run --session-key planner "
                "--target-plan docs/plans/260101_0000_test_runtime.md --json",
            )
            self.assertEqual(legacy.returncode, 0, legacy.stderr)
            legacy_payload = json.loads(legacy.stdout)
            self.assertEqual(legacy_payload["readback_state"], "ok")
            self.assertEqual(legacy_payload["lifecycle_provider_contract_state"], "legacy_absent")

            legacy_source = json.loads(stale_path.read_text(encoding="utf-8"))
            for historical_value in (True, False):
                with self.subTest(historical_business_work_executed=historical_value):
                    historical_payload = dict(legacy_source)
                    historical_payload["business_work_executed"] = historical_value
                    historical_path = receipt_dir / f"historical-business-{str(historical_value).lower()}.json"
                    historical_path.write_text(json.dumps(historical_payload), encoding="utf-8")
                    historical = self._run(
                        root,
                        env,
                        f"planveyor_role_run_receipt_check {shlex.quote(str(historical_path))} --json",
                    )
                    self.assertEqual(historical.returncode, 0, historical.stderr)
                    self.assertEqual(json.loads(historical.stdout)["readback_state"], "ok")

            planner_sid = "00000000-0000-4000-8000-000000000306"
            fresh = self._run(
                root,
                env,
                "planveyor_plan_set docs/plans/260101_0000_test_runtime.md >/dev/null && "
                "planveyor_runner_set planner codex >/dev/null && "
                f"planveyor_session_set planner {planner_sid} runner=codex >/dev/null && "
                "planveyor_role_run planner --json",
            )
            self.assertEqual(fresh.returncode, 126, fresh.stderr)
            fresh_payload = json.loads(fresh.stdout)
            self.assertEqual(fresh_payload["readback_state"], "blocked")
            self.assertEqual(fresh_payload["readback_reason"], "unclassified_carriers")
            self.assertEqual(fresh_payload["retention_prune_state"], "blocked")
            self.assertEqual(fresh_payload["retention_prune_reason"], "unclassified_carriers")
            self.assertEqual(fresh_payload["session_key"], "planner")
            self.assertIn(".planveyor.role_runs", fresh_payload["receipt_path"])
            self.assertNotEqual(fresh_payload["run_id"], "old-run")

            current_receipt = json.loads(Path(fresh_payload["receipt_path"]).read_text(encoding="utf-8"))
            partial_receipt = dict(current_receipt)
            partial_receipt.pop("provider_error_code")
            partial_path = receipt_dir / "partial-lifecycle-provider.json"
            partial_path.write_text(json.dumps(partial_receipt), encoding="utf-8")
            partial = self._run(
                root,
                env,
                f"planveyor_role_run_receipt_check {shlex.quote(str(partial_path))} --json",
            )
            self.assertNotEqual(partial.returncode, 0)
            partial_payload = json.loads(partial.stdout)
            self.assertEqual(partial_payload["reason"], "partial_lifecycle_provider_contract")
            self.assertIn("provider_error_code", partial_payload["missing_fields"])

            impossible_lifecycle_receipts = {
                "not-started-success": {
                    "process_start_outcome": "not_started",
                },
                "success-with-nonzero-exit": {
                    "exit_code": 1,
                },
                "failed-with-zero-exit": {
                    "state": "failed",
                    "success": False,
                    "exit_code": 0,
                    "non_green_reason": "exit_code_0",
                },
                "not-started-timeout": {
                    "process_start_outcome": "not_started",
                    "state": "timeout",
                    "success": False,
                    "exit_code": 124,
                    "timed_out": True,
                    "terminated_by_timeout": True,
                    "non_green_reason": "timeout",
                },
                "not-started-interrupted": {
                    "process_start_outcome": "not_started",
                    "state": "interrupted",
                    "success": False,
                    "exit_code": 130,
                    "interrupted": True,
                    "non_green_reason": "interrupted",
                },
                "started-precondition-failure": {
                    "state": "precondition_failed",
                    "success": False,
                    "exit_code": 125,
                    "non_green_reason": "preflight_failed",
                },
                "not-started-non-spawn-failure": {
                    "process_start_outcome": "not_started",
                    "state": "failed",
                    "success": False,
                    "exit_code": 23,
                    "non_green_reason": "exit_code_23",
                },
                "missing-pointer-with-started-provider-failure": {
                    "sid_before": "N/A (why=missing session id)",
                    "sid_after": "N/A (why=missing session id)",
                    "session_pointer_relation": "missing",
                    "process_start_outcome": "started",
                    "state": "failed",
                    "success": False,
                    "exit_code": 23,
                    "non_green_reason": "exit_code_23",
                    "provider_http_status": "unknown",
                    "provider_error_code": "unknown",
                    "provider_error_class": "unknown",
                    "provider_retryability": "unknown",
                },
                "missing-session-reason-with-present-pointer": {
                    "process_start_outcome": "not_started",
                    "state": "precondition_failed",
                    "success": False,
                    "exit_code": 125,
                    "non_green_reason": "missing_session_sid",
                },
                "missing-pointer-with-spawn-failure": {
                    "sid_before": "N/A (why=missing session id)",
                    "sid_after": "N/A (why=missing session id)",
                    "session_pointer_relation": "missing",
                    "process_start_outcome": "not_started",
                    "state": "failed",
                    "success": False,
                    "exit_code": 125,
                    "non_green_reason": "exit_code_125",
                },
            }
            for name, updates in impossible_lifecycle_receipts.items():
                with self.subTest(name=name):
                    impossible_receipt = dict(current_receipt)
                    impossible_receipt.update(updates)
                    impossible_path = receipt_dir / f"contradictory-{name}.json"
                    impossible_path.write_text(json.dumps(impossible_receipt), encoding="utf-8")
                    impossible = self._run(
                        root,
                        env,
                        f"planveyor_role_run_receipt_check {shlex.quote(str(impossible_path))} --json",
                    )
                    self.assertNotEqual(impossible.returncode, 0)
                    self.assertEqual(
                        json.loads(impossible.stdout)["reason"],
                        "lifecycle_provider_contract_contradiction",
                    )

            provider_contradiction_receipt = dict(current_receipt)
            provider_contradiction_receipt.update(
                {
                    "provider_http_status": "529",
                    "provider_error_code": "1305",
                    "provider_error_class": "overload",
                    "provider_retryability": "retryable",
                }
            )
            provider_contradiction_path = receipt_dir / "contradictory-provider-on-success.json"
            provider_contradiction_path.write_text(
                json.dumps(provider_contradiction_receipt),
                encoding="utf-8",
            )
            provider_contradiction = self._run(
                root,
                env,
                f"planveyor_role_run_receipt_check {shlex.quote(str(provider_contradiction_path))} --json",
            )
            self.assertNotEqual(provider_contradiction.returncode, 0)
            self.assertEqual(
                json.loads(provider_contradiction.stdout)["reason"],
                "lifecycle_provider_contract_contradiction",
            )

    def test_role_run_records_post_wrapper_sid_when_session_is_replaced(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_role_run_sid_after_") as tmpdir:
            root, env, _ = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
            self._write_runtime_plan(root, status="In progress")
            sid_before = "00000000-0000-4000-8000-000000000307"
            sid_after = "00000000-0000-4000-8000-000000000308"

            result = self._run(
                root,
                env,
                "planveyor_plan_set docs/plans/260101_0000_test_runtime.md >/dev/null && "
                "planveyor_runner_set reviewer codex >/dev/null && "
                f"planveyor_session_set reviewer_code_risk {sid_before} runner=codex >/dev/null && "
                "planveyor_reviewer_code_risk() { "
                f"planveyor_session_set reviewer_code_risk {sid_after} runner=codex >/dev/null; "
                "} && "
                "planveyor_role_run reviewer_code_risk --json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["session_key"], "reviewer_code_risk")
            self.assertEqual(payload["sid_before"], sid_before)
            self.assertEqual(payload["sid_after"], sid_after)
            self.assertEqual(payload["sid"], sid_after)
            self.assertEqual(payload["session_pointer_relation"], "replaced")
            self.assertEqual(payload["process_start_outcome"], "started")
            receipt_payload = json.loads(Path(payload["receipt_path"]).read_text(encoding="utf-8"))
            self.assertEqual(receipt_payload["sid_before"], sid_before)
            self.assertEqual(receipt_payload["sid_after"], sid_after)
            self.assertEqual(receipt_payload["sid"], sid_after)

    def test_role_run_exposes_current_run_carrier_to_role_process(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_role_run_carrier_") as tmpdir:
            root, env, _ = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
            self._write_runtime_plan(root, status="In progress")
            planner_sid = "00000000-0000-4000-8000-000000000309"
            marker = root / ".tmp" / "role-run-carrier-env.txt"

            result = self._run(
                root,
                env,
                "planveyor_plan_set docs/plans/260101_0000_test_runtime.md >/dev/null && "
                "planveyor_runner_set planner codex >/dev/null && "
                f"planveyor_session_set planner {planner_sid} runner=codex >/dev/null && "
                "planveyor_planner() { "
                "mkdir -p .tmp; "
                'print -r -- "PLANVEYOR_ROLE_RUN_ID=$PLANVEYOR_ROLE_RUN_ID" > .tmp/role-run-carrier-env.txt; '
                'print -r -- "PLANVEYOR_ROLE_RUN_RECEIPT_PATH=$PLANVEYOR_ROLE_RUN_RECEIPT_PATH" >> .tmp/role-run-carrier-env.txt; '
                'print -r -- "PLANVEYOR_ROLE_RUN_LATEST_RECEIPT_PATH=$PLANVEYOR_ROLE_RUN_LATEST_RECEIPT_PATH" >> .tmp/role-run-carrier-env.txt; '
                'print -r -- "PLANVEYOR_ROLE_RUN_OUTPUT_DIR=$PLANVEYOR_ROLE_RUN_OUTPUT_DIR" >> .tmp/role-run-carrier-env.txt; '
                'print -r -- "PLANVEYOR_ROLE_RUN_SESSION_KEY=$PLANVEYOR_ROLE_RUN_SESSION_KEY" >> .tmp/role-run-carrier-env.txt; '
                'print -r -- "PLANVEYOR_ROLE_RUN_TARGET_PLAN=$PLANVEYOR_ROLE_RUN_TARGET_PLAN" >> .tmp/role-run-carrier-env.txt; '
                "} && "
                "planveyor_role_run planner --json",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["state"], "success")
            carrier = dict(
                line.split("=", 1)
                for line in marker.read_text(encoding="utf-8").splitlines()
                if "=" in line
            )
            self.assertEqual(carrier["PLANVEYOR_ROLE_RUN_ID"], payload["run_id"])
            self.assertEqual(carrier["PLANVEYOR_ROLE_RUN_RECEIPT_PATH"], payload["receipt_path"])
            self.assertEqual(carrier["PLANVEYOR_ROLE_RUN_LATEST_RECEIPT_PATH"], payload["latest_receipt_path"])
            self.assertEqual(carrier["PLANVEYOR_ROLE_RUN_SESSION_KEY"], "planner")
            self.assertEqual(carrier["PLANVEYOR_ROLE_RUN_TARGET_PLAN"], "docs/plans/260101_0000_test_runtime.md")
            self.assertTrue(carrier["PLANVEYOR_ROLE_RUN_OUTPUT_DIR"].endswith(f"/.tmp/planveyor_role_runs/{payload['run_id']}"))
            # Carrier is identity only: final receipt state stays post-exit and
            # is not part of the in-run carrier env.
            self.assertNotIn("PLANVEYOR_ROLE_RUN_STATE", carrier)

    def test_role_run_carrier_is_isolated_from_manager_architect_paths(self) -> None:
        # Negative isolation proof (source 2233 risk:R2): the PLANVEYOR_ROLE_RUN_*
        # carrier that planveyor_role_run injects into the supervised role process
        # must NOT reach Manager/Architect init/resume paths (they never call
        # _planveyor_role_run_supervise). Fixture env is sanitized of ambient
        # PLANVEYOR_ROLE_RUN_* (see _prepare_repo), so this checks helper-injection
        # leak only, not caller-exported env (AC #4).
        with tempfile.TemporaryDirectory(prefix="planveyor_carrier_isolation_") as tmpdir:
            root, env, log_dir = self._prepare_repo(
                tmpdir,
                sid_map=SUCCESS_SIDS,
                runtime_mode="legacy_complete",
            )
            runtime_manifest = self._assert_legacy_complete_runtime_identity(root, env)
            self._write_runtime_plan(root, status="In progress")

            result = self._run(
                root,
                env,
                "planveyor_plan_set docs/plans/260101_0000_test_runtime.md >/dev/null && "
                "planveyor_runner_set planner codex >/dev/null && "
                f"planveyor_session_set planner {SUCCESS_SIDS['planner']} runner=codex >/dev/null && "
                "planveyor_role_run planner --json >/dev/null && "
                "planveyor_arch_init >/dev/null && "
                "planveyor_arch_resume >/dev/null && "
                "planveyor_manager_init >/dev/null && "
                "planveyor_manager_resume >/dev/null",
            )

            self.assertEqual(result.returncode, 0, result.stderr)

            calls = self._codex_calls(log_dir)
            # Positive contrast: the supervised planner process launched by
            # planveyor_role_run DOES carry the injected carrier.
            planner_carrier = [
                key
                for call in calls
                if str(call["role"]) == "planner"
                for key in (call.get("role_run_env_keys") or [])
            ]
            self.assertTrue(
                planner_carrier,
                "supervised planner process should carry PLANVEYOR_ROLE_RUN_* carrier",
            )
            # Negative: across every other fake-codex call (Manager/Architect
            # init AND resume — resume calls log role="" — plus any other
            # non-supervised path), no call may carry the carrier. These paths
            # never call _planveyor_role_run_supervise, so they must not inherit it.
            leaked = [
                call
                for call in calls
                if call.get("role_run_env_keys") and str(call["role"]) != "planner"
            ]
            self.assertEqual(
                leaked,
                [],
                f"PLANVEYOR_ROLE_RUN_* carrier leaked to non-planner call(s): {leaked}",
            )
            self._assert_legacy_complete_runtime_identity(
                root,
                env,
                expected_manifest=runtime_manifest,
            )


    def test_runner_matrix_readback_and_unknown_runner_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_init_capture_") as tmpdir:
            root, env, _ = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
            result = self._run(
                root,
                env,
                "planveyor_runner_set planner claude >/dev/null && "
                "planveyor_runner_set coder codex >/dev/null && "
                "planveyor_runner_set reviewer claude >/dev/null && "
                "planveyor_runner_set manager codex >/dev/null && "
                "planveyor_runner_set architect codex >/dev/null && "
                "planveyor_runner planner && planveyor_runner coder && "
                "planveyor_runner reviewer && planveyor_runner manager && planveyor_runner architect",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.splitlines(), ["claude", "codex", "claude", "codex", "codex"])

            unknown = self._run(root, env, "planveyor_runner_set coder bogus")
            self.assertNotEqual(unknown.returncode, 0)
            self.assertIn("Usage: planveyor_runner_set", unknown.stderr)

            unsupported = self._run(root, env, "planveyor_runner_set coder claude")
            self.assertNotEqual(unsupported.returncode, 0)
            self.assertIn("Unsupported runner for role=coder: claude", unsupported.stderr)
            self.assertIn("coder: codex", unsupported.stderr)


    def test_custom_reviewer_lane_init_uses_distinct_session_keys_and_runner_matrix(self) -> None:
        sid_map = {**SUCCESS_SIDS, **REVIEWER_LANE_SIDS}
        lanes = ("reviewer_code_risk", "reviewer_code_contracts")
        with tempfile.TemporaryDirectory(prefix="planveyor_init_capture_") as tmpdir:
            root, env, log_dir = self._prepare_repo(tmpdir, sid_map=sid_map)
            env["PLANVEYOR_CLAUDE_MODEL"] = "fixture-claude-reviewer"
            env["PLANVEYOR_CLAUDE_EFFORT"] = "fixture-claude-effort"

            result = self._run(
                root,
                env,
                "planveyor_runner_set reviewer claude >/dev/null && "
                "planveyor_reviewer_code_risk_init >/dev/null",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            contracts_result = self._run(root, env, "planveyor_reviewer_code_contracts_init >/dev/null")
            self.assertEqual(contracts_result.returncode, 0, contracts_result.stderr)
            self.assertFalse((root / ".planveyor.session.reviewer").exists())
            for lane in lanes:
                session_file = root / f".planveyor.session.{lane}"
                self.assertTrue(session_file.exists(), lane)
                sid = session_file.read_text(encoding="utf-8").splitlines()[-1]
                self.assertRegex(sid, r"^[0-9a-f-]{36}$")
                meta = json.loads(
                    (root / ".planveyor.init_runs" / "by_sid" / sid / "meta.json").read_text(encoding="utf-8")
                )
                self.assertEqual(meta["role"], "reviewer")
                self.assertEqual(meta["session_key"], lane)
                self.assertEqual(meta["runner"], "claude")
                self.assertEqual(meta["profile"], "direct_child")
                self.assertEqual(meta["model"], "fixture-claude-reviewer")
                self.assertEqual(meta["provider_home_state"], "unavailable")
                self.assertNotIn("codex_home", meta)
                self.assertEqual(meta["runner_alias"], "claude")
                self.assertEqual(meta["configured_model_id"], "fixture-claude-reviewer")
                self.assertEqual(meta["model_id_state"], "configured_explicit")
                self.assertEqual(meta["configured_effort"], "fixture-claude-effort")
                self.assertEqual(meta["effort_state"], "configured_explicit")

            calls = self._claude_calls(log_dir)
            self.assertEqual(len(calls), 2)
            self.assertEqual([call["command"] for call in calls], ["claude", "claude"])
            self.assertEqual([call["role"] for call in calls], ["reviewer", "reviewer"])
            self.assertEqual([call["lane"] for call in calls], list(lanes))
            for call in calls:
                self.assertEqual(call["argv"][:5], ["--model", "fixture-claude-reviewer", "--effort", "fixture-claude-effort", "-p"])
                self.assertIn("--permission-mode", call["argv"])
                self.assertIn("acceptEdits", call["argv"])
                self.assertIn("REVIEWER_PROFILE=direct_child", call["prompt"])

    def test_custom_reviewer_risk_runtime_uses_lane_session_key(self) -> None:
        with tempfile.TemporaryDirectory(prefix="planveyor_init_capture_") as tmpdir:
            root, env, log_dir = self._prepare_repo(tmpdir, sid_map=SUCCESS_SIDS)
            env["PLANVEYOR_CLAUDE_MODEL"] = "fixture-claude-reviewer"
            env["PLANVEYOR_CLAUDE_EFFORT"] = "fixture-claude-effort"
            plan_path = root / "docs" / "plans" / "260101_0000_test_reviewer_lane.md"
            plan_path.parent.mkdir(parents=True, exist_ok=True)
            plan_path.write_text(
                textwrap.dedent(
                    """\
                    # Plan: reviewer lane runtime test

                    **Date:** 2026-01-01 00:00 MSK
                    **Plan type:** dev
                    **Status:** Ready for Review

                    ## Evidence
                    """
                ),
                encoding="utf-8",
            )
            lane_sid = "00000000-0000-4000-8000-000000000206"

            result = self._run(
                root,
                env,
                "planveyor_plan_set docs/plans/260101_0000_test_reviewer_lane.md >/dev/null && "
                "planveyor_runner_set reviewer claude >/dev/null && "
                f"planveyor_session_set reviewer_code_risk {lane_sid} runner=claude >/dev/null && "
                "planveyor_reviewer_code_risk >/dev/null",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((root / ".planveyor.session.reviewer").exists())
            calls = self._claude_calls(log_dir)
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0]["sid"], lane_sid)
            self.assertEqual(calls[0]["role"], "reviewer")
            self.assertEqual(calls[0]["lane"], "reviewer_code_risk")
            argv = [str(item) for item in calls[0]["argv"]]
            self.assertIn("--resume", argv)
            self.assertNotIn("--session-id", argv)

    def test_public_owner_runbook_documents_neutral_init_run_artifact_lookup(self) -> None:
        text = OWNER_RUNBOOK.read_text(encoding="utf-8")

        _before, heading, remainder = text.partition("## Init-run artifacts\n")
        self.assertTrue(heading)
        section, next_heading, _after = remainder.partition("\n## Bounded handoffs\n")
        self.assertTrue(next_heading)
        self.assertIn("`.planveyor.init_runs/by_sid/<SID>/`", section)
        self.assertIn("`.planveyor.init_runs/pending/<role>/<run_id>/`", section)
        self.assertIn("run.log", section)
        self.assertIn("meta.json", section)
        self.assertIn("только attach pointer", section)
        self.assertIn("не доказывает, что init или role run завершился успешно", section)
        self.assertIn("не охватывает", section)
        for unsupported_surface in ("resume", "live", "tee", "stdout/stderr", "interactive TTY"):
            with self.subTest(unsupported_surface=unsupported_surface):
                self.assertIn(unsupported_surface, section)



if __name__ == "__main__":
    unittest.main()

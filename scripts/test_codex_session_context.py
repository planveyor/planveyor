#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from textwrap import dedent
from unittest import mock

try:
    from scripts.test_support.process_contract_fixtures import run_zsh_fixture
    from scripts.test_contract_authority_support import AuthorityFixture, commit_all, write
except ModuleNotFoundError:
    from test_support.process_contract_fixtures import run_zsh_fixture
    from test_contract_authority_support import AuthorityFixture, commit_all, write


MODULE_PATH = Path(__file__).with_name("codex_session_context.py")
SPEC = importlib.util.spec_from_file_location("codex_session_context", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

REPO_ROOT = MODULE_PATH.parent.parent


def _write_file(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class CodexSessionContextTests(unittest.TestCase):
    def _fake_stats_script(self, root: Path, text: str) -> Path:
        script = root / "fake_stats.py"
        _write_file(
            script,
            dedent(
                f"""\
                #!/usr/bin/env python3
                import sys
                if "--sid" not in sys.argv:
                    raise SystemExit(2)
                print({text!r})
                """
            ),
        )
        return script

    def test_markdown_prefers_env_and_continued_relation_for_existing_plan_section(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_path = root / "docs/plans/fixture.md"
            _write_file(
                plan_path,
                "# Plan: fixture\n\n## Plan provenance / session context\n- Relation: `created-here`\n",
            )
            _write_file(root / ".planveyor.session.coder", "# session\nsid-123\n")
            stats_script = self._fake_stats_script(
                root,
                "parent_thread_id=parent-456\noriginator=codex_exec\nsource=exec\n",
            )
            env = {
                "ROLE": "Coder",
                "CODEX_THREAD_ID": "thread-123",
            }

            with mock.patch.dict(os.environ, env, clear=False):
                args = MODULE.parse_args(
                    [
                        "--root",
                        str(root),
                        "--plan-path",
                        str(plan_path),
                        "--stats-script",
                        str(stats_script),
                        "--captured-at",
                        "2026-03-30T03:00:00Z",
                    ]
                )
                context = MODULE.collect_context(args)
                rendered = MODULE.render_markdown(context, section="plan")

        self.assertEqual(context.relation, "continued-here")
        self.assertEqual(context.thread_id, "thread-123")
        self.assertEqual(context.parent_thread_id, "parent-456")
        self.assertEqual(context.session_sid, "sid-123")
        self.assertEqual(context.launch_surface, "codex-cli")
        self.assertEqual(context.captured_from, "env")
        self.assertIn("## Plan provenance / session context", rendered)
        self.assertIn("- Session SID: `sid-123`", rendered)
        self.assertIn("- Captured at: `2026-03-30T03:00:00Z`", rendered)

    def test_kv_uses_wrapper_receipt_when_env_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            receipt_path = root / ".planveyor.run_receipt.manager_custom_pipeline"
            _write_file(
                receipt_path,
                dedent(
                    """\
                    thread_id=thread-from-receipt
                    parent_thread_id=parent-from-receipt
                    launch_surface=codex_exec
                    pipeline_mode=manager_custom_pipeline
                    """
                ),
            )
            with mock.patch.dict(
                os.environ,
                {"CODEX_THREAD_ID": "", "CODEX_PARENT_THREAD_ID": "", "ROLE": ""},
                clear=False,
            ):
                args = MODULE.parse_args(
                    [
                        "--root",
                        str(root),
                        "--run-receipt-path",
                        str(receipt_path),
                        "--format",
                        "kv",
                        "--captured-at",
                        "2026-03-30T03:10:00Z",
                    ]
                )
                context = MODULE.collect_context(args)
                rendered = MODULE.render_kv(context)

        self.assertEqual(context.thread_id, "thread-from-receipt")
        self.assertEqual(context.parent_thread_id, "parent-from-receipt")
        self.assertEqual(context.launch_surface, "manager-custom-pipeline")
        self.assertEqual(context.captured_from, "wrapper-session-file")
        self.assertIn("thread_id=thread-from-receipt", rendered)
        self.assertIn("launch_surface=manager-custom-pipeline", rendered)

    def test_packet_section_uses_imported_from_packet_subset(self) -> None:
        args = MODULE.parse_args(
            [
                "--packet-path",
                "docs/rollout_packets/example.md",
                "--thread-id",
                "thread-packet",
                "--session-sid",
                "sid-packet",
                "--launch-surface",
                "codex-cli",
                "--captured-from",
                "packet-import",
                "--captured-at",
                "2026-03-30T03:20:00Z",
            ]
        )
        context = MODULE.collect_context(args)
        rendered = MODULE.render_markdown(context, section="packet")

        self.assertEqual(context.relation, "imported-from-packet")
        self.assertIn("## Source provenance", rendered)
        self.assertNotIn("Parent thread ID", rendered)
        self.assertIn("Target import expectation", rendered)

    def test_wrapper_surface_shells_into_python_helper(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _write_file(root / ".planveyor.session.coder", "# session\nsid-999\n")
            stats_script = self._fake_stats_script(
                root,
                "parent_thread_id=\noriginator=codex_exec\nsource=exec\n",
            )
            fixture_env = {
                "PLANVEYOR_ROOT": str(REPO_ROOT),
                "ROLE": "Coder",
                "CODEX_THREAD_ID": "thread-wrapper",
            }
            command = dedent(
                f"""\
                source "{REPO_ROOT}/scripts/planveyor.zsh"
                planveyor_plan_provenance_context \
                  --root "{root}" \
                  --stats-script "{stats_script}" \
                  --captured-at "2026-03-30T03:30:00Z" \
                  --format kv
                """
            )
            result = run_zsh_fixture(
                command,
                cwd=root,
                path=os.environ.get("PATH", os.defpath),
                pybin=sys.executable,
                fixture_env=fixture_env,
                capture_output=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("thread_id=thread-wrapper", result.stdout)
        self.assertIn("session_sid=sid-999", result.stdout)
        self.assertIn("captured_from=env", result.stdout)

    def test_json_output_is_machine_readable(self) -> None:
        args = MODULE.parse_args(
            [
                "--thread-id",
                "thread-json",
                "--session-sid",
                "sid-json",
                "--launch-surface",
                "codex-cli",
                "--captured-from",
                "manual-owner",
                "--captured-at",
                "2026-03-30T03:40:00Z",
                "--format",
                "json",
            ]
        )
        context = MODULE.collect_context(args)
        payload = json.loads(json.dumps(MODULE.asdict(context), ensure_ascii=False))

        self.assertEqual(payload["thread_id"], "thread-json")
        self.assertEqual(payload["session_sid"], "sid-json")
        self.assertEqual(payload["captured_from"], "manual-owner")


class ProvenanceFacadeProjectRootTests(unittest.TestCase):
    """The public entrypoint stamps from the selected project, not the runtime."""

    def _run_public(
        self,
        entry: Path,
        project: Path,
        environment: dict[str, str],
        *arguments: str,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(entry), "--project", str(project), *arguments],
            cwd=project,
            env=environment,
            stdin=subprocess.DEVNULL,
            text=True,
            capture_output=True,
            check=False,
            timeout=120,
        )

    def test_public_stamp_reads_session_pointer_from_project_root(self) -> None:
        with AuthorityFixture(identity="planveyor") as fixture:
            entry = write(
                fixture.runtime_root,
                "bin/planveyor",
                (REPO_ROOT / "bin" / "planveyor").read_bytes(),
                executable=True,
            )
            commit_all(fixture.runtime_root, "public provenance facade")
            target = fixture.target_root
            plan_rel = "docs/plans/260929_1200_provenance_fixture.md"
            write(target, plan_rel, "# Plan: provenance fixture\n")
            commit_all(target, "provenance plan fixture")
            write(target, ".planveyor.session.architect", "# fixture\ntarget-sid-architect\n")
            environment = fixture.environment()
            state_root = fixture.root / "state"
            state_root.mkdir()
            environment["PLANVEYOR_STATE_ROOT"] = str(state_root)
            stamp_arguments = (
                "planveyor_plan_provenance_stamp",
                plan_rel,
                "--session-key",
                "architect",
                "--captured-at",
                "2026-09-29T09:00:00Z",
            )

            target_only = self._run_public(entry, target, environment, *stamp_arguments)

            # A same-named pointer inside the runtime checkout must not leak
            # into the consumer's provenance, while an explicit --root still
            # selects the caller's own root.
            write(fixture.runtime_root, ".planveyor.session.architect", "# decoy\nruntime-sid-decoy\n")
            commit_all(fixture.runtime_root, "runtime decoy session pointer")
            with_decoy = self._run_public(entry, target, environment, *stamp_arguments)
            explicit_root = self._run_public(
                entry,
                target,
                environment,
                "planveyor_plan_provenance_context",
                "--root",
                str(fixture.runtime_root),
                "--session-key",
                "architect",
                "--captured-at",
                "2026-09-29T09:00:00Z",
                "--format",
                "kv",
            )

        for result in (target_only, with_decoy, explicit_root):
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("- Session SID: `target-sid-architect`", target_only.stdout)
        self.assertIn("- Session SID: `target-sid-architect`", with_decoy.stdout)
        self.assertNotIn("runtime-sid-decoy", with_decoy.stdout)
        self.assertIn("session_sid=runtime-sid-decoy", explicit_root.stdout)

    def test_public_facade_passes_only_a_set_caller_thread_id(self) -> None:
        with AuthorityFixture(identity="planveyor") as fixture:
            entry = write(
                fixture.runtime_root,
                "bin/planveyor",
                (REPO_ROOT / "bin" / "planveyor").read_bytes(),
                executable=True,
            )
            commit_all(fixture.runtime_root, "public provenance facade")
            target = fixture.target_root
            plan_rel = "docs/plans/260929_1200_thread_fixture.md"
            write(target, plan_rel, "# Plan: thread fixture\n")
            commit_all(target, "thread plan fixture")
            environment = fixture.environment()
            state_root = fixture.root / "state"
            state_root.mkdir()
            environment["PLANVEYOR_STATE_ROOT"] = str(state_root)
            stamp_arguments = (
                "planveyor_plan_provenance_stamp",
                plan_rel,
                "--captured-at",
                "2026-09-29T09:00:00Z",
            )

            without_thread = self._run_public(entry, target, environment, *stamp_arguments)
            empty_thread = self._run_public(
                entry, target, {**environment, "CODEX_THREAD_ID": ""}, *stamp_arguments
            )
            with_thread = self._run_public(
                entry,
                target,
                {
                    **environment,
                    "CODEX_THREAD_ID": "thread-facade-caller",
                    "CODEX_PARENT_THREAD_ID": "parent-not-forwarded",
                },
                *stamp_arguments,
            )

        for result in (without_thread, empty_thread, with_thread):
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("- Thread ID: `thread-facade-caller`", with_thread.stdout)
        self.assertIn("- Captured from: `env`", with_thread.stdout)
        self.assertNotIn("parent-not-forwarded", with_thread.stdout)
        for result in (without_thread, empty_thread):
            self.assertIn("- Thread ID: `N/A (why=CODEX_THREAD_ID", result.stdout)
            self.assertNotIn("thread-facade-caller", result.stdout)


if __name__ == "__main__":
    unittest.main()

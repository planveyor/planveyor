#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import textwrap
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
PLANVEYOR_ZSH = REPO_ROOT / "scripts" / "planveyor.zsh"
COLLAB_PROMPT = REPO_ROOT / "docs" / "tools" / "prompts" / "manager_collab_pipeline.md"
MERGE_PROMPT = REPO_ROOT / "docs" / "tools" / "prompts" / "manager_collab_merge_pipeline.md"


class PlanveyorCodexAgentRoleConfigTests(unittest.TestCase):
    def _assert_home_ensure_preserves(
        self,
        target: Path,
        *,
        owner_home: Path,
        extra_env: dict[str, str] | None = None,
        expected_absent: tuple[str, ...] = (),
    ) -> None:
        def snapshot() -> dict[str, bytes]:
            return {
                str(path.relative_to(target)): path.read_bytes()
                for path in sorted(target.rglob("*"))
                if path.is_file() and not path.is_symlink()
            }

        before = snapshot()
        with tempfile.TemporaryDirectory(
            prefix="planveyor_owned_codex_cli_", dir=target.parent
        ) as cli_tmpdir:
            cli_bin = Path(cli_tmpdir) / "bin"
            cli_bin.mkdir()
            child_tmp = (Path(cli_tmpdir) / "child-tmp").resolve()
            child_tmp.mkdir()
            child_observation = child_tmp / "codex-agent-roles-child-environment"
            cli = cli_bin / "codex"
            cli.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            cli.chmod(0o755)
            for name in ("python3", f"python{sys.version_info.major}.{sys.version_info.minor}"):
                (cli_bin / name).symlink_to(sys.executable)

            env = os.environ.copy()
            env.update(
                {
                    "HOME": str(owner_home),
                    "PATH": f"{cli_bin}:/usr/bin:/bin:/usr/sbin:/sbin",
                    "PLANVEYOR_CODEX_HOME": str(target),
                    "PYBIN": sys.executable,
                }
            )
            env.pop("CODEX_HOME", None)
            env.pop("PLANVEYOR_CODEX_MANAGE_AGENT_ROLES", None)
            env.pop("PLANVEYOR_CODEX_NORMALIZE_MODELS", None)
            if extra_env:
                env.update(extra_env)
            env["TMPDIR"] = str(child_tmp)
            env["TMPPREFIX"] = str(child_tmp / "zsh")

            result = subprocess.run(
                [
                    "/bin/zsh",
                    "-dfc",
                    f'print -r -- "$TMPDIR|$TMPPREFIX" > {shlex.quote(str(child_observation))}; '
                    f"source {shlex.quote(str(PLANVEYOR_ZSH))} && _planveyor_codex_home_ensure",
                ],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, f"{target.resolve()}\n")
            self.assertEqual(result.stderr, "")
            self.assertEqual(
                child_observation.read_text(encoding="utf-8"),
                f"{child_tmp}|{child_tmp / 'zsh'}\n",
            )
        self.assertEqual(snapshot(), before)
        for relative in expected_absent:
            self.assertFalse((target / relative).exists(), relative)

    def test_collab_prompt_dispatches_the_configured_role_types(self) -> None:
        text = COLLAB_PROMPT.read_text(encoding="utf-8")
        self.assertIn("`architect` → `agent_type=architect`", text)
        self.assertIn("`planner` → `agent_type=planner`", text)
        self.assertIn("`coder` → `agent_type=coder`", text)
        self.assertIn("`planner` (`agent_type=planner`) и `coder` (`agent_type=coder`)", text)
        self.assertNotIn("`planner` → `agent_type=default`", text)
        self.assertIn('fork_turns="none"', text)
        self.assertIn("followup_task", text)
        self.assertIn("list_agents", text)
        self.assertIn("planner_terra_ultra_v2", text)
        self.assertIn("coder_terra_ultra_v2", text)
        self.assertIn("/root/architect_sol_xhigh_v2", text)
        self.assertIn("adopt-existing-v2", text)
        self.assertIn("до любого spawn", text)
        self.assertIn("returned `task_name` должен быть exact expected canonical path", text)
        self.assertNotIn("оканчиваться exact expected component", text)
        self.assertNotIn("send_input(", text)
        self.assertNotIn("wait_agent(ids", text)
        self.assertNotIn("close_agent(id", text)

        merge_text = MERGE_PROMPT.read_text(encoding="utf-8")
        self.assertIn('fork_turns="none"', merge_text)
        self.assertIn("followup_task", merge_text)
        self.assertIn("list_agents", merge_text)
        self.assertIn("coder_terra_ultra_v2", merge_text)
        self.assertIn("adopt-first materialization contract", merge_text)
        self.assertIn("same-name spawn поверх существующей task запрещён", merge_text)
        self.assertIn("`architect_sol_xhigh_v2` → `agent_type=architect`", merge_text)
        self.assertIn("`coder_terra_ultra_v2` → `agent_type=coder`", merge_text)
        self.assertIn(
            "`reviewer_code_risk_sol_xhigh_v2` → `agent_type=reviewer_code_risk`",
            merge_text,
        )
        self.assertIn(
            "`reviewer_code_contracts_sol_xhigh_v2` → `agent_type=reviewer_code_contracts`",
            merge_text,
        )
        self.assertNotIn("send_input(", merge_text)
        self.assertNotIn("wait_agent(ids", merge_text)
        self.assertNotIn("close_agent(id", merge_text)

    def test_home_ensure_selects_consumer_home_without_rewriting_agent_roles(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            target = home / "consumer-codex"
            agents = target / "agents"
            agents.mkdir(parents=True)
            (target / "config.toml").write_text(
                'model = "owner-selected-model"\n',
                encoding="utf-8",
            )
            (agents / "worker.toml").write_text(
                'name = "owner-worker"\nmodel = "owner-model"\n',
                encoding="utf-8",
            )

            self._assert_home_ensure_preserves(
                target,
                owner_home=home,
                extra_env={
                    "PLANVEYOR_CODEX_MANAGE_AGENT_ROLES": "1",
                    "PLANVEYOR_CODEX_NORMALIZE_MODELS": "1",
                },
                expected_absent=("agents/planner.toml",),
            )

    def test_existing_home_startup_reconcile_preserves_root_model_runtime_and_extra_agents(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            agents = home / "agents"
            agents.mkdir()
            config_path = home / "config.toml"
            config_path.write_text(
                textwrap.dedent(
                    '''
                    model = "owner-selected-root-model"

                    [features]
                    multi_agent = true

                    [features.multi_agent_v2]
                    enabled = false
                    hide_spawn_agent_metadata = true
                    tool_namespace = "collaboration"
                    max_concurrent_threads_per_session = 6
                    usage_hint_text = "preserve-v1-runtime"

                    [agents]
                    enabled = true
                    max_concurrent_threads_per_session = 6

                    [agents.worker]
                    description = "planveyor: agent_type=worker (Generic worker)"
                    config_file = "agents/worker.toml"

                    [agents.glm53]
                    description = "owner-managed extra agent"
                    config_file = "agents/glm53.toml"
                    '''
                ).lstrip(),
                encoding="utf-8",
            )
            (agents / "worker.toml").write_text(
                'name = "owner-worker"\nmodel = "owner-model"\n', encoding="utf-8"
            )
            (agents / "glm53.toml").write_text(
                'name = "owner-glm53"\nmodel = "owner-model"\n', encoding="utf-8"
            )

            self._assert_home_ensure_preserves(
                home,
                owner_home=home / "owner-home",
                extra_env={
                    "PLANVEYOR_CODEX_MANAGE_AGENT_ROLES": "1",
                    "PLANVEYOR_CODEX_NORMALIZE_MODELS": "1",
                },
                expected_absent=(
                    "agents/default.toml",
                    "agents/planner.toml",
                    "agents/architect.toml",
                    "agents/coder.toml",
                ),
            )

    def test_home_ensure_leaves_invalid_consumer_toml_opaque(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            target = home / "target"
            target.mkdir()
            config_path = target / "config.toml"
            original = '[features\nmulti_agent = false\n'
            config_path.write_text(original, encoding="utf-8")

            self._assert_home_ensure_preserves(
                target,
                owner_home=home,
                extra_env={"PLANVEYOR_CODEX_MANAGE_AGENT_ROLES": "1"},
                expected_absent=("agents",),
            )

    def test_home_ensure_leaves_invalid_managed_role_toml_opaque(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            target = home / "target"
            agents_dir = target / "agents"
            agents_dir.mkdir(parents=True)
            config_path = target / "config.toml"
            original_config = textwrap.dedent(
                '''
                model = "owner-selected-root-model"

                [agents.worker]
                description = "planveyor: agent_type=worker (Generic worker)"
                config_file = "agents/worker.toml"
                '''
            ).lstrip()
            invalid_role = '# planveyor: agent_type=worker (Generic worker)\nname = "worker"\ndeveloper_instructions = """unterminated\n'
            config_path.write_text(original_config, encoding="utf-8")
            worker_path = agents_dir / "worker.toml"
            worker_path.write_text(invalid_role, encoding="utf-8")

            self._assert_home_ensure_preserves(
                target,
                owner_home=home,
                extra_env={"PLANVEYOR_CODEX_NORMALIZE_MODELS": "1"},
                expected_absent=("agents/planner.toml",),
            )

    def test_unmanaged_home_preserves_custom_agent_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            agents = home / "agents"
            agents.mkdir()
            config_path = home / "config.toml"
            original = textwrap.dedent(
                '''
                model = "custom-model"

                [features]
                multi_agent = false

                [agents.default]
                description = "custom owner role"
                config_file = "agents/custom-default.toml"
                '''
                ).lstrip()
            config_path.write_text(original, encoding="utf-8")
            (agents / "custom-default.toml").write_text(
                'name = "custom-default"\nmodel = "custom-model"\n', encoding="utf-8"
            )

            self._assert_home_ensure_preserves(
                home,
                owner_home=home / "owner-home",
                expected_absent=("agents/planner.toml",),
            )

    def test_partially_managed_home_preserves_custom_existing_roles(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            agents_dir = home / "agents"
            agents_dir.mkdir()
            config_path = home / "config.toml"
            config_path.write_text(
                textwrap.dedent(
                    '''
                    model = "owner-selected-root-model"

                    [agents.default]
                    description = "custom default role"
                    config_file = "agents/default.toml"

                    [agents.worker]
                    description = "planveyor: agent_type=worker (Generic worker)"
                    config_file = "agents/worker.toml"
                    '''
                ).lstrip(),
                encoding="utf-8",
            )
            custom_default = textwrap.dedent(
                '''
                name = "custom-default"
                description = "owner custom role"
                model = "custom-model"
                model_reasoning_effort = "high"
                developer_instructions = """preserve me"""
                '''
            ).lstrip()
            (agents_dir / "default.toml").write_text(custom_default, encoding="utf-8")
            (agents_dir / "worker.toml").write_text(
                textwrap.dedent(
                    '''
                    # planveyor: agent_type=worker (Generic worker)
                    name = "worker"
                    description = "planveyor: agent_type=worker (Generic worker)"
                    model = "fixture-stale-model"
                    model_reasoning_effort = "xhigh"
                    developer_instructions = """stale"""
                    '''
                ).lstrip(),
                encoding="utf-8",
            )

            self._assert_home_ensure_preserves(
                home,
                owner_home=home / "owner-home",
                expected_absent=("agents/planner.toml",),
            )

    def test_home_ensure_preserves_existing_role_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            config_path = home / "config.toml"
            config_path.write_text(
                textwrap.dedent(
                    """
                    model = "owner-selected-root-model"

                    [features]
                    multi_agent = false
                    multi_agent_v2 = true

                    [agents.worker]
                    description = "planveyor: agent_type=worker (Generic worker)"
                    config_file = "stale.toml"
                    """
                ).lstrip(),
                encoding="utf-8",
            )
            agents_dir = home / "agents"
            agents_dir.mkdir()
            (agents_dir / "worker.toml").write_text(
                textwrap.dedent(
                    '''
                    # planveyor: agent_type=worker (Generic worker)
                    name = "worker"
                    description = "stale"
                    model = "fixture-stale-model"
                    model_reasoning_effort = "xhigh"
                    model_verbosity = "medium"
                    developer_instructions = """
                    stale multiline instructions
                    with [header-like] text
                    """

                    [tooling]
                    name = "nested-name"
                    description = "nested description"
                    model = "nested-model"
                    model_reasoning_effort = "low"
                    '''
                ).lstrip(),
                encoding="utf-8",
            )

            self._assert_home_ensure_preserves(
                home,
                owner_home=home / "owner-home",
                expected_absent=("agents/default.toml", "agents/planner.toml"),
            )


if __name__ == "__main__":
    unittest.main()

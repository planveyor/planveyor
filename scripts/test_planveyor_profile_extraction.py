from __future__ import annotations

import importlib.util
import json
import os
import re
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET


# The product test always exercises the sibling Planveyor root.
ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "planveyor.zsh"
if str(ROOT / "scripts") not in sys.path:
    sys.path.append(str(ROOT / "scripts"))

import build_role_bundles as bundles
import plan_lint
import post_merge_packetization_gate as packetization
from test_support.process_contract_fixtures import standalone_git_root

_CHECKER_PATH = Path(__file__).with_name("check_planveyor_profile_contract.py")
_CHECKER_SPEC = importlib.util.spec_from_file_location("_planveyor_public_contract_checker", _CHECKER_PATH)
assert _CHECKER_SPEC is not None and _CHECKER_SPEC.loader is not None
profile = importlib.util.module_from_spec(_CHECKER_SPEC)
sys.modules[_CHECKER_SPEC.name] = profile
_CHECKER_SPEC.loader.exec_module(profile)


SOURCE_IDENTITIES = (
    ("planveyor", "default", "default"),
    ("consumer-fixture", "default", "default"),
)

# This is deliberately a finite compatibility contract, rather than a prompt
# inventory discovered from the runtime.  The ZCode overlay is intentionally
# outside the public root prompt corpus and is covered separately below.
PUBLIC_PROMPT_PHASES = (
    ("architect", "init", "architect_init.md"),
    ("architect", "draft_discussion", "architect_draft_discussion.md"),
    ("architect", "status_driven", "architect_status_driven.md"),
    ("architect", "censor", "architect_censor.md"),
    ("architect", "merge_notes", "architect_merge_notes.md"),
    ("architect", "plan_harvest", "architect_plan_harvest.md"),
    ("architect", "post_merge_audit", "architect_post_merge_audit.md"),
    ("architect", "canon_sweep", "architect_canon_sweep.md"),
    ("architect", "docs_finalize_general", "architect_docs_finalize_general.md"),
    ("architect", "docs_finalize_followups", "architect_docs_finalize_followups.md"),
    ("architect", "track_process_roles", "architect_track_process_roles.md"),
    ("architect", "track_process_collab", "architect_track_process_collab.md"),
    ("architect", "track_innovations", "architect_track_innovations.md"),
    ("planner", "init", "planner_init.md"),
    ("planner", "status_driven", "planner_status_driven.md"),
    ("planner", "censor", "planner_censor.md"),
    ("planner", "docs_finalize_general", "planner_docs_finalize_general.md"),
    ("planner", "docs_finalize_followups", "planner_docs_finalize_followups.md"),
    ("coder", "init", "coder_init.md"),
    ("coder", "status_driven", "coder_status_driven.md"),
    ("coder", "censor", "coder_censor.md"),
    ("coder", "docs_finalize_general", "coder_docs_finalize_general.md"),
    ("coder", "docs_finalize_followups", "coder_docs_finalize_followups.md"),
    ("coder", "migrations_gate", "coder_migrations_gate.md"),
    ("coder", "merge_conflicts", "coder_merge_conflicts.md"),
    ("reviewer", "init", "reviewer_init.md"),
    ("reviewer", "status_driven", "reviewer_status_driven.md"),
    ("reviewer", "docs_finalize_general", "reviewer_docs_finalize_general.md"),
    ("reviewer", "docs_finalize_followups", "reviewer_docs_finalize_followups.md"),
    ("manager", "init", "manager_init.md"),
    ("manager", "router", "manager_router.md"),
    ("manager", "collab_pipeline", "manager_collab_pipeline.md"),
    ("manager", "custom_pipeline", "manager_custom_pipeline.md"),
    ("manager", "collab_merge_pipeline", "manager_collab_merge_pipeline.md"),
)

PUBLIC_RUNTIME_INPUTS = (
    "scripts/planveyor.zsh",
    "scripts/planveyor/contract_authority.zsh",
    "scripts/planveyor/session_init.zsh",
    "scripts/planveyor/role_runtime.zsh",
    "scripts/planveyor/docs_finalize.zsh",
    "scripts/contract_authority_bootstrap.py",
    "scripts/contract_authority_shell_loader.zsh",
    "scripts/contract_authority_children.py",
    "scripts/contract_authority_bridge.py",
    "scripts/contract_authority_context.py",
    "scripts/contract_authority_runtime.py",
    "scripts/contract_authority_snapshot.py",
    "scripts/fs_object_identity.py",
)
PUBLIC_RUNTIME_EXTERNAL_INPUTS = (
    "docs/_meta/runner_selection_resolution.v1.json",
)
PUBLIC_ROOT_CONTENT = (
    "AGENTS.md",
    "docs/roles/architect.md",
    "docs/roles/manager.md",
    "docs/roles/planner.md",
    "docs/roles/coder.md",
    "docs/roles/reviewer.md",
    "docs/playbooks/docs_architecture.md",
    "docs/_meta/plan_vocab.json",
    "docs/_meta/doc_classes.json",
    *(f"docs/tools/prompts/{filename}" for _role, _phase, filename in PUBLIC_PROMPT_PHASES),
)


def expected_prompt(filename: str, *, tooling: Path = ROOT) -> Path:
    return tooling / "docs" / "tools" / "prompts" / filename


def _unique_paths(*groups: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(item for group in groups for item in group))


def _shell_function_body(text: str, name: str) -> str:
    start = re.search(rf"(?m)^{re.escape(name)}\s*\(\)\s*\{{", text)
    if start is None:
        raise AssertionError(f"missing public function {name}")
    remainder = text[start.end():]
    next_function = re.search(r"(?m)^[A-Za-z_][A-Za-z0-9_]*\s*\(\)\s*\{", remainder)
    return remainder[:next_function.start()] if next_function else remainder


class PlanveyorProfileExtractionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="planveyor-profile-extraction-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.home = self.base / "home"
        self.home.mkdir()
        self.repo = self._repo("consumer-fixture")

    def _repo(self, name: str) -> Path:
        repo = self.base / "consumers" / name
        repo.mkdir(parents=True, exist_ok=True)
        (repo / "AGENTS.md").write_text("# Fixture instructions\n\n- Public fixture rule.\n", encoding="utf-8")
        return repo

    def shell(
        self,
        code: str,
        *,
        repo: Path | None = None,
        tooling: Path = ROOT,
        facade: Path | None = None,
        timeout: float = 60,
    ) -> subprocess.CompletedProcess[str]:
        repo = repo or self.repo
        facade = facade or SCRIPT
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("PLANVEYOR_", "ZCODE_", "CODEX_", "GIT_"))
            and key != "PYTHONPATH"
        }
        child_tmp = (self.base / ".child-tmp").resolve()
        child_tmp.mkdir(exist_ok=True)
        env.update(
            HOME=str(self.home),
            TMPDIR=str(child_tmp),
            TMPPREFIX=str(child_tmp / "zsh"),
            PYBIN=sys.executable,
            PYTHONDONTWRITEBYTECODE="1",
            PYTHONNOUSERSITE="1",
            GIT_CONFIG_NOSYSTEM="1",
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_TERMINAL_PROMPT="0",
        )
        source = f"source {shlex.quote(str(facade))}\n"
        return subprocess.run(
            ["/bin/zsh", "-f", "-c", source + code],
            cwd=repo,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def _git_env(self) -> dict[str, str]:
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("PLANVEYOR_", "ZCODE_", "CODEX_", "GIT_"))
        }
        env.update(
            HOME=str(self.home),
            GIT_CONFIG_NOSYSTEM="1",
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_TERMINAL_PROMPT="0",
            GIT_AUTHOR_NAME="Public fixture",
            GIT_AUTHOR_EMAIL='public-fixture' + '@' + 'example' + '.' + 'invalid',
            GIT_COMMITTER_NAME="Public fixture",
            GIT_COMMITTER_EMAIL='public-fixture' + '@' + 'example' + '.' + 'invalid',
        )
        return env

    def _git(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgSign=false", "-C", str(root), *args],
            check=True,
            capture_output=True,
            text=True,
            env=self._git_env(),
            timeout=30,
        )

    def copy_public_runtime_fixture(self) -> Path:
        """Copy finite public owners into a disposable Git runtime fixture."""

        tooling = self.base / "tooling"
        fixture_paths = _unique_paths(
            PUBLIC_RUNTIME_INPUTS,
            PUBLIC_RUNTIME_EXTERNAL_INPUTS,
            PUBLIC_ROOT_CONTENT,
            tuple(profile.EXACT_BUNDLE),
        )
        self.assertTrue(fixture_paths)
        self.assertFalse(any("profiles" in Path(path).parts for path in fixture_paths))
        self.assertFalse(any(path.startswith("private_shell/") for path in fixture_paths))
        for relative in fixture_paths:
            source = ROOT / relative
            self.assertTrue(source.is_file(), relative)
            target = tooling / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

        self._git(tooling, "init", "--quiet")
        self._git(tooling, "add", "--", "AGENTS.md", "docs", "scripts")
        self._git(tooling, "commit", "--quiet", "-m", "public runtime fixture")
        return tooling

    def _linked_git_repo(self, parent: Path, name: str) -> tuple[Path, Path]:
        repo = parent / name
        repo.mkdir()
        self._git(repo, "init", "--quiet")
        self._git(repo, "commit", "--quiet", "--allow-empty", "-m", "fixture")
        linked = parent / "linked-worktree"
        self._git(repo, "worktree", "add", "--detach", str(linked))
        return repo, linked

    def test_source_identity_and_content_selection_use_public_families(self) -> None:
        for name, expected_repo_identity, expected_content_identity in SOURCE_IDENTITIES:
            with self.subTest(name=name):
                repo = self._repo(name)
                child_observation = (
                    self.base / ".child-tmp" / "profile-extraction-child-environment"
                )
                repo_identity = self.shell(
                    f'print -r -- "$TMPDIR|$TMPPREFIX" > {shlex.quote(str(child_observation))}; '
                    "_planveyor_repo_profile_id",
                    repo=repo,
                )
                self.assertEqual(repo_identity.returncode, 0, repo_identity.stderr)
                self.assertEqual(repo_identity.stdout.strip(), expected_repo_identity)
                self.assertEqual(
                    child_observation.read_text(encoding="utf-8"),
                    f"{self.base / '.child-tmp'}|{self.base / '.child-tmp' / 'zsh'}\n",
                )
                content_identity = self.shell("_planveyor_content_profile_id", repo=repo)
                self.assertEqual(content_identity.returncode, 0, content_identity.stderr)
                self.assertEqual(content_identity.stdout.strip(), expected_content_identity)

    def test_legacy_profile_environment_is_inert_for_source_content_selection(self) -> None:
        for repo_name, expected in (("consumer-fixture", "default"), ("planveyor", "default")):
            repo = self._repo(repo_name)
            for label, command in (
                ("unset", "unset PLANVEYOR_LEGACY_PROFILE; _planveyor_content_profile_id"),
                ("empty", "PLANVEYOR_LEGACY_PROFILE='' _planveyor_content_profile_id"),
                ("named", "PLANVEYOR_LEGACY_PROFILE=planveyor _planveyor_content_profile_id"),
                ("retired", "PLANVEYOR_LEGACY_PROFILE=router _planveyor_content_profile_id"),
                ("arbitrary", "PLANVEYOR_LEGACY_PROFILE=anything _planveyor_content_profile_id"),
            ):
                with self.subTest(repo=repo_name, label=label):
                    result = self.shell(command, repo=repo)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.strip(), expected)

    def test_loaded_runtime_and_linked_worktree_use_planveyor_identity(self) -> None:
        tooling = self.copy_public_runtime_fixture()
        linked = self.base / "linked-runtime-worktree"
        self._git(tooling, "worktree", "add", "--detach", str(linked))
        facade = tooling / "scripts" / "planveyor.zsh"
        for location, root in (("runtime", tooling), ("linked", linked)):
            with self.subTest(location=location):
                for command, expected in (
                    ("_planveyor_repo_profile_id", "planveyor"),
                    ("_planveyor_content_profile_id", "planveyor"),
                    ("_planveyor_pybin_requirement_for_role planner", "required"),
                ):
                    result = self.shell(command, repo=root, facade=facade)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.strip(), expected)

    def test_real_git_renamed_and_case_variant_repos_keep_public_prompt_root(self) -> None:
        cases = (
            ("planveyor", "default", "default"),
            ("planveyor-web", "default", "default"),
            ("Planveyor", "default", "default"),
            ("consumer-fixture", "default", "default"),
        )
        for repo_name, expected_repo_identity, expected_content_identity in cases:
            with self.subTest(repo_name=repo_name):
                with tempfile.TemporaryDirectory(prefix="planveyor-identity-") as directory:
                    repo, linked = self._linked_git_repo(Path(directory), repo_name)
                    for location, checked_repo in (("main", repo), ("linked", linked)):
                        with self.subTest(repo_name=repo_name, location=location):
                            identity = self.shell("_planveyor_repo_profile_id", repo=checked_repo)
                            self.assertEqual(identity.returncode, 0, identity.stderr)
                            self.assertEqual(identity.stdout.strip(), expected_repo_identity)
                            content = self.shell("_planveyor_content_profile_id", repo=checked_repo)
                            self.assertEqual(content.returncode, 0, content.stderr)
                            self.assertEqual(content.stdout.strip(), expected_content_identity)
                            requirement = self.shell(
                                "_planveyor_pybin_requirement_for_role planner",
                                repo=checked_repo,
                            )
                            self.assertEqual(requirement.returncode, 0, requirement.stderr)
                            self.assertEqual(requirement.stdout.strip(), "optional")
                            manager = self.shell(
                                "_planveyor_prompt_file_for_role_phase manager collab_pipeline",
                                repo=checked_repo,
                            )
                            self.assertEqual(manager.returncode, 0, manager.stderr)
                            self.assertEqual(
                                manager.stdout.strip(),
                                str(expected_prompt("manager_collab_pipeline.md")),
                            )

    def test_public_checker_uses_only_root_owners_and_passes_finite_fixture(self) -> None:
        self.assertEqual(profile.check_planveyor_profile_contract(ROOT), [])
        self.assertEqual(len(profile.INVARIANT_IDS), 9)
        self.assertFalse(any("profiles" in Path(path).parts for path in profile.EXACT_BUNDLE))
        self.assertFalse(any(path.startswith("private_shell/") for path in profile.EXACT_BUNDLE))
        tooling = self.copy_public_runtime_fixture()
        self.assertEqual(profile.check_planveyor_profile_contract(tooling), [])

    def test_all_public_prompt_phases_resolve_from_one_root_corpus(self) -> None:
        self.assertEqual(len(PUBLIC_PROMPT_PHASES), 34)
        tooling = self.copy_public_runtime_fixture()
        code = "\n".join(
            f"_planveyor_prompt_file_for_role_phase {role} {phase} || exit"
            for role, phase, _filename in PUBLIC_PROMPT_PHASES
        )
        for repo_name in ("consumer-fixture", "planveyor"):
            with self.subTest(repo_name=repo_name):
                result = self.shell(
                    code,
                    repo=self._repo(repo_name),
                    tooling=tooling,
                    facade=tooling / "scripts" / "planveyor.zsh",
                    timeout=120,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                expected = [
                    str(expected_prompt(filename, tooling=tooling))
                    for _role, _phase, filename in PUBLIC_PROMPT_PHASES
                ]
                self.assertEqual(result.stdout.splitlines(), expected)
                self.assertTrue(all(Path(path).is_file() for path in expected))

    def test_missing_public_prompt_role_or_architecture_blocks_before_init_side_effects(self) -> None:
        tooling = self.copy_public_runtime_fixture()
        required_sources = (
            "docs/tools/prompts/coder_init.md",
            "docs/roles/coder.md",
            "docs/playbooks/docs_architecture.md",
        )
        stub = '''
unset PYBIN CONDA_PREFIX
_planveyor_runner_selection_init_resolve() { print unexpected > init-side-effect; return 1; }
_planveyor_codex() { print unexpected > provider-side-effect; return 1; }
planveyor_coder_init
'''
        for repo_name in ("consumer-fixture", "planveyor"):
            repo = self._repo(repo_name)
            for relative in required_sources:
                with self.subTest(repo_name=repo_name, relative=relative):
                    target = tooling / relative
                    original = target.read_bytes()
                    target.unlink()
                    try:
                        result = self.shell(
                            stub,
                            repo=repo,
                            tooling=tooling,
                            facade=tooling / "scripts" / "planveyor.zsh",
                        )
                    finally:
                        target.write_bytes(original)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("missing required public", result.stderr)
                    self.assertFalse((repo / "init-side-effect").exists())
                    self.assertFalse((repo / "provider-side-effect").exists())
                    self.assertFalse((repo / ".planveyor.pybin").exists())
                    self.assertFalse((repo / ".tmp").exists())
                    self.assertFalse(list(repo.glob(".planveyor.session*")))

    def test_docs_finalize_and_track_dispatch_use_selected_public_root_bytes(self) -> None:
        wrappers = (
            ("planveyor_arch_docs_general", "architect", "docs_finalize_general", "architect_docs_finalize_general.md"),
            ("planveyor_arch_followups", "architect", "docs_finalize_followups", "architect_docs_finalize_followups.md"),
            ("planveyor_coder_docs_general", "coder", "docs_finalize_general", "coder_docs_finalize_general.md"),
            ("planveyor_coder_followups", "coder", "docs_finalize_followups", "coder_docs_finalize_followups.md"),
            ("planveyor_planner_docs_general", "planner", "docs_finalize_general", "planner_docs_finalize_general.md"),
            ("planveyor_planner_followups", "planner", "docs_finalize_followups", "planner_docs_finalize_followups.md"),
            ("planveyor_reviewer_docs_general", "reviewer", "docs_finalize_general", "reviewer_docs_finalize_general.md"),
            ("planveyor_reviewer_followups", "reviewer", "docs_finalize_followups", "reviewer_docs_finalize_followups.md"),
        )
        dispatch_source = (ROOT / "scripts/planveyor/docs_finalize.zsh").read_text(encoding="utf-8")
        for repo_name in ("consumer-fixture", "planveyor"):
            repo = self._repo(repo_name)
            for wrapper, role, phase, filename in wrappers:
                with self.subTest(repo_name=repo_name, wrapper=wrapper):
                    body = _shell_function_body(dispatch_source, wrapper)
                    self.assertIn(f"_planveyor_role_prompt_body {role} {phase}", body)
                    result = self.shell(
                        f"_planveyor_prompt_file_for_role_phase {role} {phase}",
                        repo=repo,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.strip(), str(expected_prompt(filename)))

        track_source = SCRIPT.read_text(encoding="utf-8")
        for wrapper, phase in (
            ("planveyor_arch_process_roles_tui", "track_process_roles"),
            ("planveyor_arch_process_collab_tui", "track_process_collab"),
            ("planveyor_arch_innovations_tui", "track_innovations"),
        ):
            with self.subTest(wrapper=wrapper):
                body = _shell_function_body(track_source, wrapper)
                self.assertIn(f"_planveyor_prompt_file_for_role_phase architect {phase}", body)
                result = self.shell(f"_planveyor_prompt_file_for_role_phase architect {phase}")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), str(expected_prompt(f"architect_{phase}.md")))

    def test_manager_raw_merge_payload_uses_public_root_content_selection(self) -> None:
        for repo_name in ("consumer-fixture", "planveyor"):
            with self.subTest(repo_name=repo_name):
                result = self.shell(
                    '_planveyor_manager_merge_payload "$PYBIN" "MANAGER_CMD=merge_status"',
                    repo=self._repo(repo_name),
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                expected = expected_prompt("manager_collab_merge_pipeline.md").read_text(encoding="utf-8")
                self.assertIn(expected, result.stdout)
                self.assertTrue(result.stdout.endswith("MANAGER_CMD=merge_status\n"))

    def test_compiled_bundles_preserve_public_root_slices_and_identity_binding(self) -> None:
        for role in bundles.ROLE_IDS:
            with self.subTest(role=role):
                contexts = {}
                for repo_name, repo_profile_id, content_profile_id in (
                    ("consumer-fixture", "default", "default"),
                    ("planveyor", "planveyor", "planveyor"),
                ):
                    repo = self._repo(repo_name)
                    if not (repo / '.git').exists():
                        standalone_git_root(repo)
                    prompt = expected_prompt(f"{role}_init.md")
                    contexts[content_profile_id] = bundles._build_context(
                        role,
                        repo_root=repo,
                        tooling_root=ROOT,
                        repo_profile_id=repo_profile_id,
                        content_profile_id=content_profile_id,
                        prompt_path=prompt,
                        out_dir=repo / "bundles",
                    )
                    selected = contexts[content_profile_id]
                    self.assertEqual(selected.role_doc_ref.rel_path, f"docs/roles/{role}.md")
                    self.assertEqual(selected.architecture_ref.rel_path, "docs/playbooks/docs_architecture.md")
                    xml = ET.fromstring(bundles._bundle_xml_bytes(selected))
                    self.assertEqual(xml.attrib["repo_profile_id"], repo_profile_id)
                    self.assertEqual(xml.attrib["content_profile_id"], content_profile_id)
                    source_section = bundles._extract_section(
                        selected.role_doc_text,
                        ("Source of truth / precedence (если есть конфликт)",),
                    )
                    self.assertIsNotNone(source_section, selected.role_doc_ref.rel_path)
                    _heading, source_body = source_section
                    expected_reader_items = bundles._collect_markdown_items(source_body, max_items=3)
                    source_slice = xml.find("./bundle_payload/bootstrap_slice[@id='source_of_truth']")
                    self.assertIsNotNone(source_slice, selected.role_doc_ref.rel_path)
                    self.assertEqual(
                        [item.text for item in source_slice.findall("item")][:3],
                        expected_reader_items,
                    )

                default_xml = ET.fromstring(bundles._bundle_xml_bytes(contexts["default"]))
                planveyor_xml = ET.fromstring(bundles._bundle_xml_bytes(contexts["planveyor"]))
                default_slices = {
                    item.get("id"): [child.text for child in item.findall("item")]
                    for item in default_xml.findall(".//bootstrap_slice")
                }
                planveyor_slices = {
                    item.get("id"): [child.text for child in item.findall("item")]
                    for item in planveyor_xml.findall(".//bootstrap_slice")
                }
                self.assertEqual(set(default_slices), set(planveyor_slices))
                for slice_id in default_slices:
                    self.assertEqual(default_slices[slice_id], planveyor_slices[slice_id], slice_id)
                self.assertNotIn("ui_source_binding", default_slices)
        self.assertNotIn("manager", bundles.ROLE_IDS)

    def test_artifact_locators_and_track_working_set_use_public_root_paths(self) -> None:
        architect = expected_prompt("architect_status_driven.md").read_text(encoding="utf-8")
        coder = expected_prompt("coder_status_driven.md").read_text(encoding="utf-8")
        self.assertIn("docs/playbooks/analysis_wave.md", architect)
        self.assertIn("docs/playbooks/analysis_wave.md", coder)

        track = expected_prompt("architect_track_process_roles.md").read_text(encoding="utf-8")
        expected_working_set = (
            "- Role prompts: `docs/tools/prompts/architect_*.md`, "
            "`planner_*.md`, `coder_*.md`, `reviewer_*.md`"
        )
        self.assertIn(expected_working_set, track)
        for role in ("architect", "planner", "coder", "reviewer"):
            with self.subTest(role=role):
                expanded = sorted((ROOT / "docs/tools/prompts").glob(f"{role}_*.md"))
                self.assertTrue(expanded)
                self.assertTrue(all(path.parent == ROOT / "docs/tools/prompts" for path in expanded))

    def test_decomposition_prompt_uses_public_physical_entrypoint_without_home_loader(self) -> None:
        prompt = (ROOT / "docs/tools/prompts/planveyor_decomposition.md").read_text(encoding="utf-8")
        self.assertIn("./bin/planveyor planveyor_decomposition_init [PLAN_PATH]", prompt)
        self.assertIn("physical Planveyor root", prompt)
        self.assertNotIn("source scripts/planveyor.zsh", prompt)
        self.assertNotIn(".zshrc.d/planveyor.zsh", prompt)
        self.assertNotIn("$HOME/planveyor", prompt)

    def test_public_root_canon_is_source_only_without_declared_target_mapping(self) -> None:
        for changed_file in (
            "docs/tools/prompts/architect_init.md",
            "docs/roles/architect.md",
            "docs/playbooks/docs_architecture.md",
        ):
            with self.subTest(changed_file=changed_file):
                classification = packetization.classify_changed_file(changed_file)
                self.assertEqual(classification.targets, ("current-consumer",))
                self.assertIsNotNone(classification.source_only_reason)
                applicability = packetization.resolve_target_applicability(ROOT, changed_files=[changed_file])
                self.assertEqual(applicability.partitions, ())
                self.assertEqual(len(applicability.records), 1)
                record = applicability.records[0]
                self.assertEqual(record.target_kind, "source_only")
                self.assertEqual(record.authority, "checked-in source ownership policy")
                self.assertIn("tooling-owned canon", record.source_only_reason or "")


if __name__ == "__main__":
    unittest.main()

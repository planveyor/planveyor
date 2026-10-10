#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


MODULE_PATH = Path(__file__).with_name("build_role_bundles.py")
SPEC = importlib.util.spec_from_file_location("build_role_bundles", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

from test_support.process_contract_fixtures import standalone_git_root

PLANVEYOR_ZSH = Path(__file__).with_name("planveyor.zsh").resolve()


def _write(path: Path, text: str, *, executable: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if executable:
        path.chmod(0o755)
    return path


class BuildRoleBundlesSanitizerTests(unittest.TestCase):
    def test_known_home_absolute_paths_become_portable_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            repo_root = root / "repo"
            tooling_root = root / "tooling"
            repo_root.mkdir()
            tooling_root.mkdir()

            text = (
                f"Prompt path: {tooling_root / 'docs/tools/prompts/coder_init.md'}; "
                f"repo cache: {repo_root / '.tmp/role_bundles/coder.xml'}."
            )

            sanitized = MODULE._sanitize_item_text(text, repo_root=repo_root, tooling_root=tooling_root)

            self.assertEqual(
                sanitized,
                "Prompt path: tooling:docs/tools/prompts/coder_init.md; "
                "repo cache: repo:.tmp/role_bundles/coder.xml.",
            )

    def test_slash_delimited_prose_and_relative_commands_stay_intact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            repo_root = root / "repo"
            tooling_root = root / "tooling"
            repo_root.mkdir()
            tooling_root.mkdir()

            text = (
                "Reviewer не правит код/шаблоны/миграции; "
                "используй ./scripts/role_tools.sh doctor и ./scripts/role_tools.sh verify."
            )

            sanitized = MODULE._sanitize_item_text(text, repo_root=repo_root, tooling_root=tooling_root)

            self.assertEqual(sanitized, text)
            self.assertNotIn("<ABS_PATH_OMITTED>", sanitized)


class BuildRoleBundlesSliceTests(unittest.TestCase):
    def test_required_bootstrap_slices_are_rendered(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            repo_root = root / "repo"
            tooling_root = root / "tooling"
            repo_root.mkdir()
            tooling_root.mkdir()

            prompt_path = _write(
                tooling_root / "docs/tools/prompts/coder_init.md",
                "Read docs/roles/coder.md before bootstrap.\n- init prompt item\n",
            )
            role_doc_path = _write(
                tooling_root / "docs/roles/coder.md",
                textwrap.dedent(
                    """
                    # Coder

                    ## Source of truth / precedence (если есть конфликт)
                    - PLAN_PATH is task truth.

                    ## Границы роли (жёстко)
                    - Coder changes only scoped implementation files.

                    ## Обязательный старт (session bootstrap; 1 раз на role)
                    - Read AGENTS.md.
                    """
                ).strip()
                + "\n",
            )
            agents_path = _write(repo_root / "AGENTS.md", "# AGENTS\n\n- Repo rule.\n")
            architecture_path = _write(
                tooling_root / "docs/playbooks/docs_architecture.md",
                textwrap.dedent(
                    """
                    # Docs architecture

                    ## Purpose
                    - Keep source/control-plane/runtime bundle layers separate.

                    | Layer | Owner | Source | Generated | Storage | Writer | Examples | Rule |
                    | --- | --- | --- | --- | --- | --- | --- | --- |
                    | `runtime bundles` | init bootstrap | role docs | XML | `.tmp/role_bundles` | helper | coder.xml | generated-only |
                    """
                ).strip()
                + "\n",
            )
            plan_vocab_path = _write(
                tooling_root / "docs/_meta/plan_vocab.json",
                '{"plan_statuses":{"canonical":["Ready for Coder","Ready for Review"]}}\n',
            )
            doc_classes_path = _write(
                tooling_root / "docs/_meta/doc_classes.json",
                '{"classes":[{"label":"plan"},{"label":"code_draft"}]}\n',
            )

            def ref(path: Path, *, home: str) -> MODULE.ResolvedRef:
                root_for_home = repo_root if home == "repo" else tooling_root
                return MODULE.ResolvedRef(home=home, rel_path=path.relative_to(root_for_home).as_posix(), abs_path=path)

            ctx = MODULE.BundleContext(
                role="coder",
                repo_root=repo_root,
                tooling_root=tooling_root,
                repo_profile_id="default",
                content_profile_id="planveyor",
                prompt_ref=ref(prompt_path, home="tooling"),
                role_doc_ref=ref(role_doc_path, home="tooling"),
                agents_ref=ref(agents_path, home="repo"),
                architecture_ref=ref(architecture_path, home="tooling"),
                plan_vocab_ref=ref(plan_vocab_path, home="tooling"),
                doc_classes_ref=ref(doc_classes_path, home="tooling"),
                docs_index_ref=None,
                repo_meta_refs=(),
                prompt_text=prompt_path.read_text(encoding="utf-8"),
                role_doc_text=role_doc_path.read_text(encoding="utf-8"),
                agents_text=agents_path.read_text(encoding="utf-8"),
                architecture_text=architecture_path.read_text(encoding="utf-8"),
                plan_vocab={"plan_statuses": {"canonical": ["Ready for Coder", "Ready for Review"]}},
                doc_classes={"classes": [{"label": "plan"}, {"label": "code_draft"}]},
                out_path=repo_root / ".tmp/role_bundles/coder.xml",
            )

            root_el = ET.fromstring(MODULE._bundle_xml_bytes(ctx))
            slice_ids = {
                item.attrib["id"]
                for item in root_el.findall("./bundle_payload/bootstrap_slice")
            }
            self.assertTrue(
                {"runtime_contract", "source_of_truth", "role_contract", "control_plane_summary"}.issubset(slice_ids)
            )

            rendered_text = ET.tostring(root_el, encoding="unicode")
            self.assertIn("generated-only runtime context", rendered_text)
            self.assertIn("Control-plane manifests stay in JSON", rendered_text)
            self.assertIsNone(root_el.find("./ui_source_refs"))
            self.assertIsNone(root_el.find("./bundle_payload/bootstrap_slice[@id='ui_source_binding']"))



class BuildRoleBundlesProfileContentBridgeTests(unittest.TestCase):
    def test_prompt_manifest_carries_exactly_one_effective_content_profile(self) -> None:
        tooling_root = Path(__file__).resolve().parent.parent

        def load(stdout: str):
            with tempfile.TemporaryDirectory() as tmpdir:
                repo_root = (Path(tmpdir) / "repo").resolve()
                repo_root.mkdir()
                context = SimpleNamespace(project_root=repo_root, state="legacy")
                result = SimpleNamespace(returncode=0, stdout=stdout, stderr="")
                with (
                    mock.patch.object(MODULE, "_reader_context", return_value=context),
                    mock.patch.object(MODULE.subprocess, "run", return_value=result),
                ):
                    return MODULE._load_prompt_manifest(
                        repo_root,
                        tooling_root,
                        ["coder"],
                        context=context,
                    )

        repo_profile_id, content_profile_id, prompts = load(
            "repo_profile_id\tdefault\n"
            "content_profile_id\tdefault\n"
            "coder\t/tmp/coder_init.md\n"
        )
        self.assertEqual(repo_profile_id, "default")
        self.assertEqual(content_profile_id, "default")
        self.assertEqual(prompts, {"coder": Path("/tmp/coder_init.md").resolve()})

        for name, stdout, expected in (
            (
                "missing",
                "repo_profile_id\tdefault\ncoder\t/tmp/coder_init.md\n",
                "missing content_profile_id",
            ),
            (
                "empty",
                "content_profile_id\t\ncoder\t/tmp/coder_init.md\n",
                "empty content_profile_id",
            ),
            (
                "duplicate",
                "content_profile_id\tdefault\ncontent_profile_id\tplanveyor\ncoder\t/tmp/coder_init.md\n",
                "duplicate content_profile_id",
            ),
            (
                "unknown",
                "content_profile_id\tunknown\ncoder\t/tmp/coder_init.md\n",
                "unsupported content_profile_id",
            ),
            (
                "retired_profile_content",
                "content_profile_id\tretired_profile\ncoder\t/tmp/coder_init.md\n",
                "unsupported content_profile_id",
            ),
        ):
            with self.subTest(name=name):
                with self.assertRaisesRegex(MODULE.BuildError, expected):
                    load(stdout)

    def test_public_content_identities_compile_from_the_root_corpus(self) -> None:
        tooling_root = Path(__file__).resolve().parent.parent
        cases = {
            "default": {
                "repo_profile_id": "default",
                "content_profile_id": "default",
                "prompt_dir": "docs/tools/prompts",
                "role_dir": "docs/roles",
                "architecture": "docs/playbooks/docs_architecture.md",
                "family": "root",
            },
            "planveyor": {
                "repo_profile_id": "planveyor",
                "content_profile_id": "planveyor",
                "prompt_dir": "docs/tools/prompts",
                "role_dir": "docs/roles",
                "architecture": "docs/playbooks/docs_architecture.md",
                "family": "root",
            },
        }

        for case_id, case in cases.items():
            repo_profile_id = case["repo_profile_id"]
            with self.subTest(case_id=case_id, repo_profile_id=repo_profile_id), tempfile.TemporaryDirectory() as tmpdir:
                repo_root = (Path(tmpdir) / "repo").resolve()
                repo_root.mkdir()
                standalone_git_root(repo_root)
                _write(repo_root / "AGENTS.md", "# AGENTS\n")
                out_dir = repo_root / "bundles"
                prompt_manifest = {
                    role: tooling_root / case["prompt_dir"] / f"{role}_init.md"
                    for role in MODULE.ROLE_IDS
                }

                with (
                    mock.patch.object(MODULE, "_resolve_repo_root", return_value=repo_root),
                    mock.patch.object(MODULE, "_resolve_tooling_root", return_value=tooling_root),
                    mock.patch.object(
                        MODULE,
                        "_load_prompt_manifest",
                        return_value=(repo_profile_id, case["content_profile_id"], prompt_manifest),
                    ),
                ):
                    self.assertEqual(MODULE.main(["--all", "--out-dir", str(out_dir)]), 0)

                for role in MODULE.ROLE_IDS:
                    bundle = ET.parse(out_dir / f"{role}.xml").getroot()
                    self.assertEqual(bundle.attrib["repo_profile_id"], repo_profile_id)
                    self.assertEqual(
                        bundle.attrib["content_profile_id"],
                        case["content_profile_id"],
                    )
                    source_paths = [
                        ref.attrib["path"]
                        for ref in bundle.findall("./source_refs/source_ref")
                    ]
                    self.assertEqual(
                        source_paths,
                        [
                            "AGENTS.md",
                            f"{case['role_dir']}/{role}.md",
                            f"{case['prompt_dir']}/{role}_init.md",
                            case["architecture"],
                        ],
                    )
                    self.assertEqual(
                        bundle.find("./meta/prompt_ref").attrib["path"],
                        f"{case['prompt_dir']}/{role}_init.md",
                    )

    def test_public_profiles_keep_root_architecture(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = (Path(tmpdir) / "repo").resolve()
            repo_root.mkdir()
            standalone_git_root(repo_root)
            _write(repo_root / "AGENTS.md", "# AGENTS\n")
            tooling_root = Path(__file__).resolve().parent.parent
            prompt_path = tooling_root / "docs/tools/prompts/coder_init.md"

            for repo_profile_id, content_profile_id in (("planveyor", "planveyor"),):
                with self.subTest(repo_profile_id=repo_profile_id, content_profile_id=content_profile_id):
                    context = MODULE._build_context(
                        "coder",
                        repo_root=repo_root,
                        tooling_root=tooling_root,
                        repo_profile_id=repo_profile_id,
                        content_profile_id=content_profile_id,
                        prompt_path=prompt_path,
                        out_dir=repo_root / "bundles",
                    )
                    self.assertEqual(
                        context.architecture_ref.rel_path,
                        "docs/playbooks/docs_architecture.md",
                    )

    def test_target_local_content_fails_closed_without_engaged_consumer_contract(self) -> None:
        tooling_root = Path(__file__).resolve().parent.parent
        prompt_path = tooling_root / "docs/tools/prompts/coder_init.md"

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = (Path(tmpdir) / "repo").resolve()
            repo_root.mkdir()
            out_dir = repo_root / "bundles"
            legacy_context = SimpleNamespace(project_root=repo_root, state="legacy")

            with (
                mock.patch.object(MODULE, "_resolve_repo_root", return_value=repo_root),
                mock.patch.object(MODULE, "_resolve_tooling_root", return_value=tooling_root),
                mock.patch.object(MODULE, "resolve_top_level_context", return_value=legacy_context),
                mock.patch.object(
                    MODULE,
                    "_load_prompt_manifest",
                    return_value=("consumer", "target-local", {"coder": prompt_path}),
                ),
                mock.patch.object(
                    MODULE,
                    "_build_context",
                    side_effect=AssertionError("fallback corpus must not be assembled"),
                ) as build_context,
            ):
                self.assertEqual(MODULE.main(["--role", "coder", "--out-dir", str(out_dir)]), 3)

            build_context.assert_not_called()
            self.assertFalse((out_dir / "coder.xml").exists())

    def test_target_local_content_continues_with_engaged_consumer_contract(self) -> None:
        tooling_root = Path(__file__).resolve().parent.parent
        prompt_path = tooling_root / "docs/tools/prompts/coder_init.md"

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = (Path(tmpdir) / "repo").resolve()
            repo_root.mkdir()
            out_dir = repo_root / "bundles"
            engaged_context = SimpleNamespace(project_root=repo_root, state="engaged")
            built_context = object()

            with (
                mock.patch.object(MODULE, "_resolve_repo_root", return_value=repo_root),
                mock.patch.object(MODULE, "_resolve_tooling_root", return_value=tooling_root),
                mock.patch.object(MODULE, "resolve_top_level_context", return_value=engaged_context),
                mock.patch.object(
                    MODULE,
                    "_load_prompt_manifest",
                    return_value=("consumer", "target-local", {"coder": prompt_path}),
                ),
                mock.patch.object(MODULE, "_build_context", return_value=built_context) as build_context,
                mock.patch.object(MODULE, "_write_or_check", return_value=(True, "OK bundle")),
            ):
                self.assertEqual(MODULE.main(["--role", "coder", "--out-dir", str(out_dir)]), 0)

            build_context.assert_called_once_with(
                "coder",
                repo_root=repo_root,
                tooling_root=tooling_root,
                repo_profile_id="consumer",
                content_profile_id="target-local",
                prompt_path=prompt_path,
                out_dir=out_dir,
                context=engaged_context,
            )

class BuildRoleBundlesConsumerRuntimeTests(unittest.TestCase):
    def test_explicit_consumer_project_wins_over_nested_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            consumer_root = root / "consumer"
            nested_cwd = consumer_root / "nested"
            consumer_root.mkdir()
            nested_cwd.mkdir()
            previous_cwd = Path.cwd()
            try:
                os.chdir(nested_cwd)
                with mock.patch.dict(os.environ, {"PLANVEYOR_PROJECT_ROOT": str(consumer_root)}):
                    resolved = MODULE._resolve_repo_root()
            finally:
                os.chdir(previous_cwd)

        self.assertEqual(resolved, consumer_root)

    def test_manifest_child_uses_runtime_launcher_and_explicit_consumer_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            consumer_root = root / "consumer"
            runtime_root = root / "runtime"
            consumer_facade_hit = root / "consumer-facade-hit"
            consumer_root.mkdir()
            runtime_root.mkdir()

            _write(
                consumer_root / "scripts" / "planveyor.zsh",
                f": > {shlex.quote(str(consumer_facade_hit))}\n",
            )

            _write(
                runtime_root / "bin" / "planveyor",
                textwrap.dedent(
                    f"""\
                    #!/bin/sh
                    [ "$1" = "--project" ] || exit 91
                    [ "$2" = {shlex.quote(str(consumer_root))} ] || exit 92
                    [ "$3" = "planveyor_role_bundle_prompt_manifest" ] || exit 93
                    [ "$4" = "coder" ] || exit 94
                    [ "$PWD" = {shlex.quote(str(consumer_root))} ] || exit 95
                    printf 'repo_profile_id\\tconsumer-fixture\\n'
                    printf 'content_profile_id\\tdefault\\n'
                    printf 'coder\\t/tmp/coder_init.md\\n'
                    """
                ),
                executable=True,
            )
            context = SimpleNamespace(project_root=consumer_root, state="legacy")

            with mock.patch.object(MODULE, "_reader_context", return_value=context):
                repo_profile_id, content_profile_id, prompts = MODULE._load_prompt_manifest(
                    consumer_root,
                    runtime_root,
                    ["coder"],
                    context=context,
                )

        self.assertEqual(repo_profile_id, "consumer-fixture")
        self.assertEqual(content_profile_id, "default")
        self.assertEqual(prompts, {"coder": Path("/tmp/coder_init.md").resolve()})
        self.assertFalse(consumer_facade_hit.exists())


class RoleBundleWrapperDiagnosticsTests(unittest.TestCase):
    def _run_prepare(
        self,
        *,
        builder_body: str,
        stale_path: str = "/tmp/stale-role-bundle.xml",
    ) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            repo_root = root / "repo"
            tooling_root = root / "tooling"
            fake_home = root / "home"
            repo_root.mkdir()
            tooling_root.mkdir()
            fake_home.mkdir()
            standalone_git_root(repo_root)
            standalone_git_root(tooling_root)
            # The wrapper needs the authority facade and every module it loads
            # before it can invoke the synthetic builder.  Copy a complete
            # standalone legacy runtime into the disposable tooling root so this unit
            # fixture neither inherits the installed loader nor pins the live
            # integration checkout.
            for relative_path in (
                "planveyor.zsh",
                "planveyor/contract_authority.zsh",
                "planveyor/session_init.zsh",
                "planveyor/role_runtime.zsh",
                "planveyor/docs_finalize.zsh",
                "contract_authority_bootstrap.py",
                "contract_authority_shell_loader.zsh",
                "contract_authority_children.py",
                "contract_authority_bridge.py",
                "contract_authority_context.py",
                "contract_authority_runtime.py",
                "contract_authority_snapshot.py",
                "fs_object_identity.py",
            ):
                source_path = PLANVEYOR_ZSH.parent / relative_path
                fixture_path = tooling_root / "scripts" / relative_path
                fixture_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, fixture_path)
            _write(
                tooling_root / "scripts/build_role_bundles.py",
                builder_body,
                executable=True,
            )
            _write(repo_root / "AGENTS.md", "# AGENTS\n")

            command = textwrap.dedent(
                f"""
                source {tooling_root / "scripts/planveyor.zsh"} || exit $?
                set -e
                export PLANVEYOR_ROOT={tooling_root}
                cd {repo_root}
                export ROLE_BUNDLE_PATH={stale_path}
                [[ "$(_planveyor_project_root)" == {shlex.quote(str(repo_root))} ]] || exit 71
                [[ "$(_planveyor_role_bundle_output_dir)" == {shlex.quote(str(repo_root / '.tmp/role_bundles'))} ]] || exit 72
                _planveyor_prepare_role_bundle coder {sys.executable}
                print -r -- "rc=$?"
                print -r -- "ROLE_BUNDLE_PATH=${{ROLE_BUNDLE_PATH-}}"
                if [[ -f .tmp/role_bundles/coder.refresh.log ]]; then
                  print -r -- "diagnostic_present=yes"
                  sed -n '1,40p' .tmp/role_bundles/coder.refresh.log
                else
                  print -r -- "diagnostic_present=no"
                fi
                """
            ).strip()
            proc = subprocess.run(
                ["zsh", "-f", "-c", command],
                cwd=repo_root,
                text=True,
                capture_output=True,
                check=False,
                env={
                    **os.environ,
                    "HOME": str(fake_home),
                    "PLANVEYOR_ROOT": str(tooling_root),
                },
            )
            return proc, repo_root, tooling_root

    def test_failure_writes_transient_diagnostic_and_clears_stale_path(self) -> None:
        proc, _, _ = self._run_prepare(
            builder_body=textwrap.dedent(
                """
                #!/usr/bin/env python3
                import sys
                print("builder exploded: missing prompt", file=sys.stderr)
                raise SystemExit(3)
                """
            ).strip()
            + "\n",
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Runtime bundle refresh failed", proc.stderr)
        self.assertIn("Diagnostic: .tmp/role_bundles/coder.refresh.log", proc.stderr)
        self.assertIn("rc=0", proc.stdout)
        self.assertIn("ROLE_BUNDLE_PATH=", proc.stdout)
        self.assertIn("diagnostic_present=yes", proc.stdout)
        self.assertIn("status=failed", proc.stdout)
        self.assertIn("exit_code=3", proc.stdout)
        self.assertIn("builder exploded: missing prompt", proc.stdout)

    def test_failure_diagnostic_redacts_local_repo_and_tooling_paths(self) -> None:
        proc, repo_root, tooling_root = self._run_prepare(
            builder_body=textwrap.dedent(
                """
                #!/usr/bin/env python3
                import os
                import sys
                from pathlib import Path

                print(f"repo cwd={Path.cwd()}")
                print(f"tooling root={os.environ['PLANVEYOR_ROOT']}", file=sys.stderr)
                raise SystemExit(3)
                """
            ).strip()
            + "\n",
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn(str(repo_root), proc.stdout)
        self.assertNotIn(str(tooling_root), proc.stdout)
        self.assertIn("repo cwd=repo:", proc.stdout)
        self.assertIn("tooling root=tooling:", proc.stdout)

    def test_success_without_xml_writes_diagnostic_and_clears_stale_path(self) -> None:
        proc, _, _ = self._run_prepare(
            builder_body=textwrap.dedent(
                """
                #!/usr/bin/env python3
                print("builder ok but no xml")
                """
            ).strip()
            + "\n",
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("produced no XML", proc.stderr)
        self.assertIn("ROLE_BUNDLE_PATH=", proc.stdout)
        self.assertIn("status=no_bundle", proc.stdout)
        self.assertIn("builder ok but no xml", proc.stdout)

    def test_success_with_expected_xml_exports_fresh_path_without_warning(self) -> None:
        proc, _, _ = self._run_prepare(
            builder_body=textwrap.dedent(
                """
                #!/usr/bin/env python3
                import argparse
                from pathlib import Path

                parser = argparse.ArgumentParser()
                parser.add_argument("--role")
                parser.add_argument("--out-dir")
                args = parser.parse_args()
                out_dir = Path(args.out_dir)
                out_dir.mkdir(parents=True, exist_ok=True)
                (out_dir / f"{args.role}.xml").write_text("<role_bundle/>\\n", encoding="utf-8")
                """
            ).strip()
            + "\n",
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("Runtime bundle refresh", proc.stderr)
        self.assertRegex(proc.stdout, r"ROLE_BUNDLE_PATH=.*/\.tmp/role_bundles/coder\.xml")
        self.assertIn("diagnostic_present=no", proc.stdout)


if __name__ == "__main__":
    unittest.main()

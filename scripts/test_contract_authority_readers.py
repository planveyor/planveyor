from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

try:
    from scripts.authority_bootstrap_test_support import run_python_entry, run_python_stdin
    from scripts import contract_authority_context as authority_context
    from scripts.test_contract_authority_support import (
        AuthorityFixture,
        git,
        write,
    )
except ImportError:  # pragma: no cover - supports direct ``scripts/`` execution.
    from authority_bootstrap_test_support import run_python_entry, run_python_stdin
    import contract_authority_context as authority_context
    from test_contract_authority_support import (
        AuthorityFixture,
        git,
        write,
    )


class ContractAuthorityReaderIntegrationTests(unittest.TestCase):
    """Reader-only authority coverage in disposable runtime and target repositories."""

    def _run_target_python(self, fixture: AuthorityFixture, source: str) -> subprocess.CompletedProcess[str]:
        env = fixture.environment()
        return run_python_stdin(fixture, source, environment=env)

    def test_planveyor_local_fixture_writes_only_a_physical_v3_selector(self) -> None:
        with AuthorityFixture(identity="planveyor") as fixture:
            fixture.activate_planveyor(authority_context.STATIC_PLANVEYOR_MERGE_REQUIRED_ENGAGED_PATHS)
            marker = json.loads(
                (fixture.target_root / "docs/_meta/planveyor_contract_authority.v1.json").read_text(encoding="utf-8")
            )
            self.assertEqual(marker["schema_version"], 3)
            self.assertEqual(
                set(marker),
                {"schema_version", "repository_id", "authority_mode", "contract_root", "required_runtime_api", "source_commit"},
            )
            self.assertFalse((fixture.target_root / "docs/_meta/contract_sources.v1.json").exists())
            self.assertNotIn(
                "docs/_meta/planveyor_contract_authority.v1.json",
                subprocess.run(
                    ["git", "-C", str(fixture.target_root), "ls-files"],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.splitlines(),
            )

    def test_planveyor_local_fixture_maps_content_below_a_subdirectory_root(self) -> None:
        with AuthorityFixture(identity="planveyor") as fixture:
            fixture.activate_planveyor(
                authority_context.STATIC_PLANVEYOR_MERGE_REQUIRED_ENGAGED_PATHS,
                contract_root="contract",
            )
            self.assertTrue((fixture.target_root / "contract/docs/tools/prompts/architect_init.md").is_file())
            self.assertFalse((fixture.target_root / "docs/tools/prompts/architect_init.md").exists())
            result = self._run_target_python(
                fixture,
                """
import json
from pathlib import Path

import contract_authority_context as authority
authority.ENGAGED_ADMISSION_COMPLETE = True
context = authority.resolve_top_level_context(Path.cwd())
print(json.dumps({
    "root": str(context.contract_root),
    "body": authority.read_declared_text(context, "docs/tools/prompts/architect_init.md", "prompt"),
}, sort_keys=True))
""",
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["root"], str(fixture.target_root / "contract"))
        self.assertIn("TARGET_ONLY:docs/tools/prompts/architect_init.md", payload["body"])

    def test_engaged_bundle_reads_flat_target_contract_rows_without_ui_sources(self) -> None:
        with AuthorityFixture(identity="planveyor") as fixture:
            fixture.activate_planveyor(
                authority_context.STATIC_PLANVEYOR_MERGE_REQUIRED_ENGAGED_PATHS,
                required_runtime_api=(5, 5),
                contract_root="contract",
            )
            result = self._run_target_python(
                fixture,
                """
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET

import contract_authority_context as authority
authority.ENGAGED_ADMISSION_COMPLETE = True
import build_role_bundles as bundles

root = Path.cwd()
runtime = Path(os.environ["PLANVEYOR_ROOT"])
context = authority.resolve_top_level_context(root)
bundle = bundles._build_context(
    "coder",
    repo_root=root,
    tooling_root=runtime,
    repo_profile_id="planveyor",
    content_profile_id="target-local",
    prompt_path=root / "contract/docs/tools/prompts/coder_init.md",
    out_dir=root / ".tmp/role_bundles",
    context=context,
)
xml = ET.fromstring(bundles._bundle_xml_bytes(bundle))
print(json.dumps({
    "state": context.state,
    "generation": context.generation_sha256,
    "repo_meta_ref_count": len(bundle.repo_meta_refs),
    "prompt_ref": xml.find("./meta/prompt_ref").attrib,
    "source_homes": [item.attrib["home"] for item in xml.findall("./source_refs/source_ref")],
    "control_refs": [item.attrib for item in xml.findall("./control_plane_refs/control_plane_ref")],
    "ui_refs": [item.attrib for item in xml.findall("./ui_source_refs/ui_source_ref")],
    "ui_binding": xml.find("./bundle_payload/bootstrap_slice[@id='ui_source_binding']") is not None,
    "authority": xml.find("./meta/authority_context").attrib,
}, sort_keys=True))
""",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["state"], "engaged")
            self.assertEqual(payload["repo_meta_ref_count"], 0)
            self.assertEqual(payload["prompt_ref"]["path"], "docs/tools/prompts/coder_init.md")
            self.assertEqual(payload["prompt_ref"]["home"], "contract")
            self.assertEqual(payload["source_homes"], ["contract"] * 4)
            self.assertEqual(
                [(row["home"], row["path"]) for row in payload["control_refs"]],
                [("contract", "docs/_meta/plan_vocab.json"), ("contract", "docs/_meta/doc_classes.json")],
            )
            self.assertEqual(payload["ui_refs"], [])
            self.assertFalse(payload["ui_binding"])
            self.assertEqual(payload["authority"]["project_root"], str(fixture.target_root))
            self.assertEqual(payload["authority"]["contract_root"], str(fixture.target_root / "contract"))
            self.assertEqual(payload["authority"]["generation_sha256"], payload["generation"])

    def test_docs_closeout_cli_reads_current_declared_prompt_before_classification(self) -> None:
        with AuthorityFixture(identity="planveyor") as fixture:
            fixture.activate_planveyor(
                authority_context.STATIC_PLANVEYOR_MERGE_REQUIRED_ENGAGED_PATHS,
                required_runtime_api=(5, 5),
            )
            write(
                fixture.target_root,
                "docs/tools/prompts/architect_docs_finalize_general.md",
                "declared prompt drift\n",
            )

            result = self._run_target_python(
                fixture,
                """
import contextlib
import io
import json
from pathlib import Path

import contract_authority_context as authority
authority.ENGAGED_ADMISSION_COMPLETE = True
import docs_closeout

def fake_classify(*, context, content_profile_id, **_kwargs):
    dispatch_sources = [
        prompt_file
        for _role, _lane, prompt_file, _wrapper in docs_closeout._dispatch_family_for_profile(
            content_profile_id,
            context=context,
        )
    ]
    return {
        "state": "completed",
        "content_profile_id": content_profile_id,
        "dispatch_sources": dispatch_sources,
        "prompt": authority.read_declared_text(
            context,
            "docs/tools/prompts/architect_docs_finalize_general.md",
            "closeout prompt",
        ),
    }

docs_closeout.plan_queue.project_relative_path = lambda *_args, **_kwargs: "docs/plans/current.md"
docs_closeout.load_bundle_payload = lambda _raw: {}
docs_closeout.classify_docs_closeout = fake_classify
output = io.StringIO()
with contextlib.redirect_stdout(output):
    rc = docs_closeout.main([
        "--project-root", str(Path.cwd()),
        "--plan", "docs/plans/not-reached.md",
        "--content-profile-id", "target-local",
        "--json",
    ])
print(json.dumps({"rc": rc, "payload": json.loads(output.getvalue())}, sort_keys=True))
""",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["rc"], 0)
            self.assertEqual(payload["payload"]["state"], "completed")
            self.assertEqual(payload["payload"]["content_profile_id"], "target-local")
            self.assertEqual(payload["payload"]["prompt"], "declared prompt drift\n")
            self.assertEqual(len(payload["payload"]["dispatch_sources"]), 8)
            self.assertTrue(all(
                source.startswith(str(fixture.target_root / "docs/tools/prompts"))
                for source in payload["payload"]["dispatch_sources"]
            ))
            self.assertFalse(any(
                source.startswith(str(fixture.runtime_root))
                for source in payload["payload"]["dispatch_sources"]
            ))

    def test_engaged_builder_uses_the_pinned_facade_and_context_cwd(self) -> None:
        with AuthorityFixture(identity="planveyor") as fixture:
            fixture.activate_planveyor(
                authority_context.STATIC_PLANVEYOR_MERGE_REQUIRED_ENGAGED_PATHS,
                required_runtime_api=(5, 5),
            )
            target_shim = write(
                fixture.target_root,
                "scripts/planveyor.zsh",
                "print -r -- target-shim-must-not-be-sourced\n",
            )

            result = self._run_target_python(
                fixture,
                """
import json
import os
from pathlib import Path

import contract_authority_context as authority
authority.ENGAGED_ADMISSION_COMPLETE = True
import build_role_bundles as bundles

root = Path.cwd()
runtime = Path(os.environ["PLANVEYOR_ROOT"])
context = authority.resolve_top_level_context(root)
expected_child_context = authority.context_to_json(context)
captured = {}

class Result:
    returncode = 0
    stdout = (
        "repo_profile_id\\tdefault\\n"
        "content_profile_id\\ttarget-local\\n"
        "coder\\t" + str(root / "docs/tools/prompts/coder_init.md") + "\\n"
    )
    stderr = ""

def fake_run(command, **kwargs):
    if Path(command[0]).name != "zsh":
        return real_run(command, **kwargs)
    captured["command"] = command
    captured["cwd"] = str(kwargs["cwd"])
    captured["env"] = kwargs["env"]
    return Result()

real_run = bundles.subprocess.run
bundles.subprocess.run = fake_run
profile, content_profile, prompts = bundles._load_prompt_manifest(
    root,
    runtime,
    ["coder"],
    context=context,
)

os.environ["PLANVEYOR_ROOT"] = str(root)
try:
    bundles._load_prompt_manifest(root, runtime, ["coder"], context=context)
except bundles.BuildError as error:
    mismatch = str(error)
else:
    raise SystemExit("foreign PLANVEYOR_ROOT was accepted")

print(json.dumps({
    "command": captured["command"],
    "cwd": captured["cwd"],
    "env_context": captured["env"].get("_PLANVEYOR_AUTHORITY_CONTEXT_V1"),
    "expected_child_context": expected_child_context,
    "env_runtime": captured["env"].get("PLANVEYOR_ROOT"),
    "profile": profile,
    "content_profile": content_profile,
    "prompt": str(prompts["coder"]),
    "mismatch": mismatch,
}, sort_keys=True))
""",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            command = payload["command"]
            self.assertEqual(command[:2], ["/bin/zsh", "-dfc"])
            self.assertIn("planveyor_source_runtime ", command[2])
            self.assertIn("_planveyor_runtime_api_guard 5 5", command[2])
            self.assertIn(str(fixture.runtime_root / "scripts/planveyor.zsh"), command[2])
            self.assertNotIn(str(target_shim), command[2])
            self.assertEqual(command[3], "planveyor_role_bundle_prompt_manifest")
            self.assertEqual(command[4], str(fixture.target_root))
            self.assertEqual(command[5], "coder")
            self.assertEqual(payload["cwd"], str(fixture.target_root))
            self.assertEqual(payload["env_context"], payload["expected_child_context"])
            self.assertEqual(payload["env_runtime"], str(fixture.runtime_root))
            self.assertEqual(payload["profile"], "default")
            self.assertEqual(payload["content_profile"], "target-local")
            self.assertEqual(
                payload["prompt"],
                str(fixture.target_root / "docs/tools/prompts/coder_init.md"),
            )
            self.assertIn("PLANVEYOR_ROOT", payload["mismatch"])

    def test_omitted_context_reads_current_content_from_a_marked_git_target(self) -> None:
        with AuthorityFixture(identity="planveyor") as fixture:
            fixture.activate_planveyor(
                authority_context.STATIC_PLANVEYOR_MERGE_REQUIRED_ENGAGED_PATHS,
                required_runtime_api=(5, 5),
            )
            # A committed ordinary content edit leaves the v2 selector
            # untracked and continues through the active local reader.
            write(
                fixture.target_root,
                "docs/tools/prompts/coder_init.md",
                "# Committed current prompt\nRead docs/roles/coder.md.\n",
            )
            git(fixture.target_root, "add", "--", "docs/tools/prompts/coder_init.md")
            git(fixture.target_root, "commit", "--quiet", "-m", "committed current prompt")

            result = self._run_target_python(
                fixture,
                """
import json
import os
from pathlib import Path

import build_role_bundles as bundles

root = Path.cwd()
context = bundles._build_context(
    "coder",
    repo_root=root,
    tooling_root=Path(os.environ["PLANVEYOR_ROOT"]),
    repo_profile_id="planveyor",
    content_profile_id="target-local",
    prompt_path=root / "docs/tools/prompts/coder_init.md",
    out_dir=root / ".tmp/role_bundles",
)
print(json.dumps({"state": context.authority_context.state, "prompt": context.prompt_text}, sort_keys=True))
""",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["state"], "engaged")
            self.assertEqual(payload["prompt"], "# Committed current prompt\nRead docs/roles/coder.md.\n")
            self.assertFalse((fixture.target_root / ".tmp/role_bundles").exists())

    def test_direct_readers_do_not_import_a_target_scripts_package(self) -> None:
        """Direct readers bypass target package poison and reject invalid targets."""

        def commands_for(
            fixture: AuthorityFixture,
        ) -> tuple[tuple[str, tuple[str, ...], bool], ...]:
            return (
                (
                    "build_role_bundles.py",
                    (
                        "--role",
                        "coder",
                        "--out-dir",
                        str(fixture.root / "role-bundles"),
                    ),
                    True,
                ),
                (
                    "docs_closeout.py",
                    (
                        "--project-root",
                        str(fixture.target_root),
                        "--plan",
                        "docs/plans/not-reached.md",
                        "--json",
                    ),
                    False,
                ),
            )

        with AuthorityFixture(identity="planveyor") as fixture:
            fixture.activate_planveyor(
                authority_context.STATIC_PLANVEYOR_MERGE_REQUIRED_ENGAGED_PATHS,
                required_runtime_api=(5, 5),
            )
            sentinel = fixture.root / "target-package-imported"
            poison = (
                "from pathlib import Path\n"
                "import os\n"
                "Path(os.environ['AUTHORITY_POISON_SENTINEL']).write_text('executed', encoding='utf-8')\n"
            )
            write(fixture.target_root, "scripts/__init__.py", poison)
            write(fixture.target_root, "scripts/contract_authority_context.py", poison)
            git(
                fixture.target_root,
                "add",
                "--",
                "scripts/__init__.py",
                "scripts/contract_authority_context.py",
            )
            git(fixture.target_root, "commit", "--quiet", "-m", "committed target package poison")

            env = fixture.environment()
            env["AUTHORITY_POISON_SENTINEL"] = str(sentinel)
            # A target package first in PYTHONPATH used to make package-first
            # imports execute target scripts before a reader could fail closed.
            env["PYTHONPATH"] = str(fixture.target_root)
            for script, arguments, succeeds in commands_for(fixture):
                with self.subTest(script=script):
                    result = run_python_entry(
                        fixture,
                        fixture.runtime_root / "scripts" / script,
                        *arguments,
                        environment=env,
                    )
                    if succeeds:
                        self.assertEqual(result.returncode, 0, result.stderr)
                    else:
                        self.assertNotEqual(result.returncode, 0, result.stdout)
                    self.assertFalse(sentinel.exists(), result.stderr)
                    if script == "build_role_bundles.py":
                        self.assertTrue((fixture.root / "role-bundles/coder.xml").is_file())

                    # A generic package can be preloaded by a thin shim.  It
                    # is not itself proof of a hostile authority alias, so
                    # direct readers must bypass it without executing files
                    # below its target-owned package path.
                    preloaded_source = f"""
import runpy
import sys
import types

package = types.ModuleType('scripts')
package.__path__ = [{str(fixture.target_root / 'scripts')!r}]
sys.modules['scripts'] = package
sys.argv = {[script, *arguments]!r}
try:
    runpy.run_path({str(fixture.runtime_root / 'scripts' / script)!r}, run_name='__main__')
except SystemExit:
    pass
print('blocked-with-generic-package')
"""
                    preloaded = subprocess.run(
                        [sys.executable, "-B", "-c", preloaded_source],
                        cwd=fixture.target_root,
                        env=env,
                        text=True,
                        capture_output=True,
                        check=False,
                        timeout=60,
                    )
                    # Other direct dependencies may independently reject a
                    # generic package; the reader boundary only promises not
                    # to execute target-owned authority code.
                    self.assertFalse(sentinel.exists(), preloaded.stderr)

                    alias_source = f"""
import runpy
import sys
import types

foreign = types.ModuleType('contract_authority_context')
foreign.__file__ = {str(fixture.target_root / 'scripts' / 'contract_authority_context.py')!r}
sys.modules['contract_authority_context'] = foreign
try:
    runpy.run_path({str(fixture.runtime_root / 'scripts' / script)!r}, run_name='__main__')
except ImportError:
    print('foreign-authority-alias-rejected')
else:
    raise SystemExit('foreign authority alias was accepted')
"""
                    alias_result = subprocess.run(
                        [sys.executable, "-B", "-c", alias_source],
                        cwd=fixture.target_root,
                        env=env,
                        text=True,
                        capture_output=True,
                        check=False,
                        timeout=60,
                    )
                    self.assertEqual(alias_result.returncode, 0, alias_result.stderr)
                    self.assertIn("foreign-authority-alias-rejected", alias_result.stdout)
                    self.assertFalse(sentinel.exists(), alias_result.stderr)

        # The same poison and a committed ordinary local-body edit cannot
        # alter authority imports or make the active reader reject current
        # allowed content.
        with AuthorityFixture(identity="planveyor") as fixture:
            fixture.activate_planveyor(
                authority_context.STATIC_PLANVEYOR_MERGE_REQUIRED_ENGAGED_PATHS,
                required_runtime_api=(5, 5),
            )
            sentinel = fixture.root / "invalid-target-package-imported"
            poison = (
                "from pathlib import Path\n"
                "import os\n"
                "Path(os.environ['AUTHORITY_POISON_SENTINEL']).write_text('executed', encoding='utf-8')\n"
            )
            write(fixture.target_root, "scripts/__init__.py", poison)
            write(fixture.target_root, "scripts/contract_authority_context.py", poison)
            write(
                fixture.target_root,
                "docs/tools/prompts/coder_init.md",
                "# Committed current prompt\nRead docs/roles/coder.md.\n",
            )
            git(
                fixture.target_root,
                "add",
                "--",
                "scripts/__init__.py",
                "scripts/contract_authority_context.py",
                "docs/tools/prompts/coder_init.md",
            )
            git(fixture.target_root, "commit", "--quiet", "-m", "committed current target package poison")

            env = fixture.environment()
            env["AUTHORITY_POISON_SENTINEL"] = str(sentinel)
            env["PYTHONPATH"] = str(fixture.target_root)
            for script, arguments, succeeds in commands_for(fixture):
                with self.subTest(current_target=script):
                    result = run_python_entry(
                        fixture,
                        fixture.runtime_root / "scripts" / script,
                        *arguments,
                        environment=env,
                    )
                    if succeeds:
                        self.assertEqual(result.returncode, 0, result.stderr)
                    else:
                        self.assertNotEqual(result.returncode, 0, result.stdout)
                        self.assertNotIn("contract_authority:", result.stdout + result.stderr)
                    self.assertFalse(sentinel.exists(), result.stderr)
                    if script == "build_role_bundles.py":
                        self.assertTrue((fixture.root / "role-bundles/coder.xml").is_file())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

#!/usr/bin/env python3
"""Focused real-Git tests for the immutable contract authority context."""

from __future__ import annotations

import contextlib
from dataclasses import replace
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in os.sys.path:
    os.sys.path.insert(0, str(SCRIPT_DIR))

import contract_authority_context as module  # noqa: E402
from authority_bootstrap_test_support import (  # noqa: E402
    run_bootstrapped_bridge,
    run_python_entry,
    supported_bridge_module,
)
from test_contract_authority_support import (  # noqa: E402
    AuthorityFixture,
    PLANVEYOR_MERGE_GATE_POLICY_PATH,
    planveyor_merge_gate_policy,
    write,
)
from test_support.process_contract_fixtures import (  # noqa: E402
    NON_GIT_ROOT_SKIP_REASON,
    inside_git_work_tree,
    standalone_git_root,
)

runtime = module._runtime


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _reseal_context_envelope(envelope: dict[str, object]) -> str:
    body = {key: value for key, value in envelope.items() if key != "context_sha256"}
    envelope["context_sha256"] = module._sha256_json(body)
    return json.dumps(envelope, sort_keys=True, separators=(",", ":"))


class ContractAuthorityContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="contract-authority-context-")
        self.base = Path(self.temp_dir.name).resolve()
        self.runtime_root = self.base / "runtime"
        self.runtime_root.mkdir()
        self.runtime_git_dir = self.runtime_root / ".git"
        self.runtime_git_dir.mkdir()
        self.pin = runtime.LoadedRuntimePin(
            runtime_root=self.runtime_root,
            git_dir=self.runtime_git_dir,
            runtime_api_version=5,
            commit="1" * 40,
            tree="2" * 40,
            closure_spec_sha256="3" * 64,
            closure_rows=(),
            closure_rows_sha256="4" * 64,
            closure_sha256="5" * 64,
            pin_sha256="6" * 64,
        )
        self.context_source_match = mock.patch.object(
            module,
            "_first_loaded_context_source_matches_runtime_pin",
            return_value=True,
        )
        self.context_source_match.start()

    def tearDown(self) -> None:
        self.context_source_match.stop()
        self.temp_dir.cleanup()

    def _git(self, root: Path, *args: str) -> str:
        completed = subprocess.run(
            ["git", "-C", str(root), *args],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if completed.returncode != 0:
            self.fail(f"git {' '.join(args)} failed: {completed.stderr}")
        return completed.stdout

    def _write(self, root: Path, relative: str, text: str) -> None:
        target = root.joinpath(*relative.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def _init_repo(self, name: str | Path = "planveyor") -> Path:
        root = self.base / name
        root.mkdir(parents=True)
        self._git(root, "init", "-q")
        self._git(root, "config", "user.email", 'authority' + '@' + 'example' + '.' + 'test')
        self._git(root, "config", "user.name", "Authority Test")
        return root

    def _commit_all(self, root: Path, message: str) -> None:
        self._git(root, "add", "--all")
        self._git(root, "commit", "-q", "-m", message)

    def _commit_paths(self, root: Path, message: str, *paths: str) -> None:
        self._git(root, "add", "--", *paths)
        self._git(root, "commit", "-q", "-m", message)

    def _assert_local_marker_untracked(self, root: Path) -> None:
        self.assertEqual(
            self._git(root, "status", "--porcelain", "--", module._snapshot.MARKER_PATH).strip(),
            f"?? {module._snapshot.MARKER_PATH}",
        )

    def _head_row(self, root: Path, relative: str) -> tuple[str, str]:
        row = self._git(root, "ls-files", "--stage", "--", relative).strip()
        self.assertTrue(row, relative)
        mode, oid, _stage_and_path = row.split(" ", 2)
        return mode, oid

    def _make_complete_candidate(
        self,
        *,
        contract_root: str = ".",
        name: str | Path = "planveyor",
        required_runtime_api: tuple[int, int] = (5, 5),
    ) -> Path:
        root = self._init_repo(name)
        self.assertIn(contract_root, {".", "contract"})

        def target_relative(relative: str) -> str:
            return relative if contract_root == "." else f"{contract_root}/{relative}"

        static_paths = (
            module.STATIC_PLANVEYOR_MERGE_REQUIRED_ENGAGED_PATHS
            if required_runtime_api[0] >= 4
            else module.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS
        )
        declared_paths = static_paths
        for relative in declared_paths:
            self._write(root, target_relative(relative), f"target body: {relative}\n")
        if required_runtime_api[0] >= 4:
            self._write(
                root,
                target_relative(PLANVEYOR_MERGE_GATE_POLICY_PATH),
                planveyor_merge_gate_policy().decode("utf-8"),
            )
        self._write(root, "unrelated.txt", "before\n")
        self._commit_all(root, "target bodies")

        rows = []
        for relative in declared_paths:
            declared_relative = target_relative(relative)
            mode, oid = self._head_row(root, declared_relative)
            data = (root / declared_relative).read_bytes()
            rows.append(
                {
                    "path": declared_relative,
                    "mode": mode,
                    "blob_oid": oid,
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
            )
        manifest_relative = target_relative("docs/_meta/contract_closure.v1.json")
        manifest = {"schema_version": 1, "required_content": rows}
        self._write(root, manifest_relative, json.dumps(manifest, sort_keys=True) + "\n")
        baseline = self._git(root, "rev-parse", "HEAD").strip()
        marker = {
            "schema_version": 1,
            "repository_id": "planveyor",
            "authority_mode": "target-local",
            "contract_root": contract_root,
            "required_runtime_api": {
                "minimum": required_runtime_api[0],
                "maximum": required_runtime_api[1],
            },
            "closure_manifest": manifest_relative,
            "source_baseline": {"repository_id": "planveyor", "commit": baseline},
        }
        self._write(root, module._snapshot.MARKER_PATH, json.dumps(marker, sort_keys=True) + "\n")
        self._commit_all(root, "authority marker")
        return root

    def _make_complete_local(
        self,
        *,
        contract_root: str = ".",
        name: str | Path = "planveyor",
        repository_id: str = "planveyor",
        required_runtime_api: tuple[int, int] = (5, 5),
    ) -> Path:
        root = self._init_repo(name)
        self.assertIn(contract_root, {".", "contract", "contract/nested"})

        def physical(relative: str) -> str:
            return relative if contract_root == "." else f"{contract_root}/{relative}"

        logical_paths = module.STATIC_PLANVEYOR_MERGE_REQUIRED_ENGAGED_PATHS
        for relative in logical_paths:
            self._write(root, physical(relative), f"target body: {relative}\n")
        self._write(root, physical(PLANVEYOR_MERGE_GATE_POLICY_PATH), planveyor_merge_gate_policy().decode("utf-8"))
        self._write(root, "unrelated.txt", "before\n")
        self._commit_all(root, "local target bodies")
        self._write(
            root,
            module._snapshot.MARKER_PATH,
            json.dumps(
                {
                    "schema_version": 3,
                    "source_commit": self.pin.commit,
                    "repository_id": repository_id,
                    "authority_mode": "target-local",
                    "contract_root": contract_root,
                    "required_runtime_api": {
                        "minimum": required_runtime_api[0],
                        "maximum": required_runtime_api[1],
                    },
                },
                sort_keys=True,
            ) + "\n",
        )
        return root

    def _engaged_patches(self, *, pin: runtime.LoadedRuntimePin | None = None):
        active_pin = self.pin if pin is None else pin
        return (
            mock.patch.object(module, "ENGAGED_ADMISSION_COMPLETE", True),
            mock.patch.object(module, "_executing_runtime_root", return_value=self.runtime_root),
            mock.patch.object(
                module._runtime,
                "_first_loaded_runtime_observation",
                return_value=runtime._FirstLoadedRuntimeObservation(self.runtime_root, active_pin),
            ),
            mock.patch.object(module._runtime, "verify_loaded_runtime_pin", side_effect=lambda value: value),
        )

    def _capture_engaged(
        self,
        root: Path,
        *,
        pin: runtime.LoadedRuntimePin | None = None,
    ) -> module.ContractContext:
        active_pin = self.pin if pin is None else pin
        admission, execution_root, first_observation, verify_pin = self._engaged_patches(pin=active_pin)
        with admission, execution_root, first_observation, verify_pin, mock.patch.dict(os.environ, {}, clear=True):
            return module.resolve_top_level_context(
                root,
                runtime_root=self.runtime_root,
                loaded_pin=active_pin,
            )

    def _run_fixture_bridge(
        self,
        fixture: AuthorityFixture,
        *arguments: str,
    ) -> subprocess.CompletedProcess[str]:
        return run_bootstrapped_bridge(fixture, *arguments)

    def _call_supported_bridge(self, bridge: object, *arguments: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = getattr(bridge, "main")(list(arguments))
        return code, stdout.getvalue(), stderr.getvalue()

    def _capture_fixture_bridge_context(
        self,
        fixture: AuthorityFixture,
    ) -> tuple[str, dict[str, object], str]:
        fixture.activate_planveyor(
            module.STATIC_PLANVEYOR_MERGE_REQUIRED_ENGAGED_PATHS,
            required_runtime_api=(5, 5),
        )
        pin = self._run_fixture_bridge(
            fixture,
            "runtime-pin",
            "--runtime-root",
            str(fixture.runtime_root),
            "--entrypoint",
            str(fixture.runtime_root / "scripts" / "planveyor.zsh"),
        )
        self.assertEqual(pin.returncode, 0, pin.stdout + pin.stderr)
        runtime_summary = pin.stdout.strip()
        captured = self._run_fixture_bridge(
            fixture,
            "context",
            "--project-root",
            str(fixture.target_root),
            "--runtime-pin-summary",
            runtime_summary,
        )
        self.assertEqual(captured.returncode, 0, captured.stdout + captured.stderr)
        envelope = json.loads(captured.stdout)
        self.assertEqual(envelope["state"], "engaged")
        self.assertEqual(
            envelope["entry_observation_provenance"],
            module.ENTRY_OBSERVATION_PROVENANCE_OBSERVED_LOCAL,
        )
        compact = json.dumps(envelope, sort_keys=True, separators=(",", ":"))
        return runtime_summary, envelope, compact

    def test_context_validate_accepts_project_root_and_complete_caller_tuple_formats(self) -> None:
        with AuthorityFixture(identity="planveyor") as fixture:
            runtime_summary, envelope, compact = self._capture_fixture_bridge_context(fixture)
            project_root = str(fixture.target_root)
            common = (
                "context-validate",
                "--context",
                compact,
                "--project-root",
                project_root,
                "--runtime-pin-summary",
                runtime_summary,
            )

            project_only = self._run_fixture_bridge(fixture, *common)
            self.assertEqual(project_only.returncode, 0, project_only.stdout + project_only.stderr)
            project_result = json.loads(project_only.stdout)
            self.assertEqual(project_result["entry_observation"], envelope["entry_observation"])
            self.assertEqual(
                project_result["entry_observation_provenance"],
                module.ENTRY_OBSERVATION_PROVENANCE_INHERITED_SUPPLIED_UNVERIFIED,
            )
            self.assertEqual(
                module.parse_context_envelope(project_only.stdout),
                project_result,
            )

            complete = self._run_fixture_bridge(
                fixture,
                *common,
                "--caller-state",
                str(envelope["state"]),
                "--caller-generation-sha256",
                str(envelope["generation_sha256"]),
            )
            self.assertEqual(complete.returncode, 0, complete.stdout + complete.stderr)
            self.assertEqual(json.loads(complete.stdout), project_result)

            state = self._run_fixture_bridge(
                fixture,
                *common,
                "--caller-state",
                str(envelope["state"]),
                "--caller-generation-sha256",
                str(envelope["generation_sha256"]),
                "--format",
                "state",
            )
            self.assertEqual(state.returncode, 0, state.stdout + state.stderr)
            self.assertEqual(state.stdout, "engaged\n")

    def test_context_validate_rejects_bad_caller_tuples_before_active_recapture(self) -> None:
        harness = textwrap.dedent(
            """\
            import importlib.util
            import json
            import sys
            import types
            from pathlib import Path

            bridge_path = Path(sys.argv[1]).resolve()
            compact = sys.argv[2]
            project_root = sys.argv[3]
            state = sys.argv[4]
            generation = sys.argv[5]
            spec = importlib.util.spec_from_file_location("context_validate_probe", bridge_path)
            assert spec is not None and spec.loader is not None
            bridge = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = bridge
            spec.loader.exec_module(bridge)

            def active_recapture_forbidden(**_kwargs):
                raise AssertionError("ACTIVE_CONTEXT_RECAPTURE_REACHED")

            bridge._context_from_envelope = active_recapture_forbidden
            base = {
                "command": "context-validate",
                "context": compact,
                "runtime_pin_summary": None,
                "runtime_root": None,
                "project_root": project_root,
                "caller_state": state,
                "caller_generation_sha256": generation,
                "format": "json",
            }
            cases = (
                ("missing_state", {"caller_state": None}, "context_tuple_incomplete"),
                ("missing_generation", {"caller_generation_sha256": None}, "context_tuple_incomplete"),
                ("missing_root", {"project_root": None}, "context_tuple_incomplete"),
                ("wrong_state", {"caller_state": "legacy"}, "context_tuple_mismatch"),
                ("wrong_root", {"project_root": project_root + "-wrong"}, "context_tuple_mismatch"),
                ("wrong_generation", {"caller_generation_sha256": "0" * 64}, "context_tuple_mismatch"),
                ("malformed", {"context": "{not-json"}, "context_envelope_invalid"),
            )
            results = []
            for name, replacements, expected in cases:
                values = dict(base)
                values.update(replacements)
                try:
                    bridge._command(types.SimpleNamespace(**values))
                except bridge.BridgeError as exc:
                    results.append({"name": name, "code": exc.code, "expected": expected})
                else:
                    raise AssertionError(f"{name} unexpectedly reached active validation")
            print(json.dumps(results, sort_keys=True))
            """
        )
        with AuthorityFixture(identity="planveyor") as fixture:
            _summary, envelope, compact = self._capture_fixture_bridge_context(fixture)
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-X",
                    "pycache_prefix=/dev/null",
                    "-c",
                    harness,
                    str(fixture.runtime_root / "scripts" / "contract_authority_bridge.py"),
                    compact,
                    str(fixture.target_root),
                    str(envelope["state"]),
                    str(envelope["generation_sha256"]),
                ],
                cwd=fixture.target_root,
                env=fixture.environment(),
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        results = json.loads(result.stdout)
        self.assertEqual(
            [(item["name"], item["code"]) for item in results],
            [(item["name"], item["expected"]) for item in results],
        )

    def test_context_validate_state_format_rejects_target_and_runtime_drift(self) -> None:
        for drift in ("target", "runtime"):
            with self.subTest(drift=drift), AuthorityFixture(identity="planveyor") as fixture:
                fixture.activate_planveyor(
                    module.STATIC_PLANVEYOR_MERGE_REQUIRED_ENGAGED_PATHS,
                    required_runtime_api=(5, 5),
                )
                with supported_bridge_module(fixture) as bridge:
                    pin_code, pin_stdout, pin_stderr = self._call_supported_bridge(
                        bridge,
                        "runtime-pin",
                        "--runtime-root",
                        str(fixture.runtime_root),
                        "--entrypoint",
                        str(fixture.runtime_root / "scripts" / "planveyor.zsh"),
                    )
                    self.assertEqual(pin_code, 0, pin_stdout + pin_stderr)
                    context_code, context_stdout, context_stderr = self._call_supported_bridge(
                        bridge,
                        "context",
                        "--project-root",
                        str(fixture.target_root),
                        "--runtime-pin-summary",
                        pin_stdout.strip(),
                    )
                    self.assertEqual(context_code, 0, context_stdout + context_stderr)
                    envelope = json.loads(context_stdout)
                    compact = json.dumps(envelope, sort_keys=True, separators=(",", ":"))
                    if drift == "target":
                        changed = fixture.target_root / module.REQUIRED_ENGAGED_PATHS[0]
                    else:
                        changed = fixture.runtime_root / "scripts" / "plan_lint.py"
                    changed.write_bytes(changed.read_bytes() + b"\n# disposable context validation drift\n")

                    code, stdout, stderr = self._call_supported_bridge(
                        bridge,
                        "context-validate",
                        "--context",
                        compact,
                        "--project-root",
                        str(fixture.target_root),
                        "--caller-state",
                        str(envelope["state"]),
                        "--caller-generation-sha256",
                        str(envelope["generation_sha256"]),
                        "--runtime-pin-summary",
                        pin_stdout.strip(),
                        "--format",
                        "state",
                    )

                if drift == "target":
                    self.assertEqual(code, 0, stdout + stderr)
                    self.assertEqual(stdout, "engaged\n")
                    self.assertEqual(stderr, "")
                else:
                    self.assertEqual(code, 2, stdout + stderr)
                    self.assertEqual(stdout, "")
                    self.assertIn("runtime_closure_worktree_blob_mismatch", stderr)
                    self.assertNotIn("context_tuple", stderr)

    def test_required_paths_are_flat_and_cover_finite_target_inputs(self) -> None:
        paths = module.REQUIRED_ENGAGED_PATHS
        self.assertIsInstance(paths, tuple)
        self.assertEqual(len(paths), len(set(paths)))
        self.assertEqual(len(module._TARGET_LOCAL_PROMPT_FILENAMES), 34)
        self.assertEqual(module._PROMPT_FILENAMES, module._TARGET_LOCAL_PROMPT_FILENAMES)
        self.assertEqual(len(module._PROMPT_FILENAMES), 34)
        self.assertEqual(len(module._PROMPT_FILENAMES), len(set(module._PROMPT_FILENAMES)))
        self.assertEqual(
            {
                path.removeprefix("docs/tools/prompts/")
                for path in paths
                if path.startswith("docs/tools/prompts/")
            },
            set(module._TARGET_LOCAL_PROMPT_FILENAMES),
        )
        self.assertIn("docs/tools/prompts/architect_init.md", paths)
        self.assertIn("docs/roles/manager.md", paths)
        self.assertIn("docs/playbooks/docs_architecture.md", paths)
        self.assertNotIn("docs/playbooks/dev_ui_mod_tabs_fragments.md", paths)
        self.assertIn("docs/_meta/plan_vocab.json", paths)
        self.assertIn("docs/_meta/doc_classes.json", paths)
        self.assertIn("docs/smoke_visual.md", paths)
        self.assertIn("docs/testing_runbook.md", paths)
        self.assertNotIn("scripts/review_range_scaffold.py", paths)
        self.assertFalse(any("profiles/planveyor" in path for path in paths))
        self.assertEqual(
            module.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS,
            (
                *module.STATIC_REQUIRED_ENGAGED_PREFIX,
                *module.STATIC_REQUIRED_ENGAGED_TAIL,
            ),
        )
        self.assertEqual(len(module.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS), 59)
        self.assertNotIn("docs/_meta/ui_source_binding.v1.json", module.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS)
        self.assertEqual(
            module.STATIC_PLANVEYOR_MERGE_REQUIRED_ENGAGED_PATHS,
            (*module.STATIC_PLANVEYOR_REQUIRED_ENGAGED_PATHS, module.PLANVEYOR_MERGE_GATE_POLICY_PATH),
        )
        self.assertEqual(len(module.STATIC_PLANVEYOR_MERGE_REQUIRED_ENGAGED_PATHS), 60)

    def test_api_four_merge_capability_rejects_ui_only_or_old_runtime(self) -> None:
        root = self._make_complete_local(name=Path("api-range") / "planveyor")
        api_three_pin = replace(self.pin, runtime_api_version=3)
        with self.assertRaises(module.ContractAuthorityError) as old_runtime:
            self._capture_engaged(root, pin=api_three_pin)
        self.assertEqual(old_runtime.exception.reason_code, "runtime_api_incompatible")

        marker_path = root / module._snapshot.MARKER_PATH
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        marker["required_runtime_api"] = {"minimum": 3, "maximum": 3}
        self._write(root, module._snapshot.MARKER_PATH, json.dumps(marker, sort_keys=True) + "\n")

        with self.assertRaises(module.ContractAuthorityError) as old_marker:
            self._capture_engaged(root)
        self.assertEqual(old_marker.exception.reason_code, "runtime_api_incompatible")

    def test_marker_cannot_engage_while_compiled_admission_is_incomplete(self) -> None:
        root = self._make_complete_local()
        with mock.patch.object(module, "ENGAGED_ADMISSION_COMPLETE", False), mock.patch.object(
            module, "_executing_runtime_root", return_value=self.runtime_root
        ), mock.patch.dict(
            os.environ, {}, clear=True
        ):
            with self.assertRaises(module.ContractAuthorityError) as raised:
                module.resolve_top_level_context(root, runtime_root=self.runtime_root, loaded_pin=self.pin)
        self.assertEqual(raised.exception.reason_code, "engaged_admission_incomplete")

    def test_markerless_self_identity_uses_canonical_common_dir(self) -> None:
        runtime_root = self._init_repo("My Planveyor")
        self._write(runtime_root, "tracked.txt", "runtime\n")
        self._commit_all(runtime_root, "runtime base")
        linked = self.base / "проект"
        self._git(runtime_root, "worktree", "add", "--detach", str(linked), "HEAD")
        foreign = self._init_repo("app (1)")
        self._write(foreign, "tracked.txt", "foreign\n")
        self._commit_all(foreign, "foreign base")
        unattested = runtime._FirstLoadedRuntimeObservation(runtime_root, None)

        with mock.patch.object(module, "_executing_runtime_root", return_value=runtime_root), mock.patch.object(
            module._runtime, "_first_loaded_runtime_observation", return_value=unattested
        ), mock.patch.dict(os.environ, {}, clear=True):
            same_root = module.resolve_top_level_context(
                runtime_root,
                runtime_root=runtime_root,
                loaded_pin="unattested_legacy",
            )
            linked_root = module.resolve_top_level_context(
                linked,
                runtime_root=runtime_root,
                loaded_pin="unattested_legacy",
            )
            foreign_root = module.resolve_top_level_context(
                foreign,
                runtime_root=runtime_root,
                loaded_pin="unattested_legacy",
            )

        self.assertEqual(same_root.state, "legacy")
        self.assertEqual(same_root.behavior_identity, "planveyor")
        self.assertEqual(linked_root.behavior_identity, "planveyor")
        self.assertEqual(foreign_root.behavior_identity, "default")
        self.assertNotEqual(same_root.generation_sha256, linked_root.generation_sha256)

    def test_local_v2_repository_id_is_semantic_for_committed_content_and_untracked_marker(self) -> None:
        primary = self._make_complete_local(
            name=Path("My Planveyor") / "primary checkout",
            repository_id="acme-app",
        )
        linked = self.base / "проект (1)"
        self._git(primary, "worktree", "add", "--detach", str(linked), "HEAD")
        marker_bytes = (primary / module._snapshot.MARKER_PATH).read_bytes()
        marker_path = linked / module._snapshot.MARKER_PATH
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_path.write_bytes(marker_bytes)

        primary_context = self._capture_engaged(primary)
        linked_context = self._capture_engaged(linked)
        self.assertEqual(primary_context.behavior_identity, "acme-app")
        self.assertEqual(linked_context.behavior_identity, "acme-app")
        self._assert_local_marker_untracked(primary)
        self._assert_local_marker_untracked(linked)
        self.assertEqual(
            module._git_common_directory(primary, context="primary test binding"),
            module._git_common_directory(linked, context="linked test binding"),
        )
        self.assertNotEqual(primary_context.project_root, linked_context.project_root)
        self.assertNotEqual(primary_context.entry_observation.git_dir, linked_context.entry_observation.git_dir)
        self.assertNotEqual(primary_context.generation_sha256, linked_context.generation_sha256)


    def test_markerless_runtime_successful_common_dir_then_failed_discovery_preserves_reason(self) -> None:
        target = self._init_repo("test_markerless_runtime_successful_common_dir_then_failed_discovery_preserves_reason-target")
        self._write(target, "tracked.txt", "target\n")
        self._commit_all(target, "target base")
        runtime = self._init_repo("test_markerless_runtime_successful_common_dir_then_failed_discovery_preserves_reason-runtime")
        self._write(runtime, "tracked.txt", "runtime\n")
        self._commit_all(runtime, "runtime base")
        original_git_command = module._git_command
        common_arguments = ("rev-parse", "--git-common-dir")
        discovery_arguments = (
            "rev-parse", "--is-inside-work-tree", "--show-toplevel", "--absolute-git-dir",
        )
        events = []

        def git_for_runtime(requested, *arguments, **kwargs):
            exact_runtime = Path(requested).resolve() == runtime.resolve()
            if exact_runtime and arguments == discovery_arguments:
                completed = subprocess.CompletedProcess(
                    args=["git", *arguments], returncode=73,
                    stdout=b"",
                    stderr=b"DISCOVERY_STAGE_STDERR_MUST_STAY_PRIVATE\n",
                )
            else:
                completed = original_git_command(requested, *arguments, **kwargs)
            if exact_runtime:
                events.append((arguments, completed.returncode))
            return completed

        self.assertTrue(module._has_ancestor_git_metadata(runtime))
        with mock.patch.object(module, "_git_command", side_effect=git_for_runtime):
            with self.assertRaises(module.ContractAuthorityError) as raised:
                module._markerless_behavior_identity(target, runtime)

        self.assertEqual(events, [(common_arguments, 0), (discovery_arguments, 73)])
        self.assertEqual(raised.exception.reason_code, "git_discovery_failed")
        self.assertNotIn("DISCOVERY_STAGE_STDERR_MUST_STAY_PRIVATE", str(raised.exception))

    def test_markerless_runtime_successful_common_dir_then_foreign_top_fails_closed(self) -> None:
        target = self._init_repo("test_markerless_runtime_successful_common_dir_then_foreign_top_fails_closed-target")
        self._write(target, "tracked.txt", "target\n")
        self._commit_all(target, "target base")
        runtime = self._init_repo("test_markerless_runtime_successful_common_dir_then_foreign_top_fails_closed-runtime")
        self._write(runtime, "tracked.txt", "runtime\n")
        self._commit_all(runtime, "runtime base")
        original_git_command = module._git_command
        common_arguments = ("rev-parse", "--git-common-dir")
        discovery_arguments = (
            "rev-parse", "--is-inside-work-tree", "--show-toplevel", "--absolute-git-dir",
        )
        events = []

        def git_for_runtime(requested, *arguments, **kwargs):
            exact_runtime = Path(requested).resolve() == runtime.resolve()
            if exact_runtime and arguments == discovery_arguments:
                completed = subprocess.CompletedProcess(
                    args=["git", *arguments], returncode=0,
                    stdout=("true\n" + str(target.resolve()) + "\n" + str((target / ".git").resolve()) + "\n").encode("utf-8"),
                    stderr=b"DISCOVERY_STAGE_STDERR_MUST_STAY_PRIVATE\n",
                )
            else:
                completed = original_git_command(requested, *arguments, **kwargs)
            if exact_runtime:
                events.append((arguments, completed.returncode))
            return completed

        self.assertTrue(module._has_ancestor_git_metadata(runtime))
        with mock.patch.object(module, "_git_command", side_effect=git_for_runtime):
            with self.assertRaises(module.ContractAuthorityError) as raised:
                module._markerless_behavior_identity(target, runtime)

        self.assertEqual(events, [(common_arguments, 0), (discovery_arguments, 0)])
        self.assertEqual(raised.exception.reason_code, "git_command_failed")
        self.assertNotIn("DISCOVERY_STAGE_STDERR_MUST_STAY_PRIVATE", str(raised.exception))

    def test_markerless_runtime_successful_common_dir_then_malformed_discovery_preserves_reason(self) -> None:
        target = self._init_repo("test_markerless_runtime_successful_common_dir_then_malformed_discovery_preserves_reason-target")
        self._write(target, "tracked.txt", "target\n")
        self._commit_all(target, "target base")
        runtime = self._init_repo("test_markerless_runtime_successful_common_dir_then_malformed_discovery_preserves_reason-runtime")
        self._write(runtime, "tracked.txt", "runtime\n")
        self._commit_all(runtime, "runtime base")
        original_git_command = module._git_command
        common_arguments = ("rev-parse", "--git-common-dir")
        discovery_arguments = (
            "rev-parse", "--is-inside-work-tree", "--show-toplevel", "--absolute-git-dir",
        )
        events = []

        def git_for_runtime(requested, *arguments, **kwargs):
            exact_runtime = Path(requested).resolve() == runtime.resolve()
            if exact_runtime and arguments == discovery_arguments:
                completed = subprocess.CompletedProcess(
                    args=["git", *arguments], returncode=0,
                    stdout=b"true\n",
                    stderr=b"DISCOVERY_STAGE_STDERR_MUST_STAY_PRIVATE\n",
                )
            else:
                completed = original_git_command(requested, *arguments, **kwargs)
            if exact_runtime:
                events.append((arguments, completed.returncode))
            return completed

        self.assertTrue(module._has_ancestor_git_metadata(runtime))
        with mock.patch.object(module, "_git_command", side_effect=git_for_runtime):
            with self.assertRaises(module.ContractAuthorityError) as raised:
                module._markerless_behavior_identity(target, runtime)

        self.assertEqual(events, [(common_arguments, 0), (discovery_arguments, 0)])
        self.assertEqual(raised.exception.reason_code, "git_output_invalid")
        self.assertNotIn("DISCOVERY_STAGE_STDERR_MUST_STAY_PRIVATE", str(raised.exception))

    def test_markerless_runtime_git_failure_fails_closed_when_metadata_exists(self) -> None:
        target = self._init_repo("markerless-target")
        self._write(target, "tracked.txt", "target\n")
        self._commit_all(target, "target base")
        ordinary_runtime = self.base / "ordinary-runtime"
        ordinary_runtime.mkdir()
        self.assertEqual(module._markerless_behavior_identity(target, ordinary_runtime), "default")

        broken_runtime = self.base / "broken-runtime"
        (broken_runtime / ".git").mkdir(parents=True)
        with self.assertRaises(module.ContractAuthorityError) as raised:
            module._markerless_behavior_identity(target, broken_runtime)
        self.assertEqual(raised.exception.reason_code, "git_command_failed")

    def test_git_common_directory_rejects_nonzero_ambiguous_and_unavailable_output(self) -> None:
        probe = self.base / "common-directory-probe"
        probe.mkdir()
        missing = self.base / "missing-common-directory"
        cases = (
            ("nonzero", 73, b"", "git_command_failed"),
            ("non_utf8", 0, b"\xff\n", "git_output_invalid"),
            ("multiline", 0, b"/one\n/two\n", "git_output_invalid"),
            ("unavailable", 0, os.fsencode(missing) + b"\n", "root_unavailable"),
        )
        for name, returncode, stdout, expected in cases:
            completed = subprocess.CompletedProcess(
                args=["git"],
                returncode=returncode,
                stdout=stdout,
                stderr=b"",
            )
            with self.subTest(name=name), mock.patch.object(module, "_git_command", return_value=completed):
                with self.assertRaises(module.ContractAuthorityError) as raised:
                    module._git_common_directory(probe, context="test common directory")
            self.assertEqual(raised.exception.reason_code, expected)

    def test_local_v2_git_binding_precedes_malformed_marker_parse(self) -> None:
        root = self._make_complete_local(name="app (1)")
        (root / module._snapshot.MARKER_PATH).write_text("{}\n", encoding="utf-8")
        original_git_command = module._git_command

        def nonzero_common_dir(
            project_root: Path,
            *arguments: str,
            context: str,
        ) -> subprocess.CompletedProcess[bytes]:
            if arguments == ("rev-parse", "--git-common-dir") and context == "local marker physical binding":
                return subprocess.CompletedProcess(args=["git"], returncode=73, stdout=b"", stderr=b"")
            return original_git_command(project_root, *arguments, context=context)

        with mock.patch.object(module, "_git_command", side_effect=nonzero_common_dir):
            with self.assertRaises(module.ContractAuthorityError) as raised:
                self._capture_engaged(root)
        self.assertEqual(raised.exception.reason_code, "git_command_failed")

    def test_local_v2_marker_semantics_reject_empty_default_and_invalid_identity(self) -> None:
        root = self._make_complete_local(name="app (1)")
        marker_path = root / module._snapshot.MARKER_PATH
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        cases = (
            ("missing_schema", {}, "unsupported_live_marker_schema"),
            ("empty", {**marker, "repository_id": ""}, "invalid_text"),
            ("default", {**marker, "repository_id": "default"}, "unknown_behavior_identity"),
            ("invalid", {**marker, "repository_id": "semantic id"}, "repository_identity_invalid"),
        )
        for name, value, expected in cases:
            with self.subTest(name=name):
                marker_path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
                with self.assertRaises(module.ContractAuthorityError) as raised:
                    self._capture_engaged(root)
                self.assertEqual(raised.exception.reason_code, expected)

    def test_local_v2_reads_current_allowed_content_and_ignores_unrelated_head_change(self) -> None:
        root = self._make_complete_local()
        context = self._capture_engaged(root)
        self.assertEqual(context.state, "engaged")
        self.assertEqual(context.project_root, root.resolve())
        self.assertEqual(context.contract_root, root.resolve())
        self.assertEqual(context.behavior_identity, "planveyor")
        self.assertEqual(context.runtime_pin, self.pin)
        self.assertEqual(context.declared_rows, ())

        admission, execution_root, first_observation, verify_pin = self._engaged_patches()
        with admission, execution_root, first_observation, verify_pin, mock.patch.dict(os.environ, {}, clear=True):
            text = module.read_declared_text(context, "docs/tools/prompts/architect_init.md", "test prompt")
            self.assertEqual(text, "target body: docs/tools/prompts/architect_init.md\n")

        self._write(root, "unrelated.txt", "after\n")
        self._commit_paths(root, "unrelated target mutation", "unrelated.txt")
        self._assert_local_marker_untracked(root)
        with admission, execution_root, first_observation, verify_pin, mock.patch.dict(os.environ, {}, clear=True):
            module.validate_before_effect(context)

        self._write(root, "docs/tools/prompts/architect_init.md", "mutated\n")
        with admission, execution_root, first_observation, verify_pin, mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                module.read_declared_text(context, "docs/tools/prompts/architect_init.md", "test prompt"),
                "mutated\n",
            )
            module.validate_before_effect(context)

    def test_local_v2_reads_dirty_content_without_generation_drift(self) -> None:
        root = self._make_complete_local()
        context = self._capture_engaged(root)
        before = module.context_to_json(context)
        self._write(root, "docs/tools/prompts/architect_init.md", "edited local body\n")
        admission, execution_root, first_observation, verify_pin = self._engaged_patches()
        with admission, execution_root, first_observation, verify_pin, mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                module.read_declared_text(context, "docs/tools/prompts/architect_init.md", "prompt"),
                "edited local body\n",
            )
            module.validate_before_effect(context)
        self.assertEqual(module.context_to_json(context), before)

    def test_local_v2_selector_disappearance_never_falls_back_to_legacy(self) -> None:
        root = self._make_complete_local()
        runtime_root = self._init_repo("runtime-source")
        self._write(runtime_root, "tracked.txt", "runtime\n")
        self._commit_all(runtime_root, "runtime base")
        runtime_pin = replace(
            self.pin,
            runtime_root=runtime_root,
            git_dir=runtime_root / ".git",
        )
        admission = mock.patch.object(module, "ENGAGED_ADMISSION_COMPLETE", True)
        execution_root = mock.patch.object(module, "_executing_runtime_root", return_value=runtime_root)
        first_observation = mock.patch.object(
            module._runtime,
            "_first_loaded_runtime_observation",
            return_value=runtime._FirstLoadedRuntimeObservation(runtime_root, runtime_pin),
        )
        verify_pin = mock.patch.object(module._runtime, "verify_loaded_runtime_pin", return_value=runtime_pin)
        with admission, execution_root, first_observation, verify_pin, mock.patch.dict(os.environ, {}, clear=True):
            context = module.resolve_top_level_context(root, runtime_root=runtime_root, loaded_pin=runtime_pin)
        (root / module._snapshot.MARKER_PATH).unlink()
        with admission, execution_root, first_observation, verify_pin, mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(module.ContractAuthorityError) as raised:
                module.validate_before_effect(context)
        self.assertEqual(raised.exception.reason_code, "authority_generation_mismatch")

    def test_local_v2_selector_semantic_change_changes_generation(self) -> None:
        root = self._make_complete_local()
        context = self._capture_engaged(root)
        selector_path = root / module._snapshot.MARKER_PATH
        selector = json.loads(selector_path.read_text(encoding="utf-8"))
        selector_path.write_text(json.dumps(selector, indent=2, sort_keys=False) + "\n", encoding="utf-8")
        admission, execution_root, first_observation, verify_pin = self._engaged_patches()
        with admission, execution_root, first_observation, verify_pin, mock.patch.dict(os.environ, {}, clear=True):
            module.validate_before_effect(context)

        selector["required_runtime_api"] = {"minimum": 4, "maximum": 5}
        selector_path.write_text(json.dumps(selector, sort_keys=True) + "\n", encoding="utf-8")
        api_changed = self._capture_engaged(root)
        self.assertEqual(api_changed.behavior_identity, "planveyor")
        self.assertNotEqual(api_changed.generation_sha256, context.generation_sha256)
        api_changed_envelope = module.context_to_json(api_changed)
        with admission, execution_root, first_observation, verify_pin, mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(module.ContractAuthorityError) as raised:
                module.validate_before_effect(context)
        self.assertEqual(raised.exception.reason_code, "authority_generation_mismatch")

        selector["repository_id"] = "planveyor-next"
        selector_path.write_text(json.dumps(selector, sort_keys=True) + "\n", encoding="utf-8")
        with admission, execution_root, first_observation, verify_pin, mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(module.ContractAuthorityError) as inherited:
                module.validate_inherited_context(
                    api_changed_envelope,
                    root,
                    runtime_root=self.runtime_root,
                    loaded_pin=self.pin,
                )
        self.assertEqual(inherited.exception.reason_code, "context_expectation_mismatch")

        changed = self._capture_engaged(root)
        self.assertEqual(changed.behavior_identity, "planveyor-next")
        self.assertNotEqual(changed.generation_sha256, api_changed.generation_sha256)
        self.assertEqual(
            module.parse_context_envelope(module.context_to_json(changed))["behavior_identity"],
            "planveyor-next",
        )
        with admission, execution_root, first_observation, verify_pin, mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(module.ContractAuthorityError) as raised:
                module.validate_before_effect(api_changed)
        self.assertEqual(raised.exception.reason_code, "authority_generation_mismatch")

    def test_local_v2_reads_new_allowed_content_and_rejects_family_escapes(self) -> None:
        self.assertTrue(module._local_content_path_allowed("docs/tools/prompts/zcode/manager_pipeline.md"))
        root = self._make_complete_local()
        context = self._capture_engaged(root)
        self._write(root, "docs/tools/prompts/new_local_prompt.md", "new body\n")
        admission, execution_root, first_observation, verify_pin = self._engaged_patches()
        with admission, execution_root, first_observation, verify_pin, mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                module.read_declared_text(context, "docs/tools/prompts/new_local_prompt.md", "new prompt"),
                "new body\n",
            )
            for relative in (
                "docs/tools/prompts/profiles/planveyor/architect_init.md",
                "docs/plans/arbitrary.md",
            ):
                with self.subTest(relative=relative), self.assertRaises(module.ContractAuthorityError) as raised:
                    module.require_declared_read(context, relative, "boundary")
                self.assertEqual(raised.exception.reason_code, "undeclared_contract_read")
            with self.assertRaises(module.ContractAuthorityError) as traversal:
                module.require_declared_read(context, "../AGENTS.md", "boundary")
            self.assertEqual(traversal.exception.reason_code, "invalid_relative_path")

    def test_missing_v2_marker_parent_chain_is_legacy_and_allowed_missing_parent_is_read_missing(self) -> None:
        root = self._init_repo("marker-parent-absent")
        self._write(root, "tracked.txt", "tracked\n")
        self._commit_all(root, "base")
        legacy = module.resolve_top_level_context(root, loaded_pin="unattested_legacy")
        self.assertEqual(legacy.state, "legacy")

        local_root = self._make_complete_local(name=Path("local-missing-parent") / "planveyor")
        context = self._capture_engaged(local_root)
        (local_root / "docs/adr/_template.md").unlink()
        (local_root / "docs/adr").rmdir()
        admission, execution_root, first_observation, verify_pin = self._engaged_patches()
        with admission, execution_root, first_observation, verify_pin, mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(module.ContractAuthorityError) as missing:
                module.require_declared_read(context, "docs/adr/_template.md", "missing template")
        self.assertEqual(missing.exception.reason_code, "declared_read_missing")

    def test_subdirectory_contract_root_maps_local_paths_before_declared_reads(self) -> None:
        root = self._make_complete_local(contract_root="contract")
        context = self._capture_engaged(root)
        self.assertEqual(context.contract_root, (root / "contract").resolve())
        self.assertEqual(context.declared_rows, ())
        admission, execution_root, first_observation, verify_pin = self._engaged_patches()
        with admission, execution_root, first_observation, verify_pin, mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                module.read_declared_text(context, "docs/tools/prompts/architect_init.md", "subdirectory prompt"),
                "target body: docs/tools/prompts/architect_init.md\n",
            )
            with self.assertRaises(module.ContractAuthorityError) as raised:
                module.require_declared_read(context, "contract/docs/tools/prompts/architect_init.md")
            self.assertEqual(raised.exception.reason_code, "undeclared_contract_read")
        parsed = module.parse_context_envelope(module.context_to_json(context))
        self.assertEqual(parsed["project_root"], str(root.resolve()))
        self.assertNotIn("declared_rows", parsed)

    def test_local_read_apis_preserve_current_content_for_all_root_depths(self) -> None:
        logical = "docs/tools/prompts/architect_init.md"
        new_logical = "docs/tools/prompts/new_local_prompt.md"
        for index, contract_root in enumerate((".", "contract", "contract/nested")):
            with self.subTest(contract_root=contract_root):
                root = self._make_complete_local(
                    contract_root=contract_root, name=Path(f"root-depth-{index}") / "planveyor",
                )
                context = self._capture_engaged(root)
                self._write(context.contract_root, logical, "dirty current body\n")
                self._write(context.contract_root, new_logical, "new current body\n")
                admission, execution_root, first_observation, verify_pin = self._engaged_patches()
                with admission, execution_root, first_observation, verify_pin, mock.patch.dict(os.environ, {}, clear=True):
                    for path, body in ((logical, "dirty current body\n"), (new_logical, "new current body\n")):
                        self.assertEqual(module.read_declared_bytes(context, path), body.encode("utf-8"))
                        self.assertEqual(module.read_declared_text(context, path), body)
                        self.assertEqual(module.require_declared_read(context, path), context.contract_root / path)
                    module.validate_before_effect(context)
                self._assert_local_marker_untracked(root)

    def test_nested_contract_parent_swap_is_rejected_by_all_read_apis(self) -> None:
        logical = "docs/tools/prompts/architect_init.md"
        for reader_name in ("read_declared_bytes", "read_declared_text", "require_declared_read"):
            with self.subTest(reader=reader_name):
                root = self._make_complete_local(
                    contract_root="contract/nested", name=Path(reader_name) / "planveyor",
                )
                context = self._capture_engaged(root)
                outside = self.base / f"outside-{reader_name}"
                self._write(outside, f"nested/{logical}", "OUTSIDE_CONTRACT_SENTINEL\n")
                original_snapshot = module.snapshot_regular_or_absent
                swapped = []

                def snapshot_after_swap(trusted_root, relative_path, **kwargs):
                    old_anchor = trusted_root == context.contract_root and relative_path == logical
                    project_anchor = (
                        trusted_root == context.project_root
                        and relative_path == f"contract/nested/{logical}"
                    )
                    if (old_anchor or project_anchor) and not swapped:
                        (root / "contract").rename(root / "contract-before-swap")
                        (root / "contract").symlink_to(outside, target_is_directory=True)
                        swapped.append(True)
                    return original_snapshot(trusted_root, relative_path, **kwargs)

                admission, execution_root, first_observation, verify_pin = self._engaged_patches()
                with admission, execution_root, first_observation, verify_pin, mock.patch.dict(
                    os.environ, {}, clear=True,
                ), mock.patch.object(module, "snapshot_regular_or_absent", side_effect=snapshot_after_swap):
                    with self.assertRaises(module.ContractAuthorityError) as raised:
                        getattr(module, reader_name)(context, logical)
                self.assertEqual(swapped, [True], "the parent swap must reach the real descriptor snapshot")
                self.assertTrue((root / "contract").is_symlink())
                self.assertEqual(raised.exception.reason_code, "symlink_forbidden")

    def test_expected_envelope_preserves_entry_observation_through_unrelated_evolution(self) -> None:
        root = self._make_complete_local()
        context = self._capture_engaged(root)
        envelope = module.context_to_json(context)
        parsed = module.parse_context_envelope(envelope)
        self.assertEqual(parsed["state"], "engaged")
        self.assertEqual(
            parsed["entry_observation_provenance"],
            module.ENTRY_OBSERVATION_PROVENANCE_OBSERVED_LOCAL,
        )
        self.assertNotIn("declared_rows", envelope)
        self.assertEqual(parsed["project_root"], str(root.resolve()))

        self._write(root, "unrelated.txt", "staged unrelated change is allowed\n")
        self._git(root, "add", "unrelated.txt")
        admission, execution_root, first_observation, verify_pin = self._engaged_patches()
        with admission, execution_root, first_observation, verify_pin, mock.patch.dict(os.environ, {}, clear=True):
            staged = module.validate_inherited_context(
                envelope,
                root,
                runtime_root=self.runtime_root,
                loaded_pin=self.pin,
            )
        self.assertEqual(staged.entry_observation, context.entry_observation)
        self.assertEqual(
            staged.entry_observation_provenance,
            module.ENTRY_OBSERVATION_PROVENANCE_INHERITED_SUPPLIED_UNVERIFIED,
        )
        staged_envelope = module.context_to_json(staged)
        staged_parsed = module.parse_context_envelope(staged_envelope)
        self.assertEqual(staged_parsed["entry_observation"], parsed["entry_observation"])
        self.assertEqual(
            staged_parsed["entry_observation_provenance"],
            module.ENTRY_OBSERVATION_PROVENANCE_INHERITED_SUPPLIED_UNVERIFIED,
        )

        self._write(root, "unrelated.txt", "different head is allowed\n")
        self._commit_paths(root, "unrelated head change", "unrelated.txt")
        self._assert_local_marker_untracked(root)
        with admission, execution_root, first_observation, verify_pin, mock.patch.dict(os.environ, {}, clear=True):
            inherited = module.validate_inherited_context(
                envelope,
                root,
                runtime_root=self.runtime_root,
                loaded_pin=self.pin,
            )
        self.assertEqual(inherited.generation_sha256, context.generation_sha256)
        self.assertEqual(inherited.entry_observation, context.entry_observation)
        self.assertEqual(
            inherited.entry_observation_provenance,
            module.ENTRY_OBSERVATION_PROVENANCE_INHERITED_SUPPLIED_UNVERIFIED,
        )
        inherited_envelope = module.context_to_json(inherited)
        with admission, execution_root, first_observation, verify_pin, mock.patch.dict(os.environ, {}, clear=True):
            repeated = module.validate_inherited_context(
                inherited_envelope,
                root,
                runtime_root=self.runtime_root,
                loaded_pin=self.pin,
            )
        self.assertEqual(module.context_to_json(repeated), inherited_envelope)

        with admission, execution_root, first_observation, verify_pin, mock.patch.dict(os.environ, {}, clear=True):
            fresh = module.resolve_top_level_context(
                root,
                runtime_root=self.runtime_root,
                loaded_pin=self.pin,
            )
        self.assertNotEqual(fresh.entry_observation, context.entry_observation)

    def test_default_expected_environment_is_only_a_generation_assertion(self) -> None:
        root = self._make_complete_local()
        context = self._capture_engaged(root)
        envelope = module.context_to_json(context)
        self._write(root, "unrelated.txt", "environment expectation must not select the entry head\n")
        self._commit_paths(root, "unrelated head change", "unrelated.txt")
        self._assert_local_marker_untracked(root)
        admission, execution_root, first_observation, verify_pin = self._engaged_patches()
        with admission, execution_root, first_observation, verify_pin, mock.patch.dict(
            os.environ, {module.EXPECTED_CONTEXT_ENV: envelope}, clear=True
        ):
            inherited = module.resolve_top_level_context(
                root,
                runtime_root=self.runtime_root,
                loaded_pin=self.pin,
            )
        self.assertEqual(inherited.generation_sha256, context.generation_sha256)
        self.assertEqual(inherited.entry_observation, context.entry_observation)
        self.assertEqual(
            inherited.entry_observation_provenance,
            module.ENTRY_OBSERVATION_PROVENANCE_INHERITED_SUPPLIED_UNVERIFIED,
        )

    def test_historical_v1_and_v2_envelopes_are_passive_but_not_active_contexts(self) -> None:
        root = self._make_complete_local()
        current = json.loads(module.context_to_json(self._capture_engaged(root)))
        historical_payloads: list[dict[str, object]] = []

        v1 = dict(current)
        v1["schema_version"] = module._snapshot.LEGACY_CONTEXT_SCHEMA_VERSION
        del v1["entry_observation_provenance"]
        historical_payloads.append(v1)

        v2 = dict(current)
        v2["schema_version"] = module._snapshot.HISTORICAL_CONTEXT_SCHEMA_VERSION
        historical_payloads.append(v2)

        for payload in historical_payloads:
            with self.subTest(schema=payload["schema_version"]):
                historical = _reseal_context_envelope(payload)
                self.assertEqual(module.parse_context_envelope(historical)["schema_version"], payload["schema_version"])
                with self.assertRaises(module.ContractAuthorityError) as via_expected:
                    module.resolve_top_level_context(
                        root,
                        runtime_root=self.runtime_root,
                        loaded_pin=self.pin,
                        expected=historical,
                    )
                self.assertEqual(via_expected.exception.reason_code, "context_active_schema_unsupported")
                with self.assertRaises(module.ContractAuthorityError) as via_validate:
                    module.validate_inherited_context(
                        historical,
                        root,
                        runtime_root=self.runtime_root,
                        loaded_pin=self.pin,
                    )
                self.assertEqual(via_validate.exception.reason_code, "context_active_schema_unsupported")

    def test_resealed_inherited_entry_claims_are_downgraded_and_boundary_drift_rejects(self) -> None:
        root = self._make_complete_local()
        context = self._capture_engaged(root)
        forged = json.loads(module.context_to_json(context))
        entry = forged["entry_observation"]
        self.assertIsInstance(entry, dict)
        entry.update(
            {
                "head": "d" * 40,
                "tree": "e" * 40,
                "index_sha256": "f" * 64,
            }
        )
        forged["entry_observation_provenance"] = module.ENTRY_OBSERVATION_PROVENANCE_OBSERVED_LOCAL
        forged_envelope = _reseal_context_envelope(forged)
        self.assertEqual(
            module.parse_context_envelope(forged_envelope)["entry_observation_provenance"],
            module.ENTRY_OBSERVATION_PROVENANCE_OBSERVED_LOCAL,
        )

        admission, execution_root, first_observation, verify_pin = self._engaged_patches()
        with admission, execution_root, first_observation, verify_pin, mock.patch.dict(os.environ, {}, clear=True):
            inherited = module.validate_inherited_context(
                forged_envelope,
                root,
                runtime_root=self.runtime_root,
                loaded_pin=self.pin,
            )
        self.assertEqual(inherited.entry_observation.head, "d" * 40)
        self.assertEqual(inherited.entry_observation.tree, "e" * 40)
        self.assertEqual(inherited.entry_observation.index_sha256, "f" * 64)
        self.assertEqual(
            inherited.entry_observation_provenance,
            module.ENTRY_OBSERVATION_PROVENANCE_INHERITED_SUPPLIED_UNVERIFIED,
        )
        inherited_envelope = module.context_to_json(inherited)
        inherited_payload = module.parse_context_envelope(inherited_envelope)
        self.assertEqual(inherited_payload["entry_observation"], forged["entry_observation"])
        self.assertEqual(
            inherited_payload["entry_observation_provenance"],
            module.ENTRY_OBSERVATION_PROVENANCE_INHERITED_SUPPLIED_UNVERIFIED,
        )

        foreign_root = self._make_complete_local(name=Path("foreign-root") / "planveyor")
        with admission, execution_root, first_observation, verify_pin, mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(module.ContractAuthorityError) as cross_root:
                module.validate_inherited_context(
                    forged_envelope,
                    foreign_root,
                    runtime_root=self.runtime_root,
                    loaded_pin=self.pin,
                )
        self.assertEqual(cross_root.exception.reason_code, "context_expectation_mismatch")

        generation_drift = json.loads(forged_envelope)
        generation_drift["generation_sha256"] = "0" * 64
        generation_drift_envelope = _reseal_context_envelope(generation_drift)
        with admission, execution_root, first_observation, verify_pin, mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(module.ContractAuthorityError) as generation:
                module.validate_inherited_context(
                    generation_drift_envelope,
                    root,
                    runtime_root=self.runtime_root,
                    loaded_pin=self.pin,
                )
        self.assertEqual(generation.exception.reason_code, "context_expectation_mismatch")

    def test_passive_envelope_validation_detects_tampering_without_filesystem_access(self) -> None:
        root = self._make_complete_local()
        context = self._capture_engaged(root)
        envelope = module.context_to_json(context)
        with mock.patch.object(module, "snapshot_regular_or_absent", side_effect=AssertionError), mock.patch.object(
            module._runtime, "capture_tracked_content", side_effect=AssertionError
        ):
            self.assertEqual(module.parse_context_envelope(envelope)["project_root"], str(root.resolve()))
        tampered = json.loads(envelope)
        tampered["generation_sha256"] = "f" * 64
        with self.assertRaises(module.ContractAuthorityError) as raised:
            module.parse_context_envelope(json.dumps(tampered))
        self.assertEqual(raised.exception.reason_code, "context_envelope_digest_mismatch")

        semantically_invalid = json.loads(module.context_to_json(context))
        semantically_invalid["behavior_identity"] = "default"
        body = {key: value for key, value in semantically_invalid.items() if key != "context_sha256"}
        semantically_invalid["context_sha256"] = module._sha256_json(body)
        with self.assertRaises(module.ContractAuthorityError) as raised:
            module.parse_context_envelope(json.dumps(semantically_invalid))
        self.assertEqual(raised.exception.reason_code, "context_envelope_schema_invalid")

        missing_provenance = json.loads(module.context_to_json(context))
        del missing_provenance["entry_observation_provenance"]
        _reseal_context_envelope(missing_provenance)
        with self.assertRaises(module.ContractAuthorityError) as raised:
            module.parse_context_envelope(json.dumps(missing_provenance))
        self.assertEqual(raised.exception.reason_code, "context_envelope_schema_invalid")

        invalid_provenance = json.loads(module.context_to_json(context))
        invalid_provenance["entry_observation_provenance"] = "trusted_by_digest"
        _reseal_context_envelope(invalid_provenance)
        with self.assertRaises(module.ContractAuthorityError) as raised:
            module.parse_context_envelope(json.dumps(invalid_provenance))
        self.assertEqual(raised.exception.reason_code, "context_envelope_schema_invalid")

    def test_physical_marker_and_non_git_marker_fail_closed(self) -> None:
        root = self._init_repo()
        self._write(root, "tracked.txt", "tracked\n")
        self._commit_all(root, "base")
        self._write(root, module._snapshot.MARKER_PATH, "{}\n")
        self._git(root, "add", module._snapshot.MARKER_PATH)
        with self.assertRaises(module.ContractAuthorityError) as raised:
            module.resolve_top_level_context(root, loaded_pin="unattested_legacy")
        self.assertEqual(raised.exception.reason_code, "unsupported_live_marker_schema")

        non_git = self.base / "not-a-repository"
        non_git.mkdir()
        original_git_command = module._git_command
        original_metadata = module._has_ancestor_git_metadata

        def git_for_non_git(requested, *arguments, **kwargs):
            if Path(requested).resolve() == non_git.resolve():
                return subprocess.CompletedProcess(
                    args=["git", *arguments], returncode=128, stdout=b"",
                    stderr=b"fatal: not a git repository\n",
                )
            return original_git_command(requested, *arguments, **kwargs)

        def metadata_for_non_git(requested):
            if Path(requested).resolve() == non_git.resolve():
                return False
            return original_metadata(requested)

        with (
            mock.patch.object(module, "_git_command", side_effect=git_for_non_git),
            mock.patch.object(module, "_has_ancestor_git_metadata", side_effect=metadata_for_non_git),
        ):
            legacy = module.resolve_top_level_context(non_git, loaded_pin="unattested_legacy")
            self.assertEqual(legacy.state, "legacy")
            self._write(non_git, module._snapshot.MARKER_PATH, "{}\n")
            with self.assertRaises(module.ContractAuthorityError) as raised:
                module.resolve_top_level_context(non_git, loaded_pin="unattested_legacy")
            self.assertEqual(raised.exception.reason_code, "marker_in_non_git")

        broken_git = self.base / "broken-git"
        broken_git.mkdir()
        (broken_git / ".git").mkdir()
        def git_for_broken_git(requested, *arguments, **kwargs):
            if Path(requested).resolve() == broken_git.resolve():
                return subprocess.CompletedProcess(
                    args=["git", *arguments], returncode=128, stdout=b"",
                    stderr=b"fatal: not a git repository\n",
                )
            return original_git_command(requested, *arguments, **kwargs)

        with mock.patch.object(module, "_git_command", side_effect=git_for_broken_git):
            with self.assertRaises(module.ContractAuthorityError) as raised:
                module.resolve_top_level_context(broken_git, loaded_pin="unattested_legacy")
        self.assertEqual(raised.exception.reason_code, "git_discovery_failed")

    def test_physical_marker_and_non_git_marker_fail_closed_real_non_git(self) -> None:
        if inside_git_work_tree(self.base):
            self.skipTest(NON_GIT_ROOT_SKIP_REASON)
        root = self._init_repo()
        self._write(root, "tracked.txt", "tracked\n")
        self._commit_all(root, "base")
        self._write(root, module._snapshot.MARKER_PATH, "{}\n")
        self._git(root, "add", module._snapshot.MARKER_PATH)
        with self.assertRaises(module.ContractAuthorityError) as raised:
            module.resolve_top_level_context(root, loaded_pin="unattested_legacy")
        self.assertEqual(raised.exception.reason_code, "unsupported_live_marker_schema")

        non_git = self.base / "not-a-repository"
        non_git.mkdir()
        legacy = module.resolve_top_level_context(non_git, loaded_pin="unattested_legacy")
        self.assertEqual(legacy.state, "legacy")
        self._write(non_git, module._snapshot.MARKER_PATH, "{}\n")
        with self.assertRaises(module.ContractAuthorityError) as raised:
            module.resolve_top_level_context(non_git, loaded_pin="unattested_legacy")
        self.assertEqual(raised.exception.reason_code, "marker_in_non_git")

        broken_git = self.base / "broken-git"
        broken_git.mkdir()
        (broken_git / ".git").mkdir()
        with self.assertRaises(module.ContractAuthorityError) as raised:
            module.resolve_top_level_context(broken_git, loaded_pin="unattested_legacy")
        self.assertEqual(raised.exception.reason_code, "git_discovery_failed")

    def test_fake_git_discovery_failure_with_metadata_has_safe_cause(self) -> None:
        fake = subprocess.CompletedProcess(
            args=["git"],
            returncode=73,
            stdout=b"",
            stderr=b"DO_NOT_LEAK_TEST_GIT_STDERR_SECRET\nfatal: fixture failure\n",
        )
        local_metadata = self.base / "fake-git-local"
        (local_metadata / ".git").mkdir(parents=True)
        ancestor_metadata = self.base / "fake-git-ancestor"
        nested = ancestor_metadata / "nested"
        nested.mkdir(parents=True)
        (ancestor_metadata / ".git").mkdir()
        plain = self.base / "fake-git-plain"
        plain.mkdir()

        original_metadata = module._has_ancestor_git_metadata

        def metadata_for_plain(requested):
            if Path(requested).resolve() == plain.resolve():
                return False
            return original_metadata(requested)

        with mock.patch.object(module, "_git_command", return_value=fake):
            for requested in (local_metadata, nested):
                with self.subTest(requested=requested), self.assertRaises(module.ContractAuthorityError) as raised:
                    module._discover_project_root(requested, explicit=True)
                self.assertEqual(raised.exception.reason_code, "git_discovery_failed")
                self.assertEqual(
                    str(raised.exception),
                    "Git failed while discovering project root (exit status 73)",
                )
                self.assertNotIn("DO_NOT_LEAK_TEST_GIT_STDERR_SECRET", str(raised.exception))
                self.assertNotIn("fatal: fixture failure", str(raised.exception))

            with mock.patch.object(module, "_has_ancestor_git_metadata", side_effect=metadata_for_plain):
                discovered, is_git = module._discover_project_root(plain, explicit=True)

        self.assertEqual(discovered, plain.resolve())
        self.assertFalse(is_git)

    def test_fake_git_discovery_failure_with_metadata_has_safe_cause_real_non_git(self) -> None:
        if inside_git_work_tree(self.base):
            self.skipTest(NON_GIT_ROOT_SKIP_REASON)
        fake = subprocess.CompletedProcess(
            args=["git"],
            returncode=73,
            stdout=b"",
            stderr=b"DO_NOT_LEAK_TEST_GIT_STDERR_SECRET\nfatal: fixture failure\n",
        )
        local_metadata = self.base / "fake-git-local"
        (local_metadata / ".git").mkdir(parents=True)
        ancestor_metadata = self.base / "fake-git-ancestor"
        nested = ancestor_metadata / "nested"
        nested.mkdir(parents=True)
        (ancestor_metadata / ".git").mkdir()
        plain = self.base / "fake-git-plain"
        plain.mkdir()

        with mock.patch.object(module, "_git_command", return_value=fake):
            for requested in (local_metadata, nested):
                with self.subTest(requested=requested), self.assertRaises(module.ContractAuthorityError) as raised:
                    module._discover_project_root(requested, explicit=True)
                self.assertEqual(raised.exception.reason_code, "git_discovery_failed")
                self.assertEqual(
                    str(raised.exception),
                    "Git failed while discovering project root (exit status 73)",
                )
                self.assertNotIn("DO_NOT_LEAK_TEST_GIT_STDERR_SECRET", str(raised.exception))
                self.assertNotIn("fatal: fixture failure", str(raised.exception))

            discovered, is_git = module._discover_project_root(plain, explicit=True)

        self.assertEqual(discovered, plain.resolve())
        self.assertFalse(is_git)

    def test_legacy_entry_matches_prior_snapshot_basis_without_snapshot_capture(self) -> None:
        root = self._init_repo("legacy-equivalence")
        self._write(root, "tracked.txt", "tracked\n")
        self._commit_all(root, "base")
        prior = module._snapshot._recheck_git_basis(
            module._snapshot._capture_git_basis(root, context="target"),
            context="target legacy post-read",
        )
        expected = module.EntryObservation(
            root=prior.root,
            git_dir=prior.git_dir,
            head=prior.head,
            tree=prior.tree,
            index_sha256=prior.index_sha256,
        )

        with mock.patch.object(
            module._snapshot, "_capture_git_basis", side_effect=AssertionError("legacy entry must use runtime basis")
        ), mock.patch.object(
            module._snapshot, "_recheck_git_basis", side_effect=AssertionError("legacy entry must use runtime recheck")
        ):
            self.assertEqual(module._capture_legacy_entry(root), expected)

    def test_legacy_entry_rejects_raw_index_or_head_drift_between_runtime_observations(self) -> None:
        for drift in ("raw-index", "head"):
            with self.subTest(drift=drift):
                root = self._init_repo(f"legacy-{drift}")
                self._write(root, "tracked.txt", "before\n")
                self._commit_all(root, "base")
                index = root / ".git" / "index"
                original_index = index.read_bytes()
                original_capture = runtime._capture_git_basis
                calls = 0

                def capture_then_mutate(candidate: Path):
                    nonlocal calls
                    basis = original_capture(candidate)
                    if calls == 0:
                        if drift == "raw-index":
                            index.write_bytes(original_index + b"\0")
                        else:
                            self._write(root, "tracked.txt", "after\n")
                            self._commit_all(root, "head drift")
                    calls += 1
                    return basis

                try:
                    with mock.patch.object(runtime, "_capture_git_basis", side_effect=capture_then_mutate):
                        with self.assertRaises(module.ContractAuthorityError) as raised:
                            module._capture_legacy_entry(root)
                finally:
                    if drift == "raw-index":
                        index.write_bytes(original_index)
                self.assertEqual(raised.exception.reason_code, "snapshot_changed_during_read")
                self.assertEqual(calls, 2)

    def test_legacy_entry_rejects_missing_or_symlinked_index(self) -> None:
        root = self._init_repo("legacy-index")
        self._write(root, "tracked.txt", "tracked\n")
        self._commit_all(root, "base")
        index = root / ".git" / "index"
        retained_index = index.with_name("index-retained")
        index.rename(retained_index)

        with self.assertRaises(module.ContractAuthorityError) as raised:
            module._capture_legacy_entry(root)
        self.assertEqual(raised.exception.reason_code, "index_missing")

        index.symlink_to(retained_index.name)
        with self.assertRaises(module.ContractAuthorityError) as raised:
            module._capture_legacy_entry(root)
        self.assertEqual(raised.exception.reason_code, "symlink_forbidden")

    def test_legacy_entry_reports_runtime_git_timeout(self) -> None:
        root = self._init_repo("legacy-timeout")
        self._write(root, "tracked.txt", "tracked\n")
        self._commit_all(root, "base")
        timeout = subprocess.TimeoutExpired(["git"], runtime.GIT_COMMAND_TIMEOUT_SECONDS)

        with mock.patch.object(runtime.subprocess, "run", side_effect=timeout):
            with self.assertRaises(module.ContractAuthorityError) as raised:
                module._capture_legacy_entry(root)
        self.assertEqual(raised.exception.reason_code, "git_timeout")

    def test_runtime_environment_split_brain_blocks_engagement(self) -> None:
        root = self._make_complete_local()
        foreign = self.base / "foreign-runtime"
        foreign.mkdir()
        admission, execution_root, first_observation, verify_pin = self._engaged_patches()
        with admission, execution_root, first_observation, verify_pin, mock.patch.dict(
            os.environ, {"PLANVEYOR_ROOT": str(foreign)}, clear=True
        ):
            with self.assertRaises(module.ContractAuthorityError) as raised:
                module.resolve_top_level_context(root, runtime_root=self.runtime_root, loaded_pin=self.pin)
        self.assertEqual(raised.exception.reason_code, "runtime_environment_split_brain")

    def test_legacy_allows_only_initial_unattested_runtime_capture(self) -> None:
        root = self._init_repo()
        self._write(root, "tracked.txt", "tracked\n")
        self._commit_all(root, "base")
        external_runtime = self.base / "external-runtime"
        external_runtime.mkdir()
        external_pin = replace(
            self.pin,
            runtime_root=external_runtime,
            git_dir=external_runtime / ".git",
        )
        execution_root = mock.patch.object(module, "_executing_runtime_root", return_value=external_runtime)
        unattested = runtime._FirstLoadedRuntimeObservation(
            runtime_root=external_runtime,
            pin=None,
        )
        with execution_root, mock.patch.object(
            module._runtime, "_first_loaded_runtime_observation", return_value=unattested
        ), mock.patch.dict(os.environ, {}, clear=True):
            legacy = module.resolve_top_level_context(root, runtime_root=external_runtime)
        self.assertEqual(legacy.state, "legacy")
        self.assertIsNone(legacy.runtime_pin)

        pinned = runtime._FirstLoadedRuntimeObservation(
            runtime_root=external_runtime,
            pin=external_pin,
        )
        with execution_root, mock.patch.object(
            module._runtime, "_first_loaded_runtime_observation", return_value=pinned
        ), mock.patch.object(module._runtime, "verify_loaded_runtime_pin", return_value=external_pin), mock.patch.dict(
            os.environ, {}, clear=True
        ):
            requested_legacy = module.resolve_top_level_context(
                root,
                runtime_root=external_runtime,
                loaded_pin="unattested_legacy",
            )
        self.assertEqual(requested_legacy.state, "legacy")
        self.assertIsNone(requested_legacy.runtime_pin)

        drift = module.ContractAuthorityError("runtime_pin_drift", "runtime pin changed")
        with execution_root, mock.patch.object(
            module._runtime, "_first_loaded_runtime_observation", return_value=pinned
        ), mock.patch.object(module._runtime, "verify_loaded_runtime_pin", side_effect=drift
        ), mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(module.ContractAuthorityError) as raised:
                module.resolve_top_level_context(root, runtime_root=external_runtime, loaded_pin=external_pin)
        self.assertEqual(raised.exception.reason_code, "runtime_loaded_code_drift")

        with execution_root, mock.patch.object(
            module._runtime, "_first_loaded_runtime_observation", return_value=unattested
        ), mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(module.ContractAuthorityError) as raised:
                module.resolve_top_level_context(root, runtime_root=external_runtime, loaded_pin=external_pin)
        self.assertEqual(raised.exception.reason_code, "runtime_loaded_code_drift")

    def test_direct_and_package_authority_imports_share_identity(self) -> None:
        repo_root = SCRIPT_DIR.parent
        probe = textwrap.dedent(
            """
            import sys
            from pathlib import Path

            root = Path(sys.argv[1]).resolve()
            scripts = root / "scripts"
            order = sys.argv[2]
            if order == "direct":
                sys.path.insert(0, str(scripts))
                import contract_authority_runtime as direct_runtime
                import contract_authority_snapshot as direct_snapshot
                import contract_authority_context as direct_context
                sys.path.insert(0, str(root))
                from scripts import contract_authority_runtime as package_runtime
                from scripts import contract_authority_snapshot as package_snapshot
                from scripts import contract_authority_context as package_context
            else:
                sys.path.insert(0, str(root))
                from scripts import contract_authority_runtime as package_runtime
                from scripts import contract_authority_snapshot as package_snapshot
                from scripts import contract_authority_context as package_context
                sys.path.insert(0, str(scripts))
                import contract_authority_runtime as direct_runtime
                import contract_authority_snapshot as direct_snapshot
                import contract_authority_context as direct_context

            assert direct_runtime is package_runtime
            assert direct_snapshot is package_snapshot
            assert direct_context is package_context
            assert direct_context.ContractAuthorityError is package_context.ContractAuthorityError
            pin = direct_runtime.LoadedRuntimePin(
                runtime_root=root,
                git_dir=root / ".git",
                runtime_api_version=1,
                commit="1" * 40,
                tree="2" * 40,
                closure_spec_sha256="3" * 64,
                closure_rows=(),
                closure_rows_sha256="4" * 64,
                closure_sha256="5" * 64,
                pin_sha256="6" * 64,
            )
            assert package_context._parse_loaded_pin_value(pin) is pin
            try:
                direct_runtime.loaded_runtime_pin_from_dict({})
            except package_context.ContractAuthorityError:
                pass
            else:
                raise AssertionError("package exception did not catch direct runtime error")
            """
        )
        for order in ("direct", "package"):
            completed = subprocess.run(
                [sys.executable, "-B", "-c", probe, str(repo_root), order],
                cwd=self.base,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=30,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_direct_triage_cli_imports_from_an_unrelated_cwd(self) -> None:
        standalone_git_root(self.base)
        with AuthorityFixture() as fixture:
            completed = run_python_entry(
                fixture,
                fixture.runtime_root / "scripts" / "followups_triage.py",
                "--help",
                cwd=self.base,
                timeout=30,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("usage:", completed.stdout)

    def test_direct_triage_ignores_a_poisoned_target_scripts_package(self) -> None:
        """A direct runtime CLI must not import target ``scripts`` authority code."""

        poison = "raise SystemExit('AUTHORITY_POISON_EXECUTED')\n"
        with AuthorityFixture(identity="planveyor") as fixture:
            write(fixture.target_root, "scripts/__init__.py", poison)
            write(fixture.target_root, "scripts/contract_authority_context.py", poison)
            environment = fixture.environment()
            environment["PYTHONPATH"] = str(fixture.target_root)
            completed = run_python_entry(
                fixture,
                fixture.runtime_root / "scripts" / "followups_triage.py",
                "--help",
                environment=environment,
                timeout=30,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("usage:", completed.stdout)
        self.assertNotIn("AUTHORITY_POISON_EXECUTED", completed.stdout + completed.stderr)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

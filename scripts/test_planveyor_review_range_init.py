#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from textwrap import dedent
import time
from types import SimpleNamespace
import unittest


REPO_ROOT = Path(__file__).resolve().parent.parent
PLANVEYOR_SCRIPT = REPO_ROOT / "scripts" / "planveyor.zsh"
PLANVEYOR_MODULE_DIR = REPO_ROOT / "scripts" / "planveyor"
PLAN_TEMPLATE = REPO_ROOT / "docs" / "plans" / "_template.md"
CODE_DRAFT_TEMPLATE = REPO_ROOT / "docs" / "code_drafts" / "_template.md"
AUTHORITY_SOURCE_RUNTIME_INPUTS = (
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
REVIEW_RANGE_ENGINE_RUNTIME_INPUTS = (
    "scripts/review_range_scaffold_engine.py",
    "scripts/plan_status_oracle.py",
    "scripts/plan_lint.py",
    "scripts/review_schema_contract.py",
    "scripts/review_target_snapshot.py",
    "scripts/review_visual_lane_contract.py",
    "scripts/review_header_metadata.py",
    "scripts/retrieval_telemetry_receipt.py",
    "scripts/review_artifact_lint.py",
)
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import plan_status_oracle as PLAN_STATUS_ORACLE
import review_visual_lane_contract as REVIEW_VISUAL_LANE_CONTRACT

import contract_authority_context as authority
import plan_lint
import review_range_scaffold_engine as review_range_engine
from authority_bootstrap_test_support import run_python_entry
from test_contract_authority_support import AuthorityFixture, git, write
from test_support.process_contract_fixtures import run_zsh_fixture

REVIEW_RANGE_LOCAL_INPUT_PATHS = tuple(
    str(spec["path"])
    for spec in review_range_engine.PLANVEYOR_REVIEW_RANGE_SEMANTIC_SURFACE_V1["inputs"].values()
)
REVIEW_RANGE_POLICY_PATH = "docs/_meta/review_range_policy.v1.json"


class ReviewRangeInitRerunLineageTests(unittest.TestCase):
    @staticmethod
    def _review_range_policy_bytes(scope_note: str) -> bytes:
        return json.dumps(
            {
                "schema_version": "review_range_policy.v1",
                "corpus_rule": "planveyor.v1",
                "visual_rule": "planveyor.v1",
                "render_profile": "planveyor.review_only.v1",
                "section_prose": {
                    "review_scope_note": scope_note,
                    "reviewability_note": "fixture reviewability note",
                    "runtime_lane_note": "fixture runtime lane note",
                    "verification_handoff_note": "fixture verification handoff note",
                },
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8") + b"\n"

    @staticmethod
    def _target_visual_lane_sources() -> dict[str, bytes]:
        comparator = "./scripts/run_visual_check.sh --run-id review --repeat 2 --logs-dir .tmp/visual-regression/logs"
        primary = "./scripts/review_visual_design_audit.sh --mode primary --plan docs/plans/<plan>.md --port 8073 --assets-dir .tmp/human-visual-review/primary"
        secondary = "./scripts/review_visual_design_audit.sh --mode secondary --plan docs/plans/<plan>.md --port 8074 --assets-dir .tmp/human-visual-review/secondary"
        commands = "\n".join((comparator, primary, secondary))
        return {
            "docs/smoke_visual.md": (
                "<!-- verification-receipt lane=visual.check_1 lane=visual.check_2 lane=vis.human_visual_review_local -->\n"
                f"```bash\n{commands}\n```\n"
            ).encode("utf-8"),
            "docs/testing_runbook.md": f"```bash\n{commands}\n```\n".encode("utf-8"),
        }


    def _run_local_v2_render(
        self,
        *,
        content_profile_id: str | None = None,
    ) -> tuple[AuthorityFixture, subprocess.CompletedProcess[str], str]:
        fixture = AuthorityFixture(identity="planveyor")
        self.addCleanup(fixture.close)
        target_visual_sources = self._target_visual_lane_sources()
        fixture.activate_planveyor(
            (*authority.STATIC_PLANVEYOR_MERGE_REQUIRED_ENGAGED_PATHS, *REVIEW_RANGE_LOCAL_INPUT_PATHS),
            overrides={
                REVIEW_RANGE_POLICY_PATH: self._review_range_policy_bytes("initial local scope note"),
                **target_visual_sources,
            },
        )
        # A malformed tooling decoy must not affect an engaged declared read.
        write(fixture.runtime_root, "docs/smoke_visual.md", "RUNTIME_DECOY\n")
        write(fixture.runtime_root, "docs/testing_runbook.md", "RUNTIME_DECOY\n")
        for script_name in ("run_visual_check.sh", "review_visual_design_audit.sh"):
            write(fixture.target_root, f"scripts/{script_name}", "#!/bin/sh\n", executable=True)
        current_scope_note = "current local scope note"
        write(fixture.target_root, REVIEW_RANGE_POLICY_PATH, self._review_range_policy_bytes(current_scope_note))
        base = git(fixture.target_root, "rev-parse", "HEAD")
        write(fixture.target_root, "templates/review_range_fixture.html", "<main>fixture</main>\n")
        # Do not use commit_all(): it would add the deliberately untracked v2 marker.
        git(fixture.target_root, "add", "templates/review_range_fixture.html")
        git(fixture.target_root, "commit", "--quiet", "-m", "fixture review range")
        head = git(fixture.target_root, "rev-parse", "HEAD")
        args = [
            "--root", str(fixture.target_root),
            "--base", base,
            "--head", head,
            "--exclude-docs", "1",
            "--force-new", "1",
            "--timestamp", "260910_0030",
        ]
        if content_profile_id is not None:
            args.extend(["--content-profile-id", content_profile_id])
        result = run_python_entry(
            fixture,
            fixture.runtime_root / "scripts" / "review_range_scaffold_engine.py",
            *args,
            cwd=fixture.target_root,
            environment=fixture.environment(),
        )
        return fixture, result, current_scope_note

    def _activate_generic_consumer(self, fixture: AuthorityFixture) -> None:
        """Build an explicit generic fixture without weakening Planveyor helpers."""

        paths = (
            *authority.STATIC_PLANVEYOR_MERGE_REQUIRED_ENGAGED_PATHS,
            *REVIEW_RANGE_LOCAL_INPUT_PATHS,
        )
        target_visual_sources = self._target_visual_lane_sources()
        fixture.activate_local(
            paths,
            overrides={
                REVIEW_RANGE_POLICY_PATH: self._review_range_policy_bytes("generic consumer scope note"),
                **target_visual_sources,
            },
            required_runtime_api=(5, 5),
        )
        for script_name in ("run_visual_check.sh", "review_visual_design_audit.sh"):
            write(fixture.target_root, f"scripts/{script_name}", "#!/bin/sh\n", executable=True)

    def _run_public_generic_consumer_range_init(
        self,
        *,
        fixture_identity: str,
        marker_identity: str,
    ) -> tuple[AuthorityFixture, subprocess.CompletedProcess[str]]:
        fixture = AuthorityFixture(identity=fixture_identity)
        self.addCleanup(fixture.close)
        self._activate_generic_consumer(fixture)
        marker_path = fixture.target_root / authority._snapshot.MARKER_PATH
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        marker["repository_id"] = marker_identity
        marker_path.write_text(json.dumps(marker, sort_keys=True) + "\n", encoding="utf-8")
        base = git(fixture.target_root, "rev-parse", "HEAD")
        write(fixture.target_root, "templates/generic_consumer_fixture.html", "<main>fixture</main>\n")
        git(fixture.target_root, "add", "templates/generic_consumer_fixture.html")
        git(fixture.target_root, "commit", "--quiet", "-m", "generic consumer review range")
        head = git(fixture.target_root, "rev-parse", "HEAD")
        facade = shlex.quote(str(fixture.runtime_root / "scripts" / "planveyor.zsh"))
        program = (
            fixture.shell_loader()
            + f"\nplanveyor_source_runtime {facade} || exit $?;\n"
            + f"planveyor_review_range_init --force-new {shlex.quote(base)} {shlex.quote(head)} 1\n"
        )
        environment = fixture.environment()
        environment["PYBIN"] = sys.executable
        environment["PLANVEYOR_RUNTIME_SOURCE_KIND"] = "git"
        result = subprocess.run(
            ["/bin/zsh", "-dfc", program],
            cwd=fixture.target_root,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
            timeout=120,
        )
        return fixture, result


    def test_local_v2_semantic_provenance_uses_current_content_metadata(self) -> None:
        fixture, result, current_scope_note = self._run_local_v2_render(
            content_profile_id="default",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        plan_ref = result.stdout.strip()
        plan_path, _draft_path = self._generated_paths(fixture.target_root, plan_ref)
        plan_text = plan_path.read_text(encoding="utf-8")
        self.assertIn(current_scope_note, plan_text)
        self.assertIn('"availability_state": "available"', plan_text)
        self.assertIn("machine-backed runtime-UI visual lane", plan_text)
        self.assertNotIn("RUNTIME_DECOY", plan_text)
        receipt, error = plan_lint.parse_review_range_semantic_provenance(plan_text.splitlines())
        self.assertIsNone(error)
        assert receipt is not None
        self.assertEqual(receipt["schema_version"], "review_range_semantic_provenance.v2")
        self.assertEqual(receipt["source_engine_version"], "review-range-source-route.v2")
        self.assertEqual(receipt["context_state"], "engaged")
        self.assertEqual(receipt["behavior_identity"], "planveyor")
        self.assertEqual(
            receipt["inputs"][0],
            {
                "id": "policy_json",
                "reader": "strict_duplicate_key_safe_json",
                "contract_relative_path": REVIEW_RANGE_POLICY_PATH,
                "content_source": "current_local_worktree",
            },
        )
        self.assertEqual(
            [row["id"] for row in receipt["inputs"]],
            list(review_range_engine.PLANVEYOR_REVIEW_RANGE_SEMANTIC_SURFACE_V1["inputs"]),
        )
        for row in receipt["inputs"]:
            self.assertEqual(set(row), {"id", "reader", "contract_relative_path", "content_source"})
            self.assertEqual(row["content_source"], "current_local_worktree")
        self.assertIsNone(plan_lint._review_range_semantic_provenance_shape_error(receipt))

    def test_public_shell_generic_consumer_emits_lintable_matching_v2_receipt(self) -> None:
        marker_identity = "consumer_42"
        fixture, result = self._run_public_generic_consumer_range_init(
            fixture_identity="physical_consumer_42",
            marker_identity=marker_identity,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        plan_ref = result.stdout.strip()
        plan_path, _draft_path = self._generated_paths(fixture.target_root, plan_ref)
        receipt, error = plan_lint.parse_review_range_semantic_provenance(
            plan_path.read_text(encoding="utf-8").splitlines()
        )
        self.assertIsNone(error)
        assert receipt is not None
        self.assertEqual(receipt["schema_version"], "review_range_semantic_provenance.v2")
        self.assertEqual(receipt["behavior_identity"], marker_identity)
        self.assertEqual(receipt["marker_repository_id_or_not_applicable"], marker_identity)
        self.assertEqual(receipt["selected_rule_ids"], ["planveyor.v1", "planveyor.review_only.v1"])
        self.assertIsNone(plan_lint._review_range_semantic_provenance_shape_error(receipt))
        lint_environment = fixture.environment()
        lint_environment["PLANVEYOR_RUNTIME_SOURCE_KIND"] = "git"
        lint = run_python_entry(
            fixture,
            fixture.runtime_root / "scripts" / "plan_lint.py",
            str(plan_path),
            cwd=fixture.target_root,
            environment=lint_environment,
            timeout=120,
        )
        self.assertEqual(lint.returncode, 0, lint.stdout + lint.stderr)

    def test_public_shell_rejects_invalid_generic_consumer_before_review_artifacts(self) -> None:
        cases = (
            ("default", "default", "default"),
            ("grammar", "consumer invalid", "consumer invalid"),
        )
        for label, fixture_identity, marker_identity in cases:
            with self.subTest(case=label):
                fixture, result = self._run_public_generic_consumer_range_init(
                    fixture_identity=fixture_identity,
                    marker_identity=marker_identity,
                )
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertFalse(list((fixture.target_root / "docs" / "plans").glob("*_reviewer_range_*.md")))
                self.assertFalse(list((fixture.target_root / "docs" / "code_drafts").glob("*__code_draft.md")))
                self.assertFalse(
                    [
                        path
                        for path in (fixture.target_root / "docs" / "code_reviews").glob("*.md")
                        if not path.name.startswith("_template")
                    ]
                )

    def test_local_v2_rejects_unknown_content_profile(self) -> None:
        _fixture, result, _current_scope_note = self._run_local_v2_render(
            content_profile_id="unknown",
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid choice", result.stderr)

    def test_local_v2_target_local_content_selector_uses_declared_sources(self) -> None:
        fixture, result, _current_scope_note = self._run_local_v2_render(
            content_profile_id="target-local",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        plan_path, _draft_path = self._generated_paths(fixture.target_root, result.stdout.strip())
        plan_text = plan_path.read_text(encoding="utf-8")
        self.assertIn('"availability_state": "available"', plan_text)
        self.assertNotIn("RUNTIME_DECOY", plan_text)

    def test_legacy_root_references_are_public_and_target_local_fails_closed(self) -> None:
        expected = (
            ("reviewer_role", "docs/roles/reviewer.md"),
            ("review_scoping_playbook", "docs/playbooks/review_scoping_plan.md"),
            ("review_merge_range_playbook", "docs/playbooks/review_merge_range.md"),
        )
        for profile_id in ("default", "planveyor"):
            with self.subTest(profile_id=profile_id):
                self.assertEqual(
                    review_range_engine._legacy_root_review_references(
                        content_profile_id=profile_id,
                    ).references,
                    expected,
                )
        with self.assertRaises(review_range_engine.EngineError) as raised:
            review_range_engine._legacy_root_review_references(content_profile_id="target-local")
        self.assertEqual(str(raised.exception), "target_local_requires_declared_context")

    def _tooling_runtime_without_templates(self, root: Path) -> Path:
        """Provide the authority source closure while omitting the template under test."""

        tooling = root / "missing-tooling-root"
        for relative in AUTHORITY_SOURCE_RUNTIME_INPUTS:
            source = REPO_ROOT / relative
            target = tooling / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        return tooling

    def _install_fixed_date(self, root: Path, stamp: str) -> Path:
        bin_dir = root / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        date_script = bin_dir / "date"
        date_script.write_text(
            f"""#!/bin/zsh
if [[ "${{1:-}}" == "+%y%m%d_%H%M" ]]; then
  print -r -- "{stamp}"
else
  /bin/date "$@"
fi
""",
            encoding="utf-8",
        )
        date_script.chmod(0o755)
        return bin_dir

    def _git(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            text=True,
            capture_output=True,
        )

    def _write_commit(self, root: Path, rel_path: str, text: str, message: str) -> str:
        file_path = root / rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(text, encoding="utf-8")
        self._git(root, "add", rel_path)
        self._git(root, "commit", "-m", message)
        return self._git(root, "rev-parse", "HEAD").stdout.strip()

    def _write_multi_commit(
        self,
        root: Path,
        files: dict[str, str],
        message: str,
        *,
        executable_paths: tuple[str, ...] = (),
    ) -> str:
        for rel_path, payload in files.items():
            file_path = root / rel_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(payload, encoding="utf-8")
            if rel_path in executable_paths:
                file_path.chmod(0o755)
            self._git(root, "add", rel_path)
        self._git(root, "commit", "-m", message)
        return self._git(root, "rev-parse", "HEAD").stdout.strip()

    def _init_repo(self, root: Path) -> tuple[str, str]:
        (root / "scripts").mkdir(parents=True, exist_ok=True)
        (root / "docs" / "plans").mkdir(parents=True, exist_ok=True)
        (root / "docs" / "code_drafts").mkdir(parents=True, exist_ok=True)
        shutil.copy2(PLANVEYOR_SCRIPT, root / "scripts" / "planveyor.zsh")
        shutil.copytree(PLANVEYOR_MODULE_DIR, root / "scripts" / "planveyor")
        # Raw facade sourcing resolves and verifies this finite sibling closure
        # from the fixture root before it loads the copied module tree.
        for relative in (*AUTHORITY_SOURCE_RUNTIME_INPUTS, *REVIEW_RANGE_ENGINE_RUNTIME_INPUTS):
            if relative == "scripts/planveyor.zsh" or relative.startswith("scripts/planveyor/"):
                continue
            source = REPO_ROOT / relative
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        shutil.copy2(PLAN_TEMPLATE, root / "docs" / "plans" / "_template.md")
        shutil.copy2(CODE_DRAFT_TEMPLATE, root / "docs" / "code_drafts" / "_template.md")
        (root / "docs" / "_meta").mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / "docs" / "_meta" / "plan_vocab.json", root / "docs" / "_meta" / "plan_vocab.json")

        self._git(root, "init")
        self._git(root, "config", "user.name", "Test User")
        self._git(root, "config", "user.email", 'test' + '@' + 'example' + '.' + 'com')

        base = self._write_commit(root, "apps/example.py", "VALUE = 1\n", "base")
        head = self._write_commit(root, "apps/example.py", "VALUE = 2\n", "head")
        return base, head

    def _run_range_init(
        self,
        root: Path,
        base: str,
        head: str,
        *,
        exclude_docs: int = 0,
        extra_env: dict[str, str] | None = None,
        force_new: bool = False,
        fixed_date_stamp: str | None = None,
        runtime_facade: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        path = os.environ.get("PATH", os.defpath)
        fixture_env = {"PLANVEYOR_ROOT": str(REPO_ROOT)}
        if fixed_date_stamp:
            fixed_bin = self._install_fixed_date(root, fixed_date_stamp)
            path = f"{fixed_bin}:{path}"
        if extra_env:
            fixture_env.update(extra_env)
        force_new_prefix = "--force-new " if force_new else ""
        # Pin the fixture clock after sourcing the wrapper.
        clock_override = ""
        if fixed_date_stamp:
            clock_override = (
                'date() { if [[ "$1" == "+%y%m%d_%H%M" ]]; then print -r -- '
                + shlex.quote(fixed_date_stamp)
                + '; else /bin/date "$@"; fi; }; '
            )
        return run_zsh_fixture(
            f"source {shlex.quote(str(runtime_facade or root / 'scripts' / 'planveyor.zsh'))} && "
            f"{clock_override}planveyor_review_range_init {force_new_prefix}{base} {head} {exclude_docs}",
            cwd=root,
            path=path,
            pybin=str(Path(sys.executable).resolve()),
            fixture_env=fixture_env,
            home=root / ".home",
            check=False,
        )

    def _run_range_engine(
        self,
        root: Path,
        base: str,
        head: str,
        *,
        content_profile_id: str = "default",
        exclude_docs: int = 0,
        force_new: bool = False,
        fixed_date_stamp: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = {
            key: value for key, value in os.environ.items()
            if not key.startswith(("PLANVEYOR_", "ZCODE_"))
        }
        env["PYBIN"] = sys.executable
        env["HOME"] = str(root / ".home")
        env["PLANVEYOR_ROOT"] = str(REPO_ROOT)
        args = [
            sys.executable,
            str(root / "scripts" / "review_range_scaffold_engine.py"),
            "--root", str(root),
            "--base", base,
            "--head", head,
            "--exclude-docs", str(exclude_docs),
            "--force-new", "1" if force_new else "0",
            "--content-profile-id", content_profile_id,
        ]
        if fixed_date_stamp:
            args.extend(["--timestamp", fixed_date_stamp])
        return subprocess.run(
            args,
            cwd=root,
            text=True,
            capture_output=True,
            env=env,
            stdin=subprocess.DEVNULL,
            timeout=120,
            check=False,
        )

    def _run_range_stats_json(self, root: Path, base: str, head: str) -> subprocess.CompletedProcess[str]:
        return run_zsh_fixture(
            f"source scripts/planveyor.zsh && planveyor_merge_range_stats_json {base} {head}",
            cwd=root,
            path=os.environ.get("PATH", os.defpath),
            pybin=str(Path(sys.executable).resolve()),
            fixture_env={"PLANVEYOR_ROOT": str(REPO_ROOT)},
            home=root / ".home",
            check=False,
        )

    def _run_plan_lint(self, root: Path, plan_rel: str) -> subprocess.CompletedProcess[str]:
        env = {
            key: value for key, value in os.environ.items()
            if not key.startswith(("PLANVEYOR_", "ZCODE_"))
        }
        env["PYBIN"] = sys.executable
        env["HOME"] = str(root / ".home")
        env["PLANVEYOR_ROOT"] = str(REPO_ROOT)
        return subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "plan_lint.py"), plan_rel],
            cwd=root,
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )

    def _run_copy_doc_template(
        self,
        root: Path,
        output_rel: str,
        family: str,
        filename: str,
        *,
        tooling_root: Path | None = None,
        runtime_facade: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return run_zsh_fixture(
            f"source {shlex.quote(str(runtime_facade or root / 'scripts' / 'planveyor.zsh'))} && "
            f"_planveyor_copy_doc_template_if_missing {output_rel} {family} {filename}",
            cwd=root,
            path=os.environ.get("PATH", os.defpath),
            pybin=str(Path(sys.executable).resolve()),
            fixture_env={"PLANVEYOR_ROOT": str(tooling_root or REPO_ROOT)},
            home=root / ".home",
            check=False,
        )

    def _generated_paths(self, root: Path, plan_rel: str) -> tuple[Path, Path]:
        plan_path = root / plan_rel
        draft_path = root / "docs" / "code_drafts" / f"{plan_path.stem}__code_draft.md"
        return plan_path, draft_path

    def _retired_review_source_refs(self) -> tuple[str, str, str]:
        return (
            "docs/retired-consumer/reviewer.md",
            "docs/retired-consumer/review_scoping_plan.md",
            "docs/retired-consumer/review_merge_range.md",
        )

    @staticmethod
    def _generic_review_source_refs() -> tuple[str, str, str]:
        return (
            "docs/roles/reviewer.md",
            "docs/playbooks/review_scoping_plan.md",
            "docs/playbooks/review_merge_range.md",
        )

    def _section_body(self, text: str, heading: str) -> str:
        marker = f"## {heading}\n"
        self.assertIn(marker, text)
        return text.split(marker, 1)[1].split("\n## ", 1)[0]

    def _code_draft_meta(self, draft_path: Path) -> dict:
        draft_text = draft_path.read_text(encoding="utf-8")
        raw = draft_text.split("```json", 1)[1].split("```", 1)[0].strip()
        payload = json.loads(raw)
        return payload["code_draft_meta"]

    def _plan_meta(self, plan_path: Path) -> dict:
        plan_text = plan_path.read_text(encoding="utf-8")
        raw = plan_text.split("```json", 1)[1].split("```", 1)[0].strip()
        payload = json.loads(raw)
        return payload["plan_meta"]

    def _assert_no_template_docs_impact_residue(self, section: str) -> None:
        self.assertNotIn("Source docs used: `docs/...`", section)
        self.assertNotIn("reviews / retrieval hits", section)
        self.assertNotIn("docs that must be edited in the same implementation slice", section)
        self.assertNotIn("Owner input / review blocker / prior plan / rollout packet", section)

    def _assert_generated_understanding_summary(self, plan_text: str) -> None:
        understanding = self._section_body(plan_text, "Как я понял задачу")
        self.assertIn("Нужно проверить merge-range", understanding)
        self.assertIn("review-only flow", understanding)
        self.assertNotIn("Required for Architect intake", understanding)
        self.assertNotIn("Коротко, по-человечески", understanding)

    def _assert_header_lines_have_no_trailing_whitespace(self, *paths: Path) -> None:
        header_prefixes = (
            "**Date:**",
            "**Stage:**",
            "**Priority:**",
            "**Plan type:**",
            "**Status:**",
            "**Cluster:**",
            "**Related plan:**",
            "**Author role:**",
        )
        for path in paths:
            for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if line.startswith(header_prefixes):
                    self.assertEqual(line.rstrip(), line, f"{path}:{line_no}")

    def test_shared_scaffold_templates_ignore_stale_repo_local_mirrors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            base, head = self._init_repo(root)
            sentinel = "STALE_REPO_LOCAL_TEMPLATE_SENTINEL"
            (root / "docs" / "plans" / "_template.md").write_text(
                f"# {sentinel} plan template\n\nThis repo-local mirror is stale.\n",
                encoding="utf-8",
            )
            (root / "docs" / "code_drafts" / "_template.md").write_text(
                f"# {sentinel} code draft template\n\nThis repo-local mirror is stale.\n",
                encoding="utf-8",
            )

            result = self._run_range_init(
                root,
                base,
                head,
                fixed_date_stamp="260619_0201",
                runtime_facade=PLANVEYOR_SCRIPT,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            plan_rel = result.stdout.strip()
            plan_path, draft_path = self._generated_paths(root, plan_rel)
            plan_text = plan_path.read_text(encoding="utf-8")
            draft_text = draft_path.read_text(encoding="utf-8")
            self.assertNotIn(sentinel, plan_text)
            self.assertNotIn(sentinel, draft_text)
            self.assertIn("# Plan:", plan_text)
            self.assertIn("# Code draft:", draft_text)

    def test_existing_doc_template_output_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)
            output = root / "docs" / "plans" / "existing.md"
            output.write_text("KEEP EXISTING OUTPUT\n", encoding="utf-8")
            (root / "docs" / "plans" / "_template.md").write_text(
                "# stale repo-local mirror\n",
                encoding="utf-8",
            )

            result = self._run_copy_doc_template(root, "docs/plans/existing.md", "plans", "_template.md")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(output.read_text(encoding="utf-8"), "KEEP EXISTING OUTPUT\n")

    def test_shared_scaffold_templates_fail_when_tooling_master_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)
            missing_tooling = self._tooling_runtime_without_templates(root)

            cases = (
                ("docs/plans/generated_missing.md", "plans", "_template.md"),
                ("docs/code_drafts/generated_missing.md", "code_drafts", "_template.md"),
            )
            for output_rel, family, filename in cases:
                with self.subTest(family=family):
                    result = self._run_copy_doc_template(
                        root,
                        output_rel,
                        family,
                        filename,
                        tooling_root=missing_tooling,
                        runtime_facade=missing_tooling / "scripts" / "planveyor.zsh",
                    )

                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("Missing shared doc template", result.stderr)
                    self.assertFalse((root / output_rel).exists())

    def _plan_log_paths(self, root: Path) -> list[str]:
        log_path = root / ".planveyor.planpath.log"
        if not log_path.exists():
            return []
        result: list[str] = []
        for raw in log_path.read_text(encoding="utf-8").splitlines():
            if "\t" not in raw:
                continue
            _, plan_path = raw.split("\t", 1)
            result.append(plan_path.strip())
        return result

    def test_generic_non_doc_range_keeps_code_review_host_without_planveyor_visual_lane(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _, base = self._init_repo(root)
            comparator = "./scripts/run_visual_check.sh --run-id review --repeat 2 --logs-dir .tmp/visual-regression/logs"
            human_primary = "./scripts/review_visual_design_audit.sh --mode primary --plan docs/plans/<plan>.md --port 8073 --assets-dir .tmp/human-visual-review/primary"
            human_secondary = "./scripts/review_visual_design_audit.sh --mode secondary --plan docs/plans/<plan>.md --port 8074 --assets-dir .tmp/human-visual-review/secondary"
            visual_sources = (
                "<!-- verification-receipt lane=visual.check_1 lane=visual.check_2 lane=vis.human_visual_review_local -->\n"
                "```bash\n"
                f"{comparator}\n{human_primary}\n{human_secondary}\n"
                "```\n"
            )
            head = self._write_multi_commit(
                root,
                {
                    "templates/consumer_dashboard.html": "<div>reports</div>\n",
                    "scripts/run_visual_check.sh": "#!/bin/sh\n",
                    "scripts/review_visual_design_audit.sh": "#!/bin/sh\n",
                    "docs/smoke_visual.md": visual_sources,
                    "docs/testing_runbook.md": visual_sources,
                    "docs/plans/260329_2030_consumer_visual_contract.md": dedent(
                        """
                        # Plan: Consumer-declared visual contract

                        ## Visual Acceptance (browser, UI tasks)
                        ### Visual env
                        - Modes to test: `primary`, `secondary`
                        - Endpoint: `<consumer-declared endpoint>`
                        - Visual evidence: `docs/code_reviews/assets/<REVIEW_BASENAME>/...`

                        ### How to run (Reviewer)
                        - Run only the command declared by the selected consumer.

                        ### Visual checks
                        - `Mode: primary` — `Check: /dashboard` — Screenshot: `primary_dashboard.png`
                        - `Mode: secondary` — `Check: /dashboard?variant=secondary` — Screenshot: `secondary_dashboard.png`
                        """
                    ),
                },
                "reports lane",
                executable_paths=(
                    "scripts/run_visual_check.sh",
                    "scripts/review_visual_design_audit.sh",
                ),
            )

            result = self._run_range_init(root, base, head, fixed_date_stamp="260330_1310")

            self.assertEqual(result.returncode, 0, result.stderr)
            plan_rel = result.stdout.strip()
            plan_path, draft_path = self._generated_paths(root, plan_rel)
            plan_text = plan_path.read_text(encoding="utf-8")
            draft_text = draft_path.read_text(encoding="utf-8")
            expected_review_artifact = f"docs/code_reviews/{plan_path.stem}.md"
            expected_target_carrier = f"`**Target:** RANGE={base}..{head} (EXCLUDE_DOCS=0)`"
            expected_spec_carrier = f"`**Spec:** {plan_rel}`"

            self.assertIn(f"- Expected review artifact: `{expected_review_artifact}`", plan_text)
            self.assertIn(expected_target_carrier, plan_text)
            self.assertIn(expected_spec_carrier, plan_text)
            self.assertIn(expected_target_carrier, draft_text)
            self.assertIn(expected_spec_carrier, draft_text)
            self.assertNotIn("origin_plan_state=manual_range_review_no_origin_plan", plan_text)
            self.assertNotIn("origin_plan_state=manual_range_review_no_origin_plan", draft_text)
            self.assertIn(f"- Code review (primary): `{expected_review_artifact}`", plan_text)
            self.assertNotIn(f"- Doc review (docs-only): `{expected_review_artifact}`", plan_text)
            self.assertIn('"path": "templates/consumer_dashboard.html"', draft_text)
            self.assertIn('"path": "docs/plans/260329_2030_consumer_visual_contract.md"', draft_text)
            self.assertNotIn(f'"path": "{expected_review_artifact}"', draft_text)
            draft_review_route = self._section_body(draft_text, "Review route")
            self.assertIn(f"- `Primary artifact`: `{expected_review_artifact}`", draft_review_route)
            self.assertIn("- `Lane type`: `code review`", draft_review_route)
            self.assertNotIn("YYMMDD_HHMM_topic.md", draft_review_route)
            self.assertNotIn(" | ", draft_review_route)
            self.assertIn("## Review visual lane contract", plan_text)
            self.assertIn("## Review visual lane contract", draft_text)
            plan_contract = self._section_body(plan_text, "Review visual lane contract")
            draft_contract = self._section_body(draft_text, "Review visual lane contract")
            self.assertEqual(plan_contract, draft_contract)
            self.assertIn('"availability_state": "not_applicable"', plan_contract)
            self.assertIn('"reason": "no_declared_runtime_visual_lane:planveyor"', plan_contract)
            self.assertNotIn(comparator, plan_text)
            self.assertNotIn(human_primary.replace("docs/plans/<plan>.md", plan_rel), plan_text)
            self.assertNotIn(human_secondary.replace("docs/plans/<plan>.md", plan_rel), plan_text)
            self.assertIn("no declared applicable visual carrier", plan_text)
            self.assertNotIn("Mode: primary", self._section_body(plan_text, "Visual Acceptance (browser, UI tasks)"))
            plan_receipt = plan_text.split("## Reviewability preflight receipt", 1)[1].split("## Changes (by area)", 1)[0]
            draft_receipt = draft_text.split("## Reviewability preflight receipt", 1)[1].split("## Targeted changes (by file)", 1)[0]
            self.assertNotIn("machine-backed two-claim visual lane", plan_receipt)
            self.assertNotIn("Mode: secondary", plan_text)
            self.assertNotIn("one affected runtime UI surface", plan_text)
            self.assertNotIn("UNCONFIRMED", plan_receipt)
            self.assertNotIn("UNCONFIRMED", draft_receipt)

    def test_docs_only_range_uses_doc_review_host_and_explicit_browser_na(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _, base = self._init_repo(root)
            head = self._write_multi_commit(
                root,
                {"docs/guides/example.md": "# docs only\n"},
                "docs only",
            )

            result = self._run_range_init(root, base, head, fixed_date_stamp="260330_1311")

            self.assertEqual(result.returncode, 0, result.stderr)
            plan_rel = result.stdout.strip()
            plan_path, draft_path = self._generated_paths(root, plan_rel)
            plan_text = plan_path.read_text(encoding="utf-8")
            draft_text = draft_path.read_text(encoding="utf-8")
            expected_review_artifact = f"docs/doc_reviews/{plan_path.stem}.md"
            expected_target_carrier = f"`**Target:** RANGE={base}..{head} (EXCLUDE_DOCS=0)`"
            expected_spec_carrier = f"`**Spec:** {plan_rel}`"

            self.assertIn(f"- Expected review artifact: `{expected_review_artifact}`", plan_text)
            self.assertIn(expected_target_carrier, plan_text)
            self.assertIn(expected_spec_carrier, plan_text)
            self.assertIn(expected_target_carrier, draft_text)
            self.assertIn(expected_spec_carrier, draft_text)
            self.assertNotIn("origin_plan_state=manual_range_review_no_origin_plan", plan_text)
            self.assertNotIn("origin_plan_state=manual_range_review_no_origin_plan", draft_text)
            self.assertIn(f"- Doc review (docs-only): `{expected_review_artifact}`", plan_text)
            self.assertNotIn(f"- Code review (primary): `{expected_review_artifact}`", plan_text)
            self.assertIn('"path": "docs/guides/example.md"', draft_text)
            self.assertNotIn('"path": "apps/example.py"', draft_text)
            draft_review_route = self._section_body(draft_text, "Review route")
            self.assertIn(f"- `Primary artifact`: `{expected_review_artifact}`", draft_review_route)
            self.assertIn("- `Lane type`: `docs review`", draft_review_route)
            self.assertNotIn("YYMMDD_HHMM_topic.md", draft_review_route)
            self.assertNotIn(" | ", draft_review_route)
            plan_docs_impact = self._section_body(plan_text, "Documentation impact / provenance")
            draft_docs_impact = self._section_body(draft_text, "Documentation impact / provenance")
            self.assertIn("exact reviewed target metadata", plan_docs_impact)
            self.assertIn("code_draft_meta.targets", plan_docs_impact)
            self.assertIn("- Synchronous doc/registry targets: `docs/guides/example.md`", plan_docs_impact)
            self.assertIn("- Synchronous doc/registry targets: `docs/guides/example.md`", draft_docs_impact)
            self._assert_no_template_docs_impact_residue(plan_docs_impact)
            self._assert_no_template_docs_impact_residue(draft_docs_impact)
            plan_receipt = plan_text.split("## Reviewability preflight receipt", 1)[1].split("## Changes (by area)", 1)[0]
            draft_receipt = draft_text.split("## Reviewability preflight receipt", 1)[1].split("## Targeted changes (by file)", 1)[0]
            self.assertIn("`N/A (why: docs-only range; runtime UI gate is not implied by changed paths)`", plan_text)
            self.assertIn("no truthful declared visual contextual lane auto-enabled for this range/profile", plan_text)
            self.assertNotIn("Mode: primary", plan_text)
            self.assertNotIn("Mode: secondary", plan_text)
            self.assertNotIn("UNCONFIRMED", plan_receipt)
            self.assertNotIn("UNCONFIRMED", draft_receipt)

    def test_process_tooling_range_materializes_docs_impact_na_from_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _, _ = self._init_repo(root)
            base = self._write_commit(root, "scripts/local_helper.py", "VALUE = 1\n", "helper base")
            head = self._write_commit(root, "scripts/local_helper.py", "VALUE = 2\n", "helper head")

            result = self._run_range_init(root, base, head, fixed_date_stamp="260517_1222")

            self.assertEqual(result.returncode, 0, result.stderr)
            plan_rel = result.stdout.strip()
            plan_path, draft_path = self._generated_paths(root, plan_rel)
            plan_text = plan_path.read_text(encoding="utf-8")
            draft_text = draft_path.read_text(encoding="utf-8")
            expected_na = (
                "- Synchronous doc/registry targets: "
                "`N/A (why=process/tooling-only reviewed range; no product documentation target inferred from exact target metadata)`"
            )

            plan_docs_impact = self._section_body(plan_text, "Documentation impact / provenance")
            draft_docs_impact = self._section_body(draft_text, "Documentation impact / provenance")
            self.assertIn("exact reviewed target metadata", plan_docs_impact)
            self.assertIn("code_draft_meta.targets", plan_docs_impact)
            self.assertIn("scripts/local_helper.py", plan_docs_impact)
            self.assertIn(expected_na, plan_docs_impact)
            self.assertIn(expected_na, draft_docs_impact)
            self.assertIn("scripts/local_helper.py", draft_text)
            self._assert_no_template_docs_impact_residue(plan_docs_impact)
            self._assert_no_template_docs_impact_residue(draft_docs_impact)

    def test_process_doc_range_lists_sync_targets_and_retrieval_noop_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _, _ = self._init_repo(root)
            base = self._write_multi_commit(
                root,
                {
                    "scripts/docs_retrieve.py": "VALUE = 1\n",
                    "docs/plans/process_contract.md": "# process contract\n",
                },
                "process docs base",
            )
            head = self._write_multi_commit(
                root,
                {
                    "scripts/docs_retrieve.py": "VALUE = 2\n",
                    "docs/plans/process_contract.md": "# process contract\n\nUpdated.\n",
                },
                "process docs head",
            )

            result = self._run_range_init(root, base, head, exclude_docs=0, fixed_date_stamp="260522_2322")

            self.assertEqual(result.returncode, 0, result.stderr)
            plan_rel = result.stdout.strip()
            plan_path, draft_path = self._generated_paths(root, plan_rel)
            plan_text = plan_path.read_text(encoding="utf-8")
            draft_text = draft_path.read_text(encoding="utf-8")

            expected_sync_line = "- Synchronous doc/registry targets: `docs/plans/process_contract.md`"
            plan_docs_impact = self._section_body(plan_text, "Documentation impact / provenance")
            draft_docs_impact = self._section_body(draft_text, "Documentation impact / provenance")
            retrieval_receipt = self._section_body(plan_text, "Retrieval telemetry receipt")
            self._assert_generated_understanding_summary(plan_text)
            self.assertIn(expected_sync_line, plan_docs_impact)
            self.assertIn(expected_sync_line, draft_docs_impact)
            self.assertNotIn("process/tooling-only reviewed range", plan_docs_impact)
            self.assertIn("- used_for_decision: `false`", retrieval_receipt)
            self.assertIn("- no_op_reason: `not_used_for_decision`", retrieval_receipt)

            lint_result = self._run_plan_lint(root, plan_rel)
            self.assertEqual(lint_result.returncode, 0, lint_result.stdout + lint_result.stderr)

    def test_role_runtime_range_materializes_mapped_dependent_inventory(self) -> None:
        required_paths = (
            "scripts/planveyor/role_runtime.zsh",
            "scripts/test_planveyor_init_capture.py",
            "scripts/test_planveyor_trace_extractor.py",
            "scripts/test_planveyor_bare_entrypoints.py",
            "scripts/test_planveyor_router_merge_boundary.py",
        )
        dependent_paths = required_paths[1:]

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)
            for rel_path in dependent_paths:
                path = root / rel_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# baseline dependent test\n", encoding="utf-8")
            self._git(root, "add", *required_paths)
            self._git(root, "commit", "-m", "track role runtime helper")
            base = self._git(root, "rev-parse", "HEAD").stdout.strip()
            for rel_path in required_paths:
                path = root / rel_path
                path.write_text(
                    path.read_text(encoding="utf-8") + "\n# range touch for dependent inventory\n",
                    encoding="utf-8",
                )
            self._git(root, "add", *required_paths)
            self._git(root, "commit", "-m", "touch role runtime helper")
            head = self._git(root, "rev-parse", "HEAD").stdout.strip()

            result = self._run_range_init(root, base, head, exclude_docs=0, fixed_date_stamp="260628_2106")

            self.assertEqual(result.returncode, 0, result.stderr)
            plan_rel = result.stdout.strip()
            plan_path, draft_path = self._generated_paths(root, plan_rel)
            plan_text = plan_path.read_text(encoding="utf-8")
            draft_text = draft_path.read_text(encoding="utf-8")
            plan_receipt = plan_text.split("## Reviewability preflight receipt", 1)[1].split("## Changes (by area)", 1)[0]
            draft_receipt = draft_text.split("## Reviewability preflight receipt", 1)[1].split("## Targeted changes (by file)", 1)[0]

            self._assert_generated_understanding_summary(plan_text)
            self.assertIn("required mapped run-to-confirm inventory for `scripts/planveyor/role_runtime.zsh`", plan_receipt)
            self.assertIn("required mapped run-to-confirm inventory for `scripts/planveyor/role_runtime.zsh`", draft_receipt)
            for rel_path in dependent_paths:
                self.assertIn(rel_path, plan_receipt)
                self.assertIn(rel_path, draft_receipt)

            lint_result = self._run_plan_lint(root, plan_rel)
            self.assertEqual(lint_result.returncode, 0, lint_result.stdout + lint_result.stderr)

    def test_mixed_range_lists_exact_doc_targets_in_docs_impact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _, base = self._init_repo(root)
            head = self._write_multi_commit(
                root,
                {
                    "apps/example.py": "VALUE = 3\n",
                    "docs/guides/example.md": "# doc target\n",
                },
                "mixed app and docs",
            )

            result = self._run_range_init(root, base, head, exclude_docs=0, fixed_date_stamp="260517_1223")

            self.assertEqual(result.returncode, 0, result.stderr)
            plan_rel = result.stdout.strip()
            plan_path, draft_path = self._generated_paths(root, plan_rel)
            plan_text = plan_path.read_text(encoding="utf-8")
            draft_text = draft_path.read_text(encoding="utf-8")

            plan_docs_impact = self._section_body(plan_text, "Documentation impact / provenance")
            draft_docs_impact = self._section_body(draft_text, "Documentation impact / provenance")
            expected_line = "- Synchronous doc/registry targets: `docs/guides/example.md`"
            self.assertIn(expected_line, plan_docs_impact)
            self.assertIn(expected_line, draft_docs_impact)
            self.assertIn("apps/example.py", draft_text)
            self.assertIn("docs/guides/example.md", draft_text)
            self.assertNotIn("process/tooling-only reviewed range", plan_docs_impact)
            self._assert_no_template_docs_impact_residue(plan_docs_impact)
            self._assert_no_template_docs_impact_residue(draft_docs_impact)

    def test_range_stats_helper_labels_total_and_first_parent_counts_separately(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _, _ = self._init_repo(root)
            base = self._git(root, "rev-parse", "HEAD").stdout.strip()
            branch = self._git(root, "branch", "--show-current").stdout.strip() or "master"
            self._git(root, "checkout", "-b", "side")
            self._write_commit(root, "apps/side.py", "SIDE = 1\n", "side change")
            self._git(root, "checkout", branch)
            self._write_commit(root, "apps/main.py", "MAIN = 1\n", "main change")
            self._git(root, "merge", "--no-ff", "side", "-m", "merge side")
            head = self._git(root, "rev-parse", "HEAD").stdout.strip()

            stats_result = self._run_range_stats_json(root, base, head)

            self.assertEqual(stats_result.returncode, 0, stats_result.stderr)
            stats = json.loads(stats_result.stdout)
            self.assertEqual(stats["range"], f"{base}..{head}")
            self.assertEqual(stats["total_commits"], 3)
            self.assertEqual(stats["first_parent_commits"], 2)
            self.assertEqual(stats["changed_files"], 2)
            self.assertEqual(stats["diffstat"]["files_changed"], 2)
            self.assertEqual(stats["labels"]["total_commits"], "total commits")
            self.assertEqual(stats["labels"]["first_parent_commits"], "first-parent commits")
            self.assertIn("files changed", stats["diffstat_summary"])

            result = self._run_range_init(root, base, head, fixed_date_stamp="260503_0036")

            self.assertEqual(result.returncode, 0, result.stderr)
            plan_rel = result.stdout.strip()
            plan_path, draft_path = self._generated_paths(root, plan_rel)
            plan_text = plan_path.read_text(encoding="utf-8")
            draft_text = draft_path.read_text(encoding="utf-8")

            for text in (plan_text, draft_text):
                self.assertIn("planveyor_merge_range_stats_json", text)
                self.assertIn("zsh -lc 'source scripts/planveyor.zsh && planveyor_merge_range_stats_json", text)
                self.assertIn("total_commits=3", text)
                self.assertIn("first_parent_commits=2", text)
                self.assertIn("changed_files=2", text)
                self.assertIn("diffstat_summary=", text)

    def test_deleted_paths_split_from_live_targets_and_bundle_check_accepts_scaffold(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _, prior_head = self._init_repo(root)
            base = self._write_multi_commit(
                root,
                {
                    "apps/live.py": "VALUE = 1\n",
                    "docs/remove_me.md": "# remove me\n",
                    "cookies.txt": "cookie\n",
                },
                "add removable files",
            )
            (root / "apps" / "live.py").write_text("VALUE = 2\n", encoding="utf-8")
            self._git(root, "add", "apps/live.py")
            self._git(root, "rm", "docs/remove_me.md", "cookies.txt")
            self._git(root, "commit", "-m", "delete tracked files")
            head = self._git(root, "rev-parse", "HEAD").stdout.strip()
            self.assertNotEqual(prior_head, head)

            result = self._run_range_init(root, base, head, exclude_docs=0, fixed_date_stamp="260502_2314")

            self.assertEqual(result.returncode, 0, result.stderr)
            plan_rel = result.stdout.strip()
            plan_path, draft_path = self._generated_paths(root, plan_rel)
            plan_text = plan_path.read_text(encoding="utf-8")
            meta = self._code_draft_meta(draft_path)
            self._assert_header_lines_have_no_trailing_whitespace(plan_path, draft_path)
            target_paths = {item["path"] for item in meta["targets"]}
            deleted_paths = {item["path"] for item in meta["deleted_paths"]}
            expected_review_artifact = f"docs/code_reviews/{plan_path.stem}.md"

            self.assertIn("apps/live.py", target_paths)
            self.assertNotIn("docs/remove_me.md", target_paths)
            self.assertNotIn("cookies.txt", target_paths)
            self.assertEqual({"docs/remove_me.md", "cookies.txt"}, deleted_paths)
            self.assertIn(f"- Code review (primary): `{expected_review_artifact}`", plan_text)
            ui_checklist = self._section_body(plan_text, "Acceptance criteria / DoD")
            self.assertIn("### UI contract checklist", ui_checklist)
            self.assertIn("review-only range scaffold", ui_checklist)

            review_path = root / expected_review_artifact
            review_path.parent.mkdir(parents=True, exist_ok=True)
            review_path.write_text("# Review\n\n**Status:** ✅ OK\n", encoding="utf-8")
            bundle = run_zsh_fixture(
                f"source {shlex.quote(str(PLANVEYOR_SCRIPT))} && planveyor_plan_bundle --check {plan_rel}",
                cwd=root,
                path=os.environ.get("PATH", os.defpath),
                pybin=str(Path(sys.executable).resolve()),
                fixture_env={"PLANVEYOR_ROOT": str(REPO_ROOT)},
                home=root / ".home",
                check=False,
            )
            self.assertEqual(bundle.returncode, 0, bundle.stderr + bundle.stdout)

    def test_first_pass_stays_explicitly_first_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            base, head = self._init_repo(root)

            result = self._run_range_init(root, base, head)

            self.assertEqual(result.returncode, 0, result.stderr)
            plan_rel = result.stdout.strip()
            plan_path, draft_path = self._generated_paths(root, plan_rel)
            self.assertTrue(plan_path.exists())
            self.assertTrue(draft_path.exists())

            plan_text = plan_path.read_text(encoding="utf-8")
            draft_text = draft_path.read_text(encoding="utf-8")

            self.assertIn("- Prior review / rerun artifacts: `N/A (first pass)`", plan_text)
            self.assertIn("- Rerun mode: `N/A (first pass)`", plan_text)
            self.assertIn("- Baseline artifact: `N/A (first pass)`", plan_text)
            self.assertNotIn("## Current-flow rerun lineage", draft_text)

    def test_first_pass_materializes_literal_provenance_and_non_applicable_carriers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            base, head = self._init_repo(root)

            result = self._run_range_init(root, base, head, fixed_date_stamp="260813_1917")

            self.assertEqual(result.returncode, 0, result.stderr)
            plan_rel = result.stdout.strip()
            plan_path, draft_path = self._generated_paths(root, plan_rel)
            plan_text = plan_path.read_text(encoding="utf-8")
            draft_text = draft_path.read_text(encoding="utf-8")
            plan_meta = self._plan_meta(plan_path)
            draft_meta = self._code_draft_meta(draft_path)
            expected_decision = {
                "schema_version": "machine_authority_decision.v1",
                "applicability": "not_applicable",
                "reason_code": "no_machine_authority_change",
            }
            self.assertIn("**Status:** Reviewer intake", plan_text)
            self.assertEqual(plan_meta["machine_authority_decision"], expected_decision)
            self.assertEqual(
                draft_meta["machine_authority_decision_ref"],
                {
                    "applicability": "not_applicable",
                    "reason_code": "no_machine_authority_change",
                    "carrier_sha256": PLAN_STATUS_ORACLE.machine_authority_decision_sha256(expected_decision),
                },
            )
            authority = PLAN_STATUS_ORACLE.machine_authority_decision_readback(plan_path)
            self.assertEqual(authority.state, "not_applicable")
            self.assertEqual(authority.ref_state, "valid")

            for residue in ("UUID/handle", "YYYY-MM-DDTHH:MM:SSZ", "UNCONFIRMED", "N/A (why) или"):
                self.assertNotIn(residue, plan_text)
                self.assertNotIn(residue, draft_text)

            plan_provenance = self._section_body(plan_text, "Plan provenance / session context")
            draft_provenance = self._section_body(draft_text, "Provenance / session context")
            self.assertIn("- Relation: `created-here`", plan_provenance)
            self.assertIn("- Thread ID: `", plan_provenance)
            self.assertIn("- Captured at: `", plan_provenance)
            self.assertIn(
                "- Source plan provenance: `reuse PLAN_PATH carrier unless this draft is created/imported/backfilled separately`",
                draft_provenance,
            )
            self.assertIn("- Relation: `created-here`", draft_provenance)

            self.assertIn(
                "- Role: `N/A (why=this review-only range scaffold does not emit cross-repo rollout packets)`",
                self._section_body(plan_text, "Rollout packet handoff"),
            )
            self.assertIn(
                "- Requested profile: `N/A (why=this scaffold does not request reduced same-session conveyor classification)`",
                self._section_body(plan_text, "Small-slice conveyor classifier"),
            )
            self.assertIn(
                "- `N/A (why=this review-only range scaffold does not materialize a queue carrier)`",
                self._section_body(plan_text, "Execution queue"),
            )
            self.assertIn(
                "- `N/A (why=this review-only range scaffold does not materialize a queue carrier)`",
                self._section_body(plan_text, "Queue close-out"),
            )
            self.assertIn(
                "`N/A (why=review-only range scaffold; not business decomposition)`",
                self._section_body(plan_text, "Business decomposition framing"),
            )
            child_plan_map = self._section_body(plan_text, "Child plan map")
            self.assertIn("| Queue order | Plan | Purpose | Input | Output | Consumer | Depends on | Dependency type | Acceptance/proof lane | Independent-stop reason |", child_plan_map)
            self.assertIn("| `N/A` | `N/A (why=not a decomposition wave)` |", child_plan_map)
            decomposition_gate = self._section_body(plan_text, "Decomposition quality gate")
            self.assertIn("- Solvability: `N/A (why=not a decomposition wave)`", decomposition_gate)
            self.assertIn("- Completeness: `N/A (why=not a decomposition wave)`", decomposition_gate)
            self.assertIn("- Non-redundancy: `N/A (why=not a decomposition wave)`", decomposition_gate)
            self.assertIn("- Mutable surface / runtime isolation: `N/A (why=not a decomposition wave)`", decomposition_gate)
            self.assertIn("- Recomposition / integration owner: `N/A (why=not a decomposition wave)`", decomposition_gate)
            self.assertIn(
                "- `N/A (why=review-only range scaffold; not a decomposition umbrella)`",
                self._section_body(plan_text, "Mechanism coverage"),
            )

            changes_body = self._section_body(plan_text, "Changes (by area)")
            self.assertIn(
                "- Data/schema (migrations if used): `N/A (why=review-only scaffold does not prescribe product-layer edits)`",
                changes_body,
            )
            self.assertIn(
                "- Logic/modules: `N/A (why=review-only scaffold does not prescribe product-layer edits)`",
                changes_body,
            )
            self.assertIn(
                "- Interfaces (API/CLI/UI): `N/A (why=review-only scaffold does not prescribe product-layer edits)`",
                changes_body,
            )
            self.assertIn(
                "- Config (keys/defaults): `N/A (why=review-only scaffold does not prescribe product-layer edits)`",
                changes_body,
            )

    def test_legacy_semantic_provenance_is_cross_seed_deterministic(self) -> None:
        """The source receipt must not churn when Python's hash seed changes."""

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            base, head = self._init_repo(root)
            first = self._run_range_init(
                root,
                base,
                head,
                fixed_date_stamp="260909_0001",
                extra_env={"PYTHONHASHSEED": "1"},
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            plan_rel = first.stdout.strip()
            plan_path, draft_path = self._generated_paths(root, plan_rel)
            first_plan_receipt = self._section_body(plan_path.read_text(encoding="utf-8"), "Review-range semantic provenance")
            first_draft_receipt = self._section_body(draft_path.read_text(encoding="utf-8"), "Review-range semantic provenance")
            self.assertEqual(first_plan_receipt, first_draft_receipt)
            first_payload = json.loads(first_plan_receipt.split("```json", 1)[1].split("```", 1)[0])
            self.assertEqual(
                first_payload["selected_rule_ids"],
                [
                    "fixed_dependent_test_map",
                    "legacy_profile_aware_generated_prose",
                    "provenance_rerun_and_lifecycle",
                    "range_and_artifact_core",
                    "review_only_mechanical_commands",
                    "visual_contract_parser_and_renderer",
                ],
            )

            plan_path.unlink()
            draft_path.unlink()
            shutil.rmtree(root / "docs" / "code_reviews" / "assets", ignore_errors=True)

            second = self._run_range_init(
                root,
                base,
                head,
                fixed_date_stamp="260909_0001",
                extra_env={"PYTHONHASHSEED": "2"},
            )
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(second.stdout.strip(), plan_rel)
            second_plan_path, second_draft_path = self._generated_paths(root, plan_rel)
            second_plan_receipt = self._section_body(second_plan_path.read_text(encoding="utf-8"), "Review-range semantic provenance")
            second_draft_receipt = self._section_body(second_draft_path.read_text(encoding="utf-8"), "Review-range semantic provenance")
            self.assertEqual(second_plan_receipt, first_plan_receipt)
            self.assertEqual(second_draft_receipt, first_draft_receipt)

            second_plan_path.unlink()
            second_draft_path.unlink()
            shutil.rmtree(root / "docs" / "code_reviews" / "assets", ignore_errors=True)
            third = self._run_range_init(
                root,
                base,
                head,
                fixed_date_stamp="260909_0001",
                extra_env={"PYTHONHASHSEED": "3"},
            )
            self.assertEqual(third.returncode, 0, third.stderr)
            self.assertEqual(third.stdout.strip(), plan_rel)
            third_plan_path, third_draft_path = self._generated_paths(root, plan_rel)
            self.assertEqual(
                self._section_body(third_plan_path.read_text(encoding="utf-8"), "Review-range semantic provenance"),
                first_plan_receipt,
            )
            self.assertEqual(
                self._section_body(third_draft_path.read_text(encoding="utf-8"), "Review-range semantic provenance"),
                first_draft_receipt,
            )

    def test_same_tuple_reuse_preserves_bytes_after_clock_advances(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            base, head = self._init_repo(root)
            first = self._run_range_init(root, base, head, fixed_date_stamp="260909_0103")
            self.assertEqual(first.returncode, 0, first.stderr)
            plan_rel = first.stdout.strip()
            plan_path, draft_path = self._generated_paths(root, plan_rel)
            before = (plan_path.read_bytes(), draft_path.read_bytes())

            time.sleep(1.1)
            second = self._run_range_init(root, base, head, fixed_date_stamp="260909_0104")
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(second.stdout.strip(), plan_rel)
            self.assertEqual((plan_path.read_bytes(), draft_path.read_bytes()), before)

    def test_engaged_semantic_provenance_deduplicates_declared_rule_ids_in_order(self) -> None:
        import review_range_scaffold_engine as engine

        context = SimpleNamespace(
            runtime_pin=None,
            behavior_identity="planveyor",
            marker=SimpleNamespace(repository_id="planveyor"),
            generation_sha256="0" * 64,
        )
        policy = {
            "corpus_rule": "planveyor.v1",
            "visual_rule": "planveyor.v1",
            "render_profile": "planveyor.review_only.v1",
        }
        receipt = engine._semantic_receipt(
            context=context,
            state="engaged",
            input_rows=(),
            policy=policy,
            plan_ref="docs/plans/fixture.md",
            draft_ref="docs/code_drafts/fixture__code_draft.md",
            materialization={"mode": "inline", "markdown": "fixture"},
        )

        self.assertEqual(
            receipt["selected_rule_ids"],
            ["planveyor.v1", "planveyor.review_only.v1"],
        )
        self.assertEqual(
            [row["rule_ids"] for row in receipt["outputs"]],
            [["planveyor.v1", "planveyor.review_only.v1"], ["planveyor.v1", "planveyor.review_only.v1"]],
        )

    def test_review_range_policy_duplicate_key_is_rejected_before_policy_selection(self) -> None:
        import review_range_scaffold_engine as engine

        with self.assertRaises(engine.EngineError) as rejected:
            engine._strict_json(
                b'{"schema_version":"review_range_policy.v1","schema_version":"shadow"}',
                label="review_range_policy.v1",
            )
        self.assertEqual(rejected.exception.code, "duplicate_policy_key")

    def test_review_artifact_provenance_readback_accepts_matching_range_and_rejects_drift(self) -> None:
        import review_artifact_lint

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            base, head = self._init_repo(root)
            scaffold = self._run_range_init(root, base, head, fixed_date_stamp="260909_0102")
            self.assertEqual(scaffold.returncode, 0, scaffold.stderr)
            plan_rel = scaffold.stdout.strip()
            review_rel = f"docs/code_reviews/{Path(plan_rel).stem}.md"
            review_path = root / review_rel
            review_path.parent.mkdir(parents=True, exist_ok=True)
            matching = (
                "# Code review\n\n"
                f"**Spec:** `{plan_rel}`\n"
                f"**Target:** `RANGE={base}..{head} (EXCLUDE_DOCS=0)`\n"
            )
            review_path.write_text(matching, encoding="utf-8")

            self.assertEqual(
                review_artifact_lint.evaluate_review_range_semantic_provenance(
                    project_root=root,
                    review_path=review_path,
                    origin_plan=plan_rel,
                    review_text=matching,
                ),
                (),
            )
            drifted = matching.replace(head, "0" * 40)
            self.assertEqual(
                review_artifact_lint.evaluate_review_range_semantic_provenance(
                    project_root=root,
                    review_path=review_path,
                    origin_plan=plan_rel,
                    review_text=drifted,
                ),
                ("review_range_provenance_range_mismatch",),
            )

    def test_incremental_rerun_materializes_identical_lineage_in_plan_and_code_draft(self) -> None:
        baseline_artifact = "docs/code_reviews/260325_1052_reviewer_range_dddd444_eeee555.md"
        prior_artifact = "docs/doc_reviews/260325_1101_process_merge_range_diff_check_followup.md"

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            base, head = self._init_repo(root)
            (root / baseline_artifact).parent.mkdir(parents=True, exist_ok=True)
            (root / baseline_artifact).write_text("# baseline\n", encoding="utf-8")
            (root / prior_artifact).parent.mkdir(parents=True, exist_ok=True)
            (root / prior_artifact).write_text("# follow-up\n", encoding="utf-8")

            result = self._run_range_init(
                root,
                base,
                head,
                extra_env={
                    "PLANVEYOR_REVIEW_RERUN_MODE": "incremental",
                    "PLANVEYOR_REVIEW_BASELINE_ARTIFACT": baseline_artifact,
                    "PLANVEYOR_REVIEW_PRIOR_ARTIFACTS": f"{baseline_artifact}|{prior_artifact}",
                },
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            plan_rel = result.stdout.strip()
            plan_path, draft_path = self._generated_paths(root, plan_rel)
            plan_text = plan_path.read_text(encoding="utf-8")
            draft_text = draft_path.read_text(encoding="utf-8")

            expected_prior_line = (
                "- Prior review / rerun artifacts: "
                f"`{baseline_artifact}`, `{prior_artifact}`"
            )
            self.assertIn(expected_prior_line, plan_text)
            self.assertIn("- Rerun mode: `incremental`", plan_text)
            self.assertIn(f"- Baseline artifact: `{baseline_artifact}`", plan_text)
            self.assertIn("- Rerun scope: `current blocker-fix pass for RANGE=", plan_text)

            self.assertIn("## Current-flow rerun lineage", draft_text)
            self.assertIn(expected_prior_line, draft_text)
            self.assertIn("- Rerun mode: `incremental`", draft_text)
            self.assertIn(f"- Baseline artifact: `{baseline_artifact}`", draft_text)
            self.assertIn(
                "- Carrier source: explicit env (`PLANVEYOR_REVIEW_RERUN_MODE`, "
                "`PLANVEYOR_REVIEW_BASELINE_ARTIFACT`, `PLANVEYOR_REVIEW_PRIOR_ARTIFACTS`); no git-history inference.",
                draft_text,
            )

    def test_partial_rerun_carrier_fails_before_scaffold_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            base, head = self._init_repo(root)

            result = self._run_range_init(
                root,
                base,
                head,
                extra_env={"PLANVEYOR_REVIEW_RERUN_MODE": "incremental"},
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("PLANVEYOR_REVIEW_BASELINE_ARTIFACT is required", result.stderr)
            self.assertEqual(list((root / "docs" / "plans").glob("*_reviewer_range_*.md")), [])
            self.assertEqual(list((root / "docs" / "code_drafts").glob("*_reviewer_range_*__code_draft.md")), [])

    def test_same_range_reuses_existing_plan_across_different_timestamps_and_keeps_plan_log_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            base, head = self._init_repo(root)

            first = self._run_range_init(root, base, head, fixed_date_stamp="260325_2234")
            self.assertEqual(first.returncode, 0, first.stderr)
            first_plan_rel = first.stdout.strip()

            second = self._run_range_init(root, base, head, fixed_date_stamp="260325_2235")
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(second.stdout.strip(), first_plan_rel)

            plan_path, _ = self._generated_paths(root, first_plan_rel)
            plan_text = plan_path.read_text(encoding="utf-8")
            self.assertIn("- Repo profile: `planveyor`", plan_text)

            self.assertEqual(self._plan_log_paths(root), [first_plan_rel])
            self.assertEqual((root / ".planveyor.planpath").read_text(encoding="utf-8").splitlines()[-1], first_plan_rel)

    def test_force_new_creates_second_artifact_even_with_same_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            base, head = self._init_repo(root)

            first = self._run_range_init(root, base, head, fixed_date_stamp="260325_2234")
            self.assertEqual(first.returncode, 0, first.stderr)
            first_plan_rel = first.stdout.strip()

            second = self._run_range_init(
                root,
                base,
                head,
                fixed_date_stamp="260325_2234",
                force_new=True,
            )
            self.assertEqual(second.returncode, 0, second.stderr)
            second_plan_rel = second.stdout.strip()

            self.assertNotEqual(second_plan_rel, first_plan_rel)
            self.assertTrue(second_plan_rel.endswith("_2.md"), second_plan_rel)
            self.assertEqual(self._plan_log_paths(root), [first_plan_rel, second_plan_rel])

    def test_self_runtime_generated_review_sources_keep_generic_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            base, head = self._init_repo(root)

            result = self._run_range_init(root, base, head, fixed_date_stamp="260906_0400")

            self.assertEqual(result.returncode, 0, result.stderr)
            plan_path, _ = self._generated_paths(root, result.stdout.strip())
            plan_text = plan_path.read_text(encoding="utf-8")
            context_heading = "**Context links (source of truth):**"
            context = plan_text.split(context_heading, 1)[1].split("\n## Meta", 1)[0]
            reviewer_ref, scoping_ref, merge_ref = self._generic_review_source_refs()
            retired_reviewer_ref, _, _ = self._retired_review_source_refs()
            tick = chr(96)

            self.assertIn(f"- Repo profile: {tick}planveyor{tick}", plan_text)
            self.assertEqual(context.count("- Reviewer role:"), 1)
            self.assertEqual(context.count("- Shared playbooks:"), 1)
            self.assertIn(f"- Reviewer role: {tick}{reviewer_ref}{tick}", context)
            self.assertIn(f"  - {tick}{scoping_ref}{tick}", context)
            self.assertIn(f"  - {tick}{merge_ref}{tick}", context)
            self.assertNotIn(f"- Reviewer role: {tick}{retired_reviewer_ref}{tick}", context)

    def test_self_runtime_reuse_rejects_historical_root_context_sources_and_preserves_artifacts(self) -> None:
        reviewer_ref, scoping_ref, merge_ref = self._generic_review_source_refs()
        historical_refs = self._retired_review_source_refs()

        for tagged in (True, False):
            with self.subTest(tagged=tagged), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                base, head = self._init_repo(root)
                first = self._run_range_init(root, base, head, fixed_date_stamp="260906_0400")
                self.assertEqual(first.returncode, 0, first.stderr)
                old_rel = first.stdout.strip()
                old_plan, old_draft = self._generated_paths(root, old_rel)
                old_text = old_plan.read_text(encoding="utf-8")
                for generic_ref, historical_ref in zip(
                    (reviewer_ref, scoping_ref, merge_ref),
                    historical_refs,
                    strict=True,
                ):
                    old_text = old_text.replace(generic_ref, historical_ref)
                if not tagged:
                    tick = chr(96)
                    old_text = old_text.replace(f"- Repo profile: {tick}planveyor{tick}\n", "")
                old_plan.write_text(old_text, encoding="utf-8")
                old_review = root / "docs" / "code_reviews" / old_plan.name
                old_review.parent.mkdir(exist_ok=True)
                old_review.write_text("Historical completed review: preserve exact bytes.\n", encoding="utf-8")
                preserved = {
                    str(path.relative_to(root)): path.read_bytes()
                    for path in (old_plan, old_draft, old_review)
                }

                second = self._run_range_init(root, base, head, fixed_date_stamp="260906_0400")

                self.assertEqual(second.returncode, 0, second.stderr)
                new_rel = second.stdout.strip()
                self.assertNotEqual(new_rel, old_rel)
                self.assertTrue(new_rel.endswith("_2.md"), new_rel)
                for relative, content in preserved.items():
                    self.assertEqual((root / relative).read_bytes(), content, relative)
                new_text = (root / new_rel).read_text(encoding="utf-8")
                tick = chr(96)
                self.assertIn(f"- Repo profile: {tick}planveyor{tick}", new_text)
                self.assertIn(f"- Reviewer role: {tick}{reviewer_ref}{tick}", new_text)

                third = self._run_range_init(root, base, head, fixed_date_stamp="260906_0401")
                self.assertEqual(third.returncode, 0, third.stderr)
                self.assertEqual(third.stdout.strip(), new_rel)

    def test_default_context_source_freshness_precedes_visual_contract_exception(self) -> None:
        reviewer_ref, scoping_ref, merge_ref = self._generic_review_source_refs()
        historical_reviewer_ref, historical_scoping_ref, historical_merge_ref = self._retired_review_source_refs()
        tick = chr(96)
        expected_refs = {
            "reviewer": reviewer_ref,
            "scoping": scoping_ref,
            "merge": merge_ref,
        }
        historical_refs = {
            "reviewer": historical_reviewer_ref,
            "scoping": historical_scoping_ref,
            "merge": historical_merge_ref,
        }
        for fixture in (
            "missing_reviewer",
            "missing_scoping",
            "missing_merge",
            "wrong_reviewer",
            "wrong_scoping",
            "wrong_merge",
            "duplicate_reviewer",
            "duplicate_scoping",
            "duplicate_merge",
            "blank_separated_duplicate_scoping",
            "malformed_duplicate_reviewer_label",
            "malformed_duplicate_shared_playbooks_label",
            "multiple_context_blocks",
        ):
            with self.subTest(fixture=fixture), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                base, head = self._init_repo(root)
                first = self._run_range_init(root, base, head, fixed_date_stamp="260906_0400")
                self.assertEqual(first.returncode, 0, first.stderr)
                old_rel = first.stdout.strip()
                old_plan, _ = self._generated_paths(root, old_rel)
                original = old_plan.read_text(encoding="utf-8")
                canonical_lines = {
                    "reviewer": f"- Reviewer role: {tick}{reviewer_ref}{tick}\n",
                    "scoping": f"  - {tick}{scoping_ref}{tick}\n",
                    "merge": f"  - {tick}{merge_ref}{tick}\n",
                }

                if fixture.startswith("missing_"):
                    source_name = fixture.removeprefix("missing_")
                    tampered = original.replace(canonical_lines[source_name], "", 1)
                elif fixture.startswith("wrong_"):
                    source_name = fixture.removeprefix("wrong_")
                    tampered = original.replace(
                        canonical_lines[source_name],
                        canonical_lines[source_name].replace(
                            expected_refs[source_name],
                            historical_refs[source_name],
                        ),
                        1,
                    )
                elif fixture.startswith("duplicate_"):
                    source_name = fixture.removeprefix("duplicate_")
                    tampered = original.replace(
                        canonical_lines[source_name],
                        canonical_lines[source_name] + canonical_lines[source_name],
                        1,
                    )
                elif fixture == "blank_separated_duplicate_scoping":
                    tampered = original.replace(
                        canonical_lines["scoping"],
                        canonical_lines["scoping"] + "\n" + canonical_lines["scoping"],
                        1,
                    )
                elif fixture == "malformed_duplicate_reviewer_label":
                    tampered = original.replace(
                        canonical_lines["reviewer"],
                        canonical_lines["reviewer"]
                        + f"- Reviewer role malformed {tick}{historical_refs['reviewer']}{tick}\n",
                        1,
                    )
                elif fixture == "malformed_duplicate_shared_playbooks_label":
                    tampered = original.replace(
                        canonical_lines["merge"],
                        canonical_lines["merge"] + "- Shared playbooks malformed\n",
                        1,
                    )
                elif fixture == "multiple_context_blocks":
                    tampered = original + (
                        "\n**Context links (source of truth):**\n"
                        f"- Reviewer role: {tick}{reviewer_ref}{tick}\n"
                        "- Shared playbooks:\n"
                        f"  - {tick}{scoping_ref}{tick}\n"
                        f"  - {tick}{merge_ref}{tick}\n"
                    )
                else:
                    self.fail(f"unknown context-source fixture: {fixture}")

                self.assertNotEqual(tampered, original)
                correct_target = f"- Review target: {tick}RANGE={base}..{head} (EXCLUDE_DOCS=0){tick}"
                self.assertIn(correct_target, tampered)
                tampered = tampered.replace(
                    correct_target,
                    f"- Review target: RANGE={base}..{head} (EXCLUDE_DOCS=0)",
                    1,
                )
                tampered += '\n<!-- "schema_version": "review_visual_lane_contract_ref.v1" -->\n'
                tampered_bytes = tampered.encode("utf-8")
                old_plan.write_bytes(tampered_bytes)

                second = self._run_range_init(root, base, head, fixed_date_stamp="260906_0400")

                self.assertEqual(second.returncode, 0, second.stderr)
                self.assertNotEqual(second.stdout.strip(), old_rel)
                self.assertTrue(second.stdout.strip().endswith("_2.md"), second.stdout)
                self.assertEqual(old_plan.read_bytes(), tampered_bytes)
                self.assertTrue((root / second.stdout.strip()).is_file())

    def test_default_context_source_freshness_ignores_noise_outside_context_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            base, head = self._init_repo(root)
            first = self._run_range_init(root, base, head, fixed_date_stamp="260906_0400")
            self.assertEqual(first.returncode, 0, first.stderr)
            plan_rel = first.stdout.strip()
            plan_path, _ = self._generated_paths(root, plan_rel)
            tick = chr(96)
            noise = (
                "\n## Historical notes\n"
                f"- Reviewer role: {tick}docs/roles/reviewer.md{tick}\n"
                "- Shared playbooks:\n"
                f"  - {tick}docs/playbooks/review_scoping_plan.md{tick}\n"
                f"  - {tick}docs/playbooks/review_merge_range.md{tick}\n"
            )
            plan_path.write_text(plan_path.read_text(encoding="utf-8") + noise, encoding="utf-8")

            second = self._run_range_init(root, base, head, fixed_date_stamp="260906_0401")

            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(second.stdout.strip(), plan_rel)

    def test_generic_named_planveyor_review_reuse_checks_root_context_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "planveyor"
            root.mkdir()
            base, head = self._init_repo(root)
            first = self._run_range_init(
                root,
                base,
                head,
                fixed_date_stamp="260906_0400",
                runtime_facade=PLANVEYOR_SCRIPT,
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            plan_rel = first.stdout.strip()
            plan_path, _ = self._generated_paths(root, plan_rel)
            self.assertIn("- Repo profile: `default`", plan_path.read_text(encoding="utf-8"))
            plan_text = plan_path.read_text(encoding="utf-8")
            tampered = re.sub(
                r"^- Reviewer role: .*\n",
                "",
                plan_text,
                count=1,
                flags=re.MULTILINE,
            )
            self.assertNotEqual(tampered, plan_text)
            plan_path.write_text(tampered, encoding="utf-8")

            second = self._run_range_init(
                root,
                base,
                head,
                fixed_date_stamp="260906_0401",
                runtime_facade=PLANVEYOR_SCRIPT,
            )

            self.assertEqual(second.returncode, 0, second.stderr)
            second_rel = second.stdout.strip()
            self.assertNotEqual(second_rel, plan_rel)
            self.assertTrue((root / second_rel).is_file())
            self.assertEqual(plan_path.read_text(encoding="utf-8"), tampered)
            self.assertIn("- Repo profile: `default`", (root / second_rel).read_text(encoding="utf-8"))

    def test_explicit_planveyor_does_not_reuse_or_mutate_legacy_review_artifacts(self) -> None:
        for tagged in (True, False):
            with self.subTest(tagged=tagged), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir) / "legacy"
                root.mkdir()
                base, head = self._init_repo(root)
                first = self._run_range_engine(
                    root, base, head, content_profile_id="default", fixed_date_stamp="260906_0400"
                )
                self.assertEqual(first.returncode, 0, first.stderr)
                old_rel = first.stdout.strip()
                old_plan, old_draft = self._generated_paths(root, old_rel)
                if not tagged:
                    old_plan.write_text(old_plan.read_text().replace("- Repo profile: `default`\n", ""))
                old_review = root / "docs/code_reviews" / old_plan.name
                old_review.parent.mkdir(exist_ok=True)
                old_review.write_text("Historical completed review: preserve exact bytes.\n")
                preserved = {str(path.relative_to(root)): path.read_bytes()
                             for path in (old_plan, old_draft, old_review)}
                second = self._run_range_engine(
                    root, base, head, content_profile_id="planveyor", fixed_date_stamp="260906_0400"
                )
                self.assertEqual(second.returncode, 0, second.stderr)
                new_rel = second.stdout.strip()
                self.assertNotEqual(new_rel, old_rel)
                self.assertTrue(new_rel.endswith("_2.md"), new_rel)
                for relative, content in preserved.items():
                    self.assertEqual((root / relative).read_bytes(), content, relative)
                text = (root / new_rel).read_text()
                self.assertIn("- Repo profile: `planveyor`", text)
                self.assertIn("docs/roles/reviewer.md", text)
                self.assertIn("docs/playbooks/review_merge_range.md", text)
                third = self._run_range_engine(
                    root, base, head, content_profile_id="planveyor", fixed_date_stamp="260906_0401"
                )
                self.assertEqual(third.returncode, 0, third.stderr)
                self.assertEqual(third.stdout.strip(), new_rel)

    def test_untagged_explicit_planveyor_review_plan_does_not_reuse_profiled_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "legacy"
            root.mkdir()
            base, head = self._init_repo(root)
            first = self._run_range_engine(
                root, base, head, content_profile_id="planveyor", fixed_date_stamp="260906_0400"
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            plan_rel = first.stdout.strip()
            plan = root / plan_rel
            untagged = plan.read_text(encoding="utf-8").replace("- Repo profile: `planveyor`\n", "")
            self.assertNotEqual(untagged, plan.read_text(encoding="utf-8"))
            plan.write_text(untagged, encoding="utf-8")
            second = self._run_range_engine(
                root, base, head, content_profile_id="planveyor", fixed_date_stamp="260906_0401"
            )
            self.assertEqual(second.returncode, 0, second.stderr)
            second_rel = second.stdout.strip()
            self.assertNotEqual(second_rel, plan_rel)
            self.assertTrue((root / second_rel).is_file())
            self.assertEqual(plan.read_text(encoding="utf-8"), untagged)
            self.assertIn("- Repo profile: `planveyor`", (root / second_rel).read_text(encoding="utf-8"))

    def test_legacy_generic_named_planveyor_uses_root_sources_without_implicit_visual_lane(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "planveyor"
            root.mkdir()
            _, base = self._init_repo(root)
            comparator = "./scripts/run_visual_check.sh --run-id review --repeat 2 --logs-dir .tmp/visual-regression/logs"
            human = [f"./scripts/review_visual_design_audit.sh --mode {mode} --plan docs/plans/<plan>.md --port {port} --assets-dir .tmp/human-visual-review/{mode}"
                     for mode, port in (("primary", 8073), ("secondary", 8074))]
            source = "\n".join([
                "<!-- verification-receipt lane=visual.check_1 lane=visual.check_2 lane=vis.human_visual_review_local -->",
                "```bash", comparator, *human, "```", ""])
            head = self._write_multi_commit(root, {
                "templates/dashboard.html": "<div>dashboard</div>\n",
                "scripts/run_visual_check.sh": "#!/bin/sh\n",
                "scripts/review_visual_design_audit.sh": "#!/bin/sh\n",
                "docs/smoke_visual.md": source,
                "docs/testing_runbook.md": source,
            }, "visual fixture", executable_paths=("scripts/run_visual_check.sh", "scripts/review_visual_design_audit.sh"))
            result = self._run_range_engine(
                root, base, head, content_profile_id="default", fixed_date_stamp="260906_0400"
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            plan_rel = result.stdout.strip()
            text = (root / plan_rel).read_text()
            self.assertIn("- Repo profile: `default`", text)
            self.assertIn('"profile_id": "default"', text)
            self.assertIn('"availability_state": "not_applicable"', text)
            self.assertIn("no_declared_runtime_visual_lane:default", text)
            self.assertIn("docs/roles/reviewer.md", text)
            self.assertIn("docs/playbooks/review_merge_range.md", text)
            self.assertNotIn(comparator, text)
            self.assertNotIn(human[0].replace("docs/plans/<plan>.md", plan_rel), text)
            lint = self._run_plan_lint(root, plan_rel)
            self.assertEqual(lint.returncode, 0, lint.stdout + lint.stderr)

    def test_default_rerun_after_force_new_returns_to_canonical_first_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            base, head = self._init_repo(root)

            first = self._run_range_init(root, base, head, fixed_date_stamp="260325_2234")
            self.assertEqual(first.returncode, 0, first.stderr)
            first_plan_rel = first.stdout.strip()

            second = self._run_range_init(
                root,
                base,
                head,
                fixed_date_stamp="260325_2235",
                force_new=True,
            )
            self.assertEqual(second.returncode, 0, second.stderr)
            second_plan_rel = second.stdout.strip()
            self.assertNotEqual(second_plan_rel, first_plan_rel)

            third = self._run_range_init(root, base, head, fixed_date_stamp="260325_2236")
            self.assertEqual(third.returncode, 0, third.stderr)
            self.assertEqual(third.stdout.strip(), first_plan_rel)

            self.assertEqual(self._plan_log_paths(root), [first_plan_rel, second_plan_rel, first_plan_rel])
            self.assertEqual((root / ".planveyor.planpath").read_text(encoding="utf-8").splitlines()[-1], first_plan_rel)

    def test_same_path_replay_refreshes_code_draft_for_rerun_and_back_to_first_pass(self) -> None:
        baseline_artifact = "docs/code_reviews/base.md"
        prior_artifact = "docs/code_reviews/prior.md"

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            base, head = self._init_repo(root)
            (root / baseline_artifact).parent.mkdir(parents=True, exist_ok=True)
            (root / baseline_artifact).write_text("# baseline\n", encoding="utf-8")
            (root / prior_artifact).parent.mkdir(parents=True, exist_ok=True)
            (root / prior_artifact).write_text("# prior\n", encoding="utf-8")

            first = self._run_range_init(root, base, head, fixed_date_stamp="260325_2234")
            self.assertEqual(first.returncode, 0, first.stderr)
            first_plan_rel = first.stdout.strip()
            plan_path, draft_path = self._generated_paths(root, first_plan_rel)
            draft_text = draft_path.read_text(encoding="utf-8")
            self.assertNotIn("## Current-flow rerun lineage", draft_text)

            second = self._run_range_init(
                root,
                base,
                head,
                fixed_date_stamp="260325_2235",
                extra_env={
                    "PLANVEYOR_REVIEW_RERUN_MODE": "incremental",
                    "PLANVEYOR_REVIEW_BASELINE_ARTIFACT": baseline_artifact,
                    "PLANVEYOR_REVIEW_PRIOR_ARTIFACTS": f"{baseline_artifact}|{prior_artifact}",
                },
            )
            self.assertEqual(second.returncode, 0, second.stderr)
            second_plan_rel = second.stdout.strip()
            self.assertNotEqual(second_plan_rel, first_plan_rel)
            plan_path, draft_path = self._generated_paths(root, second_plan_rel)
            plan_text = plan_path.read_text(encoding="utf-8")
            draft_text = draft_path.read_text(encoding="utf-8")
            self.assertIn("- Rerun mode: `incremental`", plan_text)
            self.assertIn("## Current-flow rerun lineage", draft_text)
            self.assertIn(f"- Baseline artifact: `{baseline_artifact}`", draft_text)

            third = self._run_range_init(root, base, head, fixed_date_stamp="260325_2236")
            self.assertEqual(third.returncode, 0, third.stderr)
            self.assertEqual(third.stdout.strip(), first_plan_rel)
            plan_path, draft_path = self._generated_paths(root, first_plan_rel)
            plan_text = plan_path.read_text(encoding="utf-8")
            draft_text = draft_path.read_text(encoding="utf-8")
            self.assertIn("- Rerun mode: `N/A (first pass)`", plan_text)
            self.assertNotIn("## Current-flow rerun lineage", draft_text)
            self.assertEqual(self._plan_log_paths(root), [first_plan_rel, second_plan_rel, first_plan_rel])

    def test_exclude_docs_change_creates_fresh_artifact_and_reuses_matching_tuple(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _, base = self._init_repo(root)
            head = self._write_multi_commit(
                root,
                {
                    "apps/example.py": "VALUE = 3\n",
                    "docs/guides/mixed.md": "# mixed\n",
                },
                "mixed range",
            )

            first = self._run_range_init(root, base, head, exclude_docs=0, fixed_date_stamp="260325_2300")
            self.assertEqual(first.returncode, 0, first.stderr)
            first_plan_rel = first.stdout.strip()

            second = self._run_range_init(root, base, head, exclude_docs=1, fixed_date_stamp="260325_2301")
            self.assertEqual(second.returncode, 0, second.stderr)
            second_plan_rel = second.stdout.strip()
            self.assertNotEqual(second_plan_rel, first_plan_rel)

            third = self._run_range_init(root, base, head, exclude_docs=0, fixed_date_stamp="260325_2302")
            self.assertEqual(third.returncode, 0, third.stderr)
            self.assertEqual(third.stdout.strip(), first_plan_rel)

    def test_legacy_runtime_ui_has_no_native_or_browser_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "consumer-fixture"
            root.mkdir(parents=True, exist_ok=True)
            _, base = self._init_repo(root)
            head = self._write_commit(
                root,
                "apps/ui/ReviewWindow.html",
                "<main>review</main>\n",
                "runtime surface",
            )

            result = self._run_range_init(root, base, head)

            self.assertEqual(result.returncode, 0, result.stderr)
            plan_rel = result.stdout.strip()
            plan_path, draft_path = self._generated_paths(root, plan_rel)
            self.assertTrue(plan_path.exists())
            self.assertTrue(draft_path.exists())

            plan_text = plan_path.read_text(encoding="utf-8")

            self.assertIn('"availability_state": "not_applicable"', plan_text)
            self.assertIn("no_declared_runtime_visual_lane:planveyor", plan_text)
            self.assertIn("no declared applicable visual carrier", plan_text)
            self.assertNotIn("Review helper:", plan_text)
            self.assertNotIn("Capture:", plan_text)
            self.assertNotIn("Modes to test: `primary + secondary`", plan_text)

    def test_commitish_inputs_normalize_to_full_lowercase_review_target_identity(self) -> None:
        for index, (case, base_input, head_input) in enumerate((
            ("short", lambda base, _head: base[:7], lambda _base, head: head[:7]),
            ("uppercase", lambda base, _head: base.upper(), lambda _base, head: head.upper()),
            ("symbolic", lambda _base, _head: "HEAD~1", lambda _base, _head: "HEAD"),
        )):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                base, head = self._init_repo(root)

                result = self._run_range_init(
                    root,
                    base_input(base, head),
                    head_input(base, head),
                    exclude_docs=0,
                    fixed_date_stamp=f"260830_16{index}0",
                )

                self.assertEqual(result.returncode, 0, result.stderr)
                plan_rel = result.stdout.strip()
                plan_path, draft_path = self._generated_paths(root, plan_rel)
                review_target = f"RANGE={base}..{head} (EXCLUDE_DOCS=0)"
                plan_text = plan_path.read_text(encoding="utf-8")
                draft_text = draft_path.read_text(encoding="utf-8")
                self.assertIn(f"Review target: `{review_target}`", plan_text)
                self.assertIn(f"Review target: `{review_target}`", draft_text)

                materialization, errors = REVIEW_VISUAL_LANE_CONTRACT.parse_materialized_contract(
                    plan_text,
                    project_root=root,
                    expected_plan_ref=plan_rel,
                    require_review_target_identity=True,
                )
                self.assertEqual(errors, [])
                self.assertIsNotNone(materialization)
                self.assertEqual(
                    REVIEW_VISUAL_LANE_CONTRACT.review_target_identity(plan_text),
                    (base, head, 0),
                )

    def test_large_docs_external_to_inline_refuses_before_rewrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            base, _head = self._init_repo(root)
            head = self._write_multi_commit(
                root,
                {
                    f"docs/w4_generated_{index:04d}.md": f"# generated {index}\n"
                    for index in range(940)
                },
                "W4 doc-heavy external range",
            )
            first = self._run_range_init(
                root, base, head, exclude_docs=0, fixed_date_stamp="260911_0400"
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            plan_rel = first.stdout.strip()
            plan_path, draft_path = self._generated_paths(root, plan_rel)
            first_plan = plan_path.read_text(encoding="utf-8")
            refs, ref_errors = REVIEW_VISUAL_LANE_CONTRACT.referenced_full_payload_refs(first_plan)
            self.assertEqual(ref_errors, ())
            self.assertEqual(len(refs), 1)
            self.assertIn("review_visual_lane_contract_ref.v1", first_plan)
            support_path = root / refs[0]
            self.assertTrue(support_path.is_file())

            requested_payload = REVIEW_VISUAL_LANE_CONTRACT.discover_review_visual_lane(
                project_root=root,
                profile_id="default",
                changed_entries=REVIEW_VISUAL_LANE_CONTRACT.git_changed_entries(root, base, head),
                exclude_docs=True,
                review_basename=Path(plan_rel).stem,
                plan_ref=plan_rel,
            )
            requested = REVIEW_VISUAL_LANE_CONTRACT.prepare_materialized_contract(
                requested_payload,
                base=base,
                head=head,
                exclude_docs=1,
                plan_ref=plan_rel,
                review_artifact_ref=f"docs/code_reviews/{Path(plan_rel).stem}.md",
            )
            self.assertEqual(requested["mode"], "inline")
            before = (plan_path.read_bytes(), draft_path.read_bytes(), support_path.read_bytes())
            plans_before = sorted(
                (root / "docs" / "plans").glob(f"*_reviewer_range_{base[:7]}_{head[:7]}*.md")
            )
            drafts_before = sorted(
                (root / "docs" / "code_drafts").glob(
                    f"*_reviewer_range_{base[:7]}_{head[:7]}*__code_draft.md"
                )
            )
            supports_before = sorted(
                (root / "docs" / "code_reviews").glob(
                    "assets/*/review_visual_lane_contract.v2.json"
                )
            )

            second = self._run_range_init(
                root, base, head, exclude_docs=1, fixed_date_stamp="260911_0401"
            )

            self.assertNotEqual(second.returncode, 0, second.stderr)
            self.assertEqual(second.stdout, "")
            self.assertIn("publication_conflict", second.stderr)
            self.assertEqual(
                (plan_path.read_bytes(), draft_path.read_bytes(), support_path.read_bytes()),
                before,
            )
            self.assertEqual(
                sorted((root / "docs" / "plans").glob(f"*_reviewer_range_{base[:7]}_{head[:7]}*.md")),
                plans_before,
            )
            self.assertEqual(
                sorted((root / "docs" / "code_drafts").glob(
                    f"*_reviewer_range_{base[:7]}_{head[:7]}*__code_draft.md"
                )),
                drafts_before,
            )
            self.assertEqual(
                sorted((root / "docs" / "code_reviews").glob(
                    "assets/*/review_visual_lane_contract.v2.json"
                )),
                supports_before,
            )

    def test_large_range_uses_external_ref_and_reuses_exact_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            base, _head = self._init_repo(root)
            head = self._write_multi_commit(
                root,
                {f"apps/generated_{index:04d}.py": f"VALUE = {index}\n" for index in range(940)},
                "large generated range",
            )

            first = self._run_range_init(root, base, head, exclude_docs=0, fixed_date_stamp="260830_1600")
            self.assertEqual(first.returncode, 0, first.stderr)
            plan_rel = first.stdout.strip()
            plan_path, draft_path = self._generated_paths(root, plan_rel)
            plan_text = plan_path.read_text(encoding="utf-8")
            draft_text = draft_path.read_text(encoding="utf-8")
            refs, ref_errors = REVIEW_VISUAL_LANE_CONTRACT.referenced_full_payload_refs(plan_text)
            self.assertEqual(ref_errors, ())
            self.assertEqual(len(refs), 1)
            self.assertIn("review_visual_lane_contract_ref.v1", plan_text)
            self.assertIn("review_visual_lane_contract_ref.v1", draft_text)
            self.assertNotIn('"changed_path_evidence":', plan_text)
            support_path = root / refs[0]
            self.assertTrue(support_path.is_file())
            payload, errors = REVIEW_VISUAL_LANE_CONTRACT.parse_materialized_contract(
                plan_text,
                project_root=root,
                expected_plan_ref=plan_rel,
            )
            self.assertEqual(errors, [])
            self.assertIsNotNone(payload)
            self.assertGreaterEqual(len(payload["changed_path_evidence"]), 940)
            self.assertEqual(self._run_plan_lint(root, plan_rel).returncode, 0)

            before = (plan_path.read_bytes(), draft_path.read_bytes(), support_path.read_bytes())
            second = self._run_range_init(root, base, head, exclude_docs=0, fixed_date_stamp="260830_1601")
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(second.stdout.strip(), plan_rel)
            self.assertEqual(before, (plan_path.read_bytes(), draft_path.read_bytes(), support_path.read_bytes()))

    def test_large_range_same_identity_reuse_repairs_wrong_durable_review_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            base, _head = self._init_repo(root)
            head = self._write_multi_commit(
                root,
                {f"apps/generated_{index:04d}.py": f"VALUE = {index}\n" for index in range(940)},
                "large generated range",
            )

            first = self._run_range_init(root, base, head, exclude_docs=0, fixed_date_stamp="260830_1602")
            self.assertEqual(first.returncode, 0, first.stderr)
            plan_rel = first.stdout.strip()
            plan_path, draft_path = self._generated_paths(root, plan_rel)
            expected_identity = (base, head, 0)
            correct_target = f"- Review target: `RANGE={base}..{head} (EXCLUDE_DOCS=0)`"
            wrong_base = ("0" if base[0] != "0" else "1") + base[1:]
            wrong_target = f"- Review target: `RANGE={wrong_base}..{head} (EXCLUDE_DOCS=0)`"
            plan_text = plan_path.read_text(encoding="utf-8")
            draft_text = draft_path.read_text(encoding="utf-8")
            self.assertEqual(plan_text.count(correct_target), 1)
            self.assertEqual(draft_text.count(correct_target), 1)
            refs, ref_errors = REVIEW_VISUAL_LANE_CONTRACT.referenced_full_payload_refs(plan_text)
            self.assertEqual(ref_errors, ())
            self.assertEqual(len(refs), 1)
            support_path = root / refs[0]
            support_bytes = support_path.read_bytes()

            for carrier_name, carrier_path in (("plan", plan_path), ("draft", draft_path)):
                with self.subTest(carrier=carrier_name):
                    original_text = carrier_path.read_text(encoding="utf-8")
                    tampered_text = original_text.replace(correct_target, wrong_target, 1)
                    self.assertNotEqual(tampered_text, original_text)
                    carrier_path.write_text(tampered_text, encoding="utf-8")

                    effective, effective_errors = REVIEW_VISUAL_LANE_CONTRACT.parse_materialized_contract(
                        tampered_text,
                        project_root=root,
                        expected_plan_ref=plan_rel,
                    )
                    self.assertEqual(effective_errors, [])
                    self.assertIsNotNone(effective)
                    strict, strict_errors = REVIEW_VISUAL_LANE_CONTRACT.parse_materialized_contract(
                        tampered_text,
                        project_root=root,
                        expected_plan_ref=plan_rel,
                        expected_range_identity=expected_identity,
                        require_review_target_identity=True,
                    )
                    self.assertIsNone(strict)
                    self.assertEqual(strict_errors, ["identity_mismatch"])

                    rerun = self._run_range_init(
                        root,
                        base,
                        head,
                        exclude_docs=0,
                        fixed_date_stamp="260830_1603",
                    )
                    self.assertEqual(rerun.returncode, 0, rerun.stderr)
                    self.assertEqual(rerun.stdout.strip(), plan_rel)
                    self.assertEqual(support_path.read_bytes(), support_bytes)

                    for readback_name, readback_path in (("plan", plan_path), ("draft", draft_path)):
                        readback_text = readback_path.read_text(encoding="utf-8")
                        self.assertEqual(readback_text.count(correct_target), 1)
                        self.assertNotIn(wrong_target, readback_text)
                        readback, readback_errors = REVIEW_VISUAL_LANE_CONTRACT.parse_materialized_contract(
                            readback_text,
                            project_root=root,
                            expected_plan_ref=plan_rel,
                            expected_range_identity=expected_identity,
                            require_review_target_identity=True,
                        )
                        self.assertEqual(readback_errors, [], readback_name)
                        self.assertIsNotNone(readback)

    def test_large_range_same_identity_reuse_repairs_missing_or_unparseable_plan_target(self) -> None:
        discovery_target_re = re.compile(
            r"- Review target: `RANGE=(?P<base>[0-9a-f]+)\.\.(?P<head>[0-9a-f]+) "
            r"\(EXCLUDE_DOCS=(?P<exclude>[01])\)`"
        )
        for fixture in ("missing", "unbackticked"):
            with self.subTest(fixture=fixture), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                base, _head = self._init_repo(root)
                head = self._write_multi_commit(
                    root,
                    {f"apps/generated_{index:04d}.py": f"VALUE = {index}\n" for index in range(940)},
                    "large generated range",
                )

                first = self._run_range_init(
                    root,
                    base,
                    head,
                    exclude_docs=0,
                    fixed_date_stamp="260831_0420",
                )
                self.assertEqual(first.returncode, 0, first.stderr)
                plan_rel = first.stdout.strip()
                plan_path, draft_path = self._generated_paths(root, plan_rel)
                expected_identity = (base, head, 0)
                correct_target = f"- Review target: `RANGE={base}..{head} (EXCLUDE_DOCS=0)`"
                plan_text = plan_path.read_text(encoding="utf-8")
                self.assertEqual(plan_text.count(correct_target), 1)
                self.assertRegex(
                    plan_text,
                    r'"schema_version"\s*:\s*"review_visual_lane_contract_ref\.v1"',
                )
                refs, ref_errors = REVIEW_VISUAL_LANE_CONTRACT.referenced_full_payload_refs(plan_text)
                self.assertEqual(ref_errors, ())
                self.assertEqual(len(refs), 1)
                support_path = root / refs[0]
                plan_before = plan_path.read_bytes()
                draft_before = draft_path.read_bytes()
                support_before = support_path.read_bytes()
                plan_paths = sorted(
                    (root / "docs" / "plans").glob(
                        f"*_reviewer_range_{base[:7]}_{head[:7]}*.md"
                    )
                )
                support_paths = sorted(
                    (root / "docs" / "code_reviews").glob(
                        "assets/*/review_visual_lane_contract.v2.json"
                    )
                )
                self.assertEqual(plan_paths, [plan_path])
                self.assertEqual(support_paths, [support_path])

                if fixture == "missing":
                    tampered_text = plan_text.replace(f"{correct_target}\n", "", 1)
                else:
                    unbackticked_target = (
                        f"- Review target: RANGE={base}..{head} (EXCLUDE_DOCS=0)"
                    )
                    tampered_text = plan_text.replace(correct_target, unbackticked_target, 1)
                self.assertNotEqual(tampered_text, plan_text)
                self.assertIsNone(discovery_target_re.search(tampered_text))
                tampered_plan_bytes = tampered_text.encode("utf-8")
                plan_path.write_bytes(tampered_plan_bytes)
                self.assertEqual(draft_path.read_bytes(), draft_before)
                self.assertEqual(support_path.read_bytes(), support_before)

                rerun = self._run_range_init(
                    root,
                    base,
                    head,
                    exclude_docs=0,
                    fixed_date_stamp="260831_0420",
                )
                plan_paths_after = sorted(
                    (root / "docs" / "plans").glob(
                        f"*_reviewer_range_{base[:7]}_{head[:7]}*.md"
                    )
                )
                support_paths_after = sorted(
                    (root / "docs" / "code_reviews").glob(
                        "assets/*/review_visual_lane_contract.v2.json"
                    )
                )
                self.assertEqual(plan_paths_after, [plan_path])
                self.assertEqual(support_paths_after, [support_path])

                if rerun.returncode == 0:
                    self.assertEqual(rerun.stdout.strip(), plan_rel)
                    self.assertEqual(support_path.read_bytes(), support_before)
                    refs_after, refs_after_errors = (
                        REVIEW_VISUAL_LANE_CONTRACT.referenced_full_payload_refs(
                            plan_path.read_text(encoding="utf-8")
                        )
                    )
                    self.assertEqual(refs_after_errors, ())
                    self.assertEqual(refs_after, refs)
                    for readback_name, readback_path in (("plan", plan_path), ("draft", draft_path)):
                        readback, readback_errors = (
                            REVIEW_VISUAL_LANE_CONTRACT.parse_materialized_contract(
                                readback_path.read_text(encoding="utf-8"),
                                project_root=root,
                                expected_plan_ref=plan_rel,
                                expected_range_identity=expected_identity,
                                require_review_target_identity=True,
                            )
                        )
                        self.assertEqual(readback_errors, [], readback_name)
                        self.assertIsNotNone(readback)
                else:
                    self.assertEqual(rerun.stdout.strip(), "")
                    self.assertIn("review-range visual-lane publication failed:", rerun.stderr)
                    self.assertEqual(plan_path.read_bytes(), tampered_plan_bytes)
                    self.assertEqual(draft_path.read_bytes(), draft_before)
                    self.assertEqual(support_path.read_bytes(), support_before)

    def test_large_range_injected_publication_failure_leaves_no_carrier(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            base, _head = self._init_repo(root)
            head = self._write_multi_commit(
                root,
                {f"apps/generated_{index:04d}.py": f"VALUE = {index}\n" for index in range(940)},
                "large generated range",
            )
            result = self._run_range_init(
                root,
                base,
                head,
                exclude_docs=0,
                extra_env={"PLANVEYOR_REVIEW_VISUAL_LANE_PUBLISH_FAIL_AFTER": "support"},
                fixed_date_stamp="260830_1602",
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(list((root / "docs" / "plans").glob("*_reviewer_range_*.md")), [])
            self.assertEqual(list((root / "docs" / "code_drafts").glob("*_reviewer_range_*__code_draft.md")), [])
            self.assertEqual(
                list((root / "docs" / "code_reviews").glob("assets/*/review_visual_lane_contract.v2.json")),
                [],
            )

    def test_large_range_refuses_preexisting_nonidentical_full_authority(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            base, _head = self._init_repo(root)
            head = self._write_multi_commit(
                root,
                {f"apps/generated_{index:04d}.py": f"VALUE = {index}\n" for index in range(940)},
                "large generated range",
            )
            first = self._run_range_init(root, base, head, exclude_docs=0)
            self.assertEqual(first.returncode, 0, first.stderr)
            plan_rel = first.stdout.strip()
            plan_path, draft_path = self._generated_paths(root, plan_rel)
            refs, ref_errors = REVIEW_VISUAL_LANE_CONTRACT.referenced_full_payload_refs(
                plan_path.read_text(encoding="utf-8")
            )
            self.assertEqual(ref_errors, ())
            self.assertEqual(len(refs), 1)
            support_path = root / refs[0]
            plan_before = plan_path.read_bytes()
            draft_before = draft_path.read_bytes()
            conflict_bytes = b'{"foreign":"authority"}'
            support_path.write_bytes(conflict_bytes)

            result = self._run_range_init(
                root,
                base,
                head,
                exclude_docs=0,
            )

            self.assertNotEqual(
                result.returncode,
                0,
                result.stdout + result.stderr,
            )
            self.assertIn("publication_conflict", result.stderr)
            self.assertEqual(support_path.read_bytes(), conflict_bytes)
            self.assertEqual(plan_path.read_bytes(), plan_before)
            self.assertEqual(draft_path.read_bytes(), draft_before)


if __name__ == "__main__":
    unittest.main()

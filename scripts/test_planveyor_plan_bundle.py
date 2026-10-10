#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import shlex
import subprocess
import sys
import tempfile
import textwrap
import unittest
from dataclasses import replace
from typing import Callable
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import followups_capture as FOLLOWUPS_CAPTURE
from scripts import followups_apply as FOLLOWUPS_APPLY
from scripts import followups_lint as FOLLOWUPS_LINT
from scripts import plan_status_oracle as PLAN_STATUS_ORACLE
from scripts import review_visual_lane_contract as REVIEW_VISUAL_LANE_CONTRACT
from scripts.test_support.process_contract_fixtures import run_zsh_fixture


PLANVEYOR_SCRIPT = REPO_ROOT / "scripts" / "planveyor.zsh"
PLANVEYOR_MODULE_DIR = REPO_ROOT / "scripts" / "planveyor"
PLAN_LINT_PATH = REPO_ROOT / "scripts" / "plan_lint.py"
PLAN_REL = "docs/plans/260324_0009_process_exact_bundle_commit_guard_for_dirty_index.md"
DRAFT_REL = "docs/code_drafts/260324_0009_process_exact_bundle_commit_guard_for_dirty_index__code_draft.md"
REVIEW_REL = "docs/code_reviews/260324_0009_process_exact_bundle_commit_guard_for_dirty_index.md"
PRIMARY_TARGET_REL = "scripts/live_target.sh"
CAPTURE_PLAN_REL = "docs/plans/260721_0200_terminal_capture_fixture.md"
REJECTED_PLAN_REL = "docs/plans/260724_0001_process_rejected_fixture.md"
REJECTED_DRAFT_REL = "docs/code_drafts/260724_0001_process_rejected_fixture__code_draft.md"
REJECTED_REVIEW_REL = "docs/code_reviews/260724_0001_process_rejected_fixture.md"
REJECTED_SUCCESSOR_REL = "docs/plans/260724_0002_process_rejected_successor.md"
REJECTED_RECOVERY_REL = "docs/plans/260724_0003_process_rejected_recovery.md"
REJECTED_RECOVERY_DRAFT_REL = "docs/code_drafts/260724_0003_process_rejected_recovery__code_draft.md"
REJECTED_TARGETS = ["docs/rejected-overlap.md", "scripts/rejected_target.py"]
DOC_REVIEW_FIXTURE_PLAN_REL = "docs/plans/accepted_red_doc_review_source_fixture.md"
DOC_REVIEW_FIXTURE_DRAFT_REL = "docs/code_drafts/accepted_red_doc_review_source_fixture__code_draft.md"
DOC_REVIEW_FIXTURE_REVIEW_REL = "docs/doc_reviews/accepted_red_doc_review_source_fixture.md"
DOC_REVIEW_FIXTURE_SUCCESSOR_REL = "docs/plans/accepted_red_doc_review_successor_fixture.md"
DOC_REVIEW_FIXTURE_TARGET_REL = "docs/fixture_targets/accepted_red_doc_review_target_fixture.md"
DOC_REVIEW_FIXTURE_RECOVERY_REL = "docs/plans/accepted_red_doc_review_recovery_fixture.md"
DOC_REVIEW_FIXTURE_RECOVERY_DRAFT_REL = "docs/code_drafts/accepted_red_doc_review_recovery_fixture__code_draft.md"
ACCEPTED_RED_CLOSEOUT_CORE_KEYS = {
    "schema",
    "plan",
    "terminal_disposition",
    "delivery_green",
    "staging_policy",
    "durable_capture_required",
    "terminal_disposition_reason",
    "recovery_ref",
    "recovery_manifest_path",
    "recovery_cleanup_path",
    "successor_plan",
    "review_bundle_sha256",
    "bundle_ok",
    "closeout_kind",
}
ACCEPTED_RED_PENDING_KEYS = ACCEPTED_RED_CLOSEOUT_CORE_KEYS | {
    "durable_capture_state",
    "active_checkout_state",
    "recovery_state",
}
ACCEPTED_RED_DURABLE_KEYS = ACCEPTED_RED_CLOSEOUT_CORE_KEYS | {
    "recovery_plan",
    "recovery_code_draft",
    "recovery_targets",
    "recovery_contract_state",
    "captured_parent",
    "capture_commit",
    "cleanup_commit",
    "durable_capture_state",
    "active_checkout_state",
    "recovery_state",
}
PLAN_BUNDLE_MODES = {
    "--print",
    "--check",
    "--preflight",
    "--stage",
    "--commit-ready",
    "--commit-exact",
    "--closeout-json",
    "--capture-rejected",
    "--verify-rejected",
    "--cleanup-rejected",
}

PLAN_LINT_SPEC = importlib.util.spec_from_file_location("plan_lint_under_test", PLAN_LINT_PATH)
assert PLAN_LINT_SPEC is not None and PLAN_LINT_SPEC.loader is not None
PLAN_LINT = importlib.util.module_from_spec(PLAN_LINT_SPEC)
sys.modules[PLAN_LINT_SPEC.name] = PLAN_LINT
PLAN_LINT_SPEC.loader.exec_module(PLAN_LINT)


class PlanBundleCommitReadyTests(unittest.TestCase):
    def _assert_accepted_red_public_keys(
        self,
        payload: dict[str, object],
        *,
        durable: bool,
    ) -> None:
        expected = ACCEPTED_RED_DURABLE_KEYS if durable else ACCEPTED_RED_PENDING_KEYS
        self.assertEqual(set(payload), expected)
        self.assertNotIn("historical_review", payload)

    def _git(self, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            text=True,
            capture_output=True,
        )

    def _commit_ref_overlay(
        self,
        root: Path,
        *,
        parent: str,
        overlays: dict[str, bytes],
        message: str,
    ) -> str:
        with tempfile.TemporaryDirectory() as index_dir:
            env = os.environ.copy()
            env["GIT_INDEX_FILE"] = str(Path(index_dir) / "index")

            def run_git(
                *args: str,
                input_bytes: bytes | None = None,
            ) -> subprocess.CompletedProcess[bytes]:
                return subprocess.run(
                    ["git", "-C", str(root), *args],
                    input=input_bytes,
                    env=env,
                    check=True,
                    capture_output=True,
                )

            run_git("read-tree", parent)
            for rel, data in overlays.items():
                oid = run_git("hash-object", "-w", "--stdin", input_bytes=data).stdout.decode().strip()
                run_git("update-index", "--add", "--cacheinfo", "100644", oid, rel)
            tree = run_git("write-tree").stdout.decode().strip()
            return run_git(
                "commit-tree",
                tree,
                "-p",
                parent,
                input_bytes=f"{message}\n".encode(),
            ).stdout.decode().strip()

    def _init_repo(
        self,
        root: Path,
        *,
        thin_shim: bool = False,
        copy_helper_modules: bool = True,
        copy_dispatch_prompts: bool = True,
    ) -> None:
        (root / "scripts").mkdir(parents=True, exist_ok=True)
        vocab_path = root / "docs" / "_meta" / "plan_vocab.json"
        vocab_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / "docs" / "_meta" / "plan_vocab.json", vocab_path)
        if thin_shim:
            (root / "scripts" / "planveyor.zsh").write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env zsh
                    tooling_root="${PLANVEYOR_ROOT:-$HOME/planveyor}"
                    source "${tooling_root}/scripts/planveyor.zsh"
                    """
                ),
                encoding="utf-8",
            )
        else:
            shutil.copy2(PLANVEYOR_SCRIPT, root / "scripts" / "planveyor.zsh")
            shutil.copytree(PLANVEYOR_MODULE_DIR, root / "scripts" / "planveyor")
        if copy_helper_modules:
            for helper_name in (
                "contract_authority_snapshot.py",
                "contract_authority_runtime.py",
                "contract_authority_context.py",
                "contract_authority_bootstrap.py",
                "contract_authority_shell_loader.zsh",
                "contract_authority_children.py",
                "contract_authority_bridge.py",
                "docs_closeout.py",
                "followups_capture.py",
                "followups_apply.py",
                "followups_lint.py",
                "followups_index_rebuild.py",
                "fs_object_identity.py",
                "plan_lint.py",
                "plan_queue.py",
                "plan_status_oracle.py",
                "process_improvements_collect.py",
                "retrieval_telemetry_receipt.py",
                "review_artifact_lint.py",
                "review_header_metadata.py",
                "review_schema_contract.py",
                "review_target_snapshot.py",
                "review_visual_lane_contract.py",
            ):
                shutil.copy2(REPO_ROOT / "scripts" / helper_name, root / "scripts" / helper_name)
            if copy_dispatch_prompts:
                # Preserve docs-closeout dispatch coverage with the public root corpus.
                prompt_dir = Path("docs/tools/prompts")
                (root / prompt_dir).mkdir(parents=True, exist_ok=True)
                for role in ("architect", "coder", "planner", "reviewer"):
                    for lane in ("general", "followups"):
                        name = f"{role}_docs_finalize_{lane}.md"
                        shutil.copy2(REPO_ROOT / prompt_dir / name, root / prompt_dir / name)
        self._git(root, "init")
        self._git(root, "config", "user.name", "Test User")
        self._git(root, "config", "user.email", 'test' + '@' + 'example' + '.' + 'com')
        # Authority distinguishes a valid marker-free Git target from an
        # advertised repository whose HEAD is unavailable.  Keep the fixture
        # files untracked while giving the target a real initial observation.
        self._git(root, "commit", "--allow-empty", "-m", "fixture repository")

    def _commit_all(self, root: Path, message: str) -> None:
        self._git(root, "add", ".")
        self._git(root, "commit", "-m", message)

    def _materialize_bundle(
        self,
        root: Path,
        extra_targets: list[str] | None = None,
        *,
        deleted_paths: list[str] | None = None,
        materialize_deleted_paths: bool = True,
        materialize_review: bool = True,
        review_text: str | None = None,
        plan_review_notes: str | None = None,
        status: str = "✅ OK",
    ) -> None:
        extra_targets = extra_targets or []
        deleted_paths = deleted_paths or []
        (root / "docs" / "plans").mkdir(parents=True, exist_ok=True)
        (root / "docs" / "code_drafts").mkdir(parents=True, exist_ok=True)
        (root / "docs" / "code_reviews").mkdir(parents=True, exist_ok=True)

        target_path = root / PRIMARY_TARGET_REL
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text("echo ready\n", encoding="utf-8")

        targets = [{"path": PRIMARY_TARGET_REL, "kind": "py"}]
        for extra_target in extra_targets:
            targets.append({"path": extra_target, "kind": "doc"})
        deletion_entries = [{"path": deleted_path, "kind": "doc"} for deleted_path in deleted_paths]
        if materialize_deleted_paths:
            for deleted_path in deleted_paths:
                deleted_fs_path = root / deleted_path
                deleted_fs_path.parent.mkdir(parents=True, exist_ok=True)
                deleted_fs_path.write_text("obsolete\n", encoding="utf-8")

        decision = {
            "schema_version": "machine_authority_decision.v1",
            "applicability": "not_applicable",
            "reason_code": "no_machine_authority_change",
        }
        decision_ref = {
            "applicability": "not_applicable",
            "reason_code": "no_machine_authority_change",
            "carrier_sha256": PLAN_STATUS_ORACLE.machine_authority_decision_sha256(decision),
        }
        draft_payload = {
            "code_draft_meta": {
                "plan": PLAN_REL,
                "cluster": "process",
                "targets": targets,
                "deleted_paths": deletion_entries,
                "machine_authority_decision_ref": decision_ref,
            }
        }
        draft_text = textwrap.dedent(
            f"""\
            # Code draft: test exact bundle guard

            ```json
            {json.dumps(draft_payload, indent=2).replace(chr(10), chr(10) + "            ")}
            ```
            """
        )
        # Write the draft before the plan so the checked-in current-bundle producer
        # can compute the strict target from already-materialized draft + target files.
        (root / DRAFT_REL).write_text(draft_text, encoding="utf-8")

        plan_text = textwrap.dedent(
            f"""\
            # Plan: test exact bundle guard

            **Date:** 2026-03-25 00:00 MSK
            **Stage:** Stage 1
            **Priority:** P1
            **Plan type:** dev
            **Status:** Ready for Review

            **Context links (source of truth):**
            - Code draft(s): `{DRAFT_REL}`

            ## Meta (machine-readable JSON; required for new plans)
            ```json
            {json.dumps({"plan_meta": {"cluster": "process", "machine_authority_decision": decision}}, indent=2).replace(chr(10), chr(10) + "            ")}
            ```

            ## Review artifacts

            - Code review (primary): `{REVIEW_REL}`
            """
        )
        if plan_review_notes:
            plan_text = plan_text.replace(
                f"- Code review (primary): `{REVIEW_REL}`\n",
                f"- Code review (primary): `{REVIEW_REL}`\n{plan_review_notes.rstrip()}\n",
            )
        (root / PLAN_REL).write_text(plan_text, encoding="utf-8")
        if materialize_review:
            if review_text is None:
                # Default review stays on the loose `PLAN=...` target; only the same-file
                # lifecycle cases compute a producer-owned strict target via the 2-phase
                # helper (absolute/mirror-root sibling paths are not producer-eligible).
                review_text = self._same_file_review_text(status=status)
            (root / REVIEW_REL).write_text(review_text, encoding="utf-8")

    def _rewrite_deleted_path_entries(self, root: Path, deleted_entries: list[dict[str, str | bool]]) -> None:
        decision = {
            "schema_version": "machine_authority_decision.v1",
            "applicability": "not_applicable",
            "reason_code": "no_machine_authority_change",
        }
        draft_payload = {
            "code_draft_meta": {
                "plan": PLAN_REL,
                "cluster": "process",
                "targets": [{"path": PRIMARY_TARGET_REL, "kind": "py"}],
                "deleted_paths": deleted_entries,
                "machine_authority_decision_ref": {
                    "applicability": "not_applicable",
                    "reason_code": "no_machine_authority_change",
                    "carrier_sha256": PLAN_STATUS_ORACLE.machine_authority_decision_sha256(decision),
                },
            }
        }
        (root / DRAFT_REL).write_text(
            f"# Code draft: test exact bundle guard\n\n```json\n{json.dumps(draft_payload, indent=2)}\n```\n",
            encoding="utf-8",
        )

    def _compute_strict_target(self, root: Path) -> str:
        """Invoke the checked-in current-bundle producer once and return its literal target.

        Plan/draft/current targets must already be materialized under ``root``.
        """
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "review_target_snapshot.py"),
                PLAN_REL,
                "--current-bundle",
                "--project-root",
                str(root),
            ],
            cwd=root,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        snapshot = json.loads(result.stdout)
        target = snapshot["target"]
        self.assertRegex(target, r"^BUNDLE=current bundle_sha256=[0-9a-f]{64}$")
        return target

    def _compute_plan_strict_target(self, root: Path, plan_rel: str) -> str:
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "review_target_snapshot.py"),
                plan_rel,
                "--current-bundle",
                "--project-root",
                str(root),
            ],
            cwd=root,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return str(json.loads(result.stdout)["target"])

    def _compute_plan_snapshot(self, root: Path, plan_rel: str) -> dict[str, object]:
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "review_target_snapshot.py"),
                plan_rel,
                "--current-bundle",
                "--project-root",
                str(root),
            ],
            cwd=root,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        parsed = json.loads(result.stdout)
        self.assertIsInstance(parsed, dict)
        return parsed

    def _legacy_v1_bundle_sha(self, root: Path, target_paths: list[str]) -> str:
        files = []
        for rel in sorted(target_paths):
            data = (root / rel).read_bytes()
            files.append(
                {
                    "path": rel,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "size_bytes": len(data),
                }
            )
        basis = {
            "algorithm": "sha256",
            "files": files,
            "schema_version": "review_target_snapshot.hash_basis.v1",
        }
        return hashlib.sha256(
            json.dumps(
                basis,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

    def _materialize_snapshot_bridge(
        self,
        root: Path,
        *,
        strict_v2_sha: str,
        legacy_v1_sha: str,
        producer_commit: str,
        producer_blob_oid: str,
    ) -> dict[str, object]:
        target_records = []
        for rel in sorted(REJECTED_TARGETS):
            data = (root / rel).read_bytes()
            blob_oid = subprocess.run(
                ["git", "-C", str(root), "hash-object", "--stdin"],
                input=data,
                capture_output=True,
                check=True,
            ).stdout.decode("ascii").strip()
            target_records.append(
                {
                    "path": rel,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "size_bytes": len(data),
                    "git_mode": "100644",
                    "git_blob_oid": blob_oid,
                }
            )
        bridge = {
            "schema": "planveyor_accepted_red_snapshot_bridge.v1",
            "bridge_id": "synthetic-v1-to-v2",
            "source_plan": REJECTED_PLAN_REL,
            "review_bundle_sha256": legacy_v1_sha,
            "legacy_hash_basis_schema": "review_target_snapshot.hash_basis.v1",
            "legacy_hash_basis": "sha256-canonical-json-v1-path-sha256-size",
            "producer_commit": producer_commit,
            "producer_path": "scripts/review_target_snapshot.py",
            "producer_blob_oid": producer_blob_oid,
            "current_hash_basis_schema": "review_target_snapshot.hash_basis.v2",
            "current_hash_basis": "sha256-canonical-json-v2-path-sha256-size-git_mode",
            "current_bundle_sha256": strict_v2_sha,
            "targets": target_records,
        }
        bridge["bridge_sha256"] = hashlib.sha256(
            json.dumps(
                bridge,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        recovery = root / REJECTED_RECOVERY_REL
        recovery.write_text(
            recovery.read_text(encoding="utf-8")
            + "\n```json\n"
            + json.dumps({"accepted_red_snapshot_bridge": bridge}, indent=2)
            + "\n```\n",
            encoding="utf-8",
        )
        review = root / REJECTED_REVIEW_REL
        review.write_text(
            review.read_text(encoding="utf-8").replace(
                strict_v2_sha,
                legacy_v1_sha,
            ),
            encoding="utf-8",
        )
        return bridge

    def _allowlist_snapshot_bridge(
        self,
        root: Path,
        bridge: dict[str, object],
    ) -> None:
        helper = root / "scripts/plan_status_oracle.py"
        text = helper.read_text(encoding="utf-8")
        marker = "ACCEPTED_RED_SNAPSHOT_BRIDGE_ALLOWLIST: dict[tuple[str, str, str], str] = {}\n"
        entry = (
            "ACCEPTED_RED_SNAPSHOT_BRIDGE_ALLOWLIST: dict[tuple[str, str, str], str] = {\n"
            "    (\n"
            f"        {bridge['source_plan']!r},\n"
            f"        {bridge['review_bundle_sha256']!r},\n"
            f"        {bridge['bridge_id']!r},\n"
            f"    ): {bridge['bridge_sha256']!r},\n"
            "}\n"
        )
        self.assertIn(marker, text)
        helper.write_text(text.replace(marker, entry, 1), encoding="utf-8")

    def _materialize_rejected_fixture(
        self,
        root: Path,
        *,
        source_rel: str = REJECTED_PLAN_REL,
        draft_rel: str = REJECTED_DRAFT_REL,
        review_rel: str = REJECTED_REVIEW_REL,
        successor_rel: str = REJECTED_SUCCESSOR_REL,
        recovery_rel: str = REJECTED_RECOVERY_REL,
        recovery_draft_rel: str = REJECTED_RECOVERY_DRAFT_REL,
        head_absent_targets: set[str] | None = None,
        target_paths: list[str] | None = None,
        blocker_ids: tuple[str, ...] = ("B1", "B2", "B3"),
        inherited_ids: tuple[str, ...] | None = None,
        source_ref_id: str | None = None,
        blocker_state: str = "open",
        historical_text: str = "",
        review_label: str = "Code review (primary)",
    ) -> str:
        head_absent_targets = head_absent_targets or set()
        target_paths = target_paths or REJECTED_TARGETS
        inherited_ids = blocker_ids if inherited_ids is None else inherited_ids
        source_ref_id = source_ref_id or blocker_ids[-1]
        for rel in (
            source_rel,
            draft_rel,
            review_rel,
            successor_rel,
            recovery_rel,
            recovery_draft_rel,
            *target_paths,
        ):
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
        source_decision = {
            "schema_version": "machine_authority_decision.v1",
            "applicability": "not_applicable",
            "reason_code": "no_machine_authority_change",
        }
        source_meta = {
            "plan_meta": {
                "cluster": "process",
                "parent": None,
                "next_plans": [successor_rel],
                "scope_expansion": {
                    "state": "architect_accepted",
                    "target_contour": "developer_wave",
                    "source_ref": f"{review_rel}#{source_ref_id}",
                    "reason": "Accepted-red fixture route.",
                },
                "machine_authority_decision": source_decision,
            }
        }
        (root / source_rel).write_text(
            "# Plan: rejected fixture\n\n"
            "**Status:** Superseded\n\n"
            f"- Code draft(s): `{draft_rel}`\n"
            "\n## Meta\n"
            f"```json\n{json.dumps(source_meta, indent=2)}\n```\n\n"
            "## Review artifacts\n"
            f"- {review_label}: `{review_rel}`\n",
            encoding="utf-8",
        )
        draft_meta = {
            "code_draft_meta": {
                "plan": source_rel,
                "cluster": "process",
                "targets": [{"path": rel, "kind": "doc"} for rel in target_paths],
                "deleted_paths": [],
                "machine_authority_decision_ref": {
                    "applicability": "not_applicable",
                    "reason_code": "no_machine_authority_change",
                    "carrier_sha256": PLAN_STATUS_ORACLE.machine_authority_decision_sha256(source_decision),
                },
            }
        }
        (root / draft_rel).write_text(
            f"# Rejected draft\n\n```json\n{json.dumps(draft_meta, indent=2)}\n```\n",
            encoding="utf-8",
        )
        successor_meta = {
            "plan_meta": {
                "cluster": "process",
                "parent": source_rel,
                "next_plans": [],
                "scope_expansion": {
                    "state": "n/a",
                    "target_contour": "developer_wave",
                    "source_ref": "N/A (why=fixture successor has no further expansion)",
                    "reason": "N/A (why=fixture successor has no further expansion)",
                },
            }
        }
        (root / successor_rel).write_text(
            "# Plan: accepted successor\n\n"
            "**Status:** Architect initial draft\n\n"
            + "".join(
                f"- inherited `{review_rel}#{blocker}`\n"
                for blocker in inherited_ids
            )
            + "\n"
            f"```json\n{json.dumps(successor_meta, indent=2)}\n```\n",
            encoding="utf-8",
        )
        recovery_decision = {
            "schema_version": "machine_authority_decision.v1",
            "applicability": "not_applicable",
            "reason_code": "no_machine_authority_change",
        }
        recovery_meta = {
            "plan_meta": {
                "cluster": "process",
                "parent": None,
                "next_plans": [],
                "scope_expansion": {
                    "state": "n/a",
                    "target_contour": "developer_wave",
                    "source_ref": "N/A (why=fixture recovery has no further expansion)",
                    "reason": "N/A (why=fixture recovery has no further expansion)",
                },
                "machine_authority_decision": recovery_decision,
            }
        }
        (root / recovery_rel).write_text(
            "# Plan: rejected recovery\n\n"
            "**Status:** In progress\n\n"
            f"- Superseded incident plan: `{source_rel}`.\n"
            f"- Code draft(s): `{recovery_draft_rel}`\n\n"
            "## Meta\n"
            f"```json\n{json.dumps(recovery_meta, indent=2)}\n```\n",
            encoding="utf-8",
        )
        recovery_draft_meta = {
            "code_draft_meta": {
                "plan": recovery_rel,
                "cluster": "process",
                "targets": [{"path": target_paths[0], "kind": "doc"}],
                "deleted_paths": [],
                "machine_authority_decision_ref": {
                    "applicability": "not_applicable",
                    "reason_code": "no_machine_authority_change",
                    "carrier_sha256": PLAN_STATUS_ORACLE.machine_authority_decision_sha256(recovery_decision),
                },
            }
        }
        (root / recovery_draft_rel).write_text(
            f"# Recovery draft\n\n```json\n{json.dumps(recovery_draft_meta, indent=2)}\n```\n",
            encoding="utf-8",
        )
        blocker_sections = "\n\n".join(
            f"### {blocker}) blocker {blocker[1:]}\n\n"
            f"- Blocker ID: `{blocker}`\n"
            f"- Current state: `{blocker_state}`"
            for blocker in blocker_ids
        )
        (root / review_rel).write_text(
            "# Review\n\n"
            "**Target:** BUNDLE=current bundle_sha256="
            + ("0" * 64)
            + "\n**Status:** ❌ S1 blocker(ы)\n\n"
            f"## S1 Blocker\n\n{blocker_sections}\n"
            f"{historical_text}",
            encoding="utf-8",
        )
        for rel in target_paths:
            if rel in head_absent_targets:
                continue
            (root / rel).write_text(f"baseline {rel}\n", encoding="utf-8")
        self._commit_all(root, "rejected fixture baseline")
        for rel in target_paths:
            (root / rel).write_text(f"rejected {rel}\n", encoding="utf-8")
        strict_target = self._compute_plan_strict_target(root, source_rel)
        review = root / review_rel
        review.write_text(
            review.read_text(encoding="utf-8").replace(
                "BUNDLE=current bundle_sha256=" + ("0" * 64),
                strict_target,
            ),
            encoding="utf-8",
        )
        return strict_target.removeprefix("BUNDLE=current bundle_sha256=")

    def _materialize_doc_review_fixture(self, root: Path) -> bytes:
        self._materialize_rejected_fixture(
            root,
            source_rel=DOC_REVIEW_FIXTURE_PLAN_REL,
            draft_rel=DOC_REVIEW_FIXTURE_DRAFT_REL,
            review_rel=DOC_REVIEW_FIXTURE_REVIEW_REL,
            successor_rel=DOC_REVIEW_FIXTURE_SUCCESSOR_REL,
            recovery_rel=DOC_REVIEW_FIXTURE_RECOVERY_REL,
            recovery_draft_rel=DOC_REVIEW_FIXTURE_RECOVERY_DRAFT_REL,
            target_paths=[DOC_REVIEW_FIXTURE_TARGET_REL],
            blocker_ids=("B1",),
            inherited_ids=("B1",),
            source_ref_id="B1",
            review_label="Doc review (docs-only)",
        )
        # The source review is part of the baseline; only its declared target
        # must remain a rejected working-tree delta for capture/cleanup.
        self._git(root, "add", DOC_REVIEW_FIXTURE_REVIEW_REL)
        self._git(root, "commit", "-m", "doc review fixture carrier")
        return (root / DOC_REVIEW_FIXTURE_REVIEW_REL).read_bytes()

    def _inject_plan_review_notes(self, root: Path, notes: str) -> None:
        plan_path = root / PLAN_REL
        plan_text = plan_path.read_text(encoding="utf-8")
        plan_text = plan_text.replace(
            f"- Code review (primary): `{REVIEW_REL}`\n",
            f"- Code review (primary): `{REVIEW_REL}`\n{notes.rstrip()}\n",
        )
        plan_path.write_text(plan_text, encoding="utf-8")

    def _run_bundle(
        self,
        root: Path,
        mode: str,
        *,
        plan_rel: str = PLAN_REL,
    ) -> subprocess.CompletedProcess[str]:
        return run_zsh_fixture(
            f"source scripts/planveyor.zsh && planveyor_plan_bundle {mode} {plan_rel}",
            cwd=root,
            path=os.environ.get("PATH", os.defpath),
            pybin=str(Path(sys.executable).resolve()),
            fixture_env={"PLANVEYOR_ROOT": str(REPO_ROOT)},
            home=root / ".home",
            check=False,
        )

    def _write_strict_na_parent_fixture(
        self,
        root: Path,
        *,
        materialized: bool,
        phase_state: str = "active",
        asset_rel: str | None = None,
        map_only: bool = False,
        execution_queue: bool | None = None,
        next_plans: tuple[str, ...] | None = None,
        status: str | None = None,
        review_rel: str = "docs/code_reviews/260823_1509_strict_na_bundle_parent.md",
    ) -> dict[str, object]:
        """Create one strict parent without a same-stem parent draft.

        The child drafts deliberately name implementation files so the bundle
        test can prove that the parent carrier does not recurse into them.
        """

        parent_rel = "docs/plans/260823_1509_strict_na_bundle_parent.md"
        review_label = (
            "Doc review (docs-only)" if review_rel.startswith("docs/doc_reviews/") else "Code review (primary)"
        )
        children = (
            "docs/plans/260823_1510_strict_na_child_a.md",
            "docs/plans/260823_1511_strict_na_child_b.md",
        )
        child_targets = (
            "scripts/strict_na_child_a_impl.py",
            "scripts/strict_na_child_b_impl.py",
        )
        receipt_rel = "docs/reviews/260823_1509_strict_na_parent_receipt.json"
        if asset_rel is None:
            asset_rel = "docs/code_reviews/assets/260823_1509_strict_na_bundle_parent/deferred-proof.json"

        for child_rel, target_rel in zip(children, child_targets, strict=True):
            child_path = root / child_rel
            child_path.parent.mkdir(parents=True, exist_ok=True)
            child_path.write_text(
                "# Plan: strict N-A child fixture\n\n"
                "**Plan type:** dev\n"
                "**Status:** Ready for Coder\n",
                encoding="utf-8",
            )
            child_draft_rel = f"docs/code_drafts/{Path(child_rel).stem}__code_draft.md"
            child_draft = root / child_draft_rel
            child_draft.parent.mkdir(parents=True, exist_ok=True)
            child_draft.write_text(
                "# Code draft: strict N-A child fixture\n\n```json\n"
                + json.dumps(
                    {
                        "code_draft_meta": {
                            "plan": child_rel,
                            "cluster": "process",
                            "targets": [{"path": target_rel, "kind": "py"}],
                            "deleted_paths": [],
                        }
                    },
                    indent=2,
                )
                + "\n```\n",
                encoding="utf-8",
            )
            target = root / target_rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f"# child-only target: {target_rel}\n", encoding="utf-8")
            child_review = root / f"docs/code_reviews/{Path(child_rel).stem}.md"
            child_review.parent.mkdir(parents=True, exist_ok=True)
            child_review.write_text("# Child review (not a parent member)\n", encoding="utf-8")

        asset = root / asset_rel
        asset.parent.mkdir(parents=True, exist_ok=True)
        asset.write_text('{"deferred": "parent planning evidence"}\n', encoding="utf-8")
        receipt = root / receipt_rel
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text('{"schema": "fixture"}\n', encoding="utf-8")
        unrelated_followup = root / "docs/followups/strict_na_unrelated.md"
        unrelated_followup.parent.mkdir(parents=True, exist_ok=True)
        unrelated_followup.write_text("# Unrelated follow-up\n", encoding="utf-8")

        child_map_section = (
            "## Child plan map\n"
            "| Queue order | Plan | Summary |\n"
            "| --- | --- | --- |\n"
            + "\n".join(
                f"| {index} | `{child_rel}` | materialized child |"
                for index, child_rel in enumerate(children, start=1)
            )
            if materialized or map_only
            else "## Child plan map\n- `N/A (why=child graph is not materialized)`"
        )
        has_concrete_execution_queue = materialized if execution_queue is None else execution_queue
        if has_concrete_execution_queue:
            execution_rows = "\n".join(f"- Plan: `{child_rel}`" for child_rel in children)
        elif execution_queue is False:
            execution_rows = "- Resume parent: `fixture`"
        else:
            execution_rows = "- Resume parent: `fixture`\n- Plan: `N/A (why=child graph is not materialized)`"
        decision = {
            "schema_version": "machine_authority_decision.v1",
            "applicability": "not_applicable",
            "reason_code": "no_machine_authority_change",
        }
        parent_meta = {
            "cluster": "process",
            "tags": [],
            "phase_overlay": "decomposition_wave",
            "phase_state": phase_state,
            "parent": None,
            "next_plans": list((children if materialized else ()) if next_plans is None else next_plans),
            "depends_on": [],
            "followups_out": [],
            "canon_updates": [],
            "machine_authority_decision": decision,
        }
        parent = root / parent_rel
        parent.parent.mkdir(parents=True, exist_ok=True)
        parent.write_text(
            "# Plan: strict N-A parent bundle fixture\n\n"
            "**Date:** 2026-08-23 15:09 MSK\n"
            "**Stage:** Stage 1\n"
            "**Priority:** P1\n"
            "**Plan type:** dev\n"
            f"**Status:** {status or ('Ready for Review' if materialized else 'Coder intake')}\n\n"
            "**Context links (source of truth):**\n"
            "- Code draft(s): `N/A (why=strict decomposition parent fixture)`.\n\n"
            "## Meta\n```json\n"
            + json.dumps({"plan_meta": parent_meta}, indent=2)
            + "\n```\n\n"
            + child_map_section
            + "\n\n## Execution queue\n"
            + execution_rows
            + "\n\n## Review artifacts\n"
            + f"- {review_label}: `{review_rel}`\n",
            encoding="utf-8",
        )
        if materialized:
            review_text = self._same_file_review_text(
                status="✅ OK",
                target_snapshot=f"PLAN={parent_rel}",
            ).replace(PLAN_REL, parent_rel).replace(REVIEW_REL, review_rel)
            review = root / review_rel
            review.parent.mkdir(parents=True, exist_ok=True)
            review.write_text(
                review_text
                + f"\n- Parent planning asset: `{asset_rel}`\n"
                + f"- Durable receipt: `{receipt_rel}`\n",
                encoding="utf-8",
            )
        return {
            "parent_rel": parent_rel,
            "review_rel": review_rel,
            "children": children,
            "child_targets": child_targets,
            "asset_rel": asset_rel,
            "receipt_rel": receipt_rel,
            "unrelated_followup": str(unrelated_followup.relative_to(root)),
        }

    def test_strict_na_candidate_mode_matrix_is_inspection_only_and_mutation_free(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            fixture = self._write_strict_na_parent_fixture(root, materialized=False)
            parent_rel = str(fixture["parent_rel"])
            self._commit_all(root, "strict N-A candidate baseline")
            head_before = self._git(root, "rev-parse", "HEAD").stdout.strip()
            refs_before = self._git(root, "show-ref").stdout
            index_before = self._git(root, "diff", "--cached", "--name-only").stdout
            index_tree_before = self._git(root, "write-tree").stdout.strip()

            for mode in ("--print", "--preflight"):
                with self.subTest(mode=mode):
                    result = self._run_bundle(root, mode, plan_rel=parent_rel)
                    output = result.stdout + result.stderr
                    self.assertEqual(result.returncode, 0, output)
                    self.assertIn(parent_rel, output)
                    self.assertNotIn("260823_1509_strict_na_bundle_parent__code_draft.md", output)
                    for child_rel in fixture["children"]:
                        self.assertNotIn(str(child_rel), output)
                    self.assertEqual(self._git(root, "write-tree").stdout.strip(), index_tree_before)

            for mode in ("--check", "--stage", "--commit-ready"):
                with self.subTest(mode=mode):
                    result = self._run_bundle(root, mode, plan_rel=parent_rel)
                    output = result.stdout + result.stderr
                    self.assertNotEqual(result.returncode, 0, output)
                    self.assertIn("decomposition_children_missing", output)
                    self.assertEqual(self._git(root, "rev-parse", "HEAD").stdout.strip(), head_before)
                    self.assertEqual(self._git(root, "show-ref").stdout, refs_before)
                    self.assertEqual(self._git(root, "diff", "--cached", "--name-only").stdout, index_before)
                    self.assertEqual(self._git(root, "write-tree").stdout.strip(), index_tree_before)

            commit_exact = self._run_shell(
                root,
                "planveyor_plan_bundle --commit-exact --preflight-json /dev/null --message-file /dev/null "
                + parent_rel,
            )
            commit_exact_output = commit_exact.stdout + commit_exact.stderr
            self.assertNotEqual(commit_exact.returncode, 0, commit_exact_output)
            self.assertIn("decomposition_children_missing", commit_exact_output)
            self.assertEqual(self._git(root, "rev-parse", "HEAD").stdout.strip(), head_before)
            self.assertEqual(self._git(root, "show-ref").stdout, refs_before)
            self.assertEqual(self._git(root, "diff", "--cached", "--name-only").stdout, index_before)
            self.assertEqual(self._git(root, "write-tree").stdout.strip(), index_tree_before)

            stage_closeout = self._run_shell(
                root,
                "planveyor_plan_bundle --stage --docs-closeout-json /dev/null " + parent_rel,
            )
            stage_closeout_output = stage_closeout.stdout + stage_closeout.stderr
            self.assertNotEqual(stage_closeout.returncode, 0, stage_closeout_output)
            self.assertIn("decomposition_children_missing", stage_closeout_output)
            self.assertEqual(self._git(root, "rev-parse", "HEAD").stdout.strip(), head_before)
            self.assertEqual(self._git(root, "show-ref").stdout, refs_before)
            self.assertEqual(self._git(root, "diff", "--cached", "--name-only").stdout, index_before)
            self.assertEqual(self._git(root, "write-tree").stdout.strip(), index_tree_before)

            commit_ready_closeout = self._run_shell(
                root,
                "planveyor_plan_bundle --commit-ready --docs-closeout-json /dev/null " + parent_rel,
            )
            commit_ready_closeout_output = commit_ready_closeout.stdout + commit_ready_closeout.stderr
            self.assertNotEqual(commit_ready_closeout.returncode, 0, commit_ready_closeout_output)
            self.assertIn("decomposition_children_missing", commit_ready_closeout_output)
            self.assertEqual(self._git(root, "rev-parse", "HEAD").stdout.strip(), head_before)
            self.assertEqual(self._git(root, "show-ref").stdout, refs_before)
            self.assertEqual(self._git(root, "diff", "--cached", "--name-only").stdout, index_before)
            self.assertEqual(self._git(root, "write-tree").stdout.strip(), index_tree_before)

            closeout = self._run_bundle(root, "--closeout-json", plan_rel=parent_rel)
            self.assertEqual(closeout.returncode, 0, closeout.stdout + closeout.stderr)
            payload = json.loads(closeout.stdout)
            self.assertFalse(payload["bundle_ok"])
            self.assertEqual(payload["closeout_kind"], "needs_rerun")
            self.assertIn("decomposition_children_missing", "\n".join(payload["errors"]))
            self.assertEqual(self._git(root, "rev-parse", "HEAD").stdout.strip(), head_before)
            self.assertEqual(self._git(root, "show-ref").stdout, refs_before)
            self.assertEqual(self._git(root, "diff", "--cached", "--name-only").stdout, index_before)
            self.assertEqual(self._git(root, "write-tree").stdout.strip(), index_tree_before)

    def test_materialized_strict_na_parent_bundle_includes_only_planning_carriers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            fixture = self._write_strict_na_parent_fixture(root, materialized=True)
            parent_rel = str(fixture["parent_rel"])
            self._commit_all(root, "materialized strict N-A parent baseline")

            for mode in ("--print", "--preflight", "--check"):
                with self.subTest(mode=mode):
                    result = self._run_bundle(root, mode, plan_rel=parent_rel)
                    output = result.stdout + result.stderr
                    self.assertEqual(result.returncode, 0, output)
                    for expected in (
                        parent_rel,
                        str(fixture["review_rel"]),
                        str(fixture["asset_rel"]),
                        str(fixture["receipt_rel"]),
                        *(str(child_rel) for child_rel in fixture["children"]),
                    ):
                        self.assertIn(expected, output)
                    for child_rel in fixture["children"]:
                        self.assertIn(
                            f"docs/code_drafts/{Path(str(child_rel)).stem}__code_draft.md",
                            output,
                        )
                    for excluded in (*fixture["child_targets"], str(fixture["unrelated_followup"])):
                        self.assertNotIn(str(excluded), output)
                    for child_rel in fixture["children"]:
                        self.assertNotIn(
                            f"docs/code_reviews/{Path(str(child_rel)).stem}.md",
                            output,
                        )

    def test_strict_na_parent_bounded_next_plans_preserves_all_canonical_bundle_members(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            fixture = self._write_strict_na_parent_fixture(
                root,
                materialized=True,
                execution_queue=False,
                next_plans=("docs/plans/260823_1510_strict_na_child_a.md",),
            )
            parent_rel = str(fixture["parent_rel"])
            parent_text = (root / parent_rel).read_text(encoding="utf-8")
            child_state = PLAN_STATUS_ORACLE.decomposition_child_state(parent_text, root=root)
            self.assertEqual(child_state.state, "queue_ready")
            self.assertEqual(child_state.expansion_source, "next_plans")
            self.assertEqual(child_state.concrete_child_paths, fixture["children"][:1])
            self.assertEqual(child_state.canonical_planning_child_paths, fixture["children"])
            self.assertEqual(PLAN_STATUS_ORACLE.execution_queue_plan_entries(parent_text), [])
            self.assertNotIn("- Plan: `docs/plans/260823_1510_strict_na_child_a.md`", parent_text)
            self.assertNotIn("- Plan: `docs/plans/260823_1511_strict_na_child_b.md`", parent_text)
            self._commit_all(root, "bounded next-plans strict N-A parent baseline")

            for mode in ("--print", "--preflight", "--check"):
                with self.subTest(mode=mode):
                    result = self._run_bundle(root, mode, plan_rel=parent_rel)
                    output = result.stdout + result.stderr
                    self.assertEqual(result.returncode, 0, output)
                    self.assertIn(parent_rel, output)
                    for child_rel in fixture["children"]:
                        self.assertIn(str(child_rel), output)
                        self.assertIn(
                            f"docs/code_drafts/{Path(str(child_rel)).stem}__code_draft.md",
                            output,
                        )
                        self.assertNotIn(
                            f"docs/code_reviews/{Path(str(child_rel)).stem}.md",
                            output,
                        )
                    for excluded in fixture["child_targets"]:
                        self.assertNotIn(str(excluded), output)

    def test_strict_na_snapshot_and_bundle_share_complete_canonical_graph(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            fixture = self._write_strict_na_parent_fixture(
                root,
                materialized=True,
                execution_queue=False,
                next_plans=("docs/plans/260823_1510_strict_na_child_a.md",),
            )
            parent_rel = str(fixture["parent_rel"])
            parent_text = (root / parent_rel).read_text(encoding="utf-8")
            child_state = PLAN_STATUS_ORACLE.decomposition_child_state(parent_text, root=root)
            self._commit_all(root, "strict N-A snapshot parity baseline")

            bundle = self._run_bundle(root, "--preflight", plan_rel=parent_rel)
            snapshot = self._compute_plan_snapshot(root, parent_rel)

        output = bundle.stdout + bundle.stderr
        expected_children = list(child_state.canonical_planning_child_paths)
        expected_drafts = [
            f"docs/code_drafts/{Path(child).stem}__code_draft.md" for child in expected_children
        ]
        self.assertEqual(bundle.returncode, 0, output)
        self.assertEqual(child_state.state, "queue_ready")
        self.assertEqual(child_state.concrete_child_paths, tuple(expected_children[:1]))
        self.assertEqual(snapshot["schema_version"], "review_target_snapshot.v3")
        self.assertEqual(snapshot["source"]["child_plans"], expected_children)
        self.assertEqual(snapshot["source"]["child_code_drafts"], expected_drafts)
        self.assertEqual(snapshot["target_paths"], sorted([*expected_children, *expected_drafts]))
        self.assertEqual(len(snapshot["target_paths"]), 2 * len(expected_children))
        for child in expected_children:
            self.assertIn(child, output)
            self.assertIn(f"docs/code_drafts/{Path(child).stem}__code_draft.md", output)
        for excluded in (*fixture["child_targets"],):
            self.assertNotIn(str(excluded), output)
            self.assertNotIn(str(excluded), snapshot["target_paths"])
        for child in expected_children:
            review_rel = f"docs/code_reviews/{Path(child).stem}.md"
            self.assertNotIn(review_rel, snapshot["target_paths"])

    def test_strict_na_parent_candidate_materializes_into_the_same_parent_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            candidate = self._write_strict_na_parent_fixture(root, materialized=False)
            parent_rel = str(candidate["parent_rel"])
            self._commit_all(root, "strict N-A candidate lifecycle baseline")

            candidate_preflight = self._run_bundle(root, "--preflight", plan_rel=parent_rel)
            candidate_output = candidate_preflight.stdout + candidate_preflight.stderr
            self.assertEqual(candidate_preflight.returncode, 0, candidate_output)
            self.assertNotIn("260823_1509_strict_na_bundle_parent__code_draft.md", candidate_output)
            for child_rel in candidate["children"]:
                self.assertNotIn(str(child_rel), candidate_output)

            materialized = self._write_strict_na_parent_fixture(root, materialized=True)
            materialized_preflight = self._run_bundle(root, "--preflight", plan_rel=parent_rel)
            materialized_output = materialized_preflight.stdout + materialized_preflight.stderr
            self.assertEqual(materialized_preflight.returncode, 0, materialized_output)
            for expected in (
                parent_rel,
                str(materialized["review_rel"]),
                str(materialized["asset_rel"]),
                str(materialized["receipt_rel"]),
                *(str(child_rel) for child_rel in materialized["children"]),
            ):
                self.assertIn(expected, materialized_output)
            self.assertNotIn("260823_1509_strict_na_bundle_parent__code_draft.md", materialized_output)

    def test_strict_na_parent_conflicting_current_draft_fails_closed_before_staging(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            fixture = self._write_strict_na_parent_fixture(root, materialized=True)
            parent_rel = str(fixture["parent_rel"])
            parent_draft = root / "docs/code_drafts/260823_1509_strict_na_bundle_parent__code_draft.md"
            parent_draft.parent.mkdir(parents=True, exist_ok=True)
            parent_draft.write_text("# Physical conflict; strict N-A must reject it.\n", encoding="utf-8")
            self._commit_all(root, "strict N-A parent draft conflict baseline")
            index_tree_before = self._git(root, "write-tree").stdout.strip()

            preflight = self._run_bundle(root, "--preflight", plan_rel=parent_rel)
            preflight_output = preflight.stdout + preflight.stderr
            self.assertNotEqual(preflight.returncode, 0, preflight_output)
            self.assertIn("machine_authority_decision_code_draft_ref_invalid", preflight_output)

            stage = self._run_bundle(root, "--stage", plan_rel=parent_rel)
            stage_output = stage.stdout + stage.stderr
            self.assertEqual(stage.returncode, 2, stage_output)
            self.assertIn("machine_authority_decision_code_draft_ref_invalid", stage_output)
            self.assertEqual(self._git(root, "write-tree").stdout.strip(), index_tree_before)

    def test_strict_na_parent_active_map_only_graph_fails_closed_before_staging(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            fixture = self._write_strict_na_parent_fixture(root, materialized=False, map_only=True)
            parent_rel = str(fixture["parent_rel"])
            self._commit_all(root, "strict N-A active map-only baseline")
            index_tree_before = self._git(root, "write-tree").stdout.strip()

            for mode in ("--preflight", "--stage"):
                with self.subTest(mode=mode):
                    result = self._run_bundle(root, mode, plan_rel=parent_rel)
                    output = result.stdout + result.stderr
                    self.assertNotEqual(result.returncode, 0, output)
                    self.assertIn("decomposition_children_missing", output)
                    self.assertEqual(self._git(root, "write-tree").stdout.strip(), index_tree_before)

    def test_strict_na_parent_risk_support_accepts_only_parent_assets_or_durable_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            fixture = self._write_strict_na_parent_fixture(root, materialized=True)
            parent_rel = str(fixture["parent_rel"])
            parent = root / parent_rel
            self._commit_all(root, "strict N-A risk-support baseline")

            allowed_rel = str(fixture["asset_rel"])
            allowed_sha = hashlib.sha256((root / allowed_rel).read_bytes()).hexdigest()
            parent.write_text(
                parent.read_text(encoding="utf-8")
                + "\n## Evidence\n\n```json\n"
                + json.dumps(
                    {
                        "lane_id": "reviewer_code_risk",
                        "run_id": "historical-parent-asset",
                        "current": False,
                        "full_payload_ref": allowed_rel,
                        "full_payload_sha256": allowed_sha,
                    },
                    sort_keys=True,
                )
                + "\n```\n",
                encoding="utf-8",
            )
            allowed = self._run_bundle(root, "--preflight", plan_rel=parent_rel)
            self.assertEqual(allowed.returncode, 0, allowed.stdout + allowed.stderr)

            forbidden_rel = "docs/followups/strict_na_forbidden_risk.json"
            forbidden = root / forbidden_rel
            forbidden.parent.mkdir(parents=True, exist_ok=True)
            forbidden.write_text('{"forbidden":true}\n', encoding="utf-8")
            forbidden_sha = hashlib.sha256(forbidden.read_bytes()).hexdigest()
            parent.write_text(
                parent.read_text(encoding="utf-8")
                + "\n```json\n"
                + json.dumps(
                    {
                        "lane_id": "reviewer_code_risk",
                        "run_id": "historical-forbidden-followup",
                        "current": False,
                        "full_payload_ref": forbidden_rel,
                        "full_payload_sha256": forbidden_sha,
                    },
                    sort_keys=True,
                )
                + "\n```\n",
                encoding="utf-8",
            )
            index_tree_before = self._git(root, "write-tree").stdout.strip()

            preflight = self._run_bundle(root, "--preflight", plan_rel=parent_rel)
            preflight_output = preflight.stdout + preflight.stderr
            self.assertNotEqual(preflight.returncode, 0, preflight_output)
            self.assertIn("strict N-A parent risk support is outside", preflight_output)

            stage = self._run_bundle(root, "--stage", plan_rel=parent_rel)
            stage_output = stage.stdout + stage.stderr
            self.assertEqual(stage.returncode, 2, stage_output)
            self.assertIn("strict N-A parent risk support is outside", stage_output)
            self.assertEqual(self._git(root, "write-tree").stdout.strip(), index_tree_before)

    def _declare_strict_na_risk_support(self, root: Path, parent_rel: str, support_rel: str) -> None:
        support = root / support_rel
        support.parent.mkdir(parents=True, exist_ok=True)
        support.write_text('{"lane_id": "reviewer_code_risk"}\n', encoding="utf-8")
        parent = root / parent_rel
        parent_text = parent.read_text(encoding="utf-8")
        if "\n## Evidence\n" not in parent_text:
            parent_text += "\n## Evidence\n"
        carrier = {
            "lane_id": "reviewer_code_risk",
            "run_id": f"historical-{Path(support_rel).stem}",
            "current": False,
            "full_payload_ref": support_rel,
            "full_payload_sha256": hashlib.sha256(support.read_bytes()).hexdigest(),
        }
        parent.write_text(
            parent_text + "\n```json\n" + json.dumps(carrier, sort_keys=True) + "\n```\n",
            encoding="utf-8",
        )

    def test_strict_na_parent_doc_review_accepts_canonical_risk_support_root(self) -> None:
        # A docs-only parent keeps its live review in docs/doc_reviews/, while
        # docs/plans/README.md stores risk support under
        # docs/code_reviews/assets/<plan-stem>/ for every review route, and the
        # review names that support literally.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            fixture = self._write_strict_na_parent_fixture(
                root,
                materialized=True,
                review_rel="docs/doc_reviews/260823_1509_strict_na_bundle_parent.md",
                asset_rel="docs/doc_reviews/assets/260823_1509_strict_na_bundle_parent/deferred-proof.json",
            )
            parent_rel = str(fixture["parent_rel"])
            support_rel = (
                "docs/code_reviews/assets/260823_1509_strict_na_bundle_parent/"
                "reviewer_code_risk_20260823T150900Z.json"
            )
            self._declare_strict_na_risk_support(root, parent_rel, support_rel)
            review = root / str(fixture["review_rel"])
            review.write_text(
                review.read_text(encoding="utf-8") + f"- Support: `{support_rel}`\n",
                encoding="utf-8",
            )
            self._commit_all(root, "strict N-A doc-review canonical risk-support baseline")

            for mode in ("--check", "--stage"):
                with self.subTest(mode=mode):
                    result = self._run_bundle(root, mode, plan_rel=parent_rel)
                    output = result.stdout + result.stderr
                    self.assertEqual(result.returncode, 0, output)
                    self.assertIn(f"{support_rel} [plan_risk_support,review_asset]", output)
                    self.assertIn(str(fixture["review_rel"]), output)

    def test_strict_na_parent_doc_review_rejects_support_outside_canonical_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            fixture = self._write_strict_na_parent_fixture(
                root,
                materialized=True,
                review_rel="docs/doc_reviews/260823_1509_strict_na_bundle_parent.md",
                asset_rel="docs/doc_reviews/assets/260823_1509_strict_na_bundle_parent/deferred-proof.json",
            )
            parent_rel = str(fixture["parent_rel"])
            # The canonical root is keyed by this plan's stem: a child's root stays foreign.
            foreign_rel = (
                "docs/code_reviews/assets/260823_1510_strict_na_child_a/"
                "reviewer_code_risk_20260823T150900Z.json"
            )
            self._declare_strict_na_risk_support(root, parent_rel, foreign_rel)
            # The review may name only declared support under the canonical root.
            undeclared_rel = "docs/code_reviews/assets/260823_1509_strict_na_bundle_parent/undeclared.json"
            undeclared = root / undeclared_rel
            undeclared.parent.mkdir(parents=True, exist_ok=True)
            undeclared.write_text('{"undeclared": true}\n', encoding="utf-8")
            review = root / str(fixture["review_rel"])
            review.write_text(
                review.read_text(encoding="utf-8") + f"- Undeclared asset: `{undeclared_rel}`\n",
                encoding="utf-8",
            )
            self._commit_all(root, "strict N-A doc-review foreign risk-support baseline")
            index_tree_before = self._git(root, "write-tree").stdout.strip()

            check = self._run_bundle(root, "--check", plan_rel=parent_rel)
            check_output = check.stdout + check.stderr
            self.assertNotEqual(check.returncode, 0, check_output)
            self.assertIn("strict N-A parent risk support is outside", check_output)
            self.assertIn(foreign_rel, check_output)
            self.assertIn("strict N-A parent review asset is outside its matching review-assets root", check_output)
            self.assertIn(undeclared_rel, check_output)

            stage = self._run_bundle(root, "--stage", plan_rel=parent_rel)
            stage_output = stage.stdout + stage.stderr
            self.assertEqual(stage.returncode, 2, stage_output)
            self.assertIn("strict N-A parent risk support is outside", stage_output)
            self.assertEqual(self._git(root, "write-tree").stdout.strip(), index_tree_before)

    def test_materialized_strict_na_parent_rejects_invalid_review_asset_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            fixture = self._write_strict_na_parent_fixture(
                root,
                materialized=True,
                asset_rel="docs/code_reviews/assets/other-review/deferred-proof.json",
            )
            self._commit_all(root, "invalid strict N-A asset baseline")
            result = self._run_bundle(root, "--preflight", plan_rel=str(fixture["parent_rel"]))

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("outside its matching review-assets root", result.stdout + result.stderr)

    def test_materialized_parked_strict_na_parent_preserves_the_same_bundle_members(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            fixture = self._write_strict_na_parent_fixture(root, materialized=True, phase_state="parked")
            self._commit_all(root, "materialized parked strict N-A parent baseline")
            result = self._run_bundle(root, "--preflight", plan_rel=str(fixture["parent_rel"]))
            output = result.stdout + result.stderr

        self.assertEqual(result.returncode, 0, output)
        for expected in (*fixture["children"], fixture["asset_rel"], fixture["receipt_rel"]):
            self.assertIn(str(expected), output)

    def test_materialized_strict_na_parent_rejects_nonregular_asset_and_mismatched_child_draft(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            fixture = self._write_strict_na_parent_fixture(root, materialized=True)
            self._commit_all(root, "strict N-A negative membership baseline")
            asset = root / str(fixture["asset_rel"])
            asset.unlink()
            asset.mkdir()
            child_rel = str(fixture["children"][0])
            child_draft = root / f"docs/code_drafts/{Path(child_rel).stem}__code_draft.md"
            child_draft.write_text(
                child_draft.read_text(encoding="utf-8").replace(
                    child_rel,
                    "docs/plans/260823_1599_wrong_child.md",
                    1,
                ),
                encoding="utf-8",
            )
            result = self._run_bundle(root, "--preflight", plan_rel=str(fixture["parent_rel"]))
            output = result.stdout + result.stderr

        self.assertNotEqual(result.returncode, 0, output)
        self.assertIn("review asset must be a regular file", output)
        self.assertIn("child code_draft_meta.plan mismatch", output)

    def test_strict_na_parent_preamble_graph_decoy_stays_missing_before_staging(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            fixture = self._write_strict_na_parent_fixture(
                root,
                materialized=False,
                status="Ready for Review",
            )
            parent_rel = str(fixture["parent_rel"])
            review_rel = str(fixture["review_rel"])
            review = root / review_rel
            review.parent.mkdir(parents=True, exist_ok=True)
            review.write_text(
                self._same_file_review_text(
                    status="✅ OK",
                    target_snapshot=f"PLAN={parent_rel}",
                ).replace(PLAN_REL, parent_rel).replace(REVIEW_REL, review_rel)
                + f"\n- Parent planning asset: `{fixture['asset_rel']}`\n"
                + f"- Durable receipt: `{fixture['receipt_rel']}`\n",
                encoding="utf-8",
            )
            parent = root / parent_rel
            parent.write_text(
                "```json\n"
                + json.dumps(
                    {
                        "plan_meta": {
                            "phase_overlay": "decomposition_wave",
                            "phase_state": "active",
                            "next_plans": list(fixture["children"]),
                        }
                    }
                )
                + "\n```\n\n"
                + parent.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            self._commit_all(root, "strict N-A preamble graph decoy baseline")
            index_tree_before = self._git(root, "write-tree").stdout.strip()

            staged = self._run_bundle(root, "--stage", plan_rel=parent_rel)
            output = staged.stdout + staged.stderr
            index_tree_after = self._git(root, "write-tree").stdout.strip()

        self.assertEqual(staged.returncode, 2, output)
        self.assertIn("decomposition_children_missing", output)
        self.assertEqual(index_tree_after, index_tree_before)

    def test_materialized_strict_na_parent_rejects_unlintable_child_drafts_before_staging(self) -> None:
        cases = (
            ("empty_targets", [], "Empty child code_draft_meta.targets"),
            ("malformed_target", [{"kind": "py"}], "Invalid child code_draft_meta.target entry"),
        )
        for label, replacement_targets, expected_error in cases:
            with self.subTest(case=label), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                self._init_repo(root)
                fixture = self._write_strict_na_parent_fixture(
                    root,
                    materialized=True,
                )
                parent_rel = str(fixture["parent_rel"])
                child_rel = str(fixture["children"][0])
                child_draft = root / f"docs/code_drafts/{Path(child_rel).stem}__code_draft.md"
                match = re.search(r"```json\s*(\{.*?\})\s*```", child_draft.read_text(encoding="utf-8"), re.DOTALL)
                self.assertIsNotNone(match)
                child_payload = json.loads(match.group(1))
                child_payload["code_draft_meta"]["targets"] = replacement_targets
                child_draft.write_text(
                    "# Code draft: strict N-A child fixture\n\n```json\n"
                    + json.dumps(child_payload, indent=2)
                    + "\n```\n",
                    encoding="utf-8",
                )
                self._commit_all(root, f"strict N-A {label} baseline")
                index_tree_before = self._git(root, "write-tree").stdout.strip()

                staged = self._run_bundle(root, "--stage", plan_rel=parent_rel)
                output = staged.stdout + staged.stderr

                self.assertNotEqual(staged.returncode, 0, output)
                self.assertIn(expected_error, output)
                self.assertEqual(self._git(root, "write-tree").stdout.strip(), index_tree_before)

    def _run_shell(
        self,
        root: Path,
        command: str,
        *,
        env_extra: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        fixture_env = {"PLANVEYOR_ROOT": str(REPO_ROOT)}
        if env_extra:
            fixture_env.update(env_extra)
        return run_zsh_fixture(
            f"source scripts/planveyor.zsh && {command}",
            cwd=root,
            path=os.environ.get("PATH", os.defpath),
            pybin=str(Path(sys.executable).resolve()),
            fixture_env=fixture_env,
            home=root / ".home",
            check=False,
        )

    def _run_oracle_subprocess(
        self,
        root: Path,
        plan_rel: str,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run(
            [
                sys.executable,
                "-B",
                str(root / "scripts" / "plan_status_oracle.py"),
                plan_rel,
                "--json",
            ],
            cwd=root,
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )

    def _install_counting_identity_wrapper(
        self,
        root: Path,
        *,
        target_paths: list[str] | tuple[str, ...],
    ) -> None:
        helper = root / "scripts/fs_object_identity.py"
        helper_source = helper.read_text(encoding="utf-8")
        target_paths_literal = repr(tuple(target_paths))
        helper.write_text(
            helper_source
            + textwrap.dedent(
                """\

                # Test-only instrumentation appended to the canonical helper.
                import os as _test_os
                from pathlib import Path as _TestPath

                _test_original_snapshot_regular_or_absent = snapshot_regular_or_absent
                _test_target_paths = frozenset(__TARGET_PATHS__)


                def snapshot_regular_or_absent(trusted_root, relative_path, *, _observer=None):
                    if relative_path not in _test_target_paths:
                        return _test_original_snapshot_regular_or_absent(
                            trusted_root,
                            relative_path,
                            _observer=_observer,
                        )

                    count_path = _test_os.environ.get("PLANVEYOR_TEST_SNAPSHOT_COUNT_PATH")
                    if count_path:
                        with open(count_path, "a", encoding="utf-8") as handle:
                            handle.write(relative_path + "\\n")
                    target_rel = _test_os.environ.get("PLANVEYOR_TEST_IDENTITY_SWAP_REL")
                    target_stage = _test_os.environ.get("PLANVEYOR_TEST_IDENTITY_SWAP_STAGE")
                    swapped = False

                    def observer(stage):
                        nonlocal swapped
                        if _observer is not None:
                            _observer(stage)
                        if swapped or relative_path != target_rel or stage != target_stage:
                            return
                        swapped = True
                        target = _TestPath(trusted_root) / relative_path
                        if stage == "after_ancestor_chain_opened":
                            ancestor = target.parent
                            retained = ancestor.with_name(ancestor.name + "-retained")
                            alias = ancestor.with_name(ancestor.name + "-alias")
                            ancestor.rename(retained)
                            alias.mkdir(parents=True, exist_ok=True)
                            (alias / target.name).write_text("replacement ancestor bytes\\n", encoding="utf-8")
                            ancestor.symlink_to(alias, target_is_directory=True)
                        elif stage == "after_leaf_read":
                            replacement = target.with_name(target.name + ".replacement")
                            replacement.write_text("replacement leaf bytes\\n", encoding="utf-8")
                            _test_os.replace(replacement, target)

                    return _test_original_snapshot_regular_or_absent(
                        trusted_root,
                        relative_path,
                        _observer=observer,
                    )
                """
            ).replace("__TARGET_PATHS__", target_paths_literal),
            encoding="utf-8",
        )

    def _write_capture_plan_admission_pair(self, root: Path) -> Path:
        plan = root / CAPTURE_PLAN_REL
        plan.parent.mkdir(parents=True, exist_ok=True)
        decision = {
            "schema_version": PLAN_STATUS_ORACLE.MACHINE_AUTHORITY_DECISION_SCHEMA,
            "applicability": "not_applicable",
            "reason_code": "no_machine_authority_change",
        }
        plan.write_text(
            "# Plan: terminal capture fixture\n\n"
            "**Status:** Done\n\n"
            "## Meta\n"
            "```json\n"
            + json.dumps({"plan_meta": {"machine_authority_decision": decision}}, indent=2)
            + "\n```\n",
            encoding="utf-8",
        )
        draft = root / f"docs/code_drafts/{plan.stem}__code_draft.md"
        draft.parent.mkdir(parents=True, exist_ok=True)
        draft.write_text(
            "# Code draft: terminal capture fixture\n\n"
            "```json\n"
            + json.dumps(
                {
                    "code_draft_meta": {
                        "plan": CAPTURE_PLAN_REL,
                        "machine_authority_decision_ref": {
                            "applicability": "not_applicable",
                            "reason_code": decision["reason_code"],
                            "carrier_sha256": PLAN_STATUS_ORACLE.machine_authority_decision_sha256(decision),
                        },
                    }
                },
                indent=2,
            )
            + "\n```\n",
            encoding="utf-8",
        )
        return plan

    def _capture_docs_payload(self, root: Path) -> tuple[dict[str, object], str]:
        self._write_capture_plan_admission_pair(root)
        followups_dir = root / "docs/followups"
        followups_dir.mkdir(parents=True, exist_ok=True)
        (followups_dir / "README.md").write_text("# Followups fixture\n", encoding="utf-8")
        self._commit_all(root, "capture baseline")
        begin_payload = {
            "schema": "docs_closeout_payload.v1",
            "schema_state": "ok",
            "plan_ref": CAPTURE_PLAN_REL,
            "semantic_status": "Done",
            "semantic_status_norm": "done",
            "semantic_closeout_kind": "already_materialized",
            "final_docs_commit": "required",
        }
        begin = FOLLOWUPS_CAPTURE.begin_cycle(root.resolve(), CAPTURE_PLAN_REL, begin_payload)
        cycle_id = str(begin["capture_cycle_id"])
        for collector_role in FOLLOWUPS_CAPTURE.REQUIRED_ROLES:
            FOLLOWUPS_CAPTURE.process_improvements_collect.collect_process_improvements(
                project_root=root.resolve(),
                role=collector_role,
                source_ref=CAPTURE_PLAN_REL,
                text="## Process improvements\nNO PROCESS IMPROVEMENTS — why: clean_run\n",
                followups_capture_cycle_id=cycle_id,
            )
        FOLLOWUPS_CAPTURE.checkpoint_general_pi(
            root.resolve(),
            CAPTURE_PLAN_REL,
            cycle_id,
        )
        owned_rel = "docs/followups/260721_0200_terminal_capture_fixture.md"
        for index, role in enumerate(FOLLOWUPS_CAPTURE.REQUIRED_ROLES):
            FOLLOWUPS_CAPTURE.prepare_role(root.resolve(), CAPTURE_PLAN_REL, cycle_id, role)
            if index == 0:
                (root / owned_rel).write_text(
                    "# Follow-ups backlog — fixture\n\n"
                    "**Date:** 21.07.2026 02:00\n"
                    "**Source:** terminal docs finalize\n"
                    "**Status:** Draft\n"
                    "**Schema version:** followups.v1\n\n"
                    "## Follow-ups (backlog)\n"
                    "- P1 [ ] Exact terminal fixture — cluster=process — tags=fixture — to=Architect "
                    f"— status=open — plan=null — source_ref={CAPTURE_PLAN_REL} — why: exact commit proof\n",
                    encoding="utf-8",
                )
                stdout = f"Created: {owned_rel}\nSummary: fixture\n".encode()
            else:
                stdout = b"NO FOLLOWUPS\nSummary: none\n"
            FOLLOWUPS_CAPTURE.finalize_role(root.resolve(), CAPTURE_PLAN_REL, cycle_id, role, stdout)
        readback = FOLLOWUPS_CAPTURE.read_capture(
            root.resolve(),
            CAPTURE_PLAN_REL,
            cycle_id,
            semantic_fields=("Done", "done", "already_materialized"),
        )
        payload: dict[str, object] = {
            **begin_payload,
            "followups_capture_cycle_id": cycle_id,
            "current_plan_owned_docs_delta_paths": [owned_rel],
            "foreign_docs_delta_paths": [],
            "blocked_docs_delta_paths": [],
            "final_docs_diff_paths": [owned_rel],
            "architect_final_handoff": {
                "required": True,
                "plan_ref": CAPTURE_PLAN_REL,
                "final_docs_diff_paths": [owned_rel],
                "followups_staging_expectations": readback["staging_expectations"],
            },
        }
        return payload, owned_rel

    def _capture_empty_docs_payload(
        self,
        root: Path,
        *,
        before_begin: Callable[[], None] | None = None,
        before_finalize: Callable[[str, str], None] | None = None,
        general_pi_text: Callable[[str, str], str] | None = None,
    ) -> tuple[dict[str, object], dict[str, object]]:
        self._write_capture_plan_admission_pair(root)
        followups_dir = root / "docs/followups"
        followups_dir.mkdir(parents=True, exist_ok=True)
        (followups_dir / "README.md").write_text("# Followups fixture\n", encoding="utf-8")
        self._commit_all(root, "capture baseline")
        if before_begin is not None:
            before_begin()
        begin_payload: dict[str, object] = {
            "schema": "docs_closeout_payload.v1",
            "schema_state": "ok",
            "plan_ref": CAPTURE_PLAN_REL,
            "semantic_status": "Done",
            "semantic_status_norm": "done",
            "semantic_closeout_kind": "already_materialized",
            "final_docs_commit": "no_op",
        }
        begin = FOLLOWUPS_CAPTURE.begin_cycle(root.resolve(), CAPTURE_PLAN_REL, begin_payload)
        cycle_id = str(begin["capture_cycle_id"])
        for collector_role in FOLLOWUPS_CAPTURE.REQUIRED_ROLES:
            FOLLOWUPS_CAPTURE.process_improvements_collect.collect_process_improvements(
                project_root=root.resolve(),
                role=collector_role,
                source_ref=CAPTURE_PLAN_REL,
                text=(
                    general_pi_text(collector_role, cycle_id)
                    if general_pi_text is not None
                    else "## Process improvements\nNO PROCESS IMPROVEMENTS — why: clean_run\n"
                ),
                followups_capture_cycle_id=cycle_id,
            )
        FOLLOWUPS_CAPTURE.checkpoint_general_pi(
            root.resolve(),
            CAPTURE_PLAN_REL,
            cycle_id,
        )
        for role in FOLLOWUPS_CAPTURE.REQUIRED_ROLES:
            FOLLOWUPS_CAPTURE.prepare_role(root.resolve(), CAPTURE_PLAN_REL, cycle_id, role)
            if before_finalize is not None:
                before_finalize(role, cycle_id)
            FOLLOWUPS_CAPTURE.finalize_role(
                root.resolve(),
                CAPTURE_PLAN_REL,
                cycle_id,
                role,
                b"NO FOLLOWUPS\nSummary: none\n",
            )
        readback = FOLLOWUPS_CAPTURE.read_capture(
            root.resolve(),
            CAPTURE_PLAN_REL,
            cycle_id,
            semantic_fields=("Done", "done", "already_materialized"),
        )
        payload: dict[str, object] = {
            **begin_payload,
            "followups_capture_cycle_id": cycle_id,
            "current_plan_owned_docs_delta_paths": [],
            "foreign_docs_delta_paths": [],
            "blocked_docs_delta_paths": [],
            "final_docs_diff_paths": [],
            "architect_final_handoff": {
                "required": False,
                "plan_ref": CAPTURE_PLAN_REL,
                "final_docs_diff_paths": [],
                "followups_staging_expectations": [],
            },
        }
        return payload, readback

    def _capture_v2_external_docs_payload(
        self,
        root: Path,
        *,
        include_foreign_terminal: bool = False,
    ) -> tuple[dict[str, object], str, list[str]]:
        carrier_rel = "docs/followups/260721_0200_external_v2_fixture.md"
        foreign_plan_rel = "docs/plans/260721_0201_foreign_terminal_capture_fixture.md"

        def apply_before_capture() -> None:
            if include_foreign_terminal:
                foreign_plan = root / foreign_plan_rel
                foreign_plan.write_text(
                    "# Plan: foreign terminal capture fixture\n\n**Status:** Done\n",
                    encoding="utf-8",
                )
                self._commit_all(root, "foreign terminal source")
            commit = self._git(root, "rev-parse", "HEAD").stdout.strip()
            blob = self._git(root, "rev-parse", f"HEAD:{CAPTURE_PLAN_REL}").stdout.strip()
            snapshot, _contents = FOLLOWUPS_CAPTURE.snapshot_followups(root, include_bytes=True)
            row = {
                "priority": "P1",
                "summary": "External V2 exact-stage fixture",
                "cluster": "process",
                "to": "architect",
                "status": "open",
                "plan": None,
                "why": "prove one carrier is writer-derived before capture",
                "tags": ["fixture"],
                "item_id": "external-v2-stage-001",
                "source_ref": CAPTURE_PLAN_REL,
                "disposition_kind": None,
                "disposition_ref": None,
                "disposition_commit_oid": None,
                "reason": None,
            }
            tuple_key = f"{CAPTURE_PLAN_REL}\u0000external-v2-stage-001"
            manifest: dict[str, object] = {
                "schema_version": "followups_capture_cycle.v2",
                "plan_ref": CAPTURE_PLAN_REL,
                "source_terminal_commit_oid": commit,
                "source_plan_blob_oid": blob,
                "source_plan_sha256": hashlib.sha256(
                    self._git(root, "show", f"{commit}:{CAPTURE_PLAN_REL}").stdout.encode("utf-8")
                ).hexdigest(),
                "baseline_followups_snapshot": snapshot,
                "baseline_followups_snapshot_sha256": FOLLOWUPS_CAPTURE._sha256(
                    FOLLOWUPS_CAPTURE._canonical_json_bytes(snapshot)
                ),
                "declaration_roles": ["Architect", "Coder", "Planner", "Reviewer"],
                "expected_owned_tuples": [
                    {"source_ref": CAPTURE_PLAN_REL, "item_id": "external-v2-stage-001"},
                ],
                "tuple_owners": {tuple_key: "Architect"},
                "expected_zero_reason": None,
                "proposed_rows": [
                    {
                        "followup_path": carrier_rel,
                        "payload": row,
                        "row_digest": FOLLOWUPS_LINT.v2_row_digest(row),
                    },
                ],
            }
            FOLLOWUPS_APPLY.apply_frozen_rows(root, manifest, mutate=True)
            FOLLOWUPS_CAPTURE.persist_v2_frozen_manifest(root, CAPTURE_PLAN_REL, manifest)

        def collector_text(role_name: str, _cycle_id: str) -> str:
            if role_name == "Coder":
                return (
                    "## Process improvements\n"
                    "### Suggestion 1\n"
                    "- symptom: V2 fixture needs the existing PI four-path transport\n"
                    "- process_gap: staged external carrier must remain disjoint from PI ownership\n"
                    "- suggested_fix: exercise exact merge only\n"
                    "- owner: Architect\n"
                    "- promotion_class: helper_change\n"
                    "- trigger_ref: docs/code_reviews/fixture.md#B1\n"
                    f"- source_ref: {CAPTURE_PLAN_REL}\n"
                )
            return "## Process improvements\nNO PROCESS IMPROVEMENTS — why: clean_run\n"

        payload, capture = self._capture_empty_docs_payload(
            root,
            before_begin=apply_before_capture,
            general_pi_text=collector_text,
        )
        v2_expectations = FOLLOWUPS_CAPTURE.v2_external_followup_staging_expectations(
            root,
            CAPTURE_PLAN_REL,
            capture_binding=capture,
        )
        pi_proof = FOLLOWUPS_CAPTURE.process_improvement_cycle_proof(
            root,
            CAPTURE_PLAN_REL,
            capture,
        )
        pi_paths = list(pi_proof["changed_data_paths"])
        pi_expectations = FOLLOWUPS_CAPTURE.process_improvement_staging_expectations(
            root,
            CAPTURE_PLAN_REL,
            pi_paths,
            capture_binding=capture,
        )
        expectations = sorted([*v2_expectations, *pi_expectations], key=lambda item: item["path"])
        final_paths = [item["path"] for item in expectations]
        payload.update(
            {
                "final_docs_commit": "required",
                "current_plan_owned_docs_delta_paths": final_paths,
                "final_docs_diff_paths": final_paths,
                "architect_final_handoff": {
                    "required": True,
                    "plan_ref": CAPTURE_PLAN_REL,
                    "final_docs_diff_paths": final_paths,
                    "followups_staging_expectations": expectations,
                },
            }
        )
        return payload, carrier_rel, pi_paths

    def _write_json(self, root: Path, name: str, payload: dict[str, object]) -> Path:
        path = root / name
        path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def _run_bundle_json(self, root: Path) -> dict:
        result = self._run_bundle(root, "--closeout-json")
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def _extract_plan_bundle_modes(self, text: str) -> set[str]:
        match = re.search(r"planveyor_plan_bundle \[([^\]]+)\] <PLAN_PATH>", text)
        self.assertIsNotNone(match, text[:200])
        assert match is not None
        return set(match.group(1).split("|"))

    def _run_closeout_preflight(self, root: Path) -> subprocess.CompletedProcess[str]:
        return run_zsh_fixture(
            f"source scripts/planveyor.zsh && planveyor_plan_closeout_preflight {PLAN_REL}",
            cwd=root,
            path=os.environ.get("PATH", os.defpath),
            pybin=str(Path(sys.executable).resolve()),
            fixture_env={"PLANVEYOR_ROOT": str(REPO_ROOT)},
            home=root / ".home",
            check=False,
        )

    def _closeout_preflight_json(self, root: Path) -> dict:
        result = self._run_closeout_preflight(root)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def _exact_bundle_lint_findings(self, root: Path) -> list[object]:
        return PLAN_LINT.validate_exact_bundle_preflight(
            root / PLAN_REL,
            status_value="Ready for Coder",
            code_draft_refs=[(1, DRAFT_REL)],
            plan_repo_root=root,
        )

    def _same_file_review_text(
        self,
        *,
        status: str,
        aggregate_status: str | None = None,
        marker: str = "",
        blocker_state: str | None = None,
        date: str = "2026-05-07 02:00 MSK",
        target_snapshot: str | None = None,
    ) -> str:
        aggregate_status = aggregate_status or status
        target_line = target_snapshot if target_snapshot is not None else f"PLAN={PLAN_REL}"
        marker_block = f"\n{marker.strip()}\n" if marker.strip() else ""
        blocker_block = ""
        if blocker_state is not None:
            blocker_block = textwrap.dedent(
                f"""\
                ## S1 Blocker

                ### B1
                - Blocker ID: B1
                - Current state: {blocker_state}
                - Classification: same-contract reroute
                - Primary owner gap: Coder
                - Evidence refs: `{REVIEW_REL}#B1`
                """
            )
        review_text = textwrap.dedent(
            f"""\
            # Code review — merge-range (abc1234..def5678)

            **Date:** {date}
            **Target:** {target_line}
            **Status:** {status}

            ## reviewer_code_risk - GPT-5.5 xhigh
            - Lane status: `complete`
            - Target snapshot: `{target_line}`
            - Coverage domains: `correctness`, `tests quality`
            - No findings reason: `N/A (no risk findings)`

            ## reviewer_code_contracts - GPT-5.5 xhigh
            - Lane status: `complete`
            - Target snapshot: `{target_line}`
            - Coverage domains: `plan fidelity`, `docs/registry`
            - No findings reason: `N/A (no contracts findings)`

            ## Lane synthesis / aggregate verdict
            - Source lanes: `reviewer_code_risk`, `reviewer_code_contracts`
            - Canonical mapping: `none`
            - Aggregate status: `{aggregate_status}`
            - Finding: `N/A (findings отсутствуют)`
              - source_lane: `reviewer_code_risk+reviewer_code_contracts`
              - lane_finding_id: `N/A (no lane findings)`
              - synthesis_disposition: `no_findings`
              - canonical_ref: `docs/code_reviews/{PLAN_REL.split('/')[-1]}#Lane-synthesis--aggregate-verdict`
              - audit_status: `done`
              - followup_plan: `N/A`
            """
        )
        sections = [review_text.rstrip()]
        if marker_block.strip():
            sections.append(marker_block.strip())
        if blocker_block.strip():
            sections.append(blocker_block.strip())
        return "\n\n".join(sections) + "\n"

    def _stale_red_after_fix_plan_notes(
        self,
        *,
        target_snapshot: str | None = None,
        lane_status: str | None = "complete",
        stale_note_time: str = "2026-05-07 03:00",
        rerun_note_time: str = "2026-05-07 03:05",
        run_id: str = "reviewer_code_risk:bundle:20260507T030600",
    ) -> str:
        payload = {
            "lane_id": "reviewer_code_risk",
            "run_id": run_id,
            "target_snapshot": target_snapshot if target_snapshot is not None else f"PLAN={PLAN_REL}",
            "findings": [],
            "current": True,
        }
        if lane_status is not None:
            payload["lane_status"] = lane_status
        return textwrap.dedent(
            f"""\
            - Stale note ({stale_note_time}): same review file `{REVIEW_REL}` remains red until rerun
            - Rerun note ({rerun_note_time}): same review file `{REVIEW_REL}` will be rewritten in place

            ## Evidence

            - reviewer_code_risk lane-run artifact:
              ```json
              {json.dumps(payload, indent=2)}
              ```
            """
        )

    def test_owner_runbook_plan_bundle_modes_match_runtime_usage(self) -> None:
        result = run_zsh_fixture(
            "source scripts/planveyor.zsh && planveyor_plan_bundle",
            cwd=REPO_ROOT,
            path=os.environ.get("PATH", os.defpath),
            pybin=str(Path(sys.executable).resolve()),
            check=False,
        )

        self.assertEqual(result.returncode, 1)
        usage_modes = self._extract_plan_bundle_modes(result.stderr)
        self.assertEqual(usage_modes, PLAN_BUNDLE_MODES)

    def test_recovery_plan_option_is_rejected_by_every_non_capture_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._materialize_bundle(root)
            self._commit_all(root, "ordinary fixture")

            for mode in (
                "--print",
                "--check",
                "--preflight",
                "--stage",
                "--commit-ready",
                "--commit-exact",
                "--closeout-json",
                "--verify-rejected",
                "--cleanup-rejected",
            ):
                with self.subTest(mode=mode):
                    result = self._run_shell(
                        root,
                        f"planveyor_plan_bundle {mode} --recovery-plan docs/plans/recovery.md {PLAN_REL}",
                    )
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn(
                        "--recovery-plan is supported only with --capture-rejected",
                        result.stderr,
                    )

    def test_rejected_baseline_capture_cleanup_and_overlap_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            review_sha = self._materialize_rejected_fixture(root)
            head_before = self._git(root, "rev-parse", "HEAD").stdout.strip()
            index_before = self._git(root, "write-tree").stdout.strip()
            ref = f"refs/planveyor/rejected-baselines/{Path(REJECTED_PLAN_REL).stem}/{review_sha}"

            missing = self._run_shell(root, f"planveyor_plan_bundle --verify-rejected {REJECTED_PLAN_REL}")
            self.assertEqual(missing.returncode, 0, missing.stdout + missing.stderr)
            self.assertEqual(json.loads(missing.stdout)["recovery_state"], "capture_required")

            captured = self._run_shell(
                root,
                "planveyor_plan_bundle --capture-rejected "
                f"--recovery-plan {REJECTED_RECOVERY_REL} {REJECTED_PLAN_REL}",
            )
            self.assertEqual(captured.returncode, 0, captured.stdout + captured.stderr)
            capture_payload = json.loads(captured.stdout)
            self.assertEqual(capture_payload["recovery_state"], "cleanup_required")
            self.assertEqual(capture_payload["active_checkout_state"], "rejected_targets_present")
            capture_commit = self._git(root, "rev-parse", ref).stdout.strip()
            self.assertEqual(self._git(root, "show", "-s", "--format=%P", capture_commit).stdout.strip(), head_before)
            self.assertEqual(self._git(root, "write-tree").stdout.strip(), index_before)
            manifest = json.loads(
                self._git(root, "show", f"{capture_commit}:{capture_payload['recovery_manifest_path']}").stdout
            )
            self.assertEqual(manifest["schema"], "planveyor_rejected_baseline.v1")
            self.assertEqual(manifest["recovery_code_draft"], REJECTED_RECOVERY_DRAFT_REL)
            self.assertEqual(manifest["recovery_targets"], [REJECTED_TARGETS[0]])
            self.assertEqual([record["path"] for record in manifest["targets"]], sorted(REJECTED_TARGETS))
            self.assertEqual(len(manifest["routing_carriers"]), 4)
            for record in [*manifest["targets"], *manifest["routing_carriers"]]:
                blob = self._git(root, "cat-file", "blob", record["blob_oid"]).stdout.encode()
                self.assertEqual(hashlib.sha256(blob).hexdigest(), record["sha256"])
            capture_oracle = self._run_oracle_subprocess(root, REJECTED_PLAN_REL)
            self.assertEqual(
                capture_oracle.returncode,
                0,
                capture_oracle.stdout + capture_oracle.stderr,
            )
            self.assertEqual(
                json.loads(capture_oracle.stdout)["terminal_disposition_reason"],
                "accepted_red_durable_capture",
            )

            recaptured = self._run_shell(
                root,
                "planveyor_plan_bundle --capture-rejected "
                f"--recovery-plan {REJECTED_RECOVERY_REL} {REJECTED_PLAN_REL}",
            )
            self.assertEqual(recaptured.returncode, 0, recaptured.stdout + recaptured.stderr)
            self.assertEqual(self._git(root, "rev-parse", ref).stdout.strip(), capture_commit)

            # Simulate an interrupted cleanup that already restored one target.
            (root / REJECTED_TARGETS[0]).write_text(f"baseline {REJECTED_TARGETS[0]}\n", encoding="utf-8")
            cleaned = self._run_shell(root, f"planveyor_plan_bundle --cleanup-rejected {REJECTED_PLAN_REL}")
            self.assertEqual(cleaned.returncode, 0, cleaned.stdout + cleaned.stderr)
            cleanup_payload = json.loads(cleaned.stdout)
            self.assertEqual(cleanup_payload["recovery_state"], "completed")
            self.assertEqual(cleanup_payload["durable_capture_state"], "cleanup_recorded")
            self.assertFalse(cleanup_payload["delivery_green"])
            self.assertTrue(cleanup_payload["bundle_ok"])
            cleanup_commit = self._git(root, "rev-parse", ref).stdout.strip()
            self.assertEqual(self._git(root, "show", "-s", "--format=%P", cleanup_commit).stdout.strip(), capture_commit)
            cleanup = json.loads(
                self._git(root, "show", f"{cleanup_commit}:{cleanup_payload['recovery_cleanup_path']}").stdout
            )
            self.assertEqual(cleanup["schema"], "planveyor_rejected_baseline_cleanup.v1")
            self.assertEqual(cleanup["cleanup_head"], head_before)
            self.assertEqual(self._git(root, "write-tree").stdout.strip(), index_before)
            for rel in REJECTED_TARGETS:
                self.assertEqual((root / rel).read_text(), f"baseline {rel}\n")

            recaptured_after_cleanup = self._run_shell(
                root,
                "planveyor_plan_bundle --capture-rejected "
                f"--recovery-plan {REJECTED_RECOVERY_REL} {REJECTED_PLAN_REL}",
            )
            self.assertEqual(
                recaptured_after_cleanup.returncode,
                0,
                recaptured_after_cleanup.stdout + recaptured_after_cleanup.stderr,
            )
            self.assertEqual(json.loads(recaptured_after_cleanup.stdout)["recovery_state"], "completed")
            self.assertEqual(self._git(root, "rev-parse", ref).stdout.strip(), cleanup_commit)

            (root / REJECTED_TARGETS[0]).write_text("recovery-owned runbook delta\n", encoding="utf-8")
            verified = self._run_shell(root, f"planveyor_plan_bundle --verify-rejected {REJECTED_PLAN_REL}")
            self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
            self.assertEqual(json.loads(verified.stdout)["active_checkout_state"], "recovery_owned_overlap")
            overlap_bytes = (root / REJECTED_TARGETS[0]).read_bytes()
            cleaned_overlap = self._run_shell(
                root,
                f"planveyor_plan_bundle --cleanup-rejected {REJECTED_PLAN_REL}",
            )
            self.assertEqual(
                cleaned_overlap.returncode,
                0,
                cleaned_overlap.stdout + cleaned_overlap.stderr,
            )
            self.assertEqual(
                json.loads(cleaned_overlap.stdout)["cleanup_commit"],
                cleanup_commit,
            )
            self.assertEqual((root / REJECTED_TARGETS[0]).read_bytes(), overlap_bytes)
            forbidden = self._run_shell(root, f"planveyor_plan_bundle --stage {REJECTED_PLAN_REL}")
            self.assertEqual(forbidden.returncode, 2)
            self.assertEqual(json.loads(forbidden.stderr)["reason_code"], "staging_forbidden")

    def test_rejected_baseline_cleanup_publication_is_atomic_after_candidate_validation(
        self,
    ) -> None:
        cases = (
            "candidate_reject",
            "advance_head",
            "claim_ref",
            "invalidate_readback",
            "success",
        )
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                self._init_repo(root)
                review_sha = self._materialize_rejected_fixture(root)
                ref = (
                    f"refs/planveyor/rejected-baselines/{Path(REJECTED_PLAN_REL).stem}/"
                    f"{review_sha}"
                )
                captured = self._run_shell(
                    root,
                    "planveyor_plan_bundle --capture-rejected "
                    f"--recovery-plan {REJECTED_RECOVERY_REL} {REJECTED_PLAN_REL}",
                )
                self.assertEqual(captured.returncode, 0, captured.stdout + captured.stderr)
                capture_commit = self._git(root, "rev-parse", ref).stdout.strip()
                captured_parent = self._git(root, "rev-parse", "HEAD").stdout.strip()

                oracle = root / "scripts/plan_status_oracle.py"
                oracle_text = oracle.read_text(encoding="utf-8")
                marker = "    return cleanup\n\n\ndef validate_accepted_red_durable_ref("
                self.assertIn(marker, oracle_text)
                fixture_injection = (
                    "    test_mode = os.environ.get('PLANVEYOR_TEST_CLEANUP_PUBLICATION')\n"
                    "    if test_mode == 'candidate_reject':\n"
                    "        raise AcceptedRedDurableValidationError(\n"
                    "            'injected cleanup candidate rejection'\n"
                    "        )\n"
                    "    if test_mode == 'advance_head':\n"
                    "        subprocess.run(\n"
                    "            ['git', '-C', str(root), 'commit', '--allow-empty', '-m', "
                    "'injected cleanup HEAD race'],\n"
                    "            check=True,\n"
                    "            capture_output=True,\n"
                    "        )\n"
                    "    if test_mode == 'claim_ref':\n"
                    "        subprocess.run(\n"
                    "            ['git', '-C', str(root), 'update-ref', str(contract['ref']), "
                    "_accepted_red_git_text(root, 'rev-parse', 'HEAD')],\n"
                    "            check=True,\n"
                    "            capture_output=True,\n"
                    "        )\n"
                    "    if test_mode == 'invalidate_readback':\n"
                    "        calls_path = root / '.planveyor-test-cleanup-validator-calls'\n"
                    "        calls = int(calls_path.read_text(encoding='utf-8')) if calls_path.exists() else 0\n"
                    "        calls_path.write_text(str(calls + 1), encoding='utf-8')\n"
                    "        if calls >= 1:\n"
                    "            raise AcceptedRedDurableValidationError(\n"
                    "                'injected strict durable readback rejection'\n"
                    "            )\n"
                    "    return cleanup\n\n\ndef validate_accepted_red_durable_ref("
                )
                oracle.write_text(
                    oracle_text.replace(marker, fixture_injection, 1),
                    encoding="utf-8",
                )
                fixture_env = {
                    "PLANVEYOR_ROOT": str(root),
                    "PLANVEYOR_TEST_CLEANUP_PUBLICATION": case,
                }

                cleaned = self._run_shell(
                    root,
                    f"planveyor_plan_bundle --cleanup-rejected {REJECTED_PLAN_REL}",
                    env_extra=fixture_env,
                )
                for rel in REJECTED_TARGETS:
                    self.assertEqual(
                        (root / rel).read_text(encoding="utf-8"),
                        f"baseline {rel}\n",
                    )

                if case == "candidate_reject":
                    self.assertEqual(cleaned.returncode, 2, cleaned.stdout + cleaned.stderr)
                    self.assertEqual(
                        json.loads(cleaned.stderr)["reason_code"],
                        "recovery_ref_invalid",
                    )
                    self.assertEqual(self._git(root, "rev-parse", ref).stdout.strip(), capture_commit)
                    self.assertEqual(
                        self._git(root, "rev-parse", "HEAD").stdout.strip(),
                        captured_parent,
                    )
                    continue

                if case == "advance_head":
                    self.assertEqual(cleaned.returncode, 2, cleaned.stdout + cleaned.stderr)
                    self.assertEqual(
                        json.loads(cleaned.stderr)["reason_code"],
                        "recovery_ref_cas_conflict",
                    )
                    self.assertEqual(self._git(root, "rev-parse", ref).stdout.strip(), capture_commit)
                    self.assertNotEqual(
                        self._git(root, "rev-parse", "HEAD").stdout.strip(),
                        captured_parent,
                    )
                    continue

                if case == "claim_ref":
                    self.assertEqual(cleaned.returncode, 2, cleaned.stdout + cleaned.stderr)
                    self.assertEqual(
                        json.loads(cleaned.stderr)["reason_code"],
                        "recovery_ref_cas_conflict",
                    )
                    self.assertEqual(
                        self._git(root, "rev-parse", ref).stdout.strip(),
                        captured_parent,
                    )
                    continue

                if case == "invalidate_readback":
                    self.assertEqual(cleaned.returncode, 2, cleaned.stdout + cleaned.stderr)
                    self.assertEqual(
                        json.loads(cleaned.stderr)["reason_code"],
                        "recovery_ref_invalid",
                    )
                    self.assertNotEqual(self._git(root, "rev-parse", ref).stdout.strip(), capture_commit)
                    self.assertEqual(
                        (root / ".planveyor-test-cleanup-validator-calls").read_text(encoding="utf-8"),
                        "2",
                    )
                    continue

                self.assertEqual(cleaned.returncode, 0, cleaned.stdout + cleaned.stderr)
                payload = json.loads(cleaned.stdout)
                cleanup_commit = self._git(root, "rev-parse", ref).stdout.strip()
                self.assertEqual(payload["cleanup_commit"], cleanup_commit)
                self.assertEqual(
                    self._git(root, "show", "-s", "--format=%P", cleanup_commit).stdout.strip(),
                    capture_commit,
                )
                self.assertEqual(
                    self._git(root, "diff", "--name-only", capture_commit, cleanup_commit).stdout.splitlines(),
                    [payload["recovery_cleanup_path"]],
                )
                cleanup = json.loads(
                    self._git(
                        root,
                        "show",
                        f"{cleanup_commit}:{payload['recovery_cleanup_path']}",
                    ).stdout
                )
                self.assertEqual(cleanup["cleanup_head"], captured_parent)
                retried = self._run_shell(
                    root,
                    f"planveyor_plan_bundle --cleanup-rejected {REJECTED_PLAN_REL}",
                    env_extra=fixture_env,
                )
                self.assertEqual(retried.returncode, 0, retried.stdout + retried.stderr)
                self.assertEqual(json.loads(retried.stdout)["cleanup_commit"], cleanup_commit)

    def test_rejected_baseline_capture_blocks_replace_topology_before_publication(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            review_sha = self._materialize_rejected_fixture(root)
            head = self._git(root, "rev-parse", "HEAD").stdout.strip()
            tree = self._git(root, "rev-parse", "HEAD^{tree}").stdout.strip()
            replacement = self._git(
                root,
                "commit-tree",
                tree,
                "-m",
                "replacement fixture",
            ).stdout.strip()
            self._git(root, "replace", head, replacement)
            ref = (
                f"refs/planveyor/rejected-baselines/{Path(REJECTED_PLAN_REL).stem}/"
                f"{review_sha}"
            )
            objects_before = self._git(root, "count-objects", "-v").stdout

            result = self._run_shell(
                root,
                "planveyor_plan_bundle --capture-rejected "
                f"--recovery-plan {REJECTED_RECOVERY_REL} {REJECTED_PLAN_REL}",
            )

            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            error = json.loads(result.stderr)
            self.assertEqual(error["reason_code"], "recovery_ref_invalid")
            self.assertIn("replace refs are forbidden", error["message"])
            self.assertEqual(
                subprocess.run(
                    ["git", "show-ref", "--verify", "--quiet", ref],
                    cwd=root,
                    check=False,
                    capture_output=True,
                ).returncode,
                1,
            )
            self.assertEqual(self._git(root, "count-objects", "-v").stdout, objects_before)

    def test_rejected_doc_review_uses_public_capture_verify_cleanup_closeout_lifecycle(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            doc_review_rel = (
                f"docs/doc_reviews/{Path(REJECTED_PLAN_REL).stem}.md"
            )
            review_sha = self._materialize_rejected_fixture(
                root,
                review_rel=doc_review_rel,
                review_label="Code review (primary)",
            )

            missing = self._run_shell(
                root,
                f"planveyor_plan_bundle --verify-rejected {REJECTED_PLAN_REL}",
            )
            self.assertEqual(missing.returncode, 0, missing.stdout + missing.stderr)
            missing_payload = json.loads(missing.stdout)
            self._assert_accepted_red_public_keys(missing_payload, durable=False)
            self.assertEqual(
                missing_payload["recovery_state"],
                "capture_required",
            )

            captured = self._run_shell(
                root,
                "planveyor_plan_bundle --capture-rejected "
                f"--recovery-plan {REJECTED_RECOVERY_REL} {REJECTED_PLAN_REL}",
            )
            self.assertEqual(captured.returncode, 0, captured.stdout + captured.stderr)
            captured_payload = json.loads(captured.stdout)
            self._assert_accepted_red_public_keys(captured_payload, durable=True)
            self.assertEqual(captured_payload["review_bundle_sha256"], review_sha)
            self.assertEqual(captured_payload["recovery_state"], "cleanup_required")
            capture_manifest = json.loads(
                self._git(
                    root,
                    "show",
                    (
                        f"{captured_payload['capture_commit']}:"
                        f"{captured_payload['recovery_manifest_path']}"
                    ),
                ).stdout
            )
            self.assertEqual(capture_manifest["historical_review"], doc_review_rel)

            verified_before = self._run_shell(
                root,
                f"planveyor_plan_bundle --verify-rejected {REJECTED_PLAN_REL}",
            )
            self.assertEqual(
                verified_before.returncode,
                0,
                verified_before.stdout + verified_before.stderr,
            )
            verified_before_payload = json.loads(verified_before.stdout)
            self._assert_accepted_red_public_keys(
                verified_before_payload,
                durable=True,
            )
            self.assertEqual(
                verified_before_payload["recovery_state"],
                "cleanup_required",
            )

            cleaned = self._run_shell(
                root,
                f"planveyor_plan_bundle --cleanup-rejected {REJECTED_PLAN_REL}",
            )
            self.assertEqual(cleaned.returncode, 0, cleaned.stdout + cleaned.stderr)
            cleaned_payload = json.loads(cleaned.stdout)
            self._assert_accepted_red_public_keys(cleaned_payload, durable=True)
            self.assertEqual(cleaned_payload["recovery_state"], "completed")

            verified_after = self._run_shell(
                root,
                f"planveyor_plan_bundle --verify-rejected {REJECTED_PLAN_REL}",
            )
            self.assertEqual(
                verified_after.returncode,
                0,
                verified_after.stdout + verified_after.stderr,
            )
            verified_payload = json.loads(verified_after.stdout)
            self._assert_accepted_red_public_keys(verified_payload, durable=True)
            self.assertEqual(verified_payload["recovery_state"], "completed")

            closeout = self._run_shell(
                root,
                f"planveyor_plan_bundle --closeout-json {REJECTED_PLAN_REL}",
            )
            self.assertEqual(closeout.returncode, 0, closeout.stdout + closeout.stderr)
            closeout_payload = json.loads(closeout.stdout)
            self._assert_accepted_red_public_keys(closeout_payload, durable=True)
            self.assertEqual(
                closeout_payload["terminal_disposition"],
                "accepted_red_supersession",
            )
            self.assertFalse(closeout_payload["delivery_green"])
            self.assertEqual(closeout_payload["staging_policy"], "forbidden")
            self.assertEqual(closeout_payload["recovery_state"], "completed")

    def test_doc_review_fixture_complete_isolated_public_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            expected_review_bytes = self._materialize_doc_review_fixture(root)
            self.assertEqual(
                (root / DOC_REVIEW_FIXTURE_REVIEW_REL).read_bytes(),
                expected_review_bytes,
            )
            self.assertIn(b"## S1 Blocker\n", expected_review_bytes)
            self.assertIn(b"- Blocker ID: `B1`\n", expected_review_bytes)

            missing = self._run_shell(
                root,
                f"planveyor_plan_bundle --verify-rejected {DOC_REVIEW_FIXTURE_PLAN_REL}",
            )
            self.assertEqual(missing.returncode, 0, missing.stdout + missing.stderr)
            missing_payload = json.loads(missing.stdout)
            self._assert_accepted_red_public_keys(missing_payload, durable=False)
            self.assertEqual(
                missing_payload["recovery_state"],
                "capture_required",
            )

            captured = self._run_shell(
                root,
                "planveyor_plan_bundle --capture-rejected "
                f"--recovery-plan {DOC_REVIEW_FIXTURE_RECOVERY_REL} {DOC_REVIEW_FIXTURE_PLAN_REL}",
            )
            self.assertEqual(captured.returncode, 0, captured.stdout + captured.stderr)
            captured_payload = json.loads(captured.stdout)
            self._assert_accepted_red_public_keys(captured_payload, durable=True)
            capture_manifest = json.loads(
                self._git(
                    root,
                    "show",
                    (
                        f"{captured_payload['capture_commit']}:"
                        f"{captured_payload['recovery_manifest_path']}"
                    ),
                ).stdout
            )
            self.assertEqual(
                capture_manifest["historical_review"],
                DOC_REVIEW_FIXTURE_REVIEW_REL,
            )
            self.assertEqual(captured_payload["recovery_state"], "cleanup_required")

            verified_before = self._run_shell(
                root,
                f"planveyor_plan_bundle --verify-rejected {DOC_REVIEW_FIXTURE_PLAN_REL}",
            )
            self.assertEqual(
                verified_before.returncode,
                0,
                verified_before.stdout + verified_before.stderr,
            )
            verified_before_payload = json.loads(verified_before.stdout)
            self._assert_accepted_red_public_keys(
                verified_before_payload,
                durable=True,
            )
            self.assertEqual(
                verified_before_payload["recovery_state"],
                "cleanup_required",
            )

            cleaned = self._run_shell(
                root,
                f"planveyor_plan_bundle --cleanup-rejected {DOC_REVIEW_FIXTURE_PLAN_REL}",
            )
            self.assertEqual(cleaned.returncode, 0, cleaned.stdout + cleaned.stderr)
            cleaned_payload = json.loads(cleaned.stdout)
            self._assert_accepted_red_public_keys(cleaned_payload, durable=True)
            self.assertEqual(cleaned_payload["recovery_state"], "completed")

            verified_after = self._run_shell(
                root,
                f"planveyor_plan_bundle --verify-rejected {DOC_REVIEW_FIXTURE_PLAN_REL}",
            )
            self.assertEqual(
                verified_after.returncode,
                0,
                verified_after.stdout + verified_after.stderr,
            )
            verified_payload = json.loads(verified_after.stdout)
            self._assert_accepted_red_public_keys(verified_payload, durable=True)
            self.assertEqual(verified_payload["recovery_state"], "completed")

            closeout = self._run_shell(
                root,
                f"planveyor_plan_bundle --closeout-json {DOC_REVIEW_FIXTURE_PLAN_REL}",
            )
            self.assertEqual(closeout.returncode, 0, closeout.stdout + closeout.stderr)
            closeout_payload = json.loads(closeout.stdout)
            self._assert_accepted_red_public_keys(closeout_payload, durable=True)
            self.assertEqual(
                closeout_payload["terminal_disposition"],
                "accepted_red_supersession",
            )
            self.assertEqual(closeout_payload["recovery_state"], "completed")

            docs_closeout = self._run_shell(
                root,
                f"planveyor_docs_closeout {DOC_REVIEW_FIXTURE_PLAN_REL} --json",
            )
            self.assertEqual(
                docs_closeout.returncode,
                0,
                docs_closeout.stdout + docs_closeout.stderr,
            )
            docs_closeout_payload = json.loads(docs_closeout.stdout)
            self.assertEqual(docs_closeout_payload["state"], "completed")
            self.assertIn(
                docs_closeout_payload["final_docs_commit"],
                {"no_op", "landed"},
            )
            self.assertEqual(
                (root / DOC_REVIEW_FIXTURE_REVIEW_REL).read_bytes(),
                expected_review_bytes,
            )

    def test_doc_review_fixture_cleanup_when_captured_target_already_matches_head(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._materialize_doc_review_fixture(root)
            self._commit_all(root, "live 1845 target already materialized")
            head_before = self._git(root, "rev-parse", "HEAD").stdout.strip()
            index_before = self._git(root, "write-tree").stdout.strip()

            captured = self._run_shell(
                root,
                "planveyor_plan_bundle --capture-rejected "
                f"--recovery-plan {DOC_REVIEW_FIXTURE_RECOVERY_REL} {DOC_REVIEW_FIXTURE_PLAN_REL}",
            )
            self.assertEqual(captured.returncode, 0, captured.stdout + captured.stderr)
            captured_payload = json.loads(captured.stdout)
            self.assertEqual(
                captured_payload["active_checkout_state"],
                "rejected_targets_present",
            )
            self.assertEqual(captured_payload["recovery_state"], "cleanup_required")

            manifest = json.loads(
                self._git(
                    root,
                    "show",
                    (
                        f"{captured_payload['capture_commit']}:"
                        f"{captured_payload['recovery_manifest_path']}"
                    ),
                ).stdout
            )
            target_record = manifest["targets"][0]
            head_entry = self._git(
                root,
                "ls-tree",
                "HEAD",
                "--",
                target_record["path"],
            ).stdout.split()
            self.assertEqual(head_entry[0], target_record["mode"])
            self.assertEqual(head_entry[2], target_record["blob_oid"])

            cleaned = self._run_shell(
                root,
                f"planveyor_plan_bundle --cleanup-rejected {DOC_REVIEW_FIXTURE_PLAN_REL}",
            )
            self.assertEqual(cleaned.returncode, 0, cleaned.stdout + cleaned.stderr)
            cleaned_payload = json.loads(cleaned.stdout)
            self.assertEqual(cleaned_payload["active_checkout_state"], "clean")
            self.assertEqual(cleaned_payload["durable_capture_state"], "cleanup_recorded")
            self.assertEqual(cleaned_payload["recovery_state"], "completed")
            self.assertEqual(
                self._git(root, "rev-parse", "HEAD").stdout.strip(),
                head_before,
            )
            self.assertEqual(self._git(root, "write-tree").stdout.strip(), index_before)
            cleanup_commit = cleaned_payload["cleanup_commit"]

            cleaned_again = self._run_shell(
                root,
                f"planveyor_plan_bundle --cleanup-rejected {DOC_REVIEW_FIXTURE_PLAN_REL}",
            )
            self.assertEqual(
                cleaned_again.returncode,
                0,
                cleaned_again.stdout + cleaned_again.stderr,
            )
            self.assertEqual(json.loads(cleaned_again.stdout)["cleanup_commit"], cleanup_commit)

    def test_rejected_cleanup_preserves_mixed_captured_and_head_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._materialize_rejected_fixture(root)
            self._git(root, "add", REJECTED_TARGETS[0])
            self._git(root, "commit", "-m", "materialize one rejected target")
            head_before = self._git(root, "rev-parse", "HEAD").stdout.strip()
            index_before = self._git(root, "write-tree").stdout.strip()

            captured = self._run_shell(
                root,
                "planveyor_plan_bundle --capture-rejected "
                f"--recovery-plan {REJECTED_RECOVERY_REL} {REJECTED_PLAN_REL}",
            )
            self.assertEqual(captured.returncode, 0, captured.stdout + captured.stderr)
            captured_payload = json.loads(captured.stdout)
            self.assertEqual(
                captured_payload["active_checkout_state"],
                "rejected_targets_present",
            )
            self.assertEqual(captured_payload["recovery_state"], "cleanup_required")
            manifest = json.loads(
                self._git(
                    root,
                    "show",
                    (
                        f"{captured_payload['capture_commit']}:"
                        f"{captured_payload['recovery_manifest_path']}"
                    ),
                ).stdout
            )
            captured_oids = {
                record["path"]: record["blob_oid"] for record in manifest["targets"]
            }
            head_oids = {
                rel: self._git(root, "ls-tree", "HEAD", "--", rel).stdout.split()[2]
                for rel in REJECTED_TARGETS
            }
            self.assertEqual(
                captured_oids[REJECTED_TARGETS[0]],
                head_oids[REJECTED_TARGETS[0]],
            )
            self.assertNotEqual(
                captured_oids[REJECTED_TARGETS[1]],
                head_oids[REJECTED_TARGETS[1]],
            )

            cleaned = self._run_shell(
                root,
                f"planveyor_plan_bundle --cleanup-rejected {REJECTED_PLAN_REL}",
            )
            self.assertEqual(cleaned.returncode, 0, cleaned.stdout + cleaned.stderr)
            cleaned_payload = json.loads(cleaned.stdout)
            self.assertEqual(cleaned_payload["active_checkout_state"], "clean")
            self.assertEqual(cleaned_payload["recovery_state"], "completed")
            self.assertEqual(
                self._git(root, "rev-parse", "HEAD").stdout.strip(),
                head_before,
            )
            self.assertEqual(self._git(root, "write-tree").stdout.strip(), index_before)

    def test_accepted_red_embedded_route_consumer_does_not_reconstruct_code_review_path(
        self,
    ) -> None:
        source = PLANVEYOR_SCRIPT.read_text(encoding="utf-8")
        parse_source = source.split("def parse_source(", 1)[1].split(
            "def index_matches_tree(", 1
        )[0]
        is_applicable = source.split("def is_applicable()", 1)[1].split(
            "def verify(", 1
        )[0]
        self.assertNotIn("docs/code_reviews/", parse_source)
        self.assertIn("resolve_accepted_red_review_path", parse_source)
        self.assertIn(
            "validate_accepted_red_successor_topology_rebind",
            parse_source,
        )
        self.assertIn("accepted_red_topology_open_blocker_ids", parse_source)
        self.assertNotIn(
            "ACCEPTED_RED_SUCCESSOR_TOPOLOGY_REBIND_ALLOWLIST",
            parse_source,
        )
        self.assertNotIn("docs/code_reviews/", is_applicable)
        self.assertNotIn("resolve_accepted_red_review_path", is_applicable)
        self.assertIn('scope.get("state") == "architect_accepted"', is_applicable)
        self.assertIn("len(next_plans) == 1", is_applicable)

    def test_accepted_red_topology_rebind_public_bundle_fixture_preserves_phase_one_boundary(
        self,
    ) -> None:
        source_rel = "docs/plans/fixture_topology_source.md"
        successor_rel = "docs/plans/fixture_topology_successor.md"
        source_draft_rel = f"docs/code_drafts/{Path(source_rel).stem}__code_draft.md"
        successor_draft_rel = f"docs/code_drafts/{Path(successor_rel).stem}__code_draft.md"
        source_review_rel = f"docs/code_reviews/{Path(source_rel).stem}.md"
        successor_review_rel = f"docs/code_reviews/{Path(successor_rel).stem}.md"
        recovery_rel = "docs/plans/fixture_topology_recovery.md"
        recovery_draft_rel = "docs/code_drafts/fixture_topology_recovery__code_draft.md"
        target_paths = [
            "scripts/fixture_topology_alpha.py",
            "scripts/fixture_topology_beta.py",
        ]
        historical_target_bytes = {
            target_paths[0]: b"historical fixture topology alpha\n",
            target_paths[1]: b"historical fixture topology beta\n",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root, copy_dispatch_prompts=False)

            def write(rel: str, body: str) -> None:
                fixture_path = root / rel
                fixture_path.parent.mkdir(parents=True, exist_ok=True)
                fixture_path.write_text(body, encoding="utf-8")

            source_meta = {
                "plan_meta": {
                    "cluster": "process",
                    "parent": None,
                    "next_plans": [successor_rel],
                    "depends_on": [],
                    "followups_out": [],
                    "canon_updates": [],
                    "scope_expansion": {
                        "state": "architect_accepted",
                        "target_contour": "decomposition_wave",
                        "source_ref": f"{source_review_rel}#B6",
                        "reason": "fixture topology rebind",
                    },
                }
            }
            successor_meta = {
                "plan_meta": {
                    "cluster": "process",
                    "parent": None,
                    "next_plans": [],
                    "depends_on": [source_rel],
                    "followups_out": [],
                    "canon_updates": [],
                    "scope_expansion": {"state": "n/a"},
                }
            }
            source_draft_meta = {
                "code_draft_meta": {
                    "plan": source_rel,
                    "cluster": "process",
                    "targets": [{"path": rel, "kind": "py"} for rel in target_paths],
                    "deleted_paths": [],
                }
            }
            successor_draft_meta = {
                "code_draft_meta": {
                    "plan": successor_rel,
                    "cluster": "process",
                    "targets": [],
                    "deleted_paths": [],
                }
            }

            def source_review_text(bundle_sha256: str) -> str:
                return (
                    "# Fixture topology source review\n\n"
                    f"**Target:** BUNDLE=current bundle_sha256={bundle_sha256}\n"
                    "**Status:** ❌ S1 blocker\n\n"
                    "## S1 Blocker\n\n"
                    "### B6) fixture blocker\n\n"
                    "- Blocker ID: `B6`\n"
                    "- Current state: `open`\n"
                )

            write(
                source_rel,
                "# Fixture topology source\n\n"
                "**Plan type:** dev\n"
                "**Status:** Superseded\n\n"
                "**Context links (source of truth):**\n"
                f"- Code draft(s): `{source_draft_rel}`\n\n"
                f"```json\n{json.dumps(source_meta, indent=2)}\n```\n\n"
                "## Review artifacts\n"
                f"- Code review (primary): `{source_review_rel}`\n",
            )
            write(
                successor_rel,
                "# Fixture topology successor\n\n"
                "**Plan type:** dev\n"
                "**Status:** Done\n\n"
                f"`{source_review_rel}#B6`\n\n"
                f"```json\n{json.dumps(successor_meta, indent=2)}\n```\n",
            )
            write(
                source_draft_rel,
                f"# Fixture source draft\n\n```json\n{json.dumps(source_draft_meta, indent=2)}\n```\n",
            )
            write(
                successor_draft_rel,
                f"# Fixture successor draft\n\n```json\n{json.dumps(successor_draft_meta, indent=2)}\n```\n",
            )
            write(source_review_rel, source_review_text("0" * 64))
            write(
                successor_review_rel,
                "# Fixture topology successor review\n\n"
                "**Status:** ✅ OK\n",
            )
            for rel, data in historical_target_bytes.items():
                target_path = root / rel
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_bytes(data)

            recovery_meta = {
                "code_draft_meta": {
                    "plan": recovery_rel,
                    "cluster": "process",
                    "targets": [{"path": target_paths[0], "kind": "doc"}],
                    "deleted_paths": [],
                }
            }
            (root / recovery_rel).parent.mkdir(parents=True, exist_ok=True)
            (root / recovery_rel).write_text(
                "# Fixture topology recovery\n\n"
                "**Status:** In progress\n\n"
                f"- Superseded incident plan: `{source_rel}`.\n"
                f"- Code draft(s): `{recovery_draft_rel}`\n",
                encoding="utf-8",
            )
            (root / recovery_draft_rel).parent.mkdir(parents=True, exist_ok=True)
            (root / recovery_draft_rel).write_text(
                "# Fixture topology recovery draft\n\n```json\n"
                + json.dumps(recovery_meta, indent=2)
                + "\n```\n",
                encoding="utf-8",
            )
            self._commit_all(root, "historical target snapshot")
            target_commit = self._git(root, "rev-parse", "HEAD").stdout.strip()
            target_snapshot_ref = "refs/planveyor/recovery-inputs/fixture/targets"
            self._git(root, "update-ref", target_snapshot_ref, target_commit)
            target_bundle, _target_records = PLAN_STATUS_ORACLE._accepted_red_revision_bundle(
                root,
                target_commit,
                target_paths,
            )
            (root / source_review_rel).write_text(
                source_review_text(target_bundle),
                encoding="utf-8",
            )
            self._commit_all(root, "carrier set")
            carrier_commit = self._git(root, "rev-parse", "HEAD").stdout.strip()
            carrier_set_ref = "refs/planveyor/recovery-inputs/fixture/carrier-set-v1"
            self._git(root, "update-ref", carrier_set_ref, carrier_commit)

            for rel in target_paths:
                (root / rel).write_text(f"green phase-one {rel}\n", encoding="utf-8")
            self._commit_all(root, "green phase-one parent")
            green_parent = self._git(root, "rev-parse", "HEAD").stdout.strip()

            target_records = []
            for rel in target_paths:
                data = subprocess.run(
                    ["git", "-C", str(root), "show", f"{target_commit}:{rel}"],
                    check=True,
                    capture_output=True,
                ).stdout
                target_records.append(
                    {
                        "path": rel,
                        "mode": self._git(root, "ls-tree", target_commit, "--", rel)
                        .stdout.split()[0],
                        "blob_oid": self._git(
                            root,
                            "rev-parse",
                            f"{target_commit}:{rel}",
                        ).stdout.strip(),
                        "size_bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                )
            fixture_entry = PLAN_STATUS_ORACLE.AcceptedRedSuccessorTopologyRebind(
                schema="planveyor_accepted_red_successor_topology_rebind.v1",
                rebind_id="fixture-topology-rebind",
                source_plan=source_rel,
                source_draft_rule="same_stem_code_draft",
                source_review=source_review_rel,
                source_review_bundle_sha256=target_bundle,
                source_open_blockers=("B6",),
                source_scope_ref=f"{source_review_rel}#B6",
                successor_plan=successor_rel,
                successor_commit=target_commit,
                successor_plan_blob_oid=self._git(
                    root,
                    "rev-parse",
                    f"{target_commit}:{successor_rel}",
                ).stdout.strip(),
                successor_review=successor_review_rel,
                successor_review_blob_oid=self._git(
                    root,
                    "rev-parse",
                    f"{target_commit}:{successor_review_rel}",
                ).stdout.strip(),
                successor_expected_parent=None,
                successor_requires_source_in_depends_on=True,
                carrier_set_ref=carrier_set_ref,
                carrier_set_commit=carrier_commit,
                carrier_set_tree=self._git(
                    root,
                    "rev-parse",
                    f"{carrier_commit}^{{tree}}",
                ).stdout.strip(),
                carrier_set_parent=target_commit,
                carrier_paths=(
                    "@source_same_stem_code_draft",
                    "@successor_same_stem_code_draft",
                    source_review_rel,
                    successor_review_rel,
                    source_rel,
                    successor_rel,
                ),
                target_snapshot_ref=target_snapshot_ref,
                target_snapshot_commit=target_commit,
                targets=tuple(target_records),
                entry_sha256="",
            )
            identity = PLAN_STATUS_ORACLE._accepted_red_topology_rebind_identity(
                fixture_entry
            )
            fixture_entry = replace(
                fixture_entry,
                entry_sha256=hashlib.sha256(
                    json.dumps(
                        identity,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest(),
            )
            helper = root / "scripts/plan_status_oracle.py"
            helper_source = helper.read_text(encoding="utf-8")

            def write_fixture_helper(*entries: object) -> None:
                payloads = []
                for entry in entries:
                    payload = PLAN_STATUS_ORACLE._accepted_red_topology_rebind_identity(
                        entry
                    )
                    payload["entry_sha256"] = entry.entry_sha256
                    payloads.append(payload)
                helper.write_text(
                    helper_source
                    + "\n_topology_fixtures = json.loads("
                    + repr(json.dumps(payloads, ensure_ascii=False))
                    + ")\n"
                    + "for _topology_fixture in _topology_fixtures:\n"
                    + "    _topology_fixture['source_open_blockers'] = tuple(_topology_fixture['source_open_blockers'])\n"
                    + "    _topology_fixture['carrier_paths'] = tuple(_topology_fixture['carrier_paths'])\n"
                    + "    _topology_fixture['targets'] = tuple(_topology_fixture['targets'])\n"
                    + "ACCEPTED_RED_SUCCESSOR_TOPOLOGY_REBIND_ALLOWLIST = tuple(AcceptedRedSuccessorTopologyRebind(**_topology_fixture) for _topology_fixture in _topology_fixtures)\n",
                    encoding="utf-8",
                )

            def candidate_with_digest(**changes: object) -> object:
                candidate = replace(fixture_entry, **changes, entry_sha256="")
                identity = PLAN_STATUS_ORACLE._accepted_red_topology_rebind_identity(
                    candidate
                )
                return replace(
                    candidate,
                    entry_sha256=hashlib.sha256(
                        json.dumps(
                            identity,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode("utf-8")
                    ).hexdigest(),
                )

            def public_blocked_payload(
                result: subprocess.CompletedProcess[str],
            ) -> dict[str, object]:
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                payloads = []
                for line in result.stderr.splitlines():
                    try:
                        payloads.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
                self.assertTrue(payloads, result.stderr)
                payload = payloads[-1]
                self.assertEqual(
                    payload.get("reason_code"),
                    "accepted_red_closeout_invalid_carrier",
                )
                cause = payload.get("cause")
                self.assertIsInstance(cause, dict)
                self.assertEqual(cause.get("reason_code"), "not_accepted_red")
                return payload

            write_fixture_helper(fixture_entry)

            env = {"PLANVEYOR_ROOT": str(root)}
            pre_recovery = self._run_shell(
                root,
                f"planveyor_plan_bundle --closeout-json {source_rel}",
                env_extra=env,
            )
            self.assertEqual(
                pre_recovery.returncode,
                0,
                pre_recovery.stdout + pre_recovery.stderr,
            )
            pre_payload = json.loads(pre_recovery.stdout)
            self.assertEqual(
                pre_payload["terminal_disposition"],
                "accepted_red_supersession",
            )
            self.assertFalse(pre_payload["delivery_green"])
            self.assertEqual(pre_payload["staging_policy"], "forbidden")
            self.assertTrue(pre_payload["durable_capture_required"])
            self.assertNotEqual(pre_payload["closeout_kind"], "accepted_red_recovered")

            ambient_overrides = {
                "GIT_DIR": str(root / ".git"),
                "GIT_WORK_TREE": str(root),
                "GIT_COMMON_DIR": str(root / ".git"),
                "GIT_INDEX_FILE": str(root / ".git" / "index"),
            }
            for name, value in ambient_overrides.items():
                with self.subTest(ambient_git_authority=name):
                    write_fixture_helper(fixture_entry)
                    blocked = self._run_shell(
                        root,
                        f"planveyor_plan_bundle --closeout-json {source_rel}",
                        env_extra={**env, name: value},
                    )
                    payload = public_blocked_payload(blocked)
                    cause = payload["cause"]
                    self.assertIn("operational-red", str(cause.get("message")))
                    self.assertIn(name, str(cause.get("message")))

            semantic_cases: list[tuple[str, object]] = []

            def add_case(name: str, **changes: object) -> None:
                semantic_cases.append((name, candidate_with_digest(**changes)))

            add_case("schema", schema="planveyor_accepted_red_successor_topology_rebind.v2")
            add_case("source_plan", source_plan="docs/plans/other-source.md")
            add_case("source_draft_rule", source_draft_rule="other_draft_rule")
            add_case("source_review", source_review="docs/code_reviews/other-source.md")
            add_case("source_review_bundle", source_review_bundle_sha256="0" * 64)
            add_case("source_open_blockers", source_open_blockers=("B7",))
            add_case("source_scope_ref", source_scope_ref=f"{source_review_rel}#B7")
            add_case("successor_plan", successor_plan="docs/plans/other-successor.md")
            add_case("successor_commit", successor_commit="0" * 40)
            add_case("successor_plan_blob", successor_plan_blob_oid="0" * 40)
            add_case("successor_review", successor_review="docs/code_reviews/other-successor.md")
            add_case("successor_review_blob", successor_review_blob_oid="0" * 40)
            add_case("successor_expected_parent", successor_expected_parent="unexpected")
            add_case(
                "successor_depends_requirement",
                successor_requires_source_in_depends_on=False,
            )
            add_case(
                "carrier_set_ref",
                carrier_set_ref="refs/planveyor/recovery-inputs/fixture/other-carrier-set",
            )
            add_case("carrier_set_commit", carrier_set_commit="0" * 40)
            add_case("carrier_set_tree", carrier_set_tree="0" * 40)
            add_case("carrier_set_parent", carrier_set_parent="0" * 40)
            add_case(
                "target_snapshot_ref",
                target_snapshot_ref="refs/planveyor/recovery-inputs/fixture/other-targets",
            )
            add_case("target_snapshot_commit", target_snapshot_commit="0" * 40)
            add_case(
                "carrier_source_token",
                carrier_paths=(
                    "@unknown_source_draft",
                    *fixture_entry.carrier_paths[1:],
                ),
            )
            add_case(
                "carrier_successor_token",
                carrier_paths=(
                    fixture_entry.carrier_paths[0],
                    "@unknown_successor_draft",
                    *fixture_entry.carrier_paths[2:],
                ),
            )
            add_case(
                "carrier_membership",
                carrier_paths=(
                    *fixture_entry.carrier_paths[:-1],
                    "docs/plans/260900_0000_unrelated.md",
                ),
            )
            add_case(
                "carrier_cardinality",
                carrier_paths=fixture_entry.carrier_paths[:-1],
            )
            add_case(
                "carrier_order",
                carrier_paths=(
                    fixture_entry.carrier_paths[1],
                    fixture_entry.carrier_paths[0],
                    *fixture_entry.carrier_paths[2:],
                ),
            )
            add_case("target_cardinality", targets=fixture_entry.targets[:-1])
            add_case(
                "target_order",
                targets=(
                    fixture_entry.targets[1],
                    fixture_entry.targets[0],
                    *fixture_entry.targets[2:],
                ),
            )
            for index, record in enumerate(fixture_entry.targets):
                for field, value in (
                    ("path", f"{record['path']}.wrong"),
                    (
                        "mode",
                        "100755" if record["mode"] == "100644" else "100644",
                    ),
                    ("blob_oid", "0" * 40),
                    ("size_bytes", int(record["size_bytes"]) + 1),
                    ("sha256", "0" * 64),
                ):
                    targets = [dict(item) for item in fixture_entry.targets]
                    targets[index][field] = value
                    add_case(f"target_{index + 1}_{field}", targets=tuple(targets))

            raw_digest = replace(fixture_entry, entry_sha256="0" * 64)
            for case, candidate in (("entry_digest", raw_digest), *semantic_cases):
                with self.subTest(public_frozen_identity=case):
                    if case != "entry_digest":
                        self.assertEqual(
                            candidate.entry_sha256,
                            hashlib.sha256(
                                json.dumps(
                                    PLAN_STATUS_ORACLE._accepted_red_topology_rebind_identity(
                                        candidate
                                    ),
                                    ensure_ascii=False,
                                    sort_keys=True,
                                    separators=(",", ":"),
                                ).encode("utf-8")
                            ).hexdigest(),
                        )
                    write_fixture_helper(candidate)
                    public_blocked_payload(
                        self._run_shell(
                            root,
                            f"planveyor_plan_bundle --closeout-json {source_rel}",
                            env_extra=env,
                        )
                    )

            with self.subTest(public_frozen_identity="duplicate_entry"):
                write_fixture_helper(fixture_entry, fixture_entry)
                public_blocked_payload(
                    self._run_shell(
                        root,
                        f"planveyor_plan_bundle --closeout-json {source_rel}",
                        env_extra=env,
                    )
                )

            write_fixture_helper(fixture_entry)

            index_before = self._git(root, "write-tree").stdout.strip()
            for rel in target_paths:
                (root / rel).write_bytes(historical_target_bytes[rel])
            captured = self._run_shell(
                root,
                f"planveyor_plan_bundle --capture-rejected --recovery-plan {recovery_rel} {source_rel}",
                env_extra=env,
            )
            self.assertEqual(captured.returncode, 0, captured.stdout + captured.stderr)
            captured_payload = json.loads(captured.stdout)
            self.assertEqual(captured_payload["recovery_state"], "cleanup_required")
            self.assertEqual(
                self._git(root, "rev-parse", "HEAD").stdout.strip(),
                green_parent,
            )
            self.assertEqual(self._git(root, "write-tree").stdout.strip(), index_before)

            verified = self._run_shell(
                root,
                f"planveyor_plan_bundle --verify-rejected {source_rel}",
                env_extra=env,
            )
            self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
            cleaned = self._run_shell(
                root,
                f"planveyor_plan_bundle --cleanup-rejected {source_rel}",
                env_extra=env,
            )
            self.assertEqual(cleaned.returncode, 0, cleaned.stdout + cleaned.stderr)
            cleaned_payload = json.loads(cleaned.stdout)
            self.assertEqual(cleaned_payload["recovery_state"], "completed")
            self.assertEqual(cleaned_payload["closeout_kind"], "accepted_red_recovered")
            self.assertEqual(
                self._git(root, "rev-parse", "HEAD").stdout.strip(),
                green_parent,
            )
            self.assertEqual(self._git(root, "write-tree").stdout.strip(), index_before)
            for rel in target_paths:
                expected = subprocess.run(
                    ["git", "-C", str(root), "show", f"HEAD:{rel}"],
                    check=True,
                    capture_output=True,
                ).stdout
                self.assertEqual((root / rel).read_bytes(), expected)

    def test_accepted_red_rebind_projects_shared_effective_contract_without_cli_growth(
        self,
    ) -> None:
        source = PLANVEYOR_SCRIPT.read_text(encoding="utf-8")
        verify_source = source.split("def verify(", 1)[1].split(
            "def base_payload(",
            1,
        )[0]
        self.assertIn(
            "recovery_contract = dict(durable.recovery_contract)",
            verify_source,
        )
        self.assertIn(
            'overlap = set(str(item) for item in recovery_contract["recovery_targets"])',
            verify_source,
        )
        self.assertIn(
            'recovery_targets=recovery_contract["recovery_targets"]',
            verify_source,
        )
        self.assertIn(
            "recovery_contract_state=durable.recovery_contract_state",
            verify_source,
        )
        self.assertNotIn("recovery_generation", source)
        self.assertNotIn("--generate-rejected-recovery", source)
        self.assertEqual(
            ACCEPTED_RED_DURABLE_KEYS - ACCEPTED_RED_CLOSEOUT_CORE_KEYS,
            {
                "recovery_plan",
                "recovery_code_draft",
                "recovery_targets",
                "recovery_contract_state",
                "captured_parent",
                "capture_commit",
                "cleanup_commit",
                "durable_capture_state",
                "active_checkout_state",
                "recovery_state",
            },
        )

    def test_rejected_baseline_exact_legacy_bridge_migrates_without_generic_v1_fallback(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root, copy_dispatch_prompts=False)
            producer = root / "scripts/review_target_snapshot.py"
            current_producer = producer.read_text(encoding="utf-8")
            producer.write_text(
                current_producer.replace(
                    '"review_target_snapshot.v2"',
                    '"review_target_snapshot.v1"',
                ).replace(
                    '"review_target_snapshot.hash_basis.v2"',
                    '"review_target_snapshot.hash_basis.v1"',
                ),
                encoding="utf-8",
            )
            self._commit_all(root, "historical v1 producer")
            producer_commit = self._git(root, "rev-parse", "HEAD").stdout.strip()
            producer_blob_oid = self._git(
                root,
                "rev-parse",
                f"{producer_commit}:scripts/review_target_snapshot.py",
            ).stdout.strip()
            producer.write_text(current_producer, encoding="utf-8")

            strict_v2_sha = self._materialize_rejected_fixture(root)
            legacy_v1_sha = self._legacy_v1_bundle_sha(root, REJECTED_TARGETS)
            self.assertNotEqual(strict_v2_sha, legacy_v1_sha)
            review = root / REJECTED_REVIEW_REL
            review.write_text(
                review.read_text(encoding="utf-8").replace(
                    strict_v2_sha,
                    legacy_v1_sha,
                ),
                encoding="utf-8",
            )
            ref = (
                f"refs/planveyor/rejected-baselines/{Path(REJECTED_PLAN_REL).stem}/"
                f"{legacy_v1_sha}"
            )

            without_bridge = self._run_shell(
                root,
                "planveyor_plan_bundle --capture-rejected "
                f"--recovery-plan {REJECTED_RECOVERY_REL} {REJECTED_PLAN_REL}",
            )
            self.assertEqual(
                without_bridge.returncode,
                2,
                without_bridge.stdout + without_bridge.stderr,
            )
            self.assertEqual(
                json.loads(without_bridge.stderr)["reason_code"],
                "snapshot_mismatch",
            )
            self.assertNotEqual(
                subprocess.run(
                    ["git", "rev-parse", "--verify", "--quiet", ref],
                    cwd=root,
                    check=False,
                ).returncode,
                0,
            )

            bridge = self._materialize_snapshot_bridge(
                root,
                strict_v2_sha=strict_v2_sha,
                legacy_v1_sha=legacy_v1_sha,
                producer_commit=producer_commit,
                producer_blob_oid=producer_blob_oid,
            )
            self._allowlist_snapshot_bridge(root, bridge)
            bridge_env = {"PLANVEYOR_ROOT": str(root)}
            uncommitted = self._run_shell(
                root,
                "planveyor_plan_bundle --capture-rejected "
                f"--recovery-plan {REJECTED_RECOVERY_REL} {REJECTED_PLAN_REL}",
                env_extra=bridge_env,
            )
            self.assertEqual(
                uncommitted.returncode,
                2,
                uncommitted.stdout + uncommitted.stderr,
            )
            self.assertEqual(
                json.loads(uncommitted.stderr)["reason_code"],
                "snapshot_bridge_carrier_uncommitted",
            )
            self._git(
                root,
                "add",
                REJECTED_RECOVERY_REL,
                REJECTED_REVIEW_REL,
                "scripts/plan_status_oracle.py",
            )
            self._git(root, "commit", "-m", "allow exact synthetic bridge")

            successor = root / REJECTED_SUCCESSOR_REL
            successor_head = successor.read_text(encoding="utf-8")
            successor.write_text(successor_head + "\nindex-only drift\n", encoding="utf-8")
            self._git(root, "add", REJECTED_SUCCESSOR_REL)
            successor.write_text(successor_head, encoding="utf-8")
            staged_carrier = self._run_shell(
                root,
                "planveyor_plan_bundle --capture-rejected "
                f"--recovery-plan {REJECTED_RECOVERY_REL} {REJECTED_PLAN_REL}",
                env_extra=bridge_env,
            )
            self.assertEqual(staged_carrier.returncode, 2)
            self.assertEqual(
                json.loads(staged_carrier.stderr)["reason_code"],
                "snapshot_bridge_carrier_uncommitted",
            )
            self.assertNotEqual(
                subprocess.run(
                    ["git", "rev-parse", "--verify", "--quiet", ref],
                    cwd=root,
                    check=False,
                ).returncode,
                0,
            )
            self._git(root, "reset", "HEAD", "--", REJECTED_SUCCESSOR_REL)

            producer = root / "scripts/review_target_snapshot.py"
            producer_text = producer.read_text(encoding="utf-8")
            print_line = "    print(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True))\n"
            self.assertIn(print_line, producer_text)
            producer.write_text(
                producer_text.replace(
                    print_line,
                    "    marker = Path(args.project_root) / '.planveyor-test-mutate-carrier'\n"
                    "    if marker.exists():\n"
                    f"        carrier = Path(args.project_root) / {REJECTED_SUCCESSOR_REL!r}\n"
                    "        carrier.write_text(carrier.read_text(encoding='utf-8') + "
                    "'\\nproducer race drift\\n', encoding='utf-8')\n"
                    + print_line,
                    1,
                ),
                encoding="utf-8",
            )
            self._git(root, "add", "scripts/review_target_snapshot.py")
            self._git(root, "commit", "-m", "add deterministic carrier race hook")
            (root / ".planveyor-test-mutate-carrier").write_text("1\n", encoding="utf-8")
            raced_carrier = self._run_shell(
                root,
                "planveyor_plan_bundle --capture-rejected "
                f"--recovery-plan {REJECTED_RECOVERY_REL} {REJECTED_PLAN_REL}",
                env_extra=bridge_env,
            )
            self.assertEqual(raced_carrier.returncode, 2)
            self.assertEqual(
                json.loads(raced_carrier.stderr)["reason_code"],
                "snapshot_bridge_carrier_uncommitted",
            )
            self.assertNotEqual(
                subprocess.run(
                    ["git", "rev-parse", "--verify", "--quiet", ref],
                    cwd=root,
                    check=False,
                ).returncode,
                0,
            )
            (root / ".planveyor-test-mutate-carrier").unlink()
            successor.write_text(successor_head, encoding="utf-8")

            oracle = root / "scripts/plan_status_oracle.py"
            oracle_text = oracle.read_text(encoding="utf-8")
            validation_body = (
                "    _accepted_red_validate_manifest(root, capture_commit, contract)\n"
            )
            self.assertIn(validation_body, oracle_text)
            oracle.write_text(
                oracle_text.replace(
                    "import json\n",
                    "import json\nimport os\n",
                    1,
                ).replace(
                    validation_body,
                    validation_body
                    + "    test_mode = os.environ.get('PLANVEYOR_TEST_CAPTURE_VALIDATOR')\n"
                    + "    if test_mode == 'reject':\n"
                    + "        raise AcceptedRedDurableValidationError('injected candidate rejection')\n"
                    + "    if test_mode == 'advance_head':\n"
                    + "        subprocess.run(['git', '-C', str(root), 'commit', '--allow-empty', "
                    + "'-m', 'injected HEAD race'], check=True, capture_output=True)\n"
                    + "    if test_mode == 'claim_ref':\n"
                    + "        subprocess.run(['git', '-C', str(root), 'update-ref', "
                    + "str(contract['ref']), _accepted_red_git_text(root, 'rev-parse', 'HEAD')], "
                    + "check=True, capture_output=True)\n",
                    1,
                ),
                encoding="utf-8",
            )
            self._git(root, "add", "scripts/plan_status_oracle.py")
            self._git(root, "commit", "-m", "add deterministic capture publication hooks")

            rejected_candidate = self._run_shell(
                root,
                "planveyor_plan_bundle --capture-rejected "
                f"--recovery-plan {REJECTED_RECOVERY_REL} {REJECTED_PLAN_REL}",
                env_extra={
                    **bridge_env,
                    "PLANVEYOR_TEST_CAPTURE_VALIDATOR": "reject",
                },
            )
            self.assertEqual(rejected_candidate.returncode, 2)
            self.assertEqual(
                json.loads(rejected_candidate.stderr)["reason_code"],
                "recovery_ref_invalid",
            )
            self.assertNotEqual(
                subprocess.run(
                    ["git", "rev-parse", "--verify", "--quiet", ref],
                    cwd=root,
                    check=False,
                ).returncode,
                0,
            )

            advanced_head = self._run_shell(
                root,
                "planveyor_plan_bundle --capture-rejected "
                f"--recovery-plan {REJECTED_RECOVERY_REL} {REJECTED_PLAN_REL}",
                env_extra={
                    **bridge_env,
                    "PLANVEYOR_TEST_CAPTURE_VALIDATOR": "advance_head",
                },
            )
            self.assertEqual(advanced_head.returncode, 2)
            self.assertEqual(
                json.loads(advanced_head.stderr)["reason_code"],
                "recovery_ref_cas_conflict",
            )
            self.assertNotEqual(
                subprocess.run(
                    ["git", "rev-parse", "--verify", "--quiet", ref],
                    cwd=root,
                    check=False,
                ).returncode,
                0,
            )

            competing_parent = self._git(root, "rev-parse", "HEAD").stdout.strip()
            claimed_ref = self._run_shell(
                root,
                "planveyor_plan_bundle --capture-rejected "
                f"--recovery-plan {REJECTED_RECOVERY_REL} {REJECTED_PLAN_REL}",
                env_extra={
                    **bridge_env,
                    "PLANVEYOR_TEST_CAPTURE_VALIDATOR": "claim_ref",
                },
            )
            self.assertEqual(claimed_ref.returncode, 2)
            self.assertEqual(
                json.loads(claimed_ref.stderr)["reason_code"],
                "recovery_ref_cas_conflict",
            )
            self.assertEqual(
                self._git(root, "rev-parse", ref).stdout.strip(),
                competing_parent,
            )
            self._git(root, "update-ref", "-d", ref, competing_parent)

            captured = self._run_shell(
                root,
                "planveyor_plan_bundle --capture-rejected "
                f"--recovery-plan {REJECTED_RECOVERY_REL} {REJECTED_PLAN_REL}",
                env_extra=bridge_env,
            )
            self.assertEqual(captured.returncode, 0, captured.stdout + captured.stderr)
            capture_payload = json.loads(captured.stdout)
            self.assertEqual(capture_payload["recovery_state"], "cleanup_required")
            capture_commit = self._git(root, "rev-parse", ref).stdout.strip()
            manifest = json.loads(
                self._git(
                    root,
                    "show",
                    f"{capture_commit}:{capture_payload['recovery_manifest_path']}",
                ).stdout
            )
            self.assertEqual(manifest["snapshot_bridge"], bridge)
            self.assertEqual(
                manifest["recovery_plan_blob_oid"],
                self._git(root, "rev-parse", f"HEAD:{REJECTED_RECOVERY_REL}").stdout.strip(),
            )
            self.assertEqual(
                manifest["recovery_code_draft_blob_oid"],
                self._git(
                    root,
                    "rev-parse",
                    f"HEAD:{REJECTED_RECOVERY_DRAFT_REL}",
                ).stdout.strip(),
            )

            recovery = root / REJECTED_RECOVERY_REL
            recovery_text = recovery.read_text(encoding="utf-8")
            recovery.write_text(
                recovery_text.replace(strict_v2_sha, "0" * 64),
                encoding="utf-8",
            )
            drifted = self._run_shell(
                root,
                f"planveyor_plan_bundle --verify-rejected {REJECTED_PLAN_REL}",
                env_extra=bridge_env,
            )
            self.assertEqual(drifted.returncode, 0, drifted.stdout + drifted.stderr)
            self.assertEqual(
                json.loads(drifted.stdout)["durable_capture_state"],
                "captured",
            )
            self.assertEqual(
                json.loads(drifted.stdout)["recovery_contract_state"],
                "manifest_frozen",
            )
            self.assertEqual(self._git(root, "rev-parse", ref).stdout.strip(), capture_commit)
            recovery.write_text(recovery_text, encoding="utf-8")

            cleaned = self._run_shell(
                root,
                f"planveyor_plan_bundle --cleanup-rejected {REJECTED_PLAN_REL}",
                env_extra=bridge_env,
            )
            self.assertEqual(cleaned.returncode, 0, cleaned.stdout + cleaned.stderr)
            self.assertEqual(json.loads(cleaned.stdout)["recovery_state"], "completed")

    def test_rejected_baseline_legacy_bridge_rejects_unavailable_producer_before_ref_mutation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            producer = root / "scripts/review_target_snapshot.py"
            current_producer = producer.read_text(encoding="utf-8")
            producer.write_text(
                current_producer.replace(
                    '"review_target_snapshot.v2"',
                    '"review_target_snapshot.v1"',
                ).replace(
                    '"review_target_snapshot.hash_basis.v2"',
                    '"review_target_snapshot.hash_basis.v1"',
                ),
                encoding="utf-8",
            )
            self._commit_all(root, "historical v1 producer")
            producer_commit = self._git(root, "rev-parse", "HEAD").stdout.strip()
            producer_blob_oid = self._git(
                root,
                "rev-parse",
                f"{producer_commit}:scripts/review_target_snapshot.py",
            ).stdout.strip()
            producer.write_text(current_producer, encoding="utf-8")
            strict_v2_sha = self._materialize_rejected_fixture(root)
            legacy_v1_sha = self._legacy_v1_bundle_sha(root, REJECTED_TARGETS)
            bridge = self._materialize_snapshot_bridge(
                root,
                strict_v2_sha=strict_v2_sha,
                legacy_v1_sha=legacy_v1_sha,
                producer_commit=producer_commit,
                producer_blob_oid=producer_blob_oid,
            )
            ref = (
                f"refs/planveyor/rejected-baselines/{Path(REJECTED_PLAN_REL).stem}/"
                f"{legacy_v1_sha}"
            )
            unallowlisted = self._run_shell(
                root,
                "planveyor_plan_bundle --capture-rejected "
                f"--recovery-plan {REJECTED_RECOVERY_REL} {REJECTED_PLAN_REL}",
            )
            self.assertEqual(
                unallowlisted.returncode,
                2,
                unallowlisted.stdout + unallowlisted.stderr,
            )
            unallowlisted_payload = json.loads(unallowlisted.stderr)
            self.assertEqual(
                unallowlisted_payload["reason_code"],
                "recovery_plan_invalid",
            )
            self.assertIn("not allowlisted", unallowlisted_payload["message"])
            recovery = root / REJECTED_RECOVERY_REL
            recovery.write_text(
                recovery.read_text(encoding="utf-8").replace(
                    str(bridge["producer_blob_oid"]),
                    "f" * 40,
                ),
                encoding="utf-8",
            )
            captured = self._run_shell(
                root,
                "planveyor_plan_bundle --capture-rejected "
                f"--recovery-plan {REJECTED_RECOVERY_REL} {REJECTED_PLAN_REL}",
            )

            self.assertEqual(captured.returncode, 2, captured.stdout + captured.stderr)
            self.assertEqual(
                json.loads(captured.stderr)["reason_code"],
                "recovery_plan_invalid",
            )
            self.assertNotEqual(
                subprocess.run(
                    ["git", "rev-parse", "--verify", "--quiet", ref],
                    cwd=root,
                    check=False,
                ).returncode,
                0,
            )

    def test_rejected_baseline_legacy_bridge_rejects_current_hash_or_target_mode_drift(
        self,
    ) -> None:
        for case in (
            "current_hash",
            "target_mode",
            "review_hash",
            "source_plan",
            "extra_key",
            "duplicate_key",
            "path_traversal",
        ):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                self._init_repo(root)
                producer = root / "scripts/review_target_snapshot.py"
                current_producer = producer.read_text(encoding="utf-8")
                producer.write_text(
                    current_producer.replace(
                        '"review_target_snapshot.v2"',
                        '"review_target_snapshot.v1"',
                    ).replace(
                        '"review_target_snapshot.hash_basis.v2"',
                        '"review_target_snapshot.hash_basis.v1"',
                    ),
                    encoding="utf-8",
                )
                self._commit_all(root, "historical v1 producer")
                producer_commit = self._git(root, "rev-parse", "HEAD").stdout.strip()
                producer_blob_oid = self._git(
                    root,
                    "rev-parse",
                    f"{producer_commit}:scripts/review_target_snapshot.py",
                ).stdout.strip()
                producer.write_text(current_producer, encoding="utf-8")
                strict_v2_sha = self._materialize_rejected_fixture(root)
                legacy_v1_sha = self._legacy_v1_bundle_sha(root, REJECTED_TARGETS)
                self._materialize_snapshot_bridge(
                    root,
                    strict_v2_sha=strict_v2_sha,
                    legacy_v1_sha=legacy_v1_sha,
                    producer_commit=producer_commit,
                    producer_blob_oid=producer_blob_oid,
                )
                recovery = root / REJECTED_RECOVERY_REL
                recovery_text = recovery.read_text(encoding="utf-8")
                if case == "current_hash":
                    recovery_text = recovery_text.replace(
                        strict_v2_sha,
                        "0" * 64,
                    )
                elif case == "target_mode":
                    recovery_text = recovery_text.replace(
                        '"git_mode": "100644"',
                        '"git_mode": "100755"',
                        1,
                    )
                elif case == "review_hash":
                    recovery_text = recovery_text.replace(
                        f'"review_bundle_sha256": "{legacy_v1_sha}"',
                        f'"review_bundle_sha256": "{"0" * 64}"',
                    )
                elif case == "source_plan":
                    recovery_text = recovery_text.replace(
                        f'"source_plan": "{REJECTED_PLAN_REL}"',
                        '"source_plan": "docs/plans/wrong_source.md"',
                    )
                elif case == "extra_key":
                    recovery_text = recovery_text.replace(
                        '"schema": "planveyor_accepted_red_snapshot_bridge.v1",',
                        '"schema": "planveyor_accepted_red_snapshot_bridge.v1",\n'
                        '    "extra": true,',
                    )
                elif case == "duplicate_key":
                    recovery_text = recovery_text.replace(
                        '"schema": "planveyor_accepted_red_snapshot_bridge.v1",',
                        '"schema": "planveyor_accepted_red_snapshot_bridge.v1",\n'
                        '    "schema": "planveyor_accepted_red_snapshot_bridge.v1",',
                    )
                else:
                    recovery_text = recovery_text.replace(
                        f'"path": "{REJECTED_TARGETS[0]}"',
                        '"path": "../outside.md"',
                    )
                recovery.write_text(recovery_text, encoding="utf-8")
                ref = (
                    f"refs/planveyor/rejected-baselines/{Path(REJECTED_PLAN_REL).stem}/"
                    f"{legacy_v1_sha}"
                )

                captured = self._run_shell(
                    root,
                    "planveyor_plan_bundle --capture-rejected "
                    f"--recovery-plan {REJECTED_RECOVERY_REL} {REJECTED_PLAN_REL}",
                )

                self.assertEqual(captured.returncode, 2, captured.stdout + captured.stderr)
                self.assertEqual(
                    json.loads(captured.stderr)["reason_code"],
                    "recovery_plan_invalid",
                )
                self.assertNotEqual(
                    subprocess.run(
                        ["git", "rev-parse", "--verify", "--quiet", ref],
                        cwd=root,
                        check=False,
                    ).returncode,
                    0,
                )

    def test_rejected_baseline_capture_mode_only_provider_replacement_fails_before_ref_or_index_mutation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            review_sha = self._materialize_rejected_fixture(root)
            ref = (
                f"refs/planveyor/rejected-baselines/{Path(REJECTED_PLAN_REL).stem}/"
                f"{review_sha}"
            )
            head_before = self._git(root, "rev-parse", "HEAD").stdout.strip()
            index_before = self._git(root, "write-tree").stdout.strip()
            helper = root / "scripts" / "review_target_snapshot.py"
            implementation = root / "scripts" / "review_target_snapshot_impl.py"
            helper.rename(implementation)
            helper.write_text(
                textwrap.dedent(
                    """\
                    from __future__ import annotations

                    import json
                    import os
                    from pathlib import Path
                    import sys

                    from review_target_snapshot_impl import *


                    if __name__ == "__main__":
                        project_root = Path(
                            sys.argv[sys.argv.index("--project-root") + 1]
                        ).resolve()
                        payload = build_current_bundle_snapshot(
                            sys.argv[1],
                            project_root=project_root,
                        )
                        target = project_root / os.environ["PLANVEYOR_TEST_CAPTURE_SWAP_REL"]
                        target.chmod(target.stat().st_mode | 0o100)
                        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
                    """
                ),
                encoding="utf-8",
            )

            captured = self._run_shell(
                root,
                "planveyor_plan_bundle --capture-rejected "
                f"--recovery-plan {REJECTED_RECOVERY_REL} {REJECTED_PLAN_REL}",
                env_extra={
                    "PLANVEYOR_TEST_CAPTURE_SWAP_REL": REJECTED_TARGETS[0],
                },
            )

            self.assertEqual(captured.returncode, 2, captured.stdout + captured.stderr)
            self.assertEqual(
                json.loads(captured.stderr)["reason_code"],
                "snapshot_mismatch",
            )
            ref_probe = subprocess.run(
                ["git", "rev-parse", "--verify", "--quiet", ref],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(ref_probe.returncode, 0)
            self.assertEqual(
                self._git(root, "rev-parse", "HEAD").stdout.strip(),
                head_before,
            )
            self.assertEqual(self._git(root, "write-tree").stdout.strip(), index_before)
            self.assertEqual(
                (root / REJECTED_TARGETS[0]).read_text(encoding="utf-8"),
                f"rejected {REJECTED_TARGETS[0]}\n",
            )
            self.assertTrue((root / REJECTED_TARGETS[0]).stat().st_mode & 0o100)

    def test_rejected_baseline_b5_only_lineage_reuses_one_snapshot_per_target(self) -> None:
        historical = textwrap.dedent(
            """\

            ## Historical blocker reconciliation

            - B1: historical-fixed
            - B2: historical-fixed
            - B3: historical-fixed
            - B4: historical-fixed
            """
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._materialize_rejected_fixture(
                root,
                blocker_ids=("B5",),
                historical_text=historical,
            )
            captured = self._run_shell(
                root,
                "planveyor_plan_bundle --capture-rejected "
                f"--recovery-plan {REJECTED_RECOVERY_REL} {REJECTED_PLAN_REL}",
            )
            self.assertEqual(captured.returncode, 0, captured.stdout + captured.stderr)
            cleaned = self._run_shell(
                root,
                f"planveyor_plan_bundle --cleanup-rejected {REJECTED_PLAN_REL}",
            )
            self.assertEqual(cleaned.returncode, 0, cleaned.stdout + cleaned.stderr)
            (root / REJECTED_TARGETS[0]).write_text(
                "recovery-owned B5 delta\n",
                encoding="utf-8",
            )

            self._install_counting_identity_wrapper(root, target_paths=REJECTED_TARGETS)
            count_path = root / ".snapshot-count"
            verified = self._run_shell(
                root,
                f"planveyor_plan_bundle --verify-rejected {REJECTED_PLAN_REL}",
                env_extra={"PLANVEYOR_TEST_SNAPSHOT_COUNT_PATH": str(count_path)},
            )

            self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
            self.assertEqual(
                json.loads(verified.stdout)["active_checkout_state"],
                "recovery_owned_overlap",
            )
            counts = count_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(sorted(counts), sorted(REJECTED_TARGETS))
            self.assertEqual(
                Path(PLANVEYOR_SCRIPT).read_text(encoding="utf-8").count(
                    'for blocker in ("B1", "B2", "B3")'
                ),
                0,
            )

    def test_rejected_baseline_real_subprocess_parity_for_1151_terminal_ref_lifecycle(
        self,
    ) -> None:
        source_stem = (
            "260722_1151_process_censor_machine_owned_receipt_skeleton_and_enforced_validation"
        )
        successor_stem = (
            "260723_1756_process_shared_plan_mutation_authority_censor_receipt_decomposition"
        )
        recovery_stem = "260723_1904_process_superseded_red_baseline_closeout_recovery"
        source_rel = f"docs/plans/{source_stem}.md"
        draft_rel = f"docs/code_drafts/{source_stem}__code_draft.md"
        review_rel = f"docs/code_reviews/{source_stem}.md"
        successor_rel = f"docs/plans/{successor_stem}.md"
        recovery_rel = f"docs/plans/{recovery_stem}.md"
        recovery_draft_rel = f"docs/code_drafts/{recovery_stem}__code_draft.md"
        verdict_fields = (
            "terminal_disposition",
            "staging_policy",
            "durable_capture_required",
            "terminal_disposition_reason",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._materialize_rejected_fixture(
                root,
                source_rel=source_rel,
                draft_rel=draft_rel,
                review_rel=review_rel,
                successor_rel=successor_rel,
                recovery_rel=recovery_rel,
                recovery_draft_rel=recovery_draft_rel,
                blocker_ids=("B1", "B2", "B3"),
            )
            captured = self._run_shell(
                root,
                "planveyor_plan_bundle --capture-rejected "
                f"--recovery-plan {recovery_rel} {source_rel}",
            )
            self.assertEqual(captured.returncode, 0, captured.stdout + captured.stderr)
            cleaned = self._run_shell(
                root,
                f"planveyor_plan_bundle --cleanup-rejected {source_rel}",
            )
            self.assertEqual(cleaned.returncode, 0, cleaned.stdout + cleaned.stderr)
            recovery = root / recovery_rel
            recovery.write_text(
                recovery.read_text(encoding="utf-8").replace(
                    "**Status:** In progress",
                    "**Status:** Superseded",
                ),
                encoding="utf-8",
            )

            oracle = self._run_oracle_subprocess(root, source_rel)
            shell = self._run_shell(
                root,
                f"planveyor_plan_bundle --verify-rejected {source_rel}",
            )

            self.assertEqual(oracle.returncode, 0, oracle.stdout + oracle.stderr)
            self.assertEqual(shell.returncode, 0, shell.stdout + shell.stderr)
            oracle_payload = json.loads(oracle.stdout)
            shell_payload = json.loads(shell.stdout)
            self.assertEqual(
                {key: shell_payload[key] for key in verdict_fields},
                {key: oracle_payload[key] for key in verdict_fields},
            )
            self.assertEqual(
                shell_payload["terminal_disposition_reason"],
                "accepted_red_durable_capture",
            )
            self.assertEqual(shell_payload["recovery_state"], "completed")
            self.assertEqual(
                shell_payload["recovery_contract_state"],
                "manifest_frozen",
            )

    def test_rejected_baseline_real_subprocess_parity_for_1904_drift_without_ref(
        self,
    ) -> None:
        source_stem = "260723_1904_process_superseded_red_baseline_closeout_recovery"
        successor_stem = "260727_1255_process_accepted_red_object_identity_continuity_decomposition"
        recovery_stem = "260727_1450_process_fd_anchored_object_identity_snapshot_primitive"
        source_rel = f"docs/plans/{source_stem}.md"
        draft_rel = f"docs/code_drafts/{source_stem}__code_draft.md"
        review_rel = f"docs/code_reviews/{source_stem}.md"
        successor_rel = f"docs/plans/{successor_stem}.md"
        recovery_rel = f"docs/plans/{recovery_stem}.md"
        recovery_draft_rel = f"docs/code_drafts/{recovery_stem}__code_draft.md"
        verdict_fields = (
            "terminal_disposition",
            "staging_policy",
            "durable_capture_required",
            "terminal_disposition_reason",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            review_sha = self._materialize_rejected_fixture(
                root,
                source_rel=source_rel,
                draft_rel=draft_rel,
                review_rel=review_rel,
                successor_rel=successor_rel,
                recovery_rel=recovery_rel,
                recovery_draft_rel=recovery_draft_rel,
                blocker_ids=("B5",),
            )
            (root / REJECTED_TARGETS[0]).write_text(
                "post-review current snapshot drift\n",
                encoding="utf-8",
            )
            ref = f"refs/planveyor/rejected-baselines/{source_stem}/{review_sha}"
            ref_probe = subprocess.run(
                ["git", "rev-parse", "--verify", "--quiet", ref],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(ref_probe.returncode, 0)

            oracle = self._run_oracle_subprocess(root, source_rel)
            shell = self._run_shell(
                root,
                f"planveyor_plan_bundle --verify-rejected {source_rel}",
            )

            self.assertEqual(oracle.returncode, 0, oracle.stdout + oracle.stderr)
            self.assertEqual(shell.returncode, 0, shell.stdout + shell.stderr)
            oracle_payload = json.loads(oracle.stdout)
            shell_payload = json.loads(shell.stdout)
            self.assertEqual(
                {key: shell_payload[key] for key in verdict_fields},
                {key: oracle_payload[key] for key in verdict_fields},
            )
            self.assertEqual(
                shell_payload["terminal_disposition_reason"],
                "accepted_red_snapshot_mismatch_without_durable_ref",
            )
            self.assertEqual(
                shell_payload["recovery_state"],
                "snapshot_mismatch_without_durable_ref",
            )

    def test_rejected_baseline_malformed_durable_ref_has_exact_oracle_shell_parity(
        self,
    ) -> None:
        verdict_fields = (
            "terminal_disposition",
            "delivery_green",
            "staging_policy",
            "durable_capture_required",
            "terminal_disposition_reason",
        )
        for mutation in (
            "manifest",
            "target_record",
            "cleanup",
            "claimed_cleanup_missing",
        ):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                self._init_repo(root)
                review_sha = self._materialize_rejected_fixture(root)
                ref = (
                    f"refs/planveyor/rejected-baselines/{Path(REJECTED_PLAN_REL).stem}/"
                    f"{review_sha}"
                )
                captured = self._run_shell(
                    root,
                    "planveyor_plan_bundle --capture-rejected "
                    f"--recovery-plan {REJECTED_RECOVERY_REL} {REJECTED_PLAN_REL}",
                )
                self.assertEqual(captured.returncode, 0, captured.stdout + captured.stderr)
                capture_payload = json.loads(captured.stdout)
                capture_commit = self._git(root, "rev-parse", ref).stdout.strip()
                manifest_path = str(capture_payload["recovery_manifest_path"])
                cleanup_path = str(capture_payload["recovery_cleanup_path"])
                manifest = json.loads(
                    self._git(root, "show", f"{capture_commit}:{manifest_path}").stdout
                )
                overlays: dict[str, bytes] = {}
                if mutation in {"manifest", "target_record"}:
                    manifest["captured_parent"] = capture_commit
                    if mutation == "manifest":
                        manifest["schema"] = "planveyor_rejected_baseline.invalid"
                    else:
                        manifest["targets"][0]["sha256"] = "b" * 64
                    overlays[manifest_path] = (
                        json.dumps(
                            manifest,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                        + "\n"
                    ).encode()
                elif mutation == "cleanup":
                    overlays[cleanup_path] = b"{}\n"

                malformed_commit = self._commit_ref_overlay(
                    root,
                    parent=capture_commit,
                    overlays=overlays,
                    message=f"malformed durable fixture: {mutation}",
                )
                self._git(root, "update-ref", ref, malformed_commit, capture_commit)
                head_before = self._git(root, "rev-parse", "HEAD").stdout.strip()
                index_before = self._git(root, "write-tree").stdout.strip()
                target_before = {
                    rel: ((root / rel).read_bytes(), (root / rel).stat().st_mode)
                    for rel in REJECTED_TARGETS
                }

                oracle = self._run_oracle_subprocess(root, REJECTED_PLAN_REL)
                shell = self._run_shell(
                    root,
                    f"planveyor_plan_bundle --verify-rejected {REJECTED_PLAN_REL}",
                )

                self.assertEqual(oracle.returncode, 0, oracle.stdout + oracle.stderr)
                self.assertEqual(shell.returncode, 0, shell.stdout + shell.stderr)
                oracle_payload = json.loads(oracle.stdout)
                shell_payload = json.loads(shell.stdout)
                self.assertEqual(
                    {key: shell_payload[key] for key in verdict_fields},
                    {key: oracle_payload[key] for key in verdict_fields},
                )
                self.assertEqual(
                    shell_payload["terminal_disposition_reason"],
                    "accepted_red_snapshot_mismatch_without_valid_durable_ref",
                )
                self.assertEqual(shell_payload["durable_capture_state"], "invalid")
                self.assertEqual(shell_payload["active_checkout_state"], "snapshot_mismatch")
                self.assertEqual(
                    shell_payload["recovery_state"],
                    "snapshot_mismatch_without_valid_durable_ref",
                )

                for command in (
                    "planveyor_plan_bundle --capture-rejected "
                    f"--recovery-plan {REJECTED_RECOVERY_REL} {REJECTED_PLAN_REL}",
                    f"planveyor_plan_bundle --cleanup-rejected {REJECTED_PLAN_REL}",
                ):
                    blocked = self._run_shell(root, command)
                    self.assertEqual(blocked.returncode, 2, blocked.stdout + blocked.stderr)
                    self.assertEqual(
                        json.loads(blocked.stderr)["reason_code"],
                        "recovery_ref_invalid",
                    )
                    self.assertEqual(
                        self._git(root, "rev-parse", ref).stdout.strip(),
                        malformed_commit,
                    )
                    self.assertEqual(
                        self._git(root, "rev-parse", "HEAD").stdout.strip(),
                        head_before,
                    )
                    self.assertEqual(
                        self._git(root, "write-tree").stdout.strip(),
                        index_before,
                    )
                    self.assertEqual(
                        {
                            rel: ((root / rel).read_bytes(), (root / rel).stat().st_mode)
                            for rel in REJECTED_TARGETS
                        },
                        target_before,
                    )

    def test_rejected_baseline_snapshot_replacement_fails_without_retry(self) -> None:
        cases = (
            ("after_leaf_read", REJECTED_TARGETS, REJECTED_TARGETS[0]),
            (
                "after_ancestor_chain_opened",
                ["docs/recovery-owned/nested-overlap.md", REJECTED_TARGETS[1]],
                "docs/recovery-owned/nested-overlap.md",
            ),
        )
        for stage, target_paths, overlap_rel in cases:
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                self._init_repo(root)
                self._materialize_rejected_fixture(root, target_paths=target_paths)
                captured = self._run_shell(
                    root,
                    "planveyor_plan_bundle --capture-rejected "
                    f"--recovery-plan {REJECTED_RECOVERY_REL} {REJECTED_PLAN_REL}",
                )
                self.assertEqual(captured.returncode, 0, captured.stdout + captured.stderr)
                cleaned = self._run_shell(
                    root,
                    f"planveyor_plan_bundle --cleanup-rejected {REJECTED_PLAN_REL}",
                )
                self.assertEqual(cleaned.returncode, 0, cleaned.stdout + cleaned.stderr)
                (root / overlap_rel).write_text("recovery delta\n", encoding="utf-8")
                self._install_counting_identity_wrapper(root, target_paths=target_paths)
                count_path = root / ".snapshot-count"

                verified = self._run_shell(
                    root,
                    f"planveyor_plan_bundle --verify-rejected {REJECTED_PLAN_REL}",
                    env_extra={
                        "PLANVEYOR_TEST_SNAPSHOT_COUNT_PATH": str(count_path),
                        "PLANVEYOR_TEST_IDENTITY_SWAP_REL": overlap_rel,
                        "PLANVEYOR_TEST_IDENTITY_SWAP_STAGE": stage,
                    },
                )

                self.assertEqual(verified.returncode, 2, verified.stdout + verified.stderr)
                self.assertEqual(
                    json.loads(verified.stderr)["reason_code"],
                    "active_checkout_drift",
                )
                counts = count_path.read_text(encoding="utf-8").splitlines()
                self.assertEqual(counts, [overlap_rel])

    def test_rejected_baseline_generic_applicability_and_lineage_drift_fail_before_mutation(
        self,
    ) -> None:
        cases = (
            ("missing", {"inherited_ids": ()}),
            ("extra", {"inherited_ids": ("B5", "B9")}),
            ("duplicate", {"inherited_ids": ("B5", "B5")}),
            ("source_ref", {"source_ref_id": "B9"}),
            ("unsupported_state", {"blocker_state": "historical-fixed"}),
            (
                "duplicate_review_id",
                {"blocker_ids": ("B5", "B5"), "inherited_ids": ("B5",)},
            ),
        )
        for case, options in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                self._init_repo(root)
                fixture_options = dict(options)
                self._materialize_rejected_fixture(
                    root,
                    blocker_ids=fixture_options.pop("blocker_ids", ("B5",)),
                    **fixture_options,
                )
                index_before = self._git(root, "write-tree").stdout.strip()
                head_before = self._git(root, "rev-parse", "HEAD").stdout.strip()

                captured = self._run_shell(
                    root,
                    "planveyor_plan_bundle --capture-rejected "
                    f"--recovery-plan {REJECTED_RECOVERY_REL} {REJECTED_PLAN_REL}",
                )
                guarded = self._run_shell(
                    root,
                    f"planveyor_plan_bundle --stage {REJECTED_PLAN_REL}",
                )

                self.assertEqual(captured.returncode, 2, captured.stdout + captured.stderr)
                self.assertEqual(json.loads(captured.stderr)["reason_code"], "not_accepted_red")
                self.assertEqual(guarded.returncode, 2, guarded.stdout + guarded.stderr)
                self.assertEqual(
                    json.loads(guarded.stderr)["reason_code"],
                    "staging_forbidden_invalid_carrier",
                )
                self.assertEqual(self._git(root, "write-tree").stdout.strip(), index_before)
                self.assertEqual(self._git(root, "rev-parse", "HEAD").stdout.strip(), head_before)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._materialize_rejected_fixture(root, blocker_ids=("B5",))
            source = root / REJECTED_PLAN_REL
            source.write_text(
                source.read_text(encoding="utf-8").replace(
                    '"state": "architect_accepted"',
                    '"state": "n/a"',
                ),
                encoding="utf-8",
            )

            guarded = self._run_shell(
                root,
                f"planveyor_plan_bundle --stage {REJECTED_PLAN_REL}",
            )

            self.assertEqual(guarded.returncode, 1, guarded.stdout + guarded.stderr)
            self.assertIn("CURRENT-REVIEW-RED", guarded.stdout)
            self.assertNotIn("accepted_red", guarded.stdout + guarded.stderr)

    def test_rejected_baseline_recovery_identity_and_frozen_targets_fail_closed(self) -> None:
        capture_command = (
            "planveyor_plan_bundle --capture-rejected "
            f"--recovery-plan {REJECTED_RECOVERY_REL} {REJECTED_PLAN_REL}"
        )
        for mutation in ("self", "foreign", "missing_draft", "wrong_draft_plan"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                self._init_repo(root)
                review_sha = self._materialize_rejected_fixture(root)
                recovery_arg = REJECTED_RECOVERY_REL
                if mutation == "self":
                    recovery_arg = REJECTED_PLAN_REL
                elif mutation == "foreign":
                    recovery = root / REJECTED_RECOVERY_REL
                    recovery.write_text(
                        recovery.read_text(encoding="utf-8").replace(
                            REJECTED_PLAN_REL,
                            "docs/plans/foreign_source.md",
                            1,
                        ),
                        encoding="utf-8",
                    )
                elif mutation == "missing_draft":
                    (root / REJECTED_RECOVERY_DRAFT_REL).unlink()
                else:
                    draft = root / REJECTED_RECOVERY_DRAFT_REL
                    draft.write_text(
                        draft.read_text(encoding="utf-8").replace(
                            f'"plan": "{REJECTED_RECOVERY_REL}"',
                            '"plan": "docs/plans/wrong_recovery.md"',
                        ),
                        encoding="utf-8",
                    )
                ref = (
                    f"refs/planveyor/rejected-baselines/{Path(REJECTED_PLAN_REL).stem}/{review_sha}"
                )
                index_before = self._git(root, "write-tree").stdout.strip()

                capture = self._run_shell(
                    root,
                    "planveyor_plan_bundle --capture-rejected "
                    f"--recovery-plan {recovery_arg} {REJECTED_PLAN_REL}",
                )

                self.assertEqual(capture.returncode, 2, capture.stdout + capture.stderr)
                self.assertEqual(json.loads(capture.stderr)["reason_code"], "recovery_plan_invalid")
                self.assertEqual(
                    self._git(
                        root,
                        "for-each-ref",
                        "--format=%(refname)",
                        ref,
                    ).stdout.strip(),
                    "",
                )
                self.assertEqual(self._git(root, "write-tree").stdout.strip(), index_before)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._materialize_rejected_fixture(root)
            captured = self._run_shell(root, capture_command)
            self.assertEqual(captured.returncode, 0, captured.stdout + captured.stderr)
            draft = root / REJECTED_RECOVERY_DRAFT_REL
            draft_payload = json.loads(
                re.search(
                    r"```json\s*([\s\S]*?)```",
                    draft.read_text(encoding="utf-8"),
                ).group(1)
            )
            draft_payload["code_draft_meta"]["targets"].append(
                {"path": REJECTED_TARGETS[1], "kind": "doc"}
            )
            draft.write_text(
                f"# Recovery draft\n\n```json\n{json.dumps(draft_payload, indent=2)}\n```\n",
                encoding="utf-8",
            )

            verify = self._run_shell(
                root,
                f"planveyor_plan_bundle --verify-rejected {REJECTED_PLAN_REL}",
            )

            self.assertEqual(verify.returncode, 0, verify.stdout + verify.stderr)
            invalid_payload = json.loads(verify.stdout)
            self.assertEqual(invalid_payload["durable_capture_state"], "invalid")
            self.assertEqual(
                invalid_payload["terminal_disposition_reason"],
                "accepted_red_snapshot_mismatch_without_valid_durable_ref",
            )

    def test_rejected_baseline_stage_commit_guards_block_applicable_invalid_states(self) -> None:
        for mutation in (
            "green_review",
            "missing_review",
            "routing_drift",
            "corrupt_ref",
            "incomplete_receipt",
        ):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                self._init_repo(root)
                review_sha = self._materialize_rejected_fixture(root)
                ref = (
                    f"refs/planveyor/rejected-baselines/{Path(REJECTED_PLAN_REL).stem}/{review_sha}"
                )
                if mutation == "green_review":
                    review = root / REJECTED_REVIEW_REL
                    review.write_text(
                        review.read_text(encoding="utf-8").replace(
                            "❌ S1 blocker(ы)",
                            "✅ OK",
                        ),
                        encoding="utf-8",
                    )
                elif mutation == "missing_review":
                    (root / REJECTED_REVIEW_REL).unlink()
                elif mutation == "routing_drift":
                    successor = root / REJECTED_SUCCESSOR_REL
                    successor.write_text(
                        successor.read_text(encoding="utf-8").replace(
                            f'"parent": "{REJECTED_PLAN_REL}"',
                            '"parent": "docs/plans/foreign.md"',
                        ),
                        encoding="utf-8",
                    )
                elif mutation == "corrupt_ref":
                    head = self._git(root, "rev-parse", "HEAD").stdout.strip()
                    self._git(root, "update-ref", ref, head)
                else:
                    captured = self._run_shell(
                        root,
                        "planveyor_plan_bundle --capture-rejected "
                        f"--recovery-plan {REJECTED_RECOVERY_REL} {REJECTED_PLAN_REL}",
                    )
                    self.assertEqual(captured.returncode, 0, captured.stdout + captured.stderr)

                index_before = self._git(root, "write-tree").stdout.strip()
                head_before = self._git(root, "rev-parse", "HEAD").stdout.strip()
                for mode in ("--stage", "--commit-ready", "--commit-exact"):
                    with self.subTest(mode=mode):
                        guarded = self._run_shell(
                            root,
                            f"planveyor_plan_bundle {mode} {REJECTED_PLAN_REL}",
                        )
                        self.assertEqual(guarded.returncode, 2, guarded.stdout + guarded.stderr)
                        reason = json.loads(guarded.stderr)["reason_code"]
                        expected = (
                            "staging_forbidden"
                            if mutation == "incomplete_receipt"
                            else "staging_forbidden_invalid_carrier"
                        )
                        self.assertEqual(reason, expected)
                        self.assertEqual(self._git(root, "write-tree").stdout.strip(), index_before)
                        self.assertEqual(self._git(root, "rev-parse", "HEAD").stdout.strip(), head_before)
                if mutation in {"green_review", "missing_review", "routing_drift"}:
                    closeout = self._run_shell(
                        root,
                        f"planveyor_plan_bundle --closeout-json {REJECTED_PLAN_REL}",
                    )
                    self.assertEqual(
                        closeout.returncode,
                        2,
                        closeout.stdout + closeout.stderr,
                    )
                    self.assertEqual(
                        json.loads(closeout.stderr)["reason_code"],
                        "accepted_red_closeout_invalid_carrier",
                    )

    def test_rejected_baseline_oracle_and_public_closeout_agree_on_routing_drift(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._materialize_rejected_fixture(root)
            successor = root / REJECTED_SUCCESSOR_REL
            successor.write_text(
                successor.read_text(encoding="utf-8").replace(
                    f'"parent": "{REJECTED_PLAN_REL}"',
                    '"parent": "docs/plans/foreign.md"',
                ),
                encoding="utf-8",
            )
            carrier_paths = (
                REJECTED_PLAN_REL,
                REJECTED_DRAFT_REL,
                REJECTED_REVIEW_REL,
                REJECTED_SUCCESSOR_REL,
            )
            carrier_bytes = {
                rel: (root / rel).read_bytes()
                for rel in carrier_paths
            }

            oracle = self._run_oracle_subprocess(root, REJECTED_PLAN_REL)

            self.assertEqual(oracle.returncode, 0, oracle.stdout + oracle.stderr)
            oracle_payload = json.loads(oracle.stdout)
            self.assertEqual(
                oracle_payload["terminal_disposition"],
                "accepted_red_supersession",
            )
            self.assertFalse(oracle_payload["delivery_green"])
            self.assertEqual(oracle_payload["staging_policy"], "forbidden")
            self.assertTrue(oracle_payload["durable_capture_required"])
            self.assertEqual(
                oracle_payload["terminal_disposition_reason"],
                "accepted_red_carrier_invalid",
            )
            self.assertEqual(
                {rel: (root / rel).read_bytes() for rel in carrier_paths},
                carrier_bytes,
            )

            closeout = self._run_shell(
                root,
                f"planveyor_plan_bundle --closeout-json {REJECTED_PLAN_REL}",
            )

            self.assertEqual(closeout.returncode, 2, closeout.stdout + closeout.stderr)
            self.assertEqual(
                json.loads(closeout.stderr)["reason_code"],
                "accepted_red_closeout_invalid_carrier",
            )
            self.assertEqual(
                {rel: (root / rel).read_bytes() for rel in carrier_paths},
                carrier_bytes,
            )

    def test_rejected_baseline_closeout_blocks_post_capture_routing_drift(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._materialize_rejected_fixture(root)
            captured = self._run_shell(
                root,
                "planveyor_plan_bundle --capture-rejected "
                f"--recovery-plan {REJECTED_RECOVERY_REL} {REJECTED_PLAN_REL}",
            )
            self.assertEqual(captured.returncode, 0, captured.stdout + captured.stderr)
            captured_payload = json.loads(captured.stdout)
            ref = str(captured_payload["recovery_ref"])
            ref_before = self._git(root, "rev-parse", ref).stdout.strip()
            index_before = self._git(root, "write-tree").stdout.strip()
            head_before = self._git(root, "rev-parse", "HEAD").stdout.strip()

            successor = root / REJECTED_SUCCESSOR_REL
            successor.write_text(
                successor.read_text(encoding="utf-8").replace(
                    f'"parent": "{REJECTED_PLAN_REL}"',
                    '"parent": "docs/plans/foreign.md"',
                ),
                encoding="utf-8",
            )
            closeout = self._run_shell(
                root,
                f"planveyor_plan_bundle --closeout-json {REJECTED_PLAN_REL}",
            )

            self.assertEqual(
                closeout.returncode,
                2,
                closeout.stdout + closeout.stderr,
            )
            self.assertEqual(closeout.stdout, "")
            self.assertEqual(
                json.loads(closeout.stderr)["reason_code"],
                "accepted_red_closeout_invalid_carrier",
            )
            self.assertEqual(self._git(root, "rev-parse", ref).stdout.strip(), ref_before)
            self.assertEqual(self._git(root, "write-tree").stdout.strip(), index_before)
            self.assertEqual(self._git(root, "rev-parse", "HEAD").stdout.strip(), head_before)

    def test_rejected_baseline_oracle_and_public_agree_after_admission_drift(
        self,
    ) -> None:
        drift_cases = (
            ("status", "**Status:** Superseded", "**Status:** In progress"),
            (
                "scope",
                '"state": "architect_accepted"',
                '"state": "n/a"',
            ),
        )
        carrier_paths = (
            REJECTED_PLAN_REL,
            REJECTED_DRAFT_REL,
            REJECTED_REVIEW_REL,
            REJECTED_SUCCESSOR_REL,
        )
        for drift, old, new in drift_cases:
            with self.subTest(drift=drift), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                self._init_repo(root)
                self._materialize_rejected_fixture(root)
                captured = self._run_shell(
                    root,
                    "planveyor_plan_bundle --capture-rejected "
                    f"--recovery-plan {REJECTED_RECOVERY_REL} {REJECTED_PLAN_REL}",
                )
                self.assertEqual(
                    captured.returncode,
                    0,
                    captured.stdout + captured.stderr,
                )
                ref = str(json.loads(captured.stdout)["recovery_ref"])
                ref_before = self._git(root, "rev-parse", ref).stdout.strip()
                index_before = self._git(root, "write-tree").stdout.strip()
                head_before = self._git(root, "rev-parse", "HEAD").stdout.strip()

                source = root / REJECTED_PLAN_REL
                source_text = source.read_text(encoding="utf-8")
                self.assertIn(old, source_text)
                source.write_text(
                    source_text.replace(old, new, 1),
                    encoding="utf-8",
                )
                carrier_bytes = {
                    rel: (root / rel).read_bytes()
                    for rel in carrier_paths
                }

                oracle = self._run_oracle_subprocess(root, REJECTED_PLAN_REL)
                self.assertEqual(
                    oracle.returncode,
                    0,
                    oracle.stdout + oracle.stderr,
                )
                oracle_payload = json.loads(oracle.stdout)
                self.assertEqual(
                    oracle_payload["terminal_disposition"],
                    "accepted_red_supersession",
                )
                self.assertFalse(oracle_payload["delivery_green"])
                self.assertEqual(oracle_payload["staging_policy"], "forbidden")
                self.assertTrue(oracle_payload["durable_capture_required"])
                self.assertEqual(
                    oracle_payload["terminal_disposition_reason"],
                    "accepted_red_carrier_invalid",
                )

                closeout = self._run_shell(
                    root,
                    f"planveyor_plan_bundle --closeout-json {REJECTED_PLAN_REL}",
                )
                self.assertEqual(
                    closeout.returncode,
                    2,
                    closeout.stdout + closeout.stderr,
                )
                self.assertEqual(closeout.stdout, "")
                self.assertEqual(
                    json.loads(closeout.stderr)["reason_code"],
                    "accepted_red_closeout_invalid_carrier",
                )
                self.assertEqual(
                    {rel: (root / rel).read_bytes() for rel in carrier_paths},
                    carrier_bytes,
                )
                self.assertEqual(
                    self._git(root, "rev-parse", ref).stdout.strip(),
                    ref_before,
                )
                self.assertEqual(
                    self._git(root, "write-tree").stdout.strip(),
                    index_before,
                )
                self.assertEqual(
                    self._git(root, "rev-parse", "HEAD").stdout.strip(),
                    head_before,
                )

                with tempfile.TemporaryDirectory() as no_ref_tmpdir:
                    no_ref_root = Path(no_ref_tmpdir).resolve()
                    self._init_repo(no_ref_root)
                    self._materialize_rejected_fixture(no_ref_root)
                    for rel, data in carrier_bytes.items():
                        (no_ref_root / rel).write_bytes(data)

                    no_ref_oracle = self._run_oracle_subprocess(
                        no_ref_root,
                        REJECTED_PLAN_REL,
                    )

                    self.assertEqual(
                        no_ref_oracle.returncode,
                        0,
                        no_ref_oracle.stdout + no_ref_oracle.stderr,
                    )
                    no_ref_payload = json.loads(no_ref_oracle.stdout)
                    self.assertEqual(
                        no_ref_payload["terminal_disposition"],
                        "ordinary",
                    )
                    self.assertFalse(no_ref_payload["delivery_green"])
                    self.assertEqual(
                        no_ref_payload["staging_policy"],
                        "allowed",
                    )
                    self.assertFalse(no_ref_payload["durable_capture_required"])
                    self.assertEqual(
                        no_ref_payload["terminal_disposition_reason"],
                        "accepted-red conjunction is not applicable",
                    )

    def test_ordinary_superseded_review_route_near_misses_use_ordinary_bundle_path(
        self,
    ) -> None:
        for review_route in ("absent", "n_a"):
            with self.subTest(review_route=review_route), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                self._init_repo(root)
                self._materialize_bundle(root)
                plan = root / PLAN_REL
                plan_text = plan.read_text(encoding="utf-8").replace(
                    "**Status:** Ready for Review",
                    "**Status:** Superseded",
                )
                replacement = "" if review_route == "absent" else "- N/A\n"
                plan.write_text(
                    plan_text.replace(
                        f"- Code review (primary): `{REVIEW_REL}`\n",
                        replacement,
                    ),
                    encoding="utf-8",
                )
                self._commit_all(root, f"ordinary superseded {review_route}")
                index_before = self._git(root, "write-tree").stdout.strip()

                closeout = self._run_shell(
                    root,
                    f"planveyor_plan_bundle --closeout-json {PLAN_REL}",
                )
                stage = self._run_shell(
                    root,
                    f"planveyor_plan_bundle --stage {PLAN_REL}",
                )

                self.assertEqual(closeout.returncode, 0, closeout.stdout + closeout.stderr)
                self.assertEqual(closeout.stderr, "")
                closeout_payload = json.loads(closeout.stdout)
                self.assertEqual(closeout_payload["plan"], PLAN_REL)
                self.assertFalse(closeout_payload["bundle_ok"])
                self.assertIn(
                    "Missing explicit live review artifact path in ## Review artifacts",
                    closeout_payload["errors"],
                )
                self.assertEqual(stage.returncode, 1, stage.stdout + stage.stderr)
                self.assertIn(
                    "Missing explicit live review artifact path in ## Review artifacts",
                    stage.stderr,
                )
                self.assertNotIn("accepted_red", closeout.stdout + closeout.stderr + stage.stderr)
                self.assertEqual(self._git(root, "write-tree").stdout.strip(), index_before)

    def test_rejected_baseline_head_absent_cleanup_uses_lexical_path_state(self) -> None:
        absent_rel = REJECTED_TARGETS[1]
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._materialize_rejected_fixture(root, head_absent_targets={absent_rel})
            captured = self._run_shell(
                root,
                "planveyor_plan_bundle --capture-rejected "
                f"--recovery-plan {REJECTED_RECOVERY_REL} {REJECTED_PLAN_REL}",
            )
            self.assertEqual(captured.returncode, 0, captured.stdout + captured.stderr)

            cleaned = self._run_shell(
                root,
                f"planveyor_plan_bundle --cleanup-rejected {REJECTED_PLAN_REL}",
            )

            self.assertEqual(cleaned.returncode, 0, cleaned.stdout + cleaned.stderr)
            self.assertFalse(os.path.lexists(root / absent_rel))

        for entry_kind in ("broken_symlink", "live_symlink", "directory"):
            with self.subTest(entry_kind=entry_kind), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                self._init_repo(root)
                self._materialize_rejected_fixture(root, head_absent_targets={absent_rel})
                captured = self._run_shell(
                    root,
                    "planveyor_plan_bundle --capture-rejected "
                    f"--recovery-plan {REJECTED_RECOVERY_REL} {REJECTED_PLAN_REL}",
                )
                self.assertEqual(captured.returncode, 0, captured.stdout + captured.stderr)
                path = root / absent_rel
                path.unlink()
                if entry_kind == "broken_symlink":
                    path.symlink_to("missing-target")
                elif entry_kind == "live_symlink":
                    live_target = root / "live-target"
                    live_target.write_text("live\n", encoding="utf-8")
                    path.symlink_to(live_target)
                else:
                    path.mkdir()
                index_before = self._git(root, "write-tree").stdout.strip()

                cleanup = self._run_shell(
                    root,
                    f"planveyor_plan_bundle --cleanup-rejected {REJECTED_PLAN_REL}",
                )

                self.assertEqual(cleanup.returncode, 2, cleanup.stdout + cleanup.stderr)
                self.assertEqual(json.loads(cleanup.stderr)["reason_code"], "rejected_target_drift")
                self.assertTrue(os.path.lexists(path))
                self.assertEqual(self._git(root, "write-tree").stdout.strip(), index_before)

    def test_rejected_baseline_post_receipt_overlap_rejects_non_regular_objects(self) -> None:
        overlap_rel = REJECTED_TARGETS[0]
        for entry_kind in ("broken_symlink", "live_symlink", "directory", "fifo"):
            with self.subTest(entry_kind=entry_kind), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                self._init_repo(root)
                self._materialize_rejected_fixture(root)
                captured = self._run_shell(
                    root,
                    "planveyor_plan_bundle --capture-rejected "
                    f"--recovery-plan {REJECTED_RECOVERY_REL} {REJECTED_PLAN_REL}",
                )
                self.assertEqual(captured.returncode, 0, captured.stdout + captured.stderr)
                cleaned = self._run_shell(
                    root,
                    f"planveyor_plan_bundle --cleanup-rejected {REJECTED_PLAN_REL}",
                )
                self.assertEqual(cleaned.returncode, 0, cleaned.stdout + cleaned.stderr)

                path = root / overlap_rel
                path.unlink()
                if entry_kind == "broken_symlink":
                    path.symlink_to("missing-target")
                elif entry_kind == "live_symlink":
                    live_target = root / "live-target"
                    live_target.write_text("live\n", encoding="utf-8")
                    path.symlink_to(live_target)
                elif entry_kind == "directory":
                    path.mkdir()
                else:
                    os.mkfifo(path)

                verified = self._run_shell(
                    root,
                    f"planveyor_plan_bundle --verify-rejected {REJECTED_PLAN_REL}",
                )
                self.assertEqual(verified.returncode, 2, verified.stdout + verified.stderr)
                self.assertEqual(json.loads(verified.stderr)["reason_code"], "active_checkout_drift")
                self.assertTrue(os.path.lexists(path))

                closeout = self._run_shell(
                    root,
                    f"planveyor_docs_closeout {REJECTED_PLAN_REL} --json",
                )
                closeout_payload = json.loads(closeout.stdout)
                self.assertEqual(closeout_payload["state"], "blocked")
                self.assertEqual(
                    closeout_payload["reason_code"],
                    "accepted_red_recovery_incomplete",
                )
                self.assertTrue(os.path.lexists(path))

    def test_rejected_baseline_post_receipt_overlap_rejects_symlinked_ancestors(self) -> None:
        overlap_rel = "docs/recovery-owned/nested-overlap.md"
        target_paths = [overlap_rel, REJECTED_TARGETS[1]]
        for alias_kind in ("in_repo", "out_of_repo"):
            with (
                self.subTest(alias_kind=alias_kind),
                tempfile.TemporaryDirectory() as tmpdir,
                tempfile.TemporaryDirectory() as outside_tmpdir,
            ):
                root = Path(tmpdir).resolve()
                self._init_repo(root)
                self._materialize_rejected_fixture(root, target_paths=target_paths)
                captured = self._run_shell(
                    root,
                    "planveyor_plan_bundle --capture-rejected "
                    f"--recovery-plan {REJECTED_RECOVERY_REL} {REJECTED_PLAN_REL}",
                )
                self.assertEqual(captured.returncode, 0, captured.stdout + captured.stderr)
                cleaned = self._run_shell(
                    root,
                    f"planveyor_plan_bundle --cleanup-rejected {REJECTED_PLAN_REL}",
                )
                self.assertEqual(cleaned.returncode, 0, cleaned.stdout + cleaned.stderr)

                path = root / overlap_rel
                ancestor = path.parent
                path.unlink()
                ancestor.rmdir()
                alias_root = (
                    root / "foreign-recovery-owned"
                    if alias_kind == "in_repo"
                    else Path(outside_tmpdir)
                )
                alias_root.mkdir(parents=True, exist_ok=True)
                (alias_root / path.name).write_text("aliased recovery delta\n", encoding="utf-8")
                ancestor.symlink_to(alias_root, target_is_directory=True)

                verified = self._run_shell(
                    root,
                    f"planveyor_plan_bundle --verify-rejected {REJECTED_PLAN_REL}",
                )
                self.assertEqual(verified.returncode, 2, verified.stdout + verified.stderr)
                self.assertEqual(
                    json.loads(verified.stderr)["reason_code"],
                    "routing_contract_invalid",
                )

                closeout = self._run_shell(
                    root,
                    f"planveyor_docs_closeout {REJECTED_PLAN_REL} --json",
                )
                closeout_payload = json.loads(closeout.stdout)
                self.assertEqual(closeout_payload["state"], "blocked")
                self.assertEqual(
                    closeout_payload["reason_code"],
                    "accepted_red_recovery_incomplete",
                )

    def test_docs_closeout_uses_same_loaded_tooling_root_as_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._materialize_rejected_fixture(root)
            stale_root = root / "stale-tooling"
            stale_helper = stale_root / "scripts" / "docs_closeout.py"
            stale_helper.parent.mkdir(parents=True)
            stale_helper.write_text(
                "#!/usr/bin/env python3\nprint('STALE_HELPER_SELECTED')\nraise SystemExit(42)\n",
                encoding="utf-8",
            )
            (stale_root / "scripts" / "planveyor.zsh").write_text(
                "print STALE_PLANVEYOR_SELECTED\nreturn 42\n",
                encoding="utf-8",
            )
            (stale_root / "scripts" / "plan_lint.py").write_text(
                "raise SystemExit('STALE_PLAN_LINT_SELECTED')\n",
                encoding="utf-8",
            )
            (stale_root / "scripts" / "plan_status_oracle.py").write_text(
                "raise SystemExit('STALE_ORACLE_SELECTED')\n",
                encoding="utf-8",
            )
            (stale_root / "scripts" / "review_target_snapshot.py").write_text(
                "raise SystemExit('STALE_SNAPSHOT_SELECTED')\n",
                encoding="utf-8",
            )
            command = (
                f"source {shlex.quote(str(PLANVEYOR_SCRIPT))} && "
                "planveyor_plan_bundle --capture-rejected "
                f"--recovery-plan {REJECTED_RECOVERY_REL} {REJECTED_PLAN_REL} >/dev/null && "
                f"planveyor_plan_bundle --cleanup-rejected {REJECTED_PLAN_REL} >/dev/null && "
                f"planveyor_docs_closeout {REJECTED_PLAN_REL} --json"
            )

            closeout = run_zsh_fixture(
                command,
                cwd=root,
                path=os.environ.get("PATH", os.defpath),
                pybin=str(Path(sys.executable).resolve()),
                fixture_env={"PLANVEYOR_ROOT": str(stale_root)},
                home=root / ".home",
                check=False,
            )

            self.assertEqual(closeout.returncode, 0, closeout.stdout + closeout.stderr)
            self.assertNotIn("STALE_HELPER_SELECTED", closeout.stdout + closeout.stderr)
            self.assertEqual(json.loads(closeout.stdout)["state"], "completed")

    def test_closeout_rejects_identical_shell_divergent_helper_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._materialize_rejected_fixture(root)
            configured_root = root / "configured-tooling"
            shutil.copytree(root / "scripts", configured_root / "scripts")
            (configured_root / "scripts" / "docs_closeout.py").write_text(
                "#!/usr/bin/env python3\n"
                "print('{\"state\":\"completed\",\"reason_code\":\"FORGED_STALE_HELPER\"}')\n",
                encoding="utf-8",
            )
            (root / "scripts" / "docs_closeout.py").unlink()
            command = (
                "source scripts/planveyor.zsh && "
                "planveyor_plan_bundle --capture-rejected "
                f"--recovery-plan {REJECTED_RECOVERY_REL} {REJECTED_PLAN_REL} >/dev/null && "
                f"planveyor_plan_bundle --cleanup-rejected {REJECTED_PLAN_REL} >/dev/null && "
                f"planveyor_docs_closeout {REJECTED_PLAN_REL} --json"
            )

            closeout = run_zsh_fixture(
                command,
                cwd=root,
                path=os.environ.get("PATH", os.defpath),
                pybin=str(Path(sys.executable).resolve()),
                fixture_env={"PLANVEYOR_ROOT": str(configured_root)},
                home=root / ".home",
                check=False,
            )

            self.assertEqual(closeout.returncode, 1, closeout.stdout + closeout.stderr)
            self.assertIn(
                "Cannot resolve one complete tooling root for plan bundle",
                closeout.stderr,
            )
            self.assertNotIn("FORGED_STALE_HELPER", closeout.stdout + closeout.stderr)

    def test_rejected_baseline_cleanup_blocks_on_head_or_index_drift_without_worktree_mutation(self) -> None:
        for drift_kind in ("head", "index", "worktree"):
            with self.subTest(drift_kind=drift_kind), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                self._init_repo(root)
                self._materialize_rejected_fixture(root)
                captured = self._run_shell(
                    root,
                    "planveyor_plan_bundle --capture-rejected "
                    f"--recovery-plan {REJECTED_RECOVERY_REL} {REJECTED_PLAN_REL}",
                )
                self.assertEqual(captured.returncode, 0, captured.stdout + captured.stderr)
                rejected_before = {rel: (root / rel).read_bytes() for rel in REJECTED_TARGETS}
                if drift_kind == "head":
                    foreign = root / "foreign.txt"
                    foreign.write_text("new head\n", encoding="utf-8")
                    self._git(root, "add", "foreign.txt")
                    self._git(root, "commit", "-m", "move head")
                else:
                    if drift_kind == "index":
                        self._git(root, "add", REJECTED_TARGETS[0])
                    else:
                        (root / REJECTED_TARGETS[0]).write_text("third-state bytes\n", encoding="utf-8")
                        rejected_before[REJECTED_TARGETS[0]] = b"third-state bytes\n"

                cleanup = self._run_shell(root, f"planveyor_plan_bundle --cleanup-rejected {REJECTED_PLAN_REL}")

                self.assertEqual(cleanup.returncode, 2)
                reason = json.loads(cleanup.stderr)["reason_code"]
                expected_reason = {
                    "head": "head_drift",
                    "index": "rejected_target_staged",
                    "worktree": "rejected_target_drift",
                }[drift_kind]
                self.assertEqual(reason, expected_reason)
                self.assertEqual({rel: (root / rel).read_bytes() for rel in REJECTED_TARGETS}, rejected_before)

    def test_rejected_baseline_capture_rejects_preoccupied_invalid_ref_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            review_sha = self._materialize_rejected_fixture(root)
            ref = f"refs/planveyor/rejected-baselines/{Path(REJECTED_PLAN_REL).stem}/{review_sha}"
            head = self._git(root, "rev-parse", "HEAD").stdout.strip()
            self._git(root, "update-ref", ref, head)
            index_before = self._git(root, "write-tree").stdout.strip()
            targets_before = {rel: (root / rel).read_bytes() for rel in REJECTED_TARGETS}

            capture = self._run_shell(
                root,
                "planveyor_plan_bundle --capture-rejected "
                f"--recovery-plan {REJECTED_RECOVERY_REL} {REJECTED_PLAN_REL}",
            )

            self.assertEqual(capture.returncode, 2)
            self.assertEqual(json.loads(capture.stderr)["reason_code"], "recovery_ref_invalid")
            self.assertEqual(self._git(root, "rev-parse", ref).stdout.strip(), head)
            self.assertEqual(self._git(root, "write-tree").stdout.strip(), index_before)
            self.assertEqual({rel: (root / rel).read_bytes() for rel in REJECTED_TARGETS}, targets_before)

    def test_receipt_bound_stage_preflight_and_commit_exact_use_tree_parent_ref_cas(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            payload, owned_rel = self._capture_docs_payload(root)
            payload_path = self._write_json(root, "docs-closeout.json", payload)
            hook_sentinel = root / "hook-ran"
            hook = root / ".git/hooks/pre-commit"
            hook.write_text(f"#!/bin/sh\ntouch {shlex.quote(str(hook_sentinel))}\nexit 1\n", encoding="utf-8")
            hook.chmod(0o755)
            ref_hook_sentinel = root / "reference-hook-ran"
            hooks = root / "configured-hooks"
            hooks.mkdir()
            self._git(root, "config", "core.hooksPath", str(hooks))
            hook.rename(hooks / "pre-commit")
            ref_hook = hooks / "reference-transaction"
            ref_hook.write_text(
                f'#!/bin/sh\nprintf "%s\\n" "$1" >> {shlex.quote(str(ref_hook_sentinel))}\ncat >/dev/null\nexit 0\n',
                encoding="utf-8",
            )
            ref_hook.chmod(0o755)
            index_before = self._git(root, "write-tree").stdout.strip()

            stage = self._run_shell(
                root,
                f"planveyor_plan_bundle --stage --docs-closeout-json {shlex.quote(str(payload_path))} {CAPTURE_PLAN_REL}",
            )
            self.assertEqual(stage.returncode, 0, stage.stdout + stage.stderr)
            stage_receipt = json.loads(stage.stdout)
            self.assertEqual(stage_receipt["schema_version"], "followups_staging_verification.v1")
            self.assertEqual(stage_receipt["state"], "prepared")
            self.assertEqual(stage_receipt["staging_verifications"][0]["blob_mode"], "100644")
            self.assertEqual(self._git(root, "write-tree").stdout.strip(), index_before)

            preflight = self._run_shell(
                root,
                f"planveyor_plan_closeout_preflight --docs-closeout-json {shlex.quote(str(payload_path))} --json {CAPTURE_PLAN_REL}",
            )
            self.assertEqual(preflight.returncode, 0, preflight.stdout + preflight.stderr)
            preflight_payload = json.loads(preflight.stdout)
            self.assertEqual(preflight_payload["schema_version"], "followups_commit_preflight.v1")
            self.assertEqual(
                set(preflight_payload),
                {
                    "schema_version",
                    "state",
                    "reason_code",
                    "plan_ref",
                    "capture_cycle_id",
                    "receipt_revision",
                    "receipt_content_sha256",
                    "bundle_identity",
                    "staged_paths",
                    "tree_construction",
                    "expected_tree_oid",
                    "expected_ref",
                    "expected_parent_oid",
                    "docs_closeout_payload",
                },
            )
            self.assertEqual(preflight_payload["staged_paths"][0]["path"], owned_rel)
            expected_parent = preflight_payload["expected_parent_oid"]
            preflight_path = self._write_json(root, "preflight.json", preflight_payload)
            exact = self._run_shell(
                root,
                "planveyor_plan_bundle --commit-exact "
                f"--preflight-json {shlex.quote(str(preflight_path))} "
                f"--message-auto {CAPTURE_PLAN_REL}",
            )

            self.assertEqual(exact.returncode, 0, exact.stdout + exact.stderr)
            receipt = json.loads(exact.stdout)
            self.assertEqual(receipt["schema_version"], "followups_commit_exact_result.v1")
            self.assertEqual(
                set(receipt),
                {
                    "schema_version",
                    "state",
                    "reason_code",
                    "plan_ref",
                    "expected_tree_oid",
                    "expected_ref",
                    "expected_parent_oid",
                    "new_commit_oid",
                    "tree_construction",
                    "staged_paths",
                    "post_cas_ref_state",
                    "observed_ref_oid",
                    "real_index_state",
                    "real_index_readback",
                },
            )
            self.assertEqual(receipt["expected_parent_oid"], expected_parent)
            self.assertEqual(self._git(root, "rev-parse", "HEAD").stdout.strip(), receipt["new_commit_oid"])
            self.assertEqual(self._git(root, "show", "-s", "--format=%P", "HEAD").stdout.strip(), expected_parent)
            self.assertEqual(self._git(root, "show", f"HEAD:{owned_rel}").stdout, (root / owned_rel).read_text())
            raw_candidate = FOLLOWUPS_CAPTURE._git(root, "cat-file", "commit", receipt["new_commit_oid"]).stdout
            expected_message = (
                f"docs(closeout): finalize {FOLLOWUPS_CAPTURE.plan_stem(CAPTURE_PLAN_REL)}\n\n"
                f"Planveyor-Plan: {CAPTURE_PLAN_REL}\n"
            ).encode("utf-8")
            self.assertEqual(raw_candidate.partition(b"\n\n")[2], expected_message)
            self.assertFalse(hook_sentinel.exists(), "commit-tree terminal sink must not execute porcelain hooks")
            phases = ref_hook_sentinel.read_text().splitlines()
            self.assertEqual(phases[-2:], ["prepared", "committed"])
            self.assertIn(phases[:-2], ([], ["preparing"]))

    def test_commit_exact_configured_reference_hook_refusal_preserves_ref_and_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            payload, _ = self._capture_docs_payload(root)
            preflight = FOLLOWUPS_CAPTURE.commit_preflight(root, CAPTURE_PLAN_REL, payload)
            hooks = root / "configured-hooks"
            hooks.mkdir()
            self._git(root, "config", "core.hooksPath", str(hooks))
            trace = root / "hook-phases"
            hook = hooks / "reference-transaction"
            hook.write_text(f'#!/bin/sh\nprintf "%s\\n" "$1" >> {shlex.quote(str(trace))}\ncat >/dev/null\n[ "$1" != prepared ]\n')
            hook.chmod(0o755)
            parent = self._git(root, "rev-parse", "HEAD").stdout.strip()
            index = self._git(root, "write-tree").stdout.strip()
            with self.assertRaises(FOLLOWUPS_CAPTURE.CaptureError) as caught:
                FOLLOWUPS_CAPTURE.commit_exact(root, CAPTURE_PLAN_REL, preflight, message_auto=True)
            self.assertEqual(caught.exception.reason_code, "followup_terminal_ref_cas_failed")
            self.assertEqual(self._git(root, "rev-parse", "HEAD").stdout.strip(), parent)
            self.assertEqual(self._git(root, "write-tree").stdout.strip(), index)
            phases = trace.read_text().splitlines()
            self.assertEqual(phases[-2:], ["prepared", "aborted"])
            self.assertIn(phases[:-2], ([], ["preparing"]))

    def test_commit_exact_direct_auto_normalizes_plan_ref_and_source_xor_fails_before_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            payload, _owned_rel = self._capture_docs_payload(root)
            source = root / "legacy-message.txt"
            source.write_text("legacy source\n", encoding="utf-8")
            asserted_preflight = {
                "schema_version": FOLLOWUPS_CAPTURE.PREFLIGHT_SCHEMA_VERSION,
                "state": "ready",
                "plan_ref": CAPTURE_PLAN_REL,
                "docs_closeout_payload": payload,
            }
            head_before = self._git(root, "rev-parse", "HEAD").stdout.strip()
            index_before = self._git(root, "write-tree").stdout.strip()

            with mock.patch.object(FOLLOWUPS_CAPTURE, "commit_preflight") as preflight_call:
                for label, kwargs in (
                    ("neither", {}),
                    ("both", {"message_file": source, "message_auto": True}),
                ):
                    with self.subTest(source_selection=label):
                        with self.assertRaises(FOLLOWUPS_CAPTURE.CaptureError) as caught:
                            FOLLOWUPS_CAPTURE.commit_exact(
                                root,
                                CAPTURE_PLAN_REL,
                                asserted_preflight,
                                **kwargs,
                            )
                        self.assertEqual(caught.exception.reason_code, "followup_terminal_commit_mismatch")
                with self.assertRaises(FOLLOWUPS_CAPTURE.CaptureError) as invalid_ref:
                    FOLLOWUPS_CAPTURE.commit_exact(
                        root,
                        "../invalid.md",
                        asserted_preflight,
                        message_auto=True,
                    )
                self.assertEqual(invalid_ref.exception.reason_code, "followup_capture_plan_ref_invalid")
                preflight_call.assert_not_called()

            self.assertEqual(self._git(root, "rev-parse", "HEAD").stdout.strip(), head_before)
            self.assertEqual(self._git(root, "write-tree").stdout.strip(), index_before)

            preflight = FOLLOWUPS_CAPTURE.commit_preflight(root, CAPTURE_PLAN_REL, payload)
            receipt = FOLLOWUPS_CAPTURE.commit_exact(
                root,
                f"  {CAPTURE_PLAN_REL}  ",
                preflight,
                message_auto=True,
            )
            self.assertEqual(receipt["plan_ref"], CAPTURE_PLAN_REL)
            raw_candidate = FOLLOWUPS_CAPTURE._git(root, "cat-file", "commit", receipt["new_commit_oid"]).stdout
            self.assertEqual(
                raw_candidate.partition(b"\n\n")[2],
                (
                    f"docs(closeout): finalize {FOLLOWUPS_CAPTURE.plan_stem(CAPTURE_PLAN_REL)}\n\n"
                    f"Planveyor-Plan: {CAPTURE_PLAN_REL}\n"
                ).encode("utf-8"),
            )
            first_ref = "docs/plans/260827_1916_process_first.md"
            second_ref = "docs/plans/260827_1916_process_second.md"
            first_message = FOLLOWUPS_CAPTURE._resolve_commit_message(
                first_ref,
                None,
                message_auto=True,
            )
            second_message = FOLLOWUPS_CAPTURE._resolve_commit_message(
                second_ref,
                None,
                message_auto=True,
            )
            self.assertNotEqual(first_message, second_message)
            self.assertIn(b"finalize 260827_1916_process_first", first_message)
            self.assertIn(b"Planveyor-Plan: docs/plans/260827_1916_process_second.md", second_message)

    def test_commit_exact_rejects_tampered_candidate_message_before_callback_or_cas(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            payload, _owned_rel = self._capture_docs_payload(root)
            preflight = FOLLOWUPS_CAPTURE.commit_preflight(root, CAPTURE_PLAN_REL, payload)
            message = root / "message.txt"
            message.write_text("expected terminal message\n", encoding="utf-8")
            foreign_candidate = subprocess.run(
                [
                    "git",
                    "commit-tree",
                    preflight["expected_tree_oid"],
                    "-p",
                    preflight["expected_parent_oid"],
                ],
                cwd=root,
                input=b"tampered terminal message\n",
                capture_output=True,
                check=True,
            ).stdout.decode("ascii").strip()
            head_before = self._git(root, "rev-parse", "HEAD").stdout.strip()
            index_before = self._git(root, "write-tree").stdout.strip()
            before_ref_cas = mock.Mock()
            original_git = FOLLOWUPS_CAPTURE._git

            def return_tampered_candidate(
                project_root: Path,
                *args: str,
                **kwargs: object,
            ) -> subprocess.CompletedProcess[bytes]:
                if args and args[0] == "commit-tree":
                    return subprocess.CompletedProcess(
                        args=["git", "commit-tree"],
                        returncode=0,
                        stdout=(foreign_candidate + "\n").encode("ascii"),
                        stderr=b"",
                    )
                return original_git(project_root, *args, **kwargs)

            with mock.patch.object(FOLLOWUPS_CAPTURE, "_git", side_effect=return_tampered_candidate):
                with self.assertRaises(FOLLOWUPS_CAPTURE.CaptureError) as caught:
                    FOLLOWUPS_CAPTURE.commit_exact(
                        root,
                        CAPTURE_PLAN_REL,
                        preflight,
                        message,
                        before_ref_cas=before_ref_cas,
                    )

            self.assertEqual(caught.exception.reason_code, "followup_terminal_commit_mismatch")
            before_ref_cas.assert_not_called()
            self.assertEqual(self._git(root, "rev-parse", "HEAD").stdout.strip(), head_before)
            self.assertEqual(self._git(root, "write-tree").stdout.strip(), index_before)

    def test_commit_exact_python_cli_rejects_missing_combined_and_repeated_sources(self) -> None:
        parser = FOLLOWUPS_CAPTURE._parser()
        auto = parser.parse_args(
            ["commit-exact", "--plan-ref", CAPTURE_PLAN_REL, "--message-auto"]
        )
        legacy = parser.parse_args(
            ["commit-exact", "--plan-ref", CAPTURE_PLAN_REL, "--message-file", "message.txt"]
        )
        self.assertEqual(auto.message_auto, 1)
        self.assertEqual(auto.message_file, None)
        self.assertEqual(legacy.message_auto, 0)
        self.assertEqual(legacy.message_file, ["message.txt"])

        invalid_sources = (
            (),
            ("--message-auto", "--message-file", "message.txt"),
            ("--message-auto", "--message-auto"),
            ("--message-file", "one.txt", "--message-file", "two.txt"),
        )
        for selectors in invalid_sources:
            with self.subTest(selectors=selectors), mock.patch("sys.stderr", new_callable=io.StringIO):
                with self.assertRaises(SystemExit) as caught:
                    FOLLOWUPS_CAPTURE.main(
                        ["commit-exact", "--plan-ref", CAPTURE_PLAN_REL, *selectors]
                    )
                self.assertEqual(caught.exception.code, 2)

    def test_commit_exact_legacy_message_bytes_stay_compatible_or_fail_closed(self) -> None:
        storable_messages = {
            "utf8": "совместимый legacy message\n".encode("utf-8"),
            "empty": b"",
            "final_lf": b"final line\n",
            "no_final_lf": b"final line",
        }
        for label, message_bytes in storable_messages.items():
            with self.subTest(message_form=label), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                self._init_repo(root)
                payload, _owned_rel = self._capture_docs_payload(root)
                preflight = FOLLOWUPS_CAPTURE.commit_preflight(root, CAPTURE_PLAN_REL, payload)
                message = root / "legacy-message.bin"
                message.write_bytes(message_bytes)

                receipt = FOLLOWUPS_CAPTURE.commit_exact(root, CAPTURE_PLAN_REL, preflight, message)

                raw_candidate = FOLLOWUPS_CAPTURE._git(root, "cat-file", "commit", receipt["new_commit_oid"]).stdout
                self.assertEqual(raw_candidate.partition(b"\n\n")[2], message_bytes)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            payload, _owned_rel = self._capture_docs_payload(root)
            preflight = FOLLOWUPS_CAPTURE.commit_preflight(root, CAPTURE_PLAN_REL, payload)
            message = root / "legacy-message.bin"
            message.write_bytes(b"\xff")
            head_before = self._git(root, "rev-parse", "HEAD").stdout.strip()
            index_before = self._git(root, "write-tree").stdout.strip()
            before_ref_cas = mock.Mock()

            with self.assertRaises(FOLLOWUPS_CAPTURE.CaptureError) as caught:
                FOLLOWUPS_CAPTURE.commit_exact(
                    root,
                    CAPTURE_PLAN_REL,
                    preflight,
                    message,
                    before_ref_cas=before_ref_cas,
                )

            self.assertEqual(caught.exception.reason_code, "followup_terminal_commit_mismatch")
            before_ref_cas.assert_not_called()
            self.assertEqual(self._git(root, "rev-parse", "HEAD").stdout.strip(), head_before)
            self.assertEqual(self._git(root, "write-tree").stdout.strip(), index_before)

    def test_shell_commit_exact_rejects_invalid_message_selector_combinations_before_delegation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            payload, _owned_rel = self._capture_docs_payload(root)
            preflight = FOLLOWUPS_CAPTURE.commit_preflight(root, CAPTURE_PLAN_REL, payload)
            preflight_path = self._write_json(root, "preflight.json", preflight)
            message = root / "legacy-message.txt"
            message.write_text("legacy selector\n", encoding="utf-8")
            head_before = self._git(root, "rev-parse", "HEAD").stdout.strip()
            index_before = self._git(root, "write-tree").stdout.strip()
            objects_before = self._git(root, "count-objects", "-v").stdout
            prefix = (
                "planveyor_plan_bundle --commit-exact "
                f"--preflight-json {shlex.quote(str(preflight_path))} "
            )
            invalid_commands = {
                "neither": prefix + CAPTURE_PLAN_REL,
                "both": prefix
                + f"--message-auto --message-file {shlex.quote(str(message))} {CAPTURE_PLAN_REL}",
                "repeat_auto": prefix + f"--message-auto --message-auto {CAPTURE_PLAN_REL}",
                "repeat_file": prefix
                + f"--message-file {shlex.quote(str(message))} --message-file {shlex.quote(str(message))} {CAPTURE_PLAN_REL}",
                "adjacent_repeat_file": prefix + f"--message-file --message-file {CAPTURE_PLAN_REL}",
                "adjacent_both": prefix + f"--message-file --message-auto {CAPTURE_PLAN_REL}",
                "option_like_auto_assignment": prefix + f"--message-file --message-auto=value {CAPTURE_PLAN_REL}",
                "option_like_preflight": prefix + f"--message-file --preflight-json {CAPTURE_PLAN_REL}",
            }

            for label, command in invalid_commands.items():
                with self.subTest(selector_case=label):
                    result = self._run_shell(root, command)
                    output = result.stdout + result.stderr
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn("Usage: planveyor_plan_bundle --commit-exact", result.stderr)
                    self.assertNotIn("followups_capture.py", output)
                    self.assertEqual(self._git(root, "rev-parse", "HEAD").stdout.strip(), head_before)
                    self.assertEqual(self._git(root, "write-tree").stdout.strip(), index_before)
                    self.assertEqual(self._git(root, "count-objects", "-v").stdout, objects_before)

            selector_like_filename = root / "--message-auto"
            selector_like_filename.write_text("legacy selector-like filename\n", encoding="utf-8")
            explicit_filename = self._run_shell(
                root,
                prefix + f"--message-file ./--message-auto {CAPTURE_PLAN_REL}",
            )
            self.assertEqual(explicit_filename.returncode, 0, explicit_filename.stdout + explicit_filename.stderr)

    def test_shell_rejects_message_auto_outside_commit_exact_modes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._capture_docs_payload(root)
            commands = {
                "rejected_lifecycle": f"planveyor_plan_bundle --capture-rejected --message-auto {CAPTURE_PLAN_REL}",
                "ordinary_bundle": f"planveyor_plan_bundle --print --message-auto {CAPTURE_PLAN_REL}",
                "closeout_json": f"planveyor_plan_bundle --closeout-json --message-auto {CAPTURE_PLAN_REL}",
                "stage": f"planveyor_plan_bundle --stage --message-auto {CAPTURE_PLAN_REL}",
                "commit_ready": f"planveyor_plan_bundle --commit-ready --message-auto {CAPTURE_PLAN_REL}",
                "docs_closeout_json": (
                    "planveyor_plan_bundle --stage --docs-closeout-json /dev/null "
                    f"--message-auto {CAPTURE_PLAN_REL}"
                ),
            }

            for label, command in commands.items():
                with self.subTest(mode=label):
                    result = self._run_shell(root, command)
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertTrue(
                        "message options are" in result.stderr
                        or "closeout/preflight/message options are unavailable" in result.stderr,
                        result.stdout + result.stderr,
                    )

    def test_v2_external_followup_stage_preflight_and_commit_exact_rederives_exact_proof(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            payload, carrier_rel, pi_paths = self._capture_v2_external_docs_payload(root)
            expected_paths = list(payload["final_docs_diff_paths"])
            self.assertEqual(expected_paths, sorted(expected_paths))
            self.assertEqual(len(expected_paths), 5)
            self.assertIn(carrier_rel, expected_paths)
            self.assertEqual(len(pi_paths), 4)
            expectation = next(
                item
                for item in payload["architect_final_handoff"]["followups_staging_expectations"]
                if item["path"] == carrier_rel
            )
            self.assertEqual(expectation["ownership_class"], "ordinary_followup")
            self.assertIn("ownership_proof", expectation)
            payload_path = self._write_json(root, "v2-docs-closeout.json", payload)
            foreign_rel = "docs/foreign-unowned.md"
            (root / foreign_rel).write_text("must remain outside exact V2 staging\n", encoding="utf-8")
            index_before = self._git(root, "write-tree").stdout.strip()

            stage = self._run_shell(
                root,
                f"planveyor_plan_bundle --stage --docs-closeout-json {shlex.quote(str(payload_path))} {CAPTURE_PLAN_REL}",
            )
            self.assertEqual(stage.returncode, 0, stage.stdout + stage.stderr)
            stage_payload = json.loads(stage.stdout)
            self.assertEqual(
                [item["path"] for item in stage_payload["staging_verifications"]],
                expected_paths,
            )
            self.assertEqual(self._git(root, "write-tree").stdout.strip(), index_before)

            preflight = self._run_shell(
                root,
                f"planveyor_plan_closeout_preflight --docs-closeout-json {shlex.quote(str(payload_path))} --json {CAPTURE_PLAN_REL}",
            )
            self.assertEqual(preflight.returncode, 0, preflight.stdout + preflight.stderr)
            preflight_payload = json.loads(preflight.stdout)
            self.assertEqual(
                [item["path"] for item in preflight_payload["staged_paths"]],
                expected_paths,
            )
            preflight_path = self._write_json(root, "v2-preflight.json", preflight_payload)
            message_path = root / "message.txt"
            message_path.write_text("exact V2 external docs closeout\n", encoding="utf-8")

            exact = self._run_shell(
                root,
                "planveyor_plan_bundle --commit-exact "
                f"--preflight-json {shlex.quote(str(preflight_path))} "
                f"--message-file {shlex.quote(str(message_path))} {CAPTURE_PLAN_REL}",
            )
            self.assertEqual(exact.returncode, 0, exact.stdout + exact.stderr)
            receipt = json.loads(exact.stdout)
            self.assertEqual(self._git(root, "rev-parse", "HEAD").stdout.strip(), receipt["new_commit_oid"])
            self.assertEqual(
                self._git(root, "show", f"HEAD:{carrier_rel}").stdout,
                (root / carrier_rel).read_text(encoding="utf-8"),
            )
            missing_foreign = subprocess.run(
                ["git", "cat-file", "-e", f"HEAD:{foreign_rel}"],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(missing_foreign.returncode, 0)

    def test_v2_external_stage_rejects_payload_and_object_drift_before_index_mutation(self) -> None:
        for drift_kind in ("malformed_proof", "projection_drift", "object_drift"):
            with self.subTest(drift_kind=drift_kind), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                self._init_repo(root)
                payload, carrier_rel, _pi_paths = self._capture_v2_external_docs_payload(root)
                expectation = next(
                    item
                    for item in payload["architect_final_handoff"]["followups_staging_expectations"]
                    if item["path"] == carrier_rel
                )
                if drift_kind == "malformed_proof":
                    expectation["ownership_proof"]["unexpected"] = True
                elif drift_kind == "projection_drift":
                    expectation["ownership_proof"]["expected_parent_oid"] = "0" * 40
                else:
                    with (root / carrier_rel).open("a", encoding="utf-8") as handle:
                        handle.write("\n")
                index_before = self._git(root, "write-tree").stdout.strip()
                head_before = self._git(root, "rev-parse", "HEAD").stdout.strip()

                with self.assertRaises(FOLLOWUPS_CAPTURE.CaptureError) as caught:
                    FOLLOWUPS_CAPTURE.stage_docs_closeout(root, CAPTURE_PLAN_REL, payload, mutate=True)

                expected_reason = {
                    "malformed_proof": "followup_staging_payload_invalid",
                    "projection_drift": "followup_staging_receipt_drift",
                    "object_drift": "followup_staging_object_drift",
                }[drift_kind]
                self.assertEqual(caught.exception.reason_code, expected_reason)
                self.assertEqual(self._git(root, "write-tree").stdout.strip(), index_before)
                self.assertEqual(self._git(root, "rev-parse", "HEAD").stdout.strip(), head_before)

    def test_v2_external_stage_and_preflight_reject_foreign_frozen_source_before_index_or_ref_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            payload, _carrier_rel, _pi_paths = self._capture_v2_external_docs_payload(
                root,
                include_foreign_terminal=True,
            )
            foreign_plan_rel = "docs/plans/260721_0201_foreign_terminal_capture_fixture.md"
            manifest_path = FOLLOWUPS_CAPTURE.v2_frozen_manifest_path(root, CAPTURE_PLAN_REL)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            foreign_bytes = self._git(root, "show", f"HEAD:{foreign_plan_rel}").stdout.encode("utf-8")
            manifest.update(
                {
                    "plan_ref": foreign_plan_rel,
                    "source_plan_blob_oid": self._git(root, "rev-parse", f"HEAD:{foreign_plan_rel}").stdout.strip(),
                    "source_plan_sha256": hashlib.sha256(foreign_bytes).hexdigest(),
                }
            )
            # The immutable A carrier and capture remain untouched: only the
            # namespaced frozen source is forged after projection.
            FOLLOWUPS_CAPTURE.persist_v2_frozen_manifest(root, CAPTURE_PLAN_REL, manifest)
            index_before = self._git(root, "write-tree").stdout.strip()
            head_before = self._git(root, "rev-parse", "HEAD").stdout.strip()

            with self.assertRaises(FOLLOWUPS_CAPTURE.CaptureError) as stage_caught:
                FOLLOWUPS_CAPTURE.stage_docs_closeout(root, CAPTURE_PLAN_REL, payload, mutate=True)
            with self.assertRaises(FOLLOWUPS_CAPTURE.CaptureError) as preflight_caught:
                FOLLOWUPS_CAPTURE.commit_preflight(root, CAPTURE_PLAN_REL, payload)

            self.assertEqual(stage_caught.exception.reason_code, "followup_staging_receipt_drift")
            self.assertEqual(preflight_caught.exception.reason_code, "followup_staging_receipt_drift")
            self.assertEqual(self._git(root, "write-tree").stdout.strip(), index_before)
            self.assertEqual(self._git(root, "rev-parse", "HEAD").stdout.strip(), head_before)

    def test_commit_exact_rejects_empty_noop_payload_without_index_or_ref_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            payload, _readback = self._capture_empty_docs_payload(root)
            parent_before = self._git(root, "rev-parse", "HEAD").stdout.strip()
            index_before = self._git(root, "write-tree").stdout.strip()
            message = root / "message.txt"
            message.write_text("must not create an empty commit\n", encoding="utf-8")
            asserted_preflight = {
                "schema_version": FOLLOWUPS_CAPTURE.PREFLIGHT_SCHEMA_VERSION,
                "state": "ready",
                "plan_ref": CAPTURE_PLAN_REL,
                "docs_closeout_payload": payload,
            }

            with self.assertRaises(FOLLOWUPS_CAPTURE.CaptureError) as caught:
                FOLLOWUPS_CAPTURE.commit_exact(root, CAPTURE_PLAN_REL, asserted_preflight, message)

            self.assertEqual(caught.exception.reason_code, "followup_terminal_tree_drift")
            self.assertEqual(self._git(root, "write-tree").stdout.strip(), index_before)
            self.assertEqual(self._git(root, "rev-parse", "HEAD").stdout.strip(), parent_before)

    def test_stage_rejects_self_asserted_foreign_path_without_index_or_ref_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            payload, readback = self._capture_empty_docs_payload(root)
            foreign_rel = "docs/foreign-workstream.md"
            foreign = root / foreign_rel
            foreign.write_text("foreign changed bytes\n", encoding="utf-8")
            foreign_object, _foreign_data = FOLLOWUPS_CAPTURE.read_repo_regular_path(root, foreign_rel)
            fake_expectation = {
                "capture_cycle_id": readback["capture_cycle_id"],
                "receipt_revision": readback["receipt_revision"],
                "receipt_content_sha256": readback["receipt_content_sha256"],
                "receipt_object_identity": readback["receipt_object_identity"],
                "path": foreign_rel,
                "ownership_class": "process_improvement",
                "ownership_proof": {"source_ref": CAPTURE_PLAN_REL, "allowed_paths": [foreign_rel]},
                "expected_object": foreign_object,
                "expected_staged_mode": "100644",
            }
            payload.update(
                {
                    "final_docs_commit": "required",
                    "current_plan_owned_docs_delta_paths": [foreign_rel],
                    "final_docs_diff_paths": [foreign_rel],
                    "architect_final_handoff": {
                        "required": True,
                        "plan_ref": CAPTURE_PLAN_REL,
                        "final_docs_diff_paths": [foreign_rel],
                        "followups_staging_expectations": [fake_expectation],
                    },
                }
            )
            parent_before = self._git(root, "rev-parse", "HEAD").stdout.strip()
            index_before = self._git(root, "write-tree").stdout.strip()

            with self.assertRaises(FOLLOWUPS_CAPTURE.CaptureError) as caught:
                FOLLOWUPS_CAPTURE.stage_docs_closeout(root, CAPTURE_PLAN_REL, payload, mutate=True)

            self.assertIn(
                caught.exception.reason_code,
                {
                    "followup_staging_pi_cycle_invalid",
                    "followup_staging_pi_receipt_invalid",
                    "followup_staging_pi_ownership_invalid",
                },
            )
            self.assertEqual(self._git(root, "write-tree").stdout.strip(), index_before)
            self.assertEqual(self._git(root, "rev-parse", "HEAD").stdout.strip(), parent_before)
            self.assertEqual(self._git(root, "diff", "--cached", "--name-only").stdout, "")

    def test_stage_accepts_source_bound_process_improvement_with_exact_blob_proof(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            collect = FOLLOWUPS_CAPTURE.process_improvements_collect
            backlog_rel = collect.backlog_rel_path_for_source_ref(CAPTURE_PLAN_REL)

            suggestion = (
                "## Process improvements\n"
                "### Suggestion 1\n"
                "- symptom: exact stage fixture needs a source-bound PI object\n"
                "- process_gap: fixture omitted the general collector bridge\n"
                "- suggested_fix: materialize the PI through the bound collector chain\n"
                "- owner: Architect\n"
                "- promotion_class: helper_change\n"
                "- trigger_ref: docs/code_reviews/fixture.md#B1\n"
                f"- source_ref: {CAPTURE_PLAN_REL}\n"
            )

            def collector_text(role_name: str, _cycle_id: str) -> str:
                if role_name == "Coder":
                    return suggestion
                if role_name in {"Planner", "Reviewer"}:
                    return "## Process improvements\nNO PROCESS IMPROVEMENTS — why: already_tracked\n"
                return "## Process improvements\nNO PROCESS IMPROVEMENTS — why: clean_run\n"

            payload, readback = self._capture_empty_docs_payload(
                root,
                general_pi_text=collector_text,
            )
            backlog = root / backlog_rel
            expectations = FOLLOWUPS_CAPTURE.process_improvement_staging_expectations(
                root,
                CAPTURE_PLAN_REL,
                [backlog_rel],
                capture_binding=readback,
            )
            payload.update(
                {
                    "final_docs_commit": "required",
                    "current_plan_owned_docs_delta_paths": [backlog_rel],
                    "final_docs_diff_paths": [backlog_rel],
                    "architect_final_handoff": {
                        "required": True,
                        "plan_ref": CAPTURE_PLAN_REL,
                        "final_docs_diff_paths": [backlog_rel],
                        "followups_staging_expectations": expectations,
                    },
                }
            )

            stage = FOLLOWUPS_CAPTURE.stage_docs_closeout(root, CAPTURE_PLAN_REL, payload, mutate=True)

            self.assertEqual(stage["state"], "prepared")
            self.assertEqual(len(stage["staging_verifications"]), 1)
            self.assertEqual(stage["staging_verifications"][0]["path"], backlog_rel)
            self.assertEqual(stage["staging_verifications"][0]["ownership_class"], "process_improvement")
            self.assertEqual(
                stage["staging_verifications"][0]["ownership_proof"]["source_ref"],
                CAPTURE_PLAN_REL,
            )
            self.assertEqual(stage["staging_verifications"][0]["blob_mode"], "100644")
            blob_oid = stage["staging_verifications"][0]["blob_oid"]
            self.assertEqual(self._git(root, "cat-file", "blob", blob_oid).stdout, backlog.read_text(encoding="utf-8"))
            self.assertEqual(self._git(root, "diff", "--cached", "--name-only").stdout, "")

            original_backlog = backlog.read_bytes()
            index_before = self._git(root, "write-tree").stdout.strip()
            parent_before = self._git(root, "rev-parse", "HEAD").stdout.strip()
            backlog.write_text("drifted PI bytes\n", encoding="utf-8")
            with self.assertRaises(FOLLOWUPS_CAPTURE.CaptureError) as drift:
                FOLLOWUPS_CAPTURE.stage_docs_closeout(root, CAPTURE_PLAN_REL, payload, mutate=True)
            self.assertEqual(
                drift.exception.reason_code,
                "followup_capture_pi_general_checkpoint_live_drift",
            )
            self.assertEqual(self._git(root, "write-tree").stdout.strip(), index_before)
            self.assertEqual(self._git(root, "rev-parse", "HEAD").stdout.strip(), parent_before)
            backlog.write_bytes(original_backlog)

            foreign_rel = "docs/process_improvements/260721_9999_foreign__process_improvements_backlog.md"
            (root / foreign_rel).write_text("foreign uncommitted backlog\n", encoding="utf-8")
            with self.assertRaises(FOLLOWUPS_CAPTURE.CaptureError) as foreign:
                FOLLOWUPS_CAPTURE.stage_docs_closeout(root, CAPTURE_PLAN_REL, payload, mutate=True)
            self.assertEqual(
                foreign.exception.reason_code,
                "followup_capture_pi_general_checkpoint_derived_mismatch",
            )

    def test_commit_exact_ignores_unrelated_shared_index_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            payload, _owned_rel = self._capture_docs_payload(root)
            FOLLOWUPS_CAPTURE.stage_docs_closeout(root, CAPTURE_PLAN_REL, payload, mutate=True)
            preflight = FOLLOWUPS_CAPTURE.commit_preflight(root, CAPTURE_PLAN_REL, payload)
            extra = root / "docs/foreign.md"
            extra.write_text("foreign\n", encoding="utf-8")
            self._git(root, "add", "docs/foreign.md")
            message = root / "message.txt"
            message.write_text("commit only admitted docs\n", encoding="utf-8")

            receipt = FOLLOWUPS_CAPTURE.commit_exact(root, CAPTURE_PLAN_REL, preflight, message)

            self.assertEqual(receipt["state"], "committed")
            self.assertEqual(self._git(root, "ls-tree", "-r", "--name-only", "HEAD", "--", "docs/foreign.md").stdout, "")
            self.assertEqual(self._git(root, "diff", "--cached", "--name-only").stdout.strip(), "docs/foreign.md")

    def test_isolated_tree_excludes_shared_index_mutation_during_write_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            payload, owned_rel = self._capture_docs_payload(root)
            FOLLOWUPS_CAPTURE.stage_docs_closeout(root, CAPTURE_PLAN_REL, payload, mutate=True)
            foreign_rel = "docs/foreign-race.md"
            (root / foreign_rel).write_text("foreign staged bytes\n", encoding="utf-8")
            original_git = FOLLOWUPS_CAPTURE._git

            def inject_shared_index(
                project_root: Path,
                *args: str,
                **kwargs: object,
            ) -> subprocess.CompletedProcess[bytes]:
                env_overrides = kwargs.get("env_overrides")
                if args == ("write-tree",) and isinstance(env_overrides, dict) and env_overrides.get("GIT_INDEX_FILE"):
                    original_git(project_root, "add", "--", foreign_rel)
                return original_git(project_root, *args, **kwargs)

            with mock.patch.object(FOLLOWUPS_CAPTURE, "_git", side_effect=inject_shared_index):
                preflight = FOLLOWUPS_CAPTURE.commit_preflight(root, CAPTURE_PLAN_REL, payload)

            tree_paths = self._git(root, "ls-tree", "-r", "--name-only", preflight["expected_tree_oid"]).stdout.splitlines()
            self.assertIn(owned_rel, tree_paths)
            self.assertNotIn(foreign_rel, tree_paths)
            self.assertEqual(preflight["tree_construction"], "isolated_index_from_expected_parent")

            self._git(root, "reset", "--", foreign_rel)
            message = root / "message.txt"
            message.write_text("isolated exact docs closeout\n", encoding="utf-8")
            with mock.patch.object(FOLLOWUPS_CAPTURE, "_git", side_effect=inject_shared_index):
                receipt = FOLLOWUPS_CAPTURE.commit_exact(root, CAPTURE_PLAN_REL, preflight, message)

            final_paths = self._git(root, "ls-tree", "-r", "--name-only", "HEAD").stdout.splitlines()
            self.assertEqual(receipt["tree_construction"], "isolated_index_from_expected_parent")
            self.assertIn(owned_rel, final_paths)
            self.assertNotIn(foreign_rel, final_paths)
            self.assertEqual(self._git(root, "diff", "--cached", "--name-only").stdout.strip(), foreign_rel)

    def test_exact_commit_ignores_ambient_git_index_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            payload, owned_rel = self._capture_docs_payload(root)
            message = root / "message.txt"
            message.write_text("ignore ambient index override\n", encoding="utf-8")
            ambient_index = root / "ambient.index"

            with mock.patch.dict(os.environ, {"GIT_INDEX_FILE": str(ambient_index)}):
                preflight = FOLLOWUPS_CAPTURE.commit_preflight(root, CAPTURE_PLAN_REL, payload)
                receipt = FOLLOWUPS_CAPTURE.commit_exact(root, CAPTURE_PLAN_REL, preflight, message)

            self.assertEqual(receipt["state"], "committed")
            self.assertFalse(ambient_index.exists())
            self.assertEqual(self._git(root, "show", f"HEAD:{owned_rel}").stdout, (root / owned_rel).read_text())

    def test_commit_exact_expected_ref_race_fails_cas_and_leaves_candidate_unreachable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            payload, _owned_rel = self._capture_docs_payload(root)
            FOLLOWUPS_CAPTURE.stage_docs_closeout(root, CAPTURE_PLAN_REL, payload, mutate=True)
            preflight = FOLLOWUPS_CAPTURE.commit_preflight(root, CAPTURE_PLAN_REL, payload)
            message = root / "message.txt"
            message.write_text("candidate before race\n", encoding="utf-8")
            race: dict[str, str] = {}

            def move_ref(candidate: str) -> None:
                race["candidate"] = candidate
                tree = self._git(root, "show", "-s", "--format=%T", preflight["expected_parent_oid"]).stdout.strip()
                race_commit = subprocess.run(
                    ["git", "commit-tree", tree, "-p", preflight["expected_parent_oid"]],
                    cwd=root,
                    input="race\n",
                    text=True,
                    capture_output=True,
                    check=True,
                ).stdout.strip()
                race["commit"] = race_commit
                self._git(root, "update-ref", preflight["expected_ref"], race_commit, preflight["expected_parent_oid"])

            with self.assertRaises(FOLLOWUPS_CAPTURE.CaptureError) as caught:
                FOLLOWUPS_CAPTURE.commit_exact(
                    root,
                    CAPTURE_PLAN_REL,
                    preflight,
                    message,
                    before_ref_cas=move_ref,
                )

            self.assertEqual(caught.exception.reason_code, "followup_terminal_ref_cas_failed")
            self.assertEqual(caught.exception.details["unreachable_commit_oid"], race["candidate"])
            self.assertEqual(self._git(root, "rev-parse", preflight["expected_ref"]).stdout.strip(), race["commit"])
            self.assertNotEqual(race["candidate"], race["commit"])

    def test_post_cas_ref_advance_returns_committed_readback_without_retry_signal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            payload, _owned_rel = self._capture_docs_payload(root)
            preflight = FOLLOWUPS_CAPTURE.commit_preflight(root, CAPTURE_PLAN_REL, payload)
            message = root / "message.txt"
            message.write_text("linearized exact closeout\n", encoding="utf-8")
            race: dict[str, str] = {}

            def advance_after_cas(candidate: str) -> None:
                race_commit = subprocess.run(
                    ["git", "commit-tree", preflight["expected_tree_oid"], "-p", candidate],
                    cwd=root,
                    input="later commit\n",
                    text=True,
                    capture_output=True,
                    check=True,
                ).stdout.strip()
                self._git(root, "update-ref", preflight["expected_ref"], race_commit, candidate)
                race["commit"] = race_commit

            receipt = FOLLOWUPS_CAPTURE.commit_exact(
                root,
                CAPTURE_PLAN_REL,
                preflight,
                message,
                after_ref_cas=advance_after_cas,
            )

            self.assertEqual(receipt["state"], "committed")
            self.assertEqual(receipt["post_cas_ref_state"], "advanced_after_commit")
            self.assertEqual(receipt["observed_ref_oid"], race["commit"])
            self.assertEqual(self._git(root, "rev-parse", "HEAD").stdout.strip(), race["commit"])

    def test_post_cas_real_index_reconciliation_failure_stays_committed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            payload, owned_rel = self._capture_docs_payload(root)
            preflight = FOLLOWUPS_CAPTURE.commit_preflight(root, CAPTURE_PLAN_REL, payload)
            message = root / "message.txt"
            message.write_text("commit survives index reconciliation failure\n", encoding="utf-8")
            original_git = FOLLOWUPS_CAPTURE._git
            after_cas = {"value": False}

            def fail_real_index(
                project_root: Path,
                *args: str,
                **kwargs: object,
            ) -> subprocess.CompletedProcess[bytes]:
                if after_cas["value"] and args and args[0] == "update-index" and not kwargs.get("env_overrides"):
                    raise FOLLOWUPS_CAPTURE.CaptureError(
                        "followup_terminal_git_failed",
                        "forced real-index reconciliation failure",
                    )
                return original_git(project_root, *args, **kwargs)

            with mock.patch.object(FOLLOWUPS_CAPTURE, "_git", side_effect=fail_real_index):
                receipt = FOLLOWUPS_CAPTURE.commit_exact(
                    root,
                    CAPTURE_PLAN_REL,
                    preflight,
                    message,
                    after_ref_cas=lambda _candidate: after_cas.update(value=True),
                )

            self.assertEqual(receipt["state"], "committed")
            self.assertEqual(receipt["real_index_state"], "diverged_preserved")
            self.assertEqual(
                receipt["real_index_readback"]["reason_code"],
                "followup_terminal_git_failed",
            )
            self.assertEqual(self._git(root, "show", f"HEAD:{owned_rel}").stdout, (root / owned_rel).read_text())

    def test_capture_preflight_accepts_same_content_replacement_and_rejects_detached_head(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            payload, owned_rel = self._capture_docs_payload(root)
            FOLLOWUPS_CAPTURE.stage_docs_closeout(root, CAPTURE_PLAN_REL, payload, mutate=True)
            original = (root / owned_rel).read_bytes()
            replacement = root / "docs/followups/replacement.tmp"
            replacement.write_bytes(original)
            replacement.replace(root / owned_rel)
            preflight = FOLLOWUPS_CAPTURE.commit_preflight(root, CAPTURE_PLAN_REL, payload)
            self.assertEqual(preflight["state"], "ready")

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            payload, _owned_rel = self._capture_docs_payload(root)
            FOLLOWUPS_CAPTURE.stage_docs_closeout(root, CAPTURE_PLAN_REL, payload, mutate=True)
            self._git(root, "checkout", "--detach")
            with self.assertRaises(FOLLOWUPS_CAPTURE.CaptureError) as detached:
                FOLLOWUPS_CAPTURE.commit_preflight(root, CAPTURE_PLAN_REL, payload)
            self.assertEqual(detached.exception.reason_code, "followup_terminal_ref_unsupported")

    def test_commit_ready_clean_bundle_returns_zero_and_prints_exact_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)
            self._materialize_bundle(root)

            stage = self._run_bundle(root, "--stage")
            self.assertEqual(stage.returncode, 0, stage.stderr)

            result = self._run_bundle(root, "--commit-ready")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Commit-ready [", result.stdout)
            self.assertIn('commit -m "<message>" --', result.stdout)
            self.assertIn(PRIMARY_TARGET_REL, result.stdout)
            self.assertIn("Staged set matches explicit bundle.", result.stdout)
            self.assertIn("Commit-ready guard passed across 1 repo root(s).", result.stdout)

    def test_preflight_from_thin_shim_repo_uses_tooling_local_helper_modules(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root, thin_shim=True, copy_helper_modules=False)
            self._materialize_bundle(root)
            self._commit_all(root, "baseline")

            self.assertFalse((root / "scripts" / "plan_lint.py").exists())
            self.assertFalse((root / "scripts" / "review_artifact_lint.py").exists())

            result = self._run_bundle(root, "--preflight")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("ModuleNotFoundError", result.stderr)
            self.assertIn("Summary:", result.stdout)

    def test_commit_ready_fails_closed_when_unrelated_staged_path_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)
            self._materialize_bundle(root)

            stage = self._run_bundle(root, "--stage")
            self.assertEqual(stage.returncode, 0, stage.stderr)

            extra_rel = "notes/unrelated.txt"
            extra_path = root / extra_rel
            extra_path.parent.mkdir(parents=True, exist_ok=True)
            extra_path.write_text("extra\n", encoding="utf-8")
            self._git(root, "add", extra_rel)

            result = self._run_bundle(root, "--commit-ready")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn('commit -m "<message>" --', result.stdout)
            self.assertIn("Offending staged paths:", result.stdout)
            self.assertIn(extra_rel, result.stdout)

    def test_commit_ready_accepts_represented_staged_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)
            deleted_rel = "docs/obsolete_ledger.md"
            self._materialize_bundle(root, deleted_paths=[deleted_rel])
            self._commit_all(root, "baseline")
            (root / deleted_rel).unlink()

            preflight = self._run_bundle(root, "--preflight")
            self.assertEqual(preflight.returncode, 0, preflight.stderr)

            stage = self._run_bundle(root, "--stage")
            self.assertEqual(stage.returncode, 0, stage.stderr)

            result = self._run_bundle(root, "--commit-ready")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(deleted_rel, result.stdout)
            self.assertIn("Staged set matches explicit bundle.", result.stdout)

            payload = self._run_bundle_json(root)
            self.assertEqual(payload["closeout_kind"], "commit_ready")
            repo_payload = payload["repo_roots"][0]
            self.assertIn(deleted_rel, repo_payload["staged_bundle_paths"])
            self.assertEqual(repo_payload["staged_extra_paths"], [])

    def test_commit_ready_rejects_unrelated_staged_path_with_represented_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)
            deleted_rel = "docs/obsolete_ledger.md"
            self._materialize_bundle(root, deleted_paths=[deleted_rel])
            self._commit_all(root, "baseline")
            (root / deleted_rel).unlink()

            stage = self._run_bundle(root, "--stage")
            self.assertEqual(stage.returncode, 0, stage.stderr)

            extra_rel = "notes/unrelated.txt"
            extra_path = root / extra_rel
            extra_path.parent.mkdir(parents=True, exist_ok=True)
            extra_path.write_text("extra\n", encoding="utf-8")
            self._git(root, "add", extra_rel)

            result = self._run_bundle(root, "--commit-ready")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Offending staged paths:", result.stdout)
            self.assertIn(extra_rel, result.stdout)

    def test_commit_ready_prints_separate_commands_for_each_git_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)

            sibling_root = root / "mirror_root"
            self._init_repo(sibling_root)
            sibling_rel = "shared/mirror_target.txt"
            sibling_path = sibling_root / sibling_rel
            sibling_path.parent.mkdir(parents=True, exist_ok=True)
            sibling_path.write_text("mirror\n", encoding="utf-8")

            self._materialize_bundle(root, extra_targets=[str(sibling_path)])

            stage = self._run_bundle(root, "--stage")
            self.assertEqual(stage.returncode, 0, stage.stderr)

            result = self._run_bundle(root, "--commit-ready")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.count('commit -m "<message>" --'), 2)
            self.assertIn(str(root), result.stdout)
            self.assertIn(str(sibling_root), result.stdout)
            self.assertIn(PRIMARY_TARGET_REL, result.stdout)
            self.assertIn(sibling_rel, result.stdout)
            self.assertIn("Commit-ready guard passed across 2 repo root(s).", result.stdout)

    def test_preflight_allows_missing_first_pass_review_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)
            self._materialize_bundle(root, materialize_review=False)

            preflight = self._run_bundle(root, "--preflight")
            check = self._run_bundle(root, "--check")

            self.assertEqual(preflight.returncode, 0, preflight.stderr)
            self.assertIn("PLANNED", preflight.stdout)
            self.assertIn(REVIEW_REL, preflight.stdout)
            self.assertIn("Preflight guard passed across 1 repo root(s).", preflight.stdout)
            self.assertNotEqual(check.returncode, 0)
            self.assertIn("MISSING-PATH", check.stdout)
            self.assertIn(REVIEW_REL, check.stdout)

            payload = self._run_bundle_json(root)
            self.assertFalse(payload["bundle_ok"])
            self.assertEqual(payload["closeout_kind"], "needs_rerun")
            self.assertEqual(len(payload["review_artifact_receipts"]), 1)
            receipt = payload["review_artifact_receipts"][0]
            self.assertEqual(receipt["origin_plan"], PLAN_REL)
            self.assertEqual(receipt["declared_review_artifact"], REVIEW_REL)
            self.assertEqual(receipt["receipt_state"], "missing")
            self.assertEqual(receipt["blocker_code"], "missing_declared_review_artifact")
            self.assertEqual(receipt["next_owner"], "Reviewer")

    def test_preflight_has_no_retired_terminal_baseline_validator(self) -> None:
        runtime = PLANVEYOR_SCRIPT.read_text(encoding="utf-8")

        self.assertNotIn("plan_lint.validate_semantic_checkpoint_admission_baseline", runtime)

    def test_origin_plan_stays_in_exact_bundle_outside_review_target_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._materialize_bundle(root, materialize_review=False)

            preflight = self._run_bundle(root, "--preflight")
            draft_payload = json.loads(
                re.search(
                    r"```json\s*(\{.*?\})\s*```",
                    (root / DRAFT_REL).read_text(encoding="utf-8"),
                    re.DOTALL,
                ).group(1)
            )
            review_targets = {
                item["path"]
                for item in draft_payload["code_draft_meta"]["targets"]
            }
            strict_target = self._compute_strict_target(root)

        self.assertEqual(preflight.returncode, 0, preflight.stderr)
        self.assertRegex(
            preflight.stdout,
            rf"(?m)^\s+- OK\s+{re.escape(PLAN_REL)} \[plan\]$",
        )
        self.assertNotIn(PLAN_REL, review_targets)
        self.assertRegex(strict_target, r"^BUNDLE=current bundle_sha256=[0-9a-f]{64}$")

    def test_self_target_metadata_is_rejected_without_duplicate_bundle_carrier(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._materialize_bundle(
                root,
                extra_targets=[PLAN_REL],
                materialize_review=False,
            )
            bundle = self._run_bundle(root, "--preflight")
            plan_path = root / PLAN_REL
            findings = PLAN_LINT.validate_origin_plan_review_targets(
                plan_path,
                plan_path.read_text(encoding="utf-8").splitlines(),
                raw_status_value="Ready for Coder",
                effective_status_value="Ready for Coder",
                plan_type="dev",
                plan_meta_obj=None,
                code_draft_refs=[(1, DRAFT_REL)],
                plan_repo_root=root,
            )
            env = os.environ.copy()
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            snapshot = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "review_target_snapshot.py"),
                    PLAN_REL,
                    "--current-bundle",
                    "--project-root",
                    str(root),
                ],
                cwd=root,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(bundle.returncode, 0, bundle.stderr)
        self.assertEqual(bundle.stdout.count(f"{PLAN_REL} [target,plan]"), 1)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "ERROR")
        self.assertIn("origin_plan_in_review_targets", findings[0].message)
        self.assertEqual(snapshot.returncode, 1)
        self.assertEqual(snapshot.stdout, "")
        self.assertIn("origin_plan_in_review_targets", snapshot.stderr)

    def test_preflight_rejects_missing_code_draft_meta(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)
            self._materialize_bundle(root, materialize_review=False)
            (root / DRAFT_REL).write_text("# code draft without metadata\n", encoding="utf-8")

            preflight = self._run_bundle(root, "--preflight")

            self.assertNotEqual(preflight.returncode, 0)
            self.assertIn("machine_authority_decision_code_draft_ref_invalid", preflight.stderr)
            self.assertIn("expected exactly one code_draft_meta JSON carrier", preflight.stderr)

    def test_preflight_rejects_stale_target_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)
            stale_rel = "scripts/stale_target.py"
            self._materialize_bundle(root, extra_targets=[stale_rel], materialize_review=False)

            preflight = self._run_bundle(root, "--preflight")

            self.assertNotEqual(preflight.returncode, 0)
            self.assertIn("MISSING-PATH", preflight.stdout)
            self.assertIn(stale_rel, preflight.stdout)

    def test_preflight_rejects_untracked_missing_deletion_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)
            deleted_rel = "docs/never_tracked.md"
            self._materialize_bundle(
                root,
                deleted_paths=[deleted_rel],
                materialize_deleted_paths=False,
                materialize_review=False,
            )

            preflight = self._run_bundle(root, "--preflight")

            self.assertNotEqual(preflight.returncode, 0)
            self.assertIn("MISSING-DELETION-TARGET", preflight.stdout)
            self.assertIn(deleted_rel, preflight.stdout)

    def test_preflight_and_lint_reject_existing_untracked_deletion_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)
            deleted_rel = "docs/untracked_delete.md"
            self._materialize_bundle(root, deleted_paths=[deleted_rel], materialize_review=False)

            preflight = self._run_bundle(root, "--preflight")
            lint_findings = self._exact_bundle_lint_findings(root)
            stage = self._run_bundle(root, "--stage")

            self.assertNotEqual(preflight.returncode, 0)
            self.assertIn("MISSING-DELETION-TARGET", preflight.stdout)
            self.assertIn(deleted_rel, preflight.stdout)
            self.assertTrue(
                any("untracked/missing deletion path" in finding.message for finding in lint_findings),
                [finding.message for finding in lint_findings],
            )
            self.assertTrue(any(deleted_rel in finding.message for finding in lint_findings))
            self.assertNotEqual(stage.returncode, 0)
            self.assertIn("MISSING-DELETION-TARGET", stage.stdout)

    def test_preflight_and_lint_reject_review_only_deletion_without_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)
            deleted_rel = "docs/review_only_delete.md"
            self._materialize_bundle(root, deleted_paths=[deleted_rel], materialize_review=False)
            self._commit_all(root, "baseline")
            (root / deleted_rel).unlink()
            self._rewrite_deleted_path_entries(root, [{"path": deleted_rel, "kind": "review_only"}])

            preflight = self._run_bundle(root, "--preflight")
            lint_findings = self._exact_bundle_lint_findings(root)

            self.assertNotEqual(preflight.returncode, 0)
            self.assertIn("MISSING-REVIEW-ONLY-DELETION-CONTRACT", preflight.stdout)
            self.assertTrue(
                any("review-only `code_draft_meta.deleted_paths`" in finding.message for finding in lint_findings),
                [finding.message for finding in lint_findings],
            )

    def test_preflight_and_lint_accept_review_only_deletion_with_base_and_deletion_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)
            deleted_rel = "docs/review_only_deleted_with_refs.md"
            self._materialize_bundle(root, deleted_paths=[deleted_rel], materialize_review=False)
            self._commit_all(root, "baseline")
            base_ref = self._git(root, "rev-parse", "HEAD").stdout.strip()
            (root / deleted_rel).unlink()
            self._git(root, "add", deleted_rel)
            self._git(root, "commit", "-m", "delete review-only target")
            deletion_ref = self._git(root, "rev-parse", "HEAD").stdout.strip()
            self._rewrite_deleted_path_entries(
                root,
                [
                    {
                        "path": deleted_rel,
                        "kind": "review_only",
                        "base_ref": base_ref,
                        "deletion_ref": deletion_ref,
                    }
                ],
            )

            preflight = self._run_bundle(root, "--preflight")
            lint_findings = self._exact_bundle_lint_findings(root)

            self.assertEqual(preflight.returncode, 0, preflight.stderr)
            self.assertIn(deleted_rel, preflight.stdout)
            self.assertEqual([finding.message for finding in lint_findings], [])

    def test_closeout_accepts_tracked_durable_review_receipt_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)
            receipt_rel = "docs/reviews/exact_bundle_receipt.json"
            review_text = self._same_file_review_text(status="✅ OK") + f"\nDurable receipt: `{receipt_rel}`\n"
            self._materialize_bundle(root, review_text=review_text)
            receipt_path = root / receipt_rel
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_path.write_text("{}\n", encoding="utf-8")
            self._commit_all(root, "baseline")

            payload = self._run_bundle_json(root)

            self.assertTrue(payload["bundle_ok"])
            self.assertEqual(payload["closeout_kind"], "already_materialized")
            repo_payload = payload["repo_roots"][0]
            self.assertIn(receipt_rel, repo_payload["bundle_paths"])
            self.assertEqual(repo_payload["path_problems"], {})

    def test_check_rejects_missing_durable_review_receipt_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)
            receipt_rel = "docs/reviews/missing_receipt.json"
            review_text = self._same_file_review_text(status="✅ OK") + f"\nDurable receipt: `{receipt_rel}`\n"
            self._materialize_bundle(root, review_text=review_text)

            result = self._run_bundle(root, "--check")
            commit_ready = self._run_bundle(root, "--commit-ready")
            payload = self._run_bundle_json(root)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("MISSING-PATH", result.stdout)
            self.assertIn(receipt_rel, result.stdout)
            self.assertIn("Operator action", result.stderr)
            self.assertNotEqual(commit_ready.returncode, 0)
            self.assertIn(receipt_rel, commit_ready.stdout)
            self.assertIn("Operator action", commit_ready.stderr)
            self.assertFalse(payload["bundle_ok"])
            self.assertEqual(payload["closeout_kind"], "needs_rerun")
            self.assertTrue(payload["rerun_recommended"])
            repo_payload = payload["repo_roots"][0]
            self.assertIn("missing-path", repo_payload["path_problems"][receipt_rel])

    def test_check_rejects_untracked_durable_review_receipt_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)
            receipt_rel = "docs/reviews/untracked_receipt.json"
            review_text = self._same_file_review_text(status="✅ OK") + f"\nDurable receipt: `{receipt_rel}`\n"
            self._materialize_bundle(root, review_text=review_text)
            self._commit_all(root, "baseline")
            receipt_path = root / receipt_rel
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_path.write_text("{}\n", encoding="utf-8")

            result = self._run_bundle(root, "--check")
            commit_ready = self._run_bundle(root, "--commit-ready")
            payload = self._run_bundle_json(root)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("UNTRACKED-DURABLE-RECEIPT", result.stdout)
            self.assertIn(receipt_rel, result.stdout)
            self.assertIn("Operator action", result.stderr)
            self.assertNotEqual(commit_ready.returncode, 0)
            self.assertIn("UNTRACKED-DURABLE-RECEIPT", commit_ready.stdout)
            self.assertIn(receipt_rel, commit_ready.stdout)
            self.assertIn("Operator action", commit_ready.stderr)
            self.assertFalse(payload["bundle_ok"])
            self.assertEqual(payload["closeout_kind"], "needs_rerun")
            self.assertTrue(payload["rerun_recommended"])
            repo_payload = payload["repo_roots"][0]
            self.assertIn("untracked-durable-receipt", repo_payload["path_problems"][receipt_rel])

    def test_check_allows_explicit_transient_review_receipt_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)
            receipt_rel = "docs/reviews/transient_receipt.json"
            review_text = (
                self._same_file_review_text(status="✅ OK")
                + "\n"
                f"Command output only; transient debug-only receipt, not checked in: `{receipt_rel}`\n"
            )
            self._materialize_bundle(root, review_text=review_text)

            result = self._run_bundle(root, "--check")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn(receipt_rel, result.stdout)

    def test_check_ignores_historical_review_receipt_reference_outside_exact_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)
            self._materialize_bundle(root)
            historical_path = root / "docs" / "notes" / "historical.md"
            historical_path.parent.mkdir(parents=True, exist_ok=True)
            historical_path.write_text(
                "Durable receipt: `docs/reviews/historical_receipt.json`\n",
                encoding="utf-8",
            )

            result = self._run_bundle(root, "--check")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("historical_receipt.json", result.stdout)

    def test_preflight_rejects_code_draft_meta_plan_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)
            self._materialize_bundle(root, materialize_review=False)
            decision = {
                "schema_version": "machine_authority_decision.v1",
                "applicability": "not_applicable",
                "reason_code": "no_machine_authority_change",
            }
            draft_payload = {
                "code_draft_meta": {
                    "plan": "docs/plans/wrong_plan.md",
                    "cluster": "process",
                    "targets": [{"path": PRIMARY_TARGET_REL, "kind": "py"}],
                    "machine_authority_decision_ref": {
                        "applicability": "not_applicable",
                        "reason_code": decision["reason_code"],
                        "carrier_sha256": PLAN_STATUS_ORACLE.machine_authority_decision_sha256(decision),
                    },
                }
            }
            (root / DRAFT_REL).write_text(
                f"# Code draft\n\n```json\n{json.dumps(draft_payload, indent=2)}\n```\n",
                encoding="utf-8",
            )

            preflight = self._run_bundle(root, "--preflight")

            self.assertNotEqual(preflight.returncode, 0)
            self.assertIn("machine_authority_decision_code_draft_ref_invalid", preflight.stderr)
            self.assertIn("code_draft_meta.plan does not match current plan", preflight.stderr)

    def test_closeout_json_reports_commit_ready_for_exact_staged_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)
            self._materialize_bundle(root)

            stage = self._run_bundle(root, "--stage")
            self.assertEqual(stage.returncode, 0, stage.stderr)

            payload = self._run_bundle_json(root)

            self.assertEqual(payload["closeout_kind"], "commit_ready")
            self.assertTrue(payload["commit_ready"])
            self.assertFalse(payload["already_materialized"])
            repo_payload = payload["repo_roots"][0]
            self.assertEqual(repo_payload["closeout_kind"], "commit_ready")
            self.assertIn(PRIMARY_TARGET_REL, repo_payload["staged_bundle_paths"])
            self.assertEqual(repo_payload["staged_extra_paths"], [])

    def test_closeout_preflight_reports_commit_ready_with_exact_safe_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)
            self._materialize_bundle(root)

            stage = self._run_bundle(root, "--stage")
            self.assertEqual(stage.returncode, 0, stage.stderr)

            payload = self._closeout_preflight_json(root)

            self.assertTrue(payload["semantic_ready"])
            self.assertEqual(payload["semantic_verdict"], "go")
            self.assertTrue(payload["bundle_ready"])
            self.assertTrue(payload["staged_exact"])
            self.assertTrue(payload["git_writable"])
            self.assertTrue(payload["commit_ready"])
            self.assertEqual(payload["closeout_state"], "commit_ready")
            self.assertEqual(payload["next_owner"], "Architect")
            self.assertEqual(payload["source_closeout_kind"], "commit_ready")
            self.assertIn("git -C", payload["safe_command"])
            self.assertIn(PRIMARY_TARGET_REL, payload["safe_command"])

    def test_closeout_json_reports_already_materialized_when_bundle_is_clean(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)
            self._materialize_bundle(root)
            self._commit_all(root, "baseline")

            payload = self._run_bundle_json(root)

            self.assertEqual(payload["closeout_kind"], "already_materialized")
            self.assertFalse(payload["commit_ready"])
            self.assertTrue(payload["already_materialized"])
            self.assertNotIn("final_docs_commit", payload)
            repo_payload = payload["repo_roots"][0]
            self.assertEqual(repo_payload["closeout_kind"], "already_materialized")
            self.assertEqual(repo_payload["staged_bundle_paths"], [])
            self.assertEqual(repo_payload["unstaged_bundle_paths"], [])
            self.assertEqual(repo_payload["untracked_bundle_paths"], [])

    def test_closeout_preflight_reports_already_materialized_without_safe_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)
            self._materialize_bundle(root)
            self._commit_all(root, "baseline")

            payload = self._closeout_preflight_json(root)

            self.assertTrue(payload["semantic_ready"])
            self.assertEqual(payload["semantic_verdict"], "go")
            self.assertTrue(payload["bundle_ready"])
            self.assertFalse(payload["staged_exact"])
            self.assertFalse(payload["commit_ready"])
            self.assertEqual(payload["closeout_state"], "already_materialized")
            self.assertEqual(payload["next_owner"], "Architect")
            self.assertIsNone(payload["safe_command"])

    def test_closeout_json_reports_staged_empty_for_unstaged_bundle_delta(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)
            self._materialize_bundle(root)
            self._commit_all(root, "baseline")

            (root / PRIMARY_TARGET_REL).write_text("echo changed\n", encoding="utf-8")

            payload = self._run_bundle_json(root)

            self.assertEqual(payload["closeout_kind"], "staged_empty")
            repo_payload = payload["repo_roots"][0]
            self.assertEqual(repo_payload["closeout_kind"], "staged_empty")
            self.assertIn(PRIMARY_TARGET_REL, repo_payload["unstaged_bundle_paths"])
            self.assertEqual(repo_payload["staged_bundle_paths"], [])

    def test_closeout_json_reports_staged_mismatch_for_unrelated_staged_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)
            self._materialize_bundle(root)

            stage = self._run_bundle(root, "--stage")
            self.assertEqual(stage.returncode, 0, stage.stderr)

            extra_rel = "notes/unrelated.txt"
            extra_path = root / extra_rel
            extra_path.parent.mkdir(parents=True, exist_ok=True)
            extra_path.write_text("extra\n", encoding="utf-8")
            self._git(root, "add", extra_rel)

            payload = self._run_bundle_json(root)

            self.assertEqual(payload["closeout_kind"], "staged_mismatch")
            repo_payload = payload["repo_roots"][0]
            self.assertEqual(repo_payload["closeout_kind"], "staged_mismatch")
            self.assertIn(extra_rel, repo_payload["staged_extra_paths"])

    def test_closeout_preflight_suppresses_safe_command_for_staged_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)
            self._materialize_bundle(root)

            stage = self._run_bundle(root, "--stage")
            self.assertEqual(stage.returncode, 0, stage.stderr)
            extra_rel = "notes/unrelated.txt"
            extra_path = root / extra_rel
            extra_path.parent.mkdir(parents=True, exist_ok=True)
            extra_path.write_text("extra\n", encoding="utf-8")
            self._git(root, "add", extra_rel)

            payload = self._closeout_preflight_json(root)

            self.assertTrue(payload["semantic_ready"])
            self.assertEqual(payload["source_closeout_kind"], "staged_mismatch")
            self.assertEqual(payload["closeout_state"], "staged_mismatch")
            self.assertFalse(payload["commit_ready"])
            self.assertIsNone(payload["safe_command"])

    def test_closeout_preflight_reports_git_metadata_blocker_without_safe_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)
            self._materialize_bundle(root)

            stage = self._run_bundle(root, "--stage")
            self.assertEqual(stage.returncode, 0, stage.stderr)
            lock_path = root / ".git" / "index.lock"
            lock_path.write_text("fixture lock\n", encoding="utf-8")

            try:
                payload = self._closeout_preflight_json(root)
            finally:
                lock_path.unlink(missing_ok=True)

            self.assertTrue(payload["semantic_ready"])
            self.assertTrue(payload["staged_exact"])
            self.assertFalse(payload["git_writable"])
            self.assertFalse(payload["commit_ready"])
            self.assertEqual(payload["closeout_state"], "closeout_blocked_git_metadata")
            self.assertEqual(payload["next_owner"], "Owner")
            self.assertIsNone(payload["safe_command"])
            self.assertEqual(payload["git_writable_probes"][0]["reason"], "index_lock_exists")

    def test_closeout_json_reports_needs_rerun_for_split_bundle_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)
            self._materialize_bundle(root)

            stage = self._run_bundle(root, "--stage")
            self.assertEqual(stage.returncode, 0, stage.stderr)

            (root / PRIMARY_TARGET_REL).write_text("echo rerun\n", encoding="utf-8")

            payload = self._run_bundle_json(root)

            self.assertEqual(payload["closeout_kind"], "needs_rerun")
            repo_payload = payload["repo_roots"][0]
            self.assertEqual(repo_payload["closeout_kind"], "needs_rerun")
            self.assertIn(PRIMARY_TARGET_REL, repo_payload["staged_bundle_paths"])
            self.assertIn(PRIMARY_TARGET_REL, repo_payload["unstaged_bundle_paths"])

    def test_closeout_json_blocks_live_review_artifact_without_canonical_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)
            review_text = textwrap.dedent(
                f"""\
                # Code review - missing status

                **Date:** 2026-05-07 03:00 MSK
                **Target:** PLAN={PLAN_REL}

                ## reviewer_code_risk - GPT-5.5 xhigh
                - Lane status: `complete`
                - Target snapshot: `PLAN={PLAN_REL}`

                ## reviewer_code_contracts - GPT-5.5 xhigh
                - Lane status: `complete`
                - Target snapshot: `PLAN={PLAN_REL}`
                """
            )
            self._materialize_bundle(root, review_text=review_text)
            self._commit_all(root, "baseline")

            check = self._run_bundle(root, "--check")
            preflight = self._run_bundle(root, "--preflight")
            commit_ready = self._run_bundle(root, "--commit-ready")
            payload = self._run_bundle_json(root)

            self.assertNotEqual(check.returncode, 0)
            self.assertNotEqual(preflight.returncode, 0)
            self.assertNotEqual(commit_ready.returncode, 0)
            self.assertIn("NEEDS-REVIEWER-RERUN", check.stdout)
            self.assertIn("NEEDS-REVIEWER-RERUN", preflight.stdout)
            self.assertIn("NEEDS-REVIEWER-RERUN", commit_ready.stdout)
            self.assertIn("missing canonical", "\n".join(payload["errors"]))
            self.assertFalse(payload["bundle_ok"])
            self.assertEqual(payload["closeout_kind"], "needs_rerun")
            self.assertTrue(payload["rerun_recommended"])
            repo_payload = payload["repo_roots"][0]
            self.assertIn("needs-reviewer-rerun", repo_payload["path_problems"][REVIEW_REL])

    def test_closeout_json_blocks_current_red_live_review_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)
            self._materialize_bundle(
                root,
                review_text=self._same_file_review_text(
                    status="❌ S1 blocker(ы)",
                    aggregate_status="❌ S1 blocker(ы)",
                    blocker_state="open",
                ),
            )
            self._commit_all(root, "baseline")

            check = self._run_bundle(root, "--check")
            preflight = self._run_bundle(root, "--preflight")
            commit_ready = self._run_bundle(root, "--commit-ready")
            payload = self._run_bundle_json(root)

            self.assertNotEqual(check.returncode, 0)
            self.assertNotEqual(preflight.returncode, 0)
            self.assertNotEqual(commit_ready.returncode, 0)
            self.assertIn("CURRENT-REVIEW-RED", check.stdout)
            self.assertIn("CURRENT-REVIEW-RED", preflight.stdout)
            self.assertIn("CURRENT-REVIEW-RED", commit_ready.stdout)
            self.assertFalse(payload["bundle_ok"])
            self.assertEqual(payload["closeout_kind"], "needs_rerun")
            self.assertTrue(payload["rerun_recommended"])
            repo_payload = payload["repo_roots"][0]
            self.assertIn("current-review-red", repo_payload["path_problems"][REVIEW_REL])

    def test_closeout_preflight_keeps_current_red_review_as_semantic_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)
            self._materialize_bundle(
                root,
                review_text=self._same_file_review_text(
                    status="❌ S1 blocker(ы)",
                    aggregate_status="❌ S1 blocker(ы)",
                    blocker_state="open",
                ),
            )
            self._commit_all(root, "baseline")

            payload = self._closeout_preflight_json(root)

            self.assertFalse(payload["semantic_ready"])
            self.assertEqual(payload["semantic_verdict"], "blocked")
            self.assertFalse(payload["bundle_ready"])
            self.assertFalse(payload["commit_ready"])
            self.assertEqual(payload["closeout_state"], "needs_rerun")
            self.assertEqual(payload["next_owner"], "Coder")
            self.assertIsNone(payload["safe_command"])
            self.assertEqual(payload["source_closeout_kind"], "needs_rerun")

    def test_closeout_json_routes_stale_red_after_fix_to_reviewer_same_file_rewrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)
            self._materialize_bundle(root, materialize_review=False)
            target = f"PLAN={PLAN_REL}"
            self._inject_plan_review_notes(root, self._stale_red_after_fix_plan_notes(target_snapshot=target))
            (root / REVIEW_REL).write_text(
                self._same_file_review_text(
                    target_snapshot=target,
                    status="❌ S1 blocker(ы)",
                    aggregate_status="❌ S1 blocker(ы)",
                    blocker_state="open",
                ),
                encoding="utf-8",
            )
            self._commit_all(root, "baseline")

            check = self._run_bundle(root, "--check")
            preflight = self._run_bundle(root, "--preflight")
            commit_ready = self._run_bundle(root, "--commit-ready")
            payload = self._run_bundle_json(root)

            self.assertNotEqual(check.returncode, 0)
            self.assertNotEqual(preflight.returncode, 0)
            self.assertNotEqual(commit_ready.returncode, 0)
            self.assertIn("REVIEWER-SAME-FILE-REWRITE-REQUIRED", check.stdout)
            self.assertIn("REVIEWER-SAME-FILE-REWRITE-REQUIRED", preflight.stdout)
            self.assertIn("REVIEWER-SAME-FILE-REWRITE-REQUIRED", commit_ready.stdout)
            self.assertFalse(payload["bundle_ok"])
            self.assertFalse(payload["commit_ready"])
            self.assertEqual(payload["closeout_kind"], "needs_rerun")
            self.assertTrue(payload["rerun_recommended"])
            repo_payload = payload["repo_roots"][0]
            self.assertIn("reviewer-same-file-rewrite-required", repo_payload["path_problems"][REVIEW_REL])

    def test_closeout_json_keeps_newer_contracts_blocker_current_red(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)
            self._materialize_bundle(root, materialize_review=False)
            target = f"PLAN={PLAN_REL}"
            self._inject_plan_review_notes(
                root,
                self._stale_red_after_fix_plan_notes(
                    target_snapshot=target,
                    stale_note_time="2026-05-07 03:08",
                    rerun_note_time="2026-05-07 03:09",
                ),
            )
            (root / REVIEW_REL).write_text(
                self._same_file_review_text(
                    target_snapshot=target,
                    status="❌ S1 blocker(ы)",
                    aggregate_status="❌ S1 blocker(ы)",
                    blocker_state="open",
                    date="2026-05-07 03:07 MSK",
                ),
                encoding="utf-8",
            )
            self._commit_all(root, "baseline")

            check = self._run_bundle(root, "--check")
            preflight = self._run_bundle(root, "--preflight")
            commit_ready = self._run_bundle(root, "--commit-ready")
            payload = self._run_bundle_json(root)

            self.assertNotEqual(check.returncode, 0)
            self.assertNotEqual(preflight.returncode, 0)
            self.assertNotEqual(commit_ready.returncode, 0)
            self.assertIn("CURRENT-REVIEW-RED", check.stdout)
            self.assertIn("CURRENT-REVIEW-RED", preflight.stdout)
            self.assertIn("CURRENT-REVIEW-RED", commit_ready.stdout)
            self.assertNotIn("REVIEWER-SAME-FILE-REWRITE-REQUIRED", check.stdout)
            self.assertFalse(payload["bundle_ok"])
            self.assertFalse(payload["commit_ready"])
            self.assertEqual(payload["closeout_kind"], "needs_rerun")
            self.assertTrue(payload["rerun_recommended"])
            repo_payload = payload["repo_roots"][0]
            path_problems = repo_payload["path_problems"][REVIEW_REL]
            self.assertIn("current-review-red", path_problems)
            self.assertNotIn("reviewer-same-file-rewrite-required", path_problems)
            self.assertIn("newer than the selected fixed risk-lane evidence", "\n".join(payload["errors"]))

    def test_closeout_json_keeps_same_minute_contracts_blocker_current_red(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)
            self._materialize_bundle(root, materialize_review=False)
            target = f"PLAN={PLAN_REL}"
            self._inject_plan_review_notes(
                root,
                self._stale_red_after_fix_plan_notes(
                    target_snapshot=target,
                    stale_note_time="2026-05-07 03:08",
                    rerun_note_time="2026-05-07 03:09",
                    run_id="reviewer_code_risk:bundle:20260507T030644",
                ),
            )
            (root / REVIEW_REL).write_text(
                self._same_file_review_text(
                    target_snapshot=target,
                    status="❌ S1 blocker(ы)",
                    aggregate_status="❌ S1 blocker(ы)",
                    blocker_state="open",
                    date="2026-05-07 03:06 MSK",
                ),
                encoding="utf-8",
            )
            self._commit_all(root, "baseline")

            check = self._run_bundle(root, "--check")
            preflight = self._run_bundle(root, "--preflight")
            payload = self._run_bundle_json(root)

            self.assertNotEqual(check.returncode, 0)
            self.assertNotEqual(preflight.returncode, 0)
            self.assertIn("CURRENT-REVIEW-RED", check.stdout)
            self.assertIn("CURRENT-REVIEW-RED", preflight.stdout)
            self.assertNotIn("REVIEWER-SAME-FILE-REWRITE-REQUIRED", check.stdout)
            self.assertFalse(payload["bundle_ok"])
            repo_payload = payload["repo_roots"][0]
            path_problems = repo_payload["path_problems"][REVIEW_REL]
            self.assertIn("current-review-red", path_problems)
            self.assertNotIn("reviewer-same-file-rewrite-required", path_problems)
            self.assertIn("same-minute freshness ordering", "\n".join(payload["errors"]))

    def test_closeout_preflight_routes_newer_contracts_blocker_to_coder(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)
            self._materialize_bundle(root, materialize_review=False)
            target = f"PLAN={PLAN_REL}"
            self._inject_plan_review_notes(
                root,
                self._stale_red_after_fix_plan_notes(
                    target_snapshot=target,
                    stale_note_time="2026-05-07 03:08",
                    rerun_note_time="2026-05-07 03:09",
                ),
            )
            (root / REVIEW_REL).write_text(
                self._same_file_review_text(
                    target_snapshot=target,
                    status="❌ S1 blocker(ы)",
                    aggregate_status="❌ S1 blocker(ы)",
                    blocker_state="open",
                    date="2026-05-07 03:07 MSK",
                ),
                encoding="utf-8",
            )
            self._commit_all(root, "baseline")

            payload = self._closeout_preflight_json(root)

            self.assertFalse(payload["semantic_ready"])
            self.assertEqual(payload["semantic_verdict"], "blocked")
            self.assertFalse(payload["bundle_ready"])
            self.assertFalse(payload["commit_ready"])
            self.assertEqual(payload["closeout_state"], "needs_rerun")
            self.assertEqual(payload["next_owner"], "Coder")
            self.assertIsNone(payload["safe_command"])
            self.assertEqual(payload["source_closeout_kind"], "needs_rerun")

    def test_closeout_preflight_routes_same_minute_contracts_blocker_to_coder(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)
            self._materialize_bundle(root, materialize_review=False)
            target = f"PLAN={PLAN_REL}"
            self._inject_plan_review_notes(
                root,
                self._stale_red_after_fix_plan_notes(
                    target_snapshot=target,
                    stale_note_time="2026-05-07 03:08",
                    rerun_note_time="2026-05-07 03:09",
                    run_id="reviewer_code_risk:bundle:20260507T030644",
                ),
            )
            (root / REVIEW_REL).write_text(
                self._same_file_review_text(
                    target_snapshot=target,
                    status="❌ S1 blocker(ы)",
                    aggregate_status="❌ S1 blocker(ы)",
                    blocker_state="open",
                    date="2026-05-07 03:06 MSK",
                ),
                encoding="utf-8",
            )
            self._commit_all(root, "baseline")

            payload = self._closeout_preflight_json(root)

            self.assertFalse(payload["semantic_ready"])
            self.assertEqual(payload["semantic_verdict"], "blocked")
            self.assertFalse(payload["bundle_ready"])
            self.assertFalse(payload["commit_ready"])
            self.assertEqual(payload["closeout_state"], "needs_rerun")
            self.assertEqual(payload["next_owner"], "Coder")
            self.assertIsNone(payload["safe_command"])
            self.assertEqual(payload["source_closeout_kind"], "needs_rerun")

    def test_closeout_preflight_routes_stale_red_after_fix_to_reviewer_without_commit_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)
            self._materialize_bundle(root, materialize_review=False)
            target = f"PLAN={PLAN_REL}"
            self._inject_plan_review_notes(root, self._stale_red_after_fix_plan_notes(target_snapshot=target))
            (root / REVIEW_REL).write_text(
                self._same_file_review_text(
                    target_snapshot=target,
                    status="❌ S1 blocker(ы)",
                    aggregate_status="❌ S1 blocker(ы)",
                    blocker_state="open",
                ),
                encoding="utf-8",
            )
            self._commit_all(root, "baseline")

            payload = self._closeout_preflight_json(root)

            self.assertFalse(payload["semantic_ready"])
            self.assertEqual(payload["semantic_verdict"], "blocked")
            self.assertFalse(payload["bundle_ready"])
            self.assertFalse(payload["commit_ready"])
            self.assertEqual(payload["closeout_state"], "needs_rerun")
            self.assertEqual(payload["next_owner"], "Reviewer")
            self.assertIsNone(payload["safe_command"])
            self.assertEqual(payload["source_closeout_kind"], "needs_rerun")

    def test_closeout_json_fail_closes_stale_red_when_risk_lane_status_not_successful(self) -> None:
        cases = ("blocked", "incomplete", "unknown", None)
        for lane_status in cases:
            with self.subTest(lane_status=lane_status), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                self._init_repo(root)
                self._materialize_bundle(root, materialize_review=False)
                target = f"PLAN={PLAN_REL}"
                self._inject_plan_review_notes(
                    root,
                    self._stale_red_after_fix_plan_notes(target_snapshot=target, lane_status=lane_status),
                )
                (root / REVIEW_REL).write_text(
                    self._same_file_review_text(
                        target_snapshot=target,
                        status="❌ S1 blocker(ы)",
                        aggregate_status="❌ S1 blocker(ы)",
                        blocker_state="open",
                    ),
                    encoding="utf-8",
                )
                self._commit_all(root, "baseline")

                payload = self._run_bundle_json(root)

                self.assertFalse(payload["bundle_ok"])
                self.assertFalse(payload["commit_ready"])
                self.assertEqual(payload["closeout_kind"], "needs_rerun")
                self.assertTrue(payload["rerun_recommended"])
                repo_payload = payload["repo_roots"][0]
                path_problems = repo_payload["path_problems"][REVIEW_REL]
                self.assertIn("current-review-red", path_problems)
                self.assertNotIn("reviewer-same-file-rewrite-required", path_problems)
                self.assertIn("lane_status", "\n".join(payload["errors"]))

    def test_closeout_json_blocks_active_quarantine_without_rerun_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)
            plan_notes = textwrap.dedent(
                f"""\
                - Stale note (2026-05-07 03:00): same review file `{REVIEW_REL}` remains red until rerun
                - Rerun note (2026-05-07 03:05): same review file `{REVIEW_REL}` will be rewritten in place
                """
            )
            self._materialize_bundle(
                root,
                review_text=self._same_file_review_text(status="✅ OK"),
                plan_review_notes=plan_notes,
            )
            self._commit_all(root, "baseline")

            check = self._run_bundle(root, "--check")
            preflight = self._run_bundle(root, "--preflight")
            commit_ready = self._run_bundle(root, "--commit-ready")
            payload = self._run_bundle_json(root)

            self.assertNotEqual(check.returncode, 0)
            self.assertNotEqual(preflight.returncode, 0)
            self.assertNotEqual(commit_ready.returncode, 0)
            self.assertIn("NEEDS-REVIEWER-RERUN", check.stdout)
            self.assertIn("NEEDS-REVIEWER-RERUN", preflight.stdout)
            self.assertIn("NEEDS-REVIEWER-RERUN", commit_ready.stdout)
            self.assertFalse(payload["bundle_ok"])
            self.assertEqual(payload["closeout_kind"], "needs_rerun")
            self.assertTrue(payload["rerun_recommended"])
            repo_payload = payload["repo_roots"][0]
            self.assertIn("needs-reviewer-rerun", repo_payload["path_problems"][REVIEW_REL])

    def test_closeout_json_allows_current_green_clean_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)
            self._materialize_bundle(root, review_text=self._same_file_review_text(status="✅ OK"))
            self._commit_all(root, "baseline")

            check = self._run_bundle(root, "--check")
            preflight = self._run_bundle(root, "--preflight")
            commit_ready = self._run_bundle(root, "--commit-ready")
            payload = self._run_bundle_json(root)

            self.assertEqual(check.returncode, 0, check.stderr)
            self.assertEqual(preflight.returncode, 0, preflight.stderr)
            self.assertEqual(commit_ready.returncode, 0, commit_ready.stderr)
            self.assertTrue(payload["bundle_ok"])
            self.assertEqual(payload["closeout_kind"], "already_materialized")
            self.assertTrue(payload["already_materialized"])
            self.assertFalse(payload["rerun_recommended"])

    def test_closeout_json_allows_historical_reconciliation_with_rerun_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)
            plan_notes = textwrap.dedent(
                f"""\
                - Stale note (2026-05-07 03:00): same review file `{REVIEW_REL}` remains red until rerun
                - Rerun note (2026-05-07 03:05): same review file `{REVIEW_REL}` will be rewritten in place
                - Rerun result (2026-05-07 03:10): same review file `{REVIEW_REL}` was rewritten in place
                """
            )
            self._materialize_bundle(
                root,
                review_text=self._same_file_review_text(
                    status="✅ OK",
                    marker="same review file rewritten in place after same-contract rerun",
                ),
                plan_review_notes=plan_notes,
            )
            self._commit_all(root, "baseline")

            check = self._run_bundle(root, "--check")
            preflight = self._run_bundle(root, "--preflight")
            commit_ready = self._run_bundle(root, "--commit-ready")
            payload = self._run_bundle_json(root)

            self.assertEqual(check.returncode, 0, check.stderr)
            self.assertEqual(preflight.returncode, 0, preflight.stderr)
            self.assertEqual(commit_ready.returncode, 0, commit_ready.stderr)
            self.assertTrue(payload["bundle_ok"])
            self.assertEqual(payload["closeout_kind"], "already_materialized")
            self.assertFalse(payload["rerun_recommended"])

    def test_check_preserves_literal_backtick_target_identity(self) -> None:
        # B2: a target whose literal basename ends in a backtick must be looked
        # up verbatim through the strip=False metadata lane. Markdown backtick
        # cleanup belongs only to the strip=True prose lane, so the trailing
        # backtick is part of the path identity and is not stripped before lookup.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)
            literal_rel = "scripts/literal-backtick`"
            literal_fs = root / literal_rel
            literal_fs.parent.mkdir(parents=True, exist_ok=True)
            literal_fs.write_text("literal\n", encoding="utf-8")
            self._materialize_bundle(root, extra_targets=[literal_rel])
            self._commit_all(root, "baseline")

            check = self._run_bundle(root, "--check")
            preflight = self._run_bundle(root, "--preflight")
            payload = self._run_bundle_json(root)

            self.assertEqual(check.returncode, 0, check.stderr + check.stdout)
            self.assertEqual(preflight.returncode, 0, preflight.stderr + preflight.stdout)
            self.assertNotIn("MISSING-PATH", check.stdout)
            self.assertTrue(payload["bundle_ok"])
            repo_payload = payload["repo_roots"][0]
            self.assertNotIn(literal_rel, repo_payload["path_problems"])

    def test_check_preserves_literal_backtick_deleted_path_identity(self) -> None:
        # B2: a deleted_path whose literal basename ends in a backtick must be
        # resolved verbatim (strip=False) so the represented deletion confirms it
        # is tracked at HEAD under its true identity, not a backtick-stripped alias.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)
            literal_rel = "docs/obsolete-ledger`"
            self._materialize_bundle(root, deleted_paths=[literal_rel])
            self._commit_all(root, "baseline")

            check = self._run_bundle(root, "--check")
            preflight = self._run_bundle(root, "--preflight")
            payload = self._run_bundle_json(root)

            self.assertEqual(check.returncode, 0, check.stderr + check.stdout)
            self.assertEqual(preflight.returncode, 0, preflight.stderr + preflight.stdout)
            self.assertNotIn("MISSING-DELETION-TARGET", check.stdout)
            self.assertTrue(payload["bundle_ok"])

    def test_check_does_not_false_green_on_trimmed_backtick_alias(self) -> None:
        # B2 negative control: the trimmed alias (trailing backtick stripped)
        # sitting on disk must NOT satisfy a declared literal-backtick target.
        # With the fix, strip=False preserves the trailing backtick, so the
        # verbatim lookup misses the trimmed alias and --check fails closed
        # instead of false-greening via markdown backtick cleanup.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._init_repo(root)
            literal_rel = "scripts/literal-backtick`"
            trimmed_fs = root / "scripts/literal-backtick"
            trimmed_fs.parent.mkdir(parents=True, exist_ok=True)
            trimmed_fs.write_text("trimmed alias\n", encoding="utf-8")
            self._materialize_bundle(root, extra_targets=[literal_rel])
            self._commit_all(root, "baseline")

            check = self._run_bundle(root, "--check")
            payload = self._run_bundle_json(root)

            self.assertNotEqual(check.returncode, 0)
            self.assertIn("MISSING-PATH", check.stdout)
            self.assertIn(literal_rel, check.stdout)
            self.assertFalse(payload["bundle_ok"])
            repo_payload = payload["repo_roots"][0]
            self.assertIn("missing-path", repo_payload["path_problems"][literal_rel])

    def test_exact_stage_and_bundle_readers_treat_wildcard_paths_literally(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            asset_rel = "docs/[a].txt"
            foreign_rel = "docs/a.txt"
            self._materialize_bundle(root, extra_targets=[asset_rel])
            for relative in (asset_rel, foreign_rel):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("literal fixture bytes\n", encoding="utf-8")
            before = self._run_bundle_json(root)
            self.assertIn(asset_rel, before["repo_roots"][0]["bundle_paths"])
            self.assertNotIn(foreign_rel, before["repo_roots"][0]["bundle_paths"])
            stage = self._run_bundle(root, "--stage")
            self.assertEqual(stage.returncode, 0, stage.stdout + stage.stderr)
            staged = self._git(root, "diff", "--cached", "--name-only").stdout.splitlines()
            self.assertIn(asset_rel, staged)
            self.assertNotIn(foreign_rel, staged)
            payload = self._run_bundle_json(root)
            repository = payload["repo_roots"][0]
            self.assertTrue(payload["bundle_ok"], payload["errors"])
            self.assertEqual(repository["staged_extra_paths"], [])
            self.assertNotIn(foreign_rel, repository["unstaged_bundle_paths"])
            self.assertNotIn(foreign_rel, repository["untracked_bundle_paths"])
            self.assertEqual(payload["closeout_kind"], "commit_ready")

    def test_all_history_risk_support_assets_join_explicit_review_assets_and_stage_exactly(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            explicit_asset_rel = "docs/code_reviews/assets/other/explicit-review-asset.json"
            self._materialize_bundle(
                root,
                review_text=(
                    self._same_file_review_text(status="✅ OK")
                    + f"\nEvidence asset: `{explicit_asset_rel}`\n"
                ),
            )
            self._commit_all(root, "baseline")

            current_rel = "docs/code_reviews/assets/risk/current.json"
            historical_rel = "docs/code_reviews/assets/risk/historical-red.txt"
            current_path = root / current_rel
            historical_path = root / historical_rel
            explicit_path = root / explicit_asset_rel
            for path, data in (
                (current_path, b'{"current":true}\n'),
                (historical_path, b"legacy red bytes; deliberately not JSON\n"),
                (explicit_path, b'{"explicit":true}\n'),
            ):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            current_sha = hashlib.sha256(current_path.read_bytes()).hexdigest()
            historical_sha = hashlib.sha256(historical_path.read_bytes()).hexdigest()
            plan_path = root / PLAN_REL
            plan_path.write_text(
                plan_path.read_text(encoding="utf-8")
                + "\n## Evidence\n\n"
                + "```json\n"
                + json.dumps(
                    {
                        "lane_id": "reviewer_code_risk",
                        "run_id": "current",
                        "current": True,
                        "target_snapshot": f"PLAN={PLAN_REL}",
                        "full_payload_ref": current_rel,
                        "full_payload_sha256": current_sha,
                    },
                    sort_keys=True,
                )
                + "\n```\n\n```json\n"
                + json.dumps(
                    {
                        "lane_id": "reviewer_code_risk",
                        "run_id": "historical",
                        "current": False,
                        "full_payload_ref": historical_rel,
                        "full_payload_sha256": historical_sha,
                    },
                    sort_keys=True,
                )
                + "\n```\n",
                encoding="utf-8",
            )

            payload = self._run_bundle_json(root)
            self.assertTrue(payload["bundle_ok"], payload["errors"])
            repo_payload = payload["repo_roots"][0]
            self.assertEqual(
                set((current_rel, historical_rel, explicit_asset_rel)),
                set((current_rel, historical_rel, explicit_asset_rel))
                & set(repo_payload["bundle_paths"]),
            )
            self.assertEqual(
                set((current_rel, historical_rel, explicit_asset_rel)),
                set((current_rel, historical_rel, explicit_asset_rel))
                & set(repo_payload["untracked_bundle_paths"]),
            )

            stage = self._run_bundle(root, "--stage")

            self.assertEqual(stage.returncode, 0, stage.stdout + stage.stderr)
            staged = set(self._git(root, "diff", "--cached", "--name-only").stdout.splitlines())
            self.assertTrue({current_rel, historical_rel, explicit_asset_rel}.issubset(staged))

    def test_invalid_all_history_risk_support_blocks_mutation_and_reports_closeout_needs_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._materialize_bundle(root)
            self._commit_all(root, "baseline")
            plan_path = root / PLAN_REL
            plan_path.write_text(
                plan_path.read_text(encoding="utf-8")
                + "\n## Evidence\n\n```json\n"
                + json.dumps(
                    {
                        "lane_id": "reviewer_code_risk",
                        "run_id": "historical-incomplete",
                        "current": False,
                        "full_payload_ref": "docs/code_reviews/assets/risk/missing.json",
                    },
                    sort_keys=True,
                )
                + "\n```\n",
                encoding="utf-8",
            )
            index_before = self._git(root, "write-tree").stdout.strip()
            head_before = self._git(root, "rev-parse", "HEAD").stdout.strip()
            dummy_payload = self._write_json(root, "docs-closeout.json", {})
            dummy_preflight = self._write_json(root, "preflight.json", {})
            message = root / "message.txt"
            message.write_text("must not reach delegation\n", encoding="utf-8")

            commands = (
                f"planveyor_plan_bundle --stage {PLAN_REL}",
                f"planveyor_plan_bundle --commit-ready {PLAN_REL}",
                "planveyor_plan_bundle --commit-exact "
                f"--preflight-json {shlex.quote(str(dummy_preflight))} "
                f"--message-file {shlex.quote(str(message))} {PLAN_REL}",
                "planveyor_plan_bundle --stage "
                f"--docs-closeout-json {shlex.quote(str(dummy_payload))} {PLAN_REL}",
                "planveyor_plan_bundle --commit-ready "
                f"--docs-closeout-json {shlex.quote(str(dummy_payload))} {PLAN_REL}",
            )
            for command in commands:
                with self.subTest(command=command):
                    result = self._run_shell(root, command)
                    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                    self.assertIn("missing_risk_lane_support_payload_hash", result.stderr)
                    self.assertEqual(self._git(root, "write-tree").stdout.strip(), index_before)
                    self.assertEqual(self._git(root, "rev-parse", "HEAD").stdout.strip(), head_before)

            preflight = self._run_bundle(root, "--preflight")
            self.assertNotEqual(preflight.returncode, 0, preflight.stdout + preflight.stderr)
            self.assertIn("missing_risk_lane_support_payload_hash", preflight.stdout + preflight.stderr)
            self.assertEqual(self._git(root, "write-tree").stdout.strip(), index_before)
            self.assertEqual(self._git(root, "rev-parse", "HEAD").stdout.strip(), head_before)

            closeout = self._run_bundle_json(root)

            self.assertFalse(closeout["bundle_ok"])
            self.assertEqual(closeout["closeout_kind"], "needs_rerun")
            self.assertFalse(closeout["already_materialized"])
            self.assertTrue(
                any("missing_risk_lane_support_payload_hash" in error for error in closeout["errors"]),
                closeout["errors"],
            )
            self.assertEqual(self._git(root, "write-tree").stdout.strip(), index_before)
            self.assertEqual(self._git(root, "rev-parse", "HEAD").stdout.strip(), head_before)

    def test_current_proof_block_gates_every_bundle_mutation_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._materialize_bundle(root)
            self._commit_all(root, "baseline")
            (root / REVIEW_REL).write_text(
                self._same_file_review_text(
                    status="✅ OK",
                    target_snapshot=f"BUNDLE=current bundle_sha256={'a' * 64}",
                ),
                encoding="utf-8",
            )
            index_before = self._git(root, "write-tree").stdout.strip()
            head_before = self._git(root, "rev-parse", "HEAD").stdout.strip()
            dummy_payload = self._write_json(root, "docs-closeout.json", {})
            dummy_preflight = self._write_json(root, "preflight.json", {})
            message = root / "message.txt"
            message.write_text("must not reach canonical bundle mutation\n", encoding="utf-8")

            commands = (
                f"planveyor_plan_bundle --stage {PLAN_REL}",
                f"planveyor_plan_bundle --commit-ready {PLAN_REL}",
                "planveyor_plan_bundle --commit-exact "
                f"--preflight-json {shlex.quote(str(dummy_preflight))} "
                f"--message-file {shlex.quote(str(message))} {PLAN_REL}",
                "planveyor_plan_bundle --stage "
                f"--docs-closeout-json {shlex.quote(str(dummy_payload))} {PLAN_REL}",
            )
            for command in commands:
                with self.subTest(command=command):
                    result = self._run_shell(root, command)
                    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                    self.assertIn("missing_plan_resident_risk_lane", result.stdout + result.stderr)
                    self.assertEqual(self._git(root, "write-tree").stdout.strip(), index_before)
                    self.assertEqual(self._git(root, "rev-parse", "HEAD").stdout.strip(), head_before)

            preflight = self._run_bundle(root, "--preflight")
            self.assertNotEqual(preflight.returncode, 0, preflight.stdout + preflight.stderr)
            self.assertIn("missing_plan_resident_risk_lane", preflight.stdout + preflight.stderr)
            closeout = self._run_bundle_json(root)
            self.assertFalse(closeout["bundle_ok"])
            self.assertEqual(closeout["closeout_kind"], "needs_rerun")
            self.assertTrue(
                any("missing_plan_resident_risk_lane" in error for error in closeout["errors"]),
                closeout["errors"],
            )
            self.assertEqual(self._git(root, "write-tree").stdout.strip(), index_before)
            self.assertEqual(self._git(root, "rev-parse", "HEAD").stdout.strip(), head_before)

    def test_symlinked_risk_support_ref_blocks_stage_without_losing_declared_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._materialize_bundle(root)
            target_rel = "docs/code_reviews/assets/risk/regular-target.json"
            target_path = root / target_rel
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(b'{"historical":true}\n')
            self._commit_all(root, "baseline")

            declared_rel = "docs/code_reviews/assets/risk/declared-link.json"
            declared_path = root / declared_rel
            declared_path.symlink_to(target_path)
            plan_path = root / PLAN_REL
            plan_path.write_text(
                plan_path.read_text(encoding="utf-8")
                + "\n## Evidence\n\n```json\n"
                + json.dumps(
                    {
                        "lane_id": "reviewer_code_risk",
                        "run_id": "historical-symlink",
                        "current": False,
                        "full_payload_ref": declared_rel,
                        "full_payload_sha256": hashlib.sha256(target_path.read_bytes()).hexdigest(),
                    },
                    sort_keys=True,
                )
                + "\n```\n",
                encoding="utf-8",
            )
            index_before = self._git(root, "write-tree").stdout.strip()
            head_before = self._git(root, "rev-parse", "HEAD").stdout.strip()

            stage = self._run_bundle(root, "--stage")
            closeout = self._run_bundle_json(root)

            self.assertEqual(stage.returncode, 2, stage.stdout + stage.stderr)
            self.assertIn("invalid_risk_lane_support_payload_ref", stage.stderr)
            self.assertEqual(self._git(root, "write-tree").stdout.strip(), index_before)
            self.assertEqual(self._git(root, "rev-parse", "HEAD").stdout.strip(), head_before)
            self.assertEqual(self._git(root, "diff", "--cached", "--name-only").stdout, "")
            self.assertFalse(closeout["bundle_ok"])
            self.assertEqual(closeout["closeout_kind"], "needs_rerun")
            self.assertTrue(
                any("invalid_risk_lane_support_payload_ref" in error for error in closeout["errors"]),
                closeout["errors"],
            )

    def test_synthetic_risk_support_corpus_replay_is_read_only_and_has_expected_membership(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            support_bytes = {
                "docs/risk_support/alpha.json": b'{"finding":"alpha"}\n',
                "docs/risk_support/beta.json": b'{"finding":"beta"}\n',
                "docs/risk_support/gamma.json": b'{"finding":"gamma"}\n',
            }
            support_hashes = {
                rel: hashlib.sha256(data).hexdigest()
                for rel, data in support_bytes.items()
            }
            for rel, data in support_bytes.items():
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)

            def risk_payload(rel: str, sha256: str) -> dict[str, str]:
                return {
                    "lane_id": "reviewer_code_risk",
                    "full_payload_ref": rel,
                    "full_payload_sha256": sha256,
                }

            corpus = {
                "valid": (
                    [
                        risk_payload(
                            "docs/risk_support/alpha.json",
                            support_hashes["docs/risk_support/alpha.json"],
                        ),
                        risk_payload(
                            "docs/risk_support/beta.json",
                            support_hashes["docs/risk_support/beta.json"],
                        ),
                        risk_payload(
                            "docs/risk_support/alpha.json",
                            support_hashes["docs/risk_support/alpha.json"],
                        ),
                        {
                            "lane_id": "reviewer_code_contracts",
                            "full_payload_ref": "docs/risk_support/ignored.json",
                            "full_payload_sha256": "0" * 64,
                        },
                        risk_payload(
                            "docs/risk_support/gamma.json",
                            support_hashes["docs/risk_support/gamma.json"],
                        ),
                    ],
                    (
                        ("docs/risk_support/alpha.json", support_hashes["docs/risk_support/alpha.json"]),
                        ("docs/risk_support/beta.json", support_hashes["docs/risk_support/beta.json"]),
                        ("docs/risk_support/gamma.json", support_hashes["docs/risk_support/gamma.json"]),
                    ),
                    (),
                ),
                "missing": (
                    [
                        risk_payload("docs/risk_support/missing-alpha.json", "a" * 64),
                        risk_payload("docs/risk_support/missing-beta.json", "b" * 64),
                    ],
                    (),
                    (
                        "missing_risk_lane_support_payload_file",
                        "missing_risk_lane_support_payload_file",
                    ),
                ),
            }
            for case, (payloads, expected_records, expected_diagnostics) in corpus.items():
                with self.subTest(case=case):
                    plan_path = root / f"docs/plans/risk_support_{case}_fixture.md"
                    plan_path.parent.mkdir(parents=True, exist_ok=True)
                    plan_path.write_text(
                        "# Plan: risk-support fixture\n\n"
                        + "\n\n".join(
                            f"```json\n{json.dumps(payload, sort_keys=True)}\n```"
                            for payload in payloads
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                    before = plan_path.read_bytes()
                    manifest = PLAN_LINT.collect_plan_risk_lane_support_refs(
                        plan_path,
                        project_root=root,
                    )
                    self.assertEqual(manifest.records, expected_records)
                    self.assertEqual(
                        tuple(diagnostic.code for diagnostic in manifest.diagnostics),
                        expected_diagnostics,
                    )
                    self.assertEqual(plan_path.read_bytes(), before)

    def test_explicit_visual_v2_ref_adds_only_its_single_support_asset(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._materialize_bundle(root)
            payload = {
                "schema_version": REVIEW_VISUAL_LANE_CONTRACT.SCHEMA_VERSION,
                "availability_state": "not_applicable",
                "runtime_ui_kind": "none",
                "profile_id": "default",
                "source_refs": [],
                "changed_path_evidence": [
                    {
                        "status": "M",
                        "path": f"scripts/generated_{index:04d}.py",
                        "old_path": "",
                        "runtime_ui": False,
                        "runtime_ui_paths": [],
                    }
                    for index in range(940)
                ],
                "mandatory_modes": [],
                "comparator_command": "",
                "comparator_claim": "mechanical",
                "baseline_update_allowed": False,
                "human_commands_by_mode": {},
                "human_index_paths_by_mode": {},
                "human_output_roots_by_mode": {},
                "complete_index_required": True,
                "durable_review_asset_root": "docs/code_reviews/assets/260324_0009_process_exact_bundle_commit_guard_for_dirty_index/",
                "reason": "no_runtime_ui_paths",
            }
            materialization = REVIEW_VISUAL_LANE_CONTRACT.prepare_materialized_contract(
                payload,
                base="a" * 40,
                head="b" * 40,
                exclude_docs=0,
                plan_ref=PLAN_REL,
                review_artifact_ref=REVIEW_REL,
            )
            self.assertEqual(materialization["mode"], "external")
            plan_path = root / PLAN_REL
            draft_path = root / DRAFT_REL
            plan_text = plan_path.read_text(encoding="utf-8") + (
                "\n## Review visual lane contract\n\n" + str(materialization["markdown"]) + "\n"
            )
            draft_text = draft_path.read_text(encoding="utf-8") + (
                "\n## Review visual lane contract\n\n" + str(materialization["markdown"]) + "\n"
            )
            REVIEW_VISUAL_LANE_CONTRACT.publish_generated_scaffold(
                project_root=root,
                plan_ref=PLAN_REL,
                plan_text=plan_text,
                draft_ref=DRAFT_REL,
                draft_text=draft_text,
                materialization=materialization,
            )
            adjacent = root / "docs/code_reviews/assets/260324_0009_process_exact_bundle_commit_guard_for_dirty_index/adjacent.json"
            adjacent.parent.mkdir(parents=True, exist_ok=True)
            adjacent.write_text("{}", encoding="utf-8")

            preflight = self._run_bundle(root, "--preflight")
            output = preflight.stdout + preflight.stderr
            self.assertEqual(preflight.returncode, 0, output)
            self.assertIn(str(materialization["support_ref"]), output)
            self.assertNotIn(str(adjacent.relative_to(root)), output)


if __name__ == "__main__":
    unittest.main()

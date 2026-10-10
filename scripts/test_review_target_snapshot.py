#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path
from textwrap import dedent

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from test_support.process_contract_fixtures import (
    run_zsh_fixture,
    temporary_git_root,
    write_bytes_fixture,
    write_text_fixture,
)
import plan_status_oracle


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = Path(__file__).with_name("review_target_snapshot.py")
LINT_MODULE_PATH = Path(__file__).with_name("review_artifact_lint.py")
PLANVEYOR_ZSH = REPO_ROOT / "scripts" / "planveyor.zsh"


def _load_module():
    if not MODULE_PATH.exists():
        raise AssertionError(f"Missing helper: {MODULE_PATH}")
    spec = importlib.util.spec_from_file_location("review_target_snapshot", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_lint_module():
    spec = importlib.util.spec_from_file_location("review_artifact_lint", LINT_MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ReviewTargetSnapshotTests(unittest.TestCase):
    def _write_plan_with_code_draft(self, root: Path) -> tuple[str, str]:
        plan_rel = "docs/plans/260613_1500_snapshot.md"
        draft_rel = "docs/code_drafts/260613_1500_snapshot__code_draft.md"
        write_text_fixture(
            root,
            plan_rel,
            dedent(
                f"""\
                # Snapshot fixture

                **Status:** In progress

                ## Code draft

                - Draft: `{draft_rel}`
                """
            ),
        )
        write_text_fixture(
            root,
            draft_rel,
            dedent(
                """\
                # Code draft

                ```json
                {
                  "code_draft_meta": {
                    "targets": [
                      {"path": "scripts/b_target.py"},
                      {"path": "scripts/a_target.py"}
                    ]
                  }
                }
                ```
                """
            ),
        )
        write_bytes_fixture(root, "scripts/b_target.py", b"print('b')\n")
        write_bytes_fixture(root, "scripts/a_target.py", b"print('a')\n")
        return plan_rel, draft_rel

    def _expected_files(self) -> list[dict[str, object]]:
        file_bodies = {
            "scripts/a_target.py": b"print('a')\n",
            "scripts/b_target.py": b"print('b')\n",
        }
        return [
            {
                "git_mode": "100644",
                "path": rel_path,
                "sha256": hashlib.sha256(body).hexdigest(),
                "size_bytes": len(body),
            }
            for rel_path, body in sorted(file_bodies.items())
        ]

    def _expected_bundle_sha256(self) -> str:
        payload = {
            "algorithm": "sha256",
            "files": self._expected_files(),
            "schema_version": "review_target_snapshot.hash_basis.v2",
        }
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def _write_strict_na_graph_fixture(
        self,
        root: Path,
        *,
        child_count: int = 2,
        next_plans: tuple[str, ...] | None = None,
        execution_queue: bool = True,
    ) -> dict[str, object]:
        """Create an isolated admitted strict-N-A parent with N same-stem drafts."""

        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        write_bytes_fixture(root, "docs/_meta/plan_vocab.json", (REPO_ROOT / "docs/_meta/plan_vocab.json").read_bytes())
        parent_rel = "docs/plans/260824_1700_strict_na_snapshot_parent.md"
        review_rel = "docs/code_reviews/260824_1700_strict_na_snapshot_parent.md"
        children = tuple(
            f"docs/plans/260824_{1701 + index:04d}_strict_na_snapshot_child_{index + 1}.md"
            for index in range(child_count)
        )
        child_drafts = tuple(
            f"docs/code_drafts/{Path(child).stem}__code_draft.md" for child in children
        )
        child_targets = tuple(f"scripts/strict_na_child_{index + 1}_impl.py" for index in range(child_count))
        child_reviews = tuple(f"docs/code_reviews/{Path(child).stem}.md" for child in children)
        child_deleted = tuple(f"docs/removed/strict_na_child_{index + 1}.md" for index in range(child_count))

        for child_rel, draft_rel, target_rel, review_path, deleted_rel in zip(
            children,
            child_drafts,
            child_targets,
            child_reviews,
            child_deleted,
            strict=True,
        ):
            write_text_fixture(
                root,
                child_rel,
                "# Plan: strict N-A child fixture\n\n**Plan type:** dev\n**Status:** Ready for Coder\n",
            )
            write_text_fixture(
                root,
                draft_rel,
                "# Code draft: strict N-A child fixture\n\n```json\n"
                + json.dumps(
                    {
                        "code_draft_meta": {
                            "plan": child_rel,
                            "cluster": "process",
                            "targets": [{"path": target_rel, "kind": "py"}],
                            "deleted_paths": [{"path": deleted_rel}],
                        }
                    },
                    indent=2,
                )
                + "\n```\n",
            )
            write_text_fixture(root, target_rel, f"# excluded child implementation {target_rel}\n")
            write_text_fixture(root, review_path, f"# excluded child review {review_path}\n")
            write_text_fixture(root, deleted_rel, f"# excluded deleted-path sentinel {deleted_rel}\n")

        parent_meta = {
            "plan_meta": {
                "cluster": "process",
                "phase_overlay": "decomposition_wave",
                "phase_state": "active",
                "parent": None,
                "next_plans": list(children if next_plans is None else next_plans),
                "depends_on": [],
                "followups_out": [],
                "canon_updates": [],
                "machine_authority_decision": {
                    "schema_version": "machine_authority_decision.v1",
                    "applicability": "not_applicable",
                    "reason_code": "no_machine_authority_change",
                },
            }
        }
        child_map = "\n".join(
            f"| {index} | `{child_rel}` | strict carrier |"
            for index, child_rel in enumerate(children, start=1)
        )
        execution_rows = "\n".join(f"- Plan: `{child_rel}`" for child_rel in children)
        if not execution_queue:
            execution_rows = "- Resume parent: `fixture`"
        write_text_fixture(
            root,
            parent_rel,
            "# Plan: strict N-A parent snapshot fixture\n\n"
            "**Date:** 2026-08-24 17:00 MSK\n"
            "**Plan type:** dev\n"
            "**Status:** Ready for Review\n\n"
            "**Context links (source of truth):**\n"
            "- Code draft(s): `N/A (why=strict decomposition parent fixture)`.\n\n"
            "## Meta\n```json\n"
            + json.dumps(parent_meta, indent=2)
            + "\n```\n\n"
            "## Child plan map\n"
            "| Queue order | Plan | Summary |\n"
            "| --- | --- | --- |\n"
            + child_map
            + "\n\n## Execution queue\n"
            + execution_rows
            + "\n\n## Review artifacts\n"
            + f"- Code review (primary): `{review_rel}`\n\n"
            + "## Evidence\n- Parent evidence is deliberately outside the v3 hash basis.\n",
        )
        write_text_fixture(root, review_rel, "# Parent review support (excluded from v3)\n")
        return {
            "parent_rel": parent_rel,
            "review_rel": review_rel,
            "children": children,
            "child_drafts": child_drafts,
            "child_targets": child_targets,
            "child_deleted": child_deleted,
            "child_reviews": child_reviews,
        }

    def _write_external_authority_fixture(self, root: Path) -> tuple[str, str]:
        stem = "260729_0959_process_snapshot_authority"
        plan_rel = f"docs/plans/{stem}.md"
        draft_rel = f"docs/code_drafts/{stem}__code_draft.md"
        pack_rel = f"docs/analysis_packs/{stem}.md"
        write_text_fixture(
            root,
            plan_rel,
            dedent(
                f"""\
                # Plan: snapshot authority parity

                **Plan type:** dev
                **Status:** Ready for Review

                ```json
                {{"plan_meta": {{"cluster": "process", "wave_family": "analysis_wave"}}}}
                ```

                ## Analysis pack
                | Field | Value |
                | --- | --- |
                | `analysis_pack_ref` | `{pack_rel}#Analysis-pack` |

                ## Code draft
                - Draft: `{draft_rel}`
                """
            ),
        )
        write_text_fixture(
            root,
            draft_rel,
            "# Draft\n\n```json\n"
            + json.dumps(
                {
                    "code_draft_meta": {
                        "plan": plan_rel,
                        "cluster": "process",
                        "targets": [{"path": pack_rel, "kind": "doc"}],
                        "deleted_paths": [],
                    }
                },
                indent=2,
            )
            + "\n```\n",
        )
        write_text_fixture(
            root,
            pack_rel,
            "# Analysis pack\n\n## Analysis pack\n"
            "| Field | Value |\n"
            "| --- | --- |\n"
            "| `route_recommendation` | `developer_wave` |\n"
            "| `execution_budget` | budget_status=active; source_ref_floor=1; route_iteration_limit=1; needs_analysis_depth_cap=2; current_needs_analysis_depth=1; stop_owner=Architect; exhaustion_action=architect_recheck |\n",
        )
        return plan_rel, pack_rel

    def _dual_lane_review(self, target: str) -> str:
        return dedent(
            f"""\
            # Code review - current bundle

            **Date:** 2026-06-13 15:00 MSK
            **Target:** {target}
            **Status:** ✅ ok

            ОК: fixture review artifact держит русскую summary-строку.

            ## Exact bundle hygiene
            - Exact bundle hygiene: `git diff --check -- <exact bundle>` -> OK.
            - Untracked files check: `git status --porcelain --untracked-files=all` -> no untracked files.

            ## reviewer_code_risk - GPT-5.5 xhigh
            - Lane status: `complete`
            - Target snapshot: `{target}`
            - Coverage domains: `correctness`, `tests quality`
            - No findings reason: `N/A (no risk findings)`

            ## reviewer_code_contracts - GPT-5.5 xhigh
            - Lane status: `complete`
            - Target snapshot: `{target}`
            - Coverage domains: `plan fidelity`, `docs/registry`
            - No findings reason: `N/A (no contracts findings)`

            ## Lane synthesis / aggregate verdict
            - Source lanes: `reviewer_code_risk`, `reviewer_code_contracts`
            - Canonical mapping: `none`
            - Aggregate status: `✅ ok`
            - Finding: `N/A (no findings)`
              - source_lane: `reviewer_code_risk+reviewer_code_contracts`
              - lane_finding_id: `N/A (no lane findings)`
              - synthesis_disposition: `no_findings`
              - canonical_ref: `docs/code_reviews/current_bundle.md#Lane-synthesis--aggregate-verdict`
              - audit_status: `done`
              - followup_plan: `N/A`
            """
        )

    def test_current_bundle_snapshot_is_canonical_and_linter_compatible(self) -> None:
        module = _load_module()
        lint_module = _load_lint_module()
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel, draft_rel = self._write_plan_with_code_draft(root)

            snapshot = module.build_current_bundle_snapshot(root / plan_rel, project_root=root)

            expected_bundle_sha256 = self._expected_bundle_sha256()
            self.assertEqual(snapshot["schema_version"], "review_target_snapshot.v2")
            self.assertEqual(snapshot["plan"], plan_rel)
            self.assertEqual(snapshot["code_draft"], draft_rel)
            self.assertEqual(snapshot["target_paths"], ["scripts/a_target.py", "scripts/b_target.py"])
            self.assertEqual(snapshot["files"], self._expected_files())
            self.assertEqual(snapshot["hash_basis_payload"]["files"], self._expected_files())
            self.assertIn("canonical JSON", snapshot["hash_basis"])
            self.assertEqual(
                snapshot["target_snapshot"],
                {"target": "BUNDLE=current", "bundle_sha256": expected_bundle_sha256},
            )
            self.assertEqual(snapshot["target"], f"BUNDLE=current bundle_sha256={expected_bundle_sha256}")
            self.assertEqual(snapshot["bundle_sha256"], expected_bundle_sha256)
            self.assertIs(module.validate_snapshot_payload(snapshot), snapshot)

            support_payload = {
                "run_id": "reviewer_code_risk:fixture:20260613T150000Z",
                "lane_id": "reviewer_code_risk",
                "target_snapshot": snapshot,
                "lane_status": "complete",
                "findings": [],
                "current": True,
            }
            support_bytes = json.dumps(support_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
            support_rel = "docs/code_reviews/assets/current_bundle/full_payload.json"
            write_bytes_fixture(root, support_rel, support_bytes)
            compact_payload = {
                "run_id": support_payload["run_id"],
                "lane_id": "reviewer_code_risk",
                "target_snapshot": snapshot["target_snapshot"],
                "lane_status": "complete",
                "findings": [],
                "current": True,
                "full_payload_ref": support_rel,
                "full_payload_sha256": hashlib.sha256(support_bytes).hexdigest(),
            }

            write_text_fixture(
                root,
                plan_rel,
                dedent(
                    f"""\
                    # Snapshot fixture

                    ## Code draft

                    - Draft: `{draft_rel}`

                    ## Review artifacts

                    - Code review (primary): `docs/code_reviews/current_bundle.md`

                    ## Evidence
                    - reviewer_code_risk lane-run artifact:
                      ```json
                      {json.dumps(compact_payload, indent=2)}
                      ```
                    """
                ),
            )
            write_text_fixture(root, "docs/code_reviews/current_bundle.md", self._dual_lane_review(snapshot["target"]))

            findings = lint_module.lint_review_artifacts(
                lint_module.load_review_artifacts(root, ["docs/code_reviews/current_bundle.md"]),
                project_root=root,
                origin_plan=plan_rel,
                require_dual_lane_origin=True,
            )
            self.assertEqual(findings, [])

    def test_strict_na_v3_generic_n2_payload_is_exact_and_excludes_noncarriers(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            fixture = self._write_strict_na_graph_fixture(root)
            parent_rel = str(fixture["parent_rel"])
            snapshot = module.build_current_bundle_snapshot(root / parent_rel, project_root=root)

        expected_paths = sorted(
            [*fixture["children"], *fixture["child_drafts"]]  # type: ignore[list-item]
        )
        self.assertEqual(snapshot["schema_version"], "review_target_snapshot.v3")
        self.assertEqual(
            set(snapshot),
            {
                "bundle_sha256",
                "files",
                "hash_basis",
                "hash_basis_payload",
                "plan",
                "schema_version",
                "source",
                "target",
                "target_paths",
                "target_snapshot",
            },
        )
        self.assertNotIn("code_draft", snapshot)
        self.assertEqual(
            snapshot["source"],
            {
                "kind": "strict_na_decomposition_graph",
                "child_plans": list(fixture["children"]),
                "child_code_drafts": list(fixture["child_drafts"]),
            },
        )
        self.assertEqual(snapshot["target_paths"], expected_paths)
        self.assertEqual([record["path"] for record in snapshot["files"]], expected_paths)
        self.assertEqual(snapshot["hash_basis_payload"]["source"], snapshot["source"])
        self.assertEqual(snapshot["hash_basis_payload"]["schema_version"], "review_target_snapshot.hash_basis.v3")
        self.assertEqual(snapshot["hash_basis"], module.STRICT_NA_HASH_BASIS_DESCRIPTION)
        self.assertEqual(snapshot["bundle_sha256"], module._bundle_sha256(snapshot["hash_basis_payload"]))
        excluded = {
            parent_rel,
            str(fixture["review_rel"]),
            *fixture["child_targets"],  # type: ignore[misc]
            *fixture["child_deleted"],  # type: ignore[misc]
            *fixture["child_reviews"],  # type: ignore[misc]
        }
        self.assertTrue(excluded.isdisjoint(snapshot["target_paths"]))
        self.assertIs(module.validate_snapshot_payload(snapshot), snapshot)

    def test_strict_na_v3_contextual_1509_shaped_n5_graph_is_hermetic(self) -> None:
        """Exercise the contextual N=5 shape without ambient source-plan carriers."""

        module = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            fixture = self._write_strict_na_graph_fixture(root, child_count=5)
            parent_rel = str(fixture["parent_rel"])
            plan_path = root / parent_rel
            child_state = plan_status_oracle.decomposition_child_state(
                plan_path.read_text(encoding="utf-8"),
                root=root,
            )
            snapshot = module.build_current_bundle_snapshot(plan_path, project_root=root)

        expected_children = list(child_state.canonical_planning_child_paths)
        expected_drafts = [f"docs/code_drafts/{Path(child).stem}__code_draft.md" for child in expected_children]
        self.assertEqual(child_state.state, "queue_ready")
        self.assertEqual(len(expected_children), 5)
        self.assertEqual(snapshot["schema_version"], "review_target_snapshot.v3")
        self.assertEqual(snapshot["source"]["child_plans"], expected_children)
        self.assertEqual(snapshot["source"]["child_code_drafts"], expected_drafts)
        self.assertEqual(snapshot["target_paths"], sorted([*expected_children, *expected_drafts]))
        self.assertEqual(len(snapshot["files"]), 2 * len(expected_children))

    def test_strict_na_v3_current_support_uses_generic_plan_lint_preflight(self) -> None:
        """The unchanged public consumer must validate v3, not a v2-shaped proxy."""

        import plan_lint

        module = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            fixture = self._write_strict_na_graph_fixture(root)
            parent_rel = str(fixture["parent_rel"])
            parent = root / parent_rel
            snapshot = module.build_current_bundle_snapshot(parent, project_root=root)
            self.assertEqual(snapshot["schema_version"], "review_target_snapshot.v3")

            support_rel = "docs/code_reviews/assets/strict_na/current_support.json"
            support_payload = {
                "run_id": "reviewer_code_risk:strict-na:fixture",
                "lane_id": "reviewer_code_risk",
                "target_snapshot": snapshot,
                "lane_status": "complete",
                "findings": [],
                "current": True,
            }

            def write_support_and_compact() -> dict[str, object]:
                support_bytes = json.dumps(
                    support_payload,
                    ensure_ascii=False,
                    sort_keys=True,
                ).encode("utf-8")
                write_bytes_fixture(root, support_rel, support_bytes)
                compact_payload: dict[str, object] = {
                    "run_id": support_payload["run_id"],
                    "lane_id": "reviewer_code_risk",
                    "target_snapshot": snapshot["target_snapshot"],
                    "lane_status": "complete",
                    "findings": [],
                    "current": True,
                    "full_payload_ref": support_rel,
                    "full_payload_sha256": hashlib.sha256(support_bytes).hexdigest(),
                }
                parent_prefix = parent.read_text(encoding="utf-8").split(
                    "\n- reviewer_code_risk lane-run artifact:\n", 1
                )[0]
                parent.write_text(
                    parent_prefix
                    + "\n- reviewer_code_risk lane-run artifact:\n"
                    + "  ```json\n"
                    + json.dumps(compact_payload, ensure_ascii=False, indent=2)
                    + "\n  ```\n",
                    encoding="utf-8",
                )
                return compact_payload

            write_support_and_compact()
            write_text_fixture(root, str(fixture["review_rel"]), self._dual_lane_review(snapshot["target"]))

            selection = plan_lint.select_plan_risk_lane_snapshot(parent)
            self.assertIsNone(selection.error_code)
            self.assertEqual(
                plan_lint.preflight_selected_risk_lane_support(parent, selection, project_root=root),
                (),
            )
            current_proof = plan_lint.preflight_current_review_proof(parent, project_root=root)
            self.assertEqual(
                (current_proof.state, current_proof.reason_code, current_proof.target),
                ("current_green", None, snapshot["target"]),
            )

            malformed_support = json.loads(json.dumps(support_payload))
            malformed_support["target_snapshot"]["schema_version"] = "review_target_snapshot.v999"
            support_payload = malformed_support
            write_support_and_compact()
            selection = plan_lint.select_plan_risk_lane_snapshot(parent)
            diagnostics = plan_lint.preflight_selected_risk_lane_support(parent, selection, project_root=root)
            malformed_proof = plan_lint.preflight_current_review_proof(parent, project_root=root)

        self.assertIn(
            "invalid_risk_lane_support_payload_snapshot",
            [diagnostic.code for diagnostic in diagnostics],
        )
        self.assertTrue(
            any(
                "validated review_target_snapshot current-bundle payload" in diagnostic.message
                for diagnostic in diagnostics
            )
        )
        self.assertEqual(
            (malformed_proof.state, malformed_proof.reason_code),
            ("blocked", "current_review_proof_support_invalid"),
        )

    def test_strict_na_selector_failure_never_falls_back_to_v2(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            fixture = self._write_strict_na_graph_fixture(root)
            parent_rel = str(fixture["parent_rel"])
            parent_draft_rel = f"docs/code_drafts/{Path(parent_rel).stem}__code_draft.md"
            write_text_fixture(
                root,
                parent_draft_rel,
                "# A physically present ordinary draft must block strict-N-A, never select v2.\n",
            )
            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exit_code = module.main([parent_rel, "--current-bundle", "--project-root", str(root)])

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("parent code draft", stderr.getvalue())

    def test_strict_na_v3_rejects_graph_and_child_metadata_matrix_without_stdout(self) -> None:
        module = _load_module()
        cases = (
            "missing_draft",
            "map_only",
            "next_only",
            "duplicate_map",
            "out_of_root",
            "directory",
            "symlink",
            "hardlink",
            "child_plan_mismatch",
            "invalid_targets",
            "invalid_deleted_paths",
            "parent_draft_ref",
        )
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                fixture = self._write_strict_na_graph_fixture(
                    root,
                    next_plans=() if case == "map_only" else None,
                    execution_queue=False if case == "map_only" else True,
                )
                parent_rel = str(fixture["parent_rel"])
                parent = root / parent_rel
                children = tuple(str(child) for child in fixture["children"])
                first_child = root / children[0]
                second_child = root / children[1]
                first_draft = root / str(fixture["child_drafts"][0])
                if case == "missing_draft":
                    first_draft.unlink()
                elif case == "map_only":
                    pass
                elif case == "next_only":
                    parent_text = parent.read_text(encoding="utf-8")
                    for index, child in enumerate(children, start=1):
                        parent_text = parent_text.replace(
                            f"| {index} | `{child}` | strict carrier |\n",
                            "",
                        )
                    parent_text = parent_text.replace(
                        "- Plan: `" + children[0] + "`\n- Plan: `" + children[1] + "`",
                        "- Resume parent: `fixture`",
                    )
                    parent.write_text(parent_text, encoding="utf-8")
                elif case == "duplicate_map":
                    parent_text = parent.read_text(encoding="utf-8").replace(
                        f"| 2 | `{children[1]}` | strict carrier |",
                        f"| 2 | `{children[0]}` | strict carrier |",
                    )
                    parent.write_text(parent_text, encoding="utf-8")
                elif case == "out_of_root":
                    parent_text = parent.read_text(encoding="utf-8").replace(
                        f"| 1 | `{children[0]}` | strict carrier |",
                        "| 1 | `../outside.md` | strict carrier |",
                    )
                    parent.write_text(parent_text, encoding="utf-8")
                elif case == "directory":
                    first_child.unlink()
                    first_child.mkdir()
                elif case == "symlink":
                    first_child.unlink()
                    first_child.symlink_to(second_child)
                elif case == "hardlink":
                    first_child.unlink()
                    os.link(second_child, first_child)
                elif case == "parent_draft_ref":
                    parent_draft_rel = f"docs/code_drafts/{Path(parent_rel).stem}__code_draft.md"
                    parent.write_text(
                        parent.read_text(encoding="utf-8").replace(
                            "- Code draft(s): `N/A (why=strict decomposition parent fixture)`.",
                            f"- Code draft(s): `{parent_draft_rel}`.",
                            1,
                        ),
                        encoding="utf-8",
                    )
                else:
                    draft_text = first_draft.read_text(encoding="utf-8")
                    payload = json.loads(draft_text.split("```json\n", 1)[1].split("\n```", 1)[0])
                    if case == "child_plan_mismatch":
                        payload["code_draft_meta"]["plan"] = children[1]
                    elif case == "invalid_targets":
                        payload["code_draft_meta"]["targets"] = []
                    else:
                        payload["code_draft_meta"]["deleted_paths"] = [{"kind": "doc"}]
                    first_draft.write_text(
                        "# Code draft: strict N-A child fixture\n\n```json\n"
                        + json.dumps(payload, indent=2)
                        + "\n```\n",
                        encoding="utf-8",
                    )
                stdout = io.StringIO()
                stderr = io.StringIO()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    exit_code = module.main([parent_rel, "--current-bundle", "--project-root", str(root)])
                self.assertEqual(exit_code, 1, stderr.getvalue())
                self.assertEqual(stdout.getvalue(), "")

    def test_strict_na_v3_fails_closed_on_member_or_parent_draft_drift(self) -> None:
        module = _load_module()
        for case in ("member_bytes", "member_mode", "parent_draft", "parent_topology"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                fixture = self._write_strict_na_graph_fixture(root)
                parent_rel = str(fixture["parent_rel"])
                member_rel = str(fixture["children"][0])
                member_draft_rel = str(fixture["child_drafts"][0])
                parent_draft_rel = f"docs/code_drafts/{Path(parent_rel).stem}__code_draft.md"
                original = module.snapshot_regular_or_absent
                mutated = False

                def mutate_after_capture(trusted_root: Path, relative_path: str):
                    nonlocal mutated
                    snapshot = original(trusted_root, relative_path)
                    if not mutated and (
                        (case == "member_bytes" and relative_path == member_rel)
                        or (case == "member_mode" and relative_path == member_draft_rel)
                        or (case == "parent_draft" and relative_path == parent_draft_rel)
                        or (case == "parent_topology" and relative_path == parent_rel)
                    ):
                        if case == "member_bytes":
                            (root / member_rel).write_text(
                                (root / member_rel).read_text(encoding="utf-8") + "\n- drift\n",
                                encoding="utf-8",
                            )
                        elif case == "member_mode":
                            member_draft = root / str(fixture["child_drafts"][0])
                            member_draft.chmod(member_draft.stat().st_mode | 0o100)
                        elif case == "parent_topology":
                            children = tuple(str(child) for child in fixture["children"])
                            parent = root / parent_rel
                            parent.write_text(
                                parent.read_text(encoding="utf-8").replace(
                                    f"- Plan: `{children[0]}`\n- Plan: `{children[1]}`",
                                    f"- Plan: `{children[0]}`",
                                    1,
                                ),
                                encoding="utf-8",
                            )
                        else:
                            write_text_fixture(root, parent_draft_rel, "# late parent draft\n")
                        mutated = True
                    return snapshot

                stdout = io.StringIO()
                stderr = io.StringIO()
                with mock.patch.object(module, "snapshot_regular_or_absent", side_effect=mutate_after_capture):
                    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                        exit_code = module.main([parent_rel, "--current-bundle", "--project-root", str(root)])

                self.assertTrue(mutated)
                self.assertEqual(exit_code, 1, stderr.getvalue())
                self.assertEqual(stdout.getvalue(), "")

    def test_strict_na_v3_validator_rejects_mixed_pairing_and_inventory_payloads(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            fixture = self._write_strict_na_graph_fixture(root)
            snapshot = module.build_current_bundle_snapshot(root / str(fixture["parent_rel"]), project_root=root)

        mutations: list[tuple[str, object]] = []
        mixed = json.loads(json.dumps(snapshot))
        mixed["code_draft"] = "docs/code_drafts/leak.md"
        mutations.append(("v2 field", mixed))
        pairing = json.loads(json.dumps(snapshot))
        pairing["source"]["child_code_drafts"].reverse()
        pairing["hash_basis_payload"]["source"] = pairing["source"]
        pairing["bundle_sha256"] = module._bundle_sha256(pairing["hash_basis_payload"])
        pairing["target_snapshot"]["bundle_sha256"] = pairing["bundle_sha256"]
        pairing["target"] = f"BUNDLE=current bundle_sha256={pairing['bundle_sha256']}"
        mutations.append(("mispaired", pairing))
        inventory = json.loads(json.dumps(snapshot))
        inventory["files"] = inventory["files"][:-1]
        inventory["hash_basis_payload"]["files"] = inventory["files"]
        inventory["bundle_sha256"] = module._bundle_sha256(inventory["hash_basis_payload"])
        inventory["target_snapshot"]["bundle_sha256"] = inventory["bundle_sha256"]
        inventory["target"] = f"BUNDLE=current bundle_sha256={inventory['bundle_sha256']}"
        mutations.append(("short inventory", inventory))
        parent_self_reference = json.loads(json.dumps(snapshot))
        original_plan = parent_self_reference["source"]["child_plans"][0]
        original_draft = parent_self_reference["source"]["child_code_drafts"][0]
        parent_rel = parent_self_reference["plan"]
        parent_draft_rel = module._strict_same_stem_draft_path(parent_rel)
        parent_self_reference["source"]["child_plans"][0] = parent_rel
        parent_self_reference["source"]["child_code_drafts"][0] = parent_draft_rel
        parent_self_reference["files"] = sorted(
            [
                record
                for record in parent_self_reference["files"]
                if record["path"] not in {original_plan, original_draft}
            ]
            + [
                {"git_mode": "100644", "path": parent_rel, "sha256": "a" * 64, "size_bytes": 1},
                {"git_mode": "100644", "path": parent_draft_rel, "sha256": "b" * 64, "size_bytes": 1},
            ],
            key=lambda record: record["path"],
        )
        parent_self_reference["target_paths"] = [
            record["path"] for record in parent_self_reference["files"]
        ]
        parent_self_reference["hash_basis_payload"]["files"] = parent_self_reference["files"]
        parent_self_reference["hash_basis_payload"]["source"] = parent_self_reference["source"]
        parent_self_reference["bundle_sha256"] = module._bundle_sha256(
            parent_self_reference["hash_basis_payload"]
        )
        parent_self_reference["target_snapshot"]["bundle_sha256"] = parent_self_reference["bundle_sha256"]
        parent_self_reference["target"] = (
            f"BUNDLE=current bundle_sha256={parent_self_reference['bundle_sha256']}"
        )
        mutations.append(("parent self reference", parent_self_reference))

        for label, payload in mutations:
            with self.subTest(case=label):
                with self.assertRaises(module.SnapshotError):
                    module.validate_snapshot_payload(payload)

    def test_strict_na_v3_parent_evidence_is_stable_but_child_bytes_and_modes_change_hash(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            fixture = self._write_strict_na_graph_fixture(root)
            parent = root / str(fixture["parent_rel"])
            review = root / str(fixture["review_rel"])
            before = module.build_current_bundle_snapshot(parent, project_root=root)
            parent.write_text(parent.read_text(encoding="utf-8") + "\n- Evidence append.\n", encoding="utf-8")
            review.write_text("# Rewritten excluded review support\n", encoding="utf-8")
            after_excluded = module.build_current_bundle_snapshot(parent, project_root=root)
            child = root / str(fixture["children"][0])
            child.write_text(child.read_text(encoding="utf-8") + "\n- Child bytes mutate.\n", encoding="utf-8")
            after_child_bytes = module.build_current_bundle_snapshot(parent, project_root=root)
            draft = root / str(fixture["child_drafts"][0])
            draft.chmod(draft.stat().st_mode | 0o100)
            after_child_mode = module.build_current_bundle_snapshot(parent, project_root=root)

        self.assertEqual(before["bundle_sha256"], after_excluded["bundle_sha256"])
        self.assertNotEqual(after_excluded["bundle_sha256"], after_child_bytes["bundle_sha256"])
        self.assertNotEqual(after_child_bytes["bundle_sha256"], after_child_mode["bundle_sha256"])

    def test_later_snapshot_cannot_retroactively_validate_rejected_authority(self) -> None:
        module = _load_module()
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel, pack_rel = self._write_external_authority_fixture(root)
            plan = root / plan_rel
            pack = root / pack_rel
            replacement_data = pack.read_bytes().replace(
                b"budget_status=active",
                b"budget_status=exhausted",
            ).replace(b"developer_wave", b"reject")
            replacement = pack.with_name(f".{pack.name}.replacement")
            replacement.write_bytes(replacement_data)
            real_snapshot = plan_status_oracle.snapshot_regular_or_absent
            replaced = False

            def wrapped(trusted_root: Path, relative_path: str) -> object:
                nonlocal replaced
                if relative_path != pack_rel:
                    return real_snapshot(trusted_root, relative_path)

                def observer(stage: str) -> None:
                    nonlocal replaced
                    if stage == "after_leaf_read" and not replaced:
                        replacement.replace(pack)
                        replaced = True

                return real_snapshot(trusted_root, relative_path, _observer=observer)

            plan_text = plan.read_text(encoding="utf-8")
            with mock.patch.object(
                plan_status_oracle,
                "snapshot_regular_or_absent",
                side_effect=wrapped,
            ):
                rejected = plan_status_oracle.resolve_analysis_pack_authority(
                    origin_plan_path=plan,
                    plan_text=plan_text,
                    effective_status="Ready for Review",
                )

            later_snapshot = module.build_current_bundle_snapshot(plan, project_root=root)
            later_resolution = plan_status_oracle.resolve_analysis_pack_authority(
                origin_plan_path=plan,
                plan_text=plan_text,
                effective_status="Ready for Review",
            )

        self.assertTrue(replaced)
        self.assertFalse(rejected.is_valid)
        self.assertEqual(rejected.detail_category, "pack_unreadable")
        self.assertEqual(rejected.authority_text, "")
        self.assertTrue(later_resolution.is_valid)
        self.assertIn("budget_status=exhausted", later_resolution.authority_text)
        self.assertFalse(rejected.is_valid)
        self.assertEqual(rejected.authority_text, "")
        self.assertEqual(later_snapshot["schema_version"], "review_target_snapshot.v2")
        self.assertEqual(
            later_snapshot["hash_basis_payload"]["schema_version"],
            "review_target_snapshot.hash_basis.v2",
        )
        self.assertEqual(later_snapshot["target_paths"], [pack_rel])
        self.assertEqual(
            later_snapshot["files"][0]["sha256"],
            hashlib.sha256(replacement_data).hexdigest(),
        )

    def test_main_prints_json_to_stdout_only_and_preserves_plan(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel, _ = self._write_plan_with_code_draft(root)
            before = (root / plan_rel).read_bytes()

            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exit_code = module.main([plan_rel, "--current-bundle", "--project-root", str(root)])

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr.getvalue(), "")
            parsed = json.loads(stdout.getvalue())
            self.assertEqual(parsed["target"], f"BUNDLE=current bundle_sha256={self._expected_bundle_sha256()}")
            self.assertEqual((root / plan_rel).read_bytes(), before)
            self.assertFalse((root / "docs" / "code_reviews").exists())

    def test_current_bundle_snapshot_fails_closed_when_target_changes_during_read(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel, _ = self._write_plan_with_code_draft(root)
            target = root / "scripts/a_target.py"
            original = module._file_digest_and_size

            def replace_after_read(path: Path):
                result = original(path)
                if path == target:
                    path.write_bytes(b"print('z')\n")
                return result

            with mock.patch.object(
                module,
                "_file_digest_and_size",
                side_effect=replace_after_read,
            ):
                with self.assertRaisesRegex(
                    module.SnapshotError,
                    "current target changed while reading: scripts/a_target.py",
                ):
                    module.build_current_bundle_snapshot(root / plan_rel, project_root=root)

    def test_current_bundle_snapshot_fails_closed_when_target_mode_changes_during_read(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel, _ = self._write_plan_with_code_draft(root)
            target = root / "scripts/a_target.py"
            original = module._file_digest_and_size

            def chmod_after_read(path: Path):
                result = original(path)
                if path == target:
                    path.chmod(path.stat().st_mode | 0o100)
                return result

            with mock.patch.object(module, "_file_digest_and_size", side_effect=chmod_after_read):
                with self.assertRaisesRegex(
                    module.SnapshotError,
                    "current target changed while reading: scripts/a_target.py",
                ):
                    module.build_current_bundle_snapshot(root / plan_rel, project_root=root)

    def test_current_bundle_snapshot_authenticates_normalized_git_mode(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel, _ = self._write_plan_with_code_draft(root)
            target = root / "scripts/a_target.py"

            non_executable = module.build_current_bundle_snapshot(root / plan_rel, project_root=root)
            target.chmod(target.stat().st_mode | 0o100)
            executable = module.build_current_bundle_snapshot(root / plan_rel, project_root=root)

            non_executable_record = next(
                record for record in non_executable["files"] if record["path"] == "scripts/a_target.py"
            )
            executable_record = next(
                record for record in executable["files"] if record["path"] == "scripts/a_target.py"
            )
            self.assertEqual(non_executable_record["git_mode"], "100644")
            self.assertEqual(executable_record["git_mode"], "100755")
            self.assertEqual(non_executable_record["sha256"], executable_record["sha256"])
            self.assertNotEqual(non_executable["bundle_sha256"], executable["bundle_sha256"])

    def test_snapshot_payload_validator_rejects_v1_mixed_and_malformed_payloads(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel, _ = self._write_plan_with_code_draft(root)
            snapshot = module.build_current_bundle_snapshot(root / plan_rel, project_root=root)

        v1 = json.loads(json.dumps(snapshot))
        v1["schema_version"] = "review_target_snapshot.v1"
        with self.assertRaisesRegex(module.SnapshotError, "unsupported snapshot schema_version"):
            module.validate_snapshot_payload(v1)

        mixed = json.loads(json.dumps(snapshot))
        mixed["hash_basis_payload"]["schema_version"] = "review_target_snapshot.hash_basis.v1"
        with self.assertRaisesRegex(module.SnapshotError, "unsupported hash_basis_payload schema_version"):
            module.validate_snapshot_payload(mixed)

        malformed = json.loads(json.dumps(snapshot))
        del malformed["files"][0]["git_mode"]
        with self.assertRaisesRegex(module.SnapshotError, "must contain exactly"):
            module.validate_snapshot_payload(malformed)

    def test_current_bundle_snapshot_fails_when_prior_target_changes_later(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel, _ = self._write_plan_with_code_draft(root)
            prior_target = root / "scripts/a_target.py"
            original = module._file_record

            def mutate_prior_target(rel_path: str, path: Path):
                if rel_path == "scripts/b_target.py":
                    prior_target.write_bytes(b"print('changed after read')\n")
                return original(rel_path, path)

            with mock.patch.object(module, "_file_record", side_effect=mutate_prior_target):
                with self.assertRaisesRegex(
                    module.SnapshotError,
                    "current target: scripts/a_target.py changed during snapshot",
                ):
                    module.build_current_bundle_snapshot(root / plan_rel, project_root=root)

    def test_current_bundle_snapshot_fails_when_manifest_changes_during_target_reads(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel, draft_rel = self._write_plan_with_code_draft(root)
            draft = root / draft_rel
            original = module._file_record
            mutated = False

            def mutate_manifest(rel_path: str, path: Path):
                nonlocal mutated
                if not mutated:
                    draft.write_text(
                        draft.read_text(encoding="utf-8") + "\n<!-- manifest drift -->\n",
                        encoding="utf-8",
                    )
                    mutated = True
                return original(rel_path, path)

            with mock.patch.object(module, "_file_record", side_effect=mutate_manifest):
                with self.assertRaisesRegex(
                    module.SnapshotError,
                    "code draft: .* changed during snapshot",
                ):
                    module.build_current_bundle_snapshot(root / plan_rel, project_root=root)

    def test_zsh_wrapper_invokes_stdout_only_helper(self) -> None:
        _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel, _ = self._write_plan_with_code_draft(root)
            command = (
                f"source {shlex.quote(str(PLANVEYOR_ZSH))}; "
                f"planveyor_review_target_snapshot {shlex.quote(plan_rel)} --current-bundle --project-root ."
            )

            result = run_zsh_fixture(
                command,
                cwd=root,
                path=os.environ.get("PATH", os.defpath),
                pybin=str(Path(sys.executable).resolve()),
                fixture_env={"PYTHONDONTWRITEBYTECODE": "1"},
                capture_output=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            parsed = json.loads(result.stdout)
            self.assertEqual(parsed["target"], f"BUNDLE=current bundle_sha256={self._expected_bundle_sha256()}")

    def _write_plan_with_single_target(self, root: Path, plan_rel: str, draft_rel: str, target_path: str) -> None:
        write_text_fixture(
            root,
            plan_rel,
            dedent(
                f"""\
                # Snapshot fixture

                **Status:** In progress

                ## Code draft

                - Draft: `{draft_rel}`
                """
            ),
        )
        write_text_fixture(
            root,
            draft_rel,
            dedent(
                f"""\
                # Code draft

                ```json
                {{
                  "code_draft_meta": {{
                    "targets": [
                      {{"path": "{target_path}"}}
                    ]
                  }}
                }}
                ```
                """
            ),
        )

    def test_current_bundle_snapshot_preserves_literal_trailing_space_target_path(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260613_1510_trailing.md"
            draft_rel = "docs/code_drafts/260613_1510_trailing__code_draft.md"
            trailing_target = "scripts/trailing_target.py "  # literal trailing space
            body = b"print('trailing')\n"
            self._write_plan_with_single_target(root, plan_rel, draft_rel, trailing_target)
            write_bytes_fixture(root, trailing_target, body)

            snapshot = module.build_current_bundle_snapshot(root / plan_rel, project_root=root)

        self.assertEqual(snapshot["target_paths"], [trailing_target])
        self.assertEqual(len(snapshot["files"]), 1)
        self.assertEqual(snapshot["files"][0]["path"], trailing_target)
        self.assertEqual(snapshot["files"][0]["sha256"], hashlib.sha256(body).hexdigest())
        self.assertEqual(snapshot["files"][0]["size_bytes"], len(body))
        self.assertEqual(snapshot["files"][0]["git_mode"], "100644")

    def test_current_bundle_snapshot_fails_closed_on_empty_target_path(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260613_1511_empty.md"
            draft_rel = "docs/code_drafts/260613_1511_empty__code_draft.md"
            self._write_plan_with_single_target(root, plan_rel, draft_rel, "")

            with self.assertRaisesRegex(module.SnapshotError, "must be a non-empty string"):
                module.build_current_bundle_snapshot(root / plan_rel, project_root=root)

    def test_current_bundle_snapshot_rejects_trimmed_alias_of_missing_trailing_space_target(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260613_1512_alias.md"
            draft_rel = "docs/code_drafts/260613_1512_alias__code_draft.md"
            declared = "scripts/alias_target.py "  # literal trailing space
            self._write_plan_with_single_target(root, plan_rel, draft_rel, declared)
            # Only the trimmed (no-space) file exists; the literal trailing-space target must stay missing.
            write_bytes_fixture(root, "scripts/alias_target.py", b"print('trimmed')\n")

            with self.assertRaises(module.SnapshotError) as ctx:
                module.build_current_bundle_snapshot(root / plan_rel, project_root=root)

        self.assertIn("missing current target: scripts/alias_target.py ", str(ctx.exception))

    def test_origin_plan_target_fails_before_hashing_or_stdout_snapshot(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260729_1900_origin_target.md"
            draft_rel = "docs/code_drafts/260729_1900_origin_target__code_draft.md"
            self._write_plan_with_single_target(root, plan_rel, draft_rel, plan_rel)

            with mock.patch.object(module, "_file_record") as file_record:
                with self.assertRaisesRegex(
                    module.SnapshotError,
                    "origin_plan_in_review_targets",
                ):
                    module.build_current_bundle_snapshot(root / plan_rel, project_root=root)
            file_record.assert_not_called()

            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exit_code = module.main(
                    [plan_rel, "--current-bundle", "--project-root", str(root)]
                )
            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("origin_plan_in_review_targets", stderr.getvalue())

    def test_origin_plan_mixed_with_valid_targets_makes_bundle_non_green(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260729_1910_origin_mixed.md"
            draft_rel = "docs/code_drafts/260729_1910_origin_mixed__code_draft.md"
            self._write_plan_with_single_target(root, plan_rel, draft_rel, plan_rel)
            draft_path = root / draft_rel
            draft_path.write_text(
                draft_path.read_text(encoding="utf-8").replace(
                    f'{{"path": "{plan_rel}"}}',
                    f'{{"path": "scripts/ordinary.py"}},\n'
                    f'                      {{"path": "{plan_rel}"}},\n'
                    '                      {"path": "docs/ordinary.md"}',
                ),
                encoding="utf-8",
            )
            write_bytes_fixture(root, "scripts/ordinary.py", b"# ordinary\n")
            write_bytes_fixture(root, "docs/ordinary.md", b"# ordinary\n")

            with self.assertRaisesRegex(
                module.SnapshotError,
                "origin_plan_in_review_targets",
            ):
                module.build_current_bundle_snapshot(root / plan_rel, project_root=root)

    def test_symlink_and_hardlink_aliases_cannot_bypass_origin_guard(self) -> None:
        module = _load_module()
        for alias_kind in ("symlink", "hardlink"):
            with self.subTest(alias_kind=alias_kind), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                plan_rel = f"docs/plans/260729_1920_origin_{alias_kind}.md"
                draft_rel = f"docs/code_drafts/260729_1920_origin_{alias_kind}__code_draft.md"
                alias_rel = f"docs/aliases/260729_1920_origin_{alias_kind}.md"
                self._write_plan_with_single_target(root, plan_rel, draft_rel, alias_rel)
                alias_path = root / alias_rel
                alias_path.parent.mkdir(parents=True, exist_ok=True)
                if alias_kind == "symlink":
                    alias_path.symlink_to(root / plan_rel)
                else:
                    alias_path.hardlink_to(root / plan_rel)

                with self.assertRaisesRegex(
                    module.SnapshotError,
                    "origin_plan_in_review_targets",
                ):
                    module.build_current_bundle_snapshot(root / plan_rel, project_root=root)

    def test_accepted_lexical_alias_cannot_bypass_origin_guard(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260729_1925_origin_lexical.md"
            draft_rel = "docs/code_drafts/260729_1925_origin_lexical__code_draft.md"
            declared = "docs//plans/260729_1925_origin_lexical.md"
            self._write_plan_with_single_target(root, plan_rel, draft_rel, declared)

            with self.assertRaisesRegex(
                module.SnapshotError,
                "origin_plan_in_review_targets",
            ):
                module.build_current_bundle_snapshot(root / plan_rel, project_root=root)

    def test_case_alias_guard_is_capability_gated(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260729_1930_Case_Alias.md"
            alias_rel = "docs/plans/260729_1930_case_alias.md"
            draft_rel = "docs/code_drafts/260729_1930_Case_Alias__code_draft.md"
            self._write_plan_with_single_target(root, plan_rel, draft_rel, alias_rel)
            alias_path = root / alias_rel
            if not alias_path.exists() or not alias_path.samefile(root / plan_rel):
                self.skipTest("filesystem does not resolve case aliases to the same file object")

            with self.assertRaisesRegex(
                module.SnapshotError,
                "origin_plan_in_review_targets",
            ):
                module.build_current_bundle_snapshot(root / plan_rel, project_root=root)

    def test_unicode_alias_guard_is_capability_gated(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260729_1940_café.md"
            alias_rel = "docs/plans/260729_1940_cafe\u0301.md"
            draft_rel = "docs/code_drafts/260729_1940_unicode_alias__code_draft.md"
            self._write_plan_with_single_target(root, plan_rel, draft_rel, alias_rel)
            alias_path = root / alias_rel
            if not alias_path.exists() or not alias_path.samefile(root / plan_rel):
                self.skipTest("filesystem does not normalize Unicode aliases to the same file object")

            with self.assertRaisesRegex(
                module.SnapshotError,
                "origin_plan_in_review_targets",
            ):
                module.build_current_bundle_snapshot(root / plan_rel, project_root=root)

    def test_independent_same_stem_target_remains_eligible(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            stem = "260729_1950_origin_same_stem"
            plan_rel = f"docs/plans/{stem}.md"
            draft_rel = f"docs/code_drafts/{stem}__code_draft.md"
            target_rel = f"docs/analysis_packs/{stem}.md"
            self._write_plan_with_single_target(root, plan_rel, draft_rel, target_rel)
            write_bytes_fixture(root, target_rel, b"# Independent analysis pack\n")

            snapshot = module.build_current_bundle_snapshot(root / plan_rel, project_root=root)

        self.assertEqual(snapshot["target_paths"], [target_rel])

    def test_snapshot_reuses_plan_lint_identity_predicate_after_path_validation(self) -> None:
        module = _load_module()
        import plan_lint

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260729_1960_origin_shared_predicate.md"
            draft_rel = "docs/code_drafts/260729_1960_origin_shared_predicate__code_draft.md"
            self._write_plan_with_single_target(root, plan_rel, draft_rel, plan_rel)

            with mock.patch.object(
                plan_lint,
                "same_file_object",
                wraps=plan_lint.same_file_object,
            ) as predicate:
                with self.assertRaisesRegex(
                    module.SnapshotError,
                    "origin_plan_in_review_targets",
                ):
                    module.build_current_bundle_snapshot(root / plan_rel, project_root=root)

            predicate.assert_called_once()

    def test_invalid_path_reason_precedes_identity_predicate(self) -> None:
        module = _load_module()
        import plan_lint

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260729_1970_origin_invalid_precedence.md"
            draft_rel = "docs/code_drafts/260729_1970_origin_invalid_precedence__code_draft.md"
            self._write_plan_with_single_target(
                root,
                plan_rel,
                draft_rel,
                "../docs/plans/260729_1970_origin_invalid_precedence.md",
            )

            with mock.patch.object(plan_lint, "same_file_object") as predicate:
                with self.assertRaisesRegex(
                    module.SnapshotError,
                    "repo-relative without traversal",
                ):
                    module.build_current_bundle_snapshot(root / plan_rel, project_root=root)

            predicate.assert_not_called()

    def test_plan_evidence_append_does_not_change_standalone_target_hash(self) -> None:
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260729_1980_origin_evidence_append.md"
            draft_rel = "docs/code_drafts/260729_1980_origin_evidence_append__code_draft.md"
            target_rel = "docs/analysis_packs/260729_1980_origin_evidence_append.md"
            self._write_plan_with_single_target(root, plan_rel, draft_rel, target_rel)
            write_bytes_fixture(root, target_rel, b"# Stable reviewed content\n")

            before = module.build_current_bundle_snapshot(root / plan_rel, project_root=root)
            plan_path = root / plan_rel
            plan_path.write_text(
                plan_path.read_text(encoding="utf-8")
                + "\n## Evidence\n- reviewer_code_risk receipt appended here.\n",
                encoding="utf-8",
            )
            after = module.build_current_bundle_snapshot(root / plan_rel, project_root=root)

        self.assertEqual(before["bundle_sha256"], after["bundle_sha256"])
        self.assertEqual(before["files"], after["files"])


if __name__ == "__main__":
    unittest.main()

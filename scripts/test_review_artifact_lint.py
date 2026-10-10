#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from textwrap import dedent
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from test_support.process_contract_fixtures import (
    standalone_git_root,
    temporary_git_root,
    write_bytes_fixture,
    write_text_fixture,
)


MODULE_PATH = Path(__file__).with_name("review_artifact_lint.py")
SPEC = importlib.util.spec_from_file_location("review_artifact_lint", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

import review_schema_contract
import plan_lint


class ReviewArtifactLintTests(unittest.TestCase):
    def test_review_range_v2_cross_reader_calls_shared_shape_validator(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/260910_0030_reviewer_range_fixture.md"
            review_rel = "docs/code_reviews/260910_0030_reviewer_range_fixture.md"
            self._write_markdown(root, plan_rel, "# Plan\n")
            review_path = self._write_markdown(root, review_rel, "# Review\n")
            v2 = {"schema_version": "review_range_semantic_provenance.v2"}
            with mock.patch.object(plan_lint, "parse_review_range_semantic_provenance", return_value=(v2, None)), mock.patch.object(
                plan_lint,
                "_review_range_semantic_provenance_shape_error",
                return_value="engaged_input_set",
            ) as shape:
                result = MODULE.evaluate_review_range_semantic_provenance(
                    project_root=root,
                    review_path=review_path,
                    origin_plan=plan_rel,
                    review_text="# Review\n",
                )
        self.assertEqual(result, ("review_range_provenance_invalid",))
        shape.assert_called_once_with(v2)

    def _write_markdown(self, root: Path, rel_path: str, body: str) -> Path:
        for line in body.splitlines():
            if not line.strip():
                continue
            stripped = line.lstrip(" ")
            if stripped.startswith("# ") and len(stripped) != len(line):
                prefix = " " * (len(line) - len(stripped))
                body = "\n".join(
                    candidate[len(prefix):] if candidate.startswith(prefix) else candidate
                    for candidate in body.splitlines()
                ) + ("\n" if body.endswith("\n") else "")
            break
        return write_text_fixture(root, rel_path, body)

    def _load_single(self, root: Path, rel_path: str):
        return MODULE.load_review_artifacts(root, [rel_path])

    def test_review_artifact_from_text_uses_supplied_snapshot(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            path = self._write_markdown(
                root,
                "docs/code_reviews/snapshot.md",
                "# Review\n\n**Status:** ❌ S1 blocker(ы)\n",
            )
            artifact = MODULE.review_artifact_from_text(
                root,
                path,
                "# Review\n\n**Status:** ✅ OK\n",
            )

        self.assertIn("**Status:** ✅ OK", artifact.lines)
        self.assertNotIn("**Status:** ❌ S1 blocker(ы)", artifact.lines)
        self.assertEqual(artifact.rel_path, "docs/code_reviews/snapshot.md")

    def test_review_schema_version_uses_shared_contract(self) -> None:
        self.assertEqual(MODULE.CURRENT_REVIEW_SCHEMA_VERSION, review_schema_contract.CURRENT_REVIEW_SCHEMA_VERSION)
        self.assertEqual(MODULE.CURRENT_REVIEW_SCHEMA_VERSION, "review.v1")

    def _write_asset(self, root: Path, rel_path: str, body: bytes = b"png") -> Path:
        return write_bytes_fixture(root, rel_path, body)

    def _homebrew_pybin_literal(self) -> str:
        return "/" + "opt/homebrew/bin/python3"

    def _small_runner_findings(self, root: Path, rel_path: str):
        findings = MODULE.lint_review_artifacts(self._load_single(root, rel_path), project_root=root)
        return [finding for finding in findings if finding.code.startswith("small_runner_")]

    def _write_origin_plan(self, root: Path, rel_path: str, target_snapshot: str | None) -> Path:
        if target_snapshot is None:
            body = "# Plan\n\n## Evidence\n- risk lane was not materialized\n"
        else:
            body = dedent(
                f"""\
                # Plan

                ## Evidence
                - reviewer_code_risk lane-run artifact:
                  ```json
                  {{
                    "lane_id": "reviewer_code_risk",
                    "target_snapshot": "{target_snapshot}",
                    "lane_status": "complete"
                  }}
                  ```
                """
            )
        return self._write_markdown(root, rel_path, body)

    def _write_structured_origin_plan(self, root: Path, rel_path: str, snapshot: dict[str, str]) -> Path:
        body = dedent(
            f"""\
            # Plan

            ## Evidence
            - reviewer_code_risk lane-run artifact:
              ```json
              {json.dumps({"lane_id": "reviewer_code_risk", "target_snapshot": snapshot, "lane_status": "complete"}, indent=2)}
              ```
            """
        )
        return self._write_markdown(root, rel_path, body)

    def _write_current_bundle_origin_plan(
        self,
        root: Path,
        rel_path: str,
        target_snapshot: str | dict[str, str],
        *,
        payload: dict[str, object] | None = None,
        review_rel: str | None = None,
    ) -> Path:
        draft_rel = rel_path.replace("docs/plans/", "docs/code_drafts/").replace(".md", "__code_draft.md")
        payload = payload or {"lane_id": "reviewer_code_risk", "target_snapshot": target_snapshot, "lane_status": "complete"}
        self._write_markdown(
            root,
            draft_rel,
            dedent(
                """\
                # Code draft

                ```json
                {
                  "code_draft_meta": {
                    "targets": [
                      {"path": "scripts/current_bundle_target.py"}
                    ]
                  }
                }
                ```
                """
            ),
        )
        write_text_fixture(root, "scripts/current_bundle_target.py", "print('current')\n")
        review_section = (
            f"\n## Review artifacts\n\n- Code review (primary): `{review_rel}`\n"
            if review_rel is not None
            else ""
        )
        body = dedent(
            f"""\
            # Plan

            **Status:** In progress

            ## Code draft

            - Draft: `{draft_rel}`

            {review_section}

            ## Evidence
            - reviewer_code_risk lane-run artifact:
              ```json
              {json.dumps(payload, indent=2)}
              ```
            """
        )
        return self._write_markdown(root, rel_path, body)

    def _materialize_current_proof(
        self,
        root: Path,
        *,
        plan_rel: str,
        review_rel: str,
    ) -> tuple[dict[str, object], dict[str, object]]:
        seed = {"bundle_sha256": "0" * 64, "target": "BUNDLE=current"}
        self._write_current_bundle_origin_plan(root, plan_rel, seed, review_rel=review_rel)
        snapshot = MODULE.build_current_bundle_snapshot(root / plan_rel, project_root=root)
        support_payload: dict[str, object] = {
            "run_id": "reviewer_code_risk:fixture:20260619T024200Z",
            "lane_id": "reviewer_code_risk",
            "target_snapshot": snapshot,
            "lane_status": "no_findings",
            "findings": [],
            "current": True,
        }
        support_rel, support_sha = self._write_support_payload(
            root,
            f"docs/code_reviews/assets/{Path(review_rel).stem}/full_payload.json",
            support_payload,
        )
        compact_payload: dict[str, object] = {
            "run_id": support_payload["run_id"],
            "lane_id": "reviewer_code_risk",
            "target_snapshot": snapshot["target_snapshot"],
            "lane_status": "no_findings",
            "findings": [],
            "current": True,
            "full_payload_ref": support_rel,
            "full_payload_sha256": support_sha,
        }
        self._write_current_bundle_origin_plan(
            root,
            plan_rel,
            snapshot["target_snapshot"],
            payload=compact_payload,
            review_rel=review_rel,
        )
        return snapshot, compact_payload

    def _write_origin_plan_payloads(self, root: Path, rel_path: str, payloads: list[dict[str, object]]) -> Path:
        blocks = "\n".join(
            dedent(
                f"""\
                - reviewer_code_risk lane-run artifact:
                  ```json
                  {json.dumps(payload, indent=2)}
                  ```
                """
            )
            for payload in payloads
        )
        body = dedent(
            f"""\
            # Plan

            ## Evidence
            {blocks}
            """
        )
        return self._write_markdown(root, rel_path, body)

    def _write_support_payload(self, root: Path, rel_path: str, payload: dict[str, object]) -> tuple[str, str]:
        body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        path = write_bytes_fixture(root, rel_path, body)
        return str(path.relative_to(root)), hashlib.sha256(body).hexdigest()

    def _write_same_file_plan(self, root: Path, rel_path: str, review_rel: str, extra_notes: str = "") -> Path:
        notes = f"{extra_notes.rstrip()}\n" if extra_notes.strip() else ""
        body = dedent(
            f"""\
            # Plan

            **Date:** 2026-05-07 01:00 MSK
            **Status:** In progress

            ## Review artifacts

            - Code review (primary): `{review_rel}`
            {notes}
            """
        )
        return self._write_markdown(root, rel_path, body)

    def _same_file_review_fixture(
        self,
        *,
        status: str,
        target: str,
        aggregate_status: str | None = None,
        date: str = "2026-05-07 02:00 MSK",
        marker: str = "",
        blocker_state: str | None = None,
    ) -> str:
        aggregate_status = aggregate_status or status
        marker_block = f"\n{marker.rstrip()}\n" if marker.strip() else ""
        blocker_block = ""
        if blocker_state is not None:
            blocker_block = dedent(
                """\
                ## S1 Blocker

                ### B1
                - Blocker ID: B1
                - Current state: {blocker_state}
                - Classification: same-contract reroute
                - Primary owner gap: Coder
                - Evidence refs: `docs/code_reviews/sample.md#B1`
                """
            ).format(blocker_state=blocker_state)

        return dedent(
            f"""\
            # Code review — merge-range (abc1234..def5678)

            **Date:** {date}
            **Target:** {target}
            **Status:** {status}

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
            - Aggregate status: `{aggregate_status}`
            - Finding: `N/A (findings отсутствуют)`
              - source_lane: `reviewer_code_risk+reviewer_code_contracts`
              - lane_finding_id: `N/A (no lane findings)`
              - synthesis_disposition: `no_findings`
              - canonical_ref: `docs/code_reviews/sample.md#Lane-synthesis--aggregate-verdict`
              - audit_status: `done`
              - followup_plan: `N/A`
            {marker_block}
            {blocker_block}
            """
        )

    def _dual_lane_sections(
        self,
        target_snapshot: str,
        *,
        aggregate_status: str,
        risk_findings: str | None = None,
        contracts_findings: str | None = None,
        canonical_mapping: str = "`none`",
        synthesis_provenance_records: str | None = None,
        include_default_no_findings_provenance: bool = True,
    ) -> str:
        risk_body = (
            "- Findings:\n"
            f"  - {risk_findings}\n"
            "- No findings reason: `N/A`\n"
            if risk_findings
            else "- No findings reason: `N/A (no risk findings)`\n"
        )
        contracts_body = (
            "- Findings:\n"
            f"  - {contracts_findings}\n"
            "- No findings reason: `N/A`\n"
            if contracts_findings
            else "- No findings reason: `N/A (no contracts findings)`\n"
        )
        if (
            synthesis_provenance_records is None
            and include_default_no_findings_provenance
            and not risk_findings
            and not contracts_findings
        ):
            synthesis_provenance_records = self._no_findings_synthesis_provenance_record()
        provenance_body = f"\n{synthesis_provenance_records.rstrip()}\n" if synthesis_provenance_records else ""
        return dedent(
            f"""\
            ## reviewer_code_risk - GPT-5.5 xhigh
            - Lane status: `complete`
            - Target snapshot: `{target_snapshot}`
            - Coverage domains: `correctness`, `tests quality`, `security/privacy`
            {risk_body}
            ## reviewer_code_contracts - GPT-5.5 xhigh
            - Lane status: `complete`
            - Target snapshot: `{target_snapshot}`
            - Coverage domains: `plan fidelity`, `architecture/design fit`, `docs/registry`
            {contracts_body}
            ## Lane synthesis / aggregate verdict
            - Source lanes: `reviewer_code_risk`, `reviewer_code_contracts`
            - Canonical mapping: {canonical_mapping}
            - Aggregate status: `{aggregate_status}`
            {provenance_body}
            """
        )

    def test_small_runner_success_without_proof_warns(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            rel = "docs/code_reviews/260619_0032_small_runner_missing_proof.md"
            self._write_markdown(
                root,
                rel,
                dedent(
                    """\
                    # Код-ревью - small runner fixture

                    **Status:** draft

                    ## runner_quality
                    - small_runner_success: true
                    """
                ),
            )

            findings = self._small_runner_findings(root, rel)

        self.assertTrue(any(finding.code == "small_runner_success_missing_proof" for finding in findings), findings)

    def test_small_runner_success_with_material_proof_passes(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            rel = "docs/code_reviews/260619_0032_small_runner_success.md"
            self._write_markdown(
                root,
                rel,
                dedent(
                    """\
                    # Код-ревью - small runner fixture

                    **Status:** draft

                    ## runner_quality
                    - runner_id: claude
                    - runner_result: completed focused helper slice
                    - small_runner_success: true
                    - frontier_intervention: false
                    - reviewer_runner_id: codex
                    - reviewer_lane: independent frontier contracts review
                    """
                ),
            )

            findings = self._small_runner_findings(root, rel)

        self.assertEqual(findings, [])

    def test_small_runner_success_with_explicit_na_proof_warns(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            rel = "docs/code_reviews/260619_0032_small_runner_explicit_na_proof.md"
            self._write_markdown(
                root,
                rel,
                dedent(
                    """\
                    # Код-ревью - small runner fixture

                    **Status:** draft

                    ## runner_quality
                    - runner_id: N/A (why=not exposed)
                    - runner_result: N/A (why=not exposed)
                    - small_runner_success: true
                    - frontier_intervention: false
                    - reviewer_lane: independent frontier contracts review
                    """
                ),
            )

            findings = self._small_runner_findings(root, rel)

        self.assertTrue(any(finding.code == "small_runner_success_missing_proof" for finding in findings), findings)

    def test_small_runner_unavailable_conflicts_with_success_claim(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            rel = "docs/code_reviews/260619_0032_small_runner_unavailable.md"
            self._write_markdown(
                root,
                rel,
                dedent(
                    """\
                    # Код-ревью - small runner fixture

                    **Status:** draft

                    ## runner_quality
                    - runner_admission: small_runner_ok
                    - runner_id: claude
                    - runner_result: inconclusive_runner_unavailable
                    - small_runner_success: false
                    - frontier_intervention: true
                    - reviewer_lane: frontier control review
                    """
                ),
            )

            findings = self._small_runner_findings(root, rel)

        self.assertTrue(
            any(finding.code == "small_runner_success_conflicts_with_red_evidence" for finding in findings),
            findings,
        )

    def test_small_runner_same_runner_reviewer_mismatch_warns(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            rel = "docs/code_reviews/260619_0032_small_runner_self_review.md"
            self._write_markdown(
                root,
                rel,
                dedent(
                    """\
                    # Код-ревью - small runner fixture

                    **Status:** draft

                    ## runner_quality
                    - runner_id: claude
                    - runner_result: completed focused helper slice
                    - small_runner_success: true
                    - frontier_intervention: false
                    - reviewer_runner_id: claude
                    - reviewer_lane: claude
                    """
                ),
            )

            findings = self._small_runner_findings(root, rel)

        self.assertTrue(any(finding.code == "small_runner_reviewer_lane_mismatch" for finding in findings), findings)

    def _single_commit_dual_lane_fixture(
        self,
        *,
        status: str = "✅ OK",
        target: str = "BUNDLE=staged",
        extra_sections: str = "",
        risk_findings: str | None = None,
        contracts_findings: str | None = None,
        canonical_mapping: str = "`none`",
        synthesis_provenance_records: str | None = None,
        include_default_no_findings_provenance: bool = True,
        exact_bundle_hygiene: bool = True,
    ) -> str:
        summary_line = self._russian_summary(status)
        hygiene_block = self._exact_bundle_hygiene_section() if exact_bundle_hygiene else ""
        body = f"""\
            # Code review — single commit

            **Date:** 29.03.2026 02:49 MSK
            **Target:** {target}
            **Status:** {status}

            {summary_line}
            {hygiene_block}
            {self._dual_lane_sections(target, aggregate_status=status, risk_findings=risk_findings, contracts_findings=contracts_findings, canonical_mapping=canonical_mapping, synthesis_provenance_records=synthesis_provenance_records, include_default_no_findings_provenance=include_default_no_findings_provenance)}
            {extra_sections}
            """
        prefix = " " * 12
        return "\n".join(line[len(prefix):] if line.startswith(prefix) else line for line in body.splitlines()) + "\n"

    def _russian_summary(self, status: str) -> str:
        if status.startswith("❌"):
            return "Замечания: fixture review artifact фиксирует blocker в русской summary-строке."
        return "ОК: fixture review artifact держит русскую summary-строку."

    def _with_first_summary(self, body: str, summary: str) -> str:
        default_summary = self._russian_summary("✅ OK")
        self.assertIn(f"\n{default_summary}\n", body)
        return body.replace(default_summary, summary, 1)

    def _exact_bundle_hygiene_section(self) -> str:
        return dedent(
            """\

            ## Exact bundle hygiene
            - Exact bundle hygiene: `git diff --check -- <exact bundle>` -> OK.
            - Untracked files check: `rg -n "^<<<<<<< |^======= |^>>>>>>> |[[:blank:]]$" <new files>` -> no matches.
            """
        )

    def _no_findings_synthesis_provenance_record(
        self,
        *,
        canonical_ref: str = "docs/code_reviews/260329_0248_example.md#Lane-synthesis--aggregate-verdict",
        audit_status: str = "pending_post_merge_audit",
    ) -> str:
        return dedent(
            f"""\
            ### Provenance records
            - Finding: `N/A (findings отсутствуют)`
              - source_lane: `reviewer_code_risk+reviewer_code_contracts`
              - lane_finding_id: `N/A (no lane findings)`
              - synthesis_disposition: `no_findings`
              - canonical_ref: `{canonical_ref}`
              - audit_status: `{audit_status}`
              - followup_plan: `N/A`
            """
        )

    def _complete_synthesis_provenance_record(
        self,
        *,
        finding: str = "contracts:C1",
        source_lane: str = "reviewer_code_contracts",
        canonical_ref: str = "docs/code_reviews/260329_0248_example.md#S2-Risk",
        disposition: str = "accepted_non_blocking_followup",
    ) -> str:
        return dedent(
            f"""\
            ### Provenance records
            - Finding: `{finding}`
              - source_lane: `{source_lane}`
              - lane_finding_id: `{finding}`
              - synthesis_disposition: `{disposition}`
              - canonical_ref: `{canonical_ref}`
              - audit_status: `pending_post_merge_audit`
              - followup_plan: `docs/plans/260329_0248_followup.md`
            """
        )

    def _green_merge_range_fixture(self) -> str:
        return dedent(
            f"""\
            # Code review — merge-range (abc1234..def5678)

            **Date:** 29.03.2026 02:45 MSK
            **Range:** BASE=abc1234 .. HEAD=def5678
            **Status:** ✅ OK

            {self._russian_summary("✅ OK")}

            ## Exact bundle hygiene
            - Exact bundle hygiene: `git diff --check abc1234..def5678` -> OK.
            - Untracked files check: `git status --porcelain --untracked-files=all` -> no untracked files.

            ## reviewer_code_risk - GPT-5.5 xhigh
            - Lane status: `complete`
            - Target snapshot: `BASE=abc1234 .. HEAD=def5678`
            - Coverage domains: `correctness`, `tests quality`, `security/privacy`
            - No findings reason: `N/A (no risk findings)`

            ## reviewer_code_contracts - GPT-5.5 xhigh
            - Lane status: `complete`
            - Target snapshot: `BASE=abc1234 .. HEAD=def5678`
            - Coverage domains: `plan fidelity`, `architecture/design fit`, `docs/registry`
            - No findings reason: `N/A (no contracts findings)`

            ## Lane synthesis / aggregate verdict
            - Source lanes: `reviewer_code_risk`, `reviewer_code_contracts`
            - Canonical mapping: `none`
            - Aggregate status: `✅ OK`
            {self._no_findings_synthesis_provenance_record(canonical_ref="docs/code_reviews/260329_0245_green_merge_range.md#Lane-synthesis--aggregate-verdict")}

            ## Контекст rerun
            - Rerun mode: `full`
            - Baseline artifact: `docs/code_reviews/260328_1200_example.md`
            - Rerun scope: полный rerun

            ## S1 Blocker
            ### B1
            - Blocker ID: B1
            - Current state: open
            - Classification: same-contract reroute
            - Primary owner gap: Coder
            - Evidence refs: `docs/code_reviews/260329_0245_green_merge_range.md#B1`

            ## Визуальные доказательства
            - Visual env: `Modes=primary` `Port=8054`
            - Source scenarios: `docs/plans/260329_0245_green_merge_range.md#visual`
            - Post-merge visual sanity: `scenario -> primary -> screenshot -> OK`
            """
        )

    def _merge_range_dual_lane_fixture(
        self,
        *,
        target: str = "RANGE=abc1234..def5678 (EXCLUDE_DOCS=0)",
        spec: str | None = "docs/plans/260329_0248_origin.md",
        include_target: bool = True,
        include_range: bool = False,
        status: str = "✅ OK",
        exact_bundle_hygiene: bool = True,
    ) -> str:
        headers = ["**Date:** 29.03.2026 02:49 MSK"]
        if include_range:
            headers.append("**Range:** BASE=abc1234 .. HEAD=def5678")
        if include_target:
            headers.append(f"**Target:** {target}")
        if spec is not None:
            headers.append(f"**Spec:** {spec}")
        headers.append(f"**Status:** {status}")
        header_block = "\n".join(headers)
        hygiene_block = (
            "## Exact bundle hygiene\n"
            "- Exact bundle hygiene: `git diff --check abc1234..def5678` -> OK.\n"
            "- Untracked files check: `git status --porcelain --untracked-files=all` -> no untracked files.\n"
            if exact_bundle_hygiene
            else ""
        )
        return dedent(
            f"""\
            # Code review — merge-range (abc1234..def5678)

            {header_block}

            {self._russian_summary(status)}

            {hygiene_block}
            ## Контекст rerun
            - Rerun mode: `N/A (first pass)`
            - Baseline artifact: `N/A (first pass)`

            {self._dual_lane_sections(target, aggregate_status=status)}
            """
        )

    def test_green_merge_range_fixture_passes(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(root, "docs/code_reviews/260329_0245_green_merge_range.md", self._green_merge_range_fixture())

            findings = MODULE.lint_review_artifacts(self._load_single(root, "docs/code_reviews/260329_0245_green_merge_range.md"))

        self.assertEqual(findings, [])

    def test_code_review_rejects_merge_notes_done_status(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/code_reviews/260619_0211_wrong_status_family.md",
                self._single_commit_dual_lane_fixture(status="✅ Done"),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260619_0211_wrong_status_family.md")
            )

        self.assertEqual([finding.code for finding in findings], ["invalid_review_status_family"])
        self.assertIn("merge-notes statuses", findings[0].message)

    def test_code_review_rejects_non_template_placeholder_status(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/code_reviews/260619_0211_placeholder_status.md",
                self._single_commit_dual_lane_fixture(status="Черновик | ✅ OK | ❌ S1 blocker(ы)"),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260619_0211_placeholder_status.md")
            )

        self.assertEqual([finding.code for finding in findings], ["invalid_review_status_family"])
        self.assertIn("only valid in `_template_*` files", findings[0].message)

    def test_retrieval_backed_review_requires_telemetry_receipt(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0245_retrieval_missing.md",
                self._single_commit_dual_lane_fixture(
                    extra_sections=dedent(
                        """\
                        ## Reviewer notes
                        - Evidence used `planveyor_docs_retrieve` for the contract lookup.
                        """
                    )
                ),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260329_0245_retrieval_missing.md")
            )

        self.assertIn("missing_retrieval_telemetry_receipt", {finding.code for finding in findings})

    def test_retrieval_backed_review_accepts_valid_telemetry_receipt(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0245_retrieval_valid.md",
                self._single_commit_dual_lane_fixture(
                    extra_sections=dedent(
                        """\
                        ## Reviewer notes
                        - Evidence used `planveyor_docs_retrieve` for the contract lookup.

                        ## Retrieval telemetry receipt
                        - query_event_id: `20260511T120000Z-abcd123456-12345678`
                        - used_for_decision: `true`
                        - read_open: `ok`
                        - read_log_status: `present`
                        - read_event_id: `read-20260511T120001Z-12345678`
                        - outcome: `used`
                        - outcome_reason: used for review contract lookup.
                        - cited/opened files: `docs/tools/snippet.md`
                        """
                    )
                ),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260329_0245_retrieval_valid.md")
            )

        self.assertNotIn("missing_retrieval_telemetry_receipt", {finding.code for finding in findings})
        self.assertNotIn("invalid_retrieval_telemetry_receipt", {finding.code for finding in findings})

    def test_missing_rerun_field_is_reported(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0246_missing_rerun.md",
                self._green_merge_range_fixture().replace("- Baseline artifact: `docs/code_reviews/260328_1200_example.md`\n", ""),
            )

            findings = MODULE.lint_review_artifacts(self._load_single(root, "docs/code_reviews/260329_0246_missing_rerun.md"))

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "missing_rerun_fields")
        self.assertIn("baseline artifact", findings[0].message)

    def test_single_commit_rerun_section_without_fields_is_reported(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0246_empty_rerun.md",
                self._single_commit_dual_lane_fixture(
                    extra_sections=dedent(
                        """\
                        ## Контекст rerun
                        - Note: rerun requested by the owner.
                        """
                    )
                ),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260329_0246_empty_rerun.md")
            )

        self.assertEqual([finding.code for finding in findings], ["missing_rerun_fields"])
        self.assertIn("rerun mode", findings[0].message)
        self.assertIn("baseline artifact", findings[0].message)

    def test_missing_blocker_field_is_reported(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0247_missing_blocker.md",
                self._green_merge_range_fixture().replace("- Evidence refs: `docs/code_reviews/260329_0245_green_merge_range.md#B1`\n", ""),
            )

            findings = MODULE.lint_review_artifacts(self._load_single(root, "docs/code_reviews/260329_0247_missing_blocker.md"))

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "missing_blocker_fields")
        self.assertIn("B1", findings[0].message)
        self.assertIn("evidence refs", findings[0].message)

    def test_missing_visual_field_is_reported(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0248_missing_visual.md",
                self._green_merge_range_fixture().replace("- Post-merge visual sanity: `scenario -> primary -> screenshot -> OK`\n", ""),
            )

            findings = MODULE.lint_review_artifacts(self._load_single(root, "docs/code_reviews/260329_0248_missing_visual.md"))

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "missing_visual_receipt_fields")
        self.assertIn("post-merge visual sanity", findings[0].message)

    def test_final_status_without_risk_lane_is_reported(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            body = self._single_commit_dual_lane_fixture().replace("## reviewer_code_risk - GPT-5.5 xhigh\n", "## removed_lane\n", 1)
            body = body.replace("- Lane status: `complete`\n- Target snapshot: `BUNDLE=staged`\n- Coverage domains: `correctness`, `tests quality`, `security/privacy`\n- No findings reason: `N/A (no risk findings)`\n\n", "", 1)
            self._write_markdown(root, "docs/code_reviews/260329_0248_missing_risk_lane.md", body)

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260329_0248_missing_risk_lane.md")
            )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "missing_final_lane_sections")
        self.assertIn("reviewer_code_risk", findings[0].message)

    def test_final_status_without_contracts_lane_is_reported(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            body = self._single_commit_dual_lane_fixture().replace("## reviewer_code_contracts - GPT-5.5 xhigh\n", "## removed_lane\n", 1)
            body = body.replace("- Lane status: `complete`\n- Target snapshot: `BUNDLE=staged`\n- Coverage domains: `plan fidelity`, `architecture/design fit`, `docs/registry`\n- No findings reason: `N/A (no contracts findings)`\n\n", "", 1)
            self._write_markdown(root, "docs/code_reviews/260329_0248_missing_contracts_lane.md", body)

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260329_0248_missing_contracts_lane.md")
            )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "missing_final_lane_sections")
        self.assertIn("reviewer_code_contracts", findings[0].message)

    def test_final_status_without_synthesis_is_reported(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            body = self._single_commit_dual_lane_fixture()
            body = body[: body.index("## Lane synthesis / aggregate verdict")]
            self._write_markdown(root, "docs/code_reviews/260329_0248_missing_synthesis.md", body)

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260329_0248_missing_synthesis.md")
            )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "missing_final_lane_sections")
        self.assertIn("lane synthesis / aggregate verdict", findings[0].message)

    def test_final_status_with_lane_finding_requires_synthesis_provenance_fields(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0248_missing_provenance.md",
                self._single_commit_dual_lane_fixture(
                    contracts_findings=(
                        "`contracts:C1 severity=S2 domain=review artifact truthfulness "
                        "summary=missing carrier evidence=review.md#contracts`"
                    ),
                    canonical_mapping="`contracts:C1 -> accepted-risk`",
                    synthesis_provenance_records=dedent(
                        """\
                        ### Provenance records
                        - Finding: `contracts:C1`
                          - source_lane: `reviewer_code_contracts`
                          - lane_finding_id: `contracts:C1`
                          - synthesis_disposition: `accepted_non_blocking_followup`
                          - canonical_ref: `docs/code_reviews/260329_0248_missing_provenance.md#S2-Risk`
                          - audit_status: `pending_post_merge_audit`
                        """
                    ),
                ),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260329_0248_missing_provenance.md")
            )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "missing_final_synthesis_provenance_fields")
        self.assertIn("followup_plan", findings[0].message)

    def test_final_status_with_lane_finding_and_complete_synthesis_provenance_passes(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0248_complete_provenance.md",
                self._single_commit_dual_lane_fixture(
                    contracts_findings=(
                        "`contracts:C1 severity=S2 domain=review artifact truthfulness "
                        "summary=complete carrier evidence=review.md#contracts`"
                    ),
                    canonical_mapping="`contracts:C1 -> accepted-risk`",
                    synthesis_provenance_records=self._complete_synthesis_provenance_record(
                        canonical_ref="docs/code_reviews/260329_0248_complete_provenance.md#S2-Risk"
                    ),
                ),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260329_0248_complete_provenance.md")
            )

        self.assertEqual(findings, [])

    def test_final_no_findings_status_requires_synthesis_provenance_fields(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0248_no_findings_missing_provenance.md",
                self._single_commit_dual_lane_fixture(include_default_no_findings_provenance=False),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260329_0248_no_findings_missing_provenance.md")
            )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "missing_final_synthesis_provenance_fields")
        self.assertIn("source_lane", findings[0].message)
        self.assertIn("followup_plan", findings[0].message)

    def test_final_no_findings_status_rejects_legacy_placeholder_provenance_values(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0248_no_findings_legacy_provenance.md",
                self._single_commit_dual_lane_fixture(
                    synthesis_provenance_records=dedent(
                        """\
                        ### Provenance records
                        - Finding: `N/A (findings отсутствуют)`
                          - source_lane: `N/A`
                          - lane_finding_id: `N/A`
                          - synthesis_disposition: `N/A (findings отсутствуют)`
                          - canonical_ref: `N/A (findings отсутствуют)`
                          - audit_status: `N/A`
                          - followup_plan: `N/A`
                        """
                    ),
                ),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260329_0248_no_findings_legacy_provenance.md")
            )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "invalid_final_no_findings_provenance")
        self.assertIn("source_lane", findings[0].message)
        self.assertIn("synthesis_disposition", findings[0].message)

    def test_final_no_findings_status_with_complete_synthesis_provenance_passes(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0248_no_findings_complete_provenance.md",
                self._single_commit_dual_lane_fixture(
                    synthesis_provenance_records=self._no_findings_synthesis_provenance_record(
                        canonical_ref=(
                            "docs/code_reviews/260329_0248_no_findings_complete_provenance.md"
                            "#Lane-synthesis--aggregate-verdict"
                        ),
                        audit_status="done",
                    ),
                ),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260329_0248_no_findings_complete_provenance.md")
            )

        self.assertEqual(findings, [])

    def test_current_final_review_rejects_english_first_summary(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            body = self._with_first_summary(
                self._single_commit_dual_lane_fixture(),
                "OK: English verdict prose is not the current review summary carrier.",
            )
            self._write_markdown(root, "docs/code_reviews/260517_1308_current_english_summary.md", body)

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260517_1308_current_english_summary.md")
            )

        self.assertIn("invalid_russian_first_summary", {finding.code for finding in findings})

    def test_current_final_review_requires_exact_bundle_hygiene_receipt(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            body = self._with_first_summary(
                self._single_commit_dual_lane_fixture(exact_bundle_hygiene=False),
                "ОК: текущий review artifact держит русскую summary-строку.",
            )
            self._write_markdown(root, "docs/code_reviews/260517_1308_current_missing_hygiene.md", body)

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260517_1308_current_missing_hygiene.md")
            )

        self.assertIn("missing_exact_bundle_hygiene_receipt", {finding.code for finding in findings})

    def test_current_final_review_accepts_russian_summary_and_exact_bundle_hygiene(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            body = self._with_first_summary(
                self._single_commit_dual_lane_fixture(),
                "ОК: текущий review artifact держит русскую summary-строку и exact-bundle hygiene receipt.",
            )
            self._write_markdown(root, "docs/code_reviews/260517_1308_current_complete_hygiene.md", body)

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260517_1308_current_complete_hygiene.md")
            )

        self.assertEqual(findings, [])

    def test_current_final_review_rejects_expanded_homebrew_command_evidence(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            body = self._with_first_summary(
                self._single_commit_dual_lane_fixture(
                    extra_sections=dedent(
                        f"""\

                        ## Команды / evidence
                        - Command: `{self._homebrew_pybin_literal()} -B scripts/test_review_artifact_lint.py`
                        """
                    )
                ),
                "ОК: текущий review artifact держит русскую summary-строку и exact-bundle hygiene receipt.",
            )
            self._write_markdown(root, "docs/code_reviews/260517_1308_current_homebrew_command.md", body)

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260517_1308_current_homebrew_command.md")
            )

        self.assertIn("expanded_homebrew_python_command_evidence", {finding.code for finding in findings})

    def test_current_final_review_accepts_portable_command_evidence(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            body = self._with_first_summary(
                self._single_commit_dual_lane_fixture(
                    extra_sections=dedent(
                        """\

                        ## Команды / evidence
                        - Command: `$PYBIN -B scripts/test_review_artifact_lint.py`
                        - Command: `python3 scripts/review_artifact_lint.py docs/code_reviews/sample.md`
                        """
                    )
                ),
                "ОК: текущий review artifact держит русскую summary-строку и exact-bundle hygiene receipt.",
            )
            self._write_markdown(root, "docs/code_reviews/260517_1308_current_portable_command.md", body)

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260517_1308_current_portable_command.md")
            )

        self.assertEqual(findings, [])

    def test_older_dated_final_review_gets_summary_and_hygiene_guards(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            body = self._with_first_summary(
                self._single_commit_dual_lane_fixture(exact_bundle_hygiene=False),
                "OK: an older filename date no longer exempts English verdict prose.",
            )
            self._write_markdown(root, "docs/code_reviews/260517_1307_historical_english_summary.md", body)

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260517_1307_historical_english_summary.md")
            )

        current_guard_codes = {"invalid_russian_first_summary", "missing_exact_bundle_hygiene_receipt"}
        self.assertEqual(current_guard_codes, current_guard_codes.intersection({finding.code for finding in findings}))

    def test_review_guards_do_not_depend_on_filename_date(self) -> None:
        body = self._with_first_summary(
            self._single_commit_dual_lane_fixture(exact_bundle_hygiene=False),
            "OK: English verdict prose without an exact-bundle hygiene receipt.",
        )
        names = ("260928_1200_x.md", "250101_1200_x.md", "x-nonstandard.md", "my_review.md")
        guard_codes = {"invalid_russian_first_summary", "missing_exact_bundle_hygiene_receipt"}
        for review_dir in ("docs/code_reviews", "docs/doc_reviews"):
            with self.subTest(review_dir=review_dir), temporary_git_root() as tmpdir:
                root = Path(tmpdir).resolve()
                findings_by_name: dict[str, list[tuple[int, str, str]]] = {}
                for name in names:
                    rel_path = f"{review_dir}/{name}"
                    self._write_markdown(root, rel_path, body)
                    findings = MODULE.lint_review_artifacts(self._load_single(root, rel_path), project_root=root)
                    findings_by_name[name] = sorted(
                        (finding.line_no, finding.code, finding.message) for finding in findings
                    )
                    self.assertTrue(
                        guard_codes.issubset({finding.code for finding in findings}),
                        (rel_path, findings),
                    )
                reference = findings_by_name[names[0]]
                for name in names[1:]:
                    self.assertEqual(findings_by_name[name], reference, name)

    def test_template_review_stays_outside_current_guards(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            body = self._with_first_summary(
                self._single_commit_dual_lane_fixture(exact_bundle_hygiene=False),
                "OK: template carriers keep placeholder prose.",
            )
            rel_path = "docs/code_reviews/_template_code_review_fixture.md"
            self._write_markdown(root, rel_path, body)

            findings = MODULE.lint_review_artifacts(self._load_single(root, rel_path), project_root=root)

        guard_codes = {"invalid_russian_first_summary", "missing_exact_bundle_hygiene_receipt"}
        self.assertFalse(guard_codes.intersection({finding.code for finding in findings}), findings)

    def test_final_dual_lane_requires_explicit_origin_plan(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0248_missing_origin.md",
                self._single_commit_dual_lane_fixture(),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260329_0248_missing_origin.md"),
                project_root=root,
                require_dual_lane_origin=True,
            )

        self.assertTrue(any(finding.code == "missing_dual_lane_origin_plan" for finding in findings), findings)

    def test_final_merge_range_requires_explicit_target_carrier(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260329_0248_origin.md"
            target = "RANGE=abc1234..def5678 (EXCLUDE_DOCS=0)"
            self._write_origin_plan(root, plan_rel, target_snapshot=target)
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0248_merge_range_missing_target.md",
                self._merge_range_dual_lane_fixture(
                    target=target,
                    spec=plan_rel,
                    include_target=False,
                    include_range=True,
                ) + f"\n```text\n**Target:** {target}\n```\n",
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260329_0248_merge_range_missing_target.md"),
                project_root=root,
                require_dual_lane_origin=True,
            )

        self.assertTrue(any(finding.code == "missing_review_target_snapshot" for finding in findings), findings)

    def test_final_merge_range_requires_spec_carrier(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            target = "RANGE=abc1234..def5678 (EXCLUDE_DOCS=0)"
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0248_merge_range_missing_spec.md",
                self._merge_range_dual_lane_fixture(target=target, spec=None),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260329_0248_merge_range_missing_spec.md"),
                project_root=root,
                require_dual_lane_origin=True,
            )

        self.assertTrue(any(finding.code == "missing_review_spec" for finding in findings), findings)

    def test_final_merge_range_rejects_invalid_spec_carrier(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            target = "RANGE=abc1234..def5678 (EXCLUDE_DOCS=0)"
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0248_merge_range_invalid_spec.md",
                self._merge_range_dual_lane_fixture(
                    target=target,
                    spec="N/A (why=origin plan was not provided)",
                ),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260329_0248_merge_range_invalid_spec.md"),
                project_root=root,
                require_dual_lane_origin=True,
            )

        self.assertTrue(any(finding.code == "invalid_review_spec" for finding in findings), findings)

    def test_final_merge_range_accepts_spec_origin_plan_target_snapshot(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260329_0248_origin.md"
            target = "RANGE=abc1234..def5678 (EXCLUDE_DOCS=0)"
            self._write_origin_plan(root, plan_rel, target_snapshot=target)
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0248_merge_range_spec_match.md",
                self._merge_range_dual_lane_fixture(target=target, spec=plan_rel),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260329_0248_merge_range_spec_match.md"),
                project_root=root,
                require_dual_lane_origin=True,
            )

        self.assertEqual(findings, [])

    def test_final_merge_range_accepts_manual_no_origin_spec(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0248_merge_range_manual_no_origin.md",
                self._merge_range_dual_lane_fixture(
                    spec="N/A (origin_plan_state=manual_range_review_no_origin_plan)",
                ),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260329_0248_merge_range_manual_no_origin.md"),
                project_root=root,
                require_dual_lane_origin=True,
            )

        self.assertEqual(findings, [])

    def test_final_merge_range_rejects_manual_no_origin_with_origin_plan_argument(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260329_0248_origin.md"
            self._write_origin_plan(root, plan_rel, target_snapshot="RANGE=abc1234..def5678 (EXCLUDE_DOCS=0)")
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0248_merge_range_manual_no_origin_with_plan.md",
                self._merge_range_dual_lane_fixture(
                    spec="N/A (origin_plan_state=manual_range_review_no_origin_plan)",
                ),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260329_0248_merge_range_manual_no_origin_with_plan.md"),
                project_root=root,
                origin_plan=plan_rel,
                require_dual_lane_origin=True,
            )

        self.assertTrue(any(finding.code == "manual_no_origin_with_origin_plan" for finding in findings), findings)

    def test_final_dual_lane_rejects_missing_plan_resident_risk_lane(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260329_0248_origin.md"
            self._write_origin_plan(root, plan_rel, target_snapshot=None)
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0248_missing_plan_lane.md",
                self._single_commit_dual_lane_fixture(target="BUNDLE=staged"),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260329_0248_missing_plan_lane.md"),
                project_root=root,
                origin_plan=plan_rel,
                require_dual_lane_origin=True,
            )

        self.assertTrue(any(finding.code == "missing_plan_resident_risk_lane" for finding in findings), findings)

    def test_final_dual_lane_rejects_mismatched_plan_target_snapshot(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260329_0248_origin.md"
            self._write_origin_plan(root, plan_rel, target_snapshot="BUNDLE=current")
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0248_snapshot_mismatch.md",
                self._single_commit_dual_lane_fixture(target="BUNDLE=staged"),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260329_0248_snapshot_mismatch.md"),
                project_root=root,
                origin_plan=plan_rel,
                require_dual_lane_origin=True,
            )

        self.assertTrue(any(finding.code == "dual_lane_target_snapshot_mismatch" for finding in findings), findings)

    def test_final_dual_lane_accepts_matching_origin_plan_target_snapshot(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260329_0248_origin.md"
            self._write_origin_plan(root, plan_rel, target_snapshot="BUNDLE=staged")
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0248_snapshot_match.md",
                self._single_commit_dual_lane_fixture(target="BUNDLE=staged"),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260329_0248_snapshot_match.md"),
                project_root=root,
                origin_plan=plan_rel,
                require_dual_lane_origin=True,
            )

        self.assertEqual(findings, [])

    def test_final_dual_lane_rejects_homebrew_command_in_plan_risk_lane(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260329_0248_origin.md"
            self._write_origin_plan_payloads(
                root,
                plan_rel,
                [
                    {
                        "run_id": "reviewer_code_risk:sample:20260616T1956MSK",
                        "lane_id": "reviewer_code_risk",
                        "target_snapshot": "BUNDLE=staged",
                        "lane_status": "complete",
                        "findings": [],
                        "verification": [
                            {
                                "command": f"{self._homebrew_pybin_literal()} -B scripts/test_review_artifact_lint.py",
                                "exit_code": 0,
                            }
                        ],
                        "current": True,
                    },
                ],
            )
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0248_risk_lane_homebrew_command.md",
                self._single_commit_dual_lane_fixture(target="BUNDLE=staged"),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260329_0248_risk_lane_homebrew_command.md"),
                project_root=root,
                origin_plan=plan_rel,
                require_dual_lane_origin=True,
            )

        self.assertIn("expanded_homebrew_python_command_evidence", {finding.code for finding in findings})

    def test_final_dual_lane_accepts_portable_command_in_plan_risk_lane(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260329_0248_origin.md"
            self._write_origin_plan_payloads(
                root,
                plan_rel,
                [
                    {
                        "run_id": "reviewer_code_risk:sample:20260616T1956MSK",
                        "lane_id": "reviewer_code_risk",
                        "target_snapshot": "BUNDLE=staged",
                        "lane_status": "complete",
                        "findings": [],
                        "verification": [
                            {
                                "command": "$PYBIN -B scripts/test_review_artifact_lint.py",
                                "exit_code": 0,
                            }
                        ],
                        "current": True,
                    },
                ],
            )
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0248_risk_lane_portable_command.md",
                self._single_commit_dual_lane_fixture(target="BUNDLE=staged"),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260329_0248_risk_lane_portable_command.md"),
                project_root=root,
                origin_plan=plan_rel,
                require_dual_lane_origin=True,
            )

        self.assertEqual(findings, [])

    def test_final_dual_lane_selects_latest_risk_snapshot_stale_first(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260329_0248_origin.md"
            self._write_origin_plan_payloads(
                root,
                plan_rel,
                [
                    {
                        "run_id": "rcr-20260616-1953MSK-01",
                        "lane_id": "reviewer_code_risk",
                        "target_snapshot": "BUNDLE=stale",
                        "lane_status": "complete",
                        "written_at": "2026-06-16 19:53 MSK",
                    },
                    {
                        "run_id": "rcr-20260616-1956MSK-02",
                        "lane_id": "reviewer_code_risk",
                        "target_snapshot": "BUNDLE=fresh",
                        "lane_status": "complete",
                        "written_at": "2026-06-16 19:56 MSK",
                    },
                ],
            )
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0248_latest_snapshot.md",
                self._single_commit_dual_lane_fixture(target="BUNDLE=fresh"),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260329_0248_latest_snapshot.md"),
                project_root=root,
                origin_plan=plan_rel,
                require_dual_lane_origin=True,
            )

        self.assertEqual(findings, [])

    def test_final_dual_lane_selects_latest_risk_snapshot_when_fresh_is_first_in_text(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260329_0248_origin.md"
            self._write_origin_plan_payloads(
                root,
                plan_rel,
                [
                    {
                        "run_id": "reviewer_code_risk:sample:20260616T1956MSK",
                        "lane_id": "reviewer_code_risk",
                        "target_snapshot": "BUNDLE=fresh",
                        "lane_status": "complete",
                        "written_at": "2026-06-16 19:56 MSK",
                    },
                    {
                        "run_id": "reviewer_code_risk:sample:20260616T1953MSK",
                        "lane_id": "reviewer_code_risk",
                        "target_snapshot": "BUNDLE=stale",
                        "lane_status": "complete",
                        "written_at": "2026-06-16 19:53 MSK",
                    },
                ],
            )
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0248_latest_snapshot_text_order.md",
                self._single_commit_dual_lane_fixture(target="BUNDLE=fresh"),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260329_0248_latest_snapshot_text_order.md"),
                project_root=root,
                origin_plan=plan_rel,
                require_dual_lane_origin=True,
            )

        self.assertEqual(findings, [])

    def test_final_dual_lane_selects_latest_risk_snapshot_by_run_id_fallback(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260329_0248_origin.md"
            self._write_origin_plan_payloads(
                root,
                plan_rel,
                [
                    {
                        "run_id": "reviewer_code_risk:sample:20260616T1953MSK",
                        "lane_id": "reviewer_code_risk",
                        "target_snapshot": "BUNDLE=stale",
                        "lane_status": "complete",
                    },
                    {
                        "run_id": "reviewer_code_risk:sample:20260616T1956MSK",
                        "lane_id": "reviewer_code_risk",
                        "target_snapshot": "BUNDLE=fresh",
                        "lane_status": "complete",
                    },
                ],
            )
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0248_latest_snapshot_run_id.md",
                self._single_commit_dual_lane_fixture(target="BUNDLE=fresh"),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260329_0248_latest_snapshot_run_id.md"),
                project_root=root,
                origin_plan=plan_rel,
                require_dual_lane_origin=True,
            )

        self.assertEqual(findings, [])

    def test_risk_lane_selector_rejects_malformed_written_at_instead_of_run_id_fallback(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260329_0248_origin.md"
            plan_path = self._write_origin_plan_payloads(
                root,
                plan_rel,
                [
                    {
                        "run_id": "reviewer_code_risk:sample:20260616T195300Z",
                        "lane_id": "reviewer_code_risk",
                        "target_snapshot": "BUNDLE=stale",
                        "lane_status": "complete",
                        "written_at": "2026-06-16T19:53:00Z",
                    },
                    {
                        "run_id": "reviewer_code_risk:sample:20260616T200000Z",
                        "lane_id": "reviewer_code_risk",
                        "target_snapshot": "BUNDLE=must-not-select",
                        "lane_status": "complete",
                        "written_at": "UTC+14:00 2026-06-16T20:00:00",
                    },
                ],
            )

            selection = MODULE.select_plan_risk_lane_snapshot(plan_path)

        self.assertEqual(selection.error_code, "ambiguous_plan_resident_risk_lane")
        self.assertIn("missing sortable `written_at` / `run_id`", selection.message or "")

    def test_final_dual_lane_prefers_explicit_current_risk_snapshot(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260329_0248_origin.md"
            self._write_origin_plan_payloads(
                root,
                plan_rel,
                [
                    {
                        "run_id": "rcr-20260616-1956MSK-02",
                        "lane_id": "reviewer_code_risk",
                        "target_snapshot": "BUNDLE=fresh",
                        "lane_status": "complete",
                        "current": True,
                        "written_at": "2026-06-16 19:56 MSK",
                    },
                    {
                        "run_id": "rcr-20260616-2000MSK-03",
                        "lane_id": "reviewer_code_risk",
                        "target_snapshot": "BUNDLE=stale",
                        "lane_status": "complete",
                        "written_at": "2026-06-16 20:00 MSK",
                    },
                ],
            )
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0248_explicit_current.md",
                self._single_commit_dual_lane_fixture(target="BUNDLE=fresh"),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260329_0248_explicit_current.md"),
                project_root=root,
                origin_plan=plan_rel,
                require_dual_lane_origin=True,
            )

        self.assertEqual(findings, [])

    def test_final_dual_lane_rejects_ambiguous_unmarked_risk_snapshots(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260329_0248_origin.md"
            self._write_origin_plan_payloads(
                root,
                plan_rel,
                [
                    {
                        "lane_id": "reviewer_code_risk",
                        "target_snapshot": "BUNDLE=first",
                        "lane_status": "complete",
                    },
                    {
                        "lane_id": "reviewer_code_risk",
                        "target_snapshot": "BUNDLE=second",
                        "lane_status": "complete",
                    },
                ],
            )
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0248_ambiguous_plan_lane.md",
                self._single_commit_dual_lane_fixture(target="BUNDLE=second"),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260329_0248_ambiguous_plan_lane.md"),
                project_root=root,
                origin_plan=plan_rel,
                require_dual_lane_origin=True,
            )

        self.assertTrue(any(finding.code == "ambiguous_plan_resident_risk_lane" for finding in findings), findings)

    def test_public_risk_lane_selector_returns_current_snapshot(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260329_0248_origin.md"
            plan_path = self._write_origin_plan_payloads(
                root,
                plan_rel,
                [
                    {
                        "lane_id": "reviewer_code_risk",
                        "target_snapshot": "BUNDLE=stale",
                        "lane_status": "complete",
                        "current": False,
                        "written_at": "2026-06-16 20:00 MSK",
                    },
                    {
                        "lane_id": "reviewer_code_risk",
                        "target_snapshot": "BUNDLE=fresh",
                        "lane_status": "complete",
                        "current": True,
                        "written_at": "2026-06-16 19:56 MSK",
                    },
                ],
            )

            selection = MODULE.select_plan_risk_lane_snapshot(plan_path)

        self.assertIsNone(selection.error_code)
        self.assertEqual(selection.snapshot, "BUNDLE=fresh")

    def test_risk_lane_selector_reexports_plan_lint_for_selected_missing_and_ambiguous(self) -> None:
        self.assertIs(MODULE.PlanRiskLaneCandidate, plan_lint.PlanRiskLaneCandidate)
        self.assertIs(MODULE.PlanRiskLaneSelection, plan_lint.PlanRiskLaneSelection)
        self.assertIs(MODULE.select_plan_risk_lane_snapshot, plan_lint.select_plan_risk_lane_snapshot)

        fixtures = {
            "selected": [
                {
                    "run_id": "reviewer_code_risk:sample:20260616T1956MSK",
                    "lane_id": "reviewer_code_risk",
                    "target_snapshot": "BUNDLE=fresh",
                    "lane_status": "complete",
                    "current": True,
                }
            ],
            "missing": None,
            "ambiguous": [
                {
                    "lane_id": "reviewer_code_risk",
                    "target_snapshot": "BUNDLE=first",
                    "lane_status": "complete",
                },
                {
                    "lane_id": "reviewer_code_risk",
                    "target_snapshot": "BUNDLE=second",
                    "lane_status": "complete",
                },
            ],
        }
        for name, payloads in fixtures.items():
            with self.subTest(name=name), temporary_git_root() as tmpdir:
                root = Path(tmpdir).resolve()
                plan_rel = "docs/plans/260329_0248_origin.md"
                if payloads is None:
                    plan_path = self._write_origin_plan(root, plan_rel, target_snapshot=None)
                else:
                    plan_path = self._write_origin_plan_payloads(root, plan_rel, payloads)

                self.assertEqual(
                    MODULE.select_plan_risk_lane_snapshot(plan_path),
                    plan_lint.select_plan_risk_lane_snapshot(plan_path),
                )

    def test_select_risk_lane_cli_returns_selected_json(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260329_0248_origin.md"
            self._write_origin_plan_payloads(
                root,
                plan_rel,
                [
                    {
                        "run_id": "reviewer_code_risk:sample:20260616T1953MSK",
                        "lane_id": "reviewer_code_risk",
                        "target_snapshot": "BUNDLE=stale",
                        "lane_status": "complete",
                        "written_at": "2026-06-16 19:53 MSK",
                    },
                    {
                        "run_id": "reviewer_code_risk:sample:20260616T1956MSK",
                        "lane_id": "reviewer_code_risk",
                        "target_snapshot": "BUNDLE=fresh",
                        "lane_status": "complete",
                        "written_at": "2026-06-16 19:56 MSK",
                    },
                ],
            )
            stdout = io.StringIO()

            with mock.patch("sys.stdout", stdout):
                result = MODULE.main(
                    [
                        "--project-root",
                        str(root),
                        "--select-risk-lane",
                        "--origin-plan",
                        plan_rel,
                        "--json",
                    ]
                )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(result, 0)
        self.assertEqual(payload["schema_version"], "reviewer_risk_lane_selection.v1")
        self.assertEqual(payload["state"], "selected")
        self.assertEqual(payload["origin_plan"], plan_rel)
        self.assertIsInstance(payload["selected_line"], int)
        self.assertEqual(payload["run_id"], "reviewer_code_risk:sample:20260616T1956MSK")
        self.assertEqual(payload["target_snapshot"], "BUNDLE=fresh")
        self.assertIn("latest sortable", payload["reason"])
        self.assertIsNone(payload["error_code"])

    def test_select_risk_lane_cli_preflights_referenced_support_before_selected(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260811_0004_origin.md"
            support_payload = {
                "run_id": "reviewer_code_risk:sample:20260811T150000Z",
                "lane_id": "reviewer_code_risk",
                "target_snapshot": "BUNDLE=staged",
                "lane_status": "no_findings",
                "findings": [],
                "current": True,
            }
            support_rel, support_sha = self._write_support_payload(
                root,
                "docs/code_reviews/assets/260811_0004_origin/full_payload.json",
                support_payload,
            )
            compact_payload = {
                **support_payload,
                "full_payload_ref": support_rel,
                "full_payload_sha256": support_sha,
            }
            plan_path = self._write_origin_plan_payloads(root, plan_rel, [compact_payload])
            before_plan = plan_path.read_bytes()
            before_support = (root / support_rel).read_bytes()
            stdout = io.StringIO()
            previous_cwd = Path.cwd()
            try:
                os.chdir(Path(tmpdir).parent)
                with mock.patch("sys.stdout", stdout):
                    result = MODULE.main(
                        [
                            "--project-root",
                            str(root),
                            "--select-risk-lane",
                            "--origin-plan",
                            plan_rel,
                            "--json",
                        ]
                    )
            finally:
                os.chdir(previous_cwd)
            inputs_unchanged = (
                plan_path.read_bytes() == before_plan and (root / support_rel).read_bytes() == before_support
            )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(result, 0)
        self.assertEqual(payload["state"], "selected")
        self.assertEqual(payload["run_id"], support_payload["run_id"])
        self.assertTrue(inputs_unchanged)

    def test_select_risk_lane_cli_blocks_referenced_support_and_clears_identity(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260811_0004_red_support.md"
            support_payload = {
                "run_id": "reviewer_code_risk:sample:20260811T150000Z",
                "lane_id": "reviewer_code_risk",
                "target_snapshot": "BUNDLE=staged",
                "lane_status": "no_findings",
                "findings": [],
                "current": True,
                "verification": [
                    {"command": f"{self._homebrew_pybin_literal()} -B scripts/test_review_artifact_lint.py"}
                ],
            }
            support_rel, support_sha = self._write_support_payload(
                root,
                "docs/code_reviews/assets/260811_0004_red_support/full_payload.json",
                support_payload,
            )
            compact_payload = {
                "run_id": support_payload["run_id"],
                "lane_id": "reviewer_code_risk",
                "target_snapshot": "BUNDLE=staged",
                "lane_status": "no_findings",
                "findings": [],
                "current": True,
                "full_payload_ref": support_rel,
                "full_payload_sha256": support_sha,
            }
            self._write_origin_plan_payloads(root, plan_rel, [compact_payload])
            stdout = io.StringIO()
            with mock.patch("sys.stdout", stdout):
                result = MODULE.main(
                    [
                        "--project-root",
                        str(root),
                        "--select-risk-lane",
                        "--origin-plan",
                        plan_rel,
                        "--json",
                    ]
                )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(result, 1)
        self.assertEqual(payload["state"], "blocked")
        self.assertEqual(payload["error_code"], "expanded_homebrew_python_command_evidence")
        self.assertIsNone(payload["selected_line"])
        self.assertIsNone(payload["run_id"])
        self.assertIsNone(payload["target_snapshot"])

    def test_select_risk_lane_cli_support_red_matrix_is_fail_closed(self) -> None:
        scenarios = [
            ("missing_ref", {"full_payload_sha256_only": "0" * 64}, "missing_risk_lane_support_payload_ref"),
            ("missing_hash", {"omit_hash": True}, "missing_risk_lane_support_payload_hash"),
            (
                "invalid_ref",
                {
                    "full_payload_ref": "../outside/full_payload.json",
                    "full_payload_sha256": "0" * 64,
                },
                "invalid_risk_lane_support_payload_ref",
            ),
            (
                "missing_file",
                {
                    "full_payload_ref": "docs/code_reviews/assets/missing/full_payload.json",
                    "full_payload_sha256": "0" * 64,
                },
                "missing_risk_lane_support_payload_file",
            ),
            ("hash_mismatch", {"hash_override": "0" * 64}, "risk_lane_support_payload_hash_mismatch"),
            ("invalid_json", {"support_body": b"{"}, "invalid_risk_lane_support_payload_json"),
            ("missing_run_id", {"remove_support_keys": ("run_id",)}, "risk_lane_support_payload_parity_mismatch"),
            ("missing_findings", {"remove_support_keys": ("findings",)}, "risk_lane_support_payload_parity_mismatch"),
            ("missing_lane_id", {"remove_support_keys": ("lane_id",)}, "risk_lane_support_payload_parity_mismatch"),
            ("wrong_lane_id", {"lane_id": "reviewer_code_contracts"}, "risk_lane_support_payload_parity_mismatch"),
            ("run_id_mismatch", {"run_id": "reviewer_code_risk:sample:other"}, "risk_lane_support_payload_parity_mismatch"),
            ("target_mismatch", {"target_snapshot": "BUNDLE=other"}, "risk_lane_support_payload_parity_mismatch"),
            ("lane_status_mismatch", {"lane_status": "blockers"}, "risk_lane_support_payload_parity_mismatch"),
            ("findings_mismatch", {"findings": [{"finding_id": "risk:R1"}]}, "risk_lane_support_payload_parity_mismatch"),
            ("stale_support", {"current": False}, "risk_lane_support_payload_parity_mismatch"),
        ]

        for name, mutation, expected_code in scenarios:
            with self.subTest(name=name), temporary_git_root() as tmpdir:
                root = Path(tmpdir).resolve()
                plan_rel = f"docs/plans/260811_0004_selector_cli_{name}.md"
                support_payload = {
                    "run_id": mutation.get("run_id", "reviewer_code_risk:sample:20260811T150000Z"),
                    "lane_id": mutation.get("lane_id", "reviewer_code_risk"),
                    "target_snapshot": mutation.get("target_snapshot", "BUNDLE=staged"),
                    "lane_status": mutation.get("lane_status", "no_findings"),
                    "findings": mutation.get("findings", []),
                    "current": mutation.get("current", True),
                }
                for key in mutation.get("remove_support_keys", ()):
                    support_payload.pop(key)
                compact_payload = {
                    "run_id": "reviewer_code_risk:sample:20260811T150000Z",
                    "lane_id": "reviewer_code_risk",
                    "target_snapshot": "BUNDLE=staged",
                    "lane_status": "no_findings",
                    "findings": [],
                    "current": True,
                }
                if "full_payload_sha256_only" in mutation:
                    compact_payload["full_payload_sha256"] = mutation["full_payload_sha256_only"]
                elif "full_payload_ref" in mutation:
                    compact_payload["full_payload_ref"] = mutation["full_payload_ref"]
                    compact_payload["full_payload_sha256"] = mutation["full_payload_sha256"]
                elif "support_body" in mutation:
                    body = mutation["support_body"]
                    support_path = write_bytes_fixture(
                        root,
                        f"docs/code_reviews/assets/260811_0004_selector_cli_{name}/full_payload.json",
                        body,
                    )
                    compact_payload["full_payload_ref"] = str(support_path.relative_to(root))
                    compact_payload["full_payload_sha256"] = hashlib.sha256(body).hexdigest()
                else:
                    support_rel, support_sha = self._write_support_payload(
                        root,
                        f"docs/code_reviews/assets/260811_0004_selector_cli_{name}/full_payload.json",
                        support_payload,
                    )
                    compact_payload["full_payload_ref"] = support_rel
                    if not mutation.get("omit_hash", False):
                        compact_payload["full_payload_sha256"] = mutation.get("hash_override", support_sha)

                self._write_origin_plan_payloads(root, plan_rel, [compact_payload])
                stdout = io.StringIO()
                with mock.patch("sys.stdout", stdout):
                    result = MODULE.main(
                        [
                            "--project-root",
                            str(root),
                            "--select-risk-lane",
                            "--origin-plan",
                            plan_rel,
                            "--json",
                        ]
                    )

                payload = json.loads(stdout.getvalue())
                self.assertNotEqual(result, 0)
                self.assertEqual(payload["state"], "blocked")
                self.assertEqual(payload["error_code"], expected_code)
                self.assertIsNone(payload["selected_line"])
                self.assertIsNone(payload["run_id"])
                self.assertIsNone(payload["target_snapshot"])

    def test_select_risk_lane_cli_requires_current_bundle_support_pair(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260811_0004_current_bundle.md"
            self._write_origin_plan_payloads(
                root,
                plan_rel,
                [
                    {
                        "run_id": "reviewer_code_risk:sample:20260811T150000Z",
                        "lane_id": "reviewer_code_risk",
                        "target_snapshot": "BUNDLE=current bundle_sha256=" + "0" * 64,
                        "lane_status": "no_findings",
                        "findings": [],
                        "current": True,
                    }
                ],
            )
            stdout = io.StringIO()
            with mock.patch("sys.stdout", stdout):
                result = MODULE.main(
                    [
                        "--project-root",
                        str(root),
                        "--select-risk-lane",
                        "--origin-plan",
                        plan_rel,
                        "--json",
                    ]
                )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(result, 1)
        self.assertEqual(payload["state"], "blocked")
        self.assertEqual(payload["error_code"], "missing_risk_lane_support_payload_ref")
        self.assertIsNone(payload["selected_line"])
        self.assertIsNone(payload["run_id"])
        self.assertIsNone(payload["target_snapshot"])

    def test_select_risk_lane_cli_rejects_nonterminal_bare_current_compact_claims(self) -> None:
        cases: dict[str, object] = {
            "string": "BUNDLE=current",
            "object": {"target": "BUNDLE=current"},
        }
        for label, target_snapshot in cases.items():
            with self.subTest(label=label), temporary_git_root() as tmpdir:
                root = Path(tmpdir).resolve()
                plan_rel = f"docs/plans/260811_0004_bare_current_{label}.md"
                plan_path = self._write_origin_plan_payloads(
                    root,
                    plan_rel,
                    [
                        {
                            "run_id": "reviewer_code_risk:sample:20260811T150000Z",
                            "lane_id": "reviewer_code_risk",
                            "target_snapshot": target_snapshot,
                            "lane_status": "no_findings",
                            "findings": [],
                            "current": True,
                        }
                    ],
                )
                plan_path.write_text(
                    plan_path.read_text(encoding="utf-8").replace(
                        "# Plan\n", "# Plan\n\n**Status:** Ready for Review\n", 1
                    ),
                    encoding="utf-8",
                )
                stdout = io.StringIO()
                with mock.patch("sys.stdout", stdout):
                    result = MODULE.main(
                        [
                            "--project-root",
                            str(root),
                            "--select-risk-lane",
                            "--origin-plan",
                            plan_rel,
                            "--json",
                        ]
                    )

            payload = json.loads(stdout.getvalue())
            self.assertEqual(result, 1)
            self.assertEqual(payload["state"], "blocked")
            self.assertEqual(payload["error_code"], "missing_risk_lane_support_payload_ref")
            self.assertIsNone(payload["selected_line"])
            self.assertIsNone(payload["run_id"])
            self.assertIsNone(payload["target_snapshot"])

    def test_select_risk_lane_cli_rejects_invalid_current_bundle_support_snapshot(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260811_0004_invalid_current_snapshot.md"
            provisional_plan = self._write_current_bundle_origin_plan(
                root,
                plan_rel,
                "BUNDLE=current bundle_sha256=" + "0" * 64,
            )
            current_snapshot = MODULE.build_current_bundle_snapshot(provisional_plan, project_root=root)
            target_snapshot = current_snapshot["target"]
            assert isinstance(target_snapshot, str)
            support_payload = {
                "run_id": "reviewer_code_risk:sample:20260811T150000Z",
                "lane_id": "reviewer_code_risk",
                "target_snapshot": {"target": target_snapshot},
                "lane_status": "no_findings",
                "findings": [],
                "current": True,
            }
            support_rel, support_sha = self._write_support_payload(
                root,
                "docs/code_reviews/assets/260811_0004_invalid_current_snapshot/full_payload.json",
                support_payload,
            )
            compact_payload = {
                "run_id": support_payload["run_id"],
                "lane_id": "reviewer_code_risk",
                "target_snapshot": current_snapshot["target_snapshot"],
                "lane_status": "no_findings",
                "findings": [],
                "current": True,
                "full_payload_ref": support_rel,
                "full_payload_sha256": support_sha,
            }
            self._write_current_bundle_origin_plan(root, plan_rel, target_snapshot, payload=compact_payload)
            stdout = io.StringIO()
            with mock.patch("sys.stdout", stdout):
                result = MODULE.main(
                    [
                        "--project-root",
                        str(root),
                        "--select-risk-lane",
                        "--origin-plan",
                        plan_rel,
                        "--json",
                    ]
                )

        payload = json.loads(stdout.getvalue())
        self.assertNotEqual(result, 0)
        self.assertEqual(payload["state"], "blocked")
        self.assertEqual(payload["error_code"], "invalid_risk_lane_support_payload_snapshot")
        self.assertIsNone(payload["selected_line"])
        self.assertIsNone(payload["run_id"])
        self.assertIsNone(payload["target_snapshot"])

    def test_select_risk_lane_cli_blocks_stale_or_removed_current_producer_target(self) -> None:
        cases = {
            "target_drift": (
                lambda root: write_text_fixture(root, "scripts/current_bundle_target.py", "print('drift')\n"),
                "current_review_proof_producer_mismatch",
            ),
            "target_removed": (
                lambda root: (root / "scripts/current_bundle_target.py").unlink(),
                "current_review_proof_producer_or_support_unavailable",
            ),
        }
        for label, (mutate_target, expected_code) in cases.items():
            with self.subTest(label=label), temporary_git_root() as tmpdir:
                root = Path(tmpdir).resolve()
                plan_rel = f"docs/plans/260811_0004_selector_{label}.md"
                review_rel = f"docs/code_reviews/260811_0004_selector_{label}.md"
                snapshot, _compact = self._materialize_current_proof(
                    root,
                    plan_rel=plan_rel,
                    review_rel=review_rel,
                )
                target = snapshot["target"]
                assert isinstance(target, str)
                self._write_markdown(root, review_rel, f"# Review\n\n**Target:** {target}\n")

                initial_stdout = io.StringIO()
                with mock.patch("sys.stdout", initial_stdout):
                    initial_result = MODULE.main(
                        [
                            "--project-root",
                            str(root),
                            "--select-risk-lane",
                            "--origin-plan",
                            plan_rel,
                            "--json",
                        ]
                    )
                self.assertEqual(initial_result, 0)
                self.assertEqual(json.loads(initial_stdout.getvalue())["state"], "selected")

                mutate_target(root)
                canonical = plan_lint.preflight_current_review_proof(root / plan_rel, project_root=root)
                stdout = io.StringIO()
                with mock.patch("sys.stdout", stdout):
                    result = MODULE.main(
                        [
                            "--project-root",
                            str(root),
                            "--select-risk-lane",
                            "--origin-plan",
                            plan_rel,
                            "--json",
                        ]
                    )

                payload = json.loads(stdout.getvalue())
                self.assertEqual((canonical.state, canonical.reason_code), ("blocked", expected_code))
                self.assertEqual(result, 1)
                self.assertEqual(payload["state"], "blocked")
                self.assertEqual(payload["error_code"], expected_code)
                self.assertIsNone(payload["selected_line"])
                self.assertIsNone(payload["run_id"])
                self.assertIsNone(payload["target_snapshot"])

    def test_select_risk_lane_cli_rejects_origin_outside_explicit_root_without_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve() / "repo"
            root.mkdir()
            standalone_git_root(root)
            outside = Path(tmpdir).resolve() / "outside.md"
            outside.write_text("# Plan\n", encoding="utf-8")
            stdout = io.StringIO()
            with mock.patch.object(plan_lint, "select_plan_risk_lane_snapshot") as selector:
                with mock.patch("sys.stdout", stdout):
                    result = MODULE.main(
                        [
                            "--project-root",
                            str(root),
                            "--select-risk-lane",
                            "--origin-plan",
                            str(outside),
                            "--json",
                        ]
                    )

        payload = json.loads(stdout.getvalue())
        selector.assert_not_called()
        self.assertEqual(result, 1)
        self.assertEqual(payload["state"], "blocked")
        self.assertEqual(payload["error_code"], "origin_plan_outside_project_root")

    def test_select_risk_lane_cli_blocks_homebrew_command_evidence(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260329_0248_origin.md"
            self._write_origin_plan_payloads(
                root,
                plan_rel,
                [
                    {
                        "run_id": "reviewer_code_risk:sample:20260616T1956MSK",
                        "lane_id": "reviewer_code_risk",
                        "target_snapshot": "BUNDLE=fresh",
                        "lane_status": "complete",
                        "findings": [],
                        "verification": [
                            {
                                "command": f"{self._homebrew_pybin_literal()} -B scripts/test_review_artifact_lint.py",
                                "exit_code": 0,
                            }
                        ],
                    },
                ],
            )
            stdout = io.StringIO()

            with mock.patch("sys.stdout", stdout):
                result = MODULE.main(
                    [
                        "--project-root",
                        str(root),
                        "--select-risk-lane",
                        "--origin-plan",
                        plan_rel,
                        "--json",
                    ]
                )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(result, 1)
        self.assertEqual(payload["schema_version"], "reviewer_risk_lane_selection.v1")
        self.assertEqual(payload["state"], "blocked")
        self.assertEqual(payload["origin_plan"], plan_rel)
        self.assertEqual(payload["error_code"], "expanded_homebrew_python_command_evidence")
        self.assertIn("expanded owner-local Homebrew", payload["reason"])

    def test_select_risk_lane_cli_missing_is_non_green_json(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260329_0248_origin.md"
            self._write_origin_plan(root, plan_rel, target_snapshot=None)
            stdout = io.StringIO()

            with mock.patch("sys.stdout", stdout):
                result = MODULE.main(
                    [
                        "--project-root",
                        str(root),
                        "--select-risk-lane",
                        "--origin-plan",
                        plan_rel,
                        "--json",
                    ]
                )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(result, 1)
        self.assertEqual(payload["schema_version"], "reviewer_risk_lane_selection.v1")
        self.assertEqual(payload["state"], "missing")
        self.assertEqual(payload["origin_plan"], plan_rel)
        self.assertIsNone(payload["selected_line"])
        self.assertIsNone(payload["run_id"])
        self.assertIsNone(payload["target_snapshot"])
        self.assertEqual(payload["error_code"], "missing_plan_resident_risk_lane")
        self.assertIn("no parseable", payload["reason"])

    def test_select_risk_lane_cli_ambiguous_is_blocked_json(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260329_0248_origin.md"
            self._write_origin_plan_payloads(
                root,
                plan_rel,
                [
                    {
                        "lane_id": "reviewer_code_risk",
                        "target_snapshot": "BUNDLE=first",
                        "lane_status": "complete",
                    },
                    {
                        "lane_id": "reviewer_code_risk",
                        "target_snapshot": "BUNDLE=second",
                        "lane_status": "complete",
                    },
                ],
            )
            stdout = io.StringIO()

            with mock.patch("sys.stdout", stdout):
                result = MODULE.main(
                    [
                        "--project-root",
                        str(root),
                        "--select-risk-lane",
                        "--origin-plan",
                        plan_rel,
                        "--json",
                    ]
                )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(result, 1)
        self.assertEqual(payload["schema_version"], "reviewer_risk_lane_selection.v1")
        self.assertEqual(payload["state"], "blocked")
        self.assertIsNone(payload["selected_line"])
        self.assertIsNone(payload["run_id"])
        self.assertIsNone(payload["target_snapshot"])
        self.assertEqual(payload["error_code"], "ambiguous_plan_resident_risk_lane")
        self.assertIn("missing sortable", payload["reason"])

    def test_select_risk_lane_cli_single_historical_candidate_is_blocked_json(self) -> None:
        cases = (
            ({"current": False}, "ambiguous_plan_resident_risk_lane", "all candidates are marked historical/superseded"),
            (
                {"superseded_by": "reviewer_code_risk:sample:20260616T2000MSK"},
                "risk_lane_superseded_by_orphan",
                "must reference one parseable sibling",
            ),
        )
        for marker, expected_code, expected_reason in cases:
            with self.subTest(marker=marker):
                with temporary_git_root() as tmpdir:
                    root = Path(tmpdir).resolve()
                    plan_rel = "docs/plans/260329_0248_origin.md"
                    payload = {
                        "run_id": "reviewer_code_risk:sample:20260616T1956MSK",
                        "lane_id": "reviewer_code_risk",
                        "target_snapshot": "BUNDLE=stale",
                        "lane_status": "complete",
                    }
                    payload.update(marker)
                    self._write_origin_plan_payloads(root, plan_rel, [payload])
                    stdout = io.StringIO()

                    with mock.patch("sys.stdout", stdout):
                        result = MODULE.main(
                            [
                                "--project-root",
                                str(root),
                                "--select-risk-lane",
                                "--origin-plan",
                                plan_rel,
                                "--json",
                            ]
                        )

                output = json.loads(stdout.getvalue())
                self.assertEqual(result, 1)
                self.assertEqual(output["schema_version"], "reviewer_risk_lane_selection.v1")
                self.assertEqual(output["state"], "blocked")
                self.assertIsNone(output["selected_line"])
                self.assertIsNone(output["run_id"])
                self.assertIsNone(output["target_snapshot"])
                self.assertEqual(output["error_code"], expected_code)
                self.assertIn(expected_reason, output["reason"])

    def test_select_risk_lane_cli_requires_origin_plan(self) -> None:
        with mock.patch("sys.stderr", io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                MODULE.main(["--select-risk-lane", "--json"])

        self.assertEqual(raised.exception.code, 2)

    def test_public_review_artifact_status_reads_literal_header(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            review_path = self._write_markdown(
                root,
                "docs/code_reviews/260329_0248_status.md",
                self._single_commit_dual_lane_fixture(status="✅ OK"),
            )

            status = MODULE.review_artifact_status(review_path)

        self.assertEqual(status, "✅ ok")

    def test_final_dual_lane_accepts_matching_support_payload(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260329_0248_origin.md"
            support_payload = {
                "run_id": "reviewer_code_risk:sample:20260616T1956MSK",
                "lane_id": "reviewer_code_risk",
                "target_snapshot": "BUNDLE=staged",
                "lane_status": "no_findings",
                "findings": [],
                "current": True,
            }
            support_rel, support_sha = self._write_support_payload(
                root,
                "docs/code_reviews/assets/260329_0248_origin/full_payload.json",
                support_payload,
            )
            compact_payload = {
                **support_payload,
                "full_payload_ref": support_rel,
                "full_payload_sha256": support_sha,
            }
            self._write_origin_plan_payloads(root, plan_rel, [compact_payload])
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0248_support_payload_match.md",
                self._single_commit_dual_lane_fixture(target="BUNDLE=staged"),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260329_0248_support_payload_match.md"),
                project_root=root,
                origin_plan=plan_rel,
                require_dual_lane_origin=True,
            )

        self.assertEqual(findings, [])

    def test_current_bundle_support_payload_requires_nested_v2_snapshot(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260801_1622_current_bundle_origin.md"
            self._write_current_bundle_origin_plan(
                root,
                plan_rel,
                "BUNDLE=current bundle_sha256=" + "0" * 64,
            )
            current_snapshot = MODULE.build_current_bundle_snapshot(root / plan_rel, project_root=root)
            target = current_snapshot["target"]
            assert isinstance(target, str)
            support_payload = {
                "run_id": "reviewer_code_risk:fixture:20260802T204700Z",
                "lane_id": "reviewer_code_risk",
                "target_snapshot": current_snapshot,
                "lane_status": "no_findings",
                "findings": [],
                "current": True,
            }
            support_rel, support_sha = self._write_support_payload(
                root,
                "docs/code_reviews/assets/260801_1622_current_bundle_origin/full_payload.json",
                support_payload,
            )
            compact_payload = {
                "run_id": support_payload["run_id"],
                "lane_id": "reviewer_code_risk",
                "target_snapshot": current_snapshot["target_snapshot"],
                "lane_status": "no_findings",
                "findings": [],
                "current": True,
                "full_payload_ref": support_rel,
                "full_payload_sha256": support_sha,
            }
            self._write_current_bundle_origin_plan(root, plan_rel, target, payload=compact_payload)
            review_rel = "docs/code_reviews/260801_1622_current_bundle_support.md"
            self._write_markdown(
                root,
                review_rel,
                self._with_first_summary(
                    self._single_commit_dual_lane_fixture(
                        target=target,
                    ),
                    "ОК: current-bundle compact support payload validates nested v2 truth.",
                ),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, review_rel),
                project_root=root,
                origin_plan=plan_rel,
                require_dual_lane_origin=True,
            )

            self.assertEqual(findings, [])

            invalid_snapshot = dict(current_snapshot)
            invalid_snapshot.pop("schema_version")
            invalid_payload = {**support_payload, "target_snapshot": invalid_snapshot}
            invalid_rel, invalid_sha = self._write_support_payload(
                root,
                "docs/code_reviews/assets/260801_1622_current_bundle_origin/invalid_payload.json",
                invalid_payload,
            )
            invalid_compact = {**compact_payload, "full_payload_ref": invalid_rel, "full_payload_sha256": invalid_sha}
            self._write_current_bundle_origin_plan(root, plan_rel, target, payload=invalid_compact)
            findings = MODULE.lint_review_artifacts(
                self._load_single(root, review_rel),
                project_root=root,
                origin_plan=plan_rel,
                require_dual_lane_origin=True,
            )

        self.assertTrue(any(finding.code == "invalid_risk_lane_support_payload_snapshot" for finding in findings), findings)

    def test_final_dual_lane_rejects_invalid_support_payloads(self) -> None:
        scenarios = [
            ("missing_ref", {"full_payload_sha256_only": "0" * 64}, "missing_risk_lane_support_payload_ref"),
            ("missing_hash", {}, "missing_risk_lane_support_payload_hash"),
            (
                "missing_file",
                {"full_payload_ref": "docs/code_reviews/assets/missing/full_payload.json", "full_payload_sha256": "0" * 64},
                "missing_risk_lane_support_payload_file",
            ),
            ("hash_mismatch", {"hash_override": "0" * 64}, "risk_lane_support_payload_hash_mismatch"),
            ("invalid_json", {"support_body": b"{"}, "invalid_risk_lane_support_payload_json"),
            ("missing_run_id", {"remove_support_keys": ("run_id",)}, "risk_lane_support_payload_parity_mismatch"),
            ("missing_findings", {"remove_support_keys": ("findings",)}, "risk_lane_support_payload_parity_mismatch"),
            ("missing_lane_id", {"remove_support_keys": ("lane_id",)}, "risk_lane_support_payload_parity_mismatch"),
            ("wrong_lane_id", {"lane_id": "reviewer_code_contracts"}, "risk_lane_support_payload_parity_mismatch"),
            ("run_id_mismatch", {"run_id": "reviewer_code_risk:sample:other"}, "risk_lane_support_payload_parity_mismatch"),
            ("target_mismatch", {"target_snapshot": "BUNDLE=other"}, "risk_lane_support_payload_parity_mismatch"),
            ("lane_status_mismatch", {"lane_status": "blockers"}, "risk_lane_support_payload_parity_mismatch"),
            ("findings_mismatch", {"findings": [{"finding_id": "risk:R1"}]}, "risk_lane_support_payload_parity_mismatch"),
            ("stale_support", {"current": False}, "risk_lane_support_payload_parity_mismatch"),
        ]

        for name, mutation, expected_code in scenarios:
            with self.subTest(name=name), temporary_git_root() as tmpdir:
                root = Path(tmpdir).resolve()
                plan_rel = f"docs/plans/260329_0248_{name}.md"
                support_payload = {
                    "run_id": mutation.get("run_id", "reviewer_code_risk:sample:20260616T1956MSK"),
                    "lane_id": mutation.get("lane_id", "reviewer_code_risk"),
                    "target_snapshot": mutation.get("target_snapshot", "BUNDLE=staged"),
                    "lane_status": mutation.get("lane_status", "no_findings"),
                    "findings": mutation.get("findings", []),
                    "current": mutation.get("current", True),
                }
                for key in mutation.get("remove_support_keys", ()):
                    support_payload.pop(key)
                compact_payload = {
                    "run_id": "reviewer_code_risk:sample:20260616T1956MSK",
                    "lane_id": "reviewer_code_risk",
                    "target_snapshot": "BUNDLE=staged",
                    "lane_status": "no_findings",
                    "findings": [],
                    "current": True,
                }
                if "full_payload_sha256_only" in mutation:
                    compact_payload["full_payload_sha256"] = mutation["full_payload_sha256_only"]
                elif "full_payload_ref" in mutation:
                    compact_payload["full_payload_ref"] = mutation["full_payload_ref"]
                    compact_payload["full_payload_sha256"] = mutation["full_payload_sha256"]
                elif "support_body" in mutation:
                    body = mutation["support_body"]
                    support_path = write_bytes_fixture(
                        root,
                        f"docs/code_reviews/assets/260329_0248_{name}/full_payload.json",
                        body,
                    )
                    compact_payload["full_payload_ref"] = str(support_path.relative_to(root))
                    compact_payload["full_payload_sha256"] = hashlib.sha256(body).hexdigest()
                else:
                    support_rel, support_sha = self._write_support_payload(
                        root,
                        f"docs/code_reviews/assets/260329_0248_{name}/full_payload.json",
                        support_payload,
                    )
                    compact_payload["full_payload_ref"] = support_rel
                    if name != "missing_hash":
                        compact_payload["full_payload_sha256"] = mutation.get("hash_override", support_sha)

                self._write_origin_plan_payloads(root, plan_rel, [compact_payload])
                self._write_markdown(
                    root,
                    f"docs/code_reviews/260329_0248_{name}.md",
                    self._single_commit_dual_lane_fixture(target="BUNDLE=staged"),
                )

                findings = MODULE.lint_review_artifacts(
                    self._load_single(root, f"docs/code_reviews/260329_0248_{name}.md"),
                    project_root=root,
                    origin_plan=plan_rel,
                    require_dual_lane_origin=True,
                )

            self.assertTrue(any(finding.code == expected_code for finding in findings), findings)

    def test_final_dual_lane_projects_complete_shared_preflight_diagnostics(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260811_0004_shared_diagnostics.md"
            support_payload = {
                "run_id": "reviewer_code_risk:sample:20260811T150000Z",
                "lane_id": "reviewer_code_risk",
                "target_snapshot": "BUNDLE=staged",
                "lane_status": "no_findings",
                "findings": [],
                "current": True,
                "verification": [
                    {"command": f"{self._homebrew_pybin_literal()} -B scripts/test_review_artifact_lint.py"}
                ],
            }
            support_rel, _support_sha = self._write_support_payload(
                root,
                "docs/code_reviews/assets/260811_0004_shared_diagnostics/full_payload.json",
                support_payload,
            )
            compact_payload = {
                "run_id": support_payload["run_id"],
                "lane_id": "reviewer_code_risk",
                "target_snapshot": "BUNDLE=staged",
                "lane_status": "no_findings",
                "findings": [],
                "current": True,
                "full_payload_ref": support_rel,
                "full_payload_sha256": "0" * 64,
            }
            plan_path = self._write_origin_plan_payloads(root, plan_rel, [compact_payload])
            selection = plan_lint.select_plan_risk_lane_snapshot(plan_path)
            diagnostics = plan_lint.preflight_selected_risk_lane_support(
                plan_path,
                selection,
                project_root=root,
            )
            review_rel = "docs/code_reviews/260811_0004_shared_diagnostics.md"
            self._write_markdown(root, review_rel, self._single_commit_dual_lane_fixture(target="BUNDLE=staged"))
            findings = MODULE.lint_review_artifacts(
                self._load_single(root, review_rel),
                project_root=root,
                origin_plan=plan_rel,
                require_dual_lane_origin=True,
            )

        expected = {(diagnostic.code, diagnostic.message) for diagnostic in diagnostics}
        actual = {(finding.code, finding.message) for finding in findings if finding.code in {code for code, _ in expected}}
        self.assertEqual(expected, actual)
        self.assertEqual([diagnostic.code for diagnostic in diagnostics], [
            "risk_lane_support_payload_hash_mismatch",
            "expanded_homebrew_python_command_evidence",
        ])
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn("plan_lint.preflight_selected_risk_lane_support", source)
        self.assertNotIn("def _validate_risk_lane_support_payload", source)

    def test_final_dual_lane_rejects_origin_outside_explicit_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve() / "repo"
            root.mkdir()
            standalone_git_root(root)
            outside_plan = Path(tmpdir).resolve() / "outside.md"
            outside_plan.write_text("# Plan\n", encoding="utf-8")
            review_rel = "docs/code_reviews/260811_0004_outside_origin.md"
            self._write_markdown(root, review_rel, self._single_commit_dual_lane_fixture(target="BUNDLE=staged"))
            findings = MODULE.lint_review_artifacts(
                self._load_single(root, review_rel),
                project_root=root,
                origin_plan=outside_plan,
                require_dual_lane_origin=True,
            )

        self.assertTrue(any(finding.code == "origin_plan_outside_project_root" for finding in findings), findings)

    def test_final_dual_lane_rejects_same_cardinality_finding_substitutions(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260801_1622_findings_projection.md"
            compact_finding = {
                "id": "risk:R1",
                "severity": "S1",
                "domain": "correctness",
                "title": "Canonical compact finding",
                "source_refs": ["scripts/review_artifact_lint.py:2074"],
            }
            support_finding = {
                **compact_finding,
                "evidence": ["Evidence remains support-only and is not a compact field."],
                "impact": "Parity must not accept a substituted compact finding.",
                "recommendation": "Compare the canonical compact projection.",
            }
            support_payload = {
                "run_id": "reviewer_code_risk:sample:20260802T213100Z",
                "lane_id": "reviewer_code_risk",
                "target_snapshot": "BUNDLE=staged",
                "lane_status": "complete",
                "findings": [support_finding],
                "current": True,
            }
            support_rel, support_sha = self._write_support_payload(
                root,
                "docs/code_reviews/assets/260801_1622_findings_projection/full_payload.json",
                support_payload,
            )
            compact_payload = {
                "run_id": support_payload["run_id"],
                "lane_id": "reviewer_code_risk",
                "target_snapshot": "BUNDLE=staged",
                "lane_status": "complete",
                "findings": [compact_finding],
                "current": True,
                "full_payload_ref": support_rel,
                "full_payload_sha256": support_sha,
            }
            self._write_origin_plan_payloads(root, plan_rel, [compact_payload])
            review_rel = "docs/code_reviews/260801_1622_findings_projection.md"
            self._write_markdown(root, review_rel, self._single_commit_dual_lane_fixture(target="BUNDLE=staged"))

            baseline = MODULE.lint_review_artifacts(
                self._load_single(root, review_rel),
                project_root=root,
                origin_plan=plan_rel,
                require_dual_lane_origin=True,
            )
            self.assertFalse(
                any(finding.code == "risk_lane_support_payload_parity_mismatch" for finding in baseline),
                baseline,
            )

            substitutions = {
                "id": "risk:R9",
                "severity": "S3",
                "domain": "integration semantics",
                "title": "Substituted compact finding",
                "source_refs": ["scripts/other.py:9"],
            }
            for field, value in substitutions.items():
                with self.subTest(field=field):
                    mutated_support = {
                        **support_payload,
                        "findings": [{**support_finding, field: value}],
                    }
                    mutated_rel, mutated_sha = self._write_support_payload(
                        root,
                        f"docs/code_reviews/assets/260801_1622_findings_projection/{field}.json",
                        mutated_support,
                    )
                    self._write_origin_plan_payloads(
                        root,
                        plan_rel,
                        [
                            {
                                **compact_payload,
                                "full_payload_ref": mutated_rel,
                                "full_payload_sha256": mutated_sha,
                            }
                        ],
                    )
                    findings = MODULE.lint_review_artifacts(
                        self._load_single(root, review_rel),
                        project_root=root,
                        origin_plan=plan_rel,
                        require_dual_lane_origin=True,
                    )

                    self.assertTrue(
                        any(finding.code == "risk_lane_support_payload_parity_mismatch" for finding in findings),
                        findings,
                    )

    def test_final_dual_lane_accepts_plan_resident_runner_session_metadata(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260329_0248_origin.md"
            payload = {
                "run_id": "rcr-20260612-1733MSK-01",
                "lane_id": "reviewer_code_risk",
                "runner_id": "claude",
                "session_key": "reviewer_code_risk",
                "sid": "00000000-0000-4000-8000-000000000106",
                "profile": "fixture-claude-model",
                "model": "fixture-claude-model",
                "prompt_file": "docs/tools/prompts/reviewer_status_driven.md",
                "target_ref": "docs/plans/260329_0248_origin.md",
                "target_snapshot": "BUNDLE=staged",
                "lane_status": "complete",
                "written_at": "2026-06-12 17:33 MSK",
            }
            self._write_markdown(
                root,
                plan_rel,
                dedent(
                    f"""\
                    # Plan

                    ## Evidence
                    - reviewer_code_risk lane-run artifact:
                      ```json
                      {json.dumps(payload, indent=2)}
                      ```
                    """
                ),
            )
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0248_runner_metadata.md",
                self._single_commit_dual_lane_fixture(target="BUNDLE=staged"),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260329_0248_runner_metadata.md"),
                project_root=root,
                origin_plan=plan_rel,
                require_dual_lane_origin=True,
            )

        self.assertEqual(findings, [])

    def test_final_dual_lane_accepts_structured_bundle_hash_target_snapshot(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260329_0248_origin.md"
            target = "BUNDLE=staged bundle_sha256=abc123"
            self._write_structured_origin_plan(
                root,
                plan_rel,
                {"target": "BUNDLE=staged", "bundle_sha256": "abc123"},
            )
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0248_structured_snapshot_match.md",
                self._single_commit_dual_lane_fixture(target=target),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260329_0248_structured_snapshot_match.md"),
                project_root=root,
                origin_plan=plan_rel,
                require_dual_lane_origin=True,
            )

        self.assertEqual(findings, [])

    def test_final_dual_lane_accepts_producer_current_bundle_target_snapshot(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260619_0242_current_bundle_origin.md"
            review_rel = "docs/code_reviews/260619_0242_current_bundle_match.md"
            current_snapshot, _compact_payload = self._materialize_current_proof(
                root,
                plan_rel=plan_rel,
                review_rel=review_rel,
            )
            self._write_markdown(
                root,
                review_rel,
                self._with_first_summary(
                    self._single_commit_dual_lane_fixture(
                        target=current_snapshot["target"],
                    ),
                    "ОК: current bundle producer snapshot matches disk.",
                ),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, review_rel),
                project_root=root,
                origin_plan=plan_rel,
                require_dual_lane_origin=True,
            )

        self.assertEqual(findings, [])

    def test_final_dual_lane_rejects_stale_matching_current_bundle_hash(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260619_0242_current_bundle_origin.md"
            stale_target = f"BUNDLE=current bundle_sha256={'0' * 64}"
            review_rel = "docs/code_reviews/260619_0242_current_bundle_stale.md"
            self._write_current_bundle_origin_plan(root, plan_rel, stale_target, review_rel=review_rel)
            self._write_markdown(
                root,
                review_rel,
                self._single_commit_dual_lane_fixture(target=stale_target),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, review_rel),
                project_root=root,
                origin_plan=plan_rel,
                require_dual_lane_origin=True,
            )

        self.assertTrue(any(finding.code == "current_review_proof_compact_snapshot_invalid" for finding in findings), findings)
        self.assertFalse(any(finding.code == "dual_lane_target_snapshot_mismatch" for finding in findings), findings)

    def test_final_dual_lane_reports_current_bundle_snapshot_unavailable_separately(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260619_0242_current_bundle_origin.md"
            review_rel = "docs/code_reviews/260619_0242_current_bundle_unavailable.md"
            current_snapshot, _compact_payload = self._materialize_current_proof(
                root,
                plan_rel=plan_rel,
                review_rel=review_rel,
            )
            self._write_markdown(
                root,
                review_rel,
                self._single_commit_dual_lane_fixture(target=current_snapshot["target"]),
            )

            with mock.patch.object(
                plan_lint,
                "build_current_bundle_snapshot",
                side_effect=plan_lint.SnapshotError("fixture producer failure"),
            ):
                findings = MODULE.lint_review_artifacts(
                    self._load_single(root, review_rel),
                    project_root=root,
                    origin_plan=plan_rel,
                    require_dual_lane_origin=True,
                )

        codes = {finding.code for finding in findings}
        self.assertIn("current_review_proof_producer_or_support_unavailable", codes)
        self.assertNotIn("current_review_proof_projection_mismatch", codes)

    def test_final_dual_lane_keeps_origin_self_target_non_green(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260729_2000_origin_self_target.md"
            review_rel = "docs/code_reviews/260729_2000_origin_self_target.md"
            current_snapshot, _compact_payload = self._materialize_current_proof(
                root,
                plan_rel=plan_rel,
                review_rel=review_rel,
            )
            draft_rel = plan_rel.replace("docs/plans/", "docs/code_drafts/").replace(
                ".md",
                "__code_draft.md",
            )
            draft_path = root / draft_rel
            draft_path.write_text(
                draft_path.read_text(encoding="utf-8").replace(
                    "scripts/current_bundle_target.py",
                    plan_rel,
                ),
                encoding="utf-8",
            )
            review_rel = "docs/code_reviews/260729_2000_origin_self_target.md"
            self._write_markdown(
                root,
                review_rel,
                self._single_commit_dual_lane_fixture(target=current_snapshot["target"]),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, review_rel),
                project_root=root,
                origin_plan=plan_rel,
                require_dual_lane_origin=True,
            )

        unavailable = [
            finding
            for finding in findings
            if finding.code == "current_review_proof_producer_or_support_unavailable"
        ]
        self.assertEqual(len(unavailable), 1)
        self.assertIn("origin_plan_in_review_targets", unavailable[0].message)
        self.assertFalse(
            any(finding.code == "current_bundle_target_snapshot_mismatch" for finding in findings),
            findings,
        )

    def test_duplicate_green_and_red_review_status_is_rejected(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260619_0242_duplicate_status_origin.md"
            self._write_origin_plan(root, plan_rel, target_snapshot="BUNDLE=staged")
            review_rel = "docs/code_reviews/260619_0242_duplicate_status.md"
            review_body = self._single_commit_dual_lane_fixture().replace(
                "**Status:** ✅ OK",
                "**Status:** ✅ OK\n**Status:** ❌ S1 blocker(ы)",
                1,
            )
            self._write_markdown(root, review_rel, review_body)

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, review_rel),
                project_root=root,
                origin_plan=plan_rel,
                require_dual_lane_origin=True,
            )

        self.assertTrue(
            any(finding.code == "duplicate_review_status" for finding in findings),
            findings,
        )

    def test_empty_duplicate_review_status_is_rejected(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260619_0242_empty_duplicate_status_origin.md"
            self._write_origin_plan(root, plan_rel, target_snapshot="BUNDLE=staged")
            review_rel = "docs/code_reviews/260619_0242_empty_duplicate_status.md"
            review_body = self._single_commit_dual_lane_fixture().replace(
                "**Status:** ✅ OK",
                "**Status:** ✅ OK\n**Status:**",
                1,
            )
            self._write_markdown(root, review_rel, review_body)

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, review_rel),
                project_root=root,
                origin_plan=plan_rel,
                require_dual_lane_origin=True,
            )

        self.assertTrue(
            any(finding.code == "duplicate_review_status" for finding in findings),
            findings,
        )

    def test_status_inside_fenced_or_indented_code_is_not_a_header(self) -> None:
        examples = {
            "fenced": "\n```text\n**Status:** ❌ S1 blocker(ы)\n```\n",
            "indented": "\n    **Status:** ❌ S1 blocker(ы)\n",
        }
        for case, example in examples.items():
            with self.subTest(case=case), temporary_git_root() as tmpdir:
                root = Path(tmpdir).resolve()
                review_rel = f"docs/code_reviews/260619_0242_{case}_status.md"
                self._write_markdown(
                    root,
                    review_rel,
                    self._single_commit_dual_lane_fixture() + example,
                )
                artifact = self._load_single(root, review_rel)[0]

                statuses = MODULE._extract_status_lines(artifact.lines)
                findings = MODULE.lint_review_artifacts([artifact], project_root=root)

            self.assertEqual([value for _line, value in statuses], ["✅ OK"])
            self.assertNotIn("duplicate_review_status", {finding.code for finding in findings})

    def test_body_fence_content_cannot_change_header_status(self) -> None:
        examples = {
            "backtick": "\n```text\n```not-a-closing-fence\n**Status:** ✅ OK\n```\n**Status:** ❌ S1 blocker(ы)\n",
            "tilde_longer_outer": "\n~~~~text\n~~~not-a-closing-fence\n**Status:** ✅ OK\n~~~~  \n**Status:** ❌ S1 blocker(ы)\n",
            "html_comment": "\n<!--\n```text\n-->\n**Status:** ❌ S1 blocker(ы)\n```\n",
        }
        for case, example in examples.items():
            with self.subTest(case=case), temporary_git_root() as tmpdir:
                root = Path(tmpdir).resolve()
                review_rel = f"docs/code_reviews/260619_0242_{case}_fence.md"
                self._write_markdown(
                    root,
                    review_rel,
                    self._single_commit_dual_lane_fixture() + example,
                )
                artifact = self._load_single(root, review_rel)[0]

                statuses = MODULE._extract_status_lines(artifact.lines)
                findings = MODULE.lint_review_artifacts([artifact], project_root=root)

            self.assertEqual([value for _line, value in statuses], ["✅ OK"])
            self.assertNotIn("duplicate_review_status", {finding.code for finding in findings})

    def test_invalid_backtick_fence_info_in_body_cannot_create_duplicate_status(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            review_rel = "docs/code_reviews/260619_0242_invalid_fence_info.md"
            self._write_markdown(
                root,
                review_rel,
                self._single_commit_dual_lane_fixture()
                + "\n```bad`info\n**Status:** ❌ S1 blocker(ы)\n",
            )
            artifact = self._load_single(root, review_rel)[0]

            statuses = MODULE._extract_status_lines(artifact.lines)

        self.assertEqual([value for _line, value in statuses], ["✅ OK"])

    def test_list_item_fenced_status_is_not_a_header(self) -> None:
        examples = {
            "bullet": "\n- ```text\n  **Status:** ❌ S1 blocker(ы)\n  ```\n",
            "ordered": "\n1. ```text\n   **Status:** ❌ S1 blocker(ы)\n   ```\n",
        }
        for case, example in examples.items():
            with self.subTest(case=case), temporary_git_root() as tmpdir:
                root = Path(tmpdir).resolve()
                review_rel = f"docs/code_reviews/260619_0242_{case}_list_fence.md"
                self._write_markdown(
                    root,
                    review_rel,
                    self._single_commit_dual_lane_fixture() + example,
                )
                artifact = self._load_single(root, review_rel)[0]

                statuses = MODULE._extract_status_lines(artifact.lines)

            self.assertEqual([value for _line, value in statuses], ["✅ OK"])

    def test_body_spec_cannot_satisfy_header_carrier(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260329_0248_origin.md"
            target = "RANGE=abc1234..def5678 (EXCLUDE_DOCS=0)"
            self._write_origin_plan(root, plan_rel, target_snapshot=target)
            spec_rel = "docs/code_reviews/260329_0248_body_spec.md"
            spec_body = self._merge_range_dual_lane_fixture(
                target=target,
                spec=None,
            ) + f"\n```text\n**Spec:** {plan_rel}\n```\n"
            self._write_markdown(root, spec_rel, spec_body)
            spec_artifact = self._load_single(root, spec_rel)[0]

            spec_findings = MODULE.lint_review_artifacts(
                [spec_artifact],
                project_root=root,
                require_dual_lane_origin=True,
            )

        self.assertEqual(MODULE._spec_carrier(spec_artifact)[2], "missing")
        self.assertIn("missing_review_spec", {finding.code for finding in spec_findings})

    def test_body_schema_version_is_not_header_metadata(self) -> None:
        lines = (
            "# Review",
            "",
            "**Status:** ✅ OK",
            "",
            "Summary body.",
            "**Schema version:** review.v1",
        )

        self.assertEqual(MODULE._extract_schema_version_lines(lines), [])

    def test_duplicate_singleton_metadata_fields_fail_closed(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            review_rel = "docs/code_reviews/260619_0242_duplicate_metadata.md"
            duplicate_fields = (
                "**Date:** 2026-03-30 00:00 MSK\n"
                "**Target:** BUNDLE=other\n"
                "**Range:** BASE=other..head\n"
                "**Range:** BASE=third..head\n"
                "**Spec:** docs/plans/other.md\n"
                "**Spec:** docs/plans/third.md\n"
                "**Schema version:** review.v1\n"
                "**Schema version:** review.v2\n"
            )
            body = self._single_commit_dual_lane_fixture().replace(
                "**Status:** ✅ OK\n",
                duplicate_fields + "**Status:** ✅ OK\n",
                1,
            )
            self._write_markdown(root, review_rel, body)
            artifact = self._load_single(root, review_rel)[0]

            findings = MODULE.lint_review_artifacts([artifact], project_root=root)

        duplicate_findings = [
            finding for finding in findings if finding.code == "duplicate_review_header_field"
        ]
        self.assertEqual(len(duplicate_findings), 5, duplicate_findings)
        self.assertIsNone(MODULE._header_value(artifact.lines, MODULE.DATE_HEADER_RE)[0])
        self.assertIsNone(MODULE._header_value(artifact.lines, MODULE.TARGET_HEADER_RE)[0])
        self.assertIsNone(MODULE._header_value(artifact.lines, MODULE.RANGE_HEADER_RE)[0])
        self.assertIsNone(MODULE._header_value(artifact.lines, MODULE.SPEC_HEADER_RE)[0])
        self.assertIsNone(MODULE._header_value(artifact.lines, MODULE.SCHEMA_VERSION_HEADER_RE)[0])

    def test_whitespace_normalized_duplicate_status_fails_closed(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            review_rel = "docs/code_reviews/260619_0242_normalized_duplicate_status.md"
            body = self._single_commit_dual_lane_fixture().replace(
                "**Status:** ✅ OK\n",
                "**Status:** ✅ OK\n**Status :** ❌ S1 blocker(ы)\n",
                1,
            )
            self._write_markdown(root, review_rel, body)
            artifact = self._load_single(root, review_rel)[0]

            findings = MODULE.lint_review_artifacts([artifact], project_root=root)

        self.assertIn(
            "duplicate_review_header_field",
            {finding.code for finding in findings},
        )

    def test_lone_noncanonical_status_emits_header_finding(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            review_rel = "docs/code_reviews/260619_0242_noncanonical_status.md"
            self._write_markdown(root, review_rel, "# Review\n\n**Status :** ✅ OK\n")
            artifact = self._load_single(root, review_rel)[0]

            findings = MODULE.lint_review_artifacts([artifact], project_root=root)

        self.assertIn(
            "noncanonical_review_header_field",
            {finding.code for finding in findings},
        )

    def test_final_dual_lane_rejects_projection_block_as_target_snapshot_proof(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260329_0248_origin.md"
            self._write_markdown(
                root,
                plan_rel,
                dedent(
                    """\
                    # Plan

                    ## Evidence
                    - Compatibility projection block: target_snapshot=`BUNDLE=staged`
                    """
                ),
            )
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0248_projection_snapshot.md",
                self._single_commit_dual_lane_fixture(target="BUNDLE=staged"),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260329_0248_projection_snapshot.md"),
                project_root=root,
                origin_plan=plan_rel,
                require_dual_lane_origin=True,
            )

        messages = [finding.message for finding in findings]
        self.assertTrue(any(finding.code == "missing_plan_resident_risk_lane" for finding in findings), findings)
        self.assertTrue(any("projection blocks are not accepted" in message for message in messages), messages)

    def test_final_dual_lane_accepts_terminal_target_plan_fallback(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260329_0248_origin.md"
            target = f"BUNDLE=current (PLAN={plan_rel})"
            plan_path = self._write_origin_plan(root, plan_rel, target_snapshot=target)
            plan_path.write_text(
                plan_path.read_text(encoding="utf-8").replace(
                    "# Plan\n", "# Plan\n\n**Status:** Done\n", 1
                ),
                encoding="utf-8",
            )
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0248_target_plan_fallback.md",
                self._single_commit_dual_lane_fixture(target=target),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260329_0248_target_plan_fallback.md"),
                project_root=root,
                require_dual_lane_origin=True,
            )

        self.assertEqual(findings, [])

    def test_main_accepts_origin_plan_argument_for_dual_lane_review(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260329_0248_origin.md"
            review_rel = "docs/code_reviews/260329_0248_main_origin.md"
            self._write_origin_plan(root, plan_rel, target_snapshot="BUNDLE=staged")
            self._write_markdown(root, review_rel, self._single_commit_dual_lane_fixture(target="BUNDLE=staged"))
            stdout = io.StringIO()

            with mock.patch("sys.stdout", stdout):
                result = MODULE.main(["--project-root", str(root), "--origin-plan", plan_rel, review_rel])

        self.assertEqual(result, 0)
        self.assertEqual(stdout.getvalue().strip(), "review-artifact-lint: OK")

    def test_non_dual_artifact_gets_no_new_cross_file_findings(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0248_ordinary_final.md",
                dedent(
                    """\
                    # Code review — single commit

                    **Date:** 29.03.2026 02:49 MSK
                    **Target:** BUNDLE=staged
                    **Status:** ✅ OK
                    """
                ),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260329_0248_ordinary_final.md"),
                project_root=root,
                require_dual_lane_origin=True,
            )

        cross_file_codes = {
            "missing_dual_lane_origin_plan",
            "missing_dual_lane_origin_plan_file",
            "missing_plan_resident_risk_lane",
            "ambiguous_plan_resident_risk_lane",
            "missing_review_target_snapshot",
            "dual_lane_target_snapshot_mismatch",
        }
        self.assertFalse(cross_file_codes.intersection({finding.code for finding in findings}), findings)

    def test_blocker_status_without_canonical_b_refs_in_synthesis_is_reported(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0248_missing_bref.md",
                self._single_commit_dual_lane_fixture(
                    status="❌ S1 blocker(ы)",
                    risk_findings="`risk:R1 severity=S1 domain=correctness summary=critical regression evidence=review.md#risk`",
                    canonical_mapping="`risk:R1 -> open`",
                    synthesis_provenance_records=self._complete_synthesis_provenance_record(
                        finding="risk:R1",
                        source_lane="reviewer_code_risk",
                        canonical_ref="docs/code_reviews/260329_0248_missing_bref.md#S1-Blocker",
                        disposition="accepted_blocker",
                    ),
                ),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260329_0248_missing_bref.md")
            )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "missing_canonical_blocker_refs")
        self.assertIn("B<N>", findings[0].message)

    def test_single_commit_visual_section_does_not_require_merge_range_visual_fields(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0249_single_commit_visual.md",
                self._single_commit_dual_lane_fixture(
                    extra_sections=dedent(
                        """\
                        ## Визуальные доказательства
                        - Visual env: `Modes=primary` `Port=8054`
                        """
                    )
                ),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260329_0249_single_commit_visual.md")
            )

        self.assertEqual(findings, [])

    def test_single_commit_rerun_with_visual_env_stays_outside_merge_range_visual_family(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0250_single_commit_rerun_visual.md",
                self._single_commit_dual_lane_fixture(
                    extra_sections=dedent(
                        """\
                        ## Контекст rerun
                        - Rerun mode: `focused`
                        - Baseline artifact: `docs/code_reviews/260329_0001_previous.md`

                        ## Визуальные доказательства
                        - Visual env: `Modes=primary` `Port=8054`
                        """
                    )
                ),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260329_0250_single_commit_rerun_visual.md")
            )

        self.assertEqual(findings, [])

    def test_single_commit_source_scenarios_with_visual_env_stay_optional_without_post_merge_visual_sanity(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_asset(
                root,
                "docs/code_reviews/assets/260329_0251_single_commit_source_scenarios/primary_01.png",
            )
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0251_single_commit_source_scenarios.md",
                self._single_commit_dual_lane_fixture(
                    extra_sections=dedent(
                        """\
                        ## Visual evidence
                        - Visual env: `Modes=primary` `Port=8054`
                        - Source scenarios: `docs/plans/260329_0251_single_commit_source_scenarios.md#visual`
                        - `docs/code_reviews/assets/260329_0251_single_commit_source_scenarios/primary_01.png` — Proves: single-commit screenshot lane
                        """
                    )
                ),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260329_0251_single_commit_source_scenarios.md")
            )

        self.assertEqual(findings, [])

    def test_single_commit_visual_lane_requires_visual_env(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0252_single_commit_missing_visual_env.md",
                self._single_commit_dual_lane_fixture(
                    extra_sections=dedent(
                        """\
                        ## Visual evidence
                        - Source scenarios: `docs/plans/260329_0252_single_commit_missing_visual_env.md#visual`
                        """
                    )
                ),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260329_0252_single_commit_missing_visual_env.md")
            )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "missing_visual_receipt_fields")
        self.assertIn("visual env", findings[0].message)

    def test_single_commit_screenshot_backed_visual_lane_requires_visual_env(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_asset(
                root,
                "docs/code_reviews/assets/260329_0253_single_commit_screenshots_only/primary_01.png",
            )
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0253_single_commit_screenshots_only.md",
                self._single_commit_dual_lane_fixture(
                    extra_sections=dedent(
                        """\
                        ## Visual evidence
                        - Source scenarios: `docs/plans/260329_0253_single_commit_screenshots_only.md#visual`
                        - `docs/code_reviews/assets/260329_0253_single_commit_screenshots_only/primary_01.png` — Proves: screenshot-backed single-commit lane
                        """
                    )
                ),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260329_0253_single_commit_screenshots_only.md")
            )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "missing_visual_receipt_fields")
        self.assertIn("visual env", findings[0].message)

    def test_visual_asset_literal_repo_path_with_existing_file_passes(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_asset(
                root,
                "docs/code_reviews/assets/260329_0255_literal_asset/primary_01.png",
            )
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0255_literal_asset.md",
                self._single_commit_dual_lane_fixture(
                    extra_sections=dedent(
                        """\
                        ## Visual evidence
                        - Visual env: `Modes=primary` `Port=8054`
                        - `assets/260329_0255_literal_asset/primary_01.png` — Proves: literal repo-relative asset ref stays bundle-safe
                        """
                    )
                ),
            )

            findings = MODULE.lint_review_artifacts(self._load_single(root, "docs/code_reviews/260329_0255_literal_asset.md"))

        self.assertEqual(findings, [])

    def test_missing_visual_asset_file_is_reported(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0256_missing_asset.md",
                self._single_commit_dual_lane_fixture(
                    extra_sections=dedent(
                        """\
                        ## Visual evidence
                        - Visual env: `Modes=primary` `Port=8054`
                        - `assets/260329_0256_missing_asset/primary_01.png` — Proves: missing asset should be red
                        """
                    )
                ),
            )

            findings = MODULE.lint_review_artifacts(self._load_single(root, "docs/code_reviews/260329_0256_missing_asset.md"))

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "missing_visual_asset_file")
        self.assertIn("assets/260329_0256_missing_asset/primary_01.png", findings[0].message)

    def test_ambiguous_visual_asset_ref_is_reported(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0257_ambiguous_asset.md",
                self._single_commit_dual_lane_fixture(
                    extra_sections=dedent(
                        """\
                        ## Visual evidence
                        - Visual env: `Modes=primary` `Port=8054`
                        - `<path>` — `assets/<REVIEW_BASENAME>/primary_01.png` — Proves: ambiguous path wording should be red
                        """
                    )
                ),
            )

            findings = MODULE.lint_review_artifacts(self._load_single(root, "docs/code_reviews/260329_0257_ambiguous_asset.md"))

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "invalid_visual_asset_ref")
        self.assertIn("one exact literal repo path", findings[0].message)

    def test_empty_visual_asset_file_is_reported(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_asset(
                root,
                "docs/code_reviews/assets/260329_0258_empty_asset/primary_01.png",
                body=b"",
            )
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0258_empty_asset.md",
                self._single_commit_dual_lane_fixture(
                    extra_sections=dedent(
                        """\
                        ## Visual evidence
                        - Visual env: `Modes=primary` `Port=8054`
                        - `assets/260329_0258_empty_asset/primary_01.png` — Proves: empty asset should be red
                        """
                    )
                ),
            )

            findings = MODULE.lint_review_artifacts(self._load_single(root, "docs/code_reviews/260329_0258_empty_asset.md"))

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "empty_visual_asset_file")
        self.assertIn("assets/260329_0258_empty_asset/primary_01.png", findings[0].message)

    def test_absolute_visual_asset_path_is_reported_as_invalid(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0259_absolute_asset.md",
                self._single_commit_dual_lane_fixture(
                    extra_sections=dedent(
                        """\
                        ## Visual evidence
                        - Visual env: `Modes=primary` `Port=8054`
                        - `/tmp/primary_01.png` — Proves: absolute filesystem path must be red
                        """
                    )
                ),
            )

            findings = MODULE.lint_review_artifacts(self._load_single(root, "docs/code_reviews/260329_0259_absolute_asset.md"))

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "invalid_visual_asset_ref")
        self.assertIn("one exact literal repo path", findings[0].message)

    def test_bare_filename_visual_asset_path_is_reported_as_invalid(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/code_reviews/260329_0300_bare_filename_asset.md",
                self._single_commit_dual_lane_fixture(
                    extra_sections=dedent(
                        """\
                        ## Visual evidence
                        - Visual env: `Modes=primary` `Port=8054`
                        - `primary_01.png` — Proves: bare filename must be red
                        """
                    )
                ),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/code_reviews/260329_0300_bare_filename_asset.md")
            )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "invalid_visual_asset_ref")
        self.assertIn("one exact literal repo path", findings[0].message)

    def test_doc_review_merge_range_without_rerun_context_is_allowed(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/doc_reviews/260329_0254_doc_merge_range.md",
                dedent(
                    f"""\
                    # Doc review — merge-range (abc1234..def5678)

                    **Date:** 29.03.2026 02:50 MSK
                    **Range:** BASE=abc1234 .. HEAD=def5678
                    **Scope:** docs-only
                    **Status:** ✅ OK

                    {self._russian_summary("✅ OK")}

                    {self._dual_lane_sections("BASE=abc1234 .. HEAD=def5678", aggregate_status="✅ OK")}
                    {self._exact_bundle_hygiene_section()}
                    """
                ),
            )

            findings = MODULE.lint_review_artifacts(self._load_single(root, "docs/doc_reviews/260329_0254_doc_merge_range.md"))

        self.assertEqual(findings, [])

    def test_doc_review_rejects_homebrew_command_evidence(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/doc_reviews/260704_2044_doc_review_homebrew_command.md",
                dedent(
                    f"""\
                    # Doc review — merge-range (abc1234..def5678)

                    **Date:** 05.07.2026 14:30 MSK
                    **Range:** BASE=abc1234 .. HEAD=def5678
                    **Scope:** docs-only
                    **Status:** ✅ OK

                    ОК: docs-only review artifact держит русскую summary-строку и exact-bundle hygiene receipt.

                    {self._dual_lane_sections("BASE=abc1234 .. HEAD=def5678", aggregate_status="✅ OK")}
                    {self._exact_bundle_hygiene_section()}

                    ## Команды / evidence
                    - Command: `{self._homebrew_pybin_literal()} -B scripts/test_review_artifact_lint.py` -> exit 0
                    """
                ),
            )

            findings = MODULE.lint_review_artifacts(self._load_single(root, "docs/doc_reviews/260704_2044_doc_review_homebrew_command.md"))

        self.assertEqual({finding.code for finding in findings}, {"expanded_homebrew_python_command_evidence"})

    def test_doc_review_accepts_portable_command_evidence(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/doc_reviews/260704_2044_doc_review_portable_command.md",
                dedent(
                    f"""\
                    # Doc review — merge-range (abc1234..def5678)

                    **Date:** 05.07.2026 14:31 MSK
                    **Range:** BASE=abc1234 .. HEAD=def5678
                    **Scope:** docs-only
                    **Status:** ✅ OK

                    ОК: docs-only review artifact держит русскую summary-строку и exact-bundle hygiene receipt.

                    {self._dual_lane_sections("BASE=abc1234 .. HEAD=def5678", aggregate_status="✅ OK")}
                    {self._exact_bundle_hygiene_section()}

                    ## Команды / evidence
                    - Command: `$PYBIN -B scripts/test_review_artifact_lint.py` -> exit 0
                    """
                ),
            )

            findings = MODULE.lint_review_artifacts(self._load_single(root, "docs/doc_reviews/260704_2044_doc_review_portable_command.md"))

        self.assertEqual(findings, [])

    def test_main_uses_default_template_scope(self) -> None:
        stdout = io.StringIO()
        with mock.patch("sys.stdout", stdout):
            result = MODULE.main([])

        self.assertEqual(result, 0)
        self.assertEqual(stdout.getvalue().strip(), "review-artifact-lint: OK")

    def test_current_merge_notes_schema_version_is_accepted(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/reviews/_template_merge_notes.md",
                dedent(
                    """\
                    # Review: Merge notes — schema current

                    **Date:** 19.04.2026 11:06 MSK
                    **BASE:** deadbee
                    **HEAD:** feed123
                    **Topic:** schema current
                    **Status:** Draft
                    **Schema version:** review.v1

                    ## Что изменилось (human-readable)
                    - schema current fixture
                    """
                ),
            )

            findings = MODULE.lint_review_artifacts(self._load_single(root, "docs/reviews/_template_merge_notes.md"))

        self.assertEqual(findings, [])

    def test_current_merge_notes_done_status_is_accepted(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/reviews/260419_1106_merge_notes_done.md",
                dedent(
                    """\
                    # Review: Merge notes — schema current

                    **Date:** 19.04.2026 11:06 MSK
                    **BASE:** deadbee
                    **HEAD:** feed123
                    **Topic:** schema current
                    **Status:** ✅ Done
                    **Schema version:** review.v1

                    ## Что изменилось (human-readable)
                    - schema current fixture
                    """
                ),
            )

            findings = MODULE.lint_review_artifacts(self._load_single(root, "docs/reviews/260419_1106_merge_notes_done.md"))

        self.assertEqual(findings, [])

    def test_merge_notes_reject_code_review_ok_status(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/reviews/260419_1106_merge_notes_wrong_status.md",
                dedent(
                    """\
                    # Review: Merge notes — schema current

                    **Date:** 19.04.2026 11:06 MSK
                    **BASE:** deadbee
                    **HEAD:** feed123
                    **Topic:** schema current
                    **Status:** ✅ OK
                    **Schema version:** review.v1

                    ## Что изменилось (human-readable)
                    - schema current fixture
                    """
                ),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/reviews/260419_1106_merge_notes_wrong_status.md")
            )

        self.assertEqual([finding.code for finding in findings], ["invalid_review_status_family"])
        self.assertIn("Merge notes status", findings[0].message)

    def test_merge_notes_reject_non_template_placeholder_status(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/reviews/260419_1106_merge_notes_placeholder_status.md",
                dedent(
                    """\
                    # Review: Merge notes — schema current

                    **Date:** 19.04.2026 11:06 MSK
                    **BASE:** deadbee
                    **HEAD:** feed123
                    **Topic:** schema current
                    **Status:** Draft | ✅ Done
                    **Schema version:** review.v1

                    ## Что изменилось (human-readable)
                    - schema current fixture
                    """
                ),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/reviews/260419_1106_merge_notes_placeholder_status.md")
            )

        self.assertEqual([finding.code for finding in findings], ["invalid_review_status_family"])
        self.assertIn("only valid in `_template_*` files", findings[0].message)

    def test_versionless_non_template_merge_notes_is_legacy(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/reviews/260419_1107_merge_notes_schema_legacy.md",
                dedent(
                    """\
                    # Review: Merge notes — schema legacy

                    **Date:** 19.04.2026 11:07 MSK
                    **BASE:** deadbee
                    **HEAD:** feed123
                    **Topic:** schema legacy
                    **Status:** Draft

                    ## Что изменилось (human-readable)
                    - schema legacy fixture
                    """
                ),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/reviews/260419_1107_merge_notes_schema_legacy.md")
            )

        self.assertEqual(findings, [])

    def test_wrong_merge_notes_schema_version_is_reported(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_markdown(
                root,
                "docs/reviews/260419_1108_merge_notes_schema_unsupported.md",
                dedent(
                    """\
                    # Review: Merge notes — schema unsupported

                    **Date:** 19.04.2026 11:08 MSK
                    **BASE:** deadbee
                    **HEAD:** feed123
                    **Topic:** schema unsupported
                    **Status:** Draft
                    **Schema version:** plan.v1

                    ## Что изменилось (human-readable)
                    - schema unsupported fixture
                    """
                ),
            )

            findings = MODULE.lint_review_artifacts(
                self._load_single(root, "docs/reviews/260419_1108_merge_notes_schema_unsupported.md")
            )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "unsupported_schema_version")
        self.assertIn("Unsupported review schema version", findings[0].message)

    def test_same_file_rerun_closeout_current_red_blocks(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260505_0100_same_file_guard.md"
            review_rel = "docs/code_reviews/260505_0100_same_file_guard.md"
            self._write_same_file_plan(root, plan_rel, review_rel)
            self._write_markdown(
                root,
                review_rel,
                self._same_file_review_fixture(
                    status="❌ S1 blocker(ы)",
                    aggregate_status="❌ S1 blocker(ы)",
                    target="PLAN=docs/plans/260505_0100_same_file_guard.md",
                    blocker_state="open",
                ),
            )

            result = MODULE.classify_same_file_rerun_closeout(root / plan_rel, root / review_rel, project_root=root)

        self.assertEqual(result.state, "current_red")
        self.assertIn("Current review header or synthesis", result.reason)

    def test_sortable_timestamp_normalizes_supported_timezones_and_rejects_invalid_values(self) -> None:
        self.assertEqual(MODULE._sortable_timestamp_value("2026-07-23 00:39 MSK"), "20260722213900")
        # Engine stamps carry the local numeric offset; legacy `MSK` stamps above stay readable.
        self.assertEqual(MODULE._sortable_timestamp_value("2026-07-23 00:39 +0300"), "20260722213900")
        self.assertEqual(MODULE._sortable_timestamp_value("23.07.2026 00:39 +0300"), "20260722213900")
        self.assertEqual(MODULE._sortable_timestamp_value("23.07.2026 00:39 MSK"), "20260722213900")
        self.assertEqual(MODULE._sortable_timestamp_value("2026-07-23 06:39 +0900"), "20260722213900")
        self.assertEqual(MODULE._sortable_timestamp_value("2026-07-22T22:07:21Z"), "20260722220721")
        self.assertEqual(MODULE._sortable_timestamp_value("2026-07-23T01:15:00+03:00"), "20260722221500")
        self.assertEqual(MODULE._sortable_timestamp_value("2026-07-23T01:15:00+0300"), "20260722221500")
        self.assertEqual(MODULE._sortable_timestamp_value("2026-07-23T01:15:00-0430"), "20260723054500")
        self.assertIsNone(MODULE._sortable_timestamp_value("2026-02-30T01:15:00Z"))
        self.assertIsNone(MODULE._sortable_timestamp_value("2026-07-23T01:15:00+2460"))
        self.assertIsNone(MODULE._sortable_timestamp_value("2026-07-22T22:07:21Z+03:00"))
        self.assertIsNone(MODULE._sortable_timestamp_value("2026-07-22T22:07:21Z MSK"))
        self.assertIsNone(MODULE._sortable_timestamp_value("2026-07-22T22:07:21+03:00-04:00"))
        self.assertIsNone(MODULE._sortable_timestamp_value("2026-07-22T22:07:21Z UTC+03:00"))
        self.assertIsNone(MODULE._sortable_timestamp_value("2026-07-22T22:07:21Z GMT"))
        self.assertEqual(MODULE._sortable_timestamp_value("2026-07-22T22:07:21.123Z"), "20260722220721")
        self.assertTrue(MODULE._sortable_timestamp_has_explicit_timezone("2026-07-22T22:07:21.123Z"))
        for boundary in ",.;:)]}>`'\"":
            with self.subTest(boundary=boundary):
                self.assertIsNone(
                    MODULE._sortable_timestamp_value(f"2026-07-22T22:07:21{boundary} UTC+03:00")
                )
                self.assertEqual(
                    MODULE._sortable_timestamp_value(f"2026-07-22T22:07:21Z{boundary}"),
                    "20260722220721",
                )
        self.assertIsNone(MODULE._sortable_timestamp_value("2026-07-22T22:07:21) GMT"))
        self.assertIsNone(MODULE._sortable_timestamp_value("2026-07-22T22:07.123Z"))
        self.assertIsNone(MODULE._sortable_timestamp_value("UTC+14:00 2026-07-22T22:07:21"))
        self.assertIsNone(MODULE._sortable_timestamp_value("GMT) 2026-07-22T22:07:21"))
        self.assertEqual(MODULE._sortable_timestamp_value("(2026-07-22T22:07:21Z)."), "20260722220721")
        self.assertEqual(
            MODULE._sortable_timestamp_value(
                "reviewer_code_risk:sample:20260722T220721Z",
                allow_embedded_prefix=True,
            ),
            "20260722220721",
        )

    def test_same_file_rerun_closeout_stale_red_after_fix_routes_to_reviewer_rewrite(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260505_0107_same_file_guard.md"
            review_rel = "docs/code_reviews/260505_0107_same_file_guard.md"
            extra_notes = dedent(
                f"""\
                - Stale note (2026-05-07 03:00): same review file `{review_rel}` remains red until rerun
                - Rerun note (2026-05-07 03:05): same review file `{review_rel}` will be rewritten in place

                ## Evidence

                - reviewer_code_risk lane-run artifact:
                  ```json
                  {json.dumps({"lane_id": "reviewer_code_risk", "run_id": "reviewer_code_risk:sample:20260507T030600", "target_snapshot": f"PLAN={plan_rel}", "lane_status": "complete", "findings": [], "current": True}, indent=2)}
                  ```
                """
            )
            self._write_same_file_plan(root, plan_rel, review_rel, extra_notes=extra_notes)
            self._write_markdown(
                root,
                review_rel,
                self._same_file_review_fixture(
                    status="❌ S1 blocker(ы)",
                    aggregate_status="❌ S1 blocker(ы)",
                    target=f"PLAN={plan_rel}",
                    blocker_state="open",
                ),
            )

            result = MODULE.classify_same_file_rerun_closeout(root / plan_rel, root / review_rel, project_root=root)

        self.assertEqual(result.state, "stale_red_after_fix")
        self.assertIn("same-file Reviewer rewrite", result.reason)

    def test_same_file_rerun_closeout_cross_midnight_msk_and_z_fixed_newer_routes_to_reviewer(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260505_0108_same_file_guard.md"
            review_rel = "docs/code_reviews/260505_0108_same_file_guard.md"
            extra_notes = dedent(
                f"""\
                - Stale note (2026-07-23 00:39 MSK): same review file `{review_rel}` remains red until rerun
                - Rerun note (2026-07-23 00:40 MSK): same review file `{review_rel}` will be rewritten in place

                ## Evidence

                - reviewer_code_risk lane-run artifact:
                  ```json
                  {json.dumps({"lane_id": "reviewer_code_risk", "run_id": "reviewer_code_risk:sample:20260722T220721Z", "target_snapshot": f"PLAN={plan_rel}", "lane_status": "complete", "findings": [], "current": True, "written_at": "2026-07-22T22:07:21Z"}, indent=2)}
                  ```
                """
            )
            self._write_same_file_plan(root, plan_rel, review_rel, extra_notes=extra_notes)
            self._write_markdown(
                root,
                review_rel,
                self._same_file_review_fixture(
                    status="❌ S1 blocker(ы)",
                    aggregate_status="❌ S1 blocker(ы)",
                    target=f"PLAN={plan_rel}",
                    date="2026-07-23 00:39 MSK",
                    blocker_state="open",
                ),
            )

            result = MODULE.classify_same_file_rerun_closeout(root / plan_rel, root / review_rel, project_root=root)

        self.assertEqual(result.state, "stale_red_after_fix")
        self.assertIn("same-file Reviewer rewrite", result.reason)

    def test_same_file_rerun_closeout_duplicate_timezone_fixed_evidence_stays_current_red(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260505_0114_same_file_guard.md"
            review_rel = "docs/code_reviews/260505_0114_same_file_guard.md"
            extra_notes = dedent(
                f"""\
                - Stale note (2026-07-23 00:39 MSK): same review file `{review_rel}` remains red until rerun
                - Rerun note (2026-07-23 00:40 MSK): same review file `{review_rel}` will be rewritten in place

                ## Evidence

                - reviewer_code_risk lane-run artifact:
                  ```json
                  {json.dumps({"lane_id": "reviewer_code_risk", "run_id": "reviewer_code_risk:sample:20260722T220721Z", "target_snapshot": f"PLAN={plan_rel}", "lane_status": "complete", "findings": [], "current": True, "written_at": "2026-07-22T22:07:21Z+03:00"}, indent=2)}
                  ```
                """
            )
            self._write_same_file_plan(root, plan_rel, review_rel, extra_notes=extra_notes)
            self._write_markdown(
                root,
                review_rel,
                self._same_file_review_fixture(
                    status="❌ S1 blocker(ы)",
                    aggregate_status="❌ S1 blocker(ы)",
                    target=f"PLAN={plan_rel}",
                    date="2026-07-23 00:39 MSK",
                    blocker_state="open",
                ),
            )

            result = MODULE.classify_same_file_rerun_closeout(root / plan_rel, root / review_rel, project_root=root)

        self.assertEqual(result.state, "current_red")
        self.assertIn("freshness ordering against fixed risk-lane evidence is unavailable", result.reason)
        self.assertIn("current-red/Coder", result.reason)

    def test_same_file_rerun_closeout_non_consumed_timezone_fixed_evidence_stays_current_red(self) -> None:
        for written_at in (
            "2026-07-22T23:00:00,UTC+14:00",
            "UTC+14:00 2026-07-22T23:00:00",
        ):
            with self.subTest(written_at=written_at), temporary_git_root() as tmpdir:
                root = Path(tmpdir).resolve()
                plan_rel = "docs/plans/260505_0115_same_file_guard.md"
                review_rel = "docs/code_reviews/260505_0115_same_file_guard.md"
                extra_notes = dedent(
                    f"""\
                    - Stale note (2026-07-22 22:00 UTC): same review file `{review_rel}` remains red until rerun
                    - Rerun note (2026-07-22 22:01 UTC): same review file `{review_rel}` will be rewritten in place

                    ## Evidence

                    - reviewer_code_risk lane-run artifact:
                      ```json
                      {json.dumps({"lane_id": "reviewer_code_risk", "run_id": "reviewer_code_risk:sample:20260722T230000Z", "target_snapshot": f"PLAN={plan_rel}", "lane_status": "complete", "findings": [], "current": True, "written_at": written_at}, indent=2)}
                      ```
                    """
                )
                self._write_same_file_plan(root, plan_rel, review_rel, extra_notes=extra_notes)
                self._write_markdown(
                    root,
                    review_rel,
                    self._same_file_review_fixture(
                        status="❌ S1 blocker(ы)",
                        aggregate_status="❌ S1 blocker(ы)",
                        target=f"PLAN={plan_rel}",
                        date="2026-07-22T22:00:00Z",
                        blocker_state="open",
                    ),
                )

                result = MODULE.classify_same_file_rerun_closeout(
                    root / plan_rel,
                    root / review_rel,
                    project_root=root,
                )

            self.assertEqual(result.state, "current_red")
            self.assertIn("freshness ordering against fixed risk-lane evidence is unavailable", result.reason)
            self.assertIn("current-red/Coder", result.reason)

    def test_same_file_rerun_closeout_newer_contracts_blocker_stays_current_red(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260505_0110_same_file_guard.md"
            review_rel = "docs/code_reviews/260505_0110_same_file_guard.md"
            extra_notes = dedent(
                f"""\
                - Stale note (2026-05-07 03:08): same review file `{review_rel}` remains red until rerun
                - Rerun note (2026-05-07 03:09): same review file `{review_rel}` will be rewritten in place

                ## Evidence

                - reviewer_code_risk lane-run artifact:
                  ```json
                  {json.dumps({"lane_id": "reviewer_code_risk", "run_id": "reviewer_code_risk:sample:20260507T030600", "target_snapshot": f"PLAN={plan_rel}", "lane_status": "complete", "findings": [], "current": True}, indent=2)}
                  ```
                """
            )
            self._write_same_file_plan(root, plan_rel, review_rel, extra_notes=extra_notes)
            self._write_markdown(
                root,
                review_rel,
                self._same_file_review_fixture(
                    status="❌ S1 blocker(ы)",
                    aggregate_status="❌ S1 blocker(ы)",
                    target=f"PLAN={plan_rel}",
                    date="2026-05-07 03:07 MSK",
                    blocker_state="open",
                ),
            )

            result = MODULE.classify_same_file_rerun_closeout(root / plan_rel, root / review_rel, project_root=root)

        self.assertEqual(result.state, "current_red")
        self.assertIn("newer than the selected fixed risk-lane evidence", result.reason)
        self.assertIn("current-red/Coder", result.reason)

    def test_same_file_rerun_closeout_cross_midnight_numeric_offset_blocker_newer_stays_current_red(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260505_0113_same_file_guard.md"
            review_rel = "docs/code_reviews/260505_0113_same_file_guard.md"
            extra_notes = dedent(
                f"""\
                - Stale note (2026-07-23 01:15 MSK): same review file `{review_rel}` remains red until rerun
                - Rerun note (2026-07-23 01:16 MSK): same review file `{review_rel}` will be rewritten in place

                ## Evidence

                - reviewer_code_risk lane-run artifact:
                  ```json
                  {json.dumps({"lane_id": "reviewer_code_risk", "run_id": "reviewer_code_risk:sample:20260722T220721Z", "target_snapshot": f"PLAN={plan_rel}", "lane_status": "complete", "findings": [], "current": True, "written_at": "2026-07-22T22:07:21+00:00"}, indent=2)}
                  ```
                """
            )
            self._write_same_file_plan(root, plan_rel, review_rel, extra_notes=extra_notes)
            self._write_markdown(
                root,
                review_rel,
                self._same_file_review_fixture(
                    status="❌ S1 blocker(ы)",
                    aggregate_status="❌ S1 blocker(ы)",
                    target=f"PLAN={plan_rel}",
                    date="2026-07-23 01:15 MSK",
                    blocker_state="open",
                ),
            )

            result = MODULE.classify_same_file_rerun_closeout(root / plan_rel, root / review_rel, project_root=root)

        self.assertEqual(result.state, "current_red")
        self.assertIn("newer than the selected fixed risk-lane evidence", result.reason)
        self.assertIn("current-red/Coder", result.reason)

    def test_same_file_rerun_closeout_same_minute_ordering_stays_current_red(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260505_0112_same_file_guard.md"
            review_rel = "docs/code_reviews/260505_0112_same_file_guard.md"
            extra_notes = dedent(
                f"""\
                - Stale note (2026-05-07 03:08): same review file `{review_rel}` remains red until rerun
                - Rerun note (2026-05-07 03:09): same review file `{review_rel}` will be rewritten in place

                ## Evidence

                - reviewer_code_risk lane-run artifact:
                  ```json
                  {json.dumps({"lane_id": "reviewer_code_risk", "run_id": "reviewer_code_risk:sample:20260507T030644", "target_snapshot": f"PLAN={plan_rel}", "lane_status": "complete", "findings": [], "current": True}, indent=2)}
                  ```
                """
            )
            self._write_same_file_plan(root, plan_rel, review_rel, extra_notes=extra_notes)
            self._write_markdown(
                root,
                review_rel,
                self._same_file_review_fixture(
                    status="❌ S1 blocker(ы)",
                    aggregate_status="❌ S1 blocker(ы)",
                    target=f"PLAN={plan_rel}",
                    date="2026-05-07 03:06 MSK",
                    blocker_state="open",
                ),
            )

            result = MODULE.classify_same_file_rerun_closeout(root / plan_rel, root / review_rel, project_root=root)

        self.assertEqual(result.state, "current_red")
        self.assertIn("same-minute freshness ordering", result.reason)
        self.assertIn("current-red/Coder", result.reason)

    def test_same_file_rerun_closeout_open_blocker_with_ambiguous_order_stays_current_red(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260505_0111_same_file_guard.md"
            review_rel = "docs/code_reviews/260505_0111_same_file_guard.md"
            extra_notes = dedent(
                f"""\
                - Stale note (2026-05-07 03:00): same review file `{review_rel}` remains red until rerun
                - Rerun note (2026-05-07 03:05): same review file `{review_rel}` will be rewritten in place

                ## Evidence

                - reviewer_code_risk lane-run artifact:
                  ```json
                  {json.dumps({"lane_id": "reviewer_code_risk", "run_id": "reviewer_code_risk:sample:not-sortable", "target_snapshot": f"PLAN={plan_rel}", "lane_status": "complete", "findings": [], "current": True}, indent=2)}
                  ```
                """
            )
            self._write_same_file_plan(root, plan_rel, review_rel, extra_notes=extra_notes)
            self._write_markdown(
                root,
                review_rel,
                self._same_file_review_fixture(
                    status="❌ S1 blocker(ы)",
                    aggregate_status="❌ S1 blocker(ы)",
                    target=f"PLAN={plan_rel}",
                    date="not-sortable",
                    blocker_state="open",
                ),
            )

            result = MODULE.classify_same_file_rerun_closeout(root / plan_rel, root / review_rel, project_root=root)

        self.assertEqual(result.state, "current_red")
        self.assertIn("freshness ordering", result.reason)

    def test_same_file_rerun_closeout_stale_red_requires_successful_risk_lane_status(self) -> None:
        cases = ("blocked", "incomplete", "unknown", None)
        for lane_status in cases:
            with self.subTest(lane_status=lane_status), temporary_git_root() as tmpdir:
                root = Path(tmpdir).resolve()
                plan_rel = "docs/plans/260505_0109_same_file_guard.md"
                review_rel = "docs/code_reviews/260505_0109_same_file_guard.md"
                payload = {
                    "lane_id": "reviewer_code_risk",
                    "run_id": "reviewer_code_risk:sample:20260507T030600",
                    "target_snapshot": f"PLAN={plan_rel}",
                    "findings": [],
                    "current": True,
                }
                if lane_status is not None:
                    payload["lane_status"] = lane_status
                extra_notes = dedent(
                    f"""\
                    - Stale note (2026-05-07 03:00): same review file `{review_rel}` remains red until rerun
                    - Rerun note (2026-05-07 03:05): same review file `{review_rel}` will be rewritten in place

                    ## Evidence

                    - reviewer_code_risk lane-run artifact:
                      ```json
                      {json.dumps(payload, indent=2)}
                      ```
                    """
                )
                self._write_same_file_plan(root, plan_rel, review_rel, extra_notes=extra_notes)
                self._write_markdown(
                    root,
                    review_rel,
                    self._same_file_review_fixture(
                        status="❌ S1 blocker(ы)",
                        aggregate_status="❌ S1 blocker(ы)",
                        target=f"PLAN={plan_rel}",
                        blocker_state="open",
                    ),
                )

                result = MODULE.classify_same_file_rerun_closeout(root / plan_rel, root / review_rel, project_root=root)

                self.assertEqual(result.state, "current_red")
                self.assertIn("lane_status", result.reason)

    def test_same_file_rerun_closeout_stale_red_snapshot_mismatch_remains_current_red(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260505_0108_same_file_guard.md"
            review_rel = "docs/code_reviews/260505_0108_same_file_guard.md"
            extra_notes = dedent(
                f"""\
                - Stale note (2026-05-07 03:00): same review file `{review_rel}` remains red until rerun
                - Rerun note (2026-05-07 03:05): same review file `{review_rel}` will be rewritten in place

                ## Evidence

                - reviewer_code_risk lane-run artifact:
                  ```json
                  {json.dumps({"lane_id": "reviewer_code_risk", "run_id": "reviewer_code_risk:sample:20260507T030600", "target_snapshot": "PLAN=docs/plans/other.md", "lane_status": "complete", "findings": [], "current": True}, indent=2)}
                  ```
                """
            )
            self._write_same_file_plan(root, plan_rel, review_rel, extra_notes=extra_notes)
            self._write_markdown(
                root,
                review_rel,
                self._same_file_review_fixture(
                    status="❌ S1 blocker(ы)",
                    aggregate_status="❌ S1 blocker(ы)",
                    target=f"PLAN={plan_rel}",
                    blocker_state="open",
                ),
            )

            result = MODULE.classify_same_file_rerun_closeout(root / plan_rel, root / review_rel, project_root=root)

        self.assertEqual(result.state, "current_red")
        self.assertIn("target snapshot does not match", result.reason)

    def test_same_file_rerun_closeout_active_quarantine_without_rerun_result_blocks(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260505_0101_same_file_guard.md"
            review_rel = "docs/code_reviews/260505_0101_same_file_guard.md"
            extra_notes = dedent(
                f"""\
                - Stale note (2026-05-07 03:00): same review file `{review_rel}` remains red until rerun
                - Rerun note (2026-05-07 03:05): same review file `{review_rel}` will be rewritten in place
                """
            )
            self._write_same_file_plan(root, plan_rel, review_rel, extra_notes=extra_notes)
            self._write_markdown(
                root,
                review_rel,
                self._same_file_review_fixture(
                    status="✅ OK",
                    target="PLAN=docs/plans/260505_0101_same_file_guard.md",
                ),
            )

            result = MODULE.classify_same_file_rerun_closeout(root / plan_rel, root / review_rel, project_root=root)

        self.assertEqual(result.state, "needs_reviewer_rerun")
        self.assertIn("Active stale/rerun quarantine", result.reason)

    def test_same_file_rerun_closeout_current_green_passes_without_quarantine(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260505_0102_same_file_guard.md"
            review_rel = "docs/code_reviews/260505_0102_same_file_guard.md"
            self._write_same_file_plan(root, plan_rel, review_rel)
            self._write_markdown(
                root,
                review_rel,
                self._same_file_review_fixture(
                    status="✅ OK",
                    target="PLAN=docs/plans/260505_0102_same_file_guard.md",
                ),
            )

            result = MODULE.classify_same_file_rerun_closeout(root / plan_rel, root / review_rel, project_root=root)

        self.assertEqual(result.state, "current_green")
        self.assertIn("green", result.reason.lower())

    def test_same_file_rerun_closeout_ignores_body_date(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260505_0102_body_date.md"
            review_rel = "docs/code_reviews/260505_0102_body_date.md"
            self._write_same_file_plan(root, plan_rel, review_rel)
            body = self._same_file_review_fixture(
                status="✅ OK",
                target=f"PLAN={plan_rel}",
            ).replace("**Date:** 2026-05-07 02:00 MSK\n", "", 1)
            self._write_markdown(
                root,
                review_rel,
                body + "\nSummary body.\n**Date:** 2026-05-07 02:00 MSK\n",
            )

            with mock.patch.object(
                MODULE.plan_lint,
                "review_artifacts_section_has_stale_rerun_note",
                return_value=False,
            ) as stale_readback:
                result = MODULE.classify_same_file_rerun_closeout(
                    root / plan_rel,
                    root / review_rel,
                    project_root=root,
                )

        self.assertEqual(result.state, "current_green")
        self.assertIsNone(stale_readback.call_args.kwargs["review_date_value"])

    def test_same_file_rerun_closeout_code_review_done_is_not_green(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260619_0102_same_file_guard.md"
            review_rel = "docs/code_reviews/260619_0102_same_file_guard.md"
            self._write_same_file_plan(root, plan_rel, review_rel)
            self._write_markdown(
                root,
                review_rel,
                self._same_file_review_fixture(
                    status="✅ Done",
                    target="PLAN=docs/plans/260619_0102_same_file_guard.md",
                ),
            )

            result = MODULE.classify_same_file_rerun_closeout(root / plan_rel, root / review_rel, project_root=root)

        self.assertEqual(result.state, "needs_reviewer_rerun")
        self.assertIn("invalid_review_status_family", result.reason)

    def test_same_file_rerun_closeout_missing_status_blocks(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260505_0106_same_file_guard.md"
            review_rel = "docs/code_reviews/260505_0106_same_file_guard.md"
            self._write_same_file_plan(root, plan_rel, review_rel)
            self._write_markdown(
                root,
                review_rel,
                dedent(
                    f"""\
                    # Code review - missing status

                    **Date:** 2026-05-07 03:00 MSK
                    **Target:** PLAN={plan_rel}

                    ## reviewer_code_risk - GPT-5.5 xhigh
                    - Lane status: `complete`
                    - Target snapshot: `PLAN={plan_rel}`

                    ## reviewer_code_contracts - GPT-5.5 xhigh
                    - Lane status: `complete`
                    - Target snapshot: `PLAN={plan_rel}`
                    """
                ),
            )

            result = MODULE.classify_same_file_rerun_closeout(root / plan_rel, root / review_rel, project_root=root)

        self.assertEqual(result.state, "needs_reviewer_rerun")
        self.assertIn("missing canonical", result.reason)

    def test_same_file_rerun_closeout_historical_reconciliation_requires_green_header(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260505_0103_same_file_guard.md"
            review_rel = "docs/code_reviews/260505_0103_same_file_guard.md"
            self._write_same_file_plan(root, plan_rel, review_rel)
            self._write_markdown(
                root,
                review_rel,
                self._same_file_review_fixture(
                    status="✅ OK",
                    target="PLAN=docs/plans/260505_0103_same_file_guard.md",
                    marker="same review file rewritten in place after same-contract rerun",
                ),
            )
            green_result = MODULE.classify_same_file_rerun_closeout(
                root / plan_rel, root / review_rel, project_root=root
            )

            self._write_markdown(
                root,
                review_rel,
                self._same_file_review_fixture(
                    status="Черновик",
                    target="PLAN=docs/plans/260505_0103_same_file_guard.md",
                    marker="same review file rewritten in place after same-contract rerun",
                ),
            )
            draft_result = MODULE.classify_same_file_rerun_closeout(
                root / plan_rel, root / review_rel, project_root=root
            )

        self.assertEqual(green_result.state, "historical_reconciled")
        self.assertEqual(draft_result.state, "needs_reviewer_rerun")

    def test_same_file_rerun_closeout_active_quarantine_with_rerun_result_allows_historical_reconciliation(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260505_0104_same_file_guard.md"
            review_rel = "docs/code_reviews/260505_0104_same_file_guard.md"
            extra_notes = dedent(
                f"""\
                - Stale note (2026-05-07 03:00): same review file `{review_rel}` remains red until rerun
                - Rerun note (2026-05-07 03:05): same review file `{review_rel}` will be rewritten in place
                - Rerun result (2026-05-07 03:10): same review file `{review_rel}` was rewritten in place
                """
            )
            self._write_same_file_plan(root, plan_rel, review_rel, extra_notes=extra_notes)
            self._write_markdown(
                root,
                review_rel,
                self._same_file_review_fixture(
                    status="✅ OK",
                    target="PLAN=docs/plans/260505_0104_same_file_guard.md",
                    marker="same review file rewritten in place after same-contract rerun",
                ),
            )

            result = MODULE.classify_same_file_rerun_closeout(root / plan_rel, root / review_rel, project_root=root)

        self.assertEqual(result.state, "historical_reconciled")

    def test_same_file_rerun_closeout_contradictory_synthesis_blocks(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_rel = "docs/plans/260505_0105_same_file_guard.md"
            review_rel = "docs/code_reviews/260505_0105_same_file_guard.md"
            self._write_same_file_plan(root, plan_rel, review_rel)
            self._write_markdown(
                root,
                review_rel,
                self._same_file_review_fixture(
                    status="✅ OK",
                    aggregate_status="❌ S1 blocker(ы)",
                    target="PLAN=docs/plans/260505_0105_same_file_guard.md",
                ),
            )

            result = MODULE.classify_same_file_rerun_closeout(root / plan_rel, root / review_rel, project_root=root)

        self.assertEqual(result.state, "current_red")
        self.assertIn("blocker", result.reason.lower())


class HistoricalDiffCheckReadbackTests(unittest.TestCase):
    RANGE = "a" * 40 + ".." + "b" * 40

    def _write(self, root: Path, rel_path: str, body: str | bytes) -> Path:
        if isinstance(body, bytes):
            return write_bytes_fixture(root, rel_path, body)
        return write_text_fixture(root, rel_path, body)

    def _candidate(
        self,
        *,
        path: str,
        line: int,
        blob_oid: str,
        body: bytes,
        finding_kind: str,
        reason_code: str,
    ) -> dict[str, object]:
        return {
            "range": self.RANGE,
            "raw_command": f"git diff --check {self.RANGE}",
            "raw_exit": 2,
            "path": path,
            "line": line,
            "blob_oid": blob_oid,
            "finding_kind": finding_kind,
            "provenance_ref": path,
            "provenance_sha256": hashlib.sha256(body).hexdigest(),
            "lifecycle": "candidate",
            "reason_code": reason_code,
            "owner": "Reviewer",
            "action": "record_candidate",
        }

    def _raw_output(self, rows: list[dict[str, object]]) -> str:
        lines: list[str] = []
        for row in rows:
            if row["finding_kind"] == "trailing_whitespace":
                lines.extend([
                    f"{row['path']}:{row['line']}: trailing whitespace.",
                    "+intentional Markdown hard break  ",
                ])
            else:
                lines.append(f"{row['path']}:{row['line']}: new blank line at EOF.")
        return "\n".join(lines) + "\n"

    def _render_candidate(self, row: dict[str, object]) -> str:
        values = []
        for field in MODULE.HISTORICAL_DIFF_ROW_FIELDS:
            value = row[field]
            values.append(f"  - {field}: `{value}`")
        return "- Candidate:\n" + "\n".join(values)

    def _write_review(
        self,
        root: Path,
        *,
        review_rel: str,
        plan_rel: str,
        rows: list[dict[str, object]],
        include_section: bool = True,
        approval: str | None = None,
    ) -> Path:
        body = (
            "# Код-ревью - historical disposition fixture\n\n"
            "**Date:** 2026-08-30 12:00 MSK\n"
            f"**Target:** RANGE={self.RANGE} (EXCLUDE_DOCS=0)\n"
            f"**Spec:** {plan_rel}\n"
            "**Status:** ❌ S1 blocker(ы)\n\n"
        )
        if include_section:
            digest = MODULE._historical_candidate_digest(rows)
            body += (
                "## Historical diff-check disposition (optional)\n\n"
                f"- Raw command: `git diff --check {self.RANGE}`\n"
                "- Raw exit: `2`\n"
                f"- Candidate count: `{len(rows)}`\n"
                f"- Candidate set SHA-256: `{digest}`\n\n"
                "### Candidate rows\n\n"
                + "\n\n".join(self._render_candidate(row) for row in rows)
                + "\n\n"
            )
        if approval is not None:
            body += "## Архитектурное ревью\n\n" + approval + "\n"
        return self._write(root, review_rel, body)

    def _evaluate_with_git_mock(
        self,
        root: Path,
        *,
        review_rel: str,
        plan_rel: str,
        raw_exit: int,
        raw_output: str,
        blobs: dict[str, tuple[str, bytes]],
        as_status: str,
        support_reason=None,
    ):
        calls: list[tuple[list[str], dict[str, object]]] = []

        def fake_run(argv, **kwargs):
            argv_list = list(argv)
            calls.append((argv_list, kwargs))
            if argv_list[:3] == ["git", "diff", "--check"]:
                return subprocess.CompletedProcess(argv_list, raw_exit, stdout=raw_output, stderr="")
            if argv_list[:2] == ["git", "ls-tree"]:
                path = argv_list[-1]
                oid, _body = blobs[path]
                return subprocess.CompletedProcess(argv_list, 0, stdout=f"100644 blob {oid}\t{path}\n", stderr="")
            if argv_list[:3] == ["git", "cat-file", "blob"]:
                oid = argv_list[-1]
                for expected_oid, body in blobs.values():
                    if expected_oid == oid:
                        return subprocess.CompletedProcess(argv_list, 0, stdout=body, stderr=b"")
                return subprocess.CompletedProcess(argv_list, 1, stdout=b"", stderr=b"")
            raise AssertionError(argv_list)

        patcher = mock.patch.object(MODULE.subprocess, "run", side_effect=fake_run)
        reason_patcher = (
            mock.patch.object(MODULE, "_historical_support_reason_code", return_value=support_reason)
            if support_reason is not None
            else mock.patch.object(MODULE, "_historical_support_reason_code", return_value=("immutable_support_payload_selected_current", ()))
        )
        with patcher, reason_patcher:
            readback = MODULE.evaluate_historical_diff_check_disposition(
                project_root=root,
                review_path=review_rel,
                origin_plan=plan_rel,
                as_status=as_status,
            )
        return readback, calls

    def _accepted_closeout_readback(self) -> object:
        return MODULE.HistoricalDiffCheckReadback(
            state="accepted",
            as_status="Done",
            range_value=self.RANGE,
            raw_command=f"git diff --check {self.RANGE}",
            raw_exit=2,
            finding_count=1,
            candidate_count=1,
            candidate_set_sha256="a" * 64,
            approval_state="accepted",
            issues=(),
        )

    def _materialize_actual_template(
        self,
        template_rel: str,
        *,
        plan_rel: str,
        row: dict[str, object],
    ) -> str:
        """Fill the literal writer skeleton instead of substituting a synthetic H2."""

        text = (SCRIPT_DIR.parent / template_rel).read_text(encoding="utf-8")
        digest = MODULE._historical_candidate_digest([row])
        replacements = (
            ("**Date:** DD.MM.YYYY HH:MM", "**Date:** 2026-08-30 12:00 MSK"),
            (
                "**Target:** RANGE=<base>..<head> (EXCLUDE_DOCS=<0|1>)",
                f"**Target:** RANGE={self.RANGE} (EXCLUDE_DOCS=0)",
            ),
            (
                "**Spec:** docs/plans/<origin_plan>.md | N/A (origin_plan_state=manual_range_review_no_origin_plan)",
                f"**Spec:** {plan_rel}",
            ),
            ("**Status:** Черновик | ✅ OK | ❌ S1 blocker(ы)", "**Status:** ❌ S1 blocker(ы)"),
            ("- Raw command: `git diff --check <base>..<head>`", f"- Raw command: `git diff --check {self.RANGE}`"),
            ("- Raw exit: `<integer>`", "- Raw exit: `2`"),
            ("- Candidate count: `<integer>`", "- Candidate count: `1`"),
            ("- Candidate set SHA-256: `<sha256>`", f"- Candidate set SHA-256: `{digest}`"),
            ("  - range: `<base>..<head>`", f"  - range: `{row['range']}`"),
            ("  - raw_command: `git diff --check <base>..<head>`", f"  - raw_command: `{row['raw_command']}`"),
            ("  - raw_exit: `<integer>`", f"  - raw_exit: `{row['raw_exit']}`"),
            ("  - path: `<repo-relative path>`", f"  - path: `{row['path']}`"),
            ("  - line: `<integer>`", f"  - line: `{row['line']}`"),
            ("  - blob_oid: `<range-head blob oid>`", f"  - blob_oid: `{row['blob_oid']}`"),
            (
                "  - finding_kind: `trailing_whitespace | blank_line_at_eof`",
                f"  - finding_kind: `{row['finding_kind']}`",
            ),
            ("  - provenance_ref: `<exact repo-relative provenance path>`", f"  - provenance_ref: `{row['provenance_ref']}`"),
            ("  - provenance_sha256: `<sha256 of immutable bytes>`", f"  - provenance_sha256: `{row['provenance_sha256']}`"),
            ("  - lifecycle: `candidate`", f"  - lifecycle: `{row['lifecycle']}`"),
            (
                "  - reason_code: `intentional_markdown_hard_break | immutable_support_payload_selected_current | immutable_support_payload_historical_or_superseded`",
                f"  - reason_code: `{row['reason_code']}`",
            ),
            ("  - owner: `Reviewer`", f"  - owner: `{row['owner']}`"),
            ("  - action: `record_candidate`", f"  - action: `{row['action']}`"),
        )
        for literal, replacement in replacements:
            if literal not in text:
                raise AssertionError(f"writer template lost expected literal: {literal!r}")
            text = text.replace(literal, replacement, 1)
        return text

    def test_raw_green_without_optional_section_is_compatible(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/origin.md"
            review_rel = "docs/code_reviews/260830_0240_raw_green.md"
            self._write(root, plan_rel, "# Plan\n")
            review = self._write_review(root, review_rel=review_rel, plan_rel=plan_rel, rows=[], include_section=False)
            review.write_text(
                review.read_text(encoding="utf-8")
                + "\n```markdown\n## Historical diff-check disposition (optional)\n```\n",
                encoding="utf-8",
            )
            readback, calls = self._evaluate_with_git_mock(
                root,
                review_rel=review_rel,
                plan_rel=plan_rel,
                raw_exit=0,
                raw_output="",
                blobs={},
                as_status="Ready for Arch review",
            )

        self.assertEqual(readback.state, "raw_green")
        self.assertEqual(readback.finding_count, 0)
        self.assertEqual(calls[0][0], ["git", "diff", "--check", self.RANGE])
        self.assertTrue(all(kwargs["shell"] is False for _argv, kwargs in calls))

    def test_complete_candidate_handoff_handles_both_evidence_classes_and_template_routes(self) -> None:
        hard_path = "docs/code_drafts/hard_break.md"
        json_path = "docs/code_reviews/assets/support.json"
        hard_bytes = b"line with hard break  \n"
        json_bytes = b'{"current": true}\n\n'
        rows = [
            self._candidate(
                path=hard_path,
                line=1,
                blob_oid="1" * 40,
                body=hard_bytes,
                finding_kind="trailing_whitespace",
                reason_code="intentional_markdown_hard_break",
            ),
            self._candidate(
                path=json_path,
                line=2,
                blob_oid="2" * 40,
                body=json_bytes,
                finding_kind="blank_line_at_eof",
                reason_code="immutable_support_payload_selected_current",
            ),
        ]
        rows.sort(key=MODULE._historical_candidate_sort_key)
        for review_rel in (
            "docs/code_reviews/260830_0240_candidate.md",
            "docs/doc_reviews/260830_0240_candidate.md",
        ):
            with self.subTest(review_rel=review_rel), temporary_git_root() as tmpdir:
                root = Path(tmpdir)
                plan_rel = "docs/plans/origin.md"
                self._write(root, plan_rel, "# Plan\n")
                self._write(root, hard_path, hard_bytes)
                self._write(root, json_path, json_bytes)
                self._write_review(root, review_rel=review_rel, plan_rel=plan_rel, rows=rows)
                readback, _calls = self._evaluate_with_git_mock(
                    root,
                    review_rel=review_rel,
                    plan_rel=plan_rel,
                    raw_exit=2,
                    raw_output=self._raw_output(rows),
                    blobs={hard_path: ("1" * 40, hard_bytes), json_path: ("2" * 40, json_bytes)},
                    as_status="Ready for Arch review",
                )

            self.assertEqual(readback.state, "verified_pending_architect", readback.as_dict())
            self.assertEqual(readback.approval_state, "missing")
            self.assertEqual(set(readback.as_dict()), {
                "state", "as_status", "range", "raw_command", "raw_exit", "finding_count", "candidate_count",
                "candidate_set_sha256", "approval_state", "issues",
            })

    def test_actual_writer_templates_materialize_parser_compatible_optional_section(self) -> None:
        path = "docs/code_reviews/assets/support.json"
        body = b'{"current": true}\n\n'
        row = self._candidate(
            path=path,
            line=7,
            blob_oid="f" * 40,
            body=body,
            finding_kind="blank_line_at_eof",
            reason_code="immutable_support_payload_selected_current",
        )
        for template_rel, review_rel in (
            ("docs/code_reviews/_template_merge_range.md", "docs/code_reviews/260830_0240_template.md"),
            ("docs/doc_reviews/_template_merge_range.md", "docs/doc_reviews/260830_0240_template.md"),
        ):
            with self.subTest(template_rel=template_rel), temporary_git_root() as tmpdir:
                root = Path(tmpdir)
                plan_rel = "docs/plans/origin.md"
                self._write(root, plan_rel, "# Plan\n")
                self._write(root, path, body)
                self._write(
                    root,
                    review_rel,
                    self._materialize_actual_template(template_rel, plan_rel=plan_rel, row=row),
                )
                readback, _calls = self._evaluate_with_git_mock(
                    root,
                    review_rel=review_rel,
                    plan_rel=plan_rel,
                    raw_exit=2,
                    raw_output=self._raw_output([row]),
                    blobs={path: ("f" * 40, body)},
                    as_status="Ready for Arch review",
                )

            self.assertEqual(readback.state, "verified_pending_architect", readback.as_dict())
            self.assertFalse(
                {"invalid_historical_diff_top_level_row", "invalid_historical_diff_candidate_row"}
                & {issue.code for issue in readback.issues}
            )

    def test_accepted_disposition_keeps_unrelated_open_blocker_current_red(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/origin.md"
            review_rel = "docs/code_reviews/260830_0240_open-blocker.md"
            self._write(root, plan_rel, "# Plan\n")
            review = self._write_review(root, review_rel=review_rel, plan_rel=plan_rel, rows=[])
            review.write_text(
                review.read_text(encoding="utf-8")
                + "\n## S1 Blocker\n\n### B1) unrelated live defect\n\n- Current state: open\n",
                encoding="utf-8",
            )
            with mock.patch.object(
                MODULE,
                "evaluate_historical_diff_check_disposition",
                return_value=self._accepted_closeout_readback(),
            ):
                result = MODULE.classify_same_file_rerun_closeout(
                    root / plan_rel,
                    root / review_rel,
                    project_root=root,
                )

        self.assertEqual(result.state, "current_red")
        self.assertIn("blocker-era signal", result.reason)

    def test_accepted_disposition_respects_current_proof_and_header_gates(self) -> None:
        accepted = self._accepted_closeout_readback()
        with self.subTest("blocked current proof"), temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/origin.md"
            review_rel = "docs/code_reviews/260830_0240_blocked-proof.md"
            plan_path = self._write(root, plan_rel, "# Plan\n")
            review_path = self._write_review(root, review_rel=review_rel, plan_rel=plan_rel, rows=[])
            blocked_proof = plan_lint.CurrentReviewProofPreflight(
                state="blocked",
                reason_code="current_review_proof_fixture_blocked",
                message="fixture current proof is blocked",
                plan_path=str(plan_path),
                review_path=str(review_path),
                target="BUNDLE=current bundle_sha256=" + "a" * 64,
            )
            with mock.patch.object(
                MODULE,
                "evaluate_historical_diff_check_disposition",
                return_value=accepted,
            ), mock.patch.object(
                MODULE.plan_lint,
                "preflight_current_review_proof",
                return_value=blocked_proof,
            ):
                result = MODULE.classify_same_file_rerun_closeout(
                    plan_path,
                    review_path,
                    project_root=root,
                )

            self.assertEqual(result.state, "needs_reviewer_rerun")
            self.assertIn("current_review_proof_fixture_blocked", result.reason)

        with self.subTest("malformed current header"), temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/origin.md"
            review_rel = "docs/code_reviews/260830_0240_bad-header.md"
            self._write(root, plan_rel, "# Plan\n")
            review = self._write_review(root, review_rel=review_rel, plan_rel=plan_rel, rows=[])
            review.write_text(
                review.read_text(encoding="utf-8").replace(
                    "**Status:** ❌ S1 blocker(ы)",
                    "**Status:** historical_reconciled",
                    1,
                ),
                encoding="utf-8",
            )
            with mock.patch.object(
                MODULE,
                "evaluate_historical_diff_check_disposition",
                return_value=accepted,
            ):
                result = MODULE.classify_same_file_rerun_closeout(
                    root / plan_rel,
                    root / review_rel,
                    project_root=root,
                )

            self.assertEqual(result.state, "needs_reviewer_rerun")
            self.assertIn("invalid_review_status_family", result.reason)

    def test_complete_eleven_row_vector_and_continuation_lines_stay_exact(self) -> None:
        rows: list[dict[str, object]] = []
        blobs: dict[str, tuple[str, bytes]] = {}
        for index in range(11):
            if index < 2:
                path = f"docs/code_drafts/hard-break-{index:02d}.md"
                body = f"intentional hard break {index}  \n".encode("utf-8")
                finding_kind = "trailing_whitespace"
                reason_code = "intentional_markdown_hard_break"
            else:
                path = f"docs/code_reviews/assets/row-{index:02d}.json"
                body = f'{{"row": {index}}}\n\n'.encode("utf-8")
                finding_kind = "blank_line_at_eof"
                reason_code = "immutable_support_payload_selected_current"
            self_row = self._candidate(
                path=path,
                line=index + 1,
                blob_oid=f"{index + 1:040x}",
                body=body,
                finding_kind=finding_kind,
                reason_code=reason_code,
            )
            rows.append(self_row)
            blobs[path] = (str(self_row["blob_oid"]), body)
        rows.sort(key=MODULE._historical_candidate_sort_key)
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/origin.md"
            review_rel = "docs/code_reviews/260830_0240_eleven.md"
            self._write(root, plan_rel, "# Plan\n")
            for path, (_oid, body) in blobs.items():
                self._write(root, path, body)
            self._write_review(root, review_rel=review_rel, plan_rel=plan_rel, rows=rows)
            readback, _calls = self._evaluate_with_git_mock(
                root,
                review_rel=review_rel,
                plan_rel=plan_rel,
                raw_exit=2,
                raw_output=self._raw_output(rows),
                blobs=blobs,
                as_status="Ready for Arch review",
            )

        self.assertEqual(readback.state, "verified_pending_architect", readback.as_dict())
        self.assertEqual(readback.finding_count, 11)
        self.assertEqual(readback.candidate_count, 11)

    def test_strict_candidate_matrix_rejects_duplicate_conflicting_count_digest_range_command_exit_and_foreign_rows(self) -> None:
        path = "docs/code_reviews/assets/support.json"
        body = b'{"fixture": true}\n\n'
        row = self._candidate(
            path=path,
            line=7,
            blob_oid="3" * 40,
            body=body,
            finding_kind="blank_line_at_eof",
            reason_code="immutable_support_payload_selected_current",
        )
        wrong_range = "c" * 40 + ".." + "d" * 40
        digest = MODULE._historical_candidate_digest([row])
        conflicting_row = {
            **row,
            "reason_code": "immutable_support_payload_historical_or_superseded",
        }
        conflicting_digest = MODULE._historical_candidate_digest([row, conflicting_row])
        scenarios = {
            "wrong_range": lambda text: text.replace(f"  - range: `{self.RANGE}`", f"  - range: `{wrong_range}`", 1),
            "wrong_command": lambda text: text.replace("git diff --check", "git diff --stat", 1),
            "wrong_exit": lambda text: text.replace("  - raw_exit: `2`", "  - raw_exit: `0`", 1),
            "duplicate": lambda text: text.replace("  - owner: `Reviewer`", "  - owner: `Reviewer`\n  - owner: `Reviewer`", 1),
            "conflicting": lambda text: (
                text.replace("- Candidate count: `1`", "- Candidate count: `2`", 1)
                .replace(
                    f"- Candidate set SHA-256: `{digest}`",
                    f"- Candidate set SHA-256: `{conflicting_digest}`",
                    1,
                )
                + "\n"
                + self._render_candidate(conflicting_row)
                + "\n"
            ),
            "count": lambda text: text.replace("- Candidate count: `1`", "- Candidate count: `2`", 1),
            "digest": lambda text: text.replace(f"- Candidate set SHA-256: `{digest}`", "- Candidate set SHA-256: `" + "0" * 64 + "`", 1),
            "blob": lambda text: text.replace("  - blob_oid: `" + "3" * 40 + "`", "  - blob_oid: `" + "0" * 40 + "`", 1),
            "sha": lambda text: text.replace("  - provenance_sha256: `" + hashlib.sha256(body).hexdigest() + "`", "  - provenance_sha256: `" + "0" * 64 + "`", 1),
            "foreign": lambda text: text.replace("  - path: `docs/code_reviews/assets/support.json`", "  - path: `docs/code_reviews/assets/foreign.json`", 1),
        }
        for name, mutate in scenarios.items():
            with self.subTest(name=name), temporary_git_root() as tmpdir:
                root = Path(tmpdir)
                plan_rel = "docs/plans/origin.md"
                review_rel = "docs/code_reviews/260830_0240_strict.md"
                self._write(root, plan_rel, "# Plan\n")
                self._write(root, path, body)
                review = self._write_review(root, review_rel=review_rel, plan_rel=plan_rel, rows=[row])
                review.write_text(mutate(review.read_text(encoding="utf-8")), encoding="utf-8")
                readback, _calls = self._evaluate_with_git_mock(
                    root,
                    review_rel=review_rel,
                    plan_rel=plan_rel,
                    raw_exit=2,
                    raw_output=self._raw_output([row]),
                    blobs={path: ("3" * 40, body)},
                    as_status="Ready for Arch review",
                )
            self.assertEqual(readback.state, "blocked")
            self.assertTrue(readback.issues)
            if name == "conflicting":
                self.assertIn("duplicate_historical_diff_candidate", {issue.code for issue in readback.issues})

    def test_support_selection_uses_target_ref_plan_not_body_current_flag(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            source_plan_rel = "docs/plans/source.md"
            old_rel = "docs/code_reviews/assets/old.json"
            selected_rel = "docs/code_reviews/assets/selected.json"
            old_payload = {
                "run_id": "reviewer_code_risk:old:20260830T120000Z",
                "lane_id": "reviewer_code_risk",
                "target_ref": f"BUNDLE=current;PLAN={source_plan_rel}",
                "target_snapshot": "BUNDLE=fixture",
                "lane_status": "complete",
                "findings": [],
                "current": True,
            }
            selected_payload = {
                **old_payload,
                "run_id": "reviewer_code_risk:selected:20260830T120100Z",
                "current": True,
            }
            old_bytes = json.dumps(old_payload, sort_keys=True).encode("utf-8")
            selected_bytes = json.dumps(selected_payload, sort_keys=True).encode("utf-8")
            self._write(root, old_rel, old_bytes)
            self._write(root, selected_rel, selected_bytes)
            compact_old = {
                **old_payload,
                "current": False,
                "full_payload_ref": old_rel,
                "full_payload_sha256": hashlib.sha256(old_bytes).hexdigest(),
            }
            compact_selected = {
                **selected_payload,
                "full_payload_ref": selected_rel,
                "full_payload_sha256": hashlib.sha256(selected_bytes).hexdigest(),
            }
            self._write(
                root,
                source_plan_rel,
                "# Plan\n\n## Evidence\n"
                "```json\n" + json.dumps(compact_old) + "\n```\n"
                "```json\n" + json.dumps(compact_selected) + "\n```\n",
            )
            old_reason, old_issues = MODULE._historical_support_reason_code(
                project_root=root,
                support_ref=old_rel,
                support_sha256=hashlib.sha256(old_bytes).hexdigest(),
                support_bytes=old_bytes,
            )
            selected_reason, selected_issues = MODULE._historical_support_reason_code(
                project_root=root,
                support_ref=selected_rel,
                support_sha256=hashlib.sha256(selected_bytes).hexdigest(),
                support_bytes=selected_bytes,
            )

        self.assertEqual(old_issues, ())
        self.assertEqual(old_reason, "immutable_support_payload_historical_or_superseded")
        self.assertEqual(selected_issues, ())
        self.assertEqual(selected_reason, "immutable_support_payload_selected_current")

    def test_stale_worktree_bytes_fail_even_when_candidate_keeps_range_head_blob(self) -> None:
        path = "docs/code_reviews/assets/support.json"
        head_bytes = b'{"fixture": true}\n\n'
        row = self._candidate(
            path=path,
            line=7,
            blob_oid="5" * 40,
            body=head_bytes,
            finding_kind="blank_line_at_eof",
            reason_code="immutable_support_payload_selected_current",
        )
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/origin.md"
            review_rel = "docs/code_reviews/260830_0240_stale.md"
            self._write(root, plan_rel, "# Plan\n")
            self._write(root, path, b'{"fixture": "mutated"}\n')
            self._write_review(root, review_rel=review_rel, plan_rel=plan_rel, rows=[row])
            readback, _calls = self._evaluate_with_git_mock(
                root,
                review_rel=review_rel,
                plan_rel=plan_rel,
                raw_exit=2,
                raw_output=self._raw_output([row]),
                blobs={path: ("5" * 40, head_bytes)},
                as_status="Ready for Arch review",
            )

        self.assertEqual(readback.state, "blocked")
        self.assertIn("historical_diff_current_bytes_stale", {issue.code for issue in readback.issues})

    def test_done_requires_exact_approval_and_same_file_closeout_consumes_only_accepted_readback(self) -> None:
        path = "docs/code_reviews/assets/support.json"
        body = b'{"fixture": true}\n\n'
        row = self._candidate(
            path=path,
            line=7,
            blob_oid="4" * 40,
            body=body,
            finding_kind="blank_line_at_eof",
            reason_code="immutable_support_payload_selected_current",
        )
        digest = MODULE._historical_candidate_digest([row])
        approval = f"Historical disposition approval: state=accepted range={self.RANGE} raw_exit=2 candidate_set_sha256={digest}"
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            plan_rel = "docs/plans/origin.md"
            review_rel = "docs/code_reviews/260830_0240_accepted.md"
            self._write(root, plan_rel, "# Plan\n")
            self._write(root, path, body)
            self._write_review(root, review_rel=review_rel, plan_rel=plan_rel, rows=[row])
            missing, _calls = self._evaluate_with_git_mock(
                root,
                review_rel=review_rel,
                plan_rel=plan_rel,
                raw_exit=2,
                raw_output=self._raw_output([row]),
                blobs={path: ("4" * 40, body)},
                as_status="Done",
            )
            self._write_review(
                root,
                review_rel=review_rel,
                plan_rel=plan_rel,
                rows=[row],
                approval=approval.replace(digest, "0" * 64),
            )
            drifted, _calls = self._evaluate_with_git_mock(
                root,
                review_rel=review_rel,
                plan_rel=plan_rel,
                raw_exit=2,
                raw_output=self._raw_output([row]),
                blobs={path: ("4" * 40, body)},
                as_status="Done",
            )
            self._write_review(root, review_rel=review_rel, plan_rel=plan_rel, rows=[row], approval=approval)
            accepted, _calls = self._evaluate_with_git_mock(
                root,
                review_rel=review_rel,
                plan_rel=plan_rel,
                raw_exit=2,
                raw_output=self._raw_output([row]),
                blobs={path: ("4" * 40, body)},
                as_status="Done",
            )
            with mock.patch.object(MODULE, "evaluate_historical_diff_check_disposition", return_value=accepted):
                closeout = MODULE.classify_same_file_rerun_closeout(
                    root / plan_rel,
                    root / review_rel,
                    project_root=root,
                )

        self.assertEqual(missing.state, "blocked")
        self.assertEqual(missing.approval_state, "missing")
        self.assertEqual(drifted.state, "blocked")
        self.assertEqual(drifted.approval_state, "drifted")
        self.assertEqual(accepted.state, "accepted", accepted.as_dict())
        self.assertEqual(accepted.approval_state, "accepted")
        self.assertEqual(closeout.state, "historical_reconciled")

    def test_cli_requires_one_path_status_json_and_rejects_selector_mix(self) -> None:
        with mock.patch("sys.stderr", io.StringIO()):
            with self.assertRaises(SystemExit):
                MODULE.parse_args(["--historical-diff-check-readback", "--origin-plan", "docs/plans/a.md", "review.md"])
            with self.assertRaises(SystemExit):
                MODULE.parse_args([
                    "--historical-diff-check-readback", "--json", "--as-status", "Done", "--origin-plan", "docs/plans/a.md",
                    "--select-risk-lane", "review.md",
                ])

        readback = MODULE.HistoricalDiffCheckReadback(
            state="verified_pending_architect",
            as_status="Ready for Arch review",
            range_value=self.RANGE,
            raw_command=f"git diff --check {self.RANGE}",
            raw_exit=2,
            finding_count=11,
            candidate_count=11,
            candidate_set_sha256="a" * 64,
            approval_state="missing",
            issues=(),
        )
        stdout = io.StringIO()
        with mock.patch.object(MODULE, "evaluate_historical_diff_check_disposition", return_value=readback), mock.patch(
            "sys.stdout", stdout
        ):
            exit_code = MODULE.main([
                "--historical-diff-check-readback", "--json", "--as-status", "Ready for Arch review",
                "--origin-plan", "docs/plans/a.md", "review.md",
            ])
        self.assertEqual(exit_code, 0)
        self.assertEqual(set(json.loads(stdout.getvalue())), {
            "state", "as_status", "range", "raw_command", "raw_exit", "finding_count", "candidate_count",
            "candidate_set_sha256", "approval_state", "issues",
        })


class RuntimeUiVisualEvidenceReadbackTests(unittest.TestCase):
    def _contract(self, review_stem: str) -> dict[str, object]:
        return {
            "schema_version": "review_visual_lane_contract.v1",
            "availability_state": "available",
            "runtime_ui_kind": "web",
            "profile_id": "default",
            "source_refs": ["docs/smoke_visual.md", "docs/testing_runbook.md"],
            "changed_path_evidence": [],
            "mandatory_modes": ["primary", "secondary"],
            "comparator_command": "./scripts/run_visual_check.sh --repeat 2",
            "comparator_claim": "mechanical",
            "baseline_update_allowed": False,
            "human_commands_by_mode": {
                "primary": "./scripts/review_visual_design_audit.sh --mode primary",
                "secondary": "./scripts/review_visual_design_audit.sh --mode secondary",
            },
            "human_index_paths_by_mode": {
                "primary": ".tmp/human/primary/human_visual_review_primary.md",
                "secondary": ".tmp/human/secondary/human_visual_review_secondary.md",
            },
            "human_output_roots_by_mode": {"primary": ".tmp/human/primary", "secondary": ".tmp/human/secondary"},
            "complete_index_required": True,
            "durable_review_asset_root": f"docs/code_reviews/assets/{review_stem}/",
            "reason": "repo_backed_visual_lane",
        }

    def _fixture(self, root: Path, *, visual_lines: list[str] | None = None) -> tuple[Path, Path, dict[str, object]]:
        review_stem = "260722_2206_reviewer_range_aaaaaaa_bbbbbbb"
        plan_rel = "docs/plans/260722_2206_reviewer_range_aaaaaaa_bbbbbbb.md"
        review_rel = f"docs/code_reviews/{review_stem}.md"
        payload = self._contract(review_stem)
        plan = write_text_fixture(
            root,
            plan_rel,
            "# Plan\n\n## Review visual lane contract\n\n"
            + MODULE.review_visual_lane_contract.render_materialized_contract(payload)
            + "\n",
        )
        default_lines = [
            "- Comparator command: `./scripts/run_visual_check.sh --repeat 2`",
            "- Comparator claim: `mechanical`",
            "- Comparator result: `pass`",
            "- Capture status: `complete`",
            "- Complete index inspected: `yes`",
            "- Design verdict: `no_findings`",
            "- Mandatory modes: `primary, secondary`",
            "- Human index (primary): `.tmp/human/primary/human_visual_review_primary.md`",
            "- Human index (secondary): `.tmp/human/secondary/human_visual_review_secondary.md`",
            f"- Durable asset (primary): `docs/code_reviews/assets/{review_stem}/primary.png`",
            f"- Durable asset (secondary): `docs/code_reviews/assets/{review_stem}/secondary.png`",
        ]
        review = write_text_fixture(
            root,
            review_rel,
            "# Код-ревью\n\n"
            f"**Spec:** {plan_rel}\n"
            "**Status:** ✅ OK\n\n"
            "## Визуальные доказательства\n"
            + "\n".join(default_lines if visual_lines is None else visual_lines)
            + "\n",
        )
        return plan, review, payload

    def _assets(self, root: Path, review: Path, *, empty_mode: str | None = None) -> None:
        asset_root = root / "docs" / "code_reviews" / "assets" / review.stem
        for mode in ("primary", "secondary"):
            write_bytes_fixture(asset_root, f"{mode}.png", b"" if mode == empty_mode else b"png")

    def _evaluate(self, root: Path, review: Path):
        return MODULE.evaluate_runtime_ui_visual_evidence(project_root=root, review_path=review)

    def test_green_requires_independent_claims_and_current_assets(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            _plan, review, _payload = self._fixture(root)
            self._assets(root, review)
            readback = self._evaluate(root, review)
        self.assertEqual(readback.state, "green")
        self.assertEqual(readback.mandatory_modes, ("primary", "secondary"))
        self.assertEqual(len(readback.current_asset_refs), 2)

    def test_na_missing_empty_and_one_claim_paths_are_red(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            _plan, review, _payload = self._fixture(root, visual_lines=["- Durable screenshots: N/A"])
            self.assertEqual(self._evaluate(root, review).state, "red")

        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            _plan, review, _payload = self._fixture(root)
            self._assets(root, review, empty_mode="secondary")
            readback = self._evaluate(root, review)
            self.assertEqual(readback.state, "red")
            self.assertIn("empty_durable_asset_file:secondary", readback.reason_codes)

        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            _plan, review, _payload = self._fixture(root)
            self._assets(root, review)
            text = review.read_text(encoding="utf-8").replace("- Comparator result: `pass`\n", "")
            review.write_text(text, encoding="utf-8")
            self.assertIn("comparator_not_pass", self._evaluate(root, review).reason_codes)
            review.write_text(
                text.replace("- Comparator result: `pass`\n", "").replace(
                    "- Complete index inspected: `yes`", "- Complete index inspected: `no`"
                ),
                encoding="utf-8",
            )
            self.assertIn("complete_index_not_inspected", self._evaluate(root, review).reason_codes)

    def test_tmp_other_review_traversal_and_symlink_are_ambiguous(self) -> None:
        review_stem = "260722_2206_reviewer_range_aaaaaaa_bbbbbbb"
        replacements = (
            (f"docs/code_reviews/assets/{review_stem}/primary.png", ".tmp/human/primary.png"),
            (f"docs/code_reviews/assets/{review_stem}/primary.png", "docs/code_reviews/assets/other_review/primary.png"),
            (f"docs/code_reviews/assets/{review_stem}/primary.png", f"docs/code_reviews/assets/{review_stem}/../escape.png"),
        )
        for old, new in replacements:
            with self.subTest(path=new), temporary_git_root() as tmpdir:
                root = Path(tmpdir)
                _plan, review, _payload = self._fixture(root)
                self._assets(root, review)
                review.write_text(review.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
                self.assertEqual(self._evaluate(root, review).state, "ambiguous")

        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            _plan, review, _payload = self._fixture(root)
            self._assets(root, review)
            asset = root / "docs" / "code_reviews" / "assets" / review.stem / "primary.png"
            asset.unlink()
            asset.symlink_to(asset.with_name("secondary.png"))
            readback = self._evaluate(root, review)
            self.assertEqual(readback.state, "ambiguous")
            self.assertIn("symlink_durable_asset:primary", readback.reason_codes)

    def test_findings_require_terminal_disposition(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            _plan, review, _payload = self._fixture(root)
            self._assets(root, review)
            review.write_text(
                review.read_text(encoding="utf-8").replace("Design verdict: `no_findings`", "Design verdict: `findings`"),
                encoding="utf-8",
            )
            self.assertIn("nonterminal_visual_findings", self._evaluate(root, review).reason_codes)
            review.write_text(
                review.read_text(encoding="utf-8") + "- Finding dispositions: `status=deferred reference=docs/plans/followup.md`\n",
                encoding="utf-8",
            )
            self.assertEqual(self._evaluate(root, review).state, "green")

    def test_explicit_missing_origin_and_duplicate_truth_fields_are_ambiguous(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            review = write_text_fixture(
                root,
                "docs/code_reviews/missing_origin.md",
                "# Код-ревью\n\n**Spec:** docs/plans/missing.md\n**Status:** ✅ OK\n",
            )
            readback = self._evaluate(root, review)
            self.assertEqual(readback.state, "ambiguous")
            self.assertIn("missing_origin_plan", readback.reason_codes)

        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            _plan, review, _payload = self._fixture(root)
            self._assets(root, review)
            review.write_text(
                review.read_text(encoding="utf-8") + "- Comparator result: `fail`\n",
                encoding="utf-8",
            )
            readback = self._evaluate(root, review)
            self.assertEqual(readback.state, "ambiguous")
            self.assertIn("duplicate_visual_field:comparator result", readback.reason_codes)

    def test_plain_contract_mention_without_heading_preserves_legacy_not_applicable(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            plan = write_text_fixture(
                root,
                "docs/plans/legacy.md",
                "# Plan\n\nMention `## Review visual lane contract` as future work only.\n",
            )
            review = write_text_fixture(
                root,
                "docs/code_reviews/legacy.md",
                f"# Код-ревью\n\n**Spec:** {plan.relative_to(root)}\n**Status:** ✅ OK\n",
            )
            readback = self._evaluate(root, review)
        self.assertEqual(readback.state, "not_applicable")

    def test_malformed_changed_path_evidence_is_ambiguous_not_a_traceback(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            plan, review, payload = self._fixture(root)
            payload["changed_path_evidence"] = [None]
            plan.write_text(
                "# Plan\n\n## Review visual lane contract\n\n"
                + MODULE.review_visual_lane_contract.render_materialized_contract(payload)
                + "\n",
                encoding="utf-8",
            )

            readback = self._evaluate(root, review)

        self.assertEqual(readback.state, "ambiguous")
        self.assertEqual(readback.reason_codes, ("changed_path_evidence_malformed",))

    def test_external_ref_rejects_coherent_wrong_review_target(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            review_stem = "260830_0241_wrong_range_readback_fixture"
            plan_ref = f"docs/plans/{review_stem}.md"
            draft_ref = f"docs/code_drafts/{review_stem}__code_draft.md"
            review_ref = f"docs/code_reviews/{review_stem}.md"
            payload = self._contract(review_stem)
            payload["changed_path_evidence"] = [
                {
                    "status": "M",
                    "path": f"templates/generated_{index:04d}.html",
                    "old_path": "",
                    "runtime_ui": True,
                    "runtime_ui_paths": [f"templates/generated_{index:04d}.html"],
                }
                for index in range(940)
            ]
            materialization = MODULE.review_visual_lane_contract.prepare_materialized_contract(
                payload,
                base="c" * 40,
                head="d" * 40,
                exclude_docs=1,
                plan_ref=plan_ref,
                review_artifact_ref=review_ref,
            )
            plan_text = (
                "# Plan\n\n"
                f"- Review target: `RANGE={'a' * 40}..{'b' * 40} (EXCLUDE_DOCS=0)`\n\n"
                "## Review visual lane contract\n\n"
                + str(materialization["markdown"])
                + "\n"
            )
            draft_text = "# Draft\n\n## Review visual lane contract\n\n" + str(materialization["markdown"]) + "\n"
            MODULE.review_visual_lane_contract.publish_generated_scaffold(
                project_root=root,
                plan_ref=plan_ref,
                plan_text=plan_text,
                draft_ref=draft_ref,
                draft_text=draft_text,
                materialization=materialization,
            )
            review = write_text_fixture(
                root,
                review_ref,
                "# Код-ревью\n\n"
                f"**Spec:** {plan_ref}\n"
                "**Status:** ✅ OK\n",
            )

            readback = self._evaluate(root, review)

        self.assertEqual(readback.state, "ambiguous")
        self.assertEqual(readback.reason_codes, ("identity_mismatch",))

    def test_external_ref_rejects_missing_or_noncanonical_review_target(self) -> None:
        cases = {
            "missing": "",
            "short": f"- Review target: `RANGE={'a' * 7}..{'b' * 7} (EXCLUDE_DOCS=0)`\n\n",
            "uppercase": f"- Review target: `RANGE={'A' * 40}..{'B' * 40} (EXCLUDE_DOCS=0)`\n\n",
            "duplicate": (
                f"- Review target: `RANGE={'a' * 40}..{'b' * 40} (EXCLUDE_DOCS=0)`\n"
                f"- Review target: `RANGE={'a' * 40}..{'b' * 40} (EXCLUDE_DOCS=0)`\n\n"
            ),
            "mixed": (
                f"- Review target: `RANGE={'a' * 40}..{'b' * 40} (EXCLUDE_DOCS=0)`\n"
                f"- Review target: `RANGE={'a' * 7}..{'b' * 7} (EXCLUDE_DOCS=0)`\n\n"
            ),
        }
        for name, target_lines in cases.items():
            with self.subTest(target=name), temporary_git_root() as tmpdir:
                root = Path(tmpdir)
                review_stem = f"260830_0241_{name}_target_readback_fixture"
                plan_ref = f"docs/plans/{review_stem}.md"
                draft_ref = f"docs/code_drafts/{review_stem}__code_draft.md"
                review_ref = f"docs/code_reviews/{review_stem}.md"
                payload = self._contract(review_stem)
                payload["changed_path_evidence"] = [
                    {
                        "status": "M",
                        "path": f"templates/generated_{index:04d}.html",
                        "old_path": "",
                        "runtime_ui": True,
                        "runtime_ui_paths": [f"templates/generated_{index:04d}.html"],
                    }
                    for index in range(940)
                ]
                materialization = MODULE.review_visual_lane_contract.prepare_materialized_contract(
                    payload,
                    base="a" * 40,
                    head="b" * 40,
                    exclude_docs=0,
                    plan_ref=plan_ref,
                    review_artifact_ref=review_ref,
                )
                plan_text = (
                    "# Plan\n\n"
                    + target_lines
                    + "## Review visual lane contract\n\n"
                    + str(materialization["markdown"])
                    + "\n"
                )
                draft_text = "# Draft\n\n## Review visual lane contract\n\n" + str(materialization["markdown"]) + "\n"
                MODULE.review_visual_lane_contract.publish_generated_scaffold(
                    project_root=root,
                    plan_ref=plan_ref,
                    plan_text=plan_text,
                    draft_ref=draft_ref,
                    draft_text=draft_text,
                    materialization=materialization,
                )
                review = write_text_fixture(
                    root,
                    review_ref,
                    "# Код-ревью\n\n"
                    f"**Spec:** {plan_ref}\n"
                    "**Status:** ✅ OK\n",
                )

                readback = self._evaluate(root, review)

                self.assertEqual(readback.state, "ambiguous")
                self.assertEqual(readback.reason_codes, ("review_target_identity_invalid",))

    def test_external_v2_ref_uses_the_same_visual_readback(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            review_stem = "260830_0241_external_visual_fixture"
            plan_ref = f"docs/plans/{review_stem}.md"
            draft_ref = f"docs/code_drafts/{review_stem}__code_draft.md"
            review_ref = f"docs/code_reviews/{review_stem}.md"
            payload = self._contract(review_stem)
            payload["changed_path_evidence"] = [
                {
                    "status": "M",
                    "path": f"templates/generated_{index:04d}.html",
                    "old_path": "",
                    "runtime_ui": True,
                    "runtime_ui_paths": [f"templates/generated_{index:04d}.html"],
                }
                for index in range(940)
            ]
            materialization = MODULE.review_visual_lane_contract.prepare_materialized_contract(
                payload,
                base="a" * 40,
                head="b" * 40,
                exclude_docs=0,
                plan_ref=plan_ref,
                review_artifact_ref=review_ref,
            )
            self.assertEqual(materialization["mode"], "external")
            plan_text = (
                "# Plan\n\n"
                f"- Review target: `RANGE={'a' * 40}..{'b' * 40} (EXCLUDE_DOCS=0)`\n\n"
                "## Review visual lane contract\n\n"
                + str(materialization["markdown"])
                + "\n"
            )
            draft_text = "# Draft\n\n## Review visual lane contract\n\n" + str(materialization["markdown"]) + "\n"
            MODULE.review_visual_lane_contract.publish_generated_scaffold(
                project_root=root,
                plan_ref=plan_ref,
                plan_text=plan_text,
                draft_ref=draft_ref,
                draft_text=draft_text,
                materialization=materialization,
            )
            review = write_text_fixture(
                root,
                review_ref,
                "# Код-ревью\n\n"
                f"**Spec:** {plan_ref}\n"
                "**Status:** ✅ OK\n\n"
                "## Визуальные доказательства\n"
                "- Comparator command: `./scripts/run_visual_check.sh --repeat 2`\n"
                "- Comparator claim: `mechanical`\n"
                "- Comparator result: `pass`\n"
                "- Capture status: `complete`\n"
                "- Complete index inspected: `yes`\n"
                "- Design verdict: `no_findings`\n"
                "- Mandatory modes: `primary, secondary`\n"
                "- Human index (primary): `.tmp/human/primary/human_visual_review_primary.md`\n"
                "- Human index (secondary): `.tmp/human/secondary/human_visual_review_secondary.md`\n"
                f"- Durable asset (primary): `docs/code_reviews/assets/{review_stem}/primary.png`\n"
                f"- Durable asset (secondary): `docs/code_reviews/assets/{review_stem}/secondary.png`\n",
            )
            self._assets(root, review)
            readback = self._evaluate(root, review)
        self.assertEqual(readback.state, "green", readback.reason_codes)


if __name__ == "__main__":
    unittest.main()

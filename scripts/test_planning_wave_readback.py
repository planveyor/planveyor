from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).with_name("planning_wave_readback.py")
SPEC = importlib.util.spec_from_file_location("planning_wave_readback", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

from test_support.process_contract_fixtures import standalone_git_root, temporary_git_root


def _plan(
    *,
    title: str,
    status: str,
    plan_meta: dict[str, object],
    body: str = "",
) -> str:
    # Keep the shared 8-space template indent on every substituted line so that
    # textwrap.dedent below really emits canonical column-0 ``## Meta`` headings
    # (the strict routing reader only accepts 0-3 leading spaces).
    meta = textwrap.indent(
        json.dumps({"plan_meta": plan_meta}, ensure_ascii=False, indent=2),
        "        ",
    )
    indented_body = textwrap.indent(body, "        ") if body else ""
    return textwrap.dedent(
        f"""\
        # Plan: {title}

        **Date:** 2026-06-19 00:00 MSK
        **Stage:** Stage 2
        **Priority:** P1
        **Plan type:** dev
        **Status:** {status}
        **Schema version:** plan.v1

        ## Meta (machine-readable JSON; required for new plans)
        ```json
        {meta}
        ```

        {indented_body}
        """
    )


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _build(root: Path) -> dict[str, object]:
    return MODULE.build_readback(
        root=root,
        json_out=root / ".tmp/planning_wave_readback.json",
        generated_at="2026-06-19T07:45:00Z",
    )


class PlanningWaveReadbackTests(unittest.TestCase):
    def test_green_fixture_reports_waves_preview_provenance_and_accepted_routes(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            analysis_rel = "docs/plans/260619_1000_analysis.md"
            analysis_pack_rel = "docs/analysis_packs/260619_1000_analysis.md"
            analysis_draft_rel = "docs/code_drafts/260619_1000_analysis__code_draft.md"
            _write(
                root,
                analysis_rel,
                _plan(
                    title="analysis",
                    status="Ready for Review",
                    plan_meta={
                        "wave_family": "analysis_wave",
                        "phase_overlay": None,
                        "phase_state": None,
                        "parent": None,
                        "depends_on": [],
                        "promoted_from": {
                            "source_plan": analysis_rel,
                            "source_route_ref": f"{analysis_pack_rel}#Analysis-pack",
                            "accepted_route": "developer_wave",
                            "promoted_artifact_ref": "docs/plans/260619_1005_dev.md",
                            "queue_admission_at_acceptance": "queueable_now",
                            "runner_admission_at_acceptance": "frontier_only",
                        },
                    },
                    body=(
                        "## Analysis pack\n"
                        "| Field | Value |\n"
                        "| --- | --- |\n"
                        f"| `analysis_pack_ref` | `{analysis_pack_rel}#Analysis-pack` |\n"
                        "| `authority_boundary` | `standalone_pack_only` |\n"
                    ),
                ),
            )
            _write(
                root,
                analysis_pack_rel,
                "# Analysis pack\n\n## Analysis pack\n"
                "| Field | Value |\n"
                "| --- | --- |\n"
                "| `route_recommendation` | `developer_wave` |\n",
            )
            _write(
                root,
                analysis_draft_rel,
                "# Draft\n\n```json\n"
                + json.dumps(
                    {
                        "code_draft_meta": {
                            "plan": analysis_rel,
                            "cluster": "process",
                            "targets": [{"path": analysis_pack_rel, "kind": "doc"}],
                            "deleted_paths": [],
                        }
                    },
                    indent=2,
                )
                + "\n```\n",
            )
            _write(
                root,
                "docs/plans/260619_1001_child_a.md",
                _plan(title="child a", status="Ready for Coder", plan_meta={}),
            )
            _write(
                root,
                "docs/plans/260619_1002_child_b.md",
                _plan(title="child b", status="Done", plan_meta={}),
            )
            _write(
                root,
                "docs/plans/260619_1003_decomp.md",
                _plan(
                    title="decomp",
                    status="Ready for Review",
                    plan_meta={
                        "wave_family": None,
                        "phase_overlay": "decomposition_wave",
                        "phase_state": "active",
                        "parent": None,
                        "depends_on": ["docs/plans/260619_1000_analysis.md"],
                    },
                    body=textwrap.dedent(
                        """\
                        ## Child plan map
                        - `docs/plans/260619_1001_child_a.md` - Dependency type: sequential; proof lane: unit
                        - `docs/plans/260619_1002_child_b.md` - Dependency type: parallel; proof lane: docs

                        ## Execution queue
                        1. `docs/plans/260619_1001_child_a.md`
                        2. `docs/plans/260619_1002_child_b.md`

                        ## Follow-ups (deferred)
                        N/A (why=none)
                        """
                    ),
                ),
            )
            _write(
                root,
                "docs/plans/260619_1004_parked.md",
                _plan(
                    title="parked",
                    status="Done",
                    plan_meta={"phase_overlay": "decomposition_wave", "phase_state": "parked"},
                ),
            )
            _write(
                root,
                "docs/plans/260619_1005_dev.md",
                _plan(
                    title="dev",
                    status="Architect draft",
                    plan_meta={},
                ),
            )

            payload = _build(root)

        self.assertEqual(payload["schema_version"], "planning_wave_readback.v1")
        self.assertEqual(len(payload["buckets"]["open_analysis_waves"]), 1)
        self.assertEqual(len(payload["buckets"]["open_decomposition_waves"]), 1)
        self.assertEqual(len(payload["buckets"]["parked_decomposition_umbrellas"]), 1)
        self.assertEqual(payload["buckets"]["pending_child_umbrellas"][0]["pending_child_count"], 1)
        self.assertEqual(payload["decomposition_previews"][0]["child_count"], 2)
        self.assertEqual(payload["accepted_routes"]["by_route"]["developer_wave"], 1)
        self.assertEqual(payload["accepted_routes"]["entries"][0]["route_truth_source"], "plan_meta.promoted_from")
        self.assertEqual(payload["confidence"]["status"], "high")
        waves_plain = MODULE.render_plain(payload, "waves")
        preview_plain = MODULE.render_plain(payload, "preview")
        accepted_plain = MODULE.render_plain(payload, "accepted-routes")
        self.assertIn("docs/plans/260619_1000_analysis.md", waves_plain)
        self.assertIn("pending_child_count=1", waves_plain)
        self.assertIn("child_count=2", preview_plain)
        self.assertIn("accepted_route=developer_wave", accepted_plain)

    def test_missing_and_ambiguous_truth_hosts_are_visible_but_not_accepted_route_truth(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            analysis_rel = "docs/plans/260619_1100_analysis.md"
            analysis_pack_rel = "docs/analysis_packs/260619_1100_analysis.md"
            analysis_draft_rel = "docs/code_drafts/260619_1100_analysis__code_draft.md"
            _write(
                root,
                analysis_rel,
                _plan(
                    title="analysis recommendation only",
                    status="Ready for Review",
                    plan_meta={"wave_family": "analysis_wave"},
                    body=(
                        "## Analysis pack\n"
                        "| Field | Value |\n"
                        "| --- | --- |\n"
                        f"| `analysis_pack_ref` | `{analysis_pack_rel}#Analysis-pack` |\n"
                        "| `authority_boundary` | `standalone_pack_only` |\n"
                    ),
                ),
            )
            _write(
                root,
                analysis_pack_rel,
                "# Analysis pack\n\n## Analysis pack\n"
                "| Field | Value |\n"
                "| --- | --- |\n"
                "| `route_recommendation` | `developer_wave` |\n",
            )
            _write(
                root,
                analysis_draft_rel,
                "# Draft\n\n```json\n"
                + json.dumps(
                    {
                        "code_draft_meta": {
                            "plan": analysis_rel,
                            "cluster": "process",
                            "targets": [{"path": analysis_pack_rel, "kind": "doc"}],
                            "deleted_paths": [],
                        }
                    },
                    indent=2,
                )
                + "\n```\n",
            )
            _write(
                root,
                "docs/plans/260619_1101_decomp.md",
                _plan(
                    title="missing child graph",
                    status="Ready for Coder",
                    plan_meta={"phase_overlay": "decomposition_wave", "phase_state": "active"},
                ),
            )

            payload = _build(root)

        codes = {item["code"] for item in payload["confidence"]["diagnostics"]}
        self.assertIn("recommendation_only_no_accepted_route", codes)
        self.assertIn("missing_child_graph", codes)
        recommendation = payload["buckets"]["recommendation_only_refs"][0]
        self.assertEqual(recommendation["state"], "recommendation_only_no_accepted_route")
        self.assertEqual(recommendation["recommended_route"], "developer_wave")
        self.assertEqual(payload["accepted_routes"]["entries"], [])
        self.assertEqual(payload["confidence"]["status"], "medium")

    def test_red_inconsistent_truth_hosts_downgrade_confidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _write(
                root,
                "docs/plans/260619_1201_child_a.md",
                _plan(title="child a", status="Done", plan_meta={}),
            )
            _write(
                root,
                "docs/plans/260619_1200_decomp.md",
                _plan(
                    title="red decomp",
                    status="Ready for Review",
                    plan_meta={
                        "phase_overlay": "decomposition_wave",
                        "phase_state": "active",
                    },
                    body=textwrap.dedent(
                        """\
                        ## Child plan map
                        - `docs/plans/260619_1201_child_a.md`

                        ## Execution queue
                        1. `docs/plans/260619_9999_missing_child.md`
                        """
                    ),
                ),
            )
            _write(
                root,
                "docs/plans/260619_1202_route.md",
                _plan(
                    title="route conflict",
                    status="Architect draft",
                    plan_meta={
                        "promoted_from": {
                            "accepted_route": "developer_wave",
                            "promoted_artifact_ref": "docs/plans/260619_9999_missing_route.md",
                        }
                    },
                    body=textwrap.dedent(
                        """\
                        ## Promoted route artifact
                        | Field | Value |
                        | --- | --- |
                        | `accepted_route` | `decomposition_wave` |
                        | `promoted_artifact_ref` | `docs/plans/260619_9999_missing_route.md` |
                        """
                    ),
                ),
            )

            payload = _build(root)

        codes = {item["code"] for item in payload["confidence"]["diagnostics"]}
        self.assertIn("child_map_execution_queue_mismatch", codes)
        self.assertIn("missing_child_plan", codes)
        self.assertIn("promoted_route_conflict", codes)
        self.assertIn("missing_promoted_artifact_ref", codes)
        self.assertEqual(payload["confidence"]["status"], "low")

    def test_main_writes_json_and_prints_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _write(
                root,
                "docs/plans/260619_1300_analysis.md",
                _plan(title="analysis", status="Ready for Review", plan_meta={"wave_family": "analysis_wave"}),
            )

            result = MODULE.main(["--root", str(root), "--generated-at", "2026-06-19T07:45:00Z"])
            payload = json.loads((root / ".tmp/planning_wave_readback.json").read_text(encoding="utf-8"))
            plain = MODULE.render_plain(payload)

        self.assertEqual(result, 0)
        self.assertEqual(payload["schema_version"], "planning_wave_readback.v1")
        self.assertIn("planning-wave-readback", plain)
        self.assertIn("open_analysis_waves: 1", plain)

    def test_plans_readme_and_template_are_not_plan_candidates(self) -> None:
        source_plans = MODULE_PATH.parent.parent / "docs/plans"
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            for name in ("README.md", "_template.md"):
                _write(root, f"docs/plans/{name}", (source_plans / name).read_text(encoding="utf-8"))

            payload = _build(root)

        self.assertEqual(payload["inputs"]["plan_count"], 0)
        self.assertEqual(
            payload["confidence"],
            {"status": "high", "reason": "all_readback_truth_hosts_consistent", "diagnostics": []},
        )


class PlanningWaveStrictReaderTests(unittest.TestCase):
    """J1 strict-reader migration: degraded diagnostics, never green summaries."""

    def _write_carrier_plan(self, root: Path, rel: str, meta_body: str) -> None:
        text = (
            "# Plan: strict carrier fixture\n\n"
            "**Status:** Ready for Review\n\n"
            "## Meta (machine-readable JSON; required for new plans)\n"
            "```json\n"
            f"{meta_body}\n"
            "```\n\n"
            "## Analysis pack\n"
            "N/A\n"
        )
        _write(root, rel, text)

    def test_malformed_and_duplicate_meta_degrade_confidence_not_green_summary(self) -> None:
        cases = (
            (
                "malformed",
                '{\n  "plan_meta": {\n    "wave_family": "analysis_wave",\n',
                "malformed_json",
            ),
            (
                "duplicate_key",
                "{\n"
                '  "plan_meta": {\n'
                '    "wave_family": "analysis_wave",\n'
                '    "wave_family": "analysis_wave",\n'
                '    "parent": null,\n'
                '    "depends_on": []\n'
                "  }\n"
                "}\n",
                "duplicate_json_key",
            ),
        )
        for label, meta_body, expected_code in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                self._write_carrier_plan(
                    root,
                    f"docs/plans/260829_1706_{label}_carrier.md",
                    meta_body,
                )

                payload = _build(root)

            diagnostics = payload["confidence"]["diagnostics"]
            strict_row = next(
                (item for item in diagnostics if item["code"] == "plan_meta_strict_read_failed"),
                None,
            )
            self.assertIsNotNone(strict_row)
            self.assertEqual(strict_row["reason_code"], expected_code)
            self.assertEqual(strict_row["truth_host"], f"docs/plans/260829_1706_{label}_carrier.md#plan_meta")
            self.assertNotEqual(payload["confidence"]["status"], "high")
            self.assertEqual(payload["buckets"]["open_analysis_waves"], [])
            self.assertEqual(payload["provenance_chains"], [])

    def test_module_reuses_shared_strict_reader_without_local_fence_scanner(self) -> None:
        self.assertFalse(
            hasattr(MODULE, "_json_block_after"),
            "planning_wave_readback must read Meta through "
            "plan_status_oracle.strict_plan_meta_json, not a local fence scanner",
        )
        self.assertTrue(hasattr(MODULE, "plan_status_oracle"))
        self.assertTrue(hasattr(MODULE.plan_status_oracle, "strict_plan_meta_json"))


class PlanningWaveExternalAnalysisPackTests(unittest.TestCase):
    STEM = "260729_0959_process_readback_external_authority"

    def _write_external(
        self,
        root: Path,
        *,
        stem: str | None = None,
        ref_annotation: str = "(refs-only annotation)",
        origin_rows: str = "",
        pack_route_recommendation: str = "`developer_wave`",
        pack_route_rows: tuple[str, ...] | None = None,
        accepted: bool = False,
        write_pack: bool = True,
    ) -> str:
        stem = stem or self.STEM
        plan_rel = f"docs/plans/{stem}.md"
        pack_rel = f"docs/analysis_packs/{stem}.md"
        draft_rel = f"docs/code_drafts/{stem}__code_draft.md"
        accepted_section = ""
        if accepted:
            accepted_section = textwrap.dedent(
                """\
                ## Promoted route artifact
                | Field | Value |
                | --- | --- |
                | `accepted_route` | `developer_wave` |
                | `promoted_artifact_ref` | `docs/plans/260729_1000_seed.md` |
                """
            )
        body = (
            "## Analysis pack\n"
            "| Field | Value |\n"
            "| --- | --- |\n"
            f"| `analysis_pack_ref` | `{pack_rel}#Analysis-pack` {ref_annotation} |\n"
            "| `authority_boundary` | `standalone_pack_only` |\n"
            f"{origin_rows}\n\n"
            f"{accepted_section}"
        )
        _write(
            root,
            plan_rel,
            _plan(
                title="external readback authority",
                status="Ready for Review",
                plan_meta={"cluster": "process", "wave_family": "analysis_wave"},
                body=body,
            ),
        )
        if write_pack:
            route_rows = (
                (pack_route_recommendation,)
                if pack_route_rows is None
                else pack_route_rows
            )
            _write(
                root,
                pack_rel,
                "# Analysis pack\n\n## Analysis pack\n"
                "| Field | Value |\n"
                "| --- | --- |\n"
                + "".join(
                    f"| `route_recommendation` | {value} |\n"
                    for value in route_rows
                )
                + "| `decomposition_sizing_rationale` | `decomposition_wave` is a rejected alternative |\n",
            )
        _write(
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
        return plan_rel

    def _replacement_snapshot(
        self,
        root: Path,
        selected_rel: str,
        replacement_data: bytes,
    ) -> tuple[object, list[str]]:
        target = root / selected_rel
        replacement = target.with_name(f".{target.name}.replacement")
        replacement.write_bytes(replacement_data)
        real_snapshot = MODULE.plan_status_oracle.snapshot_regular_or_absent
        calls: list[str] = []
        replaced = False

        def wrapped(trusted_root: Path, relative_path: str) -> object:
            nonlocal replaced
            calls.append(relative_path)
            if relative_path != selected_rel:
                return real_snapshot(trusted_root, relative_path)

            def observer(stage: str) -> None:
                nonlocal replaced
                if stage == "after_leaf_read" and not replaced:
                    replacement.replace(target)
                    replaced = True

            return real_snapshot(trusted_root, relative_path, _observer=observer)

        return wrapped, calls

    def test_plan_resident_pack_is_read_on_intake_and_missing_ref_after_it(self) -> None:
        plan_rel = f"docs/plans/{self.STEM}.md"
        body = (
            "## Analysis pack\n"
            "| Field | Value |\n"
            "| --- | --- |\n"
            "| `analysis_subject` | plan-resident subject |\n"
            "| `route_recommendation` | `developer_wave` |\n"
        )
        payloads: dict[str, dict[str, object]] = {}
        for status in ("Ready for Planner", "Superseded", "Ready for Review"):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                _write(
                    root,
                    plan_rel,
                    _plan(
                        title="plan-resident readback",
                        status=status,
                        plan_meta={"cluster": "process", "wave_family": "analysis_wave"},
                        body=body,
                    ),
                )
                payloads[status] = _build(root)

        def authority_rows(payload: dict[str, object]) -> list[dict[str, object]]:
            return [
                row
                for row in payload["confidence"]["diagnostics"]
                if row["code"] == "analysis_pack_authority_invalid"
            ]

        intake = payloads["Ready for Planner"]
        self.assertEqual(authority_rows(intake), [])
        self.assertEqual(
            intake["buckets"]["recommendation_only_refs"],
            [
                {
                    "plan": plan_rel,
                    "recommended_route": "developer_wave",
                    "truth_host": f"{plan_rel}#Analysis pack",
                    "state": "recommendation_only_no_accepted_route",
                }
            ],
        )
        self.assertEqual(authority_rows(payloads["Superseded"]), [])
        review = payloads["Ready for Review"]
        missing = authority_rows(review)
        self.assertEqual(len(missing), 1)
        self.assertTrue(missing[0]["detail"].startswith("detail_category=ref_missing;"))
        self.assertEqual(review["buckets"]["recommendation_only_refs"], [])

    def test_external_recommendation_uses_standalone_truth_host(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            plan_rel = self._write_external(root)
            payload = _build(root)

        row = payload["buckets"]["recommendation_only_refs"][0]
        self.assertEqual(payload["schema_version"], "planning_wave_readback.v1")
        self.assertEqual(row["plan"], plan_rel)
        self.assertEqual(
            row["truth_host"],
            f"docs/analysis_packs/{self.STEM}.md#Analysis-pack",
        )
        self.assertEqual(row["recommended_route"], "developer_wave")

    def test_external_recommendation_uses_primary_leading_route_token(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            plan_rel = self._write_external(
                root,
                pack_route_recommendation="`reject` because developer_wave was rejected",
            )
            payload = _build(root)

        row = payload["buckets"]["recommendation_only_refs"][0]
        self.assertEqual(row["plan"], plan_rel)
        self.assertEqual(row["recommended_route"], "reject")
        self.assertEqual(
            row["truth_host"],
            f"docs/analysis_packs/{self.STEM}.md#Analysis-pack",
        )
        diagnostic = next(
            item
            for item in payload["confidence"]["diagnostics"]
            if item["code"] == "recommendation_only_no_accepted_route"
        )
        self.assertEqual(diagnostic["recommended_route"], "reject")

    def test_external_malformed_primary_route_is_unknown(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            self._write_external(
                root,
                pack_route_recommendation="`not_a_route` because developer_wave is available",
            )
            payload = _build(root)

        row = payload["buckets"]["recommendation_only_refs"][0]
        self.assertEqual(row["recommended_route"], "unknown")
        diagnostic = next(
            item
            for item in payload["confidence"]["diagnostics"]
            if item["code"] == "recommendation_only_no_accepted_route"
        )
        self.assertEqual(diagnostic["recommended_route"], "unknown")

    def test_external_blank_recommendation_is_unknown(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            self._write_external(root, pack_route_recommendation="")
            payload = _build(root)

        row = payload["buckets"]["recommendation_only_refs"][0]
        self.assertEqual(row["recommended_route"], "unknown")
        self.assertEqual(
            row["truth_host"],
            f"docs/analysis_packs/{self.STEM}.md#Analysis-pack",
        )
        diagnostic = next(
            item
            for item in payload["confidence"]["diagnostics"]
            if item["code"] == "recommendation_only_no_accepted_route"
        )
        self.assertEqual(diagnostic["recommended_route"], "unknown")
        self.assertEqual(
            diagnostic["truth_host"],
            f"docs/analysis_packs/{self.STEM}.md#Analysis-pack",
        )

    def test_external_duplicate_recommendations_are_unknown(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            self._write_external(
                root,
                pack_route_rows=("`reject`", "`developer_wave`"),
            )
            payload = _build(root)

        row = payload["buckets"]["recommendation_only_refs"][0]
        self.assertEqual(row["recommended_route"], "unknown")
        self.assertEqual(
            row["truth_host"],
            f"docs/analysis_packs/{self.STEM}.md#Analysis-pack",
        )
        diagnostic = next(
            item
            for item in payload["confidence"]["diagnostics"]
            if item["code"] == "recommendation_only_no_accepted_route"
        )
        self.assertEqual(diagnostic["recommended_route"], "unknown")
        self.assertEqual(
            diagnostic["truth_host"],
            f"docs/analysis_packs/{self.STEM}.md#Analysis-pack",
        )

    def test_preboundary_angle_duplicate_uses_external_truth_and_suppresses_distribution(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            stem = "260729_0958_process_readback_angle_external_authority"
            self._write_external(
                root,
                stem=stem,
                ref_annotation="<human-note>",
                origin_rows="| `route_recommendation` | `reject` |",
            )
            payload = _build(root)

        diagnostics = payload["confidence"]["diagnostics"]
        invalid = [row for row in diagnostics if row["code"] == "analysis_pack_authority_invalid"]
        self.assertEqual(len(invalid), 1)
        self.assertIn("detail_category=operational_duplicate;", invalid[0]["detail"])
        self.assertEqual(
            invalid[0]["truth_host"],
            f"docs/analysis_packs/{stem}.md#Analysis-pack",
        )
        self.assertEqual(payload["buckets"]["recommendation_only_refs"], [])
        self.assertEqual(payload["confidence"]["status"], "low")

    def test_missing_pack_reports_identity_detail_without_mirror_fallback(self) -> None:
        with temporary_git_root() as tmpdir:
            root = Path(tmpdir)
            self._write_external(
                root,
                origin_rows="| `route_recommendation` | `reject` |",
                write_pack=False,
            )
            payload = _build(root)

        invalid = [
            row
            for row in payload["confidence"]["diagnostics"]
            if row["code"] == "analysis_pack_authority_invalid"
        ]
        self.assertEqual(len(invalid), 1)
        self.assertTrue(invalid[0]["detail"].startswith("detail_category=pack_missing;"))
        self.assertEqual(payload["buckets"]["recommendation_only_refs"], [])

    def test_synchronized_carrier_replacement_suppresses_recommendation(self) -> None:
        for carrier, expected in (
            ("draft", "draft_malformed"),
            ("pack", "pack_unreadable"),
        ):
            with self.subTest(carrier=carrier), temporary_git_root() as tmpdir:
                root = Path(tmpdir)
                self._write_external(root)
                draft_rel = f"docs/code_drafts/{self.STEM}__code_draft.md"
                pack_rel = f"docs/analysis_packs/{self.STEM}.md"
                selected_rel = draft_rel if carrier == "draft" else pack_rel
                expected_calls = [draft_rel] if carrier == "draft" else [draft_rel, pack_rel]
                source = root / selected_rel
                replacement_data = source.read_bytes().replace(
                    b"developer_wave",
                    b"reject",
                )
                wrapped, calls = self._replacement_snapshot(root, selected_rel, replacement_data)

                with mock.patch.object(
                    MODULE.plan_status_oracle,
                    "snapshot_regular_or_absent",
                    side_effect=wrapped,
                ):
                    payload = _build(root)

                invalid = [
                    row
                    for row in payload["confidence"]["diagnostics"]
                    if row["code"] == "analysis_pack_authority_invalid"
                ]
                self.assertEqual(calls, expected_calls)
                self.assertEqual(payload["schema_version"], "planning_wave_readback.v1")
                self.assertEqual(len(invalid), 1)
                self.assertTrue(
                    invalid[0]["detail"].startswith(
                        f"detail_category={expected};"
                    )
                )
                self.assertEqual(
                    invalid[0]["truth_host"],
                    f"docs/analysis_packs/{self.STEM}.md#Analysis-pack",
                )
                self.assertEqual(payload["buckets"]["recommendation_only_refs"], [])
                self.assertEqual(payload["confidence"]["status"], "low")
                self.assertFalse(
                    any(
                        row["code"] == "recommendation_only_no_accepted_route"
                        for row in payload["confidence"]["diagnostics"]
                    )
                )

    def test_symlinked_pack_and_draft_suppress_external_recommendation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            for carrier, expected in (
                ("pack", "pack_unreadable"),
                ("draft", "draft_malformed"),
            ):
                with self.subTest(carrier=carrier):
                    root = base / f"repo-{carrier}"
                    root.mkdir()
                    standalone_git_root(root)
                    self._write_external(root)
                    pack = root / f"docs/analysis_packs/{self.STEM}.md"
                    draft = root / f"docs/code_drafts/{self.STEM}__code_draft.md"
                    source = pack if carrier == "pack" else draft
                    outside = base / "outside" / f"{carrier}.md"
                    outside.parent.mkdir(parents=True, exist_ok=True)
                    outside.write_bytes(source.read_bytes())
                    source.unlink()
                    source.symlink_to(outside)

                    payload = _build(root)

                    invalid = [
                        row
                        for row in payload["confidence"]["diagnostics"]
                        if row["code"] == "analysis_pack_authority_invalid"
                    ]
                    self.assertEqual(len(invalid), 1)
                    self.assertTrue(
                        invalid[0]["detail"].startswith(
                            f"detail_category={expected};"
                        )
                    )
                    self.assertEqual(
                        payload["buckets"]["recommendation_only_refs"],
                        [],
                    )
                    self.assertEqual(payload["confidence"]["status"], "low")

    def test_accepted_route_truth_host_remains_origin_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            plan_rel = self._write_external(root, accepted=True)
            payload = _build(root)

        entry = payload["accepted_routes"]["entries"][0]
        self.assertEqual(entry["truth_host"], f"{plan_rel}#Promoted route artifact")
        self.assertEqual(payload["buckets"]["recommendation_only_refs"], [])

    def test_module_cold_import_bootstraps_sibling_oracle(self) -> None:
        script = textwrap.dedent(
            f"""\
            import importlib.util
            import sys
            from pathlib import Path
            path = Path({str(MODULE_PATH)!r})
            spec = importlib.util.spec_from_file_location("cold_planning_wave_readback", path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            assert module.SCHEMA_VERSION == "planning_wave_readback.v1"
            """
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=tmpdir,
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

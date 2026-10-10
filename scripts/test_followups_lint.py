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
from urllib.parse import unquote
from unittest import mock


def _load_script_module(name: str, filename: str):
    module_path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = _load_script_module("followups_lint", "followups_lint.py")
QUERY_MODULE = _load_script_module("followups_query", "followups_query.py")
RECONCILE_MODULE = _load_script_module("followups_reconcile", "followups_reconcile.py")
CODE_REVIEW_HARVEST_MODULE = _load_script_module("followups_code_reviews_harvest", "followups_code_reviews_harvest.py")
PROMOTE_MODULE = _load_script_module("followups_promote", "followups_promote.py")
PLAN_LINT_MODULE = _load_script_module("plan_lint_for_followups", "plan_lint.py")


_PROMOTION_FIXTURE_PLAN_VOCAB = {
    "plan_statuses": {
        "canonical": [
            "Architect initial draft",
            "Ready for Planner",
            "Ready for Coder",
            "Ready for Review",
            "Ready for Arch review",
            "Done",
            "Superseded",
        ],
        "groups": {
            "code_draft_required": ["architect initial draft"],
            "ui_micro_block_full_required": [],
            "ui_micro_block_off": ["architect initial draft"],
        },
    },
    "clusters": {
        "canonical": ["process"],
        "deprecated_aliases": {},
    },
    "phase_overlays": {
        "canonical": [],
        "states": {},
    },
    "manager_modes": {
        "canonical_required": ["manager-collab", "manager-custom-pipeline", "either"],
        "canonical_actual": ["manager-collab", "manager-custom-pipeline"],
        "required_from": "260712_1255",
    },
    "blocking_dependency_carrier": {
        "field": "blocking_depends_on",
        "shape": "sorted_unique_repo_relative_plan_path_array",
        "subset_of": "depends_on",
        "clearance": "delivery_green",
    },
}


def _write_promotion_fixture_plan_vocab(root: Path) -> Path:
    path = root / "docs" / "_meta" / "plan_vocab.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_PROMOTION_FIXTURE_PLAN_VOCAB, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


class FollowupsLintMalformedRowTests(unittest.TestCase):
    def _write_followup(self, root: Path, rel_path: str, body: str) -> Path:
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        return target

    def test_malformed_item_like_row_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            path = self._write_followup(
                root,
                "docs/followups/260327_2100_malformed_followups_master.md",
                dedent(
                    """\
                    # Follow-ups backlog — malformed fixture

                    **Date:** 27.03.2026 21:00
                    **Source:** review
                    **Status:** Draft

                    ## Follow-ups
                    - P2 Broken row without checkbox marker — cluster=process — tags=fixtures — to=Coder — status=open — plan=null — why: reviewer malformed-line proof
                    """
                ),
            )

            files = MODULE.load_followup_files(root)
            findings = MODULE.lint_followup_files(files, root)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "malformed_followup_row")
        self.assertEqual(findings[0].line_no, 8)
        self.assertIn("Malformed follow-up row", findings[0].message)
        self.assertEqual(path.name, "260327_2100_malformed_followups_master.md")

    def test_canonical_scaffolding_lines_are_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_followup(
                root,
                "docs/followups/260327_2101_scaffolding_followups_master.md",
                dedent(
                    """\
                    # Follow-ups backlog — scaffolding fixture

                    **Date:** 27.03.2026 21:01
                    **Source:** review
                    **Status:** Draft

                    ## Follow-ups (backlog)
                    Формат:
                    `P? [ ] <summary> — cluster=<...> — tags=<...> — to=<Planner|Architect|Coder|Owner> — status=<open|promoted|handled|UNCONFIRMED> — plan=<docs/plans/...|null> — why: ...`

                    ### Process
                    - P2 [ ] Good row — cluster=process — tags=fixtures — to=Coder — status=open — plan=null — why: green baseline
                      - Scope:
                        - Keep nested bullets legal inside a follow-up item.

                    ### Promoted draft plans
                    - (none) — P1 items are handled:
                      - `docs/plans/260124_1540_trackers_staff_ui_overview_history_settings.md` (`**Status:** Done`)
                    """
                ),
            )

            files = MODULE.load_followup_files(root)
            findings = MODULE.lint_followup_files(files, root)

        self.assertEqual(findings, [])

    def test_main_returns_non_zero_for_malformed_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_followup(
                root,
                "docs/followups/260327_2100_malformed_followups_master.md",
                dedent(
                    """\
                    # Follow-ups backlog — malformed fixture

                    **Date:** 27.03.2026 21:00
                    **Source:** review
                    **Status:** Draft

                    ## Follow-ups
                    P2 Broken row without leading dash — cluster=process — tags=fixtures — to=Coder — status=open — plan=null — why: reviewer malformed-line proof
                    """
                ),
            )
            stdout = io.StringIO()
            argv = [
                "followups_lint.py",
                "--project-root",
                str(root),
                "docs/followups/260327_2100_malformed_followups_master.md",
            ]

            with mock.patch.object(sys, "argv", argv):
                with mock.patch("sys.stdout", stdout):
                    result = MODULE.main()

        self.assertEqual(result, 1)
        output = stdout.getvalue()
        self.assertIn("malformed_followup_row", output)
        self.assertIn("260327_2100_malformed_followups_master.md:8", output)

    def test_load_followup_files_expands_directory_argument(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_followup(
                root,
                "docs/followups/260327_2102_directory_followups_master.md",
                dedent(
                    """\
                    # Follow-ups backlog — green fixture

                    **Date:** 27.03.2026 21:02
                    **Source:** review
                    **Status:** Draft

                    ## Follow-ups
                    - P2 [ ] Good row — cluster=process — tags=fixtures — to=Coder — status=open — plan=null — why: green baseline
                    """
                ),
            )

            files = MODULE.load_followup_files(root, ["docs/followups"])

        self.assertEqual([followup.rel_path for followup in files], ["docs/followups/260327_2102_directory_followups_master.md"])

    def test_main_accepts_directory_argument_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_followup(
                root,
                "docs/followups/260327_2102_directory_followups_master.md",
                dedent(
                    """\
                    # Follow-ups backlog — green fixture

                    **Date:** 27.03.2026 21:02
                    **Source:** review
                    **Status:** Draft

                    ## Follow-ups
                    - P2 [ ] Good row — cluster=process — tags=fixtures — to=Coder — status=open — plan=null — why: green baseline
                    """
                ),
            )
            stdout = io.StringIO()

            with mock.patch("sys.stdout", stdout):
                result = MODULE.main(["--project-root", str(root), "docs/followups"])

        self.assertEqual(result, 0)
        self.assertEqual(stdout.getvalue().strip(), "followups-lint: OK")

    def test_direct_child_symlink_is_rejected_by_nofollow_reader(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            followups_dir = root / "docs" / "followups"
            followups_dir.mkdir(parents=True)
            outside = root / "outside.md"
            outside.write_text("# outside\n", encoding="utf-8")
            os.symlink(outside, followups_dir / "260721_0200_symlink_followups.md")

            with self.assertRaisesRegex(Exception, "not a regular file"):
                MODULE.load_followup_files(root)

    def test_exact_source_ref_is_preserved_as_an_ordinary_row_field(self) -> None:
        rel_path = "docs/followups/260721_0201_source_ref_followups.md"
        parsed = MODULE.parse_followup_text(
            "# Follow-ups\n\n## Follow-ups\n"
            "- P1 [ ] Terminal finding — cluster=process — to=Coder — status=open — "
            "plan=null — source_ref=docs/plans/260716_1046_fixture.md — why: exact owner\n",
            rel_path,
            Path("/") / rel_path,
        )

        self.assertEqual(len(parsed.items), 1)
        self.assertEqual(
            parsed.items[0].fields["source_ref"],
            "docs/plans/260716_1046_fixture.md",
        )

    def test_imported_into_na_with_open_rows_is_not_real_import(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_followup(
                root,
                "docs/followups/260510_2200_followups_range.md",
                dedent(
                    """\
                    # Follow-ups backlog — N/A import fixture

                    **Date:** 10.05.2026 22:00
                    **Source:** plan harvest
                    **Status:** ✅ Done
                    **Imported into:** `N/A (why=standalone receipt; no master import row created)`

                    ## Follow-ups
                    - P2 [ ] Open row — cluster=process — tags=fixtures — to=Planner — status=open — plan=null — why: should not be hidden
                    """
                ),
            )

            files = MODULE.load_followup_files(root)
            findings = MODULE.lint_followup_files(files, root)

        self.assertIn("imported_into_without_real_target_for_open_rows", [finding.code for finding in findings])
        self.assertEqual(MODULE.ready_candidates(files)[0].summary, "Open row")

    def test_real_imported_inbox_is_skipped_from_ready_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_followup(
                root,
                "docs/followups/260510_2201_followups_range.md",
                dedent(
                    """\
                    # Follow-ups backlog — imported fixture

                    **Date:** 10.05.2026 22:01
                    **Source:** plan harvest
                    **Status:** ✅ Done
                    **Imported into:** `docs/followups/process_followups_master.md`

                    ## Follow-ups
                    - P2 [ ] Imported row — cluster=process — tags=fixtures — to=Planner — status=open — plan=null — why: should be hidden by query
                    """
                ),
            )
            self._write_followup(
                root,
                "docs/followups/process_followups_master.md",
                dedent(
                    """\
                    # Follow-ups backlog — process master

                    **Date:** 10.05.2026 22:01
                    **Source:** triage
                    **Status:** Draft

                    ## Follow-ups
                    - P2 [ ] Imported row — cluster=process — tags=fixtures — to=Planner — status=open — plan=null — why: authoritative row
                    """
                ),
            )

            files = MODULE.load_followup_files(root)
            ready = MODULE.ready_candidates(files)
            cleanup = MODULE.cleanup_ready(files)

        self.assertEqual([item.rel_path for item in ready], ["docs/followups/process_followups_master.md"])
        self.assertEqual([followup.rel_path for followup in cleanup], ["docs/followups/260510_2201_followups_range.md"])


class FollowupsLintStatusFamilyTests(unittest.TestCase):
    def _write_followup(self, root: Path, rel_path: str, body: str) -> Path:
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        return target

    def test_process_improvement_only_statuses_are_rejected_in_followups(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_followup(
                root,
                "docs/followups/260620_0045_wrong_family_followups.md",
                dedent(
                    """\
                    # Follow-ups backlog — wrong family fixture

                    **Date:** 20.06.2026 00:45
                    **Source:** process-improvement boundary test
                    **Status:** Draft
                    **Schema version:** followups.v1

                    ## Follow-ups
                    - P2 [ ] Triaged row — cluster=process — tags=fixtures — to=Coder — status=triaged — plan=null — why: PI lifecycle state copied into ordinary followups
                    - P2 [ ] Deferred row — cluster=process — tags=fixtures — to=Coder — status=deferred — plan=null — why: PI lifecycle state copied into ordinary followups
                    - P2 [ ] Rejected row — cluster=process — tags=fixtures — to=Coder — status=rejected — plan=null — why: PI lifecycle state copied into ordinary followups
                    """
                ),
            )

            files = MODULE.load_followup_files(root)
            findings = MODULE.lint_followup_files(files, root)

        status_findings = [finding for finding in findings if finding.code == "invalid_status"]
        self.assertEqual([finding.line_no for finding in status_findings], [9, 10, 11])
        self.assertEqual(len(status_findings), 3)
        for status, finding in zip(("triaged", "deferred", "rejected"), status_findings, strict=True):
            self.assertIn(f"`status={status}` belongs to `docs/process_improvements/*`", finding.message)
            self.assertIn("Allowed follow-up statuses: `handled`, `open`, `promoted`, `unconfirmed`", finding.message)
            self.assertIn("backlink/delivery_refs bridge", finding.message)


class FollowupsLintSchemaVersionTests(unittest.TestCase):
    def _write_followup(self, root: Path, rel_path: str, body: str) -> Path:
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        return target

    def _parse_followup(self, rel_path: str, body: str):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            target = root / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(dedent(body), encoding="utf-8")
            followup = MODULE.parse_followup_file(target, root)
            return MODULE.classify_followups_schema_version(followup)

    def test_current_followups_schema_version_is_accepted(self) -> None:
        state, findings = self._parse_followup(
            "docs/followups/260419_1103_followups_schema_current.md",
            """\
            # Follow-ups backlog — schema current

            **Date:** 19.04.2026 11:03
            **Source:** review
            **Status:** Draft
            **Schema version:** followups.v2

            ## Follow-ups
            - P2 [ ] Good row — cluster=process — tags=fixtures — to=Coder — status=open — plan=null — why: schema current fixture
            """,
        )

        self.assertEqual(state, "v2")
        self.assertEqual(findings, [])

    def test_versionless_non_template_followups_file_is_legacy(self) -> None:
        state, findings = self._parse_followup(
            "docs/followups/260419_1104_followups_schema_legacy.md",
            """\
            # Follow-ups backlog — schema legacy

            **Date:** 19.04.2026 11:04
            **Source:** review
            **Status:** Draft

            ## Follow-ups
            - P2 [ ] Good row — cluster=process — tags=fixtures — to=Coder — status=open — plan=null — why: schema legacy fixture
            """,
        )

        self.assertEqual(state, "legacy_v1")
        self.assertEqual(findings, [])

    def test_missing_schema_version_on_followups_template_is_reported(self) -> None:
        state, findings = self._parse_followup(
            "docs/followups/_template_followups_backlog.md",
            """\
            # Follow-ups backlog — template

            **Date:** DD.MM.YYYY HH:MM
            **Source:** review
            **Status:** Draft

            ## Follow-ups
            - P2 [ ] Good row — cluster=process — tags=fixtures — to=Coder — status=open — plan=null — why: template schema fixture
            """,
        )

        self.assertEqual(state, "unsupported")
        self.assertEqual(len(findings), 1)
        self.assertIn("Missing `**Schema version:** followups.v2`", findings[0].message)

    def test_wrong_followups_schema_version_is_reported(self) -> None:
        state, findings = self._parse_followup(
            "docs/followups/260419_1105_followups_schema_unsupported.md",
            """\
            # Follow-ups backlog — schema unsupported

            **Date:** 19.04.2026 11:05
            **Source:** review
            **Status:** Draft
            **Schema version:** review.v1

            ## Follow-ups
            - P2 [ ] Good row — cluster=process — tags=fixtures — to=Coder — status=open — plan=null — why: schema unsupported fixture
            """,
        )

        self.assertEqual(state, "unsupported")
        self.assertEqual(len(findings), 1)
        self.assertIn("Unsupported followups schema version", findings[0].message)


class FollowupsSnapshotInventoryTests(unittest.TestCase):
    def _write(self, root: Path, rel_path: str, text: str) -> None:
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def _v2_row(self, item_id: str = "snapshot-001") -> str:
        return MODULE.render_v2_row(
            {
                "priority": "P1",
                "summary": "Snapshot inventory row",
                "cluster": "process",
                "to": "coder",
                "status": "open",
                "plan": None,
                "why": "classify one immutable carrier snapshot",
                "tags": [],
                "item_id": item_id,
                "source_ref": "docs/plans/snapshot_source.md",
                "disposition_kind": None,
                "disposition_ref": None,
                "disposition_commit_oid": None,
                "reason": None,
            }
        )

    def _inventory(self, root: Path):
        try:
            from scripts import followups_capture
        except ModuleNotFoundError:
            import followups_capture
        snapshot, file_bytes = followups_capture.snapshot_followups(root, include_bytes=True)
        return MODULE._inventory_followups_snapshot(root, snapshot, file_bytes)

    def test_proven_legacy_and_valid_v2_are_distinct_without_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write(
                root,
                "docs/followups/legacy.md",
                "# Legacy\n\n**Schema version:** followups.v1\n\n## Follow-ups\n- P1 [ ] malformed legacy row\n",
            )
            self._write(
                root,
                "docs/followups/valid.md",
                "# V2\n\n**Schema version:** followups.v2\n\n## Follow-ups (backlog)\n"
                + self._v2_row()
                + "\n",
            )

            inventory = self._inventory(root)

        self.assertEqual(set(inventory.legacy_v1), {"docs/followups/legacy.md"})
        self.assertEqual(set(inventory.valid_v2), {"docs/followups/valid.md"})
        self.assertEqual(inventory.blockers, ())

    def test_explicit_v2_integrity_failures_are_never_reclassified_as_legacy(self) -> None:
        cases = {
            "duplicate_header": (
                "# V2\n\n**Schema version:** followups.v2\n**Schema version:** followups.v2\n\n## Follow-ups\n"
                + self._v2_row()
                + "\n",
                "multiple_schema_version_headers",
            ),
            "unknown_header": (
                "# V2\n\n**Schema version:** followups.v9\n\n## Follow-ups\n" + self._v2_row() + "\n",
                "unsupported_schema_version",
            ),
            "missing_section": (
                "# V2\n\n**Schema version:** followups.v2\n\n" + self._v2_row() + "\n",
                "v2_followups_section_count_invalid",
            ),
            "multiple_sections": (
                "# V2\n\n**Schema version:** followups.v2\n\n## Follow-ups\n"
                + self._v2_row()
                + "\n\n## Follow-ups\n",
                "v2_followups_section_count_invalid",
            ),
            "malformed_row": (
                "# V2\n\n**Schema version:** followups.v2\n\n## Follow-ups\n"
                "- P1 [ ] missing required V2 fields — status=open\n",
                "v2_missing_fields",
            ),
        }
        for name, (text, expected_code) in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                rel_path = "docs/followups/foreign.md"
                self._write(root, rel_path, text)
                inventory = self._inventory(root)
                codes = {finding.code for finding in inventory.blockers}
                self.assertIn(expected_code, codes)
                self.assertNotIn(rel_path, inventory.legacy_v1)
                self.assertNotIn(rel_path, inventory.valid_v2)

    def test_non_utf8_snapshot_bytes_are_a_v2_integrity_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            rel_path = "docs/followups/non_utf8.md"
            raw = b"\xff"
            inventory = MODULE._inventory_followups_snapshot(
                root,
                {
                    rel_path: {
                        "sha256": hashlib.sha256(raw).hexdigest(),
                        "file_type": "regular",
                        "st_size": len(raw),
                    }
                },
                {rel_path: raw},
            )

        self.assertEqual([finding.code for finding in inventory.blockers], ["followups_snapshot_not_utf8"])

    def test_main_accepts_project_root_dot_repo_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write(
                root,
                "docs/followups/260327_2103_repo_scope_followups_master.md",
                dedent(
                    """\
                    # Follow-ups backlog — repo-scope fixture

                    **Date:** 27.03.2026 21:03
                    **Source:** review
                    **Status:** Draft

                    ## Follow-ups
                    - P2 [ ] Good row — cluster=process — tags=fixtures — to=Planner — status=open — plan=null — why: repo-scope baseline
                    """
                ),
            )
            stdout = io.StringIO()
            old_cwd = Path.cwd()
            os.chdir(root)
            try:
                with mock.patch("sys.stdout", stdout):
                    result = MODULE.main(["--project-root", "."])
            finally:
                os.chdir(old_cwd)

        self.assertEqual(result, 0)
        self.assertEqual(stdout.getvalue().strip(), "followups-lint: OK")


class FollowupsV2LegacyBridgeTests(unittest.TestCase):
    def _write(self, root: Path, rel_path: str, text: str) -> Path:
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dedent(text), encoding="utf-8")
        return path

    def _bridge_payload(self, plan_path: str, plan_bytes: bytes, row: dict[str, object], *, item_id: str) -> dict[str, object]:
        return {
            "priority": "P1",
            "summary": f"Legacy bridge {item_id}",
            "cluster": "process",
            "to": "architect",
            "status": "open",
            "plan": None,
            "why": "bounded immutable V1 bridge proof",
            "item_id": item_id,
            "source_ref": plan_path,
            "disposition_kind": None,
            "disposition_ref": None,
            "disposition_commit_oid": None,
            "reason": None,
            "legacy_row_ref": "plan_meta.followups_out[1]",
            "legacy_plan_sha256": hashlib.sha256(plan_bytes).hexdigest(),
            "legacy_row_sha256": hashlib.sha256(
                json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
        }

    def test_bridge_is_exactly_hash_bound_and_duplicate_identity_is_red(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_path = "docs/plans/260811_0100_legacy_bridge.md"
            legacy_row = {"cluster": "process", "summary": "frozen V1 row", "plan": None}
            plan_text = (
                "# Plan: legacy bridge\n\n"
                "**Status:** Done\n"
                "**Schema version:** plan.v1\n\n"
                "```json\n"
                + json.dumps({"plan_meta": {"followups_out": [legacy_row]}}, ensure_ascii=False)
                + "\n```\n"
            )
            plan = self._write(root, plan_path, plan_text)
            payload = self._bridge_payload(plan_path, plan.read_bytes(), legacy_row, item_id="bridge-001")
            duplicate = dict(payload, item_id="bridge-002")
            bridge_text = (
                "# Follow-ups backlog — bridge\n\n"
                "**Schema version:** followups.v2\n\n"
                "## Follow-ups (backlog)\n"
                + MODULE.render_v2_row(payload)
                + "\n"
            )
            bridge = self._write(root, "docs/followups/bridge.md", bridge_text)

            green = MODULE.lint_followup_files(MODULE.load_followup_files(root), root)
            self.assertEqual(green, [])
            self.assertIn("legacy_row_ref=plan_meta.followups_out[1]", bridge.read_text(encoding="utf-8"))

            plan.write_text(plan_text.replace("frozen V1 row", "changed V1 row"), encoding="utf-8")
            stale_codes = {finding.code for finding in MODULE.lint_followup_files(MODULE.load_followup_files(root), root)}
            self.assertIn("v2_legacy_bridge_plan_hash_mismatch", stale_codes)
            self.assertIn("v2_legacy_bridge_row_hash_mismatch", stale_codes)

            plan.write_text(plan_text, encoding="utf-8")
            bridge.write_text(bridge_text + MODULE.render_v2_row(duplicate) + "\n", encoding="utf-8")
            duplicate_codes = {finding.code for finding in MODULE.lint_followup_files(MODULE.load_followup_files(root), root)}
            self.assertIn("v2_legacy_bridge_duplicate", duplicate_codes)


class FollowupsHarvestLosslessTests(unittest.TestCase):
    def _write_file(self, root: Path, rel_path: str, body: str) -> Path:
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(dedent(body), encoding="utf-8")
        return target

    def test_code_review_harvest_preserves_source_intent_and_canon_summary(self) -> None:
        item = CODE_REVIEW_HARVEST_MODULE.ReviewItem(
            review_path="docs/code_reviews/example_line_by_line.md",
            section="risk",
            num=1,
            title="  Retry loop hides the original error  ",
            line_no=12,
        )

        followup = CODE_REVIEW_HARVEST_MODULE._make_new_followup_line(item, cluster="process")

        # Only generic normalization applies: the title is trimmed, never rewritten.
        self.assertEqual(followup.summary, "Retry loop hides the original error")
        source_intent = CODE_REVIEW_HARVEST_MODULE._extract_field(followup.body, "source_intent")
        canon_summary = CODE_REVIEW_HARVEST_MODULE._extract_field(followup.body, "canon_summary")
        self.assertIsNotNone(source_intent)
        self.assertIsNotNone(canon_summary)
        assert source_intent is not None
        assert canon_summary is not None
        self.assertEqual(unquote(source_intent), "Retry loop hides the original error")
        self.assertEqual(unquote(canon_summary), "Retry loop hides the original error")
        self.assertNotIn("original:", followup.body)

    def test_code_review_harvest_does_not_dedupe_distinct_raw_titles(self) -> None:
        # Both titles share one normalized summary key; the lossless source
        # intent still keeps them apart.
        title_a = "Retry loop hides the original error"
        title_b = "retry loop hides the ORIGINAL error!"
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_file(
                root,
                "docs/code_reviews/example_line_by_line.md",
                f"""\
                # Review fixture

                ## Risk
                1) **{title_a}**
                2) **{title_b}**
                """,
            )
            out_path = root / "docs/followups/out.md"
            stdout = io.StringIO()

            with mock.patch.object(CODE_REVIEW_HARVEST_MODULE, "REPO_ROOT", root):
                with mock.patch("sys.stdout", stdout):
                    result = CODE_REVIEW_HARVEST_MODULE.main(
                        [
                            "--src",
                            "docs/code_reviews/example_line_by_line.md",
                            "--out",
                            "docs/followups/out.md",
                        ]
                    )

            rows = CODE_REVIEW_HARVEST_MODULE._parse_followup_lines(out_path.read_text(encoding="utf-8"))

        self.assertEqual(result, 0)
        self.assertIn("items_out=2 mapped=0 created=2 deduped=0", stdout.getvalue())
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            {unquote(CODE_REVIEW_HARVEST_MODULE._extract_field(row.body, "source_intent") or "") for row in rows},
            {title_a, title_b},
        )
        self.assertEqual({row.summary for row in rows}, {title_a, title_b})
        self.assertEqual(
            {CODE_REVIEW_HARVEST_MODULE._normalize_summary(row.summary) for row in rows},
            {"retry loop hides the original error"},
        )

    def test_code_review_harvest_header_uses_cleanup_receipt_candidate_wording(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_file(
                root,
                "docs/code_reviews/example_line_by_line.md",
                """\
                # Review fixture

                ## Risk
                1) **Retry loop hides the original error**
                """,
            )
            out_path = root / "docs/followups/out.md"
            stdout = io.StringIO()

            with mock.patch.object(CODE_REVIEW_HARVEST_MODULE, "REPO_ROOT", root):
                with mock.patch("sys.stdout", stdout):
                    result = CODE_REVIEW_HARVEST_MODULE.main(
                        [
                            "--src",
                            "docs/code_reviews/example_line_by_line.md",
                            "--out",
                            "docs/followups/out.md",
                        ]
                    )

            text = out_path.read_text(encoding="utf-8")

        self.assertEqual(result, 0)
        self.assertIn("cleanup-receipt candidate", text)
        self.assertIn("decision=delete-ready", text)
        self.assertNotIn("После импорта inbox можно удалять", text)



class FollowupsReconcileProofClassTests(unittest.TestCase):
    def _write_file(self, root: Path, rel_path: str, body: str) -> Path:
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(dedent(body), encoding="utf-8")
        return target

    def _write_promoted_followup(self, root: Path, plan_path: str) -> None:
        self._write_file(
            root,
            "docs/followups/process_followups_master.md",
            f"""\
            # Follow-ups backlog — process master

            **Date:** 20.06.2026 09:30
            **Source:** fixture
            **Status:** Draft

            ## Follow-ups
            - P2 [ ] Promoted row — cluster=process — tags=fixtures — to=Planner — status=promoted — plan={plan_path} — why: proof class fixture
            """,
        )

    def test_bare_done_plan_needs_closure_proof_instead_of_candidate_handled(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_path = "docs/plans/260620_0930_bare_done.md"
            self._write_promoted_followup(root, plan_path)
            self._write_file(
                root,
                plan_path,
                """\
                # Plan: bare done

                **Status:** Done
                """,
            )

            files = MODULE.load_followup_files(root)
            candidates = MODULE.candidate_handled(files, root)
            needs_proof = MODULE.candidate_needs_closure_proof(files, root)
            payload = RECONCILE_MODULE._report_payload(root)

        self.assertEqual(candidates, [])
        self.assertEqual(len(needs_proof), 1)
        self.assertEqual(payload["candidate_handled"], [])
        self.assertEqual(len(payload["candidate_needs_closure_proof"]), 1)
        row = payload["candidate_needs_closure_proof"][0]
        self.assertEqual(row["reason"], "candidate_needs_closure_proof")
        self.assertIsNone(row["target_closure_proof_class"])

    def test_done_plan_with_arch_review_proof_can_be_candidate_handled(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            plan_path = "docs/plans/260620_0931_done_with_proof.md"
            self._write_promoted_followup(root, plan_path)
            self._write_file(
                root,
                plan_path,
                """\
                # Plan: done with proof

                **Status:** Done

                ## Evidence
                - [2026-06-20 09:31 MSK] (Architect arch review -> Done) Accepted review. Gates: `PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3 -B scripts/review_artifact_lint.py --origin-plan docs/plans/260620_0931_done_with_proof.md docs/code_reviews/260620_0931_done_with_proof.md` -> exit 0; `zsh -lc 'source scripts/planveyor.zsh && planveyor_plan_bundle --check docs/plans/260620_0931_done_with_proof.md'` -> exit 0.
                """,
            )

            files = MODULE.load_followup_files(root)
            candidates = MODULE.candidate_handled(files, root)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0][1].closure_proof_class, "arch_review_ok")


class FollowupsCleanupReceiptTests(unittest.TestCase):
    def _write_file(self, root: Path, rel_path: str, body: str) -> Path:
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(dedent(body), encoding="utf-8")
        return target

    def test_cleanup_receipt_delete_ready_when_imported_summary_and_no_reverse_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_file(
                root,
                "docs/followups/260510_2300_followups_range.md",
                """\
                # Follow-ups backlog — imported fixture

                **Date:** 10.05.2026 23:00
                **Source:** plan harvest
                **Status:** ✅ Done
                **Imported into:** `docs/followups/process_followups_master.md`

                ## Follow-ups
                - P2 [x] Imported row — cluster=process — tags=fixtures — to=Planner — status=handled — plan=null — why: imported summary preserved
                """,
            )
            self._write_file(
                root,
                "docs/followups/process_followups_master.md",
                """\
                # Follow-ups backlog — process master

                **Date:** 10.05.2026 23:00
                **Source:** triage
                **Status:** Draft

                ## Follow-ups
                - P2 [x] Imported row — cluster=process — tags=fixtures — to=Planner — status=handled — plan=null — why: authoritative row
                """,
            )

            rows = MODULE.cleanup_receipt_rows(MODULE.load_followup_files(root), root)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["decision"], "delete-ready")
        self.assertTrue(rows[0]["semantic_compression_preserved"])
        self.assertEqual(rows[0]["reverse_references"], [])

    def test_cleanup_receipt_retain_when_reverse_reference_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            source = "docs/followups/260510_2301_followups_range.md"
            self._write_file(
                root,
                source,
                """\
                # Follow-ups backlog — referenced fixture

                **Date:** 10.05.2026 23:01
                **Source:** plan harvest
                **Status:** ✅ Done
                **Imported into:** `docs/followups/process_followups_master.md`

                ## Follow-ups
                - P2 [x] Referenced row — cluster=process — tags=fixtures — to=Planner — status=handled — plan=null — why: imported summary preserved
                """,
            )
            self._write_file(
                root,
                "docs/followups/process_followups_master.md",
                """\
                # Follow-ups backlog — process master

                **Date:** 10.05.2026 23:01
                **Source:** triage
                **Status:** Draft

                ## Follow-ups
                - P2 [x] Referenced row — cluster=process — tags=fixtures — to=Planner — status=handled — plan=null — why: authoritative row
                """,
            )
            self._write_file(
                root,
                "docs/plans/260510_2301_reference.md",
                f"""\
                # Plan: reference

                This plan still links to `{source}`.
                """,
            )

            rows = MODULE.cleanup_receipt_rows(MODULE.load_followup_files(root), root)

        self.assertEqual(rows[0]["decision"], "retain")
        self.assertEqual(rows[0]["reverse_reference_count"], 1)
        self.assertIn("reverse references remain", rows[0]["reason"])

    def test_cleanup_receipt_needs_richer_summary_when_import_loses_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_file(
                root,
                "docs/followups/260510_2302_followups_range.md",
                """\
                # Follow-ups backlog — lossy import fixture

                **Date:** 10.05.2026 23:02
                **Source:** plan harvest
                **Status:** ✅ Done
                **Imported into:** `docs/followups/process_followups_master.md`

                ## Follow-ups
                - P2 [x] Lost semantic detail — cluster=process — tags=fixtures — to=Planner — status=handled — plan=null — why: not preserved
                """,
            )
            self._write_file(
                root,
                "docs/followups/process_followups_master.md",
                """\
                # Follow-ups backlog — process master

                **Date:** 10.05.2026 23:02
                **Source:** triage
                **Status:** Draft

                ## Follow-ups
                - P2 [x] Different short row — cluster=process — tags=fixtures — to=Planner — status=handled — plan=null — why: lossy row
                """,
            )

            files = MODULE.load_followup_files(root)
            self.assertEqual([followup.rel_path for followup in MODULE.cleanup_ready(files)], ["docs/followups/260510_2302_followups_range.md"])
            rows = MODULE.cleanup_receipt_rows(files, root)

        self.assertEqual(rows[0]["decision"], "needs-richer-summary")
        self.assertFalse(rows[0]["semantic_compression_preserved"])
        self.assertEqual(rows[0]["missing_summaries"], ["Lost semantic detail"])

    def test_cleanup_receipt_exposes_source_status_classification_and_proof_class(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_file(
                root,
                "docs/followups/260510_2304_followups_range.md",
                """\
                # Follow-ups backlog — proof class fixture

                **Date:** 10.05.2026 23:04
                **Source:** plan harvest
                **Status:** ✅ Done
                **Imported into:** `docs/followups/process_followups_master.md`

                ## Follow-ups
                - P2 [ ] Closure proof row — cluster=process — tags=fixtures — to=Planner — status=promoted — plan=docs/plans/260510_2304_done_with_proof.md — why: imported summary preserved
                """,
            )
            self._write_file(
                root,
                "docs/followups/process_followups_master.md",
                """\
                # Follow-ups backlog — process master

                **Date:** 10.05.2026 23:04
                **Source:** triage
                **Status:** Draft

                ## Follow-ups
                - P2 [ ] Closure proof row — cluster=process — tags=fixtures — to=Planner — status=promoted — plan=docs/plans/260510_2304_done_with_proof.md — why: authoritative row
                """,
            )
            self._write_file(
                root,
                "docs/plans/260510_2304_done_with_proof.md",
                """\
                # Plan: done with proof

                **Status:** Done

                ## Evidence
                - [2026-05-10 23:04 MSK] (Architect arch review -> Done) Accepted review. Gates: `PYTHONDONTWRITEBYTECODE=1 /opt/homebrew/bin/python3 -B scripts/review_artifact_lint.py --origin-plan docs/plans/260510_2304_done_with_proof.md docs/code_reviews/260510_2304_done_with_proof.md` -> exit 0; `zsh -lc 'source scripts/planveyor.zsh && planveyor_plan_bundle --check docs/plans/260510_2304_done_with_proof.md'` -> exit 0.
                """,
            )

            rows = MODULE.cleanup_receipt_rows(MODULE.load_followup_files(root), root)

        self.assertEqual(rows[0]["source_statuses"], ["promoted"])
        self.assertEqual(rows[0]["source_classifications"], ["process"])
        self.assertEqual(rows[0]["proof_classes"], ["arch_review_ok"])
        self.assertEqual(rows[0]["item_refs"][0]["proof_class"], "arch_review_ok")
        self.assertEqual(rows[0]["missing_proof_refs"], [])

    def test_cleanup_receipt_needs_richer_summary_for_bare_done_terminal_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_file(
                root,
                "docs/followups/260510_2305_followups_range.md",
                """\
                # Follow-ups backlog — missing proof fixture

                **Date:** 10.05.2026 23:05
                **Source:** plan harvest
                **Status:** ✅ Done
                **Imported into:** `docs/followups/process_followups_master.md`

                ## Follow-ups
                - P2 [ ] Missing proof row — cluster=process — tags=fixtures — to=Planner — status=promoted — plan=docs/plans/260510_2305_bare_done.md — why: imported summary preserved
                """,
            )
            self._write_file(
                root,
                "docs/followups/process_followups_master.md",
                """\
                # Follow-ups backlog — process master

                **Date:** 10.05.2026 23:05
                **Source:** triage
                **Status:** Draft

                ## Follow-ups
                - P2 [ ] Missing proof row — cluster=process — tags=fixtures — to=Planner — status=promoted — plan=docs/plans/260510_2305_bare_done.md — why: authoritative row
                """,
            )
            self._write_file(
                root,
                "docs/plans/260510_2305_bare_done.md",
                """\
                # Plan: bare done

                **Status:** Done
                """,
            )

            rows = MODULE.cleanup_receipt_rows(MODULE.load_followup_files(root), root)

        self.assertEqual(rows[0]["decision"], "needs-richer-summary")
        self.assertEqual(len(rows[0]["missing_proof_refs"]), 1)
        self.assertIn("terminal plan refs need explicit closure proof class", rows[0]["reason"])

    def test_followups_query_cleanup_receipt_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_file(
                root,
                "docs/followups/260510_2303_followups_range.md",
                """\
                # Follow-ups backlog — query fixture

                **Date:** 10.05.2026 23:03
                **Source:** plan harvest
                **Status:** ✅ Done
                **Imported into:** `docs/followups/process_followups_master.md`

                ## Follow-ups
                - P2 [x] Query row — cluster=process — tags=fixtures — to=Planner — status=handled — plan=null — why: query summary preserved
                """,
            )
            self._write_file(
                root,
                "docs/followups/process_followups_master.md",
                """\
                # Follow-ups backlog — process master

                **Date:** 10.05.2026 23:03
                **Source:** triage
                **Status:** Draft

                ## Follow-ups
                - P2 [x] Query row — cluster=process — tags=fixtures — to=Planner — status=handled — plan=null — why: authoritative row
                """,
            )
            stdout = io.StringIO()

            with mock.patch("sys.stdout", stdout):
                result = QUERY_MODULE.main(["cleanup-receipt", "--project-root", str(root), "--format", "json"])

        self.assertEqual(result, 0)
        payload = __import__("json").loads(stdout.getvalue())
        self.assertEqual(payload["view"], "cleanup-receipt")
        self.assertEqual(payload["candidate_count"], 1)
        self.assertEqual(payload["rows"][0]["decision"], "delete-ready")

    def test_followups_query_cleanup_receipt_text_operator_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            delete_ready_source = "docs/followups/260510_2306_delete_ready.md"
            retain_source = "docs/followups/260510_2307_retain.md"
            missing_proof_source = "docs/followups/260510_2308_missing_proof.md"
            missing_proof_plan = "docs/plans/260510_2308_bare_done.md"
            self._write_file(
                root,
                delete_ready_source,
                """\
                # Follow-ups backlog — delete ready fixture

                **Date:** 10.05.2026 23:06
                **Source:** plan harvest
                **Status:** ✅ Done
                **Imported into:** `docs/followups/process_followups_master.md`

                ## Follow-ups
                - P2 [x] Delete ready row — cluster=process — tags=fixtures — to=Planner — status=handled — plan=null — why: summary preserved
                """,
            )
            self._write_file(
                root,
                retain_source,
                """\
                # Follow-ups backlog — retain fixture

                **Date:** 10.05.2026 23:07
                **Source:** plan harvest
                **Status:** ✅ Done
                **Imported into:** `docs/followups/process_followups_master.md`

                ## Follow-ups
                - P2 [x] Retain row — cluster=process — tags=fixtures — to=Planner — status=handled — plan=null — why: summary preserved
                """,
            )
            self._write_file(
                root,
                missing_proof_source,
                f"""\
                # Follow-ups backlog — missing proof fixture

                **Date:** 10.05.2026 23:08
                **Source:** plan harvest
                **Status:** ✅ Done
                **Imported into:** `docs/followups/process_followups_master.md`

                ## Follow-ups
                - P2 [ ] Missing proof row — cluster=process — tags=fixtures — to=Planner — status=promoted — plan={missing_proof_plan} — why: summary preserved
                """,
            )
            self._write_file(
                root,
                "docs/followups/process_followups_master.md",
                f"""\
                # Follow-ups backlog — process master

                **Date:** 10.05.2026 23:08
                **Source:** triage
                **Status:** Draft

                ## Follow-ups
                - P2 [x] Delete ready row — cluster=process — tags=fixtures — to=Planner — status=handled — plan=null — why: authoritative row
                - P2 [x] Retain row — cluster=process — tags=fixtures — to=Planner — status=handled — plan=null — why: authoritative row
                - P2 [ ] Missing proof row — cluster=process — tags=fixtures — to=Planner — status=promoted — plan={missing_proof_plan} — why: authoritative row
                """,
            )
            self._write_file(
                root,
                "docs/plans/260510_2307_reference.md",
                f"""\
                # Plan: reference

                This plan still links to `{retain_source}`.
                """,
            )
            self._write_file(
                root,
                missing_proof_plan,
                """\
                # Plan: bare done

                **Status:** Done
                """,
            )
            stdout = io.StringIO()

            with mock.patch("sys.stdout", stdout):
                result = QUERY_MODULE.main(["cleanup-receipt", "--project-root", str(root), "--format", "text"])

        self.assertEqual(result, 0)
        output = stdout.getvalue()
        self.assertIn("view: cleanup-receipt", output)
        self.assertIn("candidate_count: 3", output)
        self.assertIn("decision_counts: delete-ready=1; retain=1; needs-richer-summary=1; other=0", output)
        self.assertIn("read_only: true; decision=delete-ready is not deletion permission", output)
        self.assertIn("delete-ready checklist:", output)
        self.assertIn(f"- [ ] {delete_ready_source} | items=1", output)
        self.assertIn(f"source_path={delete_ready_source} | decision=delete-ready", output)
        self.assertIn(f"source_path={retain_source} | decision=retain", output)
        self.assertIn("reverse_reference_count=1", output)
        self.assertIn(f"source_path={missing_proof_source} | decision=needs-richer-summary", output)
        self.assertIn(f"missing_proof_refs=1[{missing_proof_plan}]", output)


class FollowupsPromoteManagerModeTests(unittest.TestCase):
    def test_promotion_cli_emits_explicit_either_and_lintable_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            fixture_home = root / "home"
            fixture_home.mkdir()
            git_env = {
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_AUTHOR_NAME": "Follow-ups promotion fixture",
                "GIT_AUTHOR_EMAIL": 'followups-promotion-fixture' + '@' + 'example' + '.' + 'invalid',
                "GIT_COMMITTER_NAME": "Follow-ups promotion fixture",
                "GIT_COMMITTER_EMAIL": 'followups-promotion-fixture' + '@' + 'example' + '.' + 'invalid',
                "HOME": str(fixture_home),
                "LC_ALL": "C",
            }

            def git(*arguments: str) -> None:
                subprocess.run(
                    [
                        "git",
                        "-c",
                        "core.hooksPath=/dev/null",
                        "-c",
                        "commit.gpgSign=false",
                        "-C",
                        str(root),
                        *arguments,
                    ],
                    check=True,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=git_env,
                    timeout=20,
                )

            git("init", "--quiet")
            git("commit", "--allow-empty", "--quiet", "-m", "fixture root")
            _write_promotion_fixture_plan_vocab(root)
            followups = root / "docs/followups/process_followups_master.md"
            followups.parent.mkdir(parents=True)
            followups.write_text(
                dedent(
                    """\
                    # Follow-ups backlog — mode fixture

                    **Date:** 17.07.2026 19:40
                    **Source:** test
                    **Status:** Draft

                    ## Follow-ups
                    - P2 [ ] Mode fixture — cluster=process — tags=manager-mode — to=Architect — status=open — plan=null — why: fixture
                    """
                ),
                encoding="utf-8",
            )
            plan = root / "docs/plans/260712_1255_mode_fixture.md"
            stdout = io.StringIO()
            with mock.patch("sys.stdout", stdout):
                rc = PROMOTE_MODULE.main(
                    [
                        "--project-root",
                        str(root),
                        "--file",
                        "docs/followups/process_followups_master.md",
                        "--line",
                        "8",
                        "--plan-path",
                        "docs/plans/260712_1255_mode_fixture.md",
                        "--apply",
                        "--format",
                        "json",
                    ]
                )
            self.assertEqual(rc, 0)
            rendered = plan.read_text(encoding="utf-8")
            self.assertIn('"required_manager_mode": "either"', rendered)
            findings = PLAN_LINT_MODULE.lint_plan(plan)
        errors = [finding.message for finding in findings if finding.severity == "ERROR"]
        self.assertFalse(errors, "\n".join(errors))


if __name__ == "__main__":
    unittest.main()

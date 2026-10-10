#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from textwrap import dedent


MODULE_PATH = Path(__file__).with_name("range_review_risk_packet.py")
SPEC = importlib.util.spec_from_file_location("range_review_risk_packet", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

import range_review_risk_packet_schema_contract


NON_RANGE_TARGET = "BUNDLE=current"


class RangeReviewRiskPacketTests(unittest.TestCase):
    def test_schema_version_uses_shared_contract(self) -> None:
        self.assertEqual(
            MODULE.SCHEMA_VERSION,
            range_review_risk_packet_schema_contract.RANGE_REVIEW_RISK_PACKET_SCHEMA_VERSION,
        )
        self.assertEqual(MODULE.SCHEMA_VERSION, "range_review_risk_packet.v1")

    def _git(self, root: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            text=True,
            capture_output=True,
            check=True,
        )
        return result.stdout.strip()

    def _write(self, root: Path, rel_path: str, body: str) -> Path:
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    def _init_repo(self, root: Path) -> tuple[str, str]:
        subprocess.run(["git", "-C", str(root), "init"], check=True, capture_output=True)
        self._git(root, "config", "user.email", 'test' + '@' + 'example' + '.' + 'com')
        self._git(root, "config", "user.name", "Test User")
        self._write(root, "README.md", "seed\n")
        self._git(root, "add", ".")
        self._git(root, "commit", "-m", "seed")
        base = self._git(root, "rev-parse", "HEAD")
        self._write(root, "apps/catalog/models.py", "changed runtime\n")
        self._write(root, "scripts/review_helper.py", "changed helper\n")
        self._write(root, "docs/playbooks/review_merge_range.md", "changed docs\n")
        self._git(root, "add", ".")
        self._git(root, "commit", "-m", "range changes")
        head = self._git(root, "rev-parse", "HEAD")
        self._range_ref = f"{base}..{head}"
        return base, head

    def _canonical_target(self) -> str:
        return f"RANGE={self._range_ref} (EXCLUDE_DOCS=0)"

    def _write_origin_plan(
        self,
        root: Path,
        rel_path: str = "docs/plans/origin.md",
        *,
        target_snapshot: str | None = None,
    ) -> str:
        if target_snapshot is None:
            target_snapshot = self._canonical_target()
        payload = {
            "lane_id": "reviewer_code_risk",
            "run_id": "reviewer_code_risk-20260618T150000Z",
            "target_snapshot": target_snapshot,
            "lane_status": "no_findings",
            "current": True,
            "written_at": "2026-06-18T15:00:00Z",
        }
        self._write(
            root,
            rel_path,
            dedent(
                f"""\
                # Plan

                **Status:** Done

                ## Evidence
                - reviewer_code_risk lane-run artifact:
                  ```json
                  {json.dumps(payload, indent=2, sort_keys=True)}
                  ```
                """
            ),
        )
        return rel_path

    def _write_review(
        self,
        root: Path,
        *,
        status: str = "✅ OK",
        live_blocker: bool = False,
        target: str | None = None,
        spec: str | None = None,
        include_target: bool = True,
        include_spec: bool = True,
    ) -> str:
        if target is None:
            target = self._canonical_target()
        plan_rel = self._write_origin_plan(root, target_snapshot=target)
        spec_value = spec if spec is not None else plan_rel
        headers = [
            "**Schema version:** review.v1",
            "**Date:** 2026-06-18 15:00 MSK",
        ]
        if include_target:
            headers.append(f"**Target:** {target}")
        if include_spec:
            headers.append(f"**Spec:** {spec_value}")
        headers.append(f"**Status:** {status}")
        header_block = "\n".join(headers)
        blocker_section = (
            dedent(
                """\
                ## S1 Blocker

                ### B1

                - Blocker ID: `B1`
                - Current state: `live`
                - Classification: `implementation contract gap`
                - Primary owner gap: `Coder`
                - Evidence refs: `scripts/review_helper.py:1`
                """
            )
            if live_blocker
            else "## S1 Blocker\n\nN/A (why=live S1 blockers not found; previous B1 is historical-fixed by same-file rerun).\n"
        )
        review_rel = "docs/code_reviews/260618_1500_range_review.md"
        review_body = dedent(
            f"""\
                # Код-ревью - range fixture

                {header_block}

                ОК: fixture summary.

                ## reviewer_code_risk

                - Lane status: `no_findings`
                - Target snapshot: `{target}`
                - Coverage domains: `correctness`

                ## reviewer_code_contracts

                - Lane status: `complete`
                - Target snapshot: `{target}`
                - Coverage domains: `plan fidelity`

                ## Lane synthesis / aggregate verdict

                - Source lanes: `reviewer_code_risk`, `reviewer_code_contracts`
                - Aggregate status: `{status}`
                - source_lane: `reviewer_code_risk+reviewer_code_contracts`
                - lane_finding_id: `N/A (no lane findings)`
                - synthesis_disposition: `no_findings`
                - canonical_ref: `{review_rel}#Lane-synthesis--aggregate-verdict`
                - audit_status: `pending_post_merge_audit`
                - followup_plan: `N/A`

                {blocker_section}
                ## S2 Risk

                N/A (why=non-blocking risks not found).

                ## Визуальные доказательства

                - Visual env: `N/A (why=process helper)`
                """
        )
        fixture_prefix = " " * 16
        review_body = "\n".join(
            line[len(fixture_prefix):] if line.startswith(fixture_prefix) else line
            for line in review_body.splitlines()
        ) + "\n"
        self._write(root, review_rel, review_body)
        return review_rel

    def _write_truth_hosts(self, root: Path, base: str, head: str) -> dict[str, str]:
        b7 = base[:7]
        h7 = head[:7]
        hosts = {
            "post_merge_audit": f"docs/reviews/260618_1501_post_merge_audit_range_{b7}_{h7}.md",
            "operational_receipt": f"docs/reviews/260618_1502_post_merge_operational_receipt_range_{b7}_{h7}.md",
            "ready_to_push_closeout": f"docs/reviews/260618_1503_ready_to_push_closeout_range_{b7}_{h7}.md",
            "packetization_report": f"docs/reviews/260618_1504_packetization_gate_range_{b7}_{h7}.md",
        }
        self._write(root, hosts["post_merge_audit"], "# Post-merge audit\n\n**Status:** ✅ Done\n")
        self._write(
            root,
            hosts["operational_receipt"],
            "# Post-merge operational receipt\n\n**Status:** ✅ Done\n\n`post_merge_operational_receipt.v1`\n",
        )
        self._write(
            root,
            hosts["ready_to_push_closeout"],
            "# Ready-to-push closeout\n\n**Status:** ✅ Done\n\n`ready_to_push_closeout_receipt.v1`\n",
        )
        packet_payload = {
            "packetization_gate": {
                "schema_version": "packetization_gate.v1",
                "blocking_count": 0,
                "range": f"{base}..{head}",
            }
        }
        self._write(
            root,
            hosts["packetization_report"],
            "# Packetization gate report\n\n**Status:** Done\n\n```json\n"
            + json.dumps(packet_payload, indent=2, sort_keys=True)
            + "\n```\n",
        )
        return hosts

    def _materialize_runtime_visual_contract(self, root: Path, review_rel: str, *, green: bool) -> None:
        review_stem = Path(review_rel).stem
        payload = {
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
            "human_commands_by_mode": {"primary": "./scripts/human.sh --mode primary", "secondary": "./scripts/human.sh --mode secondary"},
            "human_index_paths_by_mode": {"primary": ".tmp/primary/index.md", "secondary": ".tmp/secondary/index.md"},
            "human_output_roots_by_mode": {"primary": ".tmp/primary", "secondary": ".tmp/secondary"},
            "complete_index_required": True,
            "durable_review_asset_root": f"docs/code_reviews/assets/{review_stem}/",
            "reason": "repo_backed_visual_lane",
        }
        plan = root / "docs" / "plans" / "origin.md"
        plan.write_text(
            plan.read_text(encoding="utf-8")
            + "\n## Review visual lane contract\n\n"
            + MODULE.review_artifact_lint.review_visual_lane_contract.render_materialized_contract(payload)
            + "\n",
            encoding="utf-8",
        )
        if not green:
            return
        asset_root = root / "docs" / "code_reviews" / "assets" / review_stem
        asset_root.mkdir(parents=True, exist_ok=True)
        (asset_root / "primary.png").write_bytes(b"png")
        (asset_root / "secondary.png").write_bytes(b"png")
        visual = dedent(
            f"""\
            ## Визуальные доказательства

            - Comparator command: `./scripts/run_visual_check.sh --repeat 2`
            - Comparator claim: `mechanical`
            - Comparator result: `pass`
            - Capture status: `complete`
            - Complete index inspected: `yes`
            - Design verdict: `no_findings`
            - Mandatory modes: `primary, secondary`
            - Human index (primary): `.tmp/primary/index.md`
            - Human index (secondary): `.tmp/secondary/index.md`
            - Durable asset (primary): `docs/code_reviews/assets/{review_stem}/primary.png`
            - Durable asset (secondary): `docs/code_reviews/assets/{review_stem}/secondary.png`
            """
        )
        review = root / review_rel
        before = review.read_text(encoding="utf-8").split("## Визуальные доказательства", 1)[0]
        review.write_text(before + visual, encoding="utf-8")

    def _run_main(self, args: list[str]) -> tuple[int, str]:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            rc = MODULE.main(args)
        return rc, stdout.getvalue()

    def test_generates_compact_packet_with_truth_hosts_and_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            base, head = self._init_repo(root)
            review_rel = self._write_review(root)
            hosts = self._write_truth_hosts(root, base, head)
            out_rel = f"docs/reviews/260618_150500_risk_packet_range_{base[:7]}_{head[:7]}.md"

            rc, stdout = self._run_main(
                [
                    "--repo-root",
                    str(root),
                    "--range",
                    f"{base}..{head}",
                    "--review-artifact",
                    review_rel,
                    "--post-merge-audit",
                    hosts["post_merge_audit"],
                    "--operational-receipt",
                    hosts["operational_receipt"],
                    "--ready-to-push-closeout",
                    hosts["ready_to_push_closeout"],
                    "--packetization-report",
                    hosts["packetization_report"],
                    "--out",
                    out_rel,
                    "--json",
                ]
            )

            self.assertEqual(rc, 0, stdout)
            payload = json.loads(stdout)["range_review_risk_packet"]
            self.assertEqual(payload["schema_version"], MODULE.SCHEMA_VERSION)
            self.assertEqual(payload["packet_status"], "ok")
            self.assertEqual(payload["target_snapshot"], f"RANGE={base}..{head} (EXCLUDE_DOCS=0)")
            self.assertIn("apps/catalog/models.py", payload["runtime_touched_paths"])
            self.assertIn("scripts/review_helper.py", payload["helper_process_touched_paths"])
            self.assertIn("docs/playbooks/review_merge_range.md", payload["helper_process_touched_paths"])
            self.assertEqual(payload["visual_status"]["status"], "N/A")
            self.assertEqual(payload["historical_blockers"][0]["id"], "B1")
            self.assertEqual(payload["truth_hosts"]["review_artifact"]["path"], review_rel)
            self.assertEqual(
                payload["truth_hosts"]["post_merge_audit"],
                {
                    "kind": "post_merge_audit",
                    "path": hosts["post_merge_audit"],
                    "status": "✅ Done",
                    "event_type": "review.post_merge_audit",
                },
            )
            self.assertEqual(payload["truth_hosts"]["packetization_report"]["schema_version"], "packetization_gate.v1")
            packet_text = (root / out_rel).read_text(encoding="utf-8")
            self.assertIn("## Risk packet JSON", packet_text)
            self.assertIn("range_review_risk_packet.v1", packet_text)

    def test_post_merge_audit_event_type_uses_filename_or_first_h1_identity(self) -> None:
        cases = (
            (
                "h1_only",
                "audit_receipt",
                "# Review:  Post-merge   audit\n\n**Status:** ✅ Done\n",
                "✅ Done",
                "review.post_merge_audit",
            ),
            (
                "body_marker_only",
                "unrelated_receipt",
                "# Review: unrelated receipt\n\n**Status:** ✅ Done\n\n`review.post_merge_audit`\n",
                "✅ Done",
                "unknown",
            ),
            (
                "later_h1_only",
                "unrelated_receipt",
                "# Review: unrelated receipt\n\n**Status:** ✅ Done\n\n# Post-merge audit\n",
                "✅ Done",
                "unknown",
            ),
            (
                "indented_h1_only",
                "unrelated_receipt",
                "# Review: unrelated receipt\n\n**Status:** ✅ Done\n\n  # Post-merge audit\n",
                "✅ Done",
                "unknown",
            ),
            (
                "indented_first_audit_h1",
                "audit_receipt",
                "**Status:** ✅ Done\n\n  # Post-merge audit\n",
                "unknown",
                "review.post_merge_audit",
            ),
            (
                "indented_first_unrelated_h1_before_later_raw_audit",
                "unrelated_receipt",
                "**Status:** ✅ Done\n\n  # Review: unrelated receipt\n\n# Post-merge audit\n",
                "unknown",
                "unknown",
            ),
        )
        for label, stem, audit_text, expected_status, expected_event_type in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                base, head = self._init_repo(root)
                review_rel = self._write_review(root)
                hosts = self._write_truth_hosts(root, base, head)
                audit_rel = f"docs/reviews/260618_1501_{stem}_range_{base[:7]}_{head[:7]}.md"
                self._write(root, audit_rel, audit_text)

                payload, errors = MODULE.build_packet_payload(
                    repo_root=root,
                    range_ref=f"{base}..{head}",
                    out_path=root / "docs/reviews/out.md",
                    host_paths={
                        "review_artifact": root / review_rel,
                        **{key: root / rel_path for key, rel_path in hosts.items()},
                        "post_merge_audit": root / audit_rel,
                    },
                    changed_files=(),
                )

                self.assertEqual(errors, [])
                assert payload is not None
                self.assertEqual(
                    payload["truth_hosts"]["post_merge_audit"],
                    {
                        "kind": "post_merge_audit",
                        "path": audit_rel,
                        "status": expected_status,
                        "event_type": expected_event_type,
                    },
                )

    def test_runtime_visual_red_blocks_packet_ok_and_green_passes(self) -> None:
        for green in (False, True):
            with self.subTest(green=green), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                base, head = self._init_repo(root)
                review_rel = self._write_review(root)
                hosts = self._write_truth_hosts(root, base, head)
                self._materialize_runtime_visual_contract(root, review_rel, green=green)
                payload, errors = MODULE.build_packet_payload(
                    repo_root=root,
                    range_ref=f"{base}..{head}",
                    out_path=root / "docs/reviews/out.md",
                    host_paths={"review_artifact": root / review_rel, **{key: root / value for key, value in hosts.items()}},
                    changed_files=["templates/page.html"],
                )
                if green:
                    self.assertFalse(errors)
                    self.assertIsNotNone(payload)
                    self.assertEqual(payload["packet_status"], "ok")
                    self.assertEqual(payload["visual_status"]["status"], "green")
                else:
                    self.assertIsNone(payload)
                    self.assertEqual([error.code for error in errors], ["runtime_ui_visual_evidence_red"])

    def test_body_target_or_spec_cannot_satisfy_packet_proof(self) -> None:
        cases = (
            ("target", False, True, "**Target:** BUNDLE=current", "missing_review_target"),
            ("spec", True, False, "**Spec:** docs/plans/origin.md", "missing_review_spec"),
        )
        for case, include_target, include_spec, body_field, expected_code in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                base, head = self._init_repo(root)
                review_rel = self._write_review(
                    root,
                    include_target=include_target,
                    include_spec=include_spec,
                )
                review_path = root / review_rel
                review_path.write_text(
                    review_path.read_text(encoding="utf-8")
                    + f"\n```text\n{body_field}\n```\n",
                    encoding="utf-8",
                )
                hosts = self._write_truth_hosts(root, base, head)
                host_paths = {
                    "review_artifact": review_path,
                    **{key: root / rel_path for key, rel_path in hosts.items()},
                }

                payload, errors = MODULE.build_packet_payload(
                    repo_root=root,
                    range_ref=f"{base}..{head}",
                    out_path=root / "docs/reviews/out.md",
                    host_paths=host_paths,
                    changed_files=(),
                )

            self.assertIsNone(payload)
            self.assertIn(expected_code, {error.code for error in errors})

    def test_missing_or_duplicate_status_blocks_packet(self) -> None:
        for case, mutate, expected_code in (
            (
                "missing",
                lambda text: text.replace("**Status:** ✅ OK\n", "", 1)
                + "\n```text\n**Status:** ✅ OK\n```\n",
                "missing_review_status",
            ),
            (
                "duplicate",
                lambda text: text.replace(
                    "**Status:** ✅ OK\n",
                    "**Status:** ✅ OK\n**Status :** ❌ S1 blocker(ы)\n",
                    1,
                ),
                "ambiguous_review_status",
            ),
            (
                "noncanonical",
                lambda text: text.replace("**Status:** ✅ OK\n", "**Status :** ✅ OK\n", 1),
                "invalid_review_status",
            ),
        ):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                base, head = self._init_repo(root)
                review_rel = self._write_review(root)
                review_path = root / review_rel
                review_path.write_text(
                    mutate(review_path.read_text(encoding="utf-8")),
                    encoding="utf-8",
                )
                hosts = self._write_truth_hosts(root, base, head)
                host_paths = {
                    "review_artifact": review_path,
                    **{key: root / rel_path for key, rel_path in hosts.items()},
                }

                payload, errors = MODULE.build_packet_payload(
                    repo_root=root,
                    range_ref=f"{base}..{head}",
                    out_path=root / "docs/reviews/out.md",
                    host_paths=host_paths,
                    changed_files=(),
                )

            self.assertIsNone(payload)
            self.assertEqual([error.code for error in errors], [expected_code])

    def test_body_superseded_status_does_not_supersede_packet(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            packet = self._write(
                root,
                "docs/reviews/260618_150601_risk_packet_range_abc_def.md",
                "# Packet\n\n**Status:** ✅ Done\n\nBody.\n**Status:** Superseded\n",
            )

            self.assertFalse(MODULE.packet_is_superseded(packet))

    def test_packetization_schema_version_legacy_fallback_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            base, head = self._init_repo(root)
            review_rel = self._write_review(root)
            hosts = self._write_truth_hosts(root, base, head)
            legacy_payload = {"packetization_gate": {"blocking_count": 0, "range": f"{base}..{head}"}}
            self._write(
                root,
                hosts["packetization_report"],
                "# Packetization gate report\n\n**Status:** Done\n\n```json\n"
                + json.dumps(legacy_payload, indent=2, sort_keys=True)
                + "\n```\n",
            )

            payload, errors = MODULE.build_packet_payload(
                repo_root=root,
                range_ref=f"{base}..{head}",
                out_path=root / "docs/reviews/out.md",
                host_paths={
                    "review_artifact": root / review_rel,
                    **{key: root / value for key, value in hosts.items()},
                },
                changed_files=MODULE.changed_files_for_range(root, f"{base}..{head}"),
            )

        self.assertEqual(errors, [])
        assert payload is not None
        self.assertEqual(payload["truth_hosts"]["packetization_report"]["schema_version"], "packetization_gate")

    def test_live_blocker_keeps_packet_blocked_without_shadow_green_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            base, head = self._init_repo(root)
            review_rel = self._write_review(root, status="❌ S1 blocker(ы)", live_blocker=True)
            hosts = self._write_truth_hosts(root, base, head)

            payload, errors = MODULE.build_packet_payload(
                repo_root=root,
                range_ref=f"{base}..{head}",
                out_path=root / "docs/reviews/out.md",
                host_paths={
                    "review_artifact": root / review_rel,
                    **{key: root / value for key, value in hosts.items()},
                },
                changed_files=MODULE.changed_files_for_range(root, f"{base}..{head}"),
            )

            self.assertEqual(errors, [])
            assert payload is not None
            self.assertEqual(payload["packet_status"], "review_blocked")
            self.assertEqual(payload["live_blockers"][0]["id"], "B1")

    def test_present_but_red_review_with_green_derived_summary_keeps_packet_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            base, head = self._init_repo(root)
            review_rel = self._write_review(root, status="❌ S1 blocker(ы)", live_blocker=False)
            hosts = self._write_truth_hosts(root, base, head)

            payload, errors = MODULE.build_packet_payload(
                repo_root=root,
                range_ref=f"{base}..{head}",
                out_path=root / "docs/reviews/out.md",
                host_paths={
                    "review_artifact": root / review_rel,
                    **{key: root / value for key, value in hosts.items()},
                },
                changed_files=MODULE.changed_files_for_range(root, f"{base}..{head}"),
            )

            self.assertEqual(errors, [])
            assert payload is not None
            self.assertEqual(payload["packet_status"], "review_blocked")
            self.assertEqual(payload["truth_hosts"]["review_artifact"]["status"], "❌ S1 blocker(ы)")
            self.assertEqual(payload["truth_hosts"]["packetization_report"]["blocking_count"], 0)
            self.assertEqual(payload["live_blockers"][0]["id"], "B1")
            self.assertEqual(payload["live_blockers"][0]["state"], "live_missing_details")
            self.assertEqual(payload["live_blockers"][0]["truth_host"], f"{review_rel}#S1-Blocker")

    def test_missing_target_carrier_fails_before_packet_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            base, head = self._init_repo(root)
            review_rel = self._write_review(root, include_target=False)
            hosts = self._write_truth_hosts(root, base, head)

            payload, errors = MODULE.build_packet_payload(
                repo_root=root,
                range_ref=f"{base}..{head}",
                out_path=root / "docs/reviews/out.md",
                host_paths={
                    "review_artifact": root / review_rel,
                    **{key: root / value for key, value in hosts.items()},
                },
                changed_files=MODULE.changed_files_for_range(root, f"{base}..{head}"),
            )

        self.assertIsNone(payload)
        self.assertEqual([error.code for error in errors], ["missing_review_target"])

    def test_missing_spec_carrier_fails_before_packet_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            base, head = self._init_repo(root)
            review_rel = self._write_review(root, include_spec=False)
            hosts = self._write_truth_hosts(root, base, head)

            payload, errors = MODULE.build_packet_payload(
                repo_root=root,
                range_ref=f"{base}..{head}",
                out_path=root / "docs/reviews/out.md",
                host_paths={
                    "review_artifact": root / review_rel,
                    **{key: root / value for key, value in hosts.items()},
                },
                changed_files=MODULE.changed_files_for_range(root, f"{base}..{head}"),
            )

        self.assertIsNone(payload)
        self.assertEqual([error.code for error in errors], ["missing_review_spec"])

    def test_invalid_spec_carrier_fails_with_exact_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            base, head = self._init_repo(root)
            review_rel = self._write_review(root, spec="N/A (why=origin plan missing)")
            hosts = self._write_truth_hosts(root, base, head)

            payload, errors = MODULE.build_packet_payload(
                repo_root=root,
                range_ref=f"{base}..{head}",
                out_path=root / "docs/reviews/out.md",
                host_paths={
                    "review_artifact": root / review_rel,
                    **{key: root / value for key, value in hosts.items()},
                },
                changed_files=MODULE.changed_files_for_range(root, f"{base}..{head}"),
            )

        self.assertIsNone(payload)
        self.assertEqual([error.code for error in errors], ["invalid_review_spec"])

    def test_manual_no_origin_spec_is_accepted_without_plan_risk_lane(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            base, head = self._init_repo(root)
            target = f"RANGE={base}..{head} (EXCLUDE_DOCS=0)"
            review_rel = self._write_review(
                root,
                spec="N/A (origin_plan_state=manual_range_review_no_origin_plan)",
                target=target,
            )
            hosts = self._write_truth_hosts(root, base, head)

            payload, errors = MODULE.build_packet_payload(
                repo_root=root,
                range_ref=f"{base}..{head}",
                out_path=root / "docs/reviews/out.md",
                host_paths={
                    "review_artifact": root / review_rel,
                    **{key: root / value for key, value in hosts.items()},
                },
                changed_files=MODULE.changed_files_for_range(root, f"{base}..{head}"),
            )

        self.assertEqual(errors, [])
        assert payload is not None
        self.assertEqual(payload["target_snapshot"], target)

    def test_manual_no_origin_spec_rejects_mismatched_target_range(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            base, head = self._init_repo(root)
            review_rel = self._write_review(
                root,
                spec="N/A (origin_plan_state=manual_range_review_no_origin_plan)",
                target=f"RANGE={head}..{base} (EXCLUDE_DOCS=0)",
            )
            hosts = self._write_truth_hosts(root, base, head)

            payload, errors = MODULE.build_packet_payload(
                repo_root=root,
                range_ref=f"{base}..{head}",
                out_path=root / "docs/reviews/out.md",
                host_paths={
                    "review_artifact": root / review_rel,
                    **{key: root / value for key, value in hosts.items()},
                },
                changed_files=MODULE.changed_files_for_range(root, f"{base}..{head}"),
            )

        self.assertIsNone(payload)
        self.assertEqual([error.code for error in errors], ["manual_no_origin_target_mismatch"])

    def test_non_range_or_current_shaped_target_blocks_before_payload_or_output(self) -> None:
        cases = {
            "bare_current": NON_RANGE_TARGET,
            "canonical_current": "BUNDLE=current bundle_sha256=" + "0" * 64,
            "reordered_current": "bundle_sha256=" + "0" * 64 + " BUNDLE=current",
            "non_range": "PLAN=docs/plans/origin.md",
            "wrong_range": "RANGE=" + "b" * 40 + ".." + "a" * 40 + " (EXCLUDE_DOCS=1)",
        }
        for label, target in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                base, head = self._init_repo(root)
                review_rel = self._write_review(root, target=target)
                hosts = self._write_truth_hosts(root, base, head)
                out_path = root / "docs/reviews/blocked.md"
                payload, errors = MODULE.build_packet_payload(
                    repo_root=root,
                    range_ref=f"{base}..{head}",
                    out_path=out_path,
                    host_paths={"review_artifact": root / review_rel, **{key: root / value for key, value in hosts.items()}},
                    changed_files=(),
                )

                self.assertIsNone(payload)
                self.assertEqual([error.code for error in errors], ["risk_packet_target_mismatch"])
                self.assertFalse(out_path.exists())

    def test_origin_plan_snapshot_mismatch_blocks_before_payload_or_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            base, head = self._init_repo(root)
            review_rel = self._write_review(root)
            wrong_target = f"RANGE={head}..{base} (EXCLUDE_DOCS=0)"
            origin_path = root / "docs/plans/origin.md"
            origin_path.write_text(
                origin_path.read_text(encoding="utf-8").replace(self._canonical_target(), wrong_target),
                encoding="utf-8",
            )
            hosts = self._write_truth_hosts(root, base, head)
            out_path = root / "docs/reviews/blocked.md"
            payload, errors = MODULE.build_packet_payload(
                repo_root=root,
                range_ref=f"{base}..{head}",
                out_path=out_path,
                host_paths={"review_artifact": root / review_rel, **{key: root / value for key, value in hosts.items()}},
                changed_files=(),
            )

        self.assertIsNone(payload)
        self.assertEqual([error.code for error in errors], ["risk_lane_target_mismatch"])
        self.assertFalse(out_path.exists())

    def test_durable_readback_requires_canonical_range_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            base, head = self._init_repo(root)
            target = f"RANGE={base}..{head} (EXCLUDE_DOCS=1)"
            review_rel = self._write_review(root, target=target)
            hosts = self._write_truth_hosts(root, base, head)
            payload, errors = MODULE.build_packet_payload(
                repo_root=root,
                range_ref=f"{base}..{head}",
                out_path=root / "docs/reviews/out.md",
                host_paths={"review_artifact": root / review_rel, **{key: root / value for key, value in hosts.items()}},
                changed_files=(),
            )
            self.assertEqual(errors, [])
            assert payload is not None

            canonical_rel = f"docs/reviews/260618_150610_risk_packet_range_{base[:7]}_{head[:7]}.md"
            self._write(root, canonical_rel, MODULE.render_packet_markdown(payload))
            canonical = MODULE.read_risk_packet(root, range_ref=f"{base}..{head}", risk_packet_path=Path(canonical_rel))
            self.assertTrue(canonical.ok)

            for label, invalid_target in {
                "current": NON_RANGE_TARGET,
                "non_range": "PLAN=docs/plans/origin.md",
            }.items():
                invalid_payload = dict(payload)
                invalid_payload["target_snapshot"] = invalid_target
                invalid_rel = f"docs/reviews/260618_15061{len(label)}_risk_packet_range_{base[:7]}_{head[:7]}.md"
                self._write(root, invalid_rel, MODULE.render_packet_markdown(invalid_payload))
                readback = MODULE.read_risk_packet(
                    root,
                    range_ref=f"{base}..{head}",
                    risk_packet_path=Path(invalid_rel),
                )
                self.assertEqual(readback.state, "invalid")
                self.assertEqual([error.code for error in readback.errors], ["risk_packet_target_mismatch"])

    def test_red_review_missing_s1_section_still_reports_live_blocker(self) -> None:
        review_rel = "docs/code_reviews/missing_s1.md"
        review_text = dedent(
            """\
            # Review

            **Status:** ❌ S1 blocker(ы)

            ## Lane synthesis / aggregate verdict

            - Aggregate status: `❌ S1 blocker(ы)`
            """
        )

        blockers = MODULE.parse_live_blockers(review_text, review_rel)

        self.assertEqual(
            blockers,
            [{"id": "B1", "state": "live_missing_details", "truth_host": f"{review_rel}#S1-Blocker"}],
        )

    def test_missing_truth_host_fails_closed_without_writing_packet(self) -> None:
        for missing_kind in ("ready_to_push_closeout", "post_merge_audit"):
            with self.subTest(missing_kind=missing_kind), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                base, head = self._init_repo(root)
                review_rel = self._write_review(root)
                hosts = self._write_truth_hosts(root, base, head)
                missing_rel = f"docs/reviews/missing_{missing_kind}_range_{base[:7]}_{head[:7]}.md"
                out_rel = f"docs/reviews/blocked_{missing_kind}.md"
                audit_path = missing_rel if missing_kind == "post_merge_audit" else hosts["post_merge_audit"]
                closeout_path = missing_rel if missing_kind == "ready_to_push_closeout" else hosts["ready_to_push_closeout"]

                rc, stdout = self._run_main(
                    [
                        "--repo-root",
                        str(root),
                        "--range",
                        f"{base}..{head}",
                        "--review-artifact",
                        review_rel,
                        "--post-merge-audit",
                        audit_path,
                        "--operational-receipt",
                        hosts["operational_receipt"],
                        "--ready-to-push-closeout",
                        closeout_path,
                        "--packetization-report",
                        hosts["packetization_report"],
                        "--out",
                        out_rel,
                        "--json",
                    ]
                )

                self.assertEqual(rc, 2)
                payload = json.loads(stdout)["range_review_risk_packet"]
                self.assertEqual(payload["status"], "blocked")
                self.assertTrue(any(error["code"] == "missing_truth_host" for error in payload["errors"]))
                self.assertFalse((root / out_rel).exists())

    def test_duplicate_active_same_range_packet_fails_closed_without_explicit_out(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            base, head = self._init_repo(root)
            review_rel = self._write_review(root)
            hosts = self._write_truth_hosts(root, base, head)
            existing = f"docs/reviews/260618_150000_risk_packet_range_{base[:7]}_{head[:7]}.md"
            self._write(root, existing, "# Range review risk packet\n\n**Status:** ✅ Done\n")

            rc, stdout = self._run_main(
                [
                    "--repo-root",
                    str(root),
                    "--range",
                    f"{base}..{head}",
                    "--review-artifact",
                    review_rel,
                    "--post-merge-audit",
                    hosts["post_merge_audit"],
                    "--operational-receipt",
                    hosts["operational_receipt"],
                    "--ready-to-push-closeout",
                    hosts["ready_to_push_closeout"],
                    "--packetization-report",
                    hosts["packetization_report"],
                    "--json",
                ]
            )

            self.assertEqual(rc, 2)
            payload = json.loads(stdout)["range_review_risk_packet"]
            self.assertIn("ambiguous active same-range risk packets", payload["errors"][0]["detail"])

    def test_shared_readback_classifies_invalid_packet_states(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            base, head = self._init_repo(root)
            review_rel = self._write_review(root)
            hosts = self._write_truth_hosts(root, base, head)
            payload, errors = MODULE.build_packet_payload(
                repo_root=root,
                range_ref=f"{base}..{head}",
                out_path=root / "docs/reviews/packet.md",
                host_paths={
                    "review_artifact": root / review_rel,
                    **{key: root / value for key, value in hosts.items()},
                },
                changed_files=MODULE.changed_files_for_range(root, f"{base}..{head}"),
            )
            self.assertEqual(errors, [])
            assert payload is not None

            valid_rel = f"docs/reviews/260618_150600_risk_packet_range_{base[:7]}_{head[:7]}.md"
            self._write(root, valid_rel, MODULE.render_packet_markdown(payload))
            readback = MODULE.read_risk_packet(root, range_ref=f"{base}..{head}", risk_packet_path=Path(valid_rel))
            self.assertTrue(readback.ok)

            superseded_rel = f"docs/reviews/260618_150601_risk_packet_range_{base[:7]}_{head[:7]}.md"
            self._write(
                root,
                superseded_rel,
                MODULE.render_packet_markdown(payload).replace("**Status:** ✅ Done", "**Status:** Superseded"),
            )
            readback = MODULE.read_risk_packet(root, range_ref=f"{base}..{head}", risk_packet_path=Path(superseded_rel))
            self.assertEqual(readback.state, "superseded")

            malformed_rel = f"docs/reviews/260618_150602_risk_packet_range_{base[:7]}_{head[:7]}.md"
            self._write(root, malformed_rel, "**Status:** ✅ Done\n\n```json\n{not-json}\n```\n")
            readback = MODULE.read_risk_packet(root, range_ref=f"{base}..{head}", risk_packet_path=Path(malformed_rel))
            self.assertEqual(readback.state, "unparseable")

            mismatch_payload = dict(payload)
            mismatch_payload["head"] = "c" * 40
            mismatch_rel = f"docs/reviews/260618_150603_risk_packet_range_{base[:7]}_{head[:7]}.md"
            self._write(root, mismatch_rel, MODULE.render_packet_markdown(mismatch_payload))
            readback = MODULE.read_risk_packet(root, range_ref=f"{base}..{head}", risk_packet_path=Path(mismatch_rel))
            self.assertEqual(readback.state, "range_mismatched")


if __name__ == "__main__":
    unittest.main()

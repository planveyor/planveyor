#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import io
import json
import os
import re
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

from test_support.process_contract_fixtures import run_zsh_fixture, write_text_fixture


MODULE_PATH = Path(__file__).with_name("merge_bundle_report.py")
PACKETIZATION_GATE_PATH = Path(__file__).with_name("post_merge_packetization_gate.py")
OPERATIONAL_RECEIPT_HELPER_PATH = Path(__file__).with_name("post_merge_operational_receipt.py")
REPO_ROOT = MODULE_PATH.parent.parent
SPEC = importlib.util.spec_from_file_location("merge_bundle_report", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

import post_merge_operational_receipt as OPERATIONAL_RECEIPT
import post_merge_receipt_skeleton as RECEIPT_SKELETON
import post_merge_ready_to_push_closeout as READY_TO_PUSH_CLOSEOUT


BASE = "a" * 40
HEAD = "b" * 40
B7 = BASE[:7]
H7 = HEAD[:7]
SHA256 = "b1df5fca0ca714f91180f4da82fa8392891c95dff8a49ec0ff3140cebd4c6f11"
DB_SHA256 = "c" * 64


class MergeBundleReportTests(unittest.TestCase):
    def test_receipt_schema_constants_reuse_writer_authorities(self) -> None:
        self.assertEqual(MODULE.OPERATIONAL_RECEIPT_SCHEMA_VERSION, OPERATIONAL_RECEIPT.SCHEMA_VERSION)
        self.assertEqual(RECEIPT_SKELETON.OPERATIONAL_SCHEMA_VERSION, OPERATIONAL_RECEIPT.SCHEMA_VERSION)
        self.assertEqual(
            READY_TO_PUSH_CLOSEOUT.CLOSEOUT_RECEIPT_SCHEMA_VERSION,
            MODULE.READY_TO_PUSH_CLOSEOUT_SCHEMA_VERSION,
        )
        self.assertEqual(MODULE.OPERATIONAL_RECEIPT_SCHEMA_VERSION, "post_merge_operational_receipt.v1")
        self.assertEqual(MODULE.READY_TO_PUSH_CLOSEOUT_SCHEMA_VERSION, "ready_to_push_closeout_receipt.v1")

    def test_post_merge_audit_authority_blocks_report_and_green_readback_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist="- [x] step:post_merge_audit\n- [ ] step:ready_to_push",
            )
            audit_rel = f"docs/reviews/260505_1200_post_merge_audit_range_{B7}_{H7}.md"
            self._write(root, audit_rel, "# Post-merge audit\n\n**Status:** ✅ Done\n")
            self._commit_all(root, "fixture")
            finding = MODULE.post_merge_audit_lint.Finding(
                rel_path=audit_rel,
                line_no=3,
                code="audit_status_done_conflicts_with_visual_evidence",
                message="runtime UI visual evidence is red",
            )
            with mock.patch.object(
                MODULE.post_merge_audit_lint,
                "_lint_current_audit_status_authority",
                return_value=[finding],
            ):
                blocked = MODULE.build_report(root)
            with mock.patch.object(
                MODULE.post_merge_audit_lint,
                "_lint_current_audit_status_authority",
                return_value=[],
            ):
                green = MODULE.build_report(root)

        self.assertEqual(blocked["post_merge_audit_authority"]["state"], "blocked")
        self.assertIn("post_merge_audit_authority_blocked", {error["code"] for error in blocked["errors"]})
        self.assertEqual(green["post_merge_audit_authority"]["state"], "green")
        self.assertNotIn("post_merge_audit_authority_blocked", {error["code"] for error in green["errors"]})

    def test_docs_finalize_strict_preflight_rejects_present_but_non_primary_carriers(self) -> None:
        strict_range = f"{BASE}..{HEAD}"
        good_path = f"docs/reviews/260829_1808_docs_finalize_receipt_range_{B7}_{H7}.md"
        no_followups_path = f"docs/reviews/260829_1809_docs_finalize_receipt_range_{B7}_{H7}.md"
        wrong_readback_path = f"docs/reviews/260829_1810_docs_finalize_receipt_range_{B7}_{H7}.md"
        legacy_followups_path = "docs/reviews/ordinary_docs_finalize_followups.md"
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write(
                root,
                good_path,
                self._docs_finalize_receipt(
                    rel_path=good_path,
                    process_body="NO PROCESS IMPROVEMENTS — why: clean_run",
                ),
            )
            self._write(
                root,
                no_followups_path,
                self._docs_finalize_receipt(rel_path=no_followups_path, process_body="NO FOLLOWUPS"),
            )
            self._write(
                root,
                wrong_readback_path,
                self._docs_finalize_receipt(
                    rel_path=good_path,
                    process_body="NO PROCESS IMPROVEMENTS — why: clean_run",
                ),
            )
            self._write(root, legacy_followups_path, "NO FOLLOWUPS\n")

            green = MODULE.validate_post_merge_receipt_preflight(
                root=root,
                step="docs_finalize",
                path=good_path,
                role="Architect",
                docs_finalize_range=strict_range,
            )
            no_followups = MODULE.validate_post_merge_receipt_preflight(
                root=root,
                step="docs_finalize",
                path=no_followups_path,
                role="Architect",
                docs_finalize_range=strict_range,
            )
            wrong_readback = MODULE.validate_post_merge_receipt_preflight(
                root=root,
                step="docs_finalize",
                path=wrong_readback_path,
                role="Architect",
                docs_finalize_range=strict_range,
            )
            legacy_followups = MODULE.validate_post_merge_receipt_preflight(
                root=root,
                step="docs_finalize",
                path=legacy_followups_path,
            )

        self.assertEqual(green["status"], "ok")
        self.assertEqual(legacy_followups["status"], "ok")
        self.assertEqual(no_followups["status"], "blocked")
        self.assertIn("disallowed_docs_finalize_carrier", {error["code"] for error in no_followups["errors"]})
        self.assertEqual(wrong_readback["status"], "blocked")
        self.assertIn(
            "docs_finalize_receipt_readback_mismatch",
            {error["code"] for error in wrong_readback["errors"]},
        )

    def _init_repo(self, root: Path) -> None:
        subprocess.run(["git", "-C", str(root), "init"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(root), "config", "user.email", 'test' + '@' + 'example' + '.' + 'com'], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.name", "Test User"], check=True)

    def _write(self, root: Path, rel_path: str, body: str) -> Path:
        return write_text_fixture(root, rel_path, body)

    def _docs_finalize_receipt(
        self,
        *,
        rel_path: str,
        process_body: str,
        base: str = BASE,
        head: str = HEAD,
    ) -> str:
        return dedent(
            f"""\
            # Docs finalize receipt

            **Role:** Architect
            **BASE:** {base}
            **HEAD:** {head}
            **Status:** Done
            **Schema version:** review.v1

            docs_finalize_receipt_path={rel_path}

            ## Process improvements

            {process_body}
            """
        )

    def _write_range_and_tracker(self, root: Path, *, merge_notes_checked: bool = True) -> None:
        self._write(root, ".planveyor.range.base", f"# test\n{BASE}\n")
        self._write(root, ".planveyor.range.head", f"# test\n{HEAD}\n")
        merge_mark = "x" if merge_notes_checked else " "
        self._write(
            root,
            ".planveyor.merge_tracker.md",
            dedent(
                f"""\
                # Merge tracker

                BASE={BASE}
                HEAD={HEAD}
                RANGE={BASE}..{HEAD}
                RANGE_ID=range_{B7}_{H7}

                ## Checklist
                - [x] step:review_range
                - [{merge_mark}] step:merge_notes
                - [ ] step:ready_to_push
                """
            ),
        )

    def _commit_all(self, root: Path, message: str) -> str:
        subprocess.run(["git", "-C", str(root), "add", "."], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(root), "commit", "-m", message], check=True, capture_output=True)
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            text=True,
            check=True,
            capture_output=True,
        )
        return result.stdout.strip()

    def _commit_all_at(self, root: Path, message: str, timestamp: str) -> str:
        env = {
            **os.environ,
            "GIT_AUTHOR_DATE": timestamp,
            "GIT_COMMITTER_DATE": timestamp,
        }
        subprocess.run(["git", "-C", str(root), "add", "."], check=True, capture_output=True, env=env)
        subprocess.run(
            ["git", "-C", str(root), "commit", "-m", message],
            check=True,
            capture_output=True,
            env=env,
        )
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            text=True,
            check=True,
            capture_output=True,
        )
        return result.stdout.strip()

    def _write_custom_range_and_tracker(
        self,
        root: Path,
        *,
        base: str,
        head: str,
        checklist: str,
        write_docs_finalize_receipt: bool = True,
    ) -> None:
        self._write(root, ".planveyor.range.base", f"{base}\n")
        self._write(root, ".planveyor.range.head", f"{head}\n")
        self._write(
            root,
            ".planveyor.merge_tracker.md",
            dedent(
                f"""\
                # Merge tracker

                BASE={base}
                HEAD={head}
                RANGE={base}..{head}
                RANGE_ID=range_{base[:7]}_{head[:7]}

                ## Checklist
                {checklist}
                """
            ),
        )
        if write_docs_finalize_receipt and re.search(
            r"(?m)^\s*-\s*\[[xX]\]\s+step:docs_finalize(?:\s|$)", checklist
        ):
            receipt_path = (
                "docs/reviews/260829_1808_docs_finalize_receipt_range_"
                f"{base[:7]}_{head[:7]}.md"
            )
            self._write(
                root,
                receipt_path,
                self._docs_finalize_receipt(
                    rel_path=receipt_path,
                    process_body="NO PROCESS IMPROVEMENTS — why: clean_run",
                    base=base,
                    head=head,
                ),
            )

    def _current_packet_text(
        self,
        *,
        packet_id: str,
        target_repo: str,
        source_plan: str,
        target_carrier: str,
        target_carriers: list[str] | None = None,
        target_kind: str = "plan_adoption",
    ) -> str:
        carriers = target_carriers or [target_carrier]
        payload = {
            "packet_meta": {
                "id": packet_id,
                "source_repo": "current-consumer",
                "source_plan": source_plan,
                "target_repo": target_repo,
                "target_kind": target_kind,
                "status": "open",
                "depends_on_packets": [],
                "queue_after_import": True,
                "suggested_target_plan_slug": packet_id,
                "target_import_receipt": None,
                "target_local_plan": None,
                "source_artifacts": ["docs/stale.md"],
                "target_writable_carriers": carriers,
            }
        }
        return (
            f"# Rollout packet: {packet_id}\n\n"
            "**Date:** 2026-05-11 10:00\n"
            "**Source repo:** current-consumer\n"
            f"**Target repo:** {target_repo}\n"
            f"**Target kind:** {target_kind}\n"
            "**Status:** open\n\n"
            "**Context links (source of truth):**\n"
            f"- Source plan: `{source_plan}`\n"
            "- Target import receipt: `N/A (why=not imported yet)`\n"
            "- Target local plan: `N/A (why=not imported yet)`\n\n"
            "## Meta (machine-readable JSON)\n"
            "```json\n"
            f"{json.dumps(payload, indent=2)}\n"
            "```\n\n"
            "## Source provenance\n"
            "- Source-local fixture.\n\n"
            "## Why target repo action exists\n"
            "- Structural source-side handoff only.\n\n"
            "## Source artifacts\n"
            "- `docs/stale.md`\n\n"
            "## Target writable carriers\n"
            + "".join(f"- `{carrier}`\n" for carrier in carriers)
            + "\n"
            "## Import recipe\n"
            "- Target owns import/adoption.\n\n"
            "## Stop conditions / not-in-scope\n"
            "- No sibling reads/writes.\n\n"
            "## Adoption completion signal\n"
            "- Target-local outcome only.\n\n"
            "## Source-side acknowledgement\n"
            "- `N/A (why=packet is open)`\n"
        )

    def _pi_backlog_entries_text(self, entries: list[dict[str, str]]) -> str:
        rendered_entries = []
        for entry in entries:
            rendered_entries.append(
                dedent(
                    f"""\
                    ### {entry['entry_id']}
                    - status: `{entry['status']}`
                    - priority: `{entry['priority']}`
                    - role: `Coder`
                    - owner: `Architect`
                    - promotion_class: `helper_change`
                    - target_canon_path: `{entry['target_canon_path']}`
                    - target_repo_scope: `{entry['target_repo_scope']}`
                    - delivery_mode: `{entry['delivery_mode']}`
                    - execution_kind: `{entry['execution_kind']}`
                    - execution_ref: `{entry['execution_ref']}`
                    - delivery_refs: `{entry['delivery_refs']}`
                    - handled_ref: `null`
                    - promoted_at: `null`
                    - handled_at: `null`
                    - trigger_ref: `docs/code_reviews/current.md#B1`
                    - source_ref: `docs/plans/pi_source.md`
                    - symptom: `range PI applicability needs exact evidence`
                    - process_gap: `packetization must not infer target intent`
                    - suggested_fix: `derive the target partition from the snapshot delta`
                    - created_at: `2026-05-11 10:00 MSK`
                    - triage_note: `{entry['triage_note']}`
                    """
                )
            )
        return dedent(
            """\
            # Process improvements backlog - merge-bundle fixture

            **Date:** 2026-05-11 10:00 MSK
            **Source ref:** `docs/plans/pi_source.md`
            **Status:** Draft

            ## Suggestions (truth)
            """
        ) + "\n".join(rendered_entries)

    def _write_public_current_delivery_backlog(self, root: Path, path: str) -> None:
        self._write(
            root,
            path,
            self._pi_backlog_entries_text(
                [
                    {
                        "entry_id": "PI-001",
                        "status": "triaged",
                        "priority": "P1",
                        "target_canon_path": "docs/tools/prompts/manager_collab_merge_pipeline.md",
                        "target_repo_scope": "consumer-fixture",
                        "delivery_mode": "source_plus_rollout",
                        "execution_kind": "plan",
                        "execution_ref": "docs/plans/consumer_packet_provenance.md",
                        "delivery_refs": "docs/rollout_packets/consumer_packet.md",
                        "triage_note": "first literal consumer delivery",
                    },
                    {
                        "entry_id": "PI-002",
                        "status": "triaged",
                        "priority": "P1",
                        "target_canon_path": "docs/tools/prompts/owner_merge_pipeline.md",
                        "target_repo_scope": "partner-fixture",
                        "delivery_mode": "source_plus_rollout",
                        "execution_kind": "plan",
                        "execution_ref": "docs/plans/partner_packet_provenance.md",
                        "delivery_refs": "docs/rollout_packets/partner_packet.md",
                        "triage_note": "second literal partner delivery",
                    },
                ]
            ),
        )

    def _init_current_packetization_fixture(self, root: Path) -> tuple[str, str, str, str, dict[str, object]]:
        self._init_repo(root)
        self._write(root, "README.md", "seed\n")
        base = self._commit_all(root, "seed")
        source_plan = "docs/plans/260511_1000_process_packetization.md"
        unrelated_done_plan = "docs/plans/260511_1001_process_unrelated.md"
        changed_file = "docs/process_improvements/current_delivery__process_improvements_backlog.md"
        self._write(root, source_plan, "# Packetization\n\n**Status:** Done\n")
        self._write(root, unrelated_done_plan, "# Unrelated\n\n**Status:** Done\n")
        self._write_public_current_delivery_backlog(root, changed_file)
        head = self._commit_all(root, "public PI packetization change")
        self._current_packetization_changed_files = [changed_file]
        self._write(
            root,
            "docs/rollout_packets/consumer_packet.md",
            self._current_packet_text(
                packet_id="260511_1000_consumer_packet",
                target_repo="consumer-fixture",
                source_plan="docs/plans/consumer_packet_provenance.md",
                target_carrier="docs/tools/prompts/manager_collab_merge_pipeline.md",
            ),
        )
        self._write(
            root,
            "docs/rollout_packets/partner_packet.md",
            self._current_packet_text(
                packet_id="260511_1000_partner_packet",
                target_repo="partner-fixture",
                source_plan="docs/plans/partner_packet_provenance.md",
                target_carrier="docs/tools/prompts/owner_merge_pipeline.md",
            ),
        )
        gate = subprocess.run(
            [
                sys.executable,
                str(PACKETIZATION_GATE_PATH),
                "--repo-root",
                str(root),
                "--recover",
                "--range",
                f"{base}..{head}",
                "--packet",
                "docs/rollout_packets/consumer_packet.md",
                "--packet",
                "docs/rollout_packets/partner_packet.md",
                "--stage-packets",
                "--now",
                "2026-05-11T10:00:00",
                "--json",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(gate.returncode, 0, gate.stderr)
        payload = json.loads(gate.stdout)["packetization_gate"]
        self._write_custom_range_and_tracker(
            root,
            base=base,
            head=head,
            checklist="- [x] step:packetization_gate\n- [ ] step:docs_finalize",
        )
        return base, head, source_plan, changed_file, payload

    def _init_same_target_multi_file_packetization_fixture(
        self, root: Path
    ) -> tuple[str, str, str, tuple[str, str], dict[str, object]]:
        self._init_repo(root)
        self._write(root, "README.md", "seed\n")
        base = self._commit_all(root, "seed")
        source_plan = "docs/plans/260511_1000_process_packetization.md"
        changed_files = (
            "docs/process_improvements/partner_one__process_improvements_backlog.md",
            "docs/process_improvements/partner_two__process_improvements_backlog.md",
        )
        target_carriers = (
            "docs/tools/prompts/partner_one.md",
            "docs/tools/prompts/partner_two.md",
        )
        self._write(root, source_plan, "# Packetization\n\n**Status:** Done\n")
        for index, (changed_file, target_carrier) in enumerate(zip(changed_files, target_carriers), start=1):
            self._write(
                root,
                changed_file,
                self._pi_backlog_entries_text(
                    [
                        {
                            "entry_id": "PI-001",
                            "status": "triaged",
                            "priority": "P1",
                            "target_canon_path": target_carrier,
                            "target_repo_scope": "partner-fixture",
                            "delivery_mode": "source_plus_rollout",
                            "execution_kind": "plan",
                            "execution_ref": "docs/plans/partner_packet_provenance.md",
                            "delivery_refs": "docs/rollout_packets/partner_packet.md",
                            "triage_note": f"literal shared partner carrier {index}",
                        }
                    ]
                ),
            )
        head = self._commit_all(root, "same-target public PI changes")
        self._write(
            root,
            "docs/rollout_packets/partner_packet.md",
            self._current_packet_text(
                packet_id="260511_1000_partner_packet",
                target_repo="partner-fixture",
                source_plan="docs/plans/partner_packet_provenance.md",
                target_carrier=target_carriers[0],
                target_carriers=list(target_carriers),
            ),
        )
        gate = subprocess.run(
            [
                sys.executable,
                str(PACKETIZATION_GATE_PATH),
                "--repo-root",
                str(root),
                "--recover",
                "--range",
                f"{base}..{head}",
                "--packet",
                "docs/rollout_packets/partner_packet.md",
                "--stage-packets",
                "--now",
                "2026-05-11T10:00:00",
                "--json",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(gate.returncode, 0, gate.stderr)
        payload = json.loads(gate.stdout)["packetization_gate"]
        self._write_custom_range_and_tracker(
            root,
            base=base,
            head=head,
            checklist="- [x] step:packetization_gate\n- [ ] step:docs_finalize",
        )
        return base, head, source_plan, changed_files, payload

    def _seed_many_shared_canon_changes(self, root: Path, *, count: int = 25) -> tuple[str, str]:
        self._write(root, "README.md", "seed\n")
        base = self._commit_all(root, "seed")
        for i in range(count):
            self._write(root, f"docs/playbooks/large_range_{i:02d}.md", f"# Playbook {i}\n")
        head = self._commit_all(root, "large shared canon")
        return base, head

    def _write_review_range_artifacts(self, root: Path) -> None:
        self._write(
            root,
            f"docs/plans/260505_1200_reviewer_range_{B7}_{H7}.md",
            "# Plan\n\n**Status:** Done\n",
        )
        self._write(
            root,
            f"docs/code_drafts/260505_1200_reviewer_range_{B7}_{H7}__code_draft.md",
            "# Code draft\n\n**Status:** Planner finalized\n",
        )
        self._write(
            root,
            f"docs/code_reviews/260505_1200_reviewer_range_{B7}_{H7}.md",
            "# Review\n\n**Status:** ✅ OK\n",
        )

    def _write_review_range_artifacts_for_range(
        self,
        root: Path,
        *,
        b7: str,
        h7: str,
        timestamp: str,
    ) -> tuple[str, str, str]:
        plan_path = f"docs/plans/{timestamp}_reviewer_range_{b7}_{h7}.md"
        draft_path = f"docs/code_drafts/{timestamp}_reviewer_range_{b7}_{h7}__code_draft.md"
        review_path = f"docs/code_reviews/{timestamp}_reviewer_range_{b7}_{h7}.md"
        self._write(root, plan_path, "# Plan\n\n**Status:** Done\n")
        self._write(root, draft_path, "# Code draft\n\n**Status:** Planner finalized\n")
        self._write(root, review_path, "# Review\n\n**Status:** ✅ OK\n")
        return plan_path, draft_path, review_path

    def _write_docs_hygiene_suggest_gate_fixture(self, root: Path) -> tuple[str, str]:
        self._init_repo(root)
        self._write(root, "README.md", "seed\n")
        base = self._commit_all(root, "seed")
        self._write(
            root,
            "docs/plans/260505_1200_done_plan.md",
            "# Done plan\n\n**Status:** Done\n",
        )
        head = self._commit_all(root, "done plan")
        self._write_custom_range_and_tracker(
            root,
            base=base,
            head=head,
            checklist=dedent(
                """\
                - [x] step:docs_hygiene_archive
                - [ ] step:docs_hygiene_suggest
                - [ ] step:ready_to_push
                """
            ),
        )
        return base, head

    def _run_docs_hygiene_suggest_gate(self, root: Path, *, override: str = "") -> subprocess.CompletedProcess[str]:
        script = dedent(
            f"""\
            source "$1"
            {override}
            cd "$2"
            export PYBIN="$3"
            planveyor_post_merge_docs_hygiene_suggest_gate
            """
        )
        return run_zsh_fixture(
            script,
            cwd=Path.cwd(),
            path=os.environ.get("PATH", os.defpath),
            pybin=sys.executable,
            argv0="zsh",
            argv_tail=(str(REPO_ROOT / "scripts/planveyor.zsh"), str(root), sys.executable),
            capture_output=True,
            check=False,
        )

    def _write_plan_harvest_artifacts(self, root: Path, *, extra_report_body: str = "") -> None:
        self._write(
            root,
            f"docs/reviews/260505_1200_plan_harvest_range_{B7}_{H7}.md",
            dedent(
                f"""\
                # Plan harvest

                **Status:** Done

                ## Follow-ups backlog (created)
                - `docs/followups/260505_1200_followups_range_{B7}_{H7}.md`

                ## Follow-ups (extracted; без дублей)
                - Result: `NO FOLLOWUPS` - no remaining actionable debt after full-wave harvest.
                {extra_report_body}
                """
            ),
        )
        self._write(
            root,
            f"docs/followups/260505_1200_followups_range_{B7}_{H7}.md",
            dedent(
                """\
                # Follow-ups backlog

                **Source:** plan harvest
                **Status:** Done
                **Imported into:** `docs/followups/process_followups_master.md`

                ## Range result
                - `NO FOLLOWUPS` - no remaining actionable debt after full-wave harvest.
                """
            ),
        )

    def _complete_plan_harvest_receipts(self) -> str:
        return dedent(
            """\

            ## Follow-up harvest triage/import receipt
            - `planveyor_followups_triage --file docs/followups/260505_1200_followups_range_aaaaaaa_bbbbbbb.md --apply`: imported=0, duplicate=0, open=0.

            ## Process-improvement promotion decisions
            - `N/A (why=no mature process-improvement rows in range)`.

            ## Docs retrieval metrics receipt
            - Summary copied from metrics: query_total=0, evaluated_total=0, read_log_status=missing, read_events_total=0.

            ## Golden Path lane receipt
            - `lane=tooling_process`; `active carrier=docs/guides/golden_paths.md#post-merge-plan-harvest`; `outcome=no changes needed (why=fixture)`.

            ## ADR candidates / durable decisions
            - `N/A (why=no durable decision candidate in fixture)`.

            ## Canon/follow-up summary
            - canon_updates=0; followups=0.
            """
        )

    def _write_supplemental_audit_followups(
        self,
        root: Path,
        *,
        rel_path: str | None = None,
        source: str | None = "post-merge audit",
        imported_into: str | None = "`docs/followups/process_followups_master.md`",
    ) -> str:
        path = rel_path or f"docs/followups/260505_1201_post_merge_audit_followups_range_{B7}_{H7}.md"
        headers = ["# Follow-ups backlog"]
        if source is not None:
            headers.append(f"**Source:** {source}")
        headers.append("**Status:** ✅ Done")
        if imported_into is not None:
            headers.append(f"**Imported into:** {imported_into}")
        body = "\n\n".join(headers) + "\n\n## Follow-ups (backlog)\n- P2 [ ] fixture row\n"
        self._write(root, path, body)
        return path

    def _operational_step_records(
        self,
        *,
        omit_field: tuple[str, str] | None = None,
        override_field: tuple[str, str, object] | None = None,
        record_overrides: dict[str, dict[str, object]] | None = None,
    ) -> list[dict[str, object]]:
        captured_at = "2026-05-16T00:00:00+00:00"
        followups_source = f"docs/reviews/260505_1200_plan_harvest_range_{B7}_{H7}.md"

        def ran(step: str, command: str, artifact_path: str, count_summary: str, result: str) -> dict[str, object]:
            return {
                "step": step,
                "command": command,
                "exit_code": 0,
                "result": result,
                "artifact_path": artifact_path,
                "count_summary": count_summary,
                "no_op_reason": "N/A (why=ran)",
                "in_scope": "yes",
                "captured_at": captured_at,
                "source": "fixture command output",
            }

        def skipped(step: str, reason: str) -> dict[str, object]:
            return {
                "step": step,
                "command": f"N/A (why={reason})",
                "result": "skipped",
                "artifact_path": f"N/A (why={reason})",
                "count_summary": f"N/A (why={reason})",
                "no_op_reason": reason,
                "in_scope": "no",
                "captured_at": captured_at,
                "source": "fixture no-op reason",
            }

        records = [
            ran("docs_finalize", "planveyor_arch_docs_general", "docs/plans/fixture.md", "docs_changed=0", "ok"),
            ran("doc_lint", "bash ./scripts/run_doc_lint.sh --root docs/tools/prompts/manager_collab_merge_pipeline.md", "N/A (why=stdout only)", "errors=0", "ok"),
            ran("docs_hygiene_archive", f"planveyor_docs_hygiene_archive --range {BASE}..{HEAD} --apply", ".tmp/docs_hygiene_archive.json", "inserted=0 skipped_existing=2 missing_on_disk=0", "ok"),
            ran("docs_hygiene_suggest", f"planveyor_docs_hygiene_suggest --range {BASE}..{HEAD}", ".tmp/docs_hygiene_suggest.md", "candidates=2 report_only=yes", "ok"),
            ran(
                "docs_index_context",
                "planveyor_docs_index_build all; docs_context_check --corpus plans; docs_context_check --corpus followups",
                "N/A (why=stdout summary)",
                (
                    "plans_total=2; plans_covered=2; plans_uncovered=0; plans_state=covered; "
                    "followups_total=1; followups_covered=1; followups_uncovered=0; followups_state=covered; "
                    "canon_state=advisory"
                ),
                "ok",
            ),
            ran(
                "retrieval_metrics",
                "scripts/docs_retrieve_metrics.py --format json",
                "N/A (why=stdout summary)",
                (
                    "query_total=10; evaluated_total=3; outcome_evaluated_rate=0.30; "
                    "read_log_status=present; read_events_total=1; read_open_rate=0.10; "
                    "used_for_decision=true; triage=not_required"
                ),
                "ok",
            ),
            ran(
                "followups_triage_launch",
                (
                    f"planveyor_followups_triage --file docs/followups/260505_1200_followups_range_{B7}_{H7}.md "
                    "--dry-run; "
                    f"planveyor_followups_triage --file docs/followups/260505_1200_followups_range_{B7}_{H7}.md "
                    "--apply; "
                    f"planveyor_followups_triage --file docs/followups/260505_1200_followups_range_{B7}_{H7}.md "
                    "--apply; "
                    "scripts/followups_index_rebuild.py --project-root ."
                ),
                followups_source,
                (
                    f"source_harvest_receipt_path={followups_source}; triage_mode=file; "
                    "dry_run_append_new=2; dry_run_merge_source=0; dry_run_possible_duplicate=0; dry_run_route_fallback=0; "
                    "apply_append_new=2; apply_merge_source=0; apply_possible_duplicate=0; apply_route_fallback=0; "
                    "idempotency_append_new=0; idempotency_merge_source=2; idempotency_possible_duplicate=0; "
                    "idempotency_route_fallback=0; index_rebuild_status=ok; readback_status=ok; "
                    "index_path=docs/followups/index.md; process_improvements_lane=separate; "
                    f"process_improvements_ref={followups_source}#process-improvement-promotion-decisions"
                ),
                "ok",
            ),
            skipped("canon_sweep", "canon sweep not completed in fixture"),
            ran("planveyor_merge_bundle_report", "planveyor_merge_bundle_report", "N/A (why=read-only stdout)", "status=ok errors=0", "status=ok"),
        ]
        if record_overrides:
            for record in records:
                step_overrides = record_overrides.get(str(record["step"]))
                if step_overrides:
                    record.update(step_overrides)
        if omit_field:
            step, field = omit_field
            for record in records:
                if record["step"] == step:
                    record.pop(field, None)
                    break
        if override_field:
            step, field, value = override_field
            for record in records:
                if record["step"] == step:
                    record[field] = value
                    break
        return records

    def _operational_receipt_payload(
        self,
        *,
        base: str = BASE,
        head: str = HEAD,
        omit_field: tuple[str, str] | None = None,
        override_field: tuple[str, str, object] | None = None,
        record_overrides: dict[str, dict[str, object]] | None = None,
        archive_snapshot: dict[str, object] | None = None,
        omit_docs_hygiene_suggest_summary: bool = False,
        omit_followups_triage_launch_receipt: bool = False,
        omit_followups_lane_reconciliation: bool = False,
        omit_process_improvements_open_summary: bool = False,
        docs_hygiene_suggest_summary_overrides: dict[str, object] | None = None,
        followups_triage_launch_receipt_overrides: dict[str, object] | None = None,
        followups_lane_reconciliation_overrides: dict[str, object] | None = None,
        process_improvements_open_summary_overrides: dict[str, object] | None = None,
        generated_at: str = "2026-05-16T00:00:00+00:00",
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": "post_merge_operational_receipt.v1",
            "range": f"{base}..{head}",
            "base": base,
            "head": head,
            "tracker_path": ".planveyor.merge_tracker.md",
            "generated_at": generated_at,
            "generated_by": "scripts/post_merge_operational_receipt.py",
            "receipt_path": f"docs/reviews/260505_1200_post_merge_operational_receipt_range_{base[:7]}_{head[:7]}.md",
            "archive_snapshot": archive_snapshot if archive_snapshot is not None else self._archive_snapshot_receipt(),
            "docs_hygiene_suggest_summary": self._docs_hygiene_suggest_summary(base=base, head=head),
            "followups_triage_launch_receipt": self._followups_triage_launch_receipt(base=base, head=head),
            "steps": self._operational_step_records(
                omit_field=omit_field,
                override_field=override_field,
                record_overrides=record_overrides,
            ),
        }
        if omit_docs_hygiene_suggest_summary:
            payload.pop("docs_hygiene_suggest_summary", None)
        elif docs_hygiene_suggest_summary_overrides:
            summary = payload.get("docs_hygiene_suggest_summary")
            if isinstance(summary, dict):
                summary.update(docs_hygiene_suggest_summary_overrides)
        if omit_followups_triage_launch_receipt:
            payload.pop("followups_triage_launch_receipt", None)
        elif followups_triage_launch_receipt_overrides:
            receipt = payload.get("followups_triage_launch_receipt")
            if isinstance(receipt, dict):
                receipt.update(followups_triage_launch_receipt_overrides)
        if not omit_followups_lane_reconciliation:
            launch = payload.get("followups_triage_launch_receipt")
            if isinstance(launch, dict):
                payload["followups_lane_reconciliation"] = self._followups_lane_reconciliation(
                    launch,
                    base=base,
                    head=head,
                )
                if followups_lane_reconciliation_overrides:
                    reconciliation = payload.get("followups_lane_reconciliation")
                    if isinstance(reconciliation, dict):
                        reconciliation.update(followups_lane_reconciliation_overrides)
        if omit_process_improvements_open_summary:
            payload.pop("process_improvements_open_summary", None)
        else:
            payload["process_improvements_open_summary"] = self._process_improvements_open_summary(
                base=base,
                head=head,
            )
            if process_improvements_open_summary_overrides:
                summary = payload.get("process_improvements_open_summary")
                if isinstance(summary, dict):
                    summary.update(process_improvements_open_summary_overrides)
        return payload

    def _docs_hygiene_suggest_summary(self, *, base: str = BASE, head: str = HEAD) -> dict[str, object]:
        return {
            "range": f"{base}..{head}",
            "command": f"planveyor_docs_hygiene_suggest --range {base}..{head}",
            "gate_command": f"planveyor_docs_hygiene_suggest --range {base}..{head}",
            "suggest_result": "ok",
            "source_stdout_path": ".tmp/docs_hygiene_suggest.md",
            "source_stderr_path": "N/A (why=stderr artifact path unavailable from stdout path)",
            "report_only": True,
            "deletion_executed": False,
            "ready_to_push_ticked_by_suggest_gate": False,
            "archive_required_command": f"python3 scripts/docs_hygiene_archive.py --range {base}..{head} --apply",
            "suggested_owner_rerun_command": f"planveyor_docs_hygiene_suggest --range {base}..{head}",
            "candidate_counts": {
                "terminal_plans": 1,
                "safe_review_code_drafts": 1,
                "blocked_review_code_drafts": 0,
                "blocked_missing_review_code_drafts": 0,
                "done_followups": 0,
                "blocked_followups": 0,
                "canon_blocked_items": 0,
                "suggested_git_rm_paths": 2,
                "suggested_asset_dirs": 0,
                "suggested_owner_command_items": 2,
            },
            "top_candidates": [
                {
                    "path": "docs/plans/260505_1200_done_plan.md",
                    "class": "terminal_plan",
                    "reason": "included in Suggested (Owner) command",
                },
                {
                    "path": "docs/code_reviews/260505_1200_review.md",
                    "class": "safe_review_or_code_draft",
                    "reason": "included in Suggested (Owner) command",
                },
            ],
            "omitted_count": 0,
        }

    def _archive_snapshot_receipt(self, **overrides: object) -> dict[str, object]:
        receipt: dict[str, object] = {
            "status": "ok",
            "storage_backend": "git_text_export",
            "manifest_path": "docs/_meta/archive_snapshots/current/manifest.json",
            "artifact_path": "docs/_meta/archive_snapshots/current/archived_docs.jsonl",
            "object_uri": "N/A (why=git-backed artifact)",
            "checksum": SHA256,
            "format_version": "1",
            "access_status": "not_required",
            "restore_status": "ok",
            "readback_status": "ok",
            "no_op_reason": "N/A (why=ran)",
            "blocker_reason": "N/A (why=none)",
            "source": (
                "planveyor_docs_archive_snapshot_export + planveyor_docs_archive_snapshot_validate + "
                "planveyor_docs_archive_snapshot_restore"
            ),
            "export_command": (
                "planveyor_docs_archive_snapshot_export --backend git_text_export "
                "--output-dir docs/_meta/archive_snapshots/current --force"
            ),
            "export_status": "ok",
            "snapshot_created_at_utc": "2026-05-16T00:00:01+00:00",
            "snapshot_source_db_sha256": DB_SHA256,
            "snapshot_source_docs_count": "2",
        }
        receipt.update(overrides)
        return receipt

    def _old_schema_archive_snapshot_receipt(self, **overrides: object) -> dict[str, object]:
        receipt = self._archive_snapshot_receipt(**overrides)
        for field in (
            "export_command",
            "export_status",
            "snapshot_created_at_utc",
            "snapshot_source_db_sha256",
            "snapshot_source_docs_count",
        ):
            receipt.pop(field, None)
        return receipt

    def _followups_triage_launch_receipt(self, *, base: str = BASE, head: str = HEAD) -> dict[str, object]:
        source_path = f"docs/reviews/260505_1200_plan_harvest_range_{base[:7]}_{head[:7]}.md"
        return {
            "source_harvest_receipt_path": source_path,
            "triage_mode": "file",
            "command": (
                f"planveyor_followups_triage --file docs/followups/260505_1200_followups_range_{base[:7]}_{head[:7]}.md "
                "--dry-run; "
                f"planveyor_followups_triage --file docs/followups/260505_1200_followups_range_{base[:7]}_{head[:7]}.md "
                "--apply; "
                f"planveyor_followups_triage --file docs/followups/260505_1200_followups_range_{base[:7]}_{head[:7]}.md "
                "--apply; "
                "scripts/followups_index_rebuild.py --project-root ."
            ),
            "dry_run": {"append_new": 2, "merge_source": 0, "possible_duplicate": 0, "route_fallback": 0},
            "apply": {"append_new": 2, "merge_source": 0, "possible_duplicate": 0, "route_fallback": 0},
            "idempotency_apply": {"append_new": 0, "merge_source": 2, "possible_duplicate": 0, "route_fallback": 0},
            "index_rebuild": {
                "command": "scripts/followups_index_rebuild.py --project-root .",
                "index_path": "docs/followups/index.md",
                "status": "ok",
                "readback_status": "ok",
            },
            "process_improvements_lane": {
                "status": "separate",
                "decision_receipt_path": f"{source_path}#process-improvement-promotion-decisions",
            },
        }

    def _followups_lane_reconciliation(
        self,
        launch: dict[str, object],
        *,
        base: str = BASE,
        head: str = HEAD,
    ) -> dict[str, object]:
        apply_counts = launch.get("apply")
        if not isinstance(apply_counts, dict):
            apply_counts = {}
        idempotency_counts = launch.get("idempotency_apply")
        if not isinstance(idempotency_counts, dict):
            idempotency_counts = {}
        triage_mode = str(launch.get("triage_mode", "file"))
        return {
            "source_harvest_receipt_path": launch.get(
                "source_harvest_receipt_path",
                f"docs/reviews/260505_1200_plan_harvest_range_{base[:7]}_{head[:7]}.md",
            ),
            "harvest_file_followups_result": "NO FOLLOWUPS",
            "harvest_file_followups_count": 0,
            "range_triage_mode": triage_mode,
            "range_append_new": apply_counts.get("append_new", 0),
            "range_merge_source": apply_counts.get("merge_source", 0),
            "range_possible_duplicate": apply_counts.get("possible_duplicate", 0),
            "range_route_fallback": apply_counts.get("route_fallback", 0),
            "range_unparsed_bullets": apply_counts.get("unparsed_bullets", 0),
            "range_unresolved_append_new": idempotency_counts.get("append_new", 0),
            "range_unresolved_possible_duplicate": idempotency_counts.get("possible_duplicate", 0),
            "range_unresolved_route_fallback": idempotency_counts.get("route_fallback", 0),
            "range_unresolved_unparsed_bullets": idempotency_counts.get("unparsed_bullets", 0),
            "manual_decision_ref": launch.get("manual_decision_ref", ""),
            "already_tracked_ref": launch.get("already_tracked_ref", ""),
            "source_range_command": launch.get("command", ""),
            "owner_summary": (
                "file-lane=NO FOLLOWUPS (0); range-lane apply "
                f"append_new={apply_counts.get('append_new', 0)}, "
                f"possible_duplicate={apply_counts.get('possible_duplicate', 0)}, "
                f"route_fallback={apply_counts.get('route_fallback', 0)}, "
                f"unparsed_bullets={apply_counts.get('unparsed_bullets', 0)}; "
                f"triage_mode={triage_mode}"
            ),
        }

    def _process_improvements_open_summary(self, *, base: str = BASE, head: str = HEAD) -> dict[str, object]:
        source_path = f"docs/reviews/260505_1200_plan_harvest_range_{base[:7]}_{head[:7]}.md"
        return {
            "source_harvest_receipt_path": source_path,
            "decision_receipt_path": f"{source_path}#process-improvement-promotion-decisions",
            "ordinary_followups_result": "NO FOLLOWUPS",
            "lane_status": "separate",
            "counts_by_raw_status": {
                "open": 2,
                "triaged": 0,
                "promoted": 0,
            },
            "null_execution_rows": 2,
            "owner_or_next_step": "Planner triage in process-improvement promotion lane",
        }

    def _write_followups_harvest_source(
        self,
        root: Path,
        *,
        base: str = BASE,
        head: str = HEAD,
        process_improvements_owner_or_next_step: str = "Planner triage in process-improvement promotion lane",
    ) -> None:
        self._write(
            root,
            f"docs/reviews/260505_1200_plan_harvest_range_{base[:7]}_{head[:7]}.md",
            dedent(
                f"""\
                # Plan harvest

                **Status:** ✅ Done

                ## Follow-ups (extracted; без дублей)
                - Result: `NO FOLLOWUPS` - no remaining actionable debt in the harvest file-lane.

                ## Follow-up harvest triage/import receipt
                | command | mode | append_new | merge_source | possible_duplicate | route_fallback | result |
                | --- | --- | ---: | ---: | ---: | ---: | --- |
                | `planveyor_followups_triage --file docs/followups/260505_1200_followups_range_{base[:7]}_{head[:7]}.md --dry-run` | dry-run | 2 | 0 | 0 | 0 | dry-run only |
                | `planveyor_followups_triage --file docs/followups/260505_1200_followups_range_{base[:7]}_{head[:7]}.md --apply` | apply | 2 | 0 | 0 | 0 | imported |
                | `planveyor_followups_triage --file docs/followups/260505_1200_followups_range_{base[:7]}_{head[:7]}.md --apply` | idempotency apply | 0 | 2 | 0 | 0 | no file changes |
                | `scripts/followups_index_rebuild.py --project-root .` | rebuild | 0 | 0 | 0 | 0 | index updated |

                ## Process-improvement promotion decisions
                - process_improvements_open_summary: source=docs/process_improvements/promotion_surface.md; lane=separate; ordinary_followups=NO FOLLOWUPS; open=2; triaged=0; promoted=0; null_execution=2; owner_or_next_step={process_improvements_owner_or_next_step}
                | source_ref | entry_id | raw_status | execution_kind | execution_ref | owner_or_next_step |
                | --- | --- | --- | --- | --- | --- |
                | `docs/process_improvements/promotion_surface.md` | `PI-001` | `open` | `null` | `null` | `{process_improvements_owner_or_next_step}` |
                | `docs/process_improvements/promotion_surface.md` | `PI-002` | `open` | `null` | `null` | `{process_improvements_owner_or_next_step}` |
                """
            ),
        )

    def _write_operational_receipt_artifact(
        self,
        root: Path,
        *,
        base: str = BASE,
        head: str = HEAD,
        omit_field: tuple[str, str] | None = None,
        override_field: tuple[str, str, object] | None = None,
        record_overrides: dict[str, dict[str, object]] | None = None,
        archive_snapshot: dict[str, object] | None = None,
        omit_archive_snapshot: bool = False,
        omit_docs_hygiene_suggest_summary: bool = False,
        omit_followups_triage_launch_receipt: bool = False,
        omit_followups_lane_reconciliation: bool = False,
        omit_process_improvements_open_summary: bool = False,
        docs_hygiene_suggest_summary_overrides: dict[str, object] | None = None,
        followups_triage_launch_receipt_overrides: dict[str, object] | None = None,
        followups_lane_reconciliation_overrides: dict[str, object] | None = None,
        process_improvements_open_summary_overrides: dict[str, object] | None = None,
        process_improvements_source_owner_or_next_step: str | None = None,
        generated_at: str = "2026-05-16T00:00:00+00:00",
    ) -> None:
        effective_archive_snapshot = None if omit_archive_snapshot else archive_snapshot
        payload = self._operational_receipt_payload(
            base=base,
            head=head,
            omit_field=omit_field,
            override_field=override_field,
            record_overrides=record_overrides,
            archive_snapshot=effective_archive_snapshot,
            omit_docs_hygiene_suggest_summary=omit_docs_hygiene_suggest_summary,
            omit_followups_triage_launch_receipt=omit_followups_triage_launch_receipt,
            omit_followups_lane_reconciliation=omit_followups_lane_reconciliation,
            omit_process_improvements_open_summary=omit_process_improvements_open_summary,
            docs_hygiene_suggest_summary_overrides=docs_hygiene_suggest_summary_overrides,
            followups_triage_launch_receipt_overrides=followups_triage_launch_receipt_overrides,
            followups_lane_reconciliation_overrides=followups_lane_reconciliation_overrides,
            process_improvements_open_summary_overrides=process_improvements_open_summary_overrides,
            generated_at=generated_at,
        )
        if omit_archive_snapshot:
            payload.pop("archive_snapshot", None)
        archive_payload = payload.get("archive_snapshot")
        if isinstance(archive_payload, dict) and archive_payload.get("status") == "ok":
            artifact_rel = str(archive_payload.get("artifact_path") or "")
            manifest_rel = str(archive_payload.get("manifest_path") or "")
            if artifact_rel and not artifact_rel.startswith("N/A"):
                self._write(root, artifact_rel, "artifact fixture\n")
            if manifest_rel and not manifest_rel.startswith("N/A"):
                manifest = {
                    "snapshot_manifest_version": archive_payload.get("format_version"),
                    "storage_backend": archive_payload.get("storage_backend"),
                    "created_at_utc": archive_payload.get("snapshot_created_at_utc"),
                    "artifact": {
                        "path": Path(artifact_rel).name,
                        "sha256": archive_payload.get("checksum"),
                        "record_count": int(str(archive_payload.get("snapshot_source_docs_count") or "0")),
                    },
                    "source_db": {
                        "db_sha256": archive_payload.get("snapshot_source_db_sha256"),
                        "docs_count": int(str(archive_payload.get("snapshot_source_docs_count") or "0")),
                    },
                }
                self._write(root, manifest_rel, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        self._write_followups_harvest_source(
            root,
            base=base,
            head=head,
            process_improvements_owner_or_next_step=(
                process_improvements_source_owner_or_next_step
                or "Planner triage in process-improvement promotion lane"
            ),
        )
        self._write(
            root,
            f"docs/reviews/260505_1200_post_merge_operational_receipt_range_{B7}_{H7}.md",
            dedent(
                f"""\
                # Post-merge operational receipt

                **Status:** ✅ Done

                ## Operational receipt JSON
                ```json
                {json.dumps(payload, indent=2, sort_keys=True)}
                ```
                """
            ),
        )

    def _write_token_only_operational_receipt_artifact(self, root: Path) -> None:
        self._write(
            root,
            f"docs/reviews/260505_1200_post_merge_operational_receipt_range_{B7}_{H7}.md",
            dedent(
                """\
                # Post-merge operational receipt

                **Status:** ✅ Done

                ## Command receipts
                - docs_finalize: completed.
                - doc_lint: completed.
                - docs_hygiene_archive: completed.
                - docs_hygiene_suggest: completed.
                - docs_index_context: N/A.
                - retrieval_metrics: N/A.
                - canon_sweep: N/A.
                - planveyor_merge_bundle_report: completed.
                """
            ),
        )

    def _write_malformed_operational_receipt_artifact(self, root: Path) -> None:
        self._write(
            root,
            f"docs/reviews/260505_1200_post_merge_operational_receipt_range_{B7}_{H7}.md",
            dedent(
                """\
                # Post-merge operational receipt

                **Status:** ✅ Done

                ## Operational receipt JSON
                ```json
                {not-json}
                ```
                """
            ),
        )

    def _write_ready_to_push_closeout_receipt(
        self,
        root: Path,
        *,
        base: str = BASE,
        head: str = HEAD,
        overrides: dict[str, object] | None = None,
        status: str = "✅ Done",
    ) -> str:
        path = f"docs/reviews/260505_1201_ready_to_push_closeout_range_{base[:7]}_{head[:7]}.md"
        payload: dict[str, object] = {
            "schema_version": "ready_to_push_closeout_receipt.v1",
            "range": f"{base}..{head}",
            "base": base,
            "head": head,
            "range_id": f"{base[:7]}..{head[:7]}",
            "tracker_path": ".planveyor.merge_tracker.md",
            "generated_at_utc": "2026-06-07T11:30:00+00:00",
            "generated_by": "scripts/post_merge_ready_to_push_closeout.py",
            "source_command": "planveyor_post_merge_ready_to_push_closeout",
            "terminal_state": "terminal_ready_to_push_proof",
            "final_bundle_status": "ok",
            "required_paths": [
                f"docs/reviews/260505_1200_post_merge_operational_receipt_range_{B7}_{H7}.md"
            ],
            "contextual_paths": [],
            "staged_accepted_paths": [path],
            "staged_paths_at_closeout": [path],
            "unexpected_staged_paths": [],
            "suspicious_paths": [],
            "unstaged_tracked_paths": [],
            "untracked_accepted_paths": [],
            "action": "local_commit_and_tracker_tick",
            "tracker_tick": {
                "intent": "tick step:ready_to_push before committing terminal proof",
                "result": "ticked",
            },
            "pending_owner_gate": "git push",
        }
        if overrides:
            payload.update(overrides)
        self._write(
            root,
            path,
            dedent(
                f"""\
                # Ready-to-push closeout receipt

                **Status:** {status}

                ## Ready-to-push closeout receipt JSON
                ```json
                {json.dumps(payload, indent=2, sort_keys=True)}
                ```
                """
            ),
        )
        return path

    def _range_target(self, *, base: str = BASE, head: str = HEAD) -> str:
        return f"RANGE={base}..{head} (EXCLUDE_DOCS=0)"

    def _write_range_review_risk_packet(
        self,
        root: Path,
        closeout_path: str,
        *,
        target_snapshot: str | None = None,
    ) -> str:
        hosts = {
            "review_artifact": f"docs/code_reviews/260505_1200_reviewer_range_{B7}_{H7}.md",
            "post_merge_audit": f"docs/reviews/260505_1200_post_merge_audit_range_{B7}_{H7}.md",
            "operational_receipt": f"docs/reviews/260505_1200_post_merge_operational_receipt_range_{B7}_{H7}.md",
            "ready_to_push_closeout": closeout_path,
            "packetization_report": f"docs/reviews/260505_1200_packetization_gate_range_{B7}_{H7}.md",
        }
        self._write(root, hosts["review_artifact"], "# Review\n\n**Status:** ✅ OK\n")
        self._write(root, hosts["post_merge_audit"], "# Post-merge audit\n\n**Status:** ✅ Done\n")
        self._write(root, hosts["packetization_report"], "# Packetization\n\n**Status:** ✅ Done\n")
        payload = {
            "schema_version": "range_review_risk_packet.v1",
            "packet_status": "ok",
            "range": f"{BASE}..{HEAD}",
            "range_id": f"{B7}..{H7}",
            "base": BASE,
            "head": HEAD,
            "target_snapshot": target_snapshot or self._range_target(),
            "runtime_touched_paths": [],
            "helper_process_touched_paths": [],
            "visual_status": {"status": "N/A", "reason": "fixture"},
            "live_blockers": [],
            "historical_blockers": [],
            "closure_artifacts": [{"kind": key, "path": value} for key, value in hosts.items() if key != "review_artifact"],
            "residual_risks": [],
            "truth_hosts": {key: {"path": value, "status": "✅ Done"} for key, value in hosts.items()},
        }
        path = f"docs/reviews/260505_1201_risk_packet_range_{B7}_{H7}.md"
        self._write(
            root,
            path,
            "# Range review risk packet\n\n**Status:** ✅ Done\n\n## Risk packet JSON\n```json\n"
            + json.dumps({"risk_packet": payload}, indent=2, sort_keys=True)
            + "\n```\n",
        )
        return path

    def _write_canon_sweep_receipt(
        self,
        root: Path,
        *,
        changed_count: int = 0,
        changed_files: str = "none",
        proof_kind: str = "no_op",
        closure_field: str = "no_op_reason",
        closure_value: str = "no_shared_canon_changes",
        extra_closures: dict[str, str] | None = None,
        target_repo_impact: str = "none",
        packetization_handoff: str = "N/A (why=no shared impact)",
    ) -> str:
        path = f"docs/reviews/260505_1200_canon_sweep_receipt_range_{B7}_{H7}.md"
        closure_lines = {
            "snapshot_path": "N/A (why=not snapshot proof)",
            "report_path": "N/A (why=not report proof)",
            "no_op_reason": "N/A (why=not no-op proof)",
        }
        closure_lines[closure_field] = closure_value
        if extra_closures:
            closure_lines.update(extra_closures)
        self._write(
            root,
            path,
            dedent(
                f"""\
                # Canon sweep receipt

                **Status:** ✅ Done

                ## Canon sweep receipt
                - changed_shared_canon_files_count: {changed_count}
                - changed_shared_canon_files: {changed_files}
                - proof_kind: {proof_kind}
                - snapshot_path: {closure_lines["snapshot_path"]}
                - report_path: {closure_lines["report_path"]}
                - no_op_reason: {closure_lines["no_op_reason"]}
                - target_repo_impact: {target_repo_impact}
                - packetization_handoff: {packetization_handoff}
                """
            ),
        )
        return path

    def test_report_groups_required_and_suspicious_status_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_range_and_tracker(root, merge_notes_checked=False)
            self._write_review_range_artifacts(root)
            self._write(root, "scripts/unrelated.py", "print('x')\n")

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "ok")
        required_paths = {item["path"] for item in payload["git_status"]["required"]}
        self.assertIn(f"docs/plans/260505_1200_reviewer_range_{B7}_{H7}.md", required_paths)
        suspicious_paths = {item["path"] for item in payload["git_status"]["suspicious"]}
        self.assertIn("scripts/unrelated.py", suspicious_paths)
        review_artifact = [
            artifact for artifact in payload["artifacts"] if artifact["kind"] == "review_artifact"
        ][0]
        self.assertEqual(review_artifact["status"], "✅ OK")
        self.assertTrue(review_artifact["required"])

    def test_required_artifact_git_state_reports_staged_and_unstaged(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_range_and_tracker(root, merge_notes_checked=False)
            self._write_review_range_artifacts(root)
            self._commit_all(root, "seed")

            plan_path = f"docs/plans/260505_1200_reviewer_range_{B7}_{H7}.md"
            review_path = f"docs/code_reviews/260505_1200_reviewer_range_{B7}_{H7}.md"
            self._write(root, plan_path, "# Plan\n\n**Status:** Done\n\nunstaged edit\n")
            self._write(root, review_path, "# Review\n\n**Status:** ✅ OK\n\nstaged edit\n")
            subprocess.run(["git", "-C", str(root), "add", review_path], check=True, capture_output=True)

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "ok")
        required_git_state = {
            item["path"]: item["git_state"] for item in payload["git_status"]["required"]
        }
        self.assertEqual(required_git_state[plan_path], "unstaged")
        self.assertEqual(required_git_state[review_path], "staged")

    def test_artifact_lineage_marks_filename_timestamp_divergence_as_derived_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write(root, "README.md", "seed\n")
            base = self._commit_all_at(root, "seed", "2026-06-27T12:00:00+00:00")
            self._write(root, "src/change.txt", "range head\n")
            head = self._commit_all_at(root, "range head", "2026-06-27T12:01:00+00:00")
            b7 = base[:7]
            h7 = head[:7]
            self._write_custom_range_and_tracker(
                root,
                base=base,
                head=head,
                checklist=dedent(
                    """\
                    - [x] step:review_range
                    - [x] step:merge_notes
                    - [ ] step:plan_harvest
                    """
                ),
            )
            merge_notes_path = f"docs/reviews/260627_1221_merge_notes_range_{b7}_{h7}.md"
            self._write(root, merge_notes_path, "# Merge notes\n\n**Status:** Done\n")
            first_artifact_commit = self._commit_all_at(
                root,
                "followup fix artifact",
                "2026-06-27T12:22:00+00:00",
            )
            review_plan_path, _, _ = self._write_review_range_artifacts_for_range(
                root,
                b7=b7,
                h7=h7,
                timestamp="260627_1204",
            )
            second_artifact_commit = self._commit_all_at(
                root,
                "source review scaffold",
                "2026-06-27T12:23:00+00:00",
            )

            payload = MODULE.build_report(root)
            rendered = MODULE.render_plain(payload)

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["artifact_lineage"]["status"], "diverged")
        self.assertIn(review_plan_path, payload["artifact_lineage"]["divergent_artifact_paths"])
        self.assertIn(merge_notes_path, payload["artifact_lineage"]["divergent_artifact_paths"])
        review_plan = [
            artifact for artifact in payload["artifacts"] if artifact["path"] == review_plan_path
        ][0]
        review_lineage = review_plan["artifact_lineage"]
        self.assertEqual(review_lineage["readback_kind"], "derived/read-only")
        self.assertEqual(review_lineage["chronology_authority"], "git_commit_order")
        self.assertEqual(review_lineage["artifact_materialized_at"], "2026-06-27T12:04")
        self.assertEqual(review_lineage["artifact_materialized_at_source"], "filename_timestamp")
        self.assertTrue(review_lineage["derived_from_filename"])
        self.assertEqual(review_lineage["status_write_at_source"], "unknown")
        self.assertEqual(review_lineage["commit_sha"], second_artifact_commit)
        self.assertEqual(review_lineage["lineage_role"], "source_review_scaffold")
        self.assertTrue(review_lineage["diverges_from_commit_order"])
        merge_lineage = [
            artifact for artifact in payload["artifacts"] if artifact["path"] == merge_notes_path
        ][0]["artifact_lineage"]
        self.assertEqual(merge_lineage["commit_sha"], first_artifact_commit)
        self.assertEqual(merge_lineage["lineage_role"], "docs_closeout")
        self.assertGreater(
            merge_lineage["artifact_timestamp_order_index"],
            merge_lineage["commit_order_index"],
        )
        self.assertIn(
            "artifact timestamp lineage (derived/read-only; chronology authority=git_commit_order):",
            rendered,
        )
        self.assertIn("derived_from_filename=true", rendered)
        self.assertIn("lineage_role=source_review_scaffold", rendered)
        self.assertIn("filename timestamps are not commit chronology or status authority", rendered)

    def test_artifact_lineage_plain_output_stays_compact_when_order_is_aligned(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write(root, "README.md", "seed\n")
            base = self._commit_all_at(root, "seed", "2026-06-27T12:00:00+00:00")
            self._write(root, "src/change.txt", "range head\n")
            head = self._commit_all_at(root, "range head", "2026-06-27T12:01:00+00:00")
            b7 = base[:7]
            h7 = head[:7]
            self._write_custom_range_and_tracker(
                root,
                base=base,
                head=head,
                checklist=dedent(
                    """\
                    - [x] step:review_range
                    - [x] step:merge_notes
                    - [ ] step:plan_harvest
                    """
                ),
            )
            self._write_review_range_artifacts_for_range(root, b7=b7, h7=h7, timestamp="260627_1204")
            self._commit_all_at(root, "source review scaffold", "2026-06-27T12:04:00+00:00")
            self._write(
                root,
                f"docs/reviews/260627_1221_merge_notes_range_{b7}_{h7}.md",
                "# Merge notes\n\n**Status:** Done\n",
            )
            self._commit_all_at(root, "followup fix artifact", "2026-06-27T12:22:00+00:00")

            payload = MODULE.build_report(root)
            rendered = MODULE.render_plain(payload)

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["artifact_lineage"]["status"], "aligned")
        self.assertNotIn("artifact timestamp lineage", rendered)

    def test_completed_canon_sweep_without_proof_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist="- [x] step:canon_sweep\n- [ ] step:ready_to_push\n",
            )
            self._write(root, "docs/arch.md", "# Canon touch\n")

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertIn("missing_required_receipt", {error["code"] for error in payload["errors"]})
        canon_receipts = [
            receipt
            for receipt in payload["substep_receipts"]
            if receipt["step"] == "step:canon_sweep" and receipt["receipt"] == "canon_sweep_execution"
        ]
        self.assertEqual(len(canon_receipts), 1)
        self.assertFalse(canon_receipts[0]["present"])
        contextual_paths = {item["path"] for item in payload["git_status"]["candidate_contextual"]}
        self.assertIn("docs/arch.md", contextual_paths)

    def test_completed_canon_sweep_with_snapshot_proof_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist="- [x] step:canon_sweep\n- [ ] step:ready_to_push\n",
            )
            snapshot_path = f"docs/snapshots/260505_1200_architect_range_{B7}_{H7}_canon_sweep.md"
            self._write(root, snapshot_path, "# Canon sweep snapshot\n")

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "ok")
        self.assertNotIn("missing_required_receipt", {error["code"] for error in payload["errors"]})
        canon_receipts = [
            receipt
            for receipt in payload["substep_receipts"]
            if receipt["step"] == "step:canon_sweep" and receipt["receipt"] == "canon_sweep_execution"
        ]
        self.assertEqual(len(canon_receipts), 1)
        self.assertTrue(canon_receipts[0]["present"])
        self.assertEqual(canon_receipts[0]["path"], snapshot_path)

    def test_completed_canon_sweep_with_no_op_receipt_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist="- [x] step:canon_sweep\n- [ ] step:ready_to_push\n",
            )
            receipt_path = self._write_canon_sweep_receipt(root)

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "ok")
        self.assertNotIn("missing_required_receipt", {error["code"] for error in payload["errors"]})
        self.assertNotIn("inconsistent_receipt", {error["code"] for error in payload["errors"]})
        required_paths = {item["path"] for item in payload["git_status"]["required"]}
        self.assertIn(receipt_path, required_paths)
        canon_receipts = [
            receipt
            for receipt in payload["substep_receipts"]
            if receipt["step"] == "step:canon_sweep" and receipt["receipt"] == "canon_sweep_execution"
        ]
        self.assertEqual(len(canon_receipts), 1)
        self.assertTrue(canon_receipts[0]["present"])

    def test_completed_canon_sweep_with_report_receipt_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist="- [x] step:canon_sweep\n- [ ] step:ready_to_push\n",
            )
            receipt_path = self._write_canon_sweep_receipt(
                root,
                changed_count=1,
                changed_files="docs/playbooks/docs_canon_sweep.md",
                proof_kind="report",
                closure_field="report_path",
                closure_value=f"docs/reviews/260505_1200_canon_sweep_report_range_{B7}_{H7}.md",
                target_repo_impact="source_only",
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "ok")
        self.assertNotIn("inconsistent_receipt", {error["code"] for error in payload["errors"]})
        canon_receipts = [
            receipt
            for receipt in payload["substep_receipts"]
            if receipt["step"] == "step:canon_sweep" and receipt["receipt"] == "canon_sweep_execution"
        ]
        self.assertEqual(len(canon_receipts), 1)
        self.assertTrue(canon_receipts[0]["present"])
        self.assertEqual(canon_receipts[0]["path"], receipt_path)

    def test_canon_sweep_target_repo_impact_accepts_only_neutral_vocabulary(self) -> None:
        for target_repo_impact in ("source_only", "shared_consumer", "shared_multi", "none"):
            with self.subTest(target_repo_impact=target_repo_impact), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                receipt_path = self._write_canon_sweep_receipt(
                    root,
                    target_repo_impact=target_repo_impact,
                    packetization_handoff=(
                        "step:packetization_gate" if target_repo_impact.startswith("shared_") else "N/A (why=source-only impact)"
                    ),
                )
                errors = MODULE._validate_canon_sweep_receipt_text(
                    text=(root / receipt_path).read_text(encoding="utf-8"),
                    artifact_path=receipt_path,
                    packetization_reports=["docs/reviews/packetization_gate.md"],
                )

                self.assertEqual(errors, [])

        unsupported_impacts = ("retired_impact", "unsupported_impact")
        for target_repo_impact in unsupported_impacts:
            with self.subTest(target_repo_impact=target_repo_impact), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                receipt_path = self._write_canon_sweep_receipt(
                    root,
                    target_repo_impact=target_repo_impact,
                    packetization_handoff="step:packetization_gate",
                )
                errors = MODULE._validate_canon_sweep_receipt_text(
                    text=(root / receipt_path).read_text(encoding="utf-8"),
                    artifact_path=receipt_path,
                    packetization_reports=["docs/reviews/packetization_gate.md"],
                )

                self.assertTrue(any(f"unsupported target_repo_impact={target_repo_impact}" in error["detail"] for error in errors))

    def test_completed_canon_sweep_with_invented_proof_kind_fails_closed(self) -> None:
        for proof_kind in ("bounded_canon_sweep_report", "structural_skeleton"):
            with self.subTest(proof_kind=proof_kind):
                with tempfile.TemporaryDirectory() as tmpdir:
                    root = Path(tmpdir).resolve()
                    self._init_repo(root)
                    self._write_custom_range_and_tracker(
                        root,
                        base=BASE,
                        head=HEAD,
                        checklist="- [x] step:canon_sweep\n- [ ] step:ready_to_push\n",
                    )
                    self._write_canon_sweep_receipt(
                        root,
                        proof_kind=proof_kind,
                        closure_field="report_path",
                        closure_value=f"docs/reviews/260505_1200_canon_sweep_report_range_{B7}_{H7}.md",
                        target_repo_impact="source_only",
                    )

                    payload = MODULE.build_report(root)

                self.assertEqual(payload["status"], "blocked")
                details = "\n".join(error["detail"] for error in payload["errors"])
                self.assertIn(f"unsupported proof_kind={proof_kind}", details)
                self.assertIn("allowed values: no_op, report, snapshot", details)

    def test_completed_canon_sweep_with_ambiguous_closure_lanes_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist="- [x] step:canon_sweep\n- [ ] step:ready_to_push\n",
            )
            self._write_canon_sweep_receipt(
                root,
                proof_kind="report",
                closure_field="report_path",
                closure_value=f"docs/reviews/260505_1200_canon_sweep_report_range_{B7}_{H7}.md",
                extra_closures={"snapshot_path": f"docs/snapshots/260505_1200_range_{B7}_{H7}.md"},
                target_repo_impact="source_only",
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        details = "\n".join(error["detail"] for error in payload["errors"])
        self.assertIn("must have exactly one meaningful closure lane", details)
        self.assertIn("snapshot_path", details)
        self.assertIn("report_path", details)

    def test_completed_canon_sweep_with_malformed_receipt_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist="- [x] step:canon_sweep\n- [ ] step:ready_to_push\n",
            )
            self._write_canon_sweep_receipt(
                root,
                proof_kind="no_op",
                closure_field="no_op_reason",
                closure_value="we looked and nothing was needed",
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertIn("inconsistent_receipt", {error["code"] for error in payload["errors"]})

    def test_missing_tracker_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write(root, ".planveyor.range.base", f"{BASE}\n")
            self._write(root, ".planveyor.range.head", f"{HEAD}\n")

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertIn("missing_tracker", {error["code"] for error in payload["errors"]})

    def test_missing_required_artifact_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_range_and_tracker(root, merge_notes_checked=False)

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertIn("missing_required_artifact", {error["code"] for error in payload["errors"]})

    def test_range_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_range_and_tracker(root, merge_notes_checked=False)
            self._write(root, ".planveyor.range.head", f"{'c' * 40}\n")
            self._write_review_range_artifacts(root)

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertIn("range_mismatch", {error["code"] for error in payload["errors"]})

    def test_tracker_header_field_mismatch_fails_closed_even_when_range_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write(root, ".planveyor.range.base", f"{BASE}\n")
            self._write(root, ".planveyor.range.head", f"{HEAD}\n")
            self._write(
                root,
                ".planveyor.merge_tracker.md",
                dedent(
                    f"""\
                    # Merge tracker

                    BASE={BASE}
                    HEAD={'c' * 40}
                    RANGE={BASE}..{HEAD}
                    RANGE_ID=range_{B7}_{H7}

                    ## Checklist
                    - [ ] step:merge_notes
                    """
                ),
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertIn("tracker_header_mismatch", {error["code"] for error in payload["errors"]})
        self.assertEqual(payload["tracker"]["header"]["HEAD"], "c" * 40)

    def test_ambiguous_duplicate_artifact_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_range_and_tracker(root)
            self._write_review_range_artifacts(root)
            self._write(
                root,
                f"docs/reviews/260505_1200_merge_notes_range_{B7}_{H7}.md",
                "# Merge notes\n\n**Status:** ✅ Done\n",
            )
            self._write(
                root,
                f"docs/reviews/260505_1201_merge_notes_range_{B7}_{H7}.md",
                "# Merge notes\n\n**Status:** ✅ Done\n",
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertIn("ambiguous_artifact", {error["code"] for error in payload["errors"]})

    def test_duplicate_operational_receipts_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_range_and_tracker(root)
            self._write_review_range_artifacts(root)
            first_path = f"docs/reviews/260505_1200_post_merge_operational_receipt_range_{B7}_{H7}.md"
            second_path = f"docs/reviews/260505_1201_post_merge_operational_receipt_range_{B7}_{H7}.md"
            self._write_operational_receipt_artifact(root)
            duplicate_payload = self._operational_receipt_payload(
                generated_at="2026-05-16T00:01:00+00:00",
            )
            duplicate_payload["receipt_path"] = second_path
            self._write(
                root,
                second_path,
                dedent(
                    f"""\
                    # Post-merge operational receipt

                    **Status:** ✅ Done

                    ## Operational receipt JSON
                    ```json
                    {json.dumps(duplicate_payload, indent=2, sort_keys=True)}
                    ```
                    """
                ),
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        ambiguous_details = [
            error["detail"] for error in payload["errors"] if error["code"] == "ambiguous_artifact"
        ]
        self.assertTrue(ambiguous_details)
        joined_details = "\n".join(ambiguous_details)
        self.assertIn(first_path, joined_details)
        self.assertIn(second_path, joined_details)
        self.assertIn("post_merge_operational_receipt", joined_details)

    def test_plan_harvest_primary_and_supplemental_followups_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist="- [x] step:plan_harvest\n- [ ] step:ready_to_push\n",
            )
            self._write_plan_harvest_artifacts(
                root,
                extra_report_body=self._complete_plan_harvest_receipts(),
            )
            supplemental_path = self._write_supplemental_audit_followups(root)

            payload = MODULE.build_report(root)
            rendered = MODULE.render_plain(payload)

        self.assertEqual(payload["status"], "ok")
        self.assertNotIn("ambiguous_artifact", {error["code"] for error in payload["errors"]})
        primary = [
            artifact
            for artifact in payload["artifacts"]
            if artifact["kind"] == "followups_backlog"
        ]
        supplemental = [
            artifact
            for artifact in payload["artifacts"]
            if artifact["kind"] == "supplemental_followups_backlog"
        ]
        self.assertEqual(len(primary), 1)
        self.assertTrue(primary[0]["required"])
        self.assertEqual(primary[0]["followups_role"], "primary_plan_harvest")
        self.assertEqual(len(supplemental), 1)
        self.assertFalse(supplemental[0]["required"])
        self.assertEqual(supplemental[0]["path"], supplemental_path)
        self.assertEqual(supplemental[0]["followups_role"], "supplemental_post_merge_audit")
        self.assertIn("step:plan_harvest followups_backlog [required", rendered)
        self.assertIn("step:plan_harvest supplemental_followups_backlog [candidate/contextual", rendered)
        self.assertIn("role=supplemental_post_merge_audit", rendered)

    def test_plan_harvest_duplicate_primary_followups_still_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist="- [x] step:plan_harvest\n- [ ] step:ready_to_push\n",
            )
            self._write_plan_harvest_artifacts(root)
            self._write(
                root,
                f"docs/followups/260505_1201_followups_range_{B7}_{H7}.md",
                dedent(
                    """\
                    # Follow-ups backlog

                    **Source:** plan harvest
                    **Status:** Done
                    **Imported into:** `docs/followups/process_followups_master.md`

                    ## Range result
                    - `NO FOLLOWUPS` - duplicate primary fixture.
                    """
                ),
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertIn("ambiguous_artifact", {error["code"] for error in payload["errors"]})
        detail = "\n".join(error["detail"] for error in payload["errors"])
        self.assertIn("260505_1200_followups_range", detail)
        self.assertIn("260505_1201_followups_range", detail)

    def test_plan_harvest_supplemental_only_followups_fails_missing_primary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist="- [x] step:plan_harvest\n- [ ] step:ready_to_push\n",
            )
            self._write(
                root,
                f"docs/reviews/260505_1200_plan_harvest_range_{B7}_{H7}.md",
                dedent(
                    f"""\
                    # Plan harvest

                    **Status:** Done

                    ## Follow-ups (extracted; без дублей)
                    - Result: `NO FOLLOWUPS`.
                    {self._complete_plan_harvest_receipts()}
                    """
                ),
            )
            self._write_supplemental_audit_followups(root)

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertIn("missing_required_artifact", {error["code"] for error in payload["errors"]})
        self.assertNotIn("ambiguous_artifact", {error["code"] for error in payload["errors"]})
        self.assertIn(
            "supplemental_followups_backlog",
            {artifact["kind"] for artifact in payload["artifacts"]},
        )

    def test_plan_harvest_malformed_same_range_followups_fail_closed(self) -> None:
        cases = [
            (
                "missing_source",
                {"source": None},
                "unsupported or missing Source=missing",
            ),
            (
                "na_import",
                {"imported_into": "N/A (why=not imported)"},
                "malformed Imported into=N/A",
            ),
            (
                "missing_import",
                {"imported_into": None},
                "malformed Imported into=missing",
            ),
            (
                "conflicting_filename_header",
                {"source": "plan harvest"},
                "Source=plan harvest but filename is not the primary",
            ),
        ]
        for case_name, overrides, expected_detail in cases:
            with self.subTest(case=case_name):
                with tempfile.TemporaryDirectory() as tmpdir:
                    root = Path(tmpdir).resolve()
                    self._init_repo(root)
                    self._write_custom_range_and_tracker(
                        root,
                        base=BASE,
                        head=HEAD,
                        checklist="- [x] step:plan_harvest\n- [ ] step:ready_to_push\n",
                    )
                    self._write_plan_harvest_artifacts(
                        root,
                        extra_report_body=self._complete_plan_harvest_receipts(),
                    )
                    self._write_supplemental_audit_followups(root, **overrides)

                    payload = MODULE.build_report(root)

                self.assertEqual(payload["status"], "blocked")
                self.assertIn(
                    "inconsistent_artifact_classification",
                    {error["code"] for error in payload["errors"]},
                )
                self.assertIn(expected_detail, "\n".join(error["detail"] for error in payload["errors"]))

    def test_non_final_status_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_range_and_tracker(root)
            self._write_review_range_artifacts(root)
            self._write(
                root,
                f"docs/reviews/260505_1200_merge_notes_range_{B7}_{H7}.md",
                "# Merge notes\n\n**Status:** Draft\n",
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertIn("non_final_artifact_status", {error["code"] for error in payload["errors"]})

    def test_completed_plan_harvest_missing_substep_receipts_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist="- [x] step:plan_harvest\n- [ ] step:ready_to_push\n",
            )
            self._write_plan_harvest_artifacts(root)

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertIn("missing_required_receipt", {error["code"] for error in payload["errors"]})
        missing_receipts = {
            receipt["receipt"]
            for receipt in payload["substep_receipts"]
            if not receipt["present"]
        }
        self.assertIn("followup_harvest_triage_import", missing_receipts)
        self.assertIn("docs_retrieval_metrics", missing_receipts)

    def test_completed_plan_harvest_with_substep_receipts_passes(self) -> None:
        receipt_body = dedent(
            """\

            ## Follow-up harvest triage/import receipt
            - `planveyor_followups_triage --file docs/followups/260505_1200_followups_range_aaaaaaa_bbbbbbb.md --apply`: imported=0, duplicate=0, open=0.

            ## Process-improvement promotion decisions
            - `N/A (why=no mature process-improvement rows in range)`.

            ## Docs retrieval metrics receipt
            - Summary copied from metrics: query_total=0, evaluated_total=0, read_log_status=missing, read_events_total=0.

            ## Golden Path lane receipt
            - `lane=tooling_process`; `active carrier=docs/guides/golden_paths.md#post-merge-plan-harvest`; `outcome=no changes needed (why=fixture)`.

            ## ADR candidates / durable decisions
            - `N/A (why=no durable decision candidate in fixture)`.

            ## Canon/follow-up summary
            - canon_updates=0; followups=0.
            """
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist="- [x] step:plan_harvest\n- [ ] step:ready_to_push\n",
            )
            self._write_plan_harvest_artifacts(root, extra_report_body=receipt_body)

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "ok")
        self.assertNotIn("missing_required_receipt", {error["code"] for error in payload["errors"]})
        self.assertTrue(all(receipt["present"] for receipt in payload["substep_receipts"]))

    def test_operator_receipt_checklist_marks_ok_rows_in_json_and_plain_output(self) -> None:
        receipt_body = dedent(
            """\

            ## Follow-up harvest triage/import receipt
            - `planveyor_followups_triage --file docs/followups/260505_1200_followups_range_aaaaaaa_bbbbbbb.md --apply`: imported=0, duplicate=0, open=0.

            ## Process-improvement promotion decisions
            - `N/A (why=no mature process-improvement rows in range)`.

            ## Docs retrieval metrics receipt
            - Summary copied from metrics: query_total=0, evaluated_total=0, read_log_status=missing, read_events_total=0.

            ## Golden Path lane receipt
            - `lane=tooling_process`; `active carrier=docs/guides/golden_paths.md#post-merge-plan-harvest`; `outcome=no changes needed (why=fixture)`.

            ## ADR candidates / durable decisions
            - `N/A (why=no durable decision candidate in fixture)`.

            ## Canon/follow-up summary
            - canon_updates=0; followups=0.
            """
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist="- [x] step:plan_harvest\n- [ ] step:ready_to_push\n",
            )
            self._write_plan_harvest_artifacts(root, extra_report_body=receipt_body)

            payload = MODULE.build_report(root)
            rendered = MODULE.render_plain(payload)

        checklist = {
            row["receipt"]: row
            for row in payload["operator_receipt_checklist"]
            if row["step"] == "step:plan_harvest"
        }
        self.assertEqual(checklist["followup_harvest_triage_import"]["status"], "ok")
        self.assertEqual(checklist["followup_harvest_triage_import"]["blocker_code"], "N/A")
        self.assertEqual(checklist["followup_harvest_triage_import"]["next_action"], "N/A (already present)")
        self.assertIn("operator receipt checklist:", rendered)
        self.assertIn("step:plan_harvest followup_harvest_triage_import [ok; blocker=N/A]", rendered)

    def test_operator_receipt_checklist_maps_missing_required_receipts_to_next_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist="- [x] step:plan_harvest\n- [ ] step:ready_to_push\n",
            )
            self._write_plan_harvest_artifacts(root)

            payload = MODULE.build_report(root)
            rendered = MODULE.render_plain(payload)

        row = next(
            item
            for item in payload["operator_receipt_checklist"]
            if item["step"] == "step:plan_harvest"
            and item["receipt"] == "followup_harvest_triage_import"
        )
        self.assertEqual(row["status"], "missing")
        self.assertEqual(row["blocker_code"], "missing_required_receipt")
        self.assertEqual(row["source_command"], "update the plan-harvest report artifact")
        self.assertIn("docs/reviews/*_plan_harvest_range_<base7>_<head7>.md", row["next_action"])
        self.assertNotIn("planveyor_merge_tracker_tick", row["next_action"])
        self.assertIn(
            "step:plan_harvest followup_harvest_triage_import [missing; blocker=missing_required_receipt]",
            rendered,
        )

    def test_operator_receipt_checklist_maps_inconsistent_receipts_to_next_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist="- [x] step:canon_sweep\n- [ ] step:ready_to_push\n",
            )
            self._write_canon_sweep_receipt(
                root,
                proof_kind="no_op",
                closure_field="no_op_reason",
                closure_value="we looked and nothing was needed",
            )

            payload = MODULE.build_report(root)
            rendered = MODULE.render_plain(payload)

        row = next(
            item
            for item in payload["operator_receipt_checklist"]
            if item["step"] == "step:canon_sweep"
            and item["receipt"] == "canon_sweep_execution"
        )
        self.assertEqual(row["status"], "inconsistent")
        self.assertEqual(row["blocker_code"], "inconsistent_receipt")
        self.assertEqual(row["source_command"], "planveyor_arch_canon_sweep_start")
        self.assertIn("docs/reviews/*_canon_sweep_receipt_range_<base7>_<head7>.md", row["next_action"])
        self.assertNotIn("planveyor_merge_tracker_tick", row["next_action"])
        self.assertIn(
            "step:canon_sweep canon_sweep_execution [inconsistent; blocker=inconsistent_receipt]",
            rendered,
        )

    def test_operator_receipt_checklist_preserves_unmatched_errors_as_advisory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write(root, ".planveyor.range.base", f"{BASE}\n")
            self._write(root, ".planveyor.range.head", f"{HEAD}\n")

            payload = MODULE.build_report(root)

        row = next(
            item
            for item in payload["operator_receipt_checklist"]
            if item["blocker_code"] == "missing_tracker"
        )
        self.assertEqual(row["status"], "advisory")
        self.assertEqual(row["next_action"], "inspect planveyor_merge_bundle_report error detail")

    def test_completed_plan_harvest_retrieve_evidence_requires_retrieval_telemetry_receipt(self) -> None:
        receipt_body = dedent(
            """\

            ## Follow-up harvest triage/import receipt
            - `planveyor_followups_triage --file docs/followups/260505_1200_followups_range_aaaaaaa_bbbbbbb.md --apply`: imported=0, duplicate=0, open=0.

            ## Process-improvement promotion decisions
            - `N/A (why=no mature process-improvement rows in range)`.

            ## Docs retrieval metrics receipt
            - Summary copied from metrics: query_total=0, evaluated_total=0, read_log_status=missing, read_events_total=0.

            ## Golden Path lane receipt
            - `lane=tooling_process`; `active carrier=docs/guides/golden_paths.md#post-merge-plan-harvest`; `outcome=no changes needed (why=fixture)`.

            ## ADR candidates / durable decisions
            - `N/A (why=no durable decision candidate in fixture)`.

            ## Canon/follow-up summary
            - canon_updates=0; followups=0.

            ## Lookup evidence
            - Used `planveyor_docs_retrieve plans "retrieval receipt"` for source selection.
            """
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist="- [x] step:plan_harvest\n- [ ] step:ready_to_push\n",
            )
            self._write_plan_harvest_artifacts(root, extra_report_body=receipt_body)

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertIn("missing_required_receipt", {error["code"] for error in payload["errors"]})
        missing_receipts = {
            receipt["receipt"]
            for receipt in payload["substep_receipts"]
            if not receipt["present"]
        }
        self.assertIn("retrieval_telemetry", missing_receipts)

    def test_completed_plan_harvest_lookup_evidence_with_retrieval_telemetry_receipt_passes(self) -> None:
        receipt_body = dedent(
            """\

            ## Follow-up harvest triage/import receipt
            - `planveyor_followups_triage --file docs/followups/260505_1200_followups_range_aaaaaaa_bbbbbbb.md --apply`: imported=0, duplicate=0, open=0.

            ## Process-improvement promotion decisions
            - `N/A (why=no mature process-improvement rows in range)`.

            ## Docs retrieval metrics receipt
            - Summary copied from metrics: query_total=0, evaluated_total=0, read_log_status=missing, read_events_total=0.

            ## Golden Path lane receipt
            - `lane=tooling_process`; `active carrier=docs/guides/golden_paths.md#post-merge-plan-harvest`; `outcome=no changes needed (why=fixture)`.

            ## ADR candidates / durable decisions
            - `N/A (why=no durable decision candidate in fixture)`.

            ## Canon/follow-up summary
            - canon_updates=0; followups=0.

            ## Lookup evidence
            - Used `planveyor_docs_lookup plans "retrieval receipt"` for source selection.

            ## Retrieval telemetry receipt
            - query_event_id: `20260511T120000Z-abcd123456-12345678`
            - used_for_decision: `true`
            - read_open: `ok`
            - read_log_status: `present`
            - read_event_id: `read-20260511T120001Z-12345678`
            - outcome: `used`
            - outcome_reason: used for harvest source selection.
            - cited/opened files: `docs/tools/snippet.md`
            """
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist="- [x] step:plan_harvest\n- [ ] step:ready_to_push\n",
            )
            self._write_plan_harvest_artifacts(root, extra_report_body=receipt_body)

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "ok")
        retrieval_receipts = [
            receipt for receipt in payload["substep_receipts"] if receipt["receipt"] == "retrieval_telemetry"
        ]
        self.assertEqual(len(retrieval_receipts), 1)
        self.assertTrue(retrieval_receipts[0]["present"])

    def test_ready_to_push_requires_operational_receipt_at_final_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [ ] step:ready_to_push
                    """
                ),
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertIn("missing_required_receipt", {error["code"] for error in payload["errors"]})
        self.assertTrue(
            any("post_merge_operational_receipt" in error["detail"] for error in payload["errors"])
        )

    def test_final_bundle_revalidates_docs_finalize_receipt_after_local_tick(self) -> None:
        checklist = dedent(
            """\
            - [x] step:docs_finalize
            - [x] step:doc_lint
            - [x] step:docs_hygiene_archive
            - [x] step:docs_hygiene_suggest
            - [ ] step:ready_to_push
            """
        )
        receipt_path = f"docs/reviews/260829_1808_docs_finalize_receipt_range_{B7}_{H7}.md"
        duplicate_path = f"docs/reviews/260829_1809_docs_finalize_receipt_range_{B7}_{H7}.md"
        receipt_body = self._docs_finalize_receipt(
            rel_path=receipt_path,
            process_body="NO PROCESS IMPROVEMENTS — why: clean_run",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=checklist,
                write_docs_finalize_receipt=False,
            )
            self._write_operational_receipt_artifact(root)

            missing = MODULE.build_report(root)

            self._write(root, receipt_path, receipt_body)
            green = MODULE.build_report(root)

            self._write(
                root,
                duplicate_path,
                self._docs_finalize_receipt(
                    rel_path=duplicate_path,
                    process_body="NO PROCESS IMPROVEMENTS — why: clean_run",
                ),
            )
            ambiguous = MODULE.build_report(root)
            (root / duplicate_path).unlink()

            (root / receipt_path).unlink()
            deleted_after_green = MODULE.build_report(root)

            self._write(
                root,
                receipt_path,
                receipt_body.replace(
                    f"docs_finalize_receipt_path={receipt_path}",
                    f"docs_finalize_receipt_path={duplicate_path}",
                ),
            )
            mutated_after_green = MODULE.build_report(root)

        self.assertEqual(missing["status"], "blocked")
        self.assertIn("missing_required_artifact", {error["code"] for error in missing["errors"]})
        self.assertEqual(green["status"], "ok")
        docs_finalize_artifacts = [
            artifact for artifact in green["artifacts"] if artifact["kind"] == MODULE.DOCS_FINALIZE_RECEIPT_KIND
        ]
        self.assertEqual(len(docs_finalize_artifacts), 1)
        self.assertTrue(docs_finalize_artifacts[0]["required"])
        self.assertIn(
            "architect_docs_finalize_receipt",
            {receipt["receipt"] for receipt in green["substep_receipts"]},
        )
        self.assertEqual(ambiguous["status"], "blocked")
        self.assertIn("ambiguous_artifact", {error["code"] for error in ambiguous["errors"]})
        self.assertEqual(deleted_after_green["status"], "blocked")
        self.assertIn(
            "missing_required_artifact",
            {error["code"] for error in deleted_after_green["errors"]},
        )
        self.assertEqual(mutated_after_green["status"], "blocked")
        self.assertIn(
            "docs_finalize_receipt_readback_mismatch",
            {error["code"] for error in mutated_after_green["errors"]},
        )

    def test_ready_to_push_operational_receipt_allows_closeout_without_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [ ] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(root)
            retained_temp_doc = "docs/plans/260505_1200_retained_temp_plan.md"
            self._write(root, retained_temp_doc, "# Retained temp plan\n\n**Status:** Done\n")

            payload = MODULE.build_report(root)
            rendered = MODULE.render_plain(payload)

        self.assertEqual(payload["status"], "ok")
        self.assertNotIn("missing_required_receipt", {error["code"] for error in payload["errors"]})
        operational_artifacts = [
            artifact for artifact in payload["artifacts"] if artifact["kind"] == "post_merge_operational_receipt"
        ]
        self.assertEqual(len(operational_artifacts), 1)
        self.assertTrue(operational_artifacts[0]["required"])
        self.assertIn("post_merge_operational_closeout [present]", rendered)
        self.assertIn("archive snapshot receipt:", rendered)
        self.assertIn("storage_backend: git_text_export", rendered)
        self.assertIn("restore_status: ok", rendered)
        self.assertIn("process improvements open summary:", rendered)
        self.assertIn("lane_status: separate", rendered)
        self.assertIn("followups lane reconciliation:", rendered)
        self.assertIn("harvest_file_followups_result: NO FOLLOWUPS", rendered)
        self.assertIn("range_append_new: 2", rendered)
        self.assertIn("owner_summary: file-lane=NO FOLLOWUPS (0); range-lane apply append_new=2", rendered)
        self.assertEqual(payload["followups_lane_reconciliation"]["harvest_file_followups_result"], "NO FOLLOWUPS")
        self.assertEqual(payload["followups_lane_reconciliation"]["range_append_new"], 2)
        self.assertEqual(payload["process_improvements_open_summary"]["counts_by_raw_status"]["open"], 2)
        contextual_paths = {item["path"] for item in payload["git_status"]["candidate_contextual"]}
        self.assertIn(retained_temp_doc, contextual_paths)
        self.assertEqual(payload["ready_to_push_terminal_proof"]["state"], "pre_terminal_missing_allowed")
        self.assertEqual(payload["ready_to_push_terminal_proof"]["pre_receipt_state"], "pre_receipt_pending")

    def test_ready_to_push_operational_receipt_accepts_process_improvements_owner_with_comma(self) -> None:
        owner_or_next_step = "use process-improvement promotion workflow, not ordinary plan-harvest duplication."
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [ ] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(
                root,
                process_improvements_source_owner_or_next_step=owner_or_next_step,
                process_improvements_open_summary_overrides={"owner_or_next_step": owner_or_next_step},
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["process_improvements_open_summary"]["owner_or_next_step"], owner_or_next_step)
        self.assertFalse(
            any(
                error["code"] == "stale_receipt_copy"
                and "field=process_improvements_open_summary.owner_or_next_step" in error["detail"]
                for error in payload["errors"]
            )
        )

    def test_ready_to_push_operational_receipt_missing_followups_reconciliation_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [ ] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(root, omit_followups_lane_reconciliation=True)

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertTrue(
            any("followups_lane_reconciliation must be an object" in error["detail"] for error in payload["errors"])
        )

    def test_ready_to_push_operational_receipt_rejects_mismatched_followups_reconciliation_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [ ] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(
                root,
                followups_lane_reconciliation_overrides={"range_append_new": 0},
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertTrue(
            any(
                "followups_lane_reconciliation.range_append_new must match" in error["detail"]
                for error in payload["errors"]
            )
        )

    def test_ready_to_push_operational_receipt_rejects_stale_followups_source_counts(self) -> None:
        records = self._operational_step_records()
        for record in records:
            if record["step"] == "followups_triage_launch":
                record["count_summary"] = str(record["count_summary"]).replace(
                    "apply_append_new=2",
                    "apply_append_new=1",
                )
                break
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [ ] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(
                root,
                record_overrides={"followups_triage_launch": records[6]},
                followups_triage_launch_receipt_overrides={
                    "apply": {
                        "append_new": 1,
                        "merge_source": 0,
                        "possible_duplicate": 0,
                        "route_fallback": 0,
                    }
                },
                followups_lane_reconciliation_overrides={
                    "range_append_new": 1,
                    "owner_summary": (
                        "file-lane=NO FOLLOWUPS (0); range-lane apply append_new=1, "
                        "possible_duplicate=0, route_fallback=0, unparsed_bullets=0; triage_mode=file"
                    ),
                },
            )

            payload = MODULE.build_report(root)

        stale_errors = [error for error in payload["errors"] if error["code"] == "stale_receipt_copy"]
        self.assertEqual(payload["status"], "blocked")
        self.assertTrue(
            any(
                "field=followups_lane_reconciliation.range_append_new" in error["detail"]
                and "expected=2; actual=1" in error["detail"]
                and "source=docs/reviews/260505_1200_plan_harvest_range_" in error["detail"]
                and "target=docs/reviews/260505_1200_post_merge_operational_receipt_range_" in error["detail"]
                for error in stale_errors
            )
        )

    def test_current_plan_harvest_literals_block_preflight_and_drive_freshness_parity(self) -> None:
        source_path = f"docs/reviews/260505_1200_plan_harvest_range_{B7}_{H7}.md"
        target_path = f"docs/reviews/260505_1200_post_merge_operational_receipt_range_{B7}_{H7}.md"
        current_source = dedent(
            """\
            # Plan harvest

            **Status:** Done
            **Schema version:** review.v1

            ## Follow-up harvest triage/import receipt
            - harvest_file_followups_result: `created/imported`
            - harvest_file_followups_count: 2
            - triage (idempotency): append_new=0, possible_duplicate=0, route_fallback=0, unparsed_bullets=0.

            ## Process-improvement promotion decisions
            - `N/A (why=fixture)`.

            ## Docs retrieval metrics receipt
            - query_total=0; evaluated_total=0; read_log_status=missing; read_events_total=0.

            ## Golden Path lane receipt
            - `lane=tooling_process`; `active carrier=docs/guides/golden_paths.md#post-merge-plan-harvest`.

            ## ADR candidates / durable decisions
            - `N/A (why=fixture)`.

            ## Canon/follow-up summary
            - canon_updates=0; followups=0.

            ## Follow-ups (extracted; без дублей)
            - Result: `created/imported`.
            """
        )
        artifacts = [
            {"step": "step:plan_harvest", "kind": "plan_harvest", "path": source_path, "active_candidate": True},
            {"step": "step:ready_to_push", "kind": MODULE.OPERATIONAL_RECEIPT_KIND, "path": target_path, "active_candidate": True},
        ]
        reconciliation = {
            "source_harvest_receipt_path": source_path,
            "harvest_file_followups_result": "created/imported",
            "harvest_file_followups_count": 2,
            "range_triage_mode": "file",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write(root, source_path, current_source)
            receipts, preflight_errors = MODULE._validate_substep_receipts(
                root=root,
                artifacts=artifacts,
                completed_steps={"step:plan_harvest"},
                packetization_required=False,
                packetization_reports=[],
            )
            fresh_errors = MODULE._validate_operational_harvest_freshness(
                root=root,
                artifacts=artifacts,
                operational_payload={"followups_lane_reconciliation": reconciliation},
            )
            reconciliation["harvest_file_followups_count"] = 1
            stale_errors = MODULE._validate_operational_harvest_freshness(
                root=root,
                artifacts=artifacts,
                operational_payload={"followups_lane_reconciliation": reconciliation},
            )
            self._write(
                root,
                source_path,
                current_source.replace(
                    ", unparsed_bullets=0.",
                    ".",
                ),
            )
            _idempotency_receipts, idempotency_preflight_errors = MODULE._validate_substep_receipts(
                root=root,
                artifacts=artifacts,
                completed_steps={"step:plan_harvest"},
                packetization_required=False,
                packetization_reports=[],
            )
            idempotency_freshness_errors = MODULE._validate_operational_harvest_freshness(
                root=root,
                artifacts=artifacts,
                operational_payload={"followups_lane_reconciliation": reconciliation},
            )
            self._write(
                root,
                source_path,
                current_source.replace(
                    "- harvest_file_followups_result: `created/imported`\n- harvest_file_followups_count: 2\n",
                    "",
                ),
            )
            _red_receipts, red_preflight_errors = MODULE._validate_substep_receipts(
                root=root,
                artifacts=artifacts,
                completed_steps={"step:plan_harvest"},
                packetization_required=False,
                packetization_reports=[],
            )
            red_freshness_errors = MODULE._validate_operational_harvest_freshness(
                root=root,
                artifacts=artifacts,
                operational_payload={"followups_lane_reconciliation": reconciliation},
            )

        self.assertTrue(any(receipt["receipt"] == "file_followups_literal_contract" and receipt["present"] for receipt in receipts))
        self.assertFalse(
            any(error["code"] == "invalid_current_plan_harvest_file_followups" for error in preflight_errors),
            preflight_errors,
        )
        self.assertEqual(fresh_errors, [])
        self.assertTrue(
            any(
                error["code"] == "stale_receipt_copy"
                and "field=followups_lane_reconciliation.harvest_file_followups_count" in error["detail"]
                and "expected=2; actual=1" in error["detail"]
                for error in stale_errors
            ),
            stale_errors,
        )
        self.assertTrue(
            any(
                error["code"] == "invalid_current_plan_harvest_file_followups"
                and "missing_harvest_file_followups_result" in error["detail"]
                for error in red_preflight_errors
            ),
            red_preflight_errors,
        )
        self.assertTrue(
            any(
                error["code"] == "invalid_current_plan_harvest_file_followups"
                and "missing_harvest_file_followups_idempotency_counter" in error["detail"]
                and "unparsed_bullets" in error["detail"]
                for error in idempotency_preflight_errors
            ),
            idempotency_preflight_errors,
        )
        self.assertTrue(
            any(error["code"] == "invalid_current_truth_host" for error in red_freshness_errors),
            red_freshness_errors,
        )
        self.assertTrue(
            any(
                error["code"] == "invalid_current_truth_host"
                and "missing_harvest_file_followups_idempotency_counter" in error["detail"]
                for error in idempotency_freshness_errors
            ),
            idempotency_freshness_errors,
        )

    def test_ready_to_push_operational_receipt_rejects_stale_process_improvements_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [ ] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(
                root,
                process_improvements_open_summary_overrides={
                    "counts_by_raw_status": {"open": 1, "triaged": 0, "promoted": 0},
                    "null_execution_rows": 1,
                },
            )

            payload = MODULE.build_report(root)

        stale_errors = [error for error in payload["errors"] if error["code"] == "stale_receipt_copy"]
        self.assertEqual(payload["status"], "blocked")
        self.assertTrue(
            any(
                "field=process_improvements_open_summary.counts_by_raw_status.open" in error["detail"]
                and "expected=2; actual=1" in error["detail"]
                for error in stale_errors
            )
        )

    def test_ready_to_push_operational_receipt_rejects_historical_harvest_source_path(self) -> None:
        old_source = f"docs/reviews/260505_1159_plan_harvest_range_{B7}_{H7}.md"
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [ ] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(
                root,
                followups_triage_launch_receipt_overrides={"source_harvest_receipt_path": old_source},
                followups_lane_reconciliation_overrides={"source_harvest_receipt_path": old_source},
                process_improvements_open_summary_overrides={
                    "source_harvest_receipt_path": old_source,
                    "decision_receipt_path": f"{old_source}#process-improvement-promotion-decisions",
                },
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertTrue(
            any(
                error["code"] == "stale_receipt_copy"
                and "field=followups_lane_reconciliation.source_harvest_receipt_path" in error["detail"]
                and f"actual={old_source}" in error["detail"]
                for error in payload["errors"]
            )
        )

    def test_ready_to_push_operational_receipt_rejects_ambiguous_followups_owner_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [ ] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(
                root,
                followups_lane_reconciliation_overrides={
                    "owner_summary": "file-lane=NO FOLLOWUPS (0); file-lane apply append_new=2"
                },
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertTrue(
            any(
                "followups_lane_reconciliation.owner_summary must label non-zero range counts as range-lane"
                in error["detail"]
                for error in payload["errors"]
            )
        )

    def test_ready_to_push_operational_receipt_rejects_reviews_file_mode_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [ ] step:ready_to_push
                    """
                ),
            )
            invalid_command = (
                f"planveyor_followups_triage --file docs/reviews/260505_1200_plan_harvest_range_{B7}_{H7}.md "
                "--dry-run; "
                f"planveyor_followups_triage --file docs/reviews/260505_1200_plan_harvest_range_{B7}_{H7}.md "
                "--apply; "
                f"planveyor_followups_triage --file docs/reviews/260505_1200_plan_harvest_range_{B7}_{H7}.md "
                "--apply; "
                "scripts/followups_index_rebuild.py --project-root ."
            )
            self._write_operational_receipt_artifact(
                root,
                record_overrides={"followups_triage_launch": {"command": invalid_command}},
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertTrue(
            any("command --file target must be a repo-relative docs/followups/*.md inbox" in error["detail"] for error in payload["errors"])
        )

    def test_ready_to_push_operational_receipt_rejects_unresolved_followups_idempotency(self) -> None:
        records = self._operational_step_records()
        for record in records:
            if record["step"] == "followups_triage_launch":
                record["count_summary"] = str(record["count_summary"]).replace(
                    "idempotency_route_fallback=0",
                    "idempotency_route_fallback=1",
                )
                break
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [ ] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(
                root,
                record_overrides={"followups_triage_launch": {"count_summary": records[6]["count_summary"]}},
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertTrue(
            any("count_summary.idempotency_route_fallback must be 0 at final proof" in error["detail"] for error in payload["errors"])
        )

    def test_ready_to_push_operational_receipt_rejects_unresolved_range_unparsed_bullets(self) -> None:
        records = self._operational_step_records()
        range_ref = f"{BASE}..{HEAD}"
        range_command = (
            f"planveyor_followups_triage --range {range_ref} --dry-run; "
            f"planveyor_followups_triage --range {range_ref} --apply; "
            f"planveyor_followups_triage --range {range_ref} --apply; "
            "scripts/followups_index_rebuild.py --project-root ."
        )
        for record in records:
            if record["step"] == "followups_triage_launch":
                record["command"] = range_command
                record["count_summary"] = str(record["count_summary"]).replace(
                    "triage_mode=file",
                    "triage_mode=range",
                )
                record["count_summary"] += (
                    "; dry_run_unparsed_bullets=0; apply_unparsed_bullets=0; "
                    "idempotency_unparsed_bullets=1"
                )
                break
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [ ] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(
                root,
                record_overrides={"followups_triage_launch": records[6]},
                followups_triage_launch_receipt_overrides={
                    "triage_mode": "range",
                    "command": range_command,
                    "dry_run": {
                        "append_new": 0,
                        "merge_source": 0,
                        "possible_duplicate": 0,
                        "route_fallback": 0,
                        "unparsed_bullets": 0,
                    },
                    "apply": {
                        "append_new": 0,
                        "merge_source": 0,
                        "possible_duplicate": 0,
                        "route_fallback": 0,
                        "unparsed_bullets": 0,
                    },
                    "idempotency_apply": {
                        "append_new": 0,
                        "merge_source": 0,
                        "possible_duplicate": 0,
                        "route_fallback": 0,
                        "unparsed_bullets": 1,
                    },
                },
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertTrue(
            any(
                "followups_triage_launch_receipt.idempotency_apply.unparsed_bullets must be 0 at final proof"
                in error["detail"]
                for error in payload["errors"]
            )
        )

    def test_ready_to_push_operational_receipt_accepts_unresolved_range_with_manual_decision_ref(self) -> None:
        records = self._operational_step_records()
        range_ref = f"{BASE}..{HEAD}"
        range_command = (
            f"planveyor_followups_triage --range {range_ref} --dry-run; "
            f"planveyor_followups_triage --range {range_ref} --apply; "
            f"planveyor_followups_triage --range {range_ref} --apply; "
            "scripts/followups_index_rebuild.py --project-root ."
        )
        manual_ref = "docs/reviews/260505_1200_plan_harvest_range_aaaaaaa_bbbbbbb.md#manual-followups-decision"
        for record in records:
            if record["step"] == "followups_triage_launch":
                record["command"] = range_command
                record["count_summary"] = str(record["count_summary"]).replace(
                    "triage_mode=file",
                    "triage_mode=range",
                )
                record["count_summary"] += (
                    "; dry_run_unparsed_bullets=0; apply_unparsed_bullets=0; "
                    f"idempotency_unparsed_bullets=1; manual_decision_ref={manual_ref}"
                )
                break
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [ ] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(
                root,
                record_overrides={"followups_triage_launch": records[6]},
                followups_triage_launch_receipt_overrides={
                    "triage_mode": "range",
                    "command": range_command,
                    "manual_decision_ref": manual_ref,
                    "dry_run": {
                        "append_new": 0,
                        "merge_source": 0,
                        "possible_duplicate": 0,
                        "route_fallback": 0,
                        "unparsed_bullets": 0,
                    },
                    "apply": {
                        "append_new": 0,
                        "merge_source": 0,
                        "possible_duplicate": 0,
                        "route_fallback": 0,
                        "unparsed_bullets": 0,
                    },
                    "idempotency_apply": {
                        "append_new": 0,
                        "merge_source": 0,
                        "possible_duplicate": 0,
                        "route_fallback": 0,
                        "unparsed_bullets": 1,
                    },
                },
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "ok")

    def test_ready_to_push_operational_receipt_rejects_reconciliation_ref_mismatch(self) -> None:
        records = self._operational_step_records()
        range_ref = f"{BASE}..{HEAD}"
        range_command = (
            f"planveyor_followups_triage --range {range_ref} --dry-run; "
            f"planveyor_followups_triage --range {range_ref} --apply; "
            f"planveyor_followups_triage --range {range_ref} --apply; "
            "scripts/followups_index_rebuild.py --project-root ."
        )
        manual_ref = "docs/reviews/260505_1200_plan_harvest_range_aaaaaaa_bbbbbbb.md#manual-followups-decision"
        other_ref = "docs/reviews/260505_1201_plan_harvest_range_aaaaaaa_bbbbbbb.md#manual-followups-decision"
        for record in records:
            if record["step"] == "followups_triage_launch":
                record["command"] = range_command
                record["count_summary"] = str(record["count_summary"]).replace(
                    "triage_mode=file",
                    "triage_mode=range",
                )
                record["count_summary"] += (
                    "; dry_run_unparsed_bullets=0; apply_unparsed_bullets=0; "
                    f"idempotency_unparsed_bullets=1; manual_decision_ref={manual_ref}"
                )
                break
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [ ] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(
                root,
                record_overrides={"followups_triage_launch": records[6]},
                followups_triage_launch_receipt_overrides={
                    "triage_mode": "range",
                    "command": range_command,
                    "manual_decision_ref": manual_ref,
                    "dry_run": {
                        "append_new": 0,
                        "merge_source": 0,
                        "possible_duplicate": 0,
                        "route_fallback": 0,
                        "unparsed_bullets": 0,
                    },
                    "apply": {
                        "append_new": 0,
                        "merge_source": 0,
                        "possible_duplicate": 0,
                        "route_fallback": 0,
                        "unparsed_bullets": 0,
                    },
                    "idempotency_apply": {
                        "append_new": 0,
                        "merge_source": 0,
                        "possible_duplicate": 0,
                        "route_fallback": 0,
                        "unparsed_bullets": 1,
                    },
                },
                followups_lane_reconciliation_overrides={"manual_decision_ref": other_ref},
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertTrue(
            any(
                "followups_lane_reconciliation.manual_decision_ref must match"
                in error["detail"]
                for error in payload["errors"]
            )
        )

    def test_ready_to_push_file_mode_fails_when_range_memory_inbox_is_in_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [ ] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(root)

            with mock.patch.object(
                MODULE,
                "_range_diff_candidates",
                return_value=(["docs/followups/260505_1200_followups_memory_fixture.md"], None),
            ):
                payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertTrue(
            any("triage_mode=file is insufficient while range followup inbox obligations exist" in error["detail"] for error in payload["errors"])
        )

    def test_ready_to_push_completed_new_receipt_requires_terminal_closeout_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [x] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(
                root,
                generated_at="2026-06-07T11:30:00+00:00",
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertIn("missing_required_receipt", {error["code"] for error in payload["errors"]})
        self.assertTrue(any("ready_to_push_terminal_proof" in error["detail"] for error in payload["errors"]))
        self.assertEqual(payload["ready_to_push_terminal_proof"]["state"], "missing_required")

    def test_ready_to_push_completed_new_receipt_with_terminal_closeout_receipt_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [x] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(
                root,
                generated_at="2026-06-07T11:30:00+00:00",
            )
            receipt_path = self._write_ready_to_push_closeout_receipt(root)
            risk_packet_path = self._write_range_review_risk_packet(root, receipt_path)
            self._commit_all(root, "terminal closeout receipt")

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["ready_to_push_terminal_proof"]["state"], "terminal_ready_to_push_proof")
        self.assertEqual(payload["ready_to_push_terminal_proof"]["path"], receipt_path)
        self.assertEqual(payload["risk_packet_state"]["state"], "ok")
        self.assertEqual(payload["risk_packet_state"]["packet_path"], risk_packet_path)
        closeout_artifacts = [
            artifact
            for artifact in payload["artifacts"]
            if artifact["kind"] == "ready_to_push_closeout_receipt"
        ]
        self.assertEqual(len(closeout_artifacts), 1)
        self.assertEqual(closeout_artifacts[0]["path"], receipt_path)
        self.assertEqual(closeout_artifacts[0]["git_state"], "clean")
        terminal_receipts = [
            receipt
            for receipt in payload["substep_receipts"]
            if receipt["receipt"] == "ready_to_push_terminal_proof"
        ]
        self.assertEqual(len(terminal_receipts), 1)
        self.assertTrue(terminal_receipts[0]["present"])

    def test_current_shaped_serialized_risk_packet_blocks_merge_report_readback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [x] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(
                root,
                generated_at="2026-06-07T11:30:00+00:00",
            )
            receipt_path = self._write_ready_to_push_closeout_receipt(root)
            self._write_range_review_risk_packet(
                root,
                receipt_path,
                target_snapshot="BUNDLE=current",
            )
            self._commit_all(root, "current shaped terminal risk packet")

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["risk_packet_state"]["state"], "invalid")
        self.assertIn("risk_packet_target_mismatch", {error["code"] for error in payload["errors"]})

    def test_ready_to_push_completed_new_receipt_requires_risk_packet(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [x] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(
                root,
                generated_at="2026-06-07T11:30:00+00:00",
            )
            self._write_ready_to_push_closeout_receipt(root)
            self._commit_all(root, "terminal closeout receipt without risk packet")

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["risk_packet_state"]["state"], "missing")
        self.assertIn("missing_risk_packet", {error["code"] for error in payload["errors"]})

    def test_ready_to_push_terminal_closeout_receipt_rejects_pending_tracker_tick_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [x] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(
                root,
                generated_at="2026-06-07T11:30:00+00:00",
            )
            self._write_ready_to_push_closeout_receipt(
                root,
                overrides={
                    "tracker_tick": {
                        "intent": "tick step:ready_to_push after successful local commit",
                        "result": "pending_until_helper_success",
                    }
                },
            )
            self._commit_all(root, "pending terminal receipt")

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertIn("inconsistent_receipt", {error["code"] for error in payload["errors"]})
        self.assertTrue(
            any("pending_until_helper_success unsupported" in error["detail"] for error in payload["errors"])
        )

    def test_ready_to_push_terminal_closeout_receipt_rejects_expected_pending_final_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [x] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(
                root,
                generated_at="2026-06-07T11:30:00+00:00",
            )
            self._write_ready_to_push_closeout_receipt(
                root,
                overrides={"final_bundle_status": "expected_pending_receipt"},
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertIn("inconsistent_receipt", {error["code"] for error in payload["errors"]})
        self.assertTrue(
            any("expected_pending_receipt" in error["detail"] for error in payload["errors"])
        )

    def test_ready_to_push_terminal_closeout_receipt_range_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [x] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(
                root,
                generated_at="2026-06-07T11:30:00+00:00",
            )
            self._write_ready_to_push_closeout_receipt(root, overrides={"head": "c" * 40})

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertIn("inconsistent_receipt", {error["code"] for error in payload["errors"]})
        self.assertTrue(any("head=" in error["detail"] for error in payload["errors"]))

    def test_ready_to_push_operational_receipt_accepts_wrapper_row_with_canonical_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [ ] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(
                root,
                record_overrides={
                    "docs_hygiene_suggest": {
                        "command": "planveyor_post_merge_docs_hygiene_suggest_gate",
                    }
                },
                docs_hygiene_suggest_summary_overrides={
                    "gate_command": "planveyor_post_merge_docs_hygiene_suggest_gate",
                },
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "ok")
        self.assertNotIn("inconsistent_receipt", {error["code"] for error in payload["errors"]})

    def test_ready_to_push_operational_receipt_missing_archive_snapshot_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [ ] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(root, omit_archive_snapshot=True)

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertIn("inconsistent_receipt", {error["code"] for error in payload["errors"]})
        self.assertTrue(any("archive_snapshot must be an object" in error["detail"] for error in payload["errors"]))

    def test_ready_to_push_operational_receipt_missing_archive_export_proof_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [ ] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(
                root,
                archive_snapshot=self._archive_snapshot_receipt(
                    export_command="N/A (why=validate-only)",
                    source="planveyor_docs_archive_snapshot_validate + planveyor_docs_archive_snapshot_restore",
                ),
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertIn("inconsistent_receipt", {error["code"] for error in payload["errors"]})
        self.assertTrue(any("archive_snapshot ok status requires export_command" in error["detail"] for error in payload["errors"]))
        self.assertTrue(any("archive_snapshot ok status requires source to include export" in error["detail"] for error in payload["errors"]))

    def test_ready_to_push_operational_receipt_stale_archive_snapshot_after_archive_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [ ] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(
                root,
                archive_snapshot=self._archive_snapshot_receipt(
                    snapshot_created_at_utc="2026-05-15T23:59:59+00:00",
                ),
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertTrue(
            any(
                "archive_snapshot stale: snapshot_created_at_utc is older than docs_hygiene_archive.captured_at"
                in error["detail"]
                for error in payload["errors"]
            )
        )

    def test_ready_to_push_operational_receipt_missing_docs_hygiene_summary_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [ ] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(root, omit_docs_hygiene_suggest_summary=True)

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertIn("inconsistent_receipt", {error["code"] for error in payload["errors"]})
        self.assertTrue(
            any("docs_hygiene_suggest_summary must be an object" in error["detail"] for error in payload["errors"])
        )

    def test_ready_to_push_operational_receipt_missing_followups_launch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [ ] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(root, omit_followups_triage_launch_receipt=True)

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertIn("inconsistent_receipt", {error["code"] for error in payload["errors"]})
        self.assertTrue(
            any("followups_triage_launch_receipt must be an object" in error["detail"] for error in payload["errors"])
        )

    def test_ready_to_push_operational_receipt_missing_pi_open_summary_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [ ] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(
                root,
                omit_process_improvements_open_summary=True,
                generated_at="2026-06-06T20:43:00+00:00",
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertTrue(
            any("process_improvements_open_summary must be an object" in error["detail"] for error in payload["errors"])
        )

    def test_ready_to_push_operational_receipt_allows_no_open_pi_zero_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [ ] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(
                root,
                process_improvements_open_summary_overrides={
                    "counts_by_raw_status": {"open": 0, "triaged": 0, "promoted": 0},
                    "null_execution_rows": 0,
                    "owner_or_next_step": "none (no open/triaged/promoted process-improvement rows)",
                },
                generated_at="2026-06-06T20:43:00+00:00",
            )
            self._write(
                root,
                f"docs/reviews/260505_1200_plan_harvest_range_{B7}_{H7}.md",
                dedent(
                    f"""\
                    # Plan harvest

                    **Status:** ✅ Done

                    ## Follow-up harvest triage/import receipt
                    | command | mode | append_new | merge_source | possible_duplicate | route_fallback | result |
                    | --- | --- | ---: | ---: | ---: | ---: | --- |
                    | `planveyor_followups_triage --file docs/followups/260505_1200_followups_range_{B7}_{H7}.md --dry-run` | dry-run | 2 | 0 | 0 | 0 | dry-run only |
                    | `planveyor_followups_triage --file docs/followups/260505_1200_followups_range_{B7}_{H7}.md --apply` | apply | 2 | 0 | 0 | 0 | imported |
                    | `scripts/followups_index_rebuild.py --project-root .` | rebuild | 0 | 0 | 0 | 0 | index updated |

                    ## Process-improvement promotion decisions
                    - `N/A (why=no open/triaged/promoted process-improvement rows in range)`
                    """
                ),
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "ok")
        self.assertFalse(
            any("process_improvements_open_summary source missing summary line" in error["detail"] for error in payload["errors"])
        )

    def test_ready_to_push_operational_receipt_rejects_bullet_open_pi_zero_summary_without_source_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [ ] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(
                root,
                process_improvements_open_summary_overrides={
                    "counts_by_raw_status": {"open": 0, "triaged": 0, "promoted": 0},
                    "null_execution_rows": 0,
                    "owner_or_next_step": "none (no open/triaged/promoted process-improvement rows)",
                },
                generated_at="2026-06-06T20:43:00+00:00",
            )
            self._write(
                root,
                f"docs/reviews/260505_1200_plan_harvest_range_{B7}_{H7}.md",
                dedent(
                    f"""\
                    # Plan harvest

                    **Status:** ✅ Done

                    ## Follow-up harvest triage/import receipt
                    | command | mode | append_new | merge_source | possible_duplicate | route_fallback | result |
                    | --- | --- | ---: | ---: | ---: | ---: | --- |
                    | `planveyor_followups_triage --file docs/followups/260505_1200_followups_range_{B7}_{H7}.md --dry-run` | dry-run | 0 | 0 | 0 | 0 | dry-run only |
                    | `planveyor_followups_triage --file docs/followups/260505_1200_followups_range_{B7}_{H7}.md --apply` | apply | 0 | 0 | 0 | 0 | no file changes |
                    | `scripts/followups_index_rebuild.py --project-root .` | rebuild | 0 | 0 | 0 | 0 | index updated |

                    ## Process-improvement promotion decisions
                    - Detected open raw rows, but this harvest keeps them in the PI lane:
                      - source_ref=`docs/plans/260517_1310_process_pending_followups_decision_wave.md`; entry_id=`PI-001`; raw_status=`open`; execution_kind=`null`; execution_ref=`null`; owner_or_next_step=`Planner triage in process-improvement promotion lane`.
                    """
                ),
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertTrue(
            any("process_improvements_open_summary source missing summary line" in error["detail"] for error in payload["errors"])
        )

    def test_ready_to_push_operational_receipt_malformed_pi_open_summary_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [ ] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(
                root,
                process_improvements_open_summary_overrides={
                    "lane_status": "merged",
                    "counts_by_raw_status": {"open": "two", "triaged": 0, "promoted": 0},
                },
                generated_at="2026-06-06T20:43:00+00:00",
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertTrue(
            any("process_improvements_open_summary.lane_status must be separate" in error["detail"] for error in payload["errors"])
        )
        self.assertTrue(
            any("counts_by_raw_status.open must be a non-negative integer" in error["detail"] for error in payload["errors"])
        )

    def test_ready_to_push_operational_receipt_prose_only_followups_source_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [ ] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(root)
            self._write(
                root,
                f"docs/reviews/260505_1200_plan_harvest_range_{B7}_{H7}.md",
                "# Plan harvest\n\n**Status:** ✅ Done\n\n## Notes\n- Followups handled by prose.\n",
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertTrue(
            any("followups_triage_launch_receipt source missing token" in error["detail"] for error in payload["errors"])
        )

    def test_ready_to_push_legacy_committed_operational_receipt_without_docs_hygiene_summary_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [x] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(root, omit_docs_hygiene_suggest_summary=True)
            self._commit_all(root, "legacy operational receipt")

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "ok")
        self.assertNotIn("inconsistent_receipt", {error["code"] for error in payload["errors"]})

    def test_ready_to_push_new_committed_operational_receipt_without_docs_hygiene_summary_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [x] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(
                root,
                omit_docs_hygiene_suggest_summary=True,
                generated_at="2026-05-19T11:31:00+00:00",
            )
            self._commit_all(root, "new operational receipt missing docs hygiene summary")

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertTrue(
            any("docs_hygiene_suggest_summary must be an object" in error["detail"] for error in payload["errors"])
        )

    def test_ready_to_push_legacy_committed_operational_receipt_without_pi_open_summary_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [x] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(
                root,
                omit_process_improvements_open_summary=True,
                generated_at="2026-06-06T20:41:00+00:00",
            )
            self._commit_all(root, "legacy operational receipt without pi summary")

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "ok")
        self.assertNotIn("inconsistent_receipt", {error["code"] for error in payload["errors"]})

    def test_ready_to_push_legacy_committed_operational_receipt_without_archive_snapshot_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [x] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(root, omit_archive_snapshot=True)
            self._commit_all(root, "legacy operational receipt")

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "ok")
        self.assertNotIn("inconsistent_receipt", {error["code"] for error in payload["errors"]})

    def test_ready_to_push_legacy_committed_operational_receipt_with_old_schema_archive_snapshot_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [x] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(
                root,
                archive_snapshot=self._old_schema_archive_snapshot_receipt(),
                generated_at="2026-05-24T15:14:30+00:00",
            )
            self._commit_all(root, "legacy operational receipt with old archive snapshot schema")

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "ok")
        self.assertNotIn("inconsistent_receipt", {error["code"] for error in payload["errors"]})

    def test_ready_to_push_new_committed_operational_receipt_with_old_schema_archive_snapshot_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [x] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(
                root,
                archive_snapshot=self._old_schema_archive_snapshot_receipt(),
                generated_at="2026-06-07T09:31:00+00:00",
            )
            self._commit_all(root, "new operational receipt with old archive snapshot schema")

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertTrue(
            any(
                "archive_snapshot missing field(s): export_command, export_status, snapshot_created_at_utc, "
                "snapshot_source_db_sha256, snapshot_source_docs_count" in error["detail"]
                for error in payload["errors"]
            )
        )

    def test_ready_to_push_legacy_committed_operational_receipt_with_offset_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [x] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(
                root,
                omit_archive_snapshot=True,
                generated_at="2026-05-18T22:00:00+03:00",
            )
            self._commit_all(root, "legacy operational receipt with offset")

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "ok")
        self.assertNotIn("inconsistent_receipt", {error["code"] for error in payload["errors"]})

    def test_ready_to_push_new_committed_operational_receipt_without_archive_snapshot_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [x] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(
                root,
                omit_archive_snapshot=True,
                generated_at="2026-05-18T20:00:00+00:00",
            )
            self._commit_all(root, "new operational receipt missing archive snapshot")

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertTrue(any("archive_snapshot must be an object" in error["detail"] for error in payload["errors"]))

    def test_ready_to_push_operational_receipt_no_op_snapshot_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [ ] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(
                root,
                archive_snapshot=self._archive_snapshot_receipt(
                    status="no_op",
                    storage_backend="N/A (why=no selected backend for range)",
                    manifest_path="N/A (why=no archive candidates for current range)",
                    artifact_path="N/A (why=no archive candidates for current range)",
                    object_uri="N/A (why=no archive candidates for current range)",
                    checksum="N/A (why=no archive candidates for current range)",
                    access_status="not_required",
                    restore_status="no_op",
                    readback_status="no_op",
                    no_op_reason="no_archive_candidates_for_current_range",
                    blocker_reason="N/A (why=none)",
                ),
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["archive_snapshot"]["status"], "no_op")
        self.assertNotIn("inconsistent_receipt", {error["code"] for error in payload["errors"]})

    def test_ready_to_push_operational_receipt_selected_s3_missing_access_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [ ] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(
                root,
                archive_snapshot=self._archive_snapshot_receipt(
                    status="blocked",
                    storage_backend="s3_minio_sqlite",
                    artifact_path="N/A (why=object-store backend)",
                    object_uri="s3://docs-archive/current/archive.sqlite",
                    access_status="blocked",
                    restore_status="blocked",
                    readback_status="blocked",
                    no_op_reason="N/A (why=not no-op)",
                    blocker_reason="object_access_failed",
                ),
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertTrue(any("archive_snapshot blocked: object_access_failed" in error["detail"] for error in payload["errors"]))

    def test_ready_to_push_operational_receipt_checksum_mismatch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [ ] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(
                root,
                archive_snapshot=self._archive_snapshot_receipt(
                    status="blocked",
                    restore_status="blocked",
                    readback_status="blocked",
                    no_op_reason="N/A (why=not no-op)",
                    blocker_reason="checksum_mismatch",
                ),
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertTrue(any("archive_snapshot blocked: checksum_mismatch" in error["detail"] for error in payload["errors"]))

    def test_docs_hygiene_suggest_gate_auto_ticks_parseable_report_without_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_docs_hygiene_suggest_gate_fixture(root)

            result = self._run_docs_hygiene_suggest_gate(root)
            tracker_text = (root / ".planveyor.merge_tracker.md").read_text(encoding="utf-8")
            git_status = subprocess.run(
                ["git", "-C", str(root), "status", "--short"],
                text=True,
                capture_output=True,
                check=False,
            ).stdout

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[x] step:docs_hygiene_suggest", tracker_text)
        self.assertIn("[ ] step:ready_to_push", tracker_text)
        self.assertIn("suggested git rm was not executed", result.stdout)
        self.assertNotIn("D  docs/plans/260505_1200_done_plan.md", git_status)
        self.assertNotIn(" D docs/plans/260505_1200_done_plan.md", git_status)

    def test_docs_hygiene_suggest_gate_blocks_malformed_output_without_tick(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_docs_hygiene_suggest_gate_fixture(root)

            result = self._run_docs_hygiene_suggest_gate(
                root,
                override='planveyor_docs_hygiene_suggest() { echo "[planveyor] Range: fake"; echo "malformed"; return 0; }',
            )
            tracker_text = (root / ".planveyor.merge_tracker.md").read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 2)
        self.assertIn("[ ] step:docs_hygiene_suggest", tracker_text)
        self.assertIn("missing parse markers", result.stderr)
        self.assertIn('planveyor_docs_hygiene_suggest --range "$(planveyor_range_base)..$(planveyor_range_head)"', result.stderr)

    def test_docs_hygiene_suggest_gate_blocks_nonzero_report_without_tick(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._write_docs_hygiene_suggest_gate_fixture(root)

            result = self._run_docs_hygiene_suggest_gate(
                root,
                override='planveyor_docs_hygiene_suggest() { echo "boom" >&2; return 7; }',
            )
            tracker_text = (root / ".planveyor.merge_tracker.md").read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 7)
        self.assertIn("[ ] step:docs_hygiene_suggest", tracker_text)
        self.assertIn("command exited 7", result.stderr)
        self.assertIn('planveyor_docs_hygiene_suggest --range "$(planveyor_range_base)..$(planveyor_range_head)"', result.stderr)

    def test_operational_receipt_writer_creates_schema_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [ ] step:ready_to_push
                    """
                ),
            )
            cmd = [
                sys.executable,
                "-B",
                str(OPERATIONAL_RECEIPT_HELPER_PATH),
                "--repo-root",
                str(root),
                "--print-path",
            ]
            for record in self._operational_step_records():
                cmd.extend(["--record-json", json.dumps(record)])
            cmd.extend(["--archive-snapshot-json", json.dumps(self._archive_snapshot_receipt())])
            self._write(
                root,
                ".tmp/docs_hygiene_suggest.md",
                dedent(
                    f"""\
                    [planveyor] Range: {BASE}..{HEAD}

                    [planveyor] Terminal plans in range (`Done` + `Superseded`) (1):
                      - docs/plans/260505_1200_done_plan.md

                    [planveyor] REQUIRED before any git rm: archive temp docs into the central SQLite archive:
                      python3 scripts/docs_hygiene_archive.py --range {BASE}..{HEAD} --apply

                    [planveyor] Suggested (Owner) command:
                      git rm -r \\
                        docs/plans/260505_1200_done_plan.md \\
                      # (copy, then remove trailing backslash on the last line)
                    """
                ),
            )
            self._write_followups_harvest_source(root)

            result = subprocess.run(cmd, text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            receipt_path = result.stdout.strip()
            self.assertRegex(
                receipt_path,
                rf"^docs/reviews/\d{{6}}_\d{{4}}_post_merge_operational_receipt_range_{B7}_{H7}\.md$",
            )
            receipt_file = root / receipt_path
            self.assertTrue(receipt_file.is_file())
            receipt_payload = json.loads(receipt_file.read_text(encoding="utf-8").split("```json", 1)[1].split("```", 1)[0])
            self.assertEqual(receipt_payload["receipt_path"], receipt_path)
            snapshot = self._archive_snapshot_receipt()
            self._write(root, "docs/_meta/archive_snapshots/current/archived_docs.jsonl", "artifact fixture\n")
            self._write(
                root,
                "docs/_meta/archive_snapshots/current/manifest.json",
                json.dumps(
                    {
                        "snapshot_manifest_version": snapshot["format_version"],
                        "storage_backend": snapshot["storage_backend"],
                        "created_at_utc": snapshot["snapshot_created_at_utc"],
                        "artifact": {
                            "path": "archived_docs.jsonl",
                            "sha256": snapshot["checksum"],
                            "record_count": int(str(snapshot["snapshot_source_docs_count"])),
                        },
                        "source_db": {
                            "db_sha256": snapshot["snapshot_source_db_sha256"],
                            "docs_count": int(str(snapshot["snapshot_source_docs_count"])),
                        },
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
            )
            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(
            [artifact["path"] for artifact in payload["artifacts"] if artifact["kind"] == "post_merge_operational_receipt"],
            [receipt_path],
        )
        self.assertNotIn("inconsistent_receipt", {error["code"] for error in payload["errors"]})

    def test_ready_to_push_token_only_operational_receipt_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [ ] step:ready_to_push
                    """
                ),
            )
            self._write_token_only_operational_receipt_artifact(root)

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertIn("inconsistent_receipt", {error["code"] for error in payload["errors"]})
        self.assertTrue(any("malformed/token-only" in error["detail"] for error in payload["errors"]))

    def test_ready_to_push_malformed_operational_receipt_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [ ] step:ready_to_push
                    """
                ),
            )
            self._write_malformed_operational_receipt_artifact(root)

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertIn("inconsistent_receipt", {error["code"] for error in payload["errors"]})

    def test_ready_to_push_operational_receipt_missing_no_op_reason_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [ ] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(root, omit_field=("retrieval_metrics", "no_op_reason"))

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertIn("inconsistent_receipt", {error["code"] for error in payload["errors"]})
        self.assertTrue(any("retrieval_metrics: missing field(s): no_op_reason" in error["detail"] for error in payload["errors"]))

    def test_ready_to_push_operational_receipt_allowed_docs_index_no_op_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [ ] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(
                root,
                record_overrides={
                    "docs_index_context": {
                        "command": "N/A (why=no docs/followups delta)",
                        "result": "skipped",
                        "artifact_path": "N/A (why=no docs/followups delta)",
                        "count_summary": "N/A (why=no docs/followups delta)",
                        "no_op_reason": "not_applicable_no_docs_or_followups_delta",
                        "in_scope": "no",
                    }
                },
                generated_at="2026-05-19T08:00:00+00:00",
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "ok")
        self.assertNotIn("inconsistent_receipt", {error["code"] for error in payload["errors"]})

    def test_ready_to_push_operational_receipt_generic_docs_index_no_op_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [ ] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(
                root,
                record_overrides={
                    "docs_index_context": {
                        "command": "N/A (why=legacy profile skip)",
                        "result": "skipped",
                        "artifact_path": "N/A (why=legacy profile skip)",
                        "count_summary": "N/A (why=legacy profile skip)",
                        "no_op_reason": "not_applicable_repo_profile_no_separate_docs_index_context_gate",
                        "in_scope": "no",
                    }
                },
                generated_at="2026-05-19T08:00:00+00:00",
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertTrue(any("docs_index_context: no_op_reason must be one of" in error["detail"] for error in payload["errors"]))

    def test_ready_to_push_operational_receipt_incomplete_docs_index_row_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [ ] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(
                root,
                record_overrides={
                    "docs_index_context": {
                        "count_summary": "plans_total=1; plans_covered=1; plans_uncovered=0; canon_state=advisory"
                    }
                },
                generated_at="2026-05-19T08:00:00+00:00",
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertTrue(any("docs_index_context: count_summary missing field(s)" in error["detail"] for error in payload["errors"]))

    def test_ready_to_push_operational_receipt_low_retrieval_without_triage_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [ ] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(
                root,
                record_overrides={
                    "retrieval_metrics": {
                        "count_summary": (
                            "query_total=100; evaluated_total=10; outcome_evaluated_rate=0.10; "
                            "read_log_status=present; read_events_total=1; read_open_rate=0.01; "
                            "used_for_decision=true"
                        )
                    }
                },
                generated_at="2026-05-19T08:00:00+00:00",
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertTrue(any("retrieval_metrics: low coverage requires follow_up_ref or accepted_no_op_reason" in error["detail"] for error in payload["errors"]))

    def test_ready_to_push_operational_receipt_telemetry_only_low_retrieval_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [ ] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(
                root,
                record_overrides={
                    "retrieval_metrics": {
                        "count_summary": (
                            "query_total=100; evaluated_total=10; outcome_evaluated_rate=0.10; "
                            "read_log_status=present; read_events_total=1; read_open_rate=0.01; "
                            "used_for_decision=false; accepted_no_op_reason=not_used_for_decision"
                        )
                    }
                },
                generated_at="2026-05-19T08:00:00+00:00",
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "ok")
        self.assertNotIn("inconsistent_receipt", {error["code"] for error in payload["errors"]})

    def test_ready_to_push_operational_receipt_telemetry_only_requires_no_op_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [ ] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(
                root,
                record_overrides={
                    "retrieval_metrics": {
                        "count_summary": (
                            "query_total=100; evaluated_total=10; outcome_evaluated_rate=0.10; "
                            "read_log_status=present; read_events_total=1; read_open_rate=0.01; "
                            "used_for_decision=false"
                        )
                    }
                },
                generated_at="2026-05-19T08:00:00+00:00",
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertTrue(
            any(
                "retrieval_metrics: used_for_decision=false requires accepted_no_op_reason=not_used_for_decision"
                in error["detail"]
                for error in payload["errors"]
            )
        )

    def test_ready_to_push_operational_receipt_low_retrieval_with_followup_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [ ] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(
                root,
                record_overrides={
                    "retrieval_metrics": {
                        "count_summary": (
                            "query_total=100; evaluated_total=10; outcome_evaluated_rate=0.10; "
                            "read_log_status=present; read_events_total=1; read_open_rate=0.01; "
                            "used_for_decision=true; "
                            "follow_up_ref=docs/followups/260505_1200_retrieval_quality.md"
                        )
                    }
                },
                generated_at="2026-05-19T08:00:00+00:00",
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "ok")
        self.assertNotIn("inconsistent_receipt", {error["code"] for error in payload["errors"]})

    def test_ready_to_push_operational_receipt_bad_suggest_command_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [ ] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(
                root,
                override_field=("docs_hygiene_suggest", "command", "planveyor_docs_hygiene_suggest"),
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertIn("inconsistent_receipt", {error["code"] for error in payload["errors"]})
        self.assertTrue(any("docs_hygiene_suggest: command must be exact wrapper gate or canonical same-range command" in error["detail"] for error in payload["errors"]))

    def test_ready_to_push_operational_receipt_stale_summary_command_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [ ] step:ready_to_push
                    """
                ),
            )
            stale = f"{'c' * 40}..{HEAD}"
            self._write_operational_receipt_artifact(
                root,
                docs_hygiene_suggest_summary_overrides={
                    "command": f"planveyor_docs_hygiene_suggest --range {stale}",
                    "suggested_owner_rerun_command": f"planveyor_docs_hygiene_suggest --range {stale}",
                },
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertIn("inconsistent_receipt", {error["code"] for error in payload["errors"]})
        self.assertTrue(
            any("docs_hygiene_suggest_summary.command must equal canonical same-range" in error["detail"] for error in payload["errors"])
        )

    def test_ready_to_push_operational_receipt_stale_range_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist=dedent(
                    """\
                    - [x] step:docs_finalize
                    - [x] step:doc_lint
                    - [x] step:docs_hygiene_archive
                    - [x] step:docs_hygiene_suggest
                    - [ ] step:ready_to_push
                    """
                ),
            )
            self._write_operational_receipt_artifact(root, base="c" * 40, head=HEAD)

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertIn("inconsistent_receipt", {error["code"] for error in payload["errors"]})
        self.assertTrue(any("expected=" in error["detail"] for error in payload["errors"]))

    def test_cli_json_exit_code_follows_blocked_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            stdout = io.StringIO()

            with mock.patch("sys.stdout", stdout):
                result = MODULE.main(["--root", str(root), "--format", "json"])

        self.assertEqual(result, 2)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "blocked")
        self.assertIn("missing_range", {error["code"] for error in payload["errors"]})

    def test_shared_canon_change_without_packetization_report_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write(root, "README.md", "seed\n")
            base = self._commit_all(root, "seed")
            self._write(root, "docs/playbooks/post_merge_plan_harvest.md", "# Harvest\n")
            head = self._commit_all(root, "shared canon")
            self._write_custom_range_and_tracker(
                root,
                base=base,
                head=head,
                checklist="- [x] step:ready_to_push\n",
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertIn("missing_packetization_report", {error["code"] for error in payload["errors"]})
        self.assertTrue(payload["packetization_gate"]["required"])

    def test_packetization_report_recipe_prose_does_not_create_structural_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write(root, "README.md", "seed\n")
            base = self._commit_all(root, "seed")
            self._write(root, "docs/playbooks/post_merge_plan_harvest.md", "# Harvest\n")
            head = self._commit_all(root, "shared canon")
            b7 = base[:7]
            h7 = head[:7]
            self._write_custom_range_and_tracker(
                root,
                base=base,
                head=head,
                checklist="- [x] step:packetization_gate\n- [x] step:ready_to_push\n",
            )
            self._write(
                root,
                f"docs/reviews/260511_1000_packetization_gate_range_{b7}_{h7}.md",
                "# Packetization\n\n**Status:** Done\n\ncoverage: missing-packet\n",
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertNotIn("blocking_packetization_rows", {error["code"] for error in payload["errors"]})
        self.assertEqual(payload["packetization_gate"]["report_paths"], [f"docs/reviews/260511_1000_packetization_gate_range_{b7}_{h7}.md"])
        self.assertEqual(payload["packetization_gate"]["active_packetization_report"], f"docs/reviews/260511_1000_packetization_gate_range_{b7}_{h7}.md")
        self.assertEqual(payload["packetization_gate"]["blocking_rows_count"], 0)
        self.assertEqual(payload["packetization_gate"]["blocking_coverages"], [])

    def test_packetization_report_stale_internal_count_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write(root, "README.md", "seed\n")
            base = self._commit_all(root, "seed")
            self._write(root, "docs/playbooks/post_merge_plan_harvest.md", "# Harvest\n")
            head = self._commit_all(root, "shared canon")
            b7 = base[:7]
            h7 = head[:7]
            report_path = f"docs/reviews/260511_1000_packetization_gate_range_{b7}_{h7}.md"
            self._write_custom_range_and_tracker(
                root,
                base=base,
                head=head,
                checklist="- [x] step:packetization_gate\n- [ ] step:docs_finalize\n",
            )
            payload = {
                "packetization_gate": {
                    "range": f"{base}..{head}",
                    "report_path": report_path,
                    "blocking_count": 0,
                    "blocking_rows_count": 0,
                    "created_packets": ["docs/rollout_packets/new_packet.md"],
                    "draft_packets_created_count": 0,
                    "draft_packets_created_paths": ["docs/rollout_packets/new_packet.md"],
                    "rows": [
                        {
                            "changed_file": "docs/playbooks/post_merge_plan_harvest.md",
                            "target_repo": "planveyor",
                            "packet_path": "docs/rollout_packets/existing_packet.md",
                            "packet_status": "open",
                            "target_adoption_state": "awaiting-target-import",
                            "coverage": "covered",
                            "action": "none",
                        }
                    ],
                }
            }
            self._write(
                root,
                report_path,
                "# Packetization\n\n**Status:** Done\n\n## Machine-readable JSON\n```json\n"
                + json.dumps(payload, indent=2)
                + "\n```\n",
            )

            report = MODULE.build_report(root)

        self.assertEqual(report["status"], "blocked")
        self.assertTrue(
            any(
                error["code"] == "stale_receipt_copy"
                and "field=packetization_gate.draft_packets_created_count" in error["detail"]
                and "expected=1; actual=0" in error["detail"]
                and f"source={report_path}" in error["detail"]
                for error in report["errors"]
            )
        )

    def test_packetization_declared_blocking_count_without_row_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write(root, "README.md", "seed\n")
            base = self._commit_all(root, "seed")
            self._write(root, "docs/playbooks/post_merge_plan_harvest.md", "# Harvest\n")
            head = self._commit_all(root, "shared canon")
            b7 = base[:7]
            h7 = head[:7]
            report_path = f"docs/reviews/260511_1000_packetization_gate_range_{b7}_{h7}.md"
            self._write_custom_range_and_tracker(
                root,
                base=base,
                head=head,
                checklist="- [x] step:packetization_gate\n- [ ] step:docs_finalize\n",
            )
            payload = {
                "packetization_gate": {
                    "schema_version": "packetization_gate.v1",
                    "range": f"{base}..{head}",
                    "report_path": report_path,
                    "blocking_count": 0,
                    "blocking_rows_count": 0,
                    "rows": [
                        {
                            "changed_file": "docs/playbooks/post_merge_plan_harvest.md",
                            "target_repo": "planveyor",
                            "packet_path": "docs/rollout_packets/existing_packet.md",
                            "packet_status": "open",
                            "target_adoption_state": "awaiting-target-import",
                            "coverage": "covered",
                            "action": "none",
                        }
                    ],
                    "blocking_coverage_counts": {
                        "covered": 1,
                        "legacy-create-drafts-refused": 0,
                        "missing-packet": 1,
                        "source_only": 0,
                        "unknown_target_mapping": 0,
                    },
                }
            }
            self._write(
                root,
                report_path,
                "# Packetization\n\n**Status:** Done\n\n## Machine-readable JSON\n```json\n"
                + json.dumps(payload, indent=2)
                + "\n```\n",
            )

            report = MODULE.build_report(root)

        self.assertEqual(report["status"], "blocked")
        self.assertTrue(
            any(error["code"] == "blocking_packetization_rows" for error in report["errors"]),
            report["errors"],
        )
        self.assertTrue(
            any(
                error["code"] == "stale_receipt_copy"
                and "field=packetization_gate.blocking_coverage_counts" in error["detail"]
                for error in report["errors"]
            ),
            report["errors"],
        )

    def test_packetization_superseded_history_with_one_active_report_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write(root, "README.md", "seed\n")
            base = self._commit_all(root, "seed")
            self._write(root, "docs/playbooks/post_merge_plan_harvest.md", "# Harvest\n")
            head = self._commit_all(root, "shared canon")
            b7 = base[:7]
            h7 = head[:7]
            self._write_custom_range_and_tracker(
                root,
                base=base,
                head=head,
                checklist="- [x] step:packetization_gate\n- [ ] step:docs_finalize\n",
            )
            self._write(
                root,
                f"docs/reviews/260511_1000_packetization_gate_range_{b7}_{h7}.md",
                "# Packetization\n\n**Status:** Superseded\n\n## Machine-readable JSON\n```json\n"
                + json.dumps(
                    {
                        "packetization_gate": {
                            "report_path": f"docs/reviews/260511_0999_packetization_gate_range_{b7}_{h7}.md",
                            "draft_packets_created_count": 99,
                            "draft_packets_created_paths": [],
                        }
                    },
                    indent=2,
                )
                + "\n```\n",
            )
            active_path = f"docs/reviews/260511_1001_packetization_gate_range_{b7}_{h7}.md"
            active_payload = {
                "packetization_gate": {
                    "schema_version": "packetization_gate.v1",
                    "blocking_count": 0,
                    "blocking_coverages": [],
                    "created_packets": ["docs/rollout_packets/new_packet.md"],
                    "rows": [
                        {
                            "changed_file": "docs/playbooks/post_merge_plan_harvest.md",
                            "target_repo": "planveyor",
                            "packet_path": "docs/rollout_packets/existing_packet.md",
                            "packet_status": "open",
                            "target_adoption_state": "awaiting-target-import",
                            "coverage": "covered",
                            "action": "none",
                        }
                    ],
                }
            }
            self._write(
                root,
                active_path,
                "# Packetization\n\n**Status:** Done\n\n## Machine-readable JSON\n```json\n"
                + json.dumps(active_payload, indent=2)
                + "\n```\n",
            )

            payload = MODULE.build_report(root)
            rendered = MODULE.render_plain(payload)

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["packetization_gate"]["report_paths"], [active_path])
        self.assertEqual(payload["packetization_gate"]["active_packetization_report"], active_path)
        self.assertEqual(
            payload["packetization_gate"]["superseded_packetization_reports"],
            [f"docs/reviews/260511_1000_packetization_gate_range_{b7}_{h7}.md"],
        )
        self.assertEqual(payload["packetization_gate"]["blocking_rows_count"], 0)
        self.assertEqual(payload["packetization_gate"]["blocking_coverages"], [])
        self.assertEqual(payload["packetization_gate"]["schema_version"], "packetization_gate.v1")
        self.assertEqual(payload["packetization_gate"]["draft_packets_created_count"], 1)
        self.assertEqual(
            payload["packetization_gate"]["draft_packets_created_paths"],
            ["docs/rollout_packets/new_packet.md"],
        )
        self.assertEqual(
            payload["packetization_gate"]["draft_packets_reused_paths"],
            ["docs/rollout_packets/existing_packet.md"],
        )
        self.assertIn(f"active_packetization_report: {active_path}", rendered)
        self.assertIn("schema_version: packetization_gate.v1", rendered)
        self.assertIn("superseded_packetization_reports: docs/reviews/260511_1000_packetization_gate_range_", rendered)
        self.assertIn("draft_packets_reused_paths: docs/rollout_packets/existing_packet.md", rendered)
        self.assertNotIn("stale_receipt_copy", {error["code"] for error in payload["errors"]})
        inactive_artifacts = [
            artifact
            for artifact in payload["artifacts"]
            if artifact["kind"] == "packetization_gate" and not artifact["active_candidate"]
        ]
        self.assertEqual(len(inactive_artifacts), 1)

    def test_packetization_current_delivery_readback_reopens_accepted_packets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            base, head, _, changed_file, gate_payload = self._init_current_packetization_fixture(root)
            self._write(root, "docs/rollout_packets/unrelated_packet.md", "# Unrelated packet\n")
            self._write(root, "docs/unrelated.md", "# Unrelated\n")

            hinted = subprocess.run(
                [
                    sys.executable,
                    str(PACKETIZATION_GATE_PATH),
                    "--repo-root",
                    str(root),
                    "--recover",
                    "--range",
                    f"{base[:7]}..{head[:7]}",
                    "--source-plan",
                    "docs/plans/not_in_range.md",
                    "--now",
                    "2026-05-11T10:00:00",
                    "--json",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(hinted.returncode, 0, hinted.stderr)
            hinted_payload = json.loads(hinted.stdout)["packetization_gate"]
            packet_provenance_texts = {
                "consumer": (root / "docs/rollout_packets/consumer_packet.md").read_text(encoding="utf-8"),
                "partner": (root / "docs/rollout_packets/partner_packet.md").read_text(encoding="utf-8"),
            }

            payload = MODULE.build_report(root)
            rendered = MODULE.render_plain(payload)

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(
            payload["packetization_gate"]["report_accepted_packet_paths"],
            [
                "docs/rollout_packets/consumer_packet.md",
                "docs/rollout_packets/partner_packet.md",
            ],
        )
        self.assertEqual(gate_payload["source_artifacts"], self._current_packetization_changed_files)
        self.assertEqual(hinted_payload["source_plan"], "docs/plans/not_in_range.md")
        self.assertEqual(hinted_payload["source_range"], gate_payload["source_range"])
        self.assertEqual(hinted_payload["source_revision"], gate_payload["source_revision"])
        self.assertEqual(hinted_payload["source_artifacts"], gate_payload["source_artifacts"])
        self.assertIn("docs/plans/consumer_packet_provenance.md", packet_provenance_texts["consumer"])
        self.assertIn("docs/plans/partner_packet_provenance.md", packet_provenance_texts["partner"])
        self.assertIn("report_accepted_packet_paths: docs/rollout_packets/consumer_packet.md", rendered)
        self.assertNotIn("inconsistent_packetization_packet", {error["code"] for error in payload["errors"]})
        required_paths = {item["path"] for item in payload["git_status"]["required"]}
        contextual_paths = {item["path"] for item in payload["git_status"]["candidate_contextual"]}
        self.assertTrue(
            {
                "docs/rollout_packets/consumer_packet.md",
                "docs/rollout_packets/partner_packet.md",
            }.issubset(required_paths)
        )
        self.assertTrue(
            {
                "docs/rollout_packets/unrelated_packet.md",
                "docs/unrelated.md",
            }.issubset(contextual_paths)
        )

    def test_packetization_manager_shaped_blocked_to_green_recovery_without_source_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write(root, "README.md", "seed\n")
            base = self._commit_all(root, "seed")
            self._write(root, "docs/plans/260511_1000_process_packetization.md", "# Packetization\n\n**Status:** Done\n")
            self._write(root, "docs/plans/260511_1001_process_unrelated.md", "# Unrelated\n\n**Status:** Done\n")
            changed_file = "docs/process_improvements/manager_recovery__process_improvements_backlog.md"
            self._write_public_current_delivery_backlog(root, changed_file)
            head = self._commit_all(root, "public PI recovery")
            command_prefix = [
                sys.executable,
                str(PACKETIZATION_GATE_PATH),
                "--repo-root",
                str(root),
                "--range",
                f"{base[:7]}..{head[:7]}",
                "--now",
                "2026-05-11T10:00:00",
                "--json",
            ]
            blocked = subprocess.run(command_prefix, text=True, capture_output=True, check=False)
            self.assertEqual(blocked.returncode, 2, blocked.stderr)
            blocked_payload = json.loads(blocked.stdout)["packetization_gate"]
            self.assertEqual(blocked_payload["source_plan"], "N/A (why=report-only range identity has no single source plan)")
            self.assertEqual(blocked_payload["blocking_coverage_counts"]["missing-packet"], 2)

            self._write(
                root,
                "docs/rollout_packets/consumer_packet.md",
                self._current_packet_text(
                    packet_id="260511_1000_consumer_packet",
                    target_repo="consumer-fixture",
                    source_plan="docs/plans/consumer_packet_provenance.md",
                    target_carrier="docs/tools/prompts/manager_collab_merge_pipeline.md",
                ),
            )
            self._write(
                root,
                "docs/rollout_packets/partner_packet.md",
                self._current_packet_text(
                    packet_id="260511_1000_partner_packet",
                    target_repo="partner-fixture",
                    source_plan="docs/plans/partner_packet_provenance.md",
                    target_carrier="docs/tools/prompts/owner_merge_pipeline.md",
                ),
            )
            recovered = subprocess.run(
                [
                    *command_prefix[:6],
                    "--recover",
                    *command_prefix[6:-1],
                    "--packet",
                    "docs/rollout_packets/consumer_packet.md",
                    "--packet",
                    "docs/rollout_packets/partner_packet.md",
                    "--stage-packets",
                    "--json",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(recovered.returncode, 0, recovered.stderr)
            recovered_payload = json.loads(recovered.stdout)["packetization_gate"]
            self.assertEqual(recovered_payload["range"], f"{base}..{head}")
            self.assertEqual(recovered_payload["source_plan"], "N/A (why=range identity has no single source plan)")
            self.assertEqual(recovered_payload["report_accepted_packet_paths"], [
                "docs/rollout_packets/consumer_packet.md",
                "docs/rollout_packets/partner_packet.md",
            ])
            self._write_custom_range_and_tracker(
                root,
                base=base,
                head=head,
                checklist="- [x] step:packetization_gate\n- [ ] step:docs_finalize",
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "ok")
        self.assertNotIn("blocking_packetization_rows", {error["code"] for error in payload["errors"]})
        self.assertNotIn("inconsistent_packetization_packet", {error["code"] for error in payload["errors"]})

    def test_packetization_current_delivery_allows_one_packet_for_aggregate_same_target_partition(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            _, _, _, changed_files, gate_payload = self._init_same_target_multi_file_packetization_fixture(
                root
            )

            payload = MODULE.build_report(root)

        covered_rows = [row for row in gate_payload["rows"] if row["coverage"] == "covered"]
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(gate_payload["source_artifacts"], list(changed_files))
        self.assertEqual(
            gate_payload["report_accepted_packet_paths"],
            ["docs/rollout_packets/partner_packet.md"],
        )
        self.assertEqual(len(gate_payload["target_partitions"]), 1)
        self.assertEqual({row["changed_file"] for row in covered_rows}, set(changed_files))
        self.assertEqual({row["target_repo"] for row in covered_rows}, {"partner-fixture"})
        self.assertEqual(
            {row["packet_path"] for row in covered_rows},
            {"docs/rollout_packets/partner_packet.md"},
        )
        self.assertEqual(
            {tuple(row["target_writable_carriers"]) for row in covered_rows},
            {
                (
                    "docs/tools/prompts/partner_one.md",
                    "docs/tools/prompts/partner_two.md",
                )
            },
        )
        self.assertNotIn("inconsistent_packetization_packet", {error["code"] for error in payload["errors"]})

    def test_packetization_current_delivery_readback_fails_closed_for_packet_or_receipt_drift(self) -> None:
        cases = (
            "stale_revision",
            "missing_packet",
            "untracked_packet",
            "lint_red_packet",
            "unsorted_acceptance",
            "missing_acceptance",
        )
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                _, head, _, _, gate_payload = self._init_current_packetization_fixture(root)
                consumer_packet = root / "docs/rollout_packets/consumer_packet.md"
                report_path = root / str(gate_payload["report_path"])
                if case == "stale_revision":
                    text = consumer_packet.read_text(encoding="utf-8")
                    consumer_packet.write_text(
                        text.replace(f'"source_revision": "{head}"', f'"source_revision": "{"c" * 40}"'),
                        encoding="utf-8",
                    )
                elif case == "missing_packet":
                    consumer_packet.unlink()
                elif case == "untracked_packet":
                    removed = subprocess.run(
                        ["git", "-C", str(root), "rm", "--cached", "--", consumer_packet.relative_to(root).as_posix()],
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                    self.assertEqual(removed.returncode, 0, removed.stderr)
                elif case == "lint_red_packet":
                    text = consumer_packet.read_text(encoding="utf-8")
                    consumer_packet.write_text(
                        text.replace(
                            "- `docs/tools/prompts/manager_collab_merge_pipeline.md`",
                            "- docs/tools/prompts/manager_collab_merge_pipeline.md",
                        ),
                        encoding="utf-8",
                    )
                elif case == "unsorted_acceptance":
                    text = report_path.read_text(encoding="utf-8")
                    start = text.index("```json\n") + len("```json\n")
                    end = text.index("```", start)
                    outer = json.loads(text[start:end])
                    outer["packetization_gate"]["report_accepted_packet_paths"] = list(
                        reversed(outer["packetization_gate"]["report_accepted_packet_paths"])
                    )
                    report_path.write_text(
                        text[:start] + json.dumps(outer, indent=2) + "\n" + text[end:],
                        encoding="utf-8",
                    )
                else:
                    text = report_path.read_text(encoding="utf-8")
                    start = text.index("```json\n") + len("```json\n")
                    end = text.index("```", start)
                    outer = json.loads(text[start:end])
                    outer["packetization_gate"]["report_accepted_packet_paths"] = [
                        "docs/rollout_packets/consumer_packet.md"
                    ]
                    report_path.write_text(
                        text[:start] + json.dumps(outer, indent=2) + "\n" + text[end:],
                        encoding="utf-8",
                    )

                payload = MODULE.build_report(root)

            self.assertEqual(payload["status"], "blocked")
            self.assertIn("inconsistent_packetization_packet", {error["code"] for error in payload["errors"]})

    def test_packetization_current_delivery_requires_exact_target_rows(self) -> None:
        for case in ("missing", "extra", "duplicate"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                _, _, _, changed_file, gate_payload = self._init_current_packetization_fixture(root)
                report_path = root / str(gate_payload["report_path"])
                text = report_path.read_text(encoding="utf-8")
                start = text.index("```json\n") + len("```json\n")
                end = text.index("```", start)
                outer = json.loads(text[start:end])
                gate = outer["packetization_gate"]
                rows = list(gate["rows"])
                partner_row = next(row for row in rows if row["target_repo"] == "partner-fixture")
                if case == "missing":
                    gate["rows"] = [row for row in rows if row is not partner_row]
                    gate["report_accepted_packet_paths"] = [
                        path
                        for path in gate["report_accepted_packet_paths"]
                        if path != "docs/rollout_packets/partner_packet.md"
                    ]
                elif case == "extra":
                    gate["rows"].append(
                        {
                            **partner_row,
                            "changed_file": changed_file,
                            "target_repo": "unexpected-target",
                        }
                    )
                else:
                    gate["rows"].append(dict(partner_row))
                report_path.write_text(
                    text[:start] + json.dumps(outer, indent=2) + "\n" + text[end:],
                    encoding="utf-8",
                )

                payload = MODULE.build_report(root)

            self.assertEqual(payload["status"], "blocked")
            target_errors = [
                error["detail"]
                for error in payload["errors"]
                if error["code"] == "inconsistent_packetization_packet"
            ]
            self.assertTrue(any("target rows" in detail for detail in target_errors), target_errors)

    def test_packetization_unclaimed_current_delivery_diagnostics_are_bounded_and_present_only(self) -> None:
        results = {}
        for extra_rows in (2, 940):
            with self.subTest(extra_rows=extra_rows), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                _, _, _, _, gate_payload = self._init_current_packetization_fixture(root)
                report_path = root / str(gate_payload["report_path"])
                text = report_path.read_text(encoding="utf-8")
                start = text.index("```json\n") + len("```json\n")
                end = text.index("```", start)
                outer = json.loads(text[start:end])
                gate = outer["packetization_gate"]
                rows = [dict(row) for row in gate["rows"]]
                for row in rows:
                    row.update(
                        {
                            "coverage": "missing-packet",
                            "blocking": True,
                            "packet_path": "N/A",
                            "packet_status": "missing",
                            "target_adoption_state": "N/A",
                            "action": "create exact partition packet or fail close",
                        }
                    )
                template_row = dict(rows[0])
                for index in range(extra_rows):
                    rows.append(
                        {
                            **template_row,
                            "changed_file": (
                                "docs/process_improvements/"
                                f"synthetic_{index:04d}__process_improvements_backlog.md"
                            ),
                        }
                    )
                total_rows = len(rows)
                gate["rows"] = rows
                gate["report_accepted_packet_paths"] = []
                gate["draft_packets_reused_paths"] = []
                gate["blocking_count"] = total_rows
                gate["blocking_rows_count"] = total_rows
                gate["blocking_coverages"] = ["missing-packet"]
                gate["blocking_coverage_counts"] = {
                    "missing-packet": total_rows,
                    "unknown_target_mapping": 0,
                }
                report_path.write_text(
                    text[:start] + json.dumps(outer, indent=2) + "\n" + text[end:],
                    encoding="utf-8",
                )

                payload = MODULE.build_report(root)
                rendered = MODULE.render_plain(payload)

            results[extra_rows] = (payload, rendered, str(gate_payload["report_path"]))

        small_payload, small_rendered, _ = results[2]
        large_payload, large_rendered, _ = results[940]
        for extra_rows, payload, rendered, report_path in (
            (2, small_payload, small_rendered, results[2][2]),
            (940, large_payload, large_rendered, results[940][2]),
        ):
            total_rows = extra_rows + 2
            with self.subTest(extra_rows=extra_rows, assertion="present-only-readback"):
                self.assertEqual(payload["status"], "blocked")
                self.assertEqual(payload["packetization_gate"]["blocking_coverages"], ["missing-packet"])
                self.assertEqual(
                    payload["packetization_gate"]["blocking_coverage_counts"],
                    {"missing-packet": total_rows},
                )
                self.assertEqual(
                    len(
                        [
                            error
                            for error in payload["errors"]
                            if error["code"] == "blocking_packetization_rows"
                        ]
                    ),
                    1,
                )
                self.assertEqual(
                    payload["packetization_gate"]["active_packetization_report"], report_path
                )
                self.assertIn(f"active_packetization_report: {report_path}", rendered)
                self.assertIn(f"blocking_coverage_counts: missing-packet={total_rows}", rendered)
                self.assertNotIn("unknown_target_mapping=0", rendered)

        def compact_details(payload: dict[str, object]) -> list[str]:
            return [
                str(error["detail"])
                for error in payload["errors"]
                if error["code"] == "inconsistent_packetization_packet"
                and "unclaimed_empty_accepted" in str(error["detail"])
            ]

        small_compact = compact_details(small_payload)
        large_compact = compact_details(large_payload)
        small_extra = next(detail for detail in small_compact if "category=unexpected_target_rows" in detail)
        large_extra = next(detail for detail in large_compact if "category=unexpected_target_rows" in detail)
        self.assertIn("count=2", small_extra)
        self.assertIn("count=940", large_extra)
        self.assertIn("synthetic_0000", large_extra)
        self.assertIn("synthetic_0002", large_extra)
        self.assertIn("omitted=937", large_extra)
        self.assertNotIn("synthetic_0003", "\n".join(large_compact))
        self.assertNotIn("synthetic_0939", "\n".join(large_compact))
        self.assertLessEqual(len("\n".join(large_compact)), len("\n".join(small_compact)) + 320)
        recovery_details = [detail for detail in large_compact if "recovery_action=" in detail]
        self.assertEqual(len(recovery_details), 1)
        self.assertIn("planveyor_post_merge_packetization_gate_recover", recovery_details[0])
        self.assertIn(recovery_details[0], large_rendered)
        serialized_large = json.dumps(large_payload, sort_keys=True)
        self.assertIn("unclaimed_empty_accepted recovery_action=", serialized_large)
        self.assertIn("planveyor_post_merge_packetization_gate_recover", serialized_large)

    def test_packetization_unclaimed_current_delivery_bounds_real_aggregate_carrier_cardinality(self) -> None:
        results = {}
        for carrier_count in (5, 300):
            with self.subTest(carrier_count=carrier_count), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                self._init_repo(root)
                self._write(root, "README.md", "seed\n")
                base = self._commit_all(root, "seed")
                self._write(
                    root,
                    "docs/plans/260511_1000_process_packetization.md",
                    "# Packetization\n\n**Status:** Done\n",
                )
                carrier_paths = tuple(
                    f"docs/reviews/_template_carrier_{index:04d}.md" for index in range(carrier_count)
                )
                backlog_path = "docs/process_improvements/aggregate_carriers__process_improvements_backlog.md"
                self._write(
                    root,
                    backlog_path,
                    self._pi_backlog_entries_text(
                        [
                            {
                                "entry_id": f"PI-{index + 1:03d}",
                                "status": "triaged",
                                "priority": "P1",
                                "target_canon_path": carrier_path,
                                "target_repo_scope": "consumer-fixture",
                                "delivery_mode": "source_plus_rollout",
                                "execution_kind": "plan",
                                "execution_ref": "docs/plans/aggregate_carriers.md",
                                "delivery_refs": "docs/rollout_packets/aggregate_carriers.md",
                                "triage_note": "literal aggregate carrier delivery",
                            }
                            for index, carrier_path in enumerate(carrier_paths)
                        ]
                    ),
                )
                head = self._commit_all(root, "aggregate public PI carrier range")
                gate = subprocess.run(
                    [
                        sys.executable,
                        str(PACKETIZATION_GATE_PATH),
                        "--repo-root",
                        str(root),
                        "--recover",
                        "--range",
                        f"{base}..{head}",
                        "--now",
                        "2026-05-11T10:00:00",
                        "--json",
                    ],
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(gate.returncode, 2, gate.stderr)
                gate_payload = json.loads(gate.stdout)["packetization_gate"]
                self.assertEqual(len(gate_payload["target_partitions"]), 1)
                self.assertEqual(
                    tuple(gate_payload["target_partitions"][0]["target_writable_carriers"]),
                    carrier_paths,
                )
                self.assertEqual(len(gate_payload["rows"]), carrier_count)
                self._write_custom_range_and_tracker(
                    root,
                    base=base,
                    head=head,
                    checklist="- [x] step:packetization_gate\n- [ ] step:docs_finalize",
                )

                payload = MODULE.build_report(root)
                rendered = MODULE.render_plain(payload)

            results[carrier_count] = (payload, rendered)

        def compact_details(payload: dict[str, object]) -> list[str]:
            return [
                str(error["detail"])
                for error in payload["errors"]
                if error["code"] == "inconsistent_packetization_packet"
                and "unclaimed_empty_accepted" in str(error["detail"])
            ]

        required_categories = (
            "uncovered_or_blocking_target_rows",
            "target_rows_without_accepted_packet",
            "target_partitions_without_single_packet",
        )
        for carrier_count, (payload, rendered) in results.items():
            details = compact_details(payload)
            combined_details = "\n".join(details)
            sample = ",".join(
                f"docs/reviews/_template_carrier_{index:04d}.md"
                for index in range(MODULE.PACKETIZATION_UNCLAIMED_DIAGNOSTIC_SAMPLE_LIMIT)
            )
            self.assertEqual(payload["status"], "blocked")
            self.assertIn(f"carrier_count={carrier_count}", combined_details)
            self.assertIn(f"carrier_sample={sample}", combined_details)
            self.assertIn(
                f"carrier_omitted={carrier_count - MODULE.PACKETIZATION_UNCLAIMED_DIAGNOSTIC_SAMPLE_LIMIT}",
                combined_details,
            )
            self.assertNotIn("_template_carrier_0003.md", combined_details)
            for detail in details:
                self.assertIn(detail, rendered)
            for category in required_categories:
                detail = next(detail for detail in details if f"category={category}" in detail)
                self.assertIn(f"carrier_count={carrier_count}", detail)
                self.assertIn(f"carrier_sample={sample}", detail)
                self.assertIn("count=1" if category == "target_partitions_without_single_packet" else f"count={carrier_count}", detail)

        small_details = "\n".join(compact_details(results[5][0]))
        large_details = "\n".join(compact_details(results[300][0]))
        self.assertNotIn("_template_carrier_0299.md", large_details)
        self.assertLessEqual(len(large_details), len(small_details) + 512)

    def test_packetization_readback_consumers_require_present_only_compact_wording(self) -> None:
        consumer_paths = ("docs/tools/prompts/manager_collab_merge_pipeline.md",)
        required_markers = (
            "present-class-only",
            "`blocking_coverages`",
            "nonzero `blocking_coverage_counts`",
            "compact unclaimed diagnostics",
            "strict claimed-packet validation",
        )
        for rel_path in consumer_paths:
            with self.subTest(path=rel_path):
                text = (REPO_ROOT / rel_path).read_text(encoding="utf-8")
                for marker in required_markers:
                    self.assertIn(marker, text)
                self.assertTrue(
                    "fixed forbidden-vocabulary union" in text
                    or "fixed current-readback union" in text,
                )

    def test_packetization_current_delivery_binds_required_target_rows_to_accepted_packets(self) -> None:
        cases = (
            "wrong_target_reused_packet",
            "source_only_na_substitution",
            "blank_packet_path",
            "nonliteral_packet_target_repo",
            "nonliteral_row_target_repo",
        )
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                _, _, _, _, gate_payload = self._init_current_packetization_fixture(root)
                report_path = root / str(gate_payload["report_path"])
                text = report_path.read_text(encoding="utf-8")
                start = text.index("```json\n") + len("```json\n")
                end = text.index("```", start)
                outer = json.loads(text[start:end])
                gate = outer["packetization_gate"]
                partner_row = next(
                    row for row in gate["rows"] if row["target_repo"] == "partner-fixture"
                )
                if case == "wrong_target_reused_packet":
                    partner_row["packet_path"] = "docs/rollout_packets/consumer_packet.md"
                    gate["report_accepted_packet_paths"] = ["docs/rollout_packets/consumer_packet.md"]
                elif case == "source_only_na_substitution":
                    partner_row["coverage"] = "source_only"
                    partner_row["packet_path"] = "N/A"
                    partner_row["packet_status"] = "N/A"
                    partner_row["target_adoption_state"] = "N/A"
                    gate["report_accepted_packet_paths"] = ["docs/rollout_packets/consumer_packet.md"]
                elif case == "nonliteral_packet_target_repo":
                    consumer_packet = root / "docs/rollout_packets/consumer_packet.md"
                    planveyor_text = consumer_packet.read_text(encoding="utf-8")
                    consumer_packet.write_text(
                        planveyor_text.replace(
                        "**Target repo:** consumer-fixture", "**Target repo:** CONSUMER-FIXTURE"
                    ).replace(
                        '"target_repo": "consumer-fixture"', '"target_repo": "CONSUMER-FIXTURE"'
                    ),
                        encoding="utf-8",
                    )
                elif case == "nonliteral_row_target_repo":
                    partner_row["target_repo"] = "partner-fixture "
                else:
                    partner_row["packet_path"] = ""
                    gate["report_accepted_packet_paths"] = ["docs/rollout_packets/consumer_packet.md"]
                report_path.write_text(
                    text[:start] + json.dumps(outer, indent=2) + "\n" + text[end:],
                    encoding="utf-8",
                )

                payload = MODULE.build_report(root)

            self.assertEqual(payload["status"], "blocked")
            target_errors = [
                error["detail"]
                for error in payload["errors"]
                if error["code"] == "inconsistent_packetization_packet"
            ]
            self.assertTrue(target_errors)
            self.assertFalse(
                any("unclaimed_empty_accepted" in detail for detail in target_errors),
                target_errors,
            )
            if case == "wrong_target_reused_packet":
                self.assertTrue(any("packet_meta.target_repo" in detail for detail in target_errors), target_errors)
                self.assertTrue(
                    any("is reused across target partitions" in detail for detail in target_errors),
                    target_errors,
                )
            elif case == "nonliteral_packet_target_repo":
                self.assertTrue(any("packet_meta.target_repo" in detail for detail in target_errors), target_errors)
            elif case == "nonliteral_row_target_repo":
                self.assertTrue(any("missing expected target rows" in detail for detail in target_errors), target_errors)
            elif case == "source_only_na_substitution":
                self.assertTrue(any("must be covered and non-blocking" in detail for detail in target_errors), target_errors)
                self.assertTrue(any("must name one accepted packet" in detail for detail in target_errors), target_errors)
            else:
                self.assertTrue(any("must name one accepted packet" in detail for detail in target_errors), target_errors)

    def test_packetization_current_delivery_rejects_stale_packet_identity_without_reparsing_source_plan_status(self) -> None:
        cases = {
            "missing_header": "# Packetization\n\n## Evidence\n- no lifecycle status\n",
            "body_decoy": "# Packetization\n\n**Status:** In progress\n\n## Evidence\n**Status:** Done\n",
            "fenced_decoy": (
                "# Packetization\n\n**Status:** In progress\n\n## Evidence\n```md\n**Status:** Done\n```\n"
            ),
            "list_nested_fence": (
                "# Packetization\n\n- ```md\n  **Status:** Done\n  ```\n\n## Evidence\n- nested example\n"
            ),
            "html_comment": "# Packetization\n\n<!--\n**Status:** Done\n-->\n\n## Evidence\n- comment\n",
            "inline_html_comment": "# Packetization\n\nnotes <!--\n**Status:** Done\n-->\n\n## Evidence\n- comment\n",
            "reopened_html_comment": "# Packetization\n\nnotes <!-- closed --> <!--\n**Status:** Done\n-->\n\n## Evidence\n- comment\n",
            "lazy_blockquote": "# Packetization\n\n> quoted example\n**Status:** Done\n\n## Evidence\n- quote\n",
            "indented_blockquote_one": "# Packetization\n\n > quoted example\n**Status:** Done\n\n## Evidence\n- quote\n",
            "indented_blockquote_three": "# Packetization\n\n   > quoted example\n**Status:** Done\n\n## Evidence\n- quote\n",
            "indented_code": "# Packetization\n\n    **Status:** Done\n\n## Evidence\n- code example\n",
            "duplicate_header": "# Packetization\n\n**Status:** Done\n**Status:** Done\n\n## Evidence\n- duplicate\n",
        }
        for case, source_text in cases.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                base, head, source_plan, _, gate_payload = self._init_current_packetization_fixture(root)
                self._write(root, source_plan, source_text)
                staged = subprocess.run(
                    ["git", "-C", str(root), "add", "--", source_plan],
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(staged.returncode, 0, staged.stderr)
                committed = subprocess.run(
                    ["git", "-C", str(root), "commit", "--only", "-m", f"reject {case} source status", "--", source_plan],
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(committed.returncode, 0, committed.stderr)
                updated_head = subprocess.run(
                    ["git", "-C", str(root), "rev-parse", "HEAD"],
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(updated_head.returncode, 0, updated_head.stderr)
                current_head = updated_head.stdout.strip()
                old_range = f"{base}..{head}"
                current_range = f"{base}..{current_head}"
                old_report_rel = str(gate_payload["report_path"])
                current_report_rel = old_report_rel.replace(
                    f"_range_{base[:7]}_{head[:7]}.md",
                    f"_range_{base[:7]}_{current_head[:7]}.md",
                )
                self.assertNotEqual(current_report_rel, old_report_rel)
                old_report = root / old_report_rel
                current_report = root / current_report_rel
                # Retarget the otherwise green receipt to a new commit without restamping
                # packets. Terminal readback must reopen range identity rather than
                # reparsing the source plan's lifecycle prose.
                current_report.parent.mkdir(parents=True, exist_ok=True)
                old_report.replace(current_report)
                report_text = current_report.read_text(encoding="utf-8")
                current_report.write_text(
                    report_text.replace(old_report_rel, current_report_rel)
                    .replace(old_range, current_range)
                    .replace(head, current_head),
                    encoding="utf-8",
                )
                self._write_custom_range_and_tracker(
                    root,
                    base=base,
                    head=current_head,
                    checklist="- [x] step:packetization_gate\n- [ ] step:docs_finalize",
                )
                packet_paths = (
                    root / "docs/rollout_packets/consumer_packet.md",
                    root / "docs/rollout_packets/partner_packet.md",
                )
                before_bytes = {path: path.read_bytes() for path in packet_paths}
                before_index = subprocess.run(
                    ["git", "-C", str(root), "diff", "--cached", "--name-only"],
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(before_index.returncode, 0, before_index.stderr)

                payload = MODULE.build_report(root)

                after_index = subprocess.run(
                    ["git", "-C", str(root), "diff", "--cached", "--name-only"],
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(after_index.returncode, 0, after_index.stderr)
                self.assertEqual(payload["status"], "blocked")
                self.assertIn("inconsistent_packetization_packet", {error["code"] for error in payload["errors"]})
                self.assertTrue(
                    any("packet_meta.source_range" in error["detail"] for error in payload["errors"]),
                    payload["errors"],
                )
                self.assertEqual({path: path.read_bytes() for path in packet_paths}, before_bytes)
                self.assertEqual(after_index.stdout, before_index.stdout)

    def test_packetization_structural_report_without_schema_version_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write(root, "README.md", "seed\n")
            base = self._commit_all(root, "seed")
            self._write(root, "docs/playbooks/post_merge_plan_harvest.md", "# Harvest\n")
            head = self._commit_all(root, "shared canon")
            b7 = base[:7]
            h7 = head[:7]
            self._write_custom_range_and_tracker(
                root,
                base=base,
                head=head,
                checklist="- [x] step:packetization_gate\n- [ ] step:docs_finalize\n",
            )
            report_path = f"docs/reviews/260511_1001_packetization_gate_range_{b7}_{h7}.md"
            self._write(
                root,
                report_path,
                "# Packetization\n\n**Status:** Done\n\n## Machine-readable JSON\n```json\n"
                + json.dumps({"packetization_gate": {"blocking_count": 0, "rows": []}}, indent=2)
                + "\n```\n",
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertIn("missing_packetization_schema_version", {error["code"] for error in payload["errors"]})
        self.assertEqual(
            payload["packetization_gate"]["schema_version"],
            "N/A (why=missing schema_version in structural JSON)",
        )

    def test_packetization_malformed_structural_report_fails_closed(self) -> None:
        cases = {
            "malformed_json": "## Machine-readable JSON\n```json\n{\"packetization_gate\": \n```\n",
            "machine_heading_without_fence": "## Machine-readable JSON\nnot json\n",
            "top_level_list": "## Machine-readable JSON\n```json\n[\"not\", \"an\", \"object\"]\n```\n",
            "nested_gate_list": "## Machine-readable JSON\n```json\n{\"packetization_gate\": []}\n```\n",
        }
        for name, report_body in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir).resolve()
                self._init_repo(root)
                self._write(root, "README.md", "seed\n")
                base = self._commit_all(root, "seed")
                self._write(root, "docs/playbooks/post_merge_plan_harvest.md", "# Harvest\n")
                head = self._commit_all(root, "shared canon")
                b7 = base[:7]
                h7 = head[:7]
                self._write_custom_range_and_tracker(
                    root,
                    base=base,
                    head=head,
                    checklist="- [x] step:packetization_gate\n- [ ] step:docs_finalize\n",
                )
                report_path = f"docs/reviews/260511_1001_packetization_gate_range_{b7}_{h7}.md"
                self._write(
                    root,
                    report_path,
                    f"# Packetization\n\n**Status:** Done\n\n{report_body}",
                )

                payload = MODULE.build_report(root)

            self.assertEqual(payload["status"], "blocked")
            self.assertIn("malformed_packetization_json", {error["code"] for error in payload["errors"]})
            self.assertEqual(
                payload["packetization_gate"]["schema_version"],
                "N/A (why=malformed structural packetization JSON)",
            )

    def test_packetization_duplicate_non_superseded_reports_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write(root, "README.md", "seed\n")
            base = self._commit_all(root, "seed")
            self._write(root, "docs/playbooks/post_merge_plan_harvest.md", "# Harvest\n")
            head = self._commit_all(root, "shared canon")
            b7 = base[:7]
            h7 = head[:7]
            self._write_custom_range_and_tracker(
                root,
                base=base,
                head=head,
                checklist="- [x] step:packetization_gate\n- [ ] step:docs_finalize\n",
            )
            self._write(
                root,
                f"docs/reviews/260511_1000_packetization_gate_range_{b7}_{h7}.md",
                "# Packetization\n\n**Status:** Done\n",
            )
            self._write(
                root,
                f"docs/reviews/260511_1001_packetization_gate_range_{b7}_{h7}.md",
                "# Packetization\n\n**Status:** Done\n",
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertIn("ambiguous_artifact", {error["code"] for error in payload["errors"]})
        self.assertEqual(
            payload["packetization_gate"]["active_packetization_report"],
            "N/A (why=ambiguous active packetization reports)",
        )
        self.assertTrue(
            any(f"260511_1000_packetization_gate_range_{b7}_{h7}.md" in error["detail"] for error in payload["errors"])
        )
        self.assertTrue(
            any(f"260511_1001_packetization_gate_range_{b7}_{h7}.md" in error["detail"] for error in payload["errors"])
        )

    def test_packetization_missing_status_report_remains_active_and_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write(root, "README.md", "seed\n")
            base = self._commit_all(root, "seed")
            self._write(root, "docs/playbooks/post_merge_plan_harvest.md", "# Harvest\n")
            head = self._commit_all(root, "shared canon")
            b7 = base[:7]
            h7 = head[:7]
            self._write_custom_range_and_tracker(
                root,
                base=base,
                head=head,
                checklist="- [x] step:packetization_gate\n- [ ] step:docs_finalize\n",
            )
            self._write(
                root,
                f"docs/reviews/260511_1000_packetization_gate_range_{b7}_{h7}.md",
                "# Packetization\n\n**Status:** Done\n",
            )
            self._write(
                root,
                f"docs/reviews/260511_1001_packetization_gate_range_{b7}_{h7}.md",
                "# Packetization\n\nstatus: Superseded\n",
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertIn("ambiguous_artifact", {error["code"] for error in payload["errors"]})

    def test_large_range_candidate_and_packetization_samples_are_capped(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            base, head = self._seed_many_shared_canon_changes(root, count=25)
            b7 = base[:7]
            h7 = head[:7]
            self._write_custom_range_and_tracker(
                root,
                base=base,
                head=head,
                checklist=dedent(
                    """\
                    - [x] step:packetization_gate
                    - [ ] step:ready_to_push
                    """
                ),
            )
            packetization_report = f"docs/reviews/260511_1000_packetization_gate_range_{b7}_{h7}.md"
            self._write(
                root,
                packetization_report,
                "# Packetization\n\n**Status:** Done\n",
            )

            payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["range_diff_candidates"]["count"], 25)
        self.assertEqual(len(payload["range_diff_candidates"]["sample_paths"]), 20)
        self.assertEqual(payload["range_diff_candidates"]["omitted_count"], 5)
        self.assertTrue(
            all(path.startswith("docs/playbooks/large_range_") for path in payload["range_diff_candidates"]["sample_paths"])
        )
        self.assertTrue(payload["packetization_gate"]["required"])
        self.assertEqual(payload["packetization_gate"]["shared_canon_files_count"], 25)
        self.assertEqual(len(payload["packetization_gate"]["sample_shared_canon_files"]), 20)
        self.assertEqual(payload["packetization_gate"]["source_only_files_count"], 25)
        self.assertEqual(payload["packetization_gate"]["report_paths"], [packetization_report])

    def test_git_status_timeout_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            self._write_custom_range_and_tracker(
                root,
                base=BASE,
                head=HEAD,
                checklist="- [ ] step:ready_to_push\n",
            )
            original_run_git = MODULE._run_git

            def timeout_status(root_arg: Path, *args: str) -> tuple[int, str, str]:
                if args == ("status", "--short", "--untracked-files=all"):
                    return MODULE.GIT_TIMEOUT_RETURN_CODE, "", "git status --short --untracked-files=all timed out after 30s"
                return original_run_git(root_arg, *args)

            with mock.patch.object(MODULE, "_run_git", side_effect=timeout_status):
                payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertIn("git_status_timeout", {error["code"] for error in payload["errors"]})
        self.assertTrue(any("timed out after 30s" in error["detail"] for error in payload["errors"]))

    def test_range_diff_timeout_fails_closed_without_greenwashing_packetization(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            self._init_repo(root)
            base, head = self._seed_many_shared_canon_changes(root, count=25)
            self._write_custom_range_and_tracker(
                root,
                base=base,
                head=head,
                checklist="- [ ] step:ready_to_push\n",
            )
            original_run_git = MODULE._run_git

            def timeout_range_diff(root_arg: Path, *args: str) -> tuple[int, str, str]:
                if args == ("diff", "--name-only", f"{base}..{head}"):
                    return MODULE.GIT_TIMEOUT_RETURN_CODE, "", f"git diff --name-only {base}..{head} timed out after 30s"
                return original_run_git(root_arg, *args)

            with mock.patch.object(MODULE, "_run_git", side_effect=timeout_range_diff):
                payload = MODULE.build_report(root)

        self.assertEqual(payload["status"], "blocked")
        self.assertIn("range_diff_timeout", {error["code"] for error in payload["errors"]})
        self.assertEqual(payload["range_diff_candidates"]["count"], 0)
        self.assertTrue(any("timed out after 30s" in error["detail"] for error in payload["errors"]))

    def test_pending_gate_wording_contract_is_machine_checked(self) -> None:
        contract_paths = ["docs/tools/prompts/manager_collab_merge_pipeline.md"]
        required_tokens = [
            "step:docs_hygiene_suggest",
            "step:ready_to_push",
            "planveyor_post_merge_docs_hygiene_suggest_gate",
            "[planveyor] Range:",
            "[planveyor] Suggested (Owner) command:",
            "already green",
            "pending owner gate",
            "planveyor_merge_bundle_report",
            "planveyor_plan_bundle",
        ]

        combined = ""
        for rel_path in contract_paths:
            text = (REPO_ROOT / rel_path).read_text(encoding="utf-8")
            combined += text + "\n"
            for token in required_tokens:
                self.assertIn(token, text, f"{rel_path} missing {token!r}")

        self.assertIn("canon_sweep", combined)
        self.assertIn("candidate/contextual", combined)
        self.assertNotIn("pending operational cleanup gate", combined)


if __name__ == "__main__":
    unittest.main()

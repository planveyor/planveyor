#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from textwrap import dedent
from unittest import mock


COLLECT_PATH = Path(__file__).with_name("process_improvements_collect.py")
COLLECT_SPEC = importlib.util.spec_from_file_location("process_improvements_collect", COLLECT_PATH)
assert COLLECT_SPEC is not None and COLLECT_SPEC.loader is not None
COLLECT = importlib.util.module_from_spec(COLLECT_SPEC)
sys.modules[COLLECT_SPEC.name] = COLLECT
COLLECT_SPEC.loader.exec_module(COLLECT)

TRIAGE_PATH = Path(__file__).with_name("process_improvements_triage.py")
TRIAGE_SPEC = importlib.util.spec_from_file_location("process_improvements_triage", TRIAGE_PATH)
assert TRIAGE_SPEC is not None and TRIAGE_SPEC.loader is not None
TRIAGE = importlib.util.module_from_spec(TRIAGE_SPEC)
sys.modules[TRIAGE_SPEC.name] = TRIAGE
TRIAGE_SPEC.loader.exec_module(TRIAGE)

LEGACY_DERIVED_BANNER_LINE = (
    "_DO NOT EDIT - regenerate via `PYTHONDONTWRITEBYTECODE=1 "
    "python3 -B scripts/process_improvements_collect.py --project-root . "
    "--rebuild-derived`._"
)


class ProcessImprovementsTests(unittest.TestCase):
    def _general_prompt_lower_samples(self, text: str) -> tuple[str, str]:
        output = text.rsplit("Выход (в чат):", 1)[1]
        section = re.search(
            r"^## (?:\d+\) )?Process improvements\s*\n(?P<body>.*?)(?=^## |\Z)",
            output,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(section)
        assert section is not None
        # Match the complete sample carrier: unknown prose cannot disappear
        # between the two explicitly delimited output alternatives.
        variants = re.fullmatch(
            r"\s*```md\n(?P<structured>.*?)\n```\s*```md\n(?P<noop>.*?)\n```\s*",
            section.group("body"),
            re.DOTALL,
        )
        self.assertIsNotNone(variants, "lower PI output must contain exactly two complete examples")
        assert variants is not None
        replacements = {
            "<N>": "1",
            "<что болит / где loop проявился>": "проверка полного нижнего примера",
            "<какой process/helper/prompt gap surfaced>": "пример расходится со строгим parser",
            "<bounded fix / guardrail>": "проверять весь intended output настоящим parser",
            "<Architect|Planner|Coder|Reviewer|Manager|Owner>": "Architect",
            "<canon_update|prompt_change|helper_change|routing_change|followup_plan>": "prompt_change",
            "<review/blocker/plan/queue ref|unknown>": "docs/code_reviews/fixture.md#B1",
            "<manager-fed plan_ref|unknown>": "docs/plans/fixture.md",
            "<reason_code>": "clean_run",
        }
        samples = []
        for name in ("structured", "noop"):
            sample = variants.group(name)
            for placeholder, value in replacements.items():
                sample = sample.replace(placeholder, value)
            self.assertNotRegex(sample, r"<[^>\n]+>")
            samples.append("## Process improvements\n" + sample + "\n")
        return samples[0], samples[1]

    def test_general_prompt_lower_samples_parse_canonical_and_noop(self) -> None:
        root = Path(__file__).resolve().parents[1]
        for prefix in ("docs/tools/prompts", "copier_template/docs/tools/prompts"):
            for role in ("Architect", "Planner", "Coder", "Reviewer"):
                path = root / prefix / f"{role.lower()}_docs_finalize_general.md"
                with self.subTest(path=path.relative_to(root).as_posix()):
                    structured, noop = self._general_prompt_lower_samples(path.read_text(encoding="utf-8"))
                    parsed = COLLECT.parse_process_improvements_section(
                        structured, role=role, default_source_ref="docs/plans/fixture.md",
                    )
                    self.assertEqual(parsed["state"], "suggestions")
                    self.assertEqual(len(parsed["suggestions"]), 1)
                    self.assertEqual(parsed["suggestions"][0].source_ref, "docs/plans/fixture.md")
                    self.assertEqual(parsed["suggestions"][0].role, role)
                    parsed_noop = COLLECT.parse_process_improvements_section(
                        noop, role=role, default_source_ref="docs/plans/fixture.md",
                    )
                    self.assertEqual(parsed_noop["state"], "no_process_improvements")
                    self.assertEqual(parsed_noop["suggestions"], [])
                    self.assertEqual(parsed_noop["reason_code"], "clean_run")

    def test_general_lower_sample_extraction_never_filters_prose(self) -> None:
        root = Path(__file__).resolve().parents[1]
        text = (root / "docs/tools/prompts/reviewer_docs_finalize_general.md").read_text(encoding="utf-8")
        output_start = text.rindex("Выход (в чат):")
        before, output = text[:output_start], text[output_start:]
        with self.assertRaises(AssertionError):
            self._general_prompt_lower_samples(before + output.replace("```\n\n```md", "```\nextra prose\n```md", 1))
        injected = before + output.replace("- source_ref: <manager-fed plan_ref|unknown>",
                                          "- source_ref: <manager-fed plan_ref|unknown>\nextra prose", 1)
        structured, _ = self._general_prompt_lower_samples(injected)
        with self.assertRaisesRegex(ValueError, "Unsupported line inside `Process improvements`"):
            COLLECT.parse_process_improvements_section(
                structured, role="Reviewer", default_source_ref="docs/plans/fixture.md",
            )

    def test_general_prompt_incident_tail_blocks_without_durable_effect(self) -> None:
        root = self._root()
        source_ref = "docs/plans/fixture.md"
        cycle_id = "2e9f1138-692c-45e7-a24b-4ec2ca1046f1"
        prompt = Path(__file__).resolve().parents[1] / "docs/tools/prompts/coder_docs_finalize_general.md"
        structured, _ = self._general_prompt_lower_samples(prompt.read_text(encoding="utf-8"))
        tail = "Structured suggestion передана для штатного Manager collector; durable PI carrier этой ролью не записан."
        raw_input = (structured + tail + "\n").encode("utf-8")
        self.assertEqual(len(COLLECT.parse_process_improvements_section(
            structured, role="Coder", default_source_ref=source_ref,
        )["suggestions"]), 1)
        with self.assertRaisesRegex(ValueError, "Unsupported line inside `Process improvements`"):
            COLLECT.collect_process_improvements(
                project_root=root, role="Coder", source_ref=source_ref,
                text=raw_input, followups_capture_cycle_id=cycle_id,
            )
        receipt = self._read_receipt(root, source_ref, "Coder", cycle_id)
        self.assertEqual(receipt["receipt_schema"], COLLECT.CAPTURE_RECEIPT_V2_SCHEMA)
        self.assertEqual(receipt["capture_state"], "blocked")
        self.assertEqual(receipt["reason_code"], "collector_error")
        self.assertIn(tail, receipt["error"])
        self.assertEqual(receipt["input_sha256"], hashlib.sha256(raw_input).hexdigest())
        self.assertEqual(receipt["before_process_improvement_files"], {})
        self.assertEqual(receipt["after_process_improvement_files"], {})
        self.assertEqual(receipt["process_improvement_path_results"], [])
        self.assertFalse((root / "docs/process_improvements").exists())

    def _root(self) -> Path:
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        root = Path(tmpdir.name)
        subprocess.run(["git", "init", "--quiet", os.fspath(root)], check=True)
        (root / ".authority-fixture").write_text("fixture\n", encoding="utf-8")
        subprocess.run(["git", "-C", os.fspath(root), "add", ".authority-fixture"], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                os.fspath(root),
                "-c",
                "user.name=Authority Fixture",
                "-c",
                'user.email=' + 'authority-fixture' + '@' + 'example' + '.' + 'invalid',
                "commit",
                "--quiet",
                "-m",
                "fixture",
            ],
            check=True,
        )
        return root

    def _read_receipt(
        self,
        root: Path,
        source_ref: str,
        role: str,
        followups_capture_cycle_id: str | None = None,
    ) -> dict[str, object]:
        path = root / COLLECT.capture_receipt_rel_path(source_ref, role, followups_capture_cycle_id)
        self.assertTrue(path.exists(), path)
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_backlog(
        self,
        root: Path,
        rel_path: str,
        *,
        status: str,
        delivery_refs: str = "null",
        triage_note: str = "parser status-family fixture",
    ) -> Path:
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        source_ref = f"docs/plans/{Path(rel_path).stem}.md"
        path.write_text(
            dedent(
                f"""\
                # Process improvements backlog - fixture

                **Date:** 2026-06-20 00:45 MSK
                **Source ref:** `{source_ref}`
                **Status:** Draft

                ## Suggestions (truth)

                ### PI-001
                - status: `{status}`
                - priority: `P?`
                - role: `Coder`
                - owner: `Architect`
                - promotion_class: `helper_change`
                - target_canon_path: `null`
                - target_repo_scope: `null`
                - delivery_mode: `null`
                - execution_kind: `null`
                - execution_ref: `null`
                - delivery_refs: `{delivery_refs}`
                - handled_ref: `null`
                - promoted_at: `null`
                - handled_at: `null`
                - trigger_ref: `docs/code_reviews/current.md#B1`
                - source_ref: `{source_ref}`
                - symptom: `status families can drift`
                - process_gap: `PI statuses need their own parser contract`
                - suggested_fix: `keep PI statuses out of ordinary followups`
                - created_at: `2026-06-20 00:45 MSK`
                - triage_note: `{triage_note}`
                """
            ),
            encoding="utf-8",
        )
        return path

    def test_parse_backlog_text_matches_file_parser_for_snapshot_consumers(self) -> None:
        root = self._root()
        path = self._write_backlog(
            root,
            "docs/process_improvements/snapshot__process_improvements_backlog.md",
            status="open",
        )
        text = path.read_text(encoding="utf-8")

        parsed_text = COLLECT.parse_backlog_text(text, path=path, project_root=root)
        parsed_file = COLLECT.parse_backlog_file(path, root)

        self.assertEqual(parsed_text, parsed_file)

    def test_parse_backlog_text_keeps_exact_entry_identity_across_target_delta_snapshots(self) -> None:
        root = self._root()
        path = self._write_backlog(
            root,
            "docs/process_improvements/snapshot_delta__process_improvements_backlog.md",
            status="open",
        )
        base_text = path.read_text(encoding="utf-8")
        target_path = "docs/tools/prompts/manager_collab_merge_pipeline.md"
        head_text = (
            base_text.replace("- status: `open`", "- status: `triaged`")
            .replace("- priority: `P?`", "- priority: `P1`")
            .replace("- target_canon_path: `null`", f"- target_canon_path: `{target_path}`")
            .replace("- target_repo_scope: `null`", "- target_repo_scope: `consumer-fixture`")
            .replace("- delivery_mode: `null`", "- delivery_mode: `source_plus_rollout`")
            .replace("- execution_kind: `null`", "- execution_kind: `plan`")
            .replace("- execution_ref: `null`", "- execution_ref: `docs/plans/pi_target.md`")
            .replace("- delivery_refs: `null`", "- delivery_refs: `docs/rollout_packets/pi_target.md`")
            .replace("- triage_note: `parser status-family fixture`", "- triage_note: `target delivery selected`")
        )

        base = COLLECT.parse_backlog_text(base_text, path=path, project_root=root)
        head = COLLECT.parse_backlog_text(head_text, path=path, project_root=root)
        removed = COLLECT.parse_backlog_text(base_text, path=path, project_root=root)

        self.assertEqual([entry.entry_id for entry in base.entries], ["PI-001"])
        self.assertEqual([entry.entry_id for entry in head.entries], ["PI-001"])
        self.assertEqual(head.entries[0].target_canon_path, target_path)
        self.assertEqual(head.entries[0].target_repo_scope, "consumer-fixture")
        self.assertEqual(head.entries[0].delivery_mode, "source_plus_rollout")
        self.assertEqual(head.entries[0].execution_kind, "plan")
        self.assertNotEqual(base.entries[0], head.entries[0])
        self.assertEqual(removed.entries[0], base.entries[0])

    def test_target_repo_scope_preserves_literal_consumer_identity_without_registry(self) -> None:
        for value in ("consumer-fixture", "current-consumer", "default", "planveyor", "target-local", "multi_repo"):
            with self.subTest(value=value):
                self.assertEqual(COLLECT._normalize_target_repo_scope(value), value)

        self.assertEqual(COLLECT._normalize_target_repo_scope("Consumer-Fixture"), "consumer-fixture")
        self.assertEqual(COLLECT._normalize_target_repo_scope("consumer_fixture"), "consumer-fixture")
        self.assertEqual(COLLECT._normalize_target_repo_scope("consumer__fixture"), "consumer-fixture")
        self.assertEqual(COLLECT._normalize_target_repo_scope("current_consumer"), "current-consumer")
        self.assertEqual(COLLECT._normalize_target_repo_scope("shared_consumer"), "shared-consumer")
        self.assertEqual(COLLECT._normalize_target_repo_scope("shared-consumer"), "shared-consumer")
        self.assertEqual(COLLECT._normalize_target_repo_scope("multi-repo"), "multi-repo")
        for value in ("consumer fixture", "consumer/fixture", "consumer.fixture"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "Unsupported target_repo_scope"):
                    COLLECT._normalize_target_repo_scope(value)

    def _collect_surface_fixture(self, root: Path) -> dict[str, object]:
        return COLLECT.collect_process_improvements(
            project_root=root,
            role="Coder",
            source_ref="docs/plans/surface_fixture.md",
            text=dedent(
                """\
                ## 3) Process improvements
                ### Suggestion 1
                - symptom: generated surfaces can look current after manual edits
                - process_gap: derived process-improvement docs lacked a freshness check
                - suggested_fix: add a generated-surface parity check and hard banner
                - owner: Architect
                - promotion_class: helper_change
                - trigger_ref: docs/code_reviews/current.md#B1
                - source_ref: docs/plans/surface_fixture.md
                """
            ),
        )

    def test_raw_backlog_accepts_pi_status_family_and_rejects_unknown(self) -> None:
        root = self._root()
        valid_statuses = (
            ("triaged", "null", "triaged before execution carrier exists"),
            ("deferred", "docs/followups/pi_delivery.md", "deferred with explicit delivery bridge"),
            ("rejected", "null", "rejected as duplicate process feedback"),
        )

        for status, delivery_refs, triage_note in valid_statuses:
            with self.subTest(status=status):
                path = self._write_backlog(
                    root,
                    f"docs/process_improvements/{status}__process_improvements_backlog.md",
                    status=status,
                    delivery_refs=delivery_refs,
                    triage_note=triage_note,
                )
                backlog = COLLECT.parse_backlog_file(path, root)
                self.assertEqual(backlog.entries[0].status, status)

        unknown = self._write_backlog(
            root,
            "docs/process_improvements/waiting__process_improvements_backlog.md",
            status="waiting",
        )
        with self.assertRaisesRegex(ValueError, "Unsupported status"):
            COLLECT.parse_backlog_file(unknown, root)

    def test_collect_accepts_literal_noop_reason(self) -> None:
        root = self._root()
        payload = COLLECT.collect_process_improvements(
            project_root=root,
            role="Architect",
            source_ref="docs/plans/260417_1814_process_memory_finalize_process_improvement_suggestions_harvest.md",
            text=dedent(
                """\
                ## 4) Process improvements
                NO PROCESS IMPROVEMENTS — why: clean_run
                """
            ),
        )

        self.assertEqual(payload["state"], "no_process_improvements")
        self.assertEqual(payload["reason_code"], "clean_run")
        self.assertEqual(payload["process_improvement_capture_state"], "clean_noop")
        self.assertEqual(payload["process_improvement_capture_reason"], "clean_run")
        self.assertEqual(payload["followups_capture_cycle_id"], "none")
        self.assertTrue(str(payload["process_improvement_receipt_path"]).startswith(".tmp/process_improvements_capture/"))
        self.assertEqual(payload["backlog_files"], [])
        self.assertFalse((root / "docs" / "process_improvements").exists())

        receipt = self._read_receipt(
            root,
            "docs/plans/260417_1814_process_memory_finalize_process_improvement_suggestions_harvest.md",
            "Architect",
        )
        self.assertEqual(receipt["capture_state"], "clean_noop")
        self.assertEqual(receipt["reason_code"], "clean_run")
        self.assertEqual(receipt["backlog_paths"], [])
        self.assertEqual(receipt["followups_capture_cycle_id"], "none")

    def test_collect_binds_receipt_to_exact_followups_capture_cycle(self) -> None:
        root = self._root()
        source_ref = "docs/plans/260716_1046_process_docs_closeout_terminal_immutability_scoped_ownership.md"
        cycle_id = "2e9f1138-692c-45e7-a24b-4ec2ca1046f1"
        payload = COLLECT.collect_process_improvements(
            project_root=root,
            role="Reviewer",
            source_ref=source_ref,
            text="## 4) Process improvements\nNO PROCESS IMPROVEMENTS — why: clean_run\n",
            followups_capture_cycle_id=cycle_id,
        )

        receipt = self._read_receipt(root, source_ref, "Reviewer", cycle_id)
        self.assertEqual(payload["followups_capture_cycle_id"], cycle_id)
        self.assertEqual(receipt["followups_capture_cycle_id"], cycle_id)

    def test_cycle_receipt_object_chain_outcomes(self) -> None:
        root = self._root()
        source_ref = "docs/plans/260803_1605_fixture.md"
        cycle_id = "2e9f1138-692c-45e7-a24b-4ec2ca1046f1"
        noop = "## Process improvements\nNO PROCESS IMPROVEMENTS — why: clean_run\n"
        suggestion = dedent(
            f"""\
            ## Process improvements
            ### Suggestion 1
            - symptom: general receipt chain needs exact object maps
            - process_gap: collector receipt did not bind a phase transition
            - suggested_fix: publish sorted before/after objects for the aggregate checkpoint
            - owner: Architect
            - promotion_class: helper_change
            - trigger_ref: docs/code_reviews/fixture.md#B1
            - source_ref: {source_ref}
            """
        )
        COLLECT.collect_process_improvements(
            project_root=root,
            role="Architect",
            source_ref=source_ref,
            text=noop,
            followups_capture_cycle_id=cycle_id,
        )
        COLLECT.collect_process_improvements(
            project_root=root,
            role="Coder",
            source_ref=source_ref,
            text=suggestion,
            followups_capture_cycle_id=cycle_id,
        )
        COLLECT.collect_process_improvements(
            project_root=root,
            role="Planner",
            source_ref=source_ref,
            text=noop,
            followups_capture_cycle_id=cycle_id,
        )
        COLLECT.collect_process_improvements(
            project_root=root,
            role="Reviewer",
            source_ref=source_ref,
            text="## Process improvements\nNO PROCESS IMPROVEMENTS — why: already_tracked\n",
            followups_capture_cycle_id=cycle_id,
        )

        receipts = [
            self._read_receipt(root, source_ref, role, cycle_id)
            for role in ("Architect", "Coder", "Planner", "Reviewer")
        ]
        self.assertEqual(
            [receipt["capture_state"] for receipt in receipts],
            ["clean_noop", "materialized", "clean_noop", "already_tracked"],
        )
        for receipt in receipts:
            self.assertEqual(receipt["followups_capture_cycle_id"], cycle_id)
            self.assertEqual(receipt["receipt_schema"], COLLECT.CAPTURE_RECEIPT_V2_SCHEMA)
            self.assertRegex(str(receipt["input_sha256"]), r"^[0-9a-f]{64}$")
            self.assertIn("before_process_improvement_files", receipt)
            self.assertIn("after_process_improvement_files", receipt)
            self.assertIn("process_improvement_path_results", receipt)
            self.assertEqual(
                [item["path"] for item in receipt["process_improvement_path_results"]],
                sorted(item["path"] for item in receipt["process_improvement_path_results"]),
            )
        self.assertEqual(receipts[0]["after_process_improvement_files"], receipts[1]["before_process_improvement_files"])
        self.assertEqual(receipts[1]["after_process_improvement_files"], receipts[2]["before_process_improvement_files"])
        self.assertEqual(receipts[2]["after_process_improvement_files"], receipts[3]["before_process_improvement_files"])
        self.assertEqual(receipts[3]["before_process_improvement_files"], receipts[3]["after_process_improvement_files"])

    def test_cycle_v2_leaf_and_proven_descendant_replay_are_no_write(self) -> None:
        root = self._root()
        source_ref = "docs/plans/260817_1731_replay_fixture.md"
        cycle_id = "2e9f1138-692c-45e7-a24b-4ec2ca1046f1"
        noop = "## Process improvements\nNO PROCESS IMPROVEMENTS — why: clean_run\n"
        suggestion = dedent(
            f"""\
            ## Process improvements
            ### Suggestion 1
            - symptom: replay needs a successor proof
            - process_gap: an earlier role could be retried after downstream progress
            - suggested_fix: keep the immutable receipt chain as the proof
            - owner: Architect
            - promotion_class: helper_change
            - trigger_ref: docs/code_reviews/fixture.md#B1
            - source_ref: {source_ref}
            """
        )
        fresh = COLLECT.collect_process_improvements(
            project_root=root,
            role="Architect",
            source_ref=source_ref,
            text=noop,
            followups_capture_cycle_id=cycle_id,
        )
        architect_path = root / COLLECT.capture_receipt_rel_path(source_ref, "Architect", cycle_id)
        leaf_bytes = architect_path.read_bytes()
        self.assertEqual(fresh["input_sha256"], hashlib.sha256(noop.encode("utf-8")).hexdigest())
        with mock.patch.object(COLLECT, "_collect_process_improvements_impl", side_effect=AssertionError("must not collect")):
            leaf = COLLECT.collect_process_improvements(
                project_root=root,
                role="Architect",
                source_ref=source_ref,
                text=noop,
                followups_capture_cycle_id=cycle_id,
            )
        self.assertEqual(leaf["process_improvement_capture_replay"], "exact_leaf")
        self.assertNotIn("input_sha256", leaf)
        for field in ("process_improvement_capture_state", "process_improvement_capture_reason",
                      "process_improvement_receipt_path", "followups_capture_cycle_id"):
            self.assertEqual(leaf[field], fresh[field])
        self.assertEqual(architect_path.read_bytes(), leaf_bytes)

        COLLECT.collect_process_improvements(
            project_root=root,
            role="Coder",
            source_ref=source_ref,
            text=suggestion,
            followups_capture_cycle_id=cycle_id,
        )
        for role in ("Planner", "Reviewer"):
            COLLECT.collect_process_improvements(
                project_root=root,
                role=role,
                source_ref=source_ref,
                text=noop,
                followups_capture_cycle_id=cycle_id,
            )
        receipt_bytes = {
            role: (root / COLLECT.capture_receipt_rel_path(source_ref, role, cycle_id)).read_bytes()
            for role in COLLECT.GENERAL_CAPTURE_ROLES
        }
        pi_bytes = {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in (root / "docs/process_improvements").glob("*")
            if path.is_file()
        }
        with mock.patch.object(COLLECT, "_collect_process_improvements_impl", side_effect=AssertionError("must not collect")):
            descendant = COLLECT.collect_process_improvements(
                project_root=root,
                role="Architect",
                source_ref=source_ref,
                text=noop,
                followups_capture_cycle_id=cycle_id,
            )
        self.assertEqual(descendant["process_improvement_capture_replay"], "exact_proven_descendant")
        self.assertEqual(
            {
                role: (root / COLLECT.capture_receipt_rel_path(source_ref, role, cycle_id)).read_bytes()
                for role in COLLECT.GENERAL_CAPTURE_ROLES
            },
            receipt_bytes,
        )
        self.assertEqual(
            {
                path.relative_to(root).as_posix(): path.read_bytes()
                for path in (root / "docs/process_improvements").glob("*")
                if path.is_file()
            },
            pi_bytes,
        )

    def test_cycle_v2_conflict_and_blocked_correction_preserve_receipt_bytes(self) -> None:
        root = self._root()
        source_ref = "docs/plans/260817_1731_conflict_fixture.md"
        cycle_id = "2e9f1138-692c-45e7-a24b-4ec2ca1046f1"
        valid = "## Process improvements\nNO PROCESS IMPROVEMENTS — why: clean_run\n"
        invalid = "## Process improvements\nNO PROCESS IMPROVEMENTS — why: typo_reason\n"
        with self.assertRaisesRegex(ValueError, "Unsupported no-op reason"):
            COLLECT.collect_process_improvements(
                project_root=root,
                role="Architect",
                source_ref=source_ref,
                text=invalid,
                followups_capture_cycle_id=cycle_id,
            )
        receipt_path = root / COLLECT.capture_receipt_rel_path(source_ref, "Architect", cycle_id)
        blocked_bytes = receipt_path.read_bytes()
        self.assertEqual(json.loads(blocked_bytes)["capture_state"], "blocked")

        corrected = COLLECT.collect_process_improvements(
            project_root=root,
            role="Architect",
            source_ref=source_ref,
            text=valid,
            followups_capture_cycle_id=cycle_id,
        )
        self.assertEqual(corrected["process_improvement_capture_state"], "clean_noop")
        continuation_bytes = receipt_path.read_bytes()
        self.assertNotEqual(continuation_bytes, blocked_bytes)
        with mock.patch.object(COLLECT, "_collect_process_improvements_impl", side_effect=AssertionError("must not collect")):
            with self.assertRaisesRegex(ValueError, "input digest conflicts"):
                COLLECT.collect_process_improvements(
                    project_root=root,
                    role="Architect",
                    source_ref=source_ref,
                    text=valid.replace("\n", "\r\n"),
                    followups_capture_cycle_id=cycle_id,
                )
        self.assertEqual(receipt_path.read_bytes(), continuation_bytes)

    def test_cycle_v2_interrupted_private_publication_leaves_no_canonical_and_retry_succeeds(self) -> None:
        source_ref = "docs/plans/260817_1731_atomic_publication_fixture.md"
        cycle_id = "2e9f1138-692c-45e7-a24b-4ec2ca1046f1"
        valid = "## Process improvements\nNO PROCESS IMPROVEMENTS — why: clean_run\n"
        invalid = "## Process improvements\nNO PROCESS IMPROVEMENTS — why: typo_reason\n"

        for branch in ("first_publication", "blocked_correction"):
            with self.subTest(branch=branch):
                root = self._root()
                receipt_path = root / COLLECT.capture_receipt_rel_path(source_ref, "Architect", cycle_id)
                prior_bytes: bytes | None = None
                if branch == "blocked_correction":
                    with self.assertRaisesRegex(ValueError, "Unsupported no-op reason"):
                        COLLECT.collect_process_improvements(
                            project_root=root,
                            role="Architect",
                            source_ref=source_ref,
                            text=invalid,
                            followups_capture_cycle_id=cycle_id,
                        )
                    prior_bytes = receipt_path.read_bytes()
                    self.assertEqual(json.loads(prior_bytes)["capture_state"], "blocked")

                def interrupt_private_write(fd: int, data: bytes) -> None:
                    self.assertEqual(os.write(fd, data[:17]), 17)
                    raise OSError("injected temporary receipt write failure")

                with mock.patch.object(COLLECT, "_write_fd_all", side_effect=interrupt_private_write):
                    with self.assertRaisesRegex(OSError, "injected temporary receipt write failure"):
                        COLLECT.collect_process_improvements(
                            project_root=root,
                            role="Architect",
                            source_ref=source_ref,
                            text=valid,
                            followups_capture_cycle_id=cycle_id,
                        )

                if prior_bytes is None:
                    self.assertFalse(receipt_path.exists())
                else:
                    self.assertEqual(receipt_path.read_bytes(), prior_bytes)
                self.assertEqual(list(receipt_path.parent.glob(f".{receipt_path.name}.*.tmp")), [])

                retried = COLLECT.collect_process_improvements(
                    project_root=root,
                    role="Architect",
                    source_ref=source_ref,
                    text=valid,
                    followups_capture_cycle_id=cycle_id,
                )
                self.assertEqual(retried["process_improvement_capture_state"], "clean_noop")
                complete_bytes = receipt_path.read_bytes()
                self.assertEqual(json.loads(complete_bytes)["capture_state"], "clean_noop")
                with mock.patch.object(COLLECT, "_collect_process_improvements_impl", side_effect=AssertionError("must not collect")):
                    replay = COLLECT.collect_process_improvements(
                        project_root=root,
                        role="Architect",
                        source_ref=source_ref,
                        text=valid,
                        followups_capture_cycle_id=cycle_id,
                    )
                self.assertEqual(replay["process_improvement_capture_replay"], "exact_leaf")
                self.assertEqual(receipt_path.read_bytes(), complete_bytes)

    def test_cycle_v2_unproven_successor_suffixes_fail_before_collection(self) -> None:
        source_ref = "docs/plans/260817_1731_suffix_fixture.md"
        cycle_id = "2e9f1138-692c-45e7-a24b-4ec2ca1046f1"
        noop = "## Process improvements\nNO PROCESS IMPROVEMENTS — why: clean_run\n"
        suggestion = dedent(
            f"""\
            ## Process improvements
            ### Suggestion 1
            - symptom: successor proof needs a negative fixture
            - process_gap: arbitrary live map drift can look like downstream progress
            - suggested_fix: require a contiguous immutable v2 suffix
            - owner: Architect
            - promotion_class: helper_change
            - trigger_ref: docs/code_reviews/fixture.md#B1
            - source_ref: {source_ref}
            """
        )
        for case in ("missing", "swapped", "wrong_cycle"):
            with self.subTest(case=case):
                root = self._root()
                COLLECT.collect_process_improvements(
                    project_root=root,
                    role="Architect",
                    source_ref=source_ref,
                    text=noop,
                    followups_capture_cycle_id=cycle_id,
                )
                COLLECT.collect_process_improvements(
                    project_root=root,
                    role="Coder",
                    source_ref=source_ref,
                    text=suggestion,
                    followups_capture_cycle_id=cycle_id,
                )
                architect_path = root / COLLECT.capture_receipt_rel_path(source_ref, "Architect", cycle_id)
                before = architect_path.read_bytes()
                if case == "missing":
                    COLLECT.collect_process_improvements(
                        project_root=root,
                        role="Planner",
                        source_ref=source_ref,
                        text=suggestion.replace("fixture.md#B1", "fixture.md#B2"),
                        followups_capture_cycle_id=cycle_id,
                        write_receipt=False,
                    )
                else:
                    coder_path = root / COLLECT.capture_receipt_rel_path(source_ref, "Coder", cycle_id)
                    forged = json.loads(coder_path.read_text(encoding="utf-8"))
                    if case == "swapped":
                        forged["role"] = "Planner"
                    else:
                        forged["followups_capture_cycle_id"] = "3e9f1138-692c-45e7-a24b-4ec2ca1046f1"
                    coder_path.write_text(json.dumps(forged, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
                with mock.patch.object(COLLECT, "_collect_process_improvements_impl", side_effect=AssertionError("must not collect")):
                    with self.assertRaises(ValueError):
                        COLLECT.collect_process_improvements(
                            project_root=root,
                            role="Architect",
                            source_ref=source_ref,
                            text=noop,
                            followups_capture_cycle_id=cycle_id,
                        )
                self.assertEqual(architect_path.read_bytes(), before)

    def test_cycle_v2_raw_cli_input_hashes_before_decode_and_isolated_by_cycle(self) -> None:
        root = self._root()
        source_ref = "docs/plans/260817_1731_raw_input_fixture.md"
        cycle_one = "2e9f1138-692c-45e7-a24b-4ec2ca1046f1"
        cycle_two = "3e9f1138-692c-45e7-a24b-4ec2ca1046f1"
        raw_stdin = "## Process improvements\r\nNO PROCESS IMPROVEMENTS — why: clean_run\r\n".encode("utf-8")
        stdout = io.StringIO()
        stdin = io.TextIOWrapper(io.BytesIO(raw_stdin), encoding="utf-8")
        with mock.patch.object(sys, "stdin", stdin), redirect_stdout(stdout):
            self.assertEqual(
                COLLECT.main(
                    [
                        "--project-root",
                        str(root),
                        "--role",
                        "Architect",
                        "--source-ref",
                        source_ref,
                        "--followups-capture-cycle-id",
                        cycle_one,
                        "--input",
                        "-",
                        "--json",
                    ]
                ),
                0,
            )
        first_path = root / COLLECT.capture_receipt_rel_path(source_ref, "Architect", cycle_one)
        first_bytes = first_path.read_bytes()
        first = json.loads(first_bytes)
        self.assertEqual(first["input_sha256"], hashlib.sha256(raw_stdin).hexdigest())

        input_path = root / "parser_equivalent.txt"
        input_path.write_bytes(raw_stdin.replace(b"\r\n", b"\n"))
        with self.assertRaisesRegex(ValueError, "input digest conflicts"):
            COLLECT.main(
                [
                    "--project-root",
                    str(root),
                    "--role",
                    "Architect",
                    "--source-ref",
                    source_ref,
                    "--followups-capture-cycle-id",
                    cycle_one,
                    "--input",
                    str(input_path),
                    "--json",
                ]
            )
        invalid_path = root / "invalid-utf8.txt"
        invalid_path.write_bytes(b"\xff")
        with self.assertRaises(ValueError):
            COLLECT.main(
                [
                    "--project-root",
                    str(root),
                    "--role",
                    "Architect",
                    "--source-ref",
                    source_ref,
                    "--followups-capture-cycle-id",
                    cycle_one,
                    "--input",
                    str(invalid_path),
                ]
            )
        self.assertEqual(first_path.read_bytes(), first_bytes)

        second = COLLECT.collect_process_improvements(
            project_root=root,
            role="Architect",
            source_ref=source_ref,
            text=raw_stdin,
            followups_capture_cycle_id=cycle_two,
        )
        second_path = root / COLLECT.capture_receipt_rel_path(source_ref, "Architect", cycle_two)
        self.assertEqual(second["process_improvement_capture_state"], "clean_noop")
        self.assertNotEqual(first_path, second_path)
        self.assertTrue(second_path.exists())

    def test_cycle_v2_unsafe_existing_receipt_fails_before_collection(self) -> None:
        root = self._root()
        source_ref = "docs/plans/260817_1731_unsafe_fixture.md"
        cycle_id = "2e9f1138-692c-45e7-a24b-4ec2ca1046f1"
        receipt_path = root / COLLECT.capture_receipt_rel_path(source_ref, "Architect", cycle_id)
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        target = receipt_path.with_name("architect.real.json")
        target.write_bytes(b"do-not-follow\n")
        receipt_path.symlink_to(target.name)
        with mock.patch.object(COLLECT, "_collect_process_improvements_impl", side_effect=AssertionError("must not collect")):
            with self.assertRaisesRegex(ValueError, "unsafe process-improvement capture receipt"):
                COLLECT.collect_process_improvements(
                    project_root=root,
                    role="Architect",
                    source_ref=source_ref,
                    text="## Process improvements\nNO PROCESS IMPROVEMENTS — why: clean_run\n",
                    followups_capture_cycle_id=cycle_id,
                )
        self.assertEqual(target.read_bytes(), b"do-not-follow\n")

    def test_current_cycle_operator_docs_are_v2_and_v1_is_legacy_only(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        readme = (repo_root / "docs/process_improvements/README.md").read_text(encoding="utf-8")
        for marker in (
            "process_improvement_capture.v2",
            "<source-slug>/<capture-cycle-id>/<role>.json",
            "process_improvement_capture.v1",
            "No-cycle compatibility",
            "не может быть proof для current cycle",
            "Explicit-cycle reader не ищет directory/latest/mtime и не fallback'ит к v1",
            "exclusive",
            "no-write",
            "v2 continuation receipt never перезаписывается",
        ):
            self.assertIn(marker, readme)

    def test_collect_rejects_noncanonical_followups_capture_cycle(self) -> None:
        for value in (
            "not-a-cycle",
            "`2e9f1138-692c-45e7-a24b-4ec2ca1046f1`",
            " 2e9f1138-692c-45e7-a24b-4ec2ca1046f1",
            "",
        ):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "canonical UUIDv4"):
                COLLECT.collect_process_improvements(
                    project_root=self._root(),
                    role="Reviewer",
                    source_ref="docs/plans/260716_1046_fixture.md",
                    text="## 4) Process improvements\nNO PROCESS IMPROVEMENTS — why: clean_run\n",
                    followups_capture_cycle_id=value,
                )

    def test_collect_accepts_bullet_literal_noop_reason(self) -> None:
        for bullet in ("-", "*"):
            with self.subTest(bullet=bullet):
                root = self._root()
                payload = COLLECT.collect_process_improvements(
                    project_root=root,
                    role="Architect",
                    source_ref="docs/plans/260619_1439_process_docs_finalize_noop_bullet_sentinel.md",
                    text=f"## 4) Process improvements\n{bullet} NO PROCESS IMPROVEMENTS — why: clean_run\n",
                )

                self.assertEqual(payload["state"], "no_process_improvements")
                self.assertEqual(payload["reason_code"], "clean_run")
                self.assertEqual(payload["process_improvement_capture_state"], "clean_noop")
                self.assertEqual(payload["process_improvement_capture_reason"], "clean_run")
                self.assertEqual(payload["backlog_files"], [])
                self.assertFalse((root / "docs" / "process_improvements").exists())

                receipt = self._read_receipt(
                    root,
                    "docs/plans/260619_1439_process_docs_finalize_noop_bullet_sentinel.md",
                    "Architect",
                )
                self.assertEqual(receipt["capture_state"], "clean_noop")
                self.assertEqual(receipt["reason_code"], "clean_run")
                self.assertEqual(receipt["backlog_paths"], [])

    def test_collect_accepts_ascii_hyphen_noop_reason(self) -> None:
        root = self._root()
        payload = COLLECT.collect_process_improvements(
            project_root=root,
            role="Reviewer",
            source_ref="docs/plans/260619_0026_process_small_model_ready_real_runner_pilot.md",
            text=dedent(
                """\
                ## 3) Process improvements
                NO PROCESS IMPROVEMENTS - why: already_tracked
                """
            ),
        )

        self.assertEqual(payload["state"], "no_process_improvements")
        self.assertEqual(payload["reason_code"], "already_tracked")
        self.assertEqual(payload["process_improvement_capture_state"], "already_tracked")
        self.assertEqual(payload["process_improvement_capture_reason"], "already_tracked")
        self.assertEqual(payload["backlog_files"], [])

    def test_collect_rejects_mixed_bullet_noop_with_structured_suggestion(self) -> None:
        root = self._root()
        with self.assertRaisesRegex(ValueError, "Literal no-op cannot be mixed"):
            COLLECT.collect_process_improvements(
                project_root=root,
                role="Coder",
                source_ref="docs/plans/live.md",
                text=dedent(
                    """\
                    ## 3) Process improvements
                    - NO PROCESS IMPROVEMENTS — why: clean_run
                    ### Suggestion 1
                    - symptom: mixed no-op and suggestion should stay blocked
                    - process_gap: malformed process-improvement output can hide useful rows
                    - suggested_fix: keep no-op parsing single-line only
                    - owner: Architect
                    - promotion_class: helper_change
                    - trigger_ref: docs/code_reviews/current.md#B1
                    - source_ref: docs/plans/live.md
                    """
                ),
            )

        receipt = self._read_receipt(root, "docs/plans/live.md", "Coder")
        self.assertEqual(receipt["capture_state"], "blocked")
        self.assertEqual(receipt["reason_code"], "collector_error")
        self.assertIn("Literal no-op cannot be mixed", receipt["error"])
        self.assertFalse((root / "docs" / "process_improvements").exists())

    def test_collect_rejects_bullet_noop_with_extra_body_text(self) -> None:
        root = self._root()
        with self.assertRaisesRegex(ValueError, "Literal no-op cannot be mixed"):
            COLLECT.collect_process_improvements(
                project_root=root,
                role="Reviewer",
                source_ref="docs/plans/live.md",
                text=dedent(
                    """\
                    ## 3) Process improvements
                    - NO PROCESS IMPROVEMENTS — why: clean_run
                    trailing prose
                    """
                ),
            )

        receipt = self._read_receipt(root, "docs/plans/live.md", "Reviewer")
        self.assertEqual(receipt["capture_state"], "blocked")
        self.assertEqual(receipt["reason_code"], "collector_error")
        self.assertIn("Literal no-op cannot be mixed", receipt["error"])
        self.assertFalse((root / "docs" / "process_improvements").exists())

    def test_collect_rejects_unsupported_noop_reason_in_literal_and_bullet_forms(self) -> None:
        for sentinel in (
            "NO PROCESS IMPROVEMENTS — why: typo_reason",
            "NO PROCESS IMPROVEMENTS - why: typo_reason",
            "- NO PROCESS IMPROVEMENTS — why: typo_reason",
            "* NO PROCESS IMPROVEMENTS — why: typo_reason",
        ):
            with self.subTest(sentinel=sentinel):
                root = self._root()
                with self.assertRaisesRegex(ValueError, "Unsupported no-op reason"):
                    COLLECT.collect_process_improvements(
                        project_root=root,
                        role="Planner",
                        source_ref="docs/plans/live.md",
                        text=f"## 3) Process improvements\n{sentinel}\n",
                    )

                receipt = self._read_receipt(root, "docs/plans/live.md", "Planner")
                self.assertEqual(receipt["capture_state"], "blocked")
                self.assertEqual(receipt["reason_code"], "collector_error")
                self.assertIn("Unsupported no-op reason", receipt["error"])
                self.assertFalse((root / "docs" / "process_improvements").exists())

    def test_collect_creates_backlog_and_derived_surfaces(self) -> None:
        root = self._root()
        payload = COLLECT.collect_process_improvements(
            project_root=root,
            role="Coder",
            source_ref="docs/plans/260417_1814_process_memory_finalize_process_improvement_suggestions_harvest.md",
            text=dedent(
                """\
                ## 3) Process improvements
                ### Suggestion 1
                - symptom: repeated blocker knowledge still dies in chat memory
                - process_gap: no durable collector for memory-finalize process suggestions
                - suggested_fix: add one collector helper plus derived surfaces under docs/process_improvements/
                - owner: Architect
                - promotion_class: helper_change
                - trigger_ref: docs/code_reviews/260417_1812_process_manager_docs_closeout_step_and_architect_memory_commit_handoff.md#B1
                - source_ref: docs/plans/260417_1814_process_memory_finalize_process_improvement_suggestions_harvest.md
                """
            ),
        )

        self.assertEqual(payload["state"], "collected")
        self.assertEqual(payload["process_improvement_capture_state"], "materialized")
        self.assertEqual(payload["process_improvement_capture_reason"], "structured_suggestions_materialized")
        self.assertEqual(len(payload["created"]), 1)
        backlog_rel = payload["backlog_files"][0]
        backlog_path = root / backlog_rel
        self.assertTrue(backlog_path.exists())

        backlog = COLLECT.parse_backlog_file(backlog_path, root)
        self.assertEqual(backlog.source_ref, "docs/plans/260417_1814_process_memory_finalize_process_improvement_suggestions_harvest.md")
        self.assertEqual(len(backlog.entries), 1)
        entry = backlog.entries[0]
        self.assertEqual(entry.entry_id, "PI-001")
        self.assertEqual(entry.status, "open")
        self.assertEqual(entry.priority, "P?")
        self.assertEqual(entry.owner, "Architect")
        self.assertEqual(entry.promotion_class, "helper_change")
        self.assertEqual(entry.target_canon_path, "null")
        self.assertEqual(entry.target_repo_scope, "null")
        self.assertEqual(entry.delivery_mode, "null")
        self.assertEqual(entry.execution_kind, "null")
        self.assertEqual(entry.execution_ref, "null")
        self.assertEqual(entry.delivery_refs, "null")
        self.assertEqual(entry.handled_ref, "null")
        self.assertEqual(entry.promoted_at, "null")
        self.assertEqual(entry.handled_at, "null")

        index_text = (root / "docs" / "process_improvements" / "index.md").read_text(encoding="utf-8")
        deferred_text = (root / "docs" / "process_improvements" / "deferred.md").read_text(encoding="utf-8")
        promotion_text = (root / "docs" / "process_improvements" / "promotion_surface.md").read_text(encoding="utf-8")
        self.assertIn("PI-001", deferred_text)
        self.assertIn("PI-001", promotion_text)
        self.assertIn(backlog_rel, index_text)
        self.assertIn(COLLECT.PROCESS_DERIVED_BANNER_LINE, index_text)
        self.assertIn(COLLECT.PROCESS_DERIVED_BANNER_LINE, deferred_text)
        self.assertIn(COLLECT.PROCESS_DERIVED_BANNER_LINE, promotion_text)

        receipt = self._read_receipt(
            root,
            "docs/plans/260417_1814_process_memory_finalize_process_improvement_suggestions_harvest.md",
            "Coder",
        )
        self.assertEqual(receipt["capture_state"], "materialized")
        self.assertEqual(receipt["backlog_paths"], [backlog_rel])

    def test_collect_accepts_naked_known_structured_fields_from_docs_closeout_stdout(self) -> None:
        root = self._root()
        source_ref = "docs/plans/260624_1441_process_planner_coder_handoff_digest_analysis.md"
        payload = COLLECT.collect_process_improvements(
            project_root=root,
            role="Architect",
            source_ref=source_ref,
            text=dedent(
                f"""\
                ## 3) Process improvements
                ### Suggestion 1
                symptom: docs-closeout PI capture blocked on bulletless structured field rows
                process_gap: collector grammar only accepted markdown-bulleted fields
                suggested_fix: accept known field rows without bullets inside docs-closeout stdout only
                owner: Architect
                promotion_class: helper_change
                trigger_ref: .tmp/process_improvements_capture/99db194c674a_260624_1441_process_planner_coder_handoff_digest_analysis/architect.json
                source_ref: {source_ref}
                """
            ),
        )

        self.assertEqual(payload["process_improvement_capture_state"], "materialized")
        backlog = COLLECT.parse_backlog_file(root / payload["backlog_files"][0], root)
        self.assertEqual(backlog.source_ref, source_ref)
        self.assertEqual(backlog.entries[0].symptom, "docs-closeout PI capture blocked on bulletless structured field rows")
        receipt = self._read_receipt(root, source_ref, "Architect")
        self.assertEqual(receipt["capture_state"], "materialized")

    def test_collect_rejects_ambiguous_structured_field_variants(self) -> None:
        variants = {
            "star_bullet": "* symptom: star bullets are not canonical structured output",
            "numbered": "1. symptom: numbered fields are ambiguous role prose",
            "prose": "this is just a sentence, not a process-improvement field",
            "unknown_field": "severity: P0",
        }
        for name, first_line in variants.items():
            with self.subTest(name=name):
                root = self._root()
                source_ref = f"docs/plans/{name}.md"
                expected_error = "Unsupported field" if name == "unknown_field" else "Unsupported line"
                with self.assertRaisesRegex(ValueError, expected_error):
                    COLLECT.collect_process_improvements(
                        project_root=root,
                        role="Coder",
                        source_ref=source_ref,
                        text=dedent(
                            f"""\
                            ## 3) Process improvements
                            ### Suggestion 1
                            {first_line}
                            - process_gap: parser must remain bounded to known fields
                            - suggested_fix: reject non-canonical structured variants
                            - owner: Architect
                            - promotion_class: helper_change
                            - trigger_ref: docs/code_reviews/current.md#B1
                            - source_ref: {source_ref}
                            """
                        ),
                    )

                receipt = self._read_receipt(root, source_ref, "Coder")
                self.assertEqual(receipt["capture_state"], "blocked")
                self.assertEqual(receipt["reason_code"], "collector_error")
                self.assertFalse((root / "docs" / "process_improvements").exists())

    def test_collect_maps_legacy_template_aliases_to_canon_update(self) -> None:
        for alias in ("template_change", "template_update"):
            with self.subTest(alias=alias):
                root = self._root()
                payload = COLLECT.collect_process_improvements(
                    project_root=root,
                    role="Reviewer",
                    source_ref=f"docs/plans/live_{alias}.md",
                    text=dedent(
                        f"""\
                        ## Process improvements
                        ### Suggestion 1
                        - symptom: Reviewer output used a template-specific promotion class
                        - process_gap: collector blocked docs-closeout on legacy role output
                        - suggested_fix: normalize {alias} to the canonical canon_update class
                        - owner: Architect
                        - promotion_class: {alias}
                        - trigger_ref: docs/code_reviews/current.md#process-improvements
                        - source_ref: docs/plans/live_{alias}.md
                        """
                    ),
                )

                self.assertEqual(payload["process_improvement_capture_state"], "materialized")
                backlog = COLLECT.parse_backlog_file(root / payload["backlog_files"][0], root)
                self.assertEqual(backlog.entries[0].promotion_class, "canon_update")

    def test_derived_surface_check_passes_with_banners_and_no_write(self) -> None:
        root = self._root()
        self._collect_surface_fixture(root)
        before = {
            rel.as_posix(): (root / rel).read_text(encoding="utf-8")
            for rel in (COLLECT.INDEX_PATH, COLLECT.DEFERRED_PATH, COLLECT.PROMOTION_PATH)
        }

        result = COLLECT.check_derived_surfaces(root)

        self.assertTrue(result["ok"], result)
        self.assertFalse(result["would_write"])
        self.assertEqual(len(result["surfaces"]), 3)
        for surface in result["surfaces"]:
            self.assertTrue(surface["ok"], surface)
            self.assertEqual(surface["issues"], [])
            self.assertTrue(surface["timestamp_ignored"])
        for rel in (COLLECT.INDEX_PATH, COLLECT.DEFERRED_PATH, COLLECT.PROMOTION_PATH):
            text = (root / rel).read_text(encoding="utf-8")
            self.assertEqual(text, before[rel.as_posix()])
            self.assertIn(COLLECT.PROCESS_DERIVED_BANNER_LINE, text)

    def test_derived_surface_check_allows_timestamp_only_drift(self) -> None:
        root = self._root()
        self._collect_surface_fixture(root)
        for rel in (COLLECT.INDEX_PATH, COLLECT.DEFERRED_PATH, COLLECT.PROMOTION_PATH):
            path = root / rel
            lines = [
                "_Auto-generated by `scripts/process_improvements_collect.py` on 2026-06-20 00:05 MSK._"
                if line.startswith("_Auto-generated by `scripts/process_improvements_collect.py` on ")
                else line
                for line in path.read_text(encoding="utf-8").splitlines()
            ]
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        result = COLLECT.check_derived_surfaces(root)

        self.assertTrue(result["ok"], result)
        self.assertTrue(all(surface["timestamp_ignored"] for surface in result["surfaces"]))

    def test_derived_surface_check_accepts_exact_legacy_banner_without_writes(self) -> None:
        root = self._root()
        self._collect_surface_fixture(root)
        before = {}
        for rel in (COLLECT.INDEX_PATH, COLLECT.DEFERRED_PATH, COLLECT.PROMOTION_PATH):
            path = root / rel
            text = path.read_text(encoding="utf-8")
            self.assertIn(COLLECT.PROCESS_DERIVED_BANNER_LINE, text)
            self.assertNotIn(LEGACY_DERIVED_BANNER_LINE, text)
            path.write_text(text.replace(COLLECT.PROCESS_DERIVED_BANNER_LINE, LEGACY_DERIVED_BANNER_LINE), encoding="utf-8")
            before[rel] = (path.read_bytes(), stat.S_IMODE(path.stat().st_mode))

        result = COLLECT.check_derived_surfaces(root)

        self.assertTrue(result["ok"], result)
        self.assertFalse(result["would_write"])
        for rel, expected in before.items():
            path = root / rel
            self.assertEqual((path.read_bytes(), stat.S_IMODE(path.stat().st_mode)), expected)

    def test_legacy_banner_does_not_allow_other_generated_block_changes(self) -> None:
        root = self._root()
        self._collect_surface_fixture(root)
        path = root / COLLECT.INDEX_PATH
        current = path.read_text(encoding="utf-8")
        legacy = current.replace(COLLECT.PROCESS_DERIVED_BANNER_LINE, LEGACY_DERIVED_BANNER_LINE)
        legacy_lines = legacy.splitlines()
        reordered = legacy_lines.copy()
        banner_index = reordered.index(LEGACY_DERIVED_BANNER_LINE)
        reordered[banner_index], reordered[banner_index + 1] = reordered[banner_index + 1], reordered[banner_index]
        data_row = next(line for line in legacy_lines if "docs/plans/surface_fixture.md" in line)
        variants = {
            "table_data": legacy.replace("docs/plans/surface_fixture.md", "docs/plans/edited_surface.md", 1),
            "edited_banner": legacy.replace("--rebuild-derived", "--rebuild-other"),
            "unknown_banner": legacy.replace(LEGACY_DERIVED_BANNER_LINE, "_DO NOT EDIT - unknown generator._"),
            "duplicate_legacy": legacy.replace(LEGACY_DERIVED_BANNER_LINE, LEGACY_DERIVED_BANNER_LINE + "\n" + LEGACY_DERIVED_BANNER_LINE),
            "duplicate_current": current.replace(COLLECT.PROCESS_DERIVED_BANNER_LINE, COLLECT.PROCESS_DERIVED_BANNER_LINE + "\n" + COLLECT.PROCESS_DERIVED_BANNER_LINE),
            "both_banners": legacy.replace(LEGACY_DERIVED_BANNER_LINE, LEGACY_DERIVED_BANNER_LINE + "\n" + COLLECT.PROCESS_DERIVED_BANNER_LINE),
            "extra_line": legacy.replace(LEGACY_DERIVED_BANNER_LINE, LEGACY_DERIVED_BANNER_LINE + "\nextra generated content"),
            "deleted_table_row": legacy.replace(data_row + "\n", ""),
            "reordered_lines": "\n".join(reordered) + "\n",
            "missing_banner": legacy.replace(LEGACY_DERIVED_BANNER_LINE + "\n", ""),
            "broken_marker": legacy.replace(COLLECT.INDEX_AUTO_END, ""),
        }
        for name, text in variants.items():
            with self.subTest(variant=name):
                self.assertNotEqual(text, legacy)
                path.write_text(text, encoding="utf-8")
                before = path.read_bytes()
                result = COLLECT.check_derived_surfaces(root)
                self.assertFalse(result["ok"], result)
                self.assertFalse(result["would_write"])
                self.assertEqual(path.read_bytes(), before)

    def test_derived_surface_check_fails_for_hand_edited_content(self) -> None:
        root = self._root()
        self._collect_surface_fixture(root)
        index_path = root / COLLECT.INDEX_PATH
        text = index_path.read_text(encoding="utf-8")
        index_path.write_text(
            text.replace("docs/plans/surface_fixture.md", "docs/plans/edited_surface.md", 1),
            encoding="utf-8",
        )

        result = COLLECT.check_derived_surfaces(root)
        index_surface = next(
            surface
            for surface in result["surfaces"]
            if surface["path"] == COLLECT.INDEX_PATH.as_posix()
        )

        self.assertFalse(result["ok"])
        self.assertFalse(index_surface["ok"])
        self.assertIn("generated_content_mismatch", index_surface["issues"])
        self.assertTrue(any("edited_surface" in line for line in index_surface["diff"]))

    def test_derived_surface_check_fails_for_missing_banner(self) -> None:
        root = self._root()
        self._collect_surface_fixture(root)
        deferred_path = root / COLLECT.DEFERRED_PATH
        deferred_path.write_text(
            deferred_path.read_text(encoding="utf-8").replace(
                COLLECT.PROCESS_DERIVED_BANNER_LINE + "\n",
                "",
            ),
            encoding="utf-8",
        )

        result = COLLECT.check_derived_surfaces(root)
        deferred_surface = next(
            surface
            for surface in result["surfaces"]
            if surface["path"] == COLLECT.DEFERRED_PATH.as_posix()
        )

        self.assertFalse(result["ok"])
        self.assertFalse(deferred_surface["ok"])
        self.assertIn("missing_banner_line", deferred_surface["issues"])
        self.assertIn("generated_content_mismatch", deferred_surface["issues"])

    def test_derived_surface_check_fails_for_marker_and_banner_problems(self) -> None:
        root = self._root()
        self._collect_surface_fixture(root)

        index_path = root / COLLECT.INDEX_PATH
        index_text = index_path.read_text(encoding="utf-8")
        index_path.write_text(
            index_text.rstrip() + "\n" + index_text[index_text.index(COLLECT.INDEX_AUTO_START) :],
            encoding="utf-8",
        )

        deferred_path = root / COLLECT.DEFERRED_PATH
        deferred_path.write_text(
            deferred_path.read_text(encoding="utf-8").replace(COLLECT.DEFERRED_AUTO_START, ""),
            encoding="utf-8",
        )

        promotion_path = root / COLLECT.PROMOTION_PATH
        promotion_path.write_text(
            "# Process improvements — promotion surface\n\n"
            f"{COLLECT.PROMOTION_AUTO_START}{COLLECT.PROMOTION_AUTO_END}\n",
            encoding="utf-8",
        )

        result = COLLECT.check_derived_surfaces(root)
        by_path = {surface["path"]: surface for surface in result["surfaces"]}

        self.assertFalse(result["ok"])
        self.assertEqual(
            by_path[COLLECT.INDEX_PATH.as_posix()]["issues"],
            ["multiple_generated_blocks"],
        )
        self.assertEqual(
            by_path[COLLECT.DEFERRED_PATH.as_posix()]["issues"],
            ["missing_generated_block"],
        )
        self.assertEqual(
            by_path[COLLECT.PROMOTION_PATH.as_posix()]["issues"],
            ["malformed_generated_block"],
        )

    def test_derived_surface_check_json_is_non_mutating(self) -> None:
        root = self._root()
        self._collect_surface_fixture(root)
        before = {
            rel.as_posix(): (root / rel).read_text(encoding="utf-8")
            for rel in (COLLECT.INDEX_PATH, COLLECT.DEFERRED_PATH, COLLECT.PROMOTION_PATH)
        }
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            exit_code = COLLECT.main(["--project-root", str(root), "--check", "--json"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["would_write"])
        self.assertEqual(len(payload["surfaces"]), 3)
        for rel in (COLLECT.INDEX_PATH, COLLECT.DEFERRED_PATH, COLLECT.PROMOTION_PATH):
            self.assertEqual((root / rel).read_text(encoding="utf-8"), before[rel.as_posix()])

    def test_rebuild_derived_cli_restores_banner(self) -> None:
        root = self._root()
        self._collect_surface_fixture(root)
        index_path = root / COLLECT.INDEX_PATH
        index_path.write_text(
            index_path.read_text(encoding="utf-8").replace(
                COLLECT.PROCESS_DERIVED_BANNER_LINE + "\n",
                "",
            ),
            encoding="utf-8",
        )
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            exit_code = COLLECT.main(["--project-root", str(root), "--rebuild-derived", "--json"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["state"], "derived_surfaces_rebuilt")
        self.assertIn(COLLECT.PROCESS_DERIVED_BANNER_LINE, index_path.read_text(encoding="utf-8"))
        self.assertTrue(COLLECT.check_derived_surfaces(root)["ok"])

    def test_collect_deduplicates_same_suggestion(self) -> None:
        root = self._root()
        text = dedent(
            """\
            ## 3) Process improvements
            ### Suggestion 1
            - symptom: docs-closeout reroute can still be guessed from memory
            - process_gap: no dedicated process-improvements backlog family
            - suggested_fix: collect process suggestions into their own backlog carrier
            - owner: Planner
            - promotion_class: prompt_change
            - trigger_ref: docs/plans/260417_1812_process_manager_docs_closeout_step_and_architect_memory_commit_handoff.md
            - source_ref: docs/plans/260417_1814_process_memory_finalize_process_improvement_suggestions_harvest.md
            """
        )

        first = COLLECT.collect_process_improvements(
            project_root=root,
            role="Planner",
            source_ref="docs/plans/260417_1814_process_memory_finalize_process_improvement_suggestions_harvest.md",
            text=text,
        )
        second = COLLECT.collect_process_improvements(
            project_root=root,
            role="Planner",
            source_ref="docs/plans/260417_1814_process_memory_finalize_process_improvement_suggestions_harvest.md",
            text=text,
        )

        backlog_path = root / first["backlog_files"][0]
        backlog = COLLECT.parse_backlog_file(backlog_path, root)
        self.assertEqual(len(backlog.entries), 1)
        self.assertEqual(len(first["created"]), 1)
        self.assertEqual(len(second["created"]), 0)
        self.assertEqual(len(second["duplicates"]), 1)
        self.assertEqual(second["process_improvement_capture_state"], "already_tracked")
        self.assertEqual(second["process_improvement_capture_reason"], "duplicate_backlog_entries")

        receipt = self._read_receipt(
            root,
            "docs/plans/260417_1814_process_memory_finalize_process_improvement_suggestions_harvest.md",
            "Planner",
        )
        self.assertEqual(receipt["capture_state"], "already_tracked")

    def test_private_collect_keeps_same_suggestion_distinct_across_general_roles(self) -> None:
        root = self._root()
        source_ref = "docs/plans/260927_0901_cross_role_duplicate.md"
        text = dedent(
            f"""\
            ## Process improvements
            ### Suggestion 1
            - symptom: reviewers can repeat an already collected durable suggestion
            - process_gap: private collection keeps each collector role in its legacy duplicate key
            - suggested_fix: reserve cross-role de-duplication for the admitted public collector only
            - owner: Architect
            - promotion_class: helper_change
            - trigger_ref: docs/code_reviews/cross_role_duplicate.md#B1
            - source_ref: {source_ref}
            """
        )
        first = COLLECT.collect_process_improvements(
            project_root=root,
            role="Coder",
            source_ref=source_ref,
            text=text,
        )
        second = COLLECT.collect_process_improvements(
            project_root=root,
            role="Reviewer",
            source_ref=source_ref,
            text=text,
        )

        backlog = COLLECT.parse_backlog_file(root / first["backlog_files"][0], root)
        self.assertEqual(len(backlog.entries), 2)
        self.assertEqual(backlog.entries[0].role, "Coder")
        self.assertEqual(backlog.entries[1].role, "Reviewer")
        self.assertEqual(len(first["created"]), 1)
        self.assertEqual(len(second["created"]), 1)
        self.assertEqual(second["duplicates"], [])
        self.assertEqual(second["process_improvement_capture_state"], "materialized")

    def test_collect_normalizes_unknown_source_ref_to_cli_lane(self) -> None:
        root = self._root()
        payload = COLLECT.collect_process_improvements(
            project_root=root,
            role="Coder",
            source_ref="docs/plans/live.md",
            text=dedent(
                """\
                ## 3) Process improvements
                ### Suggestion 1
                - symptom: manager-fed plan_ref can be omitted in model text
                - process_gap: helper must still keep rows on the live carrier
                - suggested_fix: normalize unknown source_ref to the CLI lane before writing backlog rows
                - owner: Architect
                - promotion_class: helper_change
                - trigger_ref: docs/code_reviews/current.md#B1
                - source_ref: unknown
                """
            ),
        )

        self.assertEqual(payload["backlog_files"], ["docs/process_improvements/live__process_improvements_backlog.md"])
        backlog = COLLECT.parse_backlog_file(root / payload["backlog_files"][0], root)
        self.assertEqual(backlog.source_ref, "docs/plans/live.md")
        self.assertEqual(backlog.entries[0].source_ref, "docs/plans/live.md")

    def test_collect_rejects_mismatched_source_ref_against_cli_lane(self) -> None:
        root = self._root()
        with self.assertRaisesRegex(ValueError, "Structured `source_ref` must match manager-fed/header source_ref"):
            COLLECT.collect_process_improvements(
                project_root=root,
                role="Coder",
                source_ref="docs/plans/live.md",
                text=dedent(
                    """\
                    ## 3) Process improvements
                    ### Suggestion 1
                    - symptom: stale model ref can point to a historical carrier
                    - process_gap: helper trusted structured source_ref over manager-fed CLI source
                    - suggested_fix: reject mismatched source_ref instead of writing the row into another backlog file
                    - owner: Architect
                    - promotion_class: helper_change
                    - trigger_ref: docs/code_reviews/current.md#B1
                    - source_ref: docs/plans/historical.md
                    """
                ),
            )

        self.assertFalse((root / "docs" / "process_improvements").exists())
        receipt = self._read_receipt(root, "docs/plans/live.md", "Coder")
        self.assertEqual(receipt["capture_state"], "blocked")
        self.assertEqual(receipt["reason_code"], "collector_error")
        self.assertIn("Structured `source_ref` must match", receipt["error"])

    def test_collect_writes_blocked_receipt_for_malformed_structured_block(self) -> None:
        root = self._root()
        with self.assertRaisesRegex(ValueError, "Missing required field: suggested_fix"):
            COLLECT.collect_process_improvements(
                project_root=root,
                role="Reviewer",
                source_ref="docs/plans/live.md",
                text=dedent(
                    """\
                    ## 3) Process improvements
                    ### Suggestion 1
                    - symptom: structured process improvement has no carrier proof
                    - process_gap: helper accepted malformed role output
                    - owner: Architect
                    - promotion_class: helper_change
                    - trigger_ref: docs/code_reviews/current.md#B1
                    """
                ),
            )

        receipt = self._read_receipt(root, "docs/plans/live.md", "Reviewer")
        self.assertEqual(receipt["capture_state"], "blocked")
        self.assertEqual(receipt["reason_code"], "collector_error")
        self.assertIn("suggested_fix", receipt["error"])
        self.assertFalse((root / "docs" / "process_improvements").exists())

    def test_triage_updates_status_priority_and_target_path(self) -> None:
        root = self._root()
        collect_payload = COLLECT.collect_process_improvements(
            project_root=root,
            role="Reviewer",
            source_ref="docs/plans/260417_1814_process_memory_finalize_process_improvement_suggestions_harvest.md",
            text=dedent(
                """\
                ## 3) Process improvements
                ### Suggestion 1
                - symptom: raw process suggestions can shadow followups if carriers drift
                - process_gap: no explicit promotion surface with target_canon_path
                - suggested_fix: keep promotion state in one derived docs/process_improvements/promotion_surface.md file
                - owner: Reviewer
                - promotion_class: canon_update
                - trigger_ref: docs/plans/260417_1814_process_memory_finalize_process_improvement_suggestions_harvest.md
                - source_ref: docs/plans/260417_1814_process_memory_finalize_process_improvement_suggestions_harvest.md
                """
            ),
        )

        backlog_rel = collect_payload["backlog_files"][0]
        payload = COLLECT.update_backlog_entry(
            project_root=root,
            backlog_path=root / backlog_rel,
            entry_id="PI-001",
            status="triaged",
            priority="P1",
            owner="Architect",
            target_canon_path="docs/tools/owner_runbook_codex.md",
            target_repo_scope="current_consumer",
            delivery_mode="source_only",
            triage_note="bounded canon update after first live row",
        )

        self.assertEqual(payload["state"], "triaged")
        self.assertEqual(payload["status"], "triaged")
        self.assertEqual(payload["priority"], "P1")
        self.assertEqual(payload["owner"], "Architect")
        self.assertEqual(payload["target_canon_path"], "docs/tools/owner_runbook_codex.md")
        self.assertEqual(payload["target_repo_scope"], "current-consumer")
        self.assertEqual(payload["delivery_mode"], "source_only")

        backlog = COLLECT.parse_backlog_file(root / backlog_rel, root)
        entry = backlog.entries[0]
        self.assertEqual(entry.status, "triaged")
        self.assertEqual(entry.priority, "P1")
        self.assertEqual(entry.owner, "Architect")
        self.assertEqual(entry.target_canon_path, "docs/tools/owner_runbook_codex.md")
        self.assertEqual(entry.target_repo_scope, "current-consumer")
        self.assertEqual(entry.delivery_mode, "source_only")

        deferred_text = (root / "docs" / "process_improvements" / "deferred.md").read_text(encoding="utf-8")
        promotion_text = (root / "docs" / "process_improvements" / "promotion_surface.md").read_text(encoding="utf-8")
        self.assertNotIn("PI-001", deferred_text)
        self.assertIn("docs/tools/owner_runbook_codex.md", promotion_text)
        self.assertIn("current-consumer", promotion_text)
        self.assertIn("source_only", promotion_text)

    def test_triage_status_requires_complete_carrier_fields(self) -> None:
        root = self._root()
        collect_payload = COLLECT.collect_process_improvements(
            project_root=root,
            role="Reviewer",
            source_ref="docs/plans/incomplete_triage_carrier.md",
            text=dedent(
                """\
                ## 3) Process improvements
                ### Suggestion 1
                - symptom: triaged rows can still have null delivery fields
                - process_gap: status change alone can make raw PI rows look actioned
                - suggested_fix: reject status=triaged until target and delivery carrier fields are present
                - owner: Reviewer
                - promotion_class: helper_change
                - trigger_ref: docs/plans/incomplete_triage_carrier.md
                - source_ref: docs/plans/incomplete_triage_carrier.md
                """
            ),
        )

        backlog_rel = collect_payload["backlog_files"][0]
        with self.assertRaisesRegex(ValueError, "target_canon_path"):
            COLLECT.update_backlog_entry(
                project_root=root,
                backlog_path=root / backlog_rel,
                entry_id="PI-001",
                status="triaged",
                priority="P1",
                triage_note="triaged without a deterministic carrier",
            )

    def test_promoted_row_requires_target_delivery_fields(self) -> None:
        root = self._root()
        collect_payload = COLLECT.collect_process_improvements(
            project_root=root,
            role="Architect",
            source_ref="docs/plans/260418_1317_process_memory_finalize_process_improvements_promotion_wave_and_source_first_canon_delivery.md",
            text=dedent(
                """\
                ## 3) Process improvements
                ### Suggestion 1
                - symptom: mature rows can still drift into source-only canon edits
                - process_gap: promotion state lacks explicit repo scope and delivery mode
                - suggested_fix: require triage fields before status=promoted
                - owner: Architect
                - promotion_class: canon_update
                - trigger_ref: docs/plans/260418_1317_process_memory_finalize_process_improvements_promotion_wave_and_source_first_canon_delivery.md
                - source_ref: docs/plans/260418_1317_process_memory_finalize_process_improvements_promotion_wave_and_source_first_canon_delivery.md
                """
            ),
        )

        backlog_rel = collect_payload["backlog_files"][0]
        with self.assertRaisesRegex(ValueError, "target_repo_scope"):
            COLLECT.update_backlog_entry(
                project_root=root,
                backlog_path=root / backlog_rel,
                entry_id="PI-001",
                status="promoted",
                target_canon_path="docs/tools/owner_runbook_codex.md",
            )

        payload = COLLECT.update_backlog_entry(
            project_root=root,
            backlog_path=root / backlog_rel,
            entry_id="PI-001",
            status="promoted",
            priority="P1",
            owner="Architect",
            target_canon_path="docs/tools/owner_runbook_codex.md",
            target_repo_scope="multi_repo",
            delivery_mode="source_plus_rollout",
            execution_kind="plan",
            execution_ref="docs/plans/260418_1317_process_memory_finalize_process_improvements_promotion_wave_and_source_first_canon_delivery.md",
            delivery_refs="docs/rollouts/260418_packet.md; docs/rollouts/260418_ack.md",
            promoted_at="2026-04-30 12:30 MSK",
            triage_note="promotion wave after mature multi-repo signal",
        )

        self.assertEqual(payload["status"], "promoted")
        self.assertEqual(payload["target_repo_scope"], "multi_repo")
        self.assertEqual(payload["delivery_mode"], "source_plus_rollout")
        self.assertEqual(payload["execution_kind"], "plan")
        self.assertEqual(
            payload["execution_ref"],
            "docs/plans/260418_1317_process_memory_finalize_process_improvements_promotion_wave_and_source_first_canon_delivery.md",
        )
        self.assertEqual(payload["delivery_refs"], "docs/rollouts/260418_packet.md; docs/rollouts/260418_ack.md")

        promotion_text = (root / "docs" / "process_improvements" / "promotion_surface.md").read_text(encoding="utf-8")
        self.assertIn("Execution kind", promotion_text)
        self.assertIn("docs/rollouts/260418_packet.md; docs/rollouts/260418_ack.md", promotion_text)

    def test_promoted_row_requires_execution_fields(self) -> None:
        root = self._root()
        collect_payload = COLLECT.collect_process_improvements(
            project_root=root,
            role="Architect",
            source_ref="docs/plans/execution_pointer.md",
            text=dedent(
                """\
                ## 3) Process improvements
                ### Suggestion 1
                - symptom: promoted rows still lack a primary execution carrier
                - process_gap: promotion state can be literal on triage fields but prose-only on execution
                - suggested_fix: require execution_kind, execution_ref, and promoted_at for promoted rows
                - owner: Architect
                - promotion_class: helper_change
                - trigger_ref: docs/plans/execution_pointer.md
                - source_ref: docs/plans/execution_pointer.md
                """
            ),
        )

        backlog_rel = collect_payload["backlog_files"][0]
        with self.assertRaisesRegex(ValueError, "execution_kind"):
            COLLECT.update_backlog_entry(
                project_root=root,
                backlog_path=root / backlog_rel,
                entry_id="PI-001",
                status="promoted",
                priority="P1",
                owner="Architect",
                target_canon_path="scripts/process_improvements_triage.py",
                target_repo_scope="current-consumer",
                delivery_mode="source_only",
            )

    def test_handled_row_requires_terminal_refs(self) -> None:
        root = self._root()
        collect_payload = COLLECT.collect_process_improvements(
            project_root=root,
            role="Planner",
            source_ref="docs/plans/handled_pointer.md",
            text=dedent(
                """\
                ## 3) Process improvements
                ### Suggestion 1
                - symptom: handled rows can claim closure without terminal proof
                - process_gap: handled lifecycle has no handled_ref or handled_at receipt
                - suggested_fix: require handled_ref and handled_at before status=handled
                - owner: Planner
                - promotion_class: routing_change
                - trigger_ref: docs/plans/handled_pointer.md
                - source_ref: docs/plans/handled_pointer.md
                """
            ),
        )

        backlog_rel = collect_payload["backlog_files"][0]
        with self.assertRaisesRegex(ValueError, "handled_ref"):
            COLLECT.update_backlog_entry(
                project_root=root,
                backlog_path=root / backlog_rel,
                entry_id="PI-001",
                status="handled",
                priority="P2",
                owner="Planner",
                target_canon_path="docs/tools/prompts/manager_collab_pipeline.md",
                target_repo_scope="current-consumer",
                delivery_mode="source_only",
                execution_kind="canon_doc",
                execution_ref="docs/tools/prompts/manager_collab_pipeline.md",
                promoted_at="2026-04-30 12:31 MSK",
            )

        payload = COLLECT.update_backlog_entry(
            project_root=root,
            backlog_path=root / backlog_rel,
            entry_id="PI-001",
            status="handled",
            priority="P2",
            owner="Planner",
            target_canon_path="docs/tools/prompts/manager_collab_pipeline.md",
            target_repo_scope="current-consumer",
            delivery_mode="source_only",
            execution_kind="canon_doc",
            execution_ref="docs/tools/prompts/manager_collab_pipeline.md",
            delivery_refs="null",
            handled_ref="docs/code_reviews/handled_pointer.md",
            promoted_at="2026-04-30 12:31 MSK",
            handled_at="2026-04-30 12:32 MSK",
        )

        self.assertEqual(payload["status"], "handled")
        self.assertEqual(payload["handled_ref"], "docs/code_reviews/handled_pointer.md")
        self.assertEqual(payload["handled_at"], "2026-04-30 12:32 MSK")

        promotion_text = (root / "docs" / "process_improvements" / "promotion_surface.md").read_text(encoding="utf-8")
        self.assertIn("handled", promotion_text)
        self.assertIn("docs/code_reviews/handled_pointer.md", promotion_text)

    def test_delivery_refs_validation_accepts_null_and_literal_list(self) -> None:
        root = self._root()
        collect_payload = COLLECT.collect_process_improvements(
            project_root=root,
            role="Coder",
            source_ref="docs/plans/delivery_refs.md",
            text=dedent(
                """\
                ## 3) Process improvements
                ### Suggestion 1
                - symptom: delivery refs need deterministic rendering
                - process_gap: delivery refs can drift into prose or blobs
                - suggested_fix: allow only null or semicolon-separated literal refs
                - owner: Coder
                - promotion_class: helper_change
                - trigger_ref: docs/plans/delivery_refs.md
                - source_ref: docs/plans/delivery_refs.md
                """
            ),
        )

        backlog_rel = collect_payload["backlog_files"][0]
        with self.assertRaisesRegex(ValueError, "delivery_refs"):
            COLLECT.update_backlog_entry(
                project_root=root,
                backlog_path=root / backlog_rel,
                entry_id="PI-001",
                delivery_refs='["docs/rollouts/a.md"]',
            )

        payload = COLLECT.update_backlog_entry(
            project_root=root,
            backlog_path=root / backlog_rel,
            entry_id="PI-001",
            delivery_refs="docs/rollouts/a.md; docs/rollouts/b.md",
        )
        self.assertEqual(payload["delivery_refs"], "docs/rollouts/a.md; docs/rollouts/b.md")

    def test_deferred_row_requires_reason_and_literal_bridge_or_null_reason(self) -> None:
        root = self._root()
        collect_payload = COLLECT.collect_process_improvements(
            project_root=root,
            role="Architect",
            source_ref="docs/plans/deferred_pointer.md",
            text=dedent(
                """\
                ## 3) Process improvements
                ### Suggestion 1
                - symptom: deferred rows can look closed without a bridge
                - process_gap: deferred state lacks reason and revisit trigger
                - suggested_fix: require explicit deferred row closure fields
                - owner: Architect
                - promotion_class: routing_change
                - trigger_ref: docs/plans/deferred_pointer.md
                - source_ref: docs/plans/deferred_pointer.md
                """
            ),
        )

        backlog_rel = collect_payload["backlog_files"][0]
        with self.assertRaisesRegex(ValueError, "null-delivery reason"):
            COLLECT.update_backlog_entry(
                project_root=root,
                backlog_path=root / backlog_rel,
                entry_id="PI-001",
                status="deferred",
                triage_note="deferred until Owner review",
            )
        with self.assertRaisesRegex(ValueError, "reason/revisit trigger"):
            COLLECT.update_backlog_entry(
                project_root=root,
                backlog_path=root / backlog_rel,
                entry_id="PI-001",
                status="deferred",
                delivery_refs="docs/followups/deferred.md",
                triage_note="null",
            )

        payload = COLLECT.update_backlog_entry(
            project_root=root,
            backlog_path=root / backlog_rel,
            entry_id="PI-001",
            status="deferred",
            delivery_refs="null",
            triage_note="deferred until Owner review; delivery_refs=null because no bridge exists yet",
        )

        self.assertEqual(payload["status"], "deferred")
        self.assertEqual(payload["delivery_refs"], "null")
        self.assertIn("delivery_refs=null", payload["triage_note"])

    def test_import_file_report_is_dry_run_and_rejects_directories(self) -> None:
        root = self._root()
        source_file = root / "external" / "docs" / "process_improvements" / "260430_1248_review_artifact_planned_path_materialization.md"
        source_file.parent.mkdir(parents=True)
        source_file.write_text(
            dedent(
                """\
                # Process improvement - review artifact planned path materialization

                **Date:** 2026-04-30 12:48 MSK
                **Source:** memory-finalize reviewer
                **Status:** Proposed
                **Plan ref:** `docs/plans/source.md`

                ## Suggestion 1
                - symptom: docs-only review plans can pass preflight with PLANNED review artifact
                - process_gap: reviewer templates do not say PLANNED is pre-materialization only
                - suggested_fix: require review artifact file plus post-materialization bundle check
                - owner: Reviewer
                - promotion_class: canon_update
                - trigger_ref: `docs/doc_reviews/source.md`
                - source_ref: `docs/plans/source.md`
                """
            ),
            encoding="utf-8",
        )

        payload = COLLECT.import_process_improvements(
            project_root=root,
            import_files=[str(source_file)],
            apply=False,
        )

        self.assertEqual(payload["state"], "import_report")
        self.assertEqual(payload["mode"], "report")
        self.assertEqual(payload["imports"][0]["source_file"], source_file.resolve().as_posix())
        self.assertFalse((root / "docs" / "process_improvements").exists())
        with self.assertRaisesRegex(ValueError, "explicit files only"):
            COLLECT.import_process_improvements(
                project_root=root,
                import_files=[str(source_file.parent)],
                apply=False,
            )
        unsupported_file = root / "external" / "process_improvements" / "260430_1248_review_artifact_planned_path_materialization.md"
        unsupported_file.parent.mkdir(parents=True)
        unsupported_file.write_text(source_file.read_text(encoding="utf-8"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "docs/process_improvements"):
            COLLECT.import_process_improvements(
                project_root=root,
                import_files=[str(unsupported_file)],
                apply=False,
            )

    def test_import_file_apply_preserves_provenance_and_ignores_source_status(self) -> None:
        root = self._root()
        source_file = root / "external" / "docs" / "process_improvements" / "260430_1227_template_parity_hard_break_noise.md"
        source_file.parent.mkdir(parents=True)
        source_file.write_text(
            dedent(
                """\
                # Process improvement - review-template parity hard-break noise

                **Date:** 2026-04-30 12:27 MSK
                **Source:** memory
                **Status:** Applied
                **Plan ref:** `docs/plans/source.md`

                ## Suggestion 1
                - symptom: exact source-parity sync can preserve Markdown hard-break whitespace
                - process_gap: shared README did not say diff --check is hygiene-only for exact parity slices
                - suggested_fix: document the parity gate and any deliberate whitespace deviation
                - owner: Architect
                - promotion_class: canon_update
                - trigger_ref: unknown
                - source_ref: manager-fed plan_ref
                - note: Applied in docs/plans/README.md during closeout.
                """
            ),
            encoding="utf-8",
        )

        payload = COLLECT.import_process_improvements(
            project_root=root,
            import_files=[str(source_file)],
            apply=True,
        )

        self.assertEqual(payload["state"], "imported")
        backlog_rel = "docs/process_improvements/260430_1227_template_parity_hard_break_noise__process_improvements_backlog.md"
        self.assertEqual(payload["backlog_files"], [backlog_rel])
        backlog = COLLECT.parse_backlog_file(root / backlog_rel, root)
        self.assertEqual(backlog.source_ref, source_file.resolve().as_posix())
        self.assertEqual(len(backlog.entries), 1)
        entry = backlog.entries[0]
        self.assertEqual(entry.status, "open")
        self.assertEqual(entry.owner, "Architect")
        self.assertEqual(entry.role, "Architect")
        self.assertEqual(entry.source_ref, source_file.resolve().as_posix())
        self.assertIn("source_status=Applied", entry.triage_note)
        self.assertIn("source_plan_ref=docs/plans/source.md", entry.triage_note)
        self.assertIn("source_ref_original=manager-fed_plan_ref", entry.triage_note)

        index_text = (root / "docs/process_improvements/index.md").read_text(encoding="utf-8")
        promotion_text = (root / "docs/process_improvements/promotion_surface.md").read_text(encoding="utf-8")
        self.assertIn(backlog_rel, index_text)
        self.assertIn("source_status=Applied", promotion_text)

        duplicate = COLLECT.import_process_improvements(
            project_root=root,
            import_files=[str(source_file)],
            apply=True,
        )
        self.assertEqual(duplicate["created"], [])
        self.assertEqual(len(duplicate["duplicates"]), 1)

    def test_import_file_accepts_russian_suggestion_headings(self) -> None:
        root = self._root()
        source_file = root / "external" / "docs" / "process_improvements" / "260502_0409_new_target_path_tracking_stub_contract.md"
        source_file.parent.mkdir(parents=True)
        source_file.write_text(
            dedent(
                """\
                # Улучшение процесса — path-tracking stub для новых target-файлов

                **Date:** 2026-05-02 04:09 MSK
                **Source:** memory-finalize planner
                **Status:** Proposed
                **Plan ref:** git history: `docs/plans/source.md`

                ## Предложение 1
                - symptom: Planner preflight fails on a new target path before Coder creates the file
                - process_gap: plan and code draft canon do not define planned-new target paths
                - suggested_fix: define a fail-closed stub or first-class planned_new_paths metadata
                - owner: Architect
                - promotion_class: canon_update
                - trigger_ref: git history: `docs/plans/source.md`
                - source_ref: git history: `docs/plans/source.md`
                """
            ),
            encoding="utf-8",
        )

        payload = COLLECT.import_process_improvements(
            project_root=root,
            import_files=[str(source_file)],
            apply=True,
        )

        self.assertEqual(payload["state"], "imported")
        backlog_rel = "docs/process_improvements/260502_0409_new_target_path_tracking_stub_contract__process_improvements_backlog.md"
        self.assertEqual(payload["backlog_files"], [backlog_rel])
        backlog = COLLECT.parse_backlog_file(root / backlog_rel, root)
        self.assertEqual(backlog.entries[0].owner, "Architect")

    def test_import_file_accepts_nested_russian_suggestion_headings(self) -> None:
        root = self._root()
        source_file = root / "external" / "docs" / "process_improvements" / "260502_1111_visual_acceptance_deferred_lane_n_a_contract.md"
        source_file.parent.mkdir(parents=True)
        source_file.write_text(
            dedent(
                """\
                # Улучшение процесса — N/A contract для deferred Visual Acceptance lane

                **Date:** 2026-05-02 11:11 MSK
                **Source:** git history: `docs/plans/source.md`

                ## Улучшения процесса

                ### Предложение 1
                - symptom: Visual Acceptance was replaced by one N/A paragraph
                - process_gap: template guidance does not require structural N/A subheads
                - suggested_fix: keep required Visual Acceptance subheads with exact N/A reasons
                - owner: Planner
                - promotion_class: prompt_change
                - trigger_ref: git history: `docs/plans/source.md`
                - source_ref: git history: `docs/plans/source.md`
                """
            ),
            encoding="utf-8",
        )

        payload = COLLECT.import_process_improvements(
            project_root=root,
            import_files=[str(source_file)],
            apply=True,
        )

        self.assertEqual(payload["state"], "imported")
        backlog_rel = "docs/process_improvements/260502_1111_visual_acceptance_deferred_lane_n_a_contract__process_improvements_backlog.md"
        backlog = COLLECT.parse_backlog_file(root / backlog_rel, root)
        self.assertEqual(backlog.entries[0].owner, "Planner")
    def test_engaged_safe_pi_collection_writes_only_closed_data_universe(self) -> None:
        root = self._root()
        source_ref = "docs/plans/260927_0001_engaged_safe_fixture.md"
        body = dedent(
            f"""\
            ## Process improvements
            ### Suggestion 1
            - symptom: engaged fixture needs one safe PI carrier
            - process_gap: the public collector must retain the exact closed write universe
            - suggested_fix: use the admitted safe PI writer for this source only
            - owner: Architect
            - promotion_class: helper_change
            - trigger_ref: docs/code_reviews/fixture.md#B1
            - source_ref: {source_ref}
            """
        )
        with mock.patch.object(COLLECT, "_validate_writer_effect") as checked:
            first = COLLECT._collect_process_improvements(
                project_root=root,
                role="Coder",
                source_ref=source_ref,
                text=body,
                write_receipt=False,
                context=object(),
                engaged_public=True,
            )
            duplicate = COLLECT._collect_process_improvements(
                project_root=root,
                role="Coder",
                source_ref=source_ref,
                text=body,
                write_receipt=False,
                context=object(),
                engaged_public=True,
            )

        backlog_rel = COLLECT.backlog_rel_path_for_source_ref(source_ref)
        expected = {
            backlog_rel,
            COLLECT.INDEX_PATH.as_posix(),
            COLLECT.DEFERRED_PATH.as_posix(),
            COLLECT.PROMOTION_PATH.as_posix(),
        }
        observed = {
            path.relative_to(root).as_posix()
            for path in (root / "docs" / "process_improvements").iterdir()
            if path.is_file()
        }
        self.assertEqual(len(first["created"]), 1)
        self.assertEqual(first["duplicates"], [])
        self.assertEqual(duplicate["created"], [])
        self.assertEqual(len(duplicate["duplicates"]), 1)
        self.assertEqual(observed, expected)
        self.assertGreaterEqual(checked.call_count, 8)

    def test_engaged_safe_pi_write_refuses_symlink_and_preserves_existing_markdown_mode(self) -> None:
        rel_path = "docs/process_improvements/safe__process_improvements_backlog.md"
        unsafe_root = self._root()
        outside = unsafe_root.parent / f"{unsafe_root.name}-outside"
        outside.mkdir()
        (unsafe_root / "docs").mkdir()
        (unsafe_root / "docs" / "process_improvements").symlink_to(outside, target_is_directory=True)
        with mock.patch.object(COLLECT, "_validate_writer_effect"):
            with self.assertRaisesRegex(ValueError, "unsafe engaged process-improvement ancestor"):
                COLLECT._safe_pi_write_text(unsafe_root, rel_path, "# blocked\n", context=object())
        self.assertEqual(list(outside.iterdir()), [])

        root = self._root()
        path = root / rel_path
        path.parent.mkdir(parents=True)
        path.write_text("# existing\n", encoding="utf-8")
        path.chmod(0o640)
        with mock.patch.object(COLLECT, "_validate_writer_effect") as checked:
            COLLECT._safe_pi_write_text(root, rel_path, "# replaced\n", context=object())

        self.assertEqual(path.read_text(encoding="utf-8"), "# replaced\n")
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o640)
        self.assertGreaterEqual(checked.call_count, 2)

    def test_engaged_safe_pi_fd_anchor_rejects_ancestor_substitution_without_external_effect(self) -> None:
        """A replacement between lstat and open cannot redirect a collector read/write."""

        def substitute_docs_once(root: Path, outside: Path):
            original_open = COLLECT.os.open
            changed = False

            def guarded_open(path, flags, mode=0o777, *, dir_fd=None):
                nonlocal changed
                if path == "docs" and dir_fd is not None and not changed:
                    changed = True
                    docs = root / "docs"
                    docs.rename(root / "docs-before-substitution")
                    docs.symlink_to(outside, target_is_directory=True)
                if dir_fd is None:
                    return original_open(path, flags, mode)
                return original_open(path, flags, mode, dir_fd=dir_fd)

            return mock.patch.object(COLLECT.os, "open", side_effect=guarded_open)

        for operation in ("read", "write"):
            with self.subTest(operation=operation):
                root = self._root()
                target = root / "docs/process_improvements/fd_anchor__process_improvements_backlog.md"
                target.parent.mkdir(parents=True)
                target.write_text("# fixed collector target\n", encoding="utf-8")
                outside = root / f"outside-{operation}"
                outside.mkdir()
                sentinel = outside / "must-not-change.txt"
                sentinel.write_text("external sentinel\n", encoding="utf-8")
                before = sentinel.read_bytes()

                with substitute_docs_once(root, outside):
                    if operation == "read":
                        with self.assertRaisesRegex(ValueError, "cannot safely open engaged process-improvement directory"):
                            COLLECT._safe_pi_read_regular(root, target.relative_to(root).as_posix())
                    else:
                        with self.assertRaisesRegex(ValueError, "cannot safely open engaged process-improvement directory"):
                            COLLECT._safe_pi_write_text(
                                root,
                                target.relative_to(root).as_posix(),
                                "# must not write\n",
                                context=None,
                            )

                self.assertTrue((root / "docs-before-substitution").is_dir())
                self.assertEqual(sentinel.read_bytes(), before)
                self.assertEqual(list(outside.iterdir()), [sentinel])

    def test_engaged_safe_pi_regular_leaf_fingerprint_rejects_same_inode_drift(self) -> None:
        """An in-place same-size mutation cannot be read or overwritten as a pinned leaf."""

        root = self._root()
        rel_path = "docs/process_improvements/fingerprint__process_improvements_backlog.md"
        target = root / rel_path
        target.parent.mkdir(parents=True)

        before = b"before!\n"
        changed = b"after!!\n"
        self.assertEqual(len(before), len(changed))
        target.write_bytes(before)
        original_read = COLLECT.os.read
        read_mutated = False

        def mutate_after_first_read(fd: int, count: int) -> bytes:
            nonlocal read_mutated
            data = original_read(fd, count)
            if data and not read_mutated:
                read_mutated = True
                target.write_bytes(changed)
            return data

        with mock.patch.object(COLLECT.os, "read", side_effect=mutate_after_first_read):
            with self.assertRaisesRegex(ValueError, "file changed while reading"):
                COLLECT._safe_pi_read_regular(root, rel_path)
        self.assertTrue(read_mutated)
        self.assertEqual(target.read_bytes(), changed)

        target.write_bytes(before)
        target_inode = target.stat().st_ino
        original_fsync = COLLECT.os.fsync
        write_mutated = False

        def mutate_after_temporary_fsync(fd: int) -> None:
            nonlocal write_mutated
            original_fsync(fd)
            if not write_mutated and os.fstat(fd).st_ino != target_inode:
                write_mutated = True
                target.write_bytes(changed)

        with mock.patch.object(COLLECT.os, "fsync", side_effect=mutate_after_temporary_fsync):
            with self.assertRaisesRegex(ValueError, "output changed while writing"):
                COLLECT._safe_pi_write_text(root, rel_path, "replacement\n", context=None)
        self.assertTrue(write_mutated)
        self.assertEqual(target.read_bytes(), changed)

        receipt_rel = Path(".tmp/followups_capture/process_improvements/fingerprint.json")
        receipt_path = root / receipt_rel
        receipt_path.parent.mkdir(parents=True)
        receipt_before = b'{"capture_state":"blocked","x":0}\n'
        receipt_changed = b'{"capture_state":"blocked","x":1}\n'
        self.assertEqual(len(receipt_before), len(receipt_changed))
        receipt_path.write_bytes(receipt_before)
        receipt_inode = receipt_path.stat().st_ino
        receipt_mutated = False

        def mutate_receipt_after_temporary_fsync(fd: int) -> None:
            nonlocal receipt_mutated
            original_fsync(fd)
            if not receipt_mutated and os.fstat(fd).st_ino != receipt_inode:
                receipt_mutated = True
                receipt_path.write_bytes(receipt_changed)

        with mock.patch.object(COLLECT.os, "fsync", side_effect=mutate_receipt_after_temporary_fsync):
            with self.assertRaisesRegex(ValueError, "continuation receipt changed while writing"):
                COLLECT._safe_pi_write_v2_capture_receipt(
                    project_root=root,
                    rel_path=receipt_rel,
                    receipt={"capture_state": "already_tracked"},
                    replace_blocked=True,
                    context=None,
                    active_admission=None,
                )
        self.assertTrue(receipt_mutated)
        self.assertEqual(receipt_path.read_bytes(), receipt_changed)


if __name__ == "__main__":
    unittest.main()
